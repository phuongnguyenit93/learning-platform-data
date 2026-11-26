# Không ghi token vào log khi vận hành Spring Batch phân tán

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Nhận diện **access token, refresh token, API key, session cookie, mật khẩu, client secret, signed URL, chuỗi kết nối chứa credentials** và các bí mật khác không được đưa vào logs, traces, metrics hoặc metadata.
- Hiểu vì sao rủi ro tăng lên khi **multi-threaded step, parallel steps, partitioning, remote chunking/partitioning**, nhiều worker JVM và môi trường Kubernetes cùng chia sẻ log pipeline.
- Phân biệt dữ liệu có thể ghi để **quan sát job** (job name do ứng dụng kiểm soát, trạng thái, số bản ghi, thời lượng, mã lỗi đã phân loại) với **bí mật cần loại bỏ** khỏi mọi đường ghi nhận.
- Không đưa token vào `JobParameters`, `JobExecutionContext`, `StepExecutionContext`, partition manifest, broker payload hoặc command-line arguments.
- Sử dụng secret provider/workload identity và nguyên tắc **least privilege** để worker lấy credentials tại lúc cần, thay vì truyền token qua metadata và logs.
- Viết Java 17/Spring Batch 5.x với **SLF4J allowlist logging, listener an toàn, HTTP client không dump header/body** và quản lý MDC khi thread pool tái sử dụng thread.
- Hiểu giới hạn của **regex masking**: chỉ là lớp dự phòng, không thay việc ngăn ghi secrets từ nguồn.
- Thiết kế kiểm thử JUnit 5 với **secret giả**, capture log và kiểm tra exception, MDC, structured JSON, HTTP debug, retries và restart.
- Lập quy trình ứng phó khi token đã xuất hiện trong log: hạn chế truy cập, thu hồi/rotate, kiểm tra phạm vi lộ, bảo tồn bằng chứng và xử lý dữ liệu đã phát tán.
- Giữ được **khả năng chẩn đoán lỗi, throughput, retry/restart và business correctness** mà không đánh đổi an toàn thông tin.

## 1. Bài toán thực tế: một dòng log làm lộ toàn bộ quyền của worker

Module **SPRING_BATCH_SCALING_OPERATIONS** tập trung mở rộng Spring Batch cho dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình phân tán. Khi số worker tăng, số process, luồng, thông điệp và vị trí thu thập logs cũng tăng theo.

Giả sử một worker cần access token để gọi dịch vụ kiểm tra đơn hàng. Người phát triển thêm:

~~~java
// ANTI-PATTERN – tuyệt đối không dùng với token thật.
log.info("Starting worker, token={}", accessToken);
~~~

Trong production, dòng này không chỉ đi vào console của một process. Nó có thể lan qua:

~~~mermaid
flowchart LR
    W["Spring Batch worker"] --> O["stdout / log file"]
    O --> F["Log agent / sidecar"]
    F --> C["Centralized log collector"]
    C --> I["Index / dashboards / alerts"]
    C --> A["Archive / backup"]
    I --> X["Users, integrations, exports"]
~~~

Nếu token còn hiệu lực, bất kỳ ai đọc được dòng log có thể có cơ hội sử dụng quyền mà token đại diện. Việc token được che trên dashboard **không** chứng minh bản ghi gốc trong collector, archive hay alert đã được xóa hoặc bảo vệ.

**Quy tắc cốt lõi:** Không viết token vào log ngay từ nguồn. Thiết kế observability bằng **trường dữ liệu an toàn được cho phép**, không dump đối tượng rồi hy vọng lớp masking bắt được mọi định dạng bí mật.

## 2. “Token” trong bài này bao gồm những gì?

| Dạng dữ liệu | Ví dụ về cấu trúc, không phải giá trị thật | Vì sao nhạy cảm? |
| --- | --- | --- |
| OAuth access token | Header `Authorization: Bearer [REDACTED]` | Có thể cấp quyền API trong thời hạn hiệu lực |
| OAuth refresh token | Field `refresh_token` | Có thể dùng xin access token mới, thường nhạy cảm hơn |
| API key | `X-API-Key` / `api_key` | Quyền phụ thuộc scope/quota của khóa |
| Client secret | `client_secret` | Cho phép ứng dụng xác thực tới identity provider |
| Session cookie | `Cookie` / `Set-Cookie` | Có thể tái sử dụng phiên làm việc |
| Signed URL | URL có chữ ký/tham số truy cập | URL tự mang quyền, kể cả không có header Authorization |
| DB password / JDBC credentials | `spring.datasource.password` | Quyền truy cập database/JobRepository |
| Broker credentials | SASL password, connection secret | Quyền publish/consume queue/topic |
| Private key / certificate key | PEM private key, service account key | Có thể ký hoặc giả mạo danh tính workload |
| Secret-bearing request body | JSON chứa password, OTP, token | Có thể bị lộ qua body logging/exception |
| One-time setup token | Enrollment/bootstrap token | Dù ngắn hạn vẫn có thể bị sử dụng trong cửa sổ hiệu lực |

**Không dùng việc token “chỉ sống 5 phút” để biện minh cho logging.** Collector có thể lưu log trong nhiều tháng; một attacker nhận thông báo ngay vẫn có thể dùng token trong 5 phút đó.

### Phân loại theo mục đích

- **Secret:** tuyệt đối không ghi giá trị; có thể ghi *loại secret* hoặc một mã lỗi không tiết lộ nội dung.
- **Identifier hạn chế:** `jobExecutionId`, `partitionName`, tenant/reference ID có thể đủ dùng để điều tra nhưng phải kiểm tra phân quyền và chính sách dữ liệu. Không đưa các định danh có PII vào metric labels.
- **Dữ liệu quan sát cho phép:** tên step cố định của ứng dụng, `BatchStatus`, `ExitStatus` đã kiểm soát, số read/write/skip/rollback, mã HTTP, latency và error category.
- **Payload nghiệp vụ:** không đồng nghĩa token, nhưng vẫn có thể chứa thông tin cá nhân/bí mật; mặc định **không dump**.

### Không log token dưới dạng một phần, hash hay encode mà chưa có lý do nghiệp vụ

Đừng tự tiện ghi 8 ký tự đầu/cuối, Base64 hay SHA-256 của token rồi gọi là “an toàn”. Token prefix có thể tiết lộ cấu trúc; hash ổn định có thể trở thành **correlation identifier bí mật**, hỗ trợ dò khớp một tập token có entropy thấp. Nếu cần correlation, dùng **request ID/trace ID được tạo riêng**, không suy ra trực tiếp từ secret.

## 3. Threat model cho một job chạy trên nhiều máy

Khi một job phân tán, token có thể đi qua nhiều biên tin cậy:

~~~mermaid
flowchart TD
    A["Scheduler / JobLauncher"] --> B["JobRepository"]
    A --> M["Manager"]
    M --> Q["Broker / Middleware"]
    Q --> W1["Worker JVM A"]
    Q --> W2["Worker JVM B"]
    W1 --> S["External API / DB"]
    W2 --> S
    W1 --> L["Logs / traces / metrics"]
    W2 --> L
    M --> L
    Q --> DLQ["DLQ / retained messages"]
    B --> BK["Metadata backup"]
    L --> OBS["Central logging + archives"]
~~~

Các rủi ro chính:

1. **Nhiều nơi ghi:** một dòng debug ở worker có thể được sao chép vào log agent, exporter, tracing và alert.
2. **Không đồng nhất quyền đọc:** developer có thể không đọc được Secret Manager nhưng lại xem được log dashboard.
3. **Lưu dài hạn:** job chạy vài phút, còn metadata backups/log retention kéo dài.
4. **Remote payload:** manager gửi yêu cầu cho worker qua broker; bất kỳ secret nào trong payload có thể bị ghi khi retry hoặc DLQ.
5. **Crash/exception:** stack trace, exception message, framework debug hoặc dump có thể tiết lộ headers/query.
6. **Thread reuse:** MDC chứa token hoặc tenant nhạy cảm có thể còn trong thread sau khi worker xử lý item tiếp theo.
7. **Restart/rolling deploy:** metadata cũ và logs từ node cũ vẫn tồn tại dù đã rotate secret.

### Mục tiêu bảo vệ

- Worker chỉ nhận **quyền tối thiểu** để làm công việc.
- Token chỉ hiện diện trong runtime cần nó, không được gửi qua metadata/messaging nếu có cách lấy lại an toàn.
- Không có secret trong logs, metric labels, tracing baggage, task parameters, file paths, exception payload hoặc báo cáo vận hành.
- Khi token cần đổi, workers lấy token mới theo lifecycle và retry/restart vẫn đúng nghiệp vụ.

## 4. Những vị trí rò rỉ thường gặp trong Spring Batch

