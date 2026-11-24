# Testing Writers with Empty Chunks and Multiple Items in Spring Batch

In chunk-oriented processing, `ItemWriter` receives a group of output items and writes them to the target system. Chunk size can vary: the final chunk is often smaller than the commit interval, the processor may filter some items, and the data source may be empty from the start. Therefore, when testing a writer, you need to verify both the content written and the number of times the writer is called in each scenario.

An important point is to distinguish **a writer receiving an empty chunk when called directly** from **Spring Batch not calling the writer because the output chunk is empty**. In default chunk processing, if there are no output items after the read and process steps, the framework skips calling the writer. Testing these two cases at the right layer helps avoid confusing the writer's responsibility with the framework's orchestration behavior.

## 1. The Role of ItemWriter in Chunk Processing

Basic processing flow:

```text
ItemReader
    |
    v
Read up to commit interval items
    |
    v
ItemProcessor (if any)
    |
    +---- output object -> keep in output chunk
    |
    +---- null          -> filter item out of output
    |
    v
ItemWriter receives output chunk
    |
    v
Commit transaction
```

In Spring Batch 5, `ItemWriter` receives a `Chunk`:

```java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

A writer usually iterates over `chunk.getItems()` to write data. Each time the framework calls it, the chunk contains the output items of one chunk-processing pass. If the reader has no items or the processor filters out every item, the output chunk is empty and the writer is not called in the default processing path.

In older Spring Batch versions, the writer signature may use `List<? extends T>` instead of `Chunk`. When writing tests, use the API corresponding to the library version the project is using.

## 2. Distinguishing Three Cases to Test

| Scenario | Reader input | Processor output | Writer behavior in default chunk processing |
| --- | --- | --- | --- |
| Empty source | No items; first read returns `null`. | No items to process. | Not called. |
| Processor filters all | Reader reads items. | All `process()` calls return `null`. | Not called because the output chunk is empty. |
| Multiple items | Reader supplies multiple items. | Has output items. | Called for each chunk with output; the last chunk may be smaller than the commit interval. |

Example with commit interval equal to 3:

```text
Input has 5 items, processor keeps all:
  Chunk 1: [A, B, C] -> writer called with 3 items
  Chunk 2: [D, E]    -> writer called with 2 items

Empty input:
  No output chunk -> writer is not called

Input has 4 items, processor filters all 4:
  readCount = 4, filterCount = 4
  No output chunk -> writer is not called
```

This result shows that the number of writer calls depends on the output after the processor, not solely on the number of items the reader read.

## 3. Testing a Writer in Isolation with a Multi-Item Chunk

Unit testing the writer directly helps verify how the writer converts and writes a group of items. You do not need to launch a job if the goal is only to check the write logic.

Example of a writer converting `Order`s into persisted records:

```java
public class OrderItemWriter implements ItemWriter<Order> {

    private final OrderRepository repository;

    public OrderItemWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        List<OrderEntity> entities = chunk.getItems().stream()
            .map(order -> new OrderEntity(order.getId(), order.getTotal()))
            .toList();

        repository.saveAll(entities);
    }
}
```

A test can pass multiple items and verify the repository receives the right data:

```java
@ExtendWith(MockitoExtension.class)
class OrderItemWriterTest {

    @Mock
    OrderRepository repository;

