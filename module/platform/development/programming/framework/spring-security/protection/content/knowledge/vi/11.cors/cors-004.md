# Allowed methods, allowed headers và exposed headers

## 1. Vì sao cần phân biệt ba loại quyền?

Một frontend tại `https://app.example` gọi API Spring Security ở `https://api.example` để tạo đơn hàng. Frontend muốn:

1. Gửi HTTP `POST`.
2. Đặt request headers `Content-Type: application/json` và `Authorization: Bearer ...`.
3. Đọc response header `X-Request-Id` để hỗ trợ đội vận hành truy vết.
4. Đọc response header `X-RateLimit-Remaining` để hiển thị số lượt gọi còn lại.

Các nhu cầu này thuộc **ba quyền khác nhau** trong Cross-Origin Resource Sharing (CORS):

| Quyền CORS | HTTP response header | Trả lời câu hỏi |
| --- | --- | --- |
| **Allowed methods** | `Access-Control-Allow-Methods` | Request thực tế có được dùng phương thức HTTP dự định hay không? |
| **Allowed headers** | `Access-Control-Allow-Headers` | Request thực tế có được mang các **request headers** không safelisted đã hỏi hay không? |
| **Exposed headers** | `Access-Control-Expose-Headers` | JavaScript có được **đọc thêm response headers** ngoài nhóm mặc định hay không? |

Hai header đầu được trình duyệt xem xét trong **preflight OPTIONS response** khi request cần preflight. Header thứ ba được xét trên **actual response** khi JavaScript muốn đọc các response headers tùy biến.

Tất cả còn phụ thuộc vào quyền gốc `Access-Control-Allow-Origin` và, khi áp dụng, `Access-Control-Allow-Credentials`. Cấu hình đúng ba quyền không tự thay thế authentication, authorization, CSRF hay kiểm soát session.

### Mục tiêu học tập

Sau bài này, người học có thể:

- Phân tích preflight request qua `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
- Chọn giá trị `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers` phù hợp với API.
- Dùng `Access-Control-Expose-Headers` để frontend đọc response headers cần thiết, không mở toàn bộ tùy tiện.
- Phân biệt request header với response header và hiểu giới hạn của wildcard `*`, đặc biệt với credentials.
- Cấu hình Spring Security **Servlet** và **Reactive**, kiểm tra các trường hợp được phép và bị từ chối bằng DevTools, `curl` và ví dụ test.

Bài học thuộc mô-đun `SPRING_SECURITY_HTTP_PROTECTION`, nơi các phòng vệ HTTP và trình duyệt gồm CORS, CSRF, CSP, security headers, HSTS, HTTP firewall và session security được kết hợp trên cả hai nền tảng. Phạm vi ở đây là **quy tắc CORS cho phương thức và header**, không phải hướng dẫn chung để vô hiệu hóa các lớp phòng vệ khác.

## 2. Hiểu luồng trước khi đặt cấu hình

Giả sử JavaScript thực hiện:

~~~javascript
const response = await fetch("https://api.example/api/orders", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer <access-token>",
    "X-Request-Id": "req-frontend-202"
  },
  body: JSON.stringify({ productId: 42, quantity: 2 })
});
~~~

Request trên thường cần **preflight** vì:

- `Content-Type: application/json` không thuộc tập giá trị CORS-safelisted của `Content-Type`.
- `Authorization` không phải request header CORS-safelisted.
- `X-Request-Id` là request header tùy biến.

Trình duyệt kiểm tra trước bằng một `OPTIONS` tự sinh:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example
Origin: https://app.example
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization, content-type, x-request-id
~~~

Preflight mang **tên** các request header định gửi, không mang giá trị token, không có body JSON của đơn hàng. Việc trình duyệt hiển thị tên header viết thường và thứ tự khác nhau là bình thường.

API cho phép và phản hồi:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-Id
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Trình duyệt kiểm tra cả **origin**, **method** lẫn **request headers**. Nếu các điều kiện preflight đạt, nó mới gửi actual `POST /api/orders` cùng các header và body thật.

API xử lý và trả actual response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example
Access-Control-Expose-Headers: X-Request-Id, X-RateLimit-Remaining
X-Request-Id: req-api-817
X-RateLimit-Remaining: 49
Vary: Origin

{"id":817,"status":"CREATED"}
~~~

Nhờ `Access-Control-Expose-Headers`, frontend đọc được:

~~~javascript
console.log(response.status); // 201
console.log(response.headers.get("X-Request-Id"));        // "req-api-817"
console.log(response.headers.get("X-RateLimit-Remaining")); // "49"
const createdOrder = await response.json();
~~~

Nếu actual response **không** có `Access-Control-Allow-Origin` hợp lệ, frontend không đọc được cả response dù preflight thành công. Nếu chỉ thiếu `Access-Control-Expose-Headers`, frontend có thể đọc body/status khi CORS hợp lệ nhưng `response.headers.get("X-Request-Id")` thường trả `null` vì header đó không thuộc nhóm response header mặc định được phép đọc.

~~~mermaid
sequenceDiagram
    participant UI as JavaScript tại app.example
    participant Browser as Trình duyệt
    participant API as API tại api.example

    UI->>Browser: fetch(POST JSON + Authorization + X-Request-Id)
    Browser->>API: OPTIONS /api/orders<br/>Origin + Request-Method + Request-Headers
    API-->>Browser: 204 + Allow-Origin + Allow-Methods + Allow-Headers
    alt Preflight hợp lệ
        Browser->>API: POST /api/orders cùng body và request headers thật
        API-->>Browser: 201 + Allow-Origin + Expose-Headers + JSON
        Browser-->>UI: Response + những response headers được phép đọc
    else Preflight thiếu một quyền
        Browser-->>UI: Lỗi CORS, không gửi POST
    end
~~~

Trong sơ đồ, thông điệp `OPTIONS` là **preflight** do trình duyệt tạo; `POST` là **actual request** của ứng dụng. Bảo mật API vẫn áp dụng cho `POST` thực tế.

## 3. Allowed methods: phương thức được phép qua preflight

`Access-Control-Allow-Methods` là response header cho biết server chấp nhận những **HTTP methods** nào trong yêu cầu cross-origin đang được hỏi bằng preflight.

Ví dụ:

~~~http
Access-Control-Allow-Methods: GET, POST, PUT
~~~

Server đang khai báo quyền CORS cho các phương thức được liệt kê. Khi preflight hỏi:

~~~http
Access-Control-Request-Method: POST
~~~

`POST` có trong danh sách, nên phần kiểm tra method đạt. Nhưng nếu preflight hỏi:

~~~http
Access-Control-Request-Method: DELETE
~~~

mà response chỉ cho `GET, POST, PUT`, phần kiểm tra method thất bại. Trình duyệt không gửi actual `DELETE` theo luồng này.

### 3.1. Method trên preflight khác method của request chính

Trong request preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Access-Control-Request-Method: POST
~~~

`OPTIONS` là HTTP method của **preflight**; `POST` là method của **actual request được hỏi quyền**. Vì thế không cần suy luận rằng phải đưa `OPTIONS` vào `Access-Control-Allow-Methods` mỗi khi frontend thực hiện `POST`. Header này cho phép method **POST** dự định, còn khả năng xử lý OPTIONS là trách nhiệm của pipeline CORS/gateway.

Ví dụ phân biệt:

| Actual request muốn gửi | Method trong `Access-Control-Request-Method` | Method nào phải được cho phép? |
| --- | --- | --- |
| `POST /api/orders` | `POST` | `POST` |
| `PUT /api/orders/817` | `PUT` | `PUT` |
| `DELETE /api/orders/817` | `DELETE` | `DELETE` |
| `GET /api/profile` có `Authorization` | `GET` | `GET` |

`GET` có header `Authorization` vẫn có thể cần preflight, mặc dù `GET` vốn là phương thức CORS-safelisted.

### 3.2. Phương thức safelisted và khi nào không có preflight

Các CORS-safelisted methods là `GET`, `HEAD` và `POST`. Một request cross-origin dùng những method này **không tự động** phải preflight. Tuy nhiên, nó vẫn có thể cần preflight do request headers hoặc điều kiện khác.

Ví dụ:

~~~javascript
// Thường không preflight: GET và không đặt header tùy biến.
await fetch("https://api.example/api/products");

// Thường có preflight vì application/json không phải Content-Type safelisted.
await fetch("https://api.example/api/orders", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ productId: 42 })
});

// Thường có preflight vì method DELETE không safelisted.
await fetch("https://api.example/api/orders/817", {
  method: "DELETE"
});
~~~

**Không có preflight không có nghĩa là không có CORS.** Trình duyệt vẫn xét `Access-Control-Allow-Origin` trên actual response. `Access-Control-Allow-Methods` không phải header cấp phép mọi request theo kiểu firewall; nó phục vụ phần kiểm tra method của **preflight**. Còn server có cho client thực hiện `DELETE` hoặc `PUT` không phải do header CORS quyết định: cần route, authentication và authorization phù hợp.

### 3.3. Method được CORS cho phép không đồng nghĩa được phân quyền

Giả sử cấu hình:

~~~http
Access-Control-Allow-Methods: GET, POST, PUT, DELETE
~~~

Đây là **khai báo quyền CORS** cho browser. Nó không tạo endpoint `DELETE`, không xác thực bearer token, không cho một nhân viên quyền xóa đơn hàng, cũng không loại bỏ quy tắc HTTP 405 hoặc HTTP 403 của API.

Ví dụ actual `DELETE /api/orders/817` có thể đi qua preflight hợp lệ nhưng bị API từ chối `403 Forbidden` vì người dùng không phải quản trị viên. Nếu actual response vẫn có `Access-Control-Allow-Origin` hợp lệ, frontend có thể đọc status 403 để hiển thị thông báo phù hợp.

Thực hành: chỉ khai báo method thực sự được thiết kế cho những API/cross-origin caller liên quan, nhưng luôn bảo vệ actual method bằng authorization phía server.

## 4. Allowed headers: những request header frontend được gửi

`Access-Control-Allow-Headers` trong **preflight response** khai báo các **tên request header** được phép sử dụng ở actual request nếu browser cần hỏi quyền cho chúng.

Ví dụ JavaScript muốn gửi:

~~~http
Authorization: Bearer <access-token>
Content-Type: application/json
X-Request-Id: req-frontend-202
~~~

Preflight có thể hỏi:

~~~http
Access-Control-Request-Headers: authorization, content-type, x-request-id
~~~

Server trả:

~~~http
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-Id
~~~

Trình duyệt kiểm tra từng tên header được hỏi. Tên HTTP header **không phân biệt hoa/thường**, nên `authorization` và `Authorization` được coi là cùng tên.

Nếu server chỉ trả:

~~~http
Access-Control-Allow-Headers: Content-Type
~~~

thì preflight **không đáp ứng** yêu cầu `Authorization` và `X-Request-Id`. Browser dừng trước actual request.

### 4.1. Phân biệt request header safelisted

Một số request headers và giá trị đủ điều kiện được **CORS-safelisted**, nên không phải lúc nào cũng cần khai báo trong preflight. Ví dụ thường gặp:

- `Accept`.
- `Accept-Language` và `Content-Language`.
- `Content-Type` nếu giá trị phù hợp một trong các kiểu `application/x-www-form-urlencoded`, `multipart/form-data` hoặc `text/plain` và đáp ứng các ràng buộc của chuẩn.

`Content-Type: application/json` **không** safelisted, còn `Content-Type: text/plain` trong điều kiện phù hợp thường safelisted.

Bản thân tên `Content-Type` không đủ để quyết định preflight; **giá trị** của nó cũng quan trọng. Một số request headers safelisted có thêm ràng buộc về nội dung/độ dài giá trị. Quy tắc quyết định cuối thuộc trình duyệt.

| Header được đặt trong request | Có thường kích hoạt preflight? | Giải thích |
| --- | --- | --- |
| `Accept: application/json` | Không, riêng header này | Thường đáp ứng safelist |
| `Content-Type: text/plain` | Không, riêng header này | Content-Type thường safelisted |
| `Content-Type: application/x-www-form-urlencoded` | Không, riêng header này | Content-Type thường safelisted |
| `Content-Type: application/json` | Có | Không phải giá trị safelisted |
| `Authorization: Bearer ...` | Có | Tên header không safelisted |
| `X-Request-Id: ...` | Có | Request header tùy biến |
| `X-Client-Version: 1.2` | Có | Request header tùy biến |

Đây là các ví dụ HTTP thông thường. Loại body, API Fetch và những điều kiện khác cũng có thể ảnh hưởng việc preflight có xảy ra hay không.

### 4.2. Những header không nên tự đặt

Browser tự quản lý một số request headers như `Origin`, `Host`, `Cookie` và các header `Access-Control-Request-*`. JavaScript không được tùy ý gán nhiều loại *forbidden request header* này.

Khi code có:

~~~javascript
await fetch("https://api.example/api/me", {
  credentials: "include"
});
~~~

`credentials: "include"` điều khiển việc browser có gửi cookie phù hợp hay không. Nó **không** làm JavaScript tự đặt `Cookie` và **không** tự kích hoạt preflight. Nếu cookie thực tế được gửi còn phụ thuộc `SameSite`, `Secure`, domain/path và chính sách trình duyệt.

Ngược lại, khi JavaScript trực tiếp đặt `Authorization`, browser thường phải đưa tên header này vào yêu cầu preflight; bản thân giá trị bearer token chỉ xuất hiện trong actual request.

### 4.3. Wildcard trong Access-Control-Allow-Headers

Có thể bắt gặp:

~~~http
Access-Control-Allow-Headers: *
~~~

Tuy nhiên, dấu `*` có các điều kiện áp dụng và **không nên xem là thay thế cho mọi header trong mọi tình huống**:

- Wildcard được hiểu theo quy tắc CORS đối với request không dùng credentials mode `include`. Với request sử dụng credentials, `*` không có tác dụng wildcard chung theo cách đó.
- `Authorization` là **CORS non-wildcard request-header name**: không được giả định chỉ `*` là đủ để browser cho phép header này. Hãy liệt kê `Authorization` cụ thể.
- Nếu client cần `Authorization`, `Content-Type` JSON và `X-Request-Id`, cấu hình rõ ba tên này dễ kiểm tra và thu hẹp phạm vi hơn.

Spring Framework có cách xử lý giá trị `allowedHeaders("*")` riêng, có thể phản hồi lại danh sách header được hỏi trong preflight. Dù vậy, đây không phải lý do để tùy tiện cho phép mọi header trong chính sách production; hãy chọn allowlist theo yêu cầu thực tế của frontend.

## 5. Exposed headers: response header nào JavaScript được đọc?

Ngay cả khi CORS cho phép JavaScript đọc **response body** và **HTTP status**, browser vẫn giới hạn những **response headers** mà JavaScript có thể lấy từ `Response.headers`.

Một nhóm response headers được CORS safelist cho phép đọc theo mặc định:

| Response header thường được đọc mặc định | Ví dụ công dụng |
| --- | --- |
| `Cache-Control` | Thông tin cache |
| `Content-Language` | Ngôn ngữ nội dung |
| `Content-Length` | Độ dài nội dung theo HTTP |
| `Content-Type` | Kiểu media, ví dụ JSON |
| `Expires` | Hết hạn cache |
| `Last-Modified` | Thời điểm tài nguyên được sửa |
| `Pragma` | Chỉ dẫn tương thích liên quan cache |

Lưu ý: header có nằm trong safelist không đồng nghĩa **server bắt buộc trả header đó**; nếu nó không tồn tại trong actual response thì `response.headers.get(...)` vẫn có thể trả `null`. Các hạn chế khác của Fetch vẫn có thể áp dụng trong những ngữ cảnh đặc biệt.

### 5.1. Ví dụ muốn đọc X-Request-Id

Server phản hồi:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example
X-Request-Id: req-api-817

{"result":"ok"}
~~~

JavaScript:

~~~javascript
const response = await fetch("https://api.example/api/health");
console.log(response.status);                     // 200
console.log(response.headers.get("Content-Type")); // "application/json"
console.log(response.headers.get("X-Request-Id")); // null (chưa expose)
~~~

CORS có thể đã cho phép JavaScript đọc JSON, nhưng `X-Request-Id` **không thuộc nhóm response header mặc định được đọc**.

Server cần thêm **trên actual response**:

~~~http
Access-Control-Expose-Headers: X-Request-Id
~~~

Lúc đó:

~~~javascript
const requestId = response.headers.get("X-Request-Id");
console.log(requestId); // "req-api-817"
~~~

Tương tự, nếu frontend muốn đọc thông tin giới hạn API:

~~~http
Access-Control-Expose-Headers: X-Request-Id, X-RateLimit-Remaining
X-RateLimit-Remaining: 49
~~~

JavaScript đọc:

~~~javascript
const remaining = response.headers.get("X-RateLimit-Remaining");
console.log(remaining); // "49"
~~~

Giá trị `Access-Control-Expose-Headers` là danh sách **tên response header**, không chứa giá trị của chúng. Cần trả header thật trong actual response. Cấu hình expose một header không tồn tại sẽ không tạo header đó.

### 5.2. Không nhầm allowed headers với exposed headers

Hai cấu hình sau phục vụ **hai hướng khác nhau**:

~~~http
# Preflight response:
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-Id
~~~

~~~http
# Actual response:
Access-Control-Expose-Headers: X-Request-Id, X-RateLimit-Remaining
~~~

- `Access-Control-Allow-Headers` cho phép frontend **gửi request header**.
- `Access-Control-Expose-Headers` cho phép frontend **đọc response header**.

Một tên như `X-Request-Id` có thể có ở cả request và response, nhưng cần khai báo **đúng chiều**. Đưa nó vào `Allow-Headers` không làm `response.headers.get("X-Request-Id")` hoạt động nếu response thiếu `Expose-Headers`.

### 5.3. Wildcard và các header bị cấm đọc

`Access-Control-Expose-Headers: *` có thể là wildcard cho response headers khi điều kiện credentials mode của request cho phép. Khi request dùng `credentials: "include"`, `*` **không** được hiểu là wildcard expose theo cách đó; hãy liệt kê cụ thể tên cần đọc.

Đặc biệt, `Set-Cookie` là **forbidden response-header name** đối với JavaScript. Ví dụ:

~~~http
Access-Control-Expose-Headers: Set-Cookie, X-Request-Id
Set-Cookie: SESSION=...; HttpOnly; Secure
X-Request-Id: req-api-817
~~~

Dù server liệt kê `Set-Cookie`, JavaScript vẫn **không** được đọc nó bằng `response.headers.get("Set-Cookie")`. Browser có thể xử lý lưu cookie theo các quy tắc cookie và credentials riêng. Các header chứa thông tin nhạy cảm khác cũng nên được đánh giá trước khi expose cho một origin đã được phép.

## 6. Tóm tắt ba header theo vị trí trong HTTP

| Thành phần | Request hay response? | Xuất hiện chủ yếu ở đâu? | Ví dụ |
| --- | --- | --- | --- |
| `Access-Control-Request-Method` | Browser gửi request | Preflight OPTIONS request | `POST` |
| `Access-Control-Request-Headers` | Browser gửi request | Preflight OPTIONS request | `authorization, content-type` |
| `Access-Control-Allow-Methods` | Server gửi response | Preflight OPTIONS response | `GET, POST` |
| `Access-Control-Allow-Headers` | Server gửi response | Preflight OPTIONS response | `Authorization, Content-Type` |
| `Access-Control-Expose-Headers` | Server gửi response | Actual response | `X-Request-Id` |
| `Access-Control-Allow-Origin` | Server gửi response | Preflight và actual response cần CORS | `https://app.example` |
| `Access-Control-Allow-Credentials` | Server gửi response | Khi response cần hỗ trợ credentials | `true` |
| `Access-Control-Max-Age` | Server gửi response | Preflight response | `600` |

