# Late binding bằng ExecutionContext trong Spring Batch

## 1. Vì sao một bean batch cần được cấu hình muộn?

Giả sử job xử lý 10 triệu đơn hàng bằng partitioning. Manager chia dữ liệu thành nhiều khoảng ID, mỗi partition được giao cho một worker. Nếu tạo tất cả reader ngay khi Spring Boot khởi động, tại thời điểm ấy ứng dụng **chưa biết** reader sẽ xử lý khoảng ID nào, đang thuộc `StepExecution` nào và có phải tiếp tục từ checkpoint trước đó hay không.

**Late binding** giải quyết bài toán này: bean được khai báo lúc khởi động ứng dụng, nhưng một số giá trị cấu hình chỉ được xác định khi job/step thực sự chạy. Trong Spring Batch, cách phổ biến là kết hợp **`@StepScope`** hoặc **`@JobScope`** với Spring Expression Language (**SpEL**) để lấy dữ liệu từ `JobParameters`, `JobExecutionContext` hoặc `StepExecutionContext`.

Bài học thuộc chương **Step scope** của module `SPRING_BATCH_SCALING_OPERATIONS`, nơi tập trung mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và xử lý phân tán. Late binding giúp từng worker nhận đúng đầu vào, tránh chia sẻ trạng thái sai giữa các execution, đồng thời hỗ trợ checkpoint, retry/restart và vận hành khi số worker tăng.

Sau bài này, bạn sẽ có thể:

- Phân biệt ba nguồn giá trị `jobParameters`, `jobExecutionContext` và `stepExecutionContext`.
- Giải thích bean proxy của `@StepScope` và thời điểm SpEL được đánh giá.
- Viết reader lấy tham số động từ `ExecutionContext` mà không tạo bean mutable dùng chung.
- Thiết kế partition có ranh giới độc lập và reader restartable.
- Biết khi nào cần promotion từ step context lên job context, và khi nào nên dùng `@JobScope`.
- Chẩn đoán lỗi scope, key không tồn tại, giá trị lỗi kiểu, thay đổi input giữa restart và tranh chấp dữ liệu.

Ví dụ dưới đây hướng tới **Spring Batch 5.x, Java 17+**, với Spring Boot và JDBC. Kiểu API/chữ ký có thể thay đổi ở major version khác; nên chạy thử với version đã khóa trong ứng dụng.

## 2. Ba nguồn dữ liệu có thể late bind

| Nguồn | Được tạo hoặc cập nhật ở đâu? | Phạm vi và thời gian sống | Ví dụ dùng |
|---|---|---|---|
| **`JobParameters`** | Người/scheduler khởi chạy job; coi là đầu vào bất biến trong một execution | Giá trị launch dùng để xác định `JobInstance` (đối với identifying parameters) | `businessDate`, `inputFile`, `tenantId` |
| **`JobExecutionContext`** | Logic của job/step, listener hoặc promotion; lưu qua `JobRepository` | Gắn với một `JobExecution`, có thể dùng giữa các step cùng lần chạy | `snapshotKey`, đường dẫn file manifest đã tạo |
| **`StepExecutionContext`** | Framework, partitioner, reader hoặc listener; lưu qua `JobRepository` | Gắn với một `StepExecution` cụ thể, có thể checkpoint theo step/partition | `minId`, `maxId`, offset/position reader |

Phân biệt rõ: `JobParameters` **không phải** nơi lưu vị trí đọc đã thay đổi giữa chừng; `ExecutionContext` **không phải** phương tiện để tự tạo một job instance mới. Context lưu các giá trị phục vụ thực thi và restart theo metadata của Spring Batch.

Ví dụ cùng một job xử lý 1000 ID:

~~~text
JobParameters (cả job):
  businessDate = "2026-11-26"
  sourceSystem = "ERP"

JobExecutionContext (cả execution):
  snapshotKey = "orders-2026-11-26-v1"

StepExecutionContext của ordersWorker:partition0:
  minId = 1
  maxId = 250
  ordersRangeReader.read.count = ...

StepExecutionContext của ordersWorker:partition1:
  minId = 251
  maxId = 500
  ordersRangeReader.read.count = ...
~~~

Trong mỗi partition, `minId` và `maxId` khác nhau. Reader của partition thứ hai không được sử dụng cursor hoặc checkpoint của partition thứ nhất, dù cả hai cùng chạy một cấu hình `Step` và cùng sử dụng một `DataSource`.

