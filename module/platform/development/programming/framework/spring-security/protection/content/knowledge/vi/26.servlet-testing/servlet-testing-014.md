# Giới hạn của kiểm thử giả lập với hành vi trình duyệt hoặc container

## 1. Vì sao kiểm thử MockMvc đạt vẫn có thể xảy ra lỗi bảo mật?

Trong chương **Kiểm thử Servlet** thuộc module **SPRING_SECURITY_HTTP_PROTECTION**, người học dùng Spring Security để bảo vệ ứng dụng web ở nhiều lớp: CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và session. Việc dùng **MockMvc** cùng **spring-security-test** giúp xác minh nhanh những quy tắc của Spring Security Servlet, nhưng cần biết chính xác mô hình giả lập bắt đầu và kết thúc ở đâu.

Ví dụ, kiểm thử có thể xác nhận phản hồi chứa:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: script-src 'self'
Set-Cookie: SESSION=abc; Secure; HttpOnly; SameSite=Lax; Path=/
~~~

Tuy nhiên, ba header này chỉ **mô tả chính sách mong muốn**. MockMvc không tạo kết nối TLS thật, không vận hành bộ nhớ HSTS của trình duyệt, không thực thi CSP bằng JavaScript engine và không tự quyết định cookie có được trình duyệt chấp nhận, lưu hoặc gửi lại hay không. Chúng ta phải phân biệt:

- **Cấu hình đúng:** framework phát status, header và quyết định ủy quyền như dự kiến.
- **Tích hợp đúng:** ứng dụng và Servlet container xử lý request, cookie, encoding, session và các bộ lọc đúng qua socket thật.
- **Hành vi người dùng được bảo vệ:** trình duyệt áp dụng chính sách theo origin, cookie, CORS, CSP, HSTS, điều hướng và trạng thái frontend.
- **Triển khai đúng:** TLS, reverse proxy, CDN, session store phân tán và host/port công khai không phá vỡ chính sách đã kiểm thử.

Các tầng bổ sung bằng chứng cho nhau. Đạt một bài MockMvc là kết quả có giá trị về **quy tắc ở tầng Servlet/Spring Security**; chưa phải bằng chứng rằng toàn bộ đường đi từ trình duyệt đến hệ thống vận hành an toàn.

### Mục tiêu sau bài học

Người học có thể:

1. Xác định MockMvc đang mô phỏng thành phần nào và đang bỏ qua thành phần nào.
2. Tránh các trường hợp kết quả kiểm thử đạt giả khi dùng with(user()), with(csrf()), secure(true), cookie giả lập hoặc Origin header.
3. Chọn kiểm thử MockMvc, embedded Servlet container, HTTP client, reverse proxy và trình duyệt theo cơ chế cần chứng minh.
4. Thiết kế ma trận kiểm thử tích hợp cho CSRF, CORS, cookie, CSP, HSTS, redirect, session, HTTP firewall và các quy tắc security headers.
5. Chẩn đoán lỗi chỉ xuất hiện trong production dù kiểm thử giả lập đã đạt.

## 2. MockMvc thực sự chạy những gì?

**MockMvc** gửi request được dựng trong bộ nhớ vào pipeline của Spring MVC bằng các đối tượng như MockHttpServletRequest và MockHttpServletResponse. Khi được cấu hình đúng, request đi qua các filter đã đăng ký, bao gồm **springSecurityFilterChain**, rồi đến DispatcherServlet và controller.

~~~mermaid
flowchart TD
    A["MockMvc request builder"] --> B["MockHttpServletRequest"]
    B --> C["Filter chain được gắn vào MockMvc"]
    C --> D["Spring Security FilterChainProxy"]
    D --> E["DispatcherServlet và Controller"]
    E --> F["MockHttpServletResponse và assertions"]
    G["Trình duyệt: cookie jar, HSTS, CSP, CORS"] -. "Không được chạy" .-> B
    H["Socket, TLS, reverse proxy, Servlet container thật"] -. "Không được chạy" .-> B
~~~

Phần có thể được kiểm tra rất tốt khi cấu hình đúng gồm:

- Các matcher và thứ tự **SecurityFilterChain**.
- Kết quả xác thực, phân quyền cho request giả lập.
- Filter CSRF từ chối token thiếu hoặc sai và cho phép token hợp lệ.
- Logic CORS của filter khi có preflight/Origin đầu vào tương ứng.
- Các header do Spring Security sinh ra: HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy và cache headers.
- Kết quả redirect, Location, status, body và nhiều tương tác với HttpSession giả lập.
- Một phần kiểm tra HTTP firewall tùy cách request được dựng và cấu hình filter.

Những thành phần **không tự chạy** gồm:

