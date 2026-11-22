# Yêu cầu đơn giản, yêu cầu preflight và phương thức OPTIONS trong CORS

## 1. Bối cảnh và mục tiêu

Trong một ứng dụng **Spring Security reactive / Spring WebFlux**, frontend ở `http://localhost:5173` gọi API tại `http://localhost:8080` thường liên quan đến **CORS — Cross-Origin Resource Sharing**. Một số request được trình duyệt gửi trực tiếp; một số request khác khiến trình duyệt **tự gửi HTTP OPTIONS trước** để hỏi máy chủ về origin, phương thức và headers mà request thật dự định sử dụng.

Điểm dễ nhầm: **CORS là chính sách trình duyệt kiểm soát việc JavaScript từ origin khác đọc response**, không phải cơ chế đăng nhập, phân quyền hay CSRF. Một preflight được chấp nhận **không có nghĩa** request thật đã xác thực, có quyền truy cập hoặc được miễn CSRF.

Sau bài học, bạn có thể:

1. Phân biệt **origin**, **cross-origin**, **cross-site** và cùng origin; biết khác biệt về scheme, host hoặc port.
2. Phân loại một **CORS simple request** (tên trong tài liệu phổ biến; trong Fetch là request dùng phương thức/headers safelisted) với request **cần preflight**.
3. Giải thích được request `OPTIONS` với `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`, cùng các response headers liên quan.
4. Phân biệt **preflight OPTIONS** với một HTTP OPTIONS thông thường và với request thật dùng GET/POST/PUT/DELETE.
5. Hiểu vì sao preflight phải được xử lý **trước Spring Security authentication** và không được yêu cầu cookie/token thật.
6. Cấu hình `CorsConfiguration` và `UrlBasedCorsConfigurationSource` cho **WebFlux**, tích hợp qua `ServerHttpSecurity.cors(...)`.
7. Chạy ví dụ **Java 17+, Spring Boot 3.3.5, Spring Security 6.x**, dùng `curl` mô phỏng request và `WebTestClient` kiểm thử.
8. Xử lý những vấn đề thường gặp như OPTIONS bị 401, origin bị 403, CORS + CSRF, credentials, wildcard và proxy.

**Phạm vi:** CORS cho Spring Security **reactive**; không áp dụng nguyên xi cấu hình Servlet `CorsFilter` hoặc `HttpSecurity` vào `SecurityWebFilterChain`. Ví dụ sử dụng localhost và không chứa credential production.

## 2. Origin là gì và khi nào xảy ra cross-origin?

Một **origin** là tổ hợp **scheme + host + port**. URL path và query không tạo origin mới.

Ví dụ frontend chính `http://localhost:5173`:

| URL yêu cầu | Có cùng origin với frontend không? | Vì sao? |
| --- | --- | --- |
| `http://localhost:5173/home` | Có | Cùng scheme, host và port |
| `http://localhost:5173/api/data` | Có | Path khác không đổi origin |
| `http://localhost:8080/api/data` | Không | Khác port |
| `https://localhost:5173/api/data` | Không | Khác scheme HTTP/HTTPS |
| `http://127.0.0.1:5173/api/data` | Không | Host khác dù cùng máy |
| `https://api.example.test/data` | Không | Khác host và scheme |

CORS liên quan khi **browser JavaScript** (`fetch`, `XMLHttpRequest`, v.v.) thực hiện request cross-origin và muốn nhận response. Các browser thực thi CORS theo Fetch/Same-Origin Policy; một `curl` hay backend-to-backend client **không có cùng mô hình enforcement**.

Đừng đồng nhất **same-origin** với **same-site**. Hai subdomain hoặc port có thể thuộc cùng site theo ngữ nghĩa cookie nhưng vẫn khác origin và cần CORS khi JavaScript gọi chéo. Cookie `SameSite`, CSRF, authentication và CORS là những lớp kiểm soát khác nhau.

### Luồng quyết định phía browser

```text
JavaScript: fetch("http://localhost:8080/api/public")
                         |
                         v
          So với origin trang đang chạy
                         |
              Cùng origin? -- Có --> Gửi request thông thường
                         |
                       Không
                         v
          Xét method/headers/content type
                         |
               Có đủ CORS safelist?
                     /       \
                   Có        Không
                   |           |
                   v           v
              Gửi thẳng    OPTIONS preflight
              request          |
                   |       Máy chủ cho phép?
                   |        /           \
                   |      Không         Có
                   |       |             |
                   |       v             v
                   |    Browser       Gửi request thật
                   |    chặn          (GET/POST/...)
                   +-----------+---------+
                               |
                               v
                 Browser kiểm tra CORS response
                               |
                       Cho JavaScript đọc?
```

**Quan trọng:** Với simple cross-origin request, browser **có thể gửi request thật trước khi phát hiện response không cho phép JavaScript đọc**. Vì vậy CORS không thay thế authentication, authorization, CSRF, validation hoặc bảo vệ khỏi thao tác gây side effect.

## 3. “Simple request” có nghĩa gì?

Tên “simple request” được dùng rộng rãi trong tài liệu CORS. Về kỹ thuật, nó đề cập các cross-origin request không cần CORS preflight vì method/headers và một số điều kiện khác thuộc **CORS-safelisted**.

Để thường được coi là simple request, request cần thỏa mãn tất cả các điều kiện liên quan:

- Method là **GET**, **HEAD** hoặc **POST**.
- Các request headers do JavaScript chủ động thiết lập thuộc nhóm **CORS-safelisted**, chẳng hạn `Accept`, `Accept-Language`, `Content-Language` và `Content-Type` có giá trị phù hợp. `Range` có thể safelisted với định dạng một range được phép.
- Khi JavaScript đặt `Content-Type`, media type thuộc ba dạng được phép: `application/x-www-form-urlencoded`, `multipart/form-data` hoặc `text/plain`, cùng các điều kiện về giá trị header.
- Không có những yếu tố của Fetch/XHR buộc preflight, ví dụ một số XHR upload event listeners hoặc streaming request body.
- Các ràng buộc safelist về byte/value length và giá trị header vẫn áp dụng; không chỉ cần nhìn tên header. Một số hành vi browser có thể khác.

**Không phải mọi POST đều cần preflight**, nhưng **POST `application/json` thường cần**, vì `application/json` không nằm trong danh sách content types safelisted.

### Ví dụ simple GET

JavaScript chạy từ `http://localhost:5173`:

```javascript
const response = await fetch("http://localhost:8080/api/public");
console.log(response.status, await response.text());
```

Nếu không có headers khác khiến preflight phát sinh, browser **gửi GET trực tiếp**, kèm `Origin: http://localhost:5173` cho một CORS request.

Một HTTP exchange khái niệm:

```http
GET /api/public HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Accept: */*
```

Khi origin được phép, server có thể trả:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Content-Type: text/plain;charset=UTF-8

