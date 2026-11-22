# Database credential trong Spring Batch: quản lý thông tin xác thực an toàn

Spring Batch thường phụ thuộc vào database ở ít nhất một trong hai vai trò: **`JobRepository`** lưu lịch sử và trạng thái thực thi, còn **reader/writer** đọc hoặc ghi dữ liệu nghiệp vụ. Để kết nối, ứng dụng có thể cần username/password, chứng chỉ client, token truy cập ngắn hạn hoặc cơ chế danh tính do nền tảng cloud cung cấp. Nếu credential bị lộ hoặc được cấp quyền quá rộng, rủi ro không chỉ là mất dữ liệu khách hàng mà còn có thể làm sai checkpoint, làm hỏng metadata batch, gây chạy trùng hoặc làm gián đoạn quy trình phục hồi.

**Database credential** là thông tin được database dùng để xác thực danh tính kết nối. Trong **Spring Batch Core Processing → Security**, quản lý credential đúng nghĩa là: **lưu bí mật ngoài mã nguồn**, **cấp quyền tối thiểu**, **truyền bí mật tới ứng dụng qua kênh được kiểm soát**, **bảo vệ kết nối**, **không ghi bí mật vào log hoặc metadata**, và **có khả năng thay/thu hồi credential mà không làm mất trạng thái batch**.

Bài này dùng Spring Batch 5.x, Spring Boot 3.x và Java 17+ làm ngữ cảnh minh họa. Tên property và hành vi chi tiết cần tương ứng với cấu hình thực tế của ứng dụng; nguyên tắc bảo mật áp dụng rộng hơn cho các phiên bản và database khác.

## 1. Spring Batch cần credential cho những kết nối nào?

Một ứng dụng batch có thể có **một hoặc nhiều `DataSource`**:

~~~mermaid
flowchart TD
    A["Spring Batch Application"] --> B["JobLauncher / JobRepository"]
    A --> C["ItemReader / ItemWriter"]
    B --> D["Batch metadata database\nBATCH_JOB_INSTANCE, BATCH_JOB_EXECUTION, ..."]
    C --> E["Business database\norders, payments, ledger, ..."]
    F["Secret manager / credential provider"] -->|Cấp thông tin xác thực| A
~~~

Hai vai trò khác nhau:

| Vai trò database | Nhiệm vụ | Quyền runtime thường cần |
|---|---|---|
| **Batch metadata repository** | Tạo/tra `JobInstance`, `JobExecution`, `StepExecution`, lưu `ExecutionContext`, checkpoint và trạng thái restart. | Truy cập đọc/ghi những bảng và sequence metadata cần thiết; không mặc định cần tạo/xóa schema. |
| **Business reader** | Đọc dữ liệu nguồn hoặc staging. | `SELECT` trên bảng/view phù hợp; có thể không cần quyền ghi. |
| **Business writer** | `INSERT`/`UPDATE`/`DELETE` dữ liệu đích theo nghiệp vụ. | Chỉ các thao tác và bảng đích được cấp phép. |
| **Migration/administration** | Tạo bảng, index, sequence, chạy migration schema. | Quyền DDL riêng, không cấp cho tài khoản chạy job hằng ngày nếu không cần. |
| **Monitoring/operations** | Xem trạng thái batch qua truy vấn hoặc API. | Quyền đọc phù hợp hoặc đi qua dịch vụ quản lý; không tự động có quyền sửa metadata. |

Một ứng dụng đơn giản có thể dùng chung database và tài khoản; tuy nhiên việc **phân tách danh tính runtime** là chiến lược giảm phạm vi thiệt hại. Việc tách nhiều `DataSource` còn cần thiết kế transaction manager và cách nối `JobRepository` với business data; chỉ tách username trong file cấu hình không tự làm cho hai transaction nguyên tử với nhau.

### Cần tránh nhầm hai loại dữ liệu

- `JobRepository` lưu metadata batch, **không phải** một kho secret hay payload đầu vào.
- `ExecutionContext` dùng để lưu trạng thái restart và có thể được serialize xuống database; nó **không phải** nơi phù hợp để cất password.
- `JobParameters` có identifying và non-identifying parameters, nhưng **cả hai loại vẫn có thể được lưu vào metadata**. Cờ `identifying=false` không phải cơ chế giấu hoặc mã hóa giá trị.
- Reader/writer thường lấy connection từ `DataSource` và pool; credential thuộc **cấu hình kết nối**, không nên đi theo từng item hoặc từng request.

## 2. Các nguyên tắc cốt lõi

| Nguyên tắc | Ý nghĩa thực tế |
|---|---|
| **Không hard-code** | Không đặt username/password thật trong Java, `application.yml` được commit, test fixture hoặc Dockerfile. |
| **Least privilege** | Tài khoản chỉ được thao tác trên schema/bảng cần thiết; không dùng tài khoản quản trị database cho job. |
| **Tách môi trường** | Dev, test, staging và production có credential/tài nguyên riêng; không dùng secret production cho CI. |
| **Quản lý vòng đời** | Credential có quy trình cấp, thay, thu hồi, khôi phục và kiểm tra hạn dùng. |
| **Không log bí mật** | Không in credential, connection string có password, environment dump hoặc cả cấu hình ứng dụng. |
| **Bảo vệ kết nối** | Dùng TLS và xác thực máy chủ theo khả năng database/driver; bảo vệ cả mạng và nơi lưu secret. |
| **Không đưa vào batch metadata** | Không truyền password qua `JobParameters`, `ExecutionContext` hoặc tên job/step. |
| **Fail safely** | Nếu secret không có hoặc không hợp lệ, không tự fallback sang tài khoản mặc định yếu hơn. |
| **Audit có kiểm soát** | Ghi nhận danh tính truy cập, việc thay secret và kết quả kết nối mà không ghi giá trị bí mật. |

Không có một nguồn secret duy nhất phù hợp mọi tổ chức. Một ứng dụng có thể dùng secret manager chuyên dụng, credential động, danh tính workload, hoặc secret được cấp qua môi trường triển khai. Quan trọng là xác định **ai được cấp quyền đọc**, **bí mật tồn tại ở đâu**, **cách cập nhật**, và **những hệ thống nào có thể quan sát giá trị đó**.

