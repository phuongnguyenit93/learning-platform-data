# HandlerExceptionResolver và luồng xử lý khi có ngoại lệ trong Spring MVC

## 1. Mục tiêu và vị trí của cơ chế xử lý lỗi

Trong Spring Web MVC, một request hợp lệ có thể thất bại ở nhiều giai đoạn: tìm handler, chuyển tham số, đọc JSON, validation, gọi service, thực thi controller, ghi phản hồi hoặc kết xuất view. **HandlerExceptionResolver** là điểm mở rộng của Spring MVC để biến những ngoại lệ được `DispatcherServlet` bắt được thành một kết quả xử lý HTTP có ý nghĩa.

Bài này trả lời các câu hỏi:

- Ngoại lệ đi qua những bước nào trước khi tới `HandlerExceptionResolver`?
- Khi nào `@ExceptionHandler` trong controller được gọi, khi nào `@ControllerAdvice` được gọi?
- `ExceptionHandlerExceptionResolver`, `ResponseStatusExceptionResolver`, `DefaultHandlerExceptionResolver` khác nhau thế nào?
- Kết quả trả về `null`, `ModelAndView` rỗng hoặc có view mang ý nghĩa gì?
- Làm sao tạo lỗi REST API thống nhất bằng `ResponseEntity`/`ProblemDetail` và kiểm thử đúng HTTP status, body?
- Những ngoại lệ nào **không** đi qua chuỗi resolver MVC, hoặc xảy ra khi phản hồi HTTP đã được gửi?

**Phạm vi:** Spring Framework 6.x/Spring Boot 3.x, Java 17+, web stack Spring MVC (Servlet). WebFlux là stack khác, sử dụng `WebExceptionHandler` và các cơ chế xử lý lỗi reactive tương ứng.

## 2. Nơi phát sinh ngoại lệ trong luồng MVC

Hình dưới mô tả trường hợp lỗi xảy ra **trong phạm vi request mà `DispatcherServlet` đang xử lý**:

```text
HTTP client
   |
   v
Servlet container (Tomcat)
   |
   v
Servlet Filter chain
   |
   v
DispatcherServlet
   |
   +--> HandlerMapping        --- lỗi tìm handler/mapping?
   |
   +--> HandlerAdapter
   |      |
   |      +--> argument resolver / binding / validation --- lỗi 400?
   |      |
   |      +--> @Controller -> service/repository -------- lỗi nghiệp vụ?
   |      |
   |      +--> return value / message converter --------- lỗi serialize?
   |
   +-- ngoại lệ được DispatcherServlet bắt trong vùng xử lý
          |
          v
   Danh sách HandlerExceptionResolver (theo order)
          |
          +--> resolver 1: xử lý được? -> response/view
          +--> resolver 2: xử lý được? -> response/view
          +--> resolver 3: xử lý được? -> response/view
          |
          +--> không resolver nào xử lý -> exception thoát ra
                    |
                    v
            Servlet container / error dispatch
```

Khi phần xử lý trong `DispatcherServlet` ném lỗi, Servlet sẽ thử các `HandlerExceptionResolver` đã được đăng ký. Resolver có thể đặt HTTP status, header, body, trả về view lỗi hoặc cho resolver tiếp theo thử.

**Không phải mọi ngoại lệ trong toàn tiến trình đều đi vào đây.** Ví dụ filter nằm trước `DispatcherServlet` ném lỗi khi chưa gọi servlet, lỗi xảy ra trong lúc ứng dụng startup, hay lỗi nền ở scheduler/`@Async` bên ngoài request MVC sẽ cần cơ chế khác. Đây là ranh giới đầu tiên để chẩn đoán chính xác.

## 3. Hợp đồng của HandlerExceptionResolver

Interface quan trọng nằm tại `org.springframework.web.servlet.HandlerExceptionResolver`. Phương thức cốt lõi có dạng:

```java
ModelAndView resolveException(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        Exception ex
);
```

Đây là **chữ ký minh họa từ API**, không phải một chương trình Java độc lập. `handler` có thể là thông tin handler mà framework xác định được; không nên mặc định nó luôn là một phương thức controller đã tìm thấy.

Giá trị trả về có ba ý nghĩa rõ ràng:

| Trả về | Ý nghĩa |
| --- | --- |
| `null` | Resolver này **chưa giải quyết ngoại lệ**; `DispatcherServlet` thử resolver tiếp theo. |
| `new ModelAndView()` rỗng | Ngoại lệ **đã được xử lý**, nhưng không cần render một view MVC; ví dụ resolver đã thiết lập status/body trực tiếp. |
| `ModelAndView` chứa view và model | Ngoại lệ **đã được xử lý** bằng cách render view lỗi, phổ biến trong MVC trả HTML. |

**Lỗi tư duy phổ biến:** `null` không nghĩa là “trả response rỗng”; nó nghĩa là *để resolver khác thử*. Ngược lại, một `ModelAndView` rỗng không yêu cầu framework tiếp tục dò resolver.

Chuỗi resolver có thứ tự (`Ordered`/`@Order` hoặc cấu hình MVC). **Resolver đầu tiên trả kết quả khác `null` sẽ quyết định hướng xử lý**. Vì thế việc viết một custom resolver bắt mọi `Exception` ở ưu tiên quá cao có thể vô tình cướp quyền xử lý của `@ExceptionHandler` và các resolver mặc định.

## 4. Ba resolver tích hợp quan trọng nhất

Khi dùng cấu hình MVC tiêu chuẩn, Spring đăng ký các resolver mặc định; cấu hình thực tế có thể đặt chúng trong `HandlerExceptionResolverComposite`, với thứ tự thông dụng như sau:

| Resolver | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **`ExceptionHandlerExceptionResolver`** | Tìm và gọi phương thức `@ExceptionHandler` trong controller hoặc controller advice | Chuyển `ProductNotFoundException` thành JSON lỗi 404. |
| **`ResponseStatusExceptionResolver`** | Ánh xạ `@ResponseStatus` và `ResponseStatusException` sang HTTP status / lý do | Một exception được gắn `@ResponseStatus(HttpStatus.NOT_FOUND)`. |
| **`DefaultHandlerExceptionResolver`** | Xử lý ngoại lệ chuẩn do Spring MVC phát sinh và ánh xạ HTTP status/header theo Servlet behavior | Sai HTTP method (405), thiếu tham số, lỗi đọc dữ liệu, v.v. |

Ngoài ra, `SimpleMappingExceptionResolver` có thể ánh xạ loại exception sang tên view lỗi để render HTML trong ứng dụng MVC truyền thống; nó không mặc nhiên là thành phần thích hợp nhất cho REST JSON API.

**Thứ tự này không có nghĩa “mọi exception đều lần lượt được ba lớp xử lý”.** Nếu resolver đầu tiên đã xử lý, các resolver còn lại không được hỏi. Nếu một ứng dụng định nghĩa resolver hoặc tùy biến cấu hình MVC, thứ tự cụ thể cần xem lúc runtime.

### 4.1. ExceptionHandlerExceptionResolver

Đây là bộ máy đằng sau `@ExceptionHandler`. Nó tìm method xử lý phù hợp theo loại ngoại lệ, khai báo controller cục bộ, các advice áp dụng được, và thứ tự advice. Method có thể trả `ResponseEntity`, `ProblemDetail`, body object, `ModelAndView`, tên view và các kiểu trả về MVC hợp lệ khác.

Nó là lựa chọn phổ biến khi cần biến **lỗi nghiệp vụ** thành HTTP contract ổn định: status, error code, message an toàn, correlation ID và những header hợp lý.

### 4.2. ResponseStatusExceptionResolver

Resolver này diễn giải các trường hợp như:

```java
@ResponseStatus(HttpStatus.NOT_FOUND)
class BookNotFoundException extends RuntimeException {
}
```

Hoặc ném `ResponseStatusException` tại một điểm xử lý:

```java
throw new ResponseStatusException(
        HttpStatus.NOT_FOUND,
        "Không tìm thấy sách"
);
```

Hai đoạn là **mã minh họa đặt trong ứng dụng đã import Spring HTTP/web classes**. Chúng làm rõ ý định status HTTP nhanh chóng, nhưng không tự bảo đảm một JSON error body thống nhất trong mọi cấu hình/container.

Nếu một `@ExceptionHandler` phù hợp đã bắt ngoại lệ trước, phương thức xử lý đó có thể quyết định response thay cho resolver status. Không giả định `@ResponseStatus` luôn có ưu tiên tuyệt đối.

### 4.3. DefaultHandlerExceptionResolver

Spring MVC phát sinh các ngoại lệ đặc thù cho protocol/mapping, ví dụ:

- `HttpRequestMethodNotSupportedException` khi HTTP method không được hỗ trợ; thường là **405 Method Not Allowed**, có thể kèm header `Allow`.
- `HttpMediaTypeNotSupportedException` khi request gửi `Content-Type` không phù hợp; thường **415 Unsupported Media Type**.
- `HttpMediaTypeNotAcceptableException` khi không thể tạo representation đúng `Accept`; thường **406 Not Acceptable**.
- `MissingServletRequestParameterException` nếu thiếu `@RequestParam(required=true)`; thường **400 Bad Request**.
- `MethodArgumentTypeMismatchException` hoặc các lỗi chuyển đổi type liên quan; thường dẫn tới **400**, nhưng body cụ thể do handler/advice/config quyết định.
- `HttpMessageNotReadableException` khi JSON không parse được; thường **400 Bad Request**.

Nhiều lỗi framework còn có đường đi qua `ResponseEntityExceptionHandler` hoặc `ErrorResponse` để tạo nội dung HTTP chi tiết. Tại runtime, resolver nào được ưu tiên có thể thay đổi response body, nhưng **HTTP status đúng chưa đồng nghĩa JSON body chuẩn hóa**. Có trường hợp resolver chỉ đặt status hay gọi `sendError`, rồi container/Boot điều hướng tới `/error`.

## 5. @ExceptionHandler trong controller: phạm vi cục bộ

Một controller có thể khai báo `@ExceptionHandler` để xử lý ngoại lệ của chính nó:

```java
@RestController
@RequestMapping("/api/invoices")
class InvoiceController {

    @GetMapping("/{id}")
    String byId(@PathVariable long id) {
        if (id == 9) {
            throw new IllegalArgumentException("Mã hóa đơn không hợp lệ");
        }
        return "invoice-" + id;
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<String> onInvalid(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body(ex.getMessage());
    }
}
```

Đây là **đoạn code controller minh họa**; cần import `@RestController`, `@RequestMapping`, `@GetMapping`, `@PathVariable`, `@ExceptionHandler` và `ResponseEntity` từ Spring. Với `GET /api/invoices/9`, response body là thông báo lỗi và status 400.

Ưu điểm: quy tắc riêng rất gần controller. Nhược điểm: nếu lặp cùng error response ở nhiều controller, mã không nhất quán và khó bảo trì. Khi nhiều controller dùng cùng contract JSON lỗi, nên chuyển quy tắc chung sang `@RestControllerAdvice`.

### Ưu tiên local so với global

Khi cùng một ngoại lệ có handler phù hợp trong controller và trong `@ControllerAdvice` áp dụng cho controller đó, **handler cục bộ được ưu tiên**. Các advice áp dụng toàn cục chỉ được xét khi không có local handler phù hợp.

Trong một controller/advice, độ cụ thể của exception type và matching trên nguyên nhân (`cause`) ảnh hưởng việc chọn method. **Không** tạo hai `@ExceptionHandler` mơ hồ cho cùng exception trong một advice: Spring có thể báo ambiguity khi khởi tạo resolver.

## 6. @ControllerAdvice và @RestControllerAdvice

