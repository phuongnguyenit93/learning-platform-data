# Worker nhận input qua ExecutionContext

## Mục tiêu bài học

Trong một job Spring Batch dùng **partitioning**, manager cần chuyển cho từng worker thông tin về **phần dữ liệu mà worker chịu trách nhiệm xử lý**. Ví dụ: worker A đọc đơn hàng có ID từ 1 đến 250.000, worker B đọc từ 250.001 đến 500.000. Một cách chuẩn để truyền thông tin ấy là dùng **ExecutionContext gắn với StepExecution của từng partition**.

Bài học thuộc chương **Thiết kế worker** của module **SPRING_BATCH_SCALING_OPERATIONS**. Trọng tâm là cách truyền input giữa manager và worker khi mở rộng Spring Batch bằng local partitioning hoặc remote partitioning, đồng thời giữ khả năng theo dõi, retry và restart khi workload dữ liệu lớn.

Học xong bài này, bạn có thể:

- Phân biệt JobParameters, JobExecution ExecutionContext và StepExecution ExecutionContext; biết đối tượng nào giữ input riêng cho từng worker.
- Viết Partitioner tạo ExecutionContext với các giá trị định tuyến dữ liệu rõ ràng và không chồng lấn.
- Dùng **@StepScope** cùng biểu thức **stepExecutionContext** để inject input vào reader, processor hoặc tasklet của worker.
- Giải thích ExecutionContext đến worker như thế nào trong local partitioning và remote partitioning.
- Thiết kế input ổn định qua restart, kiểm tra hợp lệ, quan sát được lỗi và tránh bỏ sót/ghi trùng dữ liệu.

## 1. ExecutionContext giải quyết vấn đề gì?

Giả sử một job xử lý 10 triệu đơn hàng. Nếu có bốn worker mà tất cả đều chạy câu lệnh:

~~~sql
SELECT id, amount
FROM orders
ORDER BY id;
~~~

thì cả bốn worker có thể cùng đọc toàn bộ 10 triệu dòng. Tăng worker khi đó chỉ làm tăng tải database và nguy cơ ghi trùng.

Thay vào đó, manager chia tập dữ liệu thành bốn phạm vi độc lập. Mỗi worker nhận một **hợp đồng input** mô tả phạm vi của mình:

| Worker | Input từ manager | Dữ liệu được phép đọc |
| --- | --- | --- |
| worker-0 | minIdInclusive=1; maxIdExclusive=2500001 | ID từ 1 đến dưới 2.500.001 |
| worker-1 | minIdInclusive=2500001; maxIdExclusive=5000001 | ID từ 2.500.001 đến dưới 5.000.001 |
| worker-2 | minIdInclusive=5000001; maxIdExclusive=7500001 | ID từ 5.000.001 đến dưới 7.500.001 |
| worker-3 | minIdInclusive=7500001; maxIdExclusive=10000001 | ID từ 7.500.001 đến dưới 10.000.001 |

Các con số chỉ là ví dụ; bảng thực tế có thể có khoảng trống ID. Quy tắc **bao gồm cận dưới, loại trừ cận trên** giúp các khoảng không chồng lấn tại ranh giới.

Trong Spring Batch, manager dùng một **Partitioner** để tạo ánh xạ từ **tên partition** đến **ExecutionContext**. Framework gắn mỗi context đó vào StepExecution tương ứng. Khi worker thực thi step, nó đọc context của **chính StepExecution hiện tại**, từ đó dựng reader với điều kiện lọc phù hợp.

~~~mermaid
flowchart TB
    J[JobExecution] --> M[Manager step]
    M --> P[Partitioner]
    P --> A["partition-0: ExecutionContext<br/>minId=1, maxId=2500001"]
    P --> B["partition-1: ExecutionContext<br/>minId=2500001, maxId=5000001"]
    P --> C["partition-2: ExecutionContext<br/>minId=5000001, maxId=7500001"]
    A --> W1["Worker StepExecution 0<br/>Reader theo range 0"]
    B --> W2["Worker StepExecution 1<br/>Reader theo range 1"]
    C --> W3["Worker StepExecution 2<br/>Reader theo range 2"]
    W1 --> DB[(Nguồn dữ liệu)]
    W2 --> DB
    W3 --> DB
~~~

**Ý chính:** ExecutionContext là **túi dữ liệu trạng thái theo lần thực thi** do Spring Batch quản lý, không phải một request HTTP hoặc một message tự do. Khi dùng partitioning, phần input do Partitioner tạo trở thành dữ liệu có thể truy xuất qua StepExecution của worker.

## 2. Chọn đúng nơi lưu input: JobParameters hay ExecutionContext?

Spring Batch có nhiều nơi chứa giá trị khiến người mới dễ nhầm:

| Cơ chế | Phạm vi | Dùng để làm gì? | Ví dụ |
| --- | --- | --- | --- |
| **JobParameters** | Đầu vào khi khởi chạy job; các giá trị được lưu cùng job execution/instance | Cấu hình chung của lần chạy, xác định JobInstance qua các tham số identifying | businessDate, sourceSystem |
| **JobExecution ExecutionContext** | Trạng thái gắn với một JobExecution | Thông tin trạng thái dùng ở cấp job, chuyển giao giữa các step theo thiết kế | highWatermark đã chốt |
| **StepExecution ExecutionContext** | Trạng thái gắn với **một lần thực thi step** | Input và checkpoint **riêng** của từng partition/worker | minIdInclusive, maxIdExclusive, fileName, reader.read.count |

Điểm khác biệt quan trọng:

1. **JobParameters** nên được xem là cấu hình của lần chạy. Chúng không tự tạo các giá trị khác nhau cho từng worker trong cùng một job.
2. **JobExecution ExecutionContext** là dữ liệu trạng thái cấp job; nếu nhiều worker cùng cập nhật các key chung thì khó kiểm soát tính nhất quán. Tránh dùng nó như vùng ghi chung đồng thời cho các partition.
3. **StepExecution ExecutionContext** đi cùng định danh StepExecution của partition, nên phù hợp để chuyển input riêng cho worker và lưu checkpoint của reader/step.

Ví dụ một job có tham số chung **businessDate=2026-11-25** nhưng bốn partition có các cặp **minIdInclusive/maxIdExclusive** khác nhau. Tất cả worker dùng chung businessDate; mỗi worker chỉ đọc phạm vi ID của mình.

### Input ban đầu và trạng thái tiến độ trong cùng context

ExecutionContext có thể đồng thời chứa:

- **Input phân công từ manager:** minIdInclusive, maxIdExclusive, tenantId, inputFile.
- **Trạng thái tiến độ do reader hoặc step cập nhật:** vị trí cursor, số item đã đọc, checkpoint của ItemStream.

Không nên thay đổi các key định tuyến sau khi worker bắt đầu chạy. Nếu cần ghi tiến độ, dùng **key riêng** để tránh ghi đè input. Các giá trị mới hoặc thay đổi trạng thái được Spring Batch lưu tại những thời điểm quản lý checkpoint/giao dịch phù hợp; không nên giả định mỗi thao tác put đều được ghi xuống database ngay tức thì.

## 3. Hợp đồng input giữa manager và worker

ExecutionContext là một cấu trúc key/value. Chất lượng thiết kế phụ thuộc vào **ý nghĩa và tính ổn định của các key** hơn là số lượng key.

Ví dụ hợp đồng input cho worker đọc đơn hàng:

~~~yaml
# Minh họa nội dung logic, không phải tệp cấu hình Spring Boot
minIdInclusive: 1
maxIdExclusive: 2500001
sourceName: orders
snapshotToken: "batch-2026-11-25"
~~~

Quy ước nên áp dụng:

- **Đặt tên tường minh:** minIdInclusive và maxIdExclusive dễ kiểm tra hơn start/end không rõ bao gồm cận nào.
- **Dùng kiểu đơn giản:** String, long, int, boolean và dữ liệu nhỏ phù hợp với cơ chế lưu/serialization đã cấu hình. Có thể dùng putLong, putString để tránh nhầm kiểu.
- **Giữ context nhỏ:** chỉ truyền khóa hoặc tiêu chí đọc dữ liệu, không nhét hàng triệu bản ghi hoặc các đối tượng graph lớn vào ExecutionContext.
- **Không truyền bí mật:** không đặt password, token truy cập hoặc dữ liệu nhạy cảm dạng thô vào context; metadata của job có thể được lưu bền vững và người vận hành có thể đọc được.
- **Có ngữ nghĩa bất biến:** một key đã cấp cho một partition không nên đổi từ phạm vi A sang phạm vi B trong lần restart.
- **Kiểm tra đầu vào ở worker:** context thiếu key, sai kiểu hoặc cận dưới lớn hơn/cân bằng cận trên phải thất bại rõ ràng.

Với remote partitioning, các JVM có thể khác phiên bản triển khai. Việc dùng các giá trị đơn giản còn giảm rủi ro không tương thích khi serialize/deserialize ExecutionContext. Nếu cần kiểu phức tạp, phải kiểm chứng serializer và class tương thích ở cả manager lẫn worker.

## 4. Manager tạo ExecutionContext bằng Partitioner

Một **Partitioner** nhận số partition mong muốn (gridSize) và trả về **Map<String, ExecutionContext>**. Mỗi entry là input của một worker step execution.

Đoạn mã sau minh họa cách chia miền ID **[1, 1.000.001)** cho nhiều partition. Đây là phạm vi cố định để dễ hiểu; trong production, cận trên nên được chốt một cách có kiểm soát cho cả lần chạy.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderPartitionConfig {

    @Bean
    public Partitioner ordersPartitioner() {
        return gridSize -> {
            long minIdInclusive = 1L;
            long maxIdExclusive = 1_000_001L;

            int requestedPartitions = Math.max(1, gridSize);
            long totalIds = maxIdExclusive - minIdInclusive;
            long rangeSize =
                    (totalIds + requestedPartitions - 1) / requestedPartitions;

            Map<String, ExecutionContext> result = new LinkedHashMap<>();
            int ordinal = 0;

            for (long start = minIdInclusive;
                 start < maxIdExclusive;
                 start += rangeSize) {

                long end = Math.min(start + rangeSize, maxIdExclusive);

                ExecutionContext input = new ExecutionContext();
                input.putLong("minIdInclusive", start);
                input.putLong("maxIdExclusive", end);
                input.putString("sourceName", "orders");

                result.put("partition-" + ordinal++, input);
            }

            return result;
        };
    }
}
~~~

Giả sử gridSize bằng 4. Kết quả logic là:

| Tên partition | minIdInclusive | maxIdExclusive |
| --- | ---: | ---: |
| partition-0 | 1 | 250001 |
| partition-1 | 250001 | 500001 |
| partition-2 | 500001 | 750001 |
| partition-3 | 750001 | 1000001 |

Các partition không bỏ sót hay đọc trùng ID trong phạm vi đã phân công. Tên **partition-0**, **partition-1**... và khóa trong context cần được giữ **ổn định giữa các lần chạy lại cùng JobInstance**. Nếu thay đổi cách chia hoặc gridSize giữa restart, cần phân tích kỹ trạng thái StepExecution đã lưu; không coi kết quả mới là tương đương với partition cũ.

**Đối với dữ liệu đang phát sinh liên tục:** đọc giá trị MAX(id) ở mỗi lần Partitioner chạy có thể tạo cận khác nhau khi restart. Một thiết kế ổn định là chốt high-watermark khi bắt đầu xử lý, lưu làm dữ liệu điều khiển của job và dùng đúng mốc đó khi tạo lại partition. Nếu dữ liệu có thể bị sửa/xóa trong lúc chạy, chỉ chốt MAX(id) có thể chưa đủ để bảo đảm snapshot nhất quán; cần xác định chính sách snapshot hoặc xử lý thay đổi.

**Đối với phân vùng không đều:** chia khoảng ID bằng nhau không đồng nghĩa số bản ghi bằng nhau. Có thể chia theo tenant, phân vùng vật lý, ngày, hoặc thống kê số hàng để cân bằng tải. Mỗi cách vẫn phải giữ nguyên nguyên tắc mỗi record chỉ thuộc một partition trong phạm vi xử lý.

## 5. Worker nhận input bằng @StepScope và stepExecutionContext

Spring Batch có cơ chế **late binding**: chỉ khi StepExecution chuẩn bị chạy, framework mới có context cụ thể để cung cấp cho bean được đánh dấu **@StepScope**. Với reader của worker, ta có thể nhận từng cận của partition thông qua Spring Expression Language (SpEL).

Ví dụ Spring Batch 5.x, sử dụng JDBC reader. Các import và lớp dữ liệu bên dưới minh họa cấu hình; mã giả định nguồn dữ liệu có bảng orders với cột id kiểu số và amount kiểu decimal.

~~~java
import java.math.BigDecimal;

import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderReaderConfig {

    public record OrderRow(long id, BigDecimal amount) {}

    @Bean
    @StepScope
    public JdbcCursorItemReader<OrderRow> orderReader(
            DataSource dataSource,
            @Value("#{stepExecutionContext['minIdInclusive']}")
            Long minIdInclusive,
            @Value("#{stepExecutionContext['maxIdExclusive']}")
            Long maxIdExclusive) {

        if (minIdInclusive == null || maxIdExclusive == null) {
            throw new IllegalArgumentException(
                    "Missing partition ID bounds in StepExecutionContext");
        }
        if (minIdInclusive >= maxIdExclusive) {
            throw new IllegalArgumentException(
                    "Invalid partition range: " + minIdInclusive
                    + " .. " + maxIdExclusive);
        }

        return new JdbcCursorItemReaderBuilder<OrderRow>()
                .name("orderReader")
                .dataSource(dataSource)
                .sql("""
                     SELECT id, amount
                     FROM orders
                     WHERE id >= ? AND id < ?
                     ORDER BY id
                     """)
                .preparedStatementSetter(ps -> {
                    ps.setLong(1, minIdInclusive);
                    ps.setLong(2, maxIdExclusive);
                })
                .rowMapper((rs, rowNum) ->
                        new OrderRow(
                                rs.getLong("id"),
                                rs.getBigDecimal("amount")))
                .saveState(true)
                .build();
    }
}
~~~

Các điểm cần hiểu:

- **@StepScope** khiến Spring tạo bean thực theo ngữ cảnh StepExecution đang chạy. Mỗi partition có thể có reader riêng cùng cấu hình code nhưng khác giá trị input.
- **stepExecutionContext** trong biểu thức SpEL lấy dữ liệu từ **StepExecution context hiện tại**, không lấy từ một Map toàn cục.
- Hai tên **minIdInclusive** và **maxIdExclusive** phải khớp chính xác với key được Partitioner ghi.
- **@Value** được giải quyết khi bean scoped được khởi tạo trong step. Nếu tự tạo reader ngoài vòng đời do Spring Batch quản lý hoặc bỏ @StepScope, late binding có thể không hoạt động đúng.
- **saveState(true)** cho phép reader ghi trạng thái phục vụ restart theo cơ chế ItemStream. Việc restart chính xác còn phụ thuộc tính ổn định của tập dữ liệu và cách reader truy cập nguồn, không chỉ phụ thuộc flag này.
- **name("orderReader")** cung cấp định danh cho state của reader; state reader nằm trong ExecutionContext của StepExecution tương ứng.

