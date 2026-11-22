# Cookie phiên, CSRF và thao tác gọi thử làm thay đổi trạng thái

Swagger UI cho phép người dùng gọi API ngay trên trang tài liệu bằng nút **Try it out**. Nếu Spring Boot xác thực người dùng bằng session cookie, trình duyệt sẽ tự gửi cookie trong các request phù hợp. Điều này thuận tiện cho kiểm thử, nhưng cũng có nghĩa các request làm thay đổi dữ liệu cần được bảo vệ khỏi Cross-Site Request Forgery (CSRF).

Khi tích hợp springdoc-openapi với Spring Security, cần phối hợp ba cơ chế:

1. **Session cookie** nhận diện phiên đăng nhập và được trình duyệt tự gửi theo chính sách cookie.
2. **CSRF token** chứng minh request thay đổi trạng thái được tạo từ ứng dụng đã nhận token hợp lệ.
3. **Swagger UI** gửi CSRF token trong header khi người dùng dùng Try it out, để Spring Security có thể xác minh request.

CSRF là lớp bảo vệ độc lập với xác thực và phân quyền. Một request có session hợp lệ vẫn có thể bị từ chối nếu thiếu CSRF token. Ngược lại, CSRF token hợp lệ không chứng minh người dùng có quyền thực hiện nghiệp vụ.

## 1. Vì sao session cookie cần CSRF protection?

Trình duyệt tự gửi cookie phù hợp với URL đích. Nếu người dùng đã đăng nhập vào api.example.com, một website độc hại có thể tìm cách khiến trình duyệt của người đó gửi request đến API này. Browser có thể đính kèm session cookie mà người dùng không nhận ra.

Ví dụ, người dùng đang đăng nhập vào hệ thống quản lý đơn hàng. Một trang khác có thể tạo form gửi request:

~~~html
<form action="https://api.example.com/api/orders/123/cancel" method="POST">
  <button type="submit">Continue</button>
</form>
~~~

Nếu endpoint không có CSRF protection, server có thể nhận request cùng session cookie của người dùng và thực hiện thao tác hủy đơn. Trình duyệt gửi cookie tự động, vì vậy chỉ kiểm tra session đã đăng nhập là chưa đủ để phân biệt request do ứng dụng hợp lệ tạo ra với request bị giả mạo.

CSRF token bổ sung một giá trị mà website khác không thể tự đọc hoặc đoán hợp lệ. Client phải gửi token trong header hoặc request parameter; browser không tự thêm giá trị này vào request cross-site như cách nó tự gửi cookie.

## 2. CSRF, authentication và authorization khác nhau

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Authentication | Ai đang gửi request? | Session cookie xác định phiên đăng nhập |
| Authorization | Người đó có quyền làm việc này không? | User có quyền hủy đơn hàng |
| CSRF protection | Request có mang token hợp lệ của ứng dụng không? | Header X-XSRF-TOKEN khớp token server lưu |

Một request POST có thể:

- Có session cookie hợp lệ nhưng thiếu CSRF token: bị từ chối.
- Có CSRF token hợp lệ nhưng session hết hạn: không được xác thực.
- Có session và CSRF token hợp lệ nhưng user thiếu quyền: bị từ chối bởi authorization rule.
- Có đủ cả ba điều kiện: được chuyển đến controller để xử lý nghiệp vụ.

Không nên tắt CSRF chỉ vì API dùng JSON, vì browser vẫn có thể tự gửi cookie trong một số kiểu request. Việc tắt CSRF chỉ phù hợp khi đã thiết kế và xác minh API không dùng credentials tự động của browser, chẳng hạn một resource server stateless chỉ nhận bearer token qua header do client chủ động đặt.

## 3. Những HTTP method nào cần CSRF token?

Spring Security mặc định bảo vệ các HTTP method không an toàn, điển hình là POST, PUT, PATCH và DELETE. Các method an toàn như GET, HEAD, OPTIONS và TRACE không được dùng để thay đổi trạng thái nghiệp vụ.

| Method | Mục đích thông thường | CSRF |
| --- | --- | --- |
| GET | Đọc tài nguyên | Không yêu cầu token theo matcher mặc định |
| HEAD | Đọc metadata | Không yêu cầu token theo matcher mặc định |
| OPTIONS | Khám phá khả năng HTTP/CORS | Không yêu cầu token theo matcher mặc định |
| POST | Tạo tài nguyên hoặc thực hiện hành động | Yêu cầu token |
| PUT | Thay thế tài nguyên | Yêu cầu token |
| PATCH | Cập nhật một phần tài nguyên | Yêu cầu token |
| DELETE | Xóa tài nguyên | Yêu cầu token |

Không tạo endpoint GET có tác dụng xóa, thanh toán, hủy đơn hoặc thay đổi quyền. Nếu một thao tác làm thay đổi trạng thái, hãy biểu diễn nó bằng method không an toàn và để CSRF filter kiểm tra.

Try it out không có cơ chế miễn trừ CSRF. Khi người dùng bấm Execute cho POST, PUT, PATCH hoặc DELETE, Swagger UI gửi request thật đến API. Request đó cần session, quyền nghiệp vụ và CSRF token hợp lệ giống request từ frontend khác.

## 4. Session cookie và CSRF cookie là hai cookie khác nhau

Một ứng dụng dùng cookie session thường có ít nhất hai loại cookie:

| Cookie | Chức năng | JavaScript có nên đọc? |
| --- | --- | --- |
| JSESSIONID hoặc cookie session tùy ứng dụng | Nhận diện phiên đăng nhập | Không; giữ HttpOnly |
| XSRF-TOKEN | Cung cấp token để client gửi lại trong header | Có thể cần đọc nếu dùng cookie-to-header |

Session cookie nên có các thuộc tính phù hợp:

- **HttpOnly** để JavaScript không đọc được session ID.
- **Secure** để chỉ gửi trên kết nối HTTPS.
- **SameSite** theo kiến trúc, thường dùng Lax hoặc Strict nếu phù hợp.
- **Path** và **Domain** giới hạn ở phạm vi cần thiết.
- Thời hạn cookie và thời hạn session được quản lý nhất quán.

Nếu Swagger UI dùng mô hình cookie-to-header, cookie CSRF có thể cần HttpOnly=false để JavaScript đọc giá trị token rồi đặt vào header. Điều đó không có nghĩa phải tắt HttpOnly cho cookie session. Chỉ cookie CSRF được đọc bởi client mới cần khả năng đọc; session cookie vẫn phải được giữ kín.

## 5. Synchronizer token và cookie-to-header

Hai mô hình phổ biến:

**Synchronizer Token Pattern:** server lưu CSRF token trong session. Ứng dụng nhận token qua HTML, JSON hoặc response header, rồi gửi lại token trong header hoặc form parameter. Server so sánh token nhận được với token lưu trong session.

**Cookie-to-header Pattern:** server đặt CSRF token vào cookie có thể đọc được bởi JavaScript, ví dụ XSRF-TOKEN. Client đọc cookie đó và gửi giá trị tương ứng trong header như X-XSRF-TOKEN. Server so sánh giá trị header với token mong đợi theo cấu hình repository.

Luồng cookie-to-header:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant UI as Swagger UI
    participant API as Spring Boot + Spring Security

    User->>UI: Mở tài liệu API
    UI->>API: GET /swagger-ui hoặc /v3/api-docs
    API-->>UI: Set-Cookie: SESSION; Set-Cookie: XSRF-TOKEN
    User->>UI: Execute một request POST
    UI->>UI: Đọc XSRF-TOKEN từ cookie
    UI->>API: POST /api/orders + Cookie + X-XSRF-TOKEN
    API->>API: Xác thực session và kiểm tra CSRF token
    API->>API: Kiểm tra quyền nghiệp vụ
    API-->>UI: 2xx hoặc lỗi phù hợp
~~~

Cookie được browser tự gửi. Header CSRF được client chủ động thêm. Sự khác biệt này giúp server phân biệt request có thể bị browser gửi tự động với request được tạo từ ứng dụng đã nhận token.

Không dùng session ID làm CSRF token. Cũng không chỉ kiểm tra cookie CSRF mà bỏ qua header hoặc request parameter: browser tự gửi cookie nên kẻ tấn công có thể kích hoạt việc gửi cookie trong request giả mạo.

## 6. Cấu hình CSRF trong Spring Security

Spring Security bật CSRF protection mặc định cho các unsafe HTTP methods. Mặc định, HttpSessionCsrfTokenRepository lưu token trong HttpSession. Nếu muốn Swagger UI đọc token từ cookie và tự gửi header, có thể dùng CookieCsrfTokenRepository.

Repository mặc định dùng:

- Cookie: XSRF-TOKEN.
- Request header: X-XSRF-TOKEN.
- Request parameter dự phòng: _csrf.

Các tên này khớp với cấu hình mặc định của springdoc Swagger UI CSRF support.

### Spring Security 7: cấu hình SPA helper

Với Spring Security 7, có thể dùng helper spa() để cấu hình cookie repository và request handler phù hợp với ứng dụng JavaScript:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .csrf(csrf -> csrf.spa())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/swagger-ui/**", "/v3/api-docs/**")
                    .authenticated()
                .requestMatchers("/api/**")
                    .authenticated()
                .anyRequest()
                    .permitAll()
            )
            .build();
    }
}
~~~

Đoạn cấu hình minh họa chính sách yêu cầu đăng nhập cho tài liệu và API; thay đổi matcher theo ứng dụng. Phương thức csrf.spa() có từ Spring Security 7.0. Nó xử lý các khác biệt của SPA như cookie token, request handler và token được làm mới sau xác thực hoặc logout.

### Spring Security 6: CookieCsrfTokenRepository và request handler

Với Spring Security 6, có thể bắt đầu bằng CookieCsrfTokenRepository.withHttpOnlyFalse() để client đọc cookie CSRF:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .csrf(csrf -> csrf
                .csrfTokenRepository(
                    CookieCsrfTokenRepository.withHttpOnlyFalse()
                )
            )
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/swagger-ui/**", "/v3/api-docs/**")
                    .authenticated()
                .requestMatchers("/api/**")
                    .authenticated()
                .anyRequest()
                    .permitAll()
            )
            .build();
    }
}
~~~

Đây là phần cấu hình repository, chưa phải toàn bộ cấu hình SPA hoàn chỉnh cho mọi ứng dụng Spring Security 6. Từ Spring Security 6, CSRF token được tải trì hoãn và có BREACH protection bằng XOR mặc định. Với SPA đọc token cookie rồi gửi giá trị raw trong header, cần cấu hình CsrfTokenRequestHandler theo hướng dẫn SPA chính thức để giải mã/đối chiếu đúng token và bảo đảm token mới được phát sau đăng nhập hoặc logout. Không bỏ request handler mặc định chỉ để làm ví dụ chạy được nếu chưa đánh giá ảnh hưởng BREACH.

Nếu dùng Spring Security 6, hãy lấy lớp SpaCsrfTokenRequestHandler theo ví dụ chính thức của đúng minor version trong tài liệu Spring Security đang dùng. Cấu hình đó kết hợp XorCsrfTokenRequestAttributeHandler với CsrfTokenRequestAttributeHandler để xử lý header và request parameter phù hợp.

## 7. Bật hỗ trợ CSRF tích hợp trong springdoc Swagger UI

Springdoc có các thuộc tính riêng để Swagger UI tự đọc CSRF token và gửi vào request. Với tên cookie/header mặc định của Spring Security, cấu hình:

~~~yaml
springdoc:
  swagger-ui:
    csrf:
      enabled: true
      cookie-name: XSRF-TOKEN
      header-name: X-XSRF-TOKEN
      use-local-storage: false
      use-session-storage: false
~~~

Hoặc dùng application.properties:

~~~properties
springdoc.swagger-ui.csrf.enabled=true
springdoc.swagger-ui.csrf.cookie-name=XSRF-TOKEN
springdoc.swagger-ui.csrf.header-name=X-XSRF-TOKEN
springdoc.swagger-ui.csrf.use-local-storage=false
springdoc.swagger-ui.csrf.use-session-storage=false
~~~

Ý nghĩa:

| Thuộc tính | Tác dụng |
| --- | --- |
| csrf.enabled | Bật hỗ trợ gửi CSRF token trong request từ Swagger UI |
| csrf.cookie-name | Tên cookie chứa token mà UI cần đọc |
| csrf.header-name | Tên header chứa token gửi về server |
| csrf.use-local-storage | Lấy token từ Local Storage nếu ứng dụng lưu ở đó |
| csrf.use-session-storage | Lấy token từ Session Storage nếu ứng dụng lưu ở đó |

Theo Swagger UI Properties Reference, CSRF support mặc định tắt; cookie mặc định là XSRF-TOKEN và header mặc định là X-XSRF-TOKEN. Tính năng này được springdoc bổ sung từ dòng phát hành 1.4.4. Kiểm tra phiên bản springdoc thực tế trước khi sử dụng các thuộc tính này.

Với tên cookie/header chuẩn, springdoc có thể tự thêm token cho các request Try it out. Nếu hệ thống dùng tên khác hoặc token nằm ở nơi khác, cấu hình cookie-name/header-name hoặc dùng request interceptor tùy chỉnh.

## 8. Request interceptor cho CSRF token không theo tên chuẩn

Swagger UI hỗ trợ requestInterceptor để chỉnh sửa request trước khi gửi. Có thể dùng khi backend sử dụng tên cookie hoặc header riêng. Ví dụ sau minh họa cách đọc cookie:

~~~javascript
function readCookie(name) {
    const prefix = name + "=";
    const item = document.cookie
        .split("; ")
        .find(value => value.startsWith(prefix));

    return item ? decodeURIComponent(item.substring(prefix.length)) : null;
}

function csrfRequestInterceptor(request) {
    const apiOrigin = window.location.origin;
    const requestUrl = new URL(request.url, apiOrigin);

    // Chỉ gắn token cho API cùng origin đã được tin cậy.
    if (requestUrl.origin === apiOrigin &&
        requestUrl.pathname.startsWith("/api/")) {
        const token = readCookie("APP-XSRF");
        if (token) {
            request.headers["X-APP-CSRF"] = token;
        }
    }

    return request;
}
~~~

Interceptor phải giới hạn phạm vi URL được phép nhận token. Không gắn CSRF token vào mọi request bất kể đích đến, vì Swagger UI có thể tải OpenAPI definition hoặc gọi OAuth endpoint từ host khác. Nếu token bị gửi đến domain ngoài, nó có thể bị lộ.

Với springdoc, request interceptor tùy chỉnh thường cần được đưa vào Swagger UI qua cấu hình hoặc resource transformer tùy cách ứng dụng đóng gói giao diện. Nếu tên chuẩn đã đáp ứng nhu cầu, ưu tiên thuộc tính CSRF tích hợp để tránh tự duy trì JavaScript.

## 9. Bảo vệ cookie session và cookie CSRF

Session cookie và CSRF cookie có yêu cầu khác nhau:

~~~http
Set-Cookie: JSESSIONID=...; Path=/; Secure; HttpOnly; SameSite=Lax
Set-Cookie: XSRF-TOKEN=...; Path=/; Secure; SameSite=Lax
~~~

Trong mô hình cookie-to-header, cookie CSRF cần đọc được từ JavaScript. Vì vậy, XSRF-TOKEN thường không có HttpOnly. Session cookie vẫn có HttpOnly để ngăn script đọc session ID.

Không đặt CSRF token trong URL, query parameter có thể xuất hiện trong log hoặc liên kết chia sẻ. Không ghi session ID hoặc token vào log. Token phải đủ ngẫu nhiên và được server xác minh theo session hoặc cơ chế ký tương ứng.

SameSite=Lax hoặc Strict có thể giảm một số request cross-site mang cookie, nhưng nên xem là lớp phòng vệ bổ sung. Không dựa riêng vào SameSite nếu ứng dụng có nhiều subdomain, luồng tích hợp hoặc browser không áp dụng chính sách giống nhau.

## 10. CORS khi Swagger UI và API khác origin

Đơn giản nhất là phục vụ Swagger UI và API từ cùng origin. Nếu tài liệu chạy tại https://docs.example.com còn API chạy tại https://api.example.com, request là cross-origin dù hai host có thể cùng site.

Khi gửi session cookie cross-origin, cần đồng thời:

- Swagger UI bật credentials cho request nếu cấu hình của nó yêu cầu.
- Cookie có Domain/Path/Secure/SameSite phù hợp.
- Server cho phép origin tài liệu cụ thể.
- CORS cho phép credentials.
- CORS cho phép custom header CSRF như X-XSRF-TOKEN.

Ví dụ cấu hình Spring MVC:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class ApiCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://docs.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
            .allowedHeaders(
                "Content-Type",
                "X-XSRF-TOKEN",
                "X-Request-Id"
            )
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

Không dùng allowedOrigins("*") cùng credentials. Khi dùng Spring Security, bảo đảm CORS được xử lý đúng trong filter chain và OPTIONS preflight không bị yêu cầu session/CSRF như request thay đổi trạng thái.

CORS không thay thế CSRF. CORS chủ yếu quyết định browser có cho JavaScript đọc response cross-origin và gửi một số request hay không. Server vẫn phải xác minh CSRF token ở request thay đổi trạng thái.

## 11. Mô tả yêu cầu CSRF trong OpenAPI

CSRF token không phải access token và không phải security scheme xác thực người dùng. Nó là giá trị chống giả mạo request gắn với session hoặc cơ chế token của server.

Với API được gọi bởi nhiều client, tài liệu nên giải thích:

- API dùng session cookie nào.
- Cách lấy CSRF token trước khi gửi request thay đổi trạng thái.
- Header hoặc request parameter cần gửi.
- Khi nào token hết hạn hoặc cần lấy lại, ví dụ sau đăng nhập/logout.
- Phản hồi khi token thiếu hoặc không hợp lệ.

Có thể mô tả trên operation bằng @Operation:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @Operation(
        summary = "Tạo đơn hàng",
        description = """
            Yêu cầu session cookie hợp lệ và CSRF token trong header
            X-XSRF-TOKEN. Swagger UI được cấu hình để tự gửi token
            lấy từ cookie XSRF-TOKEN.
            """
    )
    @PostMapping("/api/orders")
    OrderView createOrder(@RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }
}
~~~

Nếu tài liệu dành cho client tích hợp bên ngoài, có thể mô tả header CSRF bằng Parameter Object hoặc component parameter dùng lại. Tuy nhiên, với Swagger UI tích hợp CSRF, không nên buộc người dùng nhập thủ công cùng token nếu UI đã tự chèn header. Cần tránh khai báo trùng hoặc tạo trường nhập gây nhầm lẫn.

Ví dụ response lỗi:

~~~yaml
responses:
  '403':
    description: Thiếu hoặc không hợp lệ CSRF token, hoặc người dùng không có quyền
    content:
      application/problem+json:
        schema:
          $ref: '#/components/schemas/ProblemDetail'
~~~

Nếu API muốn phân biệt lỗi CSRF với lỗi phân quyền, hãy định nghĩa mã lỗi ứng dụng hoặc response detail phù hợp. Mã HTTP 403 có thể được dùng cho nhiều loại AccessDeniedException nên client không nên chỉ dựa vào status để suy đoán nguyên nhân.

## 12. Try it out có thể thực hiện thay đổi thật

Try it out gửi request đến backend đang được cấu hình trong OpenAPI. Nếu người dùng chọn production server và bấm Execute trên POST, PUT, PATCH hoặc DELETE, dữ liệu production có thể bị thay đổi thật.

Các biện pháp giảm rủi ro khi cung cấp Swagger UI:

- Cung cấp môi trường sandbox hoặc test tenant cho người dùng thử.
- Dùng tài khoản thử nghiệm có quyền tối thiểu.
- Giới hạn nhóm người được truy cập tài liệu và API.
- Dùng supported-submit-methods để tắt các method không muốn cho thử trên giao diện.
- Đặt mô tả rõ cho operation phá hủy dữ liệu, thanh toán hoặc gửi thông báo.
- Giữ authorization và CSRF protection hoạt động giống request thật.

Ví dụ chỉ cho phép Try it out với GET:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - head
~~~

Giá trị này chỉ điều khiển nút Try it out trong Swagger UI. Nó không khóa POST/PUT/PATCH/DELETE ở server và không thay thế Spring Security. Người dùng vẫn có thể gọi endpoint bằng curl hoặc HTTP client khác nếu họ có quyền.

## 13. Làm mới CSRF token sau đăng nhập và logout

Spring Security có thể xóa CSRF token hiện tại sau khi xác thực thành công hoặc logout thành công. Với SPA sử dụng cookie repository, client cần lấy token mới trước request unsafe tiếp theo.

Điều này thường biểu hiện như sau:

1. Người dùng đăng nhập thành công.
2. Session được tạo hoặc session ID được đổi.
3. CSRF token cũ bị xóa để tránh gắn token trước xác thực với phiên mới.
4. Client cần phát sinh request lấy token mới.
5. Request POST/PUT/PATCH/DELETE tiếp theo gửi token mới trong header.

Nếu Swagger UI vừa đăng nhập xong mà request đầu tiên trả 403, hãy kiểm tra cookie XSRF-TOKEN có được phát lại hay không. Tải lại tài liệu hoặc gọi endpoint bootstrap CSRF theo thiết kế của ứng dụng rồi thử lại.

Với Spring Security 7, csrf.spa() hỗ trợ các chi tiết làm mới token của SPA. Với Spring Security 6, cần thực hiện theo cấu hình request handler và cơ chế phát token mới được tài liệu phiên bản đó hướng dẫn.

## 14. Kiểm thử CSRF bằng MockMvc

Spring Security Test cung cấp request post processor csrf() để kiểm tra endpoint có yêu cầu CSRF token hay không.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderCsrfTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void postWithoutCsrfTokenIsRejected() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(user("tester").roles("USER"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productId":"P-100","quantity":1}
                    """))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfTokenCanReachAuthorizationAndController()
            throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(user("tester").roles("USER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productId":"P-100","quantity":1}
                    """))
            .andExpect(status().isCreated());
    }
}
~~~

Đoạn kiểm thử giả định endpoint trả 201 khi user có quyền và payload hợp lệ. Nếu controller trả 200 hoặc cần authority khác, điều chỉnh assertion theo hợp đồng thực tế.

csrf() tạo token phù hợp cho kiểm thử mặc định. Nếu ứng dụng dùng CookieCsrfTokenRepository, nên bổ sung integration test xác minh cookie token được phát và request gửi header đúng tên, đồng thời kiểm tra token cũ sau logout không còn được chấp nhận. Kiểm thử với MockMvc không thay thế việc kiểm tra cookie behavior trong browser thật.

## 15. Kiểm thử Try it out trong trình duyệt

Sau khi cấu hình Spring Security và springdoc:

1. Mở Swagger UI trên origin đã được phép.
2. Đăng nhập bằng tài khoản thử nghiệm.
3. Trong Developer Tools, mở tab Network và tải lại trang tài liệu.
4. Kiểm tra response có Set-Cookie cho session và CSRF token.
5. Kiểm tra cookie session có HttpOnly, Secure và SameSite đúng chính sách.
6. Kiểm tra cookie CSRF có thể đọc được nếu dùng cookie-to-header.
7. Chọn một operation POST hoặc PATCH và bấm Try it out.
8. Kiểm tra request có session cookie và header X-XSRF-TOKEN.
9. Kiểm tra response thành công và dữ liệu chỉ thay đổi trong môi trường thử nghiệm.
10. Thử gửi lại request khi bỏ header CSRF hoặc dùng token cũ; server phải từ chối.

Nếu Swagger UI và API khác origin, kiểm tra thêm OPTIONS preflight, Access-Control-Allow-Origin, Access-Control-Allow-Credentials và Access-Control-Allow-Headers.

## 16. Lỗi thường gặp

**POST từ Swagger UI trả 403 nhưng GET hoạt động.** Đây thường là dấu hiệu request unsafe thiếu CSRF token hoặc token không khớp session. Kiểm tra cookie CSRF và header trong Network panel.

**Đã bật springdoc CSRF nhưng header không xuất hiện.** Kiểm tra springdoc.swagger-ui.csrf.enabled, cookie name, header name và phiên bản springdoc. Đảm bảo browser thực sự nhận cookie CSRF.

**Cookie session có nhưng cookie XSRF-TOKEN không có.** Kiểm tra Spring Security có dùng CookieCsrfTokenRepository, token có được materialize trong response và request handler có phù hợp phiên bản hay không.

**Cookie XSRF-TOKEN có nhưng JavaScript không đọc được.** Kiểm tra thuộc tính HttpOnly của cookie CSRF. Với cookie-to-header, cookie CSRF cần đọc được; session cookie vẫn phải HttpOnly.

**Spring Security 6 trả 403 dù header chứa đúng giá trị cookie.** Kiểm tra SPA request handler và BREACH encoding. Token cookie có thể là raw token trong khi request handler mặc định mong đợi giá trị được encode theo cơ chế XOR.

**Đăng nhập xong request đầu tiên bị 403.** CSRF token có thể đã bị xóa sau authentication success. Lấy token mới trước khi gửi request unsafe.

**Logout không hoạt động từ Try it out.** Logout qua POST thường cũng cần CSRF token. Không chuyển logout thành GET để né CSRF.

**CORS preflight thất bại.** Cho phép origin tài liệu cụ thể, method cần thiết và header CSRF. Nếu dùng credentials, không dùng wildcard origin.

**Tắt CSRF làm Try it out hoạt động.** Đây không phải cách sửa phù hợp cho API dùng session cookie. Khôi phục CSRF và cấu hình luồng token đúng.

**Đã giới hạn method trong Swagger UI nhưng endpoint vẫn bị gọi.** supported-submit-methods chỉ ẩn/khóa thao tác trên giao diện. Dùng Spring Security và kiểm tra quyền ở server để bảo vệ endpoint.

**Token CSRF bị gửi đến host khác.** Kiểm tra request interceptor tùy chỉnh. Chỉ gắn token cho origin và path API tin cậy.

## 17. Checklist triển khai

- [ ] Dùng session cookie có Secure, HttpOnly và SameSite phù hợp.
- [ ] Giữ CSRF protection bật cho API xác thực bằng cookie.
- [ ] Không dùng GET cho thao tác thay đổi trạng thái.
- [ ] Chọn HttpSessionCsrfTokenRepository hoặc CookieCsrfTokenRepository theo kiến trúc.
- [ ] Nếu dùng cookie-to-header, chỉ để cookie CSRF có thể đọc được; giữ session cookie HttpOnly.
- [ ] Với Spring Security 7, cân nhắc csrf.spa() cho SPA.
- [ ] Với Spring Security 6, cấu hình request handler theo hướng dẫn SPA/BREACH của đúng phiên bản.
- [ ] Bật springdoc.swagger-ui.csrf.enabled=true.
- [ ] Đồng bộ cookie name và header name giữa Spring Security và springdoc.
- [ ] Làm mới token sau đăng nhập/logout.
- [ ] Nếu khác origin, cấu hình CORS credentials và header CSRF cụ thể.
- [ ] Giới hạn người truy cập Swagger UI và dùng môi trường thử nghiệm.
- [ ] Không coi supported-submit-methods là cơ chế bảo vệ server.
- [ ] Kiểm thử request thiếu token, token cũ và token hợp lệ.
- [ ] Quan sát Network panel để xác nhận cookie/header thực tế.

## 18. Kết luận

Session cookie giúp browser duy trì phiên đăng nhập, nhưng vì browser tự gửi cookie nên request thay đổi trạng thái cần CSRF protection. Spring Security cung cấp token repository và request handler; springdoc cung cấp cấu hình để Swagger UI đọc CSRF cookie và gửi token trong header khi Try it out. Hãy giữ session cookie HttpOnly, chỉ cho cookie CSRF đọc được khi cần cookie-to-header, xử lý đúng khác biệt SPA/BREACH giữa Spring Security 6 và 7, và kiểm tra request thực tế trong browser. Try it out luôn gọi API thật, vì vậy cần bảo vệ server và giới hạn môi trường kiểm thử như mọi client khác.

## 19. Nguồn tham khảo

- [Spring Security — Cross Site Request Forgery](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF filter, token repositories, CookieCsrfTokenRepository, BREACH và SPA integration.
- [Springdoc — Swagger UI Properties Reference](https://springdoc.org/ui-properties.html): các thuộc tính springdoc.swagger-ui.csrf.enabled, cookie-name, header-name và storage options.
- [Springdoc — FAQ, CSRF support](https://springdoc.org/faq.html): bật CSRF support trong Swagger UI và dùng request interceptor cho token không theo tên chuẩn.
- [Swagger UI — Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): requestInterceptor và request/response interception.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer token, signed double-submit cookie, SameSite và phòng vệ nhiều lớp.
