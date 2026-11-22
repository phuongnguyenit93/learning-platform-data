# Processor timeout

Trong Spring Batch, ItemProcessor xử lý từng item giữa reader và writer. Processor có thể chuẩn hóa dữ liệu, kiểm tra nghiệp vụ, gọi repository hoặc truy vấn một dịch vụ bên ngoài để bổ sung thông tin. Nếu một lần xử lý bị treo hoặc mất quá nhiều thời gian, worker thread có thể bị chiếm dụng, transaction của chunk kéo dài, connection bị giữ lâu và toàn bộ job chậm hoặc không hoàn tất.

Spring Batch không cung cấp một thuộc tính timeout chung trên interface ItemProcessor để tự động ngắt mọi lời gọi process(item) sau một số giây. Timeout cần được thiết kế ở nơi thực hiện công việc có thể block: HTTP client, JDBC statement, database, message client hoặc một deadline/wrapper có kiểm soát. Timeout của transaction chunk là một cơ chế khác và không bảo đảm ngắt được code Java bất kỳ đang chạy trong processor.

Một thiết kế timeout tốt xác định rõ giới hạn thời gian, cách hủy công việc, exception được phát ra, chính sách retry/skip và khả năng lặp an toàn. Bài học này trình bày cách áp dụng các nguyên tắc đó cho processor trong Spring Batch.

## 1. Timeout của processor là gì?

Timeout là giới hạn thời gian một thao tác được phép chờ hoặc thực hiện trước khi ứng dụng coi thao tác đó là thất bại. Trong processor, thời gian có thể tiêu tốn ở nhiều nơi:

- CPU xử lý hoặc tính toán dữ liệu.
- Chờ kết nối HTTP hoặc chờ response từ dịch vụ ngoài.
- Chờ database connection hoặc kết quả query.
- Chờ lock, semaphore, queue hoặc thread pool.
- Đọc dữ liệu từ object storage hoặc message broker.
- Chờ một future/task bất đồng bộ hoàn tất.

Không phải tất cả các trường hợp đều có cùng loại timeout. Connect timeout giới hạn thời gian thiết lập kết nối; response/read timeout giới hạn thời gian chờ dữ liệu; total request timeout giới hạn toàn bộ một request. Queue timeout giới hạn thời gian chờ lấy worker. Một deadline end-to-end giới hạn tổng thời gian cho toàn bộ quá trình xử lý item.

Một processor có thể hoàn tất nhanh trong điều kiện bình thường nhưng vẫn bị treo khi dịch vụ phụ thuộc gặp sự cố. Vì vậy, timeout là một phần của hợp đồng vận hành, không chỉ là một tối ưu hiệu năng.

## 2. Vị trí của processor trong chunk step

Processor được gọi trong giai đoạn xử lý từng item của chunk. Một chunk thường có nhiều item; nếu một lần gọi processor chờ quá lâu, worker không thể hoàn tất chunk cho tới khi lời gọi đó kết thúc hoặc ném exception.

~~~mermaid
flowchart LR
    A[ItemReader] --> B[ItemProcessor]
    B --> C[ItemWriter]
    C --> D[Commit chunk]
    B -.-> E[HTTP / JDBC / Service]
    E -. timeout .-> F[ProcessorTimeoutException]
    F --> G[Retry / Skip / Fail policy]
~~~

Ví dụ chunk size là 100. Nếu processor xử lý 99 item trong vài mili giây nhưng item thứ 100 chờ API 90 giây, chunk vẫn chưa thể đi tới writer/commit. Một timeout có giới hạn giúp job giải phóng worker và xử lý lỗi theo chính sách đã định.

Timeout nên được đặt gần thao tác có thể block nhất. Nếu processor gọi HTTP, cấu hình timeout của HTTP client. Nếu processor chạy query JDBC, cấu hình query/statement timeout. Nếu processor chờ task khác, giới hạn thời gian chờ task và xác định cách hủy task.

## 3. Không có timeout tổng quát trên ItemProcessor

Contract cơ bản của Spring Batch:

~~~java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
~~~

Interface không nhận tham số timeout và cũng không cung cấp callback để framework cưỡng bức dừng method sau một thời gian. Vì vậy, một lời gọi kiểu processor.setTimeout(...) không phải API chuẩn của ItemProcessor.

Nếu method process chạy vòng lặp CPU vô hạn, gọi một thư viện không có timeout hoặc chờ I/O vô hạn, Spring Batch không tự biết cách ngắt nó. Step có thể tiếp tục chờ cho tới khi thao tác trả về, thread bị interrupt và code hợp tác dừng, hoặc tiến trình bị dừng.

Hãy tránh nhầm lẫn giữa timeout của một dependency và timeout của toàn processor. Một processor có thể gọi ba service, mỗi service có timeout 5 giây; tổng thời gian vẫn có thể vượt 5 giây. Nếu cần giới hạn tổng thời gian, cần deadline được truyền xuyên suốt các bước và mỗi dependency phải tôn trọng thời gian còn lại.

## 4. Phân biệt các loại timeout

| Loại timeout | Giới hạn | Ví dụ |
|---|---|---|
| Connection timeout | Thời gian thiết lập kết nối | HTTP connect hoặc lấy connection từ pool |
| Response/read timeout | Thời gian chờ response hoặc dữ liệu tiếp theo | HTTP response, socket read |
| Request/call timeout | Tổng thời gian cho một request | Một HTTP request hoàn chỉnh |
| Query/statement timeout | Thời gian database thực thi statement | JDBC query |
| Pool/queue timeout | Thời gian chờ tài nguyên hoặc worker | Connection pool, bulkhead, executor queue |
| Processor deadline | Tổng thời gian cho logic xử lý item | Nhiều bước service trong một process call |
| Transaction timeout | Thời gian transaction được phép tồn tại | Transaction của chunk |
| Job/step operational limit | Ngưỡng thời gian vận hành của execution | Cảnh báo hoặc dừng job theo quy trình quản trị |

Các timeout này không thay thế lẫn nhau. Ví dụ, connection timeout không giới hạn thời gian server xử lý request sau khi kết nối thành công. Transaction timeout không phải một cơ chế đáng tin cậy để ngắt một lời gọi REST đang block.

## 5. Đặt timeout ngay trên HTTP client

Đây thường là cách hiệu quả nhất khi processor gọi REST service. Hãy cấu hình timeout tại client để thao tác I/O tự kết thúc bằng exception khi vượt giới hạn.

Với Java HTTP Client:

~~~java
@Bean
HttpClient customerHttpClient() {
    return HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();
}
~~~

Khi tạo request, đặt timeout cho request:

~~~java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create(customerUrl))
        .timeout(Duration.ofSeconds(5))
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

Gọi đồng bộ:

~~~java
HttpResponse<String> response =
        httpClient.send(request, HttpResponse.BodyHandlers.ofString());
~~~

Trong ví dụ, connect timeout giới hạn thời gian thiết lập kết nối; request timeout giới hạn thời gian chờ request hoàn tất theo semantics của Java HTTP Client. Hãy chọn giá trị dựa trên SLA của dịch vụ và ngân sách thời gian của job.

Không đặt timeout quá lớn chỉ để tránh lỗi. Khi dịch vụ bị treo, thời gian chờ dài làm worker bị chiếm dụng và có thể khiến backlog tăng. Cũng không đặt timeout quá ngắn khiến request bình thường bị fail trong lúc hệ thống tải cao.

## 6. Chuyển HTTP timeout thành exception nghiệp vụ

Processor không nên phụ thuộc vào mọi chi tiết exception của thư viện HTTP. Có thể bọc lỗi timeout thành exception riêng để step cấu hình retry/skip rõ ràng:

~~~java
public class ProcessorTimeoutException extends RuntimeException {
    public ProcessorTimeoutException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Service gọi API:

~~~java
public class CustomerApiClient {

    private final HttpClient httpClient;
    private final URI customerUri;

    public CustomerApiClient(HttpClient httpClient, URI customerUri) {
        this.httpClient = httpClient;
        this.customerUri = customerUri;
    }

    public CustomerDetails fetch(String customerId) {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(customerUri.resolve("/customers/" + customerId))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        try {
            HttpResponse<String> response = httpClient.send(
                    request,
                    HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() / 100 != 2) {
                throw new CustomerServiceException(
                        "Customer service returned HTTP "
                                + response.statusCode());
            }
            return parseCustomer(response.body());
        } catch (HttpTimeoutException ex) {
            throw new ProcessorTimeoutException(
                    "Timed out fetching customer " + customerId, ex);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new CustomerServiceInterruptedException(
                    "Interrupted while fetching customer " + customerId, ex);
        } catch (IOException ex) {
            throw new CustomerServiceException(
                    "Could not fetch customer " + customerId, ex);
        }
    }
}
~~~

Đây là ví dụ minh họa; ứng dụng cần bổ sung parse JSON, kiểm tra status code và xử lý response body theo API thực tế. Điểm quan trọng là phân biệt timeout với lỗi HTTP nghiệp vụ và lỗi gián đoạn thread. Khi nhận InterruptedException, khôi phục interrupt flag và không chuyển nó thành lỗi retry thông thường nếu việc dừng thread là chủ đích.

Không ghi token, authorization header hoặc toàn bộ payload nhạy cảm vào exception message. Log correlation ID và business key ở mức phù hợp để điều tra.

## 7. Đặt timeout cho JDBC query

Nếu processor gọi database, hãy cấu hình query timeout ở JDBC layer. Ví dụ với JdbcTemplate:

~~~java
@Bean
JdbcTemplate reportingJdbcTemplate(DataSource dataSource) {
    JdbcTemplate jdbcTemplate = new JdbcTemplate(dataSource);
    jdbcTemplate.setQueryTimeout(10);
    return jdbcTemplate;
}
~~~

Giá trị trên là số giây tối đa mà JDBC statement được phép thực thi theo hỗ trợ của driver/database. Driver có thể triển khai timeout khác nhau; cần kiểm tra behavior của database mục tiêu và test query chậm thực tế.

Với query cần timeout khác nhau, có thể cấu hình template riêng hoặc dùng API JDBC để đặt query timeout trên statement cụ thể. Tránh thay đổi thuộc tính timeout của một singleton JdbcTemplate theo từng item vì nhiều worker có thể dùng chung bean đồng thời.

Timeout phía JDBC client cũng không phải lúc nào bảo đảm server đã dừng ngay lập tức. Khi timeout, driver có thể gửi cancel request hoặc đóng statement/connection theo implementation. Theo dõi database session và query execution để xác nhận.

## 8. Transaction timeout không phải processor timeout

Chunk step thường thực hiện read/process/write trong transaction do step quản lý. Có thể cấu hình transaction attribute với timeout:

~~~java
DefaultTransactionAttribute transactionAttribute =
        new DefaultTransactionAttribute();
transactionAttribute.setTimeout(45);

return new StepBuilder("processOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .transactionAttribute(transactionAttribute)
        .build();
~~~

Transaction timeout giúp transaction manager/database áp dụng giới hạn thời gian cho transaction hoặc các thao tác tài nguyên có hỗ trợ. Tác dụng chính xác phụ thuộc transaction manager và resource. Nó không cưỡng bức dừng một vòng lặp CPU, một lời gọi HTTP không có timeout hoặc một thư viện đang block mà không kiểm tra interrupt.

Nếu processor gọi API trong khi chunk transaction đang mở, API có thể chờ lâu dù transaction timeout đã hết. Sau đó transaction có thể thất bại ở một thao tác database hoặc lúc commit, nhưng thời gian chờ API không nhất thiết bị cắt đúng lúc timeout.

Vì vậy, cần cấu hình cả timeout của dependency và transaction timeout nếu phù hợp. Đừng dùng transaction timeout như phương án duy nhất để giới hạn thời gian processor.

## 9. Thiết kế ngân sách thời gian cho một item

Nếu processor gọi nhiều dependency, nên xác định một deadline tổng. Ví dụ item có ngân sách 8 giây:

| Công đoạn | Ngân sách tối đa |
|---|---:|
| Lấy dữ liệu tham chiếu | 2 giây |
| Gọi scoring service | 3 giây |
| Tính toán và mapping | 1 giây |
| Dự phòng/overhead | 2 giây |

Không nên cho mỗi dependency sử dụng toàn bộ 8 giây. Nếu hai service cùng chờ 8 giây tuần tự, tổng thời gian có thể là 16 giây hoặc hơn.

Deadline nên được truyền xuyên suốt chuỗi xử lý. Mỗi bước lấy thời gian còn lại và không bắt đầu một thao tác mới nếu ngân sách đã hết. Dùng System.nanoTime() để đo elapsed time vì nó phù hợp với khoảng thời gian đơn điệu; không dùng System.currentTimeMillis() để tính timeout vì đồng hồ hệ thống có thể được điều chỉnh.

Ví dụ một deadline nhỏ:

~~~java
public final class Deadline {

    private final long deadlineNanos;

    private Deadline(Duration budget) {
        this.deadlineNanos = System.nanoTime() + budget.toNanos();
    }

    public static Deadline after(Duration budget) {
        return new Deadline(budget);
    }

    public Duration remaining() {
        long nanos = deadlineNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0, nanos));
    }

    public void throwIfExpired() {
        if (deadlineNanos - System.nanoTime() <= 0) {
            throw new ProcessorTimeoutException(
                    "Processor deadline exceeded", null);
        }
    }
}
~~~

Đây là ví dụ đơn giản cho một process call. Trong hệ thống thực tế, cần validate budget dương, tránh overflow khi cộng thời gian và quyết định rõ exception cause. Khi gọi HTTP/JDBC, truyền remaining() vào timeout của dependency thay vì luôn dùng một hằng số độc lập.

Deadline chỉ kiểm tra được ở các điểm mà code chủ động kiểm tra hoặc dependency nhận timeout. Nó không tự ngắt một method đang block.

## 10. Truyền deadline qua processor chain

Nếu dùng nhiều delegate trong CompositeItemProcessor, mỗi delegate có thể nhận cùng một context chứa deadline. Một cách là tạo item envelope:

~~~java
public record ProcessingContext<T>(
        T item,
        Deadline deadline,
        String correlationId) {
}
~~~

Processor đầu tiên tạo context:

~~~java
public class StartDeadlineProcessor
        implements ItemProcessor<OrderInput, ProcessingContext<OrderInput>> {

    @Override
    public ProcessingContext<OrderInput> process(OrderInput input) {
        return new ProcessingContext<>(
                input,
                Deadline.after(Duration.ofSeconds(8)),
                input.orderId());
    }
}
~~~

Delegate tiếp theo kiểm tra thời gian còn lại trước khi gọi dependency:

~~~java
public class EnrichWithCustomerProcessor
        implements ItemProcessor<ProcessingContext<OrderInput>,
                                 ProcessingContext<EnrichedOrder>> {

    private final CustomerClient customerClient;

    @Override
    public ProcessingContext<EnrichedOrder> process(
            ProcessingContext<OrderInput> context) {
        context.deadline().throwIfExpired();
        Customer customer = customerClient.fetch(
                context.item().customerId(),
                context.deadline().remaining());
        context.deadline().throwIfExpired();

        EnrichedOrder output = enrich(context.item(), customer);
        return new ProcessingContext<>(
                output,
                context.deadline(),
                context.correlationId());
    }
}
~~~

Ví dụ chỉ minh họa cách truyền deadline; constructor injection, null handling và method signature cần hoàn thiện theo model của ứng dụng. Một lựa chọn khác là một service điều phối nhận deadline như tham số thay vì bọc mọi item bằng envelope. Chọn cách nào cũng cần tránh lưu deadline của item hiện tại vào field singleton.

## 11. Timeout cho CPU-bound processing

Với xử lý CPU-bound, timeout không thể dừng code an toàn chỉ bằng cách ném exception từ một thread khác. Cách phù hợp là chia công việc thành các đoạn có thể kiểm tra deadline hoặc interrupt:

~~~java
public Result calculate(Input input, Deadline deadline) {
    Result result = Result.empty();

    for (Part part : input.parts()) {
        deadline.throwIfExpired();
        if (Thread.currentThread().isInterrupted()) {
            throw new ProcessingInterruptedException(
                    "Processing thread was interrupted");
        }
        result = result.add(calculatePart(part));
    }

    return result;
}
~~~

Kiểm tra định kỳ giúp code hợp tác dừng. Tần suất kiểm tra cần cân bằng overhead và độ trễ dừng. Nếu một thư viện tính toán bên thứ ba không cung cấp cancellation hoặc deadline, ứng dụng không thể bảo đảm dừng chính xác tại thời điểm timeout.

Không tạo một thread mới cho mỗi item chỉ để có thể gọi Future.get(timeout). Cách đó có thể làm số thread tăng không giới hạn khi dependency chậm, khiến job càng mất ổn định.

## 12. Dùng Future với timeout: khi nào phù hợp?

Một wrapper có thể submit task vào executor và chờ kết quả bằng Future.get(timeout, unit). Khi quá hạn, wrapper gọi cancel(true) và ném timeout exception:

~~~java
public class TimedProcessor<I, O> implements ItemProcessor<I, O> {

    private final ItemProcessor<I, O> delegate;
    private final ExecutorService executor;
    private final Duration timeout;

    public TimedProcessor(
            ItemProcessor<I, O> delegate,
            ExecutorService executor,
            Duration timeout) {
        this.delegate = delegate;
        this.executor = executor;
        this.timeout = timeout;
    }

    @Override
    public O process(I item) throws Exception {
        Future<O> future = executor.submit(() -> delegate.process(item));
        try {
            return future.get(timeout.toMillis(), TimeUnit.MILLISECONDS);
        } catch (TimeoutException ex) {
            future.cancel(true);
            throw new ProcessorTimeoutException(
                    "Processor exceeded " + timeout, ex);
        } catch (ExecutionException ex) {
            Throwable cause = ex.getCause();
            if (cause instanceof Exception exception) {
                throw exception;
            }
            throw new IllegalStateException(
                    "Processor failed with an error", cause);
        } catch (InterruptedException ex) {
            future.cancel(true);
            Thread.currentThread().interrupt();
            throw new ProcessingInterruptedException(
                    "Waiting for processor was interrupted", ex);
        }
    }
}
~~~

Đây là một mẫu kỹ thuật, không phải giải pháp mặc định cho mọi processor. Executor phải được quản lý bởi Spring/application lifecycle, có giới hạn thread và queue, có rejection policy rõ ràng và được shutdown đúng cách. Cần validate timeout dương và xử lý CancellationException nếu task bị hủy từ bên ngoài.

cancel(true) chỉ gửi interrupt tới thread chạy task. Nó không cưỡng bức kết thúc code không hợp tác, không dừng được mọi I/O client và không hoàn tác side effect đã xảy ra. Task có thể tiếp tục chạy sau khi caller đã nhận timeout.

Một rủi ro lớn khác là transaction context trong Spring thường gắn với thread. Nếu delegate được chuyển sang thread executor khác, nó không tự tham gia transaction của chunk đang chạy ở thread gọi. Không dùng wrapper này để chuyển các thao tác JDBC cần cùng transaction sang thread phụ. Chỉ dùng khi semantics của công việc độc lập với transaction của caller và có cơ chế cancellation/idempotency rõ ràng.

## 13. Bounded executor và bulkhead

Nếu dùng executor cho công việc processor, phải giới hạn số worker và hàng đợi. Executor không giới hạn có thể tạo quá nhiều thread hoặc giữ vô số task chờ khi dịch vụ downstream chậm.

Ví dụ:

~~~java
@Bean(destroyMethod = "shutdown")
ExecutorService processorExecutor() {
    return new ThreadPoolExecutor(
            8,
            8,
            0L,
            TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(100),
            new ThreadPoolExecutor.AbortPolicy());
}
~~~

Trong ví dụ, tối đa tám task chạy đồng thời và hàng đợi giữ tối đa 100 task. Khi queue đầy, task mới bị từ chối thay vì làm bộ nhớ tăng vô hạn. Ứng dụng cần quyết định cách chuyển RejectedExecutionException thành lỗi có thể quan sát và liệu có nên retry sau backoff hay không.

Bulkhead giới hạn tài nguyên dành cho một dependency hoặc nhóm công việc. Nó giúp một dịch vụ chậm không chiếm toàn bộ worker của batch. Tuy nhiên, tăng thêm executor riêng cũng làm tăng tổng số thread; phải tính tổng concurrency của step, processor executor, HTTP connection pool và database pool.

## 14. Spring Batch async processor không tự tạo timeout

Spring Batch Integration có các thành phần như AsyncItemProcessor và AsyncItemWriter để xử lý item bất đồng bộ. Async processor thường trả về một Future cho mỗi item; async writer chờ kết quả trước khi ghi output.

Bất đồng bộ và timeout là hai vấn đề khác nhau:

- Async processor thay đổi cách thực thi và kiểu dữ liệu trung gian.
- Timeout quy định thời gian chờ tối đa và cách hủy task.
- Nếu future không hoàn tất, writer có thể tiếp tục chờ tùy implementation.
- Không giả định việc dùng async processor tự động giới hạn thời gian cho từng item.

Nếu cần timeout cho future, phải thiết kế rõ nơi chờ, cancellation, exception translation và lifecycle của executor. Cũng cần kiểm tra semantics transaction và restart của phiên bản Spring Batch Integration đang dùng.

Không dùng async processing chỉ để giải quyết một HTTP call không có timeout. Trước tiên cấu hình timeout ở HTTP client; sau đó mới cân nhắc async để tăng throughput khi có giới hạn concurrency phù hợp.

## 15. Retry khi processor timeout

Timeout có thể là lỗi tạm thời, nhưng không phải timeout nào cũng nên retry. Ví dụ:

- Một API tạm quá tải có thể thành công ở lần thử sau.
- Một query luôn scan toàn bảng có thể timeout lặp lại do thiếu index.
- Một request bị timeout sau khi server đã xử lý có thể đã tạo side effect.
- Một item có payload quá lớn có thể luôn vượt quá giới hạn thời gian.

Có thể cấu hình retry cho exception timeout đã phân loại:

~~~java
return new StepBuilder("enrichOrdersStep", jobRepository)
        .<OrderInput, EnrichedOrder>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(ProcessorTimeoutException.class)
        .retryLimit(2)
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .build();
~~~

Trong ví dụ, timeout được retry tối đa theo giới hạn cấu hình, còn lỗi dữ liệu có thể được skip. Hãy kiểm tra semantics retry/skip theo phiên bản Spring Batch và Spring Retry của dự án. Đừng cấu hình timeout exception là skippable chỉ để job luôn hoàn tất nếu item bị bỏ có thể làm sai kết quả nghiệp vụ.

Retry cần có backoff, giới hạn tổng số lần thử và ngân sách thời gian tổng. Nếu một item có timeout 5 giây và được thử ba lần, thời gian xử lý có thể vượt 15 giây khi cộng thêm backoff. Deadline end-to-end phải tính cả các lần retry.

## 16. Backoff, circuit breaker và retry storm

Khi dịch vụ downstream đang quá tải, nhiều worker timeout cùng lúc rồi retry ngay lập tức có thể làm tải tăng thêm. Đây là retry storm.

Các biện pháp:

- Exponential backoff để tăng khoảng chờ giữa các lần thử.
- Jitter để tránh mọi worker retry cùng một thời điểm.
- Circuit breaker tạm ngăn gọi dependency đang lỗi liên tục.
- Bulkhead giới hạn số request đồng thời.
- Rate limiter giữ tốc độ gọi trong giới hạn dịch vụ.
- Retry chỉ cho lỗi tạm thời và request có thể lặp an toàn.

Ví dụ một chính sách minh họa:

| Lần thử | Thời gian chờ trước lần thử |
|---|---:|
| 1 | Không chờ |
| 2 | 500 ms cộng jitter |
| 3 | 1 giây cộng jitter |

Giá trị thực tế cần dựa trên SLA, rate limit và latency distribution của dependency. Circuit breaker và retry không thay thế timeout; một request vẫn cần giới hạn thời gian riêng.

## 17. Timeout và skip policy

Có hai quyết định riêng:

1. Có nên thử lại thao tác timeout không?
2. Nếu đã hết retry, có được bỏ qua item không?

Nếu timeout là lỗi hạ tầng và dữ liệu bắt buộc phải xử lý, fail step thường an toàn hơn skip. Nếu nghiệp vụ cho phép một số item không enrichment được chuyển vào khu vực review, có thể route/reject item với lý do rõ ràng. Không biến mọi timeout thành filter bằng cách trả null.

Nếu dùng skip, lưu ít nhất business key, source resource, exception type, thời điểm và số lần thử. Không lưu payload nhạy cảm nếu không cần. Đặt skip limit để ngăn job hoàn tất khi dependency lỗi diện rộng.

Một số lỗi timeout có kết quả không xác định: server có thể đã xử lý request nhưng response bị mất. Trước khi retry hoặc skip, cần biết thao tác có idempotent không và có thể truy vấn trạng thái để xác minh hay không.

## 18. Timeout trong multi-threaded step

Khi step dùng TaskExecutor, nhiều item có thể được xử lý đồng thời. Nếu processor gọi dependency chậm, số thread bị chiếm dụng tăng lên. Một timeout hợp lý giúp giới hạn thời gian chiếm dụng, nhưng concurrency vẫn cần giới hạn.

Hãy phối hợp:

- Số worker thread của step.
- Timeout của mỗi dependency.
- Connection pool size.
- HTTP max connections.
- Bulkhead limit.
- Chunk size và thời gian transaction.
- Retry/backoff budget.

Ví dụ có 16 worker nhưng HTTP client chỉ có 4 connection cho cùng host. 12 worker còn lại có thể chờ pool. Cần đặt pool-acquisition timeout hoặc giới hạn concurrency phù hợp để thời gian chờ này cũng nằm trong ngân sách.

Processor bean được nhiều thread gọi đồng thời nên phải stateless hoặc thread-safe. Không lưu deadline hiện tại, item hiện tại hay timeout mutable theo job vào field singleton. Truyền chúng qua method argument hoặc context riêng của item.

## 19. Timeout trong partitioning

Với partitioning, mỗi worker có StepExecution riêng. Timeout ở processor của một partition có thể làm partition step thất bại; manager step tổng hợp trạng thái worker theo cơ chế partition handler.

Các điểm cần thiết kế:

- Timeout của dependency phải được áp dụng ở từng worker.
- Giới hạn tổng số worker để không làm downstream quá tải.
- Một partition retry cần giữ cùng phạm vi dữ liệu và idempotency key.
- Không để worker timeout nhưng task bên trong vẫn tiếp tục ghi side effect sau khi partition đã bị đánh dấu fail.
- Theo dõi timeout theo partition để nhận diện một range dữ liệu có vấn đề.

Nếu mỗi partition có processor cấu hình khác nhau, dùng StepScope/ExecutionContext để truyền cấu hình worker. Scope không tự tạo timeout; nó chỉ quản lý vòng đời và late binding.

## 20. Timeout và transaction/chunk size

Chunk size ảnh hưởng thời gian transaction và phạm vi rollback. Chunk lớn có thể chứa nhiều lời gọi processor, vì vậy tổng thời gian chunk là tổng thời gian read/process/write cùng chi phí commit. Dù mỗi item có timeout riêng, chunk vẫn có thể vượt transaction timeout nếu có nhiều item chậm hoặc nhiều lần retry.

Ví dụ:

- 100 item.
- Trung bình 100 ms cho processor mỗi item.
- 5 item chạm timeout 3 giây.

Thời gian chunk có thể tăng đáng kể so với mức trung bình. Nếu xử lý tuần tự, các item timeout cộng dồn; nếu xử lý song song, chúng chiếm worker và dependency capacity cùng lúc.

Chọn chunk size dựa trên thời gian xử lý thực tế, memory, transaction duration và khả năng rollback. Giảm chunk size có thể giới hạn phạm vi transaction nhưng làm tăng số lần commit. Không dùng chunk size như một timeout cho từng item.

## 21. Deadline tổng cho một chunk hoặc job

Ngoài timeout từng item, vận hành có thể cần giới hạn thời gian cho một chunk, step hoặc job. Các giới hạn này cần được thiết kế riêng:

- Item deadline: giới hạn thời gian xử lý một item.
- Chunk/transaction timeout: giới hạn transaction của chunk.
- Step/job SLA: ngưỡng cảnh báo hoặc chính sách vận hành khi execution kéo dài.
- Scheduler deadline: thời điểm job cần kết thúc để không ảnh hưởng batch window tiếp theo.

Nếu cần dừng một job khi quá SLA, hãy dùng cơ chế quản trị execution có kiểm soát, cancellation cooperative và quy trình shutdown. Không chỉ kill thread đang chạy processor; điều đó có thể để lại resource hoặc side effect không rõ trạng thái.

Một scheduler có thể phát cảnh báo trước khi deadline đến, ngăn khởi chạy job mới hoặc yêu cầu dừng có kiểm soát. Việc dừng cần chờ transaction rollback/commit và lifecycle close theo khả năng của framework.

## 22. Xử lý interrupt đúng cách

Thread interruption là tín hiệu yêu cầu một thread dừng hoặc hủy công việc. Code hợp tác nên:

- Kiểm tra Thread.currentThread().isInterrupted() ở các điểm an toàn.
- Nếu một blocking API ném InterruptedException, khôi phục interrupt flag khi chuyển exception lên tầng trên.
- Không bắt InterruptedException rồi tiếp tục xử lý như không có gì.
- Không biến interruption do shutdown thành timeout retry vô hạn.
- Đóng resource trong finally hoặc try-with-resources.

Ví dụ:

~~~java
try {
    return blockingService.call();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new ProcessingInterruptedException(
            "Processor was interrupted", ex);
}
~~~

Nếu một thư viện bỏ qua interrupt, ứng dụng không thể đảm bảo dừng nó bằng Future.cancel(true). Hãy ưu tiên client có timeout/cancellation thực sự và test behavior khi đóng job.

## 23. Quan sát và logging timeout

Timeout cần được quan sát như một loại lỗi riêng. Nên thu thập:

- Số lần timeout theo dependency và operation.
- Latency p50/p95/p99.
- Số lần retry và tổng thời gian retry.
- Số worker đang active và queue depth.
- Connection pool wait time.
- Circuit breaker state và bulkhead rejection.
- Processor duration theo loại item hoặc step.
- Số item bị skip/reject vì timeout.

Log nên có step name, partition ID nếu có, business key hoặc correlation ID, dependency, timeout budget và attempt number. Tránh ghi toàn bộ request/response hoặc thông tin nhạy cảm.

Không đưa business ID riêng lẻ vào metric tag vì cardinality tăng không giới hạn. Dùng tag có tập giá trị nhỏ như step, dependency, operation và exception category.

## 24. Kiểm thử timeout của processor

Test timeout nên kiểm tra cả exception và hậu quả đối với step. Không nên chỉ dùng Thread.sleep() dài trong mọi test vì test sẽ chậm và dễ flaky. Có thể dùng mock service để ném timeout exception một cách xác định; dùng fake clock cho logic deadline; dùng HTTP stub server cho integration test của client timeout.

Các trường hợp nên kiểm thử:

1. Dependency phản hồi trong timeout: processor trả output bình thường.
2. Dependency vượt timeout: processor ném đúng ProcessorTimeoutException.
3. Connect timeout và response timeout được phân biệt nếu client hỗ trợ.
4. Deadline đã hết trước khi gọi dependency: processor không bắt đầu thao tác mới.
5. Deadline còn ít hơn timeout mặc định: client nhận phần thời gian còn lại.
6. Thread bị interrupt: processor khôi phục interrupt flag và dừng hợp tác.
7. Retry: số lần gọi đúng giới hạn và backoff được áp dụng.
8. Hết retry: step fail hoặc skip đúng policy.
9. Unknown outcome: side effect không bị duplicate khi retry.
10. Multi-threaded step: concurrency không vượt giới hạn dependency.
11. Executor queue đầy: rejection được xử lý có chủ đích.
12. Job shutdown: task và resource được đóng theo lifecycle.

## 25. Unit test với service timeout giả lập

Có thể mock dependency để kiểm tra exception translation:

~~~java
@Test
void convertsHttpTimeoutToProcessorTimeout() {
    CustomerApiClient client = new CustomerApiClient(
            httpClientThatTimesOut(),
            customerUri);

    assertThrows(
            ProcessorTimeoutException.class,
            () -> client.fetch("CUS-1"));
}
~~~

httpClientThatTimesOut() là test double hoặc mock được cấu hình để phát sinh HttpTimeoutException. Trong unit test, có thể mock HttpClient.send nếu API và test framework hỗ trợ; integration test với stub server sẽ xác nhận timeout thực tế của client.

Đối với Deadline, có thể inject một LongSupplier hoặc Clock abstraction để test thời gian mà không phải chờ thật. Với deadline dựa trên System.nanoTime, một abstraction cung cấp monotonic ticks giúp test hết hạn chính xác và không flaky.

## 26. Integration test timeout và retry trong step

Một step integration test nên chạy với processor gọi một fake service:

- Lần đầu service timeout.
- Lần retry service trả thành công.
- Xác nhận processor được gọi đúng số lần.
- Xác nhận writer chỉ ghi kết quả một lần.
- Xác nhận step status và retry count đúng.

Một test khác có thể làm service timeout ở mọi lần thử để xác nhận step fail sau retry limit hoặc skip theo policy. Kiểm tra cả output và reject store; status COMPLETED một mình không chứng minh dữ liệu đã đầy đủ.

Với transaction, dùng transaction manager/database test thật khi cần chứng minh rollback. Với HTTP, dùng stub server để tạo response delay và xác nhận request timeout. Đặt timeout test ngắn nhưng đủ ổn định trên CI; tránh phụ thuộc chính xác từng mili giây của scheduler.

## 27. Những lỗi thường gặp

**Cho rằng ItemProcessor có thuộc tính timeout built-in.** Contract không có timeout chung. Cấu hình ở dependency hoặc tạo deadline/wrapper phù hợp.

**Dùng transaction timeout để ngắt HTTP call.** Transaction manager không cưỡng bức dừng mọi blocking call. Đặt timeout trên HTTP client.

**Chỉ cấu hình connect timeout.** Kết nối thành công nhưng server có thể không trả response. Cấu hình request/read timeout phù hợp.

**Mỗi dependency dùng toàn bộ timeout item.** Nhiều lần gọi tuần tự làm tổng thời gian vượt budget. Truyền deadline và thời gian còn lại.

**Retry mọi timeout ngay lập tức.** Có thể tạo retry storm. Dùng retry có giới hạn, backoff/jitter, circuit breaker và bulkhead.

**Coi timeout là bằng chứng server chưa xử lý request.** Response có thể bị mất sau khi side effect đã hoàn tất. Dùng idempotency key và reconciliation.

**Dùng Future.cancel như một kill switch.** Cancel chỉ gửi interrupt; task không hợp tác có thể tiếp tục. Cấu hình timeout thật ở client và viết code cooperative.

**Tạo thread mới cho mỗi item.** Khi dependency chậm, thread tăng không giới hạn. Dùng executor có pool và queue bounded nếu thực sự cần.

**Chuyển thao tác JDBC sang thread phụ rồi kỳ vọng cùng transaction.** Transaction context thường gắn với thread. Giữ thao tác transaction-bound trong thread chunk.

**Bắt InterruptedException mà không khôi phục flag.** Shutdown/cancellation có thể bị bỏ qua. Khôi phục interrupt và truyền lỗi phù hợp.

**Timeout quá ngắn hoặc quá dài.** Quá ngắn gây false timeout; quá dài giữ worker và transaction. Dựa trên latency distribution và SLA.

**Không kiểm thử timeout trong step.** Unit test dependency không chứng minh retry/skip/rollback đúng. Thêm integration test cho step.

## 28. Quy trình thiết kế timeout cho processor

Khi một processor gọi dependency có thể chậm, hãy làm theo thứ tự:

1. Xác định operation nào có thể block và latency hiện tại của nó.
2. Chọn connect, read/request, query và pool timeout phù hợp cho từng dependency.
3. Đặt ngân sách end-to-end cho item nếu processor có nhiều bước.
4. Truyền deadline hoặc thời gian còn lại tới các dependency; không dùng lại timeout đầy đủ ở mọi bước.
5. Chuyển timeout thành exception riêng, giữ cause và context cần thiết.
6. Phân loại lỗi tạm thời, lỗi dữ liệu, interruption và lỗi lập trình.
7. Cấu hình retry/backoff/skip/fail theo khả năng phục hồi và yêu cầu nghiệp vụ.
8. Kiểm tra idempotency cho mọi thao tác có side effect hoặc kết quả không xác định.
9. Giới hạn concurrency, connection pool và executor queue.
10. Phân biệt timeout của processor với transaction timeout và SLA của job.
11. Viết unit test cho deadline/exception và integration test cho client cùng step.
12. Theo dõi timeout rate, latency, retry, queue depth và worker utilization trong production.

## Kết luận

Timeout của processor cần được thiết kế ở các thao tác mà processor gọi. ItemProcessor không có timeout tổng quát để Spring Batch tự ngắt method. Hãy đặt connect/request timeout trên HTTP client, query timeout trên JDBC/database, giới hạn thời gian chờ pool/executor và dùng deadline end-to-end khi một item đi qua nhiều dependency.

Transaction timeout giới hạn transaction theo khả năng của transaction manager và resource; nó không bảo đảm dừng code Java hoặc I/O tùy ý. Future.cancel(true) cũng chỉ gửi interrupt, nên chỉ hiệu quả khi task và dependency hợp tác hủy. Với timeout có thể retry, dùng exception riêng, giới hạn số lần thử và backoff; kiểm tra idempotency vì timeout không chứng minh thao tác phía server chưa xảy ra.

Cuối cùng, giới hạn concurrency và kiểm thử cả processor lẫn step. Một chính sách timeout đáng tin cậy phải xác định được thời gian chờ, cách dừng, cách phục hồi và cách phát hiện dữ liệu bị bỏ hoặc side effect bị lặp.
