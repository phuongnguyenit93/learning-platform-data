# SearchHitsIterator and Closing the Iterator After Use

When reading or exporting a large volume of documents from Elasticsearch, loading all results into a `List` can cause the application to consume excessive memory. Spring Data Elasticsearch provides `SearchHitsIterator<T>` to iterate through results hit by hit. This API is typically obtained from `ElasticsearchOperations.searchForStream(...)` and fits sequential processing flows such as file exports, data synchronization, or per-document processing.

The most critical rule when using `SearchHitsIterator` is managing the iterator's lifecycle. It is a resource that can hold a search context open in Elasticsearch while iterating data. Once finished, the application must close the iterator to release both client-side and server-side resources. The safest, clearest approach is `try-with-resources`; where that construct cannot be used, call `close()` in a `finally` block.

## 1. Why Do We Need SearchHitsIterator?

A standard query returns `SearchHits<T>` containing the hits of a single search. This works well when the result count is moderate and the application needs to keep them for display, processing, or pagination.

When processing tens of thousands or millions of documents, collecting all results in memory can cause:

- Heap usage to climb rapidly with document count and size.
- Frequent garbage collection pauses.
- Higher risk of `OutOfMemoryError`.
- High latency from waiting to load and convert many results before starting processing.

`SearchHitsIterator<T>` lets you read one `SearchHit<T>` on demand. The application processes a hit and moves to the next without retaining the entire result set in a large collection.

High-level flow:

~~~text
ElasticsearchOperations
        |
        | searchForStream(query, entityClass, index)
        v
SearchHitsIterator<T>
        |
        | hasNext() / next()
        v
SearchHit<T>
        |
        | getContent()
        v
Java Entity
        |
        v
Process / write file / send to another system
        |
        v
close() iterator
~~~

The name `searchForStream` may lead readers to think the API returns `java.util.stream.Stream<T>`. In fact, it returns `SearchHitsIterator<T>`, a closeable iterator. It is neither a preloaded collection nor a standard Java Stream.

## 2. SearchHitsIterator and SearchHit

`SearchHitsIterator<T>` iterates over search results. Each call to `next()` returns a `SearchHit<T>`, containing the converted entity alongside result metadata.

A `SearchHit<T>` can provide:

- `getContent()`: the converted Java entity.
- `getId()`: the Elasticsearch document ID.
- `getScore()`: relevance score, if applicable.
- `getIndex()`: name of the index containing the document.
- `getSortValues()`: sort values of the hit when the query specifies sorting.
- Highlight details and other metadata depending on the query and version.

Example:

~~~java
while (iterator.hasNext()) {
    SearchHit<Product> hit = iterator.next();

    Product product = hit.getContent();
    String id = hit.getId();
    float score = hit.getScore();

    process(product, id, score);
}
~~~

The iterator yields `SearchHit<Product>` rather than bare `Product` so the application can access both document content and search metadata. If you only need the entity, call `hit.getContent()`. If you need to export the ID, score, or index name, read metadata from the hit.

## 3. Creating an Iterator with searchForStream

`ElasticsearchOperations` provides `searchForStream(...)` to start streaming results. Example:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHitsIterator;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

public class ProductExportService {

    private final ElasticsearchOperations operations;

    public ProductExportService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void exportActiveProducts() {
        Query query = new CriteriaQuery(
                new Criteria("status").is("ACTIVE")
        );

        SearchHitsIterator<Product> iterator =
                operations.searchForStream(
                        query,
                        Product.class,
                        IndexCoordinates.of("products")
                );

        // Iterate over results here.
    }
}
~~~

`searchForStream` accepts a query, target entity class, and `IndexCoordinates`. Spring Data uses mapping metadata to convert `_source` into `Product`. `IndexCoordinates` can point to the target index or alias the application wants to search.

What is conspicuously missing in the snippet above is closing the iterator. Never create an iterator and leave it unclosed; wrap it in `try-with-resources` as shown next.