public-ok
```

Header `Access-Control-Allow-Origin` cho phép browser công khai response cho JavaScript ở origin đã chỉ định. Nếu thiếu header đó hoặc giá trị không khớp, **server vẫn có thể đã xử lý request và trả HTTP 200**, nhưng browser không cho script đọc response.

### Ví dụ simple POST về mặt CORS

Một POST với `Content-Type: text/plain`, không thêm header tùy chỉnh, có thể là simple request:

```javascript
await fetch("https://api.example.test/notes", {
  method: "POST",
  headers: { "Content-Type": "text/plain" },
  body: "hello"
});
```

Đây là **ví dụ nguyên lý CORS**, không phải route có trong demo Java phần 9. Chỉ vì không phải preflight **không có nghĩa** POST được server cho phép: endpoint vẫn phải xác thực/phân quyền, kiểm tra CSRF khi cần, validate body và kiểm soát side effects.

### Những tình huống dễ phân loại sai

| Request từ browser đến origin khác | Có cần preflight thông thường? | Lý do |
| --- | --- | --- |
| GET với `Accept: application/json` | Không | GET và Accept phù hợp safelist |
| HEAD, không thêm header đặc biệt | Không | HEAD là method safelisted |
| POST `Content-Type: text/plain` | Không | POST và media type safelisted |
| POST `application/x-www-form-urlencoded` | Không | Form media type safelisted |
| POST `multipart/form-data` | Không theo điều kiện safelist | Media type safelisted, nhưng còn xét headers/điều kiện khác |
| POST `application/json` | Có | Content-Type không safelisted |
| GET với `Authorization: Bearer ...` | Có | Authorization không safelisted |
| GET với `X-Client-Tag: web` | Có | Custom header không safelisted |
| PUT hoặc DELETE | Có | Method không safelisted |
| GET với cookie mặc định từ browser | Không chỉ vì cookie | Credential mode được kiểm tra riêng; cookie tự nó không nhất thiết kích hoạt preflight |
| GET với header có tên safelisted nhưng giá trị không hợp lệ | Có thể có | Fetch áp dụng thêm giới hạn giá trị/byte |

Các ví dụ giả định request cross-origin thông thường từ browser tuân theo Fetch; browser extension, service worker, browser-specific limits hoặc môi trường không phải browser có thể khác.

## 4. Preflight request là gì?

**CORS preflight** là một HTTP **OPTIONS** do browser tự tạo **trước request thật** khi request thật dùng method hoặc headers không thuộc safelist. Mục đích: hỏi server có chấp nhận **origin + method dự định + headers dự định** không.

Ví dụ JavaScript gửi JSON:

```javascript
const response = await fetch("http://localhost:8080/api/echo", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ value: "hello" })
});
console.log(response.status);
```

Browser thường thử trước:

```http
OPTIONS /api/echo HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
```

Lưu ý:
- Preflight luôn dùng HTTP **OPTIONS**, nhưng `Access-Control-Request-Method` chứa method **của request sẽ gửi sau đó**: ở đây là POST.
- `Access-Control-Request-Headers` chứa **tên headers** mà browser dự kiến gửi, không phải values. Trong ví dụ là `content-type`, **không** có JSON body.
- `Origin` là origin của trang gọi API; browser thường đặt tự động.
- Preflight **không gửi raw password/token trong `Authorization`** và theo mô hình Fetch thông thường không mang credentials của request thật. Không bắt preflight đăng nhập.
- Client-side JavaScript thông thường **không cần và không nên tự tạo OPTIONS preflight**. Browser quyết định việc preflight dựa trên request.

Server đồng ý bằng một response 2xx kèm headers phù hợp, ví dụ:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET, HEAD, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization, X-Client-Tag
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Tùy framework/config, response preflight có thể là 200 hoặc 204; **đừng kiểm tra cứng phải là 204**. Browser quan tâm 2xx và các CORS headers hợp lệ.

Nếu browser chấp nhận response preflight, **sau đó mới gửi POST thật**. Request thật vẫn có thể nhận **401**, **403**, **404**, **415**, **422** hoặc **500** vì những lý do độc lập với CORS. Với demo Spring Security bên dưới, POST không có CSRF token vẫn bị 403 mặc dù preflight được cho phép.

### Preflight GET có custom header

Ngay cả một GET cũng có thể cần preflight:

```javascript
const response = await fetch("http://localhost:8080/api/public", {
  headers: { "X-Client-Tag": "frontend-demo" }
});
console.log(await response.text());
```

Browser gửi OPTIONS có:

```http
OPTIONS /api/public HTTP/1.1
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: x-client-tag
```

Sau khi preflight hợp lệ, browser gửi GET với header `X-Client-Tag: frontend-demo`. Giá trị header thật **không được gửi trong preflight**; preflight chỉ yêu cầu tên header đó được cho phép.

### Preflight với `Authorization`

Một script chuẩn bị gửi `Authorization` (Basic hoặc Bearer) thường kích hoạt preflight vì tên header này **không safelisted**:

```http
OPTIONS /api/private HTTP/1.1
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Request OPTIONS này **không chứa** `Authorization: Basic ...` hoặc `Authorization: Bearer ...` của request thật. Nếu Security xử lý authentication **trước CORS**, nó có thể nhận request không credential và trả `401 Unauthorized`, khiến browser ngừng trước khi gửi request thật.

**Cách đúng:** cấu hình `CorsWebFilter`/CORS integration để preflight được xét **trước authentication**, sau đó request GET thật mới được xác thực và phân quyền.

## 5. HTTP OPTIONS thông thường khác CORS preflight thế nào?

Không phải mọi HTTP OPTIONS đều là preflight.

Theo logic `CorsUtils.isPreFlightRequest` của Spring WebFlux, preflight nhận diện bằng:
- HTTP method **OPTIONS**;
- có header **Origin**;
- có header **Access-Control-Request-Method**.

Header `Access-Control-Request-Headers` là **tùy chọn**.

| Request | Là CORS preflight? | Diễn giải |
| --- | --- | --- |
| `OPTIONS /api/public`, không Origin | Không | OPTIONS thông thường |
| `OPTIONS /api/public`, có Origin nhưng không `Access-Control-Request-Method` | Không | Có Origin nhưng thiếu dấu hiệu preflight |
| `OPTIONS /api/public` + Origin + `Access-Control-Request-Method: GET` | Có | Browser hỏi được phép gửi GET không |
| `OPTIONS /api/echo` + Origin + `Access-Control-Request-Method: POST` + `Access-Control-Request-Headers: content-type` | Có | Browser hỏi về JSON POST |
| `OPTIONS /api/private` + Origin + `Access-Control-Request-Method: DELETE` | Có về **hình thức** | Có thể bị CORS từ chối vì method DELETE không được cho phép |

Một request OPTIONS thông thường có thể được route tới handler, bị 401/403/405 hoặc trả thông tin capability tùy hệ thống. **Đừng viết `@RequestMapping(method = OPTIONS)` chỉ để chữa CORS** nếu vấn đề thực là thiếu cấu hình `CorsConfiguration`. Với WebFlux CORS được tích hợp đúng, preflight có thể được xử lý và kết thúc **trước controller**.

### OPTIONS không phải method thật

Nếu preflight hỏi:

```http
Access-Control-Request-Method: DELETE
```

thì browser đang hỏi **DELETE có được gửi sau đó không**, không phải muốn gọi một business endpoint thực hiện DELETE bằng chính OPTIONS. Preflight hợp lệ không thực thi việc xóa dữ liệu và không có request body JSON nghiệp vụ.

**Security policy:** Có thể cho phép xử lý OPTIONS preflight **không credential** mà vẫn yêu cầu authentication/authorization cho DELETE thật. Không suy luận “OPTIONS thông qua” = “DELETE không cần quyền”.

## 6. Các headers CORS cần đọc được

### Request headers của browser

