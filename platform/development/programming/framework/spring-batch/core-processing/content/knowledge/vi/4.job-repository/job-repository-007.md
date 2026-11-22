# JobRepository dùng database ngoài

Spring Batch cần lưu metadata để biết Job nào đã chạy, mỗi lần thực thi có trạng thái gì, Step đã xử lý đến đâu và có thể restart từ trạng thái nào. Thành phần chịu trách nhiệm quản lý metadata này là **JobRepository**.

Trong ứng dụng thực tế, metadata thường được lưu trong một cơ sở dữ liệu quan hệ bên ngoài tiến trình ứng dụng, chẳng hạn PostgreSQL, MySQL, Oracle hoặc SQL Server. Database này có thể là database đang lưu dữ liệu nghiệp vụ hoặc một database riêng dành cho batch. Việc dùng database bền vững giúp lịch sử thực thi tồn tại sau khi ứng dụng khởi động lại và cho phép nhiều instance ứng dụng cùng làm việc với một kho metadata.

## 1. JobRepository lưu những dữ liệu gì?

JobRepository là nơi Spring Batch tạo, truy vấn và cập nhật metadata của JobInstance, JobExecution, StepExecution và ExecutionContext. Metadata mô tả quá trình chạy, không phải dữ liệu nghiệp vụ mà Job đang nhập hoặc biến đổi.

Trong schema JDBC mặc định, các bảng quan trọng thường gồm:

| Bảng | Vai trò |
| --- | --- |
| **BATCH_JOB_INSTANCE** | Lưu các JobInstance, gồm tên Job và định danh instance |
| **BATCH_JOB_EXECUTION** | Lưu từng lần thực thi Job, trạng thái và thời điểm thực thi |
| **BATCH_JOB_EXECUTION_PARAMS** | Lưu JobParameters của một JobExecution |
| **BATCH_STEP_EXECUTION** | Lưu metadata của từng lần thực thi Step, ví dụ read count, write count, skip count và trạng thái |
| **BATCH_JOB_EXECUTION_CONTEXT** | Lưu ExecutionContext ở cấp JobExecution |
| **BATCH_STEP_EXECUTION_CONTEXT** | Lưu ExecutionContext ở cấp StepExecution |

Tùy database và phiên bản Spring Batch, schema còn có các sequence hoặc cơ chế cấp ID tương ứng. Các bảng liên kết với nhau bằng khóa chính và khóa ngoại để giữ quan hệ giữa JobInstance, JobExecution và StepExecution.

Ví dụ, một Job nhập đơn hàng có thể có một JobInstance cho ngày nghiệp vụ 15/11/2026. Nếu lần chạy đầu thất bại và sau đó được restart, JobRepository lưu hai JobExecution liên kết với cùng JobInstance. Metadata của Step cũng được lưu để Spring Batch biết Step nào đã hoàn thành và trạng thái checkpoint nào có thể khôi phục.

~~~text
Database metadata của Spring Batch
    |
    +-- BATCH_JOB_INSTANCE
    |       |
    |       +-- BATCH_JOB_EXECUTION
    |               |
    |               +-- BATCH_JOB_EXECUTION_PARAMS
    |               +-- BATCH_JOB_EXECUTION_CONTEXT
    |               |
    |               +-- BATCH_STEP_EXECUTION
    |                       |
    |                       +-- BATCH_STEP_EXECUTION_CONTEXT
    |
    +-- Các sequence / đối tượng hỗ trợ cấp ID
~~~

JobRepository cho phép Spring Batch quản lý vòng đời và khả năng restart dựa trên dữ liệu bền vững. Nếu chỉ lưu metadata trong bộ nhớ, thông tin đó có thể mất khi tiến trình kết thúc; repository JDBC giúp duy trì lịch sử qua các lần khởi động ứng dụng.

## 2. Database metadata có thể là database riêng

Có hai cách bố trí phổ biến:

**Dùng chung database:** JobRepository lưu metadata trong cùng database với dữ liệu nghiệp vụ. Cách này thường đơn giản hơn vì ứng dụng chỉ cần một kết nối và có thể dùng chung transaction manager nếu các thao tác nằm trên cùng DataSource.

