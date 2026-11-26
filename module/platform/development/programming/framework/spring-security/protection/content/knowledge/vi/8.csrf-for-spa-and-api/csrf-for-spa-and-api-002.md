# Token do JavaScript chủ động gửi trong Authorization header

## Mục tiêu và phạm vi

Trong chương **CSRF cho SPA và API** của module **SPRING_SECURITY_HTTP_PROTECTION**, ta cần phân biệt hai cách trình duyệt đưa thông tin đăng nhập vào yêu cầu HTTP:

1. Trình duyệt **tự động** gửi cookie phiên, cookie chứa JWT, HTTP Basic credentials đã lưu hoặc thông tin xác thực tương đương.
2. Mã JavaScript của SPA **chủ động** lấy access token và đặt vào header **Authorization: Bearer ...** khi gọi API.

Sự khác nhau này quyết định cách đánh giá **Cross-Site Request Forgery (CSRF)**. Bài học trình bày mô hình đe dọa, cách thiết kế API Bearer token, ví dụ Spring Security cho **Servlet** và **Reactive**, cũng như cách kiểm thử và chẩn đoán xung đột với **CORS**, **security headers**, quản lý session và các cơ chế bảo vệ trình duyệt.

Sau khi học, bạn có thể:

- Giải thích vì sao access token do JavaScript gửi trong **Authorization** thường không chịu CSRF truyền thống như API xác thực bằng cookie.
- Nhận diện các ngoại lệ quan trọng: cookie fallback, refresh token trong cookie, endpoint đăng nhập/đăng xuất, HTTP Basic và ứng dụng lai giữa session với Bearer token.
- Cấu hình **SecurityFilterChain** hoặc **SecurityWebFilterChain** phù hợp cho API chỉ nhận Bearer token.
- Phân biệt công dụng của **CORS**, CSRF, XSS, JWT validation và phân quyền.
- Kiểm thử request có/không có Bearer token, cross-origin preflight và các đường xác thực ngoài ý muốn.

## 1. Điểm cốt lõi: ai gắn thông tin xác thực vào request?

Giả sử người dùng đăng nhập vào SPA **https://app.example.com**. SPA nhận một access token từ hệ thống xác thực, giữ token trong bộ nhớ và dùng JavaScript gọi API:

~~~javascript
const response = await fetch("https://api.example.com/api/profile", {
  method: "GET",
  headers: {
    Authorization: "Bearer " + accessToken
  },
  credentials: "omit"
});
~~~

Trong thiết kế **Bearer-only** này, backend **chỉ** coi giá trị Bearer token trong header **Authorization** là bằng chứng xác thực; không coi cookie trình duyệt là cách đăng nhập thay thế. Trình duyệt không tự biết token mà SPA đang giữ để thêm vào một request do trang khác khởi tạo.

So sánh với API session cookie:

~~~http
POST /api/profile HTTP/1.1
Host: api.example.com
Cookie: JSESSIONID=some-session-id
Content-Type: application/x-www-form-urlencoded

displayName=NewName
~~~

Nếu trình duyệt gửi cookie phù hợp và server xác thực bằng cookie, yêu cầu có thể được coi là đã đăng nhập **mà không cần mã JavaScript của SPA chủ động bổ sung token**. Đó chính là điều kiện quan trọng làm phát sinh CSRF.

Trong API chỉ nhận Bearer token:

~~~http
POST /api/profile HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJ...
Content-Type: application/json

{"displayName":"NewName"}
~~~

Một website độc hại **https://attacker.test** có thể cố gửi POST đến URL này, nhưng nó **không có access token** của SPA để tạo một header **Authorization** hợp lệ. Nếu token không bị lộ và API không chấp nhận xác thực tự động, yêu cầu giả mạo sẽ không được xác thực.

> **Kết luận có điều kiện:** API thực sự chỉ xác thực bằng Bearer token **do client chủ động gắn vào header** thường không cần CSRF token cho các endpoint đó. Kết luận chỉ đúng khi không tồn tại đường xác thực bằng cookie, HTTP Basic tự động hoặc cơ chế browser-managed khác được backend chấp nhận.

### 1.1. Authorization header không đồng nghĩa với Bearer token chủ động

Header **Authorization** có nhiều scheme, ví dụ **Basic** và **Bearer**. Trình duyệt có thể tự quản lý thông tin xác thực của HTTP Basic trong một số tình huống. Vì vậy, không thể suy luận “có Authorization header thì không có CSRF”.

