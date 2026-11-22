# Che dữ liệu trong log, trace và thông báo lỗi

Ứng dụng Spring Data Elasticsearch thường xử lý document chứa thông tin khách hàng, đơn hàng, địa chỉ, nội dung tìm kiếm, dữ liệu nội bộ và đôi khi cả thông tin xác thực. Những dữ liệu này có thể vô tình xuất hiện ở nhiều nơi ngoài Elasticsearch: log ứng dụng, exception message, HTTP client log, distributed trace, metric tag, dead-letter record và thông báo lỗi trả về API.

Che dữ liệu (redaction/masking) là một phần của thiết kế bảo mật. Mục tiêu là giữ đủ thông tin để vận hành, điều tra lỗi và theo dõi request, đồng thời hạn chế việc ghi hoặc phát tán dữ liệu nhạy cảm.

Một nguyên tắc thực tế là chỉ ghi những gì người vận hành cần để trả lời câu hỏi kỹ thuật: request nào, thao tác nào, index nào, kết quả thành công hay thất bại, lỗi thuộc nhóm nào và mất bao lâu. Không cần ghi toàn bộ document, query body, token, password hoặc exception message nguyên bản để đạt được mục tiêu đó.

Trong bài này, “che dữ liệu” bao gồm:

- **Redaction:** loại bỏ hoàn toàn giá trị nhạy cảm khỏi log/trace/response.
- **Masking:** thay một phần giá trị bằng ký tự che, ví dụ `***1234`, khi phần còn lại vẫn cần cho vận hành.
- **Pseudonymization:** thay giá trị bằng mã ổn định hoặc HMAC để liên kết các sự kiện mà không lộ giá trị gốc.
- **Minimization:** không thu thập trường dữ liệu ngay từ đầu nếu không có mục đích cần thiết.

Che dữ liệu phải được thực hiện tại ranh giới phát sinh dữ liệu và trước khi dữ liệu đi vào hệ thống quan sát. Một bộ lọc log ở cuối pipeline có thể hữu ích, nhưng không nên là lớp bảo vệ duy nhất.

## 1. Những nơi dữ liệu nhạy cảm có thể bị lộ

Một luồng xử lý document có thể đi qua nhiều thành phần:

```text
HTTP request
    |
    v
Controller / validation
    |
    v
Service / domain logic
    |
    v
Spring Data Elasticsearch
    |
    v
Elasticsearch Java client / HTTP transport
    |
    v
Elasticsearch cluster

Các điểm quan sát song song:
  - Application logs
  - Exception messages / stack traces
  - Distributed traces / span attributes
  - Metrics labels
  - Audit events
  - API error responses
  - Reverse proxy / gateway / APM agent logs
```

Ví dụ document:

```json
{
  "customer_id": "C-10001",
  "name": "Nguyen Van A",
  "email": "customer@example.com",
  "phone": "+84 901 234 567",
  "address": "12 Example Street",
  "order_id": "O-2026-001",
  "payment_token": "tok_live_secret_value",
  "status": "PAID"
}
```

Các giá trị `email`, `phone`, `address` và payment token không nên xuất hiện nguyên văn trong log hoặc trace thông thường. Ngay cả `customer_id` và `order_id` cũng có thể là dữ liệu nhạy cảm theo chính sách nội bộ, vì chúng cho phép liên kết hoạt động của một cá nhân hoặc giao dịch.

### 1.1. Những nguồn rò rỉ thường gặp

| Nguồn | Rủi ro |
|---|---|
| `log.info("Document: {}", entity)` | `toString()` có thể in toàn bộ field của entity. |
| `log.error("Failed: {}", exception.getMessage())` | Message có thể chứa query, index, URL, field value hoặc payload. |
| `log.error("Request failed", exception)` | Stack trace/cause message có thể chứa dữ liệu đầu vào. |
| HTTP wire logging | Có thể ghi Authorization header, request body và response body. |
| Elasticsearch query logging | Query DSL có thể chứa email, phone, địa chỉ hoặc từ khóa người dùng nhập. |
| Trace span attributes | Có thể lưu URL, query string, request header, document ID hoặc exception description. |
| MDC/baggage | Dữ liệu được gắn vào context có thể tự động xuất hiện trên mọi log/span. |
| API error response | Trả nguyên exception message hoặc stack trace cho client. |
| Metric label | Dùng email, ID hoặc query làm tag tạo rò rỉ và cardinality rất cao. |
| Debug dump/dead-letter | Lưu toàn bộ source document trong log hoặc kho lỗi không có kiểm soát. |

## 2. Phân loại dữ liệu trước khi ghi log

Không nên quyết định che dữ liệu chỉ dựa vào tên field. Hãy xác định mức độ nhạy cảm và mục đích sử dụng.

Một cách phân loại thực tế:

| Nhóm | Ví dụ | Cách xử lý mặc định |
|---|---|---|
| Bí mật xác thực | Password, API key, bearer token, refresh token, private key, cookie | Không log; redaction tuyệt đối. |
| Dữ liệu cá nhân | Email, số điện thoại, tên, địa chỉ, định danh cá nhân | Không log giá trị thô; mask hoặc pseudonymize nếu có mục đích được phê duyệt. |
| Dữ liệu giao dịch | Payment token, tài khoản, mã giao dịch, nội dung đơn hàng | Chỉ ghi ID nội bộ cần thiết đã được phân loại; loại bỏ payload. |
| Nội dung người dùng | Search term, free text, comment, file name | Không log mặc định; có thể chứa thông tin cá nhân hoặc bí mật. |
| Metadata kỹ thuật | Operation, index alias, HTTP status, duration, retry count | Có thể log nếu không chứa thông tin nhạy cảm và không tiết lộ cấu trúc nội bộ không cần thiết. |
| Correlation metadata | Trace ID, request ID, job ID | Thường được phép dùng để liên kết sự kiện, nhưng không nhúng PII vào giá trị. |

Đối với mỗi field, ghi lại:

1. Mục đích thu thập.
2. Ai có thể truy cập log/trace.
3. Giá trị cần thiết là giá trị thô, masked hay pseudonymous.
4. Thời gian lưu giữ.
5. Cách xóa hoặc xử lý khi dữ liệu không còn cần thiết.

### 2.1. Không dùng một quy tắc mask cho mọi field

Ví dụ:

- API token: loại bỏ hoàn toàn, kể cả phần đầu/cuối.
- Email: có thể mask phần local part nếu đội vận hành cần nhận biết cùng địa chỉ trong một sự kiện.
- Phone: chỉ giữ một vài chữ số cuối nếu chính sách cho phép.
- Document ID: có thể dùng HMAC để liên kết sự kiện mà không công khai ID gốc.
- Search text: thường loại bỏ vì có thể chứa bất kỳ dữ liệu nào.

Không tự suy luận rằng một giá trị an toàn chỉ vì nó không giống email hoặc số điện thoại. Dữ liệu nhạy cảm có thể xuất hiện trong tên file, URL, query string, exception message hoặc field tự do.

## 3. Logging an toàn: ghi sự kiện, không dump object

Tránh ghi trực tiếp entity:

```java
// Không an toàn: toString() có thể bao gồm mọi field.
log.info("Saving product {}", product);
```

Tránh ghi request hoặc query body:

```java
// Không an toàn nếu request/query chứa dữ liệu người dùng.
log.debug("Elasticsearch query: {}", query);
```

Thay vào đó, ghi event có cấu trúc và chỉ đưa vào các trường cần thiết:

```java
log.info(
        "Elasticsearch write completed operation={} index={} documentRef={} outcome={}",
        "index",
        "products",
        safeDocumentReference(product.getId()),
        "success"
);
```

Ở đây `safeDocumentReference` phải là hàm pseudonymization hoặc masking được định nghĩa theo chính sách của ứng dụng. Nếu không cần liên kết document giữa các log, tốt hơn là không ghi ID.

### 3.1. Dùng placeholder, tránh nối chuỗi thủ công

SLF4J parameterized logging giúp tránh tạo chuỗi không cần thiết khi log level không bật:

```java
log.info("Bulk indexing finished index={} itemCount={} durationMs={}",
        indexAlias,
        itemCount,
        duration.toMillis());
```

Không nên nối toàn bộ object hoặc payload:

```java
// Tránh.
log.info("Import request=" + request);
```

Placeholder không tự che dữ liệu. Nếu tham số truyền vào là token hoặc entity chứa PII, giá trị vẫn được ghi. Hãy chọn tham số an toàn trước khi gọi logger.

### 3.2. Ghi metadata vận hành hữu ích

Ví dụ event cho một bulk operation:

```java
log.info(
        "Elasticsearch bulk completed index={} batchId={} itemCount={} successCount={} failureCount={} durationMs={}",
        indexAlias,
        batchId,
        itemCount,
        successCount,
        failureCount,
        duration.toMillis()
);
```

Những trường này hỗ trợ vận hành mà không cần ghi source document. Nếu `batchId` có thể chứa thông tin người dùng hoặc ID nhạy cảm, hãy tạo một ID kỹ thuật ngẫu nhiên thay vì dùng trực tiếp business key.

## 4. Thiết kế hàm mask và pseudonymize

Masking và pseudonymization phục vụ mục đích khác nhau.

### 4.1. Masking email

Ví dụ hàm mask đơn giản:

```java
public final class DataMasker {

    private DataMasker() {
    }

    public static String maskEmail(String email) {
        if (email == null || email.isBlank()) {
            return "[redacted]";
        }

        int at = email.indexOf('@');
        if (at <= 0 || at == email.length() - 1) {
            return "[redacted]";
        }

        String local = email.substring(0, at);
        String domain = email.substring(at + 1);
        String visible = local.substring(0, 1);

        return visible + "***@" + domain;
    }
}
```

Ví dụ `alice@example.com` thành `a***@example.com`. Cách này vẫn tiết lộ domain và ký tự đầu, vì vậy chỉ dùng nếu chính sách cho phép. Nếu domain cũng nhạy cảm, redaction toàn bộ hoặc pseudonymization sẽ an toàn hơn.

Hàm minh họa cần được điều chỉnh cho Unicode, địa chỉ không chuẩn và quy tắc nghiệp vụ. Không dùng masking để xác thực email hoặc thay thế validation.

### 4.2. Mask số điện thoại

```java
public static String maskPhone(String phone) {
    if (phone == null || phone.isBlank()) {
        return "[redacted]";
    }

    String digits = phone.replaceAll("\\D", "");
    if (digits.length() < 4) {
        return "[redacted]";
    }

    return "***" + digits.substring(digits.length() - 4);
}
```

Ví dụ số điện thoại được biểu diễn thành `***4567`. Không ghi giá trị gốc ở một log khác trong cùng workflow.

### 4.3. Pseudonymization bằng HMAC

Nếu cần nhận biết nhiều log thuộc cùng một customer mà không ghi customer ID gốc, có thể dùng HMAC-SHA-256 với secret key được quản lý bên ngoài source code:

```java
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public final class ReferenceHasher {

    private final byte[] secretKey;

    public ReferenceHasher(byte[] secretKey) {
        this.secretKey = secretKey.clone();
    }

    public String hashReference(String value) {
        if (value == null || value.isBlank()) {
            return "[missing]";
        }

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secretKey, "HmacSHA256"));
            byte[] digest = mac.doFinal(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (Exception ex) {
            throw new IllegalStateException("Could not create reference hash", ex);
        }
    }
}
```

HMAC phù hợp hơn hash thuần khi giá trị đầu vào có thể đoán được như email hoặc số điện thoại. Hash không khóa có thể bị dò từ điển. Secret key phải nằm trong secret manager hoặc cơ chế quản lý khóa tương đương, có phân quyền và quy trình rotation.

HMAC vẫn là pseudonymous identifier, không phải dữ liệu vô danh tuyệt đối. Người có quyền truy cập nhiều hệ thống hoặc key có thể liên kết sự kiện. Không dùng cùng một key cho mọi môi trường nếu không cần liên kết dữ liệu giữa dev, staging và production.

## 5. Không để `toString()` làm lộ dữ liệu

Một nguồn rò rỉ phổ biến là log object tự động. Entity có thể dùng Lombok `@Data`, `@ToString` hoặc record, khiến mọi field được đưa vào `toString()`.

Ví dụ nguy hiểm:

```java
@Data
@Document(indexName = "customers")
public class CustomerDocument {
    @Id
    private String id;
    private String email;
    private String phone;
    private String address;
    private String accessToken;
}
```

`@Data` sinh `toString()` chứa field. Nếu entity được log bởi logger, debugger, exception hoặc framework, các giá trị có thể bị lộ.

Có thể loại field nhạy cảm khỏi `toString()`:

```java
@Getter
@Setter
@ToString(onlyExplicitlyIncluded = true)
@Document(indexName = "customers")
public class CustomerDocument {

    @Id
    @ToString.Include
    private String id;

    @ToString.Include
    private String status;

    private String email;
    private String phone;
    private String address;
    private String accessToken;
}
```

Một lựa chọn khác là `@ToString.Exclude` trên field nhạy cảm. Chỉ include allowlist các field cần thiết thường dễ kiểm soát hơn exclude blacklist vì field mới thêm sau này sẽ không tự xuất hiện trong `toString()`.

Tuy vậy, không nên xem `toString()` đã được mask là giấy phép log entity ở mọi nơi. Một entity có thể được serialize hoặc dump qua cơ chế khác. Tạo DTO/log event riêng là cách rõ ràng hơn.

## 6. Logging an toàn quanh `ElasticsearchOperations`

Không log toàn bộ entity hoặc query. Có thể log operation metadata ở service boundary:

```java
public Mono<Product> saveProduct(Product product) {
    long startedAt = System.nanoTime();

    return reactiveOperations.save(product)
            .doOnSuccess(saved -> log.info(
                    "Product indexed index={} operation={} outcome={} durationMs={}",
                    "products",
                    "save",
                    "success",
                    elapsedMillis(startedAt)
            ))
            .doOnError(error -> log.warn(
                    "Product index failed index={} operation={} errorType={} durationMs={}",
                    "products",
                    "save",
                    error.getClass().getSimpleName(),
                    elapsedMillis(startedAt)
            ));
}
```

`doOnSuccess` với `Mono` có thể được gọi với `null` khi publisher hoàn tất rỗng; nếu code cần phân biệt empty và value, dùng operator phù hợp hoặc kiểm tra giá trị. Ví dụ trên tập trung vào metadata và không ghi exception message.

Với API imperative:

```java
public Product saveProduct(Product product) {
    long startedAt = System.nanoTime();
    try {
        Product saved = operations.save(product);
        log.info("Product indexed index={} operation={} outcome={} durationMs={}",
                "products", "save", "success", elapsedMillis(startedAt));
        return saved;
    } catch (RuntimeException ex) {
        log.warn("Product index failed index={} operation={} errorType={} durationMs={}",
                "products", "save", ex.getClass().getSimpleName(), elapsedMillis(startedAt));
        throw ex;
    }
}
```

Đây là ví dụ logging boundary; service thực tế có thể cần chuyển exception sang domain exception ở tầng cao hơn. Không log rồi nuốt exception nếu caller cần biết thao tác thất bại.

### 6.1. Tránh log query DSL nguyên bản

Một query có thể chứa dữ liệu người dùng:

```json
{
  "query": {
    "term": {
      "email.keyword": "customer@example.com"
    }
  }
}
```

Thay vì log JSON query, ghi metadata:

```java
log.debug("Elasticsearch search started index={} queryType={} fieldGroup={}",
        "customers", "term", "customer_lookup");
```

Không ghi literal value, query string hoặc full `NativeQuery` nếu query chứa input nhạy cảm. Nếu cần tái hiện lỗi, dùng synthetic test data hoặc một bản query đã redact.

### 6.2. Không log toàn bộ BulkResponse item source

Bulk response thường chứa status, ID, error type và reason. Có thể ghi số lượng và nhóm lỗi thay vì dump toàn response:

```java
log.warn("Bulk indexing partially failed index={} total={} succeeded={} failed={} errorType={}",
        indexAlias, total, succeeded, failed, errorType);
```

Nếu cần theo dõi item lỗi, dùng ID pseudonymous, status và mã lỗi. Lưu payload gốc trong một kho lỗi riêng chỉ khi có mục đích, mã hóa, phân quyền và retention rõ ràng.

## 7. Exception message từ Elasticsearch có thể chứa dữ liệu

Exception có thể được tạo từ nhiều tầng:

- Spring Data Elasticsearch.
- Elasticsearch Java API Client.
- HTTP transport.
- Elasticsearch server response.
- Mapping/conversion layer.
- Validation và domain service.

Thông tin lỗi có thể chứa tên index, document ID, field, query fragment, URL, request parameter hoặc một phần dữ liệu đầu vào. Vì vậy, không mặc định `exception.getMessage()` an toàn để log hoặc trả về client.

Tránh:

```java
catch (Exception ex) {
    log.error("Elasticsearch operation failed: {}", ex.getMessage());
    throw new RuntimeException(ex.getMessage());
}
```

Và tránh:

```java
catch (Exception ex) {
    return Mono.error(new ResponseStatusException(
            HttpStatus.INTERNAL_SERVER_ERROR,
            ex.getMessage(),
            ex
    ));
}
```

Ví dụ thứ hai có thể đưa thông tin nội bộ vào HTTP response hoặc error handling chain.

### 7.1. Ghi mã lỗi an toàn

Tạo error code nội bộ không chứa payload:

```java
public enum SearchErrorCode {
    INDEX_UNAVAILABLE,
    DOCUMENT_INVALID,
    SEARCH_TIMEOUT,
    SEARCH_FAILED
}
```

Map exception sang nhóm lỗi:

```java
private SearchErrorCode classify(Throwable error) {
    if (error instanceof org.springframework.dao.DataAccessResourceFailureException) {
        return SearchErrorCode.INDEX_UNAVAILABLE;
    }
    if (error instanceof org.springframework.dao.DataIntegrityViolationException) {
        return SearchErrorCode.DOCUMENT_INVALID;
    }
    return SearchErrorCode.SEARCH_FAILED;
}
```

Các exception thực tế có thể được wrap theo nhiều lớp và khác nhau giữa phiên bản client. Đây là ví dụ phân loại cơ bản; nên bổ sung classifier theo loại exception và error status mà dự án đang dùng.

Log code và loại exception:

```java
log.error("Elasticsearch operation failed errorCode={} exceptionType={} traceId={}",
        errorCode,
        error.getClass().getSimpleName(),
        traceId);
```

Nếu cần stack trace để điều tra, chỉ gửi vào log sink có quyền truy cập hạn chế và đã có quy tắc scrub dữ liệu. Không tự động ghi nguyên exception ở mọi môi trường khi message/cause có thể chứa request data.

### 7.2. Phân biệt lỗi có thể retry và lỗi dữ liệu

Không nên chỉ ghi một chuỗi exception message rồi quyết định retry. Hãy phân loại theo status/error type:

| Nhóm | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | Timeout, connection reset, 429, 502/503/504 | Retry có backoff, giới hạn và idempotency. |
| Dữ liệu | Mapping parse error, invalid field, document quá lớn | Không retry nguyên trạng; sửa dữ liệu hoặc dead-letter. |
| Xung đột | Version conflict, create conflict | Đọc version/trạng thái và xử lý theo nghiệp vụ. |
| Cấu hình/quyền | Index missing, unauthorized, forbidden | Dừng hoặc cảnh báo; sửa cấu hình/quyền. |
| Không xác định | Exception chưa được phân loại | Log mã lỗi an toàn, correlation ID và điều tra. |

Error classifier nên trả mã ổn định để metric và alert không phụ thuộc nội dung message tự do.

## 8. Trả thông báo lỗi an toàn cho API

Client cần biết thao tác thất bại và cách xử lý tiếp theo, nhưng thường không cần biết stack trace, tên node, index vật lý, query DSL hoặc nội dung exception từ Elasticsearch.

Response lỗi có thể gồm:

- HTTP status phù hợp.
- Error code ổn định.
- Thông điệp tổng quát, không chứa dữ liệu nội bộ.
- Correlation ID hoặc trace ID để bộ phận hỗ trợ tra cứu.
- Field validation đã được làm sạch nếu có thể hiển thị an toàn.

Ví dụ response:

```json
{
  "type": "https://api.example.com/problems/search-failed",
  "title": "Search could not be completed",
  "status": 503,
  "detail": "Please retry later or contact support with the request ID.",
  "code": "SEARCH_UNAVAILABLE",
  "requestId": "req-7f2c1a"
}
```

Không trả:

```json
{
  "error": "ElasticsearchException: failed request to node ...",
  "query": "...email customer@example.com...",
  "stackTrace": "..."
}
```

### 8.1. `@RestControllerAdvice` với Spring MVC/WebFlux

Spring Framework hỗ trợ `ProblemDetail` cho HTTP API error response. Có thể dùng exception handler để trả lỗi đã chuẩn hóa:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(SearchUnavailableException.class)
    public ProblemDetail handleSearchUnavailable(
            SearchUnavailableException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Search is temporarily unavailable. Please retry later."
        );
        problem.setTitle("Search unavailable");
        problem.setProperty("code", "SEARCH_UNAVAILABLE");
        return problem;
    }
}
```

Handler không sử dụng `exception.getMessage()` trong response. Với Spring WebFlux, `@RestControllerAdvice` cũng có thể xử lý exception từ reactive controller; phương thức handler có thể trả `Mono<ProblemDetail>` hoặc kiểu response reactive khi cần thực hiện thêm thao tác bất đồng bộ.

### 8.2. Gắn request ID vào response

Request ID nên được tạo hoặc xác thực ở gateway/application boundary, sau đó truyền qua logging/tracing context. Không lấy một header tùy ý từ client làm ID tin cậy mà không validate độ dài và ký tự.

Ví dụ handler nhận request ID đã được cung cấp qua request context:

```java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.SERVICE_UNAVAILABLE,
        "Search is temporarily unavailable."
);
problem.setProperty("requestId", requestId);
```

Request ID chỉ là mã tương quan, không chứa email, số điện thoại, customer ID hoặc token. Client có thể gửi ID giả để gây nhầm lẫn nếu hệ thống không tạo/kiểm soát ID ở biên tin cậy.

## 9. Trace và span attributes

Distributed tracing giúp nối một request qua gateway, service, Spring Data, Elasticsearch client và các hệ thống phụ thuộc. Nhưng span attribute thường được xuất sang APM backend và có thể tồn tại lâu hơn log ứng dụng.

Những attribute thường hữu ích:

- `db.system` hoặc loại datastore.
- Operation name, ví dụ `index`, `get`, `search`, `delete`.
- Alias/index logical name nếu không tiết lộ cấu trúc nhạy cảm.
- HTTP status hoặc nhóm lỗi.
- Duration, retry count và batch size.
- Trace ID/span ID do tracing system quản lý.

Tránh đưa vào span:

- Authorization/Cookie header.
- Document source hoặc response body.
- Query literal chứa input người dùng.
- Full URL có query parameter nhạy cảm.
- Email, phone, địa chỉ hoặc token.
- Exception message nguyên bản chưa được scrub.

### 9.1. Không đưa PII vào span name

Tên span nên ổn định và mô tả operation:

```text
elasticsearch.search products
elasticsearch.index products
elasticsearch.get products
```

Tránh tên span chứa ID hoặc search term:

```text
search customer@example.com
get customer-C-10001
```

Span name có thể được hiển thị trong dashboard, alert hoặc log correlation. Tên động chứa dữ liệu người dùng vừa làm lộ thông tin vừa tạo cardinality lớn.

### 9.2. Attribute phải có allowlist

Không gắn toàn bộ request object vào span:

```java
// Tránh: object có thể được serialize thành nhiều attribute nhạy cảm.
span.setAttribute("request", request.toString());
```

Thay vào đó, thêm một số attribute có tên và giá trị đã được phê duyệt:

```java
span.setAttribute("app.operation", "product.search");
span.setAttribute("app.index_alias", "products");
span.setAttribute("app.result_count", resultCount);
span.setAttribute("app.outcome", "success");
```

Không thêm customer ID hoặc search term chỉ vì tracing SDK cho phép lưu attribute tùy ý.

## 10. MDC, trace context và Reactor Context

Trong ứng dụng imperative, MDC của SLF4J thường được dùng để gắn `requestId`, `traceId` hoặc `spanId` vào log pattern. Trong reactive pipeline, execution có thể chuyển thread; MDC dựa trên `ThreadLocal` không tự động an toàn qua mọi operator/scheduler boundary.

Ví dụ imperative:

```java
try {
    MDC.put("requestId", requestId);
    service.handle(request);
} finally {
    MDC.remove("requestId");
}
```

Luôn xóa MDC trong `finally` để tránh dữ liệu của request trước bị giữ trên thread được tái sử dụng.

Trong Reactor, context được gắn vào subscriber context:

```java
return repository.findByStatus("ACTIVE")
        .contextWrite(context -> context.put("requestId", requestId));
```

Có thể đọc Reactor Context trong một operator:

```java
return Mono.deferContextual(contextView -> {
    String requestId = contextView.getOrDefault("requestId", "unknown");
    log.info("Reactive operation started requestId={} operation={}",
            requestId, "product.search");
    return repository.findBySku("SKU-100");
});
```

Đoạn code minh họa việc đọc context trong publisher. Nếu cần tự động đưa trace/MDC vào log trên mọi thread, ưu tiên tích hợp Micrometer Context Propagation/Tracing phù hợp với phiên bản Spring Boot và Reactor của dự án. Không tự copy ThreadLocal sang thread khác mà không có cơ chế khôi phục và dọn dẹp.

### 10.1. Baggage không phải kho chứa business data

Distributed tracing baggage có thể được truyền qua nhiều service. Một giá trị được thêm vào baggage có thể rời khỏi process hiện tại và xuất hiện trong downstream span/log.

Chỉ đưa vào baggage các giá trị kỹ thuật cần thiết, không chứa PII hoặc secret. Nếu cần tenant correlation, dùng mã pseudonymous đã được phê duyệt và giới hạn propagation scope.

## 11. Che dữ liệu trong URL và HTTP header

HTTP client log có thể ghi URL, query string và header. Ví dụ:

```text
GET /customers/search?email=customer@example.com
Authorization: Bearer eyJhbGciOi...
Cookie: session=...
```

Không bật wire logging toàn bộ ở production nếu chưa có bộ lọc và chính sách kiểm soát. Một số HTTP client hoặc logging interceptor có thể ghi cả body request/response khi bật DEBUG/TRACE.

Các nguyên tắc:

- Không log `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`.
- Không đưa token vào URL query parameter.
- Tránh log query string có dữ liệu người dùng.
- Nếu cần log endpoint, dùng route template như `/customers/{id}` thay vì URL thực tế.
- Không log request/response body của Elasticsearch mặc định.
- Không bật TRACE cho transport/client trên production trừ khi có incident và đã kiểm soát output.
- Đảm bảo proxy, gateway và APM agent áp dụng cùng chính sách redact.

### 11.1. Route template an toàn hơn URL thực tế

Ghi:

```text
http.route=/customers/{customerId}
http.request.method=GET
http.response.status_code=200
```

Tránh:

```text
url.full=https://api.example.com/customers/C-10001?email=customer@example.com
```

Nếu cần nhận diện route, dùng route template do framework cung cấp, không tự thay thế string URL theo regex trong mọi trường hợp.

## 12. Cấu hình log level cho Elasticsearch client

Spring Data Elasticsearch dùng Elasticsearch Java API Client và HTTP transport. Log category cụ thể phụ thuộc phiên bản Spring Data, client và transport implementation.

Trong `application.yml`, có thể cấu hình mức log cho package ứng dụng:

```yaml
logging:
  level:
    root: INFO
    com.example.catalog: INFO
    org.springframework.data.elasticsearch: INFO
    co.elastic.clients: WARN
```

Đây là cấu hình minh họa; package logging thực tế của transport có thể khác. Không nên bật DEBUG/TRACE rộng trên các package client trong production khi chưa biết chính xác nội dung được ghi.

Khi cần chẩn đoán:

1. Bật log cho đúng package và thời gian ngắn.
2. Dùng dữ liệu test/synthetic nếu có thể.
3. Kiểm tra output trước khi gửi đến log aggregator.
4. Tắt mức log chi tiết sau khi xử lý xong.
5. Xóa hoặc hạn chế truy cập log chứa dữ liệu nhạy cảm nếu đã phát sinh.

Không giả định đổi `logging.level` là đủ để redact. Log level chỉ điều khiển mức độ chi tiết; nó không hiểu field nào là PII.

## 13. Logback và bộ lọc redact

Có thể dùng Logback encoder/layout hoặc appender filter để chuẩn hóa log event. Tuy nhiên, lọc bằng regex trên chuỗi cuối cùng có giới hạn:

- Dữ liệu có thể được encode/escape khác nhau.
- Secret có thể nằm trong nested JSON hoặc stack trace.
- Regex có thể bỏ sót định dạng mới.
- Regex quá rộng có thể làm hỏng dữ liệu kỹ thuật hữu ích.
- Dữ liệu đã đi vào một appender khác trước khi filter chạy.

Ưu tiên không đưa dữ liệu nhạy cảm vào log event ngay từ đầu. Bộ lọc cuối pipeline là lớp phòng thủ bổ sung.

Ví dụ Logback pattern chỉ ghi các trường kỹ thuật:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] trace=%X{traceId} request=%X{requestId} %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Pattern này không tự tạo trace ID/request ID; các giá trị phải được gắn đúng context. Nếu log theo JSON, dùng encoder có hỗ trợ structured fields và cấu hình allowlist/redaction theo schema log của dự án.

Không ghi toàn bộ MDC nếu MDC có thể chứa dữ liệu do client cung cấp. Chỉ đưa vào pattern những key được kiểm soát.

## 14. Structured logging và schema log

Structured logging giúp hệ thống log phân tích field mà không phải parse chuỗi tự do. Nên định nghĩa schema event thống nhất:

```json
{
  "timestamp": "2026-11-13T12:00:00Z",
  "level": "INFO",
  "service": "catalog-api",
  "event": "elasticsearch.operation.completed",
  "operation": "search",
  "index_alias": "products",
  "outcome": "success",
  "duration_ms": 24,
  "result_count": 12,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "request_id": "req-7f2c1a"
}
```

Không có document source, query literal, token hoặc customer email. Với schema log, cần kiểm soát cả field name và field value; một field tên `request_id` vẫn không an toàn nếu ứng dụng đặt email vào đó.

Một số event hữu ích:

- `elasticsearch.operation.started`
- `elasticsearch.operation.completed`
- `elasticsearch.operation.failed`
- `elasticsearch.bulk.partial_failure`
- `elasticsearch.reindex.completed`
- `elasticsearch.alias.cutover.completed`
- `elasticsearch.connection.unavailable`

Các event name ổn định giúp tạo dashboard và alert mà không cần lưu payload.

## 15. Metrics không phải nơi để ghi dữ liệu định danh

Metric label/tag thường được lưu trong time-series database. Nếu dùng email, document ID, query string hoặc request ID làm label, hệ thống vừa rò rỉ dữ liệu vừa tạo cardinality rất cao.

Không làm:

```java
counterBuilder.tag("customer_email", customer.getEmail());
```

Nên dùng label có tập giá trị nhỏ:

```java
counterBuilder
        .tag("operation", "search")
        .tag("outcome", "success")
        .tag("index_group", "catalog")
        .register(registry)
        .increment();
```

Các label tốt thường là enum/nhóm cố định như operation, outcome, error code, region hoặc service. Không dùng ID ngẫu nhiên, user ID, email, trace ID hay search term làm tag.

Trace ID phù hợp cho correlation trong log/tracing, nhưng không phù hợp làm metric label vì mỗi request thường có giá trị khác nhau.

## 16. Audit log khác application log

Audit log ghi lại hành động có ý nghĩa bảo mật hoặc nghiệp vụ, ví dụ:

- Ai đã thay đổi quyền truy cập.
- Ai đã xóa một record.
- Khi nào một export được yêu cầu.
- Một alias cutover do job nào thực hiện.
- Một thao tác quản trị index đã xảy ra.

Audit event cần đủ thông tin để truy vết nhưng vẫn phải áp dụng minimization và pseudonymization. Không nên dùng application log debug làm audit log vì mức độ đầy đủ, retention và kiểm soát truy cập thường khác nhau.

Ví dụ audit event:

```json
{
  "event": "customer.record.deleted",
  "actor_ref": "hmac:4c91...",
  "record_ref": "hmac:8a10...",
  "reason_code": "RETENTION_POLICY",
  "outcome": "success",
  "request_id": "req-7f2c1a",
  "timestamp": "2026-11-13T12:00:00Z"
}
```

Audit log cần có integrity/access control phù hợp, retention policy rõ ràng và khả năng phát hiện sửa/xóa trái phép. Nếu cần lưu dữ liệu định danh để đáp ứng một quy trình được phê duyệt, hãy lưu trong hệ thống audit có kiểm soát riêng thay vì đưa vào mọi log ứng dụng.

## 17. Dead-letter và lỗi import

Khi bulk import thất bại, đội vận hành có thể cần lưu item lỗi để sửa và gửi lại. Tuy nhiên, dead-letter record có thể chứa toàn bộ source document, bao gồm PII và secret.

Một record lỗi tối thiểu nên gồm:

- Import job ID.
- Source record reference đã pseudonymize.
- Index alias/version.
- Operation type.
- Error code/type đã phân loại.
- Timestamp và retry count.
- Reference đến payload được bảo vệ nếu thực sự cần giữ payload.

Nếu phải lưu payload gốc:

- Lưu trong kho riêng có mã hóa at-rest/in-transit.
- Hạn chế quyền đọc theo vai trò.
- Audit mọi lần truy cập.
- Đặt retention ngắn và xóa tự động.
- Không copy payload sang application log hoặc trace.
- Che secret trước khi lưu nếu payload không cần giữ secret.

Không đưa payload nhạy cảm vào exception message để thuận tiện retry. Retry store cần có schema và quyền truy cập riêng.

## 18. Kiểm soát stack trace và thông báo lỗi

Stack trace hữu ích cho developer nhưng có thể chứa:

- Exception message từ server/client.
- URL và query parameter.
- Tên index vật lý, shard hoặc node.
- Một phần request/response.
- Giá trị field trong lỗi mapping.
- Đường dẫn file hoặc thông tin cấu hình nội bộ.

Không trả stack trace cho người dùng API. Trong production, không hiển thị exception class, message hoặc nested cause một cách tự động.

Một cách xử lý là tách log nội bộ và response công khai:

```java
try {
    return operations.search(query, Product.class);
} catch (RuntimeException ex) {
    String errorCode = "SEARCH_FAILED";
    log.error("Search failed errorCode={} exceptionType={} requestId={}",
            errorCode,
            ex.getClass().getSimpleName(),
            requestId);

    throw new SearchUnavailableException(errorCode);
}
```

Đoạn code không truyền nguyên message/cause sang response. Nếu cần stack trace để điều tra, có thể dùng một diagnostic channel được kiểm soát với scrubber, thay vì ghi tự động vào log phổ thông.

Không bắt `Throwable` để che mọi lỗi. Bắt các exception phù hợp, để lỗi nghiêm trọng của JVM được xử lý theo cơ chế runtime.

## 19. Correlation ID và trace ID an toàn

Correlation ID giúp liên kết log, trace và API response mà không cần ghi dữ liệu cá nhân.

Một quy trình:

1. Gateway hoặc application boundary tạo request ID ngẫu nhiên.
2. Request ID được lưu trong tracing/logging context.
3. Service ghi request ID trong event log.
4. Trace ID được tạo bởi tracing system.
5. API error response trả request ID/trace ID đã được cho phép.
6. Bộ phận hỗ trợ dùng ID để tra cứu log có phân quyền.

Không dùng email hoặc customer ID làm correlation ID. Không chấp nhận header có độ dài vô hạn hoặc ký tự điều khiển; validate/normalize giá trị do client gửi.

### 19.1. Tránh log injection

Input người dùng có thể chứa newline hoặc ký tự điều khiển để giả mạo log entry:

```text
searchTerm = "keyboard\nINFO login succeeded"
```

Nếu ghi chuỗi này trực tiếp vào log text, một input có thể tạo nhiều dòng log giả. Structured logging/JSON encoder giúp escape nhiều ký tự, nhưng vẫn cần validate và sanitize field tự do.

Không tự nối input vào log line. Nếu phải ghi một giá trị do người dùng kiểm soát, chuẩn hóa ký tự điều khiển hoặc dùng encoder có escaping đúng.

## 20. Quyền truy cập, retention và bảo vệ log/trace

Che dữ liệu ở ứng dụng không thay thế bảo vệ hệ thống lưu log.

Các kiểm soát vận hành:

- Phân quyền theo vai trò; developer không mặc định có quyền đọc mọi production log.
- Mã hóa dữ liệu khi truyền và khi lưu.
- Giới hạn retention theo mục đích và chính sách nội bộ.
- Bật audit truy cập log/trace và payload lưu trữ.
- Tách môi trường dev/test/staging/production.
- Không dùng production PII trong test nếu không có quy trình anonymization.
- Kiểm soát export/download và quyền chia sẻ dashboard.
- Xóa hoặc rotate dữ liệu theo retention policy.
- Có quy trình incident response nếu secret/PII đã bị log.

Log có thể được sao chép sang nhiều hệ thống: stdout, container runtime, collector, message queue, object storage, SIEM và APM backend. Cần xác định toàn bộ bản sao và retention của từng nơi.

## 21. Kiểm thử chính sách redaction

Không chỉ kiểm tra rằng logger được gọi. Hãy kiểm tra output thực tế của appender/encoder hoặc test redaction utility.

Một số test cho masker:

```java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class DataMaskerTest {

    @Test
    void masksEmailLocalPart() {
        assertThat(DataMasker.maskEmail("alice@example.com"))
                .isEqualTo("a***@example.com");
    }

    @Test
    void masksPhoneExceptLastFourDigits() {
        assertThat(DataMasker.maskPhone("+84 901 234 567"))
                .isEqualTo("***4567");
    }

    @Test
    void redactsMalformedEmail() {
        assertThat(DataMasker.maskEmail("not-an-email"))
                .isEqualTo("[redacted]");
    }
}
```

Test log output:

1. Tạo test appender hoặc capture output của logging backend.
2. Gửi request chứa email, phone, token và query text giả lập.
3. Kích hoạt success path và error path.
4. Kiểm tra output không chứa giá trị secret/PII gốc.
5. Kiểm tra request ID và error code vẫn còn để correlation.
6. Kiểm tra stack trace, cause và nested exception không làm rò rỉ dữ liệu.
7. Kiểm tra metric label và span attribute không chứa ID hoặc query literal.

Nên có canary string riêng trong test, ví dụ `SECRET_CANARY_9f31`, rồi tìm chuỗi này trong toàn bộ log/trace test output. Nếu xuất hiện, redaction policy đã bị vi phạm.

## 22. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Log chứa toàn bộ customer document | Log entity trực tiếp hoặc `toString()` include field. | Log event allowlist; loại field nhạy cảm khỏi `toString()` và không dump entity. |
| Token xuất hiện trong HTTP log | Wire logging ghi header/body. | Tắt body/header logging hoặc redact Authorization/Cookie ở transport/proxy. |
| Exception message chứa dữ liệu người dùng | Ghi `getMessage()` hoặc stack trace nguyên bản. | Log error code/type và dùng diagnostic sink có scrubber khi cần. |
| API trả stack trace | Handler trả exception message/cause cho client. | Dùng `ProblemDetail` với message tổng quát và request ID. |
| Trace có email/search term | Gắn raw request vào span attribute hoặc URL. | Allowlist attribute và dùng route template. |
| MDC bị lẫn request trong reactive app | Dùng ThreadLocal mà không có context propagation/cleanup. | Dùng Reactor Context và Micrometer context propagation. |
| Log có nhiều dòng giả | Input chứa newline/control character. | Structured logging và sanitize field do người dùng kiểm soát. |
| Metric storage tăng cardinality | Dùng user/document/request ID làm tag. | Dùng label có tập giá trị hữu hạn như operation/outcome/error code. |
| Mask email nhưng vẫn lộ thông tin | Chỉ che local part, giữ domain/độ dài. | Đánh giá threat model; redaction hoặc HMAC nếu cần kín hơn. |
| Hash ID vẫn bị dò | Dùng hash thuần với giá trị có thể đoán. | Dùng HMAC với secret key được quản lý an toàn. |
| Dead-letter chứa PII lâu dài | Lưu toàn bộ payload và không có retention. | Tối thiểu hóa payload, mã hóa, phân quyền và tự động xóa. |
| Log redaction regex bỏ sót dữ liệu | Chỉ lọc chuỗi cuối cùng, định dạng thay đổi. | Ngăn dữ liệu vào log từ đầu; dùng schema allowlist và test canary. |

## 23. Quy trình thiết kế log/trace/error an toàn

1. **Phân loại dữ liệu:** đánh dấu secret, PII, business identifier, free text và metadata kỹ thuật.
2. **Xác định mục đích:** log/trace cần trả lời câu hỏi vận hành nào?
3. **Chọn allowlist:** chỉ ghi operation, alias, outcome, duration, count, error code và correlation ID cần thiết.
4. **Chọn cách xử lý:** bỏ hoàn toàn, mask hoặc HMAC theo mục đích.
5. **Thiết kế exception mapping:** không truyền message nguyên bản sang API response.
6. **Kiểm soát client logging:** tắt hoặc redact HTTP wire/query/body/header log.
7. **Quản lý context:** dùng request ID/trace ID kỹ thuật; không đưa PII vào MDC/baggage.
8. **Kiểm soát metrics:** không dùng identifier hoặc free text làm tag.
9. **Bảo vệ storage:** phân quyền, mã hóa, retention, audit và deletion.
10. **Kiểm thử:** capture log/trace/error response và quét canary secret.
11. **Theo dõi thay đổi:** khi thêm field entity, query hoặc tracing instrumentation, đánh giá lại khả năng rò rỉ.

## 24. Những điểm cần nhớ

- Log, trace, exception, metric label và API response đều có thể làm lộ dữ liệu nhạy cảm.
- Ưu tiên data minimization và allowlist; đừng ghi entity, request body hoặc query DSL nguyên bản.
- Secret như password, token, key và cookie phải được loại bỏ hoàn toàn.
- Masking vẫn có thể tiết lộ thông tin; pseudonymization bằng HMAC giúp liên kết sự kiện nhưng vẫn cần bảo vệ key.
- `toString()` của entity/Lombok có thể làm lộ mọi field; dùng log DTO/event riêng và allowlist field.
- `exception.getMessage()` và stack trace có thể chứa query, URL, index hoặc dữ liệu đầu vào.
- Trả error code, thông điệp tổng quát và request ID; không trả stack trace cho client.
- Trace span chỉ nên có attribute kỹ thuật đã phê duyệt; không ghi PII vào span name hoặc baggage.
- MDC dựa trên ThreadLocal cần được quản lý cẩn thận trong reactive pipeline; dùng Reactor Context/context propagation.
- Không bật HTTP wire logging toàn bộ trong production nếu chưa có redaction đáng tin cậy.
- Không dùng email, document ID, query hoặc trace ID làm metric label.
- Dead-letter payload cần mã hóa, phân quyền, audit và retention.
- Bảo vệ log storage bằng quyền truy cập, encryption, retention và quy trình incident response.
- Test output thực tế bằng canary string để phát hiện rò rỉ.

Che dữ liệu trong log, trace và thông báo lỗi là một phần của thiết kế luồng dữ liệu, không chỉ là cấu hình logger. Hãy quyết định dữ liệu nào được phép xuất hiện, tạo log event từ allowlist, giữ exception nội bộ khỏi response công khai, truyền correlation ID kỹ thuật qua Reactor Context và kiểm thử output thực tế. Nhờ đó, đội vận hành vẫn có đủ tín hiệu để xử lý sự cố mà không biến log và trace thành bản sao không kiểm soát của dữ liệu nghiệp vụ.

## Tài liệu tham khảo

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Framework — Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [OpenTelemetry — Sensitive Data](https://opentelemetry.io/docs/security/handling-sensitive-data/)
