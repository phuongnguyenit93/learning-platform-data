# Phân biệt filter bảo mật reactive với Servlet Filter trong Spring Security

## 1. Mục tiêu bài học

Spring Security có hai mô hình tích hợp HTTP khác nhau:

- **Servlet stack (thường là Spring MVC)**: request đi qua Servlet Filter do Servlet container quản lý. Spring Security gắn vào đó bằng DelegatingFilterProxy và FilterChainProxy; cấu hình SecurityFilterChain bằng HttpSecurity.
- **Reactive stack (Spring WebFlux)**: request đi qua WebFilter trong chuỗi xử lý dựa trên Publisher. Spring Security gắn vào đó bằng WebFilterChainProxy và SecurityWebFilterChain; cấu hình bằng ServerHttpSecurity.

Hai hệ đều có thể xác thực, phân quyền, bảo vệ CSRF/CORS, thêm security headers và xử lý lỗi 401/403. Tuy nhiên, chúng **không dùng cùng filter interface, request/response type, context propagation hoặc DSL cấu hình**.

Bài học này giúp bạn:

1. Nhận ra đang chạy Servlet hay WebFlux.
2. Đọc được luồng xử lý filter ở mỗi stack.
3. Phân biệt filter HTTP thông thường với filter thuộc Spring Security.
4. Cấu hình security chain reactive đúng cách.
5. Đọc Authentication từ Reactor Context thay vì phụ thuộc ThreadLocal.
6. Di chuyển một Servlet Filter sang WebFilter mà không chặn event-loop.
7. Kiểm tra ordering, 401/403, CORS/CSRF và quyền truy cập bằng WebTestClient.
8. Tránh các sai lầm về double registration, context, blocking và filter order.

## 2. Hai kiến trúc xử lý HTTP

### 2.1. Servlet: request chạy qua FilterChain

Mô hình điển hình với Spring MVC:

~~~text
HTTP request
    |
    v
Servlet container (Tomcat/Jetty/Undertow)
    |
    v
jakarta.servlet.Filter(s)
    |
    v
DelegatingFilterProxy
    |
    v
Spring Security FilterChainProxy
    |
    v
Chọn một SecurityFilterChain phù hợp
    |
    v
Các security Filter theo thứ tự đã cấu hình
    |
    v
DispatcherServlet -> Controller
    |
    v
HTTP response quay về theo filter chain
~~~

Servlet container chịu trách nhiệm gọi Filter#doFilter. Filter có thể xử lý trước/sau chain.doFilter hoặc dừng request bằng cách không gọi chain.

Spring Security không yêu cầu từng security filter được đăng ký trực tiếp với container. DelegatingFilterProxy kết nối vòng đời Servlet container với một Filter bean do Spring quản lý; FilterChainProxy chọn security chain và chạy những filter bên trong.

### 2.2. WebFlux: request chạy qua WebFilterChain

Mô hình WebFlux (ví dụ chạy trên Reactor Netty):

~~~text
HTTP request
    |
    v
Reactive HTTP server -> HttpHandler
    |
    v
WebFilter(s) + WebFilterChain
    |
    v
Spring Security WebFilterChainProxy
    |
    v
Chọn một SecurityWebFilterChain phù hợp
    |
    v
Các security WebFilter theo thứ tự đã cấu hình
    |
    v
DispatcherHandler -> Handler/Controller/RouterFunction
    |
    v
Mono<Void> hoàn tất hoặc phát lỗi
~~~

Không có yêu cầu phải đi qua Servlet container hoặc DispatcherServlet. WebFilter nhận ServerWebExchange và trả Mono<Void>, nên quá trình có thể tiếp tục bất đồng bộ khi được subscribe.

**Điểm cốt lõi:** Servlet Filter và WebFilter cùng mang ý tưởng chặn trước/sau request, nhưng thuộc hai execution model khác nhau. Không thể thay tên interface rồi giữ nguyên toàn bộ cách quản lý thread/context.

## 3. Bảng đối chiếu quan trọng

| Khía cạnh | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| HTTP entry point | Servlet container, DispatcherServlet | HttpHandler, DispatcherHandler |
| Filter HTTP | jakarta.servlet.Filter | org.springframework.web.server.WebFilter |
| Method | void doFilter(ServletRequest, ServletResponse, FilterChain) | Mono<Void> filter(ServerWebExchange, WebFilterChain) |
| Gọi bước tiếp | chain.doFilter(request, response) | chain.filter(exchange) |
| Đối tượng request | HttpServletRequest | ServerHttpRequest qua ServerWebExchange |
| Đối tượng response | HttpServletResponse | ServerHttpResponse qua ServerWebExchange |
| Security proxy | FilterChainProxy | WebFilterChainProxy |
| Proxy bridge | DelegatingFilterProxy | Không dùng Servlet DelegatingFilterProxy |
| Security chain | SecurityFilterChain | SecurityWebFilterChain |
| Cấu hình DSL | HttpSecurity | ServerHttpSecurity |
| URL authorization | authorizeHttpRequests / requestMatchers | authorizeExchange / pathMatchers |
| Chọn chain | RequestMatcher / securityMatcher | ServerWebExchangeMatcher / securityMatcher |
| Authentication service | AuthenticationManager, AuthenticationProvider | ReactiveAuthenticationManager và các adapter reactive |
| Security context | SecurityContextHolder, thường ThreadLocal | ReactiveSecurityContextHolder, Reactor Context |
| Security context repository | SecurityContextRepository | ServerSecurityContextRepository |
| HTTP entry point khi chưa xác thực | AuthenticationEntryPoint | ServerAuthenticationEntryPoint |
| Access denied handler | AccessDeniedHandler | ServerAccessDeniedHandler |
| Kiểm thử HTTP | MockMvc hoặc HTTP client | WebTestClient |
| Threading | Thường request thread; Servlet async tùy cấu hình | Non-blocking Publisher; execution có thể đổi thread |
| Blocking I/O | Có thể phù hợp tùy thiết kế pool | Tránh block event-loop; cần reactive driver hoặc isolate blocking |

