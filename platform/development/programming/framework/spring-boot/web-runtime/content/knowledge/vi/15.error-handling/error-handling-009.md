# Cấu hình server.error.* và giới hạn hiển thị message, exception, stack trace

Một ứng dụng Spring Boot có thể trả về HTTP 500 khi controller ném exception, HTTP 404 khi không tìm thấy tài nguyên hoặc HTTP 400 khi dữ liệu đầu vào không hợp lệ. Phản hồi lỗi cần **đủ thông tin để client xử lý**, nhưng không nên công khai tên class exception, câu SQL, mật khẩu, token, đường dẫn máy chủ hay Java stack trace. Trong Spring Boot, nhóm property `server.error.*` kiểm soát một số thuộc tính xuất hiện trong **phản hồi lỗi mặc định**. Hiểu đúng phạm vi của chúng giúp tránh tình trạng bật debug ở production rồi vô tình tiết lộ chi tiết vận hành.

Bài tập trung vào **Spring Boot 3.3.x, Spring MVC/Servlet web application, Java 17+**. Chúng ta sẽ phân tích cơ chế `/error`, phân biệt `message`, `exception`, `trace` và `errors`, tìm hiểu các giá trị `never` / `always` / `on_param`, đưa ra cấu hình sản xuất an toàn, ví dụ thực thi và kiểm thử qua HTTP thật. Những tùy chọn này là **một lớp bảo vệ cho error response mặc định**, không thể tự kiểm soát mọi body lỗi do ứng dụng hoặc thư viện khác tạo ra.

## 1. Tại sao không nên trả chi tiết exception cho client?

Một service có thể gặp lỗi như:

~~~text
org.springframework.dao.DataIntegrityViolationException
Duplicate key value violates unique constraint "uk_customer_email"
SQL: INSERT INTO customer(email, password_hash) ...
at com.example.billing.CustomerRepository.save(CustomerRepository.java:87)
~~~

Các chi tiết trên hữu ích khi kỹ sư điều tra trong log có kiểm soát, nhưng nếu trả trực tiếp cho người gọi API, chúng có thể tiết lộ:
- Loại framework, driver, database và cấu trúc bảng/constraint.
- Tên package/class, đường dẫn file, số dòng code.
- Dữ liệu mà exception message vô tình chứa: email, token, thông tin khách hàng hoặc câu SQL.
- Các bước bên trong hệ thống, giúp người tấn công suy đoán cấu trúc triển khai.

Nguyên tắc nên áp dụng: **response cung cấp contract an toàn, log/trace phục vụ chẩn đoán nội bộ**. Một lỗi server điển hình có thể trả status 500 cùng mã lỗi ổn định và correlation ID, trong khi log có chi tiết exception ở môi trường chỉ nhân sự được phép truy cập.

Không nên trả `200 OK` cho exception chỉ để “giấu lỗi”: HTTP status vẫn phải phản ánh kết quả, còn body cần giới hạn thông tin.

## 2. Spring Boot đưa request lỗi vào /error như thế nào?

Trong Servlet/Spring MVC, Spring Boot cấu hình cơ chế error handling mặc định bằng các thành phần như `ErrorMvcAutoConfiguration`, `BasicErrorController` và `ErrorAttributes`.

Sơ đồ giản lược:

~~~text
Client -> Servlet container -> Filter chain -> DispatcherServlet
                                          |
                                          +-- request thành công -> HTTP 2xx
                                          |
                                          +-- lỗi được MVC xử lý hoàn toàn
                                          |      -> @ExceptionHandler / advice / resolver
                                          |      -> response riêng
                                          |
                                          +-- lỗi chưa xử lý hoặc container error
                                                 -> error dispatch
                                                 -> /error
                                                 -> BasicErrorController
                                                 -> ErrorAttributes
                                                 -> JSON hoặc HTML
~~~

Các vai trò:
- **`DispatcherServlet`** là front controller Spring MVC; handler có thể thành công hoặc phát sinh exception.
- **`HandlerExceptionResolver` / `@ExceptionHandler` / `@ControllerAdvice`** có thể xử lý exception ngay trong MVC. Khi đã tạo response riêng, luồng đó **không nhất thiết** đi qua `/error`.
- **Servlet container** có thể dispatch lỗi tới error page mặc định của ứng dụng.
- **`BasicErrorController`** phục vụ endpoint `/error` khi auto-configuration tương ứng còn hiệu lực.
- **`ErrorAttributes`** thu thập các thuộc tính dùng cho error response. Tập thuộc tính cuối cùng phụ thuộc lựa chọn include và lỗi thực tế.

`server.error.path` mặc định là `/error`. Đó là đường xử lý lỗi nội bộ của ứng dụng, **không phải** URL mà client nhất thiết phải gọi trực tiếp. Ví dụ client gọi `GET /api/orders/999` và gặp 404, response vẫn dành cho URL gốc dù server có thể dùng dispatch tới `/error`.

**Giới hạn quan trọng:** một số lỗi được Spring MVC, Spring Security, reverse proxy hoặc custom error handler xử lý bằng response riêng. `server.error.*` không phải một bộ lọc hậu kỳ tự động loại bỏ mọi trường nhạy cảm từ tất cả response trong hệ thống.

## 3. Phản hồi lỗi mặc định thường có gì?

Một phản hồi JSON từ error handling mặc định của Spring Boot 3.3 có thể có cấu trúc như sau:

~~~json
{
  "timestamp": "2026-11-07T02:30:00.000+00:00",
  "status": 500,
  "error": "Internal Server Error",
  "path": "/api/demo/fail"
}
~~~

Đây là **minh họa cấu trúc**, không phải kết quả cố định: timestamp, timezone hiển thị, đường dẫn, thứ tự field và thuộc tính có mặt phụ thuộc phiên bản/cấu hình/loại lỗi.

Những field dễ bị nhầm:

| Field trong JSON | Chứa gì | Rủi ro có thể có |
|---|---|---|
| `status` | HTTP status dạng số, ví dụ 404/500 | Cần thiết cho client |
| `error` | Nhãn ngắn tương ứng status, ví dụ Internal Server Error | Thường ít nhạy cảm |
| `timestamp` | Thời điểm lỗi | Có thể hữu ích cho vận hành |
| `path` | Đường dẫn request liên quan lỗi | Có thể để lộ ID, URL nội bộ hoặc thông tin trong path |
| `message` | Thông điệp của lỗi hoặc thông tin liên quan | Có thể chứa chi tiết nội bộ |
| `exception` | Tên class exception | Tiết lộ framework/package/kiểu exception |
| `trace` | Stack trace dạng text | Tiết lộ cấu trúc code và call stack |
| `errors` | Chi tiết binding/validation errors | Có thể chứa tên field, giá trị bị từ chối và metadata |

**Tên field `trace` khác property `include-stacktrace`**. Property quyết định có đưa thông tin stack trace vào response mặc định hay không; field JSON điển hình được đặt tên `trace`.

Không được giả định khi không có `message` thì tất cả response đã an toàn. Custom `@RestControllerAdvice` có thể tự trả `ex.getMessage()` dưới tên `detail`, `reason` hay bất kỳ field khác.

## 4. Các property server.error.* trong Spring Boot 3.3

Theo bảng Common Application Properties của Spring Boot 3.3:

| Property | Giá trị mặc định | Chức năng |
|---|---|---|
| `server.error.include-message` | `never` | Khi nào thêm thuộc tính `message` |
| `server.error.include-exception` | `false` | Có thêm tên class exception hay không |
| `server.error.include-stacktrace` | `never` | Khi nào thêm thuộc tính `trace` |
| `server.error.include-binding-errors` | `never` | Khi nào thêm thuộc tính `errors` |
| `server.error.include-path` | `always` | Khi nào thêm thuộc tính `path` |
| `server.error.path` | `/error` | Mapping error controller |
| `server.error.whitelabel.enabled` | `true` | Có bật trang lỗi HTML dự phòng mặc định hay không |

Lưu ý ba nhóm chức năng khác nhau:

1. **Giới hạn thuộc tính trong response:** `include-message`, `include-exception`, `include-stacktrace`, `include-binding-errors`, `include-path`.
2. **Địa chỉ xử lý lỗi:** `path`.
3. **Trang HTML dự phòng:** `whitelabel.enabled`.

Không nên dùng `server.error.path` để thay đổi mức chi tiết thông tin lỗi; nó thay đổi nơi xử lý lỗi, không tự lọc trường dữ liệu.

Các giá trị mặc định có thể đổi giữa các dòng Spring Boot. Bảng này dành cho **3.3.x**, cần đối chiếu official properties của đúng phiên bản đang chạy thay vì sao chép tên property từ Spring Boot 4.x.

## 5. never, always và on_param có nghĩa gì?

Các thuộc tính dạng *include attribute* như `include-message`, `include-binding-errors`, `include-stacktrace` và `include-path` hỗ trợ lựa chọn:

| Giá trị | Diễn giải |
|---|---|
| `never` | Không đưa attribute tương ứng vào default error response |
| `always` | Đưa attribute nếu dữ liệu tương ứng có sẵn |
| `on_param` | Chỉ đưa attribute khi có query parameter liên quan theo quy tắc của error controller |

Ví dụ trong môi trường debug riêng:

~~~properties
server.error.include-message=on_param
server.error.include-stacktrace=on_param
server.error.include-binding-errors=on_param
~~~

Ở luồng `BasicErrorController`, các tham số liên quan thường là `message`, `trace` và `errors`. Ví dụ yêu cầu có `?trace=true` có thể khiến stack trace được thêm khi setting tương ứng là `on_param`.

**Đây không phải cơ chế xác thực hay phân quyền.** Người gọi có thể tự thêm query parameter; vì vậy `on_param` **không an toàn để bật trên API công khai** với mục đích “chỉ người cần debug mới xem được”. Nó chỉ phù hợp cho môi trường local hoặc hệ thống debug thực sự bị cô lập, và ngay cả khi đó vẫn nên cân nhắc việc dữ liệu nhạy cảm xuất hiện trong response.

`server.error.include-exception` là boolean `true/false`, **không** dùng `never` hoặc `on_param` như các property ở trên. Ngược lại, `server.error.whitelabel.enabled` cũng là boolean và điều khiển HTML fallback, không điều khiển JSON field `trace`.

## 6. include-message: vì sao message không luôn là lời nhắn an toàn?

`server.error.include-message` quyết định khi nào thêm thuộc tính `message` từ error attributes mặc định.

~~~properties
server.error.include-message=never
~~~

Đây là lựa chọn hợp lý cho API public, nhất là lỗi 500. Khi đặt:

~~~properties
server.error.include-message=always
~~~

client có thể nhận thông điệp phát sinh từ exception hoặc từ cơ chế lỗi của framework, ví dụ:

~~~json
{
  "status": 500,
  "error": "Internal Server Error",
  "message": "Customer lookup failed in private backend",
  "path": "/api/customers"
}
~~~

Đây là **ví dụ minh họa một message có thể được trả**, không phải cam kết mọi exception sẽ sinh đúng field/câu chữ trên.

Nguy cơ:
- Exception message do database/HTTP client/driver sinh có thể chứa SQL, URL nội bộ, tên bảng, key hoặc giá trị input.
- Một message hữu ích cho developer có thể không có nghĩa với API consumer.
- Message có thể thay đổi theo phiên bản framework, khiến client phụ thuộc không ổn định.

Muốn client hiểu lỗi nghiệp vụ, hãy định nghĩa **mã lỗi công khai có kiểm soát** như `BOOK_NOT_FOUND` hoặc `INVALID_BOOK_TITLE` trong custom response/ProblemDetail. Không mở `include-message=always` chỉ để có mô tả lỗi thân thiện ở mọi exception.

## 7. include-exception: khác biệt giữa tên class và stack trace

~~~properties
server.error.include-exception=false
~~~

Giá trị mặc định `false` giúp tránh đưa thuộc tính `exception` vào response mặc định. Nếu bật `true`, response có thể gồm tên lớp exception, ví dụ:

~~~json
{
  "status": 500,
  "error": "Internal Server Error",
  "exception": "java.lang.IllegalStateException"
}
~~~

Tên class exception không phải toàn bộ stack trace. Tuy nhiên nó vẫn có thể tiết lộ package, công nghệ và các lớp nghiệp vụ bên trong. Không nên coi việc “chỉ công khai tên exception, không công khai trace” là an toàn mặc định.

Cũng cần phân biệt **exception type** với **HTTP status**. Một lỗi `IllegalArgumentException` do logic ứng dụng ném không tự động thành HTTP 400; nếu không có handler phù hợp, nó có thể trở thành 500. Phân loại lỗi đúng thuộc quy tắc error mapping, không thuộc `include-exception`.

## 8. include-stacktrace: tránh công khai call stack

~~~properties
server.error.include-stacktrace=never
~~~

Stack trace thường chứa:
- Tên package, class, method và file Java.
- Số dòng code.
- Thư viện/framework đang sử dụng và đường gọi hàm.
- Cấu trúc exception cause và có thể cả phần message nhạy cảm.

Đặt `always` có thể đưa trường `trace` vào JSON/HTML error response mặc định. Đây là một trong những cấu hình **nên tránh trong production**. Đặt `on_param` cũng không tạo ra quyền debug được kiểm soát: caller có thể thử `?trace=true`.

**Thay thế:** giữ `include-stacktrace=never` trong response, nhưng ghi stack trace vào log nội bộ bằng logger tại điểm thích hợp và bảo vệ quyền truy cập log. Nếu dùng distributed tracing, đưa một correlation ID/trace ID an toàn cho client rồi truy xuất trace ở backend thay vì gửi cả stack trace.