| Cách xác thực | Ai thường cung cấp thông tin xác thực? | Đánh giá CSRF |
| --- | --- | --- |
| SPA lấy access token và gửi **Authorization: Bearer ...** | JavaScript chủ động đặt header | CSRF truyền thống thường không áp dụng nếu API chỉ chấp nhận Bearer và không dùng cookie |
| JWT trong cookie **HttpOnly** được API đọc tự động | Trình duyệt tự gửi cookie | Có bề mặt CSRF với request thay đổi trạng thái |
| **JSESSIONID** cùng backend session | Trình duyệt tự gửi cookie | Cần CSRF protection với request không an toàn |
| HTTP Basic được trình duyệt ghi nhớ | Trình duyệt có thể tự cung cấp credentials | Cần đánh giá CSRF theo hành vi thực tế |
| SPA gửi Bearer nhưng backend cũng cho phép session cookie | JavaScript hoặc trình duyệt | Đường xác thực cookie vẫn cần CSRF protection |
| Native app/server-to-server gửi Bearer | Ứng dụng chủ động đặt header | Không có bối cảnh CSRF trình duyệt thông thường; vẫn cần xác thực và phân quyền |

**JWT không phải cơ chế chống CSRF.** JWT có thể nằm trong header Bearer hoặc trong cookie. Chính **cách credential được gửi đến máy chủ** mới là yếu tố quyết định.

## 2. Minh họa đường tấn công và ranh giới bảo vệ

### 2.1. Một form giả mạo không tự mang Bearer token

Giả sử kẻ tấn công tạo trang:

~~~html
<!-- Trang minh họa trong môi trường kiểm thử được phép -->
<form action="https://api.example.com/api/orders" method="post">
  <input type="hidden" name="sku" value="P100">
  <input type="hidden" name="quantity" value="10">
  <button type="submit">Submit</button>
</form>
~~~

Form có thể tạo request POST đến API. Tuy nhiên, **HTML form không có khả năng tự lấy access token** đang nằm trong bộ nhớ của JavaScript tại **app.example.com** rồi thêm header **Authorization: Bearer ...**. Nếu API chỉ chấp nhận Bearer token, response thường là **401 Unauthorized** (hoặc một mã từ chối phù hợp) vì request chưa được xác thực.

Nếu cùng endpoint lại chấp nhận cookie xác thực và body biểu mẫu, kết quả có thể khác: request vẫn có thể được xử lý dưới danh tính nạn nhân. Vì vậy phải **kiểm tra toàn bộ những cách xác thực endpoint thực sự chấp nhận**, không chỉ xem mã nguồn SPA.

### 2.2. JavaScript trên origin khác không tự lấy được token

Kẻ tấn công có thể viết:

~~~javascript
fetch("https://api.example.com/api/orders", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Authorization: "Bearer ???"
  },
  body: JSON.stringify({ sku: "P100", quantity: 10 })
});
~~~

Điều còn thiếu là **access token hợp lệ**. JavaScript ở **attacker.test** không được tự đọc **sessionStorage**, **localStorage** hay biến JavaScript trong origin **app.example.com**. Đặt header **Authorization** không giúp tự sinh credential.

Với JavaScript khác origin, header **Authorization** còn làm request cần **CORS preflight**. Nếu API không cho phép origin và header tương ứng, trình duyệt sẽ không gửi request thực tế. Đây là một hạn chế bổ sung của trình duyệt, nhưng **CORS không phải hệ thống xác thực**: công cụ CLI, backend khác và các HTTP client ngoài browser không chịu ràng buộc CORS. API vẫn phải xác minh token và quyền truy cập với mọi request.

### 2.3. XSS thay đổi hoàn toàn mô hình đe dọa

Nếu kẻ tấn công chạy được JavaScript độc hại **ngay trong origin đáng tin cậy** của SPA thông qua **Cross-Site Scripting (XSS)**, mã đó có thể:

- Đọc access token trong **localStorage**, **sessionStorage** hoặc các vị trí JavaScript truy cập được.
- Gửi request qua chính ứng dụng với quyền của người dùng, ngay cả khi access token chỉ được giữ trong bộ nhớ.
- Đọc dữ liệu mà SPA có quyền truy cập và gửi ra ngoài nếu không có các biện pháp ngăn chặn phù hợp.

**CSRF token không sửa được XSS**: mã độc đang chạy cùng origin với SPA thường có thể thực hiện các hành động giống SPA hợp lệ. Vì thế mô hình Bearer token chuyển trọng tâm phòng vệ sang:

- Chống XSS thông qua encoding đúng ngữ cảnh, xử lý HTML an toàn và kiểm soát nội dung không tin cậy.
- **Content Security Policy (CSP)** hạn chế nguồn script và các đường thực thi nguy hiểm, được triển khai và thử nghiệm phù hợp ứng dụng.
- Bảo vệ access token, hạn dùng ngắn, quyền tối thiểu, kiểm soát refresh token.
- HTTPS, **HSTS**, security headers, cập nhật dependencies, phân quyền và giám sát token bị lộ.

Không xem việc “không cần CSRF token” như “ứng dụng đã an toàn”.

## 3. Bốn điều kiện trước khi bỏ kiểm tra CSRF cho API

Hãy xác nhận **đồng thời** các điều kiện sau:

1. **Endpoint xác thực duy nhất bằng Bearer header.** Backend không tự dùng **JSESSIONID**, cookie access token, HTTP Basic đã lưu hoặc chứng chỉ client do browser gửi làm lựa chọn thay thế.
2. **Token không được browser tự gắn.** Mã client phải chủ động lấy token và gửi **Authorization: Bearer ...**; form, redirect và request do origin khác không có sẵn token.
3. **Phạm vi bỏ CSRF được giới hạn chính xác.** Chỉ áp dụng cho chain hoặc endpoint Bearer-only, tránh tắt toàn bộ bảo vệ của ứng dụng nếu cùng hệ thống còn đăng nhập web bằng session cookie.
4. **Các luồng phụ đã được đánh giá riêng.** Login, logout, refresh, token rotation, đăng nhập liên kết, endpoint quản trị, WebSocket handshake hoặc đường xác thực hỗn hợp có thể mang browser-managed credentials.

Một cách rà soát thực tế là tạo bảng:

| Route | Credential server chấp nhận | Request thay đổi trạng thái? | Cần bảo vệ CSRF? |
| --- | --- | --- | --- |
| **POST /api/orders** | Chỉ **Authorization: Bearer** | Có | Thường không, nếu cả bốn điều kiện đều đúng |
| **PATCH /api/profile** | Bearer **hoặc** session cookie | Có | **Có** cho đường cookie; cần thiết kế chính sách theo đúng chain |
| **POST /auth/refresh** | Refresh token trong cookie **HttpOnly** | Có thể xoay vòng credential và cập nhật trạng thái | Phải phân tích CSRF; các biện pháp tùy kiến trúc, không tự động loại trừ vì response chứa JSON |
| **POST /logout** | Session cookie | Có | **Có** |
| **GET /api/products** | Bearer hoặc public | Không (nếu đúng semantics GET) | Thông thường không |
| **POST /api/internal/reindex** | Chỉ Bearer từ dịch vụ nội bộ | Có | Không phải CSRF browser truyền thống; yêu cầu xác thực mạnh và phân quyền |

**SessionCreationPolicy.STATELESS** không tự chứng minh API miễn CSRF. Một backend dùng JWT **trong cookie** có thể stateless về lưu phiên nhưng vẫn có CSRF vì trình duyệt tự gửi cookie. Ngược lại, không nhất thiết phải tắt CSRF chỉ vì API dùng JSON; điểm quyết định là cơ chế credential.

## 4. Xây dựng lời gọi Bearer token từ SPA

### 4.1. Gắn access token có chủ đích

Ví dụ sau giả định SPA đã có access token qua luồng xác thực phù hợp (chẳng hạn OAuth 2.0 Authorization Code với PKCE cho public client):

~~~javascript
// Ví dụ đơn giản: token được quản lý trong bộ nhớ ứng dụng.
let accessToken = null;

function setAccessToken(nextToken) {
  accessToken = nextToken;
}

async function apiRequest(path, { method = "GET", body } = {}) {
  if (!accessToken) {
    throw new Error("User must sign in");
  }

  const response = await fetch("https://api.example.com" + path, {
    method,
    // Chỉ dùng nếu API thực sự Bearer-only, không có cookie xác thực.
    credentials: "omit",
    cache: "no-store",
    headers: {
      Authorization: "Bearer " + accessToken,
      ...(body === undefined ? {} : { "Content-Type": "application/json" })
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) })
  });

  if (response.status === 401) {
    // Hủy credential hết hạn; luồng lấy token mới phải được thiết kế riêng.
    setAccessToken(null);
    throw new Error("Access token missing, invalid or expired");
  }
  if (response.status === 403) {
    throw new Error("Permission denied");
  }
  if (!response.ok) {
    throw new Error("API request failed: " + response.status);
  }
  return response.status === 204 ? null : response.json();
}

// Gọi API JSON bằng Bearer token.
const order = await apiRequest("/api/orders", {
  method: "POST",
  body: { sku: "P100", quantity: 1 }
});
~~~

Trong mô hình này:

- **Authorization** được JavaScript thêm vào từng request; không có CSRF header riêng cho các route Bearer-only.
- **credentials: "omit"** tránh gửi cookie trình duyệt kèm request và giúp kiểm thử tính chất Bearer-only. Header Bearer được đặt tường minh trong mã.
- Token chỉ được gửi tới API tin cậy; không ghép URL tùy ý do người dùng cung cấp vào đường gửi Authorization.
- HTTP **401** thường biểu thị chưa có xác thực hợp lệ; **403** thường biểu thị đã nhận dạng nhưng không đủ quyền. Tuy nhiên, bộ xử lý lỗi và chính sách ứng dụng có thể tạo ngoại lệ; chẩn đoán theo filter chain thực tế.
- Ví dụ trên không triển khai toàn bộ cơ chế OAuth: ứng dụng thực tế cần xử lý lifecycle, timeout, refresh và hủy token an toàn, thay vì tự động retry vô hạn.

### 4.2. Token lưu ở đâu?

| Nơi giữ access token | Lợi thế | Rủi ro và lưu ý |
| --- | --- | --- |
| **Bộ nhớ JavaScript** | Không tự lưu qua reload; giảm thời gian lưu token lâu dài | XSS cùng origin có thể gọi API hoặc lấy token đang sử dụng; reload cần cơ chế đăng nhập/renew phù hợp |
| **sessionStorage** | Thường chỉ tồn tại trong vòng đời tab/session của origin | JavaScript cùng origin, gồm script bị chèn qua XSS, có thể đọc |
| **localStorage** | Tồn tại qua reload và khởi động lại | XSS có thể đọc; token bị giữ lại lâu hơn và cần chiến lược xóa |
| **HttpOnly cookie** | JavaScript không trực tiếp đọc giá trị | Browser tự gửi cookie nếu chính sách cho phép; API đọc cookie làm xác thực sẽ có bề mặt CSRF |

Không có lựa chọn lưu trữ nào tự giải quyết toàn bộ rủi ro. Mức độ tin cậy của script, CSP, quyền hạn, thời gian sống của token, cơ chế làm mới và khả năng phát hiện lộ token đều quan trọng.

**Refresh token trong HttpOnly cookie** thường được dùng để hạn chế việc JavaScript trực tiếp đọc refresh token. Nhưng nếu endpoint refresh dựa vào cookie đó, nó là một phần của mô hình xác thực dựa trên browser-managed credentials và phải được đánh giá CSRF riêng. Tùy hành vi của endpoint, có thể cần CSRF token, kiểm tra Origin/Fetch Metadata, chính sách SameSite và kiểm soát CORS chặt. Không nới CORS cho mọi origin chỉ để SPA truy cập refresh endpoint.

### 4.3. Token có thể là JWT hoặc opaque token

API Resource Server có thể chấp nhận:

- **JWT**: xác minh chữ ký, thuật toán hợp lệ, issuer, thời hạn và các claim được yêu cầu; kiểm tra **audience** theo cấu hình ứng dụng và ánh xạ scope/role thành quyền.
- **Opaque token**: gọi introspection hoặc cơ chế xác minh tương đương với authorization server, rồi kiểm tra hiệu lực và quyền.

**Bearer** mô tả cách trình bày token trong HTTP, không bắt buộc định dạng JWT. Không chấp nhận token chỉ vì chuỗi có ba phần phân tách bằng dấu chấm; phải xác minh token bằng cơ chế đáng tin cậy.

## 5. Cấu hình Spring Security Servlet cho Bearer-only API

