# Chọn database và datasource cho metadata

`JobRepository` là nơi Spring Batch lưu metadata để theo dõi job và step: JobInstance, JobExecution, StepExecution và ExecutionContext. Metadata cho phép framework phân biệt các lần chạy, ngăn khởi chạy trùng, theo dõi trạng thái và tiếp tục công việc sau khi execution thất bại hoặc dừng.

Vì vậy, database dùng cho metadata là một phần của thiết kế vận hành batch. Cần chọn hệ quản trị cơ sở dữ liệu phù hợp, cấu hình đúng `DataSource` và transaction manager, chuẩn bị schema theo phiên bản Spring Batch, đồng thời quyết định metadata dùng chung database với dữ liệu nghiệp vụ hay được đặt riêng.

## 1. JobRepository lưu những gì?

`JobRepository` lưu trạng thái điều khiển của Spring Batch, không phải nơi mặc định lưu toàn bộ dữ liệu nghiệp vụ mà job đang xử lý. Với JDBC JobRepository, metadata được lưu trong các bảng như:

| Nhóm bảng | Nội dung chính |
|---|---|
| `BATCH_JOB_INSTANCE` | Danh tính các JobInstance theo job name và identifying parameters |
| `BATCH_JOB_EXECUTION` | Các lần thực thi của JobInstance, trạng thái và thời điểm chạy |
| `BATCH_JOB_EXECUTION_PARAMS` | JobParameters của từng JobExecution |
| `BATCH_STEP_EXECUTION` | Lịch sử thực thi của từng step, số bản ghi đọc/ghi và trạng thái |
| Các bảng `*_CONTEXT` | ExecutionContext của job và step, dùng lưu trạng thái phục hồi |
| Sequence hoặc cấu trúc cấp mã tương ứng | Cấp ID cho các bản ghi metadata |

Tên bảng và chi tiết schema phụ thuộc phiên bản Spring Batch và hệ quản trị database. Các script schema đi kèm Spring Batch cung cấp cấu trúc phù hợp cho từng loại database được hỗ trợ.

Ví dụ, một job nhập đơn hàng có thể ghi dữ liệu đơn hàng vào bảng nghiệp vụ `ORDERS`, còn `JobRepository` ghi trạng thái chạy vào các bảng `BATCH_*`. Khi job thất bại, dữ liệu metadata giúp Spring Batch biết step nào đã hoàn thành và checkpoint gần nhất nằm ở đâu.

## 2. Tiêu chí chọn database cho metadata

Với môi trường phát triển và kiểm thử, database nhúng có thể thuận tiện vì dễ khởi tạo và dọn dẹp. Với môi trường production, nên dùng một relational database có lưu trữ bền vững và transaction phù hợp với ứng dụng.

Các tiêu chí cần xem xét:

1. **Được Spring Batch hỗ trợ.** Chọn hệ quản trị có schema script tương ứng trong phiên bản Spring Batch đang dùng. Kiểm tra tài liệu và script đi kèm đúng dependency thay vì lấy schema từ một phiên bản khác.
2. **Transaction và locking đáng tin cậy.** Repository tạo và cập nhật metadata trong các transaction. Database phải hỗ trợ các mức cô lập và cơ chế khóa cần thiết cho cách chạy batch của hệ thống.
3. **Lưu trữ bền vững.** Metadata phải còn sau khi ứng dụng restart hoặc một node bị lỗi. Database cần có backup, phục hồi và chính sách lưu trữ phù hợp.
4. **Dùng chung được giữa các instance ứng dụng.** Nếu job có thể được khởi chạy từ nhiều node, các node phải cùng truy cập một repository có tính nhất quán để nhận diện JobInstance và execution.
5. **Đáp ứng tải ghi và truy vấn.** Metadata thường nhỏ hơn dữ liệu nghiệp vụ, nhưng job nhiều step, nhiều chunk hoặc nhiều partition có thể tạo lượng cập nhật đáng kể.
6. **Có công cụ vận hành sẵn có.** Đội ngũ cần giám sát kết nối, dung lượng, lock, backup, quyền truy cập và lịch bảo trì database.

Các relational database phổ biến có thể được sử dụng khi phiên bản Spring Batch cung cấp schema tương ứng và cấu hình driver phù hợp. Không nên chọn database chỉ vì ứng dụng nghiệp vụ đang dùng nó; hãy xác nhận transaction, schema, locking và vận hành đều đáp ứng yêu cầu.

### Vì sao không nên dùng database trong bộ nhớ ở production?

