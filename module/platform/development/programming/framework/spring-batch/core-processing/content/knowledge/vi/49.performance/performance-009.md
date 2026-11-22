# Connection pool trong Spring Batch: cấu hình và tối ưu hiệu năng

Một Spring Batch job có thể xử lý hàng triệu bản ghi nhưng vẫn chạy chậm dù CPU còn rảnh. Một nguyên nhân phổ biến là **không lấy được kết nối database đúng lúc**. Reader chờ connection, writer chờ connection, transaction chưa được commit hoặc `JobRepository` không còn connection để ghi trạng thái. Khi tăng số thread để “chạy nhanh hơn”, tình hình đôi khi còn xấu đi vì mọi thread tranh nhau một connection pool có giới hạn.

Bài học thuộc **Spring Batch Core Processing → Performance**, tập trung vào cách connection pool vận hành trong một batch job, cách cấu hình **HikariCP** với Spring Boot, nhận diện nhu cầu connection của reader/writer/transaction/metadata, tính ngân sách pool cho nhiều job chạy đồng thời, đo các chỉ số thực tế và xử lý tình trạng pool cạn mà không đánh đổi tính đúng đắn dữ liệu.

Các ví dụ dùng Java 17, Spring Boot 3.x, Spring Batch 5.x, Spring JDBC, HikariCP và một database quan hệ. Thông số trong ví dụ là điểm khởi đầu minh họa, **không phải giá trị tối ưu cho mọi hệ thống**.

## 1. Connection pool giải quyết vấn đề gì?

Mỗi lần mở kết nối mới tới database thường có chi phí: TCP/TLS handshake, xác thực, tạo phiên, khởi tạo transaction và tài nguyên phía database. Mở rồi đóng kết nối vật lý cho từng truy vấn nhỏ sẽ gây lãng phí. **Connection pool** duy trì một tập kết nối có thể tái sử dụng:

```text
               Spring Batch application
        ┌─────────────────────────────────┐
        │ Job A: chunk worker 1           │
        │ Job A: chunk worker 2           │
        │ Job B: writer / listener        │
        │ JobRepository metadata         │
        └───────────────┬─────────────────┘
                        │ getConnection()
                        ▼
             ┌──────────────────────┐
             │ HikariCP             │
             │ active:  3           │
             │ idle:    2           │
             │ max:    10           │
             │ pending: 0           │
             └───────────┬──────────┘
                         │
                         ▼
                   Database server
```

Đối với code dùng `DataSource`, pool trả về một đối tượng `Connection` có thể được quản lý bởi Spring transaction. Khi code gọi `close()` theo đúng contract, kết nối vật lý thông thường được **trả về pool** để tái sử dụng; không có nghĩa TCP connection chắc chắn bị đóng ngay.

### 1.1. Những giới hạn cần nhớ

| Tham số / trạng thái | Ý nghĩa | Điều xảy ra khi quá tải |
| --- | --- | --- |
| `maximumPoolSize` | Số connection tối đa pool quản lý cùng thời điểm | Request tiếp theo phải chờ connection rảnh |
| `minimumIdle` | Số connection nhàn rỗi mà Hikari cố duy trì | Không phải “số connection tối thiểu mỗi job được dành riêng” |
| `connectionTimeout` | Thời gian tối đa một request chờ mượn connection | Hết hạn sẽ ném exception |
| `maxLifetime` | Tuổi thọ tối đa của connection trong pool theo cơ chế retire của Hikari | Connection cũ được thay khi không còn được sử dụng |
| `idleTimeout` | Thời gian tối đa của connection idle trước khi có thể được loại bỏ | Chỉ có ý nghĩa phù hợp khi pool cho phép giảm số idle |
| `active` | Số connection đang được mượn | Tăng cao kéo dài báo hiệu tải hoặc giữ connection lâu |
| `idle` | Số connection hiện sẵn sàng trong pool | Bằng 0 lâu dài có thể báo thiếu dung lượng |
| `pending` | Số request đang chờ lấy connection | Tăng liên tục là tín hiệu cần điều tra |

**Pool lớn hơn không đồng nghĩa job nhanh hơn.** Database cũng phải quản lý transaction, lock, bộ nhớ cho mỗi session, I/O và mức đồng thời. Tăng pool từ 10 lên 100 khi database chỉ xử lý hiệu quả 12 truy vấn đồng thời có thể làm throughput giảm, lock wait tăng và ảnh hưởng những ứng dụng dùng chung database.

## 2. Một batch job dùng connection ở những vị trí nào?

Spring Batch có hai nhóm hoạt động thường dùng database:

1. **Hạ tầng batch:** `JobRepository` ghi `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext` và các thay đổi trạng thái vào những bảng `BATCH_*`.
2. **Dữ liệu nghiệp vụ:** Reader truy vấn nguồn, processor có thể tra cứu thông tin, writer ghi kết quả, listener hoặc service khác có thể truy vấn thêm.