Câu lệnh SQL dùng placeholder nên giới hạn khoảng ID được bind thành tham số, tránh ghép trực tiếp input chưa kiểm chứng vào chuỗi truy vấn. Cần có index phù hợp trên **orders.id** và kiểm chứng kế hoạch thực thi trên dữ liệu thật.

### Khi nào nên dùng @StepScope?

Nên dùng với thành phần có cấu hình **thay đổi theo từng StepExecution**, chẳng hạn:

- Reader nhận khoảng ID hoặc tên file.
- Processor nhận cờ xử lý riêng theo partition.
- Tasklet nhận tenantId, shardName hoặc ngày dữ liệu.
- Writer được cấu hình destination tương ứng với partition khi nghiệp vụ yêu cầu.

Không cần đánh dấu toàn bộ ứng dụng là @StepScope. Các component stateless và dùng chung an toàn có thể là singleton. Đặc biệt, @StepScope giúp tách instance reader theo StepExecution, nhưng **không tự làm thread-safe mọi processor/writer singleton**, connection hay thư viện mà chúng chia sẻ.

## 6. Gắn reader vào worker step và manager step

Reader ở phần trước chỉ có tác dụng khi được gắn vào một Step thực sự. Ví dụ local partitioning dưới đây cho thấy **worker step** và **manager step** là hai vai trò khác nhau.

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

// Đặt các bean sau trong lớp @Configuration.
@Bean
public Step workerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<OrderReaderConfig.OrderRow> orderReader,
        ItemWriter<OrderReaderConfig.OrderRow> orderWriter) {

    return new StepBuilder("workerStep", jobRepository)
            .<OrderReaderConfig.OrderRow, OrderReaderConfig.OrderRow>
                    chunk(500, transactionManager)
            .reader(orderReader)
            .writer(orderWriter)
            .build();
}

@Bean
public Step managerStep(
        JobRepository jobRepository,
        Partitioner ordersPartitioner,
        @Qualifier("workerStep") Step workerStep,
        @Qualifier("partitionTaskExecutor") TaskExecutor taskExecutor) {

    return new StepBuilder("managerStep", jobRepository)
            .partitioner("workerStep", ordersPartitioner)
            .step(workerStep)
            .gridSize(4)
            .taskExecutor(taskExecutor)
            .build();
}
~~~

Ví dụ trên **giả định** ứng dụng đã khai báo bean **orderWriter** xử lý ghi dữ liệu, bean **partitionTaskExecutor** với số thread được giới hạn, và bean Spring Batch hạ tầng. Đây là đoạn minh họa các điểm nối của cấu hình; chỉ khi bổ sung writer, executor và job thì mới thành ứng dụng chạy hoàn chỉnh.

Ở local partitioning, **TaskExecutor** cho phép manager chạy nhiều worker StepExecution trên các thread trong cùng JVM. Dù có nhiều thread, từng StepExecution vẫn có ExecutionContext riêng; @StepScope đọc đúng context tương ứng.

Ở remote partitioning, manager không giao việc bằng TaskExecutor trong cùng JVM mà dùng một **PartitionHandler/Integration flow** phù hợp để dispatch phần việc sang các worker JVM. **Worker vẫn đọc StepExecution ExecutionContext theo cùng nguyên tắc**, nhưng cần thiết lập bộ phận nhận request và thực thi step trong tiến trình worker. Không thể chỉ tăng số replica hoặc thêm message broker rồi kỳ vọng Spring Batch tự động cấp partition.

### Ví dụ writer có tính lặp lại an toàn

Nếu kết quả mỗi order được lưu theo khóa duy nhất, writer có thể dùng upsert, ví dụ với PostgreSQL:

~~~sql
INSERT INTO order_summary (order_id, total_amount)
VALUES (:orderId, :amount)
ON CONFLICT (order_id)
DO UPDATE SET total_amount = EXCLUDED.total_amount;
~~~

Cần có ràng buộc **UNIQUE** hoặc **PRIMARY KEY** trên order_id và đảm bảo việc ghi đè có đúng ngữ nghĩa nghiệp vụ. Upsert theo order_id không đủ cho tác vụ gửi email, ghi sổ kế toán dạng cộng dồn hoặc gọi hệ thống bên ngoài; các tác vụ đó cần chiến lược idempotency riêng.

## 7. Input đi tới worker như thế nào?

### 7.1. Local partitioning

Luồng thực thi có thể hiểu theo thứ tự:

1. Manager step gọi Partitioner để nhận map partition name → ExecutionContext.
2. Spring Batch tạo hoặc ánh xạ **worker StepExecution** theo các partition và lưu metadata trong JobRepository.
3. PartitionHandler giao các worker StepExecution tới TaskExecutor.
4. Khi worker step bắt đầu, bean @StepScope được khởi tạo trong context của StepExecution tương ứng.
5. Reader nhận min/max từ context, đọc đúng khoảng dữ liệu và ghi checkpoint trong context của step.
6. Manager nhận kết quả từng partition để tổng hợp tình trạng của manager step.

### 7.2. Remote partitioning

~~~mermaid
sequenceDiagram
    participant M as Manager JVM
    participant R as JobRepository
    participant Q as Message middleware
    participant W as Worker JVM
    participant D as Data source

    M->>M: Partitioner tạo input theo partition
    M->>R: Lưu worker StepExecution và ExecutionContext
    M->>Q: Dispatch yêu cầu thực thi partition
    Q->>W: Worker nhận yêu cầu / StepExecution ID
    W->>R: Load metadata và StepExecutionContext
    W->>W: Tạo bean @StepScope, validate input
    W->>D: SELECT theo min/max được giao
    W->>R: Checkpoint, cập nhật StepExecution
    W-->>M: Kết quả/trạng thái theo giao thức điều phối
~~~

Sơ đồ biểu diễn **mô hình remote partitioning có JobRepository được chia sẻ**, thường gặp trong Spring Batch Integration. Chi tiết payload message, kênh phản hồi và cập nhật trạng thái tùy cấu hình/phiên bản. Điều quan trọng là worker cần truy xuất **StepExecution đã được tạo cho partition**, không tự đoán input từ số thứ tự instance hoặc tên pod.

Trong remote partitioning:

- Manager là nguồn cấp **định danh partition và input ban đầu**.
- JobRepository lưu **StepExecution và context** để worker tương ứng có thể lấy đúng thông tin.
- Message/transport giúp yêu cầu worker thực thi; nó không thay thế hoàn toàn metadata và cơ chế restart.
- Worker có thể chạy ở JVM/pod/máy khác; **cùng một định nghĩa step** có thể được triển khai ở nhiều worker, mỗi StepExecution mang input riêng.
- Cần thống nhất tên step, key input, kiểu dữ liệu, cách serialization, quyền truy cập JobRepository và phiên bản contract giữa manager/worker.

**Phân biệt với remote chunking:** remote chunking gửi các item hoặc chunk đã được manager đọc tới worker xử lý/ghi. Trong remote partitioning, worker nhận thông tin **về phần việc** rồi tự đọc nguồn. Việc inject StepExecutionContext để tạo reader đặc biệt quan trọng với remote partitioning.

## 8. Đọc context trong Tasklet hoặc StepExecutionListener

Không phải worker nào cũng là chunk-oriented reader. Có worker chạy tasklet, xuất file hoặc thực hiện một thao tác nghiệp vụ theo tenant. Vẫn có thể nhận input qua @StepScope:

~~~java
import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
public Tasklet tenantTasklet(
        @Value("#{stepExecutionContext['tenantId']}") String tenantId) {

    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException("Missing tenantId");
    }

    return (StepContribution contribution, ChunkContext chunkContext) -> {
        // Gọi dịch vụ nghiệp vụ xử lý tenantId tại đây.
        // Phải thiết kế thao tác lặp lại an toàn khi retry/restart.
        return RepeatStatus.FINISHED;
    };
}
~~~

Nếu cần đọc trực tiếp từ đối tượng **StepExecution**, có thể dùng một StepExecutionListener đã được đăng ký với step:

~~~java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.batch.item.ExecutionContext;

public class ValidatePartitionListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        ExecutionContext context = stepExecution.getExecutionContext();

        if (!context.containsKey("minIdInclusive")
                || !context.containsKey("maxIdExclusive")) {
            throw new IllegalArgumentException(
                    "Partition context missing required bounds");
        }

        long min = context.getLong("minIdInclusive");
        long max = context.getLong("maxIdExclusive");

        if (min >= max) {
            throw new IllegalArgumentException(
                    "Invalid partition bounds: " + min + " >= " + max);
        }
    }
}
~~~

Đăng ký listener trong cấu hình StepBuilder, ví dụ gọi **.listener(validatePartitionListener)** khi xây dựng worker step. Listener phù hợp khi muốn kiểm tra toàn bộ contract một lần trước khi xử lý. @StepScope thuận tiện hơn khi các giá trị phải được inject trực tiếp vào constructor hoặc phương thức @Bean tạo reader/processor/writer.

Không nên dùng biến static hoặc ThreadLocal tự quản lý để truyền input giữa manager và worker. Với remote partitioning, bộ nhớ hai JVM là độc lập; với local partitioning, thread pool tái sử dụng thread và rất dễ làm rò state từ partition này sang partition khác.

## 9. Thiết kế input có thể retry và restart

ExecutionContext hỗ trợ khôi phục trạng thái nhưng **không tự bảo đảm chính xác nghiệp vụ**. Phải phối hợp cách chia dữ liệu, checkpoint của reader, transaction và idempotency của writer.

### 9.1. Giữ định danh và ranh giới partition ổn định

Khi một partition thất bại và job được restart, Spring Batch cần biết partition nào hoàn thành và partition nào cần chạy lại. Nếu lần sau cùng một JobInstance được tạo với tên partition mới hoặc khoảng dữ liệu mới, metadata đã lưu có thể không còn phản ánh đúng phần việc trước đó.

