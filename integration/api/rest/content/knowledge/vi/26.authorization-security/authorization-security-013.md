# Security header, TLS và cấu hình môi trường

Một REST API có xác thực và phân quyền chính xác vẫn có thể lộ thông tin nếu truyền token qua HTTP, dùng chứng chỉ TLS sai, tin tưởng header do client tự đặt, cache phản hồi nhạy cảm hoặc công khai công cụ quản trị ở môi trường production. Vì thế, an toàn API phải được thiết kế xuyên suốt từ **kết nối, HTTP response, reverse proxy đến cấu hình triển khai**.

Trong mô-đun **INTEGRATION_API_REST**, các resource, URI, phương thức và mã trạng thái HTTP tạo thành hợp đồng giao tiếp. Header bảo mật, chính sách TLS và cấu hình vận hành bổ sung những điều kiện bảo vệ hợp đồng ấy. Bài học thuộc chương **Phân quyền và an toàn**, minh họa cách áp dụng cho Java/Spring Boot và các hệ thống REST API dùng gateway hoặc reverse proxy.

## 1. Mục tiêu và mô hình đe dọa

Sau bài này, người học có thể:

1. Giải thích TLS bảo vệ điều gì, cách xác thực danh tính server và khi nào cần mTLS.
2. Chọn các HTTP security header phù hợp với JSON API, trang tài liệu HTML và phản hồi chứa dữ liệu nhạy cảm.
3. Cấu hình Spring Security, HTTPS termination và forwarded headers mà không cho client giả mạo thông tin kết nối.
4. Phân biệt cấu hình local, test, staging và production; quản lý secret, điểm giám sát và quyền của endpoint vận hành.
5. Kiểm tra TLS, header, CORS, cache và cấu hình môi trường bằng công cụ HTTP, kiểm thử Spring và kiểm tra bản triển khai thực tế.

Hãy xét một kiến trúc thông dụng:

~~~mermaid
flowchart LR
    U["Browser / Java client"] -->|"HTTPS, TLS 1.2/1.3"| E["Gateway / Reverse proxy"]
    E -->|"HTTPS/mTLS hoặc kênh nội bộ được bảo vệ"| A["Spring REST API"]
    A -->|"TLS, xác thực dịch vụ"| B["Database / Service khác"]
    C["Secret manager / CI-CD"] -->|"Cấp chứng chỉ và secret"| E
    C -->|"Cấp cấu hình runtime"| A
~~~

| Điểm yếu | Hệ quả có thể xảy ra | Biện pháp trọng tâm |
| --- | --- | --- |
| Client gọi HTTP không mã hóa | Token, cookie hoặc dữ liệu bị nghe lén/sửa đổi | HTTPS bắt buộc, HSTS cho browser, không gửi credential qua HTTP |
| Java client bỏ qua kiểm tra chứng chỉ | Kết nối bị giả mạo dù URI bắt đầu bằng `https://` | Tin CA phù hợp, kiểm tra hostname/SAN, không dùng trust-all |
| Proxy tin `X-Forwarded-*` từ Internet | Giả mạo scheme/IP/host, sai redirect, bypass kiểm soát dựa IP | Chỉ tin proxy xác định; loại bỏ/ghi đè forwarded headers từ client |
| JSON chứa PII bị lưu cache ngoài ý muốn | Lộ dữ liệu qua cache trình duyệt hoặc proxy | `Cache-Control: no-store` cho phản hồi phù hợp |
| Swagger UI hoặc actuator công khai ở production | Lộ cấu trúc API, metric hoặc thao tác vận hành | Hạn chế exposure, áp dụng xác thực/phân quyền và hạn chế mạng |
| Khóa riêng TLS và secret nằm trong repository | Rò bí mật kéo dài, khó thu hồi | Secret manager, cấp quyền tối thiểu, xoay vòng và giám sát |

**Không có một header nào thay thế TLS, xác thực hay phân quyền.** Ngược lại, TLS tốt cũng không tự động ngăn Broken Function Level Authorization (BFLA), Broken Object Level Authorization (BOLA), SQL injection hoặc phản hồi lộ dữ liệu.

## 2. TLS: bảo vệ kênh truyền và danh tính server

### 2.1. HTTPS giải quyết vấn đề gì?

HTTPS là HTTP chạy trên TLS. Khi thiết lập kết nối, TLS giúp client xác thực danh tính đầu bên kia bằng chứng chỉ, thỏa thuận khóa phiên và bảo vệ tính bí mật, toàn vẹn dữ liệu trong khi truyền. Với kết nối tới `https://api.example.test`, client cần kiểm tra:

- Chứng chỉ nằm trong chuỗi tin cậy dẫn đến CA mà client tin; chuỗi chứng chỉ được cấu hình đầy đủ.
- Tên server trong URI phù hợp với **Subject Alternative Name (SAN)** của chứng chỉ; không dựa vào việc có chuỗi tên miền ở trường CN.
- Chứng chỉ còn hiệu lực và các ràng buộc sử dụng khóa phù hợp; khóa riêng được giữ an toàn tại server hoặc bộ chấm dứt TLS.
- Phiên bắt tay dùng phiên bản/gói mật mã được phép; không tự hạ xuống giao thức hoặc thuật toán yếu.

Với hệ thống mới, ưu tiên TLS 1.3; cho phép TLS 1.2 khi phải hỗ trợ client hợp lệ và đã áp dụng cấu hình mật mã an toàn. Không bật TLS 1.0/1.1, cipher yếu hoặc thuật toán cũ chỉ để một client lỗi thời có thể kết nối. TLS bảo vệ từng **chặng kết nối**: nếu gateway giải mã HTTPS rồi chuyển HTTP tới backend, đoạn giữa gateway và backend vẫn cần được đặt trong ranh giới mạng tin cậy và đánh giá rủi ro; qua mạng không tin cậy nên tiếp tục dùng TLS, thường là mTLS khi cần xác thực dịch vụ.

**mTLS (mutual TLS)** buộc cả server và client xuất trình chứng chỉ. Nó hữu ích cho giao tiếp service-to-service, nhưng chứng chỉ dịch vụ chỉ chứng minh danh tính của bên gọi ở tầng kết nối. Endpoint nhạy cảm vẫn phải phân quyền theo hành động, đối tượng và tenant. Khi sử dụng mTLS tại gateway, backend chỉ được tin danh tính client nếu gateway truyền thông tin đó qua kênh được bảo vệ và tự loại bỏ header giả mạo từ client ngoài.

### 2.2. Những sai lầm TLS thường thấy

- Bật tùy chọn “bỏ qua certificate verification”, `curl -k` hay bộ `TrustManager` chấp nhận mọi chứng chỉ để xử lý lỗi môi trường: kết quả kiểm thử có thể trông thành công dù kết nối không xác thực đúng server.
- Chỉ kiểm tra một request từ trình duyệt mà không thử Java client, mobile client, worker và webhook; mỗi nhóm có trust store và thời gian cập nhật riêng.
- Gia hạn chứng chỉ tại gateway nhưng quên chứng chỉ dùng cho một hostname phụ, gRPC endpoint, management endpoint hoặc kết nối nội bộ.
- Sao chép private key vào container image, log hoặc ticket; đưa mật khẩu keystore vào file `application.yml` đã commit.
- Chỉ kiểm tra ngày hết hạn lúc triển khai, không giám sát cảnh báo trước hạn và không thử quy trình xoay vòng chứng chỉ.

Nếu Java gọi dịch vụ HTTPS, thư viện HTTP hiện đại thường dùng xác thực TLS mặc định. Ví dụ:

~~~java
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.test/v1/status"))
    .GET()
    .build();

HttpResponse<String> response = client.send(
    request, HttpResponse.BodyHandlers.ofString());
~~~

`HttpClient.newHttpClient()` dùng cấu hình TLS/trust store mặc định của JVM. Với CA riêng của tổ chức, cung cấp trust store được quản lý phù hợp thay vì tắt hostname verification. Không viết custom `HostnameVerifier` luôn trả `true`, custom `X509TrustManager` bỏ qua xác thực hoặc can thiệp SSL để “fix” môi trường.

### 2.3. HTTPS redirection và HSTS

HTTP có thể được cấu hình chuyển hướng sang HTTPS, chẳng hạn trả `308 Permanent Redirect`. Tuy nhiên, lần kết nối HTTP đầu tiên vẫn chưa được mã hóa; client **không được gửi Bearer token, cookie nhạy cảm hoặc mật khẩu qua HTTP để chờ redirect**. Hãy dùng URL HTTPS từ đầu, đặc biệt cho SDK, webhook và service-to-service.

HSTS (`Strict-Transport-Security`) hướng dẫn **trình duyệt** dùng HTTPS cho host trong một khoảng thời gian sau khi trình duyệt nhận header qua kết nối HTTPS hợp lệ:

~~~http
HTTP/1.1 200 OK
Strict-Transport-Security: max-age=31536000
~~~

`max-age` tính bằng giây. `includeSubDomains` chỉ nên bật khi **mọi** subdomain liên quan đã hỗ trợ HTTPS và có kế hoạch chuyển đổi; `preload` đòi hỏi đánh giá thêm vì thu hồi chính sách có thể khó và chậm. Bắt đầu với chính sách phù hợp thực trạng, tăng thời gian sau khi đã kiểm chứng, rồi mới cân nhắc preload. Header HSTS phát qua HTTP bị trình duyệt bỏ qua; HSTS cũng không thay thế kiểm tra chứng chỉ của Java/CLI client.

## 3. Các HTTP security header theo ngữ cảnh

Không nên sao chép nguyên bộ header dành cho ứng dụng HTML sang JSON API mà thiếu phân tích. Header nào hữu ích phụ thuộc vào việc browser có **render** nội dung hay chỉ đọc JSON, response có dữ liệu nhạy cảm không và endpoint có hỗ trợ cookie hay không.

| Header hoặc nhóm header | Vai trò | Hướng dẫn cho REST API |
| --- | --- | --- |
| `Strict-Transport-Security` | Yêu cầu browser ưu tiên HTTPS trên host | Dùng trên HTTPS ở ingress/gateway hoặc app, chọn `max-age` có chủ đích |
| `X-Content-Type-Options: nosniff` | Hạn chế browser đoán MIME type | Nên có; kết hợp `Content-Type` chính xác |
| `Cache-Control` | Kiểm soát cách lưu cache | `no-store` cho token, PII hoặc dữ liệu không được phép lưu; chọn riêng cho API công khai |
| `Content-Security-Policy` (CSP) | Hạn chế nguồn script, style, frame của tài liệu được render | Quan trọng cho HTML như Swagger UI/admin console; ít ý nghĩa với JSON thuần |
| `X-Frame-Options` / CSP `frame-ancestors` | Kiểm soát nhúng trang trong frame | Hữu ích cho HTML; `frame-ancestors` cho chính sách hiện đại |
| `Referrer-Policy` | Hạn chế dữ liệu được gửi qua `Referer` khi điều hướng | Dùng `no-referrer` hoặc chính sách phù hợp cho trang web nhạy cảm |
| `Permissions-Policy` | Hạn chế một số browser features | Chọn theo nhu cầu trang HTML; không phải biện pháp phân quyền REST |
| `Access-Control-Allow-*` | Cho browser biết origin nào được phép đọc cross-origin | Cấu hình CORS theo allowlist; không thay thế xác thực/phân quyền |
| `Set-Cookie` với `Secure`, `HttpOnly`, `SameSite` | Giảm rủi ro với cookie xác thực | Chỉ áp dụng khi hệ thống dùng cookie; phải xét CSRF |
| `Content-Disposition` | Quy định trình duyệt xử lý nội dung download | Dùng phù hợp với file export, tránh tên file do client kiểm soát gây lỗi |

### 3.1. Content-Type, nosniff và dữ liệu phản hồi

Với JSON API, hãy trả `Content-Type: application/json` hoặc `application/problem+json` cho lỗi theo Problem Details. Với tài liệu HTML, trả `text/html; charset=UTF-8`. Với tệp tải xuống, chỉ định đúng media type và `Content-Disposition` phù hợp. Header `X-Content-Type-Options: nosniff` giúp tránh một số trường hợp browser giải thích kiểu dữ liệu sai, nhưng không thay thế encode/escape output khi đưa dữ liệu lên trang HTML.

Ví dụ phản hồi chứa thông tin tài khoản:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Content-Type-Options: nosniff
Cache-Control: no-store

{"id":"u-42","email":"user@example.test"}
~~~

`Cache-Control: no-store` yêu cầu cache không lưu request/response ở các cache tuân thủ chuẩn; nó không xóa dữ liệu đã lưu trước đó, không ngăn client lưu dữ liệu cố ý và không bảo vệ dữ liệu khỏi logging. `no-cache` **không đồng nghĩa** “không lưu”: cache có thể lưu nhưng phải tái xác nhận trước khi sử dụng. `private` cho phép browser cache và chặn shared cache; chỉ dùng khi chính sách dữ liệu cho phép. API công khai có thể chủ động dùng `public, max-age=...` hoặc ETag, nhưng phải xác định rõ resource và tránh cache nhầm dữ liệu người dùng/tenant khác.

### 3.2. CSP, frame và trang tài liệu API

Nếu triển khai Swagger UI, Redoc hoặc admin console trong cùng hệ thống, đó là **trang HTML chạy JavaScript** nên cần CSP phù hợp. Ví dụ chính sách khởi đầu cho trang HTML hoàn toàn do ứng dụng kiểm soát:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'
X-Frame-Options: DENY
Referrer-Policy: no-referrer
~~~

Đây là ví dụ chính sách nghiêm ngặt, không bảo đảm chạy nguyên vẹn với mọi Swagger UI: một số build cần script/style được cấp bằng nonce hoặc hash, và `connect-src` phải đúng API origin. Nên kiểm tra CSP ở chế độ `Content-Security-Policy-Report-Only` trước khi bật thực thi trên trang đang hoạt động; tuyệt đối không mở `unsafe-inline` rộng rãi chỉ để bỏ qua lỗi mà chưa hiểu nguyên nhân.

`frame-ancestors` điều khiển nguồn được phép nhúng trang và **không thể đặt bằng thẻ HTML meta**. `X-Frame-Options: DENY` là lớp tương thích cho browser cũ. Nếu có trang thực sự cần nhúng hợp lệ, hãy thiết kế chính sách riêng cho trang đó. Các header như COOP/COEP/CORP có thể cần trong ứng dụng browser đặc thù, nhưng có thể làm hỏng tích hợp nhúng hoặc tải tài nguyên; không nên áp đặt như checklist chung cho mọi JSON endpoint.

Không tiếp tục khuyên dùng `X-XSS-Protection` làm biện pháp chính: cơ chế cũ không còn là kiểm soát đáng tin cậy. CSP, escaping đúng ngữ cảnh, template an toàn và tránh DOM XSS mới là trọng tâm với HTML.

### 3.3. Cookie, CSRF và CORS

REST API dùng `Authorization: Bearer ...` do client gửi rõ ràng thường có đặc tính trình duyệt khác với API dùng session cookie tự động đính kèm. Nếu dùng cookie:

~~~http
Set-Cookie: __Host-session=<opaque-value>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

`Secure` chỉ gửi cookie qua kết nối an toàn; `HttpOnly` chặn truy cập bằng JavaScript trong browser; `SameSite` hỗ trợ giảm một số tình huống CSRF nhưng **không thay thế** CSRF token và chính sách origin khi nghiệp vụ cần. Tiền tố `__Host-` đòi hỏi `Secure`, `Path=/` và không có thuộc tính `Domain` trên browser hỗ trợ. `SameSite=None` phải đi cùng `Secure`, chỉ dùng khi thực sự cần cross-site. Hạn chế dùng cookie dài hạn cho token có quyền cao và xác định rõ quy trình logout/revoke.

CORS chỉ là chính sách browser đọc phản hồi cross-origin, **không phải lớp xác thực**. Một chương trình Java, cURL hoặc server khác không bị ngăn chỉ vì response thiếu `Access-Control-Allow-Origin`. Không coi preflight `OPTIONS` thành công là bằng chứng request thật có quyền truy cập. Với API cho phép một frontend quản trị:

~~~http
OPTIONS /api/v1/reports HTTP/1.1
Origin: https://console.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type

HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://console.example.test
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: authorization,content-type
Vary: Origin
~~~

Chính sách CORS chỉ cho phép origin đã duyệt; đừng phản chiếu bừa giá trị `Origin` từ client. Khi response thay đổi theo origin, cache phải có `Vary: Origin`; nhiều framework cũng thêm `Vary: Access-Control-Request-Method` và `Vary: Access-Control-Request-Headers`. Không dùng `Access-Control-Allow-Origin: *` cùng credential; với cookie cross-origin cần allowlist cụ thể, `Access-Control-Allow-Credentials: true` và biện pháp CSRF phù hợp.

## 4. TLS termination và forwarded headers

Khi trình duyệt dùng HTTPS tới gateway nhưng gateway chuyển tiếp HTTP tới ứng dụng, Spring có thể thấy `request.isSecure() == false` và sinh redirect sai scheme hoặc bỏ qua HSTS nếu không có cấu hình proxy đáng tin cậy. Các header như `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host` và `X-Forwarded-For` chỉ đáng tin khi được đặt bởi **proxy do tổ chức quản lý**, sau khi loại bỏ giá trị client tự gửi.

Ví dụ Nginx minh họa một ingress duy nhất trước backend trong mạng riêng:

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.test;

    ssl_certificate     /etc/tls/fullchain.pem;
    ssl_certificate_key /etc/tls/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;

    location / {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

Trong ví dụ, `api_backend` được giả định chỉ truy cập được từ mạng private của gateway; khi đường truyền qua vùng không tin cậy hãy dùng HTTPS hoặc mTLS giữa proxy và backend. Việc đặt `X-Forwarded-For` bằng `$remote_addr` minh họa thao tác **ghi đè đầu vào** tại ingress; trong kiến trúc nhiều proxy phải thiết lập chính sách tin cậy/real IP cụ thể cho từng hop, không tự động tin phần tử đầu tiên của chuỗi do client gửi. Với Nginx, `add_header` có quy tắc kế thừa theo location: nếu cấu hình lại `add_header` ở location con, cần kiểm tra các header cấp trên có còn được gửi không. Từ khóa `always` giúp gửi header kể cả nhiều phản hồi lỗi.

Hai hướng triển khai hợp lệ:

1. **TLS kết thúc ở gateway:** gateway quản lý chứng chỉ, giao thức và HSTS; backend dùng forwarded headers đã được gateway chuẩn hóa. Chỉ gateway được kết nối tới backend, và lớp mạng giữa các thành phần được bảo vệ.
2. **TLS kết thúc trực tiếp ở Spring:** Spring sở hữu keystore và trả HTTPS trực tiếp. Nếu có proxy phía trước, vẫn phải định nghĩa rõ scheme, trusted hop và trách nhiệm phát HSTS.

Nên chỉ định **một nơi chịu trách nhiệm chuẩn** cho mỗi security header để tránh giá trị trùng nhau hoặc mâu thuẫn giữa gateway và ứng dụng. Đồng thời không dùng forwarded IP do client tự khai để quyết định quyền quản trị hoặc miễn trừ rate limit.

## 5. Cấu hình Spring Boot và Spring Security

Ví dụ sử dụng Spring Boot 3 và Spring Security 6. Phần mã minh họa một JSON API stateless với JWT trong header, không dùng session cookie làm thông tin xác thực. Spring Security mặc định đã có một số header an toàn, nhưng ứng dụng vẫn cần cấu hình phù hợp với route, mức nhạy cảm và vị trí TLS termination.

### 5.1. Filter chain cho API

~~~java
@Configuration
@EnableWebSecurity
public class ApiSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/v1/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .headers(headers -> headers
                .contentTypeOptions(Customizer.withDefaults())
                .frameOptions(frame -> frame.deny())
                .referrerPolicy(ref -> ref.policy(
                    ReferrerPolicyHeaderWriter.ReferrerPolicy.NO_REFERRER))
                .httpStrictTransportSecurity(hsts -> hsts
                    .maxAgeInSeconds(31536000)
                    .includeSubDomains(false)))
            .build();
    }
}
~~~

Cần các import Spring Security tương ứng (`HttpSecurity`, `SecurityFilterChain`, `SessionCreationPolicy`, `AbstractHttpConfigurer`, `Customizer`, `HttpMethod` và `ReferrerPolicyHeaderWriter`). Đây là filter chain cho `/api/**`; các URL tài liệu, health, actuator hoặc trang HTML cần filter chain/chính sách riêng và phải được đối chiếu thứ tự, `securityMatcher`, cũng như quy tắc fallback. Quy tắc `.anyRequest().authenticated()` chỉ yêu cầu đăng nhập; **hành động nhạy cảm phải có thêm permission/role và kiểm tra quyền đối tượng tại service**.

Spring Security thường chỉ thêm HSTS khi request được xem là **secure**. Vì thế cấu hình `.httpStrictTransportSecurity(...)` không có nghĩa backend sau proxy HTTP sẽ phát HSTS nếu nó không nhận biết đúng scheme. Nếu gateway đã sở hữu HSTS, có thể bỏ cấu hình HSTS khỏi chain và kiểm tra header ở ingress; nếu Spring sở hữu, kiểm tra HTTPS nhận diện đúng qua proxy đã được tin cậy.

`csrf(AbstractHttpConfigurer::disable)` chỉ phù hợp với API không sử dụng browser cookie để tự động gửi thông tin xác thực. Với API dùng session/cookie, cần bảo vệ CSRF cho thao tác đổi trạng thái; tắt CSRF một cách máy móc có thể tạo lỗ hổng.

### 5.2. Cache-Control cho dữ liệu nhạy cảm

Không nhất thiết phải ép `no-store` cho mọi resource: một API catalog công khai có thể được cache chủ động nhằm giảm tải, trong khi token, thông tin hồ sơ, dữ liệu sức khỏe hoặc bí mật phải có chính sách hạn chế phù hợp.

~~~java
@RestController
@RequestMapping("/api/v1/me")
class ProfileController {
    private final ProfileService profiles;

    ProfileController(ProfileService profiles) {
        this.profiles = profiles;
    }

    @GetMapping
    ResponseEntity<ProfileDto> current(Authentication authentication) {
        ProfileDto dto = profiles.findFor(authentication.getName());
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(dto);
    }
}
~~~

`ProfileService` và `ProfileDto` là thành phần ứng dụng giả định. Tầng nghiệp vụ vẫn phải phân quyền dữ liệu hồ sơ; cache header không thay thế kiểm tra quyền. Nếu hệ thống dùng CDN, hãy rà soát cả cache key, `Authorization`, `Cookie`, `Vary` và chính sách caching tại gateway để dữ liệu của người dùng/tenant này không được trả cho người khác.

### 5.3. CORS có allowlist

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://console.example.test"));
    cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
    cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
    cors.setAllowCredentials(false); // Ví dụ dùng Bearer, không dùng cookie.
    cors.setMaxAge(3600L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cors);
    return source;
}
~~~

Filter chain ở mục 5.1 đã bật `.cors(Customizer.withDefaults())` để Spring Security xử lý preflight trước bước xác thực cần thiết. Đưa tập origin vào cấu hình môi trường được quản lý và kiểm tra giá trị hợp lệ khi khởi động; tránh wildcard và phản chiếu origin một cách tự động. Đừng hiểu `setAllowCredentials(false)` là cấm header Bearer: nó quy định chế độ credential của CORS trong browser, còn bearer token do ứng dụng gửi được xét theo chính sách và cách gọi frontend.

### 5.4. TLS trực tiếp tại Spring

Khi ứng dụng tự kết thúc HTTPS, có thể cấu hình keystore PKCS#12 bên ngoài repository:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:/run/secrets/api-server.p12
    key-store-type: PKCS12
    key-store-password: ${TLS_KEYSTORE_PASSWORD}
    key-alias: api-server
~~~

Tên alias và đường dẫn phải khớp keystore thực tế; giá trị `TLS_KEYSTORE_PASSWORD` được tiêm từ cơ chế secret của runtime, không commit trong mã nguồn. Môi trường production cần cơ chế quản lý/gia hạn/reload chứng chỉ thích hợp; một số cách thay chứng chỉ đòi hỏi restart hay reload dịch vụ. Nếu TLS kết thúc ở ingress, cấu hình HTTPS nên đặt ở ingress, đồng thời chặn backend khỏi Internet.

Đằng sau trusted reverse proxy, Spring Boot hỗ trợ `server.forward-headers-strategy`, ví dụ `framework` để xử lý forwarded headers. **Chỉ bật khi** backend nằm sau proxy tin cậy đã lọc header đầu vào và kết nối trực tiếp từ Internet tới backend bị chặn. Nếu proxy gửi header không được chuẩn hóa, thiết lập này có thể biến dữ liệu client gửi thành nguồn xác định host, scheme, URL redirect và IP.

## 6. Cấu hình môi trường và bảo vệ vận hành

Cùng một artifact ứng dụng nên nhận cấu hình theo môi trường, qua deployment configuration và secret manager; tránh tạo các bản build riêng với bí mật nhúng trong code. Tuy nhiên, “đọc giá trị từ biến môi trường” không tự động bảo đảm an toàn: biến môi trường có thể bị lộ qua công cụ quản trị, log, process dump hoặc quyền truy cập host.

| Hạng mục | Local / Test | Staging | Production |
| --- | --- | --- | --- |
| TLS | Có thể dùng CA phát triển, chỉ trong môi trường cách ly | Chứng chỉ hợp lệ, mô phỏng ingress thực tế | Chứng chỉ tin cậy, giám sát hết hạn, xoay vòng |
| Secret | Dữ liệu giả, không đưa secret production vào máy dev | Secret riêng, phạm vi hạn chế | Secret manager, rotation, quyền tối thiểu |
| CORS | Origin dev được chỉ định rõ | Origin staging chính xác | Chỉ frontend tin cậy, không wildcard credential |
| Logging | Có thể tăng độ chi tiết có kiểm soát | Phục vụ kiểm chứng | Không log token/PII, không bật debug kéo dài |
| Swagger/OpenAPI UI | Có thể bật cho học và phát triển | Được kiểm soát truy cập | Chỉ công khai nếu chủ đích; hạn chế/đóng UI quản trị |
| Actuator | Health và các endpoint cần để phát triển | Giống production | Exposure tối thiểu, bảo vệ endpoint nhạy cảm |
| Cấu hình lỗi | Có thể xem trace trong môi trường cô lập | Trả lỗi tương tự production | Không lộ stack trace, secret, chi tiết nội bộ |

Ví dụ cấu hình production thiên về giới hạn exposure:

~~~yaml
server:
  error:
    include-message: never
    include-stacktrace: never

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never

logging:
  level:
    org.springframework.security: INFO
~~~

Việc bảo vệ management port, metrics, health details và API tài liệu còn phụ thuộc network policy và filter chain thực tế. Chỉ giới hạn exposure trong cấu hình không thay thế biện pháp chặn truy cập ở ingress. `health` public có thể hợp lý cho probe nhưng không nên tiết lộ cấu hình, danh sách phụ thuộc hoặc phiên bản thư viện; `env`, `configprops`, `heapdump` và endpoint thao tác vận hành cần được khóa chặt hoặc không exposure.

Nên đặt chính sách cấu hình tối thiểu cho từng môi trường:

1. **Bí mật và chứng chỉ:** private key, keystore password, DB credential, OAuth client secret và API key nằm ngoài repository/container image; cấp quyền đọc tối thiểu, thay định kỳ hoặc ngay khi nghi lộ. Không in secret ra console khi lỗi khởi động.
2. **Nguồn cấu hình:** xác định rõ thứ tự ưu tiên của property từ YAML, profile, biến môi trường và tham số dòng lệnh. Tránh cấu hình cũ còn sót trong file profile khiến production bật debug hoặc cho phép origin quá rộng.
3. **Fail closed:** nếu thiếu issuer, audience, CORS allowlist bắt buộc, khóa hoặc secret, ứng dụng nên từ chối khởi động hoặc từ chối chức năng tương ứng thay vì âm thầm dùng giá trị development.
4. **Ranh giới mạng:** chỉ mở những port công khai cần thiết; backend, database và management port không thể bị gọi trực tiếp từ Internet. Giao tiếp liên vùng tin cậy cần TLS và danh tính dịch vụ.
5. **Vận hành:** thiết lập cảnh báo hết hạn chứng chỉ, lỗi bắt tay TLS, tăng đột biến 401/403, thay đổi cấu hình hoặc phát sinh bất thường ở endpoint nhạy cảm; giới hạn dữ liệu nhạy cảm trong audit log.
6. **Triển khai và rollback:** cấu hình được version hóa như chính sách (không kèm bí mật), review thay đổi gateway/HSTS/TLS/CORS, có smoke test trên môi trường thật và kế hoạch khôi phục nếu policy gây gián đoạn.

Một lỗi đáng chú ý là để `server.forward-headers-strategy: framework` cùng rule dựa `X-Forwarded-For` trong môi trường mà backend có thể bị truy cập thẳng. Người gọi có thể tự đặt header và đánh lừa logic gắn với địa chỉ IP. Nếu cần kiểm soát truy cập quản trị, dùng xác thực dịch vụ và quyền người dùng; giới hạn IP tại proxy/firewall chỉ là một lớp hỗ trợ.

## 7. Kiểm thử và xác minh cấu hình thực tế

Kiểm thử đơn vị của Spring không kiểm tra được toàn bộ đường đi TLS ngoài thực tế. Cần kết hợp **kiểm thử response ở ứng dụng**, kiểm tra từ bên ngoài ingress và quan sát secret/certificate trong deployment.

### 7.1. Smoke test từ máy client

Thử với hostname thực và không tắt kiểm tra chứng chỉ:

~~~bash
# Kiểm tra certificate chain, tên host và kết nối HTTPS.
curl -vI https://api.example.test/api/v1/public/status

# Xem status/header, kể cả khi API trả 401/403.
curl -sS -D - -o /dev/null https://api.example.test/api/v1/me

# Xem quá trình bắt tay TLS và chứng chỉ phía server.
openssl s_client -connect api.example.test:443 \
    -servername api.example.test -verify_return_error
~~~

Đọc kết quả để xác nhận chứng chỉ phù hợp với hostname, còn hiệu lực, chuỗi tin cậy đầy đủ, chính sách TLS được áp dụng và header xuất hiện đúng trên **cả response thành công lẫn lỗi**. `openssl s_client` giúp khảo sát chain và xác thực CA tùy trust store cấu hình; cần kết hợp với client kiểm tra hostname như `curl`, không coi một thông báo “connected” là đủ. Nếu dùng wildcard certificate hoặc SNI, thử từng hostname thực; nếu TLS terminated ở CDN/gateway, kết quả bên ngoài phản ánh lớp đó thay vì cấu hình Spring.

Kiểm tra CORS với cả origin được phép và bị từ chối:

~~~bash
curl -i -X OPTIONS https://api.example.test/api/v1/reports \
  -H "Origin: https://console.example.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type"

curl -i -X OPTIONS https://api.example.test/api/v1/reports \
  -H "Origin: https://untrusted.example.test" \
  -H "Access-Control-Request-Method: POST"
~~~

Kỳ vọng origin hợp lệ được nhận header tương ứng; origin không hợp lệ không được cấp quyền CORS. Phản hồi preflight có thể mang mã khác nhau tùy framework, nhưng điều quan trọng là chính sách không cho browser đọc/truy cập cross-origin ngoài danh sách. **Tiếp tục thử request thật** với token thiếu quyền để chắc chắn backend trả `401`/`403`; CORS không phải security test cho chức năng quản trị.

### 7.2. Spring MockMvc test header

Giả định API có `GET /api/v1/me` trả dữ liệu riêng tư và filter chain ở mục 5.1 chịu trách nhiệm đặt HSTS:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SecurityHeadersIT {
    @Autowired MockMvc mvc;

    @Test
    void privateApiResponseHasExpectedHeaders() throws Exception {
        mvc.perform(get("/api/v1/me")
                .secure(true)
                .with(jwt().jwt(token -> token.subject("user-42"))))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Content-Type-Options", "nosniff"))
            .andExpect(header().string("X-Frame-Options", "DENY"))
            .andExpect(header().string("Cache-Control",
                containsString("no-store")))
            .andExpect(header().string("Strict-Transport-Security",
                containsString("max-age=")));
    }
}
~~~

Ví dụ cần import JUnit, MockMvc, `spring-security-test`, các matcher và Hamcrest tương ứng; dữ liệu profile kiểm thử phải khớp principal giả lập. `.secure(true)` giả lập HTTPS để kiểm tra cơ chế phát HSTS của Spring. Nếu hệ thống phát HSTS tại gateway, đừng ép MockMvc kiểm tra header của gateway; kiểm tra **deployed response** qua HTTPS từ ngoài thay thế. `jwt()` của Spring Security Test tạo authentication giả, không xác minh chữ ký hay chứng chỉ: viết integration test riêng với `JwtDecoder` và TLS thật.

Một ma trận kiểm tra tối thiểu:

| Trường hợp | Bằng chứng cần có |
| --- | --- |
| HTTPS đúng host và chứng chỉ hợp lệ | Client kết nối thành công mà không bật insecure mode |
| Chứng chỉ sai hostname, hết hạn, CA lạ | Client từ chối kết nối; test negative với hạ tầng thử nghiệm |
| HSTS trên HTTPS, kể cả response lỗi | Header có từ ingress hoặc app theo phân công |
| JSON nhạy cảm | `Content-Type` đúng, `nosniff`, `Cache-Control: no-store` |
| JSON công khai được cache | TTL và cache key có chủ đích; không trộn dữ liệu tenant |
| CORS allowed/disallowed origin | Preflight đúng allowlist; actual request vẫn cần quyền |
| Trang Swagger/admin HTML | CSP/frame policy hiệu lực, không chặn asset hợp lệ |
| Cookie xác thực | `Secure`, `HttpOnly`, `SameSite` và kiểm thử CSRF |
| API truy cập trực tiếp backend | Bị chặn bởi network policy hoặc nhận TLS và auth phù hợp |
| Actuator/config production | Chỉ endpoint dự kiến được exposure; không lộ môi trường/secret |

### 7.3. Các lỗi dễ gây kết luận sai

- Đo security headers trên HTTP redirect rồi kết luận HTTPS response đã đúng; cần đo **URL cuối và từng status**.
- Chỉ đo response `200` trong khi `401`, `403`, `404`, `500` từ gateway lại thiếu header bắt buộc.
- Kiểm tra HSTS qua MockMvc với request không được đánh dấu secure rồi tưởng Spring không hỗ trợ HSTS.
- Sử dụng `curl -k` trong bài smoke test làm mất bằng chứng xác minh certificate.
- Thấy `Access-Control-Allow-Origin` đúng rồi kết luận endpoint có phân quyền; yêu cầu từ Java/cURL không bị giới hạn bởi CORS.
- Thấy `no-cache` rồi tin rằng không cache lưu thông tin nhạy cảm; cần phân biệt với `no-store` và chính sách tại CDN.
- Thử certificate chỉ ở một ingress trong khi có nhiều hostname, cluster, region và endpoint quản trị phụ.

## 8. Bài tập thực hành

**Bài tập 1 — Chọn header theo loại response.** Thiết kế header cho ba endpoint: `GET /api/v1/catalog` trả dữ liệu công khai có thể cache, `GET /api/v1/me` trả email cá nhân, và `GET /docs` phục vụ Swagger UI. Giải thích sự khác nhau về `Cache-Control`, `Content-Type`, CSP, frame policy và HSTS. Nêu lý do vì sao CSP nghiêm ngặt có thể ảnh hưởng Swagger UI nhưng ít tác dụng với JSON thuần.

**Bài tập 2 — Sửa cấu hình proxy.** Gateway nhận kết nối HTTPS nhưng backend có thể truy cập trực tiếp qua port public. Ứng dụng bật `server.forward-headers-strategy=framework`, ghi log IP từ `X-Forwarded-For` và dựa vào IP đó để miễn xác thực. Hãy lập sơ đồ tấn công, đề xuất cấu hình network/proxy, sửa chính sách xác thực, và viết test chứng minh client không thể tự khai báo forwarded header để nhận quyền cao hơn.

**Bài tập 3 — Chuẩn hóa staging và production.** Một hệ thống lưu private key trong container image, bật actuator `env` công khai, trả stack trace cho client, và cho phép mọi CORS origin. Lập bảng gồm rủi ro, thay đổi cấu hình, chủ thể chịu trách nhiệm và kiểm thử xác nhận sau triển khai. Bổ sung phương án xoay vòng chứng chỉ không làm lộ khóa và phương án rollback khi thay đổi CORS/HSTS gây gián đoạn.

**Bài tập 4 — Kiểm thử Java/Spring.** Tạo endpoint `GET /api/v1/me` và dùng Spring Security/MockMvc kiểm tra `nosniff`, `no-store`, response lỗi 401/403 và HSTS theo thiết kế TLS termination. Viết một smoke test cURL chạy sau triển khai kiểm tra hostname/certificate và cùng bộ header. Đánh dấu rõ điều gì MockMvc kiểm được và điều gì phải đo ngoài ingress.

### Tiêu chí đánh giá

Một lời giải đạt yêu cầu phải chứng minh: (1) mọi đường công khai dùng HTTPS với xác thực certificate đúng; (2) gateway/backend có ranh giới tin cậy forwarded headers; (3) header phù hợp với dữ liệu JSON, HTML và cookie; (4) secret, actuator và chế độ debug được bảo vệ theo môi trường; (5) kiểm thử bao phủ response thành công, lỗi, origin không hợp lệ và cấu hình thực tế tại điểm truy cập công khai.

## 9. Checklist trước khi phát hành

- [ ] TLS 1.2/1.3 được cấu hình đúng; chứng chỉ hợp lệ cho mọi hostname, private key và việc gia hạn được quản lý.
- [ ] Không có Java client hoặc health check production bỏ qua certificate/hostname verification.
- [ ] HTTPS termination, HSTS và forwarded headers có chủ sở hữu, trusted proxy và kiểm thử từ bên ngoài.
- [ ] JSON nhạy cảm có `no-store`; resource cache công khai có TTL/cache key phù hợp; media type đi kèm `nosniff`.
- [ ] Swagger UI/trang HTML có CSP và frame policy được thử trên giao diện thật; API JSON không bị áp chính sách vô nghĩa.
- [ ] CORS chỉ cho phép origin cần thiết; session cookie có `Secure`/`HttpOnly`/`SameSite` và cơ chế CSRF phù hợp.
- [ ] Không có secret trong repo, image, log hoặc body lỗi; actuator và management endpoint chỉ exposure đúng nhu cầu.
- [ ] Kiểm thử tự động và smoke test kiểm tra cả response lỗi, CORS, TLS, health và các đường truy cập khác nhau.

**Kết luận:** TLS bảo vệ kết nối, HTTP security header giảm rủi ro khi client xử lý phản hồi, còn cấu hình môi trường bảo vệ ranh giới vận hành. Với REST API, cả ba phải được xác minh trên **đường request thực tế qua gateway đến service**, đồng thời duy trì xác thực, phân quyền và kiểm soát dữ liệu ở tầng nghiệp vụ.
