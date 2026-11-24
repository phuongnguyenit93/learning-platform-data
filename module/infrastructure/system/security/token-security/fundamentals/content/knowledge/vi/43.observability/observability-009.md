# Trace token exchange: Theo dõi phân tán quá trình trao đổi token

## 1. Mục tiêu và phạm vi

Một lần OAuth 2.0 Token Exchange thường đi qua nhiều thành phần: API client, dịch vụ nghiệp vụ, Authorization Server hoặc Security Token Service (STS), kho khóa, hệ thống kiểm tra token nguồn và resource server đích. Khi một request chậm, bị từ chối hoặc nhận token không đúng quyền, log riêng lẻ của từng dịch vụ thường không đủ để dựng lại toàn bộ đường đi. **Trace token exchange** sử dụng distributed tracing để liên kết các bước xử lý bằng trace ID và span, từ đó xác định thành phần nào xử lý, mất bao lâu và quyết định xảy ra ở đâu.

Trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, tracing cần hỗ trợ quan sát vòng đời token mà vẫn giữ bí mật credential. Ta cần biết request exchange nào đã được xử lý, STS có xác minh subject/actor, đánh giá audience/scope và phát hành token hay không; đồng thời cần phân biệt dấu vết kỹ thuật với audit bảo mật. Trace không xác thực token, không cấp quyền và không thay thế audit log.

Sau bài học, người học có thể:

- Giải thích trace, span, parent-child relationship, trace context và correlation ID.
- Thiết kế trace cho luồng exchange qua client, STS, key service và resource server.
- Dùng OpenTelemetry và W3C Trace Context để truyền ngữ cảnh giữa dịch vụ.
- Chọn span attributes an toàn để điều tra latency và lỗi policy.
- Ngăn bearer token, refresh token, client secret, claims nhạy cảm và dữ liệu cá nhân lọt vào trace.
- Kiểm thử propagation, sampling, lỗi downstream và khả năng truy vấn trace trong hệ thống quan sát.

## 2. Trace, span và correlation trong token exchange

**Trace** là toàn bộ đường đi của một request xuyên qua các dịch vụ. **Span** đại diện cho một thao tác có thời gian bắt đầu/kết thúc, có thể có parent span, attributes, events, status và links. Mỗi trace có trace ID; mỗi span có span ID riêng. Parent-child cho biết quan hệ thực thi, không chứng minh danh tính hoặc quyền hạn của thành phần.

Ví dụ một ứng dụng Đơn hàng cần gọi dịch vụ Kho:

1. API client gửi yêu cầu nghiệp vụ tới Orders API.
2. Orders API yêu cầu STS đổi access token hiện có thành token có audience là Inventory API.
3. STS xác thực client, kiểm tra subject token, actor/delegation và policy.
4. STS có thể gọi introspection, kiểm tra trạng thái token nguồn hoặc kho khóa.
5. STS phát hành token mới với scope được cho phép.
6. Orders API gọi Inventory API bằng token mới.

Một trace có thể biểu diễn các thao tác này:

~~~mermaid
sequenceDiagram
    participant C as API Client
    participant O as Orders API
    participant S as STS / Authorization Server
    participant I as Introspection / Key Service
    participant V as Inventory API
    C->>O: POST /orders/{id}/reserve
    Note over C,O: Trace T, span orders.reserve
    O->>S: OAuth token exchange
    Note over O,S: Child span token.exchange
    S->>I: Validate subject token
    Note over S,I: Child span token.validate
    I-->>S: active / claims metadata
    S->>S: Evaluate audience and scope policy
    S-->>O: Issued token with reduced scope
    O->>V: POST /inventory/reservations
    Note over O,V: Child span inventory.reserve
    V-->>O: Result
    O-->>C: Business response
~~~

Trong tracing thực tế, mỗi service tạo span server khi nhận HTTP request và span client khi gọi dependency. Instrumentation có thể tự tạo span HTTP; ứng dụng bổ sung span nghiệp vụ như **token.exchange** hoặc **token.policy.evaluate** để giải thích quyết định. Không tạo span tên khác nhau theo từng user, token hoặc request; tên span phải ổn định để truy vấn và thống kê.

### 2.1 Trace ID, exchange ID và audit event ID khác nhau

