# Do Not Assume Transaction Rollback Cleans Up Elasticsearch Documents

In a Spring application, a service may update a database and simultaneously write documents to Elasticsearch. When the service is annotated with `@Transactional`, it is easy to assume that if a step fails, both the database and Elasticsearch will roll back. That assumption is generally wrong.

Spring transactions coordinate only resources managed by the active transaction manager. A JDBC transaction can roll back changes in the database, whereas an Elasticsearch call over an HTTP/REST client is typically an independent operation. Once Elasticsearch has accepted and stored a document, rolling back the database does not delete that document automatically.

This is especially misleading in integration tests. A test annotated with `@Transactional` typically has its database changes rolled back by Spring TestContext when the test finishes. Documents written to Elasticsearch can still remain and interfere with subsequent tests.

Key takeaways to remember:

- Rolling back a database does not roll back Elasticsearch.
- `@Transactional` does not create a distributed transaction across a relational database and Elasticsearch.
- Bulk requests are not atomic multi-document transactions either.
- Keeping two systems in sync requires explicit consistency, retry, and compensation design.
- Tests must clean up Elasticsearch data separately, using isolated IDs or indices.

## 1. Which Resources Do Spring Transactions Manage?

The `@Transactional` annotation marks a transactional boundary at the Spring layer. When a method is invoked through the transaction proxy, Spring selects the appropriate transaction manager to start, commit, or roll back a transaction.

Database example:

    @Service
    public class ProductService {

        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        @Transactional
        public Product create(Product product) {
            return repository.save(product);
        }
    }

When the repository uses JPA/JDBC and the transaction manager manages database connections, `save` participates in that transaction. If the method throws a `RuntimeException` before committing, the database transaction rolls back according to Spring's rollback rules.

The transaction manager does not automatically enlist every network call made inside the method. An HTTP request, file write, email send, or Elasticsearch operation does not become transactional merely because it runs inside a `@Transactional` method.

Example:

    @Transactional
    public Product create(Product product) {
        ProductEntity saved = databaseRepository.save(
            ProductEntity.from(product)
        );

        operations.save(product);

        return Product.from(saved);
    }

In this example:

1. The database repository participates in the open database transaction.
2. `operations.save` sends a request to Elasticsearch.
3. Elasticsearch processes the request independently and may persist the document.
4. If the method fails after step 2, Spring may roll back the database.
5. The Elasticsearch document already written is not automatically deleted.

`@Transactional` defines a boundary for the selected transaction manager; it does not turn every side effect inside the method into a single atomic transaction.

## 2. Elasticsearch Does Not Participate in Ordinary JDBC Transactions

Spring Data Elasticsearch communicates with Elasticsearch via an HTTP client and transport. Index, update, or delete requests are sent to the cluster and handled by Elasticsearch according to its own APIs.

A JDBC transaction manager has no way to roll back an HTTP request already acknowledged by Elasticsearch. Nor does Elasticsearch join a database's transaction coordinator to provide a shared atomic commit across both systems.

There is no shared transaction like this in standard integration setups:

    BEGIN
      UPDATE relational_database
      INDEX elasticsearch_document
    COMMIT BOTH

When the database rolls back, Elasticsearch never receives a rollback command. Once Elasticsearch indexes a document, that change persists until another write or delete occurs.

Even declaring multiple transaction managers or calling multiple repositories in the same service does not create an atomic transaction spanning a database and Elasticsearch. Coordinating multiple stores requires a distributed architecture with recovery mechanisms, not just annotations.

## 3. Timeline: Database Rolls Back While Elasticsearch Keeps the Document

Suppose a service creates a product:

    @Transactional
    public void create(Product product) {
        databaseRepository.save(ProductEntity.from(product));
        elasticsearchOperations.save(product);
        throw new IllegalStateException("later step failed");
    }

Timeline:

    Database transaction       Elasticsearch
    --------------------       -------------
    BEGIN
    INSERT product
                               INDEX product
                               ACK success
    Exception
    ROLLBACK
                               Document still exists

Outcome:

| System | Final state |
|---|---|
| Database | Product absent because the transaction rolled back |
| Elasticsearch | Product document may still exist |

The search index now holds data that does not exist in the source database. This is an orphan document or stale projection.

If the next test searches by product ID, it may find the document left behind by the earlier test. That test can fail even though its own code is right.

## 4. The Reverse Case Can Also Happen

If an application writes to Elasticsearch first and then writes to the database:

    @Transactional
    public void create(Product product) {
        elasticsearchOperations.save(product);
        databaseRepository.save(ProductEntity.from(product));
    }

If the database write fails or the transaction rolls back afterward, Elasticsearch can retain the document while the database has no corresponding row.

If the application writes to the database first and then to Elasticsearch, risks remain:

- Database commits successfully, yet the Elasticsearch request fails.
- Database commits successfully, yet the process dies before sending the request.
- Elasticsearch times out and the application does not know whether the request succeeded.

Both orderings have a failure window. Reordering operations does not fix the lack of an atomic transaction across two stores.

## 5. Four Dual-Write Failure Modes to Distinguish

| Scenario | Database | Elasticsearch | Consequence |
|---|---|---|---|
| DB succeeds, ES succeeds | Committed | Indexed | Desired state |
| ES succeeds, DB rolls back | Rolled back | Indexed | Orphan document |
| DB commits, ES fails | Committed | Not updated | Missing/stale search projection |
| ES times out, DB commits or rolls back | May commit/roll back | Unknown to client | Needs reconciliation or idempotent retry |

Timeouts are especially tricky: not receiving a client response does not mean the server did not execute the operation. Elasticsearch may have indexed the document before the connection dropped on the response.

Therefore, never treat an Elasticsearch client exception as proof that the document was not written.

## 6. The Bulk API Is Not a Transaction

The Bulk API batches multiple index, create, update, or delete actions into one request. It cuts overhead and raises throughput, yet it does not provide an atomic transaction across all items.

A bulk response can contain both succeeded and failed items:

    {
      "errors": true,
      "items": [
        {
          "index": {
            "_id": "p-1",
            "status": 201
          }
        },
        {
          "index": {
            "_id": "p-2",
            "status": 400,
            "error": {
              "type": "mapper_parsing_exception",
              "reason": "failed to parse field"
            }
          }
        }
      ]
    }

In this example, `p-1` can be indexed successfully even though `p-2` failed. The application cannot ask the bulk request to roll back `p-1` simply because `p-2` was invalid.

When a bulk item fails, inspect each item response and decide whether to retry, fix data, or route to a DLQ. Never assume bulk behaves like a multi-statement SQL transaction.

## 7. Refresh Is Neither Transaction Rollback Nor Commit

Elasticsearch is a near-real-time search engine. A written document may not appear in search results until the shard refreshes.

Distinguish between:

- Write acknowledgement: Elasticsearch processed the action and responded per request semantics.
- Durability: translog, replication, and flush protecting persisted data.
- Search visibility: whether the document has been refreshed so search sees it.
- Database transaction: transaction managed by the database transaction manager.

Refreshing does not commit or roll back a database. Nor does calling refresh turn an earlier Elasticsearch write into part of a SQL transaction.

In tests, if search misses a document right after `save`, the cause may simply be that refresh has not happened yet. That differs from a database rollback or a failed Elasticsearch write. Use real-time GET by ID to check whether the document exists, or refresh explicitly in tests when verifying search visibility.

## 8. @Transactional in Integration Tests Can Leave Documents Behind

Spring TestContext normally rolls back a test's transaction after the method ends when the test is annotated with `@Transactional` and does not request commit.

Example:

    @SpringBootTest
    @Transactional
    class ProductServiceIntegrationTest {

        @Autowired
        ProductService productService;

        @Autowired
        ProductRepository productRepository;

        @Test
        void createsProduct() {
            productService.create(productFixture());

            assertThat(productRepository.findAll())
                .hasSize(1);
        }
    }

After the test, the database transaction may roll back. Yet if `productService.create` called Elasticsearch, the document may still remain in the index.

This happens even though the test framework logs a successful transaction rollback. Spring rolls back only resources managed by its transaction manager; it does not delete Elasticsearch documents automatically.

### Subsequent Tests Are Affected

Suppose the first test writes `p-100` to Elasticsearch and then rolls back the database. The second test uses the same ID `p-100` or runs a broad query:

    SearchHits<Product> hits =
        operations.search(query, Product.class);

The second test can see data from the first test. If tests run in parallel, outcomes become even less predictable.

## 9. @DataJpaTest Does Not Clean Up Elasticsearch Either

`@DataJpaTest` configures a JPA slice test with transaction rollback after each test. If the test imports a service or invokes an Elasticsearch client directly to write documents, Elasticsearch remains an external system outside the JPA transaction.

Do not infer that because the database rolls back automatically, all related test data is rolled back too.

When tests involve both JPA and Elasticsearch:

- Identify which transaction manager manages the test transaction.
- Identify which operations actually participate in that transaction.
- Record created Elasticsearch IDs/indices.
- Clean up Elasticsearch independently after the test.
- Verify search visibility via refresh when assertions use search.

## 10. Why Doesn't @DirtiesContext Delete Elasticsearch Data?

`@DirtiesContext` instructs Spring TestContext to discard or recreate the `ApplicationContext` for the configured scope. It does not wipe data inside an Elasticsearch cluster.

Elasticsearch typically runs in a separate process, container, or service. Closing a Spring context does not delete indices or documents on the cluster.

Likewise:

- Restarting Spring Boot does not delete indices automatically.
- Recreating repository beans does not delete documents.
- Rolling back a database transaction does not delete documents.
- Deleting a database entity does not delete its projection automatically without a sync mechanism.

To clear data, tests must invoke the delete API or delete dedicated test indices.

## 11. Cleaning Up Elasticsearch Documents in Tests

A simple approach is recording created IDs and deleting them after the test:

    @AfterEach
    void cleanElasticsearch() {
        for (String id : createdProductIds) {
            operations.delete(id, Product.class);
        }

        operations.indexOps(Product.class).refresh();
        createdProductIds.clear();
    }

This example uses the common imperative API. Exact `delete` and `refresh` signatures depend on the Spring Data Elasticsearch version. You can also use the Elasticsearch Java API Client for direct control.