- Trình duyệt thực thi script, CSS, CSP, CORS, điều hướng, iframe, mixed content, bfcache và service worker.
- Cookie jar của trình duyệt với luật Domain, Path, Secure, SameSite, expiry và cookie phân vùng.
- TLS handshake, xác minh chứng chỉ, cổng mạng, HTTP/2 hoặc HTTP/3.
- Servlet container thật xử lý URL encoding, header, giới hạn kích thước, session cookie, async và vòng đời kết nối.
- Reverse proxy/CDN xử lý Forwarded, X-Forwarded-Proto, Host, redirect, response headers và cache.
- Kho phiên hay token ngoài tiến trình trừ khi được khởi tạo thật trong bài test.

### Ba cách khởi tạo MockMvc và hệ quả

| Cách dùng | Thành phần thường có | Điểm cần lưu ý |
|---|---|---|
| MockMvcBuilders.standaloneSetup(controller) | Controller, phần MVC được dựng cho test | Không tự có toàn bộ cấu hình Spring Security hoặc mọi filter ứng dụng |
| MockMvcBuilders.webAppContextSetup(context).apply(springSecurity()) | WebApplicationContext và tích hợp FilterChainProxy | Phản ánh cấu hình ứng dụng tốt hơn, nhưng vẫn là request/response giả lập |
| Spring Boot @SpringBootTest + @AutoConfigureMockMvc | ApplicationContext và MockMvc được Boot cấu hình | Có thể kiểm thử filter chain thật của ứng dụng; vẫn không mở socket hoặc chạy trình duyệt |

Với slice test như **@WebMvcTest**, phạm vi bean và cấu hình cũng có thể khác ứng dụng đầy đủ. Nếu test được tạo với **addFilters=false**, các kiểm tra Spring Security filter có thể bị vô hiệu. Luôn kiểm tra test có thật sự chạy filter hay không trước khi diễn giải kết quả.

## 3. Minh họa bằng một ứng dụng Servlet nhỏ

Để đánh giá đúng giới hạn kiểm thử, trước hết xây dựng một ví dụ có hành vi rõ ràng. Endpoint công khai dùng để đo security headers; endpoint thay đổi dữ liệu đòi hỏi xác thực và CSRF khi sử dụng session/browser login. Ví dụ hướng tới Spring Security Servlet với cấu hình lambda.

~~~java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ExampleApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExampleApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/ping").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());
        // CSRF và các security headers mặc định vẫn được giữ nguyên.
        return http.build();
    }

    @RestController
    static class ExampleController {
        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @PostMapping("/private/update")
        ResponseEntity<Void> update() {
            return ResponseEntity.noContent().build();
        }
    }
}
~~~

Khi dựng MockMvc với filter chain đã được kết nối, ta có thể thử quy tắc CSRF và HSTS:

~~~java
package example.security;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ServletSecurityMockTest {

    @Autowired
    MockMvc mvc;

    @Test
    void rejectsPostWithoutCsrfAndAllowsValidCsrf() throws Exception {
        mvc.perform(post("/private/update").with(user("alice")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/private/update")
                .with(user("alice"))
                .with(csrf()))
            .andExpect(status().isNoContent());
    }

    @Test
    void secureRequestReceivesHsts() throws Exception {
        mvc.perform(get("/public/ping").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Strict-Transport-Security",
                containsString("max-age=")
            ));
    }

    @Test
    void insecureRequestDoesNotReceiveHsts() throws Exception {
        mvc.perform(get("/public/ping").secure(false))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                "Strict-Transport-Security"
            ));
    }
}
~~~

Các kiểm thử này đưa ra ba nhận định hợp lệ:

1. Filter CSRF đang chặn POST không có CSRF token theo cấu hình ví dụ.
2. Request được gắn Authentication giả lập và CSRF token hợp lệ qua test helper có thể được xử lý.
3. Spring Security HSTS header writer đang ghi header khi request được xem là secure, và không ghi HSTS trên request insecure trong cấu hình mặc định.

Nhưng các test **không chứng minh** rằng người dùng có thể lấy CSRF token thật sau login, cookie được browser lưu, token được làm mới đúng khi session đổi, chứng chỉ TLS hợp lệ hoặc trình duyệt đã ghi nhớ HSTS. Việc hiểu đúng giới hạn này ngăn kết luận bảo mật vượt quá bằng chứng.

> **Lưu ý phiên bản:** ví dụ dùng API Servlet và Spring Security hiện đại; package hoặc cấu hình khởi tạo test có thể thay đổi theo phiên bản Spring Boot.

## 4. Bẫy số một: giả lập xác thực và CSRF thay cho luồng đăng nhập thật

Các helper như **with(user("alice"))**, **@WithMockUser**, **with(csrf())** và **formLogin()** hữu ích cho từng mục đích khác nhau.

| Công cụ | Điều được giả lập hoặc kiểm tra | Điều chưa được chứng minh |
|---|---|---|
| with(user("alice")) | Gắn Authentication hợp lệ cho request kiểm thử | Xác thực mật khẩu, captcha, MFA, session fixation, cookie phiên |
| @WithMockUser | Thiết lập security context cho test | Đăng nhập thật qua HTTP và lưu session trong trình duyệt |
| with(csrf()) | Thêm CSRF token phù hợp với helper test | Browser nhận token bằng cách nào, có gửi được header/form đúng không |
| with(csrf().useInvalidToken()) | Mô phỏng token sai để kiểm thử từ chối | Cách token sai xuất hiện trong đời thực và phản ứng frontend |
| formLogin() | Gửi request theo endpoint/cơ chế form login của Spring Security Test | Tính đúng đắn của HTML form, JavaScript, cookie jar và navigation của browser |

**Ví dụ false positive:** một test POST dùng with(user("alice")).with(csrf()) nhận 204 nên nhóm phát triển kết luận SPA hoạt động. Trong browser thật, fetch quên gửi header CSRF hoặc cookie session; server trả 403. MockMvc đã **tự đưa vào** những giá trị mà frontend chưa bao giờ gửi.

### Nên phân chia ca kiểm thử CSRF

- **MockMvc:** thiếu CSRF token → 403; token sai → 403; token hợp lệ cùng Authentication → request qua được filter; logout POST cần CSRF khi cấu hình bật.
- **HTTP client qua container:** login thật để nhận session; gọi endpoint nhận CSRF token theo cơ chế ứng dụng; POST với cookie/token được cấp; xác nhận session/token tương ứng hoạt động.
- **Browser E2E:** mở trang login, nhập thông tin, thao tác form/SPA, xác nhận frontend tự gửi token phù hợp và xử lý khi CSRF hết hiệu lực hoặc session hết hạn.

Khi kiểm thử CSRF qua browser, cần nhớ **CORS** và **SameSite** có thể ảnh hưởng request cross-origin nhưng không thay thế cơ chế CSRF theo mô hình session cookie. Một test có token hợp lệ do helper tạo ra không chứng minh tất cả những lớp phối hợp đó đã đúng.

## 5. Bẫy số hai: CORS là chính sách do trình duyệt thực thi

**CORS** hoạt động thông qua phản hồi của server cùng cơ chế kiểm soát đọc response trong trình duyệt. Spring Security có thể xử lý preflight và ghi Access-Control-Allow-Origin, Access-Control-Allow-Methods, Access-Control-Allow-Headers, Access-Control-Allow-Credentials. MockMvc cho phép kiểm tra header và status của preflight, ví dụ:

~~~java
mockMvc.perform(options("/api/orders")
        .header("Origin", "https://frontend.example.test")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers", "content-type"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Access-Control-Allow-Origin",
        "https://frontend.example.test"
    ));
~~~

Test trên giả định ứng dụng **đã cấu hình** CORS để cho phép origin và phương thức/headers tương ứng; nếu ứng dụng không có quy tắc này, status và header mong đợi phải thay đổi. Import options từ MockMvcRequestBuilders.

**Giới hạn:** MockMvc không vận hành trình duyệt, nên nó không tự chặn mã JavaScript đọc một response thiếu Access-Control-Allow-Origin. Một HTTP client thông thường cũng có thể đọc response mà browser sẽ chặn JavaScript. Ngược lại, một browser có thể thực hiện preflight OPTIONS trước POST dù test MockMvc chỉ gọi thẳng POST.

Khi cần bằng chứng CORS hoạt động trong sản phẩm, cần mở frontend ở **origin thật khác origin API**, dùng fetch với mode/credentials đúng thực tế, rồi quan sát Network và kết quả JavaScript. Nên thử cả origin được phép và origin không được phép. Phân biệt lỗi CORS với lỗi DNS, kết nối, TLS, redirect, cookie SameSite hoặc xác thực.

Điều đặc biệt quan trọng là **CORS không phải cơ chế ủy quyền API**. Kẻ gửi request bằng HTTP client không bị chính sách đọc response trong trình duyệt ràng buộc như JavaScript; backend vẫn phải xác thực, phân quyền và kiểm tra CSRF khi cần.

## 6. Bẫy số ba: cookie trong MockMvc không phải cookie jar trình duyệt

Trong MockMvc, có thể tự tạo Cookie hoặc thêm Set-Cookie vào response. Điều này hữu ích để kiểm tra cookie attribute, tên, Path, Domain và điều kiện khi filter/controller ghi cookie.

~~~java
mockMvc.perform(get("/public/ping")
        .cookie(new jakarta.servlet.http.Cookie("SESSION", "example-id")))
    .andExpect(status().isOk());
~~~

Ở ví dụ này, **SESSION** là cookie do test chủ động tạo và gắn vào request. Test không hề chứng minh browser chấp nhận, giữ, gửi hay loại bỏ cookie đó. Cookie kiểu Servlet dùng package jakarta.servlet ở Servlet 6 / Spring Boot 3; dự án Servlet đời cũ có thể dùng javax.servlet.

Những quy tắc quan trọng nằm ngoài việc MockMvc tự động thực thi:

| Thuộc tính/cơ chế | MockMvc có thể kiểm tra | Cần kiểm chứng trong môi trường thật |
|---|---|---|
| Secure | Response chứa attribute Secure | Browser không gửi cookie qua HTTP thông thường; các ngoại lệ localhost cần xem theo browser |
| HttpOnly | Server có phát HttpOnly | JavaScript không đọc được cookie thông qua document.cookie |
| SameSite=Lax/Strict/None | Giá trị Set-Cookie được phát | Browser có gửi cookie theo loại điều hướng hoặc cross-site request không |
| Domain, Path | Attribute được sinh đúng | Cookie thuộc host/path nào, có được gửi đến URL đích hay không |
| Expires, Max-Age | Server phát chính sách thời hạn | Cookie hết hiệu lực trong browser đúng thời điểm |
| Partitioned và chính sách chặn cookie bên thứ ba | Có thể kiểm tra chuỗi header hỗ trợ | Browser hỗ trợ và phân vùng/lọc cookie ra sao |
| Session cookie do container tạo | Cấu hình hoặc response mô phỏng có cookie | Container phát JSESSIONID/SESSION đúng context path, Secure và thuộc tính khác |

**False positive thường gặp:** test MockMvc gửi thẳng cookie SESSION rồi API xác thực thành công, nhưng frontend thực tế truy cập cross-site và browser không gửi cookie vì SameSite, Secure hoặc cấu hình fetch credentials. Cần kiểm tra cookie jar, Network request headers và chính sách browser trên đúng host/origin.

**Đối với session fixation và logout:** test với MockHttpSession có thể xác minh việc gọi invalidate hoặc thay Session ID ở mức framework. Tuy nhiên, kiểm chứng giá trị session ID mới sau login, cookie sau logout, session hết hạn, store Redis và hành vi nhiều tab/máy chủ cần thêm HTTP client có cookie jar hoặc browser.

## 7. Bẫy số bốn: security headers chỉ được quan sát, chưa được thực thi

Các lớp phòng vệ header có hai nửa: **server phát chính sách** và **browser thực thi chính sách**. MockMvc chủ yếu quan sát nửa đầu.

### CSP: header đúng không chứng minh script đã bị chặn

MockMvc có thể xác nhận:

~~~java
mockMvc.perform(get("/public/ping").secure(true))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("script-src")
    ));
~~~

Test trên chỉ hợp lệ khi ứng dụng có **cấu hình CSP tường minh**; Spring Security không tự bật một CSP đầy đủ cho mọi ứng dụng. Ngay cả khi assertion đạt, browser có thể gặp các vấn đề khác:

- Inline script trong HTML không có nonce/hash phù hợp và bị CSP chặn.
- Nonce được server cấp nhưng template render sai; nonce tái sử dụng không phù hợp với thiết kế.
- script-src hoặc connect-src cho phép quá rộng, khiến ứng dụng tải tài nguyên ngoài dự kiến.
- Content-Security-Policy-Report-Only chỉ thu thập vi phạm, **không cưỡng chế chặn** giống header Content-Security-Policy.
- Worker, iframe, font, image hoặc WebSocket chịu tác động bởi directive tương ứng khác với giả định của tác giả.

Cần dùng browser DevTools, CSP violation reports và kịch bản tải script thật để xác minh. Xem console và hành vi giao diện; không kết luận CSP “chống XSS thành công” chỉ từ sự hiện diện của header.

### Clickjacking: X-Frame-Options và frame-ancestors

MockMvc có thể kiểm tra X-Frame-Options: DENY hoặc Content-Security-Policy chứa frame-ancestors. Nhưng để chứng minh trang không bị nhúng, hãy tạo trang khác origin có iframe trỏ tới trang được bảo vệ, sau đó quan sát browser từ chối render. frame-ancestors cần được áp dụng trên **trang bị nhúng**, không phải trên trang cha. Các chính sách và browser cũ có thể xử lý khác nhau.

### HSTS: secure(true) không mở TLS

Kiểm thử MockMvc:

~~~java
mockMvc.perform(get("/public/ping").secure(true))
    .andExpect(header().exists("Strict-Transport-Security"));
~~~

chứng minh Spring Security coi request là secure và ghi HSTS theo cấu hình. Nó **không** chứng minh:

- Domain có certificate hợp lệ và TLS handshake thành công.
- HTTP ở biên mạng được redirect sang HTTPS.
- Trình duyệt đã ghi nhớ max-age hoặc tự nâng cấp URL http://.
- includeSubDomains không làm hỏng các dịch vụ con chưa hỗ trợ HTTPS.
- Reverse proxy chuyển scheme đúng để request.isSecure() phản ánh HTTPS bên ngoài.

Các header như X-Content-Type-Options, Referrer-Policy, Permissions-Policy, Cache-Control có cùng giới hạn: test header là cần thiết, nhưng kết quả chặn MIME sniffing, referrer, API trình duyệt hoặc cache phụ thuộc ngữ cảnh thực thi thật.

## 8. Bẫy số năm: HTTP firewall và Servlet container xử lý request theo các bước khác nhau

Spring Security **StrictHttpFirewall** có thể từ chối những request bất thường như đường dẫn không hợp lệ hoặc chuỗi đã được mã hóa/chuẩn hóa nguy hiểm theo chính sách. Tuy nhiên, request từ mạng đi qua nhiều lớp trước khi tới Spring Security:

~~~mermaid
flowchart LR
    A["Raw HTTP request"] --> B["Proxy / WAF"]
    B --> C["HTTP parser của Servlet container"]
    C --> D["Servlet mapping và URL decoding"]
    D --> E["StrictHttpFirewall"]
    E --> F["SecurityFilterChain / Controller"]
~~~

MockMvc bắt đầu từ MockHttpServletRequest được dựng bằng API, nên một số biến đổi sẽ **không giống** việc container nhận raw bytes qua socket. Ví dụ:

- Container có thể chặn URL sai cú pháp, request line/header quá dài hoặc ký tự không hợp lệ trước khi Spring Security nhận request.
- Reverse proxy có thể chuẩn hóa hoặc giải mã URL, chuyển đổi dấu phân tách, xử lý semicolon/path parameter hoặc loại bỏ header.
- Container có quy tắc với encoded slash, percent-encoding lặp, path traversal và cách ánh xạ servlet; kết quả có thể khác request builder của MockMvc.
- Spring Security có thể từ chối request chỉ sau khi container đã biến đổi đường dẫn; kết luận từ một chuỗi URL dựng bằng mock có thể không phản ánh raw request thật.

**Chiến lược kiểm thử hợp lý:**

1. Dùng MockMvc để kiểm tra matcher và quyết định của StrictHttpFirewall với request mô phỏng có chủ đích.
2. Dùng HTTP client kết nối tới embedded container để xác minh raw request được parser, container và Spring Security xử lý cùng nhau.
3. Khi có proxy/WAF, gửi request qua **cổng công khai** để xác minh chuẩn hóa đường dẫn và status cuối cùng. Ghi lại các giá trị request URI/path mà ứng dụng thực sự nhận.
4. Không chỉ dựa vào status: xem tầng nào từ chối (400 từ container, 403 từ security policy, status tùy firewall/handler), log hợp lệ và tính nhất quán của request path.

Các phép thử này cần được thực hiện trên hệ thống được phép kiểm thử, với input được kiểm soát. Mục tiêu là xác minh cùng một tài nguyên không được diễn giải trái ngược giữa proxy, container và authorization matcher.

## 9. Bẫy số sáu: HTTP session giả lập không tái tạo vòng đời phiên thật

MockHttpSession hữu ích cho test logic dùng session. Nhưng trong deployment thật, phiên còn liên quan cookie, timeout, session store, luồng đồng thời, nhiều node và chính sách bảo mật khi đăng nhập/đăng xuất.

| Tình huống | MockMvc nên kiểm tra | Cần kiểm tra bổ sung |
|---|---|---|
| Session invalidation sau logout | Handler/logout filter gọi hủy session và request sau không được xác thực | HTTP client tái sử dụng cookie cũ phải bị từ chối |
| Session fixation protection | Session authentication strategy của Spring Security | Trình duyệt nhận session ID mới và cookie cũ không mở phiên cũ |
| Session timeout | Logic ứng dụng khi phiên không hợp lệ | Timeout thật trong container/session store, UI và request song song |
| Concurrent sessions | Chính sách giới hạn phiên tại Spring Security | Hai browser/session độc lập, session registry và kho phân tán |
| Spring Session/Redis | Tương tác với repository được khởi tạo trong test | Nhiều node, TTL, xóa session và độ trễ đồng bộ |
| Session cookie attributes | Giá trị có thể quan sát từ response/config | Domain/Path/Secure/HttpOnly/SameSite thực được trình duyệt chấp nhận |
| Remember-me | Logout handler và repository token | Browser còn cookie/token hay tự đăng nhập lại không |

**False positive:** một test dùng with(user("alice")) và kiểm tra endpoint trả 200 không có session thật được phát qua login. Khi session store Redis sai cấu hình hoặc cookie trình duyệt không lưu, sản phẩm vẫn có thể mất đăng nhập trên từng request, dù test vẫn xanh.

Khi cần chứng minh phiên hoạt động qua nhiều request, hãy dùng client có **CookieManager** hoặc browser context duy trì cookie, thực hiện login thật, gọi API, logout rồi thử dùng lại cookie cũ. Nếu ứng dụng nhiều node, lặp qua từng node hoặc load balancer theo cấu hình đã kiểm soát.

## 10. Các giới hạn bổ sung của Servlet container và đường mạng

| Khả năng | MockMvc hữu ích ở mức | Chỉ môi trường thật mới xác minh đầy đủ |
|---|---|---|
| HTTP redirect | Status và Location do ứng dụng sinh | Client theo redirect, cổng và URL công khai, xử lý POST 301/302/307/308 |
| Multipart upload | Controller, validation, filter đối với mock multipart | Parser multipart của container, giới hạn file/part, kích thước, bộ nhớ/đĩa |
| Request body/header limits | Logic kiểm tra sau khi request đến Spring | Giới hạn server/proxy, status 400/413/431, timeout |
| TLS, client certificate | Policy khi request được đánh dấu secure hoặc có certificate giả lập | Certificate thật, cipher/TLS handshake, mTLS và proxy |
| Async request/streaming | Một phần async dispatch, MVC async handling | Kết nối chậm, ngắt kết nối, backpressure, timeout và thread scheduling |
| Encoding và URL normalization | Logic MVC/filter với request được dựng | Raw HTTP parser, encoding kép, path/host canonicalization |
| CDN và cache | Cache-Control, Vary, ETag trong response | Shared cache, service worker, bfcache, invalidation và proxy |
| HTTP version/cookies | Header và API Servlet | HTTP/2/3, SameSite enforcement, nhiều host và browser versions |
| Frontend SPA | JSON/status hợp đồng API | JavaScript state, fetch credentials, nhiều tab, navigation, history |

Một tình huống kinh điển là **server response có Cache-Control: no-store nhưng UI vẫn hiện dữ liệu cũ khi nhấn Back**. MockMvc kiểm tra được header; để phát hiện stale state, phải thử browser history, memory store, bfcache và service worker. Ngược lại, UI có thể xóa hồ sơ cũ nhưng session server vẫn còn hiệu lực; cần kiểm thử reuse cookie/request ở tầng HTTP.

## 11. Thiết kế ba tầng kiểm thử bổ sung nhau

### Tầng A — MockMvc: nhanh, xác minh quy tắc ứng dụng

Dành cho kiểm thử mỗi commit hoặc pull request:

- CSRF thiếu/sai/đúng token và status trả về.
- Quyền truy cập theo vai trò và security matcher.
- Filter chain thực sự được gắn vào MockMvc.
- Header CSP/HSTS/X-Frame-Options/cache, redirect Location.
- CORS preflight và Access-Control-* trên response giả lập.
- Logout handler, session policy và HTTP firewall ở mức dữ liệu MockHttpServletRequest.

Kết quả tầng A xác nhận **logic ứng dụng trong framework**, không nên gắn nhãn “browser validated”.

### Tầng B — Embedded Servlet container: HTTP thực, vẫn có thể tự động hóa

Khởi động ứng dụng trong test bằng server port ngẫu nhiên, gửi request bằng Java HttpClient, REST client hoặc công cụ tương đương qua localhost. Với Spring Boot phiên bản dùng @LocalServerPort từ package org.springframework.boot.test.web.server:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealServletHttpTest {

    @LocalServerPort
    int port;

    @Test
    void respondsThroughRealHttpServer() throws Exception {
        var client = HttpClient.newHttpClient();
        var request = HttpRequest.newBuilder()
            .uri(URI.create("http://localhost:" + port + "/public/ping"))
            .GET()
            .build();

        var response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).isEqualTo("pong");
    }
}
~~~

Test này xác minh request đi qua **HTTP socket và embedded Servlet container**. Nó **không** chứng minh HTTPS/TLS, reverse proxy, CORS browser hoặc các kiểm soát ở edge. Với API/chính sách đặc thù, thêm request qua cookie jar, payload vượt giới hạn, URL được encode, redirect và session. Nếu cần HTTPS, phải bật TLS cho test server và dùng client thực sự xác minh chứng chỉ theo cấu hình kiểm thử.

### Tầng C — Browser và hạ tầng: xác minh hành vi thật

Dùng Playwright, Selenium hoặc trình duyệt được nhóm dự án hỗ trợ; chạy qua URL HTTPS của môi trường tích hợp có TLS/proxy và origin/cookie giống cấu hình sản phẩm. Một kịch bản E2E nên xác minh:

1. Mở ứng dụng qua HTTPS, đăng nhập bằng form/flow thật, xác nhận browser lưu cookie và nhận CSRF token đúng.
2. Thao tác POST từ UI, quan sát CSRF header và session cookie được gửi theo chính sách SameSite/credentials.
3. Kiểm tra console/network: CSP không chặn tài nguyên hợp lệ và có chặn script/iframe bị cấm; CORS cho phép origin hợp lệ và không cho phép đọc ở origin khác.
4. Mở hai tab, logout ở tab A và thử truy cập lại tài nguyên bảo vệ từ tab B; không thấy dữ liệu riêng tư cũ sau refresh/Back.
5. Kiểm tra network: HTTPS certificate hợp lệ, phản hồi HTTPS có HSTS, HTTP công khai redirect đúng URL, không xảy ra redirect loop.

Các bài kiểm thử browser cần tài khoản và dữ liệu test riêng, cùng tiêu chí rõ ràng cho mỗi hành động. Tránh chỉ kiểm tra “màn hình hiển thị đúng” mà bỏ qua status bảo mật của request. Khi test bị lỗi, lưu network trace, console messages và response headers để đối chiếu với MockMvc.

~~~mermaid
flowchart TD
    A["Một quy tắc bảo mật cần chứng minh"] --> B{"Cơ chế nằm ở đâu?"}
    B -->|"Filter / Controller"| C["MockMvc + spring-security-test"]
    B -->|"Servlet parser / session / socket"| D["Embedded container + HTTP client"]
    B -->|"Cookie / CORS / CSP / HSTS"| E["Trình duyệt thật"]
    B -->|"TLS / proxy / CDN / multi-node"| F["Integration qua hạ tầng công khai"]
    C --> G["Tổng hợp bằng chứng"]
    D --> G
    E --> G
    F --> G
~~~

Không cần xây mọi loại test cho mọi endpoint. Chọn mức cao hơn khi cơ chế cần xác minh nằm ngoài phạm vi request giả lập hoặc khi xảy ra sai khác giữa môi trường test và triển khai.

## 12. Ma trận bằng chứng theo lớp phòng vệ

| Cơ chế | Assertion tốt ở MockMvc | Bằng chứng cần thêm | Rủi ro nếu chỉ dùng mock |
|---|---|---|---|
| Authentication | Request giả lập với quyền đúng bị cho phép/từ chối | Form login thật, cookie, MFA, trạng thái frontend | with(user()) che lỗi login/session |
| Authorization | Security matcher, role, 401/403 | Test qua URL/cổng public và routing thực | Proxy rewrite path khiến matcher khác |
| CSRF | Thiếu/sai token bị chặn; token đúng đi qua | Cách browser nhận, xoay vòng và gửi token | Frontend không có token hợp lệ |
| CORS | Preflight và Access-Control-* đúng theo Origin | Cross-origin fetch trong browser | Server trả header nhưng browser vẫn chặn, hoặc API bị hiểu sai là đã có auth |
| Cookies | Set-Cookie được sinh đúng attribute | Browser cookie jar, SameSite, Secure, domain/path | Cookie không được lưu/gửi |
| Session | Session handler và policy | Login/logout với cookie thật; multi-node TTL | Session vẫn tồn tại hoặc biến mất bất ngờ |
| HSTS | Header trên request được gắn secure | HTTPS TLS, trình duyệt HSTS cache, redirect HTTP | Không có HTTPS thật hoặc reverse proxy sai |
| CSP | Directive/nonce trong header và HTML | Browser thực thi script, style, iframe, report | UI hỏng hoặc script trái phép vẫn chạy |
| Clickjacking | X-Frame-Options, frame-ancestors | Trang khác origin thử iframe thực | Header đúng cú pháp nhưng phạm vi không phù hợp |
| HTTP firewall | Request mô phỏng bị từ chối | Raw URL qua container/proxy | Parser/normalization khác nhau |
| Cache | Cache-Control/Pragma/Expires | CDN, service worker, browser Back/bfcache | Nội dung riêng tư vẫn xuất hiện |
| Secure redirect | Status 3xx, Location qua MockMvc | HTTP public, TLS/port/proxy, browser follow | Redirect loop hoặc Location nội bộ |

## 13. Chẩn đoán khi MockMvc đạt nhưng sản phẩm vẫn lỗi

| Hiện tượng thực tế | Tín hiệu test mock có thể đã bỏ qua | Việc cần làm |
|---|---|---|
| SPA luôn bị 403 CSRF dù test POST xanh | with(csrf()) tạo token thay frontend | Quan sát network request và cơ chế cấp CSRF token sau login |
| Login trả 200 nhưng browser không giữ phiên | SameSite, Secure, Domain, credentials | Kiểm tra Set-Cookie, cookie jar và request tiếp theo |
| CORS lỗi trên browser nhưng gọi bằng curl thành công | curl không cưỡng chế CORS | Thử fetch từ origin frontend thật và quan sát preflight |
| CSP chặn script hợp lệ trong production | MockMvc chỉ kiểm tra header tồn tại | Xem console, nonce/hash và CSP directives trên trang thật |
| HTTPS không có HSTS dù .secure(true) test xanh | TLS kết thúc ở proxy, request.isSecure() sai | Đối chiếu Forwarded/X-Forwarded-Proto và response ngoài edge |
| HTTP redirect lặp vô hạn | Scheme/port nhận ở app khác ngoài proxy | Kiểm tra proxy trust và Location theo từng hop |
| URL đã encode lọt vào route khác sau deploy | Container/proxy normalize khác MockMvc | Gửi raw request qua container/proxy, kiểm tra request URI/servlet path |
| Logout trong test hủy session nhưng tab khác còn vào được | Session/token phân tán hoặc cookie khác còn hiệu lực | Kiểm thử bằng hai browser/session và node độc lập |
| Nhấn Back sau logout vẫn thấy hồ sơ | Browser history/bfcache/frontend store | Browser E2E và bảo vệ API bằng session mới |
| Upload quá lớn crash container | MockMultipartFile không giống multipart parser thật | HTTP integration với size limit thật và giám sát tài nguyên |

Khi chẩn đoán, hãy hỏi theo thứ tự: **MockMvc đã giả lập điều kiện nào? Thành phần nào thực thi quy tắc ở production? Request đã đi qua các tầng nào trước khi tới Spring Security? Bằng chứng nào thiếu ở tầng browser/container/proxy?** Trả lời bốn câu này giúp chọn test bổ sung đúng chỗ.

## 14. Bài thực hành: hoàn thiện bộ kiểm thử bảo vệ ứng dụng

### Bối cảnh

Ứng dụng đặt tại https://shop.example.test sử dụng Spring MVC, Spring Security session cookie, form login và CSRF. Frontend là SPA, API được phục vụ qua reverse proxy; hệ thống trả HTML và JSON chứa dữ liệu khách hàng. Nhóm phát triển đã có test MockMvc cho POST có with(user()).with(csrf()), header HSTS, CSP và logout thành công. Tuy vậy, trên trình duyệt thực tế người dùng đôi khi không đăng nhập được khi frontend khác origin và có thể nhìn thấy dữ liệu cũ sau logout.

### Nhiệm vụ

1. **Khoanh vùng bằng chứng đang có:** lập bảng mỗi test MockMvc đang kiểm tra filter/header nào, dữ liệu nào do helper tự tạo, và kết luận nào chưa thể rút ra.
2. **Bổ sung kiểm thử Servlet container:** login qua HTTP client duy trì cookie, POST bằng CSRF token thực, logout và thử dùng lại cookie cũ; kiểm tra session invalidation.
3. **Bổ sung browser E2E:** đăng nhập từ origin frontend thực, quan sát cookie SameSite/Secure, kiểm tra preflight và POST; mở hai tab rồi logout, reload/Back và gọi API bảo vệ.
4. **Bổ sung proxy/TLS:** yêu cầu HTTP công khai có redirect HTTPS đúng host; HTTPS response có HSTS và certificate hợp lệ; xác nhận không có redirect loop.
5. **Bổ sung kiểm thử CSP và cache:** thử tải script hợp lệ/không hợp lệ dưới CSP, kiểm tra browser console; nhấn Back sau logout, bảo đảm store và cache không phục vụ dữ liệu riêng tư cũ.
6. **Ghi lại kết quả:** nêu status/headers ở tầng mock, container và proxy; kèm browser network trace và kết luận từng lớp.

### Tiêu chí chấm

| Mục tiêu | Điều kiện đạt |
|---|---|
| Nắm rõ giả lập | Nêu đúng ít nhất ba helper/đầu vào được MockMvc dựng thay client thật |
| Hiểu CORS/CSRF | Phân biệt CORS browser enforcement với CSRF server validation |
| Kiểm chứng session | Login và logout qua cookie jar thật; session cũ không truy cập được API |
| Kiểm chứng TLS và HSTS | HTTPS hợp lệ, có HSTS; HTTP public redirect đúng URL |
| Kiểm chứng CSP/frontend | Browser thực thi policy; UI không giữ dữ liệu nhạy cảm sau logout |
| Kiểm chứng container/proxy | Ít nhất một kiểm thử phát hiện hành vi parser/forwarded headers khác mock |
| Kết luận có giới hạn | Không diễn giải kết quả MockMvc thành bằng chứng browser hoặc TLS đã an toàn |

**Ghi nhớ:** MockMvc rất phù hợp để kiểm tra nhanh quy tắc Spring Security Servlet. Độ tin cậy của hệ thống đến từ việc ghép **kiểm thử filter**, **kiểm thử request qua container**, **kiểm thử hành vi trình duyệt** và **kiểm thử đường triển khai** theo đúng cơ chế cần bảo vệ. Người học nên xác định ai là bên *thực thi* chính sách trước khi chọn công cụ xác minh.
