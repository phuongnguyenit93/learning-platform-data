# Không ghi payload nhạy cảm vào log

Trong ứng dụng Spring Boot sử dụng **Spring Modulith**, một thao tác nghiệp vụ có thể đi qua nhiều application module như `order`, `payment` và `notification`. Khi có lỗi, log giúp đội phát triển biết module nào thực hiện thao tác, loại sự kiện nào được phát và kết quả ra sao. Nhưng nếu log toàn bộ request, response hoặc event payload, hệ thống có thể vô tình lưu mật khẩu, access token, cookie, thông tin thanh toán, dữ liệu cá nhân và nội dung nghiệp vụ riêng tư.

Log thường được sao chép sang nhiều nơi: file trên máy chủ, log collector, hệ thống SIEM, nền tảng phân tích và bản sao phục vụ hỗ trợ. Vì vậy, **một dòng log chứa dữ liệu nhạy cảm có thể mở rộng phạm vi lộ lọt vượt xa request ban đầu**. Xóa dữ liệu khỏi ứng dụng không tự xóa được các bản sao đã gửi đi.

Bài thuộc chương **Logging** của học phần `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`. Học phần sử dụng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot thông qua module graph, Actuator, event metrics, tracing và context propagation. Bài này hướng dẫn thiết kế log an toàn: ghi đúng thông tin cần cho vận hành, tránh ghi payload nhạy cảm, bảo vệ dữ liệu đi qua exception và middleware, đồng thời vẫn liên kết được log với trace để điều tra sự cố.

Sau bài học, bạn có thể:

- Nhận diện các loại payload và thuộc tính không được ghi trực tiếp vào log.
- Áp dụng nguyên tắc data minimization và allowlist cho log fields.
- Viết log theo ngữ cảnh module/event thay vì serialize toàn bộ đối tượng.
- Tránh rò rỉ dữ liệu qua request logging, exception, validation errors và debug logs.
- Làm sạch dữ liệu do người dùng kiểm soát để giảm nguy cơ log injection.
- Dùng trace ID/span ID để liên kết log với trace mà không cần ghi request body.
- Kiểm thử log output để phát hiện secret hoặc dữ liệu nhạy cảm bị ghi nhầm.

> **Phạm vi ví dụ:** Spring Boot 3.5.x, SLF4J/Logback và Spring Modulith. Ví dụ minh họa cách tổ chức log trong ứng dụng; hãy áp dụng phân loại dữ liệu, retention và quyền truy cập theo chính sách của tổ chức. Không có cấu hình logging nào tự động làm mọi dữ liệu an toàn nếu code vẫn ghi payload trực tiếp.

## 1. Vì sao không ghi toàn bộ payload?

Payload là nội dung request, response, message hoặc event được truyền qua ứng dụng. Payload có thể chứa dữ liệu mà ứng dụng cần để xử lý nghiệp vụ, nhưng không có nghĩa dữ liệu đó cần xuất hiện trong log.

Ví dụ request tạo đơn hàng:

```json
{
  "customerEmail": "customer@example.com",
  "password": "Example-password",
  "paymentToken": "tok_live_example",
  "cardNumber": "4111111111111111",
  "shippingAddress": "12 Example Street",
  "items": [
    { "sku": "SKU-001", "quantity": 2 }
  ]
}
```

Ứng dụng có thể cần các trường này để xác thực, thanh toán hoặc giao hàng. Log vận hành thường chỉ cần biết:

- Thao tác nào được thực hiện?
- Module nào xử lý?
- Kết quả thành công hay thất bại?
- Lỗi thuộc nhóm nào?
- Thời điểm và trace nào liên quan?
- Có mã tham chiếu an toàn nào để tra cứu nghiệp vụ không?

Ghi toàn bộ payload tạo ra nhiều rủi ro:

1. **Lộ bí mật xác thực:** password, bearer token, API key, refresh token, session cookie hoặc private key có thể bị dùng để chiếm quyền.
2. **Lộ dữ liệu cá nhân:** email, số điện thoại, địa chỉ, giấy tờ định danh hoặc dữ liệu sức khỏe có thể bị truy cập bởi người không cần biết.
3. **Lộ dữ liệu thanh toán:** số thẻ, mã xác minh thẻ và thông tin tài khoản ngân hàng có thể kéo theo nghĩa vụ bảo vệ nghiêm ngặt.
4. **Tăng phạm vi sự cố:** log thường được gửi tới nhiều hệ thống và lưu lâu hơn dữ liệu request.
5. **Tăng chi phí:** payload lớn làm tăng dung lượng, băng thông, chỉ mục và thời gian truy vấn.
6. **Khó xử lý sự cố:** log nhiều dữ liệu không liên quan khiến thông tin cần thiết bị chìm trong noise.

**Nguyên tắc:** log phục vụ chẩn đoán, không phải bản sao lưu của request hoặc event. Hãy ghi những thuộc tính tối thiểu cần để hiểu hành động và kết quả.

## 2. Phân loại dữ liệu trước khi ghi log

Trước khi thêm một field vào log, hãy xác định field đó thuộc nhóm nào và có thật sự cần thiết không.

| Nhóm dữ liệu | Ví dụ | Cách xử lý trong log |
| --- | --- | --- |
| Bí mật xác thực | Password, access token, refresh token, API key, private key | Không ghi |
| Session và cookie | Session ID, cookie xác thực, CSRF token | Không ghi giá trị; chỉ ghi trạng thái nếu cần |
| Dữ liệu thanh toán | CVV/CVC, full PAN, PIN, payment token | Không ghi payload hoặc giá trị bí mật |
| Dữ liệu cá nhân | Email, số điện thoại, địa chỉ, ngày sinh, số định danh | Không ghi mặc định; chỉ dùng giá trị giảm thiểu đã được phê duyệt |
| Dữ liệu sức khỏe/tài chính | Hồ sơ bệnh án, số tài khoản, số dư, lịch sử giao dịch | Không ghi payload; chỉ ghi mã phân loại tối thiểu nếu được phép |
| Nội dung tự do | Ghi chú khách hàng, comment, chat, exception message | Không ghi nguyên văn |
| Metadata vận hành | Tên module, event type, outcome, error code ổn định | Thường phù hợp nếu không chứa dữ liệu nhạy cảm |
| Correlation metadata | Trace ID, span ID, request ID ngẫu nhiên | Có thể ghi theo chính sách và retention |
| Mã tham chiếu nghiệp vụ | Opaque order reference | Chỉ ghi nếu đã phân loại là an toàn và không dễ suy ra danh tính |

Một giá trị có vẻ vô hại vẫn có thể trở thành dữ liệu cá nhân khi kết hợp với dữ liệu khác. Ví dụ, mã đơn hàng có thể được tra cứu ngược ra khách hàng qua một hệ thống khác. Vì vậy, đừng mặc định mọi UUID hoặc internal ID đều an toàn.

### Những field tuyệt đối không nên ghi trực tiếp

- `Authorization` header, bearer token và API key.
- Password, password reset token, one-time password.
- Cookie, session ID, CSRF token và private key.
- CVV/CVC, PIN và dữ liệu thẻ đầy đủ.
- Request/response body có chứa thông tin cá nhân hoặc bí mật.
- URL query string có token, mã reset hoặc dữ liệu nhận dạng.
- Event payload có thông tin thanh toán, khách hàng hoặc nội dung riêng tư.
- Exception message chứa câu SQL, request body, credential hoặc dữ liệu do client gửi.

Nếu cần ghi nhận rằng một header có mặt, hãy ghi boolean như `authorizationPresent=true` hoặc trạng thái xác thực, không ghi giá trị header.

## 3. Chọn allowlist log fields thay vì ghi payload rồi che bớt

Một cách thiết kế an toàn là **allowlist**: chỉ chọn những field đã được duyệt để ghi. Cách này giúp người viết log phải suy nghĩ về mục đích của từng field.

Ví dụ, khi module `order` phát event `OrderPlaced`, log có thể ghi:

```json
{
  "event": "order.placed",
  "module": "order",
  "channel": "web",
  "outcome": "success",
  "itemCount": 2,
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Đây là ví dụ metadata đã được chọn lọc, không phải event payload. Không có email, địa chỉ giao hàng, payment token hoặc nội dung sản phẩm do người dùng nhập.

Một allowlist cho log nghiệp vụ có thể gồm:

| Field | Mục đích | Điều kiện |
| --- | --- | --- |
| `event` | Nhận diện hành động | Tên ổn định, không chứa dữ liệu động |
| `module` | Xác định module phát log | Dùng identifier kỹ thuật |
| `eventType` | Phân loại event | Tên class hoặc tên nghiệp vụ đã quy ước |
| `outcome` | Thành công/thất bại | Tập giá trị hữu hạn |
| `errorCode` | Phân nhóm lỗi | Mã lỗi đã chuẩn hóa |
| `channel` | Kênh nghiệp vụ | Enum hoặc danh mục hữu hạn |
| `itemCount` | Quy mô thao tác | Số lượng, không phải nội dung item |
| `traceId`, `spanId` | Liên kết log với trace | Không nhúng thông tin khách hàng |

Trước khi thêm field, hãy trả lời ba câu hỏi: field có cần để chẩn đoán không, có thể suy ra thông tin nhạy cảm không, và ai có quyền xem log ở tất cả hệ thống nhận dữ liệu?

### Tránh serialize toàn bộ object

Các cách sau dễ làm lộ dữ liệu:

```java
log.info("Incoming request: {}", request);
log.debug("Request payload: {}", objectMapper.writeValueAsString(request));
log.info("Event published: {}", event);
log.debug("Order details: {}", order);
```

Ngay cả khi object không có phương thức `toString()` tùy chỉnh, việc serialize có thể đưa toàn bộ field ra log. Nếu class được mở rộng trong tương lai và có thêm token hoặc dữ liệu cá nhân, dòng log cũ có thể vô tình bắt đầu ghi field mới.

`@JsonIgnore` hoặc annotation tương tự cũng không phải hàng rào bảo vệ chung cho log: `toString()`, debugger, custom serializer hoặc log statement khác có thể bỏ qua annotation đó. Cách an toàn hơn là không truyền payload vào logger.

## 4. Viết log an toàn bằng SLF4J trong module

Ví dụ service xử lý đơn hàng chỉ ghi metadata đã được duyệt:

```java
package com.example.shop.order;

import java.util.Locale;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
class OrderApplicationService {

    private static final Logger log =
        LoggerFactory.getLogger(OrderApplicationService.class);

    void place(PlaceOrder command) {
        String channel = command.channel().name().toLowerCase(Locale.ROOT);

        log.info(
            "Order placement started module={} eventType={} channel={}",
            "order",
            "OrderPlaced",
            channel
        );

        try {
            // Thực hiện xác thực, giữ hàng và thanh toán.
            // Không ghi command, request body hoặc payment data.

            log.info(
                "Order placement completed module={} eventType={} channel={} outcome={}",
                "order",
                "OrderPlaced",
                channel,
                "success"
            );
        } catch (PaymentRejectedException ex) {
            log.warn(
                "Order placement failed module={} eventType={} channel={} errorCode={} outcome={}",
                "order",
                "OrderPlaced",
                channel,
                ex.safeCode(),
                "failure"
            );
            throw ex;
        }
    }
}
```

Các kiểu `PlaceOrder` và `PaymentRejectedException` là kiểu nghiệp vụ giả định của ví dụ. `safeCode()` phải trả về mã lỗi ổn định, không phải message tùy ý do upstream/client gửi.

Một số nguyên tắc:

- Dùng placeholder của SLF4J để ghi field có cấu trúc và tránh nối chuỗi không cần thiết.
- Ghi tên module và loại event ổn định.
- Dùng enum hoặc mã kết quả có tập giá trị hữu hạn.
- Không ghi đối tượng `command`, request DTO, entity hoặc event payload.
- Không ghi giá trị token để “dễ debug”.
- Không ghi raw exception message nếu message có thể chứa dữ liệu nhạy cảm.

**Parameterized logging không tự làm sạch dữ liệu.** Dòng `log.info("token={}", token)` vẫn ghi token nguyên vẹn. Placeholder chỉ giúp format và hiệu năng; quyết định dữ liệu nào được phép ghi vẫn thuộc về người viết code.

### Ghi mã tham chiếu khi thật sự cần

Nếu đội hỗ trợ cần liên hệ log với bản ghi nghiệp vụ, hãy dùng một opaque reference được thiết kế cho mục đích đó và được phê duyệt. Có thể dùng mã tham chiếu ngẫu nhiên hoặc giá trị giả danh hóa bằng HMAC với secret quản lý riêng. Không dùng hash không khóa của email/số điện thoại như giải pháp ẩn danh: không gian giá trị có thể đoán được và dễ bị dò từ điển.

Nếu không cần tra cứu theo từng đơn hàng, trace ID thường đã đủ để tìm đúng lần thực thi trong hệ thống tracing.

## 5. Không ghi request/response body, headers và query string

Rò rỉ payload thường xuất hiện ở lớp web hơn là trong service nghiệp vụ.

### Spring MVC và CommonsRequestLoggingFilter

Spring Framework có `CommonsRequestLoggingFilter`, một filter có thể ghi thông tin request như query string, client information, headers và payload tùy cấu hình. Nếu bật payload logging, filter có thể ghi nội dung body đã đọc được. Không bật các tùy chọn này trên request có dữ liệu nhạy cảm.

Ví dụ cấu hình tường minh cho mục đích logging metadata tối thiểu:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.filter.CommonsRequestLoggingFilter;

@Configuration(proxyBeanMethods = false)
class RequestLoggingConfiguration {

    @Bean
    CommonsRequestLoggingFilter requestLoggingFilter() {
        CommonsRequestLoggingFilter filter =
            new CommonsRequestLoggingFilter();

        filter.setIncludeQueryString(false);
        filter.setIncludeHeaders(false);
        filter.setIncludePayload(false);
        filter.setIncludeClientInfo(false);

        return filter;
    }
}
```

Nếu ứng dụng cần request log, hãy dùng một filter riêng chỉ ghi method, route template, status, duration và trace ID theo chính sách. Đừng bật `includePayload` chỉ để tìm lỗi ở staging; hãy tái hiện với dữ liệu giả lập và log metadata có kiểm soát.

### Query string cũng có thể chứa bí mật

URL như `/reset-password?token=...` hoặc `/oauth/callback?code=...` có thể chứa credential tạm thời. Ghi full URL hoặc query string có thể làm lộ token trong access log, reverse proxy, APM và exception.

Nên ghi **route template** như `/orders/{orderId}` thay vì URL thực tế chứa giá trị động. Nếu cần phân biệt endpoint, dùng route name hoặc handler mapping đã chuẩn hóa.

### Headers và cookies

Không log toàn bộ headers. Một số headers thường nhạy cảm:

- `Authorization`.
- `Cookie` và `Set-Cookie`.
- `X-Api-Key` hoặc header API key riêng của hệ thống.
- Header chứa session, CSRF hoặc signed URL.
- Header do client kiểm soát có thể chứa dữ liệu tùy ý.

Nếu cần debug header, dùng allowlist cho những header đã được phân loại an toàn. Không lấy toàn bộ header map rồi chỉ cố che vài tên đã biết; header mới có thể được thêm sau này.

### WebFlux và Reactor Netty

Trong WebFlux, cấu hình wiretap hoặc custom WebClient/Netty logging có thể ghi request/response details. Kiểm tra mức độ chi tiết của logger và handler trước khi bật debug. Không bật body-level wiretap trên dữ liệu thật. Nếu cần tái hiện lỗi, dùng payload giả lập và môi trường cô lập.

## 6. Không để exception và validation errors làm lộ payload

Một exception có thể chứa dữ liệu nhạy cảm trong message:

```text
Payment declined for card 4111111111111111, token=tok_live_example
```

Nếu ghi:

```java
log.error("Payment failed", exception);
```

Logback có thể ghi cả exception message và stack trace. Vì vậy, việc không ghi request body trực tiếp vẫn chưa đủ nếu thư viện hoặc exception tự nhúng payload vào message.

### Ghi mã lỗi đã chuẩn hóa

```java
catch (PaymentGatewayException ex) {
    log.error(
        "Payment failed module={} errorCode={} outcome={} traceId={}",
        "payment",
        mapToSafeErrorCode(ex),
        "failure",
        currentTraceId()
    );
    throw ex;
}
```

`mapToSafeErrorCode(ex)` nên ánh xạ lỗi sang tập mã cố định như `gateway_timeout`, `payment_declined` hoặc `provider_unavailable`. `currentTraceId()` là helper minh họa; trong Spring Boot có thể dùng correlation fields do Micrometer Tracing đưa vào MDC nếu cấu hình logging tương ứng.

Nếu cần stack trace để điều tra, chỉ ghi exception đã được xác định không mang payload nhạy cảm hoặc dùng cơ chế báo lỗi nội bộ có kiểm soát. Không tự động log mọi throwable từ thư viện ngoài mà chưa biết message có thể chứa gì.

### Validation error và rejected value

Spring MVC validation có thể cung cấp `FieldError.getRejectedValue()`. Giá trị này là dữ liệu do client gửi, có thể là password, email hoặc nội dung riêng tư.

Không nên log:

```java
log.warn("Invalid field value: {}", fieldError.getRejectedValue());
```

Thay vào đó, log tên field đã được allowlist, mã lỗi validation và route template:

```java
log.warn(
    "Request validation failed route={} field={} errorCode={}",
    "/orders",
    safeFieldName(fieldError.getField()),
    "invalid_format"
);
```

Nếu tên field có thể được tạo động, hãy kiểm soát bằng danh sách field được phép hoặc chuẩn hóa. Không ghi rejected value.

### Không để SQL và downstream error chứa dữ liệu

Exception từ ORM, JDBC hoặc HTTP client có thể chứa câu SQL, bind parameter, URL, request headers hoặc response body. Cần kiểm tra logger của thư viện, mức DEBUG/TRACE và các error handler. Một exception được ghi ở nhiều lớp có thể làm payload xuất hiện dù lớp nghiệp vụ đã tránh log.

## 7. Tránh log injection từ dữ liệu do người dùng kiểm soát

Log injection xảy ra khi dữ liệu đầu vào chứa ký tự điều khiển như newline hoặc carriage return, khiến một giá trị được hiển thị thành nhiều dòng log hoặc làm giả một log entry khác.

Ví dụ input:

```text
guest
2026-11-27 ERROR Authentication succeeded for admin
```

Nếu nối nguyên văn input vào message, một log viewer dạng dòng có thể hiển thị dòng thứ hai như một sự kiện riêng.

SLF4J placeholders giúp giữ message template cố định, nhưng **parameterized logging tự nó không ngăn CR/LF injection**. Khi ghi dữ liệu do client kiểm soát, vẫn cần structured encoder escape giá trị đúng định dạng, giới hạn độ dài và ưu tiên phân loại/chuẩn hóa trước khi ghi.

Ưu tiên **không log raw input**. Nếu một trường không nhạy cảm và thật sự cần ghi, hãy:

- Chuẩn hóa hoặc escape CR, LF và ký tự điều khiển.
- Giới hạn độ dài.
- Dùng structured logging/JSON encoder đúng chuẩn thay vì tự nối chuỗi.
- Ghi giá trị phân loại hoặc trạng thái đã chuẩn hóa khi có thể.
- Không cho phép client tự quyết định tên logger, log level hoặc cấu trúc log.

Hàm minh họa cho một giá trị văn bản đã được xác định là không nhạy cảm:

```java
static String sanitizeLogValue(String value) {
    if (value == null) {
        return "null";
    }

    String sanitized = value
        .replace('\r', ' ')
        .replace('\n', ' ')
        .replace('\t', ' ');

    // Giới hạn chiều dài để tránh log flooding.
    return sanitized.length() > 80
        ? sanitized.substring(0, 80)
        : sanitized;
}
```

Hàm này chỉ giảm nguy cơ chèn dòng và log flooding. Nó **không** che password, token, email hoặc dữ liệu nhạy cảm; không dùng nó làm lý do để ghi raw payload.

Structured JSON logging cũng không tự động bảo vệ dữ liệu. JSON encoder giúp escape ký tự theo định dạng, nhưng nếu field `password` vẫn được đưa vào event thì secret vẫn nằm trong JSON output.

## 8. Log correlation với trace mà không cần payload

Trong ứng dụng Spring Boot có Micrometer Tracing, log có thể được bổ sung `traceId` và `spanId` trong MDC. Khi log được cấu hình correlation fields, người vận hành có thể tìm trace tương ứng trong tracing backend mà không phải ghi request body.

Một dòng log minh họa:

```text
2026-11-27 10:15:21 INFO
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=00f067aa0ba902b7
module=order event=OrderPlaced outcome=success channel=web
```

Khi dùng Spring Boot và Micrometer Tracing với logging pattern mặc định tương ứng, correlation ID thường được đưa vào log pattern. Nếu tự thay logging pattern, cần giữ các field correlation phù hợp.

Ví dụ pattern console có thể tham chiếu MDC:

```yaml
logging:
  pattern:
    correlation: "[${spring.application.name:},%X{traceId:-},%X{spanId:-}] "
  include-application-name: false
```

Property `logging.pattern.correlation` cho phép tùy chỉnh correlation ID và được Spring Boot 3.5 hỗ trợ. Vì tên ứng dụng đã được thêm vào correlation pattern, `include-application-name: false` tránh lặp tên ứng dụng ở phần prefix mặc định. Nếu không cần đổi định dạng, có thể giữ correlation ID mặc định mà Spring Boot/Micrometer Tracing đã thêm vào log. Hãy đối chiếu logging pattern hiện tại trước khi thay thế cấu hình.

### Không nhét payload vào baggage hoặc span attributes

Tránh chuyển password, token, email, full request URL hoặc toàn bộ event object sang tracing baggage/span attributes với ý định “không ghi log thì ghi trace”. Traces cũng được export và lưu ở hệ thống khác, có thể có phạm vi truy cập rộng.

Chỉ thêm thuộc tính low-cardinality phù hợp để nhóm traces, ví dụ `module=order`, `channel=web`, `outcome=success`. High-cardinality attribute nếu cần phải được phê duyệt, giảm thiểu và không chứa bí mật. Trace ID là correlation identifier, không phải chỗ lưu dữ liệu nghiệp vụ.

### Kết hợp với Spring Modulith

Với event liên module, có thể ghi log metadata ở publisher và listener:

```text
module=order eventType=OrderPlaced action=published outcome=success
module=notification eventType=OrderPlaced action=handled outcome=success
```

Hai dòng log cho biết module nào phát và module nào xử lý. Nếu có cùng trace context, trace ID giúp tìm chúng trong một trace; nếu listener chạy bất đồng bộ và dùng trace mới, event correlation ID đã được phê duyệt có thể hỗ trợ liên kết. Không cần log toàn bộ payload `OrderPlaced`.

## 9. Redaction là lớp bảo vệ bổ sung, không phải lý do để log payload

Redaction/masking có thể thay thế một phần dữ liệu trước khi xuất log:

```text
Authorization: Bearer [REDACTED]
email: c***@example.com
cardNumber: ************1111
```

Nhưng **redaction không thay thế data minimization**. Nếu hệ thống log toàn bộ object rồi cố tìm và che tất cả trường nhạy cảm, một field mới hoặc một nested object chưa được xử lý có thể lọt qua.

Một chiến lược nhiều lớp:

1. Không truyền payload vào logger.
2. Xây dựng allowlist field tại code nghiệp vụ.
3. Dùng bộ lọc/redaction tập trung cho một số key nhạy cảm đã biết như defense-in-depth.
4. Hạn chế debug/trace logging trong production.
5. Kiểm soát log access, export, retention và xóa theo chính sách.
6. Kiểm tra log ở cả ứng dụng, reverse proxy, gateway, collector và tracing backend.

Không dựa hoàn toàn vào regex để che secret. Token có nhiều định dạng, payload có thể lồng nhau, encoding khác nhau và dữ liệu có thể xuất hiện trong exception message hoặc stack trace. Bộ lọc có thể giúp giảm rủi ro nhưng không thể chứng minh mọi đường ghi log đều đã được bảo vệ.

### Khi bắt buộc phải hiển thị một phần dữ liệu

Một số nghiệp vụ có thể yêu cầu người vận hành nhận biết một đối tượng mà không thấy giá trị đầy đủ. Hãy dùng phương pháp đã được tổ chức phê duyệt, ví dụ opaque reference hoặc tokenized identifier. Với dữ liệu có thể suy ngược bằng từ điển (email/số điện thoại), hash không khóa không phải ẩn danh an toàn.

Không tự xây dựng quy tắc mask cho dữ liệu thanh toán hoặc định danh nếu tổ chức đã có thư viện/chính sách chuẩn. Hãy tái sử dụng cơ chế đã được kiểm duyệt.

## 10. Cấu hình và vận hành logging an toàn

Một cấu hình log production nên ưu tiên mức log phù hợp và tránh bật debug payload ở các package web/client.

Ví dụ cấu hình nền:

```yaml
logging:
  level:
    root: INFO
    com.example.shop: INFO
    org.springframework.web: INFO
```

Các package và level cần điều chỉnh theo ứng dụng. Khi điều tra sự cố, nếu tạm bật DEBUG/TRACE, hãy giới hạn phạm vi package, thời gian, request test và bảo đảm không ghi body/header nhạy cảm.

Một số điểm vận hành:

| Khu vực | Điều cần kiểm soát |
| --- | --- |
| Application logger | Không log DTO, entity, event payload hoặc secret |
| HTTP access log | Không ghi query string nhạy cảm, authorization, cookie hoặc body |
| Reverse proxy/API gateway | Mask hoặc loại bỏ headers/query fields nhạy cảm |
| HTTP client logger | Không dump request/response headers và body trong production |
| ORM/JDBC logger | Không bật bind parameter logging với dữ liệu thật nếu chưa đánh giá |
| Exception handler | Không trả hoặc log raw message chứa payload |
| Trace exporter | Không thêm PII/secret vào span attributes/baggage |
| Log collector/SIEM | TLS, authentication, RBAC, retention và audit |
| Backup/archive | Cùng chính sách bảo vệ và thời hạn như log gốc |

### Log retention và quyền truy cập

Log thường được giữ để điều tra sự cố, phát hiện xâm nhập và kiểm toán. Cần xác định:

- Nhóm nào được đọc log production?
- Ai có quyền tìm kiếm hoặc export log?
- Log giữ bao lâu và khi hết hạn sẽ xóa thế nào?
- Log có được sao chép sang môi trường hỗ trợ/dev không?
- Dữ liệu log có được mã hóa khi truyền và khi lưu?
- Có audit trail cho việc truy cập dữ liệu nhạy cảm không?

Không đưa log production có dữ liệu khách hàng vào issue tracker, chat hoặc môi trường dev. Khi cần chia sẻ, tạo bản trích xuất đã giảm thiểu và được phê duyệt.

## 11. Kiểm thử để bảo đảm secret không xuất hiện trong log

Quy tắc “đừng log payload” cần được kiểm chứng bằng test. Một cách là dùng Logback `ListAppender` để thu các log event phát sinh từ service, sau đó tìm các canary secret giả lập.

Ví dụ test minh họa:

```java
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import static org.junit.jupiter.api.Assertions.*;

class OrderLoggingTest {

    @Test
    void doesNotWriteSensitivePayloadToLog() {
        Logger logger = (Logger) LoggerFactory.getLogger(
            OrderApplicationService.class
        );

        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);

        try {
            // Dùng secret giả lập, không dùng credential thật trong test.
            PlaceOrder command = new PlaceOrder(
                "WEB",
                "CANARY_PASSWORD_123",
                "CANARY_TOKEN_456"
            );

            new OrderApplicationService().place(command);

            String output = appender.list.stream()
                .map(ILoggingEvent::getFormattedMessage)
                .reduce("", (left, right) -> left + "\n" + right);

            assertFalse(output.contains("CANARY_PASSWORD_123"));
            assertFalse(output.contains("CANARY_TOKEN_456"));
            assertTrue(output.contains("OrderPlaced"));
        } finally {
            logger.detachAppender(appender);
            appender.stop();
        }
    }
}
```

Đây là **mã khung kiểm thử**: constructor, kiểu `PlaceOrder`, dependency của service và cách gọi `place(...)` cần điều chỉnh theo ứng dụng thật. Test cần dependency Logback classic ở test runtime. Nếu logger ghi throwable, structured arguments hoặc JSON encoder, hãy kiểm tra cả nội dung throwable/encoded output, không chỉ `getFormattedMessage()`.

### Kiểm tra nhiều lớp logging

Một bài test service không phát hiện được mọi đường rò rỉ. Nên có thêm:

- Integration test cho HTTP request/response logging với canary trong header, query và body.
- Test exception handler để xác nhận rejected value và raw exception message không xuất hiện.
- Test event listener để xác nhận payload nhạy cảm không được serialize.
- Test appender/JSON encoder để rà soát field thực sự được xuất.
- Static search hoặc code review rule để tìm các mẫu nguy hiểm như `log.info("{}", request)`, `writeValueAsString(event)` và log toàn bộ headers.

Có thể dùng canary string như `CANARY_TOKEN_456` trong test fixture; không bao giờ đưa secret thật vào test hoặc CI logs.

## 12. Bài thực hành: bảo vệ log cho luồng đặt hàng

**Bối cảnh:** ứng dụng Spring Modulith có module `order`, `payment` và `notification`. Request đặt hàng chứa email, địa chỉ, token thanh toán; event `OrderPlaced` có thông tin khách hàng và danh sách mặt hàng.

Thực hiện các bước:

1. **Phân loại payload:** liệt kê password, token, email, địa chỉ, payment data, order reference, channel và item count. Đánh dấu field nào không được log và field nào cần phê duyệt.
2. **Tìm log nguy hiểm:** tìm những dòng log serialize request, response, entity hoặc event; kiểm tra cả `toString()`, exception message và debug log của HTTP client.
3. **Thiết kế allowlist:** xác định log fields như `module`, `eventType`, `channel`, `outcome`, `errorCode`, `traceId`; ghi rõ mục đích và cardinality.
4. **Refactor service:** thay log payload bằng SLF4J structured/parameterized fields đã duyệt. Không ghi `command` hoặc `OrderPlaced` object.
5. **Refactor listener:** module `notification` chỉ log event type, kết quả gửi và error code. Không log email/phone hoặc toàn bộ message.
6. **Kiểm tra HTTP layer:** tắt payload/header/query logging; dùng route template thay cho full URL.
7. **Kiểm tra lỗi:** tạo validation failure và payment failure với canary secret; bảo đảm exception/stack trace không làm lộ giá trị.
8. **Liên kết trace:** xác nhận log có trace ID/span ID theo cấu hình, tìm trace tương ứng trong backend mà không cần ghi payload.
9. **Viết test:** dùng ListAppender hoặc test appender của dự án để assert các canary không xuất hiện trong log output.
10. **Review vận hành:** xác định retention, RBAC, TLS, nơi log được export và quy trình chia sẻ log khi hỗ trợ.

**Tiêu chí hoàn thành:** luồng nghiệp vụ vẫn có đủ log để biết module, event, outcome và lỗi đã chuẩn hóa; không có payload nhạy cảm trong log; trace correlation hoạt động; và test có thể phát hiện khi một thay đổi code vô tình ghi lại secret.

## Tài liệu tham khảo

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu không nên ghi, kiểm soát log injection, bảo vệ và lưu giữ log.
- [OWASP Logging Vocabulary Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Vocabulary_Cheat_Sheet.html): thuật ngữ và cách phân loại sự kiện log.
- [Spring Boot 3.5 — Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html): cấu hình logging, log levels, patterns và structured logging.
- [Spring Framework — CommonsRequestLoggingFilter API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/CommonsRequestLoggingFilter.html): các tùy chọn ghi query string, headers, payload và client info.
- [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html): Micrometer Tracing, correlation IDs và log correlation.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): observation context và metadata phục vụ metrics/tracing.

**Ghi nhớ:** log chỉ nên chứa dữ liệu tối thiểu cần để vận hành và điều tra. Hãy chọn field theo allowlist, tránh serialize payload, kiểm soát exception/request logging và dùng trace ID để liên kết các bước xử lý. Redaction, structured logging và kiểm thử là các lớp bảo vệ bổ sung cho nguyên tắc không ghi dữ liệu nhạy cảm ngay từ đầu.
