# Không đưa secret vào tag hoặc span

## 1. Vì sao secret trong telemetry là rủi ro?

Trong chương **Bảo mật** của học phần **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, chúng ta tìm hiểu cách bảo vệ dữ liệu nhạy cảm khi Spring Boot và Spring Modulith tạo metrics, traces và logs. Observability giúp nhóm vận hành hiểu request đi qua module nào, thời gian xử lý ở đâu và lỗi phát sinh tại dependency nào. Tuy nhiên, mỗi tag hoặc span attribute được gửi tới backend telemetry cũng trở thành một bản sao dữ liệu trong hệ thống lưu trữ và tìm kiếm.

Nếu một access token, mật khẩu, API key, session cookie hoặc connection string xuất hiện trong tag/span, dữ liệu đó có thể được:
- Gửi qua OTLP tới OpenTelemetry Collector.
- Lưu ở Tempo, Jaeger hoặc tracing backend khác.
- Sao chép sang log, dashboard, alert, archive và backup.
- Hiển thị cho người có quyền đọc trace nhưng không có quyền truy cập hệ thống nghiệp vụ.
- Giữ lại lâu hơn vòng đời của secret gốc.

Do đó, **không đưa secret vào metric tag, span attribute, baggage, MDC hoặc log message**. Cách an toàn nhất là không thu thập giá trị nhạy cảm ngay từ đầu. Bộ lọc tại Collector chỉ là lớp bảo vệ bổ sung khi instrumentation hoặc ứng dụng khác vô tình phát ra dữ liệu đó.

Trong ứng dụng Spring Modulith, các thuộc tính kiến trúc như module identifier, module name và invocation type thường đủ để định vị module. Không cần gắn token, request body hoặc thông tin xác thực vào module span để điều tra một lời gọi.

### Mục tiêu học tập

1. Nhận diện secret và dữ liệu nhạy cảm có thể xuất hiện trong telemetry.
2. Hiểu sự khác nhau giữa low-cardinality và high-cardinality tags.
3. Thiết kế module span chỉ chứa metadata cần thiết.
4. Kiểm soát custom Observation, baggage, MDC và log correlation.
5. Dùng ObservationConvention/ObservationFilter đúng phạm vi.
6. Xóa hoặc biến đổi thuộc tính nhạy cảm tại OpenTelemetry Collector.
7. Bảo vệ Actuator endpoints và backend telemetry.
8. Viết kiểm thử để phát hiện secret bị rò rỉ trong metrics, traces và logs.

## 2. Những dữ liệu không được đưa vào tag hoặc span

Secret là dữ liệu có thể dùng để xác thực, cấp quyền, giải mã hoặc truy cập tài nguyên. Một số dữ liệu không phải secret theo nghĩa mật mã nhưng vẫn nhạy cảm vì có thể nhận dạng cá nhân, tiết lộ giao dịch hoặc tạo điều kiện liên kết hành vi.

| Nhóm dữ liệu | Ví dụ | Cách xử lý trong telemetry |
| --- | --- | --- |
| Mật khẩu và thông tin đăng nhập | Password, passphrase, recovery code | Không thu thập |
| Token và credential | Bearer token, refresh token, API key, OAuth client secret | Không thu thập; redact header trước logging/tracing |
| Session | Cookie, session ID, CSRF token | Không ghi giá trị thô; nếu cần liên kết, dùng correlation ID riêng được phê duyệt |
| Khóa mật mã | Private key, signing key, encryption key | Không thu thập |
| Kết nối hạ tầng | JDBC URL chứa credential, database connection string, broker credential | Không thu thập; chỉ ghi tên dependency hoặc trạng thái |
| Dữ liệu thanh toán | PAN, CVV, bank account, payment authorization secret | Không thu thập |
| Dữ liệu cá nhân | Email, số điện thoại, địa chỉ, government identifier | Tránh thu thập; chỉ dùng dữ liệu tổng hợp hoặc phân loại đã được phê duyệt |
| Payload nghiệp vụ | Request/response body, order detail, customer profile | Không ghi toàn bộ payload; chọn metadata tối thiểu |
| Thông tin lỗi nhạy cảm | SQL có dữ liệu, exception message chứa URL/credential | Chuẩn hóa thông báo và loại bỏ giá trị nhạy cảm |

Ví dụ header sau không được ghi vào span, log hoặc baggage:

```http
Authorization: Bearer eyJhbGciOi...secret...
Cookie: SESSION=9f8a...private...
X-Api-Key: live-secret-value
```

Nếu cần điều tra lỗi xác thực, hãy ghi kết quả như `authentication.result=failed`, loại credential như `authentication.method=oauth2` hoặc tên client đã được chuẩn hóa. Không ghi token hoặc nội dung header.

## 3. Các đường secret có thể đi vào telemetry

Secret không chỉ xuất hiện khi lập trình viên chủ động thêm tag. Nó có thể được thu thập gián tiếp từ HTTP instrumentation, exception, log, baggage hoặc custom observation.

```mermaid
flowchart TD
    A["HTTP request / business data"] --> B["Spring Boot instrumentation"]
    A --> C["Application log / MDC"]
    A --> D["Custom Observation / span"]
    A --> E["Baggage / propagation headers"]
    B --> F["Micrometer Observation"]
    D --> F
    E --> G["Downstream services"]
    F --> H["OTel exporter / Collector"]
    C --> I["Log pipeline"]
    H --> J["Trace backend"]
    I --> K["Log backend"]
    G --> H
```

Những điểm cần kiểm soát:

- **HTTP instrumentation:** không bật thu thập toàn bộ request headers, query parameters hoặc body nếu không có nhu cầu rõ ràng.
- **Custom span:** không truyền đối tượng request, entity hoặc exception nguyên bản vào span attributes.
- **Exception:** exception message và stack trace có thể chứa SQL, URL, payload hoặc credential.
- **Baggage:** giá trị baggage có thể được gửi qua HTTP headers tới service tiếp theo.
- **MDC:** trường correlation được đưa vào MDC có thể tự động xuất hiện trong log pattern.
- **Collector:** dữ liệu đã tới Collector có thể tiếp tục được export nếu chưa được lọc.
- **Dashboard và alert:** giá trị nhạy cảm có thể bị sao chép sang annotation, label hoặc notification.

Không giả định một instrumentation library luôn loại bỏ mọi dữ liệu nhạy cảm. Hãy kiểm tra dữ liệu thực tế được xuất từ ứng dụng và những thuộc tính mà thư viện đang thu thập.

## 4. Low-cardinality không đồng nghĩa với an toàn

Micrometer phân loại key-value thành hai nhóm:

| Loại | Nơi được xuất | Ví dụ |
| --- | --- | --- |
| Low cardinality | Metrics và traces | `module.identifier=payment`, `outcome=success`, `region=ap-southeast-1` |
| High cardinality | Traces | `module.method=authorize`, một request identifier hoặc giá trị có nhiều khả năng khác nhau |

Low-cardinality values được dùng làm metric tags và cũng có thể xuất hiện trong traces. High-cardinality values không được dùng làm meter tags để tránh tạo quá nhiều time series, nhưng vẫn có thể được lưu trong traces.

Điều này dẫn đến hai quy tắc:

1. Không đưa secret vào low-cardinality tag vì nó có thể xuất hiện ở cả metrics lẫn traces.
2. Không đưa secret vào high-cardinality tag với lý do nó không đi vào metrics. Trace backend vẫn lưu và cho phép tìm kiếm giá trị đó.

Ví dụ, `payment.provider=acme` có thể là low-cardinality metadata hợp lệ. `authorization=Bearer ...` là secret và không hợp lệ ở cả hai nhóm.

### 4.1. Cardinality là vấn đề khác với phân loại dữ liệu

Một giá trị có cardinality thấp vẫn có thể nhạy cảm. Ví dụ, một mã tenant chỉ có vài giá trị có thể không làm tăng số series đáng kể nhưng vẫn tiết lộ danh tính khách hàng doanh nghiệp. Ngược lại, một module method có nhiều giá trị là high-cardinality nhưng thường không phải secret.

Hãy đánh giá mỗi attribute theo hai câu hỏi riêng:
- Giá trị có tập hợp hữu hạn hay không? Điều này quyết định vị trí metric/trace.
- Giá trị có nhạy cảm, bí mật hoặc có thể nhận dạng cá nhân không? Điều này quyết định có được thu thập hay không.

Nếu câu trả lời thứ hai là có, hãy bỏ dữ liệu đó khỏi telemetry dù nó thuộc loại cardinality nào.

## 5. Metadata module nào nên xuất?

Spring Modulith bổ sung thông tin về module entry span để người vận hành hiểu lời gọi đi vào application module nào. Những thuộc tính kiến trúc thường hữu ích gồm:

| Attribute | Mục đích | Đánh giá |
| --- | --- | --- |
| `module.identifier` | Technical identifier của module | Giữ lại |
| `module.name` | Display name của module | Giữ lại nếu không chứa dữ liệu động |
| `module.invocation-type` | Phân biệt bean và event listener invocation | Giữ lại |
| `module.method` | Entry method được gọi | Dùng trong trace; tránh làm metric label nếu high-cardinality |

Ví dụ span an toàn:

```text
module.identifier = payment
module.name = Payment
module.invocation-type = bean
module.method = authorize
payment.provider = acme
payment.outcome = success
```

Ví dụ này mô tả cấu trúc module và kết quả kỹ thuật ở mức tổng quát. Nó không cần token, account number hoặc payment payload.

Không tự thêm các thuộc tính như:
- `payment.authorization-token`
- `customer.email`
- `order.payment-card-number`
- `database.password`
- `request.body`
- `http.request.header.authorization`

Nếu cần truy nguyên một giao dịch cụ thể, dùng trace ID do tracing system cấp và hệ thống correlation ID nội bộ đã được phê duyệt. Không dùng secret làm correlation identifier.

## 6. Tạo custom Observation với dữ liệu an toàn

Khi tạo observation riêng cho nghiệp vụ, chỉ thêm các giá trị đã được phân loại là an toàn. Dùng enum hoặc trạng thái có tập giá trị hữu hạn cho low-cardinality tags.

Ví dụ:

```java
package com.acme.shop.payment;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.stereotype.Component;

@Component
public class PaymentObservation {

    private final ObservationRegistry observationRegistry;

    public PaymentObservation(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public void authorize(Runnable operation) {
        Observation.createNotStarted(
                "payment.authorize",
                observationRegistry)
            .lowCardinalityKeyValue("module.identifier", "payment")
            .lowCardinalityKeyValue("payment.provider", "acme")
            .lowCardinalityKeyValue("payment.outcome", "attempt")
            .observe(operation);
    }
}
```

Lời gọi observation chỉ chứa module, provider đã chuẩn hóa và trạng thái tổng quát. Phần xử lý nghiệp vụ vẫn nhận credential qua cơ chế bảo mật riêng; credential không được truyền vào hàm tạo tag.

### 6.1. Anti-pattern: gắn token hoặc request body vào span

```java
// Không làm như vậy.
Observation.createNotStarted("payment.authorize", observationRegistry)
    .highCardinalityKeyValue("authorization", bearerToken)
    .highCardinalityKeyValue("request.body", requestBody)
    .observe(() -> paymentGateway.authorize(request));
```

Dù dùng high-cardinality key, token và payload vẫn có thể được export vào trace backend. Không nên dựa vào việc backend không hiển thị chúng trong metrics.

### 6.2. Tránh log exception nguyên bản khi có thể chứa secret

Không dùng exception message từ HTTP client, JDBC driver hoặc SDK làm metric tag hoặc span attribute. Một số exception chứa URL đầy đủ, query, header hoặc dữ liệu phản hồi.

Thay vì lưu toàn bộ message, có thể ghi:
- Tên loại lỗi đã chuẩn hóa, ví dụ `PaymentGatewayTimeout`.
- Dependency gặp lỗi, ví dụ `payment-gateway`.
- Kết quả, ví dụ `timeout`, `rejected` hoặc `unavailable`.
- Một mã lỗi nội bộ không chứa dữ liệu người dùng.

Nếu cần stack trace để debug, hãy kiểm soát nơi lưu, quyền truy cập và redaction policy. Không sao chép stack trace nguyên bản vào custom attribute hoặc log công khai.
## 7. Baggage và context propagation

Baggage là metadata được truyền theo trace context giữa các service. Nó hữu ích để chia sẻ một số thông tin xuyên suốt request, nhưng cũng tạo ra đường lan truyền dữ liệu nhạy cảm.

Trong Spring Boot, baggage có thể được:
- Truyền qua network bằng `management.tracing.baggage.remote-fields`.
- Đưa vào MDC để ghi log bằng `management.tracing.baggage.correlation.fields`.
- Thêm thành span tags bằng `management.tracing.baggage.tag-fields`.

Nếu một field được cấu hình ở cả ba nơi, giá trị có thể xuất hiện trong HTTP headers, logs và traces. Vì vậy chỉ cho phép các field có giá trị đã được phân loại an toàn.

Ví dụ cấu hình chỉ truyền một phân loại tenant đã chuẩn hóa:

```yaml
management:
  tracing:
    baggage:
      remote-fields:
        - tenant-tier
      correlation:
        fields:
          - tenant-tier
      tag-fields:
        - tenant-tier
```

`tenant-tier` trong ví dụ chỉ nên có các giá trị hữu hạn như `standard` hoặc `premium`. Không dùng tenant ID thực, email, user ID, session token hoặc API key làm baggage.

### 7.1. Vì sao không truyền credential qua baggage?

Baggage có thể được thêm vào request header gửi tới downstream service. Nếu credential bị đưa vào baggage, nó sẽ lan sang các service khác và có thể bị ghi log ở proxy, gateway hoặc tracing instrumentation.

Credential phải đi qua cơ chế xác thực riêng, có giới hạn scope và thời hạn. Trace context chỉ nên mang thông tin tương quan và phân loại an toàn.

### 7.2. Không đưa baggage nhạy cảm vào MDC

MDC thường được dùng trong log pattern để tự động gắn correlation metadata vào mỗi log line. Nếu cấu hình correlation field chứa email hoặc session identifier, dữ liệu đó có thể xuất hiện ở mọi log line trong scope hiện tại.

Hãy kiểm tra:
- Danh sách remote fields.
- Danh sách correlation fields.
- Danh sách tag fields.
- Header mà service gửi tới downstream.
- Log pattern và MDC keys được export.

## 8. Bảo vệ logs và MDC

Logs là một phần của observability. Một trace an toàn vẫn có thể bị lộ secret nếu ứng dụng log toàn bộ request hoặc exception.

Không log:
- Header `Authorization`, `Cookie`, `Set-Cookie`, `X-Api-Key`.
- Request/response body có mật khẩu, payment data hoặc thông tin cá nhân.
- Database URL hoặc connection string chứa credential.
- Raw session ID, reset token, OTP hoặc refresh token.
- Toàn bộ object nghiệp vụ bằng `toString()` nếu object có dữ liệu nhạy cảm.

Ưu tiên log metadata đã chọn lọc:

```text
timestamp=2026-11-27T10:15:22.184+07:00
service=shop-application
module=payment
operation=authorize
provider=acme
result=timeout
error.type=PaymentGatewayTimeout
trace_id=4bf92f3577b34da6a3ce929d0e0e4736
span_id=00f067aa0ba902b7
```

Trace ID và span ID giúp liên kết log với trace. Chúng không thay thế credential và không cần chứa thông tin nhận dạng người dùng.

### 8.1. Redact trước khi log

Nếu cần ghi lại header để chẩn đoán, chỉ chọn một allowlist header không nhạy cảm. Ví dụ, có thể ghi method, route template, response status và content type. Không ghi nguyên map headers.

Nếu log một giá trị đã che, hãy bảo đảm không để lộ một phần có thể dùng lại như prefix của token, session cookie hoặc key. Thông thường, bỏ hẳn giá trị credential là lựa chọn an toàn hơn.

### 8.2. Exception và stack trace

Một exception có thể chứa:
- URL đã gắn user/password.
- Query SQL chứa dữ liệu người dùng.
- Response body từ nhà cung cấp.
- Header hoặc payload gửi tới dịch vụ ngoài.
- Thông tin kết nối nội bộ.

Hãy chuẩn hóa exception message ở ranh giới ứng dụng và tránh copy message nguyên bản vào custom span attribute. Nếu log stack trace đầy đủ, cần xem log backend là nơi có thể lưu dữ liệu nhạy cảm và áp dụng cùng chính sách quyền truy cập/retention như trace backend.

## 9. Dùng ObservationConvention và ObservationFilter

`ObservationConvention` quyết định observation name và các key-value được thêm vào context. Đây là nơi tốt để định nghĩa một allowlist thuộc tính có ích cho vận hành:
- Module identifier.
- Invocation type.
- Dependency name đã chuẩn hóa.
- Operation name.
- Kết quả kỹ thuật có tập giá trị hữu hạn.

Không lấy trực tiếp toàn bộ request parameters, headers hoặc domain object rồi biến chúng thành tags.

`ObservationFilter` có thể sửa `Observation.Context` trước khi các handler xử lý trạng thái kết thúc của observation. Với custom context do ứng dụng sở hữu, có thể dùng filter để loại bỏ những key-value không được phép. Ví dụ minh họa:

```java
@Bean
ObservationFilter paymentObservationFilter() {
    return context -> {
        if (context instanceof PaymentObservationContext paymentContext) {
            // Method này do ứng dụng tự định nghĩa trên custom context.
            paymentContext.removeSensitiveValues();
        }
        return context;
    };
}
```

`PaymentObservationContext` và `removeSensitiveValues()` là ví dụ abstraction do ứng dụng định nghĩa, không phải API có sẵn của Micrometer.

Filter này chỉ xử lý context mà nó nhìn thấy. Nó không tự động scrub:
- Log message đã được ghi trước đó.
- Baggage đã được truyền sang service khác.
- HTTP header do client tự log.
- Span attribute do một instrumentation độc lập tạo ra ngoài observation context.
- Dữ liệu đã export hoặc đã lưu trong backend.

Vì vậy, hãy loại secret tại nguồn trước khi tạo observation. Dùng filter để phòng vệ bổ sung và kiểm tra raw telemetry sau khi export.

## 10. Redaction ở OpenTelemetry Collector

Khi ứng dụng export OTLP tới OpenTelemetry Collector, Collector có thể xóa hoặc biến đổi một số span attributes trước khi gửi tiếp tới backend. Đây là lớp bảo vệ bổ sung cho trường hợp instrumentation vô tình thu thập dữ liệu.

Ví dụ dùng `attributes` processor để xóa các key nhạy cảm đã biết:

```yaml
processors:
  attributes/scrub:
    actions:
      - key: http.request.header.authorization
        action: delete
      - key: http.request.header.cookie
        action: delete
      - key: db.connection_string
        action: delete
      - key: user.email
        action: delete
      - key: session.id
        action: delete

service:
  pipelines:
    traces:
      processors: [memory_limiter, attributes/scrub, batch]
    logs:
      processors: [memory_limiter, attributes/scrub, batch]
```

Đây là đoạn cấu hình minh họa phần processor và pipeline. Hãy ghép nó vào Collector configuration thực tế, bảo đảm distribution đang dùng có processor tương ứng và các processor khác cần thiết vẫn được giữ lại.

Tên attribute phụ thuộc instrumentation và semantic convention. Ví dụ `http.request.header.authorization` chỉ có tác dụng nếu attribute đó thực sự tồn tại trong dữ liệu nhận được. Hãy kiểm tra raw spans/logs ở môi trường thử nghiệm để xác định đúng key.

### 10.1. Delete, transform hay allowlist?

| Cách xử lý | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| Delete attribute | Giá trị không cần cho điều tra | Lựa chọn ưu tiên với secret |
| Mask/redact | Chỉ cần biết field đã tồn tại | Không giữ prefix/suffix có thể giúp khôi phục secret |
| Transform | Cần giảm độ chi tiết của dữ liệu | Phải kiểm tra kết quả và nguy cơ đảo ngược |
| Allowlist | Muốn chỉ cho phép một số attribute đã biết | Cần cập nhật khi instrumentation thêm field mới |

OpenTelemetry Collector có attribute, filter, redaction và transform processors. Với dữ liệu nhạy cảm, allowlist có thể an toàn hơn denylist nếu tổ chức kiểm soát được danh sách field được phép. Cần xác minh processor được chọn hỗ trợ đúng signal và phiên bản Collector đang triển khai.

### 10.2. Không coi hashing là ẩn danh mặc định

Hash một email, số điện thoại hoặc ID không tự động làm dữ liệu trở nên vô danh. Nếu không gian giá trị nhỏ hoặc dễ đoán, attacker có thể thử hash các giá trị khả dĩ để đối chiếu. Với secret xác thực, không hash rồi giữ lại trong span; hãy xóa hẳn.

Nếu cần phân tích nhóm người dùng, hãy dùng category hoặc aggregation đã được phê duyệt thay vì định danh thô.
## 11. Bảo vệ Actuator và endpoint observability

Actuator endpoints có thể tiết lộ cấu hình, package, bean, dependency và trạng thái vận hành. Không expose mọi endpoint chỉ để tiện debug.

Ví dụ allowlist endpoint cần thiết:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus,modulith"
  endpoint:
    health:
      show-details: when-authorized
      roles: OPS
```

Chọn danh sách endpoint theo nhu cầu thực tế. Không thêm `env`, `configprops`, `beans`, `heapdump` hoặc `threaddump` vào public surface nếu chưa đánh giá rõ thông tin chúng có thể tiết lộ.

Cần phân biệt hai việc:
- **Exposure:** endpoint có được ánh xạ ra HTTP/JMX hay không.
- **Authorization:** ai được phép gọi endpoint đã expose.

Exposure allowlist không thay thế authentication hoặc network policy. Hãy:
- Đặt management interface trong mạng quản trị hoặc private network.
- Dùng Spring Security để giới hạn quyền theo role.
- Dùng TLS; nếu telemetry/management đi qua mạng giữa các trust boundary, cân nhắc mTLS.
- Giới hạn quyền xem health details và module structure.
- Không đưa credential vào query string hoặc URL của management endpoint.
- Kiểm tra custom `SecurityFilterChain` vì khi ứng dụng tự khai báo filter chain, cấu hình bảo vệ Actuator mặc định có thể không còn áp dụng như mong đợi.

## 12. Bảo vệ đường export và backend telemetry

Trace backend và log backend là kho dữ liệu vận hành có thể chứa thông tin nhạy cảm. Hãy áp dụng các biện pháp sau:

| Lớp | Kiểm soát |
| --- | --- |
| Ứng dụng | Chỉ tạo attribute an toàn; không log header/body nhạy cảm |
| Exporter | Dùng endpoint tin cậy, TLS và credential quản lý qua secret store |
| Collector | Redact/delete attribute nhạy cảm trước khi export |
| Backend | RBAC, SSO, audit access, tenant isolation |
| Dashboard | Giới hạn quyền theo service, môi trường và nhóm trực vận hành |
| Storage | Encryption at rest, retention và chính sách backup |
| Vận hành | Audit truy cập, cập nhật credential và kiểm tra cấu hình định kỳ |

Không nhúng OTLP token, backend password hoặc API key vào source code, span attribute, command line có thể bị lưu trong process listing hoặc log khởi động. Dùng secret manager, workload identity hoặc cơ chế credential injection được nền tảng hỗ trợ.

Sampling không phải biện pháp bảo vệ secret. Trace được sample vẫn có thể chứa toàn bộ attribute nhạy cảm đã được ghi. Retention ngắn cũng không làm cho việc thu thập secret trở nên an toàn.

## 13. Kiểm thử để phát hiện secret bị rò rỉ

Chỉ review code là chưa đủ. Một instrumentation library có thể thêm attributes mà application code không trực tiếp khai báo. Hãy kiểm thử dữ liệu thực tế được export.

### 13.1. Dùng sentinel value trong môi trường test

Tạo một chuỗi giả lập dễ tìm, ví dụ:

```text
TEST_SECRET_DO_NOT_EXPORT_7F3A
```

Không dùng secret production thật trong test. Đưa sentinel vào các vị trí dễ bị thu thập:
- Authorization header của request test.
- Cookie/session field giả.
- Fake connection string.
- Exception message do mock dependency tạo ra.
- Request body chứa field nhạy cảm giả lập.

Gọi endpoint hoặc nghiệp vụ tạo trace, log và metrics. Sau đó kiểm tra:
1. Raw span attributes trước khi gửi.
2. OTLP payload hoặc Collector debug output trong môi trường test.
3. Trace backend sau khi Collector xử lý.
4. Log output và MDC.
5. Metrics exposition và label values.
6. Outbound headers nếu baggage được bật.

Assertion chính là sentinel không xuất hiện trong bất kỳ signal hoặc export destination nào. Nếu test dùng collector, kiểm tra cả dữ liệu trước và sau processor để chứng minh redaction đang chạy đúng.

### 13.2. Kiểm thử allowlist

Ngoài việc xác nhận secret vắng mặt, cần xác nhận metadata hữu ích vẫn còn:

| Dữ liệu | Kỳ vọng |
| --- | --- |
| `module.identifier=payment` | Vẫn có |
| `module.invocation-type=bean` | Vẫn có |
| `payment.outcome=timeout` | Vẫn có |
| `Authorization header` | Không xuất hiện |
| `session.id` | Không xuất hiện |
| `db.connection_string` | Không xuất hiện |
| `customer.email` | Không xuất hiện nếu chưa được phê duyệt rõ ràng |

Một bộ lọc xóa quá rộng có thể làm mất trace context hoặc metadata cần điều tra. Hãy kiểm tra cả điều kiện **secret bị loại bỏ** và **metadata vận hành cần thiết được giữ lại**.

### 13.3. Kiểm thử thay đổi instrumentation

Khi nâng cấp Spring Boot, Spring Modulith, Micrometer, OpenTelemetry agent hoặc HTTP client, hãy kiểm tra lại telemetry schema. Phiên bản mới có thể thêm attribute hoặc thay đổi tên key. Có thể duy trì một danh sách attribute được phép và so sánh output trong CI.

## 14. Nếu secret đã bị export thì xử lý thế nào?

Nếu phát hiện credential thật trong trace, metric, log hoặc baggage:

1. **Xử lý credential trước:** revoke hoặc rotate secret đã lộ theo quy trình của hệ thống. Không chỉ xóa span rồi tiếp tục dùng credential cũ.
2. **Khoanh vùng phạm vi:** xác định service, thời gian, trace ID, log stream, Collector và backend đã nhận dữ liệu.
3. **Giới hạn truy cập:** tạm thời siết quyền truy cập dashboard/backend và kiểm tra audit log.
4. **Ngăn tái diễn:** sửa instrumentation, log redaction, baggage configuration hoặc Collector processor tại nguồn phát.
5. **Xử lý bản sao đã lưu:** theo khả năng của backend, thực hiện purge/delete theo chính sách, xem cả archive và backup; không giả định xóa ở một UI sẽ xóa mọi bản sao.
6. **Kiểm thử lại:** dùng sentinel giả để chứng minh secret không còn xuất hiện trong các signal.
7. **Ghi nhận sự cố:** lưu loại dữ liệu, phạm vi ảnh hưởng và hành động khắc phục, nhưng không sao chép lại secret vào ticket hoặc báo cáo.

Nếu dữ liệu đã được gửi tới nhiều backend, mỗi bản sao cần được đánh giá riêng. Collector redaction chỉ tác động lên dữ liệu đi qua pipeline sau khi cấu hình có hiệu lực; nó không tự sửa dữ liệu đã lưu trước đó.
## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Token xuất hiện trong trace | HTTP instrumentation hoặc custom observation thu thập header | Kiểm tra raw span attributes và instrumentation config |
| Token không có trong span nhưng có trong log | Request logging hoặc exception message chứa header | Kiểm tra log pattern, request logger và MDC |
| Baggage xuất hiện trong outbound request | Field nằm trong `remote-fields` | Kiểm tra `management.tracing.baggage.remote-fields` và outbound headers |
| Baggage xuất hiện trong span | Field nằm trong `tag-fields` | Kiểm tra `management.tracing.baggage.tag-fields` |
| Baggage xuất hiện trong log | Field nằm trong `correlation.fields` | Kiểm tra MDC và log encoder |
| Collector đã cấu hình delete nhưng attribute vẫn còn | Sai key, sai signal hoặc processor chưa được gắn vào pipeline | Kiểm tra raw input, pipeline processors và Collector distribution |
| Attribute bị xóa nhưng vẫn thấy trong backend | Backend còn dữ liệu cũ hoặc một đường export khác chưa được lọc | Kiểm tra timestamp, exporter và các bản sao lưu |
| Metrics có secret dưới dạng label | Secret được thêm thành low-cardinality key hoặc custom meter tag | Kiểm tra MeterRegistry output và ObservationConvention |
| Trace vẫn có secret dù key là high-cardinality | High-cardinality chỉ không vào metrics, vẫn được lưu trong trace | Xóa key ở nguồn và kiểm tra span export |
| Actuator endpoint truy cập được từ Internet | Exposure quá rộng hoặc thiếu security/network policy | Kiểm tra exposure include/exclude, SecurityFilterChain và ingress |
| Health details tiết lộ thông tin nội bộ | Cấu hình `show-details` quá rộng | Chuyển sang `when-authorized`, cấu hình role và kiểm tra response |

### Thứ tự debug đề xuất

1. Tìm nguồn đầu tiên tạo ra giá trị nhạy cảm: request, exception, custom Observation, baggage hoặc logger.
2. Kiểm tra raw observation/span trước Collector.
3. Kiểm tra Collector nhận đúng key và đúng pipeline.
4. Kiểm tra backend có dữ liệu mới sau thời điểm cấu hình redaction.
5. Kiểm tra log, metrics, baggage và outbound request riêng biệt.
6. Rotate credential nếu giá trị thật đã bị export.

## 16. Bài tập thực hành

Ứng dụng Spring Modulith có module `order` và `payment`. Request thanh toán đi qua HTTP controller, gọi payment module, sau đó gửi request tới payment gateway. Một developer thêm Authorization header vào custom span để tiện debug. Ứng dụng cũng cấu hình baggage `tenant-id` để truyền sang downstream và đưa baggage vào MDC.

**Yêu cầu**

1. Giải thích vì sao Authorization header không được đưa vào high-cardinality tag.
2. Chọn các module attributes an toàn để giữ lại trong payment span.
3. Đề xuất thay thế cho việc ghi raw Authorization header khi điều tra lỗi xác thực.
4. Nêu rủi ro khi `tenant-id` được truyền qua `remote-fields`, `correlation.fields` và `tag-fields`.
5. Thiết kế một baggage value an toàn có cardinality thấp.
6. Viết Collector attributes processor để xóa authorization, cookie và connection string.
7. Nêu cách kiểm thử bằng sentinel value để xác nhận secret không xuất hiện trong trace, metrics và logs.
8. Đề xuất các bước ứng phó nếu token thật đã được lưu trong Tempo và Loki.

**Gợi ý đáp án**

- High-cardinality key vẫn được lưu trong traces; nó chỉ không được dùng làm metric tag.
- Giữ `module.identifier`, `module.name`, `module.invocation-type`, `module.method`, dependency name đã chuẩn hóa và outcome.
- Ghi authentication result, credential type hoặc error category đã chuẩn hóa; không ghi token.
- `tenant-id` có thể bị truyền qua HTTP headers, thêm vào MDC và xuất thành span tag; cần xem xét liệu nó có nhận dạng tenant hoặc tiết lộ quan hệ khách hàng không.
- Dùng phân loại như `tenant-tier=standard` hoặc `tenant-tier=premium` nếu phù hợp với mục đích và chính sách dữ liệu.
- Xóa các attribute nhạy cảm ở Collector và kiểm tra đúng key theo instrumentation.
- Gửi request test có sentinel giả, kiểm tra raw span, Collector output, backend, logs, metrics và outbound headers.
- Rotate/revoke token, khoanh vùng backend/bản sao, giới hạn quyền, purge theo khả năng, sửa nguồn phát và kiểm thử lại.

## 17. Ghi nhớ

**Secret không được xuất hiện trong metric tag, span attribute, baggage, MDC hoặc log.** Low-cardinality values đi vào metrics và traces; high-cardinality values vẫn có thể được lưu trong traces. Vì vậy cardinality không phải tiêu chí để quyết định dữ liệu có an toàn hay không.

Với Spring Modulith, hãy ưu tiên metadata kiến trúc như module identifier, module name và invocation type. Với custom Observation, chỉ thêm các giá trị đã được allowlist. Kiểm soát baggage vì nó có thể đi qua HTTP headers, MDC và span tags. Dùng Collector redaction làm lớp phòng vệ bổ sung, bảo vệ Actuator và telemetry backend bằng authentication, authorization, TLS và retention phù hợp.

Cuối cùng, kiểm thử telemetry bằng sentinel giả và xác nhận dữ liệu nhạy cảm vắng mặt trên tất cả các signal. Nếu secret thật đã bị export, rotate credential và xử lý mọi bản sao theo quy trình sự cố của tổ chức.

## Tài liệu tham khảo

1. [Spring Boot – Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Micrometer Observation, low/high cardinality, ObservationFilter và context propagation.
2. [Spring Boot – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): baggage remote fields, correlation fields và tag fields.
3. [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint exposure, access control và bảo vệ Actuator.
4. [Micrometer – Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): ObservationConvention, ObservationFilter và cách low/high cardinality values được xử lý.
5. [OpenTelemetry – Handling Sensitive Data](https://opentelemetry.io/docs/security/handling-sensitive-data/): data minimization, attribute/filter/redaction/transform processors và hạn chế của hashing.
6. [OpenTelemetry – Transforming Telemetry](https://opentelemetry.io/docs/collector/transforming-telemetry/): thêm, xóa và biến đổi telemetry attributes tại Collector.
7. [OWASP – Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu không nên ghi trực tiếp vào log, confidentiality và kiểm soát log access.
8. [Spring Modulith – Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): module observability, module entry spans và các thuộc tính module được ghi nhận.
