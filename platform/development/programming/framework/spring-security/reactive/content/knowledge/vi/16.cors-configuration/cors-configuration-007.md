# Giới hạn origin theo môi trường và tránh phản chiếu origin tùy ý trong Spring Security Reactive

## 1. Bài toán thực tế và mục tiêu

Một ứng dụng Java sử dụng **Spring WebFlux** có thể cung cấp REST API tại api.example.org, trong khi frontend chạy ở localhost:5173 khi phát triển, staging-ui.example.org khi kiểm thử và app.example.org khi sản xuất. Trình duyệt coi các địa chỉ này là **khác origin**, kể cả khi đều thuộc cùng một công ty. Nếu API cần cho frontend gọi cross-origin, server phải thiết lập **CORS (Cross-Origin Resource Sharing)** phù hợp.

Có hai kiểu cấu hình thường gặp nhưng nguy hiểm:

- Mở CORS cho mọi website vì muốn “frontend nào cũng gọi được”.
- Tự đọc header **Origin** mà client gửi rồi đặt nguyên giá trị đó vào **Access-Control-Allow-Origin** mà không kiểm tra danh sách tin cậy.

Kiểu thứ hai gọi là **phản chiếu origin tùy ý** (arbitrary origin reflection). Nếu đồng thời đặt **Access-Control-Allow-Credentials: true**, một website không đáng tin có thể được trình duyệt cho đọc response API có cookie hoặc credential hợp lệ của người dùng, khi các điều kiện gửi credential khác cũng cho phép. CORS không tự tạo ra login, nhưng nó có thể mở đường đọc dữ liệu nhạy cảm của một phiên vốn đã tồn tại.

Mục tiêu bài học:

1. Hiểu chính xác **origin** là gì và CORS tác động đến trình duyệt ra sao.
2. Phân biệt **Origin**, **Access-Control-Allow-Origin**, **Access-Control-Allow-Credentials** và **Vary: Origin**.
3. Nắm khác biệt giữa **simple/actual request** và **preflight OPTIONS**.
4. Định nghĩa một **allowlist chính xác theo môi trường local, staging, production**; cấu hình **fail closed** khi thiếu/nhập sai.
5. Không dùng **allowOrigins("*")** với credential, không phản chiếu Origin tùy ý, không viết regex hoặc suffix check quá rộng.
6. Sử dụng đúng API **CorsConfiguration**, **CorsConfigurationSource**, **UrlBasedCorsConfigurationSource** và **ServerHttpSecurity.cors(...)** của Spring Security **Reactive**.
7. Viết demo Java 17+, Spring Boot WebFlux có HTTP Basic, CORS preflight trước authentication và policy GET public/private/admin.
8. Kiểm thử bằng **WebTestClient**: origin được phép/bị từ chối, credential, preflight, request thật, method/header không cho phép và false-positive với domain giả mạo.
9. Nhìn ra giới hạn của CORS: **CORS không thay thế authentication, authorization, CSRF, kiểm tra tenant/owner hay bảo mật API với non-browser clients**.

**Đích cuối cùng:** mỗi môi trường có danh sách origin do đội triển khai kiểm soát; chỉ origin thực sự được phê duyệt mới nhận CORS allow headers. Khi chuyển từ local sang staging/prod, policy không được âm thầm mở rộng hoặc chấp nhận Origin do attacker tự chọn.

## 2. Origin là gì?

Một **web origin** được xác định chủ yếu bởi bộ ba **scheme + hostname + port**. Phần path, query và fragment **không** thuộc origin.

Ví dụ:

| URL | Origin | So với https://app.example.org |
| --- | --- | --- |
| https://app.example.org/home | https://app.example.org | Cùng origin |
| https://app.example.org:443/home | https://app.example.org (cổng mặc định theo browser) | Cùng origin về ngữ nghĩa |
| http://app.example.org | http://app.example.org | **Khác** scheme |
| https://app.example.org:8443 | https://app.example.org:8443 | **Khác** port |
| https://api.example.org | https://api.example.org | **Khác** hostname |
| https://preview.app.example.org | https://preview.app.example.org | **Khác** subdomain |
| http://localhost:5173 | http://localhost:5173 | Khác origin với app production |

Một website ở **https://evil.example.net** không được coi là tin cậy chỉ vì URL có chứa chữ “app”, “trusted”, “example” hoặc trông tương tự domain thật.

Header **Origin** thường có dạng:

~~~http
Origin: https://app.example.org
~~~

Nó **không** chứa đường dẫn /dashboard hoặc query ?token=... Trong cấu hình Spring, **allowedOrigins** phải liệt kê **origin cụ thể**, không phải URL đầy đủ có path:

~~~text
Đúng:  https://app.example.org
Sai:   https://app.example.org/dashboard
Sai:   https://app.example.org/
Sai:   https://*.example.org (nếu đặt trong allowedOrigins)
~~~

Nếu muốn cho phép wildcard subdomain, Spring có **allowedOriginPatterns**; đây là cơ chế khác và vẫn phải giới hạn pattern theo ranh giới tin cậy. Trong bài học, ta chủ động **không sử dụng patterns** để loại bỏ sự mơ hồ.

### 2.1. Origin khác Site

Site trong ngữ cảnh cookie **SameSite** không nhất thiết trùng origin. Ví dụ app.example.org và api.example.org có thể thuộc cùng một “site” theo khái niệm registrable domain nhưng là **hai origins khác nhau**. Do đó, đặt SameSite=Lax hoặc Strict không đồng nghĩa CORS tự động cho phép mọi subdomain.

Subdomain do bên thứ ba quản lý, preview deployment, CDN host hoặc subdomain có thể bị chiếm quyền **không được tự động coi đáng tin** chỉ vì cùng registrable domain. CORS phân biệt ở cấp origin; cookie Domain và CSRF tạo thêm các ranh giới bảo mật cần xem xét riêng.

## 3. CORS giải quyết điều gì, và không giải quyết điều gì?

**Same-Origin Policy** hạn chế JavaScript của một origin đọc response từ origin khác. CORS là cơ chế để server **cho phép ngoại lệ có kiểm soát**, thông qua các HTTP response headers mà trình duyệt kiểm tra.

CORS không phải tường lửa máy chủ. curl, Postman, backend service hoặc bot có thể gửi HTTP requests mà không bị trình duyệt áp đặt Same-Origin Policy. Một attacker vẫn có thể gọi API trực tiếp từ server riêng nếu endpoint cho phép; authentication/authorization phải bảo vệ dữ liệu độc lập với Origin.

| Nhu cầu | CORS có giải quyết? | Cơ chế thực sự |
| --- | --- | --- |
| Frontend cross-origin đọc response được cho phép | **Có** | CORS response headers |
| Bắt user đăng nhập | **Không** | Authentication: session, Basic, bearer/OIDC |
| Chặn người thường đọc tài nguyên admin | **Không** | Authorization và role/permission |
| Chặn user đọc tài nguyên thuộc tenant khác | **Không** | Owner/tenant check |
| Chống giả mạo request bằng cookie | **Không đủ** | CSRF token, SameSite, Origin checks bổ sung |
| Chống script độc hại trong frontend | **Không** | XSS defense, escaping, CSP |
| Chặn request từ curl không có Origin | **Không** | API auth, network policy, rate limits |
| Cho browser gửi credential trong request cross-origin | **Có điều kiện** | CORS credentials + chính sách cookie/Fetch |

Câu nói “CORS sẽ chặn mọi request đến từ domain lạ” là không đúng. Browser có thể gửi một số request trước khi kết luận response không được đọc; trên server, lỗi CORS có thể làm Spring WebFlux phản hồi 403 khi nó xử lý một cross-origin request không hợp lệ. **Không dựa chỉ vào CORS để ngăn side effect hoặc dữ liệu bị khai thác qua kênh không phải browser.**

### 3.1. Origin không phải bằng chứng danh tính

Header Origin là thông tin của **web client context**. Client không bị trình duyệt ràng buộc như curl có thể tự gửi Origin bất kỳ. Không viết:

~~~java
// SAI: Origin không chứng minh người gọi là nhân viên.
if ("https://admin.example.org".equals(originHeader)) {
    giveAdminPermissions();
}
~~~

Rule role phải dựa trên **Authentication/GrantedAuthority** đã được Spring Security xác minh, không dựa trên chuỗi Origin. CORS chỉ quyết định các ngoại lệ cross-origin cho trình duyệt.

## 4. Preflight OPTIONS và actual request

Một số cross-origin requests cần **preflight**: trình duyệt tự gửi OPTIONS để hỏi server liệu method và các headers sắp dùng có được phép không. Ví dụ SPA muốn gửi HTTP Basic hoặc bearer trong **Authorization** header:

~~~http
OPTIONS /api/me HTTP/1.1
Host: api.example.org
Origin: https://app.example.org
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Nếu origin/method/header được cho phép, server có thể trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.org
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Mã phản hồi có thể là 200 hoặc một mã 2xx thích hợp theo thành phần xử lý; điều quan trọng là header cho phép phải phản ánh policy.

Sau preflight thành công, browser mới gửi actual request:

~~~http
GET /api/me HTTP/1.1
Origin: https://app.example.org
Authorization: Basic <encoded-credential>
~~~

Server vẫn phải **xác thực mật khẩu và kiểm tra quyền** trước khi trả dữ liệu. Preflight thành công không hề chứng minh client đã đăng nhập.

### 4.1. Vì sao preflight thường không mang cookie?

CORS preflight được browser gửi để hỏi quyền, không phải request nghiệp vụ đăng nhập. Preflight thường **không mang cookie hoặc Authorization của actual request**, nên nếu Spring Security đòi login trước khi xử lý OPTIONS, browser có thể chỉ báo “CORS error”.

Giải pháp không phải cho mọi endpoint **permitAll** hoặc tắt SecurityWebFilterChain. Hãy cấu hình **CorsWebFilter trước bước authentication/authorization** bằng tích hợp của Spring Security Reactive, để preflight được xử lý theo allowlist.

### 4.2. Simple request không nhất thiết có preflight

Một GET thông thường có thể không cần preflight nếu không có custom/non-safelisted headers. Tuy vậy browser vẫn dùng Origin và kiểm tra **Access-Control-Allow-Origin** trên actual response. Cấu hình CORS phải đúng cho **cả preflight lẫn actual request**.

Ngược lại, một request có preflight hợp lệ không có nghĩa actual request sẽ trả 200: authentication có thể trả 401, authorization trả 403, validation trả 400 hoặc backend trả 5xx.

### 4.3. Vì sao cần Vary?

Khi response CORS có thể thay đổi theo Origin, cache/proxy phải biết điều đó. **Vary: Origin**, và trong preflight còn **Access-Control-Request-Method** cùng **Access-Control-Request-Headers**, giúp tránh CDN/proxy tái sử dụng header của một origin cho origin khác.

Không tự ghép một Origin từ request vào header với ý định “để cache tự phân biệt”. Cache phải tôn trọng Vary, và những response cá nhân hóa nên dùng Cache-Control phù hợp, thường no-store.

## 5. Phản chiếu Origin tùy ý là lỗi gì?

Mẫu code nguy hiểm:

~~~java
// CẤM dùng làm chính sách CORS.
String incoming = exchange.getRequest().getHeaders().getOrigin();
if (incoming != null) {
    exchange.getResponse().getHeaders()
            .setAccessControlAllowOrigin(incoming);
    exchange.getResponse().getHeaders()
            .setAccessControlAllowCredentials(true);
}
~~~

Đoạn trên lấy Origin **do client tự khai** làm câu trả lời server “tôi cho phép website đó đọc dữ liệu”. Nếu không có một allowlist, attacker có thể dùng Origin của họ và nhận **Access-Control-Allow-Origin: https://evil.example.net**.

Một cấu hình **chỉ phản chiếu khi Origin đã qua allowlist chính xác** có thể hợp lệ: nhiều CORS framework sẽ trả chính giá trị Origin đã match khi có nhiều allowed origins. Vì vậy không đánh giá rủi ro chỉ bằng việc “response ACAO bằng request Origin”; phải kiểm tra **cách xác minh Origin trước khi phản hồi**.

### 5.1. Các mẫu sai thường thấy

**Mẫu sai A: wildcard với credentials**

~~~java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOrigins(List.of("*"));
config.setAllowCredentials(true);
~~~

Spring Framework sẽ phát hiện cấu hình không hợp lệ khi validateAllowCredentials được thực hiện. CORS specification không cho **Access-Control-Allow-Origin: *** đồng thời với **Access-Control-Allow-Credentials: true**.

**Mẫu sai B: copy Origin không kiểm tra**

~~~java
config.setAllowedOrigins(List.of(exchange.getRequest()
        .getHeaders().getOrigin()));
~~~

Câu lệnh trên không tạo allowlist tĩnh; nó khiến mọi Origin được chính client chọn.

**Mẫu sai C: prefix/suffix không đúng ranh giới**

~~~java
// SAI: https://app.example.org.attacker.test cũng có chứa chuỗi này.
if (origin.contains("app.example.org")) { allow(); }

// SAI: evil-example.org cũng có thể khớp một suffix sơ sài.
if (host.endsWith("example.org")) { allow(); }
~~~

Nếu muốn dùng subdomain wildcard thật, phải phân biệt suffix có dấu chấm, eTLD/public suffix, quyền sở hữu subdomain và khả năng takeover; dùng allowedOriginPatterns có kiểm soát với danh sách đã duyệt. **Allowlist chính xác** vẫn là lựa chọn ưu tiên cho sản phẩm có vài frontend.

**Mẫu sai D: tin một URL do user nhập**

~~~text
POST /settings/cors
{"allowedOrigin": "https://attacker.example.net"}
~~~

Nếu người dùng thường có thể tự đăng ký Origin để API có cookie authentication trả dữ liệu cho website của họ, đây có thể là vấn đề phân quyền cấu hình. Danh sách CORS trong sản phẩm phải do deployment/security owner kiểm soát; nếu có self-service tenant domains, cần quy trình xác minh domain ownership và quyền sửa policy.

**Mẫu sai E: “staging dùng * cho tiện”**

Một staging environment thường có dữ liệu hoặc tài khoản tương tự production. Cho mọi Origin kèm credential là rủi ro nghiêm trọng; ngay cả không có credential, mở bừa frontend origins vẫn gây nhầm lẫn contract và mở bề mặt dữ liệu đọc được. Staging cần danh sách origin **riêng**, được duyệt, không copy từ development một cách vô thức.

## 6. allowedOrigins, allowedOriginPatterns và allowCredentials

Spring Framework cung cấp **CorsConfiguration**:

- **setAllowedOrigins(List<String>)**: danh sách origin cụ thể, hoặc * khi không dùng credentials theo quy tắc tương ứng.
- **setAllowedOriginPatterns(List<String>)**: pattern cho những tập origin cần matching động; khi match, header ACAO có thể được đặt thành **origin thực tế đã match**.
- **setAllowedMethods(...)**: HTTP methods được cấp phép CORS.
- **setAllowedHeaders(...)**: request headers được cấp phép trong preflight.
- **setExposedHeaders(...)**: response headers mà JavaScript được phép đọc thêm ngoài CORS-safelisted headers.
- **setAllowCredentials(true/false)**: liệu cross-origin request kèm credential có được browser chấp nhận theo CORS không.
- **setMaxAge(...)**: preflight result được browser cache bao lâu (subject to browser caps).

### 6.1. Khi nào được dùng "*"?

Trường hợp API hoàn toàn public, không dùng cookie/credential và cho bất kỳ website nào đọc dữ liệu có thể chủ động chọn:

~~~java
config.setAllowedOrigins(List.of("*"));
config.setAllowCredentials(false);
~~~

Nhưng đây vẫn là **một quyết định công khai dữ liệu**, không phải cấu hình tiện tay. Với API cần session, cookie hoặc authorization credential, dùng **allowlist cụ thể** và chỉ bật credentials nếu có lý do.

Spring cho phép **allowedOriginPatterns** kết hợp allowCredentials trong một số trường hợp vì nó sẽ trả origin thực tế đã match, nhưng điều đó **không có nghĩa pattern rộng là an toàn**. Pattern **"*"** cùng allowCredentials về thực tế có thể cho browser mọi origin đã match đọc dữ liệu cá nhân.

### 6.2. Credentials không chỉ là cookies

Trong CORS/Fetch, credentials bao gồm cookie, thông tin HTTP authentication và các credential theo cơ chế browser. Với request dùng **fetch(..., { credentials: "include" })**, browser yêu cầu ACAO chính xác thay vì * và **Access-Control-Allow-Credentials: true** để cho JavaScript đọc response.

Với explicit Authorization header, preflight còn phải cho phép tên header **Authorization**. Quy tắc CORS và chính sách credentials của browser có những chi tiết riêng, nhưng **CORS không xác minh Authorization**: chính Spring Security AuthenticationWebFilter/manager phải thực hiện việc đó.

Một cross-origin client vẫn có thể không gửi được cookie vì **SameSite, Secure, third-party-cookie restrictions, partitioning, trình duyệt hoặc cấu hình Domain/Path** dù server đã trả Allow-Credentials. Không “sửa” bằng cách mở CORS cho mọi Origin.

### 6.3. Phân biệt Origin và Referer

Origin là tín hiệu phục vụ CORS; Referer có thể chứa URL của trang gọi hoặc bị chính sách Referrer-Policy lược bớt. Không tạo allowlist bằng cách so substring của Referer; cũng không sử dụng Origin như bằng chứng người dùng đã đăng nhập.

### 6.4. Origin: null

Browser có thể gửi Origin: null trong một số ngữ cảnh opaque origin, sandboxed iframe, file URL hoặc môi trường đặc biệt. Nếu không có nhu cầu rõ và biện pháp bổ sung, **không cho phép "null"** trong allowlist; attacker có thể tạo bối cảnh opaque origin. Bài demo từ chối Origin null.

## 7. Tách allowlist theo môi trường

Một ứng dụng thường có ba nhóm:

| Môi trường | Frontend origin được phê duyệt | Quy tắc |
| --- | --- | --- |
| local | http://localhost:5173 | HTTP loopback chỉ dùng cho phát triển |
| staging | https://staging-ui.example.org | Chỉ HTTPS, domain staging đã xác minh |
| production | https://app.example.org | Chỉ HTTPS, domain production đã xác minh |

Các domain example.org trong bảng là **tên miền ví dụ dành cho tài liệu**; khi triển khai thật, thay bằng origin thật do tổ chức sở hữu và kiểm soát. Không coi bất kỳ subdomain example.org nào mặc nhiên đáng tin.

### 7.1. Không “suy ra môi trường” từ Origin của client

Cấm logic:

~~~java
// SAI: caller tự khai để app tưởng đang ở môi trường local.
if (request.getHeaders().getOrigin().contains("localhost")) {
    allowCors();
}
~~~

Môi trường phải đến từ **deployment configuration**, Spring profile hoặc một nguồn cấu hình được quản trị, không phải request headers.

### 7.2. Cấu hình fail-closed

Bài demo sử dụng property **app.cors.allowed-origins**. Để chạy local, deployment truyền:

~~~bash
SPRING_PROFILES_ACTIVE=local \
APP_CORS_ALLOWED_ORIGINS=http://localhost:5173 \
gradle bootRun
~~~

Với production, deployment truyền một danh sách HTTPS đã duyệt, chẳng hạn:

~~~bash
SPRING_PROFILES_ACTIVE=prod \
APP_CORS_ALLOWED_ORIGINS=https://app.example.org \
gradle bootRun
~~~

Nếu có hai frontend production đều đã được duyệt:

~~~bash
APP_CORS_ALLOWED_ORIGINS=https://app.example.org,https://admin.example.org
~~~

Danh sách **chỉ gồm origins**, không thêm path, wildcard hoặc dấu slash cuối. Spring Boot Environment có thể ánh xạ biến môi trường APP_CORS_ALLOWED_ORIGINS tới property app.cors.allowed-origins theo quy tắc cấu hình của Spring Boot.

**Fail-closed trong demo:** nếu property trống, có origin sai định dạng, dùng *, dùng null hoặc dùng HTTP ngoài loopback/ngoài profile local, bean cấu hình từ chối khởi tạo; ứng dụng không tự chuyển sang mở tất cả origins. Đây là cố ý để deployment sai không silently weaken CORS.

### 7.3. Lưu ý khi đổi môi trường

- **Local:** chỉ cho HTTP ở localhost hoặc 127.0.0.1 khi profile local đang thực sự bật.
- **Staging:** chỉ HTTPS, không chấp nhận origin local của máy dev trừ khi có quyết định đặc biệt và quy trình kiểm soát.
- **Production:** allowlist đúng website production, ưu tiên ít nhất có thể.
- **Preview deployments:** không nên cho mọi tên dạng *.preview.example.org nếu bất kỳ developer hoặc user ngoài trust boundary có thể tạo preview. Có thể dùng allowlist cho từng preview đã được cấp quyền và TTL.
- **Multi-tenant:** nếu cho tenant khai báo custom domain, phải xác minh quyền sở hữu domain và bảo vệ endpoint thay đổi CORS policy bằng quyền quản trị thích hợp.
- **Kubernetes/CI:** biến môi trường, Helm values và secret/config sources được kiểm soát; review diff cấu hình origin trước khi release.
- **Rollback:** nhớ preflight cache có thể tồn tại trong browser một thời gian theo maxAge; đo tình trạng thực tế sau thay đổi policy.

## 8. Các tầng cấu hình CORS trong WebFlux

Có nhiều nơi có thể cấu hình CORS:

| Tầng | Cơ chế | Lưu ý |
| --- | --- | --- |
| Spring Security Reactive | ServerHttpSecurity.cors(...) và CorsConfigurationSource | Tích hợp CORS với security filters; thuận lợi cho preflight trước authentication |
| WebFlux | WebFluxConfigurer.addCorsMappings(...) | Áp dụng qua HandlerMapping, kiểm tra với annotated/functional endpoints |
| Annotated controller | @CrossOrigin | Dễ lạc chính sách khi từng team thêm annotation |
| WebFlux.fn/RouterFunction | HandlerMapping/route-specific CORS source | Cần đối chiếu với security policy |
| Global WebFilter | CorsWebFilter | Cẩn thận trùng với filter do Spring Security tạo |
| Gateway/CDN/reverse proxy | Middleware CORS | Có thể thêm/sửa header trước khi response về client |

Không nên bật nhiều tầng với các allowlists khác nhau nếu không có lý do. Chẳng hạn gateway phản chiếu Origin tùy ý nhưng ứng dụng Java giới hạn đúng có thể khiến response cuối có header trái policy, duplicate ACAO hoặc lỗi cache không dễ phát hiện.

Bài demo dùng **duy nhất một reactive CorsConfigurationSource** được truyền vào **ServerHttpSecurity.cors(...)**, không tạo CorsWebFilter thứ hai thủ công và không thêm @CrossOrigin ở controller.

### 8.1. Chọn đúng package reactive

~~~java
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
~~~

Không nhầm với:

~~~java
// Servlet/MVC, không dùng làm nguồn CORS reactive:
org.springframework.web.cors.UrlBasedCorsConfigurationSource;
org.springframework.web.filter.CorsFilter;
org.springframework.security.config.annotation.web.builders.HttpSecurity;
~~~

Hai package có thể có class trùng tên **UrlBasedCorsConfigurationSource**; import nhầm khiến cấu hình không khớp API của ServerHttpSecurity reactive.

### 8.2. CORS trong SecurityWebFilterChain

Trong Spring Security 6.x có API:

~~~java
http.cors(cors -> cors.configurationSource(source));
~~~

source là **org.springframework.web.cors.reactive.CorsConfigurationSource**. Cách này đưa cấu hình CORS vào security chain; preflight được giải quyết theo chính sách origin/method/header trước authentication cho endpoint thuộc chain.

Theo Javadoc ServerHttpSecurity.CorsSpec, nếu không có source phù hợp, CORS integration có thể không làm gì. **Gọi cors() mà không cung cấp cấu hình trusted origins không đồng nghĩa đã có một allowlist**.

## 9. Dự án mẫu Java 17+: Spring Boot Reactive với allowlist theo môi trường

Demo sử dụng **Spring Boot 3.5.16**, Java 17+ và Gradle 8.4+ (ví dụ Gradle 8.14). Spring Boot 3.5.16 hỗ trợ Spring Framework 6.2.19+ và đã được công bố là bản OSS cuối của dòng 3.5; với hệ thống mới cần chọn nhánh hiện còn hỗ trợ OSS hoặc gói hỗ trợ phù hợp. Phiên bản được pin để ví dụ sử dụng API Spring Security 6.x nhất quán.

Các URL:

| URL | CORS policy | Authentication/authorization |
| --- | --- | --- |
| GET /api/public/ping | /api/** theo allowlist | Public |
| GET /api/me | /api/** theo allowlist | Yêu cầu HTTP Basic hợp lệ |
| GET /api/admin/report | /api/** theo allowlist | ROLE_ADMIN |
| Các URL khác | Không tự mở | denyAll |

Một preflight tới GET /api/me **không cần gửi password** nhưng vẫn phải có Origin, Access-Control-Request-Method và các requested headers phù hợp. Sau preflight, GET /api/me vẫn cần Basic credential.

Tài khoản minh họa: reader / reader-pass với ROLE_USER; admin / admin-pass với ROLE_USER, ROLE_ADMIN. Dùng dữ liệu học tập, tuyệt đối không hard-code credential thật trong production.

### 9.1. Cấu trúc dự án

~~~text
webflux-cors-allowlist/
├── settings.gradle
├── build.gradle
├── src/main/resources/application.yml
├── src/main/java/example/cors/CorsApplication.java
├── src/main/java/example/cors/SecurityConfig.java
├── src/main/java/example/cors/ApiController.java
├── src/test/java/example/cors/CorsIntegrationTest.java
└── src/test/java/example/cors/CorsConfigValidationTest.java
~~~

### 9.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-cors-allowlist'
~~~

### 9.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 9.4. application.yml

~~~yaml
app:
  cors:
    # Không mở origin mặc định. Deployment bắt buộc cung cấp allowlist.
    allowed-origins: ""
~~~

Khi chạy bằng biến môi trường APP_CORS_ALLOWED_ORIGINS, giá trị này ghi đè property tương ứng. Nếu triển khai qua Spring config server hoặc manifest, có thể khai báo property app.cors.allowed-origins trực tiếp bằng danh sách origins đã phê duyệt.

### 9.5. CorsApplication.java

~~~java
package example.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsApplication.class, args);
    }
}
~~~

### 9.6. SecurityConfig.java — allowlist, validation và tích hợp CORS

~~~java
package example.cors;

import java.net.URI;
import java.time.Duration;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource(Environment env) {
        // Property nằm trong application.yml hoặc được deployment override.
        String csv = env.getProperty("app.cors.allowed-origins", "");
        boolean local = env.acceptsProfiles(Profiles.of("local"));

        List<String> origins = parseAllowedOrigins(csv, local);

        CorsConfiguration cors = new CorsConfiguration();
        // Chỉ origin đã duyệt, không dùng "*" hoặc pattern rộng.
        cors.setAllowedOrigins(origins);
        cors.setAllowCredentials(true);

        // Demo có các endpoint GET, không công khai các method ghi.
        cors.setAllowedMethods(List.of("GET"));
        cors.setAllowedHeaders(List.of(
                HttpHeaders.AUTHORIZATION,
                HttpHeaders.CONTENT_TYPE));
        cors.setMaxAge(Duration.ofMinutes(10));

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    static List<String> parseAllowedOrigins(
            String raw, boolean localProfile) {

        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException(
                    "app.cors.allowed-origins must be explicitly configured");
        }

        List<String> origins = Arrays.stream(raw.split(",", -1))
                .map(String::trim)
                .toList();

        Set<String> seen = new HashSet<>();

        for (String origin : origins) {
            if (origin.isEmpty()
                    || origin.indexOf('*') >= 0
                    || "null".equalsIgnoreCase(origin)) {
                throw new IllegalArgumentException(
                        "Invalid CORS origin: " + origin);
            }

            URI uri;
            try {
                uri = URI.create(origin);
            } catch (IllegalArgumentException e) {
                throw new IllegalArgumentException(
                        "Malformed CORS origin: " + origin, e);
            }

            String scheme = uri.getScheme();
            String host = uri.getHost();

            boolean https = "https".equals(scheme);
            boolean httpLoopback = localProfile
                    && "http".equals(scheme)
                    && ("localhost".equalsIgnoreCase(host)
                            || "127.0.0.1".equals(host));

            boolean hasPath = uri.getRawPath() != null
                    && !uri.getRawPath().isEmpty();

            if ((!https && !httpLoopback)
                    || host == null
                    || uri.getRawUserInfo() != null
                    || hasPath
                    || uri.getRawQuery() != null
                    || uri.getRawFragment() != null
                    || uri.getPort() == 0
                    || uri.getPort() > 65535) {
                throw new IllegalArgumentException(
                        "CORS origin must be an exact allowed scheme,"
                        + " hostname and optional port: " + origin);
            }

            if (!seen.add(origin)) {
                throw new IllegalArgumentException(
                        "Duplicate CORS origin: " + origin);
            }
        }

        return List.copyOf(origins);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            CorsConfigurationSource corsConfigurationSource) {

        return http
                // CorsWebFilter được tích hợp vào security chain.
                .cors(cors -> cors.configurationSource(
                        corsConfigurationSource))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                HttpMethod.GET, "/api/public/ping")
                                .permitAll()
                        .pathMatchers("/api/admin/**")
                                .hasRole("ADMIN")
                        .pathMatchers("/api/**")
                                .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }
}
~~~

**Phân tích đoạn code:**

1. Bean **CorsConfigurationSource** thuộc package reactive, chỉ đăng ký dưới /api/**.
2. **parseAllowedOrigins** từ chối cấu hình rỗng, wildcard, null, URL có path/query/fragment, URL dạng userinfo, duplicate và HTTP ngoài môi trường local có loopback.
3. **localProfile** do Spring Environment quyết định, không đọc Origin do request tự gửi. Trong production và staging, HTTP bị từ chối.
4. **setAllowedOrigins** dùng danh sách cụ thể; không tự lắp allowed list từ request headers.
5. **setAllowCredentials(true)** chỉ phù hợp vì danh sách origins đã được giới hạn và ứng dụng có use case browser credentialed requests; không có wildcard.
6. **setAllowedMethods(GET)**: preflight cho GET được phép; POST/DELETE không tự được mở CORS.
7. **setAllowedHeaders(Authorization, Content-Type)**: chỉ cho những request headers cần thiết. Header names có cách viết hoa khác nhau tùy browser; Spring CORS xử lý theo tên header theo quy tắc tương ứng.
8. **setMaxAge(10 phút)**: browser có thể cache kết quả preflight, cân bằng tải và thời gian áp dụng thay đổi policy.
9. **http.cors(...)** đảm bảo tích hợp với Spring Security; không thêm một CorsWebFilter bean độc lập để tránh xử lý trùng lặp.
10. **authenticated()** và **hasRole("ADMIN")** vẫn chạy với actual GET; preflight không được coi là login thành công.
11. **anyExchange().denyAll()** là default deny cho những URL không được công bố. Đây là quyết định authorization, khác CORS.
12. HTTP Basic được dùng cho bài tập; password demo được băm bằng BCrypt khi tạo user. Không sử dụng credential thật trên HTTP cleartext.
13. Mọi thay đổi allowlist cần được review bởi người quản trị cấu hình deployment; domain ví dụ không tự cấp quyền cho admin.

**Ranh giới của validator:** đây là một lớp phòng sai cấu hình cho ví dụ, không phải thư viện chuẩn hóa origin hoàn chỉnh cho mọi đặc tả URL/IDN/IPv6. Với sản phẩm có origin quốc tế hóa hoặc cấu trúc phức tạp, hãy dùng thư viện/kiểm thử phù hợp và luôn lưu giá trị canonical mà browser gửi. Điều quan trọng là **không tạo một policy chấp nhận wildcard hoặc Origin tùy ý**.

### 9.7. ApiController.java

~~~java
package example.cors;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(Mono<Principal> principal) {
        return principal.map(actor -> Map.of(
                "username", actor.getName()));
    }

    @GetMapping("/api/admin/report")
    public Mono<Map<String, String>> report() {
        return Mono.just(Map.of("report", "ok"));
    }
}
~~~

Controller không tự đặt CORS headers; **CorsWebFilter** xử lý việc đó dựa trên cấu hình duy nhất. Các endpoint vẫn cần Authentication/authorization khi đi qua SecurityWebFilterChain.

### 9.8. Chạy trên local với allowlist cụ thể

Bash:

~~~bash
SPRING_PROFILES_ACTIVE=local \
APP_CORS_ALLOWED_ORIGINS=http://localhost:5173 \
gradle bootRun
~~~

PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:APP_CORS_ALLOWED_ORIGINS = "http://localhost:5173"
gradle bootRun
~~~

Ứng dụng mặc định lắng nghe http://localhost:8080. Chỉ sử dụng username/password demo qua localhost; production phải bật HTTPS/TLS. Nếu bỏ biến APP_CORS_ALLOWED_ORIGINS hoặc đặt *, ứng dụng **không khởi động thành công** theo guard parseAllowedOrigins; đây là chính sách fail-closed có chủ đích.

Khi chuyển staging/prod, profile không phải local, chỉ dùng HTTPS origins. Nếu môi trường có override properties theo precedence khác, phải kiểm tra effective configuration ở deployment, không ghi giá trị credential/token vào log.

## 10. Thử bằng curl: preflight và actual request

Các lệnh dưới đây được viết cho Bash, chạy sau khi ứng dụng đang lắng nghe localhost:8080 với profile local và allowed origin **http://localhost:5173**.

### 10.1. Preflight hợp lệ, không có credential

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

Kết quả chính dự kiến:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Preflight không cần đăng nhập; nếu không có CORS integration phù hợp, request OPTIONS có thể bị SecurityWebFilterChain yêu cầu auth trước khi trả CORS headers.

### 10.2. Preflight từ Origin lạ

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: https://attacker.example.net' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

Với CorsWebFilter chuẩn trong demo, kết quả dự kiến là **403 Invalid CORS request**, và **không được** nhận Access-Control-Allow-Origin của attacker. Kết quả cụ thể có thể bị biến đổi bởi proxy/lớp error handler khác, nhưng điều bất biến là **không có CORS permission cho origin đó**.

### 10.3. Origin có tên gần giống

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: http://localhost.evil.example.net:5173' \
  -H 'Access-Control-Request-Method: GET'
~~~

Dù có chữ localhost, đây **không phải** http://localhost:5173, nên bị từ chối. Test loại này giúp phát hiện code dùng contains("localhost") để coi client đáng tin.

### 10.4. Preflight xin method không có trong allowlist

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: DELETE'
~~~

Kỳ vọng: **403** hoặc không có header CORS cho DELETE; trong demo CorsWebFilter sẽ từ chối preflight không hợp lệ. Không tự mở toàn bộ methods chỉ vì website frontend đã được duyệt.

### 10.5. Actual request tới API protected, thiếu Basic credential

~~~bash
curl -i http://localhost:8080/api/me \
  -H 'Origin: http://localhost:5173'
~~~

Origin được allowlist cho phép **không tương đương login**: HTTP Basic authentication vẫn yêu cầu credential, kết quả dự kiến **401 Unauthorized** kèm Basic challenge. CORS headers của origin được phép có thể hiện diện trên response 401 để browser frontend đọc được status đúng.

### 10.6. Actual request có credential và origin được phép

~~~bash
curl -i -u reader:reader-pass \
  -H 'Origin: http://localhost:5173' \
  http://localhost:8080/api/me
~~~

Kết quả chính dự kiến:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Content-Type: application/json

{"username":"reader"}
~~~

Ở production, chỉ dùng HTTPS và cơ chế đăng nhập phù hợp; Basic Base64 không tự bảo mật password.

### 10.7. Actual request với Origin lạ dù credential đúng

~~~bash
curl -i -u reader:reader-pass \
  -H 'Origin: https://attacker.example.net' \
  http://localhost:8080/api/me
~~~

Trong demo, CorsWebFilter từ chối request CORS với Origin không được phép (dự kiến 403). Điều này thể hiện xử lý server-side của Spring, **không có nghĩa CORS là một authentication firewall phổ quát**. Client không phải browser có thể bỏ header Origin, vì vậy vẫn phải giữ Basic/role/tenant checks.

### 10.8. Request không có Origin

~~~bash
curl -i -u reader:reader-pass \
  http://localhost:8080/api/me
~~~

Kỳ vọng 200 với reader. Một direct request không có Origin không phải một cross-origin browser request cần ACAO. Chính sách xác thực vẫn áp dụng; nếu bỏ -u, kết quả là 401.

### 10.9. Lỗi thiếu ROLE_ADMIN vẫn là 403

~~~bash
curl -i -u reader:reader-pass \
  -H 'Origin: http://localhost:5173' \
  http://localhost:8080/api/admin/report
~~~

Kỳ vọng: 403 **vì authorization**, không phải vì CORS. Nếu thử admin:admin-pass với cùng origin được phép thì GET trả 200. Quan sát Network/headers để phân biệt lỗi CORS (Origin denied) với lỗi authorization (role denied).

## 11. WebTestClient: kiểm tra policy thật từ nhiều nguồn

Để chứng minh allowlist, phải test **cả preflight và actual GET**. Unit test chỉ gọi Controller không chạy CorsWebFilter hoặc SecurityWebFilterChain.

Tệp **src/test/java/example/cors/CorsIntegrationTest.java**:

~~~java
package example.cors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "app.cors.allowed-origins="
                + "https://frontend.example.org,https://ops.example.org")
@AutoConfigureWebTestClient
class CorsIntegrationTest {

    private static final String ALLOWED =
            "https://frontend.example.org";

    private static final String DENIED =
            "https://evil.example.net";

    @Autowired
    WebTestClient client;

    @Test
    void preflightFromAllowedOriginSucceedsWithoutLogin() {
        client.options().uri("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "authorization")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        ALLOWED)
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                        "true")
                .expectHeader().exists(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS)
                .expectHeader().exists(HttpHeaders.VARY);
    }

    @Test
    void preflightFromDeniedOriginIsRejected() {
        client.options().uri("/api/me")
                .header(HttpHeaders.ORIGIN, DENIED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void preflightRejectsDisallowedMethod() {
        client.options().uri("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                        "DELETE")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void preflightRejectsDisallowedRequestHeader() {
        client.options().uri("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "x-unsafe-debug")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void allowedOriginDoesNotBypassAuthentication() {
        client.get().uri("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        ALLOWED);
    }

    @Test
    void actualRequestAllowedOriginAndValidLoginWork() {
        client.get().uri("/api/me")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        ALLOWED)
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                        "true")
                .expectBody()
                .jsonPath("$.username").isEqualTo("reader");
    }

    @Test
    void actualRequestFromDeniedOriginIsRejected() {
        client.get().uri("/api/me")
                .header(HttpHeaders.ORIGIN, DENIED)
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void lookalikeSubdomainIsNotTrusted() {
        client.options().uri("/api/me")
                .header(HttpHeaders.ORIGIN,
                        "https://frontend.example.org.evil.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void opaqueNullOriginIsNotTrusted() {
        client.options().uri("/api/me")
                .header(HttpHeaders.ORIGIN, "null")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void sameOriginStyleDirectRequestStillNeedsLogin() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username").isEqualTo("reader");
    }

    @Test
    void allowedOriginDoesNotOverrideAdminAuthorization() {
        client.get().uri("/api/admin/report")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();

        client.get().uri("/api/admin/report")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.report").isEqualTo("ok");
    }

    @Test
    void publicRouteIsStillRestrictedByCorsInBrowserContext() {
        client.get().uri("/api/public/ping")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .exchange()
                .expectStatus().isOk();

        client.get().uri("/api/public/ping")
                .header(HttpHeaders.ORIGIN, DENIED)
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

**Ý nghĩa của 12 test:** không chỉ “origin được phép thì 200”. Bộ test xác minh:

- Preflight không có credential nhưng vẫn cho origin/method/header đã được duyệt.
- Origin lạ và origin có hostname gần giống không được chấp thuận.
- Method DELETE và custom header lạ không được phép chỉ vì origin hợp lệ.
- Actual GET vẫn cần login; role ADMIN vẫn có tác dụng.
- Request không có Origin vẫn chịu authorization nhưng không bị nhầm là một cross-origin request phải có ACAO.
- Public API vẫn không mở CORS cho tất cả origins chỉ vì permitAll ở security rule.

**Cảnh báo:** nếu project có gateway hoặc bộ lọc CORS bổ sung ở bên ngoài, phải test cả response tại ranh giới Internet. Test WebTestClient chỉ chứng minh policy trong ứng dụng Java.

### 11.1. Test các giá trị cấu hình sai

Tệp **src/test/java/example/cors/CorsConfigValidationTest.java**:

~~~java
package example.cors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;

import org.junit.jupiter.api.Test;

class CorsConfigValidationTest {

    @Test
    void productionOnlyAcceptsExplicitHttpsOrigins() {
        assertEquals(
                List.of("https://frontend.example.org",
                        "https://ops.example.org"),
                SecurityConfig.parseAllowedOrigins(
                        " https://frontend.example.org,"
                        + "https://ops.example.org ",
                        false));
    }

    @Test
    void missingAndWildcardOriginsFailClosed() {
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins("", false));
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins("*", false));
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "https://*.example.org", false));
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "null", false));
    }

    @Test
    void pathQueryAndTrailingCommaAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "https://frontend.example.org/", false));
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "https://frontend.example.org/home", false));
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "https://frontend.example.org?debug=1", false));
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "https://frontend.example.org,", false));
    }

    @Test
    void plainHttpIsOnlyAllowedForLoopbackInLocalProfile() {
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "http://localhost:5173", false));
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "http://public.example.org", true));

        assertEquals(
                List.of("http://localhost:5173"),
                SecurityConfig.parseAllowedOrigins(
                        "http://localhost:5173", true));
    }

    @Test
    void duplicateOriginsAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> SecurityConfig.parseAllowedOrigins(
                        "https://frontend.example.org,"
                        + "https://frontend.example.org",
                        false));
    }
}
~~~

Chạy kiểm thử toàn bộ:

~~~bash
gradle test
~~~

**Kết quả kỳ vọng:** 17 test PASS (12 kiểm thử tích hợp + 5 kiểm thử policy parser), Gradle kết thúc BUILD SUCCESSFUL nếu Java, Gradle và dependencies phù hợp. Đây là **kỳ vọng từ thiết kế mã**, không phải bản ghi một build đã thực thi.

### 11.2. Vì sao kiểm thử token/role lại quan trọng?

CORS preflight không mang nghĩa đã xác thực. Nếu chỉ test OPTIONS thành công mà không thử GET actual, có thể nhầm rằng API không cần password. Ngược lại, nếu GET actual trả 403, phải phân biệt:

- CORS từ chối Origin.
- Authentication hợp lệ nhưng role không đủ.
- Authorization từ chối ở URL.
- CSRF bị chặn trên method không an toàn.
- Proxy/gateway trả 403 trước Spring.

Ma trận test thay từng yếu tố (origin, method, header, credential, role) giúp tìm nguyên nhân thật.

## 12. Browser frontend: ví dụ Fetch và cookie

Với frontend chạy tại **http://localhost:5173** và API ở **http://localhost:8080**, JavaScript có thể gọi:

~~~javascript
async function readProfile() {
  const response = await fetch("http://localhost:8080/api/me", {
    method: "GET",
    credentials: "include",
    headers: {
      "Authorization": "Basic " + btoa("reader:reader-pass")
    }
  });

  if (!response.ok) {
    throw new Error("API status: " + response.status);
  }

  return await response.json();
}
~~~

**Đây là ví dụ học tập để quan sát CORS, không phải thiết kế login production.** Không hard-code Basic password trong JavaScript/frontend bundle; attacker có thể đọc source. Production dùng OIDC/authorization code + PKCE hoặc session/BFF và quản lý credential an toàn theo kiến trúc.

Trình duyệt thường preflight vì **Authorization** không thuộc CORS-safelisted request headers. Preflight xin GET và authorization, không mang Basic password; server allowlist kiểm tra trước. Actual GET mang Authorization mà frontend chủ động cung cấp; Spring Security kiểm tra mật khẩu rồi trả principal.

Nếu dùng cookie session thay vì Basic:

- Frontend cần **credentials: "include"** nếu cross-origin fetch cần gửi cookie theo chính sách Fetch.
- Server cần Access-Control-Allow-Credentials: true và ACAO đúng origin.
- Cookie phải có Domain/Path/Secure/SameSite thích hợp; third-party cookie restrictions có thể ngăn cookie.
- Unsafe requests còn cần CSRF protection phù hợp; CORS không thay thế CSRF.
- Frontend phải xử lý 401/403, không coi lỗi CORS là “sai mật khẩu”.

### 12.1. Dev proxy có thể làm CORS không xuất hiện

Vite/dev server có thể proxy /api về backend sao cho browser chỉ nhìn thấy một origin của frontend. Khi đó không có cross-origin request trên wire từ browser tới backend, và thiếu lỗi CORS không chứng minh allowlist đã đúng.

Hãy kiểm tra **Network panel**: request thực đi tới host nào, header Origin nào, response ACAO thế nào. Test thêm trực tiếp qua WebTestClient/curl với Origin để cố định policy.

## 13. Cache, CDN và rủi ro khi phản chiếu header

Một ứng dụng có thể có nhiều allowed origins. Spring WebFlux có thể trả chính Origin đã được **allowlist xác nhận**, nhưng nếu CDN cache response cùng key mà bỏ qua Vary, hai request có origin khác nhau có thể nhận header sai.

Giảm rủi ro:

1. Để CorsWebFilter xử lý **Vary: Origin**, **Access-Control-Request-Method** và **Access-Control-Request-Headers** phù hợp.
2. Đảm bảo reverse proxy/CDN **không loại bỏ Vary**, không cache response cá nhân hóa dùng cookie/Authorization nếu không có chính sách an toàn cụ thể.
3. Không cho gateway add Access-Control-Allow-Origin: * sau khi backend đã áp dụng allowlist.
4. Không gửi nhiều Access-Control-Allow-Origin headers có giá trị khác nhau; browser thường từ chối cấu hình trùng/mơ hồ.
5. Không dựa vào Origin để quyết định quyền dữ liệu trong cache key; authorization còn cần identity/tenant.
6. Giới hạn Access-Control-Max-Age khi team thường xuyên phải thu hồi origin; browser có thể cache preflight đến một giới hạn riêng của nó.
7. Khi rotate hostname/frontend, triển khai allowlist mới và kiểm thử trước thời điểm chuyển DNS; thu hồi origin cũ có plan.
8. Khi thấy một response có ACAO bằng Origin, hãy **xác minh việc validate Origin**, không kết luận phản chiếu tùy ý chỉ từ dấu hiệu đó.

Lưu ý browser có thể không cho JavaScript đọc response vì ACAO sai, nhưng request vẫn đã đến server trong nhiều trường hợp. Không dùng header CORS làm thay thế cho validation của các thao tác ghi tiền, thay đổi tài khoản hay dữ liệu nhạy cảm.

## 14. Khi nào được dùng allowedOriginPatterns?

Có sản phẩm nhiều tenant với custom domains hoặc nhiều preview deployments. Spring Framework hỗ trợ:

~~~java
config.setAllowedOriginPatterns(
        List.of("https://*.preview.example.org"));
~~~

Đây chỉ là một **đoạn minh họa API**, không phải khuyến nghị triển khai wildcard đó vào production. Pattern cần đánh giá ai được phép tạo hoặc kiểm soát subdomain, liệu có subdomain takeover, DNS wildcard, custom domain pointing hoặc dữ liệu người dùng thật hay không.

Khác biệt:

- **allowedOrigins** dùng origin cụ thể, dễ kiểm toán và test.
- **allowedOriginPatterns** là tập match động; khi match, Spring thường trả đúng origin được match, không trả dấu *.
- **Phản chiếu tùy ý** là trả origin nhận được mà không hề kiểm tra tập trust; nó không được biện minh chỉ vì response trông giống kết quả của allowedOriginPatterns.
- Pattern cực rộng như "*" kết hợp allowCredentials là rủi ro cao ngay cả khi Spring cho phép hình thức API đó.
- CORS policy do tenant tự quản lý phải đi kèm **domain ownership verification, approval, giới hạn tài nguyên được đọc, TTL và audit**.

Nếu chỉ có ba frontend origin, **allowlist chính xác vẫn tốt hơn** pattern.

### 14.1. Origin so khớp không đồng nghĩa với regex tự viết

Đừng viết regex từ input do admin không được phép tự khai rồi cho regex đó kiểm soát CORS toàn hệ thống. Nếu dùng pattern, hãy hiểu cú pháp Spring CorsConfiguration khác regex Java tổng quát và test cả trường hợp **evil.example.org**, **example.org.evil.test**, port, scheme và subdomain chưa được duyệt.

## 15. Checklist vận hành cho local, staging, production

| Kiểm tra | Local | Staging | Production |
| --- | --- | --- | --- |
| Origin list | http://localhost:5173, nếu cần | HTTPS host staging đã kiểm soát | HTTPS host production đã kiểm soát |
| Wildcard * khi credentials true | Cấm | Cấm | Cấm |
| Origin: null | Không cho trừ trường hợp được phê duyệt cụ thể | Cấm | Cấm |
| HTTP ngoài loopback | Không | Cấm | Cấm |
| reflect Origin từ request | Cấm | Cấm | Cấm |
| Cấu hình nguồn | Profile/env do developer kiểm soát | CI/CD cấu hình có review | IaC/secret/config có review và approval |
| Preflight không có Authorization | Pass nếu origin/method/header hợp lệ | Pass nếu hợp lệ | Pass nếu hợp lệ |
| Authentication/role trên actual request | Bắt buộc | Bắt buộc | Bắt buộc |
| CSRF cho browser credentials | Đánh giá | Bắt buộc đánh giá | Bắt buộc đánh giá |
| Vary, cache | Test | Test qua proxy | Test qua CDN |
| CORS integration bị cấu hình trùng | Tránh | Tránh | Tránh |
| Thay đổi allowlist | Mọi developer có thể quản lý local | Review của team | Security/ops review |

Một release nên tự động test tối thiểu:

- Allowed staging/prod origin có CORS headers đúng.
- Untrusted origin không được trả Access-Control-Allow-Origin.
- Lookalike hostname không được nhận quyền.
- Origin “null” bị từ chối.
- Origin HTTP bị từ chối trên production.
- Preflight cho method/header đã duyệt thành công; DELETE hoặc X-Unsafe-Debug bị từ chối.
- Actual request không có credential nhận 401 dù Origin hợp lệ.
- Authenticated user thiếu role nhận 403 dù Origin hợp lệ.
- Không có CORS config do deploy sai thì ứng dụng fail fast.
- Không có Header Access-Control-Allow-Origin bị proxy/CDN tự thêm bất ngờ.

### 15.1. Quan sát và log

Nên log **loại sự kiện** (cors_allowed, cors_rejected, preflight_denied), origin đã được làm sạch theo log policy, method/path template, requestId và trạng thái. Không log Authorization, cookie, CSRF token hay thông tin người dùng nhạy cảm. Origin là input có thể do client tự cung cấp, phải escape/truncate để chống log injection và gây nổ số lượng metric labels.

Tránh dùng raw Origin làm nhãn Prometheus cardinality không giới hạn; có thể phân loại theo allowed/denied và bucket environment. CORS errors nên được phân biệt với 401 authentication, 403 authorization và CSRF 403 trong dashboard vận hành.

### 15.2. Sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| OPTIONS nhận 401 | CORS chưa được xử lý trước authentication | Kiểm tra ServerHttpSecurity.cors và preflight test |
| OPTIONS nhận 403 | Origin/method/header không được allowlist hoặc proxy chặn | Thay lần lượt Origin, Access-Control-Request-Method/Headers |
| GET curl thành công, browser báo CORS | Curl không áp dụng Same-Origin Policy | Kiểm tra Network, ACAO, credentials và preflight |
| Browser báo không cho credential | ACAO là * hoặc thiếu Access-Control-Allow-Credentials | Dùng exact origin; bật credentials chỉ khi cần |
| Local hoạt động, prod bị chặn | Prod không có hostname trong allowlist hoặc http/https khác | Kiểm tra effective environment property |
| Test domain lookalike được phép | Dùng contains/startsWith/suffix check sai | Thay bằng exact allowedOrigins |
| Có hai ACAO headers | Gateway và Spring đều tự thêm CORS | Chọn một nguồn cấu hình và sửa proxy |
| OPTIONS thành công, GET 401 | CORS đúng, Authentication thiếu/sai | Kiểm tra scheme và credential |
| OPTIONS thành công, GET 403 | Role/owner/CSRF hoặc policy khác | Kiểm tra security filters và status/body |
| Cookie không được gửi | SameSite/Secure/third-party blocking | Kiểm tra Set-Cookie và browser storage |
| ACAO đúng nhưng JS không đọc được response header custom | Chưa cấu hình exposedHeaders | Bổ sung exposedHeaders chính xác nếu cần |
| Thay allowlist nhưng browser còn dùng cấu hình cũ | Preflight được cache | Kiểm tra Access-Control-Max-Age/browser cache |
| Unknown Origin được ACAO phản chiếu | Tầng nào đó chấp nhận không kiểm tra | Tìm manual headers, @CrossOrigin, WebFluxConfigurer, CDN |
| App không start khi env CORS trống | Validator fail closed theo chủ đích | Cung cấp allowlist chính xác qua config deployment |

## 16. Bài tập thực hành và câu hỏi tự kiểm tra

1. Origin của https://app.example.org:8443/dashboard?tab=1 là chuỗi nào?
2. Vì sao https://app.example.org và http://app.example.org không cùng origin?
3. Nếu API trả Access-Control-Allow-Origin: https://evil.example.net cho một Origin chưa hề được duyệt, rủi ro gì có thể xảy ra?
4. Vì sao allowCredentials(true) không dùng chung với allowedOrigins("*")?
5. Vì sao allowedOriginPatterns("*") dù có thể được framework nhận vẫn là chính sách không an toàn cho API có credential?
6. Một response ACAO đúng bằng request Origin có luôn chứng minh arbitrary reflection không?
7. Tại sao preflight OPTIONS cần được xử lý trước authentication?
8. Trên local profile demo, Origin http://localhost:5173 có được phép không? Origin http://localhost.evil.test:5173 thì sao?
9. Tại sao profile production trong demo từ chối HTTP không phải HTTPS?
10. Tại sao POST chỉ vì origin hợp lệ vẫn không được bỏ qua CSRF?
11. Curl gọi API không có Origin nhưng dùng Basic hợp lệ nhận 200 có chứng minh allowlist đã sai không?
12. Một user reader từ allowed Origin muốn GET /api/admin/report, status nào mong đợi?
13. Tại sao phải test cả method GET được phép và DELETE bị từ chối trong preflight?
14. Tại sao dùng HTTP method trong CORS không thay thế method authorization?
15. Vì sao không nên tin Origin từ request để quyết định role hoặc tenant?
16. Việc thêm @CrossOrigin ở một Controller có thể gây chính sách không đồng nhất với RouterFunction như thế nào?
17. Access-Control-Max-Age và Vary đóng vai trò gì đối với cache/preflight?
18. Khi deploy thiếu APP_CORS_ALLOWED_ORIGINS, vì sao fail closed tốt hơn tự default "*"? 
19. Một frontend cần đọc response header X-Request-Id bằng JS phải cấu hình gì thêm?
20. Trong hệ multi-tenant cho domain riêng, cần xác minh thêm điều gì trước khi allow CORS domain đó?

**Đáp án gợi ý:**

1. https://app.example.org:8443, path/query không thuộc origin.
2. Scheme khác nhau.
3. Một browser origin lạ có thể được cấp quyền đọc response cross-origin, nghiêm trọng nếu API cho cookie/credential.
4. Chuẩn CORS cấm ACAO * đi cùng Allow-Credentials true; Spring validate cấu hình.
5. Pattern quá rộng cho bất kỳ origin match, tương tự mở khả năng đọc response cá nhân.
6. Không; phản hồi đúng Origin sau exact allowlist matching là hợp lệ.
7. Preflight thường không có credential, nếu auth chặn trước thì browser không gửi actual request.
8. Được nếu config local đúng; lookalike domain bị từ chối.
9. Giảm rủi ro gửi/đọc dữ liệu qua HTTP ở môi trường thật; local loopback là ngoại lệ có chủ đích.
10. CORS không thay thế CSRF cho cookie/browser auto-credential.
11. Không; curl không bị browser CORS giới hạn và Authentication vẫn có tác dụng.
12. 403 do thiếu ROLE_ADMIN, nếu request đã được CORS cho phép.
13. Đảm bảo origin hợp lệ không tự động mở mọi phương thức.
14. CORS chỉ điều phối browser cross-origin, authorization quyết định user có quyền chạy method.
15. Origin do client kiểm soát ngoài browser, không phải signed identity claim.
16. @CrossOrigin có thể thêm allow origins qua HandlerMapping khác với policy trung tâm.
17. maxAge cache preflight; Vary ngăn cache trộn response giữa origins/methods/headers.
18. Fail fast ngăn một deployment lỗi âm thầm mở tất cả origins.
19. setExposedHeaders(List.of("X-Request-Id")) nếu response cung cấp header đó.
20. Ownership, trust boundary, quyền sửa policy, takeover, TTL, approval, audit.

## 17. Tài liệu tra cứu

- Spring Security — Reactive CORS integration: https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html
- Spring Security Javadoc — ServerHttpSecurity: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security Javadoc — CorsSpec.configurationSource: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html
- Spring Framework — WebFlux CORS: https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- Spring Framework — CorsConfiguration Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/cors/CorsConfiguration.html
- Spring Framework — Reactive CorsWebFilter Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/cors/reactive/CorsWebFilter.html
- Spring Boot 3.5 System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- MDN — Cross-Origin Resource Sharing: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN — Access-Control-Allow-Credentials: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials
- OWASP — CORS and Access-Control-Allow-Origin guidance: https://owasp.org/www-community/attacks/CORS_OriginHeaderScrutiny

**Kết luận:** Trong Spring Security WebFlux, **giới hạn Origin phải bắt đầu từ allowlist cụ thể, do deployment kiểm soát cho từng môi trường**; tuyệt đối không trả lại Origin tùy ý cùng Access-Control-Allow-Credentials. Dùng **CorsConfigurationSource reactive** tích hợp qua **ServerHttpSecurity.cors(...)**, kiểm tra scheme/host/port, xử lý preflight trước authentication, giới hạn method/header, giữ Vary/cache đúng và fail closed khi cấu hình sai. Kiểm thử cả preflight lẫn actual requests, domain giả mạo, credential và role: **CORS chỉ cho trình duyệt biết response nào được đọc cross-origin; không thay thế bất kỳ kiểm soát danh tính, quyền hay CSRF nào.**