Ví dụ không an toàn:

- Lần đầu: **partition-0 = ID [1, 1000)**.
- Lần restart: vì dữ liệu tăng, **partition-0 = ID [1, 2000)**.
- Worker có checkpoint cũ theo lần đọc trước, trong khi tập dữ liệu của partition đã đổi.

Vì vậy cần chốt snapshot/high-watermark và chiến lược đặt tên partition khi lập kế hoạch xử lý. Trường hợp cần thay đổi phạm vi, hãy cân nhắc khởi chạy **JobInstance mới** có tham số identifying rõ ràng thay vì thay input của execution cũ.

### 9.2. Giữ ranh giới dữ liệu độc lập với checkpoint

Hãy phân biệt:

| Dữ liệu | Ví dụ key | Ai tạo/cập nhật? | Có nên đổi khi restart? |
| --- | --- | --- | --- |
| Input phân công | minIdInclusive, maxIdExclusive | Partitioner/manager | Không, trong cùng lần xử lý logic |
| Checkpoint reader | Trạng thái đọc do ItemStream quản lý | Reader/Spring Batch | Được cập nhật qua checkpoint |
| Kết quả step | Read/write/skip counts, ExitStatus | Spring Batch | Cập nhật theo execution |
| Cấu hình job chung | businessDate trong JobParameters | Job launcher | Giữ ổn định khi restart cùng JobInstance |

Không dùng cùng key cho input nghiệp vụ và state nội bộ của reader. Reader có thể lưu số dòng đã đọc, nhưng số dòng chỉ có ý nghĩa khi query sắp xếp ổn định và tập dữ liệu không đổi ngoài dự kiến. Với dữ liệu thay đổi nhanh, cần đánh giá dùng khóa tiến độ, snapshot isolation hoặc cách đọc khác để tránh bỏ sót/lặp lại.

### 9.3. Chịu lỗi giữa commit và xác nhận

Trong một kiến trúc phân tán, worker có thể ghi kết quả xuống DB thành công nhưng chết trước khi báo về manager. Phần việc có thể được thử lại. Do đó:

- **Idempotent writer:** ghi lại cùng business key tạo cùng kết quả hợp lệ, không sinh bản ghi trùng.
- **Transaction boundary:** xác định thao tác nào commit cùng chunk và thao tác nào là side effect ngoài giao dịch.
- **Retry phân loại:** lỗi mạng tạm thời có thể retry; dữ liệu không hợp lệ nên được skip/fail theo chính sách, tránh lặp vô hạn.
- **Reconciliation:** đối chiếu số record và business key đầu vào/đầu ra thay vì chỉ nhìn JobExecution báo COMPLETED.

### 9.4. Lưu context bền vững và tương thích phiên bản

ExecutionContext được lưu nhờ hạ tầng JobRepository/serializer mà ứng dụng cấu hình. Với nhiều tiến trình, cần repository bền vững và được truy cập nhất quán bởi các thành phần cần chia sẻ StepExecution. Tránh dựa vào in-memory repository cho yêu cầu restart phân tán.

Nếu đổi tên key hoặc kiểu dữ liệu giữa hai phiên bản triển khai, worker cũ hoặc các execution đang restart có thể không đọc được context. Cần quản lý version của hợp đồng input, triển khai tương thích và kiểm tra các job chưa kết thúc trước khi nâng cấp.

## 10. Vấn đề thread safety và tài nguyên khi mỗi worker có input riêng

Mỗi worker có context riêng **không có nghĩa** mọi thành phần đều an toàn khi chạy đồng thời.

**Tài nguyên ở worker:**

- Một local partition có reader @StepScope riêng nhưng các reader vẫn dùng chung database và connection pool của JVM.
- Một remote worker JVM có pool kết nối riêng; tổng số pool trên toàn hệ thống phải được tính vào giới hạn DB.
- Processor/writer singleton có thể chia sẻ state mutable trong cùng JVM; không dựa vào @StepScope của reader để kết luận các bean khác thread-safe.
- Reader dựa trên JDBC cursor giữ tài nguyên kết nối trong khi đọc; số worker và chunk đồng thời phải phù hợp với cấu hình connection pool và transaction.

**Phân phối tải:** bốn partition có ID range rộng bằng nhau nhưng số record không đều sẽ khiến một worker xử lý lâu hơn những worker khác. Đo thời gian từng partition; cân nhắc tạo nhiều partition nhỏ hơn số worker, chia dựa trên ước tính số record, hoặc dùng shard key phù hợp.

**Giới hạn nguồn/đích:** nếu 8 worker cùng quét một bảng chưa có index thích hợp, việc dùng ExecutionContext đúng không giúp DB nhanh hơn. Thiết kế input và thiết kế năng lực xử lý phải đi cùng nhau.

## 11. Quan sát và chẩn đoán khi worker nhận input sai

Cần log đủ thông tin để tìm lỗi, nhưng tránh ghi dữ liệu nhạy cảm. Một bản ghi log hữu ích có thể chứa:

~~~text
jobExecutionId=8012
stepExecutionId=8040
stepName=workerStep:partition-2
workerId=orders-worker-03
minIdInclusive=500001
maxIdExclusive=750001
readCount=249310
writeCount=249310
status=COMPLETED
~~~

Các giá trị trên là ví dụ. Tên step thực tế thường mang định danh partition theo cơ chế partitioning được cấu hình. Với remote partitioning, nên có correlation ID trong message/log để liên kết yêu cầu dispatch với StepExecution và worker.

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| @Value inject ra null | Key không khớp tên do Partitioner tạo; context bị thiếu | Kiểm tra contract và các key ở StepExecution đã lưu |
| Không truy cập được stepExecutionContext | Bean tạo quá sớm hoặc không chạy trong StepScope | Đặt @StepScope đúng bean, để Spring Batch quản lý vòng đời step |
| Nhiều worker đọc cùng dữ liệu | Phạm vi min/max chồng lấn hoặc query không dùng phạm vi | Kiểm tra map partition và WHERE clause |
| Worker không nhận được partition | Sai tên step, dispatcher/worker chưa được cấu hình, message bị kẹt | Kiểm tra StepExecution ID, broker/channel và JobRepository |
| Worker restart đọc sai tập dữ liệu | Cận partition hoặc dữ liệu nguồn thay đổi; checkpoint không còn hợp lệ | Cố định high-watermark/snapshot, giữ partition name ổn định |
| Serialization/deserialization thất bại | Context chứa kiểu tùy biến/không tương thích giữa các JVM | Dùng kiểu đơn giản, đồng bộ serializer và phiên bản triển khai |
| Worker xử lý đúng nhưng manager báo lỗi | Worker commit xong, kết nối/ack về manager thất bại | Kiểm tra protocol timeout, metadata và idempotent writer |
| Throughput giảm khi tăng worker | DB, connection pool, I/O hoặc writer bị tranh chấp | Đo tải, hạ concurrency hoặc tối ưu nguồn/đích |

Một quy tắc vận hành hữu ích: **log định danh partition và khoảng input khi step bắt đầu**, sau đó log số lượng read/write, thời gian và lỗi khi kết thúc. Cách này cho phép xác nhận partition đã thực sự xử lý đúng phần việc mình được giao.

## 12. Tình huống thực tế: xử lý đơn hàng theo tenant

Hệ thống thương mại điện tử có 200 tenant. Mỗi tenant có số lượng đơn hàng khác nhau và dữ liệu không được trộn lẫn.

**Thiết kế đơn giản:** Partitioner tạo một context cho mỗi tenant:

~~~yaml
tenantId: "tenant-042"
businessDate: "2026-11-25"
~~~

Worker tạo reader theo input được inject:

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<OrderReaderConfig.OrderRow> tenantOrderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['tenantId']}") String tenantId,
        @Value("#{stepExecutionContext['businessDate']}") String businessDate) {

    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException("Missing tenantId");
    }
    if (businessDate == null || businessDate.isBlank()) {
        throw new IllegalArgumentException("Missing businessDate");
    }

    return new JdbcCursorItemReaderBuilder<OrderReaderConfig.OrderRow>()
            .name("tenantOrderReader")
            .dataSource(dataSource)
            .sql("""
                 SELECT id, amount
                 FROM orders
                 WHERE tenant_id = ?
                   AND business_date = ?
                 ORDER BY id
                 """)
            .preparedStatementSetter(ps -> {
                ps.setString(1, tenantId);
                ps.setDate(2, java.sql.Date.valueOf(businessDate));
            })
            .rowMapper((rs, rowNum) ->
                    new OrderReaderConfig.OrderRow(
                            rs.getLong("id"),
                            rs.getBigDecimal("amount")))
            .saveState(true)
            .build();
}
~~~

Giả định business_date là kiểu **DATE** và giá trị businessDate tuân theo định dạng ISO **yyyy-MM-dd**. Thực tế cần kiểm soát timezone/cutoff nghiệp vụ và chỉ mục phù hợp cho tenant_id, business_date, id.

Nếu một tenant có 5 triệu đơn hàng còn tenant khác chỉ có 2 nghìn, chia một partition mỗi tenant tạo lệch tải. Có thể mở rộng hợp đồng input thành **tenantId + minIdInclusive + maxIdExclusive**, giúp chia tenant lớn thành nhiều partition, trong khi tenant nhỏ giữ một partition.

Khi lựa chọn cấu hình:

1. Giữ **tenantId** như ranh giới dữ liệu bắt buộc; mọi query phải lọc theo tenant.
2. Chia tiếp ID/date khi một tenant lớn gây worker chạy quá lâu.
3. Đặt partition name ổn định, chẳng hạn **tenant-042-range-03**, với ranh giới cố định qua restart.
4. Chặn ghi trùng theo khóa nghiệp vụ gồm tenant và order ID khi miền khóa yêu cầu.
5. Theo dõi tiến độ theo partition để tìm tenant/worker bị chậm, tránh chỉ nhìn tổng throughput.

## 13. Những nhầm lẫn thường gặp

**“Mỗi worker có JobParameters khác nhau.”** Trong partitioning của cùng một job, các worker thường chia sẻ JobParameters cấp job. Input riêng theo partition được đặt trong **StepExecution ExecutionContext**.