Với cấu hình Spring Boot đơn giản, hai nhóm có thể **cùng sử dụng một `DataSource` và Hikari pool**. Khi cấu hình nhiều datasource, mỗi pool lại có giới hạn riêng; một pool còn connection không giúp ích nếu thao tác đang chờ pool khác.

```text
                              Spring Batch job
                                    │
               ┌────────────────────┴───────────────────┐
               │                                        │
        JobRepository                          Business processing
        BATCH_* tables                         reader / writer / lookup
               │                                        │
               └───────────────┬────────────────────────┘
                               ▼
                      DataSource + HikariCP
                               ▼
                            Database
```

Nếu có hai datasource:

```text
JobRepository ──> batchMetaDataSource ──> batch-meta-pool ──> DB/schema metadata
Business I/O  ──> businessDataSource ──> business-pool   ──> DB/schema nghiệp vụ
```

Việc tách pool có thể cô lập một phần tải metadata với tải nghiệp vụ. Tuy nhiên nó làm tăng cấu hình, tổng số connection, quy tắc transaction và nguy cơ chọn nhầm datasource. Chỉ nên tách khi có lý do vận hành rõ ràng và kiểm tra tổng budget kết nối ở database.

### 2.1. Connection và chunk transaction

Một chunk-oriented step thường thực hiện:

```text
BEGIN TRANSACTION
    read item(s)
    process item(s)
    write chunk
COMMIT
```

Trong một transaction JDBC, connection thường được gắn với transaction và có thể được giữ tới lúc commit/rollback sau khi đã được lấy. Tùy cách reader, writer và transaction manager được cấu hình, **không phải tất cả hoạt động của chunk đều mượn chính xác một connection duy nhất**:

- `JdbcBatchItemWriter` dùng cùng datasource và transaction manager có thể tham gia connection đang được quản lý bởi transaction.
- Reader có cursor riêng có thể dùng một connection khác được giữ trong suốt vòng đời step.
- `JdbcTemplate` gọi datasource khác sẽ đi qua pool của datasource đó.
- Các lần cập nhật `JobRepository` sử dụng datasource/transaction riêng của hạ tầng batch theo cấu hình.
- Một processor gọi HTTP hoặc API từ xa có thể khiến connection transaction đã được mượn phải chờ lâu trong khi request mạng đang chạy.

Điểm cần đo là **mỗi execution giữ bao nhiêu connection đồng thời và giữ trong bao lâu**, không chỉ đếm số dòng SQL.

### 2.2. Reader nào có thể giữ connection lâu?

| Kiểu reader | Đặc điểm connection | Tác động thường gặp |
| --- | --- | --- |
| `JdbcCursorItemReader` | Thông thường mở một JDBC cursor và giữ connection trong quá trình đọc; cách chia sẻ transaction tùy cấu hình | Job dài có thể chiếm connection lâu, kể cả khi processor chậm |
| `JdbcPagingItemReader` | Thực hiện truy vấn theo trang; nhu cầu mượn connection theo các lần query | Có thể phù hợp khi cần tránh giữ cursor lâu; cần sort key ổn định |
| `JpaPagingItemReader` | Dùng JPA `EntityManager`, paging và transaction theo thiết kế reader | Cần xem xét persistence context, fetch và datasource JPA |
| `FlatFileItemReader` | Đọc file, không cần JDBC cho thao tác đọc | Writer và metadata vẫn có thể cần connection |
| `RepositoryItemReader` | Tùy repository và transaction | Phải xem SQL/ORM thực tế thay vì suy đoán |

`JdbcCursorItemReader` theo mặc định dùng một connection riêng cho cursor. Có tùy chọn dùng connection chia sẻ mở rộng trong một số thiết kế (`useSharedExtendedConnection`) nhưng đòi hỏi cấu hình datasource/wrapper và transaction phù hợp; đây không phải thay đổi nên bật chỉ để “giảm một connection”. Mặt khác, **leak detector** có thể báo connection bị giữ lâu bởi cursor dù code đang hoạt động đúng. Cần nhìn cả lifecycle của reader trước khi coi đó là leak.

## 3. Cấu hình HikariCP trong Spring Boot

Spring Boot thường chọn **HikariCP** làm pool khi Hikari có trên classpath và ứng dụng dùng JDBC/JPA datasource auto-configuration. Với các starter Spring phổ biến, ứng dụng batch có thể sử dụng Hikari mà không cần tự tạo `HikariDataSource`.

Ví dụ `application-batch.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/reporting
    username: ${BATCH_DB_USERNAME}
    password: ${BATCH_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver
    hikari:
      pool-name: reporting-batch-pool
      maximum-pool-size: 12
      connection-timeout: 20000
      validation-timeout: 5000
      max-lifetime: 1500000

  batch:
    jdbc:
      initialize-schema: never
```

