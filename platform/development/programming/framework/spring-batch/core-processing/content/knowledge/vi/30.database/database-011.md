# Nhiều datasource trong batch

Một ứng dụng Spring Batch có thể làm việc với nhiều database hoặc nhiều `DataSource`: một nguồn dành cho metadata của Spring Batch, một nguồn đọc dữ liệu nghiệp vụ, một nguồn ghi kết quả, hoặc nhiều nguồn theo từng hệ thống tích hợp. Điều quan trọng là chỉ định rõ `DataSource` nào được dùng ở từng thành phần và `PlatformTransactionManager` nào quản lý transaction của từng Step.

Spring Batch cần một `JobRepository` để lưu JobInstance, JobExecution, StepExecution và ExecutionContext. Các bảng metadata này có thể nằm cùng database nghiệp vụ hoặc trong một database riêng. Reader, Writer và service nghiệp vụ có thể dùng các datasource khác. Việc tách datasource giúp cô lập metadata, phân quyền và tải truy cập, nhưng cũng làm cho transaction và restart cần được thiết kế cẩn thận.

## 1. Vì sao một batch application cần nhiều DataSource?

Các tình huống thường gặp:

- **Batch metadata database:** lưu các bảng `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` và ExecutionContext.
- **Source database:** đọc dữ liệu từ hệ thống nguồn, ví dụ ERP hoặc CRM.
- **Target database:** ghi dữ liệu đã chuyển đổi vào hệ thống đích.
- **Reference database:** đọc danh mục, tỷ giá hoặc dữ liệu tham chiếu.
- **Audit database:** lưu log nghiệp vụ hoặc trạng thái xử lý riêng của ứng dụng.

Ví dụ một Job chuyển đơn hàng từ hệ thống nguồn sang hệ thống đích có thể dùng ba datasource:

```text
                    Spring Batch Job
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
       Batch metadata   Source DB     Target DB
       JobRepository    ItemReader    ItemWriter
       Job/Step state   đọc orders    ghi imported_orders
```

`JobRepository` quản lý trạng thái điều phối. Source database cung cấp dữ liệu. Target database lưu kết quả nghiệp vụ. Các thành phần này có thể dùng các kết nối và transaction manager riêng.

## 2. Phân biệt DataSource metadata và DataSource nghiệp vụ

Không nên nhầm datasource mà Spring Batch dùng để lưu metadata với datasource mà Reader/Writer dùng để xử lý dữ liệu.

| Thành phần | Vai trò | Ví dụ bean |
|---|---|---|
| Batch metadata `DataSource` | Lưu lịch sử và trạng thái Job/Step | `batchDataSource` |
| Batch metadata transaction manager | Quản lý transaction của JobRepository | `batchTransactionManager` |
| Source `DataSource` | Đọc dữ liệu đầu vào | `sourceDataSource` |
| Target `DataSource` | Ghi dữ liệu đầu ra | `targetDataSource` |
| Target transaction manager | Quản lý transaction của chunk ghi target | `targetTransactionManager` |

JobRepository cần datasource bền vững nếu muốn restart qua lần dừng hoặc khởi động lại ứng dụng. Dùng repository in-memory sẽ không giữ metadata lâu dài như database repository.

Các bảng metadata có schema riêng của Spring Batch. Khi dùng database metadata riêng, cần khởi tạo đúng schema tương ứng với hệ quản trị database và phiên bản Spring Batch. Không tạo các bảng `BATCH_*` trong target database chỉ vì Writer đang dùng target datasource.

## 3. Đặt tên bean và dùng @Qualifier

Khi có nhiều bean cùng kiểu `DataSource` hoặc `PlatformTransactionManager`, Spring không thể luôn suy ra bean nào cần inject. Hãy đặt tên rõ ràng và dùng `@Qualifier` tại mọi điểm cần chọn cụ thể.

Ví dụ khai báo các transaction manager:

```java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class TransactionManagerConfig {

    @Bean("batchTransactionManager")
    public PlatformTransactionManager batchTransactionManager(
            @Qualifier("batchDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean("targetTransactionManager")
    public PlatformTransactionManager targetTransactionManager(
            @Qualifier("targetDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

`DataSourceTransactionManager` quản lý transaction JDBC cho một datasource. Nếu ứng dụng dùng JPA, có thể cần `JpaTransactionManager` cho persistence unit tương ứng. Không dùng transaction manager của database A để giả định nó có thể commit hoặc rollback connection của database B.

Có thể đánh dấu một datasource hoặc transaction manager là `@Primary` nếu ứng dụng có một lựa chọn mặc định. Tuy vậy, với cấu hình batch nhiều datasource, dùng `@Qualifier` rõ ràng thường dễ đọc và ít nhầm hơn.

## 4. Chỉ định datasource cho JobRepository

Với Spring Batch 5, có thể dùng `@EnableBatchProcessing` và chỉ rõ bean metadata datasource cùng transaction manager bằng tên:

```java
import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableBatchProcessing(
        dataSourceRef = "batchDataSource",
        transactionManagerRef = "batchTransactionManager")
public class BatchInfrastructureConfig {
}
```

Spring Batch dùng `batchDataSource` cho JobRepository và `batchTransactionManager` cho các thao tác metadata. Các bean datasource và transaction manager phải được khai báo trong application context với đúng tên.

Khi dùng cấu hình Java thủ công, cần bảo đảm metadata schema đã được tạo trong `batchDataSource`. Cách khởi tạo schema phụ thuộc database, môi trường và cơ chế migration của ứng dụng. Trong production, thường nên quản lý schema bằng migration có kiểm soát thay vì để mỗi lần khởi động ứng dụng tự tạo lại.

Nếu không chỉ định rõ datasource khi có nhiều bean, hạ tầng có thể inject nhầm datasource mặc định hoặc báo lỗi do không tìm được bean duy nhất. Hãy xác định rõ metadata database ngay tại cấu hình Batch infrastructure.

## 5. Cấu hình source và target datasource cho Reader/Writer

Giả sử ứng dụng đã khai báo ba bean:

- `batchDataSource`: metadata database.
- `sourceDataSource`: database chứa đơn hàng nguồn.
- `targetDataSource`: database lưu đơn hàng đã import.

Reader phải nhận source datasource; Writer phải nhận target datasource. Ví dụ dùng `JdbcPagingItemReader` để đọc theo trang:

```java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcPagingItemReader;
import org.springframework.batch.item.database.Order;
import org.springframework.batch.item.database.builder.JdbcPagingItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.BeanPropertyRowMapper;

@Bean
public JdbcPagingItemReader<SourceOrder> sourceOrderReader(
        @Qualifier("sourceDataSource") DataSource sourceDataSource) {

    return new JdbcPagingItemReaderBuilder<SourceOrder>()
            .name("sourceOrderReader")
            .dataSource(sourceDataSource)
            .selectClause("select id, customer_id, amount")
            .fromClause("from source_order")
            .sortKeys(Map.of("id", Order.ASCENDING))
            .rowMapper(new BeanPropertyRowMapper<>(SourceOrder.class))
            .pageSize(500)
            .saveState(true)
            .build();
}
```

Ví dụ trên giả định `SourceOrder` là JavaBean có property tương ứng. Sort key phải ổn định và duy nhất để paging không bỏ sót hoặc đọc trùng record giữa các trang. Nếu query cần filter theo JobParameters, có thể dùng `@StepScope` và bind tham số vào query.

Writer dùng target datasource:

```java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;

