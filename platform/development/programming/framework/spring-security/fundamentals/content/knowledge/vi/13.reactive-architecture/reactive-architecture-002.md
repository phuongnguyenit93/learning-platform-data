# WebFilter, WebFilterChainProxy và SecurityWebFilterChain trong Spring Security WebFlux

## 1. Bức tranh tổng thể

Trong ứng dụng **Spring WebFlux**, việc chặn, xử lý và bảo vệ HTTP request diễn ra trên pipeline reactive. Ba thành phần thường bị nhầm lẫn có vai trò khác nhau:

| Thành phần | Loại | Nhiệm vụ chính |
| --- | --- | --- |
| **WebFilter** | Interface của Spring WebFlux (org.springframework.web.server.WebFilter) | Can thiệp trước/sau quá trình xử lý một ServerWebExchange; là đơn vị thực thi filter. |
| **WebFilterChainProxy** | Một WebFilter do Spring Security cung cấp (org.springframework.security.web.server.WebFilterChainProxy) | Là điểm đi vào Spring Security trong pipeline WebFlux; nhận các SecurityWebFilterChain, chọn chuỗi phù hợp với request rồi chạy các security filter của chuỗi đó. |
| **SecurityWebFilterChain** | Interface của Spring Security reactive (org.springframework.security.web.server.SecurityWebFilterChain) | Mô tả *điều kiện áp dụng* và *tập WebFilter bảo mật* tương ứng với điều kiện đó; thường được tạo bởi ServerHttpSecurity.build(). |

**Điểm cần nhớ:** WebFilterChainProxy **là một WebFilter**; SecurityWebFilterChain **không phải một WebFilter đơn lẻ**. SecurityWebFilterChain là cấu hình/tập các filter được proxy lựa chọn. Một request thông thường đi qua **một SecurityWebFilterChain khớp đầu tiên**, dù có nhiều chain được đăng ký.

### Sơ đồ xử lý khái niệm

~~~text
HTTP request
    |
    v
Spring WebFlux (ServerWebExchange)
    |
    v
Chuỗi WebFilter toàn cục (có thể có filter của ứng dụng)
    |
    v
WebFilterChainProxy  <-- cũng là một WebFilter trong chuỗi toàn cục
    |
    +--> thử SecurityWebFilterChain theo thứ tự ưu tiên
    |        |
    |        +--> chain đầu tiên có matcher khớp
    |                 |
    |                 v
    |             WebFilter bảo mật của chain đó
    |             (xác thực, security context, phân quyền, ...)
    |                 |
    +-----------------+--> Nếu được phép tiếp tục:
                              WebFilter còn lại -> WebHandler/Controller
    |
    +--> Nếu bị từ chối: xử lý 401/403/redirect theo cấu hình;
         controller không được gọi
~~~

Sơ đồ lược bỏ một số lớp adapter/handler để tập trung vào quan hệ giữa ba thành phần. Các WebFilter toàn cục có thể nằm trước hoặc sau proxy tùy thứ tự đăng ký.

## 2. WebFilter: điểm mở rộng của Spring WebFlux

Hợp đồng cơ bản của Spring WebFlux:

~~~java
public interface WebFilter {
    Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
}
~~~

- **ServerWebExchange** bao gồm request, response, attributes và ngữ cảnh HTTP đang được xử lý.
- **WebFilterChain** biểu diễn phần xử lý tiếp theo. Gọi **chain.filter(exchange)** để chuyển request sang filter/handler kế tiếp.
- **Mono<Void>** biểu diễn quá trình hoàn tất *bất đồng bộ*. Hàm filter thường trả về một publisher để WebFlux đăng ký thực thi. Không nên coi lệnh trả về publisher là thời điểm request đã xử lý xong.
- Filter có thể đọc header, gắn correlation ID, bổ sung response header, thực thi kiểm tra hoặc quan sát kết quả. Nếu chủ đích kết thúc request, filter có thể trả về publisher hoàn tất mà không gọi chain.filter(exchange); cần tự chịu trách nhiệm về response phù hợp.

Ví dụ một **WebFilter toàn cục** đơn giản (fragment dùng trong lớp @Configuration, không phải chương trình độc lập):

~~~java
@Bean
WebFilter demoHeaderFilter() {
    return (exchange, chain) -> {
        exchange.getResponse().getHeaders().add("X-Demo-WebFilter", "global");
        return chain.filter(exchange);
    };
}
~~~

Filter này có thể chạy cho cả route công khai lẫn route cần xác thực vì đây là filter thuộc **pipeline WebFlux toàn cục**, không gắn với một SecurityWebFilterChain cụ thể. Nếu muốn thực hiện tác vụ *sau khi downstream kết thúc*, có thể gắn toán tử reactive như **doFinally(...)** vào publisher trả về. Tránh dùng **block()**, I/O đồng bộ nặng hoặc lưu trạng thái request vào biến instance của singleton filter.

## 3. WebFilterChainProxy: cầu nối giữa WebFlux và Spring Security

**org.springframework.security.web.server.WebFilterChainProxy** triển khai WebFilter, nhưng không thay thế toàn bộ chuỗi WebFilter của WebFlux. Nó nhận một danh sách SecurityWebFilterChain do cấu hình Spring Security xây dựng và thực hiện:

1. Nhận ServerWebExchange và WebFilterChain hiện tại.
2. Duyệt các SecurityWebFilterChain theo thứ tự ưu tiên; hỏi matcher của từng chain có khớp request không.
3. Lấy **chuỗi khớp đầu tiên** và chạy các WebFilter bảo mật thuộc chuỗi đó.
4. Nếu các filter không chặn xử lý, tiếp tục WebFilterChain ban đầu để đi đến các thành phần WebFlux còn lại.
5. Nếu không có chain nào khớp, các filter bảo mật của những chain đó không được áp dụng; phần WebFlux còn lại vẫn có thể xử lý request. Vì thế ứng dụng thường cần một **fallback chain** bao phủ phần URL còn lại.

Trong cấu hình ứng dụng thông thường, **@EnableWebFluxSecurity** hoặc auto-configuration phù hợp của Spring Boot sẽ lắp ráp hạ tầng này. Nhà phát triển chủ yếu khai báo các bean SecurityWebFilterChain; thường không tự tạo WebFilterChainProxy.

**Phân biệt package để tránh cấu hình sai stack:**

| WebFlux/reactive | Servlet/MVC |
| --- | --- |
| org.springframework.web.server.WebFilter | jakarta.servlet.Filter |
| org.springframework.security.web.server.WebFilterChainProxy | org.springframework.security.web.FilterChainProxy |
| SecurityWebFilterChain | SecurityFilterChain |
| ServerHttpSecurity | HttpSecurity |
| ServerWebExchangeMatcher | RequestMatcher |

Hai lớp tên gần giống nhau **WebFilterChainProxy** và **FilterChainProxy** thuộc hai kiến trúc khác nhau. Không lấy ví dụ servlet Filter/HttpSecurity áp nguyên vào WebFlux.

## 4. SecurityWebFilterChain: chọn phạm vi và điều khiển bảo mật

Một SecurityWebFilterChain có hai ý chính:

- **Matcher của cả chain:** Request nào được xử lý bởi tập security filter này? Cấu hình qua **ServerHttpSecurity.securityMatcher(...)**. Nếu không chỉ định, matcher mặc định thường khớp mọi request.
- **Các WebFilter thuộc chain:** Cơ chế bảo mật nào được bật, như khôi phục SecurityContext, HTTP Basic, kiểm tra CSRF, authorization, xử lý exception? Cấu hình qua DSL của **ServerHttpSecurity** rồi **build()**.

Ví dụ phân vùng: API dùng HTTP Basic; các URL khác dùng cấu hình fallback riêng. Một request **GET /api/private** khớp chain API; nó không tiếp tục chạy chain fallback sau khi đã chọn được chain API.

### securityMatcher khác authorizeExchange.pathMatchers

Hai thao tác này không thay thế nhau:

| Cấu hình | Câu hỏi được trả lời | Hiệu lực |
| --- | --- | --- |
| **securityMatcher("/api/**")** | Chain này có được chọn cho request không? | Quyết định *tập filter bảo mật* nào tham gia. |
| **authorizeExchange(...pathMatchers("/api/public").permitAll())** | Bên trong chain đã chọn, path nào được phép? | Quyết định *quyền truy cập*; không vô hiệu hóa toàn bộ security filter. |
| **authorizeExchange(...anyExchange().authenticated())** | Các request khác trong chain cần xác thực không? | Là quy tắc authorization dự phòng *bên trong chính chain đó*. |

**permitAll không có nghĩa là bỏ qua WebFilterChainProxy.** Các filter liên quan khác của chain vẫn có thể chạy, chẳng hạn security headers hay cơ chế xử lý security context.

### Có ba cấp độ thứ tự cần phân biệt

1. **Thứ tự WebFilter toàn cục:** quyết định vị trí của một WebFilter so với các WebFilter WebFlux khác; thường điều khiển bằng Ordered hoặc @Order ở bean/filter thích hợp.
2. **Thứ tự SecurityWebFilterChain:** quyết định proxy thử chain nào trước; áp dụng @Order cho các bean SecurityWebFilterChain. Chain cụ thể nên đứng trước chain bắt mọi request.
3. **Thứ tự WebFilter bên trong chain bảo mật:** do cấu hình Spring Security tổ chức; khi bổ sung filter bảo mật tùy biến vào chain, dùng những vị trí định nghĩa bởi **SecurityWebFiltersOrder** thông qua API như **ServerHttpSecurity.addFilterAt(...)**, tùy mục đích.

@Order trên **một bean WebFilter toàn cục** không đồng nghĩa với @Order trên **một bean SecurityWebFilterChain**. Và việc tự khai báo @Bean WebFilter không tự động đặt filter đó vào danh sách filter riêng của chain API.

## 5. Ví dụ chạy được: hai SecurityWebFilterChain và một WebFilter toàn cục

**Môi trường:** Java 17+, một dự án Maven Spring Boot 3.x dùng **Spring Reactive Web** (spring-boot-starter-webflux) và **Spring Security** (spring-boot-starter-security). Có thể tạo dự án này bằng Spring Initializr; giữ nguyên Maven wrapper và cấu trúc Maven được sinh ra. Không thêm spring-boot-starter-web cho bài minh họa WebFlux.

Tạo file **src/main/java/com/example/demo/DemoApplication.java** với **toàn bộ** nội dung sau:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebFilter;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    ReactiveUserDetailsService users() {
        UserDetails user = User.withUsername("learner")
                .password("{noop}demo123")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(user);
    }

    // WebFilter của toàn bộ ứng dụng, không chỉ dành cho /api/**.
    @Bean
    WebFilter globalHeaderFilter() {
        return (exchange, chain) -> {
            exchange.getResponse().getHeaders()
                    .add("X-Demo-WebFilter", "global");
            return chain.filter(exchange);
        };
    }

    // Ưu tiên chain API trước chain fallback.
    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher("/api/**"))
                .authorizeExchange(auth -> auth
                        .pathMatchers("/api/public").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    // Không khai báo securityMatcher: chain dự phòng cho URL còn lại.
    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }
}

@RestController
class DemoEndpoints {

    @GetMapping("/")
    String home() {
        return "home";
    }

    @GetMapping("/api/public")
    String publicApi() {
        return "public";
    }

    @GetMapping("/api/private")
    String privateApi() {
        return "private";
    }

    @GetMapping("/account")
    String account() {
        return "account";
    }
}
~~~

**Chạy** tại thư mục gốc dự án Maven (có Maven wrapper):

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows có thể dùng **mvnw.cmd spring-boot:run**. Trong terminal khác, gửi các request sau:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/private
curl -i -u learner:demo123 http://localhost:8080/api/private
curl -i http://localhost:8080/
curl -i http://localhost:8080/account
~~~

**Kết quả HTTP dự kiến** khi chạy đúng ví dụ với cấu hình Basic ở trên:

| Request | Chain được chọn | HTTP status | Response body (khi 200) |
| --- | --- | --- | --- |
| GET /api/public, không credentials | apiChain | **200** | public |
| GET /api/private, không credentials | apiChain | **401** | — |
| GET /api/private với Basic learner:demo123 | apiChain | **200** | private |
| GET /, không credentials | fallbackChain | **200** | home |
| GET /account, không credentials | fallbackChain | **401** | — |

Header **X-Demo-WebFilter: global** do filter toàn cục bổ sung minh họa việc một WebFilter bình thường độc lập với việc proxy chọn chain API hay fallback. Các header khác và nội dung response lỗi có thể thay đổi theo phiên bản/cấu hình; bảng chỉ khẳng định status và body thành công liên quan đến logic ví dụ.

Giải thích từng đường đi:

- **GET /api/public:** proxy gặp apiChain trước, matcher /api/** khớp; quy tắc /api/public cho phép truy cập không cần đăng nhập; handler trả “public”.
- **GET /api/private** không credentials: vẫn chọn apiChain; yêu cầu authenticated thất bại nên lớp bảo mật xử lý phản hồi 401, không đi đến method privateApi().
- **GET /api/private** có Basic: cơ chế xác thực tìm user trong MapReactiveUserDetailsService; hợp lệ nên authorization cho qua, handler trả “private”.
- **GET /** và **GET /account:** không khớp /api/** nên proxy chọn fallbackChain. Chỉ / được permitAll, /account đòi hỏi authenticated.

**Giới hạn bảo mật của ví dụ:** mật khẩu có tiền tố {noop} được dùng để dễ tự chạy bài học và **không phù hợp production**. Trong hệ thống thật, dùng PasswordEncoder an toàn và kho người dùng phù hợp. Ví dụ chỉ thử các request GET; Spring Security có cơ chế CSRF mặc định cho các phương thức thay đổi trạng thái. Đừng tắt CSRF một cách máy móc, nhất là ứng dụng sử dụng cookie/session trong trình duyệt.

## 6. Khi cần filter tùy biến: đặt ở đâu?

**Nhu cầu A — log/trace/response header cho mọi route:** tạo một bean **WebFilter** toàn cục và kiểm soát thứ tự với các filter khác nếu cần. Luôn bảo toàn đặc tính reactive, xử lý error/cancellation phù hợp.

**Nhu cầu B — logic chỉ thuộc một chain bảo mật:** tạo WebFilter tùy biến rồi đăng ký qua **ServerHttpSecurity.addFilterAt(...)** với **SecurityWebFiltersOrder** phù hợp. Đây là API thêm filter *vào một SecurityWebFilterChain*, không phải chỉ khai báo bean toàn cục. Fragment định hướng (giả sử đã có mySecurityFilter):

~~~java
http.addFilterAt(mySecurityFilter, SecurityWebFiltersOrder.AUTHENTICATION);
~~~

Fragment trên chỉ minh họa nơi cấu hình; chọn vị trí thực tế theo nhiệm vụ của filter và các security filter sẵn có, không chèn bừa vào AUTHENTICATION. Nếu filter phụ trách xác thực, cần phân biệt nó với AuthenticationWebFilter đã được cấu hình và tránh cơ chế xác thực trùng nhau.

**Nhu cầu C — các chính sách API/web khác nhau:** tạo nhiều bean SecurityWebFilterChain với matcher rõ ràng và thứ tự ưu tiên rõ ràng. Ví dụ API có thể dùng HTTP Basic hoặc JWT, còn trang web dùng form login; mỗi request chọn chain phù hợp theo matcher.

### SecurityContext trong reactive

Trong WebFlux, việc xử lý có thể chuyển thread giữa các bước Reactor. Spring Security reactive tích hợp **ReactiveSecurityContextHolder** và Reactor Context để truyền SecurityContext theo luồng reactive. Không dựa duy nhất vào ThreadLocal hay giả định “một request luôn chạy trên một thread”. Khi viết filter tùy biến cần đọc thông tin người dùng, hãy dùng API reactive tương ứng (ví dụ ReactiveSecurityContextHolder.getContext()) và nối publisher vào pipeline.

## 7. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| API chain không bao giờ được dùng | Chain bắt mọi request đứng trước chain /api/** | Dùng @Order để chain cụ thể đứng trước fallback. |
| Một URL ngoài /api/** không được bảo vệ | Chỉ khai báo chain có securityMatcher /api/** và không có fallback | Bổ sung chain mặc định; đặt authorization an toàn cho các đường dẫn còn lại. |
| Đặt permitAll nhưng filter vẫn chạy | permitAll là quy tắc authorization, không phải cơ chế bỏ qua toàn bộ chain | Tách rõ chọn chain và cấp quyền; xem filter nào thực sự cần bỏ qua. |
| Filter tự tạo chạy cả ở route không mong muốn | Khai báo @Bean WebFilter toàn cục | Nếu là logic bảo mật chỉ dành cho một chain, thêm đúng vào ServerHttpSecurity của chain đó. |
| Cố dùng HttpSecurity/SecurityFilterChain hoặc servlet Filter | Nhầm Spring MVC với Spring WebFlux | Dùng ServerHttpSecurity, SecurityWebFilterChain, WebFilter đúng package. |
| Request không đăng nhập trả 302 thay vì 401 | Cơ chế form login/entry point đang bật | Kiểm tra lựa chọn authentication entry point, Basic/form login theo từng chain. |
| Request đã đăng nhập nhưng bị 403 | Quyền không đủ, hoặc chính sách như CSRF từ chối | Đọc chính sách authorization/CSRF, không mặc định coi 403 là lỗi đăng nhập. |
| Filter gây treo hoặc chặn event-loop | Gọi block(), sleep hoặc I/O đồng bộ trong pipeline | Dùng Mono/Flux và cơ chế bất đồng bộ phù hợp. |
| SecurityContext “biến mất” sau khi đổi thread | Dùng ThreadLocal hoặc tự subscribe tách khỏi pipeline | Dùng ReactiveSecurityContextHolder/Reactor Context và giữ composition reactive. |

Để điều tra vì sao request vào chain nào, có thể bật tạm logging của Spring Security trong môi trường phát triển:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Quan sát matcher, security filter, authentication/authorization và status HTTP thực tế. Tránh bật logging nhạy cảm quá chi tiết trong production, và nhớ tắt cấu hình debug sau khi chẩn đoán.

## 8. Tự kiểm tra hiểu bài

1. Vì sao WebFilterChainProxy là một WebFilter nhưng SecurityWebFilterChain lại không phải?
2. Nếu khai báo hai chain đều có matcher khớp /api/orders, chain nào chạy? Điều gì quyết định lựa chọn?
3. **securityMatcher("/api/**")** khác **pathMatchers("/api/public").permitAll()** ở bước nào trong request flow?
4. Tại sao khai báo bean WebFilter ghi log không có nghĩa filter ấy chỉ chạy trong apiChain?
5. Khi thêm một filter để thực hiện xác thực riêng cho API, vì sao cần chọn **SecurityWebFiltersOrder** hợp lý?
6. Chuyện gì xảy ra nếu toàn bộ SecurityWebFilterChain đều không khớp một URL? Làm sao tránh “lỗ hổng” do thiếu fallback?
7. Tại sao không nên dùng ThreadLocal hoặc block() như trong tư duy Servlet khi xử lý request WebFlux?

**Tóm ý:** WebFilter là đơn vị xử lý request của WebFlux; WebFilterChainProxy là cửa vào Spring Security reactive và bộ chọn chain; SecurityWebFilterChain gắn matcher với các security WebFilter tương ứng. Hiểu chính xác ba vai trò và ba tầng thứ tự là nền tảng để thiết kế nhiều vùng bảo mật trong một ứng dụng WebFlux.

## Tài liệu tham khảo chính thức

- Spring Security, WebFlux Security và Multiple Chains: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security, Authorize ServerHttpRequest: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security API, WebFilterChainProxy reactive: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/WebFilterChainProxy.html
- Spring Framework, Reactive Core / WebFilter: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