    @Test
    void writesEveryItemInChunk() throws Exception {
        OrderItemWriter writer = new OrderItemWriter(repository);
        Chunk<Order> chunk = new Chunk<>();
        chunk.add(new Order("A-1", new BigDecimal("10.00")));
        chunk.add(new Order("A-2", new BigDecimal("20.00")));
        chunk.add(new Order("A-3", new BigDecimal("30.00")));

        writer.write(chunk);

        ArgumentCaptor<Iterable<OrderEntity>> captor =
            ArgumentCaptor.forClass(Iterable.class);
        verify(repository).saveAll(captor.capture());

        assertThat(StreamSupport.stream(captor.getValue().spliterator(), false))
            .extracting(OrderEntity::getOrderId)
            .containsExactly("A-1", "A-2", "A-3");
    }
}
```

This is a unit test for the writer logic. In real code, you can use an assertion suited to the repository's parameter type and avoid the captor's raw type by capturing a `List` or using `ArgumentCaptor` according to the project's Mockito API. The goal is to verify all items are present, in the right order if order matters, and with the right converted data.

A unit test does not verify the chunk transaction, how many times the framework calls the writer, or behavior when the processor filters. Those require integration testing with the step/job.

## 4. Testing a Writer When Passed an Empty Chunk Directly

A writer can be called directly in a unit test with an empty `Chunk` to verify that the implementation does not fail when there are no items, if the application wants the writer to have no-op behavior in that case:

```java
@Test
void handlesEmptyChunkAsNoOp() throws Exception {
    OrderItemWriter writer = new OrderItemWriter(repository);
    Chunk<Order> emptyChunk = new Chunk<>();

    writer.write(emptyChunk);

    verify(repository).saveAll(List.of());
}
```

The specific assertion depends on how the writer is written. If the writer explicitly returns early when `chunk.isEmpty()`, the test should verify that the repository is not called:

```java
@Override
public void write(Chunk<? extends Order> chunk) {
    if (chunk.isEmpty()) {
        return;
    }
    repository.saveAll(mapOrders(chunk.getItems()));
}
```

Then the corresponding test:

```java
writer.write(new Chunk<>());
verifyNoInteractions(repository);
```

The two approaches represent two different writer contracts. If the writer always calls `saveAll` with an empty collection, verify that the repository actually accepts that. If you want empty to be a no-op, verify that no write operations are issued.

However, a test calling `write(emptyChunk)` directly does not prove that Spring Batch will call the writer with an empty chunk. In standard chunk-oriented processing, the framework skips `ItemWriter.write()` when the output chunk is empty. That integration behavior needs a separate test.

## 5. Using a Recording Writer to Verify Invocation Counts

In an integration test, a recording writer helps observe how many times the writer is called and the contents of each chunk. Example:

```java
public class RecordingItemWriter<T> implements ItemWriter<T> {

    private final List<List<T>> writtenChunks = new ArrayList<>();

    @Override
    public void write(Chunk<? extends T> chunk) {
        writtenChunks.add(new ArrayList<>(chunk.getItems()));
    }

    public List<List<T>> getWrittenChunks() {
        return List.copyOf(writtenChunks);
    }

    public void clear() {
        writtenChunks.clear();
    }
}
```

The writer stores a copy of the item list on each call. Copying is important because the chunk is an object managed by the framework; the test should not keep a mutable reference and then assume its contents never change.

If the step runs asynchronously or tests run in parallel, the recording writer needs appropriate synchronization or each test must use a separate instance. The example above is simplified for tests running sequentially within one application context.

## 6. Integration Testing with Empty Source and Multiple Items

A test job can use `ListItemReader`, an optional processor, and a recording writer. Use `@StepScope` to create a fresh reader for each execution based on a job parameter, avoiding sharing an exhausted iterator across runs.

Configuration example for Spring Batch 5:

```java
@TestConfiguration
class WriterChunkTestConfiguration {

    @Bean
    @StepScope
    ItemReader<Integer> writerTestReader(
            @Value("#{jobParameters['scenario']}") String scenario) {
        List<Integer> items = switch (scenario) {
            case "EMPTY" -> List.of();
            case "MANY" -> List.of(1, 2, 3, 4, 5);
            case "FILTER_ALL" -> List.of(1, 2, 3, 4);
            default -> throw new IllegalArgumentException("Unknown scenario: " + scenario);
        };
        return new ListItemReader<>(items);
    }

    @Bean
    @StepScope
    ItemProcessor<Integer, Integer> writerTestProcessor(
            @Value("#{jobParameters['scenario']}") String scenario) {
        return item -> "FILTER_ALL".equals(scenario) ? null : item;
    }

    @Bean
    RecordingItemWriter<Integer> recordingItemWriter() {
        return new RecordingItemWriter<>();
    }

