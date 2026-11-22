# @Controller, @RestController và trách nhiệm của lớp tiếp nhận yêu cầu

Khi xây dựng API hoặc ứng dụng web bằng Spring Boot, controller là điểm tiếp nhận HTTP request và chuyển yêu cầu đó vào phần còn lại của hệ thống. Hai annotation thường gặp nhất là `@Controller` và `@RestController`. Chúng đều cho phép Spring MVC tìm handler qua `@RequestMapping`, `@GetMapping`, `@PostMapping`..., nhưng **cách diễn giải giá trị trả về** khác nhau: controller hướng đến view khi cần render giao diện, còn REST controller thường ghi dữ liệu trực tiếp vào HTTP response body.

Bài này tập trung vào **Spring MVC thuộc Servlet stack của Spring Boot 3.x, Java 17+**. Mục tiêu là hiểu cơ chế định tuyến, phân biệt view và response body, chọn kiểu input/output đúng, đặt ranh giới trách nhiệm của controller với service, rồi triển khai và kiểm thử một ví dụ hoàn chỉnh. Các ví dụ ứng dụng Spring Boot cần dependency Spring Framework; không phải mã Java thuần có thể biên dịch riêng lẻ bằng `javac`.

## 1. Controller ở vị trí nào trong một HTTP request?

Một chuỗi xử lý Spring MVC tiêu biểu:

~~~text
HTTP client
    |
Servlet container (Tomcat / Jetty / Undertow)
    |
Servlet filters / security filter chain
    |
DispatcherServlet
    |
HandlerMapping -> tìm handler phù hợp với URL, HTTP method và điều kiện
    |
HandlerAdapter -> binding, conversion, validation, gọi controller method
    |
@Controller hoặc @RestController
    |
Service / domain layer -> repository, HTTP client, giao dịch và quy tắc nghiệp vụ
    |
Controller nhận kết quả nghiệp vụ
    |
    +-- Model + logical view name --> ViewResolver / template --> HTML
    |
    +-- @ResponseBody hoặc ResponseEntity --> HttpMessageConverter --> JSON/text/bytes
    |
HTTP status + headers + body
~~~

`DispatcherServlet` là front controller của Spring MVC, không phải class do ứng dụng thường tự viết. Spring Boot auto-configuration đăng ký nó và các thành phần MVC khi `spring-boot-starter-web` cùng điều kiện Servlet web application thỏa mãn.

Controller **không trực tiếp mở socket, parse toàn bộ HTTP giao thức hoặc tự serialize JSON**. Spring MVC và servlet container thực hiện những phần đó; controller khai báo metadata định tuyến và phương thức xử lý đầu vào/đầu ra ở mức ứng dụng.

Những thành phần có vai trò khác nhau:

| Thành phần | Vai trò |
|---|---|
| `DispatcherServlet` | Điều phối toàn bộ luồng Spring MVC |
| `HandlerMapping` | Quyết định request phù hợp handler nào |
| `HandlerAdapter` | Biết cách gọi handler và xử lý argument/return value |
| `WebDataBinder` / `ConversionService` | Bind và chuyển kiểu dữ liệu request |
| `HttpMessageConverter` | Đọc body thành Java object, ghi object thành HTTP body |
| `ViewResolver` | Phân giải logical view thành HTML/view thực tế |
| `HandlerExceptionResolver` | Chuyển một số exception thành HTTP response |
| `@Controller` / `@RestController` | Khai báo handler và điều phối công việc tại HTTP boundary |

## 2. @Controller là gì?

`@Controller` đánh dấu một Spring bean là thành phần controller. Annotation này chuyên biệt hóa `@Component`, nên class thường được phát hiện qua component scan của ứng dụng.

Ví dụ controller phục vụ trang HTML:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class CatalogPageController {

    @GetMapping("/catalog")
    String page(Model model) {
        model.addAttribute("title", "Danh mục sách");
        return "catalog";
    }
}
~~~

Khi trả về chuỗi `"catalog"` trong phương thức `@Controller` **không có `@ResponseBody`**, Spring MVC thường coi nó là **tên logical view**. Nếu ứng dụng có template engine như Thymeleaf, view resolver có thể tìm template `catalog.html` trong `src/main/resources/templates/`.

Điểm quan trọng:
- `@Controller` **không có nghĩa** class chỉ được trả HTML. Nó vẫn có thể trả JSON/chuỗi trực tiếp khi gắn `@ResponseBody` trên method.
- Giá trị String không tự biến thành HTML. Nó thường là tên view hoặc tên redirect/forward trong luồng view.
- Việc view có render được hay không còn phụ thuộc view resolver, template dependency, tên file và cấu hình tương ứng.
- Khi trả `ModelAndView`, controller có thể cung cấp đồng thời model và view.
- Các attribute trong `Model` phục vụ render view; không có nghĩa chúng tự được đưa vào body JSON.

Ví dụ redirect sau khi xử lý form:

~~~java
@PostMapping("/catalog/search")
String search(@RequestParam String keyword, RedirectAttributes redirect) {
    redirect.addAttribute("q", keyword);
    return "redirect:/catalog/results";
}
~~~

Đây là **đoạn minh họa**, cần thêm import và method/route phù hợp. Tiền tố `redirect:` được view-resolution infrastructure hiểu là HTTP redirect. Không nên xem `"redirect:/..."` là response text trong controller không có `@ResponseBody`.

## 3. @RestController là gì?

`@RestController` là annotation kết hợp **`@Controller` và `@ResponseBody`** ở cấp class. Nó vẫn được Spring MVC phát hiện như controller thông thường nhưng mặc định các handler method trả về dữ liệu để ghi trực tiếp vào HTTP response.

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class StatusController {

    @GetMapping("/api/status")
    String status() {
        return "READY";
    }
}
~~~

Đối với HTTP GET `/api/status`, body sẽ chứa text `READY`, **không** tìm template view tên `READY`.

Khi REST controller trả Java object/record, Spring MVC dùng một `HttpMessageConverter` phù hợp, thường là Jackson JSON converter khi dependency Jackson có mặt:

~~~java
record StatusResponse(String status, int activeJobs) {}

@RestController
class StatusApiController {

    @GetMapping("/api/status")
    StatusResponse status() {
        return new StatusResponse("READY", 3);
    }
}
~~~

Body JSON điển hình:

~~~json
{"status":"READY","activeJobs":3}
~~~

Không nên diễn giải `@RestController` thành “luôn trả JSON”. Ví dụ method trả `String` có thể được ghi như text; method trả `byte[]` hoặc `ResponseEntity<Resource>` có thể ghi nội dung khác tùy converter, header `Accept` và metadata của handler. Annotation này chủ yếu quyết định **trả response body thay vì view name**.

## 4. So sánh @Controller, @ResponseBody và @RestController

| Class/method | Trả về `String "home"` | Trả về DTO/record | Dùng cho |
|---|---|---|---|
| `@Controller` không có `@ResponseBody` | Thường là logical view name `home` | Không mặc định serialize object như API; phụ thuộc return-value handler/model | MVC pages |
| `@Controller` có `@ResponseBody` trên method | Body text `home` | Converter ghi DTO vào body | Kết hợp trang HTML và API trong một class |
| `@RestController` | Body text `home` | Converter ghi DTO vào body | REST/JSON hoặc API trả dữ liệu |

Cùng một class `@Controller` vẫn có thể phục vụ hai kiểu response:

~~~java
@Controller
class MixedController {

    @GetMapping("/about")
    String aboutPage() {
        return "about";  // logical view
    }

    @ResponseBody
    @GetMapping("/api/about")
    String aboutText() {
        return "About this service";  // response body
    }
}
~~~

Có thể đặt `@ResponseBody` ở mức class, nhưng khi phần lớn method là API thì `@RestController` truyền tải ý định rõ hơn. Ngược lại, nếu class chủ yếu render view, dùng `@Controller` giúp tránh nhầm String thành body.

**Một quy ước thiết kế tốt:** tách controller API và controller phục vụ trang khi hợp đồng HTTP, security hoặc cách test khác nhau. Đây là hướng tổ chức dễ bảo trì, không phải giới hạn bắt buộc của framework.

## 5. Annotation định tuyến và điều kiện chọn handler

Spring MVC ánh xạ request tới method nhờ `@RequestMapping` và các annotation rút gọn:

- `@GetMapping`: GET.
- `@PostMapping`: POST.
- `@PutMapping`: PUT.
- `@PatchMapping`: PATCH.
- `@DeleteMapping`: DELETE.
- `@RequestMapping`: biểu diễn tổng quát, có thể kết hợp method/path/header/params/consumes/produces.

Ví dụ:

~~~java
@RestController
@RequestMapping("/api/books")
class BookRoutes {

    @GetMapping("/{id}")
    String read(@PathVariable long id) {
        return "book-" + id;
    }

    @GetMapping(params = "featured=true")
    String featured() {
        return "featured";
    }
}
~~~

Class-level mapping và method-level mapping được kết hợp: method đầu xử lý `GET /api/books/5`, method thứ hai xử lý `GET /api/books?featured=true`. Tuy nhiên, **không nên thiết kế nhiều method có mapping mơ hồ**. Nếu hai handler khớp cùng request với độ ưu tiên không phân định rõ, có thể phát sinh lỗi ambiguous mapping hoặc chọn handler ngoài dự kiến.

Điều kiện thường dùng:

~~~java
@PostMapping(
    path = "/api/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
BookResponse create(@RequestBody BookRequest request) {
    // ...
}
~~~

- `path`: URL handler nhận.
- `consumes`: loại media của request body mà handler chấp nhận, đối chiếu với `Content-Type`.
- `produces`: loại media của response mà handler hỗ trợ, cùng với `Accept` của client.
- `params`: điều kiện có hoặc giá trị query parameter.
- `headers`: điều kiện dựa trên HTTP request headers.

Một request đi sai HTTP method có thể trả **405 Method Not Allowed**; media type request không được chấp nhận có thể trả **415 Unsupported Media Type**; client `Accept` định dạng không thể cung cấp có thể dẫn đến **406 Not Acceptable**. Các lỗi này khác nhau về nguyên nhân; đừng xử lý tất cả như lỗi JSON parse.

Nên đặt URL theo resource và resource hierarchy, tránh tên kiểu `/api/doCreateBookNow` khi hợp đồng HTTP phù hợp hơn với `POST /api/books`.

## 6. Controller nhận dữ liệu request như thế nào?

Không phải tất cả dữ liệu HTTP đều đi qua một annotation duy nhất.

| Nguồn dữ liệu | Annotation/API thường dùng | Ví dụ |
|---|---|---|
| Biến trong URL | `@PathVariable` | `GET /books/10` -> id=10 |
| Query parameter | `@RequestParam` | `GET /books?page=2` |
| Header | `@RequestHeader` | `Accept-Language: vi` |
| Cookie | `@CookieValue` | `session=...` |
| JSON/XML request body | `@RequestBody` | JSON DTO |
| Form/query data thành command object | `@ModelAttribute` | Form tìm kiếm |
| Multipart file/part | `@RequestPart`, `MultipartFile` hoặc `@RequestParam` | Upload file |
| Metadata HTTP | `HttpServletRequest`, `HttpHeaders`, `UriComponentsBuilder`... | Chỉ khi thật sự cần |
| View model | `Model` | Dữ liệu render template |

Ví dụ phân biệt path, query và header:

~~~java
@GetMapping("/api/books/{id}")
BookResponse find(
        @PathVariable long id,
        @RequestParam(defaultValue = "false") boolean verbose,
        @RequestHeader(name = "X-Trace-Id", required = false) String traceId) {
    // Chỉ là ví dụ khai báo signature.
    // Controller truyền id/verbose vào service, traceId có thể dùng observability.
    return service.find(id);
}
~~~

Mã trên là đoạn minh họa, giả định `service.find` có kiểu trả về tương ứng. Request `GET /api/books/7?verbose=true` mang id ở path và verbose ở query; header không có thì `traceId` có thể null.

Một số lỗi phổ biến:
- `@PathVariable long id` nhận `/books/abc`: conversion từ String sang long thất bại, thường dẫn tới **400**.
- `@RequestParam int page` thiếu query param bắt buộc: thường **400**, trừ khi cấu hình `required=false`/default phù hợp.
- `@RequestBody` nhận JSON lỗi cú pháp: message converter có thể phát `HttpMessageNotReadableException` -> thường **400**.
- Body JSON gửi sai `Content-Type` với `consumes`: thường **415**.
- `@ModelAttribute` không đồng nghĩa deserialization JSON trong request body. Nó hướng đến binding request parameters/form data vào object và cần quản lý tập field cho phép bind.

Spring MVC còn xử lý content negotiation, type conversion và validation trước khi handler được chạy. Vì thế không phải lỗi đầu vào nào cũng đến được dòng đầu tiên của method controller.

## 7. DTO và @RequestBody: giữ ranh giới dữ liệu

Khi API tạo hoặc cập nhật resource, nên nhận một **request DTO** biểu diễn dữ liệu client được phép gửi, không bind tùy ý vào JPA entity.

Ví dụ Java record cho dữ liệu tạo sách:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateBookRequest(
    @NotBlank @Size(max = 100) String title
) {}
~~~

Record phù hợp với DTO bất biến đơn giản trên Java 17. Với dependency Jackson phù hợp, Spring MVC có thể tạo record từ JSON:

~~~http
POST /api/books HTTP/1.1
Content-Type: application/json

{"title":"Clean Architecture"}
~~~

Controller khai báo:

~~~java
@PostMapping("/api/books")
ResponseEntity<BookResponse> create(
        @Valid @RequestBody CreateBookRequest request) {
    // gọi service và trả response
}
~~~

`@RequestBody` yêu cầu converter đọc JSON thành Java object. `@Valid` yêu cầu kiểm tra Bean Validation nếu có implementation tương ứng trên classpath, thường thông qua `spring-boot-starter-validation` trong ứng dụng Boot 3.x.

**Lý do không bind trực tiếp entity:** một entity có thể chứa các field như `id`, `role`, `priceApproved`, `isAdmin` hoặc thuộc tính quan hệ nội bộ. Client không nên được quyền tự cung cấp mọi field chỉ vì entity có setter. DTO thiết kế riêng giúp ngăn over-posting/mass assignment, tách hợp đồng API khỏi schema persistence và dễ versioning hơn.

DTO của HTTP boundary cũng không nhất thiết trùng với domain command; khi hệ thống phức tạp có thể chuyển request DTO thành command rõ ràng trước khi gọi service.

## 8. Validation: chọn đúng tầng chịu trách nhiệm

Controller nên kiểm tra **tính hợp lệ của dữ liệu HTTP** trước khi chuyển đến nghiệp vụ:
- Field bắt buộc có mặt không?
- Định dạng và độ dài có đúng contract không?
- JSON có parse được không?
- Query/path argument có chuyển sang kiểu Java hợp lệ không?
- Một số ràng buộc đơn giản như `@NotBlank`, `@Size`, `@Min` có phù hợp không?

Ví dụ:

~~~java
public record CreateBookRequest(
    @NotBlank(message = "title must not be blank")
    @Size(max = 100)
    String title
) {}
~~~

Khi có `@Valid @RequestBody` và validator phù hợp, request có `"title":""` thường bị từ chối với **400 Bad Request** trước khi method controller hoàn tất. Chi tiết body lỗi mặc định phụ thuộc Spring Boot, `server.error.*`, Problem Details và handler ứng dụng.

**Nhưng quy tắc nghiệp vụ không nên chỉ nằm ở annotation DTO**. Ví dụ “không được mượn sách quá số lượng cho phép”, “không thể hủy đơn đã hoàn tất” hoặc “không thể tạo mã trùng” đòi hỏi trạng thái nghiệp vụ và sự nhất quán dữ liệu: hãy thực hiện ở service/domain và bảo vệ bằng transaction/constraint tương ứng.

Không nên chỉ dựa vào validation HTTP. Service có thể được gọi từ scheduler, message consumer, CLI hoặc test mà không đi qua controller; những business invariant quan trọng vẫn phải được đảm bảo bên dưới tầng HTTP.

## 9. Controller quyết định HTTP status, header và body

Với `@RestController`, nếu method trả object thành công và không cấu hình status riêng, status phổ biến là **200 OK**. Nhưng một API có hợp đồng REST rõ ràng cần chủ động lựa chọn status:

| Trường hợp | Status thường dùng | Ghi chú |
|---|---|---|
| GET tìm thấy resource | 200 | Body chứa representation |
| GET không tìm thấy resource | 404 | Tránh trả 200 với giá trị rỗng khó phân biệt |
| POST tạo resource thành công | 201 | Nên có `Location` chỉ đến resource mới |
| POST hợp lệ nhưng xử lý bất đồng bộ | 202 | Chỉ dùng nếu thực sự mới nhận xử lý, chưa hoàn tất |
| PUT cập nhật thành công | 200 hoặc 204 | Tùy có trả body |
| DELETE thành công | 204 | Không gửi body |
| JSON sai/validation không đạt | 400 | Phân biệt với lỗi domain |
| Xung đột với trạng thái hiện tại | 409 | Ví dụ version/conflict khi phù hợp |
| Không được xác thực | 401 | Security framework xử lý theo chính sách |
| Có xác thực nhưng không được phép | 403 | Cần chính sách security |

`ResponseEntity<T>` cho phép kiểm soát status, headers và body theo từng nhánh:

~~~java
@GetMapping("/api/books/{id}")
ResponseEntity<BookResponse> find(@PathVariable long id) {
    return service.findById(id)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
}
~~~

`ResponseEntity.created(location).body(value)` trả **201 Created** và header `Location`. `ResponseEntity.noContent().build()` trả **204 No Content**. Khi body thực sự rỗng, không trả String rỗng chỉ để giả lập 204.

`@ResponseStatus(HttpStatus.CREATED)` phù hợp khi một method luôn trả cùng status. `ResponseEntity` linh hoạt hơn khi cần status/header khác nhau theo kết quả xử lý.

Lưu ý: nếu trả về `String` từ REST controller, đó là body text; Spring không tự đánh dấu status 201 hay tự sinh `Location` chỉ vì method được đặt tên `create`.

## 10. @Controller và view rendering cho HTML

Khi xây giao diện server-rendered, `@Controller` thường đưa dữ liệu vào `Model` và trả tên template:

~~~java
@Controller
class BooksPageController {

    private final BookService service;

    BooksPageController(BookService service) {
        this.service = service;
    }

    @GetMapping("/books")
    String listPage(Model model) {
        model.addAttribute("books", service.list());
        return "books";
    }
}
~~~

Với dependency `spring-boot-starter-thymeleaf`, Boot thường cấu hình view resolver tìm file:

~~~text
src/main/resources/templates/books.html
~~~

Template có thể dùng Thymeleaf để render danh sách sách:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Books</title></head>
<body>
  <h1>Books</h1>
  <ul>
    <li th:each="book : ${books}" th:text="${book.title}"></li>
  </ul>
</body>
</html>
~~~

Khi method trả `"books"` từ `@Controller`, template sẽ được render thành HTML. Nếu đổi class thành `@RestController` mà vẫn trả `"books"`, client chỉ nhận body text `books`; **template sẽ không được chọn** theo cơ chế return-value đó.

Trong Spring MVC, `@ModelAttribute` có thể đóng góp dữ liệu cho view và bind form. Controller phục vụ form nên cân nhắc Post/Redirect/Get để tránh trình duyệt gửi lại POST khi refresh, và dùng cơ chế CSRF protection khi có phiên đăng nhập.

## 11. Trách nhiệm nên có của lớp controller

Controller là **HTTP adapter**. Một controller tốt tập trung vào:

1. Khai báo tuyến và điều kiện nhận request (path/method/headers/media types).
2. Nhận và bind dữ liệu đầu vào thành request DTO hoặc argument rõ ràng.
3. Kích hoạt validation mức transport/contract.
4. Xác định context đầu vào cần thiết, chẳng hạn identity từ security context, locale, correlation id nếu bài toán cần.
5. Gọi service/use case phù hợp, truyền dữ liệu đã được kiểm tra.
6. Ánh xạ kết quả hoặc lỗi nghiệp vụ thành response DTO, HTTP status và headers.
7. Với MVC HTML, chuẩn bị model và logical view; với API, trả response body phù hợp.
8. Giữ method ngắn, dễ test và không phụ thuộc quá sâu vào hạ tầng lưu trữ.

Đây là **trách nhiệm điều phối tại ranh giới HTTP**, không phải xử lý mọi nghiệp vụ của hệ thống.

Những việc nên tránh đặt trực tiếp vào controller:
- Viết SQL/JPA query, tạo transaction nhiều bước hoặc quản lý kết nối database.
- Tính toán nghiệp vụ phức tạp, thay đổi trạng thái theo quy tắc domain.
- Gọi nhiều downstream service theo luồng dài mà không có timeout/transaction policy.
- Gửi email, xuất báo cáo lớn, chạy batch job lâu trong request thread mà không có kế hoạch async.
- Tự viết logic xác thực/ủy quyền thay cho Spring Security.
- Ghi log toàn bộ password/token/PII hoặc trả stack trace nội bộ cho client.
- Cho phép client tự đặt ID, status, role hoặc giá trị nhạy cảm không thuộc hợp đồng API.

Ranh giới đơn giản:

~~~text
HTTP Controller -> Application Service / Use Case -> Repository / Gateway
       |                    |
  DTO, status, headers      business rules, consistency, transactions
       |
  Spring MVC (binding, validation, converters)
~~~

Một số dự án nhỏ có thể có controller khá gọn và service chỉ là một lớp, nhưng việc giữ ranh giới này vẫn giúp tái sử dụng nghiệp vụ từ các entry point khác (event consumer, scheduler, batch).

## 12. Service thực hiện nghiệp vụ, controller diễn đạt kết quả qua HTTP

Một cách tách trách nhiệm phổ biến:

~~~java
@Service
class BookingService {
    private final BookingRepository repository;

    BookingService(BookingRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public BookingResult reserve(ReserveCommand command) {
        // Kiểm tra nghiệp vụ, cập nhật dữ liệu, bảo toàn transaction.
        return repository.reserve(command);
    }
}
~~~

Đây là đoạn **minh họa kiến trúc**, không phải mã có đủ class để chạy riêng. `@Transactional` thuộc Spring transaction management, chỉ có ý nghĩa khi có transaction manager và proxy/cấu hình thích hợp.

Controller gọi service:

~~~java
@RestController
@RequestMapping("/api/reservations")
class ReservationController {
    private final BookingService service;

    ReservationController(BookingService service) {
        this.service = service;
    }

    @PostMapping
    ResponseEntity<ReservationResponse> reserve(
            @Valid @RequestBody ReserveRequest request) {
        BookingResult result = service.reserve(toCommand(request));
        return ResponseEntity
            .created(URI.create("/api/reservations/" + result.id()))
            .body(toResponse(result));
    }
}
~~~

Ở ví dụ minh họa, `ReserveRequest`, `ReserveCommand`, `BookingResult` và mapper `toCommand`/`toResponse` là những kiểu/method do ứng dụng định nghĩa. Ý chính là controller **không cần biết** service dùng JPA, JDBC, HTTP client hay in-memory store.

Trong ứng dụng MVC Servlet, method controller chạy đồng bộ trên request thread theo mặc định. Nếu service gọi blocking I/O lâu, tăng số controller không làm hệ thống tự non-blocking. Async MVC và Spring WebFlux là các mô hình riêng cần xử lý lifecycle, thread và backpressure phù hợp.

## 13. Xử lý lỗi với @ControllerAdvice và @RestControllerAdvice

Một exception có thể được Spring MVC bắt và chuyển thành HTTP response thông qua các `HandlerExceptionResolver`, trong đó có logic `@ExceptionHandler` của controller/advice.

`@ControllerAdvice` cung cấp xử lý dùng chung cho nhiều controller. `@RestControllerAdvice` kết hợp `@ControllerAdvice` với `@ResponseBody` để exception handler trả body trực tiếp; nó phù hợp cho REST API.

Ví dụ xử lý một domain exception:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(DuplicateBookException.class)
    ProblemDetail duplicate(DuplicateBookException ex) {
        ProblemDetail problem =
            ProblemDetail.forStatusAndDetail(HttpStatus.CONFLICT, ex.getMessage());
        problem.setTitle("Book conflict");
        return problem;
    }
}
~~~

Đây là snippet minh họa, ứng dụng phải định nghĩa `DuplicateBookException`. Với Spring Framework 6 / Boot 3.x, `ProblemDetail` là kiểu thể hiện lỗi theo chuẩn problem details; cần cấu hình và xử lý nhất quán với các exception handler khác.

Tránh bắt `Exception` quá rộng rồi luôn trả HTTP 200, vì làm mất semantics lỗi và khiến monitoring sai. Đừng gửi exception message nội bộ cho client nếu nó có thể chứa SQL, đường dẫn file, token hoặc dữ liệu nhạy cảm.

Một số lỗi đầu vào như malformed JSON và Bean Validation được Spring xử lý trước khi logic service chạy. Có thể tùy chỉnh chúng qua `ResponseEntityExceptionHandler` hoặc exception handler phù hợp, nhưng phải kiểm soát cụ thể status và response contract.

Với `@Controller` render view, error handling có thể trả tên trang lỗi; với REST API, nên trả body lỗi rõ ràng và status đúng. Không nên dùng một error response duy nhất cho cả HTML page và JSON client nếu hợp đồng của hai loại khác nhau.

## 14. Security và cross-cutting concerns không phải chức năng tự có của controller

`@RestController` **không có nghĩa API được bảo vệ**. Authentication, authorization, CSRF và session/cookie behavior phải được cấu hình bằng hạ tầng thích hợp, phổ biến là Spring Security và servlet filter chain.

Một số lưu ý:
- Xác thực và phân quyền ở filter/security layer hoặc method security tùy yêu cầu; controller có thể truy cập principal hoặc identity đã được xác minh.
- Mã nghiệp vụ phải giữ invariant quan trọng, không chỉ tin vào role/ID client gửi.
- CORS không thay authorization. Một frontend được phép gọi cross-origin không đồng nghĩa có quyền truy cập dữ liệu.
- `HandlerInterceptor` có thể phục vụ tracing/logging chung, nhưng không thay thế hoàn toàn security filter.
- Controller không nên tự mở transaction trong từng method nếu application service mới là nơi biết ranh giới nghiệp vụ.
- Request/response logging phải loại bỏ secret, token và dữ liệu nhạy cảm.

Một controller có thể lấy user identity đã xác thực bằng `Principal` hoặc `@AuthenticationPrincipal` khi Spring Security có mặt. Không lấy user ID từ query param rồi mặc định coi đó là người đăng nhập.

## 15. Ví dụ hoàn chỉnh có thể chạy: REST API và trang HTML

Ví dụ dùng **Spring Boot 3.3.x và Java 17+**, `spring-boot-starter-web`, Thymeleaf, Bean Validation và Spring Boot test. Mục đích là minh họa hai kiểu controller cùng dùng một service, không cần database. Dữ liệu lưu trong bộ nhớ nên mất khi restart.

Tạo project Spring Boot với các dependency: **Spring Web, Thymeleaf, Validation, Spring Boot Test**. Nếu dùng Gradle, hãy để project initializer sinh wrapper/Gradle plugin phù hợp, sau đó đảm bảo dependencies tương đương:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Nếu xây dựng project thủ công, cần plugin Spring Boot và thiết lập Java 17 tương ứng; đoạn `dependencies` ở trên là phần khai báo dependency, **không phải toàn bộ file build.gradle độc lập**.

### 15.1. Java application: một file chứa main, DTO, service và hai controller

Tạo tệp `src/main/java/com/example/demo/BookApplication.java`:

~~~java
package com.example.demo;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.stereotype.Service;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BookApplication {

    public static void main(String[] args) {
        SpringApplication.run(BookApplication.class, args);
    }
}

record CreateBookRequest(
    @NotBlank @Size(max = 100) String title
) {}

record BookResponse(long id, String title) {}

@Service
class BookService {
    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentMap<Long, BookResponse> books =
        new ConcurrentHashMap<>();

    BookResponse create(CreateBookRequest request) {
        long id = nextId.incrementAndGet();
        BookResponse book =
            new BookResponse(id, request.title().trim());
        books.put(id, book);
        return book;
    }

    Optional<BookResponse> findById(long id) {
        return Optional.ofNullable(books.get(id));
    }

    List<BookResponse> list() {
        return books.values().stream()
            .sorted(Comparator.comparingLong(BookResponse::id))
            .toList();
    }
}

@RestController
@RequestMapping("/api/books")
class BookApiController {
    private final BookService service;

    BookApiController(BookService service) {
        this.service = service;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    List<BookResponse> list() {
        return service.list();
    }

    @GetMapping(
        path = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<BookResponse> findById(@PathVariable long id) {
        return service.findById(id)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<BookResponse> create(
            @Valid @RequestBody CreateBookRequest request) {
        BookResponse created = service.create(request);
        URI location = URI.create("/api/books/" + created.id());
        return ResponseEntity.created(location).body(created);
    }
}

@Controller
class BookPageController {
    private final BookService service;

    BookPageController(BookService service) {
        this.service = service;
    }

    @GetMapping("/books")
    String listPage(Model model) {
        model.addAttribute("books", service.list());
        return "books";
    }
}
~~~

Tại sao ví dụ đúng ranh giới trách nhiệm?
- `BookApiController` khai báo contract REST: GET danh sách, GET theo ID, POST tạo resource. Nó chọn status 200/201/404 và `Location`.
- `CreateBookRequest` là DTO cho HTTP body; `@Valid` kiểm tra chuỗi rỗng và độ dài.
- `BookService` quản lý state và tạo ID. Controller không đọc/ghi map nội bộ trực tiếp.
- `BookPageController` chuẩn bị `Model` rồi trả logical view `"books"`.
- Hai controller dùng **cùng một service** nhưng tạo hai kiểu HTTP representation: JSON và HTML.
- `ConcurrentHashMap` và `AtomicLong` chỉ đủ cho demo trong một JVM. Chúng không thay database, transaction, constraint hay đồng bộ dữ liệu nhiều instance ở production.

### 15.2. Thymeleaf template

Tạo tệp `src/main/resources/templates/books.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Book catalog</title>
</head>
<body>
    <h1>Book catalog</h1>
    <p>Danh sách được lấy từ cùng service của REST API.</p>
    <ul>
        <li th:each="book : ${books}">
            <span th:text="${book.id}"></span>:
            <strong th:text="${book.title}"></strong>
        </li>
    </ul>
</body>
</html>
~~~

File này là template, không phải tài nguyên nằm ở `static/`. Thymeleaf view resolver kết hợp với `@Controller` để render HTML. Nếu `books` rỗng, danh sách `<li>` không có phần tử được lặp.

### 15.3. Chạy và thử HTTP

Trong project Gradle có wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Tạo resource mới:

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"title":"Clean Code"}'
~~~

Với ứng dụng mới và request đầu tiên, response điển hình:

~~~http
HTTP/1.1 201
Location: /api/books/1
Content-Type: application/json

{"id":1,"title":"Clean Code"}
~~~

Đây là phần response quan trọng, không liệt kê mọi header do server tạo. Request sau có thể có ID khác. Thứ tự JSON field do Jackson/record mapping thông thường quyết định, nhưng client nên parse JSON theo field chứ không phụ thuộc vị trí khóa trong chuỗi.

Đọc resource:

~~~bash
curl -i http://localhost:8080/api/books/1
~~~

Body điển hình:

~~~json
{"id":1,"title":"Clean Code"}
~~~

Danh sách JSON:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/books
~~~

Body sau một lần POST thành công:

~~~json
[{"id":1,"title":"Clean Code"}]
~~~

Trang HTML:

~~~bash
curl -i -H "Accept: text/html" http://localhost:8080/books
~~~

Response là HTML render từ `books.html`. Nó chứa danh sách từ service nhưng **không dùng JSON message converter** để tạo trang HTML.

Thử validation:

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":""}'
~~~

Kỳ vọng HTTP **400 Bad Request**, vì `@NotBlank`. Body lỗi cụ thể phụ thuộc Spring Boot configuration và exception handler nếu ứng dụng có tùy chỉnh.

Thử resource không tồn tại:

~~~bash
curl -i http://localhost:8080/api/books/99999
~~~

Kỳ vọng **404 Not Found**. Nhờ `ResponseEntity.notFound()`, nhánh này không bị nhầm với HTTP 200 và JSON `null`.

**Lưu ý về shell:** cú pháp dấu `\` để xuống dòng ví dụ là kiểu Bash. Với PowerShell nên viết curl trên một dòng hoặc dùng `curl.exe` và cú pháp quoting PowerShell phù hợp.

## 16. Kiểm thử routing và trách nhiệm của controller với MockMvc

Thêm `spring-boot-starter-test` vào test classpath. Test sau chạy Spring Boot context và gửi request qua MockMvc mà không cần mở socket HTTP thật.

Tạo tệp `src/test/java/com/example/demo/BookControllerTest.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void postCreatesBookWithLocation() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"DDD\"}"))
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"))
            .andExpect(jsonPath("$.title").value("DDD"));
    }

    @Test
    void invalidRequestReturns400() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unknownBookReturns404() throws Exception {
        mvc.perform(get("/api/books/999999"))
            .andExpect(status().isNotFound());
    }

    @Test
    void pageControllerReturnsView() throws Exception {
        mvc.perform(get("/books"))
            .andExpect(status().isOk())
            .andExpect(view().name("books"));
    }
}
~~~

Chạy bằng Gradle wrapper của project đã cấu hình JUnit Platform:

~~~bash
./gradlew test
~~~

Các test kiểm tra một **HTTP contract**, không phụ thuộc chuỗi log hoặc tự gọi method controller. `@SpringBootTest + @AutoConfigureMockMvc` phù hợp để kiểm tra wiring rộng của ứng dụng. Nếu chỉ muốn kiểm tra riêng MVC layer, `@WebMvcTest(BookApiController.class)` giúp tạo test slice, nhưng thường cần `@MockBean` hoặc cơ chế mock tương thích cho service và cấu hình test thích hợp.

Không nên chỉ unit test method Java rồi kết luận binding, Jackson, validation, exception resolution và ViewResolver đã hoạt động; các phần đó do Spring MVC cung cấp và cần test thông qua MVC infrastructure.

## 17. Spring Boot hỗ trợ sẵn những gì, controller vẫn phải tự làm gì?

Khi `spring-boot-starter-web` được bật, Spring Boot thường tự cấu hình:
- Embedded servlet container phù hợp dependency.
- `DispatcherServlet` và đăng ký servlet.
- `RequestMappingHandlerMapping` và `RequestMappingHandlerAdapter` thông qua cấu hình Spring MVC.
- Các message converter khả dụng theo classpath, thường Jackson cho JSON.
- Binding, type conversion, formatter, validation integration khi dependency và cấu hình phù hợp.
- Static resources, welcome page, một số view resolver và xử lý lỗi mặc định.
- Các properties tùy chỉnh như `spring.mvc.*`, `spring.web.resources.*` và `server.*`.

Những việc Boot **không tự biết**:
- URL nào đúng cho nghiệp vụ của hệ thống.
- DTO nào client được quyền gửi, field nào phải ẩn.
- Resource không tồn tại cần trả 404 hay hành vi domain riêng.
- Người dùng nào được phép gọi API cụ thể.
- Tính nhất quán transaction, bảo mật dữ liệu và quy tắc nghiệp vụ.
- Cách xử lý duplicate operation, idempotency key và lỗi downstream.

Trong controller, hãy dùng những auto-configuration của framework; chỉ tùy chỉnh khi cần. Nếu chỉ muốn thêm formatter, interceptor hoặc CORS mapping, hãy xem `WebMvcConfigurer` thay vì bật `@EnableWebMvc` một cách không cần thiết: `@EnableWebMvc` làm Spring Boot nhường một phần MVC auto-configuration, có thể khiến behavior mặc định thay đổi đáng kể.

## 18. HTTP semantics và tính nhất quán của hợp đồng API

Chọn annotation controller chưa đủ để một API trở thành “RESTful”. Thiết kế đúng còn bao gồm resource URI, HTTP method, status, header, representation và lỗi.

Một số quy tắc thực hành:
- GET nên an toàn về mặt nghiệp vụ: không thiết kế việc thay đổi trạng thái quan trọng như tạo đơn hàng trong GET.
- PUT theo semantics HTTP là idempotent: gửi cùng một request nhiều lần cần có cùng hiệu quả mong muốn lên resource (không có nghĩa response body luôn giống nhau).
- DELETE cũng nên được thiết kế idempotent về hiệu ứng; status 204/404 ở các lần gọi sau có thể khác theo hợp đồng.
- POST tạo resource thường trả 201 và Location; nếu xử lý bất đồng bộ có thể trả 202 khi contract phù hợp.
- Với operation có side effect và có khả năng retry, cân nhắc idempotency key để tránh tạo trùng.
- Pagination, sort và filter nên là argument/DTO rõ ràng, có giới hạn kích thước page.
- Với API public, dùng request/response DTO tách biệt domain/persistence và kiểm soát JSON field exposure.

Các quy tắc này thuộc **hợp đồng API** mà controller thể hiện. Việc đảm bảo state và transaction vẫn cần service/domain và persistence layer phía dưới.

## 19. Controller cho Spring MVC khác với WebFlux ở điểm nào?

Spring MVC và Spring WebFlux đều có annotation `@Controller`, `@RestController`, `@GetMapping` và `@RequestBody` trong namespace Spring Web, nhưng runtime xử lý request khác nhau.

- **Spring MVC** dựa trên Servlet stack và thường chạy controller đồng bộ trên servlet request thread; có hỗ trợ asynchronous return types trong những tình huống phù hợp.
- **Spring WebFlux** dùng reactive web stack và thường dùng Reactor `Mono`/`Flux`, xử lý reactive I/O và backpressure theo publisher semantics.
- Thêm `Mono` vào chữ ký method không tự biến một ứng dụng Spring MVC thành WebFlux runtime.
- Thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux` thường khiến Boot chọn Servlet MVC theo mặc định; phải xác nhận loại ứng dụng thực tế.
- Annotation giống nhau không có nghĩa được phép gọi blocking I/O tùy ý trên event loop của WebFlux.

Đề bài này tập trung vào **trách nhiệm của lớp tiếp nhận HTTP**, nguyên tắc vẫn gần nhau: controller nhận/bind request, gọi use case và trả representation; không tự thực hiện mọi nghiệp vụ.

## 20. Lỗi thường gặp và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân cần nghĩ đến | Hướng kiểm tra |
|---|---|---|
| `@Controller` trả chuỗi và nhận 404 view | Chuỗi được coi là view name, template không tồn tại | ViewResolver, template path, `@ResponseBody` có cần không |
| `@RestController` trả `"home"` thay vì HTML | Chuỗi bị ghi thẳng vào response body | Đổi sang `@Controller` hoặc trả đúng body mong muốn |
| POST JSON trả 415 | Content-Type không khớp `consumes` | Request header, media type, handler mapping |
| GET trả 406 | Header Accept không khớp `produces`/converter | Accept, converter và handler condition |
| DTO null/400 | JSON sai, binding/validation lỗi | `@RequestBody`, DTO constructors, Java record, Jackson |
| `@PathVariable` hoặc `@RequestParam` không bind | Tên argument/annotation hoặc conversion không phù hợp | Khai báo tên rõ, tham số URL, primitive/enum |
| Một URL khớp nhiều handler | Mapping trùng/mơ hồ | Class/method path, HTTP method, params/headers |
| GET resource không có nhưng trả 200/null | Controller chưa chọn status 404 | Optional/ResponseEntity/error handling |
| Request đến controller nhưng thiếu quyền | Security không được cấu hình/đang dùng logic thủ công | Filter chain, method security, ownership rule |
| Một HTTP request chạy quá lâu | Service blocking, database/downstream chậm | Tracing, timeout client, query, thread pool |
| Controller test pass nhưng endpoint production sai | Test gọi trực tiếp method, bỏ qua MVC wiring | MockMvc/integration test, config/profile |
| API lộ field nội bộ | Trả JPA entity trực tiếp | Response DTO, serialization rules |

Nếu endpoint không được gọi, theo thứ tự: xác nhận URL/context path, HTTP method, `consumes`/`produces`, security filter, mapping conditions, component scan, rồi log Spring MVC. Trong môi trường cần debug, có thể bật:

~~~properties
logging.level.org.springframework.web=DEBUG
~~~

Nếu dùng Spring Boot Actuator và được phép expose an toàn, endpoint mappings có thể cho biết các handler đã đăng ký. Tránh expose thông tin quản trị công khai hoặc log body/headers nhạy cảm.

## 21. Checklist trước khi hoàn tất một controller

- [ ] Chọn `@Controller` để render view hoặc `@RestController` để trả response body; không nhầm String view với String body.
- [ ] Dùng mapping cụ thể và HTTP method phù hợp; tránh tuyến mơ hồ.
- [ ] Tách path/query/header/body bằng annotation đúng.
- [ ] Dùng request DTO riêng, tránh bind entity/internal fields trực tiếp.
- [ ] Có validation input ở HTTP boundary và business invariant ở service/domain.
- [ ] Gọi service/use case bằng constructor injection; không đặt toàn bộ nghiệp vụ trong controller.
- [ ] Chọn status/headers/body rõ ràng, đặc biệt 201/404/204 và Location.
- [ ] Có error contract nhất quán; không trả 200 cho exception hay tiết lộ stack trace.
- [ ] Cấu hình authentication/authorization độc lập với REST annotation.
- [ ] Dùng MockMvc kiểm tra routing, media type, validation, status và representation.
- [ ] Đảm bảo có timeout, tracing và xử lý lỗi phù hợp với downstream.
- [ ] Giữ MVC auto-configuration của Boot trừ khi có lý do phải thay thế.

## 22. Tài liệu tham khảo

- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html): mô hình `@Controller` và `@RestController`.
- [Spring Framework — Request Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): điều kiện URL/HTTP method/consumes/produces.
- [Spring Framework — Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): `@PathVariable`, `@RequestParam`, `@RequestBody`, `Model`.
- [Spring Framework — Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): view name, `ResponseEntity`, response body và status.
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): auto-configuration MVC, embedded server, view, resources và errors.
- [Spring Framework — Testing MVC](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html): MockMvc và kiểm thử controller qua Spring MVC infrastructure.

**Kết luận:** `@Controller` và `@RestController` đều là lớp tiếp nhận yêu cầu HTTP trong Spring MVC. Khác biệt cốt lõi là **trả logical view** hay **ghi response body trực tiếp**. Controller nên giữ vai trò **dịch hợp đồng HTTP sang use case, rồi dịch kết quả thành HTTP response**; logic nghiệp vụ, persistence, transaction và tính nhất quán thuộc service/domain cùng các tầng thích hợp. Thiết kế ranh giới rõ ràng giúp API dễ kiểm thử, thay đổi và bảo trì mà không làm controller trở thành một “god class”.