**Dùng database riêng:** JobRepository lưu metadata ở một database chuyên dụng, còn ItemReader, ItemWriter hoặc service nghiệp vụ truy cập database khác. Cách này giúp tách tải, quyền truy cập và vòng đời metadata khỏi dữ liệu nghiệp vụ.

~~~text
Phương án A: Dùng chung database

Spring Batch Application
       |
       v
Business Database
       |
       +-- Bảng dữ liệu nghiệp vụ
       |
       +-- BATCH_JOB_INSTANCE
       +-- BATCH_JOB_EXECUTION
       +-- BATCH_STEP_EXECUTION


Phương án B: Tách database

Spring Batch Application
       |
       +----------------------+
       |                      |
       v                      v
Business Database       Batch Metadata Database
       |                      |
       +-- Orders              +-- BATCH_JOB_INSTANCE
       +-- Customers           +-- BATCH_JOB_EXECUTION
       +-- Import data         +-- BATCH_STEP_EXECUTION
                              +-- ExecutionContext
~~~

Trong phương án tách database, cần cấu hình rõ DataSource dành cho JobRepository và DataSource dùng cho dữ liệu nghiệp vụ. Không nên giả định rằng Spring Batch tự tìm ra database nào chứa metadata.

Việc tách database không làm thay đổi khái niệm JobInstance, JobExecution hay StepExecution. Nó chỉ thay đổi nơi lưu metadata và cách ứng dụng quản lý kết nối, transaction, quyền truy cập và vận hành.

## 3. Kết nối JobRepository đến database bên ngoài với Spring Boot

Nếu ứng dụng Spring Boot chỉ có một DataSource, Spring Batch thường dùng DataSource đó cho metadata repository. Khi DataSource trỏ đến database bên ngoài, metadata cũng được lưu tại database đó.

Ví dụ cấu hình PostgreSQL trong file application.properties:

~~~properties
spring.datasource.url=jdbc:postgresql://db-host:5432/batch_metadata
spring.datasource.username=batch_user
spring.datasource.password=replace-with-secret
spring.datasource.driver-class-name=org.postgresql.Driver

# Khởi tạo schema Batch khi triển khai môi trường cần tạo bảng.
spring.batch.jdbc.initialize-schema=always
~~~

Các giá trị kết nối nên được cung cấp qua biến môi trường hoặc secret manager. Không nên commit mật khẩu database vào source code hay file cấu hình được đưa lên repository.

Nếu dùng database khác, cần thêm JDBC driver tương ứng và khai báo URL, driver cùng thông tin xác thực phù hợp. Ví dụ URL PostgreSQL có dạng:

~~~text
jdbc:postgresql://db-host:5432/batch_metadata
~~~

Khi ứng dụng khởi động, Spring Boot tạo DataSource và cấu hình cơ sở hạ tầng Spring Batch dựa trên cấu hình đó. Nếu schema đã tồn tại và được quản lý bởi công cụ migration, hãy cấu hình ứng dụng không tự khởi tạo lại schema.

### Dùng database riêng cho Batch trong ứng dụng có nhiều DataSource

Một ứng dụng có thể có DataSource chính cho nghiệp vụ và một DataSource thứ hai cho metadata. Với Spring Boot, có thể đánh dấu DataSource dành cho Batch bằng annotation **@BatchDataSource** để cơ chế tự cấu hình nhận diện đúng bean.

Ví dụ minh họa khai báo DataSource cho Batch:

~~~java
@Bean
@BatchDataSource
@ConfigurationProperties("app.batch.datasource")
public DataSource batchDataSource() {
    return DataSourceBuilder.create().build();
}
~~~

Các thuộc tính kết nối tương ứng có thể được đặt trong application.properties:

~~~properties
app.batch.datasource.url=jdbc:postgresql://db-host:5432/batch_metadata
app.batch.datasource.username=batch_user
app.batch.datasource.password=replace-with-secret
app.batch.datasource.driver-class-name=org.postgresql.Driver
~~~

Ứng dụng vẫn cần cấu hình DataSource nghiệp vụ riêng theo cách phù hợp với cấu trúc của nó. Trong ứng dụng nhiều DataSource, cần khai báo rõ bean nào là primary và kiểm tra các transaction manager được inject vào từng thành phần. Cấu hình trên chỉ minh họa cách đánh dấu Batch DataSource; nó không thay thế việc thiết kế transaction manager cho các Step.

Nếu tự thêm **@EnableBatchProcessing** vào ứng dụng Spring Boot, cơ chế tự cấu hình Batch của Boot sẽ lùi lại. Khi đó, ứng dụng phải chịu trách nhiệm cấu hình cơ sở hạ tầng Batch và khởi tạo schema theo cách riêng. Không nên thêm annotation này chỉ để chỉ định một DataSource nếu cấu hình Boot hiện tại đã đáp ứng yêu cầu.

## 4. Cấu hình JobRepository bằng Java configuration

Trong cấu hình Spring Batch không dựa vào Spring Boot auto-configuration, có thể chỉ định DataSource và transaction manager dành cho JobRepository qua **@EnableBatchProcessing**.

Ví dụ dùng một database riêng cho metadata:

~~~java
@Configuration
@EnableBatchProcessing(
        dataSourceRef = "batchDataSource",
        transactionManagerRef = "batchTransactionManager"
)
public class BatchInfrastructureConfiguration {

    @Bean
    public DataSource batchDataSource() {
        return DataSourceBuilder.create()
                .url("jdbc:postgresql://db-host:5432/batch_metadata")
                .username("batch_user")
                .password(System.getenv("BATCH_METADATA_DB_PASSWORD"))
                .driverClassName("org.postgresql.Driver")
                .build();
    }

    @Bean
    public PlatformTransactionManager batchTransactionManager(
            @Qualifier("batchDataSource") DataSource batchDataSource) {
        return new DataSourceTransactionManager(batchDataSource);
    }
}
~~~

Trong ứng dụng thực tế, nên đưa URL và username vào externalized configuration như application.properties hoặc biến môi trường; đoạn code trên chỉ minh họa cách nối hai thành phần.

Hai thuộc tính của annotation có ý nghĩa:

- **dataSourceRef** chỉ bean DataSource được JobRepository sử dụng để lưu metadata.
- **transactionManagerRef** chỉ transaction manager quản lý các thao tác repository trên DataSource đó.

Tên bean phải khớp với giá trị tham chiếu. Nếu bỏ qua các thuộc tính này, cơ sở hạ tầng Batch sẽ tìm các bean theo tên mặc định của cấu hình. Với ứng dụng có nhiều DataSource, nên khai báo rõ để tránh vô tình ghi metadata vào database nghiệp vụ hoặc database không mong muốn.

Một cách khác là mở rộng **DefaultBatchConfiguration** và cung cấp các thành phần cơ sở hạ tầng theo API của phiên bản Spring Batch đang dùng. Chỉ nên chọn một hướng cấu hình cơ sở hạ tầng phù hợp; không kết hợp tùy tiện nhiều cơ chế cấu hình Batch trong cùng ứng dụng.

## 5. Cấu hình transaction manager cho Step

JobRepository cần một transaction manager để quản lý các thao tác metadata. TaskletStep hoặc chunk-oriented Step cũng cần transaction manager cho công việc mà Step thực hiện. Hai vai trò này có thể dùng chung một transaction manager hoặc dùng các transaction manager khác nhau tùy cách bố trí database.

Nếu metadata và dữ liệu nghiệp vụ cùng nằm trên một DataSource, thường có thể dùng chung transaction manager:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

Nếu metadata và dữ liệu nghiệp vụ nằm ở hai database khác nhau, cần xác định transaction manager của Step một cách tường minh. Ví dụ Step ghi dữ liệu đơn hàng vào business database:

~~~java
@Bean
public PlatformTransactionManager businessTransactionManager(
        @Qualifier("businessDataSource") DataSource businessDataSource) {
    return new DataSourceTransactionManager(businessDataSource);
}

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        @Qualifier("businessTransactionManager")
        PlatformTransactionManager businessTransactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, businessTransactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

Trong cấu hình này, transaction manager truyền vào chunk điều khiển transaction của công việc nghiệp vụ. JobRepository được cấu hình với batchTransactionManager để quản lý metadata. Cần hiểu rằng hai transaction manager độc lập không tự tạo thành một transaction phân tán.

