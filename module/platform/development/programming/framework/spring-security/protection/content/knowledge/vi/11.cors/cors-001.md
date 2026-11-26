# CORS giải quyết quyền đọc phản hồi khác nguồn như thế nào

## 1. Bài toán: trình duyệt phải quyết định ai được đọc dữ liệu

Giả sử người dùng đang đăng nhập vào `https://bank.example` và đồng thời mở một trang ở `https://evil.example`. Trang thứ hai có thể chạy JavaScript trong trình duyệt của cùng người dùng. Nếu script từ trang bất kỳ được tự do đọc phản hồi HTTP của `https://bank.example`, nó có thể lấy thông tin tài khoản mà người dùng đang có quyền truy cập.

**Same-Origin Policy (SOP)** là ranh giới an toàn mặc định của trình duyệt: JavaScript từ một *origin* thường không được đọc tùy ý nội dung phản hồi thuộc origin khác. **Cross-Origin Resource Sharing (CORS)** là giao thức phối hợp giữa trình duyệt và máy chủ để tạo **ngoại lệ có kiểm soát** cho ranh giới đó.

Ví dụ ứng dụng hợp lệ:

- Frontend: `https://app.example`.
- API Spring Boot: `https://api.example`.
- Frontend gọi `fetch("https://api.example/products")` để hiển thị danh sách sản phẩm.

Hai dịch vụ là **khác origin**, dù đều thuộc `example`. API có thể chủ động cho phép JavaScript của frontend đọc phản hồi bằng cách trả các HTTP header CORS phù hợp.

> Ý chính: CORS quyết định **trình duyệt có trao nội dung phản hồi cho JavaScript ở origin gọi hay không**. CORS không tự xác thực người dùng, phân quyền tài nguyên, hay ngăn mọi yêu cầu HTTP đi tới máy chủ.

### Origin được xác định thế nào?

Một *origin* gồm **scheme (giao thức) + host + port**. Đổi bất kỳ thành phần nào cũng tạo origin khác. Đường dẫn URL không tham gia xác định origin.

| URL được gọi từ trang `https://app.example` | Cùng origin? | Lý do |
| --- | --- | --- |
| `https://app.example/profile` | Có | Cùng scheme, host và port mặc định 443 |
| `https://app.example:443/profile` | Có | Port 443 là port mặc định của HTTPS |
| `http://app.example/profile` | Không | Khác scheme |
| `https://api.example/profile` | Không | Khác host |
| `https://app.example:8443/profile` | Không | Khác port |

**Origin khác site:** `https://app.example` và `https://api.example` thường là *same-site* nhưng vẫn *cross-origin*. Phân biệt này quan trọng khi xét cookie `SameSite`: quy tắc cookie và quy tắc CORS là hai cơ chế riêng.

## 2. CORS kiểm soát điều gì và không kiểm soát điều gì?

Một trang thường có thể **khởi tạo** nhiều tương tác khác origin (chẳng hạn tải ảnh, gửi form HTML hoặc thực hiện một số yêu cầu `fetch`). Tuy vậy, SOP hạn chế khả năng **đọc** phản hồi từ JavaScript. Một số dạng tài nguyên như ảnh, script, stylesheet có quy tắc nhúng riêng; việc chúng tải được không đồng nghĩa JavaScript được đọc mọi byte của chúng.

Có hai câu hỏi phải tách biệt:

1. **Yêu cầu có được gửi lên máy chủ hay không?** Tùy loại yêu cầu và quy tắc preflight; nhiều yêu cầu vẫn được gửi dù JavaScript sau đó không đọc được phản hồi.
2. **JavaScript có đọc được status, body và header phản hồi hay không?** Trình duyệt xét CORS và chỉ cung cấp những gì được phép.

Ví dụ: API xử lý xong `GET /balance` và trả HTTP 200, nhưng không có `Access-Control-Allow-Origin` phù hợp. Trong DevTools có thể thấy yêu cầu và phản hồi mạng, còn `fetch` phía JavaScript báo lỗi CORS, không được nhận body để xử lý.