Không ghi vô hạn payload/headers/authorization token vào log chỉ vì response đã ẩn trace. Giới hạn response và vệ sinh log là **hai lớp kiểm soát độc lập**.

## 9. include-binding-errors: cẩn trọng với rejectedValue

Khi Spring MVC binding/Bean Validation thất bại, thông tin lỗi có thể gồm tên field, loại constraint, mã lỗi hoặc giá trị client đã gửi. Bật:

~~~properties
server.error.include-binding-errors=always
~~~

có thể làm default error response chứa thuộc tính `errors` khi nguồn lỗi có binding details, ví dụ mô tả field không hợp lệ.

Điều này hữu ích để debug nhưng có nguy cơ tiết lộ:
- Tên field nội bộ và bean path.
- Giá trị bị từ chối, có thể chứa email, token, dữ liệu khách hàng.
- Thông điệp validation mà developer không định công bố.

Cho production:

~~~properties
server.error.include-binding-errors=never
~~~

Đồng thời, việc tắt `errors` trong default `/error` **không ngăn** một `@RestControllerAdvice` tự xây `fieldErrors` rồi trả về giá trị nhạy cảm. Khi muốn phản hồi validation hữu ích, hãy trả một danh sách lỗi đã chọn lọc (field public + mã ổn định + thông điệp an toàn), và không echo `rejectedValue` theo mặc định.

Lỗi JSON sai cú pháp cũng khác lỗi Bean Validation: `@RequestBody` có thể không deserialize được trước khi tới validation. Không dùng `include-binding-errors` như cơ chế duy nhất để quản lý lỗi nhập liệu.

## 10. include-path: mặc định luôn có thể thấy URL

Spring Boot 3.3 mặc định:

~~~properties
server.error.include-path=always
~~~

Do đó JSON lỗi mặc định thường có `"path": "/api/orders/42"`. Điều này có thể hữu ích cho client và log, nhưng cần cân nhắc nếu ứng dụng đặt thông tin nhạy cảm trong path.

Có thể chọn:

~~~properties
server.error.include-path=never
~~~

để không đưa thuộc tính `path` vào default error attributes. Tuy nhiên:
- URL có thể vẫn xuất hiện trong access logs, tracing, reverse proxy, browser history.
- Không nên thiết kế token/password/secret nằm trong URL dù đã tắt response path.
- Có thể dùng correlation ID để liên hệ lỗi với request thay vì phát tán nguyên đường dẫn.

`include-path` không thay `server.error.path`. Một cái quyết định **thuộc tính `path` trong response**, cái kia quyết định **mapping của error controller**.

## 11. Cấu hình an toàn cho production

Một cấu hình có chủ đích cho ứng dụng Spring Boot MVC public API:

~~~yaml
server:
  error:
    include-message: never
    include-exception: false
    include-stacktrace: never
    include-binding-errors: never
    include-path: never
~~~

Các thuộc tính trên điều khiển error attributes của cơ chế mặc định. `include-path=never` ở đây là lựa chọn giảm rò rỉ path cho ứng dụng có chính sách nghiêm ngặt; nếu client cần path, có thể giữ default `always` sau khi đánh giá contract và dữ liệu trên URL.

Không bắt buộc đặt tất cả nếu chúng trùng mặc định; việc khai báo tường minh giúp review chính sách. Quan trọng là **test runtime thực tế** và bảo đảm config không bị override bởi profile, environment variable hoặc deployment settings.

Không dùng:

~~~yaml
server:
  error:
    include-message: always
    include-stacktrace: always
    include-binding-errors: always
    include-exception: true
~~~

trên hệ thống public. Cấu hình trên là **ví dụ không an toàn cần tránh**, không phải hướng dẫn bật debug production.

Có thể tạo `application-local.yml` để debug trong môi trường máy cá nhân khi cần. Nhưng không dùng `on_param` như một công cụ hỗ trợ khách hàng công khai: nó cho người gọi kích hoạt tiết lộ chi tiết mà không cần quyền admin.

## 12. Error page HTML và whitelabel khác JSON response

Spring Boot có thể phục vụ một trang HTML dự phòng khi browser gửi `Accept: text/html` và lỗi được chuyển đến `/error`. Property:

~~~properties
server.error.whitelabel.enabled=true
~~~

bật whitelabel fallback mặc định. Đặt:

~~~properties
server.error.whitelabel.enabled=false
~~~

tắt trang fallback đó, nhưng **không có nghĩa vô hiệu hóa cơ chế `/error` hoặc tự làm sạch mọi JSON error**. Khi không có trang riêng, servlet container hoặc cơ chế khác có thể trả một trang lỗi khác; phải kiểm thử HTML thực tế.

