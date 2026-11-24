# Bảo vệ thông tin bí mật khỏi tham số được lưu và nhật ký

Trong **Spring Cloud Task**, ứng dụng Spring Boot khởi động, nhận tham số, thực hiện công việc hữu hạn, cập nhật trạng thái của `TaskExecution` trong **TaskRepository**, rồi kết thúc. Cơ chế lưu metadata giúp truy vết và vận hành tác vụ nhập dữ liệu, báo cáo, bảo trì hoặc chạy theo lịch. Nhưng nó cũng tạo một bề mặt bảo mật quan trọng: **đối số dòng lệnh có thể được lưu lâu dài trong cơ sở dữ liệu**. Nếu truyền mật khẩu, API token hoặc khóa ký qua tham số, bí mật có thể nằm lại trong TaskRepository ngay cả khi tiến trình đã thoát.

Bài thuộc chương **Bảo mật**, tập trung vào cách tránh lộ **secrets** trong **Task arguments**, **Spring Batch JobParameters**, **`exitMessage`**, **`errorMessage`**, exception và application logs. Ta sẽ dùng một tác vụ nhập hóa đơn từ đối tác làm ví dụ, thiết kế cách cấp credential qua môi trường/Secret store, cách log an toàn, kiểm soát quyền trên metadata và bài kiểm thử chứng minh không rò rỉ bí mật.

> **Nguyên tắc chính:** Bí mật cần thiết cho **thực thi**, nhưng thường **không cần tồn tại trong đối số dùng để truy vết**. Hãy truyền *định danh nghiệp vụ và tham chiếu không nhạy cảm* qua arguments; cung cấp *giá trị credential* qua kênh bảo mật và không ghi nó vào metadata, logs, metrics, traces hoặc exception messages.

## 1. Bí mật có thể rò rỉ ở đâu?

Một tác vụ có thể được kích hoạt từ CronJob, Spring Cloud Data Flow, API launcher hoặc terminal. Tưởng tượng lệnh sau:

~~~bash
# KHÔNG ÁP DỤNG: đây là ví dụ cố tình sai.
java -jar partner-import-task.jar \
  --business-date=2026-11-23 \
  --partner-id=partner-a \
  --api-token=DEMO_DO_NOT_USE_AS_A_REAL_SECRET
~~~

Giá trị sau `--api-token=` có thể xuất hiện ở nhiều nơi:

| Vị trí | Vì sao có nguy cơ? | Ai có thể thấy? |
| --- | --- | --- |
| **`TASK_EXECUTION_PARAMS`** | Spring Cloud Task ghi đối số khởi chạy vào TaskRepository | Người/tài khoản đọc metadata, công cụ quản trị, backup |
| **Process command line** | Hệ điều hành/container runtime giữ argv khi tiến trình còn sống | Người có quyền quan sát tiến trình/host/container |
| **Kubernetes Pod spec** | `args` nằm trong Pod template hoặc Job manifest | Người có quyền đọc Pod/Job, nhật ký audit API |
| **Shell history, CI/CD logs** | Lệnh launch được ghi/lưu bởi terminal hoặc pipeline | Người có quyền xem lịch sử hay log |
| **Spring Batch `JobParameters`** | Nếu copy `api-token` vào JobParameters thì Batch lưu trong repository riêng | Người có quyền đọc `BATCH_JOB_EXECUTION_PARAMS` |
| **Application logs** | `log.info("args={}", args)` hoặc log request/response không lọc | Người đọc hệ thống log tập trung |
| **`EXIT_MESSAGE` / `ERROR_MESSAGE`** | Listener hoặc exception chứa raw token | Người xem TaskExecution và trang chi tiết lỗi |
| **Metrics, traces, events** | Token vô tình thành tag/span attribute/event payload | Người truy vấn hệ thống giám sát/message broker |

**Không lưu mật khẩu trong đối số** là biện pháp đầu tiên, nhưng chưa phải toàn bộ giải pháp. Secret được cấp qua biến môi trường hoặc file vẫn có thể rò rỉ nếu code in `Environment`, dump cấu hình, log `Authorization` header hoặc đưa raw exception vào `exitMessage`.

### Sơ đồ các đường đi dữ liệu

~~~mermaid
flowchart TD
    L["Cron / API / CLI launcher"] --> A["Command-line arguments"]
    L --> S["Secret manager / Kubernetes Secret"]
    A --> P["Spring Cloud Task process"]
    A --> H[("TASK_EXECUTION_PARAMS<br/>metadata bền vững")]
    S --> E["Env / mounted secret file"]
    E --> P
    P --> B["Xử lý nghiệp vụ / HTTP / JDBC"]
    P --> X[("TASK_EXECUTION<br/>EXIT_MESSAGE, ERROR_MESSAGE")]
    P --> G[("Logs / traces / metrics")]
    B --> G
    B --> R[("Kết quả nghiệp vụ")]
    H -. "quyền đọc, sao lưu" .-> U["Người/công cụ vận hành"]
    X -. "quyền đọc" .-> U
    G -. "quyền đọc" .-> U
~~~

Mục tiêu không phải “ẩn token bằng cách đặt tên khác”, mà **giới hạn việc token đi vào những luồng được thiết kế để lưu, tìm kiếm và chia sẻ metadata**.

## 2. Spring Cloud Task thực sự lưu những gì?

Một lần chạy được biểu diễn bởi `TaskExecution`. Theo tài liệu chính thức, thông tin gồm `executionId`, `taskName`, `startTime`, `endTime`, `exitCode`, `exitMessage`, `errorMessage` và danh sách **arguments**. Trong schema mặc định:

