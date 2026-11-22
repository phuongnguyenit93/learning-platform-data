# Giới hạn của việc chuyển mã đồng bộ sang reactive bằng adapter

> **Ngữ cảnh:** Spring Security cho ứng dụng Spring WebFlux, Java 17+, Reactor. Bài học tập trung vào việc dùng adapter để tái sử dụng thành phần **xác thực đồng bộ** (như `AuthenticationManager`, JDBC/LDAP client, thư viện xác minh thông tin đăng nhập cũ) trong chuỗi xử lý reactive. Mục tiêu là hiểu giới hạn kỹ thuật và bảo mật của cách chuyển tiếp này trước khi chọn giải pháp.

## 1. Đích học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một phương thức trả về `Mono<Authentication>` chưa chắc thực hiện công việc không chặn luồng (*non-blocking*).
- Chọn điểm đặt adapter và scheduler cho một thành phần xác thực cũ; nhận biết chỗ nào vẫn tiêu tốn thread và kết nối.
- Phân biệt `SecurityContextHolder` dựa trên thread với `ReactiveSecurityContextHolder` dựa trên Reactor Context.
- Đánh giá đúng ảnh hưởng đến tải, timeout, hủy, transaction, lỗi xác thực và luồng bảo mật WebFlux.
- Viết kiểm thử chứng minh tác vụ được trì hoãn đến subscription và hệ thống vẫn trả kết quả xác thực/ủy quyền đúng.

## 2. Vì sao cần adapter?

Một hệ thống servlet cũ có thể xác thực theo dạng:

~~~java
Authentication result = authenticationManager.authenticate(authentication);
~~~

Lời gọi này trả kết quả hoặc ném ngoại lệ theo kiểu đồng bộ. Bên trong nó có thể truy vấn JDBC, gọi LDAP/HTTP đồng bộ, kiểm tra mật khẩu bằng thuật toán tốn CPU, đọc cache hoặc dùng `ThreadLocal`. Trong WebFlux, tuyến xác thực thường tiêu thụ `Mono<Authentication>` qua `ReactiveAuthenticationManager` và xử lý bằng WebFilter.

Adapter tạo **cầu nối kiểu giao diện** giữa hai mô hình:

~~~text
WebFlux request
  -> SecurityWebFilterChain / AuthenticationWebFilter
  -> ReactiveAuthenticationManager.authenticate(...) : Mono<Authentication>
  -> [adapter + scheduler]
  -> AuthenticationManager.authenticate(...) : Authentication
  -> tín hiệu onNext/onComplete hoặc onError
~~~

`ReactiveAuthenticationManagerAdapter` của Spring Security nhận một `AuthenticationManager` có sẵn. Adapter cho phép chuỗi reactive sử dụng phần xử lý xác thực legacy; nó **không chuyển JDBC đồng bộ thành R2DBC, không biến LDAP/HTTP blocking thành non-blocking, cũng không tự biến toàn bộ hệ thống servlet thành WebFlux**.

**Ba khái niệm khác nhau:**

| Khái niệm | Thực chất | Điều không được suy diễn |
| --- | --- | --- |
| API reactive | Trả về publisher, ví dụ `Mono<Authentication>`; bắt đầu xử lý khi được subscribe | Đồng nghĩa với việc mọi thao tác I/O không chặn |
| Offload blocking | Chạy công việc đồng bộ trên thread phù hợp thay vì event loop | Công việc phía dưới sẽ nhanh hơn hoặc có thể hủy tức thì |
| Reactive end-to-end | Các tầng truy cập I/O hỗ trợ bất đồng bộ/non-blocking, có quản lý nhu cầu và tín hiệu hủy | Có thể đạt chỉ bằng đổi kiểu trả về ở controller hoặc service |

## 3. Giới hạn số 1: giữ được event loop không có nghĩa là hết blocking

WebFlux thường dùng số lượng event-loop thread nhỏ để phục vụ nhiều kết nối. Nếu gọi JDBC, LDAP hoặc `Thread.sleep` ngay trên event loop, một request giữ thread trong lúc chờ, làm tăng độ trễ cho các request không liên quan.

**Sai: công việc đã chạy trước khi `Mono` được tạo.**

~~~java
Mono<Authentication> authenticate(Authentication input) {
    return Mono.just(legacyManager.authenticate(input));
}
~~~

Biểu thức `legacyManager.authenticate(input)` được Java đánh giá ngay khi gọi phương thức; đó là lời gọi đồng bộ, dù kết quả nằm trong `Mono.just`. Nếu nó chạy trên event loop thì event loop vẫn bị chặn. Ngoại lệ cũng có thể phát sinh trước khi publisher được trả về.

**Đúng về mặt cô lập blocking, nhưng vẫn là blocking bên dưới:**

~~~java
Mono<Authentication> authenticate(Authentication input) {
    return Mono.fromCallable(() -> legacyManager.authenticate(input))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

`fromCallable` trì hoãn thao tác đến subscription, còn `subscribeOn` sắp xếp thực thi nguồn đồng bộ lên scheduler được chọn. Đây là **mẫu minh họa cho mã tự viết**; khi dùng `ReactiveAuthenticationManagerAdapter`, nên dùng khả năng cấu hình scheduler của chính adapter thay vì quấn thêm nhiều tầng scheduler không cần thiết.

`Schedulers.boundedElastic()` phù hợp cho nhiều tác vụ chờ I/O blocking ngắn/trung bình, vì có giới hạn worker thread và hàng đợi. Nó không loại bỏ thời gian chờ, chi phí bộ nhớ cho thread, connection-pool contention hoặc nguy cơ hàng đợi bị quá tải. `publishOn` đặt ở cuối chuỗi không thể sửa một lời gọi đã thực hiện lúc tạo `Mono.just`; vị trí tạo nguồn, thời điểm gọi và scheduler phải được xem cùng nhau.

## 4. Giới hạn số 2: thông lượng và tài nguyên vẫn phụ thuộc legacy

Ví dụ một lần tra cứu tài khoản blocking mất trung bình 200 ms. Với 200 lượt xác thực/giây, theo định luật Little, số công việc đồng thời trung bình cần thiết xấp xỉ:

~~~text
concurrency = throughput × latency
            = 200 requests/s × 0,2 s
            = 40 blocking operations
~~~

Đây là phép tính minh họa, không phải cam kết benchmark. Nếu LDAP pool chỉ có 10 kết nối, JDBC pool có 15 kết nối, hoặc scheduler bị nghẽn, thêm `Mono` không xóa được nút thắt. Độ trễ thường tăng mạnh khi hàng đợi chạm ngưỡng tải.

Những điểm cần theo dõi gồm: số authentication đồng thời; thời gian xác thực p50/p95/p99; độ sâu hàng đợi và thời gian chờ scheduler; mức sử dụng DB/LDAP connection pool; số timeout; tỷ lệ 401/403/5xx; CPU dành cho kiểm tra mật khẩu; và event-loop stall. Tăng vô hạn số thread để “chữa” blocking có thể làm cạn RAM, tăng context switch và làm hại backend.

**Phân biệt I/O với CPU:** BCrypt/Argon2 được thiết kế tốn tài nguyên, nên việc xác minh mật khẩu không được phép chiếm event loop. Tuy nhiên, nó chủ yếu tốn CPU; đưa mọi tác vụ hash lên một pool quá lớn cũng không làm CPU xử lý nhanh hơn. Hãy đo tải và giới hạn concurrency theo loại công việc. `boundedElastic` là ranh giới hữu dụng cho I/O blocking, không phải một cấu hình tối ưu phổ quát cho mọi phép tính.

## 5. Giới hạn số 3: timeout và cancellation không điều khiển được mọi lệnh blocking

Publisher có thể bị hủy khi client ngắt kết nối, hết thời gian chờ hoặc operator downstream dừng nhận dữ liệu. Nhưng một thao tác JDBC/LDAP/HTTP đồng bộ đang kẹt trong lời gọi thư viện **có thể vẫn tiếp tục chiếm thread và kết nối**, dù subscription đã bị hủy.

~~~text
Client hủy request
  -> Reactor gửi cancel
  -> pipeline không còn cần kết quả
  -> legacy I/O có thể vẫn chờ socket/driver timeout
~~~

Tương tự, `.timeout(Duration.ofSeconds(2))` báo lỗi timeout ở mức Reactor; nó không tự cấu hình socket timeout, query timeout hay đảm bảo cắt được mọi blocking call. Một số thư viện hỗ trợ interrupt hoặc hủy request, một số không; phải kiểm tra khả năng thực tế của driver.

Quy tắc triển khai:

1. Đặt timeout **tại client/driver và từng phụ thuộc** (connect, read, query) phù hợp ngân sách thời gian của request.
2. Giới hạn số tác vụ xác thực đồng thời và hàng đợi; xác định cách từ chối tải khi bão hòa.
3. Không retry vô hạn khi credentials sai hoặc LDAP/DB đang lỗi. Retry xác thực tự động còn có thể làm quá tải dịch vụ hoặc ảnh hưởng chính sách khóa tài khoản.
4. Đảm bảo giải phóng kết nối/tài nguyên trong code đồng bộ, kể cả khi có lỗi; quan sát số tác vụ còn chạy sau khi client đã hủy.
5. Giữ nguyên cơ chế rate limit, lockout, audit và chống brute-force vốn có; adapter không tự thêm các cơ chế này.

## 6. Giới hạn số 4: SecurityContext và ThreadLocal không tương đương

Trong ứng dụng servlet, `SecurityContextHolder` mặc định gắn `SecurityContext` vào thread (thường bằng `ThreadLocal`) trong phạm vi xử lý request. Trong WebFlux, công việc có thể đổi thread và lịch thực thi; Spring Security dùng `ReactiveSecurityContextHolder` để đọc/ghi `SecurityContext` qua **Reactor Context đi cùng subscription**.

~~~java
Mono<String> currentUserName() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
}
~~~

Đoạn trên là phương thức dùng trong một ứng dụng WebFlux đã cấu hình security; nó không phải chương trình Java độc lập. Trong filter chain thông thường, Spring Security thiết lập Reactor Context cho authentication đã xác định.

Không nên làm các việc sau trong code reactive:

- Dùng `SecurityContextHolder.getContext().getAuthentication()` rồi coi kết quả là danh tính chắc chắn của request hiện tại: giá trị có thể trống hoặc thuộc ngữ cảnh khác.
- Đưa trực tiếp `SecurityContext` sang một `ThreadLocal` dùng chung mà không kiểm soát phạm vi và dọn dẹp; nguy cơ lẫn danh tính giữa request khi thread được tái sử dụng.
- Giả định `subscribeOn`/`publishOn` tự chuyển mọi MDC, locale, transaction hoặc custom ThreadLocal sang worker thread. Reactor Context và ThreadLocal là hai cơ chế khác nhau; cầu nối ngữ cảnh nếu có phải được cấu hình và kiểm thử rõ ràng.

Nếu `AuthenticationManager` cũ dựa vào việc tự lấy user/request bằng ThreadLocal, hãy **ưu tiên truyền dữ liệu cần thiết qua `Authentication` hoặc tham số tường minh**, đồng thời kiểm tra lại các provider, interceptor và audit hook. Cần đặc biệt thận trọng khi legacy code tự đọc HTTP request/session của servlet: WebFlux không cung cấp mặc nhiên các đối tượng servlet đó.

## 7. Giới hạn số 5: không thể tái sử dụng nguyên security filter chain của servlet

Hai hệ điều phối bảo mật khác nhau:

| Servlet/Spring MVC | Reactive/WebFlux |
| --- | --- |
| `SecurityFilterChain`, `HttpSecurity`, servlet `Filter` | `SecurityWebFilterChain`, `ServerHttpSecurity`, `WebFilter` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `SecurityContextHolder` phổ biến với thread-bound context | `ReactiveSecurityContextHolder` với Reactor Context |
| `@EnableMethodSecurity` cho chuỗi đồng bộ | `@EnableReactiveMethodSecurity` cho method security reactive |

Adapter chỉ giúp **một ranh giới xác thực** thích nghi với giao diện reactive. Nó không biến `OncePerRequestFilter` thành `WebFilter`, không mang nguyên thứ tự filter, session handling, CSRF, exception handlers hoặc semantics của servlet sang WebFlux.

Cần cấu hình đúng `SecurityWebFilterChain`, bộ chuyển đổi credentials (chẳng hạn HTTP Basic hoặc bearer token), authentication success/failure handling, authorization rules, session/context repository theo nhu cầu ứng dụng. Với reactive method security, nghiệp vụ được bảo vệ phải có kiểu trả về phù hợp với phương thức reactive được hỗ trợ; không thể giữ nguyên mọi interceptor dựa vào thread và tin rằng adapter sẽ xử lý.

## 8. Ví dụ cấu hình cầu nối có kiểm soát

Giả sử hệ thống **đã có một bean `AuthenticationManager` đồng bộ** hoạt động đúng (bao gồm provider, password encoder, cơ chế lockout/audit). Trong ứng dụng Spring Boot 3.x / Spring Security 6.x sử dụng `spring-boot-starter-webflux` và `spring-boot-starter-security`, cấu hình sau minh họa cách nối bean đó vào WebFlux:

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerAdapter;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import reactor.core.scheduler.Schedulers;

@Configuration
@EnableWebFluxSecurity
public class WebFluxSecurityConfig {

    @Bean
    ReactiveAuthenticationManager reactiveAuthenticationManager(
            AuthenticationManager legacyManager) {
        ReactiveAuthenticationManagerAdapter adapter =
                new ReactiveAuthenticationManagerAdapter(legacyManager);
        adapter.setScheduler(Schedulers.boundedElastic());
        return adapter;
    }

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {
        return http
                .authenticationManager(manager)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/**").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

**Cách đọc ví dụ:**

1. `AuthenticationManager` cũ vẫn xác thực và trả về `Authentication` hoặc ném `AuthenticationException` như trước. Một bean như vậy phải được cung cấp ở phần cấu hình legacy của ứng dụng; đoạn này không tự tạo provider hay dữ liệu người dùng.
2. `ReactiveAuthenticationManagerAdapter` bọc manager đồng bộ và trả về publisher cho WebFlux. `setScheduler` đặt nơi tác vụ legacy được thực thi; chọn scheduler sau khi hiểu phần việc thực tế và giới hạn tài nguyên.
3. `ServerHttpSecurity` nhận manager reactive, thiết lập đường public và yêu cầu xác thực với các đường còn lại; HTTP Basic là **cơ chế demo** để request có credentials. Đối với JWT/OAuth2, dùng cơ chế phù hợp thay vì giả định cấu hình Basic này áp dụng cho mọi hệ thống.
4. Khi cần CSRF, session, CORS, authentication entry point hoặc error handling khác, cấu hình theo yêu cầu bảo mật thực tế. Không tắt CSRF chỉ vì dùng reactive hay adapter.
5. Đây là **mảnh cấu hình trong ứng dụng Spring**, không phải file có `main` chạy riêng bằng `javac`. Nó cần dependencies WebFlux/Spring Security và một bean `AuthenticationManager` thật.

Không dùng thêm `Mono.fromCallable(...).subscribeOn(...)` để bọc *bên ngoài* adapter này nếu adapter đã chịu trách nhiệm định tuyến lịch thực thi. Thay vào đó, rà soát mọi lời gọi blocking **khác** nằm ngoài adapter.

## 9. Khi bắt buộc tự bọc một API đồng bộ khác

Không phải thành phần blocking nào cũng có adapter sẵn. Ví dụ dưới đây là một lớp Java 17 hoàn chỉnh trong project có Reactor Core (được cung cấp bởi `spring-boot-starter-webflux`); nó trì hoãn việc tra cứu legacy thông qua hàm đồng bộ và chuyển tác vụ sang `boundedElastic`.

~~~java
package demo.security;

import java.util.Objects;
import java.util.function.Function;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class LegacyLookupBridge {
    private final Function<String, String> blockingLookup;

    public LegacyLookupBridge(Function<String, String> blockingLookup) {
        this.blockingLookup = Objects.requireNonNull(blockingLookup);
    }

    public Mono<String> findRole(String username) {
        return Mono.fromCallable(() -> blockingLookup.apply(username))
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Đoạn trên **chỉ minh họa thao tác chờ blocking**, chưa phải dịch vụ cấp quyền production: dữ liệu role và quyền truy cập cần được xác minh theo chính sách của hệ thống. `Mono.fromCallable` phát ra giá trị khi callable trả khác `null`; nếu callable trả `null`, nó hoàn thành rỗng. Bởi vậy không được diễn giải “rỗng” là một lần xác thực thành công.

Bản kiểm thử JUnit 5 sau xác nhận tính lazy, không phụ thuộc vào thời gian sleep hay tên thread; cần `reactor-test` trong test dependencies. Đặt trong test source của cùng package:

~~~java
package demo.security;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LegacyLookupBridgeTest {

    @Test
    void lookupStartsOnlyWhenSubscribed() {
        AtomicInteger calls = new AtomicInteger();
        LegacyLookupBridge bridge = new LegacyLookupBridge(username -> {
            calls.incrementAndGet();
            return "mai".equals(username) ? "ROLE_USER" : null;
        });

        Mono<String> result = bridge.findRole("mai");
        assertEquals(0, calls.get());

        StepVerifier.create(result)
                .expectNext("ROLE_USER")
                .verifyComplete();

        assertEquals(1, calls.get());
    }
}
~~~

Với Spring Boot Gradle project đã cấu hình JUnit 5, kiểm tra có test dependency `io.projectreactor:reactor-test`, sau đó chạy tác vụ `./gradlew test` (Windows: `.\gradlew.bat test`). Kỳ vọng: **test pass**, không có stdout ứng dụng bắt buộc. Test chứng minh tính lazy và giá trị trả về; nó **không** chứng minh throughput, ngắt lệnh JDBC khi cancel hay bảo mật end-to-end.

## 10. Kết quả xác thực và lỗi phải giữ đúng ý nghĩa

Đối với `ReactiveAuthenticationManager.authenticate`, hợp đồng thường được hiểu như sau:

| Tín hiệu từ publisher | Ý nghĩa cần xử lý |
| --- | --- |
| `onNext(Authentication)` rồi complete | Xác thực được chấp nhận, đối tượng phải phản ánh đúng principal và authorities |
| Complete rỗng (`Mono.empty()`) | Manager không xác định/không xử lý được phương thức xác thực đó; không được coi là “đăng nhập thành công” |
| `onError(AuthenticationException)` | Xác thực bị từ chối; luồng WebFlux Security chuyển tới failure handling theo cấu hình |
| `onError` do lỗi hạ tầng | Cần phân biệt lỗi backend, thời gian chờ, dịch vụ không sẵn sàng; không nuốt lỗi rồi trả một principal giả |

Nếu provider legacy trả `null` để diễn đạt “không áp dụng”, kiểm tra hợp đồng adapter và manager cụ thể; tránh tự đổi thành một `Authentication` đã authenticated. Không dùng `onErrorResume(e -> Mono.just(adminAuth))`, không mặc định cấp quyền khi LDAP/DB lỗi, không log mật khẩu, access token hay secret để debug. Phân biệt 401 (chưa/chứng thực không hợp lệ), 403 (đã nhận diện nhưng thiếu quyền) và 5xx (lỗi hệ thống) bằng integration test, theo HTTP entry point và failure handler đang sử dụng.

## 11. Transaction, context và trạng thái phụ không được chuyển đổi tự động

Một phương thức đồng bộ gắn `@Transactional` dựa trên transaction manager kiểu JDBC và tài nguyên thread-bound có thể hoàn thành trong thread được offload **nếu toàn bộ lời gọi đồng bộ và transaction nằm trong cùng ranh giới thực thi**. Tuy vậy, điều này không biến transaction đó thành một transaction reactive.

Không nên mở transaction JDBC bằng một interceptor rồi chia việc ra nhiều publisher/worker thread, sau đó kỳ vọng transaction, connection hoặc `ThreadLocal` tự theo dòng tín hiệu. Reactive transaction management dùng cơ chế context và driver phù hợp; muốn chuyển toàn bộ sang reactive phải thiết kế lại transaction boundary và persistence stack, chẳng hạn dùng R2DBC khi đáp ứng nhu cầu.

Cũng phải kiểm tra legacy auditing, MDC/tracing, quota, retry, cache, request attributes và lifecycle của password encoder/provider. Chúng có thể dựa vào thread hoặc có mutable state không an toàn khi tăng concurrency. Việc dùng adapter không tự giải quyết thread safety, không thay thế kiểm thử chức năng và security review.

## 12. Các cách làm sai thường gặp

| Cách làm | Vì sao nguy hiểm | Hướng sửa |
| --- | --- | --- |
| `Mono.just(blockingCall())` | Blocking diễn ra lúc tạo publisher | `Mono.fromCallable` + scheduler phù hợp |
| Gọi `.block()` hoặc `.blockOptional()` trong request path WebFlux | Chặn thread xử lý; có thể bị Reactor từ chối trên non-blocking scheduler | Dùng `flatMap`/`map` và trả publisher đến cuối chuỗi |
| Dùng `Mono.defer(() -> Mono.just(blockingCall()))` rồi nghĩ đã non-blocking | `defer` chỉ hoãn thực thi, chưa đưa blocking ra khỏi event loop | Offload đúng chỗ bằng `subscribeOn` hoặc adapter hỗ trợ scheduler |
| Đặt `publishOn` sau thao tác blocking đã thực thi | Scheduler không quay ngược thời gian | Kiểm tra nguồn và thời điểm gọi |
| Coi mọi `AuthenticationException` là `Mono.empty()` | Làm mất tín hiệu thất bại và có thể gây fallback không mong muốn | Giữ đúng contract error/empty |
| Sao chép servlet `Filter`/`SecurityFilterChain` vào WebFlux | Sai hạ tầng filter và context | Dùng `WebFilter`/`SecurityWebFilterChain` |
| Lấy current user bằng `SecurityContextHolder` trên các thread bất kỳ | Context không đảm bảo đúng request | Dùng `ReactiveSecurityContextHolder` |
| Chỉ đặt Reactor `timeout` mà không có driver timeout | Legacy call có thể tiếp tục giữ thread/socket | Timeout đa tầng, bulkhead và quan sát |
| Khai báo mọi tầng là `Mono` nhưng tiếp tục JDBC/LDAP blocking bên dưới | Hệ thống vẫn bị giới hạn thread và connection pool | Cô lập ranh giới blocking hoặc chuyển sang driver native reactive |

## 13. Checklist kiểm thử trước khi đưa vào production

**Đúng chức năng và bảo mật**

- Credentials đúng: principal và authorities phù hợp; credentials sai: xác thực thất bại; provider không hỗ trợ: không tự cho phép.
- Khác biệt 401/403, behavior khi DB/LDAP timeout, lockout, audit và hành vi khi client hủy request được kiểm tra.
- Authorization rules của `SecurityWebFilterChain` và các method có `@EnableReactiveMethodSecurity` vẫn áp dụng sau khi đổi scheduler.
- Đồng thời nhiều user: không rò rỉ `SecurityContext`, dữ liệu phiên hoặc log giữa request; không log thông tin nhạy cảm.

**Đúng đặc tính vận hành**

- Dùng `StepVerifier` kiểm tra publisher lazy, kết quả và error path; dùng `WebTestClient` kiểm tra request HTTP thực sự đi qua filter chain.
- Tải đồng thời cao: đo event-loop stall, scheduler saturation, connection-pool wait, CPU hash, p95/p99 và backpressure ở downstream.
- Test timeout thật tại JDBC/LDAP client, không chỉ test `Mono.timeout`; quan sát request hủy nhưng tác vụ blocking còn chạy.
- Đo trước–sau theo cùng loại tải và cấu hình; đưa ra giới hạn concurrency, timeout budget và rollback plan có thể vận hành.

## 14. Khi nào dùng adapter, khi nào cần đổi kiến trúc?

| Tình huống | Quyết định thực tế |
| --- | --- |
| Thư viện legacy bắt buộc, lưu lượng vừa, cần tích hợp WebFlux từng bước | Adapter + scheduler + timeout + giới hạn concurrency + test là giải pháp chuyển tiếp hợp lý |
| Chỉ có một điểm gọi JDBC/LDAP blocking và đã có kế hoạch thay mới | Cô lập tại một boundary rõ ràng, đo đạc, thay dần bằng client/driver phù hợp |
| Tần suất xác thực rất cao, đòi hỏi p99 thấp, phần lớn thời gian chờ I/O blocking | Ưu tiên thay backend/driver bằng API non-blocking nếu khả thi; đánh giá cache/chính sách security và năng lực hạ tầng |
| Toàn ứng dụng vẫn chủ yếu là code MVC/JDBC blocking | Cân nhắc giữ mô hình servlet đồng bộ nếu phù hợp hơn với phần còn lại; WebFlux không phải mục tiêu bắt buộc |
| Cần khả năng hủy I/O thực sự, giao dịch reactive xuyên nhiều bước | Thiết kế end-to-end reactive, không dựa vào adapter như lời giải cuối cùng |
| Legacy manager phụ thuộc servlet request hoặc ThreadLocal ngầm | Phân tích và tách sự phụ thuộc trước; chuyển dữ liệu danh tính qua tham số/authentication tường minh |

**Kết luận kỹ thuật:** Adapter là công cụ **tương thích và khoanh vùng blocking**, không phải phép biến đổi tự động về hiệu năng, bảo mật hoặc transaction semantics. Thiết kế đúng giữ event loop thông thoáng, kiểm soát tải của phần đồng bộ, giữ hợp đồng xác thực rõ ràng và chứng minh bằng test. Khi các giới hạn của legacy chi phối yêu cầu sản phẩm, cần thay thành phần phụ thuộc hoặc chọn runtime phù hợp thay vì tiếp tục bọc thêm publisher.

## Tài liệu đối chiếu

- [Spring Security — ReactiveAuthenticationManagerAdapter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManagerAdapter.html)
- [Spring Security — ReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Project Reactor — FAQ: Wrap a Synchronous, Blocking Call](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking)