### Cú pháp SpEL thường gặp

| Biểu thức trong `@Value` | Nguồn dữ liệu được truy xuất |
|---|---|
| `#{jobParameters['businessDate']}` | Job parameter tên `businessDate` |
| `#{jobExecutionContext['snapshotKey']}` | Key trong context cấp job execution |
| `#{stepExecutionContext['minId']}` | Key trong context của chính step execution |
| `#{stepExecutionContext['maxId']}` | Key còn lại của partition |

Ví dụ method parameter:

~~~java
@Value("#{stepExecutionContext['minId']}") Long minId
~~~

Đây là **late binding giá trị khi bean scoped được tạo**. Một giá trị `@Value` đã được inject **không tự cập nhật liên tục** nếu ai đó thay đổi context sau đó. Nếu cần theo dõi state đọc đang biến đổi trong quá trình xử lý, hãy sử dụng lifecycle `ItemStream` và cập nhật `ExecutionContext` theo cơ chế checkpoint phù hợp.

## 3. `@StepScope` kích hoạt lúc nào?

`@Bean` thông thường tạo singleton lúc container Spring khởi tạo, trước khi biết `StepExecution` sẽ chạy. `@StepScope` biến bean thành một bean scoped có proxy: bước cấu hình nhận một proxy, còn **instance thực** được tạo khi có step context đang hoạt động.

~~~mermaid
flowchart TD
    A[Ứng dụng Spring khởi động] --> B[Đăng ký Step, Job và scoped proxy]
    B --> C[JobLauncher khởi chạy JobExecution]
    C --> D[StepExecution bắt đầu]
    D --> E[StepScope được kích hoạt]
    E --> F[Proxy tạo target bean]
    F --> G[SpEL lấy key từ ExecutionContext]
    G --> H[ItemStream.open / đọc / xử lý / ghi]
    H --> I[Commit chunk và cập nhật checkpoint]
    I --> J[Close stream, kết thúc StepExecution]
~~~

Ví dụ khai báo:

~~~java
@Bean
@StepScope
public MyItemReader myReader(
        @Value("#{stepExecutionContext['minId']}") Long minId) {
    return new MyItemReader(minId);
}
~~~

Khi Spring cấu hình worker step, nó chưa cần giá trị `minId`. Mỗi `StepExecution` được kích hoạt sẽ có reader target riêng và SpEL được giải quyết trong context tương ứng.

**Không nhầm `@StepScope` với việc tạo một thread mới.** Scope xác định lifecycle bean theo `StepExecution`, còn concurrency đến từ `TaskExecutor`, partition handler, listener container hoặc worker process. Scope cũng không bảo đảm thread safety cho dependency singleton mà scoped bean tham chiếu đến.

### Vì sao nên trả về kiểu concrete khi khai báo `@Bean`?

Nếu bean reader thực hiện `ItemStream` (ví dụ `JdbcCursorItemReader`), method `@Bean` nên khai báo kiểu trả về có thể bộc lộ `ItemStream` để Spring Batch nhận diện và gọi `open/update/close` đúng cách:

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<Long> ordersReader(...) {
    // ...
}
~~~

Trả về interface quá hẹp, chẳng hạn chỉ `ItemReader<Long>`, có thể làm các method `ItemStream` không được expose qua scoped proxy hoặc không được đăng ký lifecycle đúng như kỳ vọng. Đây là lỗi đặc biệt nguy hiểm khi muốn **restart từ checkpoint**: bài chạy lần đầu có thể thành công nhưng resume sai.

## 4. Ví dụ hoàn chỉnh: late binding cho reader theo khoảng ID

Giả sử bảng đầu vào có khóa chính duy nhất:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    processed BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

Chúng ta muốn chia ID thành nhiều khoảng không giao nhau. Mỗi worker đọc ID trong khoảng của nó, ghi `processed = TRUE` và có thể restart khi một partition thất bại.

### 4.1. Manager tạo `ExecutionContext` cho từng partition

`Partitioner` không cần tạo reader hoặc mở kết nối DB. Nó chỉ cung cấp tên partition và các tham số đầu vào. Ví dụ minh họa với miền ID đã chốt sẵn `1..1000`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class FixedOrderRangePartitioner implements Partitioner {
    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long firstId = 1L;
        long lastId = 1000L;
        int count = (int) Math.min((long) gridSize, lastId - firstId + 1);
        long base = (lastId - firstId + 1) / count;
        long remainder = (lastId - firstId + 1) % count;

        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
        long start = firstId;
        for (int i = 0; i < count; i++) {
            long size = base + (i < remainder ? 1 : 0);
            long end = start + size - 1;

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start);
            context.putLong("maxId", end);
            partitions.put("partition" + i, context);
            start = end + 1;
        }
        return partitions;
    }
}
~~~

Với `gridSize=4`, manager tạo `partition0: 1..250`, `partition1: 251..500`, `partition2: 501..750` và `partition3: 751..1000`. Mỗi context chỉ chứa thông tin của partition đó; Spring Batch gắn chúng với từng worker `StepExecution`.

Để áp dụng trong production, **không hardcode ranh giới** như ví dụ. Chốt miền dữ liệu bằng job parameters/manifest gắn với job instance và giữ cùng thuật toán, tên partition, cutoff khi restart. Nếu nguồn dữ liệu không đồng đều, dùng histogram hoặc manifest để tạo các vùng có chi phí tương đương; khoảng ID bằng nhau không mặc nhiên cho thời gian xử lý bằng nhau.

### 4.2. Worker tạo reader riêng bằng `@StepScope`

Đây là phần chính của late binding: `minId`/`maxId` không tồn tại khi ứng dụng start, nhưng có sẵn trong context khi worker step chạy.

~~~java
import javax.sql.DataSource;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersReaderConfiguration {

    @Bean
    @StepScope
    public JdbcCursorItemReader<Long> ordersReader(
            DataSource dataSource,
            @Value("#{stepExecutionContext['minId']}") Long minId,
            @Value("#{stepExecutionContext['maxId']}") Long maxId) {

        if (minId == null || maxId == null || minId > maxId) {
            throw new IllegalArgumentException("Invalid partition ID range");
        }

        return new JdbcCursorItemReaderBuilder<Long>()
                .name("ordersRangeReader")
                .dataSource(dataSource)
                .sql("SELECT id FROM orders "
                   + "WHERE id >= ? AND id <= ? ORDER BY id")
                .preparedStatementSetter(ps -> {
                    ps.setLong(1, minId);
                    ps.setLong(2, maxId);
                })
                .rowMapper((rs, rowNum) -> rs.getLong("id"))
                .build();
    }
}
~~~

Giải thích:

1. `@StepScope` trì hoãn tạo reader đến lúc có `StepExecution` đang hoạt động.
2. SpEL `stepExecutionContext['minId']` và `['maxId']` lấy đúng vùng đã giao cho worker.
3. Mỗi execution có một instance `JdbcCursorItemReader`, một cursor/state riêng.
4. `.name("ordersRangeReader")` giữ tên `ItemStream` ổn định để lưu và đọc checkpoint. **Cùng tên reader ở các partition là bình thường**, vì mỗi partition sở hữu `StepExecutionContext` độc lập.
5. SQL `ORDER BY id` theo khóa duy nhất tạo thứ tự đọc ổn định, cần thiết cho restart đáng tin cậy.
6. Điều kiện đọc cố ý **không lọc `processed = FALSE`** vì writer sẽ thay đổi cột đó; lọc theo trạng thái đang bị sửa có thể làm tập kết quả dịch chuyển giữa checkpoint.

Trong một JVM, nhiều partition có thể dùng cùng `DataSource` singleton nhưng vẫn có các reader instance và `StepExecution` riêng. Với remote partitioning, mỗi worker service cũng phải truy cập được dữ liệu nghiệp vụ và `JobRepository` phù hợp.

### 4.3. Worker step sử dụng reader proxy

Một worker step mẫu với writer ghi trạng thái lặp an toàn:

~~~java
import javax.sql.DataSource;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public JdbcBatchItemWriter<Long> ordersWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Long>()
            .dataSource(dataSource)
            .sql("UPDATE orders SET processed = TRUE WHERE id = :id")
            .itemSqlParameterSourceProvider(
                    id -> new MapSqlParameterSource("id", id))
            .build();
}

@Bean
public Step ordersWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<Long> ordersReader,
        JdbcBatchItemWriter<Long> ordersWriter) {

    return new StepBuilder("ordersWorkerStep", jobRepository)
            .<Long, Long>chunk(250, transactionManager)
            .reader(ordersReader)
            .writer(ordersWriter)
            .build();
}
~~~

