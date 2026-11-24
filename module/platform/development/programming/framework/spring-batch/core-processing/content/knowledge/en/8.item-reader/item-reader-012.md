# Testing Readers with Boundary Inputs

In Spring Batch, **ItemReader** reads items one by one from a data source and returns the next item to the Step. When the source is exhausted, the reader returns **null** to signal the end. Because the reader usually sits at the start of a chunk-oriented pipeline, a bug here can prevent an entire chunk from being processed or stop the Job before the writer writes any data.

Testing a reader with boundary inputs verifies that the reader behaves properly in scenarios that are easily overlooked: empty sources, a single record, record counts right before or after a page/chunk boundary, an incomplete final line, empty data fields, malformed data, a nonexistent file, and restarting from saved state.

A good test suite needs to verify the **values read**, **order**, **when the reader returns null**, **exceptions on invalid data**, and **state recovery capability**. You also need to distinguish the reader's responsibility from the processor's: the reader validates structure and converts source data into items; deeper business rules usually belong to the processor or validator.

## 1. The ItemReader Contract

The basic ItemReader contract is quite small:

~~~java
public interface ItemReader<T> {
    T read() throws Exception;
}
~~~

Each time read() is called:

- Returns an item if data remains.
- Returns null when no items remain.
- May throw an exception if data cannot be read or converted according to configuration.

Simple reader example:

~~~java
ItemReader<String> reader = new ListItemReader<>(
        List.of("A", "B", "C"));

assertEquals("A", reader.read());
assertEquals("B", reader.read());
assertEquals("C", reader.read());
assertNull(reader.read());
~~~

The end point is part of the contract. A reader should not use an empty string, the number 0, or a special object to denote EOF if those values can still be valid data. In Spring Batch, null has a clear meaning: there are no more items to read.

For stateful readers, such as readers reading files or databases by page, you also need to test the ItemStream lifecycle:

- open(ExecutionContext): opens the source and restores state.
- update(ExecutionContext): saves the current checkpoint.
- close(): releases resources.

## 2. Identifying Boundary Input Groups

Before writing tests, list the boundaries the data source can encounter. For a customer CSV file, an initial matrix might be:

| Group | Input to test | What to confirm |
|---|---|---|
| Count | Empty file | Reader ends immediately, produces no items |
| Count | Single record | Reads one item then EOF |
| Count | N-1, N, N+1 items | No missing or duplicate items at boundaries |
| Structure | Header only | Does not treat header as data |
| Structure | Missing or extra columns | Parse behavior matches configuration |
| Content | Empty or whitespace-only fields | Maps properly; rejection rule sits in the right layer |
| Content | Maximum supported string length | Does not truncate or corrupt data |
| Data type | Numeric/date values at min, max | Converts properly or reports clear error |
| Format | Delimiter inside quotes | Does not split column wrongly |
| Format | Final line without newline | Still reads the last record completely |
| Source | File missing or unreadable | Reports error per policy |
| State | Restart after saving checkpoint | Resumes from saved position |

Not every case has to be tested at the same layer. For example, a reader can successfully read an empty email into an object; the processor is where customers without an email are rejected. Reader tests should verify the reader's behavior, while processor tests verify business rules.

## 3. Testing a Reader with an In-Memory List

For simple read logic, you can use ListItemReader to test the ItemReader contract without needing a file or database.

Example EOF tests:

~~~java
class ListReaderTest {

    @Test
    void returnsItemsInOrderThenNull() throws Exception {
        ItemReader<String> reader =
                new ListItemReader<>(List.of("A", "B", "C"));

        assertEquals("A", reader.read());
        assertEquals("B", reader.read());
        assertEquals("C", reader.read());
        assertNull(reader.read());
        assertNull(reader.read());
    }

    @Test
    void emptyInputReturnsNullImmediately() throws Exception {
        ItemReader<String> reader =
                new ListItemReader<>(List.of());

        assertNull(reader.read());
    }

    @Test
    void singleItemIsReturnedExactlyOnce() throws Exception {
        ItemReader<Integer> reader =
                new ListItemReader<>(List.of(42));

        assertEquals(42, reader.read());
        assertNull(reader.read());
        assertNull(reader.read());
    }
}
~~~

These tests confirm:

- The list is read in the right order.
- The reader does not invent extra items.
- An empty source ends immediately.
- A single item is not returned repeatedly after EOF.

ListItemReader suits testing part of orchestration logic or code that accepts an ItemReader. It does not replace tests for FlatFileItemReader, JdbcPagingItemReader, or custom readers, because those readers also have their own logic for parsing, paging, cursors, and state.

## 4. Testing FlatFileItemReader with Boundary Files

For CSV files, create fixtures directly inside the test using JUnit 5 @TempDir. That way the test can control exact file content and does not depend on files on the developer machine.

Suppose the data has three columns: id, name, and email. Create a simple JavaBean to map to:

~~~java
public class CustomerRow {

    private Long id;
    private String name;
    private String email;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Create a factory for the reader:

~~~java
private FlatFileItemReader<CustomerRow> createReader(Path file) {
    return new FlatFileItemReaderBuilder<CustomerRow>()
            .name("customerReader")
            .resource(new FileSystemResource(file.toFile()))
            .encoding("UTF-8")
            .linesToSkip(1)
            .delimited()
            .names("id", "name", "email")
            .targetType(CustomerRow.class)
            .saveState(true)
            .build();
}
~~~

In the example:

- linesToSkip(1) skips the header.
- names(...) defines the field names.
- targetType(...) maps the FieldSet into the bean.
- encoding("UTF-8") defines the file encoding.
- saveState(true) allows the reader to save state for restart.
- name(...) needs to be stable so the reader recognizes its state in the ExecutionContext.

A test for a single record:

~~~java
class FlatFileCustomerReaderTest {

    @TempDir
    Path tempDir;

    private FlatFileItemReader<CustomerRow> createReader(Path file) {
        return new FlatFileItemReaderBuilder<CustomerRow>()
                .name("customerReader")
                .resource(new FileSystemResource(file.toFile()))
                .encoding("UTF-8")
                .linesToSkip(1)
                .delimited()
                .names("id", "name", "email")
                .targetType(CustomerRow.class)
                .saveState(true)
                .build();
    }

