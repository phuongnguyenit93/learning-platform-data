# Cơ chế /error, BasicErrorController và ErrorAttributes trong Spring Boot Servlet

## Mục tiêu học tập

Trong ứng dụng **Spring Boot Servlet/Spring MVC**, không phải mọi lỗi HTTP đều được tạo trực tiếp bởi controller. Khi request gây lỗi mà phần MVC không xử lý xong, **Servlet container** có thể thực hiện một lượt **error dispatch** nội bộ tới một error page. Spring Boot tự đăng ký đường dẫn mặc định **/error**, đặt một **BasicErrorController** để tiếp nhận và lấy dữ liệu từ **ErrorAttributes** nhằm tạo phản hồi HTML hoặc JSON phù hợp.

Sau bài này, bạn có thể:

- Phân biệt exception được xử lý tại controller, DispatcherServlet và Servlet container.
- Mô tả luồng request ban đầu → error dispatch → /error → BasicErrorController.
- Giải thích vai trò của ErrorMvcAutoConfiguration, ErrorController, ErrorAttributes và DefaultErrorAttributes.
- Hiểu sự khác biệt giữa JSON error response, HTML error view, whitelabel page và trang lỗi riêng.
- Biết cấu hình server.error.* trong Spring Boot 3.5 và tên spring.web.error.* trong Spring Boot 4.x.
- Bổ sung một thuộc tính an toàn vào error body mà không thay toàn bộ error controller.
- Xử lý lỗi nghiệp vụ bằng @RestControllerAdvice/ProblemDetail trước khi cân nhắc thay cơ chế /error.
- Kiểm thử đúng cơ chế Servlet error page bằng một embedded server thực, tránh hiểu sai MockMvc.
- Nhận biết rủi ro lộ stacktrace, vòng lặp error dispatch, lỗi 404 bị proxy thay thế và response đã committed.

**Phạm vi:** Bài này tập trung **Servlet stack** (Spring MVC với Tomcat/Jetty/Undertow), không phải cơ chế error handler reactive của Spring WebFlux. Ví dụ runnable dùng **Spring Boot 3.5.x, Java 17+**, và phần gần cuối chỉ rõ khác biệt với Boot 4.x.

## 1. Ba tầng xử lý lỗi cần phân biệt

Một HTTP request đi vào ứng dụng Servlet có thể gặp lỗi ở những nơi khác nhau.

| Tầng | Thành phần | Ví dụ | Hướng xử lý điển hình |
|---|---|---|---|
| Controller/service | Method nghiệp vụ và exception | Không tìm thấy sản phẩm, dữ liệu không hợp lệ | @ExceptionHandler, ResponseEntity hoặc ResponseStatusException |
| Spring MVC | DispatcherServlet và HandlerExceptionResolver | Lỗi binding, thiếu route, method không phù hợp | MVC resolver trả response/sendError hoặc để lỗi đi tiếp |
| Servlet container | Tomcat/Jetty/Undertow | Exception chưa được xử lý, HTTP error status phù hợp | Error-page mapping → error dispatch tới /error |

**Không phải mọi response 4xx/5xx đều đi qua /error.** Chẳng hạn:

~~~java
@GetMapping("/api/items/{id}")
public ResponseEntity<Void> find(@PathVariable long id) {
    return ResponseEntity.notFound().build();
}
~~~

Controller trên đã tạo ResponseEntity 404. Nó không bắt buộc container phải mở một lượt error dispatch. Ngược lại, một exception không được MVC xử lý có thể khiến container thực hiện error dispatch và để BasicErrorController xây dựng phản hồi.

Đây là lý do khi debug cần hỏi **ai đã tạo response cuối cùng**, thay vì mặc định mọi HTTP 404 hoặc 500 đều do BasicErrorController.

## 2. Luồng mặc định của /error trong Servlet

Sơ đồ khái niệm:

~~~text
HTTP client
     |
     v
Embedded Servlet container (Tomcat/Jetty/Undertow)
     |
     v
Servlet filters (REQUEST dispatch)
     |
     v
DispatcherServlet
     |
     +----> HandlerMapping tìm controller
     |
     +----> HandlerAdapter gọi controller
     |           |
     |           +-- thành công -> response bình thường
     |           |
     |           +-- lỗi -> HandlerExceptionResolver chain
     |                         |
     |                         +-- đã xử lý -> response/status
     |                         |
     |                         +-- chưa xử lý / sendError
     |                                    |
     v                                    v
Container error-page processing <---------+
     |
     | ERROR dispatch (nếu cần và còn xử lý được)
     v
Configured error path (mặc định /error)
     |
     v
DispatcherServlet / BasicErrorController
     |
     +-- ErrorAttributes -> status, error, timestamp, path...
     |
     +-- Accept: text/html -> error view / HTML fallback
     |
     +-- Accept: application/json -> JSON error body
     |
     v
HTTP response cho client
~~~

Sơ đồ mô tả luồng **điển hình**, không phải một định luật cho mọi exception. Một HandlerExceptionResolver có thể xử lý lỗi bằng response ngay, Servlet container có thể từ chối dispatch khi response đã commit, và một reverse proxy còn có thể tự tạo error page của nó.

### Các sự kiện cần nhớ

1. Servlet container nhận request ban đầu với DispatcherType.REQUEST.
2. DispatcherServlet tìm và gọi handler theo mapping.
3. Nếu xảy ra exception, Spring MVC thử danh sách HandlerExceptionResolver.
4. Với lỗi không được xử lý hoặc response báo lỗi qua cơ chế error status của Servlet, container có thể tạo error dispatch.
5. Servlet container dùng error-page registration do Boot/cấu hình cung cấp để chọn /error.
6. Lượt dispatch mới mang DispatcherType.ERROR và các request attributes chứa thông tin lỗi.
7. BasicErrorController đọc dữ liệu thông qua ErrorAttributes, xác định status và representation.
8. Container gửi response cho client khi còn có thể ghi header/body.

Điều quan trọng nhất: **/error không chỉ là một URL để client gửi GET thủ công.** Nó chủ yếu là đích của một **internal Servlet error dispatch**, đi kèm metadata lỗi mà container cung cấp.

## 3. ErrorMvcAutoConfiguration thiết lập những gì?

Spring Boot tự cấu hình error handling cho ứng dụng Servlet thông qua **ErrorMvcAutoConfiguration** khi điều kiện phù hợp. Trong Spring Boot 3.5, class thuộc package:

~~~java
org.springframework.boot.autoconfigure.web.servlet.error.ErrorMvcAutoConfiguration
~~~

Auto-configuration này có thể:

- Cung cấp bean DefaultErrorAttributes nếu ứng dụng chưa cung cấp ErrorAttributes phù hợp.
- Tạo BasicErrorController nếu chưa có ErrorController thay thế.
- Cài đặt error page integration cho Servlet container.
- Cấu hình ErrorViewResolver để tìm HTML error views khi cần.
- Cung cấp fallback whitelabel error page trong trường hợp thích hợp và được bật.

Các điều kiện auto-configuration rất quan trọng. Nếu ứng dụng tự khai báo ErrorAttributes, Boot có thể giữ BasicErrorController nhưng dùng nguồn attributes do bạn cung cấp. Nếu ứng dụng tự khai báo ErrorController, Boot có thể không tạo BasicErrorController mặc định nữa.

### Ba vai trò dễ nhầm

| Thành phần | Câu hỏi nó trả lời |
|---|---|
| ErrorMvcAutoConfiguration | Khi khởi động, có cần tạo và đăng ký các bean xử lý lỗi mặc định không? |
| BasicErrorController | Khi request đi tới error mapping, status, headers, body hoặc view nên trả thế nào? |
| ErrorAttributes / DefaultErrorAttributes | Dữ liệu mô tả lỗi hiện tại là gì và cho phép lộ những trường nào? |

Không nên thêm một custom controller cùng mapping /error chỉ để bổ sung một field JSON nếu có thể dùng ErrorAttributes. Trùng route /error có thể dẫn tới ambiguous mapping hoặc vô hiệu hóa BasicErrorController mà không đủ mã thay thế.

## 4. BasicErrorController là gì?

**BasicErrorController** là implementation ErrorController mặc định cho Servlet stack của Spring Boot. Trong Spring Boot 3.5, package:

~~~java
org.springframework.boot.autoconfigure.web.servlet.error.BasicErrorController
~~~

Về mặt annotation, đường dẫn của nó được điều khiển bởi cấu hình error path; nếu không đổi, endpoint là /error.

Nó có hai hướng tạo response chủ đạo:

- **errorHtml(...)** với mapping produces text/html: trả **ModelAndView**, cho phép resolve trang lỗi HTML.
- **error(...)** cho response không ưu tiên HTML: trả **ResponseEntity<Map<String,Object>>** từ ErrorAttributes, thường được JSON converter serialize.

Khi client gửi:

~~~http
GET /api/unknown HTTP/1.1
Accept: application/json
~~~

và request rơi vào cơ chế error dispatch của container, BasicErrorController có thể trả JSON error body:

~~~json
{
  "timestamp": "2026-11-07T10:15:30.000+00:00",
  "status": 404,
  "error": "Not Found",
  "path": "/api/unknown"
}
~~~

**Đây là JSON minh họa, không phải snapshot bắt buộc.** Giá trị timestamp, path, fields và serialization phụ thuộc phiên bản, thuộc tính include-*, cause và error handling. Theo mặc định Boot 3.5 không cần đưa message hoặc stacktrace vào JSON.

### HTML và Accept header

Nếu trình duyệt yêu cầu HTML:

~~~http
GET /api/unknown HTTP/1.1
Accept: text/html
~~~

BasicErrorController thường chọn nhánh HTML. Nó thử tìm view/template lỗi phù hợp, rồi dùng fallback whitelabel nếu được bật và không có view thích hợp.

**Accept không phải Content-Type.** Accept cho biết client muốn nhận dạng response nào; Content-Type thường mô tả định dạng body client đã gửi. Nếu cùng URL có lúc trả HTML, lúc trả JSON, hãy kiểm tra request header Accept trước khi kết luận server không nhất quán.

Không nên dùng User-Agent làm cơ chế quyết định duy nhất về response type. API clients thường cần gửi **Accept: application/json** rõ ràng khi muốn JSON.

## 5. ErrorAttributes và DefaultErrorAttributes

Trong Spring Boot 3.5 Servlet:

~~~java
org.springframework.boot.web.servlet.error.ErrorAttributes
org.springframework.boot.web.servlet.error.DefaultErrorAttributes
org.springframework.boot.web.error.ErrorAttributeOptions
~~~

**ErrorAttributes** là hợp đồng đọc dữ liệu lỗi của request hiện tại:

~~~java
Map<String, Object> getErrorAttributes(
    WebRequest webRequest,
    ErrorAttributeOptions options
);
~~~

Nó cũng có getError(WebRequest) để lấy Throwable gốc nếu có. ErrorAttributeOptions cho phép BasicErrorController quyết định có đưa message, exception, binding errors, trace hoặc path vào dữ liệu phản hồi hay không.

**DefaultErrorAttributes** là implementation mặc định. Nó thường cung cấp các trường, khi có thể xác định và được phép hiển thị:

| Trường | Ý nghĩa | Lưu ý |
|---|---|---|
| timestamp | Thời điểm lấy error attributes | Không phải timestamp nghiệp vụ hoặc trace ID |
| status | HTTP status | Ví dụ 404, 500 |
| error | Tên/lý do tóm tắt của status | Ví dụ Not Found |
| exception | Tên class exception | Có thể bị ẩn theo cấu hình |
| message | Mô tả lỗi | Có thể bị ẩn để tránh lộ dữ liệu |
| errors | Chi tiết binding/validation errors | Có thể bị ẩn và cần xử lý nội dung nhạy cảm |
| trace | Exception stack trace | Không nên public trên production |
| path | Request path gây lỗi | Tùy chính sách include-path/version |

**ErrorAttributes không nhất thiết tạo HTTP status.** Nó cung cấp dữ liệu để response/error view sử dụng. Status thực tế có thể đến từ Servlet error attributes và controller logic.

Trong Spring Boot 3.5, DefaultErrorAttributes còn tham gia như một HandlerExceptionResolver có ưu tiên cao để ghi nhận exception. Không suy ra rằng nó tự chuyển mọi lỗi thành response JSON: chức năng lưu dấu exception và chức năng render response có thể nằm ở các bước khác nhau.

### ErrorAttributeOptions

Các lựa chọn hữu ích gồm:

~~~java
ErrorAttributeOptions options =
    ErrorAttributeOptions.defaults()
        .including(ErrorAttributeOptions.Include.MESSAGE);
~~~

