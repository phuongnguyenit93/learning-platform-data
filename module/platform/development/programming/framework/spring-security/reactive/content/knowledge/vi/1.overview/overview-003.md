# Mối quan hệ giữa Spring WebFlux, Reactor và Spring Security

## 1. Mục tiêu bài học

Sau bài này, bạn có thể giải thích vai trò riêng của Spring WebFlux, Project Reactor và Spring Security trong một ứng dụng HTTP reactive; mô tả yêu cầu đi qua bộ lọc bảo mật như thế nào; hiểu vì sao thông tin người dùng được truyền bằng Reactor Context; và tự chạy một API WebFlux có endpoint công khai và endpoint cần đăng nhập.

**Ý chính:** Spring WebFlux là tầng xử lý web; Reactor là nền tảng lập trình bất đồng bộ cho các chuỗi xử lý; Spring Security là tầng xác thực, phân quyền và bảo vệ request. Spring Security trên WebFlux phải tham gia vào chuỗi reactive của Reactor để kiểm soát truy cập đúng cách.

## 2. Ba thành phần giải quyết ba vấn đề khác nhau

| Thành phần | Nhiệm vụ chính | Khái niệm/API tiêu biểu |
| --- | --- | --- |
| **Spring WebFlux** | Tiếp nhận HTTP, định tuyến, đọc/ghi request-response và gọi handler theo mô hình bất đồng bộ, không chặn | `WebHandler`, `WebFilter`, `@RestController`, `RouterFunction`, `WebClient` |
| **Project Reactor** | Biểu diễn và kết hợp các phép xử lý có thể hoàn thành bất đồng bộ; hỗ trợ Reactive Streams và backpressure | `Mono<T>` (0 hoặc 1 phần tử), `Flux<T>` (0 đến nhiều phần tử), `map`, `flatMap`, `Context` |
| **Spring Security (reactive)** | Xác thực danh tính, quyết định quyền truy cập và cung cấp ngữ cảnh bảo mật trong chuỗi reactive | `SecurityWebFilterChain`, `ServerHttpSecurity`, `ReactiveAuthenticationManager`, `ReactiveSecurityContextHolder` |

WebFlux phụ thuộc vào `reactor-core` và thường trả về `Mono`/`Flux`. Chẳng hạn, một endpoint trả về `Mono<String>` mô tả công việc có thể tạo ra một chuỗi khi hoàn tất; framework quản lý việc đăng ký (subscribe) và ghi kết quả thành HTTP response. `Mono`/`Flux` không đồng nghĩa với việc tự động tạo thêm luồng thực thi (thread), và cũng không biến một lời gọi JDBC, `Thread.sleep` hay tác vụ I/O blocking thành non-blocking.

Spring Security có hai cách tích hợp phù hợp hai web stack: **Servlet/Spring MVC** và **Reactive/Spring WebFlux**. Bài này tập trung vào cách thứ hai. WebFlux có thể dùng controller gắn annotation hoặc functional endpoint; bộ lọc bảo mật reactive bảo vệ được cả hai.

## 3. Chúng kết nối với nhau khi có HTTP request

~~~text
Client gửi HTTP request
          |
          v
HTTP server (thường là Reactor Netty khi dùng Boot WebFlux starter)
          |
          v
Spring WebFlux: chuỗi WebFilter / WebHandler
          |
          v
Spring Security: WebFilterChainProxy
    -> chọn SecurityWebFilterChain phù hợp
    -> đọc thông tin đăng nhập và xác thực khi cần
    -> đưa SecurityContext vào Reactor Context
    -> kiểm tra quy tắc phân quyền
          |
          +-- bị từ chối --> phản hồi lỗi phù hợp (ví dụ 401/403)
          |
          v
WebFlux handler -> service -> Mono/Flux -> HTTP response
~~~

Đây là sơ đồ khái niệm, không phải danh sách chính xác hoặc thứ tự cố định của mọi filter. Một request có thể đi qua nhiều filter bảo mật tùy cấu hình; nếu có nhiều `SecurityWebFilterChain`, Spring Security chọn chain phù hợp theo matcher và thứ tự ưu tiên.

Diễn tiến cần hiểu:

1. **WebFlux tiếp nhận request** thông qua hạ tầng HTTP không chặn và chuỗi `WebFilter`.
2. **Spring Security được gắn vào WebFlux bằng `WebFilter`**; `WebFilterChainProxy` áp dụng các filter trong `SecurityWebFilterChain` đã chọn.
3. **Authentication (xác thực)**: với HTTP Basic trong ví dụ bên dưới, bộ lọc lấy credentials và dùng cơ chế authentication reactive; thông thường `ReactiveAuthenticationManager.authenticate(...)` trả về `Mono<Authentication>`. Không phải mọi cơ chế đăng nhập đều dùng cùng một bộ lọc.
4. **SecurityContext** chứa `Authentication` (principal, authorities, trạng thái xác thực) và được cung cấp cho chuỗi Reactor xử lý request.
5. **Authorization (phân quyền)**: quy tắc `permitAll`, `authenticated`, `hasRole`, ... quyết định có cho request đi tiếp hay không.
6. **Handler chạy và tạo kết quả** dưới dạng `Mono`/`Flux`; WebFlux ghi response khi chuỗi hoàn thành hoặc xử lý lỗi nếu chuỗi thất bại.

**Phân biệt:** Authentication trả lời “Bạn là ai?”; Authorization trả lời “Bạn được phép làm gì?”. Không nên kết luận một request được quyền truy cập chỉ vì đã đăng nhập thành công.

## 4. Vì sao Reactor Context đặc biệt quan trọng với Security?

Ở cách xử lý Servlet truyền thống, code thường đọc `SecurityContextHolder` trong ngữ cảnh thread đang xử lý request; chiến lược mặc định của nó dựa vào `ThreadLocal`. Trong mô hình reactive, một luồng xử lý có thể chuyển thread khi thực hiện các operator hoặc khi I/O hoàn tất. Do đó, lấy “người dùng hiện tại” chỉ dựa trên thread rất dễ sai.

**Reactor Context** gắn dữ liệu với **subscription của chuỗi Reactor**, thay vì với một thread. Spring Security reactive dùng `ReactiveSecurityContextHolder` để truy cập `SecurityContext` thông qua cơ chế này. Khi chuỗi vẫn ở trong phạm vi Reactor Context thích hợp, các operator có thể tiếp cận cùng thông tin bảo mật ngay cả khi đổi thread.

Ví dụ đọc tên người đang đăng nhập bên trong một chuỗi reactive:

~~~java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
}
~~~

Đây là **đoạn minh họa bên trong một lớp có đủ import**, chưa phải chương trình độc lập. `getContext()` trả về `Mono<SecurityContext>`; nếu không có context, chuỗi có thể hoàn thành mà không phát ra giá trị. Đoạn này phù hợp trong request đã được xác thực; không thay thế bước phân quyền.

Khi cần đặt authentication cho một chuỗi reactive tự dựng (ví dụ trong test), có thể dùng:

~~~java
Authentication auth = new UsernamePasswordAuthenticationToken(
        "demo", "N/A", List.of(new SimpleGrantedAuthority("ROLE_USER")));

Mono<String> username = ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));
~~~

Đoạn minh họa thứ hai giả định các import tương ứng từ `org.springframework.security.authentication`, `org.springframework.security.core.authority`, `org.springframework.security.core.context`, `java.util` và Reactor. Khi subscribe `username`, chuỗi phát ra `demo`. `contextWrite(...)` đưa authentication vào Context mà các operator ở phía trên nhìn thấy; việc gọi `contextWrite` không tự xác thực credentials.

Trong ứng dụng WebFlux có Spring Security, hạ tầng security thiết lập context cho request theo cơ chế đã cấu hình; thường **không phải tự gọi `contextWrite` trong mỗi controller**. Cũng không dùng `SecurityContextHolder.getContext()` kiểu Servlet để thay thế `ReactiveSecurityContextHolder.getContext()`.

## 5. Ví dụ chạy được với Java 17+ và Spring Boot WebFlux

### 5.1. Tạo project

Tại [Spring Initializr](https://start.spring.io/), chọn **Maven**, **Java 17 trở lên**, phiên bản Spring Boot ổn định tương thích với Java đã chọn, group `com.example` và artifact `reactive-security-demo`. Thêm hai dependency:

- **Spring Reactive Web** (`spring-boot-starter-webflux`): WebFlux và Reactor.
- **Spring Security** (`spring-boot-starter-security`): bảo mật reactive cho ứng dụng WebFlux.

Không thêm `spring-boot-starter-web`/MVC vào project minh họa. Nếu cần kiểm tra `pom.xml` do Initializr sinh ra, phần dependencies cốt lõi có dạng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
</dependencies>
~~~

Đây là **đoạn dependencies** để đối chiếu, không phải toàn bộ `pom.xml`. File build hoàn chỉnh và phiên bản dependency được Spring Initializr quản lý.

### 5.2. Tạo file Java

Thay mã tại `src/main/java/com/example/reactivesecuritydemo/ReactiveSecurityDemoApplication.java` (hoặc dùng đúng package mà Initializr đã tạo; giữ đường dẫn, dòng `package` và tên class khớp nhau) bằng:

~~~java
package com.example.reactivesecuritydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveSecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityDemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/user").hasRole("USER")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers() {
        UserDetails user = User.withUsername("demo")
                .password("{noop}demo123")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(user);
    }

    @RestController
    static class DemoController {

        @GetMapping("/public")
        Mono<String> publicEndpoint() {
            return Mono.just("Cong khai");
        }

        @GetMapping("/user")
        Mono<String> userEndpoint() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(SecurityContext::getAuthentication)
                    .map(authentication -> "Xin chao, " + authentication.getName());
        }
    }
}
~~~

Trong đó:

- `@EnableWebFluxSecurity` bật cấu hình security cho WebFlux; `SecurityWebFilterChain` định nghĩa chính sách HTTP.
- `ServerHttpSecurity` là API cấu hình security của reactive stack; `authorizeExchange` xét quyền theo request.
- `/public` cho phép truy cập không cần đăng nhập; `/user` yêu cầu quyền `ROLE_USER` vì `hasRole("USER")` kiểm tra authority tương ứng; các đường dẫn khác yêu cầu authenticated.
- `httpBasic` nhận username/password từ HTTP Basic. `MapReactiveUserDetailsService` cung cấp một tài khoản trong bộ nhớ, đủ để thử nghiệm mà không cần database.
- Controller trả về `Mono<String>`. Endpoint `/user` lấy danh tính từ `ReactiveSecurityContextHolder`, qua đó thể hiện sự phối hợp giữa Reactor và Spring Security.
- `formLogin` được tắt để ví dụ chỉ sử dụng HTTP Basic, không chuyển sang form đăng nhập. **CSRF vẫn giữ cấu hình mặc định**; ví dụ chỉ có HTTP GET nên không cần điều chỉnh. Chuỗi `"{noop}"` chỉ dùng để tránh thiết lập password encoder trong bài thực hành; **không sử dụng mật khẩu dạng rõ trong môi trường thật**.

### 5.3. Chạy và kiểm chứng

Ở thư mục project (nơi có `pom.xml`), chạy lệnh phù hợp với hệ điều hành:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell hoặc Command Prompt, dùng `.\mvnw.cmd spring-boot:run`. Sau khi server khởi động tại `http://localhost:8080`, chạy ở terminal khác:

~~~bash
curl -s http://localhost:8080/public
curl -s -u demo:demo123 http://localhost:8080/user
curl -i http://localhost:8080/user
~~~

Kết quả nội dung hai request đầu theo thứ tự là:

~~~text
Cong khai
Xin chao, demo
~~~

Lệnh cuối (không gửi credentials) nhận **HTTP 401 Unauthorized** với cấu hình HTTP Basic; các header và body cụ thể có thể thay đổi theo phiên bản/cấu hình. Nếu user đã xác thực nhưng không đủ quyền, kết quả thông thường là **HTTP 403 Forbidden**. Để thử tình huống 403, cần thêm một tài khoản hoặc quy tắc phân quyền tương ứng; ví dụ hiện có một user mang `ROLE_USER` nên không tự tạo ra 403.

### 5.4. Đối chiếu với mục tiêu học tập

- **WebFlux** nhận `GET /user` và đưa request tới filter chain, rồi controller nếu được cho phép.
- **Spring Security** kiểm tra HTTP Basic, tạo `Authentication` và xét `hasRole("USER")`.
- **Reactor** cung cấp `Mono` cho cả những bước bất đồng bộ và cho phần trả về controller; `ReactiveSecurityContextHolder` đọc authentication từ Reactor Context.
- **Kết quả**: không có credentials → 401; credentials đúng → controller phản hồi tên người dùng.

## 6. Khi viết ứng dụng thực tế cần nhớ

### 6.1. Chọn đúng API reactive

| Phong cách Servlet/MVC | Tương ứng khi dùng WebFlux |
| --- | --- |
| `HttpSecurity` + `SecurityFilterChain` | `ServerHttpSecurity` + `SecurityWebFilterChain` |
| `Filter` / `HttpServletRequest` | `WebFilter` / `ServerWebExchange` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| `SecurityContextHolder` (thường gắn thread) | `ReactiveSecurityContextHolder` (Reactor Context) |

Hai stack có nhiều khái niệm giống nhau nhưng **không hoán đổi trực tiếp các bean và filter**. Nếu cấu hình nhầm `SecurityFilterChain` kiểu Servlet cho ứng dụng WebFlux, request reactive không được bảo vệ theo cách kỳ vọng.

### 6.2. Reactive không làm mọi tác vụ tự nhiên trở thành non-blocking

`Mono.just(blockingCall())` vẫn thực thi `blockingCall()` ngay khi tạo `Mono`; đây không phải giải pháp tránh chặn event loop. Với database, HTTP client hoặc authentication từ hệ thống ngoài, ưu tiên API reactive thực sự (ví dụ R2DBC, WebClient, `ReactiveAuthenticationManager`). Nếu buộc phải tích hợp thư viện blocking, hãy cô lập có chủ đích trên scheduler thích hợp (thường `Schedulers.boundedElastic()`), đo tải và bảo vệ giới hạn tài nguyên. Không tùy tiện gọi `block()` bên trong handler hoặc security filter reactive.

### 6.3. Context không phải biến toàn cục

`ReactiveSecurityContextHolder` phụ thuộc vào chuỗi Reactor đang được subscribe. Nếu tách xử lý ra thread thủ công, `CompletableFuture` độc lập hoặc callback bên ngoài chuỗi mà không truyền context đúng cách, không được giả định authentication tự xuất hiện. Reactor Context không đồng nghĩa với servlet session, không phải cơ chế tự động lưu user vĩnh viễn và không dùng để chia sẻ dữ liệu giữa các request độc lập.

### 6.4. Bảo vệ endpoint thôi chưa đủ

Phân quyền ở `authorizeExchange` bảo vệ request theo đường dẫn/phương thức HTTP. Với nghiệp vụ cần quyền theo đối tượng (ví dụ chỉ xem đơn hàng của chính mình), service vẫn phải kiểm tra quyền sở hữu hoặc chính sách tương ứng. Reactive method security có thể bật qua `@EnableReactiveMethodSecurity` cho nhu cầu thích hợp; method security reactive dựa vào Reactor Context và đặc biệt cần chú ý các phương thức trả về `Publisher` (`Mono`/`Flux`).

### 6.5. Cấu hình cho môi trường thực tế

- Dùng HTTPS; không hard-code username/password, không dùng `{noop}`; lưu password bằng bộ mã hóa mật khẩu phù hợp.
- Chọn rõ cơ chế xác thực: session/cookie, HTTP Basic, OAuth2 login hoặc JWT resource server; mỗi lựa chọn đòi hỏi cấu hình security khác nhau.
- Giữ CSRF protection khi có nguy cơ request giả mạo từ trình duyệt; chỉ vô hiệu hóa sau khi đánh giá mô hình xác thực và bề mặt tấn công của API.
- Định nghĩa quy tắc từ cụ thể tới tổng quát, kiểm tra cả endpoint công khai lẫn endpoint yêu cầu role; ghi nhớ mặc định `anyExchange().authenticated()` chỉ là một chính sách, không tự diễn đạt quyền nghiệp vụ.
- Nếu ứng dụng Boot có cả starter MVC và WebFlux, Spring Boot thường chọn cấu hình **MVC** theo mặc định. Hãy xác định web application type thực tế trước khi kết luận `SecurityWebFilterChain` đang được dùng.

## 7. Những lỗi hiểu sai thường gặp

1. **“Dùng Mono là request đã bất đồng bộ hoàn toàn.”** Sai: một operator có thể gọi blocking I/O; cần xem nguồn dữ liệu và cách thực thi.
2. **“Mỗi request reactive luôn chạy trên một thread cố định.”** Sai: scheduler và các ranh giới bất đồng bộ có thể thay đổi thread; dùng Reactor Context để mang thông tin bảo mật.
3. **“Đặt `hasRole` trong controller là đủ.”** Cấu hình HTTP authorization ở security chain chặn truy cập sớm; kiểm tra quyền nghiệp vụ vẫn thuộc tầng phù hợp.
4. **“`permitAll` bỏ qua mọi filter bảo mật.”** Sai: nó cho phép request qua bước authorization tương ứng; những filter khác vẫn có thể chạy theo cấu hình.
5. **“Có Spring Security dependency thì endpoint chắc chắn được bảo vệ đúng ý.”** Dependency có thể kích hoạt bảo vệ mặc định, nhưng chính sách cần được xác định rõ, kiểm thử và phù hợp reactive/servlet stack.
6. **“Có thể lấy Principal từ `ThreadLocal` ở bất cứ đâu.”** Sai trong chuỗi Reactor; hãy đọc qua API reactive được framework hỗ trợ.

## 8. Câu hỏi tự kiểm tra

**Câu 1.** Nếu WebFlux có thể xử lý HTTP mà không cần Spring Security, tại sao vẫn thêm Spring Security?

**Trả lời:** WebFlux quản lý giao thức và handler; Spring Security bổ sung xác thực, phân quyền và các cơ chế bảo vệ. Reactor hỗ trợ cách các bước bảo mật chạy cùng chuỗi bất đồng bộ.

**Câu 2.** Hai endpoint cùng trả về `Mono<String>`. Vì sao `/public` truy cập được mà `/user` không thể thiếu credentials?

**Trả lời:** Sự khác nhau nằm ở `SecurityWebFilterChain`: `permitAll` áp dụng cho `/public`, còn `hasRole("USER")` áp dụng cho `/user`. Kiểu trả về `Mono` không quyết định quyền truy cập.

**Câu 3.** Nếu xử lý chuyển sang thread khác trong chuỗi Reactor, nên đọc user hiện tại bằng gì?

**Trả lời:** `ReactiveSecurityContextHolder.getContext()` hoặc cơ chế Principal reactive do WebFlux/Spring Security cung cấp. Đừng mặc định `ThreadLocal` vẫn đúng.

**Câu 4.** Đổi từ `MapReactiveUserDetailsService` sang kho dữ liệu thật cần lưu ý điều gì?

**Trả lời:** Cần giải pháp đọc dữ liệu và xác thực phù hợp với luồng reactive, có xử lý lỗi, mật khẩu an toàn và quy tắc quyền đúng nghiệp vụ; tránh gọi database blocking trực tiếp trên event loop.

## 9. Tài liệu chính thức để đọc thêm

- [Spring Framework — WebFlux: Reactive Libraries](https://docs.spring.io/spring-framework/reference/web/webflux-reactive-libraries.html)
- [Spring Framework — WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
