# Đọc path variable, query parameter, header và cookie trong Spring Boot

## 1. Mục tiêu và bức tranh tổng quan

HTTP request không chỉ có body. Một endpoint Spring Boot thường cần đọc **biến trong đường dẫn**, **tham số truy vấn**, **HTTP headers** và **cookies** để xác định tài nguyên, cách lọc hoặc phân trang, thông tin liên quan request và trạng thái lựa chọn của client. Trong Spring MVC và Spring WebFlux theo kiểu annotated controller, các annotation phổ biến là:

- **@PathVariable**: lấy giá trị đã khớp từ path template, ví dụ itemId trong /api/items/42.
- **@RequestParam**: lấy query parameter, ví dụ page=2 hoặc tag=java trong ?page=2&tag=java.
- **@RequestHeader**: lấy HTTP request header, ví dụ X-Request-Id: req-42.
- **@CookieValue**: lấy một request cookie theo tên, ví dụ Cookie: theme=dark.

Bốn nguồn này khác nhau về vị trí trên HTTP request, khả năng lặp giá trị, ngữ nghĩa và mức độ tin cậy. Đọc đúng nguồn dữ liệu chỉ là bước đầu; còn phải **chuyển kiểu, gán mặc định, validate, giới hạn độ dài và kiểm soát bảo mật** trước khi đưa vào logic nghiệp vụ.

Bài dùng **Java 17+, Spring Boot 3.3.x và Spring Framework 6.1.x**. Ví dụ chạy đầy đủ dùng Spring MVC với embedded Tomcat, sau đó so sánh cách dùng annotation và functional API trong Spring WebFlux. Đây là nội dung về **đọc dữ liệu HTTP request**, không phải hướng dẫn thay thế toàn bộ authentication, API gateway hoặc routing framework.

Kết thúc bài, người đọc có thể:

1. Chọn đúng annotation và kiểu Java cho path, query, header, cookie.
2. Phân biệt trường hợp thiếu, rỗng, sai kiểu và có nhiều giá trị.
3. Giải thích cách DispatcherServlet/DispatcherHandler phân giải argument.
4. Đọc an toàn input đã encode và hạn chế các rủi ro tin nhầm header/cookie do client kiểm soát.
5. Xây một REST controller Java 17 hoạt động được, kiểm thử với MockMvc và cURL.
6. Nhận biết khác biệt khi dùng Spring WebFlux annotated controller và functional endpoints.

## 2. Nhìn một HTTP request cụ thể

Giả sử client gửi:

~~~http
GET /api/items/42?page=2&tag=spring&tag=java HTTP/1.1
Host: localhost:8080
Accept: application/json
X-Request-Id: req-42
Cookie: theme=dark; locale=vi
~~~

Các phần cần phân biệt:

| Nguồn | Phần trong request | Giá trị ví dụ | Spring annotation |
| --- | --- | --- | --- |
| Path variable | Đường dẫn khớp /api/items/{itemId} | itemId = "42" | @PathVariable("itemId") |
| Query parameter | Phần sau dấu ? của URL | page = "2" | @RequestParam("page") |
| Query lặp | Nhiều cặp cùng key | tag = ["spring", "java"] | @RequestParam("tag") List<String> |
| Header | Dòng metadata HTTP | X-Request-Id = "req-42" | @RequestHeader("X-Request-Id") |
| Cookie | Giá trị trong request Cookie header | theme = "dark" | @CookieValue("theme") |

**Không phải tất cả đều là path parameter.** Chuỗi page=2 nằm trong URL, nhưng nó thuộc **query string**, không thuộc path segment. Cookie có thể được client gửi qua header Cookie, nhưng @CookieValue là abstraction chuyên biệt giúp lấy một cookie theo tên; @RequestHeader("Cookie") trả lại raw header chứ không phải một object cookie đã phân tích theo ý nghĩa application.

HTTP request body, ví dụ JSON cho POST, là nguồn riêng: thông thường đọc bằng @RequestBody, không thay @RequestParam hoặc @CookieValue.

### Phân biệt URL, URI và phần đã decode

URL:

~~~text
http://localhost:8080/api/items/42?page=2&tag=spring
                           ^^^^^^^^^^^^ ^^^^^^^^^^^^^^^^^
                           request path  query string
~~~

Path template được framework match với phần path; query string **không tạo một path segment mới**. Encoding, proxy rewrite, context path và path matching strategy có thể ảnh hưởng kết quả; phần sau sẽ bàn cụ thể.

## 3. @PathVariable: lấy giá trị từ URL path

### 3.1 Khai báo cơ bản

~~~java
@GetMapping("/api/items/{itemId}")
public String find(@PathVariable("itemId") long itemId) {
    return "item=" + itemId;
}
~~~

Đây là **method minh họa**, cần đặt trong @RestController với imports. Khi GET /api/items/42, Spring tìm mapping tương ứng rồi chuyển chuỗi path "42" sang long 42.

Điều quan trọng:

- **{itemId}** là tên biến trong URI template.
- **@PathVariable("itemId")** liên kết tham số Java với biến đó.
- **long** yêu cầu Spring thực hiện type conversion. Nếu nhận /api/items/abc, binding sang long có thể thất bại và framework thường trả HTTP 400.
- Nếu route không match, controller method có thể không được chọn; đây là tình huống mapping khác với conversion failure.

Khai báo tên rõ ràng trong annotation giúp code không phụ thuộc việc compiler giữ tên tham số Java hay không:

~~~java
@PathVariable("itemId") long itemId
~~~

so với:

~~~java
@PathVariable long itemId
~~~

Cả hai có thể hoạt động trong dự án được cấu hình giữ parameter names, nhưng cách thứ nhất rõ ràng và dễ kiểm tra hơn.

### 3.2 Nhiều path variables

~~~java
@GetMapping("/shops/{shopId}/items/{itemId}")
public String find(
        @PathVariable("shopId") String shopId,
        @PathVariable("itemId") long itemId) {
    return shopId + ":" + itemId;
}
~~~

Ví dụ GET /shops/hn-01/items/42 trả body "hn-01:42" nếu method thuộc @RestController hoặc có @ResponseBody. Tên biến ở route và annotation phải khớp.

### 3.3 Kiểu dữ liệu và lỗi chuyển đổi

Spring hỗ trợ nhiều kiểu conversion phổ biến:

- String cho mã chứa chữ và số.
- long, int, UUID, enum (phụ thuộc cách đặt tên enum và converter).
- Kiểu Java nghiệp vụ có Converter/Formatter được đăng ký.
- Optional<T> hoặc các thiết kế khác khi framework và mapping phù hợp.

Với @PathVariable long, nếu path chỉ được match nhưng giá trị không parse được, Spring MVC thường ném MethodArgumentTypeMismatchException hoặc exception liên quan đến conversion rồi tạo 400. Không dùng try/catch NumberFormatException trong từng controller khi framework đã xử lý binding; hãy tùy chỉnh error contract nếu client cần JSON lỗi thống nhất.

### 3.4 Biến path có phải luôn optional?

Thông thường, path variable là thành phần **bắt buộc để route match**. Dùng @PathVariable(required=false) không tự làm đường dẫn "/items/{id}" match "/items" nếu bạn chưa định nghĩa mapping thay thế. Nếu có hai route khác nhau, hãy khai báo rõ:

~~~java
@GetMapping({"/api/items", "/api/items/{itemId}"})
public String listOrFind(
        @PathVariable(name = "itemId", required = false) Long itemId) {
    return itemId == null ? "all" : "item=" + itemId;
}
~~~

Snippet này cần đặt trong controller phù hợp. Dùng wrapper Long thay cho primitive long nếu có thể vắng mặt. Tuy nhiên, thiết kế REST thường rõ hơn khi tách GET /items và GET /items/{id} thành hai method.

### 3.5 Ký tự đặc biệt và encoded slash

Path có thể chứa percent-encoded characters. Không giả định %2F luôn được xử lý như một dấu "/" trong cùng một path variable: proxy, servlet container, firewall/path matching và phiên bản framework có thể xử lý encoded slash khác nhau. Nếu identifier cần chứa nhiều ký tự đặc biệt hoặc slash, cân nhắc thiết kế ID URL-safe hoặc dùng query parameter theo nhu cầu.

Đừng ghép trực tiếp raw path variable vào đường dẫn file hệ điều hành, câu SQL, shell command hoặc URL nội bộ mà không validate/encode theo đúng ngữ cảnh. Framework giúp đọc giá trị; **nó không làm mọi giá trị trở nên an toàn cho mọi sink**.

## 4. @RequestParam: lấy query parameters

### 4.1 Tham số bắt buộc và tham số mặc định

~~~java
@GetMapping("/api/search")
public String search(
        @RequestParam("q") String keyword,
        @RequestParam(name = "page", defaultValue = "1") int page) {
    return keyword + ":" + page;
}
~~~

Đây là method minh họa. Với GET /api/search?q=spring&page=3, các giá trị Java tương ứng là "spring" và 3.

Mặc định @RequestParam không có defaultValue và required=true; nếu query parameter bắt buộc bị thiếu, Spring MVC thường trả HTTP 400 với lỗi MissingServletRequestParameterException. Trong WebFlux có các exception tương ứng thuộc reactive stack; không phải mọi class exception trong MVC đều dùng được ở WebFlux.

Khi khai báo:

~~~java
@RequestParam(name = "page", defaultValue = "1") int page
~~~

Spring sẽ dùng mặc định "1" khi không có giá trị và với các tình huống giá trị rỗng được default handling áp dụng. defaultValue cũng làm tham số không còn bắt buộc theo ý nghĩa annotation. Nếu client gửi page=abc, giá trị hiện diện nhưng sai kiểu; **defaultValue không có nghĩa là mọi input sai kiểu được thay bằng 1**.

### 4.2 required=false và Optional<T>

Hai cách thường dùng cho giá trị có thể thiếu:

~~~java
@RequestParam(name = "sort", required = false) String sort
~~~

~~~java
@RequestParam(name = "sort") Optional<String> sort
~~~

Đoạn trên là khai báo tham số, không phải class độc lập. Với String và required=false, code phải chấp nhận null hoặc xử lý hợp lý; Optional<String> thể hiện ý nghĩa có/không rõ hơn. Tránh dùng primitive int/boolean nếu thực sự muốn nhận null; dùng wrapper Integer/Boolean hoặc defaultValue.

**Giá trị thiếu khác giá trị rỗng.** Ví dụ "?q=" không giống hoàn toàn việc không có q; hành vi default/required/conversion phụ thuộc annotation và kiểu tham số. Hãy test cụ thể quy tắc API muốn chấp nhận thay vì giả định tất cả đều tương đương.

### 4.3 Tham số query lặp

Ví dụ:

~~~text
GET /api/items?tag=spring&tag=java&tag=backend
~~~

Một cách đọc thường gặp:

~~~java
@RequestParam(name = "tag", required = false)
List<String> tags
~~~

Spring có thể bind nhiều giá trị vào List<String>. Nếu thiếu, hãy xử lý null/empty ở ranh giới controller theo lựa chọn rõ ràng. Đừng nghĩ mỗi query key luôn chỉ có một value; API có thể cho phép lặp và các framework/client có thể có quy ước khác về dấu phẩy.

Khi cần **toàn bộ query parameters** và giữ các giá trị trùng, trong Spring MVC có thể dùng:

~~~java
@RequestParam MultiValueMap<String, String> query
~~~

Cần import org.springframework.util.MultiValueMap. Một Map<String,String> đơn giản không biểu diễn đầy đủ nhiều giá trị cùng key. Với endpoint công khai, việc nhận có chọn lọc từng tham số thường an toàn và dễ document hơn việc mở toàn bộ Map.

### 4.4 Query string và form data không phải lúc nào giống nhau

Trong Spring MVC Servlet stack, @RequestParam có thể làm việc với request parameters được Servlet container cung cấp, bao gồm query string và các trường form-encoded ở những tình huống thích hợp. Trong Spring WebFlux, @RequestParam gắn với query parameters theo semantics reactive; form data có API/cách binding riêng. Đừng viết một library giả định cả hai stack luôn xem query và form body là một nguồn.

Với JSON POST, dùng @RequestBody DTO; @RequestParam không tự deserialize một JSON object từ request body.

## 5. @RequestHeader: đọc metadata HTTP

### 5.1 Đọc một header

~~~java
@GetMapping("/api/trace")
public String trace(
        @RequestHeader("X-Request-Id") String requestId) {
    return requestId;
}
~~~

Header names trong HTTP không phân biệt chữ hoa/chữ thường theo giao thức. Client có thể gửi x-request-id thay cho X-Request-Id và HTTP layer vẫn coi chúng là cùng tên header, dù biểu diễn/normalization cụ thể có thể khác theo proxy.

### 5.2 Header tùy chọn và mặc định

~~~java
@RequestHeader(name = "X-Request-Id", required = false)
String requestId
~~~

hoặc:

~~~java
@RequestHeader(name = "X-Client-Version", defaultValue = "unknown")
String clientVersion
~~~

Nếu ứng dụng tự dùng một request ID từ client cho logging, hãy áp dụng giới hạn độ dài, ký tự được phép và cơ chế chuẩn hóa; không tin ngay mọi chuỗi mà client gửi. Các header có thể bị bỏ, thay đổi hoặc tái tạo bởi proxy/gateway.

### 5.3 Nhiều header values

HTTP có các header cho phép danh sách values và những header có quy tắc đặc thù. Spring có thể cung cấp:

~~~java
@RequestHeader HttpHeaders headers
~~~

hoặc một MultiValueMap<String,String> phù hợp. HttpHeaders thuộc org.springframework.http.HttpHeaders và cho phép đọc getFirst(name), get(name) cùng các accessor chuyên biệt khác.

Đừng tự chia tất cả header theo dấu phẩy. Chẳng hạn, cú pháp Set-Cookie có quy tắc riêng và không thể parse đúng chỉ bằng split(","). Với Authorization, Content-Type và header có semantics phức tạp, ưu tiên API/framework tương ứng thay vì parser chuỗi thô.

### 5.4 Những header phổ biến

