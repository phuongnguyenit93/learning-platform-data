# Nguyên tắc chọn giải pháp đơn giản trước khi scaling Spring Batch

## Mục tiêu bài học

Một job Spring Batch chạy chậm chưa đủ để kết luận rằng hệ thống cần thêm thread, message broker hay nhiều worker JVM. Nút thắt có thể là một câu SQL thiếu index, writer ghi từng bản ghi, kích thước chunk không phù hợp hoặc một API ngoài bị giới hạn tốc độ. Nếu chuyển sang kiến trúc phân tán trước khi đo nguyên nhân, nhóm phát triển sẽ phải vận hành thêm nhiều thành phần nhưng tốc độ hoàn thành có thể không cải thiện.

Bài thuộc chương **Tổng quan scaling** của module **SPRING_BATCH_SCALING_OPERATIONS**. Nguyên tắc trung tâm là **chọn kiến trúc ít phức tạp nhất đã được kiểm chứng là đáp ứng yêu cầu**, rồi chỉ tăng mức song song khi có bằng chứng về lợi ích. Điều đó áp dụng cho multi-threaded step, parallel steps, local partitioning, remote chunking và remote partitioning, đồng thời bao gồm thread safety, retry/restart và năng lực vận hành.

Học xong bài này, bạn có thể:

- Giải thích vì sao cần đo và tối ưu bước xử lý tuần tự trước khi mở rộng bằng concurrency.
- Phân biệt giải pháp **đơn giản về cấu hình** với giải pháp **đơn giản để xử lý lỗi, restart và vận hành**.
- Xây dựng lộ trình tăng cấp kiến trúc từ baseline đến xử lý phân tán dựa trên bottleneck thực tế.
- Đặt tiêu chí dừng: khi nào throughput đã đủ, khi nào tăng worker gây phản tác dụng.
- Phác thảo các phép thử về thread safety, tính đúng dữ liệu, idempotency và khôi phục trước khi mở rộng.
- Giải thích lựa chọn kiến trúc bằng số đo SLA, ngân sách tài nguyên và chi phí bảo trì.

## 1. “Đơn giản trước” nghĩa là gì?

“Đơn giản trước” là nguyên tắc thiết kế và kiểm chứng, không phải yêu cầu rằng mọi job đều phải chạy một luồng mãi mãi.

Một giải pháp đơn giản **phù hợp với bối cảnh** có những đặc điểm:

1. **Đáp ứng mục tiêu đo được:** hoàn thành dữ liệu đúng hạn, đúng kết quả và trong giới hạn tài nguyên.
2. **Ít cơ chế cần điều phối:** số thread, partition, JVM, queue và trạng thái phân tán vừa đủ.
3. **Ranh giới dữ liệu rõ ràng:** biết chính xác phần dữ liệu nào được đọc, xử lý và ghi.
4. **Lỗi dễ phục hồi:** trạng thái checkpoint, retry và restart có thể kiểm tra được.
5. **Dễ vận hành:** log, metric, cảnh báo, rollback cấu hình và quy trình xử lý sự cố nằm trong năng lực nhóm.

Ví dụ, nếu một step tuần tự xử lý 5 triệu item trong 6 phút, trong khi SLA là 15 phút, thì thêm tám worker chưa chắc đem lại giá trị. Hệ thống có thể phải trả thêm chi phí triển khai, giám sát và điều tra dữ liệu lỗi để đổi lấy một phần thời gian không cần thiết.

Ngược lại, nếu SLA chỉ 2 phút, một JVM đã dùng gần hết CPU và dữ liệu có thể chia theo khoảng ID độc lập, partitioning có thể là **giải pháp đơn giản nhất đáp ứng yêu cầu**, dù cấu hình nhiều hơn step tuần tự.

### Đơn giản ở nhiều chiều

| Chiều đánh giá | Biểu hiện đơn giản | Chi phí thường phát sinh khi tăng mức song song |
| --- | --- | --- |
| **Cấu hình** | Ít bean, executor, channel và handler | Thêm TaskExecutor, Partitioner, broker, worker |
| **Dữ liệu** | Một luồng xử lý với checkpoint rõ | Chia vùng dữ liệu, đối soát partition, tránh ghi trùng |
| **Trạng thái** | Ít StepExecution và trạng thái đồng thời | Nhiều checkpoint, worker đang chạy/lỗi/chờ |
| **Tài nguyên** | Dễ đặt giới hạn CPU, heap và connection | Nhiều transaction, contention, pool trên nhiều JVM |
| **Khôi phục** | Một điểm dừng và luồng restart rõ | Timeout, phần việc chạy lại, message đến trễ |
| **Vận hành** | Log và metric tương đối tập trung | Correlation ID, hàng đợi, nhiều container, alert |

Một thay đổi ít dòng code chưa chắc là một thay đổi đơn giản đối với hệ thống. Chẳng hạn thêm **.taskExecutor(...)** có thể rất ngắn, nhưng nếu ItemReader có con trỏ mutable, chi phí bảo đảm không bỏ sót dữ liệu khi restart có thể lớn hơn việc thiết kế local partitioning rõ ràng ngay từ đầu.

## 2. Đừng bắt đầu bằng số worker: bắt đầu bằng yêu cầu nghiệp vụ

Trước khi chọn mô hình, cần biết **“đủ nhanh”** nghĩa là gì.

Với một batch xử lý \(N\) item trong thời hạn \(D\) giây, tốc độ đầu vào trung bình tối thiểu là:

\[
R_{\mathrm{required}}=\frac{N}{D}
\]

Ví dụ cần xử lý **9.000.000 item** trong **30 phút**:

\[
R_{\mathrm{required}}=\frac{9.000.000}{30\times60}
=5.000\ \mathrm{item/s}
\]

Con số 5.000 item/s chỉ là mức lý tưởng nếu toàn bộ cửa sổ dùng cho xử lý. Thực tế còn khởi tạo job, kết nối, các step phụ thuộc, đối soát, lưu kết quả và dự phòng lỗi. Do đó cần xác định thêm:

- **SLA hoàn thành:** giờ chốt đầu vào, giờ kết thúc bắt buộc, cách tính ngày/tenant.
- **Dữ liệu hợp lệ:** số input, tỷ lệ filter/skip và số output dự kiến.
- **Tính nhất quán:** có cần snapshot không, có yêu cầu xử lý đúng thứ tự không?
- **Độ tin cậy:** số lần retry cho phép, thời gian restart tối đa, chính sách xử lý record lỗi.
- **Ngân sách:** CPU, RAM, connection DB, quota API, chi phí message broker và số người trực vận hành.
- **Độ tăng trưởng:** dữ liệu hiện tại và mức dự báo có thể kiểm chứng cho những kỳ sau.

Nếu chỉ có câu “job phải nhanh hơn”, việc tăng concurrency không có tiêu chí thành công hay tiêu chí dừng.

### Đánh giá theo kết quả đầu ra

Một job có processor lọc 30% đầu vào có **read throughput** và **write throughput** khác nhau. Hãy định nghĩa rõ chỉ số:

\[
R_{\mathrm{read}}=\frac{\mathrm{readCount}}{T_{\mathrm{step}}},
\qquad
R_{\mathrm{write}}=\frac{\mathrm{writeCount}}{T_{\mathrm{step}}}
\]

Khi so sánh các phương án, phải dùng cùng tập dữ liệu và quy tắc filter/skip. Throughput tăng nhưng số bản ghi ghi thiếu, trùng hoặc bị skip ngoài dự kiến không được xem là thành công.

## 3. Bước đầu tiên: lấy baseline đo được

Một baseline hữu ích có thể là một **chunk-oriented step tuần tự** với nguồn dữ liệu và writer hiện có, chạy trên tập dữ liệu đủ đại diện.

~~~mermaid
flowchart LR
    A["Nguồn dữ liệu"] --> B["Reader"]
    B --> C["Processor"]
    C --> D["Writer"]
    D --> E["Commit chunk"]
    E -. "Tiếp tục" .-> B
~~~

Cần ghi tối thiểu:

| Nhóm | Dữ liệu cần thu thập | Câu hỏi được trả lời |
| --- | --- | --- |
| **Kết quả batch** | readCount, writeCount, filterCount, skipCount | Bao nhiêu item đã thực sự xử lý đúng? |
| **Thời gian** | Job/Step elapsed, chunk duration | Thời gian tiêu vào đâu? |
| **Reader** | Query latency, rows scanned, fetch/page time | Đọc có phải bottleneck? |
| **Processor** | CPU, allocation, thời gian xử lý/item | Có thiếu khả năng tính toán không? |
| **Writer** | Batch write latency, commit duration | Ghi chậm vì lệnh SQL hay transaction? |
| **Database** | Active connections, lock wait, I/O, log pressure | DB còn chịu được tải tăng không? |
| **Ứng dụng** | CPU, heap, GC pause, active threads | Một JVM đã tới giới hạn chưa? |
| **Độ tin cậy** | rollbackCount, retry, lỗi, thời gian restart | Cấu hình hiện tại có đáng tin cậy không? |

Không cần triển khai toàn bộ hệ thống tracing phân tán để có baseline đầu tiên. StepExecution, log có thời gian, JDBC metrics và số liệu giám sát DB thường đã cung cấp nhiều thông tin có ích.

### Đọc số liệu đúng

- **CPU thấp và DB lock wait cao:** tăng thread có thể tăng lock, cần xem SQL và transaction.
- **CPU một JVM gần giới hạn, DB còn nhàn:** có lý do kiểm tra song song hóa hoặc thêm JVM.
- **Reader chiếm phần lớn thời gian:** thử query/index/paging trước khi tăng worker xử lý.
- **Writer gửi từng record:** kiểm tra batch writer và commit interval.
- **GC tăng khi tăng chunk:** chunk có thể quá lớn hoặc object allocation chưa được tối ưu.
- **Job nhanh lúc ít dữ liệu nhưng chậm mạnh khi dữ liệu lớn:** cần xem query plan, phân phối dữ liệu, tài nguyên I/O, cache và độ tăng của transaction.

**Baseline phải đúng dữ liệu.** Một lượt chạy báo COMPLETED nhưng ghi trùng hoặc bỏ sót item không thể dùng làm mốc tốc độ đáng tin cậy.

## 4. Ví dụ step tuần tự làm mốc kiểm thử

Cấu hình Java dưới đây minh họa một step Spring Batch 5.x với commit interval cố định. Đây là điểm bắt đầu dễ quan sát trước khi chuyển sang multi-threaded step hoặc partitioning.

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
public class ImportJobSteps {

    public record SourceOrder(long id, long amountCents) {}
    public record TargetOrder(long orderId, long amountCents) {}

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<SourceOrder> orderReader,
            ItemProcessor<SourceOrder, TargetOrder> processor,
            ItemWriter<TargetOrder> orderWriter) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<SourceOrder, TargetOrder>chunk(250, transactionManager)
                .reader(orderReader)
                .processor(processor)
                .writer(orderWriter)
                .build();
    }
}
~~~

Ví dụ giả định ứng dụng đã cung cấp các bean reader/processor/writer tương ứng và quản lý JobRepository/transactionManager. Mã trên mô tả cấu trúc step, **không phải ứng dụng hoàn chỉnh**. Giá trị chunk **250** là một mốc thử, không phải cấu hình mặc định tối ưu.

Trước khi tăng concurrency, kiểm tra reader có truy vấn nguồn hiệu quả, writer có batch phù hợp, và checkpoint hoạt động đúng sau một lần dừng giữa chừng. Bước tối ưu này thường ít tác động kiến trúc hơn việc thêm worker.

## 5. Tối ưu nội bộ trước khi mở rộng song song

Khi baseline còn nghẽn một thao tác cụ thể, hãy sửa chính thao tác đó.

### 5.1. Tối ưu reader

Một query chưa có index phù hợp có thể buộc DB đọc lượng dữ liệu lớn hơn nhiều so với số record cần xử lý. Ví dụ:

~~~sql
SELECT id, customer_id, amount_cents
FROM orders
WHERE business_date = :businessDate
  AND id > :lastSeenId
ORDER BY id
LIMIT :pageSize;
~~~

Đây là truy vấn minh họa keyset pagination; cú pháp và cách thực thi khác nhau giữa DB. Cần kiểm tra **EXPLAIN/EXPLAIN ANALYZE**, index, số hàng quét và thời gian thực tế. Với điều kiện lọc theo business_date và sắp xếp id, có thể đánh giá một index ghép phù hợp, nhưng không có một index đúng cho mọi workload.

Các cải thiện có thể thử:

- Chỉ lấy cột thực sự cần và tránh mapping object quá nặng.
- Xác định rõ thứ tự đọc ổn định, đặc biệt khi restart.
- So sánh cursor và paging reader dựa trên driver/DB đang dùng.
- Điều chỉnh fetch size/page size độc lập với chunk size.
- Tránh gọi API hoặc truy vấn phụ riêng cho mỗi item nếu có thể batch.
- Khi dữ liệu nguồn thay đổi trong lúc job chạy, xác định snapshot/high-watermark.

Nếu reader đang thực hiện full table scan tốn 30 giây mỗi lần lấy một trang, tạo tám reader có thể chỉ tăng áp lực DB lên nhiều lần.

### 5.2. Tối ưu writer

Với dữ liệu ghi vào DB, writer gửi SQL theo batch có thể giảm overhead round trip so với gửi một lệnh riêng cho từng item. Ví dụ Spring Batch có **JdbcBatchItemWriter**; hiệu quả còn phụ thuộc driver, DB, SQL và index.

~~~java
@Bean
public JdbcBatchItemWriter<TargetOrder> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<TargetOrder>()
            .dataSource(dataSource)
            .sql("""
                 INSERT INTO order_summary (order_id, amount_cents)
                 VALUES (?, ?)
                 ON CONFLICT (order_id)
                 DO UPDATE SET amount_cents = EXCLUDED.amount_cents
                 """)
            .itemPreparedStatementSetter((item, ps) -> {
                ps.setLong(1, item.orderId());
                ps.setLong(2, item.amountCents());
            })
            .build();
}
~~~

Ví dụ dùng cú pháp **PostgreSQL** và giả định record TargetOrder ở ví dụ trước, các import và bean hạ tầng đã được khai báo. Bảng đích phải có ràng buộc UNIQUE/PRIMARY KEY trên order_id để dùng ON CONFLICT. Upsert như trên chỉ phù hợp khi nghiệp vụ cho phép ghi lại giá trị theo cùng khóa; với cộng dồn hoặc side effect ngoài DB phải thiết kế idempotency riêng.

### 5.3. Thử commit interval có kiểm soát

**Commit interval** xác định số item đầu vào mục tiêu trong một chunk. Chọn quá nhỏ tạo nhiều transaction và checkpoint; quá lớn có thể giữ bộ nhớ, lock và transaction lâu hơn, làm tăng lượng việc phải làm lại khi lỗi.

| Thử nghiệm | Điều nên đo | Dấu hiệu cần chú ý |
| --- | --- | --- |
| Chunk 50 | Throughput, commitCount, latency | Overhead commit có chiếm ưu thế? |
| Chunk 100 | Write latency, DB I/O | Batch có hiệu quả hơn không? |
| Chunk 250 | Throughput, heap, rollback | Mức cân bằng ra sao? |
| Chunk 500 | Transaction duration, lock wait | Giao dịch có kéo dài quá mức? |
| Chunk 1.000 | Peak heap, retry cost | Tăng chunk còn cải thiện tốc độ không? |

Các con số là **mốc minh họa**, không phải giá trị chuẩn cho mọi hệ thống. Page size, fetch size và JDBC batch size là những thông số khác; đừng coi chúng đồng nghĩa với commit interval.

### 5.4. Đặt điểm dừng

Nếu sau khi tối ưu SQL, batch writer và chunk size, job đã hoàn thành đúng hạn với dự phòng tải và có thể restart an toàn, đó có thể là **điểm dừng hợp lý**. Không cần thêm hệ thống messaging chỉ vì nó có thể chạy song song.

## 6. Lộ trình tăng mức song song theo bằng chứng

Một lộ trình thường có các lựa chọn sau; đây là **các nhánh để chọn**, không phải một chuỗi bắt buộc phải triển khai đủ từng mức.

~~~mermaid
flowchart TD
    A["Đo baseline tuần tự"] --> B{"Đạt SLA và yêu cầu phục hồi?"}
    B -->|Có| C["Giữ kiến trúc hiện tại<br/>theo dõi tăng trưởng"]
    B -->|Chưa| D["Tối ưu reader, writer,<br/>chunk, SQL và DB"]
    D --> E{"Đã đạt yêu cầu?"}
    E -->|Có| C
    E -->|Chưa| F{"Công việc độc lập theo cách nào?"}
    F -->|"Nhiều flow độc lập"| G["Parallel steps"]
    F -->|"Chunk độc lập, component thread-safe"| H["Multi-threaded step"]
    F -->|"Dữ liệu chia được theo key/range"| I["Local partitioning"]
    G --> J["Benchmark + lỗi/restart"]
    H --> J
    I --> J
    J --> K{"Một JVM là giới hạn thực tế?"}
    K -->|Không| L["Giữ mô hình local đáp ứng SLA"]
    K -->|Có| M{"Worker tự đọc dữ liệu được không?"}
    M -->|Có| N["Remote partitioning"]
    M -->|"Manager đọc đủ nhanh, payload phù hợp"| O["Remote chunking"]
    N --> P["Benchmark + fault injection + vận hành"]
    O --> P
~~~

Mỗi lần tăng mức song song nên trả lời được ba câu hỏi: **nút thắt trước đó là gì, thay đổi này giải quyết nút thắt ấy bằng cơ chế nào, và bằng chứng nào chứng minh kết quả tốt hơn**.

## 7. Parallel steps khi công việc vốn đã độc lập

Nếu job có các nhánh nghiệp vụ không phụ thuộc nhau, ví dụ tổng hợp doanh thu, tính chỉ số tồn kho và phân loại khách hàng, **parallel steps** thường dễ suy luận hơn việc chia một step thành nhiều partition.

~~~mermaid
flowchart TB
    J["Job bắt đầu"] --> S["Split"]
    S --> A["Flow A: tổng hợp bán hàng"]
    S --> B["Flow B: tổng hợp tồn kho"]
    A --> C["Tiếp tục khi các flow<br/>đạt điều kiện hoàn tất"]
    B --> C
    C --> D["Step xuất báo cáo"]
~~~

Nếu Flow A mất 9 phút và Flow B mất 3 phút, thời gian lý tưởng tới điểm join gần **9 phút**, thay vì 12 phút tuần tự, cộng overhead và tranh chấp hạ tầng. Chạy song song không tự làm Flow A nhanh hơn.

**Nên dùng khi** các flow có input/output độc lập và quy tắc join/restart rõ ràng. **Chưa phù hợp khi** Flow B dùng dữ liệu chưa hoàn thành từ Flow A, hoặc các flow cùng cập nhật một trạng thái không được đồng bộ.

Thêm parallel steps không cần phân tán qua nhiều JVM. Nếu một process đủ CPU/RAM, giữ một JVM giúp giảm số tiến trình phải triển khai và quan sát.

## 8. Multi-threaded step khi chunk có thể chạy đồng thời

Một **multi-threaded step** gắn TaskExecutor vào step để nhiều chunk được xử lý đồng thời trong **một JVM**. Đây là cách mở rộng tương đối gần cấu trúc step tuần tự, nhưng chỉ đơn giản về mặt triển khai nếu các component dùng chung an toàn luồng.

~~~java
@Bean
public TaskExecutor importExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("import-");
    executor.initialize();
    return executor;
}

@Bean
public Step concurrentImportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<SourceOrder> reader,
        ItemProcessor<SourceOrder, TargetOrder> processor,
        ItemWriter<TargetOrder> writer,
        @Qualifier("importExecutor") TaskExecutor executor) {

    return new StepBuilder("concurrentImportStep", jobRepository)
            .<SourceOrder, TargetOrder>chunk(250, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .taskExecutor(executor)
            .build();
}
~~~

Các đoạn code giả định đã khai báo những import, DTO và bean được tham chiếu; API minh họa Spring Batch 5.x. Chỉ dùng cấu hình này sau khi kiểm chứng reader, processor, writer và cơ chế restart. Tên bean hay sự hiện diện của TaskExecutor **không** bảo đảm thread safety.

### Cần xác minh trước khi tăng thread

- **Reader có state dùng chung?** Cursor, vị trí file hoặc biến đếm mutable có thể gây trùng/mất item.
- **Processor có state?** Cache và buffer mutable cần thread safety hoặc scope phù hợp.
- **Writer có state?** Buffer, session, kết nối và batch writer cần kiểm tra khi dùng đồng thời.
- **Thứ tự quan trọng không?** Chunk có thể hoàn tất không theo thứ tự đọc.
- **Checkpoint an toàn không?** Đồng bộ hóa read không tự bảo đảm restart chính xác khi các chunk commit lệch thứ tự.
- **DB chịu được không?** Nhiều chunk đồng thời tạo thêm giao dịch, connection và lock.

Nếu cấu hình 2 thread đã đạt SLA, thêm lên 16 chỉ làm tăng contention, nên chọn mức nhỏ hơn. Đo throughput, rollback và data reconciliation sau mỗi lần thay.

## 9. Local partitioning khi dữ liệu có ranh giới rõ ràng

Khi ItemReader khó chia sẻ an toàn nhưng dữ liệu chia được theo ID, ngày, tenant hoặc file, **local partitioning** có thể dễ kiểm soát hơn multi-threaded step.

**Partitioner** tạo ánh xạ tên partition → ExecutionContext; mỗi worker StepExecution đọc phạm vi riêng qua reader theo StepScope.

~~~mermaid
flowchart TB
    M["Manager Step"] --> P["Partitioner"]
    P --> A["partition-0: ID [1, 100001)"]
    P --> B["partition-1: ID [100001, 200001)"]
    P --> C["partition-2: ID [200001, 300001)"]
    A --> W1["Worker Step 0"]
    B --> W2["Worker Step 1"]
    C --> W3["Worker Step 2"]
    W1 --> DB[("Nguồn/đích chung")]
    W2 --> DB
    W3 --> DB
~~~

Ví dụ input logic:

~~~yaml
partitionName: partition-1
minIdInclusive: 100001
maxIdExclusive: 200001
~~~

Ví dụ trên mô tả **nội dung logic**, không phải tệp cấu hình Spring Boot. Partitioner thực tế tạo các giá trị bằng ExecutionContext, ví dụ:

~~~java
ExecutionContext input = new ExecutionContext();
input.putLong("minIdInclusive", 100_001L);
input.putLong("maxIdExclusive", 200_001L);
~~~

Worker nhận bằng biểu thức dạng:

~~~java
@StepScope
@Bean
public ItemReader<SourceOrder> partitionReader(
        @Value("#{stepExecutionContext['minIdInclusive']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxId,
        DataSource dataSource) {

    if (minId == null || maxId == null || minId >= maxId) {
        throw new IllegalArgumentException("Invalid partition range");
    }

    return new JdbcCursorItemReaderBuilder<SourceOrder>()
            .name("partitionReader")
            .dataSource(dataSource)
            .sql("""
                 SELECT id, amount_cents
                 FROM orders
                 WHERE id >= ? AND id < ?
                 ORDER BY id
                 """)
            .preparedStatementSetter(ps -> {
                ps.setLong(1, minId);
                ps.setLong(2, maxId);
            })
            .rowMapper((rs, rowNum) ->
                    new SourceOrder(
                            rs.getLong("id"),
                            rs.getLong("amount_cents")))
            .saveState(true)
            .build();
}
~~~

Đây là mã minh họa cấu hình theo Spring Batch 5.x, với các import/DTO/bean hạ tầng cần bổ sung khi tích hợp. **@StepScope** cho phép tạo reader gắn với StepExecution của partition, nhưng không thay thế kiểm tra tính nhất quán đầu vào.

Local partitioning yêu cầu thêm Partitioner, worker step và metadata, song có các lợi ích:

- Ranh giới sở hữu dữ liệu tường minh, dễ đối soát.
- Mỗi worker step có ExecutionContext và checkpoint riêng.
- Giảm nhu cầu chia sẻ một reader mutable giữa nhiều thread.
- Có thể chia **nhiều partition hơn số thread** để giảm mất cân bằng tải.

**Đổi lại**, phải giữ tên/range partition ổn định qua restart và kiểm tra rằng nhiều reader đồng thời không làm DB nguồn chậm đi. Nếu DB đã bão hòa, local partitioning không giải quyết được bottleneck.

## 10. Khi nào tăng cấp sang nhiều process?

Một JVM thường đủ cho các job vừa và lớn nếu CPU, RAM, I/O và DB còn dung lượng. Chỉ cân nhắc multi-process khi có bằng chứng rằng **ranh giới của một tiến trình/host** đang giới hạn mục tiêu hoặc cần cô lập/triển khai worker theo yêu cầu hạ tầng.

Hai mô hình Spring Batch thường gặp:

| Tiêu chí | Remote chunking | Remote partitioning |
| --- | --- | --- |
| **Ai đọc dữ liệu?** | Manager đọc, tạo chunk | Worker tự đọc phạm vi của mình |
| **Đơn vị gửi** | Item/chunk qua message | Yêu cầu/mô tả partition và trạng thái liên quan |
| **Phù hợp nhất** | Process/write nặng, reader trung tâm đủ nhanh | Dữ liệu chia theo range/key, nhiều reader được phép |
| **Nút thắt mới** | Manager, serialization, broker, kích thước message | Nguồn DB, JobRepository, chia partition, worker lifecycle |
| **Yêu cầu vận hành** | Queue, ack, retry, compatibility payload | Manager/worker, metadata, điều phối, restart partition |
| **Rủi ro dữ liệu** | Gửi lại chunk sau khi đã ghi | Partition trùng/thiếu, worker thực thi lại |

### Remote chunking

~~~mermaid
flowchart LR
    S[("Nguồn")] --> M["Manager JVM: read + chunk"]
    M --> Q[["Broker"]]
    Q --> W1["Worker JVM A: process/write"]
    Q --> W2["Worker JVM B: process/write"]
    W1 --> D[("Đích")]
    W2 --> D
    W1 -. "Phản hồi" .-> M
    W2 -. "Phản hồi" .-> M
~~~

Mô hình hợp lý khi manager đọc nhanh, item không quá lớn để serialize và phần xử lý/ghi mới là bottleneck. Nếu reader của manager chỉ đạt 5.000 item/s, thêm 10 worker có tổng năng lực 50.000 item/s không làm nguồn tự đọc nhanh hơn.

### Remote partitioning

~~~mermaid
flowchart TB
    M["Manager JVM: phân vùng"] --> Q[["Kênh điều phối"]]
    Q --> W1["Worker JVM A: range A"]
    Q --> W2["Worker JVM B: range B"]
    W1 --> D[("Nguồn và đích dữ liệu")]
    W2 --> D
    R[("JobRepository bền vững")] --- M
    R --- W1
    R --- W2
~~~

Mô hình hợp lý khi một JVM thiếu tài nguyên và nguồn hỗ trợ nhiều worker tự đọc theo phạm vi độc lập. Manager không cần chuyển toàn bộ item qua broker, nhưng nhiều worker có thể đẩy tổng tải DB nguồn/đích lên cao.

**Chi phí cần dự toán:** triển khai nhiều JVM/pod, network, broker/channels, serializer, cập nhật JobRepository, timeout, logging phân tán, retry/ack và quản lý cấu hình giữa các phiên bản.

Chọn multi-process khi lợi ích và nhu cầu cô lập/scale đủ rõ để bù chi phí này, không chỉ vì nó “mạnh” hơn single-process.

## 11. Một ma trận quyết định thực dụng

| Bằng chứng quan sát | Hướng xử lý trước | Khi nào cân nhắc mô hình cao hơn? |
| --- | --- | --- |
| Query nguồn chậm, rows scanned cao | Tối ưu SQL, index, kế hoạch đọc | Sau khi query hiệu quả và DB chịu được nhiều reader |
| Writer gửi từng item, commit quá thường | JDBC batch writer, chunk tuning | Khi đích còn dư và writer vẫn thiếu throughput |
| CPU một JVM cao, dữ liệu độc lập | Thử thread hoặc local partitioning | Khi host/JVM đã đạt giới hạn thật |
| Các flow nghiệp vụ độc lập | Parallel steps | Khi cần tách triển khai hoặc tài nguyên theo flow |
| Reader có con trỏ mutable khó chia sẻ | Local partition với reader riêng | Khi JVM không đủ CPU/RAM |
| Manager đọc nhanh, process/write nặng | Thử tối ưu worker; remote chunking nếu cần scale out | Khi broker và payload đáp ứng được |
| Dữ liệu có key/range ổn định, nguồn cho phép nhiều reader | Local partitioning trước | Remote partitioning khi resource local bị giới hạn |
| DB/API đích đã đạt quota/saturation | Tối ưu đích, backpressure, giới hạn concurrency | Khi đã mở rộng được năng lực tài nguyên đích |
| Chạy tuần tự đạt SLA với dự phòng | Giữ thiết kế hiện tại và quan sát | Khi khối lượng tăng/điều kiện thay đổi được đo |

**Không chọn bằng số dòng dữ liệu đơn lẻ.** Có job 100 triệu item nhỏ vẫn phù hợp một JVM nếu cửa sổ chạy đủ dài và I/O hiệu quả; cũng có job vài trăm nghìn item cần phân phối vì CPU cho mỗi item rất nặng hoặc hạn hoàn thành nghiêm ngặt.

## 12. Cách tính speedup và nhận biết điểm bão hòa

Với cùng dataset và nghiệp vụ, có thể dùng:

\[
\mathrm{Speedup}(p)=\frac{T_1}{T_p}
\]

Trong đó \(T_1\) là thời gian baseline, \(T_p\) là thời gian sau khi tăng lên \(p\) đơn vị xử lý. Khi các lần chạy xử lý cùng lượng công việc hợp lệ và cùng định nghĩa output, có thể tham khảo tỷ số throughput.

**Parallel efficiency**:

\[
E(p)=\frac{\mathrm{Speedup}(p)}{p}
\]

Efficiency là chỉ báo, không phải tiêu chí duy nhất. Ví dụ tăng từ 4 lên 8 worker làm job nhanh hơn 4% có thể không đáng chi phí nếu cả hai đều đạt SLA với dự phòng.

### Định luật Amdahl

Nếu tỷ lệ \(s\) công việc bắt buộc tuần tự, speedup lý tưởng bị giới hạn bởi:

\[
S(p)\leq\frac{1}{s+(1-s)/p}
\]

Ví dụ 15% thời gian vẫn tuần tự, dù dùng 8 worker:

\[
S(8)\leq\frac{1}{0{,}15+0{,}85/8}
\approx3{,}90
\]

Công thức chưa tính network, JobRepository, DB contention, retry và dữ liệu lệch tải; trên hệ thống thật tốc độ có thể thấp hơn. Nếu phần tuần tự là một reader duy nhất, remote chunking vẫn có thể bị giới hạn tại manager.

### Ví dụ benchmark giả định

| Mô hình | Thời gian job | Speedup so baseline | Mức phức tạp tăng thêm |
| --- | ---: | ---: | --- |
| Một step tuần tự | 60 phút | 1,00× | Baseline |
| Tối ưu query + JDBC batch (vẫn tuần tự) | 34 phút | 1,76× | Thấp |
| Local partition, 2 worker | 23 phút | 2,61× | Trung bình |
| Local partition, 4 worker | 19 phút | 3,16× | Trung bình |
| Local partition, 8 worker | 18,5 phút | 3,24× | Tăng contention |
| Remote partition, 8 worker | 18 phút | 3,33× | Cao |

Đây chỉ là số liệu minh họa. Nếu SLA là **25 phút**, hai worker local đã có thể đạt yêu cầu, nhưng cần kiểm tra ngân sách dự phòng khi lỗi và dữ liệu tăng. Nếu SLA là **20 phút**, bốn worker local có thể đủ; remote partitioning chỉ tiết kiệm thêm một phút so với bốn worker trong ví dụ và có chi phí vận hành cao hơn.

**Đừng chỉ tính speedup; hãy tính lợi ích còn lại so với yêu cầu thật.**

## 13. Thực nghiệm một biến mỗi lần

Để biết một thay đổi có giá trị, cần quy trình thử nghiệm có thể lặp lại:

1. **Chốt dataset và cách xác nhận output.** Cùng số business key, phân bố kích thước và tỷ lệ filter/skip.
2. **Đo baseline.** Ghi thời gian, throughput, CPU, DB, lock, heap/GC và số lần lỗi.
3. **Tối ưu đúng bottleneck.** Một thay đổi query/index hoặc writer một lần, đo lại.
4. **Chọn một mức concurrency nhỏ.** Thử 2 rồi 4 thread/worker nếu có bằng chứng cần tăng.
5. **Giữ những biến khác ổn định.** Không cùng lúc thay chunk size, DB pool, partition strategy và worker count rồi kết luận nguyên nhân.
6. **Lặp lại đủ lần.** Quan sát cache, JIT, GC và tải DB biến động; so cùng điều kiện.
7. **Thử lỗi có chủ đích.** Kill worker giữa chunk, mất kết nối, rollback và restart.
8. **Đối soát output.** Kiểm tra business key thiếu/trùng và tác dụng ngoài DB.
9. **Chỉ chọn cấu hình đạt tiêu chí.** SLA, độ tin cậy, ngân sách tài nguyên và khả năng vận hành.

### Các cột tối thiểu nên lưu trong kết quả thử

| Thuộc tính | Mục đích |
| --- | --- |
| Phiên bản code/config | Biết kết quả thuộc thay đổi nào |
| Dataset và business date | Tránh so sánh dữ liệu khác nhau |
| Chunk size, thread count, partition count | Biết biến được thử |
| Active connections, pool wait | Phát hiện nghẽn kết nối |
| CPU, heap, GC | Phát hiện giới hạn JVM |
| Read/write count, elapsed time | Tính throughput đầu-cuối |
| Rollback/retry/skip | Kiểm tra thời gian và độ tin cậy |
| JobRepository/broker latency | Chẩn đoán overhead điều phối |
| Kết quả đối soát business key | Chứng minh dữ liệu đúng |

## 14. Tài nguyên thực tế quyết định mức phức tạp hợp lý

Việc tăng worker thường dùng chung một số giới hạn vật lý:

- **Database:** số connection, CPU, I/O, transaction log, index, lock.
- **Dịch vụ ngoài:** quota API, rate limit, đồng thời tối đa và thời gian đáp ứng.
- **Một JVM:** CPU core, heap, GC, thread pool, file descriptor.
- **Nhiều JVM:** tổng RAM/CPU trên cluster, băng thông, broker và metadata store.
- **Con người:** năng lực on-call, log/tracing, quản lý phiên bản và kịch bản disaster recovery.

Ví dụ sáu worker JVM, mỗi worker có pool tối đa 10 connection và manager tối đa 8 connection: **tổng ngân sách cấu hình có thể là 68 connection**, chưa tính dịch vụ khác. Đây không phải số connection chắc chắn đang sử dụng; phải đo active/waiting và giới hạn DB thực tế.

Nếu DB chỉ xử lý hiệu quả 25 transaction đồng thời cho workload này, việc cấp 68 connection không tạo ra năng lực tương ứng. Nó có thể chỉ tăng chờ lock, context switching và timeout.

### Đừng nhầm thêm queue với tăng năng lực

Khi producer gửi nhanh hơn consumer, queue tăng nhưng số item ghi bền vững không tự tăng. Với remote chunking, cần backpressure: giới hạn inflight chunk, message age, worker concurrency và retry. Với step chunk-oriented đồng bộ không có queue ngoài, chu trình read/process/write thường tự hạn chế tốc độ đọc theo khả năng writer.

## 15. Tính đúng dữ liệu là điều kiện của “giải pháp đủ tốt”

Một hệ thống nhanh nhưng bỏ sót hoặc ghi trùng dữ liệu là không đạt mục tiêu. Mỗi lần tăng concurrency cần đánh giá ít nhất bốn vấn đề.

### 15.1. Thread safety

Multi-threaded step có thể chia sẻ reader/processor/writer. Nhiều reader có mutable state không mặc định thread-safe. Một wrapper đồng bộ hóa read có thể tránh một số race condition nhưng không giải quyết toàn bộ vấn đề thứ tự commit và restart.

Partitioning với reader riêng theo StepExecution giảm state chia sẻ nhưng **không tự** làm thread-safe các singleton còn lại hoặc tài nguyên ngoài.

### 15.2. Ranh giới dữ liệu

Mỗi partition phải sở hữu vùng dữ liệu tường minh, không chồng lấn và không bỏ sót. Ví dụ các khoảng **[1, 100001)** và **[100001, 200001)** sử dụng cận dưới bao gồm/cận trên loại trừ.

Tên partition và snapshot/high-watermark cần ổn định qua restart. Nếu một worker lấy MAX(id) mới khi chạy lại, phạm vi đầu vào có thể khác với checkpoint đã lưu.

### 15.3. Transaction, retry và idempotency

Một worker có thể commit DB nhưng chết trước khi phản hồi manager. Tùy mô hình, phần việc có thể được thực hiện lại. Vì vậy cần:

- Unique business key hoặc upsert đúng ngữ nghĩa.
- Idempotency key với API ngoài khi được hỗ trợ.
- Cơ chế outbox nếu cần phối hợp DB với message.
- Retry có giới hạn/backoff, phân biệt lỗi tạm thời và lỗi dữ liệu.
- Đối soát số record và khóa nghiệp vụ sau restart.

JobRepository hỗ trợ quản lý trạng thái, nhưng không tự bảo đảm mọi side effect qua DB, broker và HTTP xảy ra **exactly once**.

### 15.4. Restart

Không coi việc cấu hình một reader với **saveState(true)** là bằng chứng đầy đủ rằng job restart chính xác. Còn phải kiểm tra query có thứ tự ổn định, đầu vào có thay đổi, checkpoint được lưu đúng và writer có thể chạy lại an toàn.

**Một giải pháp đơn giản nhưng không restart được khi sự cố thường không phải giải pháp tốt** cho workload lớn với SLA nghiêm ngặt.

## 16. Tình huống minh họa: mười hai triệu hóa đơn cuối ngày

Một doanh nghiệp phải tính và lưu kết quả cho **12.000.000 hóa đơn** trong **30 phút** sau khi đóng cửa sổ dữ liệu.

Mục tiêu lý tưởng:

\[
12.000.000 / (30\times60)\approx6.667\ \mathrm{item/s}
\]

Giả sử các phép đo sau cùng sử dụng tập dữ liệu như nhau và writer ghi một kết quả trên mỗi item; toàn bộ số liệu là **giả định**, không phải benchmark của Spring Batch.

| Bước thử | Cấu hình | Throughput hoàn tất | Thời gian xấp xỉ |
| --- | --- | ---: | ---: |
| A | Một step tuần tự, SQL/writer ban đầu | 3.200 item/s | 62,5 phút |
| B | Vẫn tuần tự, tối ưu index và JDBC batch | 6.300 item/s | 31,7 phút |
| C | Local partitioning, 2 worker | 7.400 item/s | 27,0 phút |
| D | Local partitioning, 4 worker | 8.400 item/s | 23,8 phút |
| E | Remote partitioning, 4 worker JVM | 8.700 item/s | 23,0 phút |

### Diễn giải quyết định

**Bước A → B:** chỉ sửa query/index và writer đã gần gấp đôi throughput mà không cần điều phối thêm worker. Dù chưa đạt SLA, nhóm đã giảm rất nhiều công việc phải phân phối.

**Bước B → C:** chia dữ liệu theo ID và chạy hai worker local. SLA 30 phút được đáp ứng **trong phép đo giả định**, nhưng 27 phút có thể thiếu dư địa cho retry hoặc tăng trưởng. Vì vậy không dừng ngay nếu yêu cầu dự phòng chưa đạt.

**Bước C → D:** bốn worker local hoàn thành sau 23,8 phút, tạo khoảng **6,2 phút dư địa** theo số đo giả định. Nếu CPU/RAM/DB còn nằm trong ngân sách và thử restart thành công, đây có thể là lựa chọn hợp lý.

**Bước D → E:** remote partitioning giảm từ 23,8 xuống 23,0 phút, tức tiết kiệm chưa tới một phút, nhưng cần thêm điều phối giữa JVM, network, worker deployment và giám sát. Với dữ liệu và SLA giả định, lợi ích này chưa rõ ràng để bù chi phí. Nếu điều kiện tài nguyên khác đi hoặc cần cô lập worker theo host, kết luận có thể thay đổi.

### Các phép thử phải vượt qua

- Job xử lý đúng 12 triệu business key cần thiết; không có trùng/thiếu ngoài chính sách.
- Dừng một worker giữa chunk rồi restart, kết quả vẫn đúng.
- DB connection wait, lock, rollback và heap nằm trong giới hạn.
- Đã thử tải cao hơn baseline để có dự phòng tăng trưởng.
- Thời gian hoàn thành toàn job, gồm khởi tạo và bước đối soát, đáp ứng cửa sổ 30 phút.

Trường hợp này minh họa cách chọn **độ phức tạp tối thiểu để đáp ứng SLA có dự phòng**, không nhất thiết chọn benchmark có thời gian thấp nhất.

## 17. Lúc nào không nên đi từ tuần tự theo từng nấc?

Nguyên tắc đơn giản trước **không bắt buộc** phải triển khai mọi bước trong một “thang scaling”. Có những điều kiện khiến mô hình phân tán hoặc partitioning rõ ràng là điểm xuất phát phù hợp:

- Dữ liệu đã nằm tại các shard/region độc lập; chuyển toàn bộ về một reader trung tâm tạo chi phí mạng lớn.
- Một job có SLA ngắn hơn rõ rệt khả năng vật lý của một JVM; baseline đo hoặc capacity test đã chứng minh điều đó.
- Do yêu cầu độ tin cậy, các worker phải có vòng đời và tài nguyên tách biệt.
- Có giới hạn bảo mật hoặc dữ liệu không được rời một miền xử lý nhất định.
- Workload vốn là nhiều flow độc lập và có thể chạy parallel steps đơn giản hơn việc gộp lại rồi chia lại.

Ngay cả trong những trường hợp này, vẫn nên chọn **kiến trúc đơn giản nhất trong nhóm khả thi** và đo hiệu năng theo tập dữ liệu đại diện. Đừng phân tán chỉ để “chuẩn bị cho tương lai” mà chưa có dự báo hoặc nhu cầu cụ thể.

## 18. Triển khai thay đổi theo cách có thể quay về

Khi một cấu hình concurrency hoặc partitioning mới được chứng minh có ích, đừng chuyển toàn bộ workload mà không có cách kiểm soát.

Một quy trình triển khai phù hợp:

1. **Chốt cấu hình baseline** và kết quả đối soát làm mốc.
2. **Bổ sung metric/log** theo JobExecution, StepExecution, partition và worker.
3. **Chạy dữ liệu thử đại diện** với số worker nhỏ, tăng dần theo ngân sách.
4. **Thử lỗi/restart** trước khi áp dụng dữ liệu sản xuất.
5. **Ghi lại điều kiện quyết định:** SLA, throughput, p95 chunk duration, rollback, DB saturation.
6. **Có phương án quay về cấu hình đã kiểm chứng** nếu tải DB, lỗi hoặc thời gian hoàn thành xấu đi.

Cần lưu ý việc giảm worker hoặc thay chiến lược phân vùng trong khi **cùng JobInstance đang restart** có thể ảnh hưởng đến checkpoint và định danh partition. “Rollback cấu hình” chỉ đơn giản khi đã xác định rõ phiên bản, trạng thái job và dữ liệu được phép chạy lại; không đổi tùy tiện ranh giới partition đang có state.

### Tiêu chí dừng mở rộng

Có thể dừng tăng độ phức tạp khi:

- Job đáp ứng SLA với dự phòng được thống nhất.
- Đã qua kiểm thử restart và đối soát dữ liệu.
- Tài nguyên DB/JVM/broker còn trong giới hạn an toàn.
- Chi phí thêm worker lớn hơn lợi ích biên về thời gian.
- Hệ thống đủ dễ hiểu để đội ngũ điều tra và xử lý lỗi.

Điều kiện dừng cần được xem lại khi dữ liệu, schema, hạ tầng, dịch vụ ngoài hoặc SLA thay đổi.

## 19. Những nhầm lẫn thường gặp

| Nhận định | Điều cần hiểu |
| --- | --- |
| “Càng nhiều worker càng nhanh.” | Nút thắt chung, coordination, contention và retry có thể làm throughput giảm. |
| “Một step tuần tự là không hiện đại.” | Nếu đúng dữ liệu và đạt SLA, tuần tự có thể là thiết kế phù hợp nhất. |
| “Chỉ cần thêm TaskExecutor là an toàn.” | Reader/processor/writer dùng chung cần thread safety và kiểm tra restart. |
| “Không đạt SLA thì phải lập tức dùng remote partitioning.” | Trước hết đo SQL, writer, commit interval, CPU và năng lực DB. |
| “Local partitioning luôn phức tạp hơn multi-threaded step.” | Tùy reader stateful; ranh giới partition riêng có thể dễ kiểm soát hơn một reader mutable dùng chung. |
| “Parallel steps và partitioning giống nhau.” | Parallel steps tận dụng flow độc lập; partitioning chia một worker step thành phạm vi dữ liệu riêng. |
| “Remote chunking tự phân tán đọc DB.” | Manager thường đọc và gửi item/chunk; reader trung tâm có thể là bottleneck. |
| “Remote partitioning giúp giảm tải DB nguồn.” | Nhiều worker tự đọc có thể làm **tăng** tổng tải DB nguồn. |
| “Grid size phải bằng số thread.” | Số partition và mức concurrency thực tế là hai khái niệm khác nhau. |
| “Đạt tốc độ là đủ.” | Cần tính đúng, idempotency, retry/restart, chi phí và khả năng vận hành. |
| “Upsert giải quyết mọi tác dụng phụ lặp lại.” | Upsert chỉ phù hợp một số thao tác DB; email, API và cộng dồn cần chiến lược riêng. |
| “Chọn giải pháp đơn giản trước tức luôn chỉ chạy một thread.” | Đơn giản nhất là **giải pháp ít phức tạp nhất đã chứng minh đáp ứng đầy đủ yêu cầu**. |

## 20. Checklist trước khi chọn kiến trúc

- [ ] SLA, khối lượng dữ liệu và dự phòng tăng trưởng được xác định rõ.
- [ ] Đã đo baseline với read/write count và đối soát business key.
- [ ] Đã đo đúng bottleneck reader, processor, writer và hạ tầng.
- [ ] Đã thử tối ưu SQL/index, batch writer và commit interval trước khi tăng concurrency.
- [ ] Nếu parallel steps, các flow thực sự độc lập và điểm join hợp lệ.
- [ ] Nếu multi-threaded step, các component dùng chung được đánh giá thread safety.
- [ ] Nếu partitioning, vùng dữ liệu không chồng lấn, định danh và snapshot ổn định.
- [ ] Nếu multi-process, có lý do về tài nguyên hoặc yêu cầu cách ly được kiểm chứng.
- [ ] Đã tính tổng connection pool, DB quota, broker/queue capacity và giới hạn host.
- [ ] Có backpressure, retry có giới hạn, idempotency và thủ tục restart.
- [ ] Đã thử worker chết giữa chunk và xác nhận không mất/trùng dữ liệu.
- [ ] Có benchmark cùng dataset và ghi lại biến thay đổi cho mỗi lần thử.
- [ ] Đã xác định điểm dừng tăng concurrency theo SLA, chi phí và độ tin cậy.
- [ ] Có phương án vận hành và quay về cấu hình đã kiểm chứng.

## 21. Câu hỏi tự kiểm tra

**1. Một job chạy 8 phút và SLA là 20 phút. Có nên lập tức triển khai remote partitioning?**

Chưa có lý do chỉ từ tốc độ. Cần xem tải tăng trưởng, khả năng restart và yêu cầu vận hành; nếu các điều kiện đều đạt, giữ kiến trúc hiện tại có thể tốt hơn.

**2. Vì sao một reader chậm do query thiếu index khó được cứu bằng thêm thread?**

Nhiều thread có thể tạo thêm các truy vấn tốn scan, làm DB bão hòa hơn. Tối ưu kế hoạch truy vấn và giảm I/O không cần thiết trước khi nhân truy vấn thường hữu ích hơn.

**3. Khi nào multi-threaded step có thể kém đơn giản hơn local partitioning?**

Khi reader giữ cursor/state mutable và checkpoint phụ thuộc thứ tự đọc. Partitioning với reader riêng theo khoảng dữ liệu ổn định có thể giúp suy luận và restart rõ ràng hơn.

**4. Một job có ba flow độc lập nhưng không có tập dữ liệu chung cần chia; mô hình nào dễ phù hợp?**

Parallel steps là ứng viên trực tiếp. Cần xác nhận không có phụ thuộc dữ liệu ngoài ý muốn và hạ tầng chịu được chạy đồng thời.

**5. Khi nào remote chunking có lợi so với remote partitioning?**

Khi manager đọc đủ nhanh, item chuyển qua mạng có kích thước phù hợp và phần process/write là bottleneck; remote partitioning phù hợp hơn khi worker có thể tự đọc các phạm vi dữ liệu độc lập.

**6. Vì sao phải thử kill worker và restart trước khi đưa cấu hình nhanh hơn vào production?**

Vì concurrency và phân tán làm tăng các tình huống xử lý lại; nếu writer không idempotent hoặc checkpoint sai, job có thể trùng hoặc mất dữ liệu. Tốc độ không thể bù đắp kết quả sai.

**7. Sau khi tăng từ bốn lên tám worker, job chỉ nhanh hơn 2%, connection wait và rollback tăng. Quyết định hợp lý là gì?**

Thường nên giữ hoặc quay lại cấu hình ít worker hơn, điều tra bottleneck DB và chỉ tăng tiếp khi có cải thiện đã đo được. Phải xét yêu cầu SLA và ngân sách tài nguyên.

**8. Nguyên tắc “đơn giản trước” có cấm bắt đầu với mô hình phân tán không?**

Không. Nếu dữ liệu đã chia shard, yêu cầu cô lập worker hoặc giới hạn vật lý của một JVM được chứng minh, mô hình phân tán có thể là cách đơn giản nhất để đáp ứng mục tiêu. Quyết định vẫn cần số đo và kiểm thử tính đúng.

---

**Ghi nhớ:** Trong Spring Batch, mở rộng quy mô là một chuỗi **quyết định dựa trên bằng chứng**: đo baseline, sửa bottleneck đơn giản, kiểm tra độ độc lập của công việc, tăng concurrency từng nấc và chỉ mở rộng qua nhiều JVM khi thực sự cần. Kiến trúc tốt nhất là kiến trúc **ít phức tạp nhất có thể đáp ứng SLA, bảo vệ dữ liệu và khôi phục được khi lỗi**, với chi phí tài nguyên và vận hành phù hợp.
