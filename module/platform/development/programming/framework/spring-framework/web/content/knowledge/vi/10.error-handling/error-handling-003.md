# @ControllerAdvice, @RestControllerAdvice và phạm vi áp dụng trong Spring MVC

## Mục tiêu bài học

Một REST API có hàng chục controller thường cần cùng một cách trả lỗi 400, 404 hoặc 500. Nếu mỗi controller tự viết `try/catch` hoặc lặp `@ExceptionHandler`, định dạng lỗi dễ thiếu nhất quán. **`@ControllerAdvice`** và **`@RestControllerAdvice`** giúp chia sẻ các callback MVC cho nhiều controller, đồng thời cho phép **giới hạn phạm vi áp dụng** theo package, annotation hoặc loại controller.

Sau bài học, bạn sẽ:

- Giải thích `@ControllerAdvice` dùng được cho những callback nào và `@RestControllerAdvice` bổ sung điều gì.
- Phân biệt view rendering với HTTP response body khi xử lý exception.
- Biết advice **mặc định áp dụng rộng**, và chủ động giới hạn bằng `basePackages`, `basePackageClasses`, `assignableTypes`, `annotations`; hiểu quy tắc kết hợp selector là **OR**.
- Hiểu mức ưu tiên giữa `@ExceptionHandler` cục bộ và global, `@Order` giữa nhiều advice, root exception và cause exception.
- Viết Spring Boot 3 / Spring MVC REST API với hai advice có phạm vi tách biệt và kiểm thử bằng MockMvc.
- Tránh handler nuốt toàn bộ `Exception`, làm rò rỉ chi tiết nhạy cảm hoặc tưởng advice xử lý mọi lỗi ở mọi tầng.

**Phạm vi kỹ thuật:** Java 17+, Spring Framework 6.x / Spring Boot 3.x, MVC chạy trên **Servlet stack**. Spring WebFlux có annotation tương tự nhưng luồng xử lý reactive và exception infrastructure khác; ví dụ dưới đây dành cho MVC.

## 1. Trước khi dùng advice: xử lý lỗi cục bộ

Trong một controller, Spring MVC cho phép khai báo `@ExceptionHandler` để xử lý ngoại lệ phát sinh trong các handler của **controller đó**:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping("/{id}")
    public String find(@PathVariable long id) {
        if (id != 1L) {
            throw new BookNotFoundException("Book " + id + " not found");
        }
        return "Spring MVC";
    }

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<String> handleLocal(BookNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body("Book not found");
    }
}
~~~

Đây là **đoạn minh họa**, cần định nghĩa `BookNotFoundException` và import các class tương ứng. Nó cho thấy controller quản lý được lỗi thuộc phạm vi của mình. Tuy nhiên nếu hàng chục controller đều xử lý lỗi không tìm thấy hoặc validation như nhau, việc sao chép handler làm tăng chi phí bảo trì.

Ở mức MVC, exception được chuyển qua chuỗi `HandlerExceptionResolver`. `ExceptionHandlerExceptionResolver` tìm `@ExceptionHandler` phù hợp; ngoài ra Spring còn có resolver cho một số loại lỗi tiêu chuẩn, status được khai báo và những cơ chế xử lý lỗi tiếp theo. Vì thế không phải **mọi** response lỗi đều chắc chắn bắt nguồn từ một advice.

## 2. `@ControllerAdvice` là gì?

`@ControllerAdvice` đánh dấu một Spring bean chứa các phương thức áp dụng cho **nhiều controller**. Có ba nhóm callback thông dụng:

| Callback trong advice | Mục đích |
| --- | --- |
| `@ExceptionHandler` | Chuyển exception thành status, body, headers hoặc view lỗi |
| `@InitBinder` | Tùy chỉnh `WebDataBinder`: conversion, editor, formatter, validator và allowed fields |
| `@ModelAttribute` trên method | Bổ sung hoặc khởi tạo model dùng chung cho các handler MVC phù hợp |

Ví dụ xử lý ngoại lệ dùng chung:

~~~java
@ControllerAdvice
public class SharedErrorAdvice {

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<Map<String, String>> handle(
            BookNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("error", "BOOK_NOT_FOUND"));
    }
}
~~~

Đây cũng là **đoạn minh họa**, cần import và một `BookNotFoundException`. Khi một controller thuộc phạm vi advice ném ngoại lệ tương ứng, Spring MVC có thể gọi method `handle` và viết response 404.

`@ControllerAdvice` được meta-annotated với `@Component`, nên class thường được tìm thấy bằng **component scanning**; cũng có thể đăng ký trực tiếp thành bean. Nếu advice nằm ngoài những package Spring đang scan, nó sẽ không tự hoạt động chỉ vì bạn đã tạo file Java.

**Phạm vi mặc định:** nếu không khai báo bất kỳ selector nào, advice có thể áp dụng cho **mọi controller MVC phù hợp**, gồm cả `@Controller` và `@RestController`. Annotation không mặc định phân loại controller HTML hay REST.

