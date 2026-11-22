# Trang lỗi HTML, Whitelabel và phản hồi JSON mặc định trong Spring Boot

## Mục tiêu và phạm vi

Bài học này thuộc nhóm **Xử lý lỗi** của module **Spring Boot - web-runtime**. Sau khi học, bạn có thể:

1. Phân biệt HTTP status, HTML error page, JSON error response và RFC 9457 Problem Details.
2. Giải thích cơ chế mặc định của **Spring MVC**: Servlet error dispatch, đường dẫn /error, BasicErrorController, ErrorAttributes, ErrorViewResolver và Whitelabel Error Page.
3. Giải thích cơ chế **Spring WebFlux**: DefaultErrorWebExceptionHandler thay vì Servlet BasicErrorController.
4. Kiểm thử tại sao cùng status 404 hoặc 500 có thể trả text/html hoặc application/json tùy request Accept.
5. Dùng các thuộc tính server.error.* của **Spring Boot 3.3.x** mà không vô tình công khai exception message, validation data hoặc stack trace.
6. Thay trang Whitelabel bằng HTML tùy chỉnh cho 404, 4xx và 5xx, nhưng vẫn giữ JSON error handling cho API.
7. Hiểu khi nào @ExceptionHandler, @RestControllerAdvice, ResponseStatusException, Spring Security hoặc reverse proxy sẽ trả response khác fallback mặc định.
8. Xây ví dụ **Java 17+ / Spring Boot 3.3.x**, thử bằng curl và integration tests qua HTTP thật.
9. Nhận ra giới hạn với HTTP streaming, response đã commit, proxy caching, CORS và logging.

**Phiên bản:** Spring Boot 3.3.x, Spring Framework 6.1.x và Java 17+. Không sử dụng package hoặc property từ Boot 4.x để thay thế code ở bài này.

## 1. Điều gì xảy ra khi HTTP request gặp lỗi?

Một HTTP response có ít nhất hai thông tin quan trọng: **status** ở tầng HTTP và **body representation** được mô tả bởi Content-Type.

Client API gửi:

~~~http
GET /duong-dan-khong-co HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

Trong ứng dụng Spring Boot MVC mặc định, response thường tương đương:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"timestamp":"2026-01-01T00:00:00.000+00:00","status":404,"error":"Not Found","path":"/duong-dan-khong-co"}
~~~

**Lưu ý:** Timestamp và cách JSON được format chỉ là ví dụ minh họa, không phải kết quả cố định. Các field có thể khác do cấu hình, Spring Boot version hoặc ErrorAttributes tùy chỉnh. Với Boot 3.3, các field phổ biến là timestamp/status/error/path; message và trace thường bị ẩn theo mặc định.

Một trình duyệt yêu cầu HTML:

~~~http
GET /duong-dan-khong-co HTTP/1.1
Host: localhost:8080
Accept: text/html
~~~

có thể nhận:

~~~http
HTTP/1.1 404 Not Found
Content-Type: text/html

<!doctype html>
<html><head><title>Whitelabel Error Page</title></head>
<body><h1>Whitelabel Error Page</h1></body></html>
~~~

HTML ở đây chỉ là **hình dung rút gọn**, không phải markup chính xác của Spring Boot. Điều bất biến trong trường hợp này là **status vẫn 404**, mặc dù body là HTML thay vì JSON.

| Thuộc tính | Ví dụ | Trả lời câu hỏi |
|---|---|---|
| HTTP status | 404, 500 | Request thành công hay thất bại? |
| Response Content-Type | text/html, application/json | Body đang ở định dạng gì? |
| Response body | HTML page, JSON map, ProblemDetail | Client thấy những thông tin lỗi nào? |

Một HTTP 404 có thể có body HTML, JSON, text thuần hoặc thậm chí không có body; không thể kết luận cấu trúc response chỉ từ status.

## 2. Whitelabel Error Page là gì?

**Whitelabel Error Page** là trang HTML lỗi chung do Spring Boot cung cấp làm **fallback** khi request cần HTML nhưng không có error view nào phù hợp do ứng dụng định nghĩa.

Nó không phải:
- Một loại exception trong Java.
- Một mã trạng thái HTTP.
- Một controller mà bạn bắt buộc phải tự viết.
- Bằng chứng chắc chắn server chưa khởi động.

Nó thường cho thấy **ứng dụng đã nhận request và đang phản hồi lỗi** nhưng chưa có trang lỗi mang thương hiệu hoặc trải nghiệm người dùng riêng.

Trang Whitelabel có thể xuất hiện cho 404, 400, 500 hoặc status khác tùy nguyên nhân. Nó có thể không xuất hiện nếu ứng dụng có custom error view, custom @ExceptionHandler, Spring Security tự tạo response, hoặc proxy thay body.

### Ý nghĩa dòng “no explicit mapping for /error”

Whitelabel của một số phiên bản có câu:

~~~text
This application has no explicit mapping for /error,
so you are seeing this as a fallback.
~~~

Đây **không** phải hướng dẫn rằng mọi project cần tạo thêm @GetMapping("/error"). Spring Boot đã auto-configure error processing; câu trên nói ứng dụng chưa cung cấp view lỗi HTML chuyên biệt thay fallback.

Tạo controller /error tùy tiện có thể làm thay đổi route, HTTP status, content negotiation và JSON error contract. Đa số project chỉ cần thêm file HTML lỗi vào đúng thư mục hoặc dùng một advice khi cần API error schema khác.

## 3. Spring MVC: Servlet error dispatch và BasicErrorController