| Header | Mục đích thường gặp | Lưu ý |
| --- | --- | --- |
| Accept | Client muốn nhận media type nào | Spring dùng content negotiation; 406 có thể xảy ra |
| Content-Type | Media type của request body | Rất quan trọng với @RequestBody; 415 có thể xảy ra |
| Authorization | Credential/token | Xử lý bằng Spring Security, không tự log hoặc tin token từ String |
| X-Request-Id | Correlation/tracing theo quy ước | Validate, hạn chế độ dài, tạo ID mới nếu cần |
| If-None-Match | Conditional request/ETag | Dùng HTTP response/cache abstraction |
| If-Modified-Since | Conditional request theo thời gian | Cần dùng đúng parser/semantics |
| Forwarded / X-Forwarded-* | Thông tin từ reverse proxy | Chỉ tin khi proxy đầu vào được quản lý và cấu hình trust rõ |

**Header là dữ liệu do phía gửi hoặc proxy có thể kiểm soát**, không phải một nguồn xác thực mặc định. Lấy username từ X-User-Id và tin là đã authenticate là rủi ro bảo mật nếu gateway không bảo vệ header đó.

### 5.5 Đọc tất cả headers có nên không?

Một controller có thể nhận HttpHeaders để quan sát, nhưng đừng serialize toàn bộ header map trả cho client hoặc ghi tràn vào log. Nó có thể chứa Authorization, Cookie, API key hoặc thông tin nhạy cảm. Lấy đúng trường cần thiết sẽ giảm coupling và nguy cơ lộ dữ liệu.

## 6. @CookieValue: đọc request cookie

### 6.1 Cookie được gửi như thế nào?

Sau khi server từng phản hồi Set-Cookie phù hợp, browser có thể gửi cookie trong những request tiếp theo:

~~~http
Cookie: theme=dark; locale=vi
~~~

Trong annotated controller:

~~~java
@GetMapping("/api/preferences")
public String preferences(
        @CookieValue(name = "theme", defaultValue = "light")
        String theme) {
    return theme;
}
~~~

Khi request có theme=dark, method nhận "dark". Khi không có cookie theme, defaultValue="light" được dùng.

### 6.2 Cookie và header khác nhau ở đâu?

- **Cookie** trong request mang các cặp name=value mà client gửi theo scope policy.
- **Set-Cookie** là response header để server yêu cầu browser lưu/cập nhật cookie và các thuộc tính áp dụng.
- Thuộc tính HttpOnly, Secure, SameSite, Path, Domain và Max-Age thường nằm trong **Set-Cookie của response**, không phải một tập field client gửi lại trong Cookie header trên mỗi request.
- Browser có quy tắc gửi cookie theo domain/path/secure/SameSite và policy của trình duyệt. Client HTTP tự viết vẫn có thể giả mạo Cookie header.

Ví dụ response thiết lập cookie:

~~~http
Set-Cookie: theme=dark; Path=/; SameSite=Lax
~~~

Header trên chỉ minh họa; nếu cookie nhạy cảm liên quan session, thường cần HttpOnly, Secure trên HTTPS, thiết kế SameSite/CSRF và thời hạn phù hợp. Cookie theme đơn giản phục vụ UI không đồng nghĩa với cookie session bảo mật.

### 6.3 Đặt cookie bằng ResponseCookie

Spring cung cấp org.springframework.http.ResponseCookie; trong controller hoặc filter có thể thêm qua response API. Ví dụ Spring MVC:

~~~java
ResponseCookie cookie = ResponseCookie.from("theme", "dark")
        .path("/")
        .httpOnly(false)
        .sameSite("Lax")
        .build();
response.addHeader(HttpHeaders.SET_COOKIE, cookie.toString());
~~~

Đây là snippet trong method đã có HttpServletResponse response, cần imports. Trong Spring WebFlux, response.getCookies().add(...) là cách phù hợp với ServerHttpResponse. Với session cookie, lựa chọn httpOnly(false) ở ví dụ theme **không** phù hợp cho một credential cookie; nên bật HttpOnly và Secure nếu use case yêu cầu.

### 6.4 Cookie không phải nguồn identity đáng tin tự thân

Một client có thể đặt "role=admin" hoặc "userId=42" vào Cookie header và gửi tới server. **Không thể phân quyền dựa vào cookie text chưa xác thực**. Session ID cần được kiểm tra với server-side session storage hoặc cơ chế token có integrity/authentication; dùng Spring Security và các biện pháp CSRF phù hợp.

Với dữ liệu tùy chọn như giao diện theme, hãy whitelist values ("light", "dark"), giới hạn độ dài và tránh truyền giá trị cookie chưa validate vào HTML/SQL/header khác.

### 6.5 Cookie cùng tên và phạm vi

Trong thực tế có thể tồn tại cookie cùng tên nhưng khác Path/Domain; request có thể mang nhiều cặp cùng tên. Không xây logic nghiệp vụ phụ thuộc “cookie đầu tiên chắc chắn là cookie đúng” khi ứng dụng cho phép cấu hình scope phức tạp. Thiết kế tên và scope cookie rõ ràng, và với session/auth ưu tiên hạ tầng security đã được kiểm thử.

## 7. Cơ chế Spring đọc các annotation

### 7.1 Spring MVC

Trong Spring MVC:

~~~mermaid
flowchart TD
    A["HTTP request / Tomcat"] --> B["Servlet Filter chain"]
    B --> C["DispatcherServlet"]
    C --> D["RequestMappingHandlerMapping"]
    D --> E["HandlerMethod được chọn"]
    E --> F["RequestMappingHandlerAdapter"]
    F --> G["HandlerMethodArgumentResolver"]
    G --> H["ConversionService / Formatter / Validator"]
    H --> I["Controller method"]
    I --> J["Return-value handler / HttpMessageConverter"]
    J --> K["HTTP response"]
~~~

Luồng trên là mô hình cho annotation controller thông thường. Các HandlerMethodArgumentResolver được Spring đăng ký cho từng nguồn dữ liệu: path variable, request param, request header, cookie v.v. Resolver tìm giá trị thô; conversion service hoặc binder chuyển sang kiểu tham số Java. Nếu required data thiếu hoặc conversion thất bại, request có thể kết thúc bằng lỗi **trước khi controller method được gọi**.

**HandlerMapping chỉ chọn method, không tự biến query "page=2" thành int.** Việc tạo đối số thuộc tầng HandlerAdapter/argument resolvers.

### 7.2 Spring WebFlux annotated controller

Spring WebFlux dùng DispatcherHandler thay vì DispatcherServlet, ServerWebExchange thay vì HttpServletRequest và reactive HandlerAdapter/argument resolution. Tuy nhiên bốn annotation @PathVariable, @RequestParam, @RequestHeader và @CookieValue cũng được dùng ở annotated controllers.

Khác biệt cốt lõi nằm ở framework runtime và nguồn dữ liệu phù hợp, không nằm ở việc đổi tên bốn annotation này. @RequestParam của WebFlux nhấn mạnh query parameters; xử lý body reactive thường dùng @RequestBody Mono<T> hoặc DTO theo khả năng decoder, không copy nguyên một Servlet-specific controller.