| Vị trí | Cách rò rỉ | Cách tránh |
| --- | --- | --- |
| `JobParameters` | Log/toString hoặc persisted `BATCH_JOB_EXECUTION_PARAMS` | Chỉ lưu snapshot ID/manifest key đã phân loại an toàn, không lưu token |
| `JobExecutionContext` | Serialize vào `BATCH_JOB_EXECUTION_CONTEXT`; debug dump | Lưu references an toàn, checkpoint tối thiểu |
| `StepExecutionContext` | Partition state/restart metadata; custom `toString` | Không đưa access token, API key, signed URL |
| `StepExecution` / `JobExecution` | Log cả object hoặc toàn bộ nested context | Log field allowlist: IDs/status/counters |
| `ItemReader` / `ItemProcessor` | Log input item/payload với embedded credentials | Log số lượng/loại lỗi, không dump item |
| `ItemWriter` | Log request body/SQL bindings | Chỉ log operation type, SQLSTATE, số affected rows |
| HTTP client | Header `Authorization`, `Cookie`, URL query, raw body | Tắt wiretap/raw logging; không log request object |
| JDBC/Hikari | URL có password/query, driver debug, bind values | Không ghi password vào JDBC URL, giới hạn SQL parameter logging |
| Remote partition request | Message headers/context có secret | Worker tự lấy token, message chỉ chứa safe identifiers |
| Remote chunk request | Item payload có secret hoặc full HTTP DTO | Sanitized contract, schema allowlist, encryption/retention |
| Broker retry/DLQ | Đưa raw message/headers vào troubleshooting log | Log message ID/type/status, hạn chế quyền xem payload |
| Listener | Log `Throwable`, `ExitStatus.exitDescription` hoặc context | Log mã lỗi đã chuẩn hóa, không in nguyên exception message |
| Structured logging/MDC | `MDC.put("token", ...)` rồi encoder ghi toàn bộ MDC | MDC chỉ chứa safe correlation fields, dọn sau scope |
| Tracing/APM | `http.request.header.authorization`, full URL, request body | Không capture secrets ở attributes/events/baggage |
| CI/test reports | JUnit failure in raw request/fixture | Token giả và sanitizer, không lưu fixture chứa secret thật |
| Kubernetes events | Command args/env dump, application startup output | Không truyền token trên command line, bảo vệ runtime config |

**“Không có log statement trực tiếp” chưa đồng nghĩa an toàn.** Một HTTP library ở `DEBUG/TRACE` có thể tự ghi Authorization header mà code ứng dụng không gọi logger.

## 5. Không đưa token vào JobParameters

`JobParameters` được dùng để định danh `JobInstance` và giữ tham số chạy job; trong JDBC `JobRepository`, chúng được **persist** để hỗ trợ audit và restart. Chúng cũng có thể xuất hiện trong logging/tostring/admin endpoints tùy ứng dụng.

~~~java
// ANTI-PATTERN: token bị biến thành tham số job được persist.
JobParameters unsafe = new JobParametersBuilder()
        .addString("accessToken", token, true)
        .addString("snapshotId", "snap-demo", true)
        .toJobParameters();
~~~

Ngay cả khi `identifying=false`, giá trị tham số vẫn có thể được lưu trong metadata. Thay flag không làm token an toàn.

### Tham số job nên chứa gì?

~~~java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters safeParameters = new JobParametersBuilder()
        .addString("snapshotId", "snapshot-demo-001", true)
        .addString("sourceType", "orders", false)
        .toJobParameters();
~~~

`snapshotId` và `sourceType` ở đây là giá trị giả, đã được phân loại **không nhạy cảm**. Trong production, ngay cả snapshot ID hoặc tên khách hàng có thể là dữ liệu hạn chế; cần áp chính sách dữ liệu. Token không nằm trong tham số job, cũng không được đưa vào một parameter tên khác như `trackingId`.

### Job API và command line

- Không truyền `--accessToken=...` qua command-line args khi khởi chạy Spring Boot; command line có thể hiện trong process listings/operational logs.
- Không dùng URL query `?access_token=...` cho endpoint launch job; URL có thể được access log/proxy lưu.
- Không để người dùng gửi “token ẩn” vào `JobParameters` dưới field tùy ý rồi log toàn bộ request.
- Dùng identity của scheduler/worker để cấp quyền khởi chạy và quyền gọi downstream, tách khỏi business parameters.

## 6. Không lưu token trong ExecutionContext hay partition manifest

`ExecutionContext` dùng lưu **state phục hồi**, không phải secret storage. Với PostgreSQL/JDBC JobRepository, state được serialize xuống bảng metadata và có thể tồn tại qua restart, export hoặc backup.

~~~java
// ANTI-PATTERN: sẽ bị persist và dễ dump trong debug.
stepExecution.getExecutionContext()
        .putString("bearerToken", accessToken);
~~~

Thiết kế an toàn hơn:

~~~java
// Lưu dữ liệu phi bí mật đủ để tái tạo công việc.
stepExecution.getExecutionContext()
        .putString("snapshotId", "snapshot-demo-001");
stepExecution.getExecutionContext()
        .putLong("startInclusive", 1001L);
stepExecution.getExecutionContext()
        .putLong("endExclusive", 2001L);
~~~

Các key `snapshotId`, `startInclusive`, `endExclusive` giúp restart/partition đúng mà không cần ghi token. Worker khi chạy lại sẽ xin credential mới từ hệ thống quản lý secrets.

### Remote partitioning

Nếu `Partitioner` tạo map context cho nhiều workers, chỉ gửi những thông tin cần phân công như **partition name, immutable input key/range, snapshot version**. Đừng gửi `Authorization`, `client_secret` hoặc signed URL trong `StepExecutionRequest`/payload mà manager có thể log hoặc broker giữ lại.

### Signed URL cũng là token

Một URL tới object storage có query signature và expiry chính là bearer credential. Nếu phải dùng URL có chữ ký, không lưu nguyên URL trong `ExecutionContext`/JobParameters và không log `URI.toString()`. Ưu tiên object key + identity của worker có quyền truy cập theo nguyên tắc tối thiểu. Nếu luồng công việc không thể thay cách cấp signed URL, áp dụng cơ chế lưu/chuyển riêng đã được đánh giá bảo mật, không coi “đó chỉ là đường dẫn” là đủ.

## 7. Secret provider tại worker: credential được cấp ở lúc sử dụng

Một thiết kế phổ biến:

~~~mermaid
sequenceDiagram
    participant J as JobRepository
    participant M as Manager
    participant W as Worker
    participant P as Secret Provider / Workload Identity
    participant A as Downstream API
    M->>J: Lưu snapshotId, partition state (không token)
    M->>W: Dispatch input key / partition ID
    W->>P: Xin token theo identity + scope
    P-->>W: Short-lived token (qua kênh an toàn)
    W->>A: Authorization header (không log)
    A-->>W: HTTP status
    W->>J: Update progress/checkpoint (không token)
~~~

Nguyên tắc:

- Mỗi worker có **workload identity** hoặc credential bootstrap được quản lý an toàn; manager không cần phân phát raw downstream token.
- Credential có **scope/TTL tối thiểu** cho những API mà worker cần.
- Provider hỗ trợ refresh/rotation và retry khi token hết hạn theo contract; lỗi auth 401 không được retry vô hạn bằng token đã hết hạn.
- Người phát triển không thêm secret vào log để “kiểm tra refresh hoạt động”; theo dõi **token source category/refresh outcome**, không theo dõi giá trị.
- Phân quyền Secret Manager/Vault/IAM phải ngăn worker A lấy token của tenant hoặc service mà A không có nhiệm vụ xử lý.

### Giao diện Java: không có khả năng log token ngoài ý muốn

~~~java
public interface AccessTokenProvider {
    // Trả về token cho scope đã được cho phép theo workload identity.
    String obtainForScope(String audience);
}
~~~

Giao diện đơn giản không tự biến String thành secret-safe. Java String có thể còn trong heap cho tới GC, có thể xuất hiện trong crash dump/debugger. **Biện pháp chính vẫn là access control, thời hạn ngắn, không persist và không log.** Không hứa rằng dùng `char[]` có thể xóa sạch mọi bản sao token vì HTTP client thường cần chuyển đổi nội bộ.

### Không nhét token vào Singleton mutable field để “tối ưu”

Một singleton có field `currentAccessToken` dùng chung cho nhiều tenants/scopes dễ xảy ra cross-tenant token mix khi multi-threaded/parallel steps. Secret provider nên quản lý cache an toàn theo scope/audience/workload và có expiration/refresh rõ. Không dùng `ThreadLocal` làm nơi lưu token lâu dài, đặc biệt khi thread pool tái sử dụng threads.

## 8. Viết SLF4J logs theo allowlist, không log cả object

**Allowlist logging** nghĩa là mỗi log event chỉ ghi những field đã được xét là an toàn. Không biến đối tượng Java thành chuỗi rồi mong rằng tất cả nested fields đã được mask.

~~~java
// ANTI-PATTERN: request hoặc jobExecution có thể chứa token.
log.debug("HTTP request={}", request);
log.info("Job execution={}", jobExecution);
log.warn("Failed context={}", stepExecution.getExecutionContext());
~~~

Ví dụ tốt hơn:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class SafeBatchEvents {

    private static final Logger LOG =
            LoggerFactory.getLogger(SafeBatchEvents.class);

    public void recordStepCompleted(
            String stableStepType,
            long readCount,
            long writeCount,
            String normalizedStatus) {

        // stableStepType và normalizedStatus phải được
        // lấy từ danh mục cố định, không phải text từ input.
        LOG.info(
                "event=batch_step_completed step_type={} " +
                "status={} read_count={} write_count={}",
                stableStepType,
                normalizedStatus,
                readCount,
                writeCount);
    }

    public void recordDownstreamCall(
            String fixedServiceName,
            String fixedOperation,
            int httpStatus,
            long elapsedMillis) {

        LOG.info(
                "event=downstream_call service={} operation={} " +
                "http_status={} elapsed_ms={}",
                fixedServiceName,
                fixedOperation,
                httpStatus,
                elapsedMillis);
    }
}
~~~

