# Thu thập ngữ cảnh chẩn đoán mà không lộ thông tin bí mật

## 1. Vấn đề: chẩn đoán được lỗi nhưng không biến log thành nơi rò rỉ dữ liệu

Trong module **SPRING_DATA_COUCHBASE**, chúng ta phát triển tầng truy cập Couchbase bằng Spring Data với document mapping, repository, `CouchbaseTemplate`, truy vấn SQL++, thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive.

Một lỗi production có thể chỉ được nhìn thấy dưới dạng:

```text
Order lookup failed after retries.
```

Thông báo này quá ít thông tin: không biết request thuộc KV hay Query service, là timeout trước hay sau khi dispatch, có CAS conflict không, index chưa sẵn sàng hay scope/collection sai.

Ngược lại, log **toàn bộ exception**, SQL++ statement, query parameters và document JSON có thể tiết lộ thông tin nghiêm trọng:

```text
GET failed for documentId=customer::lan@example.test
sql=SELECT * FROM customers WHERE email='lan@example.test'
Authorization: Bearer eyJ...
payload={"email":"lan@example.test","card_token":"tok_..."}
```

Lỗi thứ hai còn nguy hiểm hơn lỗi thứ nhất: log thường được gửi qua collector, APM, search dashboard, incident ticket, chat và bên thứ ba hỗ trợ. Một bí mật xuất hiện trong log có thể được sao chép, lưu trữ lâu dài và cấp quyền đọc rộng hơn database.

**Mục tiêu của bài:** thu thập **đủ tín hiệu để phân loại, định vị và khôi phục sự cố**, nhưng chỉ qua một **schema chẩn đoán đã cho phép**; không xuất raw document, key chứa định danh, connection string, credentials, SQL++ parameter values hoặc object exception không được kiểm duyệt.

### Bạn sẽ làm được gì?

1. Phân loại `CouchbaseException`, `ErrorContext` và Spring `DataAccessException` mà không ghi raw message/context.
2. Thiết kế structured diagnostic event gồm operation, error category, service, correlation ID, latency, timeout, outcome/retry signal và **không chứa payload bí mật**.
3. Nhận ra những trường dữ liệu tiềm ẩn bí mật ngay trong `ErrorContext`, exception cause và traces.
4. Tách **business request ID**, **SDK request ID** và **trace/span ID** theo đúng mục đích.
5. Viết Java adapter an toàn cho blocking, async `CompletableFuture` và reactive `Mono`.
6. Dùng log redaction của Couchbase SDK đúng quy trình, không coi nó là phép bảo vệ tuyệt đối cho application logs.
7. Dùng metric labels, tracing attributes và SQL++ parameterization mà không gây rò rỉ hay high cardinality.
8. Phân tích CAS conflict, ambiguous timeout, durability failure, query/index lag và lỗi sub-document mà vẫn giữ bí mật.
9. Kiểm thử bằng secret sentinels và vận hành chính sách retention, phân quyền, export sự cố.

## 2. Bối cảnh kỹ thuật: hai luồng ghi, nhiều hệ thống nhận log

Ví dụ dịch vụ Spring Boot xử lý một đơn hàng:

```java
OrderDocument order = orderRepository.findById(id)
    .orElseThrow();

// Một đường khác dùng raw SDK:
orders.mutateIn(
    id,
    List.of(
        MutateInSpec.replace(
            "shipping.status", "SHIPPED")
    )
);
```

Hệ thống có thể gửi thông tin tới:

- Application logger (SLF4J/Logback/Log4j2).
- Couchbase Java SDK logger và event bus.
- Spring WebMVC/WebFlux request logging.
- Micrometer/Prometheus và OpenTelemetry tracing.
- Error tracker (Sentry/incident platform).
- API error response đến client.
- Lịch sử job, dead-letter queue, message broker.
- Hỗ trợ kỹ thuật, support bundles và incident ticket.

Mỗi điểm đích có **quyền truy cập, retention và khả năng export khác nhau**. Cần thiết kế tiêu chuẩn chẩn đoán chung, không chỉ sửa một `logger.warn`.

```mermaid
flowchart TD
    A["HTTP / job / message consumer"] --> B["Business operation + correlation ID"]
    B --> C{"Couchbase access"}
    C --> D["Spring Data Repository / Template"]
    C --> E["Raw Java SDK KV / SQL++"]
    D --> F["Exception / result"]
    E --> F
    F --> G["Classify cause & outcome"]
    G --> H["Project into strict safe allowlist"]
    H --> I["Structured log / metrics / spans"]
    H --> J["Sanitized API error"]
    F -. "Chỉ khi được phê duyệt" .-> K["Secure diagnostic channel: restricted / redacted"]
```

**Điểm an toàn:** giữa `Exception / result` và mọi sink thường dùng phải có **bước biến đổi sang dữ liệu an toàn**. Đừng gửi nguyên object rồi hy vọng sink/collector che hết.

## 3. Mô hình đe dọa đối với diagnostic data

Cần cân nhắc không chỉ attacker từ bên ngoài, mà còn rủi ro từ người vận hành, quyền truy cập dashboard, hệ thống liên kết và bản sao ngoài dự kiến.

### 3.1. Những loại dữ liệu cần bảo vệ

| Dữ liệu | Ví dụ | Nguy cơ |
| --- | --- | --- |
| Credentials | Password, API key, JWT, OAuth bearer token | Chiếm quyền truy cập. |
| Kết nối DB | `couchbases://user:secret@host` hoặc secrets trong config | Tiết lộ credentials/hạ tầng. |
| Document key | `customer::lan@example.test` hoặc `tenant::A::account::123` | Lộ PII, tenant identity, business ID. |
| Body JSON | Email, số điện thoại, địa chỉ, payment token, trạng thái nhạy cảm | Rò rỉ dữ liệu cá nhân/nghiệp vụ. |
| SQL++ query text | Predicate có literal email/token; dynamic statement | Lộ thông tin tìm kiếm và schema. |
| Query parameters | `$email`, `$accountId`, `$token` | Lộ input bí mật dù SQL template an toàn. |
| Full exception/cause | Exception message chứa document ID, statement, endpoint | Log raw có thể đưa mọi giá trị trên vào sink. |
| Request/response headers | `Authorization`, `Cookie`, internal tokens | Chiếm phiên hoặc thông tin nội bộ. |
| Stack trace | User input trong exception message, URLs, endpoint | Lộ bối cảnh nội bộ và input. |
| Traces | `db.statement`, `db.query.parameter.*`, user ID | Lan truyền PII sang APM. |
| Metrics labels | Document ID, tenant/email, trace ID | Rò rỉ và high cardinality. |
| Support bundle | Logs, configs, endpoint details, query snippets | Phát tán sang đối tác/hệ thống khác. |

Không phải mọi ID đều là bí mật tuyệt đối, nhưng hãy coi **document ID là dữ liệu có thể định danh** cho đến khi có chính sách riêng chứng minh ngược lại.

### 3.2. Rủi ro do dữ liệu tự mang thông tin

Một key kiểu `order::1001` trong bài học có vẻ vô hại; production có thể dùng `customer::alice@company.test` hoặc nối tenant + mã tài khoản. Vì vậy **không log document key theo mặc định**, kể cả khi hôm nay key chỉ là UUID.

Một tên field như `payment.card_token` có thể tiết lộ mô hình bảo mật; không để client tự chọn path rồi đưa raw path vào log. Dùng operation code cố định, ví dụ `UPDATE_SHIPPING_STATUS`.

## 4. Nguyên tắc "chỉ thu thập điều cần thiết"

Một diagnostic event tốt phải trả lời nhanh:

- Chuyện gì xảy ra? (`operationCode`).
- Ở dịch vụ nào? (`KV`/`QUERY`, môi trường và logical collection alias).
- Thuộc loại lỗi nào? (`NOT_FOUND`, `CAS_CONFLICT`, `TIMEOUT_AMBIGUOUS`…).
- Bao lâu? (latency).
- Có retry không? (attempt count hoặc cờ retry).
- Có thể dò theo request nào? (`correlationId`/`traceId` đã được quản lý).
- Outcome đã chắc chắn chưa? (`KNOWN_FAILURE`/`UNKNOWN_COMMIT`).
- Cần làm gì tiếp? (retry, reconcile, sửa schema hoặc kiểm tra cluster).

Nó **không cần** email, phone, raw SQL statement, body, document ID hay password để trả lời các câu hỏi này.

### 4.1. Bốn lớp dữ liệu

| Lớp | Quy tắc | Ví dụ |
| --- | --- | --- |
| **A — An toàn để log thường xuyên** | Enum/constant do code sở hữu, số thống kê giới hạn | `GET_ORDER`, `KV`, `CAS_CONFLICT`, `durationMs=28`. |
| **B — Cho phép có điều kiện** | Dùng khi policy, RBAC và retention cho phép | Logical alias `orders`, stable correlation ID, schema version. |
| **C — Phải được biến đổi** | HMAC/tokenization hoặc mask theo policy, không dùng raw | HMAC document key nếu thực sự cần correlation xuyên requests. |
| **D — Không vào log thông thường** | Không bao giờ serialize raw | Password, JWT, access token, body JSON, SQL parameters, exception context chưa lọc. |

**Deny-by-default:** schema logger chỉ có các field đã whitelist. Nếu SDK version mới xuất hiện field context lạ, hệ thống **không** được tự log nó.

## 5. `ErrorContext` của Java SDK hữu ích nhưng không phải log an toàn

Tài liệu Couchbase Java SDK giải thích `CouchbaseException` có getter `context()`; context đôi lúc **null**. Timeout và request-cancellation exceptions thường cung cấp thêm dữ liệu request.

Một context có thể chứa:

- `requestType`, `requestId`.
- `retryReasons`, `retried`, `timeoutMs`.
- `timings`, `status`.
- `service.type` (KV/Query/…).
- `service.bucket`/`scope`/`collection`.
- `service.documentId` đối với KV.
- `service.statement` đối với SQL++.
- Endpoint địa chỉ local/remote, channel ID và identifiers khác.

**Nguy cơ:** SDK tự chèn context vào thông báo exception khi nó được in. Nếu bạn gọi:

```java
log.error("Couchbase failure", exception);
```

framework logging có thể in `exception.toString()`, message, cause chain và SDK `ErrorContext`, bao gồm key hoặc query statement. **Không an toàn theo mặc định**.

### 5.1. Không giữ kỳ vọng schema `ErrorContext` ổn định

Tài liệu Java SDK mô tả tên và giá trị của `ErrorContext` là **volatile**, không cam kết tương thích ổn định giữa các phiên bản. Không viết:

```java
// Anti-pattern: serialize toàn bộ context ra JSON log.
log.error("db_context={}", cbException.context());
```

Cũng không parse chuỗi JSON context để trích `retryReasons[0]`, `documentId` hoặc `statement` theo kiểu brittle rồi ném toàn phần còn lại vào log khi parse lỗi.

Muốn dùng một trường context cho workflow chẩn đoán nâng cao, cần **hợp đồng allowlist theo SDK version**, test thay đổi schema và chính sách dữ liệu. An toàn nhất trong ứng dụng thường là lấy `operationCode`/`logicalCollection` từ chính call site, không phải từ serialization raw của exception.

### 5.2. `context()==null` là bình thường

`CouchbaseException.context()` không phải API luôn đảm bảo non-null. Một exception do serialization, validation hoặc logic khác có thể không có context. Diagnostic event của ứng dụng vẫn phải có `operationCode`, `correlationId` và `errorCategory` fallback.

Không ghi `"context": exception.toString()` như một phương án dự phòng.

## 6. Phân biệt request ID của ứng dụng, SDK và trace ID

Ba ID sau có vai trò khác nhau:

| ID | Ai sinh? | Mục đích | Lưu ý |
| --- | --- | --- | --- |
| Application correlation ID | Middleware tin cậy, gateway hoặc service | Liên kết log giữa các lớp của một business request | Không tin ID không kiểm chứng từ HTTP header. |
| SDK `ErrorContext.requestId` | Couchbase SDK | Tìm một internal request trong client diagnostics | Không bảo đảm unique toàn bộ ứng dụng/thời gian. |
| OpenTelemetry trace/span ID | Tracing runtime | Liên kết request phân tán | Không chứa dữ liệu người dùng; không thay auth hoặc idempotency. |
| Business operation ID | Domain/service | Phân biệt command đã thực hiện khi retry | Có thể nhạy cảm; log token thay vì raw khi cần. |

### 6.1. Sinh correlation ID tại trust boundary

Nếu HTTP client gửi `X-Request-ID` chứa email hoặc newline, không chép nguyên nó vào MDC. Một cách an toàn là tạo ID nội bộ:

```java
import java.util.UUID;

String correlationId = UUID.randomUUID().toString();
```

Nếu hệ thống có gateway phát hành ID đã xác thực, có thể dùng ID đó **sau khi xác minh format, độ dài và trust boundary**. Không nhận header user bất kỳ như ID chuẩn của hệ thống.

### 6.2. SDK request ID không phải business operation ID

SDK có thể retry một operation và sinh các request/dispatch details liên quan. Một command `shipOrder` có thể qua nhiều KV operations; một số nội dung context thay đổi giữa attempts.

Nếu cần ngăn double append/increment, phải dùng **operationId do ứng dụng quản lý** và chính sách idempotency, không dựa vào `ErrorContext.requestId`.

## 7. Schema sự kiện chẩn đoán tối thiểu

Ví dụ một log JSON an toàn, **các giá trị chỉ để minh họa**:

```json
{
  "event": "couchbase.operation.failed",
  "service": "order-service",
  "environment": "production",
  "operation": "UPDATE_ORDER_STATUS",
  "db_service": "kv",
  "logical_collection": "orders",
  "category": "CAS_CONFLICT",
  "outcome": "KNOWN_FAILURE",
  "duration_ms": 34,
  "retry_count": 0,
  "correlation_id": "f8a2e1ce-ff48-43cf-a536-b6a20d385d0b"
}
```

Không có:

- `documentId`.
- `sql.statement` hoặc bind values.
- Body JSON, request/response payload.
- Username/password/JWT, connection string.
- Raw stack trace, `exception.message` hoặc `exception.context`.
- Trace attributes chứa raw user input.

Nếu hệ thống bắt buộc có thêm trường, phải qua review bảo mật và cập nhật schema/test allowlist. Một dashboard có quyền rộng không phải lý do chấp nhận xuất mọi giá trị.

### 7.1. Diagnostic event không phải bản sao của exception

Sự kiện là một **projection có chủ ý** từ trạng thái ứng dụng và phân loại lỗi. Nó không cần trường `raw_exception` để có ích. Khi cần raw exception cho chuyên gia điều tra, dùng một đường hỗ trợ **phân quyền/retention/tẩy bí mật riêng**.

## 8. Thiết kế enum chuẩn hóa loại lỗi

Một ứng dụng nên có các category ổn định do chính mình sở hữu:

```java
public enum DbFailureCategory {
    NOT_FOUND,
    ALREADY_EXISTS,
    CAS_CONFLICT,
    PATH_ERROR,
    QUERY_ERROR,
    TIMEOUT_AMBIGUOUS,
    TIMEOUT_UNAMBIGUOUS,
    DURABILITY_UNCERTAIN,
    UNAVAILABLE,
    DATA_ACCESS,
    UNKNOWN
}
```

Enum không chứa input do người dùng gửi. Khi SDK nâng version, map lại exceptions mà **không phá schema metric/dashboard**.

### 8.1. Phân loại theo semantics, không theo exception message

| Lỗi nguồn | Category chuẩn hóa | Hướng xử lý |
| --- | --- | --- |
| `DocumentNotFoundException` | `NOT_FOUND` | Có thể là 404 hoặc dữ liệu bắt buộc mất; phụ thuộc domain. |
| `DocumentExistsException` | `ALREADY_EXISTS` | Kiểm tra conflict/idempotency. |
| `CasMismatchException` | `CAS_CONFLICT` | Đọc lại state và retry có giới hạn. |
| Sub-document path/type exception | `PATH_ERROR` | Sửa path/schema; không retry mù. |
| Query-specific error | `QUERY_ERROR` | Kiểm tra template/index/parameters/quyền. |
| `AmbiguousTimeoutException` | `TIMEOUT_AMBIGUOUS` | Outcome có thể đã commit; reconcile. |
| `UnambiguousTimeoutException` | `TIMEOUT_UNAMBIGUOUS` | Có thể cân nhắc retry theo policy. |
| Durability ambiguity | `DURABILITY_UNCERTAIN` | Không tự kết luận rollback. |
| Kết nối/node service unavailable | `UNAVAILABLE` | Kiểm tra topology, endpoint, circuit breaker. |
| Spring `DataAccessException` không chi tiết | `DATA_ACCESS` | Xem nguyên nhân qua secure debugger, không lộ raw. |
| Không nhận diện | `UNKNOWN` | Fail closed, metric/alert. |

Bảng mô tả ngữ nghĩa, không quy định phải import một exception class cụ thể cho mọi SDK/server version. Các exception có thể được Spring translator hoặc async wrapper bọc lại.

## 9. Java classifier an toàn cho SDK và Spring Data

Ví dụ sau dành cho SDK 3.x và Spring Data; hãy xác minh imports với dependencies đã resolve:

```java
import com.couchbase.client.core.error.AmbiguousTimeoutException;
import com.couchbase.client.core.error.UnambiguousTimeoutException;
import com.couchbase.client.core.error.DocumentNotFoundException;
import com.couchbase.client.core.error.DocumentExistsException;
import com.couchbase.client.core.error.CasMismatchException;

import org.springframework.dao.DataAccessException;

public final class DbFailureClassifier {
    private DbFailureClassifier() {}

    public static DbFailureCategory classify(Throwable failure) {
        Throwable current = failure;

        // Spring translator, CompletionException hay ExecutionException
        // có thể bọc exception gốc. Giới hạn độ sâu khi duyệt.
        for (int depth = 0;
             current != null && depth < 8;
             depth++, current = current.getCause()) {

            if (current instanceof AmbiguousTimeoutException) {
                return DbFailureCategory.TIMEOUT_AMBIGUOUS;
            }
            if (current instanceof UnambiguousTimeoutException) {
                return DbFailureCategory.TIMEOUT_UNAMBIGUOUS;
            }
            if (current instanceof CasMismatchException) {
                return DbFailureCategory.CAS_CONFLICT;
            }
            if (current instanceof DocumentNotFoundException) {
                return DbFailureCategory.NOT_FOUND;
            }
            if (current instanceof DocumentExistsException) {
                return DbFailureCategory.ALREADY_EXISTS;
            }
        }

        if (failure instanceof DataAccessException) {
            return DbFailureCategory.DATA_ACCESS;
        }
        return DbFailureCategory.UNKNOWN;
    }
}
```

**Điểm an toàn:** classifier chỉ dùng **type**, không gọi `getMessage()`, `toString()` hoặc serialize `context()`.

### 9.1. Giới hạn của ví dụ

- Các nhóm `QueryException`, path errors và durability errors cần bổ sung mapping có test theo version.
- `DataAccessException` có thể nằm sâu trong cause chain; production classifier nên map đủ kiểu Spring exception đã dùng.
- Nếu cause chain có cycle hoặc depth bất thường, xử lý bằng visited-set/bound.
- Một exception có thể mang nhiều ngữ cảnh; việc chọn category phải theo domain/operation.
- Không dùng đơn giản `current.getClass().getSimpleName()` như **public error code** nếu không có allowlist; tên class thay đổi theo SDK.
- Fallback `UNKNOWN` là chấp nhận được và an toàn hơn việc ghi raw message để “giải thích”.

### 9.2. Khi cần phân loại sub-document errors

Các lỗi như `PathNotFoundException`, `PathExistsException`, `PathMismatchException` có thể được map về category `PATH_ERROR`, nhưng cần phân biệt:

- Field optional thiếu có thể là nghiệp vụ bình thường.
- Required field thiếu là schema violation.
- CAS mismatch là concurrency, không phải path.
- `MultiMutationException` có thể đại diện failure của một spec trong request atomic.

Hãy kết hợp **operation code và expected contract** với exception type. Không suy rằng mọi `PathNotFound` có thể sửa bằng `createPath()`.

## 10. Structured logging: chỉ truyền những giá trị đã kiểm soát

Một ví dụ với SLF4J:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class SafeDbLogger {
    private static final Logger LOG =
        LoggerFactory.getLogger(SafeDbLogger.class);

    public void recordFailure(
            String correlationId,
            DbOperation operation,
            DbFailureCategory category,
            long durationMs) {

        // DbOperation là enum do application định nghĩa.
        // correlationId đã được sinh/validate tại trust boundary.
        LOG.warn(
            "db_failed op={} category={} trace={} durationMs={}",
            operation.name(),
            category.name(),
            correlationId,
            durationMs
        );
    }
}
```

`DbOperation` là enum do ứng dụng tạo, ví dụ:

```java
public enum DbOperation {
    LOAD_ORDER,
    UPDATE_ORDER_STATUS,
    FIND_ORDERS_BY_CUSTOMER,
    APPEND_ORDER_EVENT
}
```

Trong code sản xuất, có thể thêm service type/collection **alias** từ enum cấu hình. Không nhận `String operation` trực tiếp từ HTTP query/body; không nhận raw document ID.

### 10.1. Anti-pattern cần loại bỏ

```java
// Không dùng trong application log phổ thông:
log.error("DB error key={} payload={}", key, body);
log.error("DB error: {}", exception.getMessage());
log.error("DB request failed", exception);
log.error("Error context: {}", exception.context());
log.error("Query failed: sql={} params={}", sql, params);
```

Ngay cả khi SLF4J hỗ trợ placeholder, một placeholder **không che dữ liệu**. Nó chỉ trì hoãn formatting. Nếu đối số là `Throwable`, logger có thể in cả stack trace/context.

### 10.2. Severity không phụ thuộc raw message

- `DEBUG`: metrics/diagnostic chuyên sâu nhưng vẫn qua allowlist.
- `INFO`: expected not found nếu domain xem là bình thường; tránh log quá nhiều.
- `WARN`: CAS conflicts tăng bất thường, retryable timeout được cảnh báo theo ngưỡng.
- `ERROR`: systemic query failures, outage, durability ambiguity cần hành động.

Không tăng level lên DEBUG rồi cho log nguyên JSON để “dễ sửa lỗi”. Security policy phải áp dụng giống nhau ở mọi level.

## 11. Đo latency một cách không rò rỉ dữ liệu

Không cần document key để biết request chậm:

```java
long startedAt = System.nanoTime();
try {
    orders.get(orderId);
} catch (RuntimeException error) {
    long elapsedNanos = System.nanoTime() - startedAt;
    long elapsedMs =
        java.util.concurrent.TimeUnit.NANOSECONDS
            .toMillis(elapsedNanos);

    DbFailureCategory category =
        DbFailureClassifier.classify(error);

    safeDbLogger.recordFailure(
        correlationId,
        DbOperation.LOAD_ORDER,
        category,
        elapsedMs
    );
    throw error; // Giữ nguyên cause cho tầng xử lý nội bộ.
}
```

**Quan trọng:** `throw error` giữ exception gốc để controller/service xử lý, nhưng **tầng phía ngoài không được log nguyên exception hoặc trả exception message cho client**. Nếu tầng ngoài có middleware log `Unhandled exception` kèm Throwable theo mặc định, phải cấu hình để nó không leak; một safe logger ở đây không đủ.

### 11.1. Vì sao `System.nanoTime()`?

Đây là nguồn phù hợp đo thời lượng elapsed trong cùng tiến trình Java. Không dùng `System.currentTimeMillis()` để suy latency chính xác khi clock điều chỉnh. Nếu cần phân tích phân tán, kết hợp tracing với monotonic timers.

### 11.2. Giới hạn retry count

`ErrorContext.retried` có thể tồn tại nhưng schema volatile. Nếu ứng dụng tự điều khiển retry, ghi count **do ứng dụng đếm** và giới hạn giá trị (ví dụ 0–10), không chép một array raw `retryReasons` vào log.

## 12. Lưu exception gốc ở đâu khi cần điều tra sâu?

Giữ exception trong **call stack nội bộ** có thể hữu ích cho error translation, debug và alert. Nhưng không có nghĩa cần log nó vào mọi sink.

Một mô hình ba cấp:

1. **Public API:** `errorCode` và `correlationId`, không có database details.
2. **Operations logs/metrics:** safe allowlist, đủ để phân loại/tìm nhóm sự cố.
3. **Secure incident channel:** khi thật cần, người có quyền lấy SDK context đã được rà soát/tẩy bí mật, có audit truy cập, TTL ngắn và quy trình export.

Không lưu raw exception vào Redis, DLQ, error tracker hoặc support ticket chỉ vì tiện.

### 12.1. Không bỏ qua lỗi nghiêm trọng

Sanitization **không phải swallow**. Adapter vẫn phải:

- Throw/propagate lỗi đúng kiểu hoặc mã hóa thành domain error.
- Trả status cần thiết cho retry/reconciliation.
- Tăng metric/error counter.
- Tạo alert theo ngưỡng.
- Bảo đảm không trả success giả.

Mục tiêu là **giữ hành vi đúng, giảm độ nhạy của dữ liệu quan sát**, không xóa toàn bộ khả năng điều tra.

## 13. HMAC document key khi thật sự cần correlation xuyên requests

Có tình huống support cần biết nhiều lỗi có cùng **một document** nhưng không được thấy key. Khi đó có thể tạo fingerprint bằng **HMAC có khóa bí mật**, theo policy.

Không nên dùng:

```java
// Anti-pattern: SHA-256 không có secret.
// Email/phone/ID không gian nhỏ có thể bị đoán bằng dictionary.
String hash = sha256(documentId);
```

HMAC giúp ngăn việc đối chiếu dễ dàng bằng dictionary khi người đọc log không có secret. Nhưng **đây vẫn là pseudonymous identifier**, không phải ẩn danh tuyệt đối.

### 13.1. Ví dụ HMAC-SHA256 rút gọn

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class DocumentKeyFingerprint {
    private DocumentKeyFingerprint() {}

    public static String hmacToken(
            byte[] secretKey,
            String tenantScope,
            String documentId) throws Exception {

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(
            secretKey, "HmacSHA256"));

        // Domain separation và tenant scope để không trùng token
        // giữa các mục đích/cụm dữ liệu khác nhau.
        String input = "cb-document:v1:"
            + tenantScope.length() + ":" + tenantScope
            + ":" + documentId;

        byte[] digest = mac.doFinal(
            input.getBytes(StandardCharsets.UTF_8));

        byte[] prefix = Arrays.copyOf(digest, 16);
        return "h1:" + Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(prefix);
    }
}
```

Ví dụ kỹ thuật, không phải quyết định bắt buộc phải log fingerprint. Secret phải lấy từ secret manager/KMS theo chính sách, **không hard-code**, không truyền trong log, không cho vào URL, không đính kèm support ticket.

### 13.2. Giới hạn và vận hành HMAC

- Dùng secret riêng cho mục đích log và môi trường; tránh reuse credential kết nối Couchbase.
- Có version key (`h1`) để hỗ trợ rotation.
- Giới hạn retention/khả năng tra cứu token vì token vẫn liên kết nhiều hành động.
- Không cho tenant A nhìn token của tenant B.
- Nếu input document ID quá dài hoặc chưa validate, reject/normalize an toàn trước khi đưa vào HMAC.
- Không dùng raw SHA-256/MD5 với email, phone, user ID hay số tài khoản.
- Không coi HMAC là authorization, encryption của payload hay bảo vệ chống log injection.

Nếu không có nhu cầu correlation per-document rõ ràng, **không tạo fingerprint** còn an toàn hơn.

## 14. Tránh log injection và format-string abuse

Một chuỗi do người dùng kiểm soát có thể chứa newline hoặc control characters:

```text
x
ERROR Access granted as admin
```

Nếu ghép trực tiếp vào log, attacker có thể tạo dòng trông như lỗi nghiêm trọng hoặc làm giả diễn biến incident.

### 14.1. Vì sao structured logger chưa đủ nếu values là untrusted?

JSON encoder chuẩn giúp escape newline, nhưng sink tiếp theo vẫn có thể format lại. Một trường `requestId` từ HTTP header có thể được hiển thị không escape trong dashboard.