## 3. Những anti-pattern phổ biến

### 3.1. Hard-code trong source code

~~~java
// KHÔNG NÊN: credential thật bị đóng vào mã nguồn/binary.
var dataSource = new com.zaxxer.hikari.HikariDataSource();
dataSource.setJdbcUrl("jdbc:postgresql://db.internal:5432/payments");
dataSource.setUsername("batch_admin");
dataSource.setPassword("super-secret-password");
~~~

Rủi ro không chỉ nằm ở repository Git hiện tại. Credential có thể còn trong commit lịch sử, artifact build, cache CI, log pipeline, bản sao lưu và code review. Xóa dòng password ở commit mới **không làm bí mật cũ trở lại an toàn**; khi secret thật từng bị lộ, cần **thu hồi/rotate** theo quy trình.

### 3.2. Đưa password vào JDBC URL

~~~text
# Ví dụ không an toàn khi URL bị log hoặc hiển thị trong công cụ quản trị:
jdbc:postgresql://db.internal:5432/payments?user=batch_user&password=secret
~~~

Một số driver hỗ trợ credential trong URL, nhưng URL thường xuất hiện trong exception, config dump, diagnostics hoặc monitoring. Tốt hơn là giữ `jdbcUrl` chỉ chứa endpoint và các tùy chọn kết nối không bí mật; username/password được cấp qua thuộc tính riêng của `DataSource` hoặc một credential provider chuyên dụng.

### 3.3. Truyền secret qua command line

~~~bash
# Tránh đưa password thật lên command line:
java -jar app.jar --spring.datasource.password=some-password
~~~

Argument của process có thể bị quan sát bởi công cụ kiểm tra tiến trình, hệ thống vận hành hoặc log startup. Tương tự, không echo password trong script, không in toàn bộ environment khi chẩn đoán, và không để shell debug mode như `set -x` làm lộ câu lệnh chứa secret.

### 3.4. Dùng một tài khoản quyền cao cho tất cả

Nếu tài khoản runtime vừa được quyền `DROP TABLE` trên metadata, vừa có quyền đọc toàn bộ dữ liệu khách hàng và sửa cả bảng kế toán, một sự cố bảo mật hoặc bug writer có thể gây hậu quả lớn. Nên tách quyền theo vai trò và workload, đồng thời xem xét quyền thật sự được ứng dụng dùng đến.

### 3.5. Coi file `.env` là nơi an toàn tuyệt đối

File `.env` trong máy phát triển có thể tiện cho môi trường local, nhưng **không phải secret manager**. Nó có thể bị copy vào image, backup hoặc commit nhầm. Cần giới hạn quyền file, tránh commit, không chia sẻ qua chat/vé hỗ trợ và ưu tiên cơ chế secrets được hạ tầng triển khai quản lý khi chạy production.

`.gitignore` giúp giảm rủi ro commit nhầm nhưng không chặn secret đã được commit trước đó, được in ra log hoặc bị công cụ build sao chép.

## 4. Kết nối Spring Boot DataSource mà không ghi password vào repository

Với ứng dụng có một `DataSource`, Spring Boot có thể đọc thuộc tính datasource từ cấu hình ngoài ứng dụng:

~~~yaml
# application.yml: chỉ chứa tham chiếu, không chứa credential thật
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
  batch:
    jdbc:
      initialize-schema: never
~~~

Các placeholder theo cú pháp Spring `${...}` được phân giải từ môi trường/configuration source tương ứng. Giá trị thực được cấp **ở thời điểm triển khai**, không nằm trong file cấu hình đã commit.

Ví dụ ý nghĩa các biến:

| Biến | Chứa gì? | Lưu ý |
|---|---|---|
| `DB_JDBC_URL` | JDBC URL tới database được phép dùng | Không gắn password vào query string. |
| `DB_USERNAME` | Tên principal/role runtime | Không dùng superuser hoặc tài khoản migration nếu không cần. |
| `DB_PASSWORD` | Secret runtime do hệ thống cấp | Không in, không đưa vào JobParameters. |

`spring.batch.jdbc.initialize-schema=never` là lựa chọn thường dùng khi schema Spring Batch đã được khởi tạo bởi migration tool/tài khoản deploy riêng. Nó **không tự tạo bảng `BATCH_*`**. Nếu schema chưa tồn tại, ứng dụng/job có thể lỗi lúc truy cập `JobRepository`; cần một quy trình migration trước deployment. Trong môi trường local test, việc tự khởi tạo schema có thể được dùng có chủ đích, nhưng không nên cấp DDL rộng cho production runtime chỉ vì tiện khởi động.

### Dùng environment variable có phải là đủ an toàn?

Environment variable thuận tiện và được Spring Boot hỗ trợ, nhưng không làm credential bất khả xâm phạm:

- Người có quyền đọc cấu hình workload/process có thể quan sát biến môi trường ở một số nền tảng.
- Crash dump, diagnostic tool hoặc script có thể in toàn bộ environment.
- Khi secret thay đổi ở nơi cấp phát, **process đang chạy không nhất thiết nhận giá trị mới** nếu env chỉ được cấp lúc khởi động.
- Secret có thể tồn tại trong bộ nhớ của process và connection pool.

Vì vậy, với môi trường production cần thực hiện **kiểm soát truy cập workload**, hạn chế quyền debug/container exec, thiết lập logging an toàn và thiết kế cơ chế rotation phù hợp.

## 5. Quản lý secret bằng Kubernetes

Một cách tích hợp phổ biến là cấp `DB_USERNAME` và `DB_PASSWORD` từ Kubernetes Secret vào pod:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: settlement-batch
spec:
  replicas: 1
  selector:
    matchLabels:
      app: settlement-batch
  template:
    metadata:
      labels:
        app: settlement-batch
    spec:
      containers:
        - name: app
          image: example/settlement-batch:1.0.0
          env:
            - name: DB_JDBC_URL
              value: jdbc:postgresql://postgres.internal:5432/batchdb
            - name: DB_USERNAME
              valueFrom:
                secretKeyRef:
                  name: batch-db-credentials
                  key: username
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: batch-db-credentials
                  key: password