## 3. `@RestControllerAdvice` khác gì?

`@RestControllerAdvice` là annotation kết hợp tương đương về ngữ nghĩa với:

~~~java
@ControllerAdvice
@ResponseBody
public class RestErrorAdvice {
    // @ExceptionHandler methods...
}
~~~

Nó kế thừa chức năng và selector của `@ControllerAdvice`, đồng thời cho các method xử lý ngoại lệ mặc định mang ngữ nghĩa **`@ResponseBody`**: giá trị trả về bình thường được chuyển thành HTTP response body bằng `HttpMessageConverter` (ví dụ Jackson viết JSON), thay vì được diễn giải như tên view.

Ví dụ:

~~~java
@RestControllerAdvice
public class ApiErrors {

    @ExceptionHandler(BookNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public ErrorBody notFound(BookNotFoundException ex) {
        return new ErrorBody("BOOK_NOT_FOUND", "Book does not exist");
    }

    public record ErrorBody(String code, String message) {}
}
~~~

Đoạn trên là minh họa: `ErrorBody` sẽ thành JSON object với các property `code` và `message` khi có JSON converter, với status 404 do `@ResponseStatus`.

Với `@ControllerAdvice` thông thường:

~~~java
@ControllerAdvice
public class HtmlErrors {

    @ExceptionHandler(BookNotFoundException.class)
    public String notFound(Model model) {
        model.addAttribute("message", "Book does not exist");
        return "errors/not-found";
    }
}
~~~

Đây là **minh họa cho ứng dụng HTML có ViewResolver và template `errors/not-found`**; không phải file độc lập. `String` thông thường được diễn giải như **tên view**. Nếu đặt logic kiểu đó trong `@RestControllerAdvice`, `String` có thể được ghi **thành text response body** `errors/not-found` thay vì chọn template.

**Một điểm dễ nhầm:** `@ControllerAdvice` **vẫn có thể xử lý REST**. Nếu method gắn `@ResponseBody`, trả `ResponseEntity<SomeDto>`, hoặc dùng loại return value mang ngữ nghĩa body thích hợp, nó vẫn gửi JSON/body mà không phải đổi annotation class thành `@RestControllerAdvice`. Sự khác biệt là **giá trị trả về mặc định của các handler**, không phải phạm vi REST/HTML mà advice áp dụng.

| Đặc điểm | `@ControllerAdvice` | `@RestControllerAdvice` |
| --- | --- | --- |
| Là Spring bean được MVC phát hiện | Có | Có |
| Chia sẻ `@ExceptionHandler`, `@InitBinder`, `@ModelAttribute` | Có | Có |
| Scope mặc định khi không selector | Các controller phù hợp nói chung | Các controller phù hợp nói chung |
| Body serialization mặc định cho `@ExceptionHandler` trả object | Không có `@ResponseBody` implicit ở class | Có `@ResponseBody` implicit |
| Trả `String` từ exception handler | Thường là view name nếu không có `@ResponseBody` | Thường là response body |
| Trả `ResponseEntity<Dto>` | Hỗ trợ | Hỗ trợ |
| Nên dùng | MVC HTML, hoặc REST có return type rõ | REST JSON/problem details |

`@RestControllerAdvice` **không** đồng nghĩa “chỉ áp dụng cho `@RestController`”. Nếu muốn riêng REST, bạn phải dùng selector, ví dụ `@RestControllerAdvice(annotations = RestController.class)`.

## 4. Phạm vi áp dụng: 4 nhóm selector

Cả `@ControllerAdvice` lẫn `@RestControllerAdvice` đều hỗ trợ những thuộc tính quan trọng:

### 4.1. `basePackages`

~~~java
@RestControllerAdvice(basePackages = "com.example.demo.api")
public class ApiErrorAdvice {
    // ...
}
~~~

Áp dụng cho các controller thuộc package `com.example.demo.api` hoặc những subpackage bên dưới. Đối với dự án đổi tên/refactor package, chuỗi literal có thể trở nên sai mà compiler không cảnh báo.

Thuộc tính `value` là alias của `basePackages`, ví dụ `@ControllerAdvice("com.example.demo.api")`.

### 4.2. `basePackageClasses`

~~~java
@RestControllerAdvice(basePackageClasses = ApiPackageMarker.class)
public class ApiErrorAdvice {
    // ...
}
~~~

Đây là **đoạn minh họa**, cần có class/interface `ApiPackageMarker` nằm trong package API và khai báo method của advice. Selector dùng **package chứa class được chỉ định** (và package con), không giới hạn chính class marker. Cách này dễ refactor và được compiler kiểm tra tốt hơn chuỗi package.

### 4.3. `assignableTypes`

~~~java
@RestControllerAdvice(assignableTypes = {
        CatalogController.class, BillingController.class
})
public class BusinessErrorAdvice {
    // ...
}
~~~

Ví dụ này chọn những controller mà kiểu của chúng **assignable** tới một trong các class/interface liệt kê (có tính đến phân cấp kế thừa). Có thể dùng controller cụ thể hoặc interface/base controller chung. Đây không phải filter theo tên URL hoặc tên exception.

### 4.4. `annotations`

~~~java
@RestControllerAdvice(annotations = RestController.class)
public class RestOnlyErrorAdvice {
    // ...
}
~~~

Selector tìm controller mang annotation được chỉ định (và cách Spring tìm annotation kết hợp/phân cấp phù hợp). Ví dụ trên là một cách hướng advice tới controller REST, nhưng cần nhớ controller có thể dùng `@Controller` và `@ResponseBody` ở handler để trả API body mà **không** mang `@RestController`; nếu vậy selector này không bao phủ nó.

### 4.5. Quy tắc OR: hai selector không phải phép AND

~~~java
@RestControllerAdvice(
        basePackages = "com.example.demo.api",
        annotations = RestController.class
)
public class MixedScopeAdvice {
    // ...
}
~~~

Khi nhiều selector cùng được khai báo, Spring ghép chúng theo **OR**: controller khớp **ít nhất một** selector là đủ.

Vì vậy ví dụ trên có thể áp dụng cho:
- `@Controller` HTML nằm trong package `com.example.demo.api` dù không mang `@RestController`.
- `@RestController` ở package hoàn toàn khác.

Nếu mục tiêu là “chỉ `@RestController` nằm **trong** package api”, không thể giả định hai thuộc tính trong cùng một advice tạo thành AND. Hãy tổ chức một tập controller có marker annotation hoặc type phù hợp và dùng selector diễn đạt chính xác; nếu cần, tách các nhóm advice riêng.

Các selector được đánh giá tại runtime. Sử dụng rất nhiều selector hoặc quá nhiều advice có thể làm hệ thống khó hiểu hơn và ảnh hưởng chi phí chọn handler. Trong hệ thống đơn giản, nên dùng phạm vi rõ theo package hoặc loại controller; trong hệ thống có nhiều API version, nên chủ động tách bộ xử lý lỗi theo nhóm API.

## 5. Thứ tự ưu tiên và vòng đời callback

### 5.1. `@ExceptionHandler` trong controller được xét trước global advice

Nếu cùng một exception có `@ExceptionHandler` cục bộ trong controller và global handler trong một advice áp dụng, **handler cục bộ của controller được ưu tiên**. Điều này rất hữu ích khi chỉ một controller cần ngoại lệ response đặc thù.

~~~java
@RestController
class OneController {