`@ControllerAdvice` là Spring component chứa logic áp dụng cho nhiều controller, trong đó có `@ExceptionHandler`. `@RestControllerAdvice` tương đương `@ControllerAdvice` kết hợp `@ResponseBody`: các object trả về thường được serialize vào HTTP body thay vì xem là tên view.

| Annotation/cách dùng | Phạm vi | Dạng phản hồi |
| --- | --- | --- |
| `@ExceptionHandler` trong `@Controller` | Controller hiện tại | View, body hoặc `ResponseEntity` theo signature. |
| `@ControllerAdvice` + `@ExceptionHandler` | Nhiều controller được chọn | Phù hợp HTML view hoặc response body khi có `@ResponseBody`/`ResponseEntity`. |
| `@RestControllerAdvice` + `@ExceptionHandler` | Nhiều REST controller được chọn | Trả object/JSON lỗi thuận tiện. |
| `ResponseEntityExceptionHandler` | Base class dùng trong advice | Đã xử lý nhóm exception Spring MVC; cung cấp hook override để thống nhất response. |

Có thể giới hạn advice bằng thuộc tính như `basePackages`, `basePackageClasses`, `annotations`, `assignableTypes`. Không nên tạo một advice chung bắt mọi exception rồi biến mọi lỗi thành 200 hoặc 400.

### Nhiều ControllerAdvice và thứ tự

Spring sắp xếp controller advice theo `Ordered`/`@Order`. Advice ưu tiên cao hơn được xét trước. Trong **cùng advice**, root exception match thường ưu tiên cause match; nhưng **cause match của advice có thứ tự ưu tiên cao** có thể thắng root match ở advice ưu tiên thấp hơn.

Ví dụ dễ hiểu:

- Advice A có `@Order(1)`, bắt `IllegalArgumentException` nằm trong cause chain.
- Advice B có `@Order(10)`, bắt exception ngoài cùng cụ thể hơn.
- Khi A áp dụng và tìm thấy handler phù hợp, A có thể được dùng trước B dù B bắt root exception.

Vì vậy hãy để mapping lỗi nghiệp vụ **cụ thể** trong một advice có phạm vi và order rõ ràng; tránh nhiều advice bắt `Exception.class` ở ưu tiên cao.

## 7. ProblemDetail: một HTTP error contract rõ ràng

Thay vì trả chuỗi lỗi tùy ý hoặc một `Map` với các key không ổn định, Spring Framework 6 hỗ trợ `ProblemDetail` theo chuẩn **RFC 9457** (Problem Details for HTTP APIs).

Một problem response có các trường tiêu chuẩn:

| Trường | Ý nghĩa |
| --- | --- |
| `type` | URI định danh loại vấn đề; mặc định có thể là `about:blank`. |
| `title` | Tiêu đề ngắn của loại vấn đề. |
| `status` | Mã HTTP status tương ứng. |
| `detail` | Giải thích ngắn về trường hợp cụ thể. |
| `instance` | URI định danh request/problem instance khi được cung cấp hoặc suy ra. |
| Extension như `code` | Mã lỗi riêng của hệ thống để client xử lý ổn định. |

Định dạng media type điển hình là `application/problem+json`. JSON có thể chứa thêm trường `instance` hoặc extension tùy cách controller/converter xây response. Client nên dựa vào **HTTP status + mã lỗi ổn định**, không parse từng câu chữ `detail`.

Ví dụ error response minh họa:

```json
{
  "type": "about:blank",
  "title": "Không tìm thấy sản phẩm",
  "status": 404,
  "detail": "Không tìm thấy sản phẩm 42",
  "code": "PRODUCT_NOT_FOUND"
}
```

**Không đưa stack trace, connection string, đường dẫn file hệ thống, SQL nội bộ hoặc dữ liệu riêng tư vào `detail` của lỗi 500.** Log nội bộ có thể giữ thông tin kỹ thuật với quyền truy cập thích hợp và gắn request/correlation ID.

## 8. Bài lab chạy được: Spring Boot + MVC + @RestControllerAdvice

Ta tạo một ứng dụng Spring Boot **3.5.16**, Java 17+, Maven. API có ba loại phản hồi dễ kiểm chứng:

- `GET /api/products/1`: thành công 200.
- `GET /api/products/42`: ném ngoại lệ nghiệp vụ, advice chuyển thành 404 với `ProblemDetail`.
- `GET /api/products/0`: ném `IllegalArgumentException`, advice trả 400.
- `GET /api/products/500`: mô phỏng lỗi nội bộ, advice trả 500 với thông tin công khai đã làm sạch.

Ngoài ra, `GET /api/products/search` khi thiếu tham số `term` tạo lỗi MVC `MissingServletRequestParameterException`; custom advice kế thừa `ResponseEntityExceptionHandler` có thể override hook tương ứng.

**Cấu trúc dự án**:

```text
mvc-exception-demo/
├── pom.xml
└── src/
    ├── main/java/example/errors/
    │   ├── ExceptionDemoApplication.java
    │   ├── ProductController.java
    │   ├── ProductNotFoundException.java
    │   └── ApiExceptionHandler.java
    └── test/java/example/errors/
        └── ExceptionFlowTest.java
```

### 8.1. Maven pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>mvc-exception-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Không cần thêm thư viện riêng để dùng `@ExceptionHandler` hoặc `ProblemDetail`: cả hai có trong Spring Web MVC đã được starter kéo vào.

### 8.2. Điểm khởi động

**`src/main/java/example/errors/ExceptionDemoApplication.java`**:

```java
package example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExceptionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExceptionDemoApplication.class, args);
    }
}
```

`@SpringBootApplication` bật auto-configuration và component scan trong package `example.errors`, vì vậy controller và advice bên dưới sẽ được tìm thấy.

### 8.3. Ngoại lệ miền nghiệp vụ

**`src/main/java/example/errors/ProductNotFoundException.java`**:

```java
package example.errors;

public class ProductNotFoundException extends RuntimeException {
    public ProductNotFoundException(long id) {
        super("Không tìm thấy sản phẩm " + id);
    }
}
```

Ngoại lệ này biểu diễn lỗi domain “không tìm thấy sản phẩm”; nó **không gắn cứng Servlet hay HTTP status**. Tầng API quyết định ánh xạ sang 404 bằng advice. Nhờ vậy domain không bắt buộc phụ thuộc `ResponseStatusException` của Spring Web.

### 8.4. Controller tạo các trường hợp có lỗi

**`src/main/java/example/errors/ProductController.java`**:

```java
package example.errors;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping("/{id}")
    public Map<String, Object> get(@PathVariable long id) {
        if (id == 42) {
            throw new ProductNotFoundException(id);
        }
        if (id <= 0) {
            throw new IllegalArgumentException("id phải lớn hơn 0");
        }
        if (id == 500) {
            throw new IllegalStateException("Chi tiết hệ thống nội bộ");
        }
        return Map.of("id", id, "name", "Notebook");
    }

    @GetMapping("/search")
    public Map<String, String> search(@RequestParam String term) {
        return Map.of("term", term);
    }
}
```

Khi gọi `/api/products/42`, method đã được mapping và gọi tới nhánh ném `ProductNotFoundException`. `DispatcherServlet` giao lỗi cho chuỗi resolver; `ExceptionHandlerExceptionResolver` có thể tìm `@ExceptionHandler(ProductNotFoundException.class)`.

Khi gọi `/api/products/search` thiếu `term`, exception nảy sinh ở **argument binding** trước khi method `search` thực thi. Nhưng vì lỗi vẫn thuộc xử lý MVC, nó có thể được xử lý qua `ResponseEntityExceptionHandler` trong advice.

### 8.5. Advice chứa error contract

**`src/main/java/example/errors/ApiExceptionHandler.java`**:

```java
package example.errors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiExceptionHandler extends ResponseEntityExceptionHandler {

    private static final Logger log =
            LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(ProductNotFoundException ex) {
        return problem(HttpStatus.NOT_FOUND, "Không tìm thấy sản phẩm",
                ex.getMessage(), "PRODUCT_NOT_FOUND");
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ProblemDetail> invalid(IllegalArgumentException ex) {
        return problem(HttpStatus.BAD_REQUEST, "Yêu cầu không hợp lệ",
                ex.getMessage(), "INVALID_PRODUCT_ID");
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<ProblemDetail> unexpected(IllegalStateException ex) {
        log.error("Xảy ra lỗi nội bộ khi xử lý sản phẩm", ex);
        return problem(HttpStatus.INTERNAL_SERVER_ERROR, "Lỗi máy chủ",
                "Không thể hoàn tất yêu cầu", "INTERNAL_ERROR");
    }

    @Override
    protected ResponseEntity<Object> handleMissingServletRequestParameter(
            MissingServletRequestParameterException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                status, "Thiếu tham số: " + ex.getParameterName());
        body.setTitle("Thiếu tham số bắt buộc");
        body.setProperty("code", "MISSING_PARAMETER");
        return handleExceptionInternal(ex, body, headers, status, request);
    }

    private ResponseEntity<ProblemDetail> problem(
            HttpStatus status, String title, String detail, String code) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(status, detail);
        body.setTitle(title);
        body.setProperty("code", code);
        return ResponseEntity.status(status).body(body);
    }
}
```

Giải thích:

- `@RestControllerAdvice` khiến các handler lỗi chung áp dụng cho controller phù hợp và phản hồi qua message converters.
- Handler `ProductNotFoundException` trả **404** và code ổn định `PRODUCT_NOT_FOUND`; `IllegalArgumentException` trả **400**.
- Handler `IllegalStateException` log stack trace nội bộ, nhưng trả thông điệp công khai đã làm sạch với **500**. Trong ứng dụng thực, loại exception này chỉ là mô phỏng, và không nên mặc định mọi `IllegalStateException` luôn là lỗi 500 nếu business domain có ngữ nghĩa khác.
- Vì advice **extends `ResponseEntityExceptionHandler`**, muốn sửa phản hồi cho `MissingServletRequestParameterException` ta **override** `handleMissingServletRequestParameter`. Không thêm một `@ExceptionHandler(MissingServletRequestParameterException.class)` riêng trong cùng advice: base class đã đăng ký nhóm exception đó, có thể gây mapping mơ hồ.
- `handleExceptionInternal` giúp giữ cơ chế xử lý response và header framework cho ngoại lệ MVC, thay vì bỏ qua các contract mặc định.
- Đoạn mẫu cố tình **không bật** auto-configuration `spring.mvc.problemdetails.enabled=true`; các endpoint trả `ProblemDetail` trực tiếp vẫn hoạt động. Nếu dùng setting đó, cần đánh giá thêm advice mặc định và thứ tự ưu tiên tương ứng.

Các handler cụ thể sẽ được Spring chọn theo exception type. Trong ví dụ không dùng catch-all `@ExceptionHandler(Exception.class)`, vì catch-all quá rộng dễ che lấp lỗi protocol do framework đã hỗ trợ.

### 8.6. Chạy và quan sát

Từ thư mục chứa `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Giữ ứng dụng chạy ở terminal thứ nhất. Trên terminal thứ hai:

```bash
# 200: sản phẩm hợp lệ
curl -i http://localhost:8080/api/products/1

# 404: sản phẩm không tồn tại
curl -i -H "Accept: application/problem+json" \
  http://localhost:8080/api/products/42

# 400: id không hợp lệ
curl -i -H "Accept: application/problem+json" \
  http://localhost:8080/api/products/0

# 500: lỗi mô phỏng và body công khai đã làm sạch
curl -i -H "Accept: application/problem+json" \
  http://localhost:8080/api/products/500

# 400: thiếu @RequestParam term (framework binding error)
curl -i -H "Accept: application/problem+json" \
  http://localhost:8080/api/products/search
