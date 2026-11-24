# Testing Custom Components in Isolation

In Spring Batch, a `Job` is assembled from components such as `ItemReader`, `ItemProcessor`, `ItemWriter`, `Tasklet`, listeners, and supporting services. When writing custom components, test each component's logic in isolation before wiring it into a `Step` or `Job`. This pinpoints bugs at the exact boundary, keeps tests fast, and avoids booting the entire Batch infrastructure for every case.

Isolated testing focuses on a component's contract: what inputs it accepts, what outputs it returns, what state it saves, what exceptions it throws, and which dependencies it calls. Behaviors requiring `JobRepository`, a transaction manager, a scheduler, or a real database belong in dedicated integration tests.

## 1. Why Test Components in Isolation?

A `Step` may consist of multiple parts:

~~~text
Resource / Database / Queue
          |
          v
      ItemReader
          |
          v
    ItemProcessor
          |
          v
       ItemWriter
          |
          v
   Database / File / API
~~~

When a `Job` fails, the cause may lie in the reader, processor, writer, transaction, or `Step` configuration. Testing only the whole `Job` makes tests slow and obscures which component failed.

Unit testing individual components helps:

- Verify business logic with small, deterministic inputs.
- Cover edge cases such as nulls, empty inputs, malformed data, and exceptions.
- Confirm the reader stops at the right time without dropping items.
- Verify the processor filters or transforms items per contract.
- Verify the writer builds the right write operations and handles errors.
- Test the `ItemStream` lifecycle and state restoration.
- Reduce reliance on databases, filesystems, brokers, and the Spring context.

You do not need a `JobLauncher` or `JobRepository` in a test that only checks a processor's calculation. Instantiate the object under test directly and substitute external dependencies with appropriate fakes or mocks.

## 2. Distinguishing Unit Tests, Slice Tests, and Integration Tests

Three test categories serve distinct purposes:

| Test type | Scope | Example |
| --- | --- | --- |
| Unit test | One component and controlled dependencies | Testing `OrderProcessor` tax calculation |
| Component / slice test | A group of components with partial infrastructure | Testing a reader with a parser and file fixture |
| Spring Batch integration test | `Step`/`Job` with repository, transactions, and resources | Running a real `Step` against a test database and verifying restarts |

Unit tests typically do not boot an `ApplicationContext`. Component tests may use a lightweight Spring context when testing dependency injection or scopes. Integration tests verify collaboration across components and infrastructure.

Do not turn every unit test into a full application boot test. Doing so slows execution and lets Spring configuration mistakes obscure component logic errors.

## 3. Choosing Suitable Test Doubles

When a component depends on a repository, client, or external service, choose among these test doubles:

| Type | Purpose |
| --- | --- |
| Stub | Returns preconfigured results for calls |
| Fake | Simple working implementation with real behavior, such as an in-memory repository |
| Mock | Records interactions and lets you configure behavior |
| Spy | Wraps a real object to observe or override part of its behavior |