**“Đặt @StepScope là framework sẽ tự chia dữ liệu.”** @StepScope chỉ giúp bean nhận giá trị khi StepExecution chạy. Partitioner và query vẫn phải định nghĩa phần dữ liệu riêng, không chồng lấn.

**“ExecutionContext là message gửi qua broker.”** Nó là trạng thái do Spring Batch quản lý. Trong remote partitioning, message thường có vai trò yêu cầu worker thực thi StepExecution; metadata/context cần được truy xuất qua cơ chế điều phối và JobRepository của kiến trúc đã cấu hình.

**“Có ExecutionContext thì restart chắc chắn không ghi trùng.”** Context giúp xác định phần việc và giữ checkpoint. Tính đúng khi retry/restart còn phụ thuộc nguồn dữ liệu ổn định, transaction, writer idempotent và chiến lược khôi phục.

**“Cứ gửi cả tập item vào ExecutionContext để worker dùng.”** Context là metadata nhỏ và trạng thái thực thi; đưa hàng triệu item vào sẽ làm nặng repository, serialization và restart. Nếu muốn chuyển item đã đọc qua message, cần nghiên cứu mô hình **remote chunking**.

**“Worker tự lấy ID lớn nhất lúc bắt đầu là được.”** Nếu mỗi worker lấy MAX(id) tại thời điểm khác nhau hoặc khi restart, các partition có thể không cùng một ảnh chụp dữ liệu. Manager cần định nghĩa phạm vi logic và mốc chốt nhất quán.

## 14. Checklist trước khi chạy production

- [ ] Partitioner tạo map partitionName → ExecutionContext với tên ổn định.
- [ ] Mỗi context có key và kiểu dữ liệu rõ ràng; worker kiểm tra đủ key.
- [ ] Ranh giới dữ liệu bao phủ đúng tập đầu vào, không chồng lấn và không bỏ sót.
- [ ] Mốc snapshot/high-watermark được giữ ổn định qua restart.
- [ ] Reader hoặc tasklet dùng @StepScope và truy cập đúng stepExecutionContext.
- [ ] Không chia sẻ reader mutable giữa các partition; các processor/writer dùng chung đã được đánh giá thread safety.
- [ ] JobRepository, transaction và serializer tương thích với kiến trúc local/remote.
- [ ] Writer hỗ trợ retry/restart an toàn theo business key và side effect thực tế.
- [ ] Số worker, gridSize, chunk size và connection pool được đo dưới tải đại diện.
- [ ] Có log/metric theo JobExecution ID, StepExecution ID và partition name.
- [ ] Đã thử dừng worker giữa chunk, chạy lại và đối soát số lượng/khóa dữ liệu đầu ra.

## 15. Câu hỏi tự kiểm tra

**1. Muốn mỗi worker đọc một khoảng ID khác nhau, nên đặt minId và maxId ở đâu?**

Ở **StepExecution ExecutionContext** do Partitioner cấp cho từng partition. Worker nhận bằng @StepScope và biểu thức stepExecutionContext, hoặc truy xuất từ StepExecution qua listener.

**2. Vì sao không truyền toàn bộ bản ghi cần xử lý trong ExecutionContext?**

ExecutionContext phục vụ metadata và trạng thái checkpoint, cần lưu/serialize và có thể được tải lại khi restart. Tập dữ liệu lớn nên để worker tự đọc từ nguồn theo phạm vi phân công trong remote partitioning; nếu truyền chunk item đã đọc thì đó là một mô hình phân tán khác.

**3. Có @StepScope rồi thì worker có tự an toàn khi chạy nhiều thread không?**

Không. @StepScope cho bean riêng theo StepExecution, nhưng các component hoặc tài nguyên dùng chung vẫn cần thread safety. Đồng thời, nhiều worker có thể gây nghẽn DB và tranh chấp giao dịch.

**4. Vì sao partition name và input cần ổn định qua restart?**

Spring Batch dùng metadata StepExecution để nhận biết phần việc đã hoàn thành/thất bại và điều phối khôi phục. Đổi ranh giới hoặc tên partition có thể làm checkpoint cũ không còn khớp với dữ liệu hiện tại.

**5. Khác biệt quan trọng giữa input của remote chunking và remote partitioning là gì?**

Trong remote chunking, manager đọc và gửi **các item/chunk** cho worker. Trong remote partitioning, manager chia **phạm vi công việc** bằng ExecutionContext để worker **tự đọc dữ liệu**.

---

**Ghi nhớ:** Worker nhận input qua ExecutionContext nghĩa là mỗi **StepExecution** có một hợp đồng dữ liệu rõ ràng, được manager cấp và được Spring Batch quản lý. Thiết kế tốt phải đáp ứng đồng thời ba điều: **đúng phần dữ liệu**, **nhận input đúng ngữ cảnh**, và **khôi phục an toàn khi lỗi**. Đó là nền tảng để mở rộng Spring Batch bằng partitioning từ một JVM sang nhiều tiến trình mà vẫn kiểm soát được dữ liệu lớn.