Hai method `@Bean` này thuộc một class `@Configuration` hoặc cấu hình bean tương đương; để ngắn gọn, ví dụ lược bỏ phần khai báo class và import `@Configuration`. Khi Spring ghép step, tham số `ordersReader` là proxy của bean scoped; reader thật chỉ được tạo lúc chạy.

Trong ứng dụng dùng local partitioning, manager step có thể dùng `.partitioner("ordersWorkerStep", partitioner).step(ordersWorkerStep).gridSize(4).taskExecutor(executor)`. Trong remote partitioning, manager chuyển `StepExecutionRequest` cho worker service và reader vẫn lấy context từ `StepExecution` tương ứng. **Late binding giống nhau về nguyên tắc**, chỉ có nơi thực thi step thay đổi.

### 4.4. Vì sao ví dụ cập nhật lặp an toàn?

`UPDATE orders SET processed = TRUE WHERE id = :id` đặt trạng thái cuối giống nhau nếu cùng item bị thử lại. Tuy nhiên, đây **không phải cam kết exactly-once** cho mọi nghiệp vụ. Nếu writer gửi email, gọi API thanh toán hoặc publish message, có thể cần idempotency key, unique constraint, transactional outbox hoặc cơ chế chống trùng ở downstream.

## 5. Late binding từ `JobParameters`

Không phải giá trị nào cũng thuộc riêng một partition. Đường dẫn file, ngày xử lý hoặc tenant được truyền từ lúc launch job nên lấy từ `jobParameters`.

Ví dụ reader đọc một tệp CSV được chỉ định khi launch:

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration
public class CustomerCsvConfiguration {
    public record CustomerRow(long id, String email) {}

    @Bean
    @StepScope
    public FlatFileItemReader<CustomerRow> customerCsvReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        if (inputFile == null || inputFile.isBlank()) {
            throw new IllegalArgumentException("Missing inputFile job parameter");
        }

        return new FlatFileItemReaderBuilder<CustomerRow>()
                .name("customerCsvReader")
                .resource(new FileSystemResource(inputFile))
                .delimited()
                .names("id", "email")
                .fieldSetMapper(fs -> new CustomerRow(
                        fs.readLong("id"), fs.readString("email")))
                .build();
    }
}
~~~

Ví dụ launch job với job parameter kiểu chuỗi `inputFile=/data/in/customers-2026-11-26.csv`. Ứng dụng thực tế cần kiểm tra quyền đọc file, encoding, header/record separator và chính sách parse lỗi. Trong remote worker, đường dẫn `/data/in/...` phải có ý nghĩa trên **máy worker**, không chỉ máy manager; thường nên dùng shared storage hoặc object storage với version/key rõ ràng.

**Không sửa file đầu vào khi restart.** Reader dạng file có checkpoint theo vị trí; nếu nội dung file thay đổi giữa hai lần chạy của cùng job instance, resume có thể đọc nhầm record. Tên file chưa đủ làm đầu vào bất biến nếu dữ liệu phía sau tên ấy vẫn có thể bị thay thế.

## 6. Late binding từ `JobExecutionContext`

Giả sử job có hai step:

1. `prepareSnapshotStep` xác định bản snapshot dữ liệu cố định và ghi key `snapshotKey` vào context của nó.
2. `processSnapshotStep` đọc key để chọn đúng snapshot cho xử lý.

Theo mặc định, hai step có **StepExecutionContext khác nhau**. Step sau không tự đọc được context riêng của step trước qua expression `stepExecutionContext[...]`. Nếu dữ liệu cần dùng ở nhiều step, có thể **promote** key từ step context lên job context bằng `ExecutionContextPromotionListener`.

### 6.1. Ghi key vào context của step chuẩn bị

Trong logic của `prepareSnapshotStep`, sau khi tạo manifest/snapshot:

~~~java
// Mã đặt trong step/tasklet có quyền truy cập StepExecution:
stepExecution.getExecutionContext()
        .putString("snapshotKey", "orders-2026-11-26-v1");
~~~

Hãy chọn snapshot thực tế theo input của job và lưu key bất biến; chuỗi trong đoạn trên chỉ là giá trị minh họa.

### 6.2. Promote sau khi step thành công

~~~java
import org.springframework.batch.core.listener.ExecutionContextPromotionListener;
import org.springframework.context.annotation.Bean;

