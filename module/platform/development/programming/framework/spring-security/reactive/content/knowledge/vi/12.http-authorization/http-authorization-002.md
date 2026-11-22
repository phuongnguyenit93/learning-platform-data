# permitAll, denyAll, authenticated và quyền của người dùng ẩn danh trong Spring Security Reactive

## 1. Mục tiêu bài học

Khi xây dựng REST API bằng Spring WebFlux và Spring Security, ta phải quyết định **request nào được truy cập công khai, request nào phải có danh tính đã xác thực, và request nào luôn bị chặn**. Ba quy tắc cơ bản trong **ServerHttpSecurity.authorizeExchange(...)** là:

- **permitAll()** — cho phép mọi người truy cập nếu request khớp rule, không đòi hỏi đăng nhập.
- **denyAll()** — từ chối tất cả, bất kể đã đăng nhập hay chưa.
- **authenticated()** — yêu cầu một danh tính được Spring Security công nhận là đã xác thực, **không chấp nhận anonymous**.

Ngoài ba quy tắc này, có khái niệm dễ nhầm: **người dùng ẩn danh (anonymous)**. Trong một số cấu hình, Spring Security có thể tạo **AnonymousAuthenticationToken** và đặt nó vào Reactor Context. Mục đích là biểu diễn người chưa đăng nhập bằng một đối tượng Authentication, **không phải xác minh danh tính thực**.

Sau bài này, bạn sẽ:

1. Phân biệt **public**, **anonymous**, **authenticated** và **authorized**.
2. Viết luật WebFlux với **pathMatchers**, **anyExchange**, **permitAll**, **denyAll**, **authenticated**.
3. Hiểu **thứ tự matcher** và nguyên tắc deny-by-default.
4. Biết khi nào có anonymous Authentication, cách bật nó rõ ràng trong WebFlux và vì sao **isAuthenticated()** không đồng nghĩa "người dùng đã đăng nhập".
5. Hiểu **401** và **403** trong các trường hợp thiếu credential, sai credential và thiếu quyền.
6. Xây demo **Java 17+ / Spring Boot WebFlux** có HTTP Basic, một trang công khai, một API cần login, một API admin, một endpoint bị đóng và một endpoint chỉ dành cho anonymous.
7. Viết **WebTestClient** để xác nhận hành vi thật, không chỉ đọc cấu hình và suy đoán.

**Quy tắc cốt lõi:** cho phép đúng các URL công khai đã định nghĩa, bắt đăng nhập ở vùng riêng tư, kiểm tra quyền ở vùng đặc quyền và kết thúc bằng một chính sách **denyAll()** cho phần còn lại nếu đó là ý định của sản phẩm.

## 2. Authentication khác authorization thế nào?

Có ba câu hỏi khác nhau:

1. **Ai đang gọi?** Authentication xác định principal sau khi mật khẩu/token được kiểm tra.
2. **Có được vào endpoint không?** Authorization so sánh Authentication với policy của URL.
3. **Có được đọc/đổi tài nguyên cụ thể không?** Kiểm tra owner, tenant và quyền nghiệp vụ tại service/repository.

Ví dụ: alice có ROLE_USER đã đăng nhập. Quy tắc **authenticated()** cho phép cô ấy gọi GET /api/me. Nhưng nếu gọi GET /api/admin/report, cần **hasRole("ADMIN")**; còn đọc đơn hàng 42 phải được kiểm tra thêm chủ sở hữu.

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Unauthenticated** | Chưa có bằng chứng danh tính hợp lệ | Không gửi Authorization |
| **Anonymous** | Đại diện kỹ thuật cho caller chưa đăng nhập | AnonymousAuthenticationToken |
| **Authenticated** | Spring Security công nhận danh tính từ cơ chế xác thực tin cậy | alice đã qua HTTP Basic |
| **Authorized** | Được policy cho phép thao tác đang yêu cầu | Alice xem hồ sơ của chính mình |
| **Principal** | Đối tượng đại diện danh tính | alice hoặc guest |
| **GrantedAuthority** | Quyền cụ thể của Authentication | ROLE_USER, ROLE_ADMIN |

Nhớ rằng **Authentication tồn tại** không có nghĩa **authenticated()** sẽ đồng ý; một AnonymousAuthenticationToken cũng là Authentication. Trong Spring Security, bộ quản lý authorization dùng khái niệm trust/anonymous chứ không đơn thuần lấy giá trị boolean của token.

## 3. Ba rule quan trọng

### 3.1. permitAll(): public nhưng vẫn ở trong security chain

Ví dụ:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/public/**").permitAll()
        .anyExchange().authenticated())
~~~

Mọi request khớp /public/** được phép **vượt qua bước authorization URL này** dù không có tài khoản. Điều đó không có nghĩa:

- Bỏ qua tất cả WebFilter bảo mật.
- Tắt CSRF cho các phương thức ghi.
- Tắt authentication filters, CORS, rate limiting hoặc custom filter.
- Bỏ qua method security như @PreAuthorize nếu method được gọi có rule riêng.
- Đảm bảo controller không có lỗi nghiệp vụ.

Ví dụ **GET /public/ping không có header** trả 200 theo controller. Nhưng nếu caller tự gửi **Authorization: Basic ...** với password sai, authentication filter có thể xử lý header đó và trả 401 ngay cả khi URL được đánh dấu permitAll. **permitAll không phải “bỏ qua cơ chế xác thực”**.

Với endpoint có public data nhưng cần cá nhân hóa, có thể đọc tên nếu Authentication hợp lệ; khi không có danh tính thì trả nội dung công khai. Không tự nâng quyền khi fallback.

### 3.2. denyAll(): chặn bất kể danh tính

~~~java
.pathMatchers("/maintenance/**").denyAll()
~~~

Các request khớp rule bị từ chối dù caller chưa đăng nhập, là người thường hay admin. Đặc biệt hữu ích cho:

- API cũ đã ngừng hoạt động hoặc route không muốn công bố.
- Nhánh chưa được cấp phép để mở.
- Chính sách mặc định cho URL không liệt kê.
- Endpoint cần tạm khóa ở tầng authorization.

**denyAll không có nghĩa 404 hoặc đảm bảo “route không tồn tại”.** Status thường là 401 nếu caller chưa có danh tính được chấp nhận, hoặc 403 nếu đã đăng nhập nhưng bị từ chối, tùy entry point và error handler. Quan trọng là **không được 2xx và không trả dữ liệu nhạy cảm**.

Đặt denyAll ở nhánh URL chưa từng mở không thay thế biện pháp gỡ controller/debug endpoint, tắt feature flag, kiểm tra gateway và bảo vệ backend service bên dưới.

### 3.3. authenticated(): đã đăng nhập nhưng không mặc nhiên đủ quyền

~~~java
.pathMatchers("/api/**").authenticated()
~~~

Điều kiện là caller được Spring Security xem là **đã xác thực**, không phải anonymous. Nhưng authenticated() **không yêu cầu ROLE_USER, ROLE_ADMIN, tenant hoặc ownership cụ thể**.

- Không gửi credential → không đạt rule.
- Gửi credential sai → xác thực thất bại, không đạt rule.
- Gửi credential đúng của user thường → đạt rule.
- Gửi credential đúng của admin → đạt rule.
- AnonymousAuthenticationToken → **không đạt rule**.

Nếu API /api/orders/{id} dùng authenticated(), mọi người đã đăng nhập có thể vượt qua hàng rào URL. Service vẫn phải giới hạn bản ghi theo owner/tenant để tránh **IDOR/BOLA**.

### 3.4. Cấu hình so sánh

| Rule | Người chưa đăng nhập | Anonymous token | User đã đăng nhập | Admin đã đăng nhập |
| --- | --- | --- | --- | --- |
| **permitAll()** | Cho qua | Cho qua | Cho qua | Cho qua |
| **authenticated()** | Từ chối | Từ chối | Cho qua | Cho qua |
| **denyAll()** | Từ chối | Từ chối | Từ chối | Từ chối |
| **hasRole("ADMIN")** | Từ chối | Từ chối | Từ chối nếu không có ROLE_ADMIN | Cho qua nếu có ROLE_ADMIN |
| **Kiểm tra anonymous-only tùy chỉnh** | Có thể cho qua nếu có anonymous representation | Cho qua | Từ chối | Từ chối |

“Cho qua” nghĩa là **được phép qua bước authorization URL**, không bảo đảm response chắc chắn 200 vì controller, method security hoặc tầng khác vẫn có thể từ chối.

## 4. Anonymous trong WebFlux: những chi tiết dễ sai

### 4.1. AnonymousAuthenticationToken có phải đăng nhập thật không?

**Không.** Đây là một kiểu Authentication do framework tạo để biểu diễn người chưa đăng nhập trong ngữ cảnh bảo mật. Nếu bật anonymous support, **AnonymousAuthenticationWebFilter** sẽ phát hiện không có Authentication trong ReactiveSecurityContextHolder rồi bổ sung anonymous Authentication.

Theo Javadoc của AnonymousAuthenticationWebFilter, cấu hình mặc định khi dùng constructor nhận key tạo:

- **principal**: anonymousUser.
- **authority**: ROLE_ANONYMOUS.

Có thể tùy chỉnh principal/authorities qua **ServerHttpSecurity.anonymous(...)**.

Quan trọng: **AnonymousAuthenticationToken.isAuthenticated() có thể trả true** vì object này được tạo sẵn ở trạng thái “authenticated” theo contract của token. Điều đó chỉ nói về đối tượng trong Spring Security, **không phải bằng chứng người thật đã vượt qua login**.

~~~java
// Ví dụ minh họa test Java, không phải authentication từ request.
AnonymousAuthenticationToken guest =
        new AnonymousAuthenticationToken(
                "test-key",
                "guest",
                List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));

boolean tokenFlag = guest.isAuthenticated(); // true
~~~

Do đó, cách sau không an toàn nếu muốn kiểm tra “đã đăng nhập”:

~~~java
// Sai khi dùng độc lập để loại anonymous:
if (authentication != null && authentication.isAuthenticated()) {
    // cho truy cập mọi dữ liệu riêng tư
}
~~~

Thay vào đó, ưu tiên **.authenticated()** ở DSL, **AuthenticationTrustResolver** khi phải viết logic Java và kiểm tra quyền đối tượng tại service.

### 4.2. Anonymous không mặc định bật theo Javadoc WebFlux

Javadoc **ServerHttpSecurity.anonymous(...)** ở nhánh Spring Security 6.5 ghi anonymous authentication **disabled by default**. Vì vậy **không được giả định mọi request công khai luôn có AnonymousAuthenticationToken** trong Reactor Context.

Một endpoint **permitAll()** vẫn truy cập được khi **không có** anonymous token; tính public của URL đến từ rule permitAll, **không phụ thuộc có token anonymous hay không**.

Trong demo ta **bật anonymous rõ ràng**:

~~~java
.anonymous(anon -> anon
        .principal("guest")
        .authorities("ROLE_ANONYMOUS"))
~~~

Khi một request không có Authentication đi qua filter anonymous trong chain này, Reactor Context có thể chứa principal guest với ROLE_ANONYMOUS. Nếu đã xác thực bằng HTTP Basic, filter không nên ghi đè danh tính đã xác minh thành guest.

Không gọi **anonymous.disable()** như một phương pháp bảo vệ endpoint riêng tư. Khả năng truy cập do **authorization rules** quyết định; tắt anonymous chỉ thay đổi cách biểu diễn người chưa đăng nhập.

### 4.3. ROLE_ANONYMOUS có thể dùng để làm gì?

Anonymous authority có thể hỗ trợ mô tả một chính sách riêng, ví dụ trang hướng dẫn người dùng chưa đăng nhập. Tuy vậy:

- **ROLE_ANONYMOUS không phải dấu chứng minh tài khoản tồn tại**.
- Đừng dùng nó để cho xem dữ liệu riêng tư.
- Chỉ kiểm tra chuỗi authority ROLE_ANONYMOUS không đảm bảo người này thực sự là anonymous nếu có custom Authentication được cấp nhầm quyền đó.
- Khi thật sự cần “chỉ người chưa đăng nhập”, dùng **AuthenticationTrustResolver.isAnonymous(...)** hoặc một ReactiveAuthorizationManager phù hợp.

Trong ứng dụng nhiều vai trò, đôi khi chỉ cần permitAll rồi render lời chào “guest”/“alice” theo Authentication đã có. Không cần tạo endpoint anonymous-only nếu không có yêu cầu sản phẩm.

### 4.4. Ẩn danh không phải cùng nghĩa với chưa đăng nhập

Các trường hợp:

| Trạng thái | Có SecurityContext? | Có Authentication? | Đạt authenticated()? |
| --- | --- | --- | --- |
| Không context | Không | Không | Không |
| Context có Authentication null | Có | Không | Không |
| Anonymous support bật và không có login | Có (do filter tạo) | AnonymousAuthenticationToken | **Không** |
| User được xác thực qua HTTP Basic | Có | Authentication tin cậy | **Có** |

Một handler dùng Mono<Principal> có thể có hành vi khác với việc đọc thẳng ReactiveSecurityContextHolder, tùy resolver/chain. Nếu muốn kiểm tra anonymous object, đọc **Reactor Context** trong publisher được framework subscribe; không mặc định mọi controller argument Principal sẽ luôn nhận guest.

## 5. Thứ tự authorizeExchange: rule cụ thể trước rule rộng

Ví dụ tốt:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/public/**").permitAll()
        .pathMatchers("/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().denyAll())
~~~

**Các matcher được xét theo thứ tự đã cấu hình: rule khớp đầu tiên quyết định manager authorization cho request.**

Nếu đảo:

~~~java
// SAI nếu muốn khóa riêng /api/admin/**:
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

Thì /api/admin/report có thể khớp /api/** trước, khiến rule hasRole("ADMIN") phía sau không còn được dùng. Một người chỉ cần đã đăng nhập có thể đi vào endpoint admin.

**Checklist thứ tự:**

1. Rule của path public **cụ thể và có chủ đích**.
2. Rule deny đặc biệt nếu có.
3. Rule admin/role/scope trên path nhạy cảm.
4. Rule authenticated cho nhánh rộng.
5. **anyExchange().denyAll()** cuối cùng theo mặc định fail-closed.

Mặc định **anyExchange().authenticated()** cũng là một lựa chọn khi mọi path còn lại đều dự kiến cần login; nhưng nếu muốn endpoint mới không tự mở cho mọi user đăng nhập, **denyAll** an toàn hơn.

Cũng cần nhớ **securityMatcher** chọn **SecurityWebFilterChain** trước khi các pathMatchers bên trong chain được xét. Trong ứng dụng nhiều chain, Spring Security chọn chain phù hợp theo thứ tự: **permitAll trong một chain không cho request đi qua các chain khác để cộng dồn rule**.

## 6. Phân biệt 401 và 403

**401 Unauthorized** là trường hợp không có bằng chứng xác thực hợp lệ hoặc credential bị từ chối; với HTTP Basic, response thường mang **WWW-Authenticate: Basic realm="..."**.

**403 Forbidden** thường chỉ ra caller đã xác thực nhưng policy không cấp quyền. Dù user có ROLE_ADMIN, denyAll vẫn cấm và có thể trả 403.

| Request với HTTP Basic | Policy | Kết quả thường thấy |
| --- | --- | --- |
| GET /public/ping không header | permitAll | 200 |
| GET /api/profile không header | authenticated | 401 |
| GET /api/profile sai password | authenticated | 401 |
| GET /api/profile user hợp lệ | authenticated | 200 |
| GET /api/admin/dashboard user chỉ ROLE_USER | hasRole ADMIN | 403 |
| GET /api/admin/dashboard admin | hasRole ADMIN | 200 |
| GET /maintenance/flag user đã xác thực | denyAll | 403 |
| GET /maintenance/flag chưa xác thực | denyAll | Thường 401 với Basic entry point |
| GET /guest-only chưa login, anonymous đã bật | Chính sách chỉ anonymous | 200 |
| GET /guest-only user đã login | Chính sách chỉ anonymous | 403 |

Các mã cụ thể còn tùy **ServerAuthenticationEntryPoint**, **ServerAccessDeniedHandler**, các chain và authentication mechanisms. Về bảo mật, trường hợp denyAll không được phát dữ liệu được bảo vệ, bất kể JSON status được tùy chỉnh thế nào.

Không nên dùng **permitAll** để né lỗi credential, không nên dùng **denyAll** để “giấu” sự tồn tại tài nguyên một cách tuyệt đối, và không nên cho một anonymous token đi qua **authenticated()** chỉ vì token.isAuthenticated() là true.

## 7. Demo Java 17+ chạy được: WebFlux + HTTP Basic + anonymous tùy chỉnh

Demo sử dụng **Spring Boot 3.5.16**, Java 17+, Gradle 8.4+ (ví dụ Gradle 8.14) và Spring Security reactive do Spring Boot quản lý.

**Chú ý vòng đời phiên bản:** Spring Boot 3.5.16 là bản cuối của dòng 3.5 được phát hành OSS; khi xây mới production nên chọn một nhánh còn nhận bản vá OSS hoặc hỗ trợ thương mại, và không tự ghim library cũ. Ở đây phiên bản được pin để ví dụ có dependency xác định.

Các đường dẫn:

| Path | Ý định bảo mật |
| --- | --- |
| GET /public/ping | Công khai |
| GET /public/whoami | Công khai và cho biết tên đại diện context một cách an toàn |
| GET /api/profile | Phải đăng nhập |
| GET /api/admin/dashboard | Phải có ROLE_ADMIN |
| GET /maintenance/flag | Không ai được vào |
| GET /guest-only | Chỉ anonymous, minh họa custom ReactiveAuthorizationManager |
| Các đường khác | denyAll |

Tài khoản demo:

- alice / alice-pass có **ROLE_USER**.
- admin / admin-pass có **ROLE_USER**, **ROLE_ADMIN**.

### 7.1. Cấu trúc file

~~~text
webflux-authorization-basics/
├── settings.gradle
├── build.gradle
├── src/main/java/example/access/AccessApplication.java
├── src/main/java/example/access/SecurityConfig.java
├── src/main/java/example/access/AccessController.java
└── src/test/java/example/access/AccessPolicyTest.java
~~~

### 7.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-authorization-basics'
~~~

### 7.3. build.gradle

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

Chỉ dùng starter WebFlux, **không** thêm spring-boot-starter-web cùng lúc; mục tiêu là quan sát chính xác SecurityWebFilterChain của reactive stack.

### 7.4. AccessApplication.java

~~~java
package example.access;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccessApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccessApplication.class, args);
    }
}
~~~

### 7.5. SecurityConfig.java

~~~java
package example.access;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        AuthenticationTrustResolver trustResolver =
                new AuthenticationTrustResolverImpl();

        return http
                // Bật anonymous rõ ràng thay vì dựa vào giả định mặc định.
                .anonymous(anonymous -> anonymous
                        .principal("guest")
                        .authorities("ROLE_ANONYMOUS"))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping", "/public/whoami")
                            .permitAll()
                        .pathMatchers("/maintenance/**").denyAll()
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        // WebFlux DSL không có method anonymous() ngay
                        // trên Access như permitAll/authenticated.
                        .pathMatchers("/guest-only").access(
                                (authentication, context) ->
                                        authentication
                                                .map(trustResolver::isAnonymous)
                                                .map(AuthorizationDecision::new)
                                                .defaultIfEmpty(
                                                        new AuthorizationDecision(
                                                                false)))
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }
}
~~~

**Giải thích:**

1. **anonymous(...)** tạo representation guest / ROLE_ANONYMOUS khi chưa có Authentication. Nếu authentication đã thành công thì guest không thay thế alice/admin.
2. **permitAll()** mở hai đường công khai; không tắt Spring Security.
3. **denyAll()** chặn đường maintenance ngay cả admin.
4. **hasRole("ADMIN")** chạy trước **authenticated()** trên /api/**; vì thế ROLE_USER không thể truy cập admin endpoint.
5. **authenticated()** chặn anonymous và người không có credential hợp lệ.
6. **guest-only.access(...)** dùng ReactiveAuthorizationManager; AuthenticationTrustResolver biết cách phân biệt anonymous token. **Mono.empty() được coi là deny** bằng defaultIfEmpty(false) để fail closed.
7. **anyExchange().denyAll()** không vô tình mở các URL mới.
8. **httpBasic** kiểm tra credential theo HTTP Basic; demo không dùng form/session login để tránh các ảnh hưởng redirect.

**Các import không bắt buộc:** AnonymousAuthenticationToken và Mono xuất hiện trong phần minh họa khái niệm khác của bài nhưng không cần trong SecurityConfig.java; trong Java, unused import chỉ là cảnh báo style chứ không gây lỗi biên dịch. Có thể xóa hai import này nếu IDE yêu cầu code sạch.

**Tại sao không chỉ dùng hasAuthority("ROLE_ANONYMOUS")?** Vì authority là một chuỗi được cấp vào Authentication. Nếu ứng dụng cấu hình sai và cấp cả ROLE_ANONYMOUS cho user đã xác thực, kiểm tra authority có thể bị lẫn. TrustResolver xét đúng **tư cách anonymous của Authentication**, phù hợp hơn với chính sách "chỉ người chưa đăng nhập". Trong hệ thống không yêu cầu guest-only, **permitAll** là lựa chọn đơn giản và rõ ràng hơn.

### 7.6. AccessController.java

~~~java
package example.access;

import java.security.Principal;
import java.util.Map;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class AccessController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/public/whoami")
    public Mono<Map<String, String>> whoami() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(context ->
                        Mono.justOrEmpty(context.getAuthentication()))
                .map(auth -> Map.of(
                        "name", auth.getName(),
                        "kind", auth instanceof AnonymousAuthenticationToken
                                ? "ANONYMOUS" : "AUTHENTICATED"))
                .defaultIfEmpty(Map.of(
                        "name", "none",
                        "kind", "MISSING"));
    }

    @GetMapping("/api/profile")
    public Mono<Map<String, String>> profile(Mono<Principal> principal) {
        return principal.map(p -> Map.of("username", p.getName()));
    }

    @GetMapping("/api/admin/dashboard")
    public Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("dashboard", "admin"));
    }

    @GetMapping("/maintenance/flag")
    public Mono<Map<String, String>> disabled() {
        return Mono.just(Map.of("flag", "hidden"));
    }

    @GetMapping("/guest-only")
    public Mono<Map<String, String>> guestOnly() {
        return Mono.just(Map.of("mode", "guest"));
    }
}
~~~

Dù controller có phương thức disabled(), rule denyAll ngăn handler của /maintenance/flag trả dữ liệu cho request đã match chain. **Không** coi việc controller tồn tại là bằng chứng API đã mở.

Endpoint /public/whoami cố tình trả tên và loại danh tính **đơn giản**, không xuất toàn bộ Authentication hoặc principal. Trong ứng dụng thật, không trả password hash, token hoặc nội dung SecurityContext tùy ý ra client.

### 7.7. Khởi động

Cần Java 17+, Gradle tương thích và kết nối Maven Central:

~~~bash
gradle bootRun
~~~

Nếu không đổi port, ứng dụng lắng nghe trên **http://localhost:8080**. Dùng HTTP localhost để học; ở production phải dùng HTTPS, quản lý mật khẩu thật và chính sách identity store phù hợp.

## 8. Dùng curl quan sát các luật

Chạy trong một terminal Bash khác với terminal đang chạy Gradle:

~~~bash
# Public không cần header.
curl -s http://localhost:8080/public/ping
# {"status":"ok"}

# Anonymous được bật và đại diện bằng guest.
curl -s http://localhost:8080/public/whoami
# {"name":"guest","kind":"ANONYMOUS"}
# (thứ tự key JSON không phải hợp đồng)

# Public nhưng request có Basic credentials hợp lệ thì nhìn thấy user thật.
curl -s -u alice:alice-pass http://localhost:8080/public/whoami
# {"name":"alice","kind":"AUTHENTICATED"}

# API cần đăng nhập, request không có credential.
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/profile
# 401

# Mật khẩu sai.
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:wrong-pass http://localhost:8080/api/profile
# 401

# Người dùng thường hợp lệ.
curl -s -u alice:alice-pass http://localhost:8080/api/profile
# {"username":"alice"}

# User chỉ ROLE_USER không vào admin.
curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:alice-pass http://localhost:8080/api/admin/dashboard
# 403

# Admin đủ quyền.
curl -s -u admin:admin-pass http://localhost:8080/api/admin/dashboard
# {"dashboard":"admin"}

# Ngay cả admin cũng bị denyAll.
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin-pass http://localhost:8080/maintenance/flag
# 403

# Guest-only chỉ cho anonymous.
curl -s http://localhost:8080/guest-only
# {"mode":"guest"}

curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:alice-pass http://localhost:8080/guest-only
# 403
~~~

**Giải thích:** các dòng sau # là đầu ra dự kiến, không phải lệnh. Đối với JSON Map, thứ tự key trên wire không phải hợp đồng: client nên so sánh giá trị JSON thay vì so sánh nguyên chuỗi nếu có nhiều trường.

Trên PowerShell dùng **curl.exe** và viết mỗi lệnh trên một dòng, vì ký hiệu tiếp dòng Bash **\\** không sử dụng như PowerShell.

Một tình huống có chủ đích chưa thể hiện ở trên: request đến /public/ping mang Authorization Basic **không hợp lệ** có thể bị authentication filter trả 401 dù URL là permitAll. Điều đó không làm thay đổi ý nghĩa của permitAll; nó cho thấy authentication và authorization là hai bước khác nhau trong cùng security chain. Hãy tạo test riêng nếu ứng dụng cần chính sách xử lý credential lỗi trên URL public.

## 9. Kiểm thử bằng WebTestClient

Trọng tâm của bài là **kiểm tra chính sách thật qua HTTP**, không chỉ xác minh method SecurityWebFilterChain biên dịch. Test chạy cùng ứng dụng, không cần mở server riêng trên 8080.

Tệp **src/test/java/example/access/AccessPolicyTest.java**:

~~~java
package example.access;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AccessPolicyTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointWorksWithoutCredentials() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void anonymousRepresentationIsNotARealLogin() {
        client.get().uri("/public/whoami")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("guest")
                .jsonPath("$.kind").isEqualTo("ANONYMOUS");

        AnonymousAuthenticationToken token =
                new AnonymousAuthenticationToken(
                        "unit-test-key",
                        "guest",
                        List.of(new SimpleGrantedAuthority(
                                "ROLE_ANONYMOUS")));
        assertTrue(token.isAuthenticated());
    }

    @Test
    void authenticatedRejectsAnonymousAndInvalidPassword() {
        client.get().uri("/api/profile")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/profile")
                .headers(h -> h.setBasicAuth("alice", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void aValidUserCanOpenAuthenticatedRoute() {
        client.get().uri("/api/profile")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username").isEqualTo("alice");
    }

    @Test
    void roleBasedAdminPolicyRunsBeforeBroadAuthenticatedRule() {
        client.get().uri("/api/admin/dashboard")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden();

        client.get().uri("/api/admin/dashboard")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.dashboard").isEqualTo("admin");
    }

    @Test
    void denyAllBlocksEvenAnAdmin() {
        client.get().uri("/maintenance/flag")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void guestOnlyDeniesLoggedInUser() {
        client.get().uri("/guest-only")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.mode").isEqualTo("guest");

        client.get().uri("/guest-only")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void unknownPathIsNotOpenedByDefault() {
        client.get().uri("/unlisted")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**Kết quả kỳ vọng:** tám test PASS và Gradle báo BUILD SUCCESSFUL khi ứng dụng và dependencies tương thích. Các test dùng Spring context thực, kiểm tra chuỗi WebFilter và authorization, nhưng chưa phải bằng chứng về chính sách proxy/gateway/ingress ngoài ứng dụng.

**Vì sao test anonymous token có thể isAuthenticated=true nhưng /api/profile vẫn 401?** Vì authorization rule authenticated() được Spring Security xây trên sự phân biệt trạng thái tin cậy, không coi AnonymousAuthenticationToken như một người đăng nhập hợp lệ.

**Vì sao không test denyAll bằng “bất kỳ status 4xx”?** Với Basic và handler mặc định của demo, user đã xác thực bị từ chối cần 403. Mục tiêu test là bắt regression: denyAll không được vô tình trở thành permitAll.

## 10. Khi nhiều SecurityWebFilterChain cùng tồn tại

Trong một ứng dụng WebFlux có thể có hai chain:

~~~text
SecurityWebFilterChain 1 (priority cao) -> securityMatcher("/api/**")
    -> authorizeExchange rules của API
    -> HTTP Basic / JWT tương ứng

SecurityWebFilterChain 2 (priority thấp) -> matcher cho phần còn lại
    -> form login hoặc policy web
~~~

**Một request dùng chain được chọn theo matcher/order, không chạy lần lượt mọi chain để cộng dồn các rule.** Vì vậy:

- Một **permitAll** trong chain của API không nói gì về URL chỉ thuộc chain trang web.
- Một **anyExchange().denyAll()** áp dụng cho request **đã vào chain chứa rule**, không phải mọi request trên tất cả chain.
- Thứ tự **@Order** ở nhiều bean SecurityWebFilterChain là một trục khác với thứ tự pathMatchers trong một chain.
- Kiểm thử phải biết request khớp chain nào. Một chain public đặt quá rộng có thể làm mất toàn bộ policy của chain API định nghĩa ở sau.

Nếu không có yêu cầu nhiều cơ chế authentication, nên bắt đầu bằng **một chain rõ ràng**. Tránh thêm complexity cho đến khi có ranh giới xác thực/URL có ý nghĩa.

## 11. Các lỗi phổ biến và cách khắc phục

| Sai lầm | Hậu quả | Giải pháp |
| --- | --- | --- |
| Đặt /api/**.authenticated trước /api/admin/**.hasRole | User thường có thể qua rule admin | Rule cụ thể trước rule rộng |
| Cho mọi URL **permitAll** vì cần debug | Bỏ qua authorization URL | Chỉ public path có chủ đích, deny phần còn lại |
| Cho mọi URL **authenticated** rồi nghĩ tài nguyên cá nhân đã an toàn | Bất kỳ user nào cũng có thể thử đọc tài nguyên người khác | Kiểm tra owner/tenant ở service/repository |
| Nghĩ denyAll tự trả HTTP 404 | Lẫn yêu cầu từ chối với status/obfuscation | Test status, bảo đảm không trả dữ liệu |
| Nghĩ anonymous mặc định chắc chắn luôn tồn tại | Reactive Context có thể rỗng | Bật rõ qua .anonymous(...) nếu cần |
| Dùng isAuthenticated() để xem token anonymous như login thật | Anonymous token có thể true | DSL authenticated()/AuthenticationTrustResolver |
| Dùng hasAuthority("ROLE_ANONYMOUS") làm kiểm tra duy nhất cho guest-only | Có nguy cơ custom user cũng được cấp chuỗi quyền đó | Kiểm tra loại/trust resolver |
| Nghĩ permitAll bỏ security filters | Credential sai vẫn có thể bị filter từ chối | Tách authentication với authorization |
| Tắt CSRF hoặc CORS tùy tiện khi mở public endpoint | Nguy cơ khi browser gửi cookie tự động | Cấu hình theo kiểu credential, origin, HTTP method |
| Ghi PasswordEncoder NOOP cho dễ chạy | Mật khẩu lưu rõ và rủi ro leak | BCrypt/thuật toán phù hợp |
| Trả nguyên Authentication vào JSON | Lộ principal/credentials/metadata | Map sang DTO cho field công khai |
| Tạo method security rồi nghĩ permitAll bỏ qua | Method có thể vẫn deny | Test đầy đủ URL và service |
| Dùng SecurityContextHolder ThreadLocal kiểu servlet trong WebFlux | Context sai khi đổi thread | ReactiveSecurityContextHolder |
| Thiếu anyExchange fallback | Route chưa được quyết định rõ | denyAll hoặc explicit authenticated theo sản phẩm |
| Thử chỉ bằng trình duyệt đang có session | Nhầm người đã login với guest | Dùng cookie jar/HTTP client tách biệt |
| Không test request sai Basic credential trên URL public | Có thể bất ngờ nhận 401 | Thêm test theo auth-filter policy |

## 12. Cách thiết kế quyền của anonymous đúng nhu cầu

Đa số ứng dụng chỉ cần:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers("/catalog", "/help").permitAll()
        .pathMatchers("/account/**").authenticated()
        .anyExchange().denyAll())
~~~

Khi đó:
- **Guest** xem được danh mục/hướng dẫn.
- **User đã login** cũng xem được nội dung public và có thể vào trang tài khoản.
- **AnonymousAuthenticationToken** không phải điều kiện cần để permitAll hoạt động.

Nếu muốn “chỉ guest được vào trang giới thiệu đăng ký”, cân nhắc UX: không nhất thiết trả 403 cho người đã login. Thông thường redirect hoặc trả thông tin trạng thái khác sẽ thân thiện hơn. Chỉ dùng guest-only manager như demo khi chính sách thực sự đòi từ chối mọi user đã đăng nhập.

Nếu anonymous cần gọi API để xem dữ liệu mẫu, hãy cấp quyền truy cập **dữ liệu mẫu công khai** qua permitAll hoặc policy read-only có giới hạn; không dùng cùng repository query của dữ liệu riêng tư rồi giả lập một account đặc quyền chung.

Một yêu cầu ví dụ khác: shopping cart guest. Cookie cart guest nên là session/token tách biệt với authenticated account và có kiểm tra sở hữu phù hợp khi hợp nhất giỏ hàng. **ROLE_ANONYMOUS không phải mật khẩu** và không thể thay cơ chế phân biệt giỏ hàng của từng khách.

## 13. Bài tập và câu hỏi tự đánh giá

1. Khác biệt căn bản giữa permitAll(), denyAll() và authenticated() là gì?
2. Vì sao /api/admin/**.hasRole("ADMIN") phải đặt trước /api/**.authenticated()?
3. Một request public mang Basic credential sai có chắc sẽ trả 200 không? Tại sao?
4. Vì sao AnonymousAuthenticationToken.isAuthenticated() có thể true mà authenticated() vẫn từ chối?
5. Theo Javadoc ServerHttpSecurity 6.5, có nên giả định anonymous mặc định bật không?
6. Tại sao ROLE_ANONYMOUS không phải bằng chứng người gọi sở hữu tài khoản?
7. Nếu user alice đã đăng nhập mà gọi /maintenance/flag, denyAll cho phép không?
8. Khi denyAll từ chối một request anonymous, HTTP status có nhất thiết là 403 không?
9. Nếu app có nhiều SecurityWebFilterChain, anyExchange().denyAll() của chain A có chặn được URL chỉ thuộc chain B không?
10. Một user đã qua authenticated() có thể đọc đơn hàng của user khác không?
11. Với URL chỉ cần xem nội dung chung, nên dùng permitAll hay tạo anonymous-only policy?
12. Nên kiểm thử như thế nào để phát hiện endpoint mới vô tình được mở?

**Gợi ý đáp án:**

1. Permit public, deny mọi request, authenticated yêu cầu danh tính tin cậy.
2. Rule khớp đầu tiên được dùng; đặt rule rộng trước làm mờ rule cụ thể.
3. Không chắc; authentication filter vẫn có thể xử lý credential sai và trả 401.
4. Anonymous token là đại diện kỹ thuật; trust resolver phân biệt anonymous với login thật.
5. Không; khi cần representation anonymous, bật rõ qua anonymous(...).
6. ROLE_ANONYMOUS chỉ là authority đại diện guest, không phải chứng cứ về principal đã xác minh.
7. Không; denyAll từ chối cả admin.
8. Không; entry point có thể trả 401 cho caller chưa đăng nhập.
9. Không; request chỉ vào chain được chọn theo matcher/order.
10. Không mặc nhiên; phải kiểm tra quyền trên owner/tenant/record.
11. Thường dùng permitAll cho public content.
12. Có test unknown path bằng user đã login và bằng client chưa login, bảo đảm không xuất dữ liệu nhạy cảm.

## 14. Tài liệu đối chiếu

- Spring Security Javadoc 6.5 — ServerHttpSecurity: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security Javadoc — AuthorizeExchangeSpec.Access: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.AuthorizeExchangeSpec.Access.html
- Spring Security Javadoc — ServerHttpSecurity.AnonymousSpec: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.AnonymousSpec.html
- Spring Security Javadoc — AnonymousAuthenticationWebFilter: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AnonymousAuthenticationWebFilter.html
- Spring Security Javadoc — AuthenticationTrustResolver: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationTrustResolver.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Boot 3.5 System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html

**Kết luận:** **permitAll** mở quyền truy cập công khai ở tầng URL; **denyAll** chặn mọi request phù hợp; **authenticated** yêu cầu Authentication được Spring Security công nhận là đăng nhập thật, không chấp nhận anonymous. Người dùng ẩn danh có thể được đại diện bởi AnonymousAuthenticationToken nhưng không phải danh tính đã xác minh. Hãy bật anonymous có chủ đích khi cần, sắp xếp matcher từ cụ thể đến tổng quát, dùng **anyExchange().denyAll()** làm điểm kết thúc khi phù hợp và kiểm tra owner/tenant ở tầng nghiệp vụ.