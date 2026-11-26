# ChunkProcessor cho worker cục bộ

Trong Spring Batch, một **worker cục bộ** là một lần thực thi step xử lý dữ liệu ngay trong ứng dụng/JVM hiện tại. Worker có thể chạy tuần tự hoặc đồng thời với các worker khác, chẳng hạn khi dùng **local partitioning**. Với step kiểu chunk, thành phần đảm nhiệm phần xử lý và ghi của từng chunk là **ChunkProcessor**. Hiểu rõ ranh giới này giúp mở rộng workload lớn mà vẫn kiểm soát được tính đúng đắn, transaction, retry và restart.

Bài học thuộc chương **Local Chunking** của module **SPRING_BATCH_SCALING_OPERATIONS**: mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình phân tán phù hợp; đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và chọn kiến trúc dựa trên tài nguyên thực tế.

## 1. Mục tiêu và ngữ cảnh

Sau bài này, bạn cần có khả năng:

- Phân biệt **ChunkProcessor**, **ItemProcessor**, **ChunkProvider** và **worker Step**.
- Giải thích vòng đời read → process → write → commit trong một local chunk.
- Cấu hình worker Step có processor và writer an toàn khi nhiều partition chạy cùng JVM.
- Nhận diện tác động của chunk size, số partition và số luồng lên throughput, bộ nhớ và kết nối cơ sở dữ liệu.
- Thiết kế xử lý lỗi, retry, skip, restart và ghi idempotent để tránh mất hoặc nhân đôi dữ liệu.
- Đọc số liệu thực thi để quyết định có nên tăng concurrency hay chuyển sang mô hình phân tán.

### Local chunking nằm ở đâu?

Một chunk là một đơn vị xử lý và transaction, thường gồm tối đa N phần tử được đọc trước khi gọi writer. **Local** cho biết các thành phần điều phối, xử lý và ghi đều nằm trong cùng ứng dụng; dữ liệu không cần gửi qua message broker đến remote worker.

Có hai tình huống dễ gặp:

1. **Chunk-oriented Step thông thường:** một worker Step đọc và xử lý nhiều chunk liên tiếp.
2. **Local partitioning:** manager Step chia dữ liệu thành các vùng không giao nhau; các worker StepExecution chạy trên thread pool cục bộ. **Mỗi worker vẫn thực hiện read → process → write theo chunk**.

Không nên đồng nhất local chunking với multi-threaded Step. Multi-threaded Step có thể cho nhiều luồng cùng tham gia một step và chia sẻ một số thành phần; local partitioning tạo các **StepExecution riêng**, mỗi execution nhận ExecutionContext của một partition. Cả hai đều cần kiểm tra thread safety, nhưng ranh giới trạng thái và restart khác nhau.

## 2. Vai trò chính xác của ChunkProcessor

Trong một chunk-oriented step, Spring Batch dùng các thành phần nội bộ cùng nhau để thực hiện từng chunk:

| Thành phần | Trách nhiệm | Điều cần nhớ |
| --- | --- | --- |
| **ItemReader\<I\>** | Trả về từng item đầu vào, trả về null khi hết dữ liệu | Reader có thể có cursor và trạng thái restart |
| **ChunkProvider\<I\>** | Tập hợp item từ reader thành một chunk | Liên quan read count, read error và kích thước chunk |
| **ChunkProcessor\<I\>** | Xử lý cả chunk: chuyển đổi/lọc các item rồi gọi writer | Là tầng điều phối xử lý chunk, không phải một worker thread |
| **ItemProcessor\<I,O\>** | Biến đổi hoặc xác thực **một item**; có thể trả về null để lọc | Phần nghiệp vụ thường do ứng dụng viết |
| **ItemWriter\<O\>** | Ghi tập output của một chunk | Trong Spring Batch 5.x, phương thức write nhận một Chunk |
| **TaskletStep / ChunkOrientedTasklet** | Thực hiện các lượt chunk trong ranh giới transaction của step | Quản lý commit, rollback và cập nhật StepExecution |

**ChunkProcessor** ở đây là interface của hạ tầng Spring Batch, thường được triển khai bằng **SimpleChunkProcessor** cho xử lý cơ bản hoặc **FaultTolerantChunkProcessor** khi cấu hình cơ chế chịu lỗi. Ứng dụng thông thường **không cần tự khởi tạo hoặc tự gọi** những lớp này. Thay vào đó, ta cấu hình ItemProcessor, ItemWriter và các chính sách retry/skip qua StepBuilder; Spring Batch tạo chuỗi xử lý thích hợp.

Chữ *Processor* trong hai tên rất dễ gây nhầm lẫn:

- **ItemProcessor:** phương thức nghiệp vụ chạy trên từng item, ví dụ chuẩn hóa số tiền của một đơn hàng.
- **ChunkProcessor:** thành phần framework phối hợp xử lý **toàn bộ chunk**, lọc kết quả, ghi dữ liệu và cập nhật các bộ đếm liên quan.

Nếu ItemProcessor trả về null, item bị **filter**, không được gửi tới writer. Đây là xử lý lọc hợp lệ, khác với **skip** một item do ngoại lệ được chính sách chịu lỗi cho phép.

### Luồng điều khiển

~~~mermaid
flowchart TD
    A["Manager Step (nếu partitioning)"] --> B["Partitioner tạo ExecutionContext"]
    B --> C["Worker StepExecution trên thread pool"]
    C --> D["TaskletStep / ChunkOrientedTasklet"]
    D --> E["Bắt đầu transaction của chunk"]
    E --> F["ChunkProvider đọc Chunk<I>"]
    F --> G["ChunkProcessor xử lý Chunk<I>"]
    G --> H["ItemProcessor áp dụng từng item"]
    H --> I["ItemWriter ghi Chunk<O>"]
    I --> J["Commit; cập nhật StepExecution"]
    J --> K{"Còn dữ liệu?"}
    K -->|Có| E
    K -->|Không| L["Worker hoàn tất"]
~~~

Sơ đồ thể hiện **quy trình khái niệm**. Khi có lỗi, chunk có thể rollback, retry hoặc skip tùy cấu hình; không phải mọi lượt gọi đều đi thẳng tới commit.

## 3. Vòng đời một chunk trong worker

Giả sử chunk size = **200**, một partition có 1.000 bản ghi hợp lệ và không phát sinh lỗi:

1. Worker mở tài nguyên reader, lấy tối đa 200 bản ghi cho chunk đầu.
2. ChunkProcessor gọi ItemProcessor cho từng bản ghi. Các bản ghi bị filter không nằm trong output.
3. ItemWriter nhận chunk output và thực hiện ghi, thường theo batch SQL.
4. Transaction thành công thì commit, state của reader/step được lưu theo cấu hình restart.
5. Worker tiếp tục cho tới khi reader báo hết dữ liệu; cuối cùng step được đánh dấu hoàn tất.

Trong trường hợp lý tưởng này có khoảng **5 transaction ghi chunk**, nhưng commit count thực tế có thể khác do chunk cuối, metadata, rollback hoặc chính sách lỗi.

~~~text
Worker partition-0
  chunk 1: read 200 -> process 200 -> write <= 200 -> COMMIT
  chunk 2: read 200 -> process 200 -> write <= 200 -> COMMIT
  ...
  chunk 5: read 200 -> process 200 -> write <= 200 -> COMMIT
~~~

Transaction bao quanh **đơn vị chunk**. Nếu writer thất bại sau khi đã xử lý 200 item, transaction tài nguyên có thể rollback toàn bộ phần ghi của chunk; framework có thể thực hiện lại xử lý hoặc ghi theo chính sách đã cấu hình. Do đó **ItemProcessor nên tránh side effect ngoài transaction** như tự gửi email hoặc gọi API tạo giao dịch không có khóa chống trùng.

Các bộ đếm cần phân biệt:

| Bộ đếm StepExecution | Ý nghĩa sử dụng |
| --- | --- |
| readCount | Số item đọc thành công |
| filterCount | Số item bị ItemProcessor lọc bằng cách trả về null |
| writeCount | Số item ghi thành công được Spring Batch ghi nhận |
| readSkipCount, processSkipCount, writeSkipCount | Số item bị bỏ qua do lỗi tại từng giai đoạn |
| commitCount, rollbackCount | Số lần commit và rollback được ghi nhận |

Đừng đánh giá chất lượng job chỉ bằng readCount. Nếu readCount lớn nhưng writeCount rất nhỏ, hãy xem filter/skip count, logic nghiệp vụ và các lần rollback.

## 4. Ví dụ thực tế: xử lý đơn hàng bằng các local worker

**Bài toán:** có 400.000 đơn hàng đầu vào trong PostgreSQL, cần chuẩn hóa tổng tiền và ghi vào bảng kết quả. Ta chia khoảng ID thành 4 partition, dùng tối đa 4 thread trong cùng JVM; mỗi worker đọc và ghi từng chunk 200 item.

Giả định:

- Bảng đầu vào có khóa chính **id** và cột **total**; bảng kết quả có khóa duy nhất **order_id**.
- Dữ liệu nguồn của đợt chạy là bất biến hoặc được cố định theo snapshot/cutoff. Khoảng ID phải ổn định trong lần restart.
- Kết quả tính toán là xác định (deterministic) với cùng một bản ghi đầu vào.
- Spring Batch **5.x**, Java 17+, Spring Framework/Spring Boot tương thích. Các import được lược bớt để tập trung vào thiết kế.

### 4.1. Schema đầu vào và kết quả

~~~sql
CREATE TABLE inbound_order (
    id BIGINT PRIMARY KEY,
    total NUMERIC(18, 2)
);

CREATE TABLE order_result (
    order_id BIGINT PRIMARY KEY,
    net_total NUMERIC(18, 2) NOT NULL
);
~~~

Khóa chính của bảng kết quả cho phép ghi **idempotent** bằng PostgreSQL UPSERT. Đây là lớp bảo vệ quan trọng nếu chunk phải chạy lại sau rollback hoặc job được restart.

### 4.2. Reader theo vùng dữ liệu của từng partition

Mỗi worker nhận một ExecutionContext gồm **minId** (bao gồm) và **maxIdExclusive** (không bao gồm). Reader khai báo **@StepScope** để mỗi StepExecution có instance và tham số phù hợp với vùng dữ liệu của mình.

~~~java
record OrderRow(long id, BigDecimal total) {}
record OrderResult(long orderId, BigDecimal netTotal) {}

@Bean
@StepScope
JdbcCursorItemReader<OrderRow> orderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxIdExclusive) {

    return new JdbcCursorItemReaderBuilder<OrderRow>()
            .name("orderReader")
            .dataSource(dataSource)
            .sql("""
                 SELECT id, total
                 FROM inbound_order
                 WHERE id >= ? AND id < ?
                 ORDER BY id
                 """)
            .preparedStatementSetter(ps -> {
                ps.setLong(1, minId);
                ps.setLong(2, maxIdExclusive);
            })
            .rowMapper((rs, rowNum) ->
                    new OrderRow(rs.getLong("id"),
                                 rs.getBigDecimal("total")))
            .saveState(true)
            .build();
}
~~~

Ranh giới kiểu **[minId, maxIdExclusive)** làm cho hai partition liền kề không đọc trùng bản ghi. ORDER BY id giúp thứ tự đọc ổn định, cần thiết cho reader lưu trạng thái. Việc dùng cursor cũng có nghĩa mỗi worker có thể giữ một kết nối DB đang mở; cần tính điều này khi chọn kích thước connection pool.

### 4.3. ItemProcessor nghiệp vụ và writer

Processor bên dưới không giữ mutable shared state. Dữ liệu âm hoặc thiếu được coi là không hợp lệ và phát sinh ngoại lệ để minh họa cơ chế **skip có kiểm soát**. Writer dùng UPSERT để cùng một orderId luôn có tối đa một dòng kết quả.

~~~java
static final class BadOrderException extends RuntimeException {
    BadOrderException(long orderId) {
        super("Invalid total for order " + orderId);
    }
}

@Bean
ItemProcessor<OrderRow, OrderResult> orderProcessor() {
    return order -> {
        if (order.total() == null || order.total().signum() < 0) {
            throw new BadOrderException(order.id());
        }
        BigDecimal net = order.total().setScale(2, RoundingMode.HALF_UP);
        return new OrderResult(order.id(), net);
    };
}

@Bean
JdbcBatchItemWriter<OrderResult> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<OrderResult>()
            .dataSource(dataSource)
            .sql("""
                 INSERT INTO order_result (order_id, net_total)
                 VALUES (:orderId, :netTotal)
                 ON CONFLICT (order_id)
                 DO UPDATE SET net_total = EXCLUDED.net_total
                 """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("orderId", item.orderId())
                            .addValue("netTotal", item.netTotal()))
            .build();
}
~~~

Nếu quy tắc nghiệp vụ muốn **lọc hợp lệ** (ví dụ bỏ các đơn đã hủy), ItemProcessor có thể trả về null; khi ấy filterCount tăng. Còn nếu dữ liệu **sai** và ta muốn quan sát, giới hạn số bản ghi sai, dùng ngoại lệ cùng chính sách skip như ví dụ.

### 4.4. Cấu hình worker Step với chunk và fault tolerance

~~~java
@Bean
Step workerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<OrderRow> orderReader,
        ItemProcessor<OrderRow, OrderResult> orderProcessor,
        JdbcBatchItemWriter<OrderResult> orderWriter) {

    return new StepBuilder("workerStep", jobRepository)
            .<OrderRow, OrderResult>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .skip(BadOrderException.class)
            .skipLimit(100)
            .build();
}
~~~

Ở đây, **chunk(200, transactionManager)** quyết định commit interval; **faultTolerant()** kích hoạt đường xử lý retry/skip của framework. ChunkProcessor bên trong worker sẽ áp dụng ItemProcessor và ItemWriter đã khai báo. Không cần gọi ChunkProcessor trong mã ứng dụng.

Chính sách trên là một ví dụ cần điều chỉnh theo dữ liệu thực:

- **retryLimit(3):** dùng cho lỗi tạm thời, chẳng hạn kết nối DB hoặc tranh chấp tài nguyên. Không retry vô hạn.
- **skipLimit(100):** chỉ bỏ qua tối đa số item lỗi được chấp nhận; vượt ngưỡng thì step thất bại để người vận hành xử lý.
- Lỗi dữ liệu cố định nên được phân loại rõ. Không nên skip mọi Exception vì sẽ che khuất lỗi lập trình, lỗi schema hoặc lỗi hạ tầng nghiêm trọng.

### 4.5. Partitioner và manager Step chạy trong cùng JVM

Partitioner chia khoảng ID cố định của ví dụ thành bốn vùng gần bằng nhau. Mỗi vùng có ExecutionContext riêng. Manager phân phối các worker StepExecution qua ThreadPoolTaskExecutor; chính từng worker thực hiện ChunkProvider và ChunkProcessor của nó.

~~~java
@Bean
Partitioner orderPartitioner() {
    return gridSize -> {
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
        long from = 1L;
        long endExclusive = 400_001L; // Demo: snapshot có ID từ 1 đến 400000
        long width = Math.max(
                1L, (endExclusive - from + gridSize - 1) / gridSize);

        for (int index = 0; from < endExclusive; index++) {
            long to = Math.min(endExclusive, from + width);
            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", from);
            context.putLong("maxIdExclusive", to);
            partitions.put("partition" + index, context);
            from = to;
        }
        return partitions;
    };
}

@Bean
ThreadPoolTaskExecutor partitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(4);
    executor.setThreadNamePrefix("local-worker-");
    executor.initialize();
    return executor;
}