Ví dụ này đặt các request **/api/** vào một **SecurityFilterChain** riêng, chỉ chấp nhận JWT Bearer token. Các request web bên ngoài phạm vi đó vẫn dùng session và CSRF protection thông thường.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .cors(Customizer.withDefaults())
            // Chỉ khi /api/** thực sự không dùng cookie/browser-managed auth.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserUi(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

Những điều cần hiểu trước khi sử dụng:

1. **securityMatcher("/api/**")** giới hạn phạm vi áp dụng chain. Spring Security chọn chain đầu tiên khớp; thứ tự qua **@Order** là quan trọng.
2. **oauth2ResourceServer(...jwt(...))** cấu hình máy chủ tài nguyên xác thực JWT Bearer token. Cần khai báo nguồn khóa/issuer và dependency Resource Server theo cách phù hợp ứng dụng; ví dụ chỉ minh họa SecurityFilterChain.
3. **SessionCreationPolicy.STATELESS** tránh dùng **HttpSession** để lưu và lấy **SecurityContext** cho chain API. Nó không thay thế bước xác minh rằng API không chấp nhận cookie ở cơ chế xác thực khác.
4. **csrf(AbstractHttpConfigurer::disable)** được áp dụng **chỉ** trong chain Bearer API. Chain web vẫn giữ **CSRF** cho form/session cookie.
5. **401** khi request chưa xác thực; **403** khi token hợp lệ nhưng không được cấp quyền. Nếu API vẫn chấp nhận session cookie ở nơi khác cùng path, cần sửa thiết kế chain và AuthenticationProvider/Filter tương ứng.

Trong ứng dụng **chỉ** có API Resource Server Bearer-only, bạn có thể không cần chain **browserUi**. Ngược lại, khi ứng dụng còn có đường xác thực cookie, không sao chép cấu hình tắt CSRF của API sang chain web.

### 5.1. CORS khi SPA và API khác origin

Ví dụ SPA chạy tại **https://app.example.com**, API tại **https://api.example.com**. Fetch với Bearer header qua origin khác thường gây preflight; API cần công bố chính xác origin và header được phép:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource apiCorsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
    config.setAllowedHeaders(List.of("Authorization", "Content-Type"));
    // Không cần gửi cookie với API Bearer-only.
    config.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
~~~

Với **.cors(Customizer.withDefaults())** trong chain Servlet và **CorsConfigurationSource** bean, preflight có thể được xử lý trước khi xác thực. **Authorization** là header không nằm trong nhóm request đơn giản; vì vậy allowlist CORS phải bao gồm chính header này.

**CORS không xác minh Bearer token.** Ngay cả khi Origin không có trong allowlist và browser chặn JavaScript đọc kết quả, API vẫn phải xác thực từng request ở phía server. Nhiều API còn có client server-to-server hoặc mobile không chịu hạn chế của trình duyệt.

Chú ý **Access-Control-Allow-Credentials** không cần bật chỉ vì request chứa header Authorization do ứng dụng tự đặt. Nếu API thiết kế để không dùng cookie, cấu hình **credentials: "omit"** ở phía client cùng **setAllowCredentials(false)** ở phía server tạo một hợp đồng rõ ràng.

### 5.2. Ví dụ JWT Resource Server cần xác minh những gì?

Ngoài chữ ký và thời hạn, hãy kiểm tra cấu hình tin cậy của token:

- **issuer** phải là nhà phát hành dự kiến; không tự chọn khóa xác minh dựa trên tham số token chưa được tin cậy.
- **audience** phải phù hợp API đang được gọi; không dùng token phát cho hệ thống khác như token truy cập API của mình.
- **scope/authority** cần phù hợp thao tác, ví dụ quyền ghi đơn hàng mới được gọi **POST /api/orders**.
- Token hết hạn, bị thu hồi hoặc không hợp lệ phải bị từ chối; nếu dùng opaque token, kiểm tra introspection và chính sách cache phù hợp.
- Không đưa access token vào query string, URL được chia sẻ, log, analytics hoặc thông điệp lỗi.

Lớp **HTTP firewall**, security headers, HTTPS/HSTS và kiểm soát session vẫn là các lớp phòng vệ của hệ thống, dù chain Bearer-only không cần CSRF token trong mô hình giả định.

## 6. Cấu hình Spring Security WebFlux/Reactive

Ý tưởng tương tự Servlet nhưng API dùng **SecurityWebFilterChain** và **ServerHttpSecurity**. Ví dụ tách API Bearer JWT và phần UI dùng cookie/session:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
class ReactiveSecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain bearerApi(ServerHttpSecurity http) {
        return http
            .securityMatcher(ServerWebExchangeMatchers.pathMatchers("/api/**"))
            // Không dùng CSRF token chỉ với API JWT Bearer-only.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain browserUi(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

Trong WebFlux, cần cấu hình **CORS Reactive** riêng khi SPA khác origin, sử dụng cấu hình phù hợp với **CorsWebFilter** hoặc CORS integration của Spring Security WebFlux. Đảm bảo preflight được xử lý trước khi filter xác thực đòi Bearer token. Đừng nhập nhằng giữa **org.springframework.web.cors.UrlBasedCorsConfigurationSource** của Servlet và **org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource** của Reactive.

Nếu API WebFlux xác thực bằng cookie **WebSession** hoặc JWT trong cookie, không áp dụng nguyên xi cấu hình vô hiệu hóa CSRF ở trên. Hãy giữ CSRF protection và sử dụng **ServerCsrfTokenRepository**, các request handler cùng cách cấp token cho SPA phù hợp.

## 7. Vì sao không nên tắt CSRF cho cả ứng dụng?

Một hệ thống thường có nhiều kiểu xác thực:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B{"Đường dẫn và security chain"}
    B -->|"/api/**"| C["Bearer-only API"]
    B -->|"/login, /ui/**, /auth/refresh"| D["Browser/session flows"]
    C --> E["Authorization: Bearer"]
    E --> F{"Token hợp lệ và đủ quyền?"}
    F -->|Không| G["401 hoặc 403"]
    F -->|Có| H["Xử lý API"]
    D --> I{"Cookie/browser credentials?"}
    I -->|Có| J["Kiểm tra CSRF khi đổi trạng thái"]
    J --> K["Xác thực + phân quyền + xử lý"]
~~~

Sơ đồ là nguyên tắc thiết kế, không mặc định mọi endpoint **/auth/refresh** bắt buộc dùng cùng một thuật toán CSRF. Cần đánh giá thao tác mà refresh endpoint thực hiện, cookie được gửi trong tình huống nào và điều kiện nào cho phép website bên ngoài kích hoạt thao tác.

Các lỗi triển khai thường thấy:

- Gắn **.csrf(disable)** cho chain mặc định toàn bộ ứng dụng rồi bổ sung form login/session sau đó.
- SPA gửi header Bearer nhưng backend vẫn có filter xác thực từ **JSESSIONID** hoặc từ cookie JWT để “tương thích ngược”.
- API chia sẻ đường **/api/** giữa Bearer và session mà không có thiết kế rõ ràng cho CSRF của từng trường hợp.
- Đổi API sang stateless nhưng vẫn dựa vào refresh cookie mà không đánh giá login, logout, rotation và các endpoint phụ.
- Cho phép **CORS mọi origin** và cookies/credentials với suy nghĩ “API đã có Bearer token”.

Khi có hai cơ chế xác thực cho cùng endpoint, chỉ bỏ CSRF nếu đã chứng minh các request do browser gửi với cookie **không thể** vượt qua bảo vệ và thực hiện thao tác. Trong nhiều ứng dụng, thiết kế sạch hơn là tách rõ chain/endpoint theo cách xác thực.

## 8. Kiểm thử Spring Security Servlet bằng MockMvc

Giả định API có **POST /api/orders** và chain Bearer-only ở trên. Với **spring-security-test**, có thể mô phỏng một người dùng mang JWT hợp lệ:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BearerOnlyApiTests {
    @Autowired MockMvc mockMvc;

    @Test
    void rejectsMissingBearer() throws Exception {
        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void acceptsJwtWithoutCsrfHeader() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(jwt())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            // Khi controller và quyền truy cập thực tế cho phép tạo đơn:
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

**Lưu ý về test:** **jwt()** là test helper đặt thông tin xác thực mô phỏng vào security context; nó **không** xác minh chữ ký, khóa công khai, issuer, audience, expiry hay việc parse header Bearer thực tế. Cần thêm bài kiểm thử tích hợp với request **Authorization: Bearer <token>** hợp lệ/không hợp lệ và decoder hoặc authorization server tương ứng. Kỳ vọng **2xx** chỉ đúng khi endpoint mẫu có tồn tại và nghiệp vụ chấp nhận dữ liệu.

Test này kiểm tra đặc điểm “Bearer-only request đã xác thực không bị bắt buộc có CSRF token”. Đừng suy rộng thành việc mọi request POST trong hệ thống đều được phép thiếu CSRF.

## 9. Kiểm thử Reactive bằng WebTestClient

Trong Spring WebFlux, **spring-security-test** hỗ trợ **mockJwt()**:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

// webTestClient đã được gắn Spring Security, và /api/orders tồn tại.
webTestClient.post().uri("/api/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().isUnauthorized();

webTestClient.mutateWith(mockJwt())
    .post().uri("/api/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

Đây là đoạn thân test minh họa; khi đưa vào test class cần khai báo **WebTestClient**, import **java.util.Map**, và khởi tạo handler/controller tương ứng. Tương tự **jwt()** của MockMvc, **mockJwt()** giả lập trạng thái xác thực; kiểm thử đầy đủ vẫn cần decoder/JWT thực.

### 9.1. Ma trận kiểm thử bảo vệ

| Thử nghiệm | Kỳ vọng trong Bearer-only API |
| --- | --- |
| POST JSON không cookie, không Bearer, không CSRF token | **401**, không thay đổi dữ liệu |
| POST có cookie session cũ nhưng không Bearer | **401**, không thay đổi dữ liệu; xác minh không có cookie fallback |
| POST có Bearer token giả, hết hạn hoặc sai chữ ký | **401**, không thay đổi dữ liệu |
| POST có Bearer hợp lệ, không có CSRF header | Vượt bước xác thực và không bị CSRF chặn; vẫn chịu phân quyền và validation |
| POST có Bearer hợp lệ nhưng thiếu scope/quyền | **403** hoặc mã từ chối tương ứng, không thay đổi dữ liệu |
| POST từ origin không được cấp CORS bằng JavaScript | Browser không gửi request thực tế khi preflight thất bại; API vẫn phải xác thực server-side |
| POST từ client ngoài browser với Bearer hợp lệ | Không bị CORS quyết định; xác thực/phân quyền server-side là bắt buộc |
| POST vào endpoint session cookie của ứng dụng, thiếu CSRF token | Bị chặn theo cấu hình của **browserUi** chain |
| Refresh/login/logout dùng cookie | Kiểm thử CSRF và vòng đời session/credential theo mô hình endpoint |

Khi kiểm thử với DevTools, kiểm tra **Network** để phân biệt **OPTIONS preflight**, request thật, header **Authorization**, cookie, status **401/403**, response CORS và việc dữ liệu có bị thay đổi hay không.

### 9.2. Test xác nhận không tồn tại cookie fallback

Một kiểm thử đặc biệt hữu ích là:

1. Đăng nhập qua UI để có cookie **JSESSIONID** còn hiệu lực.
2. Gọi **POST /api/orders** với cookie đó nhưng **không** gửi **Authorization: Bearer**.
3. Xác nhận API trả **401** và không tạo đơn hàng.
4. Gọi lại với Bearer token hợp lệ; xác minh request được xử lý theo đúng quyền, bất kể cookie có mặt hay không.

Nếu bước 3 thành công, giả định “API chỉ dùng Bearer token” đã sai; phải điều chỉnh cấu hình trước khi chấp nhận việc bỏ CSRF.

## 10. Chẩn đoán lỗi thường gặp

### “Tắt CSRF rồi nhưng POST vẫn trả 403”

**403** có thể đến từ **authorization**, scope/authority thiếu, policy nghiệp vụ hoặc filter bảo mật khác. Kiểm tra chain thực sự khớp request, principal đang xác thực, mapping scope và log Spring Security. Nếu thiếu Bearer token, một Resource Server thông thường trả **401**, không phải lỗi CSRF.

### “POST có Bearer header nhưng trình duyệt báo CORS”

Nếu SPA và API khác origin, header Authorization thường kích hoạt **OPTIONS preflight**. Kiểm tra server có cho phép **Origin**, **Authorization** trong **Access-Control-Allow-Headers** và phương thức tương ứng không. Xác nhận preflight được xử lý trước lớp xác thực; đừng yêu cầu Bearer token cho preflight của trình duyệt.

### “Tại sao fetch có token hợp lệ nhưng vẫn 401?”

Xem header có bị xóa bởi proxy/API gateway, token có hết hạn, issuer/audience có đúng, Resource Server đang xác minh JWT hay opaque token, clock skew và quyền truy cập vào endpoint. CORS failure cũng có thể khiến ứng dụng JS không đọc được phản hồi, nhưng đó là triệu chứng khác với chính response **401**.

### “SPA gửi Bearer nhưng server vẫn tạo JSESSIONID”

Cookie có thể do thành phần khác tạo (controller, Spring MVC, form login, session/request cache). Việc có **JSESSIONID** chưa đủ chứng minh API dùng cookie làm xác thực, nhưng cần kiểm tra. Dùng test chỉ-có-cookie và chỉ-có-Bearer để xác nhận cơ chế nào thực sự cho phép thao tác.

### “Dùng access token trong localStorage thì có an toàn CSRF không?”

Nếu server chỉ nhận Bearer header do JS chủ động thêm thì lưu trong localStorage không làm browser tự phát sinh Bearer header trên request giả mạo. Tuy nhiên, token trong localStorage **có thể bị JavaScript độc hại cùng origin đọc**. Đây là bài toán **XSS và quản lý token**, nghiêm trọng nhưng khác CSRF truyền thống.

### “Refresh token trong cookie, access token trong Authorization: có tắt CSRF toàn bộ không?”

Không. Các API chỉ nhận access token qua header có thể theo chính sách Bearer-only, nhưng **/auth/refresh**, login, logout và các route đọc cookie phải được đánh giá riêng. Đặc biệt xem tác động của refresh token rotation, kiểm soát cookie SameSite, CSRF token hay Origin/Fetch Metadata và CORS.