    @Bean
    Step writerTestStep(JobRepository jobRepository,
                        PlatformTransactionManager transactionManager,
                        ItemReader<Integer> writerTestReader,
                        ItemProcessor<Integer, Integer> writerTestProcessor,
                        RecordingItemWriter<Integer> recordingItemWriter) {
        return new StepBuilder("writerTestStep", jobRepository)
            .<Integer, Integer>chunk(3, transactionManager)
            .reader(writerTestReader)
            .processor(writerTestProcessor)
            .writer(recordingItemWriter)
            .build();
    }

    @Bean
    Job writerTestJob(JobRepository jobRepository, Step writerTestStep) {
        return new JobBuilder("writerTestJob", jobRepository)
            .start(writerTestStep)
            .build();
    }
}
```

With a commit interval of 3:

- `EMPTY` creates a reader with no items.
- `FILTER_ALL` reads four items, but the processor returns `null` for all of them.
- `MANY` reads five items and keeps all of them, producing two writes of sizes 3 and 2 respectively.

The integration test can use `@SpringBootTest`, `@SpringBatchTest`, and import the configuration above. Disable Spring Boot's auto-launch so the job runs only when the test requests it:

```java
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@SpringBatchTest
@Import(WriterChunkTestConfiguration.class)
class WriterChunkIntegrationTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("writerTestJob")
    Job writerTestJob;

    @Autowired
    RecordingItemWriter<Integer> writer;

    @BeforeEach
    void prepare() {
        writer.clear();
        jobLauncherTestUtils.setJob(writerTestJob);
    }

    private JobExecution launch(String scenario) throws Exception {
        JobParameters parameters = new JobParametersBuilder()
            .addString("requestId", UUID.randomUUID().toString(), true)
            .addString("scenario", scenario, false)
            .toJobParameters();
        return jobLauncherTestUtils.launchJob(parameters);
    }
}
```

Each run has a unique identifying `requestId` to create a separate `JobInstance`. `scenario` is non-identifying in the example because the request ID already distinguishes each run; in a real application, identifying parameters must be chosen according to the business unit of work.

## 7. Assertions When the Input Source Is Empty

When the scenario is `EMPTY`, the reader returns `null` on the very first read. The step can still complete successfully, but the writer has no output chunk to write:

```java
@Test
void doesNotInvokeWriterWhenReaderHasNoItems() throws Exception {
    JobExecution execution = launch("EMPTY");

    assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

    StepExecution step = execution.getStepExecutions()
        .iterator()
        .next();

    assertThat(step.getReadCount()).isZero();
    assertThat(step.getWriteCount()).isZero();
    assertThat(writer.getWrittenChunks()).isEmpty();
}
```

This test verifies both the step status and that the writer was not called. Asserting only `writeCount == 0` is not enough to prove the writer was not called, because a custom writer could still be called with an empty chunk in a direct call or a custom flow. The recording writer lets you observe the exact invocation count in the job test.

## 8. Assertions When the Processor Filters Every Item

The `FILTER_ALL` case differs from an empty input: the reader still reads items, but the processor drops all of them. The framework does not call the writer because the output chunk has no items:

```java
@Test
void doesNotInvokeWriterWhenProcessorFiltersEveryItem() throws Exception {
    JobExecution execution = launch("FILTER_ALL");

    assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

    StepExecution step = execution.getStepExecutions()
        .iterator()
        .next();

    assertThat(step.getReadCount()).isEqualTo(4);
    assertThat(step.getFilterCount()).isEqualTo(4);
    assertThat(step.getWriteCount()).isZero();
    assertThat(writer.getWrittenChunks()).isEmpty();
}
```

This test proves the reader supplied four items, the processor filtered four items, and the writer was not called. When monitoring production, this is an important difference between an empty source and a source that has data where all data is rejected.

## 9. Assertions When There Are Multiple Items and a Smaller Last Chunk

With the `MANY` scenario, the reader supplies five items and the commit interval is three. The writer is called twice:

```java
@Test
void writesManyItemsInSeparateChunks() throws Exception {
    JobExecution execution = launch("MANY");

    assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

    StepExecution step = execution.getStepExecutions()
        .iterator()
        .next();

    assertThat(step.getReadCount()).isEqualTo(5);
    assertThat(step.getWriteCount()).isEqualTo(5);

    assertThat(writer.getWrittenChunks())
        .containsExactly(List.of(1, 2, 3), List.of(4, 5));
}
```

The `containsExactly` assertion checks the number of calls, the size of each chunk, and the order of items. If order is not a business requirement, you can use a less strict assertion. In this example, the reader is sequential, so order is preserved.

The last chunk has two items even though the commit interval is three. This is normal behavior; the writer receives the remainder and writes it in the final transaction. There is no need to add dummy items to pad the chunk.

## 10. Testing a Writer Called Directly with Various Chunk Sizes

Besides integration tests, you can write a parameterized test for the writer to check multiple input sizes: 0, 1, equal to the commit interval, and larger than the commit interval. A direct unit test does not simulate the framework splitting chunks, but it helps verify that the writer handles every collection its implementation expects to receive.

Example with a writer writing to a repository:

```java
@ParameterizedTest
@ValueSource(ints = {1, 2, 3, 10})
void writesAllItemsForDifferentChunkSizes(int size) throws Exception {
    OrderItemWriter writer = new OrderItemWriter(repository);
    Chunk<Order> chunk = new Chunk<>();

    for (int i = 1; i <= size; i++) {
        chunk.add(new Order("ORDER-" + i, BigDecimal.TEN));
    }

    writer.write(chunk);

    verify(repository).saveAll(argThat(items ->
        StreamSupport.stream(items.spliterator(), false).count() == size
    ));
}
```

If you want to test an empty chunk in the same test suite, add a `size = 0` case and an assertion matching the writer's contract: no-op or calling the repository with an empty list. Do not mix this unit test assertion with the expectation of the framework calling the writer when the output is empty.

## 11. Verifying Transactions and Rollback When the Writer Fails

The writer usually performs the chunk's write operations. If the writer throws an exception and the write operations participate in the step's transaction, the chunk transaction will roll back. Earlier committed chunks are kept; the current chunk is not considered successfully written.

An integration test can use a mock writer that throws an exception on the second call:

```java
public class FailingRecordingWriter<T> implements ItemWriter<T> {

    private int calls;

    @Override
    public void write(Chunk<? extends T> chunk) {
        calls++;
        if (calls == 2) {
            throw new IllegalStateException("Simulated writer failure");
        }
    }
}
```

With a commit interval of 3 and five items, the first write can commit three items. The second write fails and the step/job ends `FAILED` if there is no appropriate retry/skip. When testing real transactions, use a test database and a writer writing to the database participating in the same transaction manager to verify rollback via committed data, rather than only checking for the exception.

If the writer calls an API or writes to a datasource that does not participate in the transaction, the chunk's rollback does not automatically undo external effects. In that case, you need idempotency or a transactional outbox. This is why the writer needs to be designed to reprocess safely, even when the processor has been designed as pure transformation.

## 12. Writer Called Again on Retry or Restart

Do not assume each chunk calls the writer exactly once in every situation. If the writer fails, a fault-tolerant step can retry according to the configuration. If the chunk rolls back and then the job restarts, uncommitted data can be written again.

For writers with external side effects, check:

- Whether two writes of the same item create duplicate records.
- Whether the target API accepts a stable idempotency key.
- Whether a chunk that partially wrote and then failed can be resent without duplicating data.
- Whether metadata and target data share a transaction or need an outbox/reconciliation.
- Whether the writer keeps mutable state across calls that makes results differ.

For database writers, unique constraints and upserts can help prevent duplicate writes, but must be designed around a business key. For message brokers, distinguish a successful publish from marking the event as published; consumers should be idempotent because delivery can repeat.

## 13. Cleaning Up Data and Isolating Tests

Test jobs write metadata to `JobRepository`, while the writer can write data to the test database. If multiple tests share a database, data from an earlier test can affect assertions of a later test.

Some isolation approaches:

- Use H2 or a dedicated schema for tests.
- Use a unique identifying parameter for each run.
- Delete test business data by the test's key, in a separate transaction or fixture.
- Use a recording writer with a separate instance per test or call `clear()` before each execution.
- Clean metadata with `JobRepositoryTestUtils` only when the repository is completely owned by the test suite.

Example:

```java
@Autowired
JobRepositoryTestUtils jobRepositoryTestUtils;

