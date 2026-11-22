# Quy tắc chọn nơi lấy tham số và giới hạn đọc request body nhiều lần trong Spring MVC

## 1. Vì sao phải phân biệt nguồn dữ liệu của request?

Một HTTP request có **nhiều nơi chứa dữ liệu**: biến đường dẫn, query string, header, cookie, form field, multipart part, JSON/XML body, request attribute và session attribute. Chúng có mục đích khác nhau. Spring MVC không tự coi mọi dữ liệu là một tập giá trị đồng nhất; **annotation trên tham số handler** là cách nói rõ nên lấy ở đâu và chuyển kiểu thế nào.

Ví dụ request:

~~~http
POST /api/orders/42?notify=true HTTP/1.1
Host: localhost:8080
Content-Type: application/json
X-Trace-Id: abc-123
Cookie: locale=vi

{"sku":"BOOK-1","quantity":2}
~~~

Các nguồn khác nhau được đọc như sau:

| Giá trị | Nguồn HTTP | Cách nhận rõ ràng trong Spring MVC |
| --- | --- | --- |
| `42` | URI template `/orders/{orderId}` | `@PathVariable("orderId") long orderId` |
| `true` | Query `?notify=true` | `@RequestParam("notify") boolean notify` |
| `abc-123` | Header `X-Trace-Id` | `@RequestHeader("X-Trace-Id") String traceId` |
| `vi` | Cookie `locale` | `@CookieValue("locale") String locale` |
| `{"sku":"BOOK-1","quantity":2}` | JSON request body | `@RequestBody OrderInput input` |

**Quan trọng:** `@RequestParam` trong **Spring MVC (Servlet)** đọc *Servlet request parameters*. Tập này có thể bao gồm query string **và** trường form `application/x-www-form-urlencoded`, chứ không có nghĩa chỉ query. Phía Spring WebFlux có quy ước khác về nguồn `@RequestParam`, vì vậy phải biết mình đang dùng stack nào.

Mục tiêu bài học:
1. Xác định nguồn bind theo annotation và quy tắc mặc định khi bỏ annotation.
2. Chọn annotation đúng cho JSON, form và multipart; tách metadata khỏi payload.
3. Hiểu vì sao request body thông thường là luồng tiêu thụ một lần, và tương tác với việc phân tích form.
4. Tổ chức validation, logging/filter, caching và kiểm thử sao cho body không bị đọc mất trước controller.

Ví dụ tập trung vào **Spring MVC** với Java 17+, Spring Framework 6.x và Spring Boot 3.x, sử dụng Jakarta Servlet API (`jakarta.servlet`).

## 2. Spring chọn resolver cho một tham số như thế nào?

Khi `DispatcherServlet` tìm thấy handler method phù hợp, `RequestMappingHandlerAdapter` sử dụng một chuỗi `HandlerMethodArgumentResolver` để xử lý từng tham số. Resolver nào hỗ trợ kiểu/annotation sẽ tạo ra giá trị cho tham số đó. Các resolver sau có thể chuyển kiểu, bind object, giải mã body hay báo lỗi nếu dữ liệu không hợp lệ.

Sơ đồ khái niệm:

~~~text
HTTP request
    │
    ├── URL path / query ───────────────┐
    ├── headers / cookies ──────────────┤
    ├── body (JSON, form, multipart) ───┤
    ├── request attributes / session ───┤
    └── servlet context ────────────────┘
                                         ▼
                            HandlerMethodArgumentResolver
                            (xem annotation + Java type)
                                         │
                         ┌───────────────┼───────────────┐
                         ▼               ▼               ▼
                   URL/metadata     data binding    message converter
                         │               │               │
                  @PathVariable     @ModelAttribute   @RequestBody
                  @RequestParam      form/query       @RequestPart
                  @RequestHeader                      JSON/XML/part
                         └───────────────┬───────────────┘
                                         ▼
                                  Controller method
~~~

Đây là sơ đồ cơ chế, không phải một thứ tự ưu tiên cố định giữa các **nguồn HTTP**. Annotation được xử lý bởi resolver tương ứng; không có quy tắc chung kiểu “nếu thiếu ở path thì thử header rồi thử JSON”.

### 2.1. Bảng chọn nguồn

| Nhu cầu | Tham số controller | Lưu ý |
| --- | --- | --- |
| ID của tài nguyên nằm trong route | `@PathVariable("id") Long id` | Tên phải khớp `{id}` trong route |
| Giá trị đơn / nhiều giá trị từ query hoặc form | `@RequestParam("tag") List<String> tags` | Servlet params có thể gộp query và form |
| Header HTTP | `@RequestHeader("If-Match") String value` | Tên header HTTP không phân biệt hoa/thường |
| Cookie | `@CookieValue("theme") String theme` | Cookie là dữ liệu client gửi, không tự đáng tin |
| Thuộc tính do filter/interceptor đặt | `@RequestAttribute("requestId") String id` | Khác HTTP header và query |
| Giá trị đã đặt trong HTTP session | `@SessionAttribute("cartId") String id` | Khác `@SessionAttributes` dành cho model workflow |
| Dữ liệu form/query đưa vào DTO | `@ModelAttribute SearchForm form` | Data binding qua constructor/setter |
| JSON/XML body thành DTO | `@RequestBody CreateOrder input` | `HttpMessageConverter` tiêu thụ body |
| Cả body và headers | `HttpEntity<CreateOrder> request` | Cũng đọc body qua converter |
| File trong multipart | `@RequestParam("file") MultipartFile file` | Có thể dùng `@RequestPart` |
| Một part JSON trong multipart | `@RequestPart("metadata") Metadata metadata` | Đọc nội dung của *part* với converter |
| Truy cập dữ liệu thô từ Servlet | `HttpServletRequest`, `InputStream`, `Reader` | Cần hiểu trạng thái đã tiêu thụ body |
| Context/framework object | `Principal`, `Locale`, `HttpSession`, `Model` | Đây là đối tượng Spring/Servlet cung cấp, không bind từ JSON |

Không mặc định dùng `@RequestBody` cho tất cả đầu vào: path, query, header và cookie vẫn là những nguồn độc lập, có thể nhận cùng lúc với **một** DTO JSON.

### 2.2. Nếu không khai báo annotation?

Spring MVC vẫn có quy tắc dự phòng cho tham số mà các resolver chuyên biệt chưa nhận:
- Kiểu đơn giản theo `BeanUtils.isSimpleProperty` (như `String`, số, primitive, enum, nhiều kiểu thời gian phù hợp) thường được xử lý như `@RequestParam`.
- Kiểu phức tạp chưa được resolver khác hỗ trợ thường được xử lý như `@ModelAttribute`.

Ví dụ:

~~~java
@GetMapping("/search")
public String search(String q, SearchCriteria criteria) {
    // q thường lấy từ Servlet request parameters;
    // criteria thường được bind như @ModelAttribute.
    return "ok";
}
~~~

Đây là **đoạn minh họa**, với `SearchCriteria` phải là kiểu có thể bind. Không hiểu nhầm rằng `SearchCriteria` tự động nhận JSON body; muốn JSON thì cần `@RequestBody`. Nên viết annotation tường minh trên public API, đặc biệt khi triển khai có nhiều nguồn dữ liệu hoặc cần AOT/native image. Nếu bỏ tên trong annotation, việc suy ra tên Java parameter còn phụ thuộc metadata biên dịch; khai báo tên rõ giúp tránh lỗi khi đổi cấu hình compiler.

### 2.3. `required`, `defaultValue`, `Optional` và chuyển kiểu

~~~java
@GetMapping("/catalog")
public String catalog(
        @RequestParam("q") String q,
        @RequestParam(name = "page", defaultValue = "0") int page,
        @RequestHeader(name = "X-Request-Id", required = false) String requestId) {
    return q + ":" + page + ":" + requestId;
}
~~~

Ở đây `q` được yêu cầu mặc định; thiếu `q` thường bị Spring trả `400 Bad Request`. `page` có mặc định và được chuyển từ chuỗi sang `int`; nhập giá trị không phải số có thể phát sinh lỗi bind, thường là `400`. Header `X-Request-Id` tùy chọn nên có thể nhận `null`. Với annotation cho phép `required`, một tham số `Optional<T>` cũng thường diễn đạt sự vắng mặt. Chọn tên và điều kiện rõ ràng, rồi kiểm thử request thực tế.

Các giới hạn quan trọng:
- `@RequestParam Map<String,String>` **không ghi tên** có thể thu thập nhiều tham số; `MultiValueMap<String,String>` giữ được nhiều giá trị cho một tên.
- `@PathVariable` không được thay thế bằng `@RequestParam` dù hai giá trị đều là chuỗi có thể chuyển kiểu.
- Nếu form và query cùng có một tên, hành vi lấy giá trị phụ thuộc cách Servlet container gom request parameters; không thiết kế API dựa trên việc “query chắc chắn thắng form”.
- Chữ ký method dùng `@RequestBody Foo` với JSON phải khai báo converter phù hợp (Jackson thường có sẵn từ `spring-boot-starter-web`). `Content-Type` và `Accept` còn ảnh hưởng việc chọn endpoint/converter.

## 3. Chọn đúng cách đọc theo Content-Type

### 3.1. GET với query và path

~~~http
GET /api/products/15?sort=price&tag=java&tag=spring HTTP/1.1
Accept: application/json
~~~

Chọn `@PathVariable("id") long id`, `@RequestParam("sort") String sort` và `@RequestParam("tag") List<String> tags`. Không cần request body cho GET thông thường. Đừng đặt nguồn filter/sort trong JSON body rồi trông chờ mọi client, proxy, cache xử lý thống nhất.

### 3.2. POST JSON (`application/json`)

~~~http
POST /api/products?dryRun=true HTTP/1.1
Content-Type: application/json

{"name":"Spring Guide","price":100}
~~~

Chọn **một DTO `@RequestBody`** cho JSON và `@RequestParam("dryRun")` cho query. Bộ giải mã JSON tạo object từ body. Mặc định `@RequestBody` có `required=true`; body rỗng hoặc JSON lỗi thường gây lỗi đọc, dẫn đến HTTP 400 nếu không có custom error handler.

**Sai về mặt nguồn:** `@RequestParam("name") String name` không tự lấy trường `name` bên trong JSON. JSON là body có cấu trúc, không phải Servlet form parameters.

### 3.3. Form urlencoded (`application/x-www-form-urlencoded`)

~~~http
POST /api/products/form HTTP/1.1
Content-Type: application/x-www-form-urlencoded

name=Spring+Guide&quantity=2
~~~

Nên dùng `@RequestParam` cho từng field hoặc `@ModelAttribute FormInput` để bind nhiều field vào DTO. Với Servlet API, truy cập parameters có thể **kích hoạt việc parse POST form body**. Spring khuyến nghị xử lý form theo cách này thay vì dùng `@RequestBody` nếu sau đó còn cần request parameters, vì body có thể đã bị tiêu thụ bởi việc parse form.

Đây là lý do **không thể mặc định “đọc lại raw form body”** sau khi gọi `request.getParameter("name")`. Khi trộn form parsing và trực tiếp đọc stream, hành vi có thể phụ thuộc Servlet container, thứ tự xử lý và các filter.

### 3.4. Multipart (`multipart/form-data`)

~~~text
Part "metadata" (Content-Type: application/json): {"source":"batch"}
Part "file"     (Content-Type: text/plain): bytes của tệp
~~~

Chọn `@RequestPart("metadata") Metadata meta` để convert part JSON và `@RequestPart("file") MultipartFile file` hoặc `@RequestParam("file") MultipartFile file` cho tệp. Mỗi **part** có header/body riêng; đừng cố dùng một `@RequestBody CreateRequest` để nhận trọn multipart thành JSON DTO.

Multipart resolver/container có thể parse request trước khi vào controller. Nội dung tệp lớn cần quản lý kích thước, dung lượng tạm và phương án streaming phù hợp; tránh ép toàn bộ multipart vào một `byte[]` chỉ để log.

## 4. Ví dụ chạy được: bốn loại đầu vào trong một controller

Ví dụ ứng dụng **Spring Boot 3.x, Java 17+**, với `spring-boot-starter-web` và `spring-boot-starter-test`. Package root `com.example.inputdemo`.

~~~text
src/main/java/com/example/inputdemo/
├── InputDemoApplication.java
└── web/InputController.java
src/test/java/com/example/inputdemo/web/
└── InputControllerTest.java
~~~

Ứng dụng khởi chạy, đặt tại `src/main/java/com/example/inputdemo/InputDemoApplication.java`:

~~~java
package com.example.inputdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InputDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(InputDemoApplication.class, args);
    }
}
~~~

Controller đặt tại `src/main/java/com/example/inputdemo/web/InputController.java`:

~~~java
package com.example.inputdemo.web;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/input")
public class InputController {

    @GetMapping("/items/{id}")
    public ItemView find(
            @PathVariable("id") long id,
            @RequestParam(name = "mode", defaultValue = "summary") String mode,
            @RequestHeader(name = "X-Trace-Id", required = false) String traceId,
            @CookieValue(name = "lang", required = false) String lang) {
        return new ItemView(id, mode, traceId, lang);
    }

    @PostMapping(path = "/items", consumes = MediaType.APPLICATION_JSON_VALUE)
    public CreatedItem create(
            @RequestParam(name = "source", defaultValue = "web") String source,
            @RequestBody NewItem input) {
        return new CreatedItem(input.title(), input.quantity(), source);
    }

    @PostMapping(path = "/forms",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public FormResult submit(@ModelAttribute FormInput form) {
        return new FormResult(form.getTitle(), form.getQuantity());
    }

    @PostMapping(path = "/uploads",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public UploadResult upload(
            @RequestPart("metadata") ImportMetadata metadata,
            @RequestPart("file") MultipartFile file) {
        return new UploadResult(metadata.source(), file.getSize());
    }

    public record ItemView(long id, String mode, String traceId, String lang) {}
    public record NewItem(String title, int quantity) {}
    public record CreatedItem(String title, int quantity, String source) {}
    public record FormResult(String title, int quantity) {}
    public record ImportMetadata(String source) {}
    public record UploadResult(String source, long bytes) {}

    // JavaBean dùng riêng cho form binding; không expose JPA entity.
    public static class FormInput {
        private String title;
        private int quantity;

        public FormInput() {}

        public String getTitle() {
            return title;
        }

        public void setTitle(String title) {
            this.title = title;
        }

        public int getQuantity() {
            return quantity;
        }

        public void setQuantity(int quantity) {
            this.quantity = quantity;
        }
    }
}
~~~

Những điểm cần quan sát:
- `GET /api/input/items/{id}` không đọc body: `id` từ path, `mode` từ request parameters, `traceId` từ header, `lang` từ cookie.
- `POST /api/input/items?source=mobile` có thể đồng thời nhận **query parameter** và **JSON body**; converter đọc body đúng một lần vào `NewItem`.
- `POST /api/input/forms` dùng `@ModelAttribute`: Spring khởi tạo `FormInput` rồi bind các trường `title`/`quantity` từ parameters (trong tình huống này là form).
- `POST /api/input/uploads` dùng `@RequestPart`: Spring giải mã metadata JSON của một part, file được truy cập dưới dạng `MultipartFile`; ví dụ chỉ trả `size`, không lưu file.

Các DTO cố ý tối giản để minh họa nguồn bind. Mẫu này **chưa** khai báo validation như `@NotBlank`, `@Positive` và chưa xử lý dữ liệu ngoài phạm vi/giá trị null. Trong ứng dụng thực tế, thêm `spring-boot-starter-validation`, `@Valid` và constraint cho request DTO; không chỉ dựa vào kiểu Java để kết luận request hợp lệ.

### 4.1. Gọi HTTP và kết quả

Ở project đã cấu hình Spring Boot Gradle plugin, chạy:

~~~bash
./gradlew bootRun
~~~

Có thể thử bằng curl:

~~~bash
curl -s -H 'X-Trace-Id: t-1' -H 'Cookie: lang=vi' \
  'http://localhost:8080/api/input/items/7?mode=detail'

curl -s -X POST \
  'http://localhost:8080/api/input/items?source=mobile' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Java","quantity":2}'

curl -s -X POST 'http://localhost:8080/api/input/forms' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'title=Spring&quantity=3'

curl -s -X POST 'http://localhost:8080/api/input/uploads' \
  -F 'metadata={"source":"batch"};type=application/json' \
  -F 'file=@notes.txt;type=text/plain'
~~~

Ba response đầu với input trên là:

~~~json
{"id":7,"mode":"detail","traceId":"t-1","lang":"vi"}
~~~

~~~json
{"title":"Java","quantity":2,"source":"mobile"}
~~~

~~~json
{"title":"Spring","quantity":3}
~~~

Ví dụ multipart trả `{"source":"batch","bytes":N}`, trong đó `N` đúng bằng số byte của file `notes.txt` thực tế; không bịa một con số cố định khi nội dung file chưa xác định.

Nếu dùng Windows PowerShell, lựa chọn `curl.exe` cho cú pháp curl truyền thống; PowerShell có thể dùng alias `curl`/`Invoke-WebRequest` với cách truyền tham số khác. Trường hợp không có Unix shell, dùng công cụ HTTP client hỗ trợ form/multipart để gửi cùng request.

## 5. Request body là luồng một lần: cơ chế và hậu quả

### 5.1. Stream nằm ở đâu?

Body đến Servlet container qua kết nối HTTP. Ở tầng Servlet, request thường cấp `ServletInputStream` (`request.getInputStream()`) hoặc `BufferedReader` (`request.getReader()`). **Servlet API quy định chọn một trong hai cách**: đã dùng reader thì gọi input stream (hoặc ngược lại) có thể ném `IllegalStateException`. Đọc đến hết stream thông thường khiến lần đọc tiếp theo chỉ nhận EOF; API không đảm bảo nút “rewind”.

Khi handler có:

~~~java
@PostMapping("/orders")
public void create(@RequestBody OrderInput input) {
    // Spring đọc JSON từ body thông qua HttpMessageConverter.
}
~~~

Đoạn trên chỉ minh họa cơ chế (kiểu `OrderInput` chưa được khai báo trong snippet): việc giải mã `@RequestBody` tiêu thụ luồng. Sau đó không thể mặc nhiên `request.getInputStream()` và mong nhận lại JSON ban đầu.

Một handler có **hai** tham số `@RequestBody` cố lấy hai DTO từ cùng một JSON body là thiết kế sai phổ biến:

~~~java
// MINH HỌA SAI — đừng sử dụng:
@PostMapping("/broken")
public void broken(@RequestBody UserInput user, @RequestBody AuditInput audit) {}
~~~

Spring không tự phân đôi một JSON object thành hai lượt đọc độc lập. Thường converter đầu tiên đã tiêu thụ body, khiến tham số thứ hai lỗi thiếu body hoặc lỗi giải mã. Cách đúng: định nghĩa **một DTO bao** cho payload, hoặc bind một lần rồi truyền dữ liệu đã giải mã tới service/validator/audit.

~~~java
// MINH HỌA THIẾT KẾ ĐÚNG:
public record CreateUserRequest(UserInput user, AuditInput audit) {}

@PostMapping("/users")
public void create(@RequestBody CreateUserRequest request) {
    userService.create(request.user());
    auditService.record(request.audit());
}
~~~

Hai fragment trên là ví dụ thiết kế, **không phải Java source độc lập**: trong ứng dụng thật cần khai báo `UserInput`, `AuditInput` và service tương ứng.

### 5.2. Form parameter parsing cũng có thể đọc body

Riêng `application/x-www-form-urlencoded`, Servlet container có thể đọc/parse body khi mã gọi `getParameter()`/`getParameterMap()` hoặc khi Spring bind `@RequestParam`/`@ModelAttribute`. Bởi vậy:
- Filter đọc trước `request.getInputStream()` có thể khiến handler `@RequestBody` nhìn thấy body rỗng.
- Một filter gọi `getParameterMap()` để log form có thể làm raw body không còn sẵn để đọc theo cách khác.
- Đọc raw body trước rồi sau đó yêu cầu form parameters có thể làm việc parse form thất bại hoặc không đầy đủ.

Không kết luận rằng mọi Servlet container luôn biểu hiện giống nhau sau các thao tác sai thứ tự. Cách bền vững là dùng resolver thích hợp cho từng Content-Type và không phụ thuộc hai người tiêu thụ cùng stream.

### 5.3. Lỗi quan sát được

| Tình huống | Điều có thể xảy ra | Cách khắc phục |
| --- | --- | --- |
| Filter đọc toàn bộ stream trước controller | `@RequestBody` thấy EOF, lỗi body missing / HTTP 400 | Không tiêu thụ body trong filter; dùng caching wrapper hoặc API hook phù hợp |
| Hai tham số `@RequestBody` | Tham số sau không còn dữ liệu | Một request DTO và phân tách sau khi decode |
| `getReader()` rồi `getInputStream()` | `IllegalStateException` | Chỉ chọn một API của Servlet request |
| `getParameterMap()` trên form rồi đọc raw body | Body đã được parse, không thể đọc lại đáng tin cậy | Bind form bằng `@RequestParam` hoặc `@ModelAttribute` |
| Dùng `@RequestParam` đọc key nằm trong JSON | Không tìm thấy parameter | Đặt field trong `@RequestBody` DTO |
| JSON có `Content-Type` không tương thích | Có thể `415 Unsupported Media Type` | Gửi đúng Content-Type / mapping `consumes` |
| JSON cú pháp hỏng | `HttpMessageNotReadableException`, thường HTTP 400 | Kiểm tra JSON, DTO, converter, error handler |
| Request vượt limit server/proxy | Bị từ chối theo cấu hình, có thể HTTP 413 | Cấu hình giới hạn phù hợp; không buffer vô hạn |

Một số API có thể dùng `RequestBodyAdvice` để quan sát/biến đổi dữ liệu **ngay trong tiến trình conversion** và `HandlerInterceptor`/filter để gắn metadata. Những hook này vẫn phải tôn trọng thời điểm và trách nhiệm đọc body.

## 6. `ContentCachingRequestWrapper` giúp gì, và KHÔNG giúp gì?

Spring cung cấp `org.springframework.web.util.ContentCachingRequestWrapper`: nó giữ bản sao các byte **đã được đọc qua wrapper**; mã khác có thể xem `getContentAsByteArray()` sau khi request được xử lý.

Ba điều rất quan trọng:
1. Wrapper **không tự đọc** body khi mới tạo. Nếu downstream chưa tiêu thụ body, cache có thể trống.
2. `getContentAsByteArray()` lấy bản cache để quan sát, có thể giới hạn dung lượng. Nó **không làm `getInputStream()` trở thành luồng replayable** cho lượt đọc tiếp theo.
3. Nếu filter log body trước `chain.doFilter(...)`, cache có thể chưa có gì; thường cần kiểm tra cache **sau** khi controller/converter đã đọc. Với async processing cần xét thời điểm hoàn tất dispatch.

### 6.1. Ví dụ filter quan sát số byte đã được đọc

Đây là một file có thể biên dịch trong ứng dụng Spring Boot 3.x có `spring-boot-starter-web`. Chỉ log **số byte đã cache** để tránh ghi dữ liệu nhạy cảm.

`src/main/java/com/example/inputdemo/web/BodyAuditFilter.java`:

~~~java
package com.example.inputdemo.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingRequestWrapper;

@Component
public class BodyAuditFilter extends OncePerRequestFilter {

    private static final Logger log =
            LoggerFactory.getLogger(BodyAuditFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        ContentCachingRequestWrapper cached =
                new ContentCachingRequestWrapper(request, 8192);

        try {
            chain.doFilter(cached, response);
        } finally {
            log.debug("HTTP {} {}: bytes cached = {}",
                    request.getMethod(),
                    request.getRequestURI(),
                    cached.getContentAsByteArray().length);
        }
    }
}
~~~

Phân tích:
- `chain.doFilter(cached, response)` chuyển wrapper xuống Spring MVC. Nếu controller giải mã JSON, wrapper sao chép các byte đã đi qua nó; controller vẫn dùng body theo quy trình bình thường.
- Sau `chain.doFilter`, ví dụ chỉ ghi số byte được cache. Cache limit `8192` là **giới hạn giữ bản sao**, không phải quy tắc từ chối tất cả request lớn hơn 8192 byte.
- Không có downstream đọc body thì `bytes cached = 0` là tình huống hợp lệ.
- Không dùng wrapper này làm cơ chế đọc body lần hai; nó cũng không thay thế chính sách request size limit.
- Nếu cần log payload để gỡ lỗi, phải hạn chế kích thước, che token/password/cookie/PII, phân quyền log và kiểm tra xử lý encoding. Không ghi raw body của request chứa bí mật vào production log.

### 6.2. Nếu thật sự cần đọc nhiều lần?

Thứ tự ưu tiên thiết kế:

1. **Đọc và giải mã đúng một lần** trong controller; truyền DTO/byte[] đã có tới nhiều service, validator hoặc component. Đây là phương án đơn giản nhất.
2. Nếu nhiều thành phần cần quan sát lúc body đã được giải mã, cân nhắc `RequestBodyAdvice` hoặc truyền object đã parse vào context do ứng dụng sở hữu, thay vì đọc lại servlet stream.
3. Nếu nhiều middleware *bắt buộc* cần các lượt đọc riêng, cân nhắc một `HttpServletRequestWrapper` tùy chỉnh: đọc body **một lần, ở rất sớm**, giới hạn kích thước, lưu byte[], và trả một `ServletInputStream` mới trên cùng byte[] khi `getInputStream()` được gọi. Lúc này cần xử lý đúng `getReader()` theo charset, các phương thức/notification nonblocking (`ReadListener`, `isReady`, `isFinished`), async dispatch, error path, thứ tự filter và tương tác đặc thù với parsing form/multipart.
4. Với payload lớn, streaming, file upload hay dữ liệu nhạy cảm, tránh toàn bộ việc cache trong heap; chuyển sang cơ chế đọc/ghi theo stream, file tạm được kiểm soát hoặc thiết kế API một lần tiêu thụ.

Wrapper replay tùy chỉnh **không chỉ là** đặt `ContentCachingRequestWrapper` rồi gọi lại `getInputStream()`. Cũng không nên biến mọi request thành byte[] lớn trước khi authenticate/validate giới hạn; điều đó có thể làm tăng dùng bộ nhớ và nguy cơ DoS.

## 7. Kiểm thử nguồn dữ liệu bằng MockMvc

`src/test/java/com/example/inputdemo/web/InputControllerTest.java`:

~~~java
package com.example.inputdemo.web;

import jakarta.servlet.http.Cookie;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InputController.class)
class InputControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void pathQueryHeaderAndCookieAreIndependent() throws Exception {
        mvc.perform(get("/api/input/items/7")
                        .param("mode", "detail")
                        .header("X-Trace-Id", "t-1")
                        .cookie(new Cookie("lang", "vi")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.mode").value("detail"))
                .andExpect(jsonPath("$.traceId").value("t-1"))
                .andExpect(jsonPath("$.lang").value("vi"));
    }

    @Test
    void jsonBodyAndQueryCanBeReadTogether() throws Exception {
        mvc.perform(post("/api/input/items")
                        .param("source", "mobile")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Java\",\"quantity\":2}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Java"))
                .andExpect(jsonPath("$.quantity").value(2))
                .andExpect(jsonPath("$.source").value("mobile"));
    }

    @Test
    void urlEncodedFormBindsThroughModelAttribute() throws Exception {
        mvc.perform(post("/api/input/forms")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("title", "Spring")
                        .param("quantity", "3"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Spring"))
                .andExpect(jsonPath("$.quantity").value(3));
    }

    @Test
    void multipartJsonPartAndFileHaveTheirOwnSources() throws Exception {
        MockMultipartFile metadata = new MockMultipartFile(
                "metadata",
                "",
                "application/json",
                "{\"source\":\"batch\"}".getBytes(StandardCharsets.UTF_8));
        MockMultipartFile file = new MockMultipartFile(
                "file", "notes.txt", "text/plain", new byte[] {65, 66});

        mvc.perform(multipart("/api/input/uploads")
                        .file(metadata)
                        .file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.source").value("batch"))
                .andExpect(jsonPath("$.bytes").value(2));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Lớp test dùng Spring MVC test slice và JSON converter thường có sẵn từ `spring-boot-starter-test`/`spring-boot-starter-web`. Nó chứng minh path/query/header/cookie, JSON body, form binding và hai multipart part được phân biệt đúng. Không có dependency database/service vì controller demo tự xử lý dữ liệu. Nếu project thêm Spring Security, custom filters, advice hoặc cấu hình MVC riêng, cần điều chỉnh test context/credentials tương ứng.

**Về test form:** `MockMvcRequestBuilders.post(...).param(...)` mô phỏng Servlet form parameters. Để kiểm tra chính xác hành vi một request chứa byte body đã encode, hãy bổ sung integration test chạy qua container thực tế. Không dùng mock request để kết luận mọi container sẽ xử lý giống nhau nếu filter đọc raw stream trước khi form được parse.

Các test lỗi nên có cho dự án thực tế:
- Thiếu `@RequestParam` bắt buộc hoặc `@RequestHeader` bắt buộc: kiểm tra `400`.
- `id` là chuỗi không chuyển được sang `long`: kiểm tra error response.
- `Content-Type: text/plain` gửi đến endpoint chỉ nhận JSON: kiểm tra `415`.
- JSON cú pháp sai, thiếu body: kiểm tra `400` và format lỗi có chủ đích.
- Multipart thiếu `metadata`, sai content type JSON part, tệp quá lớn: kiểm tra policy.
- Test một filter tùy chỉnh có/không có caching wrapper để phát hiện body bị đọc trước controller, nhưng không dựa vào hành vi chỉ xuất hiện trong `MockHttpServletRequest`.

## 8. Validation, bảo mật và các giới hạn nên đặt rõ

**Chọn DTO phù hợp cho từng transport.** `@ModelAttribute` cho form/query binding có thể gán thuộc tính qua setter; không bind trực tiếp domain/JPA entity với những field nhạy cảm như `role`, `isAdmin`, `ownerId`. Dùng DTO dành riêng cho web hoặc constructor binding để kiểm soát những trường được phép. Nếu phải dùng property binding, áp dụng `@InitBinder` với `setAllowedFields(...)` cho danh sách được phép.

**Xác thực đầu vào:** 
- `@Valid @RequestBody CreateOrder input`: áp dụng Bean Validation cho dữ liệu đã deserialize khi DTO có constraint và thư viện validation được cấu hình.
- `@Valid @ModelAttribute FormInput input`: validate sau bind form/query, có thể nhận `BindingResult` ngay sau tham số được validate để tự xử lý lỗi.
- `@Valid @RequestPart("metadata") Metadata metadata`: validate part JSON.
- Lỗi `@Valid`, ràng buộc trên trực tiếp các tham số method, hay lỗi conversion có thể đi qua những loại exception khác nhau; không hardcode một thông báo lỗi Spring mặc định trong client.

**Kích thước và chi phí:** đặt giới hạn request/upload và resource trên reverse proxy, Servlet container và ứng dụng. Caching body toàn phần dùng bộ nhớ tuyến tính theo size; vài request lớn đồng thời có thể tăng đột biến heap. `ContentCachingRequestWrapper` chỉ hạn chế cache tại wrapper, không phải lớp bảo vệ upload toàn cục.

**Tránh đọc/log dữ liệu bí mật:** query có thể nằm trong access log, header/cookie có thể chứa token, JSON có thể chứa password, upload có thể là tệp riêng tư. Ưu tiên log trace ID, method, path chuẩn hóa, duration và trạng thái lỗi; tránh log payload mặc định.

**Đảm bảo tương thích HTTP:** phân biệt `Content-Type` (client nói body gửi lên là gì) và `Accept` (client mong response dạng gì). Đối với định tuyến `consumes` và `produces`, gửi sai media type có thể dẫn đến `415`/`406` trước khi vào handler.

## 9. Cây quyết định thực hành

~~~text
Giá trị cần lấy từ HTTP request?
|
+-- Nằm trong phần {variable} của đường dẫn? --> @PathVariable
|
+-- Là query / application/x-www-form-urlencoded field?
|      +-- Ít trường đơn giản?                  --> @RequestParam
|      +-- Nhiều field thành object?            --> @ModelAttribute + DTO
|
+-- Là header?                                  --> @RequestHeader
+-- Là cookie?                                  --> @CookieValue
+-- Do filter/interceptor đưa vào request?      --> @RequestAttribute
+-- Có sẵn trong HTTP session?                  --> @SessionAttribute
|
+-- Nằm trong raw HTTP body?
       +-- JSON/XML document?                   --> @RequestBody + DTO
       +-- Multipart JSON part?                 --> @RequestPart + DTO
       +-- Multipart file?                      --> MultipartFile/@RequestPart
       +-- Stream lớn/chuyên biệt?              --> xem xét Servlet streaming,
                                                    giới hạn size và ownership
                                                    của lượt đọc
~~~

Khi bạn nghĩ “tôi phải đọc body lần hai”, trước tiên kiểm tra xem **dữ liệu đã được parse ở đâu**. Phần lớn trường hợp chỉ cần truyền DTO đã giải mã xuống service hoặc audit component. Nếu một filter hiện tại đang đọc raw JSON để log trước khi controller chạy, hãy sửa cơ chế quan sát tại thời điểm request được xử lý, kiểm tra giới hạn cache và test lại endpoint nhận `@RequestBody`.

## 10. Checklist chẩn đoán nhanh

1. Xác minh `@RequestMapping`/HTTP method, `Content-Type` và `Accept` của request.
2. Với từng tham số handler, ghi rõ nguồn: path, Servlet parameters, header, cookie, body, multipart part, request/session attribute.
3. Kiểm tra kiểu Java, converter/formatter, tên tham số tường minh, `required`, default value và validation.
4. Không trộn nguồn form và JSON. Với JSON, ưu tiên một `@RequestBody` DTO; với form, dùng `@RequestParam`/`@ModelAttribute`.
5. Rà soát filter, interceptor, custom resolver và advice: thành phần nào đọc `getInputStream()`/`getReader()`/`getParameterMap()` trước handler?
6. Nếu dùng `ContentCachingRequestWrapper`, phân biệt cache để xem lại byte đã đọc với wrapper có thể replay (hai cơ chế khác nhau).
7. Kiểm thử MockMvc cho việc chọn nguồn; test qua Servlet container cho form parsing, filter order và các giới hạn upload.
8. Ràng buộc trường bind và kích thước request; hạn chế ghi log dữ liệu nhạy cảm.

## 11. Tài liệu chính thức tham khảo

- [Spring Framework — MVC Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): resolver và loại tham số được hỗ trợ.
- [Spring Framework — `@RequestParam`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html): Servlet request parameters, query/form, required/optional, map và list.
- [Spring Framework — `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): `HttpMessageConverter` và cảnh báo tương tác form parameter parsing.
- [Spring Framework — `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): constructor/property binding, validation, dữ liệu đầu vào không đáng tin cậy.
- [Spring Framework — Multipart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): `@RequestPart`, file, JSON part.
- [Spring Framework — `ContentCachingRequestWrapper` API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/util/ContentCachingRequestWrapper.html): chỉ lưu byte đã đọc, cache limit, không tự tiêu thụ body.
- [Jakarta Servlet — `ServletRequest` API](https://javadoc.io/static/jakarta.servlet/jakarta.servlet-api/6.0.0/jakarta.servlet/jakarta/servlet/ServletRequest.html): `getInputStream()`, `getReader()` và phân tích request parameters.

**Điểm cần nhớ:** nguồn dữ liệu được xác định bởi hợp đồng tham số và cơ chế resolver của Spring MVC; body chỉ nên có **một chủ thể tiêu thụ** trong luồng xử lý thông thường. Dữ liệu đã giải mã có thể được chia sẻ ở mức object; stream HTTP thô không tự trở thành dữ liệu có thể đọc vô hạn lần.