Dấu hiệu nhận biết trong code:

- Có HttpSecurity và SecurityFilterChain → đang cấu hình security theo **Servlet**.
- Có ServerHttpSecurity và SecurityWebFilterChain → đang cấu hình security theo **WebFlux**.
- Có javax.servlet.Filter từ mã rất cũ → phải xem lại package khi lên Jakarta (Spring Framework 6+ dùng jakarta.servlet).
- Có ExchangeFilterFunction của WebClient → đó là **client-side filter cho HTTP request đi ra**, không phải WebFilter bảo vệ request vào server.

## 4. Hai interface khác nhau về contract

### 4.1. Servlet Filter

Interface của Servlet API:

~~~java
import java.io.IOException;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;

public final class TraceServletFilter implements Filter {

    @Override
    public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain
    ) throws IOException, ServletException {
        long startedAt = System.nanoTime();

        try {
            chain.doFilter(request, response);
        }
        finally {
            long elapsedMs =
                (System.nanoTime() - startedAt) / 1_000_000;

            System.out.println("Servlet elapsedMs=" + elapsedMs);
        }
    }
}
~~~

Đây là ví dụ độc lập về một Servlet Filter, **không phải class để thêm vào project WebFlux ở phần 11**.

chain.doFilter tiến tới filter tiếp theo hoặc servlet cuối. Khi downstream trả về hoặc ném exception, khối finally được chạy trên call stack tương ứng. Với Servlet async, vòng đời của cả request có thể vượt ra ngoài khoảng thực thi đồng bộ này, nên muốn đo toàn bộ thời gian phải dùng AsyncListener hoặc cơ chế tương ứng.

### 4.2. Reactive WebFilter

Trong WebFlux:

~~~java
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

public final class TraceReactiveWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        return Mono.defer(() -> {
            long startedAt = System.nanoTime();

            return chain.filter(exchange)
                .doFinally(signal -> {
                    long elapsedMs =
                        (System.nanoTime() - startedAt)
                            / 1_000_000;

                    System.out.println(
                        "WebFlux " + signal
                            + " elapsedMs=" + elapsedMs
                    );
                });
        });
    }
}
~~~

Mono.defer làm cho việc đo bắt đầu khi pipeline được subscribe; doFinally theo dõi COMPLETE, ERROR hoặc CANCEL của subscription. Không dùng một khối try/finally đồng bộ quanh chain.filter(exchange) rồi tưởng đã đo xong response: method có thể chỉ trả về một Mono chưa thực thi.

### 4.3. Chặn request trong WebFilter

Nếu tự xử lý response mà không gọi chain.filter(exchange), filter có thể kết thúc pipeline:

~~~java
public Mono<Void> filter(
    ServerWebExchange exchange,
    WebFilterChain chain
) {
    if (mustReject(exchange)) {
        exchange.getResponse()
            .setStatusCode(HttpStatus.TOO_MANY_REQUESTS);

        return exchange.getResponse().setComplete();
    }

    return chain.filter(exchange);
}
~~~

Đây là snippet minh họa cần có mustReject và import HttpStatus. Với **xác thực, phân quyền hoặc rate-limit phức tạp**, ưu tiên cơ chế Spring Security và thư viện đã được kiểm thử thay vì tự viết một filter ad-hoc.

## 5. Servlet Spring Security: DelegatingFilterProxy và FilterChainProxy

Trong Servlet stack:

1. Container nhìn thấy DelegatingFilterProxy như một Servlet Filter.
2. Proxy chuyển request vào một Spring-managed Filter bean, thường có tên springSecurityFilterChain.
3. FilterChainProxy chọn SecurityFilterChain dựa trên RequestMatcher.
4. Chạy các security Filter trong chain đã được chọn.
5. Khi cho phép, request tiếp tục tới DispatcherServlet/controller.

Cấu hình ví dụ **chỉ dành cho ứng dụng Servlet/Spring MVC**:

~~~java
@Configuration
@EnableWebSecurity
public class ServletSecurityConfiguration {

