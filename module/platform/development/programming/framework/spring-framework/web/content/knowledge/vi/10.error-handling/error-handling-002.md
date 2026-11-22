# @ExceptionHandler ở controller và quy tắc chọn phương thức xử lý trong Spring MVC

> **Phạm vi:** Spring Web MVC trên Servlet stack, dùng Java 17+ và ví dụ Spring Boot 3.x / Spring Framework 6.2.x. Bài học tập trung vào `@ExceptionHandler` **đặt trong controller** và các quy tắc Spring chọn handler theo **phạm vi local/global, loại exception, root/cause, thứ tự advice và media type**. Những phần liên quan đến `@ControllerAdvice` được giải thích để hiểu thứ tự lựa chọn, không thay thế trọng tâm local `@ExceptionHandler`.

## 1. Bài toán: một exception cần biến thành HTTP response có ý nghĩa

Giả sử API truy cập sách:

```http
GET /api/books/13
Accept: application/json
```

Nếu sách không tồn tại, service có thể ném:

```java
throw new BookNotFoundException(13);
```

Nếu không chủ động xử lý, kết quả phụ thuộc các `HandlerExceptionResolver` mặc định, cấu hình Spring Boot và kiểu exception; với exception runtime không được nhận diện, thường đi đến lỗi 500. Nhưng "sách không tồn tại" là tình huống nghiệp vụ: API nên trả **404 Not Found** và body giải thích an toàn.

`@ExceptionHandler` cho phép một controller khai báo phương thức chuyên xử lý exception:

```java
@RestController
class BookController {

    @GetMapping("/api/books/{id}")
    public BookDto find(@PathVariable long id) {
        throw new BookNotFoundException(id);
    }

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<String> bookNotFound(BookNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body("Book not found");
    }
}
```

Đây là **đoạn minh họa**, cần định nghĩa `BookDto` và `BookNotFoundException` để biên dịch. Exception phát sinh khi Spring xử lý handler thuộc `BookController` sẽ được xem xét bởi local exception handler này trước các global advice thích hợp. Client nhận status 404 và body, thay vì một lỗi hệ thống không rõ nghĩa.

**Ba ý chính:**
1. `@ExceptionHandler` là annotation cho **method xử lý exception**, không phải annotation để ném exception.
2. Phương thức được chọn theo **exception được ném và cấu hình mapping**, không dựa vào tên method hay thứ tự các method xuất hiện trong file Java.
3. Method xử lý tự quyết định phản hồi: thường dùng `ResponseEntity<?>`, `ProblemDetail`, `@ResponseStatus` hoặc body/view tương ứng.

## 2. Cơ chế Spring MVC gọi @ExceptionHandler

Một luồng đơn giản:

```text
HTTP request
    |
    v
DispatcherServlet chọn @GetMapping/@PostMapping...
    |
    v
Gọi controller / xử lý đối số / conversion / validation
    |
    +------ thành công --------> return value -> HTTP response
    |
    +------ exception
               |
               v
       HandlerExceptionResolver chain
               |
               v
       ExceptionHandlerExceptionResolver
               |
               +-- tìm @ExceptionHandler local ở controller phù hợp
               |
               +-- nếu chưa xử lý: tìm @ExceptionHandler ở @ControllerAdvice
               |
               +-- áp dụng loại exception, cause, advice order, media type
               |
               v
          handler được chọn -> response
               |
       Nếu không xử lý được:
       các resolver khác / servlet container
```

`ExceptionHandlerExceptionResolver` là một `HandlerExceptionResolver` do Spring MVC cung cấp; còn có cơ chế khác như `ResponseStatusExceptionResolver` và `DefaultHandlerExceptionResolver`. Một exception không được method `@ExceptionHandler` nào nhận vẫn có thể được resolver khác xử lý hoặc đi tiếp ra servlet container.

Phạm vi xử lý là **vòng đời MVC request và những exception mà resolver nhìn thấy**. `@ExceptionHandler` trong controller không tự động bắt mọi lỗi phát sinh bên ngoài DispatcherServlet, chẳng hạn lỗi bị chặn hoàn toàn tại servlet filter trước khi vào MVC. Spring Security có cơ chế `AuthenticationEntryPoint` và `AccessDeniedHandler` trong filter chain; không mặc định giả định lỗi 401/403 đều đến controller advice.

## 3. Viết @ExceptionHandler local trong cùng controller

### 3.1. Chỉ định exception ở annotation

```java
@ExceptionHandler(IllegalArgumentException.class)
public ResponseEntity<String> badArgument(IllegalArgumentException ex) {
    return ResponseEntity.badRequest().body("Bad input");
}
```

`@ExceptionHandler(IllegalArgumentException.class)` đăng ký method xử lý `IllegalArgumentException` và các subtype phù hợp; đối số `ex` cho phép đọc exception đã khớp. Nếu controller có `@RestController`, response body được ghi như REST body; `ResponseEntity` cũng cho phép đặt status/header/body trực tiếp.

### 3.2. Suy luận exception type từ đối số

```java
@ExceptionHandler
public ResponseEntity<String> badArgument(IllegalArgumentException ex) {
    return ResponseEntity.badRequest().body("Bad input");
}
```

Khi annotation không chỉ rõ loại, Spring có thể lấy loại exception từ đối số method. Cách này gọn nếu handler đúng **một loại exception rõ ràng**. Tránh viết handler không có exception type có thể suy luận hoặc đối số quá chung khiến mapping không đúng mong đợi.

