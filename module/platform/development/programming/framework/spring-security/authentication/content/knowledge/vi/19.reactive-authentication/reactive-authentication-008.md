# ServerAuthenticationSuccessHandler và ServerAuthenticationFailureHandler trong Spring Security WebFlux

## 1. Hai handler giải quyết việc gì?

Trong ứng dụng Spring WebFlux, xác thực (authentication) là bước kiểm tra một yêu cầu đăng nhập có thực sự thuộc về người dùng hoặc client đã khai báo hay không. Sau khi thành phần xác thực trả về kết quả, ứng dụng còn phải quyết định **phản hồi HTTP ra sao**: chuyển hướng đến trang phù hợp, trả JSON, tiếp tục chuỗi WebFilter hay thông báo lỗi. Đó là trách nhiệm của hai interface:

- `ServerAuthenticationSuccessHandler`: xử lý **sau khi xác thực thành công**.
- `ServerAuthenticationFailureHandler`: xử lý **khi một lần xác thực thất bại** với `AuthenticationException`.

Cả hai thuộc package `org.springframework.security.web.server.authentication` và làm việc với hạ tầng **reactive** của WebFlux. Chúng không kiểm tra mật khẩu thay cho `ReactiveAuthenticationManager`, không tự phân quyền và không phải handler của Spring MVC/Servlet.

Ví dụ: người dùng gửi tên và mật khẩu qua form. Manager xác minh thông tin. Nếu hợp lệ, success handler có thể trả HTTP 200 kèm JSON hoặc redirect. Nếu sai, failure handler có thể trả HTTP 401 hoặc redirect về trang đăng nhập. Việc tài khoản đã xác thực có được truy cập `/admin` hay không vẫn do cơ chế **authorization** quyết định.

## 2. Vị trí trong luồng xác thực reactive

Luồng điển hình của `AuthenticationWebFilter`:

1. Yêu cầu đi qua `SecurityWebFilterChain`; matcher xác định có cần thử xác thực đối với yêu cầu này không.
2. `ServerAuthenticationConverter` đọc request và chuyển thông tin đăng nhập thành một đối tượng `Authentication` chưa xác thực. Nếu converter trả `Mono.empty()` thì filter bỏ qua việc xác thực và tiếp tục chain.
3. `ReactiveAuthenticationManager` kiểm tra thông tin. Kết quả thành công mang `Authentication` đã được xác thực; lỗi xác thực được biểu diễn bằng `AuthenticationException`.
4. Nhánh thành công thiết lập `SecurityContext` trong Reactor Context, lưu context qua `ServerSecurityContextRepository` đã cấu hình và gọi success handler. Nhánh lỗi xác thực gọi failure handler.
5. Handler trả về `Mono<Void>` đại diện cho việc hoàn tất phản hồi hoặc tiếp tục xử lý; hạ tầng WebFlux đăng ký và thực thi publisher đó.

Sơ đồ tư duy:

~~~text
HTTP request
  → SecurityWebFilterChain / AuthenticationWebFilter
    → matcher không khớp hoặc converter rỗng → tiếp tục chain
    → converter tạo Authentication → ReactiveAuthenticationManager
       ├─ hợp lệ → SecurityContext → SuccessHandler → HTTP response/redirect/chain
       └─ AuthenticationException → FailureHandler → HTTP response/redirect
~~~

**Phân biệt:** yêu cầu không có thông tin đăng nhập, lỗi CSRF, yêu cầu chưa đủ quyền (403), và lỗi phát sinh trong controller không nhất thiết đi vào failure handler. Handler chỉ xử lý các sự kiện mà **authentication filter cụ thể** chuyển cho nó.

## 3. Hợp đồng API và dữ liệu đầu vào

Chữ ký rút gọn dưới đây dùng để đọc API, không phải hai class Java độc lập cần tự khai báo:

~~~java
Mono<Void> onAuthenticationSuccess(
    WebFilterExchange webFilterExchange,
    Authentication authentication
);

Mono<Void> onAuthenticationFailure(
    WebFilterExchange webFilterExchange,
    AuthenticationException exception
);
~~~

| Thành phần | Vai trò |
| --- | --- |
| `WebFilterExchange` | Gói `ServerWebExchange` và `WebFilterChain`. Gọi `getExchange()` để truy cập request/response, `getChain()` khi cần tiếp tục filter chain. |
| `Authentication` | Principal, danh sách authorities và trạng thái xác thực ở nhánh thành công. Dùng `getName()` hoặc authorities khi cần quyết định hành vi hợp lệ. |
| `AuthenticationException` | Nguyên nhân xác thực thất bại, chẳng hạn thông tin đăng nhập sai. Dùng để phân loại nội bộ; không trả nguyên stack trace hay thông điệp nhạy cảm cho client. |
| `Mono<Void>` | Tín hiệu hoàn tất công việc bất đồng bộ: ghi response, redirect hoặc gọi tiếp chain. Không phải giá trị JSON trả trực tiếp. |

**Quy tắc reactive:** hãy **trả lại** publisher mô tả thao tác cần làm. Không gọi `block()` trên luồng xử lý request, không tự `subscribe()` rồi trả `Mono.empty()`, và không làm I/O chặn event loop. Nếu phải gọi dịch vụ mạng hoặc ghi log có I/O, dùng API reactive hoặc đưa tác vụ blocking sang scheduler phù hợp.

## 4. Cách xử lý mặc định và các implementation có sẵn

| Bối cảnh | Hành vi phổ biến |
| --- | --- |
| WebFlux `formLogin` | Mặc định success redirect về yêu cầu đã lưu nếu có; nếu không, thường về `/`. Failure redirect về `/login?error` khi dùng trang mặc định. |
| `RedirectServerAuthenticationSuccessHandler` | Redirect sau đăng nhập; có thể tận dụng `ServerRequestCache` để đưa người dùng về tài nguyên họ định truy cập. |
| `RedirectServerAuthenticationFailureHandler` | Redirect đến URI được chỉ định, ví dụ `/login?error`. |
| `WebFilterChainServerAuthenticationSuccessHandler` | Tiếp tục `WebFilterChain` sau khi thành công; đây là success handler mặc định của `AuthenticationWebFilter` được tạo trực tiếp. |
| `ServerAuthenticationEntryPointFailureHandler` | Chuyển failure đến `ServerAuthenticationEntryPoint`, ví dụ challenge HTTP Basic. |
| `DelegatingServerAuthenticationSuccessHandler` | Kết hợp nhiều success handler khi cần nhiều hành động tương thích, theo cấu hình của filter. |

**Đừng nhầm các mặc định:** `formLogin` dựng `AuthenticationWebFilter` với cấu hình redirect và lưu phiên cho trường hợp đăng nhập form; một `AuthenticationWebFilter` mới dựng bằng constructor có mặc định riêng (success tiếp tục chain, repository `NoOpServerSecurityContextRepository`, failure challenge Basic). Vì vậy, không thể suy từ mặc định của filter tùy biến rằng form login cũng hành xử y hệt.

Khi cần redirect đơn giản, ưu tiên implementation có sẵn:

~~~java
.formLogin(form -> form
    .authenticationSuccessHandler(
        new RedirectServerAuthenticationSuccessHandler("/dashboard"))
    .authenticationFailureHandler(
        new RedirectServerAuthenticationFailureHandler("/login?error"))
)
~~~

Đây là **đoạn cấu hình**, được đặt bên trong cấu hình `ServerHttpSecurity`. Với success redirect, nếu request cache đang chứa URL hợp lệ thì URL đã lưu có thể được ưu tiên so với `/dashboard`; hãy kiểm tra mục tiêu trong luồng thực tế thay vì mặc định tin rằng mọi lần đăng nhập đều vào một URL cố định.

## 5. Ví dụ hoàn chỉnh: trả JSON sau form login

Ví dụ dùng **Java 17+**, **Spring Boot WebFlux** và **Spring Security**. Tạo ứng dụng Spring Boot bằng Spring Initializr với hai dependency `Spring Reactive Web` (`spring-boot-starter-webflux`) và `Spring Security` (`spring-boot-starter-security`). Chọn Maven và để Spring Boot quản lý phiên bản thư viện tương thích. Ví dụ chỉ dùng user trong bộ nhớ để học cơ chế, không dành cho dữ liệu người dùng thật.

Tạo tệp `src/main/java/demo/ReactiveLoginDemoApplication.java`:

~~~java
package demo;

import java.nio.charset.StandardCharsets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.WebFilterExchange;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveLoginDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveLoginDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("learner")
                .password(encoder.encode("learn123"))
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(user);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            MapReactiveUserDetailsService users, PasswordEncoder encoder) {
        var manager = new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {

        ServerAuthenticationSuccessHandler success = (webFilterExchange, auth) ->
                jsonResponse(webFilterExchange, HttpStatus.OK,
                        "{\"status\":\"authenticated\"}");

        ServerAuthenticationFailureHandler failure = (webFilterExchange, error) ->
                jsonResponse(webFilterExchange, HttpStatus.UNAUTHORIZED,
                        "{\"error\":\"bad_credentials\"}");

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/login").permitAll()
                        .anyExchange().authenticated())
                .formLogin(form -> form
                        .authenticationManager(manager)
                        .authenticationSuccessHandler(success)
                        .authenticationFailureHandler(failure))
                .build();
    }

    private static Mono<Void> jsonResponse(
            WebFilterExchange webFilterExchange, HttpStatus status, String json) {
        ServerHttpResponse response = webFilterExchange.getExchange().getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        return response.writeWith(
                Mono.just(response.bufferFactory().wrap(bytes)));
    }

    @RestController
    static class DemoController {
        @GetMapping("/private")
        Mono<String> privateEndpoint() {
            return Mono.just("Only authenticated users can see this");
        }
    }
}
~~~

### Giải thích từng phần

- `MapReactiveUserDetailsService` nạp user `learner`; `BCryptPasswordEncoder` lưu bản hash của mật khẩu minh họa. `UserDetailsRepositoryReactiveAuthenticationManager` là thành phần **quyết định thông tin đăng nhập có hợp lệ**, được cấu hình cùng encoder.
- `ServerHttpSecurity` chọn policy: cho phép truy cập `/login` và yêu cầu xác thực đối với URL khác. `formLogin` cài cơ chế đăng nhập form; `authenticationManager(manager)` dùng manager đã khai báo.
- Nhánh success gọi `jsonResponse(...)` và trả `200 OK` với body `{"status":"authenticated"}`. Đối tượng `auth` có thể dùng để ghi audit theo chính sách, nhưng ví dụ cố ý không tiết lộ thông tin nhạy cảm.
- Nhánh failure trả `401 Unauthorized` với body `{"error":"bad_credentials"}`. Thông điệp cố định giảm khả năng lộ chi tiết về người dùng hoặc trạng thái tài khoản.
- Helper `jsonResponse` lấy `ServerHttpResponse`, đặt HTTP status và content type, tạo bytes UTF-8 rồi **trả** `Mono<Void>` của `response.writeWith(...)`. Không tự quản lý subscriber.

### Chạy và kiểm tra hành vi

Trong thư mục dự án do Spring Initializr tạo, chạy:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell/CMD dùng `mvnw.cmd spring-boot:run`. Sau khi ứng dụng khởi động, thao tác bằng trình duyệt:

1. Mở `http://localhost:8080/private` khi chưa đăng nhập. Form login sẽ đưa bạn tới màn hình đăng nhập `/login`.
2. Đăng nhập `learner` / `learn123`. Thao tác POST form hợp lệ gọi **success handler** và trình duyệt hiển thị JSON `{"status":"authenticated"}` với HTTP 200.
3. Giữ nguyên cookie phiên trong cùng trình duyệt, truy cập `/private`: server trả chuỗi `Only authenticated users can see this`.
4. Mở cửa sổ riêng tư mới, thử mật khẩu không đúng. POST form tới `/login` gọi **failure handler** và phản hồi HTTP 401 với `{"error":"bad_credentials"}`.

Spring Security bật bảo vệ **CSRF** mặc định cho form login. Trang `/login` do framework tạo chứa CSRF token hợp lệ. Lệnh `curl -d "username=..." -d "password=..."` gửi POST thủ công mà **không kèm token** có thể bị chặn với HTTP 403 **trước khi** failure handler chạy; đó không phải lỗi của handler. Để tự động hóa kiểm thử, dùng WebTestClient kèm hỗ trợ CSRF từ `spring-security-test` và quản lý cookie phiên đúng cách.

**Kết quả mong đợi trong ví dụ:**

| Thao tác | HTTP / kết quả | Handler |
| --- | --- | --- |
| POST `/login` với thông tin hợp lệ và CSRF hợp lệ | 200, `{"status":"authenticated"}` | Success |
| POST `/login` với sai mật khẩu và CSRF hợp lệ | 401, `{"error":"bad_credentials"}` | Failure |
| POST thiếu hoặc sai CSRF token | Thường 403 | Không phải failure handler xác thực |
| GET `/private` khi chưa xác thực | Redirect đến login trong cấu hình form | Entry point / authorization |
| GET `/private` khi đã đăng nhập, giữ phiên | 200, chuỗi từ controller | Không chạy lại success handler chỉ vì truy cập trang |

## 6. Khi nào dùng handler tự viết?

**Trang web truyền thống:** nếu sau đăng nhập cần điều hướng, dùng hai `RedirectServerAuthentication...Handler` thường là đủ. Có thể cấu hình URI cố định hoặc request cache và giao diện hiển thị thông báo lỗi ở trang login.

**Đăng nhập trả JSON:** ứng dụng SPA hoặc client tùy biến có thể muốn 200/401 với body ổn định. Khi đó custom handler chịu trách nhiệm đúng format response như ví dụ. Tuy nhiên **thay response bằng JSON không tự biến form login thành REST authentication API**: vẫn có matcher của form, tên trường, CSRF, cookie/session và luồng SecurityContext hiện hành. Nếu muốn nhận JSON credentials hoặc Bearer token, cần thiết kế converter/filter và mô hình trạng thái riêng.

**Xử lý nghiệp vụ phụ sau đăng nhập:** có thể đo audit, ghi nhận thời điểm login, điều hướng dựa theo role hoặc thiết lập cookie phù hợp. Những thao tác đó phải an toàn, có giới hạn và được nối vào `Mono`. Không chuyển logic kiểm tra credential sang handler và không làm rò password, token, stack trace, hoặc nguyên nhân chi tiết của việc từ chối.

**Bộ lọc xác thực tùy biến:** khi tự tạo `AuthenticationWebFilter`, dùng:

~~~java
filter.setAuthenticationSuccessHandler(successHandler);
filter.setAuthenticationFailureHandler(failureHandler);
~~~

Hai dòng này là **đoạn cấu hình minh họa**, chưa phải ứng dụng hoàn chỉnh: bạn còn cần `ReactiveAuthenticationManager`, `ServerAuthenticationConverter`, matcher, vị trí filter, security context repository và cơ chế xử lý lỗi phù hợp. Đối với WebFlux, thao tác với `SecurityWebFilterChain` và `ServerHttpSecurity`; không lắp nhầm `HttpSecurity`, `SecurityFilterChain` hoặc các interface Servlet `AuthenticationSuccessHandler`/`AuthenticationFailureHandler`.

## 7. So sánh với các thành phần dễ nhầm

| Thành phần | Quyết định điều gì? |
| --- | --- |
| `ReactiveAuthenticationManager` | Credentials/token có hợp lệ hay không. |
| `ServerAuthenticationSuccessHandler` | Sau **xác thực thành công**, trả gì hoặc chuyển hướng/tiếp tục ở đâu. |
| `ServerAuthenticationFailureHandler` | Sau **xác thực thất bại**, xử lý response như thế nào. |
| `ServerAuthenticationEntryPoint` | Khi client **chưa được xác thực** nhưng cần truy cập tài nguyên bảo vệ, bắt đầu cơ chế login/challenge ra sao. |
| `ServerAccessDeniedHandler` | Khi yêu cầu bị **từ chối truy cập** theo chính sách, điển hình đã xác thực nhưng thiếu quyền, trả gì (thường 403). |
| `ServerSecurityContextRepository` | Lưu/nạp `SecurityContext` giữa các request khi dùng kiểu xác thực có trạng thái. |

Một POST login sai mật khẩu và một GET tới tài nguyên bảo vệ khi chưa đăng nhập là **hai sự kiện khác nhau**. Sự kiện đầu thuộc failure handler của authentication filter; sự kiện sau thường thuộc cơ chế entry point. Tương tự, user đăng nhập được nhưng thiếu role không đồng nghĩa việc login thất bại.

## 8. Những lỗi thường gặp và cách xử lý

1. **Dùng API của Servlet trong WebFlux:** import nhầm `AuthenticationSuccessHandler`, `AuthenticationFailureHandler`, `HttpServletRequest` hoặc cấu hình `HttpSecurity`. Sửa bằng các interface có tiền tố `Server`, `WebFilterExchange` và `ServerHttpSecurity`.
2. **Trả `Mono.empty()` sau khi tự `subscribe()`:** phản hồi có thể hoàn tất trước thao tác bất đồng bộ. Sửa bằng cách trả chính `Mono<Void>` từ `writeWith`, redirect strategy hoặc chuỗi publisher có `then()`.
3. **Tưởng custom handler luôn được gọi:** matcher không khớp, converter không tạo `Authentication`, CSRF bị từ chối, hoặc filter khác xử lý request trước. Kiểm tra đúng đường dẫn, HTTP method, security chain và tình huống test.
4. **Gửi chi tiết exception cho người dùng:** nội dung có thể làm lộ trạng thái tài khoản, cấu hình hoặc dữ liệu nhạy cảm. Trả thông điệp ổn định, lưu log/audit nội bộ có kiểm soát và giới hạn thông tin.
5. **Nhầm 401 với 403:** 401 cho yêu cầu cần/xác thực thất bại theo API; 403 thường cho từ chối quyền hoặc CSRF. Chọn status dựa trên ngữ cảnh và hợp đồng HTTP của ứng dụng.
6. **Bỏ qua phiên khi dùng form login:** nếu muốn duy trì trạng thái sau POST, cần security context repository và cookie phiên. Với stateless API, phải thiết kế chiến lược token phù hợp; response handler đơn lẻ không tạo mô hình stateless.
7. **Redirect mở hoặc không an toàn:** không lấy URL chuyển hướng chưa kiểm chứng trực tiếp từ query parameter. Nếu dùng redirect theo yêu cầu đã lưu, hiểu cách request cache hoạt động và chỉ chấp nhận đích tin cậy.
8. **Viết response hai lần:** sau khi response đã commit, không thể chuyển sang redirect hoặc ghi JSON khác. Chọn một hành vi kết thúc hoặc chuỗi handler tương thích; chú ý trình tự khi dùng delegating handler.

## 9. Câu hỏi tự kiểm tra

- Vì sao `ReactiveAuthenticationManager` và success handler phải là hai trách nhiệm khác nhau?
- Tình huống POST login sai mật khẩu khác gì với GET `/private` chưa có phiên?
- Vì sao POST login thiếu CSRF token có thể không đi vào failure handler?
- Khi nào nên dùng `RedirectServerAuthenticationSuccessHandler`, khi nào nên trả JSON?
- Chuyện gì xảy ra nếu handler làm I/O blocking hoặc tự gọi `subscribe()`?

Nếu trả lời được năm câu này và chạy được hai nhánh đăng nhập trong ví dụ, bạn đã nắm được nơi gắn các handler, dữ liệu nhận vào, trách nhiệm với response và những giới hạn chính trong pipeline xác thực reactive.

## 10. Tài liệu chính thức

- [Spring Security — ServerAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationSuccessHandler.html)
- [Spring Security — ServerAuthenticationFailureHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationFailureHandler.html)
- [Spring Security — AuthenticationWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Spring Security — ServerHttpSecurity.FormLoginSpec API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