Giải pháp:

- Chỉ dùng enums và ID do middleware tin cậy sinh.
- Giới hạn độ dài, charset và cardinality.
- Không concatenate raw user-controlled strings.
- Cấu hình structured JSON encoder đáng tin cậy.
- Test log pipeline thật, không chỉ mock một Logger.
- Không đưa raw exception message vào field JSON chỉ vì encoder có escape.

### 14.2. Có nên log tên bucket/scope/collection?

Tên keyspace đôi khi giúp chẩn đoán routing, nhưng cũng tiết lộ cấu trúc nội bộ. Với ứng dụng có các tên cố định, tạo **logical alias**:

```text
logical_collection=orders
db_service=kv
environment=production
```

Chỉ nhóm vận hành phân quyền mới cần mapping alias sang cluster/keyspace thật. Không cho phép người dùng truyền arbitrary bucket/scope/collection vào log.

## 15. Truy vấn SQL++: không ghi statement hoặc parameters vào log

Truy vấn SQL++ có thể chứa:

```sql
SELECT META(o).id
FROM `shop`.`sales`.`orders` AS o
WHERE o.customer_email = "lan@example.test";
```

Nếu exception context chứa `statement`, việc log nguyên exception làm lộ email. Kể cả khi query dùng placeholder, **parameters** vẫn có thể lọt qua application logging nếu in raw `QueryOptions` hoặc context khác.

### 15.1. Dùng tham số có bind

```java
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryResult;

String statement = """
    SELECT META(o).id AS orderId
    FROM `shop`.`sales`.`orders` AS o
    WHERE o.customer_email = $email
    """;

QueryResult result = cluster.query(
    statement,
    QueryOptions.queryOptions()
        .parameters(
            JsonObject.create().put("email", email))
);
```

Đoạn code dùng Java text block (Java 15+); nếu project dùng Java cũ hơn, xây string literal tương đương. `email` là input đã validate; **không log value đó**.

### 15.2. Query template ID thay cho raw SQL

```java
safeDbLogger.recordFailure(
    correlationId,
    DbOperation.FIND_ORDERS_BY_CUSTOMER,
    category,
    elapsedMs
);
```

Một operation code/tên query template cố định đủ để nhóm lỗi theo use case. SQL++ statement có thể được lưu **trong source code** và tra lại qua deployment version, không nhất thiết phải copy vào log.

### 15.3. Parameterization không thay thế logging hygiene

Bind parameters giảm nguy cơ SQL injection vào **value literals**, nhưng:

- Parameter values vẫn nhạy cảm nếu được log.
- Tên bucket/scope/collection hoặc field identifiers được build động cần allowlist; không thể coi chúng như bind value trong mọi vị trí.
- `QueryResult.rowsAsObject()` chứa dữ liệu thật, không dump vào incident.
- `EXPLAIN`/query plan đôi khi tiết lộ schema hoặc index; chỉ gửi qua kênh nội bộ.
- SDK context có thể chứa statement, kể cả khi application không log nó trực tiếp.

## 16. KV và Sub-document: lỗi path cũng có thể chứa bí mật

Ví dụ:

```java
orders.mutateIn(
    orderId,
    List.of(
        MutateInSpec.replace(
            "shipping.tracking_code", trackingCode)
    )
);
```

Một lỗi `PathNotFound` có thể giúp phát hiện schema migration chưa hoàn tất. Nhưng không cần log:

- `orderId` raw.
- `trackingCode`.
- Toàn bộ `MutateInSpec` hay JSON event.
- Exception context có document ID.

Log an toàn:

```json
{
  "operation": "UPDATE_SHIPPING_STATUS",
  "category": "PATH_ERROR",
  "schema_contract": "order-v2",
  "logical_collection": "orders",
  "correlation_id": "2dc3ab1a-9f83-4d18-b7e5-3d8ef40c8ac9"
}
```

`schema_contract` là constant/enum do application định nghĩa. Không log raw path lấy từ HTTP query parameter.

### 16.1. Multi-spec mutation

Khi `mutateIn` chứa nhiều specs, một spec sai có thể khiến **cả mutation bị từ chối**. Để hỗ trợ chẩn đoán, ứng dụng có thể ánh xạ vị trí spec sang **tên logic**:

```text
operation=SHIP_ORDER
spec_group=shipping_and_audit
category=PATH_ERROR
```

Nếu SDK expose failure spec index trong error context, phải kiểm tra API/version và áp allowlist trước khi log; không serialize raw context chỉ để lấy index. Một mapping `spec index -> constant nghiệp vụ` giúp debug mà không in path/value.

### 16.2. Path "không tồn tại" chưa chắc lỗi server

Có thể là:

- Document V1/V2 khác schema.
- Java property `displayName` được lưu thành JSON `display_name`.
- Parent field bị ghi sai kiểu.
- Array index stale.
- Field optional bị thiếu hợp lệ.
- Scope/collection routing sai.

Diagnostic event nên ghi **schema code và error category**, không lộ raw document để “minh họa”.

## 17. CAS conflict và thông tin cần thu thập

CAS là token version do Couchbase Server quản lý. Với Spring Data `@Version` hoặc raw SDK `MutateInOptions.cas(...)`, CAS mismatch nghĩa là snapshot dùng để ghi đã stale.

**Thông tin hữu ích:**

- Operation cố ghi: `UPDATE_ORDER_STATUS`.
- Category: `CAS_CONFLICT`.
- Số lần application retry.
- Latency và contention rate.
- Logical collection, service/deployment version.
- Correlation ID.

**Không cần:**

- Full document body trước/sau.
- Raw document ID.
- User email, payload fields.
- Raw CAS token nếu không cần cho chẩn đoán (nó không phải số thứ tự nghiệp vụ).
- Exception message/context.

### 17.1. CAS mismatch không phải lý do lộ dữ liệu

Đừng log cả document `before` và `after` để “so sánh cho rõ”. Nếu cần chứng minh conflict do hot counter, ghi metric riêng `cas_conflict_total{operation="UPDATE_ORDER_STATUS"}` và measure write frequency, không in JSON profile.

### 17.2. Retry cần đọc lại state

CAS conflict rõ ràng cho phép đọc lại, revalidate business rule rồi retry có giới hạn. Không dùng log chứa bản sao body làm nguồn sự thật để quyết định retry.

## 18. Timeout: phân biệt outcome để không làm tăng tác dụng phụ

SDK phân biệt `AmbiguousTimeoutException` và `UnambiguousTimeoutException`. Với ambiguous timeout, server **có thể** đã commit mutation dù client không nhận response.

Đặc biệt nguy hiểm khi operation là:

- `MutateInSpec.increment("stats.views", 1)`.
- `MutateInSpec.arrayAppend("history", List.of(event))`.
- Tạo hoặc ghi một trạng thái thanh toán.
- Gửi event/message sau mutation.

Diagnostic cần có:

```text
operation=APPEND_ORDER_EVENT
category=TIMEOUT_AMBIGUOUS
outcome=UNKNOWN_COMMIT
retry_policy=RECONCILE_BEFORE_RETRY
```

Không ghi:

```text
event={"customer_email":"...","card_token":"..."}
```

### 18.1. Correlation không phải idempotency

`correlationId` nối các log của request. `operationId` phục vụ dedup command có side effects. Hai ID này có thể khác nhau và có vòng đời khác nhau.

Một request mới có thể retry **cùng operationId** nhưng tạo **correlationId mới**; đây là semantics hợp lệ. Nếu log operation ID raw có rủi ro linkability, dùng HMAC fingerprint hoặc metric không chứa ID.

### 18.2. Đối chiếu sau timeout

Service có thể dùng `lookupIn` để đọc `last_operation_id` hoặc state cần thiết. Dữ liệu readback dùng **trong memory để quyết định**, không tự in ra log. Log một kết quả tổng hợp:

```text
reconciliation=ALREADY_APPLIED
reconciliation=NOT_OBSERVED
reconciliation=INCONCLUSIVE
```

Không coi `NOT_OBSERVED` luôn là bằng chứng chưa commit: marker có thể bị ghi đè, write có thể pending hoặc có writer khác thay đổi state. Policy phải xét causal history và CAS.

## 19. Durability/replica failures: nội dung nào nên log?

Khi durability `MAJORITY` hoặc `PERSIST_TO_MAJORITY` không đáp ứng, điều hành cần biết:

- Operation category.
- Durability level được yêu cầu (**constant**, không secret).
- Elapsed time, timeout class.
- Cluster/zone logical alias.
- Replica availability metric theo monitoring.
- Outcome known/ambiguous.

Không cần credentials, full connection string, TLS truststore password, node URLs có token hoặc raw `ErrorContext`.

### 19.1. Không hạ yêu cầu độ bền để xử lý lỗi

Một diagnostic event tốt chỉ giúp xác định topology vấn đề. Nếu order write yêu cầu `MAJORITY`, không tự retry với `NONE` vì thấy exception, trừ khi có policy nghiệp vụ được phê duyệt. Đừng biến logging code thành nơi ra quyết định durability.

### 19.2. Endpoint names và network metadata

Host/IP/channel ID có thể cần cho on-call chuyên trách, nhưng là **thông tin hạ tầng nội bộ**; lưu ở hệ observability hạn chế quyền nếu cần, không xuất ra public API hoặc incident ticket rộng rãi.

## 20. Spring Data exception translation: unwrap có kiểm soát

Spring Data Couchbase có `CouchbaseExceptionTranslator` để chuyển một số SDK exceptions sang `org.springframework.dao.DataAccessException`. Điều này có ích cho application portability, nhưng làm đường chẩn đoán phức tạp hơn.

Ví dụ:

```java
try {
    return orderRepository.findById(orderId);
} catch (org.springframework.dao.DataAccessException ex) {
    // Không log ex/stack/message/cause.
    // Dùng category ứng dụng + correlation ID.
    safeDbLogger.recordFailure(
        correlationId,
        DbOperation.LOAD_ORDER,
        DbFailureCategory.DATA_ACCESS,
        elapsedMs
    );
    throw ex;
}
```

Đây là đoạn trong method có `elapsedMs` đã được đo. Nếu muốn phân loại sâu hơn, xem typed cause chain **trong memory**, không serialize nguyên cause.

### 20.1. Không giả định mọi lỗi repository đều do Couchbase Server

Có thể là:

- Mapping/serialization converter.
- Bean validation hoặc callback.
- Spring transaction/infrastructure.
- Lỗi connection.
- Lỗi từ custom domain code trong callbacks.
- DataAccessException từ một operation khác.

Nếu chỉ có `DataAccessException`, category `DATA_ACCESS` là fallback hợp lý. Tránh khẳng định tất cả là `QUERY_ERROR` hay `SERVER_DOWN` khi chưa có bằng chứng.

## 21. Async `CompletableFuture`: lỗi có thể bị bọc

Java SDK async API có thể trả `CompletableFuture`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import com.couchbase.client.java.kv.GetResult;

long startedAtNanos = System.nanoTime();
CompletableFuture<GetResult> request = orders.async()
    .get(orderId);

request.whenComplete((result, failure) -> {
    if (failure != null) {
        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - startedAtNanos);
        DbFailureCategory category =
            DbFailureClassifier.classify(failure);

        safeDbLogger.recordFailure(
            correlationId,
            DbOperation.LOAD_ORDER,
            category,
            elapsedMs
        );
    }
});
```

`elapsedMs` được tính khi future hoàn tất, từ mốc `startedAtNanos` trước lúc gửi request. Callback không in nguyên failure/SDK context.

### 21.1. Wrapper không phải nguyên nhân gốc

`CompletionException`/`ExecutionException` có thể bọc exception gốc. Duyệt cause chain **theo type** để phân loại. Không làm:

```java
log.error("async error", failure); // Có thể leak SDK context.
```

### 21.2. Callback logging cũng có thể thất bại

Diagnostic helper nên đơn giản và không chứa I/O block bất thường trên thread hoàn thành future. Nếu logger hoặc exporter là blocking sink, cấu hình async appender/bounded queue phù hợp; không tự gửi HTTP sync từ callback SDK hot path.

## 22. Reactive `Mono`: propagation và bẫy rò rỉ

Với Spring WebFlux và Couchbase reactive SDK:

```java
import reactor.core.publisher.Mono;
import com.couchbase.client.java.kv.GetResult;

Mono<GetResult> operation = Mono.defer(() -> {
    // Mỗi subscription có start time độc lập.
    long startedAtNanos = System.nanoTime();
    return orders.reactive().get(orderId)
        .doOnError(error -> {
            long elapsedMs =
                java.util.concurrent.TimeUnit.NANOSECONDS
                    .toMillis(
                        System.nanoTime() - startedAtNanos);

            DbFailureCategory category =
                DbFailureClassifier.classify(error);

            safeDbLogger.recordFailure(
                correlationId,
                DbOperation.LOAD_ORDER,
                category,
                elapsedMs
            );
        });
    });
```

Như async, `elapsedMs` cần đo theo từng **subscription**. `Mono.defer` ở ví dụ tạo mốc riêng mỗi lần subscribe; `correlationId` phải đến từ request context tin cậy và không được dùng chung tùy tiện giữa các yêu cầu. Khi cần metrics cho cả thành công/thất bại, có thể đo thêm ở `doFinally` với state scoped từng subscription.

### 22.1. Không dùng Reactor `log()` để dump dữ liệu nhạy cảm

`Mono.log()`/`Flux.log()` và các hook debug có thể ghi signals, lỗi, thậm chí value tùy cách cấu hình. Một query `Flux<OrderDocument>` có thể mang PII trong `toString()` của entity. Không bật operator logging đại trà ở production để debug Couchbase.

### 22.2. Không dùng MDC thread-local như thể reactive luôn cùng thread

`MDC` là thread-local trong nhiều logging implementations; Reactor có thể đổi thread. Gọi `MDC.put` ở HTTP thread rồi giả định mọi callback reactive nhận đúng context là không an toàn/không chính xác.

Thay vào đó:

- Mang correlation ID qua Reactor `Context` hoặc Micrometer context propagation khi cấu hình.
- Tạo diagnostic event từ ID đã kiểm soát tại điểm log.
- Dọn context khi kết thúc, tránh rò ID sang request khác.
- Test concurrent reactive requests để phát hiện cross-request contamination.

### 22.3. Reactive retry không được vô điều kiện

`retry(3)` với `mutateIn` chứa counter/array append có thể gửi lại request sau ambiguous timeout, gây double effect. Log category `TIMEOUT_AMBIGUOUS` và quyết định reconciliation ngoài generic retry operator.

## 23. HTTP error response: khách hàng chỉ cần mã lỗi và correlation ID

Không bao giờ trả:

```json
{
  "message": "Query failed SELECT ... WHERE email='lan@...'",
  "documentId": "customer::lan@example.test",
  "stackTrace": "com.couchbase...."
}
```

Một contract công khai tối thiểu:

```json
{
  "code": "ORDER_UPDATE_UNAVAILABLE",
  "message": "Không thể xử lý yêu cầu lúc này.",
  "correlationId": "c1b9fd71-7cf8-455d-af47-4e3f32472a38"
}
```

### 23.1. Mapping lỗi ra HTTP status có ngữ cảnh

| Domain outcome | HTTP gợi ý | Lưu ý |
| --- | --- | --- |
| Order không tồn tại, user có quyền biết | `404` | Nếu resource existence nhạy cảm, cần policy chống enumeration. |
| CAS conflict/state đổi | `409` | Không tiết lộ version/field bí mật. |
| Input không hợp lệ | `400` hoặc `422` | Chỉ trả tên rule công khai, không echo input sensitive. |
| DB unavailable/durability impossible | `503` | Có thể thêm retry guidance phù hợp. |
| Unknown/ambiguous mutation outcome | `202`/`503` hoặc mã workflow riêng | Không được tuyên bố chắc chắn failed; trả trạng thái tra cứu nếu thiết kế hỗ trợ. |

HTTP status không thể suy thẳng từ `CouchbaseException`; application cần mapping theo use case và yêu cầu privacy. Với ambiguous outcome, không tạo client retry loop gây tác dụng kép.

### 23.2. Global exception handler phải sanitize

Nếu `@RestControllerAdvice` serialize `ex.getMessage()` hoặc `Throwable` ra JSON, toàn bộ nỗ lực safe logging bị vô hiệu. Handler phải trả fixed message/code và trusted correlation ID; cause chỉ giữ nội bộ.

## 24. Couchbase SDK log redaction: đúng cơ chế hai giai đoạn

Couchbase Java SDK có hỗ trợ log redaction. Theo hướng dẫn chính thức, ứng dụng có thể thiết lập redaction level **trước khi SDK khởi tạo**:

```java
import com.couchbase.client.core.logging.LogRedaction;
import com.couchbase.client.core.logging.RedactionLevel;

// Đặt trước khi SDK/ClusterEnvironment bắt đầu ghi log.
LogRedaction.setRedactionLevel(RedactionLevel.FULL);
```

Sau đó SDK ghi các **redaction tags** vào log; khi cần xuất log để chia sẻ, dùng công cụ `cblogredaction` để obfuscate nội dung được đánh dấu. Hai giai đoạn này phục vụ **SDK-produced logs** theo định dạng hỗ trợ.

### 24.1. Vì sao không chỉ bật FULL rồi quên?

- `FULL` không tự xóa mọi `log.info("{}", userInput)` do application viết.
- Không tự sanitize Spring exception response, QueryResult dump hay traces do code riêng tạo.
- Log gốc có tags **vẫn cần được bảo vệ** trước khi chạy công cụ obfuscation/export.
- Các fields không được SDK đánh dấu/redact theo dự đoán của bạn có thể còn lộ.
- SDK và server logs là hai nguồn khác nhau, yêu cầu kiểm tra redaction riêng.

### 24.2. Các redaction levels

Theo SDK core logging API:

- `NONE`: không thực hiện redaction (mặc định của SDK theo Javadoc).
- `PARTIAL`: redact user data; chưa chắc redact system/metadata.
- `FULL`: redact user, system và metadata theo cơ chế của SDK.

**Không dùng redaction level như authorization**. Trước khi gửi support bundle, thực hiện thử nghiệm secret sentinel để đảm bảo không còn credential/PII trong file đã export.

### 24.3. Thứ tự startup

Nếu khởi tạo `Cluster` rồi mới gọi `LogRedaction.setRedactionLevel(...)`, một số log startup có thể đã ghi mà không có tags mong muốn. Đặt cấu hình trước SDK initialization theo tài liệu, sau đó xác minh log đầu tiên trong integration environment.

## 25. SDK event bus: không `System.out.println(event)` trong production

Java SDK cung cấp event bus để theo dõi hoạt động như endpoint connection/retry. Một consumer đơn giản:

```java
environment.eventBus().subscribe(event -> {
    // Không đưa nguyên event vào log hoặc stdout:
    // System.out.println(event);
});
```

Nguyên object event có thể chứa endpoint names, configuration và context khác. Cần:

1. Chỉ subscribe loại event có ích.
2. Map event thành **category/metric**.
3. Không serialize full event.
4. Không block trong callback (tài liệu SDK cảnh báo event bus consumer hot path).
5. Dùng async bounded queue nếu phải gửi sang sink chậm.
6. Hạn chế quyền dashboard chứa network diagnostics.

### 25.1. Ví dụ category-based metrics

```text
couchbase_connection_event_total{
  service="kv",
  category="endpoint_unavailable"
}
```

Đừng đặt `remote_address` hoặc user-controlled path thành label nếu không có yêu cầu rất đặc biệt và policy rõ.

## 26. Tracing: chỉ dùng safe attributes

OpenTelemetry tracing giúp theo dõi một request đi qua HTTP → service → repository/SDK → Couchbase. SDK Java hỗ trợ request tracing và có các cấu hình threshold logging tracer.

Một span có thể mang attributes như:

```text
db.system=couchbase
db.operation.name=mutateIn
app.db.operation=UPDATE_ORDER_STATUS
app.db.failure_category=CAS_CONFLICT
app.db.logical_collection=orders
```

Tuy nhiên, các attributes như `db.statement`, `db.query.parameter.email`, `db.document_id` hoặc HTTP headers có thể tiết lộ PII/secret.

### 26.1. Parent span và correlation

SDK hỗ trợ gắn parent span trên một số operation options; Javadoc/version cụ thể quyết định fluent API. Một trace ID được quản lý đúng có thể là cầu nối giữa HTTP request và SDK request. **Không cần** nhét full query/document ID vào span để trace hữu ích.

### 26.2. Sampling không che dữ liệu

Sampling 1% traces giảm volume, **không giảm độ nhạy của trace được chọn**. Một trace có token vẫn là leak. Trước khi cấu hình sampler, phải sanitize attributes và exporter destinations.

### 26.3. Threshold logging tracer

Couchbase SDK có tracer thống kê các requests vượt threshold và xuất periodically. Format có thể thay đổi giữa versions; không parse một JSON raw tracer output như API ổn định hay đưa toàn bộ vào public support channel.

## 27. Metrics: loại lỗi và latency, tuyệt đối tránh high-cardinality labels

Couchbase Java SDK có metrics durations theo percentile; có thể tích hợp Micrometer/OpenTelemetry. Ứng dụng có thể thêm metrics riêng:

```text
db_operation_total{
  operation="UPDATE_ORDER_STATUS",
  db_service="kv",
  category="CAS_CONFLICT"
}

db_operation_duration_seconds{
  operation="LOAD_ORDER",
  db_service="kv"
}
```

### 27.1. Labels nên và không nên dùng

| Nên | Tránh |
| --- | --- |
| Operation enum | Document ID |
| Error category enum | Email, phone, JWT |
| Logical collection alias | User/tenant ID raw khi có nhiều giá trị |
| Bounded status/outcome | Correlation ID, trace ID |
| Durability level enum | SQL statement text |
| Deployment version | Raw exception message |
| Fixed service type | Arbitrary URL/endpoint path |

Một metric label `document_id` có thể tạo hàng triệu time-series và rò business identities. Dùng **tracing/log correlation** cho request đơn lẻ, metrics cho phân phối và xu hướng.

### 27.2. Ngưỡng cảnh báo hữu ích

- `CAS_CONFLICT` rate tăng bất thường.
- `TIMEOUT_AMBIGUOUS` xuất hiện trên mutation non-idempotent.
- `PATH_ERROR` tăng sau deploy/schema change.
- p95/p99 `mutateIn` hoặc query latency vượt SLO.
- Query errors tăng do index not found.
- Số request đang retry hoặc request cancellations tăng.
- Replica/durability errors trong thời gian failover.

Alert payload cũng phải qua allowlist; đừng gửi raw exception vào Slack/email/on-call notification.

## 28. Mã nguồn mẫu: một decorator chẩn đoán an toàn

Ví dụ sau giữ logic business ở adapter, tạo log chỉ từ constant/enum. Nó **không** tạo ra stack trace công khai hoặc in raw `ErrorContext`.

```java
import java.util.Objects;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

public final class SafeDbExecutor {

    private final SafeDbLogger logger;

    public SafeDbExecutor(SafeDbLogger logger) {
        this.logger = Objects.requireNonNull(logger);
    }

    public <T> T call(
            String trustedCorrelationId,
            DbOperation operation,
            Supplier<T> request) {

        long startNanos = System.nanoTime();
        try {
            return request.get();

        } catch (RuntimeException failure) {
            long elapsedMs = TimeUnit.NANOSECONDS
                .toMillis(System.nanoTime() - startNanos);

            DbFailureCategory category =
                DbFailureClassifier.classify(failure);

            logger.recordFailure(
                trustedCorrelationId,
                operation,
                category,
                elapsedMs
            );

            // Application error boundary sẽ map exception sang
            // response sanitized. Không auto-log Throwable tại đó.
            throw failure;
        }
    }
}
```

Cách dùng:

```java
OrderDocument loaded = safeDbExecutor.call(
    correlationId,
    DbOperation.LOAD_ORDER,
    () -> repository.findById(orderId)
        .orElseThrow()
);
```

Đây là skeleton Java sync; không dùng generic decorator này cho reactive API vì nó chỉ đo thời gian **tạo publisher**, không phải latency của I/O khi subscribe.

### 28.1. Không nuốt lỗi hoặc biến failure thành `null`

Decorator giữ exception để domain quyết định. Nếu một repository lookup không có document và nghiệp vụ xem là bình thường, có thể xử lý `Optional.empty()` trước thay vì biến thành `ERROR`. Tránh biến tất cả thành null vì mất semantics và có thể gây lỗi khác về sau.

### 28.2. Một điểm log hay nhiều điểm log?

Chọn điểm log **rõ ràng** để tránh một lỗi bị ghi ba lần ở gateway, service và controller. Nếu nhiều lớp ghi, dùng cùng correlation ID nhưng khác event code và chỉ một lớp ghi `db_operation_failure`. Đếm metric một lần theo **attempt** hoặc **business request**, ghi rõ convention.

## 29. Trải nghiệm người dùng khi lỗi và quyền riêng tư

Một API an toàn cần trả thông tin để người dùng hành động nhưng không lộ internals.

Ví dụ:

```text
Mã lỗi: ORDER_UPDATE_CONFLICT
Yêu cầu có trạng thái mới. Vui lòng tải lại đơn hàng.
Mã tham chiếu: c1b9fd71-...
```

Thông tin này đủ hơn “Database failed” và an toàn hơn “CAS mismatch key=customer::...”.

### 29.1. Tránh enumeration

Một attacker có thể thử nhiều document IDs và nhìn response phân biệt 404/403 để biết tài khoản tồn tại. Trong các luồng nhạy cảm, error mapping và timing nên được thiết kế để không tiết lộ resource existence trái phép.

### 29.2. Chia sẻ correlation ID có an toàn tuyệt đối không?

Correlation ID thường ít nhạy cảm hơn PII, nhưng có thể là token để người khác truy vấn log nếu hệ thống thiết kế không đúng. Không dùng correlation ID như credential hoặc authorization. Dashboard lookup phải kiểm tra quyền độc lập.

## 30. Multi-tenant và data residency

Nếu database chứa nhiều tenants:

- Không ghi tenant ID raw trên metrics labels/log chung.
- Dùng logical service/cluster alias; chỉ người có quyền mới resolve alias → tenant.
- Không cho tenant A truy cập logs/traces của tenant B.
- Nếu cần HMAC fingerprint, scope theo tenant và phân quyền phép resolve.
- Chọn region/log retention phù hợp dữ liệu được phép lưu.
- Hạn chế cross-region exports của trace có business identifiers.
- Ghi nhận ai đã tạo support bundle và ai đã tải xuống.

Một log đã "che email" nhưng còn account ID, tenant ID hoặc correlation ngược lại có thể vẫn định danh cá nhân. Sanitization phải xét **khả năng liên kết dữ liệu**, không chỉ so khớp regex email.

## 31. Log retention, phân quyền và hỗ trợ sự cố

Một hệ thống production cần chính sách cụ thể cho cả application logs lẫn SDK/server diagnostics.

### 31.1. Vòng đời diagnostic data

1. **Collect:** chỉ schema allowlist.
2. **Process:** redact/tokenize ở boundary gần nguồn.
3. **Transmit:** TLS đến collector, giới hạn destinations.
4. **Store:** encrypt at rest, RBAC và audit access.
5. **Query:** least privilege, truy vấn có rate/authorization.
6. **Export:** cần mục đích, phê duyệt, scrub và kiểm tra sentinel.
7. **Expire:** retention ngắn hợp lý theo policy.
8. **Delete:** xóa bản copy không cần, kể cả incident attachment nếu có thể.

### 31.2. SDK redaction và application sanitization là hai tầng khác nhau

| Tầng | Trách nhiệm |
| --- | --- |
| Application code | Không tạo raw sensitive diagnostic event. |
| Logger encoder | Escape/control format, không thêm user values. |
| SDK redaction | Đánh dấu sensitive SDK fields cho quá trình obfuscation. |
| Collector/processor | Áp policy secondary, hạn chế routing, filter attributes. |
| Storage/retention | Access control, lifecycle và audit. |
| Support export | Chạy scrub, kiểm soát tài liệu đã xuất. |

Không có một tầng nào đủ nếu tất cả tầng còn lại tùy tiện xuất secrets.

## 32. Runbook triage một lỗi Couchbase mà không cần document body

Giả sử p99 của `UPDATE_ORDER_STATUS` tăng và error rate cao. Điều tra theo thứ tự:

1. **Triage scope:** môi trường, logical service, deployment version, thời gian.
2. **Category:** CAS_CONFLICT, TIMEOUT_AMBIGUOUS, PATH_ERROR, QUERY_ERROR hay UNAVAILABLE?
3. **Volume:** số requests, retries, p95/p99, error ratio và hot key metrics tổng hợp.
4. **Correlate:** dùng correlation ID/trace ID được quản lý để nối request với spans.
5. **Cluster health:** xem replica availability, disk/network, node/failover từ monitoring đã phân quyền.
6. **Query/index:** nếu liên quan SQL++, kiểm tra index state và query consistency; không in statement có bind values.
7. **Schema:** nếu PATH_ERROR tăng sau deploy, so sánh storage contract versions và migrations.
8. **Concurrency:** nếu CAS_CONFLICT, xem tỷ lệ writes/operation, không dump raw entity.
9. **Ambiguity:** nếu mutation timeout, chạy reconciliation theo operation ID; không retry mù.
10. **Escalate:** chỉ khi tín hiệu chưa đủ, yêu cầu diagnostic artifact đã scrub qua kênh phân quyền.

### 32.1. Ví dụ sự cố sau deploy

```text
16:00 release order-service build=abc123
16:03 PATH_ERROR UPDATE_ORDER_STATUS rate +15x
16:04 read-only metrics: query healthy, KV latency normal
16:05 schema_contract=order-v3, affected only new release
```

Từ thông tin trên có thể nghi path mismatch do đổi `shipping.status` sang tên JSON khác; **không cần** công khai document ID hay tracking code. Xác minh ở test/staging bằng synthetic fixture và sửa code/rollback hợp lý.

## 33. Test bảo mật: secret sentinel phải không xuất hiện trong logs

Unit test thường chỉ kiểm tra “có gọi log.warn không”, chưa đủ. Cần test thực tế nơi logger/encoder/sink nhận dữ liệu.

### 33.1. Bộ secret giả định

Dùng dữ liệu **giả**:

```text
SENTINEL_PASSWORD_7f83
SENTINEL_JWT_4a62
SENTINEL_CUSTOMER_EMAIL_test@example.invalid
SENTINEL_DOCUMENT_ID_96ba
SENTINEL_SQL_PARAM_81bc
```

Đặt chúng vào:

- Document ID.
- SQL++ bind parameter.
- Query statement literal trong test anti-pattern.
- `Exception.getMessage()`, cause chain và synthetic context.
- HTTP header user-provided.
- Entity `toString()`.
- Reactor error signal.
- SDK event/log mô phỏng đã qua adapter.

### 33.2. Assertion cốt lõi

```java
String logs = capturedStructuredLogs();

assert !logs.contains("SENTINEL_PASSWORD_7f83");
assert !logs.contains("SENTINEL_JWT_4a62");
assert !logs.contains("SENTINEL_DOCUMENT_ID_96ba");
assert !logs.contains("SENTINEL_SQL_PARAM_81bc");

assert logs.contains("UPDATE_ORDER_STATUS");
assert logs.contains("CAS_CONFLICT");
```

Đây là minh họa assertions; cần triển khai `capturedStructuredLogs()` bằng test appender/collector giả của logging stack đang dùng. Không log secrets thật chỉ để test redaction.

### 33.3. Negative test quan trọng

Cố tình gọi `log.error("failed", exception)` trong một nhánh test *cô lập không export* để chứng minh logger có thể chứa secret từ `getMessage()`/`ErrorContext`. Sau đó xác nhận production adapter không dùng pattern đó. Không gửi kết quả negative test chứa sentinel ra external monitoring ngoài phạm vi.

## 34. Test exception chain và fallback

Một classifier có thể gặp:

- `CompletionException(CouchbaseException)`.
- Spring `DataAccessException(CouchbaseException)`.
- `CouchbaseException` với `context()==null`.
- Cause chain rất dài.
- Một `RuntimeException` có message chứa fake token.

Các test cần chứng minh:

1. Classifier trả category theo type.
2. Không gọi `getMessage()`/`toString()` trong logger.
3. Unknown exception ra `UNKNOWN`.
4. Exception không bị swallow.
5. Public API response không chứa token.
6. Không log stack trace không kiểm duyệt tại global handler.

Đừng dùng regex thay toàn bộ secret rồi tin là đủ: một value chưa từng thấy regex sẽ lọt ra. **Allowlist fields** là cơ chế chính.

## 35. Test SQL++ và sub-document diagnostics

### 35.1. SQL++ parameter binding

Tạo query template `FIND_ORDERS_BY_CUSTOMER`, dùng input chứa sentinel email. Khi query bị lỗi index hoặc timeout, log phải chứa category/template ID nhưng **không** chứa email, statement chứa literal hay bind values.

### 35.2. Sub-document path lỗi

Trên test collection, gửi `replace` vào JSON path thiếu. Diagnostic chỉ ghi:

```json
{
  "operation": "UPDATE_SHIPPING_STATUS",
  "category": "PATH_ERROR",
  "schema_contract": "order-v2"
}
```

Test raw `Exception.getMessage()` có thể có documentId; **không log** nó.

### 35.3. CAS conflict

Gây stale CAS trên fixture riêng, log chỉ `CAS_CONFLICT`, đo latency, retry count. Không log bản sao trước/sau entity hoặc CAS token raw.

### 35.4. Ambiguous timeout

Dùng failure injection/test double để mô phỏng “server đã commit nhưng response bị mất”. Log `TIMEOUT_AMBIGUOUS`/`UNKNOWN_COMMIT`, chạy reconciliation theo operation ID trong memory; không log event body hoặc tự retry increment.

## 36. Test reactive và context isolation

Tạo hai request song song A/B với correlation IDs khác nhau, publishers thực thi trên scheduler khác nhau. Kiểm tra:

- Log của A không có ID của B.
- Log của B không có ID của A.
- Không có raw entity `toString()` hay Reactor `log()`.
- MDC được cleanup hoặc dùng Reactor Context propagation đúng.
- Publisher được subscribe một lần theo design.
- Metrics labels không chứa correlation ID.

Test nên chạy trên logging/observability stack thật trong integration environment, vì mock đơn lẻ không phát hiện cross-thread MDC leakage.

## 37. Ma trận kiểm thử production-readiness

| Nhóm | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| SDK context | Có `documentId` chứa email | Không đi vào application log. |
| SDK context | `service.statement` có literal | Không đi vào log/traces. |
| SDK context | `context()==null` | Safe fallback event vẫn tạo được. |
| SDK context | SDK nâng version, thêm field mới | Schema allowlist không đổi/lộ field. |
| Exception | Nested causes chứa bearer token | Không in raw stack/message. |
| Spring translation | `DataAccessException` bọc SDK error | Category đúng hoặc safe fallback. |
| Async | `CompletionException` | Unwrap theo type, không log wrapper raw. |
| Reactive | `Mono.onError` | Safe event, không dump signal payload. |
| Reactor context | Hai concurrent requests | Không rò correlation ID chéo. |
| Correlation | User gửi ID có newline | Reject/regenerate safe ID. |
| Identity | Document key chứa email/tenant | Không log raw. |
| HMAC | ID có không gian nhỏ | Không dùng plain hash; scoped key rotation. |
| Query | Named parameters | Values không có trong logs. |
| Query | Statement literal chứa secret | Không export raw statement. |
| KV | PathNotFound | Category + contract code, không document body. |
| CAS | Stale `@Version` | Conflict metric, không in entity. |
| Timeout | Ambiguous result | Outcome unknown, reconcile, không blind retry. |
| Durability | Majority failure | Log level/code, không node credentials. |
| SDK redaction | FULL trước init | Log được tag, export được scrub đúng. |
| Application logging | FULL đang bật | Vẫn không log raw application input. |
| Event bus | Endpoint event | Map category, không print object. |
| Tracing | `db.statement`/params | Không xuất sensitive attributes. |
| Metrics | Label cardinality | Không document/user/trace IDs. |
| HTTP API | Internal exception | Chỉ safe error code + correlation. |
| Multi-tenant | Tenant A tìm log B | Bị RBAC từ chối. |
| Retention | Logs hết thời hạn | Bị xóa theo policy. |
| Support export | Shared artifact | Qua review/redaction và access audit. |
| Collector | Processor lỗi | Không fallback dump raw payload. |

## 38. Bài thực hành

### Bài 1 — Xác định sensitive fields trong `ErrorContext`

Tạo lỗi KV timeout trên test cluster với document ID giả chứa email. Xem tài liệu SDK và nhận diện các trường có thể xuất hiện. Thiết kế allowlist riêng cho application, **không** log raw context.

### Bài 2 — Safe diagnostic schema

Thiết kế JSON event gồm operation, category, durationMs, correlation ID, db service và logical collection. Viết JSON Schema/test để từ chối field `payload`, `documentId`, `sql`, `password`, `exceptionMessage`.

### Bài 3 — Exception classifier

Tạo classifier cho `DocumentNotFound`, `CasMismatch`, ambiguous/unambiguous timeout và unknown. Test nested causes/`DataAccessException`, xác minh không dùng `getMessage()` để phân loại.

### Bài 4 — HTTP handler sanitized

Tạo Spring `@RestControllerAdvice` trả `code` và `correlationId`. Dùng exception fake chứa sentinel JWT trong message, kiểm tra response không có sentinel và không lộ stack trace.

### Bài 5 — HMAC fingerprint có khóa

Chỉ khi use case cần, viết `HMAC-SHA256` token cho document key trên test. So sánh với SHA-256 không khóa và giải thích dictionary attack trên email/phone. Thực hiện key rotation/version và không xuất secret.

### Bài 6 — SQL++ parameterization

Chuyển query literal customer email sang named parameter. Khi cố gây query/index error, log operation template ID; khẳng định email và bound parameters không có trong log/trace.

### Bài 7 — Sub-document lỗi path

Trên fixture order V2, gửi `replace` vào path thiếu và một multi-spec mutation có lỗi. Ghi category `PATH_ERROR` và contract code, đọc lại raw JSON **trong test assertion**, nhưng không log document trong production.

### Bài 8 — CAS và retry

Gây CAS mismatch giữa hai writers; log conflict rate và attempt count nhưng không log CAS token/document body. Viết retry đọc lại state trước khi gửi tiếp, giới hạn attempts.

### Bài 9 — Timeout mơ hồ

Giả lập response mất sau `increment`/`arrayAppend`. Dùng operation ID đối chiếu trong memory, log `UNKNOWN_COMMIT`/`RECONCILED`; không retry vô điều kiện hoặc log event JSON.

### Bài 10 — SDK log redaction

Bật `LogRedaction.setRedactionLevel(RedactionLevel.FULL)` trước khi tạo cluster trong test environment. Kiểm tra log tags và chạy quy trình `cblogredaction` khi export. Dùng synthetic sentinel để chứng minh app logger riêng vẫn cần allowlist.

### Bài 11 — Event bus và telemetry

Cấu hình SDK event bus/threshold logging tracer trong test. Chỉ map event thành metric categories, không in `event.toString()`. Kiểm tra callback không block.

### Bài 12 — Metrics cardinality

Tạo metric `db_operation_total` gắn operation/category/service labels. Tạo test ngăn document ID, tenant ID, trace ID, email làm label. Đánh giá ảnh hưởng high-cardinality lên hệ metric.

### Bài 13 — Reactive MDC isolation

Chạy đồng thời hai `Mono` với correlation IDs khác nhau; thử context propagation. Assert không rò ID chéo giữa requests và không phát ra raw `onNext` entity values.

### Bài 14 — Support incident export

Giả lập một sự cố trong staging, chuẩn bị bundle gồm safe application logs, metrics, traces đã scrub và SDK logs qua công cụ redaction. Viết checklist approve/download/retention/deletion, test secret sentinel.

### Bài 15 — Security regression sau SDK upgrade

Giữ một test suite chứa synthetic `ErrorContext` cũ và mới (có thêm trường lạ). Đảm bảo chỉ dữ liệu allowlist được xuất và code vẫn hoạt động khi context null/volatile. Không parse JSON context cứng rồi log fallback.

## 39. Câu hỏi tự kiểm tra

1. Vì sao log nguyên `CouchbaseException` có thể tiết lộ `documentId` hoặc SQL++ statement?
2. `CouchbaseException.context()` có luôn khác null không?
3. Tên/value fields trong `ErrorContext` có ổn định giữa SDK versions không?
4. Những trường nào đủ để nhận diện một CAS conflict mà không log document body?
5. Vì sao một document key dạng `customer::email` là dữ liệu nhạy cảm?
6. Vì sao `log.error("failed", exception)` không an toàn theo mặc định?
7. Dùng SLF4J placeholder có tự redact input không?
8. Khác biệt giữa allowlist và blacklist/regex redaction là gì?
9. Khi nào một logical collection alias an toàn hơn bucket/scope/collection raw?
10. Application correlation ID khác SDK request ID như thế nào?
11. Correlation ID có phải idempotency key không?
12. Vì sao không nên tin `X-Request-ID` do client tự gửi?
13. Vì sao plain SHA-256 của email không đủ bảo vệ privacy?
14. HMAC fingerprint cần bảo vệ và rotation key thế nào?
15. HMAC token có phải dữ liệu ẩn danh tuyệt đối không?
16. Khi nào không cần fingerprint document ID?
17. Vì sao SQL++ named parameters vẫn có thể leak qua logging?
18. Vì sao chỉ log query template ID thay raw statement?
19. SQL++ parameterization có bảo vệ dynamic bucket/field identifiers tự do không?
20. `@Field` và schema version có thể giúp debug PATH_ERROR bằng cách nào?
21. Vì sao không nên log `MutateInSpec` hoặc request options nguyên object?
22. Sub-document multi-spec failure có nghĩa đã commit một phần không?
23. `CasMismatchException` khác `AmbiguousTimeoutException` trong retry ra sao?
24. Vì sao không được retry mù `increment` và `arrayAppend`?
25. Khi gặp ambiguous write, nên log outcome gì?
26. Có nên log `last_operation_id` raw để điều tra retry không?
27. `DurabilityLevel.MAJORITY` có loại bỏ nhu cầu bảo vệ credentials trong log không?
28. Spring `DataAccessException` có thể bọc SDK cause không?
29. Khi classifier không nhận diện lỗi, nên trả category nào?
30. Vì sao không dùng `getMessage()` để điều khiển domain policy?
31. Một `CompletionException` nên được xử lý như thế nào?
32. Reactor `Mono.log()` có những rủi ro gì?
33. Vì sao MDC thread-local dễ sai trên WebFlux?
34. OpenTelemetry sampling có tự xóa dữ liệu bí mật trong spans không?
35. Những metric labels nào gây high cardinality và nguy cơ lộ PII?
36. SDK `RedactionLevel.FULL` có tự sửa application log và HTTP response không?
37. Vì sao log redaction của SDK là quy trình hai giai đoạn?
38. Vì sao phải bật redaction trước SDK initialization?
39. Event bus callback có nên block để gửi HTTP đến log collector không?
40. Một public HTTP 404 có thể tiết lộ resource existence trong trường hợp nào?
41. Vì sao support bundle cần riêng authorization và retention?
42. Test secret sentinel nên đưa dữ liệu giả vào những nguồn nào?
43. Vì sao kiểm tra trên mock logger chưa đủ?
44. Có nên log raw IP/host/channel ID vào dashboard rộng rãi không?
45. Khi lỗi SQL++ không thấy record ngay sau KV mutation, vì sao phải xem GSI consistency?
46. Khi PATH_ERROR tăng sau release, làm thế nào điều tra không cần mở customer JSON?
47. Vì sao không nên tắt retry policy chỉ dựa trên text của error?
48. Những điều kiện nào khiến một event chẩn đoán được coi là “an toàn nhưng đủ hữu ích”?

## 40. Tài liệu tham khảo

- [Couchbase Java SDK — Handling Errors](https://docs.couchbase.com/java-sdk/current/howtos/error-handling.html): `CouchbaseException`, `ErrorContext`, ambiguous/unambiguous timeout, retries và trường context có thể biến đổi.
- [Couchbase Java SDK — Error Messages](https://docs.couchbase.com/java-sdk/current/ref/error-codes.html): loại exception và phân loại lỗi theo service.
- [Couchbase Java SDK — Logging & Log Redaction](https://docs.couchbase.com/java-sdk/current/howtos/collecting-information-and-logging.html): SLF4J, event bus, `LogRedaction`, `RedactionLevel` và `cblogredaction`.
- [Couchbase Java SDK — Request Tracing](https://docs.couchbase.com/java-sdk/current/howtos/observability-tracing.html): threshold tracing, OpenTelemetry và parent spans.
- [Couchbase Java SDK — Metrics Reporting](https://docs.couchbase.com/java-sdk/current/howtos/observability-metrics.html): `LoggingMeter`, Micrometer và OpenTelemetry metrics.
- [Couchbase JVM Core IO — RedactionLevel](https://docs.couchbase.com/sdk-api/couchbase-core-io/com/couchbase/client/core/logging/RedactionLevel.html): semantics `NONE`, `PARTIAL` và `FULL`.
- [Spring Data Couchbase — CouchbaseExceptionTranslator](https://docs.spring.io/spring-data/couchbase/docs/current/api/org/springframework/data/couchbase/core/CouchbaseExceptionTranslator.html): translation sang Spring `DataAccessException`.
- [Spring Data Couchbase — Template](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): các operations và đường Spring Data/SDK.
- [Couchbase Java SDK — Query Operations](https://docs.couchbase.com/java-sdk/current/howtos/n1ql-queries-with-sdk.html): SQL++ parameter binding và QueryOptions.
- [Spring Observability — Micrometer Observation](https://docs.spring.io/spring-framework/reference/integration/observability.html): quy tắc instrument và correlation.
- [OpenTelemetry — Semantic Conventions for Database Client Spans](https://opentelemetry.io/docs/specs/semconv/database/database-spans/): các thuộc tính database và rủi ro gắn sensitive attributes.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data minimization, log injection, confidentiality và vận hành logs.

> **Kết luận:** Hãy chẩn đoán lỗi Spring Data Couchbase bằng **phân loại exception theo type, operation code cố định, correlation ID tin cậy, latency, retry/outcome và metrics**, không phải bằng cách in raw `CouchbaseException`, `ErrorContext`, SQL++, document ID hay JSON body. `ErrorContext` có ích cho điều tra nhưng có thể chứa bí mật và có schema volatile; SDK log redaction là một tầng bảo vệ bổ sung, không thay application allowlist. Với CAS, timeout mơ hồ và durability, giữ nguyên semantics nghiệp vụ và thực hiện reconciliation đúng cách. **Khả năng quan sát tốt phải làm giảm thời gian xử lý sự cố mà không tạo thêm sự cố rò rỉ dữ liệu.**

