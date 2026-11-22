# authorizeHttpRequests và RequestMatcherDelegatingAuthorizationManager trong Spring Security Servlet

## 1. Bức tranh tổng quan: xác thực xong chưa có nghĩa là được truy cập

Một ứng dụng **Spring Boot 3 / Spring Security 6 trên Servlet stack** thường cần trả lời hai câu hỏi độc lập:

1. **Authentication:** “Ai đang gửi request?” — chưa đăng nhập, đã đăng nhập bằng username/password, Bearer token, session hoặc cơ chế khác?
2. **Authorization:** “Danh tính đó có quyền thực hiện request này không?” — URL, phương thức HTTP, role, authority, ownership và quy định nghiệp vụ có cho phép?

`authorizeHttpRequests` là DSL dùng để định nghĩa **chính sách phân quyền cho HTTP request** trong `HttpSecurity`. Trong luồng Servlet hiện đại, Spring Security thường thực thi chính sách đó qua **`AuthorizationFilter`** và một `AuthorizationManager<HttpServletRequest>` được xây từ các quy tắc.

Ví dụ:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Ý nghĩa: URL public có thể truy cập không cần authentication; URL admin cần role ADMIN; các API khác cần có authentication; các URL còn lại bị từ chối. **Thứ tự ở đây quan trọng**: rule đầu tiên khớp request được chọn. DSL có một cơ chế nội bộ đóng vai trò quyết định: **`RequestMatcherDelegatingAuthorizationManager`**.

Bài học giải thích hai API này ở mức ứng dụng lẫn hoạt động bên trong, cách sắp xếp matcher tránh lộ endpoint, mối quan hệ giữa `SecurityFilterChain` và `AuthorizationFilter`, và một project Java 17+ chạy được với MockMvc để kiểm tra kết quả thực tế.

## 2. Từng thành phần trong luồng Servlet Security

Một request vào ứng dụng thường đi qua:

~~~text
Client
  |
  v
Servlet container
  |
  v
DelegatingFilterProxy
  |
  v
FilterChainProxy (springSecurityFilterChain)
  |
  | tìm SecurityFilterChain ĐẦU TIÊN có securityMatcher khớp
  v
Các Security filters thuộc chain đã chọn
  |
  +--> SecurityContextHolderFilter / authentication filters
  |       tìm hoặc thiết lập Authentication cho request
  |
  +--> ExceptionTranslationFilter
  |       diễn dịch AuthenticationException/AccessDeniedException
  |
  +--> AuthorizationFilter
          |
          v
      AuthorizationManager<HttpServletRequest>
          |
          v
      RequestMatcherDelegatingAuthorizationManager
          |
          +--> matcher #1 ? -> manager #1 quyết định
          +--> matcher #2 ? -> manager #2 quyết định
          +--> ... (chỉ xét đến rule đầu tiên khớp)
          |
          +--> không khớp? quy tắc fallback rất quan trọng
          |
          v
       ALLOW / DENY
          |
          +--> ALLOW -> Servlet/MVC controller
          |
          +--> DENY  -> exception handling -> HTTP 401/403 thường gặp
~~~

Thứ tự một số filter có thể thay đổi theo phiên bản/cấu hình; sơ đồ tập trung vào đường đi có liên quan tới HTTP authorization. Trong thực tế, **authentication đã được thực hiện hoặc được khôi phục** trước khi quyết định phân quyền; riêng rule `permitAll()` có thể được quyết định mà không cần đọc authentication/session.

Các khái niệm:

| Thành phần | Vai trò |
| --- | --- |
| `HttpSecurity` | Builder tạo một `SecurityFilterChain` |
| `securityMatcher(...)` | Matcher xác định request có được đưa vào **filter chain đó** hay không |
| `authorizeHttpRequests(...)` | Khai báo những rule phân quyền **bên trong chain đã được chọn** |
| `requestMatchers(...)` | Matcher chọn rule cho một hoặc nhiều URL/method/điều kiện request |
| `AuthorizationManager` | Giao diện quyết định cho phép/từ chối dựa vào Authentication và ngữ cảnh |
| `RequestMatcherDelegatingAuthorizationManager` | Ghép danh sách `RequestMatcher -> AuthorizationManager`, chọn rule đầu tiên khớp |
| `AuthorizationFilter` | Dùng manager để kiểm tra request trước khi đi tới tài nguyên |
| `ExceptionTranslationFilter` | Chuyển một số ngoại lệ security thành challenge/redirect hoặc 403 |
| `AuthenticationEntryPoint` | Thường xử lý khi request chưa được xác thực và cần đăng nhập |
| `AccessDeniedHandler` | Thường xử lý người đã xác thực nhưng bị từ chối quyền |

**Lưu ý phân biệt:** `RequestMatcherDelegatingAuthorizationManager` không phải “một filter mới” và không phải nơi xử lý đăng nhập. Nó là **bộ điều phối các quyết định authorization** được `AuthorizationFilter` gọi khi một request đi qua chain liên quan.

## 3. authorizeHttpRequests khai báo những gì?

DSL thường có dạng:

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/assets/**", "/health").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .requestMatchers("/reports/**").hasAuthority("report:read")
            .requestMatchers("/account/**").authenticated()
            .anyRequest().denyAll()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đoạn trên là một **snippet của lớp `@Configuration`**, cần import và bean phù hợp. Một project Maven đủ file được trình bày trong phần 9.

Các lựa chọn thường dùng:

- `permitAll()`: cho mọi người truy cập, kể cả anonymous.
- `denyAll()`: không chấp nhận truy cập theo rule này.
- `authenticated()`: yêu cầu principal đã được xác thực theo quy tắc của framework.
- `fullyAuthenticated()`: yêu cầu authentication đầy đủ; loại trừ một số trạng thái như remember-me.
- `anonymous()`: chỉ cho phép anonymous theo cách Spring Security nhận diện.
- `hasRole("ADMIN")`: mặc định đòi authority `ROLE_ADMIN`, không truyền chuỗi `ROLE_ADMIN` vào `hasRole`.
- `hasAuthority("report:read")`: khớp **đúng authority string**, không tự thêm prefix.
- `hasAnyRole("USER", "ADMIN")` / `hasAnyAuthority(...)`: chấp nhận một trong các quyền tương ứng.
- `access(customAuthorizationManager)`: dùng `AuthorizationManager<RequestAuthorizationContext>` tự xây khi DSL có sẵn chưa đủ.

Các rule này áp dụng cho **HTTP request authorization**, không thay `@PreAuthorize` trên method, không thay chính sách truy cập dữ liệu theo owner/tenant và không bỏ qua authentication provider. Chỉ vì URL `/api/orders/**` authenticated không có nghĩa user A được xem order của user B.

### 3.1. hasRole khác hasAuthority

Giả sử `Authentication` có authorities:

~~~text
ROLE_USER
report:read
~~~

Thì:

| Kiểm tra | Kết quả đối với authorities trên |
| --- | --- |
| `hasRole("USER")` | Cho phép (mặc định kiểm tra `ROLE_USER`) |
| `hasRole("ADMIN")` | Từ chối |
| `hasAuthority("ROLE_USER")` | Cho phép |
| `hasAuthority("USER")` | Từ chối |
| `hasAuthority("report:read")` | Cho phép |
| `authenticated()` | Cho phép nếu Authentication thực sự được xem là authenticated |

Prefix role mặc định có thể được tùy chỉnh trong hệ thống; giải thích ở đây theo chính sách thông dụng. Đừng suy rằng mọi authority đều là role; scopes/permissions nghiệp vụ có thể dùng chuỗi như `report:read`, `order:write` hoặc `SCOPE_read`.

### 3.2. HTTP method cũng nằm trong matcher

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/articles/**").permitAll()
    .requestMatchers(HttpMethod.POST, "/api/articles").hasAuthority("article:create")
    .requestMatchers(HttpMethod.DELETE, "/api/articles/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
~~~

Đây là đoạn cấu hình minh họa, cần import `org.springframework.http.HttpMethod`. GET, POST và DELETE có chính sách khác nhau; request không khớp các rule riêng đi vào fallback `anyRequest().authenticated()`.

**Quan trọng:** authorization rule không thay CSRF protection. Nếu POST yêu cầu CSRF token và token không hợp lệ, request có thể bị chặn **trước khi** AuthorizationFilter kiểm tra rule, dù URL được `permitAll()`. Việc công khai URL qua authorizeHttpRequests không tự biến endpoint thành ngoại lệ CSRF.

## 4. RequestMatcherDelegatingAuthorizationManager hoạt động như thế nào?

Tên class dài nhưng cấu trúc rất trực quan: “Bộ quản lý ủy quyền dựa trên việc request khớp matcher nào”.

Về mặt khái niệm, nó giữ một danh sách có thứ tự:

~~~text
Rule 1: [GET /public/**]          -> permitAll
Rule 2: [/admin/**]               -> hasRole("ADMIN")
Rule 3: [GET /api/reports/**]     -> hasAuthority("report:read")
Rule 4: [/api/**]                 -> authenticated
Rule 5: [any request]             -> denyAll
~~~

Khi một request tới:

~~~http
GET /api/reports/weekly HTTP/1.1
Host: localhost:8080
~~~

Bộ điều phối lần lượt hỏi matcher #1, #2, #3. Matcher #3 khớp, nên **chỉ manager #3** được dùng để quyết định. Nó không tiếp tục tới matcher #4 dù `/api/**` cũng có thể khớp.

Pseudo-code diễn giải **không phải nguồn code framework**:

~~~java
for (Rule rule : orderedRules) {
    if (rule.requestMatcher().matches(request)) {
        return rule.authorizationManager()
            .authorize(authenticationSupplier, requestContext);
    }
}
// Không có rule khớp: không nên dựa vào behavior ngầm.
// Khai báo anyRequest().denyAll() hoặc fallback rõ ràng.
~~~

Trong triển khai thật, manager có thể cung cấp kết quả authorization/abstain theo contract và phiên bản của interface. Đừng dùng pseudo-code trên để suy rằng luôn trả boolean; cấu trúc `AuthorizationDecision`/`AuthorizationResult` và API có thể thay đổi giữa phiên bản. Điều **cần nhớ** là **thứ tự matcher và ủy quyền cho rule đầu tiên phù hợp**.

### 4.1. Matcher và manager là hai nửa khác nhau

- `RequestMatcher` quyết định **request có thuộc một phạm vi URL/method/dispatcher nào không**.
- `AuthorizationManager` quyết định **Authentication hiện có có đáp ứng chính sách cho request thuộc phạm vi ấy hay không**.

Ví dụ: rule `requestMatchers("/admin/**").hasRole("ADMIN")` có matcher `/admin/**`; manager kiểm tra role ADMIN. Nếu URL đúng mà user không đủ quyền, request bị từ chối **ngay trong rule đó**. Nó **không** chuyển xuống `.anyRequest().authenticated()` để cho phép vì đã đăng nhập.

Đây là khác biệt lớn với một suy nghĩ sai: “Rule admin không đạt thì thử rule API hoặc authenticated tiếp theo”. **Không** — “khớp matcher” và “được phép truy cập” là hai giai đoạn của **cùng một rule đã chọn**.

### 4.2. Cấu trúc manager bên dưới DSL

Khi khai báo `authorizeHttpRequests`, Spring Security có thể xây `RequestMatcherDelegatingAuthorizationManager` với các cặp matcher/authorization-manager. Lúc chạy, `AuthorizationFilter` nhận manager này và đưa request vào kiểm tra.

Do đó `authorizeHttpRequests` là **API tiện lợi dành cho người viết cấu hình**, còn `RequestMatcherDelegatingAuthorizationManager` là **một thành phần triển khai cụ thể của chiến lược đánh giá rule**.

Trong phần lớn ứng dụng, bạn **không cần tự tạo** class này. Dùng DSL làm cấu hình dễ đọc và an toàn hơn, nhất là khi bạn đang triển khai phân quyền theo URL.

### 4.3. Có thể xây manager thủ công không?

Có. Trong những tình huống đặc biệt, API builder của `RequestMatcherDelegatingAuthorizationManager` cho phép đăng ký matcher và AuthorizationManager. Một phác thảo khái niệm:

~~~text
RequestMatcherDelegatingAuthorizationManager.builder()
    .add(matcherChoAdmin, managerYeuCauAdmin)
    .add(matcherChoApi, managerYeuCauDangNhap)
    .anyRequest().denyAll()
    .build()
~~~

Đoạn trên **là mã giả**, không phải Java độc lập biên dịch: tên matcher/manager là placeholder mô tả ý tưởng. Không copy nó như source production. Mục đích là làm rõ cấu trúc **danh sách rule có thứ tự**. Nếu cần manager tùy chỉnh thật, có thể dùng `.access(customAuthorizationManager)` trong DSL và tích hợp với policy service đã được kiểm thử.

## 5. Thứ tự rule: nguyên tắc quan trọng nhất

### 5.1. Từ cụ thể đến tổng quát

Cấu hình phù hợp:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

`/admin/reports` được rule đầu tiên yêu cầu ADMIN; `/api/profile` yêu cầu authenticated; URL khác bị deny.

**Cấu hình có nguy cơ lộ quyền:**

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

Với `GET /api/admin/users`, rule `/api/**` khớp **trước** nên được permitAll. Rule admin phía sau không được xét. Không có cơ chế “rule nghiêm hơn sẽ tự thắng” trong danh sách first match.

Sửa:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Matcher cụ thể hơn nên đứng trước matcher rộng hơn **khi các pattern có thể chồng lấp**. Bạn cũng nên thiết kế các URL để bớt chồng lấp, giảm nguy cơ vô tình thay đổi quyền khi sửa cấu hình.

### 5.2. Các rule overlap về phương thức

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**").hasAuthority("order:read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**").hasAuthority("order:write")
    .requestMatchers("/api/orders/**").denyAll()
    .anyRequest().denyAll()
);
~~~

Hệ quả: GET đòi quyền đọc, POST đòi quyền ghi, còn các method khác trong phạm vi orders bị từ chối. Nếu bạn đặt `/api/orders/**.denyAll()` lên trước, cả GET lẫn POST đều bị deny trước khi tới rule đặc thù.

**Không tự động có quy tắc “GET bao trùm HEAD” trong mọi matcher/cấu hình**; hãy test các HTTP method thực tế mà ứng dụng chấp nhận, bao gồm HEAD/OPTIONS khi có liên quan. Preflight/CORS có thể được xử lý ở filter trước authorization nếu được cấu hình.

### 5.3. Đừng bỏ fallback rõ ràng

Một rule cuối như `anyRequest().denyAll()` tạo policy “không có rule nào cho phép thì từ chối” (**deny by default**). Với ứng dụng API nội bộ quan trọng, đây thường là tư thế an toàn.

Trong ứng dụng có nhiều trang tĩnh/actuator/error, deny all có thể gây lỗi chức năng nếu thiếu rule cho tài nguyên hợp lệ. Cách sửa không phải thêm `anyRequest().permitAll()` vô điều kiện, mà là **liệt kê những endpoint cần công khai** và test kỹ.

Nếu chỉ muốn mọi URL còn lại cần login, dùng `anyRequest().authenticated()`. Đó là chính sách khác với denyAll; chọn dựa vào yêu cầu, không thay thế tùy tiện.

### 5.4. Thứ tự không phải “cộng dồn quyền”

Giả sử:

~~~java
.requestMatchers("/finance/**").hasRole("FINANCE")
.requestMatchers("/finance/report/**").hasAuthority("report:read")
~~~

Một request `/finance/report/monthly` bị rule `/finance/**` chọn trước. Không yêu cầu đồng thời role FINANCE và permission report:read; cũng không có chuyện fail FINANCE rồi chạy rule thứ hai. Nếu cần **AND**, hãy thiết kế manager/policy kiểm tra cả hai điều kiện ở **một rule** hoặc phân quyền method/service.

## 6. securityMatcher, requestMatchers và nhiều SecurityFilterChain

Hai API giống tên nhưng khác phạm vi.

### 6.1. securityMatcher: chọn filter chain

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đây là **snippet trong một lớp @Configuration**, cần import `@Bean`/`@Order` và các kiểu liên quan; để chạy phải có ứng dụng và các beans thích hợp. `securityMatcher("/api/**")` chỉ cho **chain này** xử lý các URL API tương ứng. Nếu một URL không khớp chain thì **không có rule nội bộ nào trong chain đó được kiểm tra**.

Nếu có nhiều chain, `FilterChainProxy` chọn **chain đầu tiên khớp** theo thứ tự chain (ví dụ qua `@Order`). Chain được chọn rồi mới chạy authorization rule của chain đó. **@Order của chain** khác hoàn toàn với **thứ tự .requestMatchers(...) bên trong một chain**.

### 6.2. requestMatchers: chọn quy tắc authorization trong chain

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().authenticated()
)
~~~

Các matcher này không quyết định chain có chạy hay không. Chúng chỉ áp dụng sau khi request đã đi vào chain.

So sánh:

| Khái niệm | Câu hỏi | Cơ chế chọn |
| --- | --- | --- |
| `SecurityFilterChain.securityMatcher` | Chain nào quản lý request? | `FilterChainProxy` chọn chain đầu tiên khớp |
| `@Order` trên bean chain | Chain nào được ưu tiên? | Giá trị nhỏ thường được xem trước |
| `authorizeHttpRequests().requestMatchers` | Trong chain, rule nào được dùng? | `RequestMatcherDelegatingAuthorizationManager` chọn matcher đầu tiên khớp |
| `AuthorizationManager` | User/request có được phép theo rule đã chọn? | Trả quyết định cho phép/từ chối/abstain theo contract |
| `@PreAuthorize` hoặc policy service | Có quyền thực hiện hành động/đụng dữ liệu cụ thể? | Kiểm tra ở tầng method/nghiệp vụ nếu được bật |

### 6.3. Bẫy chain không có fallback

Nếu toàn bộ filter chains đều có `securityMatcher` hẹp và một request **không khớp bất kỳ chain nào**, request có thể **không đi qua bộ lọc Spring Security**, đồng nghĩa không có HTTP authorization của các chain đó. Đừng nghĩ `anyRequest().denyAll()` bên trong API chain sẽ bảo vệ URL ngoài `/api/**`.

Khi cần bảo vệ toàn ứng dụng, thường dùng một **catch-all chain** được ưu tiên cuối hoặc đảm bảo các matcher bao phủ đầy đủ những request mong muốn. Thêm chain fallback phải cân nhắc asset, actuator, error dispatcher và cơ chế đăng nhập cụ thể.

### 6.4. web.ignoring khác permitAll

`permitAll()` cho phép request nhưng vẫn qua Spring Security filter chain và hưởng các cơ chế phù hợp như security headers, CSRF handling và security context management.

`web.ignoring()` (qua `WebSecurityCustomizer`) bỏ qua filter chain Spring Security cho request khớp. Điều này có thể làm mất các lớp bảo vệ mà bạn tưởng vẫn tồn tại. Với tài nguyên static, Spring Security thường khuyến nghị **ưu tiên permitAll** nếu muốn giữ hành vi security headers và tránh vô ý bypass quá rộng.

## 7. AuthorizationFilter và đặc điểm quyết định

### 7.1. Authentication supplier và đánh giá lười

Trong mô hình `AuthorizationManager`, authentication có thể được cung cấp qua một `Supplier<Authentication>`. Ý tưởng là chỉ lấy thông tin authentication khi policy thật sự cần; ví dụ rule `permitAll()` không cần xem roles của user.

Điều này có thể tránh session lookup không cần thiết cho một số request công khai. Nhưng đừng nhầm “permitAll” với “bỏ toàn bộ filter” hoặc “bỏ CSRF”. Request vẫn qua chain, và các filter khác có thể làm việc tùy cấu hình.

### 7.2. Kết quả allow, deny và exception

Khi `AuthorizationFilter` đánh giá manager cho một request, quyết định không cho phép có thể tạo `AccessDeniedException` hoặc tương đương theo API/version. `ExceptionTranslationFilter` tiếp nhận các ngoại lệ phù hợp và quyết định cách phản hồi:

- Nếu request chưa có authentication hợp lệ, `AuthenticationEntryPoint` thường tạo **401** với HTTP Basic hoặc redirect tới login page với form login.
- Nếu user đã authenticated nhưng không đủ quyền, `AccessDeniedHandler` thường tạo **403 Forbidden**.
- Nếu CSRF token sai, request có thể bị chặn ở **CSRF filter trước authorization**; không kết luận từ 403 rằng `RequestMatcherDelegatingAuthorizationManager` đã từ chối role.
- Kết quả HTTP phụ thuộc authentication mechanism, entry point, handler và application policy. **Không suy ra mọi denial đều bắt buộc có 403**.

Ví dụ `GET /admin/dashboard` bằng user thường với HTTP Basic đúng mật khẩu: authentication thành công, authorization từ chối, thường trả 403. Nếu không gửi credentials, cùng URL thường dẫn tới 401 và challenge `WWW-Authenticate: Basic`.

### 7.3. Request dispatch và error handling

Servlet có các dispatcher types như `REQUEST`, `FORWARD`, `ERROR` và `ASYNC`. Trong một số cấu hình, `AuthorizationFilter` có thể chạy trên nhiều dispatch và yêu cầu authorization cả với đường forward/error. Điều này khiến trang lỗi `/error` hoặc forward view bị chặn nếu fallback quá nghiêm.

Khi thật sự cần, có thể khai báo rule cụ thể:

~~~java
.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR, DispatcherType.FORWARD)
        .permitAll()
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
)
~~~

Snippet này cần `jakarta.servlet.DispatcherType`. **Chỉ cho phép các dispatcher type sau khi đánh giá luồng thực tế**; không dùng permitAll cho các dispatcher types một cách máy móc nếu ứng dụng có rủi ro bypass. Các rule theo dispatcher cũng cần đặt đúng thứ tự.

### 7.4. Dispatcher và context path

Khi dùng Spring MVC, `requestMatchers(String...)` có thể tận dụng matcher phù hợp với MVC tùy cấu hình/classpath. Các matcher theo đường dẫn không nên được coi là chuỗi URL tuyệt đối bao gồm mọi context path/servlet path; cấu hình app có `server.servlet.context-path` hoặc nhiều servlet có thể cần matcher thích hợp và test thực tế.

Nếu nhiều servlet cùng nằm trong một application context, Spring Security có thể không biết pattern thuộc servlet nào. Hãy chỉ rõ matcher/servletPath khi cần, không sử dụng một path pattern quá rộng rồi kỳ vọng luôn khớp như trên MVC root servlet.

## 8. Thiết kế rule HTTP an toàn

### 8.1. Phân lớp theo độ nhạy

Một thứ tự có thể dùng làm điểm khởi đầu:

~~~text
1. Dispatcher cần phục vụ error/forward (chỉ nếu phù hợp)
2. Public endpoints và assets được quyết định rõ
3. Sensitive/admin endpoints yêu cầu role/authority cao
4. API chức năng đặc thù yêu cầu permission
5. API còn lại yêu cầu authenticated
6. Fallback denyAll
~~~

Thứ tự trên **không phải một công thức phải sao chép cho mọi dự án**. Nếu assets ở `/admin/assets/**` và public rule `/**` quá rộng thì vẫn có thể làm lộ route. Rule đầu tiên khớp là điều thực sự quyết định.

### 8.2. Phân biệt authentication với ownership

Giả sử:

~~~java
.requestMatchers("/api/orders/**").authenticated()
~~~

Rule này chỉ chứng minh user có authentication, **không chứng minh** user là chủ của order ID trong URL. Nếu user A gọi `GET /api/orders/123` mà order 123 thuộc user B, cần có service authorization hoặc method security kiểm tra owner/tenant. Đừng cố giải quyết toàn bộ bài toán dữ liệu theo ID bằng URL matcher chung.

Có thể sử dụng `@PreAuthorize` với policy service khi ứng dụng đã bật method security, hoặc kiểm tra trong service với dữ liệu đã được load/authorized. Mục tiêu là phân quyền gần tài nguyên và không tin userId/tenantId do client tự khai báo.

### 8.3. HTTP status có thể thay đổi theo authentication type

- HTTP Basic chưa cung cấp credentials → 401 với challenge.
- Form login chưa authentication → redirect 302 tới login page.
- API Bearer thiếu token → 401 JSON/challenge tùy cấu hình.
- User authenticated nhưng thiếu authority → thường 403.
- Endpoint public `permitAll` → có thể truy cập không cần authentication.
- `denyAll` → từ chối theo policy, nhưng status công khai còn phụ thuộc exception translation/authentication state.

Do vậy hãy viết integration tests với **đúng authentication mechanism**. Không test form login và giả định status 401 giống Basic.

## 9. Project chạy được: Spring Boot 3.3.13 / Java 17 / Spring Security 6

Ví dụ này triển khai một `SecurityFilterChain` duy nhất. Một `authorizeHttpRequests` định nghĩa năm rule theo thứ tự:

1. `GET /public/**` không cần login.
2. `GET /api/reports/**` yêu cầu authority `report:read`.
3. `/admin/**` yêu cầu `ROLE_ADMIN`.
4. `/api/**` còn lại yêu cầu authenticated.
5. `anyRequest().denyAll()` từ chối URL không được đặc tả.

Dùng **HTTP Basic** để các request test dễ tái hiện, không cần trang HTML login. Đây là demo phát triển cục bộ; nếu dùng HTTP Basic trên hệ thống thật, phải có HTTPS và chính sách quản lý password. Không dùng mật khẩu demo trong production.

### 9.1. Cây thư mục

~~~text
http-authorization-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/authorization/
    │   ├── HttpAuthorizationApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/authorization/
        └── AuthorizationRulesTests.java
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
    <artifactId>http-authorization-demo</artifactId>
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

**`src/main/java/com/example/authorization/HttpAuthorizationApplication.java`**

~~~java
package com.example.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpAuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpAuthorizationApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/authorization/SecurityConfig.java`**

~~~java
package com.example.authorization;

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

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // Matcher 1: public GET
                .requestMatchers(HttpMethod.GET, "/public/**").permitAll()

                // Matcher 2: phạm vi hẹp, cần authority cụ thể
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("report:read")

                // Matcher 3: trang admin chỉ dành cho admin
                .requestMatchers("/admin/**").hasRole("ADMIN")

                // Matcher 4: API còn lại yêu cầu login
                .requestMatchers("/api/**").authenticated()

                // Matcher 5: mặc định không cho phép
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String encoded = encoder.encode("demo-pass");

        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoded)
                .authorities("ROLE_USER", "report:read")
                .build(),

            User.withUsername("bob")
                .password(encoded)
                .roles("USER")
                .build(),

            User.withUsername("admin")
                .password(encoded)
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

**Mô tả quyền của ba user:**

| User | Authorities | Có thể làm gì trong demo |
| --- | --- | --- |
| `alice` | `ROLE_USER`, `report:read` | GET API thông thường và đọc report; không vào admin |
| `bob` | `ROLE_USER` | GET API thông thường, không đọc report, không vào admin |
| `admin` | `ROLE_ADMIN` | Vào admin và API thông thường; **không tự có `report:read`** |

Điểm cố ý: **role ADMIN không tự bao gồm mọi authority khác**. Nếu business yêu cầu admin cũng đọc report, phải gắn thêm `report:read` hoặc viết policy riêng. Đừng ngầm tin “ADMIN luôn có mọi quyền” trừ khi bạn đã định nghĩa như vậy.

**`src/main/java/com/example/authorization/DemoController.java`**

~~~java
package com.example.authorization;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/status")
    public Map<String, String> publicStatus() {
        return Map.of("status", "public-ok");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile(Authentication auth) {
        return Map.of("username", auth.getName());
    }

    @GetMapping("/api/reports/weekly")
    public Map<String, String> weeklyReport() {
        return Map.of("report", "weekly-ok");
    }

    @GetMapping("/admin/dashboard")
    public Map<String, String> adminDashboard() {
        return Map.of("status", "admin-ok");
    }

    // Controller có tồn tại, nhưng HTTP authorization denyAll từ chối.
    @GetMapping("/orphaned")
    public Map<String, String> orphaned() {
        return Map.of("status", "should-not-be-seen");
    }
}
~~~

Endpoint `/orphaned` được tạo có chủ đích để chứng minh controller tồn tại **không đồng nghĩa đường dẫn được phép**. Rule cuối `denyAll` vẫn chặn request trước khi đến controller.

### 9.2. Kiểm thử với Spring Security MockMvc

**`src/test/java/com/example/authorization/AuthorizationRulesTests.java`**

~~~java
package com.example.authorization;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationRulesTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicGetRequiresNoCredentials() throws Exception {
        mvc.perform(get("/public/status"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("public-ok"));
    }

    @Test
    void protectedApiNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void normalUserCanAccessAuthenticatedApi() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("bob"));
    }

    @Test
    void reportingPermissionIsDistinctFromRole() throws Exception {
        mvc.perform(get("/api/reports/weekly")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.report").value("weekly-ok"));

        mvc.perform(get("/api/reports/weekly")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isForbidden());

        // admin có ROLE_ADMIN nhưng không có report:read.
        mvc.perform(get("/api/reports/weekly")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminPathRequiresAdminRole() throws Exception {
        mvc.perform(get("/admin/dashboard")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin/dashboard")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("admin-ok"));
    }

    @Test
    void wrongPasswordIsNotAuthenticated() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void fallbackDeniesEvenAuthenticatedUser() throws Exception {
        mvc.perform(get("/orphaned")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

**Giải thích test:**

- `httpBasic("user", "password")` tạo HTTP Basic credentials cho MockMvc; test đi qua Spring Security filters khi dùng `@AutoConfigureMockMvc` và security test dependency.
- Public GET không cần user → 200.
- API thiếu authentication → thường 401 với HTTP Basic.
- User đã đăng nhập nhưng thiếu authority → 403.
- `alice` với `report:read` đọc report → 200, trong khi `admin` không được tự miễn kiểm tra authority.
- `/orphaned` bị chặn bởi `anyRequest().denyAll()` dù MVC controller được khai báo.
- Không dùng `@WithMockUser` để chứng minh password BCrypt thật được xác minh; ở đây chủ động gửi HTTP Basic để test cả authentication và authorization.

**Chú ý về assertion**: Đối với `MockMvc`, việc chuyển đổi Spring Security exceptions sang status phụ thuộc `ExceptionTranslationFilter`/`AuthenticationEntryPoint`. Với cấu hình **HTTP Basic** ở project này, các kỳ vọng 401/403 trên là hành vi cần kiểm tra. Nếu đổi sang form login, đường đi chưa login thường redirect, nên phải cập nhật test.

### 9.3. Chạy thử

Tạo file theo đúng đường dẫn rồi chạy tại thư mục chứa `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

Cần **JDK 17+**, Maven và khả năng tải dependency lần đầu. Các dòng dưới đây là **kết quả dự kiến từ cấu hình**, không phải kết quả Maven/curl đã đo trong tài liệu.

~~~bash
curl -i http://localhost:8080/public/status
# Dự kiến 200, JSON {"status":"public-ok"}

curl -i http://localhost:8080/api/profile
# Dự kiến 401 với HTTP Basic challenge

curl -i -u bob:demo-pass http://localhost:8080/api/profile
# Dự kiến 200, JSON {"username":"bob"}

curl -i -u bob:demo-pass http://localhost:8080/api/reports/weekly
# Dự kiến 403

curl -i -u alice:demo-pass http://localhost:8080/api/reports/weekly
# Dự kiến 200, JSON {"report":"weekly-ok"}

curl -i -u admin:demo-pass http://localhost:8080/admin/dashboard
# Dự kiến 200, JSON {"status":"admin-ok"}

curl -i -u admin:demo-pass http://localhost:8080/orphaned
# Dự kiến 403 do anyRequest().denyAll()
~~~

Trên Windows PowerShell, có thể dùng `curl.exe` nếu alias `curl` của PowerShell không hoạt động như curl CLI truyền thống.

**Demo không được triển khai nguyên trạng lên Internet:** mật khẩu mẫu hiển thị trong tài liệu và HTTP Basic chỉ thích hợp khi chạy qua HTTPS trong hệ thống thật. Nếu có yêu cầu API stateless Bearer/JWT, hãy chọn resource server/token infrastructure phù hợp; các HTTP authorization rules vẫn có cùng ý tưởng matcher→manager nhưng authentication khác.

## 10. Nếu cần AuthorizationManager tùy chỉnh

Không phải mọi chính sách đều biểu diễn đẹp bằng `hasRole` hoặc `hasAuthority`. Một yêu cầu có thể là:

> Chỉ nhân viên thuộc một phòng ban đã được xác nhận mới xem dashboard nội bộ, đồng thời phải có authority report:read.

Một cách là xây một `AuthorizationManager<RequestAuthorizationContext>` được dùng tại `.access(...)`. Ví dụ **snippet riêng để hiểu API**, không phải class hoàn chỉnh khi chưa khai báo bean/service:

~~~java
AuthorizationManager<RequestAuthorizationContext> policy =
    (authenticationSupplier, context) -> {
        Authentication authentication = authenticationSupplier.get();

        boolean authenticated =
            authentication != null && authentication.isAuthenticated();

        boolean canRead = authentication != null &&
            authentication.getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("report:read"));

        return new AuthorizationDecision(authenticated && canRead);
    };
~~~

Snippet này cần import `Authentication`, `AuthorizationManager`, `AuthorizationDecision`, `RequestAuthorizationContext` và biến `policy` trong phạm vi Java phù hợp. Nó chỉ minh họa giao diện; production phải phân biệt anonymous/remember-me theo policy, không chỉ tin `isAuthenticated()` trên mọi loại token. Đặc biệt user do service ngoài cung cấp cần được kiểm chứng quyền đáng tin cậy.

Áp dụng trong HTTP DSL:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/internal/reports/**").access(policy)
    .anyRequest().denyAll()
)
~~~

Đây cũng là snippet nối vào `HttpSecurity` có `policy` đã được định nghĩa. **Không dùng một custom manager chỉ để viết lại `hasAuthority("report:read")`**; API có sẵn thường đơn giản và ít sai hơn. Dùng manager tùy chỉnh khi có thêm quy tắc nghiệp vụ cần dữ liệu/cấu trúc bổ sung.

### 10.1. Ownership hoặc tenant nên đặt ở đâu?

Nếu policy là “user chỉ xem được báo cáo của tenant chính mình”, bạn có thể:

- Kiểm tra ở service khi đã load dữ liệu, bảo đảm owner/tenant ID lấy từ nguồn tin cậy; hoặc
- Dùng method security với `@EnableMethodSecurity` và `@PreAuthorize` gọi policy service; hoặc
- Dùng request-aware authorization manager nếu thực sự có đủ ngữ cảnh tin cậy ở tầng HTTP.

**Không tin tenantId/userId từ query string như bằng chứng quyền**, và không cho rằng `authenticated()` đã đáp ứng row-level security.

### 10.2. AuthorizationDecision không phải Authenticated token

Manager **đưa ra quyết định** cho phép/từ chối. Nó không thực hiện password verification, không tự tạo `Authentication` đáng tin cậy từ username do client gửi và không ghi session. Authentication phải đi qua provider/token verifier được thiết kế hợp lệ; manager sử dụng danh tính và authorities đã được xác nhận.

## 11. Những lỗi thường gặp và cách sửa

| Lỗi | Tác hại | Cách sửa |
| --- | --- | --- |
| Đặt matcher rộng `/api/**.permitAll()` trước `/api/admin/**.hasRole(...)` | Làm lộ API admin | Đặt rule cụ thể trước rộng; thêm test endpoint |
| Nghĩ fail manager đầu sẽ thử rule tiếp theo | Bỏ qua first-match semantics | Hiểu matcher đầu khớp chọn manager và kết thúc |
| Dùng `hasRole("ROLE_ADMIN")` thay `hasRole("ADMIN")` | Sai prefix mặc định | Dùng `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` |
| Dùng `authenticated()` làm kiểm tra owner | User A có thể truy cập dữ liệu user B | Kiểm tra ownership/tenant trong service/method |
| Bỏ `anyRequest` và dựa vào default ngầm | Policy khó đọc, thay đổi khó kiểm soát | Định nghĩa fallback rõ ràng |
| Đặt `anyRequest().permitAll()` để chữa 404/403 | Có thể mở endpoint không mong muốn | Permit những URL hợp lệ cụ thể |
| Nhầm `securityMatcher` với `requestMatchers` | Cấu hình không bảo vệ toàn app | Kiểm tra chain selection và rule selection riêng |
| Chỉ có API chain `securityMatcher("/api/**")`, quên catch-all | Request ngoài API có thể không qua Spring Security | Thêm fallback chain hoặc bao phủ đầy đủ |
| Dùng `web.ignoring()` cho tài nguyên nhạy cảm | Bỏ các security filters | Ưu tiên permitAll cho public resources |
| Nghĩ `permitAll()` tự bỏ CSRF | Form POST vẫn có thể 403 do CSRF | Thiết kế CSRF riêng cho loại credentials |
| Nghĩ hasAuthority("ADMIN") tương đương hasRole("ADMIN") | Sai khi authority thực tế là ROLE_ADMIN | Kiểm tra exact GrantedAuthority |
| Test chỉ 200 mà không test 401/403 | Bỏ lọt endpoint bị mở hoặc bảo vệ quá chặt | Viết negative tests và test thứ tự rule |
| Dùng controller mapping làm chính sách security duy nhất | Không đảm bảo access control | Kiểm tra HTTP authorization và method/service |
| Hard-code mọi path theo context path nội bộ | Matcher không khớp sau proxy/context changes | Dùng matcher phù hợp và integration test |

## 12. Quy trình kiểm thử an toàn trước production

Một checklist thực tế:

1. **Lập ma trận URL + HTTP method + quyền mong muốn**. Bao gồm public, account, admin, API nhạy cảm, assets, error và actuator nếu được triển khai.
2. **Đọc rule theo đúng thứ tự**: nếu hai matcher overlap, xác định rule nào thắng và có cố tình như vậy không.
3. **Kiểm thử anonymous** trên URL cần bảo vệ; với HTTP Basic thường 401, với form login thường redirect.
4. **Kiểm thử user role thấp** vào URL cao hơn: cần bị deny (thường 403).
5. **Kiểm thử user role đúng nhưng thiếu authority bổ sung** ở các rule authority-based; không mặc định admin có tất cả permission.
6. **Kiểm thử mỗi HTTP method** tương ứng, nhất là POST/PUT/PATCH/DELETE, không chỉ GET.
7. **Kiểm thử fallback** với controller tồn tại nhưng không nằm trong các route được phép.
8. **Kiểm thử static resources, /error và dispatcher types** nếu app có forward/error rendering.
9. **Kiểm thử CSRF/CORS riêng**; tránh nhầm lỗi 403 do CSRF với lỗi `AuthorizationManager`.
10. **Kiểm thử nhiều SecurityFilterChain** nếu dự án có; xác minh @Order, securityMatcher, chain cuối và filter chain được chọn.
11. **Kiểm thử quyền theo dữ liệu thực** ở service/method: owner, tenant, trạng thái đơn hàng, thời gian truy cập.
12. **Kiểm thử sau khi refactor URL**: đổi path/controller không được vô tình mở quyền.
13. **Audit/observability an toàn:** theo dõi authorization denied mà không log password, token, session ID hoặc dữ liệu cá nhân quá mức.
14. **Đánh giá mặc định deny by default** cho endpoint không định nghĩa rõ; khi mở public, phải có quyết định và test tương ứng.

Khi production có API Gateway, reverse proxy hoặc ingress, đừng dựa vào một lớp gateway duy nhất để bảo vệ resource. Backend nên thực thi authorization phù hợp với danh tính đáng tin và kiểm tra phạm vi quyền.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `authorizeHttpRequests` khác `RequestMatcherDelegatingAuthorizationManager` thế nào?

**Đáp:** `authorizeHttpRequests` là DSL khai báo các luật HTTP; `RequestMatcherDelegatingAuthorizationManager` là cơ chế điều phối các cặp matcher→manager được xây cho việc đánh giá rule.

**Câu 2.** Hai rule `/api/**.permitAll()` và `/api/admin/**.hasRole("ADMIN")` đặt theo thứ tự đó có an toàn cho `/api/admin/users` không?

**Đáp:** Không. Matcher `/api/**` đứng trước và khớp, nên request được permitAll; rule sau không chạy.

**Câu 3.** Nếu rule đầu tiên khớp nhưng user không đủ quyền, có chuyển xuống rule tiếp theo không?

**Đáp:** Không. Rule đã được chọn theo matcher; authorization manager của rule đó quyết định, không thử rule bên dưới.

**Câu 4.** `securityMatcher("/api/**")` và `requestMatchers("/api/**")` khác ở đâu?

**Đáp:** securityMatcher quyết định **SecurityFilterChain** có xử lý request; requestMatchers bên trong authorizeHttpRequests chọn **rule phân quyền** sau khi chain đã được chọn.

**Câu 5.** `hasRole("ADMIN")` mặc định kiểm tra authority nào?

**Đáp:** Thường là `ROLE_ADMIN`. Không truyền `"ROLE_ADMIN"` vào `hasRole` khi dùng prefix role mặc định.

**Câu 6.** Một admin không có `report:read` có truy cập rule `hasAuthority("report:read")` được không?

**Đáp:** Không, trừ khi hệ thống có chính sách mở rộng quyền rõ ràng. Role ADMIN không tự động gộp mọi authority khác.

**Câu 7.** Vì sao cần `anyRequest().denyAll()`?

**Đáp:** Nó làm fallback deny rõ ràng cho URL không thuộc các rule trước. Tuy nhiên cần explicit permit cho tài nguyên công khai hợp lệ.

**Câu 8.** Tại sao controller `@GetMapping("/orphaned")` vẫn có thể nhận 403?

**Đáp:** Request bị `AuthorizationFilter` từ chối theo fallback denyAll trước khi controller được gọi.

**Câu 9.** Rule `permitAll()` có tự vô hiệu hóa CSRF không?

**Đáp:** Không. CSRF là một filter/cơ chế riêng và có thể từ chối unsafe requests trước authorization.

**Câu 10.** Làm sao kiểm tra user A không xem được đơn hàng của user B?

**Đáp:** Cần ownership/tenant authorization ở service/method hoặc policy có dữ liệu đáng tin. `authenticated()` đơn thuần không đủ.

**Câu 11.** Khi user chưa login vào URL bảo vệ, status luôn 403?

**Đáp:** Không. Với HTTP Basic thường 401; form login có thể 302 tới trang login. `AuthenticationEntryPoint` và loại authentication quyết định response.

**Câu 12.** Vì sao không nên dùng `web.ignoring()` thay `permitAll()` cho tất cả URL public?

**Đáp:** Ignoring bỏ qua security filter chain và có thể mất security headers/cơ chế khác; permitAll vẫn đi qua chain.

**Ghi nhớ:** **`authorizeHttpRequests` tạo danh sách quy tắc HTTP. `RequestMatcherDelegatingAuthorizationManager` chọn rule đầu tiên có `RequestMatcher` khớp, rồi giao `AuthorizationManager` của rule đó quyết định. Sắp xếp matcher cụ thể trước matcher rộng, đặt fallback rõ ràng, kiểm tra chain selection riêng và luôn test cả 401/403.**