    @Test
    void readsOneRecordThenReturnsEof() throws Exception {
        Path file = tempDir.resolve("customers.csv");
        Files.writeString(
                file,
                "id,name,email\n" +
                "1,Alice,alice@example.com\n",
                StandardCharsets.UTF_8);

        FlatFileItemReader<CustomerRow> reader = createReader(file);

        reader.open(new ExecutionContext());
        try {
            CustomerRow customer = reader.read();

            assertNotNull(customer);
            assertEquals(1L, customer.getId());
            assertEquals("Alice", customer.getName());
            assertEquals("alice@example.com", customer.getEmail());

            assertNull(reader.read());
        } finally {
            reader.close();
        }
    }
}
~~~

Close the reader in a finally block to release resources even when assertions or read operations fail. For readers that open files, cursors, or connections, resource closure is a part that must be tested.

### Empty Files and Header-Only Files

These two cases are not the same:

- An empty file has 0 bytes.
- A header-only file has one header line but no records.

If the reader is configured to skip one header line, both cases usually produce no items. Tests should verify that read() returns null right after open().

~~~java
@Test
void emptyFileReturnsEof() throws Exception {
    Path file = tempDir.resolve("empty.csv");
    Files.writeString(file, "", StandardCharsets.UTF_8);

    FlatFileItemReader<CustomerRow> reader = createReader(file);
    reader.open(new ExecutionContext());

    try {
        assertNull(reader.read());
    } finally {
        reader.close();
    }
}

@Test
void headerOnlyFileReturnsEof() throws Exception {
    Path file = tempDir.resolve("header-only.csv");
    Files.writeString(
            file,
            "id,name,email\n",
            StandardCharsets.UTF_8);

    FlatFileItemReader<CustomerRow> reader = createReader(file);
    reader.open(new ExecutionContext());

    try {
        assertNull(reader.read());
    } finally {
        reader.close();
    }
}
~~~

If the application requires the file to have at least one record, that is a separate business rule or input check. A reader returning EOF for a file with no data is valid behavior; do not turn every empty file into an error if business requirements do not specify that.

## 5. Testing Count Boundaries N-1, N, and N+1

A common bug in paging or chunk-based readers is losing or repeating items right at the boundary. Choose a size N representing the page size or chunk size, and then test:

- N-1 items: not enough for one full group.
- N items: exactly one full group.
- N+1 items: one leftover item creating a final group.
- 2N items: exactly two full groups.
- 2N+1 items: a final group with just one item.

With a simple reader, test total item count and order:

~~~java
@ParameterizedTest
@ValueSource(ints = {0, 1, 9, 10, 11, 20, 21})
void readsEveryItemExactlyOnce(int itemCount) throws Exception {
    List<Integer> input = IntStream.rangeClosed(1, itemCount)
            .boxed()
            .toList();

    ItemReader<Integer> reader = new ListItemReader<>(input);
    List<Integer> actual = new ArrayList<>();

    Integer item;
    while ((item = reader.read()) != null) {
        actual.add(item);
    }

    assertEquals(input, actual);
    assertNull(reader.read());
}
~~~

In this example, N is 10. The test checks sizes 9, 10, 11, 20, and 21, along with empty and single-item cases.

Note: chunk size belongs to the Step configuration, whereas the reader usually knows only how to return the next item. Standalone reader tests confirm item count and order. If you need to test commits per chunk, write an integration test for the Step with a specific chunk size and a writer that records the groups received.

### Why Does N+1 Matter?

If a reader uses a page size of 10 and the source has 11 items, the first page holds 10 items and the next page has only one item. A bug in the page-transition condition can cause the last item to be skipped or the boundary item to be returned twice.

An N+1 test should verify:

- The Nth item is returned exactly once.
- The (N+1)th item is fetched from the next page.
- After the last item, read() returns null.
- No infinite queries or reads occur after EOF.

## 6. Testing Missing, Extra, and Malformed Data

File readers often have to convert source strings into item data types. The following cases need to be tested individually:

| Input | Question to verify |
|---|---|
| Missing a column | Does the parser throw an exception or apply a default value? |
| Extra column | Does the parser reject or ignore the remainder according to configuration? |
| Non-numeric ID | Does it report a clear conversion error? |
| Malformed date | Does the reader stop with a parse exception? |
| Empty field | Is it mapped to an empty string, null, or a default value? |
| Blank line | Is it skipped, mapped to an item, or does it report an error? |
| Delimiter inside quotes | Does it preserve the content of a single field? |
| Unclosed quote | Does it report a parse error? |

Example test for a line with a non-numeric ID:

~~~java
@Test
void invalidNumericFieldFailsReading() throws Exception {
    Path file = tempDir.resolve("invalid-id.csv");
    Files.writeString(
            file,
            "id,name,email\n" +
            "abc,Alice,alice@example.com\n",
            StandardCharsets.UTF_8);

    FlatFileItemReader<CustomerRow> reader = createReader(file);
    reader.open(new ExecutionContext());

    try {
        assertThrows(Exception.class, reader::read);
    } finally {
        reader.close();
    }
}
~~~

In real tests, check the specific exception type according to the Spring Batch version and how FieldSetMapper is configured. Parsing errors may be wrapped in FlatFileParseException, along with line information and root cause. If the test cares only about the reader contract, assertThrows(Exception.class) is general; if you need to check diagnostics, assert the exception type and line number.

Do not assume every missing or extra field must be rejected. Clearly define the input schema and configure the tokenizer, strict mode, and mapper according to application requirements.

## 7. Testing Empty Fields, Whitespace, and Length Limits

Real-world data often contains values such as:

- Empty string: a field with zero characters.
- Whitespace: one or more spaces.
- Unexpected tabs or newline characters.
- Very long strings.
- Unicode characters, Vietnamese diacritics, or emoji.
- Special characters and delimiters inside the content.

The reader needs to preserve or map data accurately according to configuration. If business rules require trimming, length validation, or rejecting empty fields, decide which component is responsible.

Example test confirming the reader preserves a field with spaces:

~~~java
@Test
void preservesWhitespaceForProcessorToValidate() throws Exception {
    Path file = tempDir.resolve("whitespace.csv");
    Files.writeString(
            file,
            "id,name,email\n" +
            "1,  Alice  ,alice@example.com\n",
            StandardCharsets.UTF_8);

    FlatFileItemReader<CustomerRow> reader = createReader(file);
    reader.open(new ExecutionContext());

    try {
        CustomerRow customer = reader.read();

        assertNotNull(customer);
        assertEquals("  Alice  ", customer.getName());
    } finally {
        reader.close();
    }
}
~~~

This test makes sense if the reader is configured not to trim fields automatically. If the application's tokenizer or mapper already normalizes data, assertions should reflect that configuration.

For fields with length limits, test all of these:

- Minimum valid length.
- Exact maximum limit.
- Exceeding the limit by one character.
- Empty string and whitespace-only string.

If the reader only maps strings, rejecting lengths may belong to the processor or validator. Test at the responsible layer to avoid testing the wrong layer.

## 8. Testing Dates, Numbers, and Boundary Values

When a reader maps strings to data types, values near limits easily expose parsing bugs or overflows.

Example with an integer field:

| Case | Example | What to check |
|---|---|---|
| Minimum value | 0 or minimum supported negative value | Converts properly |
| Maximum value | MAX of target type | No overflow |
| Over limit | MAX + 1 | Reports clear error |
| Negative value | -1 | Accepted or rejected per schema |
| Plus sign | +10 | How the parser handles it |
| Decimal point | 10.25 | Correct type and scale? |

For dates, test:

- First and last day of the month.
- February 29 in a leap year.
- February 29 in a non-leap year.
- Day 31 in a month with only 30 days.
- Format missing leading zeros.
- Empty string or invalid date.

If the reader only reads strings, the parser can leave date conversion to the processor. If the reader uses FieldSetMapper to convert immediately, reader tests must verify the mapper's parsing behavior. Stay consistent with the actual schema instead of adding arbitrary business rules into the reader.

## 9. Testing Delimiters, Quotes, and Encoding

CSV files are not just values separated by commas. A field can contain commas inside quotes, escaped quotes, or Unicode characters.

Example:

~~~csv
id,name,email
1,"Nguyen, An",an@example.com
2,"He said ""Hello""",hello@example.com
3,"Nguyễn Thị Ánh",anh@example.com
~~~

Tests need to verify:

- Commas inside quoted fields do not create extra columns.
- Escaped double quotes are read properly.
- Vietnamese characters do not suffer encoding errors.
- Files with a BOM are handled according to reader configuration and version.
- Lines ending with LF or CRLF are both handled as required.
- A final line without a newline is still read completely.

Do not rely solely on fixtures generated by the same serialization function as production code. If both the fixture writer and the reader misunderstand the format the same way, the test may still pass. For important formats, keep some independent sample fixtures created from the data source's schema.

## 10. Testing Missing Files and Invalid Sources

The input source may not exist, may be unreadable, or may change before the Job runs.

With FlatFileItemReader, strict mode is on by default and usually requires the resource to exist. You can test the missing file case:

~~~java
@Test
void missingFileFailsWhenStrictModeIsEnabled() {
    Path file = tempDir.resolve("does-not-exist.csv");
    FlatFileItemReader<CustomerRow> reader = createReader(file);

    assertThrows(
            IllegalStateException.class,
            () -> reader.open(new ExecutionContext()));
}
~~~

If the application configures strict(false), a missing file may be treated as an empty source depending on the reader. Use that mode only when the business truly considers a missing file valid.

Source cases to consider:

- Wrong path.
- File does not exist.
- Path points to a directory instead of a file.
- Read permission denied.
- Empty file or truncated file.
- File changes while the Job is running.
- Remote resource does not respond or times out.

Do not test OS access permissions by assuming a specific user across all CI environments. For this scenario, test via an abstraction or a mock resource, then add an appropriate environment test if needed.

## 11. Testing Paging Readers with Page Boundaries

With a reader reading a database by page, page size creates an important boundary. Suppose page size is 10; test data sets with 0, 1, 9, 10, 11, 20, and 21 records.

What to confirm:

- An empty first page ends properly.
- A partial page is read completely.
- When record count equals page size, no extra page with duplicate items is produced.
- When there are page size + 1 records, the first item of the next page is not skipped.
- The last page can be smaller than page size.
- Read order is stable across pages.

A paging query needs a deterministic order, usually including a unique key as the final criterion. If sorting by a non-unique column only, two records with the same sort value can swap order between pages, leading to omissions or duplicates in some situations.

For example, an integration test can read through the entire reader and compare IDs against the expected order:

~~~java
List<Long> actualIds = new ArrayList<>();
Long id;

while ((id = reader.read()) != null) {
    actualIds.add(id);
}

assertEquals(expectedIds, actualIds);
assertEquals(expectedIds.size(), new HashSet<>(actualIds).size());
~~~

The second assertion detects duplicate IDs in the results. With database readers, use a dedicated test database or an embedded database to control data, rather than relying on a shared environment database.

### Paging and Changing Data

If the database source changes while the reader switches pages, results may depend on isolation level, query, and pagination strategy. Tests should simulate adding or deleting data between page reads if the Job needs to process a consistent snapshot.

For large data, you can use an ascending key or keyset pagination to reduce offset-shifting risk. Whichever approach is used, clearly define the data set belonging to the run and the expected read order.

## 12. Testing Restart and ExecutionContext

Stateful readers need to be tested through the open/update/close lifecycle. A basic restart test:

1. Create a reader with a file containing multiple records.
2. Open the reader with an empty ExecutionContext.
3. Read one or more items.
4. Call update() to write the checkpoint to the context.
5. Close the reader.
6. Create a new reader with the same name and same source.
7. Open the new reader with the saved context.
8. Verify the next item is at the expected position.

Example:

~~~java
@Test
void resumesFromSavedExecutionContext() throws Exception {
    Path file = tempDir.resolve("restart.csv");
    Files.writeString(
            file,
            "id,name,email\n" +
            "1,Alice,alice@example.com\n" +
            "2,Bob,bob@example.com\n" +
            "3,Carol,carol@example.com\n",
            StandardCharsets.UTF_8);

    ExecutionContext context = new ExecutionContext();

    FlatFileItemReader<CustomerRow> firstReader = createReader(file);
    firstReader.open(context);

    try {
        assertEquals(1L, firstReader.read().getId());

        firstReader.update(context);
    } finally {
        firstReader.close();
    }

    FlatFileItemReader<CustomerRow> restartedReader = createReader(file);
    restartedReader.open(context);

    try {
        assertEquals(2L, restartedReader.read().getId());
        assertEquals(3L, restartedReader.read().getId());
        assertNull(restartedReader.read());
    } finally {
        restartedReader.close();
    }
}
~~~

This test simulates the reader saving state and being reopened with the same ExecutionContext. In a real application, Spring Batch coordinates calling update and saving the context at the Step checkpoint. Step integration tests further confirm the link between checkpoints, transactions, and the JobRepository.

Do not reuse the same ExecutionContext for a reader with a different name if you want to test normal restart state. A stable stream name is an important part of how the reader finds its saved state again.

### Testing Source Changes After a Checkpoint

After saving a checkpoint, try replacing the input file or modifying content at the saved position. The reader may resume from the old position but the data no longer matches the previous run.

If the Job requires an immutable source, store a checksum, file version, or data source code in JobParameters/metadata and verify it before restarting. Tests should confirm the Job rejects or handles per policy if the source no longer matches.

## 13. Testing Readers in an Actual Step

Standalone reader tests do not verify all chunk behavior. To check a reader called by a Step, use Spring Batch Test and launch the Job or Step with fixture data.

An integration test typically confirms:

- The reader is opened and closed properly.
- The Step reads all expected items.
- The processor receives the right items.
- The writer writes the right count and order.
- StepExecution has matching readCount, writeCount, and filterCount.
- The Step ends with the expected BatchStatus and ExitStatus.
- Restart uses the saved checkpoint.

You can use JobLauncherTestUtils to run the Job, or StepScopeTestUtils when you need to create a Step context for a StepScope bean. Exact utility names and configuration depend on the Spring Batch Test version used.

Example of checking Step results after running a Job:

~~~java
JobExecution execution =
        jobLauncherTestUtils.launchJob(parameters);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());