### “HTTP firewall, CSP, HSTS có thay CSRF không?”

Không. **HTTP firewall** chuẩn hóa/từ chối request có đặc điểm nguy hiểm; **CSP** giúp giảm nguy cơ XSS, **HSTS** buộc trình duyệt dùng HTTPS khi đủ điều kiện; **CORS** quản lý truy cập khác origin. Chúng là các lớp bảo vệ có mục tiêu riêng, không tự xác minh người dùng chủ động phát sinh request xác thực bằng cookie.

## 11. Bài tập tình huống

**Tình huống A:** SPA lưu JWT trong memory, gọi **POST /api/payment** với header **Authorization: Bearer**; API có Resource Server JWT, không chấp nhận cookie hay Basic. Trang độc hại gửi form POST không có Bearer.  
**Đánh giá:** Đây không phải đường CSRF khả thi khi server chỉ nhận Bearer token. Yêu cầu phải bị từ chối vì chưa xác thực. Cần ưu tiên token validation, quyền thanh toán, chống XSS và kiểm tra CORS.

**Tình huống B:** SPA vẫn gửi Bearer header, nhưng backend có filter đọc JWT từ cookie **AUTH_TOKEN** nếu Authorization vắng mặt.  
**Đánh giá:** Điều kiện Bearer-only không còn đúng. Trình duyệt có thể tự gửi cookie phù hợp cho các request độc hại. Cần đánh giá và bảo vệ CSRF cho đường cookie hoặc loại bỏ đường xác thực cookie khỏi API.