| Định danh | Mục đích | Đặc điểm |
| --- | --- | --- |
| Trace ID | Nối các span trong một đường đi phân tán | Theo W3C Trace Context/OpenTelemetry; có thể được truyền qua nhiều service |
| Span ID | Định danh một thao tác cụ thể | Dùng để xác định bước phát sinh latency hoặc lỗi |
| Exchange ID | Nối các bản ghi của cùng một nghiệp vụ token exchange | Có thể được sinh tại STS; giữ ổn định khi retry theo contract |
| Request/Correlation ID | Tương quan request ở lớp ứng dụng | Có thể khác trace ID; hữu ích khi đối chiếu gateway và log |
| Audit Event ID | Định danh một sự kiện audit | Duy nhất cho sự kiện; phục vụ dedup và điều tra |
| Token fingerprint | Liên kết token mà không lưu raw token | Chỉ dùng nếu cần, tạo bằng keyed HMAC và kiểm soát quyền truy cập |

Không dùng trace ID thay exchange ID hoặc audit event ID nếu hệ thống có retry, batch, queue hay nhiều trace cho cùng một nghiệp vụ. Ví dụ, client retry có thể tạo trace mới nhưng cùng một exchange operation ID theo idempotency contract. Ngược lại, một trace có thể chứa nhiều lần exchange độc lập.

Trace ID cũng **không phải bằng chứng xác thực**. Header trace context có thể đến từ client bên ngoài và có thể bị giả mạo; không dùng trace ID để cấp quyền, bỏ qua kiểm tra token hoặc quyết định danh tính actor.

## 3. Thiết kế span cho vòng đời token exchange

Một trace hữu ích phải thể hiện được ranh giới công việc và các dependency. Gợi ý cấu trúc span:

| Span | Thành phần | Nội dung quan sát |
| --- | --- | --- |
| **orders.reserve** | Orders API | Request nghiệp vụ tổng thể |
| **oauth.token.exchange** | Orders API hoặc SDK | Gửi yêu cầu exchange, nhận kết quả |
| **sts.token.exchange** | STS | Xử lý exchange end-to-end |
| **sts.client.authenticate** | STS | Xác thực client gọi token endpoint |
| **sts.subject.validate** | STS | Xác minh subject token |
| **sts.actor.validate** | STS | Xác minh actor/delegation nếu có |
| **sts.policy.evaluate** | STS | Đánh giá audience, resource, scope và policy |
| **sts.token.issue** | STS/key service | Ký hoặc tạo token mới |
| **inventory.reserve** | Inventory API | Resource server xác thực và xử lý request |

Không nhất thiết phải tạo span cho mọi hàm nội bộ. Chỉ tách span khi thao tác có ý nghĩa điều tra, có dependency riêng hoặc cần đo latency độc lập. Nếu introspection và ký token diễn ra trong STS, tạo child span cho dependency khi cần xác định nút thắt. Giữ số span hợp lý để tránh tăng chi phí telemetry.

### 3.1 Gắn kết quả policy vào span

Span có thể lưu outcome dạng enum có giới hạn:

- **issued**
- **denied**
- **error**

Reason code cũng nên là tập mã hữu hạn, ví dụ **invalid_subject_token**, **audience_not_allowed**, **scope_not_allowed**, **actor_not_trusted**, **introspection_unavailable**, **signing_failed**. Tránh gắn thông báo exception nguyên văn hoặc dữ liệu đầu vào tự do vào attribute.

Phân biệt ba kết quả:

1. **Denied**: STS đã đưa ra quyết định từ chối theo xác thực/policy.
2. **Error**: STS không hoàn tất được thao tác do dependency hoặc lỗi nội bộ.
3. **Issued**: STS đã phát hành token theo policy.

Một lần issuance thành công không có nghĩa resource server đã chấp nhận token mới. Muốn biết bước sử dụng token có thành công hay không, phải quan sát request tại resource server và nối trace hoặc exchange metadata theo thiết kế.

## 4. W3C Trace Context và truyền context qua HTTP

W3C Trace Context chuẩn hóa hai header chính:

- **traceparent**: mang version, trace ID, parent ID và trace flags.
- **tracestate**: mang dữ liệu vendor-specific theo quy tắc của chuẩn.

Ví dụ hình thức của header traceparent:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Đây chỉ là ví dụ định dạng; không mang token hoặc danh tính. OpenTelemetry propagator có thể inject context vào HTTP request và extract ở service nhận. Khi dùng instrumentation tương thích, propagation thường được thực hiện tự động.

Trong luồng token exchange, Orders API truyền trace context đến STS qua HTTP client. STS tạo server span làm child của client span; các lời gọi introspection/key service tạo thêm child span. Nếu STS nhận request từ một nguồn bên ngoài không tin cậy, cần quyết định có tiếp tục parent context bên ngoài hay bắt đầu trace mới và dùng span link theo kiến trúc. Dù chọn cách nào, trace context vẫn chỉ là metadata quan sát.

### 4.1 Không đưa dữ liệu nhạy cảm vào baggage

W3C Baggage có thể mang key/value xuyên qua nhiều service. Vì nó có thể bị forward rộng rãi, không đặt các giá trị sau vào baggage:

- Access token, refresh token, subject token, actor token hoặc token mới.
- Authorization header, cookie, client secret, private key hoặc chữ ký.
- Raw JWT claims, email, số tài khoản, dữ liệu định danh hoặc nội dung nghiệp vụ nhạy cảm.
- Scope/audience tự do lấy từ request nếu chưa được kiểm soát và chuẩn hóa.

Nếu cần truyền exchange ID, ưu tiên metadata nội bộ được tạo và kiểm soát bởi ứng dụng; chỉ truyền qua header/baggage khi đã đánh giá quyền truy cập, giới hạn kích thước và chính sách dữ liệu. Không tin một giá trị exchange ID do caller ngoài tự gửi nếu nó được dùng để kết luận nguồn gốc sự kiện.

## 5. Chọn span attributes an toàn

Attributes giúp lọc trace theo dịch vụ, kết quả và nguyên nhân. Chúng phải có ý nghĩa ổn định, không chứa bí mật và không tạo cardinality quá cao.

| Attribute gợi ý (custom) | Ví dụ an toàn | Tránh ghi |
| --- | --- | --- |
| **app.security.token_exchange.operation** | **access_token_exchange** | Toàn bộ request body |
| **app.security.token_exchange.outcome** | **issued**, **denied**, **error** | Message tự do chứa dữ liệu người dùng |
| **app.security.token_exchange.reason_code** | **scope_not_allowed** | Stack trace/message có thể chứa token |
| **app.security.token_exchange.subject_token_type** | **access_token** | Raw subject token |
| **app.security.token_exchange.issued_token_type** | **access_token** | Raw token mới |
| **app.security.token_exchange.requested_scope_count** | **2** | Scope list tự do nếu không cần thiết |
| **app.security.token_exchange.granted_scope_count** | **1** | Toàn bộ token response |
| **app.security.token_exchange.audience_alias** | **inventory_api** (từ allowlist) | Audience tùy ý chưa chuẩn hóa |
| **app.security.token_exchange.policy_version** | **v12** | Toàn bộ policy document |
| **app.security.token_exchange.duration_ms** | **37** | Không áp dụng |

Các tên **app.security.*** trong bảng là convention nội bộ đề xuất, không phải semantic convention bắt buộc của OpenTelemetry. Có thể dùng semantic conventions HTTP chuẩn cho method/status/server, nhưng cần cấu hình để instrumentation không tự thu thập header hoặc body nhạy cảm.

### 5.1 Cardinality và dữ liệu định danh

Không đặt token ID, subject ID, email, exchange ID, trace ID hoặc fingerprint làm label của metric. Những giá trị này có cardinality rất cao, làm tăng chi phí và có thể tạo dữ liệu cá nhân có thể liên kết. Chúng có thể hữu ích trong trace hoặc audit có kiểm soát, nhưng cũng cần đánh giá retention và quyền truy cập.

Scope và audience có thể là tập giá trị nhỏ nếu chỉ lấy từ allowlist nội bộ. Nếu giá trị do client tự gửi, chuẩn hóa về alias đã biết hoặc chỉ ghi count/outcome. Không cho phép người gửi tùy ý tạo hàng triệu attribute value.

### 5.2 Ví dụ span OpenTelemetry Java

Đoạn mã minh họa tạo span nghiệp vụ trong STS. Tracer được cung cấp từ cấu hình OpenTelemetry của ứng dụng:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

final class TokenExchangeTracing {
    private final Tracer tracer;

    TokenExchangeTracing(Tracer tracer) {
        this.tracer = tracer;
    }

    <T> T traceExchange(
            String subjectTokenType,
            int requestedScopeCount,
            String audienceAlias,
            ExchangeOperation<T> operation) {
        Span span = tracer.spanBuilder("sts.token.exchange")
                .setSpanKind(SpanKind.INTERNAL)
                .startSpan();

        try (Scope ignored = span.makeCurrent()) {
            span.setAttribute(
                    "app.security.token_exchange.subject_token_type",
                    subjectTokenType);
            span.setAttribute(
                    "app.security.token_exchange.requested_scope_count",
                    requestedScopeCount);
            span.setAttribute(
                    "app.security.token_exchange.audience_alias",
                    audienceAlias);

            T result = operation.execute();
            span.setAttribute(
                    "app.security.token_exchange.outcome",
                    "issued");
            return result;
        } catch (ExchangeDeniedException ex) {
            span.setAttribute(
                    "app.security.token_exchange.outcome",
                    "denied");
            span.setAttribute(
                    "app.security.token_exchange.reason_code",
                    ex.reasonCode()); // reasonCode phải là enum/allowlist
            span.setStatus(StatusCode.OK);
            throw ex;
        } catch (RuntimeException ex) {
            span.setAttribute(
                    "app.security.token_exchange.outcome",
                    "error");
            span.setAttribute(
                    "error.type",
                    ex.getClass().getSimpleName());
            span.setStatus(StatusCode.ERROR, "token exchange failed");
            throw ex;
        } finally {
            span.end();
        }
    }

    @FunctionalInterface
    interface ExchangeOperation<T> {
        T execute();
    }
}
~~~

**ExchangeDeniedException** là kiểu exception nội bộ minh họa; ứng dụng cần định nghĩa hoặc thay bằng kiểu kết quả policy thực tế. Ví dụ cố ý không ghi exception message, request body, token hay claim. Nếu policy denial được coi là kết quả nghiệp vụ bình thường, span status có thể để **OK** và dùng outcome/reason code để phân loại; lỗi hạ tầng mới đánh dấu **ERROR**. Hãy giữ quy ước thống nhất giữa các service.

Với span client gọi STS, có thể dùng **SpanKind.CLIENT** hoặc để HTTP instrumentation tạo span. Tránh tạo hai span trùng nghĩa cho cùng một HTTP operation. Khi dùng Spring Boot/Micrometer Tracing hoặc OpenTelemetry Java Agent, kiểm tra cách instrumentation hiện tại hoạt động trước khi thêm span thủ công.

## 6. Phân biệt tracing, audit log, metric và security event

Các loại telemetry giải quyết những câu hỏi khác nhau:

| Loại | Trả lời câu hỏi | Dùng cho |
| --- | --- | --- |
| Distributed trace | Request đi qua đâu, chậm ở bước nào, lỗi tại dependency nào? | Debug latency, dependency, propagation |
| Audit event | Ai đã yêu cầu, quyết định bảo mật là gì, token được cấp/thu hồi ra sao? | Điều tra, tuân thủ, chứng minh quyết định |
| Metric | Tỷ lệ, số lượng, latency và xu hướng theo thời gian là gì? | Dashboard, alert, capacity |
| Application log | Chi tiết vận hành cụ thể của một service là gì? | Debug theo request và sự kiện |
| Security event | Có mẫu hành vi đáng ngờ hoặc vi phạm policy nào? | SIEM, phát hiện và phản ứng |

Tracing có thể bị sampling, hết retention hoặc mất do exporter lỗi. Vì vậy, **không dùng trace làm bản ghi audit duy nhất** cho việc phát hành, từ chối, thu hồi hoặc thay đổi quyền token. STS nên phát audit event bền vững theo yêu cầu bảo mật; trace ID có thể được đính kèm làm tham chiếu nếu chính sách cho phép. Metric cũng không nên mang subject/token ID.

Ví dụ metric phù hợp:

- **token_exchange_requests_total** phân theo outcome và reason code hữu hạn.
- **token_exchange_duration_seconds** histogram theo service/dependency.
- **token_introspection_failures_total** phân theo loại lỗi upstream.
- **token_exchange_policy_denials_total** phân theo policy rule alias đã chuẩn hóa.

Không tạo metric label theo trace ID, exchange ID, subject ID hoặc raw audience do caller gửi.

## 7. Sampling và bảo toàn khả năng điều tra

Sampling giúp giới hạn lượng trace lưu trữ. Tuy nhiên, nếu chỉ lưu trace thành công hoặc lấy mẫu ngẫu nhiên, các lỗi bảo mật hiếm có thể không còn dấu vết. Cần thiết kế nhiều lớp:

1. Dùng metrics để đếm toàn bộ request/outcome, không phụ thuộc trace sampling.
2. Dùng audit event bền vững cho quyết định bảo mật cần chứng minh.
3. Cấu hình tail sampling hoặc chính sách ưu tiên giữ trace có lỗi, latency cao hoặc outcome **denied** nếu nền tảng hỗ trợ.
4. Giới hạn retention và quyền đọc trace; không bật lưu toàn bộ payload để tăng khả năng debug.
5. Có cơ chế đối chiếu trace exporter/drop metrics để biết telemetry có bị mất hay không.

Không phải mọi denial đều là tấn công. Ví dụ client yêu cầu scope không được phép có thể là lỗi cấu hình hợp lệ. Hãy kết hợp reason code, tần suất, client alias và baseline để cảnh báo; không tạo cảnh báo nghiêm trọng chỉ vì một trace có **denied**.

Sampling không được quyết định quyền truy cập. Một trace bị drop không làm request được phép hoặc bị từ chối. Một request bị lấy mẫu cũng không được xử lý khác về bảo mật.

## 8. Trace qua bất đồng bộ và nhiều lần exchange

Một luồng có thể chuyển từ HTTP sang message queue hoặc job nền. Khi producer phát message, instrumentation có thể inject trace context vào message headers; consumer extract context và tạo consumer span. Cần kiểm tra hệ thống queue có giới hạn header, bảo vệ metadata và xử lý retry đúng cách.

Nếu một message được xử lý nhiều lần hoặc fan-out tới nhiều consumer, quan hệ parent-child đơn giản có thể không còn mô tả đúng. OpenTelemetry span links có thể liên kết các hoạt động liên quan mà không giả vờ chúng là một chuỗi gọi đồng bộ duy nhất.

Đối với token exchange:

- Gắn exchange operation ID do hệ thống tạo vào metadata nghiệp vụ đã được kiểm soát.
- Không đưa raw token hoặc claims vào message headers.
- Mỗi lần retry có thể tạo span mới; giữ idempotency key/exchange ID theo contract để nhận biết retry.
- Ghi nhận outcome riêng cho từng lần thử và kết quả cuối cùng của operation.
- Nếu một token được đổi nhiều lần, dùng parent exchange reference hoặc fingerprint HMAC trong audit để nối chuỗi khi thật sự cần; trace ID một mình không đủ để xác định quan hệ token.

## 9. Các rủi ro bảo mật trong tracing

### 9.1 Header và body capture

HTTP instrumentation có thể thu thập header, query string hoặc exception. Với token endpoint, request thường chứa subject_token, actor_token, client_assertion hoặc thông tin client authentication trong body/header. Với resource API, Authorization: Bearer là credential dùng được. Nếu exporter lưu các trường này, trace backend trở thành nơi phát tán bí mật.

Biện pháp:

- Tắt capture request/response body cho token endpoint.
- Cấu hình header allowlist; tuyệt đối loại Authorization, Cookie, Set-Cookie, client_secret và các header tùy chỉnh chứa credential.
- Không ghi query string có dữ liệu xác thực.
- Tắt hoặc lọc exception message có thể chứa request body, URL có query nhạy cảm hoặc token.
- Kiểm thử bằng token giả đặc trưng và quét trace output để bảo đảm giá trị đó không xuất hiện.

### 9.2 Trace context từ caller không tin cậy

Caller bên ngoài có thể gửi traceparent/tracestate tùy ý. Không coi trace context là nguồn danh tính; không sử dụng nó để bỏ qua xác thực, phân quyền, rate limit hoặc audit. Cân nhắc gateway tạo trace mới hoặc liên kết bằng span link khi không muốn cho caller kiểm soát parent. Giới hạn kích thước và kiểm tra header theo W3C specification.

### 9.3 Quyền truy cập trace backend

Trace có thể chứa service topology, endpoint, tenant alias, policy version và dấu vết thời gian của hành vi người dùng. Hạn chế truy cập theo vai trò, mã hóa khi truyền/lưu, đặt retention phù hợp và audit việc truy vấn dữ liệu nhạy cảm. Không cho phép mọi developer hoặc tenant đọc toàn bộ trace production nếu không có nhu cầu.

## 10. Kiểm thử tracing token exchange

Kiểm thử cần xác nhận cả context propagation lẫn việc loại bỏ dữ liệu nhạy cảm. Có thể dùng OpenTelemetry SDK với in-memory exporter trong unit/integration test, hoặc collector/test backend riêng cho end-to-end.

### 10.1 Ma trận kiểm thử

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| TR-01 | Orders API gọi STS | Client span và STS server span cùng trace ID, quan hệ parent đúng |
| TR-02 | STS gọi introspection | Có child span cho dependency khi instrumentation bật |
| TR-03 | STS đánh giá policy và cấp token | Span có outcome **issued**, reason code không chứa dữ liệu tự do |
| TR-04 | Audience không được phép | Outcome **denied**, reason code **audience_not_allowed** |
| TR-05 | Scope không đủ | Outcome **denied**, reason code **scope_not_allowed** |
| TR-06 | Introspection timeout | Dependency span lỗi, exchange span outcome **error** |
| TR-07 | Request không có traceparent | Service vẫn xử lý bình thường và tạo trace mới theo SDK |
| TR-08 | Caller gửi traceparent không hợp lệ | Context được bỏ qua/khởi tạo mới theo propagator; không ảnh hưởng authorization |
| TR-09 | Caller gửi traceparent hợp lệ nhưng giả mạo | Không dùng trace ID làm danh tính hoặc bằng chứng quyền |
| TR-10 | Token giả được gửi trong Authorization/body | Trace export không chứa token hoặc secret |
| TR-11 | Trace bị sampling drop | Metrics/audit cần thiết vẫn được ghi theo thiết kế |
| TR-12 | Queue retry/fan-out | Span link/parent và exchange ID phản ánh đúng retry, không nhầm thành nhiều nghiệp vụ độc lập |

### 10.2 Kiểm tra trace bằng InMemorySpanExporter

Ví dụ minh họa với OpenTelemetry SDK. Dependency test cần tương thích với phiên bản OpenTelemetry của ứng dụng:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

class TokenExchangeTraceTest {
    private final InMemorySpanExporter exporter =
            InMemorySpanExporter.create();
    private final SdkTracerProvider provider =
            SdkTracerProvider.builder()
                .addSpanProcessor(SimpleSpanProcessor.create(exporter))
                .build();
    private final Tracer tracer =
            OpenTelemetrySdk.builder()
                .setTracerProvider(provider)
                .build()
                .getTracer("token-exchange-test");

    @AfterEach
    void closeProvider() {
        provider.close();
    }

    @Test
    void recordsOutcomeWithoutRecordingToken() {
        String fakeToken = "TEST_SECRET_TOKEN_DO_NOT_EXPORT";

        Span span = tracer.spanBuilder("sts.token.exchange").startSpan();
        try {
            span.setAttribute(
                    "app.security.token_exchange.outcome",
                    "denied");
            span.setAttribute(
                    "app.security.token_exchange.reason_code",
                    "scope_not_allowed");
        } finally {
            span.end();
        }

        var spans = exporter.getFinishedSpanItems();
        assertEquals(1, spans.size());
        var attributes = spans.get(0).getAttributes();
        assertEquals(
                "denied",
                attributes.get(
                    io.opentelemetry.api.common.AttributeKey.stringKey(
                        "app.security.token_exchange.outcome")));
        assertFalse(attributes.toString().contains(fakeToken));
    }
}
~~~

Trong ví dụ này, biến fakeToken chỉ đại diện cho dữ liệu nhạy cảm cần kiểm tra; không được đưa nó vào span. Test thật nên gửi token giả qua HTTP instrumentation, export span ra exporter in-memory rồi quét toàn bộ attributes, events, resource attributes và exception data để xác nhận không có token. Chỉ kiểm tra attributes của một span thủ công là chưa đủ nếu HTTP agent tự capture header/body.

### 10.3 Kiểm thử propagation giữa hai service

Có thể dựng một HTTP test server và client với OpenTelemetry propagator W3C:

1. Tạo parent span ở service gọi.
2. Inject context vào HTTP request bằng TextMapPropagator.
3. Service nhận extract context và tạo server span.
4. Export span của cả hai service vào test exporter/collector.
5. Kiểm tra trace ID giống nhau, server span parent là client span (hoặc quan hệ link đúng theo kiến trúc).
6. Thay header bằng giá trị lỗi và xác minh service vẫn xử lý an toàn.

Không chỉ assert hai span có cùng trace ID; cần kiểm tra parent span ID, span kind và các attribute cơ bản để tránh tình huống trace bị nối nhầm. Với gateway bắt đầu trace mới, kiểm tra span link thay cho parent-child.

## 11. Điều tra một lần token exchange chậm hoặc bị từ chối

Giả sử người dùng báo rằng API đặt chỗ trả lỗi. Cách điều tra:

1. Tìm trace theo request ID hoặc trace ID đã ghi nhận.
2. Xác định span tổng của Orders API và thời gian xử lý.
3. Mở child span **oauth.token.exchange** để xem outcome.
4. Nếu outcome là **denied**, xem reason code hữu hạn và policy version.
5. Nếu outcome là **error**, xem span dependency introspection hoặc key service, upstream status và latency.
6. Đối chiếu audit event bằng exchange ID để xác nhận quyết định cấp/từ chối.
7. Nếu token đã được cấp, tìm span gọi Inventory API để biết resource server có chấp nhận request hay không.

Ví dụ:

| Span | Thời lượng | Kết quả |
| --- | ---: | --- |
| **orders.reserve** | 420 ms | HTTP 502 |
| **oauth.token.exchange** | 310 ms | error |
| **sts.token.exchange** | 295 ms | error |
| **sts.subject.validate** | 280 ms | dependency timeout |
| **sts.policy.evaluate** | Không xuất hiện | Chưa tới bước policy |

Trace cho thấy thời gian chủ yếu nằm ở kiểm tra token nguồn và policy chưa được đánh giá. Điều này gợi ý điều tra introspection dependency hoặc network. Để kết luận token bị từ chối hay không, vẫn phải xem audit/response có thẩm quyền; không suy ra chỉ từ việc span policy không xuất hiện.

## 12. Checklist triển khai

- [ ] Đã xác định ranh giới span cho client, STS, introspection/key service và resource server.
- [ ] Có trace ID/span ID và exchange ID với mục đích riêng biệt.
- [ ] W3C Trace Context được inject/extract đúng qua HTTP và message queue.
- [ ] Trace context không được dùng làm danh tính hoặc quyền truy cập.
- [ ] Span name ổn định; attributes có allowlist và cardinality được kiểm soát.
- [ ] Không ghi raw access/refresh/subject/actor token, Authorization header, client secret, private key hoặc full body.
- [ ] Exception message và automatic instrumentation đã được rà soát để tránh lộ dữ liệu.
- [ ] Denied, error và issued được phân loại riêng.
- [ ] Audit event vẫn tồn tại khi trace bị sampling hoặc exporter lỗi.
- [ ] Metric không dùng trace ID, exchange ID, subject ID hoặc token fingerprint làm label.
- [ ] Tail sampling/retention hỗ trợ điều tra lỗi mà không lưu payload nhạy cảm.
- [ ] Test propagation, invalid trace context, timeout, denial và token redaction đã chạy.
- [ ] Trace backend được phân quyền, mã hóa và giới hạn retention.

## Tài liệu tham khảo

- **RFC 8693 — OAuth 2.0 Token Exchange:** luồng exchange và các thông tin subject/actor/audience/scope.
- **W3C Trace Context:** chuẩn header traceparent/tracestate và cách truyền ngữ cảnh tracing.
- **W3C Baggage:** chuẩn truyền metadata baggage và các lưu ý về phạm vi lan truyền.
- **OpenTelemetry Specification — Traces:** trace, span, context propagation, attributes, events và status.
- **OpenTelemetry Java Documentation:** tạo span, context, instrumentation và exporter trong Java.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm tra trạng thái token opaque qua authorization server.

Trace token exchange giúp nhìn thấy request đi qua những thành phần nào, mất thời gian ở đâu và kết thúc với outcome gì. Khi trace được thiết kế cùng audit event, metric và quy tắc bảo vệ dữ liệu, đội vận hành có thể điều tra lỗi vòng đời token mà không biến telemetry thành nơi lưu trữ credential hoặc nguồn quyết định quyền truy cập.