Nếu transaction nghiệp vụ commit thành công nhưng cập nhật metadata thất bại, hoặc metadata được cập nhật trong khi transaction nghiệp vụ rollback, trạng thái giữa hai database có thể không đồng bộ như mong đợi. Việc dùng hai DataSource không tự bảo đảm tính nguyên tử xuyên suốt cả hai hệ thống.

Nếu yêu cầu bắt buộc cả dữ liệu nghiệp vụ và metadata phải commit hoặc rollback cùng nhau, cần xem xét giải pháp transaction phân tán phù hợp như JTA/XA với các resource hỗ trợ. Đây là quyết định có chi phí vận hành và độ phức tạp cao hơn. Với nhiều hệ thống batch, thiết kế idempotent, checkpoint rõ ràng và quy trình đối soát thường là một phần quan trọng của chiến lược phục hồi.

## 6. Khởi tạo schema cho database ngoài

JobRepository JDBC cần các bảng metadata và đối tượng hỗ trợ tương ứng. Spring Batch cung cấp script schema theo các hệ quản trị cơ sở dữ liệu được hỗ trợ. Cần dùng script phù hợp với database và phiên bản Spring Batch đang chạy.

Với Spring Boot, thuộc tính:

~~~properties
spring.batch.jdbc.initialize-schema=always
~~~

cho phép cơ chế khởi tạo schema chạy khi ứng dụng khởi động. Đây là lựa chọn tiện lợi trong môi trường phát triển hoặc môi trường thử nghiệm cần dựng database nhanh.

Trong môi trường production, schema thường được tạo và nâng cấp qua công cụ migration như Flyway hoặc Liquibase. Khi migration chịu trách nhiệm quản lý schema, ứng dụng có thể đặt:

~~~properties
spring.batch.jdbc.initialize-schema=never
~~~

Quy trình triển khai khi đó gồm:

1. Chọn đúng script schema đi kèm phiên bản Spring Batch đang sử dụng.
2. Tạo migration tương ứng cho database đích.
3. Chạy migration bằng tài khoản triển khai có quyền DDL.
4. Cấp cho tài khoản runtime quyền cần thiết để đọc, ghi và cập nhật metadata.
5. Khởi động ứng dụng với chế độ tự khởi tạo schema được tắt.

Không nên lấy script của một phiên bản Spring Batch bất kỳ rồi dùng lâu dài cho mọi phiên bản. Cấu trúc bảng, kiểu dữ liệu, sequence và cách lưu tham số có thể thay đổi khi nâng cấp framework. Migration phải được đối chiếu với phiên bản đang triển khai.

Nếu sử dụng **@EnableBatchProcessing** trong cấu hình Spring Batch thuần, không nên mặc định rằng annotation này sẽ tự tạo bảng trong database. Cần chủ động chọn cách chạy schema script hoặc migration. Trong ứng dụng Spring Boot, việc thêm annotation này cũng làm thay đổi hành vi auto-configuration và schema initializer của Boot.

## 7. Quyền truy cập và cấu hình database

Tài khoản database dùng cho JobRepository cần đủ quyền để Spring Batch thực hiện các thao tác metadata. Trong giai đoạn triển khai schema, tài khoản migration có thể cần quyền tạo bảng, index, sequence và constraint. Tài khoản chạy ứng dụng thường chỉ cần các quyền DML và quyền sử dụng sequence cần thiết.

Nên tách quyền triển khai schema và quyền runtime nếu chính sách bảo mật yêu cầu. Không nhất thiết cấp quyền tạo hoặc xóa bảng cho tiến trình batch chạy hằng ngày.

Các thông tin cần cấu hình và kiểm tra gồm:

| Thành phần | Nội dung cần xác nhận |
| --- | --- |
| JDBC driver | Driver tương thích với database và phiên bản Java |
| JDBC URL | Host, port, database hoặc service name chính xác |
| Credentials | Tài khoản runtime và secret được cấp đúng |
| Network | Ứng dụng truy cập được host và port database |
| Connection pool | Kích thước pool phù hợp số Job/Step và tải đồng thời |
| Schema | Bảng, index, sequence và constraint đã được tạo đúng phiên bản |
| Permissions | Runtime user có quyền đọc, ghi và cập nhật metadata |
| Timeouts | Connection timeout, socket timeout và transaction timeout phù hợp |