@Bean
public JdbcBatchItemWriter<TargetOrder> targetOrderWriter(
        @Qualifier("targetDataSource") DataSource targetDataSource) {

    return new JdbcBatchItemWriterBuilder<TargetOrder>()
            .dataSource(targetDataSource)
            .sql("""
                    insert into imported_order
                        (source_order_id, customer_id, amount)
                    values (:sourceOrderId, :customerId, :amount)
                    """)
            .beanMapped()
            .build();
}
```

`TargetOrder` cần có JavaBean properties tương ứng với các named parameters trong SQL. Với record hoặc kiểu dữ liệu khác, có thể cung cấp `ItemSqlParameterSourceProvider` tùy chỉnh.

Điểm cần kiểm tra là Writer thực sự nhận target datasource. Nếu vô tình dùng source datasource, Job có thể chạy thành công nhưng ghi dữ liệu sai database.

## 6. Chọn transaction manager cho chunk Step

Mỗi chunk-oriented Step nhận một `PlatformTransactionManager` trong lời gọi `chunk(...)`. Transaction manager này quản lý transaction của chunk. Khi Step đọc từ source database và ghi vào target database, cần xác định resource nào cần nằm trong transaction của chunk.

Ví dụ chuyển dữ liệu từ source sang target, trong đó target là nơi cần commit/rollback cho mỗi chunk:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step transferOrdersStep(
        JobRepository jobRepository,
        @Qualifier("targetTransactionManager")
        PlatformTransactionManager targetTransactionManager,
        JdbcPagingItemReader<SourceOrder> sourceOrderReader,
        ItemProcessor<SourceOrder, TargetOrder> orderProcessor,
        JdbcBatchItemWriter<TargetOrder> targetOrderWriter) {

    return new StepBuilder("transferOrdersStep", jobRepository)
            .<SourceOrder, TargetOrder>chunk(500, targetTransactionManager)
            .reader(sourceOrderReader)
            .processor(orderProcessor)
            .writer(targetOrderWriter)
            .build();
}
```

Trong ví dụ này, transaction của chunk quản lý target datasource. Reader đọc từ source datasource riêng; thao tác đọc không tự động tham gia transaction target. Đây là thiết kế phổ biến cho luồng extract-transform-load, nhưng cần quyết định rõ yêu cầu snapshot và tính nhất quán của dữ liệu nguồn.

JobRepository được cấu hình với `batchTransactionManager` riêng. Do đó, metadata transaction và target business transaction không phải một transaction cục bộ duy nhất. Hệ quả được giải thích ở phần transaction phân tán bên dưới.

## 7. Một Step chỉ nhận một transaction manager cho chunk

Một chunk Step không nhận nhiều transaction manager độc lập để commit đồng thời nhiều datasource. Truyền `targetTransactionManager` vào `chunk(...)` không làm cho `sourceDataSource` hoặc `batchDataSource` tự động tham gia cùng transaction.

Nếu một chunk cần cập nhật đồng thời hai database và yêu cầu cả hai cùng commit hoặc rollback như một đơn vị nguyên tử, một `DataSourceTransactionManager` đơn lẻ không đủ. Có các lựa chọn:

1. Dùng JTA/XA transaction manager và resource XA phù hợp để điều phối distributed transaction.
2. Thiết kế theo eventual consistency với outbox, inbox, idempotency key hoặc quy trình bù.
3. Chia thao tác thành các Step riêng, mỗi Step có transaction manager phù hợp và có cơ chế restart/reconciliation.
4. Nếu có thể, đưa các thay đổi cần nguyên tử vào cùng database và cùng transaction manager.

Không nên tự gọi `commit()` trên connection của datasource thứ hai bên trong Writer. Việc đó phá vỡ transaction boundary mà Spring Batch đang quản lý và có thể để lại dữ liệu dở dang khi chunk rollback.

## 8. JobRepository và business transaction có thể commit lệch nhau

Khi metadata database và business database khác nhau, chúng thường dùng hai local transaction manager riêng. Hai transaction không tự động atomic với nhau.

Ví dụ một chunk ghi dữ liệu vào target database và cập nhật checkpoint/metadata trong batch database:

```text
Chunk execution
   |
   +--> Transaction target DB
   |       ghi dữ liệu nghiệp vụ
   |
   +--> Transaction batch DB
           lưu StepExecution / ExecutionContext
```

Nếu một database commit nhưng database kia gặp lỗi trước khi commit, hai nơi có thể phản ánh trạng thái khác nhau. Một trường hợp là dữ liệu target đã ghi nhưng checkpoint chưa được lưu; restart có thể đọc lại item và thử ghi lần nữa. Trường hợp khác là checkpoint đã tiến lên trong khi thay đổi nghiệp vụ chưa được commit, khiến lần restart không đọc lại phần dữ liệu đó.

Để xử lý:

- Dùng business key và unique constraint để Writer có thể chạy lại an toàn.
- Dùng upsert hoặc processed-item table có khóa idempotency.
- Giữ dữ liệu nguồn ổn định bằng snapshot/watermark.
- Nếu cần tính nguyên tử xuyên các database, dùng transaction coordinator XA/JTA được hỗ trợ đầy đủ và kiểm thử với đúng hạ tầng production.
- Nếu chấp nhận eventual consistency, lưu outbox/audit và có Step reconciliation để phát hiện, sửa lệch trạng thái.

Tách metadata database là một lựa chọn hợp lệ, nhưng không nên giả định nó tự tạo ra exactly-once processing giữa các hệ thống.

## 9. Cấu hình nhiều DataSource trong Spring Boot

Với Spring Boot, cần phân biệt hai cách cấu hình:

- Dùng Batch auto-configuration của Boot và chỉ định datasource dành riêng cho metadata bằng qualifier `@BatchDataSource`.
- Tự cấu hình Batch infrastructure bằng `@EnableBatchProcessing` và các bean được tham chiếu rõ ràng qua `dataSourceRef`/`transactionManagerRef`.

Ví dụ về ý tưởng khi dùng auto-configuration:

```java
@Bean
@BatchDataSource
DataSource batchDataSource() {
    // Tạo datasource kết nối metadata database.
}

@Bean
@Primary
DataSource applicationDataSource() {
    // Datasource mặc định của ứng dụng nghiệp vụ.
}
```

`@BatchDataSource` là qualifier của Spring Boot để nhận diện datasource dành cho Batch. Bean `@Primary` có thể là datasource nghiệp vụ nếu đó là lựa chọn mặc định của ứng dụng. Các Reader/Writer vẫn nên dùng `@Qualifier` cụ thể.

Nếu tự thêm `@EnableBatchProcessing` hoặc mở rộng `DefaultBatchConfiguration`, Spring Boot Batch auto-configuration có thể lùi lại vì ứng dụng đã tự cung cấp infrastructure. Khi đó, cần tự chịu trách nhiệm cấu hình JobRepository, JobLauncher và schema theo cách đã chọn. Không nên trộn hai cơ chế mà không hiểu bean nào đang tạo hạ tầng Batch.

Chi tiết property và hành vi auto-configuration có thể thay đổi theo phiên bản Spring Boot. Hãy kiểm tra đúng phiên bản ứng dụng đang dùng, nhất là cách khởi tạo schema metadata và lựa chọn datasource mặc định.

## 10. Ví dụ cấu hình ba datasource và hai transaction manager

Một cấu hình Java có thể tổ chức như sau. Các bean DataSource được giả định đã được tạo từ cấu hình connection pool riêng:

```java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableBatchProcessing(
        dataSourceRef = "batchDataSource",
        transactionManagerRef = "batchTransactionManager")
public class MultiDataSourceBatchConfig {

    @Bean("batchTransactionManager")
    PlatformTransactionManager batchTransactionManager(
            @Qualifier("batchDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean("targetTransactionManager")
    PlatformTransactionManager targetTransactionManager(
            @Qualifier("targetDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

Sau đó Reader/Writer và Step dùng đúng bean:

```java
@Bean
public Step transferOrdersStep(
        JobRepository jobRepository,
        @Qualifier("targetTransactionManager")
        PlatformTransactionManager targetTransactionManager,
        JdbcPagingItemReader<SourceOrder> sourceOrderReader,
        JdbcBatchItemWriter<TargetOrder> targetOrderWriter) {

    return new StepBuilder("transferOrdersStep", jobRepository)
            .<SourceOrder, TargetOrder>chunk(500, targetTransactionManager)
            .reader(sourceOrderReader)
            .processor(sourceOrderProcessor())
            .writer(targetOrderWriter)
            .build();
}
```

Trong cấu hình thực tế, có thể khai báo `sourceDataSource`, `targetDataSource` và `batchDataSource` bằng `DataSourceProperties` cùng HikariCP. Nên dùng prefix cấu hình riêng, ví dụ `app.datasource.source`, `app.datasource.target` và `app.datasource.batch`, để tránh trộn URL, username hoặc pool settings.

## 11. Quản lý connection pool cho từng datasource

Mỗi datasource thường có connection pool riêng. Khi batch chạy song song, tổng số connection có thể là tổng pool size của source, target và metadata database.

Ví dụ:

| Pool | Mục đích | Cần cân nhắc |
|---|---|---|
| Source pool | Reader mở connection đọc dữ liệu | Số partition/thread, cursor lifetime, query latency. |
| Target pool | Writer ghi dữ liệu theo chunk | Số worker đồng thời, transaction duration, lock contention. |
| Batch pool | JobRepository đọc/ghi metadata | Số Job/Step execution đồng thời, polling và metadata update. |

Không nên đặt pool size của mọi datasource bằng nhau theo cảm tính. Nếu có 16 worker nhưng target pool chỉ có 4 connection, worker sẽ chờ connection. Nếu source database giới hạn số query đồng thời, tăng pool có thể làm hệ thống nguồn quá tải.

Hãy giám sát active/idle/pending connections, connection acquisition timeout, transaction duration, query latency và số worker. Đặt connection timeout và validation phù hợp để Job fail rõ ràng khi datasource không khả dụng.

## 12. Đọc từ nhiều nguồn trong cùng một Job

Một Job có thể có nhiều Step, mỗi Step dùng datasource khác nhau. Ví dụ:

```text
Job: nightlyAggregationJob
   |
   v
readCustomerStep (customerDataSource)
   |
   v
readPaymentStep (paymentDataSource)
   |
   v
aggregateStep (warehouseDataSource)
   |
   v
publishStep (reportDataSource)
```

Mỗi Step có thể nhận transaction manager phù hợp với database mà Step ghi. Nếu Step chỉ đọc, vẫn cần xem xét consistency và isolation của nguồn dữ liệu. Nếu dữ liệu ở nhiều nguồn phải phản ánh cùng một thời điểm, cần snapshot, watermark hoặc cơ chế đồng bộ dữ liệu; đọc lần lượt các database không tự tạo một snapshot phân tán nhất quán.

Nếu một Processor cần truy vấn reference database, nên inject datasource/service rõ ràng và xem xét hiệu năng. Truy vấn reference cho từng item có thể tạo N+1 queries. Có thể cache dữ liệu tham chiếu trong phạm vi phù hợp hoặc join dữ liệu trước khi đưa vào pipeline nếu khối lượng và yêu cầu consistency cho phép.

## 13. Restart khi dùng nhiều datasource

Restart cần metadata từ JobRepository và dữ liệu nguồn/đích ở trạng thái tương thích với checkpoint. Khi nhiều datasource tham gia, cần giữ ổn định các yếu tố sau:

1. Cùng identifying JobParameters để restart đúng JobInstance.
2. Source data không thay đổi ngoài snapshot/watermark đã chọn.
3. Reader có tên ổn định và lưu state nếu cần checkpoint.
4. Target Writer idempotent để xử lý lại item sau rollback hoặc metadata lệch.
5. Batch metadata database không bị xóa hoặc reset giữa các lần chạy.
6. Các transaction manager tiếp tục trỏ tới đúng datasource sau deploy/restart.

Ví dụ, nếu Job đọc source DB theo `id <= cutoffId`, hãy lưu cutoff ID làm identifying parameter hoặc metadata bất biến của batch. Nếu query dùng `ORDER BY id`, restart có thể tiếp tục theo key ổn định. Nếu source data thay đổi và query không có snapshot, item mới được chèn trước checkpoint có thể bị bỏ qua hoặc item đã đọc có thể thay đổi nội dung.

Nếu metadata database tạm thời không khả dụng, JobRepository không thể lưu trạng thái đáng tin cậy. Không nên tiếp tục xử lý chỉ với giả định metadata sẽ tự đồng bộ sau đó.

## 14. Kiểm thử cấu hình nhiều datasource

Integration test nên dùng database test riêng cho metadata, source và target để phát hiện nhầm qualifier hoặc transaction manager. Có thể dùng Testcontainers nếu ứng dụng cần kiểm tra hành vi của database cụ thể.

Các kịch bản nên kiểm tra:

1. **Metadata isolation:** JobInstance/JobExecution xuất hiện trong batch database, không bị ghi nhầm vào source/target.
2. **Source reader:** dữ liệu được đọc từ source datasource đúng.
3. **Target writer:** dữ liệu chỉ được ghi vào target datasource theo SQL đã cấu hình.
4. **Transaction rollback:** khi Writer ném exception, thay đổi target của chunk hiện tại được rollback theo target transaction manager.
5. **Restart:** sau lỗi, Job restart cùng identifying parameters và Writer không tạo bản ghi trùng.
6. **Datasource unavailable:** kiểm tra Job thất bại rõ ràng khi source, target hoặc metadata database mất kết nối.
7. **Concurrent execution:** kiểm tra pool sizing, lock contention và unique constraint khi nhiều Job/partition chạy đồng thời.
8. **Cross-database consistency:** nếu dùng XA/JTA, kiểm thử cả trường hợp một resource rollback hoặc mất kết nối trong quá trình prepare/commit.

Ví dụ kiểm tra target sau Job:

```java
Integer targetCount = new JdbcTemplate(targetDataSource).queryForObject(
        "select count(*) from imported_order where batch_id = ?",
        Integer.class,
        batchId);

