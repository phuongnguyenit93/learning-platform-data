# AuthorizationWebFilter: thực thi quyết định phân quyền trong Spring Security reactive

## 1. Mục tiêu

Trong kiến trúc bảo mật **Spring WebFlux**, `AuthorizationWebFilter` là bộ lọc quyết định một request có được đi tiếp đến phần xử lý phía sau hay không, dựa vào **chính sách phân quyền đã cấu hình**. Sau bài này, bạn có thể:

1. Xác định vị trí và trách nhiệm của `AuthorizationWebFilter` trong chuỗi `SecurityWebFilterChain`.
2. Giải thích vì sao một quy tắc `permitAll`, `authenticated`, `hasRole` hoặc `denyAll` dẫn tới cho phép hoặc từ chối.
3. Phân biệt **xác thực (authentication)** với **phân quyền (authorization)**; hiểu vai trò của `ReactiveAuthorizationManager` và Reactor Context.
4. Giải thích luồng lỗi từ quyết định không cấp quyền tới **401** hoặc **403**.
5. Viết, chạy và kiểm chứng một API WebFlux bằng Java 17+.

Bài này tập trung vào **phân quyền HTTP request của reactive stack**. Các lớp Servlet như `AuthorizationFilter`, `HttpSecurity`, `SecurityFilterChain` dành cho Spring MVC/Servlet, không thay thế trực tiếp các lớp WebFlux.

## 2. AuthorizationWebFilter là gì?

`org.springframework.security.web.server.authorization.AuthorizationWebFilter` triển khai giao diện `org.springframework.web.server.WebFilter`. Phương thức công khai chính của lớp là:

~~~java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
~~~

Trong đó:

- `ServerWebExchange` đại diện request/response HTTP cùng ngữ cảnh xử lý của WebFlux.
- `WebFilterChain` cho phép chuyển việc xử lý tới filter hoặc handler tiếp theo.
- `Mono<Void>` mô tả tác vụ xử lý bất đồng bộ, hoàn tất khi filter chain hoàn tất hoặc kết thúc với lỗi.
- Bộ lọc sử dụng một `ReactiveAuthorizationManager<? super ServerWebExchange>` để kiểm tra quyền.

**Trách nhiệm cốt lõi:** nhận ngữ cảnh request và authentication hiện tại, yêu cầu thành phần authorization đưa ra quyết định, rồi **cho chuỗi tiếp tục khi được phép** hoặc **phát sinh lỗi từ chối truy cập khi không được phép**. Bộ lọc này **không tự xác thực mật khẩu**, **không tự đọc JWT**, **không sở hữu logic nghiệp vụ** của một endpoint và **không trực tiếp đồng nghĩa với việc trả HTTP 403**; việc chuyển lỗi bảo mật thành HTTP response thuộc cơ chế xử lý exception liên quan.

Một ứng dụng WebFlux thường không phải tự tạo bean `AuthorizationWebFilter`. Khi khai báo `SecurityWebFilterChain` qua `ServerHttpSecurity.authorizeExchange(...)`, Spring Security tạo và sắp xếp bộ lọc cùng authorization manager tương ứng.

## 3. Vị trí trong kiến trúc WebFilter

Sơ đồ khái niệm của **một request đi qua security chain phù hợp**:

~~~text
Client HTTP request
        |
        v
WebFlux WebFilterChainProxy
        |
        +-- Chọn SecurityWebFilterChain phù hợp với request
        |
        v
Các bước context / authentication / bảo vệ khác
        |
        v
ExceptionTranslationWebFilter
        |
        v
AuthorizationWebFilter   <--  Điểm kiểm tra quyền truy cập HTTP
        |
        +-- ReactiveAuthorizationManager nhận:
        |      Mono<Authentication> + ServerWebExchange
        |                |
        |                v
        |      AuthorizationResult (granted/denied)
        |
        +-- ALLOW ------> chain.filter(exchange) --> Controller/Handler
        |
        +-- DENY -------> AccessDeniedException / lỗi từ chối
                               |
                               v
                     ExceptionTranslationWebFilter
                     --> entry point hoặc access-denied handler
                     --> response (ví dụ: 401 / 403)
~~~

Đây là **sơ đồ học tập**, không liệt kê toàn bộ filter và không khẳng định mọi request đều chạy đủ những bước đó. Danh sách filter thực tế phụ thuộc cấu hình (HTTP Basic, form login, OAuth2 resource server, CSRF, CORS...). Trong Spring Security, `SecurityWebFiltersOrder` có các mốc `REACTOR_CONTEXT`, `AUTHENTICATION`, `EXCEPTION_TRANSLATION` và `AUTHORIZATION`; các mốc giúp hiểu thứ tự nhưng không nên tự suy ra bằng một danh sách viết tay cố định.

**Hai tầng lựa chọn khác nhau:**

1. **Chọn chain:** `WebFilterChainProxy` xem `SecurityWebFilterChain.matches(exchange)` để chọn chain phù hợp. Khi nhiều chain cùng match, thứ tự ưu tiên quan trọng; chỉ một chain phù hợp được dùng theo cơ chế lựa chọn.
2. **Chọn rule trong chain:** các quy tắc được khai báo ở `authorizeExchange(...)` được xét theo thứ tự; matcher phù hợp trước quyết định authorization manager nào được gọi.

Ví dụ chain dành riêng cho `/api/**` không bảo vệ các URL khác chỉ bằng việc tồn tại của nó. Nếu dùng nhiều chain, cần chính sách bao phủ rõ ràng cả các URL ngoài phạm vi các matcher chuyên biệt.

## 4. Dòng dữ liệu dùng để quyết định truy cập

### 4.1. Authentication và Reactor Context

Khi request được xác thực, Spring Security có đối tượng `Authentication` gồm thông tin principal, trạng thái xác thực và tập `GrantedAuthority`. Với WebFlux, thông tin bảo mật được truyền qua **Reactor Context**, nơi `ReactiveSecurityContextHolder` có thể đọc `SecurityContext` tương ứng với chuỗi xử lý.

Không giả định một request reactive luôn ở cùng một thread. `SecurityContextHolder` kiểu `ThreadLocal` vốn quen thuộc ở Servlet không phải nguồn dữ liệu thích hợp để tự truy xuất authentication trong code reactive.

`AuthorizationWebFilter` không cần một `Authentication` Java có sẵn ngay lập tức. Nó làm việc với luồng `Mono<Authentication>` để authorization manager có thể lấy thông tin bảo mật trong quá trình subscription, theo cách phù hợp với Reactor. Những rule công khai như `permitAll` có thể cho phép mà không cần dựa vào danh tính đăng nhập.

### 4.2. ReactiveAuthorizationManager

Giao diện quan trọng:

~~~java
public interface ReactiveAuthorizationManager<T> {
    Mono<AuthorizationResult> authorize(
            Mono<Authentication> authentication, T object);

    // Giao diện cũng có phương thức verify(...) mặc định.
}
~~~

Đây là **chữ ký rút gọn để giải thích**, không phải toàn bộ source của interface. Với Spring Security 7.1, `authorize(...)` trả về `Mono<AuthorizationResult>`; kết quả có thể cho biết quyền đã được cấp hay từ chối qua `isGranted()`. `Mono.empty()` biểu thị không tạo ra kết luận rõ ràng (abstain), **không nên xem như một chiến lược chặn truy cập an toàn**. Hãy viết chính sách có kết quả rõ ràng và có rule cuối cho request chưa match.

Một số loại manager hoặc chính sách thường gặp:

| Cấu hình / manager | Ý nghĩa |
| --- | --- |
| `permitAll()` | Cho phép request đi tiếp mà không yêu cầu đăng nhập |
| `denyAll()` | Từ chối request |
| `authenticated()` | Cần danh tính được xác thực theo chiến lược tin cậy của Spring Security |
| `hasRole("ADMIN")` | Kiểm tra authority `ROLE_ADMIN` theo quy tắc tiền tố role mặc định |
| `hasAuthority("report:read")` | Kiểm tra chuỗi authority chính xác |
| `access(customManager)` | Dùng một `ReactiveAuthorizationManager<AuthorizationContext>` riêng |
| `DelegatingReactiveAuthorizationManager` | Phân công cho manager phù hợp với các matcher request |

**Lưu ý version API:** Tài liệu hiện hành của Spring Security dùng `authorize(...)` và `AuthorizationResult`. Các bài cũ có thể dùng `check(...)` và `AuthorizationDecision`. `AuthorizationDecision` vẫn là một kiểu kết quả hữu ích trong nhiều ví dụ, nhưng khi implement API cần tra Javadoc đúng version để tránh dựa vào phương thức đã deprecated hoặc thay đổi.

### 4.3. ServerWebExchange và AuthorizationContext

Các chính sách URL không chỉ dựa vào tên user. Manager có thể cần thông tin từ request như path, HTTP method, header và biến URI template. Khi gọi `access(...)` theo kiểu rule matcher, đối tượng `AuthorizationContext` cung cấp:

- `getExchange()`: truy cập `ServerWebExchange` hiện tại.
- `getVariables()`: các biến URI template được matcher trích xuất, khi có.

Chẳng hạn rule matcher `/members/{username}` có thể lấy biến `username` để so sánh với tên user. Phân quyền theo người sở hữu dữ liệu cần kiểm tra thêm dữ liệu nghiệp vụ trong service, không chỉ so trùng chuỗi URL.

## 5. Kết quả cấp quyền, từ chối và HTTP 401/403

`AuthorizationWebFilter` là điểm **enforcement** đối với authorization HTTP đã khai báo. Để hiểu kết quả từ góc nhìn client, cần ghép nó với `ExceptionTranslationWebFilter`:

| Trạng thái request | Kiểm tra quyền | Kết quả thường gặp khi cấu hình HTTP Basic |
| --- | --- | --- |
| Chưa đăng nhập, gọi endpoint công khai `permitAll` | Cho phép | HTTP 200 nếu handler xử lý thành công |
| Chưa đăng nhập, gọi endpoint cần `authenticated` hoặc role | Không đủ điều kiện | HTTP **401 Unauthorized**, thường kèm challenge `WWW-Authenticate` |
| Đăng nhập hợp lệ nhưng thiếu authority | Không đủ quyền | HTTP **403 Forbidden** |
| Đăng nhập hợp lệ, đủ quyền | Cho phép | Handler được gọi, status do handler quyết định |
| Rule cuối `denyAll` | Từ chối ngay cả user đã đăng nhập | Thường 403 nếu đã xác thực; trường hợp anonymous còn tùy entry point |

**Vì sao không thể nói “AuthorizationWebFilter luôn trả 403”?** Filter quyết định allow/deny và phát sinh kết quả lỗi khi từ chối; `ExceptionTranslationWebFilter` bắt `AccessDeniedException` trong chuỗi được bảo vệ. Với người chưa xác thực, nó có thể gọi `ServerAuthenticationEntryPoint` để bắt đầu đăng nhập; với người đã xác thực nhưng bị từ chối, nó gọi `ServerAccessDeniedHandler`. Kết quả cuối phụ thuộc cơ chế xác thực: HTTP Basic thường là 401; login bằng form có thể chuyển hướng đến trang đăng nhập; bearer token có các quy tắc response/header riêng. Sai username/password cũng có thể bị cơ chế **authentication** từ chối trước khi xét authorization.

Trong môi trường thực tế, status còn có thể chịu ảnh hưởng của custom exception handler, firewall, CSRF, hoặc logic ứng dụng. **401/403 trong bảng là kết quả mong đợi của cấu hình minh họa**, không phải mô tả bất biến của mọi hệ thống Spring Security.

## 6. Ví dụ hoàn chỉnh: quan sát AuthorizationWebFilter qua các request

### 6.1. Project và dependency

Tạo project bằng [Spring Initializr](https://start.spring.io/) với Java **17+**, Maven, package `com.example.authzfilter`, và dependencies **Spring Reactive Web** + **Spring Security**. Có thể dùng Spring Boot **4.1.2** với BOM quản lý Spring Security và Reactor tương thích. File `pom.xml` tối giản đầy đủ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>authz-filter-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

Không khai báo version riêng cho `spring-security-web`, `spring-webflux` hay `reactor-core`: để Spring Boot BOM quản lý đồng bộ. Không thêm Spring MVC starter trong ví dụ này.

### 6.2. Java: một class có đủ cấu hình và handler

Tạo file `src/main/java/com/example/authzfilter/AuthzFilterDemoApplication.java` với nội dung sau:

~~~java
package com.example.authzfilter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class AuthzFilterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthzFilterDemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/api/admin").hasRole("ADMIN")
                        .pathMatchers("/api/read").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetails() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}reader123")
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password("{noop}admin123")
                .roles("ADMIN")
                .build();
        return new MapReactiveUserDetailsService(reader, admin);
    }

    @RestController
    static class DemoController {

        @GetMapping("/public")
        public Mono<String> publicPage() {
            return Mono.just("PUBLIC_OK");
        }

        @GetMapping("/api/read")
        public Mono<String> read() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(SecurityContext::getAuthentication)
                    .map(Authentication::getName)
                    .map(name -> "READ_OK:" + name);
        }

        @GetMapping("/api/admin")
        public Mono<String> admin() {
            return Mono.just("ADMIN_OK");
        }
    }
}
~~~

**Phân tích từng phần:**

- `@EnableWebFluxSecurity` và bean `SecurityWebFilterChain` cấu hình cơ chế security cho WebFlux; `ServerHttpSecurity` tạo chain gồm các thành phần tương ứng.
- `authorizeExchange` khai báo **chính sách**; `AuthorizationWebFilter` thực hiện **đánh giá và chặn/cho qua** theo chính sách đó.
- `/public` cho phép mọi request; `/api/read` cần authentication hợp lệ; `/api/admin` cần `ROLE_ADMIN`; mọi URL không match bị từ chối bởi `denyAll`.
- `httpBasic` là **cơ chế xác thực** username/password, khác với bước authorization; `formLogin` được tắt để không chuyển sang form trong ví dụ này.
- `reader` có `ROLE_USER` nhưng không có `ROLE_ADMIN`; `admin` có `ROLE_ADMIN`. `hasRole("ADMIN")` không yêu cầu viết thêm tiền tố `ROLE_`.
- `ReactiveSecurityContextHolder` được dùng trong handler `/api/read` để đọc danh tính từ Reactor Context sau khi security cho phép.
- `"{noop}"` chỉ dùng cho bài thực hành trên máy local, nhằm tránh cấu hình password encoder; **không dùng mật khẩu lưu dạng rõ trong production**. Với ứng dụng thực tế dùng encoder phù hợp, HTTPS và hệ thống danh tính an toàn.

Vì chỉ dùng HTTP **GET**, ví dụ không cần tắt CSRF. Mặc định CSRF của WebFlux Security vẫn được giữ; nếu thêm POST/PUT/DELETE và thử không có token, có thể bị chặn bởi CSRF trước bước authorization, cần phân biệt loại lỗi.

### 6.3. Chạy dự án

Đứng trong thư mục chứa `pom.xml` rồi chạy:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows, dùng `.\mvnw.cmd spring-boot:run`. Nếu project không có Maven wrapper, dùng Maven đã cài qua lệnh `mvn spring-boot:run`. Khi ứng dụng chạy trên `http://localhost:8080`, mở terminal thứ hai.

### 6.4. Kiểm chứng bằng HTTP

~~~bash
curl -i http://localhost:8080/public

curl -i http://localhost:8080/api/read

curl -i -u reader:reader123 http://localhost:8080/api/read

curl -i -u reader:reader123 http://localhost:8080/api/admin

curl -i -u admin:admin123 http://localhost:8080/api/admin

curl -i -u admin:admin123 http://localhost:8080/unknown
~~~

Kết quả cần quan sát, theo thứ tự trên:

| Request | HTTP status mong đợi | Body đáng chú ý | Giải thích |
| --- | --- | --- | --- |
| `GET /public`, anonymous | **200** | `PUBLIC_OK` | `permitAll` |
| `GET /api/read`, anonymous | **401** | Không phụ thuộc nội dung body | `authenticated` từ chối anonymous; HTTP Basic entry point |
| `GET /api/read`, reader | **200** | `READ_OK:reader` | Có authentication hợp lệ |
| `GET /api/admin`, reader | **403** | Tùy cấu hình | Thiếu `ROLE_ADMIN` |
| `GET /api/admin`, admin | **200** | `ADMIN_OK` | Có `ROLE_ADMIN` |
| `GET /unknown`, admin | **403** | Tùy cấu hình | Rule `anyExchange().denyAll()` chặn trước khi handler tìm đường dẫn |

Với `curl -i`, response còn có các header do HTTP server/security tạo; không nên hard-code toàn bộ header vào test. Đặc biệt, `GET /unknown` thường sẽ là **404** trong một ứng dụng không chặn path, nhưng ở ví dụ này **403** là hợp lý vì policy `denyAll` chặn trước khi request tới tầng tìm handler.

Nếu request đến `/public` mà vẫn bị 401 khi gửi **credentials sai**, đó có thể là lỗi ở bước **authentication** do header HTTP Basic không hợp lệ. `permitAll` chỉ mô tả chính sách phân quyền, không vô hiệu hóa mọi filter khác.

## 7. Vì sao thứ tự rule ảnh hưởng trực tiếp tới AuthorizationWebFilter?

Quan sát cấu hình sau:

~~~java
.authorizeExchange(exchange -> exchange
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin").hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

Đây là **đoạn cấu hình sai để minh họa**, chưa phải method Java độc lập. Request `/api/admin` match `/api/**` trước và chỉ cần đăng nhập; rule `hasRole("ADMIN")` phía sau không phát huy tác dụng cho path đó. Nguyên nhân không phải `AuthorizationWebFilter` “bỏ quên” rule, mà vì **chính sách được định nghĩa theo thứ tự ưu tiên**.

Cấu hình đúng:

~~~java
.authorizeExchange(exchange -> exchange
        .pathMatchers("/api/admin").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().denyAll())
~~~

Sắp **rule đặc thù trước rule rộng**, có rule cuối rõ ràng, sau đó test cả trường hợp thiếu quyền. Đặc biệt chú ý matcher theo **HTTP method**: nếu chỉ bảo vệ `GET /reports/**`, điều đó không tự bảo vệ `POST /reports/**`. Có thể khai báo `pathMatchers(HttpMethod.POST, "/reports/**").hasAuthority("report:write")`; import `org.springframework.http.HttpMethod` tương ứng.

Một khác biệt cần ghi nhớ:

- `securityMatcher(...)` quyết định **SecurityWebFilterChain nào áp dụng**.
- `authorizeExchange(...).pathMatchers(...)` quyết định **quy tắc nào áp dụng bên trong chain đó**.

Nhầm hai cấp matcher có thể dẫn tới chỗ không được bảo vệ hoặc bảo vệ bằng chain không mong muốn.

## 8. Mở rộng: custom ReactiveAuthorizationManager và AuthorizationContext

Những rule có sẵn như `authenticated` hoặc `hasRole` thường đủ cho chính sách URL cơ bản. Khi có yêu cầu phụ thuộc ngữ cảnh, có thể dùng `access(...)`. Ví dụ: với đường dẫn `/members/{username}`, chỉ user mang role `USER` và có tên đúng bằng biến đường dẫn mới được phép.

Bên trong khối `authorizeExchange(exchange -> exchange ... )`, có thể thêm rule **trước rule cuối**:

~~~java
.pathMatchers("/members/{username}")
.access((authentication, context) ->
        authentication
                .map(auth -> (AuthorizationResult) new AuthorizationDecision(
                        auth.getName().equals(context.getVariables().get("username"))
                        && auth.getAuthorities().stream().anyMatch(
                                a -> "ROLE_USER".equals(a.getAuthority()))))
                .defaultIfEmpty(new AuthorizationDecision(false)))
~~~

Đây là **đoạn mã bổ sung vào cấu hình**, không phải một chương trình độc lập; cần import:

~~~java
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationResult;
~~~

Giải thích:

1. `pathMatchers("/members/{username}")` nhận diện URL và trích biến `username`.
2. Spring Security cung cấp `Mono<Authentication>` và `AuthorizationContext` cho custom manager.
3. `map(...)` tạo một `AuthorizationResult` minh bạch: **granted** khi cả username và authority đều phù hợp.
4. `defaultIfEmpty(new AuthorizationDecision(false))` đảm bảo không có authentication thì trả quyết định từ chối rõ ràng.
5. Để request được xử lý thành công, ứng dụng còn phải định nghĩa một handler cho `/members/{username}`; snippet trên chỉ là **policy**, không tự tạo endpoint.

Vì sao cần role ở đây? Nếu chỉ so tên với URL, một anonymous principal có tên mặc định trùng với phần URL có thể gây logic truy cập không mong đợi trong một số cấu hình. Hãy kết hợp kiểm tra danh tính/role và, với nghiệp vụ thật, kiểm tra quyền sở hữu tài nguyên từ nguồn dữ liệu đáng tin cậy.

**Giới hạn:** kiểm tra theo đường dẫn không đủ nếu client có thể chọn id bất kỳ hoặc dữ liệu nhạy cảm có quyền truy cập phức tạp. Quy tắc theo quyền sở hữu bản ghi, tenant, trạng thái nghiệp vụ cần được enforce ở service/data access nữa. Tránh gọi JDBC hoặc API blocking trực tiếp trong `access(...)` trên event loop; nếu chính sách cần truy vấn, ưu tiên component reactive.

## 9. Điều gì xảy ra khi authorization manager không phát ra quyết định?

Một `ReactiveAuthorizationManager` có thể trả về:

- `Mono.just(result)` với `result.isGranted() == true`.
- `Mono.just(result)` với `result.isGranted() == false`.
- `Mono.empty()`, nghĩa là **không quyết định** (abstain).

Không nên gán ý nghĩa “deny” một cách mặc định cho mọi `Mono.empty()`. Giao diện `verify(...)` dùng kết quả authorization để hoàn tất khi không có từ chối, hoặc báo lỗi khi bị từ chối. Trong policy bảo mật tự viết, **hãy luôn tạo quyết định rõ ràng** cho các trường hợp yêu cầu kiểm soát chặt; sử dụng `defaultIfEmpty(new AuthorizationDecision(false))` khi muốn fail closed.

Tương tự, cấu hình `anyExchange().denyAll()` ở cuối giúp tránh trường hợp quên một URL. Khi xử lý quyền phức tạp hoặc nhiều security chain, vẫn phải kiểm thử xem request thực tế có vào đúng chain, đúng rule hay không.

## 10. Liên hệ với các WebFilter khác

| Thành phần | Vai trò | Khác với AuthorizationWebFilter |
| --- | --- | --- |
| `WebFilterChainProxy` | Chọn `SecurityWebFilterChain` và chạy các filter của chain | Điều phối filter, chưa phải quyết định quyền cho từng policy URL |
| `AuthenticationWebFilter` | Đọc credentials / token theo cơ chế xác thực và phối hợp với `ReactiveAuthenticationManager` | Trả lời “ai đang gửi request?” |
| `ReactorContextWebFilter` | Tích hợp SecurityContext từ repository vào Reactor Context | Cung cấp ngữ cảnh, không tự grant role |
| `SecurityContextServerWebExchangeWebFilter` | Tích hợp principal bảo mật vào `ServerWebExchange` | Hỗ trợ truy cập principal, không quyết định rule |
| `AnonymousAuthenticationWebFilter` | Cung cấp biểu diễn anonymous khi cần | Anonymous không đồng nghĩa đã được người dùng xác thực |
| `ExceptionTranslationWebFilter` | Chuyển lỗi truy cập thành entry point hoặc access-denied response | Xử lý hậu quả của denial |
| `AuthorizationWebFilter` | Thực thi policy authorization HTTP | Là điểm đánh giá/thi hành quyền dựa vào manager |
| Reactive method security | Kiểm soát lời gọi phương thức, khi được bật | Một lớp kiểm tra khác ở service/method, không thay thế URL authorization |

**Điểm thường nhầm:** yêu cầu HTTP có thể bị chặn trước khi gọi controller, nhưng điều đó không làm cho mọi thao tác gọi service trực tiếp đều an toàn. Với quyền nghiệp vụ ở method, có thể xem `@EnableReactiveMethodSecurity` và các annotation thích hợp; trong reactive method security, việc truyền SecurityContext phụ thuộc vào Reactor Context.

## 11. Cách debug khi kết quả 401/403 không như mong đợi

Bắt đầu từ **HTTP request thật** (path, method, credentials), sau đó xác định thứ tự rule và security chain. Quy trình kiểm tra gợi ý:

1. **401 ngay cả khi nghĩ đã đăng nhập:** kiểm tra header `Authorization`, password/token, cấu hình HTTP Basic/bearer, trạng thái user, phương thức nhận credentials. Có thể request chưa được xác thực, nên authorization chưa nhận được danh tính đúng.
2. **403 với user đã đăng nhập:** in/kiểm tra tập `GrantedAuthority` từ nguồn đáng tin trong test; `hasRole("ADMIN")` cần `ROLE_ADMIN` theo cấu hình mặc định, còn `hasAuthority("ADMIN")` cần chính xác `ADMIN`.
3. **Rule admin bị bỏ qua:** kiểm tra thứ tự matcher `/api/**` và `/api/admin`. Matcher rộng đặt trước có thể làm rule cụ thể không còn cơ hội được xét.
4. **Một URL công khai bị chặn:** kiểm tra path/method thực tế, chain `securityMatcher`, rule `permitAll`, và khả năng filter khác (ví dụ authentication thất bại, CSRF) tạo lỗi.
5. **Endpoint lẽ ra là 404 lại ra 403:** kiểm tra rule catchall `denyAll`. Authorization có thể chặn trước khi WebFlux tìm được handler.
6. **Nghi ngờ context bị mất:** kiểm tra logic có tách sang luồng xử lý không mang Reactor Context hay đang dùng `SecurityContextHolder` dựa `ThreadLocal`.

Có thể bật log bảo mật ở mức DEBUG **trong môi trường phát triển** bằng `src/main/resources/application.properties`:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Sau đó quan sát request và filter/authorization logs; tên log cụ thể khác nhau theo version, không giả định luôn có một dòng thông báo giống hệt. Không bật TRACE nhạy cảm lâu dài trên production hoặc log credentials, JWT, session cookie. Khi cần chắc chắn, viết integration test kiểm tra status cho từng role thay vì chỉ đọc console.

## 12. Bài tập đánh giá hiểu biết

**Bài 1.** Có ba rule theo đúng thứ tự: `/admin/** -> hasRole("ADMIN")`, `/api/** -> authenticated`, cuối cùng `denyAll`. User `reader` đã xác thực nhưng chỉ có `ROLE_USER`. Request `GET /admin/stats` nhận gì?

**Đáp án:** bị từ chối theo rule `/admin/**`. Với HTTP Basic minh họa và user đã xác thực, kết quả thường là **403**. Rule `/api/**` không áp dụng.

**Bài 2.** Đổi thứ tự: `/api/** -> authenticated` đứng trước `/api/admin -> hasRole("ADMIN")`. Tại sao `reader` có thể vào `/api/admin`?

**Đáp án:** request match rule rộng trước, nên manager yêu cầu `authenticated` và cho qua. Rule chi tiết không được xét cho URL đó.

**Bài 3.** Tại sao lỗi không đủ quyền ở `AuthorizationWebFilter` có thể thành 401 hoặc 403?

**Đáp án:** `ExceptionTranslationWebFilter` chọn entry point đối với principal chưa được xác thực thích hợp, hoặc chọn access-denied handler với user đã xác thực. HTTP Basic thường dẫn đến 401/403; form login có thể redirect.

**Bài 4.** Muốn cho phép `/members/{username}` chỉ khi username thuộc user đăng nhập, nên đọc dữ liệu ở đâu?

**Đáp án:** dùng authentication reactive và `AuthorizationContext.getVariables()` trong custom `access(...)`; đồng thời kiểm tra role và quyền sở hữu dữ liệu ở tầng nghiệp vụ khi cần.

**Bài 5.** Vì sao `permitAll` không có nghĩa request chắc chắn tới controller?

**Đáp án:** nó cho phép ở bước phân quyền HTTP tương ứng; authentication filter, CSRF, firewall, route/handler hoặc thành phần khác vẫn có thể làm request không tới controller.

## 13. Tổng hợp những quy tắc nên ghi nhớ

- `AuthorizationWebFilter` **enforce** quyền HTTP; `ReactiveAuthorizationManager` **đánh giá** chính sách; `ExceptionTranslationWebFilter` **xử lý lỗi thành phản hồi**.
- Reactive authorization dùng `Mono<Authentication>` và Reactor Context; đừng giả định request gắn với một thread.
- Thứ tự `authorizeExchange` rất quan trọng: **matcher cụ thể trước, matcher bao quát sau**.
- Phân biệt rõ `authenticated`, `hasRole` và `hasAuthority`; role có tiền tố `ROLE_` theo cấu hình mặc định.
- Coi `Mono.empty()` trong custom authorization là **không có quyết định**, không phải cơ chế deny tin cậy; khi cần an toàn, trả kết quả denied rõ ràng.
- Thử cả anonymous, đúng role, sai role và URL không được cấu hình. Security policy phải được chứng minh bằng hành vi request thực tế.
- Authorization theo URL là một lớp phòng vệ; quyền theo dữ liệu, chủ sở hữu và tenant vẫn phải được kiểm soát ở nơi xử lý nghiệp vụ.

## 14. Tài liệu chính thức

- [Spring Security — Authorize ServerHttpRequest (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security API — AuthorizationWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/AuthorizationWebFilter.html)
- [Spring Security API — ReactiveAuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
- [Spring Security API — AuthorizationContext](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/AuthorizationContext.html)
- [Spring Security API — ExceptionTranslationWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html)
- [Spring Security API — SecurityWebFiltersOrder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html)
- [Spring Security API — ServerHttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
