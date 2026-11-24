# Small and Clear Test Data Files in Spring Batch Core Processing

When testing a batch job that reads data from files, a good test file usually has only **a few lines**, yet every line has a reason to exist. Small enough data lets readers immediately see the input, processing rules, and expected output; clear enough data helps pinpoint whether a failure originates from file structure, field mapping, business logic, chunk boundaries, or job restart behavior.

In Spring Batch, test files serve more than just `FlatFileItemReader`. They also act as input for testing `ItemProcessor`, `ItemWriter`, skip/retry mechanisms, checkpoints, and the overall `Step` outcome. This article explains how to design small, maintainable file **test fixtures** with explicit test expectations, using CSV as the running example.

## 1. What does a small and clear test file mean?

A **test fixture** is pre-prepared data used to execute a test case with predictable results. For file-reading batch jobs, a fixture can be `.csv`, fixed-width `.txt`, JSON, XML, or a custom system format.

A good fixture answers four questions:

1. **What does the file simulate?** For example: three valid orders, one row with an invalid amount, a header-only file.
2. **Which row tests which rule?** For example: row 3 contains a name with a comma to verify CSV quoting rules.
3. **What output must the job produce?** For example: write exactly three orders, preserve the customer name with the comma, and create no fourth record.
4. **When an error occurs, which layer does it belong to?** For example: an unparseable amount column is a read/mapping error; a negative amount may be a business validation error if defined as such by the system.

The goal is not to make files tiny at all costs. The goal is **the fewest lines needed to distinguish the behavior under test**. A test that only needs three rows should not haul along 10,000 anonymized production rows; conversely, pagination or high-volume load tests need datasets suited to that problem.

| Hard-to-understand test data | Clear, intentional test data |
|---|---|
| A `sample.csv` file containing 500 undescribed lines. | `orders-valid.csv` has 3 rows, each representing a specific case. |
| Random values, dates pulled from the current clock. | Deterministic IDs, fixed amounts and dates. |
| Multiple errors mixed in one file, unclear which error triggers first. | Each error file focuses on a single rule being tested. |
| Only asserting "job succeeded". | Verifying output records, matching read/write/skip counts, and step status. |
| Test depends on personal machine paths or files outside the repository. | Fixtures under `src/test/resources`, loaded as classpath resources. |

## 2. Define the data contract before creating files

Suppose a batch job receives a CSV list of orders with four fields:

| Column | Expected type | Rules in this example |
|---|---|---|
| `order_id` | String | Non-empty; acts as a stable order identifier. |
| `customer` | UTF-8 string | May contain spaces or commas when wrapped in double quotes per CSV syntax. |
| `amount` | Decimal number | Non-negative; dot as decimal separator, no thousands separators. |
| `order_date` | Date | ISO format `yyyy-MM-dd`; independent of the test runner's locale. |

Input conventions in this example:

- Files are saved in **UTF-8** encoding with a header row at the top.
- Commas `,` separate fields; double quotes `"` enclose fields containing commas.
- Each data row maps to one `OrderRow`; row order follows the file.
- `amount = 0.00` is considered valid; `amount < 0` is invalid per *this example's* business rules.
- The reader is configured to skip **one header line** via `linesToSkip(1)`.

Rules should be stated directly in the test or documentation next to the fixture. Without a contract, a file with `0`, empty fields, or commas inside names can be interpreted differently by the test author and someone modifying the processor.

## 3. Organize fixtures into separate files named after their purpose

Illustrative structure for a Maven or Gradle project:

~~~text
src/
  test/
    resources/
      batch/
        orders/
          orders-valid.csv
          orders-invalid-amount.csv
          orders-missing-column.csv
          orders-header-only.csv
          orders-duplicate-id.csv
        expected/
          orders-valid-output.csv
~~~

**You do not need every file in every project.** Only add a file when an actual test case uses it. Placing fixtures under `src/test/resources` packages them into the test classpath, avoiding reliance on absolute paths on a developer's machine.

### 3.1. Valid three-row fixture

`src/test/resources/batch/orders/orders-valid.csv`:

~~~csv
order_id,customer,amount,order_date
O-001,Lan,125000.50,2026-02-01
O-002,"Trần, An",0.00,2026-02-02
O-003,Mai,7500.00,2026-02-03
~~~

Intent of each line:

| Physical line in file | Notable content | What to verify |
|---|---|---|
| 1 | Header with four column names | Reader skips the header exactly once. |
| 2 | `O-001`, amount with two decimal places | Parser maps ID, name, amount, and date accurately. |
| 3 | `O-002`, name `"Trần, An"`, amount equal to 0 | Comma inside the name is not split into a new column; Unicode and boundary values are preserved properly. |
| 4 | `O-003` | Reader returns all three items and then terminates with `null`. |

A three-row file also works well for testing chunk boundaries when `chunkSize = 2`: two items belong to the first chunk, and the final item belongs to the next chunk. There is no need to generate hundreds of records just to observe more than one chunk.

### 3.2. Invalid-amount fixture

`src/test/resources/batch/orders/orders-invalid-amount.csv`:

~~~csv
order_id,customer,amount,order_date
O-004,Binh,abc,2026-02-04
~~~

Under the contract above, `abc` cannot be parsed into a `BigDecimal`. When the reader maps this line, the error occurs at the read/parse layer (typically wrapped by `FlatFileItemReader` in `FlatFileParseException`), before the processor can evaluate negative-amount rules.

This file has **one intentional error**. If you also changed the date to `tomorrow`, removed the ID, and broke the quotes at the same time, the test result would depend on whichever error is detected first, making the failure cause less clear.

### 3.3. Missing-column fixture

`src/test/resources/batch/orders/orders-missing-column.csv`:

~~~csv
order_id,customer,amount,order_date
O-005,Hoa,100.00
~~~

The data row has only three fields while the tokenizer configuration expects four. With `DelimitedLineTokenizer` in default strict mode, a field count mismatch triggers a parse error. This tests file structure, which differs from the data-type error in `orders-invalid-amount.csv`.

### 3.4. Header-only fixture

`src/test/resources/batch/orders/orders-header-only.csv`:

~~~csv
order_id,customer,amount,order_date
~~~

Expected outcome: the reader returns no items after skipping the header, and the step writes no orders. This file is useful when testing how a job handles empty data input. It is **different** from a completely empty (0-byte) file: whether a header is mandatory depends on how format validation is implemented, which `linesToSkip(1)` alone does not guarantee.

### 3.5. Duplicate business-key fixture

`src/test/resources/batch/orders/orders-duplicate-id.csv`:

~~~csv
order_id,customer,amount,order_date
O-006,An,100.00,2026-02-05
O-006,An,100.00,2026-02-05
~~~

Two identical rows raise an explicit question: will the writer insert duplicates, fail on a unique constraint, or perform an idempotent UPSERT? You cannot infer the behavior from the file alone; the test must state the business policy and assert the corresponding output state.

## 4. Wiring fixtures to FlatFileItemReader

A good test should use a parser close to the production parser so fixture data genuinely exercises file-reading rules. The example below uses Spring Batch 5.x, Java 17+, and `FlatFileItemReaderBuilder`:

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;

import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.core.io.ClassPathResource;

record OrderRow(
    String orderId,
    String customer,
    BigDecimal amount,
    LocalDate orderDate
) {}

class OrderReaderFactory {

    static FlatFileItemReader<OrderRow> fromTestResource(String filename) {
        return new FlatFileItemReaderBuilder<OrderRow>()
            .name("ordersTestReader")
            .resource(new ClassPathResource("batch/orders/" + filename))
            .linesToSkip(1)
            .delimited()
            .delimiter(",")
            .names("order_id", "customer", "amount", "order_date")
            .fieldSetMapper(fields -> new OrderRow(
                fields.readString("order_id"),
                fields.readString("customer"),
                fields.readBigDecimal("amount"),
                LocalDate.parse(fields.readString("order_date"))
            ))
            .build();
    }
}
~~~

Key details to understand:

- `ClassPathResource` loads files from `src/test/resources`, allowing tests to run from both IDE and CI without absolute paths.
- `linesToSkip(1)` skips the first line; it **does not automatically verify header column names**. If column names and order are a strict contract, add header validation logic (such as `skippedLinesCallback` or a dedicated header-check mechanism).
- `.names(...)` in the configuration above defines positional **column-to-field mapping**. If a real file reorders columns while keeping headers, the mapper can still misread data unless headers are validated.
- `fields.readBigDecimal(...)` and `LocalDate.parse(...)` expose data-type errors immediately while reading an item.
- `FlatFileItemReader` is stateful: when invoked directly in a test, call `open(ExecutionContext)` before reading and `close()` in a `finally` block.

When the application already defines a production reader bean, prefer testing that actual configuration, or use a shared factory whose `Resource` can be swapped. The snippet above is a self-contained configuration demonstrating how fixtures are read; it does not replace testing the production reader bean in integration tests.

## 5. Testing a few lines directly with JUnit 5

Not every file-data test needs to boot the entire job. Tokenizer and mapping verification can run at the reader level, making failures easier to localize. Example using JUnit 5 and AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileParseException;

class OrderFileReaderTest {

    @Test
    void readsThreeValidRowsExactly() throws Exception {
        FlatFileItemReader<OrderRow> reader =
            OrderReaderFactory.fromTestResource("orders-valid.csv");

        List<OrderRow> actual = new ArrayList<>();
        reader.open(new ExecutionContext());
        try {
            OrderRow row;
            while ((row = reader.read()) != null) {
                actual.add(row);
            }
        } finally {
            reader.close();
        }

        assertThat(actual).containsExactly(
            new OrderRow("O-001", "Lan",
                new BigDecimal("125000.50"), LocalDate.of(2026, 2, 1)),
            new OrderRow("O-002", "Trần, An",
                new BigDecimal("0.00"), LocalDate.of(2026, 2, 2)),
            new OrderRow("O-003", "Mai",
                new BigDecimal("7500.00"), LocalDate.of(2026, 2, 3))
        );
    }

    @Test
    void reportsInvalidAmountAsParseFailure() throws Exception {
        FlatFileItemReader<OrderRow> reader =
            OrderReaderFactory.fromTestResource("orders-invalid-amount.csv");

        reader.open(new ExecutionContext());
        try {
            assertThatThrownBy(reader::read)
                .isInstanceOf(FlatFileParseException.class);
        } finally {
            reader.close();
        }
    }

    @Test
    void headerOnlyFileHasNoItems() throws Exception {
        FlatFileItemReader<OrderRow> reader =
            OrderReaderFactory.fromTestResource("orders-header-only.csv");

        reader.open(new ExecutionContext());
        try {
            assertThat(reader.read()).isNull();
        } finally {
            reader.close();
        }
    }
}
~~~

The advantage of this style is that every assertion maps directly to the three or four lines in the file. For instance, if CSV splitting breaks `Trần, An`, the test displays both the actual read value and the expected value right at the second row.

Note: in Spring Batch, exceptions thrown by `LineMapper` are typically wrapped by the reader into `FlatFileParseException` containing line details. Testing a tokenizer directly without going through `FlatFileItemReader` can yield a different lower-level exception type; tests should assert errors at the **layer under test**.

## 6. Write output expectations as clearly as inputs

A test file alone does not make a valuable test without knowing what output counts as correct. For `orders-valid.csv`, expected post-processor output can be defined as follows:

Suppose the processor normalizes customer names with `trim()`, keeps amounts and dates intact, and the writer inserts each order into table `processed_order` keyed by `order_id`.

| `order_id` | Expected `customer` | Expected `amount` | Expected `order_date` |
|---|---|---|---|
| `O-001` | `Lan` | `125000.50` | `2026-02-01` |
| `O-002` | `Trần, An` | `0.00` | `2026-02-02` |
| `O-003` | `Mai` | `7500.00` | `2026-02-03` |

If the output is also CSV, you can store a dedicated expected fixture:

`src/test/resources/batch/expected/orders-valid-output.csv`:

~~~csv
order_id,customer,amount,order_date
O-001,Lan,125000.50,2026-02-01
O-002,"Trần, An",0.00,2026-02-02
O-003,Mai,7500.00,2026-02-03
~~~

Distinguish between **byte-level comparison** and **content-level comparison**:

- When byte format is part of the contract (for example UTF-8 encoding, line endings, column order, exact quoting), full-file comparison can be useful.
- When business data is the goal, parse the output file back into records and compare values. That way, CRLF/LF differences or equivalent decimal representations do not cause spurious failures outside the test's scope.
- When output order is not guaranteed (for example parallel writes, DB queries without `ORDER BY`), compare by key or record set rather than assuming fixed ordering.

Never "accept anything" by asserting only that the file exists or has at least one line. Tests must specify **verifiable record counts and values**.

## 7. Test files and chunk boundaries

Spring Batch typically processes read → process → write in chunks. Small file data can still exercise the important cases:

| Goal | Recommended item count | Example configuration |
|---|---:|---|
| Empty data file | 0 | Header-only; assert no items were written. |
| Fewer than one chunk | 1 | `chunkSize = 2`, one valid order. |
| Exactly one chunk | 2 | `chunkSize = 2`, two orders. |
| Across chunk boundary | 3 | `chunkSize = 2`, three orders. |
| Error at start of input | 1 error | Verify parse/validation failure and step status. |
| Error after first chunk commits | 2 valid + 1 error | `chunkSize = 2`; verify effect of committed chunk and failure handling on the next chunk. |

With the three-row fixture in section 3 and `chunkSize = 2`, a successful run processes two items in the first chunk and one item in the final chunk. This suffices to examine **logical data boundaries**, though you should not deduce exact transaction/commit counts for every framework setup purely from row counts; measurements should rely on the actual step configuration and `StepExecution`.

When testing rollback or restart:

1. Use fixtures with fixed IDs `O-001`, `O-002`, `O-003` so you know precisely which items were written.
2. Inject an intentional failure at an item past a chunk boundary, using either fixture data or a deterministic test dependency.
3. After the step fails, query the DB to inspect data from the committed chunk and the rolled-back chunk.
4. Restart the same `JobInstance` using standard Spring Batch mechanics and verify the overall output has **no duplicates and no missing records**.

Avoid "reading 100,000 rows for a high probability of hitting an error"; restart tests require a **deterministic failure position** and consistent reproducibility.

## 8. Separating format errors, parse errors, and business errors

Different error categories deserve separate fixtures because they exercise different Spring Batch paths:

| Scenario file | Example value | Layer typically catching it | Expectation to define |
|---|---|---|---|
| Missing field | `O-005,Hoa,100.00` | Tokenizer/reader | Parse failure or read skip if configured. |
| Invalid amount | `amount=abc` | FieldSetMapper/reader | Data conversion exception. |
| Invalid date | `2026-02-30` | Mapper/reader | Date parse exception. |
| Negative amount | `amount=-1.00` | Processor/validator if rule lives there | Reject, filter, or skip per business contract. |
| Duplicate ID | Two rows with same `order_id` | Writer/database or deduplication logic | One record, unique key error, or specific duplicate-handling policy. |
| Quoted comma field | `"Trần, An"` | Tokenizer | A single customer value. |
| Blank line | Empty line between items | Reader/record separator per config | Must define whether to skip, fail, or treat as empty item. |

For instance, testing `skip(FlatFileParseException.class)` is not equivalent to testing `skip(ValidationException.class)`. If the parser fails first, the processor is never called. Separating fixtures ensures tests exercise the exact branch under verification.

For a file containing both valid rows and an invalid row, explicitly describe expectations **after skipping**: read count, read/process/write skip counts, and the exact list of written IDs. Counters depend on how Spring Batch defines each phase; do not lump all errors into a vague "records failed" number.

## 9. Small details that make test files flaky

### 9.1. Encoding and Unicode characters

Create fixtures in UTF-8; if the production reader configures a specific encoding, tests must use that same encoding. Values like `Nguyễn`, `Trần, An` help catch stripped diacritics or broken separator handling. Whether a **UTF-8 BOM** is present must also be decided explicitly, since a BOM can alter the first token if not handled properly.

You do not need every Unicode edge case in one file. You can keep one standard fixture containing Vietnamese diacritics and a separate fixture for BOM if that is an actual integration requirement.

### 9.2. Delimiters, quoting, and line endings

A name `"Trần, An"` checks quoted-comma rules; values containing double quotes may need CSV escaping, such as `"An ""VIP"""` when doubled quotes are used. Do not build tests using `split(",")`, as that splits quoted fields containing commas incorrectly.

CRLF and LF are generally handled by readers as common line endings, yet tests asserting exact **output bytes** must specify the expected line ending. If business tests do not care about line endings, avoid verbatim byte comparisons.

### 9.3. Whitespace and empty fields

Clearly distinguish three cases:

~~~csv
order_id,customer,amount,order_date
O-011," An ",1.00,2026-02-11
O-012,,1.00,2026-02-12
O-013,"",1.00,2026-02-13
~~~

The first example preserves spaces inside the string, while the remaining two may both map to empty strings depending on the parser. If business rules require distinguishing `null` from an empty string, specify and test its file representation explicitly; plain CSV has no universal `null` convention across all systems.

### 9.4. Fixed values and environment independence

Do not build test files relying on:

- Current time (`now()`), default timezone, or default locale.
- UUIDs and unseeded random values.
- Paths like `C:\Users\...\orders.csv` or a shared mutable file.
- Real data containing sensitive personal or business information.
- Leftover results from earlier test runs or an uncleaned shared database.

Use synthetic IDs, fixed dates, and explicit amounts. If a test requires generated data, fix the seed, bound the scope, and log enough context to reproduce failures.

### 9.5. Input files are immutable

Fixtures in `src/test/resources` should be treated as **read-only inputs**. Test writers must output to a temporary directory (such as JUnit's `@TempDir`) or an isolated test database; never overwrite repository fixtures. This prevents a second run from seeing data modified by the first run.

If multiple tests reuse the same fixture file, they stay independent as long as each test creates a fresh reader instance, its own `ExecutionContext`, and separate output targets. Never share an open `FlatFileItemReader` across tests running in parallel.

## 10. Designing fixture sets by test layer

Not every layer needs the same amount of data:

| Test layer | Appropriate data | Key focus |
|---|---|---|
| Unit test for tokenizer/mapper | 1–3 rows | Columns, quotes, data types, line numbers on error. |
| Unit test for processor | Java objects constructed directly or 1–2 rows from fixture | Business rules: normalization, filtering, validation. |
| Reader + processor integration test | 2–4 rows | Per-row transformation results, no dropped items. |
| Step integration test | 3–5 rows with small chunk size | Final output, rollback/skip, step status. |
| Restart/idempotency test | Few rows, fixed failure position | What committed before crash and how re-processing behaves. |
| Performance/load test | Large dataset or dedicated generator | Throughput, memory, I/O; do not force small fixtures to measure load. |

These counts are **rules of thumb**, not limits imposed by Spring Batch. When scenarios require many independent cases, use multiple small fixtures with parameterized tests instead of one giant file.

### A maintainable test case matrix

| Suggested test name | Fixture | Primary expectation |
|---|---|---|
| `readsThreeValidRowsExactly` | `orders-valid.csv` | Three objects mapped accurately in order. |
| `readsQuotedCustomerName` | `orders-valid.csv` | `Trần, An` is a single field. |
| `rejectsInvalidAmount` | `orders-invalid-amount.csv` | Parse error when reading row with `abc`. |
| `rejectsMissingColumn` | `orders-missing-column.csv` | Invalid field count detected. |
| `handlesHeaderOnlyInput` | `orders-header-only.csv` | Zero output items. |
| `handlesDuplicateOrderIdAccordingToPolicy` | `orders-duplicate-id.csv` | Duplicate key behavior matches writer design. |
| `processesPartialLastChunk` | `orders-valid.csv`, chunk size 2 | All three items processed, including the single-row final chunk. |

Test names should describe **behavior**. File names should describe the **data scenario**. Combined, they let anyone modifying code grasp the impact of a change without reading hundreds of data rows.

## 11. When to construct data in code instead of saving files?

Small fixtures in the repository shine when testing **real file syntax**: delimiters, headers, encoding, escaping, and line endings. However, not all test data has to live in files:

- Testing algorithms in `ItemProcessor`: constructing `OrderRow` directly in code is faster and easier to read.
- Testing many boundary values of a single field: JUnit parameterized tests over a handful of arguments work cleanly.
- Testing a million rows or throughput: generate test files in a temporary directory with a fixed seed instead of committing huge files.
- Testing a writer/database: seed the test database with minimal data and inspect table state directly.

The rule of thumb is to **keep data in the form that reflects the system boundary under test**. If the bug to catch is CSV quoting, use a real CSV file. If the bug to catch is fee calculation, a Java object representing the amount and order type is usually clearer than running through the entire file-reading pipeline.

## 12. Walking through an end-to-end test case

Suppose `importOrdersStep` performs three tasks: reads a CSV file, checks `amount >= 0`, and writes valid records to the database. To test the happy path with `chunkSize = 2`:

**Input:** `orders-valid.csv` containing three data rows with IDs `O-001`, `O-002`, `O-003`.

**Pre-run expectations:** the test database does not yet contain those IDs; the reader uses the right resource; UTF-8 encoding and tokenizer rules are defined.

**Post-run expectations:**

1. Step finishes with `BatchStatus.COMPLETED`.
2. Target table holds exactly three orders matching the expected IDs and amounts.
3. Customer name `Trần, An` is preserved, and `amount = 0.00` is not dropped since the rule allows zero.
4. The header row does not appear as an order.
5. No fourth record or duplicate IDs exist.

For the failure case `orders-invalid-amount.csv`, assert either step failure or skip according to the configured policy. Never write a test asserting "either FAILED or COMPLETED is fine"; each test requires a concrete outcome tied to the step's actual retry/skip configuration.

When extending to restart testing, create a dedicated case with minimal data so a reader can list the exact records committed before the failure and the exact records expected after restart. This separates data bugs, chunk orchestration bugs, and idempotency bugs.

## 13. Practical checklist when preparing test files

Before adding a new fixture, answer:

1. **Does one file have one clearly nameable purpose?** If it mixes unrelated errors, split it.
2. **Can a reader predict the outcome within seconds of viewing the file?** If not, trim rows or state expectations explicitly.
3. **Does the data exercise the exact boundary under test?** For example, testing chunk size 2 may only need three rows.
4. **Does each field have fixed types and formatting rules?** ISO dates, decimal points, encoding, headers, quoting, and empty fields.
5. **Will the file run reliably on CI and other machines?** Use classpath resources, fixed synthetic data, and avoid personal paths or shared state.
6. **Do expectations validate actual business semantics?** Compare IDs, counts, and output contents; check skips/restarts where applicable.

**Remember:** An effective Spring Batch test file does not need many records. A three-row CSV with a clear intent, a defined column contract, and concrete output expectations usually catches bugs more accurately than a large, unwieldy file. When testing batch jobs with chunks, rollbacks, skips, or restarts, design additional small fixtures with errors placed at known positions; it is this ability to explain every row and reproduce results that defines high-quality test data.
