# Vai trò của @EnableWebSecurity, @EnableWebFluxSecurity và cấu hình tự động

> **Điểm cần nhớ:** `@EnableWebSecurity` và `@EnableWebFluxSecurity` kích hoạt cơ sở hạ tầng cấu hình bảo mật web của **Spring Security** cho hai mô hình chạy khác nhau. **Spring Boot auto-configuration** giúp phát hiện dependency, tạo các bean mặc định khi thích hợp và đăng ký cơ chế bảo mật. Còn **`SecurityFilterChain`/`SecurityWebFilterChain` do lập trình viên viết** mới là nơi bạn định nghĩa chính sách cụ thể như URL nào công khai, URL nào cần quyền nào và dùng phương thức xác thực gì. Ba tầng này liên quan nhưng không đồng nghĩa.

Bài học thuộc nhóm **Cấu hình hiện đại** trong module **Spring Security – fundamentals**. Phạm vi chính: Spring Boot 3.5.x, Spring Security 6.5.x, Java 17 trở lên, ứng dụng Servlet/Spring MVC và Reactive/Spring WebFlux. Với Spring Boot 4.x / Spring Security 7.x, kiểm tra lại starter, DSL và tài liệu migration trước khi chuyển nguyên mã.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nói chính xác `@EnableWebSecurity` làm gì trong ứng dụng Servlet và `@EnableWebFluxSecurity` làm gì trong ứng dụng WebFlux.
2. Phân biệt **enable security infrastructure**, **auto-configuration của Spring Boot**, **bean filter chain tự khai báo** và **hệ thống user/credential**.
3. Giải thích vì sao một Spring Boot app chỉ thêm `spring-boot-starter-security` đã yêu cầu đăng nhập mà không cần tự thêm annotation.
4. Hiểu “back off” theo điều kiện bean: tự tạo `SecurityFilterChain` khác với tự tạo `UserDetailsService`; bản WebFlux có các loại bean tương ứng.
5. Xác định đúng stack khi project chứa cả `spring-boot-starter-web` lẫn `spring-boot-starter-webflux`.
6. Viết và kiểm thử hai dự án nhỏ độc lập, một dùng `HttpSecurity`/`MockMvc` và một dùng `ServerHttpSecurity`/`WebTestClient`.
7. Tránh các hiểu nhầm như “thêm annotation là API tự cho phép”, “định nghĩa user là đã định nghĩa quyền HTTP”, “`@EnableWebFlux` tương đương `@EnableWebFluxSecurity`”, hoặc “SecurityFilterChain tự bật method security”.

## 2. Bốn lớp trách nhiệm, nhìn từ ngoài vào trong

```text
pom.xml / classpath
  |
  +-- spring-boot-starter-web          -> ứng dụng Servlet/Spring MVC
  |               hoặc
  +-- spring-boot-starter-webflux      -> ứng dụng WebFlux/reactive
  |
  +-- spring-boot-starter-security
             |
             v
    SPRING BOOT AUTO-CONFIGURATION
    - phát hiện loại ứng dụng web và bean đã tồn tại
    - bật/tích hợp cấu hình Spring Security khi điều kiện phù hợp
    - cung cấp web security mặc định và user mặc định nếu còn thiếu
             |
             v
    SPRING SECURITY WEB INFRASTRUCTURE
    Servlet: @EnableWebSecurity
       -> FilterChainProxy, HttpSecurity, SecurityFilterChain
    Reactive: @EnableWebFluxSecurity
       -> WebFilterChainProxy, ServerHttpSecurity, SecurityWebFilterChain
             |
             v
    APPLICATION SECURITY POLICY
    - SecurityFilterChain / SecurityWebFilterChain @Bean
    - authorizeHttpRequests / authorizeExchange
    - formLogin, httpBasic, oauth2ResourceServer, csrf, cors...
    - UserDetailsService / ReactiveUserDetailsService / provider riêng
             |
             v
    REQUEST -> filters -> controller/handler -> service/domain policy
```

Sơ đồ giúp phân định trách nhiệm, **không phải** thứ tự chính xác mọi class được Spring tạo lúc runtime. Spring Boot và Spring Security đều có conditional configuration, nên cùng một dependency có thể dẫn đến tập bean khác nhau khi bạn tự khai báo bean hoặc thêm OAuth2, actuator, session manager.

### 2.1. Bảng “ai chịu trách nhiệm việc gì?”

| Thành phần | Vai trò chính | Không tự làm thay việc gì? |
| --- | --- | --- |
| `@EnableWebSecurity` | Kích hoạt cấu hình bảo mật **Servlet** của Spring Security, tích hợp các `SecurityFilterChain` | Không tự định nghĩa permission theo nghiệp vụ, user database hay JWT issuer |
| `@EnableWebFluxSecurity` | Kích hoạt cấu hình bảo mật **reactive WebFlux**, tích hợp `SecurityWebFilterChain` | Không chuyển Servlet filter thành WebFilter, không tạo policy tài nguyên |
| Spring Boot `SecurityAutoConfiguration` và web configuration liên quan | Điều kiện hóa, nhập cấu hình và cung cấp **mặc định** Servlet khi phù hợp | Không giữ nguyên default chain nếu bạn chủ động thay web security configuration |
| Spring Boot `ReactiveSecurityAutoConfiguration` | Điều kiện hóa cấu hình Spring Security cho WebFlux | Không biến một app MVC thành WebFlux |
| `UserDetailsServiceAutoConfiguration` | Có thể tạo user in-memory `user` với password ngẫu nhiên ở Servlet | Không cấp quyền business hoặc tự sinh tài khoản production |
| `ReactiveUserDetailsServiceAutoConfiguration` | Có thể tạo reactive user in-memory mặc định cho WebFlux | Không thay thế OAuth2/JWT authentication provider đã được cấu hình |
| `SecurityFilterChain` | Bộ filter và policy web cho **Servlet request** | Không tự bảo vệ message listener/job nằm ngoài web filter |
| `SecurityWebFilterChain` | Bộ reactive `WebFilter`/policy web cho WebFlux exchange | Không dùng được như `SecurityFilterChain` trong app Servlet |
| `@EnableMethodSecurity` | Bật method authorization kiểu imperative, như `@PreAuthorize` | Không có hiệu lực chỉ vì đã bật `@EnableWebSecurity` |
| `@EnableReactiveMethodSecurity` | Bật method authorization reactive phù hợp publisher | Không thay thế `@EnableWebFluxSecurity` cho HTTP boundary |

**Mẹo để không lẫn:** annotation “enable” quyết định **hạ tầng framework**; bean “chain” quyết định **bảo vệ HTTP như thế nào**; user store/provider quyết định **cách xác minh danh tính**; method/domain policy quyết định **thao tác trên đối tượng nào được phép**.

## 3. @EnableWebSecurity: kích hoạt cấu hình web Servlet

### 3.1. Cơ chế ở Spring Security

`@EnableWebSecurity` thuộc package:

```java
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
```

Khi dùng trên class `@Configuration` trong ứng dụng Servlet, annotation nhập các cấu hình cần thiết để Spring Security có thể tạo và quản lý bộ lọc web, với Servlet filter tên thường gặp `springSecurityFilterChain`. Bên trong, `FilterChainProxy` chọn một `SecurityFilterChain` cho request; mỗi chain chứa các filter theo cơ chế bạn cấu hình.

```text
Servlet container / DispatcherServlet
    ^
    |
    +-- Servlet FilterChain
          |
          +-- DelegatingFilterProxy (springSecurityFilterChain)
                  |
                  +-- FilterChainProxy
                        |
                        +-- SecurityFilterChain #1 (matcher...)
                        +-- SecurityFilterChain #2 (matcher...)
                        |
                        +-- filter thực tế của chain được chọn
```

Ví dụ cấu hình rõ ràng:

```java
@Configuration
@EnableWebSecurity
class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Đây là **snippet**: còn thiếu import, ứng dụng Spring Boot và các bean khác; mã đầy đủ ở mục 8. Trong Servlet, `HttpSecurity` là builder; `http.build()` tạo `SecurityFilterChain`. Annotation **không đặt rule `/public`**; chính dòng `authorizeHttpRequests(...)` mới thực hiện việc đó.

### 3.2. Với Spring Boot, có cần ghi annotation không?

Trong ứng dụng **Spring Boot Servlet thông dụng**, chỉ cần `spring-boot-starter-security` trên classpath là Boot đã tự bật cấu hình Spring Security mặc định khi các điều kiện auto-configuration được thỏa. Vì vậy **không cần tự thêm `@EnableWebSecurity` chỉ để có một ứng dụng được bảo vệ mặc định**. Việc đặt annotation khi viết cấu hình Java tường minh có thể giúp người đọc biết mục đích của class, nhưng không phải dấu hiệu “nếu thiếu annotation thì Boot hoàn toàn không chạy security”.

Một bài thực hành:

1. Tạo Boot MVC app chỉ có Spring Web + Spring Security starter và một `@GetMapping("/hello")`.
2. **Chưa khai báo `SecurityFilterChain`, `UserDetailsService` hay `@EnableWebSecurity`**.
3. Chạy ứng dụng; nếu Boot default conditions hợp lệ, `GET /hello` anonymous bị yêu cầu đăng nhập, log có thể có password được sinh cho user `user`.
4. Thêm một `SecurityFilterChain` bean và test hành vi theo rule bạn định nghĩa; điều này tác động đến **web security defaults**.
5. Thêm `UserDetailsService` bean riêng nếu bạn muốn thay nguồn user; thay đổi này tác động đến **authentication defaults**.

**Trong ứng dụng Spring Framework không dùng Boot**, bạn cần tự thiết lập security infrastructure và đăng ký filter phù hợp với Servlet container, ví dụ qua `@EnableWebSecurity` và `AbstractSecurityWebApplicationInitializer` hoặc cơ chế registration tương đương. Không nên lấy sự tiện lợi của Boot làm quy tắc tuyệt đối cho mọi ứng dụng Spring.

### 3.3. Annotation có thay thế bean filter chain không?

Không. Khi bật cấu hình web security, Spring Security có thể cung cấp chính sách bảo mật mặc định nếu chưa có chain tự định nghĩa. Nhưng nếu bạn cần **permitAll riêng**, **hasRole cho admin**, **Bearer token cho API** hay **đổi CSRF/session**, bạn phải cấu hình chain và các thành phần cần thiết. Annotation không tự suy ra rằng `/api/payments` phải có `PAYMENT_WRITE`.

Tương tự, `@EnableWebSecurity` **không kích hoạt `@PreAuthorize` thay cho `@EnableMethodSecurity`**. Với Spring Security 6, method security là tính năng bật riêng:

```java
@Configuration
@EnableMethodSecurity
class MethodAuthorizationConfig {
    // Các method được gắn @PreAuthorize, @PostAuthorize...
}
```

`@EnableMethodSecurity` không làm mọi method tự động có permission. Method cần policy rõ ràng, lời gọi phải đi qua cơ chế chặn/proxy phù hợp; logic trên từng owner/tenant vẫn do domain layer bảo đảm.

## 4. @EnableWebFluxSecurity: kích hoạt cấu hình bảo mật reactive

### 4.1. Khác với @EnableWebSecurity ở đâu?

`@EnableWebFluxSecurity` thuộc package:

```java
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
```

Nó nhập infrastructure Spring Security **WebFlux**, cho phép xây một hoặc nhiều `SecurityWebFilterChain` từ `ServerHttpSecurity`. Không được dùng `HttpSecurity`/`SecurityFilterChain` để thay cho bộ bảo mật của WebFlux.

```text
WebFlux HTTP handler
    |
    v
WebFilterChainProxy
    |
    +-- Chọn SecurityWebFilterChain phù hợp
    |
    +-- Reactive WebFilters
    |      authentication, CSRF, security context,
    |      authorization, headers, ...
    |
    v
DispatcherHandler / RouterFunction
    |
    v
Reactive Controller / Handler -> Mono / Flux
```

Một cấu hình tường minh:

```java
@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {
    @Bean
    SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Đây cũng chỉ là **snippet**; ứng dụng hoàn chỉnh ở mục 9. `authorizeExchange(...)`/`pathMatchers(...)` thay cho DSL Servlet `authorizeHttpRequests(...)`/`requestMatchers(...)`. Với nhiều chain, reactive dùng `ServerWebExchangeMatcher`, trong khi Servlet dùng `RequestMatcher`.

### 4.2. Reactive SecurityContext không đồng nhất với ThreadLocal Servlet

Servlet thường dùng `SecurityContextHolder` dựa trên `ThreadLocal` của luồng request. Trong WebFlux, luồng xử lý có thể chuyển thread; thông tin bảo mật được truy xuất qua `ReactiveSecurityContextHolder` trong **Reactor Context**. Viết custom reactive code dựa vào `SecurityContextHolder.getContext()` như Servlet dễ làm mất identity. Reactive service nên dùng publisher-aware APIs hoặc nhận identity đã kiểm chứng từ boundary phù hợp.

### 4.3. WebFlux auto-configuration trong Spring Boot

Boot có `ReactiveSecurityAutoConfiguration` và `ReactiveUserDetailsServiceAutoConfiguration` riêng. Khi bạn dùng `spring-boot-starter-webflux` + security starter, Boot có thể cung cấp reactive web security mặc định và tài khoản phát sinh nếu chưa có cấu hình tương ứng. `@EnableWebFluxSecurity` hữu ích khi tự cấu hình tường minh hoặc không dùng Boot, nhưng **không phải điều kiện duy nhất để một Boot WebFlux application có security**.

Hơn nữa:

- Spring Security WebFlux dựa trên `WebFilter`, có thể chạy với Reactor Netty hoặc Servlet-based server trong chế độ WebFlux; tên WebFlux nói về **lập trình reactive**, không chỉ tên web server.
- `@EnableWebFlux` thuộc **Spring Framework**, bật cấu hình WebFlux MVC-equivalent; nó **không thay** `@EnableWebFluxSecurity`, và sử dụng tùy tiện còn có thể làm Boot WebFlux auto-configuration nhường quyền.
- `@EnableWebMvc` cũng thuộc Spring MVC; **không** phải cách bật Spring Security Servlet.
- Với reactive method authorization cần `@EnableReactiveMethodSecurity`, không dùng việc đã bật web filter như bằng chứng method policy hoạt động.

## 5. Boot auto-configuration: có những gì mặc định?

### 5.1. Servlet/MVC mặc định

Với Spring Boot 3.5, nếu có Spring Security trên classpath, ứng dụng web thường được bảo vệ ngay cả khi không có custom configuration. Theo tài liệu Boot, mặc định có thể gồm:

- `UserDetailsService` in-memory chứa user tên `user` và mật khẩu sinh ngẫu nhiên, được ghi vào log ở mức WARN khi khởi động; chỉ dùng development.
- Form login hoặc HTTP Basic tùy cách client gửi request (ví dụ `Accept`), yêu cầu authenticated cho ứng dụng web.
- `DefaultAuthenticationEventPublisher` cho sự kiện xác thực.
- Những filter bảo vệ HTTP do Spring Security thiết lập (CSRF, security headers, session behavior...) theo cấu hình mặc định phù hợp.

Các hành vi này chịu **điều kiện auto-configuration**: nếu thư viện OAuth2/SAML, bean custom, test profile hoặc property đã thay đổi, danh sách thực tế có thể khác. Đừng dựa vào một dòng log làm bằng chứng đầy đủ về security chain; hãy viết test HTTP.

Bài học về mặc định:

```java
// Ứng dụng Boot MVC đơn giản chỉ có @SpringBootApplication
// + spring-boot-starter-web + spring-boot-starter-security.
// Không cần tự gắn @EnableWebSecurity để thấy default web security.
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Nếu chưa có chain/user/provider khác, Boot tạo những thành phần phù hợp. Tuy nhiên, để code trên biên dịch độc lập cần package/import và tệp pom.xml; ví dụ đầy đủ ở phần thực hành.

### 5.2. WebFlux mặc định

Trong WebFlux, Boot có thể tạo `ReactiveUserDetailsService` và reactive security pipeline với user mặc định và quy tắc yêu cầu đăng nhập. Tập loại bean cần phân biệt gồm:

- `SecurityWebFilterChain`: policy và filters cho từng reactive exchange.
- `WebFilterChainProxy`: điều phối các reactive chains.
- `ReactiveUserDetailsService` / `ReactiveAuthenticationManager`: xác thực người dùng trong thế giới reactive.
- `ServerHttpSecurity`: builder cho chain.

Đừng dùng `UserDetailsService` Servlet thay cho `ReactiveUserDetailsService` rồi cho rằng Boot đã tạo reactive authentication đúng. Nếu đang dùng JWT Resource Server, reactive decoder và `ReactiveAuthenticationManager` có những yêu cầu riêng; không nên lấy sự hiện diện của generated user làm mô hình production.

### 5.3. Default user có thể được cấu hình bằng property, nhưng không phải ACL

Trong lab dùng default user, có thể cấu hình:

```properties
spring.security.user.name=student
spring.security.user.password=local-demo-password
spring.security.user.roles=USER
```

**Chỉ dùng cho development/test cục bộ.** Khi bạn tự cung cấp `UserDetailsService` hoặc reactive equivalent, Boot có thể không tạo default user nữa. Các property này **không thiết lập URL authorization**. Việc đặt `roles=ADMIN` cho một user chỉ cấp authority theo cơ chế default user store, không tự tạo API admin và không thay rule HTTP.

Ở production, lưu mật khẩu cấu hình plaintext trong Git là không an toàn; dùng identity provider/secret management và bảo vệ credential qua HTTPS.

## 6. “Back off” là gì, và bean nào khiến mặc định thay đổi?

Spring Boot dùng các điều kiện như `@ConditionalOnMissingBean` để cung cấp một thành phần **chỉ khi ứng dụng chưa tự định nghĩa thành phần tương ứng**. Vì vậy, “tôi đã tùy chỉnh Spring Security” có thể nghĩa là nhiều việc rất khác nhau.

| Việc ứng dụng làm | Điều thường bị thay đổi | Điều **không nên** tự suy ra |
| --- | --- | --- |
| Chỉ thêm security starter | Boot bật web security defaults khi đủ điều kiện | User nghiệp vụ đã được tích hợp |
| Chỉ thêm `@EnableWebSecurity` trong Boot MVC | Yêu cầu nạp hạ tầng Servlet security (đã được Boot hỗ trợ ở cấu hình chuẩn) | API được public hay có custom permission |
| Chỉ thêm `@EnableWebFluxSecurity` trong Boot WebFlux | Yêu cầu nạp hạ tầng reactive security | Đây là Servlet chain hoặc URL đã có role cụ thể |
| Tự khai báo `SecurityFilterChain` | Boot nhường **default web security policy** ở Servlet | Boot cũng tự tắt default `UserDetailsService` |
| Tự khai báo `UserDetailsService`, `AuthenticationProvider` hoặc `AuthenticationManager` | Có thể khiến **default user** Servlet không được tạo | Default web chain nhất định đã bị tắt |
| Tự khai báo `SecurityWebFilterChain` | Tùy chỉnh rule/filter cho WebFlux | Reactive default user chắc chắn biến mất |
| Tự khai báo `ReactiveUserDetailsService` hoặc `ReactiveAuthenticationManager` | Có thể khiến reactive generated user không được tạo | Chain HTTP của WebFlux đã được sửa |
| Thêm OAuth2 Client / Resource Server / SAML dependency | Có thể thay điều kiện default user/identity | Có thể bỏ cấu hình issuer, audience, token validation |
| Thêm `@EnableMethodSecurity`/`@EnableReactiveMethodSecurity` | Bật framework method authorization phù hợp | Mọi service method mặc nhiên bị chặn |

**Chi tiết kỹ thuật trong Spring Boot 3.5:**

- Servlet: Tài liệu Boot ghi rõ việc **khai báo bean `SecurityFilterChain`** thay default web security configuration, **không tự tắt** `UserDetailsService`. Default user store có điều kiện riêng; các bean `UserDetailsService`, `AuthenticationProvider`, `AuthenticationManager` hoặc một số module security trên classpath có thể làm nó back off.
- WebFlux: Boot dùng `ReactiveSecurityAutoConfiguration` cho web security và `ReactiveUserDetailsServiceAutoConfiguration` cho user store. Tài liệu nêu cách tắt hẳn default web security configuration bằng bean `WebFilterChainProxy` và cách **tùy chỉnh access rules bằng `SecurityWebFilterChain`**. Đây là hai loại bean khác nhau, không nên diễn giải máy móc rằng custom `SecurityWebFilterChain` đồng nghĩa xóa cả hạ tầng reactive.
- Với cả hai: thứ tự điều kiện trong auto-config và thành phần hiện hữu mới quyết định bean nào được tạo. Dùng log, `ConditionEvaluationReport` và test thực tế để xác minh thay vì phỏng đoán từ một annotation.

Một ví dụ quan trọng:

```text
Case A: Custom chain, không custom UserDetailsService
   -> Web policy thay đổi
   -> Generated user có thể vẫn xuất hiện

Case B: Custom UserDetailsService, không custom chain
   -> Nguồn người dùng thay đổi
   -> Web policy mặc định vẫn có thể yêu cầu authenticated

Case C: Custom cả chain và user store
   -> Chủ động định nghĩa cả rule HTTP lẫn authentication
```

Đây là cách phân chia nhiệm vụ, không phải lời hứa tuyệt đối trong mọi project phụ thuộc vào classpath.

## 7. Chọn đúng web stack trước khi chọn annotation

### 7.1. Đối chiếu Servlet và WebFlux

| Điểm so sánh | Servlet/MVC | WebFlux/reactive |
| --- | --- | --- |
| Starter web chính | `spring-boot-starter-web` | `spring-boot-starter-webflux` |
| Annotation security thủ công | `@EnableWebSecurity` | `@EnableWebFluxSecurity` |
| Builder | `HttpSecurity` | `ServerHttpSecurity` |
| Bean rule/filter chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Proxy xử lý web request | `FilterChainProxy` + Servlet filter integration | `WebFilterChainProxy` |
| Rule request | `authorizeHttpRequests` | `authorizeExchange` |
| Match endpoint | `requestMatchers(...)` | `pathMatchers(...)` |
| Default user store | `UserDetailsService` / `InMemoryUserDetailsManager` | `ReactiveUserDetailsService` / `MapReactiveUserDetailsService` |
| Context | Thường `SecurityContextHolder` và Servlet thread | `ReactiveSecurityContextHolder` và Reactor Context |
| Test HTTP | `MockMvc` | `WebTestClient` |
| Method security riêng | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |

Nếu có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot **mặc định chọn Spring MVC** thay vì WebFlux; nhiều ứng dụng MVC chỉ thêm WebFlux starter để sử dụng `WebClient`. Nếu thật sự muốn loại reactive khi có cả hai trên classpath, cần đặt `WebApplicationType.REACTIVE` một cách rõ ràng và đảm bảo các auto-config tương thích. Học cấu hình security dễ hơn khi dùng **hai dự án độc lập**, không trộn cả hai starter.

### 7.2. Những cặp tên dễ nhầm

- `@EnableWebSecurity` ≠ `@EnableWebMvc`. Một cái bật Spring Security Servlet; cái kia điều khiển web MVC infrastructure của Spring Framework.
- `@EnableWebFluxSecurity` ≠ `@EnableWebFlux`. Một cái bật Spring Security reactive; cái kia điều khiển cấu hình nền WebFlux.
- `@EnableWebSecurity` ≠ `@EnableMethodSecurity`. Bảo vệ HTTP boundary khác với chặn lời gọi service theo annotation.
- `SecurityFilterChain` ≠ `SecurityWebFilterChain`. Hai interface/filter pipeline của hai mô hình web.
- `SecurityContextHolder` kiểu ThreadLocal của Servlet ≠ `ReactiveSecurityContextHolder` dựa trên Reactor Context.
- `spring-boot-starter-security` **không** đồng nghĩa một ứng dụng đã có OAuth2 Authorization Server, JWT issuer hoặc hệ thống danh tính sản xuất.

## 8. Demo A: Spring Boot MVC có @EnableWebSecurity tường minh

Ta xây dựng ứng dụng dùng HTTP Basic để kiểm tra xác thực và rule. Mục đích của annotation là làm rõ Spring Security Servlet infrastructure. **Khi giữ nguyên custom chain và chạy trên Boot với auto-configuration mặc định, bản demo không nhất thiết cần annotation này; Boot đã có tích hợp tương ứng.** Đừng xem annotation là dòng khai báo quyền của endpoint.

Ví dụ cố định **Spring Boot 3.5.16** để có source Java 17 và test thống nhất. Đây là bản OSS cuối của dòng 3.5.x, phát hành ngày 25/06/2026; triển khai sản phẩm mới cần dùng dòng Boot còn được hỗ trợ và bản vá phù hợp.

### 8.1. Thư mục

```text
servlet-enable-demo/
├── pom.xml
└── src/
    ├── main/java/demo/servlet/ServletSecurityApplication.java
    └── test/java/demo/servlet/ServletSecurityTests.java
```

### 8.2. Maven POM

```xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>servlet-enable-demo</artifactId>
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
```

### 8.3. Java đầy đủ

Tạo `src/main/java/demo/servlet/ServletSecurityApplication.java`:

```java
package demo.servlet;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ServletSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletSecurityApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/notes")
                    .hasAuthority("NOTES_WRITE")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_USER", "NOTES_WRITE")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN")
                .build()
        );
    }
}

@RestController
class ServletRoutes {
    @GetMapping("/public")
    String publicMessage() {
        return "public";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "me:" + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin";
    }

    @PostMapping("/notes")
    String createNote(Authentication authentication) {
        // Demo: không ghi dữ liệu thật, chỉ minh họa permission + CSRF.
        return "created:" + authentication.getName();
    }
}
```

**Giải thích ranh giới:**

1. `@EnableWebSecurity` kích hoạt web security infrastructure Servlet; Spring Boot cũng có cơ chế tự cấu hình tương ứng. Dòng annotation **không khai báo `/admin` là endpoint quản trị**.
2. `SecurityFilterChain` là bean chứa filter/rule hiện tại. `authorizeHttpRequests` khai báo chính sách request; `anyRequest().denyAll()` chặn đường chưa liệt kê trong **chain này**.
3. `UserDetailsService` định nghĩa nguồn user và authorities. Vì có bean này, Boot không cần tạo generated user `user`; mật khẩu `demo-pass` là dữ liệu local.
4. `httpBasic` là cơ chế xác thực. Nó **không mã hóa** password bằng cách riêng: phải có HTTPS khi truyền credential trên mạng thật.
5. `csrf` vẫn bật; POST thiếu token hợp lệ có thể nhận `403` dù Alice có `NOTES_WRITE`.
6. `DispatcherType.ERROR` cho phép container render trang lỗi phù hợp khi có error dispatch; điều này không biến request gốc đến một URL chưa khai báo thành public.
7. Không có `@EnableMethodSecurity`, vì demo tập trung vào HTTP boundary; để bảo vệ service bằng `@PreAuthorize`, cần thêm policy và bật method security riêng.

### 8.4. Integration test với MockMvc

Tạo `src/test/java/demo/servlet/ServletSecurityTests.java`:

```java
package demo.servlet;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void requestPolicyAndCsrfAreApplied() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("me:alice"));

        mvc.perform(get("/me").with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/admin").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin").with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));

        // Đúng quyền NOTES_WRITE nhưng POST thiếu CSRF token.
        mvc.perform(post("/notes").with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        // Có CSRF + quyền NOTES_WRITE, controller được gọi.
        mvc.perform(post("/notes")
                .with(httpBasic("alice", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created:alice"));

        // Admin có ROLE_ADMIN nhưng không có NOTES_WRITE.
        mvc.perform(post("/notes")
                .with(httpBasic("admin", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        // Một đường mới chưa có rule bị deny.
        mvc.perform(get("/unknown")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
```

Test dùng HTTP Basic header thật qua `httpBasic(...)`, để security framework xác thực với `UserDetailsService` trong context test; `csrf()` tạo token hợp lệ theo MockMvc. Không cần mở web server socket để xác minh các rule này. Nếu test chỉ dùng `@WithMockUser` thì mật khẩu không được kiểm tra; đó là loại test authorization khác.

### 8.5. Chạy

Từ thư mục `servlet-enable-demo` với JDK 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Khi server đã khởi động:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice http://localhost:8080/me
curl -i -u alice http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
```

Curl sẽ hỏi password tương tác cho `-u alice`/`-u admin`; nhập `demo-pass` **chỉ trên máy lab**. Kết quả lần lượt thường là `200 public`, `401`, `200 me:alice`, `403`, `200 admin`. Để thử POST thành công khi CSRF bật, cần token hợp lệ cho session/request; bài này dùng `MockMvc.csrf()` để kiểm tra điều kiện đó. Không tắt CSRF chỉ vì POST curl bị 403.

**Một thí nghiệm khái niệm:** Với chính Boot app và bean chain/user như trên, bỏ `@EnableWebSecurity` nhưng giữ `SecurityFilterChain` có thể vẫn chạy tương đương nhờ web security auto-configuration của Boot; đây là lý do không nên coi annotation là cách gán quyền. Kiểm chứng bằng test trong môi trường Boot/version đang dùng khi thực hành.

## 9. Demo B: Spring Boot WebFlux có @EnableWebFluxSecurity

Đây là **dự án độc lập**, chỉ dùng `spring-boot-starter-webflux` chứ không ghép starter MVC. Spring Boot 3.5.16, Java 17. WebFlux dùng `WebFilterChainProxy` và `SecurityWebFilterChain`, không dùng Servlet `SecurityFilterChain`.

### 9.1. Cấu trúc

```text
webflux-enable-demo/
├── pom.xml
└── src/
    ├── main/java/demo/reactive/ReactiveSecurityApplication.java
    └── test/java/demo/reactive/ReactiveSecurityTests.java
```

### 9.2. Maven POM

```xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>webflux-enable-demo</artifactId>
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
```

### 9.3. Mã Java WebFlux đầy đủ

Tạo `src/main/java/demo/reactive/ReactiveSecurityApplication.java`:

```java
package demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/me").authenticated()
                .pathMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.POST, "/notes")
                    .hasAuthority("NOTES_WRITE")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_USER", "NOTES_WRITE")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN")
                .build()
        );
    }
}

@RestController
class ReactiveRoutes {

    @GetMapping("/public")
    Mono<String> publicMessage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    Mono<String> me() {
        return Mono.just("authenticated");
    }

    @GetMapping("/admin")
    Mono<String> admin() {
        return Mono.just("admin");
    }

    @PostMapping("/notes")
    Mono<String> createNote() {
        return Mono.just("created");
    }
}
```

Trong demo này, `@EnableWebFluxSecurity` yêu cầu Spring Security reactive web infrastructure, `SecurityWebFilterChain` xác định quyền HTTP, và `MapReactiveUserDetailsService` định nghĩa user store riêng. Một bean reactive user store thay default user store khi điều kiện auto-configuration của Boot nhường quyền. **Không dùng `InMemoryUserDetailsManager` của Servlet** để thay thế nó trong cấu hình này.

Dù controller trả `Mono`, Spring Security không tự động bảo vệ entity ở database. Nếu `GET /me` sau này có dữ liệu nhạy cảm, service phải kiểm tra đúng principal/owner/tenant và truyền context theo API reactive. Không ép `Mono.block()` trên event loop để đọc user.

### 9.4. Kiểm thử với WebTestClient

Tạo `src/test/java/demo/reactive/ReactiveSecurityTests.java`:

```java
package demo.reactive;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveSecurityTests {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void webFilterChainEnforcesRulesAndCsrf() {
        client.get().uri("/public").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");

        client.get().uri("/me").exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("authenticated");

        client.get().uri("/me")
            .headers(h -> h.setBasicAuth("alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/admin")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/admin")
            .headers(h -> h.setBasicAuth("admin", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin");

        // Alice có NOTES_WRITE, nhưng thiếu CSRF.
        client.post().uri("/notes")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();

        // Alice có quyền và token CSRF test hợp lệ.
        client.mutateWith(csrf()).post().uri("/notes")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("created");

        // Admin không có NOTES_WRITE, dù có CSRF.
        client.mutateWith(csrf()).post().uri("/notes")
            .headers(h -> h.setBasicAuth("admin", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/unknown")
            .headers(h -> h.setBasicAuth("alice", "demo-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

`WebTestClient.bindToApplicationContext(...)` kết hợp `springSecurity()` để chạy qua WebFlux + Spring Security test support. `setBasicAuth` gửi HTTP Basic credential cho reactive authentication; `mutateWith(csrf())` thêm token đúng theo hạ tầng Spring Security Test. Không cần chạy server trên một port thật cho kiểm thử này.

### 9.5. Lệnh chạy và hành vi

Tại `webflux-enable-demo`:

```bash
mvn test
mvn spring-boot:run
```

Trong terminal khác:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice http://localhost:8080/me
curl -i -u alice http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
```

Kỳ vọng: `200 public`, `401`, `200 authenticated`, `403` và `200 admin`. Với `-u` chỉ nhập password `demo-pass` khi curl hỏi; không để password trong lịch sử command. HTTP không mã hóa password; các lệnh dùng `localhost` chỉ cho lab. Production phải chạy HTTPS/TLS.

**Điểm đối chiếu với Servlet:** Kỳ vọng status giống nhau vì **rule nghiệp vụ HTTP được viết tương đương**, nhưng Spring Security thực thi bằng các filter và context **khác nhau**. Đừng kết luận rằng hai stack dùng chung các class filter hay method-security annotation.

## 10. Một thí nghiệm “baseline → custom” giúp nhìn rõ Boot auto-configuration

Để tránh nhầm ảnh hưởng của annotation với ảnh hưởng của chain bean, hãy thử theo thứ tự.

### Giai đoạn A — Chỉ có starter

1. Dùng Spring Boot MVC hoặc WebFlux một cách độc lập.
2. Có Spring Security starter nhưng **chưa khai báo chain/user store**.
3. Chạy và xem log generated security password nếu user mặc định được tạo; username mặc định thường là `user`.
4. Thử `GET /public` không credential. Mặc định thường yêu cầu xác thực ngay cả khi endpoint được đặt tên là public.
5. Thử `GET /public` với Basic user đúng: được vào. Với browser chấp nhận HTML, có thể được redirect đến login page.

**Quan sát:** Spring Boot đã bật web security defaults mà không cần mã Java cấu hình bảo mật tùy chỉnh.

### Giai đoạn B — Chỉ thêm annotation

1. Thêm một class `@Configuration @EnableWebSecurity` với MVC, hoặc `@Configuration @EnableWebFluxSecurity` với WebFlux.
2. Không tự định nghĩa bean chain hoặc user provider.
3. Quan sát và test default behavior. Trong Boot đúng stack, annotation thường không phải thay đổi chính sách cấp quyền thực tế nếu hạ tầng đã được Boot bật.
4. Không dùng “không còn generated password” như một giả định chắc chắn; việc tạo default user là một auto-configuration khác.

**Quan sát:** Annotation thể hiện việc kích hoạt hạ tầng. Không thể dùng nó thay nội dung `authorizeHttpRequests`/`authorizeExchange`.

### Giai đoạn C — Thêm chain bean

1. Tạo `SecurityFilterChain`/`SecurityWebFilterChain`.
2. Cho phép chính xác `GET /public` và yêu cầu authenticated cho `GET /me`; thêm quyền `ROLE_ADMIN` cho `GET /admin`.
3. Chạy lại test: `GET /public` anonymous đổi từ bị chặn thành `200`; `/me` vẫn yêu cầu login; user thiếu admin role nhận `403`.
4. Nếu không khai báo user store, default user có thể vẫn xuất hiện theo điều kiện Boot.

**Quan sát:** **Bean chain** thay đổi chính sách HTTP; **không tự tạo hay xóa** danh tính user.

### Giai đoạn D — Thêm user/provider riêng

1. Tạo `UserDetailsService` hoặc `MapReactiveUserDetailsService` trong các demo.
2. Dùng user `alice`/`admin` với password hash và authorities đã xác định.
3. Test đúng/sai password và đúng/sai role.
4. Kiểm tra log generated user: có thể biến mất vì default user configuration đã back off.

**Quan sát:** **Nguồn xác thực** được tùy chỉnh độc lập với **rule cấp quyền**. Các ứng dụng production cần triển khai identity provider thật và chính sách vòng đời tài khoản.

### Giai đoạn E — Bật method security khi có nhu cầu

1. Nếu service có `@PreAuthorize`, thêm `@EnableMethodSecurity` cho phần imperative/Servlet; reactive service cần `@EnableReactiveMethodSecurity` với cách hoạt động phù hợp Reactor.
2. Viết test gọi method qua proxy/bean thực, không gọi nội bộ bằng `this.method()` rồi mặc định interceptor chạy.
3. Test user có quyền gọi URL nhưng **không có quyền trên object** để xác minh policy owner/tenant ở service/repository.

**Quan sát:** Request authorization ở web boundary là một lớp. Method và domain authorization là lớp khác.

## 11. Ma trận hành vi cần xác nhận

| Tình huống | Servlet + chain do ứng dụng tạo | WebFlux + chain do ứng dụng tạo |
| --- | --- | --- |
| Anonymous gọi `GET /public` | `200` | `200` |
| Anonymous gọi `GET /me` | `401` khi dùng HTTP Basic | `401` khi dùng HTTP Basic |
| Alice có password đúng gọi `GET /me` | `200`, `me:alice` | `200`, `authenticated` |
| Alice gửi password sai | `401` | `401` |
| Alice gọi admin | `403` do thiếu role | `403` do thiếu role |
| Admin gọi admin | `200` | `200` |
| Alice POST notes thiếu CSRF | `403` | `403` |
| Alice POST notes có CSRF | `200` | `200` |
| Admin POST notes có CSRF, thiếu NOTES_WRITE | `403` | `403` |
| Alice gọi URL chưa có rule | `403` với `denyAll` | `403` với `denyAll` |

Đây là hợp đồng **của demo ở trên**, không có nghĩa tất cả ứng dụng Spring Security luôn trả mã như vậy. Nếu sử dụng form login, browser có thể được redirect; với JWT Resource Server, entry point và claims/authorities có hành vi khác. Khi reverse proxy tạo response, error route hoặc CORS/CSRF được cấu hình riêng, cần test theo deployment thật.

## 12. Các lỗi thường gặp

### 12.1. “Không có @EnableWebSecurity nên Boot không bảo vệ URL”

**Sai:** Spring Boot Servlet thường auto-config Spring Security khi có starter. Một endpoint có thể yêu cầu đăng nhập ngay cả khi source code không ghi annotation.

**Sửa:** kiểm tra dependency, bean `SecurityFilterChain` đã có chưa, log startup, response của một request không credential và báo cáo điều kiện auto-configuration.

### 12.2. “Có @EnableWebSecurity nghĩa là admin rule đã có”

**Sai:** Annotation bật hạ tầng, không biết `/admin` là thao tác đặc biệt. Bảo vệ theo quyền nghiệp vụ cần `authorizeHttpRequests` và quyền dữ liệu tại service.

**Sửa:** khai báo `requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")` và test cả non-admin/admin.

### 12.3. “Tạo UserDetailsService nghĩa là đã tắt web security mặc định”

**Sai:** Thay user store là một nhánh điều kiện auto-configuration khác với thay chain.

**Sửa:** tách test authentication và URL authorization. Đừng giả định chỉ đổi user store thì `/public` thành public.

### 12.4. “Tạo SecurityFilterChain nghĩa là user mặc định chắc chắn biến mất”

**Sai:** Boot Servlet docs nói rõ custom chain **không tự tắt** default `UserDetailsService`.

**Sửa:** nếu muốn identity riêng, cung cấp đúng `UserDetailsService`, provider hoặc manager và kiểm chứng việc generated user back off.

### 12.5. “WebFlux dùng HttpSecurity vì cũng là ứng dụng web”

**Sai:** WebFlux dùng reactive `ServerHttpSecurity`/`SecurityWebFilterChain` và `@EnableWebFluxSecurity`. Dùng nhầm API Servlet khiến cấu hình không áp dụng lên reactive pipeline.

**Sửa:** dùng đúng starter/framework; test WebFlux bằng `WebTestClient` và kiểm tra loại bean/runtime.

### 12.6. “Có cả hai starter nên Boot tự chọn WebFlux”

**Sai:** Khi `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng trên classpath, Boot mặc định chọn Spring MVC; WebFlux starter có thể được thêm chỉ để dùng `WebClient`.

**Sửa:** dùng một starter web cho demo; với sản phẩm có yêu cầu đặc biệt, xác định `WebApplicationType` và kiểm tra Spring Boot condition report.

### 12.7. “Dùng @EnableWebFlux thay @EnableWebFluxSecurity”

**Sai:** `@EnableWebFlux` điều khiển cấu hình Spring WebFlux, không phải bật reactive Spring Security.

**Sửa:** phân biệt annotation của Spring Framework web và annotation của Spring Security; không thay bừa vì tên giống nhau.

### 12.8. “Thêm annotation đã bật @PreAuthorize”

**Sai:** Method security không mặc nhiên được bật khi web security được bật.

**Sửa:** dùng `@EnableMethodSecurity` / `@EnableReactiveMethodSecurity` theo model và test method interception.

### 12.9. “Tắt CSRF là cách sửa mọi lỗi POST 403”

**Sai:** Trong browser dùng cookie/session/Basic credentials tự gửi, CSRF là nguy cơ độc lập với authentication/role. Tắt tùy tiện có thể tạo lỗ hổng.

**Sửa:** kiểm thử với token hợp lệ, thiết kế CSRF theo credential/threat model. Một API chỉ dùng Bearer header do client chủ động đặt cần đánh giá riêng, không bê nguyên cấu hình từ lab.

### 12.10. “Cấu hình SecurityFilterChain chỉ match /api/** nhưng anyRequest sẽ chặn toàn app”

**Sai:** `anyRequest` chỉ tác động lên request **đã được chain chọn**. Ngoài `/api/**` có thể không có chain nào, do đó không được Spring Security bảo vệ.

**Sửa:** có fallback chain match tất cả hoặc sử dụng một chain duy nhất với nhiều `requestMatchers`, và test URL ngoài API. Đây là lỗi chain coverage, không phải lỗi annotation.

### 12.11. “Gán role trong token/user là đủ bảo vệ mọi object”

**Sai:** Role cấp quyền thao tác mức chức năng; service còn cần kiểm tra owner, tenant, trạng thái, hạn mức và ACL. Security web filter không tự hiểu dữ liệu nghiệp vụ.

**Sửa:** viết policy theo actor + action + resource + context, thử đổi ID và tenant; dùng dữ liệu tin cậy từ server.

### 12.12. “Đã thêm @EnableWebSecurity nên chỉ cần test bean tồn tại”

**Sai:** Bean tồn tại không chứng minh CSRF, URL matching, login flow, session và exception handling hoạt động đúng.

**Sửa:** có ít nhất integration test anonymous, wrong password, insufficient authority, CSRF, valid user, fallback request; dùng test mạng thật khi kiểm chứng HTTPS/reverse proxy.

## 13. Debug cấu hình tự động và chain ở dự án thật

### 13.1. Những điều phải nhìn đầu tiên

1. **Classpath:** có starter web nào? Có cả web + webflux không? Có thêm OAuth2 client/resource server/SAML starter làm thay điều kiện user store không?
2. **WebApplicationType:** app thực sự là Servlet hay Reactive?
3. **Beans đã tạo:** `SecurityFilterChain`/`SecurityWebFilterChain`, `UserDetailsService`/`ReactiveUserDetailsService`, authentication manager/provider/decoder nào tồn tại?
4. **Annotations:** `@EnableWebSecurity` hay `@EnableWebFluxSecurity` đã có chưa? Trong Spring Boot, đã được auto-enable thông qua config chưa?
5. **Conditions:** lớp auto-configuration nào được áp dụng/back off, vì bean/classpath nào?
6. **Filter chain coverage:** chain match URL nào, order ra sao, có URL không match chain nào không?
7. **Authorization rules:** anonymous, authenticated, role/authority, HTTP method, CSRF và CORS có đúng ý định?
8. **Identity source:** generated user còn tồn tại hay đã được thay bằng service/provider/IdP thật?
9. **Transport:** request thực tế có HTTPS, cookie flags, proxy/header trust đúng không?

### 13.2. Log ở môi trường local

Có thể bật thông tin Spring Security:

```properties
logging.level.org.springframework.security=DEBUG
```

Và dùng flag `--debug` của Spring Boot khi chạy để xem **condition evaluation report** (nội dung tùy version):

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

Không nhất thiết log nào cũng cho bạn kết luận “annotation được áp dụng” nếu không đọc đúng context/classpath. Hãy xem cả bean definition, điều kiện auto-configuration và HTTP behavior. Tránh bật TRACE/log credential/token ở production.

Nếu có Actuator dành cho quản trị, endpoint `conditions` và `beans` có thể hỗ trợ chẩn đoán nhưng **không được phơi công khai**; quyền truy cập Actuator phải được bảo vệ theo policy hạ tầng.

### 13.3. Phân biệt 401, 403 và 302

- `401 Unauthorized`: cần xác thực hoặc credential chưa được chấp nhận; HTTP Basic thường gửi `WWW-Authenticate`.
- `403 Forbidden`: authentication có thể hợp lệ nhưng thiếu quyền; hoặc POST bị CSRF chặn (CSRF filter có thể chặn trước khi authentication hoàn tất).
- `302 Found`: thường là redirect đến form login cho browser, tùy entry point.
- `404`/`405`: có thể đến từ MVC/WebFlux routing nếu request đã qua filter chain; đừng nhầm với security decision.
- `200`: thành công ở handler, **không chứng minh URL public** nếu request đã mang cookie/token.

Trong mọi trường hợp, đọc **request method + path + headers + credential + chain/rule + result** trước khi sửa security configuration. Tránh tắt mọi filter chỉ để đổi status code.

## 14. Câu hỏi tự đánh giá

**Câu 1.** Một Boot MVC app có `spring-boot-starter-security` nhưng không khai báo `@EnableWebSecurity`. Nó có thể yêu cầu login cho tất cả URL không?

**Trả lời:** Có. Boot tự cấu hình web security mặc định khi điều kiện phù hợp. Annotation không phải điều kiện bắt buộc duy nhất để Boot bật security.

**Câu 2.** Bạn tạo `SecurityFilterChain` cho phép `/health` public, nhưng vẫn thấy password ngẫu nhiên trong log. Có phải Boot lỗi?

**Trả lời:** Không. Thay default web chain không tự thay `UserDetailsService`. Nếu chưa có user/provider khác và không có classpath condition loại trừ, Boot vẫn có thể tạo generated user.

**Câu 3.** Bạn tạo `UserDetailsService` custom nhưng anonymous gọi `/private` vẫn bị yêu cầu đăng nhập. Điều này có hợp lý?

**Trả lời:** Có. User store quyết định nguồn identity; web policy mặc định có thể vẫn yêu cầu authentication. Hai loại auto-configuration độc lập về ý nghĩa.

**Câu 4.** Có `spring-boot-starter-webflux` cùng với `spring-boot-starter-web`, code dùng `@EnableWebFluxSecurity` nhưng request MVC không chịu rule reactive. Vì sao?

**Trả lời:** Boot mặc định chọn MVC khi có cả hai starter. Rule WebFlux không phải Servlet `SecurityFilterChain`. Cần xác định web application type và cấu hình đúng stack.

**Câu 5.** Trong WebFlux, bạn chỉ thêm `@EnableWebFluxSecurity`. Có phải mọi URL trở thành `permitAll` không?

**Trả lời:** Không. Bật hạ tầng không có nghĩa mở quyền. Default security thường yêu cầu authentication; mở một URL cần `SecurityWebFilterChain` với `authorizeExchange(...).pathMatchers(...).permitAll()` phù hợp.

**Câu 6.** Để dùng `@PreAuthorize` trong service Servlet, bạn chỉ cần `@EnableWebSecurity`?

**Trả lời:** Chưa đủ. Cần `@EnableMethodSecurity` và cấu hình method security phù hợp; lời gọi phải đi qua interceptor/proxy để annotation có hiệu lực.

**Câu 7.** `@EnableWebMvc` có thể thay `@EnableWebSecurity` không?

**Trả lời:** Không. Một annotation bật web framework MVC; annotation còn lại bật Spring Security Servlet. Chúng phục vụ mục tiêu khác nhau.

**Câu 8.** Vì sao hai demo trả cùng mã 200/401/403 nhưng dùng hai bộ test khác nhau?

**Trả lời:** Chính sách HTTP được viết tương ứng, nhưng execution model khác: Servlet filter và `MockMvc` ở một bên, reactive WebFilter và `WebTestClient` ở bên kia.

## 15. Checklist trước khi phát hành

- [ ] Có chọn **Servlet** hay **Reactive** rõ ràng, đã kiểm tra starter và WebApplicationType?
- [ ] Hiểu sự khác nhau giữa annotation enable, auto-configuration, filter chain bean và user/provider bean?
- [ ] Không dùng generated user/password làm danh tính production?
- [ ] Bean chain đã định nghĩa URL/method/role/authority chính xác, có `denyAll`/fallback phù hợp?
- [ ] Anonymous, role sai, password sai, CSRF và request hợp lệ đều có integration test?
- [ ] Đã kiểm tra không có URL lọt ngoài mọi chain khi dùng nhiều chain?
- [ ] Các endpoint login/logout/error/health/actuator có thuộc phạm vi filter cần thiết?
- [ ] Method security được bật riêng nếu dự án dùng `@PreAuthorize`?
- [ ] WebFlux không sử dụng ThreadLocal/Servlet filter như mặc định cho reactive pipeline?
- [ ] OAuth2/JWT đã có issuer/audience/key validation và ánh xạ authorities đáng tin?
- [ ] Quyền trên resource/owner/tenant vẫn được kiểm tra ở service/repository?
- [ ] Production có HTTPS, quản lý secret, log an toàn, dependency được vá và session/token policy phù hợp?

## 16. Ghi nhớ

1. **`@EnableWebSecurity` = Spring Security Servlet infrastructure. `@EnableWebFluxSecurity` = Spring Security Reactive infrastructure.**
2. **Spring Boot có auto-configuration**: chỉ thêm starter có thể đã bật default security và sinh user/password development; bạn không phải luôn thêm annotation thủ công.
3. **Bean `SecurityFilterChain`/`SecurityWebFilterChain` quyết định chính sách web cụ thể**. Annotation không tự hiểu URL nào cần role hay quyền gì.
4. **Nguồn user và web chain là hai trách nhiệm tách biệt**. Custom chain không đồng nghĩa default user đã biến mất, và custom user không đồng nghĩa URL đã public.
5. **Chọn đúng web stack, test đúng công cụ**: Servlet dùng `HttpSecurity`/`MockMvc`, reactive dùng `ServerHttpSecurity`/`WebTestClient`.
6. **Web security là lớp biên**. Cần thêm method/domain policy, kiểm thử âm tính và HTTPS khi ứng dụng thực sự xử lý dữ liệu.

## Tài liệu chính thức

- [Spring Boot 3.5 — Spring Security Auto-Configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Security 6.5 — Servlet Java Configuration, @EnableWebSecurity](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — WebFlux Security, @EnableWebFluxSecurity](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Reactive Test WebTestClient Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — WebFlux CSRF Testing](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html)
- [Spring Security 6.5 — Servlet MockMvc Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security 6.5 — Servlet MockMvc CSRF Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Boot — Reactive Web Applications and MVC/WebFlux Starter Selection](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html)
- [Spring Boot 3.5.16 Release, 25/06/2026](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
