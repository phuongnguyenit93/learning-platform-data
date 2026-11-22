# CorsConfiguration và UrlBasedCorsConfigurationSource cho WebFlux

## 1. Vấn đề cần giải quyết: frontend và API khác origin

Một giao diện người dùng có thể chạy tại `http://localhost:5173` (Vite/React/Vue), còn API Spring WebFlux chạy tại `http://localhost:8080`. Hai URL này **khác origin** vì khác port, dù cùng hostname. Một hệ thống sản xuất có thể dùng `https://app.example.test` cho frontend và `https://api.example.test` cho API; chúng cũng khác origin vì khác host.

Browser áp dụng Same-Origin Policy và cơ chế **Cross-Origin Resource Sharing (CORS)** khi JavaScript gọi API ở origin khác. Nếu server không gửi những CORS response headers phù hợp, trình duyệt có thể chặn JavaScript đọc response hoặc chặn request ở giai đoạn preflight. Một lệnh `curl` không thực thi chính sách CORS của browser nên vẫn có thể đọc được response tương tự. Do đó:

> **CORS là chính sách về quyền truy cập liên-origin của browser, không phải cơ chế đăng nhập, không phải phân quyền nghiệp vụ, và không phải tường lửa chặn mọi HTTP client.**

Trong Spring WebFlux, hai thành phần quan trọng để cấu hình CORS theo đường dẫn là:
- **`CorsConfiguration`** — mô tả những origins, HTTP methods, request headers được chấp nhận; có cho phép browser gửi credentials không; response headers nào được JavaScript đọc; preflight được cache bao lâu.
- **`org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`** — chọn một `CorsConfiguration` dựa trên URL pattern của request Reactive.

Spring Security Reactive tích hợp chính sách này với `ServerHttpSecurity.cors(...)` để xử lý preflight **trước khi** authentication/authorization từ chối request thiếu credentials.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt `origin` và `site`; biết khi nào browser tạo CORS preflight.
2. Hiểu từng trường `allowedOrigins`, `allowedOriginPatterns`, `allowedMethods`, `allowedHeaders`, `exposedHeaders`, `allowCredentials` và `maxAge`.
3. Tạo `UrlBasedCorsConfigurationSource` Reactive, map một hoặc nhiều nhóm route với chính sách khác nhau.
4. Kết nối nguồn cấu hình vào `SecurityWebFilterChain` bằng đúng DSL của WebFlux.
5. Phân biệt CORS preflight, actual request, authentication, authorization và CSRF.
6. Chạy project Java 17+ Spring Boot WebFlux, thử `OPTIONS`, `GET`, `POST`, 200/401/403 và response headers.
7. Viết `WebTestClient` tests cho allowed origin, denied origin, denied method/header, credentials và CSRF.
8. Tránh trộn class CORS của Servlet với Reactive hoặc dùng CORS như một cách thay thế kiểm soát quyền.

## 2. Origin là gì? Khi nào request được coi là cross-origin?

**Origin = scheme + host + port** của URL; đường dẫn và query string không thuộc phép so sánh origin.

| Frontend | API | Cross-origin? | Lý do |
| --- | --- | --- | --- |
| `http://localhost:5173` | `http://localhost:8080` | Có | Port khác |
| `https://app.example.test` | `https://api.example.test` | Có | Host khác |
| `https://api.example.test` | `https://api.example.test/v2` | Không | Cùng scheme/host/port |
| `http://api.example.test` | `https://api.example.test` | Có | Scheme khác |
| `https://app.example.test` | `https://app.example.test:8443` | Có | Port khác |

**Same-origin khác same-site.** Một số subdomains khác origin vẫn có thể được browser coi là same-site trong chính sách `SameSite` cookie. Đừng suy luận từ việc cookie được gửi rằng CORS đã cho phép script đọc response, hoặc từ việc CORS cho phép rằng cookie chắc chắn được browser gửi.

Một cross-origin `fetch` thường có header:

~~~http
GET /api/public HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
~~~

Server có thể trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Vary: Origin
Content-Type: text/plain

public-ok
~~~

Browser dùng `Access-Control-Allow-Origin` để quyết định liệu JavaScript từ origin yêu cầu có được đọc response không. Không cần có `Origin` header ở mọi request: `curl` bình thường có thể không gửi nó, còn same-origin navigation thường không cần CORS.

## 3. Simple request, actual request và CORS preflight

CORS có hai bước xử lý nổi bật:

**Actual request** là request thực hiện nghiệp vụ, ví dụ GET dữ liệu hoặc POST tạo một record. **Preflight request** là một HTTP `OPTIONS` mà browser tự gửi trước một số cross-origin actual requests để hỏi server về quyền sử dụng method và headers dự kiến.

Ví dụ browser muốn thực hiện một POST có `Authorization` và `X-CSRF-TOKEN`:

~~~http
OPTIONS /api/items HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type,x-csrf-token
~~~

Server có thể trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: authorization,content-type,x-csrf-token
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
~~~

Ví dụ này biểu diễn ý nghĩa headers; thứ tự, danh sách method/header và status cụ thể có thể do Spring/bộ xử lý quyết định. Không so sánh nguyên văn toàn header string trong test. Khi preflight hợp lệ, browser có thể tiếp tục gửi **actual POST**, nhưng actual POST **vẫn phải vượt qua** authentication, authorization, CSRF và validation nghiệp vụ.

### 3.1. Dấu hiệu xác định preflight đúng

Một `OPTIONS` bình thường **không tự động là CORS preflight**. Preflight thường có đồng thời:
- HTTP method `OPTIONS`;
- header `Origin`;
- header `Access-Control-Request-Method`;
- có thể có `Access-Control-Request-Headers`.

Chỉ dùng `curl -X OPTIONS /api/items` rồi kết luận CORS hỏng là sai: request ấy thiếu các header cho browser preflight.

### 3.2. Tại sao preflight thường không có credentials?

Theo mô hình CORS của browser, preflight không gửi thông tin xác thực như một actual request đăng nhập; đặc biệt không nên đòi cookie/Basic credentials từ `OPTIONS` preflight để quyết định khả năng được phép. Nếu security kiểm tra authentication trước khi CORS được xử lý, request OPTIONS có thể bị 401/403 và browser không tiếp tục actual request.

Spring Security Reactive hỗ trợ xử lý CORS **trước** các kiểm tra security tương ứng. Cần cấu hình nguồn CORS đúng và tích hợp với `ServerHttpSecurity.cors` hoặc `CorsWebFilter` thích hợp thay vì ép mọi preflight phải vượt qua login.

### 3.3. Những request không có preflight

Một số request đáp ứng điều kiện **CORS-safelisted methods/headers/content types** có thể đi thẳng tới actual request mà không có OPTIONS preflight, ví dụ một số GET và HTML form POST. CORS **không bảo đảm** mọi cross-origin POST đều được chặn trước khi tới server.

Điểm này liên quan CSRF: website tấn công có thể không cần đọc response hay dùng JS để kích hoạt một HTML form. CORS không thay thế CSRF token.

## 4. CorsConfiguration: vai trò và các thuộc tính chính

Class cần dùng cho cả WebFlux lẫn phần cấu hình CORS chung của Spring Framework:

~~~java
import org.springframework.web.cors.CorsConfiguration;
~~~

Một cấu hình explicit, theo danh sách cho phép:

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of(
        "http://localhost:5173",
        "https://app.example.test"));
cors.setAllowedMethods(List.of("GET", "POST"));
cors.setAllowedHeaders(List.of(
        "Authorization", "Content-Type", "X-CSRF-TOKEN"));
cors.setExposedHeaders(List.of("X-Request-ID"));
cors.setAllowCredentials(true);
cors.setMaxAge(1800L);
~~~

Đây là một **snippet** (cần `import java.util.List` và đặt trong method/class), chưa phải nguyên file Java. Phần demo bên dưới sẽ cung cấp ứng dụng chạy được.

| Thuộc tính | Ý nghĩa | Mối nguy khi cấu hình sai |
| --- | --- | --- |
| `allowedOrigins` | Các origin cụ thể được phép | Wildcard rộng hoặc quên scheme/port |
| `allowedOriginPatterns` | Các pattern origin động, có thể gồm wildcard ở host/port | Cho phép subdomain không thuộc vùng tin cậy |
| `allowedMethods` | Những HTTP methods browser được dùng trong CORS context | Cho phép DELETE/PUT không cần thiết |
| `allowedHeaders` | Các request header names được phép ở preflight | Client không gửi được `Authorization`/`X-CSRF-TOKEN` hoặc wildcard quá rộng |
| `exposedHeaders` | Những response header names JS được phép đọc | Lộ metadata không cần thiết hoặc JS không thấy `X-Request-ID` |
| `allowCredentials` | Có cho phép browser credentialed cross-origin access không | Có thể mở quyền đọc dữ liệu theo session nếu origin quá rộng |
| `maxAge` | Thời gian browser có thể cache kết quả preflight, đơn vị giây | Nhầm với token TTL/cookie lifetime hoặc chọn quá dài |

### 4.1. allowedOrigins: phải ghi đúng scheme và port

`http://localhost:5173` khác `http://localhost:3000` và khác `https://localhost:5173`. CORS policy nên khai báo rõ frontend origins của từng môi trường. Không tự lấy header `Origin` từ client rồi phản chiếu vào `Access-Control-Allow-Origin` mà **không kiểm tra allowlist**.

Ví dụ:

~~~java
cors.setAllowedOrigins(List.of(
        "https://app.example.test",
        "https://admin.example.test"));
~~~

Cả hai origins phải được tổ chức kiểm soát và có mục đích sử dụng phù hợp. CORS không xác minh danh tính của script hay người dùng; nó chỉ xem origin có được phép đọc/gọi response theo browser CORS mechanism.

### 4.2. allowedOriginPatterns cho origin động

Khi cần cho phép một nhóm subdomains được kiểm soát, Spring Framework có:

~~~java
cors.setAllowedOriginPatterns(List.of(
        "https://*.trusted.example.test"));
~~~

So với `allowedOrigins`, pattern có thể match nhiều host hơn. Khi `allowCredentials=true`, pattern là một lựa chọn được hỗ trợ vì response có thể phản ánh **origin đã match cụ thể**, không phải wildcard `*` ở `Access-Control-Allow-Origin`.

**Nhưng “được framework hỗ trợ” không có nghĩa “an toàn mặc định”.** Nếu attacker có thể tạo subdomain trên `trusted.example.test`, họ có thể trở thành một origin được phép. Chỉ dùng pattern khi quản lý DNS, hosting, tenant isolation và cơ chế cấp subdomain thực sự đủ chặt.

### 4.3. allowedMethods khác authorization rule

~~~java
cors.setAllowedMethods(List.of("GET", "POST"));
~~~

Nghĩa là frontend thuộc origin được phép có thể dùng method GET/POST theo CORS protocol. **Không** nghĩa API cho anonymous POST, không có role, hoặc không cần CSRF token. CORS quyết định quyền giao tiếp từ browser; authorization của `SecurityWebFilterChain` quyết định danh tính/authority có được gọi route hay không.

Khi đổi API sang PUT/PATCH, phải xem cả CORS allowed methods **và** security authorization/CSRF rules; thiếu bất cứ lớp nào, browser có thể báo lỗi.

### 4.4. allowedHeaders khác exposedHeaders

`allowedHeaders` nói **client được gửi những request headers nào** trong CORS preflight, như `Authorization`, `Content-Type`, `X-CSRF-TOKEN`.

`exposedHeaders` nói **JavaScript được đọc những response headers nào** ngoài nhóm safelisted response headers. Ví dụ API trả `X-Request-ID` để debug:

~~~java
cors.setExposedHeaders(List.of("X-Request-ID"));
~~~

Nếu client muốn đọc `X-Request-ID` bằng `response.headers.get("X-Request-ID")`, response cần `Access-Control-Expose-Headers` phù hợp. Không đưa token/session ID hay thông tin bí mật vào response header chỉ vì có thể expose nó qua CORS.

### 4.5. allowCredentials và wildcard origin

Khi:

~~~java
cors.setAllowCredentials(true);
~~~

browser có thể chấp nhận credentialed cross-origin response nếu các chính sách CORS khác phù hợp. Nhưng:
- Frontend vẫn phải dùng `fetch(..., {credentials:"include"})` khi cần cookies/credentials ở một request cross-origin; không phải mọi credentials đều xuất hiện tự động.
- Browser còn áp dụng SameSite, Secure, third-party cookie policy, authentication cache và các quy tắc riêng.
- API vẫn phải xác thực đúng credentials và kiểm tra phân quyền.
- Response cần `Access-Control-Allow-Credentials: true` theo điều kiện phù hợp.
- **`Access-Control-Allow-Origin: *` không được dùng với credentialed requests.**

Cấu hình dưới đây **không hợp lệ** cho credentials:

~~~java
// SAI: wildcard origin và credentials.
cors.setAllowedOrigins(List.of("*"));
cors.setAllowCredentials(true);
~~~

Spring Framework có `CorsConfiguration.validateAllowCredentials()` để kiểm tra trường hợp này và có thể ném `IllegalArgumentException` trong quá trình xử lý. Thay bằng origins cụ thể:

~~~java
cors.setAllowedOrigins(List.of("https://app.example.test"));
cors.setAllowCredentials(true);
~~~

Không dùng `allowedOriginPatterns(List.of("*"))` để “lách” quy tắc này. Dù framework có thể phản chiếu origin cụ thể đã match, một pattern quá rộng vẫn cho origin không đáng tin đọc dữ liệu của user khi browser gửi credentials.

### 4.6. maxAge là bộ nhớ đệm cho preflight

~~~java
cors.setMaxAge(1800L);
~~~

Tức `Access-Control-Max-Age` khoảng **1.800 giây** (30 phút), để browser có thể cache quyết định preflight theo quy tắc browser. Đây **không phải**:
- thời hạn session cookie;
- thời hạn JWT hoặc refresh token;
- timeout của WebSession;
- cache TTL của response body;
- thời gian “được phép đăng nhập”.

Browser có thể áp dụng giới hạn riêng thấp hơn hoặc bỏ cache trong một số điều kiện. Khi thay CORS policy, vẫn phải deploy/config đúng và không chỉ trông chờ client hết cache.

## 5. Default của CorsConfiguration: đừng nhầm với applyPermitDefaultValues

Một đối tượng mới tạo:

~~~java
CorsConfiguration config = new CorsConfiguration();
~~~

**Không mặc nhiên cho phép mọi origin**. Nếu bạn không cấu hình, `CorsConfiguration` mặc định không cho phép cross-origin requests.

Có method:

~~~java
config.applyPermitDefaultValues();
~~~

Nó áp những giá trị “mở tiện lợi” cho các field chưa set, gồm:
- `allowedOrigins=["*"]` nếu chưa có origin/origin patterns;
- các HTTP methods GET, HEAD, POST;
- `allowedHeaders=["*"]`;
- `maxAge=1800` giây.

Đây là giá trị mặc định có chủ đích của **method này**, khác với một `new CorsConfiguration()` rỗng. Nếu đồng thời muốn `allowCredentials=true` mà không thay wildcard origins, cấu hình có thể trở nên không hợp lệ.

**Khuyến nghị:** viết một cấu hình allowlist rõ ràng, không gọi `applyPermitDefaultValues()` theo thói quen trong API cần giới hạn quyền cross-origin. CORS defaults ở mức `WebFluxConfigurer.addCorsMappings` hay `@CrossOrigin` có thể khác do framework chủ động áp giá trị mặc định khi đăng ký; không đánh đồng các ngữ cảnh.

## 6. UrlBasedCorsConfigurationSource: map chính sách theo URL

Đối với WebFlux, dùng **đúng package Reactive**:

~~~java
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
~~~

`UrlBasedCorsConfigurationSource` implements `CorsConfigurationSource`; method quan trọng:

~~~java
// Chữ ký minh họa; không phải class Java hoàn chỉnh.
void registerCorsConfiguration(String path, CorsConfiguration config);
CorsConfiguration getCorsConfiguration(ServerWebExchange exchange);
~~~

Ví dụ:

~~~java
UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();

source.registerCorsConfiguration("/api/**", apiCors);
source.registerCorsConfiguration("/public/**", publicCors);
~~~

Nghĩa là một request đi qua CORS processing sẽ chọn cấu hình phù hợp dựa trên **path pattern của request WebFlux**, không phải dựa vào role hay tên controller. Method, headers và origin tiếp tục được xác minh dựa trên `CorsConfiguration` đã chọn.

### 6.1. Source không phải filter

Bản thân `UrlBasedCorsConfigurationSource` chỉ **cung cấp config**. Nó không tự chặn request và không tự thêm HTTP headers. Một thành phần CORS processor/filter cần sử dụng nguồn này, ví dụ:
- `ServerHttpSecurity.cors(cors -> cors.configurationSource(source))`: tích hợp CORS với Spring Security Reactive.
- `CorsWebFilter` của Spring Framework: một WebFilter Reactive được đăng ký dùng source.

**Không tạo cả hai cách một cách vô thức** dẫn tới nhiều filter CORS cùng xử lý request. Chọn **một cơ chế chủ sở hữu CORS** và test response headers/preflight thực tế.

### 6.2. Dùng route-specific policy

Ví dụ muốn một API báo cáo nhạy cảm chỉ cho frontend quản trị:

~~~java
CorsConfiguration adminCors = new CorsConfiguration();
adminCors.setAllowedOrigins(List.of("https://admin.example.test"));
adminCors.setAllowedMethods(List.of("GET"));
adminCors.setAllowedHeaders(List.of("Authorization"));
adminCors.setAllowCredentials(true);

CorsConfiguration publicCors = new CorsConfiguration();
publicCors.setAllowedOrigins(List.of("https://app.example.test"));
publicCors.setAllowedMethods(List.of("GET"));
publicCors.setAllowedHeaders(List.of("Content-Type"));
publicCors.setAllowCredentials(false);

UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
source.registerCorsConfiguration("/api/admin/**", adminCors);
source.registerCorsConfiguration("/api/public/**", publicCors);
~~~

Đây là snippet cấu hình, cần đặt trong một method và imports. Các URL patterns phải **đúng với path mà WebFlux nhìn thấy sau reverse proxy/context-path rewrite**. Đừng dùng một pattern `/**` rộng hơn yêu cầu chỉ để “cho frontend chạy”.

### 6.3. Không có mapping cho path thì sao?

Nếu một preflight đi tới URL không có CORS config phù hợp, CORS processor có thể **từ chối preflight**; với actual cross-origin request không có cấu hình, browser thường không có header `Access-Control-Allow-Origin` phù hợp nên không cho script đọc response. Hành vi cụ thể còn phụ thuộc cách filter/handler được cấu hình.

Điều này **khác** với `anyExchange().denyAll()` của authorization:
- CORS config chọn theo path cho **browser cross-origin access**.
- Security authorization chọn theo path, method và authentication/authorities cho **quyền API**.
- WebFlux HandlerMapping quyết định route/controller tồn tại hay không.

Một URL không có CORS mapping vẫn có thể được `curl` gọi trực tiếp nếu security cho phép. CORS không phải giải pháp chặn access ngoài browser.

## 7. Spring Security Reactive: CORS phải xử lý trước authentication

Spring Security nói rõ: **preflight phải được xử lý trước Spring Security authentication**, vì preflight không có credentials/session cookie theo cách của actual request. Nếu ngược lại, security có thể coi nó là anonymous và trả 401 trước khi browser biết server có cho phép request hay không.

Cách phù hợp với Spring Security 6.x WebFlux:

~~~java
return http
        .cors(cors -> cors.configurationSource(source))
        .authorizeExchange(ex -> ex
                .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
~~~

Đây là snippet trong method tạo `SecurityWebFilterChain`, với `source` là reactive `CorsConfigurationSource` đã tạo. Theo Javadoc của `ServerHttpSecurity.CorsSpec`, `configurationSource` nhận đúng `org.springframework.web.cors.reactive.CorsConfigurationSource` và tích hợp `CorsWebFilter` vào đúng thứ tự.

Nếu đã khai báo **một bean** nguồn CORS được Spring Security nhận diện, `.cors(Customizer.withDefaults())` có thể tự dùng nó; nhưng cấu hình tường minh `configurationSource(source)` giúp người học tránh nhập nhằng khi nhiều bean/chain hoặc có cấu hình khác.

### 7.1. Sai lầm dùng CorsFilter của Servlet

**Sai với WebFlux**:

~~~java
// Các class sau là Servlet/MVC, KHÔNG dùng trong ví dụ WebFlux:
org.springframework.web.filter.CorsFilter
org.springframework.web.cors.UrlBasedCorsConfigurationSource
org.springframework.web.cors.CorsConfigurationSource
~~~

**Đúng với Reactive**:

~~~java
org.springframework.web.cors.reactive.CorsWebFilter
org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource
org.springframework.web.cors.reactive.CorsConfigurationSource
org.springframework.web.cors.CorsConfiguration
~~~

Có hai class `UrlBasedCorsConfigurationSource` trùng simple name ở hai package. IDE auto-import sai có thể gây lỗi compile hoặc không tương thích với `ServerHttpSecurity.CorsSpec.configurationSource`. Hãy kiểm tra đầy đủ package của từng import.

### 7.2. Vì sao không “permitAll OPTIONS /**” là đủ?

~~~java
// Không phải giải pháp CORS đầy đủ.
.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

Rule này chỉ thay đổi **authorization** cho OPTIONS. Nó **không tự tạo** `Access-Control-Allow-Origin`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Methods` và cũng không xác minh allowed origins. Nếu server không trả CORS headers đúng, browser vẫn có thể từ chối request.

Không mở mọi OPTIONS chỉ để chữa lỗi thiếu `CorsWebFilter`. Hãy cấu hình CORS integration và kiểm thử preflight có đủ Origin/requested method/requested headers.

### 7.3. CSRF không bị CORS tự tắt

Kể cả khi một cross-origin preflight POST được chấp thuận, **actual POST vẫn có thể nhận 403** do CSRF token thiếu/sai. Điều này đúng với browser sử dụng cookie login, Basic credentials cache hoặc các cơ chế ambient authentication khác.

Hai lớp khác nhau:

~~~text
OPTIONS preflight
   |
   +--> Origin/method/headers được CORS cho phép?
         |
         +--> Không --> browser không phát actual request hợp lệ
         |
         +--> Có ----> Browser gửi actual POST
                        |
                        +--> Authentication hợp lệ?
                        +--> CSRF token hợp lệ nếu cần?
                        +--> Authorization đủ quyền?
                        +--> Business request hợp lệ?
~~~

CORS là **chính sách khả năng giao tiếp từ origin**, còn CSRF là **chống giả mạo thao tác thay đổi trạng thái**. Đừng tắt `csrf()` chỉ vì preflight đã thành công.

## 8. Ba cách cấu hình CORS trong WebFlux: chọn một chủ sở hữu rõ ràng

Spring Framework có nhiều API cho CORS:

| Cách | Dùng ở đâu? | Ghi chú |
| --- | --- | --- |
| `CorsConfiguration` + reactive `UrlBasedCorsConfigurationSource` + `ServerHttpSecurity.cors` | Ứng dụng Spring Security Reactive | **Lựa chọn của ví dụ chính**; source explicit, filter đúng thứ tự trong security chain |
| `CorsWebFilter(source)` bean | Spring WebFlux, functional routing hoặc muốn filter độc lập | Cần xem tương tác với Spring Security để tránh duplicate filter |
| `WebFluxConfigurer.addCorsMappings(CorsRegistry)` | Global HandlerMapping configuration | Tốt cho ứng dụng không cần filter riêng; xem thứ tự với Security |
| `@CrossOrigin` | Từng controller/class/handler | Thuận tiện cho một số route, nhưng khó kiểm soát policy tập trung khi lan rộng |

### 8.1. @CrossOrigin và global CORS có thể kết hợp

Ở tầng WebFlux HandlerMapping, cấu hình CORS toàn cục và `@CrossOrigin` có thể được kết hợp: các danh sách như origins/headers/methods thường được cộng, còn những field đơn giá trị như `allowCredentials` hoặc `maxAge` có quy tắc override.

**Rủi ro:** một annotation `@CrossOrigin(origins="*")` trên controller có thể mở rộng origin ngoài ý muốn. Khi đã dùng `CorsWebFilter`/Security CORS source làm lớp xử lý đầu tiên, **đừng giả định** CORS ở HandlerMapping và filter luôn tự kết hợp như bạn mong đợi. Kiểm thử actual response theo route.

### 8.2. Ví dụ CorsWebFilter độc lập (không dùng đồng thời với cấu hình chính)

~~~java
// Snippet alternative; không thêm bean này trong demo chính.
@Bean
CorsWebFilter corsWebFilter(
        UrlBasedCorsConfigurationSource source) {
    return new CorsWebFilter(source);
}
~~~

Import `org.springframework.web.cors.reactive.CorsWebFilter`. Nếu chọn cách này, xác định ai xử lý `OPTIONS` trước authentication trong security chain, cấu hình thứ tự filter và tránh tạo duplicate CORS processing. Khi Spring Security đã cung cấp `cors(configurationSource(source))`, không cần thêm bean trên.

## 9. Project runnable: Java 17 + WebFlux + CORS source + Security

Chúng ta sẽ xây một project tối giản nhưng có đủ:
- Frontend origin demo `http://localhost:5173` và frontend production giả định `https://app.example.test`.
- CORS áp dụng cho `/api/**`, không cho origin khác.
- Methods `GET` và `POST`, headers `Authorization`, `Content-Type` và `X-CSRF-TOKEN`.
- `allowCredentials=true` với origins được liệt kê chính xác.
- Expose `X-Request-ID`.
- Cho phép GET public; GET private và POST items đòi HTTP Basic; POST items còn cần CSRF.
- Endpoint `GET /api/csrf` để quan sát token/cookie CSRF của Spring Security WebFlux.
- Kiểm thử preflight, actual request, credentials và CSRF độc lập.

**Lưu ý:** Basic user/password hard-code và `{noop}` chỉ phục vụ local demo. Mọi sản phẩm thật cần HTTPS, PasswordEncoder an toàn, authentication theo yêu cầu, phân quyền theo domain và logging không làm lộ secrets.

### 9.1. Cấu trúc

~~~text
webflux-cors-source/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── DemoApplication.java
    │   ├── SecurityConfig.java
    │   └── ApiController.java
    └── test/java/demo/
        └── CorsSecurityTest.java
~~~

### 9.2. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-cors-source'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Cần JDK 17 và Gradle tương thích. Nếu dự án có Gradle Wrapper, sử dụng `./gradlew` hoặc `gradlew.bat`. Spring Boot BOM điều phối version Spring Framework, Spring Security và Reactor tương thích. Bản `3.5.7` là ví dụ cấu hình cố định; production cần theo nhánh được hỗ trợ và các bản vá bảo mật mới của tổ chức.

### 9.3. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.4. SecurityConfig.java — nơi kết hợp đúng CorsConfiguration và reactive source

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(List.of(
                "http://localhost:5173",
                "https://app.example.test"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-CSRF-TOKEN"));
        cors.setExposedHeaders(List.of("X-Request-ID"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityFilterChain(
            ServerHttpSecurity http,
            UrlBasedCorsConfigurationSource corsConfigurationSource) {
        return http
                .cors(cors -> cors.configurationSource(
                        corsConfigurationSource))
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/api/public")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/private")
                                .authenticated()
                        .pathMatchers(HttpMethod.GET, "/api/csrf")
                                .authenticated()
                        .pathMatchers(HttpMethod.GET, "/api/items")
                                .authenticated()
                        .pathMatchers(HttpMethod.POST, "/api/items")
                                .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .csrf(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails user = User.withUsername("learner")
                .password("{noop}localpass")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(user);
    }
}
~~~

Đọc cấu hình theo từng quyết định:

1. `new CorsConfiguration()` không tự mở wildcard origin; từng field được đặt tường minh.
2. `allowedOrigins` chỉ có hai origins giả định đã phê duyệt. Port `5173` là thành phần của origin local.
3. `setAllowedMethods` cho GET/POST. Không có PUT/DELETE trong chính sách CORS.
4. `allowedHeaders` gồm Authorization và CSRF header để actual POST có thể vượt qua preflight.
5. `exposedHeaders` cho JS đọc `X-Request-ID` do một endpoint trả về.
6. `allowCredentials(true)` chỉ hợp lệ với origins cụ thể, không dùng `*`.
7. `registerCorsConfiguration("/api/**", cors)` chỉ áp policy cho namespace API; không tự bật CORS cho mọi route khác.
8. `http.cors(cors -> cors.configurationSource(...))` yêu cầu Spring Security xử lý CORS đúng vị trí; không cần tự thêm `CorsWebFilter` bean.
9. `authorizeExchange` là **security policy độc lập**: public, authenticated, deny mặc định.
10. `csrf(Customizer.withDefaults())` giữ bảo vệ mặc định cho POST; **CORS allowed POST không xóa CSRF**.

**Bảo mật production:** hai origins trong bài là giả lập/localhost. Khi triển khai, cấu hình allowlist theo môi trường, không có demo user/password, dùng HTTPS và token/password policy thực tế. Không cho phép arbitrary origins với credentials.

### 9.5. ApiController.java

`src/main/java/demo/ApiController.java`:

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    private final AtomicReference<String> item =
            new AtomicReference<>("initial");

    @GetMapping(path = "/api/public",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicData() {
        return Mono.just("public-ok");
    }

    @GetMapping(path = "/api/private",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<ResponseEntity<String>> privateData() {
        return Mono.just(ResponseEntity.ok()
                .header("X-Request-ID", "demo-request-1")
                .body("private-ok"));
    }

    @GetMapping("/api/csrf")
    public Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
                exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF token attribute is unavailable"));
        }

        return token.map(t -> Map.of(
                "headerName", t.getHeaderName(),
                "token", t.getToken()));
    }

    @GetMapping(path = "/api/items",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> readItem() {
        return Mono.fromSupplier(item::get);
    }

    @PostMapping(path = "/api/items",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> saveItem(@RequestBody Mono<String> body) {
        return body.map(text -> {
            item.set(text);
            return "saved:" + text;
        });
    }
}
~~~

Ý nghĩa:
- Public GET minh họa CORS cho một endpoint không yêu cầu login.
- Private GET yêu cầu Basic và trả `X-Request-ID` để minh họa `exposedHeaders`; giá trị ID là hằng demo, không chứa thông tin nhạy cảm.
- `/api/csrf` dùng `Mono<CsrfToken>` mà `CsrfWebFilter` cung cấp; client gửi giá trị token được request handler trình bày, không tự unmask raw session token.
- POST thay đổi `AtomicReference`, phải vượt cả CORS, Basic, CSRF. Dữ liệu chỉ nằm trong bộ nhớ tiến trình, không phải persistence production.
- Không có `block()` hay `subscribe()` thủ công trong WebFlux controller.

## 10. Chạy curl để thấy preflight hoạt động

Trong thư mục chứa `build.gradle`:

~~~bash
gradle bootRun
~~~

Nếu có Wrapper, dùng `./gradlew bootRun`. Server nghe `http://localhost:8080` mặc định; HTTP chỉ dành cho localhost demo.

### 10.1. Preflight từ origin được phép

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/items \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type,x-csrf-token'
~~~

Kỳ vọng: preflight được CORS processor chấp nhận, thường **HTTP 200 OK**, cùng các header thể hiện:
- `Access-Control-Allow-Origin: http://localhost:5173`;
- `Access-Control-Allow-Methods` có POST;
- `Access-Control-Allow-Headers` cho những header đã yêu cầu;
- `Access-Control-Allow-Credentials: true`;
- `Access-Control-Max-Age: 1800`;
- `Vary` tương ứng.

**Không cần** gửi `-u learner:localpass` trong preflight. Nếu OPTIONS chỉ được 401 vì thiếu Basic, kiểm tra CORS integration/filter order; đừng sửa bằng cách đính Authorization header vào OPTIONS giả lập mà vẫn bỏ qua browser behavior.

### 10.2. Preflight từ origin không được phép

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/items \
  -H 'Origin: https://untrusted.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
~~~

Kỳ vọng: CORS processor **từ chối**, thường trả **403 Forbidden** hoặc response không thỏa điều kiện để browser tiếp tục. Không được có `Access-Control-Allow-Origin: https://untrusted.example.test` khi origin ấy không thuộc policy.

### 10.3. Preflight method không được cho phép

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/items \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: DELETE' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

Dù origin hợp lệ, DELETE không nằm trong `allowedMethods`, nên preflight bị từ chối. Đây là **quy tắc CORS**, không chứng minh Security authorization của DELETE vì request chưa đi tới actual DELETE.

### 10.4. Preflight header không được cho phép

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/items \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: x-not-approved'
~~~

Kỳ vọng bị từ chối vì `x-not-approved` không có trong `allowedHeaders`. Đừng thêm `*` vội; xem frontend có thực sự cần header đó không, và nó có thể gây lộ/đổi trạng thái gì.

### 10.5. Actual GET từ origin hợp lệ

~~~bash
curl -i http://localhost:8080/api/public \
  -H 'Origin: http://localhost:5173'
~~~

Kỳ vọng **200** với body `public-ok` và `Access-Control-Allow-Origin` đúng. Nếu chạy trực tiếp `curl` không có Origin, vẫn có thể nhận 200 nhưng response không cần CORS headers — đó không phải lỗi CORS.

### 10.6. Actual GET có Basic authentication

~~~bash
# Thiếu credentials: auth bị từ chối (thường 401),
# nhưng allowed origin vẫn được CORS xử lý.
curl -i http://localhost:8080/api/private \
  -H 'Origin: http://localhost:5173'

# Có credentials demo đúng.
curl -i -u learner:localpass \
  http://localhost:8080/api/private \
  -H 'Origin: http://localhost:5173'
~~~

GET private không có Basic thường **401**; có Basic đúng thường **200** với `private-ok`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials` và `Access-Control-Expose-Headers: X-Request-ID`. Browser sẽ chỉ cho JS đọc header ngoài safelist như `X-Request-ID` nếu được expose.

### 10.7. CORS cho phép POST nhưng CSRF vẫn có thể trả 403

~~~bash
curl -i -u learner:localpass \
  http://localhost:8080/api/items \
  -H 'Origin: http://localhost:5173' \
  -H 'Content-Type: text/plain' \
  --data 'without-csrf'
~~~

Nếu thiếu CSRF token, Spring Security có thể trả **403 Forbidden**, mặc dù CORS đã cho phép origin/method/header. Đây không phải dấu hiệu cấu hình CORS sai; cần tách tầng CORS khỏi CSRF.

### 10.8. Lấy CSRF token để POST hợp lệ

Với `curl` và `jq` ở môi trường shell kiểu Bash:

~~~bash
# Lấy token và lưu cookie WebSession.
curl -sS -u learner:localpass \
  -c csrf-cookies.txt \
  -H 'Origin: http://localhost:5173' \
  http://localhost:8080/api/csrf > csrf.json

HEADER="$(jq -r '.headerName' csrf.json)"
TOKEN="$(jq -r '.token' csrf.json)"

# Gửi cùng Basic + WebSession cookie + CSRF token.
curl -i -u learner:localpass \
  -b csrf-cookies.txt \
  -H 'Origin: http://localhost:5173' \
  -H "$HEADER: $TOKEN" \
  -H 'Content-Type: text/plain' \
  --data 'with-csrf' \
  http://localhost:8080/api/items

curl -i -u learner:localpass \
  http://localhost:8080/api/items
~~~

Khi cookie và token đúng cùng phiên, kỳ vọng:

~~~text
POST /api/items -> HTTP 200; body: saved:with-csrf
GET  /api/items -> HTTP 200; body: with-csrf
~~~

Browser còn cần vận hành `credentials` mode/SameSite/CORS đúng; các lệnh `curl` bỏ qua nhiều chính sách trình duyệt nhưng hữu ích để thấy server trả header đúng.

Không log token, cookie, mật khẩu thật hoặc dán chúng vào công cụ chia sẻ. File `csrf.json` và `csrf-cookies.txt` chỉ để chạy local và không được commit lên repository thực.

## 11. WebTestClient: kiểm thử đúng CORS source và Spring Security

Thêm `spring-boot-starter-test`, `spring-security-test` như `build.gradle` ở trên. `WebTestClient` có thể tạo request với `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` và xác minh response status/headers. Với integration security, áp `springSecurity()`.

`src/test/java/demo/CorsSecurityTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class CorsSecurityTest {

    private static final String ALLOWED = "http://localhost:5173";
    private static final String DENIED = "https://untrusted.example.test";

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void permittedPreflightWorksWithoutAuthentication() {
        client.options().uri("/api/items")
                .header("Origin", ALLOWED)
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                        "authorization,content-type,x-csrf-token")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Origin", ALLOWED)
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Credentials", "true");
    }

    @Test
    void unknownOriginPreflightIsForbidden() {
        client.options().uri("/api/items")
                .header("Origin", DENIED)
                .header("Access-Control-Request-Method", "POST")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void unknownMethodPreflightIsForbidden() {
        client.options().uri("/api/items")
                .header("Origin", ALLOWED)
                .header("Access-Control-Request-Method", "DELETE")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void unknownHeaderPreflightIsForbidden() {
        client.options().uri("/api/items")
                .header("Origin", ALLOWED)
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "x-not-approved")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void allowedOriginCanReadPublicResponse() {
        client.get().uri("/api/public")
                .header("Origin", ALLOWED)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Origin", ALLOWED)
                .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void privateRouteWithoutCredentialsIs401() {
        client.get().uri("/api/private")
                .header("Origin", ALLOWED)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void allowedOriginWithBasicCanReadPrivateData() {
        client.get().uri("/api/private")
                .header("Origin", ALLOWED)
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Access-Control-Allow-Origin", ALLOWED)
                .expectHeader().valueEquals(
                        "Access-Control-Expose-Headers", "X-Request-ID")
                .expectBody(String.class).isEqualTo("private-ok");
    }

    @Test
    void disallowedOriginCannotUseActualCorsRequest() {
        client.get().uri("/api/public")
                .header("Origin", DENIED)
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void actualPostWithoutCsrfIs403EvenWhenCorsAllowsIt() {
        client.post().uri("/api/items")
                .header("Origin", ALLOWED)
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("not-allowed")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void postWithBasicAndCsrfPasses() {
        client.mutateWith(csrf())
                .post().uri("/api/items")
                .header("Origin", ALLOWED)
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("allowed")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("saved:allowed");
    }

    @Test
    void sameOriginStyleRequestStillNeedsAuthentication() {
        // Không có Origin: CORS không phải authentication.
        client.get().uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**Kỳ vọng:** 11 tests phản ánh đúng những ca 200/401/403 trong chính sách ví dụ. Đây là phân tích dựa trên API, **không khẳng định đã chạy Gradle trong môi trường này**. Body của lỗi 403 có thể khác theo Spring Security version; tests nên kiểm tra status và những headers quan trọng hơn là toàn bộ error page.

### 11.1. Vì sao test OPTIONS không cấp credentials?

Đó là một đặc tính cần test: **preflight được xử lý trước authentication** và policy dựa vào Origin, requested method, requested headers, không phải vào role của user. Request actual đến sau sẽ được xác thực riêng.

### 11.2. Vì sao test POST 403 có Basic đúng?

Bởi Spring Security CSRF mặc định vẫn chặn một POST thiếu CSRF token. Test `csrf()` giúp chứng minh rằng khi có token hợp lệ, CORS + authentication + route handling có thể hoạt động. Nó không phải một cơ chế vượt CSRF trong môi trường thật.

### 11.3. Tại sao test không thay browser thật?

`WebTestClient` phát HTTP requests tới WebFlux và kiểm tra response; nó **không mô phỏng mọi quyết định browser** như cookie third-party, SameSite, credential cache hay preflight caching. Hãy bổ sung E2E test bằng các browser đang hỗ trợ và kiểm tra Network tab để xác nhận actual frontend có thể chạy.

## 12. Ví dụ JavaScript từ frontend

Đây là snippet mô tả luồng fetch từ origin `http://localhost:5173` tới WebFlux API `http://localhost:8080`:

~~~javascript
const API = "http://localhost:8080";

// Trường hợp GET public: không cần credentials.
const publicResponse = await fetch(API + "/api/public");
if (!publicResponse.ok) throw new Error("Public API rejected");
console.log(await publicResponse.text());

// Trường hợp GET protected: giả định browser đã có
// credentials/session hợp lệ theo phương thức login của ứng dụng.
const privateResponse = await fetch(API + "/api/private", {
  credentials: "include"
});
if (!privateResponse.ok) throw new Error("Authentication required");
console.log(privateResponse.headers.get("X-Request-ID"));

// Trường hợp POST protected: token cần được cấp từ API trong
// cùng ngữ cảnh session. Phần lấy Basic credentials phụ thuộc
// cách login thực tế và không được hard-code trong frontend.
const csrfResponse = await fetch(API + "/api/csrf", {
  credentials: "include"
});
if (!csrfResponse.ok) throw new Error("CSRF token unavailable");
const csrf = await csrfResponse.json();

const saveResponse = await fetch(API + "/api/items", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "text/plain",
    [csrf.headerName]: csrf.token
  },
  body: "new-value"
});
if (!saveResponse.ok) throw new Error("Update rejected");
~~~

**Đây không phải frontend hoàn chỉnh**; nó giả định browser đã có Basic credentials phù hợp hoặc một phương thức login đã được tích hợp. `credentials:"include"` không tự tạo username/password mà browser chưa có. Để chạy demo dễ dàng, dùng `curl -u` để kiểm chứng server-side và dùng frontend test thật khi đã thiết kế authentication flow.

Với cookies, browser còn xét `SameSite`, `Secure` và các chính sách chặn third-party cookies. CORS allowed credentials **chỉ cho phép browser tiếp nhận response có credentials trong điều kiện phù hợp**, không ép browser gửi bất kỳ cookie nào.

## 13. CORS + CSRF + SameSite + Authorization: không thay thế nhau

Một thiết kế tốt tách bốn câu hỏi:

| Kiểm soát | Câu hỏi nó xử lý | Không đảm bảo |
| --- | --- | --- |
| CORS | Script từ origin A có được đọc/giao tiếp với response của B theo browser không? | User là ai, có quyền gì, request có chủ ý |
| Authentication | Credentials có xác minh được danh tính không? | Tài nguyên có được phép truy cập |
| Authorization | User/role/authority/tenant có quyền trên route/object không? | Browser không bị ép gửi thao tác ngoài ý muốn |
| CSRF | Browser-originated state-changing request có token/ngữ cảnh tin cậy không? | User có role/ownership phù hợp |
| SameSite cookies | Browser có gửi cookie trong những ngữ cảnh site cụ thể không? | Mọi dạng CSRF, CORS, HTTP Basic |
| XSS controls | Script độc hại có chạy trong origin tin cậy không? | Authentication/authorization đầy đủ |

### 13.1. Đừng coi CORS như “bảo vệ API khỏi curl”

CORS chủ yếu được **browser** thực thi. Một HTTP client bình thường có thể tự đặt `Origin` hoặc không đặt, và đọc response bất kể Access-Control headers. API muốn chặn một client không có quyền phải dùng authentication, authorization, network controls, rate limits và các chính sách khác; không thể phụ thuộc chỉ vào CORS.

### 13.2. SameSite không phải same-origin

`https://a.example.test` và `https://b.example.test` có thể khác origin nhưng cùng site. Cookie SameSite có thể được gửi trong một số bối cảnh dù JavaScript vẫn chịu quy tắc CORS giữa hai origins. Ngược lại, một CORS origin được phép không có nghĩa cookie third-party được browser gửi.

### 13.3. Preflight thành công không hề cấp quyền POST

Một request có:
- Origin hợp lệ;
- POST trong allowed methods;
- Headers hợp lệ;

vẫn có thể bị 401 vì thiếu credentials, 403 vì không đủ role hoặc thiếu CSRF token, 400 vì request body sai và 409 vì business conflict. Preflight chỉ là một bước trước actual request.

## 14. Quản lý nhiều frontend origins và môi trường

### 14.1. Local, staging và production

Mỗi môi trường nên có danh sách origins riêng, ví dụ:

| Môi trường | Frontend được kiểm soát | API |
| --- | --- | --- |
| Local | `http://localhost:5173` | `http://localhost:8080` |
| Staging | `https://app.staging.example.test` | `https://api.staging.example.test` |
| Production | `https://app.example.test` | `https://api.example.test` |

**Không** để localhost origin trong cấu hình production chỉ vì thuận tiện phát triển. Nếu có admin frontend, cân nhắc allowlist riêng cho namespace quản trị và kiểm tra cả DNS, deployment ownership, subdomain takeover.

Có thể lấy origins từ environment-specific config:

~~~yaml
app:
  cors:
    allowed-origins:
      - https://app.example.test
      - https://admin.example.test
~~~

Đoạn YAML là **ví dụ thiết kế thuộc tính tùy biến**, không phải property Spring Boot tự động áp CORS. Muốn dùng, cần `@ConfigurationProperties`/`@Value` và nối vào `CorsConfiguration` đúng cách; đừng giả định đặt YAML trên là ứng dụng sẽ tự có CORS.

### 14.2. Không phản chiếu origin không qua kiểm tra

Sai về mặt bảo mật:

~~~java
// PSEUDOCODE KHÔNG AN TOÀN: không chép vào production.
// response.header("Access-Control-Allow-Origin",
//                 request.header("Origin"));
// response.header("Access-Control-Allow-Credentials", "true");
~~~

Nếu server chấp nhận mọi Origin rồi phản chiếu cùng credentials, một website của attacker có thể trở thành origin được phép đọc thông tin nhạy cảm của người dùng khi browser gửi credentials. **Phải có allowlist đáng tin cậy** trước khi chọn origin.

### 14.3. Thay đổi CORS policy qua phiên bản

Khi thêm frontend mới:
1. Review quyền sở hữu origin và cơ chế xác thực.
2. Xác định endpoints và HTTP methods cần thiết.
3. Chỉ thêm request headers thực sự được sử dụng.
4. Quy định credentialed access hay không.
5. Thiết kế CSRF token/cookie cho browser flows.
6. Deploy policy và test preflight trên staging, production.
7. Quan sát error metrics, không ghi token/credentials vào logs.
8. Rà soát định kỳ, loại origins không còn được dùng.

## 15. Những lỗi cấu hình thường gặp

| Lỗi | Dấu hiệu hoặc hậu quả | Cách sửa |
| --- | --- | --- |
| Import `org.springframework.web.cors.UrlBasedCorsConfigurationSource` trong WebFlux | Sai loại source cho API Reactive | Dùng `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` |
| Dùng Servlet `CorsFilter` hoặc `HttpSecurity` | Cấu hình không áp vào Reactor WebFilter chain | Dùng `CorsWebFilter` và `ServerHttpSecurity` |
| `new CorsConfiguration()` nhưng không đặt origins | Preflight bị từ chối | Khai báo allowlist origins |
| Gọi `applyPermitDefaultValues()` vô thức | Có thể mở origins wildcard | Đặt policy explicit |
| `allowedOrigins("*")` với `allowCredentials(true)` | Combination không hợp lệ | Liệt kê origins tin cậy cụ thể |
| `allowedOriginPatterns("*")` với credentials chỉ để tránh exception | Có thể cho mọi origin đọc dữ liệu nhạy cảm | Dùng pattern hẹp/allowlist |
| Thiếu port trong origin local | `localhost:5173` không match `localhost:3000` | So sánh scheme/host/port |
| Thiếu `Authorization` trong allowedHeaders | Preflight yêu cầu header Basic/Bearer không được chấp nhận | Cho phép chính xác header cần dùng |
| Nhầm `exposedHeaders` với `allowedHeaders` | Browser không đọc được response header dù request thành công | Dùng exposedHeaders cho response headers |
| Chỉ `permitAll OPTIONS` | Thiếu CORS response headers | Dùng CORS integration/filter đúng |
| Preflight bị 401 | Authentication chạy trước CORS | Cấu hình `ServerHttpSecurity.cors`/CorsWebFilter đúng |
| Preflight 200 nhưng POST 403 | Thiếu CSRF token hoặc quyền | Kiểm tra CSRF/authz, không tắt bừa |
| Không gửi `credentials:"include"` | Browser bỏ cookie/credentials trong cross-origin fetch | Xem login flow, SameSite, CORS |
| CORS cấp origin nhưng browser vẫn chặn cookie | Cookie SameSite/Secure/third-party policy | Kiểm tra Set-Cookie/Network |
| Dùng `maxAge` làm session timeout | Client/cache expectations sai | Tách preflight TTL và session/token TTL |
| Tạo cả CorsWebFilter bean và Security cors cùng source | Có thể duplicate processing | Chọn một chủ sở hữu CORS |
| `@CrossOrigin(origins="*")` trên route nhạy cảm | Origin policy quá rộng | Central allowlist và test từng endpoint |
| Reverse proxy rewrite path không được tính | `/api/**` không match path Spring thấy | Test path tại WebFlux sau proxy |
| Coi `curl 200` là browser CORS PASS | curl không enforce CORS | Dùng browser E2E/DevTools |
| Dùng CORS để thay authentication/CSRF | API vẫn có thể bị gọi hoặc bị CSRF | Giữ security controls độc lập |

## 16. Quy trình debug CORS cụ thể

Khi frontend báo “blocked by CORS policy”, kiểm tra theo thứ tự:

1. **Xác định origin thật:** dùng DevTools xem `Origin`, kể cả scheme và port. Không suy đoán từ URL người dùng nhìn thấy.
2. **Xem preflight OPTIONS:** có `Origin` + `Access-Control-Request-Method` không? Requested headers là gì?
3. **Xác minh source:** bean có import `...cors.reactive.UrlBasedCorsConfigurationSource` không? `registerCorsConfiguration` match đúng path không?
4. **Security integration:** CORS được xử lý trước auth? Nếu OPTIONS trả 401, kiểm tra `ServerHttpSecurity.cors`.
5. **Response headers:** `Access-Control-Allow-Origin` có match Origin? Có `Allow-Methods` và `Allow-Headers` phù hợp?
6. **Credentials:** frontend dùng `credentials:"include"`? API đã cho phép credentials và dùng explicit origins? Browser có chặn cookie theo SameSite/third-party rules?
7. **CORS vs auth:** actual GET/POST trả 401/403? Đọc response server, không kết luận từ một dòng console CORS.
8. **CSRF:** POST thiếu `X-CSRF-TOKEN` hoặc cookie WebSession? CSRF filter có đang chặn 403 không?
9. **Proxy:** có CDN/gateway thêm/bỏ `Access-Control-*` headers, cache sai theo Origin hoặc rewrite paths không?
10. **Nhiều chains:** request match `SecurityWebFilterChain` nào? Chain đó có source CORS đúng không?
11. **Nhiều CORS owners:** có `CorsWebFilter` bean, `WebFluxConfigurer`, `@CrossOrigin` lẫn với `ServerHttpSecurity.cors` không?
12. **Test đúng browser:** Safari/Firefox/Chrome có chính sách khác về cookies, private network requests, preflight caching.
13. **Đánh giá rò rỉ:** không bật wildcard origin/headers/credentials tràn lan chỉ để lỗi biến mất.
14. **Ghi logs an toàn:** correlation ID, method, route template, origin có thể log nếu chính sách cho phép; không log `Authorization`, session ID hoặc token CSRF.

### 16.1. Phân biệt các hiện tượng

| Hiện tượng | Khả năng | Hành động |
| --- | --- | --- |
| OPTIONS trả 401 | Security bắt preflight trước CORS | Tích hợp CORS source trong security chain |
| OPTIONS trả 403 | Origin/method/header không được phép, hoặc security rule khác | So sánh requested values với config |
| OPTIONS 200 nhưng browser không gửi POST | Header CORS không hợp lệ, credentials policy không khớp | Kiểm tra allow-origin/method/header/credentials |
| GET 200 trong curl, lỗi CORS ở browser | curl không enforce Same-Origin Policy | Đọc Network/console và headers |
| GET authenticated vẫn 401 | Credentials thiếu/sai | Debug authentication, không đổi allowed origins |
| POST có Basic đúng nhưng 403 | CSRF/authorization | Thử token hợp lệ và quyền |
| JS không đọc được `X-Request-ID` | Thiếu exposedHeaders | Thêm response header vào danh sách expose |
| Cookie không gửi trong fetch | credentials mode/SameSite/Secure/3rd-party | Kiểm tra browser cookie policy |
| Endpoint này có CORS, endpoint khác không | URL registration/chain khác nhau | Kiểm tra `/api/**`, `/admin/**` và matcher priority |
| Đổi policy nhưng client chưa thấy | Preflight cached, CDN/gateway cache | Kiểm tra `Access-Control-Max-Age` và `Vary: Origin` |

### 16.2. Vai trò của Vary

Khi server trả `Access-Control-Allow-Origin` khác nhau theo request Origin, HTTP caches/intermediaries cần biết response biến thiên theo `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`. CORS processor thường thêm `Vary` phù hợp, nhưng với CDN/proxy tùy biến hãy kiểm tra cache keys để không phục vụ nhầm một response/cors policy của origin này cho origin khác.

Đừng tự xóa `Vary` để “tăng cache hit” trên tài nguyên có chính sách CORS theo origin.

## 17. Bài tập tự kiểm tra

**Câu 1.** `http://localhost:5173` gọi `http://localhost:8080` có phải cross-origin không?

> Có, vì origin gồm scheme, host, port và port khác nhau.

**Câu 2.** `CorsConfiguration` và `UrlBasedCorsConfigurationSource` làm hai việc gì?

> `CorsConfiguration` mô tả policy; reactive `UrlBasedCorsConfigurationSource` chọn policy theo URL path của request. Filter/processor mới thực hiện kiểm tra và thêm response headers.

**Câu 3.** Với WebFlux import UrlBasedCorsConfigurationSource ở đâu?

> `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`, không phải package Servlet `org.springframework.web.cors`.

**Câu 4.** Vì sao preflight OPTIONS không nên cần login?

> Browser preflight kiểm tra CORS trước khi gửi actual request, thường không có credentials; security cần xử lý CORS trước authentication.

**Câu 5.** `allowCredentials(true)` có dùng `allowedOrigins("*")` được không?

> Không. Credentialed response không thể có wildcard Access-Control-Allow-Origin; phải chỉ rõ origins tin cậy hoặc dùng patterns hẹp được đánh giá kỹ.

**Câu 6.** `allowedHeaders` khác `exposedHeaders` thế nào?

> Allowed headers là những request headers browser được phép gửi; exposed headers là những response headers JavaScript được phép đọc.

**Câu 7.** `maxAge=1800` có làm WebSession sống 30 phút không?

> Không. Nó chỉ liên quan cache kết quả CORS preflight.

**Câu 8.** `OPTIONS` 200 có chứng minh actual POST sẽ thành công không?

> Không. Actual request vẫn cần authentication, authorization, CSRF và business validation.

**Câu 9.** Tại sao CORS không bảo vệ API khỏi `curl`?

> CORS chủ yếu được browser enforce; non-browser HTTP client có thể gọi API độc lập. Auth và authorization mới quyết định quyền.

**Câu 10.** Vì sao `pathMatchers(HttpMethod.OPTIONS,"/**").permitAll()` chưa đủ?

> Nó chỉ mở authorization cho OPTIONS, không xây response CORS allow headers và không validate Origin.

**Câu 11.** Nếu `Access-Control-Allow-Origin` đúng mà JS vẫn không đọc được `X-Request-ID`?

> Kiểm tra `Access-Control-Expose-Headers`/`setExposedHeaders`.

**Câu 12.** Vì sao một app có cookie session vẫn cần CSRF protection dù CORS giới hạn origin?

> Browser có thể gửi một số cross-origin requests mà attacker không cần đọc response; CORS không chứng minh người dùng chủ động gửi thao tác.

## 18. Checklist code review và production

### Cấu hình
- [ ] Đã chọn đúng API WebFlux Reactive, không import Servlet classes.
- [ ] `CorsConfiguration` khai báo origins được tổ chức kiểm soát, có scheme và port chính xác.
- [ ] `allowedOriginPatterns` nếu có được kiểm tra rủi ro subdomain takeover/tenant.
- [ ] `allowCredentials` chỉ bật khi cần; tuyệt đối không kết hợp với wildcard `allowedOrigins("*")`.
- [ ] Methods, request headers và exposed response headers tối thiểu cần thiết.
- [ ] `maxAge` là preflight TTL hợp lý, không nhầm session/token TTL.
- [ ] `UrlBasedCorsConfigurationSource` áp đúng namespace route.
- [ ] `ServerHttpSecurity.cors` xử lý preflight trước authentication.
- [ ] Không tạo duplicate CORS filters/owners ngoài ý muốn.
- [ ] Security rules không dùng CORS để thay authentication/authorization.

### Browser/client
- [ ] Frontend gửi đúng credentials mode và headers cần thiết.
- [ ] Session cookie có Secure/HttpOnly/SameSite phù hợp.
- [ ] POST browser có CSRF token/flow hợp lệ khi cần.
- [ ] Test bằng browser thực, không chỉ dùng curl.
- [ ] Kiểm tra login/logout/token rotation và third-party cookie restrictions.

### Testing
- [ ] Preflight allowed origin + requested method + headers thành công **không cần authentication**.
- [ ] Preflight denied origin bị từ chối.
- [ ] Preflight denied method bị từ chối.
- [ ] Preflight denied header bị từ chối.
- [ ] Actual GET allowed origin có ACAO và expected body.
- [ ] Actual GET denied origin bị chặn theo policy.
- [ ] Protected GET không credentials vẫn trả 401.
- [ ] Basic credentials đúng và allowed origin trả 200.
- [ ] POST allowed CORS nhưng thiếu CSRF vẫn bị 403.
- [ ] POST có CSRF, auth và allowed origin thực sự thành công.
- [ ] Browser/DevTools xác nhận expose response headers.
- [ ] Không có response bị cache sai cho khác Origin.
- [ ] Reverse proxy, CORS source, security chain và HandlerMapping nhìn cùng path như mong đợi.

## 19. Tổng kết

`CorsConfiguration` và **reactive** `UrlBasedCorsConfigurationSource` tạo nên một cấu hình CORS WebFlux theo danh sách cho phép: origin nào được phép, method/header nào được sử dụng, response headers nào JS được đọc và browser có thể cache preflight bao lâu.

Trong Spring Security Reactive, điểm tích hợp quan trọng là:

~~~java
.cors(cors -> cors.configurationSource(corsConfigurationSource))
~~~

nơi `corsConfigurationSource` là bean/source có kiểu `org.springframework.web.cors.reactive.CorsConfigurationSource`. Nó giúp xử lý preflight đúng chỗ thay vì để authentication từ chối OPTIONS.

Ba quy tắc cần nhớ:
1. **CORS không phải authentication/authorization**; API vẫn cần kiểm tra user, quyền và dữ liệu.
2. **CORS không thay CSRF**; actual POST từ browser có thể cần CSRF token dù OPTIONS thành công.
3. **Allowlist origin và credentials phải có chủ đích**; tuyệt đối tránh wildcard origin với cookie/credentialed cross-origin access.

### Tài liệu tham khảo chính thức

- Spring Security Reference — CORS for WebFlux: https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html
- Spring Security Javadoc — ServerHttpSecurity.CorsSpec: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html
- Spring Framework Reference — CORS for WebFlux: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html
- Spring Framework Javadoc — CorsConfiguration: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/cors/CorsConfiguration.html
- Spring Framework Javadoc — Reactive UrlBasedCorsConfigurationSource: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/cors/reactive/UrlBasedCorsConfigurationSource.html
- Spring Framework Javadoc — CorsWebFilter: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/cors/reactive/CorsWebFilter.html
- Spring Security — CSRF for WebFlux: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- MDN — Cross-Origin Resource Sharing: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN — Fetch credentials: https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials