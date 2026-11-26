# StepBuilder.partition với Java config

## 1. Vì sao cần `PartitionStep`?

Khi một Spring Batch job phải đọc và ghi hàng triệu bản ghi, thời gian chạy có thể bị giới hạn bởi một step xử lý tuần tự. `PartitionStep` cho phép chia tập dữ liệu thành nhiều phần độc lập (*partition*), rồi thực thi cùng một định nghĩa **worker step** cho mỗi phần. Đây là một cách mở rộng Spring Batch theo chiều ngang ở mức công việc; ví dụ bên dưới dùng nhiều luồng trong **cùng một JVM**.

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, kỹ thuật này cần được nhìn nhận cùng với đo nút thắt, giới hạn kết nối, thread safety, retry/restart và vận hành job. Tăng số partition chỉ có ích khi nguồn dữ liệu và hạ tầng xử lý chịu được mức song song tương ứng.

Giả sử bảng `source_orders` có 1.000.000 đơn hàng với ID ổn định. Một worker có thể đọc các ID từ 1 đến 125.000, worker tiếp theo đọc từ 125.001 đến 250.000, v.v. Mỗi worker ghi kết quả và cập nhật trạng thái thực thi của **chính partition đó** trong Spring Batch JobRepository.

Các khái niệm cần phân biệt:

| Thành phần | Trách nhiệm |
|---|---|
| **Manager step** (`PartitionStep`) | Khởi tạo và điều phối các partition, tổng hợp kết quả thực thi. |
| **`Partitioner`** | Tạo `Map<String, ExecutionContext>`; mỗi key là tên partition, mỗi context chứa dữ liệu định tuyến cho worker. |
| **Worker step** | Một `Step` thông thường (ví dụ chunk-oriented) được chạy nhiều lần, mỗi lần với một `StepExecution` riêng. |
| **`PartitionHandler`** | Gửi partition đến worker và chờ kết quả; có thể xử lý cục bộ hoặc chuyển đến các JVM khác. |
| **`TaskExecutor`** | Với local partitioning, quyết định cách cấp luồng cho các worker. |
| **`gridSize`** | Gợi ý số partition cho `Partitioner`; không đồng nghĩa với số luồng đồng thời. |

Luồng xử lý:

~~~mermaid
flowchart TD
    A[Job ordersPartitionJob] --> B[Manager: ordersManagerStep]
    B --> C[Partitioner chia dải ID]
    C --> P0[part0: minId / maxId]
    C --> P1[part1: minId / maxId]
    C --> PN[partN: minId / maxId]
    P0 --> H[TaskExecutor và PartitionHandler]
    P1 --> H
    PN --> H
    H --> W[Worker step: ordersWorkerStep]
    W --> R[Reader nhận ExecutionContext của partition]
    R --> X[Processor / Writer trong transaction]
    X --> J[JobRepository lưu StepExecution]
~~~

Các nhánh đến `ordersWorkerStep` trong sơ đồ biểu diễn **nhiều lần thực thi độc lập** của cùng một định nghĩa step, không phải một worker duy nhất dùng chung trạng thái đọc.

## 2. Cấu trúc Java config với `StepBuilder.partition`

Trong Spring Batch 5.x, một manager step cục bộ thường được khai báo theo chuỗi:

~~~java
new StepBuilder("ordersManagerStep", jobRepository)
    .partitioner("ordersWorkerStep", orderIdPartitioner)
    .step(ordersWorkerStep)
    .gridSize(8)
    .taskExecutor(partitionTaskExecutor)
    .build();
~~~

Giải thích từng điểm:

1. `new StepBuilder(..., jobRepository)` tạo step và liên kết nó với kho metadata của Batch.
2. `partitioner("ordersWorkerStep", ...)` đặt tên step con và cấp thuật toán chia dữ liệu. Tên này phải nhất quán với tên worker step được đăng ký.
3. `step(ordersWorkerStep)` cho biết định nghĩa step sẽ chạy trên mỗi partition.
4. `gridSize(8)` yêu cầu partitioner cân nhắc tạo tối đa khoảng tám phần, tùy cách cài đặt `partition(int gridSize)`.
5. `taskExecutor(...)` chọn local execution với các worker chạy trên pool luồng.

Không cần tạo tám bean worker step. Spring Batch tạo các `StepExecution` có tên dạng `ordersWorkerStep:part0`, `ordersWorkerStep:part1`, ... và chuyển `ExecutionContext` tương ứng tới từng lần chạy.

### Ví dụ dữ liệu

Ví dụ sử dụng PostgreSQL và Java 17 với API Spring Batch 5.x. Bảng nguồn chứa dữ liệu đã ổn định trong suốt một lần chạy job; bảng đích có khóa chính để hỗ trợ ghi lặp an toàn khi retry hoặc restart.

~~~sql
CREATE TABLE source_orders (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(18, 2) NOT NULL
);

CREATE TABLE processed_orders (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(18, 2) NOT NULL
);
~~~

Ứng dụng cần được cấu hình `DataSource`, `JobRepository`, `PlatformTransactionManager`, các bảng metadata của Spring Batch và những dependency JDBC/Batch thích hợp. Nếu dùng Spring Boot, có thể để auto-configuration tạo những thành phần này; đoạn bên dưới chỉ trình bày cấu hình job.

### Cấu hình đầy đủ

~~~java
import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.Map;

import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrdersPartitionJobConfiguration {

    public record OrderRow(long id, BigDecimal amount) {}

    @Bean
    public Job ordersPartitionJob(
            JobRepository jobRepository,
            @Qualifier("ordersManagerStep") Step managerStep) {
        return new JobBuilder("ordersPartitionJob", jobRepository)
                .start(managerStep)
                .build();
    }

    @Bean
    public Step ordersManagerStep(
            JobRepository jobRepository,
            @Qualifier("ordersWorkerStep") Step workerStep,
            @Qualifier("orderIdPartitioner") Partitioner partitioner,
            @Qualifier("partitionTaskExecutor")
                    ThreadPoolTaskExecutor executor) {

        return new StepBuilder("ordersManagerStep", jobRepository)
                .partitioner(workerStep.getName(), partitioner)
                .step(workerStep)
                .gridSize(8)
                .taskExecutor(executor)
                .build();
    }

    @Bean
    public ThreadPoolTaskExecutor partitionTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("batch-partition-");
        // Spring quản lý vòng đời và khởi tạo executor bean.
        return executor;
    }

    @Bean
    public Partitioner orderIdPartitioner(JdbcTemplate jdbc) {
        return gridSize -> {
            Long min = jdbc.queryForObject(
                    "SELECT MIN(id) FROM source_orders", Long.class);
            Long max = jdbc.queryForObject(
                    "SELECT MAX(id) FROM source_orders", Long.class);

            Map<String, ExecutionContext> partitions =
                    new LinkedHashMap<>();

            if (min == null || max == null) {
                // Worker đọc 0 dòng nhưng job vẫn có một partition hợp lệ.
                ExecutionContext empty = new ExecutionContext();
                empty.putLong("minId", 1L);
                empty.putLong("maxId", 0L);
                partitions.put("part0", empty);
                return partitions;
            }

            int requested = Math.max(1, gridSize);
            long width = Math.max(1, (max - min) / requested + 1);

            long start = min;
            int index = 0;
            while (start <= max) {
                long end = Math.min(max, start + width - 1);
                ExecutionContext context = new ExecutionContext();
                context.putLong("minId", start);
                context.putLong("maxId", end);
                partitions.put("part" + index++, context);

                if (end == max) {
                    break;
                }
                start = end + 1;
            }

            return partitions;
        };
    }

    @Bean
    public Step ordersWorkerStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            @Qualifier("ordersReader")
                    JdbcCursorItemReader<OrderRow> reader,
            @Qualifier("ordersWriter")
                    JdbcBatchItemWriter<OrderRow> writer) {

        return new StepBuilder("ordersWorkerStep", jobRepository)
                .<OrderRow, OrderRow>chunk(100, transactionManager)
                .reader(reader)
                .writer(writer)
                .build();
    }

    @Bean
    @StepScope
    public JdbcCursorItemReader<OrderRow> ordersReader(
            DataSource dataSource,
            @Value("#{stepExecutionContext['minId']}") Long minId,
            @Value("#{stepExecutionContext['maxId']}") Long maxId) {

        return new JdbcCursorItemReaderBuilder<OrderRow>()
                .name("ordersReader")
                .dataSource(dataSource)
                .sql("""
                    SELECT id, amount
                    FROM source_orders
                    WHERE id BETWEEN ? AND ?
                    ORDER BY id
                    """)
                .preparedStatementSetter(ps -> {
                    ps.setLong(1, minId);
                    ps.setLong(2, maxId);
                })
                .rowMapper((rs, rowNum) ->
                        new OrderRow(
                                rs.getLong("id"),
                                rs.getBigDecimal("amount")))
                .saveState(true)
                .build();
    }

    @Bean
    public JdbcBatchItemWriter<OrderRow> ordersWriter(
            DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<OrderRow>()
                .dataSource(dataSource)
                .sql("""
                    INSERT INTO processed_orders(id, amount)
                    VALUES (:id, :amount)
                    ON CONFLICT (id)
                    DO UPDATE SET amount = EXCLUDED.amount
                    """)
                .itemSqlParameterSourceProvider(item ->
                        new MapSqlParameterSource()
                                .addValue("id", item.id())
                                .addValue("amount", item.amount()))
                .build();
    }
}
~~~

