# Kiểm tra tài nguyên tĩnh, endpoint lỗi và Actuator trong chính sách truy cập

> **Module:** Spring Security - servlet. **Nhóm:** Phân quyền HTTP. Ví dụ triển khai cho Java 17+, Spring Boot 3.x, Spring Security 6.x và Servlet/Spring MVC. Bài học tập trung vào **thiết kế và kiểm thử chính sách truy cập** cho ba bề mặt rất dễ bị cấu hình sai: tài nguyên tĩnh, endpoint xử lý lỗi và Actuator.

## 1. Vì sao ba nhóm URL này cần được kiểm tra riêng?

Một ứng dụng web có các endpoint nghiệp vụ như `/account`, `/orders`, `/admin/reports`. Nhưng khi thêm Spring Security, không chỉ controller nghiệp vụ mới chịu tác động của `SecurityFilterChain`:

1. **Tài nguyên tĩnh** như CSS, JavaScript, favicon, ảnh hoặc webjars thường phải được tải bởi người dùng chưa đăng nhập để trang login hiển thị đúng. Cho phép quá rộng hoặc dùng `web.ignoring()` không cần thiết có thể bỏ qua một số security filters và headers.
2. **Endpoint lỗi** như `/error` có thể được Servlet container gọi bằng **`DispatcherType.ERROR`** sau một lỗi xảy ra ở request gốc. Nếu authorization chạy lại trên error dispatch và không được xử lý, ứng dụng có thể chuyển lỗi 404/500 thành redirect login hoặc gây xử lý lỗi vòng lặp. Ngược lại, mở toàn bộ error handling mà trả stack trace, session data hoặc request details là nguy hiểm.
3. **Spring Boot Actuator** cung cấp endpoint vận hành như `/actuator/health`, `/actuator/info`, `/actuator/metrics` và nhiều endpoint có dữ liệu nhạy cảm hơn. Quyết định endpoint nào **được expose** khác với quyết định **ai được truy cập** endpoint đã expose.

Ba bề mặt không thể giải quyết bằng một câu `requestMatchers("/**").permitAll()`, cũng không nên mặc định bắt mọi tài nguyên về trang login. Cần một policy có thứ tự rõ và test đúng cả trạng thái anonymous lẫn authenticated.

**Nguyên tắc bao quát:** phân loại URL theo mục đích, hạn chế công khai, áp đúng authorization với từng bề mặt, và kiểm tra rằng request được phép không đồng nghĩa có dữ liệu nhạy cảm được tiết lộ.

## 2. Chuỗi xử lý HTTP: matcher chọn chain và matcher kiểm tra quyền

Trong Spring Security Servlet, `FilterChainProxy` chọn một `SecurityFilterChain` phù hợp với request, sau đó các filter trong chain thực hiện nhiệm vụ, trong đó authorization thường được thực thi bởi `AuthorizationFilter`.

```text
Browser / API client / monitoring agent
                 |
                 v
        Servlet container
                 |
                 v
   DelegatingFilterProxy ("springSecurityFilterChain")
                 |
                 v
   FilterChainProxy chọn SecurityFilterChain
                 |
                 +--> CsrfFilter (khi áp dụng)
                 +--> Authentication filters
                 +--> AuthorizationFilter
                           |
                 Thứ tự các authorization rules
                           |
          +----------------+-----------------+
          |                |                 |
      static CSS/JS    ERROR dispatch   Actuator health/metrics
          |                |                 |
      permitAll?       permitAll?       public hay role OPS?
          |                |                 |
          +----------------+-----------------+
                           |
                      MVC / Actuator
                           |
                  status/body/headers
```

Hai khái niệm rất dễ nhầm:

- **`http.securityMatcher(...)`**: giới hạn **cả filter chain**. Một URL nằm ngoài chain thì mọi rule và security filter trong chain đó đều không được áp dụng.
- **`authorizeHttpRequests(...requestMatchers(...))`**: xác định policy cho request **đã vào chain**. Những rule này thường được xét theo thứ tự khai báo, gặp rule khớp đầu tiên sẽ quyết định access.

Do đó phải đặt rule cụ thể trước rule tổng quát, ví dụ:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

Đây chỉ là fragment, không phải một ứng dụng độc lập. Nếu đảo `.anyRequest().authenticated()` lên trước rule admin, rule phía sau có thể không được đăng ký/không còn đường thực thi; policy trở nên sai hoặc config bị từ chối. Khi tạo nhiều chains với `@Order`, cũng phải xem chain được chọn trước, vì chain match-all có ưu tiên cao có thể chặn chain riêng cho Actuator hoặc web.

## 3. Tài nguyên tĩnh: nên public cái gì, bảo vệ cái gì?

Ví dụ dự án Spring Boot có:

```text
src/main/resources/
└── static/
    ├── css/site.css
    ├── js/app.js
    ├── images/logo.svg
    └── favicon.ico
```

Khi dùng cấu hình MVC thông dụng, file `classpath:/static/css/site.css` được phục vụ theo URL **`/css/site.css`**, không phải `/static/css/site.css`. Những vị trí mặc định khác có thể gồm `/public`, `/resources`, `/META-INF/resources` và WebJars tùy thư viện/cấu hình. Cần đọc **URL public thực tế**, không chỉ tên thư mục trong source tree.

Các nhóm thường gặp:

| Nhóm | Chính sách thường hợp lý | Rủi ro nếu làm sai |
| --- | --- | --- |
| CSS/JS cần để render login | `permitAll()` | Anonymous bị redirect, login bị mất style hoặc loop |
| Favicon, logo, ảnh marketing public | `permitAll()` | Trả 302/401 không cần thiết |
| `/webjars/**` cho trang public | `permitAll()` khi thực sự dùng | Chặn thư viện UI hoặc phơi quá nhiều assets ngoài ý muốn |
| JavaScript chứa nhúng API secret | **Không được đặt trong public static assets** | Mọi người tải được file; authorization URL không chữa được secret đã đóng gói |
| File xuất báo cáo của người dùng | Endpoint/controller + authorization theo owner/tenant | `permitAll("/downloads/**")` có thể lộ dữ liệu |
| Attachment cá nhân lưu dưới `/static/private/` | Không nên đặt ở static directory public | Dễ bị public matcher rộng hoặc cache/CDN phơi nội dung |
| File upload từ user | Object storage hoặc handler có kiểm tra quyền/loại tệp | XSS/content-sniffing/malware nếu phục vụ sai Content-Type |

**Quan trọng:** không dùng đường dẫn URL để tự kết luận file an toàn. Chỉ những asset đã được phân loại công khai mới được `permitAll`. Với file tùy người dùng, hãy đặt bên ngoài các static-resource locations công khai và phục vụ qua controller/resource handler kiểm tra quyền hoặc signed URL có chính sách rõ.

### 3.1. `PathRequest.toStaticResources().atCommonLocations()`

Spring Boot có helper cho các vị trí tài nguyên tĩnh thông dụng:

```java
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;

// Dùng trong authorizeHttpRequests của HttpSecurity.
.requestMatchers(PathRequest.toStaticResources().atCommonLocations())
    .permitAll()
```

Helper này tránh viết thủ công một danh sách URL dễ thiếu như `/css/**`, `/js/**`, `/images/**`, `/webjars/**`. Nhưng nó **không tự động nhận mọi thư mục tùy biến**. Khi thay resource handler locations, static path pattern hoặc đặt assets dưới URL khác, kiểm tra lại matcher thực tế và bổ sung rule hẹp theo nhu cầu.

Ví dụ file `/assets/vendor/theme.css` được phục vụ bằng một custom resource handler thì không được mặc định giả định helper sẽ match. Cũng không nên `permitAll("/**/*.css")` theo đuôi file nếu controller có resource động hoặc URL nhạy cảm vô tình kết thúc bằng `.css`.

### 3.2. `permitAll()` khác `web.ignoring()`

Hai cách làm này **không tương đương**:

```java
// Thông thường nên ưu tiên:
.requestMatchers(PathRequest.toStaticResources().atCommonLocations())
    .permitAll()
```

```java
// Ví dụ cấu hình bỏ qua chain; cần cân nhắc cẩn thận:
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring().requestMatchers("/css/**");
}
```

Đoạn thứ hai là fragment riêng, cần import `WebSecurityCustomizer`, chỉ để minh họa khác biệt; **không thêm nó vào ví dụ chính bên dưới**.

- Với `permitAll()`, request **vẫn đi qua Spring Security filter chain**, do đó các security headers, chính sách tương ứng và cơ chế filter vẫn có cơ hội hoạt động. Rule authorization cuối cùng cho phép request.
- Với `web.ignoring()`, request khớp thường **bỏ qua Spring Security chain**, tức là các bảo vệ do chain cung cấp không chạy trên đường đó. Không dùng chỉ vì cho rằng static resource "không cần kiểm tra quyền".
- `permitAll()` trong Spring Security 6 được tối ưu để không cần lấy `Authentication` cho nhánh cho phép, giảm lo ngại hiệu năng so với việc bỏ qua chain.
- Một resource static bị thiếu vẫn có thể trả **404**, nhưng nếu rule không cho phép anonymous, request có thể bị chặn/redirect **trước khi MVC xác định file không tồn tại**.

Nên áp dụng `permitAll` cho tài nguyên công khai; chỉ dùng ignoring khi có yêu cầu rõ, hiểu mất các filters/headers và có test xác nhận.

## 4. Đường dẫn favicon, trang login và asset bị chặn

Một tình huống phổ biến: trang GET `/login` hoạt động nhưng CSS bị tải thất bại.

```text
GET /login                 -> HTTP 200 HTML
GET /css/site.css          -> HTTP 302 Location: /login
GET /js/app.js             -> HTTP 302 Location: /login
GET /favicon.ico           -> HTTP 302 Location: /login
```

Về giao diện, browser có thể nhìn như trang không có style hoặc JS không chạy, còn backend không báo lỗi bảo mật rõ ràng. Cách sửa **không phải** `anyRequest().permitAll()`. Hãy cho phép chính xác assets cần cho trang chưa đăng nhập.

Nếu trang login custom có assets dưới `/login-assets/**`, đặt một rule dành riêng cho đường này. Nếu có đăng ký URL xử lý login `/login` hay `/auth/signin`, phân biệt nó với đường tải CSS/JS; xử lý POST login, CSRF và GET login là cơ chế riêng.

Trường hợp `/favicon.ico` có thể được xử lý theo location hoặc pattern khác helper common static; khi cần, dùng matcher cụ thể `.requestMatchers("/favicon.ico").permitAll()`. Nếu file không tồn tại, kỳ vọng có thể là 404 thay vì 302, và đó là điều cần xác nhận.

## 5. Endpoint lỗi: phân biệt URL `/error` với `DispatcherType.ERROR`

Spring Boot có cơ chế xử lý lỗi HTTP, thường sử dụng endpoint `/error` do `BasicErrorController` hoặc custom `ErrorController` xử lý. Nhưng một error dispatch **không đơn giản là một GET bình thường có path `/error`**.

Servlet định nghĩa các loại dispatch như:

- `DispatcherType.REQUEST`: request thông thường từ client.
- `DispatcherType.ERROR`: container dispatch trong quá trình xử lý lỗi.
- `DispatcherType.FORWARD`: server-side forward tới tài nguyên khác.
- `DispatcherType.INCLUDE`, `ASYNC`: các trường hợp dispatch khác cần hiểu nếu ứng dụng dùng.

Trong Spring Security 6, authorization có thể được đánh giá trên các dispatch phù hợp, không chỉ request gốc. Nếu một request dẫn tới lỗi được container gửi lại tới `/error`, đoạn error dispatch có thể bị authorization rule chặn vì `SecurityContext` không được coi là authenticated tại dispatch đó hoặc vì matcher mặc định chưa cho phép.

Để xử lý theo chính sách:

```java
import jakarta.servlet.DispatcherType;

.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
    // Các rule khác.
)
```

**Ý nghĩa:** server-generated ERROR dispatch được phép đi qua authorization để render/trả response lỗi; không tự biến request **REQUEST** ban đầu thành public. Browser không thể chỉ gửi một HTTP header tự đặt để thay đổi `HttpServletRequest.getDispatcherType()` thành `ERROR`: loại dispatch do Servlet container quyết định.

### 5.1. Có nên cho phép `/error` theo path?

Trong một số ứng dụng, có thể có:

```java
.requestMatchers("/error").permitAll()
```

Quy tắc này cho phép path `/error` cả ở request bình thường phù hợp, trong khi `dispatcherTypeMatchers(ERROR)` nhắm tới **loại dispatch**. Hai quy tắc có phạm vi khác nhau. Cần chọn theo kiến trúc lỗi và cách framework forward/error dispatch. Ví dụ đầy đủ bên dưới dùng cả hai để trình diễn các ý nghĩa và tránh vòng lặp trên error endpoint mặc định.

Tuy nhiên cho phép tới trang lỗi **không có nghĩa** được để lộ:

- Stack trace, exception class, nội dung message nhạy cảm.
- Header `Authorization`, cookie, session ID, CSRF token.
- SQL exception hoặc cấu hình backend.
- Thông tin domain khác tenant hoặc private payload trong error attributes.

Một endpoint lỗi công khai nên dùng thông tin tối thiểu, status phù hợp và correlation ID đã giảm nhạy cảm.

### 5.2. Có nên cho phép `DispatcherType.FORWARD` không?

Một số ứng dụng dùng `RequestDispatcher.forward(...)` hoặc view resolver để forward nội bộ tới JSP/template. Khi đó `DispatcherType.FORWARD` có thể cần được xử lý riêng. Có thể cân nhắc:

```java
.dispatcherTypeMatchers(
    DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
```

Đây là **fragment tùy chính sách**, không phải khuyến nghị mở FORWARD vô điều kiện. Nếu application code có thể forward vào một controller/resource nhạy cảm từ request public, cho phép mọi FORWARD có thể làm mất lớp authorization tại dispatch đích. Phải kiểm tra tính đáng tin cậy của điểm phát forward và rule của request gốc. Ví dụ chính chỉ tự động cho phép `ERROR`, không mở rộng `FORWARD`.

### 5.3. Phân biệt "lỗi xử lý" và "thiếu quyền"

Một request anonymous tới `/admin/reports` thường bị Spring Security chặn và đưa tới `AuthenticationEntryPoint` (redirect login hoặc 401), **không nhất thiết tạo Servlet ERROR dispatch**. Một user đã xác thực nhưng không đủ role có thể nhận 403 từ `AccessDeniedHandler`; cũng không phải mọi 403 đều đi qua `/error`.

Vì vậy đừng lấy một test status 302 rồi kết luận `/error` được bảo vệ sai. Muốn test error dispatch thực sự cần kích hoạt luồng lỗi trong **Servlet container**, hoặc trong unit/MockMvc kiểm tra riêng việc request mang `DispatcherType.ERROR` khớp authorization rule.

## 6. Kiểm thử error endpoint an toàn

Một ứng dụng Boot có thể cấu hình error body ít tiết lộ thông tin trong production:

```yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
```

Các cấu hình này làm giảm việc phản hồi chứa diagnostic details. Nó **không thay thế** bảo mật dữ liệu ở exception handlers, access logs, reverse proxy hoặc custom error controller. Với lỗi authentication/authorization, nên giữ `401`/`403` và body tối thiểu theo API contract; không chuyển mọi lỗi thành HTTP 200 cùng một trang HTML.

Các kiểm thử hữu ích:

1. Anonymous GET một URL không tồn tại nhưng thuộc nhóm public static → **không bị redirect login**, thường là 404.
2. Anonymous GET một URL private → **không được trả private data**, có thể redirect login hoặc 401.
3. Error dispatch từ controller gây lỗi → status/response phù hợp 404/500, không có redirect login vòng lặp.
4. Direct REQUEST `/error` → hành vi được định nghĩa và không lộ stacktrace.
5. Request từ user thiếu role → 403/authorization handling đúng, không lộ dữ liệu admin.
6. Không có thông tin nội bộ bị trả cho anonymous trong JSON/HTML error body.

Một bài test `MockMvc` với `request.setDispatcherType(ERROR)` chứng minh rule dispatcher, nhưng **chưa mô phỏng đầy đủ** container thật tự redispatch sau exception. Kết hợp cả `MockMvc` và HTTP integration test trên web server thực tế.

## 7. Actuator: exposure, authentication, authorization là ba lớp khác nhau

Spring Boot Actuator cung cấp các endpoint hỗ trợ quan sát và quản lý ứng dụng. Chúng là một bề mặt HTTP quan trọng, không phải "một nhóm URL chỉ cho nội bộ" theo tên gọi.

Ba quyết định cần tách biệt:

1. **Endpoint có tồn tại và được expose qua web không?** Quyết định bởi dependency `spring-boot-starter-actuator`, khả năng enable endpoint và `management.endpoints.web.exposure.*` (cùng các tùy chọn availability khác tùy Spring Boot version).
2. **Endpoint nào được phép truy cập không cần đăng nhập?** Ví dụ health phục vụ load balancer.
3. **Ai được phép xem endpoint đã expose còn lại?** Role vận hành `OPS`, admin, monitoring identity hoặc service-to-service security; cần kiểm soát mạng thêm nếu dữ liệu nhạy cảm.

Một rule `requestMatchers("/actuator/**").permitAll()` rất nguy hiểm khi một ngày ai đó expose thêm `env`, `beans`, `configprops`, `heapdump`, `threaddump`, `loggers` hoặc endpoint thay đổi cấu hình. Không phải endpoint nào cũng lộ secret trong mọi cấu hình, nhưng **không mở toàn bộ actuator chỉ vì muốn health check public**.

### 7.1. Dùng `EndpointRequest` thay vì hardcode mọi path

Spring Boot Actuator có matcher:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;

// Ví dụ fragment trong authorizeHttpRequests:
.requestMatchers(EndpointRequest.to("health")).permitAll()
.requestMatchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
```

`EndpointRequest` biết các Actuator endpoints trong application context được cấu hình và ít phụ thuộc hơn vào đường dẫn `/actuator` mặc định. Điều này hữu ích khi thay `management.endpoints.web.base-path` hoặc cấu hình endpoint mapping. **Rule có thứ tự**: health public phải đứng trước matcher `toAnyEndpoint()`, nếu không health có thể bị yêu cầu quyền OPS.

Đừng nhầm:

- `EndpointRequest.to("health")`: matcher cho Actuator health endpoint (bao gồm đường dẫn liên quan theo phiên bản/cấu hình).
- `EndpointRequest.toAnyEndpoint()`: matcher các Actuator endpoints phù hợp trong context, **không tự expose** endpoint chưa được bật/exposed.
- `management.endpoints.web.exposure.include`: chỉ định endpoint nào được xuất ra web, **không** có nghĩa ai cũng được phép xem.

### 7.2. Chọn mức exposure tối thiểu

Với demo, có thể chủ động expose:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: never
```

Đây là ví dụ cho một ứng dụng đơn giản. `health` có thể được public để load balancer biết trạng thái chung; `info` và `metrics` yêu cầu `ROLE_OPS`. Trong production, health details có thể chứa thông tin về database/queue/disk, vì vậy policy `show-details`, health groups, probes và internal/external endpoints phải được thiết kế theo audience. `info` có thể trống nếu chưa cấu hình contributor; không có nghĩa nó tự an toàn cho mọi deployment.

**Không nên expose `*\`** (mọi actuator endpoints) chỉ vì thuận tiện quan sát; hãy tạo allowlist endpoint thật sự cần dùng, thêm authorization và giới hạn network.

### 7.3. Actuator khác controller theo path

Một controller tự viết `@GetMapping("/actuator/custom")` không tự nhiên biến thành Actuator endpoint để `EndpointRequest.toAnyEndpoint()` nhận biết. Tương tự, một URL `/actuator/does-not-exist` có thể không match `EndpointRequest` và đi tới catch-all rule. Nếu bạn thêm controller trên prefix quản trị, phải bổ sung policy riêng và test, không chỉ tin vào URL prefix hay `EndpointRequest`.

## 8. Trường hợp Actuator chạy ở management port/context riêng

Spring Boot có thể dùng một management port khác với application port:

```yaml
management:
  server:
    port: 9090
```

Khi đó quản lý có thể được phục vụ trong **management server/application context** khác; security chain áp dụng cho port ứng dụng không được mặc nhiên xem là policy bảo vệ toàn bộ Actuator ở port 9090. Phải xác minh các filter chains/auto-config và security rules trong **cả hai context**. Thiết lập firewall, mạng riêng, mTLS hoặc xác thực service-to-service theo yêu cầu vận hành.

Các ví dụ và test ở phần sau giả định **Actuator chạy cùng application port/context** (mặc định nếu không đặt `management.server.port`). Không copy kết quả MockMvc đó để chứng minh management port riêng đã an toàn.

Trường hợp `management.endpoints.web.base-path=/manage`, đường URL có thể đổi từ `/actuator/health` sang `/manage/health`; `EndpointRequest` thích nghi tốt hơn hardcode `/actuator/**`, nhưng integration test vẫn cần xác minh URL, health groups và scope chính xác.

## 9. Bảng chính sách mẫu trước khi viết code

Ta muốn:

- Assets CSS/JS/images và favicon public.
- Public page `/public` public.
- Error dispatch được phép render lỗi; response không lộ exception details.
- Health Actuator public, chỉ trả trạng thái tổng quát.
- Info/metrics Actuator cần `ROLE_OPS`.
- `/admin/**` cần `ROLE_ADMIN`.
- `/account` và URL nghiệp vụ chưa phân loại cần đăng nhập.
- Form login mặc định phục vụ browser; CSRF vẫn bật.

| Yêu cầu | Anonymous | User thường | OPS | ADMIN |
| --- | --- | --- | --- | --- |
| GET /css/site.css | 200 | 200 | 200 | 200 |
| GET /js/app.js | 200 | 200 | 200 | 200 |
| GET /public | 200 | 200 | 200 | 200 |
| GET /actuator/health | 200 | 200 | 200 | 200 |
| GET /actuator/info | Redirect login | 403 | 200 | 403 nếu ADMIN không có OPS |
| GET /actuator/metrics | Redirect login | 403 | 200 | 403 nếu ADMIN không có OPS |
| GET /account | Redirect login | 200 | 200 | 200 |
| GET /admin/report | Redirect login | 403 | 403 nếu OPS không có ADMIN | 200 |
| GET /dispatch-probe, REQUEST bình thường | Redirect login | 200 | 200 | 200 |
| Internal ERROR dispatch tới /dispatch-probe | Cho qua authorization | Cho qua | Cho qua | Cho qua |
| GET /css/missing.css | Thường 404 nếu path public | Thường 404 | Thường 404 | Thường 404 |

**Lưu ý:** bảng phân biệt **role scopes độc lập**, không giả định `ADMIN` luôn bao hàm `OPS`. `hasRole("OPS")` kiểm tra authority `ROLE_OPS`; `hasRole("ADMIN")` kiểm tra `ROLE_ADMIN` theo role prefix mặc định. Mã HTTP và redirect thực tế có thể thay đổi theo authentication entry point và custom handlers.

## 10. Ví dụ Spring Boot 3.x / Spring Security 6.x / Java 17+

Đây là ví dụ học tập chạy trên Servlet MVC, một `SecurityFilterChain` chung, Actuator cùng port. Để tái tạo, tạo Spring Boot 3.x Gradle project có Java 17, thêm dependencies, rồi đặt các file theo đúng đường dẫn.

### 10.1. Gradle dependencies

Với project đã có Spring Boot Gradle plugin và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 10.2. Main application + security config + controller

Tệp `src/main/java/example/accesspolicy/AccessPolicyApplication.java`:

```java
package example.accesspolicy;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AccessPolicyApplication {

    public static void main(String[] args) {
        SpringApplication.run(AccessPolicyApplication.class, args);
    }
}

@Configuration
class AccessSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // Servlet container tự dispatch khi xử lý lỗi.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()

                // Chỉ các vị trí static thông dụng đã phân loại public.
                .requestMatchers(
                    PathRequest.toStaticResources().atCommonLocations()
                ).permitAll()
                .requestMatchers("/favicon.ico", "/public", "/error")
                    .permitAll()

                // Exposure và authorization của Actuator là 2 lớp riêng.
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .requestMatchers(EndpointRequest.toAnyEndpoint())
                    .hasRole("OPS")

                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            // Không disable CSRF; ứng dụng có form login browser.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer-pass"))
            .roles("USER")
            .build();

        UserDetails operator = User.withUsername("operator")
            .password(encoder.encode("operator-pass"))
            .roles("OPS")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(viewer, operator, admin);
    }
}

@RestController
class AccessController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/account")
    String account(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/admin/report")
    String adminReport() {
        return "admin report";
    }

    @GetMapping("/dispatch-probe")
    String dispatchProbe() {
        return "dispatch-probe";
    }
}
```

**Đây là một tệp Java 17 hợp lệ:** chỉ `AccessPolicyApplication` là public, hai top-level class còn lại package-private và thuộc package được component scan. Các imports `PathRequest`/`EndpointRequest` thuộc **Spring Boot**, `DispatcherType` thuộc **`jakarta.servlet`**, còn `SecurityFilterChain` thuộc Spring Security.

**Các chi tiết quyết định tính an toàn của code:**

- Rule `DispatcherType.ERROR` đứng trước rule `anyRequest().authenticated()`, để lỗi nội bộ có thể render response mà không redirect login do kiểm tra lại quyền.
- `PathRequest` cho phép các tài nguyên thông dụng; không mở toàn bộ `/**`.
- `/error` được phép để tránh error rendering bị authentication challenge trong ví dụ; production phải sanitize error response.
- `EndpointRequest.to("health")` đứng **trước** `toAnyEndpoint()`: public health, còn endpoint khác phải có `ROLE_OPS`.
- `/admin/**` cần `ROLE_ADMIN` riêng, không cho OPS vượt quyền.
- `anyRequest().authenticated()` là catch-all; với API yêu cầu zero trust nghiêm ngặt, có thể chọn `denyAll()` rồi allowlist mọi route chủ đích, nhưng khi đó phải khai báo `/account` cụ thể.
- `formLogin` chỉ là authentication cơ bản để học authorization. Nếu production cần login MFA, JWT hoặc mTLS cho Actuator thì phải thiết kế bổ sung đúng threat model.
- Mật khẩu và users đều chỉ để demo local; production phải dùng secret store, identity provider và HTTPS.

### 10.3. Cấu hình Actuator và error response

Tệp `src/main/resources/application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: never

server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
```

Để demo kiểm tra health, không thêm `management.server.port`: Actuator dùng cùng port app. `metrics` được expose **có chủ đích** và security rule yêu cầu `ROLE_OPS`. Không bật `management.endpoints.web.exposure.include: "*"` trong ứng dụng thật mà chưa có thiết kế rất chặt. `show-details: never` hạn chế chi tiết health cho mọi user trong ví dụ.

### 10.4. Tài nguyên tĩnh cần tạo

Tệp `src/main/resources/static/css/site.css`:

```css
body {
    color: #123456;
    font-family: sans-serif;
}
```

Tệp `src/main/resources/static/js/app.js`:

```javascript
window.accessPolicyDemoReady = true;
```

Tệp `src/main/resources/static/images/mark.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg"
     width="40" height="40" viewBox="0 0 40 40">
  <circle cx="20" cy="20" r="16" fill="#2563eb"/>
</svg>
```

Có thể tạo `src/main/resources/static/favicon.ico` nếu có favicon thật. Không bắt buộc có file favicon để test CSS/JS; nhưng route `/favicon.ico` được rule public và vẫn có thể trả 404 nếu không có file.

### 10.5. Chạy và quan sát

Từ root project đã có Gradle wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell: `./gradlew.bat bootRun`.

Khi app chạy ở localhost:8080:

```bash
curl -i http://localhost:8080/css/site.css
curl -i http://localhost:8080/js/app.js
curl -i http://localhost:8080/actuator/health
curl -i -H "Accept: text/html" http://localhost:8080/account
curl -i -H "Accept: text/html" http://localhost:8080/actuator/metrics
```

Kết quả **dự kiến**:

- CSS, JS: HTTP 200 khi file tồn tại.
- Actuator health: HTTP 200, JSON chứa trạng thái tổng quát như `{"status":"UP"}` trong demo hoạt động bình thường.
- Anonymous `/account`: thường redirect tới trang login với `formLogin`.
- Anonymous `/actuator/metrics`: không trả danh sách metrics; được dẫn tới login/entry point theo cấu hình.
- Operator đã login có `ROLE_OPS` có thể truy cập `/actuator/metrics`; viewer thiếu role phải bị từ chối.

Đây là hành vi **dự kiến từ code**, không phải output thu được từ một lần chạy thật. `curl` không tự có session login browser. Không thể chỉ thêm Basic credentials `curl -u` vào demo này và kỳ vọng HTTP Basic chạy, vì ví dụ **chỉ bật formLogin**, không bật `httpBasic`.

## 11. Test bằng MockMvc: tài nguyên tĩnh phải công khai nhưng admin/metrics không được mở

Spring Boot Test và Spring Security Test cho phép kiểm tra authorization ngay trong Servlet filter chain.

Tạo `src/test/java/example/accesspolicy/AccessPolicySecurityTest.java`:

```java
package example.accesspolicy;

import jakarta.servlet.DispatcherType;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccessPolicySecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void cssIsPublicAndServedAsRealStaticResource() throws Exception {
        mvc.perform(get("/css/site.css"))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("color:")));
    }

    @Test
    void javascriptIsPublic() throws Exception {
        mvc.perform(get("/js/app.js"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("accessPolicyDemoReady")));
    }

    @Test
    void imageIsPublic() throws Exception {
        mvc.perform(get("/images/mark.svg"))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("<circle")));
    }

    @Test
    void publicControllerIsPublic() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void healthIsPublicButShowsOnlyBasicStatus() throws Exception {
        mvc.perform(get("/actuator/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").exists());
    }

    @Test
    void anonymousCannotSeeActuatorMetrics() throws Exception {
        mvc.perform(get("/actuator/metrics")
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")));
    }

    @Test
    void normalUserCannotSeeActuatorMetrics() throws Exception {
        mvc.perform(get("/actuator/metrics")
                .with(user("viewer").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void opsUserCanSeeActuatorMetrics() throws Exception {
        mvc.perform(get("/actuator/metrics")
                .with(user("operator").roles("OPS")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.names").exists());
    }

    @Test
    void infoEndpointAlsoRequiresOps() throws Exception {
        mvc.perform(get("/actuator/info")
                .with(user("viewer").roles("USER")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/actuator/info")
                .with(user("operator").roles("OPS")))
            .andExpect(status().isOk());
    }

    @Test
    void adminPageRequiresDifferentRole() throws Exception {
        mvc.perform(get("/admin/report")
                .with(user("operator").roles("OPS")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin/report")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin report"));
    }

    @Test
    void anonymousBusinessEndpointRedirectsToLogin() throws Exception {
        mvc.perform(get("/account").accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")));
    }

    @Test
    void authenticatedUserCanSeeAccount() throws Exception {
        mvc.perform(get("/account")
                .with(user("viewer").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello viewer"));
    }

    @Test
    void errorDispatchAndNormalRequestUseDifferentRules()
            throws Exception {

        mvc.perform(get("/dispatch-probe")
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection());

        mvc.perform(get("/dispatch-probe")
                .with(request -> {
                    request.setDispatcherType(DispatcherType.ERROR);
                    return request;
                }))
            .andExpect(status().isOk())
            .andExpect(content().string("dispatch-probe"));
    }
}
```

Lệnh chạy:

```bash
./gradlew test
```

**Lưu ý về độ tin cậy của kiểm thử:** đoạn test được viết để chạy với project ví dụ cùng dependencies, nhưng **chưa được compile hoặc thực thi trong tài liệu này**. Response có thể khác khi phiên bản, classpath, ErrorController hoặc management context khác demo.

Những gì test chứng minh và không chứng minh:

- `get("/css/site.css")` trả 200 chứng minh **vừa được phép qua security vừa được MVC phục vụ file**. Chỉ `permitAll` không bảo đảm file thực tồn tại.
- `user("viewer").roles("USER")` là Spring Security Test request postprocessor **dựng principal đã xác thực**, phù hợp để test **authorization**; nó không kiểm thử password verification từ database.
- `get("/actuator/metrics").with(user("operator").roles("OPS"))` chứng minh OPS có quyền khi endpoint được expose. Nó không chứng minh endpoint đó chỉ lắng nghe trên mạng riêng hoặc management port an toàn.
- `request.setDispatcherType(DispatcherType.ERROR)` là **mô phỏng rule đánh giá loại dispatch trong mock environment**, không phải HTTP client có thể gửi dispatcher type tùy ý. Muốn test luồng 500/404 thực, hãy dùng embedded Servlet container và kích hoạt lỗi thật.
- Test Actuator dựa vào `application.yml` đã expose `health,info,metrics`. Nếu không expose metrics, response 404/không có handler sẽ không chứng minh rule OPS sai.
- Không dùng `@WithMockUser` hoặc `.with(user(...))` để chứng minh login endpoint hoạt động; đó là unit-level authentication setup của test.

## 12. Test bổ sung cho lỗi, tài nguyên thiếu và HTTP method

Một ứng dụng thường cần thêm các test ngoài happy path:

| Case | Vì sao phải test | Kỳ vọng/khả năng quan sát |
| --- | --- | --- |
| GET /css/missing.css | Public matcher không đồng nghĩa có resource | Thường 404, **không redirect login** |
| GET /css/site.css khi anonymous | Trang login phải load assets | 200 đúng MIME/body |
| GET /favicon.ico khi file không tồn tại | Đừng nhầm 404 với authorization fail | 404 hoặc fallback hợp lệ |
| GET /error trực tiếp | Kiểm tra safe error body | Không lộ stack trace/token |
| Container ERROR dispatch sau lỗi controller | Kiểm tra forwarding/error rendering | Không redirect login vòng lặp, status đúng |
| User anonymous GET /admin/report | Chặn controller private | Redirect login/401 theo entry point |
| User có ROLE_USER GET /admin/report | Không đủ quyền | 403 |
| Anonymous GET /actuator/health | Health public | 200, response tối thiểu |
| Anonymous GET /actuator/metrics | Vận hành không được public | Không trả danh sách metrics |
| ROLE_OPS GET /actuator/metrics | Operator có quyền | 200 nếu endpoint expose |
| POST tới endpoint Actuator hỗ trợ mutation | CSRF và permission | Không được phép nếu thiếu quyền hoặc CSRF |
| OPTIONS/preflight trên Actuator | CORS policy | Theo origin/method rules, không tự mở metrics |
| Management port riêng | Security có áp đúng context? | Cần test trên cả port app và port quản trị |
| Custom resource handler `/assets/**` | PathRequest có match không? | Bổ sung matcher hẹp nếu cần |
| HTTP `/actuator/env` chưa expose | Không thể truy cập | Không suy chỉ từ security rule rằng endpoint tồn tại |

### Tại sao 404 đôi khi thành 302?

Nếu anonymous yêu cầu `/css/missing.css` và security **không có public matcher** cho URL đó, authorization có thể kích hoạt login entry point trước khi resource handler phát hiện file thiếu. Kết quả là 302, không phải 404. Với static matcher đúng, request qua authorization, MVC xác định file thiếu và trả 404/error response hợp lệ.

### Error dispatch thực qua web server

Với servlet container thật, tạo một controller test-only có thể trả lỗi nội bộ, rồi kiểm tra `/error` hoặc custom error controller được dispatch đúng:

- Request gốc là `DispatcherType.REQUEST`.
- Container có thể thực hiện `DispatcherType.ERROR`.
- Response không bị thay bằng redirect login do error dispatch bị chặn.
- Không lộ stack trace hay private exception details.
- Nếu response trước đó đã commit, cơ chế error dispatch có giới hạn riêng, cần test cả tình huống ấy.

Không nên tạo một endpoint cố ý trả 500 ở môi trường production không được bảo vệ; các fixture phát sinh lỗi nên đặt trong test profile.

## 13. Khi cần nhiều `SecurityFilterChain`: tách UI, API và Actuator có kiểm soát

Một ứng dụng phức tạp có thể có nhiều chain, ví dụ:

```text
@Order(1): securityMatcher(EndpointRequest.toAnyEndpoint())
     -> health public, others ROLE_OPS
@Order(2): securityMatcher("/api/**")
     -> bearer token / stateless policy
@Order(3): match other requests
     -> form login, static resources, error handler
```

Đây là **sơ đồ thiết kế**, không phải code đầy đủ. Mỗi chain có authentication mechanisms, CSRF/session và authorization riêng. Nếu `EndpointRequest` match nhầm/không match, một Actuator endpoint có thể rơi vào web chain hoặc một chain catch-all và được xử lý sai. Nếu một chain tổng quát với độ ưu tiên cao xuất hiện trước actuator chain, các rule actuator phía sau có thể **không bao giờ chạy**.

Khi thiết kế multi-chain:

1. Ghi rõ matcher bao phủ đường nào và chain order.
2. Bảo đảm error dispatch vẫn được xử lý đúng, không làm lỗi security vòng lặp.
3. Không nhầm `web.ignoring` với một chain public có security headers.
4. Đảm bảo endpoints không thuộc chain nào chỉ khi đó là một quyết định **đã được phê duyệt**; bỏ lọt request có thể để trống lớp bảo vệ.
5. Test cả URL và dispatcher type, không chỉ một URL tĩnh ở chain đầu tiên.
6. Kiểm tra actuator exposure và security ở management context nếu tách port.

### `securityMatcher` khác `requestMatchers` trong thực tế

Nếu viết:

```java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/actuator/health").permitAll()
        .anyRequest().authenticated());
```

Đây là **fragment** và giả sử chỉ có chain match `/api/**`: rule health nằm bên trong chain không match `/actuator/health`, nên sẽ không được áp dụng cho health. Không sửa bằng cách nới `/api/**` thành `/**` tùy tiện; cần xác định đúng chain dành cho actuator.

## 14. CSRF, authentication method và Actuator management actions

Actuator có cả endpoint chỉ đọc và những endpoint có thể cho phép thao tác quản trị tùy cấu hình/phiên bản (ví dụ cấu hình log levels, shutdown nếu được enable, v.v.). Nếu app dùng browser session/form login, CSRF protection mặc định có thể chặn unsafe methods như POST/PATCH/DELETE trước khi action chạy.

Đừng disable CSRF toàn bộ chỉ để monitoring agent POST thành công. Nên phân loại:

- **Read-only health/info/metrics:** GET, bảo vệ authorization và network theo mục đích.
- **State-changing management endpoints:** cần phương thức xác thực mạnh, quyền vận hành hẹp, CSRF mitigation khi browser dùng ambient credentials, audit logs và network isolation.
- **Machine-to-machine scrapers:** thường dùng identity riêng, mTLS/bearer token hoặc cách không dựa vào browser session; không chuyển ngoại lệ của một scraper thành cho phép toàn bộ users.

Nếu cần cấu hình `csrf.ignoringRequestMatchers(...)` cho machine endpoints, chỉ thực hiện sau threat model chứng minh **không chấp nhận ambient browser credentials** và đã có cơ chế bảo vệ tương đương. `permitAll` chỉ là authorization, không đồng nghĩa tắt CSRF; `hasRole("OPS")` cũng không tự vô hiệu CSRF của POST.

## 15. Headers, caching, CORS và dữ liệu nhạy cảm

### 15.1. Static caching và bản quyền/secret

Public CSS/JS có thể được cache ở CDN/browser để giảm tải. Điều đó không đồng nghĩa có thể lưu private reports cùng đường static. Nếu đóng gói credentials hoặc cấu hình nội bộ trong JS, mọi người nhận public file đều có thể đọc; dù server-side URL cần `ROLE_ADMIN` cho API khác, secret đã lộ qua static asset không được bảo vệ.

Ngược lại, API trả dữ liệu theo tài khoản nên có authorization tại mỗi request và cache policy phù hợp; không phục vụ từ public CDN key chung nếu có dữ liệu riêng.

### 15.2. Security headers

`permitAll()` vẫn cho request qua Spring Security chain, nơi các header filters có thể thiết lập security headers phù hợp. `web.ignoring()` thường bỏ qua chúng. Không giả định mọi header được Spring Security tạo sẽ giữ nguyên sau CDN/proxy; test response qua public origin thật.

Một vài header cần xem xét:

- `Content-Security-Policy` cho tài nguyên web khi sử dụng để giảm rủi ro XSS.
- `X-Content-Type-Options: nosniff` để hạn chế kiểu MIME bị suy đoán.
- `Cache-Control` riêng cho private API và static assets.
- `Strict-Transport-Security` chỉ phát huy trên HTTPS với policy phù hợp.
- `Referrer-Policy` cho dữ liệu liên quan navigation.

Không cài "tất cả file static không cache" chỉ vì sợ lộ thông tin; dùng fingerprinted assets và cache public cho nội dung thực sự public, đồng thời bảo vệ private resources ở endpoint khác.

### 15.3. CORS không thay authorization Actuator

Nếu frontend ở origin khác cần gọi health/metrics, CORS policy ảnh hưởng browser JavaScript đọc response. Nó không thay authentication, authorization hoặc network ACL. Không dùng `Access-Control-Allow-Origin: *` bừa bãi cho endpoint vận hành có credential; cũng không coi CORS là firewall bảo vệ Actuator khỏi các client ngoài browser.

### 15.4. Liveness/readiness probes

Kubernetes/liveness/readiness probes có thể yêu cầu một health group hoặc URL khác `/actuator/health` theo cấu hình Boot. Cần quyết định có public probe trong mạng riêng hay require machine identity. Một `401` vì rule health sai có thể khiến container liên tục restart. Mở toàn bộ Actuator để "sửa probes" là sai phạm vi. Test đúng path, port, status và audience của từng probe.

## 16. Những lỗi cấu hình thường gặp

| Sai lầm | Triệu chứng hoặc rủi ro | Cách sửa |
| --- | --- | --- |
| Chặn mọi URL trừ `/login` | CSS/JS/favicon redirect tới login | `permitAll` cho static locations cần thiết |
| Dùng `web.ignoring("/**")` | Bỏ toàn bộ Spring Security | Chỉ permit những tài nguyên public trong chain |
| `requestMatchers("/static/**")` cho file ở `classpath:/static/css` | URL thật là `/css/**`, không match | Phân biệt filesystem location với URL và test |
| Cho `/css/**` public trong khi chứa private export | Rò dữ liệu người dùng | Không đặt private files dưới public static handler |
| Cho `/actuator/**` public | Mở rộng bề mặt vận hành ngoài ý muốn | Health public, endpoints khác allowlist + OPS/network |
| Chỉ cấu hình `EndpointRequest` mà không expose metrics | Metrics trả 404 hoặc không có handler | Đặt exposure phù hợp, sau đó kiểm tra quyền |
| Expose metrics nhưng security matcher không khớp | Endpoint bị mở hoặc trả login sai | Dùng `EndpointRequest.toAnyEndpoint()`, test thực |
| Đặt `toAnyEndpoint()` trước `to("health")` | Health bị yêu cầu role OPS | Đặt rule cụ thể trước rule tổng quát |
| Đặt `anyRequest().authenticated()` trước các rule cụ thể | Rule sau không hiệu lực hoặc config lỗi | Thiết kế lại thứ tự matcher |
| Chỉ permit path `/error` nhưng bỏ qua error dispatch semantics | Status lỗi biến thành login redirect | Hiểu `DispatcherType.ERROR` và error handling |
| Mở mọi `FORWARD` không kiểm tra | Rủi ro bypass policy ở dispatch đích | Chỉ mở khi đã đánh giá trusted internal forward |
| Public error controller in stacktrace | Tiết lộ thông tin nội bộ | Sanitize error response/properties |
| Nghĩ `MockMvc ERROR` là container error E2E | Test xanh nhưng container xử lý khác | Bổ sung HTTP integration test thật |
| Đổi management port nhưng chỉ test app port | Port quản trị còn thiếu bảo vệ | Test cả context, network rule và auth |
| Tắt CSRF cho cả ứng dụng để gọi Actuator | Mở rủi ro CSRF cho browser endpoints | Scope exception chặt theo threat model |
| Kiểm tra `hasRole("OPS")` bằng user thiếu role nhưng mong 401 | Authenticated thiếu quyền thường 403 | Phân biệt authentication 401/redirect và authorization 403 |
| Lẫn `ROLE_ADMIN` với `ROLE_OPS` | Bảng quyền không đúng | Định nghĩa role hierarchy nếu thực sự cần |
| Chỉ nhìn URL/status không xem body hoặc logs | Có thể trả 200 với error page hoặc proxy cache | Test body, Content-Type, dispatch và security metadata |

## 17. Câu hỏi kiểm tra có đáp án

**Câu 1.** File `src/main/resources/static/css/site.css` được load ở URL `/static/css/site.css` hay `/css/site.css` trong Boot MVC mặc định?

**Đáp án:** Thông thường `/css/site.css`. `static` là thư mục resources location chứ không phải một path prefix tự động. Cấu hình custom static handler có thể thay đổi đường URL.

**Câu 2.** Vì sao `permitAll()` thường tốt hơn `web.ignoring()` cho tài nguyên công khai?

**Đáp án:** `permitAll` vẫn đi qua Spring Security chain và các filter/headers phù hợp; ignoring thường bỏ qua hoàn toàn chain. Với Spring Security 6, permit-all cũng có tối ưu authorization không cần lookup Authentication trong trường hợp được phép.

**Câu 3.** Anonymous yêu cầu `/css/missing.css` nhận 302 về login. Điều đó chứng minh file tồn tại không?

**Đáp án:** Không. Request có thể bị authorization chặn trước khi MVC xác định thiếu resource. Kiểm tra static matcher; với public path đúng, file thiếu thường trả 404.

**Câu 4.** `DispatcherType.ERROR` khác GET trực tiếp `/error` như thế nào?

**Đáp án:** ERROR là **loại dispatch nội bộ** do Servlet container thực hiện khi xử lý lỗi. `/error` là **path**; request bình thường cũng có thể trỏ tới nó. `dispatcherTypeMatchers(ERROR)` và `requestMatchers("/error")` có phạm vi khác nhau.

**Câu 5.** Một error page được `permitAll` có được phép hiển thị toàn bộ stack trace không?

**Đáp án:** Không. Authorization cho phép hiển thị trang lỗi không đồng nghĩa trả exception details nhạy cảm. Cần sanitize, giữ status đúng và giới hạn logs/response theo môi trường.

**Câu 6.** Vì sao `EndpointRequest.to("health")` phải đứng trước `EndpointRequest.toAnyEndpoint()`?

**Đáp án:** Quy tắc authorization được xét theo thứ tự. Nếu matcher bao quát Actuator bắt trước, health có thể bị yêu cầu quyền OPS dù mong muốn public.

**Câu 7.** Tại sao thêm `management.endpoints.web.exposure.include: metrics` không đồng nghĩa metrics trở thành public?

**Đáp án:** Exposure chỉ làm endpoint có thể truy cập qua HTTP; authorization vẫn quyết định quyền của principal. Cần kết hợp role/network controls.

**Câu 8.** Khi management port là 9090, test `/actuator/metrics` ở port 8080 có đủ chứng minh bảo mật không?

**Đáp án:** Không. Management server/context có thể khác; phải kiểm tra đúng port, security chain, authentication và network ACL trên 9090.

**Câu 9.** `@WithMockUser(roles="OPS")` chứng minh user thực có password hợp lệ không?

**Đáp án:** Không. Nó tạo mock authenticated principal để test authorization. Muốn test authentication phải thực hiện login/provider flow riêng.

**Câu 10.** Có nên mở `DispatcherType.FORWARD` toàn cục chỉ vì một view JSP không render được?

**Đáp án:** Chỉ khi phân tích trusted forward paths, chain và policy thấy phù hợp. Mở toàn bộ FORWARD có thể làm dispatch đích tránh authorization mà bạn dự kiến áp dụng.

**Câu 11.** Với endpoint Actuator chưa được expose, nên sửa bằng `permitAll("/actuator/**")` không?

**Đáp án:** Không. Authorization không làm endpoint chưa expose xuất hiện; phải xác định exposure cần thiết, rồi bảo vệ endpoint đó bằng least privilege.

**Câu 12.** Tại sao một 404/500 chuyển thành 302 login trong quá trình error handling đáng quan tâm?

**Đáp án:** Nó có thể che giấu lỗi thật và tạo redirect loop hoặc trải nghiệm khó debug. Cần xem dispatch type, error URL và security policy đúng từng giai đoạn xử lý.

## 18. Checklist nghiệm thu chính sách HTTP

- [ ] Lập danh mục URL public static, private downloads, nghiệp vụ, error endpoint và Actuator.
- [ ] Xác định `SecurityFilterChain` thực sự match từng URL; kiểm tra thứ tự nhiều chains.
- [ ] Static resources public được `permitAll`, không bỏ qua toàn bộ filter chain nếu không cần.
- [ ] `PathRequest` có bao phủ đúng resource handler locations của dự án; bổ sung custom matcher hẹp nếu cần.
- [ ] Không chứa secret, private export hoặc user uploads nhạy cảm trong public static directory.
- [ ] Test assets tồn tại trả 200; assets thiếu thường trả 404 thay vì redirect login.
- [ ] Kiểm tra `DispatcherType.ERROR` và URL `/error` theo luồng Servlet container.
- [ ] Error responses được sanitize, giữ status và không tiết lộ stacktrace/token/cookie.
- [ ] Không mở `DispatcherType.FORWARD` hoặc mọi dispatch vô điều kiện khi chưa phân tích.
- [ ] Actuator exposure chỉ gồm endpoint cần dùng; không expose wildcard không kiểm soát.
- [ ] Health public chỉ ở phạm vi cho phép, details tối thiểu; probes đúng port/path.
- [ ] Các endpoint metrics/info/management nhạy cảm cần `ROLE_OPS` hoặc authentication mạnh hơn.
- [ ] Kiểm tra `EndpointRequest.to("health")` trước `toAnyEndpoint()` cùng catch-all policy.
- [ ] Kiểm thử role OPS, ADMIN, USER riêng biệt; không giả định role hierarchy tự có.
- [ ] Nếu management server chạy cổng riêng, test riêng port/context/security/network.
- [ ] CSRF vẫn được cân nhắc cho unsafe management methods nếu dùng browser credentials.
- [ ] Security headers/cache/CORS của public assets và private endpoints được kiểm chứng.
- [ ] Test cả anonymous, authenticated thiếu quyền, authorized và URL không tồn tại.
- [ ] MockMvc chỉ dùng cho kiểm tra filter/rule; HTTP integration bổ sung cho error dispatch, proxy/CDN, network ACL.
- [ ] Logging/monitoring không lộ user token, session IDs hay exception secrets.
- [ ] Có regression test tự động khi đổi base path, deployment port, resource handler, chain order hoặc actuator exposure.

## Kết luận

**Tài nguyên tĩnh, endpoint lỗi và Actuator cần ba loại quy tắc khác nhau**, dù đều đi qua authorization trong Spring Security Servlet. Tài nguyên công khai nên được `permitAll` có chọn lọc; error dispatch cần được xét theo `DispatcherType.ERROR` và error body phải an toàn; Actuator cần phân biệt **exposure** với **authorization**, chỉ health (hoặc probe tối thiểu) public khi phù hợp và phần còn lại được bảo vệ bởi quyền vận hành cùng network controls.

Để kiểm tra đúng, hãy test **request URL, loại dispatch, thứ tự matcher/chain, role và body/status**, không chỉ nhìn thấy trang login hay 200. Một policy tốt phải cho phép đúng tài nguyên cần thiết mà không làm lộ private data hoặc endpoint quản trị, và vẫn hoạt động nhất quán khi thêm custom static handlers, thay base path, chia nhiều security chains hoặc chuyển Actuator sang management port riêng.
