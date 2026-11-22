# Dữ liệu nhạy cảm, context của request và nội dung nên ghi log

Logging giúp trả lời những câu hỏi quan trọng khi vận hành ứng dụng Spring Boot: request nào gặp lỗi, thành phần nào đã xử lý nó, lỗi bắt đầu ở bước nào, mất bao lâu và điều kiện nào khiến hệ thống không hoạt động đúng. Tuy nhiên, log cũng có thể trở thành một nguồn rò rỉ thông tin nếu ứng dụng ghi nguyên HTTP headers, request body, access token, mật khẩu, dữ liệu khách hàng hoặc exception chứa thông tin bí mật.

Một hệ thống logging tốt cần cân bằng ba mục tiêu:

1. **Có đủ ngữ cảnh để chẩn đoán** mà không phải tái hiện mọi lỗi trong production.
2. **Giảm tối đa dữ liệu nhạy cảm được lưu** trong log và các hệ thống tập trung log.
3. **Liên kết được các dòng log thuộc cùng một request hoặc một luồng xử lý** mà không cần ghi toàn bộ dữ liệu của request đó.

Trong Spring Boot, các công cụ thường gặp là SLF4J/Logback, `Logger`, MDC (*Mapped Diagnostic Context*), request/correlation ID, distributed tracing và những hệ thống thu thập log có cấu trúc. Bài này đi từ nguyên tắc chọn dữ liệu đến ví dụ Java, HTTP filter, async execution, cách ghi exception và thực hành xây dựng một chính sách log an toàn.

> Nguyên tắc xuyên suốt: **log sự kiện, trạng thái, mã kết quả và định danh tương quan cần thiết; đừng dùng log như bản sao của request, response hoặc dữ liệu nghiệp vụ.**

## 1. Log là dữ liệu vận hành, không phải kho chứa mọi thông tin

Xét request:

```text
POST /api/orders
Authorization: Bearer <access-token>
Cookie: SESSION=<session-id>
Content-Type: application/json

{
  "customerEmail": "alice@example.test",
  "deliveryAddress": "123 Example Street",
  "cardNumber": "<payment-card-data>",
  "items": [
    {"sku": "SKU-101", "quantity": 2}
  ]
}
```

Để kiểm tra vì sao việc tạo đơn hàng thất bại, một kỹ sư thường chỉ cần biết:

```text
event=order.create.failed
requestId=7d2c9e64-...
route=/api/orders
method=POST
status=503
orderRef=ord_83f1
failureCode=INVENTORY_UNAVAILABLE
durationMs=217
```

Thông tin trên giúp tìm đúng request, đúng bước lỗi và đánh giá thời gian xử lý. Nó không cần chứa access token, cookie, địa chỉ giao hàng, số thẻ hoặc toàn bộ payload.

### 1.1. Tại sao log nhạy cảm gây rủi ro?

Một dòng log có thể đi qua nhiều nơi:

```text
Spring Boot service
       |
       v
Console / log file
       |
       v
Log agent / collector
       |
       v
Centralized logging platform
       |
       +--> Dashboard / search
       +--> Alert
       +--> Export / backup
       +--> Incident attachment
```

Số người và thành phần có quyền xem log có thể khác với quyền truy cập dữ liệu nghiệp vụ. Log thường được sao chép, lưu lâu hơn và tìm kiếm rộng hơn dữ liệu trong database. Một bí mật xuất hiện trong log sẽ khó thu hồi nếu đã đi qua nhiều hệ thống.

Do đó, thiết kế log phải bắt đầu từ **quyết định được phép ghi dữ liệu gì**, không phải chỉ từ việc chọn câu lệnh `log.info(...)`.

## 2. Phân loại dữ liệu trước khi ghi

Có thể chia dữ liệu theo mục đích và mức độ rủi ro.

| Nhóm | Ví dụ | Nguyên tắc |
| --- | --- | --- |
| Thông tin vận hành | Tên sự kiện, mã lỗi, status code, thời gian xử lý, tên service | Thường nên ghi |
| Ngữ cảnh tương quan | Request ID, trace ID, span ID, operation ID | Ghi có kiểm soát, không coi là secret nhưng hạn chế lạm dụng |
| Định danh nội bộ | Order reference, job ID, account reference | Chỉ ghi khi cần, ưu tiên mã không chứa dữ liệu nhận dạng trực tiếp |
| Thông tin cá nhân | Email, số điện thoại, tên, IP, địa chỉ, thiết bị | Hạn chế; chỉ ghi khi mục đích thực sự yêu cầu |
| Dữ liệu nghiệp vụ nhạy cảm | Số tiền chi tiết, hồ sơ, thông tin giao dịch, dữ liệu sức khỏe | Tránh ghi nguyên giá trị; cần đánh giá riêng |
| Thông tin xác thực | Password, access token, refresh token, API key, cookie phiên, OTP | Không ghi giá trị |
| Khóa và bí mật hệ thống | Private key, secret môi trường, connection string có password | Không ghi giá trị |
| Dữ liệu thanh toán | Số thẻ, mã bảo mật và thông tin thanh toán nhạy cảm | Không ghi nguyên dữ liệu |

Phân loại thực tế phụ thuộc sản phẩm, chính sách nội bộ và quy định áp dụng. Bảng trên là điểm khởi đầu cho một chính sách logging an toàn trong ứng dụng Spring Boot.

### 2.1. Dữ liệu cá nhân không chỉ là tên và email

Các giá trị sau có thể nhận diện hoặc liên kết tới một cá nhân trong một số ngữ cảnh:

- Địa chỉ IP và địa chỉ thiết bị.
- Account ID hoặc customer ID nếu kết nối được với hồ sơ.
- Đường dẫn URL có định danh cá nhân.
- User-Agent khi kết hợp với dữ liệu khác.
- Trace ID hoặc request ID nếu có thể liên kết sang dữ liệu người dùng.
- Nội dung người dùng nhập trong ô tìm kiếm.

Vì vậy, “không log password” mới là điều kiện cần, chưa đủ. Cần đánh giá cả **định danh gián tiếp và khả năng liên kết dữ liệu**.

### 2.2. Quy tắc không ghi bí mật

Không ghi:

```java
log.info("Login password: {}", password);
log.debug("Authorization: {}", authorizationHeader);
log.info("Session cookie: {}", sessionCookie);
log.error("API key used: {}", apiKey);
```

Thay bằng các sự kiện:

```java
log.info(
        "auth.login.succeeded authMethod={} requestId={}",
        authMethod,
        requestId
);
```

```java
log.warn(
        "auth.login.failed failureCode={} requestId={}",
        "INVALID_CREDENTIALS",
        requestId
);
```

Nếu cần biết vì sao đăng nhập thất bại, sử dụng **mã nguyên nhân đã chuẩn hóa** thay vì ghi giá trị người dùng nhập.

### 2.3. Đừng cho rằng dữ liệu được mask một phần luôn vô hại

Ví dụ:

```text
email=a***@example.test
phone=***1234
```

đã ít dữ liệu hơn bản đầy đủ, nhưng vẫn có thể mang tính cá nhân hoặc cho phép suy đoán khi kết hợp với các nguồn khác.

Nếu không cần đối chiếu email hoặc điện thoại, tốt nhất **không ghi cả giá trị đã mask**.

## 3. Chọn dữ liệu log theo câu hỏi vận hành

Một dòng log hữu ích nên giúp trả lời ít nhất một câu hỏi:

- Hành động nào vừa xảy ra?
- Thành phần nào thực hiện?
- Kết quả thành công hay thất bại?
- Mã lỗi có ý nghĩa vận hành là gì?
- Lỗi thuộc request/job/trace nào?
- Phụ thuộc bên ngoài nào gặp sự cố?
- Thời gian xử lý là bao nhiêu?
- Có cần một hành động khắc phục cụ thể không?

Nếu một field không giúp trả lời các câu hỏi này, hãy cân nhắc bỏ nó.

### 3.1. Các trường nên cân nhắc

| Field | Ví dụ | Giá trị |
| --- | --- | --- |
| `timestamp` | Thời gian theo UTC | Xác định trình tự |
| `level` | INFO, WARN, ERROR | Độ nghiêm trọng |
| `service` | `order-api` | Tên ứng dụng |
| `environment` | `staging` | Môi trường chạy |
| `event` | `order.submit.failed` | Loại sự kiện ổn định |
| `requestId` | UUID được server cấp | Liên kết log cùng request |
| `traceId`, `spanId` | ID từ tracing system | Liên kết giữa các service |
| `route` | `/api/orders/{id}` | Endpoint mẫu, tránh giá trị path động |
| `method` | POST | Phương thức HTTP |
| `status` | 503 | Kết quả HTTP |
| `durationMs` | 217 | Thời gian xử lý |
| `failureCode` | `DEPENDENCY_TIMEOUT` | Phân nhóm lỗi |
| `dependency` | `inventory-service` | Thành phần bị ảnh hưởng |
| `operationRef` | Mã thao tác nội bộ | Đối chiếu tác vụ |

Không phải mọi dòng log đều phải chứa tất cả các field. Ghi đúng những gì có ý nghĩa đối với sự kiện.

### 3.2. Dùng mã lỗi ổn định thay cho nội dung tự do

Ít hữu ích:

```text
Unable to finish because Alice ordered product X and ...
```

Hữu ích hơn:

```text
event=order.submit.failed
failureCode=INVENTORY_TIMEOUT
dependency=inventory-service
durationMs=800
```

Mã lỗi ổn định giúp tìm kiếm, tổng hợp và xây dựng cảnh báo. Đừng nhúng email, số tài khoản hoặc payload vào nội dung mã lỗi.

### 3.3. Không biến log thành metric có nhãn vô hạn

Những giá trị như request ID, order ID hoặc customer ID có độ phân biệt rất cao. Chúng hữu ích cho **tra cứu log**, nhưng nếu đưa trực tiếp vào label của metrics có thể gây cardinality bùng nổ.

Ví dụ nên dùng metric label:

```text
http.requests{route="/api/orders/{id}",status="503"}
```

Thay vì:

```text
http.requests{path="/api/orders/ord_83f1",requestId="..."}
```

Log, metrics và traces có vai trò khác nhau. Không ép tất cả thông tin vào mọi hệ thống.

## 4. Log level nào phù hợp?

Spring Boot thường dùng SLF4J cùng một implementation logging như Logback. Các mức log phổ biến:

| Level | Ý nghĩa thực tế | Ví dụ |
| --- | --- | --- |
| TRACE | Chi tiết rất thấp cấp để điều tra đặc biệt | Các bước nội bộ không nhạy cảm |
| DEBUG | Thông tin cho developer chẩn đoán | Bước xử lý hoặc lựa chọn cấu hình |
| INFO | Sự kiện hoạt động bình thường đáng ghi nhận | Ứng dụng khởi động, job hoàn thành |
| WARN | Tình huống bất thường nhưng có thể phục hồi | Dependency timeout được retry thành công |
| ERROR | Thất bại cần chú ý hoặc không thể hoàn tất thao tác | Ghi dữ liệu thất bại, dependency không khả dụng |

### 4.1. Không ghi mọi request ở ERROR

HTTP `400` vì client gửi input không hợp lệ không tự động là lỗi hệ thống. Nó có thể cần log ở INFO hoặc DEBUG với mã lỗi phù hợp, hoặc chỉ cần metric tổng hợp.

HTTP `500` không mong đợi thường cần ERROR và thông tin exception có kiểm soát.

Không nên áp dụng quy tắc cứng rằng:

```text
4xx = WARN cho mọi request
5xx = ERROR cho mọi request
```

Hãy cân nhắc bản chất lỗi, mức độ thường gặp và cách xử lý trong hệ thống.

### 4.2. Dùng WARN cho lỗi đã xử lý được

Ví dụ gọi dịch vụ đối tác lần đầu timeout nhưng retry thành công:

```java
log.warn(
        "partner.request.retry dependency={} attempt={} reasonCode={}",
        "pricing-service",
        1,
        "TIMEOUT"
);
```

Khi cuối cùng thành công, không nên ghi một loạt ERROR khiến người vận hành hiểu nhầm toàn bộ thao tác đã thất bại.

### 4.3. Tránh log trùng exception

Một exception có thể đi qua repository, service, controller và `@ControllerAdvice`.

Nếu tất cả tầng đều viết `log.error(..., exception)`, log có thể chứa nhiều stack trace giống nhau cho một lỗi.

Thường nên có **một ranh giới chịu trách nhiệm ghi lỗi đầy đủ**, còn các tầng khác bổ sung context bằng mã lỗi hoặc rethrow khi thích hợp.

## 5. Viết log bằng SLF4J trong Spring Boot

Không nên dùng `System.out.println(...)` làm cơ chế logging vận hành chính. Nó thiếu log level, metadata chuẩn và khả năng cấu hình tập trung tương đương logging framework.

Ví dụ:

```java
package com.example.orders.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void submit(String operationRef) {
        log.info(
                "order.submit.started operationRef={}",
                operationRef
        );

        // Xử lý đơn hàng

        log.info(
                "order.submit.completed operationRef={}",
                operationRef
        );
    }
}
```

Ví dụ giả định `operationRef` là mã tham chiếu nội bộ đã được thiết kế để xuất hiện trong log, không chứa email hoặc secret.

### 5.1. Dùng placeholder thay vì nối chuỗi

Ưu tiên:

```java
log.debug(
        "inventory.lookup.completed itemCount={} durationMs={}",
        itemCount,
        elapsedMs
);
```

Tránh:

```java
log.debug(
        "inventory.lookup.completed itemCount=" + itemCount +
        " durationMs=" + elapsedMs
);
```

SLF4J hỗ trợ tham số hóa message để việc format có thể được trì hoãn khi mức log tương ứng bị tắt. Tuy vậy, object truyền vào vẫn phải được chọn an toàn: placeholder **không tự loại bỏ dữ liệu nhạy cảm**.

### 5.2. Không gọi `toString()` tùy tiện trên object chứa dữ liệu

Rủi ro:

```java
log.debug("CreateOrderRequest: {}", request);
```

Nếu `CreateOrderRequest.toString()` hoặc `record.toString()` chứa tên, địa chỉ, email, token hoặc số thẻ, các giá trị đó có thể xuất hiện trong log.

Thay bằng:

```java
log.debug(
        "order.create.validated itemCount={} paymentType={}",
        request.items().size(),
        paymentTypeCode
);
```

`paymentTypeCode` nên là một tập giá trị có kiểm soát như `CARD`, `BANK_TRANSFER`, `WALLET`, không phải số tài khoản hoặc dữ liệu thẻ.

## 6. Vì sao không nên log nguyên HTTP request và response?

HTTP request có thể chứa:

- Header `Authorization` hoặc `Proxy-Authorization`.
- `Cookie`, session ID và anti-CSRF token.
- Query parameter chứa token reset mật khẩu hoặc mã mời.
- Path parameter chứa email, số điện thoại hoặc số tài khoản.
- Request body chứa thông tin cá nhân, địa chỉ, tài liệu hoặc nội dung trò chuyện.
- Multipart upload và file người dùng.

Response cũng có thể chứa:

- Session cookie mới trong `Set-Cookie`.
- Access token, refresh token.
- Kết quả tra cứu hồ sơ cá nhân.
- Dữ liệu nghiệp vụ không dành cho người xem log.

Vì thế, những đoạn sau không phù hợp trong production:

```java
log.info("Headers: {}", request.getHeaderNames());
log.info("Query string: {}", request.getQueryString());
log.info("Authorization: {}", request.getHeader("Authorization"));
log.debug("Body: {}", rawRequestBody);
log.debug("Response: {}", rawResponseBody);
```

Ngay cả khi header names không chứa giá trị secret, việc dump toàn bộ headers có thể khuyến khích các thay đổi sau này ghi thêm dữ liệu nguy hiểm. Nên thiết kế một **allowlist field** thay vì dump mặc định.

### 6.1. URL có thể chứa dữ liệu cá nhân

Không nên ghi nguyên URL như:

```text
/api/users/alice@example.test/orders?reset_token=...
```

Hãy ghi route template:

```text
/api/users/{userId}/orders
```

và ghi mã kết quả, thời gian xử lý, correlation ID.

**Route template** khác **request URI**:

| Giá trị | Ví dụ | Rủi ro |
| --- | --- | --- |
| Request URI thực | `/api/users/alice@example.test/orders` | Chứa dữ liệu động |
| Route template | `/api/users/{userId}/orders` | Ổn định hơn, ít lộ dữ liệu |

### 6.2. Request body logging không phải mặc định tốt

Đôi khi developer bật body logging để debug serialization. Nhưng một body có thể rất lớn, chứa secret hoặc dữ liệu có chính sách lưu trữ riêng.

Nếu thật sự phải ghi một số thông tin từ body, chỉ trích xuất **các field được phép** với mục đích đã xác định. Ví dụ:

```text
event=upload.validated
fileCount=3
declaredContentType=application/pdf
```

Không ghi nội dung file, không ghi multipart bytes và không ghi raw JSON chỉ để “dễ debug”.

### 6.3. Cẩn trọng với `ContentCachingRequestWrapper`

Spring Web có các wrapper có thể cache nội dung request/response để đọc lại trong quá trình xử lý. Việc có wrapper **không đồng nghĩa nội dung được phép ghi vào log**.

Ngoài vấn đề privacy, cache body còn tăng tiêu thụ bộ nhớ và có giới hạn kích thước. Nếu bật request/response body logging để debug, phải giới hạn phạm vi, kích thước, thời gian và field được phép; tắt trong production trừ khi có yêu cầu kiểm soát riêng.

## 7. Request context là gì?

Một HTTP request thường đi qua nhiều tầng:

```text
API Gateway
     |
     v
Spring MVC Filter
     |
     v
Controller
     |
     v
OrderService
     |
     v
Repository / HTTP client
     |
     v
Dependency
```

Nếu mỗi tầng ghi một vài dòng log, cần một cách để liên kết chúng. **Request context** là tập metadata phục vụ liên kết đó, không phải bản sao đầy đủ của request.

Các field thường cân nhắc:

```text
requestId
traceId
spanId
route
operation
service
environment
```

Tùy hệ thống có thể bổ sung `tenantRef`, `jobRef` hoặc định danh người dùng được giảm nhạy cảm, nhưng phải kiểm soát mục đích và phạm vi.

### 7.1. Correlation ID và request ID

Một `requestId` là định danh gắn với một yêu cầu. Ví dụ:

```text
requestId=7d2c9e64-8d74-46f1-9d2d-50c6d049e84e
```

Các log trong cùng request có thể mang giá trị này:

```text
INFO  requestId=7d2c9e64... event=http.request.received route=/api/orders
INFO  requestId=7d2c9e64... event=order.validated itemCount=2
WARN  requestId=7d2c9e64... event=inventory.retry attempt=1
INFO  requestId=7d2c9e64... event=http.request.completed status=201 durationMs=173
```

Với hệ thống nhiều service, correlation có thể dùng các ID do tracing tạo ra. Không nên tự phát minh nhiều request IDs mâu thuẫn nếu đã có cơ chế tracing đáng tin cậy.

### 7.2. ID không phải chứng cứ xác thực

Nếu client gửi header:

```text
X-Request-ID: some-value
```

giá trị đó vẫn là **input không đáng tin cậy**. Không được dùng request ID như bằng chứng user đã đăng nhập, có quyền truy cập hoặc đang thuộc một transaction hợp lệ.

Một request ID chỉ nên phục vụ correlation và hỗ trợ tìm kiếm.

## 8. MDC: đưa context vào log trong cùng thread

SLF4J cung cấp `MDC` (*Mapped Diagnostic Context*) để đặt các cặp key–value gắn với ngữ cảnh thực thi logging.

Ví dụ:

```java
import org.slf4j.MDC;

MDC.put("requestId", "7d2c9e64-...");

try {
    log.info("order.validation.started");
} finally {
    MDC.remove("requestId");
}
```

Nếu logging pattern hoặc JSON encoder đã được cấu hình để xuất MDC, các log phát ra trong khoảng này có thể mang `requestId`.

### 8.1. MDC không tự sửa mọi dòng log

Chỉ gọi:

```java
MDC.put("requestId", requestId);
```

không đủ để đảm bảo giá trị được in. Bạn còn phải cấu hình logging output đọc MDC, hoặc sử dụng encoder hỗ trợ MDC fields.

Ví dụ Logback pattern:

```properties
logging.pattern.level=%5p [requestId:%X{requestId:-}]
```

Đây là ví dụ tùy chỉnh phần level pattern theo cơ chế logging của Spring Boot sử dụng Logback. Cú pháp placeholder có thể phụ thuộc logging system/version; khi triển khai, hãy quan sát log thực tế.

### 8.2. Tại sao phải xóa MDC?

Trong servlet applications, các thread trong thread pool có thể được **tái sử dụng** cho request khác.

Nếu request A đặt:

```text
requestId=A
```

rồi không xóa, request B được xử lý trên cùng thread có thể vô tình mang ID của A.

Hậu quả:

- Log của hai request bị trộn.
- Việc điều tra lỗi trở nên sai lệch.
- Metadata về request trước có thể bị lộ vào log request sau.

Vì vậy, mọi đoạn code tự đặt MDC cần sử dụng `try/finally` hoặc cơ chế cleanup tương ứng.

### 8.3. Chỉ đặt field đã được phép vào MDC

Không nên:

```java
MDC.put("email", customerEmail);
MDC.put("authorization", bearerToken);
MDC.put("requestBody", rawJson);
```

MDC thường được tự động xuất ở nhiều log statement. Đặt một field nhạy cảm vào MDC có thể khiến nó lan ra **mọi dòng log** trong cùng luồng xử lý.

Một request ID được tạo và kiểm soát tốt thường phù hợp hơn nhiều so với email hoặc session token.

## 9. Ví dụ đầy đủ: tạo request ID trong Servlet filter

Với Spring Boot 3.x dùng Spring MVC/Servlet và Jakarta Servlet API, có thể xây dựng `OncePerRequestFilter`.

Mục tiêu:

1. Tạo một request ID không chứa dữ liệu người dùng.
2. Đặt ID vào MDC để các service có thể ghi log liên kết.
3. Gửi ID về client để thuận tiện khi báo lỗi hỗ trợ.
4. Ghi một bản tóm tắt HTTP request an toàn.
5. Xóa ID khỏi MDC khi hoàn tất.

```java
package com.example.orders.logging;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestLoggingFilter extends OncePerRequestFilter {

    private static final Logger log =
            LoggerFactory.getLogger(RequestLoggingFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();
        long startedAt = System.nanoTime();

        MDC.put("requestId", requestId);
        response.setHeader("X-Request-ID", requestId);

        try {
            chain.doFilter(request, response);
        } finally {
            Object pattern = request.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE
            );

            String route =
                    pattern instanceof String
                            ? (String) pattern
                            : "unmatched";

            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startedAt
            );

            log.info(
                    "http.request.completed method={} route={} status={} durationMs={}",
                    request.getMethod(),
                    route,
                    response.getStatus(),
                    durationMs
            );

            MDC.remove("requestId");
        }
    }
}
```

Ví dụ cố ý **không ghi** `getRequestURI()`, query string, headers, body, cookies hay user identity.

### 9.1. Vì sao dùng UUID được server tạo?

Code trên **không tin cậy giá trị request ID do client tự gửi**. UUID do server sinh tránh việc client đưa chuỗi chứa ký tự xuống dòng, thông tin cá nhân hoặc dữ liệu cố ý gây nhiễu vào log.

Nếu hệ thống đã có gateway đáng tin cậy sinh correlation ID, bạn có thể tiếp nhận ID qua hợp đồng đã xác định, nhưng phải kiểm tra nguồn, định dạng, giới hạn độ dài và quy tắc propagation.

Không nên lấy tùy ý:

```java
String id = request.getHeader("X-Request-ID");
MDC.put("requestId", id);
```

rồi tin rằng ID luôn an toàn.

### 9.2. Vì sao log route template thay vì URL thực?

Spring MVC có thể lưu pattern của handler đã match trong request attribute:

```java
HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE
```

Ví dụ route `/api/orders/{orderId}` ổn định và ít lộ thông tin hơn URI `/api/orders/abc123`.

Nếu không có MVC mapping (như request bị từ chối trước handler), ví dụ dùng giá trị cố định `unmatched` thay vì ghi đường dẫn người dùng gửi.

### 9.3. Lưu ý với exception và asynchronous Servlet processing

Đây là ví dụ giới thiệu, không phải access-log framework hoàn chỉnh:

- Một exception chưa được web container xử lý có thể khiến status đọc trong filter khác status cuối cùng sau error dispatch.
- Servlet async processing có thể trả quyền điều khiển khỏi filter trước khi response thực sự hoàn tất.
- Error dispatch, filter ordering và nested dispatch có thể làm việc ghi đúng **một log hoàn tất cuối cùng** phức tạp hơn.

Với hệ thống dùng async Servlet, streaming hoặc có yêu cầu chính xác về response completion, cần thiết kế thêm `AsyncListener`, Spring MVC interceptor hoặc lớp instrumentation phù hợp. Không coi `finally` của filter là bằng chứng tuyệt đối rằng client đã nhận response đầy đủ.

### 9.4. Nếu MDC đã có `requestId` trước đó?

Ví dụ đơn giản luôn gán và xóa một key. Trong hệ thống có nhiều lớp filter hoặc framework cùng quản lý MDC, một filter có thể vô tình ghi đè giá trị do hạ tầng khác đặt.

Khi tích hợp, nên xác định một component duy nhất sở hữu request ID. Nếu cần tạm thời thay một giá trị đã tồn tại, lưu giá trị cũ rồi khôi phục trong `finally`, thay vì xóa mù:

```java
String previous = MDC.get("requestId");
MDC.put("requestId", requestId);

try {
    // Xử lý
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
```

## 10. Trace ID và span ID trong hệ thống nhiều service

Request ID được tạo riêng trong một service hữu ích cho tìm kiếm log cục bộ. Nhưng khi request đi qua nhiều service, cần liên kết các bước giữa những tiến trình khác nhau:

```text
Client
  |
  v
Gateway                traceId = T, spanId = S1
  |
  v
Order Service          traceId = T, spanId = S2
  |
  +------> Inventory Service  traceId = T, spanId = S3
  |
  +------> Payment Service    traceId = T, spanId = S4
```

Trong distributed tracing:

- **Trace ID** xác định toàn bộ trace của một luồng xử lý.
- **Span ID** xác định một span cụ thể trong trace.
- **Parent span** thể hiện quan hệ giữa những bước gọi.

Khi hạ tầng tracing được tích hợp đúng, log của các service có thể mang trace/span IDs để điều tra xuyên hệ thống mà không cần ghi request body.

### 10.1. Micrometer Tracing và Spring Boot

Nhiều dòng Spring Boot hiện đại tích hợp observability qua Micrometer và có thể sử dụng Micrometer Tracing với OpenTelemetry hoặc Brave bridge tùy dependency và phiên bản.

Khi tracing được bật và logging đã cấu hình phù hợp, trace/span context có thể xuất hiện trong log pattern hoặc structured logging fields.

**Không nên tự thêm một bộ request ID, trace ID và span ID độc lập mà không có thiết kế.** Trước tiên kiểm tra hạ tầng quan sát đã tạo và propagate những ID nào.

### 10.2. Trace context được truyền thế nào?

Hệ thống tracing thường sử dụng propagation headers theo chuẩn phù hợp, chẳng hạn W3C Trace Context:

```text
traceparent: ...
```

Tracing instrumentation chịu trách nhiệm tạo, tiếp nhận và chuyển tiếp context giữa HTTP clients, servers hoặc messaging integrations.

Nếu bạn tự thêm header `X-Request-ID`, đó không tự động biến nó thành distributed trace. Cần thiết kế propagation rõ ràng hoặc dùng tracing infrastructure.

### 10.3. Trace ID cũng không phải secret

Trace ID hữu ích cho đối chiếu nhưng **không được dùng để chứng minh quyền truy cập**. Người biết trace ID không nên tự động được xem dữ liệu nhạy cảm của trace nếu chưa được phép.

Ngoài ra, một trace liên quan nhiều service có thể chứa hành vi của người dùng, nên việc xem và lưu dữ liệu trace vẫn cần phân quyền, retention và chính sách phù hợp.

## 11. MDC và xử lý bất đồng bộ

Một khó khăn thường gặp: MDC gắn với ngữ cảnh thread của logging implementation. Nếu bạn chuyển công việc sang một executor khác, context **không mặc nhiên luôn được truyền sang thread mới**.

Ví dụ:

```java
MDC.put("requestId", requestId);

executor.execute(() -> {
    log.info("background.task.started");
});
```

Log của background thread có thể không mang `requestId`.

Điều này làm mất khả năng liên kết các bước và đôi khi gây nhầm nếu một thread trong pool còn MDC cũ do code khác không cleanup.

### 11.1. Truyền MDC có kiểm soát bằng TaskDecorator

Ví dụ Spring `ThreadPoolTaskExecutor`:

```java
package com.example.orders.logging;

import java.util.Map;
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class LoggingExecutorConfiguration {

    @Bean("contextAwareExecutor")
    public ThreadPoolTaskExecutor contextAwareExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("order-worker-");

        executor.setTaskDecorator(task -> {
            Map<String, String> captured =
                    MDC.getCopyOfContextMap();

            return () -> {
                Map<String, String> previous =
                        MDC.getCopyOfContextMap();

                try {
                    if (captured == null) {
                        MDC.clear();
                    } else {
                        MDC.setContextMap(captured);
                    }

                    task.run();
                } finally {
                    if (previous == null) {
                        MDC.clear();
                    } else {
                        MDC.setContextMap(previous);
                    }
                }
            };
        });

        return executor;
    }
}
```

`TaskDecorator` lưu bản sao MDC tại thời điểm task được decorate, thiết lập trong thread thực thi rồi khôi phục context trước đó khi task kết thúc.

### 11.2. Sử dụng với `@Async`

Khi bật async method execution:

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
```

Một service có thể chọn executor:

```java
@Service
public class ReceiptService {

    private static final Logger log =
            LoggerFactory.getLogger(ReceiptService.class);

    @Async("contextAwareExecutor")
    public CompletableFuture<Void> sendReceipt(String operationRef) {
        log.info(
                "receipt.send.started operationRef={}",
                operationRef
        );

        // Công việc gửi receipt

        return CompletableFuture.completedFuture(null);
    }
}
```

Ví dụ giả định phương thức được gọi từ bên ngoài qua async proxy, không phải self-invocation, và executor được cấu hình như trên.

### 11.3. Chỉ truyền các field được phép

Truyền toàn bộ MDC sang background thread cũng có thể truyền theo dữ liệu nhạy cảm nếu trước đó ai đó đã đặt chúng vào MDC. Vì thế, giải pháp quan trọng nhất là **không đưa secret hoặc PII không cần thiết vào MDC từ đầu**.

Một hệ thống có yêu cầu bảo vệ nghiêm ngặt có thể chỉ truyền các field trong allowlist, chẳng hạn `traceId`, `spanId` hoặc `requestId`, thay vì sao chép mọi cặp key–value.

### 11.4. Khi task sống lâu hơn request

Một tác vụ nền có thể chạy vài phút sau khi HTTP request kết thúc. Request ID vẫn có thể là một tương quan hữu ích, nhưng tác vụ nên có **job ID riêng** để phân biệt lifecycle của nó:

```text
requestId=R1 jobId=J45 event=job.created
jobId=J45 event=job.started
jobId=J45 event=job.completed
```

Đừng giữ toàn bộ thông tin người dùng trong background task chỉ để tiếp tục ghi log. Truyền context tối thiểu và thông tin thực sự cần cho nghiệp vụ, có phân quyền và lifecycle riêng.

## 12. WebFlux và Reactor Context

Trong Spring WebFlux hoặc hệ thống reactive, một request có thể chuyển qua nhiều thread mà không có ranh giới thread cố định. Không nên lấy MDC thread-local trong Servlet làm giải pháp mặc định cho toàn bộ reactive pipeline.

Reactor cung cấp **Reactor Context** để mang dữ liệu theo reactive subscription; những hệ thống tracing hiện đại có thể tích hợp cơ chế context propagation.

Ví dụ minh họa:

```java
Mono<String> operation =
        Mono.deferContextual(contextView -> {
            String requestId = contextView.get("requestId");
            return Mono.just("request=" + requestId);
        });

return operation.contextWrite(
        context -> context.put("requestId", requestId)
);
```

Đây là ví dụ về ý tưởng mang context trong Reactor. Nếu cần `requestId` tự xuất hiện trong log, vẫn phải có cơ chế nối Reactor Context với logging context hoặc dùng tracing instrumentation phù hợp.

Không tự `MDC.put(...)` ở đầu một reactive chain rồi kỳ vọng mọi operator và mọi asynchronous boundary giữ đúng giá trị.

## 13. Log exception thế nào để vừa hữu ích vừa an toàn?

Một exception có:

- Loại lỗi.
- Message.
- Cause chain.
- Stack trace.
- Đôi khi dữ liệu request, SQL, endpoint hoặc giá trị nhạy cảm do thư viện đưa vào message.

Để debug production, stack trace có thể rất hữu ích. Nhưng không nên log mọi exception ở mọi tầng.

### 13.1. Ví dụ dùng failure code

```java
try {
    inventoryClient.reserve(operationRef);
} catch (InventoryTimeoutException ex) {
    log.warn(
            "inventory.reserve.retryable_failure operationRef={} failureCode={}",
            operationRef,
            "INVENTORY_TIMEOUT"
    );
    throw ex;
}
```

Nếu tầng cao hơn sẽ chịu trách nhiệm log stack trace một lần, tầng này có thể chỉ ghi mã lỗi hoặc không ghi gì và để exception propagate.

### 13.2. Log stack trace tại ranh giới phù hợp

Ví dụ ở một error handling boundary:

```java
log.error(
        "order.submit.failed operationRef={} failureCode={}",
        operationRef,
        "UNEXPECTED_FAILURE",
        exception
);
```

Đối số cuối là exception để logging framework có thể ghi stack trace.

**Lưu ý quan trọng:** stack trace và exception message không tự động an toàn. Một thư viện HTTP hoặc database có thể đưa giá trị request, SQL parameter hoặc URL chứa secret vào exception. Với lỗi có nguy cơ như vậy, cần chính sách sanitize hoặc chỉ ghi error code/stack tại nơi truy cập log được kiểm soát phù hợp.

### 13.3. Không ghi exception bằng `toString()` của toàn request

Không nên:

```java
log.error(
        "Failed request={} error={}",
        createOrderRequest,
        exception.getMessage()
);
```

`createOrderRequest` có thể chứa dữ liệu cá nhân, còn `exception.getMessage()` có thể chứa dữ liệu không được kiểm soát.

Tốt hơn:

```java
log.error(
        "order.create.failed operationRef={} failureCode={}",
        operationRef,
        "PERSISTENCE_FAILURE"
);
```

Khi cần thêm stack trace, dùng một đường log nội bộ được kiểm soát, sau khi đánh giá nguồn dữ liệu có thể nằm trong cause chain.

## 14. Ví dụ error handling ở Spring MVC

Một `@RestControllerAdvice` có thể chuẩn hóa kết quả HTTP và log lỗi tại ranh giới API.

```java
package com.example.orders.web;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    private static final Logger log =
            LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(InvalidOrderException.class)
    public ResponseEntity<ApiError> invalidOrder(
            InvalidOrderException ex) {

        log.info(
                "order.request.rejected failureCode={} requestId={}",
                "INVALID_ORDER",
                MDC.get("requestId")
        );

        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_ORDER",
                        MDC.get("requestId")
                )
        );
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> unexpected(Exception ex) {

        log.error(
                "http.request.unexpected_failure failureCode={} requestId={}",
                "INTERNAL_ERROR",
                MDC.get("requestId")
        );

        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(
                        new ApiError(
                                "INTERNAL_ERROR",
                                MDC.get("requestId")
                        )
                );
    }

    public record ApiError(String code, String requestId) {
    }
}
```

Ví dụ giả định `InvalidOrderException` là class nghiệp vụ do ứng dụng định nghĩa. Handler cố ý không đưa `ex.getMessage()` ra response và không trả stack trace cho client.

### 14.1. Khi nào nên log stack trace?

Nếu `unexpected(...)` là nơi duy nhất log các lỗi ngoài dự kiến, có thể cân nhắc ghi exception như đối số cuối cho log nội bộ **sau khi xác định exception chain không chứa secret không được phép lưu**.

Đừng sử dụng stack trace như mặc định bất biến cho mọi loại exception. Đối với lỗi validation do client, mã lỗi thường đủ.

### 14.2. Log và response là hai đối tượng khác nhau

Client thường cần:

```json
{
  "code": "INTERNAL_ERROR",
  "requestId": "7d2c9e64-..."
}
```

Người vận hành cần thêm thông tin về dependency và bước thất bại. Nhưng **không bên nào cần nhận password, token hoặc nội dung raw request để chỉ biết mã lỗi**.

## 15. Structured logging: dữ liệu có cấu trúc

Log truyền thống thường là một chuỗi:

```text
INFO order.submit.completed operationRef=ord_83f1 durationMs=217
```

Structured logging biểu diễn log như một record có các field rõ ràng. Một ví dụ JSON minh họa:

```json
{
  "timestamp": "2026-01-01T09:30:15Z",
  "level": "INFO",
  "service": "order-api",
  "event": "order.submit.completed",
  "requestId": "7d2c9e64-...",
  "route": "/api/orders",
  "status": 201,
  "durationMs": 217
}
```

Đây là dữ liệu giả lập để minh họa cấu trúc, không phải schema bắt buộc của Spring Boot.

### 15.1. Lợi ích của structured logging

- Dễ lọc theo `event`, `status` hoặc `requestId`.
- Dễ xây dashboard và alert.
- Tránh parse text bằng regex mong manh.
- Truy vấn nhiều service nhất quán hơn khi có field naming convention.
- Dễ áp dụng policy kiểm soát field ở tầng encoder/collector.

### 15.2. Structured không đồng nghĩa an toàn

JSON cũng có thể rò rỉ dữ liệu:

```json
{
  "event": "auth.login",
  "authorization": "<secret>",
  "password": "<secret>"
}
```

Việc chuyển plain text sang JSON không tự xóa nội dung nhạy cảm. **Allowlist field và nguyên tắc data minimization vẫn quan trọng nhất**.

### 15.3. Hỗ trợ trong Spring Boot hiện đại

Những phiên bản Spring Boot mới có hỗ trợ structured logging tích hợp, trong đó một số dòng từ Spring Boot 3.4 hỗ trợ property như:

```properties
logging.structured.format.console=ecs
```

hoặc lựa chọn format phù hợp khác theo phiên bản. Các dòng Spring Boot cũ hơn có thể dùng Logback encoder và cấu hình riêng.

Hãy đối chiếu tài liệu của phiên bản trong dự án trước khi dùng một property cụ thể. Bài học này không phụ thuộc vào việc chọn ECS, Logstash JSON hay một format riêng: **field nào được đưa vào log và cách bảo vệ chúng là trách nhiệm chung**.

### 15.4. Thiết kế schema có kiểm soát

Nên thống nhất:

```text
event
requestId
traceId
spanId
route
status
durationMs
failureCode
dependency
operationRef
```

Tránh các field mơ hồ:

```text
data
payload
everything
userInfo
object
```

Nếu field không có định nghĩa rõ, nó dễ trở thành nơi chứa dữ liệu thừa.

## 16. Masking, redaction và allowlist

Ba khái niệm thường được dùng khi giảm dữ liệu nhạy cảm trong log:

- **Allowlist:** chỉ cho phép một số field xác định được ghi.
- **Redaction:** loại bỏ hoặc thay dữ liệu không được phép bằng một giá trị an toàn.
- **Masking:** che một phần dữ liệu để giảm khả năng đọc trực tiếp.

### 16.1. Allowlist thường an toàn hơn blacklist

Giả sử một DTO:

```java
public record LoginRequest(
        String username,
        String password,
        String otp,
        String deviceId
) {
}
```

Blacklist yêu cầu nhớ loại bỏ mọi field nhạy cảm. Nếu ngày mai DTO thêm `refreshToken`, developer có thể quên cập nhật bộ lọc.

Allowlist chỉ ghi những field thực sự cần:

```java
log.info(
        "auth.login.attempted authMethod={} requestId={}",
        "PASSWORD_AND_OTP",
        requestId
);
```

Không có field đầu vào người dùng nào được ghi nguyên giá trị.

### 16.2. Redaction ở nguồn

Ưu tiên loại bỏ secret **trước khi tạo log event**:

```java
log.info(
        "partner.request.completed dependency={} status={} durationMs={}",
        "payment-partner",
        statusCode,
        elapsedMs
);
```

Thay vì:

```java
log.info(
        "partner.response.body={}",
        redact(responseBody)
);
```

Việc cố redact toàn bộ body khó bảo đảm chính xác khi schema thay đổi, body lồng nhau hoặc xuất hiện dữ liệu có cấu trúc lạ. Nếu không cần nội dung body, hãy **không đọc/ghi nó vào log**.

### 16.3. Masking không thay thế kiểm soát quyền truy cập

Ngay cả log đã mask vẫn phải có:

- Quyền truy cập theo vai trò.
- Quy định retention.
- Mã hóa khi truyền và lưu nếu hệ thống yêu cầu.
- Kiểm soát export và chia sẻ.
- Quy trình xử lý khi phát hiện dữ liệu bị ghi sai.

Một email bị che một phần vẫn có thể liên kết được với cá nhân. Masking chỉ giảm rủi ro, không bảo đảm dữ liệu trở thành vô danh.

### 16.4. Khi cần đối chiếu một giá trị nhạy cảm

Nếu thật sự cần liên kết các event theo một identifier nhạy cảm, nên tạo **tham chiếu nội bộ** không trực tiếp hiển thị dữ liệu gốc.

Trong những trường hợp cần một giá trị liên kết ổn định nhưng không đảo ngược, có thể cân nhắc HMAC với khóa được quản lý an toàn. Tránh hash trần các giá trị có không gian nhỏ hoặc dễ đoán như email/số điện thoại vì chúng có thể bị thử đoán bằng dictionary.

Đây là quyết định thiết kế bảo mật và quản trị khóa, không nên tự triển khai chỉ để thay một dòng log.

## 17. Ngăn log injection và làm bẩn log

Một request có thể chứa chuỗi do client kiểm soát. Nếu ghi nguyên chuỗi đó vào plain-text log, ký tự xuống dòng hoặc ký tự điều khiển có thể làm một thông điệp trông như nhiều dòng log riêng.

Ví dụ không nên:

```java
log.info("User-agent={}", request.getHeader("User-Agent"));
```

Đầu vào do client đặt có thể rất dài hoặc chứa ký tự đặc biệt. Placeholder của SLF4J giúp tham số hóa, **không tự bảo đảm chuỗi đã được sanitize**.

### 17.1. Cách giảm rủi ro

- Không log raw header nếu không cần.
- Với field từ client bắt buộc phải ghi, đặt giới hạn độ dài và allowlist ký tự.
- Dùng structured logging encoder có cơ chế escape phù hợp.
- Ghi field theo tên và schema xác định.
- Không cho người dùng tự quyết định log level, event name hoặc tên field trong log.

### 17.2. Nếu bắt buộc nhận `X-Request-ID`

Một cách là kiểm tra định dạng trước khi chấp nhận:

```java
private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9_-]{1,64}");

private static String correlationId(String incoming) {
    if (incoming != null &&
            SAFE_ID.matcher(incoming).matches()) {
        return incoming;
    }

    return UUID.randomUUID().toString();
}
```

Ví dụ cần import `java.util.regex.Pattern` và `java.util.UUID`.

Nhưng kiểm tra ký tự **không xác thực nguồn của header**. Nếu hệ thống chỉ chấp nhận ID do trusted gateway cấp, cần thêm quy tắc trust boundary và cấu hình mạng tương ứng.

## 18. Access log, application log và audit log

Ba loại log phục vụ ba mục đích khác nhau.

| Loại log | Mục tiêu | Dữ liệu thường nên có |
| --- | --- | --- |
| Access log | Quan sát lưu lượng HTTP | Route/method/status/latency, request correlation |
| Application log | Chẩn đoán luồng xử lý và lỗi | Event, failure code, dependency, operation ID |
| Security audit log | Ghi nhận sự kiện bảo mật cần truy vết | Hành động, kết quả, principal reference đã kiểm soát, thời điểm |

### 18.1. Access log không nên ghi mọi header

Embedded Tomcat có cấu hình access logging tùy phiên bản Spring Boot:

```properties
server.tomcat.accesslog.enabled=true
```

Để sử dụng an toàn, cần thiết kế access-log pattern và log destination phù hợp. Một số access-log pattern có thể ghi raw request path, query, headers hoặc cookies nếu được cấu hình như vậy.

Vì thế, **bật access log không tự tạo một access log đã giảm nhạy cảm**. Trong môi trường có dữ liệu cá nhân trên URL, cần kiểm tra pattern thực tế hoặc ghi access summary từ một lớp HTTP instrumentation có khả năng lấy route template.

### 18.2. Application log không thay thế audit trail

Một sự kiện thay đổi quyền có thể cần được lưu như một audit event có cấu trúc:

```text
event=role.assignment.changed
actorRef=usr_73a1
targetRef=usr_83c4
roleCode=REPORT_VIEWER
result=SUCCESS
```

Những mã tham chiếu này vẫn có thể mang tính cá nhân tùy khả năng liên kết. Cần chính sách truy cập và lưu trữ phù hợp.

Không nên dùng `log.info("User X did Y")` như cơ chế duy nhất cho mọi yêu cầu audit. Audit trail quan trọng có thể cần tính toàn vẹn, retention, phân quyền và khả năng truy vấn riêng.

### 18.3. Không dùng audit log để chứa mật khẩu

Ngay cả sự kiện security có yêu cầu truy vết cao vẫn không cần password, OTP hoặc access token nguyên giá trị.

Ghi **hành vi và kết quả**, không ghi bí mật đã được sử dụng để thực hiện hành vi.

## 19. Các cấu hình DEBUG/TRACE cần cẩn trọng

Một số developer bật:

```properties
logging.level.root=DEBUG
```

hoặc:

```properties
logging.level.org.springframework=TRACE
```

để điều tra lỗi. Mức log càng chi tiết, các thư viện có thể ghi càng nhiều metadata, bao gồm thông tin không nên lưu lâu.

### 19.1. Debug SQL và bind parameters

Các thư viện ORM/JDBC có cơ chế log SQL statement và parameter binding ở mức DEBUG/TRACE tùy phiên bản.

Ví dụ query:

```sql
select * from customer where email = ?
```

Ngay cả khi SQL dùng placeholder, một logger theo dõi bind parameters có thể ghi giá trị email thực tế.

Không bật logging parameter bindings trên production nếu chưa đánh giá các dữ liệu có thể xuất hiện. Nếu cần điều tra truy vấn chậm, ưu tiên metric, query shape và dữ liệu tổng hợp an toàn hơn.

### 19.2. Spring Security và HTTP clients

Debug logging ở security filters hoặc HTTP client có thể tiết lộ thông tin về request, endpoint và headers tùy logger/phiên bản.

Trước khi bật:

1. Xác định chính xác logger/package cần debug.
2. Đánh giá log output trong một môi trường kiểm soát.
3. Đặt thời hạn bật và người chịu trách nhiệm tắt.
4. Không ghi token, cookie hoặc raw body.
5. Xác định nơi log được lưu và ai có quyền đọc.

### 19.3. Không log toàn bộ `Environment`

Spring Boot `Environment` có thể chứa connection passwords, secret placeholders sau khi resolve và nhiều property khác.

Không làm:

```java
log.info("Environment: {}", environment);
```

hoặc loop toàn bộ property sources để in giá trị. Khi cần chẩn đoán, chỉ đọc từng property **không nhạy cảm**.

## 20. Tên field và dữ liệu phải được kiểm soát ổn định

Một schema logging tốt nên có ý nghĩa dễ đoán:

```text
event=payment.authorize.failed
failureCode=PROVIDER_TIMEOUT
dependency=payment-gateway
durationMs=700
```

Tránh:

```text
message=Error calling payment
data={...}
debugValue={...}
```

### 20.1. Chọn event name có cấu trúc

Một quy ước:

```text
<domain>.<action>.<outcome>
```

Ví dụ:

```text
order.create.started
order.create.completed
order.create.failed
payment.authorize.failed
inventory.reserve.retry
auth.login.rejected
```

Không nhất thiết tất cả hệ thống phải theo đúng cú pháp trên, nhưng tên event nên nhất quán giữa các service.

### 20.2. Tách operation ID và request ID

Một request có thể kích hoạt nhiều công việc:

```text
requestId=R1 operationRef=O1 event=order.created
requestId=R1 jobRef=J1 event=receipt.job.created
jobRef=J1 event=receipt.job.completed
```

Request ID mô tả vòng đời HTTP; jobRef mô tả vòng đời job. Nếu một job chạy sau request, nó vẫn có thể được liên kết mà không cần giữ raw request payload trong log.

### 20.3. Ghi thời gian thực thi

Để đo duration bên trong Java, sử dụng monotonic clock:

```java
long start = System.nanoTime();

try {
    callPartner();
} finally {
    long durationMs =
            TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - start
            );

    log.info(
            "partner.call.finished dependency={} durationMs={}",
            "pricing-service",
            durationMs
    );
}
```

Ví dụ cần import `java.util.concurrent.TimeUnit`.

`System.nanoTime()` phù hợp đo khoảng thời gian trôi qua, không dùng nó làm timestamp hiển thị. Timestamp log do logging framework cung cấp và nên đồng bộ hóa thời gian hệ thống theo chính sách vận hành.

## 21. Giảm dung lượng log và tránh chi phí quá mức

Ghi log cho mọi phần tử trong một danh sách lớn có thể tạo hàng triệu dòng:

```java
for (Item item : items) {
    log.info("Processing item {}", item);
}
```

Nếu `item.toString()` chứa dữ liệu nhạy cảm, rủi ro càng lớn.

### 21.1. Dùng log tổng hợp

Thay:

```java
log.info(
        "batch.completed jobRef={} processed={} failed={} durationMs={}",
        jobRef,
        processedCount,
        failedCount,
        durationMs
);
```

Nếu cần điều tra một item lỗi cụ thể, có thể ghi tham chiếu không nhạy cảm cùng error code, không dump toàn bộ item.

### 21.2. Sampling cho log tần suất cao

Một endpoint được gọi hàng chục nghìn lần mỗi phút không nhất thiết cần log INFO cho từng bước thành công. Có thể dùng metrics cho tổng hợp, tracing sampling cho phân tích và log có chọn lọc cho lỗi.

Tuy nhiên, **không sampling mù các sự kiện audit hoặc sự kiện bảo mật bắt buộc phải giữ**. Mỗi loại dữ liệu có mục đích và retention khác nhau.

### 21.3. Rate limiting cho lỗi lặp lại

Khi dependency bị mất kết nối, hàng nghìn request có thể tạo cùng exception stack trace. Hãy cân nhắc giới hạn log lặp, aggregate failure counters và alert dựa trên metrics.

Một log entry có correlation ID đủ để phân tích một ví dụ, còn metrics cho biết quy mô ảnh hưởng.

## 22. Retention, truy cập và bảo vệ log

Không có một thời hạn lưu log phù hợp với mọi hệ thống. Thời gian lưu cần dựa trên mục tiêu vận hành, sự cần thiết của dữ liệu, loại log và quy định áp dụng.

Những câu hỏi vận hành nên trả lời:

- Ai được xem application log, access log và audit log?
- Log được giữ bao lâu, tại đâu và trong những bản sao nào?
- Có mã hóa dữ liệu khi truyền và khi lưu không?
- Những hệ thống bên thứ ba nào nhận log?
- Có cơ chế xóa/giới hạn export và sao chép log không?
- Khi phát hiện secret trong log, ai chịu trách nhiệm xử lý?
- Log production có bị trộn với môi trường dev/test không?

### 22.1. Không lấy “chỉ có SRE xem log” làm lý do ghi secret

Một hệ thống tập trung log vẫn có rủi ro bị truy cập nhầm, chia sẻ nhầm hoặc xuất dữ liệu khi điều tra sự cố.

**Không ghi secret vào log ngay từ đầu** an toàn hơn nhiều so với ghi rồi chỉ dựa vào quyền truy cập.

### 22.2. Khi phát hiện secret đã lọt vào log

Cần thực hiện quy trình ứng phó phù hợp:

1. Ngăn ứng dụng tiếp tục phát sinh dòng log nhạy cảm.
2. Đánh giá loại secret và phạm vi log đã được sao chép.
3. Thu hồi/rotate credential nếu đó là secret có thể bị lạm dụng.
4. Hạn chế truy cập và xử lý các bản sao log theo quy trình tổ chức.
5. Bổ sung kiểm soát để tránh tái diễn.

Chỉ xóa một dòng khỏi dashboard thường chưa đủ nếu dữ liệu đã được chuyển qua collector, archive hoặc export khác.

## 23. Ví dụ tổng hợp: logging một request đặt hàng

Giả sử API `POST /api/orders` gọi inventory service và ghi đơn hàng. Một policy logging hợp lý có thể chia các mốc:

```text
HTTP request received
       |
       v
Request ID được tạo / trace context được nhận
       |
       v
Validate input
       |
       +--> Invalid -> log failureCode=VALIDATION_FAILED
       |
       v
Reserve inventory
       |
       +--> Timeout -> log dependency + retry attempt
       |
       v
Persist order
       |
       +--> Failure -> log sanitized errorCode
       |
       v
HTTP response
       |
       v
Log method, route template, status, duration
```

### 23.1. Những dữ liệu được phép trong ví dụ

```text
requestId
traceId
event
operationRef
itemCount
failureCode
dependency
attempt
method
route
status
durationMs
```

Điều kiện: `operationRef` là mã đã được đánh giá phù hợp để xuất log; `itemCount` là số lượng, không phải nội dung đơn hàng.

### 23.2. Những dữ liệu bị loại

```text
Authorization header
Session cookie
Customer email
Delivery address
Payment card details
Request body
Response body
Access token / refresh token
```

### 23.3. Ví dụ service logging theo event

```java
package com.example.orders.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private static final Logger log =
            LoggerFactory.getLogger(CheckoutService.class);

    private final InventoryClient inventory;
    private final OrderRepository repository;

    public CheckoutService(
            InventoryClient inventory,
            OrderRepository repository
    ) {
        this.inventory = inventory;
        this.repository = repository;
    }

    public void checkout(
            String operationRef,
            int itemCount
    ) {
        log.info(
                "checkout.started operationRef={} itemCount={}",
                operationRef,
                itemCount
        );

        long started = System.nanoTime();

        try {
            inventory.reserve(operationRef);
            repository.saveOperation(operationRef);

            log.info(
                    "checkout.completed operationRef={}",
                    operationRef
            );
        } catch (InventoryTimeoutException ex) {
            log.warn(
                    "checkout.failed operationRef={} failureCode={} dependency={}",
                    operationRef,
                    "INVENTORY_TIMEOUT",
                    "inventory-service"
            );
            throw ex;
        } finally {
            long durationMs =
                    TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started
                    );

            log.debug(
                    "checkout.finished operationRef={} durationMs={}",
                    operationRef,
                    durationMs
            );
        }
    }
}
```

Ví dụ giả định ứng dụng có `InventoryClient`, `OrderRepository`, `InventoryTimeoutException` và import `TimeUnit` phù hợp. Không dùng ví dụ như code hoàn chỉnh của một giao dịch tài chính; nó minh họa cách chọn field logging.

### 23.4. Output minh họa

```text
INFO  requestId=R-123 checkout.started operationRef=O-987 itemCount=2
WARN  requestId=R-123 checkout.failed operationRef=O-987 failureCode=INVENTORY_TIMEOUT dependency=inventory-service
INFO  requestId=R-123 http.request.completed method=POST route=/api/orders status=503 durationMs=804
```

Ở ví dụ này, log không chứa customer email, địa chỉ giao hàng, thông tin thanh toán hoặc raw payload. Người vận hành vẫn có thể tìm tất cả log theo `requestId=R-123` rồi xác định dependency lỗi.

## 24. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Log chỉ dùng nội bộ nên có thể ghi password.” | Internal log vẫn có người truy cập, export, backup và rủi ro rò rỉ |
| “Dùng placeholder `{}` thì mọi dữ liệu đều an toàn.” | Parameterized logging không tự sanitize nội dung |
| “DEBUG được tắt trong production nên có thể viết log token.” | DEBUG có thể được bật khi sự cố; không nên chứa secret trong bất kỳ level nào |
| “Chỉ email và tên mới là dữ liệu cá nhân.” | IP, device ID, URL, account ID cũng có thể cho phép nhận diện |
| “Masking khiến dữ liệu hoàn toàn vô danh.” | Giá trị che một phần vẫn có thể bị liên kết hoặc suy đoán |
| “Request ID là bằng chứng xác thực.” | Correlation ID không phải credential hoặc authorization proof |
| “MDC tự chạy qua mọi thread.” | Nhiều asynchronous boundary không tự propagate MDC |
| “MDC đặt một lần là đủ.” | Phải cleanup/restore để không rò context giữa request |
| “JDK reactive app dùng MDC như Servlet filter.” | Reactor Context và context propagation cần xử lý khác |
| “Log raw URI giúp debug tốt hơn route template.” | Raw URI có thể chứa email, token và định danh động |
| “Structured JSON logging tự động bảo vệ PII.” | JSON chỉ thay format, không thay chính sách chọn field |
| “Log full exception message luôn an toàn.” | Exception có thể chứa SQL params, URL, token hoặc input |
| “Access log không thể chứa secret.” | Access-log pattern có thể chứa URL, query, cookie hoặc headers |
| “INFO là mức phù hợp cho từng item trong batch.” | Dễ tạo log volume lớn, nên tổng hợp hoặc sampling |
| “Request hoàn tất khi filter `finally` chạy.” | Async Servlet và error dispatch có thể cần instrumentation khác |

## 25. Bài thực hành

### Bài 1 — Thiết kế policy field

Một API đăng nhập nhận username, password, OTP và device ID.

Hãy đề xuất:

- Các event nên ghi.
- Failure code có thể dùng.
- Request context an toàn.
- Những field tuyệt đối không được log.
- Mức log phù hợp cho đăng nhập thành công, thất bại và lỗi hệ thống.

Giải thích tại sao username hoặc device ID không mặc định cần xuất hiện trong log.

### Bài 2 — Tìm lỗi trong logger

Cho:

```java
log.info("Login request: {}", loginRequest);
log.debug("Token: {}", accessToken);
log.error("Request failed: {}", request.getRequestURI());
```

Hãy thay chúng bằng các log sử dụng event name, failure code, route template và request ID. Không dùng raw request body, token hoặc URL chứa path động.

### Bài 3 — Tạo servlet correlation filter

Viết `OncePerRequestFilter` để:

1. Tạo request ID ở server.
2. Gắn request ID vào MDC.
3. Đặt header response `X-Request-ID`.
4. Xóa MDC trong `finally`.

Sau đó tạo controller và service cùng in log. Xác nhận các dòng log từ một request có cùng ID.

### Bài 4 — Kiểm tra thread reuse

Thử bỏ lệnh `MDC.remove("requestId")` trong một bài demo và gửi nhiều request qua thread pool. Quan sát nguy cơ context cũ bị giữ lại.

Sau khi hiểu hiện tượng, khôi phục cleanup; không để code thiếu cleanup tồn tại trong ứng dụng thật.

### Bài 5 — Ngữ cảnh với `@Async`

Tạo một async service và kiểm tra log trong thread mới có `requestId` không.

Sau đó cấu hình `TaskDecorator` để truyền MDC và khôi phục context trong `finally`.

Giải thích vì sao sao chép một field context không có nghĩa phải sao chép toàn bộ thông tin người dùng.

### Bài 6 — Request URI và route template

Tạo endpoint:

```text
GET /api/users/{userId}/orders
```

Gửi request với một giá trị `userId` giả lập. So sánh `request.getRequestURI()` với `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE`.

Giải thích vì sao route template phù hợp hơn để làm field log và metric label.

### Bài 7 — Exception và log trùng

Tạo một exception được ném từ repository, đi qua service rồi đến `@RestControllerAdvice`.

Đầu tiên thử log stack trace ở cả ba tầng. Sau đó chuyển sang một nơi chịu trách nhiệm ghi lỗi chính và dùng failure code ở nơi cần thiết.

So sánh số dòng log và độ dễ tìm nguyên nhân gốc.

### Bài 8 — Structured logging

Thiết kế một JSON event cho:

```text
payment.authorize.failed
```

Chỉ dùng các field như `event`, `requestId`, `failureCode`, `dependency`, `durationMs` và một operation reference không nhạy cảm. Không đưa số thẻ, token hoặc raw response vào JSON.

### Bài 9 — Trace qua hai service

Giả lập `order-service` gọi `inventory-service`. Sử dụng tracing instrumentation được dự án hỗ trợ để có cùng trace ID và các span IDs riêng.

Tìm log của hai service bằng trace ID, sau đó giải thích sự khác biệt giữa trace ID, span ID và một request ID được tạo cục bộ.

### Bài 10 — SQL logging an toàn

Tạo truy vấn bằng prepared statement hoặc ORM với một điều kiện theo email giả lập. Kiểm tra cấu hình SQL statement logging và parameter binding logging.

Xác định tại sao bật TRACE cho bind parameters có thể làm lộ giá trị nhạy cảm dù SQL statement dùng dấu `?`.

### Bài 11 — Cấu hình retention

Thiết kế chính sách lưu log riêng cho application logs, access logs và security audit logs. Nêu:

- Mục đích.
- Field được phép.
- Nhóm có quyền truy cập.
- Thời gian lưu cần được phê duyệt.
- Cách export và xử lý sự cố lộ secret.

Không dùng chung một retention policy chỉ vì cả ba đều có tên là “log”.

### Bài 12 — Xây kế hoạch chẩn đoán production

Một khách hàng báo lỗi với request ID. Hãy mô tả cách:

1. Tìm log theo ID.
2. Xem event/failure code/status/duration.
3. Liên kết trace tới service phụ thuộc.
4. So sánh metric lỗi theo route.
5. Thu thập đủ thông tin kỹ thuật mà không yêu cầu khách hàng gửi mật khẩu, OTP hoặc access token.

## 26. Ghi nhớ

**Log phải cung cấp đủ ngữ cảnh để vận hành mà không sao chép dữ liệu nhạy cảm.** Thường nên ghi event name, failure code, route template, status code, duration và correlation ID. Không ghi nguyên password, token, cookie, payment details, request/response body hoặc những dữ liệu cá nhân không cần thiết.

Trong Spring Boot, SLF4J/Logback và MDC giúp gắn request context vào log; nhưng MDC cần được cleanup khi thread được tái sử dụng và phải được propagate có kiểm soát qua executor hoặc các asynchronous boundary. Với WebFlux, Reactor Context và tracing context propagation cần được xử lý đúng theo mô hình reactive.

Request ID giúp tìm log của một request; trace/span IDs hỗ trợ liên kết giữa các service. Các ID này **không phải credential** và không thay thế authentication/authorization. Structured logging giúp tìm kiếm tốt hơn nhưng không tự loại bỏ secret.

Khi thiết kế logging cho production, hãy áp dụng nguyên tắc **allowlist field, giảm dữ liệu, một nơi chịu trách nhiệm ghi lỗi, retention phù hợp và phân quyền truy cập log**. Một dòng log tốt cho phép người vận hành hiểu điều gì xảy ra mà không cần đọc thông tin riêng tư hoặc bí mật của người dùng.
