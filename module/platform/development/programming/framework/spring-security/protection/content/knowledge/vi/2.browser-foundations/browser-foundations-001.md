# Origin gồm scheme, host và port

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Xác định origin của một URL bằng ba thành phần **scheme, host và port**; nhận ra thành phần nào của URL không làm thay đổi origin.
- Phân biệt **same-origin**, **cross-origin** và **same-site** qua các tình huống thực tế.
- Giải thích vì sao **Same-Origin Policy (SOP)**, **CORS**, **CSRF** và cookie có liên quan nhưng giải quyết các vấn đề khác nhau.
- Áp dụng cách hiểu về origin để cấu hình CORS trong Spring Security (Servlet và Reactive), đọc yêu cầu preflight và xử lý lỗi trong trình duyệt.

## 1. Origin là gì?

Đối với các URL HTTP/HTTPS thông thường, **origin** là bộ ba:

**Origin = (scheme, host, port)**

Xét địa chỉ:

~~~text
https://shop.example.com:8443/orders/42?view=full#payment
└─┬─┘   └──────┬──────┘ └┬─┘└────────────┬──────────────┘
scheme        host       port      path, query, fragment
~~~

| Thành phần | Giá trị trong ví dụ | Ý nghĩa đối với origin |
| --- | --- | --- |
| **Scheme** | https | Giao thức hoặc lược đồ URL; http và https tạo ra hai origin khác nhau. |
| **Host** | shop.example.com | Tên miền hoặc địa chỉ IP mà URL hướng tới. |
| **Port** | 8443 | Cổng của dịch vụ; khác cổng nghĩa là khác origin. |
| Path | /orders/42 | Không tham gia xác định origin. |
| Query | view=full | Không tham gia xác định origin. |
| Fragment | payment | Không tham gia xác định origin; fragment cũng không được gửi trong yêu cầu HTTP. |

Vì vậy, origin của URL trên là **https://shop.example.com:8443**. Hai tài nguyên ở các đường dẫn khác nhau vẫn có thể thuộc cùng origin.

### Cổng mặc định và chuẩn hóa

Với HTTP, cổng mặc định là **80**; với HTTPS, cổng mặc định là **443**. Trình duyệt chuẩn hóa cổng mặc định khi xác định và biểu diễn origin:

~~~text
http://example.com           ≡ http://example.com:80
https://example.com          ≡ https://example.com:443
https://example.com:8443     ≠ https://example.com
~~~

Tên host trong URL HTTP/HTTPS không phân biệt chữ hoa/chữ thường sau khi chuẩn hóa: **APP.example.com** và **app.example.com** là cùng host. Tuy nhiên, **localhost**, **127.0.0.1** và **[::1]** vẫn là các host khác nhau, dù có thể cùng trỏ về máy của bạn. Không nên suy ra same-origin chỉ vì hai tên miền cùng trỏ đến một địa chỉ IP.

Trong JavaScript chạy trong trình duyệt, có thể quan sát origin như sau:

~~~javascript
console.log(window.location.origin);
// Ví dụ: "https://shop.example.com:8443"

console.log(new URL("https://api.example.com/v1/users").origin);
// "https://api.example.com"

console.log(new URL("https://example.com:443/a").origin);
// "https://example.com": cổng HTTPS mặc định được lược bỏ
~~~

**Lưu ý phạm vi:** Công thức ba thành phần là mô hình phù hợp với HTTP/HTTPS thông thường. Các trường hợp như URL data:, tài liệu trong iframe có sandbox đặc biệt, hoặc một số ngữ cảnh file: có thể có **opaque origin** (origin không thể biểu diễn bằng bộ ba HTTP/HTTPS quen thuộc). Không được coi mọi chuỗi URL đều có origin có thể so sánh đơn giản bằng cách cắt văn bản.

## 2. Khi nào hai URL cùng origin?

Giả sử trang hiện tại được tải từ:

**https://app.example.com:443/dashboard**

| URL được truy cập | Same-origin? | Lý do |
| --- | --- | --- |
| https://app.example.com/profile | **Có** | Cùng scheme, host và cổng HTTPS mặc định; path khác không ảnh hưởng. |
| https://APP.example.com:443/api/me | **Có** | Host không phân biệt hoa/thường; port vẫn là 443. |
| https://app.example.com:8443/profile | **Không** | Port 8443 khác port 443. |
| http://app.example.com/profile | **Không** | Scheme http khác https. |
| https://api.example.com/profile | **Không** | Subdomain khác nghĩa là host khác. |
| https://example.com/profile | **Không** | Host gốc khác app.example.com. |
| https://app.example.com.evil.test/profile | **Không** | Đây là một host khác hoàn toàn, dù chứa chuỗi app.example.com. |
| https://app.example.com/profile?tab=security#top | **Có** | Query và fragment không thay đổi origin. |
| https://127.0.0.1:443/profile | **Không** | Địa chỉ IP không phải host app.example.com. |

Phép kiểm tra thực chất là **so sánh từng thành phần đã được trình duyệt chuẩn hóa**, không phải kiểm tra hai URL có chung tiền tố, chung IP hoặc chung tên tổ chức.

Một ứng dụng frontend tại **http://localhost:3000** gọi API tại **http://localhost:8080** là **cross-origin** dù cả hai chạy trên cùng máy. Đây là tình huống thường gặp khi phát triển Spring Boot và SPA (React, Vue hoặc Angular).

## 3. Origin khác site và khác phạm vi cookie

Ba khái niệm thường dễ bị nhầm lẫn:

| Khái niệm | Dùng để xét điều gì? | Ví dụ |
| --- | --- | --- |
| **Origin** | Scheme + host + port; là cơ sở của Same-Origin Policy và CORS. | https://app.example.com và https://api.example.com khác origin. |
| **Site** | Trong cách xét *schemeful same-site* hiện đại, gồm scheme và miền có thể đăng ký (registrable domain, dựa trên Public Suffix List); không xét port. | https://app.example.com và https://api.example.com thường cùng site example.com. |
| **Phạm vi cookie** | Các quy tắc riêng như Domain, Path, Secure, SameSite, HttpOnly và thuộc tính cookie khác. | Một cookie có Domain=example.com có thể phù hợp với nhiều subdomain; cookie host-only thì không. |

Ví dụ:

~~~text
https://app.example.com  ──────┐
                               ├── same-site (thường cùng example.com)
https://api.example.com  ──────┘
        Nhưng: CROSS-ORIGIN vì host khác.

http://app.example.com
https://app.example.com  ─────── CROSS-ORIGIN vì scheme khác.
                                Với schemeful same-site, cũng khác site.
~~~

**Same-site không đồng nghĩa same-origin.** Thuộc tính cookie SameSite dựa trên ngữ cảnh site, trong khi CORS dựa trên origin. Cookie có thể được gửi trong một yêu cầu cross-origin nếu các quy tắc cookie, loại yêu cầu và chế độ credentials cho phép. Ngược lại, một yêu cầu same-origin cũng không nhất thiết gửi mọi cookie nếu Domain, Path hoặc các thuộc tính khác không phù hợp.

Không nên dùng cookie Domain, SameSite hay CORS như cách viết khác của một chính sách duy nhất; mỗi cơ chế quyết định một phần hành vi khác nhau.

## 4. Same-Origin Policy bảo vệ những gì?

**Same-Origin Policy (SOP)** là chính sách quan trọng của trình duyệt, giới hạn khả năng mã chạy từ một origin tương tác với dữ liệu thuộc origin khác. Mục tiêu điển hình là ngăn JavaScript trên trang không đáng tin cậy đọc nội dung riêng tư từ một website khác mà người dùng đã đăng nhập.

Giả sử người dùng đã đăng nhập tại **https://bank.example**, sau đó mở **https://evil.test**. Script trên evil.test không thể tự do đọc DOM hay nội dung phản hồi từ bank.example chỉ vì người dùng đang đăng nhập.

Tuy nhiên, SOP **không cấm mọi yêu cầu cross-origin**:

- Trình duyệt vẫn hỗ trợ nhiều hình thức nhúng hoặc điều hướng cross-origin như liên kết, ảnh, biểu mẫu và các tài nguyên khác theo những quy tắc riêng.
- JavaScript có thể khởi tạo yêu cầu fetch cross-origin, nhưng việc đọc phản hồi phụ thuộc vào SOP và **CORS**; một số yêu cầu cần preflight trước khi gửi yêu cầu thực tế.
- Việc trình duyệt chặn JavaScript **đọc phản hồi** không có nghĩa máy chủ **không hề nhận yêu cầu**. Đây là lý do SOP/CORS tự chúng không giải quyết được CSRF.

Ví dụ một trang chạy trên **https://app.example.com**:

~~~javascript
// Cùng origin với trang: không cần CORS.
await fetch("/api/profile");

// Khác origin vì host khác: trình duyệt sẽ áp dụng CORS
// nếu JavaScript cần truy cập phản hồi.
await fetch("https://api.example.com/profile");
~~~

Khi cần giao tiếp chủ động giữa hai cửa sổ hoặc iframe khác origin, có thể dùng **window.postMessage** nhưng phải kiểm tra origin của bên gửi và chỉ định đích đáng tin cậy:

~~~javascript
// Phía nhận thông điệp:
window.addEventListener("message", (event) => {
  if (event.origin !== "https://app.example.com") return;
  // Chỉ xử lý cấu trúc và nội dung thông điệp đã kiểm tra.
});

// Phía gửi thông điệp: chỉ gửi tới origin cụ thể đã biết.
// iframe.contentWindow.postMessage(payload, "https://app.example.com");
~~~

Không coi origin chỉ chứa chuỗi tên miền tương tự là đáng tin cậy. Khi gửi dữ liệu nhạy cảm, tránh dùng target origin "*" vì bất kỳ origin nào của cửa sổ nhận cũng có thể nhận thông điệp.

## 5. CORS: cho phép đọc phản hồi cross-origin theo chính sách máy chủ

**Cross-Origin Resource Sharing (CORS)** là cơ chế dựa trên các HTTP header để máy chủ thông báo cho trình duyệt những origin nào được phép đọc phản hồi qua các API như fetch.

Ví dụ frontend đặt tại **https://app.example.com** yêu cầu API tại **https://api.example.com**:

~~~http
GET /api/products HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
~~~

Nếu máy chủ cho phép origin này, phản hồi có thể chứa:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Content-Type: application/json

{"items":[]}
~~~

Trình duyệt đối chiếu Origin của yêu cầu với header phản hồi để quyết định mã JavaScript có đọc được dữ liệu hay không. **Origin header chứa scheme, host và port**, không chứa path hoặc query. Header này có thể vắng mặt trong một số loại yêu cầu; không được giả định nó luôn hiện diện.

### Preflight (yêu cầu kiểm tra trước)

Với một số yêu cầu cross-origin, trình duyệt gửi **OPTIONS preflight** trước. Chẳng hạn, POST với Content-Type: application/json và header X-CSRF-TOKEN thường cần preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Máy chủ chấp nhận chính sách có thể trả về:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Content-Type, X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Trình duyệt chỉ tiếp tục theo quy tắc CORS nếu kết quả preflight phù hợp. **Preflight không đồng nghĩa xác thực người dùng**, không bảo đảm mã gọi API là đáng tin cậy, và không thay thế kiểm tra quyền truy cập tại máy chủ.

### Credentials và các lỗi cấu hình nguy hiểm

Khi frontend cross-origin cần gửi cookie/session trong fetch, thường phải sử dụng tùy chọn credentials thích hợp và máy chủ phải trả về chính sách CORS cho phép credentials:

~~~javascript
await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ productId: 42 })
});
~~~

Đoạn trên giả định biến csrfToken đã được lấy hợp lệ từ ứng dụng. Cookie vẫn chỉ được gửi khi quy tắc cookie và chính sách trình duyệt cho phép; việc đặt credentials: "include" không vượt qua SameSite hoặc những giới hạn cookie khác.

**Không kết hợp** Access-Control-Allow-Origin: * với Access-Control-Allow-Credentials: true cho yêu cầu có credentials: trình duyệt không chấp nhận tổ hợp này. Cũng không nên phản chiếu tùy tiện mọi Origin do client gửi rồi cho phép credentials, vì điều đó có thể cho phép website không đáng tin cậy đọc dữ liệu có xác thực.

Nếu phản hồi CORS phụ thuộc vào Origin của yêu cầu, cần xem xét header **Vary: Origin** để cache trung gian không dùng nhầm phản hồi CORS giữa các origin.

> **Ranh giới bảo mật:** CORS là cơ chế do trình duyệt thực thi. curl, script backend hoặc ứng dụng không phải trình duyệt có thể tự gửi HTTP request và không bị SOP/CORS ngăn việc đọc phản hồi. API vẫn phải xác thực, phân quyền và kiểm tra dữ liệu đầu vào như bình thường.

## 6. Origin, CORS và CSRF trong Spring Security

Đây là khác biệt rất quan trọng đối với module bảo vệ HTTP:

- **SOP** hạn chế việc một origin đọc dữ liệu của origin khác trong trình duyệt.
- **CORS** là chính sách mở quyền truy cập phản hồi cross-origin một cách có kiểm soát.
- **CSRF** là việc lợi dụng trình duyệt của người dùng đã đăng nhập để thực hiện yêu cầu thay đổi trạng thái ngoài ý muốn, thường thông qua thông tin xác thực tự động gắn vào yêu cầu như cookie.
- **SameSite cookie**, **CSRF token**, và khi phù hợp là **kiểm tra Origin/Referer** có thể hỗ trợ phòng vệ CSRF. Chỉ cấu hình CORS không đủ để chống CSRF.