CORS **không** là tường lửa ở máy chủ: `curl`, Postman hoặc một backend gọi backend khác không tự động áp dụng SOP như trình duyệt. Không nên dựa vào CORS để chặn client giả mạo, chống CSRF hay bảo vệ API khỏi truy cập trái phép.

## 3. Luồng cơ bản: máy chủ cho phép origin đọc phản hồi

Với yêu cầu `GET` thông thường, trình duyệt có thể gửi trực tiếp yêu cầu cross-origin kèm header `Origin`:

~~~http
GET /products HTTP/1.1
Host: api.example
Origin: https://app.example
Accept: application/json
~~~

Máy chủ kiểm tra origin đó có trong danh sách được phép hay không. Nếu có, nó trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example
Vary: Origin

[{"id":1,"name":"Keyboard"}]
~~~

Trình duyệt đối chiếu `Origin` với `Access-Control-Allow-Origin`. Vì giá trị khớp, JavaScript của `https://app.example` có thể đọc phản hồi:

~~~javascript
const response = await fetch("https://api.example/products");
const products = await response.json();
console.log(products);
~~~

Nếu server trả `Access-Control-Allow-Origin: https://admin.example` hoặc không trả header này, trình duyệt chặn JavaScript đọc phản hồi. **Máy chủ vẫn có thể đã nhận, xử lý và trả yêu cầu thành công.**

~~~mermaid
sequenceDiagram
    participant JS as JavaScript tại app.example
    participant Browser as Trình duyệt
    participant API as API tại api.example
    JS->>Browser: fetch("/products" trên api.example)
    Browser->>API: GET /products + Origin: https://app.example
    API-->>Browser: 200 + Access-Control-Allow-Origin
    alt Origin được cho phép
        Browser-->>JS: Cung cấp status, body, header được phép đọc
    else Thiếu hoặc sai quyền CORS
        Browser-->>JS: Lỗi CORS / fetch bị từ chối
    end
~~~

`Access-Control-Allow-Origin: *` có nghĩa máy chủ cho phép mọi origin đọc phản hồi trong trường hợp yêu cầu **không sử dụng chế độ credentials cross-origin**. Dấu `*` không dùng để cấp quyền cho yêu cầu `fetch` có `credentials: "include"`.

Header `Vary: Origin` cần thiết khi server chọn giá trị `Access-Control-Allow-Origin` dựa trên `Origin` của từng request: cache trung gian phải biết phản hồi phụ thuộc origin để không tái sử dụng nhầm biến thể.

## 4. Khi nào trình duyệt gửi preflight OPTIONS?

Một số yêu cầu cross-origin cần kiểm tra quyền **trước khi gửi yêu cầu chính**. Trình duyệt tự gửi một request *preflight* bằng phương thức `OPTIONS`. Thông thường các yêu cầu dùng phương thức ngoài `GET`, `HEAD`, `POST` được cho phép đơn giản, hoặc dùng header không thuộc danh sách safelisted, sẽ cần preflight.

Các ví dụ hay gặp:

- `POST` với `Content-Type: application/json`.
- Request có header `Authorization` hoặc `X-Request-Id` do JavaScript đặt.
- `PUT` hoặc `DELETE`.

Một request `GET` hoặc `POST` **không mặc nhiên** cần preflight; điều này còn phụ thuộc phương thức, header và `Content-Type`. Trong các điều kiện liên quan, những `Content-Type` safelisted là `application/x-www-form-urlencoded`, `multipart/form-data` và `text/plain`.

Giả sử frontend định gọi:

~~~javascript
await fetch("https://api.example/orders", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer <access-token>"
  },
  body: JSON.stringify({ productId: 1, quantity: 2 })
});
~~~

Trước tiên, trình duyệt hỏi API:

~~~http
OPTIONS /orders HTTP/1.1
Host: api.example
Origin: https://app.example
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization, content-type
~~~

API có thể trả:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Max-Age: 600
Vary: Origin
~~~

Nếu quyền hợp lệ, trình duyệt mới gửi `POST /orders` thực tế. **Phản hồi của POST thực tế vẫn cần header CORS phù hợp** để JavaScript đọc được; thành công ở OPTIONS không thay thế quyền đọc phản hồi cuối cùng.

Nếu preflight bị từ chối (thiếu quyền cho origin, method hoặc header), trình duyệt **không gửi request chính** theo luồng này. Nếu yêu cầu không cần preflight, trình duyệt có thể gửi request chính rồi mới quyết định không cho JavaScript đọc phản hồi.

`Access-Control-Max-Age` cho phép trình duyệt cache kết quả preflight trong giới hạn riêng của trình duyệt. Vì vậy không nên mặc định mỗi lần gọi API đều có một `OPTIONS` mới.

## 5. Các header CORS cần hiểu đúng vai trò

| Header | Xuất hiện ở đâu | Vai trò |
| --- | --- | --- |
| `Origin` | Request thực tế và preflight | Khai báo origin của ngữ cảnh gọi |
| `Access-Control-Allow-Origin` | Response | Origin được phép đọc, hoặc `*` khi hợp lệ |
| `Access-Control-Request-Method` | Preflight request | Hỏi server có cho phép method sắp dùng không |
| `Access-Control-Request-Headers` | Preflight request | Hỏi server có cho phép các request header sắp dùng không |
| `Access-Control-Allow-Methods` | Preflight response | Liệt kê method được phép cho request chính |
| `Access-Control-Allow-Headers` | Preflight response | Liệt kê request header được phép sử dụng |
| `Access-Control-Allow-Credentials` | Response CORS khi cần credentials | Cho phép trình duyệt chia sẻ phản hồi của request dùng credentials |
| `Access-Control-Max-Age` | Preflight response | Gợi ý thời gian cache kết quả preflight |
| `Access-Control-Expose-Headers` | Response thực tế | Cho phép JavaScript đọc thêm response header ngoài nhóm mặc định |
| `Vary: Origin` | Response phụ thuộc origin | Giúp cache tách các biến thể theo header Origin |

Cần phân biệt **cho phép gửi request header** và **cho phép đọc response header**:

- `Access-Control-Allow-Headers: Authorization` là quyền cho frontend **gửi** header `Authorization` trong request chính; nó không có nghĩa frontend được đọc mọi header phản hồi.
- `Access-Control-Expose-Headers: X-Request-Id` là quyền cho frontend **đọc** response header `X-Request-Id` qua `response.headers.get("X-Request-Id")`. Một số response header thông dụng như `Content-Type` vốn đã được CORS safelist cho phép đọc.
- `Set-Cookie` là response header bị chặn đối với JavaScript; khai báo `Access-Control-Expose-Headers` không khiến `fetch` đọc được `Set-Cookie`.

Lưu ý: tên HTTP header không phân biệt hoa thường, nhưng trong ví dụ các giá trị origin phải đại diện đúng origin muốn cấp phép. `Access-Control-Allow-Origin` không nhận danh sách phân tách bằng dấu phẩy như một cơ chế cho nhiều origin; máy chủ thường chọn một origin hợp lệ để trả về cho request tương ứng.

## 6. Quyền đọc khi gửi cookie hoặc credentials

Giả sử frontend muốn đọc thông tin hồ sơ từ API và gửi kèm cookie phù hợp:

~~~javascript
const response = await fetch("https://api.example/me", {
  credentials: "include"
});
const profile = await response.json();
~~~

Để trình duyệt cung cấp phản hồi cho JavaScript, API cần đáp ứng tối thiểu các header tương ứng:

~~~http
Access-Control-Allow-Origin: https://app.example
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Hai sai lầm phổ biến:

1. Dùng `Access-Control-Allow-Origin: *` với `credentials: "include"`. Trình duyệt không chấp nhận kết hợp này để chia sẻ phản hồi.
2. Tưởng `Access-Control-Allow-Credentials: true` sẽ khiến cookie tự động được gửi. Thực tế, việc gửi và lưu cookie còn phụ thuộc `credentials` của Fetch, thuộc tính cookie, quy tắc `SameSite`/`Secure` và chính sách cookie của trình duyệt.

Với yêu cầu **cross-site** thật sự cần cookie, cookie thường phải có `SameSite=None; Secure` (và vẫn có thể chịu hạn chế cookie bên thứ ba). Cross-origin **không nhất thiết** là cross-site, nên không thể suy ra yêu cầu `SameSite=None` chỉ từ việc khác subdomain.

Hãy cấu hình danh sách origin được tin cậy rõ ràng. Không nên đơn giản phản chiếu mọi giá trị `Origin` bất kỳ rồi đồng thời bật `Access-Control-Allow-Credentials: true`: cách đó có thể cho trang không tin cậy đọc dữ liệu nhạy cảm qua trình duyệt của người dùng đã đăng nhập.

## 7. CORS, xác thực, CSRF và các lớp phòng vệ khác

Trong Spring Security, CORS nằm cạnh các lớp phòng vệ HTTP như CSRF, session, security headers và CSP, nhưng mỗi cơ chế giải quyết **một câu hỏi khác nhau**:

| Cơ chế | Câu hỏi bảo mật chính |
| --- | --- |
| CORS | JavaScript ở origin khác có được **đọc phản hồi** hay không? |
| Authentication | Request này đại diện cho ai? |
| Authorization | Danh tính đó có được truy cập tài nguyên hoặc thao tác này không? |
| CSRF protection | Request thay đổi trạng thái có thực sự xuất phát từ tương tác hợp lệ của người dùng không? |
| Cookie `SameSite` | Cookie có được gửi trong ngữ cảnh same-site/cross-site tương ứng không? |
| CSP `connect-src` | JavaScript từ chính trang này được phép mở kết nối đến các đích nào? |

Một form cross-site có thể kích hoạt thao tác thay đổi dữ liệu trong một số điều kiện, dù trang nguồn không thể đọc phản hồi do SOP/CORS. Vì vậy **CORS không thay thế chống CSRF**, đặc biệt với ứng dụng xác thực bằng session cookie. Ngược lại, API yêu cầu bearer token vẫn phải xác thực và phân quyền token cho từng request, dù origin được CORS cho phép.

Mỗi origin được allow là một nơi JavaScript có thể đọc dữ liệu mà quyền xác thực hiện tại cho phép. Hãy coi allowlist là quyết định tin cậy, rà soát kỹ khi mở quyền đối với endpoint trả thông tin riêng tư.

## 8. Liên hệ Spring Security Servlet và Reactive

Ở ứng dụng Spring Security, quy tắc CORS cần được xử lý đủ sớm để preflight `OPTIONS` không bị filter xác thực từ chối khi request preflight không mang thông tin đăng nhập thông thường.

Với ứng dụng **Servlet / Spring MVC**, một cấu hình minh họa:

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
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example"));
        config.setAllowedMethods(List.of("GET", "POST"));
        config.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        config.setExposedHeaders(List.of("X-Request-Id"));
        config.setAllowCredentials(true);
        config.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
~~~

Đây là ví dụ cấu hình quyền CORS cho `/api/**`, **không phải cấu hình xác thực hoàn chỉnh**. Cần cấu hình cơ chế đăng nhập/token, CSRF và quyền endpoint phù hợp với kiểu ứng dụng. `setAllowedOrigins` là allowlist origin tin cậy; method/header ở đây là ví dụ chứ không phải bộ giá trị bắt buộc cho mọi API. Chỉ đặt `setAllowCredentials(true)` khi luồng thực sự cần.

Với **Reactive / Spring WebFlux**, mục tiêu cũng giống nhau: cấu hình CORS trong pipeline WebFlux/Spring Security WebFlux để xử lý preflight và gắn header vào phản hồi thực tế. Tuy nhiên phải dùng các API reactive tương ứng (chẳng hạn `CorsWebFilter` và lớp `UrlBasedCorsConfigurationSource` thuộc gói reactive), không đem nguyên filter Servlet vào chuỗi `SecurityWebFilterChain`.

Trong cả hai nền tảng, cần tránh khai báo CORS chồng chéo không nhất quán ở controller, filter bảo mật, gateway và reverse proxy: header trả về có thể bị thiếu hoặc lặp, khiến trình duyệt từ chối.