Example processor depending on a customer lookup service:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, OrderOutput> {

    private final CustomerService customerService;

    public OrderProcessor(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Override
    public OrderOutput process(OrderInput input) {
        Customer customer =
                customerService.findByCode(input.customerCode());

        if (customer == null) {
            throw new UnknownCustomerException(input.customerCode());
        }

        return new OrderOutput(
                input.orderId(),
                customer.id(),
                input.amount());
    }
}
~~~

A unit test can mock `CustomerService` to control outcomes:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderProcessorTest {

    @Mock
    private CustomerService customerService;

    private OrderProcessor processor;

    @BeforeEach
    void setUp() {
        processor = new OrderProcessor(customerService);
    }

    @Test
    void mapsOrderWhenCustomerExists() throws Exception {
        OrderInput input =
                new OrderInput(1001L, "C001", new BigDecimal("250.00"));
        Customer customer = new Customer(501L, "C001");

        when(customerService.findByCode("C001"))
                .thenReturn(customer);

        OrderOutput output = processor.process(input);

        assertEquals(1001L, output.orderId());
        assertEquals(501L, output.customerId());
        assertEquals(new BigDecimal("250.00"), output.amount());
        verify(customerService).findByCode("C001");
    }
}
~~~

The example uses records for brevity; if your project uses standard classes, substitute the corresponding constructors and getters. The test checks business outcomes and essential interactions without depending on the Spring Batch runtime.

## 4. Testing a Custom ItemReader

`ItemReader` has a simple contract: each `read()` call returns the next item; when no items remain, it returns `null`. The reader may throw an exception if reading fails or data is invalid.

A custom reader reading from a repository:

~~~java
public class OrderCursorReader implements ItemReader<OrderInput> {

    private final OrderRepository repository;
    private final Iterator<OrderInput> iterator;

    public OrderCursorReader(OrderRepository repository) {
        this.repository = repository;
        this.iterator = repository.findPendingOrders().iterator();
    }

    @Override
    public OrderInput read() {
        return iterator.hasNext() ? iterator.next() : null;
    }
}
~~~

This is a small reader illustrating the contract. In practice, do not load a large dataset into a `List`/`Iterator` when paged or streaming reads are intended.

### Testing Item Ordering and EOF

~~~java
@Test
void returnsItemsInOrderThenNullAtEnd() throws Exception {
    OrderRepository repository = mock(OrderRepository.class);
    when(repository.findPendingOrders()).thenReturn(List.of(
            new OrderInput(1L, "C001", new BigDecimal("10.00")),
            new OrderInput(2L, "C002", new BigDecimal("20.00"))));

    OrderCursorReader reader = new OrderCursorReader(repository);

    assertEquals(1L, reader.read().orderId());
    assertEquals(2L, reader.read().orderId());
    assertNull(reader.read());
    assertNull(reader.read());
}
~~~

Key assertions:

- Items return in the exact order specified by contract.
- Each item is returned the exact expected number of times.
- When data runs out, the reader returns `null`.
- Calling `read()` again after EOF does not fabricate phantom items.
- Empty input returns `null` on the very first read.
- Source failures propagate as appropriate exceptions rather than silently converting to EOF.

If ordering is a business requirement, assert the sequence explicitly rather than just checking item membership.

### Testing Empty Input

~~~java
@Test
void returnsNullWhenNoOrdersExist() throws Exception {
    OrderRepository repository = mock(OrderRepository.class);
    when(repository.findPendingOrders()).thenReturn(List.of());

    OrderCursorReader reader = new OrderCursorReader(repository);

    assertNull(reader.read());
}
~~~

Never return an empty object to signify end of data. Per the `ItemReader` contract, `null` is the end-of-input marker.

### Testing Exceptions

~~~java
@Test
void propagatesRepositoryFailure() {
    OrderRepository repository = mock(OrderRepository.class);
    when(repository.findPendingOrders())
            .thenThrow(new DataAccessResourceFailureException("database unavailable"));

    assertThrows(
            DataAccessResourceFailureException.class,
            () -> new OrderCursorReader(repository));
}
~~~

If a custom reader catches exceptions to add context, verify the new exception preserves the original cause. Never catch all exceptions and return `null`, because Spring Batch treats that as end of data and can terminate the `Step` erroneously.

## 5. Testing Stateful Readers

Stateful readers require testing beyond simply returning items. If a reader implements `ItemStream`, verify `open`, `update`, and `close` work properly.

Example reader reading a small list and tracking the next index:

~~~java
public class IndexedReader
        implements ItemStreamReader<String> {

    private static final String NEXT_INDEX = "indexedReader.nextIndex";

    private final List<String> items;
    private int nextIndex;

    public IndexedReader(List<String> items) {
        this.items = items;
    }

    @Override
    public void open(ExecutionContext context) {
        nextIndex = context.containsKey(NEXT_INDEX)
                ? context.getInt(NEXT_INDEX)
                : 0;
    }

    @Override
    public String read() {
        if (nextIndex >= items.size()) {
            return null;
        }
        return items.get(nextIndex++);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(NEXT_INDEX, nextIndex);
    }

    @Override
    public void close() {
        // Release resource if the reader actually owns any.
    }
}
~~~

Testing state restoration:

~~~java
@Test
void restoresPositionFromExecutionContext() throws Exception {
    IndexedReader reader =
            new IndexedReader(List.of("A", "B", "C", "D"));

    ExecutionContext context = new ExecutionContext();
    context.putInt("indexedReader.nextIndex", 2);

    reader.open(context);

    assertEquals("C", reader.read());
    assertEquals("D", reader.read());
    assertNull(reader.read());
}
~~~

Testing checkpointing:

~~~java
@Test
void storesNextPositionInExecutionContext() throws Exception {
    IndexedReader reader =
            new IndexedReader(List.of("A", "B", "C"));
    ExecutionContext context = new ExecutionContext();

    reader.open(context);
    assertEquals("A", reader.read());
    assertEquals("B", reader.read());

    reader.update(context);

    assertEquals(2, context.getInt("indexedReader.nextIndex"));
}
~~~

In a real reader, state should represent a recoverable position such as an offset, page, sort key, or token. Never store entire large item lists in `ExecutionContext`.

### Testing the Restart Cycle

A test can instantiate a first reader, read several items, call `update`, then create a new instance and call `open` with the saved context:

~~~java
@Test
void newReaderContinuesFromSavedCheckpoint() throws Exception {
    List<String> items = List.of("A", "B", "C", "D");
    ExecutionContext checkpoint = new ExecutionContext();

    IndexedReader firstRun = new IndexedReader(items);
    firstRun.open(checkpoint);
    assertEquals("A", firstRun.read());
    assertEquals("B", firstRun.read());
    firstRun.update(checkpoint);
    firstRun.close();

    IndexedReader restarted = new IndexedReader(items);
    restarted.open(checkpoint);

    assertEquals("C", restarted.read());
    assertEquals("D", restarted.read());
    assertNull(restarted.read());
}
~~~

This test verifies reader logic. It does not prove `JobRepository` persists checkpoints transactionally; that belongs in a `Step` integration test.

## 6. Testing Resource-Managing Readers

A reader may open files, cursors, streams, or client sessions. Confirm resources close at the right time and open/read errors are handled properly.

Inject abstractions for testing:

~~~java
public class MessageReader implements ItemStreamReader<Message> {

    private final MessageSource source;

    public MessageReader(MessageSource source) {
        this.source = source;
    }

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        source.open();
    }

    @Override
    public Message read() throws Exception {
        return source.receive();
    }

    @Override
    public void update(ExecutionContext context) {
        // Save offset or token if the source supports it.
    }

    @Override
    public void close() throws ItemStreamException {
        source.close();
    }
}
~~~

