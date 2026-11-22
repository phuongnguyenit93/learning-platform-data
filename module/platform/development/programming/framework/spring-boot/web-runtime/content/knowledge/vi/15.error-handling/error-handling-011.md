# Thống nhất cấu trúc lỗi, mã nghiệp vụ và mã tương quan trong Spring Boot

## 1. Bài toán: cùng một lỗi phải hiểu được ở cả client, server và hệ thống giám sát

Một ứng dụng Spring Boot có thể trả lỗi từ nhiều nơi: controller, Bean Validation, Spring Security, tầng service/domain, dữ liệu không tồn tại, HTTP client gọi sang dịch vụ khác, filter, Servlet container hoặc reactive web server. Nếu mỗi nơi trả một JSON khác nhau, client phải viết nhiều nhánh xử lý và đội vận hành khó nối một thông báo lỗi của người dùng với log tương ứng.

Ví dụ các response thiếu thống nhất:

~~~json
{"message":"Bad request"}
~~~

~~~json
{"error":"No stock","status":409,"time":"..."}
~~~

~~~json
{"success":false,"errorCode":1012,"reason":"Database unavailable"}
~~~

Ba response này không có cùng trường xác định lỗi, có thể dùng HTTP status và mã nội bộ khác nhau, và không mang thông tin liên hệ với server logs. Đối với lỗi xảy ra ở nhiều microservice, việc chẩn đoán trở nên đặc biệt khó.

Một **hợp đồng lỗi thống nhất** cần trả lời được:

- Lỗi thuộc nhóm HTTP nào? Mã HTTP status thực tế có đúng không?
- Lỗi nghiệp vụ là gì, với một **mã máy đọc ổn định** không phụ thuộc ngôn ngữ thông báo?
- Người dùng hoặc client nên làm gì để khắc phục?
- Nếu cần hỗ trợ, dùng **mã tương quan** nào để tìm cùng request trong logs?
- Nếu đang có distributed tracing, trace ID/span ID liên hệ với request ra sao?
- Những thông tin nào có thể an toàn công khai, những gì phải giữ trong logs?
- Lỗi từ @Valid, @RequestParam, service, HTTP 404, 500 hoặc WebFlux có đi về cùng schema không?
- Kết quả có dễ kiểm thử, tài liệu hóa và phát triển mà không phá vỡ client cũ không?

Spring Framework 6.x có hỗ trợ sẵn **ProblemDetail** theo **RFC 9457 – Problem Details for HTTP APIs** (thay thế RFC 7807). Đây là nền tảng phù hợp để biểu diễn các lỗi HTTP, còn mã nghiệp vụ và correlation ID có thể được thêm dưới dạng extension fields.

Mục tiêu không phải ép mọi exception thành HTTP 200 hay HTTP 400, mà là **giữ đúng HTTP semantics** và cung cấp nội dung lỗi có cấu trúc để cả client và người vận hành sử dụng.

## 2. Phân biệt ba loại mã: HTTP status, business error code và correlation ID

| Thành phần | Ví dụ | Dùng để làm gì? | Tính ổn định |
|---|---|---|---|
| HTTP status | 400, 404, 409, 429, 500, 503 | Cho HTTP client, proxy, gateway và monitoring biết lớp kết quả | Theo HTTP specification; cần chính xác |
| Business error code | PRODUCT_NOT_FOUND, INSUFFICIENT_STOCK | Cho client rẽ nhánh theo trường hợp lỗi nghiệp vụ | Phải có contract, duy trì ổn định |
| Correlation ID | req-8f32a62e, UUID | Tìm toàn bộ log hoặc request liên quan tới một giao dịch | Thường thay đổi theo request/interaction |
| Trace ID | 32 ký tự hex trong W3C traceparent | Tìm toàn bộ distributed trace qua nhiều dịch vụ | Thay đổi theo trace |
| Span ID | 16 ký tự hex | Xác định một đơn vị hoạt động trong trace | Thay đổi theo span |
| Problem type URI | https://api.example.com/problems/insufficient-stock | Mô tả loại vấn đề và tài liệu xử lý | Ổn định theo loại vấn đề |

**HTTP status** trả lời “request này thành công hay thất bại theo giao thức?”. **Business code** trả lời “đang gặp loại lỗi sản phẩm nào?”. **Correlation ID** trả lời “đây là lần xử lý nào cần tìm trong logs?”. Ba vai trò không thay thế lẫn nhau.

Ví dụ: có 10.000 lần gọi POST đặt hàng không đủ tồn kho. Chúng có thể cùng HTTP 409 và business code INSUFFICIENT_STOCK, nhưng mỗi lần sẽ có correlation ID khác nhau. Không dùng correlation ID làm mã nghiệp vụ, cũng không dùng business code như một request ID.

### 2.1. Không trả HTTP 200 với body chứa lỗi

Ví dụ sau là thiết kế không tốt cho REST API thông thường:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"success":false,"code":"PRODUCT_NOT_FOUND"}
~~~

HTTP 200 khiến proxy, retries, cache, client SDK, SLO và monitoring có thể coi request thành công. Nếu resource không tồn tại, nên dùng HTTP 404 tương ứng. Nếu API là một protocol riêng chạy trên HTTP và có quy ước khác, cần giải thích rõ, nhưng không nên áp dụng tùy tiện vào một REST API.

### 2.2. Không dựa vào message để rẽ nhánh chương trình

Client không nên viết if (message.equals("Không tìm thấy sản phẩm")) hoặc tìm substring trong detail. Thông báo có thể được dịch sang tiếng Anh, đổi cách diễn đạt hoặc chứa thông tin theo request.

Nên sử dụng code hoặc type URI:

~~~text
if (error.code == "PRODUCT_NOT_FOUND"):
    hiển thị trạng thái không có sản phẩm
else if (error.code == "INSUFFICIENT_STOCK"):
    đề nghị giảm số lượng mua
else:
    hiển thị lỗi chung và correlationId
~~~

Đây là pseudocode, không phải mã JavaScript hoàn chỉnh. Các mã có chữ in hoa chỉ là convention minh họa; có thể dùng chuỗi có namespace như INVENTORY.INSUFFICIENT_STOCK nếu công ty quản lý bằng catalog chung.

## 3. RFC 9457 và application/problem+json

RFC 9457 định nghĩa cấu trúc Problem Details cho HTTP APIs. Spring Framework dùng class org.springframework.http.ProblemDetail cùng các abstraction ErrorResponse và ErrorResponseException.

Một ví dụ phản hồi:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
X-Correlation-ID: req-8f32a62e

{
  "type": "https://api.example.com/problems/insufficient-stock",
  "title": "Conflict",
  "status": 409,
  "detail": "Số lượng yêu cầu vượt tồn kho khả dụng.",
  "instance": "urn:uuid:3a82b5af-8a9e-434a-ab68-ae96d51ce4b7",
  "code": "INSUFFICIENT_STOCK",
  "correlationId": "req-8f32a62e"
}
~~~

Đây là response mẫu minh họa hợp đồng, không phải output được framework bảo đảm từ mọi project. Host api.example.com là placeholder tài liệu, cần đổi sang miền mà dự án thực sự quản lý và công bố các problem types.

### 3.1. Năm trường chuẩn

| Trường RFC 9457 | Ý nghĩa | Lưu ý |
|---|---|---|
| type | URI reference xác định **loại vấn đề** | Ưu tiên URI ổn định, có tài liệu; mặc định about:blank nếu không có type riêng |
| title | Mô tả ngắn của **loại vấn đề** | Nên ổn định giữa các lần gặp cùng type, trừ localization |
| status | HTTP status code của response | Nếu có mặt, phải phù hợp mã trạng thái HTTP thực tế; dùng cho thông tin |
| detail | Giải thích theo từng lần gặp lỗi, hướng tới người dùng/client | Không chứa stack trace, SQL, secrets hoặc nội dung máy phải parse |
| instance | URI reference xác định **lần xảy ra lỗi cụ thể** | Có thể là opaque URI không dereference được; tránh lộ dữ liệu cá nhân |

Không dùng instance như một trường bắt buộc phải chứa request path. RFC 9457 định nghĩa instance là tham chiếu tới **lần lỗi**; một số phiên bản Spring trước đây tự gán current request path nếu thiếu, nhưng các phiên bản mới có thể thay hành vi. Nếu cần định danh duy nhất cho occurrence, có thể chủ động dùng URN UUID hoặc URI định danh lỗi do ứng dụng quản lý.

Không đưa query string chứa email, token, mật khẩu hay nội dung tìm kiếm nhạy cảm vào instance chỉ vì muốn thuận tiện debug.

### 3.2. Extension fields cho mã nghiệp vụ và correlation

RFC cho phép mở rộng Problem Details bằng các member khác. Với Spring ProblemDetail:

~~~java
ProblemDetail problem =
        ProblemDetail.forStatus(HttpStatus.CONFLICT);

problem.setTitle("Conflict");
problem.setDetail("Số lượng yêu cầu vượt tồn kho khả dụng.");
problem.setProperty("code", "INSUFFICIENT_STOCK");
problem.setProperty("correlationId", "req-8f32a62e");
~~~

Đây là snippet cần import ProblemDetail và HttpStatus, đặt trong class hoặc method Java phù hợp. Với Jackson và cấu hình Spring thông thường, entries trong ProblemDetail.properties được đưa lên cấp đầu của JSON, không bị lồng bắt buộc trong một object "properties".

