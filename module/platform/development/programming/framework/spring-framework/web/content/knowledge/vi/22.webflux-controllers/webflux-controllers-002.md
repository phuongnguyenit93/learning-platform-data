# Đọc tham số, header, cookie, Principal và dữ liệu trong ServerWebExchange

## 1. Mục tiêu và phạm vi

Một HTTP request gửi tới Spring WebFlux có nhiều nguồn dữ liệu: **query parameters** trong URI, **path variables**, **headers**, **cookies**, **request body** (JSON, form hoặc multipart), **principal** đã xác thực và **exchange attributes** do server tạo. Chúng không đồng nghĩa với nhau, có vòng đời và mức độ tin cậy khác nhau. Controller nên dùng argument resolvers của WebFlux khi chỉ cần một giá trị; khi cần cái nhìn tổng thể thì dùng `ServerWebExchange`, đồng thời giữ nguyên mô hình bất đồng bộ.

Bài học thuộc **Controller WebFlux** của Spring Framework, dùng **Java 17+, Spring Framework 6.x, Spring Boot 3.x** (reactive stack, thông thường Reactor Netty). Kết thúc bài, bạn có thể:

- Dùng `@RequestParam` với `required`/`defaultValue`/`Optional`, chuyển đổi kiểu và multi-value query.
- Phân biệt *thiếu parameter*, *parameter rỗng*, *giá trị không chuyển được kiểu*, *parameter xuất hiện nhiều lần*.
- Đọc `@RequestHeader`, `HttpHeaders`, `@CookieValue`; tránh tin `X-User` hay token được gửi từ client như identity.
- Lấy `java.security.Principal` hoặc `Mono<Principal>`, xử lý anonymous một cách rõ ràng và hiểu mối liên hệ với Spring Security.
- Sử dụng `ServerWebExchange.getRequest()`, `getResponse()`, `getAttributes()`, `getPrincipal()`, `getSession()`, `getFormData()`, `getMultipartData()`, `getLocaleContext()` và những giới hạn liên quan.
- Phân biệt form-urlencoded, multipart, JSON và query string trong WebFlux, không cố coi tất cả thành `@RequestParam`.
- Thực hành một ứng dụng Spring Boot WebFlux có `WebFilter` tạo correlation ID, controller, HTTP examples và `WebTestClient`.
- Tránh đọc body hai lần, chặn Netty event loop bằng `block()`, ghi log bí mật hoặc bỏ qua validation/authorization.

**Điểm phải nhớ:** Trên **Spring WebFlux**, `@RequestParam` **chỉ** bind **query parameters**. Ngược lại, khái niệm “request parameter” của Servlet/Spring MVC còn có thể gộp form-data và một số multipart values. Với WebFlux, form và multipart có API riêng qua `ServerWebExchange` hoặc data binding phù hợp. Đây là khác biệt được Spring Framework ghi rõ trong tài liệu chính thức.

## 2. Bản đồ dữ liệu trong một request

Ví dụ:

```http
POST /api/input/notes/42?tag=java&tag=webflux&page=2 HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json
X-Client: mobile-app
Cookie: theme=dark; session=opaque

{"message":"Xin chào"}
```

Bóc tách:

| Vị trí | Ví dụ | Cách đọc WebFlux |
| --- | --- | --- |
| Path variable | `42` | `@PathVariable("id")` |
| Query param | `tag=java&tag=webflux` | `@RequestParam` hoặc `exchange.getRequest().getQueryParams()` |
| Header | `X-Client: mobile-app` | `@RequestHeader` hoặc `getRequest().getHeaders()` |
| Cookie | `theme=dark` | `@CookieValue` hoặc `getRequest().getCookies()` |
| JSON body | `{"message":"Xin chào"}` | `@RequestBody Mono<NoteInput>` |
| Principal | Không phải thông tin client tự khai | `Principal`, `Mono<Principal>` hoặc `exchange.getPrincipal()` |
| Exchange attribute | `app.traceId` do filter ghi | `@RequestAttribute` hoặc `exchange.getAttribute(...)` |
| Web session | Server-managed session state | `exchange.getSession()` hoặc `WebSession` |
| URL-encoded form body | `name=An&topic=java` | `exchange.getFormData()` |
| Multipart | Field/file parts | `exchange.getMultipartData()`, `@RequestPart` |

*Request headers/cookies/query/body nhìn chung là dữ liệu từ client và cần kiểm tra.* Ngay cả khi đã URL decode hoặc tự động convert thành kiểu Java, chúng không tự được “làm sạch” hoặc chứng thực. Principal cũng chỉ đáng tin khi authentication/security chain thực sự đã được cấu hình đúng.

## 3. Nên dùng annotation hay ServerWebExchange?

Thông thường chọn phương án nhỏ nhất:

```java
@GetMapping("/books")
public Mono<Book> one(
        @RequestParam("id") long id,
        @RequestHeader("Accept-Language") String language) {
    return repository.find(id, language);
}
```

Đây là **snippet** cần bean `repository` và record `Book`; không phải file Java hoàn chỉnh. Controller tự nhận đúng hai giá trị, không phải thủ công đọc request raw.

Sử dụng `ServerWebExchange` khi cần nhiều thành phần cùng lúc hoặc chức năng hạ tầng, ví dụ xem repeated query values, lấy request attributes từ `WebFilter`, form/multipart map, session, headers hay principal.

```java
@GetMapping("/inspect")
public Mono<String> inspect(ServerWebExchange exchange) {
    String method = exchange.getRequest().getMethod().name();
    String client = exchange.getRequest()
            .getHeaders().getFirst("X-Client");
    return Mono.just(method + ":" + client);
}
```

Đây cũng là snippet, cần imports. **Đừng dùng ServerWebExchange chỉ vì ngại học annotation binding.** Khi lấy toàn bộ raw request, bạn phải tự quyết định trường nào được phép đọc/echo/log, cách convert, validation và thiếu giá trị. Với argument binding, Spring xử lý nhiều bước này rõ ràng và nhất quán hơn.

## 4. @RequestParam: query parameters trong WebFlux

WebFlux bind tham số của query string:

```text
GET /api/search?q=spring&page=3
GET /api/search?q=a%26b
GET /api/search?tag=java&tag=webflux
```

Ví dụ:

```java
@GetMapping("/search")
public Mono<SearchView> search(
        @RequestParam("q") String q,
        @RequestParam(name = "page", defaultValue = "1") int page) {
    return Mono.just(new SearchView(q, page));
}
```

Với định nghĩa `record SearchView(String q,int page) {}`, URL `?q=spring&page=3` tạo giá trị tương ứng. Query là dữ liệu URI, không liên quan việc request là GET hay POST: một POST cũng có thể chứa query params.

### Required và defaultValue

- `@RequestParam("q") String q`: mặc định **required=true**; thiếu `q` gây lỗi binding request (thường status 400).
- `@RequestParam(name="q",required=false) String q`: nếu thiếu, giá trị thường là null; logic phải kiểm.
- `@RequestParam(name="q",defaultValue="all") String q`: dùng default khi thiếu hoặc khi giá trị trống theo annotation contract; `defaultValue` ngầm khiến `required=false`.
- `@RequestParam Optional<String> q`: Spring hỗ trợ kiểu `Optional`, phân biệt có/không có theo resolver; không dùng `Optional<Optional<T>>`.
- Với `int page` không có default và missing, dùng required behavior rõ ràng hoặc `Integer`/`Optional<Integer>` để thể hiện optional.

### Thiếu so với rỗng

```text
/search               -> q không xuất hiện
/search?q=            -> q có xuất hiện, giá trị chuỗi rỗng
/search?q=hello       -> q="hello"
/search?q=%20         -> q=" " sau percent-decoding
```

Nếu nghiệp vụ không cho rỗng, **cần validation riêng** như kiểm `isBlank()`/Bean Validation, không nghĩ `required=true` luôn cấm `q=`. Đối với `defaultValue`, giá trị rỗng có thể được thay bằng default nên không nên sử dụng nó để chứng minh client có gửi giá trị thật.