**Không suy luận rằng server chạy WebFlux chỉ vì method trả Mono.** Một Spring MVC controller cũng có thể trả một số reactive return types qua Servlet async support.

## 8. Required, optional, defaultValue — chọn có chủ đích

Các annotation cho phép biểu diễn nhiều kiểu input contract:

| Tình huống | Ví dụ | Quy tắc nên document |
| --- | --- | --- |
| Path variable bắt buộc | @PathVariable("id") long id | Route cần path segment và kiểu hợp lệ |
| Query bắt buộc | @RequestParam("q") String q | Thiếu q thường là 400 |
| Query có mặc định | @RequestParam(name="page", defaultValue="1") int page | Mặc định khi thiếu/rỗng theo semantics annotation |
| Query tùy chọn | @RequestParam(name="sort", required=false) String sort | Controller phải xử lý null |
| Header tùy chọn | @RequestHeader(name="X-Trace", required=false) String trace | Không coi là authentication |
| Header mặc định | @RequestHeader(name="X-Client", defaultValue="web") String client | Giá trị mặc định rõ nghĩa |
| Cookie mặc định | @CookieValue(name="theme", defaultValue="light") String theme | Nên whitelist |
| Cookie bắt buộc | @CookieValue("session") String id | Thường nên giao xác thực session cho Spring Security |

**Đừng dùng defaultValue để che giấu lỗi input sai kiểu.** Đối với tham số như page, nên kiểm tra cả page=0, page=-1, page=abc, page= và trường hợp không có page. Điều kiện chấp nhận là một phần của API contract, không chỉ quyết định bởi annotation.

### Optional<T> có phù hợp không?

Optional<String> giúp mô tả sự hiện diện của input. Tuy nhiên, đừng biến mọi method parameter thành Optional nếu defaultValue đã rõ ràng hoặc nghiệp vụ yêu cầu bắt buộc. Trong response DTO, Optional thường không phải kiểu JSON field nên lạm dụng.

## 9. Chuyển kiểu dữ liệu (type conversion)

Annotation method parameters không nhất thiết là String:

~~~java
@GetMapping("/api/tasks/{id}")
public String task(
        @PathVariable("id") UUID id,
        @RequestParam(name = "limit", defaultValue = "20") int limit,
        @RequestHeader(name = "X-Debug", defaultValue = "false")
        boolean debug) {
    // ...
}
~~~

Snippet này minh họa đối số, cần import UUID và đặt trong một controller phù hợp.

Các chuyển đổi thông dụng:

- String path "42" -> long 42.
- String query "true" -> boolean true theo conversion support.
- String UUID hợp lệ -> java.util.UUID.
- String enum phù hợp -> enum value.
- String date -> LocalDate khi dùng format/config thích hợp.

Với date query:

~~~java
@RequestParam("day")
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
LocalDate day
~~~

Cần import org.springframework.format.annotation.DateTimeFormat và java.time.LocalDate.

**Không nhầm ConversionService với JSON decoder.** @RequestBody JSON thường sử dụng HttpMessageConverter (MVC) hoặc HttpMessageReader (WebFlux) và Jackson. Formatter/Converter cho path/query/header/cookie value không mặc nhiên đổi tên field JSON hoặc áp dụng cùng serializer.

### Custom value object

Nếu domain dùng OrderId thay long/String, có thể đăng ký Converter<String,OrderId> hoặc Formatter<OrderId> theo WebMvcConfigurer (MVC) hoặc WebFluxConfigurer (WebFlux). Chọn custom converter khi muốn giữ invariant của domain type, không phải để né validate hoặc thay security layer.

## 10. Input validation và lỗi HTTP thường gặp

Một số lỗi xảy ra **trước khi method chạy**:

| Request | Nguyên nhân | Kết quả thường gặp |
| --- | --- | --- |
| GET /api/items/abc | @PathVariable long không chuyển được | 400 Bad Request |
| GET /api/search không có q | @RequestParam("q") bắt buộc | 400 Bad Request |
| GET /api/items/42?page=abc | @RequestParam int chuyển kiểu lỗi | 400 Bad Request |
| GET /api/items/42?page=0 | Conversion thành công, nhưng nghiệp vụ từ chối | 400 nếu ứng dụng validate/throw phù hợp |
| Thiếu @RequestHeader required | Header bắt buộc không có | 400 theo default argument resolution |
| Thiếu @CookieValue required | Cookie bắt buộc không có | 400 theo default argument resolution |
| GET /api/unknown | Không có mapping | 404 Not Found |
| POST tới route chỉ có GET | Method không được hỗ trợ | 405 Method Not Allowed |

Đây là những hành vi thông thường của Spring MVC/WebFlux với cấu hình lỗi mặc định. Exception class và error body khác giữa hai stacks, phiên bản và @ControllerAdvice/WebExceptionHandler riêng. Đừng đảm bảo mọi sự cố đều cho một JSON body giống nhau nếu chưa thiết kế error response contract.

### Validation của giá trị scalar

Có thể dùng Jakarta Validation như @Min(1), @NotBlank, @Pattern với method validation setup phù hợp. Spring Boot 3.x thông thường cần dependency spring-boot-starter-validation nếu muốn provider Jakarta Validation. Spring Framework 6.1 có cơ chế method validation tích hợp cho những kiểu controller; exception có thể là HandlerMethodValidationException hoặc loại khác tùy stack và cấu hình.

Với ví dụ chạy độc lập trong bài, ta kiểm tra page >= 1 bằng guard explicit để không phải phụ thuộc một cấu hình validation mở rộng. Trong ứng dụng thực, dùng ràng buộc ở API DTO/method phù hợp và thống nhất cách trả lỗi.

### Validate quan hệ giữa các nguồn

Một request có thể cung cấp shopId trong path, tenantId trong header và session cookie. Việc cả ba đều parse thành công **không chứng minh chúng thuộc cùng một tenant/user**. Sau authentication, service/security phải soát authorization giữa principal, tenant và resource.

## 11. Encoding và chuẩn hóa dữ liệu request

### 11.1 Query parameters

Query string dùng percent encoding cho những ký tự không phù hợp. Với cURL, có thể dùng --get --data-urlencode để gửi giá trị thay vì tự nối chuỗi:

~~~bash
curl --get --data-urlencode 'q=Spring Boot & WebFlux' \
  'http://localhost:8080/api/search'
~~~

Lệnh minh họa cách encode query, không phải endpoint bắt buộc của ví dụ chạy ở mục sau.

Nhiều client xử lý "+" theo quy ước form-style thành space trong query; hành vi có thể bị ảnh hưởng bởi parser/proxy. Khi giá trị quan trọng, ưu tiên client library có URI builder đúng chuẩn thay vì ghép chuỗi thủ công.

### 11.2 Path variables

Không tự encode toàn bộ URL bằng một replace() tùy tiện. Dùng URI builder của HTTP client để encode path segments khi cần. Với ID có dấu "/" hoặc những ký tự đặc biệt, nên thiết kế endpoint URL-safe; đừng giả định encoded slash được mọi reverse proxy/servlet container cho phép giống nhau.

### 11.3 Headers