**Những quyết định thiết kế trong ví dụ:**

- `orderIdPartitioner` chia **không gian ID**, không chia đều số bản ghi. Khi ID bị khuyết hoặc phân bố lệch, số dòng từng partition có thể chênh lệch lớn. Công thức giả định dải ID nằm trong phạm vi không gây tràn số nguyên `long`; với khóa cực trị hoặc nguồn rất lớn nên dùng phép tính có kiểm soát tràn.
- `ExecutionContext` chứa `minId` và `maxId` theo từng partition. Những giá trị này được Spring Batch gắn vào `StepExecution` và có thể được lưu trong JobRepository để phục vụ restart.
- `@StepScope` tạo reader riêng cho mỗi `StepExecution` và cho phép resolve `stepExecutionContext` lúc worker bắt đầu chạy. Trả về kiểu cụ thể `JdbcCursorItemReader` giúp Spring Batch nhận diện được giao diện `ItemStream` để gọi `open/update/close` và lưu checkpoint.
- Câu `ORDER BY id` tạo thứ tự đọc ổn định; mỗi khoảng dùng điều kiện `BETWEEN` bao gồm cả hai đầu, và các khoảng được tạo **không giao nhau**.
- `chunk(100, transactionManager)` commit theo chunk 100 item, tạo ranh giới checkpoint; kích thước này cần đo lại theo độ trễ DB, kích thước record và số worker.
- Writer dùng upsert theo khóa `id` (cú pháp PostgreSQL) để việc thực thi lại một chunk không gây bản ghi trùng. Với hệ quản trị khác cần thay cú pháp và chiến lược idempotency cho phù hợp.
- Bean executor có tối đa **4 luồng chạy đồng thời**, dù `gridSize` là 8. Các partition còn lại chờ trong queue. Thread pool không nên vượt quá sức chịu của kết nối DB, CPU và I/O.

Nếu ứng dụng có thêm bean `Step`, `Partitioner` hoặc `TaskExecutor`, `@Qualifier` giúp Java config không bị lỗi tiêm dependency mơ hồ.

## 3. Điều gì xảy ra khi job chạy?

Với ID liên tục từ 1 đến 1.000, partitioner nhận `gridSize=8`, tính `width=125` và trả về:

| Partition | `minId` | `maxId` | Worker đọc |
|---|---:|---:|---|
| `part0` | 1 | 125 | `1..125` |
| `part1` | 126 | 250 | `126..250` |
| `part2` | 251 | 375 | `251..375` |
| `part3` | 376 | 500 | `376..500` |
| `part4` | 501 | 625 | `501..625` |
| `part5` | 626 | 750 | `626..750` |
| `part6` | 751 | 875 | `751..875` |
| `part7` | 876 | 1000 | `876..1000` |

Spring Batch tạo các `StepExecution` tương ứng; executor có thể xử lý tối đa bốn worker cùng lúc. Thứ tự hoàn tất của các partition không nhất thiết theo thứ tự ID. Khi toàn bộ worker hoàn thành thành công, manager step có thể hoàn thành; nếu partition lỗi, job thường báo thất bại theo kết quả tổng hợp.

Ví dụ có thể bắt đầu bằng pipeline chỉ gồm reader và writer, sau đó thêm `ItemProcessor<OrderRow, ProcessedOrder>` để chuẩn hóa hoặc tính toán. Nếu processor lưu bộ đếm, cache mutable hay trạng thái tạm, phải bảo đảm không chia sẻ state thiếu đồng bộ giữa các worker. Trạng thái dùng riêng trong từng partition nên đặt trong bean có scope phù hợp.

## 4. Chọn `gridSize` và số luồng bằng số liệu

Một cấu hình có tám partition và bốn worker thường có ích hơn tám luồng nếu DB chỉ chịu được khoảng bốn truy vấn dài hoặc bốn chuỗi ghi đồng thời. Các thông số cần điều chỉnh độc lập:

| Tham số | Tác động | Điều cần đo |
|---|---|---|
| `gridSize` | Số đơn vị công việc mà partitioner được yêu cầu tạo | Độ lệch về số dòng, worker chạy lâu nhất, thời gian lập kế hoạch |
| `corePoolSize/maxPoolSize` | Số partition thực thi cùng lúc | CPU, lưu lượng I/O, wait time của DB |
| `queueCapacity` | Số tác vụ chờ trong executor | Áp lực bộ nhớ, khả năng backpressure, tác vụ bị từ chối |
| `chunkSize` | Số item mỗi lần commit | Thời gian transaction, lock, rollback, throughput |
| Pool kết nối JDBC | Số kết nối dùng được cho reader, writer và metadata | Active/idle/waiting connections, timeout |

Ví dụ, bốn worker dùng `JdbcCursorItemReader` có thể giữ nhiều kết nối nguồn mở trong lúc đọc; writer và JobRepository còn cần truy cập DB. Vì vậy, `maximumPoolSize=4` **không hàm ý** cấu hình JDBC pool bằng bốn kết nối là đủ. Cần đo nhu cầu thật và để dự phòng hợp lý cho metadata/transaction.

Cách thử hiệu năng có kiểm soát: chạy cùng một bộ dữ liệu với 1, 2 rồi 4 worker; ghi lại tổng thời gian job, throughput (items/giây), CPU, pool wait, thời gian SQL và thời lượng partition chậm nhất. Nếu tăng worker khiến throughput đứng yên hoặc giảm, nút thắt nhiều khả năng nằm ở DB, lock, network, nguồn dữ liệu hoặc overhead ghi metadata thay vì số luồng.

## 5. Thread safety, tính độc lập và restart

**Partitioning khác multi-threaded step.** Ở multi-threaded step, nhiều luồng có thể tham gia xử lý trong cùng một `StepExecution`; ở partitioning, mỗi partition có `StepExecution` và context riêng. Tuy vậy, các bean singleton được tham chiếu bởi worker vẫn có thể dùng chung giữa các luồng. Đặc biệt:

- Đặt reader có cursor, vị trí đọc hoặc bộ đếm mutable trong `@StepScope`, và không ghi dữ liệu của partition vào biến `static`.
- Processor/writer singleton chỉ nên chứa cấu hình bất biến hoặc tài nguyên hỗ trợ đồng thời an toàn. Không dùng một `List`/`HashMap` mutable không đồng bộ để ghi nhận trạng thái qua nhiều worker.
- Chia partition thành các miền xử lý **không giao nhau**. Nếu hai worker cùng ghi vào một khóa, phải có cơ chế giao dịch, locking hoặc giải quyết xung đột rõ ràng.
- Giữ tên partition ổn định (`part0`, `part1`, ...) và cặp giới hạn dữ liệu ổn định giữa các lần restart. Nếu nguồn liên tục được thêm/xóa, hãy dùng snapshot, watermark/cutoff cố định qua JobParameters hoặc tập khóa đã chốt.
- Chạy lại một `JobInstance` để restart cần dùng đúng identifying JobParameters của lần chạy lỗi; đổi identifying parameters thường tạo job instance mới và không kế thừa trạng thái chưa hoàn thành. Có thể dùng `JobOperator.restart(executionId)` theo cấu hình ứng dụng.

Giả sử `part2` thất bại sau khi ba chunk đã commit. Metadata của worker đó lưu trạng thái đọc ở checkpoint gần nhất; các worker `COMPLETED` không nhất thiết phải chạy lại khi restart đúng job instance. Phần đang lỗi có thể được chạy lại từ checkpoint, tùy reader/writer và cách JobRepository lưu trạng thái. **Không nên xem restart là cơ chế chống trùng dữ liệu:** lỗi hoặc tác động bên ngoài transaction vẫn có thể đòi hỏi writer idempotent như upsert, khóa duy nhất hoặc kiểm soát nghiệp vụ riêng.

Giới hạn của ví dụ: `MIN/MAX(id)` tính mỗi lần partitioner được gọi, và SQL đọc không có điều kiện cutoff. Do đó ví dụ giả định bảng nguồn ổn định trong khi chạy và restart. Nếu nguồn luôn thay đổi, phải cố định phạm vi của lần chạy trước khi chia partition, đồng thời dùng cùng điều kiện lọc trong partitioner và reader. Đối với dữ liệu có phân bố ID không đều, có thể chia theo hash, vùng thời gian, tenant hoặc danh sách khóa đã định sẵn; vẫn phải tránh trùng và bỏ sót.

## 6. Vận hành, giám sát và xử lý lỗi

Khi theo dõi job, xem `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` và execution context của từng partition trong JobRepository (hoặc công cụ quan sát tương ứng). `readCount`, `writeCount`, `filterCount`, `skipCount`, `rollbackCount` và `exitStatus` của **worker executions** giúp xác định vùng ID bị chậm hoặc hỏng; đừng chỉ nhìn vào manager step.

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Một partition chạy lâu hơn hẳn | Dải ID lệch dữ liệu, SQL chưa có index phù hợp | Kiểm tra execution plan, đo số dòng từng vùng, đổi thuật toán chia |
| Nhiều worker nhưng throughput giảm | DB bão hòa, tranh chấp lock, pool kết nối thiếu | Giảm concurrency, tăng hiệu quả SQL/batch write, kiểm tra connection wait |
| `minId`/`maxId` không được resolve | Reader chưa có `@StepScope` hoặc key context sai | Kiểm tra tên key, bean scope và StepExecution thực tế |
| Reader lỗi khi chạy đồng thời | Reader mutable bị chia sẻ, giữ cursor dùng chung | Tách instance theo step, tránh mutable singleton không an toàn |
| Restart có dòng thiếu/trùng | Đổi phạm vi đọc, checkpoint không ổn định, side effect ngoài transaction | Chốt snapshot/cutoff, dùng sort key ổn định và writer idempotent |
| Partition thất bại liên tục | SQL timeout, dữ liệu bẩn, transaction quá dài | Phân loại lỗi retryable, thiết lập retry/skip có giới hạn, giảm chunk |

`retry` và `skip` được cấu hình tại worker step cho lỗi phù hợp với nghiệp vụ, chẳng hạn bằng `.faultTolerant().retry(...).retryLimit(...)` trên chunk step builder. Chỉ retry lỗi có khả năng tạm thời, ví dụ deadlock/timeout; không nên retry vô hạn dữ liệu sai định dạng. Restart sẽ sử dụng JobRepository nên repository phải bền vững, không bị xóa metadata tùy tiện.

### Kiểm thử tối thiểu trước khi tăng tải

1. Nạp 1.000 dòng có ID liên tiếp, chạy job với `gridSize=8` và pool bốn luồng; đối chiếu `COUNT(*)` của bảng đích với bảng nguồn, xác nhận mọi `id` xuất hiện đúng một lần.
2. Thử ID bị khuyết, ID không bắt đầu từ 1 và bảng rỗng; không được phát sinh bản ghi ngoài phạm vi. Kiểm tra trường hợp partition ít dòng hơn số luồng.
3. Cố ý làm một partition lỗi sau vài chunk, restart **cùng JobInstance** và xác minh đủ dữ liệu, không lặp tác dụng phụ.
4. Kiểm tra số kết nối đang hoạt động và thời gian chờ của connection pool trong lúc bốn worker cùng chạy.
5. Dùng bộ dữ liệu đủ lớn để so sánh 1, 2, 4 worker; giữ cấu hình DB và khối lượng đầu vào như nhau để so sánh có ý nghĩa.

## 7. Khi nào nên chuyển sang mô hình khác?

Local partitioning là lựa chọn tốt khi có cách chia dữ liệu rõ ràng và một JVM còn đủ CPU, RAM, kết nối và băng thông. Nếu một host không còn đủ tài nguyên, có thể giữ ý tưởng **manager + partition context + worker** nhưng dùng remote partitioning: manager gửi yêu cầu qua middleware, các JVM worker nhận và thực thi; khi đó cần cấu hình hạ tầng nhắn tin, tương quan kết quả, timeout, retry, giám sát và triển khai phức tạp hơn.

Nếu công việc gồm **những giai đoạn độc lập**, dùng parallel flows/steps có thể dễ hiểu hơn chia cùng một tập dữ liệu. Nếu chỉ cần vài tác vụ xử lý song song trên các item và có thể bảo đảm thread safety, multi-threaded step có thể đơn giản hơn. Quyết định nên dựa trên cách tách dữ liệu, yêu cầu restart và nút thắt đo được.

**Điểm cần ghi nhớ:** `StepBuilder.partition(...)` là nơi ghép **partitioner**, **worker step**, **grid size** và **cơ chế thực thi** thành manager step. Hiệu quả và độ tin cậy đến từ ranh giới dữ liệu rõ ràng, tài nguyên đủ, scope đúng, checkpoint ổn định, writer idempotent và khả năng quan sát từng partition.