~~~

Đây là manifest **minh họa cách tham chiếu Secret**, không phải cấu hình Kubernetes production đầy đủ. Secret `batch-db-credentials` phải được tạo bằng một quy trình cấp phát an toàn; **không đưa credential thật vào YAML này hoặc lưu manifest có giá trị secret trực tiếp trong Git**.

Các giới hạn quan trọng:

1. Kubernetes Secret không mặc định là một kho secret mã hóa end-to-end chỉ vì dữ liệu trong YAML thường ở dạng **Base64**. Base64 là encoding, không phải encryption.
2. Cần quản lý RBAC, quyền truy cập API, quyền `kubectl exec`, chính sách bảo vệ etcd và encryption at rest của cluster theo yêu cầu.
3. **Biến môi trường của container không được cập nhật tự động** khi Kubernetes Secret thay đổi. Thường cần rollout/restart pod hoặc tích hợp một credential provider có hỗ trợ refresh.
4. Mount Secret thành volume có thể cho phép nội dung file được cập nhật theo cơ chế Kubernetes (với các caveat như mount qua `subPath`), nhưng **`DataSource` không tự nạp lại password chỉ vì file đổi**. Ứng dụng phải có cơ chế reload và làm mới connection pool.
5. Không cấp quyền list/get mọi Secret trong namespace nếu pod chỉ cần một credential cụ thể.

Nếu tổ chức dùng external secret manager hoặc CSI driver, các chi tiết đồng bộ/rotation phụ thuộc tích hợp. Phải kiểm tra **điểm thực sự nhận credential** là Spring `DataSource` hoặc driver, không chỉ việc một Secret object đã đổi trên cluster.

## 6. Secret manager và credential động

Một secret manager chuyên dụng có thể hỗ trợ versioning, audit access, rotation và cấp credential ngắn hạn. Một số nền tảng còn cho phép workload nhận danh tính thông qua service account hoặc IAM để tránh lưu password tĩnh trong cấu hình ứng dụng.

~~~mermaid
sequenceDiagram
    participant W as Batch workload
    participant I as Workload identity
    participant S as Secret manager
    participant D as Database
    W->>I: Chứng minh danh tính workload
    I-->>W: Quyền truy cập theo policy
    W->>S: Lấy credential/connection token
    S-->>W: Secret hoặc token có vòng đời giới hạn
    W->>D: Kết nối TLS và xác thực
    D-->>W: Connection đã xác thực
~~~

Đây là mô hình khái niệm. Có môi trường token được provider/driver cấp trực tiếp, có môi trường secret manager trả username/password; không phải mọi hệ thống đều có đúng chuỗi lời gọi trên.

Ưu điểm có thể có:

- Không đặt secret thật trong image hoặc source code.
- Có thể giới hạn scope theo ứng dụng, môi trường và database.
- Theo dõi việc cấp/đọc/thu hồi qua audit.
- Hỗ trợ rotation/lease ngắn khi database và client có cơ chế tương ứng.

Nhưng thiết kế credential động làm phát sinh câu hỏi về **hạn dùng và kết nối pool**: khi token/lease hết hạn, connection cũ có thể tiếp tục hoạt động hoặc bị database từ chối tùy cơ chế; connection mới có thể fail nếu pool vẫn dùng credential cũ. Cần thiết kế việc xin token mới, tạo connection mới và thay pool an toàn.

### Không đồng nhất “đổi secret” và “ứng dụng đã dùng secret mới”

Việc secret manager cập nhật một giá trị **không chứng minh** mọi `DataSource` trong tất cả pod đã sử dụng giá trị mới. Để rotation hoàn chỉnh, phải kiểm soát:

1. Secret mới được tạo và có quyền database phù hợp.
2. App có cơ chế nhận/cập nhật secret đúng lúc.
3. Pool tạo được connection mới với credential mới.
4. Job đang chạy không bị gián đoạn ngoài khả năng phục hồi.
5. Credential cũ được thu hồi sau khi các phiên sử dụng hợp lệ đã chuyển đổi, theo chính sách an ninh.

## 7. Least privilege cho JobRepository

Metadata của Spring Batch thường ở các bảng có tiền tố `BATCH_`, ví dụ `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, các bảng parameters/context và những sequence/table hỗ trợ ID.

Runtime của `JobRepository` có thể cần quyền đọc và cập nhật metadata trong suốt vòng đời job. Việc chỉ cấp `SELECT` là không đủ khi job cần tạo `JobExecution` mới, cập nhật `BatchStatus` hoặc checkpoint.

Ngược lại, runtime không nên tự động được phép:

- `DROP TABLE` hoặc sửa schema ngoài nhiệm vụ.
- Tạo user hoặc cấp quyền cho user khác.
- Truy cập các schema nghiệp vụ không phục vụ JobRepository.
- Sửa dữ liệu hệ thống hoặc bảng audit mà nó không cần.

### Ví dụ phân quyền trên PostgreSQL

Giả sử metadata được đặt trong schema riêng `batch_meta`, đã được tài khoản migration khởi tạo:

~~~sql
-- Thực thi bởi tài khoản có quyền cấp phép (không phải batch_runtime).
GRANT USAGE ON SCHEMA batch_meta TO batch_runtime;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA batch_meta
TO batch_runtime;

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA batch_meta
TO batch_runtime;
~~~

Đây là **ví dụ quyền tối thiểu ở cấp schema metadata hiện tại**, không phải script hoàn chỉnh cho mọi mô hình tổ chức. Một số ứng dụng không cần `DELETE` trên mọi bảng trong runtime; hãy xác định theo `JobRepository`/`JobOperator`/cleanup thực tế. Quyền tương lai sau migration còn liên quan `ALTER DEFAULT PRIVILEGES` do chủ sở hữu schema/tables thiết lập; `GRANT ON ALL TABLES` chỉ bao phủ các bảng hiện có vào thời điểm cấp quyền.

Nếu cùng role còn dùng cho business writer, quyền metadata và quyền nghiệp vụ sẽ gộp lại; đó là một đánh đổi cần ghi nhận. Với hệ thống nhạy cảm, có thể dùng role/`DataSource` tách biệt để giảm blast radius, đồng thời kiểm tra transaction orchestration khi metadata và output ở hai DB khác nhau.

### Tách runtime và migration

| Danh tính | Trách nhiệm | Quyền |
|---|---|---|
| `batch_migrator` | Chạy Flyway/Liquibase hoặc scripts tạo/cập nhật schema | DDL được kiểm soát, dùng trong deployment. |
| `batch_repository_runtime` | Đọc/ghi metadata thực thi | DML cần thiết trên `BATCH_*` và sequence liên quan. |
| `payment_reader` | Đọc dữ liệu nguồn | `SELECT` trên bảng/view được phép. |
| `payment_writer` | Ghi kết quả nghiệp vụ | Quyền DML cần thiết trên bảng đích cụ thể. |
| `batch_observer` | Truy vấn trạng thái được phép | Chỉ đọc metadata, hoặc qua API vận hành có phân quyền. |

Phân tách này giúp một credential bị lộ không đương nhiên cho phép sửa mọi bảng khác. Tuy nhiên nó làm tăng số secret và cấu hình phải quản lý; cần có quy trình rotation, inventory và monitoring cho từng danh tính.

## 8. Một DataSource hay nhiều DataSource?

### Một DataSource cho cả metadata và business data

Ưu điểm: cấu hình đơn giản, một pool, transaction manager có thể tham gia cùng database khi mọi thành phần dùng đúng connection và transaction.

Nhược điểm: role runtime thường cần quyền trên cả metadata và bảng nghiệp vụ. Một bug hoặc credential compromise có phạm vi ảnh hưởng rộng hơn. Nếu dùng chung database, vẫn có thể giới hạn theo schema và bảng, nhưng không tách được quyền hoàn toàn nếu chỉ có một principal.

### Tách metadata DataSource và business DataSource

~~~text
                  Spring Batch
                      |
          +-----------+-----------+
          |                       |
  batchMetadataDataSource  businessDataSource
  credential: batch_role   credential: writer_role
          |                       |
     BATCH_* tables         payment_output
~~~

Ưu điểm: quyền theo vai trò rõ ràng, dễ áp dụng rotation và audit riêng. Nhược điểm: cần định tuyến bean đúng; transaction ở hai datasource không tự động là một transaction ACID chung.

Trong Spring Boot/Spring Batch, khi tự cấu hình nhiều datasource, phải xác định **`JobRepository` sử dụng datasource/transaction manager nào** và **`StepBuilder.chunk(..., transactionManager)` dùng transaction manager nào**. Các cơ chế như `@BatchDataSource` hoặc `@EnableBatchProcessing` với tham chiếu datasource/transaction manager có thể được áp dụng tùy phiên bản/cấu hình Boot; không nên kết luận chỉ cần đánh dấu một bean `@Primary` là mọi thành phần sẽ tự khớp.

Ví dụ về chủ đích cấu hình step:

~~~java
@Bean
Step writePaymentsStep(
        JobRepository jobRepository,
        @Qualifier("businessTransactionManager")
        PlatformTransactionManager businessTransactionManager,
        ItemReader<PaymentRow> reader,
        ItemWriter<PaymentRow> writer) {

    return new StepBuilder("writePaymentsStep", jobRepository)
        .<PaymentRow, PaymentRow>chunk(100, businessTransactionManager)
        .reader(reader)
        .writer(writer)
        .build();
}
~~~

Đoạn code giả định các bean đã tồn tại. Cần bảo đảm writer dùng `businessDataSource` mà `businessTransactionManager` quản lý. Nếu `JobRepository` được lưu trong một database khác, thời điểm commit metadata/checkpoint có thể không nguyên tử với commit dữ liệu nghiệp vụ; hãy thiết kế idempotency, business key và reconciliation để phục hồi đúng sau crash.

**Tách credential là quyết định bảo mật; đảm bảo transaction là quyết định nhất quán dữ liệu.** Cả hai cần được xem xét cùng lúc trong Spring Batch.

## 9. Bảo vệ kênh kết nối tới database

Credential an toàn trong secret manager vẫn có thể bị lộ nếu kết nối tới database không được bảo vệ phù hợp hoặc nếu ứng dụng chấp nhận máy chủ giả mạo.

Một cấu hình PostgreSQL JDBC có thể yêu cầu xác minh TLS:

~~~text
jdbc:postgresql://postgres.internal:5432/batchdb?sslmode=verify-full
~~~

Với PostgreSQL JDBC, `verify-full` yêu cầu xác thực chứng chỉ và tên host theo cấu hình trust phù hợp. Phải triển khai CA/root certificate/trust store đáng tin cậy và tên DNS tương thích với certificate thực tế. Chỉ bật mã hóa mà không kiểm tra danh tính server (ví dụ cấu hình tương đương “encrypt without verification”) có thể không đủ để chống kết nối tới endpoint giả mạo.

Những lớp bảo vệ nên đánh giá:

- TLS giữa workload và database, bao gồm cơ chế kiểm chứng certificate đúng.
- Network policy/firewall/security group: chỉ nguồn cần thiết mới kết nối được.
- DB chỉ lắng nghe trên endpoint cần thiết, không mở quản trị công khai.
- Xác thực client theo khả năng provider; có thể gồm chứng chỉ, token hoặc IAM identity.
- Quyền đọc private key và file truststore; tránh đặt private key vào image công khai.
- Cơ chế cập nhật certificate/CA và kiểm soát thời điểm hết hạn.
- Giới hạn connection pool, timeout và đăng nhập sai để giảm ảnh hưởng sự cố.

TLS và secret storage giải quyết hai khía cạnh khác nhau: **bí mật được lưu ở đâu** và **đường truyền tới database có được xác thực/bảo vệ hay không**.

## 10. Rotation credential khi job chạy nhiều giờ

Một job có thể bắt đầu 23:00 và chạy qua thời điểm password hoặc token được rotate lúc 00:00. Lúc ấy `HikariCP` hoặc pool tương đương có thể đang giữ các connection đã xác thực bằng credential cũ.

~~~text
T0:  Secret V1, connection pool tạo các connection
T1:  Job đọc/ghi nhiều chunk, một số connection được tái sử dụng
T2:  Secret manager/DB chuyển sang V2
T3:  Pool cố tạo connection mới
T4:  Connection dùng V1 có thể bị từ chối tùy chính sách DB
T5:  Step phát sinh lỗi kết nối / authentication
~~~

Một số database cho phép connection cũ tiếp tục đến khi đóng dù password đã đổi; hệ thống khác có thể thu hồi session/token đang chạy. Không nên giả định một hành vi duy nhất cho tất cả driver và credential provider.

### Quy trình rotation an toàn ở mức hệ thống

1. **Chuẩn bị credential V2.** Đảm bảo user/role mới có đúng quyền trước khi chuyển ứng dụng.
2. **Phân phối theo cơ chế được hỗ trợ.** Secret manager, workload identity hoặc rollout cấu hình; không copy secret qua log/chat.
3. **Chuyển connection mới sang V2.** App hoặc pool phải thực sự nhận secret mới; env thay đổi ngoài process không đủ.
4. **Xác nhận kết nối.** Quan sát authentication failures, pool acquisition timeout và trạng thái JobRepository/step.
5. **Đưa connection cũ ra khỏi vòng đời.** Có thể cần recreate datasource/pool hoặc rollout pod; tùy driver và tính chất job.
6. **Thu hồi V1.** Khi đã chắc mọi workload hợp lệ chuyển xong, thu hồi credential cũ theo chính sách.
7. **Xác minh batch recovery.** Nếu step thất bại trong lúc chuyển đổi, dùng `JobRepository` và checkpoint để restart đúng JobInstance.

Không chỉ chỉnh `spring.datasource.hikari.max-lifetime` rồi coi rotation đã được giải quyết: thiết lập tuổi thọ connection **không tự cấp credential mới** cho pool. Nếu provider refresh credential động, phải tích hợp phù hợp vào cơ chế tạo connection. Nếu secret được cấp qua environment của pod, thông thường cần rollout/restart theo kế hoạch.

### Rotation và restart của Spring Batch

Credential rotation **không phải JobParameter nghiệp vụ**. Không nên thêm password hoặc version bí mật vào identifying `JobParameters` để tạo JobInstance mới mỗi lần rotate.

Nếu job `FAILED` do hết hạn credential:

- Sửa cơ chế xác thực và kiểm tra kết nối metadata/business DB.
- Giữ nguyên identifying parameters của `JobInstance` cần phục hồi.
- Kiểm tra chunk nào đã commit, metadata/checkpoint nào còn lại.
- Restart khi trạng thái cho phép; kiểm tra idempotency của writer nếu có replay.
- Không xóa toàn bộ bảng `BATCH_*` hoặc sinh `run.id` ngẫu nhiên để vượt lỗi repository, vì có thể tạo công việc mới và ghi trùng.

## 11. Lỗi authentication trong reader/writer và JobRepository

Cùng là “database login failed” nhưng vị trí thất bại ảnh hưởng trực tiếp đến cách phục hồi:

| Điểm lỗi | Biểu hiện thường gặp | Hướng xử lý |
|---|---|---|
| **Startup / DataSource** | App không tạo được pool/bean do thiếu secret hoặc database từ chối credential. | Kiểm tra nguồn cấp secret, URL, role và TLS; không dùng fallback không an toàn. |
| **JobRepository trước launch** | Không tạo được `JobExecution`; có thể không có execution ID mới. | Sửa kết nối metadata, tra trạng thái trước khi client retry cùng business key. |
| **ItemReader** | Step không đọc được dữ liệu nguồn, có thể fail giữa job. | Kiểm tra role đọc, connection và trạng thái checkpoint. |
| **ItemWriter** | Chunk rollback hoặc kết quả commit chưa rõ. | Kiểm tra quyền ghi, connection, dữ liệu đã commit và idempotency. |
| **Lúc commit transaction** | Writer có thể đã chạy nhưng không nhận được xác nhận commit. | Không giả định chắc chắn rollback; đối soát tại DB đích. |
| **Sau khi rotate** | Connection cũ hoạt động, connection mới báo authentication failure. | Xem pool/provider refresh và kế hoạch thu hồi credential cũ. |
| **Sau migration schema** | Role runtime không còn đủ quyền trên bảng/sequence mới. | Cập nhật grants có kiểm soát trong migration. |

Một lỗi có vẻ liên quan credential cũng có thể thực sự do hostname, DNS, firewall, TLS certificate, pool exhaustion hoặc database chưa sẵn sàng. Phải phân loại nguyên nhân thay vì cứ rotate password khi gặp mọi exception kết nối.

### Retry không giải quyết sai password

~~~java
// Anti-pattern: retry mọi exception kết nối không phân biệt nguyên nhân.
.faultTolerant()
.retry(Exception.class)
.retryLimit(100)
~~~

Sai username/password hoặc quyền `GRANT` thiếu thường là lỗi cấu hình/authorization, không tự biến mất sau 100 lần retry. Retry liên tục còn tạo tải và có thể kích hoạt chính sách khóa tài khoản. Với lỗi network transient, retry có giới hạn/backoff có thể thích hợp; với authentication failure, nên fail sớm và sửa cấu hình/secret.

Trong một số hệ thống, lỗi do credential tạm thời hết hạn có thể hồi phục sau khi token mới được cấp, nhưng chính sách retry phải hiểu rõ **cơ chế refresh secret và vòng đời pool**. Một vòng retry blind trên cùng credential cũ không phải chiến lược rotation.

## 12. Logging, tracing và metadata không được chứa secret

Một trong những cách rò rỉ database credential phổ biến là “debug connection” bằng việc in toàn bộ cấu hình:

~~~java
// KHÔNG NÊN:
log.info("DataSource properties: {}", fullDataSourceProperties);
log.debug("Database password: {}", password);
log.info("Environment: {}", System.getenv());
~~~

Thay bằng một sự kiện có cấu trúc **không chứa credential**:

~~~java
log.warn(
    "batch.database.connection.failed component={} category={} jobExecutionId={}",
    "BUSINESS_WRITER",
    "AUTHENTICATION",
    jobExecutionId
);
~~~

`jobExecutionId` có thể chưa tồn tại khi lỗi phát sinh trước lúc JobRepository tạo execution. Ở giai đoạn đó hãy dùng `correlationId`/launch attempt ID được tạo từ phía caller hoặc scheduler, rồi bổ sung execution ID sau khi tạo thành công.

### Không log nguyên JDBC URL tùy ý

JDBC URL có thể chứa query string hoặc user info nhạy cảm. Nếu muốn ghi endpoint để chẩn đoán, hãy dùng **alias theo cấu hình** như `batch-metadata-primary` hoặc `payments-reader` thay vì `dataSource.getJdbcUrl()` nguyên văn.

Các exception cũng có thể chứa hostname, username, SQL hoặc input; không mặc định mọi `Throwable.getMessage()` đều an toàn để đẩy vào log tập trung. Dùng error code đã chuẩn hóa, chỉ giữ stack trace ở kênh chẩn đoán phù hợp sau khi xem xét nội dung.

### Bảo vệ các nơi khác ngoài logger

Rò rỉ có thể xảy ra qua:

- Actuator/configuration endpoints hoặc endpoint debug tự tạo nếu cấu hình hiển thị giá trị nhạy cảm sai.
- Tracing span attributes, monitoring tags hoặc error reporting SDK.
- Startup banner/diagnostics và thông báo lỗi có JDBC URL.
- CI build logs, test reports hoặc output của script deployment.
- Heap dump, core dump, support bundle và snapshot process.
- `JobParameters`/`ExecutionContext` được serialize vào `JobRepository`.
- Command history hoặc process arguments.

Một cấu hình an toàn cần phối hợp **source code, runtime platform, observability và quyền truy cập**, không chỉ dùng `@JsonIgnore` hoặc một regex mask password trong logger.

## 13. Credential không được đi theo từng item hoặc JobParameters

Một thiết kế sai thường gặp:

~~~java
// Không làm như thế: secret sẽ có thể được lưu trong BATCH metadata.
JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("dbPassword", password, false)
    .toJobParameters();
~~~

Đánh dấu `dbPassword` là non-identifying **không làm nó biến mất** khỏi lịch sử job. Nếu cần thay đổi credential, hãy để `DataSource`/credential provider chịu trách nhiệm, không tạo lại JobInstance hoặc truyền password qua workflow.

Tương tự:

~~~java
// Không đưa thông tin xác thực vào checkpoint:
stepExecution.getExecutionContext().put("password", password);
~~~

`ExecutionContext` thường được lưu bền vững để phục vụ restart; người có quyền xem metadata hoặc backup có thể tiếp cận dữ liệu này. Nếu writer cần truy cập external database, hãy tiêm `DataSource`/service được bảo vệ qua dependency injection, hoặc truy cập credential provider theo danh tính workload tại nơi cần thiết.

Nếu một job đọc dữ liệu của nhiều tenant, **không đặt toàn bộ credential từng tenant trong JobParameters**. Có thể dùng `tenantId`/`connectionAlias` đã được xác thực và được ánh xạ ở phía server sang datasource/provider được phép. Quyền tenant phải được kiểm soát; một alias do caller cung cấp không thể tự cấp quyền đọc mọi database.

## 14. Mối quan hệ giữa credential, connection pool và transaction

Trong Spring Batch, mỗi chunk thường có một transaction boundary. Writer JDBC lấy connection từ pool theo transaction manager đã cấu hình. Điều này có các hệ quả:

1. **Kết nối xác thực thành công không đủ để nói transaction đã đúng.** Writer phải tham gia đúng `DataSource`/`PlatformTransactionManager`.
2. **Pool tái sử dụng connection.** Credential có thể chỉ được dùng lúc mở connection; rotation không tự thay các connection cũ.
3. **Pool có giới hạn.** Khi quá nhiều partition/job chạy đồng thời, cạn connection dễ bị nhầm là credential failure nếu chỉ nhìn một exception chung.
4. **Database authorization tách khỏi authentication.** Username/password hợp lệ nhưng thiếu quyền `INSERT` vào bảng đích vẫn gây lỗi.
5. **Giữa hai transaction có thể đổi connection.** Một job dài có thể phát sinh lỗi giữa chừng nếu connection mới không xác thực được sau rotation.
6. **Metadata và nghiệp vụ có thể dùng các pool khác nhau.** Một pool hỏng không nhất thiết làm pool kia hỏng ngay, nhưng job có thể thất bại và trạng thái cần đối soát.

Với HikariCP, các cấu hình `maximumPoolSize`, `connectionTimeout`, `idleTimeout`, `maxLifetime` liên quan vận hành pool; không dùng chúng làm thay thế cho secret rotation và least privilege. Một số hệ thống hỗ trợ làm mới pool/evict connection có kiểm soát; cách sử dụng phụ thuộc cách tích hợp HikariCP/credential provider thực tế.

### Dùng transaction manager sai

Ví dụ metadata nằm ở database A, writer dùng database B. Nếu step vô tình được cấu hình transaction manager của A, các cập nhật writer ở B có thể không nằm trong transaction như người phát triển nghĩ.

Khi một chunk lỗi, repository có thể ghi metadata rollback trong A nhưng writer B đã commit một phần nếu tự mở connection ngoài transaction. Sau restart, dữ liệu có thể bị replay và trùng.

**Để tránh:** xác định rõ datasource/transaction manager cho reader/writer, thiết kế unique business key/idempotency và có bước reconciliation sau lỗi. Bảo mật credential đúng không tự sửa được sự khác biệt transaction giữa các tài nguyên.

## 15. CI/CD và môi trường test

Không dùng credential production trong integration test hoặc khi chạy migration trên CI. Một chiến lược tốt:

- Unit test reader/processor logic không cần database thật nếu không có yêu cầu.
- Integration test dùng database riêng hoặc Testcontainers với credential tạm thời và dữ liệu giả.
- CI nhận secret cần thiết từ secret store của runner với scope/retention ngắn, không commit vào repository.
- Tài khoản migration trong pipeline deploy chỉ dùng lúc cần; runtime service account có quyền khác.
- Log test không hiển thị password, environment dump hoặc connection URL có credential.

### Ví dụ Testcontainers: credential chỉ tồn tại cho test

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class BatchDatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("batch_test")
            .withUsername("test_batch_user")
            .withPassword("test_only_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void contextStartsWithTestDatabase() {
        // Tùy ứng dụng: kiểm tra bean JobRepository/DataSource
        // và một truy vấn an toàn vào schema test đã khởi tạo.
    }
}
~~~

`test_only_password` là credential **giả lập chỉ cho container test cô lập**, không phải mẫu để đặt password production trong mã nguồn. Với test dùng Testcontainers, cần có schema batch được khởi tạo phù hợp (qua migration hoặc thiết lập test). Cấu hình Spring Boot `spring.batch.jdbc.initialize-schema` cũng có thể điều khiển việc này; đừng mặc định schema đã tồn tại chỉ vì container khởi động.

Khi nhiều test dùng chung Spring TestContext cache nhưng container có vòng đời ngắn hơn context, datasource có thể trỏ tới container đã dừng. Thiết kế vòng đời Testcontainers và context cache cho nhất quán; không để test vô tình dùng lại secret/database cũ đã hết hạn.

### Những assertion đáng có

| Kịch bản | Kết quả kiểm thử mong đợi |
|---|---|
| Không có `DB_PASSWORD` ở môi trường yêu cầu xác thực | Startup/connection thất bại rõ, không fallback sang credential hard-code. |
| Secret đúng, quyền tối thiểu đúng | JobRepository tạo execution và writer ghi được vào bảng được cấp phép. |
| Reader chỉ có `SELECT` | Không thể ghi hoặc sửa bảng nguồn ngoài phạm vi. |
| Runtime không có DDL | Job chạy trên schema đã migrate; không thể tự ý `DROP/ALTER` bảng. |
| Rotation sang credential mới | Connection mới dùng V2; không yêu cầu thay identifying JobParameters. |
| Credential cũ bị thu hồi | Connection mới với V1 bị từ chối theo chính sách, lỗi được phân loại an toàn. |
| Password xuất hiện trong một cấu hình test giả | Không xuất hiện trong log, trace, JobParameters hay ExecutionContext. |
| Writer mất kết nối giữa chunk | Kiểm tra rollback, restart, dữ liệu output không trùng. |
| JobRepository không truy cập được | Không tạo một lượt chạy khác key ngẫu nhiên để vượt lỗi. |

Để kiểm tra log, có thể đưa một giá trị *canary* như `DO_NOT_LOG_TEST_SECRET` vào môi trường test rồi capture output của logger/sink phù hợp. Test không được dùng credential thật và không nên khẳng định bảo mật chỉ bằng việc scan một file log, vì secret còn có thể đi qua nhiều kênh quan sát khác.

## 16. Quy trình xử lý sự cố credential

Khi một job thất bại do authentication/authorization, quy trình vận hành nên dựa trên dấu hiệu thực tế thay vì in toàn bộ secret để chẩn đoán:

1. **Xác định điểm lỗi.** Startup, JobRepository, reader, writer, commit hay connection pool? Có `jobExecutionId`/`stepExecutionId` hay chưa?
2. **Phân loại vấn đề.** Authentication (principal/secret sai), authorization (thiếu GRANT), TLS/certificate, network/DNS, database outage hay pool exhaustion.
3. **Xác minh secret source.** Workload đang được gắn đúng Secret/role/identity và phiên bản secret dự kiến không? Chỉ xem metadata phiên bản và trạng thái, không hiển thị giá trị.
4. **Kiểm tra quyền tại database.** Runtime role có quyền cần thiết trên bảng/schema/sequence nào? Migration gần đây có tạo object chưa cấp quyền không?
5. **Đánh giá rotation.** Secret store đã đổi nhưng process/pool còn dùng V1? Có connection nào vẫn hoạt động, có lỗi mới phát sinh khi pool mở connection mới không?
6. **Khắc phục an toàn.** Sửa cấu hình/permission, rollout hoặc refresh credential theo hướng được hệ thống hỗ trợ. Tránh mở rộng thành superuser để chữa cháy.
7. **Phục hồi batch.** Giữ metadata, xác minh chunk đã commit và side effect bên ngoài; restart cùng JobInstance nếu được phép và bảo đảm idempotency.
8. **Đối soát và đóng sự cố.** Kiểm tra số bản ghi, business key và kết quả writer; audit việc cấp/thu hồi secret theo chính sách.

### Khi nghi ngờ credential đã bị lộ

Đây là **sự cố bảo mật**, không chỉ là lỗi chạy batch:

- Hạn chế/thu hồi quyền credential bị nghi lộ theo quy trình ứng phó sự cố; không cố “sửa” bằng việc xóa lịch sử log.
- Cấp credential mới với scope tối thiểu, cập nhật workload và thu hồi credential cũ khi thích hợp.
- Xem xét phạm vi truy cập và audit của database/secret manager, kể cả những kết nối ngoài lịch chạy job thông thường.
- Nếu credential từng nằm trong repository, CI logs, image hoặc support bundle, đánh giá các bản sao và thời gian retention; chỉ xóa ở một file hiện tại chưa đủ.
- Đối với job đang chạy, xác định ảnh hưởng của việc thu hồi tức thời tới transaction, checkpoint và đầu ra; ưu tiên quy trình đáp ứng an toàn được tổ chức phê duyệt.

Không nên để sự tiện lợi của một job đang chạy khiến credential nghi bị lộ tiếp tục được sử dụng vô thời hạn. Quyết định thời điểm thu hồi cần cân bằng chính sách ứng phó sự cố với khả năng phục hồi dữ liệu.

## 17. Những sai lầm thường gặp

### “Để password trong application.yml nhưng repository private nên an toàn”

Repository private vẫn có nhiều người/công cụ được phép đọc, có lịch sử commit, bản sao CI và artifact. Không coi đó là secret store. Khi secret đã được commit, phải thay secret và xem xét lịch sử.

### “Dùng Kubernetes Secret thì không cần encryption hoặc RBAC”

Secret được biểu diễn bằng Base64 không phải encryption. Cần chính sách quyền truy cập cluster, encryption at rest theo môi trường và giới hạn người/ứng dụng có thể đọc secret.

### “Thay giá trị Secret là HikariCP tự dùng password mới”

Không nhất thiết. Biến môi trường không được cập nhật tự động trong process đang chạy; datasource/pool cũng không tự đọc lại mọi nguồn config. Cần cơ chế refresh hoặc rollout phù hợp.

### “Cấp quyền superuser là cách nhanh nhất sửa lỗi repository”

Đây là cách mở rộng phạm vi rủi ro không cần thiết. Nếu job cần bảng/sequence mới, cấp quyền đúng đối tượng hoặc sửa migration/grants; không dùng account quản trị làm runtime mặc định.

### “Credential của database đọc và database ghi giống nhau sẽ dễ quản lý hơn”

Đúng là giảm số secret nhưng tăng blast radius. Nếu business requirements cho phép, tách quyền đọc/ghi và metadata; nếu phải dùng chung, xác định và hạn chế quyền cụ thể thay vì bỏ qua đánh giá.

### “Non-identifying JobParameter là giá trị không lưu”

Sai. Non-identifying chỉ ảnh hưởng danh tính JobInstance; password vẫn có thể vào bảng parameters. Không truyền credential qua `JobParameters` hay `ExecutionContext`.

### “Bật SSL là đủ, không cần xác thực certificate”

TLS không kiểm chứng danh tính server có thể không đáp ứng yêu cầu chống giả mạo endpoint. Cần cấu hình trust và hostname verification phù hợp với database/driver.

### “Authentication failure cứ retry là hết”

Sai password hoặc thiếu quyền thường không tự phục hồi. Retry không giới hạn gây tải và che nguyên nhân; cần sửa secret, role hoặc cơ chế refresh rồi mới cho job phục hồi.

### “Rotate database password thì phải chạy lại job bằng run.id mới”

Credential là hạ tầng xác thực, không phải danh tính nghiệp vụ của job. Nếu job thất bại, restart cùng JobInstance theo metadata phù hợp; tạo instance mới có thể làm xử lý trùng dữ liệu đã commit.

### “Chỉ cần ẩn password trong log là toàn bộ bí mật được bảo vệ”

Credential còn có thể nằm trong process arguments, environment, crash dump, support bundle, URL, trace attributes, backup hoặc bản thân metadata do ứng dụng lưu. Cần bảo vệ cả vòng đời, không chỉ một logger.

## 18. Quy trình thiết kế Database credential cho Spring Batch

Khi xây một hệ thống batch mới, có thể áp dụng các bước:

1. **Liệt kê tất cả đường kết nối database.** Xác định metadata `JobRepository`, reader, writer, staging, audit và migration dùng datasource nào.
2. **Thiết kế role least privilege.** Cấp DML đúng bảng/sequence; tách DDL migration; không cấp superuser cho runtime.
3. **Chọn nguồn cấp secret.** Secret manager, workload identity hoặc secret integration của nền tảng; không lưu password thật trong source/image.
4. **Cấu hình externalized properties.** Chỉ dùng `${DB_USERNAME}`/`${DB_PASSWORD}` hoặc provider thích hợp; không đặt password vào JDBC URL hay JobParameters.
5. **Bảo vệ mạng và TLS.** Xác minh certificate/hostname; giới hạn endpoint và các nguồn có thể kết nối.
6. **Khớp datasource với transaction manager.** Đảm bảo reader/writer tham gia transaction như thiết kế; đánh giá rủi ro khi metadata và nghiệp vụ dùng DB khác nhau.
7. **Thiết kế rotation và recovery.** Secret được cập nhật thế nào? Pool refresh khi nào? Job đang chạy có thể fail và restart an toàn ra sao?
8. **Giảm rò rỉ qua observability.** Log mã lỗi, job/step IDs và alias kết nối; không in secret, full config, environment hoặc raw JDBC URL.
9. **Kiểm thử bằng credential riêng.** Test quyền, auth failure, rotation, schema migration và chunk recovery bằng database test/fixture giả lập.
10. **Có quy trình xử lý sự cố.** Audit secret access, thu hồi credential bị lộ và đối soát dữ liệu sau lần thất bại.

## Kết luận

Trong Spring Batch, **database credential** không chỉ là hai thuộc tính `username` và `password`. Credential quyết định quyền truy cập vào **metadata phục vụ restart** và **dữ liệu nghiệp vụ**, nên phải được quản lý xuyên suốt từ lúc cấp phát, nạp vào `DataSource`, xác thực kết nối, luân chuyển qua connection pool, cho đến lúc rotate hoặc thu hồi.

Một thiết kế an toàn giữ secret **ngoài mã nguồn và batch metadata**, cấp **quyền tối thiểu**, bảo vệ kết nối với **TLS và kiểm chứng server**, phân biệt vai trò runtime/migration, có cơ chế rotation thực sự cập nhật pool, đồng thời xử lý authentication failure như một sự cố hạ tầng có thể ảnh hưởng tới transaction và checkpoint. Khi các lớp này được vận hành cùng nhau, hệ thống batch vừa bảo vệ dữ liệu vừa giữ khả năng phục hồi nhất quán sau sự cố.