Header names không phân biệt hoa/thường; header values có cú pháp riêng. Đừng đưa dữ liệu chưa kiểm soát vào header response. Spring có bảo vệ chống một số ký tự không hợp lệ, nhưng bạn vẫn cần validate request ID, giới hạn độ dài và tránh log injection.

### 11.4 Cookies

Cookie names/values có cú pháp và phạm vi áp dụng riêng. Không tự tạo cookie bằng cách nối chuỗi chưa encode; dùng ResponseCookie hoặc API cookie của stack. Đừng đưa JSON phức tạp trực tiếp vào cookie nếu có thể dùng server-side session hoặc format được ký/xác thực phù hợp.

## 12. Ví dụ Spring Boot MVC chạy được: đọc đủ bốn nguồn

Ta xây REST endpoint GET /api/items/{itemId} trả JSON chứa dữ liệu đã bind từ bốn nguồn. Dự án dùng **Java 17, Spring Boot 3.3.13, Gradle**, không cần database.

Yêu cầu:

- Path {itemId} được chuyển sang long.
- Query page mặc định 1 và phải >= 1.
- Query tag cho phép lặp, nếu không có coi như danh sách rỗng.
- Header X-Request-Id là tùy chọn.
- Cookie theme mặc định light; chỉ cho phép light hoặc dark.
- Response là JSON của Java record.
- Test đúng binding, default values, header/cookie và lỗi conversion.

### 12.1 Cấu trúc project

~~~text
request-input-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/requestdata/
    │   ├── RequestDataApplication.java
    │   └── ItemController.java
    └── test/java/com/example/requestdata/
        └── ItemControllerTest.java
~~~

### 12.2 settings.gradle

~~~groovy
rootProject.name = 'request-input-demo'
~~~

### 12.3 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

spring-boot-starter-web thông thường mang Spring MVC, Jackson và embedded Tomcat. spring-boot-starter-test cung cấp JUnit 5, Spring Test và MockMvc. Nếu project có Gradle wrapper, có thể dùng ./gradlew trên Linux/macOS hoặc gradlew.bat trên Windows.

### 12.4 RequestDataApplication.java

~~~java
package com.example.requestdata;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestDataApplication {

    public static void main(String[] args) {
        SpringApplication.run(RequestDataApplication.class, args);
    }
}
~~~

### 12.5 ItemController.java

~~~java
package com.example.requestdata;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    @GetMapping("/{itemId}")
    public ItemView read(
            @PathVariable("itemId") long itemId,
            @RequestParam(name = "page", defaultValue = "1") int page,
            @RequestParam(name = "tag", required = false)
                    List<String> tags,
            @RequestHeader(
                    name = "X-Request-Id", required = false)
                    String requestId,
            @CookieValue(name = "theme", defaultValue = "light")
                    String theme) {

        if (page < 1) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "page must be >= 1");
        }

        if (!theme.equals("light") && !theme.equals("dark")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "unsupported theme");
        }

        List<String> safeTags =
                tags == null ? List.of() : List.copyOf(tags);

        return new ItemView(
                itemId, page, safeTags, requestId, theme);
    }
}

record ItemView(
        long itemId,
        int page,
        List<String> tags,
        String requestId,
        String theme) {
}
~~~

Đây là file Java hợp lệ với một public class ItemController và package-private record ItemView cùng package. Spring Boot component scan nhận controller. Jackson trong Boot 3.3 hỗ trợ Java records và serialize dữ liệu các component tương ứng thành JSON.

Mỗi annotation có một trách nhiệm:

| Tham số Java | Nguồn HTTP | Nếu thiếu | Nếu sai |
| --- | --- | --- | --- |
| itemId: long | Path /api/items/{itemId} | Route có thể không match | Conversion thường trả 400 |
| page: int | Query page | 1 | Không parse được hoặc <= 0 bị từ chối |
| tags: List<String> | Query tag lặp | [] sau chuẩn hóa | Quy tắc list/encoding cần test theo client |
| requestId: String | Header X-Request-Id | null | Ví dụ chưa áp dụng whitelist request ID |
| theme: String | Cookie theme | "light" | Value khác light/dark trả 400 |

**Phạm vi bảo mật của ví dụ:** theme chỉ là một lựa chọn giao diện, không phải session cookie. X-Request-Id dùng để minh họa binding; production nên giới hạn độ dài/format trước khi dùng để log. Dự án chưa có authentication nên không được dùng làm hệ thống nhiều tenant thực.

### 12.6 Chạy và gọi endpoint

Trong thư mục project:

~~~bash
gradle clean test bootRun
~~~

Ở terminal khác:

~~~bash
curl -i --get \
  --data-urlencode 'page=2' \
  --data-urlencode 'tag=spring' \
  --data-urlencode 'tag=java' \
  -H 'X-Request-Id: req-42' \
  -b 'theme=dark' \
  'http://127.0.0.1:8080/api/items/42'
~~~

Kỳ vọng HTTP 200, body JSON tương đương:

~~~json
{
  "itemId": 42,
  "page": 2,
  "tags": ["spring", "java"],
  "requestId": "req-42",
  "theme": "dark"
}
~~~

Thứ tự các JSON fields và header hạ tầng như Date/Connection phụ thuộc encoder/server; kiểm thử theo field thay vì so sánh toàn bộ bytes.

### 12.7 Thiếu query/header/cookie

~~~bash
curl -i 'http://127.0.0.1:8080/api/items/42'
~~~

Kỳ vọng HTTP 200 và các field logic:

~~~json
{
  "itemId": 42,
  "page": 1,
  "tags": [],
  "requestId": null,
  "theme": "light"
}
~~~

Đây là body dự kiến từ code và Jackson mặc định, không phải kết quả đã được thực thi trong tài liệu. Nếu ứng dụng cấu hình null inclusion khác, field requestId có thể được bỏ thay vì xuất hiện với null.

### 12.8 Sai kiểu path hoặc query

~~~bash
curl -i 'http://127.0.0.1:8080/api/items/abc'
curl -i 'http://127.0.0.1:8080/api/items/42?page=abc'
curl -i 'http://127.0.0.1:8080/api/items/42?page=0'
~~~

Trong ứng dụng ví dụ, các tình huống thường trả 400: hai trường hợp đầu ở tầng conversion, trường hợp page=0 qua guard nghiệp vụ. Body lỗi mặc định có thể thay đổi theo Spring Boot properties.

### 12.9 Cookie không thuộc whitelist

~~~bash
curl -i -b 'theme=script' \
  'http://127.0.0.1:8080/api/items/42'
~~~

Dự kiến HTTP 400 với reason unsupported theme. Ví dụ cho thấy ngay cả cookie “vô hại” cũng cần quy tắc chấp nhận nếu được dùng trong output hoặc logic.

## 13. Kiểm thử MockMvc: xác nhận binding và lỗi trước controller

Tạo file ItemControllerTest.java:

~~~java
package com.example.requestdata;

