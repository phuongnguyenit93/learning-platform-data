# Same-origin policy và mục đích của CORS

## 1. Vấn đề cốt lõi: trang web có được đọc dữ liệu từ một origin khác không?

Giả sử ứng dụng có:
- **Frontend**: http://localhost:5173, chạy JavaScript trong trình duyệt.
- **Backend**: http://localhost:8080, cung cấp API /api/public và /api/private.

Mã JavaScript từ frontend muốn gọi:

~~~javascript
const response = await fetch("http://localhost:8080/api/public");
const data = await response.json();
console.log(data);
~~~

Hai URL có cùng hostname **localhost** nhưng khác cổng **5173** và **8080**, vì vậy **không cùng origin**. Browser áp dụng **same-origin policy (SOP)**: script của origin này không được tự do đọc dữ liệu thuộc origin khác. Để API chủ động cho phép những trang có origin được tin cậy truy cập response, trình duyệt và server phối hợp bằng **Cross-Origin Resource Sharing (CORS)**.

**CORS không phải cơ chế đăng nhập và cũng không phải phân quyền nghiệp vụ.** CORS quyết định liệu **một trang/script chạy trong browser ở origin A** có được browser cho phép **đọc response** từ origin B hay không. Sau khi qua CORS, server vẫn phải kiểm Authentication, GrantedAuthority, CSRF khi cần và quyền truy cập tài nguyên.

Bài này trình bày:
1. Origin được xác định bởi **scheme + host + port** như thế nào.
2. SOP bảo vệ điều gì và không ngăn được điều gì.
3. Mục đích của CORS và cách trình duyệt thực thi chính sách qua các HTTP header.
4. Request thông thường và **preflight OPTIONS** khác nhau ra sao.
5. Tại sao **credentials, cookie, SameSite, CSRF** và CORS cần được xét riêng.
6. Cấu hình Spring Security 6.x / Spring Boot 3.x để xử lý CORS trước khi yêu cầu đăng nhập.
7. Demo Java 17+ có frontend ở localhost:5173, API ở localhost:8080, thử qua browser, curl và MockMvc.
8. Lỗi cấu hình thường gặp, các giới hạn của CORS và cách kiểm thử an toàn.

> Phạm vi ví dụ: **Spring MVC / Servlet stack**. Spring WebFlux dùng **CorsWebFilter**, **ServerHttpSecurity** và những kiểu API reactive riêng. Không sao chép nguyên lớp Servlet sang WebFlux.

## 2. Origin là gì?

**Origin** là bộ ba:

~~~text
origin = (scheme, host, port)
~~~

Ví dụ origin của **https://app.example.com:443/dashboard** là:
- Scheme: **https**.
- Host: **app.example.com**.
- Port: **443**, là cổng mặc định của HTTPS.

Đường dẫn **/dashboard**, query string, fragment và thông tin sau hostname không phải thành phần để so sánh origin. Hai URL có thể cùng host nhưng khác scheme hoặc port và vẫn là **cross-origin**.

### 2.1. Bảng so sánh origin

Giả sử trang đang mở ở **https://app.example.com/home**:

| URL tài nguyên | Cùng origin? | Lý do |
| --- | --- | --- |
| https://app.example.com/api/me | **Có** | Scheme, host, effective port đều khớp |
| https://app.example.com:443/api/me | **Có** | Cổng 443 là mặc định của HTTPS |
| https://app.example.com:8443/api/me | **Không** | Khác port |
| http://app.example.com/api/me | **Không** | Khác scheme và effective port |
| https://api.example.com/api/me | **Không** | Khác subdomain/host |
| https://app.example.com/other-path | **Có** | Chỉ khác path |
| https://app.example.com/api?q=1 | **Có** | Query không làm đổi origin |
| https://APP.example.com/api/me | **Có**, sau chuẩn hóa host phù hợp | Hostname DNS không phân biệt chữ hoa/chữ thường |
| https://app.example.org/api/me | **Không** | Khác host |

Với môi trường phát triển, **http://localhost:5173** và **http://localhost:8080** không cùng origin vì khác cổng. **http://localhost:5173** và **http://127.0.0.1:5173** cũng khác origin vì hostname khác nhau, dù cả hai đều trỏ tới máy cục bộ.

**Origin** không hoàn toàn đồng nghĩa với **site** trong bảo mật cookie:
- Origin quan tâm scheme, host và port.
- Khái niệm **site** thường dựa vào scheme và registrable domain, không coi port là yếu tố như origin.
- Vì thế hai URL **cross-origin** có thể vẫn là **same-site** theo quy tắc cookie. Hệ quả: CORS và SameSite cookie giải quyết hai vấn đề khác nhau; không thể thay thế lẫn nhau.

### 2.2. Origin của mã JavaScript đến từ đâu?

Khi trình duyệt tải **index.html** từ http://localhost:5173, script trong trang chạy với origin của tài liệu đó. Khi script gọi fetch sang http://localhost:8080, browser so sánh origin hiện tại với origin đích.

Frontend build ra HTML/JavaScript được host ở đâu quan trọng hơn tên folder source code. React, Vue, Angular, Vite không làm thay đổi khái niệm SOP: trình duyệt vẫn căn cứ URL origin của tài liệu khi code chạy.

Một số tình huống như tài liệu sandbox, data URL hoặc file URL có thể có **opaque origin**; trình duyệt có thể gửi header **Origin: null**. Không tự động coi giá trị "null" là một origin tin cậy để cho phép trong production.

## 3. Same-origin policy (SOP) bảo vệ điều gì?

SOP là một nền tảng của bảo mật trình duyệt nhằm ngăn script từ origin không đáng tin đọc hoặc can thiệp tùy ý vào dữ liệu và context của origin khác.

Ví dụ:
- Người dùng đăng nhập ứng dụng ngân hàng tại **https://bank.example**.
- Cùng lúc, người dùng mở trang độc hại **https://evil.example**.
- Nếu script của evil.example được tự do đọc phản hồi từ bank.example với credential của người dùng, attacker có thể tìm cách lấy số dư, thông tin tài khoản hoặc dữ liệu nhạy cảm.

SOP tạo ra ranh giới bảo vệ: script từ evil.example **không tự có quyền** lấy nội dung từ bank.example chỉ vì hai trang cùng đang mở trên một trình duyệt.

### 3.1. Đừng hiểu SOP là “browser chặn mọi HTTP request khác origin”

Đây là nhầm lẫn phổ biến. Browser vẫn cho phép nhiều dạng hoạt động cross-origin, tùy cơ chế:
- Điều hướng tới URL ở origin khác.
- Tải ảnh qua phần tử **img**.
- Tải script từ nguồn khác theo chính sách và thuộc tính liên quan.
- Gửi HTML form tới origin khác trong những điều kiện được browser hỗ trợ.
- Thực hiện một số request **fetch** cross-origin nhưng **không cho script đọc response** nếu không đạt CORS.

Vì vậy, SOP **không bảo đảm request không được gửi đến server**. Đối với một số request đơn giản, backend có thể đã nhận và xử lý request dù script gọi không được đọc response. Đây là lý do **CORS không thay thế CSRF**.

### 3.2. SOP có nhiều mặt, CORS tập trung vào một phần cụ thể

Bảo mật cùng origin còn liên quan tới:
- Truy cập DOM giữa frame/window khác origin.
- Khả năng script đọc dữ liệu từ fetch/XMLHttpRequest.
- Giới hạn lưu trữ, tài nguyên và các API browser khác.
- Các biện pháp bổ sung như CSP, COOP/COEP, CORP, sandbox và SameSite.

**CORS chủ yếu là cơ chế server cho phép chia sẻ response với những origin được chỉ định trong các tình huống browser áp dụng CORS.** Nó không “tắt SOP của cả trình duyệt”, không làm mọi DOM cross-origin trở nên đọc được, không vô hiệu các giới hạn cookie/storage và không tự cấp quyền API.

## 4. CORS được thiết kế để làm gì?

**Cross-Origin Resource Sharing (CORS)** là cơ chế dùng HTTP request/response headers, theo đó server chỉ ra origin nào được browser cho phép truy cập một resource nhất định. Browser nhìn các header đó để quyết định có cho JavaScript đọc response hay không.

CORS giải quyết một nhu cầu hợp pháp rất phổ biến:

~~~text
SPA ở https://app.example.com
         |
         | fetch("https://api.example.com/me")
         v
API ở https://api.example.com
         |
         +--> Cho phép origin https://app.example.com?
                  |
                  +--> Có: trả CORS response headers phù hợp
                  |         Browser cho phép JS đọc response
                  |
                  +--> Không: browser không chia sẻ response với JS
~~~

**Server quyết định chính sách chia sẻ; browser thực thi chính sách cho script.** CORS hữu ích khi frontend/backend tách domain hoặc cổng, khi web fonts nằm trên CDN hay khi một origin cần tải tài nguyên qua fetch/canvas.

CORS không xác định user là ai. CORS chỉ xem origin của trang phát request, không kiểm tra business permission của account. Một origin được phép gọi CORS **không tự được** đọc hồ sơ của mọi user.

### 4.1. CORS là hợp đồng giữa server và browser, không phải hàng rào ngăn mọi client

Một HTTP client như **curl**, Postman hoặc backend service có thể gửi request trực tiếp tới API mà không bị browser SOP kiểm soát. Nó có thể tự đặt header Origin hoặc không gửi Origin. Vì vậy, không thể bảo vệ dữ liệu bằng cách nói “chỉ app.example.com được CORS”.

**Bảo vệ API thực sự phải dùng Authentication + Authorization**, validation, rate limiting và kiểm tra ownership/tenant. CORS chỉ là một phần của bảo mật web browser.

## 5. HTTP headers quan trọng của CORS

Có hai nhóm:
1. **Request headers** do browser thêm để cho biết origin và, khi preflight, phương thức/header dự kiến.
2. **Response headers** do server trả để khai báo chính sách chia sẻ.

### 5.1. Những request header thường gặp

| Header | Được dùng khi nào? | Ý nghĩa |
| --- | --- | --- |
| **Origin** | Cross-origin request thích hợp, và một số same-origin request | Origin của trang/context khởi tạo request |
| **Access-Control-Request-Method** | Preflight OPTIONS | HTTP method mà request thực sẽ dùng |
| **Access-Control-Request-Headers** | Preflight OPTIONS khi cần | Danh sách các custom/request headers mà request thực dự kiến gửi |

Ví dụ preflight:

~~~http
OPTIONS /api/public HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: x-lesson-client
~~~

Đây là request do **browser** tạo để xin phép trước một GET có custom header. Frontend thông thường không tự viết OPTIONS thủ công để “giả làm CORS”; developer khai báo fetch, browser quyết định có cần preflight và tự gửi nó.

### 5.2. Những response header thường gặp

| Header | Chức năng |
| --- | --- |
| **Access-Control-Allow-Origin** | Origin được phép nhận response; có thể là một origin cụ thể hoặc dấu * trong trường hợp phù hợp |
| **Access-Control-Allow-Methods** | Các HTTP method được cho phép trong kết quả preflight |
| **Access-Control-Allow-Headers** | Những request header được cho phép khi preflight |
| **Access-Control-Allow-Credentials** | Cho biết browser có được chia sẻ response khi request mang credentials hay không |
| **Access-Control-Max-Age** | Hướng dẫn cache kết quả preflight một thời gian, phụ thuộc giới hạn browser |
| **Access-Control-Expose-Headers** | Những response headers ngoài danh sách CORS-safelisted mà JS được đọc |
| **Vary: Origin** | Cho cache biết response có thể khác nhau theo request Origin |
| **Vary: Access-Control-Request-Method / Headers** | Có thể cần khi preflight response thay đổi theo method/headers |

Ví dụ server cho phép frontend ở localhost:5173 đọc response:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Vary: Origin
Content-Type: application/json

{"message":"hello-from-api"}
~~~

Header **Access-Control-Allow-Origin** khai báo quyền chia sẻ response, không phải giấy phép đăng nhập. Nếu endpoint cần Authentication mà request không có credential hợp lệ, server vẫn có thể trả **401**, kèm CORS headers để frontend đọc và xử lý lỗi đúng cách.

### 5.3. Dấu * có ý nghĩa rất cụ thể

~~~http
Access-Control-Allow-Origin: *
~~~

Dấu * có nghĩa server cho phép **mọi origin** đọc response trong những request **không dùng credentials theo CORS**. Điều này có thể hợp lý đối với dữ liệu công khai như một số public APIs và tệp tĩnh công khai.

Khi request dùng credentials, server **không được** dùng * cho **Access-Control-Allow-Origin** nếu muốn browser cho phép đọc response. Browser sẽ chặn truy cập trong tình huống như:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Đối với ứng dụng dùng cookie/session, phải liệt kê origin cụ thể được tin cậy và gửi **Access-Control-Allow-Credentials: true** nếu thực sự cần chia sẻ credentialed response. Không trả **Access-Control-Allow-Origin** bằng cách echo mọi giá trị Origin chưa kiểm tra.

### 5.4. Origin không phải role hay username

Nếu một browser ở **https://app.example.com** mở hai tài khoản khác nhau, cả hai đều gửi cùng Origin trong request cross-origin đến API. CORS không biết tài khoản nào được quyền xem báo cáo. Quyền dữ liệu phụ thuộc Authentication và Authorization tại backend.

Tương tự, một attacker có thể tạo HTTP client ngoài browser và đặt tùy ý:

~~~http
Origin: https://app.example.com
~~~

Server không được coi header Origin là credential chứng minh danh tính. CORS dựa trên chính sách browser đối với script; Origin chỉ là một tín hiệu để server áp dụng chính sách chia sẻ tương ứng.

## 6. Request “đơn giản” và preflight OPTIONS

Không phải request cross-origin nào cũng có preflight. Browser có thể gửi **CORS simple request** (thuật ngữ mô tả trong MDN) trực tiếp rồi kiểm response headers. Những request khác cần **preflight** trước khi gửi request thực.

### 6.1. Ví dụ GET đơn giản, không preflight

~~~javascript
fetch("http://localhost:8080/api/public");
~~~

Một GET thông thường không có custom headers, trong điều kiện phù hợp, có thể được gửi trực tiếp. Nếu backend trả response nhưng thiếu CORS headers chấp nhận Origin, browser **không cho JavaScript đọc response**.

Điều này đặc biệt quan trọng: server có thể log thấy GET đã đến và trả 200, trong khi DevTools vẫn báo CORS error ở frontend. Không được kết luận browser chưa gửi request chỉ vì fetch() bị reject.

### 6.2. Ví dụ GET có custom header cần preflight

~~~javascript
fetch("http://localhost:8080/api/public", {
    headers: {"X-Lesson-Client": "frontend-demo"}
});
~~~

Header **X-Lesson-Client** không thuộc nhóm CORS-safelisted request headers. Browser thường gửi:

~~~http
OPTIONS /api/public HTTP/1.1
Origin: http://localhost:5173
Access-Control-Request-Method: GET
Access-Control-Request-Headers: x-lesson-client
~~~

Nếu chính sách cho phép, server trả ví dụ:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: x-lesson-client
Access-Control-Max-Age: 1800
~~~

Sau preflight thành công, browser có thể gửi GET thực, rồi vẫn kiểm CORS headers trên **response của GET thực** trước khi chia sẻ nội dung cho script.

**Preflight không phải request nghiệp vụ**: nó chỉ hỏi chính sách cross-origin. Đừng tạo dữ liệu hoặc thực hiện thao tác thay đổi trạng thái trong handler OPTIONS.

### 6.3. POST JSON thường cần preflight, nhưng không thể nói mọi POST đều cần

Một POST dùng **Content-Type: application/json** thường kích hoạt preflight do Content-Type này không thuộc nhóm CORS-safelisted content types. Ngược lại, POST form dùng Content-Type như **application/x-www-form-urlencoded**, **multipart/form-data** hoặc **text/plain** trong các điều kiện thích hợp có thể là simple request và không cần preflight.

Bảng hướng dẫn:

| Request từ JavaScript cross-origin | Có khả năng preflight? | Vì sao |
| --- | --- | --- |
| GET /api/public, không custom header | Thường **không** | Method và headers phù hợp điều kiện simple |
| GET, header X-Lesson-Client | **Có** | Custom header không safelisted |
| GET, header Authorization | **Có** | Authorization không phải CORS-safelisted request header |
| POST, Content-Type: application/json | **Có** | Content-Type không safelisted |
| POST form, application/x-www-form-urlencoded | Có thể **không** | Phù hợp điều kiện simple nếu không có yếu tố khác |
| PUT hoặc DELETE | Thường **có** | Method không thuộc nhóm simple methods |
| Request dùng custom header bất kỳ | Có thể **có** | Cần xét header và giá trị thực tế |

Kết quả còn phụ thuộc các điều kiện chi tiết của Fetch/CORS specification (request mode, header/value, browser policy…). Dùng **DevTools Network** để xem request thực tế thay vì cố suy đoán từ tên endpoint.

### 6.4. Preflight thiếu cookie là chuyện bình thường

Theo quy tắc browser, **CORS preflight không mang credentials** như session cookie. Do đó, nếu server bắt OPTIONS phải đăng nhập rồi mới trả CORS headers, browser có thể không bao giờ gửi được request thực có cookie hợp lệ.

Đây là lý do Spring Security khuyến nghị **xử lý CORS trước Spring Security authentication/authorization** cho preflight, ví dụ thông qua **CorsFilter / CorsConfigurationSource** và **http.cors(...)**. Không phải giải pháp đúng là bắt tất cả client tự gửi JSESSIONID trong OPTIONS.

## 7. Credentials: CORS không tự gửi cookie

Với browser fetch, có hai phần cần cùng tồn tại khi frontend gọi API khác origin bằng session cookie:

1. **Client chủ động chọn gửi credentials**, ví dụ fetch với **credentials: "include"**.
2. **Server cho phép credentialed CORS**, trả Origin cụ thể và Access-Control-Allow-Credentials: true.

Ví dụ frontend ở **https://app.example.com**:

~~~javascript
const response = await fetch(
    "https://api.example.com/api/me",
    {credentials: "include"}
);
~~~

Server phải có CORS policy chấp nhận origin https://app.example.com và credentialed requests, nhưng **cookie vẫn tuân theo Secure, SameSite, Domain, Path, thời hạn và chính sách privacy/tracking của browser**. CORS không buộc browser gửi cookie bị SameSite hoặc third-party-cookie policy chặn.

### 7.1. Không nhầm cross-origin với cross-site

Hai subdomain của cùng site có thể khác origin, nhưng vẫn same-site theo ngữ cảnh cookie. Ngược lại, frontend và backend ở hai registrable domains khác nhau có thể cross-site; khi ấy cookie policy khó hơn và phải kiểm tra trình duyệt thực tế.

Ví dụ **localhost:5173** và **localhost:8080** khác origin nhưng có thể được coi same-site theo mô hình cookie. Không lấy ví dụ local rồi suy ra SameSite=None luôn bắt buộc trong mọi deployment.

### 7.2. Không dùng wildcard khi bật credentials

Trong Spring Framework, cấu hình:

~~~java
configuration.setAllowedOrigins(List.of("*"));
configuration.setAllowCredentials(true);
~~~

là kết hợp **không được phép** đối với allowedOrigins. Spring có cơ chế **allowedOriginPatterns** để hỗ trợ pattern và phản hồi bằng origin cụ thể đã khớp, nhưng **pattern quá rộng vẫn là rủi ro nghiêm trọng**. Dùng **allowlist origin chính xác** khi có thể.

Một policy an toàn hơn cho ứng dụng có credential là:

~~~java
configuration.setAllowedOrigins(
    List.of("https://app.example.com"));
configuration.setAllowCredentials(true);
~~~

Hai đoạn trên là **fragments cấu hình**, không phải class chạy độc lập. Việc allowCredentials=true phải đi kèm thiết kế cookie/CSRF và endpoint authorization, không phải chỉ bật để “hết lỗi CORS”.

### 7.3. CSRF và CORS có quan hệ nhưng khác mục đích

**CORS**: browser có cho script tại origin A **đọc response** của origin B hay không?

**CSRF**: server có nhận một **yêu cầu thay đổi trạng thái giả mạo** mang credentials tự động đi kèm browser hay không?

Với simple request, browser có thể **gửi POST** dù script không được đọc response. Vì vậy chỉ cấu hình CORS không thay thế **CSRF token**. Nếu ứng dụng có session cookie hoặc cookie mang JWT tự gửi, cần đánh giá CSRF cho các unsafe methods và thiết kế Origin/Referer checks khi phù hợp.

Ngược lại, API Bearer token do client tự gắn vào Authorization header có threat model khác; vẫn cần xác thực token và chống XSS/token leakage. Không kết luận “dùng JWT thì khỏi CSRF” chỉ vì định dạng token là JWT.

## 8. Demo Spring Boot 3.x: CORS trong browser và authorization ở backend

Ta tạo một ứng dụng backend đơn giản:
- **GET /api/public**: endpoint công khai, trả JSON.
- **GET /api/private**: chỉ trả JSON nếu HTTP Basic authentication hợp lệ.
- **Allowed origin**: chỉ **http://localhost:5173**.
- **Allowed methods**: GET.
- **Allowed request headers**: X-Lesson-Client và Authorization.
- **Credentials mode của CORS**: không hỗ trợ chia sẻ credentialed responses bằng cookie; demo frontend chỉ gọi public API, không dùng session cookie.

Demo cố ý **không có endpoint thay đổi dữ liệu**. Vì vậy không phải tắt CSRF để thử CORS. HTTP Basic chỉ dùng để minh họa riêng một endpoint protected, và mật khẩu là mật khẩu thử nghiệm cục bộ.

### 8.1. Chuẩn bị project

Dùng **Spring Initializr** tạo project:
- **Java 17+**, **Spring Boot 3.x**, build bằng **Gradle**.
- Group **com.example**, artifact **demo**, package **com.example.demo**.
- Dependencies **Spring Web** và **Spring Security**.

Tạo đúng file Java:

~~~text
src/main/java/com/example/demo/CorsSopDemoApplication.java
~~~

### 8.2. Toàn bộ mã nguồn Java cho backend

~~~java
package com.example.demo;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
public class CorsSopDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CorsSopDemoApplication.class, args);
    }
}

@Configuration
class CorsSecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();

        // Chỉ frontend ở đúng origin này được đọc API qua CORS.
        configuration.setAllowedOrigins(
            List.of("http://localhost:5173"));

        // Demo chỉ có GET, không có POST/PUT/DELETE nghiệp vụ.
        configuration.setAllowedMethods(List.of("GET"));

        // Custom header này tạo ra preflight khi gọi từ browser.
        configuration.setAllowedHeaders(
            List.of("X-Lesson-Client", "Authorization"));

        configuration.setAllowCredentials(false);
        configuration.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        // Giới hạn policy cho các endpoint /api/**.
        source.registerCorsConfiguration("/api/**", configuration);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            // Tích hợp CORS vào Spring Security filter chain.
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/private")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            // CSRF mặc định được giữ nguyên.
            .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}demo123")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(reader);
    }
}

@RestController
class ApiController {

    @GetMapping("/api/public")
    Map<String, String> publicInfo() {
        return Map.of("message", "hello-from-api");
    }

    @GetMapping("/api/private")
    Map<String, String> privateInfo(Authentication authentication) {
        return Map.of(
            "username", authentication.getName(),
            "message", "authenticated");
    }
}
~~~

**Giải thích tính runnable:**
- Tên public top-level class trùng tên file **CorsSopDemoApplication.java**.
- Các class khác là package-private cùng package; Spring Boot component scan tìm được.
- Spring Boot 3.x với hai starters nêu trên cung cấp HttpSecurity, SecurityFilterChain, Spring MVC và JSON serialization.
- **UrlBasedCorsConfigurationSource** là bean để Spring Security tích hợp CORS theo cấu hình documented.
- **http.cors(Customizer.withDefaults())** bật đường xử lý CORS thích hợp trong security filter chain, để preflight hợp lệ không bị coi là request thiếu đăng nhập.
- **permitAll** ở GET /api/public không tương đương CORS allowlist. Một request từ curl vẫn có thể truy cập endpoint công khai mà không có Origin.
- **authenticated** ở GET /api/private yêu cầu Authentication; một origin được phép không thay thế password/credential.
- **setAllowCredentials(false)** cố ý dùng trong frontend thử nghiệm **không mang cookie**. Để demo credentialed CORS bằng session, cần chính sách khác và thiết kế login/CSRF đúng.
- **{noop}** chỉ dùng để học ở máy cục bộ; production phải dùng PasswordEncoder và user store an toàn.
- Không tắt CSRF vì demo chỉ có GET. Nếu bổ sung POST thay đổi dữ liệu, cần đánh giá CSRF theo cách gửi credential.

### 8.3. Chạy backend

Trong thư mục gốc project Gradle:

~~~bash
./gradlew bootRun
~~~

Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu không đổi **server.port**, API thường lắng nghe tại **http://localhost:8080**.

### 8.4. Frontend HTML độc lập để quan sát browser CORS

Tạo thư mục **web** ở thư mục gốc project và file **web/index.html**:

~~~html
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Same-origin policy / CORS demo</title>
</head>
<body>
    <h1>Thử CORS với Spring Security</h1>
    <p>Mở trang ở localhost:5173 để được phép đọc API.</p>
    <button id="ordinary">GET thông thường</button>
    <button id="preflight">GET có custom header</button>
    <button id="private">GET yêu cầu đăng nhập</button>
    <pre id="output"></pre>

    <script>
        const base = "http://localhost:8080";
        const output = document.getElementById("output");

        async function call(path, headers = {}) {
            output.textContent = "Đang gọi API...";
            try {
                const response = await fetch(base + path, {
                    method: "GET",
                    headers: headers
                });
                const body = await response.text();
                output.textContent =
                    "HTTP " + response.status + "\n" + body;
            } catch (error) {
                output.textContent = "Browser đã từ chối hoặc " +
                    "request thất bại: " + error.message;
            }
        }

        document.getElementById("ordinary")
            .addEventListener("click", function () {
                call("/api/public");
            });

        document.getElementById("preflight")
            .addEventListener("click", function () {
                call("/api/public", {
                    "X-Lesson-Client": "frontend-demo"
                });
            });

        document.getElementById("private")
            .addEventListener("click", function () {
                call("/api/private");
            });
    </script>
</body>
</html>
~~~

**File HTML này chạy được trong browser** khi được phục vụ qua một HTTP server. Không mở file:// trực tiếp, vì khi ấy trang có thể mang opaque origin và kết quả không còn là ví dụ localhost:5173 như đã thiết kế.

Dùng Python 3 (nếu có sẵn):

~~~bash
python3 -m http.server 5173 --directory web
~~~

Trên Windows, lệnh tương đương thường là:

~~~powershell
py -3 -m http.server 5173 --directory web
~~~

Sau đó mở **http://localhost:5173** trên browser. Lúc này origin của frontend là **http://localhost:5173**, còn API ở **http://localhost:8080**.

### 8.5. Những hiện tượng cần quan sát

**Nút 1 — GET thông thường:**
- Browser gửi GET /api/public với Origin http://localhost:5173.
- CORS policy khớp, server trả Access-Control-Allow-Origin.
- Script đọc được response **200** và body chứa **hello-from-api**.
- Request GET không có custom header có thể không cần preflight.

**Nút 2 — GET với X-Lesson-Client:**
- Browser tạo preflight **OPTIONS /api/public**.
- Preflight khai báo Access-Control-Request-Method: GET và Access-Control-Request-Headers: x-lesson-client.
- CORS xử lý OPTIONS trước HTTP authorization.
- Nếu preflight thành công, browser gửi GET thực.
- Kết quả GET là **200** như nút 1.

**Nút 3 — GET protected:**
- Origin vẫn được chấp nhận về CORS.
- Nhưng không có HTTP Basic credentials hợp lệ; Spring Security trả **401**.
- Frontend có thể đọc status **401** vì chính sách CORS cho phép origin đó đọc response.
- Đây là bằng chứng **CORS pass không có nghĩa authorization pass**.

**Các trạng thái trên là kết quả dự kiến từ cấu hình, không phải log thực thi đã thu thập**. Browser có thể cache preflight nhờ Max-Age; vì vậy sau một lần thử, bạn có thể không thấy OPTIONS ở mọi lượt nhấp. Mở DevTools Network và thay đổi cache/refresh khi cần.

### 8.6. Thử origin không nằm trong allowlist

Trong terminal thứ ba, dùng cùng thư mục web nhưng chạy một HTTP server khác:

~~~bash
python3 -m http.server 5174 --directory web
~~~

Mở **http://localhost:5174**. HTML/JS giống hệt nhưng origin bây giờ là **http://localhost:5174**, không thuộc allowedOrigins.

Khi script gọi GET /api/public ở localhost:8080:
- Browser không được chia sẻ response với JavaScript.
- DevTools Console/Network có thể hiển thị CORS error.
- Với triển khai CorsFilter trong ví dụ, Spring CORS processor cũng có thể trả 403 cho request có Origin không được chấp nhận.
- Nếu một request simple thực sự đi tới backend rồi bị từ chối, đây là xử lý CORS ở server; nếu backend khác chỉ thiếu response headers thì browser vẫn sẽ chặn việc script đọc response. Hai trường hợp có trải nghiệm lỗi frontend tương tự nhưng nguyên nhân ở HTTP layer khác nhau.

**Không đổi frontend port mà quên đổi danh sách allowedOrigins**, vì origin so khớp cả port. Để hỗ trợ nhiều frontend origin hợp lệ, cấu hình danh sách chính xác và giải thích lý do tin cậy từng origin.

## 9. Kiểm chứng HTTP bằng curl: quan sát header mà không nhầm với browser SOP

**curl không thực thi SOP/CORS như browser**. Nó có thể giúp kiểm tra server trả headers đúng hay không, nhưng việc curl đọc body không chứng minh browser sẽ đọc được body.

### 9.1. Request có Origin được chấp nhận

~~~bash
curl -i \
  -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/public
~~~

Kỳ vọng điển hình: **HTTP 200**, header **Access-Control-Allow-Origin: http://localhost:5173**, JSON có message hello-from-api. Trên Windows PowerShell, dùng **curl.exe** nếu curl là alias không tương thích.

### 9.2. Preflight với custom header

~~~bash
curl -i -X OPTIONS \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: x-lesson-client" \
  http://localhost:8080/api/public
~~~

Kỳ vọng điển hình: **200**, các header cho phép origin/method/request header và có thể có **Access-Control-Max-Age**. Request này **không gửi Authorization hoặc session cookie**; CORS preflight không cần credentials.

### 9.3. Origin không được chấp nhận

~~~bash
curl -i -X OPTIONS \
  -H "Origin: http://localhost:5174" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: x-lesson-client" \
  http://localhost:8080/api/public
~~~

Với Spring DefaultCorsProcessor, preflight cho origin không hợp lệ thường nhận **403 Invalid CORS request**. Đây là **quyết định của CORS processor phía server**, không phải hành động browser chặn đọc response. Browser có thể hiển thị lỗi CORS ở cấp JavaScript dù mã HTTP thực tế khác nhau giữa các API.

### 9.4. Authentication độc lập với CORS

~~~bash
# Không có HTTP Basic credentials, dù Origin hợp lệ:
curl -i \
  -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/private

# Có credentials hợp lệ của user demo:
curl -i -u reader:demo123 \
  -H "Origin: http://localhost:5173" \
  http://localhost:8080/api/private
~~~

Kỳ vọng:
- Request thứ nhất: **401** vì chưa xác thực, không phải vì Origin sai.
- Request thứ hai: **200**, JSON có username reader và message authenticated.

Không dùng mật khẩu thử nghiệm **demo123** trong hệ thống thật. Khi chạy curl -u trong môi trường dùng chung, chú ý việc command line có thể bị lưu lịch sử hoặc hiển thị cho process inspection.

### 9.5. Không gửi Origin

~~~bash
curl -i http://localhost:8080/api/public
~~~

Kỳ vọng **200** mà không cần browser CORS headers. Đây là ví dụ rõ rằng **CORS không phải cơ chế bảo vệ API khỏi truy cập ngoài browser**. Nếu muốn chặn client không hợp lệ, phải dùng Authentication/Authorization và các cơ chế an ninh thích hợp.

## 10. Bảng phân biệt CORS, Authentication, Authorization và CSRF

| Cơ chế | Câu hỏi chính | Ai kiểm tra? | Ví dụ |
| --- | --- | --- | --- |
| **SOP** | Script tại origin A có được tự đọc nội dung origin B? | Browser | Script evil.example không được đọc response bank.example tùy ý |
| **CORS** | Server B đồng ý chia sẻ response với script từ origin A không? | Server khai báo, browser thực thi | Allow-Origin: https://app.example.com |
| **Authentication** | Ai đang gửi request/credential? | Server / identity provider | Session, HTTP Basic, OAuth2 Resource Server |
| **Authorization** | Danh tính đó được xem/sửa tài nguyên nào? | Server | hasAuthority, hasRole, ownership |
| **CSRF protection** | Request thay đổi trạng thái có bị trang ngoài giả mạo nhờ credential tự gửi không? | Server, kết hợp browser semantics | CSRF token cho POST với session cookie |
| **SameSite cookie** | Browser có gửi cookie trong một số ngữ cảnh cross-site không? | Browser dựa cookie attributes | SameSite=Lax/Strict/None |
| **CSP** | Trang được tải và chạy những nguồn script/resource nào? | Browser theo policy của trang | script-src, connect-src |

**CORS không là bước thay thế cho Authentication, Authorization hoặc CSRF**. CORS sai cấu hình có thể mở rộng quyền đọc dữ liệu cross-origin cho một website không nên được tin cậy, nhưng ngay cả policy CORS khép kín cũng không bảo vệ API trước curl hoặc server-side clients.

## 11. Test tự động bằng MockMvc

Ngoài thử trên browser, có thể test cấu hình CORS của Spring Security để xác nhận:
- Preflight không cần đăng nhập.
- Origin được phép có đúng Access-Control-Allow-Origin.
- Origin khác không được cho phép.
- Endpoint yêu cầu Authentication vẫn trả 401 nếu thiếu credentials.
- Có credentials hợp lệ vẫn qua authorization.

Thêm vào **build.gradle** nếu chưa có:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là **fragment Gradle Groovy DSL**, không phải build.gradle đầy đủ. Spring Initializr thường đã thêm starter-test; tránh thêm trùng.

Tạo file **src/test/java/com/example/demo/CorsSopDemoApplicationTest.java**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsSopDemoApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void trustedOriginCanReadPublicEndpoint() throws Exception {
        mvc.perform(get("/api/public")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "http://localhost:5173"))
            .andExpect(jsonPath("$.message")
                .value("hello-from-api"));
    }

    @Test
    void anonymousPreflightIsProcessedBeforeAuthentication()
            throws Exception {
        mvc.perform(options("/api/private")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "x-lesson-client"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "http://localhost:5173"));
    }

    @Test
    void unknownOriginPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/public")
                .header(HttpHeaders.ORIGIN, "http://localhost:5174")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
            .andExpect(status().isForbidden());
    }

    @Test
    void corsAllowedDoesNotMeanUserAuthenticated()
            throws Exception {
        mvc.perform(get("/api/private")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "http://localhost:5173"));
    }

    @Test
    void correctlyAuthenticatedUserCanAccessPrivateEndpoint()
            throws Exception {
        mvc.perform(get("/api/private")
                .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                .with(httpBasic("reader", "demo123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("reader"));
    }
}
~~~

Chạy từ thư mục project:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

Các test trên xác minh **server-side CORS/Spring Security behavior** trong MockMvc. Chúng **không tự chạy chính sách SOP của browser thật**; muốn chứng minh JavaScript bị chặn tại origin không được phép, vẫn cần thử frontend thực ở port 5173/5174 hoặc browser-based E2E test.

**Kết quả nêu trong bài là kỳ vọng theo cấu hình; Gradle/test chưa được chạy trong nội dung này.**

## 12. Cách debug một lỗi “CORS policy blocked”

Khi Console báo CORS error, đừng lập tức thêm dấu * vào mọi config. Dùng thứ tự sau.

### 12.1. Xác định hai origin thật

Ghi rõ:
- Frontend URL đầy đủ gồm scheme, host, port.
- API URL đầy đủ gồm scheme, host, port.
- Redirect URL nếu có.
- Origin thực được browser gửi trong Network tab.

Ví dụ **localhost** và **127.0.0.1** là hai hostname khác nhau. Một frontend chạy ở http://localhost:3000 không tự được chấp nhận nếu chỉ allow http://localhost:5173.

### 12.2. Kiểm preflight OPTIONS trước

Nếu browser gửi OPTIONS:
1. Request có đúng **Origin** không?
2. **Access-Control-Request-Method** là gì?
3. **Access-Control-Request-Headers** liệt kê những header nào?
4. Preflight nhận HTTP 200/204 thích hợp hay 301/302/401/403?
5. Response có **Access-Control-Allow-Origin**, **-Methods**, **-Headers** đáp ứng yêu cầu không?
6. OPTIONS có bị Spring Security authentication filter, gateway hoặc reverse proxy chặn trước CORS không?

Một preflight bị redirect tới /login hoặc 401 do thiếu session thường là dấu hiệu **thứ tự filter/config CORS chưa đúng**. Trường hợp này không thể chữa bằng cách bắt browser gửi password trong OPTIONS.

### 12.3. Nếu preflight pass, kiểm response của request thực

Browser vẫn cần CORS headers phù hợp trên request thực. Một API có preflight 200 nhưng POST/GET thực trả 401/403/500 và thiếu Allow-Origin có thể khiến frontend chỉ thấy lỗi CORS chung.

Kiểm log server theo status/path/trace ID; phân biệt:
- 401: không có authentication hợp lệ.
- 403: không đủ quyền, CSRF hoặc CORS processor từ chối.
- 404: không có handler hoặc route khác với URL dự kiến.
- 5xx: lỗi application/gateway có thể không gắn CORS headers.

**Không mở quyền rộng để che lỗi phân quyền hoặc lỗi máy chủ.**

### 12.4. Kiểm cookie, SameSite và credentials

Nếu frontend phải gửi session cookie:
- fetch có **credentials: "include"** chưa?
- Server có **Access-Control-Allow-Credentials: true** cùng allow origin cụ thể chưa?
- Cookie có đúng **Secure, SameSite, Domain, Path** cho môi trường không?
- Browser có chính sách chặn third-party cookies không?
- Login/session thật sự đã hoàn thành chưa?
- CSRF token có phù hợp session hiện tại cho POST/PUT/PATCH/DELETE không?

Không cho rằng thêm **allowCredentials(true)** là đủ để khắc phục cookie bị browser từ chối hoặc session hết hạn.

### 12.5. Kiểm gateway, CDN, cache và nhiều security chains

Với reverse proxy, ingress hay CDN:
- Proxy có trả OPTIONS trực tiếp và bỏ CORS header không?
- Có trùng **Access-Control-Allow-Origin** từ gateway và Spring gây header không hợp lệ không?
- Cache có sử dụng **Vary: Origin** khi policy khác theo origin không?
- Endpoint lỗi do gateway trả có còn CORS headers phù hợp không?
- Có nhiều **SecurityFilterChain**, chain nào match /api/** và có cors() không?

Theo tài liệu Spring Security 6.5, khi có **nhiều CorsConfigurationSource beans**, framework không nhất thiết tự quyết được source nào dùng cho từng chain. Khi ấy có thể cấu hình **configurationSource** rõ ràng trong DSL của mỗi chain.

## 13. Những lỗi cấu hình và nhận định sai phổ biến

| Nhận định/lỗi | Vì sao sai hoặc nguy hiểm? | Cách làm đúng |
| --- | --- | --- |
| “CORS là cách khóa API chỉ cho frontend của tôi.” | curl hoặc backend service không chịu SOP | Dùng Authentication + Authorization phía server |
| “Không có CORS thì browser không gửi request được.” | Simple requests có thể được gửi trước khi browser chặn đọc | Không dùng CORS thay CSRF |
| “Chỉ cần permitAll là fetch cross-origin được.” | permitAll kiểm quyền API, không thêm CORS response headers | Bật CORS và allow origin phù hợp |
| “Origin localhost:5173 và localhost:8080 giống nhau.” | Port khác → cross-origin | So sánh scheme + host + port |
| “Frontend và API đều HTTPS nên same-origin.” | Host hoặc port có thể khác | So cả ba thành phần |
| “@CrossOrigin mặc định bảo vệ endpoint khỏi mọi attacker.” | CORS khai báo chia sẻ response, không xác thực user | Cấu hình origins hẹp và authorization riêng |
| “Access-Control-Allow-Origin: * + credentials=true là được.” | Browser không chấp nhận wildcard với credentials | Dùng origin cụ thể được tin cậy |
| “Preflight phải đăng nhập trước.” | Browser preflight không mang session cookies | Xử lý CORS trước authentication/authorization |
| “OPTIONS trả 200 thì chắc chắn GET/POST đọc được.” | Response thực cũng cần CORS headers, đồng thời phải qua auth | Kiểm cả preflight lẫn actual response |
| “JSON POST chắc chắn luôn simple request.” | application/json thường gây preflight | Kiểm Content-Type và request headers |
| “CORS pass nghĩa là user được phép đọc mọi dữ liệu.” | Origin không phải identity/authority | Bảo vệ endpoint và ownership |
| “CORS lỗi thì bỏ CSRF.” | Hai cơ chế khác mục đích | Giữ CSRF khi browser dùng cookie credentials |
| “Cho mọi Origin bằng regex để tiện.” | Có thể lộ dữ liệu authenticated tới domain không tin cậy | Allowlist origin cụ thể, review patterns |
| “Origin: null là localhost an toàn.” | Opaque origin có thể xuất hiện từ nhiều nguồn | Không tin null nếu không có threat model đặc biệt |
| “Set-Cookie được server gửi là browser sẽ luôn lưu.” | Cookie flags và privacy policy vẫn áp dụng | Kiểm Secure/SameSite/third-party policy |
| “CORS luôn chặn response khỏi curl.” | curl không thực thi SOP | Dùng curl để xem headers, browser để test SOP |
| “Chỉ cần add header trên 200, không cần trên lỗi.” | Frontend có thể không đọc được 401/403/500 | Bảo đảm xử lý CORS đúng filter/gateway |
| “Nếu Vary không quan trọng, cache sẽ tự hiểu Origin.” | Cache có thể nhầm response giữa origins | Kiểm Vary, caching và CDN policy |

## 14. Checklist thiết kế CORS cho hệ thống thực tế

Trước khi đưa CORS configuration lên production, nên trả lời:

1. Origin frontend chính xác là gì ở **dev, staging và production**?
2. Có thật sự cần **cross-origin** hay có thể dùng same-origin API qua reverse proxy không?
3. API nào cho phép cross-origin, API nào tuyệt đối không cần?
4. Allowed origins có được khai báo hẹp, tránh wildcard khi có credentials không?
5. Allowed methods và allowed headers có phản ánh đúng nhu cầu frontend không?
6. Preflight OPTIONS có được xử lý trước lớp authentication/authorization không?
7. Response thực và response lỗi có CORS headers đúng khi cần không?
8. Có dùng **credentials: include**, cookies hoặc Authorization header không? Lý do và threat model là gì?
9. Nếu dùng cookies, SameSite/Secure/HttpOnly/Domain/Path và CSRF có được cấu hình, kiểm thử không?
10. Có cấu hình dư thừa tại Spring MVC, Spring Security và gateway dẫn tới header trùng hoặc policy mâu thuẫn không?
11. Có endpoint nhạy cảm cần roles/scopes/ownership không, bất kể origin đã được cho phép?
12. Đã kiểm thử cả **trusted origin**, **untrusted origin**, **preflight**, **actual request**, **401/403** và browser thật chưa?
13. Nếu trả origin động, CDN/cache có hỗ trợ Vary: Origin và policy cache phù hợp không?
14. Các URL redirect, protocol upgrade, ports và localhost aliases có được tính đến không?
15. Có theo dõi configuration drift khi thêm frontend mới hoặc tách API sang một domain khác không?

### Câu hỏi tự đánh giá

1. Origin gồm những thành phần nào? Vì sao localhost:5173 khác localhost:8080?
2. Same-origin policy cấm tuyệt đối việc browser gửi mọi request cross-origin hay chủ yếu giới hạn các kiểu truy cập/đọc dữ liệu?
3. CORS do ai đề xuất chính sách và do ai thực thi đối với JavaScript chạy trong browser?
4. Vì sao một request từ curl vẫn có thể thành công ngay cả khi frontend JavaScript bị CORS chặn?
5. Tác dụng của **Origin**, **Access-Control-Allow-Origin**, **Access-Control-Request-Method** và **Access-Control-Allow-Headers** khác nhau thế nào?
6. Vì sao request GET có header **X-Lesson-Client** cần preflight nhưng GET thường thì có thể không?
7. Vì sao CORS preflight không nên bị yêu cầu có JSESSIONID?
8. Khi frontend dùng credentials: include, tại sao không thể dùng Allow-Origin: *?
9. Có thể dùng CORS thay CSRF token cho POST mang session cookie không?
10. Nếu preflight pass nhưng GET /api/private trả 401, đây có nhất thiết là lỗi CORS không?
11. Vì sao hai trang khác origin có thể vẫn được xem là same-site về cookie?
12. Trong Spring Security 6, vì sao cần **http.cors(...)** cùng CorsConfigurationSource hoặc tích hợp Spring MVC phù hợp?
13. Vì sao MockMvc test CORS headers vẫn cần thử bằng browser thật?
14. Nếu hệ thống có hai SecurityFilterChain, cần rà soát CORS ở những chain nào?
15. Vì sao không nên tự echo mọi Origin trong Access-Control-Allow-Origin khi có dữ liệu người dùng?

**Ghi nhớ:** **SOP** là ranh giới của browser giữa các origin. **CORS** là cơ chế **server công bố ngoại lệ có kiểm soát** để browser cho phép trang ở origin khác đọc response. CORS không tự xác thực user, không cấp quyền nghiệp vụ, không ngăn mọi HTTP client ngoài browser và **không thay CSRF protection**. Với Spring Security, hãy cho phép preflight được xử lý đúng, khai báo origin/method/header hẹp và luôn kiểm tra cả browser lẫn backend authorization.

## 15. Tài liệu chính thức

- MDN — Same-origin policy: https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy
- MDN — Cross-Origin Resource Sharing (CORS): https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN — Request credentials in Fetch: https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials
- Spring Security 6.5 — CORS (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html
- Spring Framework 6.x — CORS in Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Security — CSRF (Servlet): https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Fetch Living Standard — CORS protocol: https://fetch.spec.whatwg.org/