### Cần xác minh cả *giá trị* của field allowlist

Field name `operation` nghe an toàn nhưng nếu giá trị được lấy từ full URL hoặc request body thì vẫn có thể lộ token. Chỉ dùng tên service/operation **đã kiểm soát** như `orders-api`/`fetchSnapshot`; không truyền raw URL, SQL, request headers, response body hoặc exception message.

### Parameterized logging chưa phải sanitizer

`log.info("token={}", token)` vẫn lộ token dù sử dụng placeholder `{}`. Placeholder giúp trì hoãn format, **không** có nghĩa logger tự redact tham số.

## 9. Không log exception message, stack trace một cách mù quáng

Các exception từ HTTP client, JDBC driver, identity provider và serializer có thể chứa:

- Request URL có signed query string.
- Full response body có field `access_token` hoặc `client_secret`.
- Header `Authorization`/`Cookie` nếu middleware đưa chúng vào exception.
- JDBC URL chứa username/password hoặc SQL literal có secret.
- Các thông tin đầu vào do người dùng kiểm soát, có thể tự chứa secret.

~~~java
// ANTI-PATTERN: e.getMessage() hoặc Throwable toString
// có thể chứa request/URL/header/data chưa được sanitize.
log.error("Call failed: {}", exception.getMessage());
log.error("Call failed", exception);
~~~

Thay bằng **phân loại lỗi an toàn** rồi ghi những field đã duyệt:

~~~java
import java.io.IOException;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.CannotAcquireLockException;

public final class SafeFailureReporter {

    private static final Logger LOG =
            LoggerFactory.getLogger(SafeFailureReporter.class);

    public static String category(Throwable failure) {
        if (failure instanceof CannotAcquireLockException) {
            return "DB_LOCK";
        }
        if (failure instanceof IOException) {
            return "DOWNSTREAM_IO";
        }
        if (failure instanceof IllegalArgumentException) {
            return "INVALID_INPUT";
        }
        return "UNCLASSIFIED";
    }

    public void record(String fixedOperation, Throwable failure) {
        LOG.warn("event=step_failure operation={} error_category={}",
                fixedOperation, category(failure));
        // Không truyền failure, failure.getMessage() hay stack trace
        // vào logging call ở đường nhạy cảm.
    }
}
~~~

Đây là một cách **giảm rủi ro logging**, không phải lý do để che thông tin lỗi cần điều tra. Có thể giữ trace ID, error code, HTTP status, DB SQLSTATE (sau khi review) và tham chiếu tới hệ thống audit có quyền phù hợp; raw exception detail chỉ được thu thập qua cơ chế phân quyền/retention chuyên biệt nếu chính sách bảo mật cho phép, với secret filtering đã kiểm tra.

### Một bẫy của log framework

`log.warn("Failed {}", safeId, exception)` ở SLF4J có thể nhận đối số Throwable cuối và ghi stack trace, kể cả khi format string chỉ có một placeholder. Test phải xác minh **log event không chứa Throwable proxy**, không chỉ kiểm tra chuỗi formatted message.

## 10. HTTP client: header Authorization chỉ đi tới downstream, không đi vào logger

Ví dụ Java 17 `java.net.http.HttpClient` dùng token để gọi API nhưng chỉ log mã HTTP, thời gian và tên operation cố định.

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrdersApiClient {

    private static final Logger LOG =
            LoggerFactory.getLogger(OrdersApiClient.class);

    private final HttpClient httpClient;
    private final URI endpoint;
    private final AccessTokenProvider tokens;

    public OrdersApiClient(
            HttpClient httpClient,
            URI endpoint,
            AccessTokenProvider tokens) {
        this.httpClient = httpClient;
        this.endpoint = endpoint;
        this.tokens = tokens;
    }

    public int postOrderBatch(String jsonPayload)
            throws IOException, InterruptedException {

        String accessToken = tokens.obtainForScope("orders.write");

        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(Duration.ofSeconds(20))
                .header("Authorization", "Bearer " + accessToken)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(jsonPayload))
                .build();

        long started = System.nanoTime();
        try {
            var response = httpClient.send(
                    request, HttpResponse.BodyHandlers.discarding());

            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);

            LOG.info(
                    "event=orders_api_call service=orders-api " +
                    "operation=postBatch status={} elapsed_ms={}",
                    response.statusCode(),
                    elapsedMs);

            return response.statusCode();
        } catch (IOException failure) {
            LOG.warn(
                    "event=orders_api_failure service=orders-api " +
                    "error_category=IO_FAILURE");
            throw failure;
        }
    }
}
~~~

**Quan trọng:** snippet này minh họa **không ghi token** trong application log. Nó chưa xử lý retries, idempotency, rate limiting, authentication refresh hay HTTP status 429/503; đó là logic phải thiết kế riêng theo mục tiêu batch. Token vẫn hiện diện tạm trong header runtime, nhưng không được log hoặc persist.

### URL và header cũng phải được kiểm soát

- Không log `endpoint.toString()` nếu endpoint có query, credential hoặc path chứa bí mật.
- Không log nguyên `HttpRequest`, `HttpResponse` hoặc headers vì chúng có thể chứa Authorization/Cookie.
- Không bật HTTP wire logging trên production để “debug retry nhanh hơn”.
- Nếu cần phân biệt endpoint, ghi **fixed route name** hoặc operation enum, không ghi full URL.
- Không log body vì JSON có thể chứa credentials và dữ liệu khách hàng.
- Nếu thư viện HTTP bên dưới tự log, cấu hình của thư viện phải được kiểm tra riêng; việc application chỉ ghi status **không chặn** wiretap ngoài ý muốn.

## 11. MDC và thread pool: tránh lộ dữ liệu qua luồng được tái sử dụng

`MDC` (Mapped Diagnostic Context) của SLF4J giúp thêm correlation fields vào log của một thread. Khi Spring Batch dùng `TaskExecutor`, pool có thể tái sử dụng cùng thread cho nhiều chunk/partition/step. Nếu không cleanup, MDC từ công việc trước có thể xuất hiện trong log công việc sau.

~~~java
// ANTI-PATTERN.
MDC.put("authorization", accessToken);
MDC.put("tenant", rawTenantName);
processChunk();
// Thiếu cleanup trong finally.
~~~

Ngay cả khi encoder không hiển thị MDC hiện tại, token nằm trong MDC có thể được một appender/tracer khác serialize sau này. **Không bao giờ lưu token vào MDC, baggage hoặc ThreadLocal để phục vụ logging.**

### Gắn correlation ID an toàn và luôn khôi phục state

~~~java
import java.util.Objects;
import org.slf4j.MDC;

public final class BatchMdcScope {

    private static final String JOB_EXECUTION_ID =
            "batch.job_execution_id";

    private BatchMdcScope() {}

    public static void withJobExecutionId(
            long jobExecutionId, Runnable action) {

        Objects.requireNonNull(action);

        String previous = MDC.get(JOB_EXECUTION_ID);
        try {
            // ID số nội bộ phải được chính sách observability cho phép.
            MDC.put(JOB_EXECUTION_ID,
                    Long.toString(jobExecutionId));
            action.run();
        } finally {
            if (previous == null) {
                MDC.remove(JOB_EXECUTION_ID);
            } else {
                MDC.put(JOB_EXECUTION_ID, previous);
            }
        }
    }
}
~~~

Đoạn này khôi phục key mà nó đã sửa thay vì `MDC.clear()` toàn bộ context, tránh xóa correlation fields của caller khác. `MDC.clear()` có thể phù hợp ở ranh giới do ứng dụng toàn quyền sở hữu, nhưng không nên gọi tùy tiện khi thư viện khác quản lý trace fields.

### Với TaskExecutor và thread switching

- `MDC` thường gắn với thread; async work không được bảo đảm tự nhận đúng context của caller.
- Nếu có `TaskDecorator` để copy MDC, phải **lọc chỉ những key an toàn**, và cleanup sau khi task kết thúc.
- Không copy nguyên `MDC.getCopyOfContextMap()` khi map có thể chứa user data hoặc token.
- Khi remote worker là JVM khác, dùng **correlation ID an toàn** trong message; không serialise MDC gốc.
- Test một executor có đúng một thread: chạy task A, sau đó task B và assert key của A không bị rò sang B.

### Tại sao không log toàn bộ MDC?

Cấu hình log format với `%X` hoặc JSON encoder tự động đưa tất cả MDC fields có thể làm lộ một key mới được đội khác thêm vào. Ưu tiên các key allowlist cụ thể như `%X{batch.job_execution_id}` nếu đã duyệt, và kiểm thử config với synthetic sentinel.

## 12. Spring Batch StepExecutionListener: log trạng thái, không log context

Một listener thường được dùng để theo dõi thời gian và kết quả của step. Đừng log nguyên `StepExecution` hoặc `JobExecution` vì nested state, exception/exit descriptions và custom `toString` có thể chứa thông tin nhạy cảm.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public final class SafeStepExecutionListener
        implements StepExecutionListener {

    private static final Logger LOG =
            LoggerFactory.getLogger(SafeStepExecutionListener.class);

    @Override
    public void beforeStep(StepExecution execution) {
        LOG.info(
                "event=batch_step_started step_name={} step_id={}",
                execution.getStepName(),
                execution.getId());
    }

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        LOG.info(
                "event=batch_step_finished step_name={} " +
                "step_id={} status={} read_count={} " +
                "write_count={} skip_count={} rollback_count={}",
                execution.getStepName(),
                execution.getId(),
                execution.getStatus().name(),
                execution.getReadCount(),
                execution.getWriteCount(),
                execution.getSkipCount(),
                execution.getRollbackCount());

        // Không thay đổi ExitStatus do step/framework đã xác định.
        return null;
    }
}
~~~

