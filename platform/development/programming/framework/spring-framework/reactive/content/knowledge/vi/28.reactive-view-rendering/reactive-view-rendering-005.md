# Chuyển hướng và dữ liệu biểu mẫu trong Spring WebFlux

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Hiển thị giao diện

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt HTTP redirect với render view và chuyển tiếp nội bộ.
2. Chọn status 301, 302, 303, 307 hoặc 308 theo mục đích và semantics của method.
3. Thiết kế Post/Redirect/Get (PRG) sau khi xử lý form.
4. Dùng redirect trong annotated controller qua view name `redirect:` hoặc `Rendering.redirectTo`.
5. Tạo redirect trong WebFlux functional endpoints bằng `ServerResponse`.
6. Nhận `application/x-www-form-urlencoded` bằng `@RequestParam`, `@ModelAttribute`, `ServerRequest.formData()` hoặc `ServerRequest.bind()`.
7. Bind dữ liệu vào form object, validate bằng Bean Validation và xử lý lỗi qua `BindingResult`.
8. Giới hạn field được phép bind, tránh over-posting và bảo vệ redirect khỏi open redirect.
9. Xây dựng ứng dụng Spring Boot có form, trang kết quả, redirect 303 và integration tests bằng `WebTestClient`.

## 1. Redirect là gì?

HTTP redirect là response yêu cầu client gửi request khác tới URI được chỉ định trong header `Location`. Server không tự chuyển sang controller khác trong cùng request. Trình duyệt nhận response 3xx, đọc Location rồi tạo request tiếp theo theo semantics của status.

```http
HTTP/1.1 303 See Other
Location: /registrations/42
Content-Length: 0
```

Trình duyệt gửi request GET tới `/registrations/42`; server xử lý GET mới và trả trang kết quả.

Redirect khác với:

- **Render view:** server chọn template và tạo HTML cho request hiện tại.
- **Redirect:** server trả 3xx và Location; client tạo request mới.
- **Forward nội bộ:** chuyển request sang handler khác phía server. WebFlux không hỗ trợ Servlet-style FORWARD dispatch hoặc prefix `forward:`.
- **Rewrite ở proxy/gateway:** proxy thay URI trước khi request tới ứng dụng; đây không phải redirect response mà trình duyệt nhìn thấy.

Redirect thường dùng sau khi gửi form, khi URL tài nguyên thay đổi hoặc khi cần đưa người dùng tới trang khác.

### 1.1. Thành phần của response redirect

Một response redirect thường có status 3xx và header Location. Response body có thể chứa nội dung mô tả nhưng trình duyệt thường dựa vào Location để điều hướng. Nếu thiếu Location, client không có đích redirect rõ ràng.

Với redirect nội bộ, dùng đường dẫn theo ứng dụng như `/registrations/42`. Với URL tuyệt đối, kiểm tra host đích trước khi redirect.

## 2. Các status redirect quan trọng

Không nên dùng mọi status 3xx thay thế cho nhau. Khác biệt chính là redirect tạm thời hay vĩnh viễn và request tiếp theo có giữ method/body hay không.

| Status | Ý nghĩa | Method của request tiếp theo | Trường hợp thường dùng |
| --- | --- | --- | --- |
| **301 Moved Permanently** | Tài nguyên chuyển vĩnh viễn | Trình duyệt có thể đổi POST thành GET theo hành vi tương thích lịch sử | Đổi URL lâu dài, thường cho GET. |
| **302 Found** | Chuyển hướng tạm thời | Client phổ biến thường đổi POST thành GET; semantics lịch sử không rõ như 303 | Redirect tạm thời. |
| **303 See Other** | Xem kết quả tại URI khác | Client thực hiện GET (hoặc HEAD nếu request gốc là HEAD) | PRG sau POST form. |
| **307 Temporary Redirect** | Chuyển hướng tạm thời | Giữ nguyên method và body | Chuyển request tạm thời nhưng vẫn cần POST/PUT/PATCH. |
| **308 Permanent Redirect** | Chuyển hướng vĩnh viễn | Giữ nguyên method và body | API/tài nguyên chuyển lâu dài, cần bảo toàn method. |

Hai quy tắc:

- Dùng **303 See Other** sau POST khi muốn trình duyệt tải trang kết quả bằng GET.
- Dùng **307 hoặc 308** khi server muốn client gửi lại đúng method và body tới URI mới.

301 và 308 là redirect vĩnh viễn; client hoặc proxy có thể cache quyết định. Không dùng chúng cho thay đổi tạm thời. 302 có hành vi tương thích trình duyệt lâu đời; với PRG, 303 thể hiện ý định rõ hơn.

**304 Not Modified** không phải redirect điều hướng. Nó là response cache validation, cho biết client có thể dùng representation đã cache.

## 3. Post/Redirect/Get (PRG)

PRG là mẫu xử lý form gồm ba bước:

```text
Trình duyệt                  WebFlux server
    |                              |
    | GET /registrations/new       |
    |----------------------------->|
    |<-----------------------------| 200 OK + form HTML
    |                              |
    | POST /registrations          |
    | form-urlencoded              |
    |----------------------------->| Validate và lưu
    |<-----------------------------|
    | 303 See Other                |
    | Location: /registrations/42  |
    |                              |
    | GET /registrations/42        |
    |----------------------------->|
    |<-----------------------------| 200 OK + trang kết quả
```

Nếu server trả trực tiếp HTML sau POST, thao tác refresh có thể gửi lại POST. Với 303, request tiếp theo là GET; refresh trang kết quả chỉ tải lại GET và tránh hộp thoại gửi lại form trong trường hợp thông thường.

PRG không thay thế kiểm soát trùng lặp nghiệp vụ. Người dùng có thể nhấn nút hai lần trước khi nhận redirect, mạng có thể retry hoặc client có thể gửi lại POST. Với thanh toán, tạo đơn hoặc thao tác có side effect quan trọng, vẫn cần idempotency key, unique constraint hoặc cơ chế chống xử lý trùng.

### 3.1. Khi nào không cần redirect?

- API gọi bằng JavaScript có thể trả JSON cùng status 201 Created và Location.
- Endpoint xử lý nền có thể trả 202 Accepted cùng URI theo dõi công việc.
- Form lỗi validation nên render lại trang form với lỗi và giá trị đã nhập.
- Thao tác không tạo tài nguyên mới có thể trả response trực tiếp nếu contract yêu cầu.

PRG đặc biệt hữu ích cho form HTML truyền thống do trình duyệt gửi và điều hướng.

## 4. Redirect trong annotated controller của WebFlux

WebFlux hỗ trợ redirect qua view resolution.

### 4.1. View name có prefix redirect:

```java
@Controller
public class HomeController {

    @GetMapping("/legacy-home")
    public String legacyHome() {
        return "redirect:/dashboard";
    }
}
```

`UrlBasedViewResolver` nhận biết prefix `redirect:` và tạo redirect view. Phần còn lại là URL đích. Đường dẫn `/dashboard` được hiểu tương đối với ứng dụng.

Trong WebFlux, `RedirectView` mặc định dùng status `303 See Other`. Có thể cấu hình status khác khi cần. Không dùng `forward:` trong WebFlux vì không có FORWARD dispatch.

Cách này ngắn gọn khi chỉ cần URL cố định. Nếu cần cấu hình status hoặc model, dùng `Rendering`.

### 4.2. Dùng Rendering.redirectTo

`Rendering` là API trả kết quả view rendering trong WebFlux. `Rendering.redirectTo` tạo redirect thông qua `RedirectView`:

```java
@GetMapping("/old-dashboard")
public Rendering redirectDashboard() {
    return Rendering.redirectTo("/dashboard")
            .status(HttpStatus.SEE_OTHER)
            .build();
}
```

`status` chỉ định rõ status. Với PRG, dùng `HttpStatus.SEE_OTHER` để thể hiện request tiếp theo phải là GET.

Có thể dùng URI template và model attribute:

```java
return Rendering.redirectTo("/registrations/{id}")
        .status(HttpStatus.SEE_OTHER)
        .modelAttribute("id", registration.getId())
        .build();
```

Chỉ đưa dữ liệu cần cho URL đích vào model redirect. Tránh thêm toàn bộ form object hoặc dữ liệu nhạy cảm vì redirect view có thể dùng model attribute làm URI template variable hoặc request parameter.

### 4.3. Dùng ResponseEntity khi không render view

Một REST controller có thể trả redirect response trực tiếp:

```java
@PostMapping("/api/complete")
public Mono<ResponseEntity<Void>> complete() {
    URI location = URI.create("/api/results/42");

    return Mono.just(
            ResponseEntity.status(HttpStatus.SEE_OTHER)
                    .location(location)
                    .build());
}
```

Cách này phù hợp khi controller trả HTTP response thay vì tên view. Với API cho ứng dụng JavaScript, cân nhắc trả JSON và để client quyết định điều hướng; redirect từ fetch không nhất thiết làm toàn bộ cửa sổ trình duyệt chuyển trang.

## 5. Redirect trong WebFlux functional endpoints

WebFlux.fn dùng `RouterFunction`, `HandlerFunction`, `ServerRequest` và `ServerResponse`. Handler trả `Mono<ServerResponse>`.

```java
public Mono<ServerResponse> redirectToResult(ServerRequest request) {
    URI location = URI.create("/results/42");

    return ServerResponse.status(HttpStatus.SEE_OTHER)
            .location(location)
            .build();
}
```

`ServerResponse.status(...).location(...).build()` tạo response 303 cùng header Location.

Một route kết nối handler:

```java
@Bean
RouterFunction<ServerResponse> routes(ResultHandler handler) {
    return RouterFunctions.route()
            .GET("/old-result", handler::redirectToResult)
            .build();
}
```

Đây là đoạn minh họa. Trong ứng dụng thật, URI đích nên được tạo từ ID tài nguyên đã lưu hoặc URI builder phù hợp, không nối trực tiếp URL tùy ý do client gửi lên.

## 6. Dữ liệu biểu mẫu được gửi như thế nào?

HTML form có thể gửi nhiều encoding. Hai dạng thường gặp là URL-encoded và multipart.

| Encoding | Content-Type | Cách hoạt động | Trường hợp dùng |
| --- | --- | --- | --- |
| URL-encoded | `application/x-www-form-urlencoded` | Các cặp key/value được encode trong request body | Form text, số, checkbox, select. |
| Multipart | `multipart/form-data; boundary=...` | Body gồm nhiều part, mỗi part có header riêng | Form có file upload hoặc part có content type khác nhau. |

Ví dụ form URL-encoded:

```html
<form method="post" action="/registrations">
    <input name="name" value="Lan">
    <input name="email" value="lan@example.com">
    <select name="category">
        <option value="spring">Spring</option>
    </select>
    <button type="submit">Gửi</button>
</form>
```

Body được gửi gần như sau:

```text
name=Lan&email=lan%40example.com&category=spring
```

Tên field trong HTML phải khớp tên property hoặc parameter mà controller nhận. Nếu form dùng `name="email"` nhưng DTO chỉ có property `mail`, Spring không tự biết hai tên đó tương đương nếu không cấu hình ánh xạ.

### 6.1. Form URL-encoded và request JSON khác nhau

`@ModelAttribute` dùng cho form/query parameter binding; nó không phải JSON decoder.

- HTML form mặc định gửi `application/x-www-form-urlencoded`.
- JavaScript gửi JSON thường đặt `Content-Type: application/json` và dùng `@RequestBody`.
- Form có file thường dùng `multipart/form-data`, nhận file qua `@RequestPart` hoặc `FilePart`.

Không gửi JSON body rồi mong `@ModelAttribute` tự bind giống form URL-encoded. Chọn annotation theo Content-Type và contract request.

### 6.2. Một field có nhiều giá trị

Checkbox group hoặc multi-select có thể gửi cùng key nhiều lần:

```text
tag=java&tag=spring&tag=reactive
```

Spring có thể bind nhiều giá trị vào `List<String>`, array hoặc `MultiValueMap`. Nếu chỉ dùng một biến String, ứng dụng chỉ nhận một giá trị theo quy tắc resolver/conversion tương ứng. Khai báo kiểu dữ liệu đúng với form.

## 7. Nhận form bằng @RequestParam

Khi chỉ có vài field đơn giản, `@RequestParam` dễ đọc:

```java
@PostMapping(
        value = "/search",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public Mono<String> search(
        @RequestParam("keyword") String keyword,
        @RequestParam(name = "page", defaultValue = "1") int page) {

    return Mono.just("keyword=" + keyword + ", page=" + page);
}
```

`@RequestParam` lấy giá trị theo tên parameter. Có thể khai báo `required=false`, `defaultValue` hoặc kiểu dữ liệu khác String để Spring chuyển đổi.

Dùng `@RequestParam` khi method chỉ cần vài field đơn lẻ, không cần object đại diện toàn bộ form và muốn thể hiện rõ parameter nào bắt buộc hoặc có mặc định. Nếu form có nhiều field liên quan, gom chúng vào form DTO để validate và quản lý dễ hơn.

## 8. Nhận form bằng @ModelAttribute

`@ModelAttribute` bind form data và query parameters vào object. Spring thực hiện type conversion, constructor binding hoặc property binding tùy thiết kế class.

```java
public class SearchForm {
    private String keyword;
    private int page = 1;

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public int getPage() {
        return page;
    }

    public void setPage(int page) {
        this.page = page;
    }
}

@PostMapping(
        value = "/search",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public Mono<String> search(@ModelAttribute SearchForm form) {
    return Mono.just(
            "keyword=" + form.getKeyword()
                    + ", page=" + form.getPage());
}
```

Tên field keyword và page được bind vào property cùng tên. page được chuyển từ chuỗi sang int; nếu giá trị không hợp lệ, Spring tạo binding error.

Trong WebFlux, `@ModelAttribute` có thể khai báo trực tiếp hoặc bọc trong reactive type như `Mono<SearchForm>`. Khi dùng reactive type, xử lý validation error trong reactive chain. Nếu muốn nhận `BindingResult` trực tiếp, khai báo model object không bọc reactive type và đặt BindingResult ngay sau nó.

### 8.1. Khởi tạo dữ liệu cho form

Khi hiển thị form GET, controller thêm form object và danh sách lựa chọn vào model:

```java
@GetMapping("/search")
public String showSearchForm(Model model) {
    model.addAttribute("searchForm", new SearchForm());
    model.addAttribute("categories", List.of("java", "spring", "reactive"));
    return "search-form";
}
```

Có thể dùng `@ModelAttribute` method để thêm dữ liệu dùng chung cho view:

```java
@ModelAttribute("categories")
public List<String> categories() {
    return List.of("java", "spring", "reactive");
}
```

Các thuộc tính này giúp template render select, checkbox hoặc dữ liệu hỗ trợ khác. Khi render lại form do validation fail, phải cung cấp lại danh sách lựa chọn.

### 8.2. Bind kiểu số, ngày và enum

Spring dùng conversion service để chuyển chuỗi thành kiểu Java:

- page=3 có thể bind thành int.
- active=true có thể bind thành boolean.
- category=SPRING có thể bind thành enum `Category.SPRING`.
- Ngày tháng cần format phù hợp với kiểu đích và cấu hình binder.

Nếu định dạng ngày không thống nhất, khai báo format hoặc formatter rõ ràng. Không giả định trình duyệt gửi ngày theo locale của server.

## 9. Validation và BindingResult

Dữ liệu form là input không đáng tin cậy. Cần validate trước khi lưu hoặc thực hiện nghiệp vụ.

```java
public class RegistrationForm {
    @NotBlank(message = "Họ tên là bắt buộc")
    @Size(max = 80, message = "Họ tên tối đa 80 ký tự")
    private String name;

    @NotBlank(message = "Email là bắt buộc")
    @Email(message = "Email không đúng định dạng")
    private String email;

    @NotBlank(message = "Hãy chọn nhóm")
    private String category;

    // getters và setters
}
```

Controller dùng `@Valid` và `BindingResult`:

```java
@PostMapping("/registrations")
public String submit(
        @Valid @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "registration-form";
    }

    // Lưu dữ liệu sau khi hợp lệ.
    return "redirect:/registrations";
}
```

`BindingResult` phải nằm ngay sau argument được validate. Khi có lỗi, controller trả lại view form để template hiển thị thông báo. Khi không khai báo BindingResult, lỗi binding/validation thường được biểu diễn bằng `WebExchangeBindException`.

Với WebFlux, có thể validate một `Mono<RegistrationForm>` bằng `@Valid` rồi xử lý lỗi bằng `onErrorResume`. Phân biệt lỗi validation với lỗi hạ tầng hoặc nghiệp vụ; không biến mọi exception thành thông báo form không hợp lệ.

### 9.1. Hiển thị lỗi trong Thymeleaf

```html
<form th:action="@{/registrations}"
      th:object="${registrationForm}"
      method="post">
    <label for="name">Họ tên</label>
    <input id="name" type="text" th:field="*{name}">
    <p th:if="${#fields.hasErrors('name')}"
       th:errors="*{name}"></p>

    <label for="email">Email</label>
    <input id="email" type="email" th:field="*{email}">
    <p th:if="${#fields.hasErrors('email')}"
       th:errors="*{email}"></p>

    <button type="submit">Gửi</button>
</form>
```

`th:field` kết nối input với property của form object và hỗ trợ hiển thị lại giá trị đã nhập. `th:errors` hiển thị lỗi validation của field tương ứng. Dùng template engine có escaping mặc định; không tự nối input vào HTML bằng string.

## 10. Bảo vệ data binding

Nếu bind trực tiếp một entity lớn, client có thể gửi thêm property mà form không hiển thị, ví dụ role, enabled, ownerId hoặc approved.

Các nguyên tắc an toàn:

1. Tạo form DTO riêng chỉ chứa field người dùng được phép gửi.
2. Không bind trực tiếp JPA/domain entity có nhiều thuộc tính nhạy cảm.
3. Với property binding, dùng `@InitBinder` và `setAllowedFields` để giới hạn field.
4. Không tin hidden input; người dùng có thể sửa chúng trong DevTools hoặc gửi request thủ công.
5. Kiểm tra quyền trên tài nguyên theo danh tính hiện tại; không dựa vào ownerId do client gửi.
6. Validate cú pháp và quy tắc nghiệp vụ ở server.
7. Không đưa mật khẩu, token, email riêng tư hoặc dữ liệu nhạy cảm vào query string.

Ví dụ giới hạn field:

```java
@InitBinder("registrationForm")
void limitRegistrationFields(WebDataBinder binder) {
    binder.setAllowedFields("name", "email", "category");
}
```

Nếu client gửi thêm `admin=true`, binder không gán field đó vào form object. Đây là lớp bảo vệ bổ sung; quyền truy cập và kiểm tra nghiệp vụ vẫn phải được thực hiện ở service/security layer.

Với Spring Security, form thay đổi dữ liệu cần bảo vệ CSRF. Thymeleaf integration có thể thêm CSRF token theo cấu hình Security. Không tắt CSRF chỉ để làm POST từ trình duyệt hoạt động.

## 11. Nhận form trong functional endpoint

Trong WebFlux.fn, `ServerRequest.formData()` trả về `Mono<MultiValueMap<String, String>>`:

```java
public Mono<ServerResponse> submit(ServerRequest request) {
    return request.formData()
            .flatMap(form -> {
                String name = form.getFirst("name");
                String email = form.getFirst("email");

                if (name == null || name.isBlank()) {
                    return ServerResponse.badRequest()
                            .bodyValue("Tên là bắt buộc");
                }

                return registrationService.save(name, email)
                        .flatMap(saved -> ServerResponse
                                .status(HttpStatus.SEE_OTHER)
                                .location(URI.create(
                                        "/registrations/" + saved.getId()))
                                .build());
            });
}
```

`formData()` phù hợp với form URL-encoded. Kết quả là MultiValueMap vì một key có thể có nhiều value. Handler validate dữ liệu và trả lỗi trước khi gọi service.

Đăng ký handler qua router:

```java
@Bean
RouterFunction<ServerResponse> registrationRoutes(
        RegistrationHandler handler) {

    return RouterFunctions.route()
            .POST("/fn/registrations",
                    contentType(MediaType.APPLICATION_FORM_URLENCODED),
                    handler::submit)
            .build();
}
```

Với form object, `ServerRequest.bind()` hỗ trợ bind request parameters, URI variables và headers; có thể cấu hình `DataBinder` để giới hạn field:

```java
Mono<RegistrationForm> form = request.bind(
        RegistrationForm.class,
        binder -> binder.setAllowedFields(
                "name", "email", "category"));
```

Với multipart upload lớn, cân nhắc xử lý `PartEvent` theo streaming thay vì gom file vào memory. Nội dung `DataBuffer` phải được tiêu thụ, chuyển tiếp hoặc release đúng lifecycle để tránh rò rỉ bộ nhớ.

## 12. Truyền dữ liệu sau redirect

Redirect cần URL đích. Có ba cách phổ biến để trang đích biết tài nguyên nào cần hiển thị.

### 12.1. URI template variable

```java
return Rendering.redirectTo("/registrations/{id}")
        .status(HttpStatus.SEE_OTHER)
        .modelAttribute("id", registration.getId())
        .build();
```

Phù hợp cho trang chi tiết của tài nguyên đã lưu. URL mang ID; trang GET tải dữ liệu từ repository/service.

### 12.2. Query parameter

```java
return Rendering.redirectTo("/search?category={category}")
        .status(HttpStatus.SEE_OTHER)
        .modelAttribute("category", "spring")
        .build();
```

Query parameter phù hợp với bộ lọc hoặc trạng thái tìm kiếm không nhạy cảm. Giá trị phải được encode đúng URI. Không đưa thông tin bí mật vào query string vì URL có thể xuất hiện trong browser history, access log, analytics hoặc Referer header.

### 12.3. Session hoặc trạng thái phía server

Nếu cần thông báo một lần hoặc dữ liệu không nên xuất hiện trên URL, có thể lưu trạng thái phía server/session rồi redirect bằng mã tham chiếu ngắn. Quản lý expiry, quyền truy cập và tính đồng thời của session.

Không nhầm API redirect/flash của Spring MVC với WebFlux. `RedirectAttributes` thuộc package Servlet MVC; trong WebFlux, dùng `Rendering`, `RedirectView`, model URI variable hoặc cơ chế lưu trạng thái do ứng dụng quản lý.

## 13. An toàn khi redirect

Redirect URL có thể bị lợi dụng để chuyển người dùng tới website giả mạo nếu server chấp nhận URL do client tùy ý cung cấp.

Ví dụ nguy hiểm:

```java
@GetMapping("/login/success")
public Rendering success(@RequestParam String next) {
    return Rendering.redirectTo(next).build();
}
```

Nếu next là `https://attacker.example`, server sẽ điều hướng người dùng ra khỏi website. Đây là lỗi open redirect.

Cách xử lý:

- Ưu tiên route nội bộ cố định hoặc URI template do server tạo.
- Nếu cần returnUrl, chỉ cho phép relative path nội bộ đã kiểm tra.
- Nếu cần redirect tới host ngoài, dùng allow-list domain chính xác và kiểm tra scheme.
- Không chỉ kiểm tra chuỗi bắt đầu bằng `https://trusted.example`; parse URI và so sánh host đã chuẩn hóa để tránh `trusted.example.attacker.test`.
- Chặn scheme nguy hiểm như `javascript:` và URL protocol-relative `//attacker.example`.
- Không đưa access token, mật khẩu, session ID hoặc dữ liệu cá nhân vào Location.

Redirect sau đăng nhập/logout cần phối hợp với Spring Security. Không tin URL redirect từ query parameter chỉ vì request đã xác thực.

## 14. Chương trình Spring Boot 3.3.5 chạy được

Ví dụ dùng **Java 17+**, **Maven**, **Spring Boot 3.3.5**, Spring WebFlux, Thymeleaf và Bean Validation. Ứng dụng hiển thị form đăng ký, bind dữ liệu, validate, lưu vào store in-memory và trả 303 sau khi lưu thành công. Trang kết quả được tải bằng GET.

Cấu trúc project:

```text
webflux-form-prg/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── FormPrgApplication.java
    │   ├── RegistrationForm.java
    │   ├── Registration.java
    │   ├── RegistrationStore.java
    │   └── RegistrationController.java
    ├── main/resources/templates/
    │   ├── registration-form.html
    │   └── registration-detail.html
    └── test/java/demo/
        └── RegistrationControllerTest.java
```

### 14.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-form-prg</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

### 14.2. FormPrgApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormPrgApplication {
    public static void main(String[] args) {
        SpringApplication.run(FormPrgApplication.class, args);
    }
}
```

### 14.3. RegistrationForm.java

```java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class RegistrationForm {

    @NotBlank(message = "Họ tên là bắt buộc")
    @Size(max = 80, message = "Họ tên tối đa 80 ký tự")
    private String name;

    @NotBlank(message = "Email là bắt buộc")
    @Email(message = "Email không đúng định dạng")
    @Size(max = 160, message = "Email tối đa 160 ký tự")
    private String email;

    @NotBlank(message = "Hãy chọn nhóm")
    private String category;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }
}
```

### 14.4. Registration.java

```java
package demo;

public class Registration {
    private final long id;
    private final String name;
    private final String email;
    private final String category;

    public Registration(long id, String name, String email, String category) {
        this.id = id;
        this.name = name;
        this.email = email;
        this.category = category;
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public String getCategory() {
        return category;
    }
}
```

### 14.5. RegistrationStore.java

```java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class RegistrationStore {
    private final AtomicLong sequence = new AtomicLong();
    private final Map<Long, Registration> registrations =
            new ConcurrentHashMap<>();

    public Mono<Registration> save(RegistrationForm form) {
        return Mono.fromSupplier(() -> {
            long id = sequence.incrementAndGet();

            Registration registration = new Registration(
                    id,
                    form.getName().trim(),
                    form.getEmail().trim(),
                    form.getCategory());

            registrations.put(id, registration);
            return registration;
        });
    }

    public Mono<Registration> findById(long id) {
        return Mono.justOrEmpty(registrations.get(id));
    }
}
```

Store dùng map trong memory để ví dụ chạy độc lập. Khi ứng dụng restart, dữ liệu mất. Hệ thống thật thay store này bằng repository/database reactive; không gọi JDBC blocking trực tiếp trên event loop.

### 14.6. RegistrationController.java

```java
package demo;

import java.util.List;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.reactive.result.view.Rendering;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Controller
@RequestMapping("/registrations")
public class RegistrationController {

    private static final List<String> CATEGORIES =
            List.of("java", "spring", "reactive");

    private final RegistrationStore store;

    public RegistrationController(RegistrationStore store) {
        this.store = store;
    }

    @InitBinder("registrationForm")
    void limitRegistrationFields(WebDataBinder binder) {
        binder.setAllowedFields("name", "email", "category");
    }

    @GetMapping("/new")
    public Rendering newForm() {
        return Rendering.view("registration-form")
                .modelAttribute("registrationForm", new RegistrationForm())
                .modelAttribute("categories", CATEGORIES)
                .build();
    }

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<Rendering> submit(
            @Valid @ModelAttribute("registrationForm")
            RegistrationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return Mono.just(
                    Rendering.view("registration-form")
                            .modelAttribute("registrationForm", form)
                            .modelAttribute(
                                    BindingResult.MODEL_KEY_PREFIX
                                            + "registrationForm",
                                    errors)
                            .modelAttribute("categories", CATEGORIES)
                            .build());
        }

        return store.save(form)
                .map(saved -> Rendering
                        .redirectTo("/registrations/{id}")
                        .status(HttpStatus.SEE_OTHER)
                        .modelAttribute("id", saved.getId())
                        .build());
    }

    @GetMapping("/{id}")
    public Mono<Rendering> detail(@PathVariable long id) {
        return store.findById(id)
                .map(registration -> Rendering
                        .view("registration-detail")
                        .modelAttribute("registration", registration)
                        .build())
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }
}
```

`BindingResult` đứng ngay sau form argument để controller tự xử lý validation errors. Khi lỗi, controller render lại view và đưa form object, binding result cùng danh sách category vào model. Khi hợp lệ, store lưu dữ liệu rồi redirect bằng 303 tới URL chi tiết. Không có thao tác blocking trong controller.

### 14.7. registration-form.html

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng ký</title>
</head>
<body>
<h1>Đăng ký</h1>

<form th:action="@{/registrations}"
      th:object="${registrationForm}"
      method="post">

    <div>
        <label for="name">Họ tên</label>
        <input id="name" type="text" th:field="*{name}">
        <p th:if="${#fields.hasErrors('name')}"
           th:errors="*{name}"></p>
    </div>

    <div>
        <label for="email">Email</label>
        <input id="email" type="email" th:field="*{email}">
        <p th:if="${#fields.hasErrors('email')}"
           th:errors="*{email}"></p>
    </div>

    <div>
        <label for="category">Nhóm</label>
        <select id="category" th:field="*{category}">
            <option value="">-- Chọn nhóm --</option>
            <option th:each="category : ${categories}"
                    th:value="${category}"
                    th:text="${category}"></option>
        </select>
        <p th:if="${#fields.hasErrors('category')}"
           th:errors="*{category}"></p>
    </div>

    <button type="submit">Gửi đăng ký</button>
</form>
</body>
</html>
```

### 14.8. registration-detail.html

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng ký thành công</title>
</head>
<body>
<h1>Đăng ký đã được lưu</h1>
<p>Mã đăng ký: <span th:text="${registration.id}"></span></p>
<p>Họ tên: <span th:text="${registration.name}"></span></p>
<p>Email: <span th:text="${registration.email}"></span></p>
<p>Nhóm: <span th:text="${registration.category}"></span></p>
<a th:href="@{/registrations/new}">Tạo đăng ký khác</a>
</body>
</html>
```

### 14.9. RegistrationControllerTest.java

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class RegistrationControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void displaysRegistrationForm() {
        client.get()
                .uri("/registrations/new")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_HTML)
                .expectBody(String.class)
                .value(html -> {
                    assertThat(html).contains("name=\"name\"");
                    assertThat(html).contains("name=\"email\"");
                    assertThat(html).contains("name=\"category\"");
                });
    }

    @Test
    void invalidFormIsRenderedAgainWithErrors() {
        client.post()
                .uri("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "")
                        .with("email", "not-an-email")
                        .with("category", ""))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(html -> {
                    assertThat(html).contains("Họ tên là bắt buộc");
                    assertThat(html).contains("Email không đúng định dạng");
                    assertThat(html).contains("Hãy chọn nhóm");
                });
    }

    @Test
    void validPostRedirectsWith303AndTheGetLoadsTheSavedRecord() {
        EntityExchangeResult<Void> result = client.post()
                .uri("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "Lan")
                        .with("email", "lan@example.com")
                        .with("category", "reactive"))
                .exchange()
                .expectStatus().isSeeOther()
                .expectHeader().exists(HttpHeaders.LOCATION)
                .returnResult(Void.class);

        String location =
                result.getResponseHeaders().getFirst(HttpHeaders.LOCATION);

        assertThat(location).isNotBlank();

        client.get()
                .uri(location)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(html -> {
                    assertThat(html).contains("Đăng ký đã được lưu");
                    assertThat(html).contains("Lan");
                    assertThat(html).contains("lan@example.com");
                });
    }
}
```

Test thứ nhất xác nhận form được render. Test thứ hai gửi dữ liệu sai và xác nhận trang form hiển thị lại ba lỗi. Test thứ ba gửi form hợp lệ, xác nhận response 303 có Location, sau đó chủ động gọi GET URL đó và xác nhận trang chi tiết chứa dữ liệu đã lưu.

### 14.10. Chạy ứng dụng và thử bằng curl

Tại thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Mở form trong trình duyệt:

```text
http://localhost:8080/registrations/new
```

Gửi form hợp lệ từ terminal:

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "name=Lan" \
  --data-urlencode "email=lan@example.com" \
  --data-urlencode "category=reactive"
```

Response có dạng:

```http
HTTP/1.1 303 See Other
Location: /registrations/1
```

ID cụ thể phụ thuộc số lần lưu trong tiến trình hiện tại. Dùng URL nhận được trong Location để gọi trang kết quả:

```bash
curl -i http://localhost:8080/registrations/1
```

Response GET trả 200 OK và HTML có thông tin đăng ký. Khi chạy test:

```bash
mvn test
```

Ba integration tests kiểm tra trang form, validation error và luồng POST → 303 → GET. Ứng dụng dùng store in-memory nên dữ liệu chỉ tồn tại đến khi tiến trình dừng.

## 15. Lỗi thường gặp và cách xử lý

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Trả HTML trực tiếp sau POST khi muốn PRG | Refresh có thể gửi lại POST | Trả 303 và đưa người dùng tới GET. |
| Dùng 307/308 cho PRG | Browser gửi lại POST/body tới URL mới | Dùng 303 nếu muốn request tiếp theo là GET. |
| Dùng 301/308 cho URL chỉ đổi tạm thời | Client/proxy có thể cache redirect lâu dài | Chọn status tạm thời phù hợp. |
| Coi 302 và 303 giống hệt nhau | Method handling không được thể hiện rõ | Dùng 303 để chỉ rõ chuyển sang GET sau POST. |
| Nghĩ redirect là forward nội bộ | Chờ server gọi controller thứ hai trong cùng request | Redirect tạo response 3xx và client gửi request mới. |
| Dùng forward: trong WebFlux | Không có Servlet FORWARD dispatch tương ứng | Dùng view rendering hoặc redirect đúng semantics. |
| Dùng @RequestBody để nhận form URL-encoded như JSON | Codec không bind theo cách mong đợi | Dùng @ModelAttribute, @RequestParam hoặc ServerRequest.formData(). |
| Bind trực tiếp entity vào form | Client có thể gửi thêm property nhạy cảm | Dùng form DTO riêng và giới hạn allowed fields. |
| Đặt BindingResult xa @ModelAttribute | Spring không ghép lỗi với đúng command object | Đặt BindingResult ngay sau argument được validate. |
| Render lại form nhưng quên danh sách select | Select không có option hoặc mất lựa chọn | Nạp lại dữ liệu hỗ trợ vào model khi render form lỗi. |
| Dùng form field name không khớp property | Giá trị không được bind | Đồng bộ name với property hoặc cấu hình BindParam. |
| Tin hidden input hoặc ID từ form | Người dùng có thể sửa ID/owner/role | Kiểm tra quyền ở server và không tin giá trị client gửi. |
| Chuyển toàn bộ form object vào redirect model | Dữ liệu có thể xuất hiện trong URL | Chỉ đưa ID hoặc tham số công khai cần thiết. |
| Redirect tới URL do người dùng nhập | Open redirect và phishing | Dùng route nội bộ hoặc allow-list host/path. |
| Đưa token hoặc PII vào query string | Lộ qua history, log hoặc Referer | Lưu trạng thái phía server hoặc dùng mã tham chiếu an toàn. |
| Nghĩ PRG chống mọi request trùng | Double-click hoặc retry vẫn có thể tạo hai bản ghi | Dùng idempotency key và unique constraint cho thao tác quan trọng. |
| Redirect API JSON và mong tab trình duyệt tự điều hướng | fetch có thể theo redirect nội bộ nhưng không chuyển top-level page | Trả JSON/Location và để client điều hướng rõ ràng. |
| Dùng block() trong controller reactive | Chặn event loop và giảm khả năng phục vụ đồng thời | Trả Mono/Flux và dùng reactive repository. |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Redirect HTTP khác render view như thế nào?  
**Đáp án:** Render view tạo response nội dung cho request hiện tại. Redirect trả status 3xx và Location để client gửi request mới.

**Câu 2.** Vì sao PRG thường dùng 303?  
**Đáp án:** 303 yêu cầu client lấy tài nguyên đích bằng GET sau POST, nhờ đó refresh trang kết quả không gửi lại POST trong luồng thông thường.

**Câu 3.** Khi nào dùng 307 hoặc 308?  
**Đáp án:** Khi cần redirect nhưng phải giữ nguyên method và body của request gốc; 307 tạm thời, 308 vĩnh viễn.

**Câu 4.** Prefix redirect: trong WebFlux có tác dụng gì?  
**Đáp án:** View resolver nhận biết đây là redirect URL và dùng redirect view để trả response 3xx. WebFlux không hỗ trợ forward: dispatch.

**Câu 5.** Rendering.redirectTo() dùng để làm gì?  
**Đáp án:** Tạo redirect view bằng API Rendering, cho phép cấu hình URL, status, model attribute và một số header.

**Câu 6.** Dùng @RequestParam hay @ModelAttribute khi nào?  
**Đáp án:** @RequestParam phù hợp với một vài field đơn lẻ; @ModelAttribute phù hợp với form object có nhiều field và cần binding/validation chung.

**Câu 7.** BindingResult phải đặt ở đâu?  
**Đáp án:** Ngay sau argument @ModelAttribute được validate để controller đọc lỗi binding và validation của object đó.

**Câu 8.** Functional endpoint đọc form URL-encoded bằng API nào?  
**Đáp án:** ServerRequest.formData() trả Mono<MultiValueMap<String, String>>; ServerRequest.bind() có thể bind request data vào object.

**Câu 9.** Vì sao không nên bind trực tiếp entity vào form?  
**Đáp án:** Entity có thể chứa property nhạy cảm hoặc không thuộc quyền sửa của người dùng; DTO riêng và allowed fields giảm nguy cơ over-posting.

**Câu 10.** Open redirect là gì?  
**Đáp án:** Server redirect tới URL tùy ý do client cung cấp, có thể bị lợi dụng để đưa người dùng tới website giả mạo. Cần allow-list hoặc chỉ cho phép route nội bộ.

## Ghi nhớ

- Redirect là response HTTP 3xx có Location; client tạo request tiếp theo. Render view chỉ tạo nội dung cho request hiện tại.
- Dùng 303 See Other cho PRG sau khi xử lý POST; dùng 307/308 khi cần giữ nguyên method/body.
- WebFlux hỗ trợ redirect: view name, Rendering.redirectTo và ServerResponse trong functional endpoint.
- Dùng @RequestParam cho field đơn giản, @ModelAttribute cho form object; functional endpoint có ServerRequest.formData() và bind().
- Validate bằng @Valid, đặt BindingResult ngay sau form argument và render lại form với lỗi khi dữ liệu không hợp lệ.
- Bind vào DTO riêng, giới hạn allowed fields, bảo vệ CSRF và không tin hidden input.
- Không chuyển dữ liệu nhạy cảm qua query string hoặc redirect URL. Kiểm tra đích redirect để ngăn open redirect.
- PRG giảm việc gửi lại POST khi refresh; thao tác quan trọng vẫn cần idempotency để chống xử lý trùng.

### Tài liệu tham khảo

1. [Spring Framework – WebFlux Data Binding](https://docs.spring.io/spring-framework/reference/web/webflux/data-binding.html): data binding và WebDataBinder.
2. [Spring Framework – @ModelAttribute trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/modelattrib-method-args.html): form binding, constructor/property binding và BindingResult.
3. [Spring Framework – Validation trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): Bean Validation và lỗi validation.
4. [Spring Framework – DispatcherHandler và View Resolution](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html): view resolution, redirect prefix và giới hạn forward.
5. [Spring Framework – Rendering Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/result/view/Rendering.html): Rendering và redirect builder.
6. [Spring Framework – RedirectView Javadoc](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/web/reactive/result/view/RedirectView.html): status redirect mặc định và cấu hình Location.
7. [Spring Framework – Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): ServerRequest, formData, bind và ServerResponse.
8. [Spring Framework – ServerResponse Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html): xây dựng response và Location header.
9. [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): semantics của redirect status và phương thức HTTP.