Đoạn trên chỉ minh họa API, không phải lời khuyên bật MESSAGE cho môi trường production. Application properties của Spring Boot và BasicErrorController quyết định những lựa chọn thực sự đưa ra response. Nếu custom ErrorAttributes tự bỏ qua options, bạn có thể vô tình làm lộ nội dung bị cấu hình là ẩn.

## 6. Servlet error dispatch mang những request attributes nào?

Servlet API định nghĩa các attributes dùng khi container dispatch tới error page. Trong Spring Boot 3.5/Spring Framework 6 dựa trên Jakarta Servlet, đọc từ:

~~~java
import jakarta.servlet.RequestDispatcher;
~~~

Các key phổ biến:

| Constant | Ý nghĩa |
|---|---|
| RequestDispatcher.ERROR_STATUS_CODE | Mã HTTP status của lỗi |
| RequestDispatcher.ERROR_MESSAGE | Mô tả lỗi từ container |
| RequestDispatcher.ERROR_EXCEPTION | Throwable gắn với error dispatch, nếu có |
| RequestDispatcher.ERROR_EXCEPTION_TYPE | Loại exception |
| RequestDispatcher.ERROR_REQUEST_URI | URI của request ban đầu gây lỗi |
| RequestDispatcher.ERROR_SERVLET_NAME | Tên servlet liên quan |

Ví dụ **đoạn minh họa bên trong một servlet/error handler**, không phải controller đầy đủ:

~~~java
Object status = request.getAttribute(
    RequestDispatcher.ERROR_STATUS_CODE
);

Object originalUri = request.getAttribute(
    RequestDispatcher.ERROR_REQUEST_URI
);
~~~

Không phải mọi loại error dispatch đều có đầy đủ mọi attribute. Ví dụ 404 do thiếu route có thể không có Throwable tương ứng như lỗi ném IllegalStateException.

### DispatcherType.REQUEST khác DispatcherType.ERROR

Request ban đầu thường được gắn DispatcherType.REQUEST. Lượt forward sang error page của container thường dùng DispatcherType.ERROR.

Một Servlet Filter có thể được đăng ký cho REQUEST, ERROR hoặc cả hai. Vì vậy log của filter có thể chạy hai lần trong cùng một request lỗi, hoặc hoàn toàn không chạy ở lượt ERROR nếu filter mapping không bao gồm dispatcher type đó.

Không tự kết luận “controller bị gọi hai lần” chỉ từ hai dòng log. Hãy log path, dispatcher type và correlation ID để phân biệt.

## 7. /error khác với @ExceptionHandler và @RestControllerAdvice ra sao?

**@ExceptionHandler** và **@RestControllerAdvice** là điểm xử lý lỗi trong Spring MVC. Chúng thường phù hợp với lỗi nghiệp vụ hoặc exception có schema cụ thể:

~~~java
@RestControllerAdvice
public class ApiErrorAdvice {

    @ExceptionHandler(ItemNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            ItemNotFoundException error) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND, "Item không tồn tại"
        );
        problem.setTitle("Item not found");

        return ResponseEntity
            .status(HttpStatus.NOT_FOUND)
            .body(problem);
    }
}
~~~

Đây là class minh họa; cần ItemNotFoundException và imports từ Spring MVC. Khi resolver xử lý exception thành công, request có thể kết thúc **ngay tại MVC**, không cần đi qua BasicErrorController.

So sánh:

| Tiêu chí | @ExceptionHandler / @RestControllerAdvice | BasicErrorController /error |
|---|---|---|
| Vị trí | Spring MVC exception resolution | Error-page fallback ở Servlet stack |
| Dùng tốt cho | Lỗi nghiệp vụ có thể phân loại cụ thể | Lỗi còn lại, HTTP status/error dispatch toàn ứng dụng |
| Response schema | DTO/ProblemDetail do ứng dụng chọn | ErrorAttributes + HTML/JSON mặc định |
| Kiểm soát status | Trong handler | Từ error status và logic controller |
| Bao phủ lỗi ngoài MVC | Không phải mọi lỗi | Có thể xử lý nhiều lỗi do Servlet container dispatch |
| Yêu cầu error dispatch | Không nhất thiết | Thường có với lỗi được container điều hướng |

**Thứ tự ưu tiên thực tế phụ thuộc loại lỗi và cách MVC/controller/container xử lý.** Đừng cố “ép mọi exception vào /error” nếu @RestControllerAdvice đã tạo response hợp lệ.

### Không nhầm ResponseStatusException với /error

~~~java
throw new ResponseStatusException(
    HttpStatus.NOT_FOUND, "Item not found"
);
~~~

Spring MVC có các resolver để xử lý ResponseStatusException. Tùy quá trình xử lý, resolver có thể đặt status hoặc gọi cơ chế sendError dẫn tới lượt xử lý lỗi khác. Không có quy tắc “mọi ResponseStatusException chắc chắn trả JSON từ BasicErrorController”.

### Trả ResponseEntity 404 trực tiếp

~~~java
return ResponseEntity.notFound().build();
~~~

Đoạn này chỉ định HTTP 404 không có body. Nếu API cần body lỗi chuẩn, viết rõ response hoặc dùng exception handler, không dựa vào /error để tự bổ sung body cho ResponseEntity mà controller đã hoàn tất.

## 8. Cấu hình server.error.* trong Spring Boot 3.5

Spring Boot 3.5 hỗ trợ những thuộc tính sau:

~~~properties
server.error.path=/error
server.error.include-exception=false
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-binding-errors=never
server.error.include-path=always
server.error.whitelabel.enabled=true
~~~

Đây là bộ giá trị minh họa tương ứng hướng cấu hình mặc định của Boot 3.5, không phải lời khuyên phải copy hết vào mọi ứng dụng. Nếu không cần thay đổi, để Boot sử dụng mặc định thường đơn giản hơn.

| Thuộc tính | Mục đích |
|---|---|
| server.error.path | Đường dẫn error controller mặc định, thường là /error |
| server.error.include-exception | Có xuất tên exception class không |
| server.error.include-message | Khi nào đưa message vào body lỗi |
| server.error.include-stacktrace | Khi nào đưa trace vào body |
| server.error.include-binding-errors | Khi nào đưa lỗi binding/validation vào body |
| server.error.include-path | Khi nào xuất path |
| server.error.whitelabel.enabled | Bật/tắt whitelabel HTML fallback |

### never, always và on_param

