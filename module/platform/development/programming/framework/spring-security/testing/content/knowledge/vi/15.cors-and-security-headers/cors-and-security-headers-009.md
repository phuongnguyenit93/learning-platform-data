# HSTS trong ngữ cảnh request bảo mật

> **Chương:** CORS và header bảo vệ  
> **Module:** SPRING_SECURITY_TESTING — kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng spring-security-test trên ứng dụng Servlet và Reactive.

## 1. HSTS giải quyết vấn đề gì?

Một người dùng truy cập ứng dụng qua `https://portal.example.vn`. Sau đó họ nhấn một liên kết cũ dùng HTTP hoặc nhập `http://portal.example.vn`. Nếu browser gửi request HTTP trước khi chuyển hướng, request ban đầu có thể đi qua mạng không mã hóa. Cookie, đường dẫn hoặc nội dung trao đổi có nguy cơ bị quan sát hay sửa đổi trên đường truyền.

**HTTP Strict Transport Security (HSTS)** cho phép server thông báo với browser rằng host này chỉ nên được truy cập qua HTTPS trong một khoảng thời gian. Browser lưu policy và tự nâng cấp các lần truy cập HTTP tiếp theo sang HTTPS trước khi gửi request mạng.

Header cơ bản:

~~~http
Strict-Transport-Security: max-age=31536000
~~~

Giá trị `max-age` tính bằng giây. `31536000` tương đương một năm. Khi nhận header này qua kết nối HTTPS hợp lệ, browser ghi nhớ chính sách cho host đã trả response.

Trong Spring Security, HSTS là security response header được ghi theo điều kiện request được xem là bảo mật (secure). Vì vậy, kiểm thử cần chứng minh hai việc:

- Khi request được nhận qua HTTPS/secure context, response có HSTS với giá trị đúng policy.
- Khi request là HTTP không bảo mật, ứng dụng không phát HSTS một cách sai lệch.

Bài này tập trung vào HSTS trong ứng dụng Servlet và Reactive, cách cấu hình `Strict-Transport-Security`, điều kiện HTTPS phía proxy, các tùy chọn `includeSubDomains`/`preload` và kiểm thử bằng **MockMvc** cùng **WebTestClient**.

## 2. Browser xử lý HSTS như thế nào?

### 2.1. Lần đầu truy cập và các lần tiếp theo

~~~mermaid
flowchart TD
    A["Browser truy cập HTTPS host"] --> B["Server trả Strict-Transport-Security"]
    B --> C["Browser kiểm tra response từ secure connection"]
    C --> D["Lưu policy theo host và thời hạn max-age"]
    D --> E["Người dùng truy cập HTTP cùng host lần sau"]
    E --> F["Browser tự nâng cấp sang HTTPS trước khi gửi request"]
    F --> G["Kết nối HTTPS và xác minh chứng chỉ"]
~~~

Với response nhận qua kết nối HTTPS hợp lệ, browser lưu policy. Khi người dùng truy cập HTTP tới host đã có policy còn hiệu lực, browser tự nâng cấp URL trước khi gửi request mạng.

**Giới hạn lần truy cập đầu tiên:** nếu browser chưa biết host có HSTS và host chưa nằm trong preload list của browser, người dùng vẫn có thể thực hiện lần truy cập HTTP đầu tiên. HSTS động chỉ có tác dụng sau khi browser nhận policy qua HTTPS. Vì vậy, cần chuyển hướng HTTP sang HTTPS ở hạ tầng và cân nhắc preload khi đáp ứng đủ điều kiện.

HSTS không thay thế TLS certificate hợp lệ. Khi browser nâng cấp sang HTTPS mà server có chứng chỉ sai, hết hạn hoặc không đáng tin, browser phải chặn kết nối theo quy tắc TLS; HSTS không cho người dùng bỏ qua lỗi chứng chỉ một cách an toàn.

### 2.2. HSTS áp dụng theo host, không theo path

Nếu `portal.example.vn` gửi HSTS từ response tại `/account`, policy áp dụng cho host đó, không chỉ riêng đường dẫn. Browser không lưu policy theo từng controller hay endpoint.

- HSTS từ `https://portal.example.vn/account` áp dụng cho host `portal.example.vn`.
- HSTS từ `https://api.example.vn` áp dụng cho host `api.example.vn`.
- Một subdomain không tự động có policy HSTS riêng chỉ vì domain cha đã gửi HSTS; điều đó phụ thuộc `includeSubDomains` của policy từ domain cha.

### 2.3. Browser nâng cấp HTTP như thế nào?

Khi policy còn hiệu lực, browser tự chuyển URL HTTP thành HTTPS trước khi thực hiện kết nối. Với HTTP dùng cổng mặc định 80, browser chuyển sang HTTPS cổng mặc định 443; với cổng khác, quy tắc nâng cấp giữ thông tin cổng theo xử lý HSTS của user agent. Không nên dựa vào HSTS để sửa cấu hình cổng dịch vụ; hãy công bố URL HTTPS đúng và cấu hình redirect ở hạ tầng.

## 3. Đọc các directive HSTS

| Directive | Ý nghĩa | Cách kiểm tra |
| --- | --- | --- |
| `max-age` | Số giây browser ghi nhớ policy | Giá trị dương theo thời hạn được duyệt |
| `includeSubDomains` | Áp dụng policy của host cho các subdomain của host đó | Có mặt khi toàn bộ subdomain trong phạm vi đã sẵn sàng HTTPS |
| `preload` | Thể hiện ý định đáp ứng yêu cầu preload list của browser | Chỉ bật khi đã đánh giá và thực hiện quy trình preload tương ứng |

Ví dụ:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Browser lưu policy cho host và áp dụng nó cho các subdomain. Khi dùng `includeSubDomains`, cần chắc chắn mọi subdomain thuộc phạm vi đều phục vụ HTTPS ổn định. Một subdomain cũ, dịch vụ nội bộ hoặc hệ thống bên thứ ba chỉ hỗ trợ HTTP có thể bị ảnh hưởng.

### 3.1. max-age được làm mới như thế nào?

Mỗi lần browser nhận một HSTS header hợp lệ từ HTTPS, thời điểm hết hạn được tính lại dựa trên `max-age` mới. Ví dụ server gửi một năm ở hôm nay, browser lưu một năm từ thời điểm nhận response. Nếu response sau gửi sáu tháng, policy còn hiệu lực sẽ được cập nhật theo sáu tháng kể từ lần nhận mới.

Nếu server gửi:

~~~http
Strict-Transport-Security: max-age=0
~~~

browser xóa policy HSTS động đã lưu cho host đó. Tuy nhiên, policy kế thừa từ một domain cha có `includeSubDomains` hoặc policy được tích hợp trong preload list có thể vẫn áp dụng. `max-age=0` không phải cách gỡ ngay một host khỏi preload list của mọi browser.

### 3.2. includeSubDomains cần đánh giá phạm vi

Giả sử `example.vn` phát:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Browser áp dụng policy cho `example.vn` và các subdomain, ví dụ `app.example.vn`, `api.example.vn` và `legacy.example.vn`. Nếu `legacy.example.vn` chưa hỗ trợ HTTPS, việc bật directive này có thể khiến người dùng không truy cập được dịch vụ đó.

Không bật `includeSubDomains` chỉ vì muốn header có thêm directive. Hãy kiểm kê subdomain, xác minh chứng chỉ, redirect và các dịch vụ đang hoạt động trước.

### 3.3. preload không tự động đưa domain vào danh sách

`preload` trong header không có nghĩa browser lập tức thêm domain vào danh sách tích hợp sẵn. Preload list là danh sách được duy trì và phân phối trong browser. Domain phải đáp ứng các tiêu chí của chương trình preload, gửi yêu cầu theo quy trình tương ứng và chờ quá trình cập nhật tới các phiên bản browser.

Các yêu cầu phổ biến của chương trình preload gồm HSTS thời hạn dài, `includeSubDomains`, directive `preload`, HTTPS hoạt động trên các subdomain và chuyển hướng HTTP sang HTTPS. Điều kiện có thể thay đổi theo chương trình, nên phải kiểm tra hướng dẫn hiện hành trước khi đăng ký.

**Không bật `preload` trong ví dụ hoặc production chỉ để làm test pass.** Đây là quyết định vận hành có phạm vi rộng và việc gỡ preload có thể mất thời gian.

## 4. HSTS mặc định trong Spring Security

Spring Security có HSTS writer trong cấu hình security headers mặc định. Thông thường writer chỉ thêm header khi request được xem là secure. Cấu hình mặc định thường dùng thời hạn một năm và không tự bật `includeSubDomains` hoặc `preload`.

Có thể cấu hình rõ policy trong Servlet:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .headers(headers -> headers
                .httpStrictTransportSecurity(hsts -> hsts
                    .maxAgeInSeconds(31536000)
                    .includeSubDomains(false)
                    .preload(false)))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll())
            .build();
    }
}
~~~

Ví dụ đặt thời hạn một năm, không áp dụng cho subdomain và không yêu cầu preload. Nếu tổ chức đã xác minh mọi subdomain hỗ trợ HTTPS, có thể cân nhắc `includeSubDomains(true)`. Chỉ bật `preload(true)` khi đã quyết định thực hiện quy trình preload thực tế.

### 4.1. HSTS và request secure

Trong Servlet, HSTS writer dựa trên trạng thái secure của request. Request HTTPS trực tiếp thường được servlet container đánh dấu secure. Trong môi trường reverse proxy, TLS có thể kết thúc tại proxy và request từ proxy tới ứng dụng là HTTP. Nếu ứng dụng không nhận diện scheme gốc đúng cách, writer có thể không phát HSTS.

Không nên giải quyết bằng cách phát HSTS vô điều kiện trên mọi request. Hãy cấu hình proxy và forwarded headers đúng, đồng thời chỉ tin các forwarded header từ proxy đáng tin cậy.

### 4.2. Nhiều SecurityFilterChain

Nếu ứng dụng có nhiều `SecurityFilterChain`, header policy thuộc chain được chọn cho request. Kiểm tra HSTS trên một endpoint công khai không chứng minh chain quản trị hoặc API có cùng policy. Với mỗi chain cần bảo vệ, xác nhận headers không bị disable và HSTS writer được cấu hình nhất quán.

## 5. Cấu hình HSTS trong Spring Security Reactive

Với WebFlux, cấu hình qua `ServerHttpSecurity.headers(...)`:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .headers(headers -> headers
                .hsts(hsts -> hsts
                    .maxAge(Duration.ofDays(365))
                    .includeSubdomains(false)
                    .preload(false)))
            .authorizeExchange(auth -> auth
                .anyExchange().permitAll())
            .build();
    }
}
~~~

Tên method và cách biểu diễn thời hạn có thể khác giữa các phiên bản Spring Security. Hãy đối chiếu API của dependency đang dùng; nguyên tắc kiểm thử vẫn là xác nhận header HSTS chỉ xuất hiện trong secure context và có directive đúng policy.

Trong Reactive, trạng thái bảo mật được suy ra từ request mà WebFlux nhận. Nếu TLS kết thúc ở gateway, forwarded scheme phải được xử lý đúng và chỉ tin nguồn proxy đã kiểm soát.

## 6. MockMvc: kiểm tra HSTS trên request secure và insecure

MockMvc có thể mô phỏng request secure bằng `.secure(true)`. Đây là cách kiểm tra điều kiện HSTS writer ở tầng Servlet, không thực hiện TLS handshake.

### 6.1. Request secure phải có HSTS

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletHstsTests {

    @Autowired
    MockMvc mvc;

    @Test
    void secureRequestNhanHsts() throws Exception {
        mvc.perform(get("/public").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Strict-Transport-Security",
                containsString("max-age=31536000")));
    }

    @Test
    void insecureRequestKhongNhanHsts() throws Exception {
        mvc.perform(get("/public").secure(false))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                "Strict-Transport-Security"));
    }
}
~~~

Các test giả định endpoint `/public` tồn tại và trả `200`. Thay bằng endpoint thực của ứng dụng. Nếu policy mặc định hoặc cấu hình riêng có thời hạn khác, thay assertion theo giá trị đã duyệt.

### 6.2. Kiểm tra directive theo policy

Nếu ứng dụng bật `includeSubDomains`, kiểm tra directive này:

~~~java
@Test
void hstsCoIncludeSubDomainsTheoPolicy() throws Exception {
    mvc.perform(get("/public").secure(true))
        .andExpect(status().isOk())
        .andExpect(header().string(
            "Strict-Transport-Security",
            containsString("includeSubDomains")));
}
~~~

Nếu ứng dụng không bật `includeSubDomains`, không nên chỉ kiểm tra header tồn tại. Có thể kiểm tra giá trị không chứa directive đó để phát hiện cấu hình bị mở rộng ngoài ý muốn.

### 6.3. HSTS vẫn cần xuất hiện trên response lỗi secure

HSTS là response header ở tầng bảo mật, không chỉ dành cho controller trả 200. Có thể kiểm tra response xác thực bị từ chối:

~~~java
@Test
void unauthorizedSecureResponseVanCoHsts() throws Exception {
    mvc.perform(get("/admin/reports").secure(true))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            "Strict-Transport-Security",
            containsString("max-age=31536000")));
}
~~~

Kỳ vọng `401` giả định ứng dụng dùng entry point trả 401. Nếu dùng form login, status có thể là redirect. Điều quan trọng là response được tạo qua security chain vẫn có HSTS khi request được xem là secure.

### 6.4. Điều MockMvc không chứng minh

`.secure(true)` đánh dấu request mô phỏng là secure để HSTS writer xử lý. Nó không chứng minh:

- TLS certificate hợp lệ hoặc browser đã xác minh certificate.
- Reverse proxy production gửi forwarded headers chính xác.
- Browser đã lưu HSTS policy.
- Browser tự nâng cấp HTTP sang HTTPS ở lần truy cập sau.
- Host đã được đưa vào preload list.

Những điều đó cần kiểm thử HTTPS thực và browser/network environment.

## 7. WebTestClient: kiểm tra HSTS trong Reactive

WebTestClient có thể kiểm tra response header trong application context. Khi test HSTS, cần bảo đảm request URI được xem là HTTPS/secure theo cơ chế của phiên bản WebFlux đang dùng.

Ví dụ với WebTestClient gắn vào application context và base URL HTTPS để mô phỏng secure request URI:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveHstsTests {

    @Autowired
    ApplicationContext context;

    WebTestClient secureClient() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .baseUrl("https://localhost")
            .build();
    }

    @Test
    void secureUriNhanHsts() {
        secureClient().get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueMatches(
                "Strict-Transport-Security",
                ".*max-age=31536000.*");
    }
}
~~~

Test context này kiểm tra cách reactive security xử lý request có URI scheme HTTPS trong môi trường mock. Nó không thực hiện TLS handshake. Nếu phiên bản WebFlux/test client của dự án không đánh dấu request secure chỉ từ base URL, hãy dùng HTTPS test server hoặc dựng request có secure URI theo API hỗ trợ của phiên bản.

Để xác minh cả TLS và HSTS ở cấp server, chạy ứng dụng trên HTTPS test port, gọi bằng WebTestClient `bindToServer()` với SSL trust được cấu hình cho chứng chỉ test, sau đó kiểm tra header response. Không tắt xác minh certificate trong test production-like nếu mục tiêu là kiểm chứng chuỗi TLS.

## 8. Reverse proxy và TLS termination

Trong production, sơ đồ phổ biến:

~~~text
Browser -- HTTPS --> Load balancer / Reverse proxy
                           |
                           +-- TLS termination
                           |
                           +-- HTTP hoặc HTTPS --> Spring application
~~~

Nếu proxy giải mã TLS rồi gửi HTTP tới Spring, ứng dụng có thể thấy request không secure. HSTS writer khi đó có thể không phát header nếu ứng dụng không nhận biết scheme gốc.

Cần cấu hình forwarded headers theo kiến trúc, ví dụ Spring Boot hỗ trợ:

~~~properties
server.forward-headers-strategy=framework
~~~

Đây chỉ là ví dụ lựa chọn chiến lược xử lý forwarded headers. Cấu hình phải phù hợp proxy đang sử dụng và proxy phải ghi đè/loại bỏ các forwarded header do client tự gửi. **Không tin `X-Forwarded-Proto` từ Internet một cách vô điều kiện**; nếu không, client có thể giả mạo scheme và làm sai quyết định secure của ứng dụng.

Các bước kiểm tra:

1. Browser kết nối HTTPS tới proxy với certificate hợp lệ.
2. Proxy chuyển tiếp thông tin scheme gốc bằng cơ chế forwarded header đã thống nhất.
3. Spring chỉ tin forwarded header từ proxy đáng tin cậy.
4. Servlet/WebFlux nhận request ở trạng thái secure.
5. Response cuối cùng từ proxy vẫn có `Strict-Transport-Security`.
6. HTTP endpoint được redirect sang HTTPS; không dựa vào HSTS để thay thế redirect cho browser chưa có policy.

Nếu proxy tự thêm HSTS, hãy xác định rõ proxy hay Spring là nơi sở hữu header. Tránh cả hai cùng phát nhiều giá trị HSTS không nhất quán.

## 9. Kiểm tra HSTS trong môi trường thật

### 9.1. Dùng curl kiểm tra response HTTPS

~~~bash
curl -sSI https://portal.example.vn
~~~

Đối chiếu dòng:

~~~http
Strict-Transport-Security: max-age=31536000
~~~

Nếu có `includeSubDomains` hoặc `preload`, xác nhận các directive khớp policy đã duyệt. Lệnh này chỉ đọc response server; curl không lưu và thực thi HSTS như browser.

Kiểm tra HTTP:

~~~bash
curl -sSI http://portal.example.vn
~~~

Response HTTP thường nên redirect sang HTTPS. Không kỳ vọng browser chấp nhận HSTS header được gửi trên response HTTP; browser bỏ qua header này theo chuẩn.

### 9.2. Kiểm tra browser đã áp dụng policy

Trong browser test, dùng một host test riêng:

1. Truy cập HTTPS và nhận HSTS header.
2. Gọi cùng host qua HTTP.
3. Quan sát browser nâng cấp URL sang HTTPS trước khi gửi HTTP request mạng.
4. Kiểm tra certificate HTTPS hợp lệ.
5. Dùng profile/context mới để kiểm tra trạng thái chưa có policy; tránh nhầm kết quả do HSTS đã được lưu từ lần chạy trước.

Browser có thể có cơ chế quản lý HSTS riêng; không nên phụ thuộc vào một giao diện quản trị cụ thể khi viết bài test tự động. Điều quan trọng là quan sát request thực tế và xác nhận HTTP không được gửi khi policy đã được lưu.

### 9.3. Preload và lần truy cập đầu

Nếu yêu cầu bảo vệ cả lần đầu, cần xem xét preload list hoặc một cơ chế triển khai URL HTTPS từ đầu. Header HSTS động không bảo vệ browser trước khi browser nhận được policy lần đầu qua HTTPS.

Việc preload có tác động dài hạn và rộng tới subdomain. Hãy dùng domain thử nghiệm, hoàn tất kiểm kê HTTPS và tuân thủ quy trình đăng ký/gỡ preload của chương trình tương ứng.

## 10. Ma trận kiểm thử đề xuất

| Mã ca | Request | Kỳ vọng | Bằng chứng |
| --- | --- | --- | --- |
| HSTS-01 | Servlet request secure | Có HSTS, max-age đúng | MockMvc `.secure(true)` |
| HSTS-02 | Servlet request insecure | Không có HSTS | MockMvc `.secure(false)` |
| HSTS-03 | Secure request 401/403 | HSTS vẫn có | MockMvc qua security chain |
| HSTS-04 | Policy bật includeSubDomains | Header có directive | Assertion giá trị |
| HSTS-05 | Policy tắt includeSubDomains | Header không có directive | Assertion không chứa |
| HSTS-06 | Reactive request secure | Có HSTS | WebTestClient với secure URI/HTTPS |
| HSTS-07 | HTTPS qua proxy | Response cuối tuyến có HSTS | curl/browser qua proxy |
| HSTS-08 | HTTP endpoint | Redirect sang HTTPS; không dựa vào HSTS từ HTTP | HTTP integration/browser |
| HSTS-09 | Browser đã nhận HSTS | Truy cập HTTP được nâng cấp | Browser E2E |
| HSTS-10 | Preload policy | Domain đáp ứng tiêu chí preload | Kiểm tra quy trình và danh sách preload, không chỉ header |

Không gộp HSTS với CORS. CORS điều khiển chia sẻ response cross-origin; HSTS yêu cầu browser dùng HTTPS cho host đã có policy. Một API có CORS đúng nhưng HSTS thiếu vẫn có thể chưa đáp ứng chính sách truyền tải bảo mật.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| MockMvc request secure không có HSTS | Header writer bị disable, chain không khớp hoặc policy tùy chỉnh | Kiểm tra headers DSL và filter chain |
| MockMvc HTTP vẫn có HSTS | Có writer tùy chỉnh phát vô điều kiện hoặc test đánh dấu secure ngoài dự kiến | Kiểm tra toàn bộ response header writers |
| Production HTTPS không có HSTS | TLS terminate ở proxy nhưng Spring không nhận scheme gốc | Kiểm tra forwarded headers và proxy trust |
| HSTS chỉ có ở một số path | Nhiều SecurityFilterChain với header config khác nhau | Xác định chain được chọn theo path |
| HSTS có max-age quá ngắn | Cấu hình khác giữa môi trường hoặc writer bị override | Đối chiếu giá trị response cuối |
| Subdomain không truy cập được | Domain cha bật includeSubDomains nhưng subdomain chưa có HTTPS | Kiểm kê subdomain, certificate và redirect |
| Browser vẫn gửi HTTP lần đầu | Host chưa có dynamic policy hoặc chưa nằm trong preload list | Kiểm tra first-visit/preload |
| Đã đặt max-age=0 nhưng browser vẫn nâng cấp | Policy preload hoặc policy kế thừa từ domain cha còn hiệu lực | Kiểm tra policy nguồn và trạng thái preload |
| Response có nhiều HSTS header | Proxy và Spring cùng ghi header | Chỉ định một nơi sở hữu policy |

## 12. Bài thực hành và tiêu chí hoàn thành

Một ứng dụng có host `portal.example.test` chạy qua reverse proxy TLS. Nhóm yêu cầu HSTS một năm, chưa bật `includeSubDomains` và chưa đăng ký preload.

Hãy thực hiện:

1. Cấu hình HSTS trong Spring Security Servlet hoặc Reactive với `max-age=31536000`, `includeSubDomains=false`, `preload=false`.
2. Viết MockMvc test secure request có HSTS và insecure request không có HSTS.
3. Kiểm tra response 401/403 trên request secure vẫn có HSTS theo policy.
4. Viết WebTestClient test cho reactive secure request; xác minh cách test client đánh dấu scheme secure trong phiên bản đang dùng.
5. Cấu hình forwarded headers qua proxy đáng tin cậy; xác nhận response HTTPS cuối tuyến có HSTS.
6. Kiểm tra HTTP redirect sang HTTPS và xác nhận không dựa vào header HSTS từ response HTTP.
7. Dùng browser E2E để xác nhận sau khi nhận HSTS qua HTTPS, lần truy cập HTTP tiếp theo được nâng cấp.
8. Không bật `includeSubDomains` hoặc `preload` khi chưa có phê duyệt và kiểm kê phạm vi.

**Tiêu chí hoàn thành:** bạn chứng minh được HSTS chỉ được phát trong secure context, có `max-age` và directive đúng policy, vẫn xuất hiện trên các response bảo mật cần thiết, hoạt động qua proxy TLS và được browser áp dụng sau khi nhận header từ HTTPS.

**Điểm cần nhớ:** `.secure(true)` trong MockMvc hoặc một HTTPS URI mô phỏng trong WebTestClient chỉ kiểm tra logic ghi header. Để khẳng định HSTS hoạt động trong production, cần kiểm tra HTTPS thật, proxy/forwarded headers và hành vi nâng cấp request của browser.