Testing lifecycle:

~~~java
@Test
void delegatesResourceLifecycle() throws Exception {
    MessageSource source = mock(MessageSource.class);
    MessageReader reader = new MessageReader(source);
    ExecutionContext context = new ExecutionContext();

    reader.open(context);
    reader.update(context);
    reader.close();

    verify(source).open();
    verify(source).close();
}
~~~

If a reader opens resources inside its constructor, lifecycle control in tests becomes hard and connections can open before the `Step` starts. Prefer opening resources in `open()` and closing in `close()` per the `ItemStream` contract.

## 7. Testing a Custom ItemProcessor

`ItemProcessor` takes an item and returns a transformed item. If it returns `null`, Spring Batch considers the item filtered and does not pass it to the writer.

Example processor:

~~~java
public class AmountProcessor
        implements ItemProcessor<OrderInput, OrderOutput> {

    @Override
    public OrderOutput process(OrderInput input) {
        if (input.amount() == null || input.amount().signum() <= 0) {
            return null;
        }

        BigDecimal tax = input.amount()
                .multiply(new BigDecimal("0.10"));
        BigDecimal total = input.amount().add(tax);

        return new OrderOutput(input.orderId(), total);
    }
}
~~~

Testing the valid case:

~~~java
@Test
void calculatesAmountAndTax() throws Exception {
    AmountProcessor processor = new AmountProcessor();
    OrderInput input =
            new OrderInput(1001L, "C001", new BigDecimal("100.00"));

    OrderOutput output = processor.process(input);

    assertEquals(1001L, output.orderId());
    assertEquals(new BigDecimal("110.0000"), output.totalAmount());
}
~~~

`BigDecimal` scale in the result depends on arithmetic operations and application normalization. In real projects, specify rounding modes and scales explicitly rather than letting tests rely on accidental scales.

### Testing Filtering via null

~~~java
@Test
void filtersInvalidAmount() throws Exception {
    AmountProcessor processor = new AmountProcessor();
    OrderInput input =
            new OrderInput(1002L, "C002", BigDecimal.ZERO);

    assertNull(processor.process(input));
}
~~~

Distinguish filtering from data errors. If business rules require bad records to be rejected or skipped with metrics, do not return `null`, because `null` means filtering and does not trigger skip listeners.

### Testing Exceptions and Boundaries

For processors, test:

- `null` input if the API permits it, or confirm rejection if forbidden.
- Zero, negative, and very large values.
- Missing required fields.
- Unsupported enum values.
- Dates near timezone boundaries or invalid dates.
- Dependency timeouts or not-found responses.
- Proper exception classification so the `Step` can retry, skip, or fail.

Do not write a separate test for every possible input value. Focus on boundaries that alter logic branches or business rules.

## 8. Testing Processors with Dependencies

For processors calling repositories or APIs, mock dependencies to control scenarios:

~~~java
@ExtendWith(MockitoExtension.class)
class CustomerEnrichmentProcessorTest {

    @Mock
    private CustomerRepository repository;

    private CustomerEnrichmentProcessor processor;

    @BeforeEach
    void setUp() {
        processor = new CustomerEnrichmentProcessor(repository);
    }

    @Test
    void enrichesInputWhenCustomerExists() throws Exception {
        when(repository.findByCode("C001"))
                .thenReturn(Optional.of(new Customer(501L, "C001")));

        EnrichedOrder result = processor.process(
                new OrderInput(1001L, "C001", new BigDecimal("25.00")));

        assertEquals(501L, result.customerId());
        verify(repository).findByCode("C001");
    }

    @Test
    void rejectsUnknownCustomer() {
        when(repository.findByCode("MISSING"))
                .thenReturn(Optional.empty());

        assertThrows(
                UnknownCustomerException.class,
                () -> processor.process(
                        new OrderInput(1002L, "MISSING", BigDecimal.TEN)));
    }
}
~~~

Mocks control responses and verify key calls. Avoid verifying every getter or internal call, which couples tests tightly to implementation details. Assert outputs and verify only meaningful interactions—such as not querying the repository when input fails validation first.

## 9. Testing a Custom ItemWriter

`ItemWriter` receives a `Chunk` of items and writes them to a destination. In Spring Batch 5, `write` accepts `Chunk`:

~~~java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
~~~

Example writer delegating items to a repository:

~~~java
public class OrderResultWriter implements ItemWriter<OrderOutput> {

    private final OrderResultRepository repository;

    public OrderResultWriter(OrderResultRepository repository) {
        this.repository = repository;
    }

    @Override
    public void write(Chunk<? extends OrderOutput> chunk) {
        repository.saveAll(chunk.getItems());
    }
}
~~~

Testing the writer:

~~~java
@Test
void writesEveryItemInChunk() throws Exception {
    OrderResultRepository repository =
            mock(OrderResultRepository.class);
    OrderResultWriter writer = new OrderResultWriter(repository);

    List<OrderOutput> items = List.of(
            new OrderOutput(1L, new BigDecimal("10.00")),
            new OrderOutput(2L, new BigDecimal("20.00")));

    writer.write(new Chunk<>(items));

    verify(repository).saveAll(items);
}
~~~

The test verifies the writer passes every item—and in order if ordering matters. For writers performing inserts/updates, capture arguments to check SQL mappings or command objects.

### Testing Empty Chunks

If a writer might receive an empty chunk in standalone use, define the expected behavior:

~~~java
@Test
void doesNotCallRepositoryForEmptyChunk() throws Exception {
    OrderResultRepository repository =
            mock(OrderResultRepository.class);
    OrderResultWriter writer = new OrderResultWriter(repository);

    writer.write(new Chunk<>());

    verifyNoInteractions(repository);
}
~~~

This behavior is a design choice for custom writers. Do not assume it for every writer; if a writer must record markers or metadata even on empty chunks, tests should reflect that contract.

### Testing Write Failures

~~~java
@Test
void propagatesRepositoryWriteFailure() {
    OrderResultRepository repository =
            mock(OrderResultRepository.class);
    OrderResultWriter writer = new OrderResultWriter(repository);

    doThrow(new DataAccessResourceFailureException("write failed"))
            .when(repository).saveAll(anyList());

    assertThrows(
            DataAccessResourceFailureException.class,
            () -> writer.write(new Chunk<>(List.of(
                    new OrderOutput(1L, BigDecimal.TEN)))));
}
~~~

A writer must not swallow exceptions and proceed as though the write succeeded. Spring Batch needs to know the write failed to roll back, retry, or fail according to `Step` configuration.

## 10. Testing Writers with ItemStream

Custom writers can implement `ItemStreamWriter` to manage files, buffers, or checkpoints. Test separately:

- `open()` initializes resources exactly once.
- `write()` writes expected content or updates buffers properly.
- `update()` persists needed state.
- Subsequent `open()` restores from saved state.
- `close()` releases resources even after errors.

Example writer persisting the written item count:

~~~java
public class CountingWriter<T> implements ItemStreamWriter<T> {

    private static final String COUNT_KEY = "countingWriter.count";
    private int count;

    @Override
    public void open(ExecutionContext context) {
        count = context.containsKey(COUNT_KEY)
                ? context.getInt(COUNT_KEY)
                : 0;
    }

    @Override
    public void write(Chunk<? extends T> chunk) {
        count += chunk.size();
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(COUNT_KEY, count);
    }

    @Override
    public void close() {
        // Close resource if any.
    }
}
~~~

Test:

~~~java
@Test
void persistsWriterState() throws Exception {
    CountingWriter<String> writer = new CountingWriter<>();
    ExecutionContext context = new ExecutionContext();

    writer.open(context);
    writer.write(new Chunk<>(List.of("A", "B", "C")));
    writer.update(context);

    assertEquals(3, context.getInt("countingWriter.count"));
}
~~~

This illustrates state tracking. For real file writers, test file contents and resume positions using a temporary directory rather than checking only a counter.

## 11. Testing Tasklets in Isolation

A `Tasklet` executes a bounded operation in one `execute` call or repeats depending on `RepeatStatus`. Test directly with mocked dependencies and `StepContribution`/`ChunkContext`.

Example:

~~~java
public class ArchiveTasklet implements Tasklet {

    private final ArchiveService archiveService;

    public ArchiveTasklet(ArchiveService archiveService) {
        this.archiveService = archiveService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        archiveService.archiveCompletedOrders();
        return RepeatStatus.FINISHED;
    }
}
~~~

Test:

~~~java
@Test
void archivesCompletedOrdersAndFinishes() throws Exception {
    ArchiveService archiveService = mock(ArchiveService.class);
    ArchiveTasklet tasklet = new ArchiveTasklet(archiveService);

    RepeatStatus result = tasklet.execute(
            mock(StepContribution.class),
            mock(ChunkContext.class));

    assertEquals(RepeatStatus.FINISHED, result);
    verify(archiveService).archiveCompletedOrders();
}
~~~

If the `Tasklet` returns `CONTINUABLE`, test termination conditions and state across multiple `execute` calls. Avoid infinite loops in tests; use stubs to control iteration count and assert `FINISHED` once the condition is met.

## 12. Testing Listeners in Isolation

Listeners typically log, emit events, update audits, or adjust status. Call callbacks directly with `StepExecution`/`JobExecution` instances created in tests.

Example `StepExecutionListener`:

~~~java
public class AuditStepListener implements StepExecutionListener {

    private final AuditService auditService;

    public AuditStepListener(AuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        auditService.started(
                stepExecution.getId(),
                stepExecution.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        auditService.finished(
                stepExecution.getId(),
                stepExecution.getStatus().name());
        return null;
    }
}
~~~

Test:

~~~java
@Test
void recordsStepStartAndFinish() {
    AuditService auditService = mock(AuditService.class);
    AuditStepListener listener = new AuditStepListener(auditService);
    StepExecution execution =
            MetaDataInstanceFactory.createStepExecution();

    listener.beforeStep(execution);
    ExitStatus exitStatus = listener.afterStep(execution);

    verify(auditService).started(
            execution.getId(),
            execution.getStepName());
    verify(auditService).finished(
            execution.getId(),
            execution.getStatus().name());
    assertNull(exitStatus);
}
~~~

If a listener returns a new `ExitStatus`, assert the exact code and description. Listeners performing only auditing/metrics should usually return `null` to preserve the current `ExitStatus`.

For `JobExecutionListener`, create a `JobExecution` with the appropriate test factory and call `beforeJob`/`afterJob` directly. You do not need a `JobLauncher` when testing only event behavior.

## 13. Testing Late Binding and Step Scope

`@StepScope` or `@JobScope` beans use scoped proxies and require an active scope context. Calling a scoped target directly in a unit test without activating the scope causes a scope-not-active failure.

Spring Batch Test provides `StepScopeTestUtils` to execute callbacks inside a `StepExecution` context:

~~~java
@SpringBatchTest
@SpringJUnitConfig(BatchConfiguration.class)
class ScopedReaderTest {

    @Autowired
    private ItemReader<OrderInput> orderReader;

    @Test
    void readsUsingCurrentStepContext() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "orders-test.json")
                .toJobParameters();
        StepExecution stepExecution =
                MetaDataInstanceFactory.createStepExecution(parameters);

        OrderInput item = StepScopeTestUtils.doInStepScope(
                stepExecution,
                () -> orderReader.read());

        assertNotNull(item);
    }
}
~~~

This example requires corresponding fixture files and Batch configuration. Factory APIs and test utilities must match your project's Spring Batch Test version.

When testing processor logic that does not depend on scope, instantiate the processor directly instead of starting a Spring context. Use scope tests only when verifying late binding, SpEL expressions, or scoped proxies.

### Verifying Two StepExecutions Have Isolated State

If a bean reads `JobParameters` or `StepExecutionContext`, create two `StepExecution`s with distinct values and confirm the proxy resolves the right target for each active context. This catches singletons accidentally retaining first-run values.

Do not share one `StepExecution` context across the entire test suite when testing independence between executions.

## 14. Testing Exceptions to Support Retry and Skip

Custom components must throw meaningful exception types. Spring Batch uses exception types in retry/skip policies, so tests must verify the exact exception type propagates.

Example:

~~~java
@Test
void throwsInvalidOrderForBusinessDataError() {
    OrderProcessor processor = new OrderProcessor(customerService);
    OrderInput invalid = new OrderInput(
            null, "C001", new BigDecimal("10.00"));

    assertThrows(
            InvalidOrderException.class,
            () -> processor.process(invalid));
}
~~~

Distinguish:

- Permanent data errors: reject or skip if business rules allow.
- Transient errors: retry, such as service timeouts or deadlocks.
- Configuration errors: fail fast instead of retrying.
- Unrecoverable infrastructure errors: fail and alert.

Do not test retry limits by calling a component repeatedly in a unit test and concluding the `Step` will retry properly. Retry is a fault-tolerant `Step` behavior requiring integration tests with real retry configuration.

## 15. Testing Transactions at the Right Layer

Unit tests of a custom writer verify it calls repositories or JDBC abstractions properly, but they do not prove the database rolls back when a chunk fails.

To verify transactions:

- Use a test database and a real transaction manager.
- Run a `Step` or chunk integration test.
- Inject a controlled failure after a write operation.
- Query the database after the `Step` ends to verify uncommitted data rolled back.
- Inspect `JobRepository`/checkpoints if the test covers restarts.

Never mock the transaction manager and conclude rollback works. Mocks verify method calls, not database transaction semantics.

If custom components call APIs or write files outside database transactions, unit tests should confirm outgoing commands/requests are correct; integration tests must verify idempotency, staging, or compensation strategies.

## 16. Testing with File Fixtures and Temporary Directories

File-handling readers/writers are easy to test using JUnit's temporary directory:

~~~java
@TempDir
Path tempDir;
~~~

Create an input file:

~~~java
Path input = tempDir.resolve("orders.csv");
Files.writeString(
        input,
        "orderId,amount\n1001,250.00\n",
        StandardCharsets.UTF_8);
~~~

After invoking the reader, assert parsed objects match expectations. For writers, write items into a file inside `tempDir` and read it back with the matching charset and parser to verify contents.

Scenarios to include:

- Empty files.
- Header-only files.
- Single record and multiple records.
- Unicode characters.
- Lines with missing or extra fields.
- Delimiters or quotes inside values.
- Both LF and CRLF line endings if both must be supported.
- Missing files or unreadable permissions.
- Write failures or missing target directories.

Temporary directories are managed and cleaned up by the test framework. Never hardcode output paths in the working directory where parallel test runs can overwrite each other.

## 17. Testing with Clocks and Deterministic Time

Components generating timestamps via `Instant.now()` are difficult to test because outputs vary with execution time.

Instead of reading the system clock directly, inject `Clock`:

~~~java
public class TimestampProcessor
        implements ItemProcessor<OrderInput, OrderOutput> {

    private final Clock clock;

    public TimestampProcessor(Clock clock) {
        this.clock = clock;
    }

    @Override
    public OrderOutput process(OrderInput input) {
        return new OrderOutput(input.orderId(), Instant.now(clock));
    }
}
~~~

Test with a fixed clock:

~~~java
@Test
void usesProvidedClock() throws Exception {
    Instant fixedInstant = Instant.parse("2026-11-15T10:30:00Z");
    Clock clock = Clock.fixed(fixedInstant, ZoneOffset.UTC);
    TimestampProcessor processor = new TimestampProcessor(clock);

    OrderOutput output = processor.process(
            new OrderInput(1001L, "C001", BigDecimal.TEN));

    assertEquals(fixedInstant, output.processedAt());
}
~~~

A fixed clock keeps tests deterministic regardless of timezone or execution time. When business logic uses local dates, pass an explicit `ZoneId` and test timestamps right around midnight boundaries.

## 18. Testing Immutability and Side Effects

Processors should usually transform inputs into outputs without mutating input objects unless there is a clear reason. Tests can capture input values before the call and confirm the input remains untouched.

Example:

~~~java
@Test
void doesNotMutateInput() throws Exception {
    OrderInput input =
            new OrderInput(1001L, "C001", new BigDecimal("10.00"));

    AmountProcessor processor = new AmountProcessor();
    processor.process(input);

    assertEquals("C001", input.customerCode());
    assertEquals(new BigDecimal("10.00"), input.amount());
}
~~~

If a component triggers side effects, tests should verify the exact call count and keys. For APIs using idempotency keys, assert keys remain stable per business ID so retries never duplicate operations.

Do not use unit tests to assume external side effects roll back alongside databases. That is an architectural property verified via integration or contract tests.

## 19. Testing Concurrency at the Component Level

If a custom component is designed for concurrent use, identify which state is shared and which belongs to a thread or execution.

Questions to verify:

- Is the reader thread-safe or single-threaded only?
- Can the writer receive multiple `Chunk`s concurrently?
- Do counters or buffers need atomic/synchronized access?
- Can one execution overwrite another execution's state?
- Do mocked/faked dependencies support concurrent calls in tests?

Do not write a concurrency test simply invoking multiple threads and checking a shared counter unless that mirrors how the `Step` actually executes. Concurrency tests should reflect the component's real contract, worker count, and synchronization model.

If a component is not thread-safe, document that it supports only single-threaded `Step`s or requires partitioning so each worker receives its own instance. A single-threaded unit test never proves multi-threaded safety.

## 20. Using JUnit Parameterized Tests for Multiple Cases

For logic with straightforward input/output tables, parameterized tests avoid repetition:

~~~java
@ParameterizedTest
@CsvSource({
        "100.00, 110.00",
        "0.00, 0.00",
        "50.00, 55.00"
})
void calculatesExpectedTotal(
        String amount,
        String expectedTotal) throws Exception {

    AmountProcessor processor = new AmountProcessor();
    OrderInput input = new OrderInput(
            1L, "C001", new BigDecimal(amount));

    OrderOutput output = processor.process(input);

    assertEquals(
            new BigDecimal(expectedTotal),
            output.totalAmount());
}
~~~

Adjust expected scales and filter rules to match the actual implementation. For complex inputs, use `MethodSource` to construct objects more cleanly than CSV strings.

Parameterized tests suit boundary values, enums, date formats, and mapping cases. Do not cram unrelated behaviors into one test merely to reduce method count.

## 21. Test Organization and Naming

Tests can be organized by component:

~~~text
src/test/java
  com.example.batch
    reader
      OrderReaderTest.java
    processor
      OrderProcessorTest.java
    writer
      OrderWriterTest.java
    tasklet
      ArchiveTaskletTest.java
    listener
      AuditStepListenerTest.java
~~~

Test names should state condition and outcome:

- `returnsItemsInOrderThenNullAtEnd`
- `restoresPositionFromExecutionContext`
- `filtersOrdersBelowMinimumAmount`
- `throwsInvalidOrderWhenCustomerIsMissing`
- `writesEveryItemInChunk`
- `propagatesRepositoryWriteFailure`
- `recordsStepStartAndFinish`

Each test should focus on one main behavior. Multiple related assertions inside one test are fine, but avoid sprawling tests that exercise reader, processor, writer, and transactions all at once.

## 22. Common Pitfalls When Testing Custom Components

### Booting the Entire Spring Context for Pure Logic

Tests become slow and harder to diagnose. Instantiate components directly, mock dependencies, and use Spring contexts only when testing wiring or scopes.

### Mocking the Component Under Test

Tests end up verifying only how the mock was configured. Instantiate the real component and mock external dependencies instead.

### Testing Only the Happy Path

Readers, processors, and writers branch heavily on empty inputs, nulls, EOF, exceptions, and boundary values. Add tests for every branch that changes behavior.

### Reader Returning Empty Objects at End of Data

Spring Batch interprets `null` as EOF. Returning an empty object makes the `Step` process an extra bogus item.

### Processor Returning null for All Errors

`null` signifies filtering. Use explicit exceptions for data errors needing skip/reject or system errors needing retry/fail.

### Skipping ItemStream Lifecycle Tests

A reader/writer might pass a single call while failing to recover on restart. Test `open`/`update`/`close` and checkpoints explicitly.

### Testing Transactions with Mocks

Mocks cannot execute database rollbacks. Use integration tests with a real transaction manager and database.

