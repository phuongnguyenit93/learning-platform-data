# Kiểm tra HTTP redirect cùng HSTS của yêu cầu secure

## 1. Mục tiêu và phạm vi

Trong chương **Kiểm thử Servlet** của module **SPRING_SECURITY_HTTP_PROTECTION**, yêu cầu không dừng ở việc mở trang được bằng HTTPS: cần **chứng minh** rằng ứng dụng chuyển một request HTTP sang HTTPS và phát chính sách **HTTP Strict Transport Security (HSTS)** đúng trên phản hồi HTTPS. Đây là một mắt xích của phòng vệ HTTP và trình duyệt trong Spring Security, kết hợp cấu hình security headers, Servlet, reverse proxy và kiểm thử lỗi triển khai.

Sau bài học, người học có thể:

1. Phân biệt **redirect từ HTTP sang HTTPS** với **header HSTS**.
2. Cấu hình SecurityFilterChain yêu cầu kết nối bảo mật và chính sách HSTS có thời hạn, phạm vi rõ ràng.
3. Viết test **MockMvc** cho status, Location, scheme, host, port và header Strict-Transport-Security.
4. Kiểm tra những tình huống biên: HTTP/HTTPS, nhiều filter chain, HTTPS phía ngoài proxy nhưng HTTP phía trong, redirect loop, HSTS thiếu hoặc bị ghi đè.
5. Biết giới hạn của MockMvc và bổ sung kiểm thử qua kết nối TLS thật cùng trình duyệt.

> **Phạm vi:** Spring Security **Servlet** (Spring MVC, SecurityFilterChain, MockMvc). WebFlux dùng SecurityWebFilterChain và WebTestClient nên nằm ngoài ví dụ lập trình ở đây.

## 2. Redirect và HSTS giải quyết hai vấn đề khác nhau

**HTTP → HTTPS redirect** là hành động của server đối với request đến qua HTTP: trả về status trong nhóm 3xx cùng header Location mang URL HTTPS. Client có thể thực hiện request tiếp theo qua HTTPS. Redirect cần thiết khi người dùng hoặc HTTP client lần đầu truy cập bằng HTTP mà chưa biết chính sách của domain.

**HSTS** là header Strict-Transport-Security được trình duyệt chấp nhận từ **phản hồi qua kết nối HTTPS hợp lệ**. Trình duyệt ghi nhớ chính sách sử dụng HTTPS cho những lần truy cập sau đến host đó trong thời gian max-age. HSTS không thay thế cho cơ chế redirect ở lần đầu, trừ trường hợp host đã có chính sách HSTS từ trước hoặc nằm trong danh sách preload của trình duyệt.

| Tiêu chí | HTTP → HTTPS redirect | HSTS |
|---|---|---|
| Nơi thực hiện quyết định | Spring Security hoặc reverse proxy | Trình duyệt sau khi nhận header từ HTTPS |
| Dấu hiệu | HTTP 3xx và Location: https://... | Strict-Transport-Security: max-age=... |
| Tác dụng | Điều hướng request HTTP hiện tại | Chủ động sử dụng HTTPS cho các request tiếp theo |
| Lượt truy cập đầu tiên qua HTTP | Có thể redirect nhưng request đầu đã đi qua HTTP | Chưa bảo vệ nếu browser chưa học chính sách hoặc chưa preload |
| Phạm vi | URL, route hoặc host theo cấu hình | Host phát header và subdomain nếu bật includeSubDomains |
| Kiểm thử | Status và Location | Header trên request HTTPS, sau đó hành vi browser |

Ví dụ kỳ vọng khi truy cập domain giả định app.example.test:

~~~http
GET /public/ping HTTP/1.1
Host: app.example.test

HTTP/1.1 302 Found
Location: https://app.example.test/public/ping
~~~

Mã 302 chỉ là minh họa: cấu hình và phiên bản khác có thể phát một status redirect 3xx khác. **Chỉ kiểm tra 3xx là chưa đủ** vì redirect sang trang đăng nhập cũng có thể trả 302. Phải xem Location thật sự dùng HTTPS, đúng host và path.

Sau khi client truy cập lại URL HTTPS:

~~~http
GET /public/ping HTTP/1.1
Host: app.example.test

HTTP/1.1 200 OK
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
Content-Type: text/plain;charset=UTF-8

pong
~~~

Trình duyệt tuân thủ chuẩn bỏ qua HSTS được truyền bằng **HTTP thuần**. Vì vậy, việc ghi header HSTS lên response HTTP không làm lần truy cập đầu tiên an toàn. Spring Security Servlet thông thường chỉ ghi HSTS khi Servlet request được xem là secure.

## 3. Chuẩn bị cấu hình SecurityFilterChain có thể kiểm thử

Chọn một endpoint công khai để tránh nhiễu từ quy tắc xác thực: GET /public/ping. Khi dùng endpoint yêu cầu đăng nhập, response 401 hoặc redirect đến /login có thể che khuất lỗi chuyển kênh. Cấu hình minh họa dưới đây yêu cầu **tất cả request** đều secure, nhưng cho phép truy cập công khai endpoint kiểm thử.

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/ping").permitAll()
                .anyRequest().authenticated()
            )
            .requiresChannel(channel -> channel
                .anyRequest().requiresSecure()
            )
            .headers(headers -> headers
                .httpStrictTransportSecurity(hsts -> hsts
                    .maxAgeInSeconds(31536000)
                    .includeSubDomains(true)
                )
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Endpoint sử dụng trong test:

~~~java
package example.security;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Ý nghĩa:

- **requiresChannel().anyRequest().requiresSecure()**: nếu request được nhìn nhận là insecure, Spring Security áp dụng quy tắc chuyển hướng sang HTTPS. Quy tắc này áp dụng cả tài nguyên được permitAll.
- **httpStrictTransportSecurity()**: ghi HSTS vào phản hồi qua security filter chain khi request được nhận diện secure.
- **maxAgeInSeconds(31536000)**: chính sách một năm, dùng ở đây làm giá trị rõ ràng để kiểm thử. Môi trường mới nên triển khai với thời hạn ngắn trước khi nâng lên.
- **includeSubDomains(true)**: trình duyệt có thể áp dụng HSTS cho các subdomain của host. Chỉ dùng khi tất cả subdomain thuộc phạm vi này hỗ trợ HTTPS đúng chuẩn.
- **httpBasic()**: cung cấp xác thực HTTP Basic cho các route còn lại của ví dụ; ứng dụng thực tế có thể thay bằng form login hoặc phương thức khác.

Spring Security có cấu hình HSTS mặc định khi headers được bật và request secure. Ví dụ viết tường minh max-age và includeSubDomains để test tránh phụ thuộc mặc định thay đổi theo cấu hình hoặc phiên bản. Không tự bật chỉ thị preload chỉ để “bảo mật hơn”: thêm từ preload vào header không tự đăng ký domain trong danh sách preload của trình duyệt, và phạm vi/tác động có thể kéo dài.

## 4. Kiểm thử MockMvc cho HTTP redirect và HTTPS HSTS

Với Spring Boot, dự án thường có spring-boot-starter-web, spring-boot-starter-security cùng spring-boot-starter-test và spring-security-test cho môi trường kiểm thử. Sử dụng **@SpringBootTest** kết hợp **@AutoConfigureMockMvc** để MockMvc được tạo từ WebApplicationContext có Spring Security filter chain.

~~~java
package example.security;

import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class SecureChannelHstsTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void httpRequestRedirectsToHttps() throws Exception {
        mockMvc.perform(get("/public/ping")
                .secure(false)
                .with(request -> {
                    request.setScheme("http");
                    request.setServerName("app.example.test");
                    request.setServerPort(80);
                    return request;
                }))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                HttpHeaders.LOCATION,
                "https://app.example.test/public/ping"
            ))
            .andExpect(header().doesNotExist(
                "Strict-Transport-Security"
            ));
    }

    @Test
    void httpsRequestReceivesHstsHeader() throws Exception {
        mockMvc.perform(get("/public/ping")
                .secure(true)
                .with(request -> {
                    request.setScheme("https");
                    request.setServerName("app.example.test");
                    request.setServerPort(443);
                    return request;
                }))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Strict-Transport-Security",
                allOf(
                    containsString("max-age=31536000"),
                    containsString("includeSubDomains")
                )
            ))
            .andExpect(header().doesNotExist(HttpHeaders.LOCATION));
    }
}
~~~

### Hiểu từng assertion

Trong test HTTP, **secure(false)** mô phỏng trạng thái mà Servlet API thông báo kết nối không an toàn. **setScheme("http")**, **setServerName** và **setServerPort(80)** giúp URL redirect dự đoán được. Khi sử dụng cổng 80/443 tiêu chuẩn, Location không cần thêm :443. Test so sánh trọn URL để phát hiện host hoặc path bị đổi sai.

Trong test HTTPS, **secure(true)** là tín hiệu chính của Servlet request; nó không kích hoạt một TLS handshake thật. Status 200 chứng minh endpoint công khai được xử lý bình thường thay vì bị redirect lần nữa. Matcher kiểm tra max-age và includeSubDomains bằng các thành phần quan trọng, không phụ thuộc khoảng trắng trong header.

Assertion không có HSTS trên response HTTP phản ánh hành vi HSTS header writer thông thường của Spring Security. HSTS trên response HTTP không được trình duyệt tin cậy. Trong hạ tầng có proxy tùy chỉnh header, điều cần xác minh cuối cùng vẫn là **HSTS trên response HTTPS công khai**.

**Lưu ý quan trọng:** Nếu tự khởi tạo MockMvc bằng standaloneSetup mà không gắn springSecurityFilterChain, test sẽ bỏ qua bộ lọc bảo mật. Với cấu hình tự tạo từ WebApplicationContext, có thể áp dụng bộ tích hợp Spring Security:

~~~java
MockMvc mvc = MockMvcBuilders
    .webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
~~~

Các phương thức MockMvcBuilders và springSecurity cần import từ Spring Test và spring-security-test. Ví dụ trên là lựa chọn khác khi không dùng AutoConfigureMockMvc.

## 5. Test các biến thể URL và đường dẫn

### 5.1. Query string không được mất sau redirect

Ví dụ request GET /public/ping?locale=vi. Redirect cần bảo toàn query string theo hợp đồng:

~~~java
mockMvc.perform(get("/public/ping")
        .queryParam("locale", "vi")
        .secure(false)
        .with(request -> {
            request.setScheme("http");
            request.setServerName("app.example.test");
            request.setServerPort(80);
            return request;
        }))
    .andExpect(status().is3xxRedirection())
    .andExpect(header().string(
        HttpHeaders.LOCATION,
        "https://app.example.test/public/ping?locale=vi"
    ));
~~~

Test này cũng nhắc một nguyên tắc an toàn: không đưa bí mật, JWT hoặc access token vào query string vì URL có thể xuất hiện trong lịch sử, log và referrer.

### 5.2. Port không mặc định

Ở môi trường phát triển, HTTP thường dùng cổng 8080, HTTPS dùng 8443. Spring Security có cơ chế ánh xạ HTTP port sang HTTPS port cho redirect, cần kiểm tra và tùy chỉnh nếu hạ tầng khác mặc định. Kỳ vọng có thể là:

~~~text
http://localhost:8080/public/ping
    -> https://localhost:8443/public/ping
~~~

Không mặc định rằng Location lúc nào cũng dùng cổng 443. Cổng được trình duyệt truy cập phải là **cổng công khai**, không phải cổng nội bộ của proxy hoặc container.

### 5.3. Nhiều SecurityFilterChain

Ứng dụng có thể chia thành chain cho /api/** và /admin/**. Một request chỉ được xử lý bởi chain phù hợp. Nếu chain /api/** không bật requiresSecure hoặc không có header writer, test vào /admin/** thành công sẽ không phát hiện sai sót. Hãy thiết kế ca kiểm thử cho **từng nhóm endpoint quan trọng** và các matcher khác nhau.

### 5.4. Không đồng nhất redirect HTTPS với redirect đăng nhập

Giả sử request HTTP tới /private/orders cần xác thực. Nếu response Location là /login hoặc một OAuth2 authorization endpoint, test chỉ kiểm tra status 302 có thể báo đạt nhầm. Cần phân tách **chuyển kênh HTTPS**, **xác thực** và **ủy quyền**. Dùng endpoint permitAll để kiểm tra chuyển kênh; dùng endpoint bảo vệ để kiểm tra cơ chế xác thực riêng.

### 5.5. Phương thức POST và body

GET giúp kiểm chứng redirect căn bản. Với POST chứa dữ liệu, các mã redirect 301/302/303 và 307/308 có thể khiến client xử lý phương thức, body theo cách khác nhau. Nếu API nhận POST qua HTTP có thể xảy ra, cần kiểm thử riêng hành vi client và cân nhắc từ chối HTTP hoặc bảo đảm client bắt đầu bằng HTTPS. Không kết luận “POST luôn được giữ nguyên” chỉ từ test GET.

## 6. Reverse proxy, TLS termination và forwarded headers

Trong hệ thống triển khai thường có kiến trúc:

~~~mermaid
flowchart LR
    A["Trình duyệt"] -->|"HTTPS công khai"| B["Reverse proxy"]
    B -->|"HTTP mạng nội bộ"| C["Spring MVC"]
    B -->|"Forwarded / X-Forwarded-Proto"| C
    C --> D["Spring Security Filter Chain"]
~~~

Khi proxy kết thúc TLS, request tới JVM có thể đi bằng HTTP nội bộ mặc dù trình duyệt giao tiếp qua HTTPS. Spring Security quyết định secure channel dựa vào **thông tin Servlet request đã được xử lý**, đặc biệt là request.isSecure().

Nếu proxy không truyền, hoặc ứng dụng không xử lý đúng thông tin scheme/host/port, những lỗi sau có thể xuất hiện:

- **Redirect loop:** client gửi HTTPS tới proxy nhưng backend tiếp tục nghĩ request là HTTP, rồi redirect về cùng URL HTTPS.
- **Thiếu HSTS:** browser kết nối HTTPS, nhưng HSTS writer trong ứng dụng đánh giá request là insecure.
- **Location trỏ tới cổng hoặc host nội bộ:** browser không thể đi tới địa chỉ mà backend xây ra.
- **Sai ranh giới tin cậy:** client bên ngoài tự gửi X-Forwarded-Host hoặc X-Forwarded-Proto khiến redirect bị điều khiển nếu proxy không lọc.

Spring Boot có thể được cấu hình xử lý forwarded headers ở mức framework:

~~~properties
server.forward-headers-strategy=framework
~~~

Tùy môi trường, chiến lược native với container/proxy hỗ trợ tương ứng cũng có thể phù hợp. Không bật xử lý forwarded headers rồi mặc nhiên tin mọi header từ Internet. **Reverse proxy đáng tin cậy phải xóa hoặc ghi đè forwarded headers do client gửi**, và bảo đảm backend chỉ nhận nguồn header được cho phép.

### MockMvc không kiểm chứng TLS thực

MockMvc sử dụng request/response giả lập, không mở socket HTTPS, không kiểm chứng certificate và không triển khai proxy. Gắn secure(true) giúp thử **quy tắc Spring Security sau khi request đã được coi là HTTPS**, không chứng minh hạ tầng thực tạo ra request đó đúng.

Nếu muốn mô phỏng X-Forwarded-Proto, test phải thực sự có bộ xử lý forwarded headers trong cấu hình Filter/container; thêm một header như:

~~~java
.header("X-Forwarded-Proto", "https")
~~~

**không tự bảo đảm** request.isSecure() trở thành true trong mọi cấu hình. Nên kiểm thử integration qua proxy, vì URL công khai và cách xử lý forwarded headers là trách nhiệm chung của ứng dụng và hạ tầng.

### Ai nên thực hiện redirect?

Một hệ thống có thể đặt redirect ở **Spring Security**, ở **proxy**, hoặc cả hai nếu phối hợp đúng. Nếu proxy chặn request HTTP và redirect trước khi request đến JVM, MockMvc không thể chứng minh hành vi redirect đó; cần gửi HTTP trực tiếp tới endpoint công khai. Ở lớp ứng dụng, MockMvc vẫn có ích để xác minh HSTS và các ràng buộc secure do ứng dụng duy trì.

| Nơi xử lý | Có thể chứng minh bằng MockMvc | Cần kiểm thử tích hợp |
|---|---|---|
| Spring Security thực hiện HTTP redirect | requiresSecure, 3xx, Location | URL và TLS công khai |
| Proxy chuyển HTTP sang HTTPS | Hành vi app khi được báo secure | Redirect tại proxy |
| App và proxy cùng có quy tắc | Kết quả ở Servlet layer | Không có redirect loop, HSTS đúng ở HTTP response cuối cùng |

## 7. Kiểm thử âm tính và trường hợp biên

**Phản hồi HTTPS thất bại vẫn cần HSTS.** Nếu response 401/403/404 được trả qua HTTPS và vẫn đi qua security filter chain có HSTS, header nên có mặt. Ví dụ với HTTP Basic:

~~~java
mockMvc.perform(get("/private/orders").secure(true))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        "Strict-Transport-Security",
        containsString("max-age=31536000")
    ));
~~~

Đoạn trên giả định route bảo vệ và HTTP Basic như cấu hình mục 3. Với form login, response có thể là redirect 302 đến trang login; cần đặt expected status cho phù hợp. Điều quan trọng là kiểm thử HSTS không gắn cứng vào response 200.

**HTTPS không được redirect lặp.** Một request đã secure phải nhận response đúng nghiệp vụ (200, 401, 403 hoặc redirect đăng nhập có chủ đích), không bị redirect lặp tới chính URL HTTPS. Nếu lặp, kiểm tra cơ chế forwarded headers và port tại proxy.

**HSTS thống nhất.** Cả proxy và Spring Security cùng phát HSTS có thể tạo nhiều giá trị khác nhau. Nên chọn một nơi chịu trách nhiệm hoặc chuẩn hóa giá trị để không có chính sách mâu thuẫn. Kiểm tra response qua proxy ngoài mạng, không chỉ các header MockMvc nhìn thấy.

**HSTS không chữa lỗi TLS.** Header không sửa được certificate hết hạn, hostname không khớp, chuỗi chứng chỉ lỗi hoặc cipher yếu. HSTS có thể khiến trình duyệt nghiêm ngặt hơn khi có lỗi TLS; do vậy cần xác minh HTTPS thực trước khi áp max-age dài và includeSubDomains.

**Bộ nhớ HSTS của trình duyệt.** Sau khi browser học chính sách, gõ http:// có thể được nâng cấp thành HTTPS ngay trong trình duyệt mà **không gửi HTTP request** tới server. Điều này không có nghĩa redirect ở server đã ngừng hoạt động. MockMvc cũng không mô phỏng HSTS cache/preload.

**Thay đổi chính sách.** max-age=0 trên phản hồi HTTPS là cách yêu cầu trình duyệt xóa HSTS đã học cho host liên quan, nhưng không tự xóa chính sách của domain cha áp dụng cho subdomain hoặc những hiệu lực preload riêng biệt. Cần thiết kế phạm vi, kiểm thử và kế hoạch rollback trước khi bật includeSubDomains/preload.

## 8. Kiểm thử hệ thống ngoài MockMvc

Sau khi test Servlet pass, gửi request thật tới host công khai bằng HTTP client. Ví dụ dưới đây sử dụng domain giả định; thay bằng host có certificate hợp lệ. Không bỏ qua xác minh TLS trong kiểm thử production.

~~~bash
# Quan sát status và Location ban đầu, chưa follow redirect.
curl -I http://app.example.test/public/ping

# Quan sát response HTTPS và header HSTS.
curl -I https://app.example.test/public/ping

# Quan sát chuỗi chuyển hướng khi cần.
curl -IL http://app.example.test/public/ping
~~~

Kết quả mong đợi:

1. HTTP trả 3xx với Location là URL HTTPS công khai đúng scheme, host, port, path.
2. HTTPS trả status đúng nghiệp vụ, có Strict-Transport-Security theo chính sách.
3. Không bị lặp redirect; Location không lộ tên hoặc cổng nội bộ.
4. TLS handshake và certificate được client xác minh hợp lệ.
5. Endpoint bảo vệ vẫn đòi hỏi xác thực và phân quyền đúng ngay cả khi request đã HTTPS.

Trong DevTools → Network, kiểm tra request đầu tiên, response của redirect và response HTTPS cuối cùng. Có thể thấy browser nâng cấp URL trước khi gửi nếu HSTS đã được lưu. Để xác minh redirect phía server mà không chịu tác động bộ nhớ HSTS, sử dụng HTTP client phù hợp hoặc hồ sơ trình duyệt sạch.

## 9. Ma trận kiểm thử và cách nhận diện lỗi

| Mã | Tình huống | Kỳ vọng | Tầng kiểm thử |
|---|---|---|---|
| S01 | GET HTTP tới /public/ping | 3xx, Location HTTPS đúng URL | MockMvc + client thật |
| S02 | GET HTTPS tới /public/ping | 200, có HSTS, không redirect lặp | MockMvc + HTTPS thật |
| S03 | GET HTTP có query | Giữ query cần thiết khi redirect | MockMvc |
| S04 | HTTP 8080 sang HTTPS 8443 | Location đúng cổng được ánh xạ | MockMvc + tích hợp |
| S05 | HTTPS /private/orders chưa xác thực | 401 hoặc redirect login hợp lệ; có HSTS | MockMvc |
| S06 | Request thuộc chain /api/**, /admin/** | Chính sách đúng với từng matcher | MockMvc |
| S07 | HTTPS ngoài proxy, HTTP nội bộ | App nhận diện secure, không có loop | Proxy/integration |
| S08 | Browser đã học HSTS | Tự dùng HTTPS trong những lần sau | Browser |
| S09 | App/proxy cùng viết HSTS | Giá trị thống nhất ở response cuối | HTTP integration |
| S10 | Certificate/hostname lỗi | Phát hiện lỗi TLS trên client thật | Client/browser |
| S11 | HTTP response có HSTS nhưng không redirect | Không xem là đạt yêu cầu secure | HTTP integration |
| S12 | HSTS includeSubDomains thay đổi | Header đúng phạm vi đã quyết định | MockMvc + browser |

| Biểu hiện lỗi | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| HTTP trả 200 | Không có requiresSecure ở chain, hoặc redirect nằm ngoài app | Kiểm tra filter chain và proxy |
| HTTP trả 302 về /login | Test trộn lẫn chuyển kênh với xác thực | Dùng endpoint permitAll, kiểm tra Location |
| HTTPS thiếu HSTS | isSecure() false, headers bị tắt hoặc route không qua chain | Kiểm tra request và cấu hình headers |
| HTTPS redirect vô hạn | Backend không nhận forwarded scheme từ proxy | Kiểm tra proxy trust, Filter và port |
| Location có hostname nội bộ | Server xây URL theo Host/Port nội bộ | Kiểm tra forwarded host/port và port mapping |
| MockMvc pass nhưng browser từ chối HTTPS | TLS/certificate thật không được MockMvc mô phỏng | Test curl/browser qua domain thật |
| Browser không phát HTTP khi gõ http:// | HSTS cache hoặc preload đã tự nâng cấp URL | Test server redirect bằng HTTP client |
| HSTS sai max-age | Proxy/CDN hoặc chain khác ghi đè | Xem raw response ngoài proxy |
| Thêm X-Forwarded-Proto nhưng không có hiệu lực | Không đăng ký cơ chế xử lý forwarded headers | Xác minh Boot/container config và proxy |

Khi chẩn đoán, hãy xác định theo thứ tự: **request.isSecure() ở JVM là gì, filter chain nào được chọn, thành phần nào tạo Location, thành phần nào viết HSTS và proxy có sửa response không**. Các bằng chứng này giúp định vị lỗi đúng tầng.

## 10. Bài thực hành tổng hợp

**Bối cảnh:** API quản trị Spring MVC tại admin.example.test cung cấp /public/ping và /admin/reports. HTTPS là bắt buộc; ứng dụng nằm sau reverse proxy TLS termination; chưa thể áp HSTS cho toàn bộ subdomain vì còn một hệ thống cũ chưa chuyển sang HTTPS.

**Yêu cầu:**

1. Thiết lập chuyển hướng từ HTTP sang HTTPS ở lớp thích hợp, ghi rõ lớp chịu trách nhiệm.
2. Cấu hình HSTS max-age=31536000 nhưng **includeSubDomains(false)** trong giai đoạn chuyển đổi; chưa dùng preload.
3. Viết test MockMvc: HTTP /public/ping trả redirect đến https://admin.example.test/public/ping; HTTPS /public/ping trả 200 có max-age đúng và không có includeSubDomains.
4. Viết test HTTPS /admin/reports khi chưa xác thực, kỳ vọng từ chối đúng cơ chế và vẫn có HSTS.
5. Dùng curl qua proxy để xác minh Location, HSTS, certificate và không có redirect loop.

Với cấu hình includeSubDomains(false), matcher của test HTTPS có thể viết:

~~~java
import static org.hamcrest.Matchers.not;

mockMvc.perform(get("/public/ping").secure(true))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Strict-Transport-Security",
        allOf(
            containsString("max-age=31536000"),
            not(containsString("includeSubDomains"))
        )
    ));
~~~

**Tiêu chí hoàn thành:** kiểm thử chứng minh **HTTP được chuyển tới URL HTTPS đúng** và **HSTS được phát trên response HTTPS** theo chính sách đã chọn; không nhầm redirect đăng nhập với redirect HTTPS; xác minh được ảnh hưởng của reverse proxy, port và nhiều filter chain; không suy kết quả TLS thật từ việc MockMvc pass. Sau Step 4, nội dung sẽ tiếp tục được đánh giá chuyên môn ở quy trình Content QA riêng.
