# Giải quyết tham số, thực thi controller và xử lý giá trị trả về trong Spring MVC

Một method trong controller Spring MVC có thể khai báo `@PathVariable long id`, `@RequestParam String sort`, `@RequestBody CreateBookRequest input`, `Model model` hoặc `HttpServletRequest request`. Client không trực tiếp gọi Java method và cũng không tự tạo các đối tượng đó. **Spring MVC chọn một handler, giải quyết từng tham số theo nguồn dữ liệu và quy tắc phù hợp, thực thi method, rồi chuyển giá trị trả về thành HTTP response hoặc model/view.**

Bài học này giải thích ba chặng nối tiếp trong **Spring MVC trên Servlet stack**: *argument resolution* → *controller invocation* → *return value handling*. Đây là cơ chế cốt lõi đằng sau annotation-based controllers của Spring Framework 6.x / Spring Boot 3.x, dùng Java 17+. Spring WebFlux có pipeline và các abstraction khác; không áp nguyên các lớp `RequestMappingHandlerAdapter`, `ServletInvocableHandlerMethod` của MVC sang WebFlux.

## 1. Mục tiêu và bức tranh tổng thể

Sau bài này, bạn có thể:

- Mô tả vai trò của `DispatcherServlet`, `HandlerMapping`, `HandlerAdapter`, `RequestMappingHandlerAdapter` và `HandlerMethod`.
- Giải thích cách `HandlerMethodArgumentResolver` tạo giá trị cho từng tham số: path, query, header, cookie, request body, model hoặc context.
- Phân biệt **chuyển đổi kiểu đơn giản**, **data binding**, **JSON deserialization** và **validation**.
- Hiểu `@Controller` + view name khác `@RestController`/`@ResponseBody` như thế nào.
- Biết cách `HandlerMethodReturnValueHandler`, `HttpMessageConverter`, `ModelAndView`, `ResponseEntity` và exception resolver ảnh hưởng response.
- Đọc một controller thực tế và dự đoán status, headers, body, lỗi 400/404/406/415 và thứ tự các bước.

Sơ đồ cho một request đi qua MVC:

~~~text
HTTP request
    |
    v
Servlet container → Filter chain → DispatcherServlet
                                      |
                                      v
                               HandlerMapping
                       tìm HandlerMethod phù hợp
                                      |
                                      v
                      RequestMappingHandlerAdapter
                                      |
              +-----------------------+---------------------+
              |                                             |
              v                                             |
    HandlerMethodArgumentResolver(s)                        |
    + path/query/header/cookie                              |
    + body ↔ HttpMessageConverter                            |
    + @ModelAttribute ↔ DataBinder                           |
    + validation / BindingResult                             |
              |                                             |
              v                                             |
         Java arguments                                     |
              |                                             |
              v                                             |
     invoke controller method                               |
              |                                             |
              v                                             |
    HandlerMethodReturnValueHandler(s)                       |
    + @ResponseBody/ResponseEntity → converter → HTTP body   |
    + String/ModelAndView → model & view → ViewResolver      |
    + async wrapper → async request processing               |
              |                                             |
              +----------------------+----------------------+
                                     |
                                     v
                          HTTP status + headers + body
~~~

Sơ đồ là mô hình khái quát. Một `HandlerInterceptor`, `@ControllerAdvice`, exception resolver, security filter, async dispatch hay template engine có thể tham gia vào từng bước tùy cấu hình. Không suy luận controller luôn được gọi khi request có status lỗi: nhiều lỗi xuất hiện **trước lúc method chạy**.

## 2. Spring MVC tìm handler rồi mới giải quyết tham số

### 2.1. HandlerMapping và HandlerAdapter là hai trách nhiệm khác nhau

`DispatcherServlet` nhận request đã được Servlet container phân phối. Nó hỏi các `HandlerMapping` để lấy handler và các interceptor liên quan. Đối với annotation-based controllers, `RequestMappingHandlerMapping` thường xác định một `HandlerMethod` đại diện cho một Java method cùng bean controller tương ứng.

Ví dụ:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {
    @GetMapping("/{id}")
    public String get(@PathVariable long id) {
        return "book-" + id;
    }
}
~~~

Với `GET /api/books/42`, handler matching xét **HTTP method, URL path và các điều kiện của request mapping**. `HandlerMethod` có thông tin như method Java `get` và controller bean cần gọi. `HandlerMapping` không tự parse request body thành DTO để gọi method.

Sau khi tìm handler, `DispatcherServlet` chọn một `HandlerAdapter` có thể thực thi handler đó. Với `HandlerMethod` của annotated controllers, adapter thông thường là **`RequestMappingHandlerAdapter`**. Nhờ abstraction `HandlerAdapter`, `DispatcherServlet` không cần biết chi tiết cách gọi từng kiểu handler.

### 2.2. Trách nhiệm của RequestMappingHandlerAdapter

`RequestMappingHandlerAdapter` chịu trách nhiệm chuẩn bị môi trường gọi annotated controller, bao gồm:

1. Lấy metadata của controller method đã match.
2. Chuẩn bị `ModelAndViewContainer`, model, các `@ModelAttribute` liên quan và binding context.
3. Cung cấp danh sách argument resolvers để dựng từng Java argument.
4. Gọi method qua tầng invocable handler method.
5. Nhờ return-value handlers xử lý đối tượng controller trả về.
6. Cung cấp `ModelAndView` cho `DispatcherServlet` khi cần render view; hoặc đánh dấu response đã được xử lý.

Các lớp liên quan trong Spring MVC gồm `ServletInvocableHandlerMethod`, `InvocableHandlerMethod`, `HandlerMethodArgumentResolverComposite` và `HandlerMethodReturnValueHandlerComposite`. Chúng là **chi tiết nội bộ hữu ích để đọc source/debug**; code ứng dụng thông thường nên lập trình qua annotation và interface extension được hỗ trợ.

**Thứ tự quan trọng:** chọn controller không có nghĩa Spring đã resolve được argument. Ví dụ mapping `GET /books/{id}` có thể khớp path `/books/abc`, nhưng việc chuyển `abc` thành `long` thất bại sau đó và method sẽ không được gọi.

## 3. HandlerMethodArgumentResolver giải quyết tham số như thế nào?

Một `HandlerMethodArgumentResolver` có hai hoạt động chính:

- `supportsParameter(MethodParameter parameter)`: resolver có hiểu cách tạo giá trị cho tham số này không?
- `resolveArgument(...)`: lấy dữ liệu từ request/model/context, chuyển đổi hoặc kết hợp với công cụ khác để tạo argument.

Spring giữ **nhiều resolver** trong một composite. Mỗi parameter của handler được xét để chọn resolver tương ứng; resolver phù hợp đầu tiên theo thứ tự cấu hình sẽ xử lý. Kết quả được đặt đúng vị trí trong mảng argument trước khi Java method được gọi. Resolver có thể đọc metadata annotation, không chỉ nhìn kiểu Java.

Ví dụ chữ ký:

~~~java
@GetMapping("/{id}")
public BookResponse read(
        @PathVariable long id,
        @RequestParam(defaultValue = "vi") String lang,
        @RequestHeader("X-Client-Version") String version,
        HttpServletRequest request) {
    // ...
}
~~~

Với:

~~~http
GET /api/books/42?lang=en HTTP/1.1
Host: localhost:8080
X-Client-Version: 2

~~~

Các argument hình thành độc lập theo nguồn:

| Java argument | Resolver / cơ chế đại diện | Kết quả |
| --- | --- | --- |
| `@PathVariable long id` | URI-template variable + conversion | `42L` |
| `@RequestParam String lang` | Request parameter resolver | `"en"` |
| `@RequestHeader String version` | Header resolver | `"2"` |
| `HttpServletRequest request` | Servlet request argument resolver | Request object hiện tại |

Không phải controller tự xây `HttpServletRequest`; Servlet container tạo request và Spring truyền tham chiếu thích hợp. Không phải mọi đối số đều bắt buộc có annotation: các kiểu `Model`, `Principal`, `Locale`, `HttpServletResponse` có resolvers theo kiểu đối tượng. Tuy nhiên **đánh dấu annotation rõ ràng** giúp tránh nhầm source của dữ liệu.

### 3.1. Các nhóm tham số thường gặp

| Tham số | Nguồn | Điểm cần nhớ |
| --- | --- | --- |
| `@PathVariable` | Biến trong URI template đã match | Có thể convert `String` thành `long`, `UUID`, `Enum`, ... |
| `@RequestParam` | Request parameters: query và tùy trường hợp form/multipart | `required`, `defaultValue`, kiểu đích ảnh hưởng hành vi. |
| `@RequestHeader` | HTTP header | Tên header không phân biệt hoa/thường; convert kiểu khi cần. |
| `@CookieValue` | Request cookies | Cookie có thể thiếu; cần quyết định required/default. |
| `@RequestBody` | HTTP request content | Đọc qua `HttpMessageConverter`, ví dụ Jackson JSON. |
| `@RequestPart` | Một part trong multipart request | Converter có thể xử lý payload của part. |
| `MultipartFile` | Multipart upload đã được cấu hình parse | Không đồng nghĩa mọi request body là multipart. |
| `@ModelAttribute` | Model + request parameters / binding | Dùng `WebDataBinder`, thường cho form/command object. |
| `BindingResult`, `Errors` | Binding/validation errors của argument trước đó | Phải đặt **ngay sau** argument được validate. |
| `Model`, `ModelMap` | MVC model hiện tại | Thường dùng khi render HTML view. |
| `HttpServletRequest`, `HttpServletResponse` | Servlet API | Truy cập request/response thấp hơn. |
| `Principal` | Thông tin principal hiện hành | Kết quả tùy cơ chế security/container. |
| `@RequestAttribute`, `@SessionAttribute` | Request/session attributes | Khác `@RequestParam`; không phải query parameter. |
| `HttpEntity<T>` | Request headers + body | `T` được đọc thông qua message converter. |

`@RequestParam` không bắt buộc ở một số simple-type parameters vì Spring MVC có cơ chế fallback, nhưng code API rõ ràng nên chú thích nguồn dữ liệu. `Optional<T>`, `required=false` và `defaultValue` có thể xử lý trường hợp thiếu tham số, với khác biệt cụ thể tùy annotation.

### 3.2. Path variable và query parameter khác nhau

~~~java
@GetMapping("/books/{bookId}")
public String find(
        @PathVariable long bookId,
        @RequestParam(defaultValue = "full") String view) {
    return bookId + ":" + view;
}
~~~

Gọi `GET /books/7?view=summary` tạo `bookId=7`, `view="summary"`. Nếu thiếu `view`, Spring dùng `"full"` nhờ `defaultValue`. Nếu request là `/books/xyz`, matching có thể chọn method nhưng argument conversion `String → long` thất bại; Spring MVC thường phản hồi **400 Bad Request** thông qua exception handling mặc định.

**Query không thuộc URI path matching**: `?view=summary` được đọc như parameter, còn `{bookId}` là một path segment.

### 3.3. Type conversion khác JSON deserialization

Với `@PathVariable long id` và `@RequestParam int page`, dữ liệu đến từ những chuỗi ngắn. Spring dùng hệ thống chuyển đổi/formatting (`ConversionService`, `Converter`, `Formatter`, `WebDataBinder` tùy cơ chế) để chuyển chuỗi sang kiểu Java.

Với `@RequestBody BookRequest request`, dữ liệu có thể là **JSON nhiều trường**. Spring dùng `HttpMessageConverter` phù hợp với media type, thường là Jackson JSON converter khi có Jackson, để đọc stream bytes và deserialize JSON thành đối tượng.

| Nguồn dữ liệu | Ví dụ | Chủ yếu đi qua |
| --- | --- | --- |
| Path | `/books/42` → `long id` | Type conversion |
| Query | `?page=2` → `int page` | Type conversion |
| Header | `X-Limit: 10` → `int limit` | Header resolver + conversion |
| JSON request body | `{"title":"MVC"}` → `BookRequest` | `HttpMessageConverter` |
| Form parameters | `title=MVC&price=50` → command object | `@ModelAttribute` + `WebDataBinder` |

**Không nhầm `@RequestBody` với `@ModelAttribute`.** `@RequestBody` là đường đọc HTTP body qua converter; `@ModelAttribute` là đường tạo/tìm model object rồi bind các request parameters vào thuộc tính. Với `application/x-www-form-urlencoded`, việc truy cập Servlet request parameters có thể tiêu thụ hoặc ảnh hưởng việc đọc body thô, nên không mặc định dùng cả hai cơ chế để đọc lại cùng một form body.

## 4. @RequestBody, HttpMessageConverter và Content-Type

Ví dụ:

~~~java
@PostMapping(path = "/books", consumes = "application/json")
@ResponseBody
public BookResponse create(@RequestBody CreateBookRequest input) {
    return new BookResponse(1L, input.title());
}
~~~

Đây là **method minh họa cần đặt trong `@Controller` Spring MVC**, cùng khai báo các record DTO tương ứng. Luồng:

1. Request đi vào handler đã match `POST /books`.
2. Resolver cho `@RequestBody` phát hiện target Java type `CreateBookRequest`.
3. Spring chọn `HttpMessageConverter` có thể đọc kiểu đó với `Content-Type: application/json`, ví dụ Jackson converter.
4. Converter deserialize JSON thành instance Java.
5. Controller nhận object và tạo giá trị trả về.
6. Return-value handler của `@ResponseBody` lại chọn converter có thể viết `BookResponse` thành nội dung phản hồi; `Accept`, `produces` và converter capabilities có thể ảnh hưởng content negotiation.

Phân biệt:

- `Content-Type` **trong request** mô tả media type của request content.
- `Accept` **trong request** mô tả media type response mà client mong muốn.
- `Content-Type` **trong response** mô tả representation được server gửi ra.

Lỗi thường gặp:
- JSON sai cú pháp hoặc không thể deserialize theo converter → thường **400 Bad Request** (`HttpMessageNotReadableException`).
- Request media type không được handler/converter hỗ trợ → thường **415 Unsupported Media Type**.
- Client chỉ chấp nhận media type mà server không thể tạo → thường **406 Not Acceptable**.
- `@RequestBody(required=true)` nhưng không có body cần thiết → thường **400**.

Không bắt mọi exception converter rồi biến thành 500: 400/415/406 mang ý nghĩa HTTP riêng. Ngoài ra, không tự kết luận Jackson được cài chỉ vì có spring-web; cần thư viện converter tương ứng trong runtime classpath hoặc cấu hình của ứng dụng.

## 5. @ModelAttribute, DataBinder và validation

Trong ứng dụng render form HTML, Spring thường nhận dữ liệu dưới dạng request parameters. Với DTO model attribute, `WebDataBinder` bind dữ liệu vào object, kết hợp converter/formatter để xử lý kiểu, sau đó có thể validation theo annotation hoặc cấu hình.

Ví dụ một method đặt trong `@Controller`:

~~~java
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute RegistrationForm form,
        BindingResult bindingResult,
        Model model) {
    if (bindingResult.hasErrors()) {
        return "register-form";
    }
    model.addAttribute("message", "Registered " + form.getUsername());
    return "register-result";
}
~~~

Đây là **method minh họa**: `RegistrationForm`, validator/Bean Validation provider và template view phải được định nghĩa trong ứng dụng. Giá trị trả về `"register-form"` và `"register-result"` là **logical view names** khi không có `@ResponseBody`. Spring chưa gửi những chuỗi này trực tiếp vào HTTP body như JSON.

`BindingResult`/ `Errors` phải nằm **ngay sau argument mà nó mô tả**. Nếu dùng `@Valid @ModelAttribute RegistrationForm form` mà thiếu đối số `BindingResult` cần thiết để tự xử lý lỗi, lỗi validation có thể trở thành exception do Spring giải quyết và phương thức không vào nhánh `if` như bạn mong đợi.

### 5.1. @Valid và @Validated đứng ở đâu trong pipeline?

- **Binding/deserialization** đưa dữ liệu vào đối tượng Java.
- **Validation** đánh giá constraints trên đối tượng hoặc method parameters khi đã có đối tượng/giá trị thích hợp.
- **Business validation** kiểm tra các ràng buộc nghiệp vụ phức tạp, có thể cần database/service và thường nằm trong tầng nghiệp vụ.

`@Valid @RequestBody` có thể kích hoạt Bean Validation và lỗi thông thường phát sinh dưới dạng `MethodArgumentNotValidException`, thường được xử lý thành 400. Trong Spring MVC 6.1+, khi có constraints trực tiếp ở method parameter và method validation được áp dụng, `HandlerMethodValidationException` cũng có thể phát sinh. **Không giả định mọi lỗi validation đi qua duy nhất một exception class**, và không nhầm validation với JSON deserialization.

Đối với `@ModelAttribute`, hãy kiểm soát những thuộc tính được bind; không để client tự đặt thuộc tính nhạy cảm chỉ vì nó có setter, như `role`, `isAdmin` hoặc `balance`. Dùng DTO chuyên cho input, cho phép bind những field hợp lệ và áp dụng validation/bảo mật nghiệp vụ độc lập.

### 5.2. BindingResult là dữ liệu lỗi, không phải response status

`BindingResult` giữ thông tin field/global errors để controller tự quyết định xử lý. Việc có `BindingResult` không tự ghi HTTP status 400; nếu controller trả view form với status 200 thì client có thể vẫn nhận 200. Trong REST API, bạn thường cần chuyển các lỗi thành status phù hợp như 400/422 theo hợp đồng được công bố. Phân biệt **thu thập lỗi** với **chọn HTTP response**.

## 6. Gọi controller method thực sự

Sau khi từng argument được giải quyết, Spring gọi phương thức Java đã chọn. Controller là Spring-managed bean (singleton trong cấu hình mặc định), nên **nhiều request có thể gọi cùng instance đồng thời**. Tham số method được tạo riêng cho lần gọi, nhưng các trường instance mutable của singleton controller là dữ liệu chia sẻ; tránh dùng controller field để lưu trạng thái tạm của request.

Một số điểm quan trọng:

1. **Mất thời gian ở resolver cũng là thời gian request.** Converter, validation, binder có thể thất bại trước khi vào method.
2. **Interceptor preHandle** có thể ngăn handler tiếp tục. Exception filter/security cũng có thể trả response sớm.
3. **AOP proxy** có thể bọc controller/service, ảnh hưởng giao dịch, validation, bảo mật hay logging theo cấu hình.
4. **Service call** do controller điều phối, không mặc nhiên được Spring MVC retry hay tự biến thành async.
5. **Exception** phát ra trong resolver, controller hoặc return-value handler có thể được chuyển cho chuỗi `HandlerExceptionResolver`.

Không phải mọi response từ một URI đều do body của controller method đó tạo. Ví dụ lỗi request parsing có thể sinh 400 trước khi method chạy; một filter có thể gửi 401; Spring Security có thể quyết định 403.

## 7. HandlerMethodReturnValueHandler giải thích giá trị trả về

Sau khi controller trả một Java value, Spring chọn **`HandlerMethodReturnValueHandler`** phù hợp theo return type và annotation. Handler này có thể:

- Đánh dấu response đã được xử lý và viết status/headers/body.
- Đưa dữ liệu vào `ModelAndViewContainer` rồi để MVC render view.
- Đăng ký xử lý async để request tiếp tục ở lần dispatch sau.
- Chuẩn hóa status/headers theo `ResponseEntity` hoặc các annotation tương ứng.

`HandlerMethodReturnValueHandler` và `HttpMessageConverter` có vai trò khác nhau. **Return-value handler quyết định cách diễn giải Java return value** (body hay view, headers/status, async...), còn **message converter biến Java object thành bytes của HTTP representation** khi cần viết body.

| Controller trả về | Cách Spring MVC hiểu | Ví dụ |
| --- | --- | --- |
| Object + `@ResponseBody` | Serialize object vào response body | `BookResponse` → JSON |
| Object trong `@RestController` | Tương tự vì `@RestController` bao gồm `@ResponseBody` | JSON API |
| `ResponseEntity<T>` | Chỉ định HTTP status, headers và body | 201 + `Location` + DTO |
| `HttpEntity<T>` | Body + headers phản hồi, không có API đặt status riêng như `ResponseEntity` | Kết quả có header |
| `String` trong `@Controller` không `@ResponseBody` | Logical view name | `"books/list"` |
| `ModelAndView` | Tên/view object cùng model | Render HTML |
| `Model` / `Map` | Thêm attributes vào model; tên view xác định theo quy tắc MVC | Trang HTML |
| `ProblemDetail` / `ErrorResponse` | Mô tả lỗi theo hỗ trợ problem details | Phản hồi lỗi |
| `Callable<T>`, `DeferredResult<T>` | Kết quả async, sẽ xử lý return value khi có kết quả | Long-running request |
| `ResponseBodyEmitter`, `SseEmitter` | Streaming response | SSE |
| `void` | Phụ thuộc annotation/context và mức response đã xử lý | Không tự đồng nghĩa 204 |

**Giá trị Java giống nhau có thể mang ngữ nghĩa HTTP khác nhau** nếu annotation khác nhau.

### 7.1. @Controller với String: view name

~~~java
@Controller
class PageController {
    @GetMapping("/books")
    public String books(Model model) {
        model.addAttribute("heading", "Book catalog");
        return "books/list";
    }
}
~~~

Đây là method/controller minh họa chạy khi app đã cấu hình một view technology như Thymeleaf và có template tương ứng. Chuỗi `"books/list"` được view resolver diễn giải thành một view/template cần render. `Model` chuyển `heading` tới view. Nếu view không tồn tại, bạn có thể nhận lỗi render mặc dù handler method đã chạy thành công.

Với `return "redirect:/books";`, Spring MVC có thể xử lý tiền tố `redirect:` để tạo HTTP redirect, thay vì render một view cùng tên.

### 7.2. @RestController với String: response body

~~~java
@RestController
class TextController {
    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Với stack có `StringHttpMessageConverter` phù hợp, response body là chuỗi:

~~~text
pong
~~~

Ở đây Spring **không** tìm template tên `pong`. `@RestController` là một meta-annotation mang hiệu ứng `@Controller` và `@ResponseBody`. Tùy configuration/content negotiation, `Content-Type` có thể là `text/plain` hoặc loại tương ứng; không mặc định response là JSON chỉ vì controller có `@RestController`.

### 7.3. ResponseEntity điều khiển cả status, headers và body

~~~java
@PostMapping("/books")
public ResponseEntity<BookResponse> create(@RequestBody CreateBookRequest input) {
    BookResponse result = new BookResponse(42L, input.title());
    return ResponseEntity
            .created(URI.create("/api/books/42"))
            .body(result);
}
~~~

Đoạn này là **method minh họa** cần định nghĩa controller, DTO và import phù hợp. Kết quả có status `201 Created`, header `Location: /api/books/42` và body object do converter serialize. `ResponseEntity.ok(value)` tạo 200, `ResponseEntity.noContent().build()` tạo 204 không có body, `ResponseEntity.notFound().build()` tạo 404 không có body theo ví dụ.

**Đừng cố trả JSON body với 204 No Content.** Phản hồi 204 theo HTTP không mang message content. ResponseEntity không bỏ qua quy tắc HTTP chỉ vì kiểu generic được khai báo.

### 7.4. @ResponseStatus, null và void

`@ResponseStatus(HttpStatus.NO_CONTENT)` có thể đặt status khi handler hoàn tất, nhưng không có nghĩa mọi `void` method đều tự trả 204. Return type `void` hoặc `null` có ngữ nghĩa phụ thuộc các annotation, Servlet response arguments, việc response đã được ghi hay model/view flow. Trong HTML controller, Spring có thể suy ra default view name; trong REST controller, thường không có body.

Nếu tự ghi vào `HttpServletResponse.getWriter()` thì đang tác động response trực tiếp; không nên đồng thời mong message converter viết thêm một object nữa vào cùng stream. Một khi response committed, thay status/header hoặc render trang lỗi có thể không còn thực hiện được.

## 8. Ví dụ Spring Boot 3 chạy được: quan sát đủ ba chặng

Tạo dự án **Spring Boot 3.x / Java 17+** với dependencies:
- `spring-boot-starter-web`: Spring MVC, embedded servlet container và JSON converter thường dùng.
- `spring-boot-starter-validation`: Bean Validation với Jakarta Validation, để `@NotBlank`/ `@Valid` hoạt động.

Với dự án Gradle đã cấu hình Spring Boot plugin, các dependencies tương ứng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Đặt toàn bộ code dưới đây vào **`src/main/java/demo/mvc/MvcPipelineApplication.java`**. Ví dụ chạy trong ứng dụng Spring Boot với build/dependency nói trên, không phải chương trình biên dịch bằng `javac` đơn lẻ không có classpath của Spring.

~~~java
package demo.mvc;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MvcPipelineApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcPipelineApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/books")
class BookController {

    private final AtomicLong sequence = new AtomicLong();
    private final Map<Long, Book> books = new ConcurrentHashMap<>();

    @GetMapping("/{id}")
    public ResponseEntity<BookResponse> get(
            @PathVariable long id,
            @RequestParam(defaultValue = "vi") String lang,
            @RequestHeader(value = "X-Trace-Id",
                           defaultValue = "none") String traceId) {

        Book book = books.get(id);
        if (book == null) {
            return ResponseEntity.notFound().build();
        }
        BookResponse response = new BookResponse(
                book.id(), book.title(), lang, traceId);
        return ResponseEntity.ok(response);
    }

    @PostMapping(consumes = "application/json",
                 produces = "application/json")
    public ResponseEntity<BookResponse> create(
            @Valid @RequestBody CreateBookRequest request) {

        long id = sequence.incrementAndGet();
        Book book = new Book(id, request.title());
        books.put(id, book);

        BookResponse response =
                new BookResponse(id, book.title(), "vi", "none");

        return ResponseEntity
                .created(URI.create("/api/books/" + id))
                .body(response);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable long id) {
        if (books.remove(id) == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.noContent().build();
    }

    public record CreateBookRequest(@NotBlank String title) {}

    public record Book(long id, String title) {}

    public record BookResponse(
            long id, String title, String lang, String traceId) {}
}
~~~

**Vì sao ví dụ này minh họa đủ pipeline?**

- `@PathVariable`, `@RequestParam` và `@RequestHeader`: resolver lấy URI/query/header rồi convert sang kiểu Java.
- `@Valid @RequestBody`: converter đọc JSON thành record; validation kiểm tra `title` phải là chuỗi không trống/không chỉ whitespace.
- `get`, `create`, `delete`: controller method được gọi sau khi arguments đã được chuẩn bị.
- `ResponseEntity<BookResponse>`: return-value handler đọc status/headers/body; Jackson converter serialize record sang JSON.
- `ResponseEntity<Void>`: return-value handler trả 204 không có body.
- `ConcurrentHashMap` + `AtomicLong`: demo hỗ trợ nhiều request đồng thời ở mức lưu tạm trong bộ nhớ; đây không phải database, không cung cấp transaction/durability.

Ứng dụng mới khởi động không có dữ liệu và `sequence` bắt đầu từ 0; ví dụ HTTP dưới đây giả định chưa có client khác tạo sách.

Chạy bằng Gradle wrapper từ thư mục dự án:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Sau khi ứng dụng khởi động với port mặc định `8080`, thử tạo sách:

~~~bash
curl -i -X POST "http://localhost:8080/api/books" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"title":"Spring MVC"}'
~~~

Response kỳ vọng có status `201 Created`, `Location: /api/books/1` và JSON tương đương:

~~~json
{"id":1,"title":"Spring MVC","lang":"vi","traceId":"none"}
~~~

Thứ tự field, khoảng trắng, một số response headers và cách ghi Transfer-Encoding/Content-Length tùy converter/container. Giá trị ID = 1 chỉ đúng khi đây là lần tạo đầu tiên của một process demo mới.

Tiếp tục:

~~~bash
curl -i "http://localhost:8080/api/books/1?lang=en" \
  -H "X-Trace-Id: demo-001" \
  -H "Accept: application/json"
~~~

Response kỳ vọng là 200 và body tương đương:

~~~json
{"id":1,"title":"Spring MVC","lang":"en","traceId":"demo-001"}
~~~

Có thể theo dõi argument lần lượt: `id=1` lấy từ path; `lang="en"` lấy từ query; `traceId="demo-001"` lấy từ header. Giá trị trả về là `BookResponse`, sau đó converter serialize thành JSON.

Thử delete:

~~~bash
curl -i -X DELETE "http://localhost:8080/api/books/1"
~~~

Response kỳ vọng **204 No Content** không có body. Gọi lại `GET /api/books/1` nhận 404 do sách đã bị xóa.

Thử các lỗi input:

~~~bash
curl -i "http://localhost:8080/api/books/abc"

curl -i -X POST "http://localhost:8080/api/books" \
  -H "Content-Type: application/json" \
  -d '{"title":""}'

curl -i -X POST "http://localhost:8080/api/books" \
  -H "Content-Type: text/plain" \
  -d 'just text'
~~~

| Request lỗi | Điểm thất bại | HTTP status thường gặp |
| --- | --- | --- |
| `GET /api/books/abc` | `"abc"` không chuyển thành `long id` | 400 |
| POST JSON với `title=""` | Bean Validation `@NotBlank` | 400 |
| POST `Content-Type: text/plain` | `consumes="application/json"` không match | 415 |
| GET id đã bị xóa | Controller chủ động trả `notFound()` | 404 |

**Lưu ý:** Body lỗi mặc định (JSON/HTML/Problem Details) tùy Spring Boot version, `Accept`, cấu hình error handler và Security. Bảng xác nhận ý nghĩa status, không giả định một response body lỗi duy nhất.

### 8.1. Bóc từng bước một request

Với `POST /api/books` và `{"title":"Spring MVC"}`:

1. Servlet container đưa request cho `DispatcherServlet`.
2. `RequestMappingHandlerMapping` khớp POST, path, `consumes`, `produces` và tìm `BookController.create`.
3. `RequestMappingHandlerAdapter` chọn argument resolver cho `@RequestBody`.
4. `HttpMessageConverter` đọc bytes JSON, tạo `CreateBookRequest("Spring MVC")`.
5. Bean Validation kiểm tra `@NotBlank`; nếu lỗi thì dừng trước controller method.
6. Spring gọi `create(request)`; method tạo `Book`, lưu map và tạo `ResponseEntity`.
7. Return-value handler nhận `ResponseEntity`, đặt status 201 và header Location.
8. JSON converter serialize `BookResponse` thành response body.
9. Container gửi HTTP response. Interceptor/filter và bước hoàn tất request còn có thể tham gia tùy cấu hình.

Đây là **thứ tự logic** giúp hiểu cơ chế, không khẳng định mỗi bước luôn do một class duy nhất xử lý trên mọi cấu hình.

## 9. Exception xảy ra ở đâu và response hình thành thế nào?

Một request có thể thất bại trước, trong hoặc sau method:

| Chặng | Nguyên nhân | Exception/thành phần đại diện | Status thường gặp |
| --- | --- | --- | --- |
| Handler matching | Path không có route | Cơ chế mapping/static resource/no-handler | 404 |
| Handler matching | Method không được chấp nhận | `HttpRequestMethodNotSupportedException` | 405 |
| Handler matching/media type | `consumes` không phù hợp | `HttpMediaTypeNotSupportedException` | 415 |
| Argument resolution | Thiếu `@RequestParam` bắt buộc | `MissingServletRequestParameterException` | 400 |
| Argument resolution | Path/query conversion thất bại | `MethodArgumentTypeMismatchException` | 400 |
| Message conversion | Body JSON không đọc được | `HttpMessageNotReadableException` | 400 |
| Bean Validation | `@Valid @RequestBody` không hợp lệ | `MethodArgumentNotValidException` hoặc lỗi method validation tùy tình huống | 400 |
| Controller business | Không tìm thấy tài nguyên | Controller trả 404 / exception có mapping phù hợp | 404 |
| Return conversion | Không tạo được media type mà client yêu cầu | `HttpMediaTypeNotAcceptableException` | 406 |
| Bất kỳ chặng | Lỗi không xử lý được | Exception mapping / container | Có thể 500 |

Trong MVC, `DispatcherServlet` phối hợp các `HandlerExceptionResolver`. Cơ chế phổ biến gồm `ExceptionHandlerExceptionResolver` (xử lý `@ExceptionHandler`/advice), `ResponseStatusExceptionResolver` (ví dụ `@ResponseStatus`, `ResponseStatusException`) và `DefaultHandlerExceptionResolver` (các lỗi MVC phổ biến). Thứ tự cấu hình và tùy chỉnh quyết định resolver nào xử lý trước.

**Đừng bọc mọi exception rồi trả HTTP 200** chỉ để tránh lỗi ở frontend. Khi tạo API, hãy tách lỗi client có thể khắc phục, lỗi nghiệp vụ đã xác định và lỗi hạ tầng bất ngờ; sử dụng status cùng một schema lỗi ổn định.

### 9.1. @RestControllerAdvice để chuẩn hóa lỗi

Ví dụ minh họa một error handler trong ứng dụng Spring MVC (phải đặt trong component scan):

~~~java
@RestControllerAdvice
class ApiErrors {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> badInput(
            IllegalArgumentException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", ex.getMessage()));
    }
}
~~~

Đoạn class này cần import `java.util.Map`, `ResponseEntity`, `@ExceptionHandler`, `@RestControllerAdvice`. Ví dụ chỉ định nghĩa mapping cho một loại exception để minh họa. **Không nên tự động trả nguyên `ex.getMessage()` cho mọi loại exception trong production**, vì có thể làm lộ dữ liệu nội bộ; với lỗi không được tin cậy, dùng message an toàn và log chi tiết ở server.

`@RestControllerAdvice` là cơ chế chọn exception handler trước khi kết quả được viết ra. Nó **không đảm bảo** thay được phản hồi đã committed, cũng không xử lý mọi lỗi trong security filter/container nằm ngoài phạm vi exception resolution của MVC.

## 10. Xử lý giá trị trả về bất đồng bộ

Spring MVC hỗ trợ trả các wrapper async mà vẫn dùng Servlet stack. Ví dụ **method minh họa**:

~~~java
@GetMapping("/reports/{id}")
public Callable<ResponseEntity<String>> report(@PathVariable long id) {
    return () -> ResponseEntity.ok("report-" + id);
}
~~~

Ý nghĩa:
1. Handler method đầu tiên trả một `Callable`, thay vì body cuối ngay lập tức.
2. Spring MVC bắt đầu xử lý async với Servlet async support và một executor thích hợp.
3. Khi `Callable` hoàn thành, kết quả `ResponseEntity<String>` được đưa trở lại pipeline xử lý return value.
4. Response cuối cùng có thể được ghi ở giai đoạn async dispatch.

Đoạn này cần đặt trong controller Spring MVC và import `Callable`, `ResponseEntity`, `@GetMapping`, `@PathVariable`; dùng executor được cấu hình phù hợp với tải thực tế. `DeferredResult<T>` có thể được hoàn tất bởi một callback/thread khác; đó không phải bảo đảm mọi thao tác I/O của MVC đều non-blocking. Nếu timeout hoặc exception xảy ra trong async processing, xử lý lỗi cần xét cả async lifecycle.

Đừng coi `Callable<ResponseEntity<T>>` là một “return type lạ không serialize được”: async mechanism lấy kết quả cuối rồi **tiếp tục dùng return-value handlers** cho `ResponseEntity<T>`.

## 11. Custom argument resolver: khi nào cần?

Nếu ứng dụng thường xuyên cần trích một dữ liệu miền nghiệp vụ từ request (ví dụ tenant ID đã được xác thực), có thể viết `HandlerMethodArgumentResolver` riêng:

~~~java
@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface CurrentTenant {}
~~~

Đoạn annotation cần imports `java.lang.annotation.ElementType`, `Retention`, `RetentionPolicy`, `Target` và đặt ở **`CurrentTenant.java`** nếu là public top-level annotation. Resolver tương ứng sẽ implement `supportsParameter` và `resolveArgument`, có thể đọc trusted context trong request; khai báo qua `WebMvcConfigurer.addArgumentResolvers`.

Ví dụ sử dụng sau khi đã **thật sự đăng ký resolver**:

~~~java
@GetMapping("/tenant-info")
public String tenant(@CurrentTenant String tenantId) {
    return tenantId;
}
~~~

Đây là **mã minh họa, chưa phải chương trình chạy độc lập** vì chưa định nghĩa implementation của resolver hoặc cấu hình bảo mật và chưa gắn vào controller. Không dùng `@CurrentTenant` nếu chưa có resolver hỗ trợ. Khi code cần path/query/header tiêu chuẩn, dùng built-in resolver; tự viết resolver chỉ cho abstraction có ý nghĩa thực sự.

Các lưu ý nếu viết resolver:
- Tránh trùng với resolver mặc định hoặc chọn tham số quá rộng (ví dụ nhận mọi `String`).
- Chỉ dựa vào thông tin tenant/principal đã được **xác thực**; không tin raw `X-Tenant` từ Internet.
- Quyết định xử lý lỗi thiếu hoặc sai tenant bằng exception có HTTP mapping rõ ràng.
- Resolver thường được chia sẻ giữa request, nên không lưu trạng thái từng request trong các mutable instance fields.

## 12. Những nhầm lẫn phổ biến cần sửa

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`@GetMapping` tự truyền tham số vào Java method.” | Handler mapping chọn method; argument resolver chuẩn bị Java arguments. |
| “`@PathVariable long` luôn match thất bại khi URL chứa chữ.” | Handler path có thể match, rồi lỗi xảy ra khi conversion `String → long`. |
| “`@RequestBody` và `@ModelAttribute` giống nhau.” | Một bên đọc message content qua converter, bên kia bind request parameters vào model object. |
| “Có `@Valid` thì controller luôn chạy rồi mới thấy lỗi.” | Validation có thể dừng ở argument resolution trước khi method được gọi. |
| “`BindingResult` đặt đâu cũng được.” | Đặt ngay sau argument mà nó mô tả. |
| “`@RestController` bắt buộc trả JSON.” | Body serialization theo converter và content negotiation; `String` có thể là text. |
| “Return `String` luôn là HTTP body.” | Trong `@Controller` không có `@ResponseBody`, `String` thường là tên view. |
| “Return `void` luôn là 204.” | Status/view/body tùy annotation, context và response đã được xử lý. |
| “`ResponseEntity` tự JSON hóa đối tượng.” | Return-value handler xử lý status/headers; message converter serialize body. |
| “Handler đã match thì chắc chắn controller chạy.” | Resolver, conversion, validation, interceptor hoặc filter có thể ngăn chạy. |
| “Validation lỗi luôn là một loại exception.” | Spring MVC có các đường validation khác nhau, nhất là method validation. |
| “Controller singleton lưu request field là an toàn.” | Mutable field bị chia sẻ giữa requests và cần thiết kế thread-safe. |

## 13. Bài tập tự kiểm tra và đáp án

**Bài 1.** Xét method:

~~~java
@GetMapping("/books/{id}")
public ResponseEntity<BookResponse> get(
        @PathVariable long id,
        @RequestParam(defaultValue = "vi") String lang,
        @RequestHeader("X-Client") String client) {
    // ...
}
~~~

Với `GET /books/7?lang=en` không có header `X-Client`, controller có được gọi không? Lỗi thường xảy ra ở bước nào?

**Bài 2.** Một HTML controller trả `"books/index"`, một REST controller trả `"books/index"`. Hai phản hồi có nhất thiết giống nhau không?

**Bài 3.** POST JSON với `Content-Type: application/json` nhưng body hỏng cú pháp. Spring có nhất thiết vào controller rồi trả 500 không?

**Bài 4.** Controller nhận `@Valid @RequestBody CreateBookRequest body`; body hợp lệ về cú pháp JSON nhưng trường `title` vi phạm `@NotBlank`. Bước nào xử lý lỗi? Mã HTTP thường gặp?

**Bài 5.** Với `ResponseEntity.created(URI.create("/api/books/42")).body(dto)`, thành phần nào đặt status/headers, thành phần nào viết JSON body?

**Bài 6.** Tại sao `Callable<ResponseEntity<String>>` vẫn có thể trả HTTP status và body đúng, dù method ban đầu không trả `ResponseEntity` trực tiếp?

### Đáp án giải thích

1. `@RequestHeader("X-Client")` mặc định required. Không có header này, argument resolution thường báo lỗi thiếu request header, phản hồi 400; method chưa được gọi.
2. Không. HTML `@Controller` có thể coi chuỗi là **view name**; `@RestController` coi nó là **response body**.
3. Không. Converter thường báo `HttpMessageNotReadableException` trong lúc tạo `@RequestBody`; xử lý mặc định thường là 400 trước khi method chạy.
4. Sau khi converter tạo DTO, validation thực thi constraint; Spring thường phản hồi 400 thông qua exception handling nếu không có `BindingResult` phù hợp.
5. `HandlerMethodReturnValueHandler` dành cho `ResponseEntity` áp dụng status 201 và `Location`; `HttpMessageConverter` được chọn serialize `dto` thành JSON.
6. Spring MVC nhận ra wrapper async, chờ kết quả, rồi xử lý `ResponseEntity<String>` bằng return-value mechanism trong giai đoạn tiếp tục xử lý.

## 14. Checklist khi đọc hoặc xây một controller Spring MVC

Khi một endpoint không trả như mong đợi, đọc theo thứ tự:

1. **Handler:** Method/path/headers/consumes/produces có match? `HandlerMapping` chọn method nào?
2. **Arguments:** Từng argument đến từ đâu? Có required/default, conversion, multipart/body converter không?
3. **Binding và validation:** DTO được bind theo cơ chế nào? Có lỗi field/constraint trước method không?
4. **Invocation:** Có filter/interceptor/AOP/service exception? Controller singleton có dùng mutable shared state sai không?
5. **Return value:** `String` là view name hay body? `ResponseEntity` đặt status/header nào? Converter có thể ghi media type client yêu cầu không?
6. **Errors và async:** Exception resolver nào xử lý; response đã committed chưa; có async dispatch/timeout không?
7. **Quan sát thực tế:** Xem network status, headers, body và log/tracing; không kết luận chỉ từ một annotation.

Khi hiểu rõ ba chặng **resolve tham số → gọi controller → xử lý giá trị trả về**, bạn sẽ biết được vì sao một Java method không được gọi, vì sao cùng một `String` lại thành trang HTML hoặc HTTP body, và vì sao một object Java cần message converter trước khi tới client.

**Tài liệu tham khảo chính thức:** Spring Framework MVC *Annotated Controllers – Method Arguments* (https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html), *Return Values* (https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html), *@RequestBody* (https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html), *@ResponseBody* (https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html) và *ResponseEntity* (https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html).