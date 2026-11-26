# HSTS không xuất hiện do nhận diện sai HTTPS sau proxy

> **Chương:** Chẩn đoán lỗi  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Hiện tượng: URL public là HTTPS nhưng Strict-Transport-Security biến mất

Một ứng dụng Spring Boot được triển khai sau load balancer:

~~~text
Browser --HTTPS--> Load balancer / reverse proxy --HTTP--> Spring Boot
~~~

Người dùng truy cập:

~~~http
GET https://app.example.com/account
~~~

Trên response public, những header bảo vệ khác vẫn hiện diện:

~~~http
HTTP/1.1 200 OK
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
~~~

Nhưng **không thấy**:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Trong khi đó, khi chạy ứng dụng trực tiếp qua HTTPS, HSTS lại xuất hiện. Nhiều người quy kết ngay Spring Security không bật headers hoặc lỗi firewall, nhưng nguyên nhân có thể là: **Spring Security cho rằng request đang là HTTP**, vì nó thấy kết nối từ proxy đến ứng dụng thay vì scheme HTTPS mà browser đã dùng.

Đây là lỗi chẩn đoán quan trọng bởi việc “sửa nhanh” bằng cách:

- Tắt kiểm tra HSTS chỉ để scanner xanh;
- Bỏ cookie `Secure`;
- Cho client tự gửi `X-Forwarded-Proto: https`;
- Bật HSTS preload hoặc `includeSubDomains` trên toàn hệ thống không kiểm tra;

đều có thể dẫn tới vấn đề bảo mật hoặc vận hành lớn hơn.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích HSTS hoạt động thế nào và vì sao browser chỉ tin header trên kết nối HTTPS hợp lệ.
2. Phân biệt scheme của **browser → proxy** với scheme **proxy → application**.
3. Hiểu điều kiện ghi HSTS của Spring Security Servlet và WebFlux, cùng cơ chế nhận diện request secure.
4. Chẩn đoán `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port`, trusted proxies và cấu hình Spring Boot.
5. Phân biệt **Spring-owned** và **edge-owned** HSTS; ngăn ghi đè/trùng hoặc cache mất header.
6. Kiểm thử bằng DevTools, curl, MockMvc, WebTestClient và môi trường HTTPS thực, kể cả negative tests chống spoofing.

## 2. HSTS là gì? Browser nhớ chính sách HTTPS cho host

*HTTP Strict Transport Security* (HSTS) cho phép một HTTPS website thông báo browser rằng trong một khoảng thời gian, các truy cập tới host đó phải dùng HTTPS.

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

| Thành phần | Ý nghĩa | Điểm cần kiểm tra |
|---|---|---|
| `Strict-Transport-Security` | Header thiết lập chính sách HSTS | Có trong **HTTPS response public** phù hợp hay không? |
| `max-age=31536000` | Thời gian browser ghi nhớ, tính theo giây (ví dụ một năm) | Giá trị có đúng kế hoạch triển khai? |
| `includeSubDomains` | Mở rộng chính sách đến subdomain | Các subdomain có hỗ trợ HTTPS đầy đủ? |
| `preload` | Tín hiệu mong muốn được đưa vào danh sách preload | Không tự động bảo đảm được preload |

Trong thời gian HSTS có hiệu lực, browser hỗ trợ có thể tự nâng cấp các URL HTTP tới host thành HTTPS trước khi gửi request. Do đó người dùng có thể gõ `http://app.example.com` nhưng DevTools quan sát thấy kết nối HTTPS thực.

**Quan trọng:** HSTS không cung cấp TLS, không sửa certificate, không thay thế HTTPS redirect, không xác thực người dùng và không thay thế CSP, CSRF, CORS, security headers khác hoặc session protection. Nó hỗ trợ giảm nguy cơ giao tiếp HTTP sau khi browser đã biết/chấp nhận chính sách.

### Browser xử lý HSTS trên HTTPS, không trên HTTP

~~~http
HTTP/1.1 200 OK
Strict-Transport-Security: max-age=31536000
~~~

nếu được truyền qua **HTTP không an toàn**, browser phải bỏ qua khi thiết lập HSTS policy. Việc một HTTP origin trả header STS không chứng minh browser đã được bảo vệ.

Vì thế, không thể kết luận “Spring HSTS đang lỗi” chỉ từ:

~~~bash
curl -i http://localhost:8080/
~~~

Phép thử quyết định là **HTTPS public response**, nơi browser thực sự kết nối TLS với hostname được phục vụ.

## 3. HSTS không giải quyết “lần truy cập HTTP đầu tiên” theo cách tự động

HSTS thông thường là một chính sách browser học được sau khi nhận header qua HTTPS hợp lệ. Nếu người dùng chưa từng truy cập HTTPS host và host chưa nằm trong danh sách preload, một kết nối HTTP ban đầu vẫn có thể xảy ra trước khi browser biết chính sách.

### HTTP redirect và HSTS có vai trò khác

~~~mermaid
sequenceDiagram
    participant B as Browser chưa biết HSTS
    participant P as Reverse proxy
    participant S as Spring Boot
    B->>P: GET http://app.example.com/
    P-->>B: 301/308 đến https://app.example.com/
    B->>P: GET https://app.example.com/
    P->>S: HTTP upstream GET /
    S-->>P: 200 + các application headers
    P-->>B: HTTPS 200 + Strict-Transport-Security
    Note over B: Browser lưu HSTS khi HTTPS hợp lệ
~~~

HTTP redirect giúp hướng client đến HTTPS, còn HSTS giúp browser **ghi nhớ** để những lần sau tự ưu tiên HTTPS. Không dùng header HSTS trên HTTP thay cho redirect hoặc ép một backend HTTP nội bộ phải giả làm HTTPS.

## 4. Tại sao TLS termination khiến Spring có thể nhìn sai scheme?

Kiến trúc phổ biến:

~~~mermaid
flowchart LR
    A["Browser https://app.example.com"] -->|TLS HTTPS| B[Edge / load balancer]
    B -->|HTTP nội bộ| C[Spring Boot :8080]
    C --> D[Spring Security HSTS writer]
~~~

Browser thấy HTTPS; proxy giải mã TLS rồi gửi request qua HTTP vào backend. Nếu Spring chỉ dựa vào kết nối nội bộ:

~~~java
request.isSecure()       // false
request.getScheme()      // "http"
request.getServerPort()  // có thể là port upstream, ví dụ 8080
~~~

Trên Servlet, Spring Security HSTS writer mặc định chỉ áp HSTS khi request được nhận diện là **secure**. Vậy một HTTPS request từ browser có thể **không** có HSTS dù `HeaderWriterFilter` đã chạy.

### Một trường hợp quan trọng: những headers khác vẫn đúng

Nếu `X-Content-Type-Options` và `X-Frame-Options` vẫn xuất hiện nhưng HSTS biến mất, đó là một dấu hiệu đáng kiểm tra **secure-request detection**, thay vì kết luận toàn bộ header writer đã không chạy.

Tuy nhiên, cũng phải kiểm tra một vài nguyên nhân khác: HSTS bị disable trên chain này, response được proxy/CDN phục vụ ngoài Spring hoặc header bị edge strip. Không thể kết luận chỉ từ sự hiện diện của hai header khác.

## 5. Ba góc nhìn của một request qua proxy

| Vị trí | Scheme mà tầng đó thường thấy | Ai có trách nhiệm? |
|---|---|---|
| Browser → public host | HTTPS | Browser xác minh TLS certificate; xử lý HSTS của public response |
| Proxy ingress | HTTPS ở downstream connection | Edge chấm dứt TLS, tạo metadata forwarding đáng tin cậy |
| Proxy → Spring Boot | Có thể là HTTP | Application cần hiểu scheme public **qua proxy tin cậy**, không qua input client tùy ý |

Một response đi từ Spring tới browser qua proxy nhưng **HSTS vẫn mang ý nghĩa cho public host**. Nếu HSTS được phát tại Spring, ứng dụng phải biết request public đã dùng HTTPS. Nếu HSTS được phát tại edge, nó phải xuất hiện trên HTTPS response cuối cùng bất kể backend nhìn upstream như thế nào.

### Đừng nhầm TLS của backend với TLS của browser

Có hai kiến trúc hợp lệ:

~~~text
A. TLS termination:
Browser --HTTPS--> Proxy --HTTP private network--> Spring

B. TLS re-encryption:
Browser --HTTPS--> Proxy --HTTPS--> Spring
~~~

Kiến trúc B có thể giúp backend nhìn request secure, nhưng vẫn cần quản lý certificate, scheme/Host, client trust và forwarding chính xác. **Không khuyến nghị đổi từ A sang B chỉ để có header HSTS** khi có giải pháp cấu hình proxy/app đúng và phù hợp threat model.

## 6. HSTS default trong Spring Security Servlet

Trên stack Servlet:

- `FilterChainProxy` chọn `SecurityFilterChain` phù hợp.
- `HeaderWriterFilter` áp các header writers đã cấu hình.
- `HstsHeaderWriter` xử lý `Strict-Transport-Security`.
- Header writer HSTS có điều kiện chỉ thêm header trên request được coi là secure theo policy mặc định.

Trong nhiều cấu hình Spring Security hiện đại, HSTS được bật mặc định cho HTTPS requests. Nếu `HttpSecurity.headers(...)` đã được disable hoặc writer HSTS bị disable, HSTS có thể thiếu dù `request.isSecure() == true`.

### Đọc trình tự chẩn đoán

~~~text
GET HTTPS public → HTTP upstream Spring
  → Có matching SecurityFilterChain?
  → HeaderWriterFilter được bật?
  → HstsHeaderWriter được bật?
  → Request được servlet API coi là secure?
  → Response có STS tại Spring origin?
  → Proxy/CDN có giữ STS tới browser?
~~~

**Không dùng test chỉ có MockMvc** để kết luận tất cả các bước trên đúng qua production proxy; MockMvc không mô phỏng TLS termination ngoài ứng dụng.

## 7. Forwarded và X-Forwarded-Proto: metadata về request gốc

Proxy thường bổ sung metadata cho backend biết request công khai có scheme nào:

~~~http
GET /account HTTP/1.1
Host: app-internal:8080
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.com
X-Forwarded-Port: 443
~~~

Hoặc header chuẩn RFC 7239:

~~~http
Forwarded: for=192.0.2.10;proto=https;host=app.example.com
~~~

`X-Forwarded-Proto: https` **chỉ là một header chuỗi** cho đến khi tầng ứng dụng tin cậy và xử lý nó. Bản thân việc header xuất hiện trong request không bảo đảm `request.isSecure()` chuyển thành true.

### Các thành phần hay bị nhầm

| Header | Thông tin dự định mang | Ảnh hưởng nếu xử lý sai |
|---|---|---|
| `Forwarded: proto=...` | Scheme phía client/chuỗi proxy | Secure detection, redirect URLs |
| `X-Forwarded-Proto` | Scheme của request trước proxy | HSTS writer, absolute redirects, cookie |
| `X-Forwarded-Host` | Host công khai | URL generation, links và origin checks |
| `X-Forwarded-Port` | Public port | Redirect sai port, Origin/host mismatch |
| `X-Forwarded-For` | Thông tin client IP qua proxy | IP-based controls/logs nếu trust chain sai |
| `X-Forwarded-Prefix` | Path prefix được proxy thêm | Route/url generation và path scoping theo stack |

Không phải deployment nào cũng hỗ trợ/tin mọi header trên; cần hợp đồng proxy rõ ràng, không “bật tất cả” thiếu kiểm soát.

## 8. Trust boundary: không tin Forwarded do client tự gửi

Một client có thể tự gửi:

~~~http
GET /account HTTP/1.1
Host: app.example.com
X-Forwarded-Proto: https
X-Forwarded-Host: attacker.example.net
~~~

Nếu backend **trực tiếp nhận request từ Internet** và chấp nhận những giá trị này không qua proxy đáng tin, attacker có thể làm ứng dụng hiểu sai scheme/host. Tác động không giới hạn HSTS: có thể tạo redirect độc hại, link reset-password sai host, cookie attributes không phù hợp, Origin policy sai hoặc làm sai IP-based checks.

### Quy tắc triển khai an toàn

1. **Chỉ nhận traffic application từ reverse proxy đáng tin**, không để port backend bị truy cập trực tiếp từ Internet nếu hệ thống dựa vào forwarded metadata.
2. Proxy **xóa/ghi đè** các `Forwarded`/`X-Forwarded-*` do client gửi, sau đó đặt giá trị do chính proxy đo được.
3. Định nghĩa rõ trường hợp nhiều proxies: ai là trust boundary, ai ghi/append header và component nào được quyền đọc.
4. Không dùng `ForwardedHeaderFilter` như một **cơ chế xác thực proxy**: nó diễn giải header, không tự xác minh header có đến từ nguồn đáng tin.
5. Có negative tests cho header giả mạo và kết nối HTTP thực để tránh bật secure behavior do client tự khai.

**Không sửa HSTS bằng cách mở endpoint cho phép mọi client gửi `X-Forwarded-Proto: https` rồi framework tin ngay.** Phải thiết kế đường đi và trust model trước.

## 9. Lựa chọn nơi sở hữu HSTS: Spring hay HTTPS edge?

| Phương án | Cách hoạt động | Khi phù hợp | Điều cần chú ý |
|---|---|---|---|
| Spring-owned HSTS | App dùng secure detection đúng, Spring Security header writer phát STS | Một app/host có security configuration tập trung | Cấu hình forwarded headers đúng, chain match, proxy không strip |
| Edge-owned HSTS | Reverse proxy/CDN thêm STS trên HTTPS responses | Nhiều services sau cùng TLS termination, edge kiểm soát public hostname | Policy nhất quán trên success/error/cache/redirect HTTPS |
| Phối hợp có phân quyền | Edge bảo đảm STS, app có thể phát header tương thích trên một số routes | Kiến trúc nhiều lớp đã review | Không phát giá trị xung đột hoặc bị override bất ngờ |

**Không nhất thiết mọi service phải tự phát HSTS** nếu HTTPS edge đã chịu trách nhiệm cho hostname công khai. Điều cần đánh giá là browser thực sự nhận một chính sách HSTS phù hợp trên HTTPS responses.

Nếu HSTS được phát ở cả app và edge, phải đảm bảo các giá trị nhất quán: `max-age`/`includeSubDomains`/`preload` khác nhau giữa các response có thể làm browser cập nhật policy ngoài ý muốn.

## 10. Spring Boot: server.forward-headers-strategy là chìa khóa thường gặp

Spring Boot có cơ chế xử lý forwarded headers theo environment và stack:

~~~properties
# Ví dụ khi ứng dụng nằm sau proxy đáng tin.
server.forward-headers-strategy=framework
~~~

Với Servlet, chế độ framework có thể đăng ký cơ chế xử lý kiểu `ForwardedHeaderFilter` của Spring Framework; với Reactive/WebFlux, sử dụng cơ chế `ForwardedHeaderTransformer` tương ứng. Kết quả mong muốn là request wrapper/URI mà các thành phần Spring dùng phản ánh public scheme/host/port đúng.

### Các lựa chọn thường gặp

| Giá trị | Ý nghĩa khái quát | Điều cần lưu ý |
|---|---|---|
| `none` | Không bật cơ chế forwarded headers tự động theo lựa chọn Boot | App có thể tiếp tục nhìn upstream HTTP |
| `framework` | Dùng cơ chế xử lý forwarded headers của Spring Framework | Trust boundary phải được bảo đảm ở proxy/network |
| `native` | Dùng cơ chế của servlet container hoặc HTTP server nếu hỗ trợ | Cấu hình và hỗ trợ cụ thể phụ thuộc container/version |

**Không bật đồng thời nhiều cách diễn giải forwarded headers một cách tùy tiện.** Ví dụ một Tomcat `RemoteIpValve` native và một `ForwardedHeaderFilter` được tự đăng ký thêm có thể làm việc xác định scheme/host khó dự đoán. Chọn một cơ chế phù hợp và kiểm thử đầu ra.

### Phân biệt biến môi trường và property

Với Spring Boot, property có thể được cung cấp qua environment-specific configuration:

~~~properties
server.forward-headers-strategy=framework
~~~

hoặc theo chuẩn biến môi trường do Boot xử lý:

~~~text
SERVER_FORWARD_HEADERS_STRATEGY=framework
~~~

**Không đặt chung cấu hình này trên một service backend có thể bị client Internet gọi trực tiếp** khi client tự kiểm soát forwarded headers. Chỉ nên dùng sau một proxy đáng tin đã sanitize headers.

### Nếu thay đổi property mà HSTS vẫn thiếu

Kiểm tra:

1. Profile nào thực sự đang chạy? Có property khác ghi đè không?
2. Request có đúng `X-Forwarded-Proto: https` hoặc `Forwarded: proto=https` do proxy đặt không?
3. Application có trực tiếp nhận request từ Internet không?
4. Có custom `Filter`/`WebFilter` hoặc container valve đã xử lý forwarded headers một lần nữa không?
5. Response được Spring origin tạo hay do CDN trả?
6. Request khớp security chain có HSTS writer chưa?

`server.forward-headers-strategy` **không tự bật HSTS writer đã bị disable**, cũng không bắt CDN giữ header từ Spring.

## 11. Servlet: cách ForwardedHeaderFilter tác động tới request

`ForwardedHeaderFilter` thuộc Spring Framework trên Servlet stack. Khi được cấu hình đúng thứ tự và request đi qua proxy được tin cậy, nó có thể diễn giải forwarded headers để downstream components nhìn thấy public URL attributes.

Ví dụ before/after ở application layer:

~~~text
Trước xử lý forwarded headers:
  request.getScheme()      = "http"
  request.isSecure()       = false
  request.getServerName()  = "service-internal"
  request.getServerPort()  = 8080

Proxy gửi:
  X-Forwarded-Proto: https
  X-Forwarded-Host: app.example.com
  X-Forwarded-Port: 443

Sau xử lý hợp lệ:
  request.getScheme()      = "https"
  request.isSecure()       = true
  request.getServerName()  = "app.example.com"
  request.getServerPort()  = 443
~~~

Đây là **kỳ vọng minh họa**, không phải output đã thu từ một deployment cụ thể. Cần đối chiếu với Java code/response ở environment và servlet container đang dùng.

### Vì sao thứ tự filter quan trọng?

Nếu request wrapper áp forwarded headers **sau khi Spring Security đã kiểm tra secure condition**, HSTS writer có thể vẫn thấy HTTP. Spring Boot framework mode thường hỗ trợ đăng ký ở vị trí thích hợp, nhưng một custom filter registration có thể làm sai thứ tự.

Không tạo thêm filter thủ công nếu Boot đã auto-configure nó, trừ khi có lý do rõ ràng và test order. Trong Servlet, filter registration order giữa container, `DelegatingFilterProxy`, `FilterChainProxy` và custom filters phải được xem như một phần của security architecture.

### ForwardedHeaderFilter không là firewall

Nó **không xác thực nguồn gửi metadata forwarded**. Trách nhiệm chỉ tin header từ proxy thuộc network design và proxy configuration. Nếu app bị bypass proxy, filter có thể đọc dữ liệu giả mạo từ client; đây là điều kiện phải ngăn trước khi bật.

## 12. Servlet: cấu hình SecurityFilterChain giữ HSTS header writer

Một cấu hình Spring Security Servlet minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpProtectionConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/login", "/assets/**").permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().authenticated()
        );

        http.formLogin(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());

        // Giữ các header writers mặc định, gồm HSTS trên secure requests
        // khi cấu hình/version áp dụng chính sách mặc định tương ứng.
        http.headers(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là cấu hình **minh họa một chain**. Nếu có nhiều security chains, cần kiểm tra chain thật sự match path. Nếu app sử dụng custom headers configuration, không nên coi `Customizer.withDefaults()` là một phép ghi đè an toàn để khôi phục mọi policy.

### Cấu hình HSTS có kiểm soát

Với các phiên bản Spring Security Servlet hỗ trợ lambda DSL:

~~~java
http.headers(headers -> headers
    .httpStrictTransportSecurity(hsts -> hsts
        // Ngắn hạn cho giai đoạn thử nghiệm, không phải khuyến nghị cuối.
        .maxAgeInSeconds(86400)
        .includeSubDomains(false)
    )
);
~~~

Ví dụ dùng `max-age=86400` (một ngày) để minh họa chỉnh policy có chủ đích; production cần chọn thời hạn theo kế hoạch rollout và DNS/TLS của host. Đừng thêm `preload(true)` hay `includeSubDomains(true)` chỉ để làm scanner báo “đầy đủ”.

**Hai điều kiện độc lập:** header writer phải được bật **và** request phải được nhận diện secure. Tăng `maxAgeInSeconds` không làm HSTS xuất hiện nếu `request.isSecure()` vẫn false.

### Không disable toàn bộ HTTP headers

~~~java
// Phản ví dụ: có thể làm mất nhiều lớp bảo vệ cùng lúc.
http.headers(headers -> headers.disable());
~~~

Một cấu hình như trên làm thiếu `X-Content-Type-Options`/framing headers/HSTS từ Spring Security, không chỉ HSTS. Nếu thiếu **duy nhất HSTS** trên HTTPS sau proxy, trước tiên kiểm tra secure detection và header writer HSTS cụ thể.

## 13. Servlet: nhiều SecurityFilterChain có thể tạo lỗ hổng header theo path

Ví dụ:

~~~text
@Order(1)  API chain: /api/**
@Order(2)  Web chain: /account/** và /login
             (không có fallback cho /assets/**)
~~~

Nếu `/account` có HSTS nhưng `/assets/app.js` không, nguyên nhân không nhất thiết do proxy scheme: asset có thể **không khớp chain nào**, bị `web.ignoring()`, hoặc được CDN phục vụ ngoài Spring.

### Một fallback chain an toàn

~~~java
import org.springframework.core.annotation.Order;

@Bean
@Order(3)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/assets/**", "/favicon.ico").permitAll()
        .anyRequest().authenticated()
    );
    // Không disable default security headers.
    return http.build();
}
~~~

**Đây là snippet bổ sung trong cấu hình có nhiều chains**, cần giữ rõ bean ordering, auth mechanism, CSRF và các filters cần cho từng route. Không cho toàn bộ fallback `permitAll()` chỉ để HSTS xuất hiện.

Nếu request được `web.ignoring().requestMatchers("/assets/**")` loại khỏi security chain, dù có fallback chain cũng **không áp HSTS writer** trên path bị ignore. Dùng `permitAll()` để public asset vẫn đi qua security chain khi đó là mô hình mong muốn.

### HSTS trên tài nguyên tĩnh có ý nghĩa thế nào?

HSTS là chính sách của **host** mà browser học được từ HTTPS response, không phải chỉ riêng HTML. Một HTTPS asset response có thể chứa HSTS; tuy nhiên việc từng static asset thiếu header cần được đánh giá theo mức bao phủ HSTS của host và điểm phát header. Không bắt CSP/Cache-Control của HTML phải giống của JS chỉ vì cùng host.

## 14. Mẫu Nginx: chuyển tiếp scheme đúng cho Spring-owned HSTS

Giả sử Nginx nhận HTTPS public và proxy đến Spring HTTP nội bộ. **Ví dụ dành cho hạ tầng do nhóm quản lý**:

~~~nginx
server {
    listen 443 ssl;
    server_name app.example.com;

    # TLS certificate/key, TLS policy... do hệ thống thực triển khai.

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;

        # Proxy tự đặt metadata public, không dùng giá trị client tự khai.
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;

        # Ví dụ chặn header Forwarded do client gửi vào upstream;
        # chuỗi proxy nhiều tầng cần thiết kế chính sách riêng.
        proxy_set_header Forwarded "";
    }
}
~~~

Khi Nginx thực sự nhận request HTTPS trên 443, `$scheme` thường là `https` và `$server_port` là 443. Spring Boot với `server.forward-headers-strategy=framework` có cơ hội diễn giải đúng public scheme nếu trust boundary được bảo đảm.

### Tại sao phải làm sạch header từ client?

Một reverse proxy không nên chuyển tiếp nguyên header `Forwarded` và các `X-Forwarded-*` không đáng tin mà không kiểm soát. Khi chạy nhiều hops (CDN → ingress → Nginx → Spring), quy tắc rewrite/append phải được thiết kế nhất quán; ví dụ Nginx trên **chỉ là mô hình một proxy TLS terminator**.

**Không copy Nginx config này vào production mà bỏ qua TLS config, access controls và đường proxy nhiều lớp.** Nginx có thể đứng sau một CDN/TLS terminator khác, khi đó `$scheme` ở Nginx nội bộ có thể là HTTP chứ không phải HTTPS public; phải xác định hop nào đáng tin và public scheme ở đâu.

## 15. Mẫu Nginx: để HTTPS edge tự phát HSTS

Một hướng khác là chọn Nginx làm HSTS owner tại public TLS terminator:

~~~nginx
server {
    listen 443 ssl;
    server_name app.example.com;

    # Chính sách minh họa ngắn hạn; production quyết định riêng.
    add_header Strict-Transport-Security "max-age=86400" always;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
~~~

Với Nginx, `always` giúp áp dụng header với nhiều HTTP status codes hơn thay vì chỉ vài status mặc định. Tuy vậy, cách kế thừa `add_header` giữa `server`/`location` có thể khiến một cấu hình `add_header` ở location ảnh hưởng bộ headers được thừa hưởng. Phải test thực tế **200/302/401/403/404/500** trên HTTPS public, không suy từ một directive trong file.

### Có nên đồng thời bật HSTS ở Spring?

Có thể phối hợp, nhưng nên **xác định một chủ sở hữu policy chính**. Nếu Spring và edge phát các giá trị STS khác nhau, browser có thể cập nhật chính sách theo response mà nó nhận cuối; điều đó làm rollout/rollback khó quản lý.

Đừng dùng việc thêm STS ở edge để che thiếu TLS hoặc một hệ thống còn HTTP subdomain chưa sẵn sàng. Cũng đừng nghĩ sửa HSTS edge xong là có thể bỏ xử lý forwarded headers nếu ứng dụng còn dùng scheme/host để tạo redirect, cookie `Secure` hoặc OAuth callback URLs.

## 16. Khi có nhiều proxies, chọn cách tin cậy theo chuỗi hop

Kiến trúc:

~~~mermaid
flowchart LR
    B[Browser HTTPS] --> C[CDN TLS termination]
    C --> I[Ingress / gateway]
    I --> N[Nginx nội bộ]
    N --> S[Spring Boot]
~~~

Nếu CDN nhận HTTPS nhưng kết nối CDN → ingress qua HTTP, tại ingress:

~~~text
Internal request scheme tại ingress = http
Public browser scheme tại CDN = https
~~~

Khi ingress vô ý ghi đè `X-Forwarded-Proto: http`, Spring có thể xem request là insecure dù browser thật sự dùng HTTPS.

### Các câu hỏi phải được giải quyết

1. Hop nào là **public TLS terminator**?
2. Header nào biểu diễn scheme public được tin cậy? `Forwarded` hay `X-Forwarded-Proto`?
3. Tầng nào **sanitize** dữ liệu forwarded do client gửi?
4. Hop nào cần bảo toàn scheme public và hop nào được quyền thay?
5. Có gửi cả `Forwarded: proto=https` và `X-Forwarded-Proto: http` mâu thuẫn không?
6. Spring Boot đang dùng `framework` hay `native` forwarded processing?
7. Có static files được phục vụ tại CDN, không vào Spring không?

Một chuỗi proxy với forward metadata mâu thuẫn không thể chữa bằng cách thêm một header ngẫu nhiên tại backend. Cần quy ước **nguồn sự thật và trust chain**.

## 17. WebFlux: HTTPS public nhưng Reactive request URI vẫn là HTTP

Trên WebFlux/Reactive, các thành phần khác Servlet:

| Servlet | Reactive/WebFlux |
|---|---|
| `HttpServletRequest#isSecure()` | `ServerHttpRequest` và thông tin URI/SSL |
| `ForwardedHeaderFilter` | `ForwardedHeaderTransformer` |
| `HeaderWriterFilter`/`HstsHeaderWriter` | `HttpHeaderWriterWebFilter`/reactive HSTS writer |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `MockMvc` | `WebTestClient` |

Trong WebFlux, Spring Framework có `ForwardedHeaderTransformer` để xử lý forwarded metadata ở thời điểm phù hợp trong web handling. Khi app chỉ nhìn thấy HTTP upstream, URI request có thể mang scheme `http` và reactive HSTS writer có thể không nhận diện đây là secure request.

### Spring Boot property cho WebFlux

~~~properties
# Chỉ dùng khi edge/proxy đáng tin đã đặt/sanitize forwarded headers.
server.forward-headers-strategy=framework
~~~

Khi WebFlux Boot framework mode đã cấu hình forwarding đúng, scheme/host/port sau transform có thể phản ánh public HTTPS. **Không đăng ký trùng một `ForwardedHeaderTransformer` thủ công khi Boot đã tự thiết lập nó**, nếu không có lý do và kiểm thử rõ ràng.

### Không sử dụng Servlet filter cho WebFlux

`ForwardedHeaderFilter`/`HttpServletRequest.isSecure()` là khái niệm của Servlet. Trong WebFlux, hãy xem `ServerWebExchange` và request URI/SSL information, `ForwardedHeaderTransformer`, `SecurityWebFilterChain` và header writer Reactive.

## 18. WebFlux: SecurityWebFilterChain và HSTS

Ví dụ một WebFlux application bảo vệ API và cho phép trang public:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveHttpProtectionConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        http.authorizeExchange(auth -> auth
            .pathMatchers("/", "/login", "/assets/**").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().authenticated()
        );

        http.formLogin(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());
        http.headers(Customizer.withDefaults());
        return http.build();
    }
}
~~~

HSTS được xử lý qua Reactive HTTP security headers infrastructure khi được bật trong version/cấu hình phù hợp và request được nhận là secure. **Đừng lẫn trình tự với Servlet filter chain** hoặc giả định một cấu hình custom trên MVC tự áp sang WebFlux.

### Nếu chỉ có Reactive API chain

~~~java
http.securityMatcher(
    ServerWebExchangeMatchers.pathMatchers("/api/**")
);
~~~

Nếu không có fallback chain, `/assets/**` hoặc `/login` không đi vào HSTS writer của API chain. Trong trường hợp này cần kiểm tra chain coverage song song với forwarded scheme.

### Tránh đặt HSTS theo cách bỏ qua secure check

Không giải quyết bằng cách tự chèn STS vào mọi response kể cả HTTP origin rồi coi như browser đã được bảo vệ. Trên HTTP public, browser **không chấp nhận HSTS policy**. Nếu edge sở hữu HTTPS HSTS, giải pháp nên nằm trên TLS terminator của host công khai.

## 19. Kiểm tra public HTTPS trước khi thay đổi Spring code

Phép đo đầu tiên nên đi qua hostname thực mà browser sử dụng:

~~~bash
curl -i 'https://app.example.com/account'
~~~

Nếu request cần authentication, nó có thể trả 302 login hoặc 401. Điều quan trọng ở bước này là kiểm tra STS trên **HTTPS response cuối cùng**. Có thể chọn một public GET ổn định như `/login` thay vì gọi endpoint dữ liệu nhạy cảm.

Để chỉ lấy response headers mà vẫn sử dụng GET:

~~~bash
curl -sS -D - -o /dev/null 'https://app.example.com/login'
~~~

Không sử dụng `curl -I` (HEAD) làm phép thử duy nhất: proxy, routing hoặc filter matcher có thể xử lý HEAD khác GET. Không tự thêm `-k` bỏ xác thực TLS để “sửa” lỗi HSTS; HSTS phải đi cùng một HTTPS host có certificate hợp lệ.

### Đọc đúng HTTP response

~~~http
HTTP/2 200
strict-transport-security: max-age=31536000; includeSubDomains
~~~

Hoặc:

~~~http
HTTP/2 302
location: /login
strict-transport-security: max-age=31536000; includeSubDomains
~~~

Header STS là case-insensitive về tên HTTP header; khi so từ logs/tool, `Strict-Transport-Security` và `strict-transport-security` chỉ khác cách hiển thị.

### Tránh nhầm redirect HTTP với HTTPS

Một yêu cầu:

~~~bash
curl -i 'http://app.example.com/'
~~~

có thể trả:

~~~http
HTTP/1.1 301 Moved Permanently
Location: https://app.example.com/
~~~

Không có STS trên **HTTP 301** không tự là lỗi, vì browser không thể học HSTS từ HTTP không an toàn. Cần làm **request HTTPS tiếp theo**, rồi quan sát STS response đó.

Để phân tích redirect, không dùng `curl -L` một cách mù quáng nếu mục tiêu là biết tầng nào tạo từng response. Khi cần theo redirect, ghi nhận từng hop và không gửi credentials/secrets tới host ngoài danh sách được tin cậy.

## 20. DevTools: HSTS header của chính HTTPS response

Mở browser DevTools → Network trước khi tải trang; bật Preserve log nếu có redirect. Chọn **response HTTPS** từ public hostname, kiểm tra:

| Điểm quan sát | Giá trị cần đọc | Kết luận có thể rút |
|---|---|---|
| Request URL | `https://app.example.com/...` | Browser đã dùng HTTPS ở hop public |
| Response Headers | `Strict-Transport-Security` | Browser có cơ hội nhận HSTS policy |
| Status | 200, 302, 401, 403, 404, 500 | Header có bị mất ở một branch? |
| Certificate/Security information | TLS hợp lệ cho hostname | Browser có điều kiện chấp nhận HSTS |
| Remote/response source | Edge, service worker, cache | Đường nào đã tạo response? |
| Redirect chain | HTTP → HTTPS hoặc redirect nội bộ | Có hop HTTP nào bị nhầm là kết quả? |
| `Cache-Control`/cache status | CDN, browser cache | Header có thể đến từ object cache |

**Không dùng việc URL trong address bar là HTTPS để kết luận Spring đang thấy secure request.** Browser và Spring đang ở hai phía khác nhau của proxy.

### Browser có thể nâng cấp HTTP ngay từ đầu

Nếu host đã được browser biết HSTS từ trước hoặc thuộc preload list, gõ `http://app.example.com` có thể được browser nâng cấp lên HTTPS trước network. Điều này **không chứng minh HSTS header vừa mới được phát bởi server**. Hãy kiểm tra response HTTPS và chính sách HSTS hiện tại, không chỉ quan sát address bar đổi từ http thành https.

### Không coi một cảnh báo scanner là kết luận

Scanner có thể gửi HEAD, truy cập HTTP thay vì HTTPS, bỏ qua redirect hoặc dùng một asset URL qua CDN khác. Hãy tái hiện **phương thức, hostname, scheme, path và status** của scanner rồi đối chiếu với một GET HTTPS public chuẩn.

## 21. Đo scheme Spring nhìn thấy mà không để lộ thông tin nhạy cảm

Trong môi trường dev/staging, có thể dùng một fixture Servlet **chỉ dành cho diagnostics**, không xuất session ID, cookies hoặc token:

~~~java
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@Profile("diagnostics")
@RestController
class ServletSchemeDiagnostics {

    @GetMapping("/_diagnostics/request-scheme")
    Map<String, Object> scheme(HttpServletRequest request) {
        return Map.of(
            "isSecure", request.isSecure(),
            "scheme", request.getScheme(),
            "serverPort", request.getServerPort()
        );
    }
}
~~~

**Không công khai endpoint này trên Internet.** Chỉ bật profile `diagnostics` trong môi trường kiểm soát, giới hạn truy cập ở ingress và authorization; gỡ/tắt sau điều tra. Không thêm route permitAll cho diagnostics rồi quên xóa.

Giả sử gọi qua HTTPS public và proxy đáng tin:

~~~json
{
  "isSecure": true,
  "scheme": "https",
  "serverPort": 443
}
~~~

Nếu kết quả là:

~~~json
{
  "isSecure": false,
  "scheme": "http",
  "serverPort": 8080
}
~~~

thì đây là bằng chứng **request scheme tại Servlet layer chưa phản ánh HTTPS public**. Nhưng HSTS còn có thể bị disable hoặc response được edge ghi đè; không kết luận một mình fixture đã chứng minh toàn bộ nguyên nhân.

### Vì sao không trả X-Forwarded-For và toàn bộ headers?

Raw forwarded headers do client/proxy cung cấp có thể chứa IP và dữ liệu không tin cậy. Với mục tiêu secure detection, thường chỉ cần một số **thuộc tính đã chuẩn hóa** và request ID. Không cần xuất host do user tùy ý gửi, Authorization, Cookie, CSRF token hoặc raw session.

## 22. Reactive fixture: xem URI scheme và secure information của exchange

Trong WebFlux lab, kiểm tra scheme của `ServerHttpRequest`:

~~~java
import java.util.Map;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Profile("diagnostics")
@RestController
class ReactiveSchemeDiagnostics {

    @GetMapping("/_diagnostics/request-scheme")
    Mono<Map<String, Object>> scheme(ServerWebExchange exchange) {
        String requestScheme = exchange.getRequest().getURI().getScheme();
        boolean hasSslInfo = exchange.getRequest().getSslInfo() != null;

        return Mono.just(Map.of(
            "uriScheme", requestScheme == null ? "unknown" : requestScheme,
            "sslInfoAvailable", hasSslInfo
        ));
    }
}
~~~

**Diễn giải thận trọng:** khi TLS kết thúc tại proxy, upstream connection đến Netty có thể không có SSLInfo, ngay cả khi forwarded transformation đã làm URI scheme thành `https`. Vì thế, `sslInfoAvailable=false` **không nhất thiết chứng minh browser dùng HTTP** và không nên bị dùng làm duy nhất điều kiện suy HSTS. Hãy đối chiếu reactive security writer/matcher và **public HTTPS response**.

### Không biến fixture thành cách vượt qua trust boundary

Không thêm logic “nếu có `X-Forwarded-Proto: https` thì trả security = true” trong controller. Việc tin forwarded headers phải được thiết kế ở proxy/framework layer, không phải một điều kiện tự viết để bypass security.

## 23. MockMvc: tách lỗi HSTS writer khỏi lỗi proxy

Với ứng dụng Servlet, có thể dùng `MockMvc` để kiểm tra cơ chế Spring Security HSTS writer trên request được **mô phỏng secure**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class HstsServletTest {

    @Autowired MockMvc mockMvc;

    @Test
    void secureRequestReceivesHsts() throws Exception {
        mockMvc.perform(get("/login").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().exists("Strict-Transport-Security"));
    }

    @Test
    void insecureRequestDoesNotLearnHsts() throws Exception {
        mockMvc.perform(get("/login").secure(false))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist("Strict-Transport-Security"));
    }
}
~~~

Giả định `/login` trả HTTP 200, `SecurityFilterChain` phù hợp bật HSTS writer mặc định và không có custom filter luôn tự thêm header. Một app dùng redirect/custom login route cần điều chỉnh status và fixture, không thay đổi bản chất của assertions.

### Test này chứng minh gì?

Nó chứng minh trong application test context:

- Request được coi là secure thì HSTS writer có thể phát STS.
- Request không secure không nhận STS từ writer mặc định.

### Test này **không** chứng minh gì?

`.secure(true)` tạo `MockHttpServletRequest` với secure flag theo yêu cầu test. Nó **không tái hiện TLS termination, proxy forwarding hoặc việc một attacker có thể giả mạo X-Forwarded-Proto**. Do đó MockMvc PASS không chứng minh HTTPS production đang truyền forwarded headers đúng.

### Phân biệt header writer với forwarded handling

Nếu `secure(true)` PASS nhưng HTTPS public thiếu HSTS, hãy tập trung tiếp vào forwarded headers, proxy, trust boundary, selected chain thực tế và edge. Nếu ngay cả `secure(true)` cũng thiếu HSTS, cần kiểm tra HSTS writer disabled, headers disabled, path bị ignored hoặc test chưa gắn Spring Security filters.

## 24. MockMvc: kiểm tra nhận forwarded headers trong ngữ cảnh test cô lập

Trong **application test context** có `server.forward-headers-strategy=framework` và Servlet `ForwardedHeaderFilter` được đăng ký trước Spring Security, có thể tạo request upstream HTTP nhưng có forwarded headers:

~~~java
mockMvc.perform(get("/login")
        .secure(false)
        .header("X-Forwarded-Proto", "https")
        .header("X-Forwarded-Host", "app.example.com")
        .header("X-Forwarded-Port", "443"))
    .andExpect(status().isOk())
    .andExpect(header().exists("Strict-Transport-Security"));
~~~

**Chú ý:** test chỉ hợp lệ khi `MockMvc` gắn **đúng filter registration** và forwarded processing thực tế được cấu hình. Không phải mọi cấu hình MockMvc đều tái hiện container filters/valves. Nếu framework filter không được gắn, request sẽ vẫn được coi là HTTP và test có thể FAIL do setup, không phải production behavior.

**Đây không phải phép thử an toàn trước spoofing.** MockMvc tự cho test đặt header giả như thể từ proxy; một hệ thống thật phải bảo đảm header client không bao giờ được tin nếu chưa qua trusted proxy. Test chống spoofing phải thực hiện ở ingress/network boundary được kiểm soát.

## 25. WebTestClient: kiểm tra Reactive HSTS với HTTPS thật

Trong WebFlux, một mock WebTestClient bind vào application context có thể dùng request URI HTTP mặc định. Vì vậy:

~~~java
webTestClient.get()
    .uri("/login")
    .exchange()
    .expectStatus().isOk();
~~~

không đủ để kết luận HSTS có hoặc không có trên browser HTTPS public. Muốn kiểm thử **end-to-end**, cấu hình WebTestClient kết nối tới HTTPS staging endpoint có certificate hợp lệ:

~~~java
// Giả định webTestClient đã được cấu hình với baseUrl HTTPS thực:
// https://app.example.test (đường public qua proxy)
webTestClient.get()
    .uri("/login")
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
        .exists("Strict-Transport-Security");
~~~

Trong môi trường này, WebTestClient có thể kiểm tra header public, nhưng không tự chứng minh Spring hay edge đã tạo header. Xác định HSTS owner qua cấu hình và access logs.

### Reactive integration: forwarded scheme transformer

Một test riêng có thể kiểm tra exchange đã được transform để có request URI scheme HTTPS khi request đi từ proxy đáng tin. Nhưng **không nên thay thế** bằng test mock mà người viết tự gắn một header rồi kết luận thiết kế trust boundary an toàn.

Kết hợp ba lớp:

1. Unit/integration test HSTS writer trên secure exchange nếu dự án có harness phù hợp.
2. Integration test forwarded transformation trong cấu hình WebFlux thực.
3. HTTPS public test kiểm tra response browser nhận.

### Auth status trong test chỉ là fixture

Nếu `GET /login` trong WebFlux trả redirect, có CSRF/session behavior khác hoặc route không tồn tại, thay bằng một public GET lab ổn định. Chỉ khi đã biết response branch thì assertion status mới có ý nghĩa.

## 26. Playwright: quan sát HSTS trên HTTPS public

Với môi trường kiểm thử có DNS/certificate hợp lệ cho `app.example.test`:

~~~javascript
import { test, expect } from "@playwright/test";

test("public HTTPS response phát HSTS policy", async ({ page }) => {
  const response = await page.goto(
    "https://app.example.test/login"
  );

  expect(response).not.toBeNull();
  expect(response.status()).toBe(200);

  const headers = await response.allHeaders();
  const hsts = headers["strict-transport-security"];

  expect(hsts).toBeDefined();
  expect(hsts).toMatch(/max-age=\d+/i);
});
~~~

Đây là ví dụ **browser E2E đo response header**, không phải phép đo browser đã thực thi HSTS cache policy trong mọi tình huống. Với test thật, nên kiểm tra `max-age` giá trị cụ thể theo hợp đồng security rollout, và test thêm 302/401/404 nếu edge owner cần áp STS trên chúng.

### Không dùng `ignoreHTTPSErrors: true` cho test HSTS

HSTS chỉ có giá trị khi browser có thể xác minh HTTPS đáng tin. Nếu test tắt kiểm tra certificate, việc header xuất hiện không chứng minh người dùng production có thể học policy HSTS hợp lệ.

### Browser history và preload có thể gây ngộ nhận

Một browser đã biết HSTS từ trước có thể tự upgrade HTTP request ngay cả khi server **hiện không còn phát STS header**. Tương tự, browser preload list có thể khiến HTTPS được dùng từ lần truy cập đầu. Vì thế, phải kiểm tra trực tiếp response header và plan rollout, không chỉ test “nhập http mà vẫn thấy https”.

## 27. Kịch bản A — Nginx đúng HTTPS, Spring nhìn http vì chưa xử lý forwarded headers

**Bối cảnh:**

~~~text
Browser:
  GET https://app.example.com/login

Nginx:
  downstream TLS https
  upstream http://spring:8080
  X-Forwarded-Proto: https

Spring Servlet:
  request.isSecure() == false
  HstsHeaderWriter không thêm STS mặc định
~~~

Response public có thể:

~~~http
HTTP/1.1 200 OK
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
~~~

### Các bước chứng minh

1. Dùng `curl -i https://app.example.com/login`: HSTS thiếu.
2. Kiểm tra Nginx có đặt `X-Forwarded-Proto: https` trên request upstream không.
3. Trong staging lab, dùng diagnostic endpoint giới hạn để xem `request.isSecure()` và scheme.
4. Xem Spring Boot effective `server.forward-headers-strategy`.
5. Test MockMvc `secure(true)`: nếu HSTS có, chứng tỏ writer cơ bản hoạt động.
6. Bật xử lý forwarded headers **chỉ khi proxy đáng tin đã sanitize**, triển khai lại và đo HTTPS public.

### Fix đúng

~~~properties
server.forward-headers-strategy=framework
~~~

**Tiêu chí PASS:** trên HTTPS public, response có HSTS giá trị theo policy; các redirect/cookie URL không bị sai scheme; HTTP public vẫn chuyển hướng HTTPS; backend không thể bị client truy cập trực tiếp để giả metadata forwarding.

### Nếu vẫn thiếu

Kiểm tra thứ tự filter, bean custom `ForwardedHeaderFilter`, HSTS writer bị disable, matching chain và CDN cache. Property đúng chưa chắc proxy đã gửi dữ liệu đúng.

## 28. Kịch bản B — Nhiều proxy làm X-Forwarded-Proto bị đổi từ https sang http

**Bối cảnh:**

~~~text
Browser --HTTPS--> CDN --HTTP--> Ingress --HTTP--> Spring
~~~

CDN đặt:

~~~http
X-Forwarded-Proto: https
~~~

Nhưng ingress cấu hình sai, lấy scheme của kết nối CDN → ingress và ghi đè:

~~~http
X-Forwarded-Proto: http
~~~

Spring Boot đã bật `server.forward-headers-strategy=framework` mà vẫn nhìn request là HTTP.

### Sai lầm chẩn đoán thường gặp

Developer chỉ xem app config:

~~~properties
server.forward-headers-strategy=framework
~~~

và kết luận Spring Security HSTS có bug. Trong thực tế framework **diễn giải đúng dữ liệu sai** mà ingress đã cung cấp.

### Cách điều tra

1. Ghi rõ từng hop và scheme thực của từng connection.
2. Tìm hop có trách nhiệm xác nhận HTTPS public.
3. Xem rule ghi/overwrite `X-Forwarded-Proto` tại CDN, ingress và service mesh.
4. Nếu có cả `Forwarded: proto=https` và `X-Forwarded-Proto: http`, quyết định cách chuẩn hóa.
5. Chỉ chuyển tiếp metadata đã được sanitize trong một trust chain được định nghĩa.
6. Đối chiếu scheme mà Spring thực nhận, không chỉ giá trị frontend gửi.

**Sửa đúng:** sửa cấu hình tại **hop làm mất public scheme** hoặc chọn edge-owned HSTS; không nhét header thủ công trong controller mỗi request.

## 29. Kịch bản C — Browser thấy HTTPS, Spring HSTS đúng, CDN làm mất header

**Bối cảnh:**

~~~text
Spring origin response:
  Strict-Transport-Security: max-age=31536000

Public CDN response:
  (không có Strict-Transport-Security)
~~~

Có thể CDN:

- Bỏ một số response headers khi cache hoặc chuyển tiếp.
- Trả cached object cũ, được tạo trước khi HSTS được triển khai.
- Chỉ thêm/giữ STS cho HTML, không phải static assets.
- Có một edge rule khác ghi đè headers trên response 304/404/500.
- Phục vụ tài nguyên hoàn toàn từ object storage hoặc static hosting.

### Phép thử quyết định

So cùng GET, host/path và response source qua đường Spring origin được phép và public CDN. Ghi cache hit/miss, status, config version và STS values.

**Sửa đúng tầng:** cấu hình CDN/edge giữ hoặc phát HSTS theo host policy, xử lý cached variants và error branches. Không thay `HttpSecurity` nếu Spring đã trả đúng mà CDN strip header.

### Có phải mọi static response phải có HSTS không?

HSTS policy được browser lưu theo host; việc một file JS không phát STS trong một thời điểm không nhất thiết làm policy hiện có mất hiệu lực. Nhưng một chiến lược **edge-owned HSTS** thường muốn áp chính sách nhất quán trên các HTTPS responses của host. Đánh giá theo policy đã cam kết và browser behavior, không chỉ một rule scanner chung cho mọi content type.

## 30. Kịch bản D — HSTS thiếu vì đường URL không khớp SecurityFilterChain

**Bối cảnh:** HSTS hiện diện trên `/account` nhưng thiếu ở `/assets/app.js`, dù cả hai đi qua Spring origin.

Ứng dụng có:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    );
    return http.build();
}
~~~

Hoặc:

~~~java
@Bean
WebSecurityCustomizer ignoredAssets() {
    return web -> web.ignoring().requestMatchers("/assets/**");
}
~~~

Các đoạn trên chỉ là **ví dụ tách rời**. Nếu request không vào chain chứa `HstsHeaderWriter`, nó sẽ không nhận HSTS từ chain đó, **dù Spring nhận diện HTTPS đúng**.

### Phân biệt với lỗi forwarded scheme

| Đo lường | Sai scheme | Không match/ignored |
|---|---|---|
| `request.isSecure()` trên path lỗi | Thường false | Có thể true |
| HSTS trên mọi Spring responses | Có thể thiếu rộng | Có thể chỉ thiếu một nhóm path |
| HeaderWriterFilter trên path lỗi | Có thể vẫn chạy | Có thể không chạy |
| `X-Content-Type-Options` trên path lỗi | Có thể vẫn có | Có thể thiếu nếu chỉ Spring viết |
| Fix ưu tiên | Forwarded processing/trust proxy | Matcher/chain/fallback/permitAll |

**Sửa đúng:** đảm bảo một matching security chain hoặc HSTS edge owner. Không dùng `web.ignoring()` để công khai static resources khi bạn cần Spring security headers trên chúng; ưu tiên `permitAll()` trong chain phù hợp.

## 31. Kịch bản E — HSTS bị disable riêng trên một chain

**Bối cảnh:** HTTPS, `request.isSecure() == true`, `HeaderWriterFilter` vẫn chạy nhưng response thiếu STS.

Có thể một cấu hình đã disable:

~~~java
http.headers(headers -> headers
    .httpStrictTransportSecurity(hsts -> hsts.disable())
);
~~~

hoặc disable toàn bộ headers:

~~~java
http.headers(headers -> headers.disable());
~~~

**Điểm quan trọng:** trong trường hợp này sửa `server.forward-headers-strategy` không làm HSTS xuất hiện. Phải xem policy của selected security chain và config thực thi.

Nếu HSTS do edge sở hữu, việc tắt writer app có thể là quyết định có chủ đích; khi đó HTTPS public vẫn phải có STS do edge phát đúng. Không bật hai policies đối lập để scanner ở origin xanh hơn.

## 32. Kịch bản F — Forwarded header spoofing làm test “HSTS PASS” giả

**Bối cảnh:** backend lộ trực tiếp ở một port công khai và có `server.forward-headers-strategy=framework`. Tester gửi HTTP nhưng tự đặt:

~~~http
GET /login HTTP/1.1
Host: app.example.com
X-Forwarded-Proto: https
~~~

Nếu backend tin giá trị này, nó có thể cho request được nhận diện secure và phát STS trên **HTTP response**. Browser **không học HSTS từ HTTP**, và thiết kế trust boundary còn có vấn đề lớn hơn.

**Vì sao đây không phải fix:** giả header không tạo TLS, không chứng minh browser kết nối an toàn và có thể ảnh hưởng redirect/host, cookie attributes hoặc bảo mật khác.

### Regression test ở ingress được tin cậy

Trong lab có quyền kiểm soát, gửi request HTTPS public với header client cố ý sai:

~~~bash
curl -sS -D - -o /dev/null \
  -H 'X-Forwarded-Proto: http' \
  'https://app.example.test/login'
~~~

Nếu proxy được thiết kế đúng, client-supplied forwarded scheme **không được làm application thấy HTTP** và gây mất HSTS trên response HTTPS public. Kết quả mong đợi phải dựa vào proxy policy đã xác định, không phải bất cứ cách append headers nào cũng an toàn.

### Bảo vệ mạnh hơn là chặn bypass ingress

Một backend chỉ dành cho proxy không nên được public Internet truy cập trực tiếp. Dùng private networking/firewall rules/service binding và kiểm soát trusted proxies. Đừng coi một test header là đủ thay cho segmentation.

## 33. Kịch bản G — HSTS có nhưng policy không đúng hoặc nhiều giá trị xung đột

Một response:

~~~http
Strict-Transport-Security: max-age=0
~~~

có ý nghĩa **chấm dứt HSTS policy của host** khi browser nhận trên HTTPS hợp lệ, không phải bật bảo vệ. Header có mặt nhưng bảo vệ có thể không như mong đợi.

Một ví dụ khác:

~~~http
Strict-Transport-Security: max-age=86400
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Nếu edge và Spring phát hai giá trị khác nhau, đừng giả định browser sẽ chọn giá trị “mạnh nhất” theo ý người vận hành. Hành vi xử lý nhiều header cần xem theo chuẩn/browser; **thiết kế đúng là một policy nhất quán**, kiểm thử header cuối cùng người dùng thấy.

### Rollout thận trọng

- Chọn `max-age` theo lộ trình và khả năng rollback.
- Không bật `includeSubDomains` nếu bất kỳ subdomain liên quan chưa vận hành HTTPS ổn định.
- Không bật `preload` tùy tiện; nó liên quan chính sách lâu dài và thủ tục đưa host vào preload list của trình duyệt, không chỉ một directive trong response.
- Đo HSTS trên **HTTPS public**, không coi sự hiện diện trên HTTP là thành công.

## 34. Kịch bản H — HSTS trên login nhưng thiếu trên lỗi 404/500 từ edge

**Hiện tượng:**

~~~text
GET https://app.example.com/login       -> 200 + STS
GET https://app.example.com/missing     -> 404 không STS
GET https://app.example.com/api/private -> 401 + STS
GET https://app.example.com/bad-route   -> 502 từ CDN không STS
~~~

Lý do có thể:

- Nginx chỉ thêm header cho một số status, không dùng `always` hoặc directive bị override ở location.
- CDN/WAF tự sinh error page ngoài Spring.
- Servlet error dispatch không đi qua same security filters.
- HSTS only ở một chain/path, không có fallback.

**Cách chẩn đoán:** xác định **ai sinh từng response**, so 200 với 404/502, đọc header tại public HTTPS và source logs. Edge-owned HSTS nên được kiểm thử trên các status mà edge có thể phát.

**Tránh khắc phục sai:** đừng thêm `Strict-Transport-Security` vào HTTP error pages một cách mù quáng; browser không học HSTS trên HTTP và vấn đề public HTTPS vẫn tồn tại.

## 35. Bảng chẩn đoán: HSTS thiếu ở lớp nào?

| Dấu hiệu | Nguyên nhân đáng kiểm tra | Bằng chứng xác định | Hướng xử lý |
|---|---|---|---|
| HTTPS public thiếu HSTS, HTTP origin cũng thiếu | Scheme detection sai hoặc writer disable | `isSecure()`/URI scheme và selected chain | Sửa forwarded processing hoặc header writer |
| MockMvc `secure(true)` có STS, public HTTPS thiếu | Proxy forwarding, edge hoặc path | So public/origin, effective properties | Sửa đúng proxy/trust/edge |
| Spring `isSecure()==false` trên public HTTPS | Upstream HTTP chưa được diễn giải | Forwarded headers tại proxy + Boot strategy | Trusted proxy + framework/native processing |
| `X-Forwarded-Proto: http` do ingress dù CDN nhận TLS | Header bị rewrite ở hop trung gian | Tracing từng hop | Sửa trust-chain/source of truth |
| Spring đã trả STS, public CDN thiếu | Edge strip/cache hoặc static hosting | Origin/public headers cùng request | Sửa CDN/edge response policy |
| HTML có STS, JS path thiếu | Ignored/no matching chain hoặc CDN | Selected chain, response source | PermitAll/fallback hoặc edge owner |
| `X-Content-Type-Options` còn nhưng HSTS thiếu | Secure condition hoặc HSTS writer | `request.isSecure()` và header policy | Kiểm tra HSTS-specific logic |
| Tất cả Spring headers đều thiếu | Chain bypass/headers disabled/proxy | FilterChainProxy, resource routing | Chỉnh matching/header filter |
| HSTS chỉ thiếu trên HTTP localhost | Hành vi bình thường có thể xảy ra | HTTPS public test | Không ép HTTP thành HSTS |
| Browser đã upgrade HTTP nhưng response thiếu STS | Cached/preloaded HSTS | HTTPS response và browser state | Sửa phát STS hiện tại, không dựa vào history |
| STS hiện diện với `max-age=0` | Policy đang bị hủy | Giá trị header | Review rollout/rollback |
| STS có hai giá trị khác nhau | Nhiều HSTS owners | Spring và edge config | Hợp nhất policy |
| Chỉ 404/500 thiếu | Edge error handler/dispatcher mismatch | Response source/status | Test và sửa error branch |
| Cookie Secure/redirect cũng sai sau proxy | Public scheme/host hiểu sai | Location, Set-Cookie, request scheme | Sửa forwarding toàn diện |
| Spring Reactive URI scheme HTTP sau TLS proxy | ForwardedHeaderTransformer chưa áp đúng | Exchange URI và Boot config | Cấu hình Reactive forwarding |
| Client tự đặt forwarded header làm đổi scheme | Trust boundary có lỗi | Negative ingress test | Sanitize + chặn direct backend access |

**Không dùng riêng HTTP status để kết luận filter đã chạy.** Một response 200 có thể do Spring, CDN, object storage hoặc cache. Một response 404/502 cũng có thể được tạo hoàn toàn ở edge.

## 36. HSTS liên quan cookie Secure, redirect, OAuth và CORS thế nào?

Sai scheme ở Spring thường không chỉ ảnh hưởng HSTS. Những lỗi kề nhau có thể giúp định vị nguyên nhân:

### 36.1. Cookie Secure

Một ứng dụng dùng session cookie:

~~~http
Set-Cookie: JSESSIONID=...; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Nếu cookie được cấu hình dựa trên nhận diện request secure hoặc servlet container, một scheme HTTP sai sau proxy có thể khiến attributes/cookie behavior không như mong đợi. Tuy vậy, một cấu hình `server.servlet.session.cookie.secure=true` riêng có thể bảo đảm Secure bất kể request-derived flags; cần xem **header cuối cùng** chứ không suy cookie chắc chắn thiếu Secure.

**Không tắt Secure để sửa login loop.** Browser đang kết nối HTTPS public; phải giải quyết scheme, path, Domain và session architecture thích hợp.

### 36.2. Redirect và absolute URL

Nếu backend tin request scheme là HTTP, response có thể:

~~~http
Location: http://app.example.com/login
~~~

thay vì HTTPS. Browser có thể bị mixed-content/redirect loop hoặc phải qua một vòng HTTP→HTTPS không cần thiết. Nếu thấy HSTS thiếu **và** Location sai scheme, forwarded processing là nghi vấn mạnh.

### 36.3. OAuth2/SSO callback

OAuth2 redirect URI có thể phụ thuộc public scheme/host hoặc cấu hình absolute URL của app. Một proxy-scheme mismatch có thể tạo callback URL `http://...` trong khi identity provider yêu cầu `https://...`. Nhưng **không mặc định mọi OAuth redirect URI đều được tính từ request**; ứng dụng có thể cấu hình URI tường minh.

Khi HSTS và OAuth callback cùng sai, kiểm tra forwarded metadata và cách tạo URLs — không thay `state`/CSRF token để chữa sai scheme.

### 36.4. CORS Origin và scheme

Origin có scheme + host + port. Frontend `https://app.example.com` khác Origin với `http://app.example.com`. Sai public scheme ở redirect hoặc gateway có thể gây CORS mismatch, nhưng **CORS không quyết định có phát HSTS hay không**; cả hai cùng có thể chịu ảnh hưởng từ cấu hình proxy.

### 36.5. CSP và mixed content

CSP `upgrade-insecure-requests` có thể khiến browser nâng cấp một số HTTP resource URLs, hoặc browser chặn mixed content. Điều đó không bảo đảm Spring nhìn thấy HTTPS public; vẫn cần kiểm tra forwarded scheme. Không bỏ CSP để “cho HTTP qua” khi phát hiện HSTS thiếu.

## 37. HSTS preload, includeSubDomains và kế hoạch rollout thận trọng

HSTS không chỉ là một header trong scanner; nó có thể ảnh hưởng **cách browser tiếp cận toàn bộ host hoặc các subdomain** trong thời gian dài.

### 37.1. Tăng max-age theo giai đoạn

Một lộ trình minh họa:

| Giai đoạn | Policy minh họa | Điều kiện chuyển tiếp |
|---|---|---|
| Kiểm thử | `max-age=300` | HTTPS/cert/redirect hoạt động trên host test |
| Canary | `max-age=86400` | Không phát sinh login/SSO/callback/asset regressions |
| Mở rộng | `max-age=604800` | Host public và rollback procedure ổn |
| Vận hành ổn định | Giá trị dài hạn đã review | Monitoring, renewal, domains và subdomains được quản lý |

Các giá trị chỉ minh họa **phương pháp rollout**, không phải yêu cầu cố định. Khi browser đã học một `max-age` dài, thay config server không lập tức xóa trạng thái đã lưu ở mọi browser; phải lập kế hoạch rollback phù hợp.

### 37.2. includeSubDomains có phạm vi lớn

Nếu host `example.com` phát:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

browser có thể áp chính sách HSTS cho các subdomains theo phạm vi đã định. Nếu `legacy.example.com` hoặc `dev.example.com` chưa có HTTPS hợp lệ, người dùng có thể bị khóa truy cập các hosts đó.

**Không thêm includeSubDomains chỉ vì ứng dụng chính đã HTTPS**. Cần inventory domains/subdomains, TLS certificates, redirects, health checks và chủ sở hữu từng hệ thống.

### 37.3. Preload không phải bật cờ là xong

Một response:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
~~~

không có nghĩa host đã nằm trong preload list của browser. Preloading thường gắn với các điều kiện eligibility, quy trình submission, và khả năng gỡ bỏ hạn chế. Phải kiểm tra tiêu chí và chính sách mới nhất trước khi làm; không kết luận preload “đã có” chỉ từ một response header.

### 37.4. max-age=0 là rollback có giới hạn

Trên HTTPS hợp lệ:

~~~http
Strict-Transport-Security: max-age=0
~~~

được dùng để yêu cầu browser quên HSTS policy của host theo cơ chế chuẩn. Nhưng trình duyệt **phải nhận được** response HTTPS mới; và các trường hợp inherited HSTS từ parent domain hoặc preload list không thể giả định bị xóa đơn giản chỉ bởi child host.

Vì vậy kế hoạch rollout phải dự liệu tác động trước khi bật thời hạn dài, includeSubDomains hoặc preload.

## 38. Ma trận kiểm thử: không chỉ kiểm tra một response 200

| Ca test | Đường đi | Kết quả cần xác minh |
|---|---|---|
| HTTPS public GET `/login` | Browser → TLS edge → Spring | HSTS theo policy, TLS hợp lệ |
| HTTPS public GET `/assets/app.js` | Browser → CDN/static/Spring | HSTS theo owner và no conflicting policy |
| HTTPS public GET 404 | Edge hoặc Spring | HSTS theo policy trên error response |
| HTTPS public 302 login | Proxy/entry point | Location canonical HTTPS, STS hợp lý |
| HTTP public GET | Edge HTTP | Redirect tới HTTPS, không suy HSTS từ HTTP |
| Internal HTTP origin (test-only) | Bỏ qua edge trong môi trường được phép | Không coi thiếu STS là proof of production failure |
| MockMvc `secure(true)` | Servlet mock | HSTS writer hoạt động khi secure |
| MockMvc `secure(false)` | Servlet mock | Writer mặc định không phát STS cho insecure request |
| HTTPS public với client-supplied `X-Forwarded-Proto: http` | Qua trusted edge | Không bị client override scheme public |
| WebFlux HTTPS public | TLS edge → reactive stack | STS có trên final HTTPS response |
| 401/403/500 public HTTPS | Auth/error/edge | STS không mất vì status khác |
| CDN cache hit/miss | HTTPS public | Header không bị mất hoặc đổi policy tùy cache |
| Nhiều node/canary | Load balancer | Policy nhất quán giữa versions |
| Parent/subdomain rollout | Nhiều host được quản lý | TLS/certificate và includeSubDomains không phá dịch vụ |

### Không viết test giả chứng minh trust boundary

Nếu một test chỉ tạo `MockHttpServletRequest.secure=true` hoặc tự đặt `X-Forwarded-Proto: https` mà không qua ingress, test đó chỉ chứng minh logic tại tầng app, **không chứng minh header đến từ proxy đáng tin**. Hãy có kiểm thử thực tế ở edge và network boundary.

### Không đòi scanner chỉ thấy 200

Một HTTP 302/401/403/404/500 public HTTPS hoàn toàn có thể là kết quả hợp lệ của authentication hoặc nghiệp vụ; kiểm thử HSTS không nên chuyển các status đó thành 200. Mục tiêu là header policy **nhất quán trên response được thiết kế để phát STS**, không làm mất bảo mật khác.

## 39. Runbook chẩn đoán tám bước

~~~mermaid
flowchart TD
    A[HTTPS public thiếu Strict-Transport-Security] --> B{Response do Spring hay edge tạo?}
    B -- Edge/CDN --> C[Kiểm tra HSTS owner/cache/error routing ở edge]
    B -- Spring --> D{Matching security chain?}
    D -- Không --> E[Matcher/ignored/fallback chain]
    D -- Có --> F{Header writer HSTS được bật?}
    F -- Không --> G[Headers configuration per chain]
    F -- Có --> H{Servlet isSecure hoặc WebFlux URI scheme là HTTPS?}
    H -- Không --> I[Forwarded scheme/trust proxy/filter transformer]
    H -- Có --> J[Origin headers, proxy strip/override, response status]
    C --> K[HTTP integration + browser regression]
    E --> K
    G --> K
    I --> K
    J --> K
~~~

### Bước 1 — Xác nhận URL đang đo là HTTPS công khai

Ghi URL, method, status, response source, timestamp và hostname. Dùng GET HTTPS public có certificate hợp lệ; không suy từ HEAD hoặc HTTP upstream. Nếu browser đã cached HSTS, vẫn kiểm tra trực tiếp header response.

### Bước 2 — Xác định HSTS owner

Từ thiết kế hạ tầng, HSTS do Spring phát, edge phát hay đã được chia trách nhiệm? Kiểm tra có duplicate/mismatch values giữa app và proxy không.

### Bước 3 — Xác định request có tới Spring không

So CDN/ingress access logs và Spring logs theo request ID. Nếu edge trả file/response và Spring không nhận request, sửa edge/static hosting. Nếu Spring trả response, tiếp tục xem request scheme và selected chain.

### Bước 4 — Kiểm tra selected security chain

Servlet: `FilterChainProxy`, `SecurityFilterChain`, `web.ignoring()`, `HeaderWriterFilter`, `HstsHeaderWriter`. Reactive: `SecurityWebFilterChain`, `HttpHeaderWriterWebFilter` và HSTS writer. Xác định có `headers().disable()` hoặc HSTS-specific disable không.

### Bước 5 — Đo scheme mà Spring thực nhận

Trong staging diagnostics, xem `request.isSecure()/getScheme()` hoặc Reactive URI scheme. Nếu HTTP trong khi browser HTTPS, kiểm tra forwarded headers do **trusted proxy** tạo. Không bật tin header tùy ý từ Internet.

### Bước 6 — Theo dõi chuỗi proxy

Ghi hop nào terminate TLS, hop nào ghi `Forwarded`/`X-Forwarded-Proto`. Nếu một hop ghi đè `https` thành `http`, sửa ở hop đó. Kiểm tra Boot `server.forward-headers-strategy=framework/native/none` và tránh double processing.

### Bước 7 — Kiểm tra HSTS cuối cùng và giá trị thực

Nếu Spring phát nhưng public thiếu, điều tra CDN cache, static location, error handlers và header strip. Nếu STS tồn tại, kiểm tra `max-age`, `includeSubDomains`, `preload` và các values lặp.

### Bước 8 — Hồi quy cả ứng dụng

Test HTTPS/HSTS, HTTP→HTTPS, redirects, login/logout, session cookies, CSRF, CORS, CSP, framing, API authorization, error pages và multi-node rollout. Một bản sửa HSTS **không thành công** nếu vô tình làm redirect/cookies sai hoặc cho client spoof public scheme.

## 40. Anti-pattern: những “cách sửa nhanh” không an toàn

| Cách làm sai | Hậu quả | Hướng đúng |
|---|---|---|
| Tin `X-Forwarded-Proto` từ bất kỳ client nào | Scheme/host spoofing, redirect/cookie risks | Trusted proxy + sanitize + private backend |
| Cho mọi client gọi trực tiếp backend vẫn bật forwarded processing | Bypass trust boundary | Chặn direct access, chỉ nhận từ proxy |
| Gắn STS trên HTTP rồi nghĩ browser đã học HSTS | Browser bỏ qua HSTS qua HTTP | HTTPS public response |
| Tắt HSTS vì Spring thấy HTTP upstream | Mất HTTPS upgrade protection | Sửa public scheme detection hoặc edge-owned STS |
| Bỏ cookie `Secure` để login “hết lỗi” | Session có thể đi qua HTTP | Sửa cookie/TLS/proxy đúng lớp |
| Dùng `request.isSecure() = true` bằng hack/controller | Không tái tạo TLS/trust thực | Boot native/framework forwarding đáng tin |
| Bật cả native và framework processing không kiểm soát | Scheme/host biến đổi khó dự đoán | Một chế độ được kiểm thử |
| Dùng `curl -k` rồi kết luận HTTPS đúng | Bỏ xác thực certificate | Certificate/TLS hợp lệ |
| Thêm HSTS `preload` ngay từ lần đầu | Có thể khóa nhiều subdomains, khó rollback | Rollout có kiểm kê và review |
| Thêm `includeSubDomains` dù service legacy chỉ có HTTP | Browser có thể không truy cập được service | Chuẩn bị TLS trên tất cả subdomains |
| Đặt `max-age=0` để “có header” | Hủy HSTS policy | Chọn duration theo rollout |
| Hai STS headers khác policy ở Spring/edge | Policy khó dự đoán và quản lý | Một owner, consistent values |
| Chỉ fix 200, quên 404/500/edge redirects | HSTS thiếu trên một số public paths | Kiểm thử nhiều response branches |
| Bỏ `web.ignoring()` rồi `permitAll()` toàn bộ API | Mở routes nghiệp vụ | Fallback an toàn, permit assets hẹp |
| Tắt CSRF/CSP/CORS/firewall khi sửa HSTS | Suy yếu lớp bảo vệ khác | Chẩn đoán đúng tầng, giữ defenses |
| Log cookie/Authorization/CSRF token để debug scheme | Rò secrets | Chỉ log secure flag/scheme và request ID |
| Chỉ test MockMvc `secure(true)` | Không phát hiện proxy misconfiguration | HTTPS public và ingress negative tests |

HSTS là **chính sách phía browser** của hostname công khai. Quy trình đúng là sửa đường nhận diện HTTPS, nơi phát header và phạm vi policy, không thay một cơ chế bảo mật bằng shortcut khiến scanner báo xanh nhưng người dùng không được bảo vệ.

## 41. Bài thực hành tổng hợp: HSTS biến mất sau TLS termination

### Bối cảnh thực hành

Xây dựng một lab Spring Boot gồm hai biến thể độc lập:

- **Servlet:** Spring MVC, Spring Security, một trang public `/login`, một API cần authentication và một static asset.
- **Reactive/WebFlux:** `SecurityWebFilterChain`, trang public tương đương và cùng mục tiêu kiểm thử HSTS.

Trước ứng dụng, đặt reverse proxy **HTTPS với hostname/certificate do nhóm kiểm thử quản lý**. Proxy kết nối tới Spring bằng HTTP upstream trên private network. Có thể bổ sung một hop CDN hoặc ingress để tái hiện header bị ghi đè.

**Tất cả tên host bên dưới chỉ là ví dụ**, không phải endpoint thực sẵn có:

~~~text
https://app.example.test         <- public TLS
http://spring-internal:8080      <- private HTTP upstream
~~~

Không expose `spring-internal:8080` ra Internet. Không sử dụng mật khẩu, session hoặc token thật trong log hoặc response fixtures.

### Nhiệm vụ 1 — Thiết lập trạng thái ban đầu

1. Bật security headers mặc định trong `SecurityFilterChain` Servlet.
2. Để `server.forward-headers-strategy=none` ở profile **negative test** (hoặc cấu hình tương đương khiến backend không diễn giải forwarding).
3. Proxy nhận HTTPS, gửi HTTP tới backend và đặt `X-Forwarded-Proto: https`.
4. Truy cập `GET https://app.example.test/login` qua proxy bằng curl/Playwright; ghi status và HSTS.
5. Dùng diagnostic fixture hạn chế để đo `request.isSecure()` và `request.getScheme()` tại Servlet.

**Kết quả dự kiến:** trong test negative có Spring-owned HSTS, backend có thể nhìn scheme `http` và STS không được Spring Security phát, dù browser dùng HTTPS.

### Nhiệm vụ 2 — Sửa forwarded processing mà không bỏ bảo vệ

1. Xác nhận proxy sanitize giá trị forwarded của client.
2. Chuyển test profile sang `server.forward-headers-strategy=framework`.
3. Xác nhận request trong app chuyển thành `isSecure=true` và `scheme=https` trong đường request qua trusted proxy.
4. Truy cập lại HTTPS public, xem HSTS theo policy.
5. Xác nhận HTTP public redirect tới HTTPS mà không dựa vào STS gửi qua HTTP.
6. Kiểm tra `Location` của login redirect, `Secure` cookie và route static/public.

**PASS khi:** STS có trên HTTPS public và scheme/host/redirect đúng; các route private vẫn cần authentication, POST có session vẫn phải qua CSRF.

### Nhiệm vụ 3 — Kiểm tra trust boundary

1. Trong lab, gửi `X-Forwarded-Proto: http` đến **public HTTPS ingress**.
2. Xác nhận proxy không cho client đổi public scheme mà backend dùng.
3. Kiểm tra backend port chỉ truy cập được từ trusted network.
4. Nếu có nhiều proxies, mô phỏng một hop ghi đè public `https` thành `http`; xác định hop làm sai.
5. Sửa contract forwarded headers ở hop đó, không thêm code tin `X-Forwarded-Proto` trực tiếp trong controller.

Đây là **negative security test có chủ đích trên lab được sở hữu**, không phải chỉ dẫn kiểm tra các hệ thống không có quyền.

### Nhiệm vụ 4 — Chuyển chủ sở hữu HSTS sang edge

1. Trong một biến thể độc lập, để HTTPS proxy phát STS với max-age ngắn.
2. Đối chiếu output Spring origin và HTTPS public.
3. Thử 200, 302, 401, 403, 404 và 502 (có thể mô phỏng edge error trong lab).
4. Xác nhận không có hai STS headers với chính sách khác nhau.
5. Thử tắt HSTS app có chủ đích trong profile lab; HTTPS public vẫn phải nhận STS nếu edge đã được giao sở hữu.

**Chú ý:** edge-owned STS không tự bảo đảm mọi redirect URL, OAuth callback hay cookie attributes của Spring đều đúng khi app vẫn hiểu sai public scheme. Các vấn đề đó phải được test và sửa riêng.

### Nhiệm vụ 5 — Đối chiếu Servlet và Reactive

1. Với Servlet, viết MockMvc test `secure(true)` và `secure(false)` để đo HSTS writer.
2. Với WebFlux, dùng `ForwardedHeaderTransformer` qua Boot framework mode; kiểm tra URI scheme trên exchange diagnostics.
3. Dùng WebTestClient gắn HTTP endpoint thật hoặc browser Playwright qua public HTTPS để đo STS của WebFlux.
4. Tạo một profile chỉ có Reactive API chain, không có fallback; đo header ở public static resources, sau đó thêm fallback phù hợp.
5. Đừng dùng `WebSecurityCustomizer`/`ForwardedHeaderFilter` Servlet để sửa Reactive code.

### Nhiệm vụ 6 — Policy rollout có kiểm soát

1. Kiểm thử một max-age ngắn ở HTTPS staging host.
2. Mô phỏng có subdomain legacy chỉ HTTP; giải thích vì sao không nên bật `includeSubDomains`.
3. Đặt `max-age=0` ở một phản ví dụ lab để quan sát ý nghĩa xóa policy, không gọi đó là “bật HSTS”.
4. Nêu các điều kiện cần review trước khi bật preload.
5. Tạo kế hoạch rollout/canary/rollback không đánh mất bảo vệ TLS.

### Mẫu bảng bằng chứng

| Ca | Public HTTPS? | Scheme Spring thấy | HSTS public | Nguyên nhân/kết luận |
|---|---|---|---|---|
| Servlet trước forwarded processing | Có | `http` | Có thể thiếu | Spring-owned writer không thấy secure |
| Servlet sau trusted framework forwarding | Có | `https` | Theo policy | Scheme correction đã hoạt động |
| CDN strip STS | Có | Có thể `https` | Thiếu | Edge làm mất header |
| Edge-owned HSTS | Có | Có thể `http` | Có | Header do public TLS edge phát |
| HTTP public | Không | Không áp dụng | Không phải bằng chứng HSTS | Browser không học HSTS qua HTTP |
| Multiple-hop ghi đè proto | Có | `http` | Có thể thiếu | Sửa hop làm sai trust chain |
| WebFlux no matching chain | Có | Có thể `https` | Có thể thiếu | Bổ sung reactive fallback |
| STS `max-age=0` | Có | Bất kỳ | Có nhưng policy hủy | Sửa rollout policy |

## 42. Câu hỏi tự đánh giá

1. Vì sao URL `https://app.example.com` trên browser không bảo đảm Servlet `request.isSecure() == true`?
2. HSTS được browser chấp nhận trên HTTP hay HTTPS?
3. `max-age` biểu thị gì? `max-age=0` có phải bật HSTS không?
4. Vì sao HTTP 301 đến HTTPS không thể thay thế HSTS dài hạn?
5. Browser đã biết HSTS từ cache/preload có thể khiến việc debug response hiện tại bị nhầm thế nào?
6. `HeaderWriterFilter` và `HstsHeaderWriter` giữ vai trò gì ở Servlet?
7. Vì sao các headers như `nosniff` vẫn có thể xuất hiện khi HSTS thiếu?
8. `server.forward-headers-strategy=none/framework/native` khác nhau về ý tưởng thế nào?
9. Khi nào nên dùng cơ chế container native thay vì Spring framework forwarding?
10. Vì sao `ForwardedHeaderFilter` không phải cơ chế xác thực proxy?
11. HSTS thiếu do `request.isSecure()==false` khác với `headers().disable()` thế nào?
12. Nếu MockMvc `secure(true)` PASS nhưng HTTPS public thiếu STS, phải kiểm tra gì tiếp?
13. Vì sao một test MockMvc tự gắn `X-Forwarded-Proto: https` không chứng minh trust boundary an toàn?
14. Trong WebFlux, `ForwardedHeaderTransformer` xử lý loại metadata nào?
15. Vì sao `ServerHttpRequest.getSslInfo() == null` không tự chứng minh browser dùng HTTP sau TLS termination?
16. Nếu CDN nhận TLS nhưng ingress ghi `X-Forwarded-Proto: http`, sửa ở tầng nào?
17. Nếu Spring origin phát STS nhưng public response thiếu, sửa ở đâu?
18. Nếu assets không match security chain, liệu sửa forwarding có đủ để header writer chạy không?
19. Vì sao HSTS của edge có thể phù hợp hơn khi nhiều Spring services chia sẻ một public hostname?
20. Khi có hai STS headers khác `max-age`, có nên để browser tự chọn? Vì sao?
21. Vì sao cần kiểm tra HSTS trên 404/500/redirect từ edge?
22. `includeSubDomains` có những rủi ro gì với hệ thống legacy chưa có HTTPS?
23. Header `preload` có tự đưa hostname vào browser preload list không?
24. Nếu cookie `Secure`, OAuth callback và HSTS cùng sai sau proxy, chúng có thể chung nguyên nhân nào?
25. Sai scheme có thể ảnh hưởng Origin/CORS policy và redirect URL như thế nào?
26. Vì sao không nên tắt cookie Secure hoặc CSRF để khắc phục HSTS?
27. Negative ingress test với `X-Forwarded-Proto: http` trên HTTPS public có mục tiêu gì?
28. Nếu backend lộ Internet và tin forwarded headers từ client, rủi ro nào lớn hơn việc thiếu HSTS?
29. Vì sao `curl -I` hoặc HTTP local không đủ để kết luận HSTS production đúng?
30. Những phép thử nào phải PASS trước khi báo hoàn tất sửa HSTS trên hệ thống có Servlet, WebFlux, CDN và proxy?

## 43. Ghi nhớ

**HSTS không xuất hiện sau reverse proxy thường bắt nguồn từ sự lệch nhau giữa HTTPS public và HTTP upstream.** Trên Servlet, Spring Security `HstsHeaderWriter` thường chỉ ghi STS khi request được nhận diện secure. Nếu proxy kết thúc TLS rồi chuyển HTTP vào backend nhưng `Forwarded`/`X-Forwarded-Proto` chưa được xử lý đúng, `request.isSecure()` có thể false và HSTS bị bỏ qua — dù những security headers khác vẫn có mặt.

Có hai hướng triển khai có thể đúng: **Spring-owned HSTS** với forwarded processing đáng tin, hoặc **edge-owned HSTS** trên HTTPS responses công khai. Trong cả hai, phải xác định trust boundary, sanitize headers do client gửi, không để backend bị bypass proxy và đảm bảo browser nhận policy HSTS hợp lệ. Với Reactive/WebFlux, cần dùng `ForwardedHeaderTransformer`, `ServerHttpSecurity` và `SecurityWebFilterChain` tương ứng, không sao chép Servlet filter code.

**Chẩn đoán theo chuỗi:** HTTPS public response → nơi tạo response → matching security chain và header writer → scheme app nhận → proxy forwarded metadata → STS cuối cùng ở edge → tests cho login, redirects, static assets, error pages và nhiều nodes. Đừng nhầm sự hiện diện của STS `max-age=0` với chính sách đang bật; đừng thêm `includeSubDomains`/`preload` trước khi đánh giá TLS của toàn bộ subdomains.

Trong phạm vi `SPRING_SECURITY_HTTP_PROTECTION`, một bản sửa chỉ hoàn thành khi HSTS hoạt động trên đường HTTPS công khai **mà vẫn bảo toàn** cookie Secure/HttpOnly, authentication, authorization, CSRF, CORS, CSP, HTTP firewall và bảo vệ session. Mục tiêu không phải chỉ làm scanner thấy thêm một header, mà là giúp browser tiếp tục kết nối an toàn với host đúng trong một kiến trúc proxy được tin cậy.
