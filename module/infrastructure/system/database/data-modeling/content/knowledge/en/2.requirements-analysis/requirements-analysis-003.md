# Identifying Terms, Synonyms, and Homonyms (Same Name, Different Meanings)

In the **DATABASE_DATA_MODELING** module, the goal is to translate business requirements into a data model with clear entities, relationships, attributes, constraints, and identifiers, before choosing a relational, document, graph, or analytical representation. In the **Requirements Analysis** chapter, the very first task is to accurately understand the words used by users and business documents. If a concept has multiple names or a single name is used for multiple concepts, the data model can easily end up with duplicate entities, mismerged objects, or incorrect constraints.

This lesson guides you on how to identify terms, determine synonyms, detect polysemous (multi-meaning) names, and build a business glossary as the basis for modeling decisions.

**After this lesson, you will be able to:**

- Distinguish a term (label) from the business concept it represents.
- Determine whether two names truly refer to the same concept within a specific scope.
- Detect when a single name is being used for multiple different concepts.
- Record canonical names, aliases, definitions, scope, and items needing clarification.
- Turn terminology analysis results into traceable inputs for the data model.

## 1. Why Analyze Terminology Before Modeling?

Business requirements are typically collected from many sources: user interviews, operating procedures, forms, reports, application screens, APIs, and existing documentation. These sources may refer to the same object by different names. Conversely, multiple departments may use the exact same word while talking about different objects or states.

Example in a sales system:

- Sales staff say **order** (*đơn hàng*), while warehouse staff say **dispatch order** (*đơn xuất*).
- Users call a person **customer**, whereas delivery staff call the package receiver **recipient**.
- A screen displays only the label **status**, even though the system tracks order status, payment status, and delivery status.
- Documentation writes **product code**, whereas warehouse staff use that term to refer to SKU or barcode.

If relying solely on wording, a designer might create two tables for the same concept, or merge two concepts with different lifecycles and rules into a single table or attribute. Consequences can surface across multiple layers: wrong keys and relationships, mixed data, hard-to-control states, inaccurate report counts, or unverifiable business rules.

Two layers must be distinguished:

- **Term:** A word or phrase appearing in requirements, e.g., "customer," "order code," "status."
- **Concept:** The specific business meaning represented by a term within a scope, including its definition, roles, rules, lifecycle, and relationships to other concepts.

A term does not automatically map to a table. Likewise, one concept can have multiple terms. Therefore, identify the concept first, then decide whether it should be modeled as an entity, attribute, relationship, event, or another structure.

## 2. Distinguishing Synonyms and Polysemous Names

### 2.1. Synonyms or Aliases

Two words are considered synonyms within a scope when they refer to the same concept and can be substituted for each other in related requirements without altering business rules.

For example, in one enterprise, "sales order" and "purchase order" (from the buyer perspective) might be two ways of referring to the same order created by a customer. If both share one identifier, the same lifecycle, the same owning subject, and the same processing rules, they can be recorded as one canonical name and an alias.

However, similarity in everyday speech is not enough to conclude equivalence. "Shopping cart" and "order" both relate to buying products, yet usually differ: a cart is a set of selections not yet confirmed, whereas an order is a purchase request created under a defined workflow. These two concepts must not be merged simply because users occasionally call both "order."

**Substitution test:** Replace term A with term B in key requirement statements. If the substitution changes the target object, condition, timing, responsible party, or business outcome, the two terms cannot yet be treated as full synonyms.

### 2.2. Same Name, Different Meanings

One term can be used for multiple concepts. In linguistics, one distinguishes homonymy from polysemy (one word with related senses). In requirements analysis, what matters more is recognizing that **the same word string may be referencing different business objects**.

Examples:

- **Status:** Might mean order processing status, payment status, or delivery status.
- **Code:** Might mean internal key, customer-facing order number, SKU, or barcode.
- **Address:** Might mean the customer's default address, billing address, or shipping address for a specific order.
- **Account:** Might mean login account, accounts receivable/ledger account, or payment account.

Do not create a generic attribute named **status** or **code** and assume every department means the same thing. Use complete, scoped names matching the concept, such as **order_status**, **payment_status**, **shipment_status**; or **order_number**, **sku**, **barcode**.