Advantages:

- Deletes only data belonging to the current test.
- Does not affect documents from other tests.
- Can share a test index if IDs are namespaced.

Disadvantages:

- Must track every created ID.
- If the test process crashes before cleanup, documents can linger.
- On write timeouts, IDs still need cleanup because the server may have processed them.

Cleanup should live in a `finally` block or appropriate lifecycle hook so it runs even when assertions or test actions fail.

## 12. Using Dedicated IDs per Test

Avoid fixed IDs in tests sharing an index unless there is a clear reason and guaranteed cleanup.

Example:

    String testRunId = UUID.randomUUID().toString();
    String productId = "test-" + testRunId;

    Product product = new Product();
    product.setId(productId);
    product.setName("Test Keyboard");

    operations.save(product);
    createdProductIds.add(productId);

Dedicated IDs help:

- Avoid overwriting another test's data.
- Reduce conflicts under parallel execution.
- Identify which test run owns a document.
- Perform accurate cleanup.

If the system uses `tenantId`, you can attach `testRunId` to a metadata field or dedicated test tenant for cleanup queries.

Never use a fixed ID like `test-product` for every test in a shared index. Tests can overwrite or delete each other's data.

## 13. Using Dedicated Indices per Test or Test Suite

A stronger option is creating a uniquely named index per test run:

    String indexName =
        "products-test-" + UUID.randomUUID().toString().replace("-", "");

    IndexOperations indexOps =
        operations.indexOps(IndexCoordinates.of(indexName));

    indexOps.create();
    indexOps.putMapping();

After the test:

    indexOps.delete();

This snippet only illustrates index isolation; `create` and mapping APIs depend on Spring Data configuration. When using entity annotations, you can build mappings from entity metadata or declare separate mappings.

Advantages:

- Cleans up all test data by deleting the index.
- Prevents cross-test interference.
- Allows testing mappings/index settings independently.

Disadvantages:

- Creating/deleting indices adds overhead.
- Can slow down the test suite if every test creates an index.
- Requires managing dynamic aliases and index names.
- Not all repositories are straightforward to configure with dynamic indices.

You can use one index per test class or test run instead of per method, provided data is namespaced and cleaned up explicitly.

## 14. Never Delete an Entire Shared Index After Each Test

A dangerous cleanup pattern:

    operations.indexOps(Product.class).delete();

If multiple tests or developers share the `products` index, this wipes everyone's data.

Only delete an index when the test owns that index exclusively and no other consumer shares it. For shared indices, delete by ID or `testRunId` filter.

When using delete-by-query, scope the query strictly to the test namespace:

    POST products/_delete_by_query
    {
      "query": {
        "term": {
          "testRunId": "run-123"
        }
      }
    }

Never run `match_all` deletes on a shared index. One broken filter can wipe non-test data.

## 15. Cleanup Must Account for Write Timeouts

If the Elasticsearch client times out, the test cannot tell whether the request wrote the document. Adding IDs to the cleanup list only after `save` returns successfully can miss documents written right before a response timeout.

Record IDs before sending:

    String id = "test-" + UUID.randomUUID();
    createdProductIds.add(id);

    Product product = new Product(id, "Test Product");
    operations.save(product);

If the request failed before reaching the server, deleting a non-existent ID during cleanup can usually be handled safely per API semantics. If the server processed the request while the response was lost, cleanup still knows the ID to delete.

For bulk requests, record all intended IDs before sending the batch. After receiving the response, you can enrich per-item status, yet cleanup must never rely solely on the list of succeeded items reported back to the client.

## 16. Using testRunId for Grouped Cleanup

In large test suites, store `testRunId` on test documents:

    {
      "id": "p-100",
      "name": "Test Product",
      "testRunId": "run-abc123"
    }

Cleanup:

    DELETE products/_delete_by_query
    {
      "query": {
        "term": {
          "testRunId": "run-abc123"
        }
      }
    }

After delete-by-query, if subsequent assertions rely on search, refresh according to the appropriate policy so deletions become visible.

The `testRunId` field should be mapped as `keyword`. Never use a `text` analyzer for identifier fields queried with `term`.

If `testRunId` is not permitted in the production schema, use a dedicated test index or a metadata field present only in test mappings. Do not pollute production documents with test fields purely for cleanup convenience.

## 17. Testing Transaction Rollback Explicitly

When a test aims to prove that database rollback does not clean up Elasticsearch, assert both states explicitly.

Conceptual example:

    @SpringBootTest
    class DualWriteRollbackTest {

        @Autowired
        ProductService service;

        @Autowired
        ProductRepository databaseRepository;

        @Autowired
        ElasticsearchOperations operations;

        @Test
        void databaseRollbackDoesNotUndoElasticsearchWrite() {
            String id = "rollback-" + UUID.randomUUID();

            assertThatThrownBy(() ->
                service.createThenFail(productWithId(id))
            ).isInstanceOf(IllegalStateException.class);

            assertThat(databaseRepository.findById(id))
                .isEmpty();

            Product indexed = operations.get(
                id,
                Product.class,
                IndexCoordinates.of("products")
            );

            assertThat(indexed).isNotNull();
        }
    }

This illustrates transaction boundaries. Ensure the service method actually passes through Spring's transaction proxy and that the test itself does not wrap the entire method in an outer transaction that changes the scenario under test.

The test must also clean up the document in `finally`/`@AfterEach`. If an assertion aborts before cleanup, test data can remain behind.

## 18. Default @Transactional Test Rollback and Elasticsearch Data

A test method annotated with `@Transactional` typically executes inside a transaction opened by Spring TestContext and rolled back at the end.

Example:

    @SpringBootTest
    @Transactional
    class ProductIntegrationTest {

        @Test
        void saveProduct() {
            databaseRepository.save(entity);
            operations.save(product);
        }
    }

Once the method finishes:

- The database may roll back.
- The Elasticsearch document may still exist.

If a test needs to verify post-commit behavior, default rollback transactions do not fit. Use `@Commit`, `@Rollback(false)`, or `TestTransaction` to control commits explicitly, while cleaning up external non-database data.

Do not scatter `@Rollback(false)` carelessly across the test suite. Committing real database rows can couple tests and leave long-lived state behind.

## 19. Testing AFTER_COMMIT Listeners

Spring provides `@TransactionalEventListener` to handle events tied to transaction phases:

    @Component
    public class ProductIndexListener {

        private final ElasticsearchOperations operations;

        public ProductIndexListener(
                ElasticsearchOperations operations) {
            this.operations = operations;
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
        )
        public void onProductChanged(ProductChanged event) {
            operations.save(event.product());
        }
    }

By default, the listener runs only after the database transaction commits successfully. If the transaction rolls back, the `AFTER_COMMIT` listener is not invoked.

This avoids writing to Elasticsearch before database commit in event-listener flows. However, it still does not guarantee durable event delivery.

If the process crashes after the database commits yet before the listener runs or before Elasticsearch finishes writing, the in-memory event can be lost. `@TransactionalEventListener` does not replace an outbox.

When the listener runs asynchronously via `@Async`, you also need exception handling, retries, shutdown coordination, and observability. A caller that already committed to the database cannot trigger a database rollback merely because an async Elasticsearch write failed.

## 20. Testing AFTER_COMMIT Listeners Requires an Actual Commit

A `@Transactional` test with default rollback may never trigger an `AFTER_COMMIT` listener:

    @SpringBootTest
    @Transactional
    class ProductIndexListenerTest {

        @Test
        void publishesIndexAfterCommit() {
            applicationEventPublisher.publishEvent(event);
        }
    }

Because the test transaction rolls back at the end of the method, the `AFTER_COMMIT` phase never occurs. The test can finish without running the listener and still report green.

To test after-commit behavior:

- Annotate the appropriate test method with `@Commit`.
- Or use `TestTransaction.flagForCommit()` followed by `TestTransaction.end()`.
- Wait for the listener to finish before asserting if it runs asynchronously.
- Clean up both the database and Elasticsearch after the test.

For async listeners, use Awaitility or a bounded wait mechanism on the final state. Avoid fixed `Thread.sleep`, as execution time varies with load.

## 21. AFTER_COMMIT Still Has an Event-Loss Window

Timeline:

    Database transaction
       |
       +--> UPDATE product
       |
       +--> COMMIT succeeds
                 |
                 v
           AFTER_COMMIT listener
                 |
                 +--> process crashes before publishing
                 |
                 +--> Elasticsearch request fails

The database has committed, yet Elasticsearch has not been updated. If the event existed only in memory, the system may have no record of what needs retrying.

`AFTER_COMMIT` fits non-critical side effects or setups backed by another recovery mechanism. For critical synchronization, prefer the outbox pattern or CDC.

## 22. The Outbox Pattern

The outbox pattern writes business state changes and outgoing events in the exact same database transaction.

Example:

    @Transactional
    public void updateProduct(ProductCommand command) {
        ProductEntity product =
            productRepository.findById(command.id())
                .orElseThrow();

        product.changePrice(command.price());
        productRepository.save(product);

        outboxRepository.save(
            OutboxEvent.productChanged(product)
        );
    }

Both database operations participate in one transaction:

    BEGIN
      UPDATE product
      INSERT outbox_event
    COMMIT

If the transaction rolls back, both the product update and the outbox row roll back. Once committed, a publisher reads the outbox and dispatches events afterward.

The publisher may poll periodically or use CDC. After publishing succeeds, the outbox record is marked sent or tracked by an offset.

An outbox reduces the risk of losing events after database commits. It does not create an atomic transaction between the database and Elasticsearch; consumers must still retry and remain idempotent.

## 23. Outbox Consumers Must Tolerate Duplicates

A publisher may dispatch an event to the broker and crash before marking the outbox row as sent. Upon restart, it can publish the same event again.

Therefore, consumers should:

- Receive a stable `eventId`.
- Use deterministic document IDs.
- Check source versions.
- Write projections idempotently toward the desired state.
- Handle duplicate deliveries of the same event without corrupting state.

Example event:

    {
      "eventId": "evt-123",
      "aggregateId": "p-100",
      "aggregateVersion": 42,
      "eventType": "ProductUpdated",
      "payload": {
        "name": "Keyboard K8",
        "price": 120
      }
    }