### Chuyển đổi kiểu

`@RequestParam int page` chuyển String → int theo conversion service; `?page=abc` thường dẫn tới HTTP 400 (type mismatch), không thành 500 nếu xử lý lỗi mặc định đúng. `?page=-1` vẫn là int hợp lệ về mặt conversion nhưng có thể **không hợp lệ nghiệp vụ**. Phải đặt quy tắc `page>=1`/`page<=max` riêng.

Với enum, UUID, LocalDate và số thập phân, ConversionService có thể áp dụng converter phù hợp; đảm bảo format và thông báo lỗi có tính nhất quán thay vì nhận chuỗi rồi tự parse vội vàng ở controller.

## 5. Query nhiều giá trị và MultiValueMap

Query string có thể lặp lại cùng tên:

```http
GET /api/search?tag=java&tag=webflux&tag=reactor
```

`exchange.getRequest().getQueryParams()` trả `MultiValueMap<String,String>`, giữ **nhiều giá trị trên cùng key**:

```java
MultiValueMap<String, String> query =
        exchange.getRequest().getQueryParams();

List<String> tags = query.getOrDefault("tag", List.of());
String first = query.getFirst("tag");
```

Đây là snippet trong method có `ServerWebExchange exchange` và imports `java.util.List`, `org.springframework.util.MultiValueMap`. Theo request ví dụ, `tags` chứa `["java","webflux","reactor"]` và `first` là `"java"`.

Với `@RequestParam MultiValueMap<String,String> params`, Spring cũng có thể bind tất cả query params. Nếu chỉ dùng `Map<String,String>`, bạn có thể mất các giá trị lặp; nếu API quy định một giá trị duy nhất, **phải định nghĩa policy đối với duplicates**, đặc biệt khi gateway và backend có thể diễn giải query khác nhau.

### Không tự cắt raw query theo dấu &/=

Giá trị `q="a&b=c"` trên URI cần encode cho đúng component:

```text
?q=a%26b%3Dc  -> một q: "a&b=c"
?q=a&b=c      -> hai parameters q="a", b="c"
```

Dùng URI builder ở client và Spring argument binding ở server. Không giải mã percent sequences lần hai trong controller (ví dụ `%252F` phải còn literal `%2F` sau một lần decode). Query parsing và auth policy phải hiểu các ký tự phân cách theo cùng một cách qua reverse proxy/gateway.

## 6. @RequestHeader: đọc metadata HTTP

Header là tên không phân biệt hoa/thường theo HTTP semantics. Các dạng:

```java
@GetMapping("/headers")
public Mono<String> headers(
        @RequestHeader("X-Client") String client,
        @RequestHeader(name = "Accept-Language",
                       required = false) String language) {
    return Mono.just(client + ":" + language);
}
```

Snippet này sẽ yêu cầu `X-Client` nếu chưa đặt `required=false` hoặc `defaultValue`. Nếu header không có và required=true, Spring thường trả 400. `Accept-Language` có thể có nhiều giá trị/ranges, không nên tự dựa vào một chuỗi tự cắt để chọn locale khi framework đã có `LocaleContextResolver`.

### Một header, nhiều giá trị và typed header

```java
@RequestHeader(name = "X-Retry", defaultValue = "0") int retry;
@RequestHeader(name = "X-Flag", required = false)
        Optional<String> flag;
```

Các khai báo trên là **snippet tham số method**, không phải câu lệnh Java độc lập. Spring có thể convert String → type đích; `X-Retry: not-number` tạo lỗi conversion. Một số headers cho phép nhiều giá trị, dùng `List<String>`/`String[]` hoặc `@RequestHeader MultiValueMap<String,String>`/`HttpHeaders` để đọc đầy đủ.

```java
@GetMapping("/selected-header")
public Mono<String> chosen(@RequestHeader HttpHeaders headers) {
    return Mono.just(headers.getFirst("X-Client") == null
            ? "unknown" : headers.getFirst("X-Client"));
}
```

Đây là snippet trong controller, cần `org.springframework.http.HttpHeaders`. **Đừng đưa toàn bộ HttpHeaders vào response/log**: Authorization, Cookie và các token có thể lộ.

### Header không phải chứng cứ danh tính

`X-User: admin` hoặc `X-Role: root` do client gửi **không tự chứng thực** người dùng. Nếu upstream proxy xác thực rồi truyền identity bằng header, cần trust boundary: gateway kiểm xác thực, loại bỏ header do client tự khai, kết nối nội bộ được bảo vệ và downstream validate metadata. Thông thường **Spring Security reactive** nên tạo Authentication/Principal đáng tin trong security chain.

`Host`, `Forwarded`, `X-Forwarded-*` cũng có thể bị giả mạo nếu proxy trust không cấu hình đúng; không tự sinh link tuyệt đối hoặc quyết định tenant/redirect từ headers chưa xác thực.

## 7. @CookieValue: lấy cookie riêng lẻ

Cookie đi trong request header `Cookie` nhưng có resolver riêng:

```java
@GetMapping("/theme")
public Mono<String> theme(
        @CookieValue(name = "theme",
                     defaultValue = "light") String theme) {
    return Mono.just(theme);
}
```

- `@CookieValue("theme")` mặc định required; không gửi có thể gây HTTP 400.
- `required=false`, `Optional<String>` hoặc `defaultValue` thích hợp khi cookie tùy chọn.
- `@CookieValue` chuyển giá trị theo converter nếu kiểu đích không phải String.
- `exchange.getRequest().getCookies()` trả `MultiValueMap<String,HttpCookie>` khi cần xem nhiều cookies/metadata.
- Cookie tên trùng nhau có thể đến từ các path/domain khác nhau; không tự chọn một cách thiếu chủ đích nếu đó là quyết định bảo mật.

Ví dụ:

```java
MultiValueMap<String, HttpCookie> cookies =
        exchange.getRequest().getCookies();
HttpCookie first = cookies.getFirst("theme");
String value = first == null ? "light" : first.getValue();
```

Đây là snippet trong method đã có `ServerWebExchange` và imports `org.springframework.http.HttpCookie`.

### HttpOnly, Secure, SameSite không tạo authentication tự động

- `HttpOnly` khiến JavaScript phía browser thông thường không đọc cookie, **server vẫn nhận cookie** trong HTTP requests phù hợp.
- `Secure` giới hạn việc browser gửi cookie trên kết nối an toàn, không xác minh tính toàn vẹn business content.
- `SameSite` giúp giảm một số tình huống gửi cookie cross-site, **không thay** CSRF protection khi ứng dụng cần.
- Cookie value có thể bị sửa trừ khi dùng cơ chế ký/mã hóa và server-side validation; tên cookie như `role=admin` không phải role thật.
- Session cookie cần cấu hình Secure/HttpOnly/SameSite và session security policy theo môi trường; không echo session token trong JSON hoặc log.

Cookie là input cần kiểm tra, không phải kho dữ liệu server bảo đảm đáng tin chỉ vì browser quản lý nó.

## 8. Principal: danh tính đã được framework xác thực

WebFlux hỗ trợ method argument kiểu `java.security.Principal` và reactive wrapper khi thích hợp, cùng `ServerWebExchange.getPrincipal()` trả `Mono<Principal>`.

```java
@GetMapping("/whoami")
public Mono<String> whoami(ServerWebExchange exchange) {
    return exchange.getPrincipal()
            .map(Principal::getName)
            .defaultIfEmpty("anonymous");
}
```

Đây là snippet trong controller với import `java.security.Principal`. Nếu không có principal, `Mono.empty()` được chuyển thành chuỗi `"anonymous"`. **Không kết luận rằng unauthenticated user được phép truy cập mọi resource**: endpoint public có thể trả anonymous; endpoint bảo vệ phải được policy chặn (401/403) trước khi controller xử lý.

### @AuthenticationPrincipal thuộc Spring Security

Nếu tích hợp `spring-boot-starter-security`/Spring Security WebFlux:

```java
@GetMapping("/secure/profile")
public Mono<ProfileView> profile(
        @AuthenticationPrincipal CustomUser user) {
    return service.profileFor(user.id());
}
```

Đây là **snippet ý tưởng** cần Spring Security dependency, type `CustomUser`/`ProfileView` và bean `service`. `@AuthenticationPrincipal` là annotation Spring Security (`org.springframework.security.core.annotation.AuthenticationPrincipal`), không phải từ `spring-boot-starter-webflux` thuần. Không thêm nó vào file demo không có security.

`Authentication` trong Spring Security thường implement `Principal`; `Principal.getName()` là một tên định danh, không tự bảo đảm mọi application-specific role, tenant hoặc permission. Để kiểm tra quyền, dùng reactive security configuration, method security khi áp dụng và domain-level authorization.

### Principal có thể là empty

`exchange.getPrincipal()` là một Mono, không được gọi `.block()` trong Netty event loop để lấy giá trị cho controller. Kết hợp:

```java
return exchange.getPrincipal()
    .map(Principal::getName)
    .defaultIfEmpty("anonymous")
    .map(name -> new UserView(name));
```

Đây là composition non-blocking; WebFlux subscribe và ghi HTTP response. Nếu code lấy principal bằng `@RequestHeader("X-User")` mà không có trusted authentication middleware, client có thể tự đổi sang bất kỳ tên nào.

## 9. ServerWebExchange là gì?

`org.springframework.web.server.ServerWebExchange` bao toàn bộ interaction ở lớp WebFlux:

| API | Kiểu hoặc ý nghĩa |
| --- | --- |
| `getRequest()` | `ServerHttpRequest` (method, URI, headers, cookies, query params, path, ID...) |
| `getResponse()` | `ServerHttpResponse` (status, headers, cookies, body writing) |
| `getAttributes()` | `Map<String,Object>` mutable cho **một exchange** |
| `getAttribute(key)` | Đọc attribute đã tồn tại, có thể null |
| `getRequiredAttribute(key)` | Lấy bắt buộc; lỗi nếu thiếu |
| `getAttributeOrDefault(key, fallback)` | Fallback khi key không có |
| `getPrincipal()` | `Mono<Principal>` hoặc Mono empty |
| `getSession()` | `Mono<WebSession>` |
| `getFormData()` | `Mono<MultiValueMap<String,String>>` |
| `getMultipartData()` | `Mono<MultiValueMap<String,Part>>` |
| `getLocaleContext()` | LocaleContext theo resolver |
| `getLogPrefix()` | Prefix tương quan log của exchange |
| `checkNotModified(...)` | Hỗ trợ conditional requests ETag/Last-Modified |

**Exchange không phải một singleton:** mỗi HTTP interaction có attributes và response state riêng. Không cất `ServerWebExchange` trong static map/background thread sống lâu hơn request. Khi result body là `Flux` chưa hoàn tất, exchange/connection vẫn còn vòng đời xử lý, cần cleanup trên cancel và error.

### getRequest() phổ biến

```java
ServerHttpRequest request = exchange.getRequest();
String method = request.getMethod().name();
String path = request.getPath().value();
String rawQuery = request.getURI().getRawQuery();
String client = request.getHeaders().getFirst("X-Client");
String firstTag = request.getQueryParams().getFirst("tag");
String requestId = request.getId();
```

Snippet trên yêu cầu imports. `getRawQuery()` có thể null nếu URI không có query. `getPath().value()` không phải filesystem path; đừng nối nó vào file API. `getId()`/`getLogPrefix()` hỗ trợ logs, không phải security credentials.

### Response headers/status

```java
exchange.getResponse().getHeaders()
        .add("X-App-Info", "webflux");
```

Có thể set header trước khi response commit; sau commit không bảo đảm sửa status/headers còn tác dụng. Thông thường controller trả `ResponseEntity<T>` để kiểm soát status/headers, còn `WebFilter` thêm cross-cutting correlation headers.

Đừng gọi `getResponse().setComplete()` rồi tiếp tục return Publisher ghi JSON cùng response. Hoặc để framework quản lý body, hoặc chủ động handle response với `Mono<Void>` đúng contract.

## 10. Exchange attributes: dữ liệu nội bộ của một request

Filter có thể tạo metadata khi request đến:

```java
exchange.getAttributes().put("app.traceId", traceId);
return chain.filter(exchange);
```

Controller đọc bằng:

```java
String trace = exchange.getRequiredAttribute("app.traceId");
```

Hoặc khai báo:

```java
@GetMapping("/trace")
public Mono<String> trace(
        @RequestAttribute("app.traceId") String traceId) {
    return Mono.just(traceId);
}
```

`@RequestAttribute` lấy **attribute đã được server/filter tạo**, không đọc query/header cùng tên. Không nhầm `@RequestAttribute` với `@RequestParam` hoặc `@SessionAttribute`.

Các quy tắc:

- Dùng key namespace rõ, ví dụ `app.traceId`, tránh đụng framework keys.
- Attributes tồn tại theo **một exchange**, không tự lưu qua request khác.
- Attribute có thể chứa object Java, không phải chỉ String; tránh cast sai kiểu.
- Không đưa credential/secret vào attributes nếu không kiểm soát người có thể log/serialize chúng.
- Nếu filter không chạy (route/filter configuration khác), required attribute thiếu có thể tạo error; dùng `required=false` hoặc kiểm tra fallback khi thích hợp.
- Dùng correlation ID do server tạo hoặc do trusted ingress kiểm chứng. Header `X-Request-Id` tự khai từ client nên được validate/normalize trước khi dùng làm trace ID tin cậy.

**Attribute không phải Session:** khi reload trang, browser gửi request mới; exchange attributes cũ không có nữa. **Attribute không phải Reactor Context:** context đi theo subscriber chain, không phải mutable map thay thế cho mọi propagation qua scheduler.

## 11. Đọc form-urlencoded: getFormData()

Request:

```http
POST /api/input/form?name=query HTTP/1.1
Content-Type: application/x-www-form-urlencoded

name=Linh&topic=java&topic=webflux
```

Trong WebFlux:

```java
@PostMapping(path = "/form",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public Mono<FormView> form(ServerWebExchange exchange) {
    return exchange.getFormData()
        .map(form -> new FormView(
            form.getFirst("name"),
            form.getOrDefault("topic", List.of())));
}
```

Đây là snippet có `record FormView(String name,List<String> topic) {}` trong controller.

`getFormData()` trả `Mono<MultiValueMap<String,String>>` được giải mã từ **body form-urlencoded**. Spring sử dụng configured `HttpMessageReader`. Nếu Content-Type không phù hợp, contract trả empty map thay vì “đọc mọi body dưới dạng form”.

**Khác biệt trọng yếu:** WebFlux `@RequestParam("name")` đọc `?name=query` ở URI, **không tự lấy** `name=Linh` trong form body. Trong Spring MVC Servlet, khái niệm request parameters thường gộp query/form; không áp suy luận đó vào reactive stack.

### getFormData có được gọi hai lần không?

`DefaultServerWebExchange` đọc và parse form body thành map rồi **cache kết quả** để `getFormData()` có thể được gọi nhiều lần mà không đọc lại stream từ network. Điều đó không có nghĩa raw body `Flux<DataBuffer>` có thể tùy tiện đọc lặp lại.

Vì parser có thể phải tiêu thụ/cất form data, cần đặt payload size/memory budgets và không chấp nhận form body khổng lồ. Với JSON, dùng `@RequestBody Mono<Dto>` để framework decode, không gọi `getFormData()`.

## 12. Đọc multipart: getMultipartData()

Với `multipart/form-data`:

```bash
curl -i -F 'description=demo' \
  -F 'file=@sample.txt' \
  http://localhost:8080/api/input/multipart
```

`exchange.getMultipartData()` trả `Mono<MultiValueMap<String,Part>>`. Trong đó `Part` biểu diễn form/file part, có thể là `FormFieldPart` hoặc `FilePart`.

Một endpoint chỉ xem **metadata** về các tên part có thể viết:

```java
@PostMapping(path = "/multipart",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<UploadSummary> multipart(ServerWebExchange exchange) {
    return exchange.getMultipartData()
        .map(parts -> new UploadSummary(
            parts.keySet().stream().sorted().toList(),
            parts.values().stream().mapToInt(List::size).sum()));
}
```

Snippet giả định `record UploadSummary(List<String> names,int count) {}`. Đây không phải xử lý upload thực: chưa lưu hay quét file, chỉ đếm các parts. **Không log nguyên file content hoặc raw filename từ client**.

### Những giới hạn rất quan trọng

- `getMultipartData()` đọc/parse request thành `MultiValueMap` và cache **map parts** khi phù hợp; **nội dung mỗi Part không được cache để đọc lặp**.
- Với file lớn, full multipart map parsing có overhead và giới hạn memory/disk tùy codec; xem streaming `Flux<PartEvent>` và configuration limits nếu cần.
- Nếu lấy `Part.content()` là `Flux<DataBuffer>`, data buffers phải được tiêu thụ, chuyển tiếp hoặc release đúng cơ chế; không giữ các DataBuffer trong list vô hạn.
- `FilePart.filename()` là **tên không tin cậy do client cung cấp**; không dùng trực tiếp làm path lưu file.
- Validate file size, count, MIME/content signature, filename canonicalization, storage permissions và antivirus/quarantine tùy rủi ro.
- Đặt hạn mức `maxInMemorySize`/multipart codec configuration phù hợp. Vì một request có thể gửi nhiều parts, cần tổng request budget, không chỉ per-field.
- `@RequestPart("file") FilePart file` hoặc `@RequestPart("meta") Mono<Dto>` là lựa chọn tốt khi chỉ cần vài parts.

**Không trộn hai cách consume body** (`getMultipartData()` và raw `@RequestBody Flux<PartEvent>`) trên cùng request rồi mong đọc cùng bytes hai lần.

## 13. Đọc JSON body: @RequestBody Mono<T>

Nếu request body JSON:

```http
POST /api/input/json HTTP/1.1
Content-Type: application/json

{"message":"Xin chào"}
```

Khai báo:

```java
@PostMapping(path = "/json",
             consumes = MediaType.APPLICATION_JSON_VALUE)
public Mono<NoteView> json(
        @RequestBody Mono<NoteInput> input) {
    return input.map(v -> new NoteView(v.message()));
}
```

Đây là snippet cần DTO records/imports. `@RequestBody` dùng `HttpMessageReader`/Jackson decoder phù hợp để parse JSON. Mono của body cho phép nối các toán tử mà không block event loop.

**Không gọi `exchange.getRequest().getBody().collectList().block()` trong controller.** Nó vừa block vừa có thể gom bytes vào memory và lấy mất stream khỏi decoder, dẫn tới lỗi khi handler khác đọc body. Nếu muốn log body trong WebFilter, cần kiến trúc decorator/buffer bounded, redaction, reference counting và security review; không đơn giản “đọc một lần rồi chuyển tiếp y nguyên”.

Form-urlencoded, multipart và JSON là **body formats khác nhau**, không thể chỉ đổi annotation `@RequestParam` rồi mong WebFlux đọc hết cả ba.

## 14. getSession(): WebSession và giới hạn lưu trạng thái

`exchange.getSession()` trả `Mono<WebSession>`. Khi cần state server quản lý cho người dùng, dùng WebSession thay vì Exchange attributes:

```java
@GetMapping("/session-info")
public Mono<SessionView> sessionInfo(
        ServerWebExchange exchange) {
    return exchange.getSession()
        .map(s -> new SessionView(
            s.isStarted(), s.getAttributes().size()));
}
```

Snippet này không trả session ID/token ra client. `WebSession` có `getId()`, `getAttributes()`, `getMaxIdleTime()`, `invalidate()`, `save()`; không phải API cho phép lưu vô hạn data giữa các requests.

Spring WebFlux method arguments cũng có thể nhận `WebSession` (hoặc reactive wrapper phù hợp). Gọi `getSession()` để đọc không đồng nghĩa phải bắt đầu session mới ở phía client; theo Spring docs, session thường không bị start cho tới khi attributes được thêm hoặc API start được gọi.

### Attribute, session và Principal không thay nhau

| Khái niệm | Thời gian sống | Dùng làm gì |
| --- | --- | --- |
| Exchange attribute | Một HTTP exchange | Trace, metadata từ filter, request-local state |
| Reactor Context | Một subscription chain | Trace/security/reactive context propagation |
| WebSession | Tồn tại qua requests theo session policy | Server-side user session state |
| Cookie | Client gửi lại theo browser policies | Session identifier hoặc client preference |
| Principal | Identity từ authentication chain | Xác định user hiện tại khi auth được cấu hình |
| Database record | Durable theo domain | Thông tin nghiệp vụ và authorization data |

Không lưu `ServerWebExchange` hay object có reference đến request/response trong `WebSession`. Khi dùng Redis WebSession, chỉ lưu dữ liệu nhỏ, được serializable theo config và không nhạy cảm ngoài ý muốn. Session không thay authorization check mỗi lần truy cập protected resource.

## 15. Locale, method, URI và request context

`ServerWebExchange.getLocaleContext()` cho locale/time zone theo resolver ứng dụng. Method argument `Locale` được Spring WebFlux hỗ trợ trực tiếp. Đừng tự lấy `Accept-Language` rồi chọn chuỗi đầu tiên khi resolver đã cung cấp logic.

```java
@GetMapping("/locale")
public Mono<String> locale(Locale locale) {
    return Mono.just(locale.toLanguageTag());
}
```

Snippet này trả locale tag ứng dụng quyết định. Khi client gửi `Accept-Language: vi-VN,vi;q=0.9`, kết quả tùy locale resolver có thể là `vi-VN` nếu cấu hình phù hợp; không coi thông tin locale là identity/country của người dùng.

Lấy đường dẫn/canonical request data:

```java
String uri = exchange.getRequest().getURI().toString();
String rawPath = exchange.getRequest().getURI().getRawPath();
String path = exchange.getRequest().getPath().value();
String method = exchange.getRequest().getMethod().name();
String logPrefix = exchange.getLogPrefix();
```

Đây là snippets. `rawPath` chứa percent-encoding theo URI; `getPath().value()` biểu diễn path theo API WebFlux (đừng tự decode hai lần). Không dùng URI/query raw làm filesystem path, key authorization hoặc log toàn bộ khi URL có bí mật. Forwarded headers có thể bị spoof nếu chưa cấu hình trusted proxy.

## 16. Vòng đời data trong reactive pipeline

Sơ đồ:

```text
HTTP headers + query + cookies  ──────> Handler argument binding
       |
       +-- WebFilter writes exchange attribute
       |
HTTP body (JSON/form/multipart) ───────> Mono/Flux decoder/parser
       |
Authentication middleware  ───────────> exchange.getPrincipal()
       |
WebSession manager ────────────────────> exchange.getSession()
       |
Controller returns Mono<DTO> / Flux<T>
       |
HTTP infrastructure subscribes / writes response
       |
complete / error / cancel -> cleanup
```

Header/query/cookie information thường đã sẵn trong request metadata; body reading là **reactive**, có thể chỉ thực thi khi downstream subscribe. Không gọi `subscribe()` bằng tay để “đọc body sớm” rồi return response độc lập.

`Mono<Principal>` hay `Mono<MultiValueMap<...>>` không bảo đảm asynchronous thread mới; Reactor chỉ định tín hiệu/demand. Không gọi `block()` bên trong controller/WebFilter trên Netty event loop. Dữ liệu request thuộc về exchange; sau completion/cancel không giữ một lambda background tham chiếu exchange rồi thao tác response.

## 17. Mã runnable: Spring Boot 3 WebFlux + Java 17

Tạo Maven project Spring Initializr:

- Java 17+, Spring Boot **3.x**.
- Dependency `spring-boot-starter-webflux`.
- Dependency `spring-boot-starter-test` (test scope), `io.projectreactor:reactor-test` nếu project chưa có.
- **Không thêm `spring-boot-starter-web`** nếu muốn chắc Boot chọn WebFlux reactive application type trong cấu hình mặc định.

Chương trình demo không cần database hoặc Spring Security, vì vậy `exchange.getPrincipal()` mặc định không có user và trả `"anonymous"` theo fallback. Demo chỉ **echo** những giá trị đã chọn; không mở endpoint hiển thị toàn bộ headers/cookies.

Cấu trúc:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  CorrelationFilter.java
  InputController.java
src/test/java/com/example/demo/
  InputControllerTest.java
```

### 17.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 17.2. CorrelationFilter.java

```java
package com.example.demo;

import java.util.UUID;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(-100)
public class CorrelationFilter implements WebFilter {

    public static final String TRACE_ID = "app.traceId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        // Server tự tạo trace ID, không tin X-Trace-Id client tự khai.
        String trace = UUID.randomUUID().toString();

        exchange.getAttributes().put(TRACE_ID, trace);
        exchange.getResponse().getHeaders()
                .set("X-Trace-Id", trace);

        return chain.filter(exchange);
    }
}
```

Filter tạo một attribute trong scope của exchange và header response cùng giá trị. UUID minh họa **correlation ID**, không phải access token, secret hay thứ dùng để quyết định authorization. Trong production, dùng observation/tracing infrastructure để liên kết spans/requests, điều chỉnh order trước/sau security theo policy.

### 17.3. InputController.java

```java
package com.example.demo;

import java.security.Principal;
import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.http.HttpCookie;
import org.springframework.http.HttpHeaders;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/input")
public class InputController {