| Bảng / cột | Dữ liệu | Nguy cơ nếu đưa secret vào |
| --- | --- | --- |
| `TASK_EXECUTION` | Metadata một lần chạy, `EXIT_MESSAGE`, `ERROR_MESSAGE` | Thông báo tùy biến hoặc stack trace có thể lộ secret |
| `TASK_EXECUTION_PARAMS` | `TASK_EXECUTION_ID`, `TASK_PARAM` | Chuỗi đối số được giữ sau khi Task kết thúc |
| `TASK_TASK_BATCH` | Liên kết TaskExecution và JobExecution (nếu tích hợp Batch) | Có thể dẫn người đọc sang Batch metadata |
| `BATCH_JOB_EXECUTION_PARAMS` | `PARAMETER_NAME`, `PARAMETER_VALUE` và cờ identifying ở Spring Batch 5.x | Secret truyền trong JobParameters tồn tại bền vững |
| Bảng nghiệp vụ | Dữ liệu nguồn/đích và trạng thái xử lý | Có thể bị lộ do mã lỗi hoặc log raw payload |

Theo schema tham khảo Spring Cloud Task, `TASK_EXECUTION_PARAMS.TASK_PARAM` có giới hạn `VARCHAR(2500)`; `TASK_EXECUTION.EXIT_MESSAGE` và `ERROR_MESSAGE` cũng được mô tả là `VARCHAR(2500)`. Giới hạn và DDL thật phụ thuộc phiên bản/cơ sở dữ liệu; **cột có giới hạn ký tự không có nghĩa giá trị được mã hóa hoặc che giấu**.

**Một sai lầm thường gặp:**

~~~text
--spring.datasource.password=real-password
--partner-api-key=real-api-key
--storage.s3.secret-key=real-secret-key
~~~

Spring Boot có thể dùng các giá trị đó làm **cấu hình ứng dụng**; đồng thời chúng vẫn là **đối số đầu vào**, có thể nằm trong metadata của Task. Việc property có tên `password` hoặc `secret` không đồng nghĩa Spring Cloud Task tự động bỏ qua/redact giá trị khi ghi `TASK_EXECUTION_PARAMS`.

### 2.1. `TASK_EXECUTION_PARAMS` khác với JobParameters

Spring Cloud Task và Spring Batch có repository riêng theo vai trò:

~~~text
Spring Cloud Task
  TaskExecution #4101
    arguments = [
      "--business-date=2026-11-23",
      "--partner-id=partner-a"
    ]

Spring Batch (nếu ứng dụng có Batch Job)
  JobExecution #9001
    JobParameters = {
      businessDate: "2026-11-23",
      sourceId: "partner-a"
    }
~~~

**Không copy bí mật từ Task arguments sang Batch JobParameters.** Trong Spring Batch, `BATCH_JOB_EXECUTION_PARAMS` lưu các tham số đã truyền cho Job, kể cả tham số **non-identifying**. Cờ `identifying=false` chỉ thay đổi việc tham số có góp phần định danh `JobInstance` hay không; **nó không có nghĩa “không lưu” hoặc “không nhạy cảm”**.

Nếu Task được khởi chạy qua Spring Cloud Data Flow, UI và lịch sử launch/execution cũng có thể hiển thị arguments tùy quyền truy cập. Vì vậy cần xem mọi hệ thống điều phối là một bề mặt có thể ghi/đọc metadata, không phải kênh giữ bí mật mặc định.

## 3. Phân loại dữ liệu trước khi thiết kế tham số

Một cách đơn giản là lập **allowlist** cho những trường được phép xuất hiện trong metadata:

| Giá trị | Cho vào Task argument? | Lý do |
| --- | --- | --- |
| `--business-date=2026-11-23` | **Có** | Ngày nghiệp vụ có thể đối soát |
| `--operation=import` | **Có** | Chế độ xử lý, không phải bí mật |
| `--report-version=2` | **Có** | Định danh phiên bản kết quả |
| `--source-id=partner-a-feed-42` | Có **nếu đã phân loại là không nhạy cảm** | ID có thể trở thành dữ liệu nhạy cảm trong một số hệ thống |
| `--credential-ref=partner-a-service` | Có **nếu reference không nhạy cảm** | Chỉ là khóa logic để resolver lấy secret thật |
| `--access-token=...` | **Không** | Credential cấp quyền trực tiếp |
| `--db-password=...` | **Không** | Mật khẩu database |
| `--private-key=...` | **Không** | Khóa ký hoặc khóa giải mã |
| `--connection-string=...password=...` | **Không** | Connection string có credential |
| `--customer-email=...` | Hạn chế / xem chính sách PII | Không phải token nhưng có thể là dữ liệu cá nhân |

**Phân loại theo giá trị và mục đích, không chỉ theo tên key.** Một `source-id` chứa email hoặc đường dẫn tới dữ liệu mật cũng không nên đưa nguyên văn vào logs. Một `credential-ref` nếu là URL có token ký sẵn hoặc mã truy cập có thể dùng trực tiếp cũng phải được xử lý như secret.

### 3.1. Thiết kế hai kênh nhập tách biệt

~~~text
Kênh A — arguments lưu được:
  --business-date=2026-11-23
  --partner-id=partner-a
  --run-mode=scheduled

Kênh B — bí mật chỉ dùng tại runtime:
  PARTNER_API_TOKEN (Secret / vault)
  TASK_DB_PASSWORD (Secret / vault)
  TLS_PRIVATE_KEY (secret volume hoặc secret manager)
~~~

**Không có kênh nào an toàn tuyệt đối.** Kênh B giảm nguy cơ ghi vào TaskRepository và argv, nhưng tiến trình vẫn có thể truy cập secret; cần kiểm soát quyền, node/container, log, dump và rotation.