Ở đây `spring.datasource.hikari` là namespace cấu hình pool Hikari của datasource chính trong Boot. Các giá trị timeout/lifetime dùng **mili giây**. Chẳng hạn `connection-timeout: 20000` nghĩa là một request có thể chờ connection trong tối đa khoảng 20 giây trước khi thất bại.

Các biến `BATCH_DB_USERNAME` và `BATCH_DB_PASSWORD` phải được cấp bằng cơ chế cấu hình bảo mật của môi trường; không commit secret vào repository hoặc log giá trị thuộc tính chứa secret. `initialize-schema: never` trong ví dụ giả định schema `BATCH_*` đã được chuẩn bị bằng migration; không áp dụng nếu môi trường chưa có metadata schema.

### 3.1. Hiểu các tham số Hikari quan trọng

| Hikari property | Công dụng | Nguyên tắc chọn |
| --- | --- | --- |
| `maximum-pool-size` | Giới hạn số connection trong pool | Theo concurrency thực, thời gian giữ connection và budget DB |
| `minimum-idle` | Giữ một số connection idle để giảm độ trễ cấp phát | Có thể không khai báo để pool có kích thước ổn định theo chiến lược mặc định của Hikari |
| `connection-timeout` | Giới hạn thời gian chờ mượn connection | Đủ cho dao động ngắn, nhưng không che giấu pool cạn kéo dài |
| `validation-timeout` | Giới hạn thời gian kiểm tra connection còn dùng được | Nhỏ hơn `connectionTimeout` |
| `max-lifetime` | Retire connection sau thời gian tối đa trong pool | Nên ngắn hơn giới hạn lifetime của database/proxy nếu hạ tầng có giới hạn |
| `idle-timeout` | Giảm connection idle khi thích hợp | Không giúp nhiều nếu pool giữ cố định tối đa số connection |
| `keepalive-time` | Kiểm tra/giữ kết nối nhàn rỗi theo khoảng cấu hình | Cân nhắc khi proxy/load balancer tự ngắt connection idle |
| `leak-detection-threshold` | Ghi cảnh báo khi connection được mượn quá lâu | Công cụ chẩn đoán; dễ báo nhầm với cursor hoặc transaction dài |

Một số cấu hình có thể làm thay đổi ý nghĩa của cấu hình khác. Ví dụ `idleTimeout` chịu ảnh hưởng của `minimumIdle`, và `keepaliveTime` cần tương thích với `maxLifetime`. Không chỉnh từng giá trị theo cảm tính; xem điều kiện của phiên bản HikariCP đang dùng và giám sát sau thay đổi.

HikariCP thường có mặc định `maximumPoolSize=10` khi không được cấu hình, nhưng **không nên dựa vào giá trị mặc định để kết luận đủ connection** cho job nhiều thread. Khi khai báo `minimum-idle` thấp, pool có thể co lại lúc nhàn rỗi, đổi lại phải tạo thêm connection khi tải tăng. Với batch có cao điểm tập trung, chính sách pool ổn định thường giảm biến động trong lúc bắt đầu xử lý.

### 3.2. Không tự tạo DataSource thứ hai khi chưa cần

Ví dụ sau là cách khởi tạo bean **khi thực sự cần cấu hình datasource riêng**, không phải bước bắt buộc của ứng dụng Boot thông thường:

```java
@Bean
@ConfigurationProperties("spring.datasource.hikari")
HikariDataSource batchDataSource() {
    return DataSourceBuilder.create()
            .type(HikariDataSource.class)
            .build();
}
```

Đoạn này chỉ minh họa ý tưởng binding; nó cần thêm cấu hình URL/credentials tương ứng, chú ý `jdbcUrl` so với `url` khi bind trực tiếp Hikari và đúng cách đánh dấu datasource cho Spring Batch. **Đừng chép đoạn này vào ứng dụng đã dùng auto-config rồi tạo thêm pool cạnh tranh mà không kiểm tra bean hiện có.** Phần lớn ứng dụng chỉ cần chỉnh `spring.datasource.hikari.*`.

Trong Spring Boot, nếu tách datasource metadata và nghiệp vụ, cần cấu hình bean chính, datasource dành cho batch và transaction manager theo tài liệu của **phiên bản Boot/Spring Batch cụ thể**. Một dấu `@Primary` đặt sai có thể khiến repository ghi metadata vào database nghiệp vụ hoặc writer chạy trên datasource không dự kiến.

## 4. Pool size và số worker thread phải được tính cùng nhau

Xét một step dùng tám worker thread, mỗi worker đôi lúc cần một connection business. Nếu pool chỉ có bốn connection, bốn worker còn lại có thể phải chờ:

```text
Executor: 8 workers        Hikari pool: maximumPoolSize = 4

W1 ── borrowed conn #1
W2 ── borrowed conn #2
W3 ── borrowed conn #3
W4 ── borrowed conn #4
W5 ── waiting
W6 ── waiting
W7 ── waiting
W8 ── waiting
```

