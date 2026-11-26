# HeaderWriter tương ứng và khác biệt hỗ trợ theo phiên bản

## 1. Tại sao không thể sao chép một cấu hình security headers cho mọi dự án?

Trong module **SPRING_SECURITY_HTTP_PROTECTION**, người học triển khai các lớp phòng vệ HTTP và trình duyệt của Spring Security, từ **CSRF, CORS, security headers, CSP, HSTS** đến **HTTP firewall và bảo vệ session** cho cả **Servlet** và **Reactive/WebFlux**. Ở chương **Quyền và cô lập trình duyệt**, nhiều header quan trọng có quan hệ với nhau nhưng không được cấu hình hoàn toàn giống nhau trong mọi phiên bản Spring Security.

Giả sử một hệ thống có:

- Ứng dụng Servlet phục vụ giao diện tại `https://learn.example.com`.
- API Reactive/WebFlux tại `https://api.example.com`.
- Một trang mô phỏng `/isolated/**` cần phối hợp COOP và COEP.
- Một số tài nguyên `/assets/public/**` cần được nhúng cross-origin, trong khi tài liệu tài khoản phải có bảo vệ chặt hơn.
- Một popup OAuth cũ cần giữ `window.opener` trong những điều kiện đã được kiểm thử.

Nhóm phát triển muốn thêm các response header:

```http
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
Cross-Origin-Resource-Policy: same-origin
```

Nhưng khi xem hai codebase khác phiên bản, một bên có DSL chuyên dụng, một bên không nhận ra tên method; hoặc một ví dụ Servlet dùng `HttpSecurity` trong khi dự án Reactive chỉ có `ServerHttpSecurity`. Một số header được Spring Security ghi **mặc định**, một số cần bật **tường minh**, và một số cần **chọn khác nhau theo response** chứ không được áp toàn site.

**Bài này giải quyết việc lựa chọn API/header writer đúng, không chỉ thuộc lòng tên header.**

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt `HeaderWriter` của Servlet với `ServerHttpHeadersWriter` của WebFlux và điểm gắn vào security chain.
2. Xác định header nào có thể dùng DSL chuyên dụng, header nào nên phát bằng **static writer** khi API thiếu hoặc phiên bản không tương thích.
3. Đọc bảng khả năng tương thích **theo phiên bản thư viện thực tế**, không suy từ một bài blog hoặc tên Spring Boot.
4. Giữ các default security headers, tránh phát header trùng/mâu thuẫn và chọn **phạm vi theo URL**.
5. Viết test với `MockMvc`, `WebTestClient` và browser để kiểm tra **cả response header lẫn hiệu lực thực tế**.

## 2. HeaderWriter là gì và nằm ở bước nào?

**Header writer** là thành phần của Spring Security được dùng để **ghi một hay nhiều HTTP response headers** trong quá trình xử lý request. Nó không tự sửa JavaScript, không truy cập phần cứng thay browser, không thêm quyền CORS vào request khác và không phải bộ máy phân quyền.

Trong Servlet, cấu hình chủ yếu đi qua:

```text
HTTP request
    │
    ▼
Spring Security filter chain
    │  authentication / authorization / CSRF / ...
    │  HeaderWriterFilter và các HeaderWriter được cấu hình
    ▼
Servlet controller / resource handler / error handler
    │
    ▼
HTTP response + security headers
    │
    ▼
Browser áp dụng CSP / COOP / COEP / CORP / ...
```

Đây là sơ đồ **khái niệm**, không phải lịch gọi chính xác của mọi filter hay thời điểm response commit. Một header writer có thể đăng ký thao tác ghi theo vòng đời response để header hiện diện khi response được gửi; thời điểm cụ thể phụ thuộc framework, loại response và phiên bản.

Trong Reactive/WebFlux, thành phần tương ứng là một **reactive header writer** được gọi bởi security web filter infrastructure trong luồng `ServerWebExchange`. Đây **không** phải Servlet filter chạy trên `HttpServletRequest`.

| Bề mặt | Servlet | Reactive/WebFlux |
| --- | --- | --- |
| Builder bảo mật | `HttpSecurity` | `ServerHttpSecurity` |
| Chain được đăng ký | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Interface writer | `HeaderWriter` | `ServerHttpHeadersWriter` |
| Writer tĩnh thường dùng | `StaticHeadersWriter` | `StaticServerHttpHeadersWriter` |
| Thêm writer | `headers(h -> h.addHeaderWriter(...))` | `headers(h -> h.addWriter(...))` |
| Chọn chain theo URL | `securityMatcher(...)` | `securityMatcher(ServerWebExchangeMatcher)` |
| HTTP test | `MockMvc` | `WebTestClient` |
| Cơ chế phân quyền | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |

**Điểm quan trọng:** DSL Servlet và Reactive không hoàn toàn đồng nhất. Thấy một method `crossOriginOpenerPolicy()` hay `permissionsPolicy()` trong một ví dụ không có nghĩa nó tồn tại ở **cả hai API**, ở **mọi phiên bản**, hay nhận cùng enum/kiểu cấu hình.

## 3. Hai chiến lược phát header: DSL chuyên dụng và writer tổng quát

### 3.1. DSL chuyên dụng: khi phiên bản hỗ trợ

Một số header có phương thức cấu hình riêng trong Spring Security. Ví dụ quen thuộc trên Servlet là:

```java
.headers(headers -> headers
    .frameOptions(frame -> frame.deny())
    .referrerPolicy(referrer -> referrer
        .policy(ReferrerPolicyHeaderWriter.ReferrerPolicy
            .STRICT_ORIGIN_WHEN_CROSS_ORIGIN)))
```

Đây là **đoạn trích bên trong `HttpSecurity`**, không phải lớp Java độc lập. Các import/package và chữ ký cần đối chiếu với phiên bản dự án. Ưu điểm của DSL chuyên dụng là API định danh rõ chính sách, có thể hỗ trợ enum, validator, điều kiện HTTPS và những giá trị bảo mật thường dùng.

Nhưng có giới hạn:

- Method hoặc enum có thể **không tồn tại** trên dependency đang dùng.
- Một DSL mới có thể đã được thêm ở nhánh phiên bản sau, hoặc chỉ xuất hiện ở Servlet/Reactive tại thời điểm nhất định.
- Chính sách của browser tiếp tục phát triển; cú pháp hỗ trợ trong thư viện có thể khác nhau giữa các bản.
- Một header có DSL riêng **không có nghĩa** header đó tự được bật mặc định.

### 3.2. Static writer: fallback rõ ràng cho header có giá trị cố định

Khi cần phát một response header với giá trị cố định, có thể thêm writer:

**Servlet:**

```java
.headers(headers -> headers
    .addHeaderWriter(new StaticHeadersWriter(
        "Cross-Origin-Opener-Policy", "same-origin")))
```

**Reactive:**

```java
.headers(headers -> headers
    .addWriter(new StaticServerHttpHeadersWriter(
        "Cross-Origin-Opener-Policy", "same-origin")))
```

Lợi ích:

1. Tên header/value phản ánh đúng giá trị browser cần nhận.
2. Giảm phụ thuộc vào việc một **DSL riêng cho header đó** đã có trong phiên bản chưa.
3. Dễ kiểm tra bằng HTTP test vì có giá trị mong đợi cụ thể.
4. Có thể sử dụng khi chỉ cần một **policy cố định** theo chain.

Giới hạn:

- Writer tĩnh **không hiểu ngữ nghĩa browser**; nhập sai `camera=(self)` hoặc sai origin, Java có thể vẫn phát đúng chuỗi sai đó.
- Không thay authentication/authorization, CSP, CORS hay quyền người dùng.
- Có nguy cơ tạo **header trùng** nếu cùng header được phát bởi writer khác hoặc proxy.
- Một số header **không nên được tự phát tĩnh theo kiểu đơn giản**, đặc biệt HSTS khi cần điều kiện HTTPS, hoặc CORS khi giá trị phụ thuộc origin/preflight.

**Không phải cứ có header mới là nên dùng static writer.** Chọn API chuyên dụng khi API thực sự có và phù hợp; dùng writer tĩnh có kiểm soát khi nó diễn đạt đúng chính sách và có test.

## 4. Ma trận chọn công cụ cho các security headers

| Header/cơ chế | Mục đích | Gợi ý API trong Spring Security | Điểm cần kiểm tra |
| --- | --- | --- | --- |
| `X-Content-Type-Options` | Giảm MIME sniffing trong trường hợp áp dụng | Default headers hoặc DSL phù hợp | Không tùy tiện tắt `nosniff` chỉ để sửa MIME sai ở CDN. |
| `X-Frame-Options` | Bảo vệ iframe với `DENY`/`SAMEORIGIN` | DSL `frameOptions` hoặc writer chuyên dụng | Phân biệt với CSP `frame-ancestors`, kiểm tra trên response bị nhúng. |
| `Strict-Transport-Security` | Yêu cầu HTTPS theo cơ chế HSTS | DSL HSTS/header writer chuyên dụng | **Chỉ cho response HTTPS** theo điều kiện áp dụng; cân nhắc includeSubDomains/preload. |
| Cache-control security headers | Tránh cache nhạy cảm theo mặc định bảo mật | Cấu hình mặc định hoặc DSL cache control | Chính sách cache response business có thể khác theo route. |
| `Content-Security-Policy` | Hạn chế nguồn script, ảnh, frame, kết nối... | DSL CSP/writer chuyên dụng hoặc tĩnh khi phù hợp | Browser diễn giải nhiều directive, report-only, nhiều policy đồng thời. |
| `Referrer-Policy` | Hạn chế thông tin URL nguồn gửi trong `Referer` | DSL `referrerPolicy` nếu có; fallback writer tĩnh | Kiểm tra cả same-origin và cross-origin, policy trên **trang nguồn**. |
| `Permissions-Policy` | Giới hạn API như camera/microphone/geolocation | DSL nếu phiên bản có; fallback writer tĩnh | Cú pháp allowlist, iframe `allow`, user permission, browser support. |
| `Cross-Origin-Opener-Policy` | Quan hệ top-level windows/opener | DSL/writer riêng nếu có; fallback writer tĩnh | `same-origin` có thể phá popup OAuth; kiểm tra policy cả hai cửa sổ. |
| `Cross-Origin-Embedder-Policy` | Điều kiện tài nguyên cross-origin | DSL/writer riêng nếu có; fallback writer tĩnh | `require-corp` có thể chặn CDN/iframe, `credentialless` thay credentials ở một số request. |
| `Cross-Origin-Resource-Policy` | Quyền dùng response tài nguyên trong `no-cors` | DSL/writer riêng nếu có; fallback writer tĩnh trên **resource** | `same-origin`/`same-site`/`cross-origin` theo tài nguyên public/private. |
| `X-Permitted-Cross-Domain-Policies` | Meta-policy của một số client Adobe legacy | Writer chuyên dụng nếu có; static writer tĩnh | Không thay CORS, không đồng nghĩa bảo vệ `clientaccesspolicy.xml` của Silverlight. |
| **CORS** | Cho request CORS từ origin được phép | CORS processor/configuration source qua `http.cors(...)` | **Không** chỉ đặt ACAO tĩnh; cần preflight, credentials, `Origin`, `Vary` và đúng route. |

**Ma trận này mô tả chiến lược**, không cam kết tên DSL chuyên dụng xuất hiện ở mọi bản Spring Security. Đối với `COOP`, `COEP`, `CORP` và `Permissions-Policy`, phương án kiểm soát được trên nhiều codebase là **writer tĩnh + test header**, sau khi xác minh API và các header mặc định của phiên bản đang chạy.

## 5. Những header nào có sẵn mặc định?

Spring Security thường cấu hình một tập response security headers mặc định khi phần headers được bật. Tập chính xác **phụ thuộc phiên bản, Servlet/Reactive và cấu hình thực tế**.

Những header phổ biến từng xuất hiện trong cấu hình mặc định gồm:

- `Cache-Control`, `Pragma`, `Expires` với mục đích hạn chế cache cho các response phù hợp.
- `X-Content-Type-Options: nosniff`.
- `X-Frame-Options`, thường `DENY` trong cấu hình mặc định hiện đại.
- `Strict-Transport-Security` trong **điều kiện response HTTPS** của HSTS writer khi được bật.
- `X-XSS-Protection` trong một số dòng phiên bản, với giá trị mặc định đã thay đổi theo thời gian; cơ chế XSS filter cũ của browser không phải biện pháp phòng XSS đáng tin hiện nay.

Trong khi đó, **không nên giả định** Spring Security tự cấu hình một chính sách phù hợp cho ứng dụng đối với:

```http
Content-Security-Policy
Referrer-Policy
Permissions-Policy
Cross-Origin-Opener-Policy
Cross-Origin-Embedder-Policy
Cross-Origin-Resource-Policy
```

Các header này cần **lựa chọn giá trị theo nghiệp vụ**. Ví dụ `Cross-Origin-Embedder-Policy: require-corp` sẽ ảnh hưởng tới resource graph của toàn tài liệu; một default không có ngữ cảnh ứng dụng có thể gây hỏng chức năng.

### Đừng “khôi phục” header đã lỗi thời chỉ để làm đẹp điểm chấm

`X-XSS-Protection` là một ví dụ về header lịch sử: các browser hiện đại không dựa vào bộ lọc này như biện pháp chống XSS. Thay vì đặt những giá trị legacy một cách máy móc, hãy duy trì **output encoding**, CSP phù hợp, kiểm tra input, review dependency và các lớp kiểm soát hiện hành. Khi công cụ audit phàn nàn, phải xem **browser mục tiêu và khuyến nghị hiện hành**, không lấy một checklist cũ làm chân lý tuyệt đối.

### HSTS có ngoại lệ quan trọng

**Không phát `Strict-Transport-Security` bừa bãi trên HTTP.** Header HSTS chỉ có ý nghĩa khi được browser chấp nhận từ kết nối HTTPS hợp lệ. Writer HSTS chuyên dụng thường xử lý điều kiện này. Nếu dùng writer tĩnh cho HSTS mà không tính đến kết nối/proxy, có thể tạo header vô nghĩa hoặc gây hiểu nhầm trong test. Cấu hình `includeSubDomains`/`preload` còn ảnh hưởng cả hạ tầng và cần đánh giá trước.

## 6. Khác biệt hỗ trợ theo phiên bản: ba lớp phải kiểm tra

Khi một ví dụ từ tài liệu không biên dịch, cần phân biệt **ba loại khác biệt**:

1. **Phiên bản Spring Security:** method, enum, writer, package hoặc cách cấu hình thay đổi.
2. **Loại ứng dụng:** Servlet và Reactive có builder và writer khác nhau.
3. **Phiên bản browser:** một header dù được Spring phát đúng vẫn có thể không được browser hỗ trợ đầy đủ.

### 6.1. Các dòng Spring Security cần lưu ý

| Dòng phiên bản | Lưu ý thực hành |
| --- | --- |
| **Spring Security 5.x** | Nhiều ứng dụng Servlet cũ có `WebSecurityConfigurerAdapter`; phong cách DSL không nhất thiết giống cấu hình component-based. Một số DSL/header mới chưa có hoặc khác chữ ký. |
| **Spring Security 5.7/5.8** | Giai đoạn chuyển dần sang cấu hình bean `SecurityFilterChain`; `WebSecurityConfigurerAdapter` đã bị deprecate trong 5.7. Cần chuẩn bị migration. |
| **Spring Security 6.x** | `WebSecurityConfigurerAdapter` đã bị loại bỏ; thường dùng `SecurityFilterChain`/`SecurityWebFilterChain` và lambda DSL. Các mã Servlet tùy biến dùng `jakarta.servlet` thay `javax.servlet` trong hệ sinh thái tương ứng. |
| **Các dòng mới hơn (ví dụ 7.x nếu dự án đã dùng)** | Phải đọc tài liệu/Javadoc **đúng version** về DSL, các API deprecate/removed và default headers; không giả định code từ 5.x/6.x luôn hợp lệ. |

**Bảng trên không định nghĩa mốc xuất hiện của từng writer cụ thể.** Việc Spring Security hỗ trợ `HeaderWriter` hay một header riêng không chứng minh rằng **DSL cho tất cả giá trị mới** đã có từ cùng một version; cũng không nên đoán một API có sẵn chỉ từ số phiên bản major.

### 6.2. Quy trình xác nhận phiên bản thật

Trước khi chọn mã, xác minh:

- Version **Spring Security** được dependency management thực tế resolve, không chỉ `spring-boot-starter-security` khai báo gián tiếp.
- Ứng dụng đang chạy **Servlet** (Spring MVC) hay **Reactive/WebFlux**.
- Trong IDE/Javadoc của **đúng version**, builder `HeadersConfigurer` hoặc `ServerHttpSecurity.HeaderSpec` có method nào.
- Writer được import từ package nào, enum/constructor nào còn được hỗ trợ.
- Có cấu hình proxy/nginx/gateway hoặc filter riêng ghi cùng header không.

Ví dụ các cách kiểm tra dependency trong dự án bình thường (đây là **lệnh để người học tham khảo**, không phải thao tác của bài biên soạn):

```bash
# Với Maven, tùy cấu trúc pom.xml:
./mvnw dependency:tree -Dincludes=org.springframework.security

# Với Gradle:
./gradlew dependencyInsight \
  --dependency spring-security-web \
  --configuration runtimeClasspath
```

Nếu project dùng `spring-security-webflux`, `spring-security-config` hoặc starter khác, chọn đúng module và configuration. **Không đọc/version-check bằng cách đoán từ một đoạn code lấy trên mạng.**

### 6.3. Cách chọn API an toàn trước khi nâng cấp

```text
Xác nhận runtime Spring Security + Servlet/WebFlux
           │
           ▼
Header cần viết đã có DSL phù hợp?
      ├── Có  → dùng DSL chuyên dụng khi đáp ứng yêu cầu
      │          kiểm thử giá trị và điều kiện phát
      └── Chưa / khác API
               → dùng static writer nếu policy là chuỗi cố định
                  không có điều kiện động phức tạp
           │
           ▼
Kiểm tra có writer/default/proxy khác cùng tên?
           │
           ▼
Chọn chain đúng → test response → test browser thật
```

## 7. Servlet: cấu hình một chain với nhóm header rõ ràng

Ví dụ Servlet dưới đây chọn một chính sách thận trọng cho **trang thông thường**: giữ default security headers và bổ sung ba header mà ứng dụng chủ động chọn. COEP `require-corp` **chưa áp toàn website**.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.StaticHeadersWriter;

@Configuration
@EnableWebSecurity
public class HttpHeaderSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .headers(headers -> headers
                .addHeaderWriter(new StaticHeadersWriter(
                    "Referrer-Policy",
                    "strict-origin-when-cross-origin"))
                .addHeaderWriter(new StaticHeadersWriter(
                    "Permissions-Policy",
                    "camera=(), microphone=(), geolocation=()"))
                .addHeaderWriter(new StaticHeadersWriter(
                    "Cross-Origin-Opener-Policy",
                    "same-origin")))
            .build();
    }
}
```

Response HTML kỳ vọng, nếu request đi qua chain:

```http
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Cross-Origin-Opener-Policy: same-origin
```

Những header mặc định khác vẫn được Spring Security xử lý theo phiên bản/cấu hình, **không bị tắt**.

**Chú ý:**

- `authenticated()` chỉ minh họa authorization. Ứng dụng thật phải có login/role/tenant và CSRF/session tương ứng.
- `Permissions-Policy: camera=()` có thể chặn tính năng lớp học video; cần ngoại lệ theo trang nếu sản phẩm có use case thật.
- `COOP: same-origin` có thể cắt opener của OAuth popup; không đặt toàn site nếu chưa kiểm kê luồng popup.
- Các static writers phát header **cố định cho response trong chain**; chúng không tự đánh giá origin của request hay tự xử lý browser compatibility.

### Khi dự án hỗ trợ DSL referrerPolicy

Nếu version đã có DSL phù hợp, có thể thay writer tĩnh `Referrer-Policy` bằng:

```java
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;

// Bên trong .headers(headers -> ...)
.referrerPolicy(referrer -> referrer
    .policy(ReferrerPolicyHeaderWriter.ReferrerPolicy
        .STRICT_ORIGIN_WHEN_CROSS_ORIGIN))
```

**Chỉ chọn một cách phát cho mỗi header.** Không giữ writer tĩnh `Referrer-Policy` đồng thời với DSL riêng trừ khi đã xác minh chắc chắn sự phối hợp được chủ đích và không tạo response mâu thuẫn.

## 8. Reactive/WebFlux: dùng đúng ServerHttpHeadersWriter

Với WebFlux, lớp dùng ở Servlet **không được truyền trực tiếp** vào `ServerHttpSecurity`. Ví dụ tương ứng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.header.StaticServerHttpHeadersWriter;

@Configuration
@EnableWebFluxSecurity
public class ReactiveHeaderSecurityConfig {

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated())
            .headers(headers -> headers
                .addWriter(new StaticServerHttpHeadersWriter(
                    "Referrer-Policy",
                    "strict-origin-when-cross-origin"))
                .addWriter(new StaticServerHttpHeadersWriter(
                    "Permissions-Policy",
                    "camera=(), microphone=(), geolocation=()"))
                .addWriter(new StaticServerHttpHeadersWriter(
                    "Cross-Origin-Opener-Policy",
                    "same-origin")))
            .build();
    }
}
```

Về mặt HTTP/browser, giá trị các header là như nhau cho Servlet và Reactive. Khác biệt thực sự là:

1. Reactive builder `ServerHttpSecurity` thay cho `HttpSecurity`.
2. Reactive `StaticServerHttpHeadersWriter` thay cho Servlet `StaticHeadersWriter`.
3. Reactive chain và matcher hoạt động trên `ServerWebExchange`.
4. Test Reactve bằng `WebTestClient`; test Servlet thường dùng `MockMvc`.

**Không copy những import `javax.servlet` hoặc `jakarta.servlet` vào ví dụ Reactive.** Một lớp custom writer Servlet không đột nhiên trở thành Reactive chỉ vì được gọi từ WebFlux.

## 9. Cấu hình theo route: chính sách của tài liệu và resource không giống nhau

Một lỗi thiết kế nguy hiểm là gắn **COEP `require-corp`** hoặc **CORP `cross-origin`** lên mọi response, kể cả nơi không cần thiết. Hãy đặt chính sách theo chức năng:

| Route | Loại response | Header theo ví dụ |
| --- | --- | --- |
| `/isolated/**` | HTML cần cross-origin isolation | `COOP: same-origin`, `COEP: require-corp`. |
| `/auth/popup-launcher` | HTML mở popup OAuth đã kiểm chứng | `COOP: same-origin-allow-popups`. |
| `/assets/public/**` | Ảnh/script thật sự public | `CORP: cross-origin` trên resource. |
| `/assets/private/**` | Ảnh/file theo user | `CORP: same-origin` + quyền server + cache riêng. |
| `/account/**` | HTML tài khoản | `COOP: same-origin`, `Referrer-Policy` phù hợp. |
| Các route khác | HTML/API bình thường | Chỉ phát những header có yêu cầu rõ, giữ default security headers. |

### 9.1. Servlet: ba chain thể hiện sự khác biệt

Ví dụ tập trung vào route cô lập, popup và fallback. Đây là **phương án thay thế** cho cấu hình một chain ở mục 7, không đăng ký đồng thời các bean trùng vai trò.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.StaticHeadersWriter;

@Configuration
public class ScopedServletHeadersConfig {

    @Bean
    @Order(1)
    SecurityFilterChain isolated(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/isolated/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .headers(headers -> headers
                .addHeaderWriter(new StaticHeadersWriter(
                    "Cross-Origin-Opener-Policy", "same-origin"))
                .addHeaderWriter(new StaticHeadersWriter(
                    "Cross-Origin-Embedder-Policy", "require-corp")))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain popup(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/auth/popup-launcher")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll())
            .headers(headers -> headers
                .addHeaderWriter(new StaticHeadersWriter(
                    "Cross-Origin-Opener-Policy",
                    "same-origin-allow-popups")))
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain others(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .headers(headers -> headers
                .addHeaderWriter(new StaticHeadersWriter(
                    "Referrer-Policy",
                    "strict-origin-when-cross-origin")))
            .build();
    }
}
```

**Quan trọng:** `securityMatcher(...)` quyết định chain xử lý request và **header writer nào chạy**; `requestMatchers(...)` trong `authorizeHttpRequests` chỉ điều khiển quyền truy cập. Chain `@Order(1)` phải được xét trước chain fallback, nếu không policy cô lập có thể không được áp dụng.

Trong ví dụ, `/isolated/**` và `/auth/popup-launcher` **không tự có `Referrer-Policy` của chain `others`**. Nếu một baseline chung phải áp trên mọi route, hãy khai báo cùng baseline trong từng chain liên quan hoặc cấu hình phù hợp ở tầng chung, rồi kiểm tra không bị ghi đè. **Đừng suy rằng các chain tự “kế thừa” headers của nhau.**

### 9.2. Reactive: phạm vi route tương đương

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.header.StaticServerHttpHeadersWriter;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class ScopedReactiveHeadersConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain isolated(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/isolated/**"))
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated())
            .headers(headers -> headers
                .addWriter(new StaticServerHttpHeadersWriter(
                    "Cross-Origin-Opener-Policy", "same-origin"))
                .addWriter(new StaticServerHttpHeadersWriter(
                    "Cross-Origin-Embedder-Policy", "require-corp")))
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain popup(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/auth/popup-launcher"))
            .authorizeExchange(auth -> auth
                .anyExchange().permitAll())
            .headers(headers -> headers
                .addWriter(new StaticServerHttpHeadersWriter(
                    "Cross-Origin-Opener-Policy",
                    "same-origin-allow-popups")))
            .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain others(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated())
            .headers(headers -> headers
                .addWriter(new StaticServerHttpHeadersWriter(
                    "Referrer-Policy",
                    "strict-origin-when-cross-origin")))
            .build();
    }
}
```

Ứng dụng Reactive phải tích hợp chain với các filter xác thực/OAuth của dự án. **Không thể xem đoạn demo này là cấu hình OAuth2 login hoàn chỉnh**: callback và authorization endpoints cần được xử lý bởi security infrastructure đúng. Khi có `/admin/**`, `/assets/**` hay endpoint khác, cân nhắc thêm matcher và security rules cụ thể.

## 10. Khi một header không nên được viết bằng StaticHeadersWriter

Không phải response header nào cũng phù hợp với một giá trị cố định toàn site.

### 10.1. CORS: giá trị phụ thuộc Origin và preflight

Sai lầm thường gặp:

```java
// Không coi đây là cấu hình CORS hoàn chỉnh.
.addHeaderWriter(new StaticHeadersWriter(
    "Access-Control-Allow-Origin", "*"))
```

Một response ACAO tĩnh:

- Không xác định rõ những method/header được phép cho **preflight**.
- Không xử lý đúng credentialed requests.
- Có thể vô tình mở dữ liệu nếu API và quyền server được thiết kế sai.
- Không thay thế `CorsFilter`/CORS processor khi cần đọc `Origin` và trả lời OPTIONS.
- Không có cơ chế phân biệt cache theo `Origin` khi phản hồi biến thiên.

Trong Spring Security Servlet, hãy dùng `http.cors(...)` với cấu hình CORS phù hợp; trong Reactive, dùng `ServerHttpSecurity.cors(...)`/reactive CORS infrastructure theo phiên bản. CORS phải được tích hợp sao cho **preflight không bị chặn sai bởi authentication/CSRF**.

Ví dụ ý định chính sách CORS:

```http
Access-Control-Allow-Origin: https://dashboard.partner.example
Vary: Origin
```

Nếu dùng credentials, cần cấu hình `Access-Control-Allow-Credentials` và origin allowlist phù hợp; không kết hợp `Access-Control-Allow-Origin: *` với credentialed CORS request.

### 10.2. HSTS: chỉ phát khi đúng điều kiện

HSTS được browser xử lý trong ngữ cảnh HTTPS hợp lệ. Nếu reverse proxy chấm dứt TLS còn application thấy HTTP nội bộ, việc tự gắn HSTS tĩnh có thể che giấu lỗi cấu hình. Ưu tiên DSL/writer HSTS có kiểm soát, cấu hình trusted proxy và kiểm thử response HTTPS thực; phải có quyết định rõ về `includeSubDomains`, `max-age` và preload.

### 10.3. Header phụ thuộc người dùng hoặc host

Không lấy `Host`, `Origin`, `Referer` hoặc query parameter chưa được xác minh để ghép thẳng vào `Permissions-Policy`, CSP `frame-ancestors` hay ACAO. Một policy tạo động cần **danh sách origin tin cậy có kiểm soát**, nguồn cấu hình được phê duyệt, escaping/validation phù hợp và test.

Nếu chỉ có một số origin đối tác cố định, **khai báo theo chain/route** thường dễ kiểm soát hơn một writer tự động phản chiếu bất kỳ origin nào được yêu cầu.

## 11. Header trùng: nguyên nhân và cách xử lý

Một ứng dụng có thể phát cùng header tại nhiều tầng:

```text
Spring Security HeadersConfigurer
    ↓
Custom HeaderWriter
    ↓
Servlet Filter / WebFilter
    ↓
Reverse proxy / Ingress
    ↓
CDN / WAF
    ↓
Browser
```

Ví dụ không mong muốn:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Opener-Policy: same-origin-allow-popups
```

Không nên giả định browser sẽ chọn “mức bảo vệ mạnh nhất” hoặc “giá trị cuối cùng” theo cách thuận tiện. **Quy tắc cú pháp và xử lý header trùng có thể khác giữa các header và phiên bản browser**; phát trùng còn làm khó audit và chẩn đoán.

Các nguyên nhân thường gặp:

1. Dùng **DSL riêng và static writer** cho cùng tên header.
2. App viết header, proxy lại thêm hoặc thay giá trị khác.
3. Hai component nội bộ cùng cấu hình header mà không có owner.
4. Một response được tạo ngoài Spring Security chain, nên header chỉ xuất hiện ở vài route.
5. CDN cache response cũ với header khác cấu hình mới.

### Quy trình gỡ lỗi

- Xác định **response nào** chứa duplicate (HTML, PNG, redirect, error page).
- Dùng DevTools hoặc HTTP client quan sát **các header thực sự nhận**, không chỉ test code.
- Kiểm tra tầng phát dự kiến (Spring Security writer/DSL; reverse proxy/CDN).
- Chọn **một owner cho mỗi header theo route** và xóa cấu hình chồng chéo.
- Kiểm thử lại với cache/redirect và các status có liên quan.

**Đừng tắt toàn bộ phần headers** để loại một header trùng:

```java
// Tránh chữa lỗi bằng cách làm mất mọi lớp bảo vệ mặc định.
http.headers(headers -> headers.disable());
```

Thay vào đó, sửa **writer/header cụ thể** hoặc điểm phát ở proxy.

## 12. Spring Security default header và vấn đề thứ tự chain

Một ứng dụng có nhiều chain có thể cho kết quả:

| Request | Chain thực tế | Header được thêm |
| --- | --- | --- |
| `GET /isolated/simulator` | `isolated` | COOP `same-origin` + COEP `require-corp`. |
| `GET /auth/popup-launcher` | `popup` | COOP `same-origin-allow-popups`. |
| `GET /account/security` | `others` | `Referrer-Policy` trong ví dụ fallback. |
| `GET /assets/logo.png` | `others` nếu không có chain asset riêng | Không tự có `CORP: cross-origin` chỉ vì file được gọi là asset. |

**Quan trọng:** mỗi request thường được xử lý bởi **chain khớp đầu tiên**, không phải “gộp header từ mọi chain có khả năng khớp”. Những header baseline cần dùng mọi nơi phải được cấu hình theo thiết kế chung thật sự và được kiểm thử trên từng chain.

Một dấu hiệu lỗi matcher: endpoint `/isolated/simulator` chỉ nhận `Referrer-Policy` từ fallback, không có COEP. Trước khi sửa writer, hãy xác minh `securityMatcher` và `@Order`, route rewrite ở gateway và đường dẫn Spring thực sự nhìn thấy.

Với **Reactive**, `securityMatcher` nhận matcher dành cho `ServerWebExchange`; không copy nguyên API `HttpSecurity.securityMatcher(String...)` từ Servlet sang WebFlux.

### Static assets nằm ngoài security chain

Nếu `https://cdn.example.com/logo.png` được Nginx hoặc CDN trả trực tiếp, Spring không xử lý request đó. **CORP phải nằm trên response ảnh tại CDN**. Test MockMvc ở ứng dụng HTML không thể xác nhận CORP tại server tài nguyên ngoài.

## 13. Kiểm thử HTTP phía Servlet bằng MockMvc

Kiểm thử HTTP xác minh **server có phát giá trị header đúng trên response không**. Nó không mô phỏng cách browser xử lý popup, camera hoặc resource `no-cors`.

Giả sử các route tồn tại trong fixture và user `viewer` có quyền:

```java
mockMvc.perform(get("/isolated/simulator").with(user("viewer")))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Cross-Origin-Opener-Policy", "same-origin"))
    .andExpect(header().string(
        "Cross-Origin-Embedder-Policy", "require-corp"));

mockMvc.perform(get("/auth/popup-launcher"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Cross-Origin-Opener-Policy",
        "same-origin-allow-popups"))
    .andExpect(header().doesNotExist(
        "Cross-Origin-Embedder-Policy"));

mockMvc.perform(get("/account/security").with(user("viewer")))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Referrer-Policy",
        "strict-origin-when-cross-origin"));
```

Đây là **phần thân test minh họa**; cần `MockMvc`, controller/handler fixture, `spring-security-test`, static imports `get`, `user`, `status`, `header`. Nếu controller chuyển hướng login hoặc trả `404`, điều chỉnh test cho đúng response bạn muốn kiểm tra. Test `doesNotExist` chỉ đúng khi không có proxy/other writer nào thêm COEP trong môi trường đang chạy test.

### Kiểm tra header không bị trùng

Với `MockMvc`, có thể kiểm tra số giá trị của một header trong response:

```java
MvcResult result = mockMvc.perform(
        get("/isolated/simulator").with(user("viewer")))
    .andReturn();

List<String> values = result.getResponse().getHeaders(
    "Cross-Origin-Opener-Policy");

assertThat(values).containsExactly("same-origin");
```

Đoạn minh họa cần import `MvcResult`, `List` và assertion library (ví dụ AssertJ). Nếu một proxy thêm header **sau** ứng dụng, test `MockMvc` sẽ không thấy thay đổi đó; cần kiểm tra response cuối ở staging.

### Header mặc định vẫn còn?

Nếu chính sách yêu cầu `X-Content-Type-Options: nosniff`, thêm regression assertion:

```java
mockMvc.perform(get("/account/security").with(user("viewer")))
    .andExpect(header().string(
        "X-Content-Type-Options", "nosniff"));
```

Đối với HSTS, chỉ assert khi kiểm thử response HTTPS đúng; không dùng request HTTP thường rồi kết luận HSTS writer bị lỗi.

## 14. Kiểm thử Reactive bằng WebTestClient

Ví dụ tương ứng cho `SecurityWebFilterChain`:

```java
webTestClient.mutateWith(mockUser("viewer"))
    .get().uri("/isolated/simulator")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueEquals(
        "Cross-Origin-Opener-Policy", "same-origin")
    .expectHeader().valueEquals(
        "Cross-Origin-Embedder-Policy", "require-corp");

webTestClient.get().uri("/auth/popup-launcher")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueEquals(
        "Cross-Origin-Opener-Policy",
        "same-origin-allow-popups")
    .expectHeader().doesNotExist(
        "Cross-Origin-Embedder-Policy");

webTestClient.mutateWith(mockUser("viewer"))
    .get().uri("/account/security")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueEquals(
        "Referrer-Policy",
        "strict-origin-when-cross-origin");
```

`mockUser` có thể import từ `SecurityMockServerConfigurers` trong `spring-security-test`. Kiểm tra **cả giá trị và phạm vi**: route `/isolated/**` không được vô tình nhận COOP dành cho OAuth launcher, còn trang launcher không được tự nhận COEP `require-corp` nếu ứng dụng chưa có nhu cầu.

### Test header chưa đủ để chứng minh browser hỗ trợ

`WebTestClient` và `MockMvc` có thể PASS khi browser mục tiêu:

- Không hỗ trợ một directive `Permissions-Policy` nhất định.
- Đã cắt `window.opener` dù ứng dụng mong popup callback.
- Chặn ảnh CDN thiếu CORP dưới `COEP: require-corp`.
- Không chấp nhận response CORS vì credential hoặc preflight.

Do đó phải kết hợp **HTTP test** với **browser integration test** cho những chính sách tác động hành vi.

## 15. Browser test: xác nhận hiệu lực chứ không chỉ chuỗi header

### 15.1. COOP và popup OAuth

Trên một môi trường test do bạn quản lý:

- Opener `http://localhost:8080/auth/popup-launcher`.
- Popup `http://localhost:9090/popup.html`.

Hai URL khác origin vì port, dù có thể cùng site. Thử response opener:

```http
Cross-Origin-Opener-Policy: same-origin
```

và:

```http
Cross-Origin-Opener-Policy: same-origin-allow-popups
```

Khi popup phía 9090 dùng `unsafe-none`/không có COOP, browser hiện đại có thể **cắt opener** ở trường hợp đầu và **giữ opener** trong trường hợp sau. Mở popup bằng click thật, kiểm tra `window.opener` trong popup và `window.closed`/`WindowProxy.closed` ở opener.

**Không xem popup không mở là bằng chứng của COOP**: browser có popup blocker, lỗi DNS, redirect hoặc CSP riêng.

### 15.2. COEP + CORP: resource `no-cors`

Trang A ở `http://localhost:8080/isolated/demo` gửi:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

và tải ảnh:

```html
<img
  id="publicImage"
  src="http://localhost:9090/public/logo.png"
  alt="Logo">
```

Với tài nguyên ảnh PNG công khai hợp lệ ở origin 9090:

| Header resource 9090 | Kỳ vọng trong browser có COEP `require-corp` |
| --- | --- |
| Không CORP/CORS | Ảnh `no-cors` có thể bị chặn. |
| `Cross-Origin-Resource-Policy: cross-origin` | Có thể hiển thị, nếu CSP/MIME và điều kiện khác cho phép. |
| Chỉ `Access-Control-Allow-Origin` nhưng ảnh vẫn `no-cors` | Không đủ thay CORP cho `no-cors`. |

Với `<img crossorigin="anonymous">`, request chuyển sang `cors` và cần CORS hợp lệ; `CORP: cross-origin` đơn lẻ không cấp quyền CORS.

### 15.3. Permissions-Policy cho camera và microphone

Tại trang không cần thiết bị:

```http
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

Với browser hỗ trợ, có thể kiểm tra:

```javascript
const policy = document.permissionsPolicy ?? document.featurePolicy;
if (policy && typeof policy.allowsFeature === "function") {
  console.log("camera:", policy.allowsFeature("camera"));
  console.log("microphone:", policy.allowsFeature("microphone"));
}
```

Một API introspection trả `true` chỉ cho biết **policy không chặn** tính năng ở ngữ cảnh đó, **không** chứng minh người dùng đã cấp quyền. Với iframe họp, còn cần `allow="camera; microphone"`, header của cha, policy kế thừa, HTTPS/secure context, thiết bị và consent.

### 15.4. Mục tiêu cross-origin isolation

```javascript
console.table({
  secureContext: window.isSecureContext,
  isolated: window.crossOriginIsolated
});
```

`crossOriginIsolated` bằng `true` là tín hiệu phù hợp cho những API yêu cầu isolation, nhưng không chỉ dựa vào hai response headers để bảo đảm nó: còn có browser support, ngữ cảnh frame/ancestor và những điều kiện liên quan. Một trang có COOP tốt nhưng không có COEP phù hợp vẫn có thể `false`.

## 16. Những sai lầm khi di trú từ codebase cũ

### “Ở Spring Security 5.x code hoạt động, sang 6.x class không còn”

Kiểm tra code có dùng `WebSecurityConfigurerAdapter` không; API này bị deprecate ở 5.7 và loại bỏ trong 6.0. Thiết kế component-based với `SecurityFilterChain` là hướng đi tiêu chuẩn cho Servlet; Reactive sử dụng `SecurityWebFilterChain`.

Nếu có custom Servlet filter/writer, rà soát thay đổi `javax.servlet` → `jakarta.servlet` trong hệ sinh thái Spring Framework/Security tương ứng. Không chỉ sửa import mà quên dependency management, test và container.

### “Đã copy headers DSL từ Servlet sang WebFlux nhưng build lỗi”

Builder Reactive khác Servlet; dùng `ServerHttpSecurity`, `ServerHttpHeadersWriter` và `SecurityWebFilterChain`. Một DSL hoặc enum có cùng tên chính sách **không được đảm bảo** có trong cả hai. Chọn writer tĩnh Reactve khi policy cố định và API phù hợp.

### “Header writer chạy đúng nhưng tài nguyên iframe vẫn hỏng”

Xác định **header thuộc response nào**. COEP trên trang cha khác CORP trên resource; CSP `frame-ancestors`/XFO nằm ở response iframe; Permissions-Policy có thể đòi điều kiện trên cả cha và iframe `allow`. Đừng thêm CORP của ảnh vào HTML rồi mong iframe/ảnh tự được phép.

### “Đã thêm Permissions-Policy mà camera vẫn mở trên browser cũ”

Không phải mọi browser/version đều hỗ trợ mọi directive. Writer của Spring chỉ gửi một chuỗi HTTP; nó không thể buộc client chưa hỗ trợ thực thi policy. Cần xác định tập browser hỗ trợ, kiểm thử và biện pháp bổ sung về quyền/cách sử dụng thiết bị.

### “Tăng version Spring thì tự có CSP, COEP chặt hơn”

Không nên giả định. Mặc định security headers có thể thay đổi theo version, nhưng **giá trị CSP/COEP cụ thể** thường phải được chọn theo ứng dụng. Hãy ghi **header baseline mong đợi** thành test; so sánh trước/sau upgrade và thay đổi có kiểm soát.

### “Security chain chỉ permitAll nên không chạy HeaderWriter”

`permitAll()` không đồng nghĩa security chain biến mất; các filters và header writers vẫn có thể chạy cho response thuộc chain. Ngược lại, request không đi qua Spring Security (CDN/static proxy) không nhận writer của Spring. Hãy kiểm tra **chain matching và đường request thực tế**, không suy luận từ `permitAll`.

### “COEP bị gỡ trong Java nhưng production vẫn có require-corp”

Gateway/CDN có thể phát header sau Spring, hoặc response được cache. Test bằng DevTools/HTTP response qua hostname cuối, kiểm tra tầng phát và invalidation cache trước khi quy nguyên nhân cho writer.

## 17. Quy trình nâng cấp có kiểm chứng

Khi chuyển từ một phiên bản Spring Security sang phiên bản khác, nên dùng quy trình lặp lại được:

1. **Chốt baseline:** liệt kê các route tài liệu/asset/API và response headers thực tế trước khi nâng cấp, gồm cả lỗi/redirect.
2. **Xác nhận dependency:** ghi rõ Spring Boot, Spring Security, Servlet/Reactive, Java và thư viện liên quan thực sự được resolve.
3. **Phân loại writer:** default headers; DSL chuyên dụng; static writer; custom/proxy writer.
4. **Đối chiếu API/Javadoc:** xác minh signature, enum, method deprecate, sự khác nhau giữa Servlet và Reactive.
5. **Không thay policy cùng lúc với đổi API:** trước tiên giữ **cùng giá trị header** trên các route; thay đổi chính sách bảo mật như COEP `credentialless` ở một đợt riêng để dễ chẩn đoán.
6. **Chạy HTTP tests:** đảm bảo status, tên/value header, không trùng, route đúng và bảo vệ default còn nguyên.
7. **Chạy browser regression:** COOP popup, COEP/CORP CDN, CORS API, Permissions-Policy iframe, `Referrer-Policy` điều hướng.
8. **Xác minh sau proxy/CDN:** đặc biệt HSTS HTTPS, redirects, cache, CSP, COEP/CORP và header chồng.
9. **Theo dõi và rollback hẹp:** nếu một SDK hỏng, điều chỉnh policy ở đúng route/asset hoặc đưa ra ngoại lệ có thời hạn; không tắt toàn bộ security headers.

### Ma trận kiểm thử bảo vệ tối thiểu

| Trường hợp | Kiểm thử Spring | Kiểm thử browser/hạ tầng |
| --- | --- | --- |
| Tài liệu cần isolation | COOP `same-origin`, COEP `require-corp` | `crossOriginIsolated`, asset graph, browser mục tiêu. |
| Trang mở OAuth popup | COOP `same-origin-allow-popups` khi có nhu cầu | Popup/callback/redirect và `window.opener`, `state`/PKCE. |
| Ảnh/script public | CORP `cross-origin` trên response resource nếu cần | Ảnh `no-cors` và `cors`, CSP, MIME, CDN. |
| Ảnh private | CORP `same-origin`, auth/authorization | Không hiển thị trái phép trong ngữ cảnh cross-origin; không rò qua cache. |
| Trang bình thường | Referrer/Permissions Policy theo thiết kế | `Referer`, `getUserMedia` trong browser hỗ trợ. |
| CORS API | ACAO/preflight đúng origin, credential hợp lệ | `fetch` được đọc theo đúng origin/permission. |
| Header mặc định | `nosniff`, XFO/HSTS theo yêu cầu | HTTPS production và response cuối qua proxy. |

## 18. Bài tập vận dụng

**Bài A — Chọn writer.** Một ứng dụng Spring Security Servlet cần phát `Permissions-Policy: camera=(), microphone=()`, nhưng version hiện tại không có DSL `permissionsPolicy`. Hãy đề xuất cách cấu hình không cần nâng cấp ngay và nêu hai điều phải kiểm tra.

**Bài B — Servlet sang Reactive.** Một developer copy `StaticHeadersWriter` và `HttpSecurity.headers(...addHeaderWriter(...))` sang WebFlux. Nêu các lớp/API cần thay, và vì sao không chỉ sửa tên `HttpSecurity` thành `ServerHttpSecurity`.

**Bài C — Header trùng.** Response production có hai dòng `Cross-Origin-Opener-Policy`: `same-origin` và `same-origin-allow-popups`. MockMvc chỉ thấy `same-origin`. Hãy chỉ ra các tầng cần kiểm tra và cách thiết kế một owner cho chính sách.

**Bài D — HSTS.** Nhóm phát triển muốn dùng `StaticHeadersWriter("Strict-Transport-Security", "...")` trên mọi HTTP/HTTPS response. Vì sao phương án này cần cân nhắc? Hãy mô tả điều kiện và cách test phù hợp.

**Bài E — COEP và CDN.** Trang HTML gửi `COEP: require-corp`, nhưng ảnh CDN cross-origin `no-cors` thiếu `Cross-Origin-Resource-Policy`. Thêm `CORP: cross-origin` vào response HTML có giúp không? Nên thêm ở đâu, hoặc chọn cách tải nào khác?

**Bài F — Mặc định và migration.** Một dự án nâng từ Spring Security 5.x lên 6.x, chuyển sang `SecurityFilterChain`. Cần viết các test nào để chứng minh header default, header tự chọn và bảo vệ route không thay đổi ngoài ý muốn?

**Bài G — CORS.** Một nhóm dùng static writer `Access-Control-Allow-Origin: *` để sửa API cần cookies. Giải thích vì sao không phải giải pháp hợp lệ cho credentialed CORS và mô tả cấu hình phù hợp.

**Bài H — Route.** Policy `COOP: same-origin-allow-popups` chỉ cần trên `/auth/popup-launcher`; trang `/isolated/**` cần `same-origin` + `require-corp`. Hãy thiết kế các chain theo `@Order`, và viết một assertion chứng minh launcher **không nhận COEP** ngoài ý muốn.

### Gợi ý đáp án

- **A:** dùng Servlet `StaticHeadersWriter` trong `headers(...addHeaderWriter(...))`, test header và browser hỗ trợ; tránh writer trùng.
- **B:** dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, `StaticServerHttpHeadersWriter`, `addWriter` và matcher Reactive.
- **C:** kiểm tra writer/DSL Java, filter/web filter, proxy/ingress/CDN và cache; chọn một nguồn phát header.
- **D:** HSTS dành cho HTTPS hợp lệ; cân nhắc TTL/subdomains/preload, reverse proxy và test HTTPS thực.
- **E:** CORP phải nằm trên **response ảnh CDN**; có thể chuyển ảnh sang `cors` với `crossorigin` và ACAO hợp lệ nếu phù hợp.
- **F:** test header mặc định, header mới, route cụ thể, duplicate, HSTS HTTPS, auth/CSRF và browser flows.
- **G:** với credentials cần origin cụ thể được cho phép và `Access-Control-Allow-Credentials: true` khi nghiệp vụ yêu cầu, dùng CORS infrastructure, giữ authorization/CSRF/cookie.
- **H:** route `/isolated/**` trước launcher rồi fallback; MockMvc/WebTestClient assert `Cross-Origin-Embedder-Policy` không tồn tại tại launcher trong môi trường chỉ có app writer.

## 19. Checklist trước khi merge

Đối với mỗi header quan trọng:

1. **Đúng tên và giá trị HTTP?** Cú pháp `Permissions-Policy` khác CSP; `CORP` có `same-origin`/`same-site`/`cross-origin`, không có `none`.
2. **Đúng response?** COOP/COEP thường thuộc tài liệu; CORP thuộc resource; CORS thuộc endpoint/resource đích.
3. **Đúng framework?** `HeaderWriter`/`HttpSecurity` cho Servlet; `ServerHttpHeadersWriter`/`ServerHttpSecurity` cho Reactive.
4. **Đúng version?** Method/enum/constructor hiện hữu trong dependency đang resolve; không dùng API chỉ có ở blog mới.
5. **Không vô hiệu hóa default headers?** Không sử dụng `headers(...disable())` để sửa một header riêng.
6. **Không bị trùng?** Writer, DSL, filter, gateway/CDN không phát giá trị mâu thuẫn.
7. **Đúng chain?** Matcher và thứ tự `@Order` tương ứng, không kỳ vọng header tự kế thừa từ chain khác.
8. **Đúng semantics browser?** MockMvc/WebTestClient PASS vẫn cần test popup, iframe, CDN/CORS và browser support.
9. **Giữ các lớp phòng vệ khác?** Authentication, CSRF, quyền server, CSP, cookie session, HSTS và HTTP firewall vẫn hoạt động.
10. **Có kế hoạch nâng cấp?** Mỗi ngoại lệ legacy có owner, bằng chứng và lộ trình loại bỏ.

## 20. Kết luận

**`HeaderWriter` và `ServerHttpHeadersWriter` là công cụ phát HTTP response headers, còn tác động bảo mật được quyết định bởi chính sách cụ thể và browser.** Khi ứng dụng Servlet/WebFlux khác phiên bản, không nên ép dùng một DSL đã thấy trên mạng; hãy kiểm tra dependency, khả năng hỗ trợ trong builder và chọn **DSL chuyên dụng hoặc static writer phù hợp**.

Với các header của chương **Quyền và cô lập trình duyệt**, cần đặc biệt ghi nhớ: **COOP bảo vệ quan hệ cửa sổ**, **COEP yêu cầu điều kiện nhúng/tải**, **CORP nằm trên response tài nguyên**, **CORS cần bộ xử lý request/preflight phù hợp**, **Permissions-Policy giới hạn khả năng API** và **Referrer-Policy giới hạn thông tin URL nguồn**. Những chính sách này bổ sung cho CSRF, CSP, HSTS và session security chứ không thay thế chúng.

Quy trình thực hành bền vững là **chọn đúng header → đúng writer/framework/version → đúng route/response → readback/test HTTP → kiểm thử browser → xác minh qua proxy/CDN**, với ngoại lệ được kiểm soát và không làm yếu các security headers mặc định.

### Tài liệu tham khảo

- [Spring Security — Servlet HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): default headers, CSP, referrer và cách cấu hình HTTP headers trong Servlet.
- [Spring Security — Reactive HTTP Response Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html): API và cấu hình response headers trong WebFlux.
- [Spring Security — API documentation](https://docs.spring.io/spring-security/site/docs/current/api/): tra `HeaderWriter`, `StaticHeadersWriter`, `ServerHttpHeadersWriter` và builder theo version phù hợp.
- [MDN — Permissions-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy): cú pháp và khả năng tương thích của các feature directive.
- [MDN — Cross-Origin-Opener-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Opener-Policy): opener và top-level window isolation.
- [MDN — Cross-Origin-Embedder-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Embedder-Policy): tài nguyên cross-origin, `require-corp` và `credentialless`.
- [MDN — Cross-Origin-Resource-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Resource-Policy): chính sách của response tài nguyên.
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight, credentials và chính sách chia sẻ response.
- [MDN — Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy): thông tin URL nguồn và các giá trị chính sách.
