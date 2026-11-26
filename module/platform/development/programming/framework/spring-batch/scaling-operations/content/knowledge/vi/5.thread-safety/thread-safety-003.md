# Reader không an toàn khi dùng nhiều thread

> **Chương:** An toàn luồng
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và xử lý phân tán. Bài này tập trung vào việc bảo vệ luồng đọc, đo điểm nghẽn và giữ tính đúng đắn khi retry/restart.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao một `ItemReader` hoạt động đúng trong step tuần tự vẫn có thể đọc trùng, bỏ sót hoặc làm hỏng trạng thái khi nhiều thread cùng gọi `read()`.
2. Phân biệt **an toàn luồng của reader**, **tính đúng đắn của checkpoint/restart** và **tính an toàn của toàn bộ pipeline**.
3. Chọn giữa đọc tuần tự, khóa `read()` bằng `SynchronizedItemStreamReader`, tạo reader độc lập theo partition hoặc thay đổi kiến trúc xử lý.
4. Thiết kế cách kiểm thử dữ liệu và đo throughput trước khi tăng số thread trong production.

## 1. Vấn đề xuất hiện khi nào?

Một chunk-oriented step thường thực hiện chu kỳ **read → process → write → commit**. Trong cấu hình tuần tự, chỉ một thread gọi `reader.read()` để lấy từng item. Khi gắn `TaskExecutor` vào cùng step, nhiều chunk có thể chạy đồng thời và nhiều thread có thể gọi **cùng một instance reader**.

~~~mermaid
flowchart TD
    R["Một ItemReader dùng chung<br/>cursor / vị trí file / bộ đệm"]
    T1["Thread A<br/>read → process → write"]
    T2["Thread B<br/>read → process → write"]
    T3["Thread C<br/>read → process → write"]
    R --> T1
    R --> T2
    R --> T3
    T1 --> DB[("Đích dữ liệu")]
    T2 --> DB
    T3 --> DB
~~~

Mũi tên từ reader sang ba thread biểu diễn việc **chia sẻ trạng thái**, không có nghĩa mỗi thread sở hữu một bản sao reader. Một số trạng thái có thể thay đổi trong lúc gọi `read()`: số dòng hiện tại, con trỏ JDBC, chỉ số trang, iterator, bộ đệm nội bộ, cờ kết thúc dữ liệu và trạng thái lưu vào `ExecutionContext`.

**Thread-safe** nghĩa là các lời gọi đồng thời không phá vỡ các bất biến của reader. Điều này phải được xác nhận từ tài liệu hoặc cơ chế đồng bộ hóa cụ thể của implementation; giao diện `ItemReader<T>` tự nó không đưa ra bảo đảm như vậy. Gắn `@StepScope` cũng **không** tạo một reader riêng cho từng thread của cùng `StepExecution`: scope này gắn với step, không phải thread.

### Ví dụ race condition nhỏ

~~~java
// Minh họa lỗi, không sử dụng trong production.
final class UnsafeSequenceReader implements ItemReader<Long> {
    private long nextId = 1;
    private final long maxId = 1_000;

    @Override
    public Long read() {
        if (nextId > maxId) {
            return null;
        }
        return nextId++; // Đọc và tăng gồm nhiều thao tác, không nguyên tử.
    }
}
~~~

Nếu hai thread cùng thấy `nextId == 42` trước khi một bên ghi giá trị mới, cả hai có thể trả về `42`; một giá trị khác có thể bị bỏ qua. Việc đọc/ghi không được đồng bộ còn có vấn đề về khả năng nhìn thấy giá trị giữa các thread. Sửa `nextId` thành `AtomicLong` chỉ giải quyết một phần của ví dụ này; với reader có **nhiều biến trạng thái phụ thuộc nhau** (cursor, bộ đệm, trạng thái checkpoint), một biến atomic không bảo vệ được toàn bộ thao tác đọc.

| Hiện tượng | Nguyên nhân thường gặp | Hậu quả |
| --- | --- | --- |
| Item được trả về hai lần | Hai lời gọi `read()` cùng quan sát/chỉnh sửa vị trí | Ghi trùng; đếm sai; vi phạm unique key |
| Bỏ sót item | Vị trí đọc bị tăng hoặc cập nhật sai | Mất dữ liệu âm thầm |
| Exception ngẫu nhiên | Cursor, stream hoặc iterator bị sử dụng chồng chéo | Job thất bại không ổn định |
| Dữ liệu ghi ra khác thứ tự đầu vào | Chunk chạy và commit đồng thời | Không phù hợp nếu nghiệp vụ yêu cầu thứ tự |
| Restart không khớp dữ liệu đã commit | Checkpoint biểu diễn vị trí đọc chung nhưng các chunk hoàn thành khác thứ tự | Đọc lại hoặc bỏ sót item sau sự cố |

Các reader dạng cursor/stream như `FlatFileItemReader` và `JdbcCursorItemReader` có trạng thái nội bộ và không nên mặc nhiên coi là an toàn khi dùng chung giữa nhiều thread. Reader dạng paging hoặc reader tự viết cũng cần kiểm tra **đúng implementation và phiên bản Spring Batch đang dùng**; chữ “paging” không tự động đồng nghĩa với thread-safe.

## 2. Vì sao chỉ khóa reader đôi khi vẫn chưa đủ?

Để xem một step chạy song song có đúng hay không, phải xét ba lớp riêng biệt:

- **Đọc:** Hai lời gọi `read()` có đồng thời làm hỏng vị trí đọc, trả trùng hoặc mất item không?
- **Xử lý/ghi:** `ItemProcessor`, `ItemWriter`, cache, collection và kết nối được chia sẻ có chịu được các lời gọi đồng thời không? Output có cần đúng thứ tự không?
- **Transaction và restart:** Sau khi một chunk rollback hoặc tiến trình dừng đột ngột, lần chạy tiếp có thể tái xử lý item nào? Cách ghi có chống trùng và bảo toàn tính nhất quán không?

Ví dụ, khóa `read()` có thể làm cho thread A đọc item 101 trước thread B đọc item 102, nhưng thread B có thể **commit 102 trước khi A commit 101**. Nếu A thất bại và checkpoint của reader đã tiến quá xa, chỉ nhìn vào vị trí đọc sẽ không thể kết luận an toàn rằng 101 đã ghi thành công. Đồng bộ lời gọi đọc không tự tạo ra thứ tự commit hay bảo đảm exactly-once đầu cuối.

Trong Spring Batch, `ItemStream` có các hook `open`, `update` và `close`, còn `ExecutionContext` lưu trạng thái hỗ trợ restart. Với một reader chung, cả vòng đời reader lẫn việc cập nhật checkpoint phải được xem xét. Đặc biệt, **đừng bật lưu state rồi giả định checkpoint của một cursor chia sẻ có thể đại diện chính xác cho các chunk commit không theo thứ tự**.

## 3. Các phương án xử lý và giới hạn

| Phương án | Cách hoạt động | Khi nên chọn | Giới hạn chính |
| --- | --- | --- | --- |
| **Giữ step tuần tự** | Một thread đọc, xử lý và ghi | Đọc là phần khó chia, workload chưa cần song song | Throughput bị giới hạn bởi một luồng |
| **Khóa lời gọi đọc** | `SynchronizedItemStreamReader` tuần tự hóa `read()` trên một delegate | Reader khó thay thế, xử lý/ghi tốn thời gian hơn đọc | Đọc vẫn là điểm nghẽn; restart cần thiết kế riêng |
| **Reader riêng theo partition** | Chia input thành các phần **không chồng lấn**; mỗi `StepExecution` mở reader riêng | Tệp độc lập, khoảng ID, tenant hoặc key-range rõ ràng | Cần partitioner, ranh giới dữ liệu ổn định và kiểm soát phân phối tải |
| **Xử lý phân tán** | Remote partitioning hoặc remote chunking tùy bài toán | Một máy đã bão hòa CPU/I/O hoặc cần nhiều worker | Phức tạp hơn về truyền nhận, lỗi, retry, thứ tự và idempotency |