Một giải pháp tốt cho ứng dụng server-rendered là tạo trang lỗi tùy chỉnh thân thiện, không chứa exception/stack trace, ví dụ template `src/main/resources/templates/error.html` nếu template engine phù hợp được dùng. Trang có thể hiển thị thông điệp chung và đường hỗ trợ, không đính kèm chi tiết hạ tầng.

Nội dung dành cho API consumer nên được thiết kế riêng; một trang HTML đẹp không giải quyết response JSON có thể lộ thông tin.

## 13. server.error.path và ranh giới với security

Theo mặc định:

~~~properties
server.error.path=/error
~~~

Có thể đổi mapping của error controller khi thực sự cần tích hợp với đường dẫn/architecture của ứng dụng, nhưng phải kiểm tra:
- Error dispatch từ servlet container có được cấu hình đúng không.
- Security filter chain có cho phép xử lý error dispatch hay gây vòng lặp 401/403 không.
- Custom controller/handler có xung đột mapping không.
- Reverse proxy/ingress có trả trang lỗi riêng trước khi request đến ứng dụng không.

Đổi `server.error.path` không làm lỗi 500 biến thành 200 và không đảm bảo mọi exception đều được bắt. Đừng “bảo mật” `/error` bằng cách đổi sang đường dẫn khó đoán: error dispatch vẫn có thể xảy ra và response cần chính sách dữ liệu an toàn.

Spring Security có thể trả 401 hoặc 403 bằng `AuthenticationEntryPoint` / `AccessDeniedHandler` riêng, không nhất thiết qua `BasicErrorController`. Do đó cần kiểm thử body 401/403 bên cạnh body 400/404/500.

## 14. Vì sao server.error.* không kiểm soát mọi lỗi?

Một số luồng không nhất thiết dùng `BasicErrorController`:

1. `@ExceptionHandler` trên controller.
2. `@RestControllerAdvice`, `ResponseEntityExceptionHandler` hoặc error contract tự thiết kế.
3. `ResponseStatusException` được resolver khác chuyển thành HTTP response.
4. Problem Details qua Spring Framework / `spring.mvc.problemdetails.enabled`.
5. Spring Security authentication/authorization handlers.
6. Reverse proxy, gateway, load balancer hoặc web application firewall trả lỗi trước Spring Boot.
7. WebFlux reactive error handler (khác pipeline Servlet MVC).

Ví dụ một advice **không an toàn**:

~~~java
@ExceptionHandler(Exception.class)
ResponseEntity<Map<String, String>> unsafe(Exception ex) {
    return ResponseEntity.status(500)
        .body(Map.of("detail", ex.getMessage()));
}
~~~

Cho dù `server.error.include-message=never`, code này vẫn tự trả `detail` từ exception message vì nó tạo response riêng.

Trong ứng dụng thật, hãy map exception theo loại nghiệp vụ, trả status phù hợp và dùng thông điệp **đã duyệt**. Tránh bắt mọi exception rồi tự động trả 500, vì có thể ghi đè status 400/404/409 vốn có.

## 15. Thiết kế API error contract an toàn

Đối với ứng dụng API, client nên nhận được:
- HTTP status đúng.
- Mã lỗi ổn định, ví dụ `BOOK_NOT_FOUND` hoặc `VALIDATION_FAILED`.
- Mô tả công khai có kiểm soát (không phải raw exception message).
- Correlation ID nếu hệ thống đã có cơ chế tạo/ghi nhận tương ứng.
- Danh sách field lỗi **chỉ gồm các field công khai**, không gồm giá trị nhạy cảm.

Ví dụ contract minh họa:

~~~json
{
  "code": "BOOK_NOT_FOUND",
  "message": "Không tìm thấy sách được yêu cầu",
  "requestId": "req-7f3a"
}
~~~

Đây là JSON do **ứng dụng tự thiết kế**, không phải shape mặc định của `BasicErrorController` và không được `server.error.*` tự sinh. `requestId` trong ví dụ là giá trị giả định; hệ thống thật phải có cơ chế tạo và gắn ID vào log/tracing nếu muốn truy vết.

Lỗi 500 thường nên trả thông điệp tổng quát, trong khi lỗi nghiệp vụ dự kiến có thể có mô tả cụ thể sau khi đã bảo đảm không lộ dữ liệu. Log nội bộ có thể ghi exception cause và context đã được làm sạch; client không cần biết class Java đã ném lỗi.

## 16. Ví dụ Spring Boot chạy được: quan sát error response mặc định