@Bean
public ExecutionContextPromotionListener promoteSnapshotKey() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();
    listener.setKeys(new String[] { "snapshotKey" });
    return listener;
}
~~~

Gắn listener bằng `.listener(promoteSnapshotKey)` vào **step chuẩn bị**; không chỉ khai báo bean mà quên đăng ký. Listener này mặc định promote các key được chọn khi step hoàn tất phù hợp với trạng thái thành công; cần xem chính sách `statuses` nếu có logic kết thúc tùy chỉnh. Giá trị được ghi vào `JobExecutionContext` để các step tiếp theo trong cùng `JobExecution` sử dụng.

### 6.3. Step sau late bind key đã promote

~~~java
@Bean
@StepScope
public SnapshotReader snapshotReader(
        @Value("#{jobExecutionContext['snapshotKey']}") String snapshotKey) {
    if (snapshotKey == null || snapshotKey.isBlank()) {
        throw new IllegalStateException("snapshotKey not prepared");
    }
    return new SnapshotReader(snapshotKey);
}
~~~

`SnapshotReader` là class ứng dụng minh họa cần cài đặt; cần trả về kiểu cụ thể có các interface lifecycle phù hợp nếu reader cũng triển khai `ItemStream`. Mấu chốt là **step chạy sau lấy key từ job context**, còn mỗi partition vẫn lấy ranh giới riêng qua `stepExecutionContext`.

Đối với parallel flows, **không suy rằng các step chạy đồng thời sẽ tự đồng bộ một map JobExecutionContext chung**. Nếu step B cần key do step A tạo, hãy đặt phụ thuộc thứ tự rõ ràng hoặc dùng manifest bền vững. Khi nhiều step cùng ghi một key, kết quả có thể mơ hồ và không an toàn cho restart.

## 7. `@JobScope` khác `@StepScope` thế nào?

`@JobScope` tạo bean theo **JobExecution**; `@StepScope` tạo bean theo **StepExecution**. Cả hai có thể late bind, nhưng lựa chọn nên xuất phát từ vùng dữ liệu và cơ chế chạy đồng thời:

| Thuộc tính | `@JobScope` | `@StepScope` |
|---|---|---|
| Đối tượng sở hữu lifecycle | Một `JobExecution` | Một `StepExecution` |
| Tần suất tạo target | Một target cho lần job execution tương ứng | Một target cho mỗi step execution/partition |
| Giá trị thường nhận | Job parameters, job execution context | Job parameters, job context, step context |
| Dữ liệu mutable theo partition | **Không phù hợp** | Phù hợp khi bean giữ state cục bộ của step |
| Parallel/partitioned step | Cần đặc biệt thận trọng với job scope | Lựa chọn phổ biến cho reader/processor stateful |

Một số cấu hình parallel, partitioned hoặc remote worker có thể chạy nhiều execution trên nhiều thread/process; `JobScope` không phải cơ chế mặc định an toàn trong những trường hợp đó vì context của job không luôn sẵn trên các thread do người dùng tự tạo. Với reader trong partition, **ưu tiên `@StepScope`** và chuyển những gì worker cần qua `JobParameters`/`ExecutionContext` bền vững, thay vì truy cập một đối tượng mutable cấp job trong bộ nhớ.

Một bean `@StepScope` không làm một `ItemReader` trở nên thread-safe nếu **nhiều thread chia sẻ cùng một `StepExecution`** (ví dụ multi-threaded step sử dụng chung reader). Nếu xử lý nhiều chunk song song trong cùng một step, vẫn phải đánh giá cách đọc, checkpoint và xử lý trật tự. Partitioning với `StepExecution` riêng thường dễ cô lập state hơn.

## 8. Checkpoint, dirty state và restart

`ExecutionContext` là cấu trúc key-value gắn với metadata của Spring Batch. Khi một `ItemStream` được mở, nó có thể đọc tiến độ từ context; khi chunk commit, framework gọi các phương thức lifecycle phù hợp để cập nhật và lưu checkpoint.

~~~mermaid
sequenceDiagram
    participant L as Step lifecycle
    participant R as ItemStream Reader
    participant C as StepExecutionContext
    participant DB as JobRepository
    L->>R: open(context)
    R->>C: Đọc vị trí đã lưu
    loop Từng chunk
        L->>R: read() nhiều lần
        L->>R: update(context)
        R->>C: Ghi vị trí đã xử lý
        L->>DB: Lưu context/metadata khi commit
    end
    L->>R: close()
~~~

**Phân biệt hai nhóm key:**

- **Key điều phối** như `minId`/`maxId`, `snapshotKey` hoặc `fileKey` thường được tạo **trước khi step bắt đầu** và ổn định trong suốt execution.
- **Key checkpoint** như vị trí item/line/cursor do reader/stream quản lý có thể thay đổi sau mỗi chunk.

Không tùy tiện ghi đè các key nội bộ reader, chẳng hạn `ordersRangeReader.read.count`, bằng code nghiệp vụ. Không biến `minId`/`maxId` thành biến chạy theo từng chunk: những ranh giới này là contract phân vùng, không phải bộ đếm tiến độ.

### Restart an toàn cần những điều kiện gì?

1. Khởi động lại **cùng JobInstance** theo identifying `JobParameters`; thay `run.id` có thể tạo instance mới và khiến các step chạy lại từ đầu.
2. Giữ tên step, tên partition, thuật toán partition, cutoff và input ổn định. Đặc biệt không tạo lại các range khác nhau cho cùng một partition khi restart.
3. Reader có tên `ItemStream` cố định và hỗ trợ checkpoint; giá trị `saveState` không bị tắt nếu dựa vào restart.
4. Input không thay đổi thứ tự và nội dung theo cách khiến vị trí đã lưu không còn ý nghĩa; với JDBC paging cần sort key duy nhất, với file nên chốt version/checksum.
5. Writer và side effect bên ngoài phải có cơ chế idempotency; transaction theo chunk không bảo đảm exactly-once xuyên database, HTTP và message broker.
6. Theo dõi trạng thái `StepExecution` trong `JobRepository`; partition `COMPLETED` thường không cần thực thi lại trong restart thông thường theo chính sách step.

**ExecutionContext chỉ đảm bảo cơ sở cho checkpoint khi được lưu thành công.** Nếu tiến trình chết sau side effect bên ngoài nhưng trước khi metadata cập nhật, job có thể xử lý lại một phần công việc. Vì vậy, late binding và restart phải đi cùng kiểm soát tác động nghiệp vụ.

### Dữ liệu nào nên đưa vào ExecutionContext?

Nên lưu các scalar, kiểu đơn giản và định danh bền vững: String, long/int, business date, URI/key của snapshot hoặc manifest. Tránh lưu đối tượng lớn, `DataSource`, open connection, bean Spring, callback hoặc object graph phức tạp; serialization có thể thay đổi giữa version và tăng áp lực metadata database. Với danh sách hàng triệu ID, lưu **đường dẫn/key manifest** thay vì cả danh sách vào context.

Đừng đặt mật khẩu, token hoặc dữ liệu nhạy cảm trong context nếu không có kiểm soát truy cập và mã hóa phù hợp: metadata batch thường được ghi lâu dài và có thể xuất hiện trong công cụ quản trị/log.

## 9. Những lỗi late binding thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `IllegalStateException: No context holder available for step scope` | Truy cập bean `@StepScope` ngoài execution, tự gọi trong startup hoặc test chưa kích hoạt scope | Để framework chạy step, hoặc dùng `StepScopeTestUtils`/test listener phù hợp |
| Expression `stepExecutionContext[...]` trả về `null` | Sai tên key hoặc partitioner chưa điền key | Kiểm tra YAML/SpEL spelling và context thực của `StepExecution` |
| `ClassCastException` hoặc lỗi conversion | `putString` nhưng tham số constructor yêu cầu `Long`; serializer/type thay đổi | Dùng `putLong`/`Long` nhất quán, validation tường minh |
| Hai partition dùng chung cursor, đọc trùng | Reader được tạo singleton hoặc bị lấy target sai cách | `@StepScope` reader và tránh chia sẻ state ngoài phạm vi step |
| Restart đọc từ đầu hoặc sai vị trí | Reader không được đăng ký `ItemStream`, `saveState=false`, đổi tên reader, input thay đổi | Khai báo kiểu bean cụ thể, giữ tên và input ổn định, thử restart |
| Step sau không thấy key của step trước | Key nằm ở step context, chưa promote lên job context | Gắn `ExecutionContextPromotionListener` và bảo đảm thứ tự step |
| `@JobScope` lỗi trong worker thread | Không có job context trên thread được tạo riêng | Ưu tiên `@StepScope` và truyền dữ liệu bằng context phù hợp |
| Dữ liệu bị thiếu sau khi writer thay đổi cột lọc | Truy vấn đầu vào không ổn định theo chunk | Chốt dataset/cutoff, tránh lọc theo trường đang cập nhật |
| Chạy thêm thread không nhanh hơn | DB pool, lock, I/O hoặc partition skew là bottleneck | Đo throughput, wait time và duration từng partition trước khi tăng concurrency |