JobRepository là thành phần được truy cập trong quá trình khởi chạy Job, cập nhật Step và lưu checkpoint. Nếu database metadata không khả dụng, ứng dụng có thể không khởi chạy hoặc không thể cập nhật trạng thái thực thi đúng cách. Vì vậy, cần giám sát kết nối và dung lượng của database này như một thành phần quan trọng của hệ thống batch.

## 8. Dùng chung JobRepository cho nhiều instance ứng dụng

Một lợi ích lớn của database metadata bên ngoài là nhiều instance của cùng ứng dụng có thể dùng chung một JobRepository. Ví dụ hai node cùng triển khai Job nhập đơn hàng có thể nhìn thấy metadata của các lần chạy được khởi tạo từ node còn lại.

~~~text
          Scheduler / Job Operator
                    |
          +---------+---------+
          |                   |
          v                   v
      Batch Node A         Batch Node B
          |                   |
          +---------+---------+
                    |
                    v
          Shared JobRepository
          (External Database)
                    |
                    v
          BATCH_JOB_INSTANCE
          BATCH_JOB_EXECUTION
          BATCH_STEP_EXECUTION
~~~

JobRepository và các ràng buộc trong schema giúp điều phối danh tính JobInstance và các lần thực thi. Khi nhiều node đồng thời yêu cầu chạy cùng một Job với cùng identifying parameters, repository phải bảo vệ việc tạo instance khỏi các lần tạo trùng. Thuộc tính isolation level khi tạo JobExecution có vai trò trong việc xử lý cạnh tranh này.

Với Spring Boot, có thể cấu hình mức isolation dùng khi tạo JobExecution:

~~~properties
spring.batch.jdbc.isolation-level-for-create=SERIALIZABLE
~~~

Giá trị mặc định thường được chọn để bảo vệ thao tác tạo execution khỏi cạnh tranh. Chỉ thay đổi isolation level khi đã hiểu đặc tính database, tải đồng thời và hành vi khi có nhiều yêu cầu khởi chạy cùng lúc. Hạ mức isolation để giảm lock mà không kiểm tra có thể làm tăng nguy cơ race condition hoặc lỗi tạo metadata.

Các node phải dùng cùng một schema metadata tương thích, cùng cách đặt Job name và cùng quy ước JobParameters. Không nên để hai phiên bản ứng dụng không tương thích cùng ghi vào một schema nếu chưa có kế hoạch nâng cấp và kiểm soát tương thích rõ ràng.

## 9. Table prefix và tách biệt metadata

Schema mặc định sử dụng prefix **BATCH_** cho các bảng metadata. Trong một số môi trường, ứng dụng có thể cần đổi prefix để phân biệt metadata của các nhóm Job hoặc tránh trùng tên với bảng khác.

Với Spring Boot, có thể cấu hình:

~~~properties
spring.batch.jdbc.table-prefix=APP_BATCH_
~~~

Với cấu hình Spring Batch thuần, có thể chỉ định table prefix qua thuộc tính của **@EnableBatchProcessing** hoặc cấu hình JobRepository theo cơ chế được phiên bản framework hỗ trợ.

Khi đổi prefix, tên bảng trong database phải khớp với cấu hình của repository. Việc chỉ đổi property mà không tạo hoặc đổi tên bảng tương ứng sẽ khiến các câu SQL metadata không tìm thấy bảng.

Table prefix không thay thế việc chọn database hoặc schema. Nếu muốn tách biệt bằng database schema, cần cấu hình quyền và schema mặc định của tài khoản kết nối, hoặc cấu hình tên đối tượng theo cách database và framework hỗ trợ.

## 10. Truy vấn metadata để kiểm tra JobRepository

Sau khi ứng dụng chạy, có thể truy vấn metadata để xác nhận repository đang ghi vào database ngoài. Ví dụ truy vấn các JobExecution gần đây:

~~~sql
SELECT
    JOB_EXECUTION_ID,
    JOB_INSTANCE_ID,
    STATUS,
    START_TIME,
    END_TIME,
    EXIT_CODE
FROM BATCH_JOB_EXECUTION
ORDER BY JOB_EXECUTION_ID DESC;
~~~

Để xem JobInstance và các execution liên quan:

~~~sql
SELECT
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_INSTANCE ji
LEFT JOIN BATCH_JOB_EXECUTION je
    ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
ORDER BY ji.JOB_INSTANCE_ID DESC, je.JOB_EXECUTION_ID DESC;
~~~

Tên bảng và một số cột có thể khác nếu dùng table prefix tùy chỉnh hoặc schema của phiên bản khác. Hãy đối chiếu schema thực tế trước khi chạy truy vấn trong môi trường vận hành.

Trong ứng dụng, **JobExplorer** cung cấp API đọc metadata thay vì buộc code nghiệp vụ tự truy vấn các bảng nội bộ. Có thể dùng JobExplorer để tra cứu JobInstance, JobExecution và trạng thái Step thông qua API của Spring Batch. Cách này giữ code ít phụ thuộc vào cấu trúc SQL nội bộ hơn.

Không nên cập nhật hoặc xóa trực tiếp các hàng metadata để cố sửa trạng thái Job. Các bảng có quan hệ khóa ngoại và trạng thái thực thi liên quan chặt chẽ với nhau. Thay đổi thủ công có thể làm hỏng khả năng restart hoặc khiến repository hiểu sai lịch sử. Hãy dùng API vận hành phù hợp và quy trình quản trị metadata đã được kiểm soát.

## 11. Lỗi thường gặp khi dùng database ngoài

### Không tìm thấy bảng metadata

Các lỗi như table not found hoặc bad SQL grammar thường xảy ra khi schema chưa được tạo, tạo sai schema, sai table prefix hoặc ứng dụng kết nối nhầm database.

Hãy kiểm tra JDBC URL, database hiện tại, schema mặc định của user, tên bảng, prefix và kết quả migration. Đừng chỉ kiểm tra xem database server có hoạt động hay không.

### Script schema không tương thích

Một script của database hoặc phiên bản Spring Batch khác có thể tạo sai kiểu cột, sequence hoặc constraint. Hãy dùng script tương ứng với database và phiên bản dependency đang chạy, sau đó quản lý nâng cấp bằng migration có kiểm soát.

### Tài khoản runtime thiếu quyền

Ứng dụng có thể kết nối được nhưng thất bại khi insert, update hoặc lấy ID từ sequence. Kiểm tra quyền trên từng bảng và sequence, không chỉ quyền kết nối database.

### Ứng dụng ghi metadata vào nhầm DataSource

Vấn đề thường xuất hiện khi có nhiều DataSource hoặc nhiều transaction manager. Hãy xác nhận DataSource được JobRepository sử dụng, bean được đánh dấu primary, qualifier và các tham chiếu trong cấu hình Batch.

### Không kết nối được database bên ngoài

Kiểm tra DNS, firewall, network route, port, TLS, JDBC driver, credentials và giới hạn kết nối của database. Connection pool cạn cũng có thể làm Job không khởi tạo hoặc không cập nhật metadata được.

### Hai node khởi chạy cùng Job đồng thời

Khi có nhiều scheduler hoặc nhiều node, cùng một JobInstance có thể bị yêu cầu chạy đồng thời. Hãy dùng chung repository, giữ schema và transaction configuration tương thích, đồng thời kiểm tra isolation level khi tạo execution. Không tự ý xóa metadata hoặc thay đổi identifying parameters để né lỗi cạnh tranh.

### Metadata và dữ liệu nghiệp vụ không đồng bộ

Nếu JobRepository và business data dùng hai transaction manager độc lập, một bên có thể commit trong khi bên kia thất bại. Hãy đánh giá ranh giới transaction, khả năng idempotent, checkpoint và quy trình đối soát. Nếu cần atomicity xuyên nhiều database, cần giải pháp transaction phân tán tương ứng.

### Restart không khôi phục đúng vị trí

