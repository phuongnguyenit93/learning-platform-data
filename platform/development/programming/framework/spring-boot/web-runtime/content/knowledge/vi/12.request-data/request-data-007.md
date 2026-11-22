# Đọc HttpServletRequest trong MVC và ServerWebExchange trong WebFlux

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của **HttpServletRequest** trong Spring MVC và **ServerWebExchange** trong Spring WebFlux khi truy cập dữ liệu của một HTTP request.
2. Lấy method, URI/path, query parameters, headers, cookies, thông tin kết nối, thuộc tính request và session bằng API phù hợp với từng web stack.
3. Phân biệt **đọc metadata** với **tiêu thụ request body**, hiểu giới hạn đọc body một lần và lỗi khi filter đọc body trước controller.
4. Biết khi nào nên dùng @RequestParam, @PathVariable, @RequestHeader, @CookieValue, @RequestBody thay vì truy cập request object trực tiếp.
5. Xử lý request body theo hướng Servlet InputStream/Reader trong MVC và Flux<DataBuffer>/Mono<T> trong WebFlux.
6. Hiểu request lifecycle, thread-local, bất đồng bộ, backpressure, cancellation, pooling DataBuffer, session và quyền sở hữu tài nguyên.
7. Viết ví dụ chạy được với **Spring Boot 3.3.x / Spring Framework 6.1.x / Java 17+**, tách riêng MVC và WebFlux, kiểm thử bằng MockMvc hoặc WebTestClient.
8. Tránh những lỗi thường gặp khi có reverse proxy, multipart, form data, content-type, security filter và dữ liệu nhạy cảm.

**Ngữ cảnh cha: Dữ liệu yêu cầu — Spring Boot web-runtime.** Trọng tâm là cách đọc HTTP request từ hai mô hình, không phải cách viết một HTTP client hoặc cách cài cả hai server stack trong cùng một ứng dụng.

## 1. Vì sao Spring cung cấp hai kiểu request khác nhau?

HTTP request gồm request line (hoặc các pseudo-headers tương ứng trong HTTP/2), headers, cookies, query string và body. Cả Spring MVC và WebFlux đều phải đưa dữ liệu này tới controller, nhưng chúng được xây dựng trên **hai mô hình xử lý I/O khác nhau**.

- **Spring MVC:** dựa trên Servlet API. Container như Tomcat, Jetty, Undertow cung cấp HttpServletRequest và HttpServletResponse cho từng HTTP request. Mô hình phổ biến là một servlet worker thread xử lý request đồng bộ; MVC cũng hỗ trợ các phương án bất đồng bộ trên Servlet.
- **Spring WebFlux:** dựa trên reactive HTTP abstraction. WebFlux controller có thể nhận **ServerWebExchange**, truy cập ServerHttpRequest, ServerHttpResponse, request attributes, WebSession và các publisher cho body, phù hợp với xử lý reactive/non-blocking.
- **Spring Boot:** chọn loại ApplicationContext và web runtime theo dependencies/config. Nếu có cả starter-web và starter-webflux, Boot 3.3 thường ưu tiên **Spring MVC/Servlet** mặc định.

Hai API không phải hai tên gọi của cùng một object. Không nên truyền HttpServletRequest vào annotated WebFlux controller rồi mong Reactor Netty tự tạo Servlet request. Ngược lại, một Spring MVC controller thường không có ServerWebExchange làm method argument.

### Luồng Spring MVC

~~~text
Client
   |
   v
Servlet container (Tomcat/Jetty/Undertow)
   |
   v
jakarta.servlet.http.HttpServletRequest
   |
   v
Servlet Filter chain
   |
   v
DispatcherServlet
   |
   v
HandlerMapping -> HandlerAdapter
   |
   v
Spring MVC controller
   |
   +-- @RequestParam / @RequestHeader / @RequestBody
   +-- Hoặc trực tiếp HttpServletRequest
~~~

### Luồng Spring WebFlux

~~~text
Client
   |
   v
HTTP runtime (Reactor Netty hoặc reactive adapter)
   |
   v
ServerHttpRequest + ServerHttpResponse
   |
   v
ServerWebExchange
   |
   v
WebFilter chain
   |
   v
DispatcherHandler
   |
   v
HandlerMapping -> HandlerAdapter
   |
   v
Spring WebFlux controller
   |
   +-- @RequestParam / @RequestHeader / @RequestBody
   +-- Hoặc trực tiếp ServerWebExchange
~~~

WebFlux có thể được chạy trên một Servlet 3.1+ container thông qua adapter phù hợp, nhưng API chuẩn của **WebFlux controller** vẫn là các abstraction reactive. Không suy luận rằng “chạy trên Tomcat” chắc chắn có HttpServletRequest trong mọi controller.

## 2. Bảng so sánh nhanh

| Câu hỏi | Spring MVC | Spring WebFlux |
|---|---|---|
| Đối tượng ở controller | HttpServletRequest | ServerWebExchange hoặc ServerHttpRequest |
| Package | jakarta.servlet.http | org.springframework.web.server và org.springframework.http.server.reactive |
| HTTP method | request.getMethod() trả String | exchange.getRequest().getMethod() trả HttpMethod |
| URI/path | getRequestURI(), getContextPath(), getServletPath() | getRequest().getURI(), getRequest().getPath() |
| Query parameters | getParameter(), getParameterValues(), getParameterMap() | getRequest().getQueryParams() |
| Header đầu tiên | getHeader("X-Id") | getHeaders().getFirst("X-Id") |
| Nhiều giá trị header | getHeaders("X-Id") (Enumeration) | getHeaders().get("X-Id") (List) |
| Cookies | getCookies() (Cookie[] hoặc null) | getCookies() (MultiValueMap<String,HttpCookie>) |
| Request attributes | getAttribute(), setAttribute() | getAttributes(), getAttribute(), getRequiredAttribute() |
| Session | getSession(false), getSession() | getSession() trả Mono<WebSession> |
| Principal | getUserPrincipal() | getPrincipal() trả Mono<T extends Principal> |
| Remote address | getRemoteAddr(), getRemotePort() | getRequest().getRemoteAddress() |
| Raw request body | ServletInputStream hoặc BufferedReader | Flux<DataBuffer> qua getBody() |
| Typed JSON body | @RequestBody + HttpMessageConverter | @RequestBody + HttpMessageReader/codecs |
| Form data | Servlet request parameter parsing | exchange.getFormData() trả Mono<MultiValueMap<...>> |
| Multipart | Part, MultipartFile, MultipartResolver | Part/FilePart, getMultipartData(), Flux<PartEvent> |
| Filter | jakarta.servlet.Filter, OncePerRequestFilter | WebFilter |
| Context lan truyền | Servlet request context, thread-locals có giới hạn | Reactive Context và request/exchange data |
| Ghi response | HttpServletResponse hoặc return value | ServerHttpResponse hoặc reactive return value |

Không hiểu lầm rằng **ServerWebExchange chỉ chứa request**. Exchange còn gắn response, attributes, session, principal và các công cụ điều phối cho một HTTP exchange.

## 3. MVC: dùng HttpServletRequest trong controller

Trong Spring Boot 3.3 và Spring Framework 6, import chính xác:

~~~java
import jakarta.servlet.http.HttpServletRequest;
~~~

**Không** dùng javax.servlet.http.HttpServletRequest trong một dự án Boot 3.x: từ Spring Framework 6, hệ Servlet API đã chuyển sang namespace **jakarta.servlet**.

Một controller MVC nhận request trực tiếp:

~~~java
@GetMapping("/inspect")
Map<String, String> inspect(HttpServletRequest request) {
    return Map.of(
            "method", request.getMethod(),
            "uri", request.getRequestURI()
    );
}
~~~

Đây là một snippet đặt trong @RestController có imports phù hợp, **không phải toàn bộ file Java độc lập**. Spring MVC method argument resolver cung cấp HttpServletRequest hiện tại khi handler được gọi.

Truy cập request object có ích khi bạn cần nhiều trường hợp metadata hoặc API Servlet chưa được một annotation chuyên biệt bao phủ. Tuy nhiên, để lấy đúng một query parameter, một path variable hay một header, annotation thường làm controller ngắn gọn và test dễ hơn.

### Các method Servlet dễ sử dụng

~~~java
String method = request.getMethod();
String uri = request.getRequestURI();
String query = request.getQueryString();
String host = request.getServerName();
int port = request.getServerPort();
String contentType = request.getContentType();
String agent = request.getHeader("User-Agent");
String firstTag = request.getParameter("tag");
String[] tags = request.getParameterValues("tag");
~~~

Tất cả thuộc về môi trường có biến request kiểu HttpServletRequest. Giá trị query/header/parameter có thể **null**; getParameterValues có thể null khi không có key. Không cho tất cả vào Map.of ngay nếu không kiểm tra null vì Map.of không cho phép null values.