Khi các worker đang giữ connection chậm bởi transaction dài, việc tăng pool ít hơn hoặc bằng số thread không tự giải quyết mọi nút thắt. Cần đo thời gian acquire, thời gian giữ connection, lock wait và SQL execution.

### 4.1. Ngân sách connection theo workload

Một cách ước lượng ban đầu:

```text
Required pool capacity ≈
    peak concurrent borrowed connections by active chunk workers
  + connections held by long-lived cursors / streaming readers
  + concurrent metadata / listeners / auxiliary operations
  + small operational headroom
```

Đây là **ngân sách concurrency**, không phải công thức chính xác tuyệt đối vì một worker có thể dùng 0, 1 hoặc nhiều connection tại những thời điểm khác nhau.

Ví dụ đo được vào cao điểm:

| Thành phần | Số connection đang mượn cao điểm |
| --- | ---: |
| Job A: 4 chunk workers | 4 |
| Job B: 3 chunk workers | 3 |
| Hai cursor reader dài | 2 |
| Metadata và truy vấn phụ trợ đồng thời | 1 |
| Dự phòng ngắn hạn | 2 |
| **Pool budget tham khảo** | **12** |

Chọn `maximum-pool-size: 12` trong ví dụ là giả định workload này chia sẻ cùng pool và database còn đủ budget. Nếu các reader hoặc metadata dùng pool khác, phải tính lại từng pool thay vì cộng tùy ý.

### 4.2. Budget của cả database quan trọng hơn một ứng dụng

Giả sử database cho phép 100 connection nhưng cần dành 20 cho quản trị, replication và ứng dụng khác. Ba replica batch, mỗi replica dùng pool tối đa 30, có thể yêu cầu tổng cộng 90 connection và vượt ngân sách chỉ còn 80.

```text
Database allowed connections:            100
Reserved / other applications:           20
Available to batch applications:         80

3 replicas × maxPoolSize 30 = 90   --> có thể vượt ngân sách
3 replicas × maxPoolSize 20 = 60   --> còn headroom cho dao động
```

Đây là phép tính trần theo cấu hình, không phải khẳng định mỗi pool luôn mở đủ tối đa connection. Khi triển khai nhiều container/job ngắn hạn hoặc autoscaling, cần tính **số instance có thể chạy đồng thời × số pool mỗi instance × maximumPoolSize**. Mỗi replica JVM có pool riêng; HikariCP không tự điều phối giới hạn kết nối toàn cụm.

### 4.3. Đo throughput thay vì chỉ đo pool occupancy

Pool có `active=12/12` liên tục chưa chắc là lỗi nếu throughput đạt mục tiêu và `pending` nhỏ. Ngược lại, `active=3/12` và job rất chậm có thể do lock, SQL không tối ưu hoặc I/O ngoài database. Đừng tăng pool chỉ vì batch chạy lâu.

Các chỉ số nên đối chiếu cùng thời điểm:

- Số item/giây, thời gian job và từng step.
- Thời gian chờ lấy connection và số request timeout.
- `active`, `idle`, `pending` của pool.
- Thời gian transaction, SQL latency, lock wait, query plan và CPU/I/O database.
- Số thread thực sự đang xử lý, blocked hay chờ I/O.

## 5. Multi-threaded step: executor không thay thế pool

Spring Batch cho phép cấu hình `TaskExecutor` để nhiều chunk được xử lý đồng thời. Ví dụ dùng `ThreadPoolTaskExecutor`:

```java
package com.example.batch;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class BatchExecutorConfig {

    @Bean
    TaskExecutor batchTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("batch-worker-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(16);
        executor.initialize();
        return executor;
    }
}
```

Một step nhận executor:

```java
@Bean
Step importStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> reader,
        ItemProcessor<Customer, Customer> processor,
        ItemWriter<Customer> writer,
        @Qualifier("batchTaskExecutor") TaskExecutor executor) {

    return new StepBuilder("importStep", repository)
            .<Customer, Customer>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .taskExecutor(executor)
            .build();
}
```

Đây là **mẫu cấu hình**: `Customer`, reader, processor và writer phải được dự án cung cấp. Không phải mọi `ItemReader` và `ItemWriter` đều thread-safe; trước khi bật `.taskExecutor(...)`, cần kiểm tra state của từng component, thứ tự dữ liệu, checkpoint, transaction và khả năng restart. Với Spring Batch 5, API và cách giới hạn concurrency cũng cần được chọn đúng theo phiên bản đang dùng.

Trong ví dụ executor:

- `corePoolSize=4`: số thread lõi.
- `maxPoolSize=8`: số thread tối đa của executor.
- `queueCapacity=16`: công việc có thể được đưa vào hàng đợi; vì executor dùng queue nên **không thể chỉ nhìn `maxPoolSize=8` mà kết luận lúc nào cũng có tám worker đang chạy**.