### 2.3. Near-Synonyms Are Not Necessarily Synonyms

Some terms have close meanings yet represent different roles, stages, or scopes. They must be documented separately until the business confirms they can be unified.

| Terms | Why They Cannot Be Merged Immediately | Question to Verify |
|---|---|---|
| Customer / buyer | Customer may be an account holder or organization; buyer may refer to the role executing the transaction | Is the buyer always a registered customer? |
| Buyer / recipient | Someone placing an order may ship goods to someone else | Can these two roles belong to two different people? |
| Shopping cart / order | Different confirmation timing and lifecycles | When does a cart become an order? |
| Product / product variant | One product can have multiple sellable sizes, colors, or editions | At which level are price and inventory managed? |
| Default address / shipping address | A profile address may be selected or overridden at checkout | Must the shipping address be saved per order? |

The principle is neither to merge solely because words sound similar, nor to split solely because of different wording. Decisions must be grounded in definitions and business rules.

## 3. Process for Analyzing and Standardizing Terminology

You can follow these steps:

### Step 1: Collect Terms Together with Usage Context

Record words or phrases verbatim from the requirements. Each occurrence should include source and context, for example:

- The requirement statement or requirement ID containing the term.
- The department or role using the term.
- The related workflow, screen, report, or API.
- Actions occurring before and after the term is mentioned.

Do not rush to replace all variants with a single canonical name during collection. Preserving the original phrasing makes it easy to trace back to the source when debates arise.

### Step 2: Identify the Object Referenced by the Term

For each occurrence, ask:

- Is this a person, organization, physical item, transaction, event, role, state, attribute, or metric?
- Does the object have its own identifier?
- Who creates, uses, updates, or owns it?
- In which workflow does it exist, and what is its lifecycle?
- What rules or constraints apply to it?

The same word can carry different meanings in two workflows. For instance, "account" in authentication may mean login credentials, whereas "account" in billing may be an accounting entity. Capture each context accurately instead of assuming they are one.

### Step 3: Test Whether Terms Are Synonyms

Compare two terms against these criteria:

1. **Same object:** Do they refer to the exact same person, item, transaction, or concept?
2. **Same identifier:** If the object has an identifier, do both terms share the same identifier?
3. **Same lifecycle:** Are they created, modified, and terminated at the exact same points?
4. **Same rules:** Are conditions, permissions, constraints, and actions identical?
5. **Interchangeable:** Does swapping one term for the other across business scenarios preserve meaning?

If these criteria do not align, record them as two separate concepts or flag them as needing more information. Never force them into aliases just to keep the glossary shorter.

### Step 4: Detect and Split Meanings of the Same Name

When a word appears across multiple departments or workflows, compare its referenced object, owner, lifecycle, and applicable rules. Use context-qualified names to make the difference explicit.

For example, instead of recording a generic "status," define separately:

- Order status: Which stage is the order in within the sales workflow?
- Payment status: How far has the payment been initiated, confirmed, or completed?
- Delivery status: At which stage is package preparation and transit?

An order may already be confirmed while payment is still pending; a package may also not yet be handed over to the carrier. These statuses relate to each other, yet they are not a single concept.

### Step 5: Choose a Canonical Name and Document Scope

A canonical name should be:

- Clear to business stakeholders and consistent across documentation.
- Expressive of the true concept, avoiding dependence on UI button text or screen labels.
- Specific enough to distinguish from near-synonyms.
- Stable over time; if abbreviations are used, explain them clearly.
- Scoped appropriately, especially when a term is used across multiple departments.

Other names are retained as aliases or source-specific terms. The canonical name keeps documentation consistent; aliases ensure readers can still find familiar terms.

### Step 6: Confirm with Business Owners

Present concrete scenarios rather than merely asking "do these two words mean the same thing?". Ask who performs the action, which object is affected, which rules apply, and what happens in exception cases. Confirm across all relevant departments if the same term appears in multiple workflows.

### Step 7: Link Terminology to the Data Model