**Tình huống C:** Access token lưu trong memory, refresh token ở cookie HttpOnly. Route **POST /auth/refresh** xoay vòng refresh token rồi cấp access token mới qua JSON.  
**Đánh giá:** Các route Bearer-only có thể không cần CSRF token, nhưng **/auth/refresh** phải được phân tích độc lập vì nó dùng cookie và có thể thay đổi trạng thái xác thực. Kiểm soát origin, cookie, token rotation và tác động khi request do bên thứ ba gây ra.

**Tình huống D:** API chỉ nhận Bearer token nhưng một script không tin cậy được nhúng từ CDN và chạy trên origin SPA.  
**Đánh giá:** Script đó có thể thực hiện hành động dưới quyền SPA hoặc lấy token JavaScript truy cập được. Vấn đề là **XSS/supply-chain script**, không được giải quyết bằng việc bật CSRF token cho Bearer-only API; cần CSP, quản trị script và giảm quyền token.

## 12. Các nguyên tắc cần nhớ

1. **Bearer header do JavaScript chủ động gửi** khác với **cookie do trình duyệt tự gửi**. Phân biệt này là nền tảng để đánh giá CSRF.
2. **Bearer-only API** thường có thể bỏ yêu cầu CSRF token nếu server không chấp nhận browser-managed credentials làm đường xác thực thay thế.
3. **JWT** có thể ở header hoặc cookie; việc token là JWT không tự quyết định có CSRF hay không.
4. **Tách security chain** cho API Bearer-only và browser/session khi ứng dụng có cả hai; giữ CSRF cho các route xác thực bằng cookie.
5. **CORS/preflight** giúp kiểm soát lời gọi khác origin trong browser, nhưng không thay thế token validation và phân quyền.
6. **Chống XSS, kiểm soát lưu trữ token, CSP, HTTPS/HSTS và scope** vẫn quan trọng khi API không cần CSRF token.
7. **Kiểm thử bằng hành vi thực**: chỉ-có-cookie phải thất bại với API Bearer-only; Bearer hợp lệ không cần CSRF header; token sai/thiếu và thiếu quyền phải bị chặn.

Lựa chọn bật hay tắt CSRF trong Spring Security phải xuất phát từ **cách request được xác thực và khả năng trình duyệt tự gắn credential**, không xuất phát từ việc API dùng REST/JSON hay tên của trường Authorization.
