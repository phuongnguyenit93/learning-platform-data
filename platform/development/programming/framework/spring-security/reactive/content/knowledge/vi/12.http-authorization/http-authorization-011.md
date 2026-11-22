# Giữ đồng nhất quy tắc phân quyền HTTP cho Controller và RouterFunction trong Spring Security Reactive

## 1. Bài toán và kết quả cần đạt

Spring WebFlux hỗ trợ đồng thời hai cách viết HTTP endpoint: **Controller dựa trên annotation** như @RestController/@GetMapping, và **WebFlux.fn** với RouterFunction/HandlerFunction. Trong một sản phẩm thực tế, đội phát triển có thể dùng Controller cho API cũ, RouterFunction cho API mới, hoặc cùng tồn tại để chuyển đổi dần kiến trúc.

Rủi ro xuất hiện khi một chức năng được viết bằng hai kiểu handler nhưng **có chính sách truy cập khác nhau**. Ví dụ GET /api/profile/annotated yêu cầu đăng nhập, trong khi GET /v2/profile do RouterFunction cung cấp lại vô tình nằm ngoài mẫu /api/** được bảo vệ. Nếu có rule permitAll quá rộng, một bản sao endpoint có thể lộ dữ liệu.

Đích của bài này là: **cùng một ý định bảo mật phải cho cùng kết quả, bất kể endpoint do Controller hay RouterFunction xử lý**.

Sau bài học, bạn có thể:

1. Giải thích ranh giới giữa **SecurityWebFilterChain**, **DispatcherHandler**, **HandlerMapping**, Controller và RouterFunction.
2. Cấu hình một bộ quy tắc trung tâm bằng **ServerHttpSecurity.authorizeExchange** bảo vệ hai mô hình handler.
3. Thiết kế URL, HTTP method và rule precedence để tránh lỗ hổng do thay đổi đường dẫn hoặc thứ tự.
4. Biết khác nhau giữa **route predicate** và **authorization matcher**; không nhầm chúng là một.
5. Tách quyền theo URL với quyền nghiệp vụ theo owner/tenant, chia sẻ service cho cả hai kiểu endpoint.
6. Chạy ví dụ Java 17+ Spring Boot WebFlux có endpoint tương đương ở cả Controller và RouterFunction.
7. Viết **WebTestClient** kiểm tra các cặp endpoint public, authenticated, admin, denyAll, credential sai và URL không khai báo.
8. Lập checklist rà soát khi refactor hoặc thêm một RouterFunction mới.

**Nguyên tắc cốt lõi:** một endpoint được bảo vệ theo **HTTP request thực tế** (path, method, matcher đã thiết kế), không phải nhờ việc method có @GetMapping hay được đăng ký qua RouterFunctions.route().

## 2. Hai kiểu endpoint cùng chạy trong WebFlux

### 2.1. Annotated Controller

Controller ánh xạ request bằng annotation:

~~~java
@RestController
public class AnnotatedApi {
    @GetMapping("/api/profile/annotated")
    public Mono<Map<String, String>> profile(Mono<Principal> principal) {
        return principal.map(p ->
                Map.of("username", p.getName()));
    }
}
~~~

Đây là đoạn minh họa của một class và cần import tương ứng; demo hoàn chỉnh ở phần 8. Handler trả Mono cho mô hình reactive. Mapping được WebFlux nhận diện qua cơ chế handler mapping của annotation.

### 2.2. RouterFunction và HandlerFunction

Cách functional cung cấp một RouterFunction xác định predicate nào dẫn tới HandlerFunction:

~~~java
@Bean
RouterFunction<ServerResponse> routes() {
    return RouterFunctions.route()
            .GET("/public/functional",
                    request -> ServerResponse.ok()
                            .bodyValue(Map.of("mode", "public")))
            .build();
}
~~~

RouterFunction không phải Servlet Filter. Khi request khớp predicate, handler trả **Mono<ServerResponse>**; Spring Boot WebFlux starter đăng ký các thành phần cần thiết để WebFlux.fn và annotated endpoints chạy trong cùng ứng dụng.

### 2.3. Vị trí của Spring Security

~~~text
                 HTTP request
                      |
                      v
          WebFlux WebFilter chain
                      |
                      v
            SecurityWebFilterChain
             Authentication + Authorization
                      |
            Match HTTP method/path
                      |
             +--------+---------+
             | được cho phép?   |
             +---+----------+---+
                 | Có       | Không
                 v          v
          DispatcherHandler  401/403/entry point
                 |
        Chọn HandlerMapping phù hợp
                 |
          +------+------+
          |             |
   Annotated Controller RouterFunction
          |             |
          +------+------+
                 |
           Shared service
                 |
            Response body
~~~

**Điểm quan trọng:** SecurityWebFilterChain là một chuỗi bảo mật ở lớp WebFilter, không chỉ dành cho @RestController. Với cấu hình WebFlux tiêu chuẩn do Spring Boot khởi chạy, request qua Controller và RouterFunction đều chịu các WebFilter phù hợp. Rule security được đánh giá trên ServerWebExchange, trước khi logic handler được thực thi.

Điều này cũng có giới hạn: nếu bạn tự tạo một **HttpHandler khác** và gắn trực tiếp vào server mà không đi qua SecurityWebFilterChain của ứng dụng, hoặc có endpoint nằm ở gateway/service khác, không thể suy luận rằng policy ở ứng dụng hiện tại tự bao phủ nó. Bảo vệ phải được xác nhận ở **đường chạy thực tế**.

## 3. Hai lớp matcher khác nhau

| Khía cạnh | Authorization matcher | Router/Controller matcher |
| --- | --- | --- |
| Được cấu hình ở đâu? | ServerHttpSecurity.authorizeExchange | @GetMapping/@RequestMapping hoặc RouterFunctions.route |
| Dựa trên gì? | ServerWebExchange: path, method, matcher tùy chỉnh | Path, HTTP method, header, Accept, Content-Type, route predicate |
| Mục tiêu | Quyết định có đủ quyền đi tiếp không | Tìm handler xử lý request |
| Kết quả không khớp | Sang rule kế tiếp hoặc deny mặc định | Sang route/mapping khác hoặc 404/405 |
| Thứ tự | Rule được xét theo thứ tự khai báo | RouterFunction được xét theo thứ tự; annotation mapping có quy tắc độ đặc hiệu |
| Cơ chế bảo mật | ReactiveAuthorizationManager | Không tự thay thế authorization của SecurityWebFilterChain |

Đây là hai trách nhiệm độc lập. Nếu một RouterFunction khai báo GET /api/profile/functional, nhưng security policy chỉ bảo vệ /api/profile/annotated, thì việc cùng trả dữ liệu user không tự khiến security policy mở rộng sang URL thứ hai.

### 3.1. URL trên wire là hợp đồng bảo mật

Ví dụ:

~~~java
// Annotation path:
@GetMapping("/api/admin/annotated")

// Functional route:
.GET("/api/admin/functional", handler)
~~~

Cả hai nằm dưới /api/admin/**, nên có thể dùng **một rule chung**:

~~~java
.pathMatchers("/api/admin/**").hasRole("ADMIN")
~~~

Ngược lại, nếu functional route được lỡ tay đặt ở /functions/admin, rule trên không bảo vệ URL mới. Một rule mặc định **anyExchange().denyAll()** có thể giúp URL mới không tự mở, nhưng vẫn cần sửa chính sách nếu route đó là chức năng hợp lệ.

### 3.2. Rule khớp đầu tiên và trường hợp sai thứ tự

~~~java
// ĐÚNG: rule admin cụ thể đứng trước rule /api/** rộng.
.authorizeExchange(ex -> ex
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().denyAll())
~~~

Cấu hình nguy hiểm:

~~~java
// SAI nếu muốn /api/admin/** bắt buộc ROLE_ADMIN.
.authorizeExchange(ex -> ex
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

Ở cấu hình sai, /api/admin/functional có thể khớp /api/** trước, khiến kiểm tra role ở dòng sau không được chọn. **Không có ngoại lệ đặc biệt cho RouterFunction**: cả hai kiểu handler đều mắc lỗi như nhau.

### 3.3. Method cũng thuộc chính sách

Nếu API chỉ muốn công khai **GET** cho hai URL:

~~~java
.pathMatchers(
        HttpMethod.GET,
        "/public/annotated",
        "/public/functional").permitAll()
~~~

Như vậy, chính sách không vô tình công khai POST/PATCH/DELETE tại cùng path nếu sau này nhóm khác thêm handler. Trong Spring Security WebFlux, pathMatchers(HttpMethod, String...) là API của DSL authorization.

**Lưu ý quan trọng:** CSRF được bật mặc định đối với các phương thức thay đổi trạng thái trong cấu hình trình duyệt thông dụng. Khi test POST không có token, request có thể bị từ chối **403 bởi CSRF trước khi tới rule mong muốn**. Không thể dùng một test POST không CSRF để kết luận chắc rằng rule authorization đã chạy đúng. Demo sử dụng GET để tập trung vào phân quyền và dành phần 11 cho rủi ro HTTP method/CSRF.

### 3.4. Route predicate không thay thế security matcher

Functional route có thể viết:

~~~java
.GET("/api/items", accept(MediaType.APPLICATION_JSON),
        handler::listItems)
~~~

Nó có điều kiện **Accept: application/json**. Nếu URL security được cấu hình bằng:

~~~java
.pathMatchers("/api/items").authenticated()
~~~

rule bảo mật vẫn áp dụng cho URL dù request không có Accept phù hợp; sau khi được phép, RouterFunction có thể không chọn handler và WebFlux trả kết quả routing khác. Đừng dựa vào Accept hay Content-Type để làm ranh giới quyền truy cập, trừ khi bạn cố tình dùng ServerWebExchangeMatcher được thiết kế/kiểm thử riêng.

Tương tự, hai request có cùng URL nhưng GET/POST khác nhau có thể khớp các handler khác nhau. Khi có endpoint ghi dữ liệu, hãy định nghĩa authorization theo cả method, role và chủ sở hữu, không giả định tên path là đủ.

## 4. Một ma trận quyền chung cho cả hai loại handler

Trước khi viết controller/router, liệt kê các **hành vi mong muốn**, rồi để cả hai cùng tuân theo:

| Mục đích | Annotated endpoint | Functional endpoint | Rule chung |
| --- | --- | --- | --- |
| Công khai | GET /public/annotated | GET /public/functional | GET các URL public → permitAll |
| Hồ sơ của caller | GET /api/profile/annotated | GET /api/profile/functional | /api/** → authenticated |
| Thao tác admin | GET /api/admin/annotated | GET /api/admin/functional | /api/admin/** → hasRole ADMIN |
| Đã khóa | GET /internal/annotated | GET /internal/functional | /internal/** → denyAll |
| URL không được công bố | /unlisted | /unlisted-functional | anyExchange → denyAll |

Việc sắp xếp URL dưới **cùng các namespace mang ý nghĩa quyền** sẽ giảm việc lặp chính sách cho từng handler. Khi có quyền khác nhau theo phương thức (ví dụ GET đọc công khai, POST chỉ nhân viên được ghi), thêm rule method rõ ràng.

Một nhóm quy tắc điển hình:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers(
                HttpMethod.GET,
                "/public/annotated",
                "/public/functional").permitAll()
        .pathMatchers("/internal/**").denyAll()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().denyAll())
~~~

**Vì sao public là danh sách chính xác?** Nếu dùng /public/**.permitAll(), việc một developer vô tình thêm route /public/debug-secrets có thể mở endpoint. Whitelist URL cụ thể làm việc thêm route yêu cầu **cập nhật chính sách một cách có chủ đích**. Có thể dùng namespace rộng cho static resources tin cậy, nhưng phải hiểu nội dung nào được phục vụ ở đó.

**Vì sao anyExchange().denyAll()?** Một RouterFunction có thể được thêm mà không cần chỉnh Controller; fail-closed giảm khả năng URL mới tự công khai. Tuy nhiên, denyAll **không phải bộ kiểm tra owner/tenant** và không tự động nhận ra endpoint nào nên được phép.

## 5. Dùng chung nghiệp vụ, không phân tán kiểm tra quyền

Có hai mức bảo vệ:

1. **HTTP authorization:** kiểm tra URL, HTTP method, role/scope trên SecurityWebFilterChain.
2. **Business authorization:** kiểm tra caller có quyền trên bản ghi cụ thể (owner, tenant, quan hệ nhóm, trạng thái tài nguyên) trong service/repository.

Hai kiểu handler nên gọi **cùng service nghiệp vụ**, không nhân đôi một đoạn kiểm tra quyền:

~~~text
Controller GET /api/orders/42 -----+
                                   |
                                   v
                           OrderService.read(...)
                                   ^
                                   |
RouterFunction GET /api/orders/42 -+
                                   |
                                   v
                    owner/tenant check + query
~~~

Với ứng dụng thật, tránh đăng ký hai handler cùng một method+path rồi kỳ vọng WebFlux sẽ tự chọn theo mục đích. Sơ đồ chỉ minh họa cách dùng chung service khi endpoint ở hai path khác nhau hoặc khi refactor.

Ví dụ service nghiệp vụ:

~~~java
// Minh họa tích hợp: OrderDto và repository là thành phần ứng dụng.
public Mono<OrderDto> readOrder(String orderId, String actorId) {
    return repository.findByIdAndOwnerId(orderId, actorId);
}
~~~

**actorId** phải được lấy từ Authentication đã xác thực (hoặc subject/claim đã xác minh), không lấy từ query parameter do client tự khai. Trong hệ đa tenant, truy vấn còn cần tenant ID từ nguồn tin cậy.

### 5.1. Method security như lớp bổ sung

Nếu một dịch vụ dùng chung cần quyền ADMIN dù được gọi từ handler nào, có thể kích hoạt **@EnableReactiveMethodSecurity** và dùng **@PreAuthorize("hasRole('ADMIN')")** trên method của **Spring bean** trả reactive Publisher phù hợp. Khi đó Controller và RouterFunction cùng gọi bean, được kiểm tra nhất quán tại tầng method.

Tuy vậy:
- @PreAuthorize không thay thế rule URL đối với truy cập không có authentication.
- Self-invocation trong cùng class có thể bỏ qua proxy.
- Với record-level authorization vẫn cần kiểm tra quyền dựa vào dữ liệu/tài nguyên thật.
- Nếu có custom RouterFunction filter kiểm tra quyền, nó chỉ áp dụng cho các functional routes nằm trong phạm vi filter đó; Controller không tự chịu cùng filter. Không dùng **RouterFunction.filter()** như chính sách chung duy nhất cho cả hai loại handler.

Bài demo bên dưới tập trung vào **một SecurityWebFilterChain** và một ProfileService dùng chung để thể hiện chính xác vấn đề được giao.

## 6. Ví dụ Java 17+ chạy được với Spring Boot WebFlux

Phiên bản ví dụ cố định: **Java 17+**, **Spring Boot 3.5.16**, **Gradle 8.x** tương thích (Spring Boot 3.5.16 hỗ trợ Gradle từ 8.4). Mọi endpoint chạy trong **một ứng dụng Spring WebFlux**, không thêm spring-boot-starter-web.

Hai user học tập:

| User | Password demo | Authorities |
| --- | --- | --- |
| reader | reader-pass | ROLE_USER |
| admin | admin-pass | ROLE_USER, ROLE_ADMIN |

Các URL public được whitelist chính xác theo GET. Một controller và một RouterFunction có cùng cấu trúc phản hồi hồ sơ nhờ gọi **ProfileService** dùng chung.

Cấu trúc:

~~~text
hybrid-webflux-security/
├── settings.gradle
├── build.gradle
├── src/main/java/example/hybrid/HybridApplication.java
├── src/main/java/example/hybrid/SecurityConfig.java
├── src/main/java/example/hybrid/ProfileService.java
├── src/main/java/example/hybrid/AnnotatedApi.java
├── src/main/java/example/hybrid/FunctionalRoutes.java
└── src/test/java/example/hybrid/HybridAuthorizationTest.java
~~~

### 6.1. settings.gradle

~~~groovy
rootProject.name = 'hybrid-webflux-security'
~~~

### 6.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot quản lý phiên bản Spring Framework, Spring Security và Reactor theo BOM, tránh tự chọn các thư viện lệch nhánh. Dùng **Gradle Wrapper** được kiểm soát trong dự án thực tế. Bài minh họa dùng gradle trực tiếp vì wrapper chưa được tạo.

### 6.3. HybridApplication.java

~~~java
package example.hybrid;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HybridApplication {

    public static void main(String[] args) {
        SpringApplication.run(HybridApplication.class, args);
    }
}
~~~

### 6.4. SecurityConfig.java — một policy cho mọi WebFlux handler

~~~java
package example.hybrid;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        // Chỉ hai endpoint GET này public.
                        .pathMatchers(
                                HttpMethod.GET,
                                "/public/annotated",
                                "/public/functional").permitAll()
                        // Cấm tất cả route nội bộ, không phân biệt handler.
                        .pathMatchers("/internal/**").denyAll()
                        // Phải đứng trước /api/**.
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        // Route mới chưa liệt kê được đóng mặc định.
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }
}
~~~

**Điểm cần quan sát:**

- Không có tên class Controller hoặc RouterFunction nào trong authorization rules.
- Security policy dựa vào **method+path** của HTTP exchange.
- Rule /api/admin/** được đặt **trước** /api/** vì matcher khớp đầu tiên quyết định rule.
- /internal/** bị từ chối kể cả khi user đăng nhập là admin.
- Các path không khai báo bị deny mặc định; chúng không trở thành public chỉ vì một developer thêm RouterFunction.
- HTTP Basic chỉ làm nhiệm vụ lấy/kiểm chứng credential. Nếu user có password đúng nhưng role không đủ, kết quả authorization vẫn bị từ chối.
- **Không tắt CSRF**; demo chỉ dùng GET nên tập trung vào phân quyền GET. Khi bổ sung phương thức ghi, phải thiết kế CSRF đúng với browser/session/credential của ứng dụng.

**Password:** demo dùng password cố định để thử localhost và BCryptPasswordEncoder để lưu hash. Không sao chép credential hard-code vào production. Dùng HTTPS cho HTTP Basic thật vì Base64 không bảo vệ bí mật đường truyền.

### 6.5. ProfileService.java — cùng logic cho cả hai kiểu handler

~~~java
package example.hybrid;

import java.util.Map;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ProfileService {

    public Mono<Map<String, String>> profile(
            String username, String source) {

        return Mono.just(Map.of(
                "username", username,
                "source", source));
    }
}
~~~

Service chỉ minh họa cách chia sẻ logic hiển thị. Tham số username sẽ do **principal đã được framework xác thực** cung cấp trong cả hai kiểu handler; client không thể tự chọn username thông qua query parameter ở endpoint này. Với tài nguyên thật, nên dùng subject/user ID ổn định và kiểm tra owner/tenant trước khi truy cập repository.

### 6.6. AnnotatedApi.java — endpoint bằng annotation

~~~java
package example.hybrid;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class AnnotatedApi {

    private final ProfileService profiles;

    public AnnotatedApi(ProfileService profiles) {
        this.profiles = profiles;
    }

    @GetMapping("/public/annotated")
    public Mono<Map<String, String>> publicInfo() {
        return Mono.just(Map.of(
                "source", "annotated",
                "visibility", "public"));
    }

    @GetMapping("/api/profile/annotated")
    public Mono<Map<String, String>> profile(Mono<Principal> principal) {
        return principal.flatMap(p ->
                profiles.profile(p.getName(), "annotated"));
    }

    @GetMapping("/api/admin/annotated")
    public Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("admin", "annotated"));
    }

    @GetMapping("/internal/annotated")
    public Mono<Map<String, String>> internal() {
        return Mono.just(Map.of("internal", "not-exposed"));
    }
}
~~~

Có thể thay profile(Mono<Principal>) bằng ReactiveSecurityContextHolder.getContext() khi service cần tự đọc danh tính. Trong ví dụ này nhận Mono<Principal> từ argument resolver của WebFlux giúp minh họa rõ nguồn username đã được xác thực.

### 6.7. FunctionalRoutes.java — endpoint bằng RouterFunction

~~~java
package example.hybrid;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> functionalApi(ProfileService profiles) {
        return RouterFunctions.route()
                .GET("/public/functional", request ->
                        ServerResponse.ok().bodyValue(Map.of(
                                "source", "functional",
                                "visibility", "public")))
                .GET("/api/profile/functional", request ->
                        request.principal()
                                .flatMap(p -> profiles.profile(
                                        p.getName(), "functional"))
                                .flatMap(data ->
                                        ServerResponse.ok().bodyValue(data)))
                .GET("/api/admin/functional", request ->
                        ServerResponse.ok().bodyValue(
                                Map.of("admin", "functional")))
                .GET("/internal/functional", request ->
                        ServerResponse.ok().bodyValue(
                                Map.of("internal", "not-exposed")))
                .build();
    }
}
~~~

**Sự khác biệt kỹ thuật:** RouterFunction sử dụng **ServerRequest.principal()** để trả Mono<Principal>, trong khi Controller có thể nhận **Mono<Principal>** như tham số method. Tuy API Java khác nhau, chúng cùng dựa trên danh tính mà Spring Security đã thiết lập cho request.

**Vì sao không gọi profiles.profile("admin", ...)?** Vì đó là tên gán cứng, có thể dẫn tới giả mạo nghiệp vụ nếu dùng làm quyền. Chỉ lấy username từ principal sau khi URL rule authenticated đã được đáp ứng.

**Vì sao không thêm một RouterFunction.filter() để tự kiểm tra role?** Vì filter cục bộ chỉ bảo vệ các functional routes gắn với router tương ứng, **không bảo vệ AnnotatedApi**. Bảo vệ HTTP chung phải nằm ở SecurityWebFilterChain; filter route chỉ dùng cho logic riêng của functional endpoints như kiểm tra định dạng đầu vào hoặc enrich response, không thay thế authorization chung.

### 6.8. Chạy ứng dụng

Ở thư mục hybrid-webflux-security, dùng JDK 17+, Gradle 8.4+ và kết nối Maven Central:

~~~bash
gradle bootRun
~~~

Ứng dụng mặc định lắng nghe http://localhost:8080 nếu không có cấu hình server.port khác. Các endpoint GET có hai kiểu trả dữ liệu gần giống nhau để tiện kiểm thử. Chỉ dùng HTTP localhost cho học tập; khi có credential thật phải dùng HTTPS.

## 7. Thử HTTP bằng curl: hai handler, một chính sách

Ở một terminal Bash khác:

~~~bash
# Public: cả hai đều 200.
curl -s http://localhost:8080/public/annotated
# {"source":"annotated","visibility":"public"}

curl -s http://localhost:8080/public/functional
# {"source":"functional","visibility":"public"}

# Chưa đăng nhập: cả hai profile đều yêu cầu authentication.
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/profile/annotated
# 401

curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/profile/functional
# 401

# Username/password sai: không handler nào được phép trả dữ liệu.
curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:wrong-pass \
  http://localhost:8080/api/profile/functional
# 401

# Đăng nhập hợp lệ: hai handler trả cùng username đã xác thực.
curl -s -u reader:reader-pass \
  http://localhost:8080/api/profile/annotated
# {"username":"reader","source":"annotated"}

curl -s -u reader:reader-pass \
  http://localhost:8080/api/profile/functional
# {"username":"reader","source":"functional"}

# Người dùng thường thiếu ROLE_ADMIN: cả hai đều 403.
curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:reader-pass http://localhost:8080/api/admin/annotated
# 403

curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:reader-pass http://localhost:8080/api/admin/functional
# 403

# Admin hợp lệ: cả hai đều 200.
curl -s -u admin:admin-pass http://localhost:8080/api/admin/annotated
# {"admin":"annotated"}

curl -s -u admin:admin-pass http://localhost:8080/api/admin/functional
# {"admin":"functional"}

# DenyAll: ngay cả admin cũng bị từ chối.
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin-pass http://localhost:8080/internal/annotated
# 403

curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin-pass http://localhost:8080/internal/functional
# 403

# URL chưa có trong danh sách policy: bị chặn mặc định.
curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:reader-pass http://localhost:8080/unlisted
# 403
~~~

Các dòng sau # là **kết quả dự kiến**, không phải output đã thu từ một máy chủ đang chạy. Với Map JSON, thứ tự field không phải hợp đồng; WebTestClient bên dưới so sánh giá trị theo JSON path. Trên Windows PowerShell, dùng **curl.exe** và đặt lệnh trên một dòng thay vì ký hiệu tiếp dòng của Bash.

**Quan sát quan trọng:** đối với 401 của HTTP Basic, response thường có header WWW-Authenticate: Basic ...; 403 là từ chối quyền cho người đã xác thực. Controller và RouterFunction không được tự đổi status thành 200 rồi nhét {"error": "..."} vào body để che lỗi authorization.

### 7.1. Ma trận kỳ vọng

| Caller | Path annotation | Path functional | Chính sách | Cặp kết quả |
| --- | --- | --- | --- | --- |
| Guest | /public/annotated | /public/functional | GET permitAll | 200 / 200 |
| Guest | /api/profile/annotated | /api/profile/functional | authenticated | 401 / 401 |
| Credential sai | /api/profile/annotated | /api/profile/functional | Authentication thất bại | 401 / 401 |
| reader | /api/profile/annotated | /api/profile/functional | authenticated | 200 / 200 |
| reader | /api/admin/annotated | /api/admin/functional | hasRole ADMIN | 403 / 403 |
| admin | /api/admin/annotated | /api/admin/functional | hasRole ADMIN | 200 / 200 |
| admin | /internal/annotated | /internal/functional | denyAll | 403 / 403 |

Đây chính là cách xác minh **sự đồng nhất của policy qua hai mô hình handler**, thay vì chỉ test Controller rồi bỏ RouterFunction.

## 8. Kiểm thử bằng WebTestClient: một bộ test cho cả hai kiểu endpoint

Dùng **WebTestClient** để kiểm tra thực tế Spring Security WebFilter + RouterFunctionMapping + annotated handler trong cùng Spring context. Không thay thế bằng unit test chỉ gọi handler method trực tiếp vì như thế sẽ không đi qua SecurityWebFilterChain.

Tệp src/test/java/example/hybrid/HybridAuthorizationTest.java:

~~~java
package example.hybrid;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HybridAuthorizationTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ProfileService profiles;

    private static final List<String> PUBLIC = List.of(
            "/public/annotated",
            "/public/functional");

    private static final List<String> PROFILE = List.of(
            "/api/profile/annotated",
            "/api/profile/functional");

    private static final List<String> ADMIN = List.of(
            "/api/admin/annotated",
            "/api/admin/functional");

    private static final List<String> INTERNAL = List.of(
            "/internal/annotated",
            "/internal/functional");

    @Test
    void bothPublicEndpointsAcceptAnonymousClient() {
        for (String path : PUBLIC) {
            client.get().uri(path)
                    .exchange()
                    .expectStatus().isOk()
                    .expectBody()
                    .jsonPath("$.visibility").isEqualTo("public");
        }
    }

    @Test
    void bothProfileEndpointsRejectMissingCredentials() {
        for (String path : PROFILE) {
            client.get().uri(path)
                    .exchange()
                    .expectStatus().isUnauthorized()
                    .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
        }
    }

    @Test
    void bothProfileEndpointsRejectWrongCredentials() {
        for (String path : PROFILE) {
            client.get().uri(path)
                    .headers(h -> h.setBasicAuth("reader", "wrong-pass"))
                    .exchange()
                    .expectStatus().isUnauthorized();
        }
    }

    @Test
    void bothProfileEndpointsReturnTheSameVerifiedUser() {
        for (String path : PROFILE) {
            client.get().uri(path)
                    .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                    .exchange()
                    .expectStatus().isOk()
                    .expectBody()
                    .jsonPath("$.username").isEqualTo("reader");
        }
    }

    @Test
    void bothAdminEndpointsRequireRoleAdmin() {
        for (String path : ADMIN) {
            client.get().uri(path)
                    .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                    .exchange()
                    .expectStatus().isForbidden();

            client.get().uri(path)
                    .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                    .exchange()
                    .expectStatus().isOk();
        }
    }

    @Test
    void bothInternalEndpointsAreDeniedEvenForAdmin() {
        for (String path : INTERNAL) {
            client.get().uri(path)
                    .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                    .exchange()
                    .expectStatus().isForbidden();
        }
    }

    @Test
    void newUnlistedUrlCannotBeAccessedEvenWithLogin() {
        client.get().uri("/unlisted")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void sharedServiceEmitsTheSameShapeForBothAdapters() {
        StepVerifier.create(profiles.profile("alice", "annotated"))
                .expectNext(Map.of(
                        "username", "alice",
                        "source", "annotated"))
                .verifyComplete();

        StepVerifier.create(profiles.profile("alice", "functional"))
                .expectNext(Map.of(
                        "username", "alice",
                        "source", "functional"))
                .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**Kết quả mong đợi:** 8 test PASS và Gradle in BUILD SUCCESSFUL khi mã/dependencies được nhập đúng, JDK/Gradle đáp ứng yêu cầu và ứng dụng khởi động thành công.

### 8.1. Điều gì được test?

- **Public parity:** cả Controller và RouterFunction đều cho guest truy cập cùng loại dữ liệu công khai.
- **Authentication parity:** cả hai trả 401 khi không có credential hoặc password sai.
- **Identity parity:** request hợp lệ đều dùng tên từ principal đã xác minh, không hard-code username.
- **Role parity:** cả hai từ chối ROLE_USER và chấp nhận ROLE_ADMIN ở khu admin.
- **Deny parity:** cả hai route nội bộ không thể bị xem ngay cả bởi admin.
- **Fail-closed:** URL không khai báo bị deny khi user đã đăng nhập, không trả 404/200 một cách ngẫu nhiên tùy thứ tự route.
- **Shared service:** logic dữ liệu được tái sử dụng; test StepVerifier kiểm tra tín hiệu Mono và kết quả ánh xạ.

**Giới hạn của unit test service:** StepVerifier gọi trực tiếp profiles.profile không đi qua HTTP security. Nó chỉ khẳng định cùng hàm trả dữ liệu đúng. Để biết policy thực sự được áp dụng phải dùng WebTestClient như các test phía trên.

### 8.2. Vì sao không assert body JSON bằng chuỗi cố định?

Một Map có thể được serialize với thứ tự key không phải điều kiện bảo mật. Kiểm thử field bằng jsonPath, hoặc giải mã DTO và so sánh thuộc tính, sẽ ổn định hơn so với so sánh nguyên chuỗi JSON. Lưu ý test status, headers, behavior khi không có credential và khi đủ/quá quyền vẫn quan trọng hơn định dạng thuần túy.

### 8.3. Khi thêm RouterFunction mới, sửa test trước

Ví dụ nhóm phát triển thêm:

~~~java
.GET("/api/admin/export", request ->
        ServerResponse.ok().bodyValue(Map.of("export", "ok")))
~~~

Vì route nằm dưới /api/admin/**, rule trung tâm vẫn yêu cầu ROLE_ADMIN. Thêm test guest/reader/admin với URL mới để bắt regression. Ngược lại, nếu lỡ thêm dưới /reports/export, anyExchange().denyAll() sẽ từ chối; đây là tín hiệu rằng người phát triển cần **quyết định rõ policy trước khi mở route**.

Không dùng test chỉ gọi RouterFunction.route() độc lập và kết luận app đã an toàn: kiểu test đó bỏ SecurityWebFilterChain, authentication manager và các WebFilter khác.

## 9. Tránh lỗ hổng trong quá trình refactor Controller ↔ RouterFunction

Hãy xem một kế hoạch refactor từ:

~~~java
@GetMapping("/api/orders/{id}")
public Mono<OrderDto> byId(@PathVariable String id) {
    return orderService.loadForCurrentUser(id);
}
~~~

sang:

~~~java
// Minh họa tích hợp; handler cần được cài đặt trong ứng dụng.
return RouterFunctions.route()
        .GET("/api/orders/{id}", orderHandler::byId)
        .build();
~~~

Để chuyển đổi an toàn:

1. **Bảo toàn HTTP contract**: URL, method, required content-type/accept, path variable, response schema, status và media type.
2. **Bảo toàn security path**: không đổi /api/orders/{id} thành /func/orders/{id} nếu rule authorization vẫn match /api/**.
3. **Bảo toàn caller identity**: Controller có thể nhận Principal/Authentication, RouterFunction phải lấy từ ServerRequest.principal() hoặc Reactor SecurityContext; đừng mặc định principal từ query string.
4. **Bảo toàn service policy**: gọi cùng service kiểm tra owner/tenant, không chuyển query dữ liệu trực tiếp vào handler và bỏ qua quyền.
5. **Bảo toàn exception behavior**: @RestControllerAdvice và RouterFunction filters có phạm vi xử lý khác nhau; mọi nhánh phải không làm lộ stack trace hoặc dữ liệu bị chặn.
6. **Bảo toàn observability**: actor ID, correlation ID, audit và metrics không được tự ý bỏ khi đổi handler.
7. **Bảo toàn kiểm thử**: chạy test theo ma trận cho cả bản cũ/bản mới trong giai đoạn chuyển đổi; test giá trị 401/403/2xx, ownership và CSRF khi có method ghi.
8. **Bảo vệ route chưa công bố**: anyExchange().denyAll() vẫn chặn path mới nếu rule chưa được duyệt.

### 9.1. Không đăng ký hai handler cùng đường/method rồi đoán kết quả

Nếu Controller và RouterFunction cùng khai báo GET /api/orders/42, cần biết HandlerMapping nào được chọn và thứ tự cấu hình cụ thể. WebFlux hỗ trợ cả hai kiểu trong cùng DispatcherHandler, nhưng **không có chuyện security sẽ chạy hai lần cho cả hai rồi chọn nhánh an toàn hơn**.

Nên dùng URL riêng trong giai đoạn chuyển đổi hoặc chỉ giữ một mapping hoạt động cho mỗi method+path ở từng thời điểm. Nếu buộc phải có hai route cùng lúc, phải xác định thứ tự routing một cách rõ ràng và test bằng HTTP request thực.

### 9.2. Trật tự router không giống trật tự authorization

Trong RouterFunctions.route(), functional routes thường được thử **theo thứ tự khai báo**. Khi có route động rộng:

~~~java
return RouterFunctions.route()
        .GET("/api/items/special", handler::special)
        .GET("/api/items/{id}", handler::byId)
        .build();
~~~

Đặt /special trước /{id} để route cụ thể không bị xem như một biến path id. Với Controller, annotation routing có cơ chế chọn mapping theo độ đặc hiệu; không suy luận hai cơ chế ưu tiên route giống hệt nhau.

Nhưng **cả hai đều độc lập với thứ tự** authorizeExchange. Rule security được xét theo thứ tự khai báo riêng; route đúng mà rule security sai vẫn có thể lộ quyền, và rule đúng mà route sai có thể trả nhầm handler.

### 9.3. Nested RouterFunction và prefix thực tế

Nếu dùng:

~~~java
return RouterFunctions.route()
        .path("/api", api -> api
                .GET("/orders", handler::list)
                .GET("/admin/report", handler::report))
        .build();
~~~

Các path HTTP cuối cùng là /api/orders và /api/admin/report. Hãy kiểm tra **full path sau nesting**, không chỉ so sánh chuỗi literal "/orders" hoặc "/admin/report" trong source với pathMatchers.

Chính sách ở SecurityWebFilterChain nên match **URI mà client thực sự gọi**, không match file/class/router builder đặt ở đâu. Trong hệ thống reverse proxy có rewrite prefix, phải test đường dẫn **mà ứng dụng thực sự nhìn thấy**, không chỉ URL ở gateway.

### 9.4. Mọi handler nên dùng một chuẩn nhận diện caller

Ở Controller, có thể dùng method parameter **Mono<Principal>**, hoặc Spring Security WebFlux có **ReactiveSecurityContextHolder.getContext()**. Ở RouterFunction, dùng **ServerRequest.principal()** hoặc ReactiveSecurityContextHolder. Cả hai phải xuất phát từ cùng một security pipeline.

Không dùng:

~~~java
// Sai: header do client tự gửi không phải danh tính đã xác thực.
String actor = request.headers().firstHeader("X-User");
~~~

Một header custom chỉ đáng tin nếu đã được một gateway tin cậy xác thực và thiết kế ranh giới trust/proxy tương ứng. Trong demo ta dùng HTTP Basic, nên name phải lấy từ principal mà Spring Security đã cung cấp.

### 9.5. Method security là defense in depth

Trong code lớn, một số dịch vụ có thể bị gọi từ HTTP endpoint, queue consumer, scheduler hoặc internal RPC. Bảo vệ HTTP path không tự bảo vệ mọi entry point khác. Cần policy ở service/data, có thể kết hợp method security reactive, authorization cho message consumer và owner checks. Giữ **một nguồn quyết định quyền nghiệp vụ** để tránh Controller và RouterFunction đưa ra kết luận khác nhau.

## 10. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Bảo vệ Controller bằng URL, quên URL của RouterFunction | Endpoint functional bị lộ hoặc ngược policy | Định nghĩa namespace + test cả hai |
| Chỉ kiểm tra role trong RouterFunction.filter() | Controller không được bảo vệ tương tự | SecurityWebFilterChain và shared service policy |
| Chỉ dựa vào @PreAuthorize trên method Controller | Functional handler không tự có annotation tương đương | HTTP authorization trung tâm + method security tại service dùng chung |
| Đặt /api/**.authenticated trước /api/admin/**.hasRole | Rule admin bị che, cả hai handler dễ bị mở | Rule cụ thể trước rule rộng |
| Dùng /public/**.permitAll mà thêm route debug ở dưới | Debug data vô tình public | Exact public whitelist hoặc review prefix |
| Dùng anyExchange().permitAll trong lúc phát triển và quên đổi | URL mới tự công khai | anyExchange().denyAll() |
| Tưởng RouterFunction tự dùng SecurityFilterChain của servlet | Sai stack trong WebFlux | ServerHttpSecurity, SecurityWebFilterChain, WebFilter |
| Dựa vào tên class khi viết matcher | Matcher không match path thực tế | Dùng method/path của HTTP exchange |
| Đặt RouterFunction GET và security POST rule rồi cho rằng bảo vệ GET | Không kiểm soát đúng method | Đồng bộ ma trận method |
| Đổi prefix route khi refactor mà quên cập nhật policy | Policy miss/bypass | Kiểm thử URL sau refactor |
| Chỉ test handler unit | Không kiểm tra WebFilter/authentication/authorization | WebTestClient tích hợp |
| Trả ID người dùng từ query parameter trong handler | Có thể giả mạo chủ thể | Lấy Principal/Authentication đã được xác minh |
| Dùng authenticated() là đủ cho mọi dữ liệu user | Bất kỳ user nào cũng thử đọc record khác | owner/tenant authorization |
| Đăng ký cùng method+path ở hai mapping | Không biết handler thực sự được chọn | Chỉ một mapping hoặc test thứ tự rõ ràng |
| Coi permitAll nghĩa là không chạy authentication | Basic credential sai vẫn có thể tạo 401 | Hiểu authn/authz riêng |
| Tắt CSRF cho mọi POST vì test 403 | Mở rủi ro request giả mạo | Xử lý CSRF theo browser/client |
| Tưởng 404 sau route miss có nghĩa đã test security | Có thể route chưa match, không hề kiểm tra quyền của handler mới | Test đúng endpoint tồn tại với nhiều role |
| Quên securityMatcher khi có nhiều chain | Request chọn chain không dự kiến | Test chain order/URL thực tế |
| Chỉ bảo vệ WebFlux ở service trong khi gateway expose resource riêng | URL ngoài không bị Spring Security bảo vệ | Phân tích topology và bảo vệ tại boundary đúng |

## 11. Phương thức ghi, CSRF và tình huống 404/405

Bài demo chỉ có GET để cô lập bài toán đồng nhất URL authorization. Trong sản phẩm, Controller có @PostMapping hoặc RouterFunction.POST sẽ làm phát sinh thêm vấn đề:

- **POST** dưới /public không được tự công khai chỉ vì GET cùng path là public.
- **CSRF** mặc định bảo vệ các method không an toàn trong bối cảnh Spring Security WebFlux. Một POST thiếu token có thể trả 403 trước khi code authorization được chạy.
- **CORS preflight OPTIONS** thường không mang credential. Nếu browser cross-origin, cần cấu hình CORS với origin/header/method được phép và thứ tự WebFilter chính xác; không vì 401 của preflight mà mở rộng permitAll cho toàn bộ URL.
- **DELETE /api/items/{id}** cần role/authority thích hợp và owner check, không chỉ authenticated.
- Một URL không match handler có thể trả **404**, hoặc nếu path có handler khác method có thể trả **405**, nhưng security filter vẫn có thể trả 401/403 **trước** khi routing. Không dựa vào status route miss để đo quyền của endpoint chưa được chạy.

Một policy method-sensitive minh họa:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers(HttpMethod.GET, "/catalog/**").permitAll()
        .pathMatchers(HttpMethod.POST, "/catalog/**")
                .hasAuthority("CATALOG_WRITE")
        .pathMatchers(HttpMethod.DELETE, "/catalog/**")
                .hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

Đây là đoạn cấu hình **trong** SecurityWebFilterChain, không phải file Java độc lập. Nếu có route functional .POST("/catalog/items") hay Controller @PostMapping("/catalog/items"), cả hai cùng chịu rule CATALOG_WRITE. Khi thử POST qua WebTestClient, cần cung cấp CSRF token nếu hệ thống bật CSRF và request có liên quan đến việc bảo vệ CSRF; nếu không, test có thể thất bại vì CSRF chứ chưa chứng minh rule role.

Đừng tự disable CSRF chỉ để làm cho tất cả test đổi trạng thái trả 200. Với API chỉ nhận bearer token trong Authorization header và không dùng cookie/browser tự gửi credential, chính sách CSRF có thể khác, nhưng phải đánh giá đúng theo mô hình xác thực thay vì máy móc sao chép.

## 12. Nhiều SecurityWebFilterChain và ranh giới bảo vệ

Khi ứng dụng lớn có nhiều chain, một chain có thể match /api/**, chain khác match web page. Mỗi request đi qua **chain phù hợp được chọn**, không ghép authorization rules của mọi chain.

Ví dụ tư duy:

~~~text
Chain A, ưu tiên cao: securityMatcher("/api/**")
  +--> HTTP Basic hoặc Bearer
  +--> /api/admin/** hasRole ADMIN
  +--> /api/** authenticated

Chain B, ưu tiên thấp:
  +--> form login hoặc public web
  +--> anyExchange denyAll / allow theo chủ đích
~~~

Nếu RouterFunction chuyển từ /api/legacy sang /fn/legacy, nó có thể chuyển sang chain B dù code nghiệp vụ vẫn gọi cùng service. Sự đồng nhất không chỉ nằm trong pathMatchers: còn phải kiểm tra **securityMatcher**, **@Order**, authentication mechanism, CORS, CSRF, session repository và entry point của từng chain.

### 12.1. Gắn policy với chức năng, không gắn với công nghệ handler

Trong quy trình review code, thay vì hỏi “endpoint này có phải Controller không?”, hãy hỏi:

- Chức năng này là public, authenticated, admin, hay cần owner/tenant?
- HTTP path+method thực tế là gì sau @RequestMapping hoặc RouterFunction nesting?
- SecurityWebFilterChain nào bắt request?
- Rule nào khớp **đầu tiên**?
- Người chưa login, role thường và role admin sẽ nhận gì?
- Có path mới do route versioning/proxy prefix/rewrite không?
- Có phương thức ghi cần CSRF hoặc CORS preflight không?
- Cùng nghiệp vụ có entry point khác (queue/GraphQL/gRPC) cần chính sách tương đương không?

**Chỉ có một policy chính** nên trả lời được các câu hỏi trên; Controller hay RouterFunction là implementation detail của HTTP handler.

## 13. Quy trình review và kiểm thử phòng ngừa regression

Khi thêm hoặc chuyển một endpoint:

1. **Lập inventory** tất cả mapping của Controller và RouterFunction cùng method/path ở mức ứng dụng. Không suy đoán từ tên class hoặc file.
2. **Gắn loại dữ liệu** public, private, admin, tenant-bound, owner-bound.
3. **Ánh xạ policy trung tâm** theo URL/method trước khi mở handler. Với URL cụ thể, ưu tiên whitelist chính xác nếu không có lý do mở rộng.
4. **Sắp thứ tự** rule từ cụ thể đến tổng quát. Tránh để /api/** che /api/admin/**.
5. **Chọn default** anyExchange().denyAll() nếu yêu cầu fail-closed.
6. **Sử dụng cùng service** cho nghiệp vụ chung và kiểm tra owner/tenant trong service/repository.
7. **Tạo ma trận WebTestClient** cho guest, sai credential, user, admin và path không biết. Có cả Controller lẫn RouterFunction.
8. **Kiểm tra method** không chỉ path, nhất là POST/PUT/PATCH/DELETE/OPTIONS.
9. **Kiểm tra nhiều chain** nếu có securityMatcher và @Order.
10. **Soát sản xuất**: reverse proxy rewrite, context path, multi-tenant header, session/JWT behavior, observability, test trên môi trường gần thực tế.

### 13.1. Test contract song song

Có thể mở rộng bộ test bằng một bảng khai báo endpoint/role:

~~~text
endpoint group    annotated                 functional
public            /public/annotated         /public/functional
profile           /api/profile/annotated    /api/profile/functional
admin             /api/admin/annotated      /api/admin/functional
disabled          /internal/annotated       /internal/functional
~~~

Với mỗi nhóm, test cùng tập role, HTTP method và status. Điều này giúp bắt lỗi khi một developer **chỉ đổi RouterFunction** nhưng quên thay rule authorization, hoặc ngược lại.

### 13.2. Không dựa duy nhất vào static analysis

Source review và grep path string có thể bỏ qua:

- Nested routes với prefix.
- RequestMapping class-level kết hợp method-level.
- Dynamic properties/context path.
- Multiple chain matcher.
- Reverse proxy rewrite.
- Custom RequestPredicate / custom ServerWebExchangeMatcher.

Do đó, test HTTP tích hợp là bắt buộc để xác nhận chính sách được áp dụng cho **đường chạy thực tế**. Trong production có thể thêm contract tests tại gateway hoặc e2e staging, nhưng không cần thay thế unit tests kiểm tra service.

## 14. Bài tập thực hành

1. Chuyển annotated profile thành functional profile nhưng giữ nguyên path và service; làm thế nào để bảo đảm chỉ một mapping hoạt động một lúc?
2. Chuyển functional admin từ /api/admin/functional thành /functions/admin. Với policy demo, response thay đổi thế nào và vì sao?
3. Đảo rule /api/** trước /api/admin/**. Test nào phát hiện lỗ hổng? Giải thích.
4. Thay public rule chính xác bằng /public/**.permitAll(). Điều gì xảy ra nếu thêm /public/debug-tokens?
5. Bổ sung GET /api/catalog/annotated và GET /api/catalog/functional. Chúng cần rule nào nếu chỉ user đã login được xem?
6. Thêm POST /api/catalog ở cả hai kiểu handler với authority CATALOG_WRITE. Ngoài authorization phải quan tâm CSRF thế nào?
7. Viết WebTestClient test cả hai profile với reader/admin và thiếu credential; so sánh status và username.
8. Vì sao test trực tiếp handler function không kiểm chứng SecurityWebFilterChain?
9. Tại sao có @PreAuthorize ở một Controller không bảo đảm functional endpoint tương ứng cũng được bảo vệ?
10. Một RouterFunction có nested prefix /api và route con /admin/report. Security matcher cần dùng path nào?
11. Một request bị từ chối 403 nhưng route không tồn tại. Có thể kết luận owner check trong service đã chạy chưa?
12. Nếu ứng dụng dùng cả bearer token và form session qua hai chain, điều kiện gì phải soát khi chuyển URL của một endpoint?

**Đáp án gợi ý:**

- (1) Chỉ đăng ký một mapping cho method+path hoặc bật/tắt bằng cấu hình rõ ràng và test HTTP.
- (2) Không match /api/** và sẽ rơi vào anyExchange().denyAll(), thường trả 403 khi đã login; phải cập nhật URL/policy có chủ đích.
- (3) Test reader gọi /api/admin/annotated và /api/admin/functional phải nhận 403; nếu nhận 200 là sai.
- (4) Route debug ở namespace public có thể được mở trái ý định, làm lộ secret nếu không có guard khác.
- (5) /api/**.authenticated() hoặc rule chính xác tương đương.
- (6) Cấu hình authority theo HTTP method, đồng thời giữ/kiểm thử CSRF phù hợp.
- (7) Guest 401, caller hợp lệ 200 với danh tính của chính caller, không phụ thuộc loại handler.
- (8) Unit handler không đi qua WebFilter/authorization.
- (9) Annotation method/controller không tự áp dụng cho functional HandlerFunction; cần policy chung ở WebFilter hoặc shared service.
- (10) /api/admin/report, không chỉ /admin/report.
- (11) Không; security có thể deny trước khi handler/service chạy.
- (12) securityMatcher/@Order, authentication mechanism, entry point, session/CSRF/CORS và matcher URL thực tế.

## 15. Tài liệu tham khảo

- Spring Security — Authorize ServerHttpRequest (Reactive): https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — ServerHttpSecurity Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Framework — WebFlux Functional Endpoints: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Framework — WebFlux DispatcherHandler: https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html
- Spring Framework — Annotated Controllers in WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Spring Boot 3.5 System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html

**Kết luận:** Giữ đồng nhất quy tắc cho Controller và RouterFunction nghĩa là định nghĩa **một bộ luật HTTP authorization có chủ đích** trên SecurityWebFilterChain, match đúng URL/method của cả hai kiểu endpoint, xếp rule theo độ đặc hiệu, deny-by-default và gọi cùng service nghiệp vụ. Kiểm thử cặp endpoint bằng WebTestClient với guest, credential sai, user thường, admin và đường không công bố; đừng dựa vào tên class, route filter riêng hoặc unit handler tests để suy ra bảo mật đã đồng nhất.