### 3.3. Một handler xử lý nhiều exception type

```java
@ExceptionHandler({
        IllegalArgumentException.class,
        IllegalStateException.class
})
public ResponseEntity<String> invalidState(RuntimeException ex) {
    return ResponseEntity.badRequest().body("Invalid request");
}
```

Đây là **một phương thức minh họa**, gộp hai trường hợp nếu chúng thật sự có cùng HTTP semantics. Loại đối số `RuntimeException` là superclass chung; đừng khai báo một đối số `IllegalArgumentException` khi annotation cũng đăng ký `IllegalStateException` rồi cho rằng Spring luôn có thể truyền exception khác loại vào tham số đó.

Giữ handler hẹp theo nghiệp vụ thường tốt hơn:

```java
@ExceptionHandler(BookNotFoundException.class)
ResponseEntity<ApiError> missing(BookNotFoundException ex) { /* ... */ }
```

Các dấu `/* ... */` biểu thị phần chưa triển khai trong **snippet thiết kế**, không phải chương trình chạy độc lập. Tránh catch `Exception.class` trong controller rồi biến mọi lỗi lập trình thành HTTP 400 hoặc 404.

## 4. Quy tắc 1: local handler được xét trước global advice

- **Local:** method `@ExceptionHandler` được khai báo trong chính `@Controller`/`@RestController` hoặc trong cấu trúc lớp cha áp dụng cho controller đó.
- **Global:** method `@ExceptionHandler` được khai báo trong bean `@ControllerAdvice` hay `@RestControllerAdvice`, có thể áp dụng cho nhiều controller theo selector.
- Với một controller đã được chọn để xử lý request, Spring MVC **xem xét các local exception handler trước** các handler toàn cục có thể áp dụng. Một local match có thể được chọn dù một advice khai báo handler cho cùng exception.

Ví dụ hai nơi đều xử lý `BookNotFoundException`:

```java
@RestController
class BookController {
    @ExceptionHandler(BookNotFoundException.class)
    ResponseEntity<String> local(BookNotFoundException ex) {
        return ResponseEntity.status(404).body("LOCAL");
    }
}

@RestControllerAdvice
class GlobalErrors {
    @ExceptionHandler(BookNotFoundException.class)
    ResponseEntity<String> global(BookNotFoundException ex) {
        return ResponseEntity.status(404).body("GLOBAL");
    }
}
```

Đây là **hai lớp minh họa**, không gồm các route gây lỗi. Khi lỗi `BookNotFoundException` phát sinh từ handler trong `BookController`, local method thường trả `LOCAL`; cùng lỗi phát sinh ở controller khác không có local match có thể được global method trả `GLOBAL`.

Điểm cần hiểu: `@Order` trên global advice **không đẩy advice lên trước local handler phù hợp**. Muốn thay policy cho controller cụ thể, cần sửa local handler hoặc phạm vi advice; không dùng `@Order` để tranh quyền với local match.

### 4.1. @ControllerAdvice và @RestControllerAdvice khác gì?

```java
@ControllerAdvice
class ErrorViews {
    @ExceptionHandler(BookNotFoundException.class)
    String page(BookNotFoundException ex) {
        return "book-not-found";
    }
}
```

Với `@ControllerAdvice`, chuỗi có thể là **tên view** (cần view resolver/template). Còn `@RestControllerAdvice` kết hợp `@ControllerAdvice` với `@ResponseBody`: kết quả method được ghi thành **HTTP response body** trừ các kiểu trả về có cơ chế riêng. Cả hai đều tham gia quy trình tìm exception handler. Đừng dùng `@ControllerAdvice` rồi tưởng `return "error"` luôn gửi body text `error`.

### 4.2. Thu hẹp advice theo phạm vi

```java
@RestControllerAdvice(basePackages = "com.example.api")
class ApiErrorAdvice {
    // Các @ExceptionHandler dành cho controller thuộc package mục tiêu.
}
```

Có thể dùng `basePackageClasses`, `annotations` hoặc `assignableTypes` để giới hạn tập controller áp dụng. Nếu đồng thời cung cấp nhiều selector, chúng được kết hợp theo **OR**: phù hợp ít nhất một selector là đủ, không phải bắt buộc thỏa tất cả. Advice mặc định áp dụng rộng; chỉ thêm selector khi có lý do kiến trúc rõ ràng.

## 5. Quy tắc 2: kiểu exception cụ thể hơn được ưu tiên trong cùng tập handler

Giả sử một controller có:

```java
@ExceptionHandler(RuntimeException.class)
ResponseEntity<String> general(RuntimeException ex) {
    return ResponseEntity.internalServerError().body("GENERAL");
}

@ExceptionHandler(IllegalArgumentException.class)
ResponseEntity<String> invalid(IllegalArgumentException ex) {
    return ResponseEntity.badRequest().body("SPECIFIC");
}
```

Khi `IllegalArgumentException` được ném trực tiếp, cả hai mapping có thể khớp theo quan hệ kế thừa, nhưng `IllegalArgumentException` là loại **cụ thể hơn**, nên Spring chọn handler trả `SPECIFIC`. Không có quy tắc "method viết trước được chạy trước". `ExceptionDepthComparator` được Spring dùng để so sánh mức độ gần với exception.

Ví dụ hierarchy:

```text
Throwable
  └── Exception
      └── RuntimeException
          └── IllegalArgumentException
```

Nếu có hai handler riêng cho `RuntimeException` và `Exception`, một `IllegalArgumentException` cũng thường chọn `RuntimeException` vì gần subtype hơn. Nếu có handler chính xác `IllegalArgumentException`, handler đó thắng trong cùng tập ứng viên hợp lệ.

**Tuy nhiên:** không định nghĩa hai handler trùng **chính xác một exception mapping và cùng media type** trong một controller/advice. Ví dụ:

```java
@ExceptionHandler(IllegalArgumentException.class)
ResponseEntity<String> first(IllegalArgumentException ex) { /* ... */ }

@ExceptionHandler(IllegalArgumentException.class)
ResponseEntity<String> second(IllegalArgumentException ex) { /* ... */ }
```

Đây là snippet **cố ý sai**, Spring có thể báo **ambiguous @ExceptionHandler method mapping** khi khởi tạo resolver/controller advice. Việc Java cho phép tên method khác nhau không giải quyết được trùng mapping. Phân biệt trường hợp này với hai handler có exception type **khác mức kế thừa** như ví dụ hợp lệ phía trên.

## 6. Quy tắc 3: root exception và cause exception

Một exception có thể bọc exception khác:

```java
throw new IllegalStateException(
        "Load failed",
        new BookNotFoundException(13));
```

Ở đây:
- **Root/top-level exception** được ném lên MVC là `IllegalStateException`.
- **Cause** nằm trong `getCause()` là `BookNotFoundException`.
- Từ Spring Framework 5.3, `@ExceptionHandler` có thể tìm match ở các mức cause lồng nhau, không chỉ mức gần nhất.

Giả sử controller có hai phương thức:

```java
@ExceptionHandler(IllegalStateException.class)
ResponseEntity<String> top(IllegalStateException ex) {
    return ResponseEntity.status(409).body("ROOT");
}

@ExceptionHandler(BookNotFoundException.class)
ResponseEntity<String> nested(BookNotFoundException ex) {
    return ResponseEntity.status(404).body("CAUSE");
}
```

Với ví dụ wrapper `IllegalStateException` phía trên, handler cho **root** được ưu tiên trong cùng controller/advice: trả `ROOT`. Ngược lại, nếu không có local handler nào khớp root, handler cho cause `BookNotFoundException` có thể được chọn và trả `CAUSE`.

Một góc cạnh quan trọng: một handler rất rộng như `@ExceptionHandler(Exception.class)` vẫn là **root match** đối với `IllegalStateException`, nên trong cùng advice nó có thể được ưu tiên hơn một handler khớp cause sâu dù latter là exception type cụ thể hơn. Đừng thiết kế dựa trên giả định "loại cụ thể nhất trong toàn bộ chuỗi cause luôn thắng". Spring đánh giá root và cause theo quy tắc lựa chọn thực tế.

### 6.1. Exception method nhận object nào?

Nếu method `@ExceptionHandler(BookNotFoundException.class)` được chọn nhờ cause, tham số `BookNotFoundException ex` thông thường chính là exception tương ứng trong cause chain. Khi dùng mapping nhiều loại hoặc một đối số superclass rất rộng, đối tượng được truyền có thể là root/wrapper trong những trường hợp hợp lệ. Tốt nhất cho handler có chữ ký **riêng, cụ thể** để giảm mơ hồ.

Không đặt business decisions chỉ dựa vào chuỗi `exception.getMessage()`; nên định nghĩa loại exception/domain code và thuộc tính có cấu trúc như ID bị thiếu.

## 7. Quy tắc 4: thứ tự giữa nhiều @ControllerAdvice

Khi các controller advice đều áp dụng cho request, Spring xử lý theo thứ tự ưu tiên của advice bean:

```java
@RestControllerAdvice
@Order(10)
class HighPriorityAdvice {
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<String> handle(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body("HIGH");
    }
}

@RestControllerAdvice
@Order(100)
class LowPriorityAdvice {
    @ExceptionHandler(Exception.class)
    ResponseEntity<String> handle(Exception ex) {
        return ResponseEntity.internalServerError().body("LOW");
    }
}
```

Đây là **hai advice minh họa độc lập**; khi `IllegalArgumentException` đến và controller không có local match, advice có `@Order(10)` được xem trước advice `@Order(100)`. **Giá trị thứ tự nhỏ hơn có độ ưu tiên cao hơn.**

Quy tắc root/cause tinh tế:

- **Bên trong một controller/advice**: root exception match được ưu tiên hơn cause match, cùng với độ cụ thể của type.
- **Giữa hai advice có priority khác nhau**: một **cause match trong advice ưu tiên cao hơn** có thể được chọn trước **root match ở advice ưu tiên thấp hơn**.
- Vì vậy nên đặt những handler xử lý root business exceptions chủ yếu trong advice có thứ tự phù hợp và thiết kế phạm vi advice tránh xung đột.

Bảng minh họa lựa chọn, giả định controller không có local handler:

| Tình huống | Ưu tiên thường được chọn |
| --- | --- |
| Advice A `@Order(1)` khớp `IllegalArgumentException` trực tiếp, Advice B `@Order(10)` khớp `Exception` | Advice A |
| Advice A `@Order(1)` khớp **cause** `BookNotFoundException`, Advice B `@Order(10)` khớp **root** `IllegalStateException` | Advice A có thể thắng nhờ thứ tự bean |
| Trong **cùng** advice có handler `Exception` và `BookNotFoundException`, root là `IllegalStateException` bọc cause `BookNotFoundException` | Root-match `Exception` thường thắng |
| Controller có local handler khớp, mọi advice đều có match | Local controller handler được xét trước |

