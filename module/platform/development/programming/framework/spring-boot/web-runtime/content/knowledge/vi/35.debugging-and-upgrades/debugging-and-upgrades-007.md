# 500 do tuần tự hóa, template hoặc lỗi sau khi phản hồi đã commit

## 1. Vì sao controller chạy xong nhưng HTTP vẫn lỗi?

Trong Spring Boot web runtime, việc controller trả về một Java object hoặc một view name **không đồng nghĩa HTTP response đã hoàn tất**. Ví dụ controller trả `OrderDto` bình thường nhưng Jackson phải đọc một getter gây exception; hoặc `@Controller` trả `"order/detail"` nhưng Thymeleaf không thể resolve template. Cả hai lỗi xuất hiện **sau khi method controller return**. Nếu chúng xảy ra khi response còn sửa được, server thường có thể trả **HTTP 500**.

Phức tạp hơn, khi một endpoint đã gửi headers hoặc một phần body, rồi serialization, template rendering hoặc streaming phát sinh lỗi, response có thể đã **committed**. Khi đó server **không thể quay lại sửa HTTP status 200 thành 500**, cũng không thể thay phần body đã phát bằng JSON error mới. Log server có thể ghi exception dù client thấy status 200 với body cụt, kết nối bị đóng/reset hoặc không parse được JSON.

Bài thuộc mục **Gỡ lỗi và nâng cấp**, tập trung vào:
1. Phân biệt lỗi ở controller, Jackson `HttpMessageConverter`, template view rendering và streaming/asynchronous response.
2. Nhận diện `HttpMessageNotWritableException`, `JsonMappingException`, `InvalidDefinitionException`, `TemplateInputException`, `TemplateProcessingException` và các exception sau commit.
3. Hiểu `HttpServletResponse.isCommitted()`, `flushBuffer()`, headers, response buffers và giới hạn của `@ExceptionHandler`/`/error`.
4. Tái hiện lỗi với **Spring Boot 3.5.x + Java 17+**, Spring MVC, Thymeleaf và endpoint cố tình flush rồi ném exception.
5. Thiết kế DTO, xử lý template null/missing resources, pre-render/validate payload có giới hạn và protocol lỗi cho stream.
6. So sánh Spring MVC và WebFlux; điều tra lỗi sau commit qua logs/metrics/traces mà không tin riêng HTTP status.
7. Tạo integration tests phân biệt **sự cố có thể trả 500** với **response đã commit không thể đổi status**.
8. Biết cách chẩn đoán lỗi xuất hiện **sau khi nâng cấp** Spring Boot/Jackson/Thymeleaf, classpath hoặc deploy image.

> **Phạm vi phiên bản:** Spring Boot **3.5.x**, Spring Framework **6.2.x**, Java **17+**. Demo dùng Spring MVC với embedded Tomcat và Jackson từ `spring-boot-starter-web`, view engine từ `spring-boot-starter-thymeleaf`. Các thông điệp exception, JSON error body và behavior sau commit có thể khác giữa versions, embedded servers, proxy và HTTP/1.1/HTTP/2. Không đóng đinh một status/body sau khi response đã commit.

## 2. HTTP pipeline: “return object” chưa phải “write body thành công”

~~~text
Client HTTP request
        |
        v
Filter chain / DispatcherServlet / route mapping
        |
        v
Controller method execution
        |
        +---- @RestController / @ResponseBody
        |          |
        |          v
        |    ReturnValueHandler
        |          |
        |          v
        |    HttpMessageConverter (Jackson, String, byte[], ...)
        |          |
        |          v
        |    HTTP response OutputStream / container buffer
        |
        +---- @Controller returns view name
                   |
                   v
             ViewResolver / Thymeleaf
                   |
                   v
             Template evaluation/render
                   |
                   v
             HTTP response Writer / container buffer
                           |
                           v
                     Socket / proxy / client
~~~

Một method:

~~~java
@GetMapping("/orders/123")
public OrderDto getOrder() {
    return service.fetchOrder();
}
~~~

có thể hoàn thành mà không throw. Sau đó `MappingJackson2HttpMessageConverter` mới tuần tự hóa giá trị trả về. Trong quá trình này, Jackson có thể:
- Gọi một getter ném exception.
- Truy cập JPA lazy property khi Hibernate session đã đóng.
- Lặp vô hạn qua quan hệ hai chiều.
- Gặp type không có serializer/module phù hợp.
- Lỗi custom serializer, Java time module, proxy hoặc object graph kỳ dị.

Tương tự, controller:

~~~java
@GetMapping("/order")
public String orderPage(Model model) {
    model.addAttribute("order", service.loadOrder());
    return "order-detail";
}
~~~

chỉ trả **view name**. Spring còn cần tìm `templates/order-detail.html` và thực hiện Thymeleaf/SpringEL evaluation. Lỗi có thể xuất hiện ở template, **không phải trong dòng return**.

### 500 là dấu hiệu HTTP, không phải toàn bộ kết quả business

HTTP 500 báo server không thể xử lý request thành công. Nhưng có ba tình huống rất khác:
- Controller ném lỗi trước khi ghi: error resolver có cơ hội trả 500 sạch.
- Controller trả object nhưng Jackson/template fail trước commit: có thể trả 500 thông qua error path.
- Headers/body đã commit rồi mới fail: **status trên wire không đổi được**, dù backend exception severity cao. Client có thể phải phát hiện body/stream chưa hoàn tất ở tầng application protocol.

Không dùng một con số `http.server.requests 5xx` làm bằng chứng mọi response hoàn tất hợp lệ: hậu commit errors có thể không phản ánh chính xác trong HTTP status metrics.

## 3. Response “committed” nghĩa là gì?

Trong Servlet API, response bắt đầu ở trạng thái **chưa commit**. Server có thể đặt:
- HTTP status.
- Headers, cookies.
- Content-Type, Content-Length (nếu biết).
- Buffer chứa bytes chưa flush ra network.

Khi server **commit** response, HTTP status và headers đã được xác nhận để gửi qua transport. Sau thời điểm đó:
- Không thể đổi status hiệu quả trên wire.
- Không thể reset để gửi một response thay thế sạch.
- Không thể redirect/error-forward theo cách thông thường nếu nó cần thay status/headers.
- Không thể lấy lại những bytes đã gửi đến client.

Servlet cung cấp:

~~~java
HttpServletResponse response = ...;   // fragment trong servlet/controller
boolean committed = response.isCommitted();
response.flushBuffer();               // chủ động flush và commit
~~~

Nếu buffer đầy, container tự flush hoặc một code path gọi `getWriter().flush()`, `getOutputStream().flush()`, `flushBuffer()`, response cũng có thể commit. **“Đã có code viết vài bytes” chưa chắc đã committed** nếu bytes vẫn ở buffer nội bộ. Ngược lại, có thể **committed ngay khi chỉ có headers**, chưa có body.

### Trạng thái có thể minh họa

~~~text
UNCOMMITTED
  status=200 (default)
  headers mutable
  bytes may be in servlet buffer
     |
     +-- exception here:
     |       handler/error mapping còn có cơ hội set status=500
     |
     +-- buffer full / flushBuffer / writer.flush / streaming
     v
COMMITTED
  status + headers đã ra khỏi vùng có thể sửa
  partial body may be visible
     |
     +-- exception here:
             cannot turn previously emitted response into 500
             may close/reset connection, log, or mark stream failed
~~~

**Phân biệt:** Có những container/framework response implementations commit ở thời điểm cụ thể khác nhau. Không dựa vào `response.getBufferSize()` để khẳng định chính xác request nào sẽ commit; hãy dùng evidence `isCommitted()` tại thời điểm lỗi và quan sát network behavior.

### Những thông báo lỗi thường đi kèm

~~~text
java.lang.IllegalStateException:
Cannot call sendError() after the response has been committed
~~~

~~~text
Cannot forward to error page ... as the response has already been committed
~~~

~~~text
Unable to handle the Spring Security Exception because
the response is already committed
~~~

Text chính xác khác theo version/container. Các dòng trên thường là **lỗi thứ cấp khi một bộ xử lý lỗi cố thay response đã commit**. Hãy tìm **exception đầu tiên/root cause** dẫn đến streaming/serialization/template failure. Đừng chỉ sửa chỗ cuối cùng in ra `Cannot call sendError`.

## 4. Phân loại nhanh 500 và lỗi liên quan

| Dấu hiệu | Bước thường xảy ra lỗi | Nguyên nhân gợi ý |
|---|---|---|
| `HttpMessageNotWritableException` | Spring MVC viết response body | Serializer lỗi, type/converter không phù hợp |
| `JsonMappingException` | Jackson serialize/deserialize object | Getter lỗi, graph cycles, field mapping |
| `InvalidDefinitionException` | Jackson định nghĩa serializer/deserializer | Không có serializer/module, type không hỗ trợ |
| `StackOverflowError` / Jackson nested reference | Object graph traverse | Quan hệ hai chiều, recursion |
| `LazyInitializationException` | Jackson chạm JPA lazy proxy | Persistence session/transaction đã đóng |
| `TemplateInputException` | Thymeleaf load/resolve template | Sai tên, không có trong jar, resolver misconfig |
| `TemplateProcessingException` | Thymeleaf render expression/fragment | SpringEL lỗi, null, expression syntax |
| `SpelEvaluationException` | SpringEL eval trong view | Property/method trên null hoặc access invalid |
| `HttpMessageNotReadableException` | **Đọc request body**, không phải ghi response | JSON đầu vào malformed, thường 400 |
| `HttpMediaTypeNotAcceptableException` | Content negotiation | Không đáp ứng được Accept, có thể 406 |
| `HttpMediaTypeNotSupportedException` | Request Content-Type không hỗ trợ | Thường 415 |
| `IllegalStateException: response already committed` | Error handler cố đổi response sau commit | Hậu quả của lỗi sau flush |
| `ClientAbortException`, broken pipe, connection reset | Client/proxy disconnect khi server đang write | Có thể do client rời đi, không phải code bug |
| HTTP 200 + incomplete JSON/HTML/CSV | Body ghi một phần rồi fail | Cần logs, client completeness check |
| 500 nhưng controller log success | Converter/view stage lỗi **sau controller** | Kiểm tra outermost/root stacktrace |

**Quan trọng:** không phải mọi `JsonMappingException` đều dẫn đến HTTP 500. Khi **deserialize request JSON đầu vào**, error thường thành `HttpMessageNotReadableException` và HTTP 400 (client input sai); khi **serialize server response** mới thường là server 500. Luôn xem hướng dữ liệu và stacktrace.

## 5. Jackson output serialization: vì sao có thể lỗi sau return?

Trong Spring MVC, `@RestController` tương đương `@Controller` + `@ResponseBody`. Object return được `HttpMessageConverter` chuyển thành JSON khi negotiated Content-Type phù hợp. Jackson mapper của Boot thường được tự cấu hình kèm modules đã có trên classpath.

Ví dụ lỗi getter:

~~~java
public final class UnsafeDto {
    public String getId() {
        return "o-42";
    }

    public String getStatus() {
        throw new IllegalStateException("Getter failed");
    }
}
~~~

Controller trả `new UnsafeDto()` hoàn toàn bình thường. Nhưng khi Jackson truy cập `getStatus()`, exception mới phát sinh. Tùy serializer/container buffer, một vài JSON tokens có thể đã được tạo; nếu response chưa commit, error mapper có thể trả 500. Nếu đã commit, không thể gửi JSON error thay thế.

### Nhóm nguyên nhân phổ biến

**A. Getters chứa business logic/I/O**

Sai thiết kế:

~~~java
public BigDecimal getTotal() {
    return billingApi.calculateTotal(orderId); // network I/O tại getter
}
~~~

Serialize response lúc này có thể fail vì downstream timeout. Getter DTO nên trả dữ liệu **đã chuẩn bị trước**, không gọi database/network tùy hứng trong serialization phase.

**B. JPA entities trả thẳng**

~~~java
@GetMapping("/orders/{id}")
public OrderEntity order(@PathVariable long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Đây là **fragment**, chưa có entity/repository definitions. Nếu entity có lazy relationships, transaction/session đóng khi Jackson đọc các properties, có thể gặp `org.hibernate.LazyInitializationException`. Trả entity trực tiếp còn làm lộ fields, cycles và cấu trúc DB.

**Cách tốt hơn:** map thành immutable DTO/service projection khi cần dữ liệu, trong transaction thích hợp; truy xuất quan hệ theo `join fetch`/`EntityGraph`/query projection được cân nhắc, tránh “bật open-in-view cho khỏi lỗi” mà không xét N+1/security.

**C. Cyclic graph**

~~~text
Order -> Customer -> List<Order> -> Customer -> ...
~~~

Jackson có thể đệ quy sâu, tạo error hoặc bị stack overflow. Ưu tiên API DTO không biểu diễn full entity graph; có thể xem `@JsonIgnore`, `@JsonManagedReference`/`@JsonBackReference` hoặc `@JsonIdentityInfo` khi semantics phù hợp. Đừng che cycle bằng cách tăng heap cho đến khi hết lỗi.

**D. Missing Java Time module hoặc custom mapper khác Boot**

Java time types như `LocalDateTime` cần Jackson datatype support phù hợp. Boot starter JSON thường đăng ký modules hiện có; tạo `new ObjectMapper()` ngoài Boot configuration có thể thiếu modules/cấu hình chính sách nhất quán. Ưu tiên inject mapper do Boot quản lý hoặc configure modules có chủ đích.

**E. Type không có serializer/mismatched converter**

DTO không có property accessors, generated proxies, records với custom visibility rules, polymorphic type info sai hoặc handler trả một loại không có converter tương ứng có thể dẫn tới `InvalidDefinitionException`/`HttpMessageNotWritableException`. Đôi khi vấn đề thực tế là Accept/produces mismatch (406) chứ không phải Jackson serialization.

**F. Security data leaks từ toString/getter**

Không để Jackson tự traverse password/token/credential fields. Dùng output DTO và whitelist fields; không log toàn bộ object graph khi serialization lỗi.

## 6. Thymeleaf: controller trả view name nhưng chưa render xong

Spring MVC view resolution thường diễn ra sau method `@Controller` hoàn tất:

~~~java
@Controller
class PageController {
    @GetMapping("/page/profile")
    String profile(Model model) {
        model.addAttribute("name", "Linh");
        return "profile";
    }
}
~~~

Với `spring-boot-starter-thymeleaf`, mặc định template path thường là `classpath:/templates/`, suffix `.html`. Code trên cần file `src/main/resources/templates/profile.html`.

### Những lỗi template điển hình

1. Sai view name: return `"profile"` nhưng file mang tên `Profile.html`; hệ Linux/container phân biệt hoa/thường.
2. File template nằm sai thư mục hoặc bị quên khi build jar.
3. Có view resolver khác chiếm tên view, hoặc đổi `spring.thymeleaf.prefix`/`suffix` sai.
4. Thymeleaf `th:replace` trỏ fragment không tồn tại.
5. SpEL dereference null: `user.profile.name` trong khi `user` chưa nằm trong model.
6. Getter của model object ném error khi template evaluate.
7. Circular fragments/recursive inclusion tạo stack overflow.
8. Bản mới Thymeleaf/SpringEL kiểm tra expression/security chặt hơn.
9. HTML encoding/escaping sai hoặc dùng `th:utext` không an toàn tạo XSS.
10. Template parsing/syntax error chỉ xuất hiện tại runtime, test slice có thể không đóng gói đúng resources.

### Phân biệt hai loại lỗi

| Thymeleaf exception | Nơi nghi ngờ trước |
|---|---|
| `TemplateInputException` | Template không tìm thấy, input unreadable hoặc parse problem |
| `TemplateProcessingException` | Expression, property access, fragment/method evaluation trong quá trình process |
| Nested `SpelEvaluationException` | Property/method expression trên null hoặc sai type |
| Nested `IllegalStateException` | Getter/business method được template gọi gây lỗi |

Không suy “500 là Thymeleaf lỗi” chỉ từ việc endpoint là HTML. Hãy xem **exception chain** và template filename/line/column nếu log có, đồng thời kiểm tra resource có thật trong packaged jar.

## 7. Template không tồn tại khi đóng gói container

Một sự cố nâng cấp/deploy:
- Local IDE cho trang chạy.
- JAR trong Docker trả 500.
- Log có `Error resolving template [profile]`.

Các bước:
1. Kiểm tra file `src/main/resources/templates/profile.html` trong source.
2. Xác minh build tool đã include resources vào executable jar.
3. Kiểm tra case-sensitive naming trên Linux (`Profile.html` khác `profile.html`).
4. Kiểm tra profile-specific `spring.thymeleaf.prefix` và `suffix`.
5. Kiểm tra template engine dependency đúng và không bị exclude.
6. Nếu multi-module, bảo đảm module chứa template là dependency/runtime resource trong jar.
7. Nếu có `jar tf` trong JDK tools, kiểm tra resources packaging:

~~~bash
jar tf build/libs/app.jar | grep 'templates/'
~~~

Lệnh trên dành cho Bash/Linux/macOS. Windows PowerShell có thể dùng:

~~~powershell
jar tf .\build\libs\app.jar | Select-String 'templates/'
~~~

Không dùng tìm kiếm runtime resources để “sửa” bằng cách copy template bừa vào working directory; Spring Boot executable jar classpath mới là nguồn mặc định. Template cache production có thể giữ view đã compile, nên sau deploy phải đảm bảo image mới thực sự chứa tài nguyên mới và rollout hoàn thành.

### Không nhầm @RestController với @Controller

~~~java
@RestController
class WrongViewController {
    @GetMapping("/page")
    public String page() {
        return "profile";
    }
}
~~~

Ở đây response body là chuỗi `profile` (khi phù hợp), **không** được Thymeleaf render như view. Nếu muốn trả view name, dùng `@Controller`. Ngược lại, nếu API JSON trả string thuần, đừng chuyển sang `@Controller` rồi ngạc nhiên vì view resolution lỗi.

## 8. Thời điểm commit: trước hay sau khi lỗi?

| Điểm lỗi | Response đã commit? | Có thể đổi HTTP status/body không? |
|---|---|---|
| Controller throw trước khi write | Thường chưa | Có thể trả 500/ProblemDetail |
| Jackson fail trong pre-serialize byte[] trước HTTP write | Chưa | Có thể trả 500 rõ ràng |
| Jackson fail khi converter bắt đầu write | Phụ thuộc buffer/flush | Có thể, nếu chưa commit; không nếu đã commit |
| Thymeleaf fail trước khi ghi output | Thường chưa | Có thể trả 500/error view |
| Thymeleaf fail sau khi writer đã flush | Đã commit | Không thay được phần đã gửi |
| `StreamingResponseBody` flush rồi throw | Đã commit | Không chuyển thành response lỗi mới |
| `SseEmitter` đã send event, rồi fail | Thường đã commit | Không đổi HTTP status; cần stream protocol |
| WebFlux `Flux` emit vài chunks rồi `onError` | Thường đã commit | Không sửa headers/status trên wire |
| Proxy đã chuyển headers cho client | Phía client có thể đã thấy status | Backend không thể “rút lại” |
| Client disconnect trước khi response complete | Có thể | Server không còn truyền error body đến client |

**Không khẳng định mọi JSON serialization xảy ra “all at once” trước khi commit.** Jackson/Servlet converter có thể serialize và ghi từng đoạn vào buffer/stream. Với payload nhỏ, buffer thường giữ đủ nên có thể trả 500 sạch; payload lớn, flush hoặc streaming làm rủi ro hậu commit rõ hơn.

### setStatus không có hiệu lực sau commit

Trong Servlet:

~~~java
// Fragment trong controller/filter, có HttpServletResponse response
response.setStatus(500); // nếu đã committed thì không sửa status đã gửi
~~~

Nếu gọi `sendError(500)` sau commit, container có thể ném `IllegalStateException`. Một handler cố reset buffer sau commit có thể thất bại. Thêm `@RestControllerAdvice` là hữu ích cho lỗi **trước commit**, nhưng không phải phép thuật để thay response client đã nhận.

## 9. Demo chạy được: Spring Boot 3.5 MVC + Thymeleaf + lỗi hậu commit

Chúng ta tạo một dự án để tự quan sát các đường đi:
- `GET /api/ok`: JSON bình thường.
- `GET /api/serialize-error`: trả bean có getter cố ý throw **lúc Jackson serialize**.
- `GET /api/serialize-prechecked`: chủ động serialize **trước khi trả response**, nếu lỗi thì trả một body error nhỏ, có status 500 nhất quán.
- `GET /api/committed-error`: ghi `part-1`, gọi `response.flushBuffer()`, rồi throw.
- `GET /api/stream-error`: `StreamingResponseBody` ghi/flush một đoạn rồi lỗi async.
- `GET /page/ok`: view Thymeleaf thành công.
- `GET /page/broken`: view Thymeleaf gọi model property trên null.
- `GET /page/missing`: view name không có file template.

**Cảnh báo:** các endpoints `*-error` được thiết kế cố ý tạo exception. Chỉ chạy **local/test**, không expose trên public/production deployments.

### 9.1. Gradle dependencies

Tạo project từ Spring Initializr:
- Boot **3.5.x**, Java **17+**, Gradle Groovy, artifact `commit-error-demo`.
- Dependencies: **Spring Web**, **Thymeleaf**, **Spring Boot Actuator** (tuỳ chọn cho metrics) và **Spring Boot Starter Test**.

Trong `build.gradle` được Initializr tạo, phần dependencies tương đương:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Chỉ là **fragment Gradle**; giữ các blocks plugins/repositories/version và wrapper của project từ Initializr. Không cần tự gắn Jackson version; Spring Boot dependency management phối hợp tương thích theo phiên bản.

### 9.2. Java file hoàn chỉnh

Tạo `src/main/java/demo/commiterror/CommitErrorApplication.java`:

~~~java
package demo.commiterror;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonPropertyOrder;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@SpringBootApplication
public class CommitErrorApplication {

    public static void main(String[] args) {
        SpringApplication.run(CommitErrorApplication.class, args);
    }
}

@RestController
class DemoApiController {

    private static final byte[] SAFE_ERROR = (
        "{\"type\":\"about:blank\","
        + "\"title\":\"Internal Server Error\","
        + "\"status\":500}"
    ).getBytes(StandardCharsets.UTF_8);

    private final ObjectMapper mapper;

    DemoApiController(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public record GoodPayload(String message, int count) { }

    @JsonPropertyOrder({"first", "second"})
    public static final class BrokenPayload {
        public String getFirst() {
            return "ok";
        }

        public String getSecond() {
            throw new IllegalStateException(
                "Deliberate failure inside a JSON getter");
        }
    }

    @GetMapping(
        path = "/api/ok",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public GoodPayload ok() {
        return new GoodPayload("ok", 1);
    }

    @GetMapping(
        path = "/api/serialize-error",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public BrokenPayload serializeError() {
        // Controller completes; Jackson invokes getSecond later.
        return new BrokenPayload();
    }

    @GetMapping(
        path = "/api/serialize-prechecked",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<byte[]> serializePrechecked() {
        try {
            // Do JSON work BEFORE HttpMessageConverter starts writing.
            byte[] json = mapper.writeValueAsBytes(
                new BrokenPayload());

            return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(json);
        } catch (JsonProcessingException ex) {
            // Deliberately return a minimal, non-sensitive error.
            // The HTTP response has not been written here yet.
            return ResponseEntity.status(
                    HttpStatus.INTERNAL_SERVER_ERROR)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(SAFE_ERROR);
        }
    }

    @GetMapping(
        path = "/api/committed-error",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public void committedError(HttpServletResponse response)
            throws IOException {

        response.setStatus(HttpStatus.OK.value());
        response.setCharacterEncoding("UTF-8");
        response.setContentType("text/plain");

        response.getWriter().write("part-1\n");
        response.flushBuffer(); // explicitly COMMIT 200 + headers
        System.out.println(
            "DEMO_AFTER_COMMIT=" + response.isCommitted());

        // Spring cannot replace the already-sent status/body with 500.
        throw new IllegalStateException(
            "Deliberate error after flushBuffer");
    }

    @GetMapping(
        path = "/api/stream-error",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public StreamingResponseBody streamError() {
        return output -> {
            output.write(
                "first-chunk\n".getBytes(StandardCharsets.UTF_8));
            output.flush(); // commits response
            throw new IOException("Deliberate streaming failure");
        };
    }
}

@Controller
class DemoPageController {

    @GetMapping("/page/ok")
    public String ok(Model model) {
        model.addAttribute("name", "Linh");
        return "ok";
    }

    @GetMapping("/page/broken")
    public String broken() {
        // broken.html tries to evaluate a missing model variable.
        return "broken";
    }

    @GetMapping("/page/missing")
    public String missing() {
        // No corresponding templates/missing.html file.
        return "missing";
    }
}
~~~

### 9.3. Giải thích tính runnable của source

- File có đúng một public top-level class `CommitErrorApplication`, khớp tên file.
- Hai package-private classes `DemoApiController` và `DemoPageController` cùng package nên được component scan.
- `ObjectMapper` được constructor injection từ Spring Boot-configured Jackson mapper; không tự tạo `new ObjectMapper()`.
- `BrokenPayload.getSecond()` chắc chắn throw khi Jackson cố serialize property second. Việc mapper wrap error thành `JsonProcessingException` là behavior phù hợp với Jackson mapping exception; HTTP error code cho endpoint trực tiếp còn tùy commit/error handling.
- `@JsonPropertyOrder` giúp thứ tự hai JSON properties có chủ đích, nhưng **không** bảo đảm cùng một trạng thái commit nếu transport/buffering khác.
- `serializePrechecked()` gọi `mapper.writeValueAsBytes(...)` trong controller, tức là phát hiện serialization error **trước khi body được giao cho HTTP writer**. Trường hợp catch trả mảng UTF-8 nhỏ với status 500 và `application/problem+json`. Đây là demo minh họa deterministic error response, **không nên pre-serialize mọi payload lớn**.
- `committedError()` gọi `flushBuffer()` để ép response committed rồi mới throw. Log `DEMO_AFTER_COMMIT=true` kỳ vọng tại điểm đó theo Servlet API. **Không kỳ vọng client luôn nhận một JSON 500**.
- `StreamingResponseBody` có async lifecycle; Spring MVC có thể cần AsyncTaskExecutor production được cấu hình thích hợp. Lỗi sau flush là minh họa failure path, không phải một streaming endpoint hữu ích.
- `@Controller` trả tên template, không phải raw text như `@RestController`.
- `Map` import chỉ nhằm giữ ví dụ dễ mở rộng, không tham gia logic; có thể bỏ import không dùng. Trình biên dịch Java cho phép unused imports, IDE có thể cảnh báo.

### 9.4. Thymeleaf templates

Tạo `src/main/resources/templates/ok.html`:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="utf-8">
  <title>Trang hợp lệ</title>
</head>
<body>
  <h1 th:text="${name}">Fallback</h1>
</body>
</html>
~~~

Khi `/page/ok` được gọi, Thymeleaf thay fallback thành `Linh` dưới dạng text được HTML-escape. Nếu trả về HTML với đúng chuỗi `Linh`, trang render thành công. Thứ tự/whitespace của HTML output không dùng làm assertion cứng trong test.

Tạo `src/main/resources/templates/broken.html`:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="utf-8">
  <title>Trang cố ý lỗi</title>
</head>
<body>
  <p>Trang trước biểu thức.</p>
  <p th:text="${user.profile.name}">Không có user</p>
</body>
</html>
~~~

Controller `/page/broken` không đặt model attribute `user`. Thymeleaf/SpringEL cần dereference `user.profile.name` nhưng `user` là null → exception khi processing template. Thời điểm commit tùy template output buffering; không assert exact body lỗi.

**Không tạo** `templates/missing.html`. `/page/missing` trả view name missing nên Thymeleaf có thể báo `TemplateInputException` khi không tìm thấy file. Nếu bạn tạo file đó, endpoint sẽ không còn tái hiện lỗi.

### 9.5. application.yml

Tạo `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  error:
    include-message: never
    include-stacktrace: never
    include-exception: false

spring:
  thymeleaf:
    cache: false

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics"
~~~

- `server.error.include-message=never` và `include-stacktrace=never` giúp hạn chế thông tin lỗi trả về client.
- `spring.thymeleaf.cache=false` phục vụ **development/test**, để dễ thay template và kiểm tra render; production nên để cache phù hợp.
- Chỉ expose Actuator health/metrics cho local; production bảo vệ management endpoints/auth/network, không public diagnostics.
- Không bật `server.error.include-stacktrace=always` để debug production; dùng server logs/traces có quyền truy cập.
- Tắt cache không phải cách sửa thiếu template trong packaged jar.

### 9.6. Chạy ứng dụng

Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Khi startup thành công, ứng dụng listen `http://localhost:8080`.

## 10. Quan sát bốn kiểu response khác nhau bằng curl

### 10.1. Endpoint JSON thành công

~~~bash
curl -sS -i \
  -H 'Accept: application/json' \
  http://localhost:8080/api/ok
~~~

Kỳ vọng status **200** và body có các fields:

~~~json
{"message":"ok","count":1}
~~~

Thứ tự fields không bảo đảm, nhưng tên và giá trị như trên.

### 10.2. Serialization lỗi sau controller

~~~bash
curl -v \
  -H 'Accept: application/json' \
  http://localhost:8080/api/serialize-error
~~~

Kiểm tra server logs: `getSecond()` throw, Jackson có thể wrap thành `JsonMappingException`/`HttpMessageNotWritableException`. Nếu response chưa committed, framework/container có cơ hội trả HTTP 500, error JSON/HTML theo negotiation và Boot error handling. Nếu response đã committed, kết quả có thể khác. **Không ghi một output JSON 500 giả định như thể mọi version chắc chắn vậy.**

### 10.3. Prevalidate trước khi viết response

~~~bash
curl -sS -i \
  http://localhost:8080/api/serialize-prechecked
~~~

Với demo này, `mapper.writeValueAsBytes(new BrokenPayload())` phát sinh `JsonProcessingException` và controller **chủ động** trả status 500 cùng body:

~~~json
{"type":"about:blank","title":"Internal Server Error","status":500}
~~~

Đây là output do chính mã demo tạo, không phụ thuộc định dạng `/error` tự động của Boot. Dù vậy nếu lỗi xảy ra sau khi đã trả mảng byte hoặc có filter/proxy can thiệp, quy tắc commit vẫn áp dụng; không gọi đây là **global guarantee** cho mọi mạng/server.

### 10.4. Cố tình commit 200 rồi throw

~~~bash
curl -v \
  http://localhost:8080/api/committed-error
~~~

Server đã gọi `flushBuffer()` trước exception. Trong log demo có thể thấy:

~~~text
DEMO_AFTER_COMMIT=true
~~~

Response thường có status **200** với body bắt đầu:

~~~text
part-1
~~~

Sau đó connection có thể đóng, một lỗi async/servlet có thể được log, hoặc client có thể nhận body ngắn. Không có bảo đảm sẽ hiển thị nguyên vẹn một dòng kết thúc; **điểm bất biến là status/headers đã commit không thể đổi thành 500**. Nếu bạn thấy stacktrace server nhưng HTTP status 200, đây chính là trường hợp cần tránh chẩn đoán bằng status metrics đơn thuần.

### 10.5. Streaming error

~~~bash
curl -v -N \
  http://localhost:8080/api/stream-error
~~~

Body bắt đầu `first-chunk` rồi IOException. `curl` có thể báo receive error, transfer closed unexpectedly hoặc không có message cụ thể, tùy framing và server. `-N` tắt output buffering của curl để thấy chunks sớm hơn; nó không khiến Spring tự flush nếu server chưa gửi.

### 10.6. Template đúng và sai

~~~bash
curl -sS -i http://localhost:8080/page/ok
curl -v http://localhost:8080/page/broken
curl -v http://localhost:8080/page/missing
~~~

Kỳ vọng `/page/ok` trả 200 và HTML chứa `Linh`. Hai endpoint kia được thiết kế có lỗi template rendering/resolution và có thể trả 500 nếu response vẫn sửa được. Tìm stacktrace Thymeleaf để phân biệt **missing template** với **null expression**, không dựa vào một HTTP status giống nhau.

## 11. @ExceptionHandler, /error và ProblemDetail chỉ giúp được trước commit

Spring MVC dùng chuỗi `HandlerExceptionResolver` như:
- `ExceptionHandlerExceptionResolver`: các `@ExceptionHandler` / `@ControllerAdvice`.
- `ResponseStatusExceptionResolver`.
- `DefaultHandlerExceptionResolver`.
- Boot còn có `/error` mapping và `BasicErrorController`/error pages theo cấu hình.

Khi exception được phát hiện trước commit, framework có thể tạo một response lỗi hợp lệ. Ví dụ fragment:

~~~java
@RestControllerAdvice
class ApiErrorAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<ProblemDetail> handle(IllegalArgumentException ex) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST, "Invalid request");
        return ResponseEntity.badRequest().body(body);
    }
}
~~~

Imports cần:
- `org.springframework.web.bind.annotation.RestControllerAdvice`.
- `org.springframework.web.bind.annotation.ExceptionHandler`.
- `org.springframework.http.ProblemDetail`.
- `org.springframework.http.ResponseEntity`.
- `org.springframework.http.HttpStatus`.

Đây là **fragment độc lập với demo chính**. Nó thể hiện lỗi **trước HTTP write** có thể được map thành RFC 9457 `ProblemDetail`. Nó **không cứu được** khi response đã commit. Bản thân `ProblemDetail` còn phải được serialize; nếu lỗi xảy ra trong custom converter/serializer của error body, error handler có thể cũng lỗi.

### Problem Details không phải điều trị gốc

Spring MVC hỗ trợ RFC 9457, trong Boot 3.x có property cấu hình Problem Details cho một số framework exceptions theo version. Việc bật property có thể thay **hình dạng error response trước commit**, không thay định luật HTTP:
- Không sửa status đã gửi.
- Không rút lại JSON tokens đã phát.
- Không khiến SSE/Flux failure tự động biến thành HTTP 500.
- Không tự xử lý business side effects đã commit database trước khi network lỗi.

### Khi request qua proxy

Giả sử application đã gửi `HTTP/1.1 200 OK` và vài kilobytes JSON tới reverse proxy. Proxy có thể:
- Chuyển status 200 xuống client ngay và sau đó đóng stream.
- Buffer response, phát 502 khi upstream bị cắt (tùy cấu hình).
- Trả partial body hoặc log upstream prematurely closed connection.
- Với HTTP/2, reset stream; status ban đầu có thể vẫn xuất hiện trong browser DevTools.

Không đoán chung “proxy luôn trả 502”. Phải đối chiếu client headers, proxy access/error logs, upstream logs và request IDs.

## 12. Khi response đã commit, đúng hướng xử lý là gì?

**Không** cố gọi thêm `sendError(500)`, `sendRedirect(...)` hoặc serialize một object lỗi mới vào giữa body JSON đã bắt đầu, vì chúng không thể tạo một HTTP response 500 hợp lệ. Thay vào đó:

1. Ghi log lỗi tại component thực sự phát sinh, có phase, route, request/trace ID và trạng thái committed nếu có.
2. Không log toàn bộ body/token/cookies/sensitive data.
3. Tùy framework/transport, kết thúc stream/close connection theo lifecycle đúng; không tự ghi bytes tùy tiện sau IOException.
4. Với protocol có hỗ trợ message-level error, phát một **event lỗi có cấu trúc** nếu stream vẫn còn ghi được và error frame hợp lệ.
5. Client phải xác minh **application-level completeness**, không coi “status 200” tự động bằng “file/result đã hoàn tất”.
6. Những tác vụ side-effect phải có operation ID/idempotency/status lookup; hậu commit không có nghĩa transaction chưa thành công.
7. Thiết kế retry/backoff/resume cho streaming downloads/SSE khi client disconnect.
8. Quan sát số failures sau commit riêng với HTTP 5xx.

### HTTP body khác application protocol

Một API trả **một JSON object** không thể hợp lệ nếu bỗng chèn:

~~~text
{"data":[1,2,
{"error":"failed"}
~~~

Đó thường là JSON không hợp lệ. Với **NDJSON**, một protocol có thể định nghĩa dòng cuối là `{"type":"error",...}`; với SSE có thể định nghĩa `event: error`, nhưng phải có contract rõ rằng stream có một **terminal success/error signal** và client kiểm tra nó.

Ví dụ NDJSON protocol concept:

~~~text
{"type":"item","value":1}
{"type":"item","value":2}
{"type":"error","code":"UPSTREAM_TIMEOUT"}
~~~

Client biết stream đã kết thúc không thành công vì error record; **HTTP status vẫn có thể là 200** vì đã commit. Nếu kết nối rớt trước khi gửi error record, client cần nhận ra thiếu terminal completion marker/timeouts. Không phát một error record giả làm item business nếu downstream không có schema phân biệt.

## 13. Spring WebFlux: lỗi sau khi Flux bắt đầu emit

WebFlux dùng `HttpMessageWriter`, Reactor `Mono/Flux` và `ServerHttpResponse`. Ranh giới tương tự:
- `Mono.error(...)` **trước khi** headers/body được commit: framework error handler có thể tạo 500.
- `Flux` đã emit vài `DataBuffer`/NDJSON/SSE frames, writer flush, rồi `onError`: HTTP response có thể đã commit; không đổi status được.
- `ServerHttpResponse.isCommitted()` là cách kiểm tra trạng thái ở reactive response abstraction.
- `setStatusCode(...)` trả false khi status change không thể được áp dụng vì response đã commit (theo API contract).
- `beforeCommit(...)` đăng ký action chạy trước commit, không phải hook có thể sửa status **sau** commit.

Fragment WebFlux:

~~~java
// Fragment trong WebFlux handler, có ServerHttpResponse response.
if (!response.isCommitted()) {
    response.setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR);
    return response.setComplete();
}

// Response đã commit: không cố rewrite status/body.
return Mono.error(originalFailure);
~~~

Imports:
- `org.springframework.http.server.reactive.ServerHttpResponse`.
- `org.springframework.http.HttpStatus`.
- `reactor.core.publisher.Mono`.

Đây là **fragment**, `originalFailure` là exception đã có; nó không phải global WebFlux error handler runnable nguyên xi. Một `WebExceptionHandler` chuyên dụng phải tích hợp đúng chain, logging, cancellation và data buffers. Lặp logging ở nhiều layers có thể gây duplicate stacktraces.

### Những trường hợp reactive thường gặp

~~~java
// Fragment ví dụ publisher stream (không phải full controller):
Flux<String> source = Flux.just("a", "b")
    .concatWith(Flux.error(
        new IllegalStateException("late reactive error")));
~~~

Nếu được viết như NDJSON/SSE và từng phần tử đã flush, client có thể thấy “a”, “b” rồi stream kết thúc lỗi; response status không chuyển thành 500. Nếu codec quyết định **aggregate** publisher trước khi ghi (tùy Content-Type/return type), lỗi có thể tới trước commit. **Không suy từ loại Flux đơn thuần rằng response chắc chắn đã commit**: cần quan sát media type, writer và flush boundaries.

### Quản lý DataBuffer ownership

Khi custom reactive handler tạo/sử dụng `DataBuffer`, phải tuân pooled buffer retain/release semantics. Một lỗi serialization sau emit có thể đồng thời tạo buffer leak nếu application giữ `DataBuffer` references hoặc bỏ qua cancellation. Để framework writer sở hữu buffers đã chuyển giao; khi tự consume inbound buffer phải release nếu cần. Không gọi `DataBufferUtils.release` quá sớm khi outbound writer chưa đọc xong.

## 14. Thymeleaf error: cách phòng trước khi commit

Các quy tắc hữu ích:
- Không gọi database/web client từ getter của object đang render trong template.
- Chuẩn bị view model **trước khi** trả tên template.
- Với optional data, sử dụng biểu thức null-safe phù hợp với SpringEL/Thymeleaf version, hoặc cung cấp giá trị mặc định từ controller.
- Kiểm tra template existence trong packaged artifact khi build.
- Test fragments, layout dialect và changes giữa Thymeleaf versions.
- Dùng `th:text` cho text người dùng để HTML-escape; chỉ dùng `th:utext` với trusted/pre-sanitized HTML theo security policy.
- Không phụ thuộc template cache false để sửa missing resources.
- Đặt tên view rõ ràng, thống nhất case; tránh hai resolvers/fragment paths mơ hồ.
- Với trang HTML yêu cầu high reliability, có thể chuẩn bị rendering trong service trước khi commit **nếu size/latency cho phép**, nhưng template cần request/web context thì phải dùng context đúng, không thay bằng simple static string một cách cơ học.

### Error template tự nó cũng có thể lỗi

Nếu `templates/error/500.html` lại truy cập null model attribute hoặc fragment missing, error handling thất bại lần nữa. Dùng error page **đơn giản, độc lập và không truy cập DB/remote services**, không render thêm một view phức tạp vốn có thể lặp cùng lỗi.

Boot hỗ trợ custom error templates/static resources trong `error` directory theo status như `500.html` hoặc pattern 5xx. Những trang này chỉ hiển thị theo cơ chế error dispatch khi response **còn có thể thay được**; không thể render trang error đè lên body HTML đã flush.

## 15. Vì sao lỗi chỉ xuất hiện sau nâng cấp?

Các nhóm upgrade regressions:
- Boot/Spring Framework/Jackson/BOM versions **không đồng bộ** do override phụ thuộc thủ công.
- Jackson module/serializer changed behavior, custom getter không tương thích.
- Không có `jackson-datatype-jsr310` khi tự tạo mapper/loại bỏ starter.
- Hibernate/JPA lazy fetching khác do transaction boundaries/OSIV settings.
- Thymeleaf/SpringEL kiểm tra expressions chặt hơn, deprecated syntax.
- Template file bị mất sau chuyển build/multi-module/container image.
- `javax.servlet.*` code cũ đem sang Boot 3 (`jakarta.servlet.*`) gây classloading/method mismatch.
- Custom `HttpMessageConverter`/`WebMvcConfigurer` thay default converters ngoài ý muốn.
- Content negotiation, controller return type, `produces`/Accept headers đổi.
- Filters/interceptors tự gọi `flushBuffer`/`getWriter().flush` sớm hoặc nén/proxy buffering thay đổi.
- Spring Security exception handling khác khi auth failure phát sinh sau streaming response đã commit.

### Phân biệt source issue với dependency drift

Nếu thấy `NoSuchMethodError`, `ClassNotFoundException`, `NoClassDefFoundError` hoặc `LinkageError` sau nâng cấp, kiểm tra **runtime dependency graph/BOM alignment** trước. Không sửa bằng cách bắt `Exception.class` rồi trả 500 chung.

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
~~~

Dùng đúng project dependency management, loại bỏ Jackson/Spring version override không cần thiết, rebuild clean/test, kiểm tra packaged jar khác IDE classpath. Một WAR external servlet container có dependency/classloader behavior khác executable jar; kiểm tra rõ target packaging.

## 16. Test đúng điều cần test

**Bốn nhóm tests không thể thay nhau:**

1. **Unit serialization test**: dùng Boot-injected ObjectMapper serialize các DTO/records thật; phát hiện accessor/module/cycle trước HTTP.
2. **MVC view integration test**: render Thymeleaf với đủ/thiếu model attributes, fragments và packaged resources.
3. **Real HTTP integration test**: mở embedded server, dùng HTTP client và quan sát status + body + socket behavior.
4. **Streaming/cancellation/proxy test**: cần HTTP client thật qua container/ingress, kiểm tra partial response, completion markers, disconnects, error metrics.

Không dùng duy nhất MockMvc để kết luận socket đã committed ra ngoài; mock response buffers và container-specific flush behavior không đồng nhất Tomcat/Jetty/Netty.

### 16.1. Java 17 integration test đầy đủ

Tạo `src/test/java/demo/commiterror/CommitErrorApplicationTests.java`:

~~~java
package demo.commiterror;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class CommitErrorApplicationTests {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private HttpResponse<String> get(String path) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("http://localhost:" + port + path))
            .GET()
            .build();
        return client.send(
            request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void validJsonEndpointWorks() throws Exception {
        HttpResponse<String> response = get("/api/ok");
        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"message\":\"ok\""));
        assertTrue(response.body().contains("\"count\":1"));
    }

    @Test
    void jacksonFailureExistsIndependentOfHttp() {
        assertThrows(JsonProcessingException.class, () ->
            mapper.writeValueAsBytes(
                new DemoApiController.BrokenPayload()));
    }

    @Test
    void prevalidatedFailureHasStable500Body() throws Exception {
        HttpResponse<String> response =
            get("/api/serialize-prechecked");

        assertEquals(500, response.statusCode());
        assertTrue(response.body().contains("\"status\":500"));
        assertTrue(response.body().contains(
            "\"title\":\"Internal Server Error\""));
    }

    @Test
    void validThymeleafPageRenders() throws Exception {
        HttpResponse<String> response = get("/page/ok");
        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("Linh"));
    }
}
~~~

Test chạy với JUnit 5, Java 17 HTTP client, random embedded port và Boot injected ObjectMapper. Không assert JSON field ordering. Phần `/api/serialize-prechecked` có status 500 xác định vì controller chủ động serialize trước khi return. Ngược lại, **không** viết một test expect status 500 cố định cho `/api/committed-error` hoặc `/api/stream-error`, vì chúng cố tình commit rồi fail, test HTTP client có thể thấy status cũ hoặc network exception.

Chạy:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

**Không tuyên bố test đã chạy** trong mọi environment; đây là code/lệnh để người học thực thi. Khi chạy, kiểm tra logs của endpoint intentional failures riêng để phân biệt error handling double logging.

### 16.2. Test phạm vi template

Nên bổ sung tests (có thể dùng HTTP tests hoặc MVC testing):
- View `/page/ok` tồn tại, model có `name` → 200 + đúng text.
- View `/page/broken` lỗi biểu thức null trong Thymeleaf, logs có template/line.
- View `/page/missing` lỗi không có resource trong packaged jar.
- Render lại sau deploy jar/image, không chỉ khi chạy IDE.
- Kiểm tra custom error template khi exception xảy ra **trước commit**.
- Cố ý lỗi getter trong template, nhưng không dùng thông tin bí mật.
- Test change fragment/layout khi upgrade Thymeleaf.
- Khi cần content negotiation, thử `Accept: text/html` và `Accept: application/json` qua HTTP.

Không assert một HTML stacktrace trả về client. Production nên tránh lộ exception type/stack.

### 16.3. Test sau commit nên quan sát điều gì?

Với `/api/committed-error`:
- Java log `DEMO_AFTER_COMMIT=true`.
- Java log có initial root error từ method sau flush.
- Client đã nhận status/headers của response bắt đầu; có thể thấy 200 và partial body.
- Nếu proxy đệm toàn bộ, client kết quả có thể là 502, reset hoặc một response khác.
- Không có một JSON 500 hợp lệ thay thế phần đã phát.
- Metric HTTP 5xx có thể **không tăng** tương ứng với lỗi business sau commit.

Với `/api/stream-error`:
- Client có thể thấy `first-chunk` trước failure.
- Servlet async error dispatch có thể chạy, nhưng không thể rewrite headers đã commit.
- Cần log stage `stream_write` và committed state; record stream completion flag riêng nếu nghiệp vụ cần.
- Tạo thêm một stream hoàn tất bình thường làm control case để so sánh.

## 17. Thiết kế để phát hiện lỗi trước HTTP write

Đối với JSON nhỏ, business quan trọng:
1. Trong service, thực hiện validation/mapping thành response DTO.
2. Không để DTO getters gọi database/network.
3. Nếu cần đảm bảo serialize được, dùng injected Boot `ObjectMapper` để tạo bounded `byte[]` trước khi trả.
4. Nếu serialization lỗi, trả 500/ProblemDetail nhỏ với message an toàn.
5. Trả byte[] qua `ByteArrayHttpMessageConverter` với content type nhất quán.
6. Test DTO shape và null/missing values ở integration layer.

**Trade-off:** pre-serialize gây thêm memory allocation/copy, đặc biệt nếu response lớn và concurrency cao. Không áp dụng cho mọi endpoint file/stream; thay vào đó dùng NDJSON/SSE streaming protocol có completion semantics, hoặc background job + status URL.

### Prevalidate template rendering

Nếu page rất nhỏ và yêu cầu phải chắc chắn render thành công trước khi gửi headers, có thể render template thành một String/byte[] **trước** khi return. Nhưng:
- Thymeleaf template cần đúng context; web-specific expressions, CSRF attributes, request locale và link rewriting có thể phụ thuộc request.
- Gấp đôi memory/copy nếu page lớn.
- Có thể tăng latency/GC pressure.
- Không nên khuyến nghị “render tất cả template thành String” như một quy tắc chung.

Phương án thường phù hợp hơn là **test đúng resources/model + tối giản template + tránh I/O trong getter**.

## 18. Observability: 5xx counter là chưa đủ

Một log hữu ích có thể có các trường:

~~~text
level=ERROR
event=response_write_failed
route=/api/orders/{id}
phase=jackson_serialization
response_committed=true
bytes_written=8192
trace_id=<opaque-id>
exception=JsonMappingException
~~~

Đây là **schema log minh họa**, không phải dòng mặc định Spring Boot tự phát. Không log raw order ID, JWT, cookie hoặc JSON body. Với template lỗi:

~~~text
level=ERROR
event=template_render_failed
view=order-detail
phase=thymeleaf_process
response_committed=false
exception=TemplateProcessingException
trace_id=<opaque-id>
~~~

### Metrics nên phân loại

| Metric / label có thể tự instrument | Ý nghĩa |
|---|---|
| `http.server.requests` | HTTP status/latency nhìn từ framework |
| `app.response.serialization.failures` | Số lỗi Jackson response serialization |
| `app.template.render.failures` | Số lỗi template engine |
| `app.response.after_commit.failures` | Exception khi response đã committed |
| `app.stream.completed` | Stream có terminal success không |
| `app.stream.partial.failures` | Stream fail trước completion marker |
| `app.error.handler.failures` | Error rendering/dispatch tự thất bại |
| `app.client.disconnected` | Broken pipe/client cancellation theo khả năng phát hiện |

Các `app.*` chỉ là **tên metric đề xuất**, không phải mặc định được Boot tạo. Tránh cardinality vô hạn (raw URL, raw trace/request/user ID) trong tags. Một backend có HTTP 200 nhưng stream complete marker bị thiếu phải được đo như **business failure** dù không nằm trong 5xx counter.

### Root cause vs exception thứ cấp

Tìm trong logs:
1. Exception **đầu tiên** tại cùng trace/request ID.
2. Class và stack location của Jackson/Thymeleaf/business getter.
3. Nếu có `response already committed`, xác định **ai gọi flush/write** trước exception.
4. Kiểm tra async thread/coroutine/Flux chain và context propagation.
5. Xem proxy access/error logs cùng timestamp.
6. So client evidence status/headers/body length/transfer error.
7. Phân biệt client abort bình thường với lỗi business trước đó.

Bật targeted DEBUG logs trong môi trường test nếu cần; **không** bật toàn bộ HTTP body logging/sensitive stacktraces trên production.

## 19. Chi tiết lỗi sau commit khi có filter, compression và security

Ngoài controller và converter, response có thể bị commit bởi:
- Filter tự gọi `response.flushBuffer()`.
- Logging/filter wrapper copy body và flush sớm.
- Security filter viết response error/redirect hoặc CSRF response rồi chain tiếp.
- Compression layer stream data ra client sớm.
- Server sendfile/large file transfer.
- ResponseBodyEmitter/SseEmitter gửi event.
- View engine render incremental HTML.
- Async processing và servlet container buffer capacity.
- Proxy buffering/HTTP/2 frame handling.

Nếu filter gọi `sendError(401)` **sau** handler đã write/flush 200, sẽ nhận exception “response already committed” thay vì status 401; đó là lỗi lifecycle ordering. Authentication/authorization cần chạy **trước** protected response writing. Không sửa bằng cách ignore exception hoặc cố gửi second response body.

### ContentCachingResponseWrapper có thể che triệu chứng nhưng không giải quyết gốc

Một số filters dùng `ContentCachingResponseWrapper` để cache response và copy body ở cuối. Nó có thể trì hoãn commit trong một số trường hợp, nhưng:
- Có memory overhead tỷ lệ body/concurrency.
- Không phù hợp unbounded streams/SSE/downloads.
- Có thể làm sai semantics streaming flush.
- Nếu quên `copyBodyToResponse()` sẽ trả body rỗng.
- Không sửa Jackson getter lỗi, template missing hoặc downstream I/O failure.

Không thêm wrapper toàn cục chỉ để “ép mọi response thành 500 đẹp”.

## 20. Xử lý stream có giao thức hoàn tất

### 20.1. NDJSON/line-delimited protocol

Ví dụ protocol response:

~~~text
{"type":"start","streamId":"s1"}
{"type":"item","index":1,"value":100}
{"type":"item","index":2,"value":200}
{"type":"complete","count":2}
~~~

Nếu exception xảy ra trước `complete`:
- Nếu còn có thể gửi frame, server có thể gửi `{"type":"error","code":"UPSTREAM_FAILURE"}`.
- Nếu network đã broken, không gửi được frame nào; client thấy thiếu terminal marker và coi stream incomplete.
- HTTP status có thể đã 200; client **không được coi 200 + hai item đầu là full success**.

Client nên có timeout, max byte count, ack/resume cursor và idempotency policy. Không gửi terminal error message trong stream mà downstream parser coi là business item.

### 20.2. SSE

SSE có thể dùng:
- `event: item`, `id: ...` cho dữ liệu.
- `event: error` với error code an toàn nếu connection còn ghi được.
- `event: complete` trước khi chủ động close khi protocol yêu cầu.

Nếu connection bị cắt trước complete, client reconnect theo `Last-Event-ID` **chỉ khi server lưu event log/replay state**. Không đặt request vô hạn rồi kỳ vọng graceful shutdown luôn giữ socket sống.

### 20.3. Download file

Với file download:
- Nếu dùng `Content-Length` chính xác, một số clients có thể phát hiện body ngắn.
- HTTP chunked/trailers và proxy behavior khác nhau theo stack.
- Gắn checksum/content hash khi có contract phù hợp.
- Download vào temporary file, chỉ rename thành final khi đủ bytes/hash.
- Với operation lớn, cân nhắc async generation rồi phục vụ file đã hoàn tất thay vì serialize trong cùng HTTP request.

HTTP 200 không đủ chứng minh file integrity.

## 21. Upgrade checklist: chẩn đoán theo thay đổi, không mò mẫm

Khi lỗi 500 xuất hiện ngay sau nâng cấp:
1. Xác định Boot/Spring/Jackson/Thymeleaf/Hibernate versions trước và sau.
2. Kiểm tra dependency graph runtime, đặc biệt các phiên bản bị override trái Boot BOM.
3. Xem stacktrace root; phân loại lỗi converter, template hay after commit.
4. Test response DTO với Boot ObjectMapper và sample object graph production representative.
5. Kiểm tra JPA lazy loading, N+1 và entity exposure sau thay đổi fetch policy.
6. Kiểm tra template resources/fragment names/case sensitivity **trong executable jar**.
7. Kiểm tra template security changes: SpringEL, method calls và null expressions.
8. Kiểm tra Content-Type/Accept, `produces`/converter order.
9. So sánh filter/interceptor logic, response wrappers và nơi gọi flush.
10. Chạy real HTTP tests trước/đúng sau đổi server stack hoặc proxy.
11. Kiểm tra Java `jakarta.servlet` migration nếu từ Boot 2.x sang Boot 3.x.
12. Xác minh container image build đúng source mới, không dùng stale Docker layer.
13. Giữ rollback/canary plan, theo dõi 5xx **và** after-commit failures.
14. Không vô hiệu Jackson strictness hoặc expose stacktrace công khai để “pass QA”.

**Nếu lỗi chỉ có ở production**, chú ý payload shape thật, proxy buffering, HTTPS/compression, timeouts, concurrency, JPA data cycles và size vượt servlet response buffer. Dữ liệu test quá nhỏ có thể không tái hiện commit timing.

## 22. Quy trình điều tra thực tế theo 10 bước

1. **Xác định endpoint** và response type: JSON, HTML/Thymeleaf, stream, SSE, file.
2. **Tái hiện** với `curl -v`, record headers, status, bytes, transfer error; không paste private tokens.
3. **Tìm earliest exception** theo traceId trong app logs.
4. **Phân loại stage**: handler → converter → template → transport/write → error handler.
5. **Kiểm tra committed** tại nơi bắt được lỗi nếu API/context cho phép; tránh instrumentation làm thay commit timing.
6. **Đọc nested cause**: Jackson getter, lazy init, template line/fragment, IOException client abort.
7. **Đối chiếu proxy logs** để hiểu client thực nhận gì.
8. **Test ở unit layer**: ObjectMapper serialization và template model.
9. **Sửa nguyên nhân** (DTO/mapper/template/stream protocol) thay vì chỉ bắt exception.
10. **Thêm regression tests + metrics** cho both pre-commit 500 và post-commit partial response.

### Lệnh an toàn để xem headers và body

~~~bash
curl --verbose --show-error \
  --output response.bin \
  http://localhost:8080/api/committed-error
~~~

Kiểm tra `response.bin` khi file có tồn tại, compare với expected body bytes. Trên local có thể dùng:

~~~bash
wc -c response.bin
~~~

Nếu `curl` exit nonzero vì connection error, **đừng đồng nhất “file đã được tạo” với success**. Khi dùng HTTP/2/Ingress, một kết nối có thể bị reset sau headers và clients report error khác nhau.

### Lỗi từ client disconnect có được coi 500?

Không tự động. Một browser đóng tab giữa streaming có thể tạo `IOException: Broken pipe` dù application không hỏng; nếu server cứ cố viết sau disconnect có thể nhận exception. Đếm riêng `client_aborted` vs `serialization_failure` vs `application_stream_failure`. Dùng rate/impact để quyết định severity; không phải mọi disconnect đều cần pager alert.

## 23. Bảng anti-pattern và phương án thay thế

| Anti-pattern | Hậu quả | Phương án |
|---|---|---|
| Trả trực tiếp JPA Entity ra JSON | Lazy proxy, cycles, lộ dữ liệu | Map thành DTO/projection |
| Getter DTO gọi DB/HTTP | I/O failure lúc Jackson write | Tính dữ liệu trong service trước return |
| Bắt mọi Exception rồi trả 200 + `{"error":...}` | Sai HTTP semantics, khó alert | Trả 4xx/5xx khi response còn uncommitted |
| `@ExceptionHandler` cố sendError sau flush | IllegalStateException thứ cấp | Dừng ghi; log, thiết kế stream protocol |
| `flushBuffer()` sớm không cần thiết | Không thể rollback error response | Chỉ flush khi muốn streaming thật |
| JSON array stream ghi giữa chừng rồi chèn error object | Body không còn valid JSON | NDJSON/SSE protocol có typed terminal frames |
| Return view name bằng `@RestController` | Trả raw string, không render HTML | Dùng `@Controller` |
| Template expression dereference null | Thymeleaf processing error | Validate model/null-safe fallback |
| Template missing trong JAR | Runtime 500 | Build/resource packaging tests |
| Tắt Thymeleaf cache để sửa production | Không sửa missing resources, tăng cost | Fix template path/build |
| Dùng `new ObjectMapper()` ngẫu nhiên | Thiếu Boot modules/config | Inject configured mapper |
| Serialize 500 MiB vào `byte[]` trước HTTP | Heap/GC/OOM | Streaming/async generation |
| Dùng ContentCachingResponseWrapper cho mọi stream | Memory bloat/buffer semantics | Targeted instrumentation; không cache all |
| Chỉ alert trên HTTP 5xx | Bỏ sót 200 + partial body | Track stream completion/after-commit errors |
| Trả stacktrace khi 500 | Lộ path/class/secret | Safe ProblemDetail + server logs |
| Assert status 500 cố định sau commit | Flaky tests/sai protocol | Assert response committed + client truncation behavior được quan sát |
| Blind retry POST sau mất kết nối | Duplicate side effects | Idempotency key/status lookup |
| Upgrade Jackson/Spring riêng khỏi BOM | Linkage/runtime serializer issues | Align dependency versions, regression tests |

## 24. Câu hỏi ôn tập

**1.** Vì sao controller return `OrderDto` bình thường nhưng HTTP cuối cùng là 500?

**Đáp án:** Response serialization bằng Jackson diễn ra sau khi controller return. Getter/module/graph có thể fail lúc `HttpMessageConverter` viết body.

**2.** Một template view name hợp lệ có chắc Thymeleaf render xong không?

**Đáp án:** Không. Spring còn resolve resource và evaluate expressions/fragments; có thể thiếu template hoặc null model property.

**3.** Thế nào là committed response?

**Đáp án:** Status/headers đã được gửi hoặc xác nhận gửi theo container HTTP response lifecycle; không thể thay đổi hữu hiệu thành response lỗi khác.

**4.** Ghi vài bytes vào response luôn có nghĩa committed chưa?

**Đáp án:** Chưa chắc. Bytes có thể đang nằm trong servlet buffer. `flushBuffer`, buffer overflow hoặc flush có thể commit.

**5.** Khi exception xảy ra sau commit, @ExceptionHandler có tạo 500 được không?

**Đáp án:** Không thể thay HTTP status đã gửi. Nó có thể log/cleanup nhưng không rewrite response client đã nhận.

**6.** `Cannot call sendError() after the response has been committed` có chắc là root cause không?

**Đáp án:** Không. Thường là lỗi thứ cấp do error handler cố đổi response; phải tìm Jackson/template/stream/client abort exception trước đó.

**7.** Vì sao HTTP 200 vẫn có thể là failure?

**Đáp án:** Body có thể bị cắt sau headers, thiếu terminal marker hoặc không parse được; server có thể đã logged exception nhưng status trên wire không đổi.

**8.** `HttpMessageNotReadableException` thường thuộc hướng nào?

**Đáp án:** Deserialize **request body vào**; malformed JSON thường là 400, khác `HttpMessageNotWritableException` khi serialize output.

**9.** `TemplateInputException` thường liên quan đến gì?

**Đáp án:** Không tìm được/đọc được template hoặc parsing input; kiểm tra file classpath, case, resolver và package jar.

**10.** `LazyInitializationException` xuất hiện ở serialization thì nên sửa thế nào?

**Đáp án:** Thiết kế DTO/projection, fetch data đúng transaction và quan hệ; không trả entity/proxy trực tiếp để Jackson tự traverse.

**11.** Tại sao endpoint `serialize-prechecked` trong demo có thể trả 500 ổn định?

**Đáp án:** ObjectMapper serialization thực hiện **trước khi** HTTP writer nhận body; controller catch exception và trả ResponseEntity chứa byte[] lỗi nhỏ với status 500.

**12.** Có nên pre-serialize mọi response 100 MiB để tránh hậu commit không?

**Đáp án:** Không. Memory/copy/GC có thể tăng mạnh. Dùng bounded payloads hoặc streaming protocol có completion semantics.

**13.** Khi một Flux đã emit NDJSON items rồi `onError`, HTTP status có thể đổi thành 500 không?

**Đáp án:** Không nếu response đã commit. Client nên dựa vào error/complete frames và phát hiện disconnect.

**14.** Dùng `@RestController` return `"profile"` có tự render `profile.html` không?

**Đáp án:** Không, thường trả literal body `profile`. Dùng `@Controller` để resolve view.

**15.** MockMvc kiểm tra response committed có đủ thay real socket test không?

**Đáp án:** Không. Mock response buffer/flush khác container/proxy behavior. Cần real HTTP tests khi điều tra after-commit.

**16.** Vì sao 500 metrics có thể bỏ sót streaming errors?

**Đáp án:** Request đã gửi status 200 trước khi failure, nên status metrics không thể retroactively thành 500. Phải instrument application-level stream outcomes.

**17.** Nếu browser mất response sau POST thành công ở DB, retry có an toàn không?

**Đáp án:** Không chắc. Dùng idempotency key/operation status để tránh duplicate side effects.

**18.** Vì sao không bật `server.error.include-stacktrace=always` trên production?

**Đáp án:** Stacktrace có thể lộ class names, file paths, internal data hoặc secrets. Ghi server logs có quyền kiểm soát và trả body lỗi an toàn.

**19.** Khi nâng Boot 2 lên Boot 3, import servlet nào cần xem lại?

**Đáp án:** Chuyển từ `javax.servlet.*` sang `jakarta.servlet.*` và đồng bộ dependency/runtime servlet API.

**20.** Bước đầu tiên khi thấy "cannot sendError after committed" là gì?

**Đáp án:** Tìm **exception gốc** và nơi response đã bị flush/commit, kiểm tra stage serializer/template/stream, chứ không tăng timeout hoặc cố gọi sendError lần nữa.

### Bài tập thực hành

1. Chạy `/api/serialize-error`, tìm stacktrace nêu chính xác getter `getSecond`.
2. Chạy `/api/serialize-prechecked`, đối chiếu status 500/body JSON rõ ràng với endpoint trực tiếp.
3. Chạy `/api/committed-error` và so server log `DEMO_AFTER_COMMIT=true` với HTTP client status/body.
4. Chạy `/api/stream-error` qua `curl -v -N`, ghi response bytes và transfer error; đừng giả định một status cố định.
5. Tạo `templates/missing.html` rồi thử lại `/page/missing` để hiểu template resolution.
6. Sửa `broken.html`: truyền `user` và nested profile hợp lệ qua model hoặc dùng safe fallback.
7. Thêm DTO có bidirectional references, viết ObjectMapper unit test phát hiện cycles; sửa bằng API projection.
8. Thêm một DTO chứa `LocalDateTime`, dùng Boot-injected mapper, so sánh với mapper không có JavaTimeModule trong test có kiểm soát.
9. Thử HTTP compression/proxy buffering, xem khi upstream error đã commit client thấy status/body/connection ra sao.
10. Thiết kế NDJSON với `type=item`, `type=error` và `type=complete`; test client phát hiện thiếu complete marker.
11. Thêm Micrometer counter riêng cho serialization failures và after-commit failures (tags bounded, không dùng raw URL).
12. Build executable jar và kiểm tra `BOOT-INF/classes/templates/` để phát hiện missing template trước container deploy.
13. Chạy `dependencyInsight` nếu một phiên bản Jackson/module bị override, đưa dependencies về BOM-managed versions.
14. Thử một lỗi client disconnect khi streaming; phân biệt broken pipe do client abort với lỗi business nội bộ.

## 25. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Spring MVC @ResponseBody và HttpMessageConverter](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/responsebody.html)
- [Spring Framework 6.2 — Exception Resolvers, Servlet Error Dispatch](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/exceptionhandlers.html)
- [Spring Framework 6.2 — Asynchronous Requests, StreamingResponseBody/SseEmitter](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html)
- [Spring Framework 6.2 — Web MVC Error Responses, ProblemDetail](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework 6.2 — WebFlux Reactive Core and Codecs](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — ServerHttpResponse API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html)
- [Spring Boot 3.5 — Servlet Web Applications, Error Handling and Template Engines](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot 3.5 — Common Application Properties: server.error, spring.thymeleaf](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Thymeleaf 3.1 — Using Thymeleaf](https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html)
- [Jackson — ObjectMapper, JsonMappingException](https://github.com/FasterXML/jackson-databind)
- [Jakarta Servlet — ServletResponse.isCommitted / flushBuffer](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/servletresponse)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)

**Kết luận:** Một **HTTP 500** có thể xuất hiện ở giai đoạn **sau controller**, khi Jackson tuần tự hóa body hoặc Thymeleaf render template. Điều quan trọng nhất là ranh giới **response chưa commit vs đã commit**. Trước commit, error handler có thể trả 500/ProblemDetail; **sau commit, status/headers không thể viết lại**, nên client có thể thấy **200 với body thiếu** hoặc connection error. Cách sửa đúng là **xử lý DTO/template và serialization root cause, tránh flush quá sớm, thiết kế streaming protocol có completion signal, kiểm thử bằng HTTP client thật và đo failures sau commit riêng với 5xx**.