Tạo project **Spring Boot 3.3.x, Java 17+** với các dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đoạn trên là phần dependencies, không phải toàn bộ Gradle build file; cần plugin Spring Boot/Java và wrapper phù hợp.

Tạo file `src/main/java/com/example/demo/SafeErrorApplication.java`:

~~~java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SafeErrorApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeErrorApplication.class, args);
    }
}

record CreateAccountRequest(@NotBlank String displayName) {}

@RestController
@RequestMapping("/api/demo")
class DemoController {

    @GetMapping("/fail")
    public String fail() {
        // Chuỗi cố ý nhạy cảm CHỈ để kiểm thử không rò rỉ trong demo.
        throw new IllegalStateException(
            "PRIVATE_INTERNAL_DETAILS_DO_NOT_RETURN");
    }

    @PostMapping(
        path = "/accounts",
        consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreateAccountRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
~~~

Vì `fail()` ném exception không được handler nào trong demo tự xử lý, ở embedded Servlet runtime thông thường lỗi sẽ vào cơ chế error handling mặc định. Test sau kiểm tra response **không chứa** chi tiết nội bộ.

Tạo `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  error:
    include-message: never
    include-exception: false
    include-stacktrace: never
    include-binding-errors: never
    include-path: never
~~~

Ứng dụng không chứa custom `@RestControllerAdvice` hoặc `ErrorController`, vì mục tiêu của demo là kiểm tra chính **Boot default error path**. Nếu thêm advice bắt `Exception`, đường xử lý có thể khác và test phải được điều chỉnh.

### 16.1. Chạy và gọi API

Linux/macOS:

~~~bash
./gradlew bootRun
~~~

PowerShell trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Gọi endpoint phát lỗi:

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/demo/fail
~~~

Kỳ vọng status `500 Internal Server Error`. Body có thể gồm các field phổ biến như `timestamp`, `status`, `error`, nhưng không nên có `message`, `exception`, `trace`, `errors` hoặc `path` với cấu hình đã đặt.

Thử với query có vẻ yêu cầu debug:

~~~bash
curl -i -H "Accept: application/json" \
  "http://localhost:8080/api/demo/fail?trace=true&message=true&errors=true"
~~~

Với các giá trị `never`, request này **không được phép kích hoạt** các thuộc tính nhạy cảm của default error response.

Thử body validation:

~~~bash
curl -i -X POST http://localhost:8080/api/demo/accounts \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"displayName":""}'
~~~

Kỳ vọng 400 vì `@NotBlank`. Với `include-binding-errors=never`, default response không nên có danh sách `errors` mang giá trị input bị từ chối.

**Lưu ý:** response lỗi cụ thể phụ thuộc version, content negotiation và error mapping. Không lấy một body JSON minh họa rồi viết client parse cứng mọi field. Mục tiêu chính của demo là kiểm chứng status và **sự vắng mặt của các trường nhạy cảm**.

## 17. Test tích hợp HTTP thật để xác nhận không rò rỉ

Đối với cơ chế `/error`, **MockMvc không phải lúc nào mô phỏng đầy đủ servlet container error dispatch** giống request qua cổng HTTP thật. Một exception chưa được resolve trong MockMvc có thể được ném ra ở quá trình test thay vì chuyển thành response do `BasicErrorController` xử lý. Vì vậy, ví dụ dưới dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` cùng `TestRestTemplate` để kiểm tra error boundary trên embedded server.

Tạo `src/test/java/com/example/demo/SafeErrorApplicationTest.java`:

~~~java
package com.example.demo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.error.include-message=never",
        "server.error.include-exception=false",
        "server.error.include-stacktrace=never",
        "server.error.include-binding-errors=never",
        "server.error.include-path=never"
    })
class SafeErrorApplicationTest {

    @Autowired
    TestRestTemplate client;

    @Autowired
    ObjectMapper mapper;

