# TransientPropertyValueException and Unsaved References

**Module:** Spring Data JPA  
**Knowledge group:** Troubleshooting

## 1. Objectives

After this lesson, you will be able to:

- Explain why Hibernate throws TransientPropertyValueException when an entity references an unsaved related object.
- Distinguish transient, managed, and detached entities.
- Identify the offending association and property from the exception message.
- Choose the proper fix: load an existing entity, save the new entity first, or configure cascade according to the aggregate lifecycle.
- Understand the owning side of a bidirectional relationship and keep both sides synchronized.
- Distinguish CascadeType.PERSIST, MERGE, and ALL.
- Know when the error occurs during persist, flush, or commit.
- Write integration tests to verify that relationships are saved properly and transactions roll back on invalid data.

## 2. What is TransientPropertyValueException?

TransientPropertyValueException is a Hibernate exception under the TransientObjectException hierarchy. It typically occurs when an entity about to be saved or flushed has an association pointing to a transient object that is neither managed nor persisted in the database, while the persist operation lacks an appropriate cascade to save that object.

For example: the application creates a new PurchaseOrder and assigns it a Customer freshly instantiated with the `new` operator. If PurchaseOrder does not cascade PERSIST to Customer, Hibernate cannot write the customer_id foreign key pointing to a non-existent Customer record.

The message usually indicates the entity owning the association property, the property name, and the transient entity type. Read the full message and stack trace to pinpoint the exact association instead of looking only at the repository.save() line where the exception was observed.

This error reflects an issue in the entity lifecycle or how the object graph was constructed. It does not simply mean an ID is missing or that you should call save() one more time on every Repository.

## 3. Understanding Entity Lifecycle in JPA

An entity is typically in one of the following states:

| State | Meaning | Example |
|---|---|---|
| Transient | New Java object, not managed by a persistence context and no persisted record yet | new Customer() |
| Managed | Managed by an EntityManager; changes can be written to DB via dirty checking | Entity returned by findById within a transaction |
| Detached | Previously managed but no longer belongs to an active persistence context | Entity obtained from a previous request or a closed EntityManager |
| Removed | Marked for deletion in the persistence context | entityManager.remove(customer) |

Important point: a Java object having an ID does not automatically become managed. Assigning an ID to a new object neither proves that the corresponding record exists nor puts the object into the persistence context.

Example:

~~~java
Customer customer = new Customer();
customer.setName("An");

PurchaseOrder order = new PurchaseOrder();
order.setCustomer(customer);
~~~

Both objects are new. If you save order without an appropriate PERSIST cascade, Hibernate detects that order.customer points to a transient Customer and may throw TransientPropertyValueException on flush.

Detached differs from transient. A detached entity was saved previously but is no longer managed. Errors involving detached entities can take a different form, such as Detached entity passed to persist. Do not handle every association error by mechanically adding cascade PERSIST.

## 4. Example Relationship Causing the Error

Suppose an order always belongs to a customer. Customer is independent data that can be referenced by many orders.

~~~java
@Entity
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }
}
~~~

Order entity:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer) {
        this.customer = customer;
    }

    public Long getId() {
        return id;
    }
}
~~~

`@ManyToOne` does not cascade any operations by default. The following snippet can fail:

~~~java
@Transactional
public Long createOrder() {
    Customer customer = new Customer("An");

    PurchaseOrder order = new PurchaseOrder(customer);

    return orderRepository.save(order).getId();
}
~~~

Spring Data JPA calls persist or merge depending on whether the entity is considered new or existing. If the actual operation is persist and there is no PERSIST cascade to customer, Hibernate cannot save this object graph. The error can appear immediately during persist or later during flush/commit.

Do not fix this by assigning a fake ID to Customer. A fake ID does not create a record in the database and can lead to foreign key errors or other entity state errors.

## 5. Approach 1: Reference an Existing Entity Using a Managed Entity

If Customer already exists in the database, fetch that entity within the transaction and assign it to PurchaseOrder.

~~~java
@Service
@RequiredArgsConstructor
public class OrderService {

    private final CustomerRepository customerRepository;
    private final PurchaseOrderRepository orderRepository;

    @Transactional
    public Long createOrder(Long customerId) {
        Customer customer = customerRepository.findById(customerId)
                .orElseThrow(() ->
                        new EntityNotFoundException("Customer not found"));

        PurchaseOrder order = new PurchaseOrder(customer);

        return orderRepository.save(order).getId();
    }
}
~~~

findById returns a Customer managed in the current transaction's persistence context. When saving PurchaseOrder, Hibernate can use Customer's primary key to write customer_id.

This is usually the clearest approach when business logic needs to confirm the customer exists and may need to read additional customer details.

### 5.1. Using getReferenceById When Only a Reference Is Needed

If you only need to set the foreign key and do not need to read Customer properties, you can use:

~~~java
@Transactional
public Long createOrder(Long customerId) {
    Customer customer = customerRepository.getReferenceById(customerId);

    PurchaseOrder order = new PurchaseOrder(customer);

    return orderRepository.save(order).getId();
}
~~~

getReferenceById may return a proxy without immediately querying full data. When the entity is accessed, the provider may load the data. If the ID does not exist, the error may only surface when the proxy is accessed or when the database checks the foreign key.

If the API needs to return an explicit 404 when the customer does not exist, findById is usually easier to control. Do not use getReferenceById as proof that the record exists.

## 6. Approach 2: Save the Related Entity Before Saving the Referencing Entity

If Customer is genuinely new data and does not belong to a lifecycle cascaded from PurchaseOrder, save Customer first:

~~~java
@Transactional
public Long createOrder(String customerName) {
    Customer customer = customerRepository.save(
            new Customer(customerName));

    PurchaseOrder order = new PurchaseOrder(customer);

    return orderRepository.save(order).getId();
}
~~~

After saving Customer succeeds, the return value is the persisted entity. Assign the returned entity to PurchaseOrder and then save the order.

Both operations run in the same Service transaction. If saving the order fails and an exception rolls back the transaction, the Customer creation is also rolled back within the same transaction.

Calling saveAndFlush() after Customer is not strictly required. Hibernate can order SQL operations appropriately at flush time. Only flush early when there is a specific reason, such as wanting constraint errors to appear at a clear point or needing generated IDs/SQL before executing the next step.

## 7. Approach 3: Cascade PERSIST for Relationships Within the Same Aggregate

Cascade is appropriate when the root entity owns the lifecycle of child entities. For example, OrderLine is created and deleted together with PurchaseOrder and has no independent business lifecycle.

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private Customer customer;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer) {
        this.customer = customer;
    }

    public void addLine(OrderLine line) {
        lines.add(line);
        line.setOrder(this);
    }

    public Long getId() {
        return id;
    }
}
~~~

OrderLine is the child entity:

~~~java
@Entity
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    private int quantity;

    protected OrderLine() {
    }

    public OrderLine(Product product, int quantity) {
        this.product = product;
        this.quantity = quantity;
    }

    void setOrder(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

Service creating the aggregate:

~~~java
@Transactional
public Long createOrder(Long customerId, Long productId, int quantity) {
    Customer customer = customerRepository.findById(customerId)
            .orElseThrow(() ->
                    new EntityNotFoundException("Customer not found"));

    Product product = productRepository.findById(productId)
            .orElseThrow(() ->
                    new EntityNotFoundException("Product not found"));

    PurchaseOrder order = new PurchaseOrder(customer);
    order.addLine(new OrderLine(product, quantity));

    return orderRepository.save(order).getId();
}
~~~

When persisting PurchaseOrder, cascade PERSIST on order.lines tells Hibernate to persist the new OrderLine instances. Customer and Product are existing, managed entities, so there is no need to cascade PERSIST from OrderLine to those two references.

### 7.1. Why Is Cascade Placed on PurchaseOrder.lines?

PurchaseOrder is the aggregate root managing OrderLine's lifecycle. When creating an order, new order lines are created along with the order. When removing a line from the collection, orphanRemoval = true indicates that the line no longer belongs to the aggregate and can be deleted upon flush.

Cascade PERSIST on the collection propagates persist operations from the root down to child entities. Placing cascade must follow business lifecycle ownership, not merely a desire to silence an exception.

## 8. Do Not Indiscriminately Cascade PERSIST on Shared Relationships

Customer can typically be referenced by many PurchaseOrder instances. Customer is not a child entity owned by a specific order.

Do not declare by default:

~~~java
@ManyToOne(cascade = CascadeType.ALL)
private Customer customer;
~~~

Cascade ALL includes PERSIST, MERGE, REMOVE, REFRESH, and DETACH. When deleting a PurchaseOrder, cascade REMOVE can propagate to Customer and delete shared data or cause foreign key violations.

For relationships where many orders reference a customer, usually you only assign a managed/reference Customer to PurchaseOrder and do not cascade delete operations.

Practical rules:

- Cascade PERSIST when the root entity creates and manages the lifecycle of new child entities.
- Cascade MERGE when you want merge on the root to propagate to related entities in accordance with the model.
- Cascade REMOVE only when the related entity must truly be deleted together with the root.
- Cascade ALL only when the entire lifecycle of the related entity strictly depends on the root.

Never add cascade just to make an exception vanish. Examine who creates, who updates, and who is responsible for deleting the related data.

## 9. Distinguishing PERSIST and MERGE in Spring Data JPA

Repository.save(entity) does not always call the same JPA operation. Spring Data JPA checks whether the entity is considered new:

- New entities are usually persisted.
- Existing entities or entities detected as not new are usually merged.

Therefore, cascade must match the actual operation. CascadeType.MERGE does not replace CascadeType.PERSIST when a new entity is persisted. If a new root is persisted with a transient association, declaring only MERGE will not resolve that persist path.

An important point: EntityManager.merge returns a managed instance. The passed-in instance may remain detached. Thus, when calling save for detached entities or merge scenarios, continue working with the returned object:

~~~java
PurchaseOrder managedOrder = orderRepository.save(order);
~~~

Do not assume save always turns the original object itself into a managed instance.

If an entity uses assigned IDs or custom newness rules, check Spring Data's isNew mechanism, `@Version` fields, or `Persistable.isNew()`. Misidentifying newness can cause Spring to choose persist/merge unexpectedly.

## 10. Owning Side of a Bidirectional Relationship

JPA uses the owning side to determine which foreign key column is written. In the PurchaseOrder and OrderLine example:

- OrderLine.order is the owning side because it holds `@ManyToOne` and the order_id column.
- PurchaseOrder.lines is the inverse side because it uses mappedBy = "order".

If you only add an OrderLine to the PurchaseOrder.lines collection without setting OrderLine.order, the owning side remains unset. The database may not write the foreign key as intended.

The addLine helper updates both sides:

~~~java
public void addLine(OrderLine line) {
    lines.add(line);
    line.setOrder(this);
}
~~~

Similarly, when removing a line, provide a helper maintaining both the collection and the back reference:

~~~java
public void removeLine(OrderLine line) {
    lines.remove(line);
    line.setOrder(null);
}
~~~

With orphanRemoval = true, removing an entity from a managed collection can mark the child entity for deletion on flush. Ensure business logic permits this and do not reuse an orphaned child entity.

Failing to update the owning side often causes null foreign key errors or unexpected relationship data. This is distinct from TransientPropertyValueException, though both can appear together in an improperly constructed object graph.

## 11. Does the Error Appear at Persist, Flush, or Commit?

JPA can defer SQL until flush. Therefore, the line of code raising the error is not necessarily the line executing the INSERT.

A typical flow:

1. Service creates entities and sets associations.
2. Repository.save calls persist or merge.
3. Hibernate places the entity into the persistence context.
4. On flush, Hibernate validates associations and schedules SQL.
5. If a transient reference lacks cascade persist, Hibernate throws an exception.
6. The transaction fails and must roll back.

Flush can occur when calling saveAndFlush, EntityManager.flush, before a query under FlushMode AUTO, or at transaction commit.

To isolate the error during development, you can explicitly flush after building the aggregate:

~~~java
@Transactional
public Long createOrder(...) {
    PurchaseOrder order = buildOrder(...);

    PurchaseOrder saved = orderRepository.save(order);
    orderRepository.flush();

    return saved.getId();
}
~~~

This is a diagnostic technique or for cases needing SQL synchronization at a specific point. Flush is not commit. After flush, the transaction can still roll back and changes are not yet finalized.

Do not indiscriminately add flush after every Repository call, as this can reduce batching and increase database round-trips.

## 12. How to Read the Exception and Find the Failing Association

When encountering TransientPropertyValueException:

1. Read the full root cause in the stack trace; the outer wrapper may be a Spring-translated exception.
2. Find the entity name owning the association property.
3. Find the property name and transient entity type mentioned in the message.
4. Open the mapping for that association to inspect cascade, optional, JoinColumn, and mappedBy.
5. Inspect the object graph right before save/flush.
6. Determine whether the related entity should be an existing record, a new entity inside the aggregate, or a detached entity.
7. Choose the corresponding load/save/cascade approach and re-test.

For example, if the message points to PurchaseOrder.customer referencing an unsaved Customer, inspect where PurchaseOrder is built and how Customer is assigned. If it points to OrderLine.product, inspect whether loading an existing Product or creating a new Product matches business requirements.

Do not fix only the first visible association. An entity may have multiple relationships; after fixing the first error, flush may uncover another transient association.

## 13. Distinguishing Related Errors

| Error | Common cause | What to check |
|---|---|---|
| TransientPropertyValueException | Association points to a transient entity without cascade persist | Whether related entity is saved, whether cascade is right |
| Detached entity passed to persist | Persisting a detached entity that already has an identity | Whether mistakenly persisting an existing entity; whether managed reference or merge is needed |
| PropertyValueException | Required property is null or value is invalid per mapping | Check data and nullable/optional |
| DataIntegrityViolationException or FK error | Database rejects foreign key or constraint | Check whether referenced ID has a real row, constraints, and write order |
| EntityNotFoundException | Reference or proxy requires a non-existent entity | Check ID, deleted data, and proxy access timing |

The outer exception name may vary depending on Spring, Hibernate, and error timing. Always examine the cause chain and database message if available.

In particular, instantiating a Customer object with only a manually assigned ID is not the same as fetching a valid reference from EntityManager. If the ID does not exist, the database may report a foreign key error when writing. If the ID matches an existing record, the manually created object still does not automatically become a managed entity.

## 14. Transactions and Exception Handling

Place aggregate construction and saving of related entities inside a Service transaction:

~~~java
@Transactional
public Long createOrder(CreateOrderCommand command) {
    Customer customer = customerRepository.findById(command.customerId())
            .orElseThrow(() ->
                    new EntityNotFoundException("Customer not found"));

    PurchaseOrder order = new PurchaseOrder(customer);
    // Add order lines and update the owning side.

    return orderRepository.save(order).getId();
}
~~~

If an exception occurs inside the transaction, allow the appropriate error to propagate so Spring rolls back under default rules. By default, Spring rolls back on RuntimeException and Error. If converting to a checked exception, consider an appropriate rollbackFor configuration.

Do not catch TransientPropertyValueException, log it, and continue inside the same transaction. After a persistence error, the transaction or persistence context may be left in an unusable state. Let the transaction finish and roll back; then handle the error at the appropriate boundary or start a new transaction if a valid recovery flow exists.

Do not use REQUIRES_NEW just to mask object graph errors. A separate transaction can commit related data independently, breaking business atomicity.

## 15. Testing to Prevent Regressions

Have integration tests running against Hibernate and a suitable database type. At minimum, cover these cases:

- Create order with existing Customer: foreign key is saved properly.
- Create order with new OrderLine: cascade PERSIST from the aggregate root saves order lines.
- Assign transient Customer without cascade: operation fails as expected.
- Attempt to reference a non-existent ID: receive appropriate error from application validation or database constraint.
- Mutate both sides of a bidirectional relationship: owning side is persisted accurately.
- When a subsequent step fails: changes in the same transaction are rolled back.

An example happy-path test can use repositories to verify state after calling the Service:

~~~java
@Test
void createsOrderForExistingCustomer() {
    Customer customer = customerRepository.saveAndFlush(
            new Customer("An"));

    Long orderId = orderService.createOrder(customer.getId());

    PurchaseOrder reloaded = orderRepository.findById(orderId)
            .orElseThrow();

    assertEquals(customer.getId(), reloaded.getCustomer().getId());
}
~~~

This is an illustrative integration test snippet; the test class needs injected repositories/services and suitable database setup. If the test method runs inside a transaction managed by `@DataJpaTest`, operations may roll back when the test ends. That works for inspecting data within the test transaction, but if you need to verify an actual Service commit, design a separate test boundary and read back after the Service transaction has completed.

For failure tests, call saveAndFlush to force the error within the assertion scope. If the test transaction is marked rollback-only after an exception, do not keep using that persistence context to inspect state as if it were still healthy. Use a separate transaction or independent test case to verify post-rollback data.

## 16. TransientPropertyValueException Troubleshooting Checklist

- [ ] Read the root cause and identified the offending entity/association property.
- [ ] Distinguished whether the related entity is transient, managed, or detached.
- [ ] If the related entity already exists, loaded it with findById or getReferenceById as appropriate.
- [ ] If the related entity is new, saved it first or cascaded PERSIST from the right aggregate root.
- [ ] Avoided using fake IDs to simulate an existing entity.
- [ ] Avoided indiscriminate cascade REMOVE/ALL on shared relationships like Customer or Product.
- [ ] Checked the owning side and updated both sides of bidirectional relationships.
- [ ] Checked whether save takes the persist or merge path and used the returned entity when needed.
- [ ] Understood whether the error occurs at persist, flush, or commit.
- [ ] Avoided catching errors and continuing inside an already-failed transaction.
- [ ] Added integration tests for happy path, failure path, and rollback.

## 17. Conclusion

TransientPropertyValueException typically indicates an entity references an unsaved related object and the current operation lacks an appropriate PERSIST cascade. The fix depends on business lifecycle: load a managed entity if the record already exists, save the new entity first if it is independent, or cascade from the aggregate root if child entities are created and managed together with the root. Checking the owning side, distinguishing transient from detached, and observing flush timing help pinpoint the exact cause. After fixing, confirm with integration tests that foreign keys and rollbacks work correctly.
