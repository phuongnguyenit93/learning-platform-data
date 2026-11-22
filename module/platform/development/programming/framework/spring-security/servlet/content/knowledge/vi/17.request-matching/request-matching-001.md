# RequestMatcher và dữ liệu yêu cầu được dùng để khớp trong Spring Security Servlet

## 1. RequestMatcher trả lời câu hỏi gì?

Trong ứng dụng **Spring Boot 3.x / Spring Security 6.x sử dụng Servlet**, trước khi hệ thống quyết định có cho phép một HTTP request đi đến controller hay không, Spring Security thường phải nhận diện **request thuộc phạm vi nào**.

Ví dụ:

- `GET /products/42` có phải request đọc sản phẩm công khai không?
- `POST /api/reports` có phải thao tác cần quyền ghi báo cáo không?
- `GET /admin/users` có thuộc nhóm cần vai trò ADMIN không?
- `GET /api/reports` kèm header `X-Api-Version: v2` có thuộc một phiên bản API đặc biệt không?
- Request đang đi qua chain dành cho `/api/**` hay chain dành cho giao diện web?

**`RequestMatcher`** là abstraction trả lời câu hỏi: “Request HTTP hiện tại **có khớp điều kiện này không?**”. Giao diện thường gặp:

~~~java
package org.springframework.security.web.util.matcher;

public interface RequestMatcher {
    boolean matches(HttpServletRequest request);
}
~~~

Đây là **hình thức rút gọn để giải thích phương thức cốt lõi**, không phải bản sao toàn bộ interface trong mọi phiên bản Spring Security. `HttpServletRequest` đến từ `jakarta.servlet.http` trên Spring Boot 3. Một số API/phiên bản có thêm phương thức hỗ trợ kết quả match chứa biến đường dẫn, nhưng `matches(...)` là cơ sở để hiểu việc chọn request.

**RequestMatcher không tự xác thực user và không tự cấp quyền.** Nó chỉ trả lời một request có thỏa tiêu chí hay không. Quyết định quyền truy cập còn cần `AuthorizationManager`, `Authentication` và các chính sách liên quan.

### Tình huống thực tế

~~~text
GET /api/reports?month=11
Authorization: Basic ...
X-Api-Version: v2
~~~

Một matcher chỉ xét đường dẫn `/api/reports` có thể khớp bất kể `month=11` và header phiên bản. Một matcher xét **method + đường dẫn + header** có thể cho kết quả khác. **Điều kiện nào được dùng phụ thuộc vào loại matcher và cách người lập trình cấu hình**, không có quy tắc rằng mọi RequestMatcher luôn kiểm tra toàn bộ request.

## 2. RequestMatcher xuất hiện ở đâu trong Spring Security?

Có hai vị trí quan trọng nhưng rất dễ nhầm:

1. **`securityMatcher(...)` của một `SecurityFilterChain`**: chọn xem một request có được xử lý bởi filter chain đó không.
2. **`requestMatchers(...)` trong `authorizeHttpRequests(...)`**: sau khi chain đã được chọn, chọn rule phân quyền áp dụng cho request.

Luồng đơn giản:

~~~text
HTTP request
    |
    v
Servlet container / DelegatingFilterProxy
    |
    v
FilterChainProxy
    |
    | Chọn SecurityFilterChain ĐẦU TIÊN có chain RequestMatcher khớp
    v
Security filters của chain đó
    |
    | Authentication được khôi phục/kiểm tra theo cơ chế cấu hình
    v
AuthorizationFilter
    |
    v
RequestMatcherDelegatingAuthorizationManager
    |
    | Chọn cặp RequestMatcher -> AuthorizationManager đầu tiên khớp
    v
AuthorizationManager kiểm tra Authentication + request context
    |
    +--> cho phép -> controller / resource
    |
    +--> từ chối -> exception handling, thường 401 / 403 / redirect
~~~

Các filter có thể có hành vi hoặc thứ tự khác theo phiên bản, chain và dispatcher; sơ đồ giúp hiểu vai trò tương đối.

### 2.1. securityMatcher khác requestMatchers

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đây là snippet cấu hình cần import `@Bean`, `@Order`, `HttpSecurity`, `Customizer`, `SecurityFilterChain`; **không** phải file Java độc lập. `securityMatcher("/api/**")` là điều kiện **chọn chain**. Nếu `GET /web/home` không khớp chain API thì các rule bên trong `authorizeHttpRequests` của chain này **không được xét** cho request đó.

Trong chain đã chọn, `requestMatchers("/api/admin/**")` lại là điều kiện **chọn rule authorization**. Nếu tất cả chain đều có matcher hẹp mà không có chain nào khớp URL, request có thể không được bảo vệ bởi Spring Security. Trong hệ thống thật cần thiết kế chain fallback/bảo phủ theo threat model.

### 2.2. Matcher khác AuthorizationManager

~~~java
.requestMatchers("/admin/**").hasRole("ADMIN")
~~~

Matcher kiểm tra URL có thuộc `/admin/**`; manager kiểm tra `Authentication` có authority tương ứng `ROLE_ADMIN` hay không. Nếu matcher khớp mà user không có quyền, request bị **từ chối tại rule đã chọn**; Spring Security không đi tìm rule phía dưới để xem có rule nào dễ hơn không.

Một matcher **không nên tự đọc password hoặc kiểm tra quyền user trong dữ liệu đầu vào không đáng tin**. Giữ tách biệt “chọn phạm vi request” và “quyết định ai được làm gì”.

## 3. Dữ liệu nào có trong HttpServletRequest?

