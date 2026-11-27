# Managing Test Data and Initial State

## Learning Objectives

After this lesson, learners will be able to:

- Explain why test outcomes depend on source code, data, and system state alike.
- Distinguish fixtures, seed data, test data factories, snapshots, and runtime-generated data.
- Design reproducible initial states for unit tests, integration tests, and end-to-end tests.
- Isolate data across tests, jobs, branches, and environments to prevent overwrites or execution-order dependencies.
- Choose synthetic, mocked/fake, or anonymized data according to security requirements.
- Manage the data lifecycle from initialization, usage, and verification to cleanup.
- Integrate state preparation and restoration into CI/CD pipelines so results remain stable and debuggable.

## 1. Why Data and Initial State Matter

A test does not inspect source code alone. It tests how software behaves when receiving inputs and interacting with the current state of the system.

The same commit can yield different results if:

- The database contains different data.
- A test depends on a record created by a preceding test.
- A queue still holds messages from a previous run.
- A cache contains stale values.
- A feature flag or environment configuration was altered.
- A test account has been locked or expired.
- The system clock, timezone, or time-sensitive data is not pinned.
- Another pipeline is updating the same resource while the test runs.

Therefore, a test result is only meaningful when you know **which code was tested, which data was used, and what state the system started from**.

Test data management is the preparation, provisioning, protection, tracking, and cleanup of data used for testing. Initial state management is broader: it defines the preconditions the system must satisfy before a test starts, including data, configuration, dependent service states, and mutable resources.

Think of it this way:

> Reliable test results require deterministic inputs, a deterministic initial state, observable behavior, and controlled teardown.

Without managing these factors, tests can fail intermittently, pass falsely, or succeed only in one specific environment.

## 2. Distinguishing Test Data from Initial State

These two concepts are related but not identical.

**Test data** consists of the values and records read, created, updated, or deleted by a test—for example, customer accounts, products, orders, user permissions, simulated payment records, or messages in a queue.

**Initial state (baseline state)** is the overall state of all relevant components before the test begins. It can include:

- Database records.
- Cache contents.
- Messages in queues or event logs.
- Files in storage.
- Account statuses and login sessions.
- Feature flags and configuration.
- Schema and migration versions.
- State of external mocks or sandboxes.
- System time, timezone, and reference data.

For instance, an order placement test may require an active customer, an in-stock product, a sandbox payment method, and an unchecked-out cart. Creating the customer record alone is not enough if the product is out of stock or the payment sandbox is in an error state.

| Aspect | Test data | Initial state |
|---|---|---|
| Scope | Records and values used by the test | All preconditions required for the test |
| Examples | Customer, product, order | Active customer, sufficient stock, clean queue |
| Preparation | Fixtures, seeds, factories, APIs | Resets, migrations, configs, service setup |
| Verification | Queries or API calls inspecting records | Health checks and state assertions |
| Restoration | Deleting or updating test records | Resetting or recreating the baseline |

A dataset can be correct while the baseline is still wrong. For example, a test creates a valid order, yet an old event sitting in a queue causes the consumer to misprocess it. Conversely, an environment may have a clean baseline while lacking the records needed to exercise the business flow.

## 3. Ways to Create and Manage Test Data

No single technique fits every test type. Choose an approach based on speed, isolation, realism, and preparation cost.

### 3.1. Fixtures

A fixture is a pre-built set of data or state prepared for a test or group of tests to use.

For example, a fixture might contain:

- An active customer.
- A product with stock.
- An order in pending status.
- An account with a specific role.
- A sample response from an external service.

Fixtures work well when data is small, stable, and easy to understand. They let tests focus on the behavior under verification instead of recreating many related objects repeatedly.

Drawbacks arise when fixtures grow too large or are shared across many tests. When one test mutates a fixture, subsequent tests may observe altered state. Hard-to-maintain fixtures can also hide data relationships that no longer match the current model.

Keep fixtures minimal, name them by purpose, and create separate copies for tests that mutate data.

### 3.2. Seed Data

Seed data is foundational data loaded into an environment so the application or tests can operate.

Examples:

- Country and currency catalogs.
- Default roles and permissions.
- Standard product categories.
- Status codes or reference configurations.
- Minimum data needed for a demo or integration test environment.

Seed data typically outlives a single test. Clearly separate system seed data from test-specific seed data.

Seeds should be idempotent: running them again must not create duplicate records or unintended mutations. Use natural keys or fixed identifiers to identify records. Avoid seed scripts that wipe all data if they could accidentally be invoked against a non-test environment.

### 3.3. Test Data Factories

Factories construct data on demand for each test. The test declares only the attributes that matter, while the factory supplies valid defaults.

For instance, a factory creates a new customer with a unique email and active status. A test can override attributes to check a locked account, missing address, or existing transaction history.

Factories fit well when:

- Each test needs its own distinct object.
- Data involves complex relationships.
- Valid and invalid variants must be produced quickly.
- Tests run concurrently and must not share IDs.

Factories must generate meaningful data that respects business invariants. Never construct records that could not exist in the real system, unless the test intentionally checks invalid input at an appropriate boundary.

### 3.4. Runtime-Generated Data

Some tests create data directly via APIs or repositories right before executing the action under test. This makes tests self-describing and reduces reliance on shared datasets.

Example:

1. Create a customer through a test API.
2. Create a product with a specific stock count.
3. Submit an order creation request.
4. Assert order status and remaining stock count.
5. Delete the data or destroy test resources.

Runtime-generated data suits integration and end-to-end tests, though creation time, dependency order, and cleanup must be controlled. If setup becomes overly verbose, extract shared setup into helpers or factories to keep tests readable.

### 3.5. Snapshots or Environment Clones

A snapshot captures state at a point in time. Database or volume snapshots can quickly spin up test environments loaded with relatively large datasets.

This helps when:

- The dataset has complex structure.
- Seeding from scratch is too slow.
- Migrations need testing against state close to a specific schema version.
- Reproducing a bug that depends on specific data state.

Snapshots require clear versioning, provenance, and protection policies. If a snapshot contains production data, it may hold personal information or secrets. Anonymize before use, restrict access permissions, and enforce retention limits. Snapshots can also grow stale as schemas or seeds evolve.

## 4. Selecting Data by Test Type

Different test layers have different data and baseline needs.

| Test type | Appropriate data | Baseline to control |
|---|---|---|
| Unit test | Small objects, in-memory fixtures, factories | Object state and clock fixed |
| Component test | Local emulated database or service | Schema, minimal seed, mock/stub state |
| Integration test | Real records and services in an isolated environment | Database, queue, cache, dependency versions |
| Contract test | Sample requests/responses and schemas | Contract version, provider/consumer expectations |
| End-to-end test | Realistic business data | Full flow, accounts, feature flags, external state |
| Performance test | Large dataset with realistic distribution | Data size, cache state, concurrency, resources |
| Migration test | Pre-migration snapshot or representative dataset | Source schema, app version, and backup |

Do not reuse one massive dataset for every test. Unit tests need to be fast and focused. Performance tests need sufficiently large datasets with realistic distributions. End-to-end tests need traceable business data isolated so tests do not interfere with one another.

Likewise, do not mock away every dependency. Mocks control inputs and faults in unit/component tests, yet they do not prove real integration works. Critical interactions with databases, queues, or APIs require tests against real components or equivalent environments.

## 5. Designing a Reproducible Baseline

A solid baseline needs a clear definition, creation mechanism, and verification step.

### 5.1. Define Invariants

An invariant is a condition that must hold before tests begin.

Example for a checkout flow:

- Customer exists and is active.
- Product exists with sufficient stock.
- Cart belongs to that customer and has not checked out.
- Payment provider is in sandbox mode.
- The queue contains no leftover events from prior runs within the active scope.
- The checkout feature flag is enabled.
- The database schema matches the version expected by the tests.

Express invariants as automated checks rather than leaving them solely in documentation.

### 5.2. Build Baselines from Versioned Code or Data

Schema definitions, seeds, and fixtures should live in the repository or a governed source. Every baseline change should be reviewed like source code.

Record metadata such as:

- Schema or migration version.
- Seed bundle version.
- Commit SHA of the test suite.
- Database or service image versions.
- Environment configuration.
- Dataset ID or snapshot version.

This metadata clarifies whether two test runs started from identical conditions.

### 5.3. Verify the Baseline Before Running Tests

After setup, run a readiness check confirming:

- The database is reachable and at the expected schema version.
- Required seed data exists.
- Queues or topics are properly provisioned.
- Dependent services are ready.
- Test accounts hold the right permissions.
- Feature flags and settings match expected values.

If the baseline check fails, stop during setup with a clear message. Never proceed to run hundreds of tests and fail across dozens of suites due to one environment setup error.

## 6. Isolating Data Across Tests and Pipelines

One of the most common causes of flaky tests is multiple tests or pipelines operating on shared data simultaneously.

For example, two tests share customer ID 1001. Test A sets the customer inactive while Test B tests checkout. Test B's outcome depends on timing between the two tests.

Several isolation strategies exist:

### 6.1. Per-Test Data

Each test creates entities with unique IDs, such as UUIDs or namespaced identifiers. Tests only read and modify records they created.

This works well when record counts are small and the system creates data quickly.

### 6.2. Per-Job Schemas or Databases

Each CI job receives an independent schema or database. Tests never write into another job's data space.

This fits integration tests with heavy database operations. Manage quotas, schema naming, permissions, and post-job cleanup.

### 6.3. Dedicated Tenants or Namespaces

In multi-tenant apps, each test can use a separate tenant. In Kubernetes or namespace-aware services, provision a namespace per run ID or pull request.

However, an application namespace does not automatically isolate databases, queues, object storage, or external services. Check each dependency and provision isolated data scopes accordingly.

### 6.4. Transaction Rollbacks

A test can run inside a transaction and roll back upon completion. This is fast and effective for straightforward database tests.

However, transaction rollbacks do not cover all state:

- Message queue writes often fall outside database transactions.
- External API calls cannot automatically roll back.
- Some tests need multiple connections or separate processes reading committed data.
- DDL or transaction behavior differs across database engines.
- Tests verifying transaction commits or isolation levels cannot sit wholly inside a test-harness transaction.

Apply transaction rollbacks where appropriate and maintain separate cleanup for out-of-transaction resources.

### 6.5. Ephemeral Environments

For large integration suites, spin up ephemeral environments per pull request or pipeline. The environment follows a lifecycle from creation, deployment, seeding, and test execution through teardown.

This eliminates cross-branch contention and enables parallel runs, though cost, quotas, provisioning time, and resource cleanup must be managed.

## 7. Data Must Be Independent of Test Execution Order

A stable test suite must produce identical results whether tests run individually, in groups, or in different orders.

Signs of order-dependent tests:

- Test B only passes after Test A runs.
- Running a test a second time fails because records already exist.
- Tests only pass when run sequentially.
- Tests fail randomly when parallel execution is enabled.
- Tests share a static variable or a single database record.

To eliminate order dependencies:

1. Have each test prepare its own required data.
2. Never rely on side effects from another test.
3. Use unique IDs or per-test namespaces.
4. Avoid mutable global state unless explicitly reset.
5. Clean up in `finally` blocks or appropriate lifecycle hooks.
6. Run tests in randomized order periodically to expose hidden coupling.
7. Run controlled parallel executions to surface shared-resource contention.

Independent tests simplify retries and debugging. If a test only passes inside a long sequence, re-examine its setup boundaries and data dependencies.

## 8. Synthetic, Mocked/Fake, and Anonymized Data

Production data accurately reflects business distributions and relationships, yet it typically contains personal information, secrets, or sensitive records. Never copy raw production data into CI or development environments.

Three common alternatives exist:

**Synthetic data:** artificially generated according to target schemas and distributions—for example, generating thousands of customers with varied ages, addresses, orders, and statuses. Synthetic data controls content and avoids exposing real information.

**Mocked/fake data:** crafted to simulate a specific scenario or response—for example, a payment provider returning success, decline, or timeout. Fake data is useful for testing error branches and hard-to-reproduce conditions.

**Masked/anonymized data:** derived from real sources with identifying fields transformed or stripped per policy. Evaluate re-identification risk and preserve referential integrity. Merely changing names or emails is rarely sufficient anonymization.

| Approach | Advantages | Limitations |
|---|---|---|
| Synthetic | Full content control, safer for sensitive data | May not capture all real-world distributions |
| Mock/fake | Fast, reproduces specific errors and responses | May not reflect real integration behavior |
| Masked/anonymized | Preserves portions of real structure and distribution | Risk of re-identification if processed improperly |

Establish governance around data source approvals, access controls, masking, validation, and retention periods. Never place production data or unprotected snapshots into shared caches, logs, or public artifacts.

## 9. Managing Time, Randomness, and Volatile Data

Some tests become unstable because they depend on wall-clock time or unseeded randomness.

Examples:

- A test checking subscription expiration using the real system clock.
- A test generating random emails without logging the value for debugging.
- A test computing dates in the runner's local timezone.
- A test comparing timestamps across systems with differing precision.

Countermeasures:

- Inject a clock or time provider so tests pin time deterministically.
- Store timestamps in UTC and convert timezones only at display boundaries.
- Pin random generator seeds when failures must be reproducible.
- Log seeds or generated values in test output.
- Apply appropriate tolerances when comparing timestamps or floating-point numbers.
- Avoid depending on when a runner executes the job.

Do not force every test to share one fixed seed forever. Fixed seeds aid reproduction, whereas property-based tests should explore multiple seeds. Whenever a failure occurs, log the seed so the exact case can be replayed.

## 10. Cleanup and Post-Test State Restoration

Data preparation is only half the lifecycle. Tests must finish without polluting subsequent runs.

A cleanup strategy should specify:

- Which data the test owns.
- Which resources are permitted to be deleted.
- Whether cleanup runs per test, per suite, or on environment teardown.
- How to handle test timeouts or killed runners.
- How to detect and purge orphaned resources.

Never delete data using overly broad rules like "delete all records created today." Tag records with a test run ID or dedicated tenant, and delete only resources within that scope.

Use TTLs or janitor jobs to reap abandoned ephemeral environments and leftover records. Janitors should check ownership, expiration time, and resource state before deleting.

Some tests inspect data after asynchronous processing, so cleanup must happen after assertions complete. For async flows, wait for consumer processing or verify final state before deleting related records.

If cleanup fails, log the remaining resources and alert the owner. Never silently ignore failed cleanup, as orphaned data can pollute future tests or inflate costs.

## 11. Example Test Data Lifecycle in CI

An integration test pipeline can follow this flow:

~~~mermaid
flowchart TD
    A["Start CI job"] --> B["Create test namespace / database"]
    B --> C["Apply schema migrations"]
    C --> D["Load versioned seed data"]
    D --> E["Readiness checks"]
    E --> F{"Baseline valid?"}
    F -- "No" --> X["Fail setup and log diagnostics"]
    F -- "Yes" --> G["Create per-test data"]
    G --> H["Run integration tests"]
    H --> I["Collect reports and logs"]
    I --> J["Clean up data and resources"]
    J --> K["Record CI outcome"]
    X --> J
~~~

A general logical configuration example:

~~~yaml
integration_test:
  environment:
    isolation_key: ci_run_id
    database: ephemeral
    queue_namespace: ci_run_id
    external_services: sandbox

  setup:
    - create_resources
    - apply_migrations
    - load_versioned_seed
    - verify_baseline

  test:
    - create_test_data_per_case
    - run_integration_suite
    - collect_reports

  cleanup:
    always:
      - delete_test_data_by_owner
      - destroy_ephemeral_resources
      - record_cleanup_result
~~~

This example only illustrates ordering and responsibilities. Concrete syntax must be mapped to your project's CI platform and test tooling. In particular, configure cleanup to execute even when tests fail or are cancelled, as supported by the runner.

## 12. Java Example: Data Setup and Cleanup in an Integration Test

An integration test must create isolated data, execute an action, and verify the result. The example below illustrates this concept using JUnit and hypothetical repositories:

~~~java
class OrderServiceIT {
    private final OrderRepository orders;
    private final CustomerRepository customers;
    private final OrderService orderService;

    @Test
    void createsOrderForActiveCustomer() {
        String runId = UUID.randomUUID().toString();
        String email = "ci-" + runId + "@example.test";

        Customer customer = customers.save(
            new Customer(email, CustomerStatus.ACTIVE)
        );

        try {
            Order order = orderService.createOrder(customer.getId());

            assertEquals(customer.getId(), order.getCustomerId());
            assertEquals(OrderStatus.PENDING, order.getStatus());
        } finally {
            orders.deleteByCustomerId(customer.getId());
            customers.deleteById(customer.getId());
        }
    }
}
~~~

Key points to notice:

- Data is created inside the test with a unique identifier.
- The email includes a run ID to minimize collisions during parallel runs.
- Assertions check business behavior.
- Cleanup deletes only the records created by this test.

This is a conceptual example. Real projects may use transactions, test fixtures, repository helpers, or containerized databases. If the service emits events or calls external systems, reset or clean up those states separately; deleting database rows does not recall published messages.

## 13. Testing Migrations Against Stateful Data

Migration tests must verify more than SQL statements running without syntax errors. They must confirm existing data transforms accurately and the application works with the new schema.

A migration test workflow can follow these steps:

1. Create a database from the old schema version.
2. Load a representative dataset containing edge cases and key relationships.
3. Record pre-migration invariants.
4. Run migrations using the exact tool used in the release pipeline.
5. Verify the new schema and post-migration data.
6. Run compatibility tests against the new application version.
7. Verify error cases or invalid-data handling.
8. Record execution duration and lock or resource impact.
9. Tear down the test database.

Migration datasets should include empty tables, large tables, null values, duplicates if allowed by the old schema, and key foreign-key relationships. A dataset containing only a few clean records can miss bugs triggered by real-world data.

For destructive or major transformations, verify backup/restore procedures and version compatibility between old and new application releases. Never assume rollback migrations always reverse every data change cleanly.

## 14. Integrating Data Management into CI/CD

A solid pipeline treats setup and cleanup as first-class steps of the test job rather than ad-hoc manual tasks outside the workflow.

| Stage | Activities | Transition condition |
|---|---|---|
| Provision | Create test database, namespace, queue, or services | Resources provisioned in isolation and ready |
| Initialize | Apply migrations and versioned seeds | Baseline passes invariants |
| Execute | Generate per-test data and run suite | Tests finish or hit timeout |
| Observe | Collect logs, reports, and resource states | Evidence tagged with run ID |
| Cleanup | Delete job-owned data and resources | Cleanup verified or error reported |
| Publish result | Archive test reports and metadata | Environment and dataset remain traceable |

Helpful practices include:

- Provision environments via IaC or containers so configurations are reviewable.
- Use pinned database image versions.
- Apply migrations identically to production workflows.
- Use versioned, deterministic seeds.
- Scope runtime data per job or test case.
- Restrict test job permissions strictly to its own resources.
- Set timeouts on setup, test execution, and cleanup.
- Always collect reports even when tests fail.
- Record run ID, commit, image version, schema version, and dataset version.
- Run an orphan-cleanup janitor job when runner cleanup fails to finish.

Never grant integration tests access to production databases. When realistic data structure is required, use sanitized datasets loaded into isolated test environments.

## 15. Common Issues and How to Fix Them

| Symptom | Possible cause | Improvement |
|---|---|---|
| Test passes alone, fails in full suite | Shared data or state | Per-test setup, reset, and cleanup |
| Test fails only when run in parallel | Colliding IDs, tenants, or resources | Per-job namespacing and concurrency control |
| Re-running test throws duplicate key error | Non-idempotent seed or setup | Use stable keys and controlled upserts |
| Test passes locally, fails in CI | Different baseline, timezone, or service | Standardize images, config, clock, and seeds |
| Integration test runtime varies wildly | Mutating shared datasets or contended resources | Isolate data and monitor resource usage |
| Queue delivers wrong event to test | Stale messages or background consumers | Dedicated queues, correlation IDs, and cleanup |
| Cleanup skipped when job cancelled | Missing finally/always cleanup or janitor | Use cleanup hooks and TTLs |
| Snapshot contains sensitive data | Uncontrolled production copy | Mask/anonymize or switch to synthetic data |
| Migration test uses only an empty DB | Unrepresentative dataset | Add edge cases and realistic relationships |
| Test depends on current time | Uncontrolled system clock | Inject clock and pin timezone |
| Test depends on execution order | Unreset side effects | Isolate tests and randomize execution order |
| Test resource count grows steadily | Incomplete cleanup | Tag with owner/run ID and run janitor jobs |

## 16. Test Data and State Design Checklist

Before adding a test suite to CI, verify:

- [ ] Data and state requirements for each test type are documented.
- [ ] Baselines can be recreated from versioned configuration or data.
- [ ] Readiness checks validate schemas, seeds, and service dependencies.
- [ ] Fixtures are small, purposeful, and protected from unintended shared edits.
- [ ] Factories generate valid records with unique IDs.
- [ ] Tests never depend on data created by other tests.
- [ ] Data is isolated across jobs, branches, and environments where required.
- [ ] Transaction rollbacks are used only for transactional state.
- [ ] Queues, caches, storage, and external services have dedicated reset strategies.
- [ ] Sensitive data is synthetic or anonymized per policy.
- [ ] Clocks, timezones, and random seeds are controlled when they affect outcomes.
- [ ] Cleanup runs on success, failure, and job cancellation.
- [ ] TTLs or janitor jobs reclaim orphaned resources.
- [ ] Test reports link to commit, run ID, schema version, and dataset version.
- [ ] Migrations are tested against representative datasets.
- [ ] Test jobs have zero access paths to production data.

## 17. Self-Assessment Exercise

A development team maintains integration tests for an order placement feature. Tests share a single staging database. Every run creates a customer with a fixed email, creates an order, and pushes a message onto a shared queue. When multiple pipelines run concurrently, tests occasionally read the wrong order or consume messages from previous runs. When tests fail, leftover records remain in the database.

Propose a redesigned setup:

1. Which components belong to test data, and which belong to baseline state?
2. Should you use fixtures, seeds, factories, or snapshots for each data type?
3. How can you isolate customers, orders, and messages across pipelines?
4. Can transaction rollbacks cover the entire flow? Why or why not?
5. Which baseline checks should run before tests start?
6. When should cleanup execute, and how should killed runners be handled?
7. How can a message be traced back to the exact test run?
8. Which data should be synthetic or anonymized?
9. Which metadata should be archived to reproduce a failed test run?

A solid design ensures every run owns isolated data and state boundaries, verifies its baseline before testing, tracks cleanup, and retains enough evidence to reproduce failures.

## Conclusion

Test data and initial state are essential preconditions for trustworthy test results. Fixtures, seeds, factories, runtime-generated data, and snapshots serve different needs. Baselines must be defined, recreated, and verified; data must be isolated, protected, and cleaned up across a well-defined lifecycle.

In CI/CD, each run should own isolated state and data at the appropriate boundary, paired with metadata linking back to the commit, schema, dataset, and environment. When setup and cleanup are automated, tests lose order dependencies, run safely in parallel, and become far easier to investigate when failures occur. As a result, teams gain consistent quality evidence before promoting changes to shared environments or production.