Trong Servlet-based Spring MVC, Spring Boot mặc định đăng ký **/error** làm error page toàn cục cho embedded Servlet container.

~~~text
HTTP client
     |
     v
Embedded Tomcat / Jetty / Undertow
     |
     v
Servlet Filters / Spring Security (nếu có)
     |
     v
DispatcherServlet / Controller
     |
     +----> Thành công --------------------> Response
     |
     +----> Lỗi hoặc exception
                  |
                  +--> HandlerExceptionResolver / @ExceptionHandler
                  |         |
                  |         +--> Có thể xử lý và trả response ngay
                  |
                  +--> Khi cần Servlet ERROR dispatch
                             |
                             v
                          /error
                             |
                             v
                     BasicErrorController
                             |
                    +--------+----------+
                    |                   |
                HTML view           JSON/fallback
                    |                   |
            ErrorViewResolver     ErrorAttributes
                    |                   |
            Whitelabel/custom     JSON response
~~~

Sơ đồ phản ánh một **đường xử lý điển hình**, không phải mọi 4xx/5xx đều bắt buộc qua /error.

Các thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| ErrorMvcAutoConfiguration | Auto-configuration error handling trong Spring MVC |
| BasicErrorController | Controller fallback cho /error |
| ErrorAttributes | Hợp đồng cung cấp các thông tin lỗi |
| DefaultErrorAttributes | Implementation mặc định ghi lại thông tin cơ bản |
| ErrorViewResolver | Tìm view hoặc trang HTML thích hợp |
| Whitelabel view | HTML fallback khi không có custom view |
| HandlerExceptionResolver | Xử lý exception trong MVC |
| Servlet error page | Kích hoạt ERROR dispatch tới error path khi cần |

Package của BasicErrorController trong Spring Boot 3.3:

~~~java
org.springframework.boot.autoconfigure.web.servlet.error.BasicErrorController
~~~

Hai nhánh nổi bật:

~~~java
@RequestMapping(produces = "text/html")
ModelAndView errorHtml(HttpServletRequest request,
                       HttpServletResponse response);

@RequestMapping
ResponseEntity<Map<String, Object>> error(HttpServletRequest request);
~~~

Đây là chữ ký API để đọc hiểu, **không phải file Java độc lập**. Nhánh errorHtml trả view cho HTML, nhánh error trả Map thông tin để converter viết response, thông thường dưới dạng JSON.

## 4. Vì sao không nên trực tiếp gọi GET /error để kiểm thử?

Trong MVC, error dispatch chứa thông tin nội bộ của Servlet request, như status ban đầu và request URI đã gây lỗi. Nó khác với việc một client tự gửi GET /error như một URL thông thường.

~~~text
Client -> GET /khong-ton-tai
  -> MVC/Servlet xác định 404
  -> internal ERROR dispatch sang /error
  -> BasicErrorController lấy status và original path
Client <- HTTP 404, JSON/HTML phù hợp Accept
~~~

Khi client gửi thẳng GET /error, request không nhất thiết có metadata của Servlet ERROR dispatch, nên status và body không tương đương với một lỗi thật.

Thuộc tính cấu hình mặc định:

~~~properties
server.error.path=/error
~~~

Có thể đổi:

~~~yaml
server:
  error:
    path: /failure
~~~

nhưng chỉ nên làm khi có mục đích rõ, đã kiểm thử Servlet container, Security, reverse proxy và monitoring. Đổi error path không tạo ra authentication hay giảm lộ dữ liệu.

Để kiểm thử, hãy gọi **đường dẫn không có handler** hoặc endpoint cố ý ném exception trong môi trường lab.

## 5. Accept và Content-Type quyết định những việc khác nhau

- **Request Content-Type** mô tả body client gửi, ví dụ POST application/json.
- **Request Accept** mô tả response media types mà client muốn nhận.
- **Response Content-Type** mô tả body mà server thực sự trả.

Ví dụ một POST gửi JSON nhưng muốn HTML:

~~~http
POST /api/items HTTP/1.1
Content-Type: application/json
Accept: text/html

{"name":"pen"}
~~~

Nếu request lỗi và fallback handler chọn HTML, response lỗi có thể là text/html. Không có quy tắc nói request JSON bắt buộc nhận JSON error.

Để test rõ ràng:

~~~bash
curl -i -H 'Accept: application/json' http://localhost:8080/khong-ton-tai
curl -i -H 'Accept: text/html' http://localhost:8080/khong-ton-tai
~~~

Khi client gửi Accept: */* hoặc không gửi Accept, nhiều representation có thể phù hợp. Không khóa bài kiểm thử vào một loại body nếu request không quy định rõ sở thích response.

**Đừng nhầm lỗi CORS với body lỗi HTML/JSON.** Browser JavaScript có thể bị CORS policy chặn đọc một response mà server thực tế vẫn đã gửi status 404/500.

## 6. JSON error body mặc định chứa gì?

Một representation lỗi điển hình:

~~~json
{
  "timestamp": "2026-01-01T00:00:00.000+00:00",
  "status": 404,
  "error": "Not Found",
  "path": "/khong-ton-tai"
}
~~~

Các field:

| Field | Ý nghĩa | Hành vi điển hình của Boot 3.3 |
|---|---|---|
| timestamp | Thời điểm ghi nhận lỗi | Thường có |
| status | HTTP status number | Thường có |
| error | Reason phrase | Thường có |
| path | Path gây lỗi | include-path=always |
| message | Exception message | include-message=never |
| errors | Binding/validation details | include-binding-errors=never |
| trace | Stack trace | include-stacktrace=never |
| exception | Tên exception class | include-exception=false |

**Không mặc định đưa message hoặc stack trace ra public JSON.** Có thể gặp các ví dụ cũ trên Internet hiển thị message/trace, nhưng đó có thể là Boot version khác hoặc cấu hình đã bật thông tin chi tiết.

JSON default là fallback của framework, **không đồng nghĩa contract API đã được versioning**. Nếu client cần machine-readable error code, support ID, field errors và tài liệu liên kết, hãy định nghĩa phản hồi theo contract ứng dụng.

## 7. Các thuộc tính server.error.* của Spring Boot 3.3

| Property | Default Boot 3.3 | Ý nghĩa |
|---|---|---|
| server.error.path | /error | Error controller path trong MVC |
| server.error.whitelabel.enabled | true | Bật HTML fallback Whitelabel |
| server.error.include-message | never | Điều kiện công khai message |
| server.error.include-stacktrace | never | Điều kiện công khai trace |
| server.error.include-binding-errors | never | Điều kiện công khai binding/validation errors |
| server.error.include-exception | false | Có đưa exception class name không |
| server.error.include-path | always | Điều kiện đưa request path vào error attributes |

Các property kiểu “khi nào” có thể dùng never, always hoặc on_param khi thuộc tính đó hỗ trợ; với API public nên mặc định giới hạn thông tin.

Ví dụ YAML bảo thủ:

~~~yaml
server:
  error:
    whitelabel:
      enabled: true
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
    include-exception: false
    include-path: always
~~~

Giá trị này gần với mặc định Boot 3.3. Khi có HTML frontend, nên bổ sung custom error view riêng thay Whitelabel nếu cần trải nghiệm tốt hơn.

### Bật message để debug local

~~~properties
server.error.include-message=always
~~~

Có thể làm error map chứa message khi error handler sử dụng thuộc tính đó. Không có gì đảm bảo mọi exception có message hoặc mọi lỗi đều tới /error. Trong production, message có thể chứa tên class, SQL, đường dẫn, file name, host hoặc dữ liệu người dùng.

### Rủi ro include-stacktrace=always hoặc on_param

Stack trace có thể làm lộ cấu trúc code, dependency, phiên bản, exception messages, file paths và một số nội dung nhạy cảm. Không để khách hàng tự kích hoạt trace trên public endpoints. Hãy ghi stack trace vào **server logs nội bộ** có redaction và tương quan bằng request ID.

### Tắt Whitelabel có tắt default JSON không?

~~~yaml
server:
  error:
    whitelabel:
      enabled: false
~~~

Thuộc tính này chủ yếu **tắt Whitelabel HTML view**. Trong MVC, JSON handling của BasicErrorController có thể tiếp tục hoạt động. Nếu không có custom HTML view, Servlet container hoặc một fallback khác có thể hiển thị trang lỗi tùy môi trường. **Đừng xem thao tác tắt Whitelabel như một cách tạo trang 404 đẹp.**

## 8. Không phải mọi HTTP 4xx/5xx đều đi qua /error

Ví dụ controller tự trả một status:

~~~java
@GetMapping("/api/items/example")
ResponseEntity<String> demo() {
    return ResponseEntity.status(404).body("not found");
}
~~~

Đây là snippet trong REST controller. Controller đã dựng response trực tiếp; không nhất thiết Servlet error dispatch hoặc BasicErrorController tham gia.

Framework có exception resolvers dành cho request mapping, body parsing và validation. Spring Security có thể chặn và trả 401/403 hoặc redirect. Proxy có thể trả 502/503/504 khi upstream không liên lạc được.

### ResponseStatusException

~~~java
@GetMapping("/api/items/{id}")
Object item(@PathVariable long id) {
    throw new ResponseStatusException(
            HttpStatus.NOT_FOUND, "Item is unavailable");
}
~~~

Đây là snippet minh họa trong controller. Spring có xử lý status của ResponseStatusException; **không đảm bảo** field message được trả trong JSON mặc định khi include-message=never.

### Nhận diện một số HTTP status

| Status | Nguyên nhân thường gặp |
|---|---|
| 400 | Request parameters/body invalid, malformed JSON |
| 401 | Authentication chưa đạt, security handler |
| 403 | Không đủ quyền, security handler |
| 404 | Không có handler/resource hoặc object không tồn tại |
| 405 | HTTP method không được chấp nhận |
| 406 | Accept không tương thích response representation |
| 415 | Content-Type của request body không hỗ trợ |
| 500 | Unhandled server exception |
| 502/503/504 | Gateway/proxy hoặc dependency availability |

Đừng suy từ status 404 rằng tất cả do controller mapping; một API có thể intentionally trả 404. Cũng đừng suy từ status 500 rằng người dùng đã thấy trang Whitelabel: API client thường yêu cầu JSON.

## 9. Tùy chỉnh HTML error page không cần viết /error controller

Spring Boot hỗ trợ error pages theo **exact status** và **status series**.

### Static 404 page

Tạo file:

~~~text
src/main/resources/public/error/404.html
~~~

Ví dụ nội dung:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Không tìm thấy</title>
</head>
<body>
  <main>
    <h1>404 — Không tìm thấy trang</h1>
    <p>Đường dẫn không tồn tại hoặc đã thay đổi.</p>
    <a href="/">Về trang chủ</a>
  </main>
</body>
</html>
~~~

Khi lỗi 404 cần render HTML, Boot có thể chọn file này thay Whitelabel. Nếu client gửi Accept: application/json, JSON branch mặc định vẫn có thể hoạt động bình thường.

### Error series

~~~text
src/main/resources/public/error/404.html
src/main/resources/public/error/4xx.html
src/main/resources/public/error/5xx.html
~~~

Một trang exact status như 404 thường được ưu tiên so với 4xx; một error 500 chưa có trang riêng có thể dùng 5xx.

### Template HTML

Với Thymeleaf hoặc template engine được Boot auto-configure, có thể đặt:

~~~text
src/main/resources/templates/error/404.html
src/main/resources/templates/error/5xx.html
src/main/resources/templates/error.html
~~~

Trong **Spring MVC**, default error view name là **error**. Template động có thể hiển thị trạng thái hoặc thông tin đã được biên tập, nhưng không nên đưa raw stack trace, SQL hoặc exception message nội bộ cho người dùng.

Nếu template/static resource không được chọn, kiểm tra jar resources, folder path, template engine dependency, view resolver priority, cache, custom advice và các ErrorViewResolver beans.

## 10. Whitelabel disabled khác custom HTML

Ba phương án:

| Phương án | Mục tiêu | Hệ quả |
|---|---|---|
| Whitelabel mặc định | Prototype và local test | HTML fallback tối giản |
| public/error/404.html | Trải nghiệm 404 có thương hiệu | Chỉ thay HTML khi status phù hợp |
| server.error.whitelabel.enabled=false | Tắt Whitelabel | Không tự tạo trang HTML mới |

Một ứng dụng vừa phục vụ HTML frontend vừa cung cấp REST API có thể cần **hai contract riêng**:
- HTML page 404/5xx dễ hiểu, không lộ nội bộ.
- JSON lỗi có status và code ổn định cho API client.

Không buộc API client parse HTML để tìm lỗi; cũng không buộc browser hiển thị JSON raw nếu ứng dụng chủ yếu phục vụ người dùng.

## 11. Ví dụ Spring MVC chạy được: HTML và JSON mặc định

Tạo project **Spring Boot 3.3.x / Java 17+** có starter-web. Chưa thêm custom error pages và @RestControllerAdvice trong lần chạy đầu để thấy fallback nguyên bản.

Trong build.gradle của project Boot đã khai báo plugins/repositories:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây chỉ là phần dependencies, không phải toàn bộ build.gradle.

### Mã Java đầy đủ

Tạo **src/main/java/com/example/errors/ErrorViewsApplication.java**:

~~~java
package com.example.errors;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ErrorViewsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorViewsApplication.class, args);
    }

    @RestController
    static class ExampleController {

        @GetMapping("/api/ok")
        Map<String, String> ok() {
            return Map.of("result", "ok");
        }

        @GetMapping("/api/items/{id}")
        Map<String, Object> find(@PathVariable long id) {
            if (id != 7) {
                throw new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Item is unavailable");
            }
            return Map.of("id", id, "name", "pen");
        }

        @GetMapping("/api/crash")
        String crash() {
            throw new IllegalStateException(
                    "Internal diagnostic details: do not expose");
        }
    }
}
~~~

Đây là **Java file hoàn chỉnh trong project Spring Boot**; không biên dịch bằng javac thuần khi không có Spring/Jackson trên classpath.

Mục đích endpoint:
- /api/ok: hoạt động bình thường, JSON 200.
- /api/items/{id}: dữ liệu minh họa; id khác 7 tạo lỗi 404.
- /api/crash: cố ý ném exception để quan sát fallback 500, **chỉ dùng trong local lab/test**.
- /khong-ton-tai: client sẽ thử một URL không có handler.

### Cấu hình

Tạo **src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080
  error:
    whitelabel:
      enabled: true
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
    include-exception: false
~~~

### Chạy

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu port 8080 đang bận, đổi server.port và cập nhật URL trong mọi lệnh thử.

## 12. Dùng curl để chứng minh content negotiation

Endpoint thành công:

~~~bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/ok
~~~

Một JSON body tương đương:

~~~json
{"result":"ok"}
~~~

Lỗi URL không tồn tại, yêu cầu JSON:

~~~bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/khong-ton-tai
~~~

Kỳ vọng HTTP 404, Content-Type application/json, field status=404. Không cố đoán chính xác timestamp.

Cùng URL nhưng yêu cầu HTML:

~~~bash
curl -i -H 'Accept: text/html' \
  http://localhost:8080/khong-ton-tai
~~~

Kỳ vọng 404 text/html. Khi chưa có custom error view, body thường là Whitelabel HTML.

Lỗi server chưa được ứng dụng bắt:

~~~bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/crash

curl -i -H 'Accept: text/html' \
  http://localhost:8080/api/crash
~~~

Kỳ vọng 500 trong cả hai request. Với include-message=never, JSON fallback không nên có chuỗi “Internal diagnostic details” của exception. Logs nội bộ có thể chứa stack trace để debug.

### Sau khi quan sát mặc định, thêm HTML 404

Thêm public/error/404.html ở mục 9 rồi restart/repackage nếu cần. Request Accept: text/html nay có thể nhận custom page, trong khi Accept: application/json vẫn nhận JSON lỗi fallback. Đây là test quan trọng về việc **HTML customization không tự thay JSON contract**.

### PowerShell

Trên Windows PowerShell sử dụng curl.exe để tránh alias:

~~~powershell
curl.exe -i -H "Accept: application/json" "http://localhost:8080/khong-ton-tai"
curl.exe -i -H "Accept: text/html" "http://localhost:8080/khong-ton-tai"
curl.exe -i -H "Accept: application/json" "http://localhost:8080/api/crash"
~~~

## 13. Test /error bằng HTTP thật, không chỉ MockMvc

MockMvc chạy Spring MVC infrastructure nhưng **không mở embedded Servlet container**; nó không tái hiện đầy đủ Servlet error-page dispatch. Một unhandled exception trong MockMvc có thể nổi lên trong test thay vì được forward tới /error như khi chạy Tomcat thật.

Đối với fallback này, nên dùng **@SpringBootTest(webEnvironment=RANDOM_PORT)** + HTTP client. Ví dụ dùng TestRestTemplate được cung cấp bởi starter-test.

Tạo **src/test/java/com/example/errors/ErrorViewsIntegrationTests.java**:

~~~java
package com.example.errors;

import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

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
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ErrorViewsIntegrationTests {

    @Autowired
    TestRestTemplate http;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void missingUrlReturns404JsonWithoutTrace() throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));

        ResponseEntity<String> response = http.exchange(
                "/khong-ton-tai",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class
        );

        assertEquals(404, response.getStatusCode().value());
        assertNotNull(response.getHeaders().getContentType());
        assertTrue(response.getHeaders().getContentType()
                .isCompatibleWith(MediaType.APPLICATION_JSON));

        JsonNode error = objectMapper.readTree(response.getBody());
        assertEquals(404, error.path("status").asInt());
        assertEquals("/khong-ton-tai", error.path("path").asText());
        assertFalse(error.has("trace"));
        assertFalse(error.has("exception"));
    }

    @Test
    void missingUrlReturnsHtmlWith404Status() {
        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaType.TEXT_HTML));

        ResponseEntity<String> response = http.exchange(
                "/khong-ton-tai",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class
        );

        assertEquals(404, response.getStatusCode().value());
        assertNotNull(response.getHeaders().getContentType());
        assertTrue(response.getHeaders().getContentType()
                .isCompatibleWith(MediaType.TEXT_HTML));
        assertNotNull(response.getBody());
    }

    @Test
    void unhandledExceptionReturns500Json() throws Exception {
        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));

        ResponseEntity<String> response = http.exchange(
                "/api/crash",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class
        );

        assertEquals(500, response.getStatusCode().value());
        JsonNode error = objectMapper.readTree(response.getBody());
        assertEquals(500, error.path("status").asInt());
        assertFalse(error.has("trace"));
        assertFalse(error.has("message"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Trong bài này không khóa timestamp hoặc literal Whitelabel markup. Test HTML chỉ kiểm tra status/media type vì HTML có thể được tùy chỉnh mà API vẫn đúng. Test 500 giả định project chưa có advice riêng bắt IllegalStateException.

## 14. Khi nào dùng @RestControllerAdvice thay default JSON?

Fallback JSON map của Boot có thể đủ cho prototype, nhưng API công khai thường cần contract lỗi riêng: business error code, thông báo an toàn, correlation ID, field errors hợp lệ và tài liệu API.

Định nghĩa một exception nghiệp vụ trong file **ProductUnavailableException.java**:

~~~java
package com.example.errors;

public class ProductUnavailableException extends RuntimeException {
    public ProductUnavailableException(long id) {
        super("Product unavailable: " + id);
    }
}
~~~

Thêm advice **ProductErrorAdvice.java**:

~~~java
package com.example.errors;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ProductErrorAdvice {

    @ExceptionHandler(ProductUnavailableException.class)
    public ResponseEntity<ProblemDetail> handle(
            ProductUnavailableException ex) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "The requested product is unavailable");
        problem.setTitle("Product not found");
        problem.setProperty("code", "PRODUCT_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
~~~

Đây là **các file Java bổ sung tùy chọn**, không phải thay thế cho main class. Advice chỉ xử lý ProductUnavailableException; exception khác, như IllegalStateException của endpoint demo, vẫn có thể đi qua fallback mặc định.

Một response có thể là:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{"type":"about:blank","title":"Product not found","status":404,"detail":"The requested product is unavailable","code":"PRODUCT_NOT_FOUND"}
~~~

Đây là **Problem Details** (RFC 9457), khác schema JSON map mặc định. Không trả exception message thô nếu nó chứa thông tin nhạy cảm.

### Advice có thể ảnh hưởng HTML frontend

@RestControllerAdvice trả response body cho exception match. Một browser yêu cầu HTML vẫn có thể nhận JSON nếu advice được thiết kế không giới hạn phạm vi. Với app vừa có MVC views vừa có REST API, nên xác định advice áp dụng cho nhóm controller nào, tránh vô tình biến lỗi HTML frontend thành JSON.

## 15. ProblemDetail và JSON map mặc định không đồng nghĩa

Spring Framework 6 hỗ trợ ProblemDetail/ErrorResponse, Spring Boot 3.3 có property:

~~~yaml
spring:
  mvc:
    problemdetails:
      enabled: true
~~~

Một Problem Details response điển hình:

~~~json
{
  "type": "https://example.org/problems/missing-product",
  "title": "Not Found",
  "status": 404,
  "detail": "Product was not found",
  "instance": "/api/items/7"
}
~~~

Các giá trị chỉ minh họa contract có thể thiết kế. Bật Problem Details hỗ trợ một số framework errors trong MVC, **không bảo đảm mọi unhandled exception hoặc mọi Servlet error dispatch đều trở thành cùng một ProblemDetail**.

So sánh:

| Loại response | Body và Content-Type |
|---|---|
| BasicErrorController JSON | timestamp/status/error/path..., application/json |
| Whitelabel hoặc custom HTML | HTML, text/html |
| @RestControllerAdvice trả DTO | JSON theo contract của bạn |
| ProblemDetail | type/title/status/detail/instance, application/problem+json |
| Spring Security error | Do entry point/denied handler quyết định |

Đừng chỉ đổi Accept sang application/problem+json rồi giả định server đang cung cấp ProblemDetail ở mọi endpoint.

## 16. WebFlux: không dùng Servlet BasicErrorController

Spring WebFlux trên Reactor Netty có global error-handling infrastructure riêng. Trong Spring Boot 3.3, handler tiêu biểu là:

~~~java
org.springframework.boot.autoconfigure.web.reactive.error.DefaultErrorWebExceptionHandler
~~~

Nó là **WebExceptionHandler** và có thể render error HTML view cho client chấp nhận HTML hoặc JSON error payload cho API client.

~~~text
HTTP request
     |
     v
Reactive server / WebFilter / DispatcherHandler
     |
     +----> Controller thành công -> response
     |
     +----> Unhandled reactive error
                       |
                       v
             DefaultErrorWebExceptionHandler
                       |
                 +-----+------+
                 |            |
           HTML error view   JSON error data
                 |            |
              text/html   application/json
~~~

Sự khác biệt:

| Chủ đề | MVC | WebFlux |
|---|---|---|
| Runtime | Servlet/Tomcat | Reactive/Reactor Netty |
| Global fallback | BasicErrorController | DefaultErrorWebExceptionHandler |
| Error metadata | Servlet ErrorAttributes | Reactive ErrorAttributes |
| HTML view | ErrorViewResolver/Whitelabel | Reactive error view/Whitelabel |
| JSON writing | HttpMessageConverter | HttpMessageWriter/codec |
| Servlet ERROR dispatch | Có khi cần | Không cùng cơ chế |
| ProblemDetail property | spring.mvc.problemdetails.enabled | spring.webflux.problemdetails.enabled |

Trong WebFlux, không mô tả mọi error là Servlet forward tới /error. Reactive error handler có pipeline riêng.

### Error HTML view trong WebFlux

Boot 3.3 có thể tìm:

~~~text
src/main/resources/public/error/404.html
src/main/resources/public/error/5xx.html
src/main/resources/templates/error/404.html
src/main/resources/templates/error/5xx.html
~~~

**Khác biệt cần nhớ:** default error view name trong WebFlux là **error/error**, còn Spring MVC là **error**. Với file exact status như public/error/404.html, hai stack có thể dùng đường dẫn tương tự.

## 17. Project WebFlux chạy được để kiểm tra lỗi

Tạo **project riêng** chỉ dùng starter-webflux, Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Không thêm starter-web vào project này nếu cần chắc chắn Boot chọn reactive server mặc định, vì khi cả hai starter hiện diện Boot 3.3 thường ưu tiên MVC.

Tạo **src/main/java/com/example/reactiveerrors/ReactiveErrorViewsApplication.java**:

~~~java
package com.example.reactiveerrors;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveErrorViewsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveErrorViewsApplication.class, args);
    }

    @RestController
    static class DemoController {

        @GetMapping("/api/ok")
        Mono<Map<String, String>> ok() {
            return Mono.just(Map.of("result", "ok"));
        }

        @GetMapping("/api/crash")
        Mono<String> crash() {
            return Mono.error(new IllegalStateException(
                    "Internal diagnostic details: do not expose"));
        }
    }
}
~~~

Đây là **file Java đầy đủ** trong project có dependencies, không chạy độc lập bằng javac trần. /api/crash cố ý tạo reactive error để học, không được triển khai công khai ở production.

application.yml:

~~~yaml
server:
  port: 8081
  error:
    whitelabel:
      enabled: true
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
~~~

Port 8081 chỉ để có thể chạy cùng ví dụ MVC trên 8080; có thể đổi nếu cần.

Chạy:

~~~bash
./gradlew bootRun
~~~

Thử JSON/HTML cho URL không tồn tại và lỗi 500:

~~~bash
curl -i -H 'Accept: application/json' \
  http://localhost:8081/khong-ton-tai

curl -i -H 'Accept: text/html' \
  http://localhost:8081/khong-ton-tai

curl -i -H 'Accept: application/json' \
  http://localhost:8081/api/crash

curl -i -H 'Accept: text/html' \
  http://localhost:8081/api/crash
~~~

Kỳ vọng status 404 cho URL không tồn tại, 500 cho /api/crash; HTML/JSON được chọn theo Accept và error handler thực tế.

## 18. Kiểm thử WebFlux với WebTestClient

Tạo file **src/test/java/com/example/reactiveerrors/ReactiveErrorViewsIntegrationTests.java**:

~~~java
package com.example.reactiveerrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ReactiveErrorViewsIntegrationTests {

    @Autowired
    WebTestClient client;

    @Test
    void missingUrlReturnsJson404() {
        client.get()
            .uri("/khong-ton-tai")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isNotFound()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON);
    }

    @Test
    void missingUrlReturnsHtml404() {
        client.get()
            .uri("/khong-ton-tai")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isNotFound()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_HTML);
    }

    @Test
    void crashReturnsJson500() {
        client.get()
            .uri("/api/crash")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().is5xxServerError()
            .expectBody()
            .jsonPath("$.status").isEqualTo(500);
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

WebTestClient với RANDOM_PORT gửi request đến reactive HTTP server thật. Test không cố định Whitelabel markup hoặc timestamp.

Có thể bật hỗ trợ ProblemDetail WebFlux:

~~~yaml
spring:
  webflux:
    problemdetails:
      enabled: true
~~~

Tuy nhiên, property này không biến **mọi** reactive error thành application/problem+json; DefaultErrorWebExceptionHandler vẫn có phạm vi fallback riêng.

## 19. Security và proxy thường giải thích JSON/HTML “khác lạ”

### Spring Security

Security có thể sinh 401, 403 hoặc redirect login page ngay trong filter chain. Vì vậy các response này có thể không qua BasicErrorController/DefaultErrorWebExceptionHandler. Khi error page vô tình bị chặn bởi Security, hãy kiểm tra quyền của ERROR dispatch và error resources, **không mở quyền mọi API chỉ để sửa hiển thị trang lỗi**.

### Reverse proxy

~~~text
Browser/API client
        |
        v
CDN / Load balancer / Nginx / Gateway
        |
        v
Spring Boot
~~~

Proxy có thể:
- Tự tạo 502/503/504 khi backend không hoạt động.
- Intercept 404/500 và thay trang HTML.
- Thay/bỏ Accept khiến backend chọn representation khác.
- Cache nhầm HTML/JSON dưới cùng URL.
- Chặn request trước backend bằng WAF hoặc authentication.

Khi lỗi không giống Spring Boot mặc định, cần xác định **request có thực sự tới backend hay không**. So sánh logs ở gateway/backend, status và Content-Type ở từng hop.

### Vary và caching

Cùng URL có thể trả JSON và HTML tùy Accept, nên cache key và Vary: Accept cần được xem xét:

~~~http
Vary: Accept
~~~

Không khẳng định mọi error path tự gắn Vary này; cần đo response thực và cấu hình gateway/cache. Tránh cache HTML error rồi gửi cho API client mong JSON.

## 20. Streaming và response đã commit

Với Server-Sent Events, Flux streaming hoặc file download lớn, exception có thể xuất hiện **sau khi server đã gửi status/headers và một phần body**.

~~~text
Server gửi HTTP 200 + headers + vài chunks
          |
          +--> Exception phát sinh
          |
          +--> Không thể đảm bảo đổi response đã commit
               thành HTML Whitelabel hoặc JSON lỗi 500 nguyên vẹn
~~~

Client có thể thấy stream bị ngắt, thiếu dữ liệu, hoặc protocol-specific error frame nếu ứng dụng thiết kế. Đừng hứa mọi exception đều được Spring Boot chuyển thành trang 500; observability/stream protocol cần có chiến lược riêng.

## 21. Vận hành và bảo mật: tách public error khỏi server logs

Dữ liệu debug có thể bao gồm SQL, class names, file paths, dependency versions, request payload, token hoặc stack trace. Không đưa toàn bộ thông tin này vào HTML/JSON public.

Một hệ thống production nên có:

- HTTP status đúng và error code ổn định cho client.
- Correlation/request ID có thể đối chiếu với log nội bộ.
- Structured exception logs có redaction của Authorization, Cookie, token và PII.
- Metrics/alerts theo 4xx, 5xx, latency và dependency failures.
- Custom HTML 404/5xx thân thiện nhưng không có thông tin nội bộ.
- Không bật include-message/stacktrace/binding-errors trên public endpoints nếu không có đánh giá rủi ro.
- Không mở endpoint cố ý ném exception ở ví dụ thực hành ra Internet.
- Giới hạn thông tin path/query nếu chứa dữ liệu nhạy cảm.

Một error đã được @ExceptionHandler xử lý có thể không còn được một số metrics/observations tự coi là unhandled exception. Nếu vận hành yêu cầu đo exception, cấu hình observation trong handler thích hợp thay vì giả status=200.

## 22. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
|---|---|---|
| Browser thấy Whitelabel 404 | Không có route hoặc resource | Path, context path, controller scan |
| Curl thấy JSON cùng URL | Accept application/json | Response Content-Type |
| JSON không có message | include-message=never | server.error properties |
| JSON không có trace | include-stacktrace=never | Xem server logs thay vì public body |
| Tắt Whitelabel vẫn có trang lỗi | Fallback của container/proxy/custom view | Servlet runtime, error templates |
| Đặt error/404.html nhưng không được dùng | Sai vị trí, chưa package/restart, view priority | Resource classpath và template engine |
| ResponseEntity 404 khác default JSON | Controller tự dựng body | Controller/advice logic |
| MockMvc không tạo default 500 | Không có container ERROR dispatch thật | RANDOM_PORT integration test |
| WebFlux không thấy BasicErrorController | WebFlux handler khác Servlet | Web stack đã chọn |
| 401/403 không có Whitelabel | Spring Security trả riêng | AuthenticationEntryPoint/DeniedHandler |
| 502 HTML thay JSON | Proxy tạo lỗi | Gateway logs |
| Browser báo CORS thay vì đọc error | CORS policy chặn JS | Preflight và Access-Control headers |
| Streaming không có JSON 500 | Response committed | Server logs/stream protocol |
| Lỗi công khai raw exception | Custom ErrorAttributes/trace enabled | Redaction và security config |

### Quy trình debug ngắn

1. Xác định thực sự đang chạy MVC hay WebFlux.
2. Gọi một endpoint 200 để xác nhận server đang nghe đúng port.
3. Gửi request lỗi với Accept: application/json và Accept: text/html riêng.
4. Xem status + Content-Type + body.
5. Kiểm tra Security, proxy, controller advice trước khi kết luận do /error.
6. Với MVC, kiểm tra BasicErrorController, ErrorAttributes, ErrorViewResolver.
7. Với WebFlux, kiểm tra DefaultErrorWebExceptionHandler/codec.
8. Kiểm tra server.error.* và ProblemDetail settings.
9. Kiểm tra static/template error resources trong artifact.
10. Test bằng HTTP thật khi behavior phụ thuộc container dispatch.

## 23. Bài tập thực hành

**Bài 1 — Hai representation:** cùng URL /khong-ton-tai, gửi hai request có Accept khác nhau. Ghi lại status, Content-Type và điểm khác của body. Giải thích vì sao status vẫn 404.

**Bài 2 — 500 không lộ nội bộ:** gọi /api/crash với Accept JSON; kiểm tra status 500, JSON không có raw exception message và trace khi include-message/stacktrace=never.

**Bài 3 — Custom HTML 404:** thêm public/error/404.html, kiểm tra trình duyệt thấy giao diện mới còn client Accept JSON vẫn nhận JSON error map.

**Bài 4 — Tắt Whitelabel:** đặt whitelabel.enabled=false, restart, so sánh HTML. Không khẳng định fallback của mọi Servlet container giống nhau.

**Bài 5 — Domain exception:** dùng ProductUnavailableException và advice ở phần 14; so sánh application/problem+json với default ErrorAttributes JSON.

**Bài 6 — MockMvc vs HTTP thật:** thử một unhandled exception trong MockMvc và qua RANDOM_PORT; giải thích vai trò Servlet ERROR dispatch.

**Bài 7 — WebFlux:** chạy ở port 8081, gửi 404 và 500 với Accept HTML/JSON, so sánh reactive error handler và MVC BasicErrorController.

**Bài 8 — Gateway:** tạo một lỗi backend 404 và một lỗi proxy 502 trong môi trường demo; so sánh headers/body/logs để xác định lớp tạo response.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Whitelabel có phải HTTP status không?

**Đáp án:** Không. Đó là HTML fallback. HTTP status có thể là 404, 500 hoặc mã khác.

**Câu 2.** Vì sao browser và curl thấy body lỗi khác nhau với cùng URL?

**Đáp án:** Khác Accept và cơ chế content negotiation/error view selection.

**Câu 3.** server.error.whitelabel.enabled=false có tự tắt JSON default không?

**Đáp án:** Không. Thuộc tính chủ yếu tắt Whitelabel HTML fallback.

**Câu 4.** Trong Boot 3.3, message/trace có xuất hiện mặc định trong JSON lỗi không?

**Đáp án:** Không. include-message và include-stacktrace mặc định never.

**Câu 5.** File HTML 404 tĩnh đặt ở đâu?

**Đáp án:** src/main/resources/public/error/404.html.

**Câu 6.** Controller tự trả ResponseEntity.status(404) có luôn qua /error không?

**Đáp án:** Không. Có thể là response trực tiếp.

**Câu 7.** WebFlux có dùng BasicErrorController servlet không?

**Đáp án:** Không. Nó sử dụng DefaultErrorWebExceptionHandler ở reactive layer.

**Câu 8.** JSON map của Boot có cùng schema với ProblemDetail không?

**Đáp án:** Không. JSON map thường có timestamp/status/error/path; ProblemDetail theo RFC 9457.

**Câu 9.** Exception sau khi response streaming đã commit có luôn thành trang JSON 500 không?

**Đáp án:** Không. Status/headers/body đã gửi có thể không thay được.

**Câu 10.** Nginx trả 502 do upstream unavailable có được sửa bằng server.error.whitelabel.enabled không?

**Đáp án:** Không. Lỗi có thể do proxy tạo trước khi request tới Boot.

**Câu 11.** Tại sao không nên bật stack trace public?

**Đáp án:** Có thể lộ nội bộ, SQL, code paths, dependency versions và dữ liệu nhạy cảm; cần log nội bộ có kiểm soát.

## 25. Checklist triển khai

- [ ] Đã xác định MVC hay WebFlux và loại global error handler tương ứng.
- [ ] Đã thử 404/500 với Accept HTML và JSON.
- [ ] Kiểm tra status, Content-Type và body cùng lúc.
- [ ] Không dùng GET /error trực tiếp để mô phỏng đầy đủ Servlet ERROR dispatch.
- [ ] Không công khai exception message, stack trace, class name hoặc binding errors không cần thiết.
- [ ] HTML frontend có error page 404/4xx/5xx phù hợp thương hiệu.
- [ ] REST API có schema lỗi ổn định và đúng HTTP status.
- [ ] @ControllerAdvice chỉ áp dụng đúng phạm vi, không vô tình biến HTML web page thành JSON.
- [ ] Có integration test với HTTP server thật cho fallback /error.
- [ ] Có structured logs, metrics, correlation ID và redaction dữ liệu nhạy cảm.
- [ ] Kiểm tra Security, proxy, cache, CORS khi response khác mong đợi.
- [ ] Không để endpoint lab cố tình gây exception ở production.
- [ ] Có thiết kế xử lý lỗi khi streaming đã commit.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Servlet Web Applications: Error Handling](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 — Reactive Web Applications: Error Handling](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot 3.3 — BasicErrorController Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/error/BasicErrorController.html)
- [Spring Boot 3.3 — DefaultErrorWebExceptionHandler Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/reactive/error/DefaultErrorWebExceptionHandler.html)
- [Spring Framework — MVC Error Responses và ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html)
