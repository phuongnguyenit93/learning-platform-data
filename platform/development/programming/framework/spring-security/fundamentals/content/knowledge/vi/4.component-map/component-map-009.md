# Những hợp đồng chung và các API riêng cho mô hình reactive trong Spring Security

Spring Security hỗ trợ cả ứng dụng **Servlet/Spring MVC** lẫn ứng dụng **reactive/Spring WebFlux**. Hai mô hình chia sẻ nhiều khái niệm và kiểu dữ liệu cốt lõi như Authentication, GrantedAuthority, SecurityContext, UserDetails và PasswordEncoder, nhưng **đường đi request, cơ chế lưu ngữ cảnh, filter chain, API xác thực và cách thực thi phân quyền** có sự khác biệt quan trọng.

Nếu đã học SecurityFilterChain, HttpSecurity, AuthenticationManager và SecurityContextHolder ở Spring MVC, bạn không nên bê nguyên cấu hình đó sang WebFlux. Trong WebFlux, các thành phần tương ứng thường là **SecurityWebFilterChain, ServerHttpSecurity, ReactiveAuthenticationManager và ReactiveSecurityContextHolder**. Nguyên tắc “xác thực danh tính, quyết định quyền, bảo vệ request” vẫn giữ nguyên; cách triển khai phải phù hợp với chuỗi xử lý bất đồng bộ bằng Reactor.

Bài học cung cấp bản đồ các hợp đồng và API, giải thích **vì sao có sự tách biệt**, trình bày ví dụ Spring Boot WebFlux đầy đủ và hướng dẫn kiểm thử. Phạm vi là **Spring Security cho server HTTP reactive**; WebClient chạy ở client, gateway, OAuth2, RSocket và method security được giới thiệu trong các điểm liên quan, không biến chúng thành cùng một hệ API.

## 1. Hai stack web, một số khái niệm bảo mật chung

### 1.1. Servlet/Spring MVC xử lý request theo mô hình nào?

Trong ứng dụng Spring MVC, request HTTP đi qua **Servlet Filter chain** rồi tới DispatcherServlet/Controller. Spring Security tích hợp bằng các Servlet Filter và sử dụng các thành phần như:

- **HttpSecurity**: DSL cấu hình quyền truy cập, HTTP Basic, form login, CSRF và các filter cho Servlet.
- **SecurityFilterChain**: tập hợp các Servlet Filter được áp dụng cho request khớp điều kiện.
- **AuthenticationManager**: hợp đồng xác thực trả về Authentication hoặc ném AuthenticationException trong mô hình đồng bộ.
- **SecurityContextHolder**: điểm truy cập SecurityContext, thường dùng chiến lược dựa trên ThreadLocal trong các luồng Servlet thông thường.
- **AuthenticationEntryPoint / AccessDeniedHandler**: quyết định phản hồi khi cần xác thực hoặc bị từ chối quyền trong luồng Servlet.

ThreadLocal hoạt động thuận tiện khi những xử lý liên quan diễn ra trên luồng được quản lý phù hợp. Tuy nhiên nếu công việc chuyển sang thread khác, asynchronous callback hoặc một pipeline reactive, **không thể mặc định SecurityContext từ ThreadLocal sẽ tự theo sang mọi bước**.

### 1.2. Spring WebFlux xử lý request theo mô hình nào?

Spring WebFlux có **WebFilter**, **WebHandler** và các kiểu publisher của Project Reactor:

- **Mono<T>**: biểu diễn quá trình bất đồng bộ phát ra tối đa một giá trị hoặc hoàn tất không có giá trị.
- **Flux<T>**: biểu diễn quá trình phát ra 0 đến nhiều giá trị theo mô hình Reactive Streams, bao gồm tín hiệu lỗi và hoàn tất.
- **Reactor Context**: nơi mang metadata theo chuỗi subscriber, phù hợp để truyền ngữ cảnh bảo mật qua những thao tác reactive được thiết kế đúng.
- **SecurityWebFilterChain**: chuỗi WebFilter bảo mật khớp với request WebFlux.
- **ServerHttpSecurity**: DSL riêng cho WebFlux.
- **ReactiveSecurityContextHolder**: giúp đọc hoặc gắn SecurityContext qua Reactor Context, thay vì dựa vào ThreadLocal trong logic reactive.

Ngữ nghĩa HTTP **vẫn giống nhau**: GET, POST, cookie, Authorization, 401, 403, CSRF, CORS, HTTPS. Reactivity thay đổi API lập trình và vòng đời thực thi; nó **không miễn trừ** việc kiểm tra role, quyền theo object, tenant hoặc các luồng bảo mật nghiệp vụ.

~~~text
Servlet / Spring MVC                     Reactive / Spring WebFlux

HTTP request                             HTTP request
     |                                        |
Servlet Filter chain                      WebFilter chain
     |                                        |
Spring Security                           Spring Security
SecurityFilterChain                       SecurityWebFilterChain
HttpSecurity                              ServerHttpSecurity
     |                                        |
DispatcherServlet                        DispatcherHandler / WebHandler
     |                                        |
MVC Controller                           WebFlux Controller / Handler
     |                                        |
Data/service                             Reactive publisher: Mono / Flux
     |                                        |
HTTP response                            HTTP response
~~~

Sơ đồ là khái quát. Một ứng dụng có thể sử dụng cơ chế async khác; không đồng nghĩa mọi xử lý Servlet đều luôn giữ một thread hoặc WebFlux không bao giờ có thread. Điều quan trọng là **ngữ cảnh bảo mật và các hợp đồng framework được thiết kế cho stack đang chạy**.

## 2. Các hợp đồng và kiểu dữ liệu dùng chung

Những kiểu sau thuộc **Spring Security Core** và có ý nghĩa trong cả Servlet lẫn reactive:

| Kiểu/hợp đồng | Ý nghĩa | Dùng chung như thế nào? |
| --- | --- | --- |
| **Authentication** | Đại diện yêu cầu/chứng cứ xác thực hoặc danh tính đã xác thực, principal, credentials, authorities và trạng thái authenticated. | Cả hai stack đều dùng các implementation Authentication phù hợp. |
| **GrantedAuthority** | Biểu diễn một quyền đã được cấp, ví dụ ROLE_USER hoặc SCOPE_orders.read. | Kiểu quyền nền tảng dùng chung; policy quyết định cách hiểu. |
| **SecurityContext** | Chứa Authentication của ngữ cảnh bảo mật hiện tại. | Interface chung; cách **lưu, khôi phục và truyền context** khác nhau. |
| **UserDetails** | Mô hình tài khoản người dùng, password hash, authorities và trạng thái account. | Có thể dùng với UserDetailsService hoặc ReactiveUserDetailsService tương ứng. |
| **PasswordEncoder** | Mã hóa một chiều và so khớp hash mật khẩu. | Interface đồng bộ vẫn dùng được trong các hệ thống reactive; cần xét chi phí xử lý. |
| **AuthenticationException** | Họ ngoại lệ cho những trường hợp xác thực không thành công. | Cả hai mô hình có thể biểu đạt lỗi xác thực bằng ngoại lệ, nhưng cách báo qua pipeline khác nhau. |
| **AccessDeniedException** | Biểu thị truy cập bị từ chối. | Có thể xuất hiện ở các điểm kiểm soát quyền của mỗi stack. |
| **UsernamePasswordAuthenticationToken** | Một kiểu Authentication thường dùng cho xác thực username/password. | Có thể tham gia cả cơ chế đồng bộ và reactive khi được dùng đúng quy trình. |

Đừng nhầm **kiểu dữ liệu dùng chung** với **cách truy cập dữ liệu đó**. Ví dụ Authentication vẫn là interface giống nhau; nhưng trong một chuỗi reactive, bạn thường lấy thông tin hiện tại qua **Mono<SecurityContext>** và Reactor Context, thay vì gọi SecurityContextHolder.getContext() rồi tin rằng nó luôn chứa principal của request.

**Không tin dữ liệu client tự khai là Authentication hợp lệ.** Header như X-Role: ADMIN, userId trong body hoặc JWT chỉ được giải mã Base64 không chứng minh quyền. Cả Servlet và WebFlux đều cần xác thực credential qua cơ chế đã cấu hình trước khi dùng authorities để phân quyền.

### 2.1. ROLE_ và scope vẫn cùng ngữ nghĩa

Trong Spring Security, **hasRole("ADMIN")** thường kiểm tra authority **ROLE_ADMIN**, còn **hasAuthority("ADMIN")** kiểm tra chính xác authority được cung cấp. Quy tắc này áp dụng cho các DSL hỗ trợ tương ứng ở cả hai stack.

Với OAuth2 Resource Server, scope có thể được biểu diễn thành authority như **SCOPE_orders.read**, theo converter được cấu hình. Đừng tự cho rằng claim có tên role hoặc scope sẽ luôn được chuyển thành authority giống nhau trong mọi dự án.

### 2.2. Điều gì không phải là hợp đồng dùng chung có thể thay thế trực tiếp?

- **AuthenticationManager** (đồng bộ) và **ReactiveAuthenticationManager** (reactive) phục vụ cùng mục tiêu nhưng **khác chữ ký API và cách thực thi**.
- **UserDetailsService** và **ReactiveUserDetailsService** không phải một interface. Cùng trả lời câu hỏi “tìm user theo username”, nhưng reactive trả **Mono<UserDetails>**.
- **SecurityContextHolder** và **ReactiveSecurityContextHolder** dùng những cơ chế lưu ngữ cảnh khác nhau; chỉ giống mục đích, không thay thế máy móc.
- **SecurityFilterChain** là cho Servlet; **SecurityWebFilterChain** là cho WebFlux.
- **HttpSecurity** là cho Servlet; **ServerHttpSecurity** là cho WebFlux.

Việc có cùng chữ “Security” không đủ để lựa chọn import. Hãy xem **package, chữ ký phương thức và stack web** thay vì nhớ gần đúng theo tên.

## 3. Bảng đối chiếu API Servlet và reactive

| Mục đích | Servlet / Spring MVC | Reactive / Spring WebFlux | Điểm cần nhớ |
| --- | --- | --- | --- |
| Cấu hình bảo mật HTTP | **HttpSecurity** | **ServerHttpSecurity** | Hai DSL riêng; không dùng nhầm import. |
| Chuỗi bảo mật | **SecurityFilterChain** | **SecurityWebFilterChain** | Servlet Filter khác WebFilter. |
| Bộ lọc cơ bản | javax/jakarta Servlet Filter tùy thế hệ | **org.springframework.web.server.WebFilter** | WebFlux dùng nonblocking publisher API. |
| Khớp request ở cấp chain | RequestMatcher / securityMatcher | **ServerWebExchangeMatcher / securityMatcher** | Khác đối tượng request cần kiểm tra. |
| Quy tắc URL | **authorizeHttpRequests / requestMatchers** | **authorizeExchange / pathMatchers** | Cùng intent, DSL khác. |
| Quy tắc tất cả request | anyRequest() | **anyExchange()** | Cả hai nên có fallback có chủ đích. |
| Xác thực | **AuthenticationManager** | **ReactiveAuthenticationManager** | Đồng bộ Authentication so với Mono<Authentication>. |
| Tra cứu user | **UserDetailsService** | **ReactiveUserDetailsService** | UserDetails chung; cách trả kết quả khác. |
| User trong bộ nhớ | InMemoryUserDetailsManager | **MapReactiveUserDetailsService** | Demo/test, không phải nguồn danh tính production. |
| Context hiện tại | **SecurityContextHolder** | **ReactiveSecurityContextHolder** | ThreadLocal so với Reactor Context. |
| Lưu/khôi phục context | SecurityContextRepository | **ServerSecurityContextRepository** | Tích hợp request/response theo từng stack. |
| Filter xác thực tùy chỉnh | Các Servlet authentication filters | **AuthenticationWebFilter** | Reactive filter xử lý publisher và manager reactive. |
| Bắt đầu xác thực | **AuthenticationEntryPoint** | **ServerAuthenticationEntryPoint** | Ví dụ 401/challenge hoặc login redirect. |
| Từ chối quyền | **AccessDeniedHandler** | **ServerAccessDeniedHandler** | Xử lý 403 hoặc policy từ chối khác. |
| Dịch ngoại lệ | ExceptionTranslationFilter | **ExceptionTranslationWebFilter** | Chuyển một số ngoại lệ thành phản hồi HTTP. |
| Method security | **@EnableMethodSecurity** | **@EnableReactiveMethodSecurity** | AOP và Reactor Context cần hoạt động cùng nhau. |
| Test HTTP | MockMvc | **WebTestClient** | Test đúng stack và kết nối/handler đã cấu hình. |

Hãy nhận diện ba tầng khác nhau:

1. **Core contracts**: danh tính, quyền, security context, password hash.
2. **Stack adapters**: filter chain, request matcher, HTTP configuration, handlers.
3. **Integration trong ứng dụng**: lấy principal, truy vấn user/permission, database, message queue và logic nghiệp vụ.

Không nên phân loại mọi type có chữ “Reactive” là bản mới tốt hơn của Servlet. Chúng giải quyết nhu cầu **khác mô hình thực thi**, lựa chọn dựa trên kiến trúc ứng dụng.

## 4. ReactiveAuthenticationManager và ReactiveUserDetailsService

### 4.1. Xác thực đồng bộ

Với Servlet, hợp đồng cốt lõi là:

~~~java
// Chỉ mô tả chữ ký của interface, không phải file Java độc lập.
Authentication authenticate(Authentication request)
        throws AuthenticationException;
~~~

Một AuthenticationManager quyết định chứng cứ xác thực có hợp lệ và trả Authentication phù hợp hoặc phát tín hiệu lỗi. Các AuthenticationProvider có thể được kết hợp trong ProviderManager.

### 4.2. Xác thực reactive

Trong WebFlux, hợp đồng là:

~~~java
// Chỉ mô tả chữ ký của interface, không phải file Java độc lập.
Mono<Authentication> authenticate(Authentication authentication);
~~~

**ReactiveAuthenticationManager.authenticate(...)** trả publisher:

- Phát ra **Authentication** đã xác thực khi thành công.
- Hoàn tất bằng **Mono.empty()** khi implementation không thể quyết định cho loại Authentication đó.
- Phát lỗi reactive khi authentication thất bại.

Đây là khác biệt quan trọng so với việc trả về Authentication ngay. Trong một authentication filter reactive, framework sẽ subscribe/xử lý pipeline theo quy tắc của nó; bạn **không nên tự subscribe hoặc block()** chỉ để lấy Authentication trong code ứng dụng.

**ReactiveUserDetailsService** có phương thức:

~~~java
// Chỉ mô tả chữ ký của interface, không phải file Java độc lập.
Mono<UserDetails> findByUsername(String username);
~~~

UserDetails vẫn là core type dùng chung. Nhưng việc tìm user có thể được thực hiện qua cơ sở dữ liệu reactive hoặc dịch vụ mạng với Reactor. Một implementation cần phát tín hiệu hoàn thành/lỗi đúng hợp đồng và không trả null thay cho Mono.

Ví dụ về ý tưởng tra cứu, **mảnh mã minh họa cần một repository reactive có sẵn**:

~~~java
public Mono<UserDetails> findByUsername(String username) {
    return reactiveUserRepository.findByUsername(username)
        .map(account -> User.withUsername(account.username())
            .password(account.passwordHash())
            .authorities(account.authorities())
            .disabled(!account.enabled())
            .build());
}
~~~

Không gọi JDBC blocking trực tiếp trong hàm này rồi trả Mono.just(...). **Mono.just(repository.findByUsername(...))** vẫn chạy câu lệnh blocking ngay lúc dựng publisher. Với một nguồn blocking bắt buộc, phải thiết kế điểm cô lập và scheduler phù hợp; với hệ thống WebFlux thực sự, ưu tiên driver/repository không blocking khi có thể.

### 4.3. PasswordEncoder là trường hợp thú vị

**PasswordEncoder** vẫn có các phương thức đồng bộ như encode(...) và matches(...). BCrypt là hàm có chi phí CPU có chủ ý, không trở thành “không blocking” chỉ vì bao quanh bởi Mono.

Trong demo nhỏ, có thể tạo hash lúc khởi động. Trong production với lưu lượng cao, chi phí xử lý mật khẩu, scheduler, thread pool, giới hạn đồng thời và bảo vệ khỏi brute-force phải được đánh giá. Đừng dùng toán tử reactive để làm biến mất chi phí CPU.

**Không dùng User.withDefaultPasswordEncoder() trong ứng dụng thật**, và không lưu plain text. Chọn PasswordEncoder phù hợp, quản lý mật khẩu và version hash theo quy định của hệ thống.

## 5. ReactiveSecurityContextHolder và Reactor Context

Trong Servlet, nhiều ví dụ dùng:

~~~java
// Mảnh minh họa Servlet; không dùng để lấy principal trong pipeline WebFlux.
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Cách này dễ gây hiểu nhầm khi chuyển sang WebFlux. Một publisher reactive có thể tiếp tục trên luồng khác. **ThreadLocal không phải cơ chế truyền ngữ cảnh bảo mật đáng tin qua mọi bước Reactor**.

Trong WebFlux dùng:

~~~java
// Mảnh minh họa trong mã đã có Project Reactor/Spring Security.
Mono<String> currentUserName =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
~~~

Ngữ cảnh hiện tại được tìm trong **Reactor Context theo subscription**, không đồng nghĩa một biến toàn cục hoặc một ThreadLocal vĩnh viễn.

### 5.1. Đọc principal trong WebFlux Controller

Một Controller có thể nhận **Mono<Principal>** theo cơ chế resolution của Spring WebFlux:

~~~java
@GetMapping("/api/me")
public Mono<String> me(Mono<Principal> principal) {
    return principal.map(Principal::getName);
}
~~~

Đây là **mảnh method cần đặt trong @RestController**, dùng java.security.Principal và reactor.core.publisher.Mono. Nó tận dụng integration của WebFlux để lấy principal đã được framework gắn vào request.

Trong một service reactive cần đọc context, có thể sử dụng ReactiveSecurityContextHolder. Khi một luồng được tạo ngoài request (scheduler, message consumer, publisher tự dựng), **không nên tự giả định security context của HTTP request sẽ tồn tại**.

### 5.2. Gắn Authentication vào một chuỗi Mono

Khi cần viết test hoặc tích hợp theo ngữ cảnh chủ động, API cung cấp:

~~~java
Mono<String> value = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication)
    );
~~~

Ví dụ chỉ là **mảnh mã**, biến authentication phải là một Authentication hợp lệ do cơ chế tin cậy tạo ra. **withAuthentication** cung cấp Reactor Context cho nhánh publisher; nó không tạo credential hợp lệ từ dữ liệu client, không lưu session và không sửa toàn bộ ngữ cảnh ngoài nhánh.

Điều cần nhớ về Reactor:

- **subscribe** kích hoạt thực thi nhiều pipeline cold; phần lớn Controller trả Mono/Flux để framework subscribe.
- **contextWrite** gắn/biến đổi context trên phạm vi subscription theo quy tắc propagation của Reactor.
- **publishOn/subscribeOn** có thể đổi thread; context của Reactor được truyền theo ngữ nghĩa Reactor, còn ThreadLocal tùy tiện thì không.
- Tách một publisher ra ngoài lifecycle request, gọi subscribe thủ công, chuyển sang callback ngoài Reactor hoặc dùng thư viện không tích hợp có thể làm mất các giả định về bảo mật. Cần kiểm thử propagation theo đường thực tế.
- Không lưu Authentication trong một biến static/global cho mọi request; có thể rò thông tin hoặc nhầm danh tính giữa người dùng.

## 6. ServerHttpSecurity và SecurityWebFilterChain

### 6.1. Cấu hình Servlet quen thuộc

Một cấu hình Servlet thường trông như sau:

~~~java
// Mảnh cấu hình Spring MVC/Servlet, không thể cắm nguyên vào WebFlux.
@Bean
SecurityFilterChain servletSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Kiểu HttpSecurity/Servlet SecurityFilterChain **không phải** kiểu được WebFlux sử dụng.

### 6.2. Cấu hình WebFlux tương ứng

~~~java
// Mảnh cấu hình WebFlux trong lớp @Configuration.
@Bean
SecurityWebFilterChain webfluxSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public").permitAll()
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Khác biệt cụ thể:

- HttpSecurity → **ServerHttpSecurity**.
- SecurityFilterChain → **SecurityWebFilterChain**.
- authorizeHttpRequests → **authorizeExchange**.
- requestMatchers → **pathMatchers** với đường URL WebFlux.
- anyRequest → **anyExchange**.
- Các filter/entry point tương ứng thuộc **web.server** thay vì Servlet web.

Khi muốn chính sách chỉ áp dụng cho một HTTP method, dùng overload có **HttpMethod**:

~~~java
.pathMatchers(HttpMethod.GET, "/api/public").permitAll()
~~~

**permitAll()** là cho phép ở lớp authorization, không đồng nghĩa bỏ qua toàn bộ security WebFilter. Nếu client gửi credential hỏng trên một URL công khai, filter xác thực đã bật vẫn có thể xử lý credential đó và trả lỗi trước khi tới bước permitAll.

### 6.3. Nhiều SecurityWebFilterChain

Một ứng dụng có thể khai báo nhiều bean SecurityWebFilterChain với **@Order** và **securityMatcher(ServerWebExchangeMatcher)**. Spring Security chọn chuỗi phù hợp theo thứ tự. Ví dụ API /api/** dùng Bearer còn website dùng form login là trường hợp cần phân tách rõ ràng.

Nếu chain chỉ khớp /api/** và bạn quên chain fallback, URL khác có nguy cơ **không đi qua chính sách bạn mong muốn**. Xác minh hành vi của toàn bộ application route, đường quản trị và Actuator nếu được cấu hình.

### 6.4. Điều gì quyết định lựa chọn WebFlux hay MVC?

**spring-boot-starter-webflux** cung cấp stack WebFlux. **spring-boot-starter-web** cung cấp MVC. Trong Spring Boot, khi cả starter web và webflux cùng có mặt, MVC thường được ưu tiên làm ứng dụng server mặc định; chỉ có dependency WebFlux để dùng WebClient **không có nghĩa** server đã chuyển thành reactive.

Nếu bài toán là **gọi HTTP từ ứng dụng MVC**, bạn có thể dùng WebClient như client HTTP mà vẫn cấu hình server bằng **HttpSecurity/SecurityFilterChain**. Nếu bản thân server là WebFlux, mới dùng **ServerHttpSecurity/SecurityWebFilterChain** cho luồng HTTP server reactive.

Đừng chọn reactive chỉ vì muốn “nhanh hơn”. Reactive phù hợp cho các hệ thống có nhiều I/O bất đồng bộ, nhưng thêm độ phức tạp khi các dependency và database vẫn blocking. Đánh giá theo workload, hỗ trợ thư viện và khả năng vận hành.

## 7. Bộ lọc, authentication entry point và denied handler trong reactive

Các thành phần reactive có hậu tố **WebFilter** hoặc **Server...**:

| Công việc | Reactive API | Kết quả |
| --- | --- | --- |
| Chèn logic bảo mật vào request | **WebFilter**, **AuthenticationWebFilter** | Thực hiện thao tác dưới dạng Mono<Void> trong WebFilter chain. |
| Lấy/chuyển thông tin đăng nhập | **ServerAuthenticationConverter** | Chuyển ServerWebExchange thành Mono<Authentication> trong luồng tương ứng. |
| Thực hiện xác thực | **ReactiveAuthenticationManager** | Trả Mono<Authentication>. |
| Thành công khi xác thực | **ServerAuthenticationSuccessHandler** | Tiếp tục hoặc quyết định response tùy filter/config. |
| Thất bại trong lần xác thực | **ServerAuthenticationFailureHandler** | Chuyển lỗi thành response hoặc quyết định tiếp theo. |
| Cần bắt đầu xác thực | **ServerAuthenticationEntryPoint** | Thường gửi 401/challenge hoặc chuyển tới login. |
| Quyền bị từ chối | **ServerAccessDeniedHandler** | Thường gửi 403. |
| Dịch lỗi xác thực/authorization | **ExceptionTranslationWebFilter** | Phân nhánh entry point/denied handler theo tình trạng xác thực. |
| Quyết định quyền trên web exchange | **AuthorizationWebFilter** cùng policy reactive | Chặn trước handler nếu không đủ quyền. |

**Không phải mọi 401/403 đều đi qua một handler chung.** Ví dụ lỗi credential ở AuthenticationWebFilter, lỗi CSRF hoặc lỗi authorization có thể được xử lý ở các filter/handler khác nhau. Cần xem chain và cơ chế xác thực đã bật.

Phân biệt:

- **AuthenticationEntryPoint** của Servlet với **ServerAuthenticationEntryPoint** của WebFlux.
- **AccessDeniedHandler** của Servlet với **ServerAccessDeniedHandler** của WebFlux.
- **AuthenticationSuccessHandler/FailureHandler** cho Servlet form login với **ServerAuthenticationSuccessHandler/ServerAuthenticationFailureHandler** trong reactive authentication flow.

Việc cùng trả 401 hoặc 403 không khiến các interface này hoán đổi được. Kể cả phản hồi HTTP cuối giống nhau, chữ ký và đối tượng request hoàn toàn khác.

## 8. AuthorizationManager và reactive method security

Ở Servlet, bạn có thể gặp **AuthorizationManager<RequestAuthorizationContext>** và các API phân quyền method. Trong WebFlux, Spring Security có các **ReactiveAuthorizationManager** và context tương ứng với web exchange. Một triển khai có thể đưa ra quyết định dựa trên publisher Authentication và request/resource đang xét.

Với URL, dùng DSL **authorizeExchange**:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated()
)
~~~

Đây là mảnh cấu hình minh họa. Với app thật, **quyền theo URL không tự hiểu quan hệ sở hữu của từng orderId hoặc tenant**. Service/domain cần kiểm tra quyền trên dữ liệu:

~~~text
Principal đã xác thực: customer-17
GET /api/orders/42
Service tìm đơn 42 và owner/tenant của nó
Chỉ trả đơn nếu người hiện tại có quyền xem đơn đó
~~~

### 8.1. Bảo vệ method reactive

Ở WebFlux, bật **@EnableReactiveMethodSecurity** khi cần kiểm tra annotation ở method:

~~~java
// Mảnh cấu hình, dùng trong lớp @Configuration.
@EnableReactiveMethodSecurity
~~~

Và method reactive có thể được bảo vệ bằng:

~~~java
// Mảnh method nằm trong Spring bean, không chạy độc lập.
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> adminReport() {
    return Mono.just("report");
}
~~~

Những điểm cần nhớ:

- Đây là API cho **reactive method security**, không phải thay @EnableMethodSecurity của Servlet bằng một annotation tùy ý.
- Đối tượng trả về thường là **Mono/Flux hoặc publisher phù hợp** để Spring Security có thể áp dụng luồng phân quyền reactive.
- Truyền Authentication/context qua Reactor Context theo cơ chế hỗ trợ.
- Method security dựa trên Spring AOP; **self-invocation** bên trong cùng một bean có thể bỏ qua proxy. Kiểm thử qua đường gọi bean thực tế.
- Annotation không thay thế quyền đối tượng, kiểm soát data filtering hoặc test các side effects.

## 9. Ví dụ hoàn chỉnh Spring Boot 3.3.6 + WebFlux + Spring Security

Mục tiêu demo: chạy một **reactive web server** với public endpoint, protected endpoint và admin endpoint. Đây là một project WebFlux thật, không dùng Servlet Controller hay Mockito.

**Yêu cầu:** JDK 17+, Maven 3.9+, cổng 8080 trống. Ví dụ dùng HTTP Basic và in-memory accounts để minh họa. Chạy trên localhost, không dùng mật khẩu demo cho hệ thống thật. Trong triển khai qua mạng thực, cần HTTPS và quản lý credential đúng cách.

~~~text
reactive-security-demo/
  pom.xml
  src/main/java/com/example/reactivesecurity/
    ReactiveSecurityApplication.java
    ApiController.java
    SecurityConfig.java
  src/test/java/com/example/reactivesecurity/
    ReactiveSecurityTests.java
~~~

### 9.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-security-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

**Đặc biệt:** pom.xml chứa **spring-boot-starter-webflux** và **không chứa spring-boot-starter-web**. Điều này giúp giữ ví dụ là WebFlux server thay vì vô tình chạy MVC khi cả hai starter có mặt.

### 9.2. ReactiveSecurityApplication.java

~~~java
package com.example.reactivesecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityApplication.class, args);
    }
}
~~~

Package chứa main là **com.example.reactivesecurity**, cùng package với các bean, nên Spring Boot có thể quét những class bên dưới.

### 9.3. ApiController.java

~~~java
package com.example.reactivesecurity;

import java.security.Principal;
import java.util.Map;
import reactor.core.publisher.Mono;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<Map<String, String>> publicEndpoint() {
        return Mono.just(Map.of("message", "public"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(Mono<Principal> principal) {
        return principal.map(p -> Map.of("user", p.getName()));
    }

    @GetMapping("/api/admin")
    public Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("message", "admin"));
    }
}
~~~

Controller trả **Mono** để thể hiện kiểu xử lý WebFlux. Tham số Mono<Principal> của /api/me nhận principal theo cơ chế của Spring WebFlux. **Không có câu lệnh tự kiểm role trong Controller**: chính sách access được cấu hình ở SecurityWebFilterChain.

Với JSON, tên trường message/user ổn định nhưng **thứ tự trường trong một object JSON không nên được xem là hợp đồng** khi có nhiều trường.

### 9.4. SecurityConfig.java

~~~java
package com.example.reactivesecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .pathMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService reactiveUsers(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo-reader"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin"))
            .roles("USER", "ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

**Giải thích:**

- **@EnableWebFluxSecurity** bật tích hợp Spring Security WebFlux.
- **SecurityWebFilterChain** là bean chứa các policy HTTP reactive.
- **ServerHttpSecurity** thay HttpSecurity.
- **pathMatchers(HttpMethod.GET, ...)** giới hạn cả path và method; một POST không tự được permitAll vì GET công khai.
- **authenticated()** chỉ yêu cầu danh tính phù hợp, không đòi role nhất định.
- **hasRole("ADMIN")** kiểm authority ROLE_ADMIN.
- **anyExchange().denyAll()** từ chối các exchange không khớp rule trước.
- **httpBasic()** cung cấp cơ chế xác thực username/password qua HTTP Basic, phù hợp kiểm thử đơn giản.
- **ReactiveUserDetailsService** cung cấp nguồn tra cứu user qua hợp đồng reactive; MapReactiveUserDetailsService dùng user trong bộ nhớ.
- **PasswordEncoder** dùng BCrypt hash, không lưu plain password làm trường password của UserDetails.

Demo chỉ có endpoint **GET** và giữ cơ chế CSRF mặc định. Khi thêm POST/PUT/PATCH/DELETE, hãy xét CSRF theo mô hình xác thực, cookie và client. Không tắt CSRF chỉ vì một test POST trả 403.

**Cấu hình này là mẫu học tập.** InMemory accounts và mật khẩu demo không phù hợp production; HTTP Basic chỉ Base64 credentials nên phải dùng HTTPS khi trao đổi trên mạng.

### 9.5. Chạy ứng dụng

Tại thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Nếu port 8080 trống, ứng dụng WebFlux sẽ lắng nghe ở http://localhost:8080 theo cấu hình mặc định. Kiểm tra ba trường hợp bằng curl hoặc curl.exe trên Windows:

~~~powershell
curl.exe -i http://localhost:8080/api/public
curl.exe -i http://localhost:8080/api/me
curl.exe -i -u reader:demo-reader http://localhost:8080/api/me
curl.exe -i -u reader:demo-reader http://localhost:8080/api/admin
curl.exe -i -u admin:demo-admin http://localhost:8080/api/admin
~~~

**Kết quả kỳ vọng** (mã HTTP và ý nghĩa, header bổ sung phụ thuộc phiên bản/cấu hình):

| Request | HTTP status | Response |
| --- | --- | --- |
| GET /api/public ẩn danh | **200** | JSON có message = public. |
| GET /api/me ẩn danh | **401** | Cần xác thực; HTTP Basic challenge. |
| GET /api/me với reader/demo-reader | **200** | JSON có user = reader. |
| GET /api/admin với reader/demo-reader | **403** | Có danh tính nhưng thiếu ROLE_ADMIN. |
| GET /api/admin với admin/demo-admin | **200** | JSON có message = admin. |

Kết quả phản ánh **same security concepts** với Servlet: public, authenticated, role-based authorization. Sự khác biệt của WebFlux nằm ở **WebFilter chain và cách truy cập/lưu context**, không phải “mã HTTP của reactive” riêng.

Lưu ý: một request public mang header Authorization sai vẫn có thể bị filter xử lý lỗi credential. Khi thử public, gọi **không gắn credentials** để kiểm đúng permitAll().

## 10. Kiểm thử WebFlux bằng WebTestClient

Khác với MockMvc dành cho Spring MVC, **WebTestClient** là công cụ phù hợp để test WebFlux. Nó có thể kiểm thử ứng dụng reactive mà không mở cổng thật hoặc kết nối tới server đang chạy, tùy cách bind/configure.

Tạo tệp **src/test/java/com/example/reactivesecurity/ReactiveSecurityTests.java**:

~~~java
package com.example.reactivesecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveSecurityTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointAllowsAnonymous() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("public");
    }

    @Test
    void privateEndpointRejectsAnonymous() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void privateEndpointAllowsValidBasicCredentials() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("reader", "demo-reader"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.user").isEqualTo("reader");
    }

    @Test
    void privateEndpointRejectsWrongPassword() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("reader", "wrong-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void ordinaryUserCannotCallAdmin() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("reader", "demo-reader"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanCallAdmin() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "demo-admin"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("admin");
    }

    @Test
    void undeclaredRouteIsDenied() {
        client.get().uri("/api/unknown")
            .headers(h -> h.setBasicAuth("reader", "demo-reader"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Bảy kiểm thử** xác minh đúng ẩn danh, credential sai/đúng, user thiếu role, admin đủ quyền và fallback denyAll. Đây là các test HTTP/security ở tầng ứng dụng. Cần thêm kiểm thử qua reverse proxy/TLS, quyền đối tượng, tenant và các luồng ghi dữ liệu cho hệ thống thật.

Lưu ý khi test WebFlux:

- **@AutoConfigureWebTestClient** trong Spring Boot 3.3 thuộc package **org.springframework.boot.test.autoconfigure.web.reactive**.
- **WebTestClient** thuộc **org.springframework.test.web.reactive.server**, khác với MockMvc.
- Khi muốn test method security với mock principal, có thể dùng **SecurityMockServerConfigurers.mockUser(...)** hoặc các mutator tương ứng cho JWT; phải gắn Spring Security test support vào WebTestClient phù hợp. Đừng áp dụng **SecurityMockMvcRequestPostProcessors** của Servlet vào WebTestClient.
- Mock user/test JWT làm kiểm tra **authorization** dễ hơn, nhưng không tự chứng minh việc xác minh token thật đúng; nên có các integration test phù hợp khi dùng JWT decoder thực.
- Với lỗi authorization theo dữ liệu, test phải đảm bảo **không có response hay side effect trái phép**, chứ không chỉ status 403.

## 11. Hợp đồng authn/authz dùng chung, thực thi reactive khác nhau

Một số ứng dụng dùng WebFlux nhưng vẫn kết nối cơ sở dữ liệu qua JDBC hoặc gọi thư viện bảo mật cũ chỉ cung cấp API đồng bộ. Bạn cần phân biệt:

**Kiểu dữ liệu chung** không đảm bảo **nguồn dữ liệu hoặc thuật toán nonblocking**.

Ví dụ:

- **UserDetails** là DTO/contract chứa thông tin user; bản thân nó không blocking.
- **ReactiveUserDetailsService** trả Mono<UserDetails>, nhưng nếu implementation gọi JDBC blocking trực tiếp trên event-loop thì vẫn cản luồng.
- **PasswordEncoder.matches(...)** là phương thức đồng bộ; BCrypt tiêu thụ CPU có chủ ý.
- **ReactiveAuthenticationManager** trả Mono<Authentication>, nhưng bên trong cần gọi provider/dependency được chọn đúng.
- **SecurityContext** là core type; dùng ReactiveSecurityContextHolder mới phù hợp với pipeline Reactor.

Một lỗi phổ biến:

~~~java
// Anti-pattern: repository.findByUsername(...) là lời gọi blocking.
Mono<UserDetails> user =
    Mono.just(blockingRepository.findByUsername("alice"));
~~~

**Vì sao sai?** Phương thức blocking chạy **ngay trước** khi Mono.just nhận giá trị, có thể chặn event-loop tại thời điểm tạo publisher. Không chuyển thành reactive chỉ nhờ lớp bọc Mono.

Một chiến lược khi bắt buộc tương tác API blocking (mảnh minh họa):

~~~java
Mono<UserDetails> user =
    Mono.fromCallable(() ->
            blockingRepository.findByUsername("alice"))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Ví dụ cần các import Mono và reactor.core.scheduler.Schedulers cùng repository thật. Kết quả cần xử lý null/không tìm thấy, lỗi và timeout theo hợp đồng; **boundedElastic** là cách cô lập tạm thời, không thay thế đánh giá hiệu năng, giới hạn kết nối, backpressure hay việc chuyển sang repository nonblocking.

**Không gọi block() bên trong WebFilter/Controller reactive** để “lấy Authentication cho nhanh”. Điều đó có thể chặn thread xử lý request và đi ngược mục tiêu reactive. Hãy ghép chuỗi bằng map, flatMap, switchIfEmpty và xử lý error có chủ đích.

## 12. ServerSecurityContextRepository và chuyện session

**SecurityContext** vẫn là interface chung, nhưng cơ chế lưu/khôi phục khác nhau:

- Servlet có **SecurityContextRepository** tích hợp Servlet request/session tùy cấu hình.
- WebFlux có **ServerSecurityContextRepository** kết hợp với ServerWebExchange và các WebFilter liên quan.
- Một lựa chọn reactive như **WebSessionServerSecurityContextRepository** có thể sử dụng WebSession; **NoOpServerSecurityContextRepository** không lưu context giữa các request theo cơ chế repository đó.
- Cấu hình Bearer token stateless thường cần xác thực credential ở mỗi request và cân nhắc repository/session một cách có chủ đích.

**ReactiveSecurityContextHolder không phải cơ sở dữ liệu session.** Nó giúp các bước trong publisher subscription nhìn thấy context; quyết định lưu context giữa các HTTP request là việc khác.

Nếu ứng dụng dùng HTTP Basic, cookie-session hoặc OAuth2 login, vòng đời SecurityContext có thể khác. Đừng tuyên bố **WebFlux mặc định không có session**: WebFlux vẫn hỗ trợ WebSession. Tương tự, **Mono không có nghĩa tự động stateless**.

Không lưu principal toàn cục hoặc lưu token trong static field. Nếu hệ thống cần truy xuất ngữ cảnh user qua scheduler hoặc message queue, phải thiết kế cơ chế truyền danh tính có xác thực và giới hạn quyền; không tự mong Reactor Context của request tồn tại ở một job độc lập.

## 13. CORS, CSRF, HTTP Basic và Bearer trong WebFlux

Các cơ chế giao thức vẫn quan trọng:

- **CORS**: browser áp dụng chính sách cross-origin; WebFlux có cơ chế CORS phù hợp. Browser mới thực thi hạn chế JavaScript đọc response, curl và server-to-server clients không thực thi browser SOP/CORS. Không dùng CORS thay authentication/authorization.
- **CSRF**: cần xem xét đặc biệt khi browser tự gửi cookie/credential. Spring Security WebFlux hỗ trợ bảo vệ CSRF; khi thêm POST/PUT/DELETE phải kiểm request token và chiến lược phù hợp. Không tắt CSRF theo phản xạ.
- **HTTP Basic**: credentials gửi trong Authorization, mã hóa Base64, **không phải mã hóa bí mật**. Dùng HTTPS trên môi trường thật.
- **Bearer token/JWT**: khi bật OAuth2 Resource Server reactive, server cần xác minh chữ ký hoặc introspection, issuer, thời hạn, audience/scope theo yêu cầu tin cậy. Chỉ giải mã payload JWT là không đủ.
- **Role và object authorization**: một user đã xác thực vẫn có thể bị từ chối khi thiếu role, hoặc khi không sở hữu orderId. Hai stack phải thực thi cùng các quy tắc nghiệp vụ.
- **Security headers và HTTPS**: cấu hình phù hợp với môi trường web, proxy và gateway; không giả định WebFlux tự giải quyết mọi vấn đề bảo mật.

Một mảnh cấu hình WebFlux Resource Server dùng JWT có dạng:

~~~java
// Mảnh minh họa trong SecurityWebFilterChain.
// Cần spring-boot-starter-oauth2-resource-server và cấu hình issuer/jwk tin cậy.
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
)
~~~

Đừng đưa đoạn này vào dự án HTTP Basic demo mà không thêm dependency, issuer/JWK và chính sách phù hợp. **JWT decode/xác minh** trong WebFlux có thể dùng **ReactiveJwtDecoder**; trong Servlet thường dùng **JwtDecoder**. Đây là một ví dụ khác về cùng mục tiêu nhưng API tích hợp reactive khác.

## 14. Những sai lầm thường gặp khi chuyển MVC sang WebFlux

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Import **HttpSecurity** trong WebFlux server | Cấu hình không phù hợp stack, có thể thiếu bean hoặc không áp dụng policy mong muốn. | Dùng **ServerHttpSecurity** và SecurityWebFilterChain. |
| Import **SecurityFilterChain** thay vì SecurityWebFilterChain | Tạo chain Servlet không bảo vệ WebFlux như dự định. | Dùng đúng filter chain reactive. |
| Viết **authorizeHttpRequests** trong cấu hình reactive | API DSL không khớp. | Dùng **authorizeExchange** và pathMatchers. |
| Dùng **SecurityContextHolder.getContext()** trong pipeline Reactor | Có thể không nhận đúng principal sau khi đổi thread hoặc mất context. | Dùng ReactiveSecurityContextHolder / principal injection. |
| Dùng **UserDetailsService** blocking cho đường reactive mà không có kế hoạch | Chặn event-loop khi tra user từ DB hoặc service ngoài. | Thiết kế **ReactiveUserDetailsService**, nguồn nonblocking hoặc cô lập blocking đúng cách. |
| Gọi **.block()** trong WebFilter hoặc Controller | Nguy cơ nghẽn xử lý và giảm khả năng scale. | Ghép publisher bằng map/flatMap. |
| Nhầm **WebClient** với WebFlux server | Cấu hình nhầm stack vì có dependency WebFlux làm HTTP client. | Xác định server chạy Servlet hay WebFlux qua starter và runtime. |
| Tin rằng Mono tự động bảo mật hoặc tự động stateless | Bỏ qua quyền, context persistence, CSRF, session. | Vẽ chính sách cho request, principal và tài nguyên. |
| Quên **anyExchange().denyAll()** hoặc fallback chain | Endpoint mới có thể không được phân quyền như mong muốn. | Định nghĩa default policy và test route lạ. |
| Dùng **MockMvc** để kiểm WebFlux chain | Không kiểm đúng cơ chế filter/server. | Dùng **WebTestClient** với security support. |
| Chỉ kiểm 200 mà không kiểm quyền đối tượng | User A có thể đọc dữ liệu user B dù API yêu cầu login. | Test cross-user/cross-tenant ở Service và API. |
| Trả 401/403 tùy tiện mà không xem entry point | Client không biết đăng nhập lại hay thiếu quyền, debug khó. | Kiểm ServerAuthenticationEntryPoint/ServerAccessDeniedHandler. |

Một chỉ dẫn quan trọng: **không bê nguyên filter custom của Servlet vào WebFlux**. Servlet Filter xử lý ServletRequest/ServletResponse, WebFilter xử lý ServerWebExchange và trả Mono<Void>. Nếu cần mở rộng, hiểu vị trí filter, context, error pipeline và tránh blocking.

## 15. Cách suy nghĩ khi thiết kế authentication reactive

Giả sử bạn xây hệ thống API WebFlux dùng database và một Identity Provider. Có thể phác thảo:

~~~mermaid
flowchart TD
    R["HTTP request"] --> F["SecurityWebFilterChain"]
    F --> C["AuthenticationWebFilter / cơ chế auth phù hợp"]
    C --> M["ReactiveAuthenticationManager"]
    M --> P["ReactiveUserDetailsService hoặc decoder/provider"]
    P --> A["Authentication + GrantedAuthority"]
    A --> X["SecurityContext trong Reactor Context"]
    X --> Z["AuthorizationWebFilter / Reactive authorization"]
    Z --> D{"Được phép?"}
    D -- "Có" --> H["WebFlux handler → Mono/Flux"]
    D -- "Không" --> N["Entry point / denied response"]
~~~

Đây là **sơ đồ khái niệm**, không phải thứ tự byte-for-byte của tất cả WebFilter. Ví dụ, request không có credential có thể chưa cần gọi AuthenticationManager mà đến bước authorization rồi được entry point yêu cầu xác thực. Có thể có nhiều chain, filter, decoder và handler khác nhau.

Khi thiết kế, trả lời các câu hỏi:

1. **Loại credential**: cookie-session, HTTP Basic, JWT Bearer, opaque token hay mTLS?
2. **Nguồn danh tính**: user DB, OAuth2/OIDC IdP hay service identity? Hệ thống truy xuất user có API reactive thực sự hay không?
3. **Chính sách URL và method**: endpoint nào công khai, endpoint nào yêu cầu role/scope, default deny ra sao?
4. **Quyền trên dữ liệu**: user/tenant nào được đọc, sửa, xuất, hoàn tiền một bản ghi cụ thể?
5. **Lưu và truyền context**: SecurityContext được tạo, dùng trong publisher, lưu giữa request hoặc truyền sang tác vụ độc lập thế nào?
6. **Hiệu năng**: dependency có blocking không, thời gian hash password, giới hạn kết nối, timeout và backpressure?
7. **Kiểm thử**: WebTestClient kiểm 401/403/200, test role và object, test không có side effect trái phép, test token sai/hết hạn khi dùng Resource Server.
8. **Vận hành**: HTTPS, proxy, CORS/CSRF, log không lộ secret, cập nhật bản vá Spring Security.

## 16. Bài tập tự luyện

**Bài tập 1 — Phân loại type.** Xếp Authentication, GrantedAuthority, UserDetails, SecurityContext, PasswordEncoder, HttpSecurity, ServerHttpSecurity, SecurityFilterChain và SecurityWebFilterChain vào nhóm **core dùng chung**, **Servlet-specific** hoặc **reactive-specific**. Giải thích vì sao cùng một SecurityContext có thể được truy cập qua hai cơ chế khác nhau.

**Bài tập 2 — Chuyển một cấu hình.** Chuyển một policy Servlet với GET /public permitAll, /admin hasRole("ADMIN") và default authenticated thành cấu hình ServerHttpSecurity bằng authorizeExchange. Nêu rõ chỗ phải dùng pathMatchers và anyExchange.

**Bài tập 3 — Sửa lỗi context.** Một lập trình viên dùng SecurityContextHolder.getContext().getAuthentication() bên trong service WebFlux và thỉnh thoảng nhận null sau publishOn. Hãy mô tả tại sao ThreadLocal không đảm bảo và cách chuyển sang ReactiveSecurityContextHolder hoặc Mono<Principal>.

**Bài tập 4 — Nguy cơ blocking.** Giải thích tại sao Mono.just(jdbcRepository.loadUser(...)) không làm JDBC nonblocking. Đề xuất nguồn dữ liệu reactive hoặc chiến lược cô lập blocking phù hợp, đồng thời nêu điều cần đo về tải và độ trễ.

**Bài tập 5 — Viết test.** Dùng WebTestClient để chứng minh GET /api/public trả 200 khi ẩn danh, GET /api/me trả 401 khi ẩn danh, tài khoản reader được 200 trên /api/me nhưng bị 403 ở /api/admin.

**Bài tập 6 — Phân quyền đối tượng.** Thêm endpoint GET /api/orders/{id} và giải thích tại sao authenticated() không đủ bảo đảm user A không đọc đơn user B. Viết test denied với 2 user/tenant khác nhau.

**Bài tập 7 — Chọn stack.** Một ứng dụng Spring Boot MVC đang dùng WebClient để gọi đối tác. Có cần đổi HttpSecurity thành ServerHttpSecurity không? Giải thích bằng việc xác định server stack từ runtime và dependencies.

### Checklist ghi nhớ

- **Authentication, GrantedAuthority, SecurityContext, UserDetails, PasswordEncoder**: các khái niệm/kiểu cốt lõi có thể được dùng chung.
- **HttpSecurity + SecurityFilterChain + Servlet Filter**: bộ API cho Spring MVC/Servlet.
- **ServerHttpSecurity + SecurityWebFilterChain + WebFilter**: bộ API cho Spring WebFlux.
- **AuthenticationManager** so với **ReactiveAuthenticationManager**: kết quả trực tiếp so với Mono<Authentication>.
- **UserDetailsService** so với **ReactiveUserDetailsService**: tra cứu đồng bộ so với Mono<UserDetails>.
- **SecurityContextHolder** so với **ReactiveSecurityContextHolder**: ThreadLocal/strategy phù hợp Servlet so với Reactor Context.
- **AuthenticationEntryPoint/AccessDeniedHandler** so với **ServerAuthenticationEntryPoint/ServerAccessDeniedHandler**: cùng trách nhiệm bảo mật HTTP nhưng interface khác.
- **@EnableMethodSecurity** so với **@EnableReactiveMethodSecurity** và **MockMvc** so với **WebTestClient**: phải chọn đúng stack.
- **Mono/Flux không tự xác thực, không tự phân quyền và không tự biến code blocking thành nonblocking**.
- **Dùng test âm tính** để chứng minh rule và quyền theo object/tenant thực sự hoạt động.

## Tài liệu tham khảo

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): cấu hình ServerHttpSecurity và SecurityWebFilterChain.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): @EnableReactiveMethodSecurity và Reactor Context.
- [Spring Security — Reactive WebTestClient Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): hỗ trợ security trong WebTestClient.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): WebFlux test và @AutoConfigureWebTestClient.

**Lưu ý phiên bản:** Tên API và đoạn ví dụ bên trên hướng tới Spring Boot 3.3.6 / Spring Security 6.x. Khi dùng dòng mới hơn, kiểm tra tài liệu của **đúng phiên bản trong dự án** vì cấu hình và vị trí class có thể thay đổi theo bản phát hành.

## Kết luận

Spring Security giữ chung một tập hợp hợp đồng về **danh tính, authorities, SecurityContext và mật khẩu**, nhưng cung cấp bộ API riêng cho mô hình reactive để bảo vệ các request chạy qua **WebFilter và Reactor publisher**. Hiểu cặp tương ứng **HttpSecurity/ServerHttpSecurity, SecurityFilterChain/SecurityWebFilterChain, AuthenticationManager/ReactiveAuthenticationManager, SecurityContextHolder/ReactiveSecurityContextHolder** giúp đọc kiến trúc và tránh trộn cấu hình hai stack. Dù chọn Spring MVC hay WebFlux, ứng dụng vẫn phải xác thực credential, phân quyền theo tài nguyên, bảo vệ HTTP, giữ đúng ngữ cảnh người dùng và chứng minh chính sách bằng kiểm thử.