Once meanings are clear, note whether the concept will be evaluated as an entity, attribute, relationship, role, event, or metric. This serves as a prompt for further analysis during modeling, not an automated rule to create a table for every row in the glossary.

Overall workflow:

~~~mermaid
flowchart TD
    A["Collect terms from requirements"] --> B["Record source and context"]
    B --> C["Identify referenced concept"]
    C --> D{"Do terms share the same meaning?"}
    D -->|Yes| E["Choose canonical name and store aliases"]
    D -->|No or unclear| F["Split meanings or log verification questions"]
    E --> G["Confirm with business"]
    F --> G
    G --> H["Build traceable glossary"]
    H --> I["Link to data model"]
~~~

## 4. Practical Example: Terminology Analysis in a Sales System

Suppose the analysis team receives the following requirement:

> Customers select products and create an order. The order is delivered to the customer's address. After payment, staff update the status. Each product and order has its own code.

This description looks straightforward, yet still contains many ambiguities for data design.

| Word or Phrase | Possible Interpretations | Questions to Ask or Verify |
|---|---|---|
| Customer | Buyer, account owner, payer, or recipient | Can the buyer and recipient be different people? Are there orders placed on behalf of someone else or for an organization? |
| Customer address | Default address, billing address, shipping address | Which address is used for the order? If the customer profile changes, does an old order's address change too? |
| Status | Order status, payment status, or delivery status | Who updates each status? Which events trigger status transitions? |
| Code | Internal key, displayed order number, SKU, or barcode | Who uses the code? Within what scope is it unique? Can it change? |
| Product | Catalog item or sellable variant | Are inventory and price managed at the general product level or per variant? |

### 4.1. Separating Customer Roles

Never assume the order placer, payer, and recipient are always the same person. In gift orders, the buyer and recipient differ. In corporate purchasing, the requester, approver, and paying legal entity may be separate parties.

Before modeling, clarify:

- Is a customer an individual, an organization, or both?
- Is the buyer required to have an account?
- Does the recipient need to be managed as an independent customer?
- Does the system need to store a separate payer or approver?

If the same person can play multiple roles, the model can represent one party with different roles. Only create separate entities when independent identities, lifecycles, or rules are confirmed by the business.

### 4.2. Distinguishing Types of Addresses

"Customer address" is insufficiently specific. An address on a customer profile can be edited; an order's shipping address is information tied to a specific transaction. A billing address may serve a different purpose and follow different validation rules.

A critical question is: when a customer changes their default address, should already-placed orders still be delivered to the old address? If the business requires preserving the address as of order placement time, shipping details must be stored per order or via an appropriate historical mechanism. This decision cannot be deduced from the phrase "customer address" alone.

### 4.3. Separating Types of Status

A single attribute named **status** cannot express three distinct lifecycles. Valid states and transition events must be confirmed separately for each workflow.

| Canonical Concept | Business Question | Example Name in Model |
|---|---|---|
| Order status | Which stage is the order at in the sales workflow? | **order_status** |
| Payment status | How far has the payment transaction been processed? | **payment_status** |
| Delivery status | What stage is package preparation and shipping at? | **shipment_status** |

Specific values such as "pending confirmation," "confirmed," "paid," or "delivered" should only enter the model after confirming state transition rules. Not every status applies to every workflow.

### 4.4. Distinguishing Types of Codes

"Code" is far too generic. For example:

- **order_id:** Internal identifier of an order, used for linking data.
- **order_number:** Human-readable order number for customer and staff lookup.
- **sku:** Identifier for a unit of merchandise that can be sold or tracked in inventory.
- **barcode:** Encoded identifier for scanners, which may link to an SKU or another object per system rules.

These codes may appear together on one screen, yet have different purposes, uniqueness scopes, and lifecycles. Never use a generic **code** column without proving that those codes share the same meaning and rules.

### 4.5. Condensed Glossary After Verification

The table below illustrates how to document results. Aliases and definitions must be confirmed with the business before being treated as official.