assertEquals(expectedCount, targetCount);
```

Đồng thời, dùng `JobExplorer` hoặc `JobRepository` để xác nhận JobExecution/StepExecution nằm trong metadata database. Không chỉ kiểm tra Job `COMPLETED`; cần xác nhận dữ liệu thực tế ở đúng database.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Không chỉ định datasource cho JobRepository | Metadata có thể được tạo ở datasource mặc định hoặc cấu hình thất bại. | Dùng `dataSourceRef` hoặc `@BatchDataSource` theo cách cấu hình đã chọn. |
| Inject `DataSource` không có qualifier | Spring chọn nhầm bean hoặc báo lỗi nhiều candidate. | Dùng tên bean và `@Qualifier` rõ ràng. |
| Dùng batch transaction manager cho target writer | Writer không tham gia transaction target như mong muốn. | Chọn transaction manager phù hợp trong `chunk(...)`. |
| Nghĩ một Step tự commit nhiều datasource | Một local transaction manager chỉ quản lý resource của nó. | Dùng JTA/XA hoặc thiết kế eventual consistency. |
| Đọc source và ghi target nhưng không có khóa chống trùng | Restart có thể ghi lại item đã commit ở target. | Unique constraint, upsert và idempotency key. |
| Tạo schema BATCH_* ở nhầm database | JobRepository không tìm thấy hoặc ghi metadata sai nơi. | Khởi tạo schema trong batch metadata database. |
| Pool size quá nhỏ hoặc quá lớn | Worker chờ connection hoặc database bị quá tải. | Đo tải và điều chỉnh từng pool riêng. |
| Dùng @EnableBatchProcessing lẫn với Boot auto-config không rõ ràng | Infrastructure bean có thể bị tạo trùng hoặc auto-config lùi lại. | Chọn một cách cấu hình Batch infrastructure nhất quán. |
| Restart với source data đã thay đổi | Checkpoint có thể bỏ sót hoặc đọc trùng dữ liệu. | Dùng snapshot, watermark và thứ tự query ổn định. |
| Tưởng hai database local commit nguyên tử | Có thể lệch business data và checkpoint. | XA/JTA hoặc reconciliation/idempotent processing. |

## Kết luận

Một Spring Batch application có thể dùng nhiều datasource cho metadata, dữ liệu nguồn, dữ liệu đích và các hệ thống tham chiếu. Hãy đặt tên bean rõ ràng, dùng `@Qualifier`, chỉ định datasource/transaction manager cho JobRepository và chọn transaction manager phù hợp cho từng chunk Step. Một Step chỉ có một transaction manager cục bộ cho chunk; nhiều database không tự động commit nguyên tử với nhau. Khi tách batch metadata khỏi business data, cần tính đến khả năng metadata và dữ liệu nghiệp vụ lệch nhau, dùng business key/unique constraint/upsert để restart an toàn hoặc dùng JTA/XA khi thực sự cần distributed atomicity. Kiểm thử từng datasource, transaction rollback, restart và connection pool sẽ giúp cấu hình nhiều database vận hành có thể dự đoán.