StepExecution stepExecution = execution.getStepExecutions()
        .stream()
        .filter(step -> "importCustomersStep".equals(step.getStepName()))
        .findFirst()
        .orElseThrow();

assertEquals(11, stepExecution.getReadCount());
assertEquals(11, stepExecution.getWriteCount());
~~~

The example above assumes no processor filtering, skips, or writer item drops. If those behaviors exist, adjust assertions according to actual rules. Integration tests should use a dedicated database and explicitly created data so results do not depend on previous runs.

## 14. Testing Custom Readers

If the application has a custom reader, test the specific scenarios of its reading algorithm.

Example reader reading by ascending ID from a repository:

~~~java
public class CustomerRepositoryReader implements ItemReader<Customer> {

    private final CustomerRepository repository;
    private long lastId;

    public CustomerRepositoryReader(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public Customer read() {
        Customer next = repository.findNextAfter(lastId);

        if (next == null) {
            return null;
        }

        lastId = next.getId();
        return next;
    }
}
~~~

Tests should cover:

- Repository has no data.
- Only one record.
- Multiple records with consecutive IDs.
- IDs with gaps.
- Two records with the same sort value.
- Last record right at a page limit.
- Repository query throws an exception.
- New data appears while the reader is running.
- Reader is reopened with an old checkpoint if it supports ItemStream.

Use Mockito to verify how the reader calls the repository:

~~~java
@Test
void returnsNullWhenRepositoryHasNoNextCustomer() {
    CustomerRepository repository = mock(CustomerRepository.class);
    when(repository.findNextAfter(0L)).thenReturn(null);

    CustomerRepositoryReader reader =
            new CustomerRepositoryReader(repository);

    assertNull(reader.read());

    verify(repository).findNextAfter(0L);
}
~~~

With stateful readers, test checkpoint restoration separately. Do not test only the number of returned items; verify ordering, query conditions, and that the reader does not skip or repeat records at boundaries.

## 15. Distinguishing Reader Errors from Processor Errors

Some errors appear close together in the pipeline yet belong to different layers:

| Situation | Layer that should be responsible |
|---|---|
| File does not exist | Reader or input validation step |
| CSV line missing a column | Reader/parser |
| ID cannot be converted to a number | Reader/FieldSetMapper if converted here |
| Email violates business rules | Processor or validator |
| Customer already exists | Processor or writer depending on rules |
| Database loses connection on insert | Writer/transaction infrastructure |
| Data is read repeatedly due to faulty paging | Reader/query |
| Data cannot restart | Reader state/ExecutionContext/JobRepository |

If a reader test is asserting a rule that belongs to the processor, tests become hard to understand and tightly coupled to implementation. Place assertions at the responsible component.

## 16. Organizing Maintainable Fixtures and Tests

A good reader test suite typically has:

- A factory creating the reader with production-like configuration.
- Small fixtures with clear names containing just the case under test.
- Separate tests for EOF, parsing, mapping, resources, and restart.
- Boundary data created in a temporary directory.
- Assertions on order and count, not just checking the first item.
- Resource cleanup in finally or try-with-resources if the abstraction supports it.
- Integration tests with an isolated database when the reader queries a database.

Do not cram all boundary inputs into one long test. When an assertion fails, the test name should point to which scenario failed, such as emptyFileReturnsEof or resumesFromSavedExecutionContext.

With many data variations, JUnit parameterized tests help reduce duplicate code. Still, each case needs a clear enough name or input data to read test results easily.

## 17. Common Testing Mistakes

### Checking Only the First Item

A reader might read the first item properly but miss the last item or repeat an item on the next page. Read through to EOF and compare the whole list.

### Not Calling close()

The reader opens a file or cursor but the test does not close the resource. This can leak file handles and cause flaky failures on CI.

### Testing Only Valid Files

Empty sources, header-only files, malformed lines, blank fields, and a final line without a newline are the cases that most easily uncover parser bugs.

### Confusing Chunk Size with the Number of Items the Reader Reads

The reader returns one item at a time. Chunk size governs how many items are gathered for one Step transaction cycle. Standalone reader tests cannot replace Step transaction tests.

### Using Fixtures Too Similar to Production Data Generation Code

If tests generate files using the same serializer logic under test, both sides may share the same formatting bug. Keep independent fixtures or explicitly written sample data.

### Not Checking Order

A paging reader might return the right item count but in the wrong order or with duplicate IDs. Verify that the actual ID list matches the expected order.

### Not Checking Restart State

A reader might read properly on the first run but fail to restore position after a Job restart. Test ItemStream and ExecutionContext if the reader needs to support restart.

## 18. Building a Test Matrix for a Reader

For a real reader, you can build a small matrix by data source and boundary:

| Group | Minimum cases | Main assertion |
|---|---|---|
| EOF | 0 items, 1 item | null at the right time |
| Count | N-1, N, N+1 | No missing or duplicate items |
| File | Missing, empty, header-only | Resource and EOF behavior |
| Parse | Missing column, extra column, wrong type | Exception or mapping per config |
| Text | Empty, whitespace, Unicode, long string | Value preserved/normalized properly |
| CSV | Quoted delimiter, escaped quote | Exact column boundaries |
| Paging | 0, 1, pageSize-1, pageSize, pageSize+1 | No items lost across pages |
| Restart | Save and reopen ExecutionContext | Resumes at exact position |
| Resource | Read complete, mid-way exception | close called and resources released |

You do not need hundreds of tests for every combination. Choose cases based on the data source's risks and the reader's logic branches. For complex parsers or unstable sources, add tests for each specific rule.

## 19. Process for Testing a Reader Before Putting It in a Job

A practical sequence:

1. Define the source's schema and EOF rules.
2. Write tests for empty source, single item, and N-1/N/N+1 boundary data.
3. Test parsing, data types, empty fields, and encoding.
4. Test missing sources or access errors.
5. Test ordering, paging, and end-of-page data.
6. If the reader is stateful, test open/update/close and restart.
7. Run the reader in a Step with a real transaction manager and writer, or an equivalent fixture.
8. Check StepExecution counters and final results.
9. Simulate mid-chunk failures to verify rollback and restart work as designed.

When a test fails, determine whether the bug lies in fetching data, parsing, mapping, paging, or state restoration. A reliable reader must return each item properly, preserve the defined order, signal EOF accurately, and behave clearly when input sources are at boundaries or invalid.
