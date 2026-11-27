# Rollback, Checked Exceptions, and rollbackFor

## 1. Why Can Checked Exceptions Still Allow Data to Commit?

When a Spring service executes multiple write operations within the same transaction, we usually want all operations to succeed together or be undone together. For example, a goods receipt use case might:

1. Create a receipt header.
2. Add line items to the receipt.
3. Update inventory quantities.
4. Write an audit record.

If the third or fourth step fails, the earlier changes may need to roll back so the database does not store a half-finished state.

Spring transactions have a default rollback rule. This rule distinguishes **unchecked exceptions** from **checked exceptions**:

- For **RuntimeException** and **Error**, Spring marks the transaction for rollback by default.
- For checked exceptions, Spring does not roll back by default merely because the exception is thrown. The transaction may commit if the exception exits a transactional method without a matching rollback rule.

This often surprises developers when an application defines business exceptions by extending **Exception**. A business error can escape the service, the caller receives the error, yet earlier SQL statements are still committed.

The **rollbackFor** attribute lets you explicitly declare which exception types must cause a transaction rollback. This lesson explains the default rules, how to configure **rollbackFor** and **noRollbackFor**, the impact of catching exceptions, how to test rollback policies, and how to choose an appropriate policy for Spring Data JDBC.

## 2. Checked and Unchecked Exceptions in Java

Java divides exceptions into two common groups:

| Group | Characteristics | Examples |
| --- | --- | --- |
| Checked exception | An exception that must be declared with throws or handled with try/catch under Java compiler rules | IOException, business exceptions directly extending Exception |
| Unchecked exception | Extends RuntimeException; not required to be declared or caught | IllegalArgumentException, IllegalStateException, NullPointerException |

Checked exception example:

~~~java
public class ImportValidationException extends Exception {

    public ImportValidationException(String message) {
        super(message);
    }
}
~~~

Unchecked exception example:

~~~java
public class InsufficientStockException extends RuntimeException {

    public InsufficientStockException(String message) {
        super(message);
    }
}
~~~

An exception does not become checked or unchecked based on its business meaning or name. The classification is determined by its superclass in the class hierarchy:

- Extends Exception without extending RuntimeException: checked.
- Extends RuntimeException: unchecked.

## 3. Spring's Default Rollback Rules

Under Spring's standard default transaction configuration:

| Exception escaping transactional method | Default outcome |
| --- | --- |
| RuntimeException | Rollback |
| Subclass of RuntimeException | Rollback |
| Error | Rollback |
| Checked exception, e.g. IOException | Does not roll back automatically |
| Subclass of checked exception | Does not roll back automatically |

Example:

~~~java
@Transactional
public void createOrder() {
    orders.save(new PurchaseOrder(...));

    throw new IllegalStateException("Cannot continue");
}
~~~

IllegalStateException is an unchecked exception. When it exits the method through the transaction interceptor, Spring rolls back the transaction by default.

Conversely:

~~~java
@Transactional
public void importOrder() throws ImportValidationException {
    orders.save(new PurchaseOrder(...));

    throw new ImportValidationException("Invalid import row");
}
~~~

ImportValidationException is a checked exception. Without an additional rollback rule, Spring does not roll back by default solely due to this exception. Depending on the transaction manager and transaction state, prior changes may be committed even though the caller receives the exception.

This is why exception types and rollback policies must be designed together. Do not assume all exceptions share the same behavior.

## 4. Using rollbackFor to Roll Back on Checked Exceptions

The rollbackFor attribute accepts one or more exception classes. When a matching exception exits the transactional method, Spring marks the transaction for rollback.

Example:

~~~java
@Transactional(rollbackFor = ImportValidationException.class)
public void importOrder() throws ImportValidationException {
    orders.save(new PurchaseOrder(...));
    inventory.increase(...);

    throw new ImportValidationException("Invalid import row");
}
~~~

In this example:

1. The repository saves the order.
2. Another operation updates inventory.
3. The checked exception is thrown.
4. The transaction interceptor receives the exception and applies the rollback rule.
5. Both database changes in the transaction are rolled back.

You can declare multiple types:

~~~java
@Transactional(
        rollbackFor = {
                ImportValidationException.class,
                IOException.class
        }
)
public void importFile() throws ImportValidationException, IOException {
    // Read and write data.
}
~~~

In Spring, you can use rollbackFor = Exception.class if the use case's policy is that every exception must roll back:

~~~java
@Transactional(rollbackFor = Exception.class)
public void process() throws Exception {
    // All checked exceptions under Exception and unchecked exceptions
    // are covered by this rule.
}
~~~

However, do not add rollbackFor = Exception.class out of habit to every method. Choose the policy according to business semantics: some checked exceptions simply represent an expected outcome where the application still intends to commit valid partial state.

## 5. Spring Data JDBC Example: Goods Receipt Import and Rollback on Validation Failure

Suppose a goods receipt use case must save the receipt and update inventory. If line item data is invalid, both changes must be cancelled.

### 5.1. Defining the Checked Exception

~~~java
public class ImportValidationException extends Exception {

    public ImportValidationException(String message) {
        super(message);
    }
}
~~~

### 5.2. Repositories

~~~java
public interface GoodsReceiptRepository
        extends CrudRepository<GoodsReceipt, Long> {
}

public interface InventoryRepository
        extends CrudRepository<Inventory, Long> {
}
~~~

### 5.3. Service with rollbackFor

~~~java
@Service
public class GoodsReceiptService {

    private final GoodsReceiptRepository receipts;
    private final InventoryRepository inventory;

    public GoodsReceiptService(
            GoodsReceiptRepository receipts,
            InventoryRepository inventory
    ) {
        this.receipts = receipts;
        this.inventory = inventory;
    }

    @Transactional(rollbackFor = ImportValidationException.class)
    public Long importReceipt(GoodsReceipt receipt)
            throws ImportValidationException {

        GoodsReceipt saved = receipts.save(receipt);

        for (ReceiptLine line : saved.lines()) {
            if (line.quantity() <= 0) {
                throw new ImportValidationException(
                        "Quantity must be positive for SKU " + line.sku()
                );
            }

            Inventory stock = inventory.findById(line.inventoryId())
                    .orElseThrow();

            inventory.save(stock.increase(line.quantity()));
        }

        return saved.id();
    }
}
~~~

This example illustrates the transaction boundary; the model and increase method must be defined according to your application domain. If the exception is thrown after saving the receipt or updating several lines, rollbackFor undoes those operations within the same transaction.

### 5.4. Why Must the Transaction Be Placed on the Service?

A repository only knows about its own persistence operations. Only the service knows that the goods receipt workflow consists of multiple steps and which steps must succeed together.

If transactions are placed separately on each repository method, each call may finish and commit independently when there is no outer transaction. Then an error on the third line item cannot undo the steps committed earlier.

Placing @Transactional on the service lets all repository methods participate in the same transaction when they use the same DataSource and an appropriate transaction manager.

## 6. rollbackFor and noRollbackFor

Spring provides two configuration directions:

- **rollbackFor:** matching exceptions must trigger rollback.
- **noRollbackFor:** matching exceptions do not trigger rollback under that rule.

Example:

~~~java
@Transactional(
        rollbackFor = ImportValidationException.class,
        noRollbackFor = DuplicateReferenceException.class
)
public void importReceipt() throws ImportValidationException {
    // Perform write operations.
}
~~~

Here, ImportValidationException requires rollback, whereas DuplicateReferenceException is configured not to roll back. noRollbackFor should generally only be used when the application intentionally commits state even though a specific exception is thrown.

Example of a use case recording a processing attempt:

~~~java
@Transactional(noRollbackFor = AlreadyProcessedException.class)
public void recordAttempt(Command command) throws AlreadyProcessedException {
    attempts.save(Attempt.started(command.id()));

    if (alreadyProcessed(command.id())) {
        throw new AlreadyProcessedException(command.id());
    }
}
~~~

This is merely an illustration of policy semantics. If an exception indicates the business item was already processed, consider whether saving the attempt before checking is actually needed; sometimes checking first and returning a normal result is clearer than using exceptions to control commits.

### 6.1. Specific Rules vs. General Rules

If multiple rules match the same exception, Spring applies the most specific rule—that is, the rule whose exception type is closest to the actual exception thrown.

Example:

~~~java
@Transactional(
        rollbackFor = Exception.class,
        noRollbackFor = DuplicateReferenceException.class
)
public void execute() throws Exception {
    // ...
}
~~~

The specific noRollbackFor rule for DuplicateReferenceException overrides the general rollbackFor = Exception.class rule for that exception. Other checked exceptions remain covered by the general rule.

Do not declare overlapping rules without a clear reason. A simple, specific policy is usually easier to read and test.

## 7. rollbackForClassName and Why Class Types Should Be Preferred

@Transactional also offers class-name attributes such as rollbackForClassName and noRollbackForClassName. These allow declaring rules using exception names as strings.

Example:

~~~java
@Transactional(rollbackForClassName = "com.example.ImportValidationException")
public void importData() throws ImportValidationException {
    // ...
}
~~~

In most Java code, prefer:

~~~java
@Transactional(rollbackFor = ImportValidationException.class)
~~~

Reasons:

- The compiler type-checks the class reference.
- Refactoring packages/classes is safer.
- Eliminates typos in string names.
- Easier to read with better IDE navigation support.

Class-name rules may perform pattern matching against exception names. Matching is not necessarily an exact full-name equality check; a broad pattern can match unintended exceptions. Therefore, avoid short strings like Exception or Validation as rules unless you understand the matching scope.

## 8. What Happens When Catching an Exception Inside a Transactional Method?

Rollback rules apply when the transaction interceptor observes an exception escaping the transactional invocation. If code catches the exception and does not rethrow it, the interceptor may simply see the method finish normally.

Example:

~~~java
@Transactional(rollbackFor = ImportValidationException.class)
public void importData() {
    receipts.save(new GoodsReceipt(...));

    try {
        validate();
    } catch (ImportValidationException ex) {
        log.warn("Import rejected: {}", ex.getMessage());
        // Do not rethrow the exception.
    }
}
~~~

Here, ImportValidationException is caught and never leaves the method. Simply declaring rollbackFor does not mean Spring will roll back automatically when code swallows the exception. If the method completes normally and the transaction has not been marked rollback-only, the transaction may commit.

### 8.1. Approach 1: Rethrow the Exception

If the error must cancel the entire use case, the clearest approach is to let the exception propagate out:

~~~java
@Transactional(rollbackFor = ImportValidationException.class)
public void importData() throws ImportValidationException {
    receipts.save(new GoodsReceipt(...));
    validate(); // Exception escapes the method.
}
~~~

### 8.2. Approach 2: Mark Rollback-Only

If you need to catch the exception for logging or transforming the return value, while still rolling back:

~~~java
@Transactional
public ImportResult importData() {
    receipts.save(new GoodsReceipt(...));

    try {
        validate();
        return ImportResult.success();
    } catch (ImportValidationException ex) {
        log.warn("Import rejected", ex);
        TransactionAspectSupport.currentTransactionStatus()
                .setRollbackOnly();
        return ImportResult.rejected(ex.getMessage());
    }
}
~~~

setRollbackOnly() marks the current transaction to roll back upon completion. This approach fits when the service contract prefers returning a result object instead of throwing an exception, yet database changes must still be discarded.

To use this API, import:

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;
~~~

Only call currentTransactionStatus() within a Spring-managed transaction scope. If no active transaction exists, the call may fail.

### 8.3. Approach 3: Wrap a Checked Exception into an Unchecked Exception

You can wrap a checked exception in a runtime exception:

~~~java
try {
    validate();
} catch (ImportValidationException ex) {
    throw new IllegalStateException("Import failed", ex);
}
~~~

Because IllegalStateException is unchecked, default rollback applies when it exits the transactional method. However, only wrap when the new exception type accurately expresses the error abstraction. Do not turn every business error into a RuntimeException merely to avoid configuring rollback rules.

## 9. Inner Transactions, REQUIRED, and UnexpectedRollbackException

A subtle case occurs when one transactional method calls another transactional method with the default REQUIRED propagation.

~~~java
@Service
public class ImportCoordinator {

    private final ImportWorker worker;

    public ImportCoordinator(ImportWorker worker) {
        this.worker = worker;
    }

    @Transactional
    public void run() {
        try {
            worker.processOne();
        } catch (IllegalStateException ex) {
            log.warn("One item failed", ex);
        }

        // Caller may want to continue, but the transaction is already rollback-only.
    }
}

@Service
public class ImportWorker {

    @Transactional
    public void processOne() {
        throw new IllegalStateException("Cannot process item");
    }
}
~~~

If processOne() is called through a proxy and joins the existing transaction, the unchecked exception can mark the shared transaction rollback-only. ImportCoordinator catches the exception, yet the rollback-only flag remains set. When the outer transaction finishes, Spring may throw UnexpectedRollbackException instead of committing.

Points to remember:

- Catching an exception does not clear the rollback-only flag.
- REQUIRED shares one transaction, so a failure in a participant can affect the outer transaction.
- If each item must commit/roll back independently, design separate transaction boundaries—such as a separate bean processing each item with REQUIRES_NEW—while understanding its cost and semantics.

Do not use REQUIRES_NEW just to avoid UnexpectedRollbackException. Determine whether the business truly allows one item to commit independently of the others.

## 10. How Does Propagation Affect Rollback?

| Propagation | General effect |
| --- | --- |
| REQUIRED | Joins the current transaction or creates a new one. Rollback-only in the shared transaction can cause the whole use case to roll back. |
| REQUIRES_NEW | Uses an independent transaction. The inner transaction can commit even if the outer transaction rolls back, and vice versa. |
| NESTED | Can use a savepoint if supported by the transaction manager; rolling back the nested scope does not necessarily abort the entire outer transaction. |
| SUPPORTS | Joins a transaction if one exists; otherwise runs without a transaction. |
| MANDATORY | Requires the caller to have an active transaction; fails if none exists. |
| NOT_SUPPORTED | Suspends any existing transaction and executes non-transactionally. |
| NEVER | Disallows an active current transaction. |

Independent audit example:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordFailureAttempt(ImportAttempt attempt) {
    attempts.save(attempt);
}
~~~

An audit attempt may need to persist even when the main business transaction rolls back. However, if the audit signifies that the business action succeeded, an independent commit can produce misleading data. The decision must rest on data semantics.

## 11. Database Exceptions and Checked Exceptions Are Not the Same

When using Spring JDBC, errors from JDBC are typically translated into Spring's exception hierarchy, such as subclasses of DataAccessException. DataAccessException is an unchecked exception.

Example:

~~~java
@Transactional
public void saveCustomer(Customer customer) {
    customers.save(customer);
    // Constraint errors from Spring JDBC are typically translated into
    // a DataAccessException, which extends RuntimeException.
}
~~~

Therefore, many common persistence errors already trigger rollback under default rules. rollbackFor is more often needed for application-defined checked exceptions, file reading errors, validation errors, or external library APIs.

Do not catch a DataAccessException, log it, and continue as if the transaction can still safely commit. The database or transaction manager may have already marked the transaction rollback-only, especially when the error occurs in a participating transaction.

## 12. Choosing Checked vs. Unchecked Exceptions for Business Errors?

Both can be reasonable. Choose based on the API contract and how callers handle failures:

| Situation | Potentially suitable design |
| --- | --- |
| Expected input/domain failure that callers handle as a business outcome | Checked exception or explicit result type |
| Illegal programming state or broken invariant | Unchecked exception |
| I/O error from a library | Original checked exception; configure rollback via rollbackFor if needed |
| Persistence failure from Spring JDBC | Typically unchecked DataAccessException |
| A business failure that must abort the entire transaction | Choose the exception and configure rollback rules explicitly |

Do not choose checked exceptions solely to force callers to handle them; nor choose unchecked solely to make transactions roll back automatically. Exception types should express the application layer's contract, while rollback policies express the desired effect on the transaction.

## 13. Testing rollbackFor

An integration test should verify actual database state after the transactional method throws a checked exception. Crucially, read the data back after the service transaction has finished.

### 13.1. Illustrative Service

~~~java
public class ImportRejectedException extends Exception {
    public ImportRejectedException(String message) {
        super(message);
    }
}

@Service
public class DemoImportService {

    private final JdbcTemplate jdbc;

    public DemoImportService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void insertThenThrowWithoutRule() throws ImportRejectedException {
        jdbc.update(
                "INSERT INTO import_marker(marker) VALUES (?)",
                "default-rule"
        );
        throw new ImportRejectedException("Rejected");
    }

    @Transactional(rollbackFor = ImportRejectedException.class)
    public void insertThenThrowWithRule() throws ImportRejectedException {
        jdbc.update(
                "INSERT INTO import_marker(marker) VALUES (?)",
                "rollback-rule"
        );
        throw new ImportRejectedException("Rejected");
    }
}
~~~

Assume the import_marker table has been created and each test uses isolated data.

### 13.2. Testing Default Behavior and rollbackFor

~~~java
@SpringBootTest
class RollbackRuleIntegrationTest {

    @Autowired
    DemoImportService service;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void checkedExceptionDoesNotRollbackByDefault() {
        assertThatThrownBy(service::insertThenThrowWithoutRule)
                .isInstanceOf(ImportRejectedException.class);

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM import_marker WHERE marker = ?",
                Integer.class,
                "default-rule"
        );

        assertThat(count).isEqualTo(1);
    }

    @Test
    void rollbackForRollsBackCheckedException() {
        assertThatThrownBy(service::insertThenThrowWithRule)
                .isInstanceOf(ImportRejectedException.class);

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM import_marker WHERE marker = ?",
                Integer.class,
                "rollback-rule"
        );

        assertThat(count).isZero();
    }
}
~~~

This example illustrates Spring's default transaction behavior; tests require AssertJ/JUnit dependencies, the schema, and your project's actual transaction manager. Neither test should be wrapped in an outer test transaction if the goal is to observe the service's commit/rollback behavior. If the test class or method carries @Transactional, the test transaction can alter how results and commit timing are observed.

### 13.3. Additional Checks

- The exception genuinely escapes past the transactional proxy.
- The method is invoked through a Spring bean/proxy, not self-invocation.
- Repositories and JdbcTemplate share the same DataSource/transaction manager when a shared transaction is needed.
- No catch block swallows the exception.
- No noRollbackFor or more specific rule alters the outcome.
- The test reads data back after the service transaction completes.

## 14. Common Mistakes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Checked exception escapes, yet data still persists | Spring does not roll back checked exceptions by default | Add rollbackFor for the exception type that must roll back. |
| rollbackFor is declared, yet data still commits | Exception was caught and swallowed before escaping the transactional method | Rethrow the exception or mark rollback-only. |
| rollbackFor = Exception.class, yet one error still does not roll back | A more specific noRollbackFor rule exists or the transaction already ended before the error | Check rule precedence and transaction boundaries. |
| Inner method fails, outer method catches error, yet commit fails | The shared transaction was already marked rollback-only | Understand REQUIRED propagation; use independent transactions only if business allows. |
| UnexpectedRollbackException at end of method | A participant marked the shared transaction rollback-only | Find the original exception and review nested transactional boundaries. |
| I/O error does not trigger rollback | Checked exception has no rollback rule | Declare rollbackFor = IOException.class or a specific exception type. |
| Database exception rolls back even without rollbackFor | Spring JDBC typically translates errors into unchecked DataAccessException | This is default behavior; do not swallow errors when rollback is required. |
| Tests behave differently from production | Test has an enclosing transaction or uses a different database | Test service transactions independently on a database close to production. |

## 15. Process for Designing a Rollback Policy

When a service can throw exceptions, determine:

1. **Is the exception checked or unchecked?** Inspect the class inheritance hierarchy.
2. **Does the exception escape the transactional method?** Check catch/rethrow paths and proxies.
3. **If the exception occurs, should already-written data be kept or discarded?** Decide based on business rules.
4. **Do default rules satisfy this?** RuntimeException and Error roll back by default; checked exceptions do not.
5. **Is rollbackFor needed?** Prefer explicit class types.
6. **Is noRollbackFor needed?** Declare only when committing on that exception is intentional.
7. **Are there participating/nested transactions?** Check propagation and rollback-only behavior.
8. **Are there operations outside the database?** @Transactional does not automatically roll back files, emails, HTTP calls, or message brokers.
9. **Have post-commit/rollback states been tested?** Read data back after the transaction actually ends.

## 16. Practice Exercises

**Exercise 1 — Observe Default Behavior.** Create a checked exception extending Exception. Inside a @Transactional method, insert a row and throw the exception. Read the row back after the method completes and explain the result.

**Exercise 2 — Add rollbackFor.** Add rollbackFor = YourCheckedException.class to the method. Re-run the test and verify the inserted row is rolled back.

**Exercise 3 — Multiple Rollback Rules.** Declare rollbackFor = Exception.class and noRollbackFor for one specific exception. Test both the specific exception and another checked exception.

**Exercise 4 — Catching Exceptions.** Catch a checked exception inside a transactional method and return normally. Observe the data, then try adding setRollbackOnly().

**Exercise 5 — Nested REQUIRED.** Create two service beans, both using @Transactional. Have the inner service throw a runtime exception and the outer service catch it. Observe UnexpectedRollbackException.

**Exercise 6 — REQUIRES_NEW.** Try writing an audit attempt in a separate transaction, then force the outer transaction to roll back. Explain which data remains and why.

**Exercise 7 — I/O Failure.** Read a file inside a database-writing use case. When IOException occurs, configure the appropriate rollback rule and verify the database does not store partial data.

## 17. Key Takeaways

Spring rolls back by default when a RuntimeException or Error exits a transactional method. Checked exceptions such as IOException or business exceptions extending Exception do not automatically trigger rollback. If a checked exception must abort the use case's database operations, declare rollbackFor for the appropriate exception type.

rollbackFor takes effect only when the exception reaches the transaction interceptor or the transaction is marked rollback-only. If code catches and swallows the exception, the method can complete normally and the transaction will commit. When methods participate in the same transaction via REQUIRED, a failure in one participant can mark the shared transaction rollback-only even if the outer caller catches the exception.

Choose exception types based on the application's contract, choose rollback rules based on business semantics, and test database state after the transaction ends. Avoid applying one overly broad configuration to every method when different use cases have different commit/rollback policies.

### References

- [Spring Framework – Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework – @Transactional Annotation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework – Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Java 21 – Exception](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Exception.html)
- [Java 21 – RuntimeException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/RuntimeException.html)