Những thuộc tính include-message, include-stacktrace và include-binding-errors thường hỗ trợ ba chế độ:

- **never**: không xuất dữ liệu tương ứng.
- **always**: luôn xuất dữ liệu tương ứng nếu có.
- **on_param**: xuất khi request có query parameter được hỗ trợ.

on_param hữu ích để debug trong môi trường giới hạn, nhưng **không phải một cơ chế bảo vệ bí mật**. Người dùng bên ngoài cũng có thể thử thêm query parameter. Không bật on_param cho stacktrace trên public production endpoint nếu không có biện pháp bảo vệ thực sự.

### Chính sách an toàn cho production

Thông thường:

~~~properties
server.error.include-exception=false
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-binding-errors=never
~~~

Thông tin chi tiết nên được ghi vào server log theo chính sách bảo mật, gắn correlation/request ID và chỉ trả một mã lỗi ổn định, thông điệp an toàn cho client. Không dùng stacktrace như response body để thuận tiện debug.

### server.error.whitelabel.enabled=false có ý nghĩa gì?

Cấu hình:

~~~properties
server.error.whitelabel.enabled=false
~~~

chủ yếu **tắt fallback whitelabel HTML view**, không đồng nghĩa tắt /error, BasicErrorController hay error dispatch. Nếu không có view HTML phù hợp, người dùng có thể thấy response khác hoặc error page của container tùy cấu hình. Không dùng property này để tuyên bố API luôn trả JSON cho mọi client.

## 9. Spring Boot 4.x đổi package và namespace cấu hình

Đây là khác biệt quan trọng khi dự án nâng từ Boot 3.5 lên Boot 4.x.

| Thành phần | Spring Boot 3.5 | Spring Boot 4.x |
|---|---|---|
| Auto-config MVC error | org.springframework.boot.autoconfigure.web.servlet.error.ErrorMvcAutoConfiguration | org.springframework.boot.webmvc.autoconfigure.error.ErrorMvcAutoConfiguration |
| BasicErrorController | org.springframework.boot.autoconfigure.web.servlet.error.BasicErrorController | org.springframework.boot.webmvc.autoconfigure.error.BasicErrorController |
| ErrorAttributes | org.springframework.boot.web.servlet.error.ErrorAttributes | org.springframework.boot.webmvc.error.ErrorAttributes |
| DefaultErrorAttributes | org.springframework.boot.web.servlet.error.DefaultErrorAttributes | org.springframework.boot.webmvc.error.DefaultErrorAttributes |
| Error settings prefix | server.error.* | spring.web.error.* |
| Error path property | server.error.path | spring.web.error.path |
| Whitelabel property | server.error.whitelabel.enabled | spring.web.error.whitelabel.enabled |

Ví dụ Boot 4.x:

~~~properties
spring.web.error.path=/error
spring.web.error.include-message=never
spring.web.error.include-stacktrace=never
spring.web.error.include-binding-errors=never
spring.web.error.whitelabel.enabled=true
~~~

Đừng copy nguyên cấu hình server.error.* của Boot 3.5 vào Boot 4 rồi tin chắc nó vẫn có hiệu lực. Kiểm tra **Common Application Properties** và **Spring Boot 4.0 Configuration Changelog** tương ứng version đang chạy.

Một số cấu hình khác như ProblemDetail, HandlerExceptionResolver và Spring Security cũng có thay đổi package/API qua major versions. Ví dụ runnable của bài được cố định ở Boot 3.5 để có thể dùng các imports nhất quán.

## 10. Tùy chỉnh nhẹ bằng ErrorAttributes: ưu tiên giữ BasicErrorController

Nếu nhu cầu là bổ sung một field an toàn vào JSON lỗi, **không cần viết lại ErrorController**. Trong Boot 3.5, bạn có thể tạo một subclass của DefaultErrorAttributes.

Ví dụ thêm tên ứng dụng cố định:

**File src/main/java/com/example/errors/SafeErrorAttributes.java**

~~~java
package com.example.errors;

import java.util.Map;

import org.springframework.stereotype.Component;
import org.springframework.boot.web.error.ErrorAttributeOptions;
import org.springframework.boot.web.servlet.error.DefaultErrorAttributes;
import org.springframework.web.context.request.WebRequest;

@Component
public class SafeErrorAttributes extends DefaultErrorAttributes {

    @Override
    public Map<String, Object> getErrorAttributes(
            WebRequest webRequest,
            ErrorAttributeOptions options) {

        Map<String, Object> attributes =
            super.getErrorAttributes(webRequest, options);

        attributes.put("application", "error-demo");
        return attributes;
    }
}
~~~

Điều quan trọng:

1. Đây là bean thuộc loại ErrorAttributes, nên Boot có thể không tạo DefaultErrorAttributes bean thứ hai.
2. BasicErrorController mặc định vẫn sử dụng ErrorAttributes do container Spring cung cấp.
3. super.getErrorAttributes(webRequest, options) giữ cách áp dụng include settings của Boot.
4. Ta chỉ thêm application là chuỗi cố định, không đưa exception message hoặc stacktrace chưa được phép.
5. Chỉ HTML hoặc JSON body do BasicErrorController tạo mới hiển thị dữ liệu này theo cách tương ứng; không áp đặt nó lên mọi ResponseEntity do controller khác trả.

### Nếu muốn thêm correlation ID

Có thể thêm request ID khi nó được tạo bởi một filter đáng tin cậy. Không coi một header tùy ý do client gửi như ID đã được xác thực. Nếu lấy ID từ MDC hoặc request attributes, hãy kiểm tra vòng đời filter, sanitization, độ dài và tính nhất quán giữa REQUEST/ERROR dispatch.

Ví dụ trên cố tình không phụ thuộc correlation ID để thể hiện một custom ErrorAttributes có thể compile và được kiểm tra đơn giản trong ứng dụng Spring Boot 3.5.

### Tại sao không trả raw exception message mặc định?

Exception có thể chứa câu SQL, tên table, tên class nội bộ, file path, credential fragment hoặc chi tiết hệ thống. Nếu response cung cấp tất cả chi tiết, client và logs bên ngoài có thể lưu các giá trị nhạy cảm. Hãy tách:

- **Mã lỗi ổn định, status và correlation ID** cho client.
- **Root cause và stacktrace** cho logging/observability có kiểm soát.

## 11. Tạo trang HTML lỗi riêng

Khi phục vụ browser, có thể bổ sung HTML error pages thay cho whitelabel.

Trong dự án MVC có template engine như Thymeleaf, đặt:

~~~text
src/main/resources/templates/error/404.html
src/main/resources/templates/error/5xx.html
src/main/resources/templates/error.html
~~~

Cách resolver chọn view tùy status và tài nguyên/template hiện có. Các tên 404, 5xx và error là conventions phổ biến trong Spring Boot. **Chỉ đặt file trong templates không làm nó được render nếu thiếu template engine.**

Nếu không dùng template engine, có thể thêm static HTML error page ở những vị trí được Boot hỗ trợ, ví dụ:

~~~text
src/main/resources/public/error/404.html
src/main/resources/public/error/5xx.html
~~~

Tùy phiên bản và cấu hình resource handling, resolver sẽ chọn error page phù hợp. Để tránh hiểu nhầm, hãy thử request thực tế với Accept: text/html sau khi đóng gói ứng dụng JAR.

### Phân biệt HTML view với JSON fallback

Một trang HTML đặt trong templates/error/404.html không nhất thiết làm mọi API 404 trở thành HTML. BasicErrorController vẫn có nhánh xử lý phù hợp với Accept và content negotiation; client JSON thường nhận JSON lỗi mặc định trừ khi bạn đã thay cơ chế.

### Đừng đặt logic nhạy cảm trong error template

Error page có thể nhận metadata lỗi. Không tự in exception class, request params, stacktrace, SQL query hoặc input user vào HTML. Nếu cần thông tin hỗ trợ, hiển thị một thông báo thân thiện và correlation ID an toàn.

## 12. Khi nào nên thay ErrorController?

Thay ErrorController đồng nghĩa bạn nhận trách nhiệm về fallback error responses của Servlet stack. Đây là giải pháp cần cân nhắc khi:

- API toàn hệ thống phải tuân thủ error envelope đặc thù, và yêu cầu áp dụng cả lỗi do container dispatch.
- Có thêm media type riêng bên cạnh HTML/JSON.
- Kiểm soát error view/status hoàn toàn theo yêu cầu của một framework tích hợp.

Nếu chỉ cần đổi message của lỗi nghiệp vụ, dùng @RestControllerAdvice. Nếu chỉ cần thêm field trong default error body, dùng ErrorAttributes. Nếu cần trang web riêng, dùng template/static error view trước.

### Những trách nhiệm của custom ErrorController

Một custom ErrorController cần:

- Đăng ký mapping /error (hoặc error path đã cấu hình).
- Phân biệt HTML và JSON nếu ứng dụng phục vụ cả browser và API.
- Đọc Servlet error metadata và tạo status đúng.
- Không trả 200 cho lỗi 404/500.
- Tránh log hoặc trả dữ liệu nhạy cảm.
- Không tạo vòng lặp exception → /error → exception.
- Tương thích Spring Security, filters, DispatcherType.ERROR, context path và gateway.
- Có integration tests chạy server thật.

**Không khai báo hai controller cùng mapping /error** mà không biết bean nào được Boot tạo. Spring Boot tự rút lui với một ErrorController bean tùy chỉnh theo điều kiện auto-config, nhưng mapping của chính ứng dụng vẫn phải được kiểm soát.

### Mở rộng BasicErrorController

Trong Spring Boot 3.5, BasicErrorController có thể được kế thừa để bổ sung một @RequestMapping với **produces** cho media type mới. Nhưng khi custom class trở thành ErrorController thay thế, bạn cần kiểm tra constructor, mapping và cả nhánh HTML/JSON. Khả năng này được Spring Boot tài liệu hóa; không dùng inheritance chỉ để đổi một field mà ErrorAttributes đã giải quyết được.

## 13. Ví dụ Java 17+ runnable: Servlet /error và ErrorAttributes

Bài demo sử dụng **Spring Boot 3.5.x**, Java 17+ và Spring MVC, với mục tiêu:

- GET /api/ok trả 200.
- GET /api/boom ném exception chưa được xử lý, dẫn đến error dispatch và status 500.
- GET /missing-url với Accept: application/json trả 404 theo cơ chế error handling.
- Custom ErrorAttributes thêm trường application nếu request thực sự được BasicErrorController xử lý.
- @RestControllerAdvice xử lý một lỗi nghiệp vụ riêng mà không cần dùng /error.

### 13.1. Dependencies

Tạo project Spring Boot 3.5 từ Spring Initializr có Spring Web và Spring Boot Test. Nếu dùng Maven, phần dependencies gồm:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Không thêm starter WebFlux vào demo này. Muốn kiểm tra error dispatch của Servlet, dự án phải chạy **Servlet web application**.

### 13.2. Application class

**File src/main/java/com/example/errors/ErrorApplication.java**

~~~java
package com.example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorApplication.class, args);
    }
}
~~~

### 13.3. Controller

**File src/main/java/com/example/errors/DemoController.java**

~~~java
package com.example.errors;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/ok")
    public Map<String, String> ok() {
        return Map.of("result", "ok");
    }

    @GetMapping("/api/boom")
    public String boom() {
        throw new IllegalStateException(
            "internal-debug-message-do-not-expose"
        );
    }

    @GetMapping("/api/business")
    public String business() {
        throw new IllegalArgumentException("invalid business input");
    }

    @GetMapping("/api/direct")
    public ResponseEntity<Map<String, String>> direct() {
        return ResponseEntity
            .status(HttpStatus.CONFLICT)
            .body(Map.of("code", "ALREADY_EXISTS"));
    }
}
~~~

Dòng import ResponseEntity/HttpStatus là từ Spring Framework. GET /api/boom là lỗi server được ném có chủ đích để kiểm tra fallback, **không** phải mẫu production để giữ exception cố ý. Câu message dùng trong test chỉ giúp xác nhận thông tin nội bộ không xuất ra response mặc định.

### 13.4. Custom ErrorAttributes

**File src/main/java/com/example/errors/SafeErrorAttributes.java**

Dùng nguyên class đầy đủ ở phần 10. Nó có @Component, kế thừa DefaultErrorAttributes, gọi super rồi thêm trường application.

### 13.5. @RestControllerAdvice cho lỗi nghiệp vụ

**File src/main/java/com/example/errors/BusinessErrorAdvice.java**

~~~java
package com.example.errors;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class BusinessErrorAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ProblemDetail> invalidInput(
            IllegalArgumentException ex) {

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "Yêu cầu không hợp lệ"
        );
        body.setTitle("Invalid input");

        return ResponseEntity
            .badRequest()
            .body(body);
    }
}
~~~

Ở đây body có detail cố định an toàn, không dùng ex.getMessage() để phản chiếu giá trị đầu vào. Handler chỉ bắt IllegalArgumentException, nên IllegalStateException từ /api/boom không bị nó bắt.

Nếu Spring Security được thêm, cần bảo đảm error handling không vô tình bypass hoặc lặp authentication; xem thêm phần 17.

### 13.6. application.properties

**File src/main/resources/application.properties**

~~~properties
server.port=8080
server.error.include-exception=false
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-binding-errors=never
server.error.include-path=always
~~~

Giữ mặc định server.error.path=/error và không tự thay BasicErrorController.

### 13.7. Chạy project

Từ thư mục chứa Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Với Windows:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Thử:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/ok
curl -i -H "Accept: application/json" http://localhost:8080/api/boom
curl -i -H "Accept: application/json" http://localhost:8080/missing-url
curl -i -H "Accept: application/json" http://localhost:8080/api/business
curl -i -H "Accept: application/json" http://localhost:8080/api/direct
~~~

Kết quả **cần kiểm tra**:

| Endpoint | HTTP status kỳ vọng | Đường xử lý |
|---|---|---|
| /api/ok | 200 | Controller bình thường |
| /api/boom | 500 | Unhandled exception → container error dispatch → /error |
| /missing-url | 404 | Missing route → MVC/container error handling → /error trong cấu hình demo |
| /api/business | 400 | @RestControllerAdvice |
| /api/direct | 409 | Controller trả ResponseEntity trực tiếp |

Với /api/boom và /missing-url, JSON lỗi do BasicErrorController tạo thường chứa trường application: "error-demo", status tương ứng và các metadata an toàn theo config. Với /api/business, @RestControllerAdvice trực tiếp trả ProblemDetail; đừng kỳ vọng tự có trường application của ErrorAttributes. Với /api/direct, controller trả code=ALREADY_EXISTS; cũng không cần đi qua /error.

**Không so sánh cứng toàn bộ JSON lỗi** vì timestamp, field path và các thuộc tính Boot có thể thay đổi giữa phiên bản. Hãy kiểm tra những field do bạn kiểm soát và status bắt buộc.

## 14. Kiểm thử error dispatch: vì sao MockMvc không đủ?

Đây là một điểm rất dễ bỏ sót. MockMvc mô phỏng tầng Spring MVC mà **không khởi động đầy đủ Servlet container**. Spring Boot ghi rõ rằng cơ chế error page phụ thuộc container, vì vậy MockMvc không trực tiếp kiểm tra được việc forward tới custom error page hoặc toàn bộ /error flow.

| Loại kiểm thử | Kiểm được gì tốt? | Không nên mặc định kiểm được gì? |
|---|---|---|
| Unit test ErrorAttributes | Map fields và options khi cung cấp WebRequest thích hợp | Servlet dispatch thực |
| MockMvc | Controller mapping, @ExceptionHandler, status/body MVC | Container error-page registration/forward |
| @SpringBootTest RANDOM_PORT | Servlet container thật, error dispatch, end-to-end HTTP | Không mặc định mô phỏng proxy bên ngoài |
| Browser/curl | HTML/JSON negotiation, status và header thực tế | Không khẳng định business rollback/transaction |

Vì vậy, dùng RANDOM_PORT cho test quan trọng nhất của bài học.

### 14.1. Integration test với TestRestTemplate

Với Spring Boot 3.5, file:

**src/test/java/com/example/errors/ErrorDispatchIntegrationTest.java**

~~~java
package com.example.errors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ErrorDispatchIntegrationTest {

    @Autowired
    private TestRestTemplate restTemplate;

    private ResponseEntity<String> getJson(String path) {
        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));

        return restTemplate.exchange(
            path,
            HttpMethod.GET,
            new HttpEntity<>(headers),
            String.class
        );
    }

    @Test
    void missingRouteGoesThroughDefaultErrorController() {
        ResponseEntity<String> response = getJson("/missing-url");

        assertThat(response.getStatusCode())
            .isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(response.getBody())
            .contains("\"status\":404")
            .contains("\"application\":\"error-demo\"");
    }

    @Test
    void unhandledExceptionDoesNotExposeInternalMessage() {
        ResponseEntity<String> response = getJson("/api/boom");

        assertThat(response.getStatusCode())
            .isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
        assertThat(response.getBody())
            .contains("\"status\":500")
            .contains("\"application\":\"error-demo\"")
            .doesNotContain("internal-debug-message-do-not-expose");
    }

    @Test
    void controllerAdviceHandlesBusinessException() {
        ResponseEntity<String> response = getJson("/api/business");

        assertThat(response.getStatusCode())
            .isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(response.getBody())
            .contains("Yêu cầu không hợp lệ")
            .doesNotContain("\"application\":\"error-demo\"");
    }

    @Test
    void directResponseEntityDoesNotNeedErrorDispatch() {
        ResponseEntity<String> response = getJson("/api/direct");

        assertThat(response.getStatusCode())
            .isEqualTo(HttpStatus.CONFLICT);
        assertThat(response.getBody())
            .contains("ALREADY_EXISTS")
            .doesNotContain("\"application\":\"error-demo\"");
    }
}
~~~

Các assert cố ý không kiểm tra timestamp, ordering hoặc media-type parameters. Giá trị error status và application là những phần quan trọng của hợp đồng demo. Với một server dùng JSON pretty-print toàn cục, kiểm tra chuỗi chính xác "\"status\":404" có thể cần đổi sang JSONPath/JsonNode; bài demo mặc định không bật pretty-print.

### 14.2. Kiểm thử browser HTML

Chạy ứng dụng rồi gọi:

~~~bash
curl -i -H "Accept: text/html" http://localhost:8080/missing-url
~~~

Nếu không có template/static error page và whitelabel được bật, bạn thường thấy HTML fallback. Nếu đặt error/404.html, kết quả có thể đổi sang view riêng.

Đừng test HTML bằng cách gõ thẳng /error không có error metadata rồi cho rằng đó là request 404 thực tế. Cần request một URL gây lỗi và để container dispatch.

## 15. Có thể tùy chỉnh /error bằng error page registration không?

Servlet container cho phép định nghĩa error page theo status hoặc exception type. Trong Spring Boot có các extension points để đăng ký error pages với embedded server. Ví dụ API tầng container là **ErrorPage** và các tùy chỉnh container factory.