JobRepository chỉ lưu metadata và ExecutionContext mà các thành phần ghi vào đó. Nếu custom reader hoặc Tasklet không lưu trạng thái cần thiết, restart không thể tự suy ra vị trí xử lý từ dữ liệu nghiệp vụ. Hãy triển khai cơ chế ItemStream hoặc checkpoint phù hợp.

## 12. Các nguyên tắc vận hành lâu dài

Database metadata thường nhỏ hơn database nghiệp vụ nhưng có vai trò quan trọng đối với khả năng điều khiển và phục hồi Job. Nên có kế hoạch vận hành riêng cho nó:

- **Backup và restore:** bảo vệ metadata cùng với dữ liệu cần thiết để phục hồi ứng dụng. Sau khi restore, kiểm tra tính tương thích giữa metadata, schema và phiên bản ứng dụng.
- **Migration:** nâng cấp schema theo từng phiên bản Spring Batch và kiểm thử migration trước khi triển khai production.
- **Monitoring:** theo dõi connection pool, số lượng connection, latency, lock, deadlock, dung lượng database và lỗi truy vấn.
- **Retention:** xác định thời gian lưu metadata và quy trình archive hoặc dọn dẹp có kiểm soát. Không xóa riêng lẻ các hàng có quan hệ khóa ngoại.
- **Security:** lưu credentials trong secret manager, mã hóa kết nối khi phù hợp và giới hạn quyền của runtime user.
- **High availability:** đánh giá khả năng failover của database metadata vì sự cố tại đây có thể ảnh hưởng đến việc khởi chạy và cập nhật trạng thái Job.
- **Compatibility:** các node dùng chung repository phải tương thích về schema, Job name, JobParameters và cách triển khai Job.

JobRepository là một phần của trạng thái vận hành batch. Nếu database metadata mất hoặc bị hỏng, ứng dụng có thể mất khả năng tra cứu lịch sử và restart an toàn, ngay cả khi dữ liệu nghiệp vụ vẫn còn nguyên.

## 13. Quy trình cấu hình một JobRepository dùng database ngoài

Khi triển khai một ứng dụng mới, có thể thực hiện theo trình tự sau:

1. **Chọn nơi lưu metadata:** dùng chung database nghiệp vụ hay tạo database riêng cho Batch.
2. **Chuẩn bị database:** tạo database hoặc schema, user, quyền và network access.
3. **Khai báo DataSource:** cấu hình JDBC driver, URL, credentials, pool và secret.
4. **Chọn transaction manager:** xác định transaction manager cho JobRepository và cho từng Step.
5. **Khởi tạo schema:** dùng script tương ứng phiên bản Spring Batch hoặc migration được quản lý.
6. **Cấu hình JobRepository:** dùng auto-configuration của Spring Boot hoặc chỉ định DataSource và transaction manager trong Java configuration.
7. **Kiểm tra metadata:** chạy một Job thử nghiệm, truy vấn JobInstance và JobExecution để xác nhận dữ liệu được ghi vào đúng database.
8. **Kiểm tra restart:** cho một lần chạy thất bại có kiểm soát rồi khởi động lại với cùng identifying parameters để xác nhận metadata được lưu bền vững.
9. **Kiểm tra vận hành:** thử kết nối lại sau khi ứng dụng restart và xác nhận các node dùng chung repository nhìn thấy cùng lịch sử thực thi.

Không nên coi việc ứng dụng kết nối thành công là bằng chứng duy nhất rằng JobRepository đã cấu hình đúng. Cần xác nhận cả schema, quyền ghi metadata, transaction behavior và khả năng đọc lại lịch sử thực thi.

## Kết luận

JobRepository dùng database ngoài giúp Spring Batch lưu metadata bền vững, hỗ trợ restart và chia sẻ lịch sử thực thi giữa nhiều instance ứng dụng. Cấu hình cốt lõi gồm DataSource đúng, schema tương thích với phiên bản Spring Batch, transaction manager phù hợp và quyền truy cập database. Khi metadata và dữ liệu nghiệp vụ nằm ở hai database khác nhau, cần thiết kế rõ ranh giới transaction, checkpoint và khả năng phục hồi để tránh trạng thái không đồng bộ.