### Testing Scoped Beans Outside Step Context

Scoped proxies require an active context. Use `StepScopeTestUtils` or test listeners when verifying late binding.

### Testing Files at Hardcoded Paths

Tests can overwrite files or collide under parallel runs. Use `@TempDir`.

### Relying on Current Wall-Clock Time

Tests can flake across timezones or execution timestamps. Inject `Clock` and use `Clock.fixed`.

### Verifying Every Internal Call

Tests turn brittle under refactoring even when outputs are unchanged. Prefer asserting outputs, exceptions, and meaningful side effects.

### Assuming Unit Tests Prove Step Correctness

Unit tests do not verify transactions, retries, skips, checkpoints, or flow transitions. Complement them with integration tests covering framework behavior.

## 23. When Do You Need Spring Batch Test?

Spring Batch Test supplies utilities for testing `Job`s and `Step`s, such as:

- `@SpringBatchTest` to register test utilities.
- `JobLauncherTestUtils` to run a `Job` or `Step` in integration tests.
- `JobRepositoryTestUtils` to clean up test metadata when needed.
- `StepScopeTestUtils` to activate `Step` scope.
- `StepScopeTestExecutionListener` to supply `StepExecution` context to tests.

These utilities are unnecessary for every unit test. Use them when tests require Spring Batch infrastructure or need to verify real `Step`/`Job` behavior.

Example running a `Step` via `JobLauncherTestUtils`:

~~~java
@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class ImportStepIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void executesImportStep() throws Exception {
        JobExecution execution =
                jobLauncherTestUtils.launchStep("importOrdersStep");

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
    }
}
~~~

This is an integration test, not an isolated unit test. It is useful for checking `Step` wiring, reader/processor/writer lifecycles, and metadata. Configure test databases/resources and verify output data—never assert `BatchStatus` alone.

## 24. Minimum Test Matrix by Component Type

| Component | Cases to test |
| --- | --- |
| `ItemReader` | Data present, empty input, ordering, EOF, exceptions, state restoration |
| `ItemProcessor` | Accurate mapping, filtering via `null`, boundary inputs, validation, dependency failures |
| `ItemWriter` | Valid chunks, empty chunks per contract, write mapping, write failures, state |
| `Tasklet` | Expected side effects, `FINISHED`/`CONTINUABLE`, dependency errors |
| Listener | Expected callbacks, events, preserving `ExitStatus` when purely observing |
| `ItemStream` | `open`/`update`/`close`, checkpoint restoration, resource cleanup |
| Scoped bean | Late binding per `StepExecution`/`JobExecution`, no state leakage |

This matrix is a starting point. Not every component needs every case; choose tests matching the implementation's responsibilities and real risks.

## 25. Workflow for Writing Unit Tests for Custom Components

When testing a component, follow these steps:

1. Identify the component's interfaces and contracts: inputs, outputs, EOF, exceptions, and lifecycle.
2. Separate business logic from Spring contexts, databases, or files where feasible.
3. List external dependencies and decide between stubs, fakes, or mocks.
4. Write happy-path tests with small, readable inputs.
5. Write tests for empty/null inputs, boundaries, and exceptions.
6. For stateful readers/writers, test `ItemStream` `open`/`update`/`close` and restarts.
7. For scoped beans, activate the appropriate `StepExecution` or `JobExecution` context.
8. For files, use fixtures and temporary directories.
9. For time-sensitive logic, inject `Clock` for deterministic outputs.
10. Assert only meaningful interactions; avoid verifying implementation details.
11. Move transaction, retry, skip, and flow checks into integration tests.
12. Run tests under the project setup and verify tests do not depend on execution order or environment data.

Each test name should describe condition and expected outcome. Keep fixtures small, avoid sharing mutable state across tests, and always clean up opened resources.

## Conclusion

Testing custom components in isolation verifies the contracts of `ItemReader`, `ItemProcessor`, `ItemWriter`, `Tasklet`, listeners, and `ItemStream` without running an entire `Job`. Instantiate the real component, substitute external dependencies with stubs/fakes/mocks, and verify happy paths, EOF, filtering, exceptions, state, and resource lifecycles. Use `StepScopeTestUtils` for late binding, temporary directories for files, and fixed `Clock` instances for time logic. Unit tests do not prove `Step`-level transactions, retries, skips, or restarts; those behaviors require integration tests with Spring Batch infrastructure and real resources. Separating test scopes properly catches bugs quickly with clear root causes and maintainable suites.
