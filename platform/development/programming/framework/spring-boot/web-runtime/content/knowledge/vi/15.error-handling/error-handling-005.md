# ResponseStatusException, @ResponseStatus và lựa chọn mã HTTP

Khi một API Spring Boot không thể hoàn thành một yêu cầu như dự kiến, **HTTP status code là một phần của hợp đồng giao tiếp**: nó cho client biết yêu cầu có hợp lệ không, người dùng có quyền không, tài nguyên có tồn tại không, trạng thái nghiệp vụ có xung đột không, hay server đang tạm thời quá tải. Chọn sai status khiến client retry không phù hợp, hiển thị thông báo sai, hoặc xử lý lỗi lẫn với phản hồi thành công.

Trong Spring Framework 6 / Spring Boot 3.3, các cách biểu đạt status thường gặp gồm **`ResponseStatusException`**, annotation **`@ResponseStatus`** trên method hoặc exception class, và **`ResponseEntity`** cùng `@ExceptionHandler`/`@RestControllerAdvice` khi cần một response body ổn định. Chúng có vai trò khác nhau; không có một công cụ tốt nhất cho mọi trường hợp.

Bài học thuộc nhóm **Xử lý lỗi** của **Spring Boot - web-runtime**, tập trung vào lựa chọn status và luồng exception của **Spring MVC/Servlet**. Cuối bài có so sánh với WebFlux, ví dụ Spring Boot 3.3.13 + Java 21 + Gradle và MockMvc tests. Các ví dụ dùng namespace `jakarta.*` tương thích Spring Boot 3.

## 1. HTTP status, exception và error body là ba thứ khác nhau

Ví dụ một HTTP response:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Không tìm thấy tài nguyên"
}
~~~

Phân biệt:

- **Status**: con số như 404 hoặc 409 trong HTTP response line, dùng cho client, proxy, monitoring và retry logic.
- **Exception**: đối tượng Java dùng để chuyển control flow trong ứng dụng; không bắt buộc tên exception phải tương ứng 1:1 với status.
- **Body**: dữ liệu mô tả lỗi cho client, có thể là `ProblemDetail`, JSON theo schema của tổ chức, hoặc trang HTML. Status **không tự bảo đảm body JSON**.

Một API tốt cần quyết định cả **HTTP status** lẫn **error representation**. Việc throw `new ResponseStatusException(HttpStatus.NOT_FOUND)` đủ để hướng tới status 404, nhưng **không có nghĩa body chắc chắn là một JSON object có mọi key bạn mong muốn**. Body phụ thuộc Spring MVC exception resolver, Spring Boot error handling, Problem Details configuration, content negotiation và đường đi thực tế của request.

Tương tự, một controller trả JSON có key `"status":404` nhưng HTTP status thật là 200 là hợp đồng kém: client/proxy vẫn xem đó là HTTP 200 trừ khi có xử lý đặc biệt. Hãy dùng HTTP status chính xác ở tầng giao thức.

## 2. Status code families: 2xx, 3xx, 4xx, 5xx

| Dải mã | Ý nghĩa khái quát | Nhận xét |
| --- | --- | --- |
| **2xx** | Request được xử lý thành công theo ngữ nghĩa của mã | 200, 201, 202, 204 |
| **3xx** | Redirect hoặc điều kiện về representation/cache | 301, 302, 303, 304, 307, 308 |
| **4xx** | Request không thể được phục vụ do điều kiện phía client/request/authorization/state | 400, 401, 403, 404, 405, 409, 415, 422, 429 |
| **5xx** | Server hoặc một thành phần phía upstream không xử lý được yêu cầu | 500, 502, 503, 504 |

Không nên quy mọi lỗi nghiệp vụ vào 500. Nếu một ID hợp lệ nhưng bản ghi không tồn tại, 404 phù hợp hơn 500. Nếu người dùng gửi JSON sai định dạng, 400 thường phù hợp hơn 500.

Ngược lại, không biến một lỗi database bất ngờ thành 400 chỉ để tránh cảnh báo. Lỗi không lường trước, chưa có quy tắc xử lý cụ thể thường nên được phân loại 500 và ghi log vận hành phù hợp.

**Không tự động retry mọi 5xx và không mặc định retry mọi 429.** Retry cần xét loại thao tác, `Retry-After`, thời hạn, idempotency, jitter/backoff và khả năng xung đột tác vụ.

## 3. Bảng chọn các mã HTTP phổ biến

| Mã | Tên | Khi cân nhắc | Lưu ý dễ nhầm |
| --- | --- | --- | --- |
| **200** | OK | GET thành công, hoặc POST thực thi và trả kết quả bình thường | Đừng trả 200 với body báo lỗi nhưng HTTP thành công |
| **201** | Created | Tài nguyên đã được tạo, thường kèm `Location` | Không dùng 201 nếu mới chỉ nhận vào hàng đợi |
| **202** | Accepted | Request đã được nhận để xử lý về sau nhưng chưa hoàn tất | Cần cơ chế theo dõi kết quả nếu có xử lý async thật |
| **204** | No Content | Thành công và không cần response body | 204 không mang message body |
| **400** | Bad Request | Input không hợp lệ, body malformed, validation không đạt hoặc query sai | Phân biệt với 422 theo chính sách API |
| **401** | Unauthorized | Chưa có hoặc không hợp lệ authentication credentials | Thường thuộc Security; header `WWW-Authenticate` quan trọng |
| **403** | Forbidden | Đã xác định request nhưng không được phép thực hiện | Không thay thế authorization bằng một check tùy ý ở controller |
| **404** | Not Found | Route/resource không có, hoặc tài nguyên có thể bị che sự tồn tại | Không mặc định là 500 |
| **405** | Method Not Allowed | Path có nhưng HTTP method không được hỗ trợ | Framework có thể sinh header `Allow` |
| **406** | Not Acceptable | Không thể tạo representation hợp `Accept` | Thường liên quan content negotiation |
| **409** | Conflict | Yêu cầu xung đột với trạng thái hiện tại của resource/hệ thống | Trùng unique value hoặc version conflict theo policy |
| **410** | Gone | Resource từng có nhưng đã bị loại bỏ vĩnh viễn theo thông tin server có | Không phải mọi ID không tồn tại đều là 410 |
| **412** | Precondition Failed | `If-Match`/`If-Unmodified-Since` không thỏa điều kiện | Quan trọng cho optimistic concurrency HTTP |
| **415** | Unsupported Media Type | `Content-Type` hoặc payload format không được chấp nhận | Khác 406, là request content |
| **422** | Unprocessable Content | Payload có cú pháp hợp lệ nhưng semantic rules không thể xử lý | Không bắt buộc dùng thay cho mọi Bean Validation 400 |
| **429** | Too Many Requests | Vượt rate/quota limit theo chính sách | Nên cân nhắc `Retry-After` và mô tả giới hạn |
| **500** | Internal Server Error | Lỗi server bất ngờ | Không lộ stack trace/SQL bí mật |
| **502** | Bad Gateway | Gateway/proxy nhận phản hồi upstream không hợp lệ | Không mặc định do controller phát |
| **503** | Service Unavailable | Server tạm thời chưa phục vụ do overload/maintenance | Có thể kèm `Retry-After` |
| **504** | Gateway Timeout | Gateway/proxy không nhận phản hồi upstream kịp thời | Không giống mọi timeout nội bộ của service |

`HttpStatus` là enum của Spring chứa các mã HTTP thông dụng. Spring Framework 6 còn có `HttpStatusCode` để đại diện cho status codes dạng interface, và `HttpStatusCode.valueOf(int)` cho trường hợp cần code dạng số. Không tự tạo nonstandard code khi không có contract rõ ràng.

### 3.1. Ba cặp hay nhầm

**400 so với 422:** JSON có cú pháp sai hoặc thiếu dữ liệu bắt buộc thường được Spring MVC trả 400 trong đường binding/validation mặc định. 422 có thể dùng theo policy khi JSON hợp lệ nhưng một quy tắc nghiệp vụ không thể thỏa. Không có luật mọi validation lỗi phải 422.

**401 so với 403:** 401 là tình huống authentication chưa đạt; 403 là không có quyền thực hiện. Với OAuth2/Bearer token, Spring Security và authentication entry point thường sinh 401 cùng header theo scheme; access denied handler có thể sinh 403. Controller không nên tự gửi status thiếu các security headers cần thiết nếu Security layer đang quản lý.

**404 so với 410:** 404 không khẳng định tài nguyên đã từng tồn tại hoặc bị xóa vĩnh viễn. Chỉ dùng 410 khi application có thông tin/contract đủ để kết luận resource đã bị thu hồi vĩnh viễn theo semantics đó.

## 4. ResponseStatusException: chọn status tại thời điểm chạy

Tên class đầy đủ:

~~~java
org.springframework.web.server.ResponseStatusException
~~~

Mặc dù package có `web.server`, Spring Framework hỗ trợ exception này ở **Spring MVC lẫn WebFlux**.

Trong controller/service adapter:

~~~java
if (id <= 0) {
    throw new ResponseStatusException(
        HttpStatus.BAD_REQUEST,
        "id must be positive"
    );
}

if (!repository.existsById(id)) {
    throw new ResponseStatusException(
        HttpStatus.NOT_FOUND,
        "resource not found"
    );
}
~~~

Đây là **code fragment** giả định có biến `id` và `repository`. Lựa chọn trạng thái được quyết định **dynamically**, theo dữ liệu request và kết quả xử lý.

Một số constructors Spring 6.1:

~~~java
new ResponseStatusException(HttpStatus.NOT_FOUND);
new ResponseStatusException(HttpStatus.NOT_FOUND, "book not found");
new ResponseStatusException(
    HttpStatus.BAD_REQUEST,
    "input invalid",
    cause
);
~~~

`cause` là một `Throwable` đã có. Chỉ truyền cause hợp lý để bảo toàn chẩn đoán bên trong; không trả nguyên nhân SQL, credentials hoặc exception message nhạy cảm cho client.

### 4.1. ResponseStatusException kế thừa ErrorResponseException

Trong Spring 6.1, `ResponseStatusException` extends `ErrorResponseException`, triển khai `ErrorResponse`. Nó có status, headers và một `ProblemDetail` body ở cấp abstraction. Lý do (`reason`) của exception thường được ánh xạ mặc định vào `detail` của `ProblemDetail`.

**Nhưng `exception.getBody()` và JSON thật trên HTTP không luôn đồng nhất**: việc resolver nào xử lý exception, Boot có bật Problem Details không, có `@ControllerAdvice` custom không và response đã commit chưa đều có thể ảnh hưởng. Đừng viết client contract dựa trên giả định “throw exception thì JSON body luôn chứa reason”.

### 4.2. Ví dụ trong Mono/Flux của WebFlux

Trong reactive chain, lỗi nên được phát qua publisher:

~~~java
return service.findBook(id)
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(
            HttpStatus.NOT_FOUND,
            "book not found"
        )
    ));
~~~

Đây là fragment WebFlux, giả định `service.findBook(id)` trả `Mono<Book>`. Không tự `subscribe()` hay `block()` chỉ để biến exception thành HTTP response.

**Response đã commit:** nếu một stream đã ghi header/body rồi mới phát lỗi, status cũ không thể được thay hồi tố thành 404 hoặc 500. Client cần hiểu protocol streaming riêng và server phải cleanup tài nguyên.

## 5. @ResponseStatus trên controller method: trạng thái tĩnh

Ví dụ:

~~~java
@PostMapping("/validate-only")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void validateOnly(@Valid @RequestBody CheckRequest request) {
    // Chỉ kiểm tra điều kiện, không có body trả về.
}
~~~

Giá trị status cố định và gắn trực tiếp vào method. Với method trả `void` thành công, 204 mô tả rõ **không có body**. Nếu method throw exception, status lỗi có thể đến từ exception handling thay vì 204.

Có thể viết:

~~~java
@ResponseStatus(code = HttpStatus.CREATED)
@PostMapping("/items")
public ItemView create(@RequestBody CreateItem input) { ... }
~~~

Đoạn này chỉ là **fragment minh họa**; dùng 201 khi tài nguyên **đã thực sự được tạo**, còn `Location` nên được xây dựng phù hợp. Nếu cần status/headers khác nhau theo nhánh xử lý hoặc cần `Location`, `ResponseEntity` thường biểu đạt contract tốt hơn.