`StepExecutionListener.afterStep` có thể trả `null` để không bổ sung `ExitStatus` mới. Đây là ví dụ API Spring Batch 5.x; khi wiring thực tế phải đăng ký listener với step. `step_name` chỉ được xem là an toàn khi do cấu hình ứng dụng kiểm soát, không tạo trực tiếp bằng input nhạy cảm.

### Những field không nên ghi từ StepExecution

- `execution.getExecutionContext().toString()`: có state reader/partition và có thể bị đưa nhầm secret.
- `execution.getJobExecution().getJobParameters().toString()`: metadata có thể chứa tham số nhạy cảm do ai đó đặt trước đó.
- `execution.getFailureExceptions()`: Throwable có thể chứa header/body/URL khi framework/driver tạo exception.
- `execution.getExitStatus().getExitDescription()`: mô tả lỗi có thể chứa stack trace hoặc text từ exception.
- DTO nguyên bản của item lỗi trong `SkipListener`: có thể chứa token lẫn payload nghiệp vụ.

Thay vào đó, log **mã lỗi đã phân loại** và các counts; nếu cần điều tra chi tiết, dùng trace ID và nguồn thông tin được bảo vệ phù hợp.

## 13. Cấu hình logging: không bật wiretap hoặc toàn bộ MDC

Cấu hình logging phải được xem xét ở **mức ứng dụng, thư viện và hạ tầng**. Một ví dụ Logback giản lược giúp hạn chế đường xuất hiện Throwable và MDC ngoài ý muốn:

~~~xml
<configuration>
  <appender name="SAFE_CONSOLE"
            class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>
        %d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level
        [%thread] %logger{36} - %msg%n%nopex
      </pattern>
    </encoder>
  </appender>

  <logger name="org.apache.hc.client5.http.wire"
          level="OFF"/>
  <logger name="reactor.netty.http.client"
          level="WARN"/>
  <logger name="org.springframework.web.reactive.function.client"
          level="WARN"/>
  <logger name="org.springframework.jdbc.core"
          level="WARN"/>

  <root level="INFO">
    <appender-ref ref="SAFE_CONSOLE"/>
  </root>
</configuration>
~~~

Đây chỉ là **mẫu giảm rủi ro**, không phải cấu hình an toàn cho mọi appender/version. `%nopex` ngăn tự động bổ sung Throwable stack trace của Logback pattern này; **không redact `%msg`**. Một thông điệp tự ghi token trong `msg` vẫn sẽ lộ. Không thay tất cả exception logs bằng cách tắt stack trace vĩnh viễn nếu hệ thống cần forensic; thay bằng error taxonomy, correlation và cơ chế log chi tiết **được bảo vệ riêng** theo chính sách.

### Checklist cấu hình thực tế

1. Xác định logger categories của HTTP client thực đang sử dụng (Apache HttpClient 4/5, Reactor Netty, JDK HttpClient, OkHttp...), không giả định bốn logger ví dụ là đầy đủ.
2. Tắt wire logging hoặc bảo đảm cấu hình không thể dump raw Authorization/Cookie/query/body.
3. Không bật `TRACE` tràn lan cho `org.springframework.security`, JDBC parameter binding, Spring Integration broker adapters hoặc HTTP codecs.
4. Với JSON encoder, kiểm soát các field `mdc`, `arguments`, `exception`, `stack_trace`; nhiều encoder có behavior khác pattern console.
5. Kiểm tra cả stdout, file appenders, async appenders và remote appender.
6. Nếu có APM agent tự capture headers/bodies, cấu hình **denylist attributes** ở agent/exporter và test; app logging sạch không đảm bảo tracer sạch.
7. Bảo vệ endpoint cấu hình/Actuator; không tạo một admin endpoint “dump config để debug” chứa secrets.
8. Review thay đổi logging config trong CI/CD, đặc biệt khi chuyển INFO sang DEBUG lúc incident.

### Không coi regex mask là hàng rào duy nhất

Nếu vẫn dùng masking converter/filter để giảm tác hại, nó phải được kiểm thử với nhiều case. Nhưng không thể chứng minh lọc hết mọi secret có thể tồn tại khi dữ liệu bị chia thành nhiều trường, encode, truncate hoặc xuất dưới dạng khác.

## 14. JDBC, SQL và connection URL: tránh secrets trong statement logs

Spring Batch có thể dùng JDBC cho reader, writer và `JobRepository`. Những nơi dễ lộ credentials:

~~~java
// ANTI-PATTERN: URL chứa secret dưới dạng query.
String jdbcUrlWithPassword =
        "jdbc:postgresql://db.internal:5432/orders" +
        "?user=some-user&password=not-a-real-password";

// ANTI-PATTERN: ghi nguyên URL hoặc exception có thể lộ secret.
log.info("Connecting to {}", jdbcUrlWithPassword);
~~~

Ví dụ an toàn về cấu hình theo vai trò (giá trị password **không** được hardcode vào bài cấu hình thật):

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: batch_reader
    password: "[provided securely at runtime]"
    hikari:
      pool-name: orders-source
      maximum-pool-size: 8

logging:
  level:
    org.springframework.jdbc.core: WARN
~~~

`"[provided securely at runtime]"` là **placeholder mô tả**, không phải credential hoặc cách inject thực tế. Production dùng secret injection được hỗ trợ, workload identity/secret manager hoặc cơ chế cung cấp credentials phù hợp. Environment variables cũng có rủi ro hiển thị qua process configuration, dump hoặc diagnostics và phải được bảo vệ.

### Cẩn trọng với SQL bind values

Một câu SQL parameterized giúp tránh SQL injection, nhưng `TRACE` của JDBC framework/driver có thể hiển thị **bound parameter values**. Nếu một bind parameter là token, email, tenant ID hoặc payload nhạy cảm thì giá trị có thể xuất hiện trong logs dù SQL có dấu `?`.

- Không log `PreparedStatement.toString()` hoặc full SQL kèm literal values.
- Không biến token thành query parameter hoặc JDBC URL.
- Không viết `log.debug("params={}", jdbcParams)` cho map chứa secrets.
- Kiểm tra datasource proxy/P6Spy/log4jdbc/SQL observability plugin nếu được cài trong môi trường; chúng có thể ghi SQL và binding tự động.
- Hikari metrics như active/idle/pending **không cần** username/password và là lựa chọn tốt hơn để điều tra connection pressure.

### Spring Batch metadata không phải password vault

`BATCH_JOB_EXECUTION_PARAMS` và các context tables có thể được backup, truy vấn bởi vận hành hoặc xuất sang môi trường QA. Mã hóa database at rest có ích nhưng **không làm token trở nên an toàn để lưu trong metadata**, vì ứng dụng/DB user/diagnostic có thể đọc plaintext theo đường ứng dụng.

## 15. Remote partitioning và remote chunking: đừng đưa secrets qua message

Trong distributed Spring Batch, hai mô hình phổ biến có khác nhau:

- **Remote partitioning:** manager giao các `StepExecution`/partition input keys cho worker, worker thường tự đọc và xử lý data.
- **Remote chunking:** manager đọc items và gửi chunk requests, worker xử lý/ghi rồi trả reply.

Cả hai cần cơ chế auth tới DB/API/broker, nhưng credentials **không nên nằm trong message payload** chỉ vì worker đang ở process khác.

### Hợp đồng message theo allowlist

~~~json
{
  "messageType": "PARTITION_WORK_REQUEST",
  "jobExecutionId": 700,
  "stepExecutionId": 704,
  "partitionName": "workerStep:partition0004",
  "snapshotRef": "snapshot-demo-001",
  "inputRange": {
    "startInclusive": 4001,
    "endExclusive": 5001
  }
}
~~~

Đây là **JSON minh họa**, không nhất thiết là wire format mặc định của Spring Batch. Các field cũng cần được phân loại trước khi log; ví dụ snapshotRef có thể là dữ liệu nhạy cảm ở một domain khác. Không thêm `accessToken`, `Authorization`, signed URL hay secret manager bearer key.

### Nếu worker cần credential, ai cung cấp?

Worker dùng workload identity/secret provider với policy quyền riêng. Không dùng “manager gọi Secret Manager một lần rồi phát cùng token cho tất cả worker” trừ khi có kiến trúc quản trị secrets đã được đánh giá, có lifecycle/rotation/audit phù hợp; ngay cả vậy **không được log token**.

### Broker DLQ và retry

Một message bị retry có thể được ghi trong broker DLQ, inspect tools, alert hoặc diagnostics. Nếu payload có token, chỉ một exception dẫn tới DLQ cũng đủ lưu token lâu dài. Bảo mật phải áp ở **message schema**, không chỉ log line.

~~~java
// ANTI-PATTERN: listener log toàn bộ message sau lỗi.
log.error("Remote work failed, message={}", remoteMessage);
~~~

Thay bằng message type, correlation ID an toàn, attempt count đã chuẩn hóa và failure category. Không đưa full `MessageHeaders` hoặc broker properties vào log; chúng có thể chứa authentication, tracing baggage hoặc user-defined headers.

### Broker credentials cũng phải được bảo vệ

Không ghi SASL password, broker connection strings có secret, certificate private key hoặc authentication handshake trong log. TLS bảo vệ đường truyền nhưng không bảo vệ plaintext đã bị ghi ở manager/worker/collector.

## 16. Trace và metrics: token có thể lộ ngay cả khi không dùng log.info

Observability thường có ba kênh:

| Kênh | Giá trị hữu ích | Không được gắn |
| --- | --- | --- |
| **Logs** | Event type, step type, HTTP status, error category | Token, raw headers/body, signed URL, full exception nhạy cảm |
| **Metrics** | Chunk duration, retry/rollback count, queue depth, Hikari pending | Token, API key, customer email hoặc item ID làm label |
| **Traces** | Span kind, service/operation, latency, retry spans | Authorization/Cookie headers, full URL có secret, request/response body |
| **Baggage/MDC** | Safe correlation ID hoặc trace ID | Token, refresh token, credentials, PII không được phép |

### Metrics: dữ liệu nhạy cảm và cardinality

Không dùng:

~~~java
// ANTI-PATTERN: mỗi token sinh một time series riêng!
Counter.builder("batch.api.calls")
        .tag("token", accessToken)
        .register(registry)
        .increment();
~~~

Metric backend có thể lưu labels lâu hơn log retention; token trở thành một phần **index**. Dùng labels có số giá trị giới hạn:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public final class SafeBatchMetrics {

    public SafeBatchMetrics(MeterRegistry registry) {
        Counter.builder("batch.api.calls")
                .tag("service", "orders-api")
                .tag("operation", "submit")
                .register(registry)
                .increment();
    }
}
~~~

Code là ví dụ về label an toàn; trong thực tế nên lưu Counter một lần và increment lúc có call, không khởi tạo meter trong mỗi request. Đặt `jobExecutionId`/`recordId` vào labels cũng có thể gây cardinality cao dù không phải secret.

### Tracing

- Chỉ ghi span name như `orders-api POST`, không full `http.url` nếu URL mang signed query.
- Tắt capture request/response body và các header nhạy cảm tại instrumentation/agent.
- Không gắn token vào baggage: baggage có thể được truyền qua HTTP tới nhiều service và xuất hiện ở logs.
- Một span attribute “masked” ở exporter không đảm bảo **local span events/logs và storage trước exporter** không từng chứa secret.
- Khi cần đối chiếu request, dùng trace ID độc lập với token.

## 17. Regex masking có thể giúp giảm thiệt hại, nhưng không đủ

Một filter có thể thay chuỗi giống `Bearer xyz` bằng `Bearer [REDACTED]`. Đây là **defense in depth**; không nên dùng như biện pháp chính.

### Những cách token có thể vượt mask

1. Header ghi là `authorization`, `AUTHORIZATION`, hoặc custom `X-Auth`.
2. Token nằm ở JSON field `credential`/`session`/`refreshToken` thay vì `access_token`.
3. Token ở query string, URL-encoded hoặc Base64 encoded.
4. Logger chỉ ghi một đoạn token, phần còn lại trong một field khác.
5. Token nằm trong nested object `toString` hoặc stack trace.
6. Log shipper/tracer ghi bản raw **trước** khi masking filter chạy.
7. Một thành phần dùng JSON encoder mà filter chỉ hỗ trợ text pattern.
8. JWT có line breaks/truncation hoặc service-specific token format.
9. Header `Cookie` chứa nhiều session tokens trong cùng một giá trị.
10. Retry lỗi làm raw request bị ghi trong một thư viện khác, nằm ngoài filter của app.

### Thứ tự phòng vệ

~~~text
1. Không đưa secret vào JobParameters/ExecutionContext/message.
2. Không ghi request/response/exception object nguyên bản.
3. Chỉ log fields allowlist ở mã ứng dụng.
4. Tắt thư viện wire logs/tracing sensitive capture.
5. Redaction/masking như hàng rào dự phòng.
6. Giới hạn quyền truy cập/retention/exports.
7. Dùng synthetic secret tests trên toàn log pipeline.
8. Rotate/revoke kịp thời nếu lộ.
~~~

### Khi bắt buộc dùng masking

- Review pattern cùng threat model, test cả chữ hoa/thường và encoding.
- Test structured fields trước khi serialize nếu logger hỗ trợ.
- Không ghi giá trị secret vào masking diagnostics để “biết đã mask gì”.
- Đánh giá memory/CPU overhead khi logging nhiều threads.
- Dùng pattern đã biên dịch immutable hoặc implementation thread-safe; tránh global mutable `lastSeenToken` có thể gây rò giữa các threads.
- Đừng khẳng định **masking 100%** vì không thể bao quát mọi secret format và mọi logger mà không giới hạn nguồn dữ liệu.

## 18. Logging contract cho chunk, retry và restart

Một job scaling cần đủ dữ liệu để debug throughput, retry và restart **mà không log tokens**.

| Event | Trường nên ghi | Không nên ghi |
| --- | --- | --- |
| Job started | job type, safe job execution ID, snapshot category | JobParameters toàn bộ, token, raw launch request |
| Step started | step type, step execution ID, worker role | ExecutionContext toàn bộ, reader credential |
| Chunk committed | step ID, item count, duration, retry count | Raw items, SQL bound values, auth header |
| Retry attempt | error category, attempt index, backoff ms, dependency type | Exception message/stack chưa review, raw API response |
| Worker redispatch | partition name an toàn, owner epoch, delivery number | Broker message body/headers chứa secret |
| API call | fixed operation, status code, duration | Full URL/query, Authorization, Cookie, request body |
| Job failed | JobExecution ID, status, normalized error code | `Throwable.toString`, ExitDescription raw, secrets từ context |
| Job restarted | same job identity, recovery outcome, checkpoint category | Serialized context, key/secret provider response |
| Credential refreshed | audience category, success/fail, refresh latency | Old/new token, refresh token, token hash |
| Reconciliation | expected/actual counts, mismatch count | Danh sách payload nhạy cảm vào global log |

### Mẫu log hữu ích

~~~text
INFO event=batch_step_finished step_type=orders-import status=COMPLETED read_count=250000 write_count=250000 rollback_count=0

WARN event=downstream_call_failure service=orders-api operation=postBatch error_category=HTTP_503 attempt=2

INFO event=worker_credential_refresh audience=orders.write result=SUCCESS elapsed_ms=75
~~~

Những dòng trên không chứa secret thật. Trong production, cần xem xét cả việc những identifier/metric nào được phép chia sẻ giữa tenants và logs aggregator.

## 19. Unit test: dùng token giả và capture log để kiểm chứng

Không cần và **không được dùng token production thật** để kiểm tra logger. Thay bằng một chuỗi sentinel rõ ràng **không có quyền truy cập**, cố tình đặt nó trong exception message hoặc fixture; test phải xác nhận logger không để lộ chuỗi này.

Ví dụ JUnit 5 với Logback `ListAppender` (cần `logback-classic` trong test runtime):

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.IOException;
import java.util.stream.Collectors;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

class SafeFailureReporterTest {

    // Giá trị giả, không có hiệu lực xác thực.
    private static final String SYNTHETIC_TOKEN =
            "SYNTHETIC-DO-NOT-LOG-TEST-ONLY-7fa2";

    @Test
    void doesNotExposeSecretInsideExceptionMessage() {
        Logger logger = (Logger) LoggerFactory.getLogger(
                SafeFailureReporter.class);

        var captured = new ListAppender<ILoggingEvent>();
        captured.start();
        logger.addAppender(captured);

        try {
            Throwable failure = new IOException(
                    "Authorization: Bearer " + SYNTHETIC_TOKEN);

            new SafeFailureReporter().record(
                    "orders.submit", failure);

            assertFalse(captured.list.isEmpty());

            String messages = captured.list.stream()
                    .map(ILoggingEvent::getFormattedMessage)
                    .collect(Collectors.joining("\n"));

            assertFalse(messages.contains(SYNTHETIC_TOKEN));
            assertTrue(messages.contains(
                    "error_category=DOWNSTREAM_IO"));

            // Chặn trường hợp Throwable được gắn riêng vào event
            // rồi bị JSON encoder hoặc appender khác ghi ra.
            assertTrue(captured.list.stream()
                    .allMatch(e -> e.getThrowableProxy() == null));
        } finally {
            logger.detachAppender(captured);
            captured.stop();
        }
    }
}
~~~

**Ý nghĩa test:** nó chứng minh đường gọi `SafeFailureReporter.record(...)` không ghi raw exception message hoặc gắn Throwable vào **Logback event trong phạm vi unit test**. Nó **không chứng minh** tất cả logging của HTTP client, Spring Batch, broker, OpenTelemetry hay log collector đã an toàn. Những lớp đó cần test tích hợp riêng.

### Mở rộng fixture với nhiều kiểu bí mật

Một test suite có thể tạo các **sentinel không thật** ở các vị trí:

- `Authorization: Bearer SYNTHETIC...`, refresh token field, API key header.
- Cookie hoặc `Set-Cookie`.
- Signed query string/URL trong exception message.
- JSON body nested field `credentials.accessToken`.
- JDBC URL có `password=SYNTHETIC...`.
- Metadata `ExecutionContext` bị code thử nghiệm vô ý chứa sentinel.
- Broker request/reply/DLQ message chứa sentinel.
- MDC/baggage có field bị cấm.