Đồng thời, connection pool là tài nguyên khác. Tăng số worker lên 8 trong khi pool đã bão hòa có thể chỉ làm nhiều worker bị chặn ở `getConnection()`. Cần phối hợp concurrency của executor, số step/job cùng chạy và capacity của pool.

### 5.1. Chọn chunk size và thời gian giữ connection

Ví dụ với chunk size 1.000:

```text
BEGIN TRANSACTION
  process 1,000 items
  write 1,000 items
COMMIT
```

Chunk lớn có thể giảm số lần commit và batch SQL hiệu quả hơn, nhưng nếu transaction giữ connection trong thời gian dài, pool sẽ kém linh hoạt và rollback có thể đắt. Chunk quá nhỏ lại làm tăng số transaction, checkpoint và thao tác metadata.

Thay vì mặc định “chunk càng lớn càng nhanh”, hãy đo các mức như 100, 500, 1.000 trên workload đại diện và quan sát:

| Chỉ số | Chunk quá nhỏ | Chunk quá lớn |
| --- | --- | --- |
| Transaction overhead | Có thể cao | Có thể thấp hơn |
| Thời gian giữ connection | Thường ngắn | Có thể dài |
| Memory của chunk | Thấp | Cao hơn |
| Chi phí rollback | Thường nhỏ hơn | Có thể lớn hơn |
| Tần suất update metadata | Nhiều hơn | Ít hơn |
| Throughput thực tế | Phụ thuộc database | Phụ thuộc database |

**Không đưa thao tác network chờ lâu vào transaction database nếu không cần thiết.** Có thể tách giai đoạn gọi API và ghi DB, cache/prefetch thông tin ở mức phù hợp hoặc giới hạn timeout, miễn vẫn bảo đảm ràng buộc consistency và khả năng retry/restart.

## 6. Lấy connection theo transaction và trả về pool đúng cách

Khi dùng `JdbcTemplate`, Spring transaction manager và một `DataSource` được Spring quản lý, framework thường tự lấy/trả connection theo contract. Nếu tự thao tác JDBC, phải đóng tài nguyên bằng `try-with-resources`.

Ví dụ thao tác JDBC độc lập ngoài Spring-managed transaction:

```java
package com.example.batch;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public class CustomerLookup {
    private final DataSource dataSource;

    public CustomerLookup(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean exists(long customerId) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT 1 FROM customers WHERE id = ?")) {

            statement.setLong(1, customerId);
            try (ResultSet result = statement.executeQuery()) {
                return result.next();
            }
        }
    }
}
```

Ví dụ trên dùng `Connection` trực tiếp **ngoài giao dịch do Spring quản lý**. Trong một tasklet/processor đang tham gia transaction, tự gọi `dataSource.getConnection()` và đóng connection mà không hiểu transaction binding có thể khiến thao tác chạy ngoài transaction hoặc mượn thêm connection không mong muốn. Với ứng dụng Spring nên ưu tiên `JdbcTemplate`, Spring Data repository hoặc `DataSourceUtils` đúng contract khi thực sự cần JDBC thủ công.

Ví dụ bằng `JdbcTemplate`:

```java
public boolean exists(long customerId) {
    Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM customers WHERE id = ?",
            Integer.class,
            customerId);
    return count != null && count > 0;
}
```

Nếu `JdbcTemplate` dùng đúng datasource gắn với transaction manager hiện tại, Spring sẽ quản lý connection phù hợp transaction. Dù vậy, gọi `exists(...)` cho **từng item trong hàng triệu item** vẫn có thể là nút thắt N+1 query. Tối ưu truy vấn bằng join/batch lookup thường mang lại lợi ích lớn hơn tăng số connection.

## 7. Phân biệt pool cạn, leak và SQL chậm

Một lỗi điển hình từ HikariCP:

```text
java.sql.SQLTransientConnectionException:
HikariPool-1 - Connection is not available,
request timed out after 20000ms
```

Thông điệp này cho biết có thao tác **không mượn được connection trong thời gian chờ**. Nó chưa chứng minh connection bị leak.

| Triệu chứng | Khả năng cần điều tra | Bằng chứng nên tìm |
| --- | --- | --- |
| `active ≈ max`, `pending` tăng | Pool quá nhỏ so với demand hoặc giữ connection lâu | Hikari metrics, thread dump, thời gian transaction |
| `active ≈ max`, SQL rất chậm | Query/lock/I/O database | Slow query log, query plan, database wait events |
| Job tăng thread rồi timeout nhiều hơn | Concurrency vượt năng lực DB/pool | Số worker, TPS, pool pending và DB CPU |
| `active` không giảm sau khi step kết thúc | Connection không trả hoặc tài nguyên vẫn mở | Stack trace leak detection, lifecycle reader, JDBC close |
| Pool tạo connection mới thất bại | DB hết slot, network/TLS/credentials | DB connection count, Hikari logs, lỗi driver |
| Metadata job cập nhật lỗi khi writer tải nặng | `JobRepository` dùng chung pool đang bão hòa | Datasource mapping, metadata query latency |
| Hikari leak warning trên job cursor dài | Cursor giữ connection hợp lệ quá ngưỡng cảnh báo | Reader `open/close`, step duration, transaction trace |

### 7.1. Bật leak detection để điều tra

Tạm thời trong môi trường chẩn đoán:

```yaml
spring:
  datasource:
    hikari:
      leak-detection-threshold: 30000
```

Hikari sẽ ghi cảnh báo khi một connection được mượn quá thời gian ngưỡng. Đây là **tín hiệu điều tra**, không phải bằng chứng leak. Một job xử lý lâu có transaction lớn hoặc cursor mở suốt step có thể vượt 30 giây hợp lệ; cần xem connection sau đó có được trả về không và stack trace mượn connection ở đâu.

Không nên bật ngưỡng thấp trong production chỉ để “bắt được tất cả lỗi”: nó có thể gây nhiều cảnh báo vô ích và log chứa stack trace của đường gọi. Cũng đừng tăng `connectionTimeout` lên vài phút để che pool đang bão hòa; thao tác sẽ xếp hàng lâu và vượt deadline của batch.

### 7.2. Cách chẩn đoán có thứ tự

1. Xác định thời điểm lỗi và danh tính pool (`pool-name`), job, step.
2. Xem `active`, `idle`, `pending`, timeout trong thời gian đó.
3. Kiểm tra số job/step/partition đang chạy cùng lúc và pool của các replica khác.
4. Đối chiếu số session DB, SQL đang chạy, lock wait, transaction lâu.
5. Kiểm tra reader cursor/streaming, transaction quá lớn, HTTP call trong transaction và JDBC resource không đóng.
6. Sửa nguyên nhân rồi đo lại throughput, latency và tỷ lệ timeout.

Nếu các connection bị giữ vì query lock lâu, **tối ưu query và rút ngắn transaction** thường giải quyết tốt hơn việc tăng pool. Nếu DB thực sự còn dư năng lực và pending tăng do concurrency hợp lệ, mới cân nhắc tăng `maximumPoolSize` trong budget đã tính.

## 8. Quan sát HikariCP bằng Spring Boot Actuator

Thêm Actuator:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Spring Boot cùng Micrometer có thể xuất các chỉ số Hikari như:

```text
hikaricp.connections.active
hikaricp.connections.idle
hikaricp.connections.pending
hikaricp.connections.max
hikaricp.connections.timeout
hikaricp.connections.acquire
hikaricp.connections.usage
```

Tên/sự hiện diện chi tiết có thể phụ thuộc phiên bản Micrometer và registry. Kiểm tra các metric thực tế tại runtime trước khi xây dashboard.

Ví dụ bật metrics endpoint trong một môi trường được bảo vệ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
```

Truy vấn khi Actuator được bật và endpoint được phép truy cập:

```bash
curl http://localhost:8080/actuator/metrics/hikaricp.connections.active
curl http://localhost:8080/actuator/metrics/hikaricp.connections.pending
```

Nếu ứng dụng batch không chạy web server, có thể xuất metric qua Prometheus exporter/registry, JMX hoặc hệ thống telemetry được cấu hình riêng. Các endpoint Actuator không nhất thiết khả dụng bằng HTTP trong một ứng dụng batch CLI chỉ sống vài phút.

**Không mở công khai `/actuator/metrics` chỉ để tiện kiểm tra.** Cần cơ chế bảo vệ endpoint, mạng, quyền truy cập và retention metric phù hợp. Với pool nhiều datasource, sử dụng tag hoặc tên pool để tránh gộp các số liệu không cùng loại.

### 8.1. Đọc metrics như thế nào?

| Mẫu quan sát | Diễn giải khả dĩ | Bước tiếp theo |
| --- | --- | --- |
| `pending=0`, active trung bình thấp | Pool có thể chưa phải nút thắt | Đo SQL, CPU, I/O và logic processor |
| Pending tăng đúng các đợt job chạy chồng | Budget concurrency không đủ hoặc transaction dài | Giới hạn job đồng thời, tune thread/chunk và DB |
| `active=max`, timeout tăng | Pool cạn hoặc kết nối bị giữ bất thường | Tìm query chậm, lock, cursor và leak |
| Pool dư connection nhưng database CPU cao | DB đang bão hòa về xử lý | Tối ưu query/index và giảm concurrency |
| Acquire latency cao dù không timeout | Có tranh chấp trong khoảng ngắn | Quan sát percentiles theo thời gian |
| Throughput giảm sau khi tăng max pool | DB lock contention hoặc I/O tăng | So sánh baseline và quay về cấu hình hiệu quả |

Metric acquire/usage có thể phản ánh thời gian chờ mượn và thời gian giữ connection. Chúng hữu ích hơn việc chỉ lấy snapshot `active`. Cần xét khoảng thời gian và percentile, vì một spike ngắn khác với tình trạng bão hòa kéo dài.

## 9. Ví dụ giám sát pool từ Java trong môi trường test

HikariCP có `HikariPoolMXBean` để đọc tình trạng pool. Đây là cách quan sát tại một thời điểm, phù hợp cho chẩn đoán hoặc test nhỏ:

```java
package com.example.batch;

import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.HikariPoolMXBean;

public final class PoolSnapshot {

    public record Values(
            int active, int idle, int total, int waiting) {}

    public static Values capture(HikariDataSource dataSource) {
        HikariPoolMXBean pool = dataSource.getHikariPoolMXBean();
        if (pool == null) {
            throw new IllegalStateException(
                    "Hikari pool has not been initialized");
        }

        return new Values(
                pool.getActiveConnections(),
                pool.getIdleConnections(),
                pool.getTotalConnections(),
                pool.getThreadsAwaitingConnection());
    }
}
```

Ví dụ sử dụng tại một điểm chẩn đoán có `HikariDataSource`:

```java
PoolSnapshot.Values snapshot = PoolSnapshot.capture(hikariDataSource);

log.info(
        "event=batch_pool_snapshot active={} idle={} total={} waiting={}",
        snapshot.active(),
        snapshot.idle(),
        snapshot.total(),
        snapshot.waiting());
```

Các giá trị là **snapshot gần đúng của trạng thái động**: ngay sau khi đọc, một thread khác có thể mượn/trả connection. Đừng dùng chúng để tự viết vòng `while (waiting > 0)` điều khiển job hay bảo đảm không bao giờ cạn connection. Đối với production, metric theo thời gian và alert thích hợp hơn log snapshot liên tục.

### 9.1. Mô phỏng tình trạng chờ connection trong test

Với H2 và một pool riêng chỉ dành cho test:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:pool_test;DB_CLOSE_DELAY=-1
    hikari:
      maximum-pool-size: 2
      connection-timeout: 1000
```

Kịch bản kiểm thử:

1. Mượn connection thứ nhất và giữ mở.
2. Mượn connection thứ hai và giữ mở.
3. Trong một task khác, thử lấy connection thứ ba từ **cùng datasource**.
4. Sau khoảng `connectionTimeout`, kỳ vọng nhận `SQLException` liên quan đến timeout lấy connection.
5. Trong `finally`, đóng cả hai connection đầu và ngừng executor.
6. Đo lại pool để chắc rằng kết nối đã trở về trạng thái có thể dùng.

Không nên viết test dựa trên thời gian ngủ chính xác từng mili giây: CI có thể tải cao hoặc scheduling thread khác nhau. Dùng timeout có biên độ an toàn, latch để đồng bộ và kiểm tra exception có loại/mã phù hợp.

Một test như vậy chỉ chứng minh **hành vi giới hạn số connection của pool test**; nó không chứng minh batch job sản xuất có cấu hình kích thước tối ưu.

## 10. Chiến lược tối ưu theo loại workload

### 10.1. Batch đọc nhiều, ghi ít

Ví dụ job đọc 10 triệu dòng rồi tạo một file:

- Reader dạng cursor có thể giữ connection lâu.
- Nếu CPU ở processor nặng, thêm nhiều reader đồng thời có thể tăng áp lực lên DB nhưng không rút ngắn thời gian xử lý tương ứng.
- Cân nhắc paging/partition theo khóa ổn định, kích thước fetch hợp lý và giới hạn số partition hoạt động.
- Nếu file là output chính, hãy đo time spent trong reader so với processor trước khi tăng pool.

### 10.2. Batch ghi nhiều, transaction ngắn

Ví dụ nhập hàng triệu event vào database:

- Ưu tiên `JdbcBatchItemWriter` hoặc JDBC batch operations phù hợp thay vì insert từng dòng.
- Tune chunk size để cân bằng batch SQL và thời gian transaction.
- Tạo index/constraint cần thiết nhưng tránh những thao tác thừa trong vòng lặp.
- Xem lock contention, transaction isolation, unique-key conflict trước khi tăng số worker.

### 10.3. Batch gọi API ngoài khi xử lý

Ví dụ processor gọi một service đối tác cho mỗi item:

- Giới hạn concurrency riêng ở API client, timeout và retry theo chính sách.
- Cố gắng không giữ JDBC connection qua một lời gọi mạng lâu nếu mô hình consistency cho phép tách bước.
- Cân nhắc staging: lấy dữ liệu, gọi API, sau đó ghi kết quả theo nhóm với trạng thái/idempotency rõ ràng.
- Thời gian chờ API thường không được giải quyết bằng tăng `maximumPoolSize` của Hikari.

### 10.4. Nhiều job dùng chung database

