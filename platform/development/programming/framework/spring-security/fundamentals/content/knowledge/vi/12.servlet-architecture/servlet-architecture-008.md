# Vị trí mở rộng bộ lọc và nguy cơ đăng ký cùng bộ lọc hai lần

## 1. Vấn đề: thêm một Filter nhưng ứng dụng có thể gọi nó ở hai nơi

Trong Spring Security Servlet, developer thường muốn thêm một Filter riêng để gắn correlation ID, kiểm tra tenant, kiểm chứng một credential đặc thù, ghi audit sự kiện hoặc áp chính sách bảo mật bổ sung.

Một cách tự nhiên là tạo Spring bean:

~~~java
@Component
public class TenantFilter extends OncePerRequestFilter {
    // Logic kiểm tra tenant ở đây.
}
~~~

rồi đưa filter này vào cấu hình Spring Security:

~~~java
http.addFilterBefore(tenantFilter, AuthorizationFilter.class);
~~~

Đây là hai **đoạn minh họa** chứ không phải file hoàn chỉnh. Chúng có thể tạo ra một lỗi tinh vi: **Spring Boot có thể tự đăng ký Spring bean kiểu Filter vào Servlet Container, đồng thời Spring Security lại thêm chính filter đó vào SecurityFilterChain**.

Hệ quả là một HTTP request có khả năng đi qua filter tại **hai vị trí khác nhau**, với thứ tự, phạm vi URL, dispatcher type và SecurityContext không giống nhau. Với Filter thuần, logic có thể thực thi hai lần. Với OncePerRequestFilter, cơ chế “already filtered” có thể làm doFilterInternal chỉ chạy một lần trong một số đường đi, nhưng **cấu hình đăng ký hai nơi vẫn sai** và tạo sự phụ thuộc nguy hiểm vào thứ tự thực thi.

Bài này tập trung giải thích **vị trí mở rộng bộ lọc và nguy cơ đăng ký cùng bộ lọc hai lần**, trong nhóm **Kiến trúc Servlet** của module **Spring Security - fundamentals**. Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Security 6.x và Jakarta Servlet API. Có một lab chạy được bằng Spring Boot, sử dụng hai profile để kiểm tra bằng HTTP thật:

- **safe:** Filter bean chỉ chạy bên trong Spring Security vì đăng ký Servlet Container bị tắt.
- **double:** Cố tình bỏ bước tắt đăng ký, cho thấy cùng bean Filter được container và Spring Security gọi.

**Mục tiêu cuối:** biết chọn vị trí filter theo nhiệm vụ, đăng ký ở đúng một cấp, kiểm chứng chain thực tế và không vô tình phá authentication, CSRF, authorization hoặc logging.

### Những điều cần nắm sau bài

1. Phân biệt Servlet Container FilterChain với FilterChainProxy/SecurityFilterChain.
2. Hiểu chính xác addFilterBefore, addFilterAfter và addFilterAt thuộc cấp nào.
3. Chọn anchor filter theo thời điểm SecurityContext được khôi phục, credential được kiểm chứng và authorization diễn ra.
4. Biết vì sao @Component Filter hoặc @Bean Filter có thể được Spring Boot tự động đăng ký vào Servlet Container.
5. Biết cách tránh đăng ký kép bằng cách tạo new Filter không phải bean, hoặc dùng FilterRegistrationBean.setEnabled(false) nếu cần dependency injection.
6. Hiểu giới hạn của OncePerRequestFilter khi phân tích việc bị đăng ký hai lần.
7. Chạy lab dùng cùng một filter bean với hai profile safe/double và đếm số lượt gọi thực tế trên từng request.
8. Dùng integration test có embedded Servlet Container để kiểm tra đường đi thật, thay vì chỉ nhìn MockMvc.
9. Phân biệt lỗi “hai lần” với ASYNC/ERROR dispatch, CORS preflight, browser request phụ và nhiều SecurityFilterChain.
10. Rà soát bảo mật: filter đặt trước authentication không thể tin principal, filter đặt sau authorization có thể không chạy, exception mapping phụ thuộc vị trí.

## 2. Hai cấp Filter độc lập trong ứng dụng Spring MVC

Một Servlet application thường nhận request qua Servlet Container (Tomcat/Jetty/Undertow tùy stack). Container tạo chuỗi Filter cấp Servlet, trong đó Spring Security có một cầu nối gọi là DelegatingFilterProxy.

~~~text
HTTP Client
    |
    v
Servlet Container
    |
    v
ContainerFilter A
    |
    v
DelegatingFilterProxy
    |  target bean: springSecurityFilterChain
    v
FilterChainProxy              (Spring Security Filter)
    |
    +-- SecurityFilterChain đầu tiên khớp request
    |        |
    |        +-- SecurityContextHolderFilter
    |        +-- HeaderWriterFilter / CsrfFilter ...
    |        +-- Authentication filters ...
    |        +-- AnonymousAuthenticationFilter ...
    |        +-- ExceptionTranslationFilter ...
    |        +-- AuthorizationFilter ...
    |
    v
ContainerFilter B
    |
    v
DispatcherServlet
    |
    v
@RestController
~~~

Sơ đồ có tính **minh họa**, không phải danh sách filter cố định trong mọi phiên bản/cấu hình. ContainerFilter A/B có thể xuất hiện trước hoặc sau Spring Security bridge tùy registration order. Security filters cụ thể phụ thuộc HttpSecurity DSL, session policy, login mechanism và những bean được chọn.

### 2.1. Container Filter

Filter cấp Servlet Container được đăng ký bằng Servlet API, web.xml, @WebFilter cùng cơ chế scan phù hợp, hoặc bằng **FilterRegistrationBean** của Spring Boot. Nó tham gia vào chuỗi Filter do Servlet Container quản lý, độc lập với việc một URL có khớp SecurityFilterChain nào hay không.

Các thuộc tính quan trọng:

- **URL patterns / servlet names** của registration.
- **Dispatcher types** như REQUEST, ASYNC, ERROR.
- **Container registration order**.
- Servlet lifecycle init, doFilter, destroy.
- Khả năng chặn request trước khi vào Spring Security hoặc Controller.

Container Filter có thể hoạt động mà không cần biết Authentication hay SecurityContext. Nhưng nếu code của nó đọc SecurityContextHolder trước khi Spring Security khôi phục context, nó có thể thấy anonymous hoặc null.

### 2.2. DelegatingFilterProxy

DelegatingFilterProxy là một Servlet Filter của Spring Framework. Khi Container gọi nó, proxy tìm bean Filter có tên đích, thường là **springSecurityFilterChain**, rồi chuyển doFilter vào bean đó.

Bean target thường là **FilterChainProxy** của Spring Security. Vì thế Servlet Container không cần đăng ký từng CsrfFilter, AuthorizationFilter hoặc BasicAuthenticationFilter. Container chỉ gọi bridge, còn FilterChainProxy quản lý security filters.

**Không tự đăng ký thêm DelegatingFilterProxy chỉ vì đã tạo SecurityFilterChain bean.** Trong Spring Boot Servlet application thông thường với spring-boot-starter-security, bridge đã được auto-configure.

### 2.3. FilterChainProxy và SecurityFilterChain

FilterChainProxy chứa một hoặc nhiều SecurityFilterChain. Mỗi SecurityFilterChain có RequestMatcher và danh sách Filter. Trong cơ chế thông thường, **chain đầu tiên khớp request được chọn**; không cộng dồn toàn bộ chain khớp.

Vì vậy, một custom filter được thêm vào chain /api/** sẽ không tự xuất hiện ở chain dành cho /admin/** hoặc fallback. Nếu cần trên nhiều chains, phải xác định rõ phạm vi và đăng ký đúng vào từng chain liên quan.

### 2.4. Bảng so sánh hai cấp

| Khía cạnh | Servlet Container Filter | Spring Security chain filter |
| --- | --- | --- |
| Nơi đăng ký | web.xml, ServletContext, FilterRegistrationBean, auto-register Filter bean | HttpSecurity hoặc SecurityFilterChain |
| Ai gọi? | Servlet Container | FilterChainProxy |
| Thứ tự | Container filter registration order | Spring Security filter ordering |
| Phạm vi URL | URL/servlet mapping và dispatcher types | SecurityFilterChain RequestMatcher |
| SecurityContext | Có thể chạy trước khi context được tạo/khôi phục | Có thể đặt sau bước context/authentication theo nhu cầu |
| Cách thêm thường dùng | FilterRegistrationBean | addFilterBefore/addFilterAfter/addFilterAt |
| Nguy cơ đăng ký trùng | Cùng bean cũng nằm trong SecurityFilterChain | Cùng bean còn được Boot auto-register |
| Ví dụ phù hợp | Tracing không phụ thuộc danh tính, servlet diagnostics | Authentication, authorization, tenant check phụ thuộc Authentication |

## 3. Ba API mở rộng trong HttpSecurity

Spring Security cung cấp các phương thức để đưa custom filter vào vị trí có chủ đích của SecurityFilterChain:

~~~java
http.addFilterBefore(customFilter, ExistingFilter.class);
http.addFilterAfter(customFilter, ExistingFilter.class);
http.addFilterAt(customFilter, ExistingFilter.class);
~~~

Đây là **ba lựa chọn thay thế để minh họa API**, không phải lời khuyên gọi cả ba cho cùng một filter. ExistingFilter phải là lớp filter có vị trí đã được Spring Security nhận biết; class giả định trong snippet không phải class thật.

### 3.1. addFilterBefore

Đặt custom Filter **trước vị trí thứ tự** của anchor filter trong SecurityFilterChain.

~~~java
http.addFilterBefore(
    tenantAuthorizationFilter,
    AuthorizationFilter.class
);
~~~

Với một custom tenant/ownership check cần Authentication đã xác minh và cần có ExceptionTranslationFilter phía trước để chuyển AccessDeniedException thành response phù hợp, vị trí trước AuthorizationFilter **có thể là hợp lý** trong cấu hình chuẩn. Tuy nhiên phải kiểm tra danh sách filters thực tế của chain.

Không suy ra addFilterBefore(..., AuthorizationFilter.class) luôn có cùng hành vi với mọi custom DSL hoặc trong một chain đã loại bỏ AuthorizationFilter. Nếu cần phụ thuộc cụ thể vào một filter có mặt, phải xác minh chain đã được xây đúng.

### 3.2. addFilterAfter

Đặt filter **sau vị trí** của anchor filter:

~~~java
http.addFilterAfter(
    customObservationFilter,
    BasicAuthenticationFilter.class
);
~~~

Đây chỉ là snippet minh họa vị trí. Nếu BasicAuthenticationFilter nhận Basic credential sai và **chặn request mà không gọi tiếp chain**, filter đặt sau nó sẽ **không chạy** trên request thất bại. Không chọn vị trí “sau auth” cho audit thất bại nếu bạn thực sự cần ghi lại cả những request bị auth filter từ chối.

Một filter nằm sau BasicAuthenticationFilter cũng không bảo đảm mọi loại authentication đều đã hoàn thành: một chain có thể dùng BearerTokenAuthenticationFilter, form login hoặc cơ chế khác.

### 3.3. addFilterAt

Đặt custom filter **tại vị trí thứ tự của một filter được biết đến**:

~~~java
http.addFilterAt(
    customAuthenticationFilter,
    UsernamePasswordAuthenticationFilter.class
);
~~~

**Đây không đồng nghĩa một thao tác “replace object” an toàn trong mọi tình huống.** Tài liệu tham khảo kiến trúc đôi khi dùng ngôn ngữ “replace” để mô tả mục đích, nhưng Javadoc HttpSecurity giải thích rằng các filter ở cùng vị trí không mặc nhiên ghi đè lẫn nhau; thứ tự giữa chúng có thể không xác định. Một số cấu hình hoặc phiên bản còn phát hiện xung đột/đăng ký trùng và từ chối xây chain.

**Quy tắc thực hành:** nếu chủ ý thay cơ chế cũ, hãy **không bật DSL tạo filter cũ** (hoặc disable cơ chế đó một cách phù hợp) và cấu hình custom filter cùng cơ chế authentication/exception/session cần thiết. Đừng dựa vào addFilterAt để “đè” một BasicAuthenticationFilter/UsernamePasswordAuthenticationFilter đã được đăng ký.

### 3.4. addFilter khác với các API trên

HttpSecurity.addFilter(...) thường chỉ chấp nhận một filter thuộc class/subclass có vị trí đã được framework nhận biết. Với custom filter hoàn toàn mới, các phương thức addFilterBefore/After/At thường dễ kiểm soát hơn.

Nếu truyền một filter không có registered order qua addFilter, framework có thể ném lỗi; đừng giải quyết bằng cách đặt filter vào vị trí không có ý nghĩa bảo mật.

### 3.5. Không đổi thứ tự bằng @Order trên Filter bean rồi mong nó ảnh hưởng bên trong SecurityFilterChain

**@Order/Ordered trên bean Filter** hoặc FilterRegistrationBean thường liên quan thứ tự đăng ký container. Bên trong SecurityFilterChain, Spring Security dùng bộ thứ tự và các API của HttpSecurity.

Nếu yêu cầu là “chạy trước AuthorizationFilter nhưng sau Authentication”, hãy chỉnh **HttpSecurity**, không chỉnh **FilterRegistrationBean.order**.

## 4. Chọn vị trí theo sự kiện bảo mật cần xảy ra trước

Thay vì hỏi “đặt trước class X hay sau class Y” trước tiên, hãy hỏi **filter của tôi cần tin điều gì từ request?**

Một chuỗi điển hình có các giai đoạn:

~~~text
[Load SecurityContext]
          |
[Exploit protection: headers, CSRF, CORS ...]
          |
[Authentication: xác minh credentials]
          |
[Anonymous fallback nếu chưa login]
          |
[Translate security exceptions]
          |
[Authorization]
          |
[Servlet / Controller]
~~~

Cấu hình thực có nhiều filter khác. Thứ tự phụ thuộc version và authentication mechanism. Không lấy sơ đồ này làm một danh sách đầy đủ có thể hard-code.

### 4.1. Bảng chọn vị trí tham khảo

| Nhu cầu | Phụ thuộc vào | Cách tiếp cận |
| --- | --- | --- |
| Gắn request ID không cần Authentication | Servlet request | Container filter hoặc filter trước security, nhưng bảo vệ dữ liệu nhạy cảm |
| Xử lý một authentication mechanism riêng | Credential format, AuthenticationManager, context | Vị trí thuộc giai đoạn authentication; cân nhắc DSL/provider có sẵn |
| Kiểm tra tenant người dùng hiện tại | Principal đã được xác minh | Đặt sau authentication và trước authorization theo chain thực |
| Chặn resource owner không đúng | Authentication + resource identifier đáng tin | Ưu tiên authorization/service method; nếu filter thì cần exception handling đúng |
| Ghi metrics mọi response, kể cả 401 | Bao quanh toàn bộ pipeline | Filter ngoài Security hoặc vị trí được chứng minh bao quát các nhánh; không log token/body |
| Thêm security header | Response | Ưu tiên headers DSL, tránh custom filter không cần thiết |
| Kiểm tra CSRF | Session/cookie/form state | Dùng csrf DSL/CsrfFilter chuẩn |
| Phân quyền endpoint | Granted authorities | Dùng authorizeHttpRequests, method security trước khi tự viết filter |
| Phân tích thời gian xử lý | Pre/post invocation | Xem vị trí và việc short-circuit ở filters phía trước |
| Làm việc khi ERROR/ASYNC dispatch | Dispatcher type/context propagation | Cấu hình rõ registration và kiểm thử từng loại dispatch |

**Không có “một vị trí đúng cho mọi custom filter”.** Vị trí phụ thuộc vào dữ liệu mà filter cần dùng, thời điểm request có Authentication và việc filter cần bao quanh các lỗi phát sinh ở phần nào.

### 4.2. Khi cần Authentication, đừng chạy quá sớm

Ví dụ code đọc SecurityContextHolder:

~~~java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Nếu filter nằm trước SecurityContextHolderFilter hoặc trước authentication mechanism có thể xác minh credential, current có thể null hoặc là authentication cũ/chưa được xác minh. Một request có Authorization header không đồng nghĩa header đã được kiểm chứng.

Nếu mục tiêu là kiểm tra quyền người dùng, không tự parse JWT, Basic header hoặc username do client gửi rồi cấp quyền. Hãy dùng Authentication đã được provider/token verifier xác minh.

### 4.3. ExceptionTranslationFilter ảnh hưởng tới cách nhận 401/403

ExceptionTranslationFilter thường chuyển những AuthenticationException/AccessDeniedException thích hợp từ **downstream security chain** thành hành vi entry point/access denied handler.

Nếu một custom filter ném AccessDeniedException **trước** ExceptionTranslationFilter, exception đó có thể không được handler chuẩn của filter này bắt vì nó xuất phát **upstream**. Có thể nhìn thấy lỗi 500 hoặc error dispatch tùy cấu hình khác.

Do đó cần xác định filter kiểm tra authorization nằm ở đâu so với ExceptionTranslationFilter và AuthorizationFilter. Với business authorization phức tạp, phương án authorization manager hoặc method security thường rõ hơn một Servlet filter tự viết.

### 4.4. Authentication filter không chỉ cần vị trí

Một filter thực hiện xác thực thực sự có thể phải:

- Parse credential an toàn.
- Chuyển credential tới AuthenticationManager/provider đáng tin.
- Tạo và đặt SecurityContext sau khi xác thực thành công.
- Thực hiện session strategy nếu kiến trúc session-based yêu cầu.
- Lưu context nếu Spring Security 6 explicit-save và cần persistence.
- Xử lý authentication failures và security exceptions.
- Không log raw password, token, cookie hoặc nguyên Authentication.
- Giới hạn số lần thử và phân biệt user enumeration/timing risks.

Vì vậy không nên thay built-in UsernamePasswordAuthenticationFilter chỉ để đổi một tên field trong form nếu có DSL phù hợp.

### 4.5. Quan sát thất bại khác với chặn request

Một audit filter đặt trước BasicAuthenticationFilter có thể thấy request đến, nhưng **không tự biết kết quả xác thực** nếu thiếu integration với event/handler. Đặt sau BasicAuthenticationFilter có thể chỉ thấy các request thành công. Với authentication audit, dùng AuthenticationSuccessEvent/AuthenticationFailureEvent, handlers hoặc observability integration phù hợp thường chính xác hơn việc đoán từ vị trí filter.

## 5. Nguy cơ đăng ký cùng Filter hai lần bắt đầu ở đâu?

Trong Spring Boot Servlet application, một Spring bean implements jakarta.servlet.Filter được Boot xem xét **tự động đăng ký với Servlet Container**.

Ví dụ:

~~~java
@Bean
TenantFilter tenantFilter(TenantService service) {
    return new TenantFilter(service);
}
~~~

hoặc:

~~~java
@Component
public class TenantFilter extends OncePerRequestFilter {
    // ...
}
~~~

Khi sau đó dùng cùng instance trong HttpSecurity:

~~~java
@Bean
SecurityFilterChain security(
        HttpSecurity http, TenantFilter tenantFilter) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .addFilterBefore(tenantFilter, AuthorizationFilter.class)
        .build();
}
~~~

Ba đoạn này minh họa các cách khai báo và sử dụng, không phải một project đầy đủ. **Nếu Filter là Spring bean mà không có registration override**, Boot có thể đưa bean vào **Servlet Container FilterChain**; HttpSecurity đưa bean vào **SecurityFilterChain**.

### 5.1. Đường đi của một request trong cấu hình lỗi

~~~text
HTTP GET /private
      |
      v
Servlet Container FilterChain
      |
      v
DelegatingFilterProxy
      |
      v
FilterChainProxy
      |
      +-- TenantFilter [doFilter lần 1: do HttpSecurity thêm]
      |
      v
Container FilterChain tiếp tục
      |
      +-- TenantFilter [doFilter lần 2: Boot auto-register bean]
      |
      v
DispatcherServlet
      |
      v
Controller
~~~

Đây là **một thứ tự minh họa**, không bảo đảm container lúc nào cũng gọi theo đúng vị trí trong hình. Với registration order khác, lượt container có thể diễn ra trước lượt security. Điều bất biến trong tình huống này là **có hai đường đăng ký**, nên một HTTP request có thể chạm cùng filter hai lần.

Nếu Filter chứa side effects như tăng retry counter, ghi audit, gửi message, tự cập nhật session hoặc thay response, việc chạy hai lần có thể tạo lỗi nghiêm trọng.

### 5.2. Ảnh hưởng bảo mật của chạy hai lần

- **Sai thời điểm kiểm tra quyền:** lượt container chạy trước khi Authentication được thiết lập, thấy null/anonymous.
- **Nhân đôi rate-limit counter:** một lần login được đếm hai lần hoặc làm user bị throttle sớm.
- **Nhân đôi side effect:** ghi audit/tracing/billing hoặc event bus hai lần.
- **Cookie/header bị ghi đè:** filter thứ hai thay kết quả của filter thứ nhất.
- **Response commit bất ngờ:** custom filter phát 401/403 ở cấp container trước khi security entry point xử lý.
- **Bypass khi có nhiều chains:** filter container vẫn chạy trên request ngoài phạm vi securityMatcher, nhưng filter security không chạy.
- **Báo cáo sai về request:** metric request count/latency bị nhân đôi hoặc tính hai giai đoạn khác nhau.
- **Dữ liệu nhạy cảm vào log:** filter container vô tình ghi Authorization/Cookie khi chưa có guard của Spring Security.

Một chương trình có thể vẫn “chạy được”, nhưng quyền và telemetry không đáng tin. Vì vậy phải sửa ownership, không chỉ ẩn lỗi từ logs.

## 6. Cách tránh: hai phương án hợp lệ

### 6.1. Phương án A — Chỉ tạo instance trong HttpSecurity

Nếu filter ít phụ thuộc các Spring beans, tạo một instance trực tiếp trong SecurityFilterChain:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http)
        throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .addFilterBefore(
            new TenantFilter(),
            AuthorizationFilter.class)
        .build();
}
~~~

Đây là snippet trong một class @Configuration; TenantFilter do ứng dụng tự định nghĩa, không phải file standalone.

Vì instance new TenantFilter() **không được khai báo @Bean/@Component** và không được đăng ký Servlet Filter ở nơi khác, Spring Boot không tự auto-register chính instance này vào container.

Ưu điểm: ít cấu hình, không có nguy cơ auto-registration qua Spring bean. Nhược điểm: nếu filter cần nhiều dependency, bạn phải truyền chúng vào constructor hoặc chọn phương án B.

### 6.2. Phương án B — Giữ Filter là Spring bean, nhưng vô hiệu hóa đăng ký container

Nếu filter cần dependency injection, tạo bean rồi khai báo FilterRegistrationBean với enabled=false:

~~~java
@Bean
TenantFilter tenantFilter(TenantService service) {
    return new TenantFilter(service);
}

@Bean
FilterRegistrationBean<TenantFilter> disableTenantFilterRegistration(
        TenantFilter filter) {

    FilterRegistrationBean<TenantFilter> registration =
        new FilterRegistrationBean<>(filter);

    registration.setEnabled(false);
    return registration;
}

@Bean
SecurityFilterChain security(HttpSecurity http,
        TenantFilter filter) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .addFilterBefore(filter, AuthorizationFilter.class)
        .build();
}
~~~

Đây là một **snippet cấu hình** có các class/imports ứng dụng đã chuẩn bị, không phải toàn bộ file Java. FilterRegistrationBean **disabled** không xóa bean khỏi ApplicationContext; nó chỉ yêu cầu Boot **không đăng ký bean Filter này với Servlet Container**.

Filter vẫn hoạt động trong SecurityFilterChain bởi HttpSecurity.addFilterBefore. Điều này phân tách rõ trách nhiệm:

- **Spring bean:** quản lý dependency/lifecycle.
- **FilterRegistrationBean disabled:** ngăn đăng ký Servlet Container.
- **HttpSecurity:** đăng ký đúng một lần tại giai đoạn security mong muốn.

### 6.3. Khi thật sự muốn Filter ở cấp Servlet Container

Đối với một filter tracing/diagnostics độc lập với Spring Security, có thể cố ý đăng ký nó bằng FilterRegistrationBean ở container, với URL patterns, order và dispatcher types rõ ràng. Khi đó **không đưa cùng instance vào HttpSecurity**.

Đây cũng là một thiết kế hợp lệ: không phải mọi Servlet Filter đều cần nằm trong FilterChainProxy.

### 6.4. Bảng quyết định

| Trường hợp | Cách đăng ký |
| --- | --- |
| Custom filter chỉ làm authentication/authorization trong Spring Security | HttpSecurity.addFilterBefore/After, không container registration |
| Custom filter cần Spring DI và chỉ chạy trong security chain | @Bean + FilterRegistrationBean.setEnabled(false) + HttpSecurity |
| Filter tracing cần chạy bên ngoài security chain | FilterRegistrationBean có enabled=true, không thêm vào HttpSecurity |
| Filter chuẩn Basic/Csrf/Cors/Headers | DSL tương ứng của Spring Security |
| Cần filter cho nhiều SecurityFilterChain | Cấu hình theo từng chain có matcher phù hợp; cân nhắc chia state và filter instances |
| Muốn kiểm tra quyền trên từng entity/record | AuthorizationManager/method security/service thay vì filter tổng quát khi hợp lý |

## 7. OncePerRequestFilter có giải quyết việc đăng ký hai lần không?

**Không.** OncePerRequestFilter giúp tránh thực thi trùng logic doFilterInternal trong một số tình huống, nhưng nó không phải công cụ sửa registration sai.

Để hiểu, xem ý tưởng marker request attribute:

~~~text
Filter entry #1
   |
   +-- Chưa có already-filtered marker
   +-- Đặt marker trên request
   +-- Gọi doFilterInternal
   |        |
   |        +-- chain.doFilter tới downstream
   |                 |
   |                 +-- Filter entry #2
   |                       |
   |                       +-- Thấy marker: bỏ qua doFilterInternal
   |
   +-- Cuối entry #1, dọn marker
~~~

Trong một đường đi lồng nhau như trên, cùng instance OncePerRequestFilter có thể chỉ chạy **doFilterInternal một lần** dù có hai registration. Developer nhìn log đặt bên trong doFilterInternal rồi tưởng filter chỉ được đăng ký một lần.

### 7.1. Vì sao “once” không phải bảo đảm tuyệt đối một lần cho mọi tình huống?

- Marker dùng request attribute; hành vi có thể phụ thuộc tên filter và instance.
- Với hai instance khác nhau hoặc filter names khác nhau, marker có thể khác.
- ERROR/ASYNC dispatch có lifecycle và cách skip riêng.
- Một request có thể trải qua dispatch khác nhau thay vì một lần REQUEST.
- Các filter đặt ở hai cấp có vị trí khác nhau dù logic bên trong có thể bị skip.
- Nếu một filter trước đó chặn request, một trong hai registration có thể không được chạm tới.

Do đó, **không dùng mỗi số dòng log bên trong doFilterInternal để chứng minh không có duplicate registration**.

### 7.2. Dùng Filter thuần để chứng minh chính xác trong lab

Phần thực hành sẽ dùng một **plain jakarta.servlet.Filter**, không extends OncePerRequestFilter, để đếm số lần doFilter được gọi. Điều này giúp thấy rõ **hai registration → hai invocations** trong cấu hình minh họa.

Trong sản phẩm thật, filter có thể extends OncePerRequestFilter để tiện xử lý Servlet API và async/error semantics, nhưng vẫn phải có một đường đăng ký được xác định rõ.

## 8. Lab: hai profile safe và double, cùng một filter bean

Ta xây một ứng dụng Spring Boot Servlet duy nhất với:

1. **CountingProbeFilter:** plain Filter và là Spring bean; nó tăng một request attribute tại mỗi lần doFilter.
2. **SecurityFilterChain:** luôn thêm bean này **trước AuthorizationFilter**.
3. **Profile safe:** có FilterRegistrationBean<CountingProbeFilter> với setEnabled(false), nên chỉ có registration ở Spring Security.
4. **Profile double:** không có disabled registration, Boot có thể auto-register Filter bean ở Servlet Container; cộng với HttpSecurity tạo ra hai đường gọi.
5. **ContainerMarkerFilter:** filter container riêng, không tái sử dụng bean probe, dùng header để minh họa cấp container.
6. **GET /inspect:** trả số lần CountingProbeFilter được gọi trên request.
7. **/private, /admin:** kiểm chứng authentication và authorization vẫn đúng.

**Profile double cố ý sai chỉ để học. Không sử dụng ở production.**

### 8.1. Tạo project

Dùng Spring Initializr tạo project Java 17+, Spring Boot 3.x, Gradle Groovy DSL, Gradle Wrapper. Chọn Spring Web, Spring Security, Spring Boot Starter Test.

Trong phần dependencies của build.gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là **phần dependencies của project đã có Spring Boot plugin, Java toolchain và dependency management**, không phải một file build.gradle độc lập.

### 8.2. application.properties

Tạo file **src/main/resources/application.properties**:

~~~properties
# Mặc định chạy phương án đã sửa đúng.
spring.profiles.default=safe
~~~

Nếu không chỉ định profile active, Spring chọn profile safe. Khi chạy với **--spring.profiles.active=double**, default profile không còn active và bean disabled registration được loại bỏ.

### 8.3. File Java đầy đủ

Tạo file **src/main/java/com/example/filterplacement/FilterPlacementApplication.java**:

~~~java
package com.example.filterplacement;

import java.io.IOException;
import java.util.Map;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.core.Ordered;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FilterPlacementApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterPlacementApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("local-learn-only"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("local-admin-only"))
                .roles("ADMIN")
                .build()
        );
    }

    // Bean này có thể bị Boot tự đăng ký cấp Servlet Container.
    @Bean
    CountingProbeFilter countingProbeFilter() {
        return new CountingProbeFilter();
    }

    // Profile an toàn: chặn auto registration ở cấp container.
    @Bean
    @Profile("safe")
    FilterRegistrationBean<CountingProbeFilter> disableContainerProbe(
            CountingProbeFilter filter) {

        FilterRegistrationBean<CountingProbeFilter> registration =
            new FilterRegistrationBean<>(filter);
        registration.setEnabled(false);
        return registration;
    }

    // Filter thật sự chỉ dành cho Servlet Container.
    @Bean
    FilterRegistrationBean<ContainerMarkerFilter> containerMarker() {

        FilterRegistrationBean<ContainerMarkerFilter> registration =
            new FilterRegistrationBean<>(
                new ContainerMarkerFilter());

        registration.setName("labContainerMarker");
        registration.addUrlPatterns("/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return registration;
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, CountingProbeFilter filter)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/inspect", "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/private")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .addFilterBefore(filter, AuthorizationFilter.class)
            .build();
    }
}

// Không extends OncePerRequestFilter để đếm mọi invocation.
final class CountingProbeFilter implements Filter {

    static final String KEY =
        CountingProbeFilter.class.getName() + ".count";

    @Override
    public void doFilter(ServletRequest request,
            ServletResponse response, FilterChain chain)
            throws IOException, ServletException {

        Integer previous = (Integer) request.getAttribute(KEY);
        int current = previous == null ? 1 : previous + 1;

        request.setAttribute(KEY, current);
        chain.doFilter(request, response);
    }
}

// Class này không được khai báo @Bean riêng;
// FilterRegistrationBean bên trên sở hữu container registration.
final class ContainerMarkerFilter implements Filter {

    @Override
    public void doFilter(ServletRequest request,
            ServletResponse response, FilterChain chain)
            throws IOException, ServletException {

        ((HttpServletResponse) response)
            .setHeader("X-Lab-Container", "hit");
        chain.doFilter(request, response);
    }
}

@RestController
class LabController {

    @GetMapping("/inspect")
    Map<String, Integer> inspect(HttpServletRequest request) {
        Object number = request.getAttribute(
            CountingProbeFilter.KEY);

        int calls = number instanceof Integer value ? value : 0;
        return Map.of("filterInvocations", calls);
    }

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/private")
    String privateEndpoint(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

Đây là **một file Java hoàn chỉnh trong Spring Boot project đã tạo**. Public class trùng tên file; CountingProbeFilter, ContainerMarkerFilter và LabController là các class cùng package. Java 17 hỗ trợ pattern matching cho instanceof; Spring Boot 3 dùng jakarta.servlet.

### 8.4. Vì sao lab dùng request attribute thay vì AtomicInteger toàn cục?

Counter được lưu bằng **request.setAttribute** để đếm số lần gọi filter **trong một HTTP request**. Nếu dùng biến static hoặc instance field AtomicInteger trên Filter bean, nhiều request đồng thời sẽ tăng cùng counter, làm kết quả khó diễn giải.

Filter là singleton bean có thể phục vụ nhiều thread; không lưu username, Authentication hoặc request-specific data trong instance fields. Request attribute phù hợp cho probe tạm thời của lab và không tự trở thành session attribute.

### 8.5. Giải thích các profile

**Safe:**

- CountingProbeFilter là Spring bean.
- FilterRegistrationBean disabled gắn với đúng CountingProbeFilter instance.
- Spring Boot không thêm instance này vào Servlet Container FilterChain.
- HttpSecurity.addFilterBefore(filter, AuthorizationFilter.class) đưa nó vào security chain.
- GET /inspect có thể thấy filterInvocations=1.

**Double (cố tình lỗi):**

- CountingProbeFilter vẫn là Spring bean.
- Không có FilterRegistrationBean disabled.
- Spring Boot có thể tự đăng ký bean Filter vào Servlet Container.
- HttpSecurity vẫn thêm cùng bean vào SecurityFilterChain.
- GET /inspect có thể thấy filterInvocations=2 trong cấu hình embedded Servlet thông thường.

**ContainerMarkerFilter** luôn đi qua container registration và thêm header X-Lab-Container=hit. Nó là một instance khác, không phải CountingProbeFilter, giúp thấy cấp container vẫn hoạt động ở cả hai profile.

### 8.6. Tại sao chọn anchor AuthorizationFilter?

Trong bài, filter chỉ đếm lượt gọi để quan sát. Đặt nó ngay trước AuthorizationFilter làm cho nó chạy trong security chain trên cả request permitAll và request có xác thực, sau phần lớn authentication mechanisms ở cấu hình này.

Với filter nghiệp vụ thực sự kiểm tra quyền, cần xác định vị trí tương đối với ExceptionTranslationFilter và authentication mechanism. Đừng copy anchor chỉ vì ví dụ dùng nó; mỗi nhu cầu có một ranh giới tin cậy riêng.

### 8.7. Dự đoán thứ tự và ngoại lệ

Ở profile double, vị trí auto-registration của Filter bean tại container có thể thay đổi nếu hệ thống có filter order/registration tùy chỉnh. Nhưng với GET /inspect thông thường đi qua cả hai và Controller nhận request, kết quả sẽ cho biết bao nhiêu lần doFilter được gọi.

Nếu một filter bảo mật **chặn sớm** request, lượt container ở phía sau security bridge có thể chưa chạy; vì vậy không khẳng định mọi response 401 sẽ luôn mang counter bằng hai. Dùng endpoint permitAll để xác định duplicate registration trước.

## 9. Chạy lab và quan sát số lần filter chạy

### 9.1. Profile safe: chỉ một invocation

Chạy ở thư mục project có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

PowerShell: **.\gradlew.bat bootRun**. Theo application.properties, khi không có active profile, default profile safe được dùng.

Gọi:

~~~bash
curl -i http://localhost:8080/inspect
curl -i http://localhost:8080/public
~~~

Kết quả chính dự kiến cho /inspect:

~~~http
HTTP/1.1 200 OK
X-Lab-Container: hit
Content-Type: application/json

{"filterInvocations":1}
~~~

Header thực tế có thể bổ sung Date, security headers và các header khác. Body là kết quả dự kiến của một GET /inspect khi sử dụng safe profile; không phải output đã đo tại đây.

### 9.2. Profile double: cố tình đăng ký hai lần

Dừng app trước khi đổi profile, sau đó chạy:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=double'
~~~

PowerShell: **.\gradlew.bat bootRun --args='--spring.profiles.active=double'**. Khi active profile double, bean disabled registration (chỉ thuộc safe) không được tạo.

Gọi:

~~~bash
curl -i http://localhost:8080/inspect
~~~

Response kỳ vọng:

~~~http
HTTP/1.1 200 OK
X-Lab-Container: hit
Content-Type: application/json

{"filterInvocations":2}
~~~

Nếu kết quả khác, kiểm tra **Servlet Container filter registration** và security chain; đừng tự sửa code Controller để “ép” counter bằng hai. Số invocation phụ thuộc đúng việc Boot auto-register bean và request có đi qua cả hai vị trí hay không.

**Profile double chỉ dùng trong môi trường lab cô lập. Không bật ở production.**

### 9.3. Kiểm tra authentication và authorization không đổi

Ở một trong hai profile, dùng:

~~~bash
curl -i http://localhost:8080/private
curl -i -u learner http://localhost:8080/private
curl -i -u learner http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
~~~

Curl hỏi password nếu chỉ đưa username với -u; dùng password demo trong source. Trong Windows PowerShell có thể cần **curl.exe** thay vì curl alias.

| Request | Status kỳ vọng | Ý nghĩa |
| --- | --- | --- |
| GET /inspect anonymous | 200 | Probe được phép cho thí nghiệm |
| GET /public anonymous | 200 | permitAll vẫn đi qua chain |
| GET /private anonymous | 401 | Chưa có Authentication |
| GET /private learner, password demo đúng | 200 | Authenticated |
| GET /admin learner, password demo đúng | 403 | Thiếu ROLE_ADMIN |
| GET /admin admin, password demo đúng | 200 | Có ROLE_ADMIN |

HTTP Basic dùng Base64 chứ không mã hóa an toàn; phải dùng HTTPS/TLS khi truyền qua mạng. Password demo chỉ dùng trên localhost cô lập, không dùng lại ở bất kỳ account thật nào.

### 9.4. Quan sát header không đồng nghĩa chứng minh an toàn

X-Lab-Container chỉ cho thấy ContainerMarkerFilter đã chạy. Nó **không chứng minh** CountingProbeFilter chỉ chạy một lần. Counter request attribute giúp kiểm tra khía cạnh đó trong lab.

Ngược lại, ở hệ thống có proxy hay container khác, các header có thể bị xóa/thêm bởi layer bên ngoài. Dùng test nội bộ đã kiểm soát để kết luận về registration.

## 10. Integration test qua embedded Servlet Container

Vì vấn đề đang nghiên cứu là **filter registration ở Servlet Container**, kiểm thử chỉ bằng MockMvc có thể chưa đủ: MockMvc thường kiểm thử Spring MVC/Security chain theo cấu hình nhưng không tái hiện toàn bộ auto-registration của embedded server.

Để chứng minh đường container, dùng:

- **@SpringBootTest(webEnvironment = RANDOM_PORT)** để mở embedded Tomcat/Servlet Container trên cổng ngẫu nhiên.
- **TestRestTemplate** gửi HTTP thật.
- Hai test classes với **@ActiveProfiles("safe")** và **@ActiveProfiles("double")**.
- So sánh cùng endpoint /inspect và header container.

### 10.1. Test cho profile safe

Tạo file **src/test/java/com/example/filterplacement/SafeRegistrationTest.java**:

~~~java
package com.example.filterplacement;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("safe")
class SafeRegistrationTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void probeIsRegisteredOnlyWithinSecurityFilterChain() {
        ResponseEntity<Map> response =
            rest.getForEntity("/inspect", Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("hit", response.getHeaders()
            .getFirst("X-Lab-Container"));

        Number calls = (Number) response.getBody()
            .get("filterInvocations");
        assertEquals(1, calls.intValue());
    }

    @Test
    void authenticationAndAuthorizationStillWork() {
        assertEquals(HttpStatus.UNAUTHORIZED,
            rest.getForEntity("/private", String.class)
                .getStatusCode());

        ResponseEntity<String> authenticated =
            rest.withBasicAuth("learner", "local-learn-only")
                .getForEntity("/private", String.class);

        assertEquals(HttpStatus.OK,
            authenticated.getStatusCode());
        assertEquals("hello learner",
            authenticated.getBody());

        assertEquals(HttpStatus.FORBIDDEN,
            rest.withBasicAuth("learner", "local-learn-only")
                .getForEntity("/admin", String.class)
                .getStatusCode());

        assertEquals(HttpStatus.OK,
            rest.withBasicAuth("admin", "local-admin-only")
                .getForEntity("/admin", String.class)
                .getStatusCode());
    }
}
~~~

### 10.2. Test cho profile double

Tạo file **src/test/java/com/example/filterplacement/DoubleRegistrationTest.java**:

~~~java
package com.example.filterplacement;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("double")
class DoubleRegistrationTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void beanHasTwoRegistrationPathsInTheBrokenProfile() {
        ResponseEntity<Map> response =
            rest.getForEntity("/inspect", Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("hit", response.getHeaders()
            .getFirst("X-Lab-Container"));

        Number calls = (Number) response.getBody()
            .get("filterInvocations");
        assertEquals(2, calls.intValue());
    }
}
~~~

Hai file test có tên class/file trùng nhau đúng quy tắc Java, và nằm cùng package với application. Với mỗi profile, Spring Boot tạo ApplicationContext riêng; tests nhận request thật qua embedded server.

Chạy:

~~~bash
./gradlew test
~~~

PowerShell: **.\gradlew.bat test**.

### 10.3. Test này chứng minh gì?

- **Safe:** cùng bean CountingProbeFilter được gọi một lần trên GET /inspect.
- **Double:** trong môi trường embedded Servlet của lab, cùng bean được gọi hai lần vì có hai registration paths.
- Cả hai profile vẫn đi qua một container-level marker filter.
- Quy tắc HTTP authentication và authorization vẫn hoạt động (401/200/403 trong safe).
- Sự khác nhau không nằm ở Controller logic; chỉ nằm ở bean registration.

### 10.4. Test này không chứng minh gì?

- Không bảo đảm các dispatcher types ERROR/ASYNC chạy y hệt.
- Không mô phỏng proxy, service mesh, load balancer hoặc vendor container khác.
- Không có bằng chứng mọi filter trong app production chỉ đăng ký một lần.
- Không chứng minh tất cả request đều có đúng một invocation: một request có thể bị short-circuit trước filter, hoặc nhiều dispatch hợp lệ.
- Không chứng minh filter an toàn với multi-threading chỉ vì request attribute counter chính xác.
- Không chứng minh đủ CSRF/session/logout/MFA/security headers: demo chỉ tạo GET endpoints và HTTP Basic.
- Không thực sự chạy các bài test trên máy trong văn bản này; kết quả là **kỳ vọng code**, phải dùng build thật để xác minh.

**Đừng chỉ assert GET /public trả 200**: cả cấu hình safe và double đều có thể trả 200. Test phải kiểm tra một tín hiệu phản ánh sự khác nhau trong filter invocation.

## 11. Làm sao debug khi custom filter bị chạy hai lần?

Một quy trình chẩn đoán hiệu quả:

### Bước 1 — Xem Filter có phải Spring bean không

Kiểm tra class có @Component, @WebFilter với scan hoặc @Bean Factory method. Nếu là Spring bean implements Filter, Boot Servlet có thể auto-register.

Không lẫn lộn việc Filter có bean với việc nó đã được chèn vào HttpSecurity. Hai quyết định nằm ở hai subsystem khác nhau.

### Bước 2 — Tìm nơi HttpSecurity thêm filter

Kiểm tra các lời gọi:

~~~java
http.addFilterBefore(customFilter, SomeFilter.class);
http.addFilterAfter(customFilter, SomeFilter.class);
http.addFilterAt(customFilter, SomeFilter.class);
~~~

Đây là các snippet thay thế với SomeFilter giả định, không phải chương trình độc lập. Nếu đã chèn filter, cần xác định bean đó có đồng thời container registration hay không.

### Bước 3 — Liệt kê Servlet Filter registrations

Trong môi trường test, có thể xem ServletContext.getFilterRegistrations() hoặc các registration beans, tên filter, URL mappings, dispatcher types và order.

Một servlet registration có thể không dùng đúng Spring bean name. Kiểm tra instance/cấu hình thay vì chỉ tìm chuỗi class name.

### Bước 4 — In danh sách security filters

Có thể bật debug có kiểm soát:

~~~properties
logging.level.org.springframework.security.web.DefaultSecurityFilterChain=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
~~~

Spring Security thường log danh sách filters khi dựng chain ở mức DEBUG, tùy version. Kiểm tra SecurityFilterChain nào khớp request, custom filter có mặt và thứ tự tương đối với auth/authorization filters.

**Không bật request/response body logging, Authorization/Cookie header hoặc TRACE toàn diện trong production chỉ để tìm thứ tự filter.**

### Bước 5 — Phân biệt hai registration với hai HTTP requests

Trình duyệt có thể tự gửi:

- GET /favicon.ico.
- OPTIONS CORS preflight.
- GET tài nguyên CSS/JS.
- HTTP redirect sang một URL khác.
- Request lặp do frontend retry.
- ERROR dispatch sau exception.

Đừng thấy “hai dòng log gần nhau” rồi kết luận cùng HTTP request chạy filter hai lần. Gắn request ID server-side không chứa secret và kiểm tra count trong request attribute hoặc instrumentation có scope rõ ràng.

### Bước 6 — So sánh profile safe và double

Khi có lab hoặc integration test tương tự, thay đổi **duy nhất** việc disabled container registration. Nếu số lượt gọi đổi từ hai xuống một, đó là bằng chứng mạnh cho nguyên nhân duplicate registration trong môi trường đó.

### Bước 7 — Sửa ownership và chạy regression tests

Nếu filter chỉ thuộc security chain, setEnabled(false) ở FilterRegistrationBean hoặc không khai báo Filter bean. Không chữa bằng cách đặt một biến static "alreadyCalled" vì sẽ trộn các requests và users.

## 12. Một số bẫy phức tạp hơn

### 12.1. Filter bean được chèn ở hai SecurityFilterChain

Khi có nhiều SecurityFilterChain, **FilterChainProxy chỉ chọn chain đầu tiên khớp** trong cấu hình thông thường. Một Filter instance được tham chiếu ở hai chain khác nhau không có nghĩa hai chain đều chạy cho một request.

Nhưng cùng instance có thể mang state, configuration hoặc marker dùng chung theo cách nguy hiểm. Nếu các chains có nhiệm vụ khác nhau, xem xét tách filter instances, giới hạn stateless design và kiểm tra matchers.

### 12.2. Không có SecurityFilterChain khớp

Nếu một request không khớp chain nào, security filters không được áp dụng. Nhưng một Filter bean auto-registered ở container vẫn có thể chạy trên URL đó. Điều này gây cảm giác “filter security của tôi chạy trên URL mà chain không match”, thực ra đó là **bản đăng ký ở cấp container**.

Hãy kiểm tra first-match semantics và có fallback SecurityFilterChain phù hợp. Không xem sự tồn tại của một logging filter là bằng chứng URL đã được bảo vệ bởi Spring Security.

### 12.3. permitAll không bỏ security chain

Một URL permitAll vẫn đi qua những security filters của chain được chọn. Một custom filter có thể vẫn được gọi trên /public. Nếu filter chặn request public dựa trên logic riêng, **permitAll không bảo đảm request sẽ tới Controller**.

Ngược lại, web.ignoring hoặc không có chain match có thể bỏ qua nhiều security filters/headers. Đừng dùng ignoring chỉ để “ngăn filter chạy” nếu việc đó làm mất những bảo vệ cần thiết.

### 12.4. OncePerRequestFilter và ERROR/ASYNC dispatch

OncePerRequestFilter có các điểm mở rộng như shouldNotFilterAsyncDispatch và shouldNotFilterErrorDispatch. Tên “once” không bảo đảm đúng một lần cho toàn bộ các Servlet dispatch trong mọi cấu hình.

Một ERROR dispatch có thể là request lifecycle riêng; không kết luận có duplicate registration chỉ dựa vào việc filter chạy ở REQUEST và ERROR.

### 12.5. FilterRegistrationBean.enabled=false có xóa bean không?

Không. Bean vẫn sống trong Spring ApplicationContext, được inject vào SecurityFilterChain như thường. Chỉ container registration được tắt.

Đó là lý do phương án này phù hợp khi filter cần inject service/repository/mapper và vẫn phải là một bean.

### 12.6. Thứ tự container và thứ tự Spring Security tách biệt

Nếu FilterRegistrationBean.order đặt thấp hơn, nó ảnh hưởng vị trí trong chuỗi container. Nó không di chuyển AuthorizationFilter trước CsrfFilter trong FilterChainProxy.

Tương tự, @Order trên SecurityFilterChain bean điều khiển chain nào được xét trước; nó không đổi vị trí nội bộ của một filter trong từng chain.

### 12.7. Đăng ký filter mặc định quá rộng

Một @Component Filter được auto-register có thể match nhiều URL hơn securityMatcher của chain mà bạn dự định. Nếu filter thực hiện tenant enforcement với giả định “chỉ chạy sau authentication”, registration quá rộng có thể tạo lỗi 401/500 ở endpoint public hoặc healthcheck.

Nếu nó chỉ phục vụ security, giữ filter **bên trong đúng SecurityFilterChain**. Nếu container filter thật sự cần phạm vi hẹp, cấu hình URL patterns/dispatcher types rõ ràng.

### 12.8. Tạo Authentication từ dữ liệu không đáng tin

Không bao giờ dùng một custom filter để tự tạo authenticated token với role từ request header chưa kiểm chứng. Mọi Authentication đáng tin phải đến từ provider/token verifier/SSO flow đúng thiết kế.

Sai vị trí filter có thể làm bạn đọc nhầm principal, nhưng việc “sửa” bằng cách cấp role mặc định là authentication bypass.

### 12.9. Bắt exception sai chỗ

Một custom filter đặt upstream của ExceptionTranslationFilter rồi ném AccessDeniedException có thể tạo HTTP 500 thay vì 403 nếu không có handler thích hợp. Một filter muốn tận dụng handling chuẩn phải được chèn ở vị trí được wrapper phù hợp bao phủ hoặc dùng API authorization chuẩn.

Không bắt mọi RuntimeException để trả 401; điều đó che DB outages và lỗi lập trình, gây khó quan sát sự cố.

### 12.10. Bean lifecycle và quản lý filter state

Filter beans thường được reuse giữa nhiều concurrent requests. Không giữ Authentication, HttpServletRequest, HttpSession hoặc mutable request counters trong instance fields.

Nếu cần rate limiting, dùng store/service thiết kế thread-safe và distributed-safe; không dùng biến đơn giản trên singleton Filter bean làm security policy cho cả hệ thống.

## 13. Thay filter viết tay bằng cơ chế chuẩn khi có thể

Trước khi dùng addFilterBefore/After/At, hãy kiểm tra Spring Security đã có DSL hoặc hook đúng mục tiêu hay chưa:

| Nhu cầu | Ưu tiên |
| --- | --- |
| HTTP Basic | httpBasic(...) |
| Form login | formLogin(...) |
| CSRF | csrf(...) |
| CORS | cors(...) và CorsConfigurationSource |
| Security headers | headers(...) |
| URL authorization | authorizeHttpRequests(...) |
| Method authorization | @PreAuthorize / AuthorizationManager |
| OAuth2 Resource Server | oauth2ResourceServer(...) |
| Logout | logout(...) |
| Session management | sessionManagement(...), securityContext(...) |
| AuthenticationProvider riêng | Configure provider/AuthenticationManager phù hợp |
| Filter observability | Micrometer/observation integration khi phù hợp |

Một cơ chế chuẩn không nhất thiết đáp ứng mọi requirement, nhưng nó thường xử lý đúng SecurityContext, exception handling, filter ordering và session lifecycle hơn một filter tự dựng từ đầu.

### 13.1. Khi thực sự cần một filter custom

Một custom filter hợp lý cần có:

- Mô tả nhiệm vụ rõ và nằm trong threat model.
- RequestMatcher/route scope cụ thể.
- Điểm anchor được giải thích bằng các security events trước/sau.
- Không dùng dữ liệu người dùng chưa xác minh làm authority.
- Không log raw credentials/tokens.
- Không tạo side effect trùng khi retry/async/error dispatch.
- Registration ownership rõ: container-only hoặc security-only.
- Automated tests cho 200/401/403, CSRF nếu có, session và errors.
- Diagnostics an toàn không làm lộ Authorization/Cookie.
- Thử với những SecurityFilterChain khác và fallback chain.

## 14. Checklist xử lý một sự cố thực tế

Khi thấy custom filter “chạy hai lần”, hãy lần lượt hỏi:

1. Filter có được @Component hoặc @Bean không?
2. Boot có tạo Servlet Filter auto-registration cho bean đó không?
3. Có FilterRegistrationBean cho bean này không; enabled=true hay false?
4. Có ai gọi http.addFilterBefore/After/At với cùng instance không?
5. Filter dùng OncePerRequestFilter hay plain Filter? Log ở doFilterInternal có che lượt gọi nào không?
6. Hai log thuộc cùng HTTP request hay hai requests/dispatch khác nhau?
7. Cả hai lượt gọi nằm ở Servlet Container hay một lượt container, một lượt SecurityFilterChain?
8. Filter trong chain nào; @Order và securityMatcher có đúng không?
9. Filter cần Authentication đã verified chưa; vị trí hiện hành có đáp ứng không?
10. Filter có bị đặt trước ExceptionTranslationFilter gây lỗi mapping 401/403 không?
11. Có built-in DSL thay thế filter custom không?
12. Nếu cần bean, có thể dùng FilterRegistrationBean.setEnabled(false) không?
13. Nếu không cần bean, có thể tạo filter trực tiếp trong HttpSecurity không?
14. Có kiểm thử embedded server với request ID/counter theo request không?
15. Có ERROR/ASYNC dispatch, redirect, browser retries hoặc CORS preflight không?
16. Có session/context shared mutable state giữa nhiều users không?
17. Sau sửa, security headers, CSRF, authentication và authorization còn đúng không?
18. Có filter nào vô tình chạy trên route ngoài securityMatcher không?

## 15. Câu hỏi ôn tập và đáp án

**Câu 1.** Vì sao @Component Filter có thể bị gọi hai lần khi thêm qua HttpSecurity?  
**Đáp:** Boot có thể auto-register Filter bean vào Servlet Container, trong khi HttpSecurity cũng đưa cùng bean vào SecurityFilterChain.

**Câu 2.** FilterRegistrationBean.setEnabled(false) có xóa Spring bean không?  
**Đáp:** Không. Nó chỉ tắt Servlet Container registration; filter vẫn có thể được inject và dùng trong HttpSecurity.

**Câu 3.** addFilterBefore và addFilterAfter thuộc thứ tự nào?  
**Đáp:** Thứ tự nội bộ của Spring Security filters trong SecurityFilterChain, không phải container registration order.

**Câu 4.** addFilterAt có luôn thay thế hoàn toàn filter cũ không?  
**Đáp:** Không nên dựa vào điều đó. Javadoc nói nhiều filter cùng vị trí không tự ghi đè và có thể có thứ tự không xác định; cấu hình trùng còn có thể bị từ chối. Muốn thay filter cũ, cần loại bỏ hoặc disable cơ chế tạo nó.

**Câu 5.** Có cần đưa BasicAuthenticationFilter thành @Component không?  
**Đáp:** Không. Dùng httpBasic DSL để Spring Security đặt nó ở vị trí thích hợp.

**Câu 6.** Vì sao OncePerRequestFilter chưa đủ để sửa duplicate registration?  
**Đáp:** Marker có thể khiến doFilterInternal chỉ chạy một lần trong một số đường đi, nhưng hai registration vẫn còn và có thể khác nhau ở các dispatch/điều kiện.

**Câu 7.** Vì sao lab dùng request attribute để đếm filter invocations?  
**Đáp:** Vì counter thuộc một request, không bị nhiễu bởi nhiều requests chạy đồng thời.

**Câu 8.** Filter cần Principal đã verified nên đặt trước hay sau authentication?  
**Đáp:** Sau authentication mechanism phù hợp và trước authorization theo chain thực tế; phải kiểm tra context và exception handling.

**Câu 9.** Filter đặt sau BasicAuthenticationFilter có luôn được gọi khi Basic password sai không?  
**Đáp:** Không. Authentication filter có thể từ chối request và không gọi tiếp chain.

**Câu 10.** Một filter không phụ thuộc SecurityContext cần chạy ngoài security chain có hợp lệ không?  
**Đáp:** Có. Có thể đăng ký bằng FilterRegistrationBean container-only, miễn không đưa cùng filter vào HttpSecurity.

**Câu 11.** Một Filter bean có thể chạy ở URL không thuộc SecurityFilterChain dự kiến không?  
**Đáp:** Có, nếu Boot auto-register nó ở Servlet Container với URL mapping rộng.

**Câu 12.** permitAll có loại bỏ mọi security filters không?  
**Đáp:** Không. Nó là authorization rule; filters vẫn có thể chạy trong chain đã chọn.

**Câu 13.** @Order trên SecurityFilterChain có đổi thứ tự của CsrfFilter và AuthorizationFilter không?  
**Đáp:** Không. @Order điều khiển chain selection; thứ tự filter nội bộ do HttpSecurity cấu hình.

**Câu 14.** Vì sao không chỉ dùng MockMvc để chứng minh container auto-registration?  
**Đáp:** MockMvc có thể không dựng toàn bộ embedded Servlet Container; test RANDOM_PORT qua HTTP thật đáng tin hơn cho registration path.

**Câu 15.** Số lần doFilter=2 có thể đến từ gì ngoài duplicate registration?  
**Đáp:** Dispatcher types như ERROR/ASYNC, internal forwards, nhiều HTTP requests, retries hoặc logic gọi lặp của ứng dụng.

**Câu 16.** Filter cần kiểm tra tenant nên đọc tenant từ header rồi tin nó ngay không?  
**Đáp:** Không. Tenant ID là input chưa đáng tin; phải đối chiếu với principal đã được xác thực và quyền thật.

**Câu 17.** Nếu exception xảy ra upstream của ExceptionTranslationFilter, có chắc ra 403 không?  
**Đáp:** Không. Handler chuẩn có thể không bao phủ exception đó; phải kiểm tra vị trí và exception translation.

**Câu 18.** Làm sao giữ một custom Filter là Spring bean mà chỉ chạy trong security chain?  
**Đáp:** @Bean filter + FilterRegistrationBean disabled + HttpSecurity.addFilterBefore/After tại vị trí phù hợp.

## 16. Tài liệu tham khảo chính thức

- Spring Security — Servlet Architecture, Adding Filters và Declaring Your Filter as a Bean: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — HttpSecurity API, addFilterBefore/addFilterAfter/addFilterAt: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/builders/HttpSecurity.html
- Spring Security — FilterChainProxy API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html
- Spring Security — Authorization HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Boot — Embedded Web Servers, Disable Registration of a Servlet or Filter: https://docs.spring.io/spring-boot/how-to/webserver.html
- Spring Boot — Spring Security Auto-configuration: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- Spring Framework — OncePerRequestFilter API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Framework — DelegatingFilterProxy API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/DelegatingFilterProxy.html
