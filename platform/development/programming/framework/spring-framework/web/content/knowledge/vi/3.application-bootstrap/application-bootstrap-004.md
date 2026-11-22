# Ánh xạ servlet, context path và đường dẫn của ứng dụng trong Spring Web

Khi client gọi `http://localhost:8080/store/api/books/42?lang=vi`, không phải toàn bộ chuỗi `/store/api/books/42` đều thuộc về `@GetMapping`. Servlet container phải xác định **ứng dụng web (context)**, tiếp theo chọn **servlet nhận request**, rồi Spring MVC mới tìm **controller handler**. Hiểu ba tầng này giúp cấu hình URL chính xác, triển khai WAR/JAR, xử lý reverse proxy và chẩn đoán những lỗi 404/405 tưởng như vô lý.

Bài học tập trung vào **Spring MVC chạy trên Jakarta Servlet stack**, phù hợp kiến trúc Spring Framework 6 / Spring Boot 3, Java 17+. Spring WebFlux là một web stack khác; không dùng cấu trúc `DispatcherServlet` của MVC để suy luận cho WebFlux.

## 1. Mục tiêu và ba tầng ánh xạ

Sau bài này, bạn có thể:

- Phân biệt **context path**, **URL pattern của servlet** và **mapping của controller**.
- Hiểu vì sao các pattern `/`, `/*`, `/api/*`, `*.do` khác nhau và servlet nào được chọn.
- Đọc chính xác `getRequestURI()`, `getContextPath()`, `getServletPath()`, `getPathInfo()` và `getQueryString()`.
- Cấu hình `server.servlet.context-path`, hiểu ý nghĩa của `spring.mvc.servlet.path` và viết `@RequestMapping` đúng vị trí.
- Biết cách servlet được đăng ký lúc khởi tạo ứng dụng: Spring Boot embedded server hoặc WAR trên container độc lập.
- Kiểm tra endpoint thực tế bằng HTTP client và phân biệt lỗi đến từ container, Spring MVC hay reverse proxy.

Mô hình tổng quan:

~~~text
Client
  GET /store/api/books/42?lang=vi
               |
               v
Servlet container (Tomcat, Jetty, ...)
  chọn web application theo context path: /store
               |
               v
Servlet URL mapping
  chọn DispatcherServlet theo URL pattern, ví dụ "/"
               |
               v
Spring MVC DispatcherServlet
  chọn handler cho GET + "/api/books/42"
               |
               v
Controller method
  @GetMapping("/{id}") → id=42
               |
               v
Response: HTTP status + headers + body
~~~

**Nguyên tắc:** URL ngoài trình duyệt chịu ảnh hưởng bởi **server origin**, **context path**, **servlet mapping** và **route của ứng dụng**. Query string là dữ liệu truy vấn, không phải phần để servlet container so khớp URL mapping.

## 2. Phân tích URL trước khi gắn annotation

Ví dụ giả định:

~~~text
http://localhost:8080/store/api/books/42?lang=vi#details
|______ origin _____| |context| |controller path| |query| fragment
                     /store    /api/books/42    lang=vi
~~~

Cách ghi trên chỉ minh họa bố cục; trong URL thật **origin** gồm scheme `http`, host `localhost` và port `8080` (nếu có). `#details` là fragment phía client, **không được gửi trong HTTP request-target**. Khi `DispatcherServlet` được map `/`, servlet không thêm một đoạn path riêng vào URL; request đến controller nhờ path `/api/books/42`.

| Thành phần | Giá trị ví dụ | Ai quyết định? |
| --- | --- | --- |
| Scheme, host, port | `http://localhost:8080` | Server/network, client, và có thể cả reverse proxy |
| Context path | `/store` | Cấu hình triển khai web application/servlet container |
| Servlet mapping | `/` | Servlet registration; trường hợp này không thêm prefix vào URL |
| Controller mapping | `/api/books/42` | Spring MVC `@RequestMapping` + `@GetMapping` |
| Query string | `lang=vi` | Client; được tách ra khỏi path mapping |
| Fragment | `#details` | Client sử dụng, không chuyển lên HTTP server |

Nếu `DispatcherServlet` được map theo prefix `/mvc/*`, URL ứng dụng có thể là `/store/mvc/api/books/42`. Khi ấy **`/mvc` thuộc servlet mapping**, còn handler Spring MVC tiếp tục ánh xạ phần bên trong servlet là `/api/books/42`.

### 2.1. Context path là gì?

**Servlet context** đại diện cho một web application được triển khai trong container. Context path là tiền tố URL mà container dùng để xác định application tương ứng. Ví dụ cùng host có thể phục vụ hai ứng dụng độc lập:

~~~text
https://example.test/shop/...   → web application "shop"
https://example.test/admin/...  → web application "admin"
~~~

Trong một ứng dụng có context path `/shop`, request đến `/shop/api/items` được chuyển vào ứng dụng đó rồi mới kiểm tra servlet mapping. Context path **không phải một `@RequestMapping` của controller**.

Theo Servlet specification, ứng dụng ở context root có `request.getContextPath()` bằng **chuỗi rỗng `""`**, dù người dùng thường nói ứng dụng chạy ở đường dẫn gốc `/`. Khi cấu hình context path `/shop`, `getContextPath()` thường là `"/shop"`. Không nên mặc định chuỗi gốc được trả về là `"/"`.

### 2.2. Servlet mapping là gì?

Trong mỗi context, servlet container đăng ký các servlet với tên và một hoặc nhiều URL pattern, ví dụ `/api/*`, `*.action`, `/health` hoặc `/`. Khi request đi vào ứng dụng, container áp dụng quy tắc Servlet URL matching để quyết định **servlet nào được gọi**. Đây là một tầng **trước Spring MVC controller mapping**.

Trong Spring MVC, servlet trọng tâm là `org.springframework.web.servlet.DispatcherServlet`, đóng vai trò *front controller*. Nó nhận request đã được container chọn, rồi chuyển việc cho `HandlerMapping`, `HandlerAdapter`, controller và các thành phần Spring MVC khác.

### 2.3. Controller mapping là gì?

`@RequestMapping` tại cấp class, `@GetMapping`, `@PostMapping` và các annotation tương tự chọn **handler method trong Spring MVC**. Ví dụ:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {
    @GetMapping("/{id}")
    public String read(@PathVariable long id) {
        return "book-" + id;
    }
}
~~~

Đây là **đoạn controller minh họa**, cần đặt trong ứng dụng Spring MVC, import annotation và có component scanning. Mapping hiệu lực của method là `GET /api/books/{id}` trong phạm vi `DispatcherServlet`; không tự cộng `/store` vào annotation.

## 3. Servlet URL mapping theo đặc tả Jakarta Servlet

Servlet specification cho phép một servlet đăng ký nhiều dạng URL pattern. Container chọn theo mức ưu tiên sau, trong phạm vi context đã xác định:

1. **Exact match**: khớp chính xác đường dẫn, ví dụ `/health`.
2. **Longest path-prefix match**: chọn prefix dài nhất trong các pattern dạng `/path/*`.
3. **Extension match**: so khớp phần mở rộng, ví dụ `*.jsp` hoặc `*.action`.
4. **Default servlet mapping**: pattern `/` được dùng khi không có pattern ưu tiên hơn phù hợp.

Đây là **quy tắc chọn servlet**, không phải thứ tự ưu tiên giữa các method `@GetMapping` trong Spring MVC.

| Pattern | Loại | Ví dụ được khớp | Ghi chú |
| --- | --- | --- | --- |
| `/health` | Exact | `/health` | Không tự khớp `/health/details`. |
| `/api/*` | Path-prefix | `/api/books`, `/api/books/42` | Mọi đường dẫn bên dưới prefix thích hợp; có thể cạnh tranh với exact/prefix dài hơn. |
| `/api/admin/*` | Path-prefix dài hơn | `/api/admin/users` | Ưu tiên hơn `/api/*` nếu cùng khớp. |
| `*.action` | Extension | `/orders/create.action` | Chọn theo hậu tố khi exact/prefix chưa khớp. |
| `/` | Default mapping | Đường dẫn không thuộc mapping ưu tiên hơn | **Khác `/*`**, không phải pattern path-prefix thông thường. |
| `/*` | Path-prefix bao quát | Gần như mọi đường dẫn trong context | Có thể chặn đường tới JSP/default servlet hoặc servlet khác nếu không có exact/prefix ưu tiên. |
| `""` | Context-root exact | Request tới context root | Trường hợp đặc biệt; khác `/`. |

**`/` và `/*` là điểm dễ sai nhất.** Nếu mapping `DispatcherServlet` bằng `/`, nó hoạt động như default servlet mapping và những servlet khác với exact/prefix/extension mapping vẫn có thể nhận request theo thứ tự ưu tiên. Nếu mapping bằng `/*`, đây là một path-prefix mapping rộng: nó có thể bắt cả những request từng đi tới extension mapping/JSP, gây 404 và xung đột xử lý. Khi xây một Spring MVC app thông thường, **mapping `/` là lựa chọn mặc định phù hợp**.

### 3.1. Ví dụ hai servlet tranh quyền nhận request

Giả định một web application tại `/store` có:

~~~text
catalogServlet  → /api/*
adminServlet    → /api/admin/*
statusServlet   → /health
jspServlet      → *.jsp
defaultServlet  → /
~~~

Các URL được chọn như sau:

| Request path không tính `/store` | Servlet được chọn | Lý do |
| --- | --- | --- |
| `/health` | `statusServlet` | Exact match |
| `/api/books/1` | `catalogServlet` | Prefix `/api/*` |
| `/api/admin/users` | `adminServlet` | Prefix dài hơn |
| `/views/home.jsp` | `jspServlet` | Extension match |
| `/images/logo.png` | `defaultServlet` | Không có match ưu tiên hơn |

Kết quả trên **chỉ nói servlet nào được gọi**, không chứng minh servlet đó sẽ trả 200: nó còn phải xử lý được method, tài nguyên và nghiệp vụ tương ứng.

### 3.2. Cấu trúc request path trong Servlet API

Servlet API tách request URI thành các phần. Trong ngữ cảnh thông thường (không xét các sai khác mã hóa/ký tự đặc biệt), có thể hình dung:

~~~text
requestURI ≈ contextPath + servletPath + (pathInfo nếu có)
~~~

Không dùng phương trình đó như phép ghép chuỗi thô với mọi URL: `getRequestURI()` giữ URI chưa được giải mã theo cách khác với `getServletPath()`/`getPathInfo()`; container có quy tắc giải mã, chuẩn hóa và từ chối URI đáng ngờ.

| API | Ý nghĩa | Có bao gồm query? |
| --- | --- | --- |
| `request.getRequestURI()` | Phần path của URI request, thường bao gồm context path | **Không** |
| `request.getContextPath()` | Tiền tố context của ứng dụng; root context trả chuỗi rỗng | Không |
| `request.getServletPath()` | Phần path liên quan đến mapping đã chọn của servlet | Không |
| `request.getPathInfo()` | Phần path nằm ngoài servlet path trong một số loại mapping, hoặc `null` | Không |
| `request.getQueryString()` | Query nguyên bản sau dấu `?`, hoặc `null` | Chỉ chứa query |
| `request.getRequestURL()` | URL request được container dựng, không chứa query string | Không |

Ví dụ **`DispatcherServlet` map `/mvc/*`**, context path `/store`:

~~~text
GET /store/mvc/api/books/42?lang=vi HTTP/1.1

getRequestURI()   = "/store/mvc/api/books/42"
getContextPath()  = "/store"
getServletPath()  = "/mvc"
getPathInfo()     = "/api/books/42"
getQueryString()  = "lang=vi"
~~~

Ví dụ **`DispatcherServlet` map `/`**, vẫn context path `/store`:

~~~text
GET /store/api/books/42?lang=vi HTTP/1.1

getRequestURI()   = "/store/api/books/42"
getContextPath()  = "/store"
getServletPath()  = "/api/books/42"
getPathInfo()     = null
getQueryString()  = "lang=vi"
~~~

Sự khác biệt ở `servletPath`/`pathInfo` là **hệ quả của servlet mapping type**, không có nghĩa đường dẫn controller phải thay đổi. Bạn có thể kiểm tra chính xác mapping hiện tại bằng `request.getHttpServletMapping()` trong Jakarta Servlet 4.0+.

## 4. Spring MVC định tuyến sau khi Servlet container chọn DispatcherServlet

Một request qua nhiều tầng:

~~~text
HTTP request
  → Servlet container xác định context
  → Servlet mapping xác định DispatcherServlet
  → Filter chain chạy theo mapping/dispatcher type đã cấu hình
  → DispatcherServlet
      → HandlerMapping chọn handler (method, path và điều kiện khác)
      → HandlerAdapter gọi handler
      → controller / service
      → HttpMessageConverter hoặc view rendering
  → HTTP response
~~~

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/api")
class ApiController {
    @GetMapping("/books/{id}")
    public String find(@PathVariable long id) {
        return "book-" + id;
    }
}
~~~

Mapping handler là `GET /api/books/{id}`. Với context path `/store` và dispatcher mapping `/`, client gọi `GET /store/api/books/42`. Trong trường hợp prefix `/mvc/*` của dispatcher, URL dự kiến là `GET /store/mvc/api/books/42`. Spring MVC cố xác định path **nằm bên trong phạm vi servlet** để so khớp handler, chứ không yêu cầu `@GetMapping` viết cả tên context.

Spring MVC còn xét điều kiện bổ sung của mapping: HTTP method, `params`, `headers`, `consumes`, `produces` khi được chỉ định. Vì vậy đúng path chưa chắc đủ: gửi POST vào handler chỉ nhận GET thường dẫn tới 405, còn media type/Accept không phù hợp có thể dẫn tới 415/406, tùy ngữ cảnh.

### 4.1. PathPatternParser, ký tự mã hóa và servlet prefix

Spring MVC phiên bản hiện đại hỗ trợ `PathPatternParser` để so khớp **theo từng segment**, tránh một số vấn đề khi giải mã toàn bộ path rồi so chuỗi. Từ Spring Framework 6, đây là chiến lược mặc định của Spring MVC. Tuy nhiên **phiên bản Spring Boot và cách cấu hình `spring.mvc.servlet.path` có thể có ràng buộc tương thích**; một số nhánh Boot 3 ghi rõ `PathPatternParser` mặc định không tương thích với servlet prefix mapping theo cơ chế của Boot. Nếu bắt buộc dùng prefix, cần đối chiếu tài liệu của **phiên bản Boot cụ thể**, chọn chiến lược matching được hỗ trợ và chạy kiểm thử routing thay vì cho rằng mọi cấu hình sẽ hoạt động giống nhau.

Không tự xây route bằng:

~~~java
// Tránh giả định đơn giản hóa này trong code production:
String path = request.getRequestURI()
                     .substring(request.getContextPath().length());
~~~

Đoạn trên chỉ minh họa **cách làm nên tránh**, không phải ví dụ API an toàn: nó chưa giải quyết servlet prefix, encoded slash, matrix variables, proxy path rewriting và những trường hợp Servlet API trả giá trị đã giải mã/chuẩn hóa khác nhau. Trong Spring MVC hãy ưu tiên `@RequestMapping`, `@PathVariable`, `@RequestParam` và API xây dựng URI chính thức của framework.

## 5. Cấu hình context path khi chạy Spring Boot

Spring Boot với embedded Servlet container tự khởi tạo web server và đăng ký `DispatcherServlet` khi có starter MVC thích hợp. Trong ứng dụng Spring Boot 3 thông thường, DispatcherServlet được map tại `/`. Context path mặc định ở root nên URL không có tiền tố ứng dụng riêng.

Để đặt **context path**:

~~~properties
# src/main/resources/application.properties
server.port=8080
server.servlet.context-path=/store
~~~

Hoặc YAML tương đương:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /store
~~~

Với controller mapping `/api/books/{id}`, URL public trực tiếp sẽ là:

~~~text
http://localhost:8080/store/api/books/42
~~~

**Không thêm `/store` vào `@RequestMapping`**. Nếu bạn viết `@RequestMapping("/store/api/books")` trong khi đã cấu hình `server.servlet.context-path=/store`, route trong ứng dụng sẽ bị cộng thành `/store/store/api/books/... ` và client gọi URL dự kiến sẽ gặp lỗi. Sửa bằng cách tách đúng tầng cấu hình, không nhân đôi prefix.

Tài liệu cấu hình thuộc Spring Boot, không phải thuộc tính chuẩn bắt buộc của mọi ứng dụng Spring Framework chạy trên container bên ngoài. Khi triển khai WAR vào một Tomcat độc lập, **container/deployment** có thể quyết định context path theo cấu hình, tên WAR hoặc descriptor; không nên giả định `server.servlet.context-path` luôn có hiệu lực giống executable JAR với embedded server.

### 5.1. Spring MVC servlet path: một tầng khác

Spring Boot có thuộc tính:

~~~properties
spring.mvc.servlet.path=/mvc
~~~

Về ý nghĩa, thuộc tính này dùng để đổi đường dẫn **đăng ký DispatcherServlet** dưới prefix, ví dụ từ `/` sang một mapping tương ứng `/mvc/*`. Nếu đồng thời có `server.servlet.context-path=/store`, handler `@GetMapping("/api/books/{id}")` sẽ được truy cập theo URL dự kiến:

~~~text
http://localhost:8080/store/mvc/api/books/42
~~~

Chỉ dùng cấu hình này khi thực sự cần **không gian URL dành riêng cho DispatcherServlet** hoặc phải dùng thêm servlet khác. Không lẫn:

| Thành phần | Thuộc tính/annotation | Tác động |
| --- | --- | --- |
| Web application context | `server.servlet.context-path=/store` | Prefix áp dụng cho toàn bộ web application |
| DispatcherServlet registration | `spring.mvc.servlet.path=/mvc` | Prefix cho các URL tới servlet MVC (nếu phiên bản/chiến lược matching hỗ trợ) |
| Controller route | `@RequestMapping("/api/books")` | Path bên trong Spring MVC |
| URL port | `server.port=8080` | Cổng lắng nghe của embedded server |

**Lưu ý tương thích:** ở một số bản Spring Boot 3.x, `spring.mvc.pathmatch.matching-strategy=path-pattern-parser` không làm việc cùng servlet prefix mapping; tài liệu Boot chỉ rõ giới hạn đó. Nếu gặp lỗi khởi tạo hoặc route không match khi đặt `spring.mvc.servlet.path`, kiểm tra đúng tài liệu phiên bản, xem lựa chọn `ant-path-matcher` được hỗ trợ hay không hoặc thiết kế lại mapping dùng context path và controller route. Không áp dụng sửa cấu hình này máy móc cho mọi bản Spring.

### 5.2. API path prefix không nhất thiết là servlet path

Giả sử chỉ cần các endpoint có URL `/api/v1/books`, bạn có thể đơn giản viết:

~~~java
@RestController
@RequestMapping("/api/v1/books")
class BookController {
    @GetMapping("/{id}")
    public String get(@PathVariable long id) {
        return "book-" + id;
    }
}
~~~

Nếu server ở root context và dispatcher mặc định `/`, URL là `/api/v1/books/42`. Không cần đổi `spring.mvc.servlet.path`. Ngược lại, nếu đổi servlet path chỉ để thêm `/api`, bạn đã tác động đến **mọi route xử lý bởi DispatcherServlet**, kể cả các route không thuộc nhóm API, MVC view/error handling hay tài nguyên động tùy cách cấu hình. Hãy chọn thay đổi nhỏ nhất đúng mục đích.

## 6. Ví dụ Spring Boot 3 hoàn chỉnh: tự xem cách path được chia

Đây là ví dụ **Java 17+** trong dự án Spring Boot 3 có dependency `spring-boot-starter-web`. Tệp `src/main/java/demo/web/WebPathApplication.java` chứa một public main class và một controller package-private; cả hai đều nằm trong package `demo.web`, bảo đảm component scanning tìm được controller.

~~~java
package demo.web;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class WebPathApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebPathApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping("/{id}")
    public PathResult describe(
            @PathVariable long id,
            @RequestParam(defaultValue = "vi") String lang,
            HttpServletRequest request) {

        return new PathResult(
                id,
                lang,
                request.getRequestURI(),
                request.getContextPath(),
                request.getServletPath(),
                request.getPathInfo(),
                request.getQueryString()
        );
    }

    record PathResult(
            long id,
            String lang,
            String requestURI,
            String contextPath,
            String servletPath,
            String pathInfo,
            String queryString
    ) {}
}
~~~

Ví dụ này không dùng external database. `@RestController` khiến Spring MVC serialize `PathResult` thành JSON thông qua `HttpMessageConverter` thích hợp (Jackson khi dùng starter web mặc định). `HttpServletRequest` được Spring đưa vào handler method từ request thực tế.

Tạo tệp `src/main/resources/application.properties`:

~~~properties
server.port=8080
server.servlet.context-path=/store
~~~

Giữ **`spring.mvc.servlet.path` không cấu hình**, tức dùng dispatcher mapping mặc định. Nếu dự án Gradle đã được cấu hình Spring Boot plugin và starter web, từ thư mục project chạy:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell dùng:

~~~powershell
.\gradlew.bat bootRun
~~~

Lệnh trên chỉ đúng nếu **Gradle project đã có wrapper và cấu hình Spring Boot phù hợp**; đoạn Java đơn lẻ không chạy bằng `javac WebPathApplication.java` vì phụ thuộc thư viện Spring/Servlet.

Gọi endpoint bằng curl:

~~~bash
curl -i "http://localhost:8080/store/api/books/42?lang=vi"
~~~

Phản hồi thành công có **HTTP 200** và JSON tương đương:

~~~json
{
  "id": 42,
  "lang": "vi",
  "requestURI": "/store/api/books/42",
  "contextPath": "/store",
  "servletPath": "/api/books/42",
  "pathInfo": null,
  "queryString": "lang=vi"
}
~~~

Thứ tự field/whitespace/headers JSON thực tế có thể thay đổi theo cấu hình Jackson/container, nhưng các giá trị path ở đây được kỳ vọng với URL đơn giản, context `/store` và dispatcher map `/`. Hãy chú ý ba điểm:

1. `requestURI` chứa `/store` nhưng **không chứa** `?lang=vi`.
2. `contextPath` là `/store`, còn `servletPath` là toàn bộ path bên trong context khi DispatcherServlet dùng default mapping `/`.
3. `pathInfo` là `null` trong trường hợp default mapping đó; giá trị của nó **không phải** `"/42"`.

Nếu thay URL bằng:

~~~bash
curl -i "http://localhost:8080/api/books/42?lang=vi"
~~~

Bạn đang thiếu `/store`, nên request thông thường **không đi vào context mong muốn** và nhận phản hồi lỗi tương ứng (thường là 404). Nếu thay bằng `/store/api/books/42` không có query, `lang` sẽ là `"vi"` nhờ giá trị mặc định trong `@RequestParam`, nhưng `queryString` sẽ là `null`.

### 6.1. Thí nghiệm đổi context path

Thay `server.servlet.context-path=/store` thành:

~~~properties
server.servlet.context-path=/catalog
~~~

Khởi động lại ứng dụng. Đường dẫn hiện hợp lệ:

~~~text
http://localhost:8080/catalog/api/books/42?lang=vi
~~~

Controller **không thay đổi một ký tự nào**. Kết quả sẽ có `contextPath="/catalog"`, `requestURI="/catalog/api/books/42"`, còn `servletPath="/api/books/42"`. Đây là phép thử trực quan cho việc **context path thuộc container**, không thuộc route của controller.

### 6.2. Thí nghiệm quan sát servlet mapping prefix (tùy phiên bản)

Giả định DispatcherServlet được đăng ký với pattern `/mvc/*` và hệ thống Spring MVC đã cấu hình tương thích với prefix mapping. Khi đó:

~~~text
Request            /store/mvc/api/books/42?lang=vi
Context path       /store
Servlet path       /mvc
Path info          /api/books/42
Controller route   /api/books/{id}
~~~

Những giá trị này minh họa **Servlet specification**. Không nên bật `spring.mvc.servlet.path=/mvc` trong ứng dụng đang chạy mà chưa đọc lưu ý tương thích với chiến lược matching nêu ở mục 5.1.

## 7. Đăng ký DispatcherServlet khi khởi tạo ứng dụng

Một servlet chỉ được nhận request sau khi **được container đăng ký**, có tên/instance và URL mapping. Có hai môi trường triển khai phổ biến.

### 7.1. Spring Boot executable JAR với embedded Servlet container

Thông thường:

1. Chạy `SpringApplication.run(...)`.
2. Spring Boot khởi tạo `ApplicationContext` và embedded server nếu ứng dụng là Servlet web app.
3. Boot auto-configure `DispatcherServlet` và đăng ký servlet với container, mặc định tại `/`.
4. Container bắt đầu nhận request ở cổng cấu hình.
5. Spring MVC sử dụng các handler mapping của `ApplicationContext` để tìm controller.

Khi dùng starter MVC chuẩn, **không cần tự khai báo `DispatcherServlet` trong `web.xml`**. Nếu đã có các đăng ký servlet tùy chỉnh hoặc cấu hình MVC đặc biệt, đừng giả định mặc định Boot còn nguyên.

### 7.2. Ứng dụng Spring MVC truyền thống triển khai WAR

Servlet container bên ngoài có thể đọc `WEB-INF/web.xml` để đăng ký DispatcherServlet. Ví dụ tối giản minh họa servlet mapping:

~~~xml
<servlet>
    <servlet-name>dispatcher</servlet-name>
    <servlet-class>org.springframework.web.servlet.DispatcherServlet</servlet-class>
    <load-on-startup>1</load-on-startup>
</servlet>

<servlet-mapping>
    <servlet-name>dispatcher</servlet-name>
    <url-pattern>/</url-pattern>
</servlet-mapping>
~~~

**Chỉ là đoạn khai báo liên quan đến mapping**, chưa phải `web.xml` hoàn chỉnh có đầy đủ schema, Spring context/config và cấu hình ứng dụng. Trong dự án hiện đại có thể dùng Java initializer thay XML. Điểm cốt lõi là `url-pattern` chọn servlet ở cấp Servlet container, còn `@RequestMapping` chọn controller ở cấp Spring.

Với Java configuration, Spring MVC hỗ trợ `WebApplicationInitializer` và các lớp tiện ích như `AbstractAnnotationConfigDispatcherServletInitializer`. Một ví dụ initializer cho WAR:

~~~java
package demo.web;

import org.springframework.web.servlet.support
        .AbstractAnnotationConfigDispatcherServletInitializer;

public class WebInitializer
        extends AbstractAnnotationConfigDispatcherServletInitializer {

    @Override
    protected Class<?>[] getRootConfigClasses() {
        return null;
    }

    @Override
    protected Class<?>[] getServletConfigClasses() {
        return new Class<?>[] { WebMvcConfig.class };
    }

    @Override
    protected String[] getServletMappings() {
        return new String[] { "/" };
    }
}
~~~

Ở đây `WebMvcConfig` là **lớp cấu hình Spring MVC của ứng dụng phải có sẵn**, ví dụ `@Configuration`, `@EnableWebMvc`, `@ComponentScan`; ví dụ initializer không được coi là tệp Java độc lập chạy ngay khi thiếu lớp đó. Chỉ sử dụng **một cơ chế registration chủ động, nhất quán**; việc vừa đăng ký cùng servlet qua XML vừa qua initializer có thể gây xung đột.

### 7.3. Đăng ký một servlet phụ bên cạnh DispatcherServlet

Spring Boot có thể đăng ký thêm `Servlet` qua `ServletRegistrationBean` khi cần một endpoint servlet truyền thống độc lập. Đoạn dưới là **ví dụ class cấu hình** đặt trong Spring Boot Servlet application có servlet API:

~~~java
package demo.web;

import java.io.IOException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ExtraServletConfig {

    @Bean
    ServletRegistrationBean<HttpServlet> extraServlet() {
        HttpServlet servlet = new HttpServlet() {
            @Override
            protected void doGet(
                    HttpServletRequest request,
                    HttpServletResponse response) throws IOException {
                response.setContentType("text/plain;charset=UTF-8");
                response.getWriter().write("legacy servlet");
            }
        };

        return new ServletRegistrationBean<>(servlet, "/legacy/*");
    }
}
~~~

Nếu context path là `/store`, URL `/store/legacy/test` được container ánh xạ vào servlet này nhờ prefix `/legacy/*`. Theo Servlet matching, `/legacy/*` được ưu tiên hơn default mapping `/` của DispatcherServlet. Response body minh họa chính xác:

~~~text
legacy servlet
~~~

Không tạo `@GetMapping("/legacy/test")` cho request này chỉ để nó hoạt động; ở ví dụ này **servlet phụ đã nhận request trước**, Spring MVC controller không tham gia. Cần nhớ `Filter` cũng có mapping riêng và có thể áp dụng với cả hai servlet, tùy cách đăng ký.

## 8. Phân biệt servlet mapping và Filter mapping

`Filter` (ví dụ logging, authentication, CORS handling tùy hệ thống) có thể được đăng ký với URL pattern hoặc servlet name. Đây là **chuỗi filter của container**, không phải `@RequestMapping` và cũng không quyết định controller method trực tiếp.

Ví dụ:

~~~text
Filter mapping: /*          → chạy cho đường dẫn phù hợp trong context
DispatcherServlet: /         → servlet MVC mặc định
LegacyServlet: /legacy/*     → servlet riêng
~~~

Khi gọi `/store/legacy/test`, filter match `/*` vẫn có thể chạy; sau đó container chọn LegacyServlet. Cũng cùng URL pattern `/*`, nhưng dùng cho **filter mapping** có ý nghĩa khác việc đăng ký **DispatcherServlet mapping** bằng `/*`.

Filter không tự được áp dụng cho mọi loại dispatch nếu chưa cấu hình: `REQUEST`, `FORWARD`, `INCLUDE`, `ASYNC`, `ERROR` có thể ảnh hưởng. Hãy kiểm tra `DispatcherType` và thứ tự chain thực tế khi xử lý lỗi, forward hay async.

## 9. Reverse proxy, ingress và đường dẫn ngoài ứng dụng

Khi triển khai thật, URL trình duyệt thấy có thể **khác URL mà container nhận**. Ví dụ:

~~~text
Client:
  https://example.test/platform/store/api/books/42
       |
       v
Reverse proxy:
  bỏ tiền tố /platform
  forward tới http://backend:8080/store/api/books/42
       |
       v
Spring Boot:
  context path = /store
  DispatcherServlet = /
  controller mapping = /api/books/{id}
~~~

Trong ví dụ này, `/platform` thuộc **route của proxy**, không tự động trở thành `request.getContextPath()`. Nếu app tự sinh link redirect theo URL nội bộ và không biết external prefix, client có thể bị dẫn tới URL thiếu `/platform`.

Proxy có thể truyền metadata như `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Prefix`. Spring Boot Servlet app có các cơ chế như `server.forward-headers-strategy` (ví dụ `NATIVE` hoặc `FRAMEWORK`) để xử lý forwarded headers khi môi trường cho phép. **Chỉ tin các forwarded headers từ reverse proxy đáng tin cậy**: nếu client ngoài Internet tự đặt được chúng, việc tạo redirect hoặc xác định host/scheme có thể sai hoặc không an toàn.

Đừng đồng thời thêm `/platform` vào cả ingress rewrite, context path và controller mapping chỉ vì thấy URL browser có prefix đó. Hãy xác định **proxy có giữ hay bỏ prefix** trước tiên, rồi cấu hình một nguồn sở hữu rõ ràng.

### 9.1. Static resources và root path

Trong Spring Boot MVC, static resources có thể được phục vụ từ các thư mục classpath tiêu chuẩn như `/static`, `/public` theo các cấu hình mặc định; handler mapping cho static resources có thể dùng pattern `/**`. Điều này là **Spring MVC resource handler mapping**, khác với **default servlet URL mapping `/`** ở Servlet container.

Vì vậy request trả 404 không luôn có nghĩa “không có servlet”: có thể request đã đi qua DispatcherServlet, bị handler static resources nhận rồi phát hiện file không tồn tại. Những khác biệt này ảnh hưởng exception được phát ra và cách `@ControllerAdvice` quan sát 404.

## 10. Quy trình debug khi path trả 404 hoặc 405

Giả sử bạn mong đợi `GET /store/api/books/42`:

1. **Kiểm tra origin và context path.** Server đang lắng nghe cổng nào? App đã deploy tại `/store`, `/` hay một tên WAR khác?
2. **Kiểm tra servlet registration/mapping.** DispatcherServlet đang map `/`, `/mvc/*` hay `/*`? Có servlet khác với exact/prefix/extension mapping ưu tiên hơn không?
3. **Kiểm tra controller mapping thực.** Tổng của class-level và method-level `@RequestMapping` là gì? Annotation có đúng method/params/headers/consumes/produces không?
4. **So request path sau proxy.** Proxy giữ hay xóa prefix? Có rewritten URL, trailing slash, encoded path hoặc route gateway không?
5. **Xem response thực tế.** 404 thường liên quan path/tài nguyên không match; 405 cho biết method không được phép trong ngữ cảnh tương ứng; 401/403 có thể đến từ security filter trước khi vào controller.
6. **Đối chiếu logs/tracing và handler mappings.** Nếu dùng Spring Boot Actuator và endpoint mappings được bật/cấp quyền phù hợp, có thể xem mapping đã đăng ký. Không công khai thông tin này ngoài môi trường quản trị.

Thử với curl:

~~~bash
curl -i "http://localhost:8080/store/api/books/42?lang=vi"
curl -i "http://localhost:8080/api/books/42?lang=vi"
curl -i -X POST "http://localhost:8080/store/api/books/42"
~~~

Với controller ví dụ chỉ có `@GetMapping`:
- Request đầu thường thành công 200.
- Request thứ hai thiếu `/store` nên thường 404.
- Request thứ ba có đúng URI trong context nhưng method không được controller hỗ trợ; thường dẫn tới 405 (nếu không có filter/proxy/handler khác can thiệp).

**Đừng chỉ nhìn body lỗi dạng JSON.** Trạng thái HTTP, `Allow` header trong 405, cấu hình security, route proxy và log về handler được chọn giúp xác định tầng nào đã từ chối request.

### 10.1. Những lỗi hay gặp và cách sửa

| Dấu hiệu | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Controller đúng nhưng `/api/...` trả 404 | Đã đặt `server.servlet.context-path=/store` | Gọi `/store/api/...`, không đổi controller. |
| URL có `/store/store/api/...` | Đã cộng context prefix vào cả controller | Bỏ `/store` khỏi handler mapping. |
| Prefix `/mvc` làm route không match | Servlet prefix khác với path của controller hoặc xung đột matching strategy | Kiểm tra registration, Servlet API path parts và compatibility phiên bản. |
| JSP/extension routes đột nhiên hỏng | Dùng dispatcher mapping `/*` quá rộng | Xem lại default mapping `/` và thứ tự servlet match. |
| Endpoint nhận GET nhưng không nhận POST | Method mapping không hỗ trợ POST | Dùng đúng method hoặc thêm handler POST theo hợp đồng API. |
| Dịch vụ sau ingress redirect sai hostname/path | Forwarded headers hoặc rewrite chưa đúng | Kiểm tra external/internal URL, trusted proxy và strategy xử lý forwarding. |
| Static file trả 404 dù controller khác hoạt động | Static resource location/pattern không phù hợp | Kiểm tra resource handler và vị trí file. |
| `getServletPath()` không như kỳ vọng | Servlet mapping khác `/` | Đọc `getHttpServletMapping()`, `getPathInfo()`, không suy từ URL bằng tay. |

## 11. Bài tập thực hành và đáp án

**Bài 1.** Ứng dụng có `server.servlet.context-path=/academy`, DispatcherServlet mapping `/`, controller:

~~~java
@RestController
@RequestMapping("/courses")
class CourseController {
    @GetMapping("/{id}")
    public String get(@PathVariable long id) {
        return "course-" + id;
    }
}
~~~

URL nào gọi được method cho id 7? Nếu app đang ở origin `http://localhost:8080` và không có route khác can thiệp, body là gì?

**Bài 2.** Với context path `/academy` và DispatcherServlet URL pattern `/mvc/*`, request là `/academy/mvc/courses/7?lang=vi`. Hãy cho các giá trị `requestURI`, `contextPath`, `servletPath`, `pathInfo`, `queryString`.

**Bài 3.** Trong cùng application, Servlet A map `/`, Servlet B map `*.jsp`, Servlet C map `/api/*`. Servlet nào nhận `/api/books`, `/view.jsp`, `/favicon.ico`?

**Bài 4.** Tại sao đổi `@RequestMapping("/courses")` thành `@RequestMapping("/academy/courses")` không phải cách đúng để xử lý context path `/academy`?

**Bài 5.** Proxy phục vụ `/platform/academy/courses/7` nhưng forward nội bộ thành `/academy/courses/7`. Khi đọc `getContextPath()` trong app sẽ thu được `/platform/academy` hay `/academy` theo request nội bộ thông thường? App cần cân nhắc thêm vấn đề gì khi tạo external links?

### Đáp án có giải thích

1. URL `http://localhost:8080/academy/courses/7`. Body text `course-7` (với converter/cấu hình mặc định hỗ trợ `String` response); route không viết context path vào annotation.
2. `requestURI="/academy/mvc/courses/7"`, `contextPath="/academy"`, `servletPath="/mvc"`, `pathInfo="/courses/7"`, `queryString="lang=vi"`, với path đơn giản theo Servlet specification.
3. `/api/books` do C nhận (prefix mapping); `/view.jsp` do B nhận (extension mapping); `/favicon.ico` do A nhận (default mapping).
4. Vì context path đã do container áp dụng. Viết thêm `/academy` trong controller sẽ sinh đường dẫn `/academy/academy/courses/7` trong cấu hình đó.
5. Theo request nội bộ thông thường, context path là `/academy`, không phải `/platform/academy`. Khi sinh link cần nhận diện external URL, prefix rewrite và xử lý forwarded headers từ proxy tin cậy.

## 12. Checklist tư duy khi xây URL trong Spring Web

Để xác định URL chính xác, lần lượt trả lời:
1. **Ứng dụng chạy ở đâu?** Scheme/host/port nào client truy cập; proxy rewrite ra sao?
2. **Application nào nhận request?** Context path thực tế là gì?
3. **Servlet nào nhận request?** URL pattern đăng ký của DispatcherServlet hay servlet phụ là gì?
4. **Handler nào được chọn?** Controller class/method mapping và các điều kiện HTTP có khớp?
5. **Thực tế container đã thấy gì?** Kiểm tra Servlet API path components, mapping type, request URL và logs.

Bốn nguyên tắc cần giữ: **context path** là tiền tố của ứng dụng web; **servlet mapping** chọn servlet ở tầng container; **controller mapping** chọn handler bên trong Spring MVC; **proxy path** là một tầng độc lập có thể rewrite URL. Khi tách đúng trách nhiệm, việc triển khai JAR/WAR, đổi prefix và tìm lỗi routing sẽ nhất quán hơn rất nhiều.

**Tài liệu chuẩn đối chiếu:** Jakarta Servlet Specification 6.0, mục *Request Path Elements* và *Mapping Requests to Servlets* (https://jakarta.ee/specifications/servlet/6.0/jakarta-servlet-spec-6.0.html); Spring Framework MVC *DispatcherServlet* và *Path Matching* (https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html); Spring Boot Reference *Servlet Web Applications*, *Spring MVC* và *Embedded Web Servers* (https://docs.spring.io/spring-boot/reference/web/servlet.html; https://docs.spring.io/spring-boot/how-to/spring-mvc.html).