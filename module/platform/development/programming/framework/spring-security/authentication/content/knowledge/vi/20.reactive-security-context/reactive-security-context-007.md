# Tránh `.block()`, `.subscribe()` thủ công và `ThreadLocal` khi truyền danh tính trong Spring Security Reactive

## 1. Mục tiêu và phạm vi

Trong ứng dụng Spring WebFlux dùng Spring Security, một request có thể đi qua nhiều toán tử Reactor, thay đổi luồng thực thi, gọi dịch vụ khác rồi quay lại mà không giữ nguyên Java `Thread`. Vì vậy cần đồng thời bảo vệ **tính không chặn**, **vòng đời của publisher** và **ngữ cảnh bảo mật của đúng request**.

Sau bài này, bạn cần giải thích và thực hiện được:

- Không gọi `block()`, `blockFirst()`, `blockLast()`, `toFuture().get()` hoặc I/O đồng bộ trực tiếp trên luồng xử lý WebFlux.
- Không gọi `subscribe()` trong controller, service, authentication/authorization logic để “kích hoạt” công việc rồi trả response.
- Không lấy/truyền danh tính người dùng bằng `ThreadLocal` hay `SecurityContextHolder` kiểu Servlet trong một reactive chain; dùng `ReactiveSecurityContextHolder` và Reactor `Context` khi cần truy cập `Authentication`.
- Biết khi nào `Schedulers.boundedElastic()` chỉ là giải pháp chuyển tiếp cho thư viện blocking, và khi nào phải tách một ranh giới thực thi độc lập.
- Kiểm chứng đồng thời hai request có danh tính khác nhau, xử lý lỗi/cancel và không bị rò rỉ principal.

Phạm vi chính: **Spring Security trên WebFlux + Project Reactor (`Mono`/`Flux`)**. Các đoạn Java sử dụng API Spring Security 6.x, Spring Framework 6.x, Reactor 3.x và Java 17+. Ví dụ minh họa ngắn dùng tên repository/client giả định sẽ được ghi rõ; ví dụ ứng dụng hoàn chỉnh ở phần 7 có thể chạy trong một dự án Spring Boot WebFlux.

## 2. Mô hình thực thi: subscription, scheduler và security context

Trong Reactor, `Mono<T>` hoặc `Flux<T>` mô tả một chuỗi xử lý. Việc tạo publisher **không đồng nghĩa** tác vụ I/O đã được thực thi. Một `Subscriber` sẽ đăng ký (subscribe) để bắt đầu chuỗi; trên đường đi có các tín hiệu `onNext`, `onError`, `onComplete`, đồng thời có thể có `cancel`.

Ở request HTTP, WebFlux cùng hệ thống runtime chịu trách nhiệm subscribe vào publisher trả về từ handler/controller. Toán tử `map`, `flatMap`, `then`, `zip`… gắn thêm bước xử lý cho cùng chuỗi ấy. Một lời gọi `subscribe()` mới do service tự tạo thường mở **subscription khác**, khiến kết quả, lỗi và quyền hủy không còn gắn với request gốc.

Spring Security Reactive dùng `ReactiveSecurityContextHolder` để đọc `SecurityContext` từ **Reactor Context** liên kết với subscriber. `SecurityContext` chứa `Authentication` (principal, authorities, trạng thái xác thực). Cần phân biệt rõ:

| Khái niệm | Gắn với | Vai trò | Điều không được suy ra |
| --- | --- | --- | --- |
| Java `ThreadLocal` | Một Java thread | Dữ liệu cục bộ theo thread | “Thread hiện tại = người dùng hiện tại” trong WebFlux |
| Reactor `Context` | Subscription và luồng tín hiệu theo quy tắc Reactor | Truyền metadata qua các toán tử reactive | Không tự động nhảy vào mọi `Executor` hoặc subscription tách rời |
| Spring `SecurityContext` | Trạng thái bảo mật chứa `Authentication` | Xác định danh tính/quyền do Spring Security quản lý | Không tương đương với `reactor.util.context.Context` |
| `ReactiveSecurityContextHolder` | Cầu nối tới Reactor Context | `Mono<SecurityContext>` của reactive chain | Không phải một biến toàn cục dùng chung cho mọi request |

Luồng thông thường:

```text
HTTP request
    |
    v
Spring Security WebFilterChain
    |  xác thực, kiểm tra quyền, cung cấp SecurityContext
    v
WebFlux handler -> Mono/Flux -> service -> WebClient / reactive repository
    |                  |                         |
    +----------- cùng subscription / Reactor Context -----------+
    |
    v
WebFlux subscribe, phát HTTP response hoặc xử lý lỗi/hủy
```

`publishOn` và `subscribeOn` thay đổi nơi thực thi các bước của chuỗi. **Chuyển scheduler không tự động xóa Reactor Context** trong một reactive chain được ghép đúng cách. Điều dễ làm mất liên hệ là tạo subscription riêng, rời sang API bất đồng bộ ngoài Reactor mà không truyền ngữ cảnh qua ranh giới đã kiểm soát, hoặc chuyển sang cách đọc principal bằng `ThreadLocal`.

## 3. Anti-pattern 1: chặn bằng `block()` hoặc I/O đồng bộ

### 3.1. Vì sao nguy hiểm?

WebFlux thường xử lý nhiều kết nối trên số lượng event-loop thread tương đối nhỏ. `Mono.block()` đợi kết quả theo kiểu đồng bộ; nếu gọi trên thread được đánh dấu non-blocking của Reactor/Netty, nó có thể ném lỗi dạng `IllegalStateException` (“block()/blockFirst()/blockLast() are blocking…”). Ngay cả khi một lời gọi blocking chạy được trên thread khác, nó vẫn chiếm thread trong thời gian chờ, làm giảm khả năng phục vụ khi tải tăng.

**Sai — controller chờ WebClient:**

```java
@GetMapping("/profile")
public String profile() {
    return webClient.get()
            .uri("/profiles/current")
            .retrieve()
            .bodyToMono(String.class)
            .block(); // chặn luồng xử lý request
}
```

**Đúng — để WebFlux quản lý subscription:**

```java
@GetMapping("/profile")
public Mono<String> profile() {
    return webClient.get()
            .uri("/profiles/current")
            .retrieve()
            .bodyToMono(String.class);
}
```

Hai đoạn trên là **trích đoạn phương thức** trong controller đã có `WebClient` được cấu hình, không phải chương trình Java độc lập. Với phiên bản đúng, nếu downstream lỗi, lỗi đi theo `Mono` để lớp HTTP xử lý; nếu client hủy request, hủy có thể lan truyền qua chuỗi theo khả năng của từng thành phần.

Một lỗi tinh vi hơn là bọc việc chờ trong `map`:

```java
// Sai: gọi I/O blocking bên trong một toán tử reactive.
return userRepository.findById(id)
        .map(user -> blockingPaymentClient.lookup(user.id()));
```

Nếu phương thức trả về publisher, hãy nối bằng `flatMap`:

```java
// Đúng khi lookup trả về Mono<Payment>.
return userRepository.findById(id)
        .flatMap(user -> reactivePaymentClient.lookup(user.id()));
```

`map` dành cho phép biến đổi **đồng bộ, ngắn, không blocking**; `flatMap` dùng khi bước tiếp theo trả `Publisher`. Không nhầm một phương thức trả về `Mono` với một phương thức bắt buộc phải đợi kết quả ngay lập tức.

### 3.2. Nếu hệ thống còn thư viện blocking thì sao?

Ưu tiên API non-blocking thật sự (ví dụ `WebClient` thay vì HTTP client đồng bộ, driver R2DBC thay vì thực hiện JDBC trực tiếp trên event loop). Nếu chưa thể thay thư viện legacy, bao bọc từng đoạn blocking trong `Mono.fromCallable` và chuyển **đoạn ấy** sang `Schedulers.boundedElastic()`:

```java
// legacyClient.findProfile(userId) là lời gọi đồng bộ có thể block.
Mono<String> legacyProfile(String userId) {
    return Mono.fromCallable(() -> legacyClient.findProfile(userId))
            .subscribeOn(Schedulers.boundedElastic());
}
```

Đây là trích đoạn service, giả định đã có `legacyClient`, các import Reactor và phương thức trả `String`. Khi tác vụ trả `void`, có thể dùng `Mono.fromRunnable(...).subscribeOn(Schedulers.boundedElastic()).then()`. `fromCallable` chỉ gọi tác vụ lúc được subscribe; `subscribeOn` **lên lịch thực thi chứ không tự subscribe**.

Cần hiểu đúng giới hạn:

- `boundedElastic` giới hạn số thread/công việc chờ theo cấu hình; chuyển blocking sang đó **không biến API blocking thành non-blocking**. Phải theo dõi pool saturation, timeout, số connection và concurrency.
- Bọc nguồn blocking ở sát biên, rồi tiếp tục ghép `Mono` bằng các toán tử; không đặt `subscribeOn` tùy tiện quanh cả pipeline và coi mọi vấn đề đã được giải quyết.
- Không dùng `Schedulers.parallel()` để che blocking I/O; scheduler này dành cho công việc không chặn, ngắn hoặc thiên về CPU.
- Timeout/cancellation ở phía Reactor không bảo đảm lập tức ngắt được một socket/JDBC call đồng bộ đang chờ; cần cấu hình timeout của chính client/driver legacy.
- Việc chuyển scheduler không phải lý do để đọc `SecurityContextHolder` kiểu thread-local bên trong lambda blocking; nếu một API legacy cần user ID cho **nghiệp vụ**, trích danh tính hợp lệ trong reactive chain trước rồi truyền bằng đối số tường minh.

Ví dụ ghép đúng danh tính với legacy call, trong đó `legacyClient` là thư viện đồng bộ và phương thức trả `String`:

```java
Mono<String> profileForCurrentUser() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .flatMap(username ->
                    Mono.fromCallable(() -> legacyClient.findProfile(username))
                            .subscribeOn(Schedulers.boundedElastic()));
}
```

Không dùng `block()` để “lấy username” rồi gọi legacy client. Username ở đây là dữ liệu nghiệp vụ đã đọc từ security context của subscription; quyền truy cập tài nguyên vẫn phải được kiểm tra theo chính sách authorization, không chỉ dựa vào tên người dùng.

## 4. Anti-pattern 2: gọi `subscribe()` thủ công trong controller/service/filter

### 4.1. Vì sao “fire and forget” thường sai?

Ví dụ một service cập nhật dữ liệu rồi ghi audit:

```java
// Sai: cập nhật được chạy trên subscription tách rời.
Mono<Void> changeEmail(ChangeEmail command) {
    repository.update(command).subscribe();
    return Mono.empty();
}
```

Đây là trích đoạn; `ChangeEmail` và `repository` là thành phần giả định. Handler có thể trả thành công trước khi update hoàn tất; lỗi của update không đi về request; cancellation và thứ tự thực thi không còn thuộc hợp đồng của handler. Nhiều nguồn `Mono` là cold publisher, nên subscribe lại còn có thể chạy lại tác vụ I/O. Subscription phụ cũng không mặc nhiên nhận cùng `SecurityContext` đã gắn với request.

**Đúng — để nghiệp vụ nằm trong một pipeline:**

```java
// repository.update(command) -> Mono<SavedAccount>
// audit.record(id) -> Mono<Void>
Mono<Void> changeEmail(ChangeEmail command) {
    return repository.update(command)
            .flatMap(saved -> audit.record(saved.id()))
            .then();
}
```

`flatMap` chờ tác vụ audit được subscribe/chạy hoàn tất rồi mới kết thúc publisher kết quả. Nếu cập nhật và audit là tác vụ độc lập về dữ liệu nhưng đều bắt buộc xong, cân nhắc `Mono.when(first, second)`; nếu audit cần ID sau update, dùng `flatMap` như trên. Quyết định rollback/transaction phải dựa vào khả năng của repository và transaction manager, không ngầm cho rằng `then()` tạo transaction.

Một lỗi liên quan:

```java
// Sai: lambda tạo một Mono mới nhưng không đưa nó vào chuỗi.
return repository.update(command)
        .doOnNext(saved -> audit.record(saved.id()).subscribe())
        .then();
```

`doOnNext` thích hợp cho tác dụng phụ **đồng bộ, nhẹ** như tăng metric hoặc logging không blocking; không nên gọi tác vụ reactive thứ hai qua `subscribe()` bên trong nó. Đổi sang `flatMap` / `concatMap` / `then` tùy quan hệ dữ liệu và thứ tự.

### 4.2. Hệ quả về lỗi và hủy

Một pipeline được ghép đúng có đường đi rõ cho `onError` và `cancel`. Có thể dùng `onErrorMap` để chuyển lỗi, `onErrorResume` để fallback **có chủ đích**, `doOnError` để log; không dùng `onErrorResume(e -> Mono.empty())` đại trà khiến cập nhật thất bại bị coi là thành công. Lưu ý `retry` có thể subscribe lại nguồn và thực thi lại side effect, nên thao tác ghi cần thiết kế idempotency nếu có retry.

**Chỗ nào được gọi `subscribe()`?** Ở biên có chủ sở hữu vòng đời rõ ràng: WebFlux runtime khi trả HTTP, một message listener/consumer được framework quản lý, hoặc test chủ động dùng `StepVerifier`. Tác vụ nền độc lập với HTTP phải có cơ chế quản lý vòng đời, lỗi, retry, bảo mật, shutdown và quan sát riêng; việc tách công việc bất đồng bộ không biến `service.subscribe()` thành lựa chọn mặc định.

## 5. Anti-pattern 3: lấy danh tính bằng `ThreadLocal`/`SecurityContextHolder` kiểu Servlet

### 5.1. Sai lệch mô hình

Ở luồng Servlet truyền thống, người ta thường viết:

```java
// Không dùng như nguồn danh tính trong reactive service.
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
```

`SecurityContextHolder` mặc định gắn context với thread. Trong WebFlux, thread có thể được dùng lại cho các request khác, và một request có thể tiếp tục trên thread khác. Kết quả có thể là `null`, thông tin không tồn tại hoặc ngữ cảnh không phù hợp nếu ứng dụng tự đặt/xóa `ThreadLocal` sai. `InheritableThreadLocal`, thay đổi mode của `SecurityContextHolder`, hoặc tự sao chép principal sang các thread chỉ tạo thêm các trường hợp khó kiểm chứng; chúng không thay thế Reactor Context.

**Đúng — đọc từ ngữ cảnh của subscription:**

```java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
}
```

Đây là phương thức service trong vùng đã được Spring Security xác thực. `ReactiveSecurityContextHolder.getContext()` trả `Mono<SecurityContext>`; nếu không có context, chuỗi có thể hoàn thành rỗng. Đừng tùy tiện dùng giá trị mặc định “admin”, token giả hoặc biến toàn cục khi thiếu context. Yêu cầu xác thực/quyền phải được thể hiện tại `SecurityWebFilterChain`, `ReactiveAuthorizationManager` hoặc method security. Kiểm tra `isAuthenticated()` một cách độc lập cũng không thay thế kiểm tra quyền vì cơ chế anonymous authentication có quy tắc riêng.

### 5.2. Khi nào đọc principal, khi nào truyền user ID?

- Ở **biên HTTP/bảo mật**, Spring Security xác minh credential/token, nạp quyền và đưa `Authentication` vào Reactor Context. Với request bình thường, **không tự ghi đè** authentication bằng dữ liệu đến từ header tùy ý hoặc request body.
- Ở service cần quyết định “ai đang gọi”, dùng `ReactiveSecurityContextHolder.getContext()` trong pipeline, hoặc principal đã được framework cung cấp qua tham số handler. Không chuyển sang `block()` chỉ để lấy một trường.
- Sau khi kiểm tra authorization, nếu các hàm thuần nghiệp vụ hoặc thư viện blocking chỉ cần `userId` cho truy vấn/audit, truyền **giá trị rõ ràng qua tham số**. Điều này làm phụ thuộc dễ đọc, dễ test và không bắt buộc thư viện legacy hiểu Spring Security.
- `Authentication.getName()` không phải lúc nào cũng là database user ID. Với JWT/OIDC, định danh ổn định có thể nằm ở `sub` hoặc claim được hệ thống ánh xạ theo chính sách; không đồng nhất username/email với internal ID khi chưa thiết kế mapping và kiểm soát đối tượng được truy cập.

Ví dụ truyền danh tính được kiểm soát vào dịch vụ (trích đoạn; `accountService` trả `Mono<AccountView>`):

```java
Mono<AccountView> myAccount() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .flatMap(accountService::findAuthorizedViewFor);
}
```

Tên phương thức `findAuthorizedViewFor` biểu thị **service vẫn phải thực thi kiểm tra quyền dữ liệu**. Không nhận `userId` bất kỳ do client gửi rồi chỉ dựa vào `SecurityContext` có tồn tại để cho phép xem tài khoản người khác.

### 5.3. `contextWrite` và ranh giới subscription

Reactor Context di chuyển theo quan hệ subscriber trong pipeline, không phải dữ liệu thread-local. `contextWrite` thêm/sửa context cho các toán tử **ở phía upstream** của lời gọi đó (theo chiều subscription). Trong request WebFlux đã được xác thực, Spring Security chịu trách nhiệm cung cấp context cần thiết; controller/service thường chỉ **đọc**, không gọi `contextWrite(withAuthentication(...))` để tạo danh tính.

Với một test độc lập có thể xây dựng `Authentication` kiểm soát được, rồi thiết lập context cho publisher đang test:

```java
Authentication alice = UsernamePasswordAuthenticationToken.authenticated(
        "alice", "unused", AuthorityUtils.createAuthorityList("ROLE_USER"));

Mono<String> username = ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .publishOn(Schedulers.parallel())
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice));
```

Trích đoạn trên sử dụng các kiểu `Authentication`, `UsernamePasswordAuthenticationToken`, `AuthorityUtils`, `ReactiveSecurityContextHolder`, `Mono` và `Schedulers`; test hoàn chỉnh nằm ở phần 8. Nó minh họa rằng thông tin vẫn được đọc đúng sau đổi scheduler **trong cùng pipeline**. **Không** dùng mẫu tự tạo `Authentication` từ chuỗi `username` của client để vượt qua xác thực HTTP; ví dụ `withAuthentication` ở đây chỉ để dựng fixture đáng tin cậy trong test hoặc ranh giới nội bộ được thiết kế riêng.

Một lời gọi `repository.find(...).subscribe()` ở nơi khác không tự động nhận context của request cho dù cả hai subscription đôi khi chạy trên cùng thread. Tương tự, `CompletableFuture.supplyAsync`, `@Async`, executor tùy biến, callback ngoại vi và message queue là **ranh giới bất đồng bộ riêng**; cần xác định dữ liệu nào phải truyền rõ ràng và tích hợp context propagation thích hợp nếu framework hỗ trợ. Không kết luận rằng một `ThreadLocal` “đúng ở máy dev” sẽ đúng khi production tăng concurrency.

### 5.4. Downstream service và log

Có user trong `ReactiveSecurityContextHolder` **không có nghĩa** `WebClient` tự gửi access token đến mọi dịch vụ. Truyền credential sang downstream phải qua cấu hình client/security phù hợp (chẳng hạn OAuth2 authorized client khi thiết kế yêu cầu), kiểm tra audience/scopes và tuyệt đối không sao chép bearer token tùy tiện sang host không tin cậy.

MDC/correlation ID của thư viện logging thường dựa vào `ThreadLocal` và có thể cần integration context-propagation/bridge riêng. Trace ID, user ID để audit và đối tượng `Authentication` phục vụ authorization có trách nhiệm khác nhau; **không** dùng MDC hoặc header trace để ra quyết định cấp quyền. Hạn chế log token, password, toàn bộ principal hoặc dữ liệu nhạy cảm.

## 6. Cách ghép một luồng xác thực/nghiệp vụ đúng

Ví dụ chuỗi xử lý “đọc danh tính -> tra dữ liệu -> cập nhật audit”, giả định có:

- `accountRepository.findByOwner(String)` trả `Mono<Account>` (reactive).
- `auditService.recordRead(String)` trả `Mono<Void>`.
- `Account.displayName()` trả `String`.

```java
Mono<String> readOwnDisplayName() {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .flatMap(username ->
                    accountRepository.findByOwner(username)
                            .switchIfEmpty(Mono.error(
                                    new NoSuchElementException("Account not found")))
                            .flatMap(account ->
                                    auditService.recordRead(username)
                                            .thenReturn(account.displayName())));
}
```

Đây là trích đoạn logic trong một class có dependency được inject, không phải mã độc lập. Cấu trúc bảo đảm công việc audit nằm trong publisher được trả về và lỗi liên quan có thể lan ra. `NoSuchElementException` chỉ minh họa lỗi domain; tầng HTTP phải có quy tắc ánh xạ lỗi phù hợp, và service phải có kiểm tra quyền tài nguyên. Nếu muốn audit ngay cả khi đọc thất bại, cần định nghĩa semantics riêng cho sự kiện, không gọi một `subscribe()` tách rời trong `doOnError`.

Đối với danh sách kết quả, `flatMap` có thể chạy các inner publisher đồng thời; dùng `concatMap` nếu thứ tự và tính tuần tự bắt buộc, và giới hạn concurrency khi downstream có năng lực hữu hạn. Kết quả HTTP, lỗi, timeout, cancellation và thông tin bảo mật phải thuộc cùng mô hình xử lý đã thiết kế.

## 7. Ví dụ Spring Boot WebFlux hoàn chỉnh: đọc người dùng đang đăng nhập

Đoạn sau là **một file Java có thể biên dịch/chạy** trong dự án Spring Boot 3.x, Java 17+, có `spring-boot-starter-webflux` và `spring-boot-starter-security`. Ví dụ chỉ dùng HTTP Basic với user in-memory để học; **mật khẩu `{noop}` và HTTP không TLS không phù hợp production**. Không sử dụng kết quả từ HTTP header tự khai báo làm principal.

Đặt tại `src/main/java/demo/ReactiveIdentityApplication.java`:

```java
package demo;

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
public class ReactiveIdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveIdentityApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}dev-only-password")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(reader);
    }

    @RestController
    static class Api {
        @GetMapping("/public")
        Mono<String> publicEndpoint() {
            return Mono.just("public");
        }

        @GetMapping("/me")
        Mono<String> me() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(SecurityContext::getAuthentication)
                    .map(Authentication::getName)
                    .map(name -> "Hello, " + name);
        }
    }
}
```

Trong một dự án Gradle Spring Boot đã cấu hình sẵn plugin và Java 17+, các dependency cần có là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Chạy `./gradlew bootRun` (Windows: `gradlew.bat bootRun`) tại dự án chứa ứng dụng. Thử lần lượt:

```bash
curl -sS http://localhost:8080/public
curl -i http://localhost:8080/me
curl -sS -u reader:dev-only-password http://localhost:8080/me
```

Kỳ vọng:

1. Request `/public` trả body `public` mà không cần credential.
2. Request `/me` không có credential bị từ chối với HTTP **401 Unauthorized**.
3. Request `/me` đã xác thực trả body chính xác `Hello, reader`.

Ở đây `SecurityWebFilterChain` làm việc xác thực/authorization, `ReactiveSecurityContextHolder` chỉ đọc principal đã được cung cấp bởi Spring Security, và controller trả `Mono<String>` cho WebFlux subscribe. Không có `block()`, `subscribe()` thủ công hay `ThreadLocal`. Đừng tắt CSRF toàn cục chỉ để ví dụ GET chạy được; khi bổ sung request làm thay đổi trạng thái, thiết kế CSRF/authorization phù hợp loại client (browser có cookie, token bearer, v.v.).

## 8. Regression test: ngữ cảnh không biến thành ThreadLocal

Test nhỏ sau kiểm tra việc đọc principal sau `publishOn`; nó dùng `contextWrite` **chỉ để dựng fixture test**. Lưu tại `src/test/java/demo/ReactiveContextTest.java` nếu dự án có JUnit Jupiter, Spring Security Core và `reactor-test` (đã liệt kê ở phần 7).

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class ReactiveContextTest {
    @Test
    void currentUserSurvivesSchedulerSwitch() {
        Authentication alice = UsernamePasswordAuthenticationToken.authenticated(
                "alice", "unused",
                AuthorityUtils.createAuthorityList("ROLE_USER"));

        Mono<String> name = ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .publishOn(Schedulers.parallel())
                .contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice));

        StepVerifier.create(name)
                .expectNext("alice")
                .verifyComplete();
    }
}
```

Chạy `./gradlew test` hoặc `gradlew.bat test`; test **PASS** khi publisher phát đúng một chuỗi `alice` rồi hoàn thành. Đây là kiểm tra ở mức Reactor, chưa thay thế integration test cho HTTP/security filter chain.

Với hệ thống thực tế nên bổ sung các tình huống sau:

| Tình huống kiểm thử | Điều cần khẳng định |
| --- | --- |
| Hai request đồng thời của Alice và Bob | Mỗi kết quả/audit mang đúng danh tính riêng; không lẫn principal |
| Request không credential / không đủ quyền | Trả 401 / 403 theo chính sách đã cấu hình; không tự tạo quyền |
| Downstream trả lỗi hoặc timeout | Lỗi đi qua publisher, có xử lý thống nhất; không tạo công việc mồ côi |
| Client hủy request giữa chừng | Không có tác vụ `subscribe()` độc lập bị bỏ ngoài quyền quản lý |
| Di chuyển qua `publishOn` hoặc `subscribeOn` | Đọc `ReactiveSecurityContextHolder` vẫn đúng trong cùng subscription |
| Chuyển sang `CompletableFuture`/executor/broker | Danh tính/audit metadata được truyền qua ranh giới theo chính sách tường minh; không giả định ThreadLocal |

Khi muốn kiểm tra đồng thời, dùng `WebTestClient` và security test support (`spring-security-test`) hoặc gửi request thật với hai credential khác nhau; assert giá trị phản hồi và bản ghi audit theo từng request. Đừng viết test chỉ dựa vào thread name hoặc vào việc máy test dùng một worker thread.

## 9. Dấu hiệu lỗi và cách điều tra

**Có lỗi “`block() ... is blocking`” hoặc độ trễ tăng mạnh khi nhiều request.** Tìm `.block(`, `.blockFirst(`, `.blockLast(`, `Thread.sleep`, JDBC/HTTP client đồng bộ trong controller, service và cả callback `map`/`doOnNext`. Thay bằng API reactive; với legacy bắt buộc blocking, chuyển đoạn nguồn sang `fromCallable(...).subscribeOn(boundedElastic())`, đặt timeout và giới hạn tải.

**HTTP trả thành công nhưng DB/audit không cập nhật hoặc lỗi không được ghi nhận.** Tìm `.subscribe(` trong business code. Kiểm tra có publisher bị tạo ra rồi bỏ đi, `doOnNext` tự subscribe, hoặc `Mono<Void>` trả `Mono.empty()` quá sớm. Chuyển thành `flatMap`, `then`, `when` trong một publisher trả về từ controller.

**Principal có lúc là `null`, không thấy context sau callback, hoặc thông tin người dùng không ổn định.** Xem có `SecurityContextHolder.getContext()`, `ThreadLocal`, `InheritableThreadLocal`, `@Async`, subscription mới, custom executor, message queue hay không. Truy xuất `ReactiveSecurityContextHolder` trong chuỗi request đã xác thực; khi rời biên, truyền user ID nghiệp vụ hoặc tích hợp context propagation có kiểm soát.

**Chỉ có lỗi khi thêm `publishOn` và code cũ lấy user từ `ThreadLocal`.** Scheduler switch không bảo đảm thread giữ nguyên; sửa cách đọc context thay vì cố ghim toàn bộ request vào một thread. Tránh bọc logic Security vào `Schedulers.boundedElastic` một cách vô cớ.

**Thi thoảng có duplicate write sau retry.** `retry` subscribe lại upstream nên các side effect có thể chạy lại. Kiểm tra idempotency key, ranh giới transaction và điều kiện retry; không giải quyết bằng `subscribe()` riêng.

## 10. Nguyên tắc thiết kế và checklist áp dụng

1. **Giữ một pipeline có chủ sở hữu:** trả `Mono`/`Flux` từ controller, service và reactive filters. Để tầng runtime hoặc subscriber được quản lý thực hiện subscription.
2. **Không block event loop:** I/O ngoài phải non-blocking. Legacy blocking được cô lập sát nguồn trên `boundedElastic` và phải đo tài nguyên/timeout.
3. **Không tách công việc bắt buộc thành fire-and-forget:** ghép bằng `flatMap`, `then`, `when`, `concatMap` tùy thứ tự; xử lý `onError` và cancel có chủ đích.
4. **Lấy danh tính từ bảo mật đã xác thực:** dùng `ReactiveSecurityContextHolder` hoặc principal do Spring cung cấp; cấu hình authorization rõ ở `SecurityWebFilterChain` và/hoặc method security.
5. **Tách authorization khỏi dữ liệu nghiệp vụ:** truyền `userId` làm đối số sau khi kiểm tra quyền khi cần, nhưng không dùng username client gửi để giả mạo `Authentication` hoặc quyết định quyền thay cho security layer.
6. **Nêu rõ ranh giới:** các task nền, broker, executor, external callback và WebClient downstream không tự sở hữu security context của request; thiết kế identity/credential propagation theo trust boundary.
7. **Kiểm thử dưới tải và scheduler switch:** đồng thời nhiều principal, yêu cầu chưa xác thực, lỗi downstream, timeout, cancel và retry. Theo dõi event-loop latency, blocking operations và các subscription không có owner.

Quy tắc nhớ: **không “kéo” kết quả từ `Mono` bằng `block()`, không “đẩy” một subscription phụ bằng `subscribe()`, và không “đoán” danh tính từ thread.** Hãy ghép một reactive chain có chủ sở hữu và lấy context đúng từ subscriber.

## Tài liệu chính thức

- [Spring Framework — WebClient synchronous use và khuyến nghị trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html).
- [Spring Security — Reactive HTTP authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html).
- [Spring Security — Reactive Method Security và Reactor Context](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html).
- [Spring Security API — ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html).
- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/3.7.0/reference/advancedFeatures/context.html).
- [Project Reactor — Schedulers API](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html).