```

Dấu `\` để nối lệnh dùng shell kiểu Bash; trong Windows PowerShell có thể viết mỗi `curl.exe` trên một dòng đầy đủ.

Bảng kết quả mong đợi:

| Request | HTTP status | Dấu hiệu trong body |
| --- | --- | --- |
| `GET /api/products/1` | **200** | JSON có `id=1`, `name="Notebook"`. |
| `GET /api/products/42` | **404** | `code="PRODUCT_NOT_FOUND"`, `detail="Không tìm thấy sản phẩm 42"`. |
| `GET /api/products/0` | **400** | `code="INVALID_PRODUCT_ID"`. |
| `GET /api/products/500` | **500** | `code="INTERNAL_ERROR"`; **không** chứa chuỗi lỗi nội bộ. |
| `GET /api/products/search` | **400** | `code="MISSING_PARAMETER"`, `detail` nhắc tên `term`. |

Không khẳng định chính xác toàn bộ JSON field order hay mọi header của mọi môi trường: serializer/container có thể bổ sung `instance`, header hoặc trường tiêu chuẩn theo configuration. Điều cần kiểm chứng là status, mã lỗi và các trường contract ổn định.

### 8.7. Kiểm thử bằng MockMvc

**`src/test/java/example/errors/ExceptionFlowTest.java`**:

```java
package example.errors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ExceptionFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void productExists() throws Exception {
        mvc.perform(get("/api/products/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.name").value("Notebook"));
    }

    @Test
    void domainExceptionBecomes404() throws Exception {
        mvc.perform(get("/api/products/42"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"))
                .andExpect(jsonPath("$.status").value(404));
    }

    @Test
    void missingParamIsHandledByBaseClassOverride() throws Exception {
        mvc.perform(get("/api/products/search"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("MISSING_PARAMETER"));
    }

    @Test
    void internalMessageIsHiddenFromClient() throws Exception {
        mvc.perform(get("/api/products/500"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.detail")
                        .value("Không thể hoàn tất yêu cầu"));
    }
}
```

Chạy:

```bash
mvn test
```

Đây là integration test chạy MVC stack trong test ApplicationContext; `MockMvc` không cần khởi động listener HTTP thật. Test chứng minh cả đường success, domain exception, framework binding exception, và chính sách không lộ thông tin nội bộ. Nếu hệ thống có Spring Security filter, authentication/authorization của test cần được cấu hình phù hợp; không nên tắt bảo mật chỉ để test xử lý lỗi.

## 9. Theo dõi từng request trong bài lab

### Trường hợp A: lỗi nghiệp vụ `/api/products/42`

```text
GET /api/products/42
  -> DispatcherServlet
  -> HandlerMapping: ProductController.get(...)
  -> @PathVariable chuyển thành long 42
  -> controller ném ProductNotFoundException
  -> DispatcherServlet gọi chain HandlerExceptionResolver
  -> ExceptionHandlerExceptionResolver:
       tìm @ExceptionHandler(ProductNotFoundException.class)
       gọi ApiExceptionHandler.notFound(...)
  -> ResponseEntity<ProblemDetail>
  -> Jackson serialize body
  -> HTTP 404 + JSON problem response
```

Không cần `try/catch` trong mọi controller. Chính `DispatcherServlet` phối hợp resolver theo contract MVC.

### Trường hợp B: lỗi mapping tham số `/api/products/search`

```text
GET /api/products/search
  -> HandlerMapping: ProductController.search(...)
  -> HandlerAdapter chuẩn bị @RequestParam term
  -> thiếu term -> MissingServletRequestParameterException
  -> ExceptionHandlerExceptionResolver:
       gọi advice kế thừa ResponseEntityExceptionHandler
       hook handleMissingServletRequestParameter(...)
  -> HTTP 400 + ProblemDetail
```

Điểm quan trọng: logic controller `search` **chưa được gọi** khi binding đã thất bại. Ngoại lệ này không phải lỗi business service.

### Trường hợp C: không có handler

`GET /does-not-exist` có thể dẫn đến 404 theo cấu hình mapping/static-resource/Servlet container. Tùy dòng Spring Boot, cấu hình static resources và `DispatcherServlet`, ứng dụng có thể sử dụng `NoHandlerFoundException`, `NoResourceFoundException` hoặc Boot error handling fallback.

**Đừng giả định `@ExceptionHandler(ProductNotFoundException.class)` sẽ xử lý toàn bộ 404.** Một 404 “không tìm thấy route” có nguồn gốc khác lỗi domain “không tìm thấy bản ghi”.

## 10. ResponseEntityExceptionHandler và ErrorResponse

Spring Framework 6 cung cấp `ErrorResponse` cho exception mang thông tin HTTP status, headers và `ProblemDetail` body. `ResponseEntityExceptionHandler` là lớp base giúp xử lý nhóm lỗi Spring MVC và `ErrorResponseException`, có các phương thức `handle...` để tùy chỉnh.

Các hook thường cần biết:

- `handleMethodArgumentNotValid(...)`: lỗi Bean Validation khi binding `@Valid @RequestBody`.
- `handleHttpMessageNotReadable(...)`: request body JSON sai/không đọc được.
- `handleMissingServletRequestParameter(...)`: thiếu query/form parameter.
- `handleTypeMismatch(...)`: chuyển kiểu tham số không thành công.
- `handleHttpRequestMethodNotSupported(...)`: method không được hỗ trợ.
- `handleHttpMediaTypeNotSupported(...)`: request content type không phù hợp.
- `handleExceptionInternal(...)`: xây response nội bộ chung và giữ metadata thích hợp.

Chữ ký override phụ thuộc thế hệ Spring; ví dụ Spring 6 thường nhận `HttpStatusCode` thay vì `HttpStatus` ở hook liên quan. **Luôn đối chiếu chữ ký đúng bản Spring**, dùng `@Override` để compiler phát hiện thay đổi.

### Không thay mọi lỗi framework thành một JSON 400 tùy ý

Một HTTP 405 phải giữ ý nghĩa “method không được hỗ trợ”; 415 phải giữ ý nghĩa Content-Type, 406 là Accept negotiation, và 500 là server error. Nếu override hook, thường dùng `status` framework truyền vào và giữ những header bắt buộc như `Allow`. Đừng tự suy tất cả request lỗi đều là 400.

Ví dụ pseudo-code mô tả cách override có ý thức:

```java
// Minh họa bên trong subclass ResponseEntityExceptionHandler.
// Không phải chương trình Java độc lập.
@Override
protected ResponseEntity<Object> handleHttpRequestMethodNotSupported(
        HttpRequestMethodNotSupportedException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {
    ProblemDetail body = ProblemDetail.forStatusAndDetail(
            status, "HTTP method không được hỗ trợ");
    body.setProperty("code", "METHOD_NOT_ALLOWED");
    return handleExceptionInternal(ex, body, headers, status, request);
}
```

Ta dùng `headers` do framework truyền vào thay vì bỏ qua `Allow`. Những import và base class giống phần lab trước, bổ sung `HttpRequestMethodNotSupportedException` tương ứng.

## 11. Không nhầm @ResponseStatus với response body API

Ví dụ:

```java
@ResponseStatus(HttpStatus.NOT_FOUND)
class ResourceGoneException extends RuntimeException {
    ResourceGoneException(String message) {
        super(message);
    }
}
```

Annotation trên exception nói loại lỗi nên ánh xạ sang status nào. Nó phù hợp với một số trường hợp ngắn gọn, nhưng không tự bảo đảm body có `code`, `type`, `detail` và contract JSON theo thiết kế của API.

Với REST API cần error schema nhất quán, `@RestControllerAdvice` + `ResponseEntity<ProblemDetail>` thường dễ kiểm soát hơn. Với request-specific error status nhỏ, `ResponseStatusException` cho phép ném status ngay tại chỗ, nhưng cần đánh giá cách body được dựng trong cấu hình Spring Boot hiện tại.

**Sai lầm:** cho rằng mọi `@ResponseStatus` exception đều chạy qua `ResponseStatusExceptionResolver` bất kể controller advice. Nếu `@ExceptionHandler` xử lý được ngoại lệ trước, resolver status sẽ không được gọi.

## 12. Mối quan hệ với Spring Boot /error và Servlet ERROR dispatch

Có **hai tầng** thường bị gọi lẫn nhau:

1. **Spring MVC exception resolution**: `DispatcherServlet` thử `HandlerExceptionResolver`. Kết quả có thể đã ghi JSON/body/view hoặc chỉ đặt status và coi exception đã giải quyết.
2. **Servlet container error handling**: khi exception không được MVC xử lý hoặc Servlet gửi/đánh dấu error, container có thể thực hiện **ERROR dispatch** sang trang lỗi. Spring Boot trên Servlet stack thường cấu hình endpoint `/error` (ví dụ `BasicErrorController`) làm fallback.

```text
Ngoại lệ xảy ra trong DispatcherServlet
    |
    +-- HandlerExceptionResolver xử lý
    |      |
    |      +-- response body + status -> client
    |
    +-- không xử lý / error dispatch xảy ra
           |
           v
        container ERROR dispatch
           |
           v
        /error của Boot hoặc error page cấu hình
           |
           v
        response HTML/JSON theo request và config
```

Cấu trúc này giải thích vì sao một API đôi khi trả JSON `ProblemDetail` do advice tạo, nhưng request khác trả JSON mặc định Boot hoặc HTML error page. Đó là **đường đi khác nhau**, không nhất thiết là “Spring phớt lờ handler”.

Tuy nhiên, **không phải mọi response status 4xx/5xx đều chắc chắn kích hoạt `/error`**. Nếu advice đã tự dựng response với status và body, container thường gửi response đó. Cơ chế error dispatch phụ thuộc `sendError`, exception propagation, container và response state; cần quan sát thực tế.

### Bật Problem Details toàn cục trong Boot

Spring Boot có tùy chọn:

```yaml
spring:
  mvc:
    problemdetails:
      enabled: true
```

Tùy chọn này hỗ trợ định dạng Problem Details cho những lỗi MVC được framework xử lý. **Không cần bật** nếu bạn trả `ProblemDetail` trực tiếp trong `@ExceptionHandler` như bài lab. Khi kết hợp với custom `@ControllerAdvice` kế thừa `ResponseEntityExceptionHandler`, cần đánh giá độ ưu tiên và coverage để tránh các handler cạnh tranh hoặc body không thống nhất.

## 13. Những lỗi không nên xử lý bằng HandlerExceptionResolver MVC

| Nguồn lỗi | Vì sao có thể nằm ngoài chuỗi MVC? | Nơi cần xử lý |
| --- | --- | --- |
| Servlet `Filter` ném exception trước khi gọi `DispatcherServlet` | Servlet chưa nhận quyền điều phối request | Filter error policy, Servlet error dispatch; với Spring Security dùng security exception handling/filter chain. |
| Spring Security authentication/authorization | Thường được kiểm soát bởi `ExceptionTranslationFilter` và `AuthenticationEntryPoint`/`AccessDeniedHandler` | Cấu hình Spring Security tương ứng; 401 và 403 đúng contract. |
| `@Async` fire-and-forget | Không có request MVC đang chờ exception | `AsyncUncaughtExceptionHandler`, future completion, logging/observability. |
| `@Scheduled` task | Chạy trên scheduler thread, không có HTTP request | Error handler của scheduler, retries/alert. |
| Lỗi startup/config/database connection lúc khởi tạo | App context chưa sẵn sàng phục vụ HTTP | Startup logs, health/readiness, deploy fail. |
| Response đã committed rồi mới lỗi | Header/status/body đã gửi một phần; không thể thay phản hồi nguyên vẹn | Log, close connection, thiết kế streaming/transaction boundary, metrics. |

**Ngoại lệ từ async MVC request khác với lỗi nền `@Async` độc lập.** Với `Callable`/`DeferredResult`/`WebAsyncTask`, lỗi có thể được tái dispatch về Spring MVC để xử lý bằng resolver trên pha async dispatch. Cần test trường hợp cụ thể, nhất là khi response đã committed hoặc timeout.

## 14. Các lỗi thiết kế và bẫy thực tế

### Bẫy 1: catch Exception rồi trả HTTP 200

```java
// Ví dụ SAI: client không biết yêu cầu thất bại.
try {
    return service.load(id);
} catch (Exception ex) {
    return "ERROR";
}
```

Client HTTP nhìn thấy 200 có thể coi request thành công, retry/caching/monitoring sai. Nên để domain exception đi qua MVC handler và trả status đúng, hoặc chủ động `ResponseEntity.status(...)` cho một nhánh được thiết kế rõ.

### Bẫy 2: một global handler bắt tất cả và trả 400

```java
// Ví dụ SAI: che lỗi server, protocol 405/415, v.v.
@ExceptionHandler(Exception.class)
ResponseEntity<String> everything(Exception ex) {
    return ResponseEntity.badRequest().body(ex.getMessage());
}
```

Lỗi nội bộ bị gắn 400, dữ liệu nhạy cảm trong message bị lộ; các handler framework cụ thể có thể bị che hoặc gây bất ngờ trong resolver ordering. Nếu cần fallback 500, viết mapping rõ ràng, giữ log/correlation ID, đồng thời bảo đảm các lỗi chuẩn đã được xử lý đúng.

### Bẫy 3: thêm @ExceptionHandler trùng base class

Khi `extends ResponseEntityExceptionHandler`, base class có những mapping `@ExceptionHandler` cho nhóm framework exceptions. Nếu subclass thêm `@ExceptionHandler(HttpMessageNotReadableException.class)` thay vì override `handleHttpMessageNotReadable`, có thể gây ambiguous exception handler method. Với exception Spring MVC có sẵn hook, dùng **override hook**.

### Bẫy 4: xử lý HTML view trong REST advice

`@ControllerAdvice` trả một chuỗi `"error"` có thể được coi là tên view, không phải JSON body; `@RestControllerAdvice` hoặc `@ResponseBody` cùng `ResponseEntity` giúp biểu thị rõ kiểu phản hồi.

### Bẫy 5: nhầm null ModelAndView với handled

Trong custom resolver, trả `null` yêu cầu resolver sau tiếp tục. Nếu đã tự ghi status/body nhưng vẫn trả `null`, resolver sau có thể cố viết tiếp, tạo response conflict. Ngược lại trả `new ModelAndView()` để đánh dấu đã xử lý khi response đã được xây đầy đủ.

### Bẫy 6: thử xử lý exception sau response đã gửi

Nếu streaming endpoint đã gửi một phần body, dù advice được gọi, status/headers có thể không sửa được. Không thể biến một response nửa chừng thành JSON lỗi chuẩn như chưa gửi byte nào. Cần thiết kế stream-specific error protocol và logging thích hợp.

### Bẫy 7: nhầm nguyên nhân 404

**404 do route không tồn tại** khác **404 do bản ghi không tồn tại**. Endpoint path sai có thể đi qua resource handler/Boot error fallback, trong khi lỗi domain thường là `ProductNotFoundException` ở controller/service. Test cả hai đường riêng.

### Bẫy 8: bỏ mất thông tin cho client hoặc lộ quá nhiều

Lỗi 400 nên có mã nghiệp vụ ổn định và detail hữu ích (tên field, quy tắc validation) nhưng không tiết lộ dữ liệu nhạy cảm. Lỗi 500 nên trả thông báo chung, không trả stack trace. Backend cần log đủ ngữ cảnh (correlation ID, exception type, relevant request metadata) mà không ghi token/password.

## 15. Chiến lược phân loại HTTP error trong API

| Loại lỗi | HTTP status điển hình | Ví dụ | Handler phù hợp |
| --- | --- | --- | --- |
| Sai input, type, JSON hoặc validation | 400 | `id=-1`, JSON malformed | Advice cụ thể hoặc `ResponseEntityExceptionHandler` hook. |
| Chưa xác thực | 401 | Thiếu bearer token | Security filter/entry point. |
| Có danh tính nhưng không có quyền | 403 | Role không đủ | Spring Security access denied handler hoặc policy ứng dụng phù hợp. |
| Tài nguyên nghiệp vụ không có | 404 | Product ID 42 vắng mặt | Domain exception + `@ExceptionHandler`. |
| Method không hỗ trợ | 405 | POST vào GET-only endpoint | Resolver/framework behavior, giữ `Allow`. |
| Conflict với trạng thái hiện tại | 409 | Trùng mã định danh khi tạo entity | Domain conflict exception/advice. |
| Media type không hỗ trợ | 415 | XML gửi tới JSON-only endpoint | Framework mapping/resolver. |
| Validation không thể áp dụng rule nghiệp vụ | 422 khi API contract chọn | Các trường có type hợp lệ nhưng vi phạm rule | Domain exception/advice; chọn status nhất quán với API. |
| Hệ thống thất bại ngoài dự kiến | 500 | Service không hoạt động, bug | Sanitized fallback error, logging. |
| Phụ thuộc upstream không đáp ứng | 502/503/504 tùy vai trò và ngữ cảnh gateway | Dependency timeout/unavailable | Exception translation ở boundary phù hợp; không mặc định mọi timeout = 504. |

Đây là mapping gợi ý; HTTP contract nên được định nghĩa nhất quán giữa client/server. Riêng 401/403, xử lý nằm trong Spring Security filter chain thường quan trọng hơn global MVC advice.

## 16. Khi nào thực sự viết custom HandlerExceptionResolver?

Phần lớn REST API nên bắt đầu bằng:

- `@ExceptionHandler` cục bộ cho hành vi rất riêng.
- `@RestControllerAdvice` cho lỗi domain chung.
- `ResponseEntityExceptionHandler` để chuẩn hóa nhóm framework exceptions.
- `ProblemDetail` để chuẩn hóa body.

Chỉ viết một `HandlerExceptionResolver` riêng khi có yêu cầu rất đặc biệt, chẳng hạn cần tương thích một cơ chế lỗi cũ, mapping theo một handler type cụ thể hoặc tích hợp với một error pipeline có hợp đồng riêng. Nếu viết custom resolver:

1. Chỉ nhận những exception thuộc trách nhiệm của nó; exception khác trả `null`.
2. Kiểm tra `response.isCommitted()` trước khi chỉnh status/header/body.
3. Giữ HTTP status/header chính xác và tránh ghi hai lần.
4. Chọn `order` có chủ đích; không chặn `ExceptionHandlerExceptionResolver` một cách vô tình.
5. Test đồng thời case resolver xử lý và case resolver phải nhường cho default MVC chain.

Trong Spring MVC cấu hình bằng `WebMvcConfigurer`, `extendHandlerExceptionResolvers(...)` cho phép bổ sung vào danh sách hiện có. Còn `configureHandlerExceptionResolvers(...)` có thể thay đổi hoặc tự thiết lập danh sách theo hợp đồng cấu hình; dùng sai có thể làm mất các resolver mặc định. Vì vậy hãy ưu tiên cơ chế annotation sẵn có nếu nhu cầu chỉ là tạo HTTP JSON lỗi.

## 17. Kiểm thử và quan sát trên môi trường thật

### Kiểm thử chức năng

- Endpoint thành công vẫn trả **2xx** và body bình thường.
- Lỗi nghiệp vụ cụ thể trả status/code/detail mong đợi.
- Lỗi framework (missing param, malformed JSON, unsupported method/media type) trả status phù hợp và không mất header quan trọng.
- Lỗi nội bộ trả 500 **không lộ** stack trace hoặc nội dung nhạy cảm.
- Controller có local `@ExceptionHandler` xử lý khác global advice đúng theo thứ tự.
- Route 404 do không có handler được test riêng, không trộn với domain 404.
- Với async/streaming, test cả trước và sau response commit nếu ứng dụng dùng những mô hình đó.

### Quan sát production

Log stack trace ở phía server cho lỗi 5xx; phân biệt log dự đoán được (ví dụ domain 404/400) với exception bất thường để tránh tạo log nhiễu. Gắn request ID/trace ID qua logging context hay observation system. Ghi metric theo HTTP status, exception type, endpoint pattern; không dùng full URL có ID bí mật làm nhãn metric.

Khi nhận phản ánh “API trả 500 nhưng không vào advice”, trước tiên kiểm tra **lỗi phát sinh ở filter hay dispatcher?**, response đã committed chưa, class advice có được component scan không, exception có được wrapper ở cause chain không, thứ tự advice nào bắt trước và request có bị container chuyển tới `/error` không.

## 18. Câu hỏi tự đánh giá

**Câu 1:** Custom resolver trả `null` sau khi thấy exception thì có nghĩa lỗi được xử lý chưa?  
**Đáp:** Chưa. `null` nghĩa là chưa xử lý; Spring thử resolver tiếp theo.

**Câu 2:** `@ExceptionHandler` trong controller và `@RestControllerAdvice` cùng bắt `IllegalArgumentException` thì ai được ưu tiên?  
**Đáp:** Handler cục bộ trong controller được xét trước nếu phù hợp.

**Câu 3:** Thiếu `@RequestParam`, controller có được gọi rồi mới ném lỗi không?  
**Đáp:** Thường không. Exception có thể phát sinh khi HandlerAdapter chuẩn bị argument trước khi gọi method.

**Câu 4:** Vì sao status 405 có thể có header `Allow`?  
**Đáp:** Đó là thông tin method mà tài nguyên hỗ trợ theo HTTP. Tùy biến handler không nên vứt bỏ header chuẩn này.

**Câu 5:** Có nên tạo `@ExceptionHandler(HttpMessageNotReadableException.class)` trong subclass `ResponseEntityExceptionHandler`?  
**Đáp:** Nên override hook `handleHttpMessageNotReadable` để tránh mapping cạnh tranh với base class.

**Câu 6:** Spring Security filter ném authentication exception trước DispatcherServlet thì global MVC advice luôn bắt được không?  
**Đáp:** Không. Security chain có cơ chế xử lý riêng như `AuthenticationEntryPoint` và `AccessDeniedHandler`.

**Câu 7:** Vì sao API đôi khi trả body mặc định ở `/error` thay vì `ProblemDetail` custom?  
**Đáp:** Ngoại lệ có thể chưa được MVC resolver xử lý, hoặc container thực hiện error dispatch. Cần truy lại luồng xử lý thực tế.

**Câu 8:** Lỗi 500 nên gửi những gì?  
**Đáp:** Status đúng, mã lỗi ổn định, thông điệp an toàn và request/trace ID nếu có; không gửi stack trace, SQL/password hay thông tin hệ thống nội bộ.

## 19. Nguồn đối chiếu

- [Spring Framework — Exceptions / Chain of Resolvers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html).
- [Spring Framework — @ExceptionHandler methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html).
- [Spring Framework — Controller Advice](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html).
- [Spring Framework — Error Responses and ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html).
- [Spring Boot 3.5 — Servlet Web Applications / Error Handling](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html).
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457).

**Điểm ghi nhớ:** `HandlerExceptionResolver` giúp `DispatcherServlet` chuyển ngoại lệ trong Spring MVC thành **phản hồi HTTP có chủ đích**. Chọn đúng lớp xử lý theo nguồn lỗi, hiểu thứ tự resolver/advice, và kiểm thử status, body, headers cùng trust boundary sẽ giúp API có error contract ổn định và an toàn.