    @Bean
    SecurityFilterChain servletChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Imports tiêu biểu:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.Customizer;
~~~

Khai báo Servlet SecurityFilterChain không bảo vệ WebFlux server chạy thuần Reactor Netty. Đây là hai loại bean khác nhau; Spring Boot chọn auto-configuration theo web application type và classpath.

### 5.1. Servlet Filter không phải Spring Security Filter

Một Filter do bạn đăng ký với Servlet container có thể chạy **ngoài** FilterChainProxy. Vì vậy, @Order hoặc FilterRegistrationBean không đồng nghĩa với thứ tự filter **bên trong** SecurityFilterChain.

Trong Servlet Security, chèn security Filter vào chuỗi bằng HttpSecurity.addFilterBefore, addFilterAfter hoặc addFilterAt tại vị trí thích hợp. Tránh vừa để một security Filter là container Filter vừa chèn nó vào FilterChainProxy, vì có thể dẫn đến chạy hai lần.

## 6. Reactive Spring Security: WebFilterChainProxy và SecurityWebFilterChain

Trong WebFlux, Spring Security cung cấp **WebFilterChainProxy**, một WebFilter chịu trách nhiệm chọn một SecurityWebFilterChain phù hợp. Mỗi chain gồm những WebFilter phụ trách xác thực, phân quyền, chống CSRF và các nhu cầu bảo mật khác.

Cấu hình điển hình:

~~~java
@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain security(
        ServerHttpSecurity http
    ) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Các class quan trọng:

- EnableWebFluxSecurity kích hoạt security integration cho WebFlux.
- ServerHttpSecurity là DSL reactive, tương tự về vai trò với HttpSecurity bên Servlet.
- SecurityWebFilterChain là chain được build cho reactive requests.
- WebFilterChainProxy chọn một chain dựa trên ServerWebExchangeMatcher.
- AuthenticationWebFilter và AuthorizationWebFilter tham gia các bước xác thực/phân quyền khi cơ chế tương ứng được cấu hình.

Một request chỉ đi qua **chain đầu tiên khớp matcher**, không cộng dồn toàn bộ các SecurityWebFilterChain. Nếu muốn mọi API áp một policy chung, cấu hình policy đó trong từng chain phù hợp hoặc cấu trúc matcher/chain rõ ràng.

### 6.1. Chọn chain khác với chọn quy tắc phân quyền

~~~java
http.securityMatcher(
    new PathPatternParserServerWebExchangeMatcher("/api/**")
);
~~~

securityMatcher quyết định **chain này có áp dụng cho request hay không**.

~~~java
http.authorizeExchange(auth -> auth
    .pathMatchers("/api/public").permitAll()
    .pathMatchers("/api/admin").hasRole("ADMIN")
    .anyExchange().authenticated()
);
~~~

pathMatchers quyết định **quyền truy cập bên trong chain đã chọn**.

Nhầm hai cấp này thường làm rơi request vào fallback chain hoặc vô tình bỏ qua policy. Cần test ít nhất một URL khớp mỗi chain, một URL không khớp, và các path có quyền khác nhau.

### 6.2. @Order có nhiều cấp

Trong WebFlux có ba khái niệm thứ tự:

| Cấp | Điều khiển bằng | Mục đích |
| --- | --- | --- |
| WebFilter toàn ứng dụng | @Order hoặc Ordered trên WebFilter bean | Thứ tự ở outer WebFilterChain |
| Nhiều SecurityWebFilterChain | @Order trên bean security chain | Ưu tiên chain nào được xét matcher trước |
| WebFilter bên trong security chain | SecurityWebFiltersOrder + addFilterAt/Before/After | Vị trí tương đối của một security WebFilter |

Không dùng @Order của một WebFilter bean để giả định nó nằm ngay sau bước AUTHENTICATION trong security chain. Nếu cần truy cập Authentication đã được thiết lập, hãy đặt filter đúng vị trí trong security chain hoặc thực hiện ở service/controller khi Reactor Context đã sẵn sàng.

## 7. SecurityContextHolder so với ReactiveSecurityContextHolder

Đây là điểm gây lỗi phổ biến nhất khi chuyển từ Spring MVC sang WebFlux.

### 7.1. Servlet: SecurityContextHolder

Một ứng dụng Servlet thông thường có thể đọc:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext()
        .getAuthentication();

String username = authentication.getName();
~~~

Mặc định, SecurityContextHolder sử dụng chiến lược ThreadLocal; Spring Security có cơ chế gắn và dọn context theo request. Khi code chuyển thread hoặc sử dụng Servlet async, vẫn phải xử lý context propagation đúng, không mặc định ThreadLocal tự đi qua mọi executor.

### 7.2. WebFlux: Reactor Context

Reactive pipeline có thể chạy trên nhiều thread. Spring Security lưu SecurityContext vào **Reactor Context** để đi theo subscription chứ không dựa đơn thuần vào ThreadLocal.

Cách đọc đúng:

~~~java
Mono<String> username =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
~~~

Trong một WebFlux controller:

~~~java
@GetMapping("/me")
public Mono<String> me() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
~~~

Không dùng SecurityContextHolder.getContext() trong WebFlux để suy ra người dùng hiện tại. Nó có thể rỗng hoặc mang giá trị không gắn với subscription đang xử lý.

### 7.3. Gắn context trong unit test reactive

Ví dụ độc lập:

~~~java
Authentication auth =
    new TestingAuthenticationToken(
        "learner",
        "not-used",
        "ROLE_USER"
    );

Mono<String> name =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth)
        );

StepVerifier.create(name)
    .expectNext("learner")
    .verifyComplete();
~~~

Đây là snippet cần các import từ Spring Security, Reactor và reactor-test. contextWrite gắn SecurityContext với subscription ở đúng đoạn pipeline.

### 7.4. Không làm rơi Context

Các lỗi thường gặp:

- Tạo một subscribe() thủ công trong filter rồi return Mono.empty().
- Chuyển công việc ra CompletableFuture/raw Thread mà không có cơ chế context propagation.
- Dùng ThreadLocal riêng làm nơi lưu danh tính user cho mọi request.
- Cache một Mono chứa context của một user rồi tái sử dụng chéo người dùng.
- Lấy Authentication ở lúc khởi tạo singleton bean thay vì trong request pipeline.

Cần composition bằng flatMap, map, defer và contextWrite đúng vị trí. Khi phải dùng bridge sang thư viện bất đồng bộ khác, đánh giá context propagation và kiểm thử với nhiều request chạy đồng thời.

## 8. Đặt custom security WebFilter đúng chỗ

Khi cần một bước bảo mật riêng, có thể thêm WebFilter vào SecurityWebFilterChain:

~~~java
@Bean
SecurityWebFilterChain security(
    ServerHttpSecurity http
) {
    WebFilter audit = (exchange, chain) ->
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .doOnNext(auth ->
                logger.debug(
                    "Authenticated principal={}",
                    auth.getName()
                )
            )
            .then(chain.filter(exchange));

    return http
        .authorizeExchange(auth -> auth
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .addFilterAfter(
            audit,
            SecurityWebFiltersOrder.AUTHENTICATION
        )
        .build();
}
~~~

Đây là **snippet minh họa**: cần logger và các import, không thay thế lớp cấu hình hoàn chỉnh ở phần 11. Audit ở đây nằm trong security chain, sau vị trí AUTHENTICATION. Nó không phải bean WebFilter toàn cục.

Trong production:

- Không log token, mật khẩu hoặc thông tin nhạy cảm của principal.
- Không tự tạo Authentication với trạng thái authenticated=true chỉ vì thấy một header tùy ý.
- Nếu cần authentication tùy chỉnh, dùng ReactiveAuthenticationManager, ServerAuthenticationConverter/AuthenticationWebFilter và error handling chuẩn.
- Nếu cần authorization, dùng authorizeExchange/ReactiveAuthorizationManager hoặc reactive method security thay vì một custom if tùy tiện.
- Không đăng ký cùng một filter vừa là global WebFilter bean vừa qua addFilterAt/After; filter có thể chạy hai lần.

### 8.1. Custom global WebFilter là một khái niệm khác

Một WebFilter bean toàn cục hữu ích cho request ID, logging, CORS, metrics hoặc giới hạn cơ bản. Nó bao quanh handler theo order nhưng **không mặc nhiên chạy sau Spring Security xác thực**.

Muốn đọc Authentication đã xác thực từ filter, không giả định context tồn tại ở một @Order bất kỳ. Dùng custom security WebFilter đúng order hoặc xử lý ở lớp service với ReactiveSecurityContextHolder.

### 8.2. WebFilter khác HandlerFilterFunction

Trong WebFlux.fn, **HandlerFilterFunction** chỉ áp dụng trong một RouterFunction/handler chức năng được ghép filter đó. **WebFilter** thuộc WebFlux HTTP pipeline và có thể áp dụng rộng hơn cho nhiều route. Không dùng HandlerFilterFunction để thay thế toàn bộ bảo vệ của Spring Security trên mọi route.

## 9. Authentication, authorization, CSRF, CORS và lỗi

### 9.1. Authentication và authorization

- **Authentication** trả lời "Ai đang gọi?".
- **Authorization** trả lời "Người gọi có được phép truy cập resource này không?".

Trong reactive stack, authentication có thể được thực hiện bất đồng bộ qua ReactiveAuthenticationManager, ReactiveUserDetailsService hoặc resource server JWT support. Authorization dùng Authentication trong Reactor Context và policy của security chain.

HTTP Basic chỉ là một phương thức demo. Trong production, cân nhắc OAuth 2.0 Resource Server/JWT, OIDC, session login hoặc cơ chế phù hợp threat model.

### 9.2. HTTP 401 khác 403

- **401 Unauthorized**: thường xảy ra khi request cần xác thực nhưng chưa có credential hợp lệ; server có thể trả WWW-Authenticate.
- **403 Forbidden**: principal đã xác thực nhưng không đủ quyền truy cập, hoặc request bị từ chối bởi một quy tắc bảo vệ khác như CSRF.

Không giả định mọi request bị chặn đều là 403. Status phụ thuộc authentication entrypoint, access-denied handler và policy đang cấu hình.

### 9.3. CSRF

Spring Security **bật CSRF protection mặc định** cho các method không an toàn, đặc biệt quan trọng với ứng dụng browser sử dụng cookie/session.

Đối với API stateless sử dụng bearer token gửi chủ động qua Authorization header, có thể thiết kế CSRF policy khác sau khi phân tích các credential được browser tự động gắn vào request. Không vô hiệu hóa CSRF một cách mặc định chỉ vì ứng dụng dùng WebFlux.

Trong bài demo ở phần 11 chỉ dùng GET nên không cần tắt CSRF. Nếu thêm POST/PUT/PATCH/DELETE, cần bổ sung CSRF token hoặc điều chỉnh đúng theo thiết kế xác thực của hệ thống.

### 9.4. CORS

Browser gửi preflight OPTIONS trước một số cross-origin request. Preflight thường không chứa cookie đăng nhập. Nếu bảo mật chặn preflight trước khi CORS xử lý, browser có thể báo CORS error thay vì lỗi xác thực rõ ràng.

WebFlux cung cấp CorsWebFilter và cấu hình CORS ở WebFlux; Spring Security có cơ chế tích hợp CORS theo cấu hình. Hãy xử lý CORS đúng trước authentication và kiểm tra allowed origins, headers, methods, credentials.

Không dùng wildcard origin cùng credentialed requests. CORS không thay thế authentication hoặc authorization.

### 9.5. Security headers

Spring Security có cấu hình mặc định cho một số HTTP security headers, ví dụ nosniff, cache headers và frame options. Khi tự viết filter hoặc route permitAll, không nên vô tình bỏ qua các security defaults. **permitAll** cho phép truy cập URL nhưng request vẫn đi qua security chain; bypass toàn bộ security chain là hành vi khác.

### 9.6. Exception handling

Servlet dùng AuthenticationEntryPoint và AccessDeniedHandler; reactive dùng ServerAuthenticationEntryPoint và ServerAccessDeniedHandler. WebFlux có thể tạo response bất đồng bộ, nên lỗi sau khi response đã commit không thể tự nhiên đổi thành response 401/403 mới.

Không nuốt AccessDeniedException hoặc AuthenticationException bằng onErrorResume(... -> Mono.empty()) khi điều đó có thể làm mất response bảo mật mong đợi.

## 10. Những lỗi khi chuyển Servlet Filter sang WebFlux

### 10.1. Copy nguyên Servlet Filter vào WebFlux

Sai về runtime:

~~~java
@Component
public class LegacySecurityFilter implements jakarta.servlet.Filter {
    // ...
}
~~~

Một Filter như vậy không nằm trong WebFlux WebFilterChain thuần reactive. Spring Boot dùng Netty với WebFlux sẽ không gọi Filter#doFilter như Servlet container. Hãy triển khai WebFilter nếu muốn filter request vào WebFlux.

### 10.2. Block event-loop

Không làm trong WebFilter:

~~~java
public Mono<Void> filter(
    ServerWebExchange exchange,
    WebFilterChain chain
) {
    User user = userRepository.findBlockingUser(); // blocking I/O
    Thread.sleep(100);
    return chain.filter(exchange);
}
~~~

Đây là ví dụ **sai có chủ đích**; code còn cần xử lý checked exception. Dùng repository/driver reactive:

~~~java
return reactiveUserRepository.findById(userId)
    .flatMap(user -> authorize(user, exchange))
    .then(chain.filter(exchange));
~~~

Nếu phải tích hợp thư viện blocking tạm thời, có thể cô lập với Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic()) và giới hạn concurrency; giải pháp này không biến I/O blocking thành non-blocking và không thay thế việc kiểm soát tải.

