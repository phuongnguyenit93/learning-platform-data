# Xác minh hành vi tích hợp Batch, Stream và Deployer sau nâng cấp

Trong chương **Tối ưu và nâng cấp** của module **SPRING_CLOUD_TASK**, việc cập nhật một phiên bản thư viện không dừng ở bước biên dịch thành công. Một ứng dụng Spring Cloud Task có thể khởi chạy được trên JDK mới nhưng **mất liên kết với Spring Batch**, **không còn phát đúng sự kiện qua Spring Cloud Stream**, hoặc **được Deployer tiếp nhận nhưng không thật sự tạo tiến trình chạy được**. Những sự cố này thường chỉ xuất hiện khi kiểm thử với database, broker, nền tảng triển khai và dữ liệu lịch sử giống môi trường production.

Mục tiêu bài học là thiết lập một quy trình xác minh **trước và sau nâng cấp**, dựa trên hành vi quan sát được, cho ba đường tích hợp:

- **Batch:** `TaskExecution` ↔ `JobExecution`/`StepExecution`, tham số định danh, trạng thái Job, checkpoint và mã thoát của JVM.
- **Stream:** binding, destination, schema của payload, các sự kiện bắt đầu/kết thúc, consumer group, redelivery và khả năng khởi động task ngắn hạn.
- **Deployer:** artifact/version/image, tham số, biến môi trường, quyền truy cập, tài nguyên, ID thực thi, trạng thái pod/process và worker remote partitioning nếu sử dụng.

Đây là một bài **xác minh hành vi và chiến lược chuyển đổi**, không phải danh sách property cố định cho mọi Spring Boot/Spring Cloud release train. Khi nâng cấp qua các thế hệ lớn, đặc biệt giữa Spring Boot 3/Spring Batch 5 và Spring Boot 4/Spring Batch 6, phải đối chiếu migration guide **đúng phiên bản của từng thành phần** trước khi áp dụng mã nguồn mẫu.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Lập ma trận tương thích **JDK – Spring Boot – Spring Cloud Task – Spring Batch – Spring Cloud Stream – binder – Deployer – database**.
2. Ghi lại hành vi baseline của phiên bản cũ để so sánh với bản nâng cấp bằng cùng bộ đầu vào và tiêu chí nghiệp vụ.
3. Kiểm tra liên kết `TaskExecution` với `JobExecution` qua `TaskBatchExecutionListener` và bảng metadata phù hợp.
4. Phát hiện thay đổi ảnh hưởng tới `JobParameters`, `JobInstance`, restart, checkpoint và schema Batch.
5. Xác nhận binding `task-events`, `job-execution-events`, destination, header/serializer và consumer không bị lệch contract sau nâng cấp.
6. Chứng minh một yêu cầu được Deployer nhận **thực sự** tạo tiến trình, hoàn tất và trả mã thoát đúng.
7. Kiểm thử trường hợp remote partitioning, mất kết nối broker/DB, chạy trùng và sự cố sớm khi tạo `ApplicationContext`.
8. Đưa ra ngưỡng so sánh hiệu năng, chiến lược canary, điều kiện chặn triển khai và rollback khả thi.
9. Thiết kế bằng chứng chạy thử có thể kiểm toán: artifact digest, profile, execution ID, business key, log, metrics, SQL và message từ broker.

## 2. Vì sao “build xanh” chưa đủ?

Một quy trình chạy Task có thể đi qua nhiều thành phần:

~~~mermaid
flowchart LR
    A["Scheduler / SCDF API"] --> B["Spring Cloud Deployer"]
    B --> C["JVM / Pod chạy Spring Cloud Task"]
    C --> D["Spring Batch Job / Step"]
    D --> E["DB nghiệp vụ"]
    D --> F["JobRepository"]
    C --> G["TaskRepository"]
    C --> H["Stream binding: task-events"]
    D --> I["Stream binding: job-execution-events"]
    H --> J["Kafka / RabbitMQ"]
    I --> J
    J --> K["Consumer giám sát"]
    F --> L["Đối soát kết quả"]
    G --> L
    E --> L
    K --> L
~~~

Sau nâng cấp, bất kỳ ranh giới nào đều có thể thay đổi dù phần nghiệp vụ không thay đổi:

| Ranh giới | Dấu hiệu có thể xảy ra | Vì sao compile không phát hiện |
| --- | --- | --- |
| Boot ↔ Task | Listener vòng đời không được kích hoạt, thiếu `TaskExecution` | Điều kiện auto-configuration thay đổi theo classpath/property |
| Task ↔ Batch | Có `JobExecution` nhưng không có quan hệ với `TaskExecution` | Bean `TaskBatchExecutionListener` hoặc module phụ thuộc không có |
| Batch ↔ JDBC | Job cũ không restart được, query metadata lỗi | DDL và serialization `JobParameters` đã thay đổi |
| Task/Batch ↔ Stream | Không có event, hoặc consumer không parse được | Binding name, content type, serializer, binder và cấu hình runtime |
| Deployer ↔ artifact | Launcher trả ID nhưng pod không khởi chạy | Image pull, Java runtime, manifest, security context, resource limit |
| Deployer ↔ worker | Worker partition được tạo nhưng không tìm thấy StepExecution | Sai datasource, JobRepository, token hoặc tham số worker |
| Task ↔ scheduler | Tiến trình kết thúc nhưng exit code không phản ánh lỗi Batch | Chính sách ánh xạ `fail-on-job-failure` hoặc cách đóng context |
| Runtime ↔ monitoring | Không có event cuối hoặc `END_TIME` | SIGKILL, OOM, broker/DB lỗi, task quá ngắn để export telemetry |

Quy tắc: **mỗi đường tích hợp phải có một test hành vi quan sát được ở ranh giới thực**, không chỉ test unit/mocking của một class.

## 3. Chốt ma trận phiên bản trước khi sửa dependency

Không nâng cấp rời rạc từng thư viện Spring theo cảm tính. Spring Cloud dùng **release train BOM** được thiết kế tương thích với một nhóm Spring Boot cụ thể; Spring Batch và Stream thường nhận version thông qua dependency management của hệ sinh thái.

Ví dụ các tổ hợp được bảng tương thích Spring Cloud công bố ở giai đoạn 2025–2026 (cần kiểm tra lại khi chọn bản release cụ thể):

| Spring Cloud release train | Spring Boot generation | Lưu ý khi lập kế hoạch |
| --- | --- | --- |
| `2025.0.x` | `3.5.x` | Thế hệ Spring Boot 3, cần tra đúng dòng Spring Batch được quản lý |
| `2025.1.x` | `4.0.x` và các bản `4.1.x` được hỗ trợ theo bản train | Có thể kéo theo thay đổi lớn từ Boot 3 → 4 và Batch 5 → 6 |
| `2026.0.x` | `4.2.x` theo tài liệu train tương ứng | Đọc tài liệu Task/Stream/Batch/Binder đúng bản phát hành |