`RequestMatcher.matches(HttpServletRequest)` có thể đọc nhiều thuộc tính từ request. Một số trường được lấy từ servlet API; một số là dữ liệu mà servlet container hoặc các filter trước đó đã xử lý.

| Dữ liệu | Cách đọc điển hình | Mục đích thường gặp |
| --- | --- | --- |
| HTTP method | `request.getMethod()` | Phân biệt GET, POST, PUT, DELETE… |
| Request URI | `request.getRequestURI()` | Đường URI trên server, **thường bao gồm context path** |
| Context path | `request.getContextPath()` | Tên ngữ cảnh ứng dụng, ví dụ `/shop` |
| Servlet path | `request.getServletPath()` | Đường dẫn ánh xạ tới servlet, hữu ích cho matcher servlet/MVC |
| Path info | `request.getPathInfo()` | Phần đường dẫn còn lại khi servlet mapping có path info |
| Query string | `request.getQueryString()` | Chuỗi truy vấn từ URL, không chứa phần path |
| Query/form parameters | `request.getParameter("key")` | Chọn biến thể request, lọc theo tham số nếu thật cần |
| HTTP headers | `request.getHeader("X-Api-Version")` | API version/content negotiation/routing có kiểm soát |
| Content type | `request.getContentType()` | Phân biệt JSON/form/multipart theo định dạng |
| Cookies | `request.getCookies()` | Chọn request theo sự hiện diện của cookie khi cần |
| Dispatcher type | `request.getDispatcherType()` | Phân biệt REQUEST, FORWARD, ERROR, ASYNC… |
| Server/host/scheme | `getServerName()`, `getScheme()`, `isSecure()` | Chính sách theo host/HTTPS, cần xem proxy trust |
| Client network address | `request.getRemoteAddr()` | Mạng/IP nhìn từ container, có thể là proxy |
| Request attributes | `request.getAttribute(...)` | Dữ liệu do ứng dụng/filter gắn trước đó |
| Servlet mapping | `request.getHttpServletMapping()` | Ngữ cảnh servlet mapping trên Servlet hiện đại |

**Không phải matcher nào cũng kiểm tra tất cả các dữ liệu trên.** Ví dụ matcher theo path có thể bỏ qua header/query; matcher theo method có thể không xét query parameters. Bạn quyết định dữ liệu được dùng bằng cách **chọn matcher phù hợp**, hoặc xây custom matcher khi các điều kiện có giá trị thực.

Không nên đọc/buffer lại toàn bộ request body từ một matcher để quyết định quyền: body có thể chỉ đọc được một lần, làm hỏng controller/parser tiếp theo, gây tốn tài nguyên và mở nguy cơ DoS. Authorization dựa trên nội dung nghiệp vụ thường nên nằm sau bước parse/validate ở service/method.

## 4. Hiểu đúng RequestURI, contextPath, servletPath, pathInfo và query

### 4.1. Ví dụ ứng dụng chạy dưới context path

Giả sử public URL:

~~~text
https://example.test/shop/api/items/42?include=stock
~~~

Ứng dụng được deploy với `contextPath=/shop` và Spring MVC `DispatcherServlet` thường ánh xạ ở `/`. Một cách nhìn thường gặp:

~~~text
getRequestURI()   -> /shop/api/items/42
getContextPath()  -> /shop
getServletPath()  -> /api/items/42
getPathInfo()     -> null
getQueryString()  -> include=stock
~~~

Đây là **ví dụ cho servlet mapping kiểu mặc định**. Với servlet được map theo `/app/*` hoặc các kiểu mapping khác, `getServletPath()` và `getPathInfo()` có thể khác. Nếu ứng dụng chạy sau reverse proxy rewrite path, URL bên ngoài browser và path container nhìn thấy cũng có thể khác.

**Lỗi phổ biến:** lấy `getRequestURI()` rồi so trực tiếp với `"/api/items/42"` khi context path là `/shop`. Kết quả không khớp vì request URI chứa `/shop`. Khi dùng matcher hỗ trợ Spring MVC hoặc matcher path phù hợp, framework có thể xử lý phần này theo quy tắc của matcher; custom matcher phải xét đúng path API mà mình sử dụng.

### 4.2. Query string không thuộc path

~~~text
GET /api/items?sort=price
GET /api/items?sort=date
GET /api/items?sort=price&limit=100
~~~

Một path matcher cho `/api/items` thường xem các request này là **cùng một path**, dù query khác. `request.getRequestURI()` và `getServletPath()` không gồm `?sort=...`.

Nếu bạn cần matching theo query, phải làm có chủ ý bằng `getParameter(...)` hoặc matcher custom phù hợp; nhưng **không nên giao quyền dựa trên tham số do client tự chọn** như `?role=ADMIN` hoặc `?isOwner=true`.

### 4.3. URL encoding và path normalization

Các path chứa phần mã hóa như `%2F`, `%2E`, chuỗi `..`, dấu chấm phẩy, dấu gạch chéo liên tiếp hoặc khoảng trắng có thể được xử lý khác nhau giữa browser, reverse proxy, Servlet container và Security matcher.

Spring Security thường sử dụng `HttpFirewall` (chẳng hạn `StrictHttpFirewall`) trong `FilterChainProxy` để áp dụng quy tắc chấp nhận/chuẩn hóa request trước khi các bộ lọc nhìn request. **Đừng tự viết matcher dựa trên việc decode URL theo cách riêng** và đừng nới firewall chỉ để làm một endpoint khó khớp mà không đánh giá bảo mật.

Phải tránh khác biệt giữa:
- URL mà reverse proxy dùng để định tuyến;
- URL mà Servlet container chuẩn hóa;
- URL mà Spring Security match;
- URL mà Spring MVC hoặc controller sử dụng.

Nếu những tầng này hiểu khác nhau, có thể xảy ra lỗi authorization bypass hoặc chặn nhầm request hợp lệ. Giữ đường dẫn canonical, test encoded/trailing-slash/semicolons trên môi trường thực.

## 5. Những dạng RequestMatcher thường gặp

Spring Security có nhiều implementation, và DSL `requestMatchers(...)` có thể chọn implementation dựa vào ngữ cảnh Spring MVC/servlet mapping. Không nên suy đoán pattern string luôn là regular expression hoặc luôn có cùng semantics trong mọi version.

### 5.1. Path-based matcher

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

`/public/**` diễn tả một nhóm URL; các ký hiệu wildcard được diễn giải theo **matcher implementation** đã chọn. Các biểu thức pattern của MVC-aware matcher, Ant-style matcher, PathPattern-based matcher và regex matcher không hoàn toàn tương đương. Khi nâng cấp Spring Security hoặc thay servlet mapping, cần test lại pattern thực tế.

Với Spring MVC trong classpath, DSL có thể lựa chọn matcher phù hợp MVC; đôi khi dự án cần xác định tường minh servlet path hoặc matcher type để tránh nhập nhằng. Nếu có nhiều servlet, Spring Security có thể yêu cầu chỉ rõ matcher thuộc servlet nào. **Đừng giả định `requestMatchers(String...)` luôn khớp giống `String.startsWith()`.**

### 5.2. Method-based matcher

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/articles/**").permitAll()
    .requestMatchers(HttpMethod.POST, "/api/articles").hasAuthority("article:write")
    .requestMatchers(HttpMethod.DELETE, "/api/articles/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

Đây là snippet của `HttpSecurity` có import `org.springframework.http.HttpMethod`. Một path có thể cho phép GET công khai nhưng yêu cầu quyền khác cho POST/DELETE. Phải kiểm thử các method được ứng dụng hỗ trợ, không chỉ GET. Với các method “safe” như HEAD/OPTIONS, đừng tự giả định luôn khớp cùng rule với GET: tùy matcher và hạ tầng có thể có hành vi khác.

### 5.3. RequestHeaderRequestMatcher và match theo header

Spring Security có matcher chuyên dụng cho một số điều kiện header; hoặc có thể viết một lambda dễ đọc:

~~~java
RequestMatcher apiVersionTwo = request ->
    "GET".equals(request.getMethod())
    && "/api/reports".equals(request.getServletPath())
    && "v2".equals(request.getHeader("X-Api-Version"));
~~~

Snippet này cần import `RequestMatcher` và nằm trong phạm vi Java phù hợp. Nó chỉ khớp GET path `/api/reports` kèm header phiên bản v2 chính xác. Kiểm tra header **là cách phân loại route**, **không phải bằng chứng quyền**: người gọi có thể tự gửi `X-Api-Version: v2`.

Trong ví dụ chạy được, rule của v2 sẽ yêu cầu **authority đáng tin** `report:v2` do server cung cấp cho user sau authentication. Nếu client giả header v2 mà không có quyền, request vẫn bị 403. Đây là thiết kế đúng hơn việc chỉ nhìn header và tự cho phép.

### 5.4. Regex và matcher tùy biến

Khi pattern routing phức tạp, một regex matcher có thể hữu ích nhưng cần chú ý escaped path, separator, query handling, performance và regex denial-of-service. Không chuyển tất cả path patterns thành regex khi matcher mặc định đã diễn đạt rõ ràng.

Khi kiểm tra nhiều điều kiện, có thể dùng `AndRequestMatcher`, `OrRequestMatcher`, `NegatedRequestMatcher` hoặc lambda `request -> ...`. Tập trung vào các điều kiện rõ ràng, tránh viết logic matcher khó kiểm chứng hoặc phụ thuộc response/body.

~~~java
RequestMatcher securedReportRead = request ->
    "GET".equals(request.getMethod())
    && "/api/reports".equals(request.getServletPath())
    && "v2".equals(request.getHeader("X-Api-Version"));
~~~

Trong mã thật, matcher chỉ có nhiệm vụ chọn rule cần `report:v2`. Việc `Authentication` có authority `report:v2` hay không phải do AuthorizationManager kiểm tra.

### 5.5. Dispatcher type matcher

Servlet request có thể chuyển qua `DispatcherType.REQUEST`, `FORWARD`, `ERROR`, `ASYNC` và `INCLUDE`. Có thể dùng:

~~~java
.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR, DispatcherType.FORWARD)
        .permitAll()
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
)
~~~

Đây là snippet, cần import `jakarta.servlet.DispatcherType`. Một số ứng dụng cần cho phép error/forward rendering, nhưng **không bật permitAll mọi dispatcher type một cách mù quáng**; cần đánh giá vì forward/error paths có thể dẫn tới nội dung nhạy cảm hoặc quy trình khác. Dispatcher matching và authorization còn phụ thuộc cách các filter được kích hoạt khi request dispatch.

### 5.6. Matcher theo host, scheme, remote address và thời điểm

Trong một số bài toán nhiều domain, reverse proxy hoặc internal endpoint, custom matcher có thể xét `Host`, `getServerName()`, scheme hoặc remote address. Tuy nhiên **dữ liệu này có thể bị thay đổi bởi proxy và header forwarded từ client**, nên chỉ an toàn khi đã thiết lập trust boundary rõ ràng.

Không dùng `X-Forwarded-For` do người dùng tự gửi làm chứng cứ rằng request đến từ mạng nội bộ; không cấp ADMIN dựa trên `User-Agent` hoặc `Referer`. IP checks có thể là lớp phụ trợ nhưng thường không đủ thay thế authentication/authorization.

## 6. Matchers không tự động kiểm tra user có quyền

Giả sử API muốn cho phép admin xem báo cáo:

~~~java
.requestMatchers("/admin/reports/**").hasRole("ADMIN")
~~~

Luồng:

1. Matcher kiểm tra URL.
2. Nếu URL khớp, AuthorizationManager kiểm tra `Authentication` và authority cần thiết.
3. Nếu user không có `ROLE_ADMIN`, bị từ chối.
4. **Không thử rule tiếp theo** dù có một matcher rộng phía sau như `"/admin/**"` hoặc `anyRequest().authenticated()`.

Lỗi rất nguy hiểm:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

`/api/admin/users` đã khớp rule `/api/**` đầu tiên, nên được `permitAll`. Rule admin phía sau không được dùng. Sửa bằng cách đặt matcher hẹp trước:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

**Quy tắc nền tảng:** `RequestMatcherDelegatingAuthorizationManager` chọn **matcher đầu tiên khớp**, không phải matcher có quyền nghiêm ngặt nhất, cũng không thử manager thứ hai nếu manager thứ nhất từ chối.

### 6.1. Fallback cần explicit

`anyRequest().denyAll()` giúp thiết kế **deny by default** cho URL chưa có rule. `anyRequest().authenticated()` cũng có giá trị, nhưng nghĩa là user nào đăng nhập cũng được vào mọi URL còn lại — đó là policy khác.

Nếu đặt matcher broad `/**` trước các rule cụ thể, chúng sẽ trở thành unreachable; nếu bỏ catch-all chain trong multi-chain config, các URL ngoài phạm vi matcher của mọi chain có thể không được Spring Security bảo vệ.

## 7. Dữ liệu request không đáng tin: ranh giới cực kỳ quan trọng

Trong nhiều hệ thống, thông tin request có thể bị người gọi kiểm soát:

- URL path và query string;
- Header `X-Role`, `X-User`, `X-Tenant-Id`, `X-Api-Version`;
- HTTP method do client gửi;
- Cookie do client tự đặt;
- Body JSON/form parameters;
- Header `Origin`, `Referer`, `User-Agent`;
- Một phần network metadata nếu có reverse proxy sai cấu hình.

**Có thể dùng những dữ liệu này để CHỌN chính sách cần kiểm tra**, nhưng **không được dùng làm bằng chứng user có quyền** nếu chưa có bước xác minh đáng tin cậy.

### 7.1. Một anti-pattern nghiêm trọng

~~~java
// SAI: ai cũng có thể tự gửi X-Role: ADMIN.
RequestMatcher "admin" = request ->
    "ADMIN".equals(request.getHeader("X-Role"));
~~~

Đây là **pseudo-code cố ý không biên dịch**, minh họa vấn đề tin header do client tự cung cấp. Nếu hệ thống sau đó `permitAll()` cho matcher này, attacker có thể tự đặt header để giành quyền.

Thực hiện đúng:

~~~java
.requestMatchers("/admin/**").hasRole("ADMIN")
~~~

Authority `ROLE_ADMIN` phải đến từ `Authentication` đã xác minh hoặc token có chữ ký/claims đã được kiểm tra, không phải từ header `X-Role` do request tự khai.

### 7.2. Query parameter không đồng nghĩa quyền sở hữu

~~~text
GET /api/orders/123?ownerId=alice
GET /api/orders/123?isOwner=true
~~~

Ngay cả nếu URL thuộc rule `authenticated()`, ứng dụng **không thể tin** `ownerId=alice` hoặc `isOwner=true` do client tự gửi. Cần kiểm tra account thực đã authenticated và owner/tenant của order 123 từ nguồn dữ liệu đáng tin, thường ở service/method policy.

### 7.3. Dùng matcher để tăng yêu cầu, không để bypass

Một lựa chọn an toàn là dùng header phiên bản để **nâng yêu cầu quyền**:

~~~java
.requestMatchers(v2Matcher).hasAuthority("report:v2")
.requestMatchers(HttpMethod.GET, "/api/reports").hasAuthority("report:read")
~~~

Nếu người gọi chọn `X-Api-Version: v2`, họ phải có `report:v2`; nếu không chọn, yêu cầu `report:read`. Việc sửa header **không tự tạo authority**, chỉ chọn chế độ phục vụ với quyền khác nhau.

**Cẩn trọng:** nếu v2 chứa dữ liệu nhạy cảm hơn nhưng đường fallback cho phép client truy cập cùng dữ liệu theo một cách khác, hệ thống vẫn có lỗ hổng thiết kế. Authorization ở service nên bảo vệ dữ liệu thực; không dựa hoàn toàn vào header variant.

### 7.4. Method override và request wrappers

Nếu app có `HiddenHttpMethodFilter` hoặc custom filter sửa/wrap request, matcher có thể thấy HTTP method đã được chuyển đổi tùy **thứ tự filter**. Không tự suy rằng `getMethod()` luôn là phương thức gốc trên wire trong mọi deployment.

Nên test HTTP method thực được security filter nhìn thấy, đặc biệt khi hỗ trợ `_method=DELETE`, reverse proxy rewrite hoặc API gateway. Không để bypass bằng method override khác cách mà controller áp dụng.

## 8. Matcher theo đường dẫn: các bẫy cần kiểm thử

### 8.1. Wildcard không phải biểu thức regex phổ quát

String pattern `"/api/**"` diễn tả nhóm path theo matcher đang được dùng, không phải là một regex Java trực tiếp. Pattern `"/api/{id}"` thường có semantics khác `"/api/*"`. Cần xác minh phiên bản Spring Security, Spring MVC, servlet mapping và parser được áp dụng.

### 8.2. Trailing slash, case và dấu chấm phẩy

~~~text
/api/items
/api/items/
/API/items
/api/items;v=1
/api/items%2F42
~~~

Những URL này có thể bị framework/proxy xử lý khác nhau. Đừng giả định luôn đồng nhất và đừng nới `StrictHttpFirewall` quá rộng để chấp nhận encoded slash/semicolon chỉ vì một client gửi URL không chuẩn. Hãy thống nhất canonical URL và test từ proxy tới controller.

### 8.3. Context path và servlet mapping

Trong ứng dụng có `server.servlet.context-path=/shop`, một matcher custom so `getRequestURI()` trực tiếp với `"/api/reports"` sẽ sai. Trong cấu hình Boot MVC root servlet, `getServletPath()` thường phù hợp cho path app-relative, nhưng với servlet khác mapping phải phân tích `getPathInfo()`, `HttpServletMapping` và cách matcher đã chọn xử lý đường dẫn.

### 8.4. Query và fragment

Browser không gửi URL fragment `#section` trong HTTP request; Servlet `HttpServletRequest` không nhận fragment như một phần URI để matcher kiểm tra. Query `?page=2` thì được gửi, nhưng **không thuộc path**. Không dùng `request.getRequestURI().contains("?")` để match query.

### 8.5. Static resources và actuator

Nếu application cho phép `/css/**`, `/js/**` hoặc `/health` công khai, hãy khai báo rõ. Đừng chữa lỗi asset 403 bằng `anyRequest().permitAll()` rồi vô tình mở toàn bộ API. Với actuator management port/context khác, có thể cần matcher chuyên dụng và security chain riêng.

## 9. Project runnable: matcher theo path, HTTP method và header

Ví dụ sử dụng **Java 17**, **Spring Boot 3.3.13**, **Spring Security 6** và HTTP Basic để test matcher đơn giản. Project minh họa:

- `GET /health` công khai.
- `GET /api/reports` **không có header v2** yêu cầu `report:read`.
- `GET /api/reports` với `X-Api-Version: v2` yêu cầu `report:v2`.
- `POST /api/reports` yêu cầu `report:write`; CSRF vẫn bật mặc định.
- `GET /api/profile` yêu cầu đã authenticated.
- `GET /admin/status` yêu cầu `ROLE_ADMIN`.
- URL không liệt kê bị `anyRequest().denyAll()`.

**Không dùng một header do client tự đặt để cấp authority**. Header phiên bản chỉ **chọn rule** yêu cầu permission tương ứng. Login dùng user/password demo trong memory chỉ để thực hành; không triển khai trực tiếp ra production.

### 9.1. Cấu trúc project

~~~text
request-matcher-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/matchdemo/
    │   ├── MatcherApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/matchdemo/
        └── RequestMatcherTests.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>request-matcher-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/com/example/matchdemo/MatcherApplication.java`**

~~~java
package com.example.matchdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MatcherApplication {
    public static void main(String[] args) {
        SpringApplication.run(MatcherApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/matchdemo/SecurityConfig.java`**

~~~java
package com.example.matchdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        // Custom matcher CHỈ chọn biến thể API: GET + path + header.
        // Header là dữ liệu client-controlled, KHÔNG phải authority.
        RequestMatcher reportsV2 = request ->
            "GET".equals(request.getMethod())
            && "/api/reports".equals(request.getServletPath())
            && "v2".equals(request.getHeader("X-Api-Version"));

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()

                // Đặt matcher hẹp lên trước GET cùng path thông thường.
                .requestMatchers(reportsV2).hasAuthority("report:v2")
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("report:read")

                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("report:write")

                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()

                .requestMatchers("/admin/**").hasRole("ADMIN")

                // Mọi request ngoài các route trên bị từ chối.
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            // CSRF giữ mặc định; POST cần token hợp lệ.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String hash = encoder.encode("demo-pass");
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(hash)
                .authorities("ROLE_USER", "report:read")
                .build(),
            User.withUsername("bob")
                .password(hash)
                .authorities("ROLE_USER", "report:v2")
                .build(),
            User.withUsername("writer")
                .password(hash)
                .authorities("ROLE_USER", "report:write")
                .build(),
            User.withUsername("admin")
                .password(hash)
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

**Lý do thứ tự rule:** matcher `reportsV2` phải nằm trước `requestMatchers(HttpMethod.GET, "/api/reports")`, vì URL/method giống nhau. Nếu đổi chỗ, request v2 sẽ bị matcher GET tổng quát bắt trước, làm quyền `report:v2` không được kiểm tra.

Trong ví dụ, alice có `report:read` nhưng không có `report:v2`, còn bob có `report:v2` nhưng không có `report:read`. User được chọn bằng authentication HTTP Basic do Spring Security xác thực, **không** bởi header `X-Api-Version`. `POST` còn phải vượt CSRF filter, nên một user có `report:write` vẫn có thể bị 403 nếu thiếu CSRF token.

**`src/main/java/com/example/matchdemo/DemoController.java`**

~~~java
package com.example.matchdemo;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/reports")
    public Map<String, String> reports(HttpServletRequest request) {
        String version = "v2".equals(request.getHeader("X-Api-Version"))
            ? "v2" : "v1";
        return Map.of("version", version);
    }

    @PostMapping("/api/reports")
    public ResponseEntity<Map<String, String>> createReport() {
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("result", "created"));
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/admin/status")
    public Map<String, String> admin() {
        return Map.of("status", "admin-ok");
    }

    @GetMapping("/unlisted")
    public Map<String, String> unlisted() {
        return Map.of("status", "should-not-be-visible");
    }
}
~~~

`/unlisted` có MVC mapping nhưng không được policy HTTP cho phép. Đây là cách kiểm tra fallback `denyAll`. Nếu request đến controller thật, đó sẽ là dấu hiệu security rule bị bỏ qua hoặc cấu hình không đúng.

### 9.2. Kiểm thử bằng MockMvc

**`src/test/java/com/example/matchdemo/RequestMatcherTests.java`**

~~~java
package com.example.matchdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestMatcherTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPathIsAccessible() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void queryParameterDoesNotChangePathMatch() throws Exception {
        mvc.perform(get("/api/reports")
                .param("page", "2")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.version").value("v1"));
    }

    @Test
    void headerSelectsStricterVersionPolicy() throws Exception {
        mvc.perform(get("/api/reports")
                .header("X-Api-Version", "v2")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.version").value("v2"));

        // Alice có quyền đọc v1 nhưng KHÔNG có report:v2.
        mvc.perform(get("/api/reports")
                .header("X-Api-Version", "v2")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        // Bob có report:v2 nhưng không có report:read.
        mvc.perform(get("/api/reports")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedVersionTwoNeedsLogin() throws Exception {
        mvc.perform(get("/api/reports")
                .header("X-Api-Version", "v2"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void methodRuleAndCsrfAreIndependent() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("writer", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.result").value("created"));

        // Có quyền ghi nhưng thiếu CSRF token vẫn bị chặn.
        mvc.perform(post("/api/reports")
                .with(httpBasic("writer", "demo-pass")))
            .andExpect(status().isForbidden());

        // Có token CSRF nhưng thiếu authority ghi cũng bị từ chối.
        mvc.perform(post("/api/reports")
                .with(httpBasic("alice", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminRuleAndFallback() throws Exception {
        mvc.perform(get("/admin/status")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/admin/status")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/unlisted")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

Các test minh họa:

- **Path**: `GET /api/reports?page=2` vẫn khớp GET `/api/reports` khi không có header v2; query không được dùng để chọn path matcher.
- **Header**: người gọi có thể chuyển sang biến thể v2, nhưng cần authority `report:v2` thực sự.
- **Method**: POST dùng rule write, không phải rule GET.
- **CSRF**: một request POST có quyền nhưng không có CSRF token vẫn bị 403. Không nhầm 403 từ CSRF với 403 từ manager quyền.
- **Negative tests**: anonymous 401 với HTTP Basic, thiếu permission 403, URL không khai báo bị deny.
- **Authentication**: tests dùng `httpBasic` để đi qua cơ chế xác thực, không dùng header tự khai quyền hoặc `@WithMockUser` để làm giả việc kiểm tra mật khẩu.

### 9.3. Chạy và kết quả dự kiến

Cần JDK 17+, Maven và tải dependency khi chạy lần đầu. Tại thư mục chứa `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

**Kết quả mong đợi:** các bài test kết thúc thành công khi project/phiên bản/môi trường đúng. Đây là **thiết kế ví dụ và kỳ vọng**, không phải bản ghi Maven đã được thực thi trong tài liệu này.

Thử bằng curl (chỉ dành cho localhost; HTTP Basic có chứa credentials, production phải dùng HTTPS):

~~~bash
curl -i http://localhost:8080/health
# Dự kiến 200: {"status":"ok"}

curl -i http://localhost:8080/api/reports
# Dự kiến 401 HTTP Basic challenge

curl -i -u alice:demo-pass \
  'http://localhost:8080/api/reports?page=2'
# Dự kiến 200: {"version":"v1"}

curl -i -u bob:demo-pass \
  -H 'X-Api-Version: v2' \
  http://localhost:8080/api/reports
# Dự kiến 200: {"version":"v2"}

curl -i -u alice:demo-pass \
  -H 'X-Api-Version: v2' \
  http://localhost:8080/api/reports
# Dự kiến 403

curl -i -u admin:demo-pass http://localhost:8080/admin/status
# Dự kiến 200: {"status":"admin-ok"}

curl -i -u admin:demo-pass http://localhost:8080/unlisted
# Dự kiến 403
~~~

Để kiểm thử POST bằng curl với CSRF còn bật, client cần **CSRF token hợp lệ gắn với cơ chế lưu token/cookie/session**. Không gửi `curl -X POST` không CSRF rồi khẳng định kết quả 403 là do permission sai. Test MockMvc dùng `.with(csrf())` để mô phỏng yêu cầu hợp lệ và phân biệt hai loại lỗi.

Trong PowerShell trên Windows, có thể dùng `curl.exe` khi `curl` là alias khác.

## 10. Những khác biệt cần hiểu khi dùng nhiều SecurityFilterChain

Giả sử một hệ thống vừa có web session, vừa có API Basic hoặc Bearer:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Đây là **snippet cấu hình minh họa**; muốn dùng trong production cần quyết định CSRF, session, authentication providers và route đầy đủ. Chain thứ hai không có `securityMatcher(...)` tường minh nên thường là catch-all. `FilterChainProxy` xét chain theo thứ tự và **chọn chain đầu tiên phù hợp**, không cộng dồn các filters của cả hai chain.

**Phân biệt hai tầng first-match:**

| Tầng | Matcher | Kết quả |
| --- | --- | --- |
| Filter chain selection | `securityMatcher(...)` + thứ tự chain | Chọn **một** SecurityFilterChain |
| Authorization rule selection | `requestMatchers(...)` trong chain | Chọn **một** AuthorizationManager phù hợp |
| Authorization decision | `AuthorizationManager` đã chọn | Cho phép/từ chối request |
| Controller/service permission | Policy dựa vào dữ liệu nghiệp vụ | Có thể kiểm tra ownership, tenant, resource-level quyền |

`@Order` trên chain **không** điều khiển thứ tự các `requestMatchers` ở bên trong chain. Và `anyRequest().denyAll()` của chain API **không bảo vệ** request nằm ngoài `/api/**` khi request đó không đi vào chain API.

## 11. Debug matcher mà không làm lộ thông tin nhạy cảm

Khi một endpoint trả 401/403/404 ngoài dự kiến, đừng thay luôn `anyRequest().permitAll()` để “sửa nhanh”. Hãy kiểm tra theo thứ tự:

1. **Request thực tế** có method, path, contextPath, servletPath, query, header và dispatcher type gì?
2. Request **đi vào SecurityFilterChain nào**? Có `@Order`/`securityMatcher` nào bắt request sớm không?
3. Trong chain đó, **rule nào match đầu tiên**? Có matcher rộng che matcher hẹp không?
4. Manager của rule đó yêu cầu role/authority gì? `Authentication` có authorities thực sự nào?
5. Request có bị CSRF filter, CORS hoặc một filter trước đó chặn chưa?
6. Nếu request đã qua authorization nhưng trả 404, endpoint MVC có được map không?
7. Nếu áp dụng proxy/context path, các tầng có cùng hiểu đường dẫn và HTTP method không?

Có thể tăng logging Spring Security có chọn lọc trong **môi trường test**:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Không bật TRACE/DEBUG vô thời hạn trên production và không ghi header Authorization, cookie session, password, token hay dữ liệu cá nhân đầy đủ vào log. Một số log security có thể chứa đường dẫn và thông tin authentication nên phải có kiểm soát truy cập/retention.

### Bảng phân tích

| Hiện tượng | Khả năng | Hướng kiểm tra |
| --- | --- | --- |
| `/api/admin/**` truy cập được anonymous | Rule `/api/**.permitAll` đứng trước, chain khác bắt request | Thứ tự matcher/chain |
| User có role nhưng nhận 403 | Sai prefix authority, rule khác match trước, CSRF thiếu | Authentication authorities, selected rule, CSRF |
| `GET /shop/api/items` không khớp custom matcher | So `getRequestURI()` với app-relative path | ContextPath/ServletPath/PathInfo |
| Matcher header v2 không chạy | Matcher GET tổng quát đặt trước hoặc header value khác | Thứ tự rule, header và case |
| GET thành công nhưng POST 403 | POST authority khác hoặc CSRF token thiếu | HTTP method rule và CSRF riêng |
| Một URL nằm ngoài chain vẫn có response public | Không có catch-all chain | Chain coverage và securityMatcher |
| `/error` bị chặn | Dispatcher/error path chưa được xử lý | Rule dispatcher hoặc endpoint error |
| URL encoded kỳ lạ tạo 400/403 trước controller | HttpFirewall hoặc proxy/container normalization | Firewall, canonical path, reject policy |
| Query `?role=admin` không ảnh hưởng policy | Path matcher không xét query; đây có thể là hành vi đúng | Không cấp quyền dựa vào query |
| CORS preflight OPTIONS bị 401/403 | Thứ tự xử lý CORS, authentication hoặc matcher method | CORS config và OPTIONS handling |

## 12. Kinh nghiệm thiết kế RequestMatcher an toàn

### 12.1. Ưu tiên matcher rõ ràng, giới hạn phức tạp

Dùng `requestMatchers(HttpMethod.GET, "/api/items/**")` thay vì regex phức tạp nếu chỉ cần path và method. Regex/lambda custom nên có lý do cụ thể, có test positive/negative và comment mô tả điều kiện. Tránh nhân bản logic path parsing ở nhiều lớp.

### 12.2. Đừng dùng dữ liệu dễ giả làm quyền truy cập

Header, query, cookie và IP là thông tin request; chúng không tự xác thực identity. Dùng `hasRole`, `hasAuthority` hoặc policy service dựa trên nguồn đáng tin và Authentication đã được xác minh. Với Bearer/JWT, phải kiểm tra chữ ký, issuer/audience, expiry, scopes/claims theo cấu hình; không tin payload chỉ vì decode được.

### 12.3. Luôn có test cho matcher chồng lấp

Với rule v2 và GET tổng quát, viết test “v2 + user chỉ có report:read phải 403” để phát hiện ai đó vô tình đảo thứ tự. Test “v1 + user chỉ có report:v2 phải 403” để bảo đảm không có quyền được hiểu lầm như bao hàm nhau.

### 12.4. Chọn deny by default khi yêu cầu

Một fallback rõ ràng giảm rủi ro endpoint mới được tạo nhưng quên đưa vào policy. Tuy nhiên phải khai báo public assets, health, login, error và management paths phù hợp. Không chữa mọi 403 bằng `anyRequest().permitAll()`.

### 12.5. Authorization theo dữ liệu cần tầng nghiệp vụ

`RequestMatcher` giỏi phân loại request theo URL/method; nó không biết user có được sở hữu object `order-123` hay không. Kiểm tra tại service/method với `@PreAuthorize` (khi đã bật method security) hoặc policy riêng, dựa trên object đã được tải và tenant/user đáng tin.

### 12.6. Đặt ra test matrix trước khi production

Ma trận nên bao gồm:
- URL bình thường và URL có trailing slash.
- HTTP methods GET/POST/PUT/DELETE/HEAD/OPTIONS phù hợp.
- Query parameter khác nhau trên cùng path.
- Header/version đúng, sai hoặc không có.
- Anonymous, user quyền thấp, user có permission, admin.
- ContextPath/ServletPath khi deploy không ở root.
- CSRF/CORS, dispatcher/error/forward nếu liên quan.
- URL encoded và proxy rewrite theo policy cho phép.
- Endpoint không liệt kê và chain fallback.
- Negative tests cho cross-tenant/ownership ở service.

## 13. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| RequestMatcher xác thực user | Matcher chỉ kiểm tra request có thuộc phạm vi hay không |
| RequestMatcher luôn dựa vào URL | Matcher có thể xét method, header, query, dispatcher... |
| `getRequestURI()` chỉ gồm path app-relative | Thường gồm contextPath; cần hiểu servlet mapping |
| Query string là phần của `getServletPath()` | Không; query có API riêng |
| Header `X-Role: ADMIN` chứng minh quyền ADMIN | Sai, client có thể tự đặt header |
| Cứ match header v2 thì user được sử dụng API v2 | Không; manager vẫn phải kiểm tra permission |
| Matcher rộng đặt sau sẽ “cứu” rule đầu bị deny | Không; chọn matcher đầu tiên khớp |
| `securityMatcher` và `requestMatchers` là một | Một cái chọn chain, một cái chọn rule |
| Chỉ có API chain là mọi URL được bảo vệ | URL ngoài chain có thể không qua Spring Security |
| `permitAll()` tắt CSRF và mọi filter | Không; request vẫn đi qua chain |
| 403 luôn là thiếu role | Có thể do CSRF/authorization/filter khác |
| Same-site query, URI và header luôn đã được normalize giống MVC | Có thể khác qua container/proxy/firewall |
| `GET /api/items` và `POST /api/items` dùng cùng quyền | Phải khai báo/test method policy |
| `hasRole("ADMIN")` chấp nhận mọi authority có chữ ADMIN | Mặc định kiểm tra `ROLE_ADMIN` chính xác |
| Có HTTP authorization thì không cần ownership check | Cần service/method authorization cho dữ liệu cụ thể |

## 14. Tự kiểm tra

**1. `RequestMatcher` trả lời câu hỏi gì?**

Nó kiểm tra request HTTP hiện tại có khớp tiêu chí đã định hay không; nó **không** quyết định password đúng hay tự cấp quyền.

**2. `getRequestURI()`, `getServletPath()` và `getQueryString()` khác nhau ra sao?**

Request URI thường chứa context path nhưng không query; ServletPath biểu thị phần đường liên quan servlet mapping, thường app-relative trong MVC root servlet; query có accessor riêng. Khi servlet mapping khác, PathInfo/ServletPath có thể thay đổi.

**3. Path matcher `/api/reports` có tự phân biệt `?page=1` và `?page=2` không?**

Thông thường không. Query không thuộc path; muốn phân biệt query phải chọn matcher có xét parameter và phải đánh giá tính an toàn của mục đích đó.

**4. `X-Api-Version: v2` có chứng minh user có `report:v2` không?**

Không. Header do client gửi chỉ chọn policy; authority phải đến từ Authentication/nguồn đáng tin sau kiểm tra credentials hoặc token.

**5. Vì sao matcher header v2 phải đặt trước matcher GET tổng quát cho `/api/reports`?**

Vì `RequestMatcherDelegatingAuthorizationManager` chọn rule đầu tiên có matcher khớp. Nếu GET tổng quát đứng trước, v2 rule sẽ bị che.

**6. User có report:write nhưng POST thiếu CSRF token có thể nhận 403 không?**

Có. CSRF kiểm tra request độc lập với rule authorization và có thể từ chối trước khi manager kiểm tra quyền.

**7. `securityMatcher("/api/**")` có bảo vệ `/admin/**` không?**

Không. Nó chỉ xác định chain API xử lý `/api/**`; cần chain khác/catch-all để bảo vệ URL ngoài phạm vi đó.

**8. Có nên dùng `?role=ADMIN` để chọn rule permitAll không?**

Không. Dữ liệu query do client tự điều khiển, không phải bằng chứng quyền. Dùng authority đã xác minh.

**9. Vì sao custom matcher so trực tiếp `getRequestURI()` với `"/api/reports"` có thể lỗi sau deploy `/shop`?**

Vì getRequestURI có thể là `/shop/api/reports`. Cần hiểu context path, servlet mapping hoặc dùng matcher framework phù hợp.

**10. `DispatcherType.ERROR` bị chặn có nghĩa user không có role không?**

Không nhất thiết. Có thể là authorization được chạy lại trong error dispatch và fallback chặn. Phải xem selected chain/rule, dispatcher và luồng error.

**11. Vì sao cần test positive và negative cho matcher?**

Positive chứng minh request hợp lệ được phép; negative chứng minh matcher rộng/overlap/client header không vô tình bypass permission, và fallback thực sự từ chối.

**12. Có RequestMatcher theo URL là đủ bảo vệ dữ liệu đa tenant không?**

Không. HTTP matcher không tự biết ownership/tenant của một bản ghi. Cần policy service/method dựa vào identity đáng tin và dữ liệu thực.

**Ghi nhớ:** **`RequestMatcher` là phép kiểm tra trên `HttpServletRequest`; matcher có thể xét path, method, header, query, dispatcher và nhiều thuộc tính khác. `securityMatcher` chọn filter chain, `requestMatchers` chọn rule authorization đầu tiên khớp. Tuyệt đối không coi dữ liệu client tự khai là quyền; chỉ `AuthorizationManager` và các chính sách dựa trên identity đáng tin mới quyết định được phép truy cập.**