import jakarta.servlet.http.Cookie;

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
class ItemControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void readsAllFourSources() throws Exception {
        mockMvc.perform(get("/api/items/{itemId}", 42)
                .param("page", "2")
                .param("tag", "spring", "java")
                .header("X-Request-Id", "req-42")
                .cookie(new Cookie("theme", "dark")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.itemId").value(42))
            .andExpect(jsonPath("$.page").value(2))
            .andExpect(jsonPath("$.tags[0]").value("spring"))
            .andExpect(jsonPath("$.tags[1]").value("java"))
            .andExpect(jsonPath("$.requestId").value("req-42"))
            .andExpect(jsonPath("$.theme").value("dark"));
    }

    @Test
    void usesDefaultsForMissingOptionalValues() throws Exception {
        mockMvc.perform(get("/api/items/{itemId}", 42))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page").value(1))
            .andExpect(jsonPath("$.tags").isEmpty())
            .andExpect(jsonPath("$.theme").value("light"));
    }

    @Test
    void rejectsNonNumericPathVariable() throws Exception {
        mockMvc.perform(get("/api/items/abc"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsNonNumericQueryParameter() throws Exception {
        mockMvc.perform(get("/api/items/42").param("page", "abc"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsNonPositivePage() throws Exception {
        mockMvc.perform(get("/api/items/42").param("page", "0"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidCookieValue() throws Exception {
        mockMvc.perform(get("/api/items/42")
                .cookie(new Cookie("theme", "untrusted")))
            .andExpect(status().isBadRequest());
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**MockMvc** dùng mock Servlet request/response để thực thi Spring MVC request pipeline, bao gồm argument resolvers, conversion và controller, nhưng trong test này không mở một socket HTTP thật trên cổng 8080. Vì vậy test có thể chạy trong CI không phụ thuộc port cục bộ. Nếu muốn test integration qua TCP thực sự, dùng @SpringBootTest(webEnvironment = RANDOM_PORT) và HTTP client tương ứng.

Các assertions cho dữ liệu JSON sử dụng JSONPath nên không phụ thuộc thứ tự key JSON. Khi debug một test fail, xác định nó fail ở mapping, conversion, controller validation hay serialization thay vì ngay lập tức kết luận Spring “không đọc được query”.

## 14. Cách đọc tất cả values bằng Servlet API khi thật sự cần

Trong Spring MVC, có thể inject HttpServletRequest vào controller để truy cập raw Servlet information:

~~~java
@GetMapping("/inspect")
public String inspect(HttpServletRequest request) {
    String rawQuery = request.getQueryString();
    String page = request.getParameter("page");
    String header = request.getHeader("X-Request-Id");
    Cookie[] cookies = request.getCookies();
    // ...
}
~~~

Đây là method minh họa, cần imports jakarta.servlet.http.HttpServletRequest, jakarta.servlet.http.Cookie và đặt trong class controller. **Không phải lúc nào getQueryString trả dữ liệu đã decode**, trong khi getParameter sử dụng parsing của container. Servlet API cho phép đọc dữ liệu thô, nhưng làm controller phụ thuộc trực tiếp Servlet stack.

Ưu tiên @PathVariable/@RequestParam/@RequestHeader/@CookieValue khi chỉ cần vài giá trị rõ tên. Dùng HttpServletRequest khi framework abstraction không đủ, ví dụ request metadata hạ tầng, debugging có kiểm soát hoặc custom middleware.

### Đừng dùng HttpServletRequest trong WebFlux reactive server

Một Spring WebFlux controller thường dùng ServerWebExchange, ServerHttpRequest hoặc annotation binding. Kéo Servlet-specific API vào reactive controller không phải hướng port code chuẩn.

## 15. Spring WebFlux: bốn annotation vẫn có thể dùng

Trong một ứng dụng **chỉ có spring-boot-starter-webflux**, annotated controller có thể viết tương tự:

~~~java
@RestController
class ReactiveItemController {

    @GetMapping("/reactive/items/{itemId}")
    Mono<String> read(
            @PathVariable("itemId") long itemId,
            @RequestParam(name = "page", defaultValue = "1")
                    int page,
            @RequestHeader(name = "X-Request-Id", defaultValue = "none")
                    String requestId,
            @CookieValue(name = "theme", defaultValue = "light")
                    String theme) {

        return Mono.just(itemId + ":" + page + ":"
                + requestId + ":" + theme);
    }
}
~~~

Đây là **class minh họa**, cần imports org.springframework.web.bind.annotation.*, reactor.core.publisher.Mono, và không phải class nằm trong project MVC ở mục 12. Spring WebFlux RequestMappingHandlerAdapter giải quyết các annotated arguments theo reactive stack.

Ví dụ HTTP GET:

~~~text
/reactive/items/42?page=3
X-Request-Id: req-x
Cookie: theme=dark
~~~

Body dự kiến:

~~~text
42:3:req-x:dark
~~~

Tuy nhiên, nếu bạn thêm starter-webflux vào project MVC ở mục 12 rồi cũng khai báo controller mới, Spring Boot vẫn **mặc định ưu tiên Spring MVC** khi hai starter đều có. Nếu muốn thử reactive stack thuần, tạo project riêng hoặc chọn spring.main.web-application-type=reactive một cách có chủ đích.

### Những điều không thay đổi

- Đừng tin giá trị header/cookie là đã xác thực.
- Validate path/query giống nguyên tắc MVC.
- Encoding/decoding và HTTP semantics vẫn cần đúng.
- Không nên block Netty event loop để lấy dữ liệu khác nếu controller đã dùng reactive pipeline.

### Những điều khác

- WebFlux xử lý HTTP bằng ServerWebExchange/DispatcherHandler, thay vì HttpServletRequest/DispatcherServlet.
- Reactive request body thông thường dùng HttpMessageReader/codecs.
- @RequestParam WebFlux dựa vào query parameters; form body có API riêng.
- Với Java WebFlux functional endpoints, không dùng các annotation controller giống hệt; đọc từ ServerRequest.

## 16. WebFlux functional endpoints: path, query, header, cookie

Với functional routing, handler nhận org.springframework.web.reactive.function.server.ServerRequest. Các phương thức cần dùng:

~~~java
request.pathVariable("itemId");
request.queryParam("page");
request.headers().firstHeader("X-Request-Id");
request.cookies().getFirst("theme");
~~~

Các kiểu thường gặp:

| Nguồn | API | Kiểu |
| --- | --- | --- |
| Path variable | ServerRequest.pathVariable(name) | String |
| Query parameter | ServerRequest.queryParam(name) | Optional<String> |
| Query lặp | ServerRequest.queryParams().get(name) | List<String> hoặc null |
| Header | ServerRequest.headers().firstHeader(name) | String hoặc null |
| Cookie | ServerRequest.cookies().getFirst(name) | HttpCookie hoặc null |

Ví dụ class có thể đưa vào project Spring Boot WebFlux với starter-webflux:

~~~java
package com.example.functional;

import java.util.Map;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpCookie;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class RequestRoutes {

    @Bean
    public RouterFunction<ServerResponse> routes() {
        return RouterFunctions.route(
                RequestPredicates.GET("/functional/items/{itemId}"),
                request -> {
                    String itemId = request.pathVariable("itemId");
                    String page =
                            request.queryParam("page").orElse("1");

                    String header =
                            request.headers().firstHeader("X-Request-Id");
                    String requestId =
                            header == null ? "none" : header;

                    HttpCookie cookie =
                            request.cookies().getFirst("theme");
                    String theme =
                            cookie == null ? "light" : cookie.getValue();

                    return ServerResponse.ok().bodyValue(Map.of(
                            "itemId", itemId,
                            "page", page,
                            "requestId", requestId,
                            "theme", theme));
                });
    }
}
~~~

Đây là một **class Java hoàn chỉnh** cho ứng dụng WebFlux có component scan bao phủ com.example.functional, nhưng không tự cung cấp main method hoặc Gradle files. Import java.util.Optional trong snippet không được dùng và có thể xóa mà không ảnh hưởng hoạt động; Java compiler chấp nhận unused imports nếu class đó tồn tại. Kết quả JSON ở route functional chứa itemId và page dạng String, khác ví dụ MVC chuyển sang long/int. **Functional handlers không tự có @PathVariable/@RequestParam argument conversion**, vì vậy bạn phải tự parse/validate nếu muốn typed data.

Để tránh tạo cảm giác chức năng bảo mật đã có sẵn: đoạn functional route này chưa kiểm tra page số dương, chưa whitelist theme và chưa xác thực requestId. Với ứng dụng thật, hãy thêm validation và xử lý lỗi tương ứng.

## 17. Cookie trong ứng dụng có Spring Security

Với session hoặc login, đừng viết controller đọc @CookieValue("JSESSIONID") rồi coi đó là bằng chứng user đã đăng nhập. Spring Security hoặc framework session tương ứng sẽ dùng cơ chế xác thực, session fixation protection, CSRF protection và lifecycle quản lý.

Lưu ý:

- **HttpOnly** giúp JavaScript phía browser không đọc cookie qua document.cookie, nhưng không ngăn browser tự động gửi cookie trên request.
- **Secure** giới hạn browser gửi cookie qua kết nối bảo mật theo quy tắc tương ứng; dùng HTTPS.
- **SameSite** ảnh hưởng gửi cookie cross-site, nhưng không thay thế toàn bộ CSRF protection.
- **Cookie signing/encryption** hoặc server-side session lookup cần được thiết kế đúng nếu cookie chứa giá trị có ảnh hưởng authorization.
- CORS và cookie credentials là hai cơ chế riêng; cấu hình Access-Control-Allow-Credentials không khiến mọi cookie tự động an toàn.
- Header Authorization và cookie session không nên được đưa thẳng vào error body hay log.

Phân biệt **đọc cookie** với **tin cậy cookie** là một nguyên tắc an toàn quan trọng.

## 18. Headers từ reverse proxy và nhận diện client

Ứng dụng đứng sau Nginx, ingress, API gateway hoặc load balancer có thể nhận các header như Forwarded, X-Forwarded-For, X-Forwarded-Proto và X-Forwarded-Host.

Không viết:

~~~java
String clientIp = request.getHeader("X-Forwarded-For");
// Sau đó coi clientIp chắc chắn là IP thực của user.
~~~

Mẫu trên là ví dụ **không đủ an toàn**. Client có thể tự đặt header giả nếu proxy không lọc và ghi đè. Với Spring Boot, dùng server.forward-headers-strategy phù hợp topology và chỉ tin header từ reverse proxy đáng tin; cấu hình proxy để loại bỏ header giả mạo từ bên ngoài.

Nếu ứng dụng cần địa chỉ IP cho rate limiting, auditing hoặc fraud controls, hãy xác định rõ trusted proxy chain và policy log. Header name đúng không đồng nghĩa giá trị đáng tin.

## 19. Thiết kế API contract cho từng nguồn

### Path variable: xác định tài nguyên

Path variable thích hợp cho resource identity, ví dụ /orders/{orderId}. Tài nguyên có thể cần validation/authorization; ID hợp lệ không đồng nghĩa user có quyền xem resource.

### Query parameter: tùy chọn truy vấn

Query nên mang filter, sort, page, limit, cursor, field selection hoặc search condition. Đặt giới hạn page size, số tag lặp và độ dài chuỗi tìm kiếm, tránh một client gửi hàng nghìn tham số gây lãng phí CPU/memory.

### Header: metadata request

Header hợp với correlation ID, content negotiation, conditional requests và metadata giao thức. Tránh đưa business contract quan trọng vào một header tự phát không được document, vì proxy/client có thể khó debug. Với authentication, dùng cơ chế tiêu chuẩn phù hợp.

### Cookie: trạng thái do client gửi lại theo scope

Cookie phù hợp với session hoặc một số client preferences có scope và policy. Đừng nhét lượng dữ liệu lớn vào cookie: browser/server có giới hạn kích thước header, và cookie thường được gửi lại ở nhiều request, tăng bandwidth.

### Body: dữ liệu nghiệp vụ lớn/được cấu trúc

POST/PUT/PATCH JSON thường dùng @RequestBody DTO và validation. Không cố truyền một JSON document nhiều KB dưới dạng một query parameter hoặc Cookie để “tránh dùng body”.

## 20. Các lỗi dễ nhầm khi debug

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| @PathVariable id luôn null hoặc không match | Tên {id} và annotation không khớp, path template sai |
| /items/abc trả 400 dù route tồn tại | Type conversion sang long thất bại |
| ?page=0 vẫn vào method | Conversion thành công; thiếu validation nghiệp vụ |
| @RequestParam không thấy JSON field | JSON body không phải query parameter |
| Query tag lặp chỉ lấy một giá trị | Dùng String/Map một giá trị thay vì List/MultiValueMap |
| required=false String trả null | Đúng contract; cần guard/default |
| defaultValue không cứu page=abc | Giá trị sai kiểu khác giá trị thiếu |
| Header không có ở server dù client gửi | Proxy/gateway có thể không forward hoặc đổi header |
| X-Forwarded-For chứa IP lạ | Có thể bị spoof hoặc đi qua nhiều proxy |
| CookieValue không thấy theme | Cookie không được gửi do domain/path/SameSite/Secure/browser policy |
| Thấy session cookie nhưng không authenticated | Chưa được hạ tầng xác thực/session xác nhận |
| Bật @CookieValue("theme") làm API phụ thuộc browser | Non-browser clients có thể không gửi cookie; cần default/contract |
| Thêm starter-webflux nhưng controller vẫn Servlet MVC | Boot mặc định ưu tiên MVC khi cả hai starter có trên classpath |
| WebFlux functional request không nhận @RequestParam | Functional handler dùng ServerRequest API, không dùng argument binding annotated |
| Response JSON thiếu requestId | Jackson null inclusion policy có thể đã loại field null |
| HTTP 404 khi gọi đường dẫn mong đợi | HandlerMapping/route hoặc context path sai, không hẳn lỗi argument binding |

Không cần bật toàn bộ HTTP TRACE logs để điều tra từng lỗi đơn giản. Bắt đầu từ route đã match chưa, giá trị request thực tế, argument conversion/validation và status trả về.

## 21. Quy trình debug có hệ thống

1. Gửi một request có path/query/header/cookie rõ ràng bằng cURL/Postman/HTTP client.
2. Xác nhận URI được gọi đúng, có encoding phù hợp và proxy rewrite không làm sai path.
3. Kiểm tra handler mapping có khớp endpoint không.
4. Kiểm tra annotation name và Java parameter type.
5. Phân biệt missing value với empty value, sai kiểu hoặc query key lặp.
6. Xem exception gốc nếu controller không được gọi: required parameter, type mismatch, validation?
7. Khi controller đã chạy, kiểm tra validation và authorization trước khi gọi service.
8. Xác định response formatter/serializer JSON thực sự được dùng.
9. Nếu cookie không có, kiểm tra Set-Cookie, domain/path, browser credentials, SameSite và HTTPS.
10. Nếu header do proxy cung cấp, kiểm tra proxy trust boundary và bản cấu hình forward.
11. Viết test bao quát ít nhất một happy path, một default/optional path và vài invalid inputs.
12. Ghi lại API contract trong OpenAPI hoặc tài liệu endpoint để client biết nên gửi từng giá trị ở đâu.

Gợi ý logger Spring MVC trong local/test:

~~~properties
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
~~~

Với WebFlux:

~~~properties
logging.level.org.springframework.web.reactive.DispatcherHandler=DEBUG
logging.level.org.springframework.web.reactive.result.method.annotation=TRACE
~~~

Không log token, Authorization header, toàn bộ Cookie hoặc dữ liệu cá nhân trong production. Bật TRACE có kiểm soát, tắt khi đã chẩn đoán.

## 22. Các câu hỏi thường gặp

**1. Có thể dùng @PathVariable và @RequestParam trong cùng method không?**

Có. Chúng đọc hai nguồn khác nhau, ví dụ /items/{id}?page=2. Chỉ cần route/annotation name phù hợp và type conversion thành công.

**2. Header name có phân biệt chữ hoa không?**

Theo HTTP semantics, header field names không phân biệt chữ hoa/thường. Tuy nhiên, không nên tự so sánh một raw header dump bằng String.equals phân biệt hoa/thường để kết luận server không nhận header.

**3. Có phải Cookie chỉ tồn tại khi client dùng browser?**

Không. HTTP client có thể gửi Cookie header thủ công. Browser chỉ giúp quản lý chính sách lưu/gửi cookie; server vẫn phải coi dữ liệu cookie nhận được là client-controlled.

**4. Nếu @CookieValue(required=false) và cookie vắng mặt?**

Khi dùng String, framework có thể cung cấp null; với defaultValue có thể nhận giá trị mặc định. Chọn contract rõ ràng và test thực tế.

**5. Nếu một query parameter có hai giá trị thì sao?**

Chọn List<String> hoặc MultiValueMap nếu API cho phép lặp. Đừng tự lấy một giá trị rồi bỏ qua phần còn lại mà không document.

**6. Làm sao nhận LocalDate từ query?**

Dùng @DateTimeFormat với LocalDate và format ISO/phù hợp. Dữ liệu JSON date trong body là một câu chuyện codec/Jackson khác.

**7. Một path variable dùng làm ID có cần validate không?**

Có. Chuyển thành long hoặc UUID chỉ xác nhận cú pháp, không xác nhận ID tồn tại hay user có quyền truy cập.

**8. @RequestHeader("Authorization") có thay Spring Security không?**

Không. Nó chỉ đọc chuỗi header. Xác thực token, signature, expiry, scopes và authorization là trách nhiệm của security stack/architecture.

**9. @RequestParam có đọc các field của JSON POST không?**

Không phải cơ chế chuẩn cho JSON body. Dùng @RequestBody DTO. Query parameters có thể đi kèm POST nhưng không nên trộn nguồn không rõ ràng.

**10. Nếu client truyền X-Request-Id không hợp lệ thì có nên tin?**

Không. Hãy validate độ dài/ký tự, chuẩn hóa hoặc tạo ID mới theo tracing policy. Đừng dùng giá trị raw làm tên file, log format hay database key nếu chưa kiểm soát.

**11. Nên đọc cookies từ request header thô hay @CookieValue?**

Với một cookie rõ tên trong annotated controller, @CookieValue đơn giản hơn. Đọc raw Cookie header chỉ khi thực sự cần xử lý giao thức ở tầng hạ tầng và hiểu trường hợp duplicate/scope.

**12. Có nên viết custom argument resolver cho mọi giá trị?**

Không. Các annotation chuẩn đã bao phủ phần lớn use case. Custom resolver phù hợp khi cần tạo một domain object có logic tái sử dụng từ nhiều nguồn request, sau khi cân nhắc trust boundary.

## 23. Checklist cuối cùng

- [ ] Path template đã khai báo đúng biến và annotation name.
- [ ] Query parameters có required/defaultValue/Optional đúng API contract.
- [ ] Nhiều query values được xử lý bằng List/MultiValueMap khi cần.
- [ ] Kiểu Java và converter/formatter phù hợp dữ liệu đầu vào.
- [ ] Header name đúng, chỉ đọc những header cần thiết.
- [ ] Giá trị header/cookie từ client được coi là chưa đáng tin.
- [ ] Cookie sử dụng đúng name/scope, default hoặc required rõ ràng.
- [ ] Input được validate về định dạng, độ dài và quyền truy cập.
- [ ] Không dùng request metadata chưa xác thực để phân quyền.
- [ ] Tránh log Authorization/Cookie/session token.
- [ ] HTTP status 400/404/405 được phân biệt đúng nguyên nhân.
- [ ] Có test thành công, thiếu giá trị, sai kiểu và dữ liệu không hợp lệ.
- [ ] Khi dùng WebFlux, không nhập nhằng với Servlet-specific API.
- [ ] Khi đọc dữ liệu đã encode, kiểm chứng bằng HTTP client thật.

## 24. Tóm tắt

Trong Spring Boot, **@PathVariable** lấy dữ liệu từ đường dẫn đã match, **@RequestParam** lấy tham số truy vấn (và các nguồn request parameter phù hợp theo stack), **@RequestHeader** đọc metadata HTTP, còn **@CookieValue** lấy request cookie theo tên. Spring MVC/annotated WebFlux sẽ dùng argument resolvers và type conversion để đưa các giá trị này vào method parameter. Đây là các cơ chế **binding**, không phải bằng chứng rằng input đã hợp lệ, an toàn hoặc user đã được xác thực.

Thiết kế API tốt bắt đầu bằng việc chọn đúng nguồn, đặt required/default rõ ràng, dùng kiểu dữ liệu thích hợp, test missing/invalid/multi-value, encode URI đúng chuẩn và kiểm tra trust boundary của header/cookie. Với nhu cầu cơ bản, các annotation chuẩn rõ ràng và dễ bảo trì hơn custom request parsing.

## 25. Tài liệu tham khảo

- Spring Framework — MVC @PathVariable: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/uri-templates.html
- Spring Framework — MVC @RequestParam: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html
- Spring Framework — MVC @RequestHeader: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestheader.html
- Spring Framework — MVC @CookieValue: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/cookievalue.html
- Spring Framework — WebFlux annotated controller method arguments: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html
- Spring Framework — WebFlux functional endpoints: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Boot 3.3 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- MDN Web Docs — HTTP cookies: https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies
