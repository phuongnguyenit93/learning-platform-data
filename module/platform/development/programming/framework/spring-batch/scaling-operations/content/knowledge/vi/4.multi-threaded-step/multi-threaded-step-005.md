# ItemProcessor chạy trên nhiều thread

Khi bật **multi-threaded step** trong Spring Batch, nhiều thread có thể xử lý các chunk của cùng một **StepExecution**. Nếu step có `ItemProcessor`, các lời gọi `process(item)` của những chunk khác nhau có thể **chồng thời gian trên cùng một instance processor**. Một processor vốn chạy đúng khi xử lý tuần tự vì thế có thể gây sai số liệu, race condition, kết quả không ổn định hoặc lỗi khó tái hiện khi tăng số thread.

Bài học thuộc chương **Step nhiều luồng** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module nghiên cứu cách mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán; đồng thời đo nút thắt, giữ thread safety, bảo đảm retry/restart và chọn kiến trúc theo tài nguyên thực tế. Bài này tập trung vào **hành vi, thiết kế, cấu hình, kiểm thử và vận hành ItemProcessor khi một step dùng nhiều thread**.

## 1. Mục tiêu học tập

Sau bài này, bạn cần có khả năng:

1. Giải thích vì sao **multi-threaded step** có thể gọi một `ItemProcessor` từ nhiều thread và phân biệt với **parallel steps** hoặc **partitioning**.
2. Nhận diện processor có **mutable shared state**, collaborator không thread-safe, side effect không an toàn khi retry, và vấn đề `ThreadLocal`.
3. Viết processor **stateless**, dựa trên đầu vào và trả về output mới, phù hợp khi xử lý đồng thời.
4. Hiểu giới hạn của `@StepScope`: scope theo **StepExecution**, **không phải** cấp một processor mới cho mỗi thread.
5. Cấu hình `TaskExecutor`, chunk size, reader/writer và connection pool mà không hứa hẹn thứ tự xử lý.
6. Kiểm thử sự chồng thời gian của các lời gọi `process`, kiểm tra toàn vẹn dữ liệu, lỗi/retry/restart và đo throughput thực tế.

**Tình huống xuyên suốt:** job đọc 500.000 giao dịch bán hàng, chuẩn hóa tiền và tính số tiền sau chiết khấu. Do processor thực hiện kiểm tra nghiệp vụ và biến đổi dữ liệu tương đối tốn CPU, nhóm vận hành muốn dùng bốn thread thay vì một. Kết quả phải giữ **mỗi giao dịch đúng một bản ghi**, số tiền chính xác, có thể retry và restart mà không tạo side effect trùng.

## 2. Cơ chế gọi ItemProcessor trong multi-threaded step

Với một chunk-oriented step thông thường, quá trình xử lý được mô tả đơn giản như sau:

~~~text
read -> process -> write -> commit -> chunk tiếp theo
~~~

Khi gắn một `TaskExecutor` vào step, nhiều lần xử lý chunk có thể chạy đồng thời. Ở mức khái niệm:

~~~mermaid
flowchart TD
    S["Một StepExecution"] --> T["TaskExecutor"]
    T --> A["Thread A: chunk #1"]
    T --> B["Thread B: chunk #2"]
    T --> C["Thread C: chunk #3"]
    A --> PA["processor.process(item)"]
    B --> PB["processor.process(item)"]
    C --> PC["processor.process(item)"]
    PA --> P["Cùng một ItemProcessor bean"]
    PB --> P
    PC --> P
    A --> WA["writer / transaction A"]
    B --> WB["writer / transaction B"]
    C --> WC["writer / transaction C"]
~~~

Các mũi tên từ ba lời gọi `process` về cùng processor thể hiện việc **dùng chung đối tượng** trong cách cấu hình thường gặp; sơ đồ không khẳng định mọi bean processor của mọi ứng dụng đều có cùng vòng đời. Nếu một bean được tạo theo scope đặc biệt, cần xem rõ scope đó hoạt động như thế nào.

Trong multi-threaded step:

- **Các chunk** là đơn vị được phân công cho những lần thực thi đồng thời, không có cam kết mỗi item luôn có một thread riêng.
- **Thứ tự hoàn tất chunk** có thể khác thứ tự đọc. Một chunk đọc trước có thể commit sau chunk khác.
- Nhiều transaction có thể tồn tại đồng thời; throughput phụ thuộc reader, processor, writer, DB, CPU và cấu hình executor.
- **Một StepExecution** vẫn đại diện cho step đó. Không mặc định có một StepExecution riêng cho mỗi thread như khi dùng partitioning.
- Việc tăng số thread **không làm mọi thành phần tự trở thành thread-safe**.

### So với các mô hình scaling khác

| Kiến trúc | Đơn vị chạy song song | Tác động lên ItemProcessor |
| --- | --- | --- |
| Multi-threaded step | Nhiều chunk trong **một StepExecution** | Nhiều thread có thể gọi cùng một instance |
| Parallel steps/flows | Nhiều step/flow độc lập | Processor chỉ bị chia sẻ nếu cấu hình bean hoặc service chung khiến nó bị chia sẻ |
| Local partitioning | Nhiều worker StepExecution cho các partition | Có thể dùng `@StepScope` để có instance theo **partition StepExecution**; các bean singleton vẫn có thể dùng chung |
| Remote partitioning/chunking | Công việc chạy trên các worker qua middleware | Phải xét ranh giới tiến trình, messaging, retry/redelivery và idempotency |

Vì đề bài là **ItemProcessor chạy trên nhiều thread**, những vấn đề liên quan reader/writer/JobRepository được bàn khi chúng ảnh hưởng trực tiếp đến an toàn và kết quả của processor.

## 3. Thread safety nghĩa là gì đối với ItemProcessor?

**Thread-safe** nghĩa là các lời gọi đồng thời vẫn duy trì được các bất biến đã định, không làm hỏng trạng thái hoặc trả kết quả sai vì cạnh tranh truy cập. Với processor, ba khía cạnh cần được đánh giá riêng:

1. **Trạng thái của processor:** có field nào bị ghi trong `process` không? Dữ liệu đó có thuộc về một item hay là trạng thái chia sẻ?
2. **Các dependency:** processor có gọi formatter, cache, DAO, client HTTP, collection hay service có mutable state không?
3. **Side effect:** ngoài trả về output, processor có cập nhật DB, gửi message, gọi API, tăng số dư hay ghi file không? Nếu item được xử lý lại do rollback/retry, tác động đó còn đúng không?

Một processor có thể **thread-safe** nhưng vẫn **không restart-safe**. Ví dụ dùng `AtomicLong` tạo số thứ tự đảm bảo các thread không tạo trùng trong cùng JVM, nhưng thứ tự phụ thuộc scheduling và bộ đếm mất khi process restart. Nếu số thứ tự dùng làm khóa nghiệp vụ thì kết quả không ổn định.

Một processor cũng có thể **không lưu field nào** nhưng vẫn không an toàn khi gọi vào một dependency chung không thread-safe.

## 4. Ví dụ processor sai: mutable state dùng chung

Xem bộ xử lý sau:

~~~java
@Component
class UnsafeOrderProcessor implements ItemProcessor<Order, OrderResult> {
    private long sequence = 0;
    private final List<Long> processedIds = new ArrayList<>();

    @Override
    public OrderResult process(Order order) {
        sequence++;                   // Đọc-sửa-ghi không nguyên tử
        processedIds.add(order.id()); // ArrayList không thread-safe

        return new OrderResult(
                order.id(),
                sequence,
                order.amount());
    }
}
~~~

Khi hai thread đọc cùng giá trị `sequence` rồi cùng tăng, cả hai item có thể nhận một số thứ tự. Việc ghi đồng thời vào `ArrayList` còn có thể dẫn tới mất phần tử hoặc cấu trúc không nhất quán. Do scheduling thay đổi, lỗi có thể chỉ xuất hiện khi tải lớn.

Chuyển `sequence` sang `AtomicLong` và `processedIds` sang collection đồng thời có thể giải quyết **một số race ở bộ nhớ**, nhưng chưa giải quyết được:

- **Thứ tự nghiệp vụ:** item nào nhận `sequence=1` sẽ phụ thuộc scheduling.
- **Restart:** sequence trong RAM không tương ứng vị trí đã commit trong JobRepository.
- **Rollback:** processor có thể đã tăng sequence hoặc thêm ID dù transaction DB bị rollback.
- **Retry:** cùng một item có thể đi qua `process` nhiều lần.

Nếu nghiệp vụ cần một ID ổn định, hãy dùng khóa từ dữ liệu đầu vào, sequence của DB với hợp đồng phù hợp, hoặc chiến lược định danh bền vững. Không lấy thứ tự gọi processor trong thread pool làm định danh.

### Dependency không thread-safe cũng gây lỗi

~~~java
// Không an toàn nếu formatter này bị gọi đồng thời:
private final SimpleDateFormat formatter =
        new SimpleDateFormat("yyyy-MM-dd");

// Thay bằng kiểu bất biến, thread-safe của java.time:
private static final DateTimeFormatter FORMATTER =
        DateTimeFormatter.ISO_LOCAL_DATE;
~~~

`DateTimeFormatter` là immutable và phù hợp để dùng chung. Với cache hoặc map cập nhật đồng thời, không dùng `HashMap` thông thường rồi giả định mọi thao tác là an toàn; tuy nhiên `ConcurrentHashMap` chỉ bảo vệ các thao tác phù hợp trên map, không tự bảo đảm tính nhất quán của cả một chuỗi nghiệp vụ nhiều bước.

## 5. Thiết kế ưu tiên: stateless, deterministic, mỗi item một kết quả

Lý tưởng, processor hoạt động như một hàm:

~~~text
output = process(input, immutable configuration)
~~~

Cùng một input và cùng bộ quy tắc bất biến cho ra cùng output; mọi biến trung gian nằm trên stack của lời gọi. Không dùng mutable field để chứa dữ liệu của item hiện tại.

Ví dụ Spring Batch 5.x, Java 17+:

~~~java
record Order(
        long id,
        BigDecimal amount,
        BigDecimal discountRate,
        LocalDate businessDate) {}

record OrderResult(
        long orderId,
        BigDecimal netAmount,
        LocalDate businessDate) {}

class InvalidOrderException extends RuntimeException {
    InvalidOrderException(long id, String detail) {
        super("Order " + id + ": " + detail);
    }
}

@Bean
ItemProcessor<Order, OrderResult> orderProcessor() {
    return order -> {
        if (order.amount() == null
                || order.amount().signum() < 0
                || order.discountRate() == null
                || order.discountRate().compareTo(BigDecimal.ZERO) < 0
                || order.discountRate().compareTo(BigDecimal.ONE) > 0) {
            throw new InvalidOrderException(order.id(), "invalid amount/rate");
        }

        BigDecimal net = order.amount()
                .multiply(BigDecimal.ONE.subtract(order.discountRate()))
                .setScale(2, RoundingMode.HALF_UP);

        return new OrderResult(order.id(), net, order.businessDate());
    };
}
~~~

Vì `BigDecimal`, `LocalDate` và record đầu vào/đầu ra trong ví dụ được dùng theo kiểu bất biến, từng lời gọi chỉ xử lý dữ liệu của item, không ghi vào shared state. Processor có thể được gọi đồng thời trên cùng instance mà không cần `synchronized`.

**Determinism còn phụ thuộc đầu vào và cấu hình.** Nếu processor đọc `LocalDate.now()` hoặc tỷ giá ngoại tệ hiện hành ở mỗi lần gọi, retry có thể cho kết quả khác. Nên cố định ngày nghiệp vụ, phiên bản quy tắc hoặc tỷ giá trong input/job parameters/snapshot rồi truyền đến processor bằng dependency bất biến.

Nếu cần **lọc item hợp lệ** (chẳng hạn bỏ đơn bị hủy), processor có thể trả về `null` theo hợp đồng Spring Batch. Điều này tăng **filterCount** và khác với việc ném exception rồi **skip** một item bị lỗi.

## 6. Cấu hình multi-threaded Step

Một cấu hình cơ bản sử dụng `TaskExecutor` của Spring Batch 5.x:

~~~java
@Bean
ThreadPoolTaskExecutor chunkExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("batch-chunk-");
    executor.initialize();
    return executor;
}

@Bean
Step orderStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, OrderResult> orderProcessor,
        ItemWriter<OrderResult> orderWriter,
        @Qualifier("chunkExecutor") TaskExecutor chunkExecutor) {

    return new StepBuilder("orderStep", jobRepository)
            .<Order, OrderResult>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .taskExecutor(chunkExecutor)
            .build();
}
~~~

Ví dụ tập trung vào cấu hình step: các bean reader và writer cần được triển khai phù hợp với đặc tính concurrent use. **Không lấy đoạn code này làm bằng chứng rằng mọi reader/writer đều thread-safe.**

**Ý nghĩa tham số:**

| Tham số | Ý nghĩa | Rủi ro nếu chọn không phù hợp |
| --- | --- | --- |
| `chunk(200, ...)` | Mỗi transaction thường xử lý tối đa 200 item | Chunk lớn tăng bộ nhớ, thời gian rollback và thời gian giữ lock |
| Core/max threads = 4 | Giới hạn số thread thực hiện chunk task của executor ví dụ | Nhiều thread có thể làm DB/CPU quá tải |
| Queue capacity = 8 | Giới hạn số task đang chờ trong executor | Queue lớn che giấu nghẽn; giới hạn quá thấp có thể gây từ chối task |
| Transaction manager | Quản lý ranh giới transaction của các chunk | Side effect dùng tài nguyên không cùng transaction có thể không rollback |
| DataSource pool | Cấp kết nối cho read/write/metadata theo cách ứng dụng dùng | Cạn pool, starvation và timeout |

Trong một số bản Spring Batch 5, cấu hình `throttleLimit` cũ đã bị **deprecated**; hành vi điều tiết thực tế còn phụ thuộc phiên bản và cơ chế repeat/throttle đang dùng. Đừng dựa vào `maxPoolSize` như cam kết cứng về số chunk đồng thời nếu một tầng khác còn đặt giới hạn. Kiểm tra version và đo số thread/chunk đang hoạt động trong môi trường triển khai.

### Reader và writer có thể trở thành nút thắt hoặc nguồn lỗi

**Processor stateless không cứu được reader/writer không thread-safe.** Nhiều reader dùng cursor, vị trí đọc hoặc buffer mutable và không thể được chia sẻ tùy ý giữa các chunk. Một số cách xử lý:

- Chọn reader được tài liệu của implementation xác nhận an toàn cho concurrent reads và tắt lưu trạng thái khi phù hợp với hợp đồng restart.
- Nếu phải dùng reader stateful, có thể cân nhắc wrapper đồng bộ như `SynchronizedItemStreamReader` cho loại reader tương thích, nhưng truy cập tuần tự vào reader có thể trở thành bottleneck.
- **Synchronization không tự làm restart đúng**: nhiều chunk được xử lý ngoài thứ tự có thể khiến checkpoint reader không đại diện đơn giản cho tập item đã commit.
- Khi cần restart có ranh giới và thứ tự rõ, cân nhắc **local partitioning** với mỗi StepExecution/reader có vùng đầu vào độc lập.
- Writer phải được đánh giá riêng về concurrent calls, transaction, unique constraint, lock và idempotency.

Đừng mặc định một `JdbcCursorItemReader`, `FlatFileItemReader` hoặc writer tự viết là an toàn chỉ vì step đã có `TaskExecutor`.

## 7. Vì sao @StepScope không tạo processor riêng cho từng thread?

Một hiểu lầm nguy hiểm:

~~~java
@Bean
@StepScope
ItemProcessor<Order, OrderResult> myProcessor() {
    return new StatefulOrderProcessor();
}
~~~

`@StepScope` gắn vòng đời bean với **StepExecution**, không phải với từng **thread** hoặc từng **item**. Trong multi-threaded step, những thread xử lý chunk của cùng StepExecution có thể sử dụng **cùng một scoped processor instance**. Vì vậy việc gắn `@StepScope` **không thay thế** kiểm tra thread safety.

`@StepScope` vẫn hữu ích khi processor cần tham số của job:

~~~java
@Bean
@StepScope
ItemProcessor<Order, OrderResult> discountProcessor(
        @Value("#{jobParameters['discountVersion']}") String version,
        DiscountRulesRepository rulesRepository) {

    // Chỉ đọc một snapshot quy tắc bất biến cho StepExecution.
    DiscountRules rules = rulesRepository.loadImmutable(version);

    return order -> new OrderResult(
            order.id(),
            rules.calculateNet(order.amount(), order.discountRate()),
            order.businessDate());
}
~~~

Trong ví dụ, `DiscountRules` phải thực sự bất biến hoặc cho phép đọc đồng thời. Nếu `loadImmutable` trả về một object có cache mutable không đồng bộ, chỉ thêm `@StepScope` vẫn không làm processor an toàn.

**So sánh:** ở **partitioning**, các worker partition có StepExecution riêng, nên `@StepScope` có thể tạo instance riêng theo StepExecution. Tuy nhiên nếu một worker step lại bật nhiều thread, instance trong partition ấy vẫn có thể bị gọi đồng thời.

## 8. Nếu processor buộc phải giữ trạng thái

Một số bài toán cần cache, giới hạn tốc độ, thống kê hay đối chiếu liên item. Hãy tách rõ **trạng thái phụ trợ** và **trạng thái quyết định kết quả nghiệp vụ**:

| Nhu cầu | Cách thiết kế gợi ý | Giới hạn cần nhớ |
| --- | --- | --- |
| Đếm số lần gọi để theo dõi | `LongAdder`, Micrometer counter hoặc metric theo tag | Counter không tương ứng số item commit khi có rollback/retry |
| Cache dữ liệu tra cứu | Dữ liệu bất biến hoặc cache concurrent với chiến lược tải an toàn | Cache key phải gồm version/snapshot; xem tác động eviction |
| Dùng formatter/rules | Chọn immutable object, truyền qua constructor | Không chia sẻ instance formatter mutable |
| Ghi lịch sử item | Ghi theo transaction với business key và unique constraint | Không để `ArrayList` trong processor làm nguồn sự thật |
| Gộp tổng theo nhóm | Đưa aggregate xuống DB, thiết kế reducer/partition theo key | Kết quả phụ thuộc thứ tự nếu thuật toán không giao hoán |
| Rate limiting | Dùng limiter thread-safe ở service riêng | Giảm throughput; có thể làm giới hạn toàn hệ thống khác mong đợi |

### Dùng synchronized có phải là giải pháp?

~~~java
@Override
public synchronized OrderResult process(Order order) {
    return compute(order);
}
~~~

Đồng bộ hóa toàn bộ `process` có thể ngăn concurrent access vào state của instance, nhưng về cơ bản **tuần tự hóa phần xử lý**. Nếu processor là nơi tiêu tốn nhiều CPU nhất, đây có thể phá hủy lợi ích của multi-threaded step. Đồng bộ chỉ hữu ích khi vùng cần bảo vệ ngắn và bất biến được định nghĩa rõ; cần đo contention thực tế.

### ThreadLocal có giúp tạo state riêng theo thread?

`ThreadLocal` tách giá trị theo thread, nhưng thread pool **tái sử dụng thread** giữa các chunk, StepExecution và thậm chí giữa các job tùy cấu hình. Nó có thể giữ dữ liệu cũ, gây rò bộ nhớ hoặc sai correlation ID. Nếu buộc dùng `ThreadLocal`, phải xác định vòng đời, khởi tạo và dọn bằng `try/finally` (`remove()`), đồng thời kiểm tra các callback async có chuyển thread hay không. Không dùng `ThreadLocal` làm checkpoint/restart state.

## 9. Retry, skip, rollback có thể gọi lại process(item)

Trong fault-tolerant chunk processing, các lỗi đọc, xử lý hoặc ghi có thể dẫn tới retry/skip/rollback. Tùy tình huống, framework có thể **gọi lại ItemProcessor cho một item**. Đối với processor được chia sẻ giữa nhiều thread, hãy tính cả hai điều kiện: **lời gọi chồng thời gian** và **lời gọi lặp lại**.

Ví dụ:

~~~java
new StepBuilder("orderStep", jobRepository)
        .<Order, OrderResult>chunk(200, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(100)
        .taskExecutor(chunkExecutor)
        .build();
~~~

Đoạn này minh họa chính sách, không phải gợi ý skip hoặc retry tất cả loại ngoại lệ. `TransientDataAccessException` đại diện một số lỗi dữ liệu có thể hồi phục; `InvalidOrderException` là lỗi dữ liệu cần có chính sách nghiệp vụ rõ. Các retry/skip listener, metric và writer cũng phải an toàn khi concurrent.

### Phân biệt filter, skip và rollback

| Tình huống | Hành vi chính | Điều cần kiểm tra |
| --- | --- | --- |
| Processor trả về `null` | Item bị **filter**, không đưa cho writer | `filterCount`, quy tắc lọc |
| Processor ném exception được phép skip | Item bị **skip** theo giới hạn | `processSkipCount`, nguyên nhân và log |
| Lỗi tạm thời được retry | Lời gọi có thể được thực hiện lại | Idempotency, giới hạn retry và thời gian backoff |
| Chunk rollback | Ghi thuộc transaction có thể bị đảo ngược | Side effect bên ngoài transaction có thể đã xảy ra |
| Job/step restart | Xử lý lại phần dữ liệu phù hợp với checkpoint | Input snapshot, reader state và writer không ghi trùng |

**Không nên gửi email, trừ tiền hoặc publish event trực tiếp trong `process`** nếu không có cơ chế chống lặp/tương thích transaction. Một processor stateless về bộ nhớ vẫn có thể gây side effect trùng khi retry.

### Writer idempotent để bảo vệ đầu ra

Ví dụ PostgreSQL cho dữ liệu tính theo từng đơn:

~~~sql
CREATE TABLE order_result (
    job_key       VARCHAR(100) NOT NULL,
    order_id      BIGINT NOT NULL,
    net_amount    NUMERIC(18, 2) NOT NULL,
    business_date DATE NOT NULL,
    PRIMARY KEY (job_key, order_id)
);

INSERT INTO order_result(job_key, order_id, net_amount, business_date)
VALUES (:jobKey, :orderId, :netAmount, :businessDate)
ON CONFLICT (job_key, order_id)
DO UPDATE SET
    net_amount = EXCLUDED.net_amount,
    business_date = EXCLUDED.business_date;
~~~

Khóa `(job_key, order_id)` giúp một item được xử lý lại vẫn có **một dòng kết quả** cho job logic. Nhưng UPSERT không giải quyết mọi nghiệp vụ: nếu hai lần tính tạo hai giá trị khác nhau, lần ghi cuối sẽ thay thế lần trước. Phải cố định snapshot/rules hoặc dùng input version và kiểm tra conflict để giữ tính đúng đắn. Đối với side effect gửi message ra ngoài, có thể cần transactional outbox và consumer idempotent.

## 10. Thứ tự, isolation và sự khác nhau giữa đồng thời với song song thực sự

Một step nhiều thread không bảo đảm `process(A)` xong trước `process(B)` chỉ vì reader đã đọc A trước B. Tương tự, `write` và commit của chunk chứa A có thể diễn ra sau chunk chứa B.

Hệ quả:

- Không xây quy tắc nghiệp vụ phụ thuộc `process` được gọi theo ID tăng dần.
- Nếu mỗi item độc lập, xử lý mất thứ tự thường chấp nhận được; nếu cần xử lý tuần tự theo một khóa tài khoản, có thể phải phân vùng theo khóa hoặc dùng chiến lược đồng bộ/transaction cụ thể.
- Không suy ra `readCount == writeCount` trong mọi tình huống; filter/skip và thất bại ảnh hưởng bộ đếm.
- Hai thread cùng ghi một hàng DB có thể gây **lost update**, lock contention hoặc deadlock tùy SQL/isolation level. Processor stateless không tự sửa vấn đề cạnh tranh ở writer.
- Nếu cần **tính thứ tự hoàn tất chính xác**, mô hình multi-threaded step tự do có thể không phù hợp.

Với nghiệp vụ **tính số dư cộng dồn**, việc xử lý hai giao dịch của cùng tài khoản song song rồi cộng dựa trên giá trị đọc trước là không an toàn. Một số lựa chọn: thực hiện atomic update trong DB, sắp xếp/cô lập theo account key, hoặc chọn partitioning theo account thay vì phân phát chunk tùy ý.

## 11. Kiểm thử processor thuần trước khi test cả step

Kiểm thử unit xác nhận processor tính đúng, deterministic và không biến đổi input:

~~~java
@Test
void computesSameResultForSameInput() throws Exception {
    ItemProcessor<Order, OrderResult> processor = orderProcessor();
    Order input = new Order(
            8742L,
            new BigDecimal("120.00"),
            new BigDecimal("0.10"),
            LocalDate.of(2026, 11, 26));

    OrderResult first = processor.process(input);
    OrderResult second = processor.process(input);

    assertEquals(new BigDecimal("108.00"), first.netAmount());
    assertEquals(first, second);
    assertEquals(new BigDecimal("120.00"), input.amount());
}
~~~

Tuy nhiên, **cùng input cho cùng output ở hai lần gọi tuần tự chưa chứng minh thread safety**. Một processor có race chỉ xuất hiện khi hai lời gọi chồng thời gian. Do đó cần một integration test tạo concurrency có kiểm soát.

## 12. Integration test: chứng minh process chạy trên nhiều thread

Đừng chỉ đo thời gian job và kết luận “chạy nhanh hơn nên chắc chắn song song”. Thời gian phụ thuộc CPU, CI, DB, GC và kích thước dữ liệu. Một kiểm thử ổn định hơn dùng **CountDownLatch** để giữ hai lời gọi `process` cùng ở trạng thái đang thực thi.

### 12.1. Processor probe chỉ dùng trong môi trường test

~~~java
final class ProcessorOverlapProbe implements ItemProcessor<Integer, Integer> {
    final CountDownLatch bothEntered = new CountDownLatch(2);
    final CountDownLatch allowFinish = new CountDownLatch(1);
    final AtomicInteger active = new AtomicInteger();
    final AtomicInteger maxActive = new AtomicInteger();
    final Set<String> threads = ConcurrentHashMap.newKeySet();

    @Override
    public Integer process(Integer item) throws Exception {
        threads.add(Thread.currentThread().getName());
        int now = active.incrementAndGet();
        maxActive.accumulateAndGet(now, Math::max);
        bothEntered.countDown();
        try {
            if (!allowFinish.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for concurrency test");
            }
            return item * 2;
        } finally {
            active.decrementAndGet();
        }
    }
}
~~~

Probe ghi **số lời gọi process đang hoạt động**. Nếu test thấy hai lời gọi đều đã vào trước khi thả cổng, `maxActive >= 2`, đó là bằng chứng trực tiếp về overlap. `Set` thread name giúp phát hiện processor thực thi trên hai thread, nhưng riêng số tên thread **không chứng minh** các lời gọi chồng thời gian.

### 12.2. Step test có hai item, mỗi chunk một item

Để tách kiểm thử concurrency của processor khỏi sự phức tạp của JDBC reader, dùng reader **atomic** trên một danh sách bất biến. Reader này chỉ là fixture kiểm thử, **không có checkpoint bền vững** và không được dùng thay reader production.

~~~java
@TestConfiguration(proxyBeanMethods = false)
class ProcessorConcurrencyTestConfig {
    @Bean
    ProcessorOverlapProbe processorProbe() {
        return new ProcessorOverlapProbe();
    }

    @Bean
    @StepScope
    ItemReader<Integer> testReader() {
        List<Integer> values = List.of(10, 20);
        AtomicInteger position = new AtomicInteger();
        return () -> {
            int index = position.getAndIncrement();
            return index < values.size() ? values.get(index) : null;
        };
    }

    @Bean
    ThreadPoolTaskExecutor testChunkExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(4);
        executor.setThreadNamePrefix("test-chunk-");
        executor.initialize();
        return executor;
    }

    @Bean
    Step concurrentProcessorStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            @Qualifier("testReader") ItemReader<Integer> testReader,
            ProcessorOverlapProbe processorProbe,
            @Qualifier("testChunkExecutor") TaskExecutor executor) {
        return new StepBuilder("concurrentProcessorStep", jobRepository)
                .<Integer, Integer>chunk(1, transactionManager)
                .reader(testReader)
                .processor(processorProbe)
                .writer(chunk -> { /* không ghi ra hệ thống ngoài */ })
                .taskExecutor(executor)
                .build();
    }

    @Bean
    Job processorConcurrencyJob(JobRepository jobRepository,
                                Step concurrentProcessorStep) {
        return new JobBuilder("processorConcurrencyJob", jobRepository)
                .start(concurrentProcessorStep)
                .build();
    }
}
~~~

Vì `chunk(1)`, hai item có thể nằm trong hai chunk khác nhau; cấu hình executor cho phép tối thiểu hai thread. `@StepScope` ở đây tạo **reader mới theo StepExecution**, còn `AtomicInteger` bảo vệ việc cấp vị trí đọc khi hai thread truy cập reader ấy. Reader vẫn **không có khả năng restart**, vì đây là fixture kiểm tra scheduling.

### 12.3. JUnit 5 integration test

Giả định test application có cấu hình Spring Batch infrastructure hợp lệ (JobRepository, transaction manager, DataSource) và chỉ chạy một test dùng probe này trên mỗi instance context. Có thể dùng `@DirtiesContext` hoặc tạo fixture mới cho từng test nếu tổ chức nhiều test case.

~~~java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@Import(ProcessorConcurrencyTestConfig.class)
class ProcessorConcurrencyIT {
    @Autowired JobLauncherTestUtils jobLauncherTestUtils;
    @Autowired ProcessorOverlapProbe probe;
    @Autowired
    @Qualifier("processorConcurrencyJob")
    Job job;

    @Test
    void processorCallsActuallyOverlap() throws Exception {
        jobLauncherTestUtils.setJob(job);
        ExecutorService launcherThread = Executors.newSingleThreadExecutor();

        JobParameters params = new JobParametersBuilder()
                .addString("test.run.id", UUID.randomUUID().toString())
                .toJobParameters();

        try {
            Future<JobExecution> jobFuture = launcherThread.submit(
                    () -> jobLauncherTestUtils.launchJob(params));

            try {
                assertTrue(probe.bothEntered.await(15, TimeUnit.SECONDS),
                        "Two chunks must reach process concurrently");
                assertEquals(2, probe.threads.size());
                assertTrue(probe.maxActive.get() >= 2);
                assertFalse(jobFuture.isDone(),
                        "Job must still be waiting at probe");
            } finally {
                probe.allowFinish.countDown();
            }

            JobExecution execution = jobFuture.get(35, TimeUnit.SECONDS);
            assertEquals(BatchStatus.COMPLETED, execution.getStatus());

            StepExecution step = execution.getStepExecutions().iterator().next();
            assertEquals(2L, step.getReadCount());
            assertEquals(2L, step.getWriteCount());
        } finally {
            probe.allowFinish.countDown();
            launcherThread.shutdownNow();
        }
    }
}
~~~

Trong một số tổ hợp Spring Batch/Boot, cần cấu hình JobLauncherTestUtils hoặc `JobLauncher` cho test cụ thể; đoạn code trên giả định `@SpringBatchTest` đang được cấu hình đúng và chỉ có job mục tiêu. Các import từ JUnit 5, Spring Batch, Spring Boot Test, `java.util.concurrent` và `java.util` được lược bớt để tập trung vào ý tưởng.

**Vì sao launchJob nằm ở thread riêng?** Trong nhiều cấu hình, `launchJob` chờ job kết thúc; nếu gọi trên thread test rồi mới chờ latch, test không thể mở cổng cho processor. Một executor riêng cho **lệnh khởi chạy test** khác với executor dùng để thực thi chunk.

**Lưu ý về timeout:** timeout ở latch là điều kiện **phòng test treo**; không phải một lời khẳng định rằng processor production phải xong trong 15 giây. Khi test fail, `finally` luôn giải phóng cổng để tránh giữ thread mãi. Nếu executor bị đổi sang chỉ một thread hoặc step vô tình mất `.taskExecutor(...)`, phép thử phải fail do hai lời gọi không thể cùng đi qua latch.

## 13. Kiểm thử đúng dữ liệu, lỗi và restart

Kiểm thử overlap là **cần**, nhưng chỉ kiểm tra cấu trúc đồng thời. Với workload thực, cần ba lớp bằng chứng bổ sung:

| Lớp test | Kịch bản | Assertion quan trọng |
| --- | --- | --- |
| **Data correctness** | Nạp N item với ID duy nhất, chạy nhiều thread | Không thiếu/trùng khóa; giá trị sau xử lý đúng; filter/skip hợp lý |
| **Fault tolerance** | Chèn lỗi process tạm thời hoặc dữ liệu bất hợp lệ | Retry/skip đúng chính sách; không side effect trùng |
| **Restart** | Dừng hoặc làm fail giữa nhiều chunk đã commit | Đọc lại đúng phần cần thiết, không trùng business effect |
| **Resource contention** | Hạ DB pool hoặc cho nhiều worker ghi cùng bảng | Không mất cập nhật; không tạo deadlock không được xử lý |
| **Performance** | So sánh 1, 2, 4, 8 thread trên cùng workload | Throughput/CPU/GC/DB wait phù hợp giả thuyết bottleneck |

### Kiểm thử restart phải dựa trên nguồn bền vững

Không dùng reader `AtomicInteger` trong test ở phần 12 để kết luận một production job restart an toàn. Nó không lưu checkpoint bền vững. Đối với restart:

1. Dùng database hoặc file input ổn định, có bộ dữ liệu và khóa duy nhất.
2. Ghi lại `JobExecution`, `StepExecution`, các bộ đếm read/write/commit/rollback và dữ liệu đích của lần chạy đầu.
3. Tạo lỗi sau khi một số chunk đã commit; làm job thất bại.
4. Restart **cùng JobInstance** với identifying JobParameters nhất quán, sau khi sửa nguyên nhân lỗi.
5. Kiểm tra tập khóa và giá trị cuối, đồng thời đối soát các side effect bên ngoài transaction.

Multi-threaded step có thể hoàn tất chunk ngoài thứ tự, nên chiến lược checkpoint/restart của reader phải được kiểm tra **đặc biệt kỹ**. Nếu nguồn dữ liệu không thể xác định item nào đã xử lý chính xác khi restart, cân nhắc chuyển sang partitioning theo các vùng không giao nhau hoặc thiết kế idempotent replay thay vì dựa hoàn toàn vào một vị trí đọc.

### Kiểm thử negative nhằm chứng minh test có khả năng phát hiện lỗi

Trong **môi trường test riêng**, thử:

- Đổi processor thuần thành một bản có `long counter` mutable, tạo nhiều item, xác minh test invariant phát hiện trùng/mất thứ tự theo yêu cầu.
- Thay executor bằng executor tuần tự: overlap test phải **fail có timeout**, không treo.
- Cho writer ném lỗi tạm thời sau một số item; xác minh retry/rollback và tính idempotent của kết quả.
- Cho một luồng chậm có chủ đích; xác minh không giả định thứ tự commit trùng thứ tự input.

Những biến thể cố ý gây lỗi này không phải cấu hình production và không được giữ trong đường chạy bình thường của job.

## 14. Đo nút thắt trước và sau khi tăng số thread

Tăng số thread có ích khi phần công việc có khả năng chạy độc lập và vẫn còn tài nguyên. Ví dụ processor tốn CPU nhưng DB đọc/ghi rất nhẹ, việc chạy nhiều chunk có thể tăng throughput. Nếu phần lớn thời gian dành cho DB connection wait hoặc một đoạn `synchronized`, tăng thread có thể làm job **chậm hơn**.

Theo dõi ít nhất:

- **Throughput:** item đọc/ghi mỗi giây, thời gian hoàn thành job, throughput theo từng cấu hình.
- **Processor:** thời gian `process` trung bình và p95/p99 (nếu instrumentation cho phép), số lời gọi đồng thời, lỗi/retry/filter.
- **Executor:** active threads, queue depth, rejected tasks, thời gian chờ task.
- **DB:** active/idle/waiting connections, commit latency, lock wait, deadlock, batch write time.
- **JVM:** CPU utilization, heap allocation, GC pause, thread contention.
- **Batch metadata:** readCount, writeCount, filterCount, skipCount, commitCount, rollbackCount.

Thử nghiệm có thể bắt đầu như sau:

| Lần thử | Thread pool | Chunk size | Cần quan sát |
| --- | --- | --- | --- |
| A | 1 thread | 100 | Baseline độ đúng và thời gian |
| B | 2 threads | 100 | CPU/DB có còn dư tài nguyên không |
| C | 4 threads | 100 | Throughput có tăng tương xứng không |
| D | 4 threads | 200 | Ít commit hơn có bù tăng memory/rollback không |
| E | 8 threads | 200 | Queue/connection pool có thành bottleneck không |

Đây là **ma trận thí nghiệm**, không phải thông số tối ưu cho mọi hệ thống. Khi so sánh, giữ tập dữ liệu, phiên bản quy tắc, hạ tầng DB và điều kiện tải càng ổn định càng tốt. Nếu dùng nguồn có cache, cần ghi nhận hiệu ứng warm-up.

Không kết luận chỉ từ `maxPoolSize`: hãy đo **số lời gọi processor thực sự chồng thời gian**, thời gian reader/writer và số connection đang sử dụng. Nếu processor thuần CPU và CPU đã đầy, tăng thêm thread có thể chủ yếu tăng context switching.

## 15. Các dấu hiệu lỗi thường gặp

| Triệu chứng | Gốc rễ có thể | Hướng xử lý |
| --- | --- | --- |
| Dữ liệu sai ngẫu nhiên khi bật nhiều thread | Field mutable, formatter/cache không thread-safe | Làm processor stateless; rà soát dependency |
| Số thứ tự item không ổn định | Dựa vào counter hoặc thứ tự `process` | Dùng business key/snapshot; bỏ phụ thuộc scheduling |
| Bị trùng side effect sau retry | Processor gọi API/gửi message ngoài transaction | Chuyển side effect sang outbox/idempotent operation |
| Tăng thread nhưng throughput không tăng | Reader bị đồng bộ, DB pool thiếu, writer khóa chung | Đo bottleneck; cân nhắc partitioning |
| Job chạy xong nhưng thiếu dữ liệu sau restart | Reader checkpoint không phù hợp với out-of-order chunks | Kiểm thử restart; chia vùng ổn định và dedup |
| Processor chạy tuần tự dù đặt pool 8 | Executor/throttle đang giới hạn hoặc bottleneck khác | Probe overlap, metric active threads, kiểm tra cấu hình |
| Memory tăng theo thời gian | Processor giữ List/Map, ThreadLocal không dọn, queue quá lớn | Tránh giữ item, dọn ThreadLocal, giới hạn queue |
| Skip count khác kỳ vọng | Filter, skip, rollback/retry bị hiểu lẫn | Đối soát per-item và thống kê StepExecution |

## 16. Quy trình thực hành áp dụng vào một job thật

1. **Kiểm tra processor hiện có:** liệt kê field mutable, cache, formatter, listener, service gọi bên trong và các thao tác ngoài transaction.
2. **Chuyển đổi sang stateless:** đầu vào bất biến, biến trung gian cục bộ, output mới, cấu hình nghiệp vụ là snapshot bất biến; dùng business key ổn định.
3. **Kiểm tra reader/writer:** xác minh hợp đồng thread safety và restart, transaction boundary, unique constraint và idempotency.
4. **Đo baseline một thread:** item/giây, CPU, DB latency, GC, lỗi và tỷ lệ filter/skip.
5. **Bật TaskExecutor có giới hạn:** bắt đầu bằng 2 thread, tăng dần khi số liệu cho thấy còn tài nguyên.
6. **Chạy integration test overlap:** dùng latch để xác nhận `process` thực sự được gọi đồng thời.
7. **Chạy test dữ liệu/lỗi/restart:** đo số lượng và giá trị, tạo rollback, kiểm chứng chạy lại không nhân đôi tác động.
8. **Theo dõi production:** alarm theo throughput, backlog, connection wait, skip/retry và sai lệch dữ liệu; giữ phương án giảm concurrency khi bottleneck mới xuất hiện.

### Checklist trước khi đưa vào vận hành

- [ ] `ItemProcessor` và các dependency được gọi từ nó thread-safe, hoặc không có mutable shared state.
- [ ] Kết quả của processor không phụ thuộc thứ tự chạy hoặc thời điểm retry ngoài hợp đồng nghiệp vụ.
- [ ] `@StepScope` được hiểu đúng theo **StepExecution**, không được xem là per-thread scope.
- [ ] Reader/writer phù hợp với concurrent chunk processing và chiến lược restart thực tế.
- [ ] Các thao tác ghi được ràng buộc bởi transaction, unique key và idempotency khi cần.
- [ ] Có kiểm thử đồng thời bằng latch, kiểm thử data correctness, rollback và restart.
- [ ] Executor, queue và DB pool được cấu hình từ số đo; không đặt concurrency vô hạn.
- [ ] Đã chuẩn bị metric, log correlation và cách giảm concurrency nếu tài nguyên bị nghẽn.

**Ghi nhớ:** Với multi-threaded step, câu hỏi trọng tâm không chỉ là **“Spring Batch có tạo nhiều thread không?”** mà là **“nhiều thread gọi cùng ItemProcessor có còn cho kết quả đúng, chịu được retry/restart và dùng tài nguyên hiệu quả không?”**. Thiết kế stateless, dữ liệu bất biến, writer idempotent và kiểm thử concurrency có điều khiển là nền tảng để mở rộng workload lớn một cách đáng tin cậy.