Bằng chứng cần bao gồm bản ghi **trước và sau serializer/appender/collector**, không chỉ formatted message tại Java logger, bởi vì một encoder có thể tự nối exception, arguments hoặc MDC vào JSON.

### Kiểm tra allowlist thay vì chặn một chuỗi duy nhất

Nếu chỉ assert thiếu đúng một sentinel, code khác vẫn có thể lộ token thật ở định dạng khác. Kết hợp kiểm thử:

1. **Nguồn:** các API logging không nhận raw secret-bearing objects.
2. **Schema:** sự kiện cho phép có field nào, field nào tuyệt đối cấm.
3. **Dữ liệu:** sentinel không xuất hiện trên tất cả sinks.
4. **Cấu hình:** wiretap/SQL bind logging/tracing sensitive capture bị tắt hoặc có redaction đã test.
5. **Quyền:** người xem dashboard/log archive không đương nhiên có quyền xem credentials.

## 20. Kiểm thử MDC không rò giữa hai tác vụ trên cùng thread

Spring Batch nhiều thread dễ gặp vấn đề **context cross-contamination** vì executor tái sử dụng worker thread. Unit test có thể cho hai tasks chạy tuần tự trên **một thread thực**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;

class BatchMdcScopeTest {

    @Test
    void cleansCorrelationKeyOnReusedThread() throws Exception {
        var executor = Executors.newSingleThreadExecutor();
        try {
            var first = executor.submit(() -> {
                BatchMdcScope.withJobExecutionId(101L, () ->
                    assertEquals("101",
                        MDC.get("batch.job_execution_id")));

                // Sau khi scope kết thúc, key do scope thêm
                // không còn bị giữ trong thread của executor.
                return MDC.get("batch.job_execution_id");
            });

            assertNull(first.get(5, TimeUnit.SECONDS));

            var second = executor.submit(() ->
                    MDC.get("batch.job_execution_id"));

            assertNull(second.get(5, TimeUnit.SECONDS));
        } finally {
            executor.shutdownNow();
            assertTrue(executor.awaitTermination(
                    10, TimeUnit.SECONDS));
        }
    }
}
~~~

**Giới hạn:** test này kiểm tra một key correlation an toàn. Nếu application từng đặt raw token vào MDC của worker, phải **sửa nguồn tạo key đó**; việc `BatchMdcScope` xóa job ID không tự xóa một field bí mật do component khác tạo.

### Thử cả exceptional path

Một task cố tình ném `IllegalStateException` bên trong `withJobExecutionId(...)`. Dù task thất bại, khối `finally` vẫn phải khôi phục MDC; thread sau không được thấy ID của công việc trước. Với structured encoder, cần test JSON output có đúng allowlist fields.

### Remote worker không kế thừa MDC như object Java

Một worker trên node khác không thể dùng MDC của manager để suy ra token hoặc quyền. Truyền một **safe correlation ID** trong message contract; ở worker, nhập vào MDC theo whitelist, dọn trong `finally` và không tự động copy mọi message headers vào MDC.

## 21. Integration test toàn pipeline: từ lỗi tới log archive

Unit test ở ứng dụng là lớp đầu. Để nói “không ghi token vào log” ở mức vận hành, cần kiểm tra một đường đi thực tế:

~~~mermaid
flowchart LR
    T["Synthetic token fixture"] --> J["Job + Step listener"]
    J --> H["HTTP/JDBC/Broker libraries"]
    H --> L["Logback encoder / appender"]
    L --> A["Log agent / collector"]
    A --> I["Index + dashboards + alerts"]
    I --> C["Sentinel scan + schema assertion"]
~~~

### Kịch bản end-to-end gợi ý

1. Khởi tạo **token giả không thể dùng để xác thực** và test API/server giả trong môi trường cô lập.
2. Job chạy một Step gửi request bằng HTTP client thật với header Authorization chứa sentinel.
3. Server giả trả HTTP 503 và một response body cố tình nhắc lại sentinel.
4. Processor/writer phát sinh exception có message chứa sentinel.
5. Retry/backoff và listener cùng được kích hoạt; ít nhất một StepExecution FAILED rồi restart.
6. Để middleware giả/broker test tạo một message redelivery hoặc DLQ entry có payload kiểm soát.
7. Thu gom stdout/stderr, file appender, JSON logs, collector index, traces, diagnostic events và alert payload của **test environment**.
8. Scan token giả và kiểm tra schema allowlist; không được thấy sentinel hoặc secret-bearing headers.
9. Kiểm tra log vẫn có event type, status, duration, error category, retry count và safe correlation ID để debug.
10. Lặp trên multi-threaded step, parallel steps, manager và nhiều worker JVM; không chỉ một process.

### Test ở điểm nào để tránh false confidence?

- **Trước appender:** kiểm tra event fields/Throwable/MDC.
- **Sau encoder:** kiểm tra JSON/text thực đã ghi.
- **Sau shipper:** một số collector tự thêm metadata, request body hoặc stack trace.
- **Trên APM:** trace attributes/events/baggage có thể được capture độc lập với logging.
- **Trên DLQ:** message payload đã được retain dù không xuất hiện trong stdout.
- **Trong JobRepository:** query metadata fixtures test để phát hiện secret trong params/context; nhớ chỉ dùng test data và quyền đọc phù hợp.

**Không đưa token thật vào CI/CD** để test. Nếu secret thật vô tình xuất hiện trong logs của CI, xử lý như incident chứ không chỉ xóa artifact.

## 22. Token rotation, retry và restart: worker phải lấy credential mới an toàn

Spring Batch có thể chạy hàng giờ; access token có thể hết hạn giữa Step. Thiết kế credential lifecycle phải **khác** business checkpoint:

~~~text
T0  Worker chạy partition P, đọc snapshot V.
T1  Worker lấy token từ identity provider.
T2  Worker gọi API, ghi batch output.
T3  Token hết hạn hoặc bị thu hồi.
T4  Provider refresh/issue token mới theo scope.
T5  Worker tiếp tục partition từ checkpoint hợp lệ.
~~~

Không lưu token T1 vào `StepExecutionContext` để restart từ T5. **Checkpoint lưu vị trí dữ liệu**, còn provider cấp credential theo identity hiện thời.

### Phân biệt lỗi xác thực và lỗi nghiệp vụ

- **401:** token có thể hết hạn hoặc thiếu quyền. Có thể thử một lần refresh có kiểm soát nếu contract cho phép; 401 lặp lại phải fail/alert, không retry vô hạn.
- **403:** thường là vấn đề quyền/scope, cần fail rõ và kiểm tra IAM; không tự nâng quyền worker.
- **429/503:** downstream rate limit/overload, dùng backoff, quota và bounded concurrency, nhưng không log response body/header nhạy cảm.
- **Timeout sau POST:** không biết server có commit hay chưa; retry phải có idempotency key/ledger và validation.
- **Token provider unreachable:** fail/stop có policy và không fallback sang hardcoded credential hoặc token từ log/metadata.

### Credential cache trong nhiều thread

Nếu 32 worker threads cùng phát hiện token hết hạn, provider có thể bị “refresh storm”. Thiết kế cache/refresh an toàn theo workload/audience, có giới hạn concurrency, nhưng không ghi token vào diagnostics để kiểm tra đồng bộ. Đo **refresh count, refresh latency, result code**, không đo hoặc log raw token.

### Restart trên node khác

Khi một partition được giao lại worker mới, worker phải có quyền lấy credential theo **vai trò và scope của mình**. Không dựa vào token cũ được mã hóa trong checkpoint. Nếu worker cũ còn hoạt động, ngoài bảo mật còn cần ownership/fencing để tránh double writes.

## 23. Vận hành trên Kubernetes, cloud và hệ thống thu thập log

Trong Kubernetes, một container ghi log ra stdout có thể bị collect bởi node agent và lưu ở hệ thống ngoài cluster. Việc đưa token vào stdout có thể tạo bản sao ngoài phạm vi kiểm soát của application.

### Cần xem xét

- **Secrets as environment variables:** có thể lộ qua diagnostics/process dumps/config inspection nếu quyền không phù hợp. Không in toàn bộ environment lúc startup.
- **Mounted secret volumes:** hạn chế quyền file, không in file contents; hỗ trợ rotation khi nền tảng/app cho phép.
- **ServiceAccount/workload identity:** gán quyền tối thiểu, không dùng quyền manager cho mọi worker.
- **HTTP ingress/service mesh/proxy logs:** tắt logging raw Authorization/Cookie, signed query; quản lý trace sampling và redaction.
- **kubectl logs / central dashboards:** phân quyền theo project/team/environment, không cho người dùng không liên quan xem toàn bộ logs của service có đặc quyền.
- **Core dumps/heap dumps:** có thể chứa token trong RAM dù application không log; bảo vệ, mã hóa, hạn chế export và retention.
- **Kubernetes Events và command args:** không đưa token vào command-line launch options.
- **JobRepository backups và broker retention:** metadata/message không được chứa secret từ đầu; encryption at rest không thay nguyên tắc này.
- **Log archive và export:** tránh sao chép logs ra ticket/email/chat/public artifact không có kiểm soát.

### Mẫu phân quyền theo vai trò