    @GetMapping("/conflict")
    String action() {
        throw new ItemConflictException("Conflict");
    }

    @ExceptionHandler(ItemConflictException.class)
    ResponseEntity<String> localHandler(ItemConflictException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body("local");
    }
}
~~~

Đây là minh họa; cần khai báo `ItemConflictException` và import. Dù có `@RestControllerAdvice` chung xử lý cùng exception, local handler phù hợp thường được chọn trước.

### 5.2. Nhiều advice: `@Order` và `Ordered`

~~~java
@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
class SpecificErrors {
    // ...
}

@RestControllerAdvice
@Order(Ordered.LOWEST_PRECEDENCE)
class FallbackErrors {
    // ...
}
~~~

Đây là đoạn mô tả thứ tự (chưa có các method handler). Spring xét các advice theo thứ tự ưu tiên. `@Order` có giá trị **nhỏ hơn thì ưu tiên cao hơn**; `Ordered` là một cơ chế ưu tiên tương ứng. Với một exception, Spring có thể chọn **advice ưu tiên cao nhất có handler khớp**, không tự chờ một advice ưu tiên thấp hơn dù handler ở đó trông có vẻ cụ thể hơn.

**Root exception vs cause exception:** bên trong **cùng một advice**, matching ở exception gốc thường được ưu tiên hơn matching ở cause. Nhưng một **cause match ở advice ưu tiên cao** vẫn có thể thắng **root match ở advice ưu tiên thấp**. Hãy đặt các mapping exception nghiệp vụ cụ thể trong advice được ưu tiên rõ ràng. Tránh phân tán handler cùng exception vào nhiều advice mà không kiểm soát thứ tự.

Một vài chi tiết của Spring Framework 6.x:
- Bean advice implement `Ordered` có tính ưu tiên so với metadata `@Order`/`@Priority` theo quy tắc framework.
- `PriorityOrdered` trên advice không tự bảo đảm ưu tiên trên mọi `Ordered` như bạn có thể kỳ vọng từ nơi khác.
- `Ordered` **không được tôn trọng** đối với scoped advice bean (ví dụ bean request-scoped hoặc session-scoped). Dùng advice singleton thông thường khi cần điều phối ưu tiên ổn định.
- Không suy đoán thứ tự giữa nhiều handler mơ hồ. Nếu cấu hình có thể dẫn tới ambiguous mapping cho cùng exception và scope, hãy tách rõ kiểu exception/phạm vi/ưu tiên và kiểm thử.

### 5.3. Với `@ModelAttribute` và `@InitBinder`, thứ tự khác

Ngược với `@ExceptionHandler`: `@ModelAttribute` và `@InitBinder` từ **global advice** được áp dụng **trước** method tương ứng trong controller (nếu cùng ngữ cảnh). Điều này hữu ích khi cấu hình binder/model chung phải có trước, rồi controller mới tinh chỉnh.

Ví dụ `@InitBinder` trong advice có thể trim form input cho một nhóm controller; binder cục bộ đặt `allowedFields` cho một model cụ thể. Không kỳ vọng `@InitBinder` chuyển đổi toàn bộ JSON `@RequestBody` đã được Jackson deserialization. Scope advice không thay thế sự khác nhau giữa **WebDataBinder** và **HttpMessageConverter**.

### 5.4. Exception handler không phải blanket `try/catch` cho ứng dụng

`@ControllerAdvice` hoạt động trong luồng xử lý MVC. Ngoại lệ trong authentication filter hoặc tầng proxy có thể được xử lý **trước khi tới DispatcherServlet** và không được advice bắt; với Spring Security, các exception authentication/access liên quan filter chain có cơ chế riêng. Lỗi bất đồng bộ, exception từ task ngoài request hoặc việc response đã commit cũng cần xử lý riêng.

Đừng bắt `Exception.class` toàn cục rồi biến mọi lỗi thành 200/400. Điều đó che lỗi server, khó theo dõi và có thể phá những status Spring MVC xử lý chính xác cho lỗi input.

## 6. Ví dụ chạy được: hai nhóm controller có advice riêng

Ta xây dựng hai endpoint nhóm **catalog** và **billing** cùng ném `RecordMissingException`, nhưng trả body lỗi riêng. Đồng thời catalog có **local `@ExceptionHandler`** cho lỗi conflict để chứng minh local được ưu tiên hơn global.

Dự án Maven dùng **Java 17+**, **Spring Boot 3.x**, dependency **Spring Web** (starter `spring-boot-starter-web`) và **Spring Boot Starter Test** (`spring-boot-starter-test`). Tạo bằng Spring Initializr, package `com.example.demo`.

Cấu trúc:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/RecordMissingException.java
src/main/java/com/example/demo/CatalogConflictException.java
src/main/java/com/example/demo/CatalogController.java
src/main/java/com/example/demo/BillingController.java
src/main/java/com/example/demo/CatalogErrorAdvice.java
src/main/java/com/example/demo/BillingErrorAdvice.java
src/test/java/com/example/demo/AdviceScopeTest.java
~~~

### 6.1. `DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 6.2. Hai exception nghiệp vụ

**`RecordMissingException.java`:**

~~~java
package com.example.demo;

public class RecordMissingException extends RuntimeException {
    public RecordMissingException(String message) {
        super(message);
    }
}
~~~

**`CatalogConflictException.java`:**

~~~java
package com.example.demo;

public class CatalogConflictException extends RuntimeException {
    public CatalogConflictException(String message) {
        super(message);
    }
}
~~~

Không gắn `@ResponseStatus` lên hai exception này: status được quyết định bởi handler được chọn theo scope, giúp chúng ta dễ quan sát sự khác nhau.

### 6.3. `CatalogController.java` có local handler

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/catalog")
public class CatalogController {

