# @RequestBody, HttpEntity và đọc nội dung yêu cầu trong Spring MVC

## 1. Mục tiêu và phạm vi

Sau bài này, bạn có thể đọc và giải thích body của một HTTP request trong Spring MVC, chọn đúng giữa `@RequestBody` và `HttpEntity<T>`, hiểu vai trò của `HttpMessageConverter`, kiểm soát `Content-Type` và validation, đồng thời biết khi nào cần đọc trực tiếp `HttpServletRequest`. Bài tập trung vào **Spring MVC chạy trên Servlet stack**; các cơ chế reactive của Spring WebFlux có API xử lý body khác.

Một request HTTP có ba phần thường gặp:

```http
POST /api/orders HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json
X-Trace-Id: trace-42

{"sku":"JAVA-17","quantity":2}
```

- **Request line** xác định phương thức và URL.
- **Headers** cung cấp siêu dữ liệu. `Content-Type` mô tả **định dạng body gửi lên**; `Accept` mô tả **định dạng response client mong muốn**.
- **Body** là dữ liệu sau dòng trống ngăn headers và body. Trong ví dụ trên, body là JSON; giá trị `sku` và `quantity` nằm trong body, không phải query string.

`@RequestBody` giải mã body thành tham số Java. `HttpEntity<T>` gom body đã giải mã và headers vào một đối tượng. Cả hai thường dựa trên hệ thống HTTP message converters của Spring MVC.

## 2. Cơ chế Spring MVC đọc body

Với controller sau:

```java
@PostMapping("/orders")
public void create(@RequestBody OrderRequest request) {
    // request đã được đọc và chuyển đổi trước khi method được gọi
}
```

Luồng xử lý về nguyên tắc:

```text
Client gửi bytes + HTTP headers
  -> Servlet container tạo HttpServletRequest
  -> DispatcherServlet chọn controller/method theo route
  -> HandlerAdapter / argument resolver xử lý tham số
  -> Chọn HttpMessageConverter phù hợp kiểu Java và media type
  -> Converter đọc body, ví dụ JSON -> OrderRequest
  -> (Nếu có @Valid) kiểm tra ràng buộc
  -> Gọi controller method với đối tượng Java
  -> Chuyển đổi response body bằng converter thích hợp
```

`HttpMessageConverter` là giao diện đọc/ghi nội dung HTTP theo kiểu dữ liệu và media type. Các lựa chọn thông dụng:

| Đầu vào HTTP | Kiểu tham số | Cách đọc thường gặp |
| --- | --- | --- |
| `application/json` | DTO/record Java | Jackson JSON converter khi có thư viện phù hợp |
| `text/plain` | `String` | String converter |
| `application/octet-stream` | `byte[]` | Byte-array converter |
| JSON array | `List<MyDto>` | JSON converter dựa vào generic type |

Spring chỉ chuyển đổi được khi có converter hỗ trợ cả kiểu dữ liệu đích lẫn media type. `Content-Type: application/json` **không tự biến JSON thành object** nếu ứng dụng không có converter JSON thích hợp. Trong ứng dụng Spring Boot Web thông thường, starter Web cung cấp cấu hình JSON phổ biến; Spring Framework thuần cần tự đảm bảo các phụ thuộc và cấu hình tương ứng.

Lưu ý rằng `HttpMessageConverter` và Jackson xử lý ánh xạ dữ liệu; validation là **bước riêng** sau khi tạo object. Một JSON parse được vẫn có thể vi phạm `@NotBlank` hoặc `@Min`.

## 3. Dùng @RequestBody

```java
@PostMapping(path = "/orders", consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody OrderRequest request) {
    // ...
}
```

Những điểm cần nắm:

- `@RequestBody` đánh dấu **toàn bộ body** cần được ánh xạ vào tham số. Nó không hoạt động như `@RequestParam` (query/form parameter) hay `@PathVariable` (đoạn đường dẫn).
- Với DTO/record, JSON field thường được ánh xạ theo tên thành property hoặc constructor/record component tương ứng. Kiểu dữ liệu không hợp lệ hoặc JSON lỗi cú pháp có thể gây `HttpMessageNotReadableException` và response `400 Bad Request` theo cấu hình mặc định.
- Thuộc tính `required` mặc định là `true`. Nếu body bắt buộc mà request không cung cấp body hợp lệ, Spring thông thường trả `400` trước khi gọi controller. `@RequestBody(required = false)` cho phép không có body, do đó method phải xử lý trường hợp giá trị `null`. Đừng dùng chế độ tùy chọn để vô tình bỏ qua dữ liệu bắt buộc về nghiệp vụ.
- `@Valid` từ `jakarta.validation.Valid` kích hoạt Bean Validation cho object phù hợp khi provider validation hiện diện. Với kiểu tham số DTO thông thường, lỗi ràng buộc thường gây `MethodArgumentNotValidException` và `400`; trong một số chữ ký có method validation, `HandlerMethodValidationException` có thể được dùng thay thế.
- `consumes = "application/json"` ràng buộc định dạng request ở bước chọn handler. Gửi `text/plain` đến endpoint chỉ nhận JSON thường dẫn đến `415 Unsupported Media Type`. `produces` mô tả response media type; client gửi `Accept` không được hỗ trợ có thể nhận `406 Not Acceptable`.
- Trong mã ứng dụng thực, ưu tiên request DTO được thiết kế riêng. Không bind trực tiếp JSON không tin cậy vào entity persistence có trường mà client không được phép điều khiển.

### Một body, nhiều cách biểu diễn

```java
@PostMapping(path = "/payload/text", consumes = MediaType.TEXT_PLAIN_VALUE)
public String text(@RequestBody String body) {
    return "length=" + body.length();
}

@PostMapping(path = "/payload/binary",
             consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
public int binary(@RequestBody byte[] body) {
    return body.length;
}
```

Đây là **hai method minh họa** để đặt trong một `@RestController` có mapping phù hợp, chưa phải chương trình Java độc lập. `String` là văn bản đã giải mã bằng charset do converter áp dụng; `byte[]` phù hợp khi cần byte gốc. `String.length()` đếm đơn vị mã UTF-16, không đếm số byte hay luôn bằng số ký tự người dùng nhìn thấy.

## 4. HttpEntity<T>: body kèm headers

`HttpEntity<T>` là đối tượng chứa **request body** kiểu `T` và `HttpHeaders`. Ví dụ:

```java
@PostMapping(path = "/orders/entity",
             consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<String> inspect(HttpEntity<OrderRequest> entity) {
    OrderRequest body = entity.getBody();
    String traceId = entity.getHeaders().getFirst("X-Trace-Id");
    // Xử lý body và header...
    return ResponseEntity.ok(traceId == null ? "missing" : traceId);
}
```

Trong Spring MVC, `HttpEntity<OrderRequest>` ở tham số controller được framework resolve và đọc body thông qua message converters, tương tự `@RequestBody OrderRequest`, đồng thời giữ headers. Không cần đặt thêm `@RequestBody` lên cùng tham số `HttpEntity<T>`. `getBody()` có thể là `null` khi request không có body; kiểm tra trước khi truy cập. Nếu cần xác thực dữ liệu, đừng giả định Bean Validation được thực hiện chỉ vì body nằm trong `HttpEntity`: hãy thiết kế luồng validation tường minh, hoặc dùng `@Valid @RequestBody` khi phù hợp.

| Nhu cầu | Tham số nên chọn |
| --- | --- |
| Nhận JSON thành DTO, có `@Valid` | `@Valid @RequestBody MyDto body` |
| Nhận DTO và đọc nhiều request headers như một gói | `HttpEntity<MyDto> entity` |
| Chỉ lấy một header | `@RequestHeader("X-Trace-Id") String traceId` cùng `@RequestBody` |
| Cần điều khiển trực tiếp Servlet body stream | `HttpServletRequest` và `getInputStream()` |
| Nhận form fields kiểu `application/x-www-form-urlencoded` | Thường dùng `@RequestParam` hoặc `@ModelAttribute` |

**Đừng nhầm `HttpEntity<T>` với `ResponseEntity<T>`:** `HttpEntity` mô hình hóa body + headers; `ResponseEntity` kế thừa ý tưởng đó và thêm HTTP status cho **response**. Controller có thể nhận `HttpEntity<RequestDto>` và trả `ResponseEntity<ResponseDto>`.

## 5. Ví dụ đầy đủ, chạy được: Spring MVC + Java 17

Ví dụ sử dụng **Spring Boot 3.3.5 (Spring Framework 6.x)** và Java 17 để có một ứng dụng MVC nhỏ. Spring Boot chỉ giúp bootstrap, tự cấu hình Jackson và validation; API controller là của Spring MVC. Dùng Maven và cấu trúc:

```text
web-body-demo/
├── pom.xml
└── src/main/java/demo/webbody/
    ├── WebBodyApplication.java
    └── OrderController.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>web-body-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/webbody/WebBodyApplication.java`**

```java
package demo.webbody;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebBodyApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebBodyApplication.class, args);
    }
}
```

**`src/main/java/demo/webbody/OrderController.java`**

```java
package demo.webbody;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    public record OrderRequest(@NotBlank String sku,
                               @Min(1) int quantity) {}

    public record OrderResponse(long id, String sku, int quantity) {}

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody OrderRequest request) {
        OrderResponse result =
                new OrderResponse(7L, request.sku(), request.quantity());
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

    @PostMapping(path = "/entity",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> inspect(HttpEntity<OrderRequest> entity) {
        OrderRequest request = entity.getBody();
        if (request == null) {
            return ResponseEntity.badRequest().build();
        }
        String traceId = entity.getHeaders().getFirst("X-Trace-Id");
        String value = traceId == null ? "missing" : traceId;
        return ResponseEntity.ok("sku=" + request.sku() + ", trace=" + value);
    }

    @PostMapping(path = "/raw",
                 consumes = MediaType.TEXT_PLAIN_VALUE,
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public String raw(@RequestBody String body) {
        return "length=" + body.length();
    }

    @PostMapping(path = "/bytes",
                 consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Integer> bytes(@RequestBody byte[] body) {
        return Map.of("bytes", body.length);
    }
}
```

Hai `record` được khai báo lồng trong `OrderController`, nhưng vẫn là kiểu Java có thể được Jackson ánh xạ. Dùng `@NotBlank` cho SKU và `@Min(1)` cho số lượng. `id = 7` là giá trị minh họa cố định, không có cơ sở dữ liệu hoặc tạo đơn hàng thực. Endpoint `/entity` chỉ minh họa truy cập headers/body; nó **không có `@Valid`**, vì vậy ví dụ không hứa validation tương tự endpoint `create`.

Chạy từ thư mục có `pom.xml`:

```bash
mvn spring-boot:run
```

Khi ứng dụng đã mở cổng mặc định `8080`, gọi thử trong Bash (Linux/macOS/Git Bash):

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"sku":"JAVA-17","quantity":2}'
```

Kết quả chính (bỏ các HTTP headers thay đổi theo môi trường):

```http
HTTP/1.1 201
Content-Type: application/json

{"id":7,"sku":"JAVA-17","quantity":2}
```

Thử `HttpEntity` với request header riêng:

```bash
curl -i -X POST http://localhost:8080/api/orders/entity \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/plain' \
  -H 'X-Trace-Id: trace-42' \
  -d '{"sku":"SPRING","quantity":1}'
```

Response body:

```text
sku=SPRING, trace=trace-42
```

Thử nhận văn bản và bytes:

```bash
curl -s -X POST http://localhost:8080/api/orders/raw \
  -H 'Content-Type: text/plain' --data-binary 'hello'
curl -s -X POST http://localhost:8080/api/orders/bytes \
  -H 'Content-Type: application/octet-stream' --data-binary 'ABC'
```

Lần lượt nhận:

```text
length=5
{"bytes":3}
```

Trên PowerShell, có thể gửi JSON bằng lệnh một dòng:

```powershell
Invoke-RestMethod -Method Post -Uri 'http://localhost:8080/api/orders' -ContentType 'application/json' -Body '{"sku":"JAVA-17","quantity":2}'
```

Các số liệu trên cố định do dữ liệu và cách xử lý của ví dụ; header như `Date`, `Transfer-Encoding` và định dạng thân lỗi mặc định có thể khác nhau tùy cấu hình.

## 6. Nếu cần đọc trực tiếp HttpServletRequest

Trong Servlet MVC, `HttpServletRequest.getInputStream()` cung cấp stream bytes của body; `getReader()` cung cấp cách đọc ký tự. Đọc trực tiếp hữu ích khi xử lý định dạng tùy biến, kiểm tra chữ ký trên **raw bytes**, hoặc có yêu cầu đặc biệt với stream. Ví dụ **method thay thế** có thể thêm vào controller; đây là đoạn mã minh họa, cần imports `jakarta.servlet.http.HttpServletRequest`, `java.io.IOException` và `java.io.InputStream`:

```java
@PostMapping(path = "/stream",
             consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
public ResponseEntity<String> readStream(
        HttpServletRequest request) throws IOException {
    try (InputStream input = request.getInputStream()) {
        byte[] data = input.readAllBytes();
        return ResponseEntity.ok("bytes=" + data.length);
    }
}
```

**Chú ý:** `readAllBytes()` nạp toàn bộ dữ liệu vào RAM, chỉ hợp lý khi đã giới hạn kích thước request. Body thông thường là stream được tiêu thụ một lần; không nên đồng thời đọc bằng `@RequestBody` và tự gọi `getInputStream()` cho cùng dữ liệu. Filter/interceptor đã đọc stream trước đó cũng có thể làm controller thấy body rỗng. `ContentCachingRequestWrapper` chỉ cache dữ liệu **đã được đọc**, không tự động làm body trở thành stream có thể đọc lại vô hạn. Với tải lên tệp lớn, hãy cân nhắc giải pháp upload/streaming phù hợp, tránh biến mọi nội dung thành một `byte[]` lớn.

Khi đọc JSON thông thường, `@RequestBody` tốt hơn vì giải quyết chuyện ánh xạ và lỗi định dạng; chỉ xuống mức Servlet API khi cần kiểm soát bytes thật sự.

## 7. Phân biệt JSON body, query, form và multipart

Đây là các nguồn dữ liệu khác nhau:

| Request gửi lên | Spring MVC thường dùng | Ví dụ |
| --- | --- | --- |
| `/orders?limit=10` | `@RequestParam int limit` | Query parameter |
| `/orders/123` | `@PathVariable long id` | Path segment |
| `Content-Type: application/json` | `@RequestBody OrderRequest dto` | JSON body |
| `Content-Type: application/x-www-form-urlencoded` | `@RequestParam` hoặc `@ModelAttribute` | Form fields |
| `Content-Type: multipart/form-data` | `@RequestPart`, `MultipartFile` hoặc form binding | Multipart parts |

Theo lưu ý của Spring MVC, request form `application/x-www-form-urlencoded` nên xử lý dưới dạng tham số/form binding; Servlet API có thể parse body khi truy cập request parameters, khiến việc đọc body thêm lần nữa thiếu tin cậy. `@RequestPart` hữu ích khi một phần multipart chứa JSON và cần converter riêng cho phần đó.

`@RequestBody` thường dùng cho POST, PUT, PATCH có body; HTTP không buộc annotation này chỉ thuộc ba phương thức đó, nhưng thiết kế API cần tôn trọng ngữ nghĩa của từng method.

## 8. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/xử lý |
| --- | --- | --- |
| `400 Bad Request`, controller chưa chạy | JSON sai, body bắt buộc bị thiếu, không ánh xạ được kiểu, hoặc validation thất bại | Kiểm tra raw body, DTO/record, exception thực tế và constraint |
| `415 Unsupported Media Type` | `Content-Type` không phù hợp `consumes` hoặc converter | Gửi đúng media type, đăng ký converter nếu cần |
| `406 Not Acceptable` | `Accept` không phù hợp response có thể tạo | Kiểm tra `produces` và response converter |
| Field là `null` hoặc giá trị mặc định | JSON thiếu field, tên property không khớp, hoặc primitive có giá trị mặc định | Kiểm tra JSON và thêm ràng buộc đúng mục tiêu |
| `@Valid` không có tác dụng | Thiếu Bean Validation provider/starter hoặc validation không áp dụng ở luồng này | Bổ sung dependency và đặt validation đúng trên DTO |
| Body rỗng dù client đã gửi | Stream bị filter/handler khác đọc trước | Rà soát các thành phần can thiệp request |
| Dữ liệu nhị phân bị hỏng | Đọc bytes bằng `String` và mã hóa/giải mã sai charset | Dùng `byte[]` hoặc stream cho dữ liệu binary |

Khi `@Valid @RequestBody` thông thường thất bại, Spring trả `400` theo handler mặc định, nhưng **JSON body của response lỗi không có một dạng duy nhất** giữa mọi phiên bản/cấu hình. Để chuẩn hóa lỗi, ứng dụng có thể dùng `@RestControllerAdvice` / `@ExceptionHandler` hoặc `ResponseEntityExceptionHandler`. Đừng bắt mọi exception và trả `200 OK` vì khiến client không biết request thất bại.

Ngoài ra, cần giới hạn kích thước body ở tầng phù hợp, không ghi log payload nhạy cảm, tránh tin rằng kiểu Java và annotation validation có thể thay thế quy tắc nghiệp vụ hoặc phân quyền.

## 9. Câu hỏi tự kiểm tra

1. Client gửi `Content-Type: text/plain` đến method chỉ định `consumes = "application/json"`. Vì sao method thường không được gọi?
2. Khi nào chọn `HttpEntity<OrderRequest>` thay cho `@RequestBody OrderRequest`? Nếu chỉ cần một header thì còn cách nào ngắn hơn?
3. `@Valid`, Jackson và `HttpMessageConverter` đảm nhiệm ba vai trò khác nhau như thế nào?
4. Vì sao không nên vừa có `@RequestBody String body` vừa tự đọc `request.getInputStream()` của cùng request?
5. Khi nào dùng `@RequestParam`, `@ModelAttribute` hoặc `@RequestPart` thay cho `@RequestBody`?

**Gợi ý đáp án:** (1) Media type không hợp mapping/converter, thường `415`. (2) `HttpEntity` khi cần body kèm headers; chỉ một header có thể thêm `@RequestHeader`. (3) Converter đọc bytes và deserialize, Jackson thực hiện JSON mapping, Bean Validation kiểm tra constraints sau đó. (4) Body stream có thể đã bị tiêu thụ. (5) Query/form/multipart tương ứng với cơ chế binding khác nhau.

## 10. Tài liệu tham khảo chính thức

- [Spring MVC — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring MVC — HttpEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/httpentity.html)
- [Spring MVC — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)

Các đường dẫn trên trỏ đến tài liệu Spring Framework hiện hành; ví dụ runnable đã cố định Spring Boot 3.3.5 để lệnh Maven có môi trường xác định.