Tuy nhiên, tự thêm error pages có thể thay thứ tự xử lý và làm request không còn đi qua BasicErrorController như mặc định. Nếu có requirement như một trang HTML riêng cho 404 nhưng vẫn muốn giữ JSON error defaults, thường nên bắt đầu bằng **error views** thay vì thay error-page mapping.

Một ví dụ cấu hình nâng cao dạng pseudocode:

~~~text
HTTP 404 -> custom /not-found page
HTTP 500 -> /error
~~~

Nếu áp dụng nó, cần kiểm tra: exception context, status code, security filter dispatcher type, static resources, redirect/forward và client Accept. Không dùng cấu hình này chỉ để đổi một thông báo trong JSON 404.

### WAR deployment và ErrorPageFilter

Với ứng dụng WAR triển khai vào external Servlet container, Spring Boot có thể sử dụng **ErrorPageFilter** để chuyển request lỗi tới error page thích hợp. Cơ chế và giới hạn khác embedded-server error page registration.

ErrorPageFilter chỉ forward được nếu response chưa commit. Vì vậy lỗi phát sinh sau khi dữ liệu đã được flush có thể không còn tạo được HTML/JSON error page chuẩn. Nếu app chạy sau reverse proxy, proxy cũng có thể thay body/status của backend bằng trang 502/503 riêng.

## 16. Những trường hợp không đi qua /error như bạn tưởng

### 16.1. @ExceptionHandler đã xử lý lỗi

Khi advice trả ResponseEntity<ProblemDetail>, Spring MVC có thể coi exception đã được giải quyết. BasicErrorController không cần tham gia.

### 16.2. Controller chủ động trả 400/404/409

Trả ResponseEntity.status(...).body(...) là một response HTTP hợp lệ. Status thuộc nhóm lỗi **không tự chứng minh** container đã error-dispatch.

### 16.3. Response đã committed

Nếu servlet/controller đã gửi headers hoặc một phần body rồi mới ném exception, không thể bảo đảm server tạo một response lỗi mới. Ghi đè status/body sau commit có thể bất khả thi.

### 16.4. Spring Security trả lỗi ở filter chain

Spring Security có cơ chế riêng cho authentication (401) và authorization (403) thông qua filter/entry point/access denied handler. Những phản hồi này có thể được tạo mà không đi tới BasicErrorController. Khi cấu hình ERROR dispatcher type, cần kiểm tra security matchers để error dispatch không bị từ chối lần nữa.

### 16.5. Lỗi đến từ reverse proxy

Gateway hoặc load balancer có thể trả 404/502/503/504 trước khi request tới Boot. ErrorAttributes của ứng dụng không thể sửa response mà nó không tham gia tạo.

### 16.6. Lỗi từ static resources hoặc URL không có handler

Spring MVC và Boot có nhiều resolver/resource handler. Thiếu tài nguyên tĩnh, thiếu route, method không phù hợp và exception từ converter có thể đi qua những nhánh xử lý khác nhau trước khi đến fallback. Nên kiểm tra cả request path lẫn exception type thực tế, không suy ra dựa vào status cuối cùng.

## 17. Security và observability của /error

### Bảo vệ metadata lỗi

Trên production, không cho client tự yêu cầu stacktrace chỉ bằng thêm query parameter. Tránh include-message=always khi thông báo exception chứa dữ liệu nhạy cảm.

Một error response an toàn có thể cung cấp:

~~~json
{
  "status": 500,
  "code": "INTERNAL_ERROR",
  "message": "Hệ thống chưa thể xử lý yêu cầu",
  "requestId": "a1b2c3d4"
}
~~~

Đây là **schema minh họa do ứng dụng tự thiết kế**, không phải schema mặc định của BasicErrorController. Nếu muốn schema nhất quán trên mọi lỗi, cần phối hợp advice, ErrorAttributes và các tầng security/gateway.

### ERROR dispatcher type và security filters

Trong Servlet, filter được đăng ký cho những dispatcher type cụ thể. Có trường hợp error dispatch bị security filter kiểm tra lại, dẫn tới:

- 404 ban đầu chuyển thành 401/403.
- Error page HTML bị chặn.
- Lỗi 500 bị che bởi response khác.
- Log xuất hiện hai lượt filter processing.

Không giải quyết bằng cách cấp quyền toàn bộ ứng dụng. Với Spring Security hiện đại, xác định quyền cho **DispatcherType.ERROR** hoặc route error theo chính sách có kiểm soát, chỉ mở những gì cần để render error response, đồng thời giữ xác thực cho API nghiệp vụ.

### Tránh vòng lặp khi custom /error

Custom ErrorController có thể tự ném exception, truy cập service đang chết hoặc forward ngược về /error. Khi đó container có thể gặp lỗi trong quá trình xử lý lỗi, khiến root cause ban đầu khó quan sát hơn.

Vì vậy custom error handler nên:

- Có ít dependency, tránh external I/O.
- Không đọc database để render thông báo 500.
- Không dùng những component dễ lỗi chung với business path.
- Ghi log nguyên nhân ở tầng có kiểm soát và tạo response tối giản.
- Được test cho cả chính lỗi trong handler.

### Gắn request ID

Sử dụng correlation ID sinh tại gateway hoặc server theo trust policy và truyền qua logging/observability. Không xuất stacktrace cho client; return requestId để đội hỗ trợ tra trong logs. Đừng lưu email/token/raw body vào ErrorAttributes hoặc MD C mà không có chính sách bảo vệ.

## 18. Troubleshooting theo triệu chứng