Database nhúng trong bộ nhớ như H2 rất hữu ích cho demo và test. Tuy nhiên, khi JVM kết thúc, dữ liệu của một database in-memory thường bị mất. Nếu metadata biến mất, Spring Batch không còn lịch sử JobInstance, JobExecution và ExecutionContext để nhận diện lần chạy cũ hoặc phục hồi checkpoint.

Một database nhúng dạng file có thể giữ dữ liệu qua lần restart tiến trình, nhưng vẫn cần xem xét khả năng truy cập đồng thời, độ bền, backup, HA và hỗ trợ vận hành. Với hệ thống production hoặc nhiều node, database dùng chung có quản trị thường là lựa chọn phù hợp hơn.

## 3. Chọn một hay nhiều DataSource?

Spring Batch cần một `DataSource` cho JDBC JobRepository. Ứng dụng cũng có thể có một hoặc nhiều datasource để đọc/ghi dữ liệu nghiệp vụ. Có hai mô hình thường gặp.

### Dùng chung DataSource cho metadata và dữ liệu nghiệp vụ

Trong mô hình đơn giản, metadata và dữ liệu nghiệp vụ cùng nằm trong một database và dùng chung một `DataSource` cùng transaction manager.

```text
Spring Batch application
        |
        v
   DataSource
        |
        v
   One relational database
        |
        +-- BATCH_* metadata tables
        +-- ORDERS, CUSTOMERS, ... business tables
```

Ưu điểm:

- Cấu hình đơn giản, ít connection pool và ít thành phần cần vận hành.
- Có thể dùng cùng transaction manager cho metadata và dữ liệu nghiệp vụ khi các thao tác dùng chung transaction resource.
- Dễ kiểm tra trạng thái batch cùng dữ liệu được xử lý trong một database.

Điểm cần cân nhắc là tải batch và dữ liệu nghiệp vụ chia sẻ tài nguyên database. Các job ghi nhiều chunk có thể làm tăng contention, dung lượng log hoặc áp lực connection. Quyền truy cập cũng cần được giới hạn để code nghiệp vụ không tùy tiện sửa bảng metadata.

### Tách DataSource cho metadata và dữ liệu nghiệp vụ

Ứng dụng có thể dùng một database hoặc schema riêng cho metadata, và một datasource khác cho dữ liệu nghiệp vụ:

```text
Spring Batch application
        |
        +--> batchDataSource ------> Batch metadata database
        |                             BATCH_* tables
        |
        +--> businessDataSource --> Business database
                                      ORDERS, CUSTOMERS, ...
```

Mô hình này hữu ích khi cần tách quyền truy cập, backup, vòng đời dữ liệu, tài nguyên hoặc tải truy vấn. Nó cũng cho phép quản trị metadata theo chính sách riêng.

Đổi lại, ứng dụng phải quản lý nhiều connection pool, datasource, transaction manager và cấu hình khởi tạo schema. Nếu metadata và dữ liệu nghiệp vụ nằm ở hai database khác nhau, transaction JDBC cục bộ thường không thể commit nguyên tử cả hai nơi. Có thể xảy ra tình huống dữ liệu nghiệp vụ đã commit nhưng checkpoint metadata chưa được ghi, hoặc metadata đã cập nhật nhưng thao tác nghiệp vụ ở database khác chưa hoàn tất.

Vì thế, khi tách database, cần thiết kế thao tác ghi có tính idempotent, khóa nghiệp vụ duy nhất, cơ chế đối soát hoặc quy trình bù trừ phù hợp. Không nên giả định hai datasource riêng tự động tạo thành một transaction thống nhất.

## 4. Transaction manager phải khớp với datasource

`JobRepository` dùng `DataSource` để lưu metadata và một `PlatformTransactionManager` để quản lý transaction cho các thao tác repository. Các step cũng cần transaction manager phù hợp với tài nguyên nghiệp vụ mà chúng đọc hoặc ghi.

Khi metadata và dữ liệu nghiệp vụ dùng cùng database và cùng transaction resource, có thể dùng chung datasource và transaction manager. Cách này giúp phối hợp cập nhật dữ liệu chunk và trạng thái batch trong transaction theo cấu hình của step và repository.

Khi dùng datasource riêng, hãy cấu hình transaction manager cho JobRepository trỏ đến batch datasource. Step ghi dữ liệu nghiệp vụ phải dùng transaction manager của business datasource. Nếu cần tính nguyên tử xuyên hai database, cần một giải pháp transaction phân tán được thiết kế và hỗ trợ rõ ràng; nếu không, hãy thiết kế để có thể phục hồi khi một phía commit còn phía kia chưa commit.

