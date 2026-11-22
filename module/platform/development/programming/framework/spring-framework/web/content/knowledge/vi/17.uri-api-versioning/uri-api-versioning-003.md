# ServletUriComponentsBuilder và xây URI từ yêu cầu hiện tại trong Spring MVC

## 1. Vấn đề: trả liên kết đúng mà không hardcode máy chủ

Một REST API nhận `POST /api/v1/notes` và tạo tài nguyên mới có thể trả **201 Created**, kèm header **Location** trỏ đến URL của tài nguyên vừa tạo. Một trang HTML cũng có thể cần liên kết tới chính ứng dụng, ví dụ đường dẫn trang chi tiết hoặc URL phân trang.

Nếu ghép chuỗi thủ công:

```java
String location = "http://localhost:8080/api/v1/notes/" + id;
```

URL có thể sai khi ứng dụng chạy trên môi trường khác, có HTTPS trước reverse proxy, chạy dưới context path `/shop`, dùng cổng không mặc định hoặc có một servlet mapping prefix. Nếu gắn trực tiếp ID/slug từ người dùng vào URL, code còn có nguy cơ xử lý encoding sai.

**`ServletUriComponentsBuilder`** trong Spring MVC giúp xây URI dựa trên **các thành phần được Servlet request hiện tại cung cấp**: scheme, host, port, context path, servlet mapping, request path và query, tùy factory method được chọn.

Nó kết hợp với `UriComponentsBuilder` để thêm path, query, URI templates và encode biến một cách có hệ thống. Tuy nhiên, builder **không tự bảo đảm request host/forwarded headers là đáng tin**, không thay thế policy công khai URL của ứng dụng, không tự tạo resource và không biến URL tùy ý thành hợp lệ về bảo mật.

Mục tiêu sau bài:

- Hiểu sự khác biệt chính xác giữa `fromCurrentRequest()`, `fromCurrentRequestUri()`, `fromCurrentContextPath()` và `fromCurrentServletMapping()`.
- Biết dùng `fromRequest(request)`, `fromRequestUri(request)`, `fromContextPath(request)`, `fromServletMapping(request)` khi có `HttpServletRequest` tường minh.
- Tạo `Location` cho response 201, liên kết phân trang, link đến tài nguyên cùng API version.
- Biết `path`, `pathSegment`, `queryParam`, `replaceQueryParam`, `buildAndExpand`, `encode` và `toUri`.
- Phân biệt request-derived URL với **canonical public base URL**, đặc biệt qua reverse proxy.
- Tránh Host-header poisoning, forwarded-header spoofing, open redirect, double encoding, duplicate query và URL sai context path.
- Kiểm thử đường dẫn được sinh ra bằng `MockMvc` và request giả lập.

**Phạm vi:** Spring MVC **Servlet stack**, Java 17+, Spring Framework **6.2.x** / Spring Boot **3.5.x**. Đây không phải builder cho Spring WebFlux; WebFlux có cơ chế server request URI và forwarding khác. Bài thuộc nhóm **URI và phiên bản API**.

## 2. URI gồm các phần gì?

Ví dụ URI tuyệt đối:

```text
https://api.example.org:8443/shop/api/v1/notes/42?lang=vi&page=2

|scheme|      |host|   |port| |context|  |request path|  |query|
  https    api.example.org  8443   /shop  /api/v1/notes/42  lang=vi&page=2
```

Các thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `scheme` | Giao thức URI; thường HTTP/HTTPS | `https` |
| `host` | Tên máy/host của origin từ góc nhìn request | `api.example.org` |
| `port` | Cổng, có thể lược bỏ cổng mặc định | `8443` |
| `contextPath` | Prefix ứng dụng Servlet được deploy dưới một context | `/shop` |
| `servletPath` | Một phần path liên quan servlet mapping, không luôn là toàn route MVC | `/api` hoặc giá trị theo mapping |
| `requestURI` | Path mà Servlet container thấy, không gồm query string | `/shop/api/v1/notes/42` |
| `queryString` | Phần sau `?` của HTTP target | `lang=vi&page=2` |
| `fragment` | Phần `#section` được client diễn giải | Không được gửi lên server như request-target HTTP thông thường |

**`HttpServletRequest#getRequestURL()` không giống `getRequestURI()`.** Request URL thường gồm scheme/host/port/path; request URI chỉ là đường dẫn trong request, không phải URI tuyệt đối. `getQueryString()` là query riêng; `getContextPath()` là Servlet context prefix.

Browser không gửi **fragment** trong HTTP request, nên builder lấy dữ liệu từ request không thể “phục hồi fragment ban đầu” chỉ từ `HttpServletRequest`.

Trong mô hình API:

```text
Origin                 https://api.example.org
Servlet context path   /shop
MVC route              /api/v1/notes
Resource path          /42
Query                  ?lang=vi

Public full URI:
https://api.example.org/shop/api/v1/notes/42?lang=vi
```

Một URL đúng phải xét **path prefix thực tế** khi ứng dụng deploy, không tự nối `/shop` hai lần hoặc bỏ mất nó.

## 3. `ServletUriComponentsBuilder` nằm ở đâu trong Spring?

Class:

```java
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;
```

Nó mở rộng `org.springframework.web.util.UriComponentsBuilder`, cho phép xử lý URI theo thành phần. Các factory methods tạo builder từ Servlet request có thể nhận request trực tiếp hoặc lấy request đang được xử lý qua `RequestContextHolder`.

Chuỗi thực thi đơn giản:

```text
Client HTTP request
       |
       v
Servlet container
  HttpServletRequest (scheme, host, port, contextPath, requestURI, query)
       |
       v
DispatcherServlet -> @RestController handler
       |
       v
ServletUriComponentsBuilder.fromCurrentRequestUri()
       |
       v
.pathSegment("{id}").encode().buildAndExpand(id).toUri()
       |
       v
java.net.URI
       |
       v
ResponseEntity.created(uri).body(resource)
       |
       v
HTTP 201 Created + Location header
```

**Builder không gửi HTTP response.** Nó chỉ tạo một `URI` hoặc `UriComponents`. `ResponseEntity` / Spring MVC mới quyết định status, headers và body. Cũng không có gì trong builder tự ghi bản ghi vào database; nó phải được gọi sau khi ứng dụng đã tạo tài nguyên theo nghiệp vụ.

### 3.1. Tại sao không luôn dùng `URI.create(...)`?

`URI.create("https://example.org/api/notes/42")` thích hợp khi đã có URI hợp lệ được tạo một cách an toàn. Nhưng cách này **không tự lấy** context path/current host, không giúp quản lý URL template và các path/query components.

`UriComponentsBuilder` và `ServletUriComponentsBuilder` giúp thao tác thành phần, đặc biệt khi biến chứa dấu cách, ký tự Unicode hoặc ký tự có nghĩa đặc biệt trong URI.

Không lạm dụng builder để chấp nhận **toàn bộ URI do client nhập** làm destination; điều đó liên quan open redirect/SSRF và phải có validation/allowlist riêng.

## 4. Bốn factory methods quan trọng nhất

Giả sử request giả định:

```http
GET /shop/api/v1/notes?sort=desc&page=2 HTTP/1.1
Host: api.example.org:8443
```

Và Servlet container thấy `scheme=https`, `port=8443`, `contextPath=/shop`, DispatcherServlet mặc định map tại `/`.

### 4.1. `fromCurrentRequest()` — đầy đủ path **và query**

```java
URI sameRequest = ServletUriComponentsBuilder
        .fromCurrentRequest()
        .build()
        .toUri();
```

URI thu được có dạng:

```text
https://api.example.org:8443/shop/api/v1/notes?sort=desc&page=2
```

Dùng khi tạo link đến **biến thể của request hiện tại**, thay query parameter hoặc giữ filter/sort của danh sách.

**Cảnh báo:** nếu dùng làm nền để tạo `Location` cho một tài nguyên vừa POST, query parameters của POST có thể bị giữ lại không cần thiết, ví dụ `?debug=true` hoặc `?source=web`. Với đường dẫn tài nguyên mới, `fromCurrentRequestUri()` hoặc context-based builder thường phù hợp hơn.

### 4.2. `fromCurrentRequestUri()` — có path, **không có query**

```java
URI withoutQuery = ServletUriComponentsBuilder
        .fromCurrentRequestUri()
        .build()
        .toUri();
```

Kết quả:

```text
https://api.example.org:8443/shop/api/v1/notes
```

Dùng cho collection URI hiện tại hoặc xây URI con. Ví dụ POST vào `/api/v1/notes`, sau khi lưu có ID 42:

```java
URI createdUri = ServletUriComponentsBuilder
        .fromCurrentRequestUri()
        .pathSegment("{id}")
        .encode()
        .buildAndExpand(42)
        .toUri();
```

Kỳ vọng:

```text
https://api.example.org:8443/shop/api/v1/notes/42
```

**Không append `"/42"` vào URL đã chứa `?sort=desc&page=2` bằng string concatenation**, vì có thể trở thành `...?sort=desc&page=2/42`.

### 4.3. `fromCurrentContextPath()` — origin + Servlet context path

```java
URI collection = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .path("/api/v1/notes")
        .build()
        .toUri();
```

Kết quả:

```text
https://api.example.org:8443/shop/api/v1/notes
```

Dùng khi muốn tạo link đến **một endpoint khác** trong cùng ứng dụng, không nhất thiết là con của current request. Ví dụ code trong `GET /shop/api/v1/search` muốn link tới `/shop/api/v1/notes`.

**Không nhân đôi context path**:

```java
// Sai nếu contextPath đã là /shop:
ServletUriComponentsBuilder.fromCurrentContextPath()
        .path("/shop/api/v1/notes");
```

Đúng là thêm phần route MVC **sau context**, không chèn lại `/shop`.

### 4.4. `fromCurrentServletMapping()` — origin + context + servlet prefix

Nếu DispatcherServlet được map dạng prefix như `/main/*`, builder này lấy scheme/host/port/context path **và Servlet mapping prefix**:

```java
URI uri = ServletUriComponentsBuilder
        .fromCurrentServletMapping()
        .path("/accounts")
        .build()
        .toUri();
```

Với context `/shop` và servlet mapping prefix `/main`, kết quả có dạng:

```text
https://api.example.org:8443/shop/main/accounts
```

Khi mapping là `/` hoặc dạng extension `*.do`, `fromServletMapping` có thể hành xử như `fromContextPath` theo Javadoc.

**Không coi `servletPath` là chuỗi route bất biến** trong mọi kiểu servlet mapping. `PathPatternParser` của Spring MVC và prefix servlet mapping có những giới hạn tương thích cần xem theo Boot/framework version; nếu chọn prefix mapping, hãy integration-test URI và HandlerMapping trên container thực.

### Tóm tắt so sánh

| Method | Scheme/host/port | Context path | Servlet mapping prefix | Full request path | Query |
| --- | --- | --- | --- | --- | --- |
| `fromCurrentRequest()` | Có | Nằm trong full path | Nằm trong full path nếu có | Có | Có |
| `fromCurrentRequestUri()` | Có | Nằm trong full path | Nằm trong full path nếu có | Có | **Không** |
| `fromCurrentContextPath()` | Có | Có | Không tự lấy prefix riêng | Không | Không |
| `fromCurrentServletMapping()` | Có | Có | Có nếu prefix mapping | Không lấy full handler path | Không |

“Current” ở đây nghĩa là **Servlet request hiện có trong `RequestContextHolder`**. Nó không phải “URL của trang browser đang mở” trong một background job, và không tự suy ra URL chính thức của ứng dụng khi không có request.

## 5. Phiên bản tường minh nhận `HttpServletRequest`

Mỗi nhóm “current” có factory method nhận request tường minh:

| Method hiện tại | Method có request parameter |
| --- | --- |
| `fromCurrentRequest()` | `fromRequest(HttpServletRequest)` |
| `fromCurrentRequestUri()` | `fromRequestUri(HttpServletRequest)` |
| `fromCurrentContextPath()` | `fromContextPath(HttpServletRequest)` |
| `fromCurrentServletMapping()` | `fromServletMapping(HttpServletRequest)` |

Ví dụ trong handler:

```java
@GetMapping("/self")
String self(HttpServletRequest request) {
    return ServletUriComponentsBuilder
            .fromRequestUri(request)
            .build()
            .toUriString();
}
```

Đây là fragment controller, cần import `jakarta.servlet.http.HttpServletRequest`. Khác biệt lớn nhất là **dependency được khai báo tường minh**. Nếu code được gọi từ một helper có `HttpServletRequest` hợp lệ, cách này dễ quan sát nguồn dữ liệu hơn.

**Không truyền một request đã hết lifecycle** vào background thread chỉ để có builder. Servlet request là context của request đang xử lý; link cho email/batch tasks nên dùng canonical base URL từ cấu hình.

### 5.1. Current request được tìm như thế nào?

`ServletUriComponentsBuilder.fromCurrentXxx()` dùng `RequestContextHolder`. `DispatcherServlet` thường expose web request attributes trong thời gian handler xử lý; `RequestContextFilter` / `RequestContextListener` có thể hỗ trợ những thành phần khác khi được cấu hình.

Trong scheduler, `@Async` worker hoặc một thread tự tạo, không mặc định có request attributes. Gọi `fromCurrentRequestUri()` ở đó có thể gặp `IllegalStateException` liên quan request không có trong thread context.

**Không khắc phục bằng cách copy HttpServletRequest tùy ý vào static field hoặc ThreadLocal dùng lâu dài.** Thay bằng:

- Truyền URL/base URI đã được xây an toàn từ tầng web nếu chỉ cần dữ liệu đó.
- Dùng canonical external base URI từ cấu hình khi xử lý email/batch.
- Trong test, giả lập Servlet request hoặc dùng MockMvc thay vì phụ thuộc ambient request ở ngoài MVC.
- Với async request của Spring MVC, kiểm tra cách framework bind/unbind request context theo dispatch/thread, không tự suy đoán.

## 6. `path(...)`, `pathSegment(...)` và URI encoding

### 6.1. `path(String)`

```java
URI uri = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .path("/api/v1/notes/")
        .path("42")
        .build()
        .toUri();
```

`path` nối phần path vào builder. Nó phù hợp cho **đoạn path tĩnh** đã có dấu `/` hợp lý. Nhưng nếu ghép trực tiếp input không đáng tin:

```java
// Anti-pattern: raw path có thể chứa "/" hoặc ký tự đặc biệt.
.path("/api/v1/notes/" + userInput)
```

Khi `userInput` mang `a/b`, nó trở thành **hai path segments** thay vì một định danh duy nhất; khi input chứa `?`, `#`, `%`, `;` hoặc Unicode, việc encoding sai có thể đổi ý nghĩa path.

### 6.2. `pathSegment(String...)`

Dùng `pathSegment` cho từng thành phần tách biệt:

```java
URI uri = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .pathSegment("api", "v1", "notes", "{slug}")
        .encode()
        .buildAndExpand("Spring MVC / cơ bản")
        .toUri();
```

Với `encode()` **trên builder trước khi expand**, các ký tự reserved trong biến được encode chặt, nên dấu cách và dấu `/` thuộc slug không tự trở thành separator route. Đường dẫn sẽ có dạng có percent encoding, ví dụ:

```text
.../api/v1/notes/Spring%20MVC%20%2F%20c%C6%A1%20b%E1%BA%A3n
```

Đây là hình dạng UTF-8 percent-encoding cho giá trị slug; **không phải ví dụ mapping bảo đảm rằng mọi Servlet container cho phép và không decode %2F trên request GET**. Một số containers/proxies từ chối hoặc có policy riêng với **encoded slash**. Thiết kế API nên ưu tiên ID an toàn như số hoặc UUID cho resource path, và đặt chuỗi người dùng vào query/body nếu không thể bảo đảm routing.

### 6.3. Thứ tự `encode()` và `buildAndExpand()`

Hai cách encode dễ bị lẫn:

```java
// Encode template trước và URI variables theo chế độ chặt hơn.
URI a = UriComponentsBuilder
        .fromUriString("https://api.example.org/items/{id}")
        .encode()
        .buildAndExpand("a/b")
        .toUri();

// Encode sau khi expand: có thể giữ một số reserved characters
// theo semantics của từng URI component.
URI b = UriComponentsBuilder
        .fromUriString("https://api.example.org/items/{id}")
        .buildAndExpand("a/b")
        .encode()
        .toUri();
```

Trong Spring Framework 6.2, `UriComponentsBuilder#encode()` trước expand được tài liệu khuyến nghị khi URI variables là **dữ liệu cần encode nghiêm ngặt**. `UriComponents#encode()` sau expand có semantics khác, đặc biệt với dấu phân tách có ý nghĩa trong component.

**Không double encode:** nếu input đã là `a%2Fb` (pre-encoded), gọi encode một lần nữa theo policy dành cho raw values có thể biến `%` thành `%25`, dẫn tới `a%252Fb`. Chọn contract rõ: helper nhận **giá trị thô** hay **component đã encode**, không trộn hai trường hợp.

### 6.4. `build()` và `toUri()`

| Cách gọi | Trả về | Khi dùng |
| --- | --- | --- |
| `builder.build()` | `UriComponents` | Muốn tiếp tục inspect/expand/encode |
| `builder.build().toUri()` | `java.net.URI` | Đưa vào ResponseEntity/HttpHeaders |
| `builder.buildAndExpand(values).toUri()` | `URI` | URI template có biến |
| `builder.encode().buildAndExpand(values).toUri()` | `URI` | Khuyến nghị khi biến là raw user data |
| `builder.toUriString()` | Chuỗi URI từ builder | Khi cần string, chú ý encoding policy |
| `UriComponentsBuilder.fromUriString(...)` | Builder từ template/string, không phụ thuộc Servlet request | Background jobs/configured public base |

Nếu URI không có variables hoặc ký tự đặc biệt, `build().toUri()` đủ đơn giản. Khi có variables, hãy kiểm soát cách encode để chúng không thay đổi cấu trúc URI.

## 7. Query parameters và URL phân trang

Giả sử client gọi:

```http
GET /api/v1/notes?page=2&sort=desc HTTP/1.1
Host: api.example.org
```

Tạo link “trang kế tiếp” mà vẫn giữ `sort`:

```java
URI next = ServletUriComponentsBuilder
        .fromCurrentRequest()
        .replaceQueryParam("page", 3)
        .build()
        .toUri();
```

Kết quả có dạng:

```text
http://api.example.org/api/v1/notes?page=3&sort=desc
```

Thứ tự query keys có thể khác trong các môi trường/parser; **không nên coi query key order là contract**. Những lưu ý:

- `queryParam("page",3)` có thể **thêm** một giá trị mới bên cạnh page cũ. Nếu mục tiêu là thay page hiện tại, dùng **`replaceQueryParam`**.
- `replaceQueryParam("page", 3)` loại các giá trị page cũ theo tên và thêm giá trị mới.
- `replaceQueryParam("page")` có semantics khác, có thể loại parameter theo API; kiểm tra đúng overload/Javadoc.
- `replaceQuery(null)` có thể dùng để bỏ toàn bộ query trong builder khi muốn reset trước khi thiết kế query mới.
- Không tự phản chiếu tất cả query parameters vào link nếu chúng mang secret/token/debug flags. Cân nhắc **allowlist fields** như `page`, `size`, `sort`.
- Không đẩy credentials vào query string của `Location`, pagination, email hoặc logs.
- Query builder không tự kiểm tra business limits (page size tối đa, giá trị sort hợp lệ, number overflow); controller phải validate.

Ví dụ xây pagination chỉ với query cho phép:

```java
URI next = ServletUriComponentsBuilder
        .fromCurrentRequestUri()
        .queryParam("page", 3)
        .queryParam("size", 20)
        .queryParam("sort", "createdAt,desc")
        .build()
        .toUri();
```

Đoạn này loại bỏ mọi query input cũ và tạo lại **các parameters server đã chọn**. Nếu phần `sort` đến từ user, hãy kiểm tra sort key/direction theo allowlist.

## 8. Sinh Location đúng cho POST 201 Created

Một endpoint tạo resource nên thực hiện nghiệp vụ trước, sau đó sinh một đường dẫn truy cập resource mới.

Flow:

```text
POST /api/v1/notes
Content-Type: application/json
{"title":"Spring MVC"}

       |
       v
Validate -> Store/DB tạo id=1001
       |
       v
ServletUriComponentsBuilder.fromCurrentRequestUri()
    .pathSegment("{id}")
    .encode()
    .buildAndExpand(1001)
    .toUri()
       |
       v
ResponseEntity.created(location).body(resource)
       |
       v
HTTP/1.1 201 Created
Location: http://localhost:8080/api/v1/notes/1001

{"id":1001,"title":"Spring MVC"}
```

**Lưu ý:** response minh họa giả định server không chạy dưới proxy/context path và cổng 8080. Nếu HTTP request thực tế được proxy xử lý đúng, Location có thể là `https://api.example.org/...`; không hardcode `localhost:8080` vào production.

### 8.1. Tại sao `fromCurrentRequestUri()` phù hợp ở đây?

- POST collection endpoint có path `/api/v1/notes`, nên append `/{id}` trỏ đến member resource.
- Không giữ query cũ từ POST, ví dụ `?notify=true`.
- Giữ current origin và context path do Servlet request trình bày.
- `pathSegment` cung cấp ranh giới một segment cho ID.
- `ResponseEntity.created` set 201 và `Location`.

**Nhưng nếu POST tạo resource ở một collection khác**, ví dụ `POST /api/v1/imports` tạo `/api/v1/jobs/{id}`, không append `/{id}` vào imports. Hãy tạo từ **context path** hoặc route mapping thật:

```java
URI jobUri = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .pathSegment("api", "v1", "jobs", "{id}")
        .encode()
        .buildAndExpand(jobId)
        .toUri();
```

Với servlet mapping prefix đặc biệt, cần dùng `fromCurrentServletMapping`/explicit configured route prefix khi tương thích; test đường dẫn end-to-end.

## 9. Ví dụ chạy được: Spring Boot 3.5 và Java 17

Dự án dưới đây minh họa:

1. `POST /api/v1/notes` → 201 Created, Location lấy từ request URI không có query.
2. `GET /api/v1/notes/{id}` → resource theo ID.
3. `GET /api/v1/links/inspect?page=2&sort=desc` → so sánh bản có query, không query, context root và phiên bản query page=3.
4. `GET /api/v1/links/catalog` → URI collection notes xây từ context path dù handler hiện tại nằm ở đường khác.
5. Có thể test Host/scheme/port từ Servlet request; khi deploy dưới proxy phải bổ sung trust policy như phần 12.

Dữ liệu lưu trong `ConcurrentHashMap` **chỉ phục vụ ví dụ**; restart mất dữ liệu. Không có auth, DB, giao dịch, multi-node sharing. Không dùng demo này làm production resource service.

### 9.1. Dependencies

Với project Spring Boot **3.5.x**, Java 17, đã có Gradle Boot plugin, repositories và toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **fragment `build.gradle`**, không phải file build độc lập. Starter web dùng Spring MVC Servlet và Jackson do Boot 3 quản lý. Nếu dùng Maven, thêm dependencies tương ứng từ Boot BOM.

### 9.2. Application và controllers

Tạo **`src/main/java/demo/urilinks/UriLinksApplication.java`**:

```java
package demo.urilinks;

import java.net.URI;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@SpringBootApplication
public class UriLinksApplication {

    public static void main(String[] args) {
        SpringApplication.run(UriLinksApplication.class, args);
    }
}

record NewNote(String title) {}

record Note(long id, String title) {}

@RestController
@RequestMapping("/api/v1/notes")
class NoteController {

    private final AtomicLong sequence = new AtomicLong(1000);
    private final ConcurrentMap<Long, Note> notes =
            new ConcurrentHashMap<>();

    @PostMapping
    ResponseEntity<Note> create(@RequestBody NewNote input) {
        if (input == null || input.title() == null
                || input.title().isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "title is required");
        }

        long id = sequence.incrementAndGet();
        Note saved = new Note(id, input.title());
        notes.put(id, saved);

        URI location = ServletUriComponentsBuilder
                .fromCurrentRequestUri()
                .pathSegment("{id}")
                .encode()
                .buildAndExpand(id)
                .toUri();

        return ResponseEntity.created(location).body(saved);
    }

    @GetMapping("/{id}")
    Note find(@PathVariable long id) {
        Note value = notes.get(id);
        if (value == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Note not found");
        }
        return value;
    }
}

record UriSnapshot(
        String requestWithQuery,
        String requestWithoutQuery,
        String contextRoot,
        String notesCollection,
        String pageThree) {}

@RestController
@RequestMapping("/api/v1/links")
class LinksController {

    @GetMapping("/inspect")
    UriSnapshot inspect() {
        String withQuery = ServletUriComponentsBuilder
                .fromCurrentRequest()
                .build()
                .toUriString();

        String withoutQuery = ServletUriComponentsBuilder
                .fromCurrentRequestUri()
                .build()
                .toUriString();

        String context = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .build()
                .toUriString();

        String collection = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/api/v1/notes")
                .build()
                .toUriString();

        String nextPage = ServletUriComponentsBuilder
                .fromCurrentRequest()
                .replaceQueryParam("page", 3)
                .build()
                .toUriString();

        return new UriSnapshot(
                withQuery, withoutQuery, context,
                collection, nextPage);
    }

    @GetMapping("/catalog")
    ResponseEntity<Void> catalog() {
        URI uri = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/api/v1/notes")
                .build()
                .toUri();

        return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(uri)
                .build();
    }
}
```

Đây là **một file Java 17 có cấu trúc hợp lệ** trong dự án Spring Boot 3.5 có dependencies nói trên: chỉ `UriLinksApplication` là public; records/controllers package-private và được component scan trong package `demo.urilinks`.

Phân tích các quyết định:

- `NoteController#create` sử dụng `fromCurrentRequestUri()` vì URI được sinh cho resource con của request collection.
- `pathSegment("{id}")` biểu diễn ID như một URI variable; `encode()` được gọi trước `buildAndExpand(id)`.
- `ResponseEntity.created(location)` trả 201 và `Location`. Body là một Java record, được Jackson serialize thành JSON.
- `GET /api/v1/notes/{id}` có thể dùng với path do Location cung cấp, vì mapping khớp member URI.
- `LinksController#inspect` so sánh chính xác các factory methods trên cùng request; `replaceQueryParam("page",3)` giữ các query keys khác trong ví dụ.
- `catalog` xây URL từ context path, **không** append `/notes` vào `/api/v1/links/catalog`. Nó dùng 303 như một ví dụ HTTP navigation; endpoint không bắt buộc redirect để trả link.
- URI builder không kiểm tra authentication hoặc resource authorization. Nếu API riêng, cần Spring Security ở layer phù hợp.

### 9.3. Chạy và quan sát curl

```bash
./gradlew bootRun
```

Tạo note:

```bash
curl -i -X POST \
  'http://localhost:8080/api/v1/notes?notify=true' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Servlet URI Builder"}'
```

Nếu đây là note đầu tiên, response dự kiến:

```http
HTTP/1.1 201 Created
Location: http://localhost:8080/api/v1/notes/1001
Content-Type: application/json

{"id":1001,"title":"Servlet URI Builder"}
```

**Không có `?notify=true` trong Location** do chọn `fromCurrentRequestUri()`. ID 1001 là minh họa chỉ đúng khi counter khởi tạo ở 1000 và chưa có POST nào khác.

Request tới Location:

```bash
curl -i 'http://localhost:8080/api/v1/notes/1001'
```

Kỳ vọng 200 và JSON của note đã tạo, nếu server cùng instance chưa restart. Nếu code được scale nhiều instances mà dùng map local, GET ở node khác có thể 404 — vấn đề lưu trữ, **không phải lỗi builder**.

Inspect URI:

```bash
curl -sS \
  'http://localhost:8080/api/v1/links/inspect?page=2&sort=desc'
```

Body minh họa (thứ tự JSON/query params không phải contract):

```json
{
  "requestWithQuery":
      "http://localhost:8080/api/v1/links/inspect?page=2&sort=desc",
  "requestWithoutQuery":
      "http://localhost:8080/api/v1/links/inspect",
  "contextRoot": "http://localhost:8080",
  "notesCollection": "http://localhost:8080/api/v1/notes",
  "pageThree":
      "http://localhost:8080/api/v1/links/inspect?page=3&sort=desc"
}
```

Lấy link collection từ endpoint khác:

```bash
curl -i 'http://localhost:8080/api/v1/links/catalog'
```

Kỳ vọng **303 See Other**, `Location: http://localhost:8080/api/v1/notes`. Trong demo chỉ có POST collection, chưa khai báo GET collection, nên **client theo Location bằng GET có thể nhận 405**. Đây là giới hạn ví dụ redirect không có list endpoint; trong sản phẩm thực tế, chỉ redirect tới target hỗ trợ method phù hợp, hoặc thêm GET collection. Để không tạo redirect tới endpoint chưa hỗ trợ GET, bổ sung GET handler khi dùng chức năng này; xem bài test minh họa chỉ assert Location, không giả định GET thành công.

## 10. Kiểm thử MockMvc cho URI/Location

MockMvc tạo Servlet request giả lập, Spring MVC gọi controller và request context được bind trong lần xử lý. Dùng `MockMvcRequestBuilders`, `jsonPath`, `header` để kiểm tra cả success và failure. Tạo **`src/test/java/demo/urilinks/UriLinksApplicationTests.java`**:

```java
package demo.urilinks;

import java.net.URI;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UriLinksApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void createdLocationUsesCurrentPathWithoutOldQuery()
            throws Exception {

        MvcResult result = mvc.perform(
                post("/api/v1/notes?notify=true")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"title":"URI Builder"}
                        """))
            .andExpect(status().isCreated())
            .andReturn();

        String rawLocation = result.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(rawLocation);

        URI location = URI.create(rawLocation);
        assertTrue(location.isAbsolute());
        assertTrue(location.getPath().matches(
                "/api/v1/notes/[0-9]+"));
        assertEquals(null, location.getRawQuery());

        mvc.perform(get(location.getRawPath()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("URI Builder"));
    }

    @Test
    void inspectDistinguishesQueryAndRequestUri()
            throws Exception {

        mvc.perform(get(
                "/api/v1/links/inspect?page=2&sort=desc"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.requestWithQuery")
                .value(org.hamcrest.Matchers.containsString(
                    "?page=2&sort=desc")))
            .andExpect(jsonPath("$.requestWithoutQuery")
                .value(org.hamcrest.Matchers.endsWith(
                    "/api/v1/links/inspect")))
            .andExpect(jsonPath("$.notesCollection")
                .value(org.hamcrest.Matchers.endsWith(
                    "/api/v1/notes")))
            .andExpect(jsonPath("$.pageThree")
                .value(org.hamcrest.Matchers.containsString(
                    "page=3")));
    }

    @Test
    void contextRootIncludesServletContextPath()
            throws Exception {

        mvc.perform(get(
                "/shop/api/v1/links/inspect?page=2")
                    .contextPath("/shop")
                    .servletPath("/api/v1/links/inspect"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.contextRoot")
                .value(org.hamcrest.Matchers.endsWith("/shop")))
            .andExpect(jsonPath("$.notesCollection")
                .value(org.hamcrest.Matchers.endsWith(
                    "/shop/api/v1/notes")));
    }

    @Test
    void explicitCurrentOriginComesFromServletRequest()
            throws Exception {

        MvcResult result = mvc.perform(
                post("/api/v1/notes")
                    .scheme("https")
                    .serverName("edge.example.org")
                    .serverPort(443)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"title":"HTTPS"}
                        """))
            .andExpect(status().isCreated())
            .andReturn();

        String location = result.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(location);
        URI uri = URI.create(location);

        assertEquals("https", uri.getScheme());
        assertEquals("edge.example.org", uri.getHost());
        assertTrue(uri.getPath().startsWith("/api/v1/notes/"));
    }

    @Test
    void invalidTitleIsNotPersisted()
            throws Exception {

        mvc.perform(post("/api/v1/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"   "}
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unknownNoteReturns404() throws Exception {
        mvc.perform(get("/api/v1/notes/999999999"))
            .andExpect(status().isNotFound());
    }
}
```

Chạy:

```bash
./gradlew test
```

Các test được **thiết kế để pass** trên Spring Boot 3.5 với dependency và mã demo nêu trên. Đây là **kỳ vọng từ code đã rà soát**, không phải kết quả đã chạy Gradle. Một vài assertion dùng `Matchers.endsWith`/`containsString` để tránh phụ thuộc cổng/host mặc định trong MockMvc.

**Kiểm thử quan trọng:** status 201 không đủ. Phải kiểm tra Location thực sự có URI của member, không giữ query cũ, resource GET được truy cập và link respect context path. Test “host/scheme” không chứng minh forwarded-header trust an toàn; nó chỉ chứng minh builder phản ánh thông tin mà Servlet request cung cấp.

## 11. Test thuần với MockHttpServletRequest khi không cần controller

Với `spring-test`, có thể tạo request giả rồi gọi builder dạng nhận tham số, không cần `RequestContextHolder`:

```java
import java.net.URI;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

MockHttpServletRequest request =
        new MockHttpServletRequest("GET", "/shop/api/v1/notes");

request.setScheme("https");
request.setServerName("example.org");
request.setServerPort(443);
request.setContextPath("/shop");
request.setQueryString("page=2&sort=desc");

URI withQuery = ServletUriComponentsBuilder
        .fromRequest(request)
        .build()
        .toUri();

URI withoutQuery = ServletUriComponentsBuilder
        .fromRequestUri(request)
        .build()
        .toUri();

System.out.println(withQuery);
System.out.println(withoutQuery);
```

Đây là **fragment trong test method**, vì `MockHttpServletRequest` cần `spring-test` dependency (có qua starter-test), chưa phải file độc lập với `main`. Với những fields như trên, output mong đợi:

```text
https://example.org/shop/api/v1/notes?page=2&sort=desc
https://example.org/shop/api/v1/notes
```

Khi xây fake request, phải bảo đảm `requestURI`, `contextPath`, `servletPath` và `queryString` nhất quán với request thực, đặc biệt khi test mapping prefix. Trong Boot app, integration tests cần thực hiện sau khi filter/proxy đã được cấu hình đúng.

## 12. Reverse proxy và forwarded headers — trọng tâm bảo mật

Trong nhiều triển khai, client không gọi trực tiếp Tomcat; nó gọi load balancer hoặc API gateway:

```text
Client:
  https://api.example.org/api/v1/notes

Reverse proxy:
  TLS termination; forward đến http://10.0.0.5:8080/api/v1/notes
  thêm các headers đại diện client origin (theo trust policy)

Spring Boot backend:
  HttpServletRequest nội bộ thấy http://10.0.0.5:8080
  nếu không cấu hình trusted forwarding

Location sai:
  http://10.0.0.5:8080/api/v1/notes/42

Location mong muốn:
  https://api.example.org/api/v1/notes/42
```

Các headers thường thấy:

- `Forwarded: proto=https;host=api.example.org` (chuẩn RFC 7239).
- `X-Forwarded-Proto: https`.
- `X-Forwarded-Host: api.example.org`.
- `X-Forwarded-Port: 443`.
- `X-Forwarded-Prefix: /api` tùy proxy routing.
- `X-Forwarded-For` liên quan client address, không nên tự dùng nó làm host public.

### 12.1. Tại sao builder không tự đọc raw forwarded headers?

**Từ Spring Framework 5.1**, `ServletUriComponentsBuilder` không tự diễn giải `Forwarded` hay `X-Forwarded-*` từ request headers. Spring khuyến nghị dùng **`ForwardedHeaderFilter`** hoặc container forwarding support để request wrapper/Servlet container phản ánh origin đã xác minh trước khi builder chạy.

Điều này giúp tách rõ ai tin forwarded data và ai chỉ xây URI từ request, nhưng **không tự bảo đảm an toàn**. Nếu bạn cấu hình filter tin headers trực tiếp từ internet, attacker vẫn có thể điều khiển host/scheme của generated URLs.

### 12.2. Spring Boot `server.forward-headers-strategy`

Với Spring Boot 3.5:

```properties
# Chọn MỘT chiến lược phù hợp sau khi đã có trusted proxy.
server.forward-headers-strategy=framework
```

Các giá trị:

| Giá trị | Ý nghĩa |
| --- | --- |
| `none` | Boot không tự áp dụng forwarding support; ứng dụng thấy thông tin request/connector đã có |
| `native` | Dùng hỗ trợ forwarded headers của Servlet container (ví dụ Tomcat RemoteIpValve); khả năng support từng header phụ thuộc container |
| `framework` | Dùng Spring Framework `ForwardedHeaderFilter` cho Servlet MVC |

Nếu proxy dùng `X-Forwarded-Prefix` hoặc những semantics phức tạp, `framework` có thể cần thiết vì native container support không bao quát mọi header. Boot docs nêu rằng với proxy thiết lập `X-Forwarded-For`/`X-Forwarded-Proto`, `native` có thể đã đủ. **Không chạy đồng thời cả native và framework forwarding chỉ theo cảm tính**; điều đó có thể khiến host/scheme/prefix bị áp dụng hai lần hoặc sai.

Khi dùng Tomcat và terminate HTTPS ở reverse proxy, tài liệu Boot cũng nhắc cấu hình `server.tomcat.redirect-context-root=false` trong các trường hợp cần để `X-Forwarded-Proto` được tôn trọng trước container redirects.

### 12.3. Ranh giới tin cậy mới là điều quyết định

Reverse proxy/edge phải:

1. **Xóa/ghi đè** tất cả `Forwarded` và `X-Forwarded-*` do client không đáng tin gửi đến.
2. Chỉ **thêm headers mới** dựa trên thông tin đã được proxy xác thực/quan sát.
3. Chặn truy cập trực tiếp từ internet vào backend nếu backend tin forwarded headers.
4. Kiểm soát hostnames, scheme, ports và trusted proxy IPs; chỉ chấp nhận public origins hợp lệ.
5. Test cả chuỗi proxy/gateway/Ingress với multi-hop forwarding và `X-Forwarded-Prefix`.
6. Không dùng thông tin forwarded do client cung cấp để xây password reset links, email verification links hoặc OAuth callback URIs khi chưa có strict public-base policy.

Spring `ForwardedHeaderFilter` có thể được đặt `removeOnly=true` để **loại bỏ** forwarded headers nhưng **không sử dụng** giá trị của chúng. Chế độ này phù hợp nếu không có trusted proxy hoặc muốn bảo đảm forwarded headers bên ngoài không ảnh hưởng request URI.

### 12.4. Host-header poisoning

Ngay cả không có `X-Forwarded-Host`, HTTP `Host` được client gửi có thể không đáng tin trong một số cấu hình routing. Một server trả:

```http
HTTP/1.1 201 Created
Location: https://evil.example/api/v1/notes/42
```

nếu dựng host từ request không được validation có thể vô tình tạo liên kết tới domain của attacker.

**Khuyến nghị an toàn:**

- Với `Location` self-link ngay trong response tới một trusted gateway được cấu hình đúng, request-derived URL có thể hợp lý.
- Với links **gửi ra email**, password reset, magic login, OAuth redirect URI và các URL mang quyền truy cập, dùng **canonical public base URI được cấu hình từ server**, không suy ra từ raw Host/Forwarded.
- Hạn chế allowed hosts ở gateway/web server và kiểm tra request host nếu business yêu cầu.
- Không nhầm `ServletUriComponentsBuilder` với open redirect validator; builder chỉ xử lý cấu trúc URI.

## 13. Khi nào dùng URI tuyệt đối, URI tương đối và canonical base?

| Tình huống | Lựa chọn thường hợp lý |
| --- | --- |
| `Location` cho POST tạo resource trong API sau trusted proxy | `fromCurrentRequestUri()` + path segment |
| Link tới endpoint khác cùng Servlet app | `fromCurrentContextPath()` + route |
| Pagination giữ filter/sort | `fromCurrentRequest()` + `replaceQueryParam` |
| Có servlet mapping prefix `/main/*` | `fromCurrentServletMapping()`, xem tương thích mapping |
| Sinh URL khi không có HTTP request (scheduler/email) | Canonical base URI từ config |
| Password reset/OAuth callback, signed links | Canonical origin + strict allowlist/policy |
| SPA chỉ điều hướng trong cùng origin | Root-relative paths có thể giảm lệ thuộc host, nhưng phải xử lý context path |
| Hypermedia links (HAL/JSON), versioned API | Builder hoặc `MvcUriComponentsBuilder` theo mapping thật |
| Link tới website ngoài | Không build từ raw user URL; partner ID/allowlist và validation riêng |

Ví dụ dùng canonical base `https://api.example.org` cho tác vụ offline:

```java
URI base = URI.create("https://api.example.org");

URI resource = UriComponentsBuilder
        .fromUri(base)
        .pathSegment("api", "v1", "notes", "{id}")
        .encode()
        .buildAndExpand(42)
        .toUri();
```

Code fragment này **không cần Servlet request**, nên dùng trong message worker hoặc email service thuận tiện. Trong app thực, base nên được lấy từ **validated configuration properties**, không từ một request header không đáng tin. Nếu external base chứa prefix `/shop`, kiểm soát việc append route để tránh mất/nhân đôi prefix.

## 14. URI API version: `/api/v1` và HATEOAS links

Vì bài thuộc nhóm **URI và phiên bản API**, việc đặt version trong path ảnh hưởng cách build link.

Ví dụ:

```text
POST /api/v1/notes
GET  /api/v1/notes/{id}

POST /api/v2/notes
GET  /api/v2/notes/{id}
```

Nếu controller V1 và V2 nhận request ở collection riêng, `fromCurrentRequestUri().pathSegment("{id}")` sẽ tự lấy đúng **collection path hiện tại**. Nhưng nếu POST V2 tạo resource thuộc route GET khác (`/api/v2/documents/{id}`), bạn phải build theo mapping tài nguyên thực, không chỉ append ID.

`fromCurrentContextPath()` hữu ích khi muốn xây link cụ thể:

```java
URI v2Note = ServletUriComponentsBuilder
        .fromCurrentContextPath()
        .pathSegment("api", "v2", "notes", "{id}")
        .encode()
        .buildAndExpand(42)
        .toUri();
```

**Không hardcode nhầm v1** trong Location của response V2. Với versioning theo header/media type thay vì URL path, URI có thể không mang version; khi đó link contract cần thuyết minh `Accept`/media type hoặc cách version negotiation tương ứng.

### 14.1. `MvcUriComponentsBuilder` khi muốn dựa vào controller mappings

Spring MVC có class **`MvcUriComponentsBuilder`**, giúp tạo link dựa trên các `@RequestMapping`/`@GetMapping` thay vì viết lại mọi route string. Nó hữu ích khi API được refactor path và muốn compiler/framework hỗ trợ giữ liên kết.

Ví dụ fragment theo Javadoc:

```java
UriComponents components = MvcUriComponentsBuilder
        .fromMethodName(
                NoteController.class, "find", 42L)
        .build();

URI resourceUri = components.encode().toUri();
```

Điều kiện: method `find(long id)` ở ví dụ đã đánh dấu `@GetMapping("/{id}")` và `@PathVariable`; Spring tìm metadata mapping. Khi có class-level `@RequestMapping("/api/v1/notes")`, kết quả gắn với route đó theo context/base URL phù hợp.