**Đây không phải danh sách các tổ hợp chắc chắn được hỗ trợ mãi mãi.** Cần dùng [bảng chính thức của Spring Cloud](https://spring.io/projects/spring-cloud/) và release notes của từng phiên bản để xác nhận **từng patch release**.

Lập manifest phiên bản trước khi thay đổi:

~~~text
service                 daily-import-task
old-artifact            daily-import-task:1.8.3
new-artifact            daily-import-task:2.0.0
old-java                (điền từ baseline)
new-java                (điền từ target)
spring-boot             old -> new
spring-cloud-train      old -> new
spring-cloud-task       old -> new
spring-batch            old -> new
spring-cloud-stream     old -> new
kafka-binder            old -> new
spring-cloud-deployer   old -> new
scdf-server             old -> new, nếu có
postgresql-driver       old -> new
schema-task             old -> target
schema-batch            old -> target
kafka-cluster           broker + protocol + ACL
runtime                 k8s/CF/local + cluster/version
image-digest            sha256:<digest mới>
~~~

Không suy đoán version đã được load từ số trong `pom.xml`: cần kiểm tra **dependency tree**, BOM precedence, plugin đóng gói và artifact thật trong image. Ví dụ cách lấy cây dependency qua Maven, chạy tại **dự án được phép build**:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

Không dùng output này để thay thế việc chạy một test tích hợp. Nó chỉ xác nhận phần **phụ thuộc và cấu hình build**.

### Câu hỏi cần trả lời trước khi chọn target

- Bản Spring Boot target yêu cầu Java tối thiểu/khả năng chạy với image/JDK nào?
- Spring Cloud Task target có hỗ trợ chính xác Boot release đó không?
- Stream binder target tương thích broker/Kafka client/serialization hay không?
- Spring Batch target có migration DDL và thay đổi `JobParameters` hay không?
- Deployer/Spring Cloud Data Flow target có nhận artifact mới và chấp nhận deployment properties cũ không?
- Dữ liệu lịch sử nào **bắt buộc** phải đọc hoặc restart sau nâng cấp?
- Có nhiều phiên bản worker cùng chạy trên một `JobRepository`/`TaskRepository` không? Chính sách hỗ trợ mixed-version được xác nhận chưa?

## 4. Ghi baseline bằng một “golden run”

Trước khi upgrade, chạy phiên bản cũ trên môi trường staging có dữ liệu mẫu kiểm soát, và lưu toàn bộ dấu vết. Ví dụ một job đối soát cho `businessKey=shop-01|2026-11-24|v1`.

Một **golden run** nên có:

| Dữ liệu baseline | Ví dụ | Nguồn |
| --- | --- | --- |
| Artifact chính xác | Version, digest image hoặc hash JAR | Registry/build manifest |
| Đầu vào | Business key, tham số Batch, snapshot dữ liệu, runId | API/scheduler |
| Launch receipt | Request ID, execution ID, external runtime ID | SCDF/Deployer |
| Task metadata | `TASK_EXECUTION_ID`, `START_TIME`, `END_TIME`, `EXIT_CODE` | `TaskRepository` |
| Batch metadata | `JOB_INSTANCE_ID`, `JOB_EXECUTION_ID`, `STATUS`, `EXIT_CODE` | `JobRepository` |
| Liên kết Task–Batch | Mapping Task ↔ Job | `TASK_TASK_BATCH`, khi feature hoạt động |
| Đầu ra nghiệp vụ | Row count, checksum, unique business key | DB/file/API nghiệp vụ |
| Event | Số message, destination, schema, correlation ID | Kafka/Rabbit + consumer |
| Runtime | Pod status, exit code, OOM, launch-to-finish duration | Deployer/Kubernetes |
| Hiệu năng | JVM startup, batch throughput, DB query time, lag broker | Log/metrics |

**Một bản ghi baseline hợp lệ không chỉ là ảnh chụp màn hình.** Ghi cả lệnh launch, cấu hình đã được che secret, thời điểm, tham số và công cụ truy vấn. Nếu các dữ liệu này không được lưu, khó phân biệt regression do nâng cấp với biến động nguồn dữ liệu.

### Không so sánh bằng ID tuyệt đối

Lần chạy mới sẽ thường có `TASK_EXECUTION_ID` và `JOB_EXECUTION_ID` khác. Thay vì so sánh ID bằng nhau, hãy so sánh **quan hệ và điều kiện**:

- Một lần launch đúng mục đích tạo một TaskExecution khi hạ tầng sẵn sàng.
- TaskExecution liên kết đúng JobExecution.
- Job/Step đạt trạng thái mong đợi.
- Output có cùng business key, số lượng và checksum theo contract.
- Event start/end cùng nhận diện một execution, không cần có ID giống baseline.
- Runtime kết thúc với mã thoát đúng theo policy.

## 5. Chạy test trên schema mới và dữ liệu lịch sử

Một bản upgrade có thể chạy trên **DB trống** nhưng thất bại khi đọc `JobRepository` cũ. Do đó test database nên có **ít nhất ba trường hợp**:

1. **Fresh install:** schema Task và Batch được tạo bằng DDL đúng phiên bản mới; chạy job lần đầu.
2. **Upgrade từ bản cũ:** clone/snapshot schema và metadata cũ vào môi trường cô lập, áp dụng migration có kiểm soát, sau đó chạy ứng dụng mới.
3. **Historical compatibility:** thử xem lại lịch sử `TaskExecution`/`JobExecution` và đọc các Job/ExecutionContext mà nghiệp vụ cần giữ.

### 5.1. Không sửa trực tiếp các bảng metadata như bảng nghiệp vụ

Spring Cloud Task dùng các bảng như `TASK_EXECUTION`, `TASK_EXECUTION_PARAMS`, `TASK_TASK_BATCH`. Spring Batch dùng `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` và các bảng parameter/context. Mỗi framework sở hữu schema và cách ánh xạ của mình.

Một migration đúng cần:

- Backup/snapshot dữ liệu trước khi chạy.
- Dùng DDL migration chính thức hoặc script có review, tương ứng **đúng phiên bản nguồn và đích**.
- Kiểm tra quyền, sequence, index, khóa ngoại, prefix tên bảng và database vendor.
- Có kế hoạch xử lý mã `ExecutionContext` đã serialize, JobParameters của phiên bản cũ và dữ liệu còn dở.
- Không để nhiều process tự chạy DDL cạnh tranh trong production.

Ví dụ một cấu hình production thường quản lý schema từ ngoài ứng dụng:

~~~yaml
spring:
  batch:
    jdbc:
      initialize-schema: never
  cloud:
    task:
      initialize-enabled: false
~~~

`initialize-enabled: false` chỉ ngừng tự khởi tạo bảng Task, **không tắt `TaskRepository`**. Ở staging mới tạo, có thể cấp schema trước bằng migration và chạy cùng cấu hình này để phản ánh production.

### 5.2. Đặc biệt khi chuyển Spring Batch 5 → 6

Migration guide chính thức của Spring Batch 6 nêu thay đổi cách biểu diễn/lưu `JobParameters`, domain model và một số API. Một hệ quả quan trọng: **JobInstance thất bại tạo bằng Batch 5 không thể restart trực tiếp bằng Batch 6 do format parameter khác nhau** theo hướng dẫn migration. Vì thế, trước khi cutover cần **restart hoàn tất hoặc abandon** các JobInstance thất bại còn ở Batch 5 theo quy trình phù hợp.

Điều này không đồng nghĩa mọi lịch sử v5 đều phải xóa. Cần tách rõ:

- **Đọc/audit metadata cũ:** thử bằng API/truy vấn tương thích trong môi trường đã migrate.
- **Restart đúng một JobInstance đã thất bại:** có thể bị ràng buộc version và serialization.
- **Tạo JobInstance mới cho cùng công việc nghiệp vụ:** không được dùng để lách vấn đề restart nếu chưa có idempotency và quyết định nghiệp vụ rõ.

Nếu nâng cấp Boot/Batch qua **hai thế hệ**, lập một cửa sổ dừng worker, chốt trạng thái các Job dang dở và xác minh khả năng rollback **trước khi đổi schema**. Không hứa hẹn rollback chỉ bằng cách thay Docker image khi database đã áp dụng migration không tương thích.

## 6. Xác minh tích hợp Spring Cloud Task ↔ Spring Batch

Spring Cloud Task hỗ trợ liên kết `TaskExecution` với `JobExecution` qua `TaskBatchExecutionListener`. Tài liệu mô tả listener có thể được tự động gắn khi có `Job` và module `spring-cloud-task-batch` trong classpath. Sau nâng cấp cần kiểm tra **classpath, auto-configuration và kết quả thực tế**, không chỉ xét tên bean.

### 6.1. Những hành vi phải giữ

- `Job` thực sự được khởi chạy **một lần theo ý định**, không bị gọi hai lần vì vừa có Batch auto-runner vừa có runner custom.
- `JobParameters` của yêu cầu có đúng giá trị, đúng kiểu và đúng ý nghĩa identifying/non-identifying.
- `JobExecution` thuộc đúng `JobInstance`; retry và restart làm theo chính sách đã xác định.
- `StepExecution` có trạng thái/counters/checkpoint hợp lệ.
- Mapping Task–Batch được lưu khi feature được bật và repository sẵn sàng.
- `BatchStatus.FAILED` được phản ánh đúng lên `TaskExecution.exitCode` và exit code process khi policy yêu cầu.
- Các kết quả nghiệp vụ đã commit không bị tạo lại chỉ vì execution ID mới.

### 6.2. Cấu hình mẫu để thử đường lỗi

~~~yaml
spring:
  application:
    name: upgrade-smoke-task
  main:
    web-application-type: none
  batch:
    job:
      enabled: true
    jdbc:
      initialize-schema: never
  cloud:
    task:
      name: upgrade-smoke-task
      initialize-enabled: false
      batch:
        fail-on-job-failure: true
~~~

Phần này không chứa datasource/credentials; phải cung cấp qua Secret hoặc biến môi trường của test. `fail-on-job-failure` là chính sách yêu cầu Batch failure phản ánh qua mã thoát Task, **không tự bảo đảm mọi loại lỗi JVM/Deployer đều được ghi vào TaskRepository**.

Ở một số dòng phiên bản, thay đổi thứ tự `ApplicationRunner` của Batch integration có thể ảnh hưởng hành vi. Tài liệu Spring Cloud Task có property `spring.cloud.task.batch.applicationRunnerOrder` đối với dòng hỗ trợ. Hãy kiểm tra property metadata theo version, đặc biệt nếu ứng dụng có **nhiều runner** hoặc logic chuẩn bị dữ liệu trước khi Job chạy.

### 6.3. Truy vấn SQL đối soát Task và Batch

Theo schema Spring Cloud Task JDBC tham khảo, bảng `TASK_TASK_BATCH` lưu mapping:

~~~sql
SELECT t.TASK_EXECUTION_ID,
       t.TASK_NAME,
       t.START_TIME AS TASK_START_TIME,
       t.END_TIME   AS TASK_END_TIME,
       t.EXIT_CODE  AS TASK_EXIT_CODE,
       j.JOB_EXECUTION_ID,
       j.STATUS     AS BATCH_STATUS,
       j.EXIT_CODE  AS BATCH_EXIT_CODE
FROM TASK_EXECUTION t
JOIN TASK_TASK_BATCH m
  ON m.TASK_EXECUTION_ID = t.TASK_EXECUTION_ID
JOIN BATCH_JOB_EXECUTION j
  ON j.JOB_EXECUTION_ID = m.JOB_EXECUTION_ID
ORDER BY t.TASK_EXECUTION_ID DESC;
~~~

Nếu kết quả không có row, không vội kết luận task chưa chạy. Hãy kiểm tra:

1. Có row riêng trong `TASK_EXECUTION` không?
2. Có row riêng trong `BATCH_JOB_EXECUTION` không?
3. Có `spring-cloud-task-batch` và `TaskBatchExecutionListener` hoạt động không?
4. Có dùng cùng schema/prefix/datasource mà ứng dụng thực sự ghi không?
5. Job có chạy trước khi listener được gắn, hoặc bị khởi tạo lỗi không?

Một mapping hợp lệ cho lần chạy mới là bằng chứng tốt hơn việc chỉ xem log `Job completed`.

### 6.4. Phân biệt kết quả Batch với kết quả Task

| Quan sát | Diễn giải đúng |
| --- | --- |
| `BatchStatus.COMPLETED` | Job/Step được Batch đánh dấu hoàn tất; vẫn cần xác minh output |
| `BatchStatus.FAILED` + Task exit code `0` | Có thể mất policy ánh xạ, auto-config thay đổi hoặc ứng dụng nuốt lỗi |
| `BatchStatus.FAILED` + Task exit code khác `0` | Policy exit code hoạt động cho trường hợp test; cần kiểm tra mã thoát process |
| Task exit code khác `0`, nhưng output đã có | Có thể commit nghiệp vụ trước khi lỗi metadata/hậu xử lý |
| Không có TaskExecution nhưng launcher đã chạy | Có thể lỗi rất sớm khi tạo `ApplicationContext` |

Một assertion “mã thoát khác 0” cũng chưa đủ: process có thể fail vì **lỗi thiếu dependency** thay vì lỗi Batch mà test dự định. Cần xem nguyên nhân exception và JobExecution trong database.

## 7. Kiểm tra restart, checkpoint và dữ liệu nghiệp vụ

Upgrade không được làm hỏng các hành vi restart quan trọng.

### 7.1. Những trường hợp phải thử

| Trường hợp | Cần xác minh |
| --- | --- |
| Job chạy từ đầu | Đúng JobInstance, StepExecution, số dòng ghi và exit code |
| Job thất bại ở giữa chunk | Chỉ các chunk đã commit được giữ theo transaction; checkpoint phù hợp |
| Restart bằng cùng identifying parameters | Hành vi đúng theo Batch version và trạng thái JobInstance |
| Retry toàn bộ Task nhưng tạo JobInstance mới | Không nhân đôi output nhờ business key và unique constraint |
| Lỗi `JobRepository` lúc cập nhật | Kết quả commit không được suy đoán theo log; cần đối soát |
| Nâng cấp v5 → v6 với JobInstance thất bại cũ | Được xử lý xong/abandon trước cutover, không tự restart mù |
| Hai worker cùng xử lý một partition | Lock/fencing/idempotency tại nơi ghi, không chỉ metadata |

### 7.2. Đặt bất biến nghiệp vụ trong database

Ví dụ bảng output:

~~~sql
CREATE TABLE daily_report (
    tenant_id       VARCHAR(64) NOT NULL,
    business_date   DATE NOT NULL,
    report_version  VARCHAR(24) NOT NULL,
    payload_hash    CHAR(64) NOT NULL,
    report_body     TEXT NOT NULL,
    PRIMARY KEY (tenant_id, business_date, report_version)
);
~~~

Nếu cùng yêu cầu bị chạy lại, unique key chặn row trùng. Tuy nhiên, nếu row đã tồn tại với `payload_hash` khác, ứng dụng phải **báo conflict hoặc xử lý version nghiệp vụ**, không trả `ALREADY_APPLIED` một cách mù quáng.

Một regression khó phát hiện sau upgrade: code mới dùng timestamp hiện tại làm identifying JobParameter nên sinh `JobInstance` mới cho mỗi attempt, trong khi business key thực tế không đổi. JobRepository không thể thay ràng buộc unique ở bảng nghiệp vụ.

## 8. Xác minh Spring Cloud Stream sau nâng cấp

Khi tích hợp Task–Stream hoạt động, Spring Cloud Task có thể phát các sự kiện chứa `TaskExecution` lúc bắt đầu và kết thúc thông qua binding logic `task-events`. Nếu tích hợp Batch events, các binding như `job-execution-events`, `step-execution-events` hoặc `chunk-events` có thể được cấu hình riêng.

Sau nâng cấp cần kiểm tra **cả producer và consumer**, vì “topic có message” chưa chứng minh consumer parse đúng schema.

### 8.1. Cấu hình producer và consumer minh họa

Phía task:

~~~yaml
spring:
  cloud:
    task:
      events:
        enabled: true
      batch:
        events:
          enabled: true
    stream:
      bindings:
        task-events:
          destination: ops.task.lifecycle.v1
          contentType: application/json
        job-execution-events:
          destination: ops.batch.job.v1
          contentType: application/json
      kafka:
        binder:
          brokers: ${KAFKA_BROKERS}
~~~

Phía consumer sử dụng một function `Consumer` tên `observeTask`:

~~~yaml
spring:
  cloud:
    function:
      definition: observeTask
    stream:
      bindings:
        observeTask-in-0:
          destination: ops.task.lifecycle.v1
          group: task-observer
          contentType: application/json
      kafka:
        binder:
          brokers: ${KAFKA_BROKERS}
~~~

**Lưu ý:**

- `task-events` là **binding logic output**, còn `ops.task.lifecycle.v1` là **Kafka topic đích**; không tự đổi tên binding trong cấu hình producer rồi mong listener tìm thấy.
- Dạng property tương đương ở producer là `spring.cloud.stream.bindings.task-events.destination=ops.task.lifecycle.v1`; ở consumer là `spring.cloud.stream.bindings.observeTask-in-0.destination=ops.task.lifecycle.v1`.
- Với mô hình functional, `observeTask-in-0` là input binding mặc định của function `observeTask`.
- Broker, topic, ACL, content type, converter, serializer và consumer group phải được đối chiếu ở **runtime**, không chỉ trong YAML.
- Đây là các cấu hình gợi ý để dựng test; phiên bản binder và event module phải được lựa chọn từ train tương thích, không lấy ngẫu nhiên artifact version.

### 8.2. Test “golden message contract”

Lưu một event thật ở phiên bản cũ, **đã loại dữ liệu nhạy cảm**, rồi kiểm thử consumer mới trên payload đó. Đồng thời lấy một event của producer mới và kiểm thử consumer cũ nếu có giai đoạn chạy song song.

Ma trận:

| Producer | Consumer | Kết luận mong muốn |
| --- | --- | --- |
| Cũ | Cũ | Baseline hợp lệ |
| Mới | Mới | Đường vận hành mới hoạt động |
| Cũ | Mới | Cần hỗ trợ nếu rolling upgrade chạy chéo |
| Mới | Cũ | Cần hỗ trợ nếu consumer cũ còn tồn tại khi canary phát message |

Đối với payload JSON/Avro/Protobuf, test đúng hợp đồng của từng hệ thống: tên field, kiểu `executionId`, timestamp, nullability, enum, contentType, header và version schema. Một consumer dùng `Map<String,Object>` không miễn kiểm tra type runtime, ví dụ số có thể được đọc thành `Integer` hoặc `Long`.

**Không so sánh byte-for-byte** nếu thứ tự trường JSON hoặc cách serialize ngày có thể khác nhưng contract vẫn tương thích. Dùng schema/DTO hoặc kiểm tra trường và ý nghĩa.

### 8.3. Event start/end và tính đầy đủ

Test phải trả lời:

1. Có event tương ứng lúc bắt đầu và lúc kết thúc cho một TaskExecution **hoàn tất bình thường** không?
2. Chúng có cùng execution ID hoặc correlation ID phù hợp không?
3. Event cuối có exit code/end time đúng với row repository theo schema/payload thực tế không?
4. Nếu Batch Job thất bại, `job-execution-events` và `task-events` có phản ánh trạng thái phù hợp không?
5. Nếu JVM bị kill trước shutdown, monitoring có giữ trạng thái `UNKNOWN` thay vì kết luận nhầm `RUNNING` mãi không?
6. Nếu broker phát lại, consumer có idempotent theo **(executionId, lifecycle phase)** hay cơ chế tương đương không?

Một consumer chỉ deduplicate theo `executionId` có thể nhận start event rồi **bỏ mất end event**. Mốc phase cần suy ra từ message và protocol thực tế, không được mặc định payload mọi version có trường `phase`.

## 9. Test Binder và broker thật phục vụ mục tiêu khác nhau

Spring Cloud Stream Test Binder hỗ trợ test contract và function trong Spring context **không cần Kafka/Rabbit thật**. Đây là lớp test nhanh, nhưng không chứng minh các yếu tố broker:

- Broker endpoint, TLS/SASL, quyền publish/subscribe.
- Topic tồn tại và destination mapping đúng.
- Serializer/converter thực tế, offset, consumer group, partition key, retry/DLQ.
- Thời điểm task rất ngắn thoát khỏi JVM và khả năng flush message trước shutdown.
- Mạng bị ngắt, producer ACK bị mất hoặc consumer redelivery.

Vì vậy nên chia:

- **Contract tests:** Test Binder trong module/test profile phù hợp, validate payload và mapping.
- **Broker integration tests:** Kafka/Rabbit thật (có thể dùng Testcontainers), chạy task/consumer trong process độc lập và chờ message với deadline hữu hạn.

Tài liệu Spring Cloud Stream cũng lưu ý tránh trộn Test Binder với binder thật trong cùng một module test không kiểm soát vì test binder có thể được lựa chọn thay broker. Tách profile hoặc module giúp test broker thật không “pass giả” trên kênh in-memory.

### Bằng chứng bắt buộc ở broker thật

~~~text
runId=upgrade-20261124-001
taskExecutionId=<ID do repository cấp>
brokerCluster=<cluster kiểm thử>
taskBinding=task-events
taskTopic=ops.task.lifecycle.v1
batchBinding=job-execution-events
batchTopic=ops.batch.job.v1
consumerGroup=task-observer
receivedStart=true|false
receivedEnd=true|false
receivedBatchEvent=true|false
payloadSchema=version kiểm chứng
consumerAckStatus=theo binder
~~~

Không có dữ liệu trong biểu mẫu này mặc định đồng nghĩa thất bại; phải điều tra rõ **chưa launch, chưa publish, chưa broker ACK hay consumer chưa đọc**.

## 10. Xác minh Deployer: launch receipt không phải completion

Với Spring Cloud Data Flow hoặc ứng dụng dùng Spring Cloud Deployer, lớp Deployer chịu trách nhiệm triển khai artifact, cấp cấu hình và tạo tiến trình trên nền tảng như Kubernetes, Cloud Foundry hoặc local.

Sau nâng cấp cần kiểm tra theo chuỗi:

~~~mermaid
flowchart TD
    A["Đăng ký artifact/version mới"] --> B["Launch request"]
    B --> C{"Deployer tiếp nhận?"}
    C -->|"Có"| D["Receipt / deployment ID"]
    C -->|"Không"| X["Lỗi launch"]
    D --> E["Image pull / tạo Pod hoặc process"]
    E --> F["JVM bootstrap + TaskExecution"]
    F --> G["Batch Job / nghiệp vụ"]
    G --> H["Runtime kết thúc + exit code"]
    H --> I["Đối soát TaskRepository + Batch + output + events"]
    E -. "Pull/secret/quota failure" .-> J["Có thể không có TaskExecution"]
    F -. "ApplicationContext failure" .-> J
~~~

**Một response launch thành công không chứng minh ứng dụng đã chạy xong.** Nếu Kubernetes không tải được image, thiếu Secret, ServiceAccount bị từ chối hoặc runtime có JDK không phù hợp, Deployer vẫn có thể đã tạo hoặc yêu cầu tạo Job nhưng Task không tạo `TaskExecution`.

### 10.1. Những trường cần giữ khi phát TaskLaunchRequest

Ở mô hình khởi chạy qua Spring Cloud Stream, `TaskLaunchRequest` có thể chứa:

| Trường | Ý nghĩa cần test |
| --- | --- |
| `uri` | Artifact được gọi đúng version/coordinate |
| `applicationName` | Tên task dùng trong launcher, log/metadata |
| `commandLineArguments` | Business key, JobParameters và option Boot được chuyển nguyên vẹn |
| `environmentProperties` | Cấu hình môi trường cần thiết được chuyển đúng, secret không lộ |
| `deploymentProperties` | Thuộc tính deployer như resource/namespace/instance settings nếu hỗ trợ |

Ví dụ minh họa theo API `TaskLaunchRequest` của một dòng phiên bản có constructor này:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.cloud.task.launcher.TaskLaunchRequest;

TaskLaunchRequest request = new TaskLaunchRequest(
    "maven://com.example:daily-report-task:jar:2.0.0",
    List.of("--businessDate=2026-11-24",
            "--tenant=shop-01",
            "--runId=upgrade-20261124-001"),
    Map.of("SPRING_PROFILES_ACTIVE", "staging"),
    Map.of(),
    "daily-report-task"
);
~~~

Đoạn mã chỉ **tạo request**, không tự gửi message hay triển khai task. Cần sink/launcher và binder thích hợp. Deployer trên Kubernetes có thể yêu cầu **container image** thay vì cơ chế lấy Maven JAR tùy thiết kế; `uri` phải đúng loại artifact mà launcher đang dùng thực sự hỗ trợ.

### 10.2. Kiểm thử launch bằng artifact không đổi và artifact mới

- **Giữ nguyên artifact, đổi deployer:** phân lập regression của hạ tầng triển khai.
- **Giữ nguyên deployer, đổi artifact:** phân lập regression của Boot/Task/Batch.
- **Đổi cả hai:** thực hiện sau khi từng trục đã được xác minh, với một end-to-end canary.

Ở SCDF, cần kiểm tra **task application version/default version**, tham số deployer và hành vi khi task cũ còn chạy. Tài liệu SCDF có các kịch bản launch khi artifact/properties không đổi hoặc khi cần upgrade deployment; một số platform có thể **chặn upgrade đang có task chạy** để tránh phá hủy deployment cũ. Không suy ra quy tắc này đúng y nguyên ở mọi SCDF/platform/version.

## 11. Nếu dùng remote partitioning: phải kiểm cả manager và worker

Spring Cloud Task cung cấp cơ chế tích hợp **Spring Batch remote partitioning** thông qua các lớp như `DeployerPartitionHandler` và `DeployerStepExecutionHandler` trong các phiên bản hỗ trợ. Manager tạo partition, Deployer khởi chạy worker, và worker phải tìm đúng `StepExecution` trong `JobRepository`.

Nâng cấp có thể làm sai đường này dù một Job không partition vẫn chạy tốt.

### 11.1. Contract cần kiểm

- Manager và worker dùng **tổ hợp thư viện/phần model tương thích**, cùng format metadata mà version hỗ trợ.
- Worker được khởi chạy với đúng artifact URI/image, biến môi trường, Job/StepExecution ID và cấu hình datasource.
- Worker tra được `StepExecution` trong **đúng `JobRepository`**, không phải database trống hay schema khác.
- `gridSize`, số worker đồng thời, poll interval, timeout và thread pool không vượt khả năng Deployer.
- Một worker chết không khiến manager báo Job hoàn tất giả; retry worker không ghi trùng dữ liệu đã commit.
- Các partition có key/range không chồng chéo; restart kế thừa checkpoint hợp lệ.
- Tác vụ worker ngắn hạn đóng context/tiến trình đúng sau xử lý; không để pod tồn tại mãi.

### 11.2. Ma trận test partition

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Một partition | Worker khởi chạy, đọc/ghi đúng, manager nhận kết quả |
| Nhiều partition | Số partition đúng, không mất/nhân bản record |
| Một worker crash | Manager phát hiện lỗi hoặc timeout, Job không báo success giả |
| Launcher từ chối tạo worker | Không treo vô hạn, có thông tin lỗi rõ |
| Worker chạy image/version sai | Có kiểm soát compatibility/canary và cảnh báo |
| Worker dùng sai DB/schema | Fail rõ ràng, không tạo record ở repository khác |
| Retry partition sau commit không rõ | Kết quả idempotent, có đối soát business key |
| Thay đổi max workers | Không vượt quota/connections, throughput ở mức chấp nhận |

Tránh cấu hình timeout **vô hạn** rồi chỉ kiểm tra rằng manager “đang chờ”: khi worker không bao giờ xuất hiện, test phải kết thúc bằng **deadline rõ ràng**.

## 12. Ví dụ test harness chạy JAR trong tiến trình riêng

Một test `@SpringBootTest` có thể đo logic Job trong context, nhưng không đủ để chứng minh Deployer, kết thúc JVM, process exit code và publish event cuối. Cần một bài test chạy **artifact thật** trong JVM/Pod riêng.

Ví dụ khung JUnit 5 dùng `ProcessBuilder` khi thử trên máy/build agent có Java và một JAR đã build:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class UpgradeProcessSmokeIT {

    @Test
    void taskKetThucTrongGioiHan() throws Exception {
        Path artifact = Path.of(
            "target", "daily-report-task-2.0.0.jar");

        ProcessBuilder builder = new ProcessBuilder(
            "java", "-jar", artifact.toString(),
            "--businessDate=2026-11-24",
            "--tenant=shop-01",
            "--runId=upgrade-20261124-001");

        // Mã thật phải lấy endpoint/secret từ Testcontainers
        // hoặc một môi trường tích hợp cô lập.
        builder.environment().put(
            "SPRING_PROFILES_ACTIVE", "integration");

        // Chuyển output đến file test để tránh đầy pipe buffer.
        builder.redirectErrorStream(true);
        builder.redirectOutput(
            Path.of("target", "upgrade-smoke.log").toFile());

        Process child = builder.start();
        try {
            boolean completed =
                child.waitFor(90, TimeUnit.SECONDS);

            if (!completed) {
                child.destroy();
                if (!child.waitFor(5, TimeUnit.SECONDS)) {
                    child.destroyForcibly();
                }
                fail("Task vượt timeout kiểm thử");
            }

            assertEquals(0, child.exitValue(),
                "Kiểm tra log và repository khi exit != 0");
        } finally {
            if (child.isAlive()) {
                child.destroyForcibly();
            }
        }
    }
}
~~~

Đây là **mã khung minh họa**, không thay thế cấu hình môi trường test. Trong một dự án thực tế phải:

1. Build JAR trước integration-test phase, hoặc nhận đường dẫn artifact từ CI.
2. Tạo thư mục output log và cô lập tên file theo test; tránh nhiều test ghi đè.
3. Cấp `TASK_DB_URL`, username/password, broker endpoint/credentials qua biến môi trường hoặc Secret test, **không in giá trị secret**.
4. Chờ process với timeout; thu exit code và log trước khi đóng test.
5. Truy vấn PostgreSQL và broker **sau** khi process dừng để đối chiếu TaskExecution, Batch metadata, event và output.
6. Không chạy test process-level với datasource H2 `mem:` nếu cần kiểm tra dữ liệu sau khi JVM con thoát.
7. Kiểm tra thêm *negative path* như `--failDemo=true` hoặc lỗi dữ liệu có chủ đích; kết quả non-zero phải do **đúng nguyên nhân kỳ vọng**, không phải thiếu class/DB.

Ở môi trường Kubernetes, thay `ProcessBuilder` bằng API hoặc công cụ điều phối **tạo Job thử nghiệm** và chờ trạng thái Job/Pod. Không dùng success từ API tạo Job làm bằng chứng hoàn tất.

## 13. Bảng kiểm thử bắt buộc trước–sau nâng cấp

Đây là bộ test cốt lõi cho một hệ thống có Batch + Stream + Deployer:

| ID | Kịch bản | Bằng chứng chấp nhận |
| --- | --- | --- |
| U01 | App context khởi tạo bằng artifact mới | Không có lỗi dependency/autoconfiguration; correct profile/JDK |
| U02 | Launch qua Deployer | Có receipt; pod/process được tạo đúng image digest |
| U03 | Task thành công | `END_TIME`, Task exit code và process exit code đúng; output hợp lệ |
| U04 | Batch Job thành công | `BatchStatus.COMPLETED`, Step đúng, mapping Task–Batch có |
| U05 | Batch Job thất bại | `BatchStatus.FAILED`; Task/process non-zero theo policy |
| U06 | Event Task start/end | Topic đúng; payload contract; nhận diện execution khớp |
| U07 | Batch Job event | Topic riêng; trạng thái job khớp JobRepository |
| U08 | Consumer mới nhận payload cũ | Tương thích rolling upgrade hoặc kế hoạch cắt chuyển rõ |
| U09 | Consumer cũ nhận payload mới | Tương thích trong giai đoạn song song hoặc có versioned topic |
| U10 | Restart/JobParameters | Đúng JobInstance, checkpoint, chiến lược với history cũ |
| U11 | Retry cùng business key | Không nhân đôi output; conflict được phát hiện |
| U12 | PostgreSQL migration | Đọc được metadata lịch sử trong phạm vi hỗ trợ, sequence/index đúng |
| U13 | Broker down/ACL sai | Fail/alert có lý do; không báo event đã được nhận khi chưa |
| U14 | DB down lúc bootstrap | Log runtime có lỗi; không khẳng định TaskExecution phải tồn tại |
| U15 | JVM bị kill giữa job | Không yêu cầu event cuối; runtime/reconciliation xác định tình trạng |
| U16 | Remote partitioning nếu dùng | Worker launch, StepExecution mapping, timeout và retry đúng |
| U17 | Overlap/2 executions | Idempotency và unique key ngăn trùng |
| U18 | So sánh hiệu năng | Đạt ngưỡng đã đo trên baseline tương đương |
| U19 | Canary dùng artifact mới | Không tăng tỉ lệ lỗi/lag/timeout so với baseline |
| U20 | Rollback rehearsal | Khôi phục được theo chính sách DB/schema/event/worker đã chuẩn bị |

Không phải ứng dụng nào cũng dùng remote partitioning hoặc Batch events. Những mục **không áp dụng** phải được ghi rõ lý do, không để trống như chưa kiểm tra.

## 14. Tự động hóa assertions: chỉ kiểm tra kết quả có ý nghĩa

### 14.1. Ví dụ SQL kiểm tra metadata Batch–Task

Đếm task theo mã kết thúc trong một cửa sổ test, dùng tham số timestamp do framework/test cung cấp:

~~~sql
SELECT TASK_NAME,
       EXIT_CODE,
       COUNT(*) AS RUNS
FROM TASK_EXECUTION
WHERE START_TIME >= ?
  AND START_TIME < ?
GROUP BY TASK_NAME, EXIT_CODE
ORDER BY TASK_NAME, EXIT_CODE;
~~~

Với JDBC `PreparedStatement`/`JdbcTemplate`, hai placeholder `?` được binding bằng mốc bắt đầu/kết thúc của từng bài test. Không so sánh số row toàn database nếu có lịch sử cũ hoặc test chạy song song.

Một truy vấn kiểm tra liên kết Task–Batch trong phạm vi test:

~~~sql
SELECT COUNT(*) AS LINKED_JOBS
FROM TASK_TASK_BATCH m
JOIN TASK_EXECUTION t
  ON t.TASK_EXECUTION_ID = m.TASK_EXECUTION_ID
JOIN BATCH_JOB_EXECUTION j
  ON j.JOB_EXECUTION_ID = m.JOB_EXECUTION_ID
WHERE t.TASK_NAME = ?
  AND t.START_TIME >= ?;
~~~

Đối chiếu số `LINKED_JOBS` với số Job thực tế mà golden run cần. Nếu `Job` chưa chạy vì lỗi bootstrap, thiếu mapping là **hệ quả**, không phải nguyên nhân gốc.

### 14.2. Ví dụ JSON contract assertion

Với một payload `task-events`:

~~~json
{
  "executionId": 502,
  "taskName": "upgrade-smoke-task",
  "startTime": "2026-11-24T01:00:00Z",
  "endTime": "2026-11-24T01:00:08Z",
  "exitCode": 0
}
~~~

Đây là **payload minh họa**, không phải serializer contract bắt buộc của mọi Spring Cloud Task version. Test phải dựa vào JSON/schema thật của bản cũ và bản mới. Các assertion nên kiểm tra:

- Có `executionId` hợp lệ; identity khớp một row từ TaskRepository.
- `taskName`, `startTime`, `endTime` và `exitCode` được parse với kiểu/semantics đúng khi có.
- Event start và end được nhận diện bằng dữ liệu version thực tế, không vì trùng execution ID mà bị bỏ một event.
- Trường thêm mới được consumer xử lý theo contract backward compatibility.
- Timestamp timezone/precision được so sánh phù hợp (không buộc hai chuỗi phải giống tuyệt đối nếu cả hai cùng biểu thị một instant).

## 15. Nâng cấp có thể làm thay đổi hiệu năng

Một upgrade tăng độ trễ không nhất thiết là lỗi logic nhưng có thể gây **quá SLA**, đặc biệt với task ngắn hạn có overhead bootstrap lớn.

### 15.1. Đo theo từng giai đoạn

| Chỉ số | Đo ở đâu | Regression có thể phát hiện |
| --- | --- | --- |
| Launch-to-pod-ready | Deployer/cluster | Pull image chậm, admission/quota, resource |
| JVM/context startup | Log/telemetry Boot | Autoconfiguration nhiều hơn, classpath, JDK |
| Task runtime | `TaskExecution` + process | Tăng tổng thời gian |
| Batch Job/Step duration | `JobRepository`, Step metrics | Chunk size, JDBC, serialization |
| Throughput | Business rows / thời gian | Reader/processor/writer giảm tốc |
| DB pool/lock/wait | PostgreSQL metrics | Concurrent job/migration/index |
| Event publish latency | Broker/producer metrics | Batching/acks/serializer |
| Consumer lag | Kafka consumer group | Converter hoặc processing chậm |
| Remote worker launch latency | Deployer/manager logs | Partition scaling và provisioning |

Khi so sánh v1/v2, giữ nguyên **snapshot dữ liệu**, số partition, CPU/memory limit, broker/database và thời gian warmup hợp lý. Không so sánh lần chạy cache nóng với lần chạy cache lạnh rồi kết luận thư viện bị regression.

### 15.2. Đặt ngưỡng nghiệm thu trước khi chạy

Ví dụ ngưỡng do nhóm vận hành thống nhất:

~~~text
task_success_rate >= 99.9% trên canary (nếu mẫu đủ lớn)
p95_launch_to_finish <= baseline_p95 * 1.20
p95_batch_step_duration <= baseline_p95 * 1.15
task_event_missing_end = 0 khi runtime shutdown bình thường và broker khỏe
duplicate_business_output = 0
unexplained_batch_task_exit_mismatch = 0
database_migration_errors = 0
remote_partition_stuck_above_deadline = 0
~~~

Các số phần trăm chỉ là **ví dụ chính sách**, không phải SLA hay default của framework. Khi số lượng canary ít, tỉ lệ 99,9% không có ý nghĩa thống kê; cần dùng test có kiểm soát và kiểm tra **mọi run** thay vì một biểu đồ phần trăm đẹp.

## 16. Quy trình nâng cấp theo từng giai đoạn

Một lộ trình thực tế:

~~~mermaid
flowchart TD
    A["Khóa baseline và dependency manifest"] --> B["Kiểm tra compatibility/migration guide"]
    B --> C["Backup DB + diễn tập schema migration"]
    C --> D["Chạy contract/unit/Batch tests"]
    D --> E["Test broker thật + Deployer sandbox"]
    E --> F{"Golden run và failure test PASS?"}
    F -->|"Không"| G["Sửa regression; chưa cutover"]
    F -->|"Có"| H["Canary nhỏ trên staging/prod có kiểm soát"]
    H --> I{"Metric, Batch, event, output đạt ngưỡng?"}
    I -->|"Không"| J["Dừng rollout + đối soát"]
    I -->|"Có"| K["Mở rộng theo đợt + theo dõi"]
    J --> L["Rollback/restore theo kế hoạch"]
~~~

### Giai đoạn A — Chuẩn bị

1. Đóng băng source version, config, artifact URI/image digest và danh sách dependency.
2. Chốt test dataset/golden run, bao gồm một ca Batch FAILED và một ca retry cùng business key.
3. Chụp metadata/backup DB; liệt kê JobInstance chưa hoàn tất.
4. Đọc migration guide của **từng bước nhảy** từ version cũ sang mới.
5. Xác nhận khả năng chạy image cũ/new trong cùng cluster, hoặc cần tách môi trường.

### Giai đoạn B — Thử trên staging cô lập

1. Clone database (đã ẩn/giảm thông tin nhạy cảm), áp dụng migration.
2. Chạy JAR mới qua Deployer sandbox, không chỉ bằng `mvn spring-boot:run`.
3. Kiểm tra Task/Batch/Stream/Deployer theo ma trận U01–U20.
4. Kiểm thử broker không sẵn sàng, DB mất kết nối, worker timeout, JVM bị dừng.
5. Lưu SQL, message mẫu, log, artifact digest và kết luận.

### Giai đoạn C — Cutover

1. Dừng tạo launch mới hoặc điều phối chuyển hướng theo kế hoạch, tránh nâng cấp giữa Job đang ghi metadata.
2. Chốt trạng thái Job dang dở, đặc biệt khi đổi major Batch và serialization.
3. Áp dụng DDL bằng migration độc lập có giám sát.
4. Triển khai producer và consumer theo **ma trận tương thích**, không tự thay cả hai và mất khả năng xác định nguyên nhân.
5. Chạy một số yêu cầu canary có business key cô lập; chỉ mở rộng khi đạt gate.

### Giai đoạn D — Theo dõi sau cutover

- Kiểm tra Batch failure có biến thành Task/process non-zero đúng policy.
- Theo dõi số event nhận/start/end và consumer lag theo topic.
- Theo dõi Deployer retry, pod OOM, image pull fail, deadline exceeded.
- Đối chiếu TaskRepository, JobRepository và bảng output cho từng canary.
- Xác minh scheduled occurrences không bị bỏ lỡ và retry không nhân bản kết quả.

## 17. Rollback phải tính cả database, broker và worker

Rollback không chỉ là **đổi tag Docker về version cũ**.

| Thành phần | Rủi ro khi rollback | Cần chuẩn bị |
| --- | --- | --- |
| Database Batch | Metadata/JobParameters đã migrate, ứng dụng cũ không đọc/restart được | Snapshot/restore hoặc kịch bản backward-compatible có kiểm chứng |
| Database Task | DDL/schema/prefix thay đổi, sequence/index hoặc row mới | Migration thuận/nghịch được test, backup và đánh giá mất dữ liệu |
| Producer/consumer Stream | Payload mới đã phát vào topic, consumer cũ không parse được | Versioned destination hoặc consumer hỗ trợ đồng thời v1/v2 |
| Kafka offsets | Consumer mới đã commit offset, đổi về consumer cũ có thể bỏ qua message | Kế hoạch replay/dedup/DLQ với retention phù hợp |
| Deployer | Artifact mới đã được deploy/cached, worker cũ đang chạy | Pin digest/version, quyết định xử lý in-flight Job |
| Business output | Bản mới đã commit dữ liệu hoặc gọi API bên ngoài | Idempotency/đối soát hoặc bù trừ; không xóa tùy tiện |
| Scheduler | Cron/trigger đang tiếp tục sinh launch trong lúc rollback | Tạm dừng/đổi tuyến có kiểm soát, lưu backlog occurrence |

Với thay đổi schema phá vỡ tương thích, nhiều nhóm dùng chiến lược **expand → migrate → contract** để giữ một giai đoạn mà cả hai version có thể hoạt động, nếu framework/schema cho phép. Nhưng không áp dụng máy móc cho `JobRepository` khi migration guide **không hỗ trợ đọc/ghi hai phiên bản đồng thời**. Trường hợp đó phải chấp nhận cutover có cửa sổ dừng, backup/restore và một phương án khôi phục dữ liệu riêng.

Nếu đã có tác động nghiệp vụ mới, phục hồi database từ snapshot có thể **làm mất những kết quả đã commit sau thời điểm snapshot**. Kế hoạch rollback phải nêu cách đối soát/replay/khôi phục chúng, không coi restore là không có rủi ro.

## 18. Những lỗi thường gặp sau nâng cấp

| Triệu chứng | Nguyên nhân khả dĩ | Hành động |
| --- | --- | --- |
| Job chạy nhưng `TASK_TASK_BATCH` rỗng | Module/listener Batch–Task mất hoặc điều kiện bean đổi | Kiểm tra dependency, auto-config, mapping và datasource |
| Batch FAILED nhưng Task `EXIT_CODE=0` | Policy `fail-on-job-failure` không áp dụng/runner bị custom hóa | Test process-level, condition report, ExitCodeGenerator |
| Không restart Job cũ sau nâng cấp lớn | Serialization `JobParameters`/schema thay đổi | Đọc migration guide; xử lý JobInstance cũ trước cutover |
| Task chạy nhưng topic `task-events` trống | Module/binder/listener mất, destination sai, ACL lỗi | Kiểm tra classpath, config, broker và producer log |
| Consumer nhận event nhưng parse fail | Thay đổi JSON field/type/header/contentType | Contract test producer mới ↔ consumer cũ/mới |
| Deployer nhận launch nhưng không có TaskExecution | Image/pod không chạy, bootstrap lỗi, DB sai | Xem receipt, status Job/Pod, log startup |
| Worker partition treo | Worker không launch/không tìm được StepExecution | Deployer logs, JobRepository, timeout/worker config |
| Hai lần chạy ghi trùng output | Retry tạo JobInstance mới, thiếu unique key | Bổ sung business idempotency, kiểm tra conflict |
| Task chậm hơn dù Batch duration không tăng | Pod provisioning/JVM startup/telemetry | So sánh launch-to-finish và từng giai đoạn |
| Event end thiếu sau rollout | JVM shutdown sớm, broker lỗi hoặc publish chưa flush | Đối chiếu runtime, repository, producer ACK và consumer |
| Lúc canary mới pass, production đầy lỗi | Dữ liệu/history lớn hoặc ACL/scale khác staging | Test migrated DB clone, giới hạn và load tương đương |

Đừng chữa lỗi “không ghi TaskExecution” bằng cách tắt Task auto-configuration nếu quy trình vận hành vẫn bắt buộc có metadata. Hãy tìm nguyên nhân version, schema, kết nối và listener.

## 19. Checklist nghiệm thu nâng cấp

- [ ] Ghi chính xác BOM/Boot/Task/Batch/Stream/Binder/Deployer/Java/DB versions và artifact digest.
- [ ] Xác nhận compatibility matrix bằng tài liệu chính thức **đúng release**.
- [ ] Có golden run trước nâng cấp và test dataset/snapshot tái lập.
- [ ] Backup DB và diễn tập migration với metadata lịch sử, sequence và index.
- [ ] Đã xử lý `JobInstance` Batch cũ chưa hoàn tất theo migration guide.
- [ ] Job/Step chạy đúng, `JobParameters` đúng và checkpoint/restart được kiểm chứng.
- [ ] Task–Batch mapping `TASK_TASK_BATCH` hiện diện khi feature được yêu cầu.
- [ ] `BatchStatus.FAILED` phản ánh qua mã thoát Task và process theo policy.
- [ ] Task events start/end và Batch events đến đúng destination, consumer parse đúng.
- [ ] Đã test producer cũ/mới với consumer cũ/mới nếu cần rolling upgrade.
- [ ] Có broker test thật, không chỉ Test Binder.
- [ ] Deployer được thử bằng JAR/image thật: receipt, pod/process, exit code và log.
- [ ] Nếu có remote partitioning, đã kiểm tra worker launch, metadata và timeout.
- [ ] Retry/overlap không tạo dữ liệu nghiệp vụ trùng; có unique key và đối soát.
- [ ] Có test DB/broker down, bootstrap fail, SIGKILL và kết quả commit không rõ.
- [ ] Ngưỡng hiệu năng canary được chốt trước khi chạy và có đủ bằng chứng.
- [ ] Có quy trình dừng rollout, rollback DB/worker/event và phục hồi output hậu snapshot.
- [ ] Đã bảo vệ Secret, payload có PII, log, access token và quyền topic/database.
- [ ] Kết luận `PASS/FAIL/BLOCKED/NOT_APPLICABLE` cho từng test case kèm bằng chứng.

## 20. Bài tập và câu hỏi tự kiểm tra

**Câu hỏi 1.** Vì sao một bài test `JobExecution.STATUS=COMPLETED` chưa đủ chứng minh tích hợp Spring Cloud Task và Deployer đã nâng cấp thành công?

**Câu hỏi 2.** Nếu `TASK_EXECUTION` và `BATCH_JOB_EXECUTION` đều có row mới nhưng `TASK_TASK_BATCH` rỗng, bạn kiểm tra những điều kiện nào?

**Câu hỏi 3.** Khi Batch Job FAILED nhưng Kubernetes Job lại báo process exit code `0`, cần kiểm tra property nào và vì sao phải chạy test process-level?

**Câu hỏi 4.** Vì sao contract test với Test Binder chưa xác minh Kafka topic/ACL/consumer group sau khi nâng cấp binder?

**Câu hỏi 5.** Điểm khác nhau giữa `TaskLaunchRequest.uri`, `deploymentProperties` và `commandLineArguments` là gì? Deployer phải xác minh thêm thông tin nào?

**Câu hỏi 6.** Tại sao không nên tự restart JobInstance thất bại đã tạo trên Batch 5 bằng Batch 6 mà chưa xử lý migration?

**Câu hỏi 7.** Nếu đã nâng cấp database schema và chạy 100 tác vụ mới, rollback chỉ bằng đổi image cũ có an toàn không? Vì sao?

**Bài tập A — Golden run.** Lập manifest baseline/target và thực hiện một lần chạy thành công, một lần Batch failure. Lưu TaskExecution, JobExecution, mapping, output checksum và process exit code cho mỗi version.

**Bài tập B — Contract Stream.** Lấy JSON task-events thực từ bản cũ và bản mới; dựng các phép thử consumer cũ/mới. Khi payload thay đổi không tương thích, đề xuất schema versioning hoặc destination mới.

**Bài tập C — Deployer sandbox.** Khởi chạy cùng một JAR trên local và Kubernetes deployer, so sánh receipt, biến môi trường, resource, exit code và runtime metadata.

**Bài tập D — Remote partition.** Với một Job phân vùng, cho một worker chết giữa lúc xử lý. Kiểm tra manager timeout, Job/StepExecution và số row nghiệp vụ sau retry.

**Bài tập E — Rollback.** Diễn tập migration trong DB cô lập có dữ liệu lịch sử, sau đó lập kế hoạch quay về version cũ mà không làm mất output đã được commit sau thời điểm backup.

**Bài tập F — Regression performance.** Dùng cùng data snapshot đo p95 startup, duration Job và end-to-end; nêu ngưỡng chặn rollout, giải thích ảnh hưởng của cache nóng/lạnh và pod image pull.

## 21. Ghi nhớ

- **Nâng cấp thành công không đồng nghĩa build thành công.** Cần chứng minh hành vi ở cả Batch, Stream, Deployer, TaskRepository và kết quả nghiệp vụ.
- Ma trận version **JDK–Boot–Cloud–Batch–Stream–Deployer** cùng manifest artifact là điều kiện để test có thể tái lập.
- Liên kết `TaskExecution`–`JobExecution` cần được kiểm chứng bằng `TaskBatchExecutionListener`/mapping, không chỉ thấy hai bảng có row.
- Khi nâng cấp Batch major, phải đọc migration guide về `JobParameters`, DDL và khả năng restart **JobInstance cũ**.
- `task-events` là binding output logic; destination/serializer/broker/consumer group đều phải xác minh bằng event thực.
- **Deployer ACK không có nghĩa task hoàn tất**. Cần quan sát process/pod, mã thoát, Task metadata và output.
- Remote partitioning có thêm ranh giới manager–worker–JobRepository, vì thế phải test timeout, retry và worker version.
- Canary, failure injection, idempotency và rollback bao gồm **database lẫn broker** là những bước không thể bỏ qua ở hệ thống cần vận hành an toàn.

## Tài liệu tham khảo

- [Spring Cloud — Compatibility với Spring Boot](https://spring.io/projects/spring-cloud/): bảng ghép release train và Boot generation; cập nhật theo các bản phát hành.
- [Spring Cloud Task — Batch](https://docs.spring.io/spring-cloud-task/reference/batch.html): `TaskBatchExecutionListener` và `spring.cloud.task.batch.fail-on-job-failure`.
- [Spring Cloud Task — Stream Integration](https://docs.spring.io/spring-cloud-task/reference/stream.html): Task start/end events và Batch event bindings.
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/appendix-task-repository-schema.html): bảng `TASK_EXECUTION` và `TASK_TASK_BATCH`.
- [Spring Batch 6 — Migration Guide](https://github.com/spring-projects/spring-batch/wiki/Spring-Batch-6.0-Migration-Guide): thay đổi JobParameters, domain model và giới hạn restart lịch sử v5.
- [Spring Batch — Metadata Schema](https://docs.spring.io/spring-batch/reference/6.0/schema-appendix.html): bảng Job/Step, DDL và migration scripts.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): destination, group, contentType và binder.
- [Spring Cloud Stream — Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html): contract test và giới hạn khi test cùng broker thật.
- [Spring Cloud Task — DeployerPartitionHandler API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/batch/partition/DeployerPartitionHandler.html): worker StepExecution trong remote partitioning.
- [Spring Cloud Task — TaskLaunchRequest API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/launcher/TaskLaunchRequest.html): artifact URI, args, environment, deployment properties.
- [Spring Cloud Data Flow — Reference Guide](https://docs.spring.io/spring-cloud-dataflow/docs/current/reference/htmlsingle/): task application versions, launch lifecycle và upgrade trên platform.

**Phạm vi:** các đoạn mã và SQL là mẫu để học và xây dựng test harness; chưa compile/chạy trong dự án thật. Hãy xác minh dependency, migration scripts, cấu hình binder/Deployer và tương thích API đúng phiên bản trước khi áp dụng. Một vòng Content QA chuyên sâu sẽ đánh giá chi tiết tính phù hợp với cấu trúc dự án sau bước viết tài liệu này.