Không nên vô tình gắn `batchTransactionManager` cho step ghi dữ liệu vào `businessDataSource`, hoặc ngược lại. Transaction manager quản lý tài nguyên mà nó được tạo ra để quản lý; dùng sai manager có thể khiến thao tác không nằm trong transaction mong muốn.

## 5. Cấu hình một DataSource dùng chung

Với ứng dụng Spring Boot chỉ có một datasource, Boot thường có thể dùng datasource đó cho Spring Batch và tự cấu hình JobRepository. Ví dụ cấu hình kết nối PostgreSQL:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: batch_app
    password: ${ORDERS_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver

  batch:
    jdbc:
      initialize-schema: never
```

Ở ví dụ này, `initialize-schema: never` giả định schema metadata đã được tạo và quản lý bằng quy trình migration của môi trường. Trong môi trường thử nghiệm, có thể cấu hình Spring Boot khởi tạo schema tự động thay vì dùng migration riêng.

Với cấu hình Java thủ công của Spring Batch 5, `@EnableBatchProcessing` có thể chỉ rõ datasource và transaction manager dùng cho hạ tầng batch:

```java
@Configuration
@EnableBatchProcessing(
    dataSourceRef = "dataSource",
    transactionManagerRef = "transactionManager"
)
public class BatchConfiguration {
    // Khai báo Job và Step beans tại đây.
}
```

Khi Spring Boot đã tự cấu hình batch infrastructure, không thêm `@EnableBatchProcessing` chỉ để khai báo lại cấu hình mặc định. Việc bật annotation này làm ứng dụng chuyển sang cấu hình hạ tầng batch tường minh và có thể khiến một số auto-configuration của Spring Boot không còn áp dụng. Chỉ dùng khi chủ động quản lý cấu hình infrastructure.

## 6. Cấu hình datasource riêng cho metadata

Khi ứng dụng có nhiều datasource, hãy chỉ rõ datasource nào được dùng cho batch metadata. Với cấu hình Spring Batch 5 tường minh, có thể khai báo tên bean trong `@EnableBatchProcessing`.

Ví dụ cấu hình rút gọn:

```java
@Configuration
@EnableBatchProcessing(
    dataSourceRef = "batchDataSource",
    transactionManagerRef = "batchTransactionManager"
)
public class BatchInfrastructureConfiguration {

    @Bean
    @ConfigurationProperties("app.datasource.batch")
    DataSource batchDataSource() {
        return DataSourceBuilder.create().build();
    }

    @Bean
    PlatformTransactionManager batchTransactionManager(
            @Qualifier("batchDataSource") DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

Các import cần thiết gồm `DataSourceBuilder`, `ConfigurationProperties`, `Qualifier`, `DataSource`, `JdbcTransactionManager` và các annotation Spring tương ứng. Cấu hình properties phải cung cấp URL, username, password và driver phù hợp.

Với Spring Boot, một datasource được đánh dấu `@BatchDataSource` có thể được auto-configuration nhận diện làm datasource cho Spring Batch. Cách này phù hợp khi muốn giữ auto-configuration của Boot. Chọn một phương thức cấu hình nhất quán; tránh vừa tự bật hạ tầng bằng `@EnableBatchProcessing` vừa mong Boot tiếp tục tạo cùng các bean batch tự động.

Khi tách datasource, hãy khai báo business datasource và transaction manager riêng cho các step thao tác dữ liệu nghiệp vụ. Ví dụ, step chunk ghi vào database đơn hàng phải dùng transaction manager gắn với business datasource đó.

## 7. Tạo và quản lý schema metadata

Spring Batch cung cấp script schema theo database. Script cần được lấy từ đúng phiên bản thư viện đang chạy. Không nên sao chép một file schema cũ vào dự án rồi nâng phiên bản Spring Batch mà không kiểm tra thay đổi metadata.

Trong Spring Boot, thuộc tính `spring.batch.jdbc.initialize-schema` thường được dùng để điều khiển việc khởi tạo schema:

| Giá trị | Ý nghĩa thường dùng |
|---|---|
| `embedded` | Khởi tạo schema tự động khi nhận diện embedded database |
| `always` | Luôn chạy script khởi tạo schema |
| `never` | Không tự chạy script; schema được quản lý bên ngoài |

Đối với production, thường nên quản lý DDL bằng công cụ migration như Flyway hoặc Liquibase, sau khi xác nhận script phù hợp với phiên bản Spring Batch. Khi đó đặt cấu hình khởi tạo tự động thành `never` để tránh ứng dụng tự chạy DDL trong lúc khởi động.

Quy trình triển khai schema nên bao gồm:

1. Xác định phiên bản Spring Batch chính xác của ứng dụng.
2. Lấy script schema dành cho database đang sử dụng từ artifact hoặc tài liệu của phiên bản đó.
3. Rà soát khác biệt schema khi nâng cấp thư viện và chuẩn bị migration tương ứng.
4. Chạy migration bằng tài khoản triển khai có quyền DDL.
5. Cấp cho tài khoản runtime các quyền tối thiểu cần thiết để đọc, ghi và cập nhật metadata.
6. Kiểm tra ứng dụng khởi động, tạo JobInstance và JobExecution, thực thi step, rồi truy vấn metadata thành công.

Không nên để nhiều application instance cùng lúc chạy script tạo bảng trong một đợt triển khai. Hãy thực hiện migration theo một bước triển khai được kiểm soát trước khi các instance ứng dụng bắt đầu dùng schema mới.

## 8. Schema, table prefix và quyền truy cập

Các bảng metadata có thể được đặt trong schema riêng để phân tách quyền và trách nhiệm, ví dụ schema `BATCH_META`. Cần cấu hình datasource hoặc database connection để các câu lệnh JDBC truy cập đúng schema, đồng thời tạo bảng theo script đã điều chỉnh phù hợp.

Spring Batch hỗ trợ tùy chỉnh table prefix trong cấu hình JobRepository. Prefix mặc định thường là `BATCH_`; đổi prefix làm thay đổi tên bảng mà repository truy vấn. Prefix không thay thế việc chọn schema hoặc cấp quyền database. Nếu dùng schema riêng, cần bảo đảm script tạo bảng và cấu hình kết nối cùng trỏ đến đúng vị trí.

Có thể tách quyền như sau:

- Tài khoản migration có quyền tạo, sửa và cập nhật schema metadata.
- Tài khoản runtime của batch application có quyền cần thiết để đọc và ghi các bảng metadata.
- Tài khoản nghiệp vụ chỉ được truy cập các bảng dữ liệu mà job cần xử lý.
- Tài khoản người dùng hoặc dịch vụ khác không được sửa trực tiếp metadata nếu không có yêu cầu vận hành được kiểm soát.

Không nên cấp quyền DBA cho tài khoản runtime chỉ để Spring Batch có thể ghi metadata. Quyền tối thiểu giúp hạn chế tác động khi ứng dụng hoặc một câu lệnh SQL gặp lỗi.

## 9. Database và cấu hình khi chạy nhiều instance

Khi nhiều instance của ứng dụng cùng có khả năng khởi chạy hoặc điều phối job, chúng phải dùng chung một JobRepository bền vững. Nếu mỗi node trỏ đến một database metadata riêng, mỗi node có thể không nhìn thấy JobInstance và execution do node còn lại tạo ra. Điều này làm mất khả năng phối hợp và có thể dẫn đến xử lý trùng.

```text
Application node A ----+
                       |
Application node B ----+----> Shared JobRepository database
                       |          BATCH_* metadata
Application node C ----+
```

JobRepository dùng ràng buộc database và transaction để bảo vệ việc tạo metadata, nhận diện instance và cập nhật trạng thái. Cấu hình mức cô lập cho thao tác tạo execution cần phù hợp với database và yêu cầu concurrency. Trong cấu hình JDBC chuẩn, thao tác tạo metadata thường dùng isolation level chặt như `SERIALIZABLE` để giảm nguy cơ hai request đồng thời tạo cùng một JobInstance. Có thể điều chỉnh `isolationLevelForCreate` khi có lý do và đã kiểm chứng trên database cụ thể.

Database dùng chung cần đủ connection capacity cho tất cả node. Đồng thời, cần giám sát lock wait, deadlock, timeout, connection pool và độ trễ ghi metadata. Nếu job chạy lâu hoặc có nhiều partition, tải cập nhật StepExecution và ExecutionContext có thể tăng đáng kể.

## 10. Backup, retention và phục hồi

Metadata là một phần của trạng thái ứng dụng. Backup database nghiệp vụ mà bỏ qua database metadata có thể khiến dữ liệu đã xử lý và trạng thái batch không còn đồng bộ. Ngược lại, phục hồi metadata về một thời điểm khác với dữ liệu nghiệp vụ có thể khiến job restart từ checkpoint không phù hợp với dữ liệu thực tế.

Vì vậy, hãy đưa metadata vào kế hoạch backup và disaster recovery. Nếu metadata và dữ liệu nghiệp vụ ở hai database, cần xác định cách phối hợp thời điểm backup, restore và đối soát sau phục hồi.

Các bảng metadata tăng theo số JobInstance, JobExecution, StepExecution và nội dung ExecutionContext. Hãy xác định thời gian lưu lịch sử theo nhu cầu kiểm toán, điều tra lỗi và vận hành. Việc dọn dẹp cần tuân thủ quan hệ khóa ngoại và quy tắc của phiên bản Spring Batch; không xóa tùy tiện từng bảng `BATCH_*` bằng câu lệnh thủ công.

Khi restore một repository, hãy bảo đảm schema tương thích với phiên bản ứng dụng sẽ chạy. Không nên để một phiên bản code mới đọc metadata đã được migration theo một phiên bản không tương thích mà chưa có kiểm thử restart.

## 11. Những lỗi cấu hình thường gặp

| Lỗi | Biểu hiện hoặc rủi ro | Cách xử lý |
|---|---|---|
| Dùng database in-memory trong production | Metadata mất khi tiến trình kết thúc hoặc không được chia sẻ giữa các node | Dùng database bền vững, dùng chung khi cần chạy nhiều node |
| JobRepository trỏ nhầm datasource | Không tìm thấy bảng metadata hoặc ghi metadata vào database ngoài dự kiến | Khai báo rõ batch datasource và kiểm tra URL/schema thực tế |
| Transaction manager không khớp datasource | Thao tác không nằm trong transaction mong muốn hoặc phát sinh lỗi kết nối | Gắn từng transaction manager với đúng datasource |
| Tự tạo bảng bằng schema của phiên bản khác | Lỗi SQL, thiếu cột hoặc không tương thích metadata | Dùng schema script/migration theo đúng phiên bản Spring Batch |
| Nhiều node dùng repository riêng | Các node không nhìn thấy cùng lịch sử execution và có thể xử lý trùng | Dùng một repository database chung |
| Tách metadata và business DB nhưng giả định commit nguyên tử | Một phía có thể commit trong khi phía kia thất bại | Thiết kế idempotency, đối soát hoặc transaction phân tán có chủ đích |
| Runtime account có quyền quá rộng | Tăng rủi ro thay đổi schema hoặc xóa metadata | Tách tài khoản migration và runtime, cấp quyền tối thiểu |
| Xóa metadata không theo quan hệ | Hỏng tham chiếu hoặc mất lịch sử không nhất quán | Dùng quy trình retention được kiểm soát và phù hợp schema |

Khi gặp lỗi khởi động, hãy kiểm tra URL database, driver, tài khoản, schema hiện tại, quyền trên bảng, script migration và log tạo JobRepository. Khi gặp lỗi restart hoặc chạy trùng, kiểm tra các node có dùng cùng repository hay không và xem lịch sử JobInstance/JobExecution trong metadata.

## 12. Cách chọn cấu hình theo tình huống

| Tình huống | Lựa chọn phù hợp |
|---|---|
| Học tập hoặc test đơn giản | Embedded database có schema tự khởi tạo |
| Một ứng dụng production, tải vừa phải | Database quan hệ bền vững; có thể dùng chung datasource với dữ liệu nghiệp vụ nếu transaction và vận hành phù hợp |
| Nhiều node cùng chạy batch | Một JobRepository database dùng chung và được quản trị bền vững |
| Cần tách quyền hoặc vòng đời metadata | Datasource/schema riêng, cấu hình rõ transaction manager và chiến lược phục hồi xuyên database |
| Production có quy trình quản lý DDL | Migration bằng Flyway/Liquibase; tắt tự khởi tạo schema của ứng dụng |

Không có một lựa chọn datasource đúng cho mọi hệ thống. Nếu cần tính đơn giản và dữ liệu cùng database, dùng chung datasource thường dễ vận hành. Nếu cần cô lập tài nguyên hoặc quyền, có thể tách metadata, nhưng phải xử lý rõ ràng ranh giới transaction và phục hồi.

## Kết luận

Database của JobRepository lưu trạng thái điều khiển cần thiết để Spring Batch nhận diện job, theo dõi từng execution và restart từ metadata đã lưu. Hãy chọn relational database bền vững có schema phù hợp với phiên bản Spring Batch, cấu hình datasource và transaction manager đúng tài nguyên, đồng thời quản lý schema bằng một quy trình triển khai có kiểm soát.

Với ứng dụng đơn giản, metadata có thể dùng chung datasource với dữ liệu nghiệp vụ. Khi tách datasource, cần tính đến transaction không nguyên tử giữa hai database, tính idempotent và khả năng đối soát. Với nhiều node, tất cả phải dùng chung JobRepository để chia sẻ lịch sử execution và phối hợp an toàn.