| Hiện tượng | Khả năng nguyên nhân | Cách xác minh |
|---|---|---|
| API lỗi trả HTML, không phải JSON | Client gửi Accept: text/html hoặc browser default | Gọi curl -H "Accept: application/json" với URL thật sự gây lỗi |
| /error trả 200 hoặc dữ liệu kỳ lạ khi gọi thủ công | Không có Servlet error dispatch attributes | Tạo request 404/500 thực và kiểm tra status cuối |
| Có status 404 nhưng không có trường application từ custom ErrorAttributes | Controller/advice/security trả response trực tiếp | Kiểm tra controller path, filters và error dispatch |
| Custom ErrorAttributes không được dùng | Bean không được scan, bean khác ưu tiên, classpath/version sai | Kiểm tra bean type trong ApplicationContext và condition report |
| Có stacktrace trong public response | include-stacktrace=always/on_param hoặc controller tự trả stacktrace | Kiểm tra properties và custom error serialization |
| Tắt whitelabel nhưng HTML error vẫn xuất hiện | Custom error view/container page vẫn phục vụ | Kiểm tra view resolver và container defaults |
| API đang chạy Boot 4 nhưng server.error.path không có tác dụng | Prefix cấu hình đổi sang spring.web.error.* | Kiểm tra version-specific application properties |
| MockMvc test không nhận custom /error page | Không có full Servlet container error dispatch | Dùng @SpringBootTest(RANDOM_PORT) với HTTP client thật |
| Đặt custom ErrorController rồi context không khởi động | Trùng mapping hoặc bean/configuration conflict | Xem startup failure và loại bỏ controller duplicate |
| Một lỗi 500 bị chuyển thành 403 | Security filter xử lý lại ERROR dispatch | Kiểm tra DispatcherType.ERROR, filter order và logs |
| Error response bị đổi thành 502/503 | Proxy/gateway phát lỗi thay backend | So sánh gateway logs, backend status và request ID |
| Error page không ghi được sau exception | Response đã committed hoặc stream đã flush | Tìm thời điểm flush/write và root cause trong server logs |
| Error view template không chạy | Thiếu template engine, sai vị trí hoặc packaging | Kiểm tra classpath, templates/error/404.html và JAR contents |
| Body lỗi lộ raw exception message | advice/custom ErrorAttributes trực tiếp đưa ex.getMessage | Dùng thông điệp công khai cố định và log root cause riêng |

### Quy trình ngắn

1. Ghi nhận method, path, Accept và status thực.
2. Xác định request có tới Boot hay bị proxy trả lỗi.
3. Kiểm tra controller/advice có chủ động tạo response không.
4. Kiểm tra Servlet error dispatch, RequestDispatcher.ERROR_STATUS_CODE và ERROR_REQUEST_URI khi cần.
5. Kiểm tra BasicErrorController/ErrorAttributes beans nếu dùng mặc định.
6. Kiểm tra server.error.* hoặc spring.web.error.* theo Boot version.
7. Kiểm tra security filters và DispatcherType.ERROR.
8. Dùng HTTP integration test với RANDOM_PORT để xác minh lỗi 404/500 thật.

## 19. Bài tập tự kiểm tra

1. /error trong Servlet dùng để làm gì? Nó có phải là endpoint API nghiệp vụ để client gọi trực tiếp không?
2. BasicErrorController quyết định gì, còn ErrorAttributes cung cấp gì?
3. Vì sao cùng một lỗi có lúc trả HTML, có lúc trả JSON?
4. @RestControllerAdvice đã trả 400 rồi thì có bắt buộc đi qua /error nữa không?
5. ResponseEntity.notFound().build() có bảo đảm DefaultErrorAttributes được gọi không?
6. Trong Boot 3.5, tên property điều chỉnh đường dẫn error controller là gì?
7. Trong Boot 4.x, property và package của BasicErrorController đổi ra sao?
8. Vì sao không nên bật include-stacktrace=on_param trên public production?
9. Error dispatch có DispatcherType gì, request gốc thường có DispatcherType gì?
10. Muốn thêm field application vào default JSON mà vẫn giữ BasicErrorController, dùng extension point nào?
11. Vì sao MockMvc không đủ để kiểm tra error-page registration của Servlet container?
12. Một HTTP 500 đã committed headers rồi, server có luôn dựng được trang lỗi khác không?
13. Khi 404 bị Spring Security biến thành 403, nên kiểm tra điều gì?
14. ErrorPageFilter thường liên quan đến loại triển khai nào?
15. Nếu muốn thay body lỗi nghiệp vụ mà không động đến default fallback 500, nên dùng cơ chế nào?

### Đáp án gợi ý

1. Là error mapping do Boot đăng ký cho Servlet container điều hướng lỗi đến handler chung; không phải API nghiệp vụ thông thường.
2. BasicErrorController chọn response status, view/media type; ErrorAttributes cung cấp map dữ liệu lỗi và cause nếu có.
3. Content negotiation/Accept cho HTML hoặc JSON và các error views được cấu hình.
4. Không; MVC có thể hoàn thành response qua exception resolver.
5. Không; response do controller tạo trực tiếp có thể không có lượt error dispatch.
6. server.error.path (mặc định /error).
7. spring.web.error.path; BasicErrorController chuyển sang org.springframework.boot.webmvc.autoconfigure.error.
8. Query parameter do client có thể tự đặt, dẫn tới lộ trace và thông tin nội bộ.
9. ERROR và REQUEST.
10. ErrorAttributes bean, ví dụ subclass DefaultErrorAttributes và override getErrorAttributes.
11. Nó không khởi động/điều phối đầy đủ embedded Servlet container; dùng RANDOM_PORT.
12. Không, response committed không thể dễ dàng thay status/body.
13. Filter mapping, DispatcherType.ERROR và security authorization/entry point.
14. WAR trong external Servlet container.
15. @RestControllerAdvice và @ExceptionHandler; có thể kết hợp ProblemDetail/ResponseEntity.

## 20. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Servlet Web Applications: Error Handling](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): /error, BasicErrorController, ErrorAttributes, HTML/JSON, custom views và WAR deployment.
- [Spring Boot 3.5 — BasicErrorController Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/servlet/error/BasicErrorController.html): mappings, errorHtml, error và ErrorAttributeOptions.
- [Spring Boot 3.5 — DefaultErrorAttributes Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/error/DefaultErrorAttributes.html): error fields và hợp đồng getErrorAttributes.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): server.error.* và giá trị mặc định.
- [Spring Boot 4.0 — Servlet Web Applications](https://docs.spring.io/spring-boot/4.0/reference/web/servlet.html): cơ chế /error và spring.web.error.*.
- [Spring Boot 4.0 — BasicErrorController Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/webmvc/autoconfigure/error/BasicErrorController.html): package mới và mapping property.
- [Spring Boot 4.0 Configuration Changelog](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Configuration-Changelog): thay server.error.* bằng spring.web.error.*.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): MockMvc vs real Servlet server khi kiểm tra error pages.
- [Spring Framework — MVC Exceptions](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): @ExceptionHandler và resolver flow.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): ProblemDetail, HTTP API error responses.
- [Jakarta Servlet API — RequestDispatcher](https://jakarta.ee/specifications/servlet/): dispatcher types và ERROR_* request attributes.
