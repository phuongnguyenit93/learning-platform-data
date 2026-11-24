# Quản lý thông tin kết nối qua Secret hoặc dịch vụ bí mật

## 1. Vì sao quản lý bí mật đặc biệt quan trọng với Spring Cloud Task?

**Spring Cloud Task** xây dựng các ứng dụng Spring Boot có thời gian chạy hữu hạn: nhận yêu cầu, khởi động, xử lý công việc, ghi trạng thái và kết quả vào cơ sở dữ liệu thông qua `TaskRepository`, sau đó kết thúc. Task có thể được chạy theo lịch hoặc yêu cầu, phối hợp với Spring Batch, kết nối nhiều cơ sở dữ liệu và trao đổi dữ liệu qua broker hoặc API bên ngoài.

Để làm việc, Task thường cần thông tin nhạy cảm:

- Tài khoản và mật khẩu JDBC của `TaskRepository`, `JobRepository` hoặc database nghiệp vụ.
- Chuỗi kết nối chứa token, khóa truy cập Kafka/AMQP, API key hoặc OAuth client secret.
- Khóa riêng, chứng chỉ mTLS, mật khẩu keystore/truststore.
- Credential cho object storage hoặc dịch vụ xuất/nhập dữ liệu.

Nếu đưa những giá trị đó trực tiếp vào code, `application.yml` đóng gói trong JAR, command-line arguments hoặc log, người không được phép có thể lấy được. Một số vị trí còn đặc biệt nguy hiểm đối với Spring Cloud Task: **tham số thực thi có thể được lưu trong `TASK_EXECUTION_PARAMS`**, và lỗi có thể xuất hiện trong `ERROR_MESSAGE`, log hoặc hệ thống điều phối.

Mục tiêu bài học **“Quản lý thông tin kết nối qua Secret hoặc dịch vụ bí mật”** thuộc chương **Bảo mật**:

1. Phân loại secret, cấu hình thông thường và danh tính truy cập.
2. Tránh đưa credential vào Git, image, command line, metadata và log.
3. Cấu hình Spring Boot đọc bí mật từ Kubernetes Secret qua biến môi trường hoặc file mount.
4. Sử dụng dịch vụ bí mật bên ngoài như HashiCorp Vault hoặc dịch vụ quản lý secret của cloud theo danh tính workload.
5. Hiểu vòng đời secret: cấp phát, giới hạn quyền, làm mới/luân chuyển, thu hồi và xử lý sự cố.
6. Thiết kế quyền tối thiểu riêng cho TaskRepository, Spring Batch, migration và service nghiệp vụ.
7. Xây dựng quy trình kiểm tra và vận hành an toàn cho Task ngắn hạn lẫn Job dài.

## 2. Mô hình nguy cơ: bí mật đi qua những ranh giới nào?

```mermaid
flowchart TD
    U["Scheduler / API yêu cầu chạy"] --> L["TaskLauncher / Kubernetes Job"]
    L --> P["Pod hoặc JVM Spring Cloud Task"]
    K["Kubernetes Secret hoặc Secret Manager"] -->|Danh tính và quyền hợp lệ| P
    P --> R["TaskRepository JDBC"]
    P --> B["JobRepository / DB nghiệp vụ"]
    P --> E["Broker, API, object storage"]
    P --> O["Log, trace, metric, TaskExecution"]
    X["Kẻ truy cập trái phép"] -.-> L
    X -.-> O
    X -.-> K
```

Mỗi mũi tên là một **ranh giới tin cậy**. Người có quyền gọi API tạo Task không nhất thiết được quyền đọc mật khẩu database. Người xem log để điều tra sự cố không nhất thiết được quyền đọc Secret trong cluster. Một process đang chạy phải được cấp **đủ quyền để hoàn thành đúng công việc**, không phải quyền quản trị của cả database hoặc secret store.

### 2.1. Phân loại dữ liệu cấu hình

| Giá trị | Có phải secret? | Nơi nên quản lý |
| --- | --- | --- |
| `--business-date=2026-11-23` | Thường không | Tham số nghiệp vụ; có thể lưu metadata |
| `--source=marketplace` | Thường không, nếu không chứa định danh nhạy cảm | Tham số nghiệp vụ |
| `spring.application.name` | Không | ConfigMap/`application.yml` |
| JDBC host/port/schema | Thường không, nhưng có thể là thông tin nội bộ cần giới hạn | Cấu hình môi trường |
| JDBC username | Có thể nhạy cảm về định danh/quyền | Secret hoặc cấu hình được bảo vệ theo chính sách |
| JDBC password | **Có** | Kubernetes Secret/secret manager |
| Bearer token hoặc OAuth client secret | **Có** | Secret manager; ưu tiên cấp ngắn hạn |
| Private key/mật khẩu keystore | **Có** | Secret file hoặc secret manager |
| CA certificate công khai | Thông thường không phải secret | ConfigMap hoặc truststore được quản lý |
| Cloud role/workload identity | Danh tính và chính sách quyền, không phải “mật khẩu” thông thường | IAM/ServiceAccount |

**Không cho rằng mọi URI đều an toàn để công bố.** Ví dụ `jdbc:postgresql://db.example/taskdb` thường không mang password, nhưng `jdbc:postgresql://user:password@host/...` hoặc URL có query token chứa bí mật. Nếu một URL chứa credential, toàn bộ URL phải được xử lý như secret.

### 2.2. Những nơi dễ làm lộ secret

| Kênh | Ví dụ rủi ro | Vì sao nguy hiểm? |
| --- | --- | --- |
| Git | `password: actual-password` trong YAML | Lịch sử commit và bản sao có thể tồn tại lâu dài |
| Image/JAR | Đóng gói `application-prod.yml` chứa mật khẩu | Ai tải image/JAR có thể trích xuất |
| CLI | `--spring.datasource.password=...` | Lộ qua argv, event, hệ điều phối và metadata Task |
| `TaskRepository` | `TASK_EXECUTION_PARAMS` chứa password | Lịch sử chạy thành kho secret ngoài ý muốn |
| Spring Batch | JobParameters hoặc ExecutionContext chứa token | Bí mật có thể được serialize vào `BATCH_*` |
| Log/tracing | In toàn bộ `Environment`, request header | Nhiều người hoặc hệ thống có quyền xem log |
| Actuator | Expose `/actuator/env`, `/actuator/configprops` thiếu kiểm soát | Dù có cơ chế che giá trị, vẫn tạo bề mặt truy cập rủi ro |
| Kubernetes API | Secret base64 hoặc quyền tạo Pod tùy ý | Base64 giải mã được; Pod có thể mount Secret trong namespace |
| Dump/snapshot | Heap dump, core dump, bản backup etcd | Có thể chứa chuỗi secret đang ở bộ nhớ hoặc cấu hình |

Không chỉ **cất giấu giá trị** mà cần bảo vệ cả quá trình **truyền, sử dụng, ghi log, sao lưu, làm mới và thu hồi**.

## 3. Các chiến lược cung cấp bí mật cho một Task

| Phương án | Nguồn bí mật | Cách Task nhận | Điểm mạnh | Cần chú ý |
| --- | --- | --- | --- | --- |
| Kubernetes Secret → `env` | Secret trong namespace | `secretKeyRef` | Đơn giản, phù hợp Task ngắn | Env không tự cập nhật trong process; nguy cơ đọc từ process/debug |
| Kubernetes Secret → volume | Secret trong namespace | File chỉ đọc | Không đưa secret vào argv; dễ dùng với cert/`configtree:` | Cần quyền file; thay đổi mount không tự làm bean refresh |
| Vault/secret manager → Spring Boot | Kho bí mật tập trung | `spring.config.import`/SDK | Audit, phân quyền, secret động/TTL tùy dịch vụ | Xác thực, HA, mạng, startup failure, lease/refresh |
| Secrets Store CSI Driver | Kho secret bên ngoài | Volume file qua CSI provider | Cấp file cho Pod từ secret store | Rotation tùy cấu hình; ứng dụng phải dùng nội dung mới |
| External Secrets controller | Kho secret bên ngoài | Đồng bộ thành Kubernetes Secret | Tận dụng `secretKeyRef`/volume sẵn có | Secret được sao chép vào cluster; xét RBAC, sync delay |
| Cloud workload identity + IAM | IAM, không cần lưu khóa tĩnh | SDK nhận token ngắn hạn tự động | Giảm private key/long-lived secret | Cấu hình audience, role, quyền và luân chuyển đúng |

Không có giải pháp nào loại bỏ trách nhiệm bảo vệ secret **sau khi Task đã đọc**. Secret manager cũng không ngăn được việc ứng dụng tự in credential vào log.

## 4. Thiết kế cấu hình Spring Boot: giữ bí mật ngoài repository code

### 4.1. Chỉ lưu placeholder trong application.yml

Ví dụ một Task dùng PostgreSQL:

```yaml
spring:
  application:
    name: orders-import-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      initialize-enabled: false
      closecontextEnabled: true
  batch:
    jdbc:
      initialize-schema: never
```

Trong đó:

- File trong Git **không chứa mật khẩu thật**.
- `TASK_DB_URL`, `TASK_DB_USER`, `TASK_DB_PASSWORD` được cấp ở môi trường khởi chạy.
- `spring.cloud.task.initialize-enabled=false` giả định schema `TASK_*` đã được tạo bằng migration.
- `spring.batch.jdbc.initialize-schema=never` chỉ cần nếu ứng dụng dùng Batch và schema `BATCH_*` cũng được quản lý bằng migration.

**Không đặt giá trị mặc định thật cho password**, chẳng hạn `${TASK_DB_PASSWORD:productionPassword}`. Nếu thiếu secret bắt buộc, Task nên **fail sớm** và ghi một thông báo **không chứa giá trị secret**, thay vì âm thầm kết nối bằng tài khoản chung.

### 4.2. Cách Spring Boot đọc environment

Spring Boot có cơ chế externalized configuration, cho phép bind environment variable vào property. Dạng biến trực tiếp thường gặp:

```text
SPRING_DATASOURCE_URL
SPRING_DATASOURCE_USERNAME
SPRING_DATASOURCE_PASSWORD
```

Hoặc dùng placeholder riêng như `TASK_DB_PASSWORD` trong YAML để tách hợp đồng deploy khỏi tên thuộc tính framework. Các nguồn property có **thứ tự ưu tiên**; một đối số CLI `--spring.datasource.password=...` có thể ghi đè giá trị lấy từ nguồn an toàn. Vì vậy phải kiểm soát các tham số mà launcher/API cho phép truyền.

### 4.3. Không đưa secret vào ApplicationArguments

**Sai:**

```bash
java -jar orders-import.jar \
  --business-date=2026-11-23 \
  --spring.datasource.password=<real-password>
```

**Đúng về nguyên tắc:**

```bash
java -jar orders-import.jar \
  --business-date=2026-11-23 \
  --source=marketplace
```

Mật khẩu được cấp qua môi trường/volume/secret manager, **không có trong argv**. Spring Cloud Task có bảng `TASK_EXECUTION_PARAMS` lưu các tham số thực thi. `ApplicationArguments`, shell history, lệnh `ps`, Pod spec hoặc các hệ thống launch cũng có thể phơi bày argv tùy quyền truy cập.

Nếu hệ thống đang lưu secret trong tham số cũ, không chỉ sửa code mới: phải xem xét **dữ liệu metadata đã lưu**, log, bản backup và các kênh cấp credential để có kế hoạch thu hồi.

## 5. Phương án A — Kubernetes Secret dưới dạng environment variable

### 5.1. Tạo Secret an toàn

Kubernetes Secret loại `Opaque` chứa các key-value như password, token và thông tin kết nối. Trường `data` trong manifest biểu diễn dữ liệu bằng Base64; **Base64 không phải mã hóa bảo mật**. Dữ liệu Secret có thể được lưu không mã hóa trong `etcd` nếu cluster chưa bật encryption at rest.

Trong tài liệu, **không đưa mật khẩu thật** vào manifest hay ví dụ lệnh có tham số giá trị. Khi thử nghiệm, bạn có thể chuẩn bị một file secret tại máy quản trị an toàn và dùng `--from-file`:

```bash
# File dưới đây phải được tạo bởi quy trình quản lý bí mật an toàn,
# không commit lên Git hoặc in nội dung ra terminal.
kubectl -n batch-jobs create secret generic orders-task-db \
  --from-file=password=/secure/path/orders-db-password.txt
```

Đây là thao tác **minh họa**, không chạy tự động trong bài học. File đầu vào cần được hạn chế quyền, xóa an toàn theo chính sách tổ chức, và không để command history hoặc log hệ thống ghi nội dung bí mật. Nếu tổ chức đã có GitOps, dùng công cụ quản lý secrets phù hợp như secret manager + controller, hoặc encrypted secret manifest do nền tảng hỗ trợ, thay vì commit Secret plaintext/Base64.

### 5.2. Job sử dụng secretKeyRef

Giả sử Secret `orders-task-db` tồn tại trong namespace `batch-jobs`, chứa key `password`. Ví dụ:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: orders-import-example
  namespace: batch-jobs
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 1800
  template:
    spec:
      restartPolicy: Never
      serviceAccountName: orders-task-runner
      containers:
        - name: orders-import
          image: registry.example.com/tasks/orders-import:1.4.2
          args:
            - "--business-date=2026-11-23"
            - "--source=marketplace"
          env:
            - name: TASK_DB_URL
              value: "jdbc:postgresql://postgres.internal:5432/taskdb"
            - name: TASK_DB_USER
              value: "task_runtime"
            - name: TASK_DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: orders-task-db
                  key: password
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              memory: "768Mi"
```

Điều kiện:

1. Namespace `batch-jobs`, Secret `orders-task-db` và ServiceAccount `orders-task-runner` đã được tạo.
2. Image có entrypoint chạy Spring Boot Task và chuyển tiếp `args` đúng cách.
3. Pod có đường mạng đến PostgreSQL; database và bảng `TASK_*` được chuẩn bị trước.
4. Mật khẩu của tài khoản `task_runtime` có quyền vừa đủ trên repository và không có quyền DDL không cần thiết.
5. Không có debug/log tự in toàn bộ `env`.

`env[].valueFrom.secretKeyRef` **chỉ tham chiếu** tên Secret và key; manifest Pod không cần chứa mật khẩu. Tuy nhiên, quyền truy cập Pod hoặc quyền tạo Pod trong cùng namespace có thể gián tiếp mở đường đọc Secret. Cần chính sách RBAC và admission control phù hợp, không chỉ che giá trị khỏi file YAML.

### 5.3. Secret thiếu thì chuyện gì xảy ra?

Nếu Secret hoặc key được tham chiếu **bắt buộc** không tồn tại, Kubernetes thường không cho container bắt đầu và tạo sự kiện liên quan. Khi đó **Task có thể chưa có bản ghi `TaskExecution`**, vì JVM chưa chạy.

Đừng kết luận “Task không được gọi” chỉ vì bảng `TASK_EXECUTION` trống. Hãy kiểm tra:

```bash
kubectl -n batch-jobs get job orders-import-example
kubectl -n batch-jobs get pods
kubectl -n batch-jobs describe job orders-import-example
kubectl -n batch-jobs describe pod <pod-name>
```

Thay `<pod-name>` bằng tên Pod thực tế. Không dùng `kubectl get secret ... -o yaml` hoặc `-o json` để debug một cách tùy tiện: có thể lộ dữ liệu `data` dưới dạng Base64 dễ giải mã. Để xác nhận Secret tồn tại, có thể dùng quyền metadata phù hợp và kiểm tra event/Pod status mà không in giá trị.

### 5.4. Giới hạn của env khi secret thay đổi

Kubernetes **không tự cập nhật biến môi trường** của một container đang chạy khi Secret được sửa. Secret mới thường được sử dụng khi **Pod được tạo lại** hoặc process được khởi động mới. Với Task hữu hạn chạy vài phút, dùng env có thể phù hợp nếu credential còn hiệu lực trong toàn bộ thời gian chạy.

Với Batch Job nhiều giờ:

- Secret bị thu hồi lúc Job còn chạy có thể làm JDBC reconnect thất bại.
- Nếu Task giữ connection pool với credential cũ, kết nối cũ và kết nối mới có thể có hành vi khác nhau khi credential được rotate.
- Không giả định sửa Secret ở API server sẽ làm `HikariDataSource` tự đổi password.

Cần kế hoạch rotation/credential overlap, drain và restart Task theo ranh giới nghiệp vụ.

## 6. Phương án B — Mount Secret thành file

### 6.1. Khi nào nên dùng file?

Mount Secret thành file phù hợp với:

- Private key, client certificate, truststore/keystore và cấu hình TLS.
- Secret manager/CSI driver cấp file vào Pod.
- Ứng dụng muốn tránh copy password vào biến môi trường.
- Cơ chế Spring Boot `configtree:` để bind file theo tên key.

File mount không làm secret “vô hình”: mọi process/container có quyền đọc đường dẫn đó vẫn có thể lấy giá trị. Phải bảo vệ bằng namespace, Pod security context, quyền POSIX và việc chỉ mount vào **container thật sự cần**.

### 6.2. Dùng Spring Boot configtree

Giả sử muốn Spring Boot bind thẳng vào `spring.datasource.username` và `spring.datasource.password`. Trong Kubernetes Secret, tạo hai key **với đúng tên property**:

```text
orders-task-db-properties
  spring.datasource.username
  spring.datasource.password