## 9. Đọc lỗi CORS theo tình huống thực tế

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xác minh |
| --- | --- | --- |
| API trả 200 nhưng `fetch` báo lỗi CORS | Response thiếu/sai `Access-Control-Allow-Origin` | DevTools → Network → request thực tế → Response Headers |
| Chỉ request `POST application/json` hoặc dùng `Authorization` bị lỗi | Preflight `OPTIONS` bị 401/403, thiếu method/header cho phép | Xem request OPTIONS, `Access-Control-Request-*` và response header |
| Gửi `credentials: "include"` nhưng JS không đọc được response | Server trả `Access-Control-Allow-Origin: *` hoặc thiếu `Access-Control-Allow-Credentials: true` | Kiểm tra response thực tế; với preflight có thể cần kiểm tra cả preflight |
| CORS qua được nhưng server không nhận cookie | Cookie `SameSite`/`Secure`, Fetch credentials, chính sách cookie, domain/path | Xem Request Headers và tab Cookies của DevTools |
| `response.headers.get("X-Request-Id")` trả null | Chưa expose response header tùy biến | Kiểm tra `Access-Control-Expose-Headers` |
| Chỉ một số origin hoặc môi trường bị lỗi ngẫu nhiên | Allowlist sai, cache thiếu `Vary: Origin`, proxy sửa header | So sánh Origin, response headers và lớp gateway |
| JS không đọc được nội dung lỗi 401/403/500 | Response lỗi không mang CORS header thích hợp | Kiểm tra response của chính request thất bại |

Có thể kiểm tra phản hồi server bằng dòng lệnh:

~~~bash
curl -i -H "Origin: https://app.example" https://api.example/products
~~~

Và mô phỏng preflight:

~~~bash
curl -i -X OPTIONS https://api.example/orders \
  -H "Origin: https://app.example" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization, content-type"
~~~

Lệnh `curl` hữu ích để thấy server trả header gì, nhưng `curl` **không thực thi chính sách CORS của trình duyệt**. Muốn xác nhận JavaScript được đọc phản hồi, hãy thử từ đúng origin trong trình duyệt và xem DevTools Console/Network. Dấu `Origin` có thể được giả lập bằng client khác; server không được coi riêng header đó là bằng chứng xác thực người dùng.

## 10. Tự kiểm tra hiểu biết

**Tình huống A.** Frontend `https://shop.example` gọi `https://api.example/catalog` bằng `GET`. API xử lý thành công và trả JSON, nhưng không có `Access-Control-Allow-Origin`. JavaScript có đọc JSON không?

**Trả lời:** Không. Yêu cầu mạng có thể đã thành công; trình duyệt không cấp quyền đọc response cross-origin cho JavaScript.

**Tình huống B.** Frontend gửi `POST` JSON với `Authorization`. Server cho phép origin ở response POST nhưng từ chối `OPTIONS` bằng 401. POST có được trình duyệt gửi không?

**Trả lời:** Thông thường không. Trình duyệt cần preflight thành công trước khi gửi request chính trong trường hợp này. Cần cấu hình xử lý CORS trước khâu xác thực preflight và cho phép method/header phù hợp.

**Tình huống C.** API có `Access-Control-Allow-Origin: *` và frontend dùng `credentials: "include"`. Thêm `Access-Control-Allow-Credentials: true` có đủ không?

**Trả lời:** Không. Response dùng credentials cần `Access-Control-Allow-Origin` chỉ rõ origin được tin cậy, cùng `Access-Control-Allow-Credentials: true`. Cookie thực tế còn phải được trình duyệt chấp nhận theo quy tắc riêng.

---

**Ghi nhớ:** CORS là cơ chế **máy chủ khai báo quyền, trình duyệt thực thi quyền đọc phản hồi khác origin**. Cần phân biệt request thực tế với preflight, cho phép gửi header với cho phép đọc header, và quyền CORS với xác thực, phân quyền, CSRF cùng chính sách cookie.