| Concept ID | Canonical Name | Acceptable Aliases | Not the Same As |
|---|---|---|---|
| **CUSTOMER** | Customer | Buyer, if referring to the purchasing party within sales scope | Recipient, contact person |
| **ORDER** | Order | Purchase order (customer-side), if sharing the same transaction lifecycle | Shopping cart, delivery slip |
| **ORDER_STATUS** | Order status | Order state | Payment status, delivery status |
| **PAYMENT_STATUS** | Payment status | Transaction status, if within the same payment workflow | Order status |
| **SHIPPING_ADDRESS** | Shipping address | Delivery address | Billing address, default address |
| **SKU** | SKU code | Item code, if the business uses this exact meaning | Order code, barcode |

## 5. Building a Business Glossary

A business glossary stores agreed canonical names and definitions. It serves as a shared reference among analysts, business stakeholders, developers, testers, and data stewards.

A glossary entry should contain:

| Field | Purpose |
|---|---|
| **concept_id** | Stable identifier for the concept, independent of spelling variations |
| **canonical_name** | Standard name used across documentation and models |
| **definition** | Concise, verifiable business definition |
| **scope** | Applicable department, workflow, or context |
| **aliases** | Synonyms, legacy names, UI labels, or local terms |
| **not_same_as** | Easily confused concepts that must be kept distinct |
| **source_requirements** | Supporting requirements or documents |
| **owner** | Person or department responsible for confirming meaning |
| **status** | Confirmation status or open questions |

Example structure usable in project documentation:

~~~yaml
terms:
  - concept_id: CUSTOMER
    canonical_name: Customer
    scope: Sales
    definition: Party that purchases goods or maintains a commercial relationship with the enterprise.
    aliases:
      - Buyer
    not_same_as:
      - Recipient
      - Contact person
    source_requirements:
      - REQ-SALES-001
    owner: Sales department
    status: confirmed

  - concept_id: ORDER_STATUS
    canonical_name: Order status
    scope: Order lifecycle
    definition: Value indicating the processing stage of an order.
    aliases:
      - Order state
    not_same_as:
      - Payment status
      - Delivery status
    source_requirements:
      - REQ-ORDER-004
    owner: Order operations team
    status: confirmed

  - concept_id: SHIPPING_ADDRESS
    canonical_name: Shipping address
    scope: Order
    definition: Location selected to deliver a specific order.
    aliases:
      - Delivery address
    not_same_as:
      - Billing address
      - Customer default address
    source_requirements:
      - REQ-DELIVERY-002
    owner: Fulfillment & delivery team
    status: unresolved
    open_questions:
      - Must the address at order placement time be preserved historically?
~~~

In this example, **CUSTOMER** and **ORDER_STATUS** are confirmed, whereas **SHIPPING_ADDRESS** still has an open question. The **unresolved** status means there is insufficient evidence to lock down the modeling decision. Do not fill in a technical answer yourself in place of business confirmation.

## 6. From Business Glossary to Data Model

The glossary grounds modeling decisions in agreed meanings. Important principles include:

- **Multiple aliases, one concept:** Use one concept identifier and one consistent representation. Do not create multiple tables or columns merely because documents use different words.
- **One name, multiple concepts:** Split names by context and rules. For instance, order, payment, and delivery statuses must be described separately.
- **Multiple roles, one party:** If the same person can be both buyer and recipient, define role relationships before deciding whether separate entities are required.
- **A term denoting a role in one workflow:** "Approver" may be a role of an employee, not necessarily a new entity type.
- **Purpose-specific identifiers:** Distinguish technical keys, customer-facing business codes, and operational codes.
- **Do not choose storage structures from names alone:** Determine meaning and rules first, then select the representation.

The same glossary can support multiple modeling paradigms:

| Modeling Approach | How Terminology Analysis Results Are Used |
|---|---|
| Relational | Determine table names, columns, foreign keys, and constraints; e.g., separating order, payment, and delivery data when they have distinct lifecycles |
| Document | Keep semantically clear field names within documents; e.g., distinguishing **orderStatus** and **paymentStatus**, even if both sections reside in one document |
| Graph | Identify accurate node labels and relationship types; e.g., **Customer** — **PLACED** → **Order**, while a recipient may be modeled via another role or relationship |
| Analytical | Consistently define dimensions and metrics; e.g., never mixing payment status with delivery status when analyzing operational performance |

One concept may be represented differently depending on system goals and constraints. The glossary keeps business meaning consistent even when physical structures change.

## 7. Clarifying Terms Across Different Contexts

An enterprise does not always have a single system-wide definition for a word. For example, "customer" in sales may be the buyer; in accounting, the customer concept may tie to an accounts receivable profile; in customer care, it may tie to a contact person and support history.

In such cases, explicitly record the **business scope** (bounded context) for each definition. Two concepts in two contexts may relate or share a party identifier, yet you must not assume they share the same attributes and rules. When data must be exchanged across contexts, document the mapping and each side's responsibilities.

A helpful checklist of questions:

- In which workflow is this word used?
- Who has authority to create or modify the data?
- Does the definition change when moving to another department?
- Do both systems share the same identification and update rules?
- If two sides disagree, which side is the authoritative source for each attribute?

When terminology changes over time, retain aliases or former names along with effective dates and sources. Never silently alter the definition of a term currently used in reports, APIs, or historical data.

## 8. Common Mistakes

1. **Merging words because they sound alike:** "Customer" and "recipient" can be two distinct roles. Verify real-world scenarios before merging.
2. **Splitting objects merely because of multiple names:** "Purchase order" and "order" might be aliases within one workflow. Check identifiers and lifecycles before creating two entities.
3. **Using generic names for multiple meanings:** Fields like **status**, **code**, **type** are confusing without context and definitions.
4. **Treating UI labels as definitions:** Display labels are often abbreviated to save space and do not always reflect full data semantics.
5. **Ignoring scope:** One word can mean different things across sales, accounting, and warehousing.
6. **Omitting sources and confirmers:** When disputes arise, the project team will not know where a definition came from or who has decision authority.
7. **Solving business questions with technical choices:** If it is unclear whether shipping addresses require history, you cannot decide solely by picking document vs. relational storage.
8. **Not updating aliases:** Legacy names in forms, APIs, or reports may still persist; without recording them, readers will struggle to cross-reference.

## 9. Pre-Modeling Checklist

- [ ] Key terms have documented sources and usage contexts.
- [ ] Each concept has a definition clear enough for others to verify.
- [ ] Aliases have been tested against object, lifecycle, and business rules.
- [ ] Polysemous terms have been split by scope or logged as questions to verify.
- [ ] Canonical names are specific enough to avoid confusion with near-synonyms.
- [ ] Roles such as buyer, recipient, payer, and approver have been distinguished.
- [ ] Identifiers and statuses have distinct purposes, scopes, and rules.
- [ ] Every critical entry has an accountable person or department to confirm it.
- [ ] Unresolved questions are explicitly logged rather than turned into silent model assumptions.
- [ ] Terms are linked to source requirements for traceability when the model evolves.

## 10. Practice Exercise

Another requirement states:

> Buyers can update their default address in their profile. When creating an order, the buyer selects a shipping address. Accounting tracks payment status, while the warehouse tracks delivery status. Customers can look up orders by order code.

Determine:

1. Within what scope can "buyer" and "customer" be aliases? What needs to be verified?
2. Are "default address" and "shipping address" the same concept?
3. Can "payment status" and "delivery status" share a single business attribute?
4. How should "order code" be distinguished from the order's internal key?

**Analysis hints:**

- "Buyer" can be an alias for "customer" in the ordering workflow if both refer to the same party. Verify cases such as buying on someone else's behalf, corporate purchasing, or ordering without an account.
- "Default address" belongs to the customer profile; "shipping address" is tied to an order's selection. They may contain the same address details, yet differ in purpose and point-in-time applicability.
- Payment status and delivery status belong to two workflows tracked by two departments, so they require separate definitions and state transition rules.
- The order code used by users for lookup may be a business order number; the internal key is used to link data. Both values may identify the same order, yet have different purposes, formats, and rules.

The expected outcome of the exercise is a glossary containing canonical names, aliases, scopes, definitions, easily confused concepts, and open questions. Only once meanings are confirmed does the team have solid grounds to decide entities, attributes, relationships, keys, and constraints in the data model.