    @GetMapping(path = "/query",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<QueryView> query(
            @RequestParam("q") String q,
            @RequestParam(name = "page", defaultValue = "1") int page,
            @RequestHeader(name = "X-Client",
                           defaultValue = "unknown") String client,
            @CookieValue(name = "theme",
                         defaultValue = "none") String theme,
            @RequestAttribute(CorrelationFilter.TRACE_ID)
                    String traceId,
            ServerWebExchange exchange) {

        // Repeated query params không bị mất trong MultiValueMap.
        List<String> tags = exchange.getRequest().getQueryParams()
                .getOrDefault("tag", List.of());

        // Khi không có Authentication provider, principal có thể empty.
        return exchange.getPrincipal()
                .map(Principal::getName)
                .defaultIfEmpty("anonymous")
                .map(name -> new QueryView(
                    q, page, List.copyOf(tags), client,
                    theme, name, traceId));
    }

    @GetMapping(path = "/raw",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<RawView> raw(ServerWebExchange exchange) {
        var request = exchange.getRequest();

        String method = request.getMethod().name();
        String path = request.getPath().value();
        String firstTag = request.getQueryParams().getFirst("tag");
        String firstClient = request.getHeaders().getFirst("X-Client");

        HttpCookie cookie = request.getCookies().getFirst("theme");
        String theme = cookie == null ? "none" : cookie.getValue();

        return Mono.just(new RawView(
            method, path,
            firstTag == null ? "none" : firstTag,
            firstClient == null ? "unknown" : firstClient,
            theme,
            exchange.getRequiredAttribute(
                    CorrelationFilter.TRACE_ID)));
    }

    @GetMapping(path = "/whoami",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<UserView> whoami(ServerWebExchange exchange) {
        return exchange.getPrincipal()
                .map(Principal::getName)
                .defaultIfEmpty("anonymous")
                .map(UserView::new);
    }

    @GetMapping(path = "/session-info",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<SessionView> session(ServerWebExchange exchange) {
        // Không trả session ID/token về client.
        return exchange.getSession()
                .map(s -> new SessionView(
                    s.isStarted(), s.getAttributes().size()));
    }

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<FormView> form(
            @RequestParam(name = "name", required = false)
                    String queryName,
            ServerWebExchange exchange) {

        // @RequestParam trong WebFlux chỉ lấy query "name".
        // getFormData đọc name và topic từ BODY form-urlencoded.
        return exchange.getFormData()
                .map(values -> new FormView(
                    queryName == null ? "(không có)" : queryName,
                    values.getFirst("name"),
                    List.copyOf(values.getOrDefault(
                        "topic", List.of()))));
    }

    @PostMapping(path = "/json",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<NoteView> json(
            @RequestBody Mono<NoteInput> input) {
        return input.map(value -> new NoteView(value.message()));
    }

    @PostMapping(path = "/multipart",
                 consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<UploadView> multipart(
            ServerWebExchange exchange) {
        // Chỉ thống kê tên part, KHÔNG đọc/lưu file bytes.
        return exchange.getMultipartData()
                .map(parts -> new UploadView(
                    parts.keySet().stream().sorted().toList(),
                    parts.values().stream()
                        .mapToInt(List::size).sum()));
    }

    public record QueryView(
            String q, int page, List<String> tags,
            String client, String theme,
            String principal, String traceId) {}

    public record RawView(
            String method, String path,
            String firstTag, String client,
            String theme, String traceId) {}

    public record UserView(String name) {}

    public record SessionView(
            boolean started, int attributeCount) {}

    public record FormView(
            String queryName, String formName, List<String> topics) {}

    public record NoteInput(String message) {}
    public record NoteView(String message) {}

    public record UploadView(
            List<String> partNames, int partCount) {}
}
```

**Vì sao code này dùng hai đường để đọc metadata?** Endpoint `/query` minh họa annotation binding cùng Principal; `/raw` minh họa `ServerWebExchange` direct APIs. Cả hai vẫn chạy cùng Spring WebFlux handler infrastructure.

**Vì sao Principal fallback?** Project demo chưa cài Spring Security; `getPrincipal()` thường empty. Trong app có security, principal có thể hiện diện theo policy. `"anonymous"` chỉ là một nhãn output hiển thị, **không phải** identity đã xác thực.

**Vì sao form queryName khác formName?** Để kiểm chứng WebFlux `@RequestParam` chỉ đọc URI query còn `getFormData()` đọc form body. Không tự trộn chúng theo hành vi Spring MVC.

**Vì sao Multipart chỉ đếm parts?** Chủ đề là đọc dữ liệu trong exchange; triển khai upload thật cần giới hạn kích thước, kiểm chữ ký file, storage an toàn và lựa chọn streaming riêng. File content có thể tiêu tốn tài nguyên ngay cả khi endpoint chỉ đếm tên parts; không bật endpoint metadata demo ngoài môi trường test mà không có access control.

**Về imports:** `HttpHeaders` và `MultiValueMap` được nêu trong các ví dụ phía trước nhưng chưa dùng trực tiếp trong method hoàn chỉnh; Java cho phép unused imports (compiler Java thông thường không coi đó là lỗi). Có thể bỏ khi dùng IDE để code gọn.

### 17.4. Chạy ứng dụng

macOS/Linux:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Nếu không tùy chỉnh, endpoint ở `http://localhost:8080`. Mã Spring Boot phải có Maven/Gradle classpath; `javac InputController.java` độc lập không thể biên dịch vì thiếu Spring/Reactor dependencies.

## 18. Curl: query, header, cookie, principal và trace

### 18.1. Query có tag lặp và header/cookie

```bash
curl -i 'http://localhost:8080/api/input/query?q=a%2Bb%26c&page=2&tag=java&tag=webflux' \
  -H 'X-Client: mobile-app' \
  -H 'Cookie: theme=dark'
```

Dự kiến HTTP 200 với body mang các trường:

```json
{
  "q": "a+b&c",
  "page": 2,
  "tags": ["java", "webflux"],
  "client": "mobile-app",
  "theme": "dark",
  "principal": "anonymous",
  "traceId": "UUID-khác-nhau-mỗi-request"
}
```

Chuỗi `"UUID-khác-nhau-mỗi-request"` ở JSON trên chỉ là **ký hiệu minh họa**, không phải stdout literal. Thực tế `traceId` là UUID do filter server tạo, ví dụ `"550e8400-e29b-41d4-a716-446655440000"`, đồng thời response header `X-Trace-Id` mang đúng cùng giá trị. Không hardcode UUID hoặc thứ tự JSON properties trong test.

### 18.2. Default values

```bash
curl -i 'http://localhost:8080/api/input/query?q=hello'
```

Dự kiến `page=1`, `tags=[]`, `client="unknown"`, `theme="none"`, `principal="anonymous"`, còn `traceId` thay đổi mỗi request.

### 18.3. Missing query bắt buộc

```bash
curl -i 'http://localhost:8080/api/input/query'
```

Dự kiến **HTTP 400 Bad Request** vì thiếu `q`. Body lỗi phụ thuộc Spring Boot/WebFlux error handling; không cam kết một JSON định dạng duy nhất nếu chưa tự cấu hình `ErrorWebExceptionHandler`.

### 18.4. Sai kiểu page

```bash
curl -i 'http://localhost:8080/api/input/query?q=ok&page=abc'
```

Dự kiến **400** do conversion String→int thất bại. Ngược lại, `page=-1` vẫn convert được, cần domain validation nếu không chấp nhận.

### 18.5. Đọc ServerWebExchange metadata trực tiếp

```bash
curl -i 'http://localhost:8080/api/input/raw?tag=java&tag=webflux' \
  -H 'X-Client: cli' \
  -b 'theme=light'
```

Body JSON ví dụ:

```json
{
  "method": "GET",
  "path": "/api/input/raw",
  "firstTag": "java",
  "client": "cli",
  "theme": "light",
  "traceId": "UUID-khác-nhau-mỗi-request"
}
```

Response `X-Trace-Id` và JSON traceId phải bằng nhau; ý tưởng này test filter tạo exchange attribute rồi controller đọc, **không phải lấy trace trực tiếp từ header client gửi**.

### 18.6. Principal khi chưa cài security

```bash
curl -i 'http://localhost:8080/api/input/whoami'
```

Dự kiến 200:

```json
{"name":"anonymous"}
```

Trong app có Spring Security yêu cầu authentication, request chưa có thông tin hợp lệ có thể nhận 401/redirect thay vì chạy controller; đây là kết quả mong đợi của policy, không phải lỗi `exchange.getPrincipal()`.

### 18.7. Session chỉ được xem metadata

```bash
curl -i 'http://localhost:8080/api/input/session-info'
```

Dự kiến response JSON với `started` (boolean) và `attributeCount` (số nguyên). Với project demo chưa thêm session attributes, thường `started=false`, `attributeCount=0`. Không echo session ID hoặc Set-Cookie chứa session token như “bằng chứng”.

## 19. Curl: form-urlencoded khác query params

Gửi body form:

```bash
curl -i -X POST \
  'http://localhost:8080/api/input/form?name=query' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'name=Linh&topic=java&topic=webflux'
```

Expected JSON:

```json
{
  "queryName": "query",
  "formName": "Linh",
  "topics": ["java", "webflux"]
}
```

Vì `@RequestParam(name="name")` trong WebFlux chỉ nhìn query string nên `queryName="query"`, còn `getFormData().getFirst("name")` là `"Linh"`. Nếu bỏ `?name=query`, `queryName` sẽ thành `"(không có)"` theo code demo, còn body vẫn giữ Linh.

Để khỏi tự encode form fields:

```bash
curl -i -X POST \
  'http://localhost:8080/api/input/form' \
  --data-urlencode 'name=Linh' \
  --data-urlencode 'topic=a+b' \
  --data-urlencode 'topic=Spring & WebFlux'
```

`--data-urlencode` sẽ encode dữ liệu theo form-style, literal `+` và `&` không biến thành delimiters ngoài ý muốn. Nếu gửi raw `topic=a+b` trong form body, dấu `+` có thể được parser coi là space; muốn dấu cộng literal phải dùng `%2B`.

### Vì sao không dùng URLDecoder trong controller?

`getFormData()` đã được form parser decode. Nếu value là literal `"%2F"` được gửi trên wire thành `%252F`, ứng dụng nhận đúng `"%2F"`. Chạy `URLDecoder.decode(...)` thêm lần nữa sẽ đổi thành slash `"/"` và có thể tạo bug bảo mật/đổi business value.

## 20. Curl: JSON và multipart

### 20.1. JSON body

```bash
curl -i -X POST \
  'http://localhost:8080/api/input/json' \
  -H 'Content-Type: application/json' \
  -d '{"message":"Xin chào WebFlux"}'
```

Dự kiến HTTP 200:

```json
{"message":"Xin chào WebFlux"}
```

Đây là `@RequestBody Mono<NoteInput>`, không phải `@RequestParam` và không phải `getFormData`. Nếu gửi JSON syntax hỏng, reactive body reader thường tạo 400. Nếu thiếu `message`, record có thể nhận null theo Jackson nếu không có validation; ứng dụng thật cần `@Valid`/constraints và domain checks.

### 20.2. Multipart form

Tạo tệp nhỏ `sample.txt` chứa dữ liệu test rồi chạy:

```bash
curl -i -X POST \
  'http://localhost:8080/api/input/multipart' \
  -F 'description=demo' \
  -F 'file=@sample.txt'
```

Body ví dụ:

```json
{"partNames":["description","file"],"partCount":2}
```

Spring multipart codec quyết định parsing và giới hạn. Không dùng ví dụ “đếm parts” để kết luận file upload đã được lưu, quét virus hoặc kiểm MIME. Nếu tên file độc hại và size quá lớn, production phải reject/sanitize đúng và cleanup resources, không chỉ echo metadata.

## 21. WebTestClient: test controller và filter trên HTTP thật

Tệp `src/test/java/com/example/demo/InputControllerTest.java`:

```java
package com.example.demo;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class InputControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void queryHeaderCookieAndFilterAttribute() {
        client.get()
            .uri("/api/input/query?q=a%2Bb%26c&page=2"
                + "&tag=java&tag=webflux")
            .header("X-Client", "mobile-app")
            .cookie("theme", "dark")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("X-Trace-Id")
            .expectBody()
            .jsonPath("$.q").isEqualTo("a+b&c")
            .jsonPath("$.page").isEqualTo(2)
            .jsonPath("$.tags[0]").isEqualTo("java")
            .jsonPath("$.tags[1]").isEqualTo("webflux")
            .jsonPath("$.client").isEqualTo("mobile-app")
            .jsonPath("$.theme").isEqualTo("dark")
            .jsonPath("$.principal").isEqualTo("anonymous")
            .jsonPath("$.traceId").isNotEmpty();
    }

    @Test
    void missingRequiredQueryParameterReturns400() {
        client.get().uri("/api/input/query")
            .exchange().expectStatus().isBadRequest();
    }

    @Test
    void wrongPageTypeReturns400() {
        client.get().uri("/api/input/query?q=ok&page=nope")
            .exchange().expectStatus().isBadRequest();
    }

    @Test
    void rawExchangeSeesRequestMetadata() {
        client.get().uri("/api/input/raw?tag=java&tag=reactor")
            .header("X-Client", "cli")
            .cookie("theme", "light")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.method").isEqualTo("GET")
            .jsonPath("$.path").isEqualTo("/api/input/raw")
            .jsonPath("$.firstTag").isEqualTo("java")
            .jsonPath("$.client").isEqualTo("cli")
            .jsonPath("$.theme").isEqualTo("light");
    }

    @Test
    void withoutSecurityPrincipalIsAnonymous() {
        client.get().uri("/api/input/whoami")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("anonymous");
    }

    @Test
    void formBodyIsDifferentFromQueryString() {
        client.post()
            .uri("/api/input/form?name=query")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("name", "Linh")
                .with("topic", "java")
                .with("topic", "webflux"))
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.queryName").isEqualTo("query")
            .jsonPath("$.formName").isEqualTo("Linh")
            .jsonPath("$.topics[0]").isEqualTo("java")
            .jsonPath("$.topics[1]").isEqualTo("webflux");
    }

    @Test
    void jsonBodyIsDecodedByHttpMessageReader() {
        client.post().uri("/api/input/json")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("message", "hello"))
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("hello");
    }

    @Test
    void contentTypeIsPartOfMappingContract() {
        client.post().uri("/api/input/json")
            .contentType(MediaType.TEXT_PLAIN)
            .bodyValue("not-json")
            .exchange()
            .expectStatus().isUnsupportedMediaType();
    }
}
```

Chạy trong Maven Boot 3 project:

```bash
./mvnw test
```

PowerShell:

```powershell
.\mvnw.cmd test
```

Các tests kiểm chính xác những giá trị cốt lõi, **không hardcode UUID** của filter. Nếu muốn khẳng định response header X-Trace-Id **bằng** trường `traceId` trong body, dùng `EntityExchangeResult<byte[]>` và JSON parser/Jackson hoặc consumer của `WebTestClient` để so hai giá trị động trong cùng một response. Việc chỉ kiểm tồn tại/không rỗng (như test mẫu) chưa chứng minh bằng nhau; đây là test bổ sung có ích.

**Giới hạn:** đây là code kiểm thử mẫu; không phải lời khẳng định đã chạy trong repository người dùng. Với Spring Security, request có thể bị chặn bởi authentication/CSRF và test phải tạo security context hoặc credentials phù hợp. `RANDOM_PORT` giúp đi qua HTTP server thực, nhưng chưa bao phủ reverse proxy/CDN và cấu hình production.

## 22. Test Principal thực với Spring Security

Để test authenticated Principal, cần thêm Spring Security WebFlux:

- `spring-boot-starter-security` cho runtime, tạo `SecurityWebFilterChain` đúng policy.
- `spring-security-test` cho test với mock authentication.
- Dùng `@AuthenticationPrincipal` hoặc `ReactiveSecurityContextHolder` khi contract cần thông tin sâu hơn tên `Principal`.
- Khi dùng WebTestClient, cấu hình `mutateWith(mockUser("alice"))` với mock-bound WebTestClient hoặc các setup phù hợp theo Spring Security testing docs; không assume nó hoạt động với mọi kiểu `RANDOM_PORT` live server không được bind test security context.
- Với HTTP thật, dùng Basic/Bearer/cookie/session credentials qua security filter; đừng giả danh `X-User: alice` và coi đó là Principal.
- Kiểm phân biệt **401 Unauthorized** khi thiếu credentials và **403 Forbidden** khi đã xác thực nhưng thiếu permission; status cụ thể phụ thuộc cấu hình Spring Security, nên test theo policy thực tế.
- Kiểm authentication trước khi trả nội dung hay metadata bí mật. Không dùng một `Optional<Principal>` có mặt làm authorization thay cho kiểm roles/tenant/resource owner.

Một ví dụ cực ngắn (không phải file compile độc lập):

```java
@GetMapping("/secure/me")
public Mono<String> me(ServerWebExchange exchange) {
    return exchange.getPrincipal()
        .map(Principal::getName)
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(HttpStatus.UNAUTHORIZED)));
}
```

Endpoint này mới **phản ánh tên principal**, chưa phải security policy đầy đủ; với WebFlux Security nên bảo vệ route bằng `SecurityWebFilterChain`. Nếu authentication là một anonymous Authentication object, cần phân biệt nó với user thật theo Spring Security policy, không chỉ kiểm `Mono<Principal>` có giá trị.

## 23. Bảo mật: dữ liệu nào đáng tin?

### Xác thực khác dữ liệu do client khai

| Input | Có tự đáng tin? | Yêu cầu |
| --- | --- | --- |
| Query `userId=42` | Không | Authz kiểm actor được đọc resource 42? |
| Header `X-Role=ADMIN` | Không | Chỉ đọc nếu trusted gateway kiểm và loại client spoof |
| Cookie `role=admin` | Không | Signed/encrypted/server-validated value nếu cần |
| `Principal` từ security chain | Là identity do security xác định | Vẫn phải check permission/tenant |
| Exchange attribute do trusted WebFilter tạo | Tin theo contract nội bộ | Không cho untrusted caller ghi đè |
| Session attribute | Server-side state theo session policy | CSRF/session fixation và authz vẫn cần |
| `Forwarded`/`X-Forwarded-For` | Có thể bị giả mạo | Config trust proxy, không tin trực tiếp |
| JSON/form/multipart body | Không | Validation, size limits, authorization |

Không tạo URL redirect/external HTTP fetch từ `Host`/`Forwarded` raw mà không kiểm soát: có nguy cơ host-header poisoning, open redirect hoặc SSRF.

### Privacy trong logs và response

Không log/echo toàn bộ `exchange.getRequest().getHeaders()`, `getCookies()` hoặc raw query, vì có thể chứa tokens, email, số điện thoại, session IDs và PII. `Principal.getName()` cũng có thể là định danh cá nhân; chỉ trả trong endpoint có authorization và mục đích rõ. Demo `/query` echo principal để dạy API, không dùng nguyên trạng cho production public.

Header như `X-Request-Id` do client đưa vào cần giới hạn length/characters để chống log injection hoặc trace spoofing. Server-generated correlation ID tránh một số rủi ro nhưng vẫn không phải một authentication token.

## 24. Những lỗi thường gặp và cách xử lý

1. **Dùng @RequestParam để đọc form-urlencoded body trong WebFlux.** Sai phạm vi; dùng `getFormData`/`@ModelAttribute` phù hợp.
2. **Nhầm WebFlux với Spring MVC Servlet request parameters.** Hai stack không gộp query/form giống nhau.
3. **Quên required=true mặc định.** Thiếu query/header/cookie cần thiết thường gây 400.
4. **Nhầm q thiếu với q rỗng.** Dùng validation nếu blank không được phép.
5. **Cho rằng String→int conversion cũng kiểm giá trị trong range.** `-999` là số nhưng có thể sai domain.
6. **Dùng Map<String,String> cho repeated tags.** Nên dùng MultiValueMap/List và quy định duplicates.
7. **Tự split query sau decode theo '&'/'='.** Data encoded có thể biến thành delimiter.
8. **URLDecoder.decode thêm lần nữa sau binding.** Double-decode và thay đổi ký tự gốc.
9. **Lấy header X-User làm identity đã xác thực.** Header do client tự khai.
10. **Ghi toàn bộ Authorization/Cookie headers ra log.** Lộ credentials.
11. **Lưu session ID vào response DTO.** Rò token/có thể bị chiếm phiên.
12. **Coi HttpOnly cookie là server không đọc được.** HttpOnly chặn JS, không chặn HTTP server.
13. **Lấy Principal.getName làm kết luận user có quyền admin.** Authorization riêng.
14. **Tưởng exchange attribute tồn tại qua nhiều requests.** Nó là request-scoped.
15. **Dùng @RequestAttribute nhưng quên WebFilter tạo giá trị.** Thiếu required attribute gây lỗi.
16. **Dùng getFormData và getRequest().getBody như hai nguồn độc lập.** Body consumption cạnh tranh.
17. **Nghĩ getMultipartData cache cả file content.** Map cache, content của part không được đọc hai lần.
18. **Giữ DataBuffer từ multipart mà không release/consume.** Có thể leak native memory.
19. **Tin FilePart.filename an toàn làm filesystem path.** Rủi ro path traversal/name collision.
20. **Không giới hạn số lượng/kích thước multipart.** Memory/disk exhaustion.
21. **Đọc getPrincipal().block() trong Netty event-loop.** Chặn reactive processing.
22. **Tự subscribe Mono<Principal>/getFormData để mutate shared variable.** Race/lifecycle lỗi.
23. **Dùng WebSession như global cache vô hạn.** Tăng memory và data retention.
24. **Tin Forwarded/X-Forwarded headers từ bất kỳ client.** Host/proxy spoofing.
25. **Gửi principal/session/tracing internal values vào public DTO không kiểm tra mục đích.** Rò identity/metadata.
26. **Không test 400/415 trong controller argument handling.** Happy path chưa đủ.
27. **Không phân biệt JSON @RequestBody và multipart @RequestPart.** Codec/validation khác.
28. **Ghi response body thủ công rồi cũng return ResponseEntity/Mono DTO.** Gây double-writing.
29. **Không xử lý client disconnect/cancel với upload dài.** Leak file handles/buffers.
30. **Cho rằng ServerWebExchange an toàn để giữ sau HTTP completion.** Request/response lifecycle hữu hạn.
31. **Dùng RequestParam Optional<T> nhưng quên kiểm empty.** Null/empty contract cần rõ.
32. **Hardcode tên header case-sensitive trong logic tự viết.** HTTP header names case-insensitive.
33. **Không kiểm security khi echo cookies/query của người khác.** Inadvertent data exposure.
34. **Dựa vào raw URI làm tenant/authorization identity.** Cần canonical path và domain policy.
35. **Kỳ vọng @RequestParam không thể xuất hiện trong POST.** Query param vẫn tồn tại ở mọi HTTP method.

## 25. Checklist triển khai production

### Binding và validation

- [ ] Biết rõ parameter nào thuộc query, path, header, cookie, JSON/form/multipart body?
- [ ] `@RequestParam` trong WebFlux chỉ dùng cho query, không nhầm Servlet behavior?
- [ ] `required=false`/`defaultValue`/`Optional` có hợp đồng thiếu/rỗng rõ?
- [ ] Có kiểm format/range/size các giá trị và xử lý conversion errors thành 400?
- [ ] Repeated query params được giữ hoặc từ chối theo policy?
- [ ] Không decode URL thêm lần nữa sau Spring binding?
- [ ] Dùng `HttpHeaders`/`MultiValueMap` có kiểm redaction khi log?
- [ ] Cookie flags, data integrity và CSRF/authorization được cấu hình?

### Exchange, Principal và session

- [ ] Principal đến từ authentication chain đáng tin, không từ header tự khai?
- [ ] Authorization kiểm đúng actor, tenant, resource và action?
- [ ] Xử lý `Mono.empty()`/anonymous một cách đúng với public/protected route?
- [ ] Request attributes có key namespace và producer rõ ràng?
- [ ] Không lưu exchange/session ID/HTTP objects ngoài lifetime phù hợp?
- [ ] Reactor Context/security context không bị mất do tự subscribe?
- [ ] WebSession không giữ PII/credential ngoài chính sách retention?
- [ ] Không tin raw forwarded headers từ proxy chưa cấu hình?

### Bodies và tài nguyên

- [ ] JSON dùng `@RequestBody Mono<T>` và decoder phù hợp?
- [ ] Form-urlencoded dùng `getFormData`/binding, không chồng chéo raw body?
- [ ] Multipart có giới hạn file size/count, storage, scanning và cleanup?
- [ ] Part content/DataBuffer được consume/release chính xác, không đọc lặp?
- [ ] HTTP response chưa commit trước khi ghi header/status?
- [ ] Client disconnect/cancel có cleanup?
- [ ] Không block event-loop với `block()`/JDBC/I/O?

### Test

- [ ] `WebTestClient` kiểm query/header/cookie/trace và data conversion?
- [ ] Test form queryName khác formName, repeated values?
- [ ] Test principal unauthenticated/authenticated với security config thật?
- [ ] Test JSON input, 400, 415 và malformed body?
- [ ] Test upload metadata/size limit và rejected large payload ở môi trường thực?
- [ ] Test qua proxy/ingress để xác minh trusted forwarded headers?
- [ ] Logs không chứa Authorization/Cookie/session/query secrets?

## 26. Tự kiểm tra kiến thức

**1.** Trong WebFlux, `@RequestParam("name")` có tự đọc field `name` trong form body không?

**Đáp án:** Không. WebFlux `@RequestParam` chỉ bind query. Dùng `getFormData()`/`@ModelAttribute` phù hợp với form body.

**2.** `@CookieValue` và `@RequestHeader("Cookie")` có giống nhau không?

**Đáp án:** Cả hai truy cập dữ liệu liên quan cookies, nhưng `@CookieValue` bind một cookie theo tên; `@RequestHeader` lấy raw header string. Với nhiều cookie và decoding, ưu tiên API cookie-aware.

**3.** `@RequestParam("page") int page` nhận `page=abc` ra sao?

**Đáp án:** Conversion thất bại; thường HTTP 400 theo error handling chuẩn.

**4.** `getRequest().getQueryParams()` nên có kiểu map gì?

**Đáp án:** `MultiValueMap<String,String>` để giữ repeated query parameters.

**5.** Principal có thể lấy trực tiếp từ `X-User` client gửi không?

**Đáp án:** Không. Chỉ nhận identity từ trusted auth middleware/Spring Security chain và vẫn phải kiểm quyền.

**6.** Vì sao `exchange.getPrincipal()` trả `Mono<Principal>`?

**Đáp án:** WebFlux dùng reactive abstraction; principal có thể có hoặc không, được nối vào pipeline mà không cần block.

**7.** `@RequestAttribute` lấy ở đâu?

**Đáp án:** Exchange/request attribute đã được set trước, ví dụ bởi `WebFilter`; không phải query/header cùng tên.

**8.** `getFormData()` có thể gọi nhiều lần không?

**Đáp án:** Trong `DefaultServerWebExchange`, form body được parse/cached thành map; gọi lại API này lấy map cache, không chứng minh raw body có thể consume hai lần.

**9.** `getMultipartData()` có cache contents mỗi file part không?

**Đáp án:** Không. Map/parts được cache theo contract, còn nội dung từng Part không được đảm bảo đọc lại.

**10.** Có thể dùng `WebSession.getId()` trả về public JSON như minh họa không?

**Đáp án:** Không nên. Session ID/token là dữ liệu nhạy cảm có thể dẫn tới session hijacking.

**11.** Nếu không có principal và route public, nên làm gì?

**Đáp án:** Xử lý Mono empty/fallback rõ ràng; với route protected thì security filter phải đòi authentication, không tự coi anonymous là user đã có quyền.

**12.** ServerWebExchange attributes tồn tại bao lâu?

**Đáp án:** Trong lifetime của một HTTP exchange, không tự kéo dài sang request khác.

**13.** Vì sao không đọc `getRequest().getBody()` rồi `block()`?

**Đáp án:** Chặn event loop, có thể consume một lần body stream và phá decoder/memory budget; dùng reactive reader/binding APIs.

**14.** Header `Forwarded` có thể tin tuyệt đối để xác định host/protocol ban đầu không?

**Đáp án:** Không. Cần trusted proxy configuration và validation tránh spoofing.

**15.** Khi nào dùng `ServerWebExchange` thay vì chỉ annotations?

**Đáp án:** Khi cần nhiều thành phần request/response, attributes, session, principal, form/multipart map hay chức năng hạ tầng mà annotation binding không diễn đạt tốt bằng một vài tham số rõ ràng.

## 27. Tài liệu tham khảo

- Spring Framework 6.2 — WebFlux Controller Method Arguments: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/arguments.html
- Spring Framework 6.2 — `@RequestParam` query-only ở WebFlux: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestparam.html
- Spring Framework 6.2 — `@RequestHeader`: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestheader.html
- Spring Framework 6.2 — `@CookieValue`: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/cookievalue.html
- Spring Framework 6.2 — `@RequestAttribute`: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestattrib.html
- Spring Framework 6.2 — `@ModelAttribute` / Data Binding: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — Multipart Content: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html
- Spring Framework 6.2 — `@RequestBody`: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework 6.2 — WebHandler API and form/multipart parsing: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework 6.2 — ServerWebExchange API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework 6.2 — ServerHttpRequest API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Security — Reactive WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/index.html
- Spring Security — WebFlux testing: https://docs.spring.io/spring-security/reference/reactive/test/web/index.html
- Reactor Core reference: https://projectreactor.io/docs/core/release/reference/
