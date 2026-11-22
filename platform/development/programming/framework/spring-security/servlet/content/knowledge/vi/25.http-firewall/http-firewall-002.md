# StrictHttpFirewall so với DefaultHttpFirewall trong Spring Security Servlet

## 1. Vì sao HttpFirewall quan trọng?

Trong ứng dụng Java Servlet, một URL có thể được diễn giải theo nhiều lớp: reverse proxy, servlet container, Spring Security và Spring MVC. Các lớp này không phải lúc nào cũng xử lý giống nhau với dấu chấm phẩy, đường dẫn dư dấu gạch chéo, ký tự đã URL-encode hoặc đoạn `..`. Nếu security matcher kiểm tra một cách hiểu đường dẫn nhưng controller xử lý theo cách hiểu khác, quy tắc bảo vệ tài nguyên có thể bị áp dụng sai.

**`HttpFirewall`** của Spring Security nằm ở đầu quá trình xử lý của `FilterChainProxy` để kiểm tra, giới hạn và cung cấp một dạng request phù hợp cho việc khớp các `SecurityFilterChain`. Hai triển khai cần phân biệt là:

- **`StrictHttpFirewall`:** mặc định được Spring Security Servlet sử dụng trong các cấu hình hiện đại; chủ động từ chối nhiều dạng request bất thường hoặc nguy hiểm.
- **`DefaultHttpFirewall`:** triển khai cũ, ít nghiêm ngặt hơn; vẫn có kiểm tra đường dẫn không chuẩn hóa nhưng không cung cấp cùng mức hạn chế toàn diện như `StrictHttpFirewall`.

Mục tiêu bài học là hiểu **sự khác nhau, ảnh hưởng tới URL/method, lỗi `RequestRejectedException`, cách cấu hình và cách kiểm thử**. Không nên đổi sang firewall lỏng hơn chỉ vì một client nhận lỗi.

## 2. HttpFirewall hoạt động ở đâu trong servlet filter chain?

`FilterChainProxy` là bộ lọc của Spring Security được gọi qua servlet filter (thường thông qua `DelegatingFilterProxy`). Quy trình khái quát:

```text
HTTP request
   |
   v
Servlet container / filters phía trước
   |
   v
springSecurityFilterChain (FilterChainProxy)
   |
   +--> HttpFirewall.getFirewalledRequest(request)
   |       |
   |       +--> từ chối -> RequestRejectedException
   |       |                   -> RequestRejectedHandler / xử lý lỗi
   |       |
   |       +--> chấp nhận -> FirewalledRequest
   |                             |
   |                             v
   |                  khớp SecurityFilterChain
   |                             |
   |                             v
   |               authentication / CSRF / authorization...
   |                             |
   |                             v
   +----------------> DispatcherServlet -> controller
```

Khi request hợp lệ, `HttpFirewall#getFirewalledRequest` trả về một `FirewalledRequest` wrapper để Spring Security thực hiện việc khớp đường dẫn và xử lý. Wrapper có phương thức `reset()` để khôi phục cách nhìn request tại phần tiếp theo của chuỗi xử lý khi cần. Đây không phải cơ chế cho phép bỏ qua xác thực hay chỉnh sửa URL nghiệp vụ tùy tiện.

Khi request bị firewall từ chối, **controller thường chưa được gọi**, và lỗi là `RequestRejectedException`, **không** phải `AuthenticationException` hay `AccessDeniedException`. Vì vậy cần chẩn đoán khác nhau:

- Firewall rejection: request có hình thức/method/header không hợp lệ theo chính sách.
- Authentication failure: không có hoặc không hợp lệ thông tin đăng nhập.
- Authorization failure: người dùng được xác thực nhưng thiếu quyền.
- MVC 404/405: request đã đi qua firewall nhưng không có route/method tương ứng.

Không kết luận 403 thiếu quyền chỉ từ một log `RequestRejectedException`.

## 3. So sánh StrictHttpFirewall và DefaultHttpFirewall

| Tiêu chí | `StrictHttpFirewall` | `DefaultHttpFirewall` |
| --- | --- | --- |
| Vai trò | Mặc định nên dùng cho ứng dụng Servlet hiện đại | Triển khai cũ, tương thích hơn nhưng ít ràng buộc hơn |
| Tư duy bảo vệ | Từ chối các biểu diễn URL/method không được phép theo quy tắc chặt chẽ | Có kiểm tra chuẩn hóa đường dẫn, nhưng ít quy tắc chặt chẽ hơn |
| Đường dẫn bất thường | Mặc định từ chối nhiều dạng bất thường như semicolon, encoded slash/backslash và chuỗi không chuẩn hóa | Không áp cùng bộ hạn chế nghiêm ngặt; không đồng nghĩa chấp nhận mọi URL |
| Dấu `;` trong URL | Mặc định bị từ chối; có tùy chọn cho phép nếu được kiểm soát | Có hành vi lịch sử liên quan path parameters; cần kiểm tra container/version thực tế |
| HTTP method | Có allowlist mặc định cho những phương thức thường dùng | Không thực thi cùng allowlist nghiêm ngặt như Strict |
| Tinh chỉnh | Có các setter chọn lọc: semicolon, encoded slash, methods, hostname... | Ít lựa chọn chi tiết hơn cho từng loại request |
| Chẩn đoán | Có thể tạo `RequestRejectedException` trước security chain/controller | Cũng có thể từ chối request; không phải lựa chọn “tắt firewall” |
| Khuyến nghị | **Giữ mặc định, chỉ nới đúng một điều kiện khi có lý do và test** | Chỉ xem xét cho ràng buộc tương thích đã đánh giá, không dùng như cách sửa lỗi tổng quát |

**Không có bảng “Strict chặn thì Default chắc chắn cho qua” chính xác cho mọi môi trường.** Servlet container, proxy, ứng dụng và phiên bản thư viện có thể từ chối hoặc chuẩn hóa request trước khi request tới firewall. Ngược lại, nếu Default chấp nhận một chuỗi, điều đó không bảo đảm các lớp phía sau diễn giải nó an toàn hoặc thống nhất.

### Vì sao Strict là lựa chọn chuẩn?

Một URL như `/admin/../public`, `/api//users`, `/api/users;role=admin` hoặc chứa ký tự encode bất thường có thể bị phân tích khác nhau bởi proxy, servlet container và security matcher. Khi đó xuất hiện rủi ro **path confusion**: thành phần kiểm tra quyền thấy một đường dẫn, thành phần thực thi thấy đường dẫn khác.

`StrictHttpFirewall` hướng đến loại bỏ các biểu diễn có khả năng gây nhầm lẫn ngay đầu `FilterChainProxy`. Nhưng đây là **defense in depth**, không thay thế cấu hình reverse proxy, normalization thống nhất, xác thực hay authorization ở endpoint.

## 4. Các trường hợp request cụ thể

### 4.1. URL bình thường

```http
GET /api/products/42 HTTP/1.1
Host: app.example.test
```

Đường dẫn rõ ràng và phương thức `GET` nằm trong allowlist mặc định của Strict. Nếu các lớp khác cho phép, firewall không có lý do từ chối chỉ vì URL này. Việc server thực tế trả 200/401/403/404 sẽ do authentication, authorization và route quyết định.

### 4.2. Semicolon và matrix/path parameters

```http
GET /api/products;version=2/42 HTTP/1.1
Host: app.example.test
```

`StrictHttpFirewall` mặc định không cho dấu `;` trong URL. Điều này có thể ảnh hưởng ứng dụng cũ dùng matrix variables, path parameters hoặc `;jsessionid=...`. Một số môi trường truyền session ID trong URL có thể có yêu cầu lịch sử, nhưng **ưu tiên cookie phiên** và hạn chế URL-based session tracking vì URL dễ bị ghi log/lộ qua lịch sử và referrer.

Nếu ứng dụng thực sự có giao thức matrix variable, có thể cân nhắc `setAllowSemicolon(true)` trên **StrictHttpFirewall** sau khi kiểm thử matcher, Spring MVC routing, proxy, servlet container và khả năng path traversal. Việc cho phép semicolon **không tự động bảo đảm an toàn**, và không phải lý do chuyển toàn bộ hệ thống sang `DefaultHttpFirewall`.

### 4.3. Encoded slash, backslash và double slash

Ví dụ dạng request cần xem xét:

```text
/api/items%2F42
/api/items%5C42
/api//items
/api/items/../admin
```

Các dạng này có thể tạo khác biệt giữa raw URL và path mà các tầng sau nhìn thấy. Strict thường từ chối biểu diễn không an toàn/không chuẩn hóa theo bộ quy tắc mặc định; đặc biệt `%2F` (encoded slash) bị từ chối mặc định. Trên ứng dụng có cơ chế encoding nhiều tầng, việc mở encoded slash có thể khiến proxy và controller phân biệt ranh giới segment khác nhau.

Nếu API cần lưu một giá trị chứa dấu `/`, ưu tiên **đưa giá trị đó vào query parameter hoặc request body** theo giao thức phù hợp, hoặc thiết kế segment ID không chứa slash. Không sử dụng `setAllowUrlEncodedSlash(true)` như biện pháp chữa lỗi hàng loạt. Dù firewall cho phép, servlet container/reverse proxy vẫn có thể từ chối hoặc decode trước.

### 4.4. HTTP methods

`StrictHttpFirewall` sử dụng danh sách phương thức được phép; trong Spring Security 6, mặc định thường gồm:

```text
GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS
```

Các method khác, ví dụ `TRACE`, không nằm trong allowlist mặc định. Một request `TRACE` có thể bị firewall hoặc container chặn trước khi tới controller. Dùng `setAllowedHttpMethods(...)` nếu muốn thu hẹp allowlist cho sản phẩm; cần tính tới `OPTIONS` cho preflight CORS, `HEAD`, health checks, client SDK, reverse proxy và các method API thực sự sử dụng.

Chặn method bằng firewall khác với **authorization cho method**. Ví dụ cho phép `POST` qua firewall không có nghĩa mọi người được phép tạo dữ liệu; `CSRF`, authentication và authorization vẫn kiểm tra tiếp.

### 4.5. Host, headers và parameters

Strict có các kiểm tra/điểm mở rộng bổ sung cho tính hợp lệ của hostname, header names/values và request parameters. Đối với hệ thống phục vụ nhiều tên miền hoặc đi qua proxy, hãy kiểm tra chính sách hostname với cấu hình `Host`, `Forwarded` / `X-Forwarded-*` và trust boundary của proxy.

Có thể dùng `setAllowedHostnames(...)` để giới hạn hostname mà firewall cho phép, nhưng điều đó **không thay thế** cấu hình trusted proxy, TLS virtual host, chống host-header injection và quy tắc điều hướng/redirect của ứng dụng.

Không nên tự tạo regex phức tạp cho toàn bộ header/parameter chỉ để “chặt chẽ hơn”: nhiều request hợp lệ chứa Unicode, dấu câu hoặc encoding. Nếu phải tùy chỉnh, kiểm thử với dữ liệu thật, xác định API contract, áp rule chính xác và ghi nhận trường hợp bị chặn.

## 5. Cấu hình trên Spring Boot 3 / Spring Security 6 (Java 17+)

Ví dụ dưới đây là **các class thuộc ứng dụng Spring Boot Servlet** có `spring-boot-starter-web` và `spring-boot-starter-security`, cùng một lớp `@SpringBootApplication`. Mã không phải một chương trình Java độc lập có thể chạy bằng `javac` mà không có dependencies. Tên package có thể được thêm theo ứng dụng thực tế.

### 5.1. Giữ StrictHttpFirewall và khai báo allowlist

File `ServletSecurityConfig.java`:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Configuration
public class ServletSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/ping").permitAll()
            .anyRequest().authenticated());
        return http.build();
    }

    @Bean
    WebSecurityCustomizer firewallCustomizer() {
        return web -> {
            StrictHttpFirewall firewall = new StrictHttpFirewall();

            // Minh họa ứng dụng chỉ triển khai GET/HEAD/POST.
            // Nếu có PUT, PATCH, DELETE hoặc CORS OPTIONS,
            // cần mở đúng các method thực tế của hệ thống.
            firewall.setAllowedHttpMethods(
                List.of("GET", "HEAD", "POST")
            );

            web.httpFirewall(firewall);
        };
    }
}
```

Đây là ví dụ **thu hẹp method allowlist** để làm rõ cách tùy chỉnh: ứng dụng demo chỉ định dùng `GET`, `HEAD` và `POST`. Với REST API sử dụng `PUT`, `PATCH`, `DELETE` hoặc trình duyệt gửi `OPTIONS` preflight, cấu hình trên sẽ chặn các request hợp lệ. **Không sao chép allowlist này vào sản phẩm khi chưa thống kê method của các client.** Nếu không có nhu cầu đặc biệt, có thể bỏ toàn bộ bean `firewallCustomizer` để dùng StrictHttpFirewall mặc định.

`WebSecurityCustomizer#customize` nhận WebSecurity và gắn firewall ở cấp `FilterChainProxy`. Chính sách này cần được phân biệt với `SecurityFilterChain`: security filter chain xử lý xác thực/quyền/CSRF, firewall áp dụng cho request trước giai đoạn chọn chain. Với ứng dụng nhiều `SecurityFilterChain`, không tạo các giả định rằng một chain riêng tự làm firewall bớt nghiêm ngặt trên route của nó.

### 5.2. Endpoint kiểm chứng đơn giản

File `PingController.java`:

```java
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }
}
```

Request bình thường `GET /public/ping` khi chạy ứng dụng với cấu hình trên sẽ qua firewall, match route được phép truy cập, và trả JSON:

```json
{"status":"ok"}
```

Đây là output body mong đợi; status là **200 OK** nếu endpoint được phục vụ bình thường. Nếu URL bị firewall từ chối, method `ping()` không chạy. Nếu URL được firewall chấp nhận nhưng sai route, MVC có thể trả 404/405; đây là hai nhóm lỗi khác nhau.

### 5.3. Nếu thực sự phải cho phép semicolon

Một thay đổi **có phạm vi rủi ro cao hơn** để minh họa cách điều chỉnh đúng tại Strict, chỉ dùng sau khi kiểm tra thiết kế:

```java
StrictHttpFirewall firewall = new StrictHttpFirewall();
firewall.setAllowSemicolon(true);
// Đăng ký firewall này thông qua web.httpFirewall(firewall)
// trong WebSecurityCustomizer của ứng dụng.
```

Đoạn này là **snippet cấu hình**, không phải file Java độc lập. Nó **chỉ** nới quy tắc semicolon của Strict, không phải bật lại mọi URL bất thường; các rule còn lại vẫn cần kiểm tra. Tốt nhất thiết kế endpoint tránh semicolon nếu không có nhu cầu đã xác định. Một pattern thay thế: `GET /api/products/42?version=2` nếu `version` là tham số dữ liệu thông thường.

Đừng nhầm giữa việc nới đúng một quy tắc URL và việc dùng `DefaultHttpFirewall`. Phương án thứ hai thay đổi tập hành vi bảo vệ rộng hơn và có thể gây khác biệt không được kiểm thử.

### 5.4. Có nên chuyển sang DefaultHttpFirewall?

Spring Security cũng cung cấp class `org.springframework.security.web.firewall.DefaultHttpFirewall` và có thể gắn qua `web.httpFirewall(...)`. Tuy nhiên, dùng nó để “hết lỗi” mà chưa chứng minh nguyên nhân là một quyết định về **giảm mức lọc đầu vào**, không phải bản vá tương đương.

Trước khi cân nhắc, bắt buộc xác định:
1. Request cụ thể bị từ chối bởi **quy tắc nào**, tại firewall hay trước đó ở proxy/container.
2. Đây có phải request hợp lệ theo API contract không; có thể chỉnh client/route để dùng URL chuẩn hóa không.
3. Có cơ chế validate URL/method tương đương ở proxy và ứng dụng hay không.
4. Tất cả security matchers có hoạt động nhất quán với cách servlet container/MVC diễn giải đường dẫn không.
5. Có test phủ các trường hợp semicolon/encoded slash/backslash/traversal, auth và authorization hay không.

Với đa số ứng dụng mới, **giữ StrictHttpFirewall mặc định** là quyết định dễ bảo trì và an toàn hơn.

## 6. RequestRejectedException và HTTP status

Khi Strict từ chối request, Spring Security ném `RequestRejectedException`. Tùy phiên bản Spring Security, cấu hình `RequestRejectedHandler`, servlet container và gateway, phản hồi client có thể khác; trong các cấu hình Servlet phổ biến, request bị từ chối có thể trở thành **HTTP 400 Bad Request**.

Không nên mặc định đây là lỗi 401/403:

| Tín hiệu | Tầng thường xử lý | Kỳ vọng điều tra |
| --- | --- | --- |
| `RequestRejectedException` với URL/method bất thường | `HttpFirewall` / `RequestRejectedHandler` | Request không đạt chính sách firewall; thường xem luồng HTTP 400 |
| `AuthenticationException` | Authentication filters / `AuthenticationEntryPoint` | Đăng nhập/xác thực thất bại; 401/redirect tùy API/web |
| `AccessDeniedException` | Authorization / `ExceptionTranslationFilter` | Thiếu quyền; thường 403 |
| Không khớp `@GetMapping` | Spring MVC DispatcherServlet | Route 404 hoặc method 405, không mặc định là firewall |
| Proxy trả 400/404 trước ứng dụng | Reverse proxy/servlet container | Ứng dụng có thể chưa hề thấy request; cần log tại edge |

`@ControllerAdvice` không phải công cụ bao phủ chắc chắn các exception xuất hiện **trước DispatcherServlet**, đặc biệt khi firewall chặn ngay tại `FilterChainProxy`. Muốn tùy biến status/log của firewall, sử dụng cơ chế `RequestRejectedHandler` của Spring Security phù hợp phiên bản triển khai, thay vì cố bắt `RequestRejectedException` bằng controller advice rồi mở rộng catch toàn cục.

Khi log, ghi nhận loại lỗi, request/correlation ID, method, địa chỉ route ở dạng đã **sanitise/truncate**; tuyệt đối không log session cookie, Authorization header, secret hoặc toàn bộ raw query string chưa lọc. Tránh biến phản hồi lỗi thành nơi lộ chi tiết rule matcher hay nội bộ filter chain. Không trả 200 “cho dễ debug” khi request bị firewall từ chối.

## 7. Kiểm thử hành vi của StrictHttpFirewall

### 7.1. Unit test trực tiếp, không phụ thuộc mạng/container

Với `spring-security-web` và `spring-test` (được kéo theo qua `spring-boot-starter-test` trong ứng dụng Boot), ta có thể kiểm chứng ngay tại HttpFirewall. Ví dụ JUnit 5 file `StrictFirewallTest.java` trong `src/test/java`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.FirewalledRequest;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.StrictHttpFirewall;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StrictFirewallTest {
    private final StrictHttpFirewall firewall = new StrictHttpFirewall();

    private MockHttpServletRequest req(String method, String uri) {
        return new MockHttpServletRequest(method, uri);
    }

    @Test
    void allowsOrdinaryGet() {
        FirewalledRequest accepted =
            firewall.getFirewalledRequest(req("GET", "/public/ping"));
        assertNotNull(accepted);
        accepted.reset();
    }

    @Test
    void rejectsSemicolonByDefault() {
        assertThrows(RequestRejectedException.class,
            () -> firewall.getFirewalledRequest(
                req("GET", "/public/ping;version=2")));
    }

    @Test
    void rejectsEncodedSlashByDefault() {
        assertThrows(RequestRejectedException.class,
            () -> firewall.getFirewalledRequest(
                req("GET", "/api/items%2F42")));
    }

    @Test
    void rejectsTraceMethodByDefault() {
        assertThrows(RequestRejectedException.class,
            () -> firewall.getFirewalledRequest(
                req("TRACE", "/public/ping")));
    }
}
```

Các test này sử dụng **Strict mặc định** để kiểm tra những quy tắc cốt lõi, không phụ thuộc vào status do proxy hay container tạo ra. `MockHttpServletRequest` là request giả của Spring Test; nó không mô phỏng trọn vẹn mọi quy tắc decoding của Tomcat/Jetty/Undertow, vì thế vẫn cần integration test nếu sửa firewall hoặc phụ thuộc URL encoding đặc biệt.

Để kiểm tra bean `firewallCustomizer` tại mục 5.1, phải bổ sung test chạy `FilterChainProxy` thực tế vì test trên khởi tạo một Strict mới mặc định. Không dùng unit test ở trên làm bằng chứng rằng customizer đã được áp dụng vào ứng dụng.

### 7.2. Thử thủ công với một ứng dụng chạy local

Khi đã có endpoint `/public/ping` và app khởi động tại `localhost:8080`, thử:

```bash
# URL bình thường: có thể trả 200 với body {"status":"ok"}.
curl -i http://localhost:8080/public/ping

# URL chứa semicolon: Strict mặc định sẽ từ chối nếu container chuyển đến firewall.
curl -i --path-as-is 'http://localhost:8080/public/ping;version=2'

# Encoded slash: có thể bị container chặn trước hoặc Strict từ chối.
curl -i --path-as-is 'http://localhost:8080/api/items%2F42'

# TRACE: bị Strict hoặc container chặn theo cấu hình.
curl -i -X TRACE http://localhost:8080/public/ping
```

Ví dụ không có credential và chỉ nên chạy ở môi trường dev/staging mà bạn kiểm soát. Nếu nhận 400 nhưng không thấy log firewall, kiểm tra Tomcat/proxy trước vì request có thể đã bị từ chối ở tầng dưới. Nếu request đến controller, xác nhận lại cấu hình `springSecurityFilterChain` đã được đăng ký đúng và app có dùng bean firewall đã chỉ định hay không. Không kết luận firewall đã từ chối chỉ từ HTTP status 400 duy nhất.

### 7.3. Ma trận regression khi thay policy

| Kiểm thử | Phản hồi/đường đi mong đợi |
| --- | --- |
| `GET /public/ping` bình thường | Firewall cho qua; controller có thể trả 200 |
| `GET` chứa semicolon | Strict mặc định từ chối; không gọi controller |
| Encoded slash/backslash hoặc URL không chuẩn hóa | Không vượt được chính sách Strict mặc định; có thể bị chặn trước bởi proxy/container |
| HTTP method `TRACE` | Không qua allowlist Strict mặc định |
| API GET/POST hợp lệ | Không bị chặn vì hình thức URL; auth/CSRF/authorization vẫn áp dụng |
| REST PUT/PATCH/DELETE thực sự sử dụng | Phải nằm trong custom allowlist nếu đã thu hẹp method |
| OPTIONS preflight từ browser | Nếu API dùng CORS, phải được xử lý hợp lệ; custom allowlist không chặn vô tình |
| User chưa đăng nhập tại route bảo vệ | Đi qua firewall nếu URL hợp lệ, sau đó auth xử lý riêng |
| User thiếu quyền tại route bảo vệ | Firewall cho qua URL hợp lệ, rồi authorization từ chối |
| Matrix variables được cho phép có chủ đích | Matchers, controller và proxy diễn giải cùng một route, không bypass quyền |
| Multiple Spring Security chains | Firewall policy vẫn áp dụng ở cấp FilterChainProxy, không dựa vào từng chain |
| Log/request error | Không lộ raw credential; phân biệt firewall, proxy và 403 auth |

Một bài kiểm tra end-to-end quan trọng: với **cùng một người dùng có/không có quyền**, thử request bình thường và các biểu diễn URL được coi tương đương bởi ứng dụng. Không có biến thể nào được phép chạm vào endpoint nhạy cảm khi quyền không cho phép. Đây là lý do policy URL cần thống nhất giữa proxy, container, security matcher và MVC.

## 8. Quy trình điều tra khi API bị firewall từ chối

1. **Lấy request thực tế:** method, đường dẫn, encoding, query, proxy routing, servlet context path và response status. Ẩn cookie/token, giảm thông tin cá nhân trước khi gửi log.
2. **Xác định tầng từ chối:** proxy, servlet container, `FilterChainProxy` hay Spring MVC. Tìm loại exception chính xác; `RequestRejectedException` là dấu hiệu firewall rõ hơn một status đơn lẻ.
3. **Kiểm tra phiên bản và cấu hình:** dùng `StrictHttpFirewall` mặc định hay custom `HttpFirewall`; có bean `WebSecurityCustomizer` đang ghi đè cấu hình không; có nhiều SecurityFilterChain không.
4. **Phân tích từng ký tự bất thường:** semicolon, encoded slash, backslash, double slash, dot segments, method lạ; kiểm tra có lý do nghiệp vụ thật cho biểu diễn đó không.
5. **Ưu tiên sửa client/URL contract:** loại bỏ đường dẫn không chuẩn hóa, chuyển giá trị có slash sang query/body, chuẩn hóa cơ chế encode/decode đúng một lần ở biên phù hợp.
6. **Chỉ khi cần mới nới một rule cụ thể:** ví dụ semicolon cho matrix variable; đánh giá an toàn của URL matching và regression testing. Giữ các rule Strict còn lại.
7. **Kiểm tra từ ngoài vào trong:** cùng một request qua proxy và gọi trực tiếp ứng dụng trong môi trường test; xác minh không sinh path confusion hay bypass authorization.

### Lỗi phổ biến cần tránh

- Thấy HTTP 400 rồi tắt firewall hoặc chuyển sang `DefaultHttpFirewall` ngay.
- Đồng nhất `RequestRejectedException` với lỗi CSRF 403, chưa login 401 hay thiếu quyền 403.
- Tin rằng encoded slash được mở ở Strict thì Tomcat/reverse proxy chắc chắn sẽ cho qua hoặc diễn giải giống nhau.
- Dùng `setUnsafeAllowAnyHttpMethod(true)` để “sửa” method lạ trong khi chưa hiểu rủi ro. Tùy chọn này cần được tránh trong ứng dụng thông thường.
- Cho phép semicolon vì một client tạo URL sai, thay vì sửa client hoặc hợp đồng route.
- Tạo allowlist HTTP methods quá ngắn mà quên `OPTIONS` preflight, `HEAD` hoặc REST methods đang dùng.
- Chỉ test controller/MVC; bỏ qua proxy, container, `FilterChainProxy` và filter chain registration.
- Log toàn bộ raw URI/headers từ request bị từ chối, làm phát tán token và ký tự điều khiển vào log.
- Coi firewall là thay thế cho input validation và phân quyền từng endpoint.

## 9. Checklist quyết định

- [ ] Sử dụng `StrictHttpFirewall` mặc định khi chưa có yêu cầu tương thích được xác nhận.
- [ ] Hiểu rằng `DefaultHttpFirewall` vẫn có kiểm tra đường dẫn nhưng ít nghiêm ngặt, không phải đường tắt bỏ mọi lỗi.
- [ ] Phân biệt đường dẫn chuẩn hóa, semicolon, encoded slash, backslash và HTTP methods.
- [ ] Firewall chạy trước logic authentication/authorization; lỗi `RequestRejectedException` được phân loại riêng với 401/403.
- [ ] Không tùy tiện mở các setter `setAllow...`; có lý do, phạm vi và regression test cụ thể nếu cần.
- [ ] Kiểm thử trực tiếp `StrictHttpFirewall` và kiểm thử end-to-end tại proxy/container khi sửa policy.
- [ ] Kiểm tra chính xác matcher, servlet context path và controller route trên các biến thể URL.
- [ ] Không để thay đổi firewall gây bypass authorization, thay đổi sai route hoặc rò rỉ dữ liệu qua log.

**Kết luận:** `StrictHttpFirewall` là lựa chọn mặc định có kiểm soát chặt cho Spring Security Servlet; `DefaultHttpFirewall` có khả năng tương thích rộng hơn nhưng không cùng mức bảo vệ. Khi request bị từ chối, cần tìm rule và tầng thực sự chặn request. Chỉnh đúng URL contract hoặc nới **duy nhất** điều kiện thực sự cần thiết trên Strict, rồi kiểm thử toàn chuỗi proxy → servlet → security → MVC.