Lưu ý các trường hợp đặc biệt như scoped advice beans có thể ảnh hưởng cách Spring áp dụng interface `Ordered`; không dựa vào may rủi về thứ tự quét class. Thiết lập explicit `@Order` khi nhiều advice có thể cùng xử lý ngoại lệ và dùng integration test xác minh kết quả.

## 8. Quy tắc 5: media type của exception handler (Spring Framework 6.2+)

Từ **Spring Framework 6.2**, annotation `@ExceptionHandler` có thuộc tính `produces`. Nhờ đó có thể đăng ký **hai handler cho cùng exception type** khi biểu diễn phản hồi khác nhau:

```java
// Snippet độc lập minh họa API Spring Framework 6.2+.
@ExceptionHandler(
        value = BookNotFoundException.class,
        produces = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<ErrorDto> json(BookNotFoundException ex) {
    return ResponseEntity.status(404)
            .body(new ErrorDto("NOT_FOUND", "Book not found"));
}

@ExceptionHandler(
        value = BookNotFoundException.class,
        produces = MediaType.TEXT_PLAIN_VALUE)
public ResponseEntity<String> text(BookNotFoundException ex) {
    return ResponseEntity.status(404)
            .body("Book not found");
}
```

Hai method trên **không bị coi là trùng hoàn toàn** vì mỗi method công bố một media type riêng. Header `Accept: application/json` sẽ hướng đến handler JSON; `Accept: text/plain` hướng đến handler text nếu content negotiation thỏa mãn. Với `Accept: */*` hoặc tập media type phức tạp, cần kiểm thử kết quả cụ thể theo thứ tự và negotiation hiện hành, không tùy tiện cam kết một handler.

`@ExceptionHandler(produces=...)` **không tồn tại** trong các phiên bản Spring Framework cũ hơn 6.2. Nếu dùng Boot 3.x nhưng thực tế phụ thuộc Spring Framework 6.0/6.1, code trên có thể **không compile**. Hãy kiểm tra dependency/version thực tế; nếu chưa thể nâng, dùng một handler quyết định response hợp lệ theo API sẵn có thay vì sao chép annotation mới.

Phân biệt:

- `@GetMapping(produces=...)`: chọn **controller endpoint** trước khi thực thi.
- `@ExceptionHandler(produces=...)`: chọn **error representation handler** trong quá trình xử lý exception (Spring 6.2+).
- `ResponseEntity.contentType(...)`: đặt **header response**; không đăng ký một exception mapping mới.
- `@RestControllerAdvice`: ảnh hưởng phạm vi/global body semantics, không thay thế chọn media type.

Nếu request `Accept` không tương thích với bất kỳ error representation nào, Spring có thể cần tới cơ chế fallback khác; đừng mặc định rằng exception luôn được trả dưới một JSON cụ thể bất kể `Accept`.

## 9. Quy tắc 6: rethrow để từ chối xử lý trường hợp đang xét

Một handler có thể nhận exception type rộng nhưng phát hiện instance hiện tại không thuộc phạm vi mong muốn:

```java
@ExceptionHandler(IllegalStateException.class)
public ResponseEntity<String> selective(IllegalStateException ex) {
    if (!"known-state".equals(ex.getMessage())) {
        throw ex; // Ném lại chính object ban đầu.
    }
    return ResponseEntity.status(409).body("Known conflict");
}
```

Đây là **snippet minh họa**. Việc ném lại **cùng exception instance** cho phép Spring xử lý như thể handler đã từ chối match, và phần còn lại của cơ chế exception resolution có thể tiếp tục. Không tạo exception mới chỉ để chuyển tiếp rồi giả định mọi metadata stacktrace/cause vẫn nguyên vẹn.

Tuy nhiên, rethrow dựa vào message là thiết kế mỏng manh; production nên có exception subtype hoặc error code có cấu trúc:

```java
class InventoryConflictException extends RuntimeException {
    InventoryConflictException(String message) {
        super(message);
    }
}
```

Tạo loại exception rõ nghĩa rồi viết `@ExceptionHandler(InventoryConflictException.class)` là cách dễ dự đoán hơn. Không sử dụng rethrow như một vòng lặp thử từng handler; nên biết rõ resolver nào chịu trách nhiệm.

## 10. @ExceptionHandler có thể nhận đối số và trả kiểu gì?

Các method này có cách resolve tham số và return value tương tự handler MVC, nhưng không phải tất cả input của handler bình thường đều có thể lấy lại. Request body có thể đã được đọc trước lúc phát sinh lỗi.

Các đối số hữu ích:

| Tham số | Dùng để làm gì |
| --- | --- |
| `BookNotFoundException ex` / `Exception ex` | Đọc object exception phù hợp |
| `HttpServletRequest request` | Xem URI, method, request headers; lưu ý namespace `jakarta.servlet.http.*` của Boot 3 |
| `WebRequest` / `NativeWebRequest` | Ngữ cảnh request mà không phụ thuộc servlet API ở mọi thao tác |
| `Locale locale` | Lấy locale theo resolver để quốc tế hóa error message |
| `Principal principal` | Xem identity nếu có; không tự đảm bảo quyền |
| `HandlerMethod handlerMethod` | Thông tin về controller handler gây lỗi khi có |
| `Model model` | Gắn dữ liệu cho error view (phương thức kiểu view) |