### 10.3. Tự subscribe trong filter

Sai:

~~~java
public Mono<Void> filter(
    ServerWebExchange exchange,
    WebFilterChain chain
) {
    verifyCredential(exchange).subscribe();
    return chain.filter(exchange);
}
~~~

Việc xác thực chạy ngoài chain và có thể hoàn tất **sau** khi request đã được cho qua. Error/cancel cũng không được nối vào lifecycle chính.

Đúng về composition:

~~~java
return verifyCredential(exchange)
    .then(chain.filter(exchange));
~~~

Đây là snippet minh họa, cần đảm bảo verifyCredential thực sự phát lỗi hoặc trả kết quả từ chối khi credential không hợp lệ. Trong Spring Security nên ưu tiên AuthenticationWebFilter/ReactiveAuthenticationManager hơn tự xây chain xác thực.

### 10.4. Thử đọc Servlet HttpSession

Trong WebFlux hãy dùng ServerWebExchange.getSession() (Mono<WebSession>) khi cần WebSession. Spring Security reactive có ServerSecurityContextRepository. Không giả định có HttpServletRequest, HttpSession hoặc ServletContext trên một Netty WebFlux server.

### 10.5. Đặt cấu hình đúng kiểu nhưng sai stack

Một SecurityFilterChain(HttpSecurity) không thay thế SecurityWebFilterChain(ServerHttpSecurity). Khi có cả Spring MVC starter và WebFlux starter, Spring Boot thường chọn **Servlet MVC** theo mặc định; thêm WebFlux để dùng WebClient không đồng nghĩa server của bạn là reactive.

Kiểm tra dependency và loại web application thật. Không dùng cách "thêm cả hai starter" để thử sửa lỗi filter.

## 11. Dự án Java 17+ chạy được: Spring WebFlux Security

Ví dụ dùng **Spring Boot 4.1.2**, Java 17+, Spring WebFlux và Spring Security. Mục đích là chứng minh:

- Chain reactive được chọn theo /api/**.
- Request GET /api/public được permitAll.
- GET /api/me cần authentication.
- GET /api/admin cần ROLE_ADMIN.
- Username đọc từ Reactor Context.
- Global WebFilter dùng để đo thời gian, không thay Spring Security filter.
- WebTestClient xác minh status và response.

Dự án dùng HTTP Basic với user demo và {noop} password **chỉ cho môi trường học tập**. Production phải dùng password hash và secret management phù hợp, HTTPS, authentication thật, rate limits và monitoring.

### 11.1. Cấu trúc

~~~text
reactive-security-filters-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/securityfilters/
    │       ├── SecurityFiltersApplication.java
    │       ├── SecurityConfiguration.java
    │       ├── ApiController.java
    │       └── RequestMetricsWebFilter.java
    └── test/
        └── java/com/example/securityfilters/
            └── SecurityIntegrationTest.java
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactive-security-filters-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

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
            <artifactId>spring-boot-starter-webflux-test</artifactId>
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

### 11.3. SecurityFiltersApplication.java

~~~java
package com.example.securityfilters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityFiltersApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            SecurityFiltersApplication.class,
            args
        );
    }
}
~~~

### 11.4. SecurityConfiguration.java

~~~java
package com.example.securityfilters;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http
    ) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/api/**"
                )
            )
            .authorizeExchange(auth -> auth
                .pathMatchers(
                    HttpMethod.GET,
                    "/api/public"
                ).permitAll()
                .pathMatchers(
                    HttpMethod.GET,
                    "/api/admin"
                ).hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackSecurity(
        ServerHttpSecurity http
    ) {
        return http
            .authorizeExchange(auth -> auth
                .anyExchange().denyAll()
            )
            .build();
    }

    @Bean
    ReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo-password")
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}demo-admin")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(
            learner,
            admin
        );
    }
}
~~~

Giải thích:

1. @EnableWebFluxSecurity cấu hình tích hợp Spring Security WebFlux.
2. apiSecurity có @Order(1), chỉ match URL /api/**.
3. Trong apiSecurity, /api/public được cho phép công khai; /api/admin yêu cầu ROLE_ADMIN; các /api/** còn lại yêu cầu đăng nhập.
4. fallbackSecurity với @Order(2) denyAll những request không thuộc /api/**.
5. HTTP Basic cung cấp cơ chế kiểm tra credential cho demo.
6. UserDetails in-memory chỉ phục vụ unit/integration test; password {noop} không mã hóa và tuyệt đối không dùng ở production.
7. CSRF không bị disable; ứng dụng demo chỉ cung cấp GET.

Chú ý: hasRole("ADMIN") tương ứng authority ROLE_ADMIN. Nếu dùng hasAuthority("ADMIN") thì authority phải khớp đúng chuỗi ADMIN; không trộn hai cách mà không hiểu prefix ROLE_.

### 11.5. ApiController.java

~~~java
package com.example.securityfilters;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/public")
    public Mono<String> publicMessage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }

    @GetMapping("/admin")
    public Mono<String> adminMessage() {
        return Mono.just("admin-only");
    }
}
~~~

Tại endpoint /api/me, Authentication được đọc từ Reactor Context trong pipeline Mono. Không dùng SecurityContextHolder ThreadLocal của Servlet.

### 11.6. RequestMetricsWebFilter.java

~~~java
package com.example.securityfilters;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestMetricsWebFilter implements WebFilter {

    private static final Logger log =
        LoggerFactory.getLogger(
            RequestMetricsWebFilter.class
        );

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        return Mono.defer(() -> {
            long startedAt = System.nanoTime();
            String path =
                exchange.getRequest().getPath().value();

            return chain.filter(exchange)
                .doFinally(signal -> {
                    long elapsedMs =
                        (System.nanoTime() - startedAt)
                            / 1_000_000;

                    log.info(
                        "path={} signal={} elapsedMs={}",
                        path,
                        signal,
                        elapsedMs
                    );
                });
        });
    }
}
~~~

Filter này đo thời gian xử lý HTTP và chạy như một WebFilter toàn cục. Nó **không tự xác thực user** và không truy cập Reactor SecurityContext. Không log Authorization header, password, raw body hoặc thông tin nhạy cảm.

### 11.7. SecurityIntegrationTest.java

~~~java
package com.example.securityfilters;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webflux.test.autoconfigure.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class SecurityIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointAllowsAnonymous() {
        client.get()
            .uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void privateEndpointRejectsAnonymousWith401() {
        client.get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedLearnerReadsTheirIdentity() {
        client.get()
            .uri("/api/me")
            .headers(headers ->
                headers.setBasicAuth(
                    "learner",
                    "demo-password"
                )
            )
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("learner");
    }

    @Test
    void learnerCannotAccessAdminEndpoint() {
        client.get()
            .uri("/api/admin")
            .headers(headers ->
                headers.setBasicAuth(
                    "learner",
                    "demo-password"
                )
            )
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdminEndpoint() {
        client.get()
            .uri("/api/admin")
            .headers(headers ->
                headers.setBasicAuth(
                    "admin",
                    "demo-admin"
                )
            )
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo(
                "admin-only"
            );
    }
}
~~~

Tất cả tests dùng HTTP thật trên port ngẫu nhiên do SpringBootTest tạo. Điều này xác minh reactive security chain và HTTP Basic integration end-to-end.

WebTestClient còn hỗ trợ mockUser(), mockJwt(), csrf() qua Spring Security test utilities khi bindToApplicationContext hoặc MockServer exchange đã được áp dụng springSecurity(). Trong test HTTP end-to-end ở đây, truyền Basic auth credential thật tới server là cách đơn giản nhất để kiểm tra filter chain.

### 11.8. Chạy dự án

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Mở terminal khác:

~~~bash
curl -i http://localhost:8080/api/public
~~~

Kết quả kỳ vọng: HTTP 200, body public.

~~~bash
curl -i http://localhost:8080/api/me
~~~

Kết quả kỳ vọng: HTTP 401 và challenge HTTP Basic.

~~~bash
curl -i -u learner:demo-password \
  http://localhost:8080/api/me
~~~

Kết quả kỳ vọng: HTTP 200, body learner.

~~~bash
curl -i -u learner:demo-password \
  http://localhost:8080/api/admin
~~~

Kết quả kỳ vọng: HTTP 403 do learner không có ROLE_ADMIN.

~~~bash
curl -i -u admin:demo-admin \
  http://localhost:8080/api/admin
~~~

Kết quả kỳ vọng: HTTP 200, body admin-only.

Các header bổ sung và log có thể khác theo cấu hình. Ví dụ cố ý không triển khai ghi dữ liệu bằng POST nên không cần xử lý token CSRF trong các lệnh curl này.

## 12. Kiểm thử security WebFilter mà không khởi động server thật

Khi chỉ cần test một SecurityWebFilterChain hoặc controller theo slice, có thể dùng WebTestClient bindToApplicationContext với Spring Security test support:

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(
        SecurityMockServerConfigurers.springSecurity()
    )
    .configureClient()
    .build();
~~~

Sau đó:

~~~java
client.mutateWith(
        SecurityMockServerConfigurers
            .mockUser()
            .roles("ADMIN")
    )
    .get()
    .uri("/api/admin")
    .exchange()
    .expectStatus().isOk();
~~~

Đây là snippet cần context test hợp lệ và import SecurityMockServerConfigurers. **mockUser() không chạy cơ chế xác thực Basic thật**; nó chèn Authentication giả vào test pipeline. Dùng mockUser để kiểm tra authorization, và dùng HTTP credential thực trong integration test khi cần kiểm tra authentication.

Thêm một số test quan trọng:

- Anonymous không vào được route cần authentication.
- User thường không vào được admin.
- Admin vào được route được phép.
- Matcher /api/** chọn đúng chain, URL ngoài pattern rơi vào fallback chain.
- Thứ tự rule cụ thể trước anyExchange được giữ.
- Custom filter không bị đăng ký hai lần.
- POST cần CSRF có hoặc không có token theo đúng policy.
- OPTIONS preflight được xử lý theo CORS config.
- Authentication trong Mono không bị mất khi publishOn/flatMap.

## 13. Multi-chain và các bẫy về matcher/order

Một WebFlux app có thể có chain cho API và chain cho web pages:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher(
                "/api/**"
            )
        )
        .authorizeExchange(auth -> auth
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain web(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/", "/login").permitAll()
            .anyExchange().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

**Chỉ một chain được chọn cho mỗi request.** Một request /api/orders khớp api, không chạy thêm chain web dù chain web có matcher catch-all. Nếu api chain không có fallback rule phù hợp, có thể có đường đi ngoài dự kiến. Vì vậy dùng anyExchange ở cuối mỗi chain.

Một bean SecurityWebFilterChain được đánh dấu @Order nhưng bạn lại dùng @Order trên global WebFilter không sửa thứ tự chọn chain. Hai cấp đó độc lập.

### 13.1. Nếu cần chèn vào vị trí authentication

Dùng các method của ServerHttpSecurity:

~~~java
http.addFilterBefore(
    customFilter,
    SecurityWebFiltersOrder.AUTHORIZATION
);
~~~

hoặc:

~~~java
http.addFilterAfter(
    customFilter,
    SecurityWebFiltersOrder.AUTHENTICATION
);
~~~

Đây là snippet: customFilter phải là một WebFilter và chỉ đăng ký tại một nơi. Cần phân tích mục đích trước khi chọn thứ tự: filter cần identity đã xác thực phải đặt sau bước authentication; filter quyết định authorization nên tích hợp với cơ chế authorization chuẩn thay vì tùy tiện chen vào chain.

## 14. Debug và quan sát đúng chuỗi security

Các bước khi gặp 401/403 khó hiểu:

1. Xác nhận ứng dụng thực sự là WebFlux hay Servlet.
2. Tìm bean SecurityWebFilterChain hay SecurityFilterChain đang được áp dụng.
3. Xác nhận matcher nào chọn chain; kiểm tra @Order.
4. Kiểm tra authorizeExchange và thứ tự pathMatchers.
5. Kiểm tra authentication method (Basic, bearer, session).
6. Kiểm tra ReactiveUserDetailsService hoặc ReactiveAuthenticationManager.
7. Kiểm tra Reactor Context trong Mono/Flux; không suy luận từ ThreadLocal.
8. Xem security CSRF/CORS và preflight behavior.
9. Kiểm tra global WebFilter có chạy trước hoặc sau security proxy không.
10. Kiểm tra response đã commit trước khi exception handler cố đổi status chưa.

Chỉ bật debug log cục bộ trong môi trường được kiểm soát:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Không bật body/token logging bừa bãi; không ghi mật khẩu hoặc Authorization header.

### 14.1. Quan sát order filter

Spring Boot WebFlux auto-configure WebFilterChainProxy của Spring Security ở order khoảng -100. Một WebFilter bean có @Order(Ordered.HIGHEST_PRECEDENCE) thường chạy ngoài/bên ngoài proxy này, **không phải một security filter phía sau AuthenticationWebFilter**.

Nếu muốn đo toàn bộ request, global WebFilter là phù hợp. Nếu muốn kiểm tra principal đã xác thực, dùng custom security WebFilter đúng vị trí, controller hoặc service reactive.

### 14.2. Có thể dùng WebFlux mà vẫn thấy Servlet dependency?

Một project có thể có nhiều thư viện liên quan Servlet trong dependency tree nhưng ứng dụng thực tế chọn reactive web application type. Ngược lại, khi có cả Spring MVC và WebFlux starters, Spring Boot thường ưu tiên MVC. Xác minh web application type thật thay vì suy luận chỉ từ một dependency.

## 15. So sánh cách viết cùng một yêu cầu bảo mật

Yêu cầu: mọi request /admin/** cần vai trò ADMIN, /health công khai, những URL còn lại yêu cầu đăng nhập.

### 15.1. Servlet

~~~java
@Bean
SecurityFilterChain servletSecurity(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/health").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

### 15.2. Reactive

~~~java
@Bean
SecurityWebFilterChain reactiveSecurity(
    ServerHttpSecurity http
) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/health").permitAll()
            .pathMatchers("/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Hai đoạn có ý định authorization tương tự nhưng **kiểu bean, DSL và runtime không giống nhau**. Đừng copy lời giải Servlet vào WebFlux rồi ép kiểu hoặc thêm Servlet adapter tùy tiện.

## 16. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| jakarta.servlet.Filter không chạy trên Netty | WebFlux không dùng Servlet filter chain | Triển khai WebFilter |
| Bean SecurityFilterChain không bảo vệ request WebFlux | Cấu hình đúng API nhưng sai stack | Dùng SecurityWebFilterChain và ServerHttpSecurity |
| Bean SecurityWebFilterChain không ảnh hưởng MVC | Ứng dụng chạy Servlet stack | Dùng SecurityFilterChain và HttpSecurity |
| SecurityContextHolder trả null trong Mono | Dùng ThreadLocal thay cho Reactor Context | Dùng ReactiveSecurityContextHolder |
| Custom filter không thấy principal | Chạy quá sớm hoặc ngoài security chain | Chèn đúng SecurityWebFiltersOrder |
| Filter chạy hai lần | Vừa global @Component vừa addFilterAt/After | Chỉ đăng ký một lần |
| Request được phép nhưng trả 404 | Security cho qua nhưng controller/route không tồn tại | Kiểm tra handler mapping |
| User thường vào được admin | Matcher/order sai hoặc thiếu hasRole | Test ROLE_ADMIN và rule |
| 401 khi browser OPTIONS preflight | CORS bị xử lý sau bảo mật | Cấu hình CORS trước security đúng cách |
| 403 với POST dùng cookie | CSRF token thiếu | Gửi token hoặc cấu hình policy phù hợp |
| WebFilter chậm làm các request khác chậm | Blocking I/O trên event-loop | Dùng reactive API hoặc isolate blocking có giới hạn |
| Exception bị mất | Tự subscribe bên ngoài pipeline | Return composition của Mono |
| Audit log không ghi sau response | Dùng try/finally đồng bộ sai lifecycle | Dùng doFinally |
| Filter order lạ | Nhầm @Order bean với SecurityWebFiltersOrder | Phân biệt ba cấp ordering |
| Bỏ qua bảo mật ở /api/** | securityMatcher không khớp và fallback thiếu | Kiểm tra chain matcher/fallback |
| /api/** chạy sai chain | @Order ưu tiên wildcard trước pattern cụ thể | Đặt matcher cụ thể và order cao hơn |
| User context lẫn nhau | Cache/context propagation sai | Không lưu Authentication request vào singleton/ThreadLocal |
| Thêm cả spring-boot-starter-web và webflux mà filter không chạy | Boot chọn MVC làm server mặc định | Chọn stack chủ đích và kiểm tra web application type |
| 403 bị đổi thành 200 | onErrorResume nuốt access-denied error | Để Spring Security xử lý hoặc map lỗi có chủ đích |
| Lỗi 401/403 chỉ xuất hiện trên server thật | Test mockUser không đi qua auth thật | Bổ sung integration test với Basic/JWT/cookie |

## 17. Checklist chuyển từ Servlet sang WebFlux

- [ ] Xác nhận server chạy WebFlux, không phải MVC.
- [ ] Thay jakarta.servlet.Filter bằng WebFilter khi cần HTTP filter reactive.
- [ ] Thay SecurityFilterChain/HttpSecurity bằng SecurityWebFilterChain/ServerHttpSecurity.
- [ ] Thay DelegatingFilterProxy/FilterChainProxy theo kiến trúc WebFilterChainProxy.
- [ ] Thay RequestMatcher bằng ServerWebExchangeMatcher ở mức chọn chain.
- [ ] Dùng authorizeExchange và pathMatchers, phân biệt securityMatcher.
- [ ] Kiểm tra @Order giữa các security chain.
- [ ] Đặt custom security WebFilter bằng SecurityWebFiltersOrder phù hợp.
- [ ] Không double-register global WebFilter và internal security filter.
- [ ] Thay SecurityContextHolder ThreadLocal bằng ReactiveSecurityContextHolder.
- [ ] Không block, sleep hoặc gọi subscribe thủ công trên request pipeline.
- [ ] Chuyển authentication repository/service sang API reactive.
- [ ] Kiểm tra 401, 403, CSRF, CORS và security headers.
- [ ] Kiểm tra test mockUser khác test authentication HTTP thật.
- [ ] Bảo vệ mọi route ngoài các URL được permitAll rõ ràng.
- [ ] Kiểm tra resource server/session policy khi triển khai thực tế.
- [ ] Không lưu password demo {noop} trong production.
- [ ] Viết integration test và log/metrics không chứa secret.

## 18. Bài tập thực hành

**Bài 1 — Nhận diện stack:** Viết bảng xác định Filter/HttpSecurity và WebFilter/ServerHttpSecurity tương ứng với MVC hay WebFlux.

**Bài 2 — Global WebFilter:** Tạo một WebFilter đo thời gian bằng Mono.defer và doFinally. Kiểm tra log khi request trả 200, 401 hoặc 403.

**Bài 3 — SecurityWebFilterChain:** Bảo vệ /api/** bằng HTTP Basic và cho phép /api/public. Test anonymous và authenticated.

**Bài 4 — Roles:** Tạo USER và ADMIN, giới hạn /api/admin với hasRole("ADMIN"). Kiểm thử 200 và 403.

**Bài 5 — Reactor Context:** Trong controller trả Mono<String>, đọc username bằng ReactiveSecurityContextHolder.

**Bài 6 — Multi-chain:** Cấu hình @Order(1) cho /api/** và @Order(2) cho mọi URL khác. Kiểm tra chain nào được chọn.

**Bài 7 — Custom security filter:** Đặt một audit WebFilter sau AUTHENTICATION và xác minh principal được ghi nhận đúng, không log secret.

**Bài 8 — Không block:** Thay một lookup blocking trong filter bằng ReactiveUserDetailsService hoặc một reactive service; kiểm tra pipeline không có block().

**Bài 9 — CSRF:** Thêm endpoint POST dựa vào cookie session, thử thiếu và có CSRF token. Giải thích vì sao WebFlux không tự làm mất nguy cơ CSRF.

**Bài 10 — CORS:** Tạo preflight OPTIONS cho request cross-origin có Authorization. Cấu hình CorsWebFilter đúng origin/method/header.

**Bài 11 — Test mockUser:** Dùng WebTestClient mutateWith(mockUser()) để kiểm tra quyền truy cập; so sánh với integration test HTTP Basic.

**Bài 12 — Sai stack:** Thêm một jakarta.servlet.Filter vào một WebFlux-Netty demo và xác minh nó không trở thành một WebFilter trong pipeline.

## 19. Ghi nhớ

**Servlet security filter ≠ Reactive security filter.** Servlet dùng jakarta.servlet.Filter, FilterChainProxy, SecurityFilterChain và HttpSecurity. WebFlux dùng org.springframework.web.server.WebFilter, WebFilterChainProxy, SecurityWebFilterChain và ServerHttpSecurity.

WebFlux security không dựa vào Servlet DelegatingFilterProxy. Mỗi request được ghép với **một SecurityWebFilterChain phù hợp**. securityMatcher chọn chain; pathMatchers/authorizeExchange quyết định quyền trong chain. Global @Order của WebFilter, @Order của security chain và SecurityWebFiltersOrder là ba cấp khác nhau.

Trong reactive pipeline, Authentication thuộc **Reactor Context**. Đọc bằng ReactiveSecurityContextHolder; không dùng ThreadLocal Servlet như một giả định toàn cục. Luôn return Mono/Flux thay vì block() hoặc tự subscribe(). CSRF, CORS, security headers, 401/403 và authorization vẫn quan trọng như ở Servlet.

## 20. Tài liệu tham khảo

- Spring Security Reference — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security Reference — Getting Started with WebFlux: https://docs.spring.io/spring-security/reference/reactive/getting-started.html
- Spring Security Reference — Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security Reference — Servlet Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security Reference — Reactive CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security Reference — Reactive Web Tests: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Spring Security API — ReactiveSecurityContextHolder: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security API — WebFilterChainProxy: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/server/WebFilterChainProxy.html
- Spring Framework API — WebFilter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilter.html
- Spring Framework API — WebFilterChain: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebFilterChain.html
- Spring Boot Reference — Security: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- Spring Boot Reference — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Boot Reference — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Security API — ServerHttpSecurity: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/config/web/server/ServerHttpSecurity.html