### 5.1. Không đặt @ResponseStatus trên mọi method theo phản xạ

- Với `@RestController` trả DTO bình thường, 200 là mặc định phổ biến.
- Với POST tạo resource, 201 có thể hợp lý nếu đã ghi thành công.
- Với operation đã hoàn tất nhưng không có body, 204 hợp lý.
- Với request **được nhận chờ xử lý** ở hàng đợi thật, 202 phù hợp.
- Với nhánh thất bại, throwing exception có status rõ ràng thường tốt hơn giả vờ trả một DTO thành công.

Annotation dùng một mã **cố định** cho method hoặc exception class. Nếu cùng method có thể trả 200, 201 hoặc 409 theo kết quả runtime, dùng `ResponseEntity`/exception handling phù hợp thay vì ép một status cho mọi trường hợp.

### 5.2. @ResponseStatus trên controller class có thể ảnh hưởng cả class

Annotation còn có thể đặt trên class; status có thể được áp dụng tới những request mapping/exception handler methods trừ khi method có override. Điều này dễ gây bất ngờ khi class có nhiều route với semantics khác nhau. Với REST controller có GET/POST/DELETE, ưu tiên đặt status **ở method cụ thể** thay vì class-level status chung.

## 6. @ResponseStatus trên exception class: mapping cố định

Ví dụ một business exception có status không đổi:

~~~java
@ResponseStatus(HttpStatus.GONE)
public class RetiredResourceException extends RuntimeException {
    public RetiredResourceException() {
        super("Resource is retired");
    }
}
~~~

Khi exception này không bị advice khác bắt/trả thành response khác, `ResponseStatusExceptionResolver` có thể chuyển nó thành 410 Gone. Điểm mạnh: status gắn với **loại exception**, không phải từng chỗ throw.

Nhược điểm: domain exception bị gắn chặt với HTTP semantics. Nếu domain layer còn dùng trong batch, messaging, CLI hoặc thư viện độc lập, không nhất thiết nên thêm annotation web lên exception chung. Một `@RestControllerAdvice` có thể ánh xạ domain exception sang HTTP error contract ở tầng web mà không buộc domain code biết `HttpStatus`.

### 6.1. Đặt reason trong @ResponseStatus cần đặc biệt cẩn trọng

Ví dụ nên tránh trong REST API:

~~~java
@ResponseStatus(
    code = HttpStatus.NOT_FOUND,
    reason = "Book not found"
)
public class BookMissingException extends RuntimeException {
}
~~~

Theo Javadoc Spring Framework 6.1, với **annotation trên exception class** hoặc **`reason` không rỗng**, Spring MVC có thể gọi `HttpServletResponse.sendError(...)`. Sau `sendError`, response được coi là hoàn tất đối với đường xử lý đó; Servlet container hoặc Boot error dispatch có thể tạo **trang HTML hoặc JSON lỗi mặc định**, thay vì body bạn định serialize từ controller.

Vì vậy, nếu muốn API luôn trả JSON problem document ổn định, đừng dựa vào `reason` annotation. Dùng `@ExceptionHandler` trả `ProblemDetail` hoặc `ResponseEntity` với content type/fields được test.

**Khác biệt quan trọng:** `@ResponseStatus(HttpStatus.NO_CONTENT)` trên một method thành công, không có `reason`, có thể hoạt động cùng return value thông thường; nhưng thêm non-empty `reason` có thể khiến return body bị bỏ qua do `sendError`.

## 7. @ResponseStatus so với ResponseStatusException và ResponseEntity

| Cách | Chọn status | Body/schema | Phù hợp khi |
| --- | --- | --- | --- |
| `@ResponseStatus` trên method | Cố định theo method | Return handling bình thường khi không dùng reason đặc biệt | 201/202/204 cố định, rõ semantics |
| `@ResponseStatus` trên exception | Cố định theo exception class | Có thể đi qua `sendError`/Boot error path | Một exception rất cụ thể luôn có status không đổi |
| `ResponseStatusException` | Chọn lúc chạy theo nhánh | Body không được bảo đảm ổn định nếu không thiết kế handler/config | Điều kiện request khác nhau như 400/404 đơn giản |
| `ResponseEntity<T>` | Chọn per response | Kiểm soát status, headers và body | 201 + Location, 204, 200 có headers, nhiều nhánh |
| `@RestControllerAdvice` + `@ExceptionHandler` | Chọn theo exception/domain mapping | Kiểm soát schema chung, ProblemDetail, localization | API cần error contract nhất quán trên nhiều controllers |

Một số tình huống nên chọn:

- **Lệnh kiểm tra input trả 204**: `@ResponseStatus(NO_CONTENT)` trên method có thể đơn giản và rõ ràng.
- **Tài nguyên không tìm thấy do ID**: `ResponseStatusException(NOT_FOUND)` có thể đủ khi không bắt buộc body lỗi riêng.
- **Thao tác tạo tài nguyên**: `ResponseEntity.created(location).body(dto)` thể hiện chính xác 201/Location/body.
- **Conflict theo nghiệp vụ kèm mã lỗi ổn định**: domain exception + `@RestControllerAdvice` tạo `ProblemDetail`.
- **Spring Security 401/403**: nên cấu hình Security entry point/access denied handler thay vì throw ngẫu nhiên trong controller.

### 7.1. ResponseEntity có thể định nghĩa status/headers tường minh

~~~java
return ResponseEntity
    .created(URI.create("/api/books/42"))
    .body(new BookView(42L, "Java 21"));
~~~

Đây là code fragment trong một method trả `ResponseEntity<BookView>`; dùng khi resource được tạo thật. Ví dụ Location đang là relative URI; với public API đòi absolute URI, hãy dùng URL builder hiểu context path và forwarded headers đáng tin, tránh hard-code localhost hoặc internal host.

Với không có body:

~~~java
return ResponseEntity.noContent().build();
~~~

Không cần `@ResponseStatus` nữa. Nếu code vừa có `@ResponseStatus` vừa tự trả `ResponseEntity`, framework có quy tắc ưu tiên; tránh cấu hình trùng và gây khó hiểu khi review.

## 8. Exception đi qua Spring MVC như thế nào?

Luồng giản lược khi controller hoặc binding phát lỗi:

~~~text
HTTP request
     |
     v
DispatcherServlet / HandlerAdapter
     |
     +-- request mapping / binding / validation
     |      |
     |      +-- có thể ném framework exception
     |
     +-- controller / service
            |
            +-- có thể ném custom exception
            |
            v
HandlerExceptionResolver chain
     |
     +-- ExceptionHandlerExceptionResolver
     |      -> @ExceptionHandler ở controller / @ControllerAdvice
     |
     +-- ResponseStatusExceptionResolver
     |      -> @ResponseStatus / ResponseStatusException
     |
     +-- DefaultHandlerExceptionResolver
            -> một số lỗi Spring MVC mặc định
     |
     v
HTTP status + headers + body hoặc error dispatch
~~~

Đây là **sơ đồ khái niệm về cơ chế mặc định**, không phải cam kết thứ tự cho mọi custom resolvers; các bean resolver có `Ordered`, cấu hình riêng và cách kết hợp. Nếu một `@ExceptionHandler` bắt đúng exception và trả response, status cuối cùng có thể do handler đó quyết định — annotation trên exception không phải “mệnh lệnh bất biến” vượt qua mọi resolver.

Một số lỗi được Spring xử lý trước khi tới controller:

- Không có mapping thích hợp → thường 404.
- Path có nhưng method sai → thường 405.
- `Content-Type` không phù hợp → 415.
- `Accept` không thể đáp ứng → 406.
- JSON parse lỗi, thiếu body bắt buộc hoặc validation thất bại → thường 400.
- Authentication/authorization thất bại có thể bị **Spring Security filter chain** xử lý trước MVC.

**Không cần throw ResponseStatusException cho mọi lỗi framework đã nhận diện chính xác**. Chỉ thêm handler khi muốn tùy biến body, logging hoặc policy; giữ lại đúng status và required HTTP headers.

## 9. Dùng ProblemDetail để chuẩn hóa error body

Spring Framework 6 hỗ trợ `org.springframework.http.ProblemDetail` và `org.springframework.web.ErrorResponse` cho error representation theo RFC 9457. Các trường chuẩn thường gặp:

| Field | Vai trò |
| --- | --- |
| `type` | URI định danh loại vấn đề; mặc định có thể là `about:blank` |
| `title` | Tên ngắn mô tả lớp lỗi |
| `status` | HTTP status number trong problem document |
| `detail` | Diễn giải lỗi dành cho client (không lộ bí mật) |
| `instance` | URI nhận diện trường hợp lỗi cụ thể nếu ứng dụng cung cấp |

Body mẫu:

~~~json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "A book with this title already exists",
  "code": "TITLE_ALREADY_EXISTS"
}
~~~

`code` là **extension property** của API riêng, không phải field bắt buộc của RFC. Spring hỗ trợ thêm properties qua `ProblemDetail.setProperty(...)`; Jackson integration thường viết các extension properties ở top-level.

### 9.1. Không dựa vào JSON error mặc định cho một contract chặt

Trong Spring Boot 3.3, property:

~~~yaml
spring:
  mvc:
    problemdetails:
      enabled: true
~~~

có thể bật auto-configuration liên quan Problem Details cho các MVC exceptions hỗ trợ. Nhưng tùy cấu hình, `@ControllerAdvice` do ứng dụng tạo, `@ResponseStatus` exception và đường error dispatch, các trường/format có thể khác nhau. **Không tự kết luận mọi lỗi đều có ProblemDetail chỉ vì bật property.**

Nếu tổ chức cần một error schema thống nhất, viết exception handlers/`ResponseEntityExceptionHandler` thích hợp, xác định precedence rõ ràng và test toàn bộ các lỗi cần hỗ trợ.

### 9.2. Lỗi không mong đợi không nên lộ chi tiết

Đừng đưa message gốc của `SQLException`, stack trace, đường dẫn file tuyệt đối, SQL query, token, thông tin người dùng khác hoặc chi tiết hạ tầng vào `ProblemDetail.detail`. Dùng thông điệp an toàn cho client, mã lỗi ổn định, và correlation ID để hỗ trợ điều tra trong server logs.

`ProblemDetail.status` phải tương ứng HTTP status thực. Nếu mã body là 409 mà HTTP line 200, client/proxy sẽ nhận tín hiệu trái nhau.

## 10. Ví dụ chạy được: Spring Boot MVC + ba cách chọn status

Demo dưới đây có:

1. `ResponseStatusException` trả 400 khi ID sai, 404 khi ID không tồn tại.
2. `@ResponseStatus(HttpStatus.GONE)` trên exception class trả 410 khi tài nguyên đã ngừng cung cấp.
3. `@ResponseStatus(NO_CONTENT)` trên method POST validation-only trả 204.
4. `@RestControllerAdvice` trả 409 + `ProblemDetail` khi title xung đột.
5. MockMvc tests kiểm tra status và schema JSON cho trường hợp advice.

Project demo không dùng database hoặc tạo tài nguyên thật; các nhánh dữ liệu là giả lập có chủ đích. Không sử dụng ví dụ này để khẳng định một mã 201 Created nếu không thực sự tạo resource.

~~~text
http-error-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/httperror/
    │   ├── HttpErrorDemoApplication.java
    │   ├── BookController.java
    │   ├── RetiredBookException.java
    │   ├── DuplicateTitleException.java
    │   └── ApiExceptionHandler.java
    └── test/java/com/example/httperror/
        └── BookControllerTest.java
~~~

### 10.1. Gradle build và entrypoint

**settings.gradle**

~~~groovy
rootProject.name = 'http-error-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/java/com/example/httperror/HttpErrorDemoApplication.java**

~~~java
package com.example.httperror;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpErrorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpErrorDemoApplication.class, args);
    }
}
~~~

`spring-boot-starter-web` thông thường dùng embedded Tomcat/Spring MVC và Jackson JSON. `spring-boot-starter-validation` bổ sung Jakarta Bean Validation. Không cần cài Tomcat độc lập.

### 10.2. Hai exception classes của ví dụ

**src/main/java/com/example/httperror/RetiredBookException.java**

~~~java
package com.example.httperror;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.GONE)
public class RetiredBookException extends RuntimeException {
    public RetiredBookException() {
        super("This book is retired");
    }
}
~~~

Annotation chỉ khai báo status, **không đặt `reason`**. Với đường xử lý mặc định phù hợp, framework trả 410. Không giả định body lỗi có JSON keys ổn định.

**src/main/java/com/example/httperror/DuplicateTitleException.java**

~~~java
package com.example.httperror;

public class DuplicateTitleException extends RuntimeException {
    public DuplicateTitleException() {
        super("Book title already exists");
    }
}
~~~

Exception thứ hai **không phụ thuộc vào Spring HTTP status**. Web adapter sẽ ánh xạ nó thành 409 và body nhất quán trong `ApiExceptionHandler`.

### 10.3. Controller có các nhánh lỗi rõ ràng

**src/main/java/com/example/httperror/BookController.java**

~~~java
package com.example.httperror;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/books")
public class BookController {

    public record Book(long id, String title) {
    }

    public record TitleRequest(@NotBlank String title) {
    }

    @GetMapping("/{id}")
    public Book find(@PathVariable long id) {
        if (id <= 0) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "id must be positive"
            );
        }
        if (id != 1L) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND,
                "book not found"
            );
        }
        return new Book(1L, "Java 21");
    }

    @GetMapping("/retired")
    public Book retired() {
        throw new RetiredBookException();
    }

    @PostMapping(
        path = "/validate-only",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void validateOnly(@Valid @RequestBody TitleRequest input) {
        // Chỉ validate; không tạo/sửa bản ghi.
    }

    @PostMapping(
        path = "/check-title",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, Boolean> checkTitle(
            @Valid @RequestBody TitleRequest input) {
        // Mô phỏng trạng thái nghiệp vụ; không dùng database.
        if ("Java 21".equalsIgnoreCase(input.title())) {
            throw new DuplicateTitleException();
        }
        return Map.of("available", true);
    }
}
~~~

**Phân tích:**

- `GET /api/books/1` → 200, trả JSON từ record `Book`.
- `GET /api/books/0` → 400; vì ID không hợp lệ.
- `GET /api/books/9` → 404; vì không tìm thấy trong dữ liệu demo.
- `GET /api/books/retired` → 410; exception class được gắn `@ResponseStatus(GONE)`.
- `POST /api/books/validate-only`, body JSON hợp lệ → 204, không có response body.
- `POST /api/books/check-title` với title trùng trong demo → custom exception, được advice xử lý thành 409.
- `POST /api/books/check-title` với title khác → 200 và JSON `{"available":true}`.
- Title rỗng/whitespace hoặc null → `@NotBlank` validation thường dẫn đến 400.

Không dùng in-memory check như ví dụ để bảo đảm uniqueness trong production: hai requests cạnh tranh có thể qua check đồng thời. Với dữ liệu thật, database unique constraint/transaction và exception mapping có tính đến race condition là cần thiết.

### 10.4. @RestControllerAdvice trả ProblemDetail có schema ổn định

**src/main/java/com/example/httperror/ApiExceptionHandler.java**

~~~java
package com.example.httperror;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(DuplicateTitleException.class)
    public ResponseEntity<ProblemDetail> duplicateTitle(
            DuplicateTitleException ex) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "A book with this title already exists"
        );
        problem.setTitle("Conflict");
        problem.setProperty("code", "TITLE_ALREADY_EXISTS");

        return ResponseEntity
            .status(HttpStatus.CONFLICT)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
~~~

Với `DuplicateTitleException`, status nằm ở **HTTP response thực** (`ResponseEntity.status(CONFLICT)`) và trong `ProblemDetail.status`. Body dùng `application/problem+json` cùng extension field `code` giúp client xử lý ổn định.

`ex` được nhận để biết loại lỗi nhưng cố ý **không gửi `ex.getMessage()` trực tiếp** ra client. Điều này giảm nguy cơ lộ thông tin từ backend. Trong sản phẩm thật, có thể log lỗi an toàn kèm correlation ID nhưng không log dữ liệu cá nhân nhạy cảm.

### 10.5. Chạy và thử với curl

Với JDK 21 và Gradle wrapper tương thích:

~~~bash
./gradlew bootRun
~~~

Nếu dự án chưa có wrapper nhưng đã cài Gradle tương thích, có thể tạo:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Request thành công:

~~~bash
curl -i http://localhost:8080/api/books/1
~~~

Kỳ vọng HTTP 200 và JSON:

~~~json
{"id":1,"title":"Java 21"}
~~~

Hai trường hợp throw `ResponseStatusException`:

~~~bash
curl -i http://localhost:8080/api/books/0
curl -i http://localhost:8080/api/books/9
~~~

Kỳ vọng lần lượt 400 và 404. **Không gán cố định JSON body** cho hai response vì đường lỗi mặc định có thể khác theo cấu hình và môi trường.

Exception gắn `@ResponseStatus`:

~~~bash
curl -i http://localhost:8080/api/books/retired
~~~

Kỳ vọng 410 Gone. Status là điều quan trọng trong demo này; không tự khẳng định body chứa message Java của exception.

Method gắn `@ResponseStatus(NO_CONTENT)`:

~~~bash
curl -i -X POST http://localhost:8080/api/books/validate-only \
  -H "Content-Type: application/json" \
  -d '{"title":"Clean Code"}'
~~~

Kỳ vọng **204 No Content**, không có response body.

Conflict do advice xử lý:

~~~bash
curl -i -X POST http://localhost:8080/api/books/check-title \
  -H "Content-Type: application/json" \
  -H "Accept: application/problem+json" \
  -d '{"title":"Java 21"}'
~~~

Response dự kiến chứa 409, `Content-Type: application/problem+json` và body tương đương:

~~~json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "A book with this title already exists",
  "code": "TITLE_ALREADY_EXISTS"
}
~~~

`instance` và các headers khác có thể được thêm tùy framework/configuration; thứ tự JSON object keys không có ý nghĩa. Khi viết API thật, test HTTP status và JSON field values thay vì so sánh nguyên văn toàn bộ response.

## 11. MockMvc tests: kiểm tra status và body

**src/test/java/com/example/httperror/BookControllerTest.java**

~~~java
package com.example.httperror;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validBookHas200() throws Exception {
        mvc.perform(get("/api/books/1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Java 21"));
    }

    @Test
    void responseStatusExceptionReturns400Or404() throws Exception {
        mvc.perform(get("/api/books/0"))
            .andExpect(status().isBadRequest());

        mvc.perform(get("/api/books/9"))
            .andExpect(status().isNotFound());
    }

    @Test
    void annotatedExceptionReturns410() throws Exception {
        mvc.perform(get("/api/books/retired"))
            .andExpect(status().isGone());
    }

    @Test
    void annotatedMethodReturns204WithNoBody() throws Exception {
        mvc.perform(post("/api/books/validate-only")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Clean Code\"}"))
            .andExpect(status().isNoContent())
            .andExpect(content().string(""));
    }

    @Test
    void adviceReturns409WithProblemDetails() throws Exception {
        mvc.perform(post("/api/books/check-title")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_PROBLEM_JSON)
                .content("{\"title\":\"Java 21\"}"))
            .andExpect(status().isConflict())
            .andExpect(header().string(
                "Content-Type", MediaType.APPLICATION_PROBLEM_JSON_VALUE))
            .andExpect(jsonPath("$.status").value(409))
            .andExpect(jsonPath("$.title").value("Conflict"))
            .andExpect(jsonPath("$.code")
                .value("TITLE_ALREADY_EXISTS"));
    }

    @Test
    void blankTitleIsBadRequest() throws Exception {
        mvc.perform(post("/api/books/check-title")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unsupportedMethodGets405() throws Exception {
        mvc.perform(put("/api/books/1"))
            .andExpect(status().isMethodNotAllowed());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Test dùng `@SpringBootTest` + `@AutoConfigureMockMvc` để nạp application context và MVC test infrastructure, **không bắt buộc mở TCP socket Tomcat thật**. Nó kiểm tra exception resolver và response body tại Spring web layer; không thay thế integration test qua reverse proxy/security gateway.

Cẩn trọng với assertion exact header `Content-Type` nếu ứng dụng có converter/config thêm charset. Đoạn code cố ý set `application/problem+json` trong advice; nếu cần mềm dẻo hơn trong những môi trường custom, có thể dùng `contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)`.

**Không kiểm tra nội dung reason của `ResponseStatusException` bằng JSONPath trong test này.** Các response 400/404 phụ thuộc error configuration; bài minh họa status contract trước, body ổn định được đảm bảo bằng advice riêng.

## 12. ResponseStatusException với @ExceptionHandler và @ControllerAdvice

Một policy thực tế:

- Ở controller/web adapter, `ResponseStatusException` giúp biểu đạt các điều kiện đơn giản khi không cần error schema phức tạp.
- Trong domain layer, nên dùng exception/return type không phụ thuộc Servlet/WebFlux.
- Ở web boundary, `@RestControllerAdvice` ánh xạ domain exception sang `ProblemDetail` hoặc DTO lỗi.
- Với lỗi framework có sẵn, chọn cơ chế override phù hợp `ResponseEntityExceptionHandler` hoặc advice được đặt thứ tự hợp lý.

Có thể thêm một handler riêng cho `ResponseStatusException` nếu API yêu cầu body JSON đồng nhất, nhưng phải xem **tương tác với exception handlers của Spring Boot**, đặc biệt khi bật Problem Details. Không tự bắt toàn bộ `Exception.class` để luôn trả 400/200; đó là cách che lỗi hệ thống và làm metrics sai.

### 12.1. Order và phạm vi của advice

`@ControllerAdvice` có thể giới hạn phạm vi qua controllers/packages/annotations và dùng `@Order` để điều chỉnh thứ tự ưu tiên. Nếu có nhiều advice cùng bắt một loại exception, kết quả có thể phụ thuộc precedence.

Hãy đặt handler chuyên biệt cho lỗi nghiệp vụ, giữ behavior mặc định của framework cho request mapping/validation khi chưa có lý do thay, và có integration tests cho đường lỗi cần chuẩn hóa.

### 12.2. Chuyển exceptions nội bộ sang HTTP mã gì?

Một nguyên tắc là tầng nghiệp vụ phát exception mô tả **tại sao operation không thể hoàn thành**; web adapter xét nó trong context của HTTP operation:

~~~text
Domain:
  DuplicateTitleException
       |
       v
Web adapter:
  409 Conflict + TITLE_ALREADY_EXISTS

Domain:
  BookNotFoundException
       |
       v
Web adapter:
  404 Not Found

Infrastructure:
  DatabaseUnavailableException
       |
       v
Web adapter / operational policy:
  503 Service Unavailable (khi đúng ý nghĩa temporary unavailable)
  hoặc 500/Internal Server Error theo nguyên nhân thực tế
~~~

Đây là **định hướng**, không phải quy tắc mọi lỗi database đều là 503. Một database connection timeout nội bộ có thể dẫn đến 500, 503 hoặc timeout từ gateway tùy hoàn cảnh và kiến trúc.

## 13. Validation, authentication và routing: ai quyết định status?

Có những lỗi controller method chưa hề được gọi:

| Tầng | Tình huống | Status thường gặp |
| --- | --- | --- |
| HTTP parsing/binding | JSON không hợp lệ, thiếu body bắt buộc | 400 |
| Jakarta Bean Validation | `@NotBlank`/`@NotNull` trong `@Valid @RequestBody` fail | 400 theo MVC defaults |
| Request mapping | Path không có | 404 |
| Request mapping | HTTP method không phù hợp | 405 |
| Content negotiation | `Content-Type` không được chấp nhận | 415 |
| Content negotiation | `Accept` không thể đáp ứng | 406 |
| Spring Security | Chưa authentication | 401 hoặc redirect sang login tùy scheme |
| Spring Security | Không có authorization | 403 hoặc che resource theo policy |
| Application | Resource ID không tồn tại | 404 |
| Application | Xung đột trạng thái resource | 409 hoặc 412/422 theo contract |
| Infrastructure | Lỗi bất ngờ | 500 hoặc mã phù hợp policy |

Đừng đưa toàn bộ logic này vào mỗi controller. Spring MVC và Spring Security đã có resolver/handlers phù hợp; có thể customize error body và logging mà không phá ý nghĩa HTTP.

### 13.1. 401 cần biết authentication challenge

Với HTTP authentication, 401 thường cần `WWW-Authenticate` theo scheme. Nếu throw một `ResponseStatusException(UNAUTHORIZED)` thủ công trong controller, bạn có thể bỏ sót challenge header hoặc bypass policy được Spring Security thiết lập.

Giải pháp đúng là cấu hình `AuthenticationEntryPoint`/authentication mechanisms và kiểm thử với client tương ứng.

### 13.2. 403 và 404 cho tài nguyên nhạy cảm

Một số hệ thống cố ý dùng 404 để không tiết lộ resource mà client không được phép nhìn thấy. Đó phải là một **security/privacy policy nhất quán**, không phải sự thay thế tuỳ tiện cho authorization; ở nội bộ vẫn cần audit và enforcement đúng.

## 14. 409, 412 và 422: phân biệt lỗi nghiệp vụ

Ba status thường dễ bị gom:

**409 Conflict**: request xung đột với trạng thái hiện tại — ví dụ một tên unique đã tồn tại, hoặc thao tác chuyển trạng thái không được phép vì resource đang ở giai đoạn khác. Client có thể sửa dữ liệu/refresh state rồi thử lại.

**412 Precondition Failed**: client gửi HTTP precondition như `If-Match` nhưng ETag không còn đúng. Dùng cho optimistic concurrency ở tầng HTTP giúp client tránh ghi đè resource đã thay đổi.

**422 Unprocessable Content**: HTTP body có cú pháp hợp lệ và media type hiểu được, nhưng không thể xử lý semantic instructions theo policy. Ví dụ một yêu cầu thanh toán hợp lệ về JSON nhưng vi phạm một quy tắc nghiệp vụ cụ thể; tùy contract có thể chọn 409 hoặc 422.

Không có mapping chuẩn tự động “mọi exception nghiệp vụ = 422”. Cần ghi rõ mã nào dùng cho loại lỗi nào trong OpenAPI, test và tài liệu client.

### 14.1. Duplicate key và race condition

Code:

~~~java
if (repository.existsByName(name)) {
    throw new ResponseStatusException(HttpStatus.CONFLICT);
}
repository.save(entity);
~~~

chỉ là ví dụ phản diện về **check-then-act race**. Hai request đồng thời có thể cùng thấy chưa tồn tại rồi cùng lưu. Để bảo toàn uniqueness cần ràng buộc tại database (hoặc cơ chế đồng bộ thực tế), transaction và mapping exception tương ứng sang status 409 theo policy.

Không trả thẳng câu SQL unique constraint hoặc tên bảng/cột nội bộ cho client. Nếu cần mã lỗi ổn định, dùng một `code` công khai như `TITLE_ALREADY_EXISTS` trong error response.

## 15. 429 và 503: quá tải, retry và Retry-After

**429 Too Many Requests** thường thể hiện client đã vượt rate limit/quota. **503 Service Unavailable** thể hiện server tạm thời không thể xử lý do bảo trì hoặc overload. Cả hai có thể có header `Retry-After`:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
~~~

`Retry-After: 30` biểu thị thời gian chờ tính bằng giây theo cú pháp header. Nó cũng có thể là một HTTP-date. Không gửi giá trị chỉ để “cho đủ” nếu server không có policy phù hợp.

Một API client nên:

1. Xem request có thể retry an toàn không (idempotency, idempotency key, transaction state).
2. Tôn trọng `Retry-After` khi có.
3. Dùng exponential backoff + jitter để tránh retry storm.
4. Đặt giới hạn lần retry/tổng deadline.
5. Không tự retry lỗi validation 400 hoặc resource 404 liên tục nếu không có lý do.

Ví dụ trong controller có rate limiting đã được triển khai thực tế, web layer có thể trả 429/Retry-After; nhưng **rate limiting phải được thiết kế riêng**, không mặc định tồn tại nhờ `ResponseStatusException`.

Đừng dùng 429 chỉ vì database chậm; nếu cả server tạm thời quá tải, 503 có thể phản ánh đúng hơn. Khi có API gateway trả 502/504, cần phân biệt nguồn lỗi từ proxy và nguồn lỗi từ backend trước khi sửa status handler.

## 16. Status code và observability

HTTP status là tín hiệu quan trọng cho monitoring:

- Tỷ lệ 5xx tăng có thể cho thấy lỗi server/infrastructure.
- 400 tăng sau release có thể là client gửi format khác hoặc validation thay đổi.
- 401/403 tăng có thể do auth config/client credentials hoặc hoạt động không hợp lệ.
- 404 tăng có thể là route thay đổi, broken links, hoặc resource không tồn tại theo nghiệp vụ.
- 409 tăng có thể phản ánh concurrency conflicts hoặc rule nghiệp vụ.
- 429 tăng có thể phản ánh quota/rate limit đang phát huy tác dụng hoặc mức tải không phù hợp.
- 503/504 tăng có thể phản ánh quá tải, dependency, gateway timeout.

Không log mọi `ResponseStatusException(NOT_FOUND)` như lỗi hệ thống nghiêm trọng. Có thể dùng log level phù hợp, metrics, trace ID và theo dõi theo endpoint. Ngược lại, không “giấu” 500 bằng cách trả HTTP 200 để dashboard đẹp hơn.

Không gắn message chứa dữ liệu cá nhân, token hoặc SQL vào error response. Với production hãy có correlation/request ID không nhạy cảm để truy nguyên log. Mô tả lỗi cho client nên ổn định, an toàn và có thể localize nếu cần.

## 17. Những lỗi và hiểu nhầm thường gặp

### 17.1. @ResponseStatus(reason=...) bảo đảm JSON message

Sai. Với Servlet MVC, reason không rỗng có thể dẫn tới `sendError`; container/Boot có thể tạo body khác hoặc bỏ qua method return value. Nếu API cần JSON ổn định, dùng explicit response/exception handler.

### 17.2. new ResponseStatusException(404) luôn xuất ProblemDetail

Không bảo đảm. Framework 6 có `ErrorResponse`/`ProblemDetail` abstraction, nhưng đường resolver và Boot Problem Details config quyết định HTTP body cuối. Test actual status/body trong ứng dụng.

### 17.3. @ResponseStatus có thể chọn nhiều status theo runtime

Không phải bản chất của annotation: một annotation gắn status cố định cho method/exception class. Muốn chọn 400/404 theo dữ liệu, dùng exception động hoặc `ResponseEntity`/advice.

### 17.4. HTTP 200 với {"success":false} là tương đương HTTP lỗi

Không tương đương: HTTP clients, caches, API gateways và monitoring dựa trên status line. Hãy phát status HTTP đúng; body `success` nếu có chỉ là thông tin bổ sung.

### 17.5. Validation mặc định nên là 500

Không. Input invalid là tình huống client có thể sửa, thường 400. Chỉ dùng 500 cho lỗi server thực sự.

### 17.6. 401 và 403 là như nhau

Không. Authentication chưa hoàn tất khác authorization không được phép. Để Spring Security xử lý challenge/access denial đúng scheme.

### 17.7. 404 luôn chứng minh controller mapping không tồn tại

Không. Controller có thể cố ý trả 404 cho resource ID không tìm thấy, hoặc security policy có thể giấu resource.

### 17.8. 409 và 422 tùy ý đổi cho nhau

Không nên. Chọn semantics có thể giải thích được, tài liệu hóa theo loại lỗi và đảm bảo client contract nhất quán.

### 17.9. Dùng 410 cho mọi tài nguyên chưa tìm thấy

Không. 410 biểu đạt server biết resource không còn tồn tại theo ý nghĩa lâu dài; 404 vẫn đúng cho nhiều trường hợp.

### 17.10. Trả 503 với mọi lỗi database

Không chính xác. 503 cần phù hợp “service temporarily unavailable”; lỗi dữ liệu, bug code hoặc internal server exception có thể là 500, còn constraint conflict có thể 409.

### 17.11. Response đã commit vẫn đổi status được

Không. Khi bytes/headers đã đi ra client, status không thể đổi hồi tố. Đặc biệt quan trọng với Servlet streaming, SSE và WebFlux Flux.

### 17.12. Error response body có thể chứa mọi Throwable message

Nguy hiểm. Throwable message có thể chứa SQL, file paths hoặc secret values. Dùng thông điệp an toàn và mã lỗi công khai.

### 17.13. Cứ bắt Exception rồi trả 400 sẽ đơn giản hơn

Sai. Catch-all 400 che lỗi server và phá metrics. Đặt handler theo loại lỗi, để lỗi không nhận diện đi qua cơ chế 500 an toàn.

### 17.14. Test status thôi là đủ cho API công khai

Chưa đủ nếu client phụ thuộc error JSON. Test status, Content-Type, error code, field presence và version compatibility; đồng thời không test những body default mà chưa được hợp đồng bảo đảm.

## 18. Checklist khi chọn HTTP status và xử lý lỗi

1. Client cần biết request đã thành công, chờ xử lý hay thất bại? Chọn 200/201/202/204 đúng semantics.
2. Lỗi xảy ra do syntax/body invalid, authentication, authorization, missing resource, conflict hay server?
3. `@ResponseStatus` được gắn trên method/exception có status cố định đúng hoàn cảnh không?
4. Annotation có `reason` không rỗng khiến Servlet `sendError` và mất body không?
5. `ResponseStatusException` có thích hợp cho trạng thái động mà không cần schema riêng không?
6. Khi API cần body ổn định, có `ResponseEntity`/`@RestControllerAdvice`/`ProblemDetail` và tests chưa?
7. Exception domain có bị ràng buộc vào Spring HTTP quá mức không?
8. Có `@ExceptionHandler` hoặc `@ControllerAdvice` khác ưu tiên cao làm thay đổi mapping status không?
9. Status ở HTTP line có khớp `ProblemDetail.status` và documentation không?
10. Với 400, 401, 403, 404, 409, 410, 412, 415, 422, 429, 500, 503 đã có policy rõ chưa?
11. Có status/header do framework/Spring Security tạo trước controller không? Đã tránh ghi đè `Allow`/`WWW-Authenticate` sai cách chưa?
12. Với 201, `Location` có trỏ đến resource vừa được tạo thật và đúng public URL không?
13. Với 204/304, response có vô tình mang body không?
14. Khi phát 429/503, `Retry-After` và retry policy có hợp lý không?
15. Có leak nội bộ stack trace/SQL/secrets trong `detail`/`reason` không?
16. Có database unique constraint để tránh race khi trả 409 cho duplicate key không?
17. Với streaming/async, code có cố đổi status sau response commit không?
18. Unit/MockMvc tests đã kiểm tra cả status, headers và error representation mà client dùng chưa?
19. Monitoring có phân biệt expected 4xx với unexpected 5xx và chú ý gateway 502/504 không?
20. API OpenAPI/contract đã liệt kê status codes và schemas theo từng endpoint chưa?

**Kết luận:** `@ResponseStatus` phù hợp với status cố định trên method hoặc exception; `ResponseStatusException` phù hợp để chọn HTTP status theo điều kiện runtime; `ResponseEntity` và `@RestControllerAdvice`/`@ExceptionHandler` cho phép kiểm soát status, headers và error schema chặt chẽ hơn. Chọn **mã HTTP theo ngữ nghĩa lỗi**, không theo sự tiện lợi của exception type. Đặc biệt trong Spring MVC, `@ResponseStatus(reason=...)` có thể kích hoạt `sendError`, vì vậy không dùng nó để bảo đảm JSON lỗi. Để có API ổn định, cần đồng bộ status line, ProblemDetail/error code, bảo mật thông tin và tests.

## Tài liệu tham khảo

- [Spring Framework 6.1 — @ResponseStatus Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/bind/annotation/ResponseStatus.html): status, reason và cảnh báo `sendError`.
- [Spring Framework 6.1 — ResponseStatusException Javadoc](https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/web/server/ResponseStatusException.html): constructors, `ErrorResponse` và `ProblemDetail`.
- [Spring Framework 6.1 — ResponseStatusExceptionResolver Javadoc](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/web/servlet/mvc/annotation/ResponseStatusExceptionResolver.html): xử lý annotation/exception trong Servlet MVC.
- [Spring Framework — MVC Exceptions](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html): `HandlerExceptionResolver` chain.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, `ResponseEntityExceptionHandler`.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.mvc.problemdetails.enabled`.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): cấu trúc error representation.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): định nghĩa HTTP status codes và các headers liên quan.
