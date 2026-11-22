# `authorizeHttpRequests` và `authorizeExchange` trong hai mô hình web

**Phạm vi:** Phân quyền endpoint ở tầng HTTP trong Spring Security, so sánh ứng dụng **Servlet/Spring MVC** và **Reactive/Spring WebFlux**. Hai DSL giải cùng một bài toán: với một HTTP request đã đi qua các bước xử lý bảo mật, đường dẫn và phương thức HTTP nào được truy cập, ai phải đăng nhập và ai cần role/authority cụ thể. Tuy nhiên, chúng thuộc hai mô hình thực thi khác nhau nên **không thay thế trực tiếp cho nhau**.

## 1. Phân biệt xác thực và phân quyền

- **Authentication (xác thực):** xác định người dùng/client là ai; Spring Security biểu diễn thông tin đó bằng `Authentication` với danh tính và tập `GrantedAuthority`. Basic, form login, session hay OAuth2 Resource Server/JWT là các cơ chế xác thực khác nhau.
- **Authorization (phân quyền):** quyết định một yêu cầu đã có (hoặc không có) danh tính/authority có được đi tiếp tới endpoint không. `authorizeHttpRequests` và `authorizeExchange` khai báo các quy tắc này ở tầng HTTP.
- `permitAll()`: cho phép truy cập endpoint công khai; không yêu cầu login.
- `authenticated()`: yêu cầu danh tính được Spring Security xem là đã xác thực, không đòi một quyền cụ thể.
- `hasAuthority("report:read")`: chỉ chấp nhận một `GrantedAuthority` bằng chính xác `report:read`.
- `hasRole("ADMIN")`: theo quy ước prefix mặc định, tìm authority `ROLE_ADMIN`. **Không truyền `"ROLE_ADMIN"` vào `hasRole`**; nếu đã có chuỗi đầy đủ thì dùng `hasAuthority("ROLE_ADMIN")`.
- `denyAll()`: từ chối tất cả yêu cầu khớp quy tắc.

**Giới hạn:** Đây là phân quyền ở cửa vào HTTP. Nó không tự kiểm tra rằng bản ghi cụ thể thuộc về người dùng, không tự sinh token và không tự xác thực mật khẩu. Với nghiệp vụ cần kiểm tra chủ sở hữu dữ liệu, bổ sung phân quyền ở service/method hoặc một `AuthorizationManager` phù hợp.

## 2. Nhìn nhanh sự khác nhau

| Khía cạnh | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| DSL của rule | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| Builder | `HttpSecurity` | `ServerHttpSecurity` |
| Bean thành phẩm | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Đơn vị HTTP | `HttpServletRequest` | `ServerWebExchange` |
| Match theo path | `requestMatchers(...)` | `pathMatchers(...)` |
| Match tất cả còn lại | `anyRequest()` | `anyExchange()` |
| Bộ thực thi authorization | Thường là `AuthorizationFilter` | `AuthorizationWebFilter` |
| API quyết định tùy chỉnh | `AuthorizationManager<RequestAuthorizationContext>` | `ReactiveAuthorizationManager<AuthorizationContext>` |
| Truyền danh tính | `SecurityContextHolder` trong cơ chế Servlet | `ReactiveSecurityContextHolder` qua Reactor `Context` |
| Cách tính quyết định | Đồng bộ qua `AuthorizationManager` | Reactive qua `Mono<AuthorizationDecision>` |
| Công cụ test phổ biến | `MockMvc` + `spring-security-test` | `WebTestClient` + `spring-security-test` |

Về trực giác, cả hai đều đi theo hướng:

```text
HTTP request
  → Spring Security chọn chain áp dụng
  → xác thực và tạo/khôi phục Authentication
  → tìm quy tắc authorization khớp request
  → đủ quyền: đi tiếp tới handler; không đủ: xử lý từ chối
```

**Khác biệt then chốt:** MVC dựa trên Servlet Filter và lời gọi đồng bộ theo request; WebFlux dùng các WebFilter và Publisher reactive. Trong một `ReactiveAuthorizationManager`, quyết định có thể phụ thuộc truy vấn bất đồng bộ và được trả về qua `Mono`; không gọi `block()` hoặc `subscribe()` thủ công trong quá trình quyết định quyền.

## 3. Cấu hình Servlet: `HttpSecurity.authorizeHttpRequests`

Ví dụ dưới đây là **một lớp cấu hình hoàn chỉnh** dành cho **ứng dụng Spring Boot MVC/Servlet** sử dụng Spring Security 6.x, Java 17+. Đặt ở tệp `ServletSecurityConfig.java` trong package của ứng dụng; ứng dụng cần có `spring-boot-starter-web` và `spring-boot-starter-security`. Không đặt lớp này vào ứng dụng WebFlux thuần.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ServletSecurityConfig {

    @Bean
    SecurityFilterChain servletSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**", "/actuator/health")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("report:read")
                .requestMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasAuthority("report:write")
                .requestMatchers("/admin/**")
                    .hasRole("ADMIN")
                .anyRequest()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

**Giải thích theo từng tầng:**

1. `HttpSecurity` cấu hình HTTP security cho **Servlet stack**. `http.build()` tạo bean `SecurityFilterChain`.
2. `authorizeHttpRequests` đưa vào một danh sách cặp **request matcher → quy tắc**. Spring Security áp dụng **quy tắc khớp đầu tiên** trong danh sách của chain đã chọn.
3. Hai đường dẫn public được `permitAll`. Muốn mở thêm endpoint, khai báo rõ nó; không đưa `"/**"` vào `permitAll` trước các rule bảo vệ.
4. `GET /api/reports/**` cần authority chính xác `report:read`, còn `POST` trên cùng nhóm path cần `report:write`. Nếu quyền đọc/ghi là hai authority riêng, user chỉ có quyền đọc không được mặc nhiên ghi.
5. `/admin/**` cần role `ADMIN`, tương ứng authority `ROLE_ADMIN` theo prefix mặc định.
6. `anyRequest().denyAll()` là **chính sách mặc định từ chối**: endpoint chưa liệt kê không vô tình mở. Thay bằng `authenticated()` nếu yêu cầu sản phẩm là mọi endpoint khác đều cho user đăng nhập truy cập; đây là **quyết định bảo mật** cần nêu rõ.
7. `httpBasic(...)` chỉ chọn một cơ chế HTTP authentication để ví dụ có ngữ cảnh. Người dùng, mật khẩu, OAuth2/JWT, session hay nguồn dữ liệu tài khoản vẫn phải được cấu hình phù hợp với ứng dụng thật.

Có thể viết mẫu rút gọn cho ứng dụng chỉ cần “mọi request phải đăng nhập”:

```java
http.authorizeHttpRequests(authorize -> authorize
    .anyRequest().authenticated()
);
```

Mẫu rút gọn là **trích đoạn cấu hình**, không phải chương trình Java độc lập. Đừng suy diễn rằng `authenticated()` tự cấp role hoặc tự kiểm tra owner của tài nguyên.

## 4. Cấu hình Reactive: `ServerHttpSecurity.authorizeExchange`

Đây là **lớp cấu hình riêng** cho **ứng dụng Spring Boot WebFlux** sử dụng Spring Security 6.x, Java 17+. Đặt tại `ReactiveSecurityConfig.java` và dùng `spring-boot-starter-webflux` cùng `spring-boot-starter-security`. Lớp này **không cùng tồn tại** với lớp Servlet bên trên như một cấu hình dùng chung; chọn class theo web stack thực tế.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain reactiveSecurityWebFilterChain(ServerHttpSecurity http) {

        http
            .authorizeExchange(authorize -> authorize
                .pathMatchers("/public/**", "/actuator/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("report:read")
                .pathMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasAuthority("report:write")
                .pathMatchers("/admin/**")
                    .hasRole("ADMIN")
                .anyExchange()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Ý nghĩa chính sách **tương đương về mục đích** với ví dụ MVC, nhưng các lớp và loại request khác nhau:

- `ServerHttpSecurity` xây dựng `SecurityWebFilterChain` thay vì `SecurityFilterChain`.
- `authorizeExchange` xét `ServerWebExchange`. `pathMatchers` là bộ matcher path/method của WebFlux; nó **không nhận `HttpServletRequest`**.
- `anyExchange()` xử lý những exchange chưa match rule trước đó; vai trò tương tự `anyRequest()`.
- Lựa chọn thực sự trong hệ reactive được thực thi qua các thành phần reactive, có thể trả tín hiệu bất đồng bộ. Vì vậy cấu hình và logic tùy biến phải bảo toàn chuỗi Publisher.
- Cũng như ví dụ Servlet, `httpBasic(...)` không tự tạo kho user hoặc mapping authority. Cơ chế xác thực cần có thể là reactive user details, HTTP Basic hoặc reactive resource server/JWT.

Mẫu WebFlux tối giản:

```java
http.authorizeExchange(authorize -> authorize
    .anyExchange().authenticated()
);
```

**Lưu ý tên DSL:** `authorizeHttpRequests` thuộc `HttpSecurity`; `authorizeExchange` thuộc `ServerHttpSecurity`. Không sửa tên phương thức một cách máy móc trong cùng một class mà quên thay toàn bộ stack và các bean tương ứng.

## 5. Đọc và đánh giá thứ tự rule

Trong **mỗi chain**, Spring Security xét rule **theo thứ tự khai báo** và dùng quy tắc khớp đầu tiên. Ví dụ với các rule giống nhau ở hai stack:

```text
1. /public/**                → permitAll
2. GET /api/reports/**       → hasAuthority("report:read")
3. POST /api/reports/**      → hasAuthority("report:write")
4. /admin/**                 → hasRole("ADMIN")
5. mọi request còn lại       → denyAll
```

| Request | Rule đầu tiên khớp | Điều kiện để được tiếp tục |
|---|---|---|
| `GET /public/about` | 1 | Không cần đăng nhập |
| `GET /api/reports/42` | 2 | Phải có `report:read` |
| `POST /api/reports/42` | 3 | Phải có `report:write`; còn chịu kiểm tra CSRF nếu đang bật |
| `GET /admin/users` | 4 | Phải có `ROLE_ADMIN` |
| `GET /unknown` | 5 | Bị từ chối dù đã đăng nhập |

**Sai vì thứ tự:**

```java
// Servlet — SAI: rule rộng bắt tất cả trước rule riêng.
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

Nếu có một matcher tổng quát cho toàn bộ đường dẫn ở đầu danh sách, rule dành cho `/admin/**` không có cơ hội quyết định. Trong WebFlux, lỗi tương tự xảy ra khi `pathMatchers("/**").permitAll()` xuất hiện trước `pathMatchers("/admin/**").hasRole("ADMIN")`.

**Đúng:** khai báo trường hợp đặc biệt trước, trường hợp rộng sau; đặt `anyRequest()`/`anyExchange()` ở cuối. Cấu hình phải bao phủ rõ cả HTTP method khi nghiệp vụ phân quyền đọc/ghi khác nhau. `GET` khác `POST`, nhưng `HEAD`, `OPTIONS`, `PATCH`, `PUT` và `DELETE` cũng cần chính sách rõ nếu endpoint hỗ trợ chúng.

## 6. Matcher chọn chain khác với matcher chọn rule

Có **hai cấp chọn** dễ nhầm:

1. **Chọn security chain:** với Servlet, `http.securityMatcher(...)` xác định request nào sử dụng `SecurityFilterChain` đó; với WebFlux, `http.securityMatcher(ServerWebExchangeMatcher)` quyết định `SecurityWebFilterChain` áp dụng cho exchange nào.
2. **Chọn rule bên trong chain đã áp dụng:** Servlet dùng `authorizeHttpRequests(...requestMatchers(...))`; WebFlux dùng `authorizeExchange(...pathMatchers(...))`.

Ví dụ ý tưởng một chain chỉ bảo vệ `/api/**`:

```java
// Trích đoạn Servlet: điều kiện CHỌN CHAIN, rồi mới chọn RULE.
http.securityMatcher("/api/**")
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated()
    );
```

```java
// Trích đoạn WebFlux: ServerWebExchangeMatcher chọn CHAIN.
http.securityMatcher(
        ServerWebExchangeMatchers.pathMatchers("/api/**"))
    .authorizeExchange(authorize -> authorize
        .pathMatchers("/api/public/**").permitAll()
        .anyExchange().authenticated()
    );
```

Trích đoạn reactive cần import `org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers`. Cả hai trích đoạn nằm bên trong một phương thức cấu hình có builder tương ứng; không phải lớp Java độc lập.

**Hệ quả quan trọng:** `anyRequest()` hoặc `anyExchange()` chỉ là “mọi request/exchange còn lại **trong chain này**”. Nếu định nghĩa chain riêng cho `/api/**` mà không có chain bao phủ các path khác, các path ngoài `/api/**` có thể **không được Spring Security bảo vệ**. Khi dùng nhiều chain, kiểm tra thứ tự `@Order`, các matcher giao nhau và fallback chain tổng quát; đừng nhầm “deny all ở cuối API chain” với “deny all toàn ứng dụng”.

Đường đi tổng quát:

```text
Servlet:
HTTP request → FilterChainProxy → chọn SecurityFilterChain
             → các Servlet Filter → AuthorizationFilter
             → rule requestMatchers → controller

Reactive:
HTTP exchange → WebFilterChainProxy → chọn SecurityWebFilterChain
              → các WebFilter → AuthorizationWebFilter
              → rule pathMatchers → reactive handler
```

## 7. Từ matcher đến quyết định quyền tùy biến

Các rule `permitAll`, `authenticated`, `hasRole`, `hasAuthority` xử lý phần lớn nhu cầu căn bản. Trường hợp “user chỉ được xem báo cáo mà mình sở hữu” thường cần quyền theo **đối tượng** chứ không chỉ theo URL.

- Trong **Servlet**, khi cần chính sách tùy biến ở tầng request, DSL hỗ trợ `.access(AuthorizationManager<RequestAuthorizationContext>)`. Manager nhận `Supplier<Authentication>` và dữ liệu request; việc đánh giá authorization là đồng bộ. Khi cần xác minh owner trong database, có thể đặt logic tại service/method phù hợp thay vì I/O tốn thời gian ngay trong matcher.
- Trong **WebFlux**, `.access(ReactiveAuthorizationManager<AuthorizationContext>)` dùng ngữ cảnh exchange và `Mono<Authentication>`; logic phải trả Publisher chứa quyết định `AuthorizationDecision` hoặc kết quả phù hợp API. Nếu chính sách cần đọc dữ liệu bất đồng bộ, kết hợp `flatMap`/`map`, không gọi `block()`, không `subscribe()` thủ công.
- Với cả hai, **deny by default** khi thiếu dữ liệu/không thể kết luận, đồng thời phân biệt lỗi hạ tầng với “không có quyền” để log/giám sát và tạo response thích hợp. Đừng lấy một tham số do client gửi làm bằng chứng owner khi chưa đối chiếu danh tính đã được xác thực.

Ví dụ trực giác về phép kiểm tra:

```text
GET /users/alice/reports/42
  → matcher /users/{username}/reports/{id}
  → Authentication.name phải phù hợp chính sách quyền
  → nếu cần, truy vấn dữ liệu xác minh report 42 thuộc user
  → cho phép hoặc từ chối TRƯỚC khi trả dữ liệu
```

Matcher path có thể cung cấp biến đường dẫn cho policy engine tùy cấu hình matcher, nhưng **chỉ khớp URL chưa chứng minh quyền trên bản ghi**. Để tránh lẫn khái niệm, các ví dụ cấu hình ở trên chỉ kiểm tra authority tĩnh theo route.

## 8. Các khác biệt cần nhớ khi chuyển MVC ↔ WebFlux

### 8.1. Không hoán đổi API “một đổi một”

| Servlet | WebFlux |
|---|---|
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `requestMatchers("/foo/**")` | `pathMatchers("/foo/**")` |
| `requestMatchers(HttpMethod.GET, "/foo/**")` | `pathMatchers(HttpMethod.GET, "/foo/**")` |
| `anyRequest().authenticated()` | `anyExchange().authenticated()` |
| `Authentication` trong mô hình Servlet | `Authentication` được truyền qua Reactor Context khi xử lý reactive |

Không nhập cả `spring-boot-starter-web` và `spring-boot-starter-webflux` rồi cho rằng mọi controller sẽ tự chạy reactive. Trong Spring Boot, cấu hình nhiều web starter có thể khiến ứng dụng chọn Servlet stack; hãy xác minh loại ứng dụng thực tế trước khi chọn DSL. Tránh dùng `SecurityContextHolder.getContext()` như nguồn duy nhất của user trong luồng WebFlux; dùng các cơ chế tích hợp reactive, ví dụ `ReactiveSecurityContextHolder` khi cần đọc context.

### 8.2. HTTP method, path và query string

`requestMatchers` và `pathMatchers` có thể kiểm tra path và HTTP method. Hành vi chi tiết của pattern phụ thuộc loại matcher/phiên bản/configuration, nhất là khi có Servlet path, context path, ký tự mã hóa hoặc parser pattern. Không mặc nhiên xem tất cả pattern syntax là giống hệt giữa MVC và WebFlux.

Ví dụ `/api/reports/**` không tự quy định rằng `?owner=alice` phải đúng với danh tính. Query parameter và ownership cần matcher tùy biến, authorization manager hoặc business-layer guard phù hợp. Cũng cần viết test với đường dẫn gần giống (ví dụ `/admin`, `/admin/`, `/adminx`), method không liệt kê và biến path để kiểm tra chính xác logic matcher của dự án.

### 8.3. `permitAll` và bỏ qua toàn bộ security chain

Cho phép public bằng `permitAll()` để request vẫn đi qua security chain và có thể nhận header bảo mật hoặc cơ chế bảo vệ cần thiết. Tránh cấu hình loại trừ hoàn toàn Spring Security cho tài nguyên tĩnh khi không có nhu cầu rõ ràng. Dùng `permitAll` không tự tắt CSRF hay các bảo vệ khác.

### 8.4. CSRF là lớp kiểm tra khác authorization rule

Trong các cấu hình mặc định hỗ trợ CSRF, request thay đổi trạng thái như `POST` có thể bị **403 vì thiếu CSRF token** dù có `report:write`. Điều đó **không chứng tỏ `hasAuthority` sai**. Khi test, cung cấp CSRF token hoặc thiết kế chính sách CSRF theo thực tế: ứng dụng dùng cookie/session trong trình duyệt thường cần CSRF; API stateless dùng bearer token trong header có thể có mô hình đe dọa khác. Không tắt CSRF hàng loạt chỉ để làm xanh một test.

### 8.5. Servlet dispatch và WebFlux request lifecycle

Trong Servlet, các dispatch như `FORWARD` và `ERROR` có thể đi qua `AuthorizationFilter`. Nếu ứng dụng render trang lỗi/view và bị `403` không mong muốn, cân nhắc rule có chủ đích qua `dispatcherTypeMatchers(DispatcherType.ERROR, DispatcherType.FORWARD)` hoặc quy tắc phù hợp; đừng mở toàn bộ dispatch thiếu kiểm soát. Trong WebFlux, ngữ cảnh và vòng đời reactive do framework quản lý; thao tác quyền bất đồng bộ phải nằm trong Publisher được trả về, không tự chuyển sang subscription rời.

## 9. 401, 403 và lỗi thường gặp

**401 Unauthorized** thường là dấu hiệu request chưa có thông tin xác thực hợp lệ và cơ chế authentication (chẳng hạn HTTP Basic) yêu cầu xác thực. **403 Forbidden** thường là danh tính đã xác thực nhưng thiếu quyền, hoặc một cơ chế khác như CSRF từ chối. Với form login, request chưa đăng nhập có thể bị **redirect** tới trang đăng nhập thay vì trả 401; cấu hình entry point/exception handler quyết định phản hồi cụ thể. Vì thế đừng suy ra “rule không khớp” chỉ từ HTTP status.

Các lỗi cần tránh:

1. **Dùng nhầm stack:** đặt `authorizeHttpRequests` lên `ServerHttpSecurity` hoặc ngược lại; builder/bean và ứng dụng không tương thích.
2. **Mở rule rộng trước rule hẹp:** `/**.permitAll()` bắt hết trước `/admin/**`.
3. **Quên catch-all:** để lọt route không có chính sách rõ ràng, đặc biệt khi sau này thêm endpoint.
4. **Hiểu sai `hasRole`:** `hasRole("ADMIN")` kiểm tra `ROLE_ADMIN` theo convention; `hasAuthority("ADMIN")` là một authority khác.
5. **Không phân biệt authentication và authorization:** có token hợp lệ không có nghĩa token có quyền `report:write`.
6. **Lẫn securityMatcher và requestMatchers/pathMatchers:** một rule không thể bảo vệ request nếu request nằm ngoài security chain đang chọn.
7. **Dựa vào URL cho object-level security:** biết path `/users/{id}` không chứng minh người gọi được truy cập user đó.
8. **Lỗi Reactive I/O:** gọi `block()` hoặc `subscribe()` thủ công trong authorization manager; làm hỏng sequencing, error propagation, cancellation và Reactor Context.
9. **Bỏ qua CSRF hoặc ERROR dispatch:** tưởng các phản hồi 403 là do rule quyền trong khi lớp bảo mật khác đang từ chối.

## 10. Kiểm thử theo ma trận chung

Dùng **cùng bộ tình huống nghiệp vụ** cho MVC và WebFlux, nhưng công cụ test khác nhau.

| Tình huống | Kỳ vọng về phân quyền |
|---|---|
| Anonymous truy cập `GET /public/about` | Được phép qua lớp authorization; nếu không có handler vẫn có thể 404 |
| User có `report:read` gọi `GET /api/reports/42` | Được phép qua lớp authorization |
| User chỉ có `report:write` gọi `GET /api/reports/42` | Bị từ chối vì thiếu `report:read` |
| User có `report:write` gọi `POST /api/reports/42` | Được phép theo rule; phải đáp ứng CSRF nếu bật |
| User có `ROLE_ADMIN` gọi `GET /admin/users` | Được phép theo role |
| User thường không có `ROLE_ADMIN` gọi `GET /admin/users` | Bị từ chối |
| User bất kỳ gọi `GET /not-declared` | Bị từ chối vì catch-all `denyAll` |
| Cùng URL nhưng method chưa khai báo, ví dụ `DELETE` | Bị từ chối nếu không có rule khác cho phép |
| WebFlux custom policy trả kết quả trễ/lỗi | Không cho request đi qua trước khi có quyết định; lỗi đi trong reactive pipeline |

**Servlet:** dùng `MockMvc` cùng `spring-security-test`. Ví dụ trích đoạn test đã cấu hình `MockMvc`, Spring Security và endpoint thật `GET /api/reports/42`:

```java
// static imports: get(...), user(...), status()
mockMvc.perform(get("/api/reports/42")
        .with(user("reader").authorities(
                new SimpleGrantedAuthority("report:read"))))
    .andExpect(status().isOk());
```

**Reactive:** dùng `WebTestClient` kết hợp `spring-security-test` và mock user cho WebFlux. Ví dụ trích đoạn khi WebTestClient đã bind vào ứng dụng và có endpoint tương ứng:

```java
// static import: SecurityMockServerConfigurers.mockUser
webTestClient
    .mutateWith(mockUser().authorities(
            new SimpleGrantedAuthority("report:read")))
    .get().uri("/api/reports/42")
    .exchange()
    .expectStatus().isOk();
```

Trong hai snippet test, import `org.springframework.security.core.authority.SimpleGrantedAuthority` và static import tương ứng của `spring-security-test`. HTTP 200 chỉ hợp lý khi endpoint tồn tại và nghiệp vụ của handler thành công. Kiểm thử cho biết rule có cho qua **và** handler trả gì; để cô lập lỗi, cần kiểm tra cả hai. Với POST dùng test CSRF phù hợp stack hoặc cấu hình ứng dụng thực tế.

Khi test 401/403, nêu rõ mechanism: Basic, form login hay resource server, trạng thái user anonymous/authenticated, và CSRF. Kiểm tra cả negative cases; test chỉ “admin truy cập được” không chứng minh user thường bị chặn.

## 11. Checklist cấu hình và chuyển đổi

1. Xác định ứng dụng thực chạy **Servlet/MVC** hay **WebFlux**; chọn đúng `HttpSecurity`/`ServerHttpSecurity` và loại filter chain.
2. Lập danh sách route công khai, route cần đăng nhập, route cần authority/role và route theo method.
3. Sắp matcher **cụ thể trước, tổng quát sau**; đặt `anyRequest()`/`anyExchange()` cuối mỗi chain.
4. Quy định fallback (`denyAll` hoặc `authenticated`) theo mục tiêu sản phẩm, tránh vô tình mở endpoint mới.
5. Kiểm tra mapping role/authority từ user store hoặc token claims; `hasRole("ADMIN")` khác `hasAuthority("ADMIN")`.
6. Nếu có nhiều chain, phân biệt `securityMatcher` ở cấp chain với matcher cấp rule; kiểm tra `@Order` và catch-all chain.
7. Xem lại CSRF, login entry point, static resources, Servlet dispatch và error responses tùy stack.
8. Với WebFlux, tùy biến authorization phải giữ Publisher, Reactor Context và tính không chặn.
9. Bổ sung authorization nghiệp vụ ở service/method cho quyền theo owner/data; endpoint protection đơn thuần không đủ.
10. Chạy cả test thành công lẫn test từ chối cho anonymous, wrong role, wrong method, URL ngoài policy, missing CSRF và đường dẫn biên.

## 12. Nguồn tham khảo chính thức

- [Spring Security – Authorize HttpServletRequests (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security – WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security – ServerHttpSecurity API](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security – Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)

**Ghi nhớ:** `authorizeHttpRequests` là DSL phân quyền HTTP cho **Servlet**; `authorizeExchange` là DSL tương ứng cho **WebFlux**. Cùng mục tiêu xác định ai được gọi endpoint, nhưng khác builder, chain, matcher, request type và cách thực thi authorization. Cấu hình đúng stack, đúng thứ tự rule và đúng phạm vi chain là nền tảng tránh lộ endpoint khi ứng dụng phát triển.