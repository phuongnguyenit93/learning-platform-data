# Ownership, Lifecycle Dependency, and the Semantics of Deleting Related Entities

In a data model, having a relationship between two entities does not mean one entity owns the other. A customer can place many orders, yet an order that has entered into transactions usually needs to be retained even when the customer profile becomes inactive. Conversely, an order line item normally has meaning only within the order that contains it; if a draft order is deleted under an allowed workflow, its corresponding draft line items can be deleted alongside it.

Therefore, when modeling a relationship, clarify three questions:

- **Ownership:** which entity governs the lifecycle of the other within the business scope?
- **Lifecycle dependency:** can the dependent entity exist independently when the owner entity ceases to exist?
- **Deletion semantics:** if one side is deleted, must data on the other side be preserved, deleted with it, detached, or transitioned to another status?

These questions directly affect entity boundaries, keys, relationships, referential constraints, and retention policies. Making the wrong choice can destroy transactional data, leave orphan records, or render the system unable to explain historical facts.

This lesson helps distinguish ownership relationships from ordinary associations, identify dependent entities, map out lifecycles, and select deletion behaviors that match business semantics.

**After this lesson, you will be able to:**

- Distinguish ownership relationships, reference relationships, and general associative links.
- Identify dependent entities and entities with independent lifecycles.
- Describe the lifecycles of owner entities and child entities.
- Distinguish physical deletion, soft deletion, business cancellation, deactivation, archiving, and anonymization.
- Choose among RESTRICT, CASCADE, SET NULL, and other handling policies.
- Audit risks of orphan data, cascading deletes, and lost history.
- Translate lifecycle decisions into a verifiable logical model.

## 1. What is ownership in data relationships?

In this lesson, **ownership** describes a dependency relationship in lifecycle and data management responsibility. An owner entity controls the existence or scope of a child entity under business rules.

Examples:

- An order manages its own order lines.
- A shopping cart manages the items currently inside the cart.
- A user profile manages that profile's personal preferences.
- A warehouse receipt manages the item lines recorded on that receipt.

When the owner entity is no longer valid, the child entity may also lose independent meaning. An order line cannot be interpreted properly without knowing which order it belongs to. A cart item has no meaning if the cart has been discarded and the business does not permit retaining that item as a standalone object.

Ownership in a data model is not synonymous with legal ownership, asset ownership, or security access permissions. A customer may be the business owner of an account, yet the relationship between CUSTOMER and ORDER still requires separate data-lifecycle analysis.

### 1.1. Signs of a lifecycle ownership relationship

A relationship may imply ownership if most of the following hold true:

- The child entity is created while creating or operating on the owner entity.
- The child entity always belongs to a specific owner within the business scope.
- The child entity has no independent meaning without the owner entity.
- The child's identifier may depend on the owner's identifier.
- Update permissions, status, or rules of the child are directly governed by the owner.
- When the owner ends its lifecycle, business rules require the child to end as well, be archived alongside it, or follow an explicit dependency rule.

Not every sign has to hold. This is a diagnostic checklist rather than an automatic formula.

### 1.2. Ownership is not synonymous with a one-to-many relationship

A customer can have many orders, yet that does not mean orders are child data to be deleted when the customer is deleted.

A customer can have many saved addresses in an address book. Those addresses may belong to the customer profile and be deleted when the profile is deleted if unused elsewhere. However, the shipping address finalized on an order may need to be preserved as a historical transaction snapshot.

Accordingly:

- **Cardinality** answers how many instances link to one another.
- **Ownership** answers who governs the lifecycle and existence of related data.
- **Delete behavior** answers how the system handles related data when an object is deleted.

These three dimensions are related but cannot be inferred as substitutes for one another.

## 2. Distinguishing owner, dependent child, and referenced entities

### 2.1. Owner (or parent) entity

An owner entity governs the existence scope of one or more child objects. It typically has its own identifier and independent business lifecycle.

Examples:

- ORDER is the owner of ORDER_LINE.
- CART is the owner of CART_ITEM.
- PURCHASE_ORDER is the owner of PURCHASE_ORDER_LINE.

An owner entity can exist without children in certain states. For instance, a newly created cart may be empty; a draft order may still be under construction. Therefore, do not assume a parent–child relationship is always mandatory in both directions.

### 2.2. Dependent child entity

A dependent entity is an object that requires an owner entity to be identified or to hold business meaning.

For example, an order line is typically identified within the scope of an order. The line sequence number may be unique only within that order. A line without a parent order is an incomplete record.

Typical signs:

- Its identifying key includes the owner entity's key;
- Each child instance belongs to exactly one owner at a time;
- No independent business lifecycle;
- Deleting or ending the owner makes the child invalid;
- Child attributes depend on both the owner key and the local identifier.

### 2.3. Referenced or shared entity

A referenced entity can be used by many other entities and has its own lifecycle. It is not automatically deleted when an entity referencing it is deleted.

Examples:

- `PRODUCT_VARIANT` is referenced by many order lines.
- `WAREHOUSE` is referenced by many receipts, issues, and shipments.
- `PAYMENT_METHOD` is used by many transactions.
- `CUSTOMER` can be referenced by many orders.

A product may be discontinued while historical order lines still need to reference it to explain past transactions. Deleting a product as soon as it stops selling can destroy traceability.

### 2.4. Comparison table

| Criterion | Owner entity | Dependent child entity | Referenced entity |
|---|---|---|---|
| Role | Manages scope or lifecycle | Exists within the owner's scope | Referenced by many objects |
| Identity | Usually independent | May depend on the owner | Usually independent |
| Can be shared? | Possibly | Usually no | Usually yes |
| Lifecycle | Coordinates or encloses children | Tied to the owner | Separate |
| When another entity is deleted | Follows its own rules | May be deleted with the owner | Usually retained |
| Example | Order | Order line | Product variant |

## 3. Distinguishing identity dependency from lifecycle dependency

These two forms of dependency often appear together, yet they are not always identical.

### 3.1. Identity dependency

An identity-dependent entity cannot be fully identified without the owner entity's key.

For example, an order line is identified by the pair:

- `order_id`;
- `line_number`.

Within one order, `line_number` can be unique. Across different orders, line numbers repeat. The composite key identifies the line using both the parent order and the sequence number.

### 3.2. Lifecycle dependency

A lifecycle-dependent entity requires the owner entity to exist for itself to remain meaningful in the business domain.

For example, an item in a shopping cart belongs to a specific cart. If the cart is discarded, that item can be deleted alongside it.

An entity with its own ID can still be lifecycle-dependent. For example, `CART_ITEM` may have its own `cart_item_id` for convenient updates, yet it remains meaningless if the owner cart is deleted.

Conversely, a record with a composite key does not necessarily have to be deleted with its owner under all circumstances. Historical retention or audit rules may require preserving the record even if the owner has transitioned to a terminal status. Clarify whether such records represent valid historical data or unwanted orphan records.

### 3.3. Questions to determine dependency

| Question | If Yes | If No |
|---|---|---|
| Can the child be created without an owner yet? | May be an independent entity or an under-specified relationship | Sign of lifecycle dependency |
| Can the child move to another owner? | Needs ownership-transfer or link-reassignment rules | Likely dependent on current owner |
| Can the child be referenced by multiple owners? | Likely a shared entity or associative relationship | Likely a dedicated child of one owner |
| When the owner ends, does the child still carry meaning? | Needs child retention or status transition | Can be deleted alongside or archived within historical scope |
| Does the child have a stable independent identifier? | May be identity-independent | May need a composite key with the owner |

Do not rely on a single answer to decide. For instance, an address has its own ID yet is owned inside a customer's address book; meanwhile, a shipping address snapshot on an order follows the order's lifecycle.

## 4. Lifecycles of owner and child entities

A lifecycle describes the states and events an object passes through from creation to termination. When ownership exists, understand how events on the owner affect the child.

A simple lifecycle might include:

1. Create the owner entity;
2. Create child entities;
3. Update or add children;
4. Confirm or activate the owner;
5. Close, cancel, or archive the owner;
6. Handle child data according to the defined policy.

For example, a shopping cart can be in ACTIVE, CHECKED_OUT, or ABANDONED status. Cart items can be added, edited, or removed while the cart is active. When the cart converts into an order, the system can copy the items into a new structure or create an order while keeping the cart as historical data. This is a business decision that must be confirmed.

### 4.1. Lifecycles do not always end in physical deletion

When an order is canceled, the order and order-line data usually still need to be kept to explain the transaction, support operational auditing, or assist customer support. Order cancellation is a business event that changes status—it is not synonymous with deleting records.

Similarly:

- Discontinuing a product does not imply deleting the product.
- Locking an account does not imply deleting the account.
- Closing a contract does not imply deleting contract history.
- Canceling an unapproved request can transition status to CANCELLED instead of deleting it.

### 4.2. Transferring ownership or changing the owner

Some objects can be transferred from one owner to another. For example, equipment moves from one department to another, or a case is reassigned to a new processing team.

Distinguish among:

- Updating the current owner;
- Adding a new stakeholder;
- Closing the old relationship and creating a new one;
- Retaining transfer history.

If ownership changes over time, an associative entity such as `ASSET_ASSIGNMENT` with `asset_id`, `owner_id`, `valid_from`, and `valid_to` may be needed. This preserves the history of who held responsibility during each period.

Do not simply overwrite `owner_id` if the business needs to trace handovers.

## 5. The semantics of deleting a related entity

Deleting data can carry many different meanings. Before choosing behavior in the logical model, ask what the user actually intends to terminate.

| Action | Meaning | Example |
|---|---|---|
| Physical delete | Removes the record from the data store | Deleting a draft cart item |
| Soft delete | Marks the record inactive or deleted | Marking an old address inactive |
| Business cancellation | Records an event moving the object to a canceled state | Canceling a placed order |
| Deactivation | Prevents use in new transactions while retaining data | Discontinuing a product variant |
| Archiving | Moves data to archival storage or an archived state | Archiving long-completed orders |
| Anonymization | Replaces or strips identifying details per policy | Anonymizing personal info when identification is no longer needed |

These actions are not equivalent. For example, soft deletion does not automatically soft-delete child records; canceling an order does not mean deleting order lines; discontinuing a product does not mean removing references in past orders.

### 5.1. Deleting an owner entity

When deletion of an owner entity is requested, review:

- Are there any dependent child entities?
- Are any shared entities referencing it?
- Are there historical or transactional records that must be retained?
- Are there legal, audit, reconciliation, or operational constraints?
- Do external systems hold references to it?
- Can anonymization or deactivation be used instead of physical deletion?

Do not apply a single deletion behavior to every relationship merely because they all use foreign keys.

### 5.2. Deleting a child entity

When deleting a child entity, check whether it is referenced by other entities or has already entered transactions.

For example, an order line can be deleted while the order is still in draft status. Once the order is confirmed or shipped, deleting a line can distort totals, invoices, payments, and shipment history. In that case, the business may require line cancellation, an adjustment, or a compensating transaction.

## 6. ON DELETE behaviors in the relational model

In relational databases, foreign keys can specify what happens when a referenced record is deleted. Common options include RESTRICT, NO ACTION, CASCADE, SET NULL, and SET DEFAULT. Exact syntax, evaluation timing, and support details vary across DBMSs.

### 6.1. RESTRICT

RESTRICT prevents deleting the parent record if any child records still reference it.

Example: forbid deleting `PRODUCT_VARIANT` if historical order lines still reference that variant.

This is usually the right choice when child data must be preserved and parent retirement must go through a separate business workflow, such as discontinuing a product.

### 6.2. NO ACTION

NO ACTION also requires referential integrity to hold when the constraint is checked. Depending on the DBMS, check timing and constraint deferrability may differ from RESTRICT.

Do not assume these two keywords behave identically on every platform. At implementation time, verify your DBMS documentation and when constraints are evaluated.

### 6.3. CASCADE

CASCADE deletes referencing child records when the parent record is deleted. It is suitable when child data is genuinely dependent and holds no independent meaning.

For example, if a draft cart is deleted, its private cart items can be deleted along with it. For order lines, cascade may be appropriate within the scope of draft orders permitted for physical deletion.

Use CASCADE with caution:

- Deleting one parent record can wipe out multiple layers of data;
- A child table may be referenced by other relationships;
- Cascade chains can propagate further than anticipated;
- History or reconciliation records may be lost;
- Side effects are hard to spot without inspecting the entire foreign key graph.

### 6.4. SET NULL

SET NULL keeps the child record while setting the referencing foreign key to NULL when the parent record is deleted.

It is appropriate when the relationship is optional and the child record remains meaningful independently. For example, a support ticket can be retained even if the former assigned agent is removed from the system, provided the business allows clearing the assignee reference.

Never use SET NULL if the foreign key is part of the primary key, or if NULL removes mandatory information. Also verify whether losing the link makes the record hard to explain.

### 6.5. SET DEFAULT

SET DEFAULT replaces the foreign key with a default value when the parent record is deleted. That default value must point to a valid record if a foreign key constraint is active.

For example, a record might be reassigned to a default group such as "Unassigned" if the business defines that group as valid and meaningful. However, never use an artificial default value to mask the loss of a relationship.

### 6.6. Behavior comparison table

| Behavior | Child data | Relationship after parent deletion | When to consider |
|---|---|---|---|
| RESTRICT | Retained | Blocks parent deletion while references exist | Child must remain and reference parent |
| NO ACTION | Retained | Checks integrity at constraint evaluation time | When relying on DBMS constraint check rules |
| CASCADE | Deleted alongside | No child records remain | Child is completely dependent and deletion is permitted |
| SET NULL | Retained | Foreign key becomes NULL | Link can be lost while child stays valid |
| SET DEFAULT | Retained | Foreign key switches to default | A valid, meaningful default target exists |

No single option is always right. Decisions must rest on each relationship's lifecycle and business meaning.

## 7. Example: Order and order lines

An order has order lines. Order lines have no meaning without belonging to an order. In a system that allows deleting draft orders with no transactions yet, deleting the order can also delete its draft lines.

~~~mermaid
erDiagram
    ORDER ||--|{ ORDER_LINE : owns
    PRODUCT_VARIANT ||--o{ ORDER_LINE : referenced_by
~~~

An illustrative logical structure:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    order_status VARCHAR(30) NOT NULL
);

CREATE TABLE order_line (
    order_id BIGINT NOT NULL,
    line_number INTEGER NOT NULL,
    product_variant_id BIGINT NOT NULL,
    quantity DECIMAL(12, 3) NOT NULL,
    unit_price DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (order_id, line_number),
    FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
        ON DELETE CASCADE,
    FOREIGN KEY (product_variant_id)
        REFERENCES product_variant(product_variant_id)
        ON DELETE RESTRICT
);
~~~

In this example:

- ORDER is the owner entity of ORDER_LINE.
- ORDER_LINE depends on the order for identity and existence.
- PRODUCT_VARIANT is a referenced entity; an order line does not own the product.
- Deleting an order can delete its lines if the workflow allows it.
- Deleting a product variant is blocked while order lines still reference it.

However, a foreign-key cascade is unaware of order status. If the system only permits deleting orders in DRAFT status, that rule must be enforced via a business workflow or additional mechanism. Foreign keys only handle referential integrity—they do not understand conditions like "only delete draft orders."

## 8. Example: Customer, orders, and historical data

A customer can create many orders. Although this relationship has one-to-many cardinality, orders generally need to exist independently once transactions occur.

Deleting a customer with CASCADE could wipe out all orders, order lines, and related historical data. That is usually dangerous for transactional data.

A viable design direction is:

- Retain orders and order lines;
- Block hard deletion of a customer while referenced orders exist;
- Or anonymize personal data under an approved policy;
- Retain the minimal transactional details needed to explain the order;
- Distinguish current profile data from snapshots captured at placement time.

For example, an order can store the recipient name and shipping address at placement time. When the customer updates the address in their profile, older orders retain the finalized address. That snapshot belongs to transaction history and must not mutate alongside the current profile.

### 8.1. Deactivation instead of deletion

For customers, products, warehouses, or payment methods, businesses typically need deactivation rather than data deletion. Statuses such as ACTIVE, INACTIVE, or DEACTIVATED can be used, along with transition timestamps if needed.

Clarify:

- The object cannot be used in new transactions;
- Past transactions can still reference it;
- Whether users can view its history;
- Whether it can be reactivated;
- Whether business codes can be reused.

Do not use a single `is_deleted` flag to represent every terminal status when the business distinguishes cancellation, deactivation, archiving, and deletion on request.

## 9. Soft delete, archiving, and anonymization

### 9.1. Soft delete

Soft deletion keeps the record in the database while marking it hidden or inactive under application policy. For example, using `deleted_at`, `deleted_by`, or a `DELETED` status.

Advantages:

- Recoverable within an allowed window;
- Preserves references from historical data;
- Supports investigation and auditing;
- Prevents unintended cascading deletions.

Caveats:

- Foreign keys still see soft-deleted records;
- Queries must filter by the appropriate status;
- Unique constraints may need to apply only to active records;
- Reports may accidentally include soft-deleted data;
- Restoration must check conflicts and lifecycle rules.

Soft delete is not automatically equivalent to CASCADE. To mark children alongside an owner, the application must execute an explicit workflow or use appropriate state management.

### 9.2. Archiving

Archiving typically moves old data to storage tiers or states meant for infrequent access. The data may still be needed for reporting, audits, or historical lookups.

When archiving an owner entity, ensure child data and related links remain queryable or reconstructible. Never move only the parent table while breaking links to child tables.

### 9.3. Anonymization

Anonymization replaces or strips personally identifying fields while retaining data needed for other purposes. For instance, retaining transaction figures while no longer displaying personal names or contact information under an approved policy.

Anonymization is not the same as soft deletion. Because it alters data values, determine:

- Which attributes are retained;
- Which attributes are replaced or erased;
- Whether linkability across transactions must be preserved;
- Whether pseudonymized identifiers must be kept;
- Which tables or replicas must also be processed.

This is a business and data governance decision, not something to infer solely from foreign key relationships.

## 10. When to use CASCADE and when to block deletion

A practical rule of thumb is to use CASCADE only when child data is truly dependent on the parent and business rules allow physically deleting both.

| Relationship | Commonly considered behavior | Reason |
|---|---|---|
| CART → CART_ITEM | CASCADE | Cart items depend on the cart; draft carts can be deleted |
| ORDER → ORDER_LINE | Conditionally controlled CASCADE | Lines depend on the order, yet transacted orders normally cannot be hard-deleted |
| PRODUCT_VARIANT → ORDER_LINE | RESTRICT or product deactivation | Historical order lines must preserve references |
| CUSTOMER → ORDER | RESTRICT, or retain/anonymize customer | Orders must persist after transactions |
| ORDER → PAYMENT_ATTEMPT | Typically retain and block order deletion once attempts exist | Payment processing history requires traceability |
| SHIPMENT → SHIPMENT_EVENT | CASCADE if shipment deletion is valid; usually retain history after dispatch | Events depend on the shipment but often need history retention |
| USER → USER_PREFERENCE | CASCADE may fit | Personal preferences depend on the profile |
| USER → AUDIT_EVENT | Typically retain events and handle identity per policy | Audit trails must not vanish merely because an account is deleted |

The behaviors in this table are starting suggestions. Always confirm actual workflows, retention requirements, and states before finalizing.

## 11. Preventing orphan data and unintended cascading deletes

### 11.1. Orphan records

An orphan record is a child record referencing an owner entity that no longer exists or cannot be resolved in the model.

Foreign keys prevent many orphan cases in relational databases. However, orphan data can still arise when:

- Foreign key constraints are omitted or disabled;
- Data is imported bypassing validation;
- Data spans multiple systems without a shared transaction;
- Referenced keys are manually modified or deleted;
- Relationships are represented by plain text codes rather than foreign keys.

Validation and reconciliation processes are needed when data is synchronized across systems.

### 11.2. Cascading deletes

Cascading deletion happens when deleting one parent record triggers deleting many child records, which in turn delete deeper layers.

Example:

~~~mermaid
flowchart TD
    A["Delete CUSTOMER"] --> B["ORDER"]
    B --> C["ORDER_LINE"]
    B --> D["PAYMENT"]
    B --> E["SHIPMENT"]
    E --> F["SHIPMENT_EVENT"]
    style D fill:#fce8e6,stroke:#c5221f,color:#5f1110
    style F fill:#fce8e6,stroke:#c5221f,color:#5f1110
~~~

This diagram illustrates a potential dependency chain. If every relationship used CASCADE, deleting a customer would wipe out transactions and shipping history—potentially violating data retention requirements.

Before choosing cascade, trace every reference path and answer:

- Which tables could be deleted indirectly?
- Is any of that data shared or required to be stored independently?
- Have any records already entered transactions or obligations?
- Is an explicit confirmation or separate business workflow needed?
- Can impact be previewed before execution?

### 11.3. Controlled deletion

For critical business domains, the application can execute a controlled deletion workflow:

1. Verify status and actor permissions;
2. Inspect dependent entities;
3. Determine which data is retained, deleted, anonymized, or transitioned in status;
4. Record the reason and actor if required;
5. Execute changes within a transaction or consistent workflow;
6. Verify references and outcome;
7. Log the completion event.

Not every operation requires a lengthy workflow. Yet for transactions, shared profiles, or historical data, impact must be clearly defined before permitting deletion.

## 12. Ownership in document, graph, and analytical data

Ownership and lifecycle dependency remain crucial outside the relational model.

### 12.1. Document model

A document can contain child components managed together with the aggregate. For example, an `ORDER` document containing an `ORDER_LINE` array.

If line items only have meaning within the order and are always read/updated with it, embedding lines can be appropriate. When the `ORDER` document is deleted, embedded elements vanish with it.

However, if line items must be referenced independently across multiple shipments, histories, or external systems, consider independent identifiers or referencing structures. Embedding alone does not resolve all lifecycle rules.

### 12.2. Graph model

In a graph, deleting a node does not necessarily mean deleting every neighboring node. Distinguish:

- Deleting an edge: ends a relationship;
- Deleting a node: removes an object;
- Deleting dependent nodes: removes objects meaningful only beneath an owner node;
- Keeping a node and marking status: preserves history while inactive.

For example, a `CUSTOMER` can link to an `ORDER` via a `PLACED` edge. Deleting the edge should not automatically delete `ORDER` if orders have independent lifecycles. Conversely, a `CART_ITEM` node may depend on `CART` and be deleted alongside valid cart deletion.

### 12.3. Analytical model

Analytical data typically must preserve events and historical snapshots. Deleting a current dimension entity must never erase previously recorded historical facts.

For instance, a discontinued product still appears in past sales facts. Use inactive statuses, versioned dimensions, or surrogate keys to maintain historical joins.

If a dimension is deleted or altered, decide which version historical facts reference, whether to use an "unknown" member, or whether to preserve descriptive snapshots at event time. Never cascade-delete facts simply because a descriptive entity is no longer active.

## 13. Process for defining lifecycle and deletion policies

Use the following workflow when analyzing a relationship.

### Step 1: Identify both ends and relationship semantics

Clearly record the subject entity, referenced entity, relationship name, and roles at both ends.

### Step 2: Specify the grain of each entity

Define what one record represents. If the child has no meaning outside the owner, document the unit of dependency.

### Step 3: Check ownership and sharing

Ask whether the child can belong to multiple owners, transfer between owners, be referenced by other objects, and who governs its lifecycle.

### Step 4: Map out lifecycles

List states and events for both owner and child. Define creation, activation, completion, cancellation, archiving, and restoration.

### Step 5: Define the meaning of each deletion type

Distinguish physical delete, soft delete, business cancellation, deactivation, archiving, and anonymization. Do not lump them into a single action.

### Step 6: Choose referential behavior

Select RESTRICT, NO ACTION, CASCADE, SET NULL, or an appropriate business workflow. Check multi-tier impacts.

### Step 7: Audit historical data and shared records

Ensure transactions, events, facts, and widely referenced objects cannot be deleted unintentionally.

### Step 8: Confirm with business stakeholders

Present concrete scenarios: "If a customer with shipped orders is deleted, what must the system do with orders, payments, invoices, and addresses?" Document the decision and approver.

~~~mermaid
flowchart TD
    A["Relationship between two entities"] --> B["Identify roles and grain"]
    B --> C["Check ownership and lifecycle dependency"]
    C --> D{"Does child have independent meaning?"}
    D -->|No| E["Define end-with-owner policy"]
    D -->|Yes| F["Define retention or detachment policy"]
    E --> G["Distinguish physical delete, cancel, and archive"]
    F --> G
    G --> H["Choose delete behavior and constraints"]
    H --> I["Check cascades, orphans, and history"]
    I --> J["Confirm with business"]
~~~

## 14. Questions to document in the data dictionary

For each relationship involving ownership or dependency, capture the following details:

| Field | Information to record |
|---|---|
| Owner concept | Entity governing the lifecycle |
| Dependent concept | Entity that may be dependent |
| Relationship name | Business relationship name |
| Ownership type | Lifecycle ownership, reference, or association |
| Dependency | Identity dependency, lifecycle dependency, or none |
| Transferability | Whether ownership can be transferred |
| Parent deletion policy | How child is handled when owner is deleted |
| Child deletion policy | Whether owner is affected when child is deleted |
| Historical retention | Whether history or snapshots must be retained |
| Business condition | Status or permission conditions allowing deletion |
| Confirmation owner | Person/team confirming the rule |

Brief specification example:

~~~yaml
relationship:
  name: ORDER_OWNS_ORDER_LINE
  owner_concept: ORDER
  dependent_concept: ORDER_LINE
  ownership_type: lifecycle
  dependency:
    identifying: true
    lifecycle: true
  transferability: false
  parent_deletion_policy:
    draft: cascade
    confirmed_or_later: prohibit_physical_delete
  child_deletion_policy:
    allowed_when: order_status_is_draft
  historical_retention:
    required_after_confirmation: true
  confirmation_owner: Order Operations
~~~

This is an illustrative documentation structure, not a mandatory format. Values must be confirmed with the business and mapped to concrete constraints or enforcement workflows.

## 15. Common mistakes

1. **Treating every 1:N relationship as ownership:** a customer having many orders does not mean deleting the customer deletes orders.
2. **Treating a foreign key as proof of ownership:** a foreign key only expresses a reference, not the full lifecycle.
3. **Using CASCADE on every relationship:** risks deleting historical or shared data.
4. **Failing to distinguish cancellation from deletion:** order cancellation is a business event that usually requires retaining history.
5. **Assuming an entity with its own ID is independent:** a cart item with its own ID can still depend on the cart.
6. **Confusing identity dependency with lifecycle dependency:** a composite key does not automatically dictate deletion policy.
7. **Using SET NULL on mandatory relationships:** destroys links required by the business.
8. **Keeping meaningless orphan records:** child data lacking an owner or explanation.
9. **Deleting shared entities:** products, warehouses, or payment methods may be referenced by many transactions.
10. **Failing to check multi-tier cascades:** one deletion can propagate across many tables.
11. **Using soft delete without filtering queries:** deleted records still show up on screens or reports.
12. **Inconsistent anonymization:** identifying information remains in snapshots, logs, or related tables.
13. **Failing to track ownership transfer history:** overwriting an owner key erases handover records.
14. **Skipping status-specific policies:** deleting a draft order and deleting a shipped order may require different behaviors.

## 16. Checklist before finalizing ownership and deletion policies

- [ ] Owner, child, and referenced entities are clearly identified.
- [ ] Cardinality is distinguished from lifecycle ownership.
- [ ] Granularity and identity of child entities are clear.
- [ ] Identity dependency and lifecycle dependency are identified.
- [ ] Whether children can be shared or transferred to another owner is confirmed.
- [ ] Lifecycles and terminal states on both sides are documented.
- [ ] Physical delete, soft delete, cancellation, deactivation, archiving, and anonymization are distinguished.
- [ ] RESTRICT, NO ACTION, CASCADE, SET NULL, or SET DEFAULT behaviors have clear business justifications.
- [ ] All multi-tier cascade impacts have been audited.
- [ ] Transactions, invoices, payments, and historical events are retained as required.
- [ ] Handling of orphan data and external system references is defined.
- [ ] Soft delete includes rules for querying, uniqueness, and restoration.
- [ ] Status-dependent decisions are explicitly documented.
- [ ] Business owners have confirmed the policies.

## 17. Practice exercise

A sales system has the following rules:

- A shopping cart has many cart items.
- Cart items have meaning only within one cart.
- When a customer checks out, the system creates an order and order lines.
- An order can have many payment attempts.
- An order can have many shipments and shipment events.
- A product can be discontinued, yet past orders must still display it.
- A customer can request account deactivation.
- Shipped orders must be retained for historical lookup.

Propose lifecycle and deletion policies for the following relationships:

1. `CART → CART_ITEM`;
2. `ORDER → ORDER_LINE`;
3. `ORDER → PAYMENT_ATTEMPT`;
4. `ORDER → SHIPMENT`;
5. `SHIPMENT → SHIPMENT_EVENT`;
6. `PRODUCT_VARIANT → ORDER_LINE`;
7. `CUSTOMER → ORDER`;
8. `CUSTOMER → CUSTOMER_PROFILE`.

For each relationship, state:

- Is it a lifecycle ownership relationship?
- Can the child entity exist independently?
- What is the appropriate deletion or termination behavior?
- What historical data must be retained?
- Which constraints can be used, and which rules must be handled in the business layer?

**Suggested answers:**

| Relationship | Lifecycle assessment | Reference policy |
|---|---|---|
| `CART → CART_ITEM` | Cart items depend on the cart | CASCADE can apply when deleting draft carts |
| `ORDER → ORDER_LINE` | Lines depend on the order | CASCADE only for draft orders; confirmed orders require cancellation or history retention |
| `ORDER → PAYMENT_ATTEMPT` | Attempts are transaction processing history | Usually block deleting orders with attempts; retain records for traceability |
| `ORDER → SHIPMENT` | Shipments have independent operational ID and history | Retain order and shipments; handle cancellation or completion by status |
| `SHIPMENT → SHIPMENT_EVENT` | Events depend contextually on the shipment | Retain alongside event history; delete only when shipment has no auditable events yet |
| `PRODUCT_VARIANT → ORDER_LINE` | Variant is a referenced entity | Block hard deletion when historical lines exist; transition to inactive |
| `CUSTOMER → ORDER` | Orders have independent transactional lifecycles | Retain orders; deactivate or anonymize profile per policy |
| `CUSTOMER → CUSTOMER_PROFILE` | Profile may depend on the account | Can delete alongside if profile holds only personal preferences and requires no history retention |

These answers are starting options. For example, `PAYMENT_ATTEMPT` may contain sensitive data governed by specific policies; `CUSTOMER_PROFILE` may contain auditable data that must be kept. Confirm concrete data scope before deciding.

**Target outcome:** the model must explain why some child entities are deleted with the owner, some are retained, some links are merely detached, and some objects only transition states. Every behavior must reflect the business lifecycle, prevent orphan records, and avoid accidentally deleting critical transactions or history.
