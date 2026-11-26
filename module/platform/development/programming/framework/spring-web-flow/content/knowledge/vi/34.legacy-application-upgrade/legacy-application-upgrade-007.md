# Xác minh API phân quyền khi nâng cấp Spring Security

Khi nâng cấp một ứng dụng Spring MVC và Spring Web Flow cũ, cấu hình phân quyền thường là phần dễ bị bỏ sót. Ứng dụng có thể vẫn khởi động sau khi đổi dependency, nhưng URL trước đây chỉ dành cho quản trị viên lại cho phép người dùng thường truy cập, một số request bị từ chối sai hoặc annotation bảo vệ service không còn được kích hoạt như mong đợi.

Spring Security đã chuyển dần từ cấu hình kế thừa dựa trên `WebSecurityConfigurerAdapter`, `authorizeRequests`, các matcher riêng như `antMatchers` sang cấu hình bean `SecurityFilterChain`, DSL `authorizeHttpRequests` và mô hình `AuthorizationManager`. Phân quyền ở tầng method cũng có cấu hình mới qua `@EnableMethodSecurity`.

Bài này thuộc chương **Nâng cấp ứng dụng cũ** của module **SPRING_WEB_FLOW**. Mục tiêu là xác minh API phân quyền sau khi nâng cấp, đặc biệt ở ranh giới giữa request HTTP, FlowExecutor, state/event của Web Flow và service nghiệp vụ. Một request đi vào flow có thể dùng chung URL cho nhiều event; vì vậy cần kiểm tra cả quy tắc URL lẫn quyền truy cập tài nguyên tại service.

Sau bài học, bạn có thể:

1. Nhận diện API cấu hình phân quyền cũ và API thay thế.
2. Chuyển cấu hình từ `WebSecurityConfigurerAdapter` sang bean `SecurityFilterChain`.
3. Chuyển `authorizeRequests` và matcher cũ sang `authorizeHttpRequests`, `requestMatchers` và `securityMatcher` đúng vai trò.
4. Hiểu thứ tự matcher, khác biệt giữa role và authority, và tác động của dispatcher type.
5. Chuyển method security sang `@EnableMethodSecurity` và xác minh các annotation vẫn hoạt động.
6. Dùng `AuthorizationManager` cho chính sách phân quyền tùy chỉnh.
7. Bảo vệ endpoint Spring Web Flow và kiểm tra quyền nghiệp vụ tại service.
8. Viết integration test để chứng minh người dùng đúng quyền được phép và người dùng thiếu quyền bị từ chối.

## 1. Phân biệt authentication và authorization

Hai khái niệm này có liên quan nhưng giải quyết hai câu hỏi khác nhau:

- **Authentication (xác thực):** request thuộc về ai? Ví dụ người dùng đã đăng nhập với principal `alice`.
- **Authorization (phân quyền):** người đó được phép làm gì trên tài nguyên nào? Ví dụ `alice` có quyền xem đơn hàng `ORD-100` hay không.

Một request có thể xác thực thành công nhưng vẫn không được phép thực hiện hành động. Ví dụ người dùng có authority `ROLE_USER` đã đăng nhập, nhưng không có quyền truy cập màn quản trị hoặc đơn hàng thuộc tài khoản khác.

| Tình huống | Kết quả thường gặp |
| --- | --- |
| Chưa đăng nhập, endpoint yêu cầu authentication | Chuyển tới trang đăng nhập hoặc trả 401 tùy entry point |
| Đã đăng nhập nhưng thiếu authority | 403 Forbidden |
| Đã đăng nhập và đủ authority | Request được phép đi tiếp |
| Có role chung nhưng không sở hữu tài nguyên cụ thể | Vẫn phải bị từ chối ở kiểm tra quyền tài nguyên |

Đừng coi việc thay đổi API cấu hình là bằng chứng chính sách phân quyền vẫn đúng. Sau nâng cấp, cần kiểm tra lại **ai được phép gọi URL**, **ai được phép gọi service**, và **quyền có được kiểm tra trên đúng tài nguyên hay không**.

## 2. Những API phân quyền thường gặp trong ứng dụng cũ

Một cấu hình cũ có thể trông như sau:

```java
@EnableWebSecurity
public class LegacySecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/assets/**").permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .antMatchers("/orders/**").hasAnyRole("USER", "ADMIN")
                .anyRequest().authenticated()
            .and()
            .formLogin();
    }
}
```

Cấu hình này kết hợp ba phần:

- `WebSecurityConfigurerAdapter` là base class để override cấu hình.
- `authorizeRequests` mở DSL phân quyền request theo mô hình cũ.
- `antMatchers` khai báo các đường dẫn cần áp dụng quy tắc.

Khi nâng cấp, không nên thay tên API một cách máy móc. Cần xác định từng matcher đang bảo vệ URL nào, thứ tự rule ra sao và ứng dụng có phụ thuộc vào cách match của Spring MVC hay không.

### Bảng chuyển đổi API

| API cũ | Hướng chuyển đổi | Điều cần xác minh |
| --- | --- | --- |
| `WebSecurityConfigurerAdapter` | Bean `SecurityFilterChain` | Mọi filter và chính sách cũ đã được đưa vào đúng chain |
| `configure(HttpSecurity)` | Cấu hình trực tiếp trong method tạo bean | Không bỏ sót login, logout, CSRF, session hoặc exception handling |
| `authorizeRequests()` | `authorizeHttpRequests(...)` | Các rule được áp dụng theo thứ tự mong muốn |
| `antMatchers(...)` | `requestMatchers(...)` | Semantics path có giống cấu hình cũ không |
| `mvcMatchers(...)` | `requestMatchers(...)` hoặc RequestMatcher tường minh | Servlet path, context path và MVC mapping |
| `regexMatchers(...)` | RequestMatcher phù hợp với regex hoặc matcher tường minh | Regex cũ có đang match quá rộng không |
| `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity` | Pre/post, secured và JSR-250 được bật đúng |
| `AccessDecisionManager` / voter tùy chỉnh | Xem xét `AuthorizationManager` | Logic grant/deny và thứ tự quyết định được giữ nguyên |
| `WebSecurity.ignoring()` | Ưu tiên `permitAll()` khi phù hợp | Request có còn đi qua security filter chain không |

`WebSecurityConfigurerAdapter` đã bị deprecated từ Spring Security 5.7 và bị loại khỏi Spring Security 6. Các matcher `antMatchers` và `mvcMatchers` cũng không còn trong DSL mới của Spring Security 6. Hãy kiểm tra phiên bản đích của dự án vì một số giai đoạn chuyển tiếp ở 5.8 vẫn hỗ trợ API cũ để giúp di trú từng bước.

## 3. Chuyển từ WebSecurityConfigurerAdapter sang SecurityFilterChain

Thay vì kế thừa adapter, khai báo bean `SecurityFilterChain`:

```java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/orders/**")
                    .hasAnyRole("USER", "ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

Cách mới làm rõ mỗi bean xây dựng một filter chain. Nếu ứng dụng chỉ có một chain, rule có thể đặt trong một bean như ví dụ. Nếu ứng dụng có nhiều nhóm endpoint với cấu hình khác nhau, cần khai báo nhiều bean và thứ tự phù hợp.

### Những cấu hình khác phải được chuyển cùng

Khi bỏ adapter, đừng chỉ mang phần authorization sang bean mới rồi quên những cấu hình khác. Kiểm tra các phần ứng dụng cũ đã override:

- Authentication provider, user details service hoặc authentication manager.
- Form login, logout và success/failure handler.
- CSRF, CORS và session management.
- Exception handling và access denied handler.
- Remember-me, HTTP Basic hoặc resource server.
- Security headers và request cache.
- Method security được bật ở cấu hình khác hay chưa.

Các API cấu hình authentication có thể thay đổi theo phiên bản. Hãy chuyển từng phần theo API của phiên bản Spring Security đích, rồi kiểm tra filter chain thực tế trong integration test.

## 4. Chuyển authorizeRequests sang authorizeHttpRequests

Ví dụ DSL mới:

```java
@Bean
SecurityFilterChain applicationSecurity(HttpSecurity http)
        throws Exception {

    http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/assets/**").permitAll()
        .requestMatchers("/login", "/about").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .requestMatchers("/reports/**")
            .hasAuthority("REPORT_READ")
        .requestMatchers(HttpMethod.POST, "/orders/**")
            .hasAnyAuthority("ORDER_WRITE", "ROLE_ADMIN")
        .anyRequest().authenticated()
    );

    return http.build();
}
```

`authorizeHttpRequests` dùng mô hình authorization manager cho các request. Các phương thức quen thuộc như `permitAll`, `authenticated`, `hasRole` và `hasAuthority` vẫn có thể diễn đạt phần lớn chính sách thông thường.

### Quy tắc đầu tiên khớp sẽ được áp dụng

Thứ tự khai báo matcher rất quan trọng. Ví dụ:

```java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/admin/help").permitAll()
    .anyRequest().authenticated()
)
```

Với cách sắp xếp này, `/admin/help` đã khớp rule `/admin/**` trước nên rule `permitAll` phía sau không được dùng. Nếu muốn trang help công khai, đặt rule cụ thể trước:

```java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/admin/help").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

Sau khi di trú, hãy rà soát từ rule cụ thể nhất tới rule tổng quát nhất. Một rule cuối như `anyRequest().authenticated()` thường giúp tránh endpoint mới vô tình trở thành public, nhưng phải phù hợp với ứng dụng và các filter chain khác.

## 5. Phân biệt requestMatchers và securityMatcher

Hai API có tên gần nhau nhưng dùng ở hai cấp khác nhau.

- `securityMatcher` chọn **toàn bộ filter chain** nào sẽ xử lý request.
- `requestMatchers` bên trong `authorizeHttpRequests` chọn **quy tắc phân quyền** cho request đã đi vào chain đó.

Ví dụ ứng dụng có endpoint FlowExecutor dưới `/flow/**` và các endpoint web thông thường:

```java
@Bean
@Order(1)
SecurityFilterChain flowSecurity(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/flow/**")
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        );

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain applicationSecurity(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/assets/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        );

    return http.build();
}
```

Trong ví dụ, chain đầu tiên chỉ nhận request khớp `/flow/**`; chain thứ hai xử lý phần còn lại. Chain thứ hai không có `securityMatcher` nên là chain dự phòng. Thứ tự `@Order` quyết định chain nào được xét trước.

Nếu không có chain nào khớp request, request có thể không được Spring Security bảo vệ. Vì vậy, kiểm tra cả matcher của từng chain và bảo đảm có chain dự phòng cho các endpoint cần bảo vệ.

### Không nhầm URL trang với URL FlowExecutor

Spring Web Flow có URL mở flow, URL tiếp tục execution và các request phát event. Tùy cấu hình, nhiều event có thể gửi tới cùng một endpoint FlowExecutor. Hãy match URL thực tế browser gửi, không suy ra từ tên flow definition hoặc tên view.

Một flow ID như `checkout` không nhất thiết là URL `/checkout/**`. Hãy kiểm tra mapping của FlowHandlerMapping, FlowExecutor và DispatcherServlet trong cấu hình ứng dụng.

## 6. Xác minh semantics của request matcher

Khi thay `antMatchers` hoặc `mvcMatchers` bằng `requestMatchers`, không được mặc định rằng mọi đường dẫn vẫn được diễn giải y hệt.

`requestMatchers(String...)` chọn matcher phù hợp theo môi trường Spring Security/Spring MVC và phiên bản đang dùng. Khi ứng dụng có servlet path, nhiều DispatcherServlet, context path hoặc đường dẫn có biến, cần xác minh matcher thực tế.

Các câu hỏi cần kiểm tra:

- Pattern có tính từ context path hay servlet path?
- Ứng dụng có DispatcherServlet đặt dưới prefix riêng không?
- Có endpoint cùng path nhưng khác HTTP method không?
- Path variable hoặc trailing slash có làm thay đổi kết quả không?
- Có rule regex cũ đang match cả URL ngoài dự kiến không?
- Request forward/error dispatch có được xử lý theo chính sách mong muốn không?

Nếu semantics mặc định không đủ rõ, cung cấp một `RequestMatcher` tường minh theo API phiên bản đích. Tránh viết matcher mới chỉ dựa vào `startsWith` hoặc chuỗi URL tự cắt nếu có thể gây nhầm path, context hoặc encoded path.

### Kiểm thử matcher thay vì chỉ đọc cấu hình

Tạo test cho từng nhóm đường dẫn: URL hợp lệ, URL gần giống nhưng không hợp lệ, HTTP method khác nhau, context/servlet path và dispatcher type. Kiểm tra cả kết quả allow/deny để phát hiện rule vô tình mở rộng.

## 7. Role và authority không giống nhau

`hasRole("ADMIN")` thường tự thêm prefix mặc định `ROLE_`, tương đương kiểm tra authority `ROLE_ADMIN`. Trong khi đó `hasAuthority("ORDER_READ")` kiểm tra chính xác chuỗi authority được truyền vào.

| Cấu hình | Authority được kiểm tra |
| --- | --- |
| `hasRole("ADMIN")` | `ROLE_ADMIN` theo prefix mặc định |
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` |
| `hasAuthority("ORDER_READ")` | `ORDER_READ` |
| `hasAnyRole("USER", "ADMIN")` | `ROLE_USER` hoặc `ROLE_ADMIN` |
| `hasAnyAuthority("ORDER_READ", "ORDER_WRITE")` | Một trong hai authority chính xác |

Một lỗi nâng cấp phổ biến là đổi `hasRole("ADMIN")` thành `hasAuthority("ADMIN")`. Hai biểu thức này không tương đương nếu authority thực tế có prefix `ROLE_`.

Ứng dụng có thể tùy chỉnh role prefix bằng `GrantedAuthorityDefaults`. Nếu có cấu hình đó, hãy xác minh lại tất cả rule `hasRole` và expression method security. Không đoán prefix chỉ từ tên role trong database.

### Quyền nghiệp vụ nên dùng authority có ý nghĩa

Role thường đại diện nhóm người dùng như ADMIN hoặc USER. Authority có thể mô tả hành động cụ thể như `ORDER_READ`, `ORDER_WRITE`, `PAYMENT_APPROVE`. Một ứng dụng lớn có thể kết hợp role để nhóm quyền và authority để diễn đạt chính sách chi tiết.

## 8. Chuyển method security sang EnableMethodSecurity

Cấu hình cũ thường dùng:

```java
@Configuration
@EnableGlobalMethodSecurity(prePostEnabled = true)
public class LegacyMethodSecurityConfig {
}
```

Cấu hình mới:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

`@EnableMethodSecurity` bật pre/post annotations theo mặc định. Nếu ứng dụng dùng `@Secured` hoặc JSR-250 như `@RolesAllowed`, hãy bật rõ các tùy chọn tương ứng:

```java
@Configuration
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfig {
}
```

Trước khi đổi annotation, lập danh sách những method đang dùng:

- `@PreAuthorize`
- `@PostAuthorize`
- `@PreFilter`
- `@PostFilter`
- `@Secured`
- `@RolesAllowed`

Sau khi nâng cấp, xác nhận cấu hình method security được nạp trong application context và bean được gọi qua Spring proxy. Nếu annotation không được kích hoạt, URL authorization có thể vẫn cho request vào controller trong khi service không còn lớp kiểm tra quyền dự kiến.

## 9. Đặt authorization ở service boundary

Trong Spring Web Flow, flow action thường gọi service để tải hoặc cập nhật dữ liệu. Không nên chỉ dựa vào việc người dùng không nhìn thấy nút hoặc transition trên giao diện.

Ví dụ service:

```java
@Service
public class OrderService {

    @PreAuthorize("@orderAuthorization.canRead(authentication, #orderId)")
    public Order findForReview(String orderId) {
        return orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));
    }

    @PreAuthorize("@orderAuthorization.canEdit(authentication, #orderId)")
    public void updateDeliveryNote(String orderId, String note) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.updateDeliveryNote(note);
        orderRepository.save(order);
    }
}
```

Bean `orderAuthorization` là chính sách do ứng dụng cung cấp. Nó cần kiểm tra principal hiện tại, quyền sở hữu hoặc tenant, trạng thái nghiệp vụ và quyền hành động. `orderId` lấy từ flow input hoặc request vẫn phải được coi là dữ liệu đầu vào cần xác minh.

### Vì sao không chỉ bảo vệ flow URL?

FlowExecutor có thể nhận nhiều event khác nhau trên cùng một URL. URL authorization có thể xác minh người dùng đã đăng nhập hoặc có quyền truy cập nhóm endpoint, nhưng không nhất thiết biết event đang gọi là `viewOrder`, `editAddress` hay `confirmPayment`.

Vì vậy:

- Dùng HTTP authorization để bảo vệ endpoint và nhóm URL.
- Dùng method/domain authorization để kiểm tra quyền trên tài nguyên cụ thể.
- Không coi transition bị ẩn trong view là biện pháp bảo mật.
- Không tin ID hoặc trạng thái được giữ trong flow scope nếu chưa xác minh lại ở service.

### Cẩn thận với PostAuthorize

`@PostAuthorize` kiểm tra sau khi method đã thực thi. Nó có thể hữu ích khi cần kiểm tra object trả về, nhưng không nên dùng thay `@PreAuthorize` cho method có side effect như ghi đơn, capture payment hoặc xóa dữ liệu. Với thao tác thay đổi trạng thái, hãy kiểm tra quyền trước khi thực hiện.

## 10. Xác minh method security thực sự được áp dụng

Method security dựa trên Spring AOP proxy. Vì vậy, một số cách gọi có thể bỏ qua proxy:

```java
@Service
public class OrderService {

    public void update(String orderId) {
        updateInternal(orderId); // self-invocation có thể không đi qua proxy
    }

    @PreAuthorize("@orderAuthorization.canEdit(authentication, #orderId)")
    public void updateInternal(String orderId) {
        // Cập nhật dữ liệu
    }
}
```

Lời gọi nội bộ `this.updateInternal(...)` không nhất thiết đi qua proxy Spring, nên interceptor method security có thể không chạy. Cách tổ chức tốt hơn là đặt method được bảo vệ ở một bean service riêng và gọi bean đó qua dependency injection.

Ngoài ra, xác minh:

- Bean thực sự được Spring quản lý.
- Method được gọi qua proxy.
- Cấu hình `@EnableMethodSecurity` có trong context đang chạy.
- Annotation nằm ở vị trí mà proxy/method security nhận diện.
- Test không gọi trực tiếp object được tạo bằng `new`.
- Parameter name dùng trong SpEL có thể được phân giải đúng; nếu cần, cấu hình biên dịch có metadata tên tham số hoặc dùng annotation hỗ trợ tên tham số theo phiên bản.

Nếu unit test gọi trực tiếp một object không qua Spring context, test đó không chứng minh method security hoạt động.

## 11. Chuyển AccessDecisionManager và voter tùy chỉnh

Một số ứng dụng cũ có chính sách phân quyền riêng thông qua `AccessDecisionManager`, `AccessDecisionVoter` hoặc voter tự viết. Mô hình authorization mới khuyến khích dùng `AuthorizationManager`.

Voter cũ thường nhận authentication, object bảo vệ và config attributes rồi trả về grant, deny hoặc abstain. Khi di trú, cần hiểu rõ:

- Voter nào được gọi cho URL/method nào?
- Thứ tự voter có ảnh hưởng kết quả không?
- Cách tổng hợp grant/deny/abstain là affirmative, unanimous hay consensus?
- Có voter nào dựa vào request attribute hoặc domain object không?
- Có quy tắc deny ưu tiên hơn grant không?

Không chuyển một voter phức tạp thành lambda đơn giản nếu làm mất semantics tổng hợp.

Ví dụ một authorization manager cho request:

```java
@Bean
AuthorizationManager<RequestAuthorizationContext> reportAccessManager(
        ReportAuthorizationPolicy policy) {

    return (authentication, context) -> {
        boolean allowed = policy.canRead(
            authentication.get(),
            context.getRequest()
        );
        return new AuthorizationDecision(allowed);
    };
}
```

Dùng manager trong DSL:

```java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/reports/**").access(reportAccessManager)
    .anyRequest().authenticated()
)
```
Dùng manager trong bean tạo filter chain:

```java
@Bean
SecurityFilterChain reportSecurity(
        HttpSecurity http,
        AuthorizationManager<RequestAuthorizationContext> reportAccessManager)
        throws Exception {

    http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/reports/**").access(reportAccessManager)
        .anyRequest().authenticated()
    );

    return http.build();
}
```

`ReportAuthorizationPolicy` là bean ứng dụng chịu trách nhiệm quyết định. Trong production, policy nên lấy thông tin tài nguyên theo cách có kiểm soát, xử lý trường hợp không tìm thấy và không rò rỉ dữ liệu giữa tenant.

### Không dùng AuthorizationManager chỉ để đổi tên voter

Hãy tách phần xác định quyền thành policy/service có thể kiểm thử độc lập. AuthorizationManager nên điều phối quyết định cho request; domain service vẫn chịu trách nhiệm kiểm tra quyền nghiệp vụ khi thao tác tài nguyên.

## 12. permitAll và WebSecurity ignoring

Hai cách cấu hình này không tương đương.

`permitAll` cho phép request qua bước authorization, nhưng request vẫn đi qua Spring Security filter chain và các filter khác có thể tiếp tục hoạt động.

`WebSecurity.ignoring()` bỏ qua security filter chain cho request khớp matcher. Khi đó các filter như security headers hoặc các chức năng bảo vệ khác trong chain cũng không chạy.

Với tài nguyên tĩnh, cấu hình `permitAll` thường là lựa chọn dễ hiểu và giữ request trong chain:

```java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/assets/**").permitAll()
    .anyRequest().authenticated()
)
```

Chỉ dùng `WebSecurityCustomizer`/ignoring khi có lý do rõ ràng và đã đánh giá tác động. Không thêm ignore matcher cho FlowExecutor để sửa lỗi phân quyền hoặc 403; việc đó có thể bỏ qua nhiều lớp bảo vệ.

## 13. Dispatcher type và request được forward

Ứng dụng Spring MVC có thể dùng servlet dispatch như `REQUEST`, `FORWARD`, `ERROR` hoặc `ASYNC`. Với authorization filter mới, cần kiểm tra cách các dispatcher type được phân quyền trong ứng dụng.

Ví dụ, một controller hoặc view có thể forward tới resource nội bộ. Nếu forward bị đánh giá như một request mới và không có rule phù hợp, ứng dụng có thể trả 403 dù request ban đầu đã được phép.

Nếu kiến trúc yêu cầu forward/error dispatch được phép, có thể khai báo rõ:

```java
.authorizeHttpRequests(authorize -> authorize
    .dispatcherTypeMatchers(DispatcherType.FORWARD,
                            DispatcherType.ERROR).permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

Đây chỉ là ví dụ cho ứng dụng thực sự cần cho phép các dispatch đó. Không mở rộng mọi dispatcher type một cách máy móc; cần xác minh controller, view resolver, error page và đường dẫn đích không tạo ra đường truy cập ngoài dự kiến.

## 14. Kiểm tra Spring Web Flow sau khi nâng cấp

Với Spring Web Flow, có ít nhất hai lớp phân quyền cần được xác minh.

**Lớp request:** URL mà browser dùng để mở flow và gửi event phải đi qua SecurityFilterChain phù hợp. Kiểm tra matcher có bao phủ đúng servlet path và endpoint FlowExecutor không.

**Lớp nghiệp vụ:** action/service được gọi bởi event phải xác minh người dùng có quyền với order, payment, account hoặc resource tương ứng. Một user đã đăng nhập không mặc nhiên được phép thao tác trên mọi ID.

Ví dụ:

```xml
<view-state id="reviewOrder" view="checkout/review">
    <transition on="confirm" to="placeOrder"/>
</view-state>

<action-state id="placeOrder">
    <evaluate expression="orderService.placeOrder(order.id)"/>
    <transition on="success" to="completed"/>
</action-state>
```

Method service:

```java
@PreAuthorize("@orderAuthorization.canPlace(authentication, #orderId)")
public Order placeOrder(String orderId) {
    // Đọc lại order và kiểm tra trạng thái trước khi commit.
}
```

Ngay cả khi flow đã tải order ở bước trước, service cần kiểm tra lại quyền và trạng thái ngay tại thời điểm ghi. Quyền có thể thay đổi giữa các request; flow execution có thể sống lâu hơn một lần request HTTP.

### Event không phải permission

Tên event như `confirm`, `cancel`, `edit` chỉ mô tả ý định điều hướng. Nó không phải authority. Không tạo quy tắc kiểu “người dùng thấy nút confirm thì có quyền xác nhận”. Quyết định cuối cùng phải nằm ở server-side policy/service.

## 15. 401, 403 và AccessDeniedHandler

Khi kiểm thử authorization, cần phân biệt response theo cấu hình authentication entry point và access denied handler.

- Người chưa xác thực truy cập endpoint cần đăng nhập có thể bị redirect tới login hoặc nhận 401.
- Người đã xác thực nhưng thiếu authority thường nhận 403.
- Một số ứng dụng có custom entry point hoặc exception translation nên status/redirect khác nhau.

Hãy xác định behavior contract của ứng dụng thay vì viết test mặc định mọi trường hợp không được phép đều là 403.

Nếu ứng dụng có AJAX, response 401/403 không nên bị client hiểu nhầm là fragment thành công. Client cần xử lý riêng trường hợp hết session, thiếu quyền và lỗi nghiệp vụ.

## 16. Quy trình nâng cấp và xác minh theo từng bước

Một quy trình an toàn có thể chia thành các lượt nhỏ:

1. **Chốt phiên bản đích.** Xác định Spring Framework, Spring Boot, Spring Security và Spring Web Flow đang dùng. Kiểm tra yêu cầu JDK và namespace javax/jakarta nếu nâng cấp qua Boot 3.
2. **Liệt kê API cũ.** Tìm `WebSecurityConfigurerAdapter`, `authorizeRequests`, `antMatchers`, `mvcMatchers`, `regexMatchers`, `@EnableGlobalMethodSecurity`, `AccessDecisionManager` và voter tùy chỉnh.
3. **Ghi lại chính sách hiện tại.** Với mỗi URL và method, ghi ai được phép, ai bị từ chối, matcher nào khớp và filter chain nào xử lý.
4. **Chuyển cấu hình HTTP.** Tạo `SecurityFilterChain`, chuyển rule sang `authorizeHttpRequests` và `requestMatchers`.
5. **Kiểm tra chain selection.** Nếu có nhiều chain, xác nhận `securityMatcher`, `@Order` và chain dự phòng.
6. **Chuyển method security.** Dùng `@EnableMethodSecurity`, giữ đúng annotation và tùy chọn `securedEnabled`/`jsr250Enabled`.
7. **Di trú custom authorization.** Đánh giá voter và AccessDecisionManager; chuyển logic cần thiết sang AuthorizationManager hoặc policy/service phù hợp.
8. **Xác minh matcher.** Test URL, HTTP method, servlet path, context path và dispatcher type.
9. **Xác minh Web Flow.** Test URL FlowExecutor, các event trong parent/child và service được gọi bởi flow action.
10. **Chạy integration tests.** Bao gồm anonymous, user thường, admin, resource owner và người dùng thuộc tenant khác.
11. **Kiểm tra log và hành vi runtime.** Tìm lỗi bean wiring, matcher không khớp, method security không kích hoạt hoặc access denied sai.
12. **So sánh behavior trước/sau.** Mỗi trường hợp allow/deny của cấu hình cũ phải có kết quả mong muốn tương ứng ở cấu hình mới.

## 17. Integration test cho URL authorization

Dùng MockMvc cùng Spring Security Test để request đi qua filter chain thực tế. Ví dụ:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderAuthorizationHttpTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousUserCannotOpenProtectedOrderPage() throws Exception {
        mockMvc.perform(get("/orders/ORD-100"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void normalUserCanOpenAllowedOrderEndpoint() throws Exception {
        mockMvc.perform(get("/orders/ORD-100"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void normalUserCannotOpenAdminEndpoint() throws Exception {
        mockMvc.perform(get("/admin/users"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "root", roles = "ADMIN")
    void adminCanOpenAdminEndpoint() throws Exception {
        mockMvc.perform(get("/admin/users"))
            .andExpect(status().isOk());
    }
}
```

Các status trong ví dụ giả định ứng dụng dùng form login và controller/view trả 200 cho endpoint hợp lệ. Với REST API hoặc custom entry point, hãy điều chỉnh assertion theo behavior đã cấu hình.

### Kiểm tra cả HTTP method

Nếu rule chỉ cho phép đọc bằng GET nhưng cập nhật bằng POST, viết test cho cả hai:

```java
@Test
@WithMockUser(roles = "USER")
void userCannotPostToAdminEndpoint() throws Exception {
    mockMvc.perform(post("/admin/users"))
        .andExpect(status().isForbidden());
}
```

Nếu POST được bảo vệ CSRF, thêm token hợp lệ trong test để phân biệt lỗi CSRF với lỗi authorization:

```java
mockMvc.perform(post("/admin/users")
        .with(csrf()))
    .andExpect(status().isForbidden());
```

Không có token có thể khiến request bị từ chối ở CSRF filter trước khi authorization rule được kiểm tra.

## 18. Integration test cho method security và flow service

Test method security qua Spring-managed bean:

```java
@SpringBootTest
class OrderServiceSecurityTest {

    @Autowired
    OrderService orderService;

    @Test
    @WithMockUser(username = "alice", authorities = "ORDER_READ")
    void userWithReadAuthorityCanRead() {
        assertThatCode(() -> orderService.findForReview("ORD-100"))
            .doesNotThrowAnyException();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "ORDER_READ")
    void readOnlyUserCannotEdit() {
        assertThatThrownBy(() ->
            orderService.updateDeliveryNote("ORD-100", "Giao buổi sáng")
        ).isInstanceOf(AccessDeniedException.class);
    }
}
```

Ví dụ giả định policy cho phép `alice` đọc đơn `ORD-100` và từ chối chỉnh sửa. Trong test thật, tạo dữ liệu và policy rõ ràng; không chỉ mock policy thành luôn `true`.

Với Web Flow, integration test cần khởi chạy flow, gửi event tới đúng execution URL và xác nhận service authorization được áp dụng. Các trường hợp quan trọng:

- User có quyền xem nhưng không có quyền sửa.
- User thuộc tenant A thử truy cập order của tenant B.
- User có quyền đọc nhưng không có quyền xác nhận payment.
- Flow đã mở trước đó nhưng quyền bị thu hồi trước event tiếp theo.
- Event được gửi trực tiếp mà không đi qua nút giao diện.
- Child subflow gọi service với resource ID không thuộc user hiện tại.

Khi bị từ chối, xác nhận flow không đi tới end-state thành công và service không thực hiện side effect.

## 19. Ma trận xác minh sau nâng cấp

| ID | Kịch bản | Kết quả cần xác nhận |
| --- | --- | --- |
| T1 | Anonymous truy cập URL cần authentication | Login redirect hoặc 401 theo cấu hình |
| T2 | User thường truy cập admin URL | 403 |
| T3 | Admin truy cập admin URL | Được phép |
| T4 | URL public được khai báo `permitAll` | Được phép nhưng vẫn qua filter chain |
| T5 | Matcher cụ thể đứng trước matcher tổng quát | Rule cụ thể được áp dụng |
| T6 | Matcher tổng quát đứng trước matcher cụ thể | Test phát hiện rule sau bị che khuất |
| T7 | GET và POST cùng path | Chính sách theo method đúng |
| T8 | Request đi qua servlet path/context path | Matcher khớp đúng |
| T9 | Request forward/error | Behavior đúng theo dispatcher policy |
| T10 | FlowExecutor URL | Nằm trong filter chain dự kiến |
| T11 | Flow event `confirm` gửi trực tiếp | Service vẫn kiểm tra quyền |
| T12 | User đọc được order nhưng không sửa được | Method security từ chối update |
| T13 | User truy cập order tenant khác | Policy/service từ chối |
| T14 | `@PreAuthorize` trên Spring bean | Interceptor được kích hoạt |
| T15 | Self-invocation gọi method có annotation | Test phát hiện proxy bị bypass nếu có |
| T16 | `@Secured` hoặc `@RolesAllowed` | Chỉ hoạt động khi bật option tương ứng |
| T17 | Authority `ROLE_ADMIN` với `hasRole` | Prefix được xử lý đúng |
| T18 | Authority `ORDER_READ` với `hasAuthority` | So khớp chính xác |
| T19 | Custom AuthorizationManager | Grant/deny đúng policy |
| T20 | User bị thu hồi quyền giữa hai request flow | Event sau bị từ chối |
| T21 | POST thiếu CSRF token | Bị CSRF filter từ chối riêng |
| T22 | POST có CSRF token nhưng thiếu authority | Bị authorization từ chối |
| T23 | Nhiều SecurityFilterChain | Request vào đúng chain theo matcher và order |
| T24 | Endpoint không khớp chain nào | Test phát hiện khoảng trống bảo vệ |

## 20. Các lỗi nâng cấp thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không biên dịch sau nâng cấp Security 6 | Còn `WebSecurityConfigurerAdapter`, `antMatchers` hoặc `mvcMatchers` | Chuyển sang bean và DSL mới |
| Endpoint public bất ngờ | Rule tổng quát đặt trước rule cụ thể hoặc chain không khớp | Kiểm tra thứ tự matcher và `securityMatcher` |
| User đúng role vẫn bị 403 | Nhầm `hasRole` với `hasAuthority`, prefix sai | Kiểm tra `GrantedAuthority` thực tế |
| Service không còn từ chối truy cập | Method security chưa bật hoặc bean không qua proxy | Kiểm tra `@EnableMethodSecurity`, Spring bean và call path |
| `@Secured` không có tác dụng | `securedEnabled` chưa bật | Cấu hình option tương ứng |
| Flow page vào được nhưng event ghi vẫn chạy trái phép | Chỉ bảo vệ URL hoặc UI, thiếu authorization tại service | Bảo vệ method/domain operation |
| Flow event bị từ chối dù user có quyền | Matcher không đúng servlet path hoặc chain order | Kiểm tra request thực tế và chain được chọn |
| Forward nội bộ bị 403 | Dispatcher type chưa có rule phù hợp | Kiểm tra dispatch và cấu hình rõ ràng nếu cần |
| Static resource thiếu security header | Dùng `ignoring` rộng | Cân nhắc `permitAll` |
| Custom voter cho kết quả khác trước | Mất semantics grant/deny/abstain khi di trú | Viết test contract và chuyển logic có chủ đích |
| Test nhận 403 thay vì kết quả mong đợi | Thiếu CSRF token hoặc thiếu authority | Tách test CSRF và authorization |
| Annotation không hoạt động trong unit test | Gọi object không qua Spring proxy | Dùng Spring context và inject bean |

## 21. Bài thực hành: nâng cấp authorization cho checkout

Hãy nâng cấp một ứng dụng checkout dùng Spring Web Flow từ cấu hình Spring Security cũ sang API mới.

Ứng dụng có các nhóm endpoint:

- `/assets/**`: tài nguyên tĩnh công khai.
- `/admin/**`: chỉ quản trị viên.
- `/orders/**`: người dùng đã đăng nhập; quyền cụ thể phụ thuộc chủ sở hữu đơn.
- `/flow/**`: FlowExecutor nhận event của các flow checkout và payment.

Yêu cầu thực hành:

1. Thay `WebSecurityConfigurerAdapter` bằng các bean `SecurityFilterChain`.
2. Dùng `authorizeHttpRequests` và `requestMatchers` cho URL.
3. Nếu tách chain cho `/flow/**`, khai báo `securityMatcher`, `@Order` và chain dự phòng.
4. Bật method security bằng `@EnableMethodSecurity`.
5. Bảo vệ `OrderService` bằng `@PreAuthorize` gọi policy kiểm tra quyền sở hữu/tenant.
6. Bảo vệ thao tác xác nhận thanh toán tại service; không dựa vào event `confirm` hoặc nút giao diện.
7. Xác minh role prefix và authority thực tế của người dùng.
8. Viết MockMvc test cho anonymous, user, admin và user thuộc tenant khác.
9. Viết method-security test cho quyền đọc, sửa và xác nhận.
10. Gửi event flow trực tiếp trong test để chứng minh service vẫn từ chối user thiếu quyền.
11. Test CSRF riêng để không nhầm 403 CSRF với 403 authorization.
12. Ghi lại mọi API cũ đã thay, matcher semantics và kết quả allow/deny sau nâng cấp.

Đầu ra mong đợi gồm cấu hình security mới, policy/service có kiểm tra quyền, bảng mapping API cũ/mới, test matrix và giải thích cách bảo vệ FlowExecutor cùng domain service.

## 22. Checklist trước khi hoàn tất nâng cấp

- [ ] Xác định đúng phiên bản Spring Security đích và API có sẵn ở phiên bản đó.
- [ ] Không còn phụ thuộc vào `WebSecurityConfigurerAdapter` khi dùng Spring Security 6.
- [ ] Chuyển rule request sang `authorizeHttpRequests`.
- [ ] Chuyển matcher cũ sang `requestMatchers` hoặc matcher tường minh đã kiểm thử.
- [ ] Phân biệt `securityMatcher` chọn filter chain với `requestMatchers` chọn authorization rule.
- [ ] Kiểm tra `@Order` và bảo đảm request cần bảo vệ khớp một chain.
- [ ] Đặt rule cụ thể trước rule tổng quát.
- [ ] Xác minh semantics path, HTTP method, servlet path và dispatcher type.
- [ ] Kiểm tra `hasRole` và `hasAuthority` theo authority thực tế.
- [ ] Chuyển method security sang `@EnableMethodSecurity`.
- [ ] Bật `securedEnabled`/`jsr250Enabled` nếu ứng dụng cần.
- [ ] Xác minh bean và method được gọi qua Spring proxy.
- [ ] Đánh giá custom voter/AccessDecisionManager trước khi chuyển sang AuthorizationManager.
- [ ] Không dùng `ignoring` rộng để né lỗi authorization.
- [ ] Bảo vệ URL FlowExecutor và service nghiệp vụ.
- [ ] Không coi flow event hoặc UI visibility là quyền truy cập.
- [ ] Kiểm tra lại quyền trên resource ID và tenant ở service.
- [ ] Tách test CSRF khỏi test authorization.
- [ ] Có integration test cho allow, deny, anonymous, method security và nhiều filter chain.
- [ ] So sánh hành vi trước/sau để bảo đảm không mở rộng quyền ngoài ý muốn.

**Kết luận:** nâng cấp API phân quyền Spring Security cần bảo toàn chính sách, không chỉ làm mã nguồn biên dịch được. Hãy chuyển cấu hình request sang `SecurityFilterChain` và `authorizeHttpRequests`, kiểm tra matcher/chain order, bật method security bằng `@EnableMethodSecurity` và xác minh các service vẫn thực thi quyền trên tài nguyên thật. Với Spring Web Flow, URL FlowExecutor chỉ là lớp bảo vệ request; quyền xem, sửa, xác nhận đơn hàng hoặc thanh toán phải được kiểm tra lại tại service. Integration test cho cả đường cho phép và đường từ chối là bằng chứng quan trọng nhất rằng nâng cấp không làm thay đổi quyền truy cập ngoài dự kiến.
