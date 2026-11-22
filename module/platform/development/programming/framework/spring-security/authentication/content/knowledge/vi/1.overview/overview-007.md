# Phạm vi xác thực trong ứng dụng Servlet và reactive

## Mục tiêu học tập

Trong Spring Security, “phạm vi xác thực” trả lời bốn câu hỏi: **request nào** phải xác thực; **bằng chứng** nào được kiểm tra; **danh tính đã xác thực** được giữ và truy cập ở đâu; và danh tính đó **có hiệu lực bao lâu**. Khi hoàn thành bài, bạn có thể:

1. Chỉ ra điểm Spring Security chặn request trong ứng dụng Servlet/Spring MVC và reactive/Spring WebFlux.
2. Phân biệt `Authentication`, `SecurityContext`, authentication filter, security chain và cơ chế lưu phiên.
3. Giải thích vì sao Servlet chủ yếu dùng `ThreadLocal`, còn WebFlux dùng **Reactor Context**; xử lý việc mất principal khi chuyển ngữ cảnh thực thi.
4. Phân biệt xác thực theo request, xác thực được khôi phục từ session và xác thực bằng bearer token trên mỗi request.
5. Viết và chạy cấu hình cơ bản cho từng stack; nhận biết phản hồi `200`, `401` và `403`.

**Phạm vi:** authentication đối với HTTP request trong Spring Security 6+ / Spring Boot 3+. OAuth 2.0/OIDC, JWT, MFA, quản trị session và authorization chuyên sâu được đề cập khi cần minh họa ranh giới; chúng không phải mục tiêu triển khai đầy đủ ở bài tổng quan này.

## 1. Xác thực bắt đầu và kết thúc ở đâu?

**Authentication** xác minh danh tính từ bằng chứng mà server tin cậy: username/password, HTTP Basic, cookie trỏ tới phiên đã đăng nhập, bearer token, client certificate hoặc cơ chế được cấu hình riêng. **Authorization** dùng kết quả đó để quyết định quyền truy cập. Hai bước liên quan nhưng không đồng nhất: một người có thể đăng nhập hợp lệ mà vẫn bị từ chối endpoint yêu cầu quyền cao hơn.

Các đối tượng cơ bản:

- `Authentication` chứa `principal` (ai), `credentials` (bằng chứng; thường được xóa sau khi xác thực), `authorities` (role/scope/quyền) và trạng thái liên quan.
- `SecurityContext` chứa `Authentication` cho ngữ cảnh hiện hành.
- Filter xác thực đọc bằng chứng, gọi thành phần kiểm tra credentials và công bố `Authentication` thành công vào context.
- Thành phần authorization dựa trên context và luật bảo vệ endpoint/method để quyết định cho phép hay từ chối.

Một request được đưa vào Spring Security thường đi theo mô hình:

~~~text
Client gửi HTTP request
  -> Chọn security chain phù hợp với request
  -> Nạp SecurityContext trước đó (nếu có)
  -> Đọc/kiểm tra credentials và tạo Authentication khi cần
  -> Kiểm tra authorization
  -> Controller/handler -> service
  -> Hoàn tất request; giải phóng ngữ cảnh thực thi
     và lưu danh tính cho request sau nếu cơ chế cho phép
~~~

Mọi request HTTP tiếp theo đều có lượt xử lý mới. “Đã đăng nhập” không có nghĩa một đối tượng Java `SecurityContext` tồn tại vĩnh viễn trong ứng dụng. Context của request mới có thể được **khôi phục** qua session hoặc **tạo lại** sau khi kiểm tra token.

**Anonymous không đồng nghĩa đã đăng nhập.** Một `AnonymousAuthenticationToken` vẫn có thể trả `isAuthenticated() == true`. Vì thế, không dùng duy nhất cờ này để kết luận người dùng thật đã xác thực; hãy dùng `authenticated()` và các luật Spring Security tương ứng.

Spring Security chỉ bảo vệ điểm vào thực sự nằm trong security chain. Scheduled job, message consumer, CLI, tác vụ chạy sau request hay lời gọi sang service khác không tự nhận một danh tính HTTP hợp lệ.

## 2. Ứng dụng Servlet: xác thực gắn với request và thread xử lý

### 2.1. Chuỗi filter của Spring MVC

Trong Servlet stack, `DelegatingFilterProxy` nối filter của Servlet container tới Spring Bean `FilterChainProxy`. `FilterChainProxy` tìm `SecurityFilterChain` đầu tiên phù hợp request và chạy các filter liên quan; cấu hình bằng `HttpSecurity`.

| Thành phần | Nhiệm vụ |
| --- | --- |
| `SecurityFilterChain` | Quy định request nào thuộc chuỗi và filter xác thực/authorization nào được áp dụng |
| `AuthenticationManager` | Giao diện kiểm tra `Authentication` đầu vào; thường là `ProviderManager` |
| `AuthenticationProvider` | Xử lý một dạng chứng cứ cụ thể, ví dụ username/password |
| `SecurityContextHolder` | Giữ `SecurityContext` hiện hành, mặc định dựa trên `ThreadLocal` |
| `SecurityContextRepository` | Khôi phục/lưu context qua các request nếu cần |
| `AuthenticationEntryPoint` | Yêu cầu đăng nhập hoặc trả HTTP authentication challenge khi chưa đủ bằng chứng |

Ví dụ HTTP Basic: client gửi header `Authorization: Basic ...`; filter đọc giá trị, gọi `AuthenticationManager`, nếu thành công đặt `Authentication` vào context. Nếu request thiếu credentials mà đường dẫn yêu cầu xác thực, Spring Security thường phản hồi `401 Unauthorized` cùng challenge. Với form login, sau một lần đăng nhập, browser có thể gửi session cookie ở request sau để lấy lại danh tính.

### 2.2. SecurityContextHolder và giới hạn của ThreadLocal

Khi xử lý HTTP request Servlet đã vào security chain, code đồng bộ trên thread hiện hành có thể đọc:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
String username = auth.getName();
~~~

Đây là **mã minh họa bên trong một phương thức của ứng dụng Servlet**, không phải chương trình độc lập. Dùng import `org.springframework.security.core.Authentication` và `org.springframework.security.core.context.SecurityContextHolder`. Trong Spring MVC controller, tham số `Principal` hoặc `Authentication` thường rõ nghĩa hơn việc gọi holder trực tiếp.

`ThreadLocal` giúp tránh truyền thủ công danh tính qua từng lời gọi đồng bộ; nhưng **không tự truyền an toàn sang thread khác**. `@Async`, `ExecutorService`, CompletableFuture, callback ngoài request và thread tự tạo có thể không có context mong đợi. Tùy use case, dùng cơ chế chuyển `SecurityContext` được Spring Security hỗ trợ (họ `DelegatingSecurityContext*`), hoặc thiết kế một service identity độc lập. Spring Security dọn context sau request để thread trong pool không mang nhầm danh tính của người dùng trước đó.

### 2.3. Sống qua một hay nhiều request?

- **Theo request:** credentials được kiểm tra trong request hiện tại; context phục vụ việc xử lý request đó.
- **Theo session:** với đăng nhập form, `SecurityContextRepository` có thể dùng `HttpSession` để lưu/khôi phục danh tính. Cookie do client gửi chỉ là cách nhận diện session; không phải toàn bộ thông tin người dùng.
- **Theo bearer token:** client thường gửi token trong mỗi request; resource server xác thực token rồi xây dựng danh tính của lượt gọi đó, không bắt buộc dựa vào `HttpSession`.

Cần phân biệt **đặt context tạm thời** và **lưu để request sau khôi phục**. Trong Spring Security 6+, `SecurityContextHolderFilter` nạp context nhưng không tự động lưu mọi thay đổi. Nếu bạn tự xử lý login trong custom filter/controller và muốn duy trì đăng nhập, phải lưu context bằng `SecurityContextRepository.saveContext(context, request, response)`. Luồng login dựng sẵn xử lý bước lưu phù hợp với cấu hình.

Đối với Servlet API xác thực bằng token, `SessionCreationPolicy.STATELESS` thường được dùng để không dựa vào `HttpSession` cho `SecurityContext`. Tuy nhiên, cấu hình stateless của Spring Security không chứng minh rằng toàn bộ ứng dụng không bao giờ có session vì mục đích khác.

## 3. Ứng dụng reactive: xác thực gắn với Reactor pipeline

### 3.1. Bộ lọc và API của WebFlux

WebFlux dùng `WebFilter`, `ServerWebExchange` và các publisher `Mono`/`Flux`. Spring Security dùng `SecurityWebFilterChain` phù hợp request và cấu hình bằng `ServerHttpSecurity`:

- `AuthenticationWebFilter` và các web filter xác thực phù hợp chuyển request thành `Authentication` đầu vào (thường qua `ServerAuthenticationConverter`).
- `ReactiveAuthenticationManager` xử lý xác thực theo giao diện bất đồng bộ và trả `Mono<Authentication>`.
- `ReactiveSecurityContextHolder` lấy context từ **Reactor Context**, tức ngữ cảnh gắn với reactive subscription.
- `ServerSecurityContextRepository` quyết định cách đọc/lưu context; `WebSessionServerSecurityContextRepository` có thể dùng `WebSession`.

Một đoạn đọc danh tính đúng cách trong reactive pipeline:

~~~java
Mono<String> currentName =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
~~~

Đây là **mã minh họa đặt trong một pipeline WebFlux đã được Spring Security thiết lập context**. Import `ReactiveSecurityContextHolder`, `SecurityContext` từ `org.springframework.security.core.context` và `Authentication` từ `org.springframework.security.core`.

### 3.2. Vì sao không dùng ThreadLocal cho WebFlux?

Một chuỗi reactive có thể chuyển thread qua các toán tử hoặc scheduler mà vẫn thuộc cùng một request/subscription. `ThreadLocal` là thuộc tính của thread, nên nó không thể biểu thị ổn định người dùng của toàn bộ luồng reactive. Reactor Context đi theo cơ chế truyền context của publisher/subscription; Spring Security tích hợp cơ chế đó vào HTTP pipeline.

Những thao tác như tự gọi `subscribe()` trên luồng tách biệt, tự tạo callback bên ngoài pipeline hoặc chuyển sang API không giữ Reactor Context có thể làm mất thông tin xác thực. Đừng thay bằng truy cập `SecurityContextHolder.getContext()` theo thói quen Servlet; hãy giữ chuỗi publisher và lấy `ReactiveSecurityContextHolder.getContext()` tại nơi dùng.

Trong bài test hoặc luồng được quản lý riêng, Spring Security cung cấp `ReactiveSecurityContextHolder.withAuthentication(authentication)` kết hợp toán tử `contextWrite(...)`. Việc gắn context cần dùng một `Authentication` đã được kiểm chứng; không biến chuỗi username do client tự khai báo thành danh tính tin cậy.

### 3.3. Reactive không đồng nghĩa stateless

WebFlux vẫn có thể dùng **WebSession** cho form login và giữ danh tính qua nhiều request. Nếu một API reactive dùng bearer token, bạn có thể không muốn lưu context giữa các exchange, ví dụ với `NoOpServerSecurityContextRepository`. Việc chọn repository này không tự vô hiệu hóa mọi tính năng WebSession trong ứng dụng.

Cấu hình OAuth2 resource server (JWT hoặc opaque token) phải kiểm tra token qua decoder/introspector đáng tin cậy, đồng thời kiểm tra điều kiện như issuer/audience khi thích hợp. Spring Security resource server xác minh token đầu vào; nó không mặc nhiên cung cấp endpoint cấp token cho client.

## 4. Đối chiếu trực tiếp Servlet và reactive

| Khía cạnh | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| Điểm chặn HTTP | Servlet `Filter` / `SecurityFilterChain` | `WebFilter` / `SecurityWebFilterChain` |
| DSL | `HttpSecurity` | `ServerHttpSecurity` |
| Bộ quản lý xác thực | `AuthenticationManager` | `ReactiveAuthenticationManager` |
| Đọc context | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| Nơi context được chuyển theo mặc định | `ThreadLocal` của thread hiện hành | Reactor Context của subscription |
| Kho lưu cho request sau | `SecurityContextRepository`, ví dụ `HttpSession` | `ServerSecurityContextRepository`, ví dụ `WebSession` |
| Luật URL | `authorizeHttpRequests().requestMatchers(...)` | `authorizeExchange().pathMatchers(...)` |
| Đọc principal trong handler | `Principal`/`Authentication` hoặc holder | Reactor Context hoặc tham số principal reactive phù hợp |

**Chọn theo stack của ứng dụng, không suy ra từ tên container.** WebFlux có thể chạy trên những runtime HTTP khác nhau. Nếu đưa đồng thời `spring-boot-starter-web` và `spring-boot-starter-webflux` vào một Spring Boot application, Spring MVC thường được chọn mặc định. Hãy xác định rõ một mô hình và dùng đúng bộ security API.

## 5. Mã Java 17+ cho hai ứng dụng độc lập

Tạo **hai Spring Boot project riêng biệt** bằng Spring Initializr (Spring Boot 3.x, Java 17 hoặc 21). Project Servlet chọn dependencies **Spring Web** + **Spring Security**; project reactive chọn **Spring Reactive Web** + **Spring Security**. Đặt các file sau trong `src/main/java/com/example/demo/` của từng project. Ví dụ dùng user in-memory và mật khẩu demo, chỉ để thử trên máy phát triển; production cần nguồn identity, cấu hình secret và HTTPS thích hợp.

### 5.1. Servlet: `ServletAuthApplication.java`

~~~java
package com.example.demo;

import java.security.Principal;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class ServletAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletAuthApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var user = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("READER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        String publicPage() {
            return "public";
        }

        @GetMapping("/me")
        String me(Principal principal) {
            return principal.getName();
        }
    }
}
~~~

`/public` cho phép anonymous; `/me` yêu cầu xác thực. Cùng một thread xử lý Servlet request có thể thấy context, và Spring MVC đưa danh tính vào tham số `Principal`. `httpBasic(...)` bật cơ chế xác thực HTTP Basic, không cần viết custom filter.

### 5.2. WebFlux: `ReactiveAuthApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var user = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("READER")
            .build();
        return new MapReactiveUserDetailsService(user);
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        Mono<String> publicPage() {
            return Mono.just("public");
        }

        @GetMapping("/me")
        Mono<String> me() {
            return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
        }
    }
}
~~~

Hai ứng dụng có **chính sách URL giống nhau**, nhưng WebFlux trả publisher và đọc principal qua Reactor Context. Không chuyển đoạn WebFlux sang `HttpSecurity` / `SecurityContextHolder` nếu không đổi mô hình ứng dụng.

### 5.3. Chạy và kết quả kỳ vọng

Chạy từng project một, bởi cả hai mặc định dùng cổng 8080:

~~~bash
./mvnw spring-boot:run
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:demo-pass http://localhost:8080/me
curl -i -u alice:wrong-password http://localhost:8080/me
~~~

Nếu tạo project bằng Gradle, dùng `./gradlew bootRun`; trên Windows PowerShell có thể gọi `curl.exe` để tránh alias khác tên.

| Request | Status kỳ vọng | Phần nội dung quan sát được |
| --- | --- | --- |
| `GET /public` không credentials | `200 OK` | `public` |
| `GET /me` không credentials | `401 Unauthorized` | Basic challenge, không lộ username |
| `GET /me` với `alice:demo-pass` | `200 OK` | `alice` |
| `GET /me` với mật khẩu sai | `401 Unauthorized` | Không lộ username |

Không giả định thứ tự header/charset chính xác vì có thể phụ thuộc runtime. Mỗi request `/me` xác thực đủ bằng chứng mà filter sử dụng; ví dụ này không chứng minh việc bật lưu session. Hai endpoint chỉ dùng GET, vì vậy không cần tắt CSRF để thử nghiệm.

## 6. “Được đi qua chain” khác “phải đăng nhập”

Đây là ranh giới cấu hình hay nhầm nhất, đặc biệt khi ứng dụng có nhiều luồng xác thực:

1. **Chọn chain:** `securityMatcher(...)` quyết định request nào thuộc một `SecurityFilterChain` / `SecurityWebFilterChain`. Khi có nhiều chain, Spring Security xét thứ tự ưu tiên và dùng chain phù hợp đầu tiên.
2. **Quyết định quyền trong chain:** `requestMatchers("/public").permitAll()` (Servlet) hoặc `pathMatchers("/public").permitAll()` (WebFlux) cho phép request công khai đi tiếp nhưng **không loại bỏ các authentication filter khác** của chain.
3. **Không có chain nào khớp:** HTTP request không được các chain Spring Security đó bảo vệ. Đây có thể là khoảng trống cấu hình nguy hiểm, không tương đương một quy tắc `permitAll` trong chain được quản lý.

Ví dụ ứng dụng có `/api/**` cho bearer token và `/web/**` cho form login: mỗi phần có thể dùng một chain riêng. Khi đó, phải có matcher và thứ tự rõ ràng; một chain quá rộng được ưu tiên trước có thể khiến chain còn lại không bao giờ chạy. Một request `GET /public` mang credential sai vẫn có thể bị filter từ chối trước khi quy tắc `permitAll` được áp dụng, tùy cơ chế bật trong chain.

Quy tắc HTTP cũng không thay thế authorization của business method. Với Servlet, bật `@EnableMethodSecurity` nếu cần `@PreAuthorize` trên service; với WebFlux dùng `@EnableReactiveMethodSecurity`, và thiết kế phương thức/reactive return type phù hợp. Thêm lớp kiểm tra ở service khi cùng nghiệp vụ được gọi từ nhiều điểm vào.

## 7. Phạm vi thời gian: session, Basic, bearer và backend khác

### Browser đăng nhập bằng session

Browser gửi credentials lần đầu. Nếu xác thực thành công và được cấu hình lưu vào session, client giữ cookie định danh phiên. Request sau vẫn **đi qua security chain**, nhưng server có thể khôi phục danh tính từ `HttpSession` (Servlet) hoặc `WebSession` (WebFlux), không phải người dùng phải nhập lại password. Thời hạn session khác thời hạn một context trong request. Logout, session timeout, cookie flags, CSRF và session fixation là các vấn đề bảo mật liên quan nhưng có chính sách riêng.

### API dùng Basic hoặc bearer token

HTTP Basic truyền credentials ở từng request; chỉ dùng qua HTTPS. Với bearer JWT, server thường kiểm tra token trong từng request (chữ ký/issuer/hạn dùng và chính sách liên quan), xây dựng `Authentication` hiện hành và kiểm tra quyền. JWT không tự yêu cầu session, cũng không có nghĩa resource server tự phát hành JWT. Header `Authorization` phải được giữ bí mật; không đặt token trong URL query hoặc log.

### Reverse proxy / API gateway

Nếu gateway xác thực người dùng rồi gửi thông tin xuống backend, backend phải có một **trust boundary** có thể kiểm chứng: kênh truyền được bảo vệ, quy tắc truy cập trực tiếp, hoặc chữ ký/mTLS thích hợp. Đừng tin trực tiếp header tự khai báo như `X-User-Id` từ mọi client. Spring Security ở backend chỉ biết bằng chứng mà backend thật sự kiểm tra.

### Scheduled job, WebSocket và message consumer

Một scheduled task hay message listener không tự có `SecurityContext` của HTTP request. WebSocket handshake có thể liên quan danh tính HTTP ban đầu, nhưng thời gian sống của kết nối/message cần chính sách riêng. Với tác vụ nền, hãy thiết kế service principal/token hoặc kiểm tra quyền cho chính điểm vào đó; đừng giữ reference tới context của request đã kết thúc.

## 8. Phạm vi giữa các thread và tác vụ bất đồng bộ

**Servlet:** `SecurityContextHolder` mặc định gắn vào `ThreadLocal`. Một lời gọi đồng bộ trong cùng request thường truy cập được danh tính; lời gọi chạy qua `@Async`/executor có thể không. Nếu nghiệp vụ cần mang danh tính người dùng qua boundary đó, dùng cơ chế propagation được hỗ trợ và kiểm soát thời điểm dọn context, tránh rò rỉ giữa các tác vụ.

**WebFlux:** context đi qua publisher/subscription. Chuỗi `flatMap`, `map` hoặc chuyển scheduler vẫn có thể truy cập Reactor Context khi ở đúng pipeline. Tuy nhiên, tự tạo một subscription mới ngoài ngữ cảnh hoặc gọi thư viện callback không lan truyền context có thể làm mất principal. Tránh `block()` trên event loop và không sửa vấn đề bằng cách đặt một `SecurityContextHolder` global.

Một câu hỏi hữu ích khi debug: **ai tạo execution boundary mới, và nó có chuyển danh tính được kiểm chứng sang boundary đó không?** Giải pháp phụ thuộc stack và semantics của công việc, không chỉ phụ thuộc tên phương thức Spring Security.

## 9. Chẩn đoán nhanh 401, 403 và context bị mất

| Hiện tượng | Kiểm tra |
| --- | --- |
| `401 Unauthorized` | Request chưa có/sai credentials, token sai/hết hạn, Basic challenge hoặc cơ chế authentication không thành công |
| `403 Forbidden` | Đã xác thực nhưng thiếu authority phù hợp; với request thay đổi trạng thái cũng kiểm tra CSRF và cấu hình tương ứng |
| URL đáng lẽ kín nhưng trả `200` | Chain matcher/thứ tự sai, có `permitAll` quá rộng hoặc request không khớp chain nào |
| Servlet mất principal khi chạy tác vụ async | `ThreadLocal` không tự theo executor/thread mới; xem cơ chế context propagation |
| WebFlux thấy principal rỗng ngoài pipeline | Đã tách subscription hoặc truy cập sai loại holder; cần Reactor Context |
| Custom login thành công nhưng request sau thành anonymous | Context chỉ đặt tạm, chưa lưu vào `SecurityContextRepository`/`ServerSecurityContextRepository` khi cần |
| Preflight `OPTIONS` lỗi trước khi đăng nhập | Cấu hình CORS tại gateway/chain, vì preflight thường không có credentials như request chính |
| Phân quyền trong service không chạy | Chưa bật method security, bean không đi qua proxy hoặc kiểu thực thi không phù hợp |

Khi debug, chỉ log metadata cần thiết như request path, status, dạng cơ chế auth và correlation ID. **Không log mật khẩu, cookie session, raw JWT hay toàn bộ header Authorization.** Đừng tắt CSRF trên ứng dụng có browser session/cookie chỉ để bỏ qua `403`.

## 10. Tự kiểm tra với một ứng dụng thực tế

Hãy xác minh tuần tự:

1. Project dùng Spring MVC/Servlet hay WebFlux/reactive? Đúng loại `SecurityFilterChain` hay `SecurityWebFilterChain` chưa?
2. Request đi vào đúng chain nào? Matcher và thứ tự ưu tiên có bao phủ mọi endpoint nhạy cảm không?
3. Ai là principal, credentials được lấy từ đâu và được kiểm tra bởi thành phần nào?
4. Context của lần gọi được nạp từ session hay tạo mới từ token? Chính sách lưu có phù hợp không?
5. Controller và service đang đọc context theo `ThreadLocal` hay Reactor Context? Các async boundary có làm mất nó không?
6. Bạn có kiểm chứng đường dẫn public (`200`), thiếu credentials (`401`), credentials hợp lệ (`200`) và thiếu quyền (`403` khi có luật role/authority) không?
7. Có điểm vào ngoài HTTP (job, message, gateway callback) cần cơ chế xác thực/ủy quyền độc lập không?

**Kết luận kiến thức:** Spring Security định danh người gọi tại ranh giới request đã được bảo vệ, rồi đưa danh tính vào `SecurityContext` để các bước tiếp theo sử dụng. Servlet mặc định chuyển context qua **thread**, WebFlux chuyển qua **Reactor subscription**. Session và token quyết định cách nhận diện lại người gọi ở request sau; chúng là một chiều khác với phạm vi thực thi của request hiện tại.

## Tài liệu tham khảo

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Servlet Authentication Persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security API — ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
