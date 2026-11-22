# Tránh đưa dữ liệu nhạy cảm vào log, trace hoặc baggage

Trong một hệ thống microservices, mỗi yêu cầu có thể tạo ra hàng chục dòng log, nhiều span tracing và một số metadata được truyền qua nhiều dịch vụ. Những dữ liệu quan sát này rất hữu ích để tìm lỗi, phân tích độ trễ và điều tra sự cố. Tuy nhiên, nếu ứng dụng ghi nguyên request body, token xác thực, tham số URL, exception message hoặc thông tin khách hàng vào telemetry, dữ liệu nhạy cảm có thể lan ra **nhiều nơi hơn dữ liệu nghiệp vụ ban đầu**: agent thu thập, message queue, collector, nhà cung cấp observability, dashboard, bản export và cả thông báo cảnh báo.

Mục tiêu là **quan sát được hành vi và nguyên nhân lỗi mà không cần ghi nội dung nhạy cảm**. Thiết kế an toàn bắt đầu từ quy ước dữ liệu được phép thu thập, thực thi ở nơi sinh dữ liệu và dùng nhiều lớp kiểm soát để hạn chế thiệt hại nếu có sai sót.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện dữ liệu nhạy cảm trong log, trace attributes, span events, exception, metrics và W3C Baggage.
2. Phân biệt thông tin chẩn đoán cần thiết với dữ liệu nghiệp vụ không nên xuất hiện trong hệ thống observability.
3. Thiết kế logging theo **allowlist** và dữ liệu cấu trúc, tránh dump request/response hay object bất kỳ.
4. Hiểu vì sao **redaction tại nguồn** quan trọng hơn chỉ che dữ liệu ở dashboard hoặc collector.
5. Áp dụng nguyên tắc tối thiểu hóa khi đặt tên span, HTTP route, metric labels và propagated baggage.
6. Thiết lập các lớp bảo vệ ở ứng dụng, SDK/instrumentation, OpenTelemetry Collector và backend.
7. Viết kiểm thử chứng minh secret giả lập không xuất hiện trong telemetry ở đường thành công và đường lỗi.
8. Xử lý khi phát hiện dữ liệu nhạy cảm đã lọt vào log hoặc trace.

## 2. Tại sao telemetry là một bề mặt rò rỉ dữ liệu?

Dữ liệu nghiệp vụ thông thường nằm trong database được bảo vệ bằng phân quyền, mã hóa và thời gian lưu được kiểm soát. Telemetry thường có đặc điểm khác:

- Nhiều developer, SRE, support hoặc hệ thống cảnh báo cần truy cập để xử lý sự cố.
- Collector và exporter có thể chuyển telemetry sang hệ thống của bên thứ ba.
- Log được copy qua nhiều pipeline, index, archive, alert hoặc hệ thống tìm kiếm.
- Một số log hoặc trace được lưu dài hơn dữ liệu request tạm thời.
- Trace context và baggage có thể tiếp tục lan truyền sang service khác mà người viết code ban đầu không biết.
- Dữ liệu bị đặt trong **metric label** có thể tạo cardinality cao, khiến chi phí và tải hệ thống tăng mạnh.
- Giao diện che một trường không đồng nghĩa dữ liệu đã bị xóa khỏi đường truyền, storage hoặc bản backup.

Ví dụ request thanh toán:

~~~http
POST /payments
Authorization: Bearer <token-thu-nghiem>
Content-Type: application/json

{
  "customerEmail": "demo@example.invalid",
  "cardNumber": "<du-lieu-thanh-toan-gia-lap>",
  "amount": 120000
}
~~~

Nếu middleware ghi `headers={} body={}` hoặc `request.toString()`, token và dữ liệu khách hàng có thể xuất hiện trong log. Nếu Java agent hoặc instrumentation gắn toàn bộ request URL có query chứa token vào span attribute, lỗi vẫn xảy ra dù ứng dụng tự viết log rất cẩn thận. Nếu mã hóa customer email vào baggage để “dễ tìm trace”, giá trị này có thể được gửi tiếp đến mọi downstream được cấu hình propagation.

**Quy tắc nền:** log và tracing dùng để mô tả hoạt động kỹ thuật, không phải kho lưu dữ liệu yêu cầu hoặc bản sao của dữ liệu khách hàng.

## 3. Phân loại dữ liệu trước khi chọn trường telemetry

Không phải mọi ID đều vô hại, và không phải mọi trường mang tên “metadata” đều an toàn. Đánh giá giá trị theo khả năng nhận dạng, xác thực, suy ra hành vi, kết hợp với dữ liệu khác và độ rộng nơi dữ liệu có thể được gửi.

| Nhóm | Ví dụ | Nguyên tắc xử lý |
|---|---|---|
| **Bí mật/xác thực** | Password, API key, access/refresh token, cookie phiên, private key, connection string có mật khẩu, OTP, mã khôi phục | **Không ghi** vào log, trace, baggage, metric; chặn ngay tại nguồn. |
| **Dữ liệu thanh toán/tài chính nhạy cảm** | Số thẻ đầy đủ, mã bảo mật, thông tin tài khoản, dữ liệu giao dịch định danh | Không ghi giá trị thô; nếu cần chẩn đoán, chỉ dùng trạng thái đã chuẩn hóa và mã tham chiếu được duyệt. |
| **Thông tin cá nhân** | Tên, email, điện thoại, địa chỉ, định vị chi tiết, ngày sinh, IP nếu chính sách coi là cá nhân | Mặc định không ghi thô; dùng thông tin tổng hợp hoặc định danh thay thế có kiểm soát. |
| **Nội dung nghiệp vụ** | Nội dung chat, tài liệu, giỏ hàng, hồ sơ sức khỏe, payload webhook, bản ghi database | Không dump payload; chỉ thu dữ liệu tối thiểu đã phê duyệt. |
| **Định danh có thể liên kết** | Customer ID, tenant ID, order ID, device ID, message ID, correlation ID | Cần đánh giá vì vẫn có thể theo dõi một cá nhân/tổ chức; giới hạn phạm vi, quyền truy cập và retention. |
| **Thông tin vận hành** | Tên route chuẩn hóa, service name, operation name, trạng thái HTTP, error code dạng enum, duration, retry count | Thường hữu ích, nhưng vẫn cần kiểm soát tên/giá trị để không chứa dữ liệu người dùng. |

Một định danh được biến đổi bằng hash **chưa chắc đã ẩn danh**. Email và số điện thoại có không gian giá trị tương đối dễ đoán; hash không khóa có thể bị dò ngược bằng từ điển. HMAC có khóa hoặc token hóa có thể giảm khả năng liên kết ngoài ý muốn, nhưng đầu ra vẫn cần được quản lý như dữ liệu có khả năng liên kết; không đưa khóa HMAC vào log hoặc cấu hình công khai.

### Chọn dữ liệu theo câu hỏi vận hành

Thay vì hỏi “có thể ghi trường nào?”, hãy hỏi:

- Muốn biết API nào lỗi? Ghi **HTTP route template**, status code và mã lỗi đã chuẩn hóa.
- Muốn biết dependency nào chậm? Ghi service/operation, duration, timeout, retry count và nhóm lỗi.
- Muốn biết request có kết quả chưa? Ghi trạng thái nghiệp vụ dạng enum, ví dụ `PAYMENT_PENDING` hoặc `PAYMENT_REJECTED`.
- Muốn nối log với trace? Dùng trace ID/span ID được instrumentation quản lý, kết hợp correlation ID nội bộ nếu được phê duyệt.
- Muốn hỗ trợ điều tra một đơn hàng? Thiết kế quyền truy cập và tra cứu từ hệ thống nghiệp vụ; đừng mặc định đẩy mọi thuộc tính đơn hàng vào tracing backend.

## 4. Log, trace, metric và baggage có rủi ro khác nhau

### 4.1. Log

Log là bản ghi sự kiện, thường chứa message, timestamp, severity, service và một số trường bổ sung. Rủi ro cao nhất xuất hiện khi logging tùy ý bằng chuỗi:

~~~java
log.info("Incoming request: {}", request);
log.error("Payment failed: {}", paymentPayload);
log.error("Unexpected failure", exception);
~~~

Ở dòng đầu, `toString()` của object có thể lộ trường mới sau khi DTO thay đổi. Dòng thứ hai lộ payload. Dòng thứ ba có thể lộ thông tin trong exception message, nested causes, SQL, URL hoặc các giá trị được gắn vào stack trace. Không phải mọi exception đều chứa secret, nhưng cách ghi không kiểm soát khiến phạm vi rủi ro khó dự đoán.

### 4.2. Trace

Trace chứa span names, attributes, events, links và exception information. Các chỗ cần kiểm soát:

- `http.route` nên là mẫu route có tên như `/orders/{orderId}`, không phải URL thực chứa ID và query string.
- `url.full` hoặc các trường URL tương đương cần được xem xét vì có thể chứa token trong query.
- `db.statement`, `db.query.text` hoặc SQL ghi kèm tham số có thể lộ dữ liệu người dùng.
- `messaging.message.body` hoặc event attributes do lập trình viên thêm dễ biến trace thành bản sao message.
- `exception.message` và stack trace có thể chứa raw payload hoặc secret, nhất là exception từ HTTP client, driver hoặc validation.

Tên và semantic conventions của OpenTelemetry có thể khác giữa phiên bản và loại instrumentation. Phải kiểm tra **tập attributes thực tế** mà hệ thống của bạn đang xuất, không giả định mọi thư viện đều thu đúng một danh sách cố định.

### 4.3. Metric

Metric là số đo tổng hợp, nhưng nhãn (labels/tags) vẫn có thể lộ thông tin. Không đặt email, user ID, full URL, access token hoặc message ID làm label. Ngoài bảo mật, giá trị duy nhất theo request tạo cardinality rất cao, gây tăng bộ nhớ, chi phí lưu trữ và chậm truy vấn.

Mẫu phù hợp:

~~~text
http.server.request.duration{
  service="order-service",
  route="/orders/{orderId}",
  status="500"
}
~~~

Mẫu rủi ro:

~~~text
http.server.request.duration{
  user_email="demo@example.invalid",
  raw_path="/orders/customer-12345",
  query="access_token=..."
}
~~~

### 4.4. Baggage

**W3C Baggage** là thông tin dạng key–value có thể được truyền qua nhiều hop cùng trace context. Đây là **phương tiện propagation**, không phải kho dữ liệu tùy ý và không phải cơ chế xác thực.

~~~http
baggage: deployment.region=ap-southeast,flow.stage=checkout
~~~

Ngay cả những key có vẻ vô hại vẫn cần kiểm tra. Ví dụ `tenant.name`, `customer.tier` hoặc `experiment.group` có thể tiết lộ thông tin tổ chức/khách hàng hoặc bí mật kinh doanh. Baggage có thể được inject vào outbound request đến domain ngoài nếu thư viện tự động truyền nó.

**Không bao giờ đặt vào baggage:** password, token, cookie, PII thô, order/cart contents, thông tin thanh toán, bí mật kinh doanh hoặc authorization claims chưa được kiểm soát. Không lấy baggage làm bằng chứng rằng caller đã xác thực.

## 5. Thiết kế “không thu thập” ngay tại điểm sinh dữ liệu

Ba mức xử lý phổ biến:

1. **Không ghi (omit):** tốt nhất với dữ liệu không cần thiết để quan sát; ví dụ không ghi header Authorization.
2. **Chuẩn hóa/tổng hợp:** thay giá trị chi tiết bằng category hoặc enum; ví dụ `PAYMENT_DECLINED`, `NETWORK_TIMEOUT`, `VALIDATION_FAILED`.
3. **Biến đổi được kiểm soát:** masking, tokenization hoặc pseudonymization cho nhu cầu thật sự cần liên kết; có chính sách về khóa, retention, quyền truy cập và tính ổn định của định danh.

Thứ tự ưu tiên:

~~~text
Dữ liệu request/response gốc
        |
        v
Quy tắc thu thập tại ứng dụng / instrumentation
        |
        +-- Trường không cần: bỏ hoàn toàn
        |
        +-- Trường cần chẩn đoán: đổi sang mã an toàn
        |
        +-- Trường định danh có lý do rõ: dùng token/ID theo chính sách
        |
        v
Telemetry đã tối thiểu hóa
        |
        v
Collector kiểm tra/lọc thêm
        |
        v
Backend có phân quyền và retention
~~~

Cách tốt nhất để ngăn dữ liệu nhạy cảm xuất hiện trong telemetry là **không đưa nó vào bản ghi ngay từ đầu**. Nếu secret đã được tạo thành log record hay span attribute, việc xóa ở collector vẫn không loại bỏ hoàn toàn nguy cơ trong buffer của SDK, local log file, kênh mạng, debug output hoặc exporter phụ.

### Vì sao chỉ dùng blacklist không đủ?

Blacklist có thể bỏ `password` hoặc `token`, nhưng dữ liệu nhạy cảm có thể nằm dưới key mới như `credential`, `authData`, `authorizationValue`, `input`, `payload` hoặc trong chuỗi tự do. Một DTO bổ sung trường `recoveryCode` có thể bị log ngay nếu middleware serialize toàn bộ object.

**Allowlist** tốt hơn: chỉ chấp nhận một tập trường có mục đích, kiểu dữ liệu và giới hạn kích thước đã xác định. Dùng redaction pattern như lớp bổ sung, không coi regex là biện pháp duy nhất.

## 6. Structured logging với trường được phép

Thay vì ghi toàn bộ object, định nghĩa event và trường rõ ràng.

**Không nên:**

~~~java
log.info("Payment request: {}", paymentRequest);
log.warn("Provider call failed. headers={} body={}",
        providerHeaders, providerResponseBody);
~~~

**Nên:**

~~~java
log.info(
    "payment_attempt_started route={} operation={} provider={} amount_band={}",
    "/payments",
    "authorize",
    "example-provider",
    "100k-500k"
);

log.warn(
    "payment_attempt_failed route={} provider={} reason={} retryable={}",
    "/payments",
    "example-provider",
    "UPSTREAM_TIMEOUT",
    true
);
~~~

Các giá trị trong ví dụ là enum, route chuẩn hóa hoặc khoảng số đã phê duyệt; không có email, số tài khoản, số thẻ hay token. Ngay cả `provider` hoặc amount band cũng phải nằm trong danh sách cho phép theo chính sách kinh doanh và hệ thống observability của tổ chức.

Ưu điểm của structured logging là dễ kiểm tra tập field, dễ truy vấn và tạo alert. Tuy vậy, **structured logging không tự an toàn**: nếu giá trị field là request body hoặc secret thì JSON log vẫn rò rỉ như log dạng text.

### 6.1. Tạo mã lỗi an toàn

Mã lỗi nên ổn định và có cardinality hữu hạn:

~~~text
UPSTREAM_TIMEOUT
PAYMENT_PROVIDER_UNAVAILABLE
INVALID_REQUEST_FORMAT
DATABASE_CONCURRENCY_CONFLICT
BUSINESS_RULE_REJECTED
~~~

Tránh đưa exception message đầy đủ làm `errorCode`, vì message có thể chứa raw input. Mapping exception → error category cần ở lớp xử lý lỗi có kiểm soát; không nên dựa vào `getMessage()` rồi coi đó là giá trị an toàn.

### 6.2. Chú ý field thay đổi theo thời gian

DTO có thể được thêm thuộc tính nhạy cảm khi tính năng phát triển. Logging kiểu `log.debug("{}", dto)` tự động đưa thuộc tính mới vào telemetry. Với field allowlist, thay đổi DTO không làm log thay đổi ngầm. Nếu cần thêm một trường, phải xác định mục đích observability và phân loại trước.

## 7. Ví dụ Java: tạo event log bằng allowlist

Ví dụ dưới đây dùng SLF4J, giới hạn event và các trường được ghi. Các loại enum giúp mã lỗi không trở thành một chuỗi tự do từ exception:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class PaymentTelemetry {
    private static final Logger LOG =
            LoggerFactory.getLogger(PaymentTelemetry.class);

    public enum Outcome {
        APPROVED,
        DECLINED,
        TIMED_OUT,
        FAILED
    }

    public enum FailureCategory {
        NONE,
        VALIDATION,
        UPSTREAM_TIMEOUT,
        UPSTREAM_UNAVAILABLE,
        INTERNAL_ERROR
    }

    private PaymentTelemetry() {
    }

    public static void completed(
            Outcome outcome,
            FailureCategory category,
            long elapsedMillis) {

        long safeDuration = Math.max(0L, elapsedMillis);

        LOG.info(
                "payment_completed outcome={} failure_category={} duration_ms={}",
                outcome.name(),
                category.name(),
                safeDuration
        );
    }
}
~~~

Sử dụng:

~~~java
long started = System.nanoTime();

try {
    // Gọi nghiệp vụ thanh toán.
    PaymentTelemetry.completed(
            PaymentTelemetry.Outcome.APPROVED,
            PaymentTelemetry.FailureCategory.NONE,
            (System.nanoTime() - started) / 1_000_000L
    );
} catch (ProviderTimeoutException exception) {
    PaymentTelemetry.completed(
            PaymentTelemetry.Outcome.TIMED_OUT,
            PaymentTelemetry.FailureCategory.UPSTREAM_TIMEOUT,
            (System.nanoTime() - started) / 1_000_000L
    );
    throw exception;
}
~~~

`ProviderTimeoutException` là kiểu exception giả định của ứng dụng; ví dụ minh họa việc **phân loại**, không phải một class mặc định của JDK. Trong hệ thống thực, đo latency bằng monotonic clock, tính event phù hợp và đưa trace/span IDs qua instrumentation đã cấu hình.

Điểm quan trọng:

- Truyền enum thay cho một `String message` tùy ý.
- Không truyền DTO, raw exception, header hay body vào event.
- Không chứa tên tài khoản, user ID hoặc dữ liệu giao dịch trong field log.
- Nếu cần request-level correlation, sử dụng trace ID từ context hoạt động và đảm bảo chính sách lưu trữ/tra cứu phù hợp.
- Nếu code path cần log nguyên nhân lỗi chuyên sâu, chọn một tập exception types và attributes được kiểm soát; kiểm tra message/stack trước khi đưa vào telemetry.

## 8. Không ghi raw request và response ở Gateway

Gateway thường là vị trí dễ mắc lỗi nhất vì nhìn thấy dữ liệu từ nhiều API:

~~~text
HTTP Client
  |
  | Authorization, Cookie, X-API-Key,
  | URL/query, request body
  v
API Gateway ----> Access Log / Tracing / Error Log
  |
  v
Downstream Services
~~~

Hãy coi mọi phần sau là **không an toàn mặc định**:

- Request/response body: JSON, XML, multipart, upload, form data, GraphQL variables.
- Headers: `Authorization`, `Cookie`, `Set-Cookie`, `Proxy-Authorization`, `X-API-Key` và header xác thực tùy biến.
- Query parameters: `access_token`, `code`, `session`, `email`, `phone` hoặc tham số nghiệp vụ chưa được phân loại.
- Raw path chứa dữ liệu động: `/users/demo@example.invalid`.
- URL có embedded credentials, redirect URI có query, webhook callback URL có secret.
- Error response body có thể bao gồm echo input hoặc dữ liệu nhạy cảm.

**Trường nên ghi** thường là phương thức HTTP, route template, status code, duration, service/operation và correlation ID được duyệt. Nếu web framework chưa xác định route template khi request lỗi, có thể dùng route cố định như `UNKNOWN_ROUTE`, thay vì tự động fallback sang raw path.

~~~text
Khuyến nghị:
method=POST route=/orders/{orderId} status=422 duration_ms=24

Không nên:
method=POST url=/orders/customer-123?email=demo@example.invalid&token=...
~~~

Đừng dựa vào HTTP status để suy luận mọi thứ an toàn: log stack trace của một lỗi 400 có thể chứa giá trị đầu vào, còn response 200 có thể chứa thông tin riêng tư nếu middleware dump response body.

## 9. Trace attributes, events và span names

Trace thường được xem là “ít nguy hiểm hơn log” vì chủ yếu chứa thời gian. Thực tế, span có thể chứa nội dung chi tiết như request URL, SQL statement, message payload hoặc exception.

### 9.1. Đặt tên span theo operation, không theo dữ liệu người dùng

Nên:

~~~text
SERVER POST /orders/{orderId}
CLIENT GET /inventory/{sku}
INTERNAL validate-order
PRODUCER publish OrderCreated
CONSUMER process OrderCreated
~~~

Không nên:

~~~text
SERVER POST /orders/customer-12345
CLIENT GET https://service.internal/search?q=demo@example.invalid
INTERNAL validate-order-for-demo@example.invalid
~~~

Tên span phải có số biến thể hữu hạn để dễ tìm nhóm operations và tránh vô tình đưa dữ liệu cá nhân vào tên.

### 9.2. Dùng attributes có giới hạn

Ví dụ OpenTelemetry Java API:

~~~java
import io.opentelemetry.api.trace.Span;

Span span = Span.current();

span.setAttribute("app.order.validation.result", "REJECTED");
span.setAttribute("app.order.validation.reason", "INVALID_QUANTITY");
span.setAttribute("app.order.items_count", 3L);
~~~

Các key `app.order.*` là **attributes minh họa của ứng dụng**, không phải semantic conventions chính thức. Đừng thay dòng thứ hai bằng:

~~~java
span.setAttribute("app.order.validation.reason", rawRequestBody);
~~~

Các thuộc tính số có thể dùng dạng aggregate hoặc bucket. Đặc biệt tránh đưa user ID, email, number of card, request message hay URL thô vào span để tìm kiếm thuận tiện.

### 9.3. Exception và stack trace

Instrumentation có thể ghi `exception.type`, `exception.message` và `exception.stacktrace`. Việc thu exception đầy đủ không luôn phù hợp, bởi message có thể chứa SQL với literal, dữ liệu người dùng hoặc response từ provider.

Thực hành:

- Phân loại lỗi trước thành `UPSTREAM_TIMEOUT`, `VALIDATION_ERROR`, `DB_LOCK_TIMEOUT`...
- Chỉ ghi exception type/stack khi đã đánh giá và có nhu cầu thực tế.
- Tránh tự đặt exception message thành field truy vấn hay metric label.
- Nếu phải lưu stack chi tiết để điều tra, xem xét kênh bảo mật riêng, quyền truy cập chặt, TTL ngắn và masking có kiểm thử.
- Lưu ý thư viện/framework có thể tự tạo exception event; kiểm tra output sau khi bật instrumentation.

## 10. Kiểm soát SQL, database và message payload

### 10.1. Database

SQL có thể vô tình ghi dữ liệu nhạy cảm khi query được xây dựng bằng cách nối chuỗi, hoặc logger in parameter bindings.

~~~text
Không nên:
SELECT * FROM customers WHERE email = 'demo@example.invalid'

Nên quan sát theo operation:
db.system=postgresql
db.operation=SELECT
db.collection=customers
duration_ms=38
status=OK
~~~

Dù SQL dùng bind parameters, một số chế độ debug của ORM/driver vẫn có thể ghi bound parameter values. Phải kiểm tra cấu hình logging ở cả Spring Data, Hibernate, JDBC driver và proxy DB đang sử dụng. Không bật các chế độ log SQL bind toàn hệ thống production chỉ để xử lý một sự cố.

### 10.2. Message brokers

Producer/consumer có thể ghi raw Kafka record, RabbitMQ message, event body hoặc dead-letter payload khi gặp lỗi parse. Cần phân biệt:

- **Envelope kỹ thuật:** topic, event type, delivery attempt, số byte, trạng thái xử lý.
- **Payload nghiệp vụ:** tên, địa chỉ, nội dung đơn hàng, dữ liệu thanh toán, tài liệu.
- **Trace context headers:** metadata dùng để nối trace, có thể kèm baggage cần lọc.

Logging phù hợp:

~~~text
event_type=OrderCreated topic=orders status=PROCESSED
attempt=2 duration_ms=81 payload_size_bucket=1KB_10KB
~~~

Logging rủi ro:

~~~text
Failed to consume record: body=<toan-bo-payload-khach-hang>
headers=<toan-bo-thong-diep-va-secret>
~~~

Một dead-letter queue có thể cần payload gốc để xử lý nghiệp vụ theo chính sách riêng; điều đó **không cấp quyền** in payload đó ra log/trace. Phân quyền, retention và truy cập dữ liệu trong queue phải được kiểm soát riêng.

## 11. Baggage: lựa chọn nội dung và ranh giới lan truyền

Baggage có chức năng truyền metadata qua process và đôi khi qua tổ chức khác. Các library có thể tự động copy baggage vào outgoing HTTP headers hoặc message headers. Một giá trị nhạy cảm được đặt vào baggage ở Gateway có thể lan theo cả chuỗi:

~~~text
Gateway
  baggage: customer.email=demo@example.invalid
       |
       +--> Order Service
       |       +--> Inventory Service
       |       +--> Pricing Service
       |
       +--> Analytics Service
       |       +--> Vendor API
       |
       +--> Event Producer
               +--> Message Broker
                       +--> Consumer
~~~

Vì vậy baggage phải có **allowlist riêng**, thường nghiêm ngặt hơn log nội bộ. Chỉ đưa những metadata thật sự cần propagate tới downstream. Ví dụ trạng thái rollout hoặc phân vùng deployment có thể hữu ích, nhưng vẫn phải đánh giá ảnh hưởng đến bí mật kinh doanh.

### 11.1. Ví dụ phân loại baggage key

| Key giả định | Đánh giá | Cách thay thế |
|---|---|---|
| `auth.token` | Cấm | Chuyển auth qua cơ chế xác thực dành riêng; không dùng baggage. |
| `user.email` | Cấm | Không propagate dữ liệu cá nhân cho mục đích tracing. |
| `payment.card` | Cấm | Không đưa thông tin thanh toán vào telemetry. |
| `customer.id` | Mặc định không đưa | Nếu cần liên kết nghiệp vụ, dùng context nghiệp vụ đã được bảo vệ và kiểm soát quyền. |
| `deployment.region` | Có thể cho phép | Chỉ dùng mã vùng kỹ thuật không nhạy cảm và cần thiết. |
| `flow.stage` | Có thể cho phép | Enum hữu hạn, ví dụ `checkout`/`fulfillment`, sau khi xét nhu cầu. |

Baggage không tự động trở thành span attribute trong mọi thư viện; nhưng SDK, processor, custom instrumentation hoặc log enrichment có thể copy nó sang trace/log. Do đó, **không ghi secret vào baggage dù tạm thời chưa thấy nó ở backend**.

### 11.2. Phía gửi cần lọc những gì?

- Kiểm tra rõ bộ propagators được cấu hình: có W3C Trace Context, W3C Baggage hay định dạng tùy biến nào?
- Quyết định domain/transport nào được phép nhận baggage.
- Bỏ key không được chấp nhận, kể cả baggage do client bên ngoài gửi.
- Giới hạn kích thước và số phần tử để ngăn lạm dụng và tránh vượt header limits.
- Bảo đảm key/value không chứa bí mật hoặc dữ liệu người dùng; không chỉ dựa vào tên key vì value cũng có thể bị lạm dụng.

### 11.3. Phía nhận cần làm gì?

Bên nhận không được coi baggage là dữ liệu xác thực hoặc tenant identity đáng tin cậy. Nếu logic ứng dụng cần tenant hoặc quyền truy cập, nó phải dùng security context đã xác minh qua auth, không dựa vào propagated key do caller có thể sửa.

Trace context (`traceparent`, `tracestate`) cũng là metadata do bên gửi cung cấp; không dùng trace ID để xác thực. Với ranh giới tin cậy bên ngoài, cân nhắc lọc hoặc khởi tạo trace context mới theo chính sách, đồng thời giữ khả năng liên kết nội bộ nếu cần.

## 12. Redaction, masking, tokenization và pseudonymization

Các kỹ thuật dưới đây phục vụ nhu cầu khác nhau; đừng dùng thay thế cho nhau một cách máy móc.

| Kỹ thuật | Ý nghĩa | Rủi ro còn lại |
|---|---|---|
| **Omission** | Không ghi trường. | Tốt nhất nếu không cần giá trị. |
| **Redaction** | Thay giá trị bằng hằng số, ví dụ `[REDACTED]`. | Có thể còn lộ tên field hoặc sự tồn tại của dữ liệu; phải bao phủ mọi nguồn. |
| **Masking** | Che một phần giá trị, ví dụ ẩn tất cả trừ phần được cho phép. | Các ký tự giữ lại vẫn có thể nhận dạng; phải có lý do rõ và chính sách. |
| **Tokenization** | Thay giá trị bằng token có bảng ánh xạ được bảo vệ. | Token có thể liên kết nhiều sự kiện, bảng ánh xạ là tài sản nhạy cảm. |
| **HMAC/pseudonymization** | Biến đổi có khóa để phục vụ correlation có kiểm soát. | Vẫn có thể là dữ liệu cá nhân/liên kết; cần quản lý khóa, rotation và TTL. |
| **Aggregation** | Biến giá trị thành bucket/category. | Thường giảm rủi ro, nhưng group hiếm vẫn có thể lộ thông tin. |

Ví dụ thay vì log số tiền chính xác hoặc email, có thể log `amount_band=LOW` và `customer_type=KNOWN` nếu các bucket đó thực sự được phê duyệt. Không dùng hash không khóa của email để tạo “user_id an toàn”; rất nhiều email có thể bị đoán và thử hash.

### 12.1. Redaction theo pattern dùng để phòng thủ bổ sung

Pattern có thể phát hiện Bearer token, chuỗi giống API key hoặc thông tin định dạng cố định; tuy vậy:

- Secret có thể xuất hiện dưới dạng JSON escape, URL encode, base64 hoặc cắt thành nhiều trường.
- Dữ liệu nhạy cảm không nhất thiết có pattern cố định (nội dung chat, địa chỉ, tên người).
- Regex quá rộng có thể phá thông tin chẩn đoán; quá hẹp thì bỏ sót.
- Thay thế sau khi event đã vào buffer không tránh mọi nguy cơ.

Ưu tiên chặn ngay API sinh log hoặc span; dùng pattern redaction ở collector/backend để bắt lỗi ngoài dự kiến.

## 13. Thiết kế nhiều lớp bảo vệ

Một pipeline quan sát tiêu biểu:

~~~text
Application code
  |   1. Allowlist fields; safe error categories
  v
Logging framework / OTel SDK / auto instrumentation
  |   2. Filter, attribute limits, sanitize interceptors
  v
Local agent / log forwarder / OTel Collector
  |   3. Redaction, processors, routing, drop fields
  v
Transport
  |   4. TLS, identity, network policy
  v
Telemetry backend
  |   5. RBAC, retention, audit, encryption, export policy
  v
Dashboard / Alert / Incident tooling
      6. Permissioned access, safe templates and notifications
~~~

**Lớp 1: Ứng dụng.** Quyết định rõ những field nào được ghi. Đó là nơi có nhiều ngữ cảnh nghiệp vụ nhất để phân loại.

**Lớp 2: SDK/instrumentation.** Giảm thu thập request/response details, headers, body, SQL binds, exception messages và query strings theo khả năng từng thư viện. Kiểm tra sau mỗi lần bật agent/plugin mới.

**Lớp 3: Collector.** Dùng processor lọc bỏ attributes có tên nhạy cảm, thay chuỗi, giới hạn độ dài, bỏ logs/spans không thể làm sạch. Cấu hình phải chạy **trước khi xuất ra mọi exporter** có liên quan.

**Lớp 4: Transport.** Mã hóa đường truyền và kiểm soát endpoint exporter. Telemetry đã được lọc vẫn có thể mang metadata nội bộ; không gửi tùy tiện tới nơi không được duyệt.

**Lớp 5: Backend.** Phân quyền dựa trên vai trò, thời gian lưu hợp lý, giới hạn export/share và audit hoạt động truy cập. Dashboard che trường không giải quyết dữ liệu gốc trong storage.

**Lớp 6: Tích hợp phụ.** Alert, chat notification, incident ticket và ảnh chụp màn hình có thể phát tán log/trace tiếp. Template thông báo nên dùng status, service, route và trace link thay vì nhúng raw event body.

### Giới hạn của collector-side redaction

Collector chỉ nhìn thấy telemetry đã được gửi tới nó. Nếu code đã ghi secret vào file log local hoặc exporter khác, việc xóa field trên một pipeline không làm dữ liệu ở các nơi khác biến mất. Cũng cần xét thứ tự processors: filter chạy sau exporter là quá muộn, và nhiều pipelines có thể dùng cấu hình khác nhau. Khi triển khai, kiểm tra config thực tế cùng dữ liệu test.

## 14. Cấu hình framework và auto instrumentation phải được kiểm tra

Một ứng dụng Spring Boot có thể dùng SLF4J/Logback, Micrometer Tracing, OpenTelemetry Java agent và các HTTP/DB/client instrumentation. Mỗi cơ chế có phạm vi thu thập riêng.

Danh sách vị trí thường cần rà soát:

- HTTP access log ở web server, ingress, Gateway hoặc reverse proxy.
- Logging filter tự ghi `request.getHeaderNames()`, `request body` hoặc response body.
- Feign/RestClient/WebClient/OkHttp interceptors ở chế độ verbose/debug.
- gRPC interceptors ghi request/response protobuf bằng `toString()`.
- Hibernate SQL logging, JDBC proxy, bind parameters và driver diagnostics.
- Kafka/RabbitMQ producer-consumer interceptors, serialization errors và DLQ handlers.
- Exception handler, validation library và request binding error messages.
- OpenTelemetry semantic attributes, span events, exception recording và resource attributes.
- Logback encoder, JSON layout, MDC enrichment và custom appenders.
- Collector processors, exporters và backend ingestion pipelines.

**Không bật “log everything” trên production** để tìm lỗi trong một service; việc đó thường tạo một lượng lớn dữ liệu không kiểm soát. Nếu cần phiên debug có chủ đích, dùng phạm vi hẹp, dữ liệu đã khử nhạy cảm, TTL ngắn, quyền xem phù hợp và quy trình tắt lại.

Lưu ý tên thuộc tính/cờ cấu hình thay đổi theo phiên bản Spring Boot, Micrometer và OpenTelemetry. Không sao chép một option từ tài liệu phiên bản khác rồi giả định dữ liệu sẽ được lọc. Đọc output thực tế từ collector/backend và kiểm chứng bằng request synthetic.

## 15. Phân biệt dữ liệu phục vụ debug với dữ liệu cần bảo tồn nghiệp vụ

Khi điều tra lỗi thanh toán, đôi khi cần xem nội dung giao dịch để đối soát. Nhu cầu đó **không đồng nghĩa** nên ghi payload vào log.

Hãy tách hai loại hệ thống:

- **Kho nghiệp vụ có kiểm soát:** giữ dữ liệu cần để phục vụ giao dịch, compliance hoặc hỗ trợ khách hàng theo chính sách; có ACL, mã hóa, versioning, audit và vòng đời xóa.
- **Hệ thống quan sát:** thu các mã lỗi, trạng thái, thời gian, service dependencies và ID tham chiếu đã được chấp thuận; không chứa bản sao tùy ý của đối tượng nghiệp vụ.

Ví dụ khi payment provider báo lỗi, log `provider=example, category=UPSTREAM_TIMEOUT, attempt=2`. Nếu thực sự cần truy vấn giao dịch cụ thể, hệ thống hỗ trợ phải truy cập kho nghiệp vụ qua công cụ có quyền phù hợp; không dựa vào việc tìm token hoặc số tài khoản trong log.

Một business ID trong telemetry vẫn có thể mang thông tin nhạy cảm. Nếu được phép dùng, cân nhắc token hóa, phân loại quyền và retention riêng. Không cho rằng chuỗi UUID hay số ngẫu nhiên luôn an toàn: nó có thể là mã mở trực tiếp tài nguyên hoặc tạo correlation dài hạn.

## 16. Exceptions: chẩn đoán được mà không lộ input

Khi xử lý lỗi, việc `log.error("failed", ex)` có thể hữu ích nhưng không phải luôn an toàn. Ví dụ exception từ HTTP client có thể chứa URL đầy đủ; validation exception chứa giá trị request sai; database exception có thể chứa SQL và literal.

Thiết kế một handler tập trung:

~~~text
Throwable / framework exception
              |
              v
Phân loại bằng type + context được phép
              |
              +--> error_category = INVALID_REQUEST
              +--> http_status = 400
              +--> route = /orders/{orderId}
              +--> trace_id = từ tracing context nếu có
              |
              v
Log event ít trường, hữu ích cho cảnh báo
~~~

Các nguyên tắc:

1. Dùng loại exception và mã lỗi rõ nghĩa; không chọn category bằng cách log `exception.getMessage()`.
2. Không echo input nhạy cảm vào HTTP error response rồi vô tình ghi response đó.
3. Không đưa raw validation rejected value vào log hoặc span event.
4. Khi cần stack trace trong nội bộ, cân nhắc lọc/masking và kênh quyền truy cập hạn chế; không tự động gắn stack trace vào baggage hoặc tags.
5. Bảo đảm error handler ở retry, circuit breaker, async callback và message consumer cũng tuân theo chính sách này.
6. Quan sát lỗi bằng số lượng, tỷ lệ, service, route, dependency và trace link; điều đó thường đủ để xác định vị trí lỗi trước khi cần dữ liệu nghiệp vụ.

### Error log “an toàn” vẫn có thể gây rò rỉ gián tiếp

Ví dụ `reason=USER_NOT_FOUND` tại một endpoint công khai có thể tạo signal để suy đoán tài khoản tồn tại. Việc phát thông tin từ HTTP response và telemetry có mức rủi ro khác nhau, nhưng cùng cần xem xét. Không đưa giá trị email/phone vào error category hoặc group label; giữ category ở mức đủ để vận hành.

## 17. MDC và correlation context: tránh lan truyền nhầm

Trong Java, SLF4J MDC thường được dùng để bổ sung `trace_id` hoặc `request_id` vào mọi log line. Nếu bạn tự đưa `userEmail`, `tenantName` hoặc `authorization` vào MDC, giá trị đó có thể xuất hiện ở **tất cả** log bên trong request, kể cả log từ thư viện không do bạn kiểm soát.

~~~java
// Rủi ro: lưu PII trong logging context dùng chung.
MDC.put("customerEmail", customer.getEmail());

// An toàn hơn nếu chính sách chấp thuận mã tương quan:
MDC.put("requestId", safeCorrelationId);
~~~

Một `safeCorrelationId` phải được sinh/kiểm soát theo chính sách; không mặc định tin ID do caller tự đặt và không sử dụng bearer token làm request ID.

Phải đóng scope và xóa giá trị khi request hoàn tất:

~~~java
try {
    // Xử lý request và log theo allowlist.
} finally {
    MDC.remove("requestId");
}
~~~

Nếu framework đã tự gắn trace ID vào MDC, tránh ghi đè thủ công. Qua thread pool hoặc reactive pipeline, MDC có thể được copy khác với OpenTelemetry Context; quản lý vòng đời rõ để không trộn dữ liệu giữa các request hoặc giữ dữ liệu người dùng trong thread tái sử dụng.

## 18. HTTP, RPC và message propagation: kiểm soát trước khi ra khỏi biên tin cậy

Khi một request đi qua nhiều service:

~~~text
Internet Client
      |
      v
Public Gateway
      |  kiểm tra và lọc inbound headers/baggage
      v
Order Service ------> Inventory gRPC
      |
      +-------------> Message Broker ------> Worker
      |
      +-------------> External Payment Provider
                                |
                                v
                       Không forward metadata
                       nội bộ không cần thiết
~~~

Một **trust boundary** có thể là:

- Giữa Internet và Gateway.
- Giữa các nhóm service có phạm vi dữ liệu khác nhau.
- Từ service nội bộ sang đối tác bên ngoài.
- Từ môi trường production sang hệ thống test.
- Từ tenant này sang tenant khác trong một nền tảng multi-tenant.

Tại mỗi boundary, cần quyết định:

1. Trace context nào được phép nhận hoặc truyền đi?
2. Baggage keys nào được giữ, bỏ hoặc thay thế?
3. Có cần bắt đầu trace mới và tạo link nội bộ hay không?
4. Propagator/HTTP client có đang tự inject headers ngoài dự kiến không?
5. Có log outbound request headers/body trong interceptor không?
6. Có gửi trace cho vendor có hợp đồng và quyền truy cập phù hợp không?

Không đặt authentication claims vào W3C Baggage để “đỡ gọi auth service”. Dữ liệu xác thực phải được truyền qua cơ chế bảo mật riêng, với kiểm tra chữ ký/phiên/quyền tương ứng.

## 19. Thiết kế metric label có cardinality thấp

Một số field vừa nhạy cảm vừa tạo số lượng time series rất lớn:

~~~text
Không nên:
http_requests_total{user_email="...",session_id="...",path="/users/12345"}

Nên:
http_requests_total{route="/users/{id}",status_class="4xx",method="GET"}
~~~

Những trường dùng để grouping phải có tập giá trị được kiểm soát:

| Field | Dạng an toàn gợi ý |
|---|---|
| HTTP route | Mẫu route, ví dụ `/customers/{id}` |
| Status | `2xx`/`4xx`/`5xx` hoặc numeric status khi hợp lý |
| Error category | Enum hữu hạn |
| Retry | Count hoặc bucket |
| Latency | Histogram với bucket phù hợp |
| Dependency | Service/operation có danh mục |
| Queue | Topic/consumer group được duyệt, tránh tên chứa tenant/user thô |
| Region | Mã vùng infrastructure không chứa dữ liệu cá nhân |

Metric không phải nơi làm **request-level lookup**. Dùng trace ID trong log/tracing nếu được phê duyệt và truy vấn qua hệ thống phù hợp; tránh biến mỗi request thành một time series.

## 20. Logging trong môi trường kiểm thử và production

Rủi ro ở môi trường phát triển đôi khi lớn hơn production vì dữ liệu có thể được copy vào ticket, ảnh màn hình hoặc báo cáo CI.

**Trong unit test:** dùng fake secret hoặc synthetic PII rõ ràng, ví dụ `TEST-SECRET-DO-NOT-USE-123` và email với domain `.invalid`. Không dùng token production hay dữ liệu khách hàng thật làm fixture.

**Trong integration test:** kiểm chứng HTTP error handling, validation, database errors, message consumer failure, timeout và retry với logging/tracing instrumentation thật. Log output có thể được capture in-memory hoặc qua test collector.

**Trong CI:** kiểm soát test logs/artifacts và không in environment variables, secret values hoặc command arguments chứa mật khẩu.

**Trong staging:** dữ liệu copy từ production phải đi qua quy trình giảm nhạy cảm; “staging nên ai cũng xem được” không phải lý do chấp nhận dữ liệu cá nhân trong telemetry.

**Trong production:** quyền debug tạm thời cần kiểm soát thời gian và phạm vi. Khi tắt debug, xác nhận config runtime đã quay về mức thường dùng.

## 21. Kiểm thử tự động: telemetry không được chứa synthetic secret

Một kiểm thử tốt phải phát hiện rò rỉ từ cả log và trace. Với một synthetic secret không có trong cấu hình thông thường:

~~~text
TEST-SECRET-DO-NOT-USE-123
demo@example.invalid
SYNTHETIC-CARD-NUMBER
~~~

Thực hiện các luồng:

1. Request thành công có Authorization header giả lập và payload chứa synthetic email.
2. Request validation lỗi với rejected value chứa synthetic secret.
3. HTTP client timeout hoặc trả 500 kèm error body có synthetic secret.
4. Database query bị lỗi và driver tạo exception có SQL/parameters.
5. Message consumer deserialize lỗi với payload synthetic.
6. Request chuyển thread và phát spans/logs downstream.
7. Outbound call tới external domain khi incoming request có baggage không được phép.

Sau đó kiểm tra:

- Appender/captured log events không chứa secret, kể cả formatted messages và Throwable proxies.
- Span attributes, events và resource attributes không chứa secret; không chỉ kiểm tra span names.
- Raw metadata/header mà application hoặc auto instrumentation inject ra downstream không chứa baggage key/value bị cấm.
- Collector output trước backend không chứa synthetic secret ở tất cả export pipelines.
- Metric attribute sets không chứa email, user IDs hoặc high-cardinality input values.
- Alert templates và error response capture không echo secret vào thông báo vận hành.

### 21.1. Ví dụ kiểm thử log allowlist bằng Java

Đây là ý tưởng unit test với một test appender đã cấu hình để lấy formatted log lines:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.util.List;
import org.junit.jupiter.api.Test;

class PaymentTelemetryTest {

    @Test
    void secretIsNotPartOfSafeTelemetryEvent() {
        String syntheticSecret = "TEST-SECRET-DO-NOT-USE-123";

        // Arrange: tạo request/DTO thử nghiệm có chứa syntheticSecret.
        // Act: chạy handler có ghi các event theo allowlist.
        // List<String> lines = captureFormattedLogLines();

        List<String> lines = List.of(
                "payment_completed outcome=FAILED " +
                "failure_category=UPSTREAM_TIMEOUT duration_ms=24"
        );

        assertFalse(
                lines.stream().anyMatch(line ->
                        line.contains(syntheticSecret))
        );
    }
}
~~~

`List.of(...)` ở trên là fixture minh họa; một integration test thực sự phải **capture log được sinh bởi handler**, và kiểm tra cả Throwable, attributes, tracing exporter và outbound propagation. Nếu test chỉ tạo chuỗi đã biết an toàn rồi assert, nó không chứng minh ứng dụng thật không rò rỉ.

### 21.2. Test theo allowlist mạnh hơn kiểm tra vài secret cụ thể

Đừng chỉ kiểm tra một regex token. Hãy kiểm tra schema của log/traces:

~~~text
Allowed keys:
service, operation, route, status, error_category,
dependency, duration_ms, retry_count, trace_id, span_id
~~~

Nếu một event xuất hiện key bất ngờ như `requestBody`, `email`, `headers`, `auth`, `dbParameters` hoặc một key không được đăng ký, test phải báo thất bại. Sau đó đối chiếu nội dung giá trị để phát hiện secret nằm trong field tưởng như an toàn.

## 22. Quan sát việc lọc dữ liệu mà không log dữ liệu bị lọc

Chính bộ lọc cũng cần được theo dõi, nhưng đừng tạo “redaction log” chứa giá trị thô.

Nên có metric:

~~~text
telemetry_redaction_total{rule="authorization_header",service="gateway"}
telemetry_dropped_attributes_total{reason="not_allowlisted"}
telemetry_rejected_events_total{reason="oversized_payload"}
~~~

Trường `rule` và `reason` là enum/identifier được duyệt, không phải key ngẫu nhiên có secret. Không ghi:

~~~text
Redacted this secret: Bearer <original-token>
Rejected baggage value: customerEmail=demo@example.invalid
~~~

Bộ lọc có thể ghi số lượng, loại quy tắc, service và mức độ; debug chi tiết về dữ liệu bị cấm nên diễn ra trong môi trường synthetic, không qua production telemetry.

## 23. Quyền truy cập, retention và xuất dữ liệu

Ngay cả telemetry đã tối thiểu hóa vẫn có thể chứa thông tin nhạy cảm về kiến trúc, dịch vụ, hành vi người dùng hoặc sự cố.

Các kiểm soát cần xem xét:

- **RBAC/least privilege:** developer chỉ thấy môi trường và service cần thiết; truy cập dữ liệu nâng cao có thể cần phê duyệt.
- **Phân tách môi trường:** không cho prod telemetry tự động chảy vào workspace test có quyền rộng.
- **Retention:** xác định thời gian lưu cho logs, traces, metrics và archives; tránh lưu vô thời hạn vì “sau này biết đâu cần”.
- **Mã hóa:** TLS trên đường truyền và mã hóa lưu trữ theo tiêu chuẩn nội bộ; bảo vệ khóa/API token của exporter.
- **Audit:** biết ai truy vấn, export hoặc chia sẻ dữ liệu có rủi ro.
- **Dashboard và alerts:** áp dụng quyền xem và tránh nhúng raw logs vào email/chat/webhook thiếu bảo vệ.
- **Third-party vendors:** đánh giá quyền truy cập, nơi lưu trữ, dữ liệu chuyển đi và cách xóa trước khi tích hợp.
- **Backup và snapshots:** chính sách xóa dữ liệu bị lộ có thể cần tính cả archive, replica và bản export.

Không xem màn hình dashboard đã che là bằng chứng không có dữ liệu trong storage. Cần kiểm chứng ingestion và đường export thực tế.

## 24. Khi phát hiện secret hoặc PII đã lọt vào telemetry

Một sự cố rò rỉ telemetry cần được xử lý như sự cố dữ liệu, không chỉ sửa một log statement.

1. **Ngăn phát sinh thêm:** tắt code/config ghi dữ liệu thô, rollback instrumentation gây rò rỉ hoặc áp filter khẩn cấp ở nơi phù hợp.
2. **Xác định phạm vi:** loại dữ liệu, service, thời gian, môi trường, collector, backend, export pipelines, alert/chat/ticket và log archives.
3. **Bảo vệ hoặc thay thế credential:** nếu token, key hoặc mật khẩu bị ghi, làm việc với chủ sở hữu hệ thống để thu hồi/rotate theo quy trình; masking bản lưu không làm credential hết hiệu lực.
4. **Hạn chế truy cập:** áp dụng quyền xem tạm thời chặt hơn trong khi điều tra.
5. **Loại bỏ dữ liệu theo quy trình:** đánh giá tính khả thi của xóa/expire trên indexes, object storage, replicas, backups, exports và vendor; không mặc định xóa trên UI là xóa toàn bộ.
6. **Ghi nhận và thông báo theo chính sách:** liên hệ nhóm security/privacy/compliance và thực hiện nghĩa vụ thông báo thích hợp nếu áp dụng.
7. **Đặt biện pháp ngăn tái diễn:** kiểm thử synthetic secret, schema allowlist, review pipeline và guardrails cho instrumentation mới.
8. **Kiểm tra lại bằng đầu ra thực:** xác nhận không còn secret trong log, trace, baggage hay alert khi chạy các đường lỗi tương đương.

Không sao chép secret đang bị lộ vào issue, chat hoặc báo cáo sự cố chỉ để minh họa. Dùng tên trường, dạng dữ liệu và ví dụ tổng hợp, kèm tham chiếu bảo mật nếu thực sự cần điều tra.

## 25. Quy trình triển khai cho một microservice thực tế

**Bước 1 — Liệt kê nguồn telemetry.** Gồm application logger, access log, metrics, tracing agent, RPC interceptors, DB debug, broker consumer, collector và vendor exporters.

**Bước 2 — Phân loại dữ liệu.** Tạo danh sách các loại secret/PII, field nghiệp vụ, key có khả năng liên kết; xác định chủ sở hữu và chính sách.

**Bước 3 — Định nghĩa schema allowlist.** Quy định event name, keys, kiểu giá trị, enum/bucket, tối đa ký tự và lý do quan sát. Không chấp nhận raw object dump như field mặc định.

**Bước 4 — Thực thi tại nguồn.** Sửa middleware, error handlers, span enrichers, log encoders và baggage propagation để chỉ phát dữ liệu được phép.

**Bước 5 — Thêm phòng thủ ở pipeline.** Lọc attributes/headers, kiểm soát collector processors, giới hạn kích thước, quyền export và retention.

**Bước 6 — Kiểm thử end-to-end.** Gửi request chứa synthetic secret qua HTTP → RPC → broker → worker, bao gồm timeout và exception. Capture log, spans, metadata và collector output.

**Bước 7 — Kiểm tra quyền xem.** Xác định người dùng, dashboard, alert channels và bên thứ ba có thể truy cập; đóng đường chia sẻ rộng không cần thiết.

**Bước 8 — Theo dõi thay đổi.** Mỗi lần nâng instrumentation, thêm dependency hoặc bật debug config, chạy lại test chống rò rỉ. Thêm review cho field mới trong telemetry schema.

### Checklist trước khi bật tính năng quan sát mới

- [ ] Dữ liệu cần ghi có mục đích chẩn đoán cụ thể.
- [ ] Không ghi token, credential, cookie, request/response body hoặc PII thô.
- [ ] Log/trace fields có allowlist và giá trị được chuẩn hóa.
- [ ] HTTP route đã dùng template; URL/query và SQL bind không bị thu thập thô.
- [ ] Exception messages/stack traces được kiểm soát theo rủi ro.
- [ ] Baggage keys được lọc ở inbound và outbound trust boundaries.
- [ ] Metric labels có cardinality hữu hạn và không chứa dữ liệu người dùng.
- [ ] Collector/exporters không mở đường dữ liệu chưa được lọc.
- [ ] Test synthetic secret đi qua cả success, error, async và retry paths.
- [ ] Backend có phân quyền, retention, audit và quy trình xử lý rò rỉ.

Checklist trên là công cụ áp dụng tại team, không thay thế yêu cầu chính sách nội bộ hoặc quy trình bảo mật của từng tổ chức.

## 26. Bài tập tình huống

Một hệ thống đặt hàng có:

~~~text
Mobile Client
   |
   | POST /orders?email=demo@example.invalid
   | Authorization: Bearer TEST-SECRET-DO-NOT-USE-123
   v
API Gateway
   |
   | HTTP
   v
Order Service
   |-- gRPC --> Inventory Service
   |-- Kafka: OrderCreated --> Notification Worker
   |-- HTTP --> Payment Provider
   v
Order Database
~~~

Bạn phát hiện:

1. Gateway access log đang lưu `request_uri` đầy đủ.
2. Order Service ghi `log.info("payload={}", request)`.
3. gRPC interceptor khi lỗi ghi toàn bộ protobuf request.
4. Kafka consumer ghi raw message body khi deserialize thất bại.
5. Java instrumentation tạo span attribute chứa `url.full` của Payment Provider, trong đó URL có query token.
6. Một developer thêm `customer.email` vào baggage để lọc trace nhanh hơn.
7. Metric `orders_failed_total` đang dùng label `customer_id`.

### Câu hỏi

1. Những điểm nào phải được sửa tại nguồn? Có thể chỉ áp một redaction rule trong collector là đủ không?
2. Với Gateway, nên lưu route và các field nào để vẫn biết endpoint nào lỗi?
3. Với gRPC và Kafka, làm sao giữ đủ thông tin về lỗi parse mà không ghi request/message body?
4. Có nên truyền email trong baggage tới Payment Provider không? Nếu không, dùng phương pháp nào để liên hệ sự kiện một cách được kiểm soát?
5. Với metric, thay `customer_id` bằng label gì để vẫn phân tích lỗi hữu ích?
6. Nếu Bearer token đã xuất hiện trong log production, cần những việc gì ngoài xóa field khỏi code?

### Hướng phân tích

- Cả bảy điểm đều cần đánh giá và sửa ở tầng sinh dữ liệu hoặc instrumentation, vì collector chỉ là lớp kiểm soát tiếp theo; raw secret có thể đã nằm trong local file/buffer hoặc exporter khác.
- Gateway dùng `http.method`, route template như `/orders`, response status, duration, error category, service và trace/correlation ID được phép.
- gRPC ghi method, error code dạng enum, duration và payload size bucket nếu được phép; Kafka ghi topic, event type, deserialize-error category, attempt count và message size bucket. Không ghi raw protobuf hoặc body.
- Không truyền email qua baggage. Nếu cần tra cứu theo giao dịch, dùng job/order reference được bảo vệ theo chính sách hoặc hệ thống hỗ trợ có phân quyền; tracing vẫn truyền trace context chuẩn mà không mang dữ liệu cá nhân.
- Metric dùng route, status class, dependency, error category hoặc message type với tập giá trị hữu hạn.
- Với token đã lộ, ngăn phát sinh tiếp, xác định phạm vi truy cập/export, cân nhắc thu hồi/rotate credential, xử lý dữ liệu đã lưu và bổ sung test chống tái diễn.

## 27. Ghi nhớ

Một hệ thống có log và trace tốt không cần nhìn thấy token, email hay request body để biết **service nào lỗi, gọi dependency nào, mất bao lâu và vì sao**. Hãy thiết kế telemetry theo allowlist, ghi những trạng thái được chuẩn hóa và kiểm soát mọi chỗ tự động thu dữ liệu, đặc biệt HTTP URL/query, exception, database binds, message bodies và propagated baggage.

Ngăn dữ liệu nhạy cảm **trước khi nó trở thành telemetry** là biện pháp mạnh nhất. Collector redaction, phân quyền, retention, mã hóa và kiểm thử end-to-end là các lớp bổ sung để giảm rủi ro. Mỗi lần mở rộng tracing hoặc logging, kiểm chứng cả đường thành công lẫn đường lỗi để sự quan sát không đánh đổi quyền riêng tư và an toàn dữ liệu.