Một số extension hữu ích:

- code: mã lỗi nghiệp vụ ổn định.
- correlationId: ID để client gửi cho bộ phận hỗ trợ.
- errors: danh sách vi phạm validation, mỗi phần tử có field và rule.
- retryable: có thể thêm nếu hợp đồng xác định chính xác; không nên thay HTTP Retry-After.
- documentation: URL đến tài liệu lỗi nếu type URI chưa phục vụ mục tiêu này.

Không thêm tất cả extension vào mọi response một cách thừa thãi. Một lỗi 500 có thể chỉ cần code tổng quát, thông báo an toàn và correlationId; không nên tiết lộ stack trace hoặc tên cơ sở dữ liệu.

### 3.3. Content-Type

Khi dùng ProblemDetail/ErrorResponse đúng cách trong Spring MVC/WebFlux, framework ưu tiên media type **application/problem+json** với Jackson. Không tự trả một String JSON bằng tay rồi gắn Content-Type tùy tiện, vì dễ làm status/body không đồng nhất hoặc mất content negotiation.

Nếu client gửi Accept không tương thích, hệ thống có thể gặp 406 hoặc thực hiện content negotiation theo cấu hình. Hãy kiểm thử media type và headers với client thực.

## 4. Thiết kế catalog mã lỗi nghiệp vụ

Một bộ mã lỗi tốt nên có tên ổn định, ý nghĩa rõ, status mapping nhất quán, loại dữ liệu an toàn được trả về và hành động client có thể thực hiện.

| Business code | HTTP status | Ý nghĩa | Hướng xử lý |
|---|---:|---|---|
| VALIDATION_FAILED | 400 | Dữ liệu đầu vào vi phạm schema/constraint | Client sửa field theo errors |
| MALFORMED_REQUEST | 400 | Body/query sai định dạng, không parse được | Sửa request format |
| AUTHENTICATION_REQUIRED | 401 | Chưa xác thực hợp lệ | Đăng nhập hoặc refresh token theo flow |
| ACCESS_DENIED | 403 | Đã biết principal nhưng không có quyền | Không retry y nguyên để tăng quyền |
| PRODUCT_NOT_FOUND | 404 | Resource sản phẩm không tồn tại hoặc không được lộ | Kiểm tra ID hoặc UI empty state |
| INSUFFICIENT_STOCK | 409 | Trạng thái tồn kho xung đột với yêu cầu | Giảm số lượng / lấy tồn kho mới |
| RESOURCE_VERSION_CONFLICT | 409 | Cập nhật khi version không còn phù hợp | Refresh và giải quyết xung đột |
| PRECONDITION_FAILED | 412 | If-Match hoặc precondition không thỏa | Lấy phiên bản mới, kiểm tra ETag |
| RATE_LIMITED | 429 | Vượt quota/rate limit | Backoff theo Retry-After khi có |
| DEPENDENCY_UNAVAILABLE | 503 | Dependency thiết yếu tạm không đáp ứng | Retry có giới hạn khi an toàn |
| INTERNAL_ERROR | 500 | Lỗi không dự kiến, không thể công bố chi tiết | Hiển thị lỗi chung và correlation ID |

Bảng là **thiết kế ví dụ**, không có nghĩa mọi dự án đều bắt buộc dùng chính các mã này. Ví dụ nghiệp vụ tồn kho có thể dùng 422 nếu hợp đồng coi số lượng không hợp lệ về nghiệp vụ; 409 phù hợp nếu đó là xung đột trạng thái tài nguyên hiện hành. Chọn cách diễn giải nhất quán, giải thích trong OpenAPI và giữ ổn định.

### 4.1. Một HTTP status có thể có nhiều business codes

HTTP 404 có thể tương ứng PRODUCT_NOT_FOUND, ORDER_NOT_FOUND hoặc CUSTOMER_NOT_FOUND. HTTP 409 có thể tương ứng INSUFFICIENT_STOCK hoặc RESOURCE_VERSION_CONFLICT. Business code cung cấp phân loại cụ thể hơn, trong khi status giữ ngữ nghĩa chuẩn cho hạ tầng HTTP.

Ngược lại, không dùng cùng mã nghiệp vụ cho hai hành vi hoàn toàn khác nhau trừ khi đó là contract cố ý. Với một mã như ORDER_NOT_FOUND, nên xác định rõ status, detail an toàn và các trường có thể có.

### 4.2. Không dùng số lỗi ngẫu nhiên không có catalog

Mã như 1001, 1002, 1003 vẫn có thể dùng, nhưng cần một registry và phạm vi tránh xung đột. Tên ký hiệu có namespace (ví dụ INVENTORY.INSUFFICIENT_STOCK) thường dễ đọc khi debug. Nếu API đã công bố numeric codes, không thay đổi sang string codes một cách breaking mà không versioning và kế hoạch migration.

Đừng gắn thông tin nhạy cảm vào code: mã nghiệp vụ nên có cardinality hữu hạn và không chứa email, username, product ID hoặc token.

### 4.3. Message và localization

Có thể giữ code=INSUFFICIENT_STOCK ổn định và trả detail theo ngôn ngữ:

~~~json
{
  "code": "INSUFFICIENT_STOCK",
  "detail": "Số lượng yêu cầu vượt tồn kho khả dụng."
}
~~~

Hoặc theo Accept-Language="en":

~~~json
{
  "code": "INSUFFICIENT_STOCK",
  "detail": "Requested quantity exceeds available stock."
}
~~~

Đây là hai đoạn minh họa các trường. Spring ErrorResponse có MessageSource message codes cho type/title/detail, hoặc ứng dụng có thể chủ động dùng resource bundles. **Client không parse detail để quyết định logic**. Khi support đa ngôn ngữ, code và HTTP status giữ nguyên.

## 5. Correlation ID khác W3C Trace Context

Một hệ thống có thể vừa có X-Correlation-ID vừa có traceparent. Chúng liên quan nhưng không đồng nhất.

**Correlation ID** là định danh tùy hợp đồng ứng dụng dùng để tìm request hoặc chuỗi thao tác trong logs. Header có thể là X-Correlation-ID hoặc X-Request-ID; không có một cách đặt tên duy nhất bắt buộc trong mọi REST API.

**Trace ID** là thành phần của hệ thống distributed tracing, được truyền theo W3C Trace Context. Header traceparent có cấu trúc theo phiên bản 00:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Trong đó:
- 00 là version.
- 4bf92f3577b34da6a3ce929d0e0e4736 là trace-id 32 ký tự hex (không toàn 0).
- 00f067aa0ba902b7 là parent-id/span-id 16 ký tự hex (không toàn 0).
- 01 là trace flags, có sampled bit được đặt theo đặc tả.

Một client không nên tự sửa ngẫu nhiên traceparent mà không hiểu tiêu chuẩn; ưu tiên OpenTelemetry, Micrometer Tracing hoặc thư viện instrumentation tương ứng. tracestate có thể mang context của vendor, cần kiểm soát giới hạn và bảo mật.

### 5.1. Trace ID có thể làm correlation ID không?

Có thể **chủ động** chọn trace ID làm định danh tra cứu nếu toàn hệ thống có tracing thống nhất, quy tắc sampling và log correlation đã phù hợp. Nhưng đừng mặc định chúng luôn bằng nhau.

Một correlation ID có thể đến từ API Gateway hoặc request được người dùng gửi. Một trace có thể kéo qua nhiều request hoặc nhiều spans; một request có thể thuộc trace đã tồn tại. Nếu tracing bị vô hiệu hóa, không có tracing context hoặc ID bị reset, correlation ID độc lập vẫn hữu ích.

Không tự coi mọi chuỗi header X-Correlation-ID là một trace-id hợp lệ theo W3C format; định dạng và ý nghĩa khác nhau.

### 5.2. Mã lỗi nghiệp vụ và correlation ID cần ở cả header lẫn body?

Một quy ước dễ sử dụng:

- Server trả X-Correlation-ID trong HTTP response header, cả khi thành công.
- Với response lỗi, cũng đưa correlationId vào ProblemDetail để client có thể hiển thị hoặc gửi cho support.
- Logs có trường correlationId tương ứng.
- Nếu có tracing, logs còn có traceId/spanId do instrumentation cung cấp; không nhất thiết đưa toàn bộ span metadata ra response.

Client có thể ghi lại response status, business code, correlationId, thời điểm và endpoint (không lưu secrets). Hệ thống logs dùng correlationId để truy vấn một cách nhất quán.

## 6. Quy tắc sinh, nhận và truyền correlation ID

Một chính sách đơn giản, rõ ràng:

1. Tại một trusted ingress/gateway, kiểm tra correlation header incoming.
2. Nếu không có hoặc giá trị không hợp lệ, sinh một ID mới.
3. Giới hạn độ dài, bộ ký tự và số lượng header; không cho CR/LF hoặc các ký tự gây log injection.
4. Lưu ID trong request context; đưa vào log context.
5. Trả lại trong response header và error body.
6. Khi gửi HTTP request downstream, truyền correlation ID theo chính sách toàn hệ thống.
7. Trên mỗi downstream, không tự đổi ID trong một chuỗi giao dịch nếu contract yêu cầu giữ cùng ID.
8. Khi rời trust boundary, không mù quáng tin header do client bên ngoài gửi làm định danh nội bộ hoặc khóa bảo mật.

Định dạng ví dụ: [A-Za-z0-9._-]{8,64}, hoặc chỉ dùng UUID nếu hệ thống kiểm soát toàn bộ ID. Đây là chính sách minh họa, không phải tiêu chuẩn bắt buộc. Việc chấp nhận một ID hợp lệ về cú pháp **không chứng minh nó đáng tin**: client bên ngoài có thể cố tình dùng ID giống người khác. Với API Internet public, một lựa chọn an toàn hơn là luôn cấp ID do gateway/server sở hữu và lưu inbound ID chưa tin cậy ở field khác, nếu thật sự cần.

Đừng đặt email, access token, số tài khoản, địa chỉ IP hoặc username làm correlation ID. ID nên là định danh opaque có entropy phù hợp, không mang dữ liệu nhạy cảm.

### 6.1. Mã tương quan không phải idempotency key

Trong thanh toán hoặc API tạo đơn hàng, correlation ID chỉ hỗ trợ truy vết. **Idempotency-Key** được thiết kế để tránh xử lý trùng một thao tác khi retry, với kho lưu và quy tắc deduplication. Không dùng correlation ID thay cho Idempotency-Key trừ khi hệ thống đã có hợp đồng và kiểm soát đúng semantics, TTL, phạm vi chủ thể và payload.

Một request được retry có thể có correlation ID mới hoặc được giữ nguyên theo chính sách tracing, nhưng deduplication không được phụ thuộc vào sự lựa chọn ngẫu nhiên đó.

## 7. Tích hợp trong Spring Boot MVC bằng Java 17+

Ví dụ minh họa chạy trên **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+, Spring MVC/Servlet và embedded Tomcat**. Nó sử dụng:
- ProblemDetail theo RFC 9457.
- ErrorCode enum làm catalog business codes.
- BusinessException chỉ mang mã lỗi nghiệp vụ.
- OncePerRequestFilter sinh hoặc nhận correlation ID và ghi vào SLF4J MDC.
- @RestControllerAdvice kế thừa ResponseEntityExceptionHandler để chuẩn hóa phần lớn lỗi trong annotated MVC controller.
- MockMvc kiểm tra contract và correlation ID.

Các phiên bản mới hơn có thể thay đổi vài hook hoặc behavior mặc định; đối chiếu đúng Javadoc của Spring Framework được quản lý bởi project. Đặc biệt không giả định việc bật Problem Details sẽ khiến mọi response từ Servlet container, /error, gateway và security filter đều tự có schema giống nhau.

### 7.1. Dependencies và cấu trúc project

Trong một project Gradle đã có Spring Boot plugin và Maven Central (ví dụ project do Spring Initializr tạo), dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Các dependency trên đủ cho MVC, JSON/Jackson, SLF4J và Bean Validation trong demo Boot 3.3 thông thường. Không thêm spring-boot-starter-webflux vào project này chỉ để chạy một WebClient; ví dụ reactive riêng có ở phần sau.

Sắp xếp file:

~~~text
src/main/java/dev/example/errors/
    ErrorDemoApplication.java
    ErrorCode.java
    BusinessException.java
    CorrelationIdFilter.java
    ApiErrorAdvice.java
    ProductController.java
src/main/resources/application.yml
src/test/java/dev/example/errors/
    ErrorContractTest.java
~~~

### 7.2. Main class

File src/main/java/dev/example/errors/ErrorDemoApplication.java:

~~~java
package dev.example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorDemoApplication.class, args);
    }
}
~~~

Các class còn lại đặt cùng package dev.example.errors nên được component scan phát hiện.

### 7.3. Catalog mã nghiệp vụ

File src/main/java/dev/example/errors/ErrorCode.java:

~~~java
package dev.example.errors;

import org.springframework.http.HttpStatus;

public enum ErrorCode {

    PRODUCT_NOT_FOUND(
            HttpStatus.NOT_FOUND,
            "Không tìm thấy sản phẩm."),

    INSUFFICIENT_STOCK(
            HttpStatus.CONFLICT,
            "Số lượng yêu cầu vượt tồn kho khả dụng.");

    private final HttpStatus status;
    private final String safeDetail;

    ErrorCode(HttpStatus status, String safeDetail) {
        this.status = status;
        this.safeDetail = safeDetail;
    }

    public HttpStatus status() {
        return status;
    }

    public String safeDetail() {
        return safeDetail;
    }
}
~~~

ErrorCode có mapping từ mã nghiệp vụ sang HTTP status và thông điệp an toàn. Trong dự án thật có thể thêm i18n message key, documentation URI, retry policy và versioning policy. Không đưa exception message kỹ thuật từ database trực tiếp vào safeDetail.

### 7.4. BusinessException

File src/main/java/dev/example/errors/BusinessException.java:

~~~java
package dev.example.errors;

public final class BusinessException extends RuntimeException {

    private final ErrorCode errorCode;

    public BusinessException(ErrorCode errorCode) {
        super(errorCode.safeDetail());
        this.errorCode = errorCode;
    }

    public ErrorCode errorCode() {
        return errorCode;
    }
}
~~~

Exception này đại diện lỗi có chủ đích theo domain/catalog, khác với NullPointerException, SQLException hoặc một lỗi lập trình không dự kiến. Việc mang mã ổn định giúp controller advice quyết định status và response không phải phân tích chuỗi thông báo exception.

### 7.5. CorrelationIdFilter cho Servlet MVC

File src/main/java/dev/example/errors/CorrelationIdFilter.java:

~~~java
package dev.example.errors;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class CorrelationIdFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Correlation-ID";
    public static final String ATTRIBUTE = "correlationId";

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{8,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String proposed = request.getHeader(HEADER);
        String correlationId = proposed != null
                && SAFE_ID.matcher(proposed).matches()
                ? proposed
                : UUID.randomUUID().toString();

        request.setAttribute(ATTRIBUTE, correlationId);
        response.setHeader(HEADER, correlationId);

        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable(ATTRIBUTE, correlationId)) {
            chain.doFilter(request, response);
        }
    }
}
~~~

Đây là class hợp lệ cho Servlet stack với Spring Boot 3.x/Jakarta Servlet. Filter đặt ID vào Servlet request attribute và response header **trước** khi MVC xử lý, nên controller advice có thể đọc lại cùng ID. MDC.putCloseable giúp xóa giá trị khỏi thread context sau request để không rò sang tác vụ khác trên thread pool.

**Giới hạn quan trọng:** snippet chấp nhận ID incoming nếu hợp lệ về format; điều này phù hợp trong môi trường demo hoặc khi ingress đáng tin đã xác thực/đặt lại header. Với endpoint public, nên cân nhắc luôn sinh internal correlation ID hoặc chỉ tin header do trusted proxy đưa vào. Filter không tự xác minh nguồn header.

Servlet async dispatch và error dispatch có thể chạy trên các thread/dispatch khác với request ban đầu. OncePerRequestFilter có các hành vi mặc định khi async/error dispatch; MDC chỉ gắn với thread trong đoạn try và **không tự lan qua CompletableFuture, thread pool hoặc reactive pipeline**. Production cần integration với context propagation/observability và test cả async/error flows. Việc set response header sớm giúp ID tồn tại trong nhiều đường lỗi, nhưng không bảo đảm mọi lỗi ngoài Servlet MVC đã có cùng JSON body.

### 7.6. RestControllerAdvice chuẩn hóa ProblemDetail

File src/main/java/dev/example/errors/ApiErrorAdvice.java:

~~~java
package dev.example.errors;

import java.net.URI;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.ServletWebRequest;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiErrorAdvice extends ResponseEntityExceptionHandler {

    public record FieldIssue(String field, String rule) {}

    @ExceptionHandler(BusinessException.class)
    protected ResponseEntity<Object> handleBusiness(
            BusinessException ex, WebRequest request) {

        ProblemDetail problem =
                ProblemDetail.forStatus(ex.errorCode().status());

        problem.setDetail(ex.errorCode().safeDetail());
        problem.setProperty("code", ex.errorCode().name());

        return handleExceptionInternal(
                ex, problem, new HttpHeaders(),
                ex.errorCode().status(), request);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatus(status);
        problem.setDetail("Dữ liệu gửi lên không hợp lệ.");
        problem.setProperty("code", "VALIDATION_FAILED");

        List<FieldIssue> issues = ex.getBindingResult()
                .getFieldErrors().stream()
                .map(error -> new FieldIssue(
                        error.getField(),
                        error.getCode() == null
                                ? "Invalid"
                                : error.getCode()))
                .toList();

        problem.setProperty("errors", issues);

        return handleExceptionInternal(
                ex, problem, headers, status, request);
    }

    @ExceptionHandler(Exception.class)
    protected ResponseEntity<Object> handleUnexpected(
            Exception ex, WebRequest request) {

        logger.error("Unhandled request exception", ex);

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);

        problem.setDetail(
                "Hệ thống không thể xử lý yêu cầu. "
                + "Hãy cung cấp mã tương quan khi liên hệ hỗ trợ.");
        problem.setProperty("code", "INTERNAL_ERROR");

        return handleExceptionInternal(
                ex, problem, new HttpHeaders(),
                HttpStatus.INTERNAL_SERVER_ERROR, request);
    }

    @Override
    protected ResponseEntity<Object> createResponseEntity(
            Object body,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = body instanceof ProblemDetail pd
                ? pd
                : ProblemDetail.forStatus(status);

        if (problem.getProperties() == null
                || !problem.getProperties().containsKey("code")) {
            problem.setProperty(
                    "code",
                    status.is5xxServerError()
                            ? "INTERNAL_ERROR"
                            : "HTTP_" + status.value());
        }

        if (status.is5xxServerError()) {
            problem.setDetail(
                    "Hệ thống không thể xử lý yêu cầu. "
                    + "Hãy cung cấp mã tương quan khi liên hệ hỗ trợ.");
        }

        String correlationId = UUID.randomUUID().toString();

        if (request instanceof ServletWebRequest servletRequest) {
            Object value = servletRequest.getRequest()
                    .getAttribute(CorrelationIdFilter.ATTRIBUTE);

            if (value instanceof String saved) {
                correlationId = saved;
            }
        }

        problem.setProperty("correlationId", correlationId);
        headers.set(CorrelationIdFilter.HEADER, correlationId);

        // Instance định danh một lần xảy ra lỗi, không dùng raw query.
        problem.setInstance(
                URI.create("urn:uuid:" + UUID.randomUUID()));

        if ("about:blank".equals(problem.getType().toString())) {
            String code = (String) problem.getProperties().get("code");
            problem.setType(URI.create(
                    "https://api.example.com/problems/"
                    + code.toLowerCase(Locale.ROOT)
                          .replace('_', '-')));
        }

        return super.createResponseEntity(
                problem, headers, status, request);
    }
}
~~~

Ví dụ này tập trung vào **một hợp đồng lỗi**, không phải toàn bộ các loại exception có thể phát sinh trong hệ thống. Lớp extends ResponseEntityExceptionHandler để chuẩn hóa các lỗi framework được nó hỗ trợ; @ExceptionHandler(BusinessException.class) xử lý lỗi domain; @ExceptionHandler(Exception.class) là fallback cho các exception chưa có handler cụ thể trong MVC controller.

Một số điểm quan trọng:

1. ProblemDetail.forStatus(...) tạo status phù hợp; HTTP status trả thực tế được lấy từ ResponseEntity. Không tự đặt body.status=400 nhưng trả HTTP 200.
2. createResponseEntity là hook của ResponseEntityExceptionHandler, được dùng để thêm code, correlationId và instance vào nhiều lỗi đã qua cơ chế MVC exception handling.
3. Nếu đã có business code, không bị ghi đè bởi mã generic HTTP_400.
4. Validation errors chỉ chứa field và rule; **không trả rejectedValue** (có thể chứa mật khẩu, token hoặc dữ liệu cá nhân).
5. 5xx nhận detail tổng quát, không lộ thông tin exception.
6. correlationId được lấy từ request attribute do filter cung cấp, vì vậy response header và body có cùng ID ở đường đi bình thường.
7. instance dùng URN UUID mới cho từng occurrence, không sao chép request URL chứa query nhạy cảm.
8. type URI dùng miền placeholder api.example.com; trong production thay bằng URI ổn định thuộc hệ thống và công bố tài liệu problem type. Không được quảng cáo placeholder là endpoint đang tồn tại.

**Thận trọng với fallback:** một @RestControllerAdvice không tự bắt mọi lỗi từ Servlet Filter chạy trước DispatcherServlet, container error dispatch, lỗi từ API Gateway hay response đã committed. Muốn thống nhất ở mức toàn hệ thống, cần thêm cơ chế tương ứng ở từng boundary và test chúng, như phần 11.

**Thận trọng với logging:** logger.error(..., ex) giúp điều tra nhưng cần chính sách mask dữ liệu nhạy cảm, log retention và quyền truy cập. Không tự động in raw request body, Authorization header, cookie phiên hoặc thông tin cá nhân vào exception logs.

### 7.7. Controller minh họa lỗi domain và validation

File src/main/java/dev/example/errors/ProductController.java:

~~~java
package dev.example.errors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    public record Product(long id, String name) {}

    public record ReserveRequest(
            @NotBlank String sku,
            @NotNull @Min(1) Integer quantity) {}

    public record Reservation(String sku, int quantity) {}

    @GetMapping("/{id}")
    public Product find(@PathVariable long id) {
        if (id != 1L) {
            throw new BusinessException(ErrorCode.PRODUCT_NOT_FOUND);
        }

        return new Product(1L, "Mechanical keyboard");
    }

    @PostMapping("/reserve")
    public ResponseEntity<Reservation> reserve(
            @Valid @RequestBody ReserveRequest request) {

        if (request.quantity() > 5) {
            throw new BusinessException(
                    ErrorCode.INSUFFICIENT_STOCK);
        }

        Reservation reservation = new Reservation(
                request.sku(), request.quantity());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(reservation);
    }
}
~~~

Trong demo, sản phẩm ID=1 được coi là tồn tại và tồn kho tối đa 5 đơn vị. Đây chỉ là logic mô phỏng để minh họa HTTP status và business code, không phải một thuật toán quản lý tồn kho dùng được trong production. Ở sản phẩm thật, việc kiểm tra và giữ tồn kho phải bảo đảm concurrency, transaction và idempotency phù hợp.

### 7.8. application.yml

File src/main/resources/application.yml:

~~~yaml
server:
  port: 8080

spring:
  mvc:
    problemdetails:
      enabled: false

logging:
  pattern:
    level: "%5p [corr:%X{correlationId:-}]"
~~~

Ở đây project **chủ động** cung cấp ApiErrorAdvice extends ResponseEntityExceptionHandler nên đặt spring.mvc.problemdetails.enabled=false để tránh đồng thời dựa vào auto-configured ResponseEntityExceptionHandler của Boot. Nếu chỉ muốn mặc định framework trả ProblemDetail cho các web exceptions, có thể bật spring.mvc.problemdetails.enabled=true và dùng advice riêng được sắp thứ tự phù hợp để bổ sung các lỗi nghiệp vụ.

Cấu hình Logback/SLF4J format minh họa trường MDC correlationId. Trong production, ưu tiên structured JSON logs có các field riêng code, status, correlationId, traceId, spanId, serviceName, environment và timestamp, thay vì parse một chuỗi text tùy ý.

Khi sử dụng tracing auto-configuration, không thêm hai cơ chế sinh trace ID độc lập. Nếu hệ thống đã có traceId trong logs, correlationId là field bổ sung theo contract của API.

## 8. Chạy demo và kiểm tra từng trường hợp

Từ thư mục dự án có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

### 8.1. Success response có header

~~~bash
curl -i http://localhost:8080/api/products/1
~~~

HTTP 200 với JSON body mô phỏng:

~~~json
{"id":1,"name":"Mechanical keyboard"}
~~~

Response header X-Correlation-ID có một ID do filter tạo hoặc tiếp nhận. Không cần đưa code lỗi vào body của response thành công; điều đó không phải một problem response.

### 8.2. Business error 404

~~~bash
curl -i -H "X-Correlation-ID: req-product12345" \
  http://localhost:8080/api/products/9
~~~

Kết quả cần kiểm tra: HTTP 404, Content-Type có thể tương thích application/problem+json, X-Correlation-ID=req-product12345, body có:

~~~json
{
  "status": 404,
  "code": "PRODUCT_NOT_FOUND",
  "correlationId": "req-product12345",
  "detail": "Không tìm thấy sản phẩm."
}
~~~

Đoạn JSON chỉ hiển thị các field đáng quan sát; response ProblemDetail đầy đủ còn có type/title/instance và có thể thêm các field được framework định nghĩa. ID trong ví dụ thuộc tập ký tự được filter cho phép.

### 8.3. Business error 409

~~~bash
curl -i -X POST \
  http://localhost:8080/api/products/reserve \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: req-order987654" \
  -d '{"sku":"KB-001","quantity":9}'
~~~

Kết quả cần kiểm tra: HTTP 409, body code=INSUFFICIENT_STOCK, status=409 và correlationId=req-order987654; response header X-Correlation-ID giữ cùng ID.

### 8.4. Validation error 400

~~~bash
curl -i -X POST \
  http://localhost:8080/api/products/reserve \
  -H "Content-Type: application/json" \
  -d '{"sku":"","quantity":0}'
~~~

Kết quả: HTTP 400, code=VALIDATION_FAILED. Extension errors có những mục mô tả field sku (rule NotBlank) và quantity (rule Min). Thứ tự của các field errors không nên được client xem là bất biến.

### 8.5. Malformed JSON và lỗi framework

~~~bash
curl -i -X POST \
  http://localhost:8080/api/products/reserve \
  -H "Content-Type: application/json" \
  -d '{"sku":'
~~~

Request sai cú pháp; Spring có thể trả HTTP 400 từ HTTP message reader. Trong demo, nó đi qua cơ chế ResponseEntityExceptionHandler và nhận schema ProblemDetail cùng correlationId, với mã generic HTTP_400 nếu chưa định nghĩa một mapping chuyên biệt.

Không nhất thiết mọi lỗi 400 phải có code VALIDATION_FAILED. **Malformed JSON** khác với **Bean Validation failure**; có thể cung cấp MALFORMED_REQUEST riêng nếu project muốn client phân biệt, nhưng cần cập nhật một nơi tập trung và test.

## 9. Kiểm thử contract với MockMvc

Khi chuẩn hóa cấu trúc lỗi, test không chỉ status code: cần test Content-Type, code, correlationId ở header/body, field violations và việc không lộ dữ liệu không an toàn.

File src/test/java/dev/example/errors/ErrorContractTest.java:

~~~java
package dev.example.errors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ErrorContractTest {

    @Autowired
    MockMvc mvc;

    @Test
    void notFoundHasBusinessCodeAndCorrelationId()
            throws Exception {

        mvc.perform(get("/api/products/9")
                .header("X-Correlation-ID", "req-product12345"))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.valueOf("application/problem+json")))
                .andExpect(header().string(
                        "X-Correlation-ID", "req-product12345"))
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"))
                .andExpect(jsonPath("$.correlationId").value(
                        "req-product12345"));
    }

    @Test
    void inventoryConflictUses409AndStableCode()
            throws Exception {

        mvc.perform(post("/api/products/reserve")
                .header("X-Correlation-ID", "req-order987654")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"KB-001\",\"quantity\":9}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value(
                        "INSUFFICIENT_STOCK"))
                .andExpect(jsonPath("$.correlationId").value(
                        "req-order987654"));
    }

    @Test
    void invalidBodyProvidesFieldIssuesWithoutValues()
            throws Exception {

        mvc.perform(post("/api/products/reserve")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"\",\"quantity\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(
                        "VALIDATION_FAILED"))
                .andExpect(jsonPath("$.errors").isArray());
    }

    @Test
    void unsafeIncomingHeaderIsReplaced()
            throws Exception {

        mvc.perform(get("/api/products/9")
                .header("X-Correlation-ID", "bad id with spaces"))
                .andExpect(status().isNotFound())
                .andExpect(header().exists("X-Correlation-ID"))
                .andExpect(jsonPath("$.correlationId").exists());
    }

    @Test
    void successStillCarriesCorrelationHeader()
            throws Exception {

        mvc.perform(get("/api/products/1"))
                .andExpect(status().isOk())
                .andExpect(header().exists("X-Correlation-ID"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Trong ví dụ, các test kiểm tra contract ở tầng MVC và filter khi chạy qua MockMvc. Chúng không tự chứng minh API Gateway, proxy, Servlet container error dispatch hay cloud tracing đúng; cần thêm integration test với server thực hoặc staging.

**Chú ý test schema:** các dynamic fields như instance và UUID không được so với một chuỗi cố định. Kiểm tra format và tính khác nhau giữa các lần nếu contract yêu cầu. Trong test production còn cần assert rằng body.status đúng bằng HTTP status; header correlationId trùng với body; lỗi 500 không lộ SQL/stack trace.

## 10. HTTP status và retry semantics

Một lỗi thống nhất phải cho client quyết định có retry không, và retry như thế nào. Không dùng mỗi business code để suy ra “retry mọi lỗi”.

| Status | Ví dụ | Retry thông thường |
|---|---|---|
| 400 | JSON malformed, validation failed | Không retry y nguyên; sửa request |
| 401 | Chưa xác thực | Thực hiện auth flow; tránh retry vô hạn |
| 403 | Không được phép | Không retry y nguyên để mong có quyền |
| 404 | Không tìm thấy resource | Tùy use case; thường không retry ngay |
| 409 | Xung đột tồn kho/version | Có thể cần refresh state, thay payload |
| 412 | ETag/precondition fail | Lấy version mới và giải quyết xung đột |
| 422 | Payload hiểu được nhưng không xử lý được theo rule | Sửa dữ liệu hoặc quy trình |
| 429 | Rate limit | Backoff, xem Retry-After |
| 500 | Lỗi nội bộ không dự kiến | Retry chỉ khi thao tác an toàn/idempotent và có giới hạn |
| 502/503/504 | Gateway/upstream không đáp ứng | Có thể retry với backoff/jitter khi an toàn |

Nếu response có Retry-After ở 429/503, client nên tuân thủ trong giới hạn hợp đồng; trường body retryable nếu có chỉ là gợi ý nghiệp vụ chứ không thay thế HTTP semantics. Một request POST có side effect cần có Idempotency-Key hoặc cơ chế chống trùng phù hợp trước khi retry tự động.

Mã lỗi giúp phân loại hậu quả; nó không tự biến một thao tác không idempotent thành an toàn để thử lại.

## 11. Phạm vi bao phủ thực tế: ControllerAdvice không bắt được mọi lỗi

Một thiết kế lỗi thống nhất có thể thất bại vì tưởng rằng @RestControllerAdvice áp dụng cho toàn bộ HTTP stack. Trong Spring Boot MVC, request có thể bị chặn hoặc gặp lỗi **trước** khi vào DispatcherServlet.

Một số nơi cần kiểm tra riêng:

| Nơi phát sinh | Có chắc đi qua @RestControllerAdvice không? | Điểm mở rộng |
|---|---|---|
| Exception trong annotated controller | Thường có nếu MVC còn xử lý được response | @ExceptionHandler / ResponseEntityExceptionHandler |
| Bean Validation @Valid @RequestBody | Thường có | handleMethodArgumentNotValid |
| Method validation Spring 6.1+ | Thường có | handleHandlerMethodValidationException |
| Spring Security authentication/authorization | Không bảo đảm | AuthenticationEntryPoint, AccessDeniedHandler |
| Servlet Filter ném exception trước MVC | Không bảo đảm | Filter error handling, container /error |
| Servlet container error dispatch | Không bảo đảm | ErrorController / ErrorAttributes |
| BasicErrorController mặc định | Có thể tạo legacy JSON | Tùy biến Boot error handling |
| Reverse proxy/load balancer/gateway | Không | Cấu hình error mapping ở gateway |
| Connection bị đóng/response committed | Không thể luôn viết lại body | Log/metrics/client-side handling |
| WebFlux WebFilter/WebExceptionHandler | Khác Servlet MVC | Reactive error handler thích hợp |

### 11.1. /error và BasicErrorController

Trong Spring Boot MVC, các lỗi không được xử lý qua controller advice có thể đi qua error dispatch và BasicErrorController với DefaultErrorAttributes. Tùy phiên bản/cấu hình, response có thể có cấu trúc legacy như timestamp/status/error/path, không phải RFC 9457.

**Bật spring.mvc.problemdetails.enabled không phải bảo đảm tuyệt đối** rằng mọi response BasicErrorController, mọi lỗi 404 của container và mọi lỗi phía proxy sẽ được chuyển thành ProblemDetail. Nếu contract yêu cầu toàn bộ response cùng schema, cần khảo sát và thiết kế thêm:

- Cách biến đổi ErrorAttributes hoặc thay ErrorController một cách có kiểm soát.
- Mapping status, error code và correlationId tại /error.
- Cách xử lý HTML error pages, content negotiation và client Accept headers.
- Error dispatch với filter/security: header và request attributes có còn tồn tại không.
- Integration tests cho lỗi trước MVC, static resources, unknown route và bảo mật.

Không tự thay BasicErrorController bằng một controller @RequestMapping("/error") không hiểu vòng đời container; có thể thay đổi status/headers, làm loop hoặc tạo lỗi HTML/JSON khác dự kiến.

### 11.2. Spring Security cần cấu hình riêng

Một 401 do Security filter thường không đi qua MVC controller advice. Ở Servlet stack, dùng AuthenticationEntryPoint và AccessDeniedHandler có thể tạo ProblemDetail an toàn, cùng code và correlationId. Để tránh duplicate code, trích xuất một **ErrorResponseFactory** dùng chung cho MVC advice và security handlers, nhưng bảo đảm các class không phụ thuộc quá mức vào một request abstraction cụ thể.

Không trả chi tiết như “username đã tồn tại”, “token ký bởi ai”, “chữ ký JWT sai ra sao” nếu thông tin đó giúp tấn công hoặc dò tài khoản. Một code tổng quát AUTHENTICATION_REQUIRED thường phù hợp bên ngoài; logs giữ chi tiết kỹ thuật trong phạm vi bảo vệ.

### 11.3. Kiểm tra error body từ downstream và gateway

Nếu một service gọi downstream rồi nhận ProblemDetail từ downstream, không nhất thiết chuyển nguyên body đó ra client. Nó có thể chứa internal service names, object IDs hoặc error codes không thuộc public API contract.

Tại boundary BFF/gateway, ánh xạ từ downstream codes sang public codes ổn định và giữ trace/correlation link trong logs. Không công khai chi tiết service topology hoặc access token do downstream vô tình trả về.

## 12. Spring WebFlux: dùng WebFilter và reactive error handling

Spring WebFlux reactive server dùng DispatcherHandler/WebHandler, WebFilter và WebExceptionHandler thay vì Servlet DispatcherServlet/OncePerRequestFilter. Cấu trúc lỗi cuối có thể dùng ProblemDetail, nhưng **không được sao chép nguyên MVC ResponseEntityExceptionHandler method signatures** sang WebFlux: WebFlux có các method reactive và nhận ServerWebExchange.

### 12.1. WebFilter đặt correlationId trong exchange và Reactor Context

File ReactiveCorrelationFilter.java trong một project Spring Boot WebFlux riêng:

~~~java
package dev.example.reactiveerrors;

import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class ReactiveCorrelationFilter implements WebFilter {

    public static final String KEY = "correlationId";
    public static final String HEADER = "X-Correlation-ID";

    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9._-]{8,64}");

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String candidate = exchange.getRequest()
                .getHeaders().getFirst(HEADER);

        String id = candidate != null && SAFE.matcher(candidate).matches()
                ? candidate
                : UUID.randomUUID().toString();

        exchange.getAttributes().put(KEY, id);
        exchange.getResponse().getHeaders().set(HEADER, id);

        return chain.filter(exchange)
                .contextWrite(context -> context.put(KEY, id));
    }
}
~~~

Đây là class chạy được với Spring WebFlux/Reactor trong một project Java 17+ có starter-webflux. Exchange attributes giúp error handler truy cập ID; Reactor Context giúp truyền metadata theo **reactive subscription chain**. Không dùng MDC.put(...) quanh một lời gọi trả Mono rồi nghĩ MDC tự duy trì trên mọi event-loop thread: MDC truyền thống là ThreadLocal và cần context propagation bridge nếu muốn log correlation đầy đủ.

**Trust boundary vẫn áp dụng:** class này kiểm tra format, không chứng minh incoming header đáng tin. Với API public, có thể chọn sinh ID mới tại ingress.

### 12.2. Reactive @RestControllerAdvice cho business error

Ví dụ snippet cần có BusinessException và ErrorCode tương thích trong WebFlux project, không dùng Servlet imports:

~~~java
@RestControllerAdvice
public class ReactiveBusinessErrorAdvice {

    @ExceptionHandler(BusinessException.class)
    public Mono<ResponseEntity<ProblemDetail>> onBusiness(
            BusinessException ex,
            ServerWebExchange exchange) {

        ProblemDetail problem =
                ProblemDetail.forStatus(ex.errorCode().status());

        problem.setDetail(ex.errorCode().safeDetail());
        problem.setProperty("code", ex.errorCode().name());

        String id = exchange.getAttribute(
                ReactiveCorrelationFilter.KEY);

        if (id != null) {
            problem.setProperty("correlationId", id);
        }

        problem.setInstance(
                URI.create("urn:uuid:" + UUID.randomUUID()));

        return Mono.just(ResponseEntity
                .status(ex.errorCode().status())
                .body(problem));
    }
}
~~~

Đây là **snippet**: cần package/imports và các class BusinessException, ErrorCode của project tương ứng. Nó minh họa cách tạo ProblemDetail mà không gọi block(). Nếu muốn chuẩn hóa cả lỗi framework ở WebFlux, có thể mở rộng ResponseEntityExceptionHandler của **WebFlux** hoặc thiết kế ErrorWebExceptionHandler tại WebHandler boundary.

### 12.3. Truyền ID xuống WebClient qua Reactor Context

Khi WebClient gửi request downstream, có thể dùng một ExchangeFilterFunction đọc Reactor Context:

~~~java
@Bean
WebClient downstreamClient(WebClient.Builder builder) {
    return builder.filter((request, next) ->
            Mono.deferContextual(context -> {
                String id = context.getOrDefault(
                        "correlationId", "");

                ClientRequest.Builder changed =
                        ClientRequest.from(request);

                if (!id.isBlank()) {
                    changed.headers(headers ->
                            headers.set("X-Correlation-ID", id));
                }

                return next.exchange(changed.build());
            }))
            .build();
}
~~~

Đây là một @Bean method snippet cần imports WebClient, ClientRequest, Mono, Bean và class @Configuration. Nó giả định reactive flow được chain bình thường trong một request và context đã được đặt ở WebFilter. Nếu ứng dụng tự subscribe detached publisher, chạy job độc lập hoặc chuyển sang thread-local code không có bridge, metadata có thể không còn như kỳ vọng.

Tương tự, nếu đang dùng Micrometer Tracing/OpenTelemetry, **để instrumentation quản lý traceparent/tracestate** thay vì tự viết một filter tạo trace ID không đúng chuẩn. Correlation header ứng dụng là một contract khác với trace propagation chuẩn.

### 12.4. ErrorWebExceptionHandler và response đã committed

Trong WebFlux, những exception chưa được annotated advice xử lý có thể đi đến WebExceptionHandler hoặc error handler của Spring Boot. Nếu response đã committed do streaming Flux hoặc server gửi headers, một lỗi muộn có thể không còn được đổi thành một JSON ProblemDetail mới. Cần log correlation/trace ID, xử lý cancellation và thiết kế protocol streaming thích hợp.

Không gọi block() trong WebExceptionHandler để truy xuất service hoặc logs; handler nên trả Mono<Void> và kết hợp Publisher phù hợp.

## 13. Distributed tracing, Micrometer và logs

Ở nhiều microservice, nên tận dụng Micrometer Observation/Tracing hoặc OpenTelemetry. Instrumentation có thể tự tạo trace/span, lan truyền W3C traceparent qua HTTP clients và đưa traceId/spanId vào logs theo cấu hình. Correlation ID của ứng dụng có thể là một field bổ sung, không phải thay cho telemetry framework.

Ví dụ log có cấu trúc:

~~~json
{
  "timestamp": "2026-11-07T14:32:00Z",
  "service": "inventory-api",
  "level": "WARN",
  "httpStatus": 409,
  "errorCode": "INSUFFICIENT_STOCK",
  "correlationId": "req-order987654",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "message": "Reservation rejected by inventory policy"
}
~~~

Đây là log giả lập, không phải dữ liệu hệ thống thật. Không gắn nguyên user input, access token hay nội dung nhạy cảm vào log chỉ để tăng khả năng tra cứu.

### 13.1. Structured logging và MDC

Trong Servlet MVC, MDC thường hữu ích khi xử lý đồng bộ trên một thread; filter đặt correlationId trước chain và xóa trong finally. Với async controllers, @Async hoặc Reactor, phải dùng cơ chế context propagation; không tự truyền MDC bằng cách dùng biến static hoặc ThreadLocal không được cleanup.

Trong WebFlux, ưu tiên Reactor Context và Micrometer context propagation/tracing. Nếu cần truyền vào MDC ở logging boundary, chọn thư viện bridge và kiểm thử trên scheduler switches. Không dùng MDC như nguồn chân lý duy nhất cho correlationId trong reactive flow.

### 13.2. Tìm log theo correlation ID

Một trình tự hỗ trợ production:

1. Client nhận lỗi 409 và lưu code, correlationId, thời điểm, route.
2. Nhân viên hỗ trợ tìm logs bằng correlationId, giới hạn theo service/time window.
3. Truy ngược qua API Gateway và các service downstream có truyền cùng ID hoặc trace context.
4. Nếu tracing enabled, dùng traceId để xem spans và latency.
5. Xem lỗi domain hoặc dependency ở logs, không dùng raw exception text do client gửi làm chứng cứ duy nhất.
6. Xác minh idempotency và hoạt động đã xảy ra trước khi quyết định retry.
7. Sửa nguyên nhân và dùng regression test cho đúng error code/status.

Không yêu cầu client gửi stack trace hoặc token để debug nếu correlation/trace data đã đủ cho người vận hành truy xuất logs được phân quyền.

## 14. Bảo mật của một error contract

Error response là một bề mặt tiết lộ thông tin. Các nguyên tắc:

- Không trả ex.getStackTrace(), tên class nội bộ, đường dẫn file, SQL query, connection string hoặc thông tin database schema.
- Không echo toàn bộ @RequestBody vào lỗi validation.
- Không trả rejectedValue chứa mật khẩu, token, số tài khoản hoặc dữ liệu cá nhân.
- Không tiết lộ token verification detail hoặc tên user/tenant không được phép truy cập.
- Không đưa PII trong correlationId, type URI, instance URI hoặc metric tags.
- Kiểm tra inbound ID header để tránh CR/LF log injection, giá trị quá dài và high cardinality không kiểm soát.
- Với lỗi 500, hiển thị message an toàn; giữ stack trace trong logs có kiểm soát.
- Không tin header forwarded/correlation từ nguồn ngoài trust boundary.
- Có authentication/authorization thích hợp khi cung cấp endpoint tra cứu chi tiết một instance URI.
- Bảo đảm mã lỗi không làm lộ sự tồn tại resource mà người dùng không có quyền biết; đôi khi security policy chủ động trả 404 thay vì 403.
- Đánh giá cache behavior của error responses; không vô tình cache thông tin lỗi nhạy cảm ở shared proxy.

### 14.1. Status, CORS và client browser

Nếu frontend chạy cross-origin, X-Correlation-ID là custom response header; JavaScript chỉ đọc được khi CORS policy **expose** header phù hợp, ví dụ Access-Control-Expose-Headers: X-Correlation-ID. Cấu hình tại Spring Security/CORS hoặc gateway tùy kiến trúc. Đừng thêm wildcard exposure khi đang có credential policy mà chưa hiểu tác động.

Cần bảo đảm body correlationId và header là cùng giá trị. Nếu browser không thể đọc header do CORS, body vẫn có thể cung cấp ID trong những lỗi JSON đã được server cho phép frontend đọc, nhưng lỗi mạng/CORS hoàn toàn có thể không cho client truy cập response.

## 15. Thiết kế response lỗi validation

Một input có nhiều field sai cần trả cấu trúc máy đọc ổn định. Extension errors của ProblemDetail có thể là một array:

~~~json
{
  "type": "https://api.example.com/problems/validation-failed",
  "title": "Bad Request",
  "status": 400,
  "detail": "Dữ liệu gửi lên không hợp lệ.",
  "instance": "urn:uuid:ef0db84d-4c3f-4c16-a06f-522ba2c7139d",
  "code": "VALIDATION_FAILED",
  "correlationId": "req-validate12345",
  "errors": [
    {"field": "sku", "rule": "NotBlank"},
    {"field": "quantity", "rule": "Min"}
  ]
}
~~~

Đây là ví dụ minh họa, không phải output tĩnh của một request cụ thể. Thứ tự lỗi không nên là một phần contract trừ khi có sorting được quy định.

**Nên có**:
- field hoặc JSON pointer, nếu được phép công khai.
- rule hoặc error code ở từng field, ổn định giữa ngôn ngữ.
- message an toàn theo locale nếu UI cần.
- không cần rejected value trong response; nếu cần, phải có policy bảo vệ.

**Đừng coi** mọi HTTP 400 là VALIDATION_FAILED. Malformed JSON, missing header, unsupported encoding hoặc type conversion lỗi nên được phân biệt nếu client cần hành động khác. Nếu không, một generic HTTP_400 vẫn tốt hơn bịa một mã chuyên biệt không đúng.

### 15.1. Bean Validation và method validation theo phiên bản

Spring Framework 6.1+ có built-in controller method validation cho direct constraints trên tham số/return value và có thể phát sinh HandlerMethodValidationException, trong khi @Valid @RequestBody object validation có thể phát sinh MethodArgumentNotValidException trong MVC. Với WebFlux object validation thường có WebExchangeBindException.

Để đồng bộ contract, cần xử lý cả hai loại trong đúng web stack. Với MVC, ResponseEntityExceptionHandler có hook handleHandlerMethodValidationException ở Framework 6.1+. Không được ép lỗi return-value validation do server tạo thành HTTP 400: nó thường là server error 500.

Đoạn demo MVC ở trên override handleMethodArgumentNotValid. Nếu bổ sung @Min trực tiếp vào @RequestParam, cần mở rộng thêm hook method validation hoặc dùng createResponseEntity để bảo đảm có code và correlationId. Nếu API muốn code VALIDATION_FAILED nhất quán cho **input method validation**, phải phân biệt với return-value error và thêm mapping phù hợp.

### 15.2. Client xử lý danh sách lỗi như thế nào?

Frontend có thể dùng errors để đặt thông báo gần field. Nếu field nào không được nhận diện, hiển thị detail tổng quát. Không giả định errors luôn tồn tại: một 503 hoặc 409 thường không có field errors. Client nên viết parser có cấu trúc hợp lý cho extension tùy chọn và bỏ qua những field mới chưa biết theo nguyên tắc mở rộng RFC.

## 16. Phối hợp với API Gateway và nhiều microservice

Nếu nhiều backend framework cùng phục vụ một sản phẩm (Spring MVC, WebFlux, Node.js, Go), nên công bố một **error schema chung** ở cấp API contract thay vì để mỗi framework tự quyết định.

Một quy trình:

~~~text
Client request
  |
  v
Gateway: cấp/kiểm tra correlation ID, tạo trace context
  |
  +-- Service A: xử lý HTTP request, validation, domain
  |      |
  |      +-- downstream Service B: có status/code nội bộ
  |      |
  |      +-- map sang public HTTP status và public error code
  |
  v
Gateway: giữ status, headers, response body đúng contract
  |
  v
Client: đọc status + code + correlationId
  |
  v
Support: tìm logs theo correlationId, trace theo traceId
~~~

Không để gateway ép mọi upstream error về 200 hoặc thay 409 thành 500 vì client sẽ xử lý sai. Nếu gateway cần ẩn lỗi nội bộ, phải có mapping chủ động, test và log cả internal code lẫn public code ở nơi được phép.

### 16.1. Những lỗi chỉ gateway tạo ra

Gateway có thể trả 413, 429, 502, 503, 504 mà request chưa đến Spring controller. Nếu yêu cầu thống nhất tuyệt đối, gateway phải tạo cùng Problem Details contract và trả/gắn X-Correlation-ID. Spring @ControllerAdvice không thể xử lý một lỗi do gateway trả trước khi forward.

### 16.2. Khi downstream có business code khác

Ví dụ Service A public API dùng INVENTORY_UNAVAILABLE, nhưng Service B trả warehouse/slot-specific codes. Service A có thể map tất cả lỗi đó sang một mã public được tài liệu hóa, đồng thời log internal code + correlation/trace ID.

Không chuyển nguyên downstream ProblemDetail nếu nó chứa nội bộ hostnames, internal trace IDs, debug data hoặc tên bảng. Client public chỉ nên thấy những field thuộc contract của Service A.

## 17. Kiểm thử end-to-end và ma trận lỗi

| Tình huống | Status | Code mong đợi | Correlation |
|---|---:|---|---|
| GET product hợp lệ | 200 | Không bắt buộc error code | Header có ID |
| GET product không tồn tại | 404 | PRODUCT_NOT_FOUND | Header = body |
| Reserve quá tồn kho | 409 | INSUFFICIENT_STOCK | Header = body |
| @Valid body sai | 400 | VALIDATION_FAILED | Header = body |
| JSON malformed | 400 | HTTP_400 hoặc MALFORMED_REQUEST | Header = body |
| Query type mismatch | 400 | HTTP_400 hoặc INPUT_TYPE_MISMATCH | Header = body |
| Input method validation | 400 | Mã validation theo contract | Header = body |
| Return-value validation lỗi | 500 | INTERNAL_ERROR | Header = body nếu ghi được |
| Exception không dự kiến | 500 | INTERNAL_ERROR | Không tiết lộ stack trace |
| Spring Security chặn 401 | 401 | AUTHENTICATION_REQUIRED | Cần security handler riêng |
| Spring Security chặn 403 | 403 | ACCESS_DENIED | Cần security handler riêng |
| Servlet error dispatch | Theo lỗi | Contract chung nếu được cấu hình | Test request attribute/filter |
| Gateway rate limit | 429 | RATE_LIMITED | Gateway phát/giữ ID |
| Gateway timeout | 504 | GATEWAY_TIMEOUT theo contract | Gateway phát/giữ ID |
| WebFlux functional handler lỗi | Theo lỗi | Contract chung qua reactive handler | Reactive context |
| Response streaming đã committed | Có thể đóng stream | Không bảo đảm viết ProblemDetail mới | Logs/trace vẫn cần |
| Incoming correlationId sai format | Tùy lỗi | Không liên quan code domain | ID được thay hoặc từ chối theo policy |

Các điểm cần test thêm ngoài bảng:

1. Trường status trong body khớp HTTP status thực tế.
2. Content-Type phù hợp application/problem+json.
3. code có trong catalog và không biến đổi theo locale.
4. type URI có cấu trúc, ý nghĩa và tài liệu ổn định.
5. instance không chứa PII hoặc query nhạy cảm.
6. errors không chứa rejected values.
7. correlationId không rỗng và header/body trùng nhau.
8. ID incoming quá dài, chứa CR/LF hoặc Unicode không được chấp nhận/được thay theo policy.
9. Header duplicate hoặc nhiều nguồn ID có quy tắc chọn rõ.
10. Async và error dispatch không làm mất ID hoặc rò MDC sang request khác.
11. Tracing propagation không bị đứt qua WebClient hoặc HTTP clients khác.
12. API Gateway cùng giữ đúng schema khi backend chưa nhận request.
13. 5xx body không chứa tên class, SQL, token hoặc stack trace.
14. Client retry không tạo side effect trùng lặp; có Idempotency-Key nếu cần.
15. OpenAPI/examples và generated clients khớp contract.

## 18. Quy trình triển khai trong một hệ thống thực

### Bước 1: Chốt hợp đồng trước khi viết filter

Chọn RFC 9457 ProblemDetail, media type, required extensions (code, correlationId), optional extensions (errors) và danh sách status. Thống nhất ý nghĩa type/title/detail/instance; xác định có hỗ trợ locale không.

### Bước 2: Quản lý catalog mã nghiệp vụ

Đặt code dưới dạng enum/registry, map sang status và tài liệu. Quy tắc code mới có người chịu trách nhiệm duyệt; tránh trùng hoặc đổi meaning của code cũ.

### Bước 3: Cấp và lưu correlationId đúng trust boundary

Ưu tiên ingress/gateway hoặc một WebFilter/Servlet Filter đầu pipeline. Đặt ID trong request/exchange context, response header và logs. Không coi header khách hàng tự đưa vào là chứng cứ xác thực.

### Bước 4: Dùng một factory để tạo lỗi

Có thể trích ErrorResponseFactory từ code mẫu để tạo ProblemDetail và thêm code/correlationId/type/instance theo một quy tắc. Dùng lại factory ở MVC advice, WebFlux advice, security handlers và /error tương ứng; tránh copy-paste status mapping.

### Bước 5: Tách những điểm xử lý ngoài MVC

Bổ sung security entry point/denied handler, container error dispatch, WebFlux ErrorWebExceptionHandler và gateway error mapper tùy kiến trúc. Không đánh dấu “toàn bộ lỗi đã chuẩn hóa” chỉ vì @RestControllerAdvice hoạt động với một controller.

### Bước 6: Bổ sung logs, metrics, tracing

Gắn correlationId, traceId, spanId và code ở nơi thích hợp. Không đưa correlationId làm metric tag cho mỗi request vì cardinality cao; error code hữu hạn mới phù hợp hơn cho metrics. Bảo vệ log access và retention.

### Bước 7: Contract tests và fault injection

Thử lỗi nghiệp vụ, invalid body, missing query, security 401/403, upstream timeout, filter exception và 500. Xem body/status/header thực tế; không chỉ kiểm tra Java exception class.

### Bước 8: Công bố API docs và thực hiện migration

Định nghĩa schema ProblemDetail + extensions trong OpenAPI, công bố catalog mã lỗi, giữ backward compatibility. Nếu client cũ đang dùng JSON legacy, có thể dùng versioning hoặc transitional dual-read clients; không tự đổi tất cả responses vào một ngày mà chưa phối hợp.

## 19. Những lỗi thường gặp

### Lỗi 1 — Cho rằng HTTP status là business code

HTTP 404 không cho biết đang thiếu sản phẩm, đơn hàng hay người dùng. Nếu client cần xử lý khác nhau, cung cấp code ổn định như PRODUCT_NOT_FOUND hoặc ORDER_NOT_FOUND.

### Lỗi 2 — Trả HTTP 200 cho mọi response lỗi

Monitoring/gateway/client có thể coi lỗi là thành công. Giữ status đúng và thống nhất nội dung.

### Lỗi 3 — Dùng message làm khóa logic

Một câu detail có thể đổi theo locale hoặc cách diễn đạt. Client dùng code/type để rẽ nhánh.

### Lỗi 4 — Gắn stack trace vào detail

Có thể lộ đường dẫn, SQL hoặc dữ liệu nội bộ. Dùng message an toàn cho client; logs có kiểm soát giữ thông tin kỹ thuật.

### Lỗi 5 — Gắn correlationId bằng HTTP header nhưng không có trong logs

Khi user báo ID, nhân viên support không tìm được gì. Đặt ID tại request context, MDC/tracing và bảo đảm thread/reactive context propagation.

### Lỗi 6 — Dùng MDC ThreadLocal trực tiếp cho WebFlux

Reactive callbacks có thể đổi thread; MDC không tự theo Publisher. Dùng Reactor Context và bridge phù hợp.

### Lỗi 7 — Tin ID do client ngoài Internet gửi

Client có thể giả mạo ID, làm nhiễu logs hoặc dò tương quan request khác. Validate/replace tại trusted ingress; không dùng ID làm quyền truy cập.

### Lỗi 8 — Dùng correlationId để deduplicate POST

Correlation ID chỉ để trace; không có bảo đảm idempotency. Cần Idempotency-Key và storage policy nếu thao tác yêu cầu.

### Lỗi 9 — Hiểu instance là URL request có query

RFC 9457 mô tả instance là một URI reference của occurrence. Copy raw URL dễ lộ PII/query secrets và không nhất thiết phân biệt từng occurrence.

### Lỗi 10 — Bật problem details rồi nghĩ mọi /error đều chuẩn

BasicErrorController và các nguồn lỗi ngoài MVC có thể vẫn trả legacy JSON hoặc HTML. Kiểm tra thật bằng integration tests.

### Lỗi 11 — Cố catch Exception trong controller advice cho tất cả hệ thống

Filter, Spring Security, gateway và response committed nằm ở các tầng khác nhau. Cần xử lý tại boundary phù hợp.

### Lỗi 12 — Trả 400 cho return-value validation/server bugs

Lỗi do server tạo ra nên được phân loại 5xx khi phù hợp. Không “đổ lỗi” cho request để cải thiện metric.

### Lỗi 13 — Trả trực tiếp downstream error cho frontend

Có nguy cơ lộ internal hostnames, exception details hoặc mã nội bộ không ổn định. Ánh xạ sang public contract.

### Lỗi 14 — Trùng tên code giữa các team

Nếu mã chỉ là "NOT_FOUND" cho nhiều domain không phân biệt, client không đủ ngữ nghĩa. Dùng namespace/catalo g có quản trị và tài liệu.

### Lỗi 15 — Bỏ qua CORS header exposure

Browser frontend có thể nhận lỗi nhưng không đọc được X-Correlation-ID. Cấu hình Access-Control-Expose-Headers khi cần và an toàn.

### Lỗi 16 — Dùng correlationId làm metric tag

Một ID cho mỗi request có cardinality rất cao, gây tốn bộ nhớ/time-series. Metric tag nên là error code hữu hạn, status hoặc normalized route; correlationId thuộc logs/traces.

### Lỗi 17 — Không test đường lỗi ngay lúc startup/shutdown

Khi server chưa ready hoặc đang graceful shutdown, error responses có thể do gateway/container tạo ra, không đi qua advice. Cần quy tắc correlation/tracing tại ingress.

### Lỗi 18 — Thay code cũ mà không versioning

Client đã rẽ nhánh theo code cũ có thể hỏng khi ý nghĩa mã bị đổi. Không repurpose code; thêm mã mới và lên kế hoạch migration.

## 20. Câu hỏi tự kiểm tra

**Câu 1. Vì sao phải có cả HTTP 409 và INSUFFICIENT_STOCK?**  
409 cho hạ tầng HTTP biết có xung đột; INSUFFICIENT_STOCK mô tả loại lỗi nghiệp vụ cụ thể để client xử lý.

**Câu 2. correlationId và traceId có luôn giống nhau không?**  
Không. Chúng thuộc hai contract khác nhau; có thể chủ động thống nhất nếu kiến trúc cho phép.

**Câu 3. detail có nên được client parse để nhận biết lỗi không?**  
Không. detail dành cho con người và có thể được dịch; client nên dùng code/type URI.

**Câu 4. Vì sao instance không nên chứa raw query?**  
Vì có thể lộ secrets/PII và không nhất thiết định danh duy nhất một occurrence.

**Câu 5. @RestControllerAdvice có bắt một 401 do Spring Security trả trước MVC không?**  
Không bảo đảm; cần AuthenticationEntryPoint hoặc cơ chế bảo mật phù hợp.

**Câu 6. Khi validation field lỗi, có nên trả rejectedValue để frontend biết người dùng nhập gì?**  
Thường không, đặc biệt với mật khẩu/token. Frontend đã có input; server chỉ cần trả field/rule/message an toàn.

**Câu 7. Vì sao không dùng correlationId làm Idempotency-Key?**  
Một cái để truy vết, cái kia để chống thực thi trùng side effects. Không có bảo đảm tương đương.

**Câu 8. Khi nào một lỗi validation cần là HTTP 500?**  
Khi constraint trên giá trị trả về bị server vi phạm hoặc đó là lỗi invariant nội bộ, không phải input client sai.

**Câu 9. Trong WebFlux có thể dùng MDC.put trong WebFilter rồi lập tức return Mono để mọi downstream log nhận ID không?**  
Không. Mono chạy khi subscribe và có thể đổi thread. Cần Reactor Context/bridge hoặc instrumentation.

**Câu 10. Client nên làm gì khi không nhận được problem+json vì connection bị đóng?**  
Dùng HTTP/network error handling riêng, lưu correlation/trace ID có sẵn và quyết định retry theo tính an toàn/idempotency của thao tác.

## 21. Tổng kết

Một lỗi HTTP nhất quán trong Spring Boot cần **ba lớp thông tin độc lập**:

- HTTP status đúng theo giao thức.
- Business error code/type ổn định để client xử lý.
- Correlation ID (và trace context khi có) để người vận hành truy vết.

**RFC 9457 ProblemDetail** giúp giữ năm trường chuẩn type/title/status/detail/instance. Spring Framework cung cấp ProblemDetail, ErrorResponse, ErrorResponseException và ResponseEntityExceptionHandler; application-specific fields như code, correlationId, errors có thể thêm bằng extensions.

Trong Spring MVC, @RestControllerAdvice cùng một correlation filter là điểm bắt đầu tốt, nhưng cần cấu hình riêng nếu muốn bao phủ Spring Security, /error, Servlet container và gateway. Trong Spring WebFlux, dùng WebFilter/Reactor Context và reactive exception handling; không sao chép ThreadLocal/MVC hooks sang reactive pipeline.

Một contract chỉ thật sự “thống nhất” khi **cùng schema, cùng status semantics, cùng mã lỗi ổn định, cùng correlation policy và có test trên mọi boundary**. Làm rõ những quy tắc đó giúp frontend xử lý ổn định, giảm rò rỉ thông tin và rút ngắn thời gian tìm nguyên nhân ở hệ thống nhiều dịch vụ.

## 22. Tài liệu chính thức

- IETF RFC 9457 – Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
- Spring Framework – MVC REST exceptions, ProblemDetail và ErrorResponse: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework – WebFlux REST exceptions, ProblemDetail: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
- Spring Framework 6.1 Javadoc – ResponseEntityExceptionHandler: https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework – MVC Controller Advice: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html
- Spring Boot – Error Handling và Problem Details: https://docs.spring.io/spring-boot/reference/web/servlet.html
- W3C Trace Context specification: https://www.w3.org/TR/trace-context/
- Micrometer Tracing: https://docs.micrometer.io/tracing/reference/
- OpenTelemetry – Context propagation: https://opentelemetry.io/docs/concepts/context-propagation/