Nếu `dailyImportJob`, `reconciliationJob` và `monthlySummaryJob` có thể chạy đồng thời:

- Đặt giới hạn concurrency ở scheduler/orchestrator, không chỉ tại step.
- Ưu tiên các cửa sổ chạy không chồng lấn khi DB có peak.
- Tính tổng max pool của mọi process/replica cùng database.
- Theo dõi `JobRepository` vì metadata có thể bị ảnh hưởng khi pool dùng chung bị tải nặng.
- Dùng workload prioritization và batch queue nếu cần phục vụ request online cùng database.

## 11. Checklist xử lý sự cố thực tế

Giả sử job thất bại với `Connection is not available` trong lúc cao điểm:

| Bước | Câu hỏi | Hành động |
| --- | --- | --- |
| 1 | Pool nào bị timeout? | Kiểm tra `pool-name`, datasource, stack trace mượn connection |
| 2 | Có nhiều job/replica chạy chồng? | Kiểm tra lịch, executor và số process |
| 3 | Active/pending có tăng? | Xem Hikari metrics theo phút/giây |
| 4 | Database có lock/query dài? | Xem slow SQL, query plan, transaction wait |
| 5 | Cursor/connection có bị giữ quá lâu? | Xem lifecycle reader, leak warning và kết thúc step |
| 6 | Pool size có vượt ngân sách DB? | Tính tổng max connections của các replica và dịch vụ khác |
| 7 | Có thể giảm thời gian giữ connection? | Tối ưu chunk, SQL, batch write, mạng ngoài transaction |
| 8 | Có đủ cơ sở để thay đổi pool? | Tăng/giảm có kiểm soát, đo lại throughput và timeout |

Khi một job bị timeout vì chờ connection, **đừng tự động retry vô hạn**. Nếu mỗi retry đều tạo thêm request hoặc job instance mới, hệ thống có thể bị quá tải nặng hơn. Nên dùng retry có backoff và giới hạn, giữ nguyên identifying `JobParameters` khi cần restart cùng instance, đồng thời sửa nguyên nhân cạn pool.

Không sử dụng `HikariPoolMXBean.softEvictConnections()` hoặc restart ứng dụng như giải pháp mặc định khi pool cao: việc thay connection chỉ hữu ích cho một số sự cố connection không còn hợp lệ, không giải quyết transaction kéo dài hoặc tải vượt năng lực DB.

## 12. Bài thực hành

Hãy xây dựng một `importOrdersJob` đọc dữ liệu và ghi vào PostgreSQL hoặc H2 test database, sau đó đo lại khi thay đổi tải. Thực hiện các bước sau:

1. Khởi động job với Hikari `maximum-pool-size: 4`, chunk size 100 và một worker. Ghi thời gian chạy, throughput và số connection active/pending.
2. Tăng số worker của step lên 4. Theo dõi CPU, connection acquire latency, SQL wait và throughput. Chỉ dùng reader/writer hỗ trợ concurrency phù hợp.
3. Tăng worker lên 8 nhưng giữ pool ở 4. Xác nhận số worker chờ connection có tăng hay không, thay vì giả định job chắc chắn nhanh hơn.
4. Tăng pool lên 8 **chỉ khi database còn đủ budget**. So sánh throughput, transaction latency và mức sử dụng tài nguyên của DB.
5. Thử chunk size 50, 100 và 500. Tìm mức phù hợp cho data shape thực tế dựa trên thời gian commit, rollback và lock wait.
6. Dùng một reader cursor và đo thời gian nó giữ connection. So sánh với reader paging nếu nghiệp vụ và restartability cho phép.
7. Tạo một processor gọi API stub với độ trễ có kiểm soát. Quan sát ảnh hưởng của HTTP latency lên thời gian transaction/connection usage, rồi cân nhắc tách công đoạn.
8. Mô phỏng pool exhaustion bằng hai connection giữ mở và một request thứ ba như phần 9.1. Đảm bảo mọi connection được đóng trong `finally`.
9. Chạy hai job đồng thời, xem tổng demand trên cùng pool. Tạo dashboard với `active`, `pending`, timeout, throughput và duration cho từng job.
10. Viết một đề xuất cấu hình production dựa trên số replica tối đa, concurrency cao điểm, giới hạn database và SLA; ghi rõ dữ liệu đo hỗ trợ lựa chọn.

**Kết luận:** Connection pool là tài nguyên dùng chung giữa các worker, reader, writer, transaction và hạ tầng metadata của Spring Batch. Tối ưu hiệu năng cần phối hợp **pool capacity, số job/step đồng thời, chunk size, thời gian giữ connection và năng lực database**. Khi metrics cho thấy pool đang là nút thắt, hãy sửa nguyên nhân giữ connection lâu hoặc phân bổ concurrency hợp lý trước khi tăng `maximumPoolSize`; sau mỗi thay đổi, xác nhận throughput và tính đúng đắn của kết quả batch.