## 4. Ví dụ sai và đúng khi launch ứng dụng

### 4.1. Sai: đưa credential vào dòng lệnh

~~~bash
# Chỉ là phản ví dụ; không dùng với credential thật.
java -jar partner-import-task.jar \
  --business-date=2026-11-23 \
  --partner-api-token=DEMO_SECRET_DO_NOT_USE
~~~

Rủi ro:

- Token có thể được lưu trong `TASK_EXECUTION_PARAMS`.
- Shell history và process argv có thể giữ nguyên lệnh.
- Kubernetes Job/Pod specs và nền tảng điều phối có thể ghi lại `args`.
- Nếu mã có `log.info("Args: {}", args.getSourceArgs())`, token xuất hiện thêm trong logs.

**Đổi sang một tên property lạ** như `--p-a-t=...` không giải quyết được vấn đề; chuỗi vẫn có trong arguments.

### 4.2. Đúng hướng: credential ở môi trường/secret provider

~~~bash
# DEMO_ONLY: truyền duy nhất các tham số không nhạy cảm.
java -jar partner-import-task.jar \
  --business-date=2026-11-23 \
  --partner-id=partner-a
~~~

Trong môi trường Kubernetes, `PARTNER_API_TOKEN` được cấp qua Secret chứ không phải argument. Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  application:
    name: partner-import-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      initialize-enabled: false

partner:
  api:
    token: ${PARTNER_API_TOKEN}
~~~

Ở ví dụ này, các biến môi trường phải tồn tại khi tiến trình khởi động; giá trị token **không được ghi lại trong `application.yml`**. Không commit file `.env` chứa secret hoặc đưa file đó vào image.

**Giới hạn:** nội suy `${PARTNER_API_TOKEN}` chỉ đưa credential vào Spring Environment; nếu ứng dụng in toàn bộ properties, expose Actuator quá rộng hoặc tạo exception chứa token, secret vẫn có thể rò rỉ. Kênh cấp secret tốt phải đi kèm **kỷ luật không log**.

## 5. Kubernetes Secret: env và mounted volume

Một Kubernetes Job có thể nhận secret qua `env[].valueFrom.secretKeyRef`:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: partner-import-demo
  namespace: batch-jobs
spec:
  backoffLimit: 1
  template:
    spec:
      serviceAccountName: partner-import-task
      automountServiceAccountToken: false
      restartPolicy: Never
      containers:
        - name: task
          image: registry.example.com/batch/partner-import-task:1.0.0
          args:
            - "--business-date=2026-11-23"
            - "--partner-id=partner-a"
          env:
            - name: TASK_DB_URL
              valueFrom:
                secretKeyRef:
                  name: task-db-credentials
                  key: jdbc-url
            - name: TASK_DB_USER
              valueFrom:
                secretKeyRef:
                  name: task-db-credentials
                  key: username
            - name: TASK_DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: task-db-credentials
                  key: password
            - name: PARTNER_API_TOKEN
              valueFrom:
                secretKeyRef:
                  name: partner-api-credentials
                  key: token
~~~

Tên Secret, image, namespace và ServiceAccount chỉ là minh họa. Môi trường thực tế phải tạo những tài nguyên này và có network policy/quyền phù hợp. `automountServiceAccountToken: false` hợp lý khi Task **không cần gọi Kubernetes API**; nếu ứng dụng thật sự cần API, hãy cấp ServiceAccount tối thiểu và cấu hình token theo nhu cầu.

**Secret không nên được ghi trong manifest dưới dạng dữ liệu rõ**. Kubernetes Secret base64 **không phải mã hóa**: ai đọc được giá trị base64 có thể giải mã. Cần giới hạn quyền `get/list/watch` Secrets bằng RBAC, bật **encryption at rest** cho etcd khi dùng Kubernetes và quản lý quyền truy cập vào hệ thống sao lưu.

### 5.1. Mật khẩu qua env chưa phải tuyệt đối an toàn

Biến môi trường tránh lưu secret trong Task arguments, nhưng vẫn có thể bị đọc bởi:

- Mã chạy **trong cùng container/process**.
- Người có quyền `exec`/debug hoặc truy cập host/node theo cấu hình.
- Crash dump, bộ thu chẩn đoán hoặc thư viện in toàn bộ `System.getenv()`.
- Các thành phần có đặc quyền trong hạ tầng.

Nếu yêu cầu bảo mật cao, cân nhắc secret manager hoặc **mounted file/Secret Store CSI Driver**; chỉ mount vào container cần dùng, giới hạn filesystem permissions và không dump nội dung file vào log.

### 5.2. Mounted Secret thay cho env

Ví dụ mount token vào một đường dẫn riêng:

~~~yaml
volumes:
  - name: partner-token
    secret:
      secretName: partner-api-credentials
      items:
        - key: token
          path: token
containers:
  - name: task
    image: registry.example.com/batch/partner-import-task:1.0.0
    volumeMounts:
      - name: partner-token
        mountPath: /var/run/secrets/partner
        readOnly: true
~~~

Đây là **mảnh Pod spec minh họa**, phải đặt dưới `spec.template.spec` và kết hợp với phần Job hoàn chỉnh. Ứng dụng đọc token từ `/var/run/secrets/partner/token` qua một service chuyên trách, sử dụng trong HTTP client, **không in file path nhạy cảm hoặc nội dung token trong log**.