Return value phổ biến:

```java
@ExceptionHandler(BookNotFoundException.class)
ResponseEntity<ApiError> error(BookNotFoundException ex) {
    return ResponseEntity.status(404)
            .body(new ApiError("NOT_FOUND", "Book not found"));
}
```

Hoặc `ProblemDetail`:

```java
@ExceptionHandler(BookNotFoundException.class)
ProblemDetail problem(BookNotFoundException ex) {
    ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND, "Book not found");
    body.setTitle("Requested book not found");
    return body;
}
```

Trong Spring Framework 6+, `ProblemDetail` được hỗ trợ để render lỗi theo **RFC 9457**; status trong `ProblemDetail` quyết định HTTP status khi trả theo đường xử lý chuẩn của Spring. Có thể chọn `ResponseEntity<ProblemDetail>` nếu cần đặt header hoặc status tường minh. Với `@ResponseStatus(HttpStatus.NOT_FOUND)` và body DTO, annotation có thể đặt status cố định. Nếu method trả `String` trong `@Controller` thông thường không có `@ResponseBody`, chuỗi thường là tên view; trong `@RestControllerAdvice` hoặc method có `@ResponseBody` nó đại diện body text.

Đừng cố thêm `@RequestBody` vào exception handler để đọc lại toàn bộ request: stream có thể đã bị tiêu thụ hoặc lỗi parse body chính là nguyên nhân exception.

## 11. Ví dụ Spring Boot 3.x chạy được: local, global, generic và cause

Ví dụ chạy được với **Java 17+**, **Spring Boot 3.x + Spring Web**, dùng Spring Framework 6.x. Nó không phụ thuộc database, Security hay validation starter; tất cả response lỗi do code chủ động trả. Mục tiêu là kiểm tra **method nào được Spring chọn**, thể hiện rõ qua header `X-Error-Source` và body JSON.

Tạo dự án tại [Spring Initializr](https://start.spring.io/), chọn Java 17+ và dependency **Spring Web**. Thay toàn bộ nội dung file `src/main/java/com/example/demo/DemoApplication.java` bằng mã sau:

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

record ItemDto(long id, String name) {
}

record ApiError(String code, String message, String path) {
}

class ItemNotFoundException extends RuntimeException {
    private final long id;

    ItemNotFoundException(long id) {
        super("Item " + id + " not found");
        this.id = id;
    }

    long getId() {
        return id;
    }
}

@RestController
@RequestMapping("/api/items")
class ItemController {

    @GetMapping("/{id}")
    public ItemDto find(@PathVariable("id") long id) {
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }
        if (id == 13) {
            throw new ItemNotFoundException(id);
        }
        if (id == 99) {
            throw new IllegalStateException(
                    "wrapped lookup failure",
                    new ItemNotFoundException(id));
        }
        return new ItemDto(id, "item-" + id);
    }

    @ExceptionHandler(ItemNotFoundException.class)
    public ResponseEntity<ApiError> localNotFound(
            ItemNotFoundException ex,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "ITEM_NOT_FOUND",
                "Item " + ex.getId() + " does not exist",
                request.getRequestURI());

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .header("X-Error-Source", "controller")
                .body(body);
    }
}

@RestController
@RequestMapping("/api/other")
class OtherController {

    @GetMapping("/items/{id}")
    public ItemDto find(@PathVariable("id") long id) {
        if (id == 13) {
            throw new ItemNotFoundException(id);
        }
        if (id == 99) {
            throw new IllegalStateException("internal simulated failure");
        }
        return new ItemDto(id, "other-" + id);
    }
}

@RestControllerAdvice
class GlobalErrorAdvice {

    @ExceptionHandler(ItemNotFoundException.class)
    public ResponseEntity<ApiError> missing(
            ItemNotFoundException ex,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "ITEM_NOT_FOUND",
                "Item " + ex.getId() + " does not exist",
                request.getRequestURI());

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .header("X-Error-Source", "advice")
                .body(body);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiError> badArgument(
            IllegalArgumentException ex,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "BAD_ARGUMENT",
                "id must be positive",
                request.getRequestURI());

        return ResponseEntity.badRequest()
                .header("X-Error-Source", "advice")
                .body(body);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> internal(
            Exception ex,
            HttpServletRequest request) {

        // Không gửi ex.getMessage() cho lỗi hệ thống.
        ApiError body = new ApiError(
                "INTERNAL_ERROR",
                "Unexpected server error",
                request.getRequestURI());

        return ResponseEntity.status(
                        HttpStatus.INTERNAL_SERVER_ERROR)
                .header("X-Error-Source", "advice")
                .body(body);
    }
}
```

**Điểm quan trọng trong code:**
- `ItemController` có **một local** `@ExceptionHandler(ItemNotFoundException.class)`.
- `GlobalErrorAdvice` có ba handler: `ItemNotFoundException`, `IllegalArgumentException` và `Exception`. Các mapping này **không mơ hồ** vì chúng khác loại, có quan hệ specificity và Spring chọn method phù hợp.
- `OtherController` không có local exception handler, nên khi ném `ItemNotFoundException`, handler global sẽ nhận.
- `find(99)` trong `ItemController` cố ý ném wrapper `IllegalStateException` chứa cause `ItemNotFoundException`: local cause match được xét trước global handler rộng, nên vẫn trả lỗi từ controller.
- Handler generic `Exception.class` trả 500 với thông điệp đã kiểm soát; đây là ví dụ có chủ đích để phân biệt lỗi chưa biết. Trong ứng dụng thực tế, cần log exception với correlation ID và chính sách bảo mật; không trả stacktrace hoặc thông điệp nội bộ.
- Không có Security hoặc data store; tính đúng đắn business/persistence và authorization không nằm trong demo này.

### 11.1. Chạy chương trình

Trong thư mục gốc Spring Initializr project:

```bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell hoặc Command Prompt
mvnw.cmd spring-boot:run
```

Sau khi server khởi động trên port mặc định 8080, thử từng request. Dùng `curl -i` để thấy status và custom header; trong PowerShell dùng `curl.exe`.

### 11.2. Kết quả 1: request bình thường

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/items/7
```

HTTP status **200 OK**, body JSON dự kiến:

```json
{"id":7,"name":"item-7"}
```

Không có `X-Error-Source` vì không xảy ra exception và exception handler không chạy.

### 11.3. Kết quả 2: controller có local handler

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/items/13
```

Status **404 Not Found**, header:

```http
X-Error-Source: controller
```

Body:

```json
{"code":"ITEM_NOT_FOUND","message":"Item 13 does not exist","path":"/api/items/13"}
```

Dù global advice cũng có handler cho `ItemNotFoundException`, handler local thắng. Không phải do nó nằm phía trên trong source code Java.

### 11.4. Kết quả 3: lỗi cùng loại ở controller khác

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/other/items/13
```

Status **404**, `X-Error-Source: advice`; body:

```json
{"code":"ITEM_NOT_FOUND","message":"Item 13 does not exist","path":"/api/other/items/13"}
```

`OtherController` không có local handler phù hợp, nên advice xử lý.

### 11.5. Kết quả 4: exception đặc hiệu hơn generic

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/items/0
```

Status **400 Bad Request**, `X-Error-Source: advice`, body:

```json
{"code":"BAD_ARGUMENT","message":"id must be positive","path":"/api/items/0"}
```

Advice có cả `@ExceptionHandler(IllegalArgumentException.class)` và `@ExceptionHandler(Exception.class)`. Handler cụ thể hơn được chọn cho top-level `IllegalArgumentException`.

### 11.6. Kết quả 5: local match trên nested cause

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/items/99
```

Status **404**, `X-Error-Source: controller` và body:

```json
{"code":"ITEM_NOT_FOUND","message":"Item 99 does not exist","path":"/api/items/99"}
```

Top-level exception là `IllegalStateException`, cause là `ItemNotFoundException`. Controller chỉ có local mapping cho cause nên local handler khớp. Nếu thêm một local handler cho top-level `IllegalStateException` trong cùng controller, kết quả sẽ thay đổi theo quy tắc root match ưu tiên cause match.

### 11.7. Kết quả 6: fallback generic cho lỗi chưa biết

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/other/items/99
```

Status **500 Internal Server Error**, `X-Error-Source: advice`, body:

```json
{"code":"INTERNAL_ERROR","message":"Unexpected server error","path":"/api/other/items/99"}
```

Không có local handler tại `OtherController` và không có global handler cụ thể cho `IllegalStateException`, nên `@ExceptionHandler(Exception.class)` khớp root exception. Nội dung thật của exception `"internal simulated failure"` không bị gửi ra client.

Các header khác như `Date`, `Connection`, `Content-Type` và thứ tự field/headers phụ thuộc servlet container, message converter và phiên bản. JSON trên là **giá trị payload dự kiến**, không cần so khớp byte-for-byte thứ tự header.

## 12. Kiểm thử quy tắc lựa chọn bằng MockMvc

Để tránh "thêm handler mới rồi vô tình đổi method được chọn", test nên kiểm tra **status + header phân biệt nguồn xử lý + body**. Thêm dependency `spring-boot-starter-test` qua Spring Initializr hoặc `pom.xml`, rồi tạo file `src/test/java/com/example/demo/ExceptionSelectionTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ExceptionSelectionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void localHandlerWins() throws Exception {
        mvc.perform(get("/api/items/13"))
                .andExpect(status().isNotFound())
                .andExpect(header().string(
                        "X-Error-Source", "controller"))
                .andExpect(jsonPath("$.code")
                        .value("ITEM_NOT_FOUND"));
    }

    @Test
    void globalHandlerHandlesOtherController() throws Exception {
        mvc.perform(get("/api/other/items/13"))
                .andExpect(status().isNotFound())
                .andExpect(header().string(
                        "X-Error-Source", "advice"))
                .andExpect(jsonPath("$.path")
                        .value("/api/other/items/13"));
    }

    @Test
    void specificExceptionBeatsGenericInAdvice() throws Exception {
        mvc.perform(get("/api/items/0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BAD_ARGUMENT"));
    }

    @Test
    void localHandlerMatchesNestedCause() throws Exception {
        mvc.perform(get("/api/items/99"))
                .andExpect(status().isNotFound())
                .andExpect(header().string(
                        "X-Error-Source", "controller"));
    }

    @Test
    void genericAdviceHandlesUnknownFailure() throws Exception {
        mvc.perform(get("/api/other/items/99"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code")
                        .value("INTERNAL_ERROR"));
    }
}
```

Chạy bằng:

```bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
```

Test giả định dùng Spring Boot 3.x, không thêm Spring Security filter yêu cầu đăng nhập. Đây là kiểm thử cho **quy tắc chọn method**, không chứng minh mọi tình huống bảo mật hay tất cả lỗi framework. Khi đổi version Spring hoặc thêm advice, hãy bổ sung test cho trường hợp overlap mới.

## 13. Tình huống dễ nhầm: exception phát sinh trước khi controller method chạy

Không phải mọi lỗi HTTP đều do code `throw` trong thân method. Ví dụ:

- `@RequestBody` không parse được JSON có thể gây `HttpMessageNotReadableException` trong bước đọc body.
- `@Valid` thất bại có thể gây `MethodArgumentNotValidException`.
- Thiếu request parameter cần thiết có thể gây `MissingServletRequestParameterException`.
- Không khớp `consumes`/`produces` hoặc không tìm được handler có thể phát sinh lỗi trong các pha mapping/dispatch khác nhau.

Một exception resolver phù hợp **có thể** xử lý những lỗi này, nhưng local `@ExceptionHandler` không nhất thiết luôn áp dụng được: khi framework chưa xác định controller method, có thể không có handler cụ thể để tra cứu local mapping. Global advice hoặc resolver mặc định thường phù hợp cho error policy chung.

Khi muốn thay đổi **đúng một nhóm lỗi framework**, nên dùng `@RestControllerAdvice` hoặc mở rộng `ResponseEntityExceptionHandler` ở mức API. Nếu kế thừa `ResponseEntityExceptionHandler`, xem những method `protected` mà framework cung cấp để override; đừng thêm tùy tiện một `@ExceptionHandler` trùng với mapping rộng đã khai báo trong lớp cha, vì có thể gây mơ hồ.

Với `ResponseStatusException` hoặc exception type gắn `@ResponseStatus`, Spring có resolver chuyên dụng; một `@ExceptionHandler` phù hợp có thể can thiệp sớm hơn trong chuỗi resolver mặc định. Đừng coi annotation `@ResponseStatus` trên exception là ưu tiên tuyệt đối trong mọi tình huống có custom/global exception handlers.

## 14. Lựa chọn HTTP error response an toàn

| Trường hợp | Status phù hợp thường gặp | Gợi ý |
| --- | --- | --- |
| Tài nguyên không tồn tại | 404 | `ItemNotFoundException` → 404 |
| Tham số nghiệp vụ không hợp lệ | 400 hoặc 422 theo contract | Trả error code và field context an toàn |
| Trạng thái tài nguyên xung đột | 409 | `ConflictException` → 409 |
| Client thiếu xác thực | 401 | Thường xử lý qua Spring Security entry point nếu có |
| Client không được phép | 403 | Authorization handler; tránh lộ thông tin tài nguyên |
| Lỗi parse JSON / request body | 400 | Error advice chuyên cho parse/validation |
| Lỗi server không xác định | 500 | Thông điệp tổng quát, log nội bộ có correlation ID |

Không trả `ex.getMessage()` từ `SQLException`, `NullPointerException` hay stacktrace trực tiếp cho client. Với exception dự kiến có thông điệp an toàn, có thể lấy mã lỗi/ngữ cảnh đã lọc; với lỗi hệ thống, dùng message tổng quát. Đừng bắt mọi `Exception` rồi trả 200 hoặc 400 vì như vậy che giấu bug và làm sai semantics của HTTP.

Tạo error response thống nhất, ví dụ:

```json
{
  "code": "ITEM_NOT_FOUND",
  "message": "Item 13 does not exist",
  "path": "/api/items/13"
}
```

Hoặc theo chuẩn Problem Details:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Item 13 does not exist",
  "instance": "/api/items/13"
}
```

Đây là **ví dụ cấu trúc**, không cam kết mọi field xuất hiện mặc định nếu chưa đặt thông tin tương ứng. Với ứng dụng đa ngôn ngữ, thông điệp lỗi có thể lấy từ `MessageSource` dựa vào `Locale`; exception handler giữ vai trò chuyển lỗi thành HTTP response, không nên chứa toàn bộ business logic.

## 15. Các lỗi phổ biến khi khai báo @ExceptionHandler

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Handler local không chạy ở controller khác | Local chỉ áp cho controller/lớp cha tương ứng | Dùng advice nếu cần phạm vi chung |
| Global handler không chạy dù khớp type | Có local handler xử lý trước | Kiểm tra local mapping và inheritance |
| Handler `Exception.class` xử lý lỗi cause ngoài mong đợi | Root-match generic trong cùng advice ưu tiên cause | Thu hẹp generic hoặc thiết kế advice order |
| Một advice ưu tiên cao xử lý cause thay vì advice khác xử lý root | `@Order` giữa advice có ưu tiên riêng | Thiết kế priority có chủ đích, thêm test |
| Ứng dụng báo ambiguous handler mapping | Hai method trùng exception type và media type | Gộp/đổi mapping; dùng `produces` 6.2+ nếu biểu diễn khác |
| Chép `@ExceptionHandler(produces=...)` nhưng compile fail | Spring Framework dưới 6.2 | Nâng version hoặc dùng API được hỗ trợ |
| `return "error"` khiến tìm view | `@ControllerAdvice` không có `@ResponseBody` | `@RestControllerAdvice` hoặc `ResponseEntity` |
| Exception handler có status 200 khi trả body lỗi | Quên status | Dùng `ResponseEntity.status(...)` / `ProblemDetail` |
| Handler đọc `@RequestBody` lần nữa rồi lỗi | Body đã bị tiêu thụ | Dùng exception, request metadata và input được lưu có kiểm soát |
| Thêm Spring Security nhưng handler không bắt 401/403 | Lỗi bị xử lý ở filter chain trước MVC | Cấu hình Security entry point/denied handler |
| Handler không bắt lỗi do filter ném | Lỗi ngoài phạm vi DispatcherServlet | Xử lý tại filter hoặc chuyển giao đúng cơ chế |
| Đổi `@ExceptionHandler` nhưng status vẫn lạ | Handler resolver khác, error response có config riêng | Xem log resolver, test HTTP thực |

### 15.1. Trình tự debug một handler không được chọn

1. Xác định **root exception type** được ném vào MVC và đầy đủ `getCause()` chain (trong log server).
2. Xác định controller method có thực sự được match hay exception xảy ra trước mapping.
3. Liệt kê local `@ExceptionHandler` trong controller và hierarchy, đối chiếu class assignability.
4. Nếu không có local match, liệt kê global advices **áp dụng cho controller đó**, kể cả selectors.
5. Kiểm tra `@Order` giữa advice; trong từng advice xét root/cause/specificity.
6. Kiểm tra `produces` (Framework 6.2+), request `Accept`, response converter.
7. Kiểm tra trùng exception mappings, phương thức method signature có exception argument phù hợp.
8. Viết MockMvc test cố định status, error code và custom header để ngăn regression.

Nếu method xử lý **rethrow** chính exception, hãy tiếp tục xem resolver phía sau thay vì chỉ đọc log "handler đã được chọn" rồi kết luận lỗi đã xử lý xong.

## 16. Tự kiểm tra kiến thức

**Câu 1.** Controller và một `@RestControllerAdvice` đều có `@ExceptionHandler(IllegalArgumentException.class)`. Exception được ném từ controller đó; handler nào được thử trước?

**Đáp án:** Handler **local** trong controller được xét trước nếu khớp.

**Câu 2.** Cùng controller có mapping `RuntimeException` và `IllegalArgumentException`. Root exception là `IllegalArgumentException`. Ai được chọn?

**Đáp án:** Handler `IllegalArgumentException`, do mapping cụ thể hơn.

**Câu 3.** Root `IllegalStateException` chứa cause `ItemNotFoundException`; cùng advice có mapping `Exception` và `ItemNotFoundException`. Điều gì có thể gây bất ngờ?

**Đáp án:** `Exception` khớp **root**, còn `ItemNotFoundException` khớp **cause**. Root match trong một advice thường được ưu tiên, mặc dù loại của cause cụ thể hơn.

**Câu 4.** Advice A `@Order(1)` xử lý cause, Advice B `@Order(100)` xử lý root. Controller không có local handler. Có chắc B được chọn vì root không?

**Đáp án:** Không. Advice A ưu tiên cao hơn có thể xử lý cause trước, dù B có root mapping.

**Câu 5.** Hai method trong cùng controller đều khai báo `@ExceptionHandler(IllegalArgumentException.class)` với cùng media type có hợp lệ không?

**Đáp án:** Không; chúng có mapping mơ hồ. Từ Framework 6.2 có thể tách theo `produces` khác nhau nếu API thực sự cần nhiều error representations.

**Câu 6.** Vì sao `@ExceptionHandler(Exception.class)` trả 400 cho mọi exception là nguy hiểm?

**Đáp án:** Nó nuốt cả lỗi server, làm client hiểu sai và khiến monitoring không phân biệt được bug với input không hợp lệ.

**Câu 7.** Filter của Spring Security chặn request trước khi tới DispatcherServlet. Handler local có tự xử lý 403 đó không?

**Đáp án:** Không mặc định. Security filter thường xử lý bằng cơ chế authentication/authorization của nó; `@ExceptionHandler` hoạt động trong phạm vi xử lý exception của Spring MVC.

## 17. Tài liệu chính thức

- [Spring Framework 6.2 — Exceptions / @ExceptionHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-exceptionhandler.html): mapping types, root/cause, rethrow, `produces`, method arguments và return values.
- [Spring Framework 6.2 — Controller Advice](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html): local và global scope, `@RestControllerAdvice`, selector.
- [Spring Framework 6.2 — DispatcherServlet Exception Resolvers](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/exceptionhandlers.html): `HandlerExceptionResolver` chain và MVC default resolvers.
- [Spring Framework 6.2 — Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse` và `ResponseEntityExceptionHandler`.
- [Spring Framework 6.2 — `@ExceptionHandler` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/bind/annotation/ExceptionHandler.html): annotation parameters `value`, `exception` và `produces`.
- [Spring Framework — `@Order` and advice ordering](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/bind/annotation/ControllerAdvice.html): ưu tiên giữa các advice bean.

**Ghi nhớ:** Muốn dự đoán method `@ExceptionHandler` nào chạy, hãy xét theo đúng trình tự: **handler trong controller trước → global advice phù hợp theo thứ tự ưu tiên → đối chiếu root/cause và exception specificity trong từng nhóm → media type phù hợp → method trả HTTP response**. Viết exception types có ý nghĩa nghiệp vụ, tránh global catch-all trả sai status và kiểm thử cả các trường hợp trùng mapping, nested cause và advice overlap.