## 4. Closing the Iterator with try-with-resources

This is the recommended approach:

~~~java
public void exportActiveProducts() {
    Query query = new CriteriaQuery(
            new Criteria("status").is("ACTIVE")
    );

    try (SearchHitsIterator<Product> iterator =
                 operations.searchForStream(
                         query,
                         Product.class,
                         IndexCoordinates.of("products")
                 )) {

        while (iterator.hasNext()) {
            SearchHit<Product> hit = iterator.next();
            Product product = hit.getContent();

            exportOne(product);
        }
    }
}
~~~

When execution leaves the `try` block, Java automatically invokes `close()` on the iterator. This happens in all scenarios:

- Normal completion of iteration.
- A `return` statement inside the `try` block.
- Early loop exit via `break`.
- `exportOne(...)` throwing an exception.
- An error occurring during `hasNext()` or `next()`.

`SearchHitsIterator` implements the closeable iterator contract (`CloseableIterator` in Spring Data). This contract enables `try-with-resources` just like other Java resources.

### 4.1. Why Not Rely Solely on Reaching the End of the Loop?

`hasNext()` returning `false` indicates there are no more hits to iterate. It does not replace your responsibility to close the iterator. The iterator may hold a scroll/search context or request-related resources. Always close it explicitly, even after reaching the end.

### 4.2. Closing on Early Exit

For example, finding and processing at most 100 documents:

~~~java
try (SearchHitsIterator<Product> iterator =
             operations.searchForStream(
                     query,
                     Product.class,
                     IndexCoordinates.of("products")
             )) {

    int processed = 0;

    while (iterator.hasNext() && processed < 100) {
        Product product = iterator.next().getContent();
        exportOne(product);
        processed++;
    }
}
~~~

When the limit is reached and the `try` block exits, the iterator is still closed. This is especially vital for workflows with early-stop conditions.

## 5. Closing the Iterator with try-finally

If the code structure cannot use `try-with-resources`, call `close()` inside `finally`:

~~~java
SearchHitsIterator<Product> iterator =
        operations.searchForStream(
                query,
                Product.class,
                IndexCoordinates.of("products")
        );

try {
    while (iterator.hasNext()) {
        Product product = iterator.next().getContent();
        exportOne(product);
    }
} finally {
    iterator.close();
}
~~~

The `finally` block runs when the loop ends, on `return`, or when an exception propagates outward. However, whenever possible, `try-with-resources` is more concise and less error-prone.

Do not write code that calls `close()` only after the loop:

~~~java
// Unsafe if processing throws an exception or returns before the close line.
while (iterator.hasNext()) {
    process(iterator.next());
}
iterator.close();
~~~

If `process(...)` throws an exception, the `close()` line at the end of the method never runs. This is why structured resource management is mandatory.

## 6. The Iterator Typically Uses a Scroll Context

In common Spring Data Elasticsearch implementations, `searchForStream(...)` is backed by the scroll mechanism to fetch results in batches. Scroll keeps a search context on Elasticsearch so subsequent fetches continue reading the same result set as of the initial state.

High-level flow:

1. Spring Data sends the initial query and receives the first batch.
2. The iterator yields each hit from the batch.
3. When more results are needed, the implementation issues the next scroll request.
4. Elasticsearch returns the next batch.
5. When the iterator is closed, the scroll context is released per the implementation.

The application does not need to invoke the scroll API directly for each batch when using this abstraction. Nonetheless, remember that the iterator is not an in-memory list: iterating can continue issuing network requests.

### 6.1. Search Contexts Consume Resources

A scroll context holds search state and can keep old segments pinned to continue reading. Many long-lived scroll contexts can place pressure on Elasticsearch nodes.

Therefore:

- Close the iterator immediately once processing finishes.
- Set a scroll retention duration just long enough for the processing rate.
- Avoid opening an iterator and leaving it idle while waiting for user actions.
- Avoid creating an unbounded number of concurrent iterators.
- Cap the number of concurrent export streams.
- Monitor processing times and network errors to catch iterators staying open too long.