```

Ở Pod, mount các key thành hai file tại:

```text
/run/secrets/task-db/
  spring.datasource.username
  spring.datasource.password
```

Trong `application.yml`:

```yaml
spring:
  application:
    name: orders-import-task
  config:
    import: "configtree:/run/secrets/task-db/"
  datasource:
    url: ${TASK_DB_URL}
  cloud:
    task:
      initialize-enabled: false
```

Với `configtree:`, **tên file** trở thành property name và **nội dung file** là property value. Đây là tính năng Spring Boot Config Data, không phải cơ chế đọc file độc quyền của Spring Cloud Task.

**Vì sao không dùng `optional:configtree:` cho secret bắt buộc?** Dạng `optional:` cho phép tiếp tục khi vị trí không tồn tại. Nếu password bắt buộc, nên để startup thất bại rõ ràng khi thiếu mount, thay vì âm thầm lấy cấu hình từ nơi khác không mong muốn. Vẫn cần validate property ở tầng ứng dụng.

### 6.3. Manifest Job dùng volume Secret

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: orders-import-from-files
  namespace: batch-jobs
spec:
  backoffLimit: 0
  template:
    spec:
      serviceAccountName: orders-task-runner
      restartPolicy: Never
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        fsGroup: 2000
      containers:
        - name: orders-import
          image: registry.example.com/tasks/orders-import:1.4.2
          args:
            - "--business-date=2026-11-23"
          env:
            - name: TASK_DB_URL
              value: "jdbc:postgresql://postgres.internal:5432/taskdb"
          volumeMounts:
            - name: task-db-credentials
              mountPath: /run/secrets/task-db
              readOnly: true
          resources:
            requests:
              memory: 256Mi
            limits:
              memory: 768Mi
      volumes:
        - name: task-db-credentials
          secret:
            secretName: orders-task-db-properties
            defaultMode: 0440
            items:
              - key: spring.datasource.username
                path: spring.datasource.username
              - key: spring.datasource.password
                path: spring.datasource.password
```

Mẫu trên giả định cơ chế cấp quyền volume của cluster cho phép user/group được chỉ định đọc file. `defaultMode: 0440` là cách biểu diễn **octal trong YAML Kubernetes** (khi dùng JSON cần dùng số thập phân tương ứng). Cần kiểm tra quyền file hiệu lực trong môi trường container và chính sách `fsGroup`.

Lưu ý:

- Secret và Pod phải thuộc **cùng namespace**.
- Không mount file chứa secret vào sidecar không cần thiết.
- Không cho Task ghi secret ngược ra file log hoặc thư mục output.
- Không dùng mount với `subPath` nếu kỳ vọng Kubernetes cập nhật nội dung file sau khi Secret đổi.
- Khi rotation, nội dung mount có thể đổi theo cơ chế cập nhật **eventually consistent**, nhưng bean `DataSource` đã khởi tạo **không tự refresh** chỉ vì file đổi.

### 6.4. Nếu key Secret không trùng tên property

Bạn có thể đặt file là `username` và `password`, sau đó dùng:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/task-db/"
  datasource:
    username: ${username}
    password: ${password}
```

Nhưng tên `username` và `password` quá chung có thể **xung đột** với nguồn property khác. Trong ứng dụng dùng nhiều database, nên đặt key có namespace như `task.db.username`/`task.db.password` hoặc mount ở đường dẫn được thiết kế để tạo tên đầy đủ.

Với nhiều configtree, phải kiểm tra thứ tự ưu tiên của các location và tránh một secret của hệ thống A ghi đè thuộc tính hệ thống B.

## 7. Phương án C — Lấy bí mật từ dịch vụ bên ngoài

### 7.1. Secret manager bổ sung gì?

Dịch vụ quản lý secret như **HashiCorp Vault**, AWS Secrets Manager, Azure Key Vault hay Google Secret Manager có thể hỗ trợ:

- Chính sách truy cập chi tiết theo identity và đường dẫn secret.
- Lịch sử thay đổi, audit, version và quy trình rotation.
- Kết nối được mã hóa và xác thực máy chủ.
- Cấp credential ngắn hạn/động trong những hệ thống hỗ trợ.
- Phân chia quyền giữa môi trường development, staging và production.

Không phải mọi dịch vụ cung cấp **cùng cơ chế lease, renewal hay dynamic database credentials**. Cần đối chiếu dịch vụ đang dùng và cách SDK/framework tích hợp, tránh giả định tất cả secret đều tự cập nhật trong JVM.

### 7.2. Luồng khởi động Task với Vault

```mermaid
sequenceDiagram
    participant K as Kubernetes Job / Pod
    participant T as Spring Cloud Task
    participant V as Vault
    participant D as PostgreSQL
    K->>T: Khởi động container với ServiceAccount
    T->>V: Xác thực Kubernetes identity
    V-->>T: Token/lease theo policy
    T->>V: Đọc cấu hình hoặc DB credentials
    V-->>T: Secret qua kết nối TLS
    T->>D: Mở kết nối JDBC
    D-->>T: Kết nối được chấp nhận
    T->>T: Chạy Runner, ghi TaskExecution
    T->>T: Đóng context và kết thúc
```

Mục tiêu là không cần đặt **Vault root token** hoặc static application secret vào image. Workload dùng **Kubernetes ServiceAccount identity** để Vault xác thực và trả về đúng secret được policy cho phép.

### 7.3. Cấu hình Spring Cloud Vault với Kubernetes authentication

Ví dụ mang tính hướng dẫn, dùng `Spring Cloud Vault` và `Config Data API`:

```yaml
spring:
  application:
    name: orders-import-task
  config:
    import: "vault://"
  cloud:
    vault:
      uri: https://vault.internal.example:8200
      authentication: KUBERNETES
      kubernetes:
        role: orders-task-reader
        kubernetes-path: kubernetes
        service-account-token-file: /var/run/secrets/kubernetes.io/serviceaccount/token
      kv:
        enabled: true
    task:
      initialize-enabled: false
  datasource:
    url: ${TASK_DB_URL}
```

Về dependency, cần starter Spring Cloud Vault tương thích BOM Spring Boot/Spring Cloud của dự án, ví dụ `org.springframework.cloud:spring-cloud-starter-vault-config` theo dòng phát hành hỗ trợ. **Không tự đặt phiên bản** ngoài ma trận tương thích.

Các điều kiện bắt buộc:

1. Vault đã được triển khai, cấu hình TLS/certificate và có Kubernetes auth mount theo `kubernetes-path`.
2. Vault role `orders-task-reader` được **ràng buộc** với ServiceAccount và namespace hợp lệ.
3. Policy Vault chỉ cấp quyền đọc đường dẫn secret của Task này, không cấp quyền quản trị Vault.
4. Pod thực sự có ServiceAccount token ở đường dẫn ứng dụng sử dụng (không cấu hình tắt projection khi vẫn cần xác thực).
5. Vault path/version và keys được định nghĩa để tạo đúng Spring properties cần thiết, ví dụ `spring.datasource.username` và `spring.datasource.password`.
6. Hạ tầng cho phép kết nối HTTPS từ Pod tới Vault và xác minh chứng chỉ server.

`vault://` ở đây nhập các secret backend được bật theo cơ chế Config Data của Spring Cloud Vault; cách chọn **KV context path**, profile hoặc mount path phải kiểm tra theo version, không tự suy rằng mọi Vault KV có tên `orders-import-task` sẽ được đọc mà không cần cấu hình.

**Không làm ví dụ production bằng `spring.cloud.vault.token=<root-token>`.** Static root token cấp quyền rất lớn và có nguy cơ lộ qua YAML, môi trường, log hoặc snapshot. Nếu học thử với Vault dev server, cần phân biệt rõ mô hình demo với production.

### 7.4. KV secret và dynamic database credential

Hai mô hình thường gặp:

| Mô hình | Bí mật được trả về | Vòng đời |
| --- | --- | --- |
| KV versioned | Username/password hoặc API key được quản trị | Rotate theo quy trình bên ngoài; application có thể cần restart |
| Dynamic database credentials | Username/password được cấp theo role và lease | Có TTL, có thể phải renew hoặc cấp lại; DB user có thể bị thu hồi khi lease kết thúc |

Khi dùng dynamic credentials, phải xem thời gian chạy **tối đa** của Task, khoảng gia hạn, network và hành vi `DataSource` khi connection được lấy lại. Không mặc định Vault tự thay password của các kết nối JDBC đang có hoặc service vẫn sử dụng credential được thu hồi.

Với Task chạy rất ngắn, credential được cấp khi startup và có TTL **dài hơn thời gian chạy dự kiến** (kèm biên an toàn) là một chiến lược đơn giản, nhưng vẫn cần deadline và xử lý Task treo. Với Batch Job kéo dài nhiều giờ, cần cơ chế renew/refresh được **kiểm chứng end-to-end** hoặc chia công việc thành các phần ngắn hơn để giảm rủi ro.

### 7.5. Tích hợp trực tiếp SDK của cloud

Nếu dùng AWS/Azure/GCP, ứng dụng có thể lấy secret qua SDK:

```text
Spring Cloud Task
    |
    +-- Workload identity / IAM role
    |
    +-- Cloud Secret Manager SDK
            |
            +-- Lấy secret theo resource name / version
            +-- Cache trong thời gian cần thiết
            +-- Ghi audit ở phía dịch vụ
```

Tên API và cách cấu hình khác theo provider, nên không có đoạn Java chung có thể chạy trên cả ba cloud. Quy tắc nền tảng là **ưu tiên danh tính workload ngắn hạn**, tránh phân phát access key tĩnh, dùng TLS, cấp quyền chỉ đọc đúng secret và thiết kế cơ chế fail-safe khi secret store không phản hồi.

## 8. Secrets Store CSI Driver và External Secrets: hai đường tích hợp khác nhau

### 8.1. Secrets Store CSI Driver

**Secrets Store CSI Driver** cho phép Pod mount secret từ secret manager bên ngoài qua CSI provider. Thông thường:

1. Admin cài CSI Driver và provider thích hợp.
2. Tạo `SecretProviderClass` mô tả đối tượng secret được lấy, theo cấu hình của provider đó.
3. Pod gắn CSI volume và mount file secret.
4. Spring Boot có thể đọc file hoặc dùng `configtree:`.

Ví dụ **mẫu volume** (không phải manifest độc lập chạy được nếu thiếu provider):

```yaml
volumeMounts:
  - name: secret-store
    mountPath: /mnt/secrets-store
    readOnly: true
volumes:
  - name: secret-store
    csi:
      driver: secrets-store.csi.k8s.io
      readOnly: true
      volumeAttributes:
        secretProviderClass: orders-import-secrets
```

`SecretProviderClass` phải tồn tại **trong namespace của Pod** và phù hợp cấu hình provider. CSI Driver có tùy chọn **auto rotation**; không mặc định tính năng đã bật hoặc có độ trễ cố định. Dù file mount được cập nhật, Spring Boot bean/connection pool vẫn cần cơ chế đọc lại và thay connection nếu muốn dùng secret mới trong process đang chạy.

### 8.2. External Secrets controller

Một controller như **External Secrets Operator** có thể đồng bộ secret từ kho bên ngoài thành **Kubernetes Secret**. Khi đó Pod dùng `secretKeyRef` hoặc volume như phần 5–6. Điểm khác:

- Bí mật được **sao chép vào Kubernetes Secret**; phải tiếp tục bảo vệ RBAC và mã hóa `etcd`.
- Việc đồng bộ có chu kỳ, có thể có độ trễ hoặc lỗi khi provider mất kết nối.
- Pod sử dụng `env` không tự đổi giá trị sau khi Kubernetes Secret được cập nhật.
- Quyền của controller đi đọc secret store nên được giới hạn; không cấp quyền toàn tổ chức cho mọi namespace.

Không gọi CSI Driver và External Secrets là một cơ chế giống hệt nhau: một bên chủ yếu **mount file từ provider**, bên kia **đồng bộ Kubernetes Secret**; triển khai thực tế có thể kết hợp nhưng kéo theo nhiều điểm cần audit.

## 9. Danh tính workload và nguyên tắc quyền tối thiểu

### 9.1. Tách quyền theo vai trò

Một hệ thống Spring Cloud Task có ít nhất bốn vai trò khác nhau:

| Vai trò | Cần quyền gì? | Không nên có |
| --- | --- | --- |
| **Launcher/orchestrator** | Được tạo Job/Pod từ allowlist artifact và namespace cho phép | Toàn quyền đọc mọi Secret/cluster-admin |
| **Task runtime** | Đọc đúng secret được cấp; DML/sequence cần thiết trên `TASK_*` và bảng nghiệp vụ | Tạo/xóa bảng, đọc secret của ứng dụng khác |
| **Migration job** | Quyền DDL theo migration đã review | Mật khẩu/secret của các môi trường không liên quan |
| **Operator/auditor** | Xem Job status, logs đã lọc, metadata/metric cần thiết | Truy cập plaintext secrets nếu không có nhiệm vụ |

Khi tích hợp Spring Batch, `JobRepository` có bảng `BATCH_*` riêng. Runtime user cần quyền đọc/ghi các bảng/sequence phù hợp; không dùng tài khoản DBA cho mỗi worker. Nếu TaskRepository và JobRepository nằm ở database khác nhau, dùng credential **riêng** và mô tả rõ `DataSource` nào được phép truy cập đâu.

### 9.2. ServiceAccount của Pod không tự cần quyền get Secret

Nếu Pod chỉ khai báo `secretKeyRef` hoặc Secret volume, kubelet thực hiện quá trình cung cấp dữ liệu cho container. **Không cấp bừa RBAC `get/list/watch secrets` cho ServiceAccount runtime** chỉ vì Pod cần một Secret làm môi trường.

Tuy vậy, người có quyền **tạo Pod** trong namespace có thể thiết kế Pod mount những Secret của namespace đó trong nhiều cấu hình. Do đó, quyền tạo Pod/Job, quyền sửa ServiceAccount, admission policy và cách phân chia namespace đều là một phần của mô hình bảo mật.

### 9.3. Dùng service account riêng theo Task

Ví dụ:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-task-runner
  namespace: batch-jobs
```

Đây chỉ là **định danh Pod**, không tự cấp quyền truy cập Vault hoặc cloud secret store. Tùy hạ tầng, cần cấu hình Vault role, cloud workload identity, IAM binding hoặc projected token audience phù hợp. Không dùng default ServiceAccount có quá nhiều quyền cho mọi Job.

Khi workload **không cần** gọi Kubernetes API hoặc Vault Kubernetes auth, có thể cân nhắc tắt tự động mount ServiceAccount token bằng cấu hình tương ứng. Nếu **cần** token để xác thực Vault thì không được tắt một cách máy móc; thay vào đó giới hạn quyền và audience/token theo thiết kế.

## 10. Bí mật trong JDBC: bảo mật kết nối không chỉ là password

### 10.1. Bốn lớp bảo vệ

Một Task kết nối PostgreSQL nên xem xét:

1. **Xác thực:** username/password hoặc cơ chế IAM/cert phù hợp.
2. **Phân quyền SQL:** tài khoản runtime có đúng quyền DML/sequence, không dùng superuser.
3. **Mã hóa trên đường truyền:** TLS, xác minh hostname và chứng chỉ server.
4. **Quản lý vòng đời:** đổi credentials, thu hồi, giám sát lỗi, đóng pool khi Task kết thúc.

Mật khẩu lấy từ Secret vẫn có thể bị lộ trên đường truyền nếu kết nối không bảo vệ đúng. Cấu hình driver cần theo hệ quản trị; với PostgreSQL JDBC, một ví dụ có chế độ xác minh:

```text
jdbc:postgresql://postgres.internal:5432/taskdb?sslmode=verify-full
```

Cần cung cấp CA/truststore và tên DNS khớp chứng chỉ. Đây là **ví dụ hướng thiết kế**, không bảo đảm mọi database đã phát hành cert đúng để URL tự chạy được. Không dùng `sslmode=disable` hoặc bỏ xác minh certificate chỉ để vượt lỗi TLS production.

### 10.2. Database credential theo môi trường

| Môi trường | Cách cấp quyền | Hướng quản lý |
| --- | --- | --- |
| Local dev | Credential sandbox không có dữ liệu thật | Env/file ngoài Git; không dùng mật khẩu production |
| CI | Credential thử nghiệm cấp theo job/pipeline | CI secret store, job isolation; dọn tài nguyên sau test |
| Staging | Role riêng, database hoặc schema riêng | Secret riêng, policy độc lập |
| Production | Role runtime quyền tối thiểu | Secret manager/Kubernetes Secret, rotation, audit và alert |

Đừng cho staging dùng chung secret production vì tiện cấu hình. Nếu một pipeline CI bị lộ, blast radius phải giới hạn ở môi trường kiểm thử.

### 10.3. Một DataSource khác cho migration

Trong production, Flyway/Liquibase nên dùng account **migration** riêng, chạy như bước phát hành. Các instance Spring Cloud Task runtime chỉ cần quyền để sử dụng `TaskRepository`:

```yaml
spring:
  cloud:
    task:
      initialize-enabled: false
  sql:
    init:
      mode: never
  flyway:
    enabled: false
```

Đoạn trên giả định **migration đã chạy riêng**. Nếu dùng Liquibase thay Flyway, tắt Liquibase trong runtime tương ứng. Không cho mỗi Task ngắn hạn tự chạy DDL với một tài khoản có quyền quản trị khi có thể tách deployment pipeline.

## 11. Tránh rò rỉ qua log, exception, TaskRepository và Batch

### 11.1. TaskRepository lưu điều gì?

Trong schema JDBC thông dụng, bảng `TASK_EXECUTION_PARAMS` ghi lại tham số của Task, còn `TASK_EXECUTION` lưu mã kết thúc/thông tin lỗi. Điều đó có ích cho kiểm toán nhưng **không phải secret store**.

Không truyền những tham số như:

```text
--db-password=<secret-value>
--api-token=<secret-value>
--client-secret=<secret-value>
--jdbc-url=jdbc:postgresql://user:password@host/db
```

Mọi `<secret-value>` trong ví dụ là **placeholder**, không phải giá trị thật. Nếu một thư viện có cơ chế lọc tham số, vẫn nên **loại secret khỏi argv ngay từ thiết kế** thay vì phụ thuộc hoàn toàn vào bộ lọc.

### 11.2. Batch JobParameters và ExecutionContext cũng có thể chứa bí mật

Khi Task gọi Spring Batch, `JobRepository` lưu `JobParameters` và `ExecutionContext` để phục vụ restart. Đừng đưa password, token hoặc private key vào:

```text
JobParameters:
    businessDate=2026-11-23   (thường phù hợp)
    source=marketplace        (thường phù hợp)
    apiToken=<secret-value>   (không phù hợp)
```

Một Job khi restart có thể deserialize context từ database; nếu context chứa credential hết hạn hoặc giá trị bí mật, vừa tạo rủi ro rò rỉ vừa khiến lần restart dùng secret cũ. Nên lưu **định danh resource/secret path không nhạy cảm** hoặc metadata nghiệp vụ, rồi lấy lại credential qua cơ chế an toàn ở mỗi lần khởi chạy.

### 11.3. Đừng in Spring Environment hoặc JDBC URL đầy đủ

**Không nên:**

```java
// Không dùng trong ứng dụng thật:
System.out.println(System.getenv());
System.out.println(dataSource.getConnection().getMetaData().getURL());
```

Ngay cả khi JDBC URL hiện không có password, log URL vẫn có thể phơi hostname nội bộ hoặc query parameters nhạy cảm trong cấu hình khác. Không ghi token/header vào trace span attributes hoặc metric tags.

**Nên:** log tên hệ thống đích, trạng thái kết nối, mã lỗi đã phân loại và correlation ID mà **không ghi credential**. Nếu cần kiểm tra secret hiện diện, chỉ log **có/không** ở mức đã cho phép; tránh in giá trị, độ dài, hash hoặc token prefix bởi chúng vẫn có thể tiết lộ thông tin.

### 11.4. Kiểm tra secret có mặt nhưng không log nội dung

Ví dụ Spring Boot:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
class SecretStartupValidation {
    @Bean
    ApplicationRunner validateDatabaseSecret(Environment env) {
        return args -> {
            String password = env.getProperty(
                    "spring.datasource.password");
            if (password == null || password.isBlank()) {
                throw new IllegalStateException(
                        "Thiếu cấu hình xác thực database bắt buộc");
            }
            // Không log password; Spring Boot sử dụng nó
            // thông qua cấu hình DataSource đã thiết lập.
        };
    }
}
```

Ví dụ minh họa **kiểm tra presence**, không phải đầy đủ quy trình kiểm thử credential. Thực tế, `DataSource` có thể khởi tạo hoặc kết nối trước khi Runner này chạy; việc fail sớm hơn nên được hiện thực bằng cấu hình bắt buộc và validation tại thời điểm bind nếu kiến trúc yêu cầu.

### 11.5. Giữ lỗi đủ hữu ích nhưng không lộ bí mật

Đừng tạo exception chứa credential:

```java
// Sai: giá trị secret có thể đi vào ERROR_MESSAGE/log.
throw new IllegalArgumentException(
        "Login failed with password=" + password);
```

Hãy phát lỗi không tiết lộ credential, bảo toàn loại lỗi/stack trace cần thiết và giới hạn ai được xem log. Cần xem driver/client bên thứ ba có tự ghi URL chứa user/password hay không; nếu có, cấu hình log redaction và driver properties phù hợp.

## 12. Vòng đời rotation: Task ngắn khác ứng dụng chạy mãi

### 12.1. Mô hình cấp phát lúc bắt đầu

Với Task chạy 1–3 phút, cách đơn giản là:

1. Scheduler tạo Job.
2. Pod đọc Secret hoặc xác thực tới secret manager.
3. Ứng dụng thiết lập `DataSource`.
4. Runner hoàn thành trước khi secret hết hạn.
5. JVM đóng kết nối và kết thúc; credential mới được cấp cho lần Task kế tiếp.

Đây là mô hình phù hợp khi **TTL được thiết kế dài hơn thời lượng Task** và có kế hoạch xử lý nếu Task bị chậm. Không dùng credential có TTL 60 giây cho Job có thể chạy 20 phút rồi hy vọng DB session tự gia hạn.

### 12.2. Luân chuyển credential an toàn

Một quy trình tham khảo:

```mermaid
flowchart TD
    A["Phát hành credential mới"] --> B["Cập nhật Secret/secret manager"]
    B --> C["Kiểm tra Pod/Task mới đăng nhập được"]
    C --> D["Theo dõi và drain Task đang dùng credential cũ"]
    D --> E["Thu hồi credential cũ theo thời hạn an toàn"]
    E --> F["Kiểm tra lỗi auth, audit và log"]
```

Các hệ thống hỗ trợ **hai credential đồng thời** có thể thực hiện giai đoạn chồng lấn để tránh gián đoạn. Nếu DB chỉ cho một password và cập nhật sẽ vô hiệu hóa ngay password cũ, phải chuẩn bị downtime/rolling restart hoặc phương án cấp tài khoản thay thế theo chính sách DB.

Không đợi đến khi hàng trăm Pod `Authentication failed` mới phát hiện secret đã đổi. Cần metric và cảnh báo về **secret expiry/lease TTL** theo nguồn hợp lệ, nhưng không đưa giá trị secret vào metric label.

### 12.3. Env và file mount khác nhau về cập nhật

| Cơ chế | Khi secret ở nguồn thay đổi | Ứng dụng sẽ dùng secret mới khi nào? |
| --- | --- | --- |
| Secret → env | Env của process hiện có không thay đổi | Khi tạo process/Pod mới |
| Secret → volume | File thường được cập nhật sau một khoảng trễ; không áp dụng auto-update khi mount bằng `subPath` | Chỉ khi code/binding **đọc lại** hoặc process mới chạy |
| CSI Driver | Có thể cập nhật mount nếu rotation feature/config được bật | Khi ứng dụng thực sự lấy lại nội dung file |
| Vault KV qua Config Data | Properties thường được load trong bootstrap/startup | Khi có refresh/restart được thiết kế; không mặc định tự đổi bean |
| Vault dynamic credential | Có lease và khả năng renewal tùy integration | Theo cách credential/connection được gia hạn/cấp lại, phải test |

Một Secret được cập nhật trong Kubernetes API **không trực tiếp biến thành một mật khẩu mới trong connection pool**. Xác minh cả ba tầng: nguồn secret → dữ liệu Pod nhìn thấy → connection mới của ứng dụng.

### 12.4. Thu hồi khẩn cấp

Nếu nghi credential bị lộ:

1. **Cô lập phạm vi:** xác định secret nào, database/API nào, môi trường và Task nào bị ảnh hưởng.
2. **Thu hồi/đổi credential** theo khả năng dịch vụ, ưu tiên chặn truy cập trái phép.
3. **Phát hành credential mới** qua secret manager/Kubernetes Secret và khởi chạy lại những Task cần thiết có kiểm soát.
4. **Kiểm tra Job còn sống**, connection pool và các lần retry đang dùng secret cũ.
5. **Rà soát dấu vết:** Git history, CI logs, Pod specs, `TASK_EXECUTION_PARAMS`, `BATCH_*`, log, traces, backup.
6. **Xác minh dữ liệu nghiệp vụ**, tránh để Job retry làm ghi trùng sau khi credential bị thu hồi giữa chừng.
7. **Lưu incident audit** và siết quyền/ngăn nguồn rò rỉ ban đầu.

Chỉ xóa mật khẩu khỏi commit mới **không làm nó biến mất khỏi lịch sử Git hoặc bản sao đã bị đọc**. Cần coi secret từng lộ là đã bị xâm phạm và xoay vòng/thu hồi theo quy trình sự cố.

## 13. Cấu hình lỗi: có nên cho Task chạy khi secret manager không sẵn sàng?

Đối với credential **bắt buộc**, câu trả lời mặc định nên là **không**: thiếu secret nghĩa là Task không thể hoàn thành an toàn. Không nên tự fallback sang password dùng chung hoặc credential nằm trong JAR.

| Sự cố | Hành vi nên có | Điều cần quan sát |
| --- | --- | --- |
| Secret thiếu key | Startup fail, không xử lý dữ liệu | Kubernetes event/Bean bind error |
| Sai RBAC/role Vault | Fail xác thực với thông điệp không lộ token | Vault audit, role binding |
| Vault tạm mất kết nối | Retry có giới hạn ở mức thích hợp hoặc fail sớm | Timeout, request ID, alert |
| Certificate Vault không hợp lệ | Fail TLS verification | Chain/hostname/CA, không tắt SSL verify |
| DB từ chối credential | Fail và điều tra rotation/quyền | SQLState/log đã lọc, DB audit |
| Secret hết hạn giữa Job | Dừng/rollback phần giao dịch phù hợp, khôi phục theo checkpoint | Lease TTL, pool reconnect |
| Secret rotate nhưng Pod vẫn dùng env cũ | Chủ động tạo Pod mới/drain | Tuổi Pod, version Secret, lỗi auth |

Với secret manager, một số framework cho phép `optional:` import hoặc tắt fail-fast. **Không bật optional cho secret bắt buộc** chỉ để ứng dụng “chạy được”. Nếu không thể lấy credential, Task phải báo thất bại thay vì ghi dữ liệu sang một hệ thống không đúng hoặc không được cấp quyền.

### 13.1. Task có thể lỗi trước khi ghi TaskExecution

Nếu Spring Boot không đọc được `spring.datasource.password` hoặc Vault chưa xác thực, `TaskRepository` có thể **chưa khởi tạo**. Khi đó `TASK_EXECUTION` trống **không chứng minh không có yêu cầu khởi chạy**.

Nguồn điều tra theo thứ tự:

1. Launcher/scheduler đã tạo Job chưa?
2. Pod có khởi động được không, hay bị `CreateContainerConfigError`?
3. Ứng dụng có lỗi cấu hình/TLS/auth trước Runner không?
4. `TaskRepository` có ghi được `START_TIME` không?
5. Runner đã thực hiện bao nhiêu phần việc nghiệp vụ?

Nếu app thất bại ở cấu hình, lỗi có thể được ghi ở log khởi động/Pod events thay vì metadata Task.

## 14. Khi chạy qua Spring Cloud Data Flow hoặc TaskLauncher

### 14.1. Tách quyền launcher khỏi quyền runtime

`TaskLauncher` hoặc Spring Cloud Data Flow nhận URI artifact, command-line arguments, application properties và deployment properties để khởi chạy Task. Người dùng API launch có thể được quyền yêu cầu `orders-import --business-date=...` nhưng **không nên được quyền tự chọn mọi ServiceAccount hoặc secret reference**.

Kiến trúc phù hợp:

```text
Caller
  -> request: businessDate, source (allowlist)
  -> Launcher:
       chọn artifact/version được phê duyệt
       chọn namespace + serviceAccount từ policy
       chọn tham chiếu Secret/secret manager
       tạo Job / AppDeploymentRequest
  -> Spring Cloud Task:
       đọc secret từ runtime, KHÔNG từ request business
       chạy và ghi TaskExecution
```

Không chuyển plaintext password trong `TaskLaunchRequest.environmentProperties` qua message broker: payload launch có thể đi qua broker, tracing hoặc log. Khi cần cấu hình bí mật, ưu tiên **tham chiếu** đến Secret/role mà platform cấp cho container thay vì chứa giá trị.

### 14.2. Không ghi secret vào deployment properties

Một số backend cho phép chỉ định environment variables qua deployment properties. Nếu đặt plaintext credential trong request, nó có thể xuất hiện trong lịch sử lệnh hoặc metadata deployer.

Chỉ truyền **tên Secret**, **service account**, **resource name**, hoặc định danh secret manager đã được policy cho phép. Key cú pháp cụ thể phụ thuộc Kubernetes/Cloud Foundry/Local `TaskLauncher`; không giả định một property chung có thể chạy ở mọi backend.

### 14.3. Remote partitioning: mỗi worker cần credential phù hợp

Với Spring Batch remote partitioning, manager triển khai nhiều worker. Worker phải truy cập **cùng `JobRepository`** khi kiến trúc yêu cầu, nhưng không nhất thiết có quyền đọc tất cả secret của manager. Có thể phân quyền:

- Manager: quyền launch worker và truy cập metadata cần thiết.
- Worker: quyền đọc đúng partition và credential cần cho DB/queue nghiệp vụ.
- Migration Job: quyền DDL riêng; không cấp cho manager/worker.

Nếu mỗi worker sử dụng token ngắn hạn, TTL/rotation phải chịu được thời gian chạy Step và restart. Không truyền password trong `ExecutionContext` hoặc JobParameters vì metadata sẽ được lưu lại.

## 15. Quan sát bảo mật mà không lộ secret

### 15.1. Log và metric đề xuất

| Tín hiệu | Nên ghi | Không nên ghi |
| --- | --- | --- |
| Startup config | Tên môi trường, secret source kind, secret đã mount hay chưa | Password/token/cert private key |
| Vault auth | Thành công/thất bại, role ID không nhạy cảm, correlation ID | Vault token hoặc response chứa secret |
| JDBC | DB role logic, SQLState, kết nối thành công/thất bại | Connection URL có credential, plaintext password |
| Rotation | Thời điểm/version alias, kết quả rollout | Giá trị secret cũ/mới |
| `TaskExecution` | ID, trạng thái, exit code, thông điệp đã lọc | Secret trong args/error message |
| Metrics | Lỗi auth theo loại, Task startup failed count, latency secret manager | Secret value làm label, token prefix |

Một nguyên tắc thiết kế: **operator có thể xác minh Task được cấp quyền đúng mà không cần đọc giá trị secret**. Cần khả năng audit ở cả hai phía: secret manager (ai đọc secret) và scheduler/Task (ai chạy artifact nào).

### 15.2. Actuator và debug

Spring Boot Actuator có cơ chế che một số thông tin cấu hình, nhưng không dựa vào đó để cho phép tất cả người dùng gọi `/actuator/env` hoặc `/actuator/configprops`. Phải kiểm soát endpoint exposure, authentication, network và quyền đọc; việc sanitization có thể khác theo version/cấu hình.

Không bật debug toàn bộ Spring JDBC, HTTP client hoặc logging request body trong production chỉ để điều tra lỗi auth; trước hết sử dụng error code và redaction.

### 15.3. Audit các lần Task đọc secret

Ở Vault/cloud manager, audit event có thể cho biết identity nào đọc secret, thời điểm và đường dẫn/phiên bản secret. Ở phía Task, lưu:

```text
taskName: orders-import
taskExecutionId: <id hoặc correlation id>
artifactVersion: 1.4.2
environment: prod
secretReference: orders-task-db (chỉ tên đã được phép ghi)
credentialVersion: <version alias không nhạy cảm>
result: success/failure
```

Không dùng `<credentialVersion>` làm bằng chứng duy nhất rằng connection pool đang thực sự dùng credential tương ứng; cần test connection thực tế và quy trình rotate.

## 16. Runbook: Task không kết nối được database vì Secret

Giả sử Kubernetes Job được tạo nhưng Runner không chạy và log báo `FATAL: password authentication failed`.

### 16.1. Chuỗi điều tra ít rò rỉ

1. **Xác nhận Task đã được launch:** kiểm tra Job/Pod status, thời điểm khởi động và image digest.
2. **Kiểm tra Secret reference:** Secret name, namespace và key có đúng không; không in giá trị `data`.
3. **Kiểm tra Pod env/mount cấu hình:** tên biến môi trường, đường dẫn, quyền file và cấu hình `spring.config.import`.
4. **Kiểm tra identity và quyền:** ServiceAccount, Vault role hoặc cloud IAM binding có hợp lệ không.
5. **Kiểm tra TLS/network:** DNS, CA, hostname, firewall/egress, endpoint.
6. **Kiểm tra credential version/rotation:** secret mới đã được đồng bộ? Pod cũ còn dùng env cũ?
7. **Kiểm tra database role:** có quyền `CONNECT`, quyền trên schema/bảng/sequence đúng chức năng không.
8. **Đối chiếu metadata:** có `TaskExecution` nào được tạo chưa; có dữ liệu nghiệp vụ đã commit hay không.
9. **Khắc phục bằng quy trình phát hành/rotation** chứ không gửi plaintext credential qua chat, log hoặc tham số lệnh.
10. **Retry có giới hạn và idempotency**, xác nhận process cũ đã dừng trước khi chạy lại.

### 16.2. Lệnh Kubernetes chỉ đọc trạng thái

```bash
kubectl -n batch-jobs get jobs
kubectl -n batch-jobs get pods
kubectl -n batch-jobs describe pod <pod-name>
kubectl -n batch-jobs logs <pod-name> --tail=100
```

Chỉ dùng khi operator được cấp quyền và log đã có cơ chế bảo vệ dữ liệu nhạy cảm. `describe` có thể hiển thị **tên** Secret/key hoặc các thông tin triển khai, nên kết quả cũng cần được chia sẻ đúng phạm vi. Tránh các lệnh in thẳng environment process hoặc giải mã `Secret.data` để debug trên kênh không được kiểm soát.

## 17. Một số tình huống sự cố và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách xử lý an toàn |
| --- | --- | --- |
| `CreateContainerConfigError` | Secret/key bắt buộc chưa có | Kiểm tra reference/namespace, provisioning và events |
| `ConfigDataLocationNotFoundException` | Sai đường dẫn `configtree:` hoặc volume chưa mount | Sửa mount/path, không tự fallback sang credential hardcode |
| `AccessDenied` với Vault | ServiceAccount/role/policy không khớp | Kiểm tra audit và quyền tối thiểu, không dùng root token |
| TLS handshake failed | Thiếu CA, sai hostname hoặc cert hết hạn | Sửa chứng chỉ/truststore; không tắt verify |
| DB authentication failed sau rotation | Pod dùng env cũ, secret sync chậm, password cũ đã bị thu hồi | Drain/restart, kiểm tra version và thời điểm revoke |
| `TaskExecution` không có dòng | JVM lỗi trước khi repository sẵn sàng | Tra launcher/Pod/startup logs |
| Task kết thúc giữa chunk | Credential hết hạn hoặc lỗi kết nối | Checkpoint, transaction, dữ liệu đã commit trước khi retry |
| Có password trong `TASK_EXECUTION_PARAMS` | Secret từng được truyền bằng CLI | Thu hồi credential, làm sạch luồng cấp, điều tra metadata cũ |
| Có secret trong log | In `Environment`/HTTP headers/exception | Thu hồi, hạn chế truy cập, redaction và điều tra bản sao |
| Secret được sửa nhưng Task vẫn dùng giá trị cũ | Env immutable trong process hoặc bean chưa refresh | Tạo Pod mới hoặc tích hợp refresh được kiểm chứng |
| Hai môi trường dùng chung credential | Cấu hình Secret path/namespace/IAM sai | Tách role và secret theo môi trường, rotation có kiểm soát |
| Worker không có quyền ghi `BATCH_*` | Runtime user chỉ được quyền `TASK_*` | Cấp đúng DML/sequence cần thiết cho JobRepository |

## 18. Checklist trước khi chạy Task production

| Câu hỏi kiểm tra | Tiêu chí đạt |
| --- | --- |
| Secret có nằm trong Git/JAR/image/command line không? | **Không**, kể cả dạng Base64 |
| Credential có được tách theo môi trường không? | Dev, CI, staging, production có vai trò và secret độc lập |
| Pod/ServiceAccount có đủ nhưng không thừa quyền? | RBAC/IAM/Vault policy theo nguyên tắc least privilege |
| Secret được truyền qua kênh an toàn? | Secret reference/file hoặc manager có TLS và identity xác thực |
| Secret manager khi lỗi xử lý ra sao? | Fail an toàn; retry có giới hạn; không fallback plaintext |
| JDBC dùng TLS và xác minh server? | Driver, CA/hostname/certificate được cấu hình phù hợp |
| Runtime có quyền DDL không? | Không nếu đã dùng migration account riêng |
| TaskRepository/Batch có giữ secret không? | CLI/JobParameters/ExecutionContext không chứa credential |
| Có log/env/debug vô tình làm lộ không? | Đã kiểm tra redaction và hạn chế endpoint |
| Secret rotation có kiểm thử end-to-end? | Có kế hoạch dual credential/drain/restart/lease |
| Task dài hơn secret TTL có được xử lý? | Có renew hoặc deadline phù hợp; không giả định tự gia hạn |
| Có runbook thu hồi khẩn cấp không? | Có owner, bước revoke, audit và retry an toàn |
| Dữ liệu có thể bị xử lý trùng khi retry? | Có idempotency/checkpoint và ràng buộc nghiệp vụ |

## 19. Bài tập thực hành

**Bài tập 1 — Phân loại dữ liệu.** Cho danh sách `--business-date`, JDBC password, API token, JDBC hostname, CA certificate, Kubernetes ServiceAccount name và Vault role. Phân loại secret, cấu hình thông thường và thông tin danh tính/quyền. Giải thích những trường hợp metadata có thể vẫn nhạy cảm dù không phải password.

**Bài tập 2 — Kubernetes env.** Tạo **Secret thử nghiệm** trong namespace riêng (không dùng mật khẩu thật), cấu hình `secretKeyRef` cấp `TASK_DB_PASSWORD` cho Pod. Xác minh Pod nhận reference đúng mà **không in giá trị** Secret.

**Bài tập 3 — Configtree.** Tạo Secret có các key `spring.datasource.username` và `spring.datasource.password`, mount vào `/run/secrets/task-db/`. Viết `spring.config.import=configtree:...`, xác minh Task khởi tạo được `DataSource` và không có credential trong Git.

**Bài tập 4 — Env rotation.** Chạy một Job thử nghiệm, sửa Secret trong cluster và quan sát process đang chạy. Vì sao env hiện có không đổi? Đề xuất cách rollout/restart an toàn.

**Bài tập 5 — Vault.** Thiết kế role `orders-task-reader` ràng buộc namespace `batch-jobs` và ServiceAccount `orders-task-runner`; chỉ cho đọc một path KV. Giải thích vì sao không nên nhúng root token trong `application.yml`.

**Bài tập 6 — Dynamic credential.** Một Task có timeout 40 phút nhưng dynamic database credential hết hạn sau 15 phút. Phân tích nguy cơ và đề xuất renewal hoặc chia Step/Task với giới hạn thời lượng.

**Bài tập 7 — Quyền SQL.** Tách hai tài khoản: `task_migrator` và `task_runtime`. Liệt kê quyền DDL cần cho migration và quyền DML/sequence tối thiểu cho TaskRepository/JobRepository.

**Bài tập 8 — Tình huống lộ secret.** Một lần chạy cũ dùng `--api-token=...`. Hãy liệt kê những nơi cần điều tra (Git, shell history, Pod spec, `TASK_EXECUTION_PARAMS`, Batch, log, backup) và trình tự thu hồi token.

**Bài tập 9 — Remote partitioning.** Manager triển khai bốn worker. Thiết kế credential cho manager/worker sao cho worker đọc đúng partition và cùng `JobRepository`, nhưng không tự có quyền đọc mọi secret.

**Bài tập 10 — Incident.** Pod bị `CreateContainerConfigError` vì thiếu Secret, không có dòng `TASK_EXECUTION`. Viết checklist điều tra và giải thích vì sao đây chưa phải lỗi Runner.

**Bài tập 11 — TLS.** Một JDBC URL dùng TLS nhưng tắt xác minh chứng chỉ. Nêu nguy cơ, cách cấu hình trust và lý do password từ Vault vẫn chưa đủ bảo đảm kênh kết nối an toàn.

**Bài tập 12 — Kiểm toán.** Thiết kế log an toàn với `taskName`, `taskExecutionId`, `businessDate`, `secretReference` (chỉ tên được phép ghi), `artifactVersion` và result. Giải thích vì sao không ghi token prefix hoặc hash của password để debug.

## 20. Những nguyên tắc cần nhớ

1. **Spring Cloud Task cần bí mật để kết nối repository và dịch vụ khác, nhưng `TaskRepository` không phải secret store.**
2. **Không đưa password/token vào CLI hoặc JobParameters**, vì có thể được lưu trong `TASK_EXECUTION_PARAMS`, `BATCH_*` và hệ thống điều phối.
3. **Kubernetes Secret biểu diễn giá trị bằng Base64, không phải mã hóa dữ liệu.** Cần bật encryption at rest cho `etcd` và áp dụng RBAC đúng.
4. **`secretKeyRef` và Secret volume giải quyết cách cấp dữ liệu**, không thay thế phân quyền, mã hóa đường truyền hoặc quản lý vòng đời.
5. **Env của process không tự đổi sau khi Secret thay đổi**; volume có thể được cập nhật nhưng `DataSource`/bean vẫn cần đọc lại hay restart để sử dụng giá trị mới.
6. **Spring Boot `configtree:` cho phép đọc file mount như properties**; cần đặt tên key, đường dẫn và quyền file đúng.
7. **Vault/cloud secret manager nên được truy cập bằng workload identity**, với quyền tối thiểu và TLS; tránh root token/static access key trong JAR.
8. **Credential động có TTL và cơ chế cấp lại riêng**; Job dài cần thiết kế renewal, connection pool và deadline.
9. **Tách runtime user và migration user**, đồng thời tách quyền TaskRepository, JobRepository và DB nghiệp vụ khi phù hợp.
10. **Rotation, thu hồi, kiểm toán và retry idempotent phải được thử nghiệm**, không chỉ kiểm tra Pod có biến môi trường.
11. **Một lỗi secret có thể xảy ra trước khi TaskExecution được tạo**; điều tra qua launcher, Pod, secret manager và log startup.
12. **Chỉ ghi log/metric đủ để điều tra mà không chứa giá trị bí mật**, kể cả trong exception, trace attribute và Actuator endpoint.

## Tài liệu tham khảo

- [Spring Cloud Task — Reference](https://docs.spring.io/spring-cloud-task/reference/): vòng đời Task và `TaskRepository`.
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/reference/appendix-task-repository-schema.html): `TASK_EXECUTION_PARAMS` và các bảng metadata liên quan.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): biến môi trường, placeholders, `configtree:` và precedence.
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): `secretKeyRef`, volume, đồng bộ cập nhật và `subPath`.
- [Kubernetes — Good Practices for Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/): Base64, encryption at rest, RBAC và giới hạn quyền truy cập.
- [Kubernetes — Encrypting Secret Data at Rest](https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/): bảo vệ dữ liệu Secret trong `etcd`.
- [Kubernetes — Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/): danh tính Pod và token được cấp theo quyền.
- [Spring Cloud Vault — Config Data API](https://docs.spring.io/spring-cloud-vault/reference/config-data.html): `spring.config.import=vault://` và nguồn cấu hình Vault.
- [Spring Cloud Vault — Authentication Methods](https://docs.spring.io/spring-cloud-vault/reference/authentication.html): Kubernetes authentication và các mô hình xác thực khác.
- [Spring Cloud Vault — Quick Start](https://docs.spring.io/spring-cloud-vault/reference/quickstart.html): cấu hình Vault, TLS và dependency.
- [Secrets Store CSI Driver — Usage](https://secrets-store-csi-driver.sigs.k8s.io/getting-started/usage.html): mount external secret và khả năng đồng bộ tùy chọn.
- [Secrets Store CSI Driver — Auto Rotation](https://secrets-store-csi-driver.sigs.k8s.io/topics/secret-auto-rotation): điều kiện bật và độ trễ rotation của CSI.
- [Prometheus — Instrumentation Best Practices](https://prometheus.io/docs/practices/instrumentation/): ghi số đo/nhãn phù hợp, tránh dùng secret làm metric labels.