Ví dụ một form HTML trên website khác có thể khiến trình duyệt gửi POST đến endpoint dùng cookie phiên nếu các quy tắc cookie cho phép. CORS có thể ngăn script của website đó đọc kết quả, nhưng không chắc ngăn được tác dụng phụ của POST. Với ứng dụng Spring Security sử dụng session/cookie, hãy giữ và tích hợp bảo vệ CSRF phù hợp cho các thao tác thay đổi trạng thái.

### 6.1. Ví dụ cấu hình Servlet (Spring Security 6.x)

API dự kiến được gọi từ ứng dụng frontend **https://app.example.com**, có thể dùng cấu hình CORS cụ thể thay vì mở toàn bộ origin:

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
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
                .build();
        // Bảo vệ CSRF mặc định vẫn được giữ.
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "Authorization", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Điểm cần hiểu:

1. Origin trong allowedOrigins là **https://app.example.com**, không phải URL trang như https://app.example.com/dashboard; path không thuộc origin.
2. Với source được đăng ký cho /api/**, các endpoint ở đường dẫn khác không tự nhiên nhận cùng chính sách CORS.
3. Phương thức POST chỉ vượt qua **kiểm tra CORS** nếu được phép; request vẫn có thể bị chặn bởi xác thực, phân quyền hoặc CSRF.
4. Spring Security cần xử lý CORS **trước các bước xác thực bảo mật có thể từ chối preflight**, vì preflight thường không kèm cookie phiên. Tích hợp cors trong security filter chain giúp xử lý yêu cầu này.

Nếu bạn dùng mô hình authentication khác, cấu hình allowed headers, credentials, cookie và CSRF phải điều chỉnh theo cách hệ thống thật sự hoạt động. Ví dụ trên minh họa chính sách origin, không phải một cấu hình bảo mật đầy đủ cho mọi ứng dụng.

### 6.2. Ví dụ cấu hình Reactive (Spring WebFlux)

Trong stack Reactive, dùng API thuộc gói **org.springframework.web.cors.reactive** cho CorsConfigurationSource và UrlBasedCorsConfigurationSource:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .authorizeExchange(auth -> auth.anyExchange().authenticated())
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "Authorization", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Về mặt trình duyệt, cách xác định origin là như nhau trong Servlet và WebFlux. Điểm khác là API cấu hình và chuỗi xử lý request trong Spring Security; không được trộn nhầm hai gói CorsConfigurationSource của Servlet và Reactive.

## 7. Chẩn đoán lỗi cross-origin theo đúng nguyên nhân

Một lỗi quen thuộc trong DevTools là:

~~~text
Access to fetch at 'https://localhost:8443/api/data'
from origin 'http://localhost:3000' has been blocked by CORS policy.
~~~

Trước hết hãy so sánh **đủ ba thành phần**:

~~~text
Frontend: http://localhost:3000
API:      https://localhost:8443
          ^^^^              ^^^^
          scheme khác       port khác
~~~

Quy trình kiểm tra thực tế:

1. Mở **DevTools → Network**, lọc request bị lỗi, kiểm tra URL đích, Request Headers và Origin.
2. Nếu có **OPTIONS**, xem preflight được trả về 2xx thích hợp hay bị 401/403/redirect; đối chiếu Access-Control-Request-Method/Headers với các header cho phép từ server.
3. Kiểm tra Access-Control-Allow-Origin có khớp **chính xác origin** của frontend hay không; nếu có credentials, kiểm tra thêm Access-Control-Allow-Credentials và cách cookie được gửi.
4. Nếu request thực tế đã tới server nhưng trả 401/403, kiểm tra **authentication, authorization và CSRF** bên cạnh CORS; lỗi 403 không mặc nhiên là lỗi CORS.
5. Kiểm tra reverse proxy hoặc gateway có thêm/xóa/nhân đôi CORS header, thay đổi scheme/host/port, hoặc chuyển hướng đến origin khác không. Chỉ tin cậy Forwarded/X-Forwarded-* khi đến từ proxy đã cấu hình tin cậy.

Có thể kiểm tra phản hồi preflight ở mức HTTP bằng lệnh:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Nếu triển khai trên PowerShell, hãy dùng **curl.exe** để tránh việc bí danh curl trỏ đến lệnh PowerShell khác. Lệnh trên chỉ giúp **xem cách máy chủ trả header**; curl không tự thực thi SOP/CORS như trình duyệt. Hãy kiểm tra thêm cả trường hợp Origin không nằm trong danh sách được phép để xác nhận server không mở quyền nhầm.

### Các sai lầm dễ gặp

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Chỉ so host, bỏ scheme và port. | Cho rằng HTTP/HTTPS hoặc hai cổng khác nhau là same-origin. | So đủ scheme, host, port đã chuẩn hóa. |
| Cấu hình origin có path: https://app.example.com/home. | Không khớp Origin header của trình duyệt. | Ghi https://app.example.com. |
| Dùng dấu * rồi bật credentials. | Trình duyệt từ chối đọc phản hồi có credentials. | Chỉ định origin được tin cậy một cách rõ ràng. |
| Mở CORS cho mọi origin vì thấy 403. | Tăng nguy cơ lộ dữ liệu hoặc làm mờ lỗi thật. | Xác định 403 đến từ CORS, CSRF hay phân quyền. |
| Tin rằng CORS ngăn mọi request độc hại. | Bỏ sót CSRF và các HTTP client ngoài trình duyệt. | Kết hợp CSRF, xác thực, phân quyền và kiểm tra đầu vào. |
| Cho phép Origin: null như một origin nội bộ tin cậy. | Có thể vô tình tin cậy các tài liệu opaque origin. | Chỉ hỗ trợ trường hợp đó khi có yêu cầu rõ và đánh giá rủi ro riêng. |

## 8. Bài tập tình huống

**Tình huống A — Cùng máy khác cổng.** Giao diện chạy tại http://localhost:5173, API Spring Boot tại http://localhost:8080. Chúng có same-origin không? Khi gọi fetch từ giao diện cần kiểm tra điều gì?

**Đáp án:** Không, vì port 5173 khác 8080. Nếu frontend gọi trực tiếp API cross-origin từ trình duyệt thì cần chính sách CORS phù hợp trên API; request vẫn chịu các quy tắc xác thực và CSRF tương ứng.

**Tình huống B — Cùng tên miền nhưng khác giao thức.** Ứng dụng chuyển từ http://portal.example.com sang https://portal.example.com. Hai origin có như nhau không? HSTS giúp ích thế nào?

**Đáp án:** Không, vì scheme khác. HSTS chỉ thị trình duyệt ưu tiên HTTPS cho host đã được áp dụng chính sách, giúp hạn chế kết nối HTTP không an toàn; nó **không** làm HTTP và HTTPS trở thành cùng origin.

**Tình huống C — Cùng site, khác origin.** Trang https://app.example.com gọi https://api.example.com với cookie đăng nhập. Hai địa chỉ có same-site và same-origin không? Bật CORS có chắc gửi được cookie không?

**Đáp án:** Thường cùng site example.com theo cách xét schemeful site, nhưng khác origin vì host khác. CORS phải cho phép origin cụ thể và credentials nếu cần đọc phản hồi có xác thực; việc cookie được gửi còn phụ thuộc fetch credentials, cookie Domain/Path/Secure/SameSite và quy tắc trình duyệt.

**Tình huống D — Form trên website lạ.** Một website ngoài hệ thống gửi form POST sang endpoint chuyển tiền có dùng cookie phiên. Website đó không được CORS cho phép. Có thể kết luận endpoint không có rủi ro CSRF không?

**Đáp án:** Không. Việc gửi form và việc đọc kết quả là hai việc khác nhau. Nếu cookie được gửi và endpoint không kiểm tra CSRF hay các điều kiện bảo vệ phù hợp, thao tác vẫn có thể xảy ra dù JavaScript trên website lạ không đọc được phản hồi.

**Tình huống E — Origin giả mạo.** Một HTTP client ngoài trình duyệt tự gửi Origin: https://app.example.com đến API. Máy chủ có nên coi Origin này là bằng chứng client đã đăng nhập hợp lệ?

**Đáp án:** Không. Header Origin không phải thông tin xác thực; client ngoài trình duyệt có thể tự đặt header. Hãy xác thực và phân quyền độc lập với CORS.

## 9. Ghi nhớ

- Với HTTP/HTTPS thông thường: **Origin = scheme + host + port**. Path, query và fragment không tham gia so sánh.
- **Khác scheme, khác host hoặc khác port ⇒ khác origin**. Cổng mặc định được chuẩn hóa khi so sánh.
- **Same-origin** khác **same-site**; cookie SameSite và CORS kiểm soát các khía cạnh khác nhau.
- **SOP** giới hạn quyền truy cập giữa các origin; **CORS** cho phép một số truy cập cross-origin theo quyết định của máy chủ.
- **CORS không thay thế CSRF, xác thực hoặc phân quyền**. Đây là nền tảng để triển khai nhất quán lớp bảo vệ HTTP trong Spring Security ở cả Servlet và Reactive.