**Một quy tắc để nhớ:** `Allow-Methods` và `Allow-Headers` nằm ở giai đoạn hỏi **“có được gửi actual request này không?”**; `Expose-Headers` nằm ở giai đoạn **“JS được đọc những trường nào trên actual response?”**.

## 7. Cấu hình Spring Security Servlet

Spring Security trên Servlet nên xử lý CORS sớm hơn các bộ lọc xác thực, vì preflight `OPTIONS` thường không mang token hoặc cookie xác thực của actual request. Có thể khai báo `CorsConfigurationSource` và bật `http.cors(...)`:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(List.of("https://app.example"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Authorization",
            "Content-Type",
            "X-Request-Id"
        ));
        cors.setExposedHeaders(List.of(
            "X-Request-Id",
            "X-RateLimit-Remaining"
        ));
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Giải thích theo đúng ba trường của bài:

1. `setAllowedMethods(...)` cho phép browser gửi actual request bằng `GET`, `POST`, `PUT` sau preflight phù hợp. API vẫn có quyền trả 403 hoặc 405 theo endpoint và quyền của người dùng.
2. `setAllowedHeaders(...)` cho phép request gửi `Authorization`, `Content-Type`, `X-Request-Id` khi cần preflight.
3. `setExposedHeaders(...)` cho phép JavaScript đọc response headers `X-Request-Id` và `X-RateLimit-Remaining` nếu server có trả chúng.
4. `setMaxAge(600L)` cho phép browser cache kết quả preflight trong phạm vi và giới hạn của trình duyệt.
5. `registerCorsConfiguration("/api/**", cors)` áp dụng chính sách cho các request path API tương ứng.

Ví dụ này **không bật** `allowCredentials`; phù hợp để minh họa cross-origin request không yêu cầu cookie theo `credentials: "include"`. Nếu API thực sự dùng session cookie hoặc cần đọc response của request có credentials mode `include`, cần cân nhắc thêm `cors.setAllowCredentials(true)`, dùng allowlist origin cụ thể và cấu hình cookie/session/CSRF thích hợp.

`anyRequest().authenticated()` không tự cung cấp cơ chế đăng nhập hoặc resource server; cần cấu hình authentication thực sự khi tích hợp vào ứng dụng. Không nên tắt CSRF chỉ để sửa lỗi CORS của `POST`.

### 7.1. Cấu hình được ánh xạ ra HTTP như thế nào?

Khi nhận preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization, content-type, x-request-id
~~~

Spring CORS kiểm tra origin và method/header với cấu hình. Với request được chấp nhận, response có thể chứa:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example
Access-Control-Allow-Methods: GET,POST,PUT
Access-Control-Allow-Headers: Authorization,Content-Type,X-Request-Id
Access-Control-Max-Age: 600
~~~

Trên actual response, Spring có thể thêm:

~~~http
Access-Control-Allow-Origin: https://app.example
Access-Control-Expose-Headers: X-Request-Id,X-RateLimit-Remaining
~~~

Giá trị và khoảng trắng thực tế do framework tuần tự hóa; kiểm thử nên chú trọng **các tên/method được phép**, không phụ thuộc vào việc giữa các giá trị có dấu cách hay không. Header `X-Request-Id` và `X-RateLimit-Remaining` phải do ứng dụng/filter tương ứng thực sự tạo.

## 8. Cấu hình tương ứng cho Spring Security Reactive

Với WebFlux, cấu hình qua `ServerHttpSecurity` và `SecurityWebFilterChain`, dùng `UrlBasedCorsConfigurationSource` thuộc package `org.springframework.web.cors.reactive`:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-Request-Id"
        ));
        cors.setExposedHeaders(List.of(
            "X-Request-Id", "X-RateLimit-Remaining"
        ));
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);

        return http
            .cors(spec -> spec.configurationSource(source))
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated())
            .build();
    }
}
~~~

Trên cả Servlet và Reactive, ý nghĩa của allowed methods/headers/exposed headers **giống nhau**. Điểm khác biệt là loại filter và security chain. Nếu hệ thống sử dụng `CorsWebFilter` riêng trong WebFlux, cần đặt đúng thứ tự trước lớp xác thực chặn preflight và tránh cấu hình CORS trùng lặp ở nhiều tầng.

Ở hệ thống có reverse proxy hoặc API gateway, kiểm tra cả route `OPTIONS`, header của response lỗi 401/403/500 và header chèn bởi gateway. Cấu hình trong ứng dụng đúng nhưng proxy xóa hoặc nhân đôi header vẫn có thể khiến browser thất bại.

## 9. Kiểm thử phương thức, request header và exposed header

### 9.1. Ma trận kiểm thử preflight

Giả sử chỉ cho phép origin `https://app.example`, methods `GET`, `POST`, `PUT` và request headers `Authorization`, `Content-Type`, `X-Request-Id`.

| Preflight hỏi gì? | Kết quả mong đợi | Nguyên nhân |
| --- | --- | --- |
| `POST` + `authorization, content-type` | Cho phép | Method và hai header đều có trong allowlist |
| `PUT` + `content-type` | Cho phép | Method/header được phép |
| `DELETE` + `content-type` | Từ chối | `DELETE` không có trong `Allow-Methods` |
| `POST` + `x-admin-override` | Từ chối | Header tùy biến chưa được cho phép |
| `GET` + `authorization` | Cho phép | `GET` được phép, `Authorization` được cho phép |
| `POST` + `authorization`, nhưng `Origin: https://evil.example` | Từ chối | Origin không được cho phép dù method/header hợp lệ |

Lưu ý: với các request thực tế không cần preflight, browser không kiểm tra `Allow-Methods` và `Allow-Headers` theo bảng trên trước khi gửi, mà xét quyền CORS trên actual response. Ma trận này dành riêng cho **preflight cần thiết**.

### 9.2. Thử OPTIONS bằng curl

Mô phỏng preflight hợp lệ:

~~~bash
curl -i -X OPTIONS "https://api.example/api/orders" \
  -H "Origin: https://app.example" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization, content-type, x-request-id"
~~~

Đổi method thành phương thức không được phép:

~~~bash
curl -i -X OPTIONS "https://api.example/api/orders" \
  -H "Origin: https://app.example" \
  -H "Access-Control-Request-Method: DELETE" \
  -H "Access-Control-Request-Headers: content-type"
~~~

Đổi request header thành tên không được phép:

~~~bash
curl -i -X OPTIONS "https://api.example/api/orders" \
  -H "Origin: https://app.example" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: x-admin-override"
~~~

Với cơ chế xử lý CORS chuẩn của Spring, request preflight không hợp lệ có thể nhận `403 Invalid CORS request`. Tùy proxy/security filter, biểu hiện HTTP cụ thể có thể khác. Trong DevTools, điều cần xác minh là browser **không gửi actual request** sau preflight bị từ chối.

`curl` chỉ mô phỏng request/response HTTP, **không áp dụng chính sách CORS như browser**. Các tên miền trên là ví dụ; cần thay bằng API thật khi chạy. Trên Windows PowerShell cũ, dùng `curl.exe` nếu `curl` là alias của `Invoke-WebRequest`.

### 9.3. Thử exposed headers trong trình duyệt

Giả sử API trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example
Access-Control-Expose-Headers: X-Request-Id, X-RateLimit-Remaining
X-Request-Id: req-api-818
X-RateLimit-Remaining: 37
Content-Type: application/json
~~~

Từ đúng frontend origin:

~~~javascript
const res = await fetch("https://api.example/api/products");
console.log({
  status: res.status,
  contentType: res.headers.get("Content-Type"),
  requestId: res.headers.get("X-Request-Id"),
  remaining: res.headers.get("X-RateLimit-Remaining")
});
~~~

Nếu xóa riêng `Access-Control-Expose-Headers` khỏi actual response, trong khi origin vẫn được cấp quyền:

- `status` và body vẫn có thể được đọc.
- `Content-Type` vẫn thường có thể được đọc vì được safelist.
- `X-Request-Id` và `X-RateLimit-Remaining` thường trả `null`, dù chúng xuất hiện trên Network tab.

Lưu ý: nếu browser nhận một **opaque response** (chẳng hạn do `mode: "no-cors"`), code sẽ có những hạn chế khác. `no-cors` không phải cách sửa lỗi hoặc lấy quyền đọc cross-origin.

### 9.4. Kiểm thử Servlet bằng MockMvc

Với Spring Boot và các dependency test phù hợp, một ví dụ kiểm thử preflight khi cấu hình ở mục 7 được nạp:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsPermissionsIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void allowsRequestedPostAndHeaders() throws Exception {
        mvc.perform(options("/api/orders")
                .header("Origin", "https://app.example")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                    "authorization,content-type,x-request-id"))
            .andExpect(status().isOk())
            .andExpect(header().exists("Access-Control-Allow-Methods"))
            .andExpect(header().exists("Access-Control-Allow-Headers"));
    }

    @Test
    void rejectsMethodNotInAllowlist() throws Exception {
        mvc.perform(options("/api/orders")
                .header("Origin", "https://app.example")
                .header("Access-Control-Request-Method", "DELETE"))
            .andExpect(status().isForbidden());
    }

    @Test
    void rejectsUnknownRequestedHeader() throws Exception {
        mvc.perform(options("/api/orders")
                .header("Origin", "https://app.example")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "x-admin-override"))
            .andExpect(status().isForbidden());
    }
}
~~~

Test minh họa hành vi của cấu hình Spring CORS, chưa được chạy trên một project thật. Test exposed headers cần actual response của một endpoint có trả các header đó; khi cần xác thực, hãy bổ sung cơ chế tạo phiên hoặc token hợp lệ cho actual request. Với WebFlux, sử dụng `WebTestClient` và cùng bộ header preflight.

## 10. Chẩn đoán các lỗi dễ nhầm

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| `OPTIONS` 204/200 nhưng browser vẫn chặn | Thiếu `Access-Control-Allow-Methods` hoặc `Access-Control-Allow-Headers` phù hợp | So từng header `Access-Control-Request-*` với response |
| Chỉ `POST application/json` lỗi, `GET` hoạt động | Preflight cho `Content-Type` JSON không được xử lý | Kiểm tra OPTIONS và `Access-Control-Allow-Headers` |
| Chỉ request có `Authorization` lỗi | Header `Authorization` chưa được cho phép rõ ràng | Kiểm tra tên header trong preflight |
| `DELETE` bị CORS chặn | `DELETE` không có trong allowed methods | Kiểm tra `Access-Control-Request-Method` và cấu hình |
| `OPTIONS` trả 401/403 do bảo mật | CORS bị xử lý sau authentication hoặc gateway chặn OPTIONS | Kiểm tra thứ tự filter Spring Security và route proxy |
| `POST` trả 403 nhưng frontend chỉ thấy lỗi mạng/CORS | Actual response lỗi không có quyền `Allow-Origin` phù hợp | Xem POST response trong Network |
| Đọc JSON được nhưng `headers.get("X-Request-Id")` trả null | Thiếu `Access-Control-Expose-Headers` trên actual response, hoặc header không tồn tại | So response headers thực tế với exposed headers |
| Dùng `Expose-Headers: Set-Cookie` vẫn không đọc được cookie | `Set-Cookie` là forbidden response header | Xem chính sách cookie/DevTools; không cố đọc bằng JS |
| Dùng wildcard với `credentials: "include"` không hoạt động | Quy tắc wildcard của CORS giới hạn khi có credentials | Dùng origin và tên header cụ thể theo yêu cầu |
| Khác nhau giữa trực tiếp và qua gateway | Proxy chặn OPTIONS, xóa/sửa response headers hoặc chèn trùng CORS headers | So request/response tại từng tầng |
| Không nhìn thấy OPTIONS trong một lần gọi | Kết quả preflight có thể đã được cache | Xem `Access-Control-Max-Age`, trạng thái cache, thử phiên mới |

### 10.1. Quy trình xác định lỗi trong DevTools

1. Mở **Network** ở frontend đang chạy tại origin thật và tìm request API.
2. Xác định request có **OPTIONS preflight** hay không; nếu không có, kiểm tra điều kiện safelist và cache preflight.
3. Trên OPTIONS, đối chiếu `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` với `Access-Control-Allow-*` trong response.
4. Nếu OPTIONS thất bại, kiểm tra Spring Security CORS, gateway và rule authentication. Không suy luận rằng lỗi do endpoint business.
5. Nếu OPTIONS thành công, xem **actual request** có xuất hiện hay không và response có `Access-Control-Allow-Origin` hợp lệ không.
6. Nếu body đọc được nhưng response header tùy biến không đọc được, xem `Access-Control-Expose-Headers` **trên actual response** và chắc chắn header mục tiêu thật sự tồn tại.
7. Với request dùng session cookie, kiểm tra riêng `credentials`, `Access-Control-Allow-Credentials`, cookie `SameSite`/`Secure` và CSRF.

Không dùng `mode: "no-cors"` để tránh thông báo lỗi vì nó làm response bị giới hạn quyền đọc, không giải quyết vấn đề cấu hình server.

## 11. Ranh giới với xác thực, CSRF và bảo vệ trình duyệt

Trong mô-đun Spring Security HTTP Protection, CORS là một lớp phối hợp cùng những cơ chế khác:

| Cơ chế | Vấn đề giải quyết |
| --- | --- |
| CORS `Allow-Methods` | Browser được gửi actual request dùng method được hỏi qua preflight hay không? |
| CORS `Allow-Headers` | Browser được gửi những request header cần hỏi qua preflight hay không? |
| CORS `Expose-Headers` | JS được đọc thêm response headers nào trên actual response? |
| Authentication | Người hoặc client gửi actual request là ai? |
| Authorization | Chủ thể có được gọi endpoint và thao tác đó hay không? |
| CSRF protection | Request thay đổi trạng thái có vượt qua bảo vệ chống thao tác ngoài ý muốn không? |
| CSP `connect-src` | JavaScript của chính trang được phép kết nối tới đích nào? |
| Session/cookie protection | Session và cookie được cấp phát, truyền và bảo vệ ra sao? |

Một API cho phép `DELETE` trong `Access-Control-Allow-Methods` **không** cho mọi user quyền xóa. Một API cho phép `Authorization` trong `Access-Control-Allow-Headers` **không** có nghĩa token đã được xác thực. Một API expose `X-RateLimit-Remaining` **không** có nghĩa mọi origin đều được đọc response; origin vẫn phải được cho phép bởi CORS.

Đặc biệt, **CORS không thay thế chống CSRF**. Một số request cross-site có thể gửi tới server mà không cần preflight, và việc browser không cho JavaScript đọc kết quả không ngăn server đã thay đổi dữ liệu. Bảo vệ CSRF phải dựa trên thiết kế xác thực, session và hành vi thay đổi trạng thái thực tế.

## 12. Tình huống tự kiểm tra

**Tình huống A.** Frontend gửi `PUT` với `Content-Type: application/json`. Preflight trả `Allow-Methods: GET, POST` và `Allow-Headers: Content-Type`. Actual PUT có được gửi không?

**Đáp án:** Không. `PUT` không thuộc `Access-Control-Allow-Methods` được trả, nên preflight không đạt dù `Content-Type` được cho phép.

**Tình huống B.** Frontend gửi `POST` JSON kèm `Authorization`. Preflight trả `Allow-Methods: POST` và `Allow-Headers: Content-Type`. Actual POST có được gửi không?

**Đáp án:** Không. `Authorization` có trong `Access-Control-Request-Headers` nhưng không nằm trong `Access-Control-Allow-Headers` được trả.

**Tình huống C.** Actual response có `Access-Control-Allow-Origin` hợp lệ, `X-Request-Id: abc-123` và JSON. JavaScript đọc được JSON nhưng `response.headers.get("X-Request-Id")` là `null`. Cần sửa phần nào?

**Đáp án:** Cần thêm `Access-Control-Expose-Headers: X-Request-Id` vào **actual response**. Thêm `X-Request-Id` vào `Access-Control-Allow-Headers` không giải quyết quyền đọc response header.

**Tình huống D.** Server thêm `Access-Control-Expose-Headers: Set-Cookie`. JavaScript có đọc được giá trị `Set-Cookie` không?

**Đáp án:** Không. `Set-Cookie` thuộc nhóm forbidden response header và không thể được expose để đọc qua Fetch như các response header tùy biến.

**Tình huống E.** Một `GET` không thêm request header tùy biến và không cần preflight. Server không trả `Access-Control-Allow-Methods` trên actual response. JavaScript có nhất thiết bị chặn không?

**Đáp án:** Không. `Allow-Methods` dùng cho kiểm tra preflight. Với actual response của GET không cần preflight, browser xét `Access-Control-Allow-Origin` và các điều kiện CORS tương ứng. Nếu quyền đọc response hợp lệ, việc thiếu `Allow-Methods` trên actual response không phải lý do riêng để chặn.

**Tình huống F.** Frontend dùng `credentials: "include"` và server trả `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Credentials: true`, `Access-Control-Expose-Headers: X-Request-Id`. JS có đọc được `X-Request-Id` không?

**Đáp án:** Không. CORS đã thất bại ở `Access-Control-Allow-Origin: *` trong credentials mode này; expose thêm header không khắc phục được lỗi origin. Cần origin cụ thể và các điều kiện credentials phù hợp.

---

**Ghi nhớ:** **`Access-Control-Allow-Methods` và `Access-Control-Allow-Headers`** cho browser biết preflight có cho phép **gửi actual request** với method và request headers dự định hay không. **`Access-Control-Expose-Headers`** cho JavaScript biết **được đọc response headers bổ sung nào** khi actual response đã qua kiểm tra CORS. Phải xác minh đúng giai đoạn request/response, và luôn duy trì authentication, authorization, CSRF cùng bảo vệ session của Spring Security.
