# Tìm security chain thực sự xử lý endpoint

> **Chương:** Chẩn đoán lỗi  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Một endpoint trả lỗi — nhưng security chain nào gây ra?

Một ứng dụng Spring Boot có hai vùng: REST API dùng HTTP Basic/Bearer token và giao diện quản trị dùng form login. Nhóm phát triển đã khai báo rằng `/api/**` cần được xác thực qua cơ chế API, nhưng khi gọi `GET /api/reports`, client nhận:

~~~http
HTTP/1.1 302 Found
Location: /login
~~~

Thay vì vội sửa controller, hãy đặt câu hỏi **request này thực sự khớp `SecurityFilterChain` nào?** Nếu một chain tổng quát được xét trước chain API, nó có thể đưa request vào cơ chế form login. Khi đó việc sửa rule `hasRole(...)` bên trong chain API sẽ không giải quyết gì, bởi chain ấy chưa từng xử lý request.

Những dấu hiệu khác của việc request đi nhầm security chain:

- API trả 302 đến `/login` thay vì 401 và `WWW-Authenticate`.
- GET hoạt động nhưng POST nhận 403 do CSRF ở một chain không mong đợi.
- CORS preflight `OPTIONS` không nhận các header CORS cần thiết.
- Security headers (CSP, HSTS, `X-Content-Type-Options`) khác nhau giữa hai route.
- Route có `permitAll()` trong code vẫn bị 401/403 vì rule nằm trong **chain không được chọn**.
- Route nào đó đi thẳng tới controller mà không qua Spring Security do bị loại khỏi filter chain.

**Mục tiêu bài:** xác định chính xác chain xử lý một HTTP endpoint, giải thích thuật toán chọn chain, phân biệt điều kiện chọn chain với rule authorization, dùng log và kiểm thử có bằng chứng trên **Servlet** lẫn **Reactive/WebFlux**, đồng thời chẩn đoán tác động tới CSRF, CORS, headers và session.

## 2. Mô hình hai cấp: chọn chain trước, kiểm tra quyền sau

Trong Servlet stack, một request thường qua `DelegatingFilterProxy` để đi vào `FilterChainProxy` của Spring Security. Bên trong có thể có nhiều `SecurityFilterChain`. Với Reactive/WebFlux, cơ chế tương tự dựa trên `WebFilterChainProxy` và các `SecurityWebFilterChain`.

Điều cốt lõi là **hai loại điều kiện khác nhau**:

1. **Điều kiện chọn chain:** request có thuộc phạm vi chain này không? Ví dụ `securityMatcher("/api/**")`.
2. **Quy tắc bên trong chain:** sau khi chain được chọn, một request có quyền truy cập không? Ví dụ `requestMatchers("/api/admin/**").hasRole("ADMIN")`.

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Proxy / container / HTTP firewall]
    B --> C{Security chain 1 có match?}
    C -- Có --> D[Chạy bộ filters của chain 1]
    C -- Không --> E{Security chain 2 có match?}
    E -- Có --> F[Chạy bộ filters của chain 2]
    E -- Không --> G{Fallback chain có match?}
    G -- Có --> H[Chạy bộ filters của fallback]
    G -- Không --> I[Không có Spring Security chain khớp]
    D --> J[Authentication / CSRF / CORS / Authorization...]
    F --> J
    H --> J
    J --> K[Response hoặc Controller]
~~~

**Không có cơ chế cộng các filter và rule của mọi chain phù hợp.** Chain đầu tiên khớp theo thứ tự được xét sẽ được chọn; các chain sau không được dùng cho request đó.

| Khái niệm | Đặt ở đâu? | Quyết định điều gì? |
|---|---|---|
| `@Order` trên bean chain | Cấu hình nhiều chain | Thứ tự các chain được xét |
| `securityMatcher(...)` (Servlet) | `HttpSecurity` | Toàn bộ chain áp dụng cho request nào |
| `authorizeHttpRequests(...).requestMatchers(...)` | Trong chain Servlet đã được chọn | Request có được `permitAll`, `authenticated` hoặc yêu cầu authority không |
| `securityMatcher(...)` (Reactive) | `ServerHttpSecurity` | `SecurityWebFilterChain` áp dụng cho exchange nào |
| `authorizeExchange(...).pathMatchers(...)` | Trong chain Reactive đã được chọn | Điều kiện phân quyền bên trong chain |
| `web.ignoring()` (Servlet) | `WebSecurityCustomizer` | Loại một số request khỏi Spring Security filter chain, không đồng nghĩa `permitAll` |

Không nên nhầm `SecurityFilterChain` (Servlet) với `SecurityWebFilterChain` (Reactive). Hai loại có nguyên tắc chọn tương tự nhưng API, servlet filters và reactive web filters **không thể dùng thay thế cho nhau**.

## 3. Servlet: thuật toán first-match của FilterChainProxy

Với nhiều bean `SecurityFilterChain`, `FilterChainProxy` làm việc về nguyên tắc:

~~~text
for each securityChain in orderedChains:
    if securityChain.matches(request):
        use filters from securityChain
        stop searching

if no chain matches:
    continue without filters from that FilterChainProxy
~~~

Đây là **pseudocode giải thích**, không phải mã nguồn nguyên văn. Request còn có thể bị `HttpFirewall` từ chối trước bước matching, và servlet container/proxy có thể đã xử lý URL theo quy tắc riêng.

### Ưu tiên @Order

Về cơ bản, `@Order(1)` được xét trước `@Order(2)`; số thứ tự thấp hơn thể hiện độ ưu tiên cao hơn. Nếu có một chain rộng khớp mọi request nằm trước chain đặc biệt, chain đặc biệt có nguy cơ **không bao giờ được chọn**.

Ví dụ sai về ý tưởng:

~~~java
@Bean
@Order(1)
SecurityFilterChain generic(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(a -> a.anyRequest().authenticated());
    http.formLogin(Customizer.withDefaults());
    return http.build(); // Không có securityMatcher: thường là catch-all.
}

@Bean
@Order(2)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    http.httpBasic(Customizer.withDefaults());
    http.authorizeHttpRequests(a -> a.anyRequest().authenticated());
    return http.build();
}
~~~

Khi chain `generic` đứng đầu và match mọi request, request `/api/reports` không đến chain `api`. Dù chain API có cấu hình đúng, nó không có tác dụng đối với request đã khớp generic.

**Cách sửa:** cho chain đặc thù khớp trước, chain fallback sau; đặt matcher phạm vi rõ ràng và thêm kiểm thử chứng minh thứ tự.

## 4. Ví dụ Servlet chuẩn: chain API trước, fallback web sau