Scroll/keep-alive durations and configuration options can vary across Spring Data Elasticsearch versions. Use the query API matching your project's version and do not assume a particular method exists across every release train.

## 7. Processing Hit by Hit Without Accumulating Everything

The primary purpose of the iterator is processing one hit or one small batch at a time. Example writing rows to a writer:

~~~java
public void exportProducts(Writer writer) throws IOException {
    Query query = new CriteriaQuery(
            new Criteria("status").is("ACTIVE")
    );

    try (SearchHitsIterator<Product> iterator =
                 operations.searchForStream(
                         query,
                         Product.class,
                         IndexCoordinates.of("products")
                 )) {

        while (iterator.hasNext()) {
            Product product = iterator.next().getContent();

            writer.write(product.getId());
            writer.write(",");
            writer.write(escapeCsv(product.getName()));
            writer.write(",");
            writer.write(product.getPrice().toPlainString());
            writer.write(System.lineSeparator());
        }
    }
}
~~~

This example focuses on iterating and closing the iterator. In production CSV export code, handle nulls, comma/quote escaping, character encoding, and writer closure according to resource ownership. If the writer is passed in from outside, the service should establish clearly which party owns closing it.

### 7.1. Processing in Small Batches

Some systems need to group a few hundred records to write to a database or call a target API. You can accumulate a bounded batch:

~~~java
int batchSize = 500;
List<Product> batch = new ArrayList<>(batchSize);

try (SearchHitsIterator<Product> iterator =
             operations.searchForStream(
                     query,
                     Product.class,
                     IndexCoordinates.of("products")
             )) {

    while (iterator.hasNext()) {
        batch.add(iterator.next().getContent());

        if (batch.size() == batchSize) {
            targetService.writeBatch(new ArrayList<>(batch));
            batch.clear();
        }
    }

    if (!batch.isEmpty()) {
        targetService.writeBatch(new ArrayList<>(batch));
    }
}
~~~

Memory usage now scales with `batchSize` rather than total document count. If `writeBatch` throws an exception, `try-with-resources` still closes the iterator.

Do not pick an overly large batch without measuring. The right size depends on entity size, target system speed, request limits, and heap capacity.

## 8. Distinguishing SearchHitsIterator from SearchHits and Java Stream

| Characteristic | SearchHits | SearchHitsIterator | Java Stream |
|---|---|---|---|
| Form | Materialized search results | Iterator reading hits lazily | Element-processing pipeline |
| Traversal | Loop over pre-fetched results | `hasNext()` / `next()` | Stream operations |
| Memory | Depends on loaded hits | Can be bounded per batch | Depends on source and pipeline |
| Hit metadata | Yes | Yes, via each `SearchHit` | Depends on source elements |
| Resource closure | Does not normally hold a scroll iterator | Must be closed | Must be closed only if the stream source holds resources |
| Use case | Moderately sized result pages | Exporting or scanning many documents | Processing data from a Stream source |

Do not call `iterator.forEachRemaining(...)` and forget to close the iterator. Even if convenience methods exhaust all hits, the duty to release resources remains.

### 8.1. Do Not Convert the Iterator to a List When Saving Memory

The following defeats the purpose of streaming:

~~~java
List<Product> allProducts = new ArrayList<>();

try (SearchHitsIterator<Product> iterator =
             operations.searchForStream(query, Product.class, index)) {
    while (iterator.hasNext()) {
        allProducts.add(iterator.next().getContent());
    }
}
~~~

The iterator is closed properly, yet every entity is retained in `allProducts`. With large indices, heap usage can still grow to unsafe levels.

Process each hit individually, write it out to a file, or send it in bounded batches. Convert to a `List` only when the maximum result count is strictly known to be small.

## 9. Exception Handling During Iteration

Errors can happen at multiple points:

- Opening the initial query fails.
- Fetching the next batch times out or loses connectivity.
- Mapping `_source` to the entity encounters a conversion error.
- Document processing code throws an exception.
- The target system rejects a batch or file writing fails.

`try-with-resources` ensures `close()` is called once the iterator has been created successfully. It does not make failing operations succeed automatically, nor does it guarantee resumption from the exact spot after a scroll request fails.

Example logging errors:

~~~java
public void exportProducts() {
    Query query = new CriteriaQuery(
            new Criteria("status").is("ACTIVE")
    );

    try (SearchHitsIterator<Product> iterator =
                 operations.searchForStream(
                         query,
                         Product.class,
                         IndexCoordinates.of("products")
                 )) {

        while (iterator.hasNext()) {
            SearchHit<Product> hit = iterator.next();
            process(hit.getContent());
        }
    } catch (RuntimeException exception) {
        log.error("Export products from Elasticsearch failed", exception);
        throw exception;
    }
}
~~~

Do not swallow exceptions and report the export as successful. If a batch fails, determine whether the job can be safely retried and record progress in the coordinating system if needed.

### 9.1. Per-Document Error Handling

If one bad document should not halt the entire export, wrap the per-hit processing in a `try/catch`:

~~~java
try (SearchHitsIterator<Product> iterator =
             operations.searchForStream(query, Product.class, index)) {

    while (iterator.hasNext()) {
        SearchHit<Product> hit = iterator.next();

        try {
            process(hit.getContent());
        } catch (RecoverableRecordException exception) {
            recordFailure(hit.getId(), exception);
        }
    }
}
~~~

Catch only exception types the application can genuinely handle. Avoid catching broad `Exception` and continuing when the error may reflect a system failure, connection loss, or untrustworthy data state.

## 10. Do Not Share One Iterator Across Multiple Threads

`SearchHitsIterator` is a stateful cursor tracking current position, buffered batch, and scroll state. Never let multiple threads call `hasNext()` or `next()` concurrently on one iterator unless the API explicitly guarantees thread safety.

To increase throughput:

- Partition work into independent queries with clear boundaries.
- Cap the number of threads and simultaneously open iterators.
- Have each worker own and close its own iterator.
- Avoid overlapping queries that cause duplicate processing.
- Monitor load on Elasticsearch and the destination system.

Do not create a single iterator and share it across tasks in an executor. Doing so can break ordering, drop items, or cause duplicate processing.

## 11. Choosing Batch Size and Scroll Retention Time

Batch size is the number of hits Elasticsearch returns per fetch. Smaller batches lower per-fetch memory usage at the cost of more requests; larger batches cut round-trips at the cost of higher heap usage and longer per-batch processing.

When choosing a batch size:

1. Measure the average size of `_source` and the converted entity.
2. Benchmark several batch sizes in a production-like environment.
3. Monitor heap, GC, request latency, and throughput.
4. Check the consumption speed of the target system.
5. Pick a setting with safety headroom as data grows.

Scroll keep-alive is how long Elasticsearch retains the search context between scroll calls. It must be long enough for the application to process a batch and request the next one. If too short, the context may expire before the next request; if too long, resources remain pinned when a worker stalls or stops.

Do not set `keep_alive` indefinitely to hide slow processing. Measure batch durations, detect stalled workers, and close the iterator when a task is cancelled.

## 12. SearchHitsIterator vs. Other Pagination Choices

Not every large-read scenario calls for `SearchHitsIterator`. Pick the approach matching your goal:

| Need | Commonly suited mechanism |
|---|---|
| Displaying a small page to a user | `SearchHits` or `Pageable` |
| Sequential traversal, processing/exporting many documents | `SearchHitsIterator` via `searchForStream` |
| Deep cursor pagination for a user-facing API | `search_after`, typically combined with PIT |
| Large traversal needing a stable cursor order | `PIT + search_after` |
| Aggregating/processing an entire dataset | Streaming or batch jobs with checkpoints |

