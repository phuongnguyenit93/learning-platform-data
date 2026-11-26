# Yêu cầu thực tế và preflight OPTIONS

## Mục tiêu bài học

Sau bài này, người học có thể:

- Phân biệt **yêu cầu thực tế (actual request)** với **yêu cầu kiểm tra trước (CORS preflight request)**.
- Dự đoán khi nào trình duyệt gửi trực tiếp request cross-origin, khi nào phải gửi `OPTIONS` trước.
- Đọc các cặp HTTP request/response để xác định lý do CORS cho phép hoặc chặn.
- Cấu hình CORS trong Spring Security cho ứng dụng **Servlet** và **Reactive**, tránh để preflight bị chặn bởi xác thực.
- Kiểm tra bằng DevTools và `curl`, hiểu giới hạn của mỗi công cụ.

Bối cảnh xuyên suốt: giao diện tại `https://app.example` truy cập REST API Spring Security tại `https://api.example`. Đây là hai **origin** khác nhau vì host khác nhau. Trong mô-đun bảo vệ HTTP của Spring Security, CORS phối hợp với authentication, authorization, CSRF, security headers và quản lý session; mỗi lớp bảo vệ có nhiệm vụ riêng.

## 1. Hai request có vai trò khác nhau

Khi JavaScript sử dụng `fetch()` để gọi sang origin khác, trình duyệt áp dụng **Same-Origin Policy (SOP)** và giao thức **Cross-Origin Resource Sharing (CORS)**.

- **Actual request:** yêu cầu HTTP mà ứng dụng thật sự muốn thực hiện, chẳng hạn `GET /products` hoặc `POST /orders`. Nó có thể đọc dữ liệu, sửa dữ liệu hoặc gặp lỗi xác thực; kết quả CORS quyết định JavaScript có được truy cập phản hồi hay không.
- **Preflight request:** yêu cầu `OPTIONS` do trình duyệt tự tạo trước **một số** actual request. Nó hỏi server liệu origin hiện tại có được phép gửi **phương thức** và **request headers** dự định hay không. Nó không phải lệnh tạo đơn hàng, cập nhật dữ liệu hay xác thực người dùng.
- **Preflight response:** câu trả lời khai báo quyền CORS cho request chính. Nếu không đạt, trình duyệt dừng trước khi phát actual request.

Điều quan trọng: **không phải mọi request cross-origin đều có preflight**. Một số request đi thẳng tới API và chỉ bị kiểm tra quyền đọc khi phản hồi quay về. Preflight cũng **không thay thế** việc xét CORS trên response của actual request.

~~~mermaid
flowchart TD
    A["JavaScript gọi API khác origin"] --> B{"Request có cần preflight?"}
    B -- "Không" --> E["Trình duyệt gửi actual request"]
    B -- "Có" --> C["Trình duyệt gửi OPTIONS preflight"]
    C --> D{"Preflight được phép?"}
    D -- "Không" --> X["Báo lỗi CORS; không gửi actual request"]
    D -- "Có" --> E
    E --> F["API xử lý và trả actual response"]
    F --> G{"Actual response đạt kiểm tra CORS?"}
    G -- "Có" --> H["JavaScript đọc phản hồi"]
    G -- "Không" --> I["JavaScript không đọc được phản hồi"]
~~~

> **Hai thời điểm kiểm tra khác nhau:** preflight quyết định liệu trình duyệt có thể **tiến hành request chính** theo luồng cần kiểm tra trước; kiểm tra CORS trên actual response quyết định liệu JavaScript có **đọc được kết quả** hay không.

## 2. Khi nào trình duyệt cần preflight?

Để giảm việc phải kiểm tra trước những yêu cầu có hình thức quen thuộc với HTML truyền thống, CORS định nghĩa nhóm điều kiện *safelisted*. Một request thường không cần preflight nếu phương thức và các header do script đặt đều đáp ứng điều kiện này.

### 2.1. Phương thức và Content-Type

Các **CORS-safelisted methods** là `GET`, `HEAD` và `POST`. Các phương thức như `PUT`, `PATCH`, `DELETE` thường cần preflight khi gọi cross-origin bằng `fetch`.

Với `Content-Type`, các kiểu media được safelist (nếu thỏa các ràng buộc giá trị liên quan) là:

- `application/x-www-form-urlencoded`
- `multipart/form-data`
- `text/plain`

`application/json` **không nằm trong danh sách này**. Do đó `POST` với `Content-Type: application/json` thường cần preflight, dù `POST` là phương thức safelisted.

Một số request header phổ biến như `Accept`, `Accept-Language` và `Content-Language` cũng thuộc nhóm safelisted **chỉ khi giá trị thỏa quy định**. Ngoài tên header, có các ràng buộc về giá trị và một số trường hợp đặc biệt; vì vậy không nên biến quy tắc thành phép kiểm tra duy nhất bằng tên header.

### 2.2. Ví dụ dự đoán

| Request do JavaScript muốn gửi | Thường có preflight? | Nguyên nhân |
| --- | --- | --- |
| `GET /products`, không thêm header tùy biến | Không | Method và headers thông thường được safelist |
| `HEAD /health`, không thêm header tùy biến | Không | Method safelisted |
| `POST /contact` với `Content-Type: application/x-www-form-urlencoded` | Không | Method và Content-Type đáp ứng safelist |
| `POST /orders` với `Content-Type: application/json` | Có | `application/json` không safelisted |
| `GET /me` có `Authorization: Bearer ...` | Có | Header `Authorization` không safelisted |
| `POST /orders` có `X-Request-Id` | Có | Header tùy biến không safelisted |
| `PUT /orders/42` | Có | `PUT` không safelisted |
| `DELETE /orders/42` | Có | `DELETE` không safelisted |
| `GET /me` với `credentials: "include"`, không thêm header ngoài safelist | Không, chỉ xét riêng điều kiện này | Yêu cầu gửi cookie **không tự động** kích hoạt preflight |

Các điều kiện trong bảng là các trường hợp phổ biến; Fetch còn có các điều kiện khác, chẳng hạn một số cách truyền body hoặc dùng sự kiện theo dõi tải lên. Quyết định thực tế thuộc về trình duyệt. Không dùng thuật ngữ “request đơn giản” để suy ra nó **an toàn**: `POST` dạng form vẫn có thể thay đổi trạng thái và liên quan tới **CSRF**.

**Lưu ý:** JavaScript không nên tự đặt header `Origin`. Đây là request header do trình duyệt quản lý. Cookie do trình duyệt gửi theo chính sách cookie cũng khác với header tùy biến mà script đặt.

## 3. Luồng A: actual request được gửi trực tiếp

Frontend cần đọc danh sách sản phẩm:

~~~javascript
const response = await fetch("https://api.example/products");

if (!response.ok) {
  throw new Error("API trả trạng thái HTTP " + response.status);
}

const products = await response.json();
console.log(products);
~~~

Vì đây là `GET` thông thường, không đặt header tùy biến, trình duyệt có thể gửi request trực tiếp:

~~~http
GET /products HTTP/1.1
Host: api.example
Origin: https://app.example
Accept: */*
~~~

Server xử lý và trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example
Vary: Origin

[{"id":1,"name":"Keyboard"}]
~~~

Trình duyệt đối chiếu `Origin` của trang gọi với `Access-Control-Allow-Origin` trong response. Khi hợp lệ, JavaScript nhận được đối tượng `Response` và đọc được JSON. `Vary: Origin` hữu ích khi server chọn origin được phép dựa trên header `Origin`: cache cần phân biệt các biến thể phản hồi.

Nếu server **không** trả header CORS phù hợp:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

[{"id":1,"name":"Keyboard"}]
~~~

Server **vẫn có thể đã xử lý thành công**. Nhưng trình duyệt không chia sẻ nội dung response cross-origin cho JavaScript. Khi đó `fetch` thường bị từ chối với lỗi liên quan CORS; mã JavaScript không nhận được `Response` để kiểm tra `response.status === 200`.

**Tại sao đây là điểm bảo mật quan trọng?** CORS là một cơ chế kiểm soát **quyền đọc response trong trình duyệt**. Không thể dùng việc “frontend không đọc được” làm bằng chứng rằng server không nhận request, hoặc biến CORS thành lớp kiểm soát truy cập thay cho xác thực/phân quyền.

## 4. Luồng B: trình duyệt gửi OPTIONS preflight trước

Frontend gửi JSON và bearer token:

~~~javascript
const response = await fetch("https://api.example/orders", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer <access-token>"
  },
  body: JSON.stringify({
    productId: 42,
    quantity: 2
  })
});

if (!response.ok) {
  throw new Error("Tạo đơn hàng không thành công: " + response.status);
}
~~~

Đây là cross-origin request có `Content-Type: application/json` và `Authorization`. Trước khi gửi `POST`, trình duyệt thường tự tạo **preflight OPTIONS**:

~~~http
OPTIONS /orders HTTP/1.1
Host: api.example
Origin: https://app.example
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization, content-type
~~~

Ý nghĩa từng trường:

| Thành phần | Ý nghĩa |
| --- | --- |
| `OPTIONS /orders` | Hỏi về chính đường dẫn mà request chính dự định truy cập |
| `Origin: https://app.example` | Origin của trang đang khởi tạo yêu cầu |
| `Access-Control-Request-Method: POST` | Phương thức của actual request sắp tới, **không phải** phương thức của preflight |
| `Access-Control-Request-Headers: authorization, content-type` | Các tên request header không safelisted mà JavaScript dự kiến dùng |

Thứ tự và cách viết hoa/thường tên header có thể khác; tên HTTP header không phân biệt hoa thường. Preflight không gửi body JSON cần tạo đơn hàng, và theo chuẩn CORS preflight không đính kèm cookie hay token xác thực của actual request. Vì thế một rule yêu cầu mọi `OPTIONS` phải xác thực bằng session/token thường làm preflight thất bại.

Server chấp nhận những gì được yêu cầu và phản hồi, ví dụ:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Đây là những quyền server khai báo:

- `Access-Control-Allow-Origin`: cho phép JavaScript từ origin này truy cập phản hồi nếu các kiểm tra khác hợp lệ.
- `Access-Control-Allow-Methods`: bao gồm `POST` mà request chính muốn sử dụng.
- `Access-Control-Allow-Headers`: bao gồm các request header `Authorization` và `Content-Type` mà frontend muốn gửi.
- `Access-Control-Max-Age: 600`: cho phép trình duyệt cache kết quả preflight tối đa theo giới hạn mà trình duyệt áp dụng.
- `Vary`: đánh dấu rằng phản hồi có thể phụ thuộc vào origin, method và headers được hỏi, hữu ích nếu qua cache trung gian.

Preflight thành công thường có HTTP status thuộc nhóm **2xx**, ví dụ `200 OK` hoặc `204 No Content`. Một mã 2xx **không đủ** nếu response thiếu hoặc khai báo sai header cho origin, method, headers. Ví dụ: `Access-Control-Allow-Methods: GET` không cho phép `POST`.

Sau đó trình duyệt mới gửi actual request:

~~~http
POST /orders HTTP/1.1
Host: api.example
Origin: https://app.example
Content-Type: application/json
Authorization: Bearer <access-token>

{"productId":42,"quantity":2}
~~~

Server xử lý API và trả phản hồi thực tế:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example
Vary: Origin

{"id":817,"status":"CREATED"}
~~~

**Actual response vẫn cần `Access-Control-Allow-Origin` hợp lệ.** Header `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers` ở preflight không tự động làm response của `POST` trở thành phản hồi mà JavaScript được đọc.

~~~mermaid
sequenceDiagram
    participant JS as JS trên app.example
    participant Browser as Trình duyệt
    participant API as API trên api.example
    JS->>Browser: fetch(POST JSON + Authorization)
    Browser->>API: OPTIONS /orders + Origin + Request-Method/Headers
    API-->>Browser: 204 + Allow-Origin/Methods/Headers
    alt Preflight hợp lệ
        Browser->>API: POST /orders + JSON + Authorization
        API-->>Browser: 201 + Allow-Origin + JSON
        alt Actual response có CORS hợp lệ
            Browser-->>JS: Response và dữ liệu
        else Actual response thiếu/sai CORS
            Browser-->>JS: Lỗi CORS, không đọc được response
        end
    else Preflight không hợp lệ
        Browser-->>JS: Lỗi CORS, không gửi POST
    end
~~~

## 5. Preflight bị từ chối thì điều gì xảy ra?

Ví dụ API hoặc security filter trả lời:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Hoặc một response status 204 nhưng thiếu quyền:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://other.example
Access-Control-Allow-Methods: GET
~~~

Trong cả hai trường hợp, preflight **không đạt kiểm tra CORS**. Trình duyệt không gửi `POST /orders` theo yêu cầu đã kích hoạt preflight. JavaScript nhận lỗi về giao tiếp CORS, thường không có quyền đọc nội dung chi tiết từ response OPTIONS.

Nhưng nếu preflight thành công và **request POST thực tế trả 401/403**, có hai khả năng cần tách biệt:

1. POST response **có CORS hợp lệ**: frontend nhận được HTTP status 401/403 để xử lý đăng nhập/quyền.
2. POST response **thiếu CORS hợp lệ**: frontend chỉ thấy lỗi CORS, dù lỗi gốc từ server là 401/403.

Trong Spring Security, đây là nguyên nhân phổ biến khiến frontend báo “CORS error” khi thực chất cấu hình authentication/authorization hoặc xử lý lỗi chưa đúng. Hãy kiểm tra request **nào** thất bại, status của nó và các response header ở từng bước.

| Vị trí lỗi | OPTIONS đã gửi? | Actual request đã gửi? | Điều JavaScript thường quan sát |
| --- | --- | --- | --- |
| GET trực tiếp, actual response thiếu CORS | Không | Có | Lỗi CORS |
| POST JSON, OPTIONS nhận 401 | Có | Không | Lỗi CORS khi preflight |
| POST JSON, OPTIONS trả 204 nhưng thiếu `Allow-Headers` phù hợp | Có | Không | Lỗi CORS khi preflight |
| POST JSON, OPTIONS hợp lệ, POST trả 403 kèm CORS hợp lệ | Có | Có | Có thể đọc `response.status === 403` |
| POST JSON, OPTIONS hợp lệ, POST trả 403 thiếu CORS | Có | Có | Lỗi CORS, khó biết 403 từ code frontend |

Trong nhiều môi trường, request OPTIONS không nhất thiết luôn xuất hiện trên mỗi lần gọi: kết quả preflight có thể đã được cache. Vì vậy “không nhìn thấy OPTIONS” **chưa đủ** để kết luận request không cần preflight.

## 6. Credentials làm thay đổi quy tắc đọc phản hồi, không tự tạo preflight

Xét request dùng session cookie:

~~~javascript
const response = await fetch("https://api.example/me", {
  credentials: "include"
});
~~~

Tùy cookie và chính sách trình duyệt, actual request có thể mang cookie. `credentials: "include"` **tự nó không phải** điều kiện bắt buộc preflight. Ví dụ `GET /me` không có header tùy biến có thể đi thẳng; nhưng server vẫn phải trả quyền CORS phù hợp với chế độ gửi credentials:

~~~http
Access-Control-Allow-Origin: https://app.example
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Đối với request sử dụng `credentials: "include"`, `Access-Control-Allow-Origin: *` không thể thay thế giá trị origin cụ thể để cho phép JavaScript đọc response. Preflight, nếu có, cũng phải khai báo quyền phù hợp với credentials mode của request thực tế.

**Phân biệt thêm:**

- `Authorization` được JavaScript chủ động đặt là một request header không safelisted, thường **kích hoạt preflight**, kể cả khi ứng dụng không sử dụng session cookie.
- `credentials: "include"` kiểm soát chính sách gửi/nhận credentials của Fetch; **không** có nghĩa JavaScript tự thêm header `Authorization`.
- Cookie còn phải đáp ứng domain/path, `SameSite`, `Secure` và chính sách cookie của trình duyệt. CORS thành công không bảo đảm cookie đã được gửi.
- `SameSite` đánh giá quan hệ **site**, còn CORS dùng **origin**. Hai subdomain khác origin có thể vẫn same-site.

Không trả `Access-Control-Allow-Credentials: true` cho mọi origin và không phản chiếu mọi giá trị `Origin` đầu vào một cách vô điều kiện. Chỉ cấp phép các origin thực sự được tin cậy đọc response trong bối cảnh người dùng đã xác thực.

## 7. Bộ nhớ cache của preflight và gateway

`Access-Control-Max-Age` gợi ý thời gian cache quyết định preflight, tính theo giây:

~~~http
Access-Control-Max-Age: 600
~~~

Trình duyệt có thể tái sử dụng quyền đã kiểm tra cho các request phù hợp trong thời gian được phép, chịu các giới hạn và cách phân vùng cache riêng của trình duyệt. Cache của preflight **khác** cache HTTP thông thường đối với response dữ liệu API.

Hệ quả khi chẩn đoán:

- Lần gọi đầu xuất hiện `OPTIONS` và `POST`, lần sau có thể chỉ thấy `POST`.
- Sửa CORS ở server rồi gọi lại có thể vẫn chịu ảnh hưởng của preflight đã cache; hãy thử môi trường/phiên mới hoặc chờ cache hết hiệu lực khi cần kiểm chứng.
- Reverse proxy/API gateway phải cho phép route `OPTIONS` đến thành phần xử lý CORS; nếu proxy chặn 404/405/301 không phù hợp, backend phía sau có cấu hình đúng vẫn chưa chắc giúp trình duyệt gọi được.
- Nếu response preflight khác nhau theo `Origin`, `Access-Control-Request-Method` hoặc `Access-Control-Request-Headers`, hãy cấu hình `Vary` tương ứng khi đi qua cache HTTP có khả năng lưu biến thể.
- Tránh hai tầng cùng chèn `Access-Control-Allow-Origin` với giá trị không nhất quán; phản hồi chứa nhiều giá trị origin có thể bị trình duyệt từ chối.

Không dựa vào cache preflight để thay thế xác thực/phân quyền: mỗi **actual request** vẫn phải được kiểm tra theo chính sách bảo mật của API.

## 8. Cấu hình Spring Security Servlet cho cả preflight lẫn actual request

Với ứng dụng Spring MVC + Spring Security, nên khai báo chính sách CORS nhất quán và tích hợp qua `http.cors(...)`. Ví dụ minh họa một API cho frontend `https://app.example`:

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
        http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());
        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of("Content-Type", "Authorization"));
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }
}
~~~

Điểm cốt lõi:

1. `http.cors(Customizer.withDefaults())` để Spring Security tích hợp xử lý CORS đúng vị trí trong chuỗi filter.
2. Quy tắc `allowedOrigins`, `allowedMethods`, `allowedHeaders` phải khớp **Origin / Access-Control-Request-Method / Access-Control-Request-Headers** của request.
3. Preflight đến route `/orders` cần được xử lý trước khi cơ chế xác thực của API yêu cầu token từ request. Việc chỉ dùng `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` chưa chắc đủ: response vẫn phải có header CORS hợp lệ.
4. Actual request `POST` vẫn đi qua authentication, authorization và (nếu áp dụng) CSRF protection. Ví dụ trên **chưa cấu hình phương thức xác thực hay endpoint**, nên chỉ minh họa chính sách CORS.

Ví dụ trên không bật `allowCredentials`. Nếu ứng dụng **thực sự cần** dùng `credentials: "include"` và session cookie, có thể thêm `cors.setAllowCredentials(true)`, giữ `allowedOrigins` là danh sách origin cụ thể và thiết kế đầy đủ session/cookie/CSRF. Không dùng wildcard origin `*` cùng chế độ này.

Nếu CORS được khai báo ở Spring MVC bằng `@CrossOrigin` hoặc `WebMvcConfigurer`, cần kiểm tra cơ chế mà Spring Security đang sử dụng; tránh đặt các luật khác nhau trên MVC, Security filter và gateway.

## 9. Tương đương trong Spring Security Reactive / WebFlux

Trên WebFlux, dùng thành phần thuộc nhánh **reactive** thay cho `CorsFilter` và `UrlBasedCorsConfigurationSource` của Servlet. Ví dụ tích hợp chính sách CORS trực tiếp vào `ServerHttpSecurity` để xử lý preflight trong chuỗi bảo mật:

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
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of("Content-Type", "Authorization"));
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);

        return http
            .cors(spec -> spec.configurationSource(source))
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated())
            .build();
    }
}
~~~

Với Spring Security WebFlux, cần đảm bảo CORS được xử lý **trước các kiểm tra bảo mật chặn preflight** trong `SecurityWebFilterChain`. Một phương án khác là đăng ký `CorsWebFilter` với thứ tự thực thi phù hợp; không đồng thời cấu hình hai bộ xử lý CORS mâu thuẫn. Cấu hình authentication, authorization và CSRF cho actual request vẫn là trách nhiệm riêng; ví dụ chưa triển khai các cơ chế đó.

Nếu hệ thống có gateway hoặc load balancer, kiểm tra luồng OPTIONS đi qua mọi tầng, không chỉ handler ở service cuối.

## 10. Kiểm thử có hệ thống

### 10.1. Quan sát trình duyệt

Từ trang đang chạy thật ở `https://app.example`:

1. Mở DevTools → **Network**; bật hiển thị request OPTIONS nếu trình duyệt có bộ lọc liên quan.
2. Thực hiện một lệnh `GET` safelisted và một lệnh `POST` JSON.
3. Với `POST`, tìm request `OPTIONS` tương ứng (nếu không có, xem khả năng cache preflight).
4. Đọc `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` trên OPTIONS; so sánh với `Access-Control-Allow-*` trên preflight response.
5. Xác định request POST thực tế **có xuất hiện hay không**, rồi kiểm tra response CORS của POST.
6. Đối chiếu thông báo **Console** với kết quả **Network**. Console thường chỉ nêu lỗi CORS tổng quát; Network giúp nhận ra 401, 403, 404, 405 hoặc header sai.

Ví dụ kiểm tra chủ động:

~~~javascript
// Thường không cần preflight.
await fetch("https://api.example/products");

// Thường cần preflight do Content-Type application/json.
await fetch("https://api.example/orders", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ productId: 42 })
});
~~~

### 10.2. Kiểm tra header bằng curl

Có thể mô phỏng một request thực tế:

~~~bash
curl -i "https://api.example/products" \
  -H "Origin: https://app.example"
~~~

Và một preflight:

~~~bash
curl -i -X OPTIONS "https://api.example/orders" \
  -H "Origin: https://app.example" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization, content-type"
~~~

Các domain ở đây chỉ là **ví dụ minh họa**: thay bằng hostname API thật trước khi chạy. Trong Windows PowerShell cũ, có thể dùng `curl.exe` thay cho `curl` để tránh bí danh của `Invoke-WebRequest`.

Đối chiếu response với các điều kiện:

| Câu hỏi | Điều cần xác nhận |
| --- | --- |
| Response preflight có status hợp lệ? | Status 2xx |
| Origin có được cho phép? | `Access-Control-Allow-Origin` khớp request (theo credentials mode) |
| Method định dùng có được cho phép? | `Access-Control-Allow-Methods` cho phép `POST` |
| Các header định gửi có được cho phép? | `Access-Control-Allow-Headers` cho phép `authorization` và `content-type` |
| Nếu request dùng credentials? | Origin cụ thể và `Access-Control-Allow-Credentials: true` khi cần |
| Actual response có thể đọc? | Chính response thực tế có header CORS phù hợp |
| API còn an toàn? | Actual request vẫn kiểm tra token/session, authorization và CSRF theo thiết kế |

`curl` giúp kiểm tra HTTP response của server nhưng **không thực thi chính sách SOP/CORS như trình duyệt**. `curl` nhận được nội dung không chứng minh frontend sẽ được phép đọc nội dung đó.

### 10.3. Những lỗi hay gặp

| Hiện tượng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `OPTIONS /orders` trả 401/403 | Authentication/CSRF/filter xử lý OPTIONS trước CORS | Đưa xử lý CORS vào đúng thứ tự filter; kiểm tra cấu hình Spring Security |
| `OPTIONS /orders` trả 404/405 | Proxy/router không hỗ trợ OPTIONS tại route | Kiểm tra gateway và mapping xử lý preflight |
| OPTIONS 204 nhưng console vẫn báo lỗi | Thiếu `Allow-Origin`, `Allow-Methods` hoặc `Allow-Headers` phù hợp | So sánh từng header request/response |
| OPTIONS đạt, POST 200 nhưng frontend báo CORS | POST response thiếu `Access-Control-Allow-Origin` | Bổ sung CORS cho actual response, kể cả response lỗi |
| Chỉ request có `Authorization` thất bại | Chưa cho phép request header `Authorization` | Kiểm tra `Access-Control-Request-Headers` và `Access-Control-Allow-Headers` |
| Cookie không được gửi | `credentials`, cookie `SameSite`/`Secure`/domain/path hoặc chính sách trình duyệt | Kiểm tra tab Cookies và request thực tế |
| Khác giữa chạy trực tiếp và qua proxy | Origin/port thay đổi, proxy sửa/xóa/chèn header hoặc chặn OPTIONS | So sánh toàn bộ chuỗi HTTP hai môi trường |
| `mode: "no-cors"` làm hết lỗi Console nhưng không đọc được JSON | Response trở thành *opaque* và không truy cập được body/status như mong muốn | Cấu hình CORS đúng ở server; không dùng `no-cors` để thay thế quyền đọc |

## 11. Không nhầm preflight với các lớp bảo mật khác

Trong Spring Security, tách bạch những quyết định sau:

- **CORS preflight:** browser có được gửi actual request với method/header dự kiến hay không?
- **CORS actual response:** JavaScript ở origin gọi có được đọc kết quả không?
- **Authentication:** request thực tế đại diện cho người dùng/client nào?
- **Authorization:** người dùng/client có được thao tác tài nguyên này không?
- **CSRF protection:** request có nguy cơ thực hiện thao tác ngoài ý muốn thông qua cookie phiên có được kiểm tra hợp lệ không?
- **CSP `connect-src`:** trang có được phép mở kết nối tới API này theo chính sách của chính trang không?

**CORS không phải lớp chặn request giả mạo hoặc thay thế CSRF.** Một request cross-site dạng form có thể tới server mà không cần preflight; nếu nó gây thay đổi dữ liệu và có cookie hợp lệ, việc JavaScript không đọc được response không xóa được tác động đã xảy ra.

Vì thế, trong mọi sơ đồ triển khai Servlet/Reactive, hãy cấu hình CORS để browser hoạt động đúng, đồng thời duy trì xác thực, phân quyền, CSRF và các cơ chế session/security headers theo mô hình rủi ro của hệ thống.

## 12. Bài tập đọc luồng

**Tình huống 1.** Trang `https://app.example` gọi `GET https://api.example/products` không thêm header tùy biến. API trả 200 nhưng thiếu `Access-Control-Allow-Origin`. Có OPTIONS không? JavaScript đọc được JSON không?

**Đáp án:** Thường không có OPTIONS. Actual GET vẫn có thể đã chạy và trả 200. Trình duyệt chặn JavaScript đọc JSON vì actual response thiếu quyền CORS.

**Tình huống 2.** Trang gửi `POST` JSON kèm header `Authorization`. Preflight trả `204`, `Access-Control-Allow-Origin: https://app.example`, `Access-Control-Allow-Methods: POST` nhưng không trả `Access-Control-Allow-Headers`. POST có được gửi không?

**Đáp án:** Không. Preflight không cho phép các request header cần dùng, nên trình duyệt không gửi actual POST.

**Tình huống 3.** OPTIONS thành công, POST thực tế trả `403 Forbidden` cùng `Access-Control-Allow-Origin: https://app.example` hợp lệ. Frontend có thể phân biệt lỗi phân quyền với lỗi CORS không?

**Đáp án:** Có, nếu các điều kiện CORS của response thực tế đều đạt, frontend nhận `Response` với `status === 403`. CORS không thay đổi kết quả phân quyền.

**Tình huống 4.** Một GET dùng `credentials: "include"` nhưng không thêm header tùy biến. Có bắt buộc gửi preflight không? Response `Access-Control-Allow-Origin: *` có dùng được không?

**Đáp án:** Chỉ bật `credentials: "include"` không tự làm GET cần preflight. Nhưng nếu server trả wildcard `*`, browser không chia sẻ response cho JavaScript dưới credentials mode này; cần origin cụ thể được tin cậy và `Access-Control-Allow-Credentials: true`.

**Tình huống 5.** API có thể nhận POST dạng form cross-origin mà không cần preflight. Có thể tắt CSRF vì CORS không cho trang lạ đọc phản hồi không?

**Đáp án:** Không. Request thay đổi trạng thái có thể được gửi và xử lý dù trang nguồn không đọc được response. CSRF protection và chính sách cookie vẫn cần được xem xét độc lập.

---

**Ghi nhớ:** Với request CORS, hãy đặt đúng hai câu hỏi theo thứ tự: **(1) Có cần OPTIONS để được phép gửi request chính không? (2) Response của request chính có cho phép JavaScript đọc không?** Muốn chẩn đoán chính xác, phải quan sát riêng preflight, actual request và từng response, rồi kiểm tra thứ tự CORS filter trong Spring Security cùng authentication, authorization và CSRF.