If the Elasticsearch document is already at version 42, the consumer can ignore the duplicate event. If the index is at version 40, the consumer can update it to version 42.

## 24. Sagas and Compensation

When an atomic cross-system transaction is impossible, a workflow can use a saga: each step is an independent action paired with a compensating action if the workflow fails.

Example:

1. Save product in the database.
2. Index document in Elasticsearch.
3. Emit event to another system.

If step 3 fails, the workflow can retry or execute compensation per business rules.

Compensation is not an atomic rollback. It is a new forward operation aimed at bringing the system to an acceptable state.

If deleting an Elasticsearch document is needed after a database failure, you can issue a delete as compensation. Yet that delete can also time out, fail, or execute out of order against a newer event.

Therefore, compensation needs:

- ID and version metadata to target the exact document.
- Idempotency or safe retryability.
- Protection against deleting newer state.
- Tracking of compensation status.
- Reconciliation when compensation fails to complete.

## 25. Never Use Delete as an Unconditional Rollback

Suppose Elasticsearch already indexed version 10. Then the database rolls back and the app sends a delete by ID. Meanwhile, another request may have already written a valid version 11.

An unversioned delete during compensation can accidentally wipe version 11.

Thus, compensation must know which version it is compensating for. Use external versioning, sequence numbers/primary terms, or marker operations depending on your API and design.

Never delete blindly by ID if concurrent requests can update the same ID.

## 26. Optimistic Concurrency Is Not a Distributed Transaction

Elasticsearch supports optimistic concurrency control via versions or `if_seq_no`/`if_primary_term` on supporting APIs.

These mechanisms detect whether a document changed between read and write. They do not create a shared transaction with a database.

For example:

- Rolling back a database transaction does not rewind an Elasticsearch sequence number.
- Incrementing an Elasticsearch version is never undone automatically by a database transaction.
- Document update conflicts must be handled separately.

Use concurrency control to prevent stale data from overwriting newer data—never as proof that two systems committed or rolled back together.

## 27. Transaction Managers and Multiple Data Stores

An application may declare multiple transaction managers—for example, one for JPA and one for a reactive database or another resource. `@Transactional` can select a transaction manager using a qualifier.

However, selecting one transaction manager does not coordinate remaining resources into an atomic commit.

Even with multi-transaction-manager wrappers, check carefully which resources support enlistment, prepare/commit/rollback, and crash recovery. Ordinary Elasticsearch REST calls do not participate in XA/JTA transactions with relational databases.

Do not assume that:

    @Transactional("transactionManager")

or declaring an extra transaction manager makes Elasticsearch writes roll back alongside JPA.

Identify each resource's transaction boundary and design eventual consistency or compensation for anything that cannot enlist.

## 28. Rollback Rules of @Transactional

By default, Spring rolls back transactions on `RuntimeException` or `Error`. Checked exceptions do not trigger rollback by default unless configured via `rollbackFor`.

Example:

    @Transactional(rollbackFor = IOException.class)
    public void process() throws IOException {
        databaseRepository.save(entity);
        elasticsearchOperations.save(document);
        throw new IOException("failed");
    }

`rollbackFor` can make the database transaction roll back when `IOException` occurs. It still does not delete the document written to Elasticsearch.

Rollback rules govern only how the transaction manager handles its own managed transaction. They do not grant rollback capability to external side effects.

## 29. Self-Invocation on @Transactional Methods

Spring transactions are typically applied via proxies. When one method in a bean directly calls another `@Transactional` method in the same bean, the internal call bypasses the proxy and the inner transaction annotation may not take effect as expected.

This can confuse tests or services about transaction boundaries. However, even when `@Transactional` is applied cleanly, HTTP writes to Elasticsearch still never roll back with the database.

When testing transactions:

- Invoke the service through its Spring bean/proxy.
- Avoid self-invocation when relying on propagation.
- Verify transactions are actually active when needed.
- Confirm which transaction manager is selected.
- Never infer Elasticsearch transaction participation from a successful database rollback.

## 30. Testing Persisting Data After Rollback

An integration test can demonstrate this failure mode explicitly:

    @Service
    public class ProductService {

        private final ProductRepository databaseRepository;
        private final ElasticsearchOperations operations;

        @Transactional
        public void saveThenFail(ProductEntity entity) {
            databaseRepository.save(entity);

            Product document = Product.from(entity);
            operations.save(document);

            throw new IllegalStateException("force rollback");
        }
    }

Test:

    @Test
    void rollbackOnlyAffectsDatabase() {
        String id = "rollback-" + UUID.randomUUID();

        assertThatThrownBy(() ->
            service.saveThenFail(productEntity(id))
        ).isInstanceOf(IllegalStateException.class);

        assertThat(databaseRepository.findById(id)).isEmpty();

        Product document = operations.get(
            id,
            Product.class,
            IndexCoordinates.of("products")
        );

        assertThat(document).isNotNull();
    }

This is an illustrative example. Ensure the service method actually passes through the Spring transaction proxy and that the test does not open an outer transaction wrapping the call in a way that alters the scenario under test.

The test must also clean up the document in `finally`/`@AfterEach`. If assertions abort early, test data may linger.

## 31. Tests Must Not Depend on Execution Order

A test that passes alone yet fails in the full suite often shares mutable data or index state.

Causes:

- Leftover documents from earlier tests.
- Tests reusing fixed IDs and overwriting each other.
- Cleanup running only when assertions succeed.
- Parallel tests sharing an index.
- Tests using overly broad tenants or filters.
- Async indexing running after test cleanup finished.

Solutions:

- Generate unique IDs per test run.
- Use dedicated indices or test namespaces.
- Record IDs before issuing writes.
- Clean up inside `finally`/`@AfterEach`.
- Await or cancel async workers.
- Never depend on test ordering.

## 32. Cleanup Inside finally

When a test creates documents directly, you can wrap it in `try`/`finally`:

    String id = "test-" + UUID.randomUUID();

    try {
        operations.save(productWithId(id));

        Product found = operations.get(
            id,
            Product.class,
            IndexCoordinates.of("products")
        );

        assertThat(found).isNotNull();
    } finally {
        operations.delete(
            id,
            Product.class,
            IndexCoordinates.of("products")
        );
    }

`delete`/`get` signatures vary across Spring Data versions. If cleanup itself can throw, log cleanup failures without masking the original test failure. You can also centralize cleanup in a test extension or resource fixture.

For bulk writes, record all IDs before sending and delete all in cleanup. Even if the request times out, clean up all anticipated IDs.

## 33. Cleanup Using @AfterEach

In a test class with multiple methods, track created IDs in a set:

    private final Set<String> createdIds =
        ConcurrentHashMap.newKeySet();

    @AfterEach
    void cleanup() {
        for (String id : createdIds) {
            operations.delete(
                id,
                Product.class,
                IndexCoordinates.of("products")
            );
        }

        operations.indexOps(Product.class).refresh();
        createdIds.clear();
    }

`ConcurrentHashMap.newKeySet` is needed only if tests spawn multiple threads writing IDs. For strictly sequential tests, a plain collection suffices.

In async tests, wait for workers to finish or cancel them before cleanup. If a worker writes after cleanup runs, documents can reappear.

## 34. Cleanup by Dedicated Test Index

A test suite can provision a class-scoped index:

    @BeforeAll
    static void createIndex() {
        // Create a uniquely named index for the test suite.
    }

    @AfterAll
    static void deleteIndex() {
        // Delete only the index owned by the test suite.
    }

This works well when verifying mappings, analyzers, or settings, while isolating data from other tests.

When generating dynamic index names, point templates/repositories to that index. Never let production repositories or other tests accidentally read or write a test index scheduled for deletion.

## 35. Cleanup Using testRunId

In large test suites, attach `testRunId` to test documents:

    {
      "id": "p-100",
      "name": "Test Product",
      "testRunId": "run-abc123"
    }

Cleanup:

    DELETE products/_delete_by_query
    {
      "query": {
        "term": {
          "testRunId": "run-abc123"
        }
      }
    }

After delete-by-query, if subsequent assertions rely on search, refresh per policy so deletions become visible.

Map `testRunId` as `keyword`. Never use a `text` analyzer for identifier fields used in `term` queries.

If `testRunId` is disallowed in the production schema, use a separate test index or a metadata field present only in test mappings. Do not add test-only fields to production documents merely for cleanup convenience.

## 36. Never Delete an Entire Shared Index

A dangerous cleanup pattern:

    operations.indexOps(Product.class).delete();

If multiple tests or developers share `products`, this wipes everyone's data.

Delete an index only when the test owns it exclusively and no other consumers share it. On shared indices, delete by ID or `testRunId` filter.

Never execute `match_all` deletes on a shared index. A broken filter can delete non-test data.

## 37. Cleanup Must Account for Write Timeouts

When the Elasticsearch client times out, the test does not know whether the document was saved. Recording IDs only after `save` succeeds risks leaking documents written before the timeout.

Record IDs before sending:

    String id = "test-" + UUID.randomUUID();
    createdProductIds.add(id);

    Product product = new Product(id, "Test Product");
    operations.save(product);

If the request failed before reaching the server, deleting a non-existent ID in cleanup is usually safe per API semantics. If the server processed the write while the response was lost, cleanup still knows the ID to remove.

For bulk writes, record all intended IDs before sending the batch. Cleanup should never rely solely on the list of succeeded items returned to the client.

## 38. Refresh in Cleanup and Assertions

After indexing a document, real-time GET by ID sees it immediately while search may need a refresh. After deleting, search can also keep returning the document until the next refresh.

In tests:

- If assertions use GET by ID, you do not rely on search refresh the same way.
- If assertions use search, refresh after setup or apply an appropriate refresh policy.
- If cleanup uses delete-by-query and the next test searches, refresh after cleanup when needed.

Never use fixed `Thread.sleep` durations to wait for refresh. Explicit refreshes in tests make conditions clear and reduce flakiness.

Refresh only controls search visibility; it never rolls back documents or transactions.

## 39. Async Event Listeners and Cleanup Races

Suppose a test emits an event and an `@Async` listener writes to Elasticsearch. The test may finish, cleanup deletes the document, and then the async worker runs and writes the document back.

Timeline:

    Test publishes event
       |
       v
    Async task queued
       |
       v
    Test finishes and cleans up
       |
       v
    Async task runs after cleanup
       |
       v
    Document reappears

To prevent this:

- Wait for tasks to finish before running cleanup.
- Use a synchronous test executor when appropriate.
- Use test event listeners or latches to confirm completion.
- Disable or isolate unrelated consumers during tests.
- Use dedicated indices/IDs so late writes cannot affect other tests.

Never assume `@AfterEach` automatically means every async task has finished.

## 40. Testing Outbox and Eventual Consistency

If the application uses an outbox, write separate tests for each stage:

1. On database commit, both business row and outbox row persist.
2. On database rollback, neither row persists.
3. Publisher reads the outbox and emits the event.
4. Consumer indexes the document successfully.
5. On Elasticsearch failures, events retry or remain pending.
6. When the consumer receives duplicates, projections stay intact.
7. When an older event arrives after a newer event, version checks prevent stale overwrites.

Do not try to verify the entire flow using a single `@Transactional` rollback test. Separate transaction persistence, publishing, consumption, and Elasticsearch integration to pinpoint failures quickly.

For eventual consistency, assertions should wait on a bounded condition:

    await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() -> {
            Product indexed = operations.get(
                id,
                Product.class,
                IndexCoordinates.of("products")
            );
            assertThat(indexed).isNotNull();
        });

This example uses Awaitility. Pick timeouts suited to the test environment, and refresh if assertions rely on search.

## 41. Testing When Elasticsearch Fails

To verify recovery, simulate failure modes:

- Elasticsearch unreachable.
- Request timeout.
- HTTP 429 or rejected execution.
- Missing index.
- Mapping parse error.
- Partial bulk failure.
- Consumer crashes after writing but before acknowledging.
- Response lost even though the server processed the write.

Use mock clients for unit-testing error classification and Testcontainers/Elasticsearch test instances for integration tests. Faults like timeouts after server-side processing require fault injection or dedicated test proxies.

Tests should verify:

- The database transaction commits or rolls back as required.
- Events/outbox rows remain retryable.
- DLQ captures exact permanent failures.
- Retries produce no duplicate side effects.
- Reconciliation detects missing or orphan documents.

## 42. Never Use Mocks to Prove Elasticsearch Rollback

Mocking `ElasticsearchOperations` can confirm the service called `save` or `delete`. It cannot prove Elasticsearch's real state after a rollback.

To verify transaction boundaries, run at least one integration test with real Elasticsearch or an equivalent test environment:

- Issue a real write.
- Trigger a database rollback.
- Read the document back from Elasticsearch.
- Verify the document persists or was removed by compensation as designed.
- Clean up test data afterward.

Mocks work well for unit-testing orchestration logic, yet they cannot prove server-side persistence.

## 43. Testcontainers and Dedicated Elasticsearch Environments

Testcontainers can start Elasticsearch for integration tests, providing far better isolation than shared clusters.

A practical setup:

- Start the container at test-suite scope.
- Create dedicated test indices per class or test run.
- Use production-like mappings/settings.
- Track document IDs.
- Clean up indices/documents at the end.
- Close the container after the whole suite finishes.

Do not spin up a fresh container per test method if startup cost is high. Isolating via indices or namespaces is usually more efficient.

Testcontainers does not make Elasticsearch join database transactions. It solely manages test-environment lifecycles.

## 44. Database Rollback and Test Data Setup

If database fixtures are inserted inside a test transaction that rolls back at method end, an async consumer running after the test may fail to find the source row.

Example:

1. Test inserts a product inside a transaction.
2. Test publishes an event.
3. Async consumer runs after the test transaction rolls back.
4. Consumer queries the database and finds no product.

This makes tests flaky or creates unwanted DLQ entries.

When testing event-driven flows:

- Commit fixtures before consumers run if consumers read the source database.
- Or carry full payloads in events so consumers do not depend on uncommitted transactions.
- Control consumers and transaction boundaries explicitly.
- Clean up database and Elasticsearch fixtures separately.

Never let a test roll back fixtures while background workers are still processing them.

## 45. Spring Transaction Propagation Does Not Fix Dual Writes

Propagation modes such as `REQUIRED`, `REQUIRES_NEW`, `NESTED`, or `NOT_SUPPORTED` control how Spring joins or opens transactions for resources managed by a transaction manager.

They do not turn an Elasticsearch HTTP request into a JDBC transaction participant.

For example, `REQUIRES_NEW` starts an independent database transaction. Calling Elasticsearch inside it remains an independent HTTP call. Rolling back the outer transaction does not delete the written document.

Do not try to use propagation to fake atomicity between a database and Elasticsearch. Identify the transaction manager and concrete resource used by each step.

## 46. Transactional Outbox vs AFTER_COMMIT Events

| Criterion | AFTER_COMMIT application event | Transactional outbox |
|---|---|---|
| Runs only after DB commit | Yes | Yes, via publisher reading outbox |
| Event stored durably with DB transaction | No by default | Yes |
| Process crash right after commit | May lose event | Outbox row persists |
| Duplicate delivery | Possible depending on async/retry | Possible; consumer must be idempotent |
| Requires publisher/replay | Depends on design | Yes |
| Complexity | Lower | Higher, with clear recovery |

`AFTER_COMMIT` suits lightweight side effects or setups with alternative recovery mechanisms. Outbox suits critical source changes that must sync reliably to Elasticsearch or a broker.

## 47. When to Use Sagas/Compensation?

Sagas fit business workflows spanning multiple independent steps that may need compensating actions.

Example:

    Reserve inventory
         |
         v
    Save order
         |
         v
    Index order search document
         |
         v
    Notify downstream

If a downstream step fails, deleting prior data is not always right. You may retry the failed step, mark pending state, or run business-specific compensation.

For Elasticsearch projections, keeping the database as the source of truth and retrying/rebuilding projections is usually preferable. Deleting Elasticsearch documents to mimic a database rollback is often unnecessary and can introduce further inconsistency.

Compensation must be a stateful, retryable business operation—never an uncontrolled delete command.

## 48. Versioning Prevents Regressing Projections

Suppose an older version-5 event is retried after version 7 was already indexed. If the consumer overwrites blindly by ID without checking versions, data can regress.

You can store `sourceVersion` in documents:

    {
      "id": "p-100",
      "name": "Keyboard K8",
      "price": 120,
      "sourceVersion": 7
    }

Consumer check:

    if (event.sourceVersion() <= indexed.sourceVersion()) {
        return; // duplicate or stale event
    }

In real implementations, use external versioning or conditional updates matching Elasticsearch APIs to prevent races between reading the version and writing.

Versioning protects document update ordering. It does not create a shared transaction with the database.

## 49. Reconciliation to Detect Orphan Documents

If a database rolls back while Elasticsearch succeeded, reconciliation can find documents existing solely in the index.

A workflow:

1. Read ID sets or a snapshot from the database.
2. Scan IDs in Elasticsearch via PIT/`search_after` or batches.
3. Compare IDs and source versions.
4. Identify documents no longer present in the source.
5. Check tombstones or business state.
6. Delete or flag documents per policy.

Never delete every missing document from a single inconsistent database read while data is actively being created. Use watermarks, tombstones, or transactional snapshots to avoid deleting brand new documents.

Reconciliation serves as a safety net for residual drift, not a replacement for event-driven sync.

## 50. Reconciliation and Deletion Policies

Orphan documents can arise from rollbacks, sync errors, duplicate events, or index migrations. Before deleting, check:

- Does the ID still exist in the source?
- Is the source marked deleted or merely inside an uncommitted transaction?
- Does the indexed document have a newer version?
- Does an alias point to an older index?
- Are events still pending processing?
- Which tenant/test run owns the document?

For critical business data, retain tombstones or event histories to confirm deletions reliably. Never run a broad delete-by-query lacking version/namespace conditions.

## 51. Tests Must Not Share Uncontrolled State

A test suite may share:

- Elasticsearch cluster.
- Index names.
- Database schemas.
- Broker topics.
- Consumer groups.
- Caches.

Without namespacing data, tests can read or delete state created by other suites.

Tag documents/events with `testRunId` and isolate indices/topics where needed. Under parallel execution, cleanup must target only data owned by that test.

Never wipe an entire shared index or topic just to fix a flaky test.

## 52. Workflow for Testing Transactions and Elasticsearch

A clear test plan can cover:

1. Test database transaction rollback independently.
2. Test Elasticsearch save/get/delete independently.
3. Test dual-write service failing after the ES write.
4. Verify the database rolls back while the ES document persists.
5. Test `AFTER_COMMIT` listeners execute only on commit.
6. Test outbox rows commit/roll back atomically with business rows.
7. Test publishers and consumers handling duplicates.
8. Test partial bulk failures.
9. Test retries and DLQs.
10. Test cleanup after timeouts and exceptions.
11. Test parallel execution with isolated IDs/indices.
12. Test reconciliation detecting orphan/missing documents.

Each test should explicitly define its transaction manager, transaction boundary, target index, refresh policy, and cleanup strategy.

## Conclusion

Spring transaction rollbacks do not automatically clean up documents written to Elasticsearch. `@Transactional` coordinates resources managed by the transaction manager; a typical Spring Data Elasticsearch call dispatches an independent HTTP request and does not join JDBC transactions. Consequently, databases can roll back while documents remain, or databases can commit while search indices stay stale. Bulk APIs are not atomic transactions either and can produce partial failures.

In integration tests, `@Transactional` and `@DataJpaTest` normally roll back database state without removing Elasticsearch documents. Use unique IDs, dedicated test indices, or `testRunId`, record IDs before issuing requests, and clean up via explicit deletes or index lifecycles. When testing `AFTER_COMMIT` listeners, ensure tests actually commit; when durable post-commit delivery is required, use an outbox or CDC rather than relying solely on in-memory application events. For production synchronization, design idempotency, versioning, retries, DLQs, compensation, and reconciliation to handle duplicates, timeouts, and drift. Always inspect each store's state independently after failures—never treat a successful database rollback as evidence that Elasticsearch rolled back too.