Scroll is usually suited for batch tasks scanning a result set. `search_after` fits cursor pagination and deep pagination. PIT keeps pages reading a consistent data view. These abstractions have overlapping goals but should not be treated as drop-in replacements in all situations.

### 12.1. Why Not Use Pageable to Export Millions of Documents?

`Pageable` is typically based on offset pagination. As page numbers increase, `from` grows and query cost escalates. Elasticsearch also enforces the result window limit on `from + size`.

For full data exports, fetching page 0, page 1, page 2 sequentially is inefficient. `SearchHitsIterator` or `PIT + search_after` fits better depending on ordering, consistency, and checkpointing needs.

### 12.2. When to Choose PIT + search_after Instead of an Iterator?

Choose `PIT + search_after` when:

- The client needs a cursor to resume across multiple HTTP requests.
- Users may pause and resume within the PIT's lifetime.
- You need to persist sort values of the last hit explicitly.
- You require explicit control over ordering and a consistent snapshot across pages.

Choose `SearchHitsIterator` when a single application process owns the entire traversal lifecycle, processes sequentially, and closes the iterator within the same job.

## 13. Complete Example: Batch Exporting and Safe Closure

The following example shows a service processing active products in batches. Each batch is sent to the target system; the iterator is always closed whether processing succeeds or fails.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHitsIterator;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductExportService {

    private static final int BATCH_SIZE = 500;

    private final ElasticsearchOperations operations;
    private final ProductTargetService targetService;

    public ProductExportService(
            ElasticsearchOperations operations,
            ProductTargetService targetService
    ) {
        this.operations = operations;
        this.targetService = targetService;
    }

    public void exportActiveProducts() {
        Query query = new CriteriaQuery(
                new Criteria("status").is("ACTIVE")
        );

        List<Product> batch = new ArrayList<>(BATCH_SIZE);

        try (SearchHitsIterator<Product> iterator =
                     operations.searchForStream(
                             query,
                             Product.class,
                             IndexCoordinates.of("products")
                     )) {

            while (iterator.hasNext()) {
                SearchHit<Product> hit = iterator.next();
                batch.add(hit.getContent());

                if (batch.size() == BATCH_SIZE) {
                    targetService.writeBatch(new ArrayList<>(batch));
                    batch.clear();
                }
            }

            if (!batch.isEmpty()) {
                targetService.writeBatch(new ArrayList<>(batch));
            }
        }
    }
}
~~~

`new ArrayList<>(batch)` creates a copy of the batch before passing it to the target service. This prevents `batch.clear()` from mutating a list that the target service may still reference. If `writeBatch` executes synchronously without retaining the list reference, you can pass it in accordance with the service's contract.

In a production export, also consider:

- Recording checkpoints or progress to track what has been processed.
- Designing target operations to be idempotent so retries do not duplicate data.
- Tracking counts of succeeded and failed documents.
- Handling task cancellation signals so the `try` block exits and closes the iterator.
- Setting timeout limits and retry caps.

## 14. Testing Iterator Closure

Closing the iterator is part of the behavior you should test, especially when the job can exit early or throw an exception.

Key scenarios:

| Scenario | Expectation |
|---|---|
| Normal completion | `close()` is called |
| Exit via `break` | `close()` is called |
| `return` inside `try` | `close()` is called |
| Document processing throws exception | `close()` is called |
| `hasNext()` or `next()` throws exception | `close()` is called |
| Iterator opens successfully but target batch fails | `close()` is called |

You can mock a `CloseableIterator` in a unit test to verify `close()` is called when the service finishes. However, unit tests cannot verify that the actual scroll context on Elasticsearch was freed. For critical flows, write integration tests against an Elasticsearch instance matching your project's Spring Data version and observe scroll closure behavior.

### 14.1. Conceptual Test Example

~~~java
@Test
void closesIteratorWhenProcessingFails() {
    SearchHitsIterator<Product> iterator = mock(SearchHitsIterator.class);

    when(iterator.hasNext()).thenReturn(true, false);
    when(iterator.next()).thenReturn(searchHit);

    when(operations.searchForStream(
            any(Query.class),
            eq(Product.class),
            any(IndexCoordinates.class)
    )).thenReturn(iterator);

    doThrow(new IllegalStateException("target failed"))
            .when(targetService).writeBatch(anyList());

    assertThrows(
            IllegalStateException.class,
            () -> service.exportActiveProducts()
    );

    verify(iterator).close();
}
~~~

This example demonstrates the testing approach; exact method signatures and mocking depend on the specific service. The key point is verifying `close()` is invoked when processing throws an exception, not only when the loop completes normally.

## 15. Common Mistakes

### 15.1. Forgetting to Close the Iterator

This is the most critical mistake. Scroll/search contexts can continue holding resources on Elasticsearch. Wrap every created iterator in `try-with-resources`.

### 15.2. Closing Only After the Loop

If an exception or `return` occurs before the `close()` line, resources are not freed. Use `try-with-resources` or `finally`.

### 15.3. Collecting All Results into a List

Doing so makes heap usage scale with total document count and defeats streaming. Process hit by hit or in bounded batches.

### 15.4. Assuming the Iterator Only Reads In-Memory Data

Calling `next()` can trigger the implementation to fetch the next batch over the network. Plan for timeouts, retries, and connection errors during iteration.

### 15.5. Using the Iterator Like a Java Stream

`SearchHitsIterator` implements the `hasNext()`/`next()` and `close()` contract. Do not assume it supports `map`, `filter`, or `parallel` operations from Java Stream.

### 15.6. Sharing an Iterator Across Threads

The iterator maintains traversal state and must not be used concurrently by multiple threads. Each task should own its own iterator.

### 15.7. Holding an Iterator Open While Waiting on External Actions

For instance, opening an iterator and waiting for user confirmation before continuing can hold a scroll context open far too long. Close the iterator after each operation or design separate cursor pagination for user sessions.

### 15.8. Ignoring Destination Write Errors

If a batch fails and the application still reports the export as successful, data may be lost. Record checkpoints, counts, and error status; retry only when the target operation is safe to replay.

## 16. Workflow for Using SearchHitsIterator

A sound export workflow:

1. Identify the index or alias and the query to iterate.
2. Select the entity class so Spring Data converts `_source`.
3. Pick a batch size suited to heap capacity and the destination system.
4. Open the iterator with `searchForStream(...)`.
5. Immediately place the iterator inside `try-with-resources`.
6. Iterate over `SearchHit<T>` using `hasNext()` and `next()`.
7. Process `getContent()` or hit metadata.
8. Send each record or bounded batch to the destination system.
9. Track progress and handle errors per your retry policy.
10. Let `try-with-resources` close the iterator on completion, early exit, `return`, or exception.

If the requirement is user-facing deep pagination, consider `PIT + search_after` rather than holding an iterator/scroll context open across long HTTP sessions.

## 17. Conclusion

`SearchHitsIterator<T>` allows Spring Data Elasticsearch to iterate search results hit by hit as `SearchHit<T>`, suited for exporting or processing large numbers of documents without loading all results into a collection. This API is typically created via `ElasticsearchOperations.searchForStream(...)`.

Because the iterator can hold a search/scroll context on Elasticsearch, it must be closed after use. Use `try-with-resources` to guarantee `close()` runs on completion, early exit, `return`, or exception. Where that construct cannot be used, call `close()` in `finally`.

Process hit by hit or in bounded batches, cap concurrent iterators, and monitor context retention times. `SearchHitsIterator` fits batch processes that own the entire traversal lifecycle; `search_after` combined with PIT is better suited for cursor pagination spanning multiple requests. Closing the iterator is a mandatory part of the design, not an optional cleanup step.