@AfterEach
void cleanMetadata() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

Do not use this cleanup utility on a production repository or a repository shared with other jobs. Deleting metadata also does not automatically delete the data the writer wrote into business tables; clean both parts independently and in a controlled manner.

If tests run in parallel, avoid using a singleton recording writer with a shared mutable list. Create separate contexts/beans, use test data with distinct keys, or synchronize recording so tests do not overwrite each other's results.

## 14. Common Mistakes When Testing Writers

**Checking only `writeCount`:** a count of 0 does not clarify whether the writer was not called or was called but wrote no items. Use a recording writer or verify mocks to confirm invocation.

**Confusing empty input with filtering all items:** both can result in not calling the writer, but `readCount` and `filterCount` differ. Check the reader, processor, and step counters together.

**Expecting the writer to receive an empty chunk from the framework:** standard chunk processing skips calling the writer when output is empty. If you need to test the implementation with an empty chunk, call the writer directly in a unit test.

**Assuming the last chunk must fill the commit interval:** the writer receives a last chunk smaller than the interval if items remain. Test counts not divisible by the interval to verify the trailing portion of data is not lost.

**Keeping a reference to a mutable chunk:** store a copy `new ArrayList<>(chunk.getItems())` in the recording writer so assertions do not depend on later changes.

**Sharing a stateful writer across tests:** recorded lists or invocation counters may contain data from an earlier test. Reset state or create separate instances.

**Not testing rollback:** a writer throwing an exception can make the chunk roll back, while a writer calling an external system may still have created side effects. Use transaction tests and appropriate idempotency.

**Cleaning metadata too broadly:** deleting all executions in a shared repository can affect other tests or running jobs. Only clean up an isolated repository.

## 15. Designing a Behavior-Based Writer Test Suite

A useful writer test suite should cover these cases:

1. **Single item:** the writer receives one item and writes one result.
2. **Multiple items:** the writer writes all items, in the right order if order matters.
3. **Empty chunk called directly:** the writer behaves according to the chosen contract, usually a no-op.
4. **Empty source in a job:** the writer is not called by the framework; the step can still complete.
5. **Processor filters all:** the reader has a read count, filter count increases; the writer is not called.
6. **Smaller last chunk:** the writer receives the remaining items and writes the exact count.
7. **Writer failure:** the chunk transaction rolls back and job status reflects failure if not recovered.
8. **Retry/restart:** the writer can receive items again without creating duplicate side effects.

Not every writer needs all tests in the same class. Unit tests should focus on mapping/write logic; integration tests should verify how the framework splits chunks, calls the writer, manages transactions, and updates metadata.

## 16. Choosing Appropriate Assertions

When verifying the content the writer receives, use `containsExactly(...)` if order is part of the contract. Use `containsExactlyInAnyOrder(...)` if order does not matter but the item set must be complete. With large data, you can check size, totals, business keys, or checksums instead of comparing every whole object.

When verifying invocation counts, use `verify(writer, times(n))` if the writer is a mock or use a recording writer to save each chunk. For a job with commit interval 3 and five unfiltered items, expect two calls of sizes 3 and 2. For empty input or empty output, expect zero invocations in default chunk processing.

When verifying status, the `BatchStatus.COMPLETED` assertion should go alongside the `readCount`, `filterCount`, and `writeCount` counters and the actual data in the target system if that is the job's goal. A completed job does not by itself prove the writer wrote the right data.

Testing writers with empty chunks and multiple items helps verify the boundary between data the reader supplies, data the processor keeps, and data the writer actually writes. Combining unit tests for the writer with integration tests for the job—checking invocations, chunk sizes, transactions, and retry behavior—lets the application catch dropped items, duplicate writes, or mishandled empty-output cases early.
