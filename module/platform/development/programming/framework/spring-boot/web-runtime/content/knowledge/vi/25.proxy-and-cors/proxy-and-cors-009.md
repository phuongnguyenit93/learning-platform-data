# Allowed origins, methods, headers và exposed headers trong Spring Boot — cấu hình CORS đúng và an toàn

## 1. CORS giải quyết vấn đề gì?

**CORS (Cross-Origin Resource Sharing)** là cơ chế giao thức HTTP cho phép một server thông báo với **browser** rằng JavaScript từ một origin khác có được phép truy cập response của server hay không, và trong những trường hợp cần thiết, browser được phép gửi request thật sau bước kiểm tra trước (*preflight*).

Ví dụ frontend được mở tại `http://localhost:5173`, backend Spring Boot lắng nghe `http://localhost:8080`:

~~~text
Browser: trang HTML/JS từ http://localhost:5173
                    |
                    | fetch("http://localhost:8080/api/message")
                    v
Spring Boot:           http://localhost:8080
                    |
                    | CORS response headers
                    v
Browser: quyết định có cho JavaScript đọc response không
~~~

Hai địa chỉ này **khác origin vì khác port**, dù cùng hostname `localhost`. Một origin là bộ ba **scheme + host + port**. `https://app.example.test` khác `http://app.example.test`; `https://app.example.test` khác `https://api.example.test`; `http://localhost:3000` khác `http://localhost:5173`. Đường dẫn như `/admin`, `/login` **không phải thành phần của origin**.

**CORS không phải authentication hay authorization.** Một request CORS được phép vẫn cần login, role, quyền đọc tài nguyên, CSRF defense và validation. Ngược lại, `curl`/server-to-server client không bị browser CORS enforcement chặn: chúng có thể gọi endpoint dù response không có `Access-Control-Allow-Origin`. CORS hạn chế **quyền JavaScript đọc kết quả qua trình duyệt**, không phải firewall của API.

Ví dụ một request cross-origin:

~~~http
GET /api/message HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
~~~

Response có thể bao gồm:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Vary: Origin
Content-Type: application/json

{"message":"hello"}
~~~

Browser kiểm tra header và cho script của origin được phép đọc body. Nếu header CORS thiếu hoặc không khớp, request có thể **đã đến server và server đã xử lý**, nhưng browser chặn JavaScript đọc response. Vì vậy “Network thấy 200 nhưng fetch báo CORS” là hiện tượng có thật.

## 2. Bốn khái niệm cốt lõi phải phân biệt

| Cấu hình Spring | Header HTTP chính tương ứng | Điều kiểm soát | Không kiểm soát |
| --- | --- | --- | --- |
| `allowedOrigins` / `allowedOriginPatterns` | `Access-Control-Allow-Origin` | **Trang web nào** được phép đọc response qua browser | Người dùng có được xác thực/ủy quyền không |
| `allowedMethods` | `Access-Control-Allow-Methods` trên preflight | **Phương thức HTTP dự kiến** mà browser được phép gửi từ origin khác | Controller có thực hiện method đó hoặc user có quyền không |
| `allowedHeaders` | `Access-Control-Allow-Headers` trên preflight | **Request headers do script muốn gửi** | Response headers nào script được đọc |
| `exposedHeaders` | `Access-Control-Expose-Headers` trên actual response | **Response headers ngoài safelist** mà JavaScript được đọc | Request headers client có thể gửi |

Đọc bảng theo hai chiều:

~~~text
Browser → Spring Boot (request)
  allowedOrigins  : Origin nào được chấp nhận?
  allowedMethods  : GET/POST/PUT/DELETE/... nào được phép?
  allowedHeaders  : Authorization, Content-Type, X-Request-Id,... nào được gửi?

Spring Boot → Browser (response)
  exposedHeaders  : Location, X-Request-Id, ETag,... nào cho JS đọc?
~~~

**Bẫy phổ biến nhất:** thêm `Authorization` vào `exposedHeaders` không giúp browser gửi Authorization; phải cấu hình `allowedHeaders`. Thêm `X-Request-Id` vào `allowedHeaders` không giúp JavaScript đọc `X-Request-Id` trả về; phải cấu hình `exposedHeaders`.

## 3. Allowed origins: khớp chính xác origin, không phải URL hay path

### 3.1. `allowedOrigins`

Cấu hình ví dụ:

~~~java
.allowedOrigins(
    "http://localhost:5173",
    "https://app.example.test"
)
~~~

Nó cho phép JS từ hai origin đó gọi những URL backend được mapping CORS tương ứng. Những origin như `https://evil.example.test` hoặc `http://localhost:3000` không được cho phép, trừ khi khai báo riêng.

Một response CORS thường chỉ có **một** giá trị origin:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

Không phải:

~~~http
Access-Control-Allow-Origin: https://app.example.test, https://other.example.test
~~~

`Access-Control-Allow-Origin` không chấp nhận danh sách nhiều origin phân tách bằng dấu phẩy. Khi backend cho nhiều origin, nó phải so khớp incoming `Origin` với allowlist, rồi trả **origin cụ thể** phù hợp cho request ấy. Cần `Vary: Origin` khi response có thể thay đổi theo Origin để các shared caches không tái sử dụng nhầm biến thể.

**Không đưa trailing slash hoặc path vào allowed origin**: cấu hình `https://app.example.test`, không phải `https://app.example.test/checkout`. Browser gửi giá trị `Origin` dạng scheme/host/port hoặc dạng đặc biệt `null`.

### 3.2. Wildcard origin và credential

~~~java
.allowedOrigins("*")
.allowCredentials(true)
~~~

là cấu hình **không hợp lệ/không an toàn** cho credentialed browser requests. Browser không chấp nhận `Access-Control-Allow-Origin: *` khi request có credentials. Spring Framework cũng không cho phép dùng `*` trong `allowedOrigins` kết hợp `allowCredentials(true)` theo quy tắc cấu hình của nó.

Nếu tài nguyên **thực sự public, không credentialed**, wildcard có thể hợp lý:

~~~http
Access-Control-Allow-Origin: *
~~~

Nhưng nếu dùng cookie/session/auth HTTP, cần các origin xác định:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
~~~

Điều này cũng cần client chọn chế độ gửi credentials khi thích hợp; chỉ bật server-side credentials không ép browser gửi cookie.

### 3.3. `allowedOriginPatterns`

Spring hỗ trợ pattern khi cần nhiều subdomain:

~~~java
.allowedOriginPatterns("https://*.example.test")
.allowCredentials(true)
~~~

Khác `allowedOrigins("*")`, khi pattern match, Spring có thể trả **origin thực tế đã match** thay vì chuỗi `*`, phù hợp nguyên tắc credentialed CORS.

**Đánh giá bảo mật:** một subdomain như `team.example.test` được cho phép nếu nằm trong pattern, kể cả khi subdomain đó thuộc bên thứ ba hoặc có nguy cơ bị takeover. Pattern quá rộng thường nới trust boundary không cần thiết. Khi chỉ có 2–3 frontend cố định, ưu tiên `allowedOrigins` liệt kê chính xác. Không dùng `allowedOriginPatterns("*")` với credentials để “cho mọi website được đọc dữ liệu đã xác thực”.

### 3.4. `Origin: null`

Một số trang từ `file://`, sandboxed iframe hoặc origin không thể tuần tự hóa thành tuple thông thường có thể gửi:

~~~http
Origin: null
~~~

Không nên thêm `"null"` vào allowlist chỉ để làm file HTML local hết báo lỗi; nó có thể mở quyền cho nhiều bối cảnh opaque origin không đáng tin. Phát triển frontend bằng local dev server như Vite, hoặc thiết kế môi trường test chính xác. CORS không phải cơ chế xác định danh tính của site bằng một header người dùng không thể giả mạo ngoài browser.

## 4. Allowed methods: cho phép phương thức chứ không tự tạo endpoint

`allowedMethods` định nghĩa những phương thức cross-origin browser có thể yêu cầu:

~~~java
.allowedMethods("GET", "POST", "PATCH", "DELETE")
~~~

Khi browser gửi preflight hỏi về `POST`, Spring xác nhận nó có nằm trong danh sách không và trả `Access-Control-Allow-Methods` phù hợp.

**Phân biệt ba vấn đề:**

1. CORS cho phép method `POST` từ origin X.
2. Spring MVC có thật sự khai báo `@PostMapping` tại URL đó không.
3. User gửi POST có được phép thực hiện hành động theo Spring Security/authorization không.

Nếu CORS cho phép POST nhưng controller chỉ có GET, request thật vẫn có thể nhận **405 Method Not Allowed**. Nếu controller có DELETE nhưng CORS chỉ cho GET, browser từ origin khác không thể đi qua preflight để dùng DELETE. CORS không tự cấp quyền nghiệp vụ.

### `OPTIONS` không cần tự thêm vào `allowedMethods` chỉ để preflight hoạt động

Preflight **dùng HTTP OPTIONS** nhưng yêu cầu browser kiểm tra *phương thức thật* qua:

~~~http
Access-Control-Request-Method: POST
~~~

Do đó:

~~~java
.allowedMethods("GET", "POST")
~~~

vẫn có thể cho browser gửi preflight `OPTIONS` hỏi về POST. Không phải mọi API cần tự tạo controller `@RequestMapping(method=OPTIONS)`. Spring Framework/HandlerMapping/CorsFilter có thể xử lý preflight trực tiếp.

### GET, HEAD, POST và các trường hợp gây preflight

Một request đơn giản theo tiêu chí CORS safelist (ví dụ GET không có header tùy chỉnh) có thể **không preflight**. Request `POST` với `Content-Type: application/json` thường cần preflight vì JSON media type không thuộc nhóm Content-Type được safelist. Các phương thức `PUT`, `PATCH`, `DELETE` thường cần preflight khi gọi cross-origin từ script.

Đừng cố chuyển POST JSON thành dạng “simple request” chỉ để né preflight. **Preflight là một phần bảo vệ của browser**, nên cấu hình chính xác thay vì tối ưu bằng cách lách tiêu chí.

## 5. Allowed headers: client được gửi request headers nào?

Ví dụ frontend gọi:

~~~javascript
fetch("http://localhost:8080/api/message", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Request-Id": "req-101"
  },
  body: JSON.stringify({message: "hello"})
});
~~~

Browser nhận thấy request cần preflight và gửi:

~~~http
OPTIONS /api/message HTTP/1.1
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-request-id
~~~

Server chỉ chấp nhận nếu cấu hình cho phép hai request headers này:

~~~java
.allowedHeaders("Content-Type", "X-Request-Id")
~~~

Preflight response có thể chứa:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type,x-request-id
~~~

Danh sách, cách viết hoa và thứ tự của values có thể khác theo framework/cấu hình; browser xét **ngữ nghĩa case-insensitive của HTTP header names**. Đừng viết test so khớp nguyên chuỗi header nếu yêu cầu chỉ là chứa các header được phép.

**`Authorization` là request header**. Nếu frontend gửi bearer token qua JavaScript, thường cần:

~~~java
.allowedHeaders("Authorization", "Content-Type", "X-Request-Id")
~~~

Điều này chỉ nói browser được **gửi header**. Nó không tạo token, không xác thực token, không cấp role; backend vẫn cần filter xác thực và kiểm tra quyền.

### Header wildcard và ranh giới tin cậy

~~~java
.allowedHeaders("*")
~~~

cho phép tập request headers rộng hơn (trong credentialed cases Spring có quy tắc phản chiếu các header được yêu cầu). Dù hữu ích khi thử nghiệm, nó làm mất khả năng giới hạn rõ những custom headers client code được phép gửi. Với API có xác thực, nên dùng danh sách thực tế cần thiết.

Browser vẫn kiểm soát các **forbidden request headers**; cấu hình CORS không cho phép JavaScript tự đặt `Host`, `Cookie` hay một số header bị cấm theo Fetch standard. Việc cho `Cookie` vào `allowedHeaders` **không làm script tự đặt được Cookie**; muốn gửi cookie phải dùng credential mode và cookie policy của browser.

Không phải mọi request header đều cần xuất hiện trong `Access-Control-Request-Headers`: browser chỉ liệt kê những header cần kiểm tra; các CORS-safelisted request headers theo điều kiện có thể được gửi mà không liệt kê.

## 6. Exposed headers: JavaScript được phép đọc response headers nào?

Thông thường script đọc được các **CORS-safelisted response headers** từ response cross-origin hợp lệ:

- `Cache-Control`
- `Content-Language`
- `Content-Length`
- `Content-Type`
- `Expires`
- `Last-Modified`
- `Pragma`

Các header khác như `Location`, `ETag`, `Content-Disposition`, `X-Request-Id` hoặc `X-RateLimit-Remaining` **không tự nhiên cho script đọc được** khi cross-origin. Server cần khai báo:

~~~java
.exposedHeaders("Location", "ETag", "X-Request-Id")
~~~

HTTP response thật:

~~~http
HTTP/1.1 201 Created
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Expose-Headers: Location, X-Request-Id
Location: /api/message/42
X-Request-Id: req-101
Content-Type: application/json
~~~

Khi đó JavaScript có thể:

~~~javascript
const response = await fetch("http://localhost:8080/api/message", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({message: "hello"})
});

console.log(response.status);                       // 201
console.log(response.headers.get("Location"));      // /api/message/42
console.log(response.headers.get("X-Request-Id"));  // req-101
~~~

Ví dụ này giả sử request thành công, origin được phép, đúng CORS config, không có redirect bất ngờ và response có những headers như trong sample.

**`exposedHeaders` không làm server tự gửi thêm header.** Nếu backend không phát `X-Request-Id`, JavaScript đọc vẫn thấy `null` dù expose nó. Cần cả **tạo header thật** lẫn **expose tên header**.

### Đừng expose `Set-Cookie`

`Set-Cookie` là **forbidden response-header name** đối với Fetch; JavaScript không được đọc nó bằng `response.headers.get("Set-Cookie")` dù bạn liệt kê `Set-Cookie` trong `Access-Control-Expose-Headers`. Browser tự quản lý cookie theo cookie policy. Không đưa token bí mật vào exposed headers và nghĩ CORS thay cơ chế xác thực.

### Wildcard exposed headers và credentials

Trong tiêu chuẩn Fetch, `Access-Control-Expose-Headers: *` chỉ hoạt động như wildcard cho request **không credentialed**. Với credentialed request, dấu `*` được xem như một tên header literal. Spring có lưu ý implementation có thể vẫn in `*` trong một số trường hợp credentialed; **đừng dựa vào wildcard khi frontend cần đọc headers có credentials**. Liệt kê rõ `Location`, `ETag`, `X-Request-Id` và chỉ các header thật sự cần thiết.

## 7. Credentialed CORS: cookie và fetch credentials

Nếu frontend cần gửi session cookie đến API cross-origin:

~~~javascript
const response = await fetch("https://api.example.test/api/me", {
  credentials: "include"
});
~~~

Các điều kiện độc lập phải thỏa:

1. Browser được phép gửi cookie theo `Domain`, `Path`, `Secure`, `SameSite` và chính sách third-party cookies hiện hành.
2. CORS server cho origin cụ thể qua `Access-Control-Allow-Origin: https://app.example.test`, **không dùng `*`**.
3. Response có `Access-Control-Allow-Credentials: true`.
4. Backend vẫn xác thực/ủy quyền cookie/session đúng cách.
5. Các request thay đổi trạng thái phải có **CSRF defense** phù hợp. CORS không tự thay CSRF protection.

### Phân biệt **cross-origin** với **cross-site**

`https://app.example.test` và `https://api.example.test` là **khác origin**, nhưng có thể vẫn cùng site theo tiêu chí cookie/registrable domain và scheme. `https://shop.example.test` với `https://other-domain.test` là cross-site. `SameSite` là thuộc tính cookie dựa trên **site**, không dựa hoàn toàn vào origin. Hai cơ chế độc lập; không dùng `SameSite=Lax` hay CORS như một lời giải cho mọi tình huống credential.

Nếu request thực sự cross-site và phải gửi cookie, trình duyệt hiện đại thường đòi `SameSite=None; Secure`, nhưng còn phụ thuộc hạn chế third-party cookies và chính sách bảo vệ riêng của browser. Khi development trên HTTP localhost, cách xử lý Secure cookie có thể khác môi trường HTTPS production; không suy diễn từ cURL.

**CORS cho phép JavaScript đọc response, không bảo đảm ngăn mọi request thay đổi trạng thái**. Một HTML form truyền thống từ site khác có thể gửi các request đơn giản mà không cần CORS preflight; nên vẫn cần CSRF token, SameSite policy và authorization.

## 8. Luồng preflight và actual request đầy đủ

Ví dụ frontend ở `http://localhost:5173` muốn POST JSON tới `http://localhost:8080/api/message`, kèm `X-Request-Id`:

~~~text
Browser                       Spring Boot
  |                              |
  | OPTIONS /api/message         |
  | Origin: http://localhost:5173|
  | Access-Control-Request-Method: POST
  | Access-Control-Request-Headers: content-type,x-request-id
  |----------------------------->|
  |                              | check Origin, Method, Headers
  |<-----------------------------|
  | 200 OK (preflight)           |
  | Access-Control-Allow-Origin: http://localhost:5173
  | Access-Control-Allow-Methods: GET,POST
  | Access-Control-Allow-Headers: content-type,x-request-id
  | Access-Control-Max-Age: 1800 |
  |                              |
  | POST /api/message            |
  | Origin: http://localhost:5173|
  | Content-Type: application/json
  | X-Request-Id: req-101        |
  |----------------------------->|
  |                              | controller xử lý request
  |<-----------------------------|
  | 201 Created                  |
  | Access-Control-Allow-Origin: http://localhost:5173
  | Access-Control-Expose-Headers: Location, X-Request-Id
  | Location: /api/message/42    |
  | X-Request-Id: req-101        |
~~~

**Lưu ý thực tế:**

- `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers` chủ yếu được browser dùng ở **preflight response**.
- `Access-Control-Expose-Headers` có tác dụng với **actual response** để frontend đọc headers.
- `Access-Control-Max-Age` là cache TTL **kết quả preflight**, không phải TTL của body JSON hay CDN cache.
- Browser có thể giới hạn max-age nhỏ hơn giá trị server công bố và có thể không gửi OPTIONS mỗi lần do preflight cache.
- Nếu preflight không đạt, browser sẽ **không gửi actual request** theo luồng bình thường.
- Nếu **simple CORS request** không có preflight, request thật vẫn có thể tới server dù origin bị từ chối; browser chặn script đọc response. Không coi CORS như bộ lọc chống CSRF.
- Response có `Vary: Origin`, đôi khi cùng `Access-Control-Request-Method` và `Access-Control-Request-Headers`, để cache trung gian chọn đúng biến thể.

## 9. Spring Boot MVC: cấu hình tập trung bằng WebMvcConfigurer

Ví dụ dưới đây dùng **Java 17+, Spring Boot 3.3.x, Spring MVC**, frontend dev `http://localhost:5173` và frontend production `https://app.example.test`. CORS mapping chỉ áp dụng cho `/api/**`.

~~~java
@Configuration
public class CorsConfig implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins(
                        "http://localhost:5173",
                        "https://app.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders(
                        "Content-Type",
                        "Authorization",
                        "X-Request-Id")
                .exposedHeaders(
                        "Location",
                        "X-Request-Id",
                        "ETag")
                .allowCredentials(true)
                .maxAge(1800);
    }
}
~~~

Snippet cần imports:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
~~~

Các giá trị và ý nghĩa:

- `addMapping("/api/**")`: giới hạn **URL của backend** được cấu hình CORS. Không tự mở CORS cho Actuator, Swagger, admin hoặc static files.
- `allowedOrigins(...)`: allowlist cụ thể; port dev là một phần origin.
- `allowedMethods("GET","POST")`: chỉ những method cần cho API ví dụ.
- `allowedHeaders(...)`: request script có thể gửi Content-Type, Authorization và X-Request-Id.
- `exposedHeaders(...)`: browser script được đọc Location, X-Request-Id, ETag khi response thực sự có chúng.
- `allowCredentials(true)`: cho phép credentialed CORS từ origin đã match. Không thay cách browser gửi cookie và không tự cấp login.
- `maxAge(1800)`: cho phép browser cache kết quả preflight tối đa theo chính sách/browser cap.

### 9.1. @CrossOrigin trên controller

Với một endpoint riêng, có thể dùng annotation:

~~~java
@CrossOrigin(
    origins = "https://app.example.test",
    methods = {RequestMethod.GET},
    allowedHeaders = {"Authorization", "X-Request-Id"},
    exposedHeaders = {"ETag"},
    allowCredentials = "true",
    maxAge = 1800)
@GetMapping("/api/summary")
public Summary summary() {
    return service.currentSummary();
}
~~~

Đây là **snippet**; `Summary` và `service` thuộc ứng dụng thực tế. Annotation hữu ích khi route có chính sách đặc thù. **Không trộn global và local thiếu kiểm soát**: Spring MVC có thể **combine** global/local configurations; nhiều thuộc tính dạng danh sách được gộp nên một `@CrossOrigin` quá rộng có thể vô tình mở thêm origin/header cho route. Chọn một **nguồn cấu hình chính** và test kết quả cuối cùng.

Theo tài liệu Spring MVC, defaults của `@CrossOrigin` và defaults của global mapping không hoàn toàn giống nhau. Không dựa vào default “all origins/all headers” cho API nhạy cảm; khai báo rõ policy.

## 10. Ví dụ dự án Spring Boot Java 17 chạy được

Ví dụ này cố tình **không thêm Spring Security** để người học nhìn rõ CORS trước; phần Security có hướng dẫn riêng bên dưới.

Cấu trúc:

~~~text
cors-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/cors/CorsApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/cors/CorsHttpTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'cors-lab'
~~~

`build.gradle` (dùng Spring Boot 3.3.13 làm ví dụ phiên bản 3.x và Java 17; dự án thật dùng phiên bản đã được tổ chức duy trì):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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

`src/main/resources/application.properties`:

~~~properties
server.port=8080
~~~

`src/main/java/demo/cors/CorsApplication.java` — **một file Java hoàn chỉnh**:

~~~java
package demo.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class CorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsApplication.class, args);
    }
}

@Configuration
class ApiCorsConfig implements WebMvcConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins(
                        "http://localhost:5173",
                        "https://app.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders(
                        "Content-Type",
                        "Authorization",
                        "X-Request-Id")
                .exposedHeaders(
                        "Location",
                        "X-Request-Id",
                        "ETag")
                .allowCredentials(true)
                .maxAge(1800);
    }
}

@RestController
class MessageController {
    public record MessageResponse(String message) {
    }

    public record CreateMessage(String message) {
    }

    @GetMapping("/api/message")
    ResponseEntity<MessageResponse> read() {
        return ResponseEntity.ok()
                .header("X-Request-Id", "req-get-101")
                .header(HttpHeaders.ETAG, "\"demo-v1\"")
                .body(new MessageResponse("hello"));
    }

    @PostMapping("/api/message")
    ResponseEntity<MessageResponse> create(
            @RequestBody CreateMessage input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .header(HttpHeaders.LOCATION, "/api/message/42")
                .header("X-Request-Id", "req-post-202")
                .body(new MessageResponse(input.message()));
    }
}
~~~

**Giải thích:**

1. Spring Boot auto-configuration nạp `WebMvcConfigurer` và gắn CORS mapping vào Spring MVC HandlerMapping.
2. Vì URL là `/api/message` nên nó match `/api/**`. Không có cấu hình tương ứng cho `/admin/**`.
3. GET trả body `{"message":"hello"}` và response headers `X-Request-Id`, `ETag`.
4. POST JSON trả **201 Created**, body theo `input.message()` và headers `Location`, `X-Request-Id`.
5. Exposed headers không tự tạo các header đó; controller tạo chúng, CORS policy cho JS đọc chúng.
6. `allowCredentials(true)` chỉ là tín hiệu CORS; ví dụ không có authentication và không có session business. Khi thêm bảo mật, cần Spring Security và CSRF defense phù hợp.
7. Không cần tạo `@OptionsMapping` hay `@RequestMapping(method = OPTIONS)` cho preflight: Spring MVC xử lý preflight theo CORS configuration.
8. Tệp chứa một public class `CorsApplication` và các package-private top-level classes `ApiCorsConfig`, `MessageController`, hợp lệ với Java 17. Hai nested records public dùng làm DTO cho Jackson.

### 10.1. Khởi động

Dùng Gradle wrapper có trong project:

~~~bash
./gradlew bootRun
~~~

PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu chưa có wrapper, tạo wrapper bằng Gradle phù hợp phiên bản plugin và JDK trước khi chạy. Khi server lắng nghe port 8080, có thể dùng cURL mô phỏng browser CORS headers.

### 10.2. Preflight hợp lệ

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/message" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-request-id"
~~~

Kỳ vọng status **2xx** (Spring MVC thường trả 200 cho preflight hợp lệ) và các header mang ý nghĩa:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type,x-request-id
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
~~~

Không yêu cầu các giá trị danh sách có cùng thứ tự/kiểu chữ như ví dụ. Header `Vary` cũng có thể xuất hiện. **Không có response body JSON** ở preflight hợp lệ vì controller POST **chưa chạy**.

### 10.3. Actual POST

~~~bash
curl -i "http://localhost:8080/api/message" \
  -H "Origin: http://localhost:5173" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: req-client-77" \
  -d '{"message":"xin chao"}'
~~~

Những phần cần thấy:

~~~http
HTTP/1.1 201 Created
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: Location, X-Request-Id, ETag
Location: /api/message/42
X-Request-Id: req-post-202
Content-Type: application/json

{"message":"xin chao"}
~~~

`X-Request-Id` từ response là giá trị cố định do controller demo tạo, **không bắt buộc trùng** header request `req-client-77`. Với ứng dụng thật, correlation ID nên được sinh/validate và propagate nhất quán theo logging/tracing policy; demo chỉ minh họa allowed vs exposed headers.

### 10.4. Origin bị từ chối

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/message" \
  -H "Origin: https://untrusted.example.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"
~~~

Trong cấu hình ví dụ, Spring MVC thường trả **403 Invalid CORS request** cho preflight không hợp lệ. Quan trọng là browser **không nhận được CORS approval** và không thực hiện actual POST theo flow preflight. Đừng dùng `curl` không có header `Origin` để kết luận endpoint đã cấu hình CORS đúng.

### 10.5. Method hoặc request header ngoài allowlist

Preflight hỏi `DELETE` sẽ không được chấp thuận:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/message" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: DELETE"
~~~

Preflight đòi header chưa khai báo cũng bị từ chối:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/message" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: x-internal-secret"
~~~

Các test này minh họa rằng origin được phép **không đồng nghĩa** mọi method/header được phép. Không sửa lỗi bằng `allowedMethods("*")` và `allowedHeaders("*")` nếu chỉ cần một method/header cụ thể.

## 11. Ví dụ frontend thật: fetch và đọc exposed headers

Một script đang chạy ở `http://localhost:5173`:

~~~javascript
const api = "http://localhost:8080/api/message";

async function createMessage() {
  const response = await fetch(api, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Request-Id": "req-frontend-1"
    },
    credentials: "include",
    body: JSON.stringify({message: "hello from frontend"})
  });

  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }

  console.log("status =", response.status);
  console.log("location =", response.headers.get("Location"));
  console.log("responseId =", response.headers.get("X-Request-Id"));
  console.log("body =", await response.json());
}

createMessage().catch(console.error);
~~~

Ví dụ server cấu hình `allowedOrigins("http://localhost:5173")`, `allowedMethods("POST")`, `allowedHeaders("Content-Type","X-Request-Id")` và `exposedHeaders("Location","X-Request-Id")`, nên response có thể được đọc. `credentials:"include"` chỉ cho phép browser gửi cookies nếu chúng tồn tại và cookie policy cho phép; demo không tạo cookie.

Với controller ví dụ, **console logic** của các trường xác định được:

~~~text
status = 201
location = /api/message/42
responseId = req-post-202
body = { message: 'hello from frontend' }
~~~

Cách in object của JavaScript console (dấu nháy, thứ tự) tùy browser; ví dụ trên mô tả giá trị logic, không cam kết console byte-for-byte. Nếu bỏ `exposedHeaders("Location",...)`, HTTP response có thể vẫn chứa `Location` nhưng `response.headers.get("Location")` sẽ trả `null` trong browser cross-origin.

**Đừng cố dùng frontend code** như `response.headers.get("Set-Cookie")`: nó luôn bị lọc bởi Fetch, không phải do chưa thêm exposed header.

## 12. Spring Security: preflight phải được xử lý trước authentication

Preflight CORS của browser thường **không gửi cookie session** và không được xem như request nghiệp vụ đã xác thực. Nếu Spring Security chặn `OPTIONS` trước khi CORS processor xử lý, frontend có thể nhận 401/403 trên preflight, dù actual endpoint cho user hợp lệ.

Theo tài liệu Spring Security, cần tích hợp CORS vào security filter chain. Với Spring MVC đã có `WebMvcConfigurer` CORS mapping, ví dụ cấu hình Security cho ứng dụng thực tế:

~~~java
// Snippet trong @Configuration: cần dependency spring-boot-starter-security.
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.cors(Customizer.withDefaults());
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated());
    http.httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

Cần imports `org.springframework.context.annotation.Bean`, `org.springframework.security.config.Customizer`, `org.springframework.security.config.annotation.web.builders.HttpSecurity` và `org.springframework.security.web.SecurityFilterChain`. Đây là **snippet tích hợp**, không phải phần được dùng trong dự án runnable mục 10. Tùy cách xác thực (Bearer, OAuth2 resource server, session), cần cấu hình bổ sung phù hợp.

**Không đơn giản “permitAll OPTIONS /**” để giải quyết tất cả.** Nếu CORS không xử lý/bổ sung header đúng, browser vẫn chặn. Tích hợp `http.cors(...)` giúp preflight đi qua CORS logic trước authentication theo thiết kế.

Nếu dùng Spring Security cùng với một `CorsConfigurationSource` bean, hoặc có nhiều filter chains/multiple sources, cần kiểm tra thứ tự và **nguồn cấu hình nào được Security dùng**. Không tạo cả CorsFilter thủ công và WebMvcConfigurer ở nhiều tầng mà không kiểm soát việc trả header trùng lặp.

### CSRF không biến mất khi bật CORS

Với cookie/session authentication, những request thay đổi trạng thái cần đánh giá CSRF. Browser có thể gửi những request “simple” xuyên site theo cơ chế HTML form mà không cần CORS approval để đọc response. Không tắt CSRF chỉ vì đã giới hạn allowedOrigins. Đối với token-based stateless API, CSRF design có thể khác; lựa chọn phải dựa trên threat model và cơ chế credential thực tế.

## 13. CORS trong Spring WebFlux

Spring WebFlux cũng cung cấp CORS mapping, nhưng sử dụng `WebFluxConfigurer` và reactive handler stack, **không dùng `WebMvcConfigurer`** trong ứng dụng WebFlux thuần.

Snippet cấu hình WebFlux (đặt trong class `@Configuration`):

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
            .allowedOrigins(
                    "http://localhost:5173",
                    "https://app.example.test")
            .allowedMethods("GET", "POST")
            .allowedHeaders(
                    "Content-Type", "Authorization", "X-Request-Id")
            .exposedHeaders("Location", "X-Request-Id")
            .allowCredentials(true)
            .maxAge(1800);
}
~~~

Lưu ý `CorsRegistry` của WebFlux là `org.springframework.web.reactive.config.CorsRegistry`, và class phải `implements WebFluxConfigurer` với import `org.springframework.web.reactive.config.WebFluxConfigurer`.

Các khái niệm HTTP giống MVC: preflight, Origin, allowed/exposed headers, credentials. Nếu thêm Spring Security WebFlux, cần reactive `SecurityWebFilterChain` và tích hợp CORS đúng với `ServerHttpSecurity`, không bê nguyên `HttpSecurity`/Servlet `CorsFilter` sang Netty WebFlux.

Spring Boot thường ưu tiên Servlet MVC nếu có cả `spring-boot-starter-web` và `spring-boot-starter-webflux` trên classpath. Để kiểm thử cấu hình nào có hiệu lực, xác định web application type/starter thật và dùng `WebTestClient` nếu đó là reactive web app.

## 14. Proxy, CDN, gateway và CORS

Một triển khai thường có:

~~~text
Browser frontend (https://app.example.test)
   |
   v
CDN / reverse proxy / API gateway
   |
   v
Spring Boot (http://service:8080)
~~~

Vấn đề thường gặp không nằm ở `allowedOrigins` mà ở intermediary:

- Proxy **chặn OPTIONS** bằng 401, 403, 404 hoặc 405, nên preflight không đến Spring.
- Proxy phản hồi `301/302` cho OPTIONS từ HTTP sang HTTPS hoặc thêm/xóa slash, gây lỗi preflight/redirect tùy browser.
- Gateway tự thêm một `Access-Control-Allow-Origin`, Spring cũng thêm một giá trị khác, kết quả là **duplicate/invalid header**.
- Proxy strip `Access-Control-Expose-Headers` hoặc `Access-Control-Allow-Headers`, khiến JavaScript không đọc/gửi như mong muốn.
- CDN cache preflight/actual response nhưng bỏ `Origin`, `Access-Control-Request-Method` hoặc `Access-Control-Request-Headers` khỏi cache variation, làm policy từ origin A bị trả cho origin B.
- TLS termination và forwarded headers khiến backend hiểu sai external scheme/host trong quá trình sinh URL, redirect hoặc cookie; proxy config cần chính xác.
- Proxy thay origin header theo policy sai: không nên dùng một `Origin` do client giả mạo như chứng cứ authentication.

### Nên cấu hình CORS ở đâu?

Chọn **một lớp rõ ràng chịu trách nhiệm policy**:

1. **Ở Spring Boot:** phù hợp API cần policy theo controller/URL, dễ test bằng MockMvc/WebTestClient.
2. **Ở API gateway/proxy:** phù hợp quy tắc tập trung cho nhiều service; cần đảm bảo hỗ trợ preflight và **không ghi đè/nhân đôi** header của Spring.
3. **Kết hợp:** chỉ khi mỗi lớp có trách nhiệm phân định rõ (ví dụ gateway kiểm tra allowlist chung, Spring vẫn kiểm soát route nhạy cảm); test end-to-end final headers.

Một reverse proxy có thể phục vụ frontend và API qua **cùng public origin**:

~~~text
https://app.example.test/          -> frontend
https://app.example.test/api/...   -> reverse proxy -> Spring Boot
~~~

Khi browser gọi cùng origin, **không cần CORS** cho cuộc gọi đó. Proxy same-origin có thể đơn giản hóa cấu hình, nhưng không thay authentication, CSRF, cookies, authorization hay yêu cầu bảo vệ proxy.

### Header `Vary` và shared caches

Khi `Access-Control-Allow-Origin` được phản ánh từ một allowlist nhiều origin, response nên có:

~~~http
Vary: Origin
~~~

Với preflight có thể cần variation theo:

~~~http
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Spring CORS processor thường quản lý các giá trị Vary tương ứng. Không xóa chúng vô ý tại CDN; nếu không, một preflight response của origin/method/header này có thể bị sử dụng nhầm cho nguồn khác. `Vary` không thay authorization và không tự làm body có PII an toàn để public-cache.

Đặc biệt, `Access-Control-Max-Age` là browser preflight cache, **khác** với `Cache-Control: public, max-age=...` cho response body. Không public-cache các API chứa thông tin cá nhân chỉ để giảm số preflight.

## 15. Những lỗi CORS thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| Browser báo “No Access-Control-Allow-Origin” | Origin không match, CORS chưa enable, response lỗi không có header, proxy strip | Xem chính Origin, status, final headers; so allowlist |
| `http://localhost:3000` chạy nhưng `5173` lỗi | Port thuộc origin | Thêm dev origin đúng, không wildcard production |
| HTTPS frontend gọi HTTP API bị blocked | Mixed content hoặc redirect/proxy, không chỉ CORS | Dùng HTTPS API cùng security policy |
| Preflight OPTIONS 401 | Security auth chạy trước CORS | Tích hợp Spring Security `http.cors(...)`; xem gateway |
| Preflight OPTIONS 405 | Proxy/controller xử lý OPTIONS sai | Để framework CORS xử lý, cấu hình forwarding |
| Preflight báo request method not allowed | `allowedMethods` không chứa method thực | Thêm đúng method cần, kiểm tra route HTTP thực tế |
| Preflight báo header not allowed | `allowedHeaders` không chứa `Authorization`/custom header | Thêm header tên chính xác, không trộn với exposedHeaders |
| POST thành công nhưng JS không đọc Location | Thiếu `exposedHeaders("Location")` | Expose Location trên actual response |
| JS không đọc Set-Cookie dù đã expose | Set-Cookie là forbidden response header | Để browser xử lý cookie; không expose token |
| Credentials mode báo wildcard origin invalid | `Access-Control-Allow-Origin: *` với credentialed request | Dùng origin cụ thể, enable credentials có kiểm soát |
| Cookie không được gửi dù CORS pass | `credentials`, Domain/Path, Secure/SameSite, third-party cookie policy | Kiểm tra Request Cookie và browser storage/network |
| cURL trả 200 nhưng browser fetch fail | cURL không enforcement CORS | Xem DevTools preflight, headers và console |
| Response có hai ACAO headers | Gateway và Spring cùng thêm | Chọn một owner CORS, bỏ duplicate |
| `allowedOrigins("https://*.example.test")` không match | allowedOrigins không phải pattern matching | Dùng concrete list hoặc allowedOriginPatterns có kiểm soát |
| API trả 403 nhưng console ghi CORS | Origin chưa được phép, auth fail hoặc Spring CORS reject | Tách 403 từ CORS processor, Security và gateway logs |
| `OPTIONS` thành công nhưng actual trả 401 | CORS cho request đi qua nhưng chưa authenticated | Cấu hình authentication đúng, không sửa CORS |
| GET chạy, POST JSON lỗi | JSON gây preflight; allowedHeaders/Methods thiếu | Xem Access-Control-Request-* trên OPTIONS |
| CORS chạy localhost, lỗi sau CDN | Proxy strip/cache/redirect/duplicated policy | Test qua public hostname, không chỉ backend port |

**Quy trình điều tra ưu tiên:**

1. Ghi chính xác frontend URL (scheme, host, port), API URL và request method/header/credential mode.
2. Mở DevTools → Network: request có `OPTIONS` không? Status preflight và actual là gì?
3. Đọc `Origin` và `Access-Control-Request-Method` / `Access-Control-Request-Headers` nếu preflight; đối chiếu config.
4. Xác nhận response của preflight có `Access-Control-Allow-Origin/Methods/Headers/Credentials` phù hợp.
5. Đọc actual response `Access-Control-Allow-Origin` và `Access-Control-Expose-Headers`; xem browser console.
6. Nếu dùng Security, xác minh CorsFilter/Security chain và CSRF/auth; nếu có proxy, kiểm tra headers **cuối cùng** từ public endpoint.
7. Test denied-origin, denied-method, denied-header để chắc policy **không quá rộng**.

Không sửa bằng cách đặt `allowedOrigins("*")`, `allowedMethods("*")` và `allowedHeaders("*")` cho mọi API. Nó che mất chỗ cấu hình sai và mở rộng bề mặt tin cậy.

## 16. Test tự động bằng MockMvc

Với dự án mục 10, dùng `spring-boot-starter-test` và tạo `src/test/java/demo/cors/CorsHttpTest.java`:

~~~java
package demo.cors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsHttpTest {
    @Autowired
    MockMvc mvc;

    @Test
    void validPreflightAllowsMethodAndHeaders() throws Exception {
        mvc.perform(options("/api/message")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type,x-request-id"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    "http://localhost:5173"))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"))
            .andExpect(header().exists(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS))
            .andExpect(header().exists(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS));
    }

    @Test
    void actualResponseExposesRequestId() throws Exception {
        mvc.perform(get("/api/message")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("hello"))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    "http://localhost:5173"))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS,
                    containsString("X-Request-Id")))
            .andExpect(header().string(
                    "X-Request-Id", "req-get-101"));
    }

    @Test
    void untrustedOriginIsRejectedOnPreflight() throws Exception {
        mvc.perform(options("/api/message")
                .header(HttpHeaders.ORIGIN,
                        "https://untrusted.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden());
    }

    @Test
    void disallowedMethodIsRejected() throws Exception {
        mvc.perform(options("/api/message")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                        "DELETE"))
            .andExpect(status().isForbidden());
    }

    @Test
    void disallowedRequestHeaderIsRejected() throws Exception {
        mvc.perform(options("/api/message")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "x-internal-secret"))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests demo.cors.CorsHttpTest
~~~

**Các test này chứng minh** Spring MVC CORS mapping xử lý preflight, actual response và các case từ chối. Chúng **chưa** kiểm tra Spring Security (vì lab không thêm Security), **chưa** mô phỏng cookie policy của browser, và **chưa** đi qua CDN/reverse proxy. Nếu production có các lớp ấy, cần bổ sung integration test với security filter chain và public URL thực tế.

Trên những phiên bản framework khác nhau, status/body cho preflight không hợp lệ có thể khác. Giá trị cốt lõi cần xác nhận là browser không nhận CORS approval; test cụ thể 403 phù hợp với hành vi Spring MVC trong lab.

## 17. Thử nghiệm từ browser và proxy

### Browser console / frontend dev server

Chạy frontend ở đúng `http://localhost:5173`. Đảm bảo request POST JSON có preflight, sau đó body và exposed headers đọc được. Thử đổi frontend sang `http://localhost:5174`: nếu không nằm allowlist, browser phải chặn. Thử `Authorization` nếu app thực sự dùng bearer token; cần authentication thật để nhận 200 sau khi qua preflight.

### Kiểm tra sau reverse proxy

Giả sử external API là `https://api.example.test`, reverse proxy tới port 8080. Gửi:

~~~bash
curl -i -X OPTIONS "https://api.example.test/api/message" \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-request-id"
~~~

Ở **public endpoint**, xem status 2xx và Access-Control-Allow-* headers; đồng thời không có duplicate ACAO. Kiểm tra request thật và status/auth riêng. Nếu origin backend pass nhưng public URL fail, nghi ngờ gateway/ingress/cdn rule, forwarding OPTIONS, redirect, CORS header rewrite, hoặc cache key variation.

Một test quan trọng là origin không nằm allowlist **bị từ chối**, thay vì chỉ test happy path. Nếu policy thực tế vô tình phản ánh bất kỳ Origin nào và trả Credentials true, browser từ site của attacker có thể đọc tài nguyên đã xác thực trong một số điều kiện; đây là lỗi an toàn.

## 18. Những giới hạn cần nhớ của CORS

- **Không bảo vệ API khỏi Postman/cURL/server clients.** Tất cả endpoint nhạy cảm cần authentication/authorization riêng.
- **Không thay CSRF protection.** Cookie có thể được gửi theo cơ chế khác CORS, nhất là các request simple hoặc HTML forms.
- **Không sửa mixed content HTTPS → HTTP.** Browser có thể chặn trước khi CORS được xét.
- **Không bảo đảm cookies được gửi.** Fetch credentials, SameSite, Secure, Domain, Path và third-party cookie policy là các điều kiện độc lập.
- **Không tự expose Set-Cookie.** Đây là forbidden response header.
- **Không có nghĩa mọi headers script muốn gửi đều được phép.** Forbidden request headers vẫn do browser quyết định.
- **Không thay HTTP caching.** `Access-Control-Max-Age` là thời gian cache preflight, không phải response body CDN caching.
- **Không cho phép tự động tất cả controllers.** CORS mapping scope theo URL/HandlerMapping và có thể bị kết hợp với annotation.
- **Không kiểm tra quyền theo Origin header.** Non-browser clients có thể giả mạo Origin; backend auth phải dùng credential đáng tin.
- **Không khắc phục lỗi server 401/403/404/500 thật.** CORS có thể khiến browser không thấy body/status chi tiết, nhưng gốc lỗi vẫn cần xử lý.

## 19. Checklist review cấu hình CORS trước release

1. Các frontend origin hợp lệ được liệt kê **chính xác scheme/host/port** chưa? Có local/test origin vô tình nằm trong production không?
2. Có dùng `allowedOriginPatterns` quá rộng, cho phép subdomain không tin cậy hoặc `Origin: null` không?
3. Có bật `allowCredentials(true)` chỉ khi cần? Nếu có, ACAO là origin cụ thể, không phải `*`?
4. `allowedMethods` chỉ chứa các methods API cần cross-origin không?
5. `allowedHeaders` liệt kê những request headers frontend thật gửi không, phân biệt với response headers?
6. `exposedHeaders` chỉ gồm response header cần JS đọc; không cố expose `Set-Cookie` hoặc bí mật?
7. Browser gửi JSON/Authorization/custom header có preflight; OPTIONS có được Spring Security/gateway xử lý trước auth không?
8. Error/redirect/proxy có giữ một policy nhất quán và không tạo duplicate Access-Control-Allow-Origin không?
9. Credentialed CORS đã xét CSRF, SameSite/Secure cookie và authorization chưa?
10. Shared cache/CDN đã có `Vary` phù hợp khi ACAO thay đổi theo Origin chưa?
11. Có test origin bị từ chối, method bị từ chối, custom header bị từ chối và exposed headers trên actual response không?
12. Có test end-to-end bằng browser thật và public proxy URL, không chỉ bằng cURL/MockMvc không?

## 20. Bài tập tự kiểm tra

**Bài 1.** Frontend chạy `https://app.example.test`, API ở `https://api.example.test`. Có cần CORS không?

**Đáp án:** Có, chúng khác host → khác origin. Cần allow origin cho frontend ở backend/gateway, dù có thể cùng site xét theo cookie.

**Bài 2.** Spring cấu hình `allowedHeaders("Authorization")`. JavaScript có tự đọc `Authorization` trong response không?

**Đáp án:** Không. AllowedHeaders kiểm soát **request** headers. Để JS đọc một custom **response** header, dùng exposedHeaders; nhưng credential/token nên tránh phát trong response header nếu không cần.

**Bài 3.** Response có `X-Request-Id` nhưng JS `response.headers.get("X-Request-Id")` trả null. Cần kiểm tra gì?

**Đáp án:** Actual response có `Access-Control-Expose-Headers: X-Request-Id` không, có ACAO phù hợp không và header thực sự được gửi không.

**Bài 4.** Có `allowedMethods("POST")`, preflight là HTTP `OPTIONS`. Có phải thêm `allowedMethods("OPTIONS")` không?

**Đáp án:** Không chỉ vì preflight. `OPTIONS` là method của preflight, `Access-Control-Request-Method: POST` là method thật cần xét; Spring CORS processor xử lý preflight.

**Bài 5.** `allowedOrigins("*")` kết hợp `allowCredentials(true)` có hợp lệ để dùng cookie không?

**Đáp án:** Không. Browser không chấp nhận ACAO `*` với credentials; dùng origin cụ thể hoặc origin pattern được kiểm soát và trả origin đã match.

**Bài 6.** Vì sao POST JSON thường gửi preflight nhưng GET thường không?

**Đáp án:** `Content-Type: application/json` không nằm trong CORS-safelisted Content-Type, nên POST JSON thường cần OPTIONS. GET với headers đơn giản có thể không cần preflight.

**Bài 7.** Trình duyệt báo CORS blocked nhưng `curl` gọi API thành công. API có lỗi bảo mật chặn request không?

**Đáp án:** Không suy ra như vậy. cURL không enforcement CORS, còn browser áp chính sách cross-origin. Phải kiểm tra Origin, preflight và final headers; authentication vẫn độc lập.

**Bài 8.** Spring Security chặn OPTIONS bằng 401. Có nên tắt authentication cho cả API không?

**Đáp án:** Không. Tích hợp CORS trước Security (ví dụ `http.cors(Customizer.withDefaults())` và CORS mapping hợp lệ) để preflight được xử lý đúng; actual request vẫn cần auth.

**Bài 9.** Có thể cấu hình `Access-Control-Expose-Headers: *` khi dùng credentials và kỳ vọng mọi header đọc được không?

**Đáp án:** Không nên. Theo Fetch standard, wildcard không hoạt động như wildcard ở credentialed response; dùng explicit names. `Set-Cookie` vẫn không readable.

**Bài 10.** CDN cache response CORS cho origin A rồi trả cho origin B. Header nào liên quan?

**Đáp án:** `Vary: Origin` và với preflight còn `Access-Control-Request-Method`, `Access-Control-Request-Headers`. CDN cache key/rules phải tuân thủ, không chỉ dựa vào browser enforcement.

## 21. Tài liệu tham khảo chính thức

- [Spring Framework — CORS trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): `@CrossOrigin`, WebMvcConfigurer, allowed origins/methods/headers/exposed headers, credentials và combine policy.
- [Spring Framework — CORS trong Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): reactive CORS mapping, `WebFluxConfigurer`, allowedOriginPatterns.
- [Spring Security — Servlet CORS Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): tại sao CORS phải chạy trước Security, `http.cors(...)` và `CorsConfigurationSource`.
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): browser preflight, simple requests, credentials và response headers.
- [MDN — Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin): origin cụ thể và wildcard.
- [MDN — Access-Control-Allow-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Headers): xác định request headers được phép gửi.
- [MDN — Access-Control-Allow-Methods](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Methods): các phương thức được phép cho actual request.
- [MDN — Access-Control-Expose-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Expose-Headers): header script được đọc và giới hạn wildcard/credentials.
- [Fetch Standard — CORS protocol](https://fetch.spec.whatwg.org/#http-cors-protocol): quy tắc browser về preflight, wildcard, credentials và forbidden headers.

**Ghi nhớ:** `allowedOrigins` trả lời **site nào**; `allowedMethods` trả lời **method nào**; `allowedHeaders` trả lời **request header nào được gửi**; còn `exposedHeaders` trả lời **response header nào JavaScript được đọc**. Với credentials, chỉ tin origin cụ thể, không dùng ACAO `*`. CORS phải được kết hợp với authentication/authorization, CSRF controls và proxy policy chính xác — không bao giờ xem nó là firewall API.
