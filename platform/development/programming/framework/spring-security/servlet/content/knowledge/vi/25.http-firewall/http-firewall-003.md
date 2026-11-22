# HttpFirewall: HTTP method, header, hostname và các điều kiện được chấp nhận trong Spring Security Servlet

## 1. HttpFirewall bảo vệ ranh giới HTTP nào?

Trong ứng dụng Spring Security dùng **Servlet**, một request không chỉ chứa đường dẫn. Nó còn có **HTTP method**, header, hostname, query string, tham số và nhiều biểu diễn URL có thể gây nhập nhằng. Khi hai thành phần trong hệ thống hiểu khác nhau về cùng một request, kẻ tấn công có thể tận dụng sự khác biệt để vượt qua quy tắc định tuyến, kiểm tra quyền hoặc kiểm tra dữ liệu.

**`HttpFirewall`** của Spring Security là điểm kiểm soát request ở lớp HTTP trước khi các bộ lọc bảo mật và `RequestMatcher` xử lý request theo cách thông thường. Triển khai thường dùng là **`StrictHttpFirewall`**. Firewall có thể từ chối request không đạt điều kiện, hoặc cung cấp một `FirewalledRequest` để các thành phần phía sau nhìn request theo cách nhất quán hơn.

Ví dụ, hệ thống chỉ mong nhận `GET`, `POST` và một số method chuẩn khác, nhưng client gửi `TRACE` hoặc một method tùy ý; hoặc tên host mà ứng dụng nhận được không nằm trong tập host công khai dự kiến. Firewall có thể chặn ngay ở ranh giới HTTP.

Đừng đồng nhất các lớp kiểm soát:

- **`HttpFirewall`**: quyết định request có đủ hợp lệ về mặt HTTP và các điều kiện firewall hay không, như method, tên/giá trị header, hostname, URL.
- **`SecurityFilterChain` / `authorizeHttpRequests`**: xác thực và quyết định ai có quyền truy cập một URL/method hợp lệ.
- **Spring MVC mapping**: ánh xạ method/URL vào controller, có thể trả `405 Method Not Allowed` nếu không có handler phù hợp.
- **Web server, reverse proxy, servlet container**: có thể từ chối request sai chuẩn trước khi nó đi đến Spring Security.
- **Controller/service**: kiểm tra dữ liệu nghiệp vụ và quyền trên từng tài nguyên.

Một request **qua được firewall** không có nghĩa là được xác thực, được cấp quyền hoặc an toàn về nội dung. Ngược lại, request bị firewall từ chối có thể không đến controller hay lớp phân quyền.

## 2. Luồng xử lý và vị trí cấu hình

Trong cấu hình Servlet thông thường, `FilterChainProxy` của Spring Security sử dụng một `HttpFirewall` trước khi áp dụng các security filters phù hợp. `StrictHttpFirewall` là triển khai được dùng mặc định trong cấu hình Spring Security phổ biến; nếu ứng dụng đã thay thế firewall bằng một triển khai khác, phải kiểm tra chính triển khai đó.

~~~text
Client
  │ HTTP request: method + path + Host + headers + body
  ▼
Web server / reverse proxy / Servlet container
  │ có thể từ chối request sai cú pháp trước
  ▼
Spring Security FilterChainProxy
  │
  ├─ HttpFirewall / StrictHttpFirewall
  │    ├─ method có được cho phép?
  │    ├─ URL/path có bị từ chối vì biểu diễn nguy hiểm?
  │    └─ hostname, header, parameter có đáp ứng predicate?
  │
  ├─ Nếu không: RequestRejectedException → bộ xử lý từ chối
  │
  └─ Nếu có: FirewalledRequest → SecurityFilterChain
                                   │
                                   └─ authentication → authorization → MVC/controller
~~~

Sơ đồ là mô hình khái niệm: một số kiểm tra header/parameter được thực hiện **khi code truy cập dữ liệu đó qua request đã bọc**, chứ không nhất thiết được duyệt toàn bộ ngay lúc nhận request. Vì vậy khi kiểm thử custom predicate cho header, phải thực sự làm cho ứng dụng đọc header hoặc duyệt danh sách header.

Không cấu hình `StrictHttpFirewall` bằng `http.headers(...)`: phần đó là cấu hình **security headers gửi trong response**, còn các phương thức `setAllowedHttpMethods`, `setAllowedHeaderNames`, `setAllowedHeaderValues` và `setAllowedHostnames` kiểm soát **request đi vào**.

## 3. Điều kiện HTTP method được chấp nhận

### 3.1. Default allowlist của StrictHttpFirewall

`StrictHttpFirewall` mặc định giới hạn request trong các method thông dụng sau (so khớp tên method):

| Được cho phép mặc định | Ý nghĩa HTTP thông thường |
| --- | --- |
| `GET` | Đọc tài nguyên; không nên có side effect |
| `HEAD` | Như GET về metadata, không trả body |
| `OPTIONS` | Hỏi khả năng của tài nguyên; dùng cho CORS preflight |
| `POST` | Gửi dữ liệu hoặc thực hiện thao tác |
| `PUT` | Tạo/thay thế trạng thái tài nguyên theo hợp đồng API |
| `PATCH` | Cập nhật một phần |
| `DELETE` | Xóa tài nguyên |

Các method như `TRACE`, `TRACK`, `CONNECT` và WebDAV `PROPFIND` không nằm trong tập mặc định. Request bị từ chối theo chính sách firewall có thể gây `RequestRejectedException` trước khi đến controller. Server/proxy đôi khi chặn method sớm hơn, nên HTTP status quan sát được phụ thuộc vị trí chặn.

Ví dụ:

~~~http
TRACE /api/orders HTTP/1.1
Host: api.example.test
~~~

Dù ứng dụng không có controller cho `TRACE`, loại bỏ method không mong muốn ngay tại firewall vẫn hữu ích. Tuy nhiên **cho phép method** không tự tạo endpoint: firewall mặc định có `PUT` không có nghĩa `PUT /api/orders` tồn tại hay có quyền.

### 3.2. Khi nào cần thay danh sách?

Chỉ mở rộng allowlist khi hệ thống thực sự cần một method không chuẩn, ví dụ ứng dụng WebDAV chủ đích hỗ trợ `PROPFIND`. Hãy đánh giá hỗ trợ từ proxy, container, CORS, routing, Spring Security method authorization và controller; thêm một method vào firewall **không tự hoàn thành** các bước đó.

Nếu API chỉ hỗ trợ đọc, có thể đặt allowlist hẹp hơn, nhưng đừng vô tình loại `HEAD` và `OPTIONS` nếu client, health check hoặc CORS preflight cần chúng. Việc `OPTIONS` có qua firewall không đồng nghĩa tự động cho phép mọi origin: CORS phải được cấu hình riêng.

`StrictHttpFirewall#setAllowedHttpMethods(List<String>)` cho phép cấu hình danh sách tùy ứng dụng. Tránh `setUnsafeAllowAnyHttpMethod(true)` chỉ để làm một request không chuẩn “chạy được”: hành vi này làm mất lớp giới hạn method vốn có và không xử lý các nguyên nhân cấu hình khác.

### 3.3. Phân biệt ba quyết định liên tiếp

| Tình huống | Lớp quyết định | Kết quả ví dụ |
| --- | --- | --- |
| Client gửi `TRACE` nhưng firewall không chấp nhận | Firewall | Bị từ chối trước controller; thường được ánh xạ thành phản hồi lỗi kiểu 400 |
| Client gửi `PATCH` hợp lệ nhưng không có mapping PATCH | MVC/router | Thường `405 Method Not Allowed` |
| Client gửi `DELETE` hợp lệ, có controller nhưng thiếu quyền | Authorization | Thường `403 Forbidden` hoặc `401` nếu chưa xác thực, tùy cấu hình |
| Client gửi `POST` hợp lệ dùng session nhưng thiếu CSRF token | CSRF filter | Thường `403 Forbidden` |
| Client gửi `GET` hợp lệ và được cấp quyền | Nhiều lớp cùng cho qua | Controller xử lý, kết quả phụ thuộc logic |

Không dùng firewall để thay thế `@PreAuthorize`, `authorizeHttpRequests`, CSRF hoặc validation nghiệp vụ.

## 4. Điều kiện tên header và giá trị header

HTTP request có thể mang nhiều header: `Host`, `Authorization`, `Accept`, `Content-Type`, `Cookie`, `Origin`, `X-CSRF-TOKEN`, `User-Agent`, trace headers, `Forwarded` và các `Sec-Fetch-*`. Tên header **không phân biệt chữ hoa/chữ thường** về ý nghĩa HTTP: `authorization` và `Authorization` chỉ cùng một trường.

Spring Security cung cấp các predicate tùy chỉnh trên `StrictHttpFirewall`:

- **`setAllowedHeaderNames(Predicate<String>)`**: trả `true` nếu tên header được chấp nhận; trả `false` nếu phải từ chối.
- **`setAllowedHeaderValues(Predicate<String>)`**: trả `true` nếu giá trị header được chấp nhận; trả `false` nếu phải từ chối.

Cả hai là điều kiện áp dụng cho request mà firewall bọc. Chúng không định nghĩa request header bắt buộc, không bảo đảm header không bị giả mạo và không thay thế việc parse/validate dữ liệu nghiệp vụ.

### 4.1. Thiết kế predicate cho header name

Giả sử một ứng dụng nội bộ quy định tuyệt đối không nhận header `X-Internal-Override` từ client. Ví dụ predicate minh họa:

~~~java
firewall.setAllowedHeaderNames(name ->
    name != null
        && !name.equalsIgnoreCase("X-Internal-Override"));
~~~

Đây là **đoạn trích của cấu hình firewall**, không phải file Java độc lập. Tên header bị cấm sẽ bị từ chối khi firewall kiểm tra header đó. Điều kiện `equalsIgnoreCase` tránh lỗi chỉ chặn `X-Internal-Override` nhưng bỏ sót `x-internal-override`.

Không nên tạo một danh sách chỉ gồm hai hoặc ba header quen thuộc rồi cho rằng mọi request sẽ hoạt động: browser, proxy, load balancer, OAuth2, CSRF, observability và HTTP/2 có thể cần header khác. Nếu dùng allowlist thật, kiểm kê traffic hợp lệ và các môi trường trước khi triển khai; bổ sung kiểm thử để tránh vô tình làm hỏng login, preflight hoặc tracing.

Đặc biệt không xem sự xuất hiện của một custom header là bằng chứng đáng tin cậy về quyền hạn: client có thể tự gửi nhiều header tùy ý. Quyền truy cập phải dựa trên xác thực và phân quyền, còn header được reverse proxy tạo phải được xử lý qua mô hình **trusted proxy**.

### 4.2. Thiết kế predicate cho header value

Giá trị header không nên chứa các ký tự điều khiển nguy hiểm như CR/LF theo chính sách HTTP hiện đại; vấn đề request splitting/header injection thường đã được server và container kiểm soát một phần. Một predicate minh họa có thể là:

~~~java
firewall.setAllowedHeaderValues(value ->
    value != null
        && value.indexOf('\r') < 0
        && value.indexOf('\n') < 0);
~~~

Đoạn trích này mô tả điều kiện ứng dụng; nó **không bảo đảm ngăn mọi dạng header injection**. Hệ thống còn cần kiểm soát dữ liệu khi tạo response header, proxy forwarding, parser và các dạng mã hóa khác. Nếu đặt chính sách quá chặt theo ký tự hoặc độ dài, có thể chặn `Authorization`, token, filename, `User-Agent` hay metadata hợp lệ.

**Lưu ý quan trọng khi kiểm thử:** kiểm tra header có thể được gọi khi code sử dụng `getHeader(...)`, `getHeaders(...)`, `getHeaderNames()` thông qua request đã được firewall bọc. Request chứa một header bạn cấm nhưng controller/framework **không bao giờ đọc nó** có thể không tạo đúng tín hiệu từ chối như bạn dự đoán. Viết test kích hoạt đúng cách truy cập header hoặc thêm validation rõ ở tầng proxy/application nếu yêu cầu chính sách phải được thi hành cho **mọi header ngay tại thời điểm nhận request**.

### 4.3. Header hợp lệ vẫn có thể là dữ liệu không đáng tin

Ví dụ header `X-Forwarded-Host: admin.example.test` vượt qua một predicate chỉ kiểm tra ký tự không có nghĩa nội dung đáng tin. Với headers do proxy sở hữu, cần cấu hình proxy **loại bỏ/ghi đè giá trị từ client** và chỉ cho ứng dụng tin header từ proxy đã được xác nhận. Không cho phép client tự tuyên bố mình đang đi qua một cổng/host trusted.

Tương tự, header `Authorization` có định dạng được firewall chấp nhận chưa chắc có credential đúng; bộ lọc xác thực phải kiểm tra chữ ký/token, issuer, audience, expiry hoặc secret phù hợp.

## 5. Điều kiện hostname được chấp nhận

### 5.1. Host mà firewall nhìn thấy là gì?

`StrictHttpFirewall#setAllowedHostnames(Predicate<String>)` đặt điều kiện cho tên host ứng dụng nhìn qua request (theo `HttpServletRequest#getServerName()`). Nếu `getServerName()` trả một giá trị mà predicate cho là không hợp lệ, firewall có thể từ chối request.

Trong các hệ thống công khai, host là một phần của ranh giới định tuyến: request có thể được gửi đến IP hoặc reverse proxy bằng giá trị `Host` không mong muốn. Nếu ứng dụng dựa vào host để tạo link đặt lại mật khẩu, chuyển hướng, callback URL hoặc phân luồng tenant, host không đáng tin có thể gây lỗi an ninh như **Host header injection** và URL poisoning.

**Mặc định không phải danh sách domain của ứng dụng.** Cần cấu hình allowlist hostname theo kiến trúc và kiểm tra cả quy tắc chọn virtual host tại reverse proxy/web server.

Ví dụ logic policy: chỉ chấp nhận `api.example.test` cho production và `localhost` cho môi trường phát triển/test. Tránh dùng phép so khớp `endsWith("example.test")` một cách ngây thơ: tên `attackerexample.test` cũng kết thúc bằng chuỗi đó. Nếu có subdomain, cần boundary bằng dấu chấm, canonicalization và chính sách quản lý subdomain cụ thể.

### 5.2. Khi có load balancer, reverse proxy hoặc forwarded headers

Mối quan hệ giữa header `Host` do client gửi, `X-Forwarded-Host`/`Forwarded` và `getServerName()` phụ thuộc vào servlet container, proxy và filter xử lý forwarded headers. Một ứng dụng phía sau gateway có thể nhìn thấy **hostname nội bộ** thay vì public hostname, hoặc thấy host đã được chuẩn hóa bởi một filter. Vì vậy:

1. Xác định request thực tế đến server mang `Host` nào và `getServerName()` mà Spring Security nhìn thấy.
2. Tại **trusted reverse proxy**, từ chối host không thuộc danh sách domain cho phép và loại/ghi đè forwarded headers do bên ngoài gửi.
3. Cấu hình chuyển tiếp header chỉ từ các hop đáng tin, rồi đặt hostname allowlist phù hợp với điểm kiểm tra trong ứng dụng.
4. Kiểm thử cả truy cập thông qua domain thật, internal health check, local/test và host giả; không nới allowlist sang `.*` chỉ vì môi trường proxy chưa được cấu hình chuẩn.

Dùng `setAllowedHostnames` làm lớp bảo vệ request hữu ích; đây không phải DNS resolver, không kiểm soát request outbound/SSRF, không chứng minh hostname đã TLS-authenticated và không tự xử lý mọi kỹ thuật giả mạo forwarded headers.

## 6. Cấu hình hoàn chỉnh cho Spring Security Servlet (Java 17+, Security 6+)

Ví dụ là class cấu hình **`FirewallConfig.java`** trong một dự án Spring Boot 3.x có `spring-boot-starter-security` và Spring Web. Nó được Spring container gọi, **không phải chương trình Java độc lập có `main()` để chạy bằng `javac FirewallConfig.java`**.

~~~java
package com.example.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.firewall.HttpFirewall;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Configuration
public class FirewallConfig {

    @Bean
    HttpFirewall httpFirewall() {
        StrictHttpFirewall firewall = new StrictHttpFirewall();

        // Các method mà API thực sự dự định nhận.
        // Giữ OPTIONS nếu có browser CORS preflight.
        firewall.setAllowedHttpMethods(List.of(
            "GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"
        ));

        // Môi trường production có thể chỉ cần một public hostname.
        // localhost chỉ để minh họa môi trường dev/test.
        firewall.setAllowedHostnames(host ->
            host != null
                && (host.equalsIgnoreCase("api.example.test")
                    || host.equalsIgnoreCase("localhost")));

        // Minh họa chính sách tên header bổ sung.
        // Các header thông thường vẫn được cho qua predicate này.
        firewall.setAllowedHeaderNames(name ->
            name != null
                && !name.equalsIgnoreCase("X-Internal-Override"));

        // Minh họa kiểm tra giá trị; container/proxy vẫn cần
        // chính sách cú pháp và chuẩn hóa HTTP độc lập.
        firewall.setAllowedHeaderValues(value ->
            value != null
                && value.indexOf('\r') < 0
                && value.indexOf('\n') < 0);

        return firewall;
    }

    @Bean
    WebSecurityCustomizer webSecurityCustomizer(HttpFirewall firewall) {
        return web -> web.httpFirewall(firewall);
    }
}
~~~

**Giải thích từng lựa chọn:**

- `new StrictHttpFirewall()` giữ các kiểm tra path/URL nghiêm ngặt khác của StrictHttpFirewall; ví dụ chỉ chỉnh những policy liên quan đề bài.
- `setAllowedHttpMethods(...)` dùng giá trị mặc định minh họa để người học biết điều kiện được chấp nhận. Ứng dụng có thể thu hẹp nếu thực sự cần.
- `setAllowedHostnames(...)` giới hạn host vào tập ví dụ; hãy thay domain theo môi trường thật, không sao chép nguyên `api.example.test` vào production.
- `setAllowedHeaderNames(...)` và `setAllowedHeaderValues(...)` minh họa predicate. Chúng **không phải một allowlist HTTP hoàn chỉnh cho mọi hệ thống**. Cần điều chỉnh theo giao thức và nhu cầu nghiệp vụ.
- `WebSecurityCustomizer` gắn chính firewall với cấu hình `WebSecurity`. Chỉ khai báo một bean `StrictHttpFirewall` mà không xác nhận hệ thống sử dụng bean đó có thể tạo sự nhầm lẫn ở một số cách cấu hình; đoạn trên gắn nó tường minh.
- Nếu ứng dụng đã có một `WebSecurityCustomizer`, hợp nhất cấu hình một cách phù hợp để tránh override hoặc logic chồng chéo. Nếu có nhiều `SecurityFilterChain` cùng chung `FilterChainProxy`, firewall áp dụng ở ranh giới proxy trước khi chọn chain.

Đối với phần lớn ứng dụng, cấu hình mặc định của `StrictHttpFirewall` cộng với proxy/container được cấu hình tốt đã là nền tảng phù hợp. Chỉ bổ sung custom predicates nếu có yêu cầu cụ thể và bộ test thể hiện được chúng chặn đúng traffic không mong muốn.

### 6.1. Ví dụ SecurityFilterChain để phân biệt firewall với authorization

Đoạn sau có thể nằm trong class cấu hình Security riêng của cùng dự án; chỉ minh họa tầng **ủy quyền**:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
        .anyRequest().authenticated());
    return http.build();
}
~~~

Các import tương ứng là `org.springframework.context.annotation.Bean`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.http.HttpMethod` và `org.springframework.security.web.SecurityFilterChain`. Đoạn này **không độc lập biên dịch nếu không đặt trong class có import**; nó nhấn mạnh rằng cho phép `GET` qua firewall và cho phép một URL công khai là hai quyết định khác nhau. Các method khác tuy được firewall chấp nhận vẫn phải đi qua authentication/authorization/CSRF của chain.

### 6.2. Điều kiện URL vẫn cần xét dù bài tập trung vào method/header/hostname

`StrictHttpFirewall` còn có chính sách chặt đối với một số cách biểu diễn URL/path gây nhập nhằng như dấu chấm phẩy, ký tự điều khiển, ký tự mã hóa nguy hiểm hoặc đường dẫn chưa chuẩn hóa. Không bật hàng loạt option `setAllow...` chỉ để “fix” lỗi URL. Thường nên sửa frontend/client gửi URL chuẩn và xác định đúng nguyên nhân reject; chỉ nới một quy tắc nếu thật sự có yêu cầu hợp lệ và đánh giá riêng rủi ro request smuggling/path matching.

Một URL có path hợp lệ **vẫn có thể bị chặn vì method hoặc hostname**, và một request method/host đúng **vẫn có thể bị chặn vì URL**. Các predicate không thay thế nhau.

## 7. Kiểm thử: method, header, hostname và tầng xử lý

### 7.1. Unit test ngay trên StrictHttpFirewall

Ví dụ **JUnit 5** sau đặt tại `src/test/java/com/example/security/FirewallConfigTest.java` trong dự án có dependency `spring-boot-starter-test` và `spring-security-test`. Nó gọi cấu hình firewall trực tiếp, không cần chạy một web server. Các tên class/package phù hợp với `FirewallConfig.java` ở mục 6.

~~~java
package com.example.security;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.HttpFirewall;
import org.springframework.security.web.firewall.RequestRejectedException;

class FirewallConfigTest {
    private final HttpFirewall firewall =
        new FirewallConfig().httpFirewall();

    private MockHttpServletRequest request(
        String method, String host) {
        MockHttpServletRequest request =
            new MockHttpServletRequest(method, "/api/example");
        request.setServerName(host);
        return request;
    }

    @Test
    void acceptsExpectedMethodAndHost() {
        assertDoesNotThrow(() ->
            firewall.getFirewalledRequest(
                request("GET", "api.example.test")));
    }

    @Test
    void rejectsUnexpectedMethod() {
        assertThrows(RequestRejectedException.class, () ->
            firewall.getFirewalledRequest(
                request("TRACE", "api.example.test")));
    }

    @Test
    void rejectsUnexpectedHost() {
        assertThrows(RequestRejectedException.class, () ->
            firewall.getFirewalledRequest(
                request("GET", "untrusted.example.test")));
    }
}
~~~

Vì đây là **unit test có các dependency Spring**, không chạy bằng JDK thuần. Với Maven/Gradle và dự án mẫu được cấu hình đầy đủ, chạy `./mvnw test` hoặc `./gradlew test` (trên Windows dùng `mvnw.cmd test` / `gradlew.bat test`). Ba test được thiết kế để pass khi cách cấu hình tại mục 6 được áp dụng; thông báo test runner cụ thể phụ thuộc công cụ và môi trường nên không giả lập stdout.

**Kiểm thử header** cần lưu ý việc kiểm tra có thể phát sinh khi code gọi accessor của request đã được bọc. Có thể tạo `MockHttpServletRequest` với header không hợp lệ, lấy `FirewalledRequest` qua `firewall.getFirewalledRequest(...)` rồi truy cập `getHeaderNames()`/`getHeader(...)` đúng như đường code thực tế. Không nên chỉ thêm một header vào MockMvc request và giả định mọi header đều luôn bị duyệt tại firewall ngay lập tức. Kiểm thử integration mới xác nhận cách container, filter chain và application sử dụng header.

### 7.2. Thử HTTP thực tế bằng curl và browser

Giả sử ứng dụng đang chạy ở `localhost:8080`, proxy cho phép `Host: api.example.test` chuyển đến instance thử nghiệm, và endpoint `/api/example` tồn tại:

~~~bash
# Request method/host bình thường:
curl -i -H "Host: api.example.test" \
  http://localhost:8080/api/example

# Method không nằm trong default allowlist:
curl -i -X TRACE -H "Host: api.example.test" \
  http://localhost:8080/api/example

# Host sai với allowlist minh họa:
curl -i -H "Host: untrusted.example.test" \
  http://localhost:8080/api/example
~~~

Các lệnh **chỉ là tình huống kiểm thử**, không có stdout hay HTTP status cố định vì môi trường/proxy/controller chưa được cung cấp. Ví dụ `TRACE` có thể bị chặn ở web server trước khi đến firewall. Host test có thể bị virtual-host router từ chối trước, hoặc có `ForwardedHeaderFilter` biến đổi serverName. Cần dùng logs có kiểm soát và integration test để biết chính xác tầng nào chặn.

Với browser, nhớ kiểm tra `OPTIONS` preflight cho SPA cross-origin nếu có CORS; không loại `OPTIONS` khỏi allowlist khi browser cần nó. HTTP method của request thực tế, host mà servlet nhìn thấy và headers do proxy chuyển tiếp là các giá trị cần quan sát.

### 7.3. Kỳ vọng xử lý request bị từ chối

Spring Security dùng `RequestRejectedException` cho các request bị firewall từ chối. Ở nhiều cấu hình hiện đại, `RequestRejectedHandler` chuyển chúng thành response lỗi **HTTP 400 Bad Request**; hành vi quan sát được có thể khác nếu server, proxy, container hoặc handler tùy biến trả mã riêng.

Một request bị firewall reject **không tương đương** với `401` (chưa xác thực), `403` (không được phép/CSRF) hay `405` (MVC không có mapping method). Khi debug, cần xác định điểm reject và đảm bảo lỗi bất thường không bị biến thành phản hồi 500 hoặc lộ stack trace chi tiết cho client.

Việc ghi log nên nêu nguyên nhân và loại request đủ để điều tra, nhưng **không log toàn bộ Authorization/Cookie hay dữ liệu nhạy cảm**; có thể áp dụng giới hạn log để tránh request độc hại làm ngập hệ thống.

## 8. Các lỗi thiết kế và cấu hình hay gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| CORS preflight bị chặn khi thêm method allowlist | Bỏ `OPTIONS` khỏi danh sách | Đánh giá lại policy, giữ OPTIONS nếu browser cần, rồi cấu hình CORS đúng |
| WebDAV `PROPFIND` bị reject | Method không thuộc nhóm mặc định | Chỉ thêm PROPFIND khi sản phẩm thực sự hỗ trợ; test proxy, security, MVC |
| Request có Host bất ngờ bị reject sau khi lên production | Proxy chuyển host nội bộ hoặc tên host khác môi trường test | Kiểm tra request.getServerName ở đúng tầng, chỉnh trusted proxy và allowlist |
| Host không mong muốn vẫn qua gateway | Gateway không khóa Host hoặc forwarded headers từ internet | Lọc ở proxy và cấu hình trusted hops; allowlist trong app làm lớp bổ sung |
| Browser login, CSRF hoặc tracing hỏng sau khi siết header names | Predicate quá hẹp, chặn Cookie/Origin/Authorization/trace headers | Kiểm kê traffic hợp lệ, test end-to-end và sửa predicate |
| Thêm header lạ nhưng không thấy request bị chặn | Accessor kiểm tra header chưa được code sử dụng; hoặc header bị proxy loại bỏ | Test đúng đường truy cập header và tầng nhận request |
| Cho phép PUT ở firewall nhưng API vẫn trả 403 hoặc 405 | Authorization, CSRF hoặc MVC chặn độc lập | Kiểm tra từng lớp theo thứ tự và status/log tương ứng |
| Ứng dụng dùng `setUnsafeAllowAnyHttpMethod(true)` để “sửa” lỗi | Nới toàn bộ policy thay vì sửa một requirement | Quay lại allowlist method nhỏ nhất đáp ứng nghiệp vụ |
| Dùng `http.headers(...)` để kiểm soát header request | Nhầm response security headers với request firewall predicates | Cấu hình HttpFirewall/WebSecurityCustomizer đúng lớp |
| Chỉ test Spring tại localhost, không test qua proxy | Host và header ở production khác | Test đường đi thật qua LB/CDN, error paths và preflight |

### Checklist triển khai

- [ ] Xác nhận hệ thống dùng `StrictHttpFirewall` và biết nơi nó được gắn vào `FilterChainProxy`/`WebSecurity`.
- [ ] Liệt kê method thực sự cần; không mở `TRACE`/`CONNECT`/method lạ khi không có yêu cầu chính đáng.
- [ ] Giữ `OPTIONS` khi trình duyệt cần CORS preflight; quản lý CORS riêng.
- [ ] Ràng buộc tên/giá trị header theo yêu cầu thực tế, không vô tình phá header hợp lệ và không coi custom header là bằng chứng phân quyền.
- [ ] Chỉ tin forwarded headers từ reverse proxy được kiểm soát; xác minh `getServerName()` và Host allowlist.
- [ ] Kiểm thử method không hợp lệ, host giả, header không hợp lệ, URL sai và request hợp lệ qua **cả** unit test lẫn proxy/container thật.
- [ ] Quan sát và xử lý `RequestRejectedException` có kiểm soát, không log credentials nhạy cảm.
- [ ] Giữ nguyên authentication, authorization, CSRF, MVC validation và chính sách upload/URL phù hợp; chúng là các lớp độc lập với firewall.

**Ghi nhớ:** `StrictHttpFirewall` kiểm tra **request HTTP có được chấp nhận để xử lý tiếp**; `setAllowedHttpMethods` là danh sách method, `setAllowedHeaderNames/Values` là các predicate cho header và `setAllowedHostnames` là predicate cho hostname mà servlet nhìn thấy. Tùy biến ở ranh giới này phải dựa trên client, proxy và ứng dụng thực tế; cho request qua firewall chỉ là bước đầu, không phải quyết định cấp quyền.