    @GetMapping("/{id}")
    public CatalogItem get(@PathVariable long id) {
        if (id != 1L) {
            throw new RecordMissingException("Catalog item not found");
        }
        return new CatalogItem(1L, "Spring MVC");
    }

    @GetMapping("/conflict")
    public String conflict() {
        throw new CatalogConflictException("Catalog state conflict");
    }

    @ExceptionHandler(CatalogConflictException.class)
    public ResponseEntity<Map<String, String>> localConflict(
            CatalogConflictException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("error", "LOCAL_CATALOG_CONFLICT"));
    }

    public record CatalogItem(long id, String title) {
    }
}
~~~

Khi `/api/catalog/conflict` ném `CatalogConflictException`, local handler trong chính controller này trả **409 Conflict**. Ta sẽ tạo global handler cho cùng exception ở `CatalogErrorAdvice` nhưng nó **không được chọn** cho trường hợp này.

### 6.4. `BillingController.java`

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/billing")
public class BillingController {

    @GetMapping("/{id}")
    public BillingRecord get(@PathVariable long id) {
        if (id != 1L) {
            throw new RecordMissingException("Billing record not found");
        }
        return new BillingRecord(1L, 750);
    }

    public record BillingRecord(long id, int amount) {
    }
}
~~~

Hai controller cùng ném một **class exception**. Nếu handler global không được scope rõ, rất dễ áp dụng sai format lỗi giữa catalog và billing.

### 6.5. `CatalogErrorAdvice.java`: REST body và ProblemDetail

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@Order(Ordered.HIGHEST_PRECEDENCE)
@RestControllerAdvice(assignableTypes = CatalogController.class)
public class CatalogErrorAdvice {

    @ExceptionHandler(RecordMissingException.class)
    public ResponseEntity<ProblemDetail> missing(
            RecordMissingException ex) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, "Catalog item not found");
        problem.setTitle("Catalog lookup failed");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(problem);
    }

    // Chỉ minh họa: nếu controller KHÔNG có local handler,
    // advice này có thể xử lý CatalogConflictException.
    @ExceptionHandler(CatalogConflictException.class)
    public ResponseEntity<Map<String, String>> globalConflict(
            CatalogConflictException ex) {
        return ResponseEntity.unprocessableEntity()
                .body(Map.of("error", "ADVICE_CATALOG_CONFLICT"));
    }
}
~~~

`ProblemDetail` là kiểu Spring Framework 6.x hỗ trợ phản hồi lỗi theo **RFC 9457**. Khi Jackson và MVC cấu hình thông thường, response ưu tiên `application/problem+json`, có các field như `type`, `title`, `status`, `detail`, có thể có `instance`. Đừng ghi mã lỗi nội bộ hoặc dữ liệu nhạy cảm nguyên vẹn vào `detail` cho client.

Advice này chỉ áp dụng cho `CatalogController` theo `assignableTypes`. `@Order(HIGHEST_PRECEDENCE)` thể hiện độ ưu tiên giữa các advice khi phạm vi chồng nhau; trong ví dụ, hai advice được scope tách biệt nên sự chính xác đến chủ yếu từ selector.

### 6.6. `BillingErrorAdvice.java`: `@ControllerAdvice` vẫn trả JSON

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;

@ControllerAdvice(assignableTypes = BillingController.class)
public class BillingErrorAdvice {

    @ExceptionHandler(RecordMissingException.class)
    public ResponseEntity<Map<String, String>> missing(
            RecordMissingException ex) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of(
                        "error", "BILLING_NOT_FOUND",
                        "message", "Billing record not found"));
    }
}
~~~

Đây là bằng chứng rằng `@ControllerAdvice` **không chỉ dành cho HTML view**: method trả `ResponseEntity<Map<...>>` được Spring xử lý như HTTP body bình thường. Nếu thay return type thành một `String` không có `@ResponseBody`, việc xử lý lại có thể theo cơ chế view name.

Hai advice đều nhìn thấy cùng class `RecordMissingException` nhưng **không đụng nhau** vì `assignableTypes` tách controller catalog với billing.

## 7. Chạy và đối chiếu HTTP status/body

Tại thư mục dự án Maven, chạy:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows dùng `mvnw.cmd spring-boot:run`; nếu không có Maven Wrapper, dùng `mvn spring-boot:run` sau khi cài Maven.

### Catalog thiếu bản ghi

~~~bash
curl -i http://localhost:8080/api/catalog/99
~~~

Kết quả kỳ vọng **404 Not Found**, media type tương thích `application/problem+json`, JSON có nội dung tương đương:

~~~json
{
  "type": "about:blank",
  "title": "Catalog lookup failed",
  "status": 404,
  "detail": "Catalog item not found"
}
~~~

`instance` có thể được Spring bổ sung từ path tùy ngữ cảnh; không cố định toàn bộ JSON body và thứ tự property. Nếu server có custom Jackson/advice khác thì representation cũng có thể thay đổi.

### Billing thiếu bản ghi

~~~bash
curl -i http://localhost:8080/api/billing/99
~~~

Kết quả kỳ vọng **404 Not Found** với JSON:

~~~json
{
  "error": "BILLING_NOT_FOUND",
  "message": "Billing record not found"
}
~~~

Cùng exception, cùng status 404 nhưng **body khác** vì advice khác nhau được chọn theo controller.

### Local exception handler thắng advice

~~~bash
curl -i http://localhost:8080/api/catalog/conflict
~~~

Kết quả kỳ vọng **409 Conflict** và JSON:

~~~json
{"error":"LOCAL_CATALOG_CONFLICT"}
~~~

Nếu local handler không được xét trước, advice catalog có thể trả **422 Unprocessable Entity** với `ADVICE_CATALOG_CONFLICT`. Vì local handler tồn tại, nhánh global đó không chạy trong request này.

### Trường hợp thành công

~~~bash
curl -i http://localhost:8080/api/catalog/1
curl -i http://localhost:8080/api/billing/1
~~~

Hai response đều có status **200 OK**, lần lượt chứa:

~~~json
{"id":1,"title":"Spring MVC"}
~~~

~~~json
{"id":1,"amount":750}
~~~

Vì ví dụ không dùng database, dữ liệu hoàn toàn cố định để thuận tiện kiểm thử. Trên PowerShell Windows, dùng `curl.exe` để tránh alias `curl` ở một số môi trường.

## 8. Kiểm thử phạm vi bằng MockMvc

Thêm dependency `spring-boot-starter-test`. Tạo file **`src/test/java/com/example/demo/AdviceScopeTest.java`**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = {
        CatalogController.class, BillingController.class
})
@Import({CatalogErrorAdvice.class, BillingErrorAdvice.class})
class AdviceScopeTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void catalogErrorUsesCatalogAdvice() throws Exception {
        mockMvc.perform(get("/api/catalog/99"))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.title")
                        .value("Catalog lookup failed"))
                .andExpect(jsonPath("$.detail")
                        .value("Catalog item not found"));
    }

    @Test
    void billingErrorUsesBillingAdvice() throws Exception {
        mockMvc.perform(get("/api/billing/99"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error")
                        .value("BILLING_NOT_FOUND"))
                .andExpect(jsonPath("$.message")
                        .value("Billing record not found"));
    }

    @Test
    void localExceptionHandlerWinsOverGlobalAdvice() throws Exception {
        mockMvc.perform(get("/api/catalog/conflict"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error")
                        .value("LOCAL_CATALOG_CONFLICT"));
    }

    @Test
    void successfulRequestsStillReturnNormalResponses() throws Exception {
        mockMvc.perform(get("/api/catalog/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Spring MVC"));

        mockMvc.perform(get("/api/billing/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.amount").value(750));
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

Các test này xác nhận **hành vi observable**, không chỉ kiểm tra class có annotation. Cụ thể:
1. Catalog lỗi 404 dùng RFC 9457 `ProblemDetail`, không nhận JSON của billing.
2. Billing lỗi 404 dùng body của billing, không nhận `ProblemDetail` catalog.
3. Local handler cho `CatalogConflictException` nhận 409, không bị advice global trả 422.
4. Các đường không lỗi vẫn phản hồi như bình thường.

`@WebMvcTest` chỉ dựng web MVC test slice; `@Import` bảo đảm hai advice có mặt trong context. Nếu dự án thực có Spring Security và CSRF, cần bổ sung cấu hình xác thực phù hợp ở các test có yêu cầu đó. Trong ví dụ chỉ dùng Spring Web + Starter Test nên không cần mở HTTP server thật.

## 9. Một advice HTML riêng với `ModelAndView`

Ứng dụng vừa có web page vừa có REST API có thể dùng advice dành riêng cho HTML controller:

~~~java
@ControllerAdvice(basePackageClasses = PageController.class)
public class HtmlPageAdvice {

    @ExceptionHandler(RecordMissingException.class)
    public ModelAndView missingPage(RecordMissingException ex) {
        ModelAndView mav = new ModelAndView("errors/not-found");
        mav.setStatus(HttpStatus.NOT_FOUND);
        mav.addObject("message", "Page does not exist");
        return mav;
    }
}
~~~

**Đây là mẫu minh họa**, không thuộc ứng dụng chạy đầy đủ ở phần 6: bạn cần tạo `PageController`, có view resolver/template `errors/not-found` và import `ModelAndView`, `HttpStatus`, annotation liên quan.

`basePackageClasses = PageController.class` chọn **cả package chứa** `PageController`, không chỉ class đó. Nếu cả controller API và HTML chung package, selector này có thể bao gồm cả API; khi cần giới hạn chính một controller, dùng `assignableTypes = PageController.class`.

Một cách tổ chức thường gặp:

- HTML controllers trong `com.example.web.pages` được `@ControllerAdvice(basePackages="com.example.web.pages")` xử lý bằng views.
- REST controllers trong `com.example.web.api` được `@RestControllerAdvice(basePackages="com.example.web.api")` xử lý bằng JSON/`ProblemDetail`.

Cấu trúc package này làm scope dễ đọc, nhưng cần kiểm thử vì package con và các selector OR có thể mở phạm vi rộng hơn dự tính.

## 10. `ResponseEntityExceptionHandler` và lỗi sẵn có của Spring MVC

Không phải tất cả lỗi HTTP đều là exception nghiệp vụ tự định nghĩa. Spring MVC còn phát sinh lỗi khi thiếu request parameter, sai method, JSON malformed, media type sai, validation thất bại, binding sai và những tình huống khác.

Spring Framework 6.x cung cấp **`ResponseEntityExceptionHandler`**, một lớp nền có thể được `@ControllerAdvice` kế thừa để xử lý nhiều exception của Spring MVC và lỗi có kiểu `ErrorResponse` theo hướng thống nhất. Nếu dùng nó, bạn có thể override những protected hook thích hợp để tùy chỉnh status/body, và khai báo thêm `@ExceptionHandler` cho exception nghiệp vụ của mình.

**Không nên** tạo một method `@ExceptionHandler(Exception.class)` ở mức ưu tiên cao chỉ để đổi mọi lỗi thành 400. Điều đó dễ che lỗi hệ thống thật, có thể can thiệp các status framework đã ánh xạ đúng, và tạo JSON contract sai cho client.

### `ProblemDetail` và RFC 9457

`ProblemDetail` có các field chuẩn như `type`, `title`, `status`, `detail`, `instance`. Spring MVC có thể lấy status từ `ProblemDetail`/response, và dùng media type `application/problem+json` khi Jackson xử lý dạng này.

Khi muốn thêm trường nghiệp vụ, có thể dùng `problem.setProperty("code", "CATALOG_NOT_FOUND")` và kiểm thử JSON render; không tự ý chèn stack trace hoặc SQL. Ví dụ:

~~~java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND, "Resource does not exist");
problem.setTitle("Resource not found");
problem.setProperty("code", "RESOURCE_NOT_FOUND");
~~~

Đoạn này là **minh họa trong method** (cần import). Spring có hỗ trợ các field mở rộng được serialize bên cạnh các field chuẩn của RFC 9457.

Spring Boot có cấu hình `spring.mvc.problemdetails.enabled` ở những phiên bản 3.x phù hợp để hỗ trợ Problem Details cho nhiều lỗi tích hợp. Tuy nhiên cách Boot tự cấu hình advice, thứ tự handler và những cấu hình đã có phụ thuộc phiên bản. **Không bật một property rồi mặc định mọi exception custom đều được map sang body mong muốn**; cần test hợp đồng API cụ thể.

### REST error JSON bằng `@ControllerAdvice` thuần có hợp lệ không?

Có. Trong ví dụ phần 6, `BillingErrorAdvice` dùng `@ControllerAdvice` mà vẫn trả `ResponseEntity<Map<String,String>>`. Return value được Spring xử lý thành body JSON nhờ `ResponseEntity`. `@RestControllerAdvice` chủ yếu giảm việc gắn `@ResponseBody` cho những method trả DTO/String làm body.

## 11. Khi exception handler không xử lý được

Các trường hợp sau cần xem xét luồng xử lý trước khi kết luận advice “không chạy”:

| Trường hợp | Vì sao advice có thể không xử lý | Cách xác minh |
| --- | --- | --- |
| Lỗi được ném trong Servlet filter hoặc Spring Security filter trước MVC | Không đi qua chính exception resolution của controller MVC | Kiểm tra Security filter chain, authentication entry point, access denied handler |
| Client ngắt kết nối hoặc response đã commit | Không còn khả năng ghi lại status/body bình thường | Xem log, thời điểm commit và cách truyền response |
| Lỗi task nền ngoài request | Không thuộc MVC handler execution | Dùng error handling của async executor, message consumer, scheduler |
| Controller không khớp selector | Advice không áp dụng cho handler đó | Kiểm tra package/type/annotation trên controller và quy tắc OR |
| Advice không được Spring đăng ký bean | Class nằm ngoài component scan hoặc profile/config loại bỏ | Kiểm tra application context và startup logs |
| Có local `@ExceptionHandler` | Local handler được ưu tiên trước advice | Kiểm tra controller/hierarchy |
| Advice khác có ưu tiên cao hơn | Handler ở advice ưu tiên trước đã khớp | Kiểm tra `@Order`, `Ordered`, exception root/cause |
| Handler trả view name trong REST | Dùng `@ControllerAdvice` + `String` thiếu body semantics | Trả `ResponseEntity`, gắn `@ResponseBody` hoặc dùng `@RestControllerAdvice` |

Một `@ExceptionHandler` có thể ném lại **chính exception** mà nó nhận được để từ chối xử lý trường hợp cụ thể; Spring MVC có cơ chế cho các resolver tiếp tục xem xét. Chỉ sử dụng kỹ thuật này khi cần, vì nó gây khó đọc và nên được kiểm thử.

## 12. Các sai lầm phổ biến về phạm vi

### 12.1. Nghĩ `@RestControllerAdvice` chỉ bắt lỗi từ `@RestController`

Sai: **phạm vi mặc định không phân biệt** REST hay HTML. Nếu muốn chỉ áp dụng cho `@RestController`, đặt `annotations = RestController.class` hoặc tổ chức package rồi cấu hình selector rõ.

### 12.2. Nghĩ hai selector được ghép AND

Sai: `basePackages="..."` cùng `annotations=RestController.class` tạo điều kiện OR. Điều này có thể làm advice rộng hơn mong muốn và trả JSON cho controller HTML. Cách khắc phục là dùng tiêu chí đơn nhất đủ chính xác hoặc tách controller/advice theo marker/nhóm.

### 12.3. Gắn `@Order` mà tưởng override local handler

Không. `@Order` dùng phân loại ưu tiên **giữa các advice**; một `@ExceptionHandler` cục bộ phù hợp trong controller được xét trước global advice. Nếu muốn thay đổi hành vi cục bộ, cần sửa controller/hierarchy tương ứng.

### 12.4. Handler generic bắt mọi lỗi và trả 200

Ví dụ phản diện:

~~~java
@ExceptionHandler(Exception.class)
public ResponseEntity<String> catchEverything(Exception ex) {
    return ResponseEntity.ok("Oops");
}
~~~

Đây là đoạn minh họa **không nên dùng**. Nó biến lỗi hệ thống thành thành công giả, ảnh hưởng monitor/client. Nếu xây fallback handler thực sự, chỉ nên đặt ở mức ưu tiên thấp, trả 500 khi thích hợp, log correlation ID, và không tiết lộ bí mật cho client.

### 12.5. Dùng exception message nội bộ làm public JSON

`ex.getMessage()` đôi khi chứa ID nội bộ, đường dẫn tệp, SQL, thông tin người dùng hoặc stack context. Trả message public đã kiểm duyệt, đồng thời ghi log có cấu trúc an toàn với trace/correlation ID riêng. `@RestControllerAdvice` không tự loại bỏ nội dung nhạy cảm của chuỗi bạn trả.

### 12.6. Tưởng advice biến mọi validation error thành cùng exception

Lỗi `@Valid @RequestBody`, `@Validated` trên method, thiếu `@RequestParam`, không parse được JSON và lỗi binding có thể tạo **những class exception khác nhau**. Nếu chuẩn hóa lỗi, xem exception thực tế và các hook của `ResponseEntityExceptionHandler`; tránh một handler bắt chung và bỏ qua status.

### 12.7. Dùng `@ControllerAdvice` cho lỗi của bất kỳ thread nào

Advice gắn với cơ chế Spring MVC. Scheduled job, `@Async` chạy tách khỏi request hoặc message listener có error handler riêng. Cần xử lý exception theo đúng execution context.

## 13. Câu hỏi ôn tập

**1. `@RestControllerAdvice` có tự động chỉ áp dụng cho `@RestController` không?**

Không. Nó có cùng scope mặc định của `@ControllerAdvice` và thêm ngữ nghĩa `@ResponseBody`. Muốn chỉ chọn REST controllers, dùng selector phù hợp.

**2. Nếu cả controller và advice có `@ExceptionHandler` xử lý cùng một exception, Spring ưu tiên cái nào?**

Handler cục bộ của controller được ưu tiên. Đây là hành vi quan trọng được test bằng `/api/catalog/conflict` trong ví dụ.

**3. Nếu một advice khai báo đồng thời `basePackages` và `annotations` thì Spring chọn controller thế nào?**

Ghép theo OR: khớp ít nhất một selector là đủ. Không phải AND.

**4. Tại sao `BillingErrorAdvice` dùng `@ControllerAdvice` mà vẫn trả JSON?**

Vì exception handler trả `ResponseEntity<Map<...>>`, vốn có ngữ nghĩa HTTP response body rõ ràng, không cần ngữ nghĩa mặc định `@ResponseBody` từ class.

**5. Nếu hai advice xử lý cùng exception và cùng áp dụng, yếu tố nào cần kiểm tra?**

Thứ tự `@Order`/`Ordered`, handler khớp root/cause, kiểu exception cụ thể, khả năng có local handler và việc advice thật sự nằm trong application context.

**6. Muốn chia sẻ `@InitBinder` nhưng không muốn mọi controller bị ảnh hưởng thì sao?**

Đặt `@InitBinder` trong advice có selector hẹp, hoặc giữ binder method trực tiếp tại controller. Kiểm thử các model attribute và converter/formatter được dùng thực tế.

## 14. Checklist áp dụng trong dự án

1. Phân nhóm rõ controller REST, HTML, API version và các domain nếu format lỗi khác nhau; đặt scope advice tương ứng.
2. Với REST trả DTO hoặc ProblemDetail, dùng `@RestControllerAdvice` hoặc `@ControllerAdvice` trả `ResponseEntity` rõ ràng.
3. Với view HTML, cân nhắc `@ControllerAdvice` + view resolver/`ModelAndView`.
4. Luôn nhớ selector mặc định là toàn cục và nhiều selector là OR; chọn `basePackageClasses` hoặc `assignableTypes` khi muốn tránh chuỗi package khó refactor.
5. Tránh handler cùng exception nằm rải rác mà không có quy tắc `@Order` và test rõ; local handler vẫn được ưu tiên trước global.
6. Phân biệt exception nghiệp vụ với exception của framework, filter/security và task nền; dùng đúng tầng xử lý.
7. Test đồng thời **status, content type, response JSON và phạm vi advice**; test trường hợp controller không bị áp dụng sai.
8. Trả thông tin lỗi public tối thiểu, không tiết lộ stack trace/SQL/secret; dùng correlation ID và log an toàn khi cần.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Controller Advice](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html)
- [Spring Framework 6.2 — `@ExceptionHandler`](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-exceptionhandler.html)
- [Spring Framework 6.2 — `@InitBinder`](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — REST Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework 6.2 Javadoc — `ControllerAdvice`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/annotation/ControllerAdvice.html)
- [Spring Framework 6.2 Javadoc — `RestControllerAdvice`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/annotation/RestControllerAdvice.html)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
