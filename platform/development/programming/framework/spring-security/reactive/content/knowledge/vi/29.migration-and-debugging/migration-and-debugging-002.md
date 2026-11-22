# Chuyển từ UserDetailsService và AuthenticationManager sang hợp đồng reactive

## Bối cảnh, mục tiêu và giới hạn

Trong ứng dụng Spring MVC (Servlet), bạn thường dùng `UserDetailsService` và `AuthenticationManager` để xác thực tên đăng nhập/mật khẩu. Khi chuyển sang **Spring WebFlux / Spring Security Reactive**, cặp API tương ứng là `ReactiveUserDetailsService` và `ReactiveAuthenticationManager`. Đây là thay đổi cả **hợp đồng trả về, cách phát tín hiệu lỗi, thời điểm thực thi và ngữ cảnh bảo mật**, không chỉ thêm `Mono` vào tên phương thức.

Bài này thuộc **Spring Security – reactive / Chuyển đổi và gỡ lỗi**. Sau khi học, bạn có thể:

1. Đối chiếu hợp đồng Servlet và Reactive, biết trách nhiệm của user lookup so với password validation.
2. Di chuyển username/password authentication sang `ReactiveUserDetailsService` và `UserDetailsRepositoryReactiveAuthenticationManager` mà không thay đổi ý nghĩa mật khẩu, quyền và trạng thái tài khoản.
3. Chọn giữa **di chuyển thuần reactive** và **bắc cầu tạm thời** tới `UserDetailsService`/`AuthenticationManager` đồng bộ bằng `boundedElastic`.
4. Gắn manager vào `SecurityWebFilterChain`, lấy authentication từ Reactor Context, kiểm thử bằng `StepVerifier` và kiểm tra hành vi HTTP bằng `WebTestClient` hoặc curl.
5. Phân biệt lỗi không tìm thấy user, sai mật khẩu, token không được manager hỗ trợ, lỗi storage, blocking và việc cấu hình nhầm Servlet/WebFlux.

Ví dụ định hướng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Reactor**, sử dụng username/password. OAuth2 Resource Server, JWT và OIDC có các manager/filter chuyên dụng, không tự động chuyển thành repository username/password chỉ vì ứng dụng dùng WebFlux.

## 1. Bản đồ hai hợp đồng bảo mật

| Trách nhiệm | Servlet / đồng bộ | WebFlux / reactive | Ý nghĩa khi chuyển |
| --- | --- | --- | --- |
| Tìm user | `UserDetailsService.loadUserByUsername(String)` trả `UserDetails` hoặc ném `UsernameNotFoundException` | `ReactiveUserDetailsService.findByUsername(String)` trả `Mono<UserDetails>` | Không trả `null`; phát user khi tìm thấy, thường `Mono.empty()` khi không có |
| Xác thực credentials | `AuthenticationManager.authenticate(Authentication)` trả `Authentication` hoặc ném `AuthenticationException` | `ReactiveAuthenticationManager.authenticate(Authentication)` trả `Mono<Authentication>` | Success = phát token đã xác thực; failure = `onError`; không thể quyết định = `Mono.empty()` |
| Username/password chuẩn | `DaoAuthenticationProvider` + `ProviderManager` | `UserDetailsRepositoryReactiveAuthenticationManager` + `ReactiveUserDetailsService` | Tái dùng `PasswordEncoder` và `UserDetails`, thay provider/manager phù hợp |
| Lưu auth khi xử lý | `SecurityContextHolder` thường gắn với ThreadLocal | `ReactiveSecurityContextHolder` gắn với Reactor Context | Không dựa vào ThreadLocal Servlet bên trong chuỗi reactive |
| Cấu hình HTTP | `HttpSecurity`, `SecurityFilterChain` | `ServerHttpSecurity`, `SecurityWebFilterChain` | WebFlux dùng chuỗi `WebFilter`, không dùng `Filter` Servlet |
| User store in-memory | `InMemoryUserDetailsManager` | `MapReactiveUserDetailsService` | Tiện cho demo/test; dữ liệu thật thường đi qua repository adapter |
| Verify pipeline | Kỳ vọng giá trị/exception đồng bộ | `StepVerifier` subscribe và xác minh `onNext/onError/onComplete` | Lỗi reactive không nhất thiết ném ngay khi gọi method |

**Phân biệt lookup và authenticate:** `ReactiveUserDetailsService` chỉ tìm thông tin user và authorities. Nó **không thay** password checks, account status checks, hay việc tạo token xác thực. `UserDetailsRepositoryReactiveAuthenticationManager` là thành phần tiêu chuẩn kiểm username/password dựa trên một `ReactiveUserDetailsService` và `PasswordEncoder`. Nếu logic cũ có MFA, kiểm tra tenant, mật khẩu hết hạn hoặc provider chain riêng, bạn phải chuyển cả các quy tắc đó một cách có chủ đích.

### 1.1. Ba kết quả của `ReactiveAuthenticationManager`

Hợp đồng `Mono<Authentication> authenticate(Authentication request)` phân biệt:

- **`onNext(authenticatedAuthentication)` rồi `onComplete`:** credentials hợp lệ; kết quả có `isAuthenticated() == true`, principal/authorities phù hợp.
- **`onError(AuthenticationException)`:** manager nhận diện yêu cầu xác thực nhưng xác thực thất bại, chẳng hạn sai mật khẩu hoặc tài khoản bị khóa. Không đổi sang `Mono.empty()` vì điều đó làm mất nghĩa “credentials không hợp lệ”.
- **`onComplete` mà không phát giá trị (`Mono.empty()`):** manager **không thể quyết định** xác thực yêu cầu đó, ví dụ một manager chỉ hỗ trợ loại token khác. Với nhiều manager được ghép lại, cơ chế điều phối mới quyết định manager kế tiếp. Không dùng `Mono.empty()` để “cho đăng nhập thất bại một cách im lặng”.

Lưu ý: `ReactiveUserDetailsService` có hợp đồng riêng. User không tồn tại thường thể hiện bằng `Mono.empty()`; manager tiêu chuẩn sẽ biến điều đó thành thất bại xác thực. Không viết mã tự cho phép truy cập khi lookup hoàn thành rỗng.

## 2. Vì sao thay kiểu trả về là chưa đủ?

Ví dụ đồng bộ cũ:

~~~java
UserDetails user = legacyUserDetailsService.loadUserByUsername(username);
return user;
~~~

Một bản “migrate” sai thường trông như sau:

~~~java
@Override
public Mono<UserDetails> findByUsername(String username) {
    // SAI: JDBC/LDAP đồng bộ đã chạy TRƯỚC khi Mono được tạo.
    return Mono.just(
        legacyUserDetailsService.loadUserByUsername(username));
}
~~~

`Mono.just(...)` đánh giá tham số **ngay lập tức**. Nếu `loadUserByUsername` truy cập JDBC/JPA, LDAP hoặc HTTP client đồng bộ, lời gọi có thể chặn luồng Reactor Netty đang xử lý request. Đổi sang `Mono.justOrEmpty(...)` cũng không sửa vấn đề.

Đoạn tiếp theo có **lazy execution** nhưng vẫn chưa hoàn chỉnh:

~~~java
return Mono.fromCallable(
    () -> legacyUserDetailsService.loadUserByUsername(username));
~~~

Nó dời lời gọi đến khi subscribe, nhưng nếu subscriber chạy trên event loop, thao tác blocking vẫn chạy **trên event loop**. Khi chưa thể bỏ API cũ, cần **cả** `Mono.fromCallable` và `subscribeOn(Schedulers.boundedElastic())`. Khi đã có R2DBC/reactive driver hoặc reactive HTTP client, ưu tiên API non-blocking thật thay vì dùng boundedElastic lâu dài.

Một sai lầm khác là gọi `Mono.block()` trong custom `ReactiveAuthenticationManager` để “lấy user cho dễ”:

~~~java
// SAI trong event loop; đồng thời phá lợi ích của pipeline.
UserDetails user = reactiveUsers.findByUsername(username).block();
~~~

Trong WebFlux, hãy **ghép publisher bằng `flatMap`/`map`**. Một số lời gọi `block()` trên thread non-blocking bị Reactor ném `IllegalStateException` ngay. Điều này khác lỗi bad credentials.

## 3. Hướng A — triển khai thuần ReactiveUserDetailsService

Giả sử database có bảng tài khoản với username, password hash, enabled, authorities. Khi repository đã dùng R2DBC hoặc một client reactive thực sự, tạo adapter user lookup như sau. Đây là **đoạn minh họa tích hợp repository**, không phải chương trình độc lập vì `AccountRepository`/`Account` là mô hình dự án:

~~~java
public interface AccountRepository {
    Mono<Account> findByUsername(String username);
}

public record Account(
    String username,
    String passwordHash,
    boolean enabled,
    String role
) {}

public final class DatabaseReactiveUsers
        implements ReactiveUserDetailsService {

    private final AccountRepository accounts;

    public DatabaseReactiveUsers(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        return accounts.findByUsername(username)
            .map(account -> User.withUsername(account.username())
                .password(account.passwordHash()) // hash đã lưu!
                .disabled(!account.enabled())
                .roles(account.role())             // ví dụ: "USER"
                .build());
    }
}
~~~

Các import cần thiết: `reactor.core.publisher.Mono`; `org.springframework.security.core.userdetails.User`, `UserDetails` và `ReactiveUserDetailsService`. Một ứng dụng thực tế phải map **toàn bộ** trạng thái còn áp dụng (locked, account expired, credentials expired) cùng authorities; đừng bỏ kiểm tra tài khoản khóa chỉ vì demo có mỗi `enabled`. Nếu role trong dữ liệu đã là authority `ROLE_USER` hoặc danh sách quyền dạng `document:write`, hãy map chính xác bằng `authorities(...)` và tránh vô tình thêm trùng tiền tố `ROLE_` từ `roles(...)`.

Với repository reactive, `findByUsername` trả về `Mono.empty()` nếu không thấy username. Nếu database hỏng, để lỗi đi theo `onError` và phân loại là **lỗi hạ tầng**, không dùng `onErrorResume(error -> Mono.empty())` một cách tổng quát: thao tác đó sẽ biến lỗi database thành “không có tài khoản” và che giấu sự cố.

**Điều cần giữ nguyên khi migrate:** dữ liệu password được đọc từ cột **hash**, không phải plaintext; thuật toán hash và prefix như `{bcrypt}` phải tương thích `PasswordEncoder`. Không encode lại hash mỗi lần đọc. Việc đổi thuật toán hoặc hash password phải nằm trong một migration dữ liệu có kiểm soát, không làm âm thầm bên trong `findByUsername`.

## 4. Hướng B — cấu hình username/password WebFlux chạy được

Phần này dùng user in-memory để tập trung vào hợp đồng và dây nối các bean. File **`src/main/java/demo/migration/ReactiveMigrationApplication.java`** sau là một ứng dụng Spring Boot WebFlux đầy đủ với endpoint công khai và endpoint yêu cầu đăng nhập:

~~~java
package demo.migration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class ReactiveMigrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveMigrationApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService reactiveUsers(PasswordEncoder encoder) {
        // Chỉ là credential DEMO; không hard-code production secret.
        UserDetails user = User.withUsername("alice")
            .password(encoder.encode("changeit"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(user);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager manager) {

        return http
            .authenticationManager(manager)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated())
            .httpBasic(withDefaults())
            .build();
    }
}

@RestController
class ExampleRoutes {

    @GetMapping("/public/ping")
    Mono<String> publicPing() {
        return Mono.just("pong");
    }

    @GetMapping("/private/me")
    Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
    }
}
~~~

Cấu hình dependencies cần có trong dự án Spring Boot Gradle (sử dụng BOM/plugin Boot hiện hữu để quản lý phiên bản):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy ứng dụng:

~~~bash
./gradlew bootRun
~~~

Kiểm tra bằng curl (thay `localhost:8080` nếu ứng dụng dùng cổng khác):

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/private/me
curl -i -u alice:changeit http://localhost:8080/private/me
curl -i -u alice:wrong http://localhost:8080/private/me
~~~

Kết quả HTTP mong đợi cho cấu hình demo này:

| Request | Kết quả dự kiến | Vì sao |
| --- | --- | --- |
| `GET /public/ping`, không credentials | **200**, body `pong` | URL được `permitAll()` |
| `GET /private/me`, không credentials | **401** | `anyExchange().authenticated()` và HTTP Basic challenge |
| `GET /private/me`, `alice:changeit` | **200**, body `alice` | Manager kiểm hash và phát authentication hợp lệ |
| `GET /private/me`, `alice:wrong` | **401** | Sai mật khẩu, authentication thất bại |

Header, thứ tự log và thông báo Gradle phụ thuộc phiên bản/cấu hình; bảng chỉ mô tả ý nghĩa cần kiểm. Password demo được tạo hash bằng `PasswordEncoder` khi ứng dụng khởi động và so khớp bởi manager. Không dùng `User.withDefaultPasswordEncoder()` hoặc `{noop}` cho dữ liệu thật.

**Ai làm gì trong ví dụ?**

1. `ReactiveUserDetailsService` cung cấp thông tin `UserDetails` của `alice`.
2. `UserDetailsRepositoryReactiveAuthenticationManager` lấy user rồi kiểm credentials/status và trả `Mono<Authentication>`.
3. `ServerHttpSecurity.authenticationManager(manager)` kết nối manager với phần xác thực WebFlux.
4. `httpBasic(...)` cung cấp cơ chế trích xuất header Basic và xử lý challenge/error trong security WebFilter chain.
5. `ReactiveSecurityContextHolder.getContext()` lấy authentication từ **Reactor Context** trong request; không đọc `SecurityContextHolder.getContext()` rồi cho rằng ThreadLocal sẽ luôn đúng khi đổi scheduler.

**Không trộn hai ngăn xếp:** một `SecurityFilterChain(HttpSecurity)` của Servlet không thay thế `SecurityWebFilterChain(ServerHttpSecurity)`. Nếu dự án chứa cả starter web MVC và webflux, Spring Boot có thể chọn loại ứng dụng Servlet; hãy kiểm tra web application type thật và dependencies trước khi kết luận cấu hình WebFlux đã có hiệu lực.

## 5. Hướng C — bắc cầu tạm thời khi chỉ có UserDetailsService đồng bộ

Nếu đang phụ thuộc repository JDBC/JPA/LDAP đồng bộ và chưa thể di chuyển ngay, có thể bọc `UserDetailsService` cũ bằng `ReactiveUserDetailsService`. Tạo file **`src/main/java/demo/migration/LegacyUserDetailsBridge.java`** (đây là class hoàn chỉnh; backend cũ do ứng dụng cung cấp):

~~~java
package demo.migration;

import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class LegacyUserDetailsBridge
        implements ReactiveUserDetailsService {

    private final UserDetailsService legacy;

    public LegacyUserDetailsBridge(UserDetailsService legacy) {
        this.legacy = legacy;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        return Mono.fromCallable(
                () -> legacy.loadUserByUsername(username))
            .subscribeOn(Schedulers.boundedElastic())
            .onErrorResume(
                UsernameNotFoundException.class,
                error -> Mono.empty());
    }
}
~~~

Cách đưa vào Spring context khi **đã có** bean `UserDetailsService` và muốn dùng `UserDetailsRepositoryReactiveAuthenticationManager`:

~~~java
@Bean
ReactiveUserDetailsService reactiveUsers(UserDetailsService legacy) {
    return new LegacyUserDetailsBridge(legacy);
}
~~~

Snippets `@Bean` trên là **phần tích hợp trong class `@Configuration`**, không phải file độc lập. Khi đưa chúng vào ứng dụng, thay bean `reactiveUsers(...)` in-memory của phần 4 bằng bean adapter này để tránh có **nhiều bean cùng kiểu gây ambiguity**; giữ các phần config còn lại nếu dùng username/password.

**Tại sao bridge hợp lệ về mặt luồng?**

- `Mono.fromCallable` trì hoãn truy vấn đến subscription.
- `subscribeOn(Schedulers.boundedElastic())` đưa nguồn đồng bộ sang scheduler thích hợp cho blocking; không chặn event-loop đang phục vụ request.
- `UsernameNotFoundException` riêng được đổi sang publisher rỗng, phù hợp với nghĩa “không có user” ở lookup reactive. **Lỗi kết nối DB, timeout, lỗi mapping** không bị bắt chung; chúng vẫn là `onError` để quản lý như lỗi dịch vụ.
- `UserDetails` vẫn giữ nguyên password hash, authorities, trạng thái account từ hệ thống cũ; manager reactive vẫn đảm nhiệm xác thực.

**Giới hạn quan trọng:** bridge không làm JDBC/JPA/LDAP trở thành non-blocking. Bounded elastic có số worker/hàng đợi hữu hạn; phải kiểm connection pool, timeout driver, concurrency và p95/p99 trong tải thực tế. `Mono.timeout(...)` không bảo đảm ngắt được truy vấn JDBC đồng bộ đã bắt đầu. Nếu backend cũ có lazy JPA associations, cũng phải xét phạm vi transaction và session khi chuyển worker thread.

Không dùng kiểu sau:

~~~java
// SAI: fromCallable đã lazy nhưng vẫn có thể chạy ngay trên event loop.
return Mono.fromCallable(() -> legacy.loadUserByUsername(username));

// SAI: công việc chạy trước khi subscribeOn có tác dụng.
return Mono.just(legacy.loadUserByUsername(username))
    .subscribeOn(Schedulers.boundedElastic());
~~~

## 6. Hướng D — bắc cầu AuthenticationManager cũ nguyên khối

Khi hệ thống cũ có **`AuthenticationManager` tùy biến** với chuỗi `AuthenticationProvider`, LDAP bind hoặc quy tắc riêng khó tách ra ngay, Spring Security có sẵn **`ReactiveAuthenticationManagerAdapter`**. Ví dụ tích hợp (giả định có bean `AuthenticationManager` cũ):

~~~java
@Bean
ReactiveAuthenticationManager reactiveManager(
        AuthenticationManager legacyManager) {

    ReactiveAuthenticationManagerAdapter adapter =
        new ReactiveAuthenticationManagerAdapter(legacyManager);
    adapter.setScheduler(Schedulers.boundedElastic());
    return adapter;
}
~~~

Các import tương ứng: `org.springframework.security.authentication.AuthenticationManager`, `ReactiveAuthenticationManager`, `ReactiveAuthenticationManagerAdapter`, `reactor.core.scheduler.Schedulers` và `org.springframework.context.annotation.Bean`.

Adapter chuyển lời gọi manager đồng bộ sang giao diện reactive; thiết lập scheduler phù hợp khi implementation cũ **có thể blocking**. Nó giúp duy trì các provider đang vận hành trong giai đoạn chuyển đổi, nhưng có chi phí thread và tiếp tục phụ thuộc kiến trúc cũ. Ưu tiên chuyển từng provider/lookup sang reactive khi có API non-blocking thực sự.

**Chọn một đường thực thi cho mỗi cơ chế xác thực:**

- Nếu chỉ còn `UserDetailsService` đồng bộ, dùng **bridge lookup** ở mục 5 và `UserDetailsRepositoryReactiveAuthenticationManager` để xác minh password bằng manager reactive.
- Nếu cần bảo toàn **toàn bộ `AuthenticationManager` đồng bộ**, dùng `ReactiveAuthenticationManagerAdapter` ở mục 6; không song song dựng thêm manager mới cho cùng credential flow mà không có thiết kế dispatch rõ ràng.
- Nếu đã có user store reactive, dùng thẳng manager ở mục 4. Đây là đích di chuyển thông thường.

Không biến adapter thành một “cơ chế đăng nhập mới”: **không được chấp nhận token không phù hợp**, bỏ qua password checks, vô hiệu hóa account status, hoặc nuốt mọi exception. Những quy tắc cũ như rate limiting, khóa tài khoản, audit, tenant scope hay MFA cần được kiểm thử khi chạy dưới WebFlux.

## 7. Dùng trực tiếp ReactiveAuthenticationManager khi có token/custom flow

Bạn có thể tự triển khai `ReactiveAuthenticationManager` để xử lý một loại credential riêng, nhưng phải bảo toàn ba trạng thái **success / cannot determine / failure**. Mẫu khái niệm:

~~~java
@Override
public Mono<Authentication> authenticate(Authentication request) {
    if (!(request instanceof MyApiKeyAuthenticationToken token)) {
        return Mono.empty(); // Manager này không hỗ trợ loại token.
    }

    return apiKeys.findByKey(token.getKey()) // API truy vấn reactive.
        .switchIfEmpty(Mono.error(
            new BadCredentialsException("Invalid credentials")))
        .map(account -> new UsernamePasswordAuthenticationToken(
            account.principal(), null, account.authorities()));
}
~~~

`MyApiKeyAuthenticationToken` và `apiKeys` là **kiểu và dependency giả định** của ứng dụng, nên đoạn này là **mã minh họa cấu trúc**, không thể biên dịch độc lập. Việc xác thực API key thực tế còn cần so khớp secret an toàn, thời hạn, thu hồi, giới hạn quyền, và chọn đúng `ServerAuthenticationConverter` để tạo token từ request. Không sử dụng password manager chuẩn để kiểm Bearer JWT; Spring Security Resource Server đã có authentication/filter tương ứng cho JWT và opaque token.

Ở nhánh custom, nếu không tìm thấy token đã được manager nhận diện, dùng `Mono.error(BadCredentialsException)`. `Mono.empty()` có nghĩa “tôi không quyết định được”, không có nghĩa “từ chối”. Trả `Authentication` đã được đánh dấu authenticated và authorities đã xác minh, không sao chép `isAuthenticated=true` từ một request chưa qua kiểm chứng. Thực thi I/O bằng client reactive hoặc chuyển legacy call sang bounded elastic.

## 8. Kiểm thử hợp đồng reactive bằng JUnit và StepVerifier

Đặt file **`src/test/java/demo/migration/ReactiveAuthenticationContractTest.java`**. Đây là một **test class đầy đủ**, không cần chạy HTTP server hoặc database; phụ thuộc `spring-security-test` và `reactor-test` đã khai báo ở phần 4:

~~~java
package demo.migration;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveAuthenticationContractTest {

    private final PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

    private final ReactiveUserDetailsService users =
        new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password(encoder.encode("changeit"))
                .roles("USER")
                .build()
        );

    private final ReactiveAuthenticationManager manager =
        createManager();

    private ReactiveAuthenticationManager createManager() {
        UserDetailsRepositoryReactiveAuthenticationManager result =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        result.setPasswordEncoder(encoder);
        return result;
    }

    private Authentication request(String user, String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
            user, password);
    }

    @Test
    void findsExistingUser() {
        StepVerifier.create(users.findByUsername("alice"))
            .assertNext(found -> {
                assertEquals("alice", found.getUsername());
                assertTrue(encoder.matches(
                    "changeit", found.getPassword()));
            })
            .verifyComplete();
    }

    @Test
    void unknownUserLookupIsEmpty() {
        StepVerifier.create(users.findByUsername("unknown"))
            .verifyComplete();
    }

    @Test
    void acceptsCorrectCredentialsAndExposesAuthorities() {
        StepVerifier.create(
                manager.authenticate(request("alice", "changeit")))
            .assertNext(auth -> {
                assertTrue(auth.isAuthenticated());
                assertEquals("alice", auth.getName());
                assertTrue(auth.getAuthorities().stream()
                    .anyMatch(a -> a.getAuthority()
                        .equals("ROLE_USER")));
            })
            .verifyComplete();
    }

    @Test
    void wrongPasswordFailsAsAuthenticationError() {
        StepVerifier.create(
                manager.authenticate(request("alice", "wrong")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void unknownUserCannotAuthenticate() {
        StepVerifier.create(
                manager.authenticate(request("unknown", "anything")))
            .expectError(AuthenticationException.class)
            .verify();
    }
}
~~~

Chạy một test class từ gốc project có Gradle wrapper:

~~~bash
./gradlew test --tests demo.migration.ReactiveAuthenticationContractTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests demo.migration.ReactiveAuthenticationContractTest
~~~

**Kỳ vọng:** năm test PASS trong môi trường có dependencies tương thích. Không dựa vào thông báo stdout Gradle cụ thể. `StepVerifier` thực sự subscribe và kiểm tín hiệu; chỉ gọi `manager.authenticate(...)` rồi `assertNotNull(...)` không đủ. Đoạn trên cũng tách rõ **user lookup không tồn tại = empty** khỏi **authentication không tồn tại = error**. Loại lỗi chính xác của một manager có thể khác theo implementation/cấu hình, nên test missing user kiểm tổng quát `AuthenticationException`; test sai mật khẩu kiểm `BadCredentialsException`.

### 8.1. Thêm test với legacy adapter

Với bridge ở mục 5, cần một dependency giả lập để xác minh cách chuyển exception và scheduler. Ví dụ dưới là **phần thêm vào test class thích hợp**, không phải class chạy độc lập:

~~~java
UserDetailsService legacy = username -> {
    if (!"alice".equals(username)) {
        throw new UsernameNotFoundException(username);
    }
    return User.withUsername("alice")
        .password("{noop}demo-only")
        .roles("USER")
        .build();
};

LegacyUserDetailsBridge bridge = new LegacyUserDetailsBridge(legacy);

StepVerifier.create(bridge.findByUsername("alice"))
    .assertNext(user -> assertEquals("alice", user.getUsername()))
    .verifyComplete();

StepVerifier.create(bridge.findByUsername("missing"))
    .verifyComplete();
~~~

Các import bổ sung: `org.springframework.security.core.userdetails.UserDetailsService` và `UsernameNotFoundException`. Hash `{noop}` ở fixture này chỉ để minh họa một đối tượng `UserDetails`, **không sử dụng cho password thật**. Nếu cần kiểm xác thực đầu cuối, nên dùng `PasswordEncoder` như ví dụ test đầy đủ, và kiểm cả đúng/sai password.

### 8.2. Kiểm tra HTTP sau khi manager đã PASS

Test method trực tiếp không tự khẳng định security filter chain đã được gắn đúng. Hãy chạy ứng dụng ở phần 4 rồi dùng curl hoặc `WebTestClient` với Spring context thực để xác nhận:

- `/public/ping` không cần auth.
- `/private/me` thiếu credentials bị từ chối.
- `/private/me` với credentials đúng được phép và đọc chính xác username từ Reactor Context.
- Sai password hoặc account bị disable/locked không tạo được authentication hợp lệ.
- Khi dùng bridge, request đi qua repository/manager thực sự; đừng mock thay toàn bộ manager trong test nhằm phát hiện blocking.

Phân biệt **lỗi method-level** (`AuthenticationException` trong tín hiệu Reactor) với **mã HTTP** (ví dụ 401 đối với Basic không hợp lệ). WebFlux security filter mới chuyển lỗi thành HTTP response theo authentication entry point và exception handling; test trực tiếp manager không nên khẳng định một mã HTTP.

## 9. Security context trong quá trình chuyển thread

Trong Servlet, nhiều code cũ gọi:

~~~java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();
~~~

`SecurityContextHolder` mặc định dựa trên ThreadLocal. Trong WebFlux, request và callback có thể chạy trên nhiều scheduler; không chuyển logic này nguyên xi sang custom reactive authentication/authorization service để tìm principal.

Trong pipeline reactive, truy cập bằng:

~~~java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
~~~

Cần import `org.springframework.security.core.context.ReactiveSecurityContextHolder`, `reactor.core.publisher.Mono`. Đoạn trên là **method minh họa** trong bean hoặc controller, không phải file Java độc lập. Khi HTTP filter chain xác thực thành công, nó đưa context vào chuỗi reactive phù hợp.

Khi chuyển sang `Schedulers.boundedElastic()` bằng các Reactor operators, Reactor Context được truyền theo subscription; tuy nhiên tự gọi `subscribe()` trong service hoặc tự tạo `new Thread(...)` có thể làm tách lifecycle và security context. Đừng lưu token/mật khẩu vào static hoặc ThreadLocal như một cách “khắc phục” mất context. Nếu cần context trong adapter đồng bộ, truyền **giá trị cụ thể đã được xác thực** làm tham số hoặc chuyển thành context-aware reactive flow, không giả định `SecurityContextHolder` của Servlet đang phản ánh user đúng.

## 10. Checklist migration an toàn theo từng bước

**Bước 1 — Liệt kê hợp đồng thật đang dùng.** Xác định source `UserDetailsService`, `AuthenticationManager`, các `AuthenticationProvider`, PasswordEncoder, account-state checks, tenant/multi-factor rules và cơ chế HTTP (form, basic, bearer...). Chỉ thay đổi những thành phần thực sự tham gia request flow đang chuyển.

**Bước 2 — Xác nhận runtime WebFlux.** Kiểm dependency, ứng dụng có chạy reactive web application type không, các endpoint dùng Reactor Netty/WebFlux, và security dùng `SecurityWebFilterChain`/`ServerHttpSecurity`. Không đổi bean Servlet xong rồi cho rằng reactive chain tự thấy bean đó.

**Bước 3 — Chọn đường dữ liệu.** Với driver hỗ trợ reactive, dùng `ReactiveUserDetailsService` backed by reactive repository; nếu chưa có, dùng bridge `fromCallable + boundedElastic` cho lookup, hoặc `ReactiveAuthenticationManagerAdapter` cho manager legacy nguyên khối. Ghi rõ kế hoạch loại bỏ bridge và giới hạn concurrency.

**Bước 4 — Bảo toàn semantics bảo mật.** Giữ nguyên algorithm/password-hash compatibility, authorities, disabled/locked/expired checks, error policy, audit và tenant scoping. Không đưa credential plaintext ra log và không cấp role mặc định khi lookup thất bại.

**Bước 5 — Cấu hình một đường xác thực rõ ràng.** Tạo manager tương ứng, inject nó vào `ServerHttpSecurity.authenticationManager(...)`, cấu hình `httpBasic`/`formLogin`/custom filter đúng nhu cầu. Tránh hai `ReactiveUserDetailsService` beans cạnh tranh nếu không có qualifier/dispatch thiết kế rõ.

**Bước 6 — Test contract trước, HTTP sau.** Với `StepVerifier` kiểm user found/missing, đúng/sai password, account disabled, lỗi storage. Với `WebTestClient` hoặc curl kiểm public/private, thành công/thất bại, HTTP response, Reactor Context. Khi kiểm blocking, dùng công cụ như BlockHound và load test phù hợp.

**Bước 7 — Theo dõi khi rollout.** So sánh tỷ lệ authentication success/failure, nguyên nhân 401, p95/p99 login, CPU cho password hash, boundedElastic queue/threads, connection pool, timeout/exception và saturation dưới tải. Đặt alert hữu ích; không log password/token.

## 11. Các lỗi gỡ rối thường gặp

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách xử lý |
| --- | --- | --- |
| Đã có `ReactiveUserDetailsService` nhưng login vẫn không chạy | Không gắn manager phù hợp vào WebFlux chain, hoặc ứng dụng chạy Servlet | Kiểm loại ứng dụng, `SecurityWebFilterChain`, `ServerHttpSecurity` và manager thật được inject |
| `Mono.just(legacy.load...)` gây request chậm/blocking | Lời gọi đồng bộ chạy trước khi tạo publisher | Dùng `fromCallable(...).subscribeOn(boundedElastic)` hoặc thay backend bằng reactive driver |
| Sai mật khẩu nhưng manager trả `Mono.empty()` | Custom manager nhầm “failed” với “unsupported” | `Mono.error(BadCredentialsException)` cho credentials đã được nhận diện nhưng không hợp lệ |
| User không tìm thấy làm lộ lỗi hệ thống hoặc thông báo không thống nhất | Đang trộn contract `UsernameNotFoundException` của legacy với publisher rỗng | Chỉ đổi lỗi **not found** thành empty ở user lookup; để manager phát authentication failure, giữ chính sách chống username enumeration |
| `PasswordEncoder` báo format không hợp lệ | Password hash cũ thiếu prefix hoặc encoder thay đổi | Xác minh dữ liệu hash và encoder tương thích; migrate hash có kế hoạch, không dùng `NoOp` cho production |
| `ROLE_USER` không khớp `hasRole('USER')` | Lưu role/authority sai tiền tố hoặc mapping trùng `ROLE_` | Dùng `roles("USER")` cho role thô, hoặc `authorities("ROLE_USER")` cho authority đã có tiền tố |
| Login đúng nhưng principal mất sau `publishOn/flatMap` | Dựa vào ThreadLocal hoặc subscribe thủ công tách context | Dùng Reactor Context và `ReactiveSecurityContextHolder`; giữ chuỗi publisher nối tiếp |
| Auth fail thành 500 thay vì 401 | Lỗi storage bị bắt/chuyển sai kiểu, hoặc exception translation không qua security filter | Kiểm stack trace, phân loại `AuthenticationException`, test HTTP handler/filter |
| Có dữ liệu user nhưng account disabled vẫn vào được | Bỏ account-state flags khi map UserDetails hoặc tự manager không kiểm status | Map đầy đủ trạng thái và test disabled/locked/expired |
| Bounded elastic đầy, p99 cao | Quá nhiều blocking backend calls hoặc driver timeout lâu | Bounded concurrency/connection pool, driver timeouts, chuyển dần sang driver non-blocking |
| Test pass nhưng production dùng logic khác | Test mock nhầm manager/service hoặc bean ambiguity | Integration test bean thật, xác minh wiring và cả denied/success cases |
| Nhiều kiểu token (Basic/JWT/API key) | Một manager xử lý sai token hoặc thứ tự dispatch | Chọn filter/manager theo authentication mechanism; dùng reactive manager resolver/delegation nếu thực sự cần |

### Những bẫy tinh vi

- **Không tạo `Mono<Mono<UserDetails>>`** bằng `map` cho một thao tác đã trả publisher; dùng `flatMap` để trải phẳng chuỗi.
- **Không ghi `onErrorResume(error -> Mono.empty())`** ở authentication pipeline: nó có thể giấu DB outage hoặc biến bad credentials thành trường hợp “không quyết định được”.
- **Không gọi `subscribe()` trong `authenticate`** rồi trả một publisher khác; điều này tách request khỏi luồng xác thực, làm hỏng error propagation, cancellation và context.
- **Không gắn toàn bộ password hashing vào event loop.** `UserDetailsRepositoryReactiveAuthenticationManager` có scheduler nội bộ phù hợp cho việc so hash CPU intensive; với adapter tự viết, phải xét chi phí CPU và blocking thật thay vì đoán tất cả bằng scheduler mặc định.
- **Không chuyển nguyên `DaoAuthenticationProvider` sang bean reactive chỉ bằng tên.** Nó là provider đồng bộ của Servlet; lựa chọn native reactive là `UserDetailsRepositoryReactiveAuthenticationManager` hoặc bridge manager cũ có chủ đích.
- **Không dùng `@EnableReactiveMethodSecurity` thay cho `@EnableWebFluxSecurity`.** Method security và web authentication là hai tầng khác nhau; chỉ bật method security không tự cung cấp HTTP Basic login filter.
- **Không coi `Mono.empty()` từ lookup là “anonymous authenticated”.** User không tồn tại không cấp quyền; hệ thống phải bảo toàn nguyên tắc mặc định từ chối khi chưa xác thực.
- **Không kỳ vọng bản test manager đơn vị bảo đảm HTTP 401/403.** Phản hồi HTTP là trách nhiệm của WebFlux security filters, cần test ở tầng đó.

## 12. Tự đánh giá

Hãy trả lời các câu sau bằng cách tham chiếu ví dụ và chỉnh test cho từng tình huống:

1. Trong `UserDetailsService` cũ, user không tồn tại ném lỗi; với `ReactiveUserDetailsService` mới, tín hiệu kết quả nên như thế nào? Vì sao manager lại cần chuyển kết quả đó thành authentication failure?
2. Khi nào `ReactiveAuthenticationManager.authenticate` được phép phát `Mono.empty()`, và khi nào phải phát `Mono.error(BadCredentialsException)`?
3. Vì sao `Mono.just(legacyStore.find(username))` và `Mono.fromCallable(... )` không có scheduler đều có thể gây blocking trên event loop?
4. Nếu database chưa có reactive driver, bạn chọn `LegacyUserDetailsBridge` hay `ReactiveAuthenticationManagerAdapter` trong tình huống nào? Có những rủi ro hiệu năng gì?
5. Khi password đúng nhưng role không đúng, đây là lỗi **authentication** hay **authorization**? Test khác nhau như thế nào?
6. Vì sao một bean `AuthenticationManager` Servlet không thể mặc nhiên được dùng bởi `SecurityWebFilterChain`?
7. Nếu chuyển request qua bounded elastic, nguồn dữ liệu authentication hiện tại nên được đọc từ đâu trong reactive pipeline?
8. Bạn sẽ kiểm tra các trạng thái account locked/disabled và lỗi kết nối DB thế nào để tránh biến lỗi hệ thống thành “user không tồn tại”?

Bài hoàn tất khi có **test contract reactive** xác minh thành công và thất bại, **test WebFlux** xác minh protected route/HTTP, và **bằng chứng không blocking event loop** cho đường truy cập tài khoản. Nếu dùng bridge tạm, cần ghi nhận rõ phụ thuộc blocking còn tồn tại và kế hoạch chuyển đổi.

## Tài liệu chính thức

- Spring Security WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- `ReactiveUserDetailsService` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html
- `ReactiveAuthenticationManager` API và ba trạng thái kết quả: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html
- `UserDetailsRepositoryReactiveAuthenticationManager` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
- `ReactiveAuthenticationManagerAdapter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManagerAdapter.html
- Reactor Reference – wrap blocking call: https://projectreactor.io/docs/core/release/reference/faq.html
- Spring Security Reactive testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/index.html