Không có phương án nào tối ưu cho mọi workload. Nếu phần lớn thời gian nằm trong truy vấn đọc tuần tự, thêm thread sau một reader có khóa thường không tăng nhiều throughput. Nếu thời gian nằm trong biến đổi CPU hoặc ghi I/O độc lập, nhiều chunk chạy song song có thể giúp ích ngay cả khi thao tác đọc được tuần tự hóa.

## 4. Cách bảo vệ một reader bằng SynchronizedItemStreamReader

Spring Batch cung cấp `SynchronizedItemStreamReader` để đồng bộ các lời gọi `read()` tới một `ItemStreamReader` bên dưới. Nó hữu ích khi cần nhiều thread xử lý cùng một step nhưng reader gốc không an toàn.

Ví dụ sau minh họa kiểu cấu hình của **Spring Batch 5.x**. File input có một bản ghi văn bản trên mỗi dòng; `processor` và `writer` là các bean riêng **đã được kiểm chứng thread-safe**. Đường dẫn và cấu hình transaction phải điều chỉnh theo ứng dụng thực tế.

~~~java
@Configuration
class OrdersImportStepConfig {

    @Bean
    FlatFileItemReader<String> ordersFileReader(
            @Value("file:/data/input/orders.txt") Resource resource) {
        return new FlatFileItemReaderBuilder<String>()
                .name("ordersFileReader")
                .resource(resource)
                .lineMapper((line, lineNumber) -> line)
                // Không dùng checkpoint vị trí đọc chung cho các chunk song song.
                .saveState(false)
                .build();
    }

    @Bean
    SynchronizedItemStreamReader<String> ordersSynchronizedReader(
            FlatFileItemReader<String> ordersFileReader) {
        return new SynchronizedItemStreamReaderBuilder<String>()
                .delegate(ordersFileReader)
                .build();
    }

    @Bean
    ThreadPoolTaskExecutor ordersStepExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("orders-step-");
        return executor;
    }

    @Bean
    Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            SynchronizedItemStreamReader<String> ordersSynchronizedReader,
            ItemProcessor<String, String> processor,
            ItemWriter<String> writer,
            ThreadPoolTaskExecutor ordersStepExecutor) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<String, String>chunk(100, transactionManager)
                .reader(ordersSynchronizedReader)
                .processor(processor)
                .writer(writer)
                .taskExecutor(ordersStepExecutor)
                .build();
    }
}
~~~

Ở ví dụ này, `SynchronizedItemStreamReaderBuilder` tạo decorator chỉ để tuần tự hóa thao tác **read**. Việc `ThreadPoolTaskExecutor` có tối đa 4 thread không có nghĩa 4 thread được đọc file đồng thời. Các thread có thể xử lý và ghi các chunk khác nhau cùng lúc, tùy trạng thái executor và khả năng của writer.

**Cảnh báo restart quan trọng:** `saveState(false)` ngăn reader lưu checkpoint vị trí đọc trong `ExecutionContext`. Đây là lựa chọn có chủ đích cho ví dụ reader chung, **đổi lấy việc không thể dựa vào checkpoint của reader để tiếp tục chính xác từ dòng cuối cùng khi restart**. Chạy lại có thể đọc từ đầu; do đó đầu ra phải idempotent, có cơ chế loại trùng theo khóa nghiệp vụ, hoặc có kế hoạch làm sạch/khôi phục. Tài liệu của `SynchronizedItemStreamReader` cũng lưu ý tính restart có thể không phù hợp nếu việc xử lý lại một item gây vấn đề.

Những điều decorator **không** giải quyết:

- Không tự đồng bộ `ItemProcessor`, `ItemWriter`, shared cache hoặc logic ghi vào file chung.
- Không đảm bảo thứ tự kết quả theo thứ tự dòng đầu vào.
- Không tăng tốc khâu đọc vì các lời gọi `read()` vẫn đi qua một khóa.
- Không biến checkpoint/transaction của nhiều chunk song song thành một giao dịch tổng thể.
- Không thay thế retry, giới hạn số kết nối, giám sát lỗi hay chiến lược restart.

Nếu chỉ muốn an toàn với cách ghi hiện tại mà chưa có yêu cầu tăng throughput, **giữ step tuần tự** có thể là phương án chính xác và ít rủi ro nhất.

## 5. Cách tốt hơn khi cần đọc song song: partitioning

Khi nguồn dữ liệu có thể chia thành các phần độc lập, partitioning thường rõ ràng hơn việc chia sẻ một cursor. Một **manager step** tạo các `ExecutionContext` cho các partition. Mỗi **worker step** có `StepExecution` riêng, reader riêng và trạng thái checkpoint riêng.

~~~mermaid
flowchart TB
    P["Manager step / Partitioner"]
    P --> A["Partition A<br/>file-01.csv<br/>Reader A"]
    P --> B["Partition B<br/>file-02.csv<br/>Reader B"]
    P --> C["Partition C<br/>file-03.csv<br/>Reader C"]
    A --> O[("Kho đích")]
    B --> O
    C --> O
~~~

Giả sử partitioner gán đường dẫn từng file vào key `fileName` trong `stepExecutionContext`. Reader của worker có thể tạo theo ngữ cảnh partition như sau:

~~~java
@Bean
@StepScope
FlatFileItemReader<String> partitionFileReader(
        @Value("#{stepExecutionContext['fileName']}") Resource file) {

    return new FlatFileItemReaderBuilder<String>()
            .name("partitionFileReader")
            .resource(file)
            .lineMapper((line, lineNumber) -> line)
            // Mỗi partition có ExecutionContext riêng để checkpoint.
            .saveState(true)
            .build();
}
~~~

**Đây là ví dụ dùng trong worker step có partitioner**, không phải cách làm cho reader an toàn khi nhiều thread dùng chung một `StepExecution`. Mỗi partition phải nhận đúng một phần input và được thực thi một lần tại một thời điểm; số partition có thể lớn hơn số thread. Với input theo database, partitioner có thể chia theo ID range hoặc shard key, còn reader của mỗi partition lọc bằng điều kiện riêng như `WHERE id >= :minId AND id < :maxId`.

Để partitioning thực sự đúng:

1. **Không giao thoa:** Các khoảng hoặc tệp không chồng lấn, không bỏ vùng dữ liệu, và partition ID ổn định qua restart.
2. **Nguồn nhất quán:** Nếu dữ liệu nguồn thay đổi trong lúc chạy, cân nhắc watermark, snapshot hoặc quy tắc chọn dữ liệu cố định; chỉ chia range không bảo vệ trước bản ghi mới/cập nhật.
3. **Checkpoint độc lập:** Mỗi partition lưu vị trí theo `StepExecution` của chính nó; phải cấu hình tên reader/state và giới hạn số worker phù hợp.
4. **Ghi an toàn:** Nếu nhiều partition ghi chung bảng, cần unique key, giao dịch, upsert/idempotency hợp lý; tránh khóa hàng/bảng gây nghẽn.
5. **Retry/restart có chủ đích:** Lỗi ở partition nào cần được chạy lại theo trạng thái của partition đó. Thao tác ghi ra hệ thống ngoài transaction vẫn cần cơ chế chống ghi trùng.

So với khóa reader dùng chung, partitioning có thể tăng song song **ngay ở khâu đọc**, đồng thời tạo ranh giới để quan sát và restart dễ kiểm soát hơn. Đổi lại, chi phí thiết kế partitioner và bảo đảm cân bằng tải cao hơn.

## 6. Retry, restart và nguy cơ xử lý trùng

Chỉ tiêu “không có exception khi tăng thread” chưa đủ để kết luận job đúng. Hãy phân biệt:

| Tình huống | Điều cần hiểu | Biện pháp |
| --- | --- | --- |
| Một chunk rollback | Một số item đã đọc nhưng chưa commit có thể được thử lại | Processor chịu được gọi lại; writer tương thích transaction |
| Job dừng giữa chừng | Checkpoint reader và các chunk đã commit có thể lệch nhau trong step đa luồng | Ưu tiên partition + checkpoint riêng; với reader chia sẻ dùng chính sách replay/idempotency |
| Gọi API ngoài hoặc gửi sự kiện | Tác dụng phụ có thể đã xảy ra dù transaction DB rollback | Idempotency key, outbox hoặc cơ chế xác nhận/dedup |
| Job chạy lại sau khi `saveState(false)` | Reader có thể đi qua dữ liệu đã xử lý | Upsert, unique constraint, bảng staging hoặc cơ chế loại trùng |
| Input thay đổi giữa hai lần chạy | Tập item trên lần restart khác với lần trước | Đóng băng tập dữ liệu theo batch ID, snapshot hoặc watermark |

Ví dụ, nếu khóa nghiệp vụ là `order_id`, đích có thể đặt unique constraint trên `(batch_id, order_id)` và thực hiện upsert hoặc ghi idempotent theo yêu cầu. Một unique constraint chỉ *phát hiện/chặn* trùng; phải xác định rõ khi nào coi trùng là thành công và khi nào là lỗi dữ liệu. Không nên hứa “exactly once” chỉ từ `synchronized`, `retry()` hoặc checkpoint.

## 7. Kiểm thử và đo trước khi triển khai

### 7.1. Kiểm tra tính đúng đắn

Dùng tập input cố định có **ID duy nhất**, ví dụ 100.000 bản ghi; lưu số lượng và checksum kỳ vọng. Chạy baseline một thread, sau đó lặp lại với 2, 4, 8 thread trong cùng điều kiện và kiểm tra:

- **Đủ:** Số ID nguồn hợp lệ bằng số ID đích kỳ vọng sau khi trừ các mục được lọc/skip có chủ đích.
- **Không trùng:** Đếm theo khóa nghiệp vụ; so sánh số lượng bản ghi với số lượng ID distinct.
- **Không sai nội dung:** So sánh checksum hoặc aggregate của các trường quan trọng, không chỉ `readCount`/`writeCount`.
- **Đúng khi có lỗi:** Cố ý gây exception trong process/write, timeout nguồn, rollback chunk, rồi restart; kiểm tra không mất và không nhân đôi tác dụng phụ.
- **Ổn định qua nhiều lần chạy:** Race condition có thể chỉ lộ dưới tải và lịch thread khác nhau. Lặp lại đủ nhiều vòng với dữ liệu và thời điểm lỗi khác nhau.

Các chỉ số Spring Batch như `readCount`, `writeCount`, `filterCount`, `readSkipCount`, `processSkipCount`, `writeSkipCount`, `commitCount` và `rollbackCount` hỗ trợ chẩn đoán, nhưng **không thay thế** đối soát đầu vào–đầu ra. `readCount` và `writeCount` có thể khác nhau hợp lệ khi có filter/skip.

### 7.2. Tìm điểm nghẽn thay vì tăng thread theo cảm giác

Quan sát tổng thời gian job, items/giây, p95 thời gian đọc/ghi, CPU, thời gian chờ DB, mức sử dụng connection pool, I/O disk/network, độ dài hàng đợi executor, lock contention và GC. Thử tăng concurrency từng nấc nhỏ.

| Kết quả đo | Khả năng xảy ra | Hướng điều chỉnh |
| --- | --- | --- |
| Throughput gần như đứng yên, thread đợi quanh `read()` | Reader có khóa là điểm nghẽn | Cân nhắc partitioning hoặc tối ưu nguồn đọc |
| CPU bão hòa và throughput tăng chậm | Processor dùng nhiều CPU | Giới hạn thread theo số lõi và chi phí GC |
| Connection pool cạn, query đợi lâu | Writer/reader đồng thời vượt khả năng DB | Chỉnh pool, batch size, index và concurrency có kiểm soát |
| Rollback/lock timeout tăng | Các chunk tranh chấp tài nguyên ghi | Giảm vùng dữ liệu giao thoa, sắp xếp khóa, phân vùng đích |
| Bộ nhớ tăng mạnh | Nhiều chunk lớn, queue lớn hoặc processor giữ dữ liệu | Giảm chunk size, queue capacity, dữ liệu giữ trong RAM |

Một phép thử đơn giản là cố định dataset, database, chunk size và hạ tầng; chỉ thay đổi số thread `1 → 2 → 4 → 8`, ghi lại thông lượng và lỗi. Khi thay đổi nhiều tham số cùng lúc, rất khó biết yếu tố nào tạo ra cải thiện hoặc suy giảm.

## 8. Quy trình ra quyết định cho một hệ thống thực tế

**Bài toán:** Import nhiều triệu đơn hàng từ file, làm giàu dữ liệu qua CPU, ghi vào database. Người vận hành muốn rút ngắn thời gian chạy hằng đêm nhưng vẫn restart được sau sự cố.

1. **Đo baseline tuần tự.** Tách thời gian read, process và write; kiểm tra dữ liệu đầu ra và khả năng chạy lại. Nếu phần đọc chỉ chiếm tỷ lệ nhỏ, còn CPU process chiếm đa số, khóa `read()` có thể là bước thử ngắn hạn hợp lý.
2. **Kiểm tra implementation từng component.** Reader file đang chia sẻ cursor; processor cần tránh mutable shared state; writer phải hỗ trợ ghi đồng thời và transaction. `@StepScope` trong một multi-threaded step không tự cấp reader riêng theo thread.
3. **Thử đồng bộ reader ở môi trường kiểm thử.** Bọc bằng `SynchronizedItemStreamReader`, cấu hình thread pool hữu hạn và viết rõ chính sách replay khi reader không lưu state. Kiểm tra độ đúng và hiệu năng.
4. **Nếu cần đọc song song hoặc restart chính xác hơn, chia file/ID range.** Mỗi partition tạo reader và checkpoint riêng; ràng buộc unique key cho đầu ra và thử restart từng partition.
5. **Vận hành theo số đo.** Theo dõi tiến độ theo partition, thời gian chờ DB, số rollback và tính đầy đủ dữ liệu; giới hạn concurrency theo tài nguyên thực chứ không theo số thread tối đa có thể tạo.

**Câu hỏi tự kiểm tra:** Một `FlatFileItemReader` có `@StepScope` đang được dùng trong step gắn `TaskExecutor` 8 thread. Kết quả ghi đôi khi bị trùng; sau restart có dòng bị thiếu. Vì sao `@StepScope` không giải quyết vấn đề? Nếu bắt buộc xử lý đúng và restart được theo vị trí đọc, bạn sẽ ưu tiên reader có khóa hay partitioning theo file, và những điều kiện nào cần đảm bảo?

**Đáp án định hướng:** Tám thread của **cùng** `StepExecution` vẫn dùng chung reader step-scoped. Reader có khóa có thể xử lý race trong `read()` nhưng không tự giải quyết thứ tự commit/checkpoint. Với tệp tách được, partitioning dùng reader và `ExecutionContext` riêng theo file thường phù hợp hơn, miễn là không chồng lấn input và ghi idempotent.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): các mô hình multi-threaded step, parallel steps và partitioning.
- [Spring Batch API — SynchronizedItemStreamReader](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/item/support/SynchronizedItemStreamReader.html): phạm vi đồng bộ hóa và lưu ý về restart.
- [Spring Batch Reference — ItemReader and ItemWriter](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-reader-writer-implementations.html): reader implementation, cấu hình state và hành vi đọc.

> **Ghi nhớ:** “Đọc được đồng thời” và “khôi phục đúng sau lỗi” là hai bài toán khác nhau. Khi mở rộng Spring Batch, hãy đo bottleneck, bảo vệ shared state, tách checkpoint theo partition nếu có thể và đối soát dữ liệu cả sau khi retry/restart.
