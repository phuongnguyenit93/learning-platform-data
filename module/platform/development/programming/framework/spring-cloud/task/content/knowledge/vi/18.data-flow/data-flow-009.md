# Kho dữ liệu dùng chung, quyền truy cập và tương thích phiên bản

## 1. Vì sao Spring Cloud Data Flow cần kho dữ liệu dùng chung?

**Spring Cloud Task** hỗ trợ những ứng dụng Spring Boot chạy hữu hạn: khởi động, thực hiện nghiệp vụ, cập nhật metadata về lần chạy trong **TaskRepository** và kết thúc. **Spring Cloud Data Flow (SCDF)** bổ sung một lớp điều phối: đăng ký ứng dụng, tạo định nghĩa task, khởi chạy theo yêu cầu hoặc theo lịch, theo dõi lịch sử và hiển thị kết quả qua dashboard/API.

Trong chương **Data Flow**, bài học này trả lời ba câu hỏi vận hành có liên quan chặt chẽ:

1. **Kho dữ liệu dùng chung:** server Data Flow, ứng dụng task và ứng dụng Spring Batch cần thấy những bảng metadata nào?
2. **Quyền truy cập:** ai được đọc, ai được ghi, ai được tạo bảng, và làm sao truyền thông tin xác thực mà không làm lộ secret?
3. **Tương thích phiên bản:** khi Data Flow, Spring Cloud Task, Spring Batch hoặc schema được nâng cấp, làm thế nào để các tiến trình cũ và mới còn hiểu cùng dữ liệu?

Tình huống thường gặp: quản trị viên khởi chạy `daily-settlement` từ Data Flow Dashboard, task đã xuất báo cáo thành công nhưng trang **Task Executions** lại không hiện lần chạy. Nguyên nhân không nhất thiết là task lỗi; có thể task dùng **H2 in-memory riêng**, sai database/schema, thiếu JDBC driver, thiếu quyền ghi metadata hoặc schema không phù hợp.

Theo hướng dẫn Spring Cloud Data Flow, để hệ thống hiển thị lịch sử của một ứng dụng task, **Data Flow và task phải cùng truy cập kho metadata thực thi phù hợp**. Với tác vụ Spring Batch, lịch sử job/step cũng cần được ghi vào kho mà Data Flow được cấu hình để truy vấn.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt các kho metadata **Data Flow**, **Spring Cloud Task** và **Spring Batch** với **database nghiệp vụ**.
- Thiết kế kết nối DataSource cho task do SCDF khởi chạy, task chạy ngoài SCDF và các tác vụ trong **Composed Task Runner**.
- Cấu hình quyền đọc/ghi/schema migration theo **nguyên tắc quyền tối thiểu**.
- Nhận diện rủi ro lộ credential khi SCDF truyền cấu hình xuống Kubernetes Pod.
- Lập ma trận tương thích giữa **Data Flow – Boot – Cloud Task – Batch – JDBC driver – schema**.
- Thực hiện kiểm thử kết nối, schema, quyền và migration trước khi nâng cấp production.

## 2. Các loại dữ liệu không nên đánh đồng

Một hệ thống xử lý task có thể sử dụng nhiều lớp dữ liệu:

| Lớp | Ví dụ bảng/đối tượng | Phục vụ việc gì? |
| --- | --- | --- |
| **SCDF server metadata** | Định nghĩa ứng dụng, task definition, lịch chạy, thông tin triển khai | Data Flow Server đăng ký, điều phối và hiển thị tài nguyên |
| **Spring Cloud Task metadata** | `TASK_EXECUTION`, `TASK_EXECUTION_PARAMS`, `TASK_SEQ`, bảng liên quan | Ghi trạng thái **mỗi lần chạy process task** |
| **Spring Batch metadata** | `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, `BATCH_*_EXECUTION_CONTEXT` | Theo dõi job/step, bộ đếm item và khả năng restart |
| **Database nghiệp vụ** | `orders`, `settlements`, `report_outbox` | Lưu kết quả thật, khóa nghiệp vụ, checkpoint riêng nếu có |
| **Hạ tầng điều phối** | Kubernetes Job/Pod, CronJob, Cloud Foundry Task | Khởi tạo process, quản lý tài nguyên, timeout và mã thoát |

**Dùng chung kho metadata không đồng nghĩa phải dùng chung tất cả dữ liệu nghiệp vụ.**

Một cách triển khai phổ biến:

- Data Flow Server dùng PostgreSQL `scdf_metadata` để lưu metadata điều phối.
- Task do server khởi chạy ghi `TASK_EXECUTION` trong cùng database/schema metadata phù hợp.
- Nếu task chạy Spring Batch, các bảng `BATCH_*` cũng cần xuất hiện ở nơi SCDF/Batch có thể đọc và cập nhật theo contract của phiên bản.
- Phần xử lý đơn hàng vẫn ghi vào database `business_db` riêng, qua DataSource/transaction manager của nghiệp vụ.

Nếu một task có **nhiều DataSource**, không được giả định Spring Cloud Task sẽ tự chọn đúng kho metadata. Cần cấu hình `TaskConfigurer` để đặt `TaskRepository` và `TaskExplorer` vào DataSource mong muốn, đồng thời đảm bảo `JobRepository` của Batch dùng kho đã thống nhất.

~~~mermaid
flowchart TB
    U["SCDF Dashboard / Shell / REST API"] --> S["Spring Cloud Data Flow Server"]
    S --> M[("Metadata DB dùng chung")]
    S --> P["Task Platform / Deployer"]
    P --> A["Task A: Spring Cloud Task"]
    P --> B["Task B: Spring Cloud Task + Batch"]
    A --> M
    B --> M
    A --> BA[("Database nghiệp vụ")]
    B --> BA
    M --- T["TASK_*: lần chạy task"]
    M --- J["BATCH_*: job và step"]
    M --- D["SCDF metadata: định nghĩa và điều phối"]
~~~

Sơ đồ trên là **mô hình logic**. Dù cùng một database, các thành phần vẫn có thể dùng **tài khoản SQL riêng** theo quyền cần thiết. Khi tách schema hoặc database vật lý, phải xác định rõ khả năng đọc, ghi và query của SCDF theo phiên bản; không được chỉ tạo hai bảng cùng tên rồi xem như đã kết nối.

## 3. “Cùng database” cần kiểm tra những gì?

Hai cấu hình có cùng hostname chưa chắc thực sự trỏ cùng tập metadata. Để khẳng định dùng chung, cần đối chiếu:

| Thành phần cần khớp | Ví dụ | Rủi ro nếu không khớp |
| --- | --- | --- |
| **DB engine** | PostgreSQL | Driver/DDL khác nhau |
| **DB host/cluster** | `metadata-db.internal:5432` | Task ghi sang cluster khác |
| **Database name** | `scdf_metadata` | Bảng có cùng tên nhưng dữ liệu khác |
| **Schema / search_path** | `public` hoặc schema metadata đã cấu hình | `TASK_EXECUTION` nằm tại namespace không được đọc |
| **Table prefix** | `TASK_`, `BATCH_` | Repository dùng tên bảng khác thực tế |
| **Driver và protocol** | `org.postgresql.Driver`, `jdbc:postgresql:...` | Task không kết nối hoặc bootstrap lỗi |
| **Quyền thực tế** | `SELECT`, `INSERT`, `UPDATE`, quyền sinh ID | Task tạo ID/ghi trạng thái thất bại |
| **Schema version** | DDL tương thích với runtime | Query/INSERT có cột hoặc kiểu dữ liệu không khớp |

**Tài liệu SCDF 2.11 chỉ rõ:** khi Data Flow khởi chạy một task thông thường, server chuyển các thuộc tính DataSource của mình như `spring.datasource.url`, `driverClassName`, `username` và `password` tới ứng dụng task. Nhờ vậy task ghi metadata vào kho chung **nếu** ứng dụng nhận đúng cấu hình, có driver và không tự ghi đè DataSource theo cách khác.

Đối với **task khởi chạy từ bên ngoài** (CLI, scheduler riêng, một Kubernetes Job khác), không có gì đảm bảo nó nhận các thuộc tính do SCDF đưa xuống. Bạn phải **tự cấp cấu hình DataSource cùng kho** nếu muốn nó xuất hiện trong SCDF.

### 3.1. Ba đường khởi chạy phổ biến

~~~mermaid
flowchart LR
    S["Data Flow Server"] -->|"launch task + DataSource properties"| A["Task chạy từ SCDF"]
    C["Scheduler bên ngoài"] -->|"phải cấu hình DB riêng"| B["Task chạy ngoài SCDF"]
    S --> D["Composed Task Runner"]
    D --> E["Child task 1"]
    D --> F["Child task 2"]
    A --> M[("Kho metadata chung")]
    B --> M
    D --> M
    E --> M
    F --> M
~~~

| Đường chạy | Điều kiện chia sẻ metadata |
| --- | --- |
| **Simple task launch từ SCDF** | SCDF truyền cấu hình datasource; task phải có driver, schema/quyền phù hợp |
| **Composed Task Runner (CTR)** | Runner và **mọi child task** cần tiếp cận đúng kho dữ liệu chung và driver tương ứng |
| **Task chạy ngoài SCDF** | Phải cấu hình DataSource **tường minh** theo kho SCDF cần đọc; không phụ thuộc H2 mặc định |
| **Chạy trên nhiều platform** | Dù pod/job chạy ở namespace/cluster khác, vẫn cần kết nối mạng, DNS, firewall và quyền tới kho metadata đúng |

**Không nhầm “SCDF Server khởi chạy được task” với “task ghi được metadata”.** Deployer có thể tạo Pod thành công nhưng ứng dụng thất bại vì thiếu driver hoặc không có quyền truy cập bảng TaskExecution.

## 4. Cấu hình thử nghiệm với PostgreSQL

Giả sử tổ chức dùng PostgreSQL đặt tại `metadata-db.internal:5432`, database `scdf_metadata`, schema mặc định `public`. Để minh họa quyền tối thiểu, server và task sử dụng **hai tài khoản runtime khác nhau**.

### 4.1. Phía Data Flow Server

Ví dụ `application.yml` của **SCDF server** (rút gọn):

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://metadata-db.internal:5432/scdf_metadata
    username: scdf_server
    driver-class-name: org.postgresql.Driver
    # Password: cung cấp bằng Kubernetes Secret/secret manager.
~~~

Trong thực tế phải bổ sung **cơ chế cung cấp password** (ví dụ `SPRING_DATASOURCE_PASSWORD` trong environment của server), cấu hình hạ tầng và các thuộc tính database cần thiết theo **phiên bản SCDF** đang triển khai. Dòng `driver-class-name` dùng cách viết kebab-case; Spring Boot có cơ chế binding tương ứng với `driverClassName`.

**Đây là cấu hình của server**, không phải câu lệnh tự động tạo schema metadata cho production. SCDF có thể tự khởi tạo một số bảng tùy phiên bản/cấu hình; môi trường production nên dùng chiến lược migration có kiểm soát, thay vì cho nhiều ứng dụng cùng tranh nhau tạo bảng.

### 4.2. Phía ứng dụng task

Ví dụ `application.yml` cho **task có chủ đích kết nối cùng database**:

~~~yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: jdbc:postgresql://metadata-db.internal:5432/scdf_metadata
    username: task_writer
    driver-class-name: org.postgresql.Driver
    # Password: cung cấp qua secret của task runtime.
  cloud:
    task:
      name: daily-settlement
      initialize-enabled: false
~~~

`initialize-enabled: false` chỉ phù hợp sau khi DBA/migration đã tạo schema TaskRepository tương thích. Nếu database trống mà tắt tự khởi tạo, ứng dụng không thể ghi `TASK_EXECUTION`.

**Quan trọng khi Data Flow khởi chạy:** SCDF có thể truyền DataSource properties từ server xuống task. Nếu muốn task dùng **tài khoản khác** (như `task_writer`) nhưng vẫn cùng kho metadata, cần đảm bảo thứ tự ưu tiên property/binding và cách cấu hình platform thực tế **không khiến các giá trị bị ghi đè sai**. Đừng nhìn YAML trong jar rồi kết luận task đã dùng tài khoản đó; kiểm tra thông tin kết nối **đã resolve ở runtime** mà không in password.

### 4.3. Driver JDBC phải đi cùng task artifact

SCDF Server có PostgreSQL driver **không đồng nghĩa** mỗi task jar/image đã có driver đó. Với Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Version của starter và driver nên được quản lý bằng **BOM tương thích**. Khi ứng dụng có Spring Batch, bổ sung Spring Batch starter và kiểm tra JobRepository riêng. Không chọn độc lập các bản Spring Boot, Task và Batch chỉ vì từng dependency đều tồn tại trên Maven Central.

### 4.4. Khi dùng database nghiệp vụ riêng

Một task có thể cần:

- `metadataDataSource` tới `scdf_metadata`.
- `businessDataSource` tới `orders_db`.

Trường hợp này cần **cấu hình cụ thể `TaskConfigurer`**, transaction manager và bean JDBC/JPA để **TaskRepository** ghi vào metadata DB. Với Spring Batch, xác định tiếp `JobRepository` dùng DataSource/transaction manager nào.

Các API có thể truy vấn bằng `TaskExplorer` và `JobExplorer`, nhưng chúng **không tự đồng bộ kết quả nghiệp vụ** giữa hai database. Thực hiện hoàn tiền trên database nghiệp vụ rồi lỗi cập nhật metadata có thể khiến SCDF thấy trạng thái chưa hoàn tất dù tiền đã được xử lý. Thiết kế retry/idempotency theo business key vẫn bắt buộc.

## 5. Quyền truy cập: tách người dùng và trách nhiệm

Đây là ba lớp quyền khác nhau:

1. **SCDF API/RBAC:** người dùng hoặc service account nào được đăng ký ứng dụng, launch task, hủy task, xem execution hay cấu hình schedule.
2. **Platform RBAC:** server/deployer nào được tạo Kubernetes Job/Pod, đọc Secret, truy cập namespace hoặc gọi API cloud.
3. **Database privilege:** tài khoản runtime được `SELECT`, `INSERT`, `UPDATE`, dùng sequence/sequence table hoặc tạo/sửa schema nào.

Một người dùng có quyền **xem SCDF Dashboard** không nên mặc nhiên có quyền kết nối SQL trực tiếp. Và việc cấp quyền Kubernetes tạo Pod **không tạo ra quyền** ghi bảng `TASK_EXECUTION` trong PostgreSQL.

### 5.1. Ma trận trách nhiệm gợi ý

| Vai trò | Quyền cần thiết | Không nên cấp rộng |
| --- | --- | --- |
| **SCDF server runtime** | Quyền thao tác metadata SCDF và các bảng task/batch mà server thực tế tạo/đọc/cập nhật | Superuser DB; tự do sửa mọi database nghiệp vụ |
| **Spring Cloud Task runtime** | `SELECT/INSERT/UPDATE` trên bảng TaskRepository cần ghi và quyền cấp ID theo schema | `CREATE/DROP/ALTER` trên toàn database |
| **Spring Batch runtime** | Quyền đọc/ghi các bảng Batch metadata, bảng Task nếu tích hợp Cloud Task | DDL rộng, quyền tới ứng dụng không liên quan |
| **Dashboard tự phát triển dùng TaskExplorer** | Nếu cần DB trực tiếp, quyền `SELECT` tới bảng metadata cần đọc | `UPDATE` trạng thái hoặc `DELETE` lịch sử |
| **Migration/DBA role** | Quyền `CREATE/ALTER/DROP` được giới hạn và kiểm soát để áp dụng migration | Dùng chung với tài khoản runtime cho mọi task |

**Không áp một danh sách quyền cố định cho mọi phiên bản.** SCDF Server có thể tự tạo `TaskExecution` trước khi deployer thật sự khởi chạy process, nên **server đôi khi cũng cần quyền ghi bảng task**. Tài khoản task có thể cần quyền cho `TASK_SEQ`; tính năng single-instance có thể cần `TASK_LOCK`; tích hợp Batch cần `TASK_TASK_BATCH` và `BATCH_*`. Hãy dựa vào **DDL, chức năng và triển khai thực tế**.

### 5.2. Ví dụ PostgreSQL: cấp quyền theo nhu cầu

Sau đây là **mẫu minh họa SQL**, không phải migration dùng ngay cho mọi hệ thống:

~~~sql
-- Chạy bằng tài khoản DBA/migration đã được phê duyệt.
-- Ví dụ bảng TaskRepository nằm trong schema public.

GRANT CONNECT ON DATABASE scdf_metadata TO task_writer;
GRANT USAGE ON SCHEMA public TO task_writer;

GRANT SELECT, INSERT, UPDATE
ON TABLE public.TASK_EXECUTION
TO task_writer;

GRANT SELECT, INSERT, UPDATE
ON TABLE public.TASK_EXECUTION_PARAMS
TO task_writer;
~~~

Trong PostgreSQL, tên bảng không có dấu nháy kép thường được lưu ở dạng chữ thường; ví dụ trên tương ứng với bảng tạo theo quy ước thông thường. Nếu DDL thực tế dùng tên **quoted, case-sensitive**, cần sửa câu lệnh cho khớp.

**Ví dụ trên chưa đầy đủ quyền của toàn bộ runtime.** Việc cấp execution ID có thể sử dụng bảng `TASK_SEQ` hoặc cơ chế sequence khác; nếu dùng `TASK_TASK_BATCH`, `TASK_LOCK` hay Spring Batch thì còn các đối tượng khác. Với bảng sử dụng sequence thực, có thể cần quyền `USAGE`/`SELECT` thích hợp trên sequence. Với sequence dạng bảng, quyền DML khác nhau. DBA cần đọc **schema thực** trước khi cấp.

Khi **SCDF server và task dùng hai tài khoản**, cần chuẩn bị quyền riêng cho `scdf_server` trên những bảng SCDF thao tác, không coi ví dụ `task_writer` là đủ. Sau khi cấp, chạy integration test với **chính tài khoản runtime** để xem có lỗi permission denied ở câu lệnh insert, update, nextval hay không.

### 5.3. Quyền xem dữ liệu cũng phải được giới hạn

`TASK_EXECUTION_PARAMS` có thể lưu các tham số dòng lệnh; `ERROR_MESSAGE` và `EXIT_MESSAGE` có thể chứa tên host, đường dẫn, stack trace hoặc thông tin nhạy cảm nếu ứng dụng ghi thiếu kiểm soát.

- Không truyền mật khẩu, token và khóa API qua `--password=...`.
- Không log toàn bộ environment hoặc DataSource URL có user/password.
- Phân quyền SCDF REST API/Dashboard theo môi trường, nhóm và nhu cầu.
- Nếu xuất metadata ra hệ thống BI, dùng view giới hạn trường hoặc giảm thiểu dữ liệu nhạy cảm.
- Dùng TLS cho kết nối database và hạn chế network ingress; ràng buộc nguồn kết nối ở firewall/NetworkPolicy.

## 6. Bảo vệ credential khi SCDF khởi chạy task trên Kubernetes

Spring Cloud Data Flow có thể **truyền thông tin kết nối database xuống task lúc launch**. Trong nhánh tài liệu SCDF Kubernetes 2.11, cơ chế mặc định có thể truyền credential dưới dạng application properties; với một số `entryPointStyle` như `exec` hoặc `shell`, thông tin này có thể lộ khi xem mô tả Pod hoặc command line.

Tài liệu SCDF 2.11 mô tả một tùy chọn dùng **Kubernetes Secrets** cho credentials:

~~~properties
spring.cloud.dataflow.task.use.kubernetes.secrets.for.db.credentials=true
~~~

**Đây là cấu hình dành cho server/đường triển khai có hỗ trợ tính năng đó**, không phải property mà mọi ứng dụng Spring Cloud Task đều hiểu.

Khi bật, phải đảm bảo các `secretKeyRefs` thích hợp được cấu hình cho **task platform account** và Secret thật sự tồn tại trong namespace mà worker được chạy. Tên biến môi trường, tên Secret và data key phụ thuộc chart/manifests/phiên bản triển khai.

Ví dụ **minh họa cấu trúc**, không đưa mật khẩu thật vào mã nguồn:

~~~yaml
spring:
  cloud:
    dataflow:
      task:
        use:
          kubernetes:
            secrets:
              for:
                db:
                  credentials: true
        platform:
          kubernetes:
            accounts:
              default:
                secretKeyRefs:
                  - envVarName: "spring.datasource.username"
                    secretName: metadata-db
                    dataKey: username
                  - envVarName: "spring.datasource.password"
                    secretName: metadata-db
                    dataKey: password
~~~

Các khóa `secretKeyRefs` và cách kết hợp với cờ `use.kubernetes.secrets.for.db.credentials` phải được **đối chiếu với bản SCDF/Helm chart thực tế**; ví dụ chỉ minh họa vị trí ý nghĩa. Không giả định mọi bản SCDF đều triển khai cấu hình này theo cùng cú pháp.

**Khuyến nghị vận hành:**

1. Cấp credential bằng Secret manager/Kubernetes Secret, không hardcode YAML trong image.
2. Giới hạn những service account/pod có thể đọc Secret của metadata DB.
3. Kiểm tra cách deployer truyền argument/environment để tránh credential hiện trong logs, process list, `kubectl describe` hoặc metadata TaskExecution.
4. Có quy trình rotate mật khẩu đồng bộ với những Job đang chạy; không làm gián đoạn transaction đang xử lý mà không có kế hoạch.
5. Tách quyền đọc của công cụ quan sát khỏi quyền tạo/sửa task và quyền ghi metadata.
6. Audit ai đã launch một task, thay đổi cấu hình DataSource hoặc deployment properties.

**Không dùng base64 như một cơ chế mã hóa bảo mật.** Kubernetes `Secret.data` dùng base64 để biểu diễn dữ liệu, không khiến dữ liệu tự nhiên trở nên bí mật trước người có quyền đọc Secret.

## 7. Tương thích phiên bản gồm nhiều lớp

Một ứng dụng task có thể build thành công nhưng vẫn **không thể ghi metadata chung** nếu các thành phần khác thế hệ framework hoặc schema.

~~~mermaid
flowchart LR
    A["SCDF Server version"] --> B["Schema metadata SCDF"]
    C["Spring Cloud Task + Boot"] --> D["TASK_* schema"]
    E["Spring Batch version"] --> F["BATCH_* schema"]
    G["JDBC driver + Database engine"] --> H["Kết nối/SQL thực thi"]
    B --> I{"Tương thích được kiểm chứng?"}
    D --> I
    F --> I
    H --> I
    I -->|Có| J["Test integration + migration"]
    I -->|Không| K["Không triển khai production"]
~~~

### 7.1. Ma trận cần quản lý

| Thành phần | Những gì cần đối chiếu |
| --- | --- |
| **SCDF Server** | Bản release, API/dashboard, schema quản trị, hỗ trợ các nền tảng và task application versions |
| **Spring Boot** | Java runtime yêu cầu, auto-configuration DataSource, phiên bản JDBC/Hibernate |
| **Spring Cloud Task** | Release tương thích Boot, cấu trúc `TaskExecution`, SQL schema/DDL, `TaskConfigurer` |
| **Spring Batch** | Metadata schema, kiểu dữ liệu/cột, `JobRepository`, khả năng restart và execution context |
| **Spring Cloud Deployer** | TaskLauncher implementation, cách truyền app properties/secret, URI artifact |
| **Database engine & JDBC driver** | Dialect, kiểu timestamp, schema prefix, khóa/sequence, version server |
| **Task artifact** | Version jar/image, Spring Cloud BOM, dependency DB driver, môi trường đang launch |

**Không lấy tên “current” của tài liệu làm bằng chứng một bộ phiên bản có thể chạy cùng nhau.** Cần đối chiếu bản release được cố định trong manifest/Helm và tài liệu compatibility matrix của release đó.

Ở **SCDF 2.11**, tài liệu có các nhánh hỗ trợ task ứng dụng Boot 2/Boot 3, với cấu hình/metadata như `spring.cloud.deployer.bootVersion` và `spring.cloud.task.schemaTarget` trên những đường thực thi cụ thể. Đây là ví dụ điển hình vì sao phải kiểm tra **đường chạy và schema target** trước khi nâng cấp; không tự đặt `schemaTarget=boot3` trong mọi task không kiểm chứng contract tương ứng.

### 7.2. Bối cảnh bảo trì phiên bản

Theo thông báo của Spring ngày **21/04/2025**, dòng **Spring Cloud Data Flow 2.11.x** và **Spring Cloud Deployer 2.9.x** là những dòng **open-source cuối cùng**; những bản phát hành tương lai thuộc mô hình thương mại dành cho khách hàng Tanzu Spring. Điều này **không đồng nghĩa** mọi bản 2.11.x đều hết hoạt động hay không có cập nhật theo hợp đồng hỗ trợ.

Khi lập kế hoạch upgrade trong doanh nghiệp, cần kiểm tra **nguồn phân phối và quyền truy cập phiên bản mới**, thời hạn hỗ trợ, CVE/patches và ma trận tương thích từ nhà cung cấp. Tránh khẳng định một bản mới nhất cố định nếu chưa xác nhận tại thời điểm triển khai.

### 7.3. Vì sao “cùng bảng” chưa chắc tương thích

Giả sử một Task 2.x ghi metadata theo một DDL cũ, trong khi SCDF Server và Task 3.x kỳ vọng cấu trúc mới. Có thể xuất hiện:

- Lỗi `column does not exist` khi query.
- Lỗi kiểu dữ liệu khi insert/update timestamp hoặc exit code.
- Lỗi tạo ID do bảng sequence khác cách sinh khóa.
- Truy vấn Batch metadata thất bại do schema `BATCH_*` không khớp.
- Lỗi mapping do table prefix hoặc schema target sai.
- App có thể khởi động nhưng một số chức năng truy vấn lịch sử/restart không còn đúng.

Vì vậy compatibility phải được **kiểm thử ở mức SQL và nghiệp vụ**, không dừng ở `mvn package` hoặc việc Pod chuyển sang trạng thái Running.

## 8. Quản lý schema và migration an toàn

### 8.1. Ai tạo bảng?

Trong môi trường demo, Spring Cloud Task có thể tự khởi tạo schema bằng `spring.cloud.task.initialize-enabled`, còn SCDF có cơ chế khởi tạo schema tùy bản release. Trong **production**, nhiều tiến trình task cùng chạy và server có thể cùng khởi động, vì vậy tránh để mỗi process tự động tạo/sửa bảng metadata không kiểm soát.

Một mô hình rõ ràng:

1. **DBA hoặc migration pipeline** sở hữu schema metadata, có quyền DDL.
2. **SCDF server và các task runtime** chỉ được cấp quyền DML cần thiết để đọc/ghi dữ liệu.
3. **Các migration của Task, Batch và SCDF** được chọn theo đúng bộ version đã triển khai.
4. **Không tự ý đổi cột** trong `TASK_EXECUTION` hoặc `BATCH_JOB_EXECUTION` chỉ để “sửa nhanh” một câu SQL.
5. **Không xóa dữ liệu metadata cũ** trước khi xác định ảnh hưởng đến restart, audit và liên kết task/job.

### 8.2. Quy trình nâng cấp theo giai đoạn

~~~mermaid
flowchart TD
    A["Chốt inventory phiên bản + schema hiện tại"] --> B["Backup DB và thử restore"]
    B --> C["Dựng staging bản sao dữ liệu/DDL"]
    C --> D["Chạy migration chính thức"]
    D --> E["Test SCDF, Task, Batch theo ma trận"]
    E --> F{"Tất cả test PASS?"}
    F -->|Không| G["Dừng nâng cấp, xử lý tương thích"]
    F -->|Có| H["Quản lý task đang chạy + triển khai theo kế hoạch"]
    H --> I["Smoke test, audit và giám sát"]
~~~

**Bước 1 — Inventory:** ghi version SCDF Server, các task jar/image, Spring Boot/Cloud BOM, Spring Batch, Spring Cloud Deployer, JVM, DB engine/driver, table prefix và cấu hình `schemaTarget` nếu có.

**Bước 2 — Bảo toàn:** backup metadata và **thử khôi phục**. Nếu cần restart Batch Job cũ, phải bảo toàn các bảng `BATCH_JOB_*`, `BATCH_STEP_*` và execution context. Backup file dump nhưng chưa test restore không đủ.

**Bước 3 — Thử migration staging:** áp DDL/migration chính thức trên bản sao phù hợp. Kiểm tra các bảng, chỉ mục, sequence/sequence table, constraint và quyền mới.

**Bước 4 — Test đa phiên bản:** nếu cần chạy rolling upgrade, phải xác nhận cả binary cũ và mới có thể đọc/ghi cùng schema **trong giai đoạn chồng lấn**. Nếu không được bảo đảm, lên kế hoạch **dừng nhận task mới**, chờ Job đang chạy hoàn tất, migration rồi chuyển đồng loạt.

**Bước 5 — Cutover:** cập nhật container/image, DataSource, secret, deployment properties và cấu hình platform. Không thay đổi đồng thời quá nhiều biến mà không có đường truy lỗi.

**Bước 6 — Verify:** khởi chạy task smoke test, đọc lại `TASK_EXECUTION` và `BATCH_JOB_EXECUTION`, kiểm tra dashboard, retry và restart, rồi giám sát vài chu kỳ vận hành.

**Bước 7 — Rollback plan:** rollback binary **không bảo đảm rollback schema**. Nếu DDL thay đổi không tương thích ngược, phải có phương án phục hồi backup/khôi phục dữ liệu và cửa sổ bảo trì rõ ràng. Không chạy mã cũ trên schema mới một cách mù quáng.

## 9. Ví dụ kiểm tra kho và quyền bằng SQL

Những câu lệnh SQL sau dành cho **PostgreSQL**, thực thi bằng công cụ kiểm tra được cấp phép và **tài khoản runtime đang cần xác minh**, không phải tự động chạy từ một task không có trách nhiệm quản trị.

### 9.1. Xác nhận kết nối thật

~~~sql
SELECT
    current_database() AS database_name,
    current_schema() AS default_schema,
    current_user AS login_role;
~~~

Hãy chạy cùng truy vấn từ môi trường SCDF Server và từ task (ví dụ qua kết nối dùng cùng cấu hình) để kiểm tra database/schema thực tế. Hai role có thể khác nhau nhưng phải nhìn thấy đúng bảng metadata.

### 9.2. Kiểm tra có bảng metadata hay không

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_name IN (
    'task_execution',
    'task_execution_params',
    'batch_job_execution',
    'batch_step_execution'
)
ORDER BY table_schema, table_name;
~~~

Với PostgreSQL, các DDL tạo identifier không quote thường chuyển tên bảng chữ hoa như `TASK_EXECUTION` thành chữ thường `task_execution` trong `information_schema`. Nếu bảng được tạo bằng identifier có dấu nháy kép, cần điều chỉnh điều kiện tên cho đúng.

### 9.3. Kiểm tra quyền trên bảng task

~~~sql
SELECT
    has_table_privilege(
        current_user, 'public.task_execution', 'SELECT'
    ) AS can_select,
    has_table_privilege(
        current_user, 'public.task_execution', 'INSERT'
    ) AS can_insert,
    has_table_privilege(
        current_user, 'public.task_execution', 'UPDATE'
    ) AS can_update;
~~~

Kết quả phải phù hợp với vai trò. Nếu schema không phải `public`, thay bằng tên đầy đủ. **Có quyền trên bảng vẫn chưa đủ** nếu cơ chế cấp execution ID dùng một sequence/sequence table mà role không thể truy cập.

### 9.4. Đọc lần chạy theo SQL

~~~sql
SELECT
    TASK_EXECUTION_ID,
    TASK_NAME,
    START_TIME,
    END_TIME,
    EXIT_CODE,
    ERROR_MESSAGE
FROM TASK_EXECUTION
ORDER BY TASK_EXECUTION_ID DESC
LIMIT 20;
~~~

Nếu task chạy Spring Batch:

~~~sql
SELECT JOB_EXECUTION_ID, STATUS, EXIT_CODE,
       START_TIME, END_TIME
FROM BATCH_JOB_EXECUTION
ORDER BY JOB_EXECUTION_ID DESC
LIMIT 20;
~~~

Các truy vấn đọc này hỗ trợ đối chiếu **metadata đã được commit**; không chứng minh tiến trình/pod hiện còn sống, hoặc kết quả nghiệp vụ đã hoàn tất đúng. Cần kết hợp log, TaskExplorer/JobExplorer và kiểm tra dữ liệu thật.

### 9.5. Phương pháp test tối thiểu

Một integration test có giá trị hơn việc chỉ `SELECT 1`:

1. Bằng tài khoản runtime task, chạy task test có `ApplicationRunner` thành công; nó phải **tạo TaskExecution và cập nhật kết thúc**.
2. Với một task kiểm thử lỗi có kiểm soát, xác minh `EXIT_CODE` và `ERROR_MESSAGE` ở repository.
3. Bằng SCDF Dashboard/API, tìm thấy đúng lần chạy và xem trạng thái tương ứng.
4. Nếu có Batch, chạy Job một Step, xác minh metadata Job/Step và đường liên kết Task–Batch theo phiên bản.
5. Tạo một lần chạy lại có kiểm soát và xác minh retry/idempotency; đừng chỉnh `EXIT_CODE` trực tiếp trong DB.
6. Lặp lại qua mỗi platform account cần hỗ trợ, bao gồm job chạy theo lịch và job được launch bên ngoài SCDF nếu doanh nghiệp dùng.

## 10. Khắc phục sự cố theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra ưu tiên |
| --- | --- | --- |
| Task chạy xong, SCDF không hiện execution | Task dùng H2 riêng hoặc sai host/database/schema | So sánh JDBC URL đã resolve, database, schema và bảng |
| Task khởi động lỗi `No suitable driver` | Task jar/image thiếu JDBC driver | Kiểm tra driver trong task artifact, URL JDBC |
| `permission denied for table task_execution` | Role runtime thiếu DML trên bảng task | Kiểm tra `current_user` và `has_table_privilege` |
| `permission denied for sequence` / cấp ID thất bại | Thiếu quyền với cơ chế `TASK_SEQ` tương ứng | Kiểm tra DDL và quyền của sequence/sequence table |
| `relation task_execution does not exist` | Schema chưa migrate, sai `search_path` hoặc table prefix | Xem `information_schema`, JDBC schema và khởi tạo bảng |
| Batch Job không xuất hiện hoặc restart lỗi | `BATCH_*` không ở kho SCDF đọc, schema/version không khớp | Kiểm tra DataSource của JobRepository, DDL, JobExecution |
| CTR chạy, child task không có lịch sử | Một hoặc nhiều child app dùng datasource/driver khác | Kiểm tra cấu hình từng child và quyền |
| Lỗi sau nâng cấp nhưng vẫn connect DB được | Binary mới/DDL cũ hoặc ngược lại | So sánh ma trận version, migration log, cột/index |
| Dashboard hiện task lỗi dù dữ liệu nghiệp vụ đã ghi | Tiến trình chết trước khi cập nhật TaskRepository | Kiểm tra hạ tầng/log, idempotency và kết quả đã commit |
| Mật khẩu DB lộ trong Pod description | SCDF truyền credential dạng property hoặc sai entry point style | Rà soát Kubernetes Secrets, cấu hình SCDF theo version |
| Chạy trên platform A thấy dữ liệu, B không thấy | B kết nối kho DB riêng hoặc không có network route | So sánh config/runtime/network policy từng platform |
| Task bị gián đoạn sau khi rotate secret | Thay secret/credential giữa các đợt chạy | Đánh giá connection pool, thời gian sống pod và chiến lược rotate |

**Một nguyên tắc xử lý sự cố:** không sửa/ghi đè bảng metadata chỉ để dashboard chuyển sang “COMPLETED”. Nếu task đã có kết quả nghiệp vụ nhưng thiếu `END_TIME`, cần điều tra vì sao tiến trình không cập nhật được, rồi thiết kế phục hồi an toàn.

## 11. Tình huống thiết kế thực tế

### Tình huống A — Một SCDF server, nhiều task chạy theo lịch

Một server SCDF khởi chạy `daily-billing`, `email-digest` và `reconciliation` trên Kubernetes. Ba task khác nhau nhưng cùng dùng một PostgreSQL metadata DB. Mỗi app có driver và được cấp quyền ghi bảng TaskRepository. Lịch sử được tra cứu trên Dashboard.

**Điểm thiết kế:** giới hạn quyền database runtime và network access; các task không cần truy cập bảng nghiệp vụ của nhau. Mỗi task có cơ chế chống xử lý trùng theo business key, vì kho metadata chung **không tự đảm bảo exactly-once**.

### Tình huống B — Task được khởi chạy ngoài Data Flow

Hệ thống thanh toán có scheduler độc lập chạy `nightly-reconciliation.jar`. Nếu muốn thấy execution trên SCDF, scheduler cần cung cấp DataSource **cùng kho metadata** phù hợp với SCDF; chỉ có đúng `spring.cloud.task.name` không đủ.

**Điểm thiết kế:** bản task chạy ngoài phải có JDBC driver, cấu hình schema và quyền ghi đúng. Nên lưu nguồn khởi chạy trong log/correlation để không nhầm lịch của SCDF với scheduler ngoài.

### Tình huống C — Composed Task Runner với hai child tasks

CTR điều phối `download-data` rồi `transform-data`. Cả CTR và child app chạy trên những pod riêng; từng app cần metadata DS tương thích. Child thứ hai dùng profile riêng vô tình trỏ sang H2.

**Hệ quả:** CTR có thể không theo dõi đúng trạng thái child. Cần kiểm tra **từng image/profile**, không chỉ thử kết nối từ CTR hoặc SCDF Server.

### Tình huống D — Nâng cấp môi trường Boot 2/Boot 3

Một số task cũ dựa trên Boot 2, một số task mới dùng Boot 3, trong khi server SCDF 2.11 hỗ trợ nhiều thế hệ task theo những điều kiện cấu hình nhất định.

**Điểm thiết kế:** chốt `bootVersion` / `schemaTarget` thích hợp khi contract hỗ trợ, thử nghiệm TaskRepository/Batch schema và dependency JDBC, giữ ma trận kiểm thử riêng cho từng loại task. **Không nâng cấp tất cả metadata schema** nếu chưa kiểm tra tác động lên task/JobInstance còn cần restart.

## 12. Checklist đưa lên production

### Kết nối và schema

- [ ] SCDF Server, task apps và các child tasks dùng **cùng metadata database/schema** theo cấu hình đã kiểm chứng.
- [ ] Task do scheduler ngoài chạy cũng có cấu hình metadata DB nếu cần hiển thị trong SCDF.
- [ ] Từng task artifact có JDBC driver tương thích với DB engine.
- [ ] Khi có nhiều DataSource, `TaskConfigurer` và `JobRepository` trỏ đúng kho.
- [ ] Table prefix `TASK_`, `BATCH_` và `schemaTarget` được xác nhận theo release.
- [ ] Metadata tables/indexes/sequence đã được tạo bằng migration phù hợp.

### Quyền và bảo mật

- [ ] Role server, task, batch, viewer và migration được **phân quyền riêng** theo yêu cầu thực tế.
- [ ] Task runtime không có quyền DDL rộng; quyền cấp execution ID được kiểm tra.
- [ ] SCDF API/RBAC, Kubernetes RBAC và SQL privilege được quản lý tách biệt.
- [ ] Secret được cấp an toàn theo phiên bản SCDF/deployer, không hiện ở command line/log.
- [ ] Database dùng TLS và giới hạn nguồn kết nối; có kế hoạch rotate credentials.
- [ ] Không lưu password/token trong `TASK_EXECUTION_PARAMS` hoặc thông điệp lỗi.

### Phiên bản và vận hành

- [ ] Có inventory SCDF/Boot/Cloud Task/Batch/Deployer/JDBC/DB/schema.
- [ ] Đã kiểm thử phiên bản cũ và mới trên staging khi rolling upgrade.
- [ ] Có backup **và thử restore** trước khi nâng cấp metadata schema.
- [ ] Có phương án cho Job/Task đang chạy, restart và rollback binary/schema.
- [ ] Đã kiểm thử một task thành công, một task lỗi và một Batch Job qua SCDF UI/API.
- [ ] Có runbook điều tra mismatch DB/schema/permission và metadata chưa kết thúc.
- [ ] Có cơ chế đối soát nghiệp vụ và idempotency khi task bị kill trước khi ghi trạng thái cuối.

## 13. Tổng kết

Để **Spring Cloud Data Flow** điều phối và hiển thị lịch sử **Spring Cloud Task**, thành phần ghi và thành phần đọc cần truy cập **cùng kho metadata thực tế**: không chỉ cùng tên bảng mà còn đúng **database, schema, table prefix, driver, quyền và schema version**. Với **Spring Batch**, còn phải kiểm tra các bảng `BATCH_*` và khả năng restart job/step.

Quyền truy cập cần được tách giữa **SCDF API**, **hạ tầng triển khai** và **database**. Trong môi trường Kubernetes, cần đặc biệt thận trọng cách Data Flow truyền credential xuống task và kiểm chứng tính năng Secrets của đúng phiên bản. Khi nâng cấp, phải đánh giá **cả bộ phiên bản và DDL**, chạy migration có backup/rollback plan, và chứng minh bằng integration test rằng task ghi được, SCDF đọc được và dữ liệu nghiệp vụ vẫn chính xác.

### Tài liệu tham khảo

- [Spring Cloud Data Flow 2.11 — Sharing Data Flow's Datastore with Tasks](https://docs.spring.io/spring-cloud-dataflow/docs/2.11.0/reference/htmlsingle/)
- [Spring Cloud Data Flow — Architecture and Database](https://dataflow.spring.io/docs/concepts/architecture/)
- [Spring Cloud Data Flow — FAQ: task/batch applications and shared database](https://dataflow.spring.io/docs/resources/faq/)
- [Spring Cloud Data Flow — Kubernetes database credentials and Secrets](https://docs.spring.io/spring-cloud-dataflow/docs/current/reference/htmlsingle/)
- [Spring Cloud Task — DataSource, table prefix and schema initialization](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/appendix-task-repository-schema.html)
- [Spring Cloud — Release train / Spring Boot compatibility](https://spring.io/projects/spring-cloud/)
- [Spring — Spring Cloud Data Flow End of Open-Source, 21/04/2025](https://spring.io/blog/2025/04/21/spring-cloud-data-flow-commercial/)