Mounted file giúp tách bí mật khỏi argv/env nếu code thực sự đọc file trực tiếp. Nhưng nội dung file vẫn có thể bị tiến trình hợp lệ đọc; cần quyền Pod/container, bảo mật node, chính sách cấp secret và rotation. Nếu dùng Kubernetes Secret làm env, việc đổi Secret **thường không tự cập nhật giá trị env trong một Pod đang chạy**; với mounted volumes, việc cập nhật có điều kiện và độ trễ, ngoại lệ như `subPath`. Với **Task chạy ngắn**, chiến lược thực tế thường là **mỗi lần chạy lấy secret mới lúc khởi động**, kèm quy trình thu hồi token cũ.

## 6. Mã Java: đọc tham số an toàn, không log giá trị bí mật

Tác vụ nhập dữ liệu nên nhận **business-date** và **partner-id** qua `ApplicationArguments`, còn token được cấp từ provider cấu hình và chỉ chuyển tới HTTP client.

~~~java
import java.time.LocalDate;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ImportTaskConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(ImportTaskConfiguration.class);

    @Bean
    ApplicationRunner runImport(
            PartnerImportService service,
            @Value("${partner.api.token}") String apiToken) {

        return args -> {
            LocalDate businessDate = LocalDate.parse(
                    required(args, "business-date"));
            String partnerId = required(args, "partner-id");

            // Log allowlist: không in toàn bộ args hoặc Environment.
            log.info(
                    "Import starting: operation=partner-import, date={}",
                    businessDate);

            // Mã service chịu trách nhiệm không log apiToken.
            ImportResult result =
                    service.importOrders(partnerId, businessDate, apiToken);

            log.info("Import completed: accepted={}, rejected={}",
                    result.accepted(), result.rejected());
        };
    }

    private static String required(
            ApplicationArguments args, String key) {
        List<String> values = args.getOptionValues(key);
        if (values == null || values.size() != 1 ||
                values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Missing or invalid option: " + key);
        }
        return values.get(0);
    }
}

interface PartnerImportService {
    ImportResult importOrders(
            String partnerId, LocalDate date, String apiToken);
}

record ImportResult(long accepted, long rejected) {}
~~~

Đoạn code là **ví dụ thành phần**: phải cung cấp bean `PartnerImportService`, dependency Spring Cloud Task, DataSource và cấu hình ứng dụng. `ImportResult` ghi lại số lượng xử lý, không chứa token.

**Chú ý vòng đời dữ liệu trong JVM:** `String apiToken` vẫn nằm trong bộ nhớ và có thể xuất hiện trong heap dump. Với loại secret cần bảo vệ ở mức cao hơn, ưu tiên client/credential provider tự quản lý secret, tránh nhân bản `String` nhiều nơi và kiểm soát chính sách dump. Việc dùng `char[]` không làm hệ thống tự động an toàn nếu thư viện HTTP/JDBC cuối cùng lại chuyển thành `String`.

### 6.1. Các cách log nên tránh

~~~java
// KHÔNG làm trong production.
log.info("Arguments: {}", args.getSourceArgs());
log.debug("All environment variables: {}", System.getenv());
log.info("Partner configuration: {}", partnerProperties);
log.error("HTTP request: {}", request);
log.error("HTTP response: {}", response);
~~~

Tùy thư viện, `toString()` của một object có thể chứa `Authorization`, cookie, URL có token, credentials hoặc nội dung dữ liệu nhạy cảm. Kể cả ở mức `DEBUG` cũng có nguy cơ: cấp độ log có thể bị bật tạm thời rồi quên tắt, log được ship lên backend với retention dài.

Thay bằng **trường được phép**:

~~~java
log.info(
    "Partner import started: date={}, operation={}",
    businessDate, "import-orders");

log.warn(
    "Partner API rejected request: reasonCode={}, retryable={}",
    "AUTH_REJECTED", false);
~~~

Không ghi nguyên `partnerId` nếu ID đó được phân loại nhạy cảm; có thể dùng mã nội bộ ổn định, hash có khóa hoặc một tham chiếu sự cố đã kiểm soát.

## 7. Exception và ERROR_MESSAGE: chỗ rò rỉ dễ bị bỏ sót

Spring Cloud Task lưu **`ERROR_MESSAGE`** khi kết thúc do exception; tài liệu mô tả nó có thể chứa **stack trace**. Stack trace thường bao gồm **exception message**, và message đôi khi do thư viện bên ngoài tạo ra, có thể chứa:

- URL với query `?api_key=...`.
- JDBC URL có mật khẩu.
- Response body từ API đối tác (có thể chứa token hoặc PII).
- File path, record nội bộ hoặc header xác thực.
- Đối số lỗi chứa giá trị raw của người dùng.

Ví dụ nguy hiểm:

~~~java
throw new IllegalArgumentException(
        "Invalid token: " + apiToken);
~~~

Ngay cả khi không có một dòng `log.error(...)`, exception này vẫn có thể được ghi vào **`TASK_EXECUTION.ERROR_MESSAGE`**. Tương tự, một listener gọi `taskExecution.setExitMessage(exception.getMessage())` có thể lưu credential thêm vào `EXIT_MESSAGE`.

### 7.1. Dùng reason code không nhạy cảm

~~~java
try {
    partnerClient.executeImport();
} catch (PartnerAuthenticationException ex) {
    // Không đưa ex.getMessage() hay raw response vào log.
    log.warn("Partner import failed: reasonCode=AUTH_REJECTED");

    // Message cố định, không chứa token hoặc dữ liệu đối tác.
    throw new IllegalStateException("PARTNER_AUTH_REJECTED");
}
~~~

Mục đích ví dụ là **ngăn đường đi từ raw exception sang ERROR_MESSAGE**. Vì cố tình không gắn `ex` làm cause trong exception được ném tiếp, stack trace được lưu không chứa message gốc có thể nhạy cảm. Nếu cần điều tra root cause, hãy dùng một luồng chẩn đoán **được phân quyền, được redaction và có retention giới hạn**; không tự động đưa raw exception sang log chung.

**Không bắt mọi exception rồi trả về bình thường**: cách này có thể làm `exitCode=0` dù nghiệp vụ lỗi. Hãy ném exception có thông điệp an toàn hoặc dùng cơ chế trả mã thoát lỗi phù hợp với Task; bảo mật không nên làm sai trạng thái thực thi.

### 7.2. Listener ghi exitMessage có cấu trúc

Một listener có thể ghi thông điệp cuối gọn để người vận hành hiểu tác vụ:

~~~java
import org.springframework.cloud.task.listener.annotation.FailedTask;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class SafeFailureSummaryListener {

    @FailedTask
    public void onFailure(
            TaskExecution execution, Throwable failure) {
        execution.setExitMessage(
                "FAILED; reason=TASK_EXECUTION_ERROR");
    }
}
~~~

**Phạm vi của listener:** `exitMessage` do mình kiểm soát; nó **không tự làm sạch `errorMessage`** mà framework có thể ghi từ exception. Cần phối hợp kiểm soát exception ở **nguồn phát sinh**, không kỳ vọng listener sau cùng có thể redaction mọi nơi.

Không đặt `@AfterTask` để ghi vô điều kiện `SUCCESS`: callback này có thể chạy sau thất bại và ghi đè thông điệp do `@FailedTask` đặt. Nếu có listener tổng kết, chỉ ghi thành công khi trạng thái thật sự thành công.

## 8. Spring Batch JobParameters cũng phải được xem là metadata công khai có kiểm soát

Khi Task chạy một Spring Batch Job, `JobParameters` được lưu tại **JobRepository**, thường ở `BATCH_JOB_EXECUTION_PARAMS`. Ví dụ đúng:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-23", true)
        .addString("partnerId", "partner-a", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
~~~

Không làm:

~~~java
// KHÔNG ĐƯA secret vào JobParameters, dù identifying=false.
JobParameters bad = new JobParametersBuilder()
        .addString("apiToken", apiToken, false)
        .toJobParameters();
~~~

**`identifying=false` không có nghĩa parameter được ẩn hoặc không ghi DB**. Nó chỉ không tham gia định danh `JobInstance`. Khi restart, Spring Batch cần metadata JobParameters; vì vậy chúng thường có đời sống dài hơn tiến trình và được nhiều công cụ Batch Explorer/UI sử dụng.

Cách đúng hơn:

- JobParameters giữ `partnerId` hoặc `credentialRef` an toàn.
- `ItemReader`/service ở runtime lấy token qua secret provider.
- Không đưa token vào `ExecutionContext` của Job/Step, vì `ExecutionContext` cũng có thể được **serialize xuống JobRepository** để checkpoint/restart.
- Tránh để DTO/Item/exception chứa token trong phần state được serialize hoặc log.

Cần phân biệt `TaskRepository` với `JobRepository`: **hai kho metadata có vai trò khác nhau**, và phải đặt quyền đọc/bảo vệ sao lưu cho cả hai nếu ứng dụng dùng Spring Batch.

## 9. Cơ chế redaction trong log và tracing

Không nên cố giải quyết bài toán bằng **một filter regex duy nhất** vì định dạng secret không cố định. Nên dùng nhiều lớp:

1. **Không tạo giá trị cần redact:** không đưa secret vào arguments, exception, log message, metric tag hoặc span attribute.
2. **Log allowlist:** chỉ log `event`, `operation`, `outcome`, mã lý do, số lượng đã xử lý, correlation ID an toàn.
3. **Sanitization tập trung:** cấu hình logging/HTTP client để che `Authorization`, `Cookie`, `Set-Cookie`, `X-Api-Key`, chuỗi URL nhạy cảm; coi đây là hàng rào phụ.
4. **Không log raw request/response body:** nếu cần debug, dùng dữ liệu mẫu/giả lập, loại bỏ trường nhạy cảm và giới hạn quyền xem.
5. **Bảo vệ tracing:** không đưa bearer token, mật khẩu, signed URL hoặc query raw vào `Span` attributes; chọn tag cardinality thấp cho metrics.
6. **Chính sách quyền và retention:** backend logs, traces và events có ACL, thời hạn lưu, audit access và encryption theo mức dữ liệu.

### 9.1. Ví dụ logging interceptor an toàn

~~~java
// Pseudocode ở ranh giới HTTP client:
log.info(
    "partner_request_completed operation={} statusCode={} durationMs={}",
    "import-orders",
    response.statusCode(),
    duration.toMillis());

// Không làm:
// log.info("headers={}", request.headers());
// log.info("body={}", response.body());
// log.info("url={}", request.uri());
~~~

URL có thể chứa query token. Khi cần quan sát đích HTTP, ghi **host/route template đã được cho phép** thay vì toàn bộ URI. Đối với HTTP client/SDK, kiểm tra logger debug của thư viện vì việc không tự log trong code của bạn **không đảm bảo thư viện cũng không log**.

### 9.2. Đừng để token trong metric labels

~~~text
# Nên:
business.task.outcome{operation="import",outcome="success"}

# Không nên:
business.task.outcome{apiToken="<secret>",customerEmail="<PII>"}
~~~

Metric labels thường có retention dài và được index/truy vấn rộng. Ngoài rò rỉ, label thay đổi mỗi request còn gây **high cardinality**. Đưa `TaskExecution ID` vào structured logs/traces hoặc metadata, không dùng làm nhãn metric cho mọi lần chạy.

## 10. Spring Boot Actuator: bảo vệ việc xem cấu hình

Dù Task thường chạy với `spring.main.web-application-type=none` và không mở HTTP server, một số ứng dụng vẫn bật **Actuator** hoặc JMX. Endpoint `/actuator/env` và `/actuator/configprops` có thể chứa cấu hình nhạy cảm.

Trong Spring Boot 3.x, các endpoint này **che giá trị theo mặc định**, và thuộc tính `management.endpoint.env.show-values`/`management.endpoint.configprops.show-values` điều khiển việc hiển thị. Ví dụ đặt chế độ chặt chẽ:

~~~yaml
management:
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
  endpoints:
    web:
      exposure:
        include: "health,info"
~~~

Đây là **lớp bảo vệ phụ**, không phải cách ngăn Spring Cloud Task lưu arguments. Không bật `show-values: always` ở môi trường thật chỉ để debug. Nếu cần endpoint quản trị, bảo vệ network, TLS, authentication và authorization; kiểm tra cả JMX và các endpoint tự định nghĩa.

**Không giả định sanitization của Actuator cũng áp dụng** cho `TASK_EXECUTION_PARAMS`, `BATCH_JOB_EXECUTION_PARAMS`, structured logs hay exception message. Chúng là các đường dữ liệu khác nhau.

## 11. Phân quyền TaskRepository và JobRepository

Người có quyền đọc metadata có thể xem lịch sử tham số và lỗi. Vì vậy:

| Đối tượng | Quyền đề xuất | Lý do |
| --- | --- | --- |
| Tài khoản runtime của Task | Quyền DML cần thiết cho bảng Task (và Batch nếu có) | Tạo/cập nhật kết quả một lần chạy |
| Bộ điều phối/Task explorer | Quyền đọc metadata cần dùng | Xem trạng thái mà không cần quyền quản trị DB |
| Người hỗ trợ vận hành | Quyền đọc hạn chế, qua giao diện có kiểm soát | Tránh truy cập raw arguments/errorMessage ngoài nhu cầu |
| Migration account | DDL qua quy trình thay đổi được phê duyệt | Không cấp quyền `CREATE/ALTER/DROP` tràn lan cho runtime |
| Backup/BI/export | Quyền tối thiểu, encryption và thời hạn lưu | Metadata có thể chứa dữ liệu từng rò rỉ trước đó |

**Không dùng `SELECT *` đưa nguyên bảng arguments hoặc errors vào ticket** nếu không kiểm soát nội dung. Nếu cần chia sẻ sự cố, chỉ xuất các trường cho phép như execution ID, tên task, thời gian, mã thoát và reason code đã làm sạch.

Khi TaskRepository dùng chung cho nhiều team hoặc tenant, thiết kế **phân tách quyền truy cập** theo vai trò/schema/công cụ điều phối phù hợp. **Một tài khoản có `SELECT` trên `TASK_EXECUTION_PARAMS` có thể đọc tham số của nhiều lần chạy**; che thông tin trên UI không giúp nếu tài khoản vẫn có truy cập SQL trực tiếp.

### 11.1. Truy vấn chỉ trạng thái tối thiểu

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'partner-import-task'
ORDER BY START_TIME DESC;
~~~

Truy vấn trên **không lấy** `TASK_PARAM`, `EXIT_MESSAGE`, `ERROR_MESSAGE`; phù hợp hơn để tạo báo cáo trạng thái ở phạm vi rộng. Muốn điều tra chi tiết lỗi, dùng một luồng được ủy quyền, có kiểm soát dữ liệu xuất ra.

### 11.2. Lưu trữ, sao lưu và xóa dữ liệu cũ

Metadata có thể được lưu nhiều tháng/năm để điều tra và restart. Nếu từng vô tình ghi token vào `TASK_EXECUTION_PARAMS`, sửa code **chỉ ngăn rò rỉ ở tương lai**; bản cũ có thể còn trong:

- Bảng TaskRepository/JobRepository.
- Database backup, replica, CDC stream.
- Log shipper, search index, dashboard snapshots.
- CI/CD job logs và các tệp chẩn đoán.
- Ticket/screenshot do người vận hành đã tạo.

Với rò rỉ thực tế, phải **thu hồi/rotate secret trước**, xác định phạm vi truy cập và tuân theo quy trình incident response. Sau đó thực hiện cleanup phù hợp retention, quan hệ FK, restart requirements và backup lifecycle. Đừng xóa bảng Task/Batch trực tiếp để “xóa nhanh” vì có thể làm mất lịch sử cần thiết cho recovery.

## 12. Kiểm chứng không rò rỉ bằng token giả

Dùng **canary giả** thay cho secret thật khi thử nghiệm:

~~~text
SCT_CANARY_FAKE_TOKEN_FOR_TEST_20261124
~~~

Đây là chuỗi **không có giá trị xác thực**, dùng để tìm đường rò rỉ. Cấp nó qua Secret thử nghiệm, **không** qua arguments. Chạy một Task test mà service nhận giá trị giả nhưng không thực hiện lời gọi nhạy cảm ra ngoài.

Kiểm chứng:

1. Khởi chạy Task bằng `--business-date=...` và `--partner-id=...`, **không có token trong argv**.
2. Xác nhận `TaskExecution.arguments` chỉ chứa allowlisted options.
3. Kiểm tra `TASK_EXECUTION_PARAMS` không chứa canary.
4. Nếu có Batch, kiểm tra `BATCH_JOB_EXECUTION_PARAMS` và `ExecutionContext` không chứa canary.
5. Kiểm tra `EXIT_MESSAGE` và `ERROR_MESSAGE` không chứa canary trong cả kịch bản thành công lẫn lỗi.
6. Tìm canary trong log/trace/event xuất ra khỏi tiến trình bằng công cụ kiểm thử có quyền phù hợp.
7. Kiểm tra Pod/Job spec không chứa token ở `args` hoặc `env[].value`; chỉ có tham chiếu `secretKeyRef`.
8. Giả lập lỗi HTTP có message chứa canary; xác nhận mã lỗi cuối đã được làm sạch và Task vẫn thất bại đúng.
9. Kiểm tra quyền xem metadata và Secret của ServiceAccount/người vận hành theo nguyên tắc tối thiểu.

### 12.1. SQL kiểm thử không hiển thị dữ liệu raw

Ví dụ cho **môi trường test**, dùng marker giả để đếm dấu vết trong Task arguments:

~~~sql
SELECT COUNT(*) AS task_parameter_canary_hits
FROM TASK_EXECUTION_PARAMS
WHERE TASK_PARAM LIKE '%SCT_CANARY_FAKE_TOKEN_FOR_TEST_20261124%';
~~~

Kỳ vọng **0 hàng chứa canary**. Không đưa mật khẩu thật vào truy vấn để “thử xem có rò rỉ không”: bản SQL query, database audit và console history lại có thể tạo **một đường rò rỉ mới**.

Đối với Spring Batch 5.x:

~~~sql
SELECT COUNT(*) AS job_parameter_canary_hits
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE PARAMETER_VALUE
      LIKE '%SCT_CANARY_FAKE_TOKEN_FOR_TEST_20261124%';
~~~

Tên cột khác nhau giữa các thế hệ Spring Batch; cần tra DDL đang triển khai. Đối với `ERROR_MESSAGE`, có thể thử đếm bằng một truy vấn tương tự ở `TASK_EXECUTION`, nhưng không in toàn bộ stack trace ra màn hình khi chưa kiểm soát dữ liệu.

### 12.2. Kịch bản thử nghiệm có lỗi

Cố tình giả lập một API client ném exception có nội dung canary:

~~~text
Remote response (test-only):
  "Authorization failed for token:
   SCT_CANARY_FAKE_TOKEN_FOR_TEST_20261124"
~~~

Nếu ứng dụng chỉ `throw ex;`, framework có thể ghi raw exception vào `ERROR_MESSAGE`. Với policy xử lý lỗi an toàn, ứng dụng phải **chuyển về mã lý do sạch** như `PARTNER_AUTH_REJECTED` để trạng thái Task vẫn thất bại nhưng không đưa token vào metadata.

**Đừng chỉ kiểm tra trường hợp chạy thành công.** Rò rỉ thường xuất hiện đúng khi timeout, HTTP 401/403, lỗi JDBC, lỗi parse dữ liệu hoặc một logger bị bật `DEBUG`.

## 13. Vận hành với rotation và thời gian sống của Task

Một lợi thế của Task hữu hạn là **mỗi lần chạy có thể lấy secret mới** khi khởi động. Tuy nhiên, điều này chỉ an toàn nếu cơ chế cấp secret có vòng đời đúng.

| Tình huống | Điều cần thiết kế |
| --- | --- |
| Token bị rotate giữa hai lịch | Lần chạy mới lấy phiên bản hiện tại, lần cũ được thu hồi theo quy trình |
| Token hết hạn giữa một Task dài | Client có refresh token/credential provider hoặc retry an toàn |
| Pod retry cùng Kubernetes Job | Pod mới lấy secret phù hợp, nhưng vẫn giữ **business key** của kỳ xử lý |
| Secret bị thu hồi do nghi rò rỉ | Chặn credential cũ tại bên cấp, kiểm tra các lượt đang chạy, cấp mới |
| Mounted Secret thay đổi khi Pod đang chạy | Ứng dụng cần đọc lại/refresh theo cơ chế hỗ trợ; không giả định tự đổi mọi chỗ |
| Bảo vệ DB password | Phân quyền TaskRepository, TLS tới DB, rotate và điều phối thay đổi kết nối |

Nếu quá trình rotate làm một lần nhập dữ liệu lỗi, cần xử lý retry/idempotency theo business key, **không dùng token cũ được lưu trong TaskExecution.arguments để “khôi phục nhanh”**. Metadata thực thi phải đủ để tái tạo **ý định nghiệp vụ**, không chứa credential để tái tạo **quyền truy cập**.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Token lộ trong `TASK_EXECUTION_PARAMS` | Truyền qua `--api-token` | Chuyển sang Secret/env/file, rotate credential bị lộ |
| Token không có trong Task arguments nhưng có ở Batch repository | Copy token vào `JobParameters` | Chỉ truyền business key; lấy token ở runtime |
| `ERROR_MESSAGE` chứa signed URL | Exception gốc chứa URL/token | Không lan truyền raw message; dùng reason code đã làm sạch |
| `EXIT_MESSAGE` chứa dữ liệu khách hàng | Listener ghi `failure.getMessage()` | Chỉ lưu trạng thái và mã lỗi an toàn |
| Log lộ `Authorization` header | HTTP client logging interceptor hoặc DEBUG thư viện | Tắt raw headers/bodies, dùng allowlist và redaction |
| Secrets được commit trong YAML | Dùng `env.value` hoặc manifest chứa base64 | Dùng Secret reference/secret manager; xử lý git history và rotate |
| Người đọc dashboard có thể xem token cũ | Metadata không được bảo vệ | Rà soát RBAC, DB grants, UI permissions, retention |
| Dùng `identifying=false` để “ẩn” Batch token | Hiểu sai JobParameters | Không đưa token vào JobParameters dưới bất kỳ cờ nào |
| Mật khẩu bị lộ qua Actuator | Bật `show-values=always` hoặc endpoint tùy biến không bảo vệ | Bật sanitization, giới hạn endpoint và authorization |
| Không xác định được root cause sau redaction | Chỉ còn reason code rất chung | Thêm correlation ID, diagnostic store hạn chế quyền và quy tắc hỗ trợ |
| Task `COMPLETED` dù API lỗi | Code catch exception rồi trả bình thường | Propagate lỗi đã làm sạch, kiểm tra exit code |
| Rotation xong nhưng log/backup vẫn chứa token cũ | Rò rỉ đã tồn tại trước khi sửa code | Thu hồi token, xử lý incident/retention/backup |

## 15. Bài tập thực hành

Một hệ thống chạy `daily-payment-import-task` qua Kubernetes CronJob. Tác vụ nhận `--business-date`, `--partner-id`, gọi API đối tác có **bearer token**, lưu bản ghi và chạy một Spring Batch Job. Nhóm vận hành muốn người hỗ trợ xem trạng thái trong dashboard nhưng **không thể xem credential**.

**Phần A — phân loại và sửa launch:**

1. Đánh dấu trường nào có thể lưu: `business-date`, `partner-id`, `partner-api-token`, `source-id`, `credential-ref`.
2. Viết lại Pod `args` để chỉ còn các tham số được phép; cấp token qua `secretKeyRef` hoặc mounted secret file.
3. Cấu hình `spring.datasource.password` qua biến môi trường mà không đưa password vào `--spring.datasource.password`.
4. Giải thích vì sao `TASK_EXECUTION_PARAMS` có thể chứa secret nếu launch qua CLI/SCDF dù ứng dụng không hề gọi `log.info`.

**Phần B — mã Java và metadata:**

5. Viết runner chỉ log `event, businessDate, outcome, acceptedCount`, không in `ApplicationArguments` hay `Environment`.
6. Chuyển lỗi `PartnerAuthenticationException` thành một **exception message an toàn** nhưng vẫn để Task thất bại.
7. Viết một `@FailedTask` listener ghi `exitMessage="FAILED; reason=PARTNER_AUTH_REJECTED"` hoặc reason code được phân loại; giải thích vì sao listener không tự sanitize `ERROR_MESSAGE`.
8. Tạo `JobParameters` cho Batch mà không chứa token; giải thích vì sao `identifying=false` không phải cơ chế che giấu.

**Phần C — kiểm chứng và vận hành:**

9. Dùng canary giả `SCT_CANARY_FAKE_TOKEN_FOR_TEST_20261124`, chạy success và error paths.
10. Kiểm tra TaskRepository, JobRepository, logs và traces không chứa canary; chỉ trả về **số lượng trùng** thay vì dump giá trị.
11. Thiết kế quyền đọc chỉ trạng thái cho người vận hành và quyền xem raw errors hạn chế cho nhóm sự cố.
12. Mô tả quy trình khi phát hiện token thật đã từng lọt vào TaskExecution: thu hồi/rotate, đánh giá scope, cleanup và điều tra backfill/backup.

**Tiêu chí đạt:** sau mọi trường hợp kiểm thử, không có credential trong argv, Task/Batch metadata, logs, metrics, traces và messages; tác vụ vẫn báo lỗi đúng qua exit code; quyền và quy trình ứng cứu được định nghĩa trước.

## 16. Tổng kết

1. **`TASK_EXECUTION_PARAMS` lưu arguments** nên **không truyền secrets qua CLI**, kể cả dưới tên property của Spring Boot hoặc qua launcher.
2. **`BATCH_JOB_EXECUTION_PARAMS` lưu JobParameters**; `identifying=false` không ẩn hoặc không ngăn lưu giá trị.
3. **`ERROR_MESSAGE` có thể chứa stack trace**, **`EXIT_MESSAGE` do listener đặt**. Cần bảo vệ thông tin ở **nguồn exception** và không sao chép raw message.
4. **Dùng arguments cho dữ liệu nghiệp vụ được phép truy vết**, dùng Secret/env/mounted file/secret manager cho credential, đồng thời hạn chế quyền đọc.
5. **Kubernetes Secret base64 không phải encryption**; bật encryption at rest, RBAC tối thiểu, không commit secret manifest, kiểm soát quyền debug và backup.
6. **Không log toàn bộ args, Environment, HTTP headers, bodies hoặc DTO config**. Dùng allowlist, reason code và correlation ID an toàn.
7. Bảo vệ Actuator, logs, traces, metrics và các hệ thống báo cáo metadata **độc lập**, không trông chờ một bộ lọc áp dụng cho mọi đường dữ liệu.
8. **Test bằng canary giả**, gồm đường chạy thành công, exception, retry và các hệ thống nhận log; không dùng secret thật làm chuỗi tìm kiếm.
9. Khi rò rỉ đã xảy ra, **rotate/thu hồi credential trước** và xử lý tất cả bản sao tồn tại trong repository, backups, logs và tickets theo incident response.

### Tài liệu tham khảo chính thức

- [Spring Cloud Task — Features và TaskRepository](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/reference/appendix-task-repository-schema.html)
- [Spring Batch — Metadata Schema và JobParameters](https://docs.spring.io/spring-batch/reference/schema-appendix.html)
- [Spring Boot — Actuator Endpoints và Sanitization](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Kubernetes — Good Practices for Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/)
- [Kubernetes — Using Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Kubernetes — Security Checklist](https://kubernetes.io/docs/concepts/security/security-checklist/)