| Thành phần | Quyền tối thiểu |
| --- | --- |
| Scheduler | Quyền gọi JobLauncher có kiểm soát; không cần token downstream |
| Manager | Phân phối partition/chunk, ghi metadata; không phát token API |
| Worker reader | Chỉ đọc snapshot/source trong phạm vi được giao |
| Worker writer | Chỉ ghi target/table/topic cần thiết |
| Secret provider client | Xin token cho đúng audience/scope; không truy cập mọi secret |
| Observability operator | Đọc số liệu/traces an toàn; không có quyền Secret Manager mặc định |
| Security incident responder | Quyền điều tra hạn chế theo quy trình và audit |
| Backup/retention service | Lưu/encrypt/expire dữ liệu theo policy, không tự xuất secrets |

Không nhầm “log đã được mã hóa khi lưu” với “có thể ghi token vào log”: người có quyền đọc index/decrypt vẫn nhận được token plaintext.

## 24. Bảng đánh giá rủi ro và ưu tiên xử lý

| Rủi ro | Khả năng ảnh hưởng | Dấu hiệu | Ưu tiên |
| --- | --- | --- | --- |
| Log trực tiếp `Authorization` header | Token có thể bị sử dụng ngay | Token xuất hiện trong stdout/index | **Chặn ngay, revoke/rotate** |
| Token trong `JobParameters` | Tồn tại trong metadata/backups | Param string có key bí mật | **Sửa nguồn + xử lý dữ liệu cũ** |
| Signed URL trong context | Quyền truy cập object bị lộ qua snapshot | URL query signature trong metadata/logs | **Loại khỏi state** |
| HTTP wiretap ở DEBUG | Lộ nhiều requests đồng loạt | Raw header/body logs | **Tắt/cấu hình logging** |
| MDC token trên pooled thread | Rò giữa jobs hoặc tenants | MDC key xuất hiện trong event khác | **Sửa nguồn và cleanup** |
| Broker DLQ chứa token | Lưu dài hạn, nhiều người có quyền inspect | Message raw payload/headers | **Đổi contract + bảo vệ DLQ** |
| Tracing capture Authorization | Secret ở APM spans/baggage | Header attribute trên trace | **Tắt capture + xóa/quản trị retention** |
| JDBC URL có password | Connection secret bị log tự động | Driver/config exception với URL | **Đổi cách inject credential** |
| Log archive đọc quá rộng | Tăng phạm vi lộ | ACL rộng, export tùy ý | **Siết quyền, audit access** |
| Masking regex không bao phủ | Lộ dạng encode/field mới | Synthetic leak test fail | **Allowlist tại nguồn + tests** |

Bảng là **định hướng threat modeling**, không thay việc đánh giá dữ liệu, mức độ ảnh hưởng và chính sách tổ chức.

## 25. Ma trận kiểm thử bảo mật cho multi-threaded, partitioned và distributed jobs

| Kịch bản | Kích hoạt | Oracle / kỳ vọng |
| --- | --- | --- |
| Reader nhận token từ provider | Dùng token giả trong test runtime | Token không có trong params/context/logs |
| Processor xử lý JSON có `access_token` | Dùng payload giả | Không dump payload vào log/trace |
| Writer gọi API trả 503 | Body/exception chứa sentinel | Logger chỉ có status/category |
| JDBC connection fail | Connection config giả có secret sentinel | Driver exception không xuất ở application log |
| StepExecution FAILED | ExitDescription chứa test sentinel | Safe listener không in raw description |
| Multi-threaded chunks | Nhiều threads cùng lỗi | Không log token, không gắn sai context |
| Parallel steps | Hai flows gọi hai APIs khác nhau | Không trộn audience/token hoặc MDC |
| Local partitioning | Partition input keys khác nhau | Không copy secret vào `StepExecutionContext` |
| Remote partitioning | Manager dispatch 100 partitions | Request schema không có credentials |
| Remote chunking | Message redelivery sau commit | Không in raw message headers/body |
| Broker DLQ | Poison chunk giả | DLQ không có token; access control đúng |
| HTTP wiretap enabled trong fixture | Cố ý bật trên test riêng | Sentinel scan phải phát hiện, CI fail |
| Tracing/APM capture | Synthetic header/URL | Span attributes không chứa sentinel |
| Token expiry | Server trả 401 | Provider refresh an toàn, không log token cũ/mới |
| Worker crash/restart | Replay từ JobRepository | Token được lấy lại qua provider, không persist |
| Rolling deploy | Old/new worker logging configs | Cả hai version giữ allowlist contract |
| Core/heap dump workflow | Simulate diagnostic collection | Chỉ người được phép đọc, retention được kiểm soát |
| Log collector export | Gửi synthetic event | Index/archive/alert không chứa token |
| Logback MDC encoder | Thêm field bị cấm trong test | Schema/review ngăn field và pipeline báo lỗi |
| Business reconciliation | Retry sau mất reply | Output đúng, logs không chứa secrets |

### Test đồng thời không chỉ là tìm chuỗi

Ở nhiều worker, cần kiểm tra cả **đúng quyền và đúng audience**: worker A không dùng token của B; retry không làm token của tenant khác được gắn vào request; worker cũ bị thu hồi quyền không tiếp tục ghi sai khi failover. Không ghi token thật để phân biệt — dùng synthetic provider ghi **logical token IDs giả** trong test harness riêng.

## 26. Quy trình xử lý khi token đã xuất hiện trong log

Nếu phát hiện token thật trong log, coi đó là **sự cố lộ bí mật**, không chỉ “lỗi format log”.

### Thứ tự xử lý đề xuất

1. **Ngăn ghi thêm:** tắt logger/wiretap gây lộ hoặc cô lập đường log; triển khai bản sửa theo quy trình khẩn.
2. **Giới hạn phạm vi truy cập:** tạm khóa quyền đọc/export không cần thiết đối với index, bucket, alerts, dashboards và các bản sao đã biết.
3. **Thu hồi/rotate secret:** revoke token, rotate refresh token/API key/client secret phù hợp với identity provider. Kiểm tra downstream đã chấp nhận token mới.
4. **Xác minh các workers:** credential cache được refresh, job không thất bại vì token cũ, không hardcode bản dự phòng.
5. **Xác định phạm vi lộ:** thời gian token xuất hiện, hệ thống log/trace/backup/DLQ chứa bản sao, ai có quyền truy cập hoặc đã export.
6. **Audit việc sử dụng token:** tra logs của identity provider/downstream theo **ID giao dịch an toàn**, phân biệt hoạt động hợp lệ với bất thường.
7. **Bảo quản bằng chứng theo chính sách:** không xóa tất cả dữ liệu ngay làm mất khả năng điều tra hoặc vi phạm retention/legal hold.
8. **Xử lý dữ liệu tồn dư:** phối hợp owners của collector, archive, alerts, tracing, tickets và backups để purge/redact/expire theo policy; hiểu rằng token cũ có thể đã được sao chép.
9. **Thông báo/escalate:** tuân theo quy trình security incident, privacy/compliance và SLA của tổ chức khi cần.
10. **Kiểm chứng hậu xử lý:** synthetic sentinel end-to-end test, review ACL, token scopes/TTL và dashboard schema.
11. **Bổ sung regression tests và guardrails CI:** prevent logging raw objects/headers/params, kiểm tra thay đổi config, giám sát việc bật TRACE.
12. **Ghi root cause và hành động phòng ngừa:** không chỉ “đã đổi token” mà không sửa nguồn gây log leak.

### Đừng làm những việc sau

- Chỉ thay `accessToken` trong app nhưng giữ refresh token đã lộ còn hiệu lực.
- Chỉ xóa một dòng trên dashboard trong khi bản gốc vẫn ở collector/archive.
- Gửi chính token vừa bị lộ vào ticket/email/chat để báo sự cố.
- Dán nguyên stack trace/JDBC URL/signed URL vào báo cáo công khai.
- Xóa metadata `BATCH_*`/JobRepository để xóa token cũ mà không hiểu restart/data integrity.
- Khởi chạy JobInstance mới bằng identifying `run.id` khác để né state cũ, tạo duplicate side effects.
- Cố chứng minh “không có ai xem log” khi không có audit evidence.

**Nếu token đã bị vô hiệu hóa**, nguy cơ sử dụng sau đó giảm, nhưng vẫn cần đánh giá mức độ lộ trước thời điểm thu hồi và các hệ thống giữ bản sao.

## 27. Bài tập tình huống: access token bị log ở 12 remote workers

Một công ty chạy Spring Batch phân tán nhập **5 triệu orders** mỗi đêm:

~~~text
Manager JVM: 1
Remote worker JVMs: 12
Worker threads per JVM: 4
Input: immutable snapshot, checkpoint ở JobRepository
Target: orders-api, OAuth2 token TTL=15 phút
Observability: Logback -> stdout -> Fluent Bit -> centralized logs
Broker: có retry, reply queue và DLQ
~~~

Một đợt deploy có ba thay đổi:

1. Developer đưa `accessToken` vào `JobParameters` để worker “lấy lại sau restart”.
2. Worker bật HTTP debug và gọi `log.debug("request={}", request)`.
3. Khi API trả 503, listener dùng `log.error("step failed", exception)`; exception có URL ký và response body nhạy cảm.

Sau 20 phút, đội vận hành phát hiện chuỗi giống token trong log search; một số messages đã tới DLQ, còn 12 workers vẫn chạy.

**Câu hỏi:**

1. Ngoài application stdout, token có thể nằm trong những hệ thống nào?
2. Đổi `addString("accessToken", token, false)` có khiến JobParameters an toàn không?
3. Tại sao mã hóa database at rest chưa giải quyết rủi ro token trong ExecutionContext?
4. Worker restart trên JVM khác nên lấy credential theo cơ chế nào?
5. Vì sao log request object và raw exception đều nguy hiểm?
6. Tắt DEBUG của Logback có bảo đảm token không còn trong APM và DLQ không?
7. Dùng chung field `currentToken` trong một singleton cho nhiều threads/tenants có rủi ro gì?
8. Ngoài sửa log statement, bước khẩn cấp cần làm khi token đã lộ là gì?
9. Sau khi rotate access token, tại sao vẫn phải xem xét refresh token, archive và quyền xem logs?
10. Đề xuất một safe log event đủ để phân tích HTTP 503 mà không ghi secret.
11. Kể tên ba security tests dùng synthetic sentinel trước rollout.
12. Vì sao đổi identifying `run.id` để “restart” có thể tạo duplicate effects?
13. Có nên ghi prefix/suffix hoặc hash token để correlation không?
14. Nếu chunk đã commit nhưng mất broker reply, cần chứng minh gì trước khi replay?
15. Khi nào có thể coi việc sửa đã đạt kết quả?

### Gợi ý đáp án

- **(1)** JobRepository parameters/context, broker DLQ/payload/headers, log agent, collector/index/backup, tracing/APM, alerts, tickets và diagnostics.
- **(2)** Không; non-identifying parameter vẫn có thể được persist/log.
- **(3)** Người có quyền đọc dữ liệu/metadata và debug tools vẫn có thể thấy giá trị; encrypted-at-rest không thay secret manager.
- **(4)** Workload identity và secret provider có least-privilege scope, refresh/rotation đúng lifecycle.
- **(5)** `toString`/exception message/stack trace có thể chứa header, query, cookies, signed URL, raw body.
- **(6)** Không. Broker payload, traces và các appenders khác phải được kiểm tra độc lập.
- **(7)** Cross-tenant/scope token mix, data race, dùng token sai hoặc hết hạn cho request khác.
- **(8)** Ngăn phát tán thêm, giới hạn log access và revoke/rotate bí mật theo incident procedure.
- **(9)** Các credentials khác có thể cùng bị lộ; bản sao logs vẫn tồn tại và đã có thể được export.
- **(10)** `event=downstream_call_failure service=orders-api operation=postBatch status=503 error_category=HTTP_503 attempt=2`.
- **(11)** Logback ListAppender test với exception chứa sentinel; MDC cleanup test trên một pooled thread; end-to-end scan collector/traces/DLQ.
- **(12)** JobInstance mới có thể chạy lại snapshot, thay vì resume checkpoint và idempotency chưa chắc đủ.
- **(13)** Không tự tiện; nó có thể rò cấu trúc/cho correlation nhạy cảm. Dùng ID độc lập với token.
- **(14)** Business key và idempotency ledger/operation identity, ownership, checkpoint và reconciliation.
- **(15)** Synthetic token không xuất hiện ở các sinks kiểm thử, secret thật đã thu hồi, phạm vi incident xử lý và regression tests hoạt động.

### Kiến trúc đề xuất sau khi sửa

~~~mermaid
flowchart TD
    J["JobLauncher: safe job parameters"] --> R["JobRepository: snapshot + checkpoint"]
    J --> M["Manager: safe partition dispatch"]
    M --> B["Broker: allowlisted message"]
    B --> W["Worker: workload identity"]
    W --> S["Secret provider: scoped, short-lived token"]
    W --> A["Downstream API: auth header, not logged"]
    W --> O["Allowlist log: status, error category, latency"]
    O --> C["Collector: RBAC, audit and retention"]
    R --> V["Restart and business reconciliation"]
    A --> V
~~~

Checkpoint tiếp tục lưu đúng snapshot/partition state; credential bị thu hồi được lấy lại từ provider, không đọc từ metadata cũ. Business effects vẫn cần idempotency khi retry và broker redelivery.

## 28. Checklist trước production và code review

- [ ] Không log access/refresh token, API key, client secret, password, cookie, private key hoặc signed URL.
- [ ] Không chứa secret trong `JobParameters`, `JobExecutionContext`, `StepExecutionContext` hay partition manifest.
- [ ] Không truyền credentials trong manager-to-worker message khi worker có thể lấy qua identity riêng.
- [ ] Workload identity và secret provider giới hạn scope/audience/source/target theo least privilege.
- [ ] Có TTL, rotation/refresh và policy fail rõ khi auth lỗi kéo dài.
- [ ] Không log raw HTTP request/response, URL query, headers, body hoặc `Throwable` chưa được kiểm soát.
- [ ] Chỉ ghi event fields đã allowlist, cả **tên field lẫn nguồn giá trị** được review.
- [ ] Correlation ID độc lập với token, không sử dụng token hash/prefix/suffix như ID.
- [ ] MDC/baggage không chứa secrets; cleanup/restoration ở `finally` khi thread pool tái sử dụng thread.
- [ ] Batch listeners chỉ log safe step name/status/counters, không dump metadata/context/exit description.
- [ ] Đã kiểm tra HTTP wiretap, JDBC bind parameter logging, tracing/APM capture và JSON encoder behavior.
- [ ] Masking/redaction chỉ là defense in depth, có test đa định dạng và trước/sau serializer.
- [ ] Broker DLQ/retained message payload không chứa credential, có quyền và retention phù hợp.
- [ ] Traces/metrics không chứa Authorization/Cookie, signed URLs hoặc PII trong labels/baggage.
- [ ] DB connection URL, command-line args, startup logs và diagnostic endpoints không lộ secrets.
- [ ] Production không dùng real token trong tests hoặc CI artifacts.
- [ ] JUnit test kiểm tra formatted messages **và** Throwable proxies/MDC fields khi phù hợp.
- [ ] Integration test kiểm tra stdout, log file, collector, APM, alert và DLQ bằng token giả.
- [ ] Có test nhiều worker threads/JVM, retry, restart, rolling deploy và token rotation.
- [ ] Metadata chỉ chứa immutable input reference/checkpoint để restart, không giữ token.
- [ ] Business writer idempotent và có reconciliation cho commit–reply uncertainty.
- [ ] Central logs/backup/traces có RBAC, audit truy cập, retention/encryption đúng chính sách.
- [ ] Có alert kiểm tra forbidden fields mà không gửi raw secret vào alert.
- [ ] Có incident runbook revoke/rotate, xác định phạm vi lộ, archive cleanup và bảo quản bằng chứng.
- [ ] Cấu hình logging/tracing được review mỗi khi đổi release, tăng DEBUG hoặc thêm integration.
- [ ] Logs an toàn vẫn đủ chẩn đoán throughput, retry storm, failed partitions và recovery.
- [ ] Không tăng concurrency trước khi xác minh authentication, tenant isolation và logging contract an toàn.

## 29. Tài liệu tham khảo

- [Spring Batch Reference – Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): JobInstance, JobParameters, StepExecution, ExecutionContext.
- [Spring Batch Reference – Job Configuration](https://docs.spring.io/spring-batch/reference/job.html): identifying parameters và restart.
- [Spring Batch Reference – Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): execution metadata và context tables.
- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel steps và partitioning.
- [Spring Batch Reference – Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): remote partitioning/chunking.
- [Spring Batch Reference – Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): job/step observability.
- [Spring Batch Reference – Intercepting Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): StepExecutionListener.
- [Spring Boot Reference – Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logging config/levels.
- [Spring Security Reference – OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): OAuth2 client credentials/token lifecycle.
- [SLF4J User Manual](https://www.slf4j.org/manual.html): logging API, MDC.
- [Logback Manual](https://logback.qos.ch/manual/index.html): appenders, layouts, throwable and MDC output.
- [Micrometer Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): metrics, timers, tags.
- [OpenTelemetry – HTTP Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/http/http-spans/): HTTP tracing attributes.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): secure logging và data handling.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): scope, rotation và incident response.
- [Kubernetes – Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): Kubernetes secret-management boundaries.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): Java HTTP client.
- [JUnit 5 User Guide](https://docs.junit.org/5.11.4/user-guide/): unit/integration tests.

Các ví dụ và đường dẫn phải được đối chiếu với phiên bản Spring Batch 5.x, Spring Boot, Logback, HTTP client và observability agent đang triển khai. Tài liệu tham khảo không đồng nghĩa đã thực hiện security audit cho ứng dụng cụ thể.

## Ghi nhớ

**Không ghi token vào log là yêu cầu thiết kế toàn bộ đường đi của dữ liệu, không chỉ dùng regex để thay chuỗi sau khi log được tạo.** Trong Spring Batch phân tán, hãy bảo vệ `JobParameters`, `ExecutionContext`, partition messages, remote chunks, HTTP/JDBC/broker debug logs, listeners, MDC, metrics, traces, DLQ và log archives. Để **worker lấy credentials ngắn hạn theo workload identity**, còn metadata chỉ lưu snapshot/partition/checkpoint cần cho restart. Ghi logs theo allowlist với event type, status, error category, latency và counters; kiểm thử bằng token **giả** trên nhiều lớp, gồm concurrent threads và remote workers. Nếu token thật đã lộ, coi là incident: **ngăn phát tán, revoke/rotate, xác định phạm vi và sửa nguồn**, không chỉ ẩn một dòng log. **Scaling thành công phải giữ throughput, retry/restart và tính đúng của dữ liệu mà không đánh đổi bí mật của hệ thống.**