Ví dụ sau minh họa cú pháp Spring Security theo DSL lambda (phổ biến trong Spring Security 6). Hai chain cùng tồn tại nhưng có phạm vi khác nhau:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiChainSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**");

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        );

        http.httpBasic(Customizer.withDefaults());
        // Bài học giữ nguyên CSRF protection để quan sát sự khác biệt
        // giữa GET và POST. API stateless phải đánh giá CSRF riêng.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webFallback(HttpSecurity http) throws Exception {
        // Không khai báo securityMatcher: chain fallback cho request còn lại.
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated()
        );

        http.formLogin(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Giả định môi trường lab có các controller phù hợp, và HTTP Basic có cơ chế tìm user hợp lệ khi cần test đăng nhập. Cấu hình ví dụ **không tạo database, user hoặc controller**; những thành phần đó phải tồn tại trong ứng dụng thực hành.

| Request | Chain được chọn | Rule bên trong | Phản hồi thường gặp |
|---|---|---|---|
| `GET /api/public/ping` | `apiChain` | `permitAll()` | Controller có thể trả 200 |
| `GET /api/reports`, anonymous | `apiChain` | `authenticated()` | 401 và Basic challenge |
| `GET /api/admin/summary`, user thiếu `ROLE_ADMIN` | `apiChain` | `hasRole("ADMIN")` | 403 |
| `GET /public/about` | `webFallback` | `permitAll()` | Controller có thể trả 200 |
| `GET /private/dashboard`, anonymous | `webFallback` | `authenticated()` | Thường redirect 302 đến login |
| `POST /api/orders`, có authentication nhưng thiếu CSRF token | `apiChain` | CSRF có thể từ chối trước authorization | Thường 403 khi CSRF đang áp dụng |

Lưu ý mã phản hồi thực tế còn phụ thuộc các thành phần được bật, auth scheme, redirect và controller. Mục đích của bảng là minh họa **một request vào chain nào**, không phải khẳng định mọi ứng dụng trả đúng status đã liệt kê.

### Không tùy tiện tắt CSRF trên API

Nhiều API chỉ nhận Bearer token qua `Authorization` và không dựa vào ambient cookie nên có thể thiết kế khác với form dùng session. Nhưng nếu API sử dụng cookie hoặc HTTP Basic do browser tự gửi, nguy cơ CSRF cần được xem xét nghiêm túc.

**Không sử dụng `csrf.disable()` như một mẹo để xác định chain.** Hãy kiểm tra điểm từ chối, loại credential và yêu cầu kiến trúc trước khi chọn chính sách CSRF phù hợp cho từng chain.

## 5. securityMatcher và requestMatchers dễ bị đặt sai chỗ

So sánh hai cấu hình:

~~~java
// A: Chain chỉ được chọn cho request thuộc /api/**.
http.securityMatcher("/api/**");
http.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
);
~~~

~~~java
// B: Không thu hẹp chain; chỉ quy định authorization cho /api/**.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .anyRequest().permitAll()
);
~~~

**A và B không tương đương.** Ở A, các request ngoài `/api/**` sẽ không sử dụng chain ấy. Ở B, nếu `HttpSecurity` không có `securityMatcher`, chain có thể vẫn match **mọi request**, kể cả request được `permitAll`. Nếu B đứng đầu, các chain sau có thể không bao giờ được chọn.

### Bẫy “đặt rule rất chính xác nhưng vẫn nhầm chain”

~~~java
@Order(1)
SecurityFilterChain broad(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/health").permitAll()
        .anyRequest().authenticated()
    );
    return http.build();
}
~~~

Khi không có `securityMatcher`, rule `/health` không thu hẹp phạm vi chain. Nếu một bean khác `@Order(2)` mới xử lý `/api/**`, nó có thể bị che hoàn toàn.

### Trong một chain cũng có thứ tự rule

Ngay cả sau khi tìm đúng chain, **thứ tự các rule authorization** vẫn quan trọng:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

Một rule rộng `/api/**` đứng trước rule hẹp `/api/admin/**` có thể khiến yêu cầu admin chỉ bị kiểm tra `authenticated()` thay vì kiểm tra role như dự định.

Hãy đưa rule cụ thể trước rule tổng quát **trong cùng chain**:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Hai lỗi cần kiểm tra **riêng biệt**:

1. Chain nào được chọn?
2. Rule nào trong chain được áp dụng?

## 6. Nếu không có chain nào match, điều gì xảy ra?

Giả sử chỉ khai báo:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    http.authorizeHttpRequests(a -> a.anyRequest().authenticated());
    http.httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

Với request `GET /unmatched`, không có chain nào trong cấu hình này match. Nếu không có security chain khác do ứng dụng/auto-configuration cung cấp, request có thể tiếp tục đến application **mà không đi qua các Spring Security filters trong `FilterChainProxy` ấy**.

Đây không tương đương với:

~~~java
.anyRequest().denyAll()
~~~

Rule `denyAll()` chỉ có tác dụng **sau khi đã chọn một chain**. Nó không tự tạo chain fallback cho mọi URL còn lại.

**Rủi ro:** thiếu fallback có thể làm route nằm ngoài `/api/**` không được bảo vệ bởi Spring Security headers, CSRF, authentication và authorization của filter chain tương ứng.

Một cách thiết kế thường dùng là có **chain fallback cuối cùng** match những request còn lại, với chính sách rõ ràng. Trường hợp cố tình để một số request không đi qua Spring Security cần review đặc biệt vì khác với `permitAll()`.

## 7. permitAll và web.ignoring: hai quyết định khác nhau

Ở Servlet, bạn có thể thấy:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/assets/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Ở đây request `/assets/logo.svg` **vẫn đi qua security chain** được chọn; chỉ bước authorization cho phép truy cập mà không yêu cầu đăng nhập.

Khác với:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;

@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
        .requestMatchers("/assets/**");
}
~~~

Với `web.ignoring()`, các request khớp được đưa ra khỏi bộ Spring Security filters theo cấu hình đó. Hệ quả có thể gồm:

- Không được Spring Security thêm CSP, HSTS, `X-Content-Type-Options` và những security headers khác như các request đi qua chain.
- Không sử dụng những cơ chế context/authentication/CSRF/CORS tương ứng trong Spring Security filters.
- Khi debug, việc không thấy log một filter không chứng minh route được `permitAll()`; nó có thể bị **bỏ qua toàn chain**.

Trong nhiều ứng dụng, **ưu tiên `permitAll()`** khi muốn phục vụ static resources công khai nhưng vẫn giữ security headers và các bảo vệ cần thiết. Nếu hạ tầng CDN phục vụ asset tách origin, phải xác định header bảo vệ nào thuộc trách nhiệm của CDN; không giả định CSP ở API sẽ áp dụng cho tài liệu HTML của CDN.

## 8. Cách tìm chain trong log Servlet

Trên môi trường dev/staging có quyền kiểm soát, có thể tăng mức log có chọn lọc:

~~~properties
# Cho thấy các hoạt động security ở mức tổng quát.
logging.level.org.springframework.security=DEBUG

# Khi cần điều tra chọn chain, có thể bật TRACE tạm thời.
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Mức DEBUG thường giúp nhận biết Spring Security đang bảo vệ một request; log khởi tạo có thể cho thấy cấu hình filter chains. Khi cần chứng minh **matcher nào đã được xét và chain nào thực sự khớp**, TRACE và log startup của phiên bản đang dùng có ích hơn việc chỉ tìm dòng `Securing GET /api/reports`.

Ví dụ kiểu thông tin có thể gặp (mang tính minh họa, **không phải format log ổn định**):

~~~text
... Trying to match request against DefaultSecurityFilterChain ...
... Securing GET /api/reports
... Invoking SecurityContextHolderFilter ...
... Invoking AuthorizationFilter ...
~~~

**Không dùng chỉ số/filter order trong log làm API lâu dài.** Tên filter, mức log và lời nhắn thay đổi theo phiên bản Spring Security. Hãy đối chiếu với các bean chain đang được tạo và HTTP request thực nhận.

### EnableWebSecurity(debug = true) có nên bật?

Trong Servlet có chế độ security debug phục vụ chẩn đoán chuyên sâu, ví dụ cấu hình `@EnableWebSecurity(debug = true)` theo môi trường/version phù hợp. Chế độ này có thể ghi nhiều thông tin về request và filter, có nguy cơ tiết lộ headers hoặc dữ liệu nhạy cảm.

**Không bật security debug toàn cục lâu dài trên production.** Ưu tiên log có chọn lọc, thời gian ngắn, có quyền truy cập chặt chẽ và xử lý dữ liệu nhạy cảm; tắt lại sau khi thu đủ bằng chứng.

### Bằng chứng cần lưu khi điều tra

| Thuộc tính | Tại sao cần? |
|---|---|
| Timestamp và correlation ID | Liên kết log browser/proxy/container/Spring |
| Method và URI gốc/đã rewrite (đã loại dữ liệu nhạy cảm) | Kiểm tra matcher và firewall |
| Servlet context path / servlet path | Tránh so khớp nhầm đường dẫn |
| Origin/Host và thông tin proxy đáng tin | Tìm khác biệt khi request qua gateway |
| Security chain/matcher đã chọn | Trả lời trực tiếp bài toán |
| Authentication scheme và authorities | Phân biệt 401, 403 và rule |
| CSRF/CORS/authorization failure nếu có | Định vị filter từ chối |
| Response status, `WWW-Authenticate`, `Location` | Đối chiếu HTTP behavior |

Không ghi nguyên `Authorization`, bearer token, cookie session, CSRF token hoặc dữ liệu người dùng vào log/debug report chia sẻ.

## 9. Quan sát chain bằng marker chỉ dành cho môi trường test

Nếu log chưa đủ để phân biệt hai chain tương tự, có thể gắn một dấu hiệu **chỉ trong test/staging** vào response từ filter đặt trong từng chain. Ví dụ một servlet filter không đăng ký như global bean:

~~~java
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.context.SecurityContextHolderFilter;

private static Filter chainMarker(String chainName) {
    return (request, response, filterChain) -> {
        ((HttpServletResponse) response)
            .setHeader("X-Debug-Security-Chain", chainName);
        filterChain.doFilter(request, response);
    };
}

// Trong phương thức cấu hình apiChain(HttpSecurity http):
http.addFilterBefore(
    chainMarker("api"),
    SecurityContextHolderFilter.class
);
~~~

Khi áp dụng tương tự cho fallback chain với tên `web`, một HTTP test có thể đọc `X-Debug-Security-Chain` để biết chain nào đã chạy.

**Giới hạn cần hiểu:** đoạn code là một **phương án instrumentation có phạm vi rõ**, không phải cấu hình production. Nếu HTTP firewall từ chối request trước khi chain chạy, nếu proxy/container tạo response trước Spring, hoặc nếu một filter đứng trước marker dừng xử lý, header có thể không xuất hiện. **Thiếu marker không đồng nghĩa chắc chắn không có chain match**; hãy kết hợp log và vị trí từ chối.

Để tránh rò thông tin kiến trúc, không xuất tên chain nội bộ ra response production. Nếu thêm marker vào test, bảo đảm filter chỉ đăng ký trong test/staging và không bị tự động đăng ký lần thứ hai vào Servlet container.

## 10. CORS preflight và CSRF: vì sao status có thể làm ta tìm nhầm chain?

### CORS: OPTIONS có thể đi qua một chain khác GET/POST

Browser có thể gửi:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://frontend.example.net
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Nếu chain API chỉ match `GET /api/**` do một matcher tùy biến, thì request `OPTIONS` có thể **không vào cùng chain**. Một security chain khác có thể yêu cầu authentication hoặc trả redirect; frontend chỉ thấy lỗi CORS.

Ngay cả khi OPTIONS và POST chọn **cùng chain**, CORS processor có thể từ chối origin/method/header không hợp lệ trước authorization. Phải kiểm tra:

1. Chain nào match **preflight OPTIONS**?
2. CORS configuration đã được áp vào đúng chain chưa?
3. `Origin`, requested method và headers có được cấp phép không?
4. Browser có thực sự gửi POST sau preflight thành công không?
5. Request POST có còn cần auth/authorization/CSRF riêng hay không?

Trong Servlet, cấu hình `http.cors(Customizer.withDefaults())` thường được dùng khi có nguồn `CorsConfigurationSource` phù hợp hoặc cấu hình Spring MVC được tích hợp đúng. **Chỉ thêm `permitAll()` cho OPTIONS không tự tạo header `Access-Control-Allow-Origin` đúng.**

### CSRF: 403 trên POST không xác định chain

Giả sử GET `/api/orders` thành công nhưng POST nhận 403. Có ít nhất ba khả năng khác nhau:

- POST match chain khác do matcher phụ thuộc method.
- POST match đúng chain nhưng bị `CsrfFilter` từ chối vì thiếu token.
- POST qua CSRF rồi bị authorization/method security từ chối.

Không tắt CSRF toàn hệ thống để tìm lỗi. Hãy dùng một request test có token CSRF hợp lệ làm **đối chứng**, đồng thời kiểm tra chain được chọn.

## 11. Authentication, status và header chỉ là dấu hiệu gián tiếp

Những kết quả HTTP thường gợi ý loại chain, nhưng **không chứng minh trực tiếp**:

| Quan sát | Giả thuyết | Cần xác minh thêm |
|---|---|---|
| 401 + `WWW-Authenticate: Basic` | Chain HTTP Basic/API | Log chain, entry point, auth scheme |
| 401 + Bearer challenge | Chain resource server | Token/decoder config và chain |
| 302 + `Location: /login` | Form-login chain | Redirect do entry point nào sinh? |
| 403 + thiếu role | Authorization rule được áp dụng | Chain, rule, authorities thực tế |
| 403 trên POST | CSRF hoặc authorization | CSRF exception, chain, authentication |
| 403 trên OPTIONS | CORS hoặc chain yêu cầu auth | CORS processor, preflight log |
| 400 + `RequestRejectedException` | Servlet HTTP firewall | URI thực nhận và rejection handler |
| CSP/header khác kỳ vọng | Chain khác hoặc proxy/CDN chỉnh header | Header ở origin và public path |
| Không có Spring Security header | Ignoring, no matching chain, proxy hoặc response trước Spring | Log/tracing và nguồn tạo response |

Một application có thể cấu hình entry point/denied handler tùy chỉnh; proxy cũng có thể thêm các header trông giống Spring Security. Vì thế status và header là **dấu hiệu để đặt giả thuyết**, không phải phép chứng minh chain duy nhất.

## 12. Servlet path, context path và reverse proxy làm matcher khó hiểu

Request công khai:

~~~text
https://public.example.net/my-app/api/orders
~~~

có thể đi qua proxy:

~~~text
GET /my-app/api/orders
     → proxy rewrite
GET /api/orders
     → Spring app
~~~

Trong Servlet container, còn có những giá trị khác nhau như:

~~~text
requestURI   : /my-app/api/orders
contextPath  : /my-app
servletPath  : /api/orders
pathInfo     : ...
~~~

Đây chỉ là ví dụ **một kiểu deployment**; các giá trị phải được quan sát thật, vì servlet mapping và proxy rewrite có thể khác. Spring Security có nhiều loại matcher, bao gồm cơ chế nhận biết Spring MVC mapping; chúng có thể diễn giải context path/servlet path và URL encoding khác nhau.

**Không suy rằng pattern `/api/**` đang match trực tiếp URL được browser thấy**. Cần kiểm tra đường dẫn thực sự được Spring nhận và loại matcher mà phiên bản/config đang dùng chọn.

Những bẫy thường gặp:

- Servlet được mount dưới prefix khác `/`; matcher viết theo đường browser thay vì path mà matcher nhận.
- Reverse proxy xóa hoặc thêm tiền tố `/gateway` nhưng Spring không biết.
- Route có dấu slash cuối, viết hoa/thường hoặc encoded characters khác kỳ vọng.
- Một chain dùng matcher theo HTTP method; GET và OPTIONS/POST không cùng kết quả.
- Servlet API và WebFlux dùng hệ matcher khác nhau.
- Request bất thường bị `StrictHttpFirewall` hoặc container từ chối trước khi chọn chain.

Nếu cần xử lý `Forwarded` hoặc `X-Forwarded-*`, chỉ tin các giá trị do proxy được kiểm soát cung cấp. Không dùng header Host/forwarded do client có thể giả để tự động xây source expression CSP hay security matcher mà không có trust boundary.

## 13. Reactive/WebFlux: cùng nguyên tắc first-match, API khác

Với Reactive stack, Spring Security xây dựng tập `SecurityWebFilterChain` và chọn chain bằng `ServerWebExchangeMatcher`. Thành phần quản lý là `WebFilterChainProxy`, không phải `FilterChainProxy` của Servlet.

Ví dụ hai chain tương ứng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
public class ReactiveMultiChainSecurity {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        http.securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**")
        );

        http.authorizeExchange(auth -> auth
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers("/api/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated()
        );
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain webFallback(ServerHttpSecurity http) {
        http.authorizeExchange(auth -> auth
            .pathMatchers("/public/**").permitAll()
            .anyExchange().authenticated()
        );
        http.formLogin(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Các điểm tương ứng:

| Servlet | Reactive/WebFlux |
|---|---|
| `FilterChainProxy` | `WebFilterChainProxy` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity.securityMatcher(...)` | `ServerHttpSecurity.securityMatcher(...)` |
| `HttpServletRequest` / `RequestMatcher` | `ServerWebExchange` / `ServerWebExchangeMatcher` |
| `authorizeHttpRequests` | `authorizeExchange` |
| `requestMatchers` trong authorization | `pathMatchers` hoặc `matchers` trong authorization |
| Servlet `Filter` / `SecurityContextHolderFilter` | Reactive `WebFilter` / reactive security context |
| `@Order` định thứ tự bean chains | `@Order` định thứ tự bean chains |

**Không dùng một `OncePerRequestFilter` Servlet để quan sát WebFlux**, cũng không đặt một `SecurityWebFilterChain` vào servlet stack. Nếu ứng dụng Spring Boot có cả WebFlux và MVC dependencies, cần xác định **web application type thực tế** và HTTP server được dùng, thay vì đoán từ dependency có mặt.

### Phân biệt hai cấp matcher trong WebFlux

~~~java
// Giới hạn phạm vi toàn bộ chain:
http.securityMatcher(
    ServerWebExchangeMatchers.pathMatchers("/api/**")
);

// Chỉ quyết định authorization sau khi chain đã được chọn:
http.authorizeExchange(auth -> auth
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated()
);
~~~

Một `pathMatchers(...)` trong `authorizeExchange` không thu hẹp phạm vi của `SecurityWebFilterChain` nếu `securityMatcher(...)` không được cấu hình. Lỗi chain fallback đứng quá sớm **cũng xảy ra trong WebFlux**.

## 14. Log chain Reactive: WebFilterChainProxy và các web filters

Ví dụ logging có chọn lọc ở môi trường thử nghiệm:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.server.WebFilterChainProxy=TRACE
~~~

Log thực tế có thể khác Servlet vì WebFlux dùng reactive publisher và request có thể xử lý trên nhiều thread. Không dựa vào `ThreadLocal` hoặc tên thread làm định danh request; dùng correlation ID và context/logging được cấu hình phù hợp.

Khi điều tra:

1. Ghi HTTP method, path và query đã làm sạch của `ServerWebExchange`.
2. Kiểm tra thứ tự bean `SecurityWebFilterChain` và matcher của từng chain.
3. Xác minh exchange nào thực sự khớp, không chỉ xem một dòng “Securing ...”.
4. Xem các `WebFilter` liên quan: authentication, CSRF, CORS, exception translation, authorization.
5. Đối chiếu response cuối cùng, nhất là khi Reactor Netty/gateway xử lý request trước.

### Reactive marker chỉ dành cho test

Khi cần chứng cứ hiển thị trực tiếp, có thể thêm `WebFilter` riêng vào từng chain:

~~~java
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;

// Trong apiChain(ServerHttpSecurity http), chỉ bật tại test/staging:
http.addFilterAt((exchange, chain) -> {
    exchange.getResponse().getHeaders()
        .set("X-Debug-Security-Chain", "reactive-api");
    return chain.filter(exchange);
}, SecurityWebFiltersOrder.FIRST);
~~~

Marker được chạy khi chain tương ứng đã được chọn và filter tới lượt. Không ghi tên chain này trên response production. Trên một request bị gateway, HTTP server hoặc tầng trước `WebFilterChainProxy` từ chối, marker có thể không xuất hiện.

### Reactive request matcher có thể bất đồng bộ

`ServerWebExchangeMatcher.matches(exchange)` trả kết quả trong luồng reactive. Khi thiết kế custom matcher, tránh side effect, blocking I/O hoặc thay đổi exchange không cần thiết. Matcher nên quyết định phạm vi chain rõ ràng, có thể kiểm thử bằng request thực; không đặt logic authentication phức tạp vào matcher để giải quyết authorization.

## 15. Tạo ca test Servlet chứng minh chain nào chạy

Một bộ test chỉ xem 200/401/403 thường cho bằng chứng **gián tiếp**. Để chắc hơn, kết hợp ba loại assert:

1. **Header marker** trong test-only chain instrumentation khi phù hợp.
2. **Hành vi riêng của chain**, như HTTP Basic 401 so với form-login redirect.
3. **Log/matcher thực nhận**, đặc biệt nếu request bị từ chối trước marker.

Giả sử đã đăng ký hai chain như mục 4, có các route demo, MockMvc bật Spring Security filter và môi trường test có user phù hợp.

### 15.1. API anonymous đi vào Basic chain

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/reports"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        "WWW-Authenticate",
        containsString("Basic")
    ));
~~~

Đây là bằng chứng mạnh cho việc entry point HTTP Basic có hiệu lực với route API, nhưng một entry point custom hoặc proxy cũng có thể xuất challenge. Trong test-only instrumentation, kiểm tra thêm:

~~~java
mockMvc.perform(get("/api/reports"))
    .andExpect(header().string(
        "X-Debug-Security-Chain", "api"
    ));
~~~

Chỉ dùng assertion header marker khi code test đã gắn marker đó vào chain và filter được chạy trước điểm trả response.

### 15.2. Route ngoài API đi vào form-login fallback

~~~java
mockMvc.perform(get("/private/dashboard"))
    .andExpect(status().is3xxRedirection())
    .andExpect(header().string(
        "Location",
        containsString("/login")
    ));
~~~

Nếu test-only marker được bật, có thể assert giá trị `web` thay cho `api`. Nếu request redirect tới external SSO hoặc API dùng bearer entry point, cần chỉnh kỳ vọng theo cấu hình thực chứ không ép tất cả route thành Basic/form login.

### 15.3. Public API vẫn đi qua API chain

~~~java
mockMvc.perform(get("/api/public/ping"))
    .andExpect(status().isOk());
~~~

Một route trả 200 không tự chứng minh nó ở chain API; route có thể bị `permitAll` ở chain khác hoặc không được bảo vệ. Hãy đối chiếu marker/log và xác nhận ứng dụng thật sự có controller trả 200 cho route đó.

### 15.4. User đúng và sai quyền: authorization sau chain selection

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;

mockMvc.perform(get("/api/admin/summary")
        .with(user("analyst").roles("USER")))
    .andExpect(status().isForbidden());

mockMvc.perform(get("/api/admin/summary")
        .with(user("admin").roles("ADMIN")))
    .andExpect(status().isOk());
~~~

Giả định `/api/admin/summary` có handler trả 200 và method security không thêm ràng buộc khác. Hai ca này xác minh rule `hasRole("ADMIN")` sau khi chain API được chọn. Dùng `spring-security-test` cho `with(user(...))`; không coi đây là test xác thực password thật.

### 15.5. Test method và CORS preflight

Trong cùng bộ test, cần có ca:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;

mockMvc.perform(options("/api/orders")
        .header("Origin", "https://frontend.example.net")
        .header("Access-Control-Request-Method", "POST"))
    // Kỳ vọng response phụ thuộc CORS configuration của ứng dụng:
    // kiểm tra marker/log của chain và response CORS riêng.
    ;
~~~

Đoạn cuối minh họa việc tạo request, **không phải test assertion hoàn chỉnh**. Khi triển khai thật, cần thiết lập origin/method/header được phép trong CORS config, rồi assert status/header được kỳ vọng. Không mặc định preflight luôn 200 hoặc luôn đi qua authorization giống POST.

## 16. Kiểm thử WebFlux bằng WebTestClient

Các nguyên tắc tương tự Servlet, nhưng test harness và mock authentication là Reactive:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

// API anonymous dùng Basic chain: thường 401.
webTestClient.get()
    .uri("/api/reports")
    .exchange()
    .expectStatus().isUnauthorized();

// Route web anonymous dùng form login: thường 302.
webTestClient.get()
    .uri("/private/dashboard")
    .exchange()
    .expectStatus().is3xxRedirection();

// API admin, người dùng có ROLE_USER: 403.
webTestClient.mutateWith(mockUser("analyst").roles("USER"))
    .get()
    .uri("/api/admin/summary")
    .exchange()
    .expectStatus().isForbidden();

// Người dùng có ROLE_ADMIN: handler có thể trả 200.
webTestClient.mutateWith(mockUser("admin").roles("ADMIN"))
    .get()
    .uri("/api/admin/summary")
    .exchange()
    .expectStatus().isOk();
~~~

Test giả định WebTestClient đã được gắn Spring Security và endpoint tồn tại. Muốn xác nhận chain chính xác, test-only marker ở mục 14 có thể giúp:

~~~java
webTestClient.get()
    .uri("/api/reports")
    .exchange()
    .expectHeader()
    .valueEquals("X-Debug-Security-Chain", "reactive-api");
~~~

Nếu test có `SecurityWebFilterChain` nhưng không có Reactor Netty HTTP server thực, kết quả chưa kiểm tra lớp HTTP parsing và reverse proxy như production. Khi nghi ngờ URL normalization, routing hay gateway, cần thêm HTTP integration test trên server thực tế.

### CSRF ở WebFlux

Nếu cần đối chứng POST:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

webTestClient.mutateWith(mockUser("admin").roles("ADMIN"))
    .post().uri("/api/orders")
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("admin").roles("ADMIN"))
    .mutateWith(csrf())
    .post().uri("/api/orders")
    .exchange()
    // Assert theo response thật của controller nếu request qua CSRF.
    ;
~~~

Đây là ví dụ phân biệt **CSRF rejection** với chain selection, không phải đề xuất tắt CSRF cho Reactive. Khi request có token hợp lệ vẫn 403, hãy tiếp tục kiểm tra authorization, method security và controller.

## 17. Kiểm kê các bean chain để biết hệ thống đang có gì

Một sai sót hay gặp là **tưởng ứng dụng chỉ có hai chain** nhưng một dependency, cấu hình điều kiện hoặc auto-configuration lại tạo thêm chain, hoặc thứ tự thực tế khác dự kiến.

Trong Servlet, `FilterChainProxy` cung cấp thông tin về các `SecurityFilterChain` đã được cấu hình. Trong môi trường test/dev, có thể in ra danh sách đã được framework tạo, thay vì chỉ đọc source:

~~~java
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.SecurityFilterChain;

// Ví dụ mã chẩn đoán đặt trong công cụ test/dev có FilterChainProxy.
int index = 0;
for (SecurityFilterChain chain : filterChainProxy.getFilterChains()) {
    System.out.println("Chain " + index++ + ": " + chain);
    System.out.println("Filters: " + chain.getFilters()
        .stream().map(f -> f.getClass().getSimpleName()).toList());
}
~~~

Đây là đoạn minh họa, cần có biến `filterChainProxy` được lấy bằng dependency injection/test context. `toString()` hoặc filter name hiển thị **mô tả cấu hình**, không tự xác nhận một request cụ thể sẽ khớp.

**Bước tiếp theo vẫn phải gửi request và kiểm tra matcher/runtime behavior.** Một chain xuất hiện trong danh sách không có nghĩa nó được chọn với endpoint bạn đang điều tra.

Không công khai danh sách filter/matcher nội bộ lên API production. Thông tin này phục vụ quản trị, có thể tiết lộ cấu trúc bảo mật.

### Với Reactive

Có thể dùng log startup, beans trong test ApplicationContext và khả năng introspection tương ứng của phiên bản đang chạy để liệt kê các `SecurityWebFilterChain`. Đừng ép `FilterChainProxy` Servlet vào Reactive, cũng đừng đoán có method `getFilterChains()` giống hệt ở tất cả phiên bản Reactive. Mục tiêu cuối là kiểm tra **matcher và filter behavior** của exchange thực.

## 18. ERROR, FORWARD, ASYNC và route nội bộ

Trong Servlet, một HTTP request có thể liên quan đến nhiều **dispatcher types**, chẳng hạn:

- `REQUEST`: request ban đầu.
- `FORWARD`: nội bộ forward tới servlet/view.
- `ERROR`: dispatch đến trang lỗi.
- `ASYNC`: một số luồng xử lý bất đồng bộ.

Việc Spring Security filters có được áp dụng lại trên các dispatch đó hay không phụ thuộc filter registration, framework/config và kiểu dispatcher. Nếu một trang lỗi 403 hoặc 500 bất ngờ bị redirect tới login, có thể lỗi nằm ở **dispatch/authorization của error page**, không phải controller ban đầu.

Ví dụ cơ chế authorization cho một số dispatcher trong Servlet:

~~~java
import jakarta.servlet.DispatcherType;

http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
        DispatcherType.FORWARD,
        DispatcherType.ERROR
    ).permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

**Lưu ý:** đoạn trên chỉ điều chỉnh **authorization bên trong chain đã chọn**; nó không tự chọn chain khác hoặc thay đổi filter registration. Chỉ áp dụng khi yêu cầu bảo mật của error/forward đã được review. Không mặc định cho tất cả error routes `permitAll` nếu route ấy có dữ liệu nhạy cảm.

### Vì sao test trực tiếp URL và test qua forward cho kết quả khác?

Một request trực tiếp `GET /error` có thể mang khác method, security context hoặc dispatcher type so với error dispatch thực tế. Vì vậy khi một tình huống chỉ lỗi trong production:

1. Kiểm tra request gốc và error/forward dispatch.
2. Xác định Spring Security chain có được chọn ở mỗi dispatch không.
3. So sánh filter registration, servlet mapping và security matchers.
4. Kiểm tra template HTML của trang lỗi nhận security headers/CSP như mong muốn.

Reactive/WebFlux có đường xử lý lỗi khác Servlet dispatcher. Không chuyển nguyên khái niệm `DispatcherType.ERROR` sang `ServerWebExchangeMatcher` của WebFlux.

## 19. Actuator, management port và nhiều ApplicationContext

Các management endpoints như Spring Boot Actuator có thể chạy:

- Trên cùng cổng và context với ứng dụng.
- Dưới management base path khác.
- Trên **cổng management riêng**, có thể dẫn đến web server/context bảo mật riêng tùy cấu hình.

Ví dụ giả định:

~~~text
https://app.example.com/actuator/health
https://management.example.net/actuator/health
~~~

Không thể khẳng định hai đường này dùng cùng security chain chỉ vì tên endpoint giống nhau. Cần kiểm tra **cổng, application context, management configuration và bean chains thực tế**.

Nếu muốn phân quyền Actuator, nên dùng cơ chế matcher do framework hỗ trợ phù hợp phiên bản, kiểm soát exposure của endpoint và đăng nhập/quyền quản trị. Không coi việc endpoint trả 200 hoặc 401 ở cổng khác là bằng chứng chắc chắn của chain trong web application chính.

### Vì sao security chain trong test không giống production?

- Test slice chỉ nạp một phần bean hoặc security config.
- Profile dev/staging/prod kích hoạt bean chain khác nhau.
- Một dependency hoặc auto-configuration conditional thay đổi khi đủ class/bean.
- Management chạy cổng/context khác.
- Reverse proxy rewrite path trước khi request tới Spring.
- Test sử dụng mock request không qua container/netty thật.

Vì vậy cần **kiểm thử ở đúng cấu hình và đường request mà người dùng thật sử dụng** trước khi kết luận.

## 20. Ba tình huống chẩn đoán từ đầu đến cuối

### Tình huống A — API bỗng trả 302 đến /login

**Hiện tượng:** sau một lần refactor Spring Security, `GET /api/reports` (anonymous) không còn trả 401 mà redirect:

~~~http
HTTP/1.1 302 Found
Location: /login
~~~

**Giả thuyết cần kiểm tra:**

1. Có chain fallback với form login đứng trước `/api/**` không?
2. Chain API có thực sự được tạo trong profile đang chạy không?
3. Request đến Spring còn nguyên đường `/api/reports` không, hay proxy rewrite prefix?
4. Có một security matcher phụ thuộc method/origin vô tình loại request khỏi chain API không?
5. Redirect có phải do Spring entry point hay do gateway/SSO?

**Thử nghiệm phân biệt:**

~~~text
GET /api/reports
  -> kiểm tra TRACE matcher: chain API hay fallback match?
  -> nếu fallback match trước, sửa @Order/securityMatcher
  -> nếu chain API match, kiểm tra entry point được cấu hình
  -> nếu không có Spring log, kiểm tra proxy/WAF/route
~~~

**Kết luận mẫu:** nếu TRACE và test marker xác nhận `webFallback` xử lý `/api/reports`, nguyên nhân là **chain selection**, không phải controller hoặc role. Sửa thứ tự/scope, rồi test lại cả API và UI.

### Tình huống B — GET và POST cùng path có status khác

**Hiện tượng:** `GET /api/orders` trả 200 với user hợp lệ; `POST /api/orders` trả 403.

**Có thể do:**

- Cả hai vào API chain, nhưng POST thiếu CSRF token.
- Một chain custom chỉ match `GET`; POST rơi vào fallback.
- POST qua authorization rule khác hoặc method security.
- Browser bị CORS preflight chặn trước khi gửi POST thực.

**Kế hoạch xác minh:**

1. Gửi GET và POST bằng HTTP client test, ghi method, path, headers.
2. Xác nhận **chain của từng method**, không suy từ GET cho POST.
3. Nếu cả hai cùng chain, kiểm tra `CsrfException` và authorization.
4. Gửi POST có token CSRF hợp lệ làm đối chứng khi cơ chế CSRF đang áp dụng.
5. Nếu gọi từ browser khác origin, kiểm tra OPTIONS preflight và CORS headers.

**Kết luận mẫu:** nếu marker/log giống nhau và chỉ thiếu token CSRF khiến POST 403, sửa **CSRF token flow**; đừng thay `securityMatcher` hoặc `permitAll()`.

### Tình huống C — Management endpoint không theo rule ứng dụng

**Hiện tượng:** đội vận hành thêm `requestMatchers("/actuator/health").permitAll()` vào chain web nhưng request trên management port vẫn trả kết quả khác dự kiến.

**Cần tìm:**

- Endpoint có thực sự do cùng web server/application context phục vụ không?
- Có management context/security config khác không?
- Đường dẫn có bị đổi bởi `management.endpoints.web.base-path` hoặc reverse proxy không?
- Cơ chế exposure của Actuator có cho phép endpoint đó không?
- Request nào vào chain nào, và có một tầng gateway bảo vệ riêng không?

**Kết luận mẫu:** nếu request đang ở management port/context khác, việc sửa authorization rule trên chain của main web application có thể không áp dụng. Xác định **đúng context sở hữu endpoint** trước khi đổi cấu hình.

## 21. Kiểm tra HTTP thật bằng công cụ dòng lệnh

Những lệnh dưới đây chỉ minh họa cho **môi trường do bạn kiểm soát**, không phải yêu cầu chạy trong STEP 4.

### 21.1. Phân biệt Basic challenge và form-login redirect

~~~bash
# API anonymous
curl -i http://localhost:8080/api/reports

# Web anonymous, xem response 302 thay vì tự follow sang /login
curl -i http://localhost:8080/private/dashboard
~~~

Quan sát `WWW-Authenticate`, `Location`, cookies, content type và log chain. Không chỉ dựa vào 401/302 vì handler tùy chỉnh và gateway có thể tạo cùng kết quả.

### 21.2. So sánh GET, POST và OPTIONS

~~~bash
curl -i http://localhost:8080/api/orders

curl -i -X OPTIONS http://localhost:8080/api/orders \
  -H 'Origin: https://frontend.example.net' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,authorization'

curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"itemId":"demo-123"}'
~~~

POST ở ví dụ không mang auth/CSRF token; 401/403 có thể là kết quả **dự kiến**, không phải lỗi chain. Khi cần test authenticated POST, sử dụng account/token test hợp lệ, truyền CSRF theo cơ chế ứng dụng và không để bí mật lộ trong command/log.

### 21.3. So sánh đường public với origin

~~~bash
# Qua gateway/reverse proxy staging
curl -i https://staging.example.net/api/reports

# Tới origin được phép kiểm thử
curl -i http://localhost:8080/api/reports
~~~

Nếu kết quả khác, ghi lại:

- `Host`, path/context prefix, scheme, method và redirect.
- Trace ID ở các tầng.
- Security chain log tại origin.
- Gateway authentication/CORS/WAF config và rewrite rule.

Đừng suy rằng hai lệnh gửi request tương đương: `Host`/scheme/cookie có thể khác; proxy có thể chấm dứt TLS và thay đường dẫn. Kết quả chỉ so sánh được khi các khác biệt đã được kiểm soát.

### 21.4. Request bị firewall từ chối trước chain selection

~~~bash
curl --path-as-is -i 'http://localhost:8080/api;flag=1/orders'
~~~

Trong Servlet, đường dẫn bất thường có thể bị `StrictHttpFirewall` từ chối với `RequestRejectedException`. Tuy nhiên proxy/container có thể chặn trước, hoặc kết quả khác theo version/config. Nếu không có chain marker, **chưa đủ bằng chứng** nói chain API không match — request có thể chưa đến bước chọn chain.

## 22. Quy trình tìm chain thực sự: bảy bước

Một quy trình chẩn đoán có thể tái lập:

1. **Xác định request thất bại.** Ghi method, full URL, header quan trọng đã làm sạch, có/không cookie/auth/CSRF và response status thực tế.
2. **Xác nhận request tới Spring chưa.** Đối chiếu browser, CDN/WAF, proxy, container và application logs bằng correlation ID.
3. **Kiểm tra loại stack.** Servlet hay WebFlux? Main application hay Actuator/management context? Đang chạy profile/security configuration nào?
4. **Liệt kê chains thực sự đã tạo** và thứ tự `@Order`. Xác định chain fallback, chain dùng matcher đặc biệt và các nguồn ignore.
5. **Xác nhận matcher first-match trên request thật.** Bật TRACE có chọn lọc hoặc test-only marker; chú ý context/servlet path, method, proxy rewrite và firewall.
6. **Chỉ sau khi đã tìm đúng chain**, xem authentication entry point, CSRF/CORS, headers và rule authorization theo thứ tự; tiếp tục tới method security nếu cần.
7. **Tạo test hồi quy** cho route/method bị lỗi, route không liên quan và đường public; giữ lại bảo vệ HTTP đúng thiết kế.

~~~mermaid
flowchart TD
    A[Endpoint trả sai status/header] --> B{Request đã tới Spring chưa?}
    B -- Không --> C[Browser CSP/CORS, CDN/WAF, proxy, container]
    B -- Có --> D{Firewall/container từ chối trước matching?}
    D -- Có --> E[Kiểm tra URI/method/header/normalization]
    D -- Không --> F[Liệt kê chain theo @Order]
    F --> G{Chain đầu tiên nào matches(request)?}
    G -- Không chain nào --> H[Kiểm tra fallback/ignoring và lỗ hổng bảo vệ]
    G -- Có --> I[Chọn chain đó; không hợp nhất chain khác]
    I --> J[CSRF, CORS, authentication, authorization]
    J --> K[Method security, controller, response]
    K --> L[Test hồi quy tại origin và public path]
~~~

### Phân biệt “không match chain” với “match nhưng permitAll”

| Trạng thái | Spring Security filters được chạy? | Kết quả có thể có |
|---|---|---|
| Chain match, rule `permitAll()` | **Có** | Tài nguyên công khai, vẫn có headers/filter phù hợp |
| Chain match, rule `denyAll()` | **Có** | Bị từ chối bởi authorization |
| Không có chain match | Không có filters của `FilterChainProxy` đó | Request có thể tới controller mà thiếu Spring Security protections |
| Bị `web.ignoring()` loại khỏi Spring Security (Servlet) | Không chạy bộ security filters theo cấu hình ignore | Không tự nhận security headers từ Spring Security |
| Firewall từ chối trước khi chọn chain | Không đi qua filters của chain được chọn | HTTP status theo rejection handler/container |
| Browser chặn CSP trước khi gửi request | Không có request tới backend API | Console violation, không nhất thiết có HTTP status API |

## 23. Các sai lầm nên tránh

| Cách làm sai | Vì sao sai | Cách làm phù hợp |
|---|---|---|
| Đọc thấy `requestMatchers("/api/**")` rồi kết luận API chọn chain đó | Đây có thể chỉ là authorization rule | Xem `securityMatcher` và `@Order` |
| Đặt chain fallback match-all trước chain API | First-match khiến API chain không bao giờ được dùng | Sắp xếp đặc thù trước, fallback cuối |
| Bỏ fallback vì đã có `anyRequest().denyAll()` trong API chain | `denyAll()` không áp cho request ngoài phạm vi chain | Tạo fallback chain rõ ràng nếu muốn bảo vệ toàn bộ ứng dụng |
| Giả định 401 hoặc 302 là bằng chứng tuyệt đối của chain | Custom entry point hoặc proxy có thể trả cùng status | Dùng TRACE/marker và kiểm tra nguồn response |
| Sửa role của user khi POST bị CSRF filter từ chối | Chain có thể đúng, token CSRF thiếu | Kiểm tra CSRF và đối chứng có token |
| Tắt CSRF/CORS để “test chain” | Che lỗi và suy yếu bảo vệ | Dùng request test hợp lệ, quan sát filter |
| Coi `web.ignoring()` giống `permitAll()` | Bypass security filters thay vì chỉ cho authorization | Ưu tiên `permitAll()` khi cần headers |
| Chỉ kiểm tra GET, bỏ OPTIONS/POST | Matcher phụ thuộc method có thể khác | Test từng method thực tế |
| Chỉ dùng MockMvc ở origin rồi kết luận production đúng | Proxy/CDN/context có thể thay request/response | Test qua đường public |
| Dùng Servlet `StrictHttpFirewall` để giải thích mọi lỗi Reactive | Hai stack có HTTP/security processing khác nhau | Dùng đúng WebFlux logs/server behavior |
| Bật security TRACE và log token trên production lâu dài | Lộ dữ liệu nhạy cảm, tăng chi phí | Chẩn đoán có giới hạn, che secrets, tắt sau |
| Dựa vào header marker trên response production | Rò cấu trúc nội bộ | Chỉ dùng instrumentation ở test/staging |
| Chỉ liệt kê bean chains, không kiểm tra request matcher | Chain có bean không đồng nghĩa chain được chọn | Test first-match bằng request thực |

## 24. Bài thực hành tổng hợp

**Bối cảnh:** Một ứng dụng Spring Security có khu vực API và web UI. Dự án muốn bảo vệ API bằng HTTP Basic/Bearer, còn web UI dùng form login. Sau deploy, request `/api/reports` nhận 302, `/api/public/ping` đôi lúc không có CSP header, và `POST /api/orders` nhận 403.

### Nhiệm vụ

1. Tạo hai bean `SecurityFilterChain` Servlet, lần lượt có `@Order(1)` với `securityMatcher("/api/**")` và `@Order(2)` fallback. Trong phạm vi lab, dùng Basic cho API và form login cho web.
2. Cố tình hoán đổi thứ tự để fallback đứng đầu; gọi `/api/reports` và quan sát thay đổi 401/302. Dùng log để chứng minh chain nào được chọn.
3. Thêm authorization rule `requestMatchers("/api/admin/**").hasRole("ADMIN")` và test user có `ROLE_USER`/`ROLE_ADMIN`. Phân biệt **chain** với **rule**.
4. Tạo một phiên bản sai chỉ dùng `requestMatchers("/api/**")` bên trong authorization của chain đầu, không dùng `securityMatcher`. Giải thích vì sao chain vẫn có thể match mọi request.
5. Thử route không khớp chain nào khi không có fallback; xác định có bị thiếu security headers hoặc bảo vệ authorization không.
6. So sánh static route `permitAll()` với một route dùng `web.ignoring()` trong môi trường test. Kiểm tra headers và log, không dùng cơ chế ignoring cho route nhạy cảm.
7. Bật `FilterChainProxy` TRACE tạm thời hoặc marker chỉ ở test, rồi ghi lại chain chọn cho GET/POST/OPTIONS trên cùng endpoint.
8. Thử POST không có CSRF token và POST có CSRF token hợp lệ; phân biệt 403 do `CsrfFilter` với 403 do authorization.
9. Tạo request URI bất thường ở môi trường Servlet lab; nếu firewall từ chối trước matching, xác minh `RequestRejectedException` thay vì suy luận từ việc không có marker.
10. Cấu hình hai `SecurityWebFilterChain` Reactive tương ứng bằng `ServerHttpSecurity.securityMatcher(...)` và `authorizeExchange(...)`. Dùng WebTestClient xác minh API khác form login.
11. Kiểm tra một trường hợp proxy rewrite prefix `/gateway/api/...` thành `/api/...`. Ghi request path ở từng tầng và xác nhận matcher được dùng.
12. Nếu có Actuator trên management port riêng, xác định route thực tế, context và chain của nó. Không suy từ chain ở main application.
13. Viết bảng kết quả nêu: method/path, environment, chain mong muốn, chain quan sát, filter/handler từ chối, HTTP status và biện pháp sửa.

### Câu hỏi tự đánh giá

1. Spring Security Servlet xử lý nhiều `SecurityFilterChain` theo cơ chế nào khi hai chain đều match cùng request?
2. Tại sao `@Order(1)` của một chain không có `securityMatcher` có thể khiến `@Order(2)` không bao giờ được chọn?
3. Khác biệt giữa `http.securityMatcher("/api/**")` và `requestMatchers("/api/**").authenticated()` là gì?
4. Rule `anyRequest().denyAll()` trong API chain có bảo vệ URL ngoài phạm vi của chain đó không?
5. Vì sao `permitAll()` không tương đương `web.ignoring()`?
6. Khi không tìm thấy filter chain ở log, cần xem những nguyên nhân nào trước khi kết luận không có chain match?
7. Tại sao 302 đến `/login` chỉ là dấu hiệu gợi ý form-login chain chứ không phải bằng chứng chắc chắn?
8. Một GET và POST cùng đường dẫn có nhất thiết chọn cùng chain không?
9. Vì sao OPTIONS CORS preflight phải được kiểm tra riêng?
10. HTTP firewall có thể từ chối request trước khi một marker gắn trong chain được chạy không?
11. Các thành phần Reactive tương ứng với `FilterChainProxy`, `SecurityFilterChain` và `HttpSecurity` là gì?
12. Vì sao một test WebTestClient mock web environment có thể không tái hiện lỗi proxy/URL parsing của Netty production?
13. Khi route Actuator ở management port riêng, có thể dùng một matcher của chain main app để suy luận kết quả không?
14. Chỉ nhìn danh sách bean chains có xác nhận chain nào đã xử lý request cụ thể chưa?
15. Một 403 do method-level `@PreAuthorize` có tự chứng minh HTTP security chain chọn sai không?
16. Làm sao bảo đảm sau khi sửa thứ tự chain, route khác không bị giảm bảo vệ CSP, CSRF, CORS, HSTS và session?

## 25. Bảng kiểm ngắn cho người trực sự cố

| Câu hỏi | Bằng chứng nên có |
|---|---|
| Request thật tới Spring chưa? | Correlation ID và log gateway/container/app |
| Đang dùng Servlet hay WebFlux? | Web application type và filter infrastructure |
| Bean chains thực tế gồm những gì? | Danh sách chain, `@Order` và matcher trong runtime |
| Chain đầu tiên khớp request nào? | TRACE/matcher observation hoặc test-only marker |
| Path/method nào Spring thật sự nhận? | Request URI, context/servlet path hoặc exchange path, proxy rewrite |
| Request có bị firewall từ chối trước matching? | Rejection exception/handler hoặc server logs |
| Rule nào trong chain được dùng? | Authorization matcher, role/authority và order |
| CSRF/CORS có từ chối trước authorization? | CSRF/CORS logs, preflight và token test |
| Vì sao 401, 403, 302 hoặc thiếu headers? | Entry point, denied handler, filters và proxy response |
| Sau sửa có hồi quy không? | Test nhiều method, API/UI/public/admin, origin và public path |

## 26. Ghi nhớ

**Muốn chẩn đoán đúng một endpoint trong Spring Security, hãy tìm chain thực sự được chọn trước khi đọc rule authorization.** Trên Servlet, `FilterChainProxy` xét các `SecurityFilterChain` theo thứ tự; chain **đầu tiên** match sẽ xử lý request. Trên Reactive/WebFlux, `WebFilterChainProxy` chọn `SecurityWebFilterChain` theo nguyên tắc tương ứng. `securityMatcher` giới hạn **phạm vi toàn chain**, còn `requestMatchers`/`pathMatchers` trong authorization chỉ kiểm soát quyền **bên trong chain đã chọn**.

Hãy ưu tiên chain đặc thù trước chain fallback, kiểm tra `@Order`, context path, proxy rewrite và method; phân biệt `permitAll()` với `web.ignoring()`. Dùng log có chọn lọc, marker chỉ trong test và các ca MockMvc/WebTestClient để có chứng cứ. Sau khi tìm chain, mới điều tra authentication, authorization, CSRF, CORS, header hoặc method security. Trong mô-đun `SPRING_SECURITY_HTTP_PROTECTION`, mục tiêu là sửa đúng lớp mà vẫn giữ các phòng vệ HTTP khác — security headers, CSP, HSTS, HTTP firewall và bảo vệ session — hoạt động đúng thiết kế.