- getRequestURI() trả phần URI request của server, không bao gồm query string.
- getQueryString() trả phần query string **chưa decode theo cách của getParameter**, hoặc null khi không có query.
- getParameter("tag") lấy một giá trị; nếu key lặp nhiều lần, dùng getParameterValues("tag") để tránh mất dữ liệu.
- getServerName()/getServerPort() phản ánh request/container/proxy theo ngữ cảnh, **không phải** lúc nào cũng là địa chỉ public thật đã được khách hàng gọi.

## 4. Path, context path và query trong Servlet API

Ví dụ client gọi:

~~~http
GET /shop/api/orders/42?include=items&tag=java&tag=spring HTTP/1.1
Host: localhost:8080
~~~

Giả sử server.servlet.context-path=/shop và route MVC là /api/orders/{id}. Những trường thường gặp:

| API | Giá trị minh họa |
|---|---|
| getRequestURI() | /shop/api/orders/42 |
| getContextPath() | /shop |
| getQueryString() | include=items&tag=java&tag=spring |
| getParameter("include") | items |
| getParameterValues("tag") | ["java","spring"] |

Đây là **ví dụ với cấu hình cụ thể**, không phải một transcript bắt buộc cho mọi Servlet mapping. getServletPath() và getPathInfo() còn phụ thuộc cấu hình servlet mapping; không dùng getServletPath() như một bản sao luôn đúng của getRequestURI().

### Các lựa chọn binding thuận tiện hơn

~~~java
@GetMapping("/api/orders/{id}")
OrderResponse find(
        @PathVariable long id,
        @RequestParam(defaultValue = "false") boolean includeItems,
        @RequestHeader(value = "X-Trace", required = false) String trace) {
    // ...
}
~~~

Đoạn trên là snippet minh họa. @PathVariable, @RequestParam và @RequestHeader do framework bind; bạn thường không cần tự parse string thành long/boolean bằng tay.

**Chọn raw request khi thật sự cần metadata hoặc integration infrastructure**, không chỉ vì controller có thể nhận nó. Sử dụng @RequestParam cho một query key đem lại contract rõ ràng và validation dễ kiểm soát.

## 5. Đọc request headers và cookies trong MVC

### Header

~~~java
String accept = request.getHeader("Accept");
String trace = request.getHeader("X-Trace-Id");
Enumeration<String> traceValues = request.getHeaders("X-Trace-Id");
Enumeration<String> headerNames = request.getHeaderNames();
~~~

getHeader trả một giá trị hoặc null. Với header nhiều giá trị, getHeaders(name) cho phép duyệt Enumeration thay vì giả định chỉ một phần tử.

Tên header không phân biệt chữ hoa/thường theo chuẩn HTTP; **giá trị của một header** có quy tắc riêng theo loại header, không nên coi mọi giá trị đều case-insensitive.

### Cookies

~~~java
Cookie[] cookies = request.getCookies();

if (cookies != null) {
    for (Cookie cookie : cookies) {
        if ("theme".equals(cookie.getName())) {
            String value = cookie.getValue();
            // Sử dụng value sau khi kiểm tra tính hợp lệ.
        }
    }
}
~~~

Imports cần jakarta.servlet.http.Cookie. getCookies() có thể trả **null** khi request không có cookie.

Nếu chỉ cần một cookie trong controller, Spring MVC cung cấp @CookieValue:

~~~java
@GetMapping("/theme")
String theme(@CookieValue(
        value = "theme", defaultValue = "light") String value) {
    return value;
}
~~~

Đây là snippet trong @RestController; không gắn bất cứ thông tin quyền truy cập nào vào cookie chưa được xác thực và kiểm tra integrity. Cookie session hoặc token chỉ có giá trị bảo mật khi hệ thống xác thực và quản lý đúng.

## 6. Request attributes: dữ liệu nội bộ một request

Servlet request attributes là một map do server và filters/controller dùng trong **quá trình xử lý cùng một request**:

~~~java
request.setAttribute("demo.trace", "mvc-123");
Object trace = request.getAttribute("demo.trace");
request.removeAttribute("demo.trace");
~~~

Phân biệt:

- **Request parameter:** dữ liệu đến từ client, thường query hoặc form.
- **Header:** metadata do client hoặc proxy gửi.
- **Request attribute:** dữ liệu server-side gắn vào một request; filter, interceptor hoặc controller có thể chia sẻ.
- **Session attribute:** dữ liệu gắn với session, có thể dùng qua nhiều request.

Request attribute không phải dữ liệu mà client có thể tự set trực tiếp bằng cách thêm một HTTP header trùng tên. Tuy nhiên, nếu application copy dữ liệu header không đáng tin vào attribute và sau đó coi attribute là tin cậy, vẫn có nguy cơ spoofing do chính code ứng dụng tạo ra.

### Filter nên dùng request attribute khi nào?

Ví dụ một filter có thể tạo một request correlation marker rồi controller đọc lại:

~~~java
request.setAttribute("demo.marker", "mvc-filter");
filterChain.doFilter(request, response);
~~~

Đây là snippet bên trong Servlet Filter, chưa phải class hoàn chỉnh. Trong ví dụ runnable ở phần sau sẽ có đầy đủ filter và controller.

Đừng dùng request attribute để lưu object có vòng đời dài hoặc task chạy nền vô hạn. Request kết thúc thì không nên giữ reference đến HttpServletRequest trong singleton hoặc static cache.

## 7. Session trong MVC: getSession() khác getSession(false)

~~~java
HttpSession existing = request.getSession(false);

if (existing == null) {
    // Chưa có session hiện tại.
}
~~~

- **getSession(false):** trả session hiện có hoặc null, **không tạo session mới**.
- **getSession():** tương đương getSession(true), trả session và có thể tạo mới nếu chưa có.
- **request.getUserPrincipal():** principal do container/security context cung cấp nếu có, có thể null.

Nếu chỉ muốn kiểm tra request hiện tại đã có session chưa, dùng getSession(false) để tránh vô tình tạo session cho một GET endpoint vốn stateless.

Một HttpSession có thể được nhiều request cùng dùng; **không xem session attributes là thread-safe theo mặc định**. Khi dùng session chung cho state thay đổi đồng thời, cần thiết kế concurrency và consistency phù hợp.

### Không coi session id là mật khẩu công khai

Session ID là thông tin có giá trị bảo mật. Không trả trực tiếp session ID ra response JSON hoặc in vào access log khi không có mục đích được kiểm soát. Ví dụ sẽ chỉ trả boolean có session hay không.

## 8. Lấy raw request body bằng ServletInputStream/Reader

Một HTTP request có thể có body. Servlet API cung cấp:

~~~java
ServletInputStream stream = request.getInputStream();
~~~

hoặc:

~~~java
BufferedReader reader = request.getReader();
~~~

Hai cách này có những ràng buộc sử dụng theo Servlet API: không tùy tiện lấy cả getInputStream() và getReader() cho cùng request rồi kỳ vọng đọc lại độc lập. Body có bản chất là **stream**: khi bytes đã được tiêu thụ, code downstream không tự nhìn thấy lại dữ liệu cũ.

### Ví dụ đọc text body (chỉ dành cho body nhỏ)

~~~java
byte[] bytes = request.getInputStream().readAllBytes();
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

Đây là snippet Servlet MVC, cần imports và phải được gọi trong ngữ cảnh nhận request. readAllBytes() có thể giữ toàn bộ body trong heap, không phù hợp cho upload lớn hoặc dữ liệu không được giới hạn kích thước.

Nên dùng:

~~~java
@PostMapping(
    path = "/echo",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
EchoResponse echo(@RequestBody EchoInput input) {
    return new EchoResponse(input.message());
}
~~~

khi cần JSON DTO. MVC sử dụng HttpMessageConverter cùng Jackson để đọc JSON body. Đừng đọc raw body trước bằng filter rồi dùng @RequestBody mà không có cơ chế wrapper/caching phù hợp.

### Tại sao đọc body trong Filter có thể làm @RequestBody thất bại?

~~~text
HTTP body -> ServletInputStream
                 |
                 +--> Filter đọc hết stream
                 |
                 +--> Controller @RequestBody cố đọc tiếp
                            |
                            +--> Không còn bytes như ban đầu
~~~

Một filter log body nên cẩn trọng. **ContentCachingRequestWrapper** của Spring cache bytes **được đọc qua wrapper** để hỗ trợ quan sát, nhưng bản thân nó không mặc định biến body đã tiêu thụ thành một stream có thể đọc lại tùy ý cho mọi downstream consumer. Nếu thật sự cần replay body, phải thiết kế request wrapper chuyên biệt, giới hạn body size, xử lý encoding và bảo mật log; thường nên tránh đọc body khi filter chỉ cần header/path.

## 9. Servlet form data và getParameter() có thể tiêu thụ body

Với request:

~~~http
POST /submit HTTP/1.1
Content-Type: application/x-www-form-urlencoded

name=An&level=2
~~~

Servlet container có thể parse form body để cung cấp:

~~~java
String name = request.getParameter("name");
String level = request.getParameter("level");
~~~

**Cảnh báo:** Việc gọi getParameter/getParameterMap cho form POST có thể kích hoạt parse request body. Khi đã parse từ body, raw InputStream/Reader không nhất thiết còn nguyên vẹn cho code khác. Ngược lại, nếu bạn đã đọc stream trước, container có thể không parse form parameters như mong đợi.

Vì vậy:

- **JSON:** @RequestBody DTO hoặc JSON converter.
- **Form:** @RequestParam, @ModelAttribute hoặc cơ chế form Servlet phù hợp.
- **Multipart:** MultipartResolver, MultipartFile, Part hoặc @RequestPart khi phù hợp.
- **Raw bytes:** đọc InputStream khi có contract rõ ràng và giới hạn dung lượng.

Không dùng getParameter("message") để kỳ vọng lấy được một field của JSON body. Servlet request parameters không tự parse JSON thành Map.

## 10. MVC request lifecycle, threads và RequestContextHolder

Thông thường HttpServletRequest gắn với **một request đang được xử lý**, không phải một singleton global.

Code nguy hiểm:

~~~java
@Component
class BadCache {

    private HttpServletRequest remembered;

    void store(HttpServletRequest request) {
        remembered = request;
    }
}
~~~

Đây là **phản ví dụ**: giữ reference request trong singleton có thể dẫn tới memory leak, đọc dữ liệu sai request và race condition giữa nhiều client. Đừng triển khai theo mẫu này.

Spring có RequestContextHolder để lấy request context theo thread-bound state trong một số tình huống MVC:

~~~java
RequestAttributes attrs = RequestContextHolder.getRequestAttributes();
~~~

Nhưng thread-local context không tự lan truyền qua mọi asynchronous callback, executor hoặc scheduler. Nếu bạn tạo thread/task riêng, không nên giả định RequestContextHolder vẫn giữ đúng request. Khi cần một số metadata, hãy **trích xuất dữ liệu tối thiểu thành value object an toàn** và truyền rõ vào task; không giữ nguyên HttpServletRequest.

Spring MVC hỗ trợ Servlet async (Callable, DeferredResult, WebAsyncTask và một số reactive return types) nên việc “MVC luôn luôn chỉ chạy đúng một thread từ đầu đến cuối” cũng là kết luận sai. Điều quan trọng là quản lý request lifecycle đúng, không dựa vào thread identity như một nguồn chân lý.

## 11. Spring WebFlux: ServerWebExchange là gì?

WebFlux đặt HTTP request/response và request-scoped state trong **ServerWebExchange**:

~~~java
import org.springframework.web.server.ServerWebExchange;
~~~

Các method quan trọng:

~~~java
ServerHttpRequest request = exchange.getRequest();
ServerHttpResponse response = exchange.getResponse();

Map<String, Object> attrs = exchange.getAttributes();
Mono<WebSession> session = exchange.getSession();
Mono<Principal> principal = exchange.getPrincipal();
~~~

Đây là các dòng minh họa bên trong WebFlux handler có imports thích hợp. exchange.getSession() và exchange.getPrincipal() trả **Publisher** dưới dạng Mono, không phải HttpSession hoặc Principal đồng bộ. Với principal không tồn tại, Mono có thể rỗng.

Để lấy request và response:

- **ServerHttpRequest** nằm trong org.springframework.http.server.reactive.
- **ServerHttpResponse** cũng thuộc org.springframework.http.server.reactive.
- **ServerWebExchange** nằm trong org.springframework.web.server.

Một controller WebFlux có thể nhận trực tiếp ServerWebExchange:

~~~java
@GetMapping("/inspect")
Mono<String> inspect(ServerWebExchange exchange) {
    return Mono.just(exchange.getRequest().getMethod().name());
}
~~~

Đây là snippet WebFlux. Với GET /inspect, body thường là GET; một String có thể được writer ghi text/plain tùy produces và content negotiation. Không nên tự subscribe Mono trong controller: WebFlux framework thực hiện subscribe cho publisher trả về.

## 12. Đọc method, URI, path và query trong WebFlux

Ví dụ:

~~~java
ServerHttpRequest req = exchange.getRequest();

HttpMethod method = req.getMethod();
URI uri = req.getURI();
RequestPath path = req.getPath();
MultiValueMap<String, String> params = req.getQueryParams();

String q = params.getFirst("q");
List<String> tags = params.get("tag");
~~~

Các import tiêu biểu:

~~~java
import java.net.URI;
import java.util.List;
import org.springframework.http.HttpMethod;
import org.springframework.http.server.RequestPath;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.util.MultiValueMap;
~~~

Dòng import RequestPath trong ví dụ trên chỉ minh họa kiểu trong API. Controller có thể dùng var để giảm imports.

### Khác biệt so với Servlet getParameter()

**ServerHttpRequest.getQueryParams()** cho bạn một MultiValueMap của **query parameters**. Nó không tự trộn body JSON hoặc dữ liệu form POST vào query như cơ chế request parameters ở Servlet. Để đọc form body trong WebFlux, dùng exchange.getFormData().

### Path đã tách query

Ví dụ GET /api/books/42?lang=vi:

~~~java
String withinApp = req.getPath().pathWithinApplication().value();
String query = req.getURI().getRawQuery();
~~~

withinApp biểu thị path trong ứng dụng, không chứa ?lang=vi. URI.getRawQuery() cho chuỗi query chưa được decode theo logic của parsed query parameters. Nếu cần nội dung parameter đã decode và có thể lặp, dùng req.getQueryParams().

Các thành phần path có thể bao gồm encoding hoặc context path khác nhau; không tự viết logic security bằng cách cắt chuỗi request URI mà bỏ qua normalization và framework path matching.

## 13. Đọc headers, cookies và network peer trong WebFlux

Ví dụ:

~~~java
ServerHttpRequest req = exchange.getRequest();

String channel = req.getHeaders().getFirst("X-Channel");
List<String> accept = req.getHeaders().get("Accept");
String contentType = String.valueOf(
        req.getHeaders().getContentType());

MultiValueMap<String, HttpCookie> cookies = req.getCookies();
HttpCookie theme = cookies.getFirst("theme");

InetSocketAddress peer = req.getRemoteAddress();
~~~

Đây là snippet, chưa phải file Java độc lập. Các giá trị có thể null: content-type có thể không được khai báo, header có thể thiếu, remote address không phải lúc nào cũng sẵn có ở mọi runtime.

Khác với Servlet Cookie[], WebFlux nhận **MultiValueMap<String,HttpCookie>**. Nếu request có nhiều cookie cùng tên, không nên mặc định chỉ có một.

### Client IP và proxy

- MVC request.getRemoteAddr() thường là địa chỉ peer trực tiếp kết nối với Servlet container.
- WebFlux ServerHttpRequest.getRemoteAddress() thường là địa chỉ peer trực tiếp của HTTP runtime.
- Khi sau Nginx, gateway, load balancer hoặc CDN, peer có thể là proxy, **không phải IP người dùng cuối**.
- Forwarded, X-Forwarded-For và các header tương tự có thể bị client giả mạo nếu mạng/proxy không kiểm soát. Chỉ tin các header đó khi có chiến lược trusted proxy rõ ràng.

Không dùng một giá trị IP remote chưa được chuẩn hóa làm bằng chứng xác thực hoặc phân quyền. Những header proxy cần được xử lý bởi cấu hình forward-header strategy/proxy phù hợp với môi trường.

## 14. Request attributes trong ServerWebExchange

ServerWebExchange có một map request attributes do framework và ứng dụng sử dụng:

~~~java
exchange.getAttributes().put("demo.marker", "webflux-filter");

String marker = exchange.getAttributeOrDefault(
        "demo.marker", "none");
~~~

Attributes này là **state theo HTTP exchange**, tương tự mục đích Servlet request attributes nhưng không phải cùng object hoặc cùng lifecycle API.

Hữu ích khi:

- WebFilter gắn thông tin đánh dấu đã xử lý.
- Router/handler chia sẻ metadata nội bộ.
- Infrastructure gắn marker/correlation id.
- Ghi nhận state nhỏ để nhiều thành phần trong cùng một request sử dụng.

**Lưu ý:** Không đặt object có kích thước lớn hoặc nội dung request body vào exchange attributes để “cache vô hạn” mà không có giới hạn. Tránh lưu dữ liệu cá nhân, token hoặc mật khẩu khi không cần thiết.

### WebFilter và attributes

~~~java
@Bean
WebFilter marker() {
    return (exchange, chain) -> {
        exchange.getAttributes().put(
                "demo.marker", "webflux-filter");
        return chain.filter(exchange);
    };
}
~~~

Đây là phương thức bean trong ứng dụng WebFlux, có imports và class ứng dụng tương ứng trong ví dụ đầy đủ. WebFilter có cùng mục đích interception request với Servlet Filter nhưng trả **Mono<Void>**, phù hợp với reactive request pipeline.

Không nhầm WebFilter với HandlerInterceptor của MVC, và không khai báo jakarta.servlet.Filter rồi mong Reactor Netty WebFlux pipeline tự chạy filter Servlet.

## 15. Session và principal trong WebFlux: Mono là một phần của contract

WebFlux không cung cấp HttpSession trong controller. Dùng WebSession:

~~~java
Mono<WebSession> sessionMono = exchange.getSession();
~~~

**getSession() trả Mono<WebSession>**, cho phép truy cập session trong reactive pipeline. Theo contract Spring Framework 6.1, gọi getSession không tự khởi tạo một session **đã bắt đầu**; session có thể được tạo ra như object để sử dụng, nhưng chỉ khi state/session thực sự thay đổi hoặc bắt đầu theo cơ chế mới cần lưu session tương ứng.

Ví dụ:

~~~java
Mono<Boolean> hasStarted = exchange.getSession()
        .map(WebSession::isStarted);
~~~

Không log hoặc trả session ID cho client chỉ để debug. WebSession attributes là dữ liệu có thể tồn tại qua nhiều request khi session được lưu, khác với exchange attributes theo một request.

### Principal

~~~java
Mono<String> username = exchange.<Principal>getPrincipal()
        .map(Principal::getName)
        .defaultIfEmpty("anonymous");
~~~

Đây là snippet trong WebFlux controller có java.security.Principal và reactor.core.publisher.Mono được import.

Nếu ứng dụng có Spring Security reactive, thông tin authentication có thể được kết nối qua security context/reactive pipeline; đừng tự đoán rằng header X-User do client đặt tương đương principal được xác thực. Nếu request chưa có principal, Mono có thể rỗng.

## 16. Request body trong WebFlux: Flux<DataBuffer>, không phải InputStream

API cơ bản:

~~~java
Flux<DataBuffer> body = exchange.getRequest().getBody();
~~~

Imports:

~~~java
import org.springframework.core.io.buffer.DataBuffer;
import reactor.core.publisher.Flux;
~~~

Body thường được phát theo những DataBuffer khi bytes đến; consumer dùng subscription và backpressure theo reactive contract. Không gọi block() hoặc subscribe() thủ công trong controller chỉ để “đọc request ngay”:

~~~java
// KHÔNG NÊN làm trong request path:
exchange.getRequest().getBody().subscribe(buffer -> {
    // Đọc một side effect ngoài request pipeline.
});
~~~

Đây là **phản ví dụ**. Việc tự subscribe có thể gây race condition với downstream controller, bỏ qua error/cancellation và tiêu thụ body trước khi decoder thông thường đọc được.

### Luồng đọc đúng cho JSON DTO

~~~java
@PostMapping(
    path = "/echo",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
Mono<EchoResponse> echo(@RequestBody Mono<EchoInput> input) {
    return input.map(body -> new EchoResponse(body.message()));
}
~~~

Đây là snippet WebFlux. Spring sử dụng HttpMessageReader/Decoder (thường Jackson JSON codec) để đọc body thành EchoInput; controller nhận Mono<EchoInput> và giữ luồng reactive.

### Nếu thực sự cần đọc raw body

Có thể dùng DataBufferUtils.join để gộp dữ liệu thành một DataBuffer, **kèm giới hạn kích thước rõ ràng**:

~~~java
Mono<String> smallText = DataBufferUtils.join(
        exchange.getRequest().getBody(), 8192)
    .map(buffer -> {
        try {
            byte[] bytes = new byte[buffer.readableByteCount()];
            buffer.read(bytes);
            return new String(bytes, StandardCharsets.UTF_8);
        } finally {
            DataBufferUtils.release(buffer);
        }
    });
~~~

Đây là snippet bên trong handler có imports. Tham số 8192 biểu diễn giới hạn tối đa số byte được buffer trong thao tác join; nếu vượt, DataBufferLimitException có thể phát sinh. Ngưỡng phù hợp phải theo API thực tế, không phải luôn 8192.

DataBuffer có thể dùng bộ nhớ pooled/ref-counted, vì vậy khi code **tự nhận quyền quản lý buffer**, phải release theo contract; không release trước khi đọc xong và không giữ buffer sau khi request bị cancel. Không dùng DataBufferUtils.join để nhận upload không giới hạn vào heap.

**Một lần tiêu thụ:** nếu handler đọc request.getBody() rồi muốn sau đó chuyển cùng body tới @RequestBody, body không tự phát lại. Muốn replay trong filter cần thiết kế ServerHttpRequestDecorator và chiến lược buffering/release an toàn, không phải cứ gọi subscribe lần hai.

## 17. Form data trong WebFlux qua exchange.getFormData()

Đối với:

~~~http
POST /submit HTTP/1.1
Content-Type: application/x-www-form-urlencoded

name=An&level=2
~~~

WebFlux cung cấp:

~~~java
Mono<MultiValueMap<String, String>> form =
        exchange.getFormData();
~~~

Ví dụ xử lý:

~~~java
Mono<String> result = exchange.getFormData()
        .map(values -> values.getFirst("name"))
        .map(name -> name == null ? "none" : name);
~~~

Đây là snippet. **Chú ý riêng:** Reactor map không được trả null. Nếu getFirst("name") là null, hàm map đầu đã lỗi trước khi map tiếp theo xử lý. Vì vậy cách viết trên **không an toàn** nếu name vắng mặt; đoạn đúng phải xử lý null trong **một** lambda:

~~~java
Mono<String> safeResult = exchange.getFormData()
        .map(values -> {
            String name = values.getFirst("name");
            return name == null ? "none" : name;
        });
~~~

Đoạn đúng trả “none” khi key không tồn tại. Đây là ví dụ hữu ích về quy tắc không phát null qua Reactor onNext.

### getFormData() có cache nhưng raw body vẫn bị tiêu thụ

Trong Spring Framework 6.1, ServerWebExchange.getFormData() parse dữ liệu application/x-www-form-urlencoded và cache MultiValueMap kết quả cho các lần gọi getFormData() tiếp theo.

**Không** suy ra raw Flux<DataBuffer> vẫn đọc lại được: body gốc được tiêu thụ khi parse, và việc muốn đọc raw bytes lại là một bài toán khác. Nên dùng API getFormData nhất quán để truy cập form trên cùng exchange.

So sánh với Servlet:

- MVC có request.getParameter() và parsing form qua Servlet.
- WebFlux có getRequest().getQueryParams() **chỉ query**, và exchange.getFormData() **form body**.

Phân biệt này đặc biệt quan trọng khi di chuyển endpoint MVC sang WebFlux.

## 18. Multipart trong MVC và WebFlux

### MVC

Servlet MVC dùng Servlet multipart support, MultipartResolver, MultipartFile, Part:

~~~java
@PostMapping(
    path = "/upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
String upload(@RequestPart("file") MultipartFile file) {
    return file.getOriginalFilename();
}
~~~

Đây là snippet minh họa; **không** lưu file với đường dẫn lấy trực tiếp từ getOriginalFilename(). Kiểm tra size, loại file, tên an toàn và antivirus/chính sách storage nếu có.

### WebFlux

Các API gồm org.springframework.http.codec.multipart.Part và FilePart:

~~~java
Mono<MultiValueMap<String, Part>> allParts =
        exchange.getMultipartData();
~~~

getMultipartData() có thể parse/thu thập các parts theo tên và cache map kết quả; **nội dung của từng part không tự cache vô hạn để đọc nhiều lần**. Dữ liệu part và multipart upload có thể lớn, nên ưu tiên API FilePart.transferTo hoặc stream PartEvent phù hợp với nhu cầu.

Với Spring WebFlux 6.1 có thể dùng Flux<PartEvent> cho multipart streaming nếu cần xử lý từng chunk mà không gom toàn bộ part thành map. Khi tự xử lý buffers phải giải phóng phần dữ liệu theo contract.

Không nhầm giữa jakarta.servlet.http.Part của MVC và org.springframework.http.codec.multipart.Part của WebFlux: type và cách xử lý I/O khác nhau.

## 19. Request object có sửa trực tiếp được không?

### MVC và HttpServletRequestWrapper

HttpServletRequest cung cấp các method để set request attributes, nhưng việc chỉnh method/URI/headers như một object tùy ý không phải cơ chế phổ thông. Nếu cần thay đổi cách downstream nhìn request, thường dùng **HttpServletRequestWrapper** trong Servlet Filter và override method cụ thể:

~~~java
HttpServletRequestWrapper wrapped =
        new HttpServletRequestWrapper(request) {
            @Override
            public String getHeader(String name) {
                if ("X-Demo".equalsIgnoreCase(name)) {
                    return "from-wrapper";
                }
                return super.getHeader(name);
            }
        };
chain.doFilter(wrapped, response);
~~~

Đây là snippet cho Filter có chain, request, response và imports; chưa xử lý mọi method như getHeaders/getHeaderNames, nên chỉ dùng để minh họa wrapper, không phải giải pháp production hoàn chỉnh để thay đổi header. Khi xây wrapper header hoàn chỉnh, bảo đảm các API đọc header nhất quán.

### WebFlux: mutate request và exchange

ServerHttpRequest và ServerWebExchange có cơ chế decorator/mutator:

~~~java
ServerHttpRequest altered = exchange.getRequest()
        .mutate()
        .header("X-Demo", "from-filter")
        .build();

ServerWebExchange alteredExchange = exchange.mutate()
        .request(altered)
        .build();

return chain.filter(alteredExchange);
~~~

Đây là snippet trong WebFilter có các import phù hợp. Thay vì tìm cách sửa read-only headers trực tiếp, tạo request đã được decorate rồi truyền exchange tương ứng tới downstream.

**Lưu ý:** nếu X-Demo là header tin cậy, filter phải **loại bỏ hoặc kiểm soát giá trị do client giả mạo** trước khi thêm. Không mặc định một giá trị header trở nên authenticated chỉ vì filter ghi lại nó.

### Mutate không làm raw body tự replay

ServerHttpRequest.mutate() hữu ích cho URI, headers và các thuộc tính được builder hỗ trợ. Nó **không** tự nhân bản luồng DataBuffer đã tiêu thụ. Muốn thay body, cần ServerHttpRequestDecorator phù hợp, xử lý buffer ownership và cancellation — việc này phức tạp hơn chỉnh một header.

## 20. Controller arguments: nên dùng request object hay annotation?

| Nhu cầu | MVC ưu tiên | WebFlux ưu tiên |
|---|---|---|
| Lấy một query value | @RequestParam | @RequestParam |
| Lấy path id | @PathVariable | @PathVariable |
| Lấy một header | @RequestHeader | @RequestHeader |
| Lấy cookie | @CookieValue | @CookieValue |
| Deserialize JSON | @RequestBody DTO | @RequestBody Mono<DTO> hoặc DTO tùy use case |
| Lấy nhiều request metadata | HttpServletRequest | ServerWebExchange / ServerHttpRequest |
| Thêm state nội bộ từ filter | request.setAttribute | exchange.getAttributes().put |
| Đọc form POST | @RequestParam/@ModelAttribute | exchange.getFormData hoặc @ModelAttribute |
| Xử lý multipart | MultipartFile/@RequestPart | FilePart/@RequestPart hoặc PartEvent |
| Đọc raw body | ServletInputStream/Reader | Flux<DataBuffer> với quản lý buffer |
| Session | HttpSession | WebSession/Mono<WebSession> |
| Response xử lý trực tiếp | HttpServletResponse | ServerHttpResponse |

Sử dụng trực tiếp request object không phải “cấp cao hơn” so với annotation. Annotation cho contract rõ, validation thuận tiện, xử lý kiểu dữ liệu và test dễ. Request object phát huy giá trị ở middleware, tracing, multi-field inspection hoặc API tích hợp hạ tầng.

## 21. Ví dụ chạy được 1 — Spring MVC và HttpServletRequest

**Project riêng thứ nhất:** Spring Boot 3.3.x, Java 17+, chỉ cần starter-web cùng starter-test.

### 21.1. Dependencies

Trong build.gradle của một project Spring Boot đã khai báo plugins/repositories:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là phần dependencies, **không phải toàn bộ build.gradle**. Starter-web cung cấp Servlet Spring MVC, embedded Tomcat và Jackson cho JSON.

### 21.2. Mã Java

Tạo file **src/main/java/com/example/requestmvc/MvcRequestApplication.java**:

~~~java
package com.example.requestmvc;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class MvcRequestApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcRequestApplication.class, args);
    }

    public record Snapshot(
            String method,
            String uri,
            String query,
            String channel,
            String marker,
            boolean hasSession) {}

    public record EchoInput(String message) {}
    public record EchoReply(String message, String contentType) {}

    @Component
    static class DemoFilter extends OncePerRequestFilter {

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {

            request.setAttribute("demo.marker", "mvc-filter");
            chain.doFilter(request, response);
        }
    }

    @RestController
    @RequestMapping("/demo")
    static class DemoController {

        @GetMapping(
                path = "/inspect",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        Snapshot inspect(HttpServletRequest request) {
            String q = request.getParameter("q");
            String channel = request.getHeader("X-Channel");

            return new Snapshot(
                    request.getMethod(),
                    request.getRequestURI(),
                    q == null ? "none" : q,
                    channel == null ? "none" : channel,
                    (String) request.getAttribute("demo.marker"),
                    request.getSession(false) != null
            );
        }

        @PostMapping(
                path = "/echo",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        EchoReply echo(
                @RequestBody EchoInput input,
                HttpServletRequest request) {
            return new EchoReply(
                    input.message(),
                    request.getContentType()
            );
        }

        @PostMapping(
                path = "/raw",
                consumes = MediaType.TEXT_PLAIN_VALUE,
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        String raw(HttpServletRequest request)
                throws IOException {
            byte[] bytes = request.getInputStream().readAllBytes();
            return new String(bytes, StandardCharsets.UTF_8)
                    .toUpperCase(Locale.ROOT);
        }
    }
}
~~~

Giải thích:

- **DemoFilter** chạy trong Servlet filter chain và ghi một request attribute. Controller đọc lại qua request.getAttribute.
- **GET /demo/inspect** cho biết method, URI, một query parameter, một header, filter marker và có session sẵn hay không.
- **POST /demo/echo** sử dụng @RequestBody cho JSON, đồng thời có thể đọc request Content-Type qua HttpServletRequest mà không tiêu thụ body lần thứ hai.
- **POST /demo/raw** đọc raw text bytes trực tiếp. Endpoint này **không** có @RequestBody nên tránh tranh đọc body với converter.
- raw dùng readAllBytes() chỉ để minh họa body text nhỏ; production cần limit. Content-Type text/plain và ký tự UTF-8 phải thống nhất giữa client/server.
- Filter và controller đều là nested static classes, được Spring component scan khi package root là com.example.requestmvc. Không cần tạo hai application contexts.

### 21.3. Chạy với Gradle

Trong src/main/resources/application.yml:

~~~yaml
server:
  port: 8080
~~~

Từ thư mục project:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

### 21.4. Thử đọc metadata

~~~bash
curl -s -H 'Accept: application/json' \
  -H 'X-Channel: mobile' \
  'http://localhost:8080/demo/inspect?q=hello'
~~~

Khi request không mang session có sẵn, response body có ý nghĩa tương đương:

~~~json
{"method":"GET","uri":"/demo/inspect","query":"hello","channel":"mobile","marker":"mvc-filter","hasSession":false}
~~~

Thứ tự JSON keys/whitespace phụ thuộc Jackson, không phải contract. Nếu môi trường khác đã tạo session và gửi cookie tương ứng, hasSession có thể true.

### 21.5. Thử @RequestBody JSON

~~~bash
curl -i -X POST http://localhost:8080/demo/echo \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"message":"xin chao"}'
~~~

Body tương đương:

~~~json
{"message":"xin chao","contentType":"application/json"}
~~~

getContentType() phản ánh header client gửi. Nếu client gửi thêm tham số charset hợp lệ, giá trị trả về có thể bao gồm tham số đó.

### 21.6. Thử raw body

~~~bash
curl -s -X POST http://localhost:8080/demo/raw \
  -H 'Content-Type: text/plain' \
  --data-binary 'hello'
~~~

Response body chính xác:

~~~text
HELLO
~~~

Đây là path thực hành cho raw ServletInputStream; nó **không** chứng minh mọi request nên đọc InputStream thủ công.

## 22. Kiểm thử ví dụ MVC bằng MockMvc

Tạo **src/test/java/com/example/requestmvc/MvcRequestApplicationTests.java**:

~~~java
package com.example.requestmvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvcRequestApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void readsMetadataAndRequestAttribute() throws Exception {
        mvc.perform(get("/demo/inspect")
                    .param("q", "hello")
                    .header("X-Channel", "mobile"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.method").value("GET"))
            .andExpect(jsonPath("$.uri").value("/demo/inspect"))
            .andExpect(jsonPath("$.query").value("hello"))
            .andExpect(jsonPath("$.channel").value("mobile"))
            .andExpect(jsonPath("$.marker").value("mvc-filter"));
    }

    @Test
    void readsJsonWithRequestBodyAndHeadersWithServletApi()
            throws Exception {
        mvc.perform(post("/demo/echo")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"message\":\"hello\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("hello"))
            .andExpect(jsonPath("$.contentType")
                    .value("application/json"));
    }

    @Test
    void readsRawBodyOnlyInItsOwnEndpoint() throws Exception {
        mvc.perform(post("/demo/raw")
                    .contentType(MediaType.TEXT_PLAIN)
                    .content("hello"))
            .andExpect(status().isOk())
            .andExpect(content().string("HELLO"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

MockMvc mô phỏng servlet request/response và chạy MVC infrastructure mà **không cần TCP listener thật**. Test trên kiểm tra route, việc đọc header/query, request attribute của filter, body JSON và raw text. Nó không chứng minh port thực tế có mở hoặc proxy forwarding đã đúng.

## 23. Ví dụ chạy được 2 — Spring WebFlux và ServerWebExchange

**Project riêng thứ hai:** Spring Boot 3.3.x, Java 17+, chỉ sử dụng starter-webflux cùng starter-test. Không thêm starter-web vào project này vì Boot thường chọn MVC nếu có cả hai.

### 23.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là phần dependencies của project Spring Boot Gradle đã thiết lập plugins/repositories.

### 23.2. Mã Java

Tạo **src/main/java/com/example/requestwebflux/WebFluxRequestApplication.java**:

~~~java
package com.example.requestwebflux;

import java.nio.charset.StandardCharsets;
import java.security.Principal;
import java.util.Locale;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxRequestApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxRequestApplication.class, args);
    }

    public record Snapshot(
            String method,
            String path,
            String query,
            String channel,
            String marker,
            String principal) {}

    public record EchoInput(String message) {}
    public record EchoReply(String message, String contentType) {}
    public record FormReply(String name) {}

    @Bean
    WebFilter demoMarker() {
        return (exchange, chain) -> {
            exchange.getAttributes().put(
                    "demo.marker", "webflux-filter");
            return chain.filter(exchange);
        };
    }

    @RestController
    @RequestMapping("/demo")
    static class DemoController {

        @GetMapping(
                path = "/inspect",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        Mono<Snapshot> inspect(ServerWebExchange exchange) {
            ServerHttpRequest request = exchange.getRequest();

            String q = request.getQueryParams().getFirst("q");
            String channel = request.getHeaders()
                    .getFirst("X-Channel");
            String marker = exchange.getAttributeOrDefault(
                    "demo.marker", "none");

            return exchange.<Principal>getPrincipal()
                    .map(Principal::getName)
                    .defaultIfEmpty("anonymous")
                    .map(name -> new Snapshot(
                            request.getMethod().name(),
                            request.getPath()
                                    .pathWithinApplication().value(),
                            q == null ? "none" : q,
                            channel == null ? "none" : channel,
                            marker,
                            name
                    ));
        }

        @PostMapping(
                path = "/echo",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        Mono<EchoReply> echo(
                @RequestBody Mono<EchoInput> body,
                ServerWebExchange exchange) {
            return body.map(input -> new EchoReply(
                    input.message(),
                    String.valueOf(
                            exchange.getRequest()
                                    .getHeaders().getContentType())
            ));
        }

        @PostMapping(
                path = "/raw",
                consumes = MediaType.TEXT_PLAIN_VALUE,
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        Mono<String> raw(ServerWebExchange exchange) {
            return DataBufferUtils.join(
                    exchange.getRequest().getBody(),
                    8192
            ).map(buffer -> {
                try {
                    byte[] bytes =
                            new byte[buffer.readableByteCount()];
                    buffer.read(bytes);
                    return new String(
                            bytes, StandardCharsets.UTF_8)
                            .toUpperCase(Locale.ROOT);
                } finally {
                    DataBufferUtils.release(buffer);
                }
            }).defaultIfEmpty("");
        }

        @PostMapping(
                path = "/form",
                consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        Mono<FormReply> form(ServerWebExchange exchange) {
            return exchange.getFormData().map(data -> {
                String name = data.getFirst("name");
                return new FormReply(
                        name == null ? "none" : name);
            });
        }
    }
}
~~~

**Giải thích:**

- **WebFilter** thêm exchange attribute trước khi chuyển tiếp tới handler reactive.
- **GET /demo/inspect** đọc method, path, query, header, attribute và principal không có thì hiển thị anonymous. Đọc principal qua Mono, không gọi block().
- **POST /demo/echo** đọc JSON bằng @RequestBody Mono<EchoInput>; query/header metadata từ exchange có thể đọc mà không tranh tiêu thụ body.
- **POST /demo/raw** dùng DataBufferUtils.join với giới hạn **8192 bytes**, đọc buffer rồi release bằng finally. Chỉ dùng cho payload text nhỏ.
- **POST /demo/form** dùng getFormData(), không trộn lẫn với query params hoặc đọc raw body lần nữa.
- Các request handlers trả Mono, framework sẽ subscribe khi gửi HTTP response. Controller không tự gọi subscribe hoặc block.
- Chưa cấu hình Spring Security; principal mặc định có thể empty và được chuyển thành anonymous. Trong môi trường có authentication, field principal sẽ là tên đã được security context cung cấp.

Đây là **Java source file hoàn chỉnh** trong một project Boot 3.3.x có starter-webflux. Không chạy bằng javac thuần khi thiếu thư viện Spring, Reactor và Jackson.

### 23.3. Chạy và thử

Cấu hình src/main/resources/application.yml:

~~~yaml
server:
  port: 8080

spring:
  codec:
    max-in-memory-size: 256KB
~~~

Giá trị codec là một ví dụ giới hạn cho các trường hợp decoder cần aggregate. Nó khác giới hạn 8192 bytes đặt rõ trong raw endpoint; không suy ra property này giới hạn **toàn bộ** request body ở mọi endpoint.

Chạy:

~~~bash
./gradlew bootRun
~~~

Trên PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

### 23.4. Request metadata

~~~bash
curl -s -H 'X-Channel: mobile' \
  'http://localhost:8080/demo/inspect?q=hello'
~~~

Response JSON có ý nghĩa:

~~~json
{"method":"GET","path":"/demo/inspect","query":"hello","channel":"mobile","marker":"webflux-filter","principal":"anonymous"}
~~~

Thứ tự JSON fields có thể khác. Nếu ứng dụng đã cấu hình authentication, principal sẽ có giá trị tương ứng với principal đã được xác thực.

### 23.5. Request body JSON

~~~bash
curl -s -X POST http://localhost:8080/demo/echo \
  -H 'Content-Type: application/json' \
  --data '{"message":"hello"}'
~~~

Response tương đương:

~~~json
{"message":"hello","contentType":"application/json"}
~~~

### 23.6. Request body raw text

~~~bash
curl -s -X POST http://localhost:8080/demo/raw \
  -H 'Content-Type: text/plain' \
  --data-binary 'hello'
~~~

Body chính xác:

~~~text
HELLO
~~~

### 23.7. Form data

~~~bash
curl -s -X POST http://localhost:8080/demo/form \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=An'
~~~

Response body có ý nghĩa:

~~~json
{"name":"An"}
~~~

Thử đổi thành /demo/form?name=query nhưng gửi body name=body: getFormData() trong ví dụ chỉ đọc **form body**, không tự thay bằng query. Nếu muốn ghép query và form, phải thiết kế quy tắc ưu tiên rõ ràng và lấy từ cả hai nguồn.

### 23.8. PowerShell và quoting

Trên Windows PowerShell dùng curl.exe để tránh alias curl:

~~~powershell
curl.exe -s -H "X-Channel: mobile" "http://localhost:8080/demo/inspect?q=hello"
curl.exe -s -X POST "http://localhost:8080/demo/raw" -H "Content-Type: text/plain" --data-binary "hello"
curl.exe -s -X POST "http://localhost:8080/demo/form" -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "name=An"
~~~

Với JSON trên Windows, đặt nội dung JSON trong file UTF-8, ví dụ input.json, rồi dùng curl.exe --data-binary "@input.json" để tránh khác biệt escaping giữa phiên bản PowerShell.

## 24. Kiểm thử WebFlux bằng WebTestClient

Tạo **src/test/java/com/example/requestwebflux/WebFluxRequestApplicationTests.java**:

~~~java
package com.example.requestwebflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class WebFluxRequestApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void readsMetadataAndExchangeAttribute() {
        client.get()
                .uri("/demo/inspect?q=hello")
                .header("X-Channel", "mobile")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.method").isEqualTo("GET")
                .jsonPath("$.path").isEqualTo("/demo/inspect")
                .jsonPath("$.query").isEqualTo("hello")
                .jsonPath("$.channel").isEqualTo("mobile")
                .jsonPath("$.marker").isEqualTo("webflux-filter");
    }

    @Test
    void decodesJsonAndKeepsHeaderMetadata() {
        client.post()
                .uri("/demo/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"message\":\"hello\"}")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("hello")
                .jsonPath("$.contentType")
                        .isEqualTo("application/json");
    }

    @Test
    void readsRawSmallBodyAndReturnsText() {
        client.post()
                .uri("/demo/raw")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("HELLO");
    }

    @Test
    void parsesFormBodyThroughExchange() {
        client.post()
                .uri("/demo/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("name", "An"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("An");
    }
}
~~~

Lệnh:

~~~bash
./gradlew test
~~~

Khác với MockMvc, WebTestClient trong test RANDOM_PORT này gửi HTTP đến embedded reactive server với port do test cấp. Do vậy nó kiểm tra cả phần HTTP transport hơn so với test chỉ bindToController; tuy nhiên không thay thế kiểm thử reverse proxy, TLS hoặc cấu hình deployment.

## 25. Phân biệt Servlet Filter với WebFilter và dữ liệu đọc được

| Chủ đề | MVC Servlet Filter | WebFlux WebFilter |
|---|---|---|
| Contract | doFilter(request,response,chain) | filter(exchange,chain) trả Mono<Void> |
| Request abstraction | ServletRequest/HttpServletRequest | ServerWebExchange |
| Chuyển tiếp | chain.doFilter(...) | return chain.filter(exchange) |
| Attributes | request.setAttribute | exchange.getAttributes().put |
| Body | ServletInputStream/Reader | Flux<DataBuffer> |
| Thread-local context | Có thể dùng trong điều kiện cụ thể | Không dựa vào thread-local cho request context |
| Thay headers/URI | Wrapper Servlet hoặc cơ chế proxy | ServerHttpRequest.mutate() và exchange.mutate() |
| Dùng khi | MVC và Servlet container | WebFlux reactive pipeline |

### Không đặt blocking code trong WebFilter trên event loop

Một WebFilter chạy I/O chặn lâu hoặc Thread.sleep có thể làm giảm throughput của Reactor Netty. Nếu phải tích hợp thư viện blocking, hãy sử dụng một scheduler phù hợp (ví dụ boundedElastic) theo đúng contract, có timeout và giới hạn concurrency. Không giả định chỉ cần bọc mọi blocking call trong Mono.just sẽ làm nó non-blocking.

### Đọc body trong middleware: tại sao phức tạp?

- Filter có thể đi qua trước khi controller resolve @RequestBody.
- Body stream không tự replay giữa subscribers.
- Nếu buffer để log, có thể tăng memory theo số request đồng thời.
- Dữ liệu nhạy cảm có thể bị đưa vào logs.
- Pooled DataBuffers yêu cầu quản lý release đúng.
- Cần xử lý cancellation và error paths.

Thường nên log **method/path/response code/correlation id** ở middleware, còn payload có validation và redaction rõ ràng ở tầng DTO hoặc business boundary.

## 26. Request attributes khác với Reactor Context

WebFlux có hai khái niệm dễ nhầm:

1. **ServerWebExchange attributes:** Map theo một HTTP exchange, framework và WebFilter có thể truy cập qua exchange.
2. **Reactor Context:** ngữ cảnh gắn với subscriber/pipeline, thường được dùng để truyền dữ liệu xuyên các operator async mà không dựa vào ThreadLocal.

Một ví dụ Reactor Context thuần:

~~~java
Mono<String> value = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("trace", "none")))
    .contextWrite(ctx -> ctx.put("trace", "r-1"));
~~~

Khi subscribed, giá trị có ý nghĩa "r-1". Đây là snippet Reactor, không đồng nghĩa đang đọc exchange attribute. Việc chuyển dữ liệu giữa exchange attributes và Reactor Context phải có code/cơ chế phù hợp.

**Đừng truyền nguyên HttpServletRequest/ServerWebExchange vào background task dài hạn** chỉ để tiếp tục logging. Hãy trích xuất một immutable value object như traceId và những field thực sự cần thiết.

## 27. Error handling: lỗi nào xuất phát từ request metadata, lỗi nào từ body?

### 400 Bad Request

Thường do:
- @RequestParam required bị thiếu.
- Không convert được giá trị parameter sang int/long/enum.
- JSON malformed hoặc type mismatch.
- @Valid validation thất bại.

Không tự gộp mọi lỗi 400 thành “server không tìm thấy route”. Route có thể đã được chọn thành công nhưng parsing/binding thất bại.

### 415 Unsupported Media Type

Ví dụ @PostMapping(consumes=application/json) nhưng client gửi Content-Type=text/plain. Framework không chấp nhận loại body đó. Đừng đổi Accept để sửa lỗi input Content-Type.

### 406 Not Acceptable

Ví dụ endpoint chỉ produces JSON nhưng client gửi Accept chỉ text/plain. Đây là lỗi chọn representation cho response, không phải lỗi getParameter hay getHeader.

### Body đọc hai lần

Trong MVC có thể gặp HttpMessageNotReadableException: required request body is missing sau một filter đã tiêu thụ InputStream. Trong WebFlux, tự subscribe request.getBody() trước có thể làm downstream không còn raw body để decode, gây lỗi, rỗng hoặc race conditions. Lỗi thực tế phụ thuộc runtime và timing.

### Buffer/size limit

WebFlux có thể báo DataBufferLimitException khi một codec hoặc DataBufferUtils.join với giới hạn bị vượt. **Không mặc định** mọi tình huống này đều trả HTTP 413; response phụ thuộc exception mapping, server và thời điểm headers đã commit.

### Session và request lifecycle

Nếu cố dùng request object ngoài thời gian xử lý HTTP, có thể đọc state không còn hợp lệ hoặc giữ tài nguyên. Đừng sửa bằng cách kéo dài lifetime của request trong singleton.

## 28. Reverse proxy, header spoofing và dữ liệu nhạy cảm

Trong cả MVC và WebFlux:

- **X-Forwarded-For**, **Forwarded**, **X-Real-IP** chỉ có thể là nguồn đáng tin khi proxy tin cậy quản lý/ghi đè chúng đúng cách.
- getRemoteAddr() hoặc getRemoteAddress() phản ánh peer kết nối trực tiếp theo runtime; đó có thể là gateway.
- Request headers và query params do client kiểm soát; phải validate trước khi dùng để chọn account, role hoặc quyền truy cập.
- Cookie có thể bị giả mạo, sửa hoặc lấy cắp; chỉ coi session/auth cookies an toàn khi hệ thống quản lý chữ ký/định danh và session đúng.
- Không log Authorization, Cookie, Set-Cookie, mật khẩu, token hoặc body chứa thông tin cá nhân vào debug output.
- Tránh in mọi getHeaderNames/getHeaders hoặc getParameters trong production mà không redaction và giới hạn.

### CORS không thay security

Nếu browser bị từ chối do CORS preflight, vấn đề không nhất thiết là HttpServletRequest hoặc ServerWebExchange đọc header sai. CORS là cơ chế trình duyệt. Nó không thay authentication, authorization, firewall hoặc phân quyền cho API.

### URI và host không phải nguồn xác thực

HTTP Host và forwarded headers có thể ảnh hưởng URL mà ứng dụng xây dựng nếu proxy configuration không chặt chẽ. Khi tạo redirect hoặc absolute links, cần cấu hình trusted forwarded headers phù hợp và tránh sử dụng trực tiếp host dữ liệu không tin cậy để tạo security-sensitive links.

## 29. Khi nào nên dùng WebRequest/NativeWebRequest thay Servlet request?

Spring MVC còn hỗ trợ:

~~~java
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.context.request.NativeWebRequest;
~~~

Các abstraction này phù hợp nếu bạn muốn đọc request parameters hoặc attributes ở cấp Spring mà không phụ thuộc quá sâu vào HttpServletRequest cho từng thao tác.

Tuy nhiên:

- NativeWebRequest có khả năng truy cập native Servlet request trong MVC.
- Không suy ra NativeWebRequest là thay thế tương đương cho ServerWebExchange trong reactive WebFlux.
- Nếu code chỉ nhận một header hoặc parameter, annotation vẫn ngắn và dễ bảo trì hơn.

Khi tách business service khỏi web layer, truyền DTO/value object thay vì cả HttpServletRequest/ServerWebExchange để không buộc service phụ thuộc vào runtime.

## 30. Di chuyển controller MVC sang WebFlux: checklist mapping API

| MVC đang sử dụng | Hướng WebFlux thường dùng | Lưu ý |
|---|---|---|
| HttpServletRequest request | ServerWebExchange exchange | Không phải cast hoặc adapter 1-1 |
| getMethod() | getRequest().getMethod() | String vs HttpMethod |
| getRequestURI() | getRequest().getPath() hoặc getURI() | Path API tách context/query |
| getParameter("x") | getRequest().getQueryParams().getFirst("x") | Không tự bao gồm form body |
| getParameterValues("x") | getQueryParams().get("x") | List hoặc null |
| getHeader("X") | getHeaders().getFirst("X") | Có thể null |
| getCookies() | getCookies() | Cookie[] vs MultiValueMap |
| getAttribute("k") | exchange.getAttribute("k") | Request-scoped |
| getSession(false) | exchange.getSession() / WebSession.isStarted | Mono và semantics khác |
| getUserPrincipal() | exchange.getPrincipal() | Mono có thể rỗng |
| getInputStream() | getBody() | ServletInputStream vs Flux<DataBuffer> |
| @RequestBody DTO | @RequestBody Mono<DTO> hoặc DTO | Reactive reader/codecs |
| MultipartFile | FilePart / Part / PartEvent | Streaming và cleanup khác |
| Servlet Filter | WebFilter | Chain và return contract khác |
| @ControllerAdvice MVC | @ControllerAdvice WebFlux theo framework | Exception types/handling có khác |

**Không chuyển máy móc** code đọc body synchronously sang WebFlux bằng .block(). Hãy suy nghĩ lại về publisher composition và timeouts để giữ semantics non-blocking.

## 31. Bài tập thực hành

**Bài 1 — Query lặp:** Client gọi /demo/inspect?tag=java&tag=spring. Viết một endpoint MVC dùng getParameterValues("tag") và WebFlux dùng getQueryParams().get("tag") để trả danh sách hai giá trị. Đảm bảo không chỉ giữ giá trị đầu tiên.

**Bài 2 — Missing header:** Thử GET /demo/inspect không có X-Channel trong cả hai project. Kiểm tra response trả "none" (ví dụ của bài) thay vì exception. Sau đó đổi sang @RequestHeader(required=true) và quan sát hành vi 400 khi thiếu.

**Bài 3 — Body đọc hai lần:** Trong một môi trường test riêng, thêm filter đọc raw body trước controller @RequestBody. Quan sát lỗi; sau đó **khôi phục** filter chỉ đọc metadata. Giải thích vì sao việc đọc lại raw body cần wrapper/decorator và quản lý size.

**Bài 4 — Form vs query:** Với WebFlux /demo/form, gửi query name=query và body name=body. Xác nhận getFormData() lấy body. Nếu cần cả hai, tạo handler trả hai field riêng bằng getQueryParams và getFormData.

**Bài 5 — Session:** Thêm endpoint chỉ đọc session state. Đừng trả session id; trả boolean isStarted/hasSession tương ứng. Phân tích vì sao getSession(false) của Servlet khác getSession() trả Mono<WebSession> của WebFlux.

**Bài 6 — Giới hạn raw text:** Với WebFlux /demo/raw giới hạn join là 8192 byte, gửi body lớn hơn rồi quan sát exception/status. Không khẳng định status chung cho mọi configuration. Sau đó thiết kế giới hạn tại reverse proxy hoặc endpoint cho production.

**Bài 7 — Filter attributes:** Đổi marker từ filter và kiểm tra test vẫn đọc đúng marker thông qua request/exchange attributes. Sau đó thử giữ cả request object trong singleton và giải thích vì sao đây là anti-pattern, **không dùng anti-pattern trong code production**.

## 32. Câu hỏi tự kiểm tra

**Câu 1.** Trên Spring Boot 3.3, vì sao import javax.servlet.http.HttpServletRequest thường báo thiếu package?

**Đáp án:** Spring Framework 6/Boot 3 chuyển sang Jakarta Servlet API, nên import là jakarta.servlet.http.HttpServletRequest.

**Câu 2.** WebFlux ServerWebExchange chứa những gì ngoài request?

**Đáp án:** Response, exchange attributes, session Mono, principal Mono, locale context, form/multipart parsing và nhiều thành phần điều phối HTTP exchange.

**Câu 3.** request.getParameter("tag") và request.getParameterValues("tag") khác nhau thế nào?

**Đáp án:** getParameter trả một giá trị hoặc null; getParameterValues trả mảng các giá trị cùng tên hoặc null.

**Câu 4.** ServerHttpRequest.getQueryParams() có tự lấy JSON fields trong request body không?

**Đáp án:** Không. Nó chỉ lấy query parameters đã parse, không decode JSON body hay parse form body thay getFormData().

**Câu 5.** Tại sao một Servlet Filter đọc request.getInputStream() trước có thể làm @RequestBody bị lỗi?

**Đáp án:** Body stream bị tiêu thụ, mặc định không tự rewind/replay cho converter ở controller.

**Câu 6.** Trong WebFlux, vì sao không gọi request.getBody().subscribe(...) trong WebFilter để log rồi lại chain.filter(exchange)?

**Đáp án:** Subscription tiêu thụ body ngoài pipeline chính, có thể race, mất error/cancel propagation và khiến downstream không còn dữ liệu.

**Câu 7.** Sự khác biệt giữa request attributes và session attributes?

**Đáp án:** Request attributes gắn với một request/exchange; session attributes gắn với một session và có thể tồn tại qua nhiều request.

**Câu 8.** Nếu chỉ muốn biết MVC request đã có session hay chưa, nên gọi getSession() hay getSession(false)?

**Đáp án:** getSession(false), vì nó không tạo session mới nếu không tồn tại.

**Câu 9.** WebFlux getSession() có luôn bắt đầu/persist session khi chỉ đọc không?

**Đáp án:** Không. Gọi method trả Mono<WebSession>; không tự bắt đầu session nếu chỉ truy cập mà không có thay đổi/start được yêu cầu.

**Câu 10.** DataBufferUtils.join có giới hạn giúp điều gì?

**Đáp án:** Giới hạn số byte được buffer để aggregate, giảm rủi ro tiêu thụ memory vô hạn; khi code tự sử dụng pooled buffer vẫn phải release đúng contract.

**Câu 11.** getRemoteAddr() và getRemoteAddress() có luôn là IP người dùng thực không?

**Đáp án:** Không. Khi có proxy/gateway, đó có thể là địa chỉ peer trực tiếp; forwarded headers phải được xử lý theo trusted proxy policy.

**Câu 12.** Khi nào nên dùng @RequestParam thay vì HttpServletRequest hoặc ServerWebExchange?

**Đáp án:** Khi controller chỉ cần vài query parameters có kiểu rõ ràng, muốn tận dụng binding, defaultValue, validation và contract dễ kiểm thử.

## 33. Checklist trước khi triển khai

- [ ] Đã xác định web stack thực sự là Spring MVC hay Spring WebFlux.
- [ ] Với Boot 3.x, MVC dùng jakarta.servlet.http.HttpServletRequest, không còn javax.servlet.
- [ ] WebFlux controller dùng ServerWebExchange/ServerHttpRequest, không dùng Servlet API như mặc định.
- [ ] Đọc path, query, header, cookie từ API tương ứng; kiểm tra null/missing values.
- [ ] Phân biệt query parameters và form body, nhất là khi di chuyển MVC sang WebFlux.
- [ ] Dùng @RequestBody cho DTO/JSON thay vì tiêu thụ raw body trùng lặp.
- [ ] Không log payload nhạy cảm hoặc mọi request headers thiếu redaction.
- [ ] Servlet Filter và WebFilter không chủ động tiêu thụ body trừ khi có thiết kế replay/cache và size limit rõ.
- [ ] Không giữ request object trong singleton, static field hay background jobs dài hạn.
- [ ] Không dùng ThreadLocal MVC như nguồn request context trong reactive pipeline.
- [ ] Không gọi block()/subscribe() để đọc WebFlux body trong controller/filter.
- [ ] Raw DataBuffer có giới hạn aggregation, release và xử lý cancel/error.
- [ ] Phân biệt session tồn tại và session mới được tạo/bắt đầu.
- [ ] Chỉ tin IP/Forwarded headers khi có trusted proxy policy.
- [ ] Có MockMvc tests cho MVC và WebTestClient tests cho WebFlux.
- [ ] Không đặt cả starter-web và starter-webflux vào project demo rồi mặc định nó chạy reactive.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.1 — MVC Controller Method Arguments](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring Framework 6.1 — WebFlux Controller Method Arguments](https://docs.spring.io/spring-framework/reference/6.1/web/webflux/controller/ann-methods/arguments.html)
- [Spring Framework 6.1 — ServerWebExchange API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/ServerWebExchange.html)
- [Spring Framework 6.1 — ServerHttpRequest API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html)
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Spring Framework — WebFlux Form Data and Multipart](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