    private static HttpHeaders jsonHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        return headers;
    }

    private void assertNoSensitiveFields(JsonNode body) {
        assertFalse(body.has("message"));
        assertFalse(body.has("exception"));
        assertFalse(body.has("trace"));
        assertFalse(body.has("errors"));
        assertFalse(body.has("path"));
    }

    @Test
    void unexpectedExceptionReturns500WithoutInternals()
            throws Exception {
        ResponseEntity<String> response = client.exchange(
            "/api/demo/fail?trace=true&message=true&errors=true",
            HttpMethod.GET,
            new HttpEntity<Void>(jsonHeaders()),
            String.class);

        assertEquals(500, response.getStatusCode().value());
        assertNotNull(response.getBody());
        JsonNode body = mapper.readTree(response.getBody());

        assertEquals(500, body.path("status").asInt());
        assertNoSensitiveFields(body);
        assertFalse(response.getBody().contains(
            "PRIVATE_INTERNAL_DETAILS_DO_NOT_RETURN"));
    }

    @Test
    void invalidBodyReturns400WithoutRejectedValues()
            throws Exception {
        HttpHeaders headers = jsonHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        ResponseEntity<String> response = client.exchange(
            "/api/demo/accounts",
            HttpMethod.POST,
            new HttpEntity<String>(
                "{\"displayName\":\"\"}", headers),
            String.class);

        assertEquals(400, response.getStatusCode().value());
        assertNotNull(response.getBody());
        JsonNode body = mapper.readTree(response.getBody());
        assertNoSensitiveFields(body);
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Test có tính xác thực cao hơn lời hứa cấu hình:
1. Nó chạy trên **embedded server thật** với port ngẫu nhiên.
2. Request JSON đi qua HTTP/Servlet processing.
3. Assert status 500 và 400.
4. Assert các field `message`, `exception`, `trace`, `errors`, `path` vắng mặt.
5. Assert một chuỗi cố ý nhạy cảm không đi ra response.
6. Dùng cả query `trace=true&message=true&errors=true` để bảo đảm policy `never` không bị người gọi bật ngược.

Các test này không chứng minh logs đã an toàn hoặc mọi custom error handler đều được kiểm soát. Cần thêm test cho các luồng riêng như Spring Security 401/403, business exception handler, gateway/proxy và Problem Details nếu ứng dụng sử dụng chúng.

## 18. Problem Details và @RestControllerAdvice

Spring Framework 6 hỗ trợ RFC 9457 Problem Details với media type `application/problem+json`. Trong Spring Boot 3.3 MVC có thể bật:

~~~properties
spring.mvc.problemdetails.enabled=true
~~~

Tùy exception và framework handling, body có thể chứa `type`, `title`, `status`, `detail` và `instance`. Những field đó **khác** các field `message`/`trace` của error attributes mặc định. `server.error.include-message=never` không phải bảo đảm rằng mọi `ProblemDetail.detail` đều được ẩn.

Khi thiết kế custom advice, có thể dùng `ProblemDetail` nhưng phải tự kiểm soát text công khai:

~~~java
@RestControllerAdvice
class ApiErrorAdvice {

    @ExceptionHandler(BookNotFoundException.class)
    ProblemDetail notFound(BookNotFoundException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Không tìm thấy sách được yêu cầu");
        problem.setTitle("Book not found");
        return problem;
    }
}
~~~

Đây là **snippet minh họa**, cần import và định nghĩa `BookNotFoundException`. Nó không được đưa vào ví dụ thực thi ở phần 16 vì sẽ thay đổi error flow.

Nên tránh:

~~~java
ProblemDetail.forStatusAndDetail(
    HttpStatus.INTERNAL_SERVER_ERROR, ex.getMessage());
~~~

với exception nội bộ. Nếu trả `ex.getMessage()` cho 500, bạn đã tạo một kênh rò rỉ mới ngay cả khi mọi `server.error.include-*` đều ở chế độ hạn chế.

## 19. WebFlux, proxy và tình huống ngoài phạm vi MVC

Spring WebFlux có pipeline reactive error handling riêng với `ErrorWebExceptionHandler`/`ErrorAttributes` và cơ chế trả response khác `BasicErrorController` của Servlet MVC. Một số cấu hình `server.error.*` vẫn liên quan đến error attributes trong hệ Boot, nhưng không nên suy đoán tất cả behavior MVC, error dispatch và JSON shape tương đương. Với Problem Details ở WebFlux, property phù hợp là:

~~~properties
spring.webflux.problemdetails.enabled=true
~~~

Khi sử dụng proxy/ingress/load balancer:
- HTTP 502/504 có thể do proxy sinh trước khi request tới Spring Boot.
- Proxy có thể thay body lỗi ứng dụng hoặc gửi trang HTML khác.
- CORS/security layer có thể trả 401/403 riêng.
- Đổi `server.error.include-stacktrace` không kiểm soát body do gateway tạo.

Cần kiểm thử ở **đường đi public thật** qua các hop cần thiết, không chỉ qua `localhost:8080`.

## 20. Logging an toàn và khả năng hỗ trợ điều tra

Giấu stack trace khỏi client không đồng nghĩa không ghi nhận thông tin cần thiết ở backend. Một chiến lược hợp lý:
- Error response có status, code công khai và request/correlation ID.
- Log nội bộ có timestamp, trace ID và exception phù hợp.
- Không log request body, password, token, API key hoặc dữ liệu nhận dạng khi không có lý do chính đáng.
- Định nghĩa retention, masking, quyền truy cập và audit đối với hệ thống log.
- Có dashboard cho tỉ lệ HTTP 4xx/5xx, latency và đường đi hệ thống.
- Trả hướng dẫn hỗ trợ dựa trên request ID thay vì nội dung exception.

Spring Boot Actuator/Micrometer/OpenTelemetry có thể cung cấp observability khi dependency/cấu hình tương ứng có mặt. Không giả định các thành phần đó được tự bật đầy đủ trong mọi ứng dụng.

Phải phân biệt log level với error response: `logging.level.root=DEBUG` không tự bắt buộc body HTTP có stack trace, còn `server.error.include-stacktrace=always` không đảm bảo log backend đã được ghi/giám sát thích hợp.

## 21. Những lỗi cấu hình dễ mắc

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| `include-message=always` ở production | Có thể lộ message nội bộ | Dùng `never`, tạo public error code riêng |
| `include-exception=true` | Lộ tên class/package exception | Giữ `false` |
| `include-stacktrace=on_param` trên API public | Caller có thể yêu cầu `?trace=true` | Dùng `never` |
| `include-binding-errors=always` | Có thể lộ field/rejectedValue | Dùng `never` và map field errors an toàn |
| Nhầm `include-path` với `path` | Đổi sai hành vi error endpoint | Phân biệt field trong body và mapping |
| Chỉ tắt whitelabel | JSON error vẫn có thể lộ dữ liệu | Kiểm thử JSON và HTML riêng |
| Tin rằng server.error.* che custom advice | Custom response vẫn lộ `ex.getMessage()` | Review `@RestControllerAdvice`/`ProblemDetail` |
| Đổi profile nhưng không test deployed config | Production vẫn giữ debug overrides | Integration test và kiểm tra môi trường |
| Dựa vào MockMvc cho mọi error-dispatch case | Có thể khác servlet container thật | Test `RANDOM_PORT` với HTTP client |
| Trả HTTP 200 cho mọi exception | Client/monitoring hiểu sai lỗi | Map đúng status 400/404/409/500 |
| Log raw credentials để debug | Rò rỉ qua log dù response an toàn | Masking, filtering, least privilege |

## 22. Checklist trước khi phát hành

- [ ] Đã xác nhận Spring Boot version và web stack Servlet hay Reactive.
- [ ] `server.error.include-message=never` trong môi trường public.
- [ ] `server.error.include-exception=false`.
- [ ] `server.error.include-stacktrace=never`, không dùng `on_param` công khai.
- [ ] `server.error.include-binding-errors=never`.
- [ ] Có quyết định rõ về `include-path` dựa trên hợp đồng API và dữ liệu URL.
- [ ] Đã kiểm tra cả `Accept: application/json` và `Accept: text/html`.
- [ ] Custom `@ExceptionHandler`/`@RestControllerAdvice` không echo raw exception message.
- [ ] Problem Details, security handlers và proxy responses được test riêng.
- [ ] Error status 4xx/5xx chính xác, không bọc mọi lỗi thành 200.
- [ ] Có cách truy vết lỗi qua request ID/log bảo mật.
- [ ] Không chứa password, token, SQL, stack trace hoặc internal hostnames trong response public.
- [ ] Có kiểm thử HTTP qua embedded server thật, không chỉ MockMvc, cho 400/404/500.

## 23. Tài liệu chính thức

- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): các property `server.error.include-*`, `server.error.path` và `whitelabel.enabled` cùng mặc định.
- [Spring Boot 3.3 — Servlet Web Applications / Error Handling](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): cơ chế `/error`, error controller, HTML/JSON response và Problem Details.
- [Spring Boot 3.3 — BasicErrorController API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/error/BasicErrorController.html): error attributes và các hàm kiểm soát việc hiển thị message, path, errors, trace.
- [Spring Framework — MVC Exceptions](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): `@ExceptionHandler` và cách xử lý exception của MVC.
- [Spring Framework — Error Responses / Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): RFC 9457 `ProblemDetail` và `ErrorResponse`.

**Ghi nhớ:** `server.error.*` giúp **giới hạn thông tin trong error response mặc định**, đặc biệt `message`, `exception`, `trace` và `errors`. Giữ các thuộc tính nhạy cảm ở chế độ không xuất ra client trong production, tránh `on_param` công khai, và kiểm thử cả custom error handler lẫn HTTP error dispatch thực tế. Mục tiêu là **client hiểu đúng lỗi mà không nhìn thấy nội tình hệ thống**.