| Header | Nơi dùng | Ý nghĩa |
| --- | --- | --- |
| `Origin` | Simple, preflight và actual CORS | Origin của trang JavaScript gọi |
| `Access-Control-Request-Method` | Preflight OPTIONS | Method của request thật sắp gửi |
| `Access-Control-Request-Headers` | Preflight OPTIONS khi cần | Danh sách tên headers của request thật |
| `Authorization` | Request thật nếu client dùng authentication header | Thông tin xác thực; không phải header mặc định trong preflight |
| `Cookie` | Request thật khi browser credential mode và cookie policy cho phép | Session/credential, không nhất thiết làm request cần preflight |

Các request headers `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers` thường do browser quản lý. JavaScript không nên tự đặt những forbidden headers này.

### Response headers của server

| Header | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `Access-Control-Allow-Origin` | Origin được browser cho phép đọc response | Phải khớp origin, hoặc `*` chỉ trong những trường hợp được phép |
| `Access-Control-Allow-Methods` | Methods được phép cho preflight | Thường chứa GET/POST/PUT/DELETE... theo policy |
| `Access-Control-Allow-Headers` | Request headers được phép cho preflight | Ví dụ `Content-Type`, `Authorization`, `X-Client-Tag` |
| `Access-Control-Allow-Credentials` | Cho phép JavaScript nhận response credentialed khi các điều kiện khác đúng | Chỉ bật khi thật sự cần, không kết hợp wildcard origin `*` |
| `Access-Control-Max-Age` | Số giây browser có thể cache kết quả preflight | Browser có thể đặt cap riêng; cache preflight khác HTTP cache thường |
| `Access-Control-Expose-Headers` | Response headers bổ sung JS được đọc | Không làm header trở thành bằng chứng authorization |
| `Vary` | Báo cache rằng response phụ thuộc vào Origin và các request headers liên quan | Quan trọng với CDN/reverse proxy và nhiều origins |

**`Access-Control-Allow-Origin` không phải authentication.** Server nên áp dụng permission và lọc dữ liệu đúng với principal/role, kể cả khi origin hợp lệ. CORS vẫn là lớp giới hạn JavaScript cross-origin, không phải ACL cho máy chủ.

## 7. CORS, credentials, CSRF và Spring Security là bốn vấn đề riêng

### 7.1. Preflight không có credential của request thật

Spring Security chính thức lưu ý **CORS phải xử lý trước Spring Security**, vì preflight thường không mang cookie/session hoặc credentials request thật. Nếu authentication filter nhận OPTIONS trước và yêu cầu đăng nhập, browser có thể gặp lỗi preflight 401/redirect.

Phối hợp đúng:

```text
Cross-origin OPTIONS preflight
          |
          v
    CORS validation
      /         \
    reject      allow
      |           |
     403        2xx + CORS headers
                  |
          Browser quyết định gửi
              actual request
                  |
                  v
        CORS response processing
                  |
                  v
           Authentication
                  |
                  v
           Authorization
                  |
                  v
              CSRF check
          (khi method/client cần)
                  |
                  v
              Controller
```

Sơ đồ là ý tưởng phân tách nhiệm vụ, không khẳng định thứ tự chính xác của mọi WebFilter nội bộ. `ServerHttpSecurity.cors(...)` tích hợp `CorsWebFilter` vào thứ tự phù hợp của Spring Security reactive.

### 7.2. Preflight thành công ≠ authentication thành công

Ví dụ, origin được phép hỏi OPTIONS `/api/private` với method GET và header Authorization. Server có thể cho phép OPTIONS trước khi biết user là ai. Browser sau đó gửi GET thật; nếu không có `Authorization` hợp lệ thì **401 Unauthorized**.

Tương tự, origin được phép gọi POST không chứng tỏ principal đủ role hay CSRF token đúng; actual request có thể bị 403.

### 7.3. CORS không thay thế CSRF

CORS quyết định JavaScript từ origin khác có **đọc response** được hay không. CSRF phòng các thao tác **thay đổi trạng thái** do browser tự gửi credentials (cookies/Basic trong một số tình huống) mà người dùng không có ý định thực hiện.

Một cross-origin **simple POST** có thể được browser gửi **không cần preflight**; vì vậy không được coi preflight là cơ chế CSRF protection. Với login dựa cookie/session, giữ CSRF defense thích hợp bất kể bạn đã khóa CORS như thế nào.

Ví dụ demo phần 9 **giữ CSRF enabled mặc định**. JSON POST có thể được preflight chấp thuận nhưng POST thật không có CSRF token sẽ trả **403**. Đây là một kết quả **đúng và có chủ đích**, giúp người học không nhầm CORS và CSRF.

### 7.4. `allowCredentials` và wildcard

Nếu frontend cần gửi cookie/session cross-origin (`fetch(..., { credentials: "include" })`), response phải có `Access-Control-Allow-Credentials: true` và một `Access-Control-Allow-Origin` **cụ thể, không phải `*`**, cùng các điều kiện cookie `SameSite`/`Secure` phù hợp. Điều này **không miễn CSRF**, cũng không buộc browser gửi cookie nếu cookie policy cấm.

Ví dụ bài dùng `setAllowCredentials(false)` để làm rõ **CORS public-origin demo không cấp quyền gửi cookies**. Nếu chuyển sang phiên browser có credentials, phải thiết kế lại whitelist origin, cookie attributes, CSRF và authentication. Không chỉ đổi một Boolean.

Với `Authorization` do script thiết lập, tên header **không safelisted** nên có preflight; việc browser gửi credential thực tế còn phụ thuộc Fetch credentials mode và chính sách client. Không hardcode raw password/token vào JavaScript public.

### 7.5. CORS không giới hạn `curl` hoặc service-to-service

Một caller không phải browser có thể gửi trực tiếp HTTP request không kèm Origin hoặc tự tạo Origin tùy ý. CORS **không phải** cơ chế xác thực/cấp quyền cho backends. Để bảo vệ API phải dùng OAuth2/JWT, Basic qua HTTPS, mTLS, session hoặc authentication thích hợp, kết hợp authorization.

## 8. Thiết kế cấu hình CORS cho Spring WebFlux

Trong Spring Security reactive, sử dụng:

- `org.springframework.web.cors.CorsConfiguration` (common framework configuration).
- `org.springframework.web.cors.reactive.CorsConfigurationSource` hoặc `UrlBasedCorsConfigurationSource` (**reactive** package).
- `ServerHttpSecurity.cors(cors -> cors.configurationSource(source))` trên `SecurityWebFilterChain`.

Đừng nhầm import `org.springframework.web.cors.UrlBasedCorsConfigurationSource` của Servlet với `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`. Hai loại dành cho hai web stacks khác nhau.

### Phạm vi path và origin

Giả sử frontend development chạy `http://localhost:5173`, API chạy `http://localhost:8080`:

- Whitelist origin **chính xác** `http://localhost:5173`, không tự mở mọi origin `*`.
- Đăng ký CORS cho `/api/**`, không vô tình bật cho mọi endpoint của app nếu không cần.
- Methods: `GET`, `HEAD`, `POST`, `OPTIONS`.
- Headers được phép: `Content-Type`, `Authorization`, `X-Client-Tag`.
- Credentials: **false** trong demo; các request không dùng cross-origin cookies.
- Preflight cache: `maxAge=600` giây, tùy browser có giới hạn riêng.
- Exposed header: `X-Demo-Trace` để minh họa sự khác biệt giữa headers được gửi và headers JS được phép đọc.

Một điều quan trọng về thiết kế: **`allowedMethods` có thể chứa OPTIONS**, nhưng với preflight browser vẫn hỏi method thật như POST; không phải cứ thêm OPTIONS vào allow list là mọi POST, PUT, DELETE được chấp nhận. Policy phải chứa cả method được yêu cầu.

### Không dùng hai cơ chế CORS trùng lặp vô thức

Có thể cấu hình CORS ở cấp handler WebFlux (`@CrossOrigin`, `WebFluxConfigurer.addCorsMappings`), ở `CorsWebFilter` hoặc ở Spring Security. Với một service, nên chọn **một chiến lược rõ ràng**, thống nhất trong security chain và kiểm thử. Nếu đặt `@CrossOrigin("*")` cùng global config chặt, cần hiểu quy tắc kết hợp; đừng suy đoán “cấu hình nào chặt hơn tự thắng”.

Ví dụ bên dưới dùng **một `UrlBasedCorsConfigurationSource` truyền trực tiếp vào `ServerHttpSecurity.cors`**. Không tạo thêm bean `CorsWebFilter` độc lập để tránh double-processing/header duplication trong demo.

## 9. Dự án chạy được: Spring Boot 3.3.5 + WebFlux + CORS

Mã dành cho **Java 17+**, **Gradle 8.x tương thích**, **Spring Boot 3.3.5**. Spring Security 6.x được Spring Boot quản lý, không pin version Spring Security riêng.

Cấu trúc:

```text
reactive-cors-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/cors/
    │   ├── CorsDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/dev/example/cors/
        └── CorsSecurityTests.java
```

### 9.1. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'reactive-cors-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Vì sao chỉ dùng WebFlux starter?** Nếu thêm `spring-boot-starter-web` cùng lúc, Spring Boot thường chọn Servlet/MVC. Khi đó các class CORS/Security khác với bài và việc kiểm thử reactive bị nhiễu.

### 9.2. Lớp khởi động

`src/main/java/dev/example/cors/CorsDemoApplication.java`:

```java
package dev.example.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
```

### 9.3. Cấu hình CORS và Spring Security reactive

`src/main/java/dev/example/cors/SecurityConfig.java`:

```java
package dev.example.cors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        config.setAllowedOrigins(List.of("http://localhost:5173"));
        config.setAllowedMethods(
                List.of("GET", "HEAD", "POST", "OPTIONS"));
        config.setAllowedHeaders(
                List.of("Content-Type", "Authorization", "X-Client-Tag"));
        config.setExposedHeaders(List.of("X-Demo-Trace"));
        config.setAllowCredentials(false);
        config.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
                User.withUsername("reader")
                        .password(encoder.encode("reader-pass"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            UrlBasedCorsConfigurationSource corsSource) {

        return http
                .cors(cors -> cors.configurationSource(corsSource))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/private")
                            .authenticated()
                        .pathMatchers(HttpMethod.POST, "/api/echo")
                            .permitAll()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

**Giải thích từng phần:**

1. Bean `UrlBasedCorsConfigurationSource` là loại **reactive**, lấy CORS policy dựa trên URL path. Chúng ta chỉ áp dụng cho `/api/**`.
2. `setAllowedOrigins(...)` chấp nhận origin **`http://localhost:5173`**. `https://localhost:5173`, `http://127.0.0.1:5173` hoặc port khác không tự động được cho phép.
3. `setAllowedMethods(...)` cho phép kiểm tra preflight đối với GET, HEAD, POST, OPTIONS. Nếu frontend bắt đầu gửi PUT, phải đánh giá nghiệp vụ rồi thêm PUT vào policy và route tương ứng.
4. `setAllowedHeaders(...)` cho phép browser đề nghị `Authorization`, `Content-Type` hoặc `X-Client-Tag` trong `Access-Control-Request-Headers`. Đây không phải cơ chế cấp quyền hay tự chấp nhận token.
5. `setAllowCredentials(false)` không công bố response là cho phép cookie/session cross-origin. Khi đổi sang app browser login theo cookie, cần cấu hình khác có kiểm soát.
6. `setMaxAge(600L)` đặt preflight cache tối đa theo server policy; browser có thể có giới hạn riêng.
7. `http.cors(cors -> cors.configurationSource(corsSource))` tích hợp xử lý CORS vào thứ tự Spring Security hợp lệ, **để OPTIONS preflight đi trước authentication**.
8. HTTP rule cho `GET /api/public` là public, `GET /api/private` yêu cầu đăng nhập. `POST /api/echo` public ở lớp authorization chỉ để quan sát CSRF; nó vẫn chịu **CSRF protection mặc định**.
9. `anyExchange().denyAll()` giúp fail closed đối với những method/path chưa thiết kế. **Không phải** thêm `pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()` là đủ nếu CORS headers chưa đúng.
10. `httpBasic` cho phép thử private GET với tài khoản mẫu. `formLogin` tắt để dễ nhìn 401; không tắt `csrf`.
11. Các account/password dùng cho localhost chỉ là **demo**. Với request thật trên mạng, HTTP Basic phải đi qua HTTPS/TLS hợp lệ.

**Vì sao preflight vào `/api/echo` vẫn được chấp nhận khi actual POST chưa có CSRF?** CORS xét origin/method/headers **ở bước giao thức browser**, còn CSRF bảo vệ request **POST thật**. Đây là hai lớp khác nhau và mục tiêu chính của bài.

### 9.4. Controller WebFlux

`src/main/java/dev/example/cors/DemoController.java`:

```java
package dev.example.cors;

import java.security.Principal;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    public record EchoInput(String value) {
    }

    @GetMapping("/api/public")
    public Mono<String> publicPage(ServerHttpResponse response) {
        response.getHeaders().set("X-Demo-Trace", "public-demo");
        return Mono.just("public-ok");
    }

    @GetMapping("/api/private")
    public Mono<String> privatePage(Principal principal) {
        return Mono.just("user=" + principal.getName());
    }

    @PostMapping(
            value = "/api/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Map<String, String>> echo(
            @RequestBody Mono<EchoInput> input) {
        return input.map(value -> Map.of("echo", value.value()));
    }
}
```

`/api/public` và `/api/private` cho phép quan sát simple GET, preflight GET có custom header và authentication. Endpoint `/api/echo` đại diện JSON POST để thấy preflight **OPTIONS thành công**, nhưng actual POST không có CSRF sẽ bị từ chối. Dự án không có một `@RequestMapping(method = OPTIONS)` nào: preflight được CORS layer xử lý.

Controller trả `Mono`, không gọi `block()` hay `subscribe()`. Với JSON input production phải có validation và xử lý giá trị `null` phù hợp; demo chỉ echo một field.

## 10. Thực hành kiểm tra với curl

Từ thư mục `reactive-cors-demo`:

```bash
gradle bootRun
```

Nếu có Gradle Wrapper, dùng `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat bootRun` (Windows). Mặc định ứng dụng chạy `http://localhost:8080`. Trong PowerShell, nếu `curl` là alias khác, dùng `curl.exe` để gọi chương trình curl.

**Cảnh báo:** `curl` không tự áp dụng Same-Origin Policy và **không tự gửi preflight** như browser. Khi muốn mô phỏng preflight, bạn phải gửi OPTIONS và headers phù hợp **thủ công**.

### 10.1. Simple cross-origin GET

```bash
curl -i \
  -H 'Origin: http://localhost:5173' \
  http://localhost:8080/api/public
```

Dự kiến:
- HTTP **200**, body `public-ok`.
- Có `Access-Control-Allow-Origin: http://localhost:5173`.
- Có `Access-Control-Expose-Headers` chứa `X-Demo-Trace` và response header `X-Demo-Trace: public-demo`.
- Không có một request OPTIONS nào tự xuất hiện từ **curl** chỉ vì bạn dùng Origin.

Browser JavaScript từ origin `http://localhost:5173` có thể đọc response khi CORS headers hợp lệ. Nếu request phát từ origin khác, hành vi sẽ khác.

### 10.2. OPTIONS preflight cho GET có custom header

```bash
curl -i -X OPTIONS \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: x-client-tag' \
  http://localhost:8080/api/public
```

Dự kiến:
- Preflight trả **2xx** (không cố định phải là 200 hay 204).
- Có `Access-Control-Allow-Origin` khớp origin.
- `Access-Control-Allow-Methods` cho biết GET được chấp nhận.
- `Access-Control-Allow-Headers` cho biết `X-Client-Tag` được chấp nhận.
- Body có thể rỗng; **controller GET không được gọi** vì đây là OPTIONS preflight.

Sau đó, browser gửi GET thật với `X-Client-Tag` và nhận response theo security rule.

### 10.3. OPTIONS preflight cho JSON POST

```bash
curl -i -X OPTIONS \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type' \
  http://localhost:8080/api/echo
```

Dự kiến: **2xx** và có CORS allow headers cho POST/Content-Type.

Nhưng nếu gửi POST thật **không có CSRF token**:

```bash
curl -i -X POST \
  -H 'Origin: http://localhost:5173' \
  -H 'Content-Type: application/json' \
  --data '{"value":"hello"}' \
  http://localhost:8080/api/echo
```

Dự kiến: **403 Forbidden** từ **CSRF protection**, không phải vì JSON POST bị CORS từ chối. Chính sách CORS đã cho origin/method/header; CSRF của Spring Security là lớp riêng. Không tắt CSRF chỉ để làm lệnh POST trả 200 nếu ứng dụng sẽ dùng browser và tự động gửi session/credentials.

### 10.4. OPTIONS preflight với Authorization cho endpoint bảo vệ

```bash
curl -i -X OPTIONS \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization,x-client-tag' \
  http://localhost:8080/api/private
```

Dự kiến: **2xx**, dù OPTIONS không gửi `Authorization` thực tế.

Request GET thật không credential:

```bash
curl -i \
  -H 'Origin: http://localhost:5173' \
  http://localhost:8080/api/private
```

Dự kiến: **401 Unauthorized** (authentication không hợp lệ/chưa có).

Request GET thật có HTTP Basic:

```bash
curl -i --user reader \
  -H 'Origin: http://localhost:5173' \
  http://localhost:8080/api/private
```

Curl hỏi password tương tác; nhập mật khẩu **demo localhost** `reader-pass`. Dự kiến **200**, body `user=reader`. Với credential thật, luôn dùng HTTPS và không đặt password trực tiếp trong command-line/history.

### 10.5. Origin không được cho phép

```bash
curl -i -X OPTIONS \
  -H 'Origin: http://untrusted.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  http://localhost:8080/api/public
```

Dự kiến: **4xx**, thông thường `403 Invalid CORS request` trong Spring WebFlux default CORS processor; không có response CORS hợp lệ cho origin đó. Khi browser nhận preflight lỗi, nó **không gửi request thật** qua flow CORS vừa kiểm tra.

### 10.6. Method hoặc header không được cho phép

Thử yêu cầu DELETE mặc dù cấu hình chỉ cho GET/HEAD/POST/OPTIONS:

```bash
curl -i -X OPTIONS \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: DELETE' \
  http://localhost:8080/api/public
```

Dự kiến: **4xx** (CORS không chấp nhận method DELETE).

Tương tự, preflight yêu cầu `X-Secret-Debug` không nằm trong `setAllowedHeaders` sẽ bị từ chối. Không sửa bằng cách `allowedHeaders("*")` thiếu kiểm soát nếu có thể chỉ cho phép các header ứng dụng cần.

### 10.7. OPTIONS thông thường, không phải preflight

```bash
curl -i -X OPTIONS http://localhost:8080/api/public
```

Đây **không phải** CORS preflight vì thiếu `Origin` và `Access-Control-Request-Method`. Nó có thể nhận 401/403/405 tùy security rules và routing; demo dùng `anyExchange().denyAll()` nên không xem request này như preflight được cho phép. **Đừng kết luận CORS sai chỉ vì OPTIONS không mang preflight headers bị từ chối.**

## 11. Thử trực tiếp bằng browser và DevTools

Để kiểm tra đúng cách browser quyết định có preflight hay không, chạy frontend development ở `http://localhost:5173`, mở DevTools **Network**, bật filter hiển thị OPTIONS/Fetch requests. Ví dụ từ JavaScript console của trang đó:

### Case A — simple GET, không OPTIONS

```javascript
const r1 = await fetch("http://localhost:8080/api/public");
console.log(r1.status, await r1.text()); // Dự kiến: 200 public-ok
```

Nếu không có yếu tố khác cần preflight, Network chỉ có GET. Response được JS đọc nhờ `Access-Control-Allow-Origin` đúng.

### Case B — GET có custom header, có OPTIONS

```javascript
const r2 = await fetch("http://localhost:8080/api/public", {
  headers: { "X-Client-Tag": "web-v1" }
});
console.log(r2.status, await r2.text()); // Dự kiến: 200 public-ok
```

Network có thể thấy:
1. `OPTIONS /api/public` hỏi GET + x-client-tag.
2. `GET /api/public` thật sau khi preflight được chấp nhận.

Nếu browser đã cache preflight hợp lệ, **có thể không thấy OPTIONS lặp lại** khi chạy lần hai. Trong DevTools, có thể dùng môi trường mới hoặc thay request theo cách phù hợp để quan sát lại.

### Case C — JSON POST có OPTIONS, actual 403 do CSRF

```javascript
const r3 = await fetch("http://localhost:8080/api/echo", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ value: "hello" })
});
console.log(r3.status); // Dự kiến: 403 khi không có CSRF
```

Browser gửi OPTIONS vì JSON Content-Type. Khi preflight được cho phép, POST thật đi tiếp rồi bị CSRF filter từ chối. **Đây không phải lỗi CORS.** Nếu frontend cần state-changing API qua browser, cần thiết kế CSRF token, authentication và cookie policy cùng với CORS.

### Case D — không đúng origin

Nếu gọi từ một trang `http://127.0.0.1:5173` hoặc `https://localhost:5173`, origin không khớp whitelist `http://localhost:5173`, nên browser có thể báo lỗi CORS. CORS so scheme, host, port **chính xác**. Không “mở tất cả” chỉ vì dev server đổi cổng; thêm những development origins cụ thể và quản trị theo môi trường.

### Khi Network không có OPTIONS

Có thể vì:
- Request thật thuộc CORS safelist (simple).
- Preflight result còn trong browser cache.
- Request được phát từ cùng origin, không phải cross-origin.
- Browser không gửi request do JS error/mixed-content/extension trước đó.
- Công cụ bạn dùng **không phải browser**, chẳng hạn `curl`, Postman hay backend script.

Đừng nhìn một lần không có OPTIONS rồi kết luận server không có CORS; kiểm tra request thật và điều kiện Fetch.

## 12. Kiểm thử tích hợp bằng WebTestClient

Đây là phần QA quan trọng vì lỗi CORS thường nằm ở **security filter ordering**, không chỉ ở controller. Test gửi các headers mô phỏng browser, nhưng **không tự thực thi CORS enforcement của một browser thật**. Vẫn nên kiểm tra DevTools/E2E trên trình duyệt.

Tệp `src/test/java/dev/example/cors/CorsSecurityTests.java`:

```java
package dev.example.cors;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CorsSecurityTests {

    private static final String ORIGIN = "http://localhost:5173";

    @Autowired
    WebTestClient client;

    @Test
    void simpleGetFromAllowedOriginSucceedsWithCorsHeader() {
        client.get().uri("/api/public")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN)
                .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void requestWithoutOriginIsNotACorsRequest() {
        client.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN)
                .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void allowedPreflightForGetCustomHeaderDoesNotNeedLogin() {
        client.options().uri("/api/public")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "x-client-tag")
                .exchange()
                .expectStatus().is2xxSuccessful()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN)
                .expectHeader().value(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS,
                        value -> assertTrue(
                                value.toLowerCase().contains("x-client-tag")));
    }

    @Test
    void allowedPreflightForJsonPostSucceedsWithoutCsrf() {
        client.options().uri("/api/echo")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type")
                .exchange()
                .expectStatus().is2xxSuccessful()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN)
                .expectHeader().value(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                        value -> assertTrue(value.contains("POST")));
    }

    @Test
    void actualPostWithoutCsrfIsRejectedDespiteCors() {
        client.post().uri("/api/echo")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("value", "hello"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN);
    }

    @Test
    void preflightForProtectedGetIsAcceptedWithoutCredentials() {
        client.options().uri("/api/private")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "authorization,x-client-tag")
                .exchange()
                .expectStatus().is2xxSuccessful()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN);
    }

    @Test
    void actualProtectedGetWithoutAuthenticationIs401() {
        client.get().uri("/api/private")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void actualProtectedGetWithAuthenticationIs200() {
        client.get().uri("/api/private")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN)
                .expectBody(String.class).isEqualTo("user=reader");
    }

    @Test
    void preflightFromUnknownOriginIsRejected() {
        client.options().uri("/api/public")
                .header(HttpHeaders.ORIGIN,
                        "http://untrusted.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void preflightWithDisallowedMethodIsRejected() {
        client.options().uri("/api/public")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void preflightWithDisallowedHeaderIsRejected() {
        client.options().uri("/api/public")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "x-secret-debug")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void ordinaryOptionsWithoutPreflightHeadersIsNotGrantedCorsBypass() {
        client.options().uri("/api/public")
                .exchange()
                .expectStatus().is4xxClientError();
    }
}
```

Chạy:

```bash
gradle test
```

**Kết quả dự kiến:** 12 tests thành công với cấu hình đầy đủ ở trên và dependency tương thích. Đây là **kỳ vọng từ API và logic code**, **không phải khẳng định đã thực thi Gradle tại workspace của bạn**. Khi chạy trên hệ thống thực, kiểm tra test report và log để xác nhận.

### Ý nghĩa các test

1. GET simple từ allowed origin có 200 và ACAO đúng.
2. GET same-origin/không Origin không cần CORS header.
3. OPTIONS GET với custom header được chấp nhận mà không yêu cầu login.
4. OPTIONS JSON POST trả 2xx, method POST được phép.
5. Actual JSON POST không có CSRF bị 403 dù CORS hợp lệ.
6. OPTIONS cho endpoint private không cần credentials.
7. GET private thực tế không login vẫn 401.
8. GET private với Basic hợp lệ trả 200.
9. Origin ngoài allowlist bị 403 ở preflight.
10. Method DELETE không được phép bị 403.
11. Header `x-secret-debug` không được phép bị 403.
12. OPTIONS không có dấu hiệu preflight **không được đặc cách** chỉ vì nó là OPTIONS.

**Tại sao test preflight dùng `is2xxSuccessful()`?** HTTP status thành công của preflight có thể là 200 hoặc 204 tùy framework/config. CORS semantics dựa trên status phù hợp và allow headers, không cần gắn cố định một mã cho mọi triển khai.

**Tại sao test 12 dùng `is4xxClientError()`?** OPTIONS thông thường có thể trả 401, 403 hoặc 405 tùy authentication/authorization/routing. Điều cần kiểm là không lẫn nó với CORS preflight hợp lệ, không phải ép một mã cụ thể.

### Mở rộng test CSRF ở tầng mock

Nếu muốn chứng minh endpoint POST thực sự chạy khi có CSRF token hợp lệ, có thể dùng Spring Security Test với `WebTestClient.bindToApplicationContext(context).apply(springSecurity())` và `mutateWith(csrf())`. Đây là **mẫu kiểm thử mở rộng**, không nằm trong class `CorsSecurityTests` (đang dùng RANDOM_PORT) vì mock CSRF thường được áp dụng với client gắn vào Spring application context:

```java
// Fragment JUnit khi đã @Autowired ApplicationContext context.
// Cần dependency testImplementation 'org.springframework.security:spring-security-test'.
WebTestClient secureClient = WebTestClient
        .bindToApplicationContext(context)
        .apply(SecurityMockServerConfigurers.springSecurity())
        .configureClient()
        .build();

secureClient.mutateWith(SecurityMockServerConfigurers.csrf())
        .post().uri("/api/echo")
        .header("Origin", "http://localhost:5173")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("value", "hello"))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.echo").isEqualTo("hello");
```

Đây là **fragment không phải file Java độc lập**; cần imports `ApplicationContext`, `SecurityMockServerConfigurers`, `WebTestClient`, `Map` và `MediaType` và bổ sung test dependency đã ghi trong comment. Nó xác minh **POST có CSRF token** được xử lý, không minh họa browser tự lấy/gắn CSRF token vào request. Với app browser thật, thiết kế CSRF token repository và client flow phù hợp.

## 13. Chẩn đoán lỗi khi frontend báo “CORS error”

### 13.1. Phân biệt lỗi browser chặn với lỗi server trả

Khi DevTools báo:

```text
Access to fetch at ... from origin ... has been blocked by CORS policy
```

hãy kiểm tra:
1. Browser có gửi OPTIONS không?
2. OPTIONS status là gì, có bị chuyển hướng login hay 401 không?
3. Request headers `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` là gì?
4. Response headers `Access-Control-Allow-Origin`, `Allow-Methods`, `Allow-Headers` có đúng không?
5. Browser có gửi actual request sau OPTIONS không?
6. Actual request có 401/403/500 do authentication/CSRF/authorization không?
7. Có reverse proxy/gateway nào xóa hoặc sửa CORS headers không?

Lỗi CORS hiện ra ở browser **không chứng minh Spring Controller đã chạy**; preflight có thể bị chặn trước controller. Ngược lại, một response 401/403 có ACAO đúng sẽ được JavaScript thấy status/body nếu security/browser policy cho phép, và đó là **lỗi authentication/authorization**, không phải lỗi CORS.

### 13.2. “Preflight response is not successful” / OPTIONS 401

**Nguyên nhân thường gặp:** Security nhận OPTIONS trước CORS và yêu cầu login, hoặc gateway chuyển hướng login/HTTPS. Preflight không có cookie/token thật nên bị 401/302.

**Cách sửa:** Tích hợp `CorsConfigurationSource` vào `ServerHttpSecurity.cors(...)` hoặc dùng `CorsWebFilter` đúng thứ tự; kiểm tra gateway và security chain. Không chỉ thêm `OPTIONS permitAll` rồi bỏ qua allow headers.

### 13.3. “No Access-Control-Allow-Origin” dù API trả 200

Nguyên nhân có thể là:
- Origin không nằm trong allowedOrigins.
- CORS source đăng ký sai path, ví dụ `/api/**` nhưng request vào `/auth/**`.
- Chỉ cấu hình ở một security chain, request đi chain khác.
- CORS processing bị disable `cors(cors -> cors.disable())`.
- Proxy/cache bỏ header hoặc response đến từ gateway error page.

Dùng DevTools/curl với Origin chính xác để kiểm tra response, không chỉ nhìn status.

### 13.4. "Request header field authorization is not allowed"

Preflight `Access-Control-Request-Headers` có `authorization` nhưng policy `allowedHeaders` chưa cho phép. Bổ sung **tên header** cần thiết trong allowlist, rồi đảm bảo request thật vẫn qua authentication. **Không trả token** trong `Access-Control-Allow-Headers`: đó là danh sách tên headers, không phải secret values.

### 13.5. "Method PUT is not allowed"

Origin hợp lệ nhưng `Access-Control-Request-Method: PUT` không nằm trong `allowedMethods`. Đánh giá business endpoint có hỗ trợ PUT không, rồi cập nhật cả CORS policy và HTTP routing/authorization. Đừng sửa bằng `allowedMethods("*")` khi có thể liệt kê methods thật.

### 13.6. Preflight 2xx nhưng actual POST 403

Đây là tình huống có chủ đích trong demo: CORS đã chấp nhận origin/method/headers, nhưng actual POST thiếu **CSRF token**. Có thể cũng do thiếu quyền, session hết hạn hoặc invalid authentication.

**Cách sửa:** kiểm tra security status và CSRF flow; không mặc định tắt CSRF cho browser session app.

### 13.7. Cookie không xuất hiện khi gọi cross-origin

Xem lại:
- `fetch(..., { credentials: "include" })` và server `Access-Control-Allow-Credentials: true`.
- Origin cụ thể, **không** `*` khi credentialed.
- Cookie `SameSite=None; Secure` khi mô hình cross-site cần, HTTPS thực tế và browser third-party cookie policy.
- Domain/Path/Secure/HttpOnly của cookie và proxy.
- CSRF token nếu request thay đổi trạng thái.

Demo này **cố ý `allowCredentials(false)`**, nên không phải cấu hình để frontend cross-origin dùng session cookie. Không bật `true` chỉ vì frontend báo lỗi mà chưa đánh giá threat model.

### 13.8. Preflight bị redirect

Một số browser không xử lý redirect cho preflight như mong muốn. Nếu proxy đổi HTTP→HTTPS hay rewrite path, cấu hình frontend gọi **URL HTTPS cuối cùng ngay từ đầu**, tránh redirect preflight nếu có thể. Đảm bảo gateway trả CORS headers phù hợp ở tất cả route/errors. Với `Authorization` trigger preflight, client khó tránh preflight bằng cách chỉ thay request syntax.

### 13.9. Origin `null` và file://

Các nguồn như sandboxed iframe, `file://` hoặc một số tài liệu opaque origin có thể gửi `Origin: null`. Không mở `null` tùy tiện vì có thể cho phép các nguồn không mong muốn. Trong development, chạy frontend trên một HTTP local server có origin rõ ràng, rồi whitelist chính xác.

### 13.10. Browser có cache preflight

`Access-Control-Max-Age` dùng cho preflight cache riêng của browser, có giới hạn theo từng browser. Có thể thấy lần đầu OPTIONS, lần sau không. Khi debug thay đổi cấu hình, thử phiên mới hoặc điều kiện request khác thay vì suy luận server bỏ qua CORS. Cache/CDN nên tôn trọng `Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers` để tránh dùng response của origin/header không phù hợp.

## 14. Các nguyên tắc an toàn khi cấu hình CORS

| Cấu hình hoặc thói quen | Rủi ro / hiểu lầm | Cách làm phù hợp |
| --- | --- | --- |
| `allowedOrigins("*")` cho API có cookie | Browser credentialed request không thể dùng wildcard origin theo chuẩn; mở quá rộng cho các trường hợp khác | Liệt kê origins cần thiết |
| `allowedHeaders("*")` mọi nơi | Mở rộng bề mặt request JS khi không cần | Chọn headers đã phê duyệt |
| `allowedMethods("*")` để chữa lỗi | Khó kiểm soát method được chấp nhận | Liệt kê GET/POST/... theo API contract |
| `OPTIONS /** permitAll` nhưng không có CORS config | Preflight vẫn thiếu allow headers | Tích hợp CORS filter/source |
| Bắt preflight login/CSRF | Browser không gửi actual request | Xử lý preflight trước security |
| Coi preflight 2xx là user đã login | OPTIONS không mang credentials thật | Xác thực actual request |
| Bỏ CSRF vì đã có CORS | Simple POST vẫn có thể được gửi và gây side effect | Đánh giá CSRF độc lập |
| Tin Origin như bằng chứng user hợp lệ | Non-browser caller giả Origin dễ dàng | Bắt buộc authn/authz |
| Trả `Access-Control-Allow-Origin` không phù hợp cho cache | CDN có thể phục vụ response sai origin | Cấu hình `Vary`/cache hợp lý |
| Vừa có `@CrossOrigin("*")` vừa có global policy khác | Khó dự đoán composition, dễ rộng quyền | Chọn một strategy kiểm soát |
| CORS riêng ở gateway và app không đồng nhất | Duplicate/missing headers, OPTIONS bị chặn | Thống nhất ownership và test E2E |
| Lưu Basic password trong JS | Lộ secret trong bundle/browser | Không hardcode credentials; dùng flow auth phù hợp |
| Dùng `curl` rồi nghĩ đã test browser CORS | Curl không enforce CORS | Test DevTools/browser E2E |
| Kết luận lỗi CORS từ status 403 đơn lẻ | 403 có thể là CSRF/authorization | Xác định OPTIONS hay actual, đọc headers |
| Cho phép origin với `Origin: null` vô điều kiện | Opaque origins có thể không đáng tin | Chỉ cho khi threat model chấp nhận |

## 15. Checklist debug nhanh theo thứ tự

1. **Origin thật:** copy nguyên `Origin` từ browser Network; kiểm tra scheme/host/port.
2. **Có preflight không:** tìm OPTIONS và các request headers tương ứng.
3. **Đúng route:** OPTIONS đi tới path nào? `CorsConfigurationSource` có bao phủ path không?
4. **Preflight không mang credential:** tránh đòi cookie/token trên OPTIONS.
5. **Methods:** `Access-Control-Request-Method` có được phép không?
6. **Headers:** các tên trong `Access-Control-Request-Headers` có được phép không?
7. **Status:** preflight 2xx; nếu 3xx/4xx/5xx xem proxy/filter trước.
8. **Response CORS:** ACAO/AllowMethods/AllowHeaders/MaxAge và Vary có đúng?
9. **Actual request:** có được gửi sau OPTIONS không? Nếu có, status 401/403 có thể thuộc auth/CSRF.
10. **Credentialed mode:** nếu có cookies, kiểm tra `Allow-Credentials`, origin cụ thể, SameSite/Secure.
11. **Cache:** browser preflight cache/CDN có đang che thay đổi config không?
12. **Kiểm thử hai phía:** `curl` để mô phỏng protocol, DevTools để xác nhận browser enforcement và Spring security tests để xác nhận ordering.

## 16. Câu hỏi tự kiểm tra

**1. Origin gồm những thành phần nào?**  
**Đáp án:** Scheme, host, port. Path/query không tạo origin khác.

**2. `http://localhost:5173` và `http://localhost:8080` có cùng origin không?**  
**Đáp án:** Không, khác port.

**3. GET không custom header có cần preflight không?**  
**Đáp án:** Thông thường không nếu mọi điều kiện CORS safelist khác đều thỏa mãn.

**4. POST `application/json` có cần preflight?**  
**Đáp án:** Thông thường có, vì Content-Type không thuộc ba media types safelisted.

**5. GET có `Authorization` có cần preflight không?**  
**Đáp án:** Có trong browser CORS vì Authorization không safelisted.

**6. Preflight luôn dùng method gì?**  
**Đáp án:** OPTIONS.

**7. `Access-Control-Request-Method: DELETE` có nghĩa OPTIONS đang xóa dữ liệu không?**  
**Đáp án:** Không; nó hỏi server có cho gửi DELETE thật sau đó không.

**8. Ba header giúp nhận diện preflight là gì?**  
**Đáp án:** HTTP OPTIONS cộng `Origin` và `Access-Control-Request-Method`; `Access-Control-Request-Headers` tùy chọn.

**9. Browser có gửi raw Basic/JWT token trong preflight không?**  
**Đáp án:** Theo flow preflight chuẩn, không gửi Authorization value của request thật; chỉ có thể liệt kê tên header `authorization`.

**10. Preflight 2xx bảo đảm actual POST 200 không?**  
**Đáp án:** Không. POST thật vẫn qua authentication, authorization, CSRF, validation và business logic.

**11. Vì sao CORS phải trước Spring Security authentication?**  
**Đáp án:** Preflight không có credentials như actual request; nếu Security yêu cầu đăng nhập trước, OPTIONS có thể bị 401/redirect.

**12. `OPTIONS /api/public` không Origin và không Access-Control-Request-Method có phải preflight không?**  
**Đáp án:** Không, đó là OPTIONS thông thường.

**13. `Access-Control-Allow-Origin: *` có phù hợp với response credentialed `allowCredentials=true` không?**  
**Đáp án:** Không. Credentialed browser requests cần allowed origin cụ thể và Allow-Credentials đúng.

**14. Có thể dùng CORS để cấm curl gọi API không?**  
**Đáp án:** Không. CORS là browser enforcement; server-to-server/curl không bị bảo vệ bằng CORS.

**15. Nếu JSON POST preflight thành công nhưng bị 403, phải kiểm tra gì?**  
**Đáp án:** Xác định 403 đến từ actual POST, kiểm tra CSRF token, authentication và authorization trước khi đổi CORS.

**16. Tại sao browser đôi khi không gửi lại OPTIONS?**  
**Đáp án:** Preflight response có thể được cache trong khoảng thời gian nhất định; request cũng có thể thay đổi để trở thành simple/same-origin.

**17. Có cần controller riêng `@RequestMapping(OPTIONS)` cho CORS không?**  
**Đáp án:** Không nếu CORS layer xử lý preflight đúng; controller OPTIONS thông thường có mục đích khác.

**18. `Vary` giúp gì trong CORS?**  
**Đáp án:** Hướng dẫn caches phân biệt response dựa trên Origin, request method/headers liên quan để tránh phục vụ CORS headers sai ngữ cảnh.

### Bài tập thực hành

1. Chạy demo, dùng `curl -H Origin` và DevTools để so simple GET có OPTIONS hay không. Mô tả khác biệt giữa tool và browser.
2. Từ frontend `http://localhost:5173`, gửi GET có `X-Client-Tag`, tìm OPTIONS trong Network và kiểm tra `Access-Control-Request-Headers`.
3. Đổi `X-Client-Tag` thành `X-Unknown` mà không sửa CORS policy; quan sát preflight bị chặn. Sửa allowHeaders **có chủ đích** để hiểu điều kiện.
4. Gửi OPTIONS yêu cầu DELETE khi allowedMethods chưa có DELETE; giải thích vì sao đây là CORS rejection chứ không phải controller DELETE.
5. Gửi OPTIONS đến `/api/private` có `Access-Control-Request-Headers: authorization` **không** kèm Basic credentials; xác minh 2xx, rồi gửi GET thật không login và nhận 401.
6. Thử JSON POST không CSRF: preflight 2xx nhưng actual 403. Viết ngắn sự khác nhau giữa CORS và CSRF.
7. Thay frontend origin thành `http://127.0.0.1:5173` hoặc port 3000, kiểm chứng chính sách exact origins và cập nhật danh sách cho môi trường development nếu cần.
8. Trên một ứng dụng browser login bằng session, thiết kế `allowCredentials`, cookie SameSite/Secure và CSRF đúng; giải thích vì sao không thể chỉ bật wildcard.
9. Thêm test `Access-Control-Expose-Headers` cho `X-Demo-Trace`; lưu ý việc expose header không làm dữ liệu bí mật an toàn.
10. Vẽ luồng một request preflight và actual request qua reverse proxy/gateway; xác định vị trí CORS bị chặn hoặc sửa headers.
11. Đổi `setMaxAge(600L)` thành thời gian ngắn trong môi trường test, quan sát preflight cache (có thể cần browser/profile mới).
12. Thêm endpoint GET bảo vệ role ADMIN, kiểm thử origin hợp lệ + preflight thành công vẫn nhận 403 với user thiếu role.

## 17. Tài liệu tham khảo chính thức

- [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): CORS phải xử lý trước Spring Security, ví dụ `UrlBasedCorsConfigurationSource` và `CorsWebFilter`.
- [Spring Security 6.x API — ServerHttpSecurity.CorsSpec](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html): `configurationSource` và cách Spring Security tích hợp CORS.
- [Spring Framework 6.1 — WebFlux CORS API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/cors/reactive/package-summary.html): reactive `CorsWebFilter`, `CorsConfigurationSource`, `UrlBasedCorsConfigurationSource`.
- [Spring Framework — CORS in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): `@CrossOrigin`, cấu hình CORS toàn cục, preflight processing.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): simple requests, preflighted requests, safelist và credentialed requests.
- [MDN — Preflight request](https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request): OPTIONS và `Access-Control-Request-Method`.
- [MDN — HTTP OPTIONS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods/OPTIONS): phân biệt mục đích của OPTIONS và CORS preflight.
- [MDN — CORS errors](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors): cách đọc lỗi browser.
- [Fetch Standard](https://fetch.spec.whatwg.org/): điều kiện CORS-safelisted request, preflight và credential modes.
- [Spring Security — CSRF testing in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): kiểm thử CSRF độc lập với CORS bằng `WebTestClient`.

**Ghi nhớ:** **Simple cross-origin request** đi thẳng tới server nhưng response vẫn bị browser kiểm tra CORS. **Non-safelisted method/header/content type** khiến browser gửi **OPTIONS preflight** trước; OPTIONS hỏi về method/headers **của request thật**, không mang credentials thực tế để login. Trong **Spring Security reactive**, CORS phải xử lý **trước authentication**; preflight thành công **không miễn** xác thực, phân quyền hay CSRF của request thật.