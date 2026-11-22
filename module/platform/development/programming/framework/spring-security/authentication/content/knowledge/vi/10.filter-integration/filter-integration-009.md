# Đặt thứ tự bộ lọc và tránh đăng ký cùng bộ lọc hai lần

Spring Security trong kiến trúc **Servlet** dựa trên một tập hợp các `Filter` hoạt động trước khi HTTP request tới controller. Thứ tự của các filter quyết định **khi nào security context được nạp, khi nào credential được xác minh, khi nào quyền được kiểm tra**, và request có được tiếp tục đi xuống `DispatcherServlet` hay không. Nếu authentication filter chạy quá muộn, những quyền đúng vẫn có thể bị từ chối; nếu filter chạy quá sớm hoặc được tự đăng ký ngoài security chain, nó có thể không nhìn thấy `Authentication` đáng tin cậy. Một nguy cơ khác là cùng một filter được đăng ký **hai lần**: một lần tự động ở Servlet container bởi Spring Boot, một lần trong `SecurityFilterChain` bằng `http.addFilterBefore/After(...)`.

Bài thuộc nhóm **Tích hợp bộ lọc** của Spring Security Authentication. Mục tiêu là phân biệt các tầng ordering, hiểu `FilterChainProxy` và các chain matcher, chọn đúng điểm chèn custom filter, ngăn tự động đăng ký trùng ở Spring Boot, nhận diện giới hạn của `OncePerRequestFilter`, debug bằng filter chain log và kiểm thử tự động. Ví dụ **Java 17 chạy độc lập dạng console** sẽ sử dụng `FilterChainProxy` thật và mock Servlet request để cho thấy cùng một instance filter có thể được gọi hai lần trong **một request**.

**Tóm tắt nguyên tắc:** Một custom authentication filter nên xuất hiện **một lần, ở đúng `SecurityFilterChain`, đúng vị trí sau các bước chuẩn bị context/protection và trước authorization**, đồng thời chỉ đặt một `Authentication` đáng tin sau khi verifier/provider đã kiểm chứng thông tin đầu vào.

## 1. Sơ đồ ba tầng: chỗ nào quyết định thứ tự?

~~~text
Client HTTP
   |
   v
[1] Servlet container FilterChain
     Container Filter trước security (nếu có)
     DelegatingFilterProxy("springSecurityFilterChain")
       |
       v
     [2] FilterChainProxy: duyệt SecurityFilterChain theo @Order
           SecurityFilterChain #1 /api/admin/**
           SecurityFilterChain #2 /api/**
           SecurityFilterChain #3 fallback /**
           -> CHỈ chọn chain đầu tiên có matcher khớp
              |
              v
     [3] Filter order TRONG CHAIN ĐƯỢC CHỌN
           SecurityContextHolderFilter
           các security/protection filters
           LogoutFilter
           authentication filters (form / Basic / Bearer / custom)
           AnonymousAuthenticationFilter
           ExceptionTranslationFilter
           AuthorizationFilter
              |
              v
     Filter sau security ở container (nếu có)
   |
   v
DispatcherServlet -> Controller
~~~

Sơ đồ mang tính **khái niệm**, không phải danh sách filter cố định cho mọi phiên bản hoặc mọi cách cấu hình. Filter cụ thể có mặt tùy `HttpSecurity`, HTTP Basic/form/JWT/OIDC, session, CSRF, CORS và đường đi của request.

| Tầng | Đơn vị được sắp thứ tự | Cơ chế chính | Ngộ nhận |
|---|---|---|---|
| **Container** | Các Servlet `Filter` đã đăng ký, kể cả `DelegatingFilterProxy` | `FilterRegistrationBean.setOrder`, Servlet registration | Không quyết định vị trí giữa authentication và authorization filters của Spring Security |
| **Giữa các chain** | Các bean `SecurityFilterChain` mà proxy thử matcher | `@Order` trên chain, `securityMatcher` | Proxy không trộn tất cả chain khớp thành một |
| **Trong một chain** | Danh sách security filters thuộc chain đã chọn | Thứ tự Spring Security, `addFilterBefore/After/At` | `@Order` trên class custom filter không tự quyết định thứ tự nội bộ |

Điều quan trọng là cùng một class `Filter` có thể xuất hiện ở nhiều tầng. Nếu nó nằm ở cả container và chain, một request có thể đi qua **cả hai điểm đăng ký**. Không thể sửa vấn đề chỉ bằng đổi số `@Order` trên bean.

### 1.1. DelegatingFilterProxy không xác thực mật khẩu

`DelegatingFilterProxy` là bridge giữa Servlet container và Spring `ApplicationContext`. Container gọi proxy, proxy tìm bean tên `springSecurityFilterChain`, thường là `FilterChainProxy`. Bản thân proxy không tải `UserDetails`, không băm password hay kiểm tra chữ ký JWT. Nó ủy quyền cho bộ lọc do Spring quản lý.

`FilterChainProxy` chọn chain và điều phối lifecycle như `HttpFirewall`/cleanup. Authentication filters như `UsernamePasswordAuthenticationFilter`, `BasicAuthenticationFilter` và `BearerTokenAuthenticationFilter` mới tiếp nhận thông tin tương ứng. Kết quả được kiểm chứng bởi `AuthenticationManager`/provider, decoder hoặc verifier thích hợp.

### 1.2. Container FilterChain khác SecurityFilterChain

`jakarta.servlet.FilterChain` biểu diễn phần còn lại của chuỗi filter container rồi đến servlet. `SecurityFilterChain` biểu diễn **matcher + danh sách security filters** cho một loại request. Khi custom filter gọi `chain.doFilter(request,response)`, nó cho xử lý tiếp xuống filter/servlet downstream; khi không gọi, request có thể dừng ở đó theo quyết định có chủ đích.

Không gọi `chain.doFilter` không tự động có nghĩa bảo mật hơn. Một filter chặn request phải xử lý HTTP response/exception đúng giao thức; một filter tiếp tục request với authentication giả lại mở lỗ hổng.

## 2. Thứ tự ở Servlet container: @Component, @Order và FilterRegistrationBean

Trong ứng dụng Spring Boot Servlet, một `Filter` được khai báo thành Spring bean thường được Spring Boot tự đăng ký với embedded Servlet container, trừ khi có registration policy vô hiệu hóa. Ví dụ:

~~~java
@Component
public final class CorrelationIdFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        // Xử lý correlation ID của request tại container.
        chain.doFilter(request, response);
    }
}
~~~

Đây là **mảnh cấu hình** cần imports Spring Web và app context thực, không phải chương trình độc lập. Filter correlation ID thực sự không cần biết user đã đăng nhập có thể **được thiết kế** để chạy ở container cho mọi URL.

Thứ tự ở tầng này có thể được cấu hình qua:

~~~java
@Bean
FilterRegistrationBean<CorrelationIdFilter> correlationRegistration(
        CorrelationIdFilter filter) {

    FilterRegistrationBean<CorrelationIdFilter> bean =
            new FilterRegistrationBean<>(filter);
    bean.setOrder(-100);
    bean.addUrlPatterns("/*");
    return bean;
}
~~~

Đoạn Java minh họa registration. Nó điều khiển **Servlet container filter order**, không tự làm filter chạy giữa `BasicAuthenticationFilter` và `AuthorizationFilter`.

### 2.1. Khi nào đặt filter ở container là hợp lý?

- Tạo correlation ID, chuẩn hóa logging metadata tối thiểu không phụ thuộc principal.
- Một số thao tác xử lý response/request chung cần áp dụng trước cả security chain, theo thiết kế rõ.
- Chức năng infrastructure mà framework/container có contract riêng.

Nếu filter cần `SecurityContextHolder.getContext().getAuthentication()` đã được xác minh, việc đặt nó **trước `DelegatingFilterProxy`** có thể nhận null/anonymous hoặc auth chưa được nạp. Với authorization/audit sau login, hãy đặt đúng trong security chain hoặc dùng framework events/handlers.

Nếu filter container log toàn bộ `Authorization`/`Cookie`/body chứa password để debug, đó là rủi ro credential leak. Correlation ID nên được kiểm soát độ dài, không dùng trực tiếp user input không giới hạn làm log key.

## 3. Thứ tự giữa các SecurityFilterChain: first-match wins

`FilterChainProxy` chỉ dùng **SecurityFilterChain đầu tiên khớp request**. Ví dụ:

~~~text
@Order(1) /api/admin/**   -> admin token rules
@Order(2) /api/**         -> general API token rules
fallback /**              -> website session rules

GET /api/admin/users  -> admin chain
GET /api/orders       -> general API chain
GET /home             -> web chain
~~~

Nếu fallback `/**` được xét trước, nó có thể lấy mọi request, khiến API chain không chạy. Nếu **không chain nào khớp**, request có thể đi xuống servlet mà không qua security filters do Spring Security quản lý cho URL đó. Đây là **bypass nguy hiểm** đối với endpoint cần bảo vệ.

### 3.1. @Order trên chain không phải order của filter

~~~java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http)
        throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a
            .requestMatchers("/api/health").permitAll()
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

`@Order(1)` làm API chain được xét sớm. Nó không có nghĩa Basic authentication chạy ở vị trí filter thứ nhất. Cách sắp **filter nội bộ** do Spring Security framework và `addFilterBefore/After/At` xử lý.

### 3.2. securityMatcher khác requestMatchers

- `securityMatcher("/api/**")` định nghĩa phạm vi **toàn bộ security chain**.
- `requestMatchers("/api/health").permitAll()` chỉ cho phép public access **trong chain đã chọn**; các protection filters còn hiệu lực theo config.
- `web.ignoring()` hoặc URL không thuộc bất kỳ chain nào có thể **bỏ qua toàn bộ security filter processing**.

Một endpoint public có thể vẫn cần HTTP headers, CORS, auditing hoặc context processing. Vì vậy `permitAll` thường hữu ích hơn việc bỏ qua Spring Security hoàn toàn.

### 3.3. Filter ở hai chain có bị gọi hai lần không?

Nếu cùng object `myFilter` nằm trong cả API chain và Web chain, nhưng một request chỉ chọn **một chain**, thông thường object đó chỉ được gọi theo chain đã chọn. Đó **không** tự động là double registration. Ngược lại, nếu object nằm **một lần trong container và một lần trong selected chain**, hoặc được thêm **hai lần vào cùng selected chain**, nó có thể bị gọi hai lần thật.

Phân biệt ba tình huống này trước khi đổi cấu hình.

## 4. Thứ tự filters bên trong chain: các mốc bảo mật

Spring Security thiết kế thứ tự các filter để xử lý request có các bước phù hợp:

~~~text
SecurityContext được nạp hoặc chuẩn bị
       |
Protection: security headers, CORS, CSRF... tùy cấu hình
       |
Logout handling
       |
Authentication: form, Basic, Bearer, API key custom...
       |
AnonymousAuthenticationFilter khi chưa xác thực
       |
ExceptionTranslationFilter
       |
AuthorizationFilter
       |
Controller nếu request được cho phép
~~~

Sơ đồ không đại diện chính xác cho mọi loại chain; ví dụ không phải API nào cũng có form login, CSRF hay bearer filter. Spring Security duy trì order có chủ đích để request chưa có authentication không thể qua authorization như user đã xác thực.

### 4.1. Vì sao authentication phải đi trước authorization?

Một token hợp lệ đến server nhưng custom authentication filter chạy **sau** `AuthorizationFilter` sẽ khiến authorization nhìn thấy context null/anonymous và từ chối. Cách sửa là đặt filter vào đúng vị trí **sau setup/protection cần thiết và trước authorization**, không tắt authorization.

Lỗi ngược lại nguy hiểm hơn: custom filter tự tạo `UsernamePasswordAuthenticationToken.authenticated(...)` chỉ từ username/roles do client gửi, bỏ qua `AuthenticationManager` hoặc JWT verifier. Khi ấy “đúng vị trí” cũng không cứu được vì **không có trust boundary**. Chỉ đặt Authentication đáng tin sau khi credential/token đã được kiểm chứng.

### 4.2. Vị trí phải phụ thuộc chức năng

| Custom filter làm gì? | Cần những bước nào đã xảy ra? | Điểm neo tham khảo |
|---|---|---|
| Bảo vệ bổ sung trước authentication | Context đã có thể nạp, protection theo policy | Sau `SecurityContextHolderFilter` khi phù hợp |
| **Custom authentication** | Context/protection ban đầu, chưa đến authorization | Thường **sau `LogoutFilter`** |
| Phân quyền/tenant check | Principal/anonymous đã được thiết lập | Sau `AnonymousAuthenticationFilter` và trước khi downstream được cho phép |
| Audit sự kiện login success/failure | Biết kết quả authentication, response/error policy | Ưu tiên success/failure handlers hoặc Spring events nếu phù hợp |
| Trace ID không đọc security identity | Không phụ thuộc auth | Có thể ở Servlet container |

Gợi ý “đặt custom authentication filter sau `LogoutFilter`” là **nguyên tắc thường dùng**, không phải lời khẳng định nó hợp mọi filter. Một filter audit cần đọc principal **sau khi Basic/JWT đã xác minh** có thể phải đặt sau filter xác thực tương ứng hoặc dùng sự kiện framework.

## 5. Ba API addFilterBefore, addFilterAfter, addFilterAt

`HttpSecurity` cung cấp các method:

~~~java
http.addFilterBefore(customFilter, LogoutFilter.class);

http.addFilterAfter(customFilter, BasicAuthenticationFilter.class);

http.addFilterAt(customFilter, UsernamePasswordAuthenticationFilter.class);
~~~

Đây là **ba lựa chọn độc lập để minh họa API**, không phải ba dòng nên thực hiện cùng lúc cho cùng một filter.

| Method | Tác động | Điều không làm |
|---|---|---|
| `addFilterBefore` | Đặt custom filter trước **slot** filter tham chiếu đã biết | Không tắt filter cũ hoặc container registration |
| `addFilterAfter` | Đặt custom filter sau slot tham chiếu | Không ép tất cả chain đều chứa filter |
| `addFilterAt` | Đặt custom filter **cùng vị trí** tham chiếu | **Không tự loại bỏ filter cũ** |

### 5.1. Bẫy addFilterAt không phải replace tự động

`HttpSecurity` JavaDoc nói rõ: nếu nhiều filters được đặt ở cùng vị trí, thứ tự giữa chúng **không xác định**, và việc đăng ký filter cùng slot **không override filter đã có**. Vì vậy:

~~~java
http.formLogin(Customizer.withDefaults());
http.addFilterAt(customLoginFilter,
                 UsernamePasswordAuthenticationFilter.class);
~~~

Hai dòng là **phản ví dụ rủi ro** nếu bạn tưởng filter mặc định chắc chắn bị thay thế. Khi hai filter đều xử lý login endpoint, request có thể bị tiêu thụ/xử lý theo cơ chế không mong muốn.

Nếu muốn thay cơ chế login, hãy tắt hoặc điều chỉnh phần DSL đã tạo filter cũ, định nghĩa URL/handler/entry point rõ và kiểm thử **filter list thực tế**. Không đặt hai filters cùng slot rồi dựa vào thứ tự ngầm.

### 5.2. @Order trên @Component Filter không thay addFilterBefore

~~~java
@Component
@Order(5)
final class ApiKeyFilter extends OncePerRequestFilter {
    // ...
}
~~~

Đây là snippet minh họa. `@Order` có thể ảnh hưởng container registration của Filter bean do Boot quản lý; nó **không trực tiếp quyết định** filter này chạy trước `AnonymousAuthenticationFilter` trong Spring Security chain. Chọn internal order qua DSL và kiểm thử.

### 5.3. Anchor được nhận diện là gì?

`addFilterBefore/After/At` cần một **filter class có vị trí/order được Spring Security nhận diện**. Với anchor tùy tiện không được đăng ký thứ tự phù hợp, có thể gặp lỗi build cấu hình. Không suy rằng cứ lấy bất kỳ class implements Filter làm anchor sẽ có order hợp lệ.

Với resource server bearer token, `BearerTokenAuthenticationFilter` thuộc nhánh OAuth2 Resource Server; không mặc định có trong ứng dụng chỉ dùng form login. Chọn anchor theo cơ chế xác thực thật, xem Spring Security filter list và các JavaDoc cho đúng phiên bản.

## 6. Double registration trong Spring Boot: vì sao xảy ra?

Tình huống:

~~~java
@Component
final class ApiTokenFilter extends OncePerRequestFilter {
    // doFilterInternal(...) kiểm chứng API token theo provider.
}
~~~

và đồng thời:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http,
                             ApiTokenFilter tokenFilter)
        throws Exception {
    http.securityMatcher("/api/**")
        .addFilterAfter(tokenFilter, LogoutFilter.class);
    return http.build();
}
~~~

Cả hai đều là mảnh cấu hình chưa đủ dependencies/authorization. Nhưng chúng mô tả lỗi:

~~~text
ApiTokenFilter được Spring tạo thành bean:
     |
     +--> Spring Boot đăng ký Filter bean ở Servlet container
     |       (ví dụ mọi request)
     |
     '--> Security config đưa đúng bean vào /api/** chain

GET /api/orders:
  Servlet container -> ApiTokenFilter [registration #1]
      -> DelegatingFilterProxy -> FilterChainProxy
           -> /api/** SecurityFilterChain
                -> ApiTokenFilter [registration #2]
                -> AuthorizationFilter
      -> Controller
~~~

Một request có thể đi qua **hai điểm đăng ký**. Các hệ quả:

- Xác minh token hoặc query account được gọi hai lần, tăng latency.
- Token dùng một lần bị tiêu thụ ở lần đầu và lỗi lần sau.
- Rate limiter/metrics/audit đếm đôi.
- Filter đọc `SecurityContextHolder` ở container trước proxy, chưa thấy principal hợp lệ.
- Một lần chạy nằm ngoài chain, áp dụng lên URL không phải API.
- Body/header đã bị tiêu thụ hoặc response đã commit trước khi downstream xử lý.
- Dispatcher types khác nhau làm sự cố chỉ xuất hiện ở một số request.

**Không kết luận “chắc chắn hai lần doFilterInternal” nếu filter kế thừa `OncePerRequestFilter`**: marker có thể khiến nội dung chính chạy một lần trong nested dispatch, nhưng vẫn là registration sai tầng và dễ gây timing bug.

### 6.1. Hai lần gọi không nhất thiết là hai HTTP requests

Một filter viết:

~~~java
System.out.println("before");
chain.doFilter(request, response);
System.out.println("after");
~~~

đương nhiên tạo hai dòng log dù chỉ có **một invocation**. Một HTTP request cũng có thể có `ASYNC` hoặc `ERROR` dispatch. Muốn chứng minh duplicate registration phải theo dõi:

- Request correlation ID và `DispatcherType`.
- Identity của filter **instance**, bean name và layer.
- Số lần `Filter.doFilter` bắt đầu.
- Số lần `OncePerRequestFilter.doFilterInternal` thật sự chạy.
- FilterChainProxy đã chọn chain nào và số entries của filter trong chain.
- Container có FilterRegistrationBean/auto-registration cho bean đó hay không.

Không đưa raw `Authorization`/`Cookie`/password vào debug log.

## 7. Khắc phục đúng tầng: chọn container hoặc security chain

### 7.1. Nếu muốn filter chỉ ở Spring Security

Có thể giữ filter như Spring bean để dependency injection, nhưng **tắt registration tự động tại container**:

~~~java
@Configuration
class FilterRegistrationConfig {

    @Bean
    FilterRegistrationBean<ApiTokenFilter> disableContainerRegistration(
            ApiTokenFilter filter) {

        FilterRegistrationBean<ApiTokenFilter> registration =
                new FilterRegistrationBean<>(filter);
        registration.setEnabled(false);
        return registration;
    }
}
~~~

Đây là mảnh Spring Boot config. `setEnabled(false)` ngăn Filter bean được Boot đăng ký độc lập tại Servlet container; **không** gỡ instance đã được `http.addFilterAfter` vào `SecurityFilterChain`.

Đây là cách khắc phục phù hợp nếu filter cần chạy **sau các bước context/protection của Spring Security** và chỉ trong namespace đã chọn. Phải test rằng API endpoint vẫn được security chain xử lý; tắt container registration không tự mở rộng matcher.

### 7.2. Hoặc không khai báo instance là Filter bean

Nếu filter không cần lifecycle của một Spring bean độc lập, có thể tạo instance trong security config và inject dependency qua constructor:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http,
                             ApiTokenVerifier verifier)
        throws Exception {

    ApiTokenFilter tokenFilter = new ApiTokenFilter(verifier);

    http.securityMatcher("/api/**")
        .addFilterAfter(tokenFilter, LogoutFilter.class)
        .authorizeHttpRequests(a -> a.anyRequest().authenticated());

    return http.build();
}
~~~

Đây là mảnh cấu hình minh họa; class `ApiTokenVerifier` và `ApiTokenFilter` của dự án phải được triển khai. Nếu instance không được đăng ký thành `Filter` bean ở container, Boot không có bean filter đó để auto-register. Tuy nhiên, bạn vẫn phải xác minh cả cơ chế registration khác (ví dụ `@WebFilter`, manual Servlet registration).

### 7.3. Nếu muốn filter ở container

Khi filter chỉ xử lý correlation ID hay công việc không cần principal, có thể giữ **container registration** và **không thêm nó** vào `HttpSecurity`. Khi đó nó chỉ xuất hiện tại container một lần, theo URL mapping và order đã cấu hình.

Nếu vừa cần generic request logging ở container vừa cần auth-specific auditing trong security chain, nên tách thành **hai filters với hai trách nhiệm** hoặc dùng framework events, thay vì một bean ở cả hai tầng.

### 7.4. Những cách sửa sai

- Không dùng `setOrder(Integer.MAX_VALUE)` để “dịch đăng ký trùng ra sau”: vẫn còn hai registrations.
- Không tắt `DelegatingFilterProxy` để tránh custom filter chạy hai lần; như vậy có thể bỏ toàn bộ Spring Security.
- Không chỉ dựa vào `OncePerRequestFilter`/marker để che duplicate.
- Không tắt authorization/CSRF để tránh lỗi 401/403 do filter order.
- Không thêm cùng filter bằng nhiều `addFilter...` calls trong một chain.
- Không loại bỏ cả filter chuẩn và entry point nếu chưa thiết kế replacement đầy đủ.

## 8. OncePerRequestFilter: bảo đảm có giới hạn, không phải thuốc chữa duplicate

`OncePerRequestFilter` của Spring Framework là base class giúp kiểm soát việc gọi `doFilterInternal` trong phạm vi request/dispatch phù hợp nhờ một **already-filtered request attribute**.

~~~text
Filter.doFilter(...) bị gọi
    |
    v
OncePerRequestFilter.doFilter(...)
    |
    +--> Xem dispatcher type, shouldNotFilter, marker
    |
    +-- Đã có marker phù hợp
    |       -> có thể skip doFilterInternal, tiếp tục chain
    |
    '-- Chưa có marker
            -> đánh dấu request
            -> doFilterInternal(...)
            -> dọn marker trong finally
~~~

Nếu cùng instance được đăng ký container **ngoài** proxy và trong security chain, lời gọi ngoài có thể đặt marker trước khi chain nội bộ chạy. Khi security chain gọi lại filter, `doFilterInternal` có thể bị skip, khiến **logic authentication đã chạy ở sai thời điểm** ngoài context. Do đó, dù log “logic chạy một lần” trông hợp lý, security design vẫn có vấn đề.

### 8.1. Async và Error dispatch

`OncePerRequestFilter` có các extension points:

~~~java
protected boolean shouldNotFilter(HttpServletRequest request);
protected boolean shouldNotFilterAsyncDispatch();
protected boolean shouldNotFilterErrorDispatch();
~~~

Đây là method signatures minh họa; mặc định/overrides và Servlet registration dispatcher mapping quyết định behavior. “Once” không có nghĩa luôn đúng một lần suốt tất cả `REQUEST`, `ASYNC`, `ERROR` hoặc redispatch khác.

Nếu có **hai instances** hoặc các bean/filter names khác nhau dẫn đến marker khác nhau, `doFilterInternal` cũng có thể chạy nhiều lần. Ngoài ra, business invariant như “charge đúng một lần” phải được kiểm soát bởi idempotency/transaction ở domain, không dựa vào OncePerRequestFilter.

### 8.2. Khi nào dùng OncePerRequestFilter?

Nó hữu ích cho custom filter theo request, nhưng cần:

- Vị trí đúng trong `SecurityFilterChain`;
- Cơ chế verifier/provider đáng tin;
- Correct response handling và `chain.doFilter` khi cần;
- Giới hạn token/body và redaction;
- Kiểm thử async/error dispatch và thread reuse;
- Không có container registration trùng.

Đừng dùng `OncePerRequestFilter` để “đảm bảo một user chỉ đăng nhập một lần”; đó không phải semantics của lớp này.

## 9. Ví dụ cấu hình Spring Boot với hai chains và một custom filter

Sau đây là **các snippet tích hợp**, không phải một project standalone. Giả định có Spring Boot 3.x, Spring Security Servlet, UserDetailsService/AuthenticationProvider hoặc verifier phù hợp.

### 9.1. Trace filter không chứa credential

~~~java
@Component
final class SafeTraceFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        // Chỉ minh họa nơi ghi method/path và correlation ID.
        // Tuyệt đối không log Cookie/Authorization/raw password.
        chain.doFilter(request, response);
    }
}
~~~

### 9.2. Đăng ký filter đúng một tầng

~~~java
@Bean
FilterRegistrationBean<SafeTraceFilter> traceRegistration(
        SafeTraceFilter filter) {

    FilterRegistrationBean<SafeTraceFilter> registration =
            new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
~~~

### 9.3. Cấu hình hai SecurityFilterChain

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http,
                             SafeTraceFilter trace)
        throws Exception {

    http.securityMatcher("/api/**")
        .addFilterAfter(trace, LogoutFilter.class)
        .authorizeHttpRequests(a -> a
            .requestMatchers("/api/health").permitAll()
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http)
        throws Exception {

    http.authorizeHttpRequests(a -> a
            .requestMatchers("/", "/assets/**").permitAll()
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

**Ý nghĩa:** API chain có ưu tiên trước, trace filter nằm **một lần** trong chain ấy. `GET /home` chỉ dùng Web chain, không gọi trace filter của API; `GET /api/health` tuy `permitAll` vẫn qua API chain. `addFilterAfter(trace, LogoutFilter.class)` chỉ minh họa placement, **không chứng minh trace đã nhìn thấy authenticated user**, bởi Basic authentication filter có thể chạy về sau.

Nếu trace cần audit login success/failure, framework handlers/events phù hợp hơn; nếu cần auth result trong filter, chọn anchor sau mechanism tương ứng và test khi authentication filter chặn request hoặc ném exception.

Cấu hình production cần cân nhắc CSRF, CORS, HTTP Basic qua TLS, session, logout, user store, endpoint paths và yêu cầu nghiệp vụ. Không copy các snippets trên thay một security design hoàn chỉnh.

## 10. Ví dụ Java 17 chạy được: quan sát một lần và hai lần gọi cùng Filter

Chương trình sau dùng **Spring Security `FilterChainProxy` thật** cùng `MockHttpServletRequest` của Spring Test. Không khởi động web server; nó tự gọi proxy bằng mock Servlet request. Một `TraceFilter` implement `jakarta.servlet.Filter` thuần sẽ in `enter`/`exit` trước và sau khi gọi downstream.

Có hai lượt chạy với cùng path `/api/orders`:

1. **ONLY SECURITY:** `audit` chỉ là filter trong `SecurityFilterChain`.
2. **DOUBLE REGISTERED:** bên ngoài proxy, ta cố ý gọi cùng instance `audit` để mô phỏng container auto-registration, rồi bên trong proxy **nó lại được gọi lần nữa**.

### 10.1. Cấu trúc tệp

~~~text
filter-order-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/FilterOrderDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'filter-order-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.3.8'
    implementation 'org.springframework:spring-test:6.1.18'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'example.FilterOrderDemo'
}
~~~

Phiên bản trên nhằm cố định một demo API của **Spring Security 6.3.8 / Spring Framework 6.1.18**, **không phải khuyến nghị sử dụng phiên bản này cho production hiện tại**. Với ứng dụng thật, dùng phiên bản Spring Security/Boot được hỗ trợ và dependency management/BOM thống nhất, cập nhật bản vá bảo mật.

### 10.2. Chương trình đầy đủ

Tạo `src/main/java/example/FilterOrderDemo.java`:

~~~java
package example;

import java.io.IOException;
import java.util.List;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.web.DefaultSecurityFilterChain;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

public final class FilterOrderDemo {

    private static final String PATH = "/api/orders";

    static final class TraceFilter implements Filter {
        private final String name;

        TraceFilter(String name) {
            this.name = name;
        }

        @Override
        public void doFilter(
                ServletRequest request,
                ServletResponse response,
                FilterChain chain)
                throws IOException, ServletException {
            System.out.println("enter " + name);
            chain.doFilter(request, response);
            System.out.println("exit " + name);
        }
    }

    private static void run(
            String title,
            FilterChainProxy proxy,
            TraceFilter shared,
            boolean alsoRegisteredAtContainer)
            throws IOException, ServletException {

        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", PATH);
        request.setServletPath(PATH);
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        FilterChain servlet = (req, res) -> {
            HttpServletRequest http = (HttpServletRequest) req;
            System.out.println("SERVLET " + http.getRequestURI());
        };

        System.out.println("=== " + title + " ===");

        if (alsoRegisteredAtContainer) {
            shared.doFilter(
                    request, response,
                    (req, res) -> proxy.doFilter(req, res, servlet));
        } else {
            proxy.doFilter(request, response, servlet);
        }
    }

    public static void main(String[] args) throws Exception {
        TraceFilter shared = new TraceFilter("audit");

        SecurityFilterChain api = new DefaultSecurityFilterChain(
                new AntPathRequestMatcher("/api/**"),
                new TraceFilter("authentication-slot"),
                shared,
                new TraceFilter("authorization-slot"));

        FilterChainProxy proxy = new FilterChainProxy(List.of(api));

        run("ONLY SECURITY", proxy, shared, false);
        run("DOUBLE REGISTERED", proxy, shared, true);
    }
}
~~~

### 10.3. Biên dịch/chạy bằng Gradle

Trong thư mục project, nếu có Gradle Wrapper tương thích:

~~~bash
./gradlew run
~~~

Nếu chỉ có Gradle đã cài, dùng `gradle run`. Windows PowerShell với wrapper có thể dùng `.\gradlew.bat run`.

Đầu ra các lệnh `System.out.println` (không tính log Gradle):

~~~text
=== ONLY SECURITY ===
enter authentication-slot
enter audit
enter authorization-slot
SERVLET /api/orders
exit authorization-slot
exit audit
exit authentication-slot
=== DOUBLE REGISTERED ===
enter audit
enter authentication-slot
enter audit
enter authorization-slot
SERVLET /api/orders
exit authorization-slot
exit audit
exit authentication-slot
exit audit
~~~

### 10.4. Giải thích thứ tự từng dòng

- Ở **ONLY SECURITY**, request `/api/orders` khớp matcher `/api/**`. Proxy chạy ba filters theo thứ tự mảng trong `DefaultSecurityFilterChain`. Mỗi filter in `enter`, gọi `chain.doFilter` cho filter tiếp theo, cuối cùng gọi Servlet. Khi stack unwinds, các dòng `exit` xuất hiện theo thứ tự ngược.
- Ở **DOUBLE REGISTERED**, bên ngoài proxy có một lời gọi `shared.doFilter` của container giả lập, nên đầu tiên in `enter audit`. Khi proxy đi đến chính instance `shared` trong chain, nó in **lần thứ hai**. Có hai dòng `exit audit` tương ứng. Đây vẫn chỉ là **một request mock** cho kịch bản này.
- Filter `TraceFilter` là **marker để quan sát order**, không kiểm chứng token và không thực thi authorization thật. Tên `authentication-slot`/`authorization-slot` không cấp quyền cho ai.

Ví dụ dùng `Filter` thuần thay vì `OncePerRequestFilter` để làm double invocation nhìn thấy trực tiếp. Nếu dùng `OncePerRequestFilter`, lần gọi nested bên trong có thể skip `doFilterInternal` vì request marker, **không phải chứng minh đăng ký trùng là vô hại**.

### 10.5. Thử thay đổi để tự kiểm chứng

- Đổi chỗ `authentication-slot` và `authorization-slot` trong `DefaultSecurityFilterChain` để thấy thứ tự enter/exit đổi theo. Đây là mô hình cách đặt filter sai order.
- Loại `shared` khỏi list filters nhưng giữ lời gọi ngoài proxy: chỉ còn audit ở **container**, không nằm trong security chain.
- Thêm `shared` hai lần trong một `SecurityFilterChain`: một request vẫn có thể in audit hai lần dù không có container registration.
- Tạo thêm một fallback chain match `/**` và thay thứ tự giữa nó với `/api/**`; kiểm tra first-match ảnh hưởng filter nào chạy.
- Đổi sang `OncePerRequestFilter` ở một dự án thử nghiệm và ghi nhận riêng `doFilter` so với `doFilterInternal`.

**Giới hạn:** demo không dựng Spring Boot context, không dùng Servlet container thật, không kiểm chứng cơ chế tự đăng ký Filter bean và không có JWT/session/CSRF. Nó kiểm chứng hoạt động `FilterChainProxy` và duplicate invocation bằng mô phỏng container call. Vấn đề Boot auto-registration cần được test thêm với ứng dụng Spring Boot thực ở phần sau.

## 11. Debug filter order và đăng ký trùng có hệ thống

### 11.1. Nhìn hai tầng registration

Chẩn đoán theo hai tập câu hỏi riêng:

~~~text
CONTAINER
- Có bao nhiêu registrations tới Filter bean?
- Có FilterRegistrationBean nào tự động bật cho custom Filter?
- DelegatingFilterProxy có được đăng ký đúng một lần?
- Order, URL mapping, DispatcherTypes có đúng?

SPRING SECURITY
- FilterChainProxy đang chứa những SecurityFilterChain nào?
- Request matcher nào được chọn, @Order ra sao?
- Chain được chọn có mấy entry của custom Filter?
- Placement so với SecurityContext, auth, anonymous, authorization?
- Có addFilterBefore và addFilterAfter cùng một instance?

RUNTIME
- Một hay nhiều HTTP requests?
- Một hay nhiều servlet dispatches (REQUEST/ASYNC/ERROR)?
- Một hay nhiều Filter instances?
- Filter.doFilter và doFilterInternal được gọi mấy lần?
- User hiện tại null, anonymous hay authentication đã xác minh?
~~~

Nếu chỉ đọc log `FilterChainProxy`, bạn có thể thấy filter trong security chain đúng **một lần** mà không thấy container auto-registration độc lập bên ngoài. Vì vậy đừng khẳng định “không duplicate” khi chưa kiểm tra Boot registrations.

### 11.2. Log Spring Security phù hợp

Trong môi trường test/dev:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Startup log thường hiển thị danh sách filter của `DefaultSecurityFilterChain`; TRACE của proxy có thể giúp xem chain/filter đã chạy. Filter list thực tế phụ thuộc Spring Security version/config, không dựa vào một danh sách copy từ tài liệu.

Không duy trì TRACE vô hạn ở production, không dump raw `Authorization`, `Cookie`, password hoặc toàn bộ claims của principal. Sử dụng correlation ID, metrics có giới hạn và redaction.

### 11.3. Phân biệt lỗi HTTP trước khi di chuyển filter

| Triệu chứng | Nguyên nhân đáng kiểm tra | Không nên làm |
|---|---|---|
| API nhận 401 dù gửi token | Auth filter không nằm trong selected chain, token invalid, verify lỗi | Không tự tạo authenticated token từ raw header |
| API nhận 403 | Authorization denied hoặc CSRF, context chưa kịp set | Không tắt CSRF/authorization toàn hệ thống |
| Login URL trả 404 | URL login nằm ngoài chain matcher hoặc filter login chưa bật | Không chỉ tăng `@Order` tùy tiện |
| Custom filter không chạy | Sai chain, matcher, filter disabled, path sai | Không auto-register thêm container filter ngay |
| Custom filter chạy hai lần | Bean auto registration + addFilter*, hoặc hai entries trong chain | Không chỉ dùng OncePerRequestFilter để che |
| Trace filter thấy auth null | Chạy trước auth filter hoặc ngoài proxy | Không coi null là bằng chứng password sai |
| Lỗi chỉ ở error/async | Dispatcher types và once-per-dispatch policy | Không giả định mọi dispatch đều giống REQUEST |
| Controller không đọc được JSON | Custom filter đã tiêu thụ InputStream | Không tiếp tục đọc body thô không wrapper |
| Request A thấy principal B | Rò ThreadLocal hoặc static/currentUser field | Không dùng MODE_GLOBAL trong web multi-user |

### 11.4. Quan sát không được tiết lộ credential

Khi điều tra, có thể log **loại filter, lớp/tầng, requestId, method/path đã được kiểm soát, dispatcher type, thời điểm và kết quả**. Tránh log raw password, session cookie, API key, bearer token, request body chứa thông tin nhạy cảm. Trong security incident, log cũng là tài sản cần bảo vệ.

## 12. Bộ kiểm thử khuyến nghị

### 12.1. Unit test các quy tắc order

| Test | Kết quả cần chứng minh |
|---|---|
| `addFilterBefore` | Custom filter chạy trước anchor theo chain đã build |
| `addFilterAfter` | Custom filter chạy sau anchor theo chain đã build |
| `addFilterAt` cùng slot | Không dựa vào relative order không bảo đảm; filter mặc định không tự bị xóa |
| Chỉ có API chain | URL khác API không được mặc định coi là bảo vệ |
| API chain trước fallback | Request API chọn chain cụ thể |
| Fallback trước API | Test cảnh báo API matcher bị che |
| Custom filter lặp trong một chain | Detect được số lần gọi >1 |
| Filter nằm ở hai chain khác nhau | Request chỉ chạy selected chain |
| Filter ở container + security chain | Detect được hai điểm đăng ký/lần gọi |
| `OncePerRequestFilter` nested call | Phân biệt doFilter và doFilterInternal |
| ERROR/ASYNC dispatch | Behavior đúng với dispatcher mapping và overrides |

### 12.2. Spring Boot integration test với MockMvc

- `GET /api/orders` phải vào API chain, custom filter có mặt đúng một lần.
- `GET /home` phải vào fallback Web chain, không bị API-only filter xử lý.
- `GET /api/health` dù `permitAll` vẫn qua API chain.
- `POST /login` phải nằm trong chain tạo login filter và không 404.
- API request không có credential bị entry point/authorization từ chối đúng; token sai không tạo authenticated principal.
- `FilterRegistrationBean.setEnabled(false)` không làm filter biến mất khỏi Security chain.
- Với context và servlet filter registrations có thật, xác minh instance/custom filter không được gọi lần hai.
- Test CSRF ở write endpoints theo policy, không chẩn đoán mọi 403 là sai authority.
- Test account bị khóa, role đổi, session/token lifecycle và không rò context qua request/worker reuse.
- Test `DispatcherType.ERROR`/`ASYNC` và lần gọi doFilterInternal tương ứng.
- Test custom filter dừng chain đúng lúc trên failure và không double-commit response.

### 12.3. E2E qua embedded Tomcat hoặc container thật

MockMvc không phản ánh toàn bộ automatic Servlet registrations và reverse proxy. Test qua HTTP port thật để kiểm chứng:

- Spring Boot auto-registration, thứ tự của `DelegatingFilterProxy` và custom filters.
- URL context path/servlet path, forwarding headers, encoded URL/path matcher.
- Request có body lớn, CORS preflight, CSRF, error dispatch và async.
- Đồng thời nhiều users để phát hiện request context bị rò.
- Việc tắt container registration không làm mất logging/trace cần ở các URL ngoài security chain.

**Không coi code chạy đúng trên một request mock là đủ chứng minh an toàn production**. Phải dùng filter chain thực và attack/regression cases.

## 13. FAQ những hiểu nhầm quan trọng

**1. Spring Security có chạy mọi SecurityFilterChain khớp request không?**  
Không. `FilterChainProxy` chọn chain đầu tiên khớp, không cộng dồn filters.

**2. `@Order(1)` trên class Filter có bắt nó chạy đầu tiên trong Spring Security không?**  
Không. Container filter order và internal security filter order là hai tầng.

**3. Một bean Filter nằm trong hai SecurityFilterChain có bị gọi hai lần?**  
Không tự động. Chỉ chain được chọn mới chạy; xem có duplicate trong selected chain/container hay không.

**4. Tại sao `@Component` cộng `addFilterAfter` có thể gây duplicate?**  
Bởi Boot có thể tự đăng ký Filter bean ở container; đồng thời SecurityFilterChain cũng chứa nó.

**5. `addFilterAt` có thực sự thay thế filter cũ không?**  
Không tự động; cùng slot không bảo đảm thứ tự. Disable/filter config cũ một cách rõ ràng.

**6. `OncePerRequestFilter` có bảo đảm chỉ xử lý một lần cho cả HTTP request và mọi redispatch?**  
Không. Nó có marker và behavior theo dispatcher type; đăng ký trùng vẫn phải sửa.

**7. `FilterRegistrationBean.setEnabled(false)` có xóa filter khỏi Spring Security chain không?**  
Không. Nó kiểm soát container registration, không xóa entry đã thêm bằng `HttpSecurity`.

**8. Xác thực token ở container trước Spring Security luôn đúng không?**  
Không. Có thể thiếu context/protection, không nằm dưới lifecycle proxy và gây double verification. Chọn đúng security chain/provider.

**9. Vì sao thấy auth null trong filter dù token hợp lệ?**  
Có thể filter chạy trước mechanism xác thực hoặc ở container trước security chain; phải xem vị trí và selected chain.

**10. Dùng `permitAll` và `web.ignoring` có giống nhau không?**  
Không. `permitAll` vẫn đi qua security filters của chain; ignoring có thể bypass filters.

**11. Có thể log token để kiểm tra hai lần parse không?**  
Không nên. Log category, requestId và số lần gọi mà không lộ bí mật.

**12. Muốn một business operation chạy đúng một lần, có thể dựa vào OncePerRequestFilter không?**  
Không. Cần idempotency key/transaction/unique constraint và xử lý replay phù hợp ở domain.

## 14. Checklist triển khai

- [ ] Phân biệt **Servlet container order**, **SecurityFilterChain priority** và **filter order nội bộ**.
- [ ] Xác minh `DelegatingFilterProxy`/`springSecurityFilterChain` được container đăng ký đúng, không tạo proxy không cần thiết.
- [ ] Với nhiều chains, đặt matcher hẹp trước fallback và test `@Order` thực tế.
- [ ] Mọi endpoint quan trọng đều vào chain có authentication/authorization phù hợp.
- [ ] Phân biệt `securityMatcher` với `requestMatchers` và `permitAll` với `web.ignoring`.
- [ ] Custom filter có lý do tồn tại; ưu tiên filter/provider/handler chuẩn trước khi viết mới.
- [ ] Chọn `addFilterBefore/After` theo trạng thái context/protection/auth cần có; không để auth filter chạy sau authorization.
- [ ] Không dùng `addFilterAt` như một cách “replace” tự động.
- [ ] Nếu custom Filter bean chỉ dùng trong Spring Security, tắt auto-registration bằng `FilterRegistrationBean.setEnabled(false)` hoặc không tạo Filter bean độc lập.
- [ ] Không add cùng filter hai lần trong selected chain.
- [ ] Hiểu `OncePerRequestFilter` và kiểm thử cả `REQUEST`, `ASYNC`, `ERROR`.
- [ ] Không gắn authenticated principal từ dữ liệu chưa được verifier/provider kiểm tra.
- [ ] Không tắt CSRF/CORS/headers/firewall chỉ để che lỗi order.
- [ ] Đọc Spring Security DEBUG/TRACE đúng môi trường, xác minh filter list và container registrations.
- [ ] Không lộ password, bearer token, cookie, API key, raw body chứa credentials trong log.
- [ ] Có unit test, Boot MockMvc integration test và HTTP test thật cho double registration.
- [ ] Sau khi tắt container auto-registration, kiểm tra không làm mất behavior ở endpoint ngoài security chain.
- [ ] Dùng phiên bản Spring Boot/Spring Security được hỗ trợ, cập nhật vá bảo mật khi triển khai production.

**Ghi nhớ:** Custom filter phải được đặt **đúng một tầng, đúng chain và đúng vị trí**; `OncePerRequestFilter` không thay thế việc kiểm soát registration. Hiểu rõ thứ tự từ Servlet container đến `FilterChainProxy` rồi tới filters nội bộ sẽ giúp phân biệt một lỗi authentication thật với lỗi filter chạy sai thời điểm hoặc chạy hai lần.

### Tài liệu chính thức

- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `DelegatingFilterProxy`, `FilterChainProxy`, thứ tự events, custom filters và registration pitfalls.
- [Spring Security — HttpSecurity JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/builders/HttpSecurity.html): `addFilterBefore`, `addFilterAfter`, `addFilterAt` và cảnh báo nhiều filter ở cùng slot.
- [Spring Security — Java Configuration / Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `@Order`, `securityMatcher`/`requestMatchers`.
- [Spring Boot — Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html): auto-register Filter beans và `FilterRegistrationBean` để tắt registration.
- [Spring Framework — Servlet Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): `OncePerRequestFilter`, GenericFilterBean và Servlet Filter lifecycle.
- [Spring Framework — OncePerRequestFilter JavaDoc](https://docs.spring.io/spring-framework/docs/6.1.18/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): `doFilterInternal`, marker và dispatch behavior.