### Khi unit test scoped bean

Trong unit test trực tiếp method factory hoặc lấy bean từ `ApplicationContext`, không nên giả định có sẵn `StepExecution`. Có thể dùng utilities từ `spring-batch-test` để kích hoạt scope:

~~~java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.batch.test.scope.StepScopeTestUtils;

StepExecution execution = MetaDataInstanceFactory.createStepExecution();
execution.getExecutionContext().putLong("minId", 1L);
execution.getExecutionContext().putLong("maxId", 100L);

StepScopeTestUtils.doInStepScope(execution, () -> {
    // Lấy bean scoped từ ApplicationContext và xác minh cấu hình reader.
    // Không gọi reader.open(...) nếu chỉ đang kiểm tra SpEL/injection.
    return null;
});
~~~

Phần này là **minh họa cách tạo context giả lập**, không phải test đầy đủ. Test có ý nghĩa cần kiểm tra query thực tế trên DB, range không giao nhau, checkpoint và lỗi restart bằng `JobRepository` phù hợp. Nếu dùng thư viện test với API khác giữa các major version, điều chỉnh import và setup theo phiên bản.

## 10. Quan sát late binding khi scale Spring Batch

Trong hệ thống nhiều worker, lỗi thường chỉ xảy ra ở một partition có ranh giới đặc biệt. Hãy ghi log **ID và tham số đã bind sau khi xác thực**, đồng thời tránh log dữ liệu nhạy cảm.

| Vùng quan sát | Nên theo dõi | Mục đích |
|---|---|---|
| Job | `jobName`, `jobExecutionId`, identifying parameters, status | Xác định lần chạy và restart đúng |
| Partition/Step | `stepExecutionId`, `partitionName`, `minId/maxId`, reader name | Chứng minh các worker nhận vùng khác nhau |
| Spring Batch metadata | `readCount`/`writeCount`, commits, rollbacks, skip/retry, checkpoint age | Biết partition nào chậm hoặc restart từ đâu |
| Executor / worker | Active threads, queue, worker pod, CPU, heap/GC | Phân biệt thiếu worker với tranh chấp tài nguyên |
| Database / middleware | Connection pool pending, SQL latency, lock wait, IOPS, broker lag | Đo nút thắt trước khi tăng concurrency |
| Nghiệp vụ | Tổng số bản ghi kỳ vọng, đã xử lý, trùng hoặc thiếu | Kiểm tra tính đúng, không chỉ thời gian chạy |

Với local partitioning, các partition có thể chạy cùng process nhưng sử dụng target bean `@StepScope` riêng. Với remote partitioning, worker process cần cùng metadata `JobRepository` và có thể tải `ExecutionContext` theo `stepExecutionId`; không thể mong bean phía manager được gửi nguyên vẹn sang JVM khác.

**Cần đo hiệu năng song song một cách công bằng:** chạy các mức worker 1, 2, 4, 8 trên cùng snapshot dữ liệu, so sánh thời gian job, throughput, thời gian partition chậm nhất và connection wait. Nếu pool DB đã bão hòa, thêm reader `@StepScope` sẽ chỉ tạo thêm cạnh tranh kết nối, không tự cải thiện throughput.

## 11. Quy tắc lựa chọn và checklist trước production

| Nhu cầu | Cách truyền/cất giữ nên chọn |
|---|---|
| Giá trị được scheduler cung cấp tại launch và ổn định cả job | `JobParameters` |
| Kết quả của một step cần dùng ở step sau trong cùng execution | Step context rồi promotion sang `JobExecutionContext`, hoặc manifest bền vững |
| Ranh giới riêng cho từng partition/worker | `StepExecutionContext` + reader `@StepScope` |
| Vị trí đọc, checkpoint, resume của `ItemStream` | `StepExecutionContext` do stream/framework quản lý |
| Dữ liệu nghiệp vụ kích thước lớn | Database/object storage; context chỉ chứa khóa hoặc URI |
| Biến dùng chung giữa nhiều thread và cập nhật liên tục | Cơ chế đồng bộ/transaction phù hợp; không dùng `ExecutionContext` như shared concurrent map |

Checklist:

- [ ] Đã phân biệt tham số launch, job context và step context.
- [ ] Bean đọc trạng thái theo execution sử dụng `@StepScope`, method return type expose đúng lifecycle `ItemStream`.
- [ ] Các key SpEL đã được tạo **trước** khi bean scoped thực được khởi tạo.
- [ ] Giá trị context có kiểu ổn định, validate các key bắt buộc và không chứa secret.
- [ ] Partition không overlap, tên/range/cutoff ổn định khi restart.
- [ ] Reader có order/checkpoint rõ ràng; dữ liệu đầu vào không biến đổi làm vô hiệu vị trí đọc.
- [ ] Writer/side effect idempotent; retry không gây tác động trùng ngoài ý muốn.
- [ ] Cảnh báo và metric theo `jobExecutionId`, `stepExecutionId` và partition.
- [ ] Đã thử một partition thất bại giữa chunk, restart và đối soát toàn bộ kết quả.

## 12. Bài tập thực hành

**Bài 1 — Phân biệt các scope.** Một job có `businessDate` từ scheduler, bước A tạo `snapshotKey`, bước B chia 6 partition, mỗi partition có `minId/maxId`. Hãy điền từng giá trị vào `JobParameters`, `JobExecutionContext` hoặc `StepExecutionContext` và giải thích cách bean ở bước B late bind.

**Bài 2 — Kiểm tra range.** Chạy `FixedOrderRangePartitioner.partition(6)` trên miền 1..1000. Liệt kê ranh giới thực tế của sáu partition, kiểm tra hợp các range bằng 1000 ID và không trùng. Dùng reader `@StepScope` để log range của từng worker.

**Bài 3 — Lỗi key.** Đổi tên context key từ `minId` thành `startId` nhưng giữ nguyên SpEL trong reader. Quan sát lỗi/`null`, thêm validation và viết test chứng minh cấu hình sai được phát hiện trước khi xử lý dữ liệu.

**Bài 4 — Restart.** Khởi chạy job với reader có `.name("ordersRangeReader")`, làm một partition lỗi sau vài chunk. Restart cùng job instance, so sánh checkpoint và dữ liệu đã ghi. Thử đổi tên reader hoặc thay input giữa hai lần chạy để hiểu vì sao kết quả có thể không còn đúng.

**Bài 5 — Promotion.** Tạo bước chuẩn bị ghi `snapshotKey` vào step context và đăng ký `ExecutionContextPromotionListener`. Bước sau lấy `#{jobExecutionContext['snapshotKey']}` qua `@StepScope`. Xác minh hành vi nếu promotion chưa chạy hoặc step chuẩn bị thất bại.

**Câu hỏi tự kiểm tra:** Vì sao cần `@StepScope` mới đọc được `stepExecutionContext` khi bean được tạo? Vì sao `@JobScope` không phải giải pháp mặc định cho partitioned step? `ExecutionContext` khác `JobParameters` ở cơ chế restart thế nào? Tại sao dùng tên reader ổn định nhưng không đồng nhất checkpoint giữa các partition? Khi scale lên nhiều worker, đâu là phép đo chứng minh late binding đã đúng mà throughput vẫn chưa cải thiện?

## 13. Tổng kết

Late binding bằng `ExecutionContext` giúp Spring Batch cấu hình **đúng giá trị tại thời điểm thực thi**. `JobParameters` là đầu vào launch; `JobExecutionContext` chia sẻ tiến độ/kết quả giữa các step trong cùng execution; `StepExecutionContext` giữ dữ liệu riêng và checkpoint của từng step/partition. Với reader/writer có state theo execution, `@StepScope` là công cụ chính để tạo target bean đúng lúc, nhận tham số qua SpEL và cô lập trạng thái.

Trong workload lớn, late binding phát huy giá trị khi gắn với **partition plan ổn định, reader restartable, idempotency, giới hạn tài nguyên và phép đo theo từng partition**. Scope giúp thiết lập ranh giới của đối tượng; tính đúng và hiệu năng vẫn cần được chứng minh qua transaction, kiểm thử restart và quan sát hệ thống thực tế.