Một lựa chọn khác dùng `MvcUriComponentsBuilder.on(...)` tạo proxy invocation:

```java
UriComponents components = MvcUriComponentsBuilder
        .fromMethodCall(
                MvcUriComponentsBuilder.on(NoteController.class)
                        .find(42L))
        .build();

URI uri = components.encode().toUri();
```

**Lưu ý giới hạn:** các kỹ thuật proxy invocation có ràng buộc về return type, class/method proxyability và signature. Ví dụ `find` trả record `Note` (record là final), nên **không cam kết proxy-call fragment chạy đúng như mong đợi** với return type final. Hãy dùng cách `fromMethodName` hoặc refactor endpoint trả một kiểu proxy-compatible nếu muốn dùng method-call API. Hai fragment ở phần này không cần cho runnable demo 9.

Không suy ra `MvcUriComponentsBuilder` tự nhận raw forwarded headers an toàn; nó cũng cần request/proxy trust policy giống `ServletUriComponentsBuilder`.

## 15. Pagination và Link header

Đối với một collection GET, API có thể trả `Link` header theo kiểu:

```http
HTTP/1.1 200 OK
Link: <https://api.example.org/api/v1/notes?page=3&size=20>; rel="next"
Content-Type: application/json
```

`ServletUriComponentsBuilder.fromCurrentRequest().replaceQueryParam("page", ...)` giúp dựng URI. Nhưng để tránh lộ query credentials hoặc giữ parameter không được phép, một API production nên chọn rõ những fields được giữ trong link.

Fragment:

```java
URI next = ServletUriComponentsBuilder
        .fromCurrentRequestUri()
        .queryParam("page", 3)
        .queryParam("size", 20)
        .build()
        .toUri();

return ResponseEntity.ok()
        .header(HttpHeaders.LINK,
                "<" + next + ">; rel=\"next\"")
        .body(pageData);
```

Đây là **fragment trong handler**, cần `HttpHeaders`, `pageData` và logic phân trang do ứng dụng định nghĩa. Nếu `page` là số ở trang cuối, không nên tạo link next vô nghĩa. Hãy đảm bảo `page/size` không âm hoặc vượt giới hạn và kết quả sort ổn định.

Có thể dùng `org.springframework.http.HttpHeaders` APIs và Spring HATEOAS nếu ứng dụng đã dùng hypermedia; nhưng **URI builder tự nó không quản lý quan hệ resource, pagination semantics hoặc permission**.

## 16. Những sai lầm phổ biến

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Location chứa `?debug=true` từ POST | Dùng `fromCurrentRequest()` để xây resource con | Dùng `fromCurrentRequestUri()` hoặc reset query |
| URI thành `/api/v1/links/catalog/notes/42` | Append path vào request URI của endpoint khác | Dùng context path + resource route |
| Sau deploy context `/shop`, link thiếu `/shop` | Dùng hardcoded `http://.../api/...` | Dùng `fromCurrentContextPath()` |
| URL bị `/shop/shop/api` | Tự thêm context path lần nữa | Chỉ append route sau context |
| URI chứa `http://10.x.x.x:8080` | TLS termination ở proxy nhưng forwarded headers chưa được trust/apply | Cấu hình trusted proxy, forwarding strategy |
| Location có domain attacker | Tin Host/Forwarded từ client | Validate allowed hosts, strip forwarding, canonical base |
| Ký tự `/` trong slug đổi route | Nối input vào `path` | `pathSegment("{slug}").encode().buildAndExpand`; cân nhắc ID an toàn |
| URI chứa `%252F` thay vì `%2F` | Double-encode giá trị đã escaped | Chọn raw-value encoding contract |
| Query có `page=2&page=3` | Dùng `queryParam` thay vì replace | `replaceQueryParam("page",3)` |
| `fromCurrent...` lỗi trong async/job | Không có request context | Dùng explicit base hoặc truyền URI an toàn |
| URL có scheme sai phía sau HTTPS proxy | `server.forward-headers-strategy` sai hoặc forwarded header chưa được trusted | Kiểm tra proxy/backend headers và Boot strategy |
| URL thiếu servlet prefix `/main` | Dùng context path khi route thực cần servlet mapping | Xem `fromCurrentServletMapping` và mapping |
| Test chỉ assert 201 | Chưa kiểm tra Location hay GET target | Assert URI path/query/host và follow GET |
| Redirect POST mang payload nhạy cảm | Chọn 307/308 sang target không tin cậy | Không cho input quyết định redirect; kiểm tra status |
| JSON link chính xác ở localhost nhưng sai production | Chưa test reverse proxy/context path | HTTP integration sau gateway |
| URL dùng external host nhưng business chỉ cần relative path | Lạm dụng absolute links từ Host | Cân nhắc root-relative path đã kiểm soát |

**Chẩn đoán hợp lý:** request thật → Servlet fields (scheme, host, port, context, URI, query) → forwarded/proxy handling → factory method được chọn → path/query modifications → encoding → HTTP output → URI client nhận.

## 17. Những lưu ý về URI canonicalization và bảo mật

### 17.1. Open redirect

`ServletUriComponentsBuilder` không mặc nhiên chống open redirect. Nếu ứng dụng làm:

```java
@GetMapping("/jump")
String jump(@RequestParam String next) {
    return "redirect:" + next;
}
```

Đó là lỗi **tin đích từ user**, không phải lỗi builder. Giải pháp an toàn thường là nhận mã đích hợp lệ (`dashboard`, `help`) rồi ánh xạ sang route server-defined, hoặc exact allowlist cho đối tác ngoài.

### 17.2. Host header và absolute links

Nếu bạn xây absolute URL từ request rồi đưa nó vào email reset mật khẩu, host đầu vào có thể ảnh hưởng link trong thư. Ưu tiên **canonical public URL từ cấu hình**, strict host validation, HTTPS và không nhúng secret/query token tùy tiện vào logs.

### 17.3. CRLF, header injection và encoded path

URI builders có encoding/parsing nhưng không biến raw string đầu vào thành dữ liệu đáng tin. Tránh gửi untrusted raw string vào `Location`/`Link`, kiểm tra scheme/host/path theo contract và chỉ dùng typed `URI` đã xác minh. Với reserved characters trong path variable, chính sách container/proxy về encoded slash, semicolon/matrix params và path normalization có thể ảnh hưởng routing/authorization; test trên gateway thực tế.

### 17.4. URI xây cho client không đồng nghĩa truy cập được resource

Một Location có cấu trúc đúng nhưng tài nguyên chưa commit vào DB, node khác không nhìn thấy state hoặc Security cấm GET sẽ vẫn lỗi. Cần đảm bảo lifecycle, transaction, permission và retention phù hợp.

`ResponseEntity.created(uri)` tự set 201/Location, **không** chứng minh resource đã persist hoặc route GET đã được công bố. Test cả hai.

## 18. Testing qua reverse proxy và container thật

MockMvc cho phép thử builder với request fields nhưng không tự xác minh **ngăn attacker gửi forwarded headers** hoặc TLS termination thật.

Với staging sau gateway:

1. Gửi `POST /api/v1/notes` vào **public URL HTTPS**.
2. Xác nhận `201 Created` và `Location` có **scheme=https**, đúng public host, port và context/prefix.
3. Follow GET Location từ bên ngoài gateway (có auth nếu cần), xác minh 200 hoặc trạng thái hợp đồng đúng.
4. Gửi `Host` không cho phép tại gateway để xác minh bị từ chối/normalize, không xuất hiện trong `Location`.
5. Kiểm tra `Forwarded` và `X-Forwarded-*` client tự gửi **bị edge proxy xóa/ghi đè**.
6. Test `X-Forwarded-Prefix` khi gateway thêm/loại path prefix.
7. Với nhiều nodes, đảm bảo generated Location không chứa backend IP và resource GET hoạt động khi đi vào node khác.
8. Xác minh access logs và tracing không lưu bearer tokens hoặc query secrets.
9. Đánh giá canonical origin chính thức cho links chạy ngoài request (email, scheduled jobs, external callbacks).
10. Không bật `server.forward-headers-strategy=framework` trên backend exposed trực tiếp ra internet nếu forwarded headers không được lọc.

Phân biệt **NATIVE vs FRAMEWORK** bằng integration tests trên servlet container thực, nhất là khi Tomcat/Jetty/Undertow và gateway có hành vi khác nhau.

## 19. Gợi ý chọn API theo nhu cầu

| Bạn muốn... | Bắt đầu từ... |
| --- | --- |
| Build URI y hệt HTTP request bao gồm query | `fromCurrentRequest()` |
| Build URI request path hiện tại không query | `fromCurrentRequestUri()` |
| Link sang route khác cùng context | `fromCurrentContextPath()` |
| Link gắn servlet mapping prefix | `fromCurrentServletMapping()` |
| Không có ambient current request nhưng có servlet request | `fromRequest(request)` / `fromRequestUri(request)` |
| Không có HTTP request (email, batch job) | `UriComponentsBuilder.fromUriString(configuredBase)` |
| Thêm resource ID | `pathSegment("{id}").encode().buildAndExpand(id)` |
| Giữ query khác, thay page | `replaceQueryParam("page",n)` |
| Bỏ query cũ, tạo query đã kiểm duyệt | `fromCurrentRequestUri().queryParam(...)` |
| Trả 201 với Location | `ResponseEntity.created(uri).body(...)` |
| Dựa theo annotation routes | `MvcUriComponentsBuilder`, chú ý proxy/return-type |
| Deploy sau trusted reverse proxy | `ForwardedHeaderFilter` hoặc container support theo Boot strategy |
| URL canonical mang tính bảo mật | Explicit validated public base từ config |

## 20. Checklist cho lập trình và triển khai

- [ ] Chọn đúng factory method: `fromCurrentRequest()` khi cần query, `fromCurrentRequestUri()` khi không cần.
- [ ] Không append vào current request path nếu resource target thuộc endpoint khác.
- [ ] Khi route thay đổi/khác version, dùng context base + route được kiểm soát.
- [ ] Dùng `pathSegment`/URI templates và encode variables đúng thứ tự.
- [ ] Không double encode input đã escaped; phân biệt raw values và pre-encoded components.
- [ ] Không đặt raw password/token/credential vào URI/query/Location.
- [ ] Có 201 Location trỏ tới resource thực sự truy cập được theo API contract.
- [ ] Context path/servlet mapping prefix/HTTPS/port được test.
- [ ] Spring Boot forwarding strategy được chọn có chủ đích, không trộn native và framework tùy tiện.
- [ ] Edge proxy strip/overwrite untrusted `Forwarded`/`X-Forwarded-*`.
- [ ] Gateway bảo vệ allowed hosts; absolute email/OAuth/reset links dùng canonical base.
- [ ] Không truy cập request-bound builder từ background thread khi không có request context.
- [ ] Có integration tests cho pagination URL, Location query stripping và follow GET.
- [ ] API versioning theo path/media type tương thích link generation.
- [ ] Security và authorization cho URI được sinh ra vẫn được kiểm tra độc lập.

## 21. Bài tập tự đánh giá

1. Từ request `https://example.org/shop/api/v1/notes?page=2`, hãy viết outputs của `fromCurrentRequest()`, `fromCurrentRequestUri()`, `fromCurrentContextPath()`.
2. Một endpoint `POST /api/v1/notes?notify=true` tạo ID 7. Vì sao `fromCurrentRequestUri().pathSegment("{id}")` phù hợp hơn `fromCurrentRequest().pathSegment("{id}")`?
3. Trong `GET /api/v1/links/inspect`, hãy tạo link tới `/api/v1/notes` mà không bị prefix `/api/v1/links/inspect`.
4. Khi ứng dụng chạy dưới `/shop`, vì sao `fromCurrentContextPath().path("/shop/api/v1/notes")` sai?
5. So sánh `path("/" + userSlug)` với `pathSegment("{slug}").encode().buildAndExpand(userSlug)` khi slug chứa ký tự `/`.
6. Dùng `queryParam("page",3)` với URL đã có `page=2` có tác động gì? Sửa bằng `replaceQueryParam`.
7. Vì sao `RequestContextHolder` không luôn tồn tại trong `@Async` hoặc scheduled jobs? Bạn sẽ sinh URL cho email như thế nào?
8. Reverse proxy client dùng HTTPS, backend HTTP: URI builder trả host nội bộ. Phải sửa ở proxy/Boot lớp nào trước khi code builder chạy?
9. Tại sao không được tin `X-Forwarded-Host` từ internet? Phân biệt remove-only mode và trusted proxy mode.
10. Tại sao `ServletUriComponentsBuilder` không thay thế URL allowlist validator khi app cho phép external redirect?
11. Viết MockMvc test nhận Location sau POST và follow GET đúng ID. Vì sao chỉ assert status 201 chưa đủ?
12. Nếu API V2 đặt path `/api/v2/jobs/{id}` nhưng POST gọi `/api/v2/imports`, dùng factory nào và append route như thế nào?
13. Phân biệt `MvcUriComponentsBuilder#fromMethodName` và `fromMethodCall`; vì sao return type final có thể gây giới hạn với proxy?
14. Nếu application cần link tuyệt đối trong password reset email, nên lấy base URL từ request Host hay server config? Giải thích threat model.
15. Khi gateway thay prefix `/internal` bằng `/public-api`, cần kiểm tra những gì để Location không có internal prefix?

## 22. Tài liệu chính thức

- [Spring Framework 6.2 — URI Links](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-uri-building.html): `UriComponentsBuilder`, `ServletUriComponentsBuilder`, `MvcUriComponentsBuilder`, URI templates và encoding.
- [Spring Framework 6.2 — ServletUriComponentsBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html): toàn bộ `fromCurrent*` và `fromXxx(HttpServletRequest)`.
- [Spring Framework 6.2 — UriComponentsBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html): `path`, `pathSegment`, `encode`, `queryParam`, `buildAndExpand`.
- [Spring Framework 6.2 — Servlet Filters / Forwarded Headers](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html): `ForwardedHeaderFilter`, security boundary và `X-Forwarded-Prefix`.
- [Spring Boot 3.5 — Embedded Servers / Forwarded Headers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): `server.forward-headers-strategy`, proxy support và Tomcat.
- [Spring Framework 6.2 — HTTP ResponseEntity](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/ResponseEntity.html): 201 Created và Location header.
- [Spring Framework 6.2 — Path Matching](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-path.html): context/servlet mapping và an toàn đường dẫn.
- [RFC 3986 — Uniform Resource Identifier Syntax](https://www.rfc-editor.org/rfc/rfc3986.html): scheme, authority, path, query và fragment.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): `Location`, 201/303 và redirect semantics.
