# Commit interval ảnh hưởng hiệu năng Spring Batch như thế nào?

## Mục tiêu bài học

Trong một workload Spring Batch xử lý hàng triệu bản ghi, **commit interval** là tham số quan trọng vì nó xác định lượng công việc gom vào mỗi chunk trước khi hoàn tất giao dịch (transaction). Interval quá nhỏ thường làm tăng số lần commit và overhead; interval quá lớn có thể tăng áp lực bộ nhớ, thời gian giữ tài nguyên và lượng công việc phải thực hiện lại khi có lỗi.

Bài này thuộc chương **Thông lượng** của module **SPRING_BATCH_SCALING_OPERATIONS**, gắn với mục tiêu mở rộng Spring Batch qua multi-threaded step, parallel steps, partitioning và mô hình phân tán. Giá trị commit interval phải được lựa chọn dựa trên phép đo bottleneck, thread safety, retry/restart và giới hạn CPU, database, bộ nhớ, mạng của môi trường thật.

Sau bài học, bạn có thể:

- Giải thích commit interval trong chunk-oriented step và ranh giới transaction/checkpoint.
- Phân tích vì sao tăng chunk size ban đầu giúp cải thiện throughput nhưng sau đó có thể bị bão hòa hoặc giảm.
- Phân biệt chunk size, JDBC fetch size, page size, JDBC batch size và số worker.
- Nhận diện ảnh hưởng tới heap, GC, database lock, transaction duration, retry và restart.
- Thiết kế benchmark, chọn interval dựa trên throughput **và** tính đúng dữ liệu.
- Kết hợp điều chỉnh interval với multi-threaded step hoặc partitioning một cách có kiểm soát.

## 1. Commit interval là gì?

Trong cách xử lý **chunk-oriented**, một step thường lặp lại chu trình:

1. Reader đọc item đầu vào.
2. Processor biến đổi, xác thực hoặc lọc item (nếu được cấu hình).
3. Framework gom các item thành chunk.
4. Writer nhận một chunk đầu ra để ghi.
5. Transaction được commit nếu toàn bộ thao tác liên quan thành công; framework lưu trạng thái/checkpoint theo cơ chế của step.
6. Step chuyển sang chunk tiếp theo cho tới khi hết dữ liệu.

**Commit interval** (thường được cấu hình bằng kích thước chunk) là số item đầu vào mục tiêu của mỗi chu kỳ chunk. Trong Java DSL Spring Batch, ví dụ **chunk(250, transactionManager)** đặt interval là **250**.

~~~mermaid
flowchart LR
    R[ItemReader] --> P[ItemProcessor]
    P --> C["Gom chunk<br/>tối đa khoảng k item đầu vào"]
    C --> W[ItemWriter]
    W --> T[Commit transaction]
    T -. "Chunk tiếp theo" .-> R
~~~

Cần nhớ rằng **250 item đầu vào không có nghĩa chính xác 250 item được ghi**. Processor có thể trả về null để lọc, fault-tolerant step có thể skip bản ghi lỗi, và chunk cuối thường ngắn hơn. Khi có retry/rollback, số lượt read/process/write thực tế cũng có thể khác số item duy nhất.

Trong trường hợp đơn giản không filter, skip, retry và mọi item đều được xử lý thành công, số chunk xấp xỉ:

\[
\operatorname{chunkCount} \approx \left\lceil \frac{N}{k} \right\rceil
\]

với \(N\) là số item đầu vào và \(k\) là commit interval. Đây là **ước lượng số chunk**, không phải bộ đếm chính xác tất cả giao dịch DB. Spring Batch còn có hoạt động metadata và đường xử lý đặc biệt tùy cấu hình.

### Ví dụ với một triệu item

| Commit interval | Số chunk xấp xỉ | Nhận xét ban đầu |
| ---: | ---: | --- |
| 1 | 1.000.000 | Rất nhiều chu kỳ transaction |
| 10 | 100.000 | Giảm overhead so với 1 |
| 100 | 10.000 | Mốc thử nghiệm thường dễ kiểm soát |
| 500 | 2.000 | Ít commit hơn, chunk dài hơn |
| 1.000 | 1.000 | Tăng lượng dữ liệu trong mỗi transaction |
| 10.000 | 100 | Ít chunk nhưng có thể tạo áp lực tài nguyên |

Bảng cho biết sự khác biệt về số chu kỳ, **không** kết luận interval 10.000 nhanh nhất.

## 2. Vì sao commit interval nhỏ tạo overhead?

Mỗi chunk có một phần chi phí tương đối cố định, ngoài công việc đọc và xử lý từng item:

- Commit transaction, đồng bộ transaction log và thay đổi trạng thái giao dịch ở DB.
- Gửi lệnh/nhận phản hồi qua mạng giữa ứng dụng và DB.
- Gọi writer, callback và cơ chế transaction/chunk của framework.
- Lưu checkpoint và metadata của step tại các ranh giới thích hợp.
- Với writer hỗ trợ batch, chuẩn bị và gửi nhiều đợt batch nhỏ thay vì ít đợt batch lớn.

Với commit interval bằng 1, job thực hiện gần như một chu kỳ chunk cho mỗi item. Nếu dữ liệu lớn, overhead cố định bị lặp lại rất nhiều lần.

### Mô hình ước lượng throughput

Một mô hình đơn giản cho một chunk là:

\[
T(k) \approx k \cdot t_{\mathrm{item}} + t_{\mathrm{fixed}}
\]

Trong đó:

- \(k\) là số item/chunk.
- \(t_{\mathrm{item}}\) là thời gian trung bình cần thiết cho phần việc biến đổi theo số item.
- \(t_{\mathrm{fixed}}\) là overhead tương đối cố định cho một chunk, gồm chi phí transaction và tổ chức ghi.
- \(T(k)\) là thời gian hoàn tất chunk theo mô hình.

Nếu chỉ có một luồng và không có lỗi:

\[
\operatorname{throughput}(k)
\approx \frac{k}{T(k)}
= \frac{1}{t_{\mathrm{item}} + t_{\mathrm{fixed}}/k}
\]

Khi tăng \(k\), overhead tính trên mỗi item giảm. Nhưng sau một mức, thành phần \(t_{\mathrm{item}}\) quyết định giới hạn tốc độ; tăng chunk tiếp sẽ có lợi rất ít.

### Phép tính minh họa

Giả sử mất **0,8 ms** để xử lý/ghi phần biến đổi theo từng item và mỗi chunk có overhead **8 ms**. Các số sau là **giả định để hiểu công thức, không phải benchmark thực tế**:

| Interval | Thời gian/chunk ước tính | Throughput ước tính |
| ---: | ---: | ---: |
| 1 | 8,8 ms | ~114 item/s |
| 10 | 16 ms | 625 item/s |
| 100 | 88 ms | ~1.136 item/s |
| 500 | 408 ms | ~1.225 item/s |
| 2.000 | 1.608 ms | ~1.244 item/s |

Trong mô hình này, tốc độ tối đa về lý thuyết xấp xỉ **1.250 item/s**. Bước tăng 1 → 100 rất đáng kể, còn 500 → 2.000 đem lại cải thiện nhỏ. Trên hệ thống thật, các chi phí phụ thuộc vào kích thước batch, contention, network, DB và GC, nên đường throughput còn có thể **giảm xuống**.

## 3. Vì sao commit interval quá lớn có thể phản tác dụng?

### 3.1. Transaction dài và tranh chấp database

Tăng interval làm một transaction có thể tồn tại lâu hơn. Tùy database, isolation level, reader và writer, điều này có thể dẫn đến:

- Connection bị chiếm lâu hơn trong mỗi chunk.
- Khóa ghi được giữ lâu hơn, tăng lock wait hoặc deadlock khi nhiều worker ghi vào dữ liệu liên quan.
- Transaction log, undo/MVCC và các tác vụ duy trì dữ liệu chịu áp lực lớn hơn.
- Vượt transaction timeout hoặc giới hạn hệ thống khi chunk nặng.
- Gây độ trễ lớn cho các giao dịch nghiệp vụ đang chia sẻ database.

Không nên suy luận rằng mọi thao tác đọc đều giữ khóa cho tới commit; hành vi cụ thể phụ thuộc DB và truy vấn. Điều cần đo là **transaction duration, lock wait và tổng tải DB**, thay vì chỉ xem số lần commit giảm.

### 3.2. Bộ nhớ và garbage collection

Ở nhiều thiết kế, framework hoặc writer cần giữ dữ liệu của chunk trong bộ nhớ tới khi xử lý và ghi xong. Reader và ORM có thể giữ thêm cursor, cache, entity hoặc buffer.

Một ước lượng sơ bộ:

\[
M_{\mathrm{chunk}} \approx k \times m_{\mathrm{item}} \times c
\]

với \(m_{\mathrm{item}}\) là lượng bộ nhớ trung bình cho một item/kết quả và \(c\) là số chunk hoạt động đồng thời.

Ví dụ **8 chunk × 2.000 item × 2 KiB/item = 31,25 MiB** dữ liệu thô, chưa bao gồm object overhead, dữ liệu nguồn và kết quả cùng tồn tại, collection buffer hoặc persistence context. Heap thực tế có thể cao hơn đáng kể.

Với JPA/Hibernate, cần đặc biệt xem việc tích lũy entity trong persistence context, flush/clear và cấu hình JDBC batching. Tăng chunk size không tự biến mỗi lời gọi persist thành một batch SQL tối ưu.

### 3.3. Lượng công việc phải làm lại khi rollback

Nếu chunk lỗi trước commit, các thao tác nằm trong transaction của chunk thường bị rollback theo quy tắc của resource tham gia transaction. Khi retry/restart, một phần dữ liệu có thể được xử lý lại.

Ở interval 200, một chunk gặp lỗi thường có phạm vi công việc nhỏ hơn interval 10.000. Với fault-tolerant step, framework có thể thực hiện retry, tách/scan chunk hoặc skip theo policy; vì thế không có quy tắc đơn giản “mọi lỗi luôn chạy lại đúng k item”.

Điểm mấu chốt: **throughput của lần chạy không lỗi chỉ là một nửa câu chuyện**. Trong sản xuất, rollback, retry, kiểm tra đối soát và restart cũng tiêu tốn thời gian.

### 3.4. Khoảng cách giữa các checkpoint

Commit interval lớn có thể làm checkpoint thưa hơn, kéo dài quãng xử lý chưa được ghi nhận hoàn thành nếu job chết đột ngột. Một chunk dài cũng có thể khiến thao tác dừng job phản hồi chậm hơn khi ứng dụng đang chờ I/O hoặc xử lý dữ liệu nặng.

## 4. Phân biệt chunk size, fetch size, page size và batch size

Các thông số này ở những tầng khác nhau và không nên dùng thay thế cho nhau.

| Thông số | Chức năng | Có xác định ranh giới commit? |
| --- | --- | --- |
| **Commit interval / chunk size** | Số item mục tiêu trong một chu kỳ read/process/write | **Có**, trong chunk-oriented step |
| **JDBC fetch size** | Gợi ý cách driver lấy hàng từ result set | Không trực tiếp |
| **JDBC paging page size** | Số hàng reader lấy cho mỗi trang query | Không trực tiếp |
| **JDBC batch size** | Số lệnh SQL gom khi driver/writer hỗ trợ batch | Không trực tiếp |
| **Hibernate batch size** | Kích thước lô DML có thể gom theo cấu hình ORM | Không trực tiếp |
| **Thread pool size** | Số thread có thể chạy song song | Không |
| **Partition count/grid size** | Mức chia phần việc giữa các worker | Không |

Một step có thể sử dụng:

- chunk size = 500;
- paging reader page size = 200;
- JDBC fetch size = 100;
- bốn worker chạy đồng thời.

Reader có thể cần đọc qua nhiều page/fetch để đủ một chunk 500 item; việc lấy xong một trang **không** tạo commit. Mỗi worker có chu kỳ chunk và transaction riêng.

**Đặt page size = chunk size** đôi khi tiện lợi để thử nghiệm, nhưng không phải quy tắc bắt buộc. Cần đo query plan, round trip, số dòng và cấu hình driver. Tương tự, **JdbcBatchItemWriter** có thể gửi lệnh SQL theo batch, nhưng hiệu quả thực tế còn phụ thuộc loại câu lệnh, driver, DB, index và kích thước các batch.

## 5. Cấu hình commit interval trong Java DSL

Ví dụ sau minh họa API Spring Batch 5.x, với reader, processor và writer đã có sẵn trong ứng dụng:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportOrdersConfig {

    public record InputOrder(long id, long amountCents) {}
    public record OrderSummary(long orderId, long totalCents) {}

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<InputOrder> reader,
            ItemProcessor<InputOrder, OrderSummary> processor,
            ItemWriter<OrderSummary> writer) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<InputOrder, OrderSummary>chunk(
                        500, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .build();
    }
}
~~~

**chunk(500, transactionManager)** là điểm đặt commit interval. Ví dụ giả định các bean reader/processor/writer được cấu hình riêng, có kiểu dữ liệu tương thích và reader đủ điều kiện checkpoint/restart. Số **500** chỉ là giá trị minh họa; cần thử nhiều interval trước khi quyết định production.

Một cách tổ chức thực tế là đưa interval vào cấu hình của ứng dụng để thay đổi giữa các lượt benchmark và lưu phiên bản cấu hình của lần chạy. Cấu hình interval **không** tự tạo nhiều thread, không thay đổi cách chia partition, và cũng không tự động kích hoạt JDBC batch writer.

### Chunk size không thay đổi bản chất của API ngoài

Nếu writer gọi HTTP API **một lần cho mỗi item**, tăng interval từ 50 lên 500 không tự biến 500 request thành một batch request. Tốc độ vẫn phụ thuộc số lần gọi, latency và rate limit. Chỉ khi writer và API hỗ trợ gửi lô thì cần nghiên cứu batch request cùng giới hạn payload và tính idempotent.

Nếu processor đang bị nghẽn CPU, chunk lớn đôi khi chỉ giảm phần overhead nhỏ mà không giải quyết được bottleneck.

## 6. Ranh giới transaction và checkpoint trong một chunk

Mô hình thường gặp:

~~~mermaid
sequenceDiagram
    participant S as Spring Batch Step
    participant R as ItemReader
    participant P as ItemProcessor
    participant W as ItemWriter
    participant D as Database

    S->>S: Bắt đầu transaction chunk
    loop Cho đến khi đủ chunk hoặc hết nguồn
        S->>R: read()
        R-->>S: input item
        S->>P: process(input)
        P-->>S: output hoặc null
    end
    S->>W: write(chunk đầu ra)
    W->>D: Ghi SQL / JDBC batch
    S->>S: Cập nhật state và metadata theo chu kỳ
    S->>D: Commit transaction
~~~

Sơ đồ giản lược, nhằm giải thích phạm vi chunk. Thời điểm ghi ExecutionContext, thứ tự callback và transaction của metadata phụ thuộc phiên bản/cấu hình Spring Batch và JobRepository. Không nên coi sơ đồ là thứ tự SQL chính xác.

Nếu writer thất bại trước commit:

- Các thay đổi DB nằm trong transaction đúng cách thường rollback.
- Framework có thể retry, skip hoặc fail step dựa trên chính sách lỗi.
- Reader/processor/writer có thể được gọi lại trong quá trình phục hồi.
- State checkpoint cần phản ánh những phần đã hoàn tất theo cơ chế StepExecution và ItemStream.

**Rollback DB không đồng nghĩa rollback side effect ngoài DB.** Email đã gửi, thông báo đã publish hoặc request HTTP đã thành công thường không được tự động hoàn tác bởi transactionManager của DB. Các thao tác này cần idempotency key, outbox pattern hoặc cơ chế giao dịch phù hợp.

### Ví dụ ghi lặp lại an toàn

Giả sử mỗi giao dịch chỉ có một bản ghi tổng hợp, writer có thể dùng upsert với PostgreSQL:

~~~sql
INSERT INTO payment_summary (transaction_id, total_cents)
VALUES (:transactionId, :totalCents)
ON CONFLICT (transaction_id)
DO UPDATE SET total_cents = EXCLUDED.total_cents;
~~~

Ví dụ yêu cầu khóa **UNIQUE/PRIMARY KEY** trên transaction_id và nghiệp vụ cho phép cập nhật tổng theo cùng khóa. Việc cộng dồn số dư, gửi email hoặc gọi thanh toán ngoài DB đòi hỏi chiến lược chống trùng riêng.

## 7. Commit interval khi có retry, skip và restart

### 7.1. Retry và rollback

Tăng chunk size có thể làm tăng chi phí cho mỗi thất bại, vì nhiều thao tác đã thực hiện trước lỗi sẽ phải được làm lại hoặc xác minh. Khi dùng fault-tolerant step:

- Chỉ retry các exception thực sự có khả năng phục hồi, ví dụ lỗi kết nối tạm thời theo chính sách phù hợp.
- Có giới hạn số lần retry và backoff nếu cần; tránh vòng lặp lỗi liên tục gây quá tải DB.
- Xử lý dữ liệu sai schema/constraint bằng phân loại lỗi rõ ràng thay vì retry vô hạn.
- Theo dõi rollbackCount và độ trễ mỗi chunk trong các bài thử gây lỗi.

Trong các kịch bản lỗi ghi, framework có thể thực hiện thêm các lượt xử lý để nhận diện item có thể skip. Không dùng số item đầu vào nhân số retry làm công thức chính xác cho mọi cấu hình.

### 7.2. Skip và filter

Giả sử chunk có 100 item đầu vào:

- Processor lọc 10 item.
- Có 2 item lỗi được skip hợp lệ.
- Writer ghi 88 item còn lại.

Kích thước chunk đầu vào vẫn được quyết định theo interval, trong khi **writeCount, filterCount và skipCount** phản ánh những chiều khác nhau. Vì vậy phép chia **writeCount / interval** không cho số commit chính xác.

### 7.3. Restart từ trạng thái đã lưu

Với reader hỗ trợ ItemStream và một nguồn dữ liệu có thứ tự ổn định, Spring Batch có thể dùng ExecutionContext để tiếp tục từ checkpoint phù hợp sau khi job thất bại. Nhưng điều đó đòi hỏi:

- Reader được thiết kế restartable và lưu state đúng.
- Writer có tính lặp lại an toàn theo business key.
- Query/snapshot đầu vào không âm thầm thay đổi theo hướng làm mất hoặc nhân đôi item.
- Với partitioning, khoảng dữ liệu và định danh partition ổn định qua lần restart của cùng JobInstance.

Chunk lớn có thể khiến lượng dữ liệu đã đọc nhưng chưa commit nhiều hơn, làm tăng thời gian cần để bắt kịp sau restart. Nếu reader đọc cursor thay đổi giữa các lần chạy, chỉ tăng hay giảm interval đều không giải quyết được vấn đề nhất quán dữ liệu nguồn.

## 8. Khi tăng nhiều thread hoặc worker

**Concurrency** và **commit interval** là hai biến khác nhau. Một step có thể giữ chunk size 500 và tăng từ một lên bốn thread; hoặc giữ bốn thread rồi thử chunk 100, 250 và 500.

### 8.1. Multi-threaded step

Một multi-threaded step phân phối chunk tới các thread trong cùng JVM. Concurrency do **TaskExecutor** quản lý, còn interval xác định mục tiêu chunk của các transaction.

~~~java
@Bean
public Step parallelImportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<InputOrder> reader,
        ItemProcessor<InputOrder, OrderSummary> processor,
        ItemWriter<OrderSummary> writer,
        TaskExecutor taskExecutor) {

    return new StepBuilder("parallelImportStep", jobRepository)
            .<InputOrder, OrderSummary>chunk(250, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .taskExecutor(taskExecutor)
            .build();
}
~~~

Mã minh họa giả định **InputOrder**, **OrderSummary**, các bean và import được định nghĩa cùng ứng dụng. Các component sử dụng đồng thời phải được xem xét **thread safety**; nhiều ItemReader có cursor/state mutable không mặc định an toàn khi chia sẻ giữa nhiều thread. Không tăng concurrency trước khi đánh giá reader/processor/writer và cơ chế checkpoint.

Nếu có tám chunk cùng hoạt động và interval 1.000, lượng dữ liệu chờ xử lý có thể lớn hơn đáng kể so với một chunk, và DB có thể phải phục vụ nhiều transaction đồng thời.

### 8.2. Local và remote partitioning

Trong **local partitioning**, manager chia dữ liệu và giao StepExecution của partition cho các worker thread trong cùng JVM. Trong **remote partitioning**, worker có thể chạy trong các JVM khác nhau. Cả hai đều có các chunk/transaction của worker step:

- Mỗi worker có input/ExecutionContext riêng, cần phạm vi dữ liệu không chồng lấn.
- Commit interval được dùng trong worker step.
- Số transaction đồng thời phụ thuộc concurrency tổng, không chỉ interval.
- Các worker vẫn cạnh tranh CPU, database, I/O và connection pool dùng chung trên hệ thống.
- Retry/restart và idempotency cần được kiểm tra theo từng worker StepExecution.

Trong **remote chunking**, manager đọc và tạo chunk để gửi sang worker. Interval còn ảnh hưởng đến kích thước payload, tần suất trao đổi message và hành vi ack/retry theo giao thức điều phối. Không giả định rằng một transaction DB tự bao trùm được các JVM và broker.

### 8.3. Cẩn trọng với tổng connection và bộ nhớ

Giả sử bốn worker JVM, mỗi JVM có tối đa hai chunk hoạt động đồng thời. Nếu mỗi item đang chờ ghi có dữ liệu thô trung bình 2 KiB và interval 1.000:

\[
M \approx 4 \times 2 \times 1.000 \times 2\ \mathrm{KiB}
= 15{,}625\ \mathrm{MiB}
\]

Đây chỉ là lượng dữ liệu thô xấp xỉ, chưa tính object overhead và buffer khác. Trong thực tế cũng cần tính **tổng connection pool** của manager và mọi worker, không chỉ cấu hình pool của một instance.

Khi benchmark, thay **một biến tại một thời điểm**. Ví dụ: cố định số worker rồi thử interval; sau đó giữ interval ở vùng tốt và kiểm tra số worker. Thay đồng thời cả hai làm khó xác định nguyên nhân thay đổi throughput.

## 9. Đo metric nào để tối ưu?

Throughput cần được định nghĩa rõ. Với job có dữ liệu lọc/skip, read throughput và write throughput không giống nhau.

\[
\mathrm{WriteThroughput}
= \frac{\mathrm{writeCount}}
{\mathrm{elapsedSeconds}}
\]

Cũng có thể dùng readCount để đo tốc độ quét input. Đừng so sánh hai lần chạy có khác dataset hoặc tỷ lệ filter/skip mà không giải thích khác biệt.

**StepExecution** lưu nhiều thống kê hữu ích:

| Metric | Ý nghĩa khi tuning |
| --- | --- |
| **readCount** | Số item đọc được ghi nhận |
| **writeCount** | Số item được ghi nhận đã ghi |
| **commitCount** | Số lần commit ở mức thống kê step |
| **rollbackCount** | Tín hiệu các lần rollback trong quá trình chạy |
| **filterCount** | Item bị processor loại khỏi đầu ra |
| **readSkipCount** | Item lỗi trong đọc và được skip |
| **processSkipCount** | Item lỗi trong xử lý và được skip |
| **writeSkipCount** | Item lỗi ghi và được skip |
| **startTime/endTime** | Mốc thời gian chạy step nếu có |

**commitCount không phải tổng mọi transaction tại database**. Nó là thống kê của step, có thể khác số transaction metadata, transaction của ứng dụng khác và các trường hợp rollback/retry.

Cần bổ sung phép đo bên ngoài StepExecution:

- p50/p95/p99 **chunk duration** và transaction duration.
- CPU utilization, heap, allocation rate, GC pause.
- DB active connections, lock wait, deadlock, query duration, write latency và transaction log I/O.
- Thread pool active/queue; worker idle time; broker lag nếu phân tán.
- Số retry, exception theo loại, thời gian phục hồi sau lỗi.
- Số business key duy nhất ở đích và số item thiếu/trùng sau restart.

### Ví dụ tổng hợp metric của một step

~~~java
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class StepRateListener implements StepExecutionListener {

    private long startedAtNanos;

    @Override
    public void beforeStep(StepExecution stepExecution) {
        startedAtNanos = System.nanoTime();
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        double seconds =
                (System.nanoTime() - startedAtNanos) / 1_000_000_000.0;

        double writeRate = seconds > 0
                ? stepExecution.getWriteCount() / seconds
                : 0.0;

        System.out.printf(
                "step=%s read=%d write=%d commit=%d rollback=%d "
                + "seconds=%.2f writePerSecond=%.1f%n",
                stepExecution.getStepName(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getCommitCount(),
                stepExecution.getRollbackCount(),
                seconds,
                writeRate);

        return stepExecution.getExitStatus();
    }
}
~~~

Listener phải được đăng ký với step mới được gọi. Ví dụ trên chỉ phù hợp khi instance listener không bị chia sẻ giữa nhiều StepExecution đồng thời, vì **startedAtNanos** là biến mutable. Với partitioning hoặc concurrent execution, dùng listener/đối tượng đo riêng cho từng step, hoặc công cụ metric hỗ trợ concurrency và gắn StepExecution ID. Trong production nên dùng logging/metrics có cấu trúc thay System.out.

## 10. Quy trình benchmark có thể lặp lại

### Bước 1: Lấy baseline

Chạy job trên dữ liệu đại diện, ghi tổng số item, tỷ lệ lỗi, throughput, thời gian step, p95 chunk duration, mức sử dụng heap và kết nối DB. Đo read/process/write để xác định nút thắt thực sự. Nếu API ngoài đang bị rate limit, chỉ tăng interval sẽ khó có ích.

### Bước 2: Cố định các biến khác

Giữ nguyên code, dữ liệu, worker count, pool size, database/index, JVM, retry policy và môi trường. Tách dữ liệu thí nghiệm khỏi nghiệp vụ thật; nếu writer có side effect, tạo cách khôi phục trạng thái giữa các lần đo.

### Bước 3: Thử các giá trị interval

Ví dụ thử **50 → 100 → 250 → 500 → 1.000 → 2.000** và lặp đủ lần để phát hiện dao động do cache, JIT hoặc tải DB. Đây chỉ là **dải tham khảo**, không phải cấu hình khuyến nghị cho mọi ứng dụng.

### Bước 4: So sánh cả throughput và rủi ro

Bảng dưới đây hoàn toàn **giả định**, dùng để học cách đọc kết quả benchmark:

| Interval | Write throughput | p95 thời gian chunk | Rollback / 100.000 item | Peak heap |
| ---: | ---: | ---: | ---: | ---: |
| 50 | 4.900 item/s | 85 ms | 1 | 1,0 GiB |
| 100 | 7.400 item/s | 140 ms | 1 | 1,1 GiB |
| 250 | 9.200 item/s | 350 ms | 2 | 1,3 GiB |
| 500 | 9.600 item/s | 850 ms | 5 | 1,7 GiB |
| 1.000 | 9.550 item/s | 2.100 ms | 11 | 2,5 GiB |
| 2.000 | 8.400 item/s | 5.200 ms | 23 | 3,8 GiB |

Trong bảng, interval 500 chỉ cải thiện khoảng 4,3% throughput so với 250, nhưng có p95 chunk duration cao hơn đáng kể. Interval 1.000 gần như không thêm tốc độ, trong khi heap và rollback tăng. **250 và 500** là hai ứng viên để kiểm tra tiếp về SLA và sự cố; chưa thể tuyên bố giá trị nào tốt nhất chỉ từ bảng này.

### Bước 5: Thử nghiệm lỗi/restart

Chủ động dừng worker giữa chunk, tạo lỗi DB tạm thời, inject dữ liệu sai để kiểm tra skip/fail, rồi restart. Đối chiếu **business key**, không chỉ tổng số dòng, nhằm nhận diện trường hợp vừa trùng vừa thiếu dữ liệu.

Thời gian hoàn thành **sau một sự cố** là metric quan trọng bên cạnh thời gian hoàn thành khi không lỗi.

### Bước 6: Chọn vùng gần điểm bão hòa

Chọn interval đạt throughput đủ cao nhưng còn ngân sách cho heap, transaction duration, DB connection và rollback. Lưu lại tham số, dataset, kết quả, phiên bản code, môi trường và điều kiện benchmark để người vận hành tái kiểm chứng.

## 11. Bài toán thực tế: xử lý sáu triệu giao dịch cuối ngày

Một công ty cần tổng hợp **6.000.000 giao dịch** trong cửa sổ **10 phút** sau khi dữ liệu ngày được chốt. Mức write throughput tối thiểu theo phép chia lý tưởng:

\[
\frac{6.000.000}{10 \times 60}
= 10.000\ \text{item/s}
\]

Con số này chưa tính thời gian khởi tạo, kiểm tra và dự phòng retry, nên thực tế cần throughput cao hơn mục tiêu tối thiểu.

**Giai đoạn A — Đo trạng thái ban đầu.** Một JVM, một step, interval 50 cho 4.000 item/s. CPU chỉ 30% nhưng DB thực hiện nhiều transaction nhỏ. Tăng interval 250 đạt 7.000 item/s; interval 1.000 đạt 7.300 item/s nhưng thời gian transaction tăng đáng kể.

**Giai đoạn B — Tối ưu writer.** Thay cách ghi từng bản ghi bằng writer hỗ trợ JDBC batch và tối ưu index. Với interval 250, throughput đạt 8.000 item/s; CPU và DB còn dung lượng.

**Giai đoạn C — Mở rộng có kiểm soát.** Dùng local partitioning theo các khoảng ID không trùng, với hai worker và interval 250. Throughput đạt 11.200 item/s. Tăng lên bốn worker làm lock wait tăng, throughput giảm còn 10.500 item/s.

**Giai đoạn D — Kiểm tra độ đúng.** Dừng một worker giữa chunk, restart và đối soát khóa giao dịch ở đích. Writer dùng khóa nghiệp vụ duy nhất/idempotent nên không tạo bản ghi trùng sau retry.

Tất cả số đo ở tình huống này là **giả định nhằm minh họa cách ra quyết định**, không phải benchmark của Spring Batch. Phương án hai worker với interval 250 đáp ứng SLA theo số liệu giả định, trong khi tăng thêm worker hoặc interval không mang lại lợi ích tương xứng.

## 12. Các sai lầm thường gặp

| Nhận định | Điều cần hiểu |
| --- | --- |
| “Interval càng lớn thì job luôn càng nhanh.” | Overhead giảm tới một mức, sau đó tài nguyên, lock, GC và rollback có thể làm chậm. |
| “chunk(500) luôn ghi đúng 500 item.” | Processor có thể filter, skip và chunk cuối có thể ngắn hơn. |
| “Page size 100 nghĩa là commit mỗi 100 item.” | Page size thuộc reader, không trực tiếp đặt transaction boundary. |
| “Interval tăng sẽ tự tăng số thread.” | TaskExecutor và partition topology mới quyết định concurrency. |
| “CommitCount là số commit của toàn hệ thống DB.” | Đây là thống kê StepExecution, không phải mọi transaction của toàn hệ thống. |
| “Rollback DB sẽ hoàn tác email hoặc request HTTP.” | Side effect ngoài transaction cần cơ chế idempotency/điều phối riêng. |
| “Tăng chunk để sửa API ngoài bị rate limit.” | Cần xử lý giới hạn của API và mô hình gọi, không chỉ chunk size. |
| “Chỉ nhìn write throughput là đủ.” | Phải xem retry, restart, correctness, heap, lock, transaction duration và SLA. |
| “Hai worker mỗi worker chunk 500 là một transaction 1.000 item.” | Mỗi worker có transaction riêng; chúng không tự gộp thành một transaction. |

## 13. Checklist lựa chọn commit interval

- [ ] Có baseline trên workload và dữ liệu đại diện.
- [ ] Biết bottleneck chính thuộc read, process, write, commit, CPU hay dịch vụ ngoài.
- [ ] Phân biệt commit interval với fetch/page/batch size và concurrency.
- [ ] Đã thử nhiều interval trong điều kiện so sánh nhất quán.
- [ ] Đã đo throughput, p95 chunk duration, heap/GC, DB lock và connection.
- [ ] Đã xem rollbackCount, retry và skip, không chỉ commitCount.
- [ ] Đã đánh giá thread safety nếu kết hợp với multi-threaded step.
- [ ] Đã kiểm soát tổng tải từ nhiều partition/worker, kể cả trên các JVM khác nhau.
- [ ] Đã kiểm thử lỗi giữa chunk, restart và đối soát business key.
- [ ] Có kết quả benchmark và lý do lựa chọn giá trị interval để vận hành lâu dài.

## 14. Câu hỏi tự kiểm tra

**1. Tại sao interval 1 thường chậm khi xử lý một triệu item?**

Vì phần overhead transaction, callback và checkpoint được lặp gần như mỗi item. Tăng interval thường giảm overhead cố định trên mỗi item, cho tới khi bottleneck khác chi phối.

**2. Một reader dùng page size 200 và step có interval 500. Sau khi lấy 200 dòng đã commit chưa?**

Không thể kết luận như vậy. Reader page size quyết định lượng dữ liệu một lần truy vấn, còn interval là ranh giới chunk/commit của step.

**3. Với interval 100, processor lọc 30% item, writer có luôn nhận 100 item không?**

Không. Chunk có thể có khoảng 100 item đầu vào nhưng chỉ khoảng 70 item đầu ra khi tỷ lệ lọc là 30%, chưa tính skip hay chunk cuối.

**4. Vì sao tăng interval 250 lên 1.000 đôi khi không cải thiện throughput mà còn tăng rollback?**

Vì overhead commit đã nhỏ so với chi phí mỗi item, trong khi chunk lớn hơn tăng thời gian transaction, contention, bộ nhớ và phần việc bị ảnh hưởng khi lỗi.

**5. Một job chạy tám partition, mỗi partition interval 500. Tất cả có chung một transaction 4.000 item không?**

Không. Các worker StepExecution có chunk và transaction độc lập. Chúng có thể cùng hoạt động nhưng không tự biến thành transaction chung.

**6. Vì sao phép đo sau khi restart quan trọng?**

Một interval lớn có thể làm việc chưa commit phải xử lý lại nhiều hơn; side effect ngoài DB có thể đã xảy ra. Việc tối ưu chỉ đạt yêu cầu nếu kết quả vẫn đúng sau retry/restart và thời gian phục hồi chấp nhận được.

---

**Ghi nhớ:** Commit interval là kích thước công việc mục tiêu của mỗi chunk trong Spring Batch. **Nhỏ quá** thường gây nhiều overhead commit; **lớn quá** dễ gây áp lực transaction, heap và rollback. Hãy chọn interval bằng phép đo thực tế, đồng thời kiểm soát concurrency, thread safety, tính đúng của writer và khả năng restart khi mở rộng workload dữ liệu lớn.