@Bean
Step managerStep(JobRepository jobRepository,
                 Step workerStep,
                 Partitioner orderPartitioner,
                 ThreadPoolTaskExecutor partitionExecutor) {
    return new StepBuilder("managerStep", jobRepository)
            .partitioner(workerStep.getName(), orderPartitioner)
            .step(workerStep)
            .gridSize(4)
            .taskExecutor(partitionExecutor)
            .build();
}

@Bean
Job orderJob(JobRepository jobRepository, Step managerStep) {
    return new JobBuilder("orderJob", jobRepository)
            .start(managerStep)
            .build();
}
~~~

Ví dụ cố ý dùng phạm vi ID tĩnh để dễ quan sát. **Trong hệ thống thực**, cần lấy mốc dữ liệu lúc tạo job (từ tham số job hoặc một snapshot/cutoff bền vững) và giữ nguyên ranh giới qua các lần restart. Không tính lại khoảng chia từ bảng nguồn đang thay đổi, vì như vậy một partition được khởi động lại có thể đọc lệch vùng cũ.

Với 400.000 item hợp lệ, chunk size 200 tạo khoảng **2.000 chunk** trên toàn job; bốn partition cân bằng có khoảng **500 chunk/partition**. Đây là ước lượng lý tưởng, không thay thế số commit và write thực đo được.

## 5. Thread safety và ranh giới trạng thái

Local partitioning chạy các StepExecution độc lập nhưng các bean singleton có thể vẫn được dùng chung trong cùng ApplicationContext. Vì thế **tạo nhiều partition chưa tự động bảo đảm mọi component thread-safe**.

| Thành phần | Cách cấu hình an toàn | Rủi ro khi chia sẻ |
| --- | --- | --- |
| Reader có cursor và vị trí đọc | @StepScope, nhận min/max từ ExecutionContext | Trộn vị trí đọc, bỏ sót hoặc đọc trùng |
| ItemProcessor | Stateless, chỉ dùng biến cục bộ; hoặc tách trạng thái theo StepScope | Race condition trên bộ đếm, cache hoặc danh sách mutable |
| ItemWriter | Writer hỗ trợ concurrent use và ghi độc lập; dùng khóa/upsert khi cần | Race condition, update mất dữ liệu, trùng kết quả |
| ExecutionContext | Mỗi StepExecution sở hữu context; lưu giá trị nhỏ, có thể serialize | Ghi chung state hoặc cất object không bền vững |
| DataSource / HTTP client | Pool có giới hạn, timeout và đo thời gian chờ | Cạn connection, queue dài, làm chậm cả ứng dụng |

Đặc biệt, **@StepScope áp dụng cho instance bean theo StepExecution**, không biến một thư viện không thread-safe thành thread-safe nếu instance đó vẫn bị chia sẻ ngoài scope. Tránh đưa một List, Map, SimpleDateFormat mutable hoặc counter không đồng bộ vào singleton processor rồi để tất cả worker cùng sửa.

Nếu sử dụng multi-threaded Step thay cho partitioning, hãy rà soát reader và writer kỹ hơn: các luồng có thể dùng chung cùng một reader của step. Một số reader có thể được bọc đồng bộ nhưng điều đó cũng có thể tạo nút thắt mới; đồng bộ phương thức read không giải quyết mọi yêu cầu về restart hoặc thứ tự xử lý.

## 6. Retry, rollback, skip và restart

### 6.1. Retry có giới hạn

Retry phù hợp với lỗi **tạm thời** có khả năng tự hết (ví dụ DB trả lỗi transient). Khi chunk rollback rồi thử lại, quá trình xử lý có thể được thực hiện thêm lần nữa. Vì vậy:

- Processor nên **deterministic**, không gửi side effect không thể rollback.
- Writer nên ghi trong transaction và có chiến lược **idempotency** hoặc constraint chống trùng.
- Cần đo **số retry, rollback, thời gian backoff** và xem xét tải DB; thêm retry quá nhiều có thể làm tình trạng nghẽn nặng hơn.

### 6.2. Skip không giống filter

**Filter** là kết quả nghiệp vụ mong muốn của ItemProcessor trả về null. **Skip** là việc bỏ qua item lỗi theo một chính sách đã được khai báo. Skip phải có ngưỡng và lý do đủ rõ để người vận hành đối soát dữ liệu đầu vào với kết quả.

Ví dụ: 10.000 item đọc, 200 item lọc hợp lệ, 3 item process skip, không có write skip; số item ghi kỳ vọng là 9.797 nếu không có trường hợp khác. Trong vận hành, hãy đối chiếu theo khóa nghiệp vụ thay vì chỉ dựa trên phép trừ bộ đếm.

### 6.3. Restart không có nghĩa là exactly-once ở mọi hệ thống

Spring Batch lưu metadata **JobExecution / StepExecution / ExecutionContext** trong JobRepository. Khi một worker fail, job restart có thể tiếp tục các partition chưa hoàn tất dựa trên trạng thái được lưu và đặc tính restart của reader. Nhưng:

- State của reader chỉ đáng tin khi dữ liệu nguồn và thứ tự truy vấn ổn định.
- Một thao tác ngoài DB transaction (HTTP request, gửi email, xuất file ra hệ thống khác) có thể đã thành công dù chunk bị rollback.
- Việc worker/crash ở thời điểm biên có thể khiến một chunk cần chạy lại; do đó output cần khả năng ghi lặp an toàn.
- Partition name và phạm vi phân chia phải ổn định. Đổi chiến lược chia partition giữa các lần restart có thể làm metadata cũ không còn tương ứng dữ liệu.

Với writer PostgreSQL UPSERT ở ví dụ, chạy lại cùng orderId tạo cùng giá trị net_total. Nếu nghiệp vụ thực sự yêu cầu chống gửi trùng sự kiện ra ngoài, hãy cân nhắc **outbox pattern** hoặc khóa idempotency thay vì kỳ vọng một transaction DB bao phủ hệ thống khác.

## 7. Chọn chunk size và mức đồng thời bằng số đo

Ba tham số liên quan nhưng không thay thế nhau:

| Tham số | Điều chỉnh | Đổi lại |
| --- | --- | --- |
| **chunk size** | Số item mỗi transaction/đợt ghi | Chunk lớn giảm commit overhead nhưng tăng bộ nhớ và chi phí rollback |
| **gridSize** | Số partition đề nghị chia | Nhiều partition có thể cân bằng tải tốt hơn nhưng tăng overhead và metadata |
| **pool size** | Số worker cùng chạy thực tế | Tăng concurrency nhưng tiêu thụ thêm CPU, kết nối, I/O và lock |

Hãy bắt đầu bằng một baseline tuần tự và tăng dần trong giới hạn tài nguyên. Ví dụ trên máy có 8 CPU core, DB connection pool 10 và ứng dụng còn nhiều request khác, không thể mặc định 8 hoặc 10 worker là tối ưu: 4 worker có thể đạt throughput tốt hơn 8 worker nếu DB đang là nút thắt.

Một quy trình đo đơn giản:

1. Chạy với **1 worker**, chunk size 100 hoặc 200, ghi nhận item/giây, CPU, heap, GC, thời gian truy vấn/commit, connection wait và lock wait.
2. Giữ chunk size cố định, thử **2 rồi 4 worker** trên tập dữ liệu tương đương; so sánh throughput tổng và thời gian từng partition.
3. Giữ concurrency tốt nhất, thử chunk size **100, 200, 500**; quan sát số commit, heap peak, thời gian rollback và hiệu năng writer.
4. Xem phân phối partition. Nếu một partition mất 40 phút trong khi ba partition khác xong sau 5 phút, nút thắt có thể là **skew dữ liệu**, cần chia phạm vi cân bằng hơn trước khi tăng thread.
5. Cố định kết quả bằng số liệu thực, đồng thời giữ chừa chỗ cho connection pool, DB và những tác vụ chung của ứng dụng.

Các metric tối thiểu nên xem là **read/write/skip/rollback per partition**, throughput (item/giây), duration, CPU, heap/GC, pool active/idle/waiting và latency SQL. Tổng writeCount không nói lên được worker nào chậm nhất.

## 8. Tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Tăng worker nhưng job chậm hơn | DB pool thiếu, lock contention, CPU saturation hoặc I/O nghẽn | Giảm concurrency, xem SQL/index, mở rộng pool có kiểm soát |
| Bản ghi bị xử lý trùng giữa partition | Phạm vi ID giao nhau hoặc partitioner thay đổi sau restart | Dùng ranh giới [from, to), khóa duy nhất và phân vùng ổn định |
| Restart xong thiếu/nhân đôi kết quả | Source thay đổi, thứ tự đọc không ổn định, writer có side effect | Snapshot/cutoff bền vững, ORDER BY khóa duy nhất, idempotency |
| Thỉnh thoảng lỗi cursor hoặc trạng thái reader | Reader stateful bị dùng chung giữa thread | Mỗi StepExecution một reader qua @StepScope; kiểm tra multi-threaded Step |
| readCount cao, writeCount thấp | Nhiều filter, skip hoặc rollback | Kiểm tra per-partition counts và log ngoại lệ |
| Memory/GC tăng mạnh | Chunk quá lớn, processor giữ object, queue không giới hạn | Giảm chunk/queue, tránh giữ toàn bộ dữ liệu trong bộ nhớ |

## 9. Thực hành kiểm chứng

Với thiết kế đơn hàng ở phần 4, hãy chạy bốn phép thử có thể đo được:

1. **Phân vùng:** nạp các ID 1, 2, 100000, 100001, 200000, 200001 và 400000. Kiểm tra mỗi ID được đúng một partition đọc, không có bản ghi ở biên bị bỏ sót.
2. **Filter/skip:** nạp một đơn có total âm. Xác nhận processSkipCount tăng theo chính sách BadOrderException, bản ghi không được ghi và job chỉ tiếp tục khi chưa vượt skipLimit.
3. **Retry/restart:** làm một worker thất bại tạm thời khi đang ghi, sau đó cho job restart. Xác nhận kết quả theo order_id vẫn chỉ có một dòng, các partition hoàn tất không bị xử lý lại một cách không cần thiết.
4. **Hiệu năng:** so sánh 1, 2, 4 worker với chunk size 200; lưu thời gian job, item/giây, các bộ đếm và mức sử dụng DB. Chọn mức đồng thời theo bottleneck thực tế.

**Tiêu chí đạt:** dữ liệu đầu ra có đúng tập khóa và giá trị kỳ vọng; retry/restart không tạo bản ghi trùng; bộ đếm skip/filter được giải thích; throughput tăng khi còn tài nguyên và không sụp giảm do nghẽn DB.

## 10. Khi nào nên dùng kiến trúc khác?

- Dùng **chunk-oriented Step đơn luồng** khi dữ liệu vừa phải, thao tác I/O nhanh hoặc yêu cầu vận hành đơn giản.
- Dùng **local partitioning** khi có thể chia input thành phạm vi độc lập, cần restart/metrics riêng cho từng phần và một JVM còn đủ CPU/RAM/DB connections.
- Cân nhắc **parallel steps** khi các nhánh nghiệp vụ độc lập ở mức step, không chỉ là chia tập bản ghi của một step.
- Cân nhắc **remote partitioning/remote chunking** khi một JVM không đáp ứng tài nguyên hoặc cần triển khai worker ở nhiều máy; lúc này phải tính thêm truyền thông, độ tin cậy message và theo dõi các worker phân tán.

**Ghi nhớ:** ChunkProcessor là một mắt xích xử lý chunk bên trong worker; mở rộng hiệu quả đến từ cách phân chia dữ liệu, thread safety của các thành phần nghiệp vụ, transaction/restart đáng tin cậy và số đo tài nguyên. Chỉ tăng số thread hoặc chunk size mà bỏ qua các điều kiện đó có thể làm job chậm hơn hoặc tạo dữ liệu sai.
