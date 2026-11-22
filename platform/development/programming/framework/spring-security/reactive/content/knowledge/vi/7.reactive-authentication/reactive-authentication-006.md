# DelegatingReactiveAuthenticationManager và phối hợp nhiều bộ xác thực

> **Phạm vi:** Spring Security **reactive** trong Spring WebFlux, Spring Boot 3.x, Spring Security 6.3–6.5 và Java 17+. Chủ đề là **`DelegatingReactiveAuthenticationManager`**, cách phối hợp nhiều `ReactiveAuthenticationManager` theo thứ tự, ý nghĩa của ba tín hiệu Reactor (`success`, `empty`, `error`), cách kết nối với HTTP authentication, thiết kế fallback an toàn và kiểm thử. Các ví dụ dùng credential giả chỉ dành cho học tập; production phải xác thực dựa trên nguồn tin cậy, quản lý secret và TLS.

## 1. Tại sao cần nhiều bộ xác thực?

Một ứng dụng có thể có nhiều cách chứng minh danh tính:

- Người dùng đăng nhập bằng **username/password**.
- Một công việc tự động gọi API bằng **API key** hoặc chứng thư workload.
- REST API nhận **OAuth2 Bearer access token** (JWT hoặc opaque).
- Một hệ thống chuyển đổi dần từ một Identity Provider sang một Identity Provider khác.
- Mỗi tenant hoặc request path có cơ chế xác thực riêng.

Mỗi cơ chế có cách đọc credential, kiểm chứng, ánh xạ principal và cấp authorities khác nhau. Thay vì một method lớn chứa nhiều nhánh `if/else` và logic xác thực trộn lẫn, ta có thể đóng gói từng phương thức vào một `ReactiveAuthenticationManager`, sau đó **phối hợp** chúng tại ranh giới phù hợp.

`DelegatingReactiveAuthenticationManager` là một implementer của `ReactiveAuthenticationManager`. Nó nhận **danh sách manager có thứ tự**, thử xác thực request qua từng manager và sử dụng kết quả phù hợp theo contract. Đây là cấu trúc **ủy quyền tuần tự** theo tín hiệu của publisher, không phải phép kiểm tra nhiều cơ chế đồng thời hoặc cộng dồn quyền.

Khi các cơ chế tách biệt rõ bằng **HTTP path**, **credential scheme** hoặc **issuer/tenant**, đôi khi chọn đúng manager ngay từ đầu bằng `ReactiveAuthenticationManagerResolver` hoặc các cấu hình HTTP riêng sẽ tốt hơn thử tuần tự. Bài này trình bày rõ từng trường hợp.

### 1.1 Các thành phần trong WebFlux

| Thành phần | Trách nhiệm |
| --- | --- |
| `ServerAuthenticationConverter` | Đọc HTTP `ServerWebExchange` và biến credential thành một `Authentication` **chưa xác thực**; không tự chứng minh credential đúng |
| `AuthenticationWebFilter` | Xác định request cần xác thực, gọi converter rồi gọi `ReactiveAuthenticationManager`, xử lý thành công/thất bại |
| `ReactiveAuthenticationManager` | Kiểm tra credential và trả `Mono<Authentication>`, `Mono.empty()` hoặc `Mono.error(...)` |
| `DelegatingReactiveAuthenticationManager` | Thử nhiều `ReactiveAuthenticationManager` theo thứ tự |
| `Authentication` | Đại diện thông tin trước xác thực và kết quả sau xác thực (principal, authorities, trạng thái...) |
| `ReactiveSecurityContextHolder` | Cung cấp `SecurityContext` cho reactive request pipeline sau khi xác thực thành công |
| `SecurityWebFilterChain` / `ServerHttpSecurity` | Bao các WebFilter cho request, chọn cơ chế xác thực và áp dụng authorization |
| `ReactiveAuthenticationManagerResolver<C>` | Chọn **manager phù hợp với ngữ cảnh C**, ví dụ theo request/tenant, trước bước authenticate |

**Không nhầm:** `DelegatingReactiveAuthenticationManager` phối hợp **authentication managers**. `SecurityWebFilterChain` phối hợp các **WebFilter bảo mật** cho HTTP request. `DelegatingReactiveAuthorizationManager` thuộc **authorization**, ra quyết định cấp quyền; nó không xác minh credential.

## 2. Contract quan trọng nhất: thành công, không hỗ trợ, thất bại

API chức năng:

```java
@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
```

Đây là chữ ký để hiểu concept; interface thực tế ở package `org.springframework.security.authentication`. Mỗi manager nhận một `Authentication` yêu cầu (thường chưa authenticated) và trả về một trong ba dạng tín hiệu:

| Tín hiệu | Ý nghĩa nghiệp vụ của một delegate | Ảnh hưởng khi ghép manager |
| --- | --- | --- |
| `Mono.just(authenticated)` | Credential hợp lệ; kết quả chứa danh tính và authorities đã được xác minh | Dừng thử tiếp; dùng kết quả đầu tiên thành công |
| `Mono.empty()` | Manager **không thể ra quyết định**, ví dụ không hỗ trợ loại `Authentication` này | Cho phép thử manager tiếp theo |
| `Mono.error(AuthenticationException)` | Manager có trách nhiệm xử lý nhưng credential sai, tài khoản khóa, hoặc xác thực thất bại | **Mặc định dừng và phát lỗi**; không thử tiếp |
| `Mono.error(otherException)` | Thường là lỗi xử lý/hạ tầng; phải phân loại và xử lý an toàn | Mặc định phát lỗi; không âm thầm đổi thành thành công/empty |

Quy tắc lập trình then chốt:

> **“Không hỗ trợ” là `Mono.empty()`; “đã thử nhưng thất bại” là `Mono.error(...)`.** Không trả empty khi mật khẩu sai, token hết hạn hoặc chữ ký JWT không hợp lệ chỉ để một manager dễ dàng fallback sang cơ chế khác.

Trong ví dụ **hai manager theo loại credential**:

- Manager password nhận `UsernamePasswordAuthenticationToken` thì **kiểm tra password**. Nếu sai, trả `BadCredentialsException`; nếu đúng, trả authenticated token.
- Manager API key nhận `PreAuthenticatedAuthenticationToken` do **converter API key có kiểm soát** tạo ra. Nếu key sai, trả `BadCredentialsException`; nếu đúng, trả token đã cấp authorities.
- Nếu manager password nhận `PreAuthenticatedAuthenticationToken`, nó trả `Mono.empty()` vì **không phải loại credential của nó**.
- Nếu manager API key nhận `UsernamePasswordAuthenticationToken`, nó trả `Mono.empty()` vì **không thuộc cơ chế API key**.

### 2.1 Minh họa theo thứ tự

```text
Authentication request
        |
        v
DelegatingReactiveAuthenticationManager
        |
        +--> manager A.authenticate(request)
        |      |
        |      +-- Mono<Authentication> hợp lệ ----> TRẢ KẾT QUẢ
        |      +-- Mono.error(ex) -----------------> BÁO LỖI (mặc định)
        |      +-- Mono.empty() -------------------+
        |                                         |
        +<----------------------------------------+
        |
        +--> manager B.authenticate(request)
               |
               +-- Mono<Authentication> hợp lệ ----> TRẢ KẾT QUẢ
               +-- Mono.error(ex) -----------------> BÁO LỖI (mặc định)
               +-- Mono.empty() -------------------> tiếp manager tiếp theo
                                                     hoặc kết thúc empty
```

Các manager được cấu hình theo thứ tự của `List<ReactiveAuthenticationManager>` hoặc đối số varargs. Về mặt chính sách, **thứ tự rất quan trọng**: kết quả xác thực đầu tiên có giá trị sẽ được sử dụng; các manager phía sau không có cơ hội bổ sung hay kiểm chứng lại kết quả đó.

Việc xây dựng publisher có thể xảy ra khi method `authenticate` được gọi, còn I/O hay logic reactive thực sự thường chạy khi **subscription** diễn ra. Đừng tự gọi `subscribe()` hoặc `block()` bên trong manager để điều phối; hãy **trả lại `Mono`** và để chuỗi bảo mật/kiểm thử subscribe.

## 3. Cách tạo DelegatingReactiveAuthenticationManager

Hai cách hợp lệ của Spring Security 6.x:

```java
ReactiveAuthenticationManager combined =
    new DelegatingReactiveAuthenticationManager(passwordManager, apiKeyManager);
```

hoặc:

```java
List<ReactiveAuthenticationManager> managers =
    List.of(passwordManager, apiKeyManager);

DelegatingReactiveAuthenticationManager combined =
    new DelegatingReactiveAuthenticationManager(managers);
```

Các dòng là **snippet cần các biến/manager đã định nghĩa**; import `org.springframework.security.authentication.DelegatingReactiveAuthenticationManager` và `ReactiveAuthenticationManager`.

Đặc điểm:

1. **Constructor không tự biến mỗi delegate thành singleton Spring bean.** Bạn cần tạo các delegate và nối đúng vào `SecurityWebFilterChain`, `AuthenticationWebFilter` hoặc thành phần tiêu thụ `ReactiveAuthenticationManager`.
2. **Không tự dò “manager nào support token” bằng `supports(Class)` như Servlet `AuthenticationProvider`.** Reactive contract dùng `Mono.empty()` để biểu thị không ra quyết định.
3. **Không tự cộng hợp authorities** từ các manager. Nếu manager A thành công, kết quả A được dùng; B không chạy để cộng role.
4. **Không tự định tuyến HTTP header.** Header Basic/Bearer/API key phải được giải mã bởi converter phù hợp trước khi manager nhận `Authentication`.
5. **Không tự đăng nhập người dùng và không tự viết session.** Nó chỉ xác thực một `Authentication` do caller cung cấp.

### 3.1 Ngữ nghĩa của setContinueOnError

Trong Spring Security **6.3+**, API `setContinueOnError(boolean)` cho phép chọn chính sách khi delegate phát lỗi:

```java
DelegatingReactiveAuthenticationManager combined =
    new DelegatingReactiveAuthenticationManager(primary, secondary);

// Mặc định false. Cần lý do rất rõ mới bật:
combined.setContinueOnError(true);
```

- Khi **`false` (mặc định)**: một lỗi từ delegate làm quá trình xác thực thất bại; không sang delegate tiếp theo. Nếu delegate trả empty, vẫn chuyển tiếp.
- Khi **`true`**: implementation tiếp tục thử các delegate khác khi có lỗi, tìm **kết quả xác thực không empty, không error** theo Javadoc 6.5.
- Nếu mọi delegate không xác thực thành công, không nên đoán cụ thể exception cuối từ mỗi phiên bản: hãy kiểm tra tín hiệu hoàn tất/error với version thực tế và thiết lập chính sách **fail closed** ở tầng gọi.

**Cảnh báo bảo mật:** Dùng `setContinueOnError(true)` để “dự phòng” sau `BadCredentialsException` có thể mở đường từ **credential đã bị từ chối** sang provider yếu hơn. Ví dụ cơ chế mới khóa tài khoản nhưng provider cũ vẫn cho đăng nhập. Cách an toàn là **chỉ manager khác xử lý khi manager trước trả empty vì không hỗ trợ loại token**, hoặc chọn provider bằng ranh giới rõ ràng (tenant, path, issuer, header).

Không coi lỗi **Identity Provider downtime** giống lỗi **invalid credentials**. Đổi mọi lỗi thành empty hoặc bật continue-on-error toàn cục làm sai chính sách xác thực và có thể che lỗi vận hành. Nếu có yêu cầu dự phòng, thiết kế riêng phương án failover với ràng buộc security và test tất cả case.

## 4. Thiết kế delegate theo loại credential để không fallback nhầm

Hai cách phân chia thường gặp:

| Cách phân chia | Ví dụ | Đánh giá |
| --- | --- | --- |
| Theo **loại Authentication** | `UsernamePasswordAuthenticationToken` và `PreAuthenticatedAuthenticationToken` | Rõ ràng, dễ trả empty cho loại không hỗ trợ; thích hợp minh họa delegation |
| Theo **issuer / tenant** | JWT của IdP A vs IdP B | Thường chọn `ReactiveAuthenticationManagerResolver` dựa trên issuer/tenant đã xác minh; tránh thử chữ ký ngẫu nhiên nhiều lần |
| Theo **HTTP path** | `/browser/**` vs `/api/**` | Thường dùng nhiều `SecurityWebFilterChain` với `securityMatcher` và thứ tự rõ |
| Theo **Authorization scheme** | `Basic` vs `Bearer` | Mỗi converter/filter phù hợp, có thể dùng riêng manager; Resource Server là lựa chọn chuẩn cho Bearer |
| Theo **nhà cung cấp password cùng token type** | Directory mới + directory cũ | Nguy hiểm nếu coi sai password ở provider A là empty để thử provider B; phải có quy tắc nhận diện và giải quyết xung đột |

**Nguyên tắc phối hợp:** **Một credential phải được giải thích theo đúng phương thức mà client chọn**. Không nên để token vốn đã xác định là JWT lỗi chữ ký tự động bị thử như một loại API key “legacy” hoặc được coi là username/password. Điều đó làm yếu ranh giới bảo mật.

## 5. Ví dụ unit test Java 17+: hai manager với hai loại Authentication

Bài đầu tiên cố tình **không khởi chạy HTTP server**: học cách phân biệt success/empty/error của chính `DelegatingReactiveAuthenticationManager`. Dùng Spring Boot 3.x, JUnit 5, Reactor Test.

Trong project đã áp dụng Spring Boot plugin, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Khai báo file hoàn chỉnh `src/test/java/com/example/delegatingauth/DelegatingManagersTest.java`:

```java
package com.example.delegatingauth;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DelegatingReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class DelegatingManagersTest {

    private static Authentication userRequest(String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
            "alice", password
        );
    }

    private static Authentication serviceRequest(String key) {
        return new PreAuthenticatedAuthenticationToken("worker", key);
    }

    private static ReactiveAuthenticationManager passwordManager() {
        return request -> {
            if (!(request instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }
            if (!"alice".equals(request.getName())
                    || !"correct-test-password".equals(request.getCredentials())) {
                return Mono.error(new BadCredentialsException(
                    "Invalid username/password"));
            }
            return Mono.just(UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_READER"))
            ));
        };
    }

    private static ReactiveAuthenticationManager apiKeyManager() {
        return request -> {
            if (!(request instanceof PreAuthenticatedAuthenticationToken)) {
                return Mono.empty();
            }
            if (!"correct-test-key".equals(request.getCredentials())) {
                return Mono.error(new BadCredentialsException(
                    "Invalid API key"));
            }
            return Mono.just(new PreAuthenticatedAuthenticationToken(
                "service-worker",
                null,
                List.of(new SimpleGrantedAuthority("SCOPE_jobs.read"))
            ));
        };
    }

    @Test
    void passwordRequestSkipsUnsupportedKeyManager() {
        AtomicInteger passwordCalls = new AtomicInteger();

        ReactiveAuthenticationManager countedPassword = request -> {
            passwordCalls.incrementAndGet();
            return passwordManager().authenticate(request);
        };
        var combined = new DelegatingReactiveAuthenticationManager(
            apiKeyManager(), countedPassword
        );

        StepVerifier.create(
                combined.authenticate(userRequest("correct-test-password"))
            )
            .assertNext(result -> {
                assertThat(result.isAuthenticated()).isTrue();
                assertThat(result.getName()).isEqualTo("alice");
                assertThat(result.getAuthorities())
                    .extracting("authority")
                    .contains("ROLE_READER");
            })
            .verifyComplete();

        assertThat(passwordCalls).hasValue(1);
    }

    @Test
    void firstSuccessStopsLaterDelegates() {
        AtomicInteger laterCalls = new AtomicInteger();
        ReactiveAuthenticationManager later = request -> {
            laterCalls.incrementAndGet();
            return Mono.error(new IllegalStateException(
                "Must not be called"));
        };

        var combined = new DelegatingReactiveAuthenticationManager(
            apiKeyManager(), later
        );

        StepVerifier.create(
                combined.authenticate(serviceRequest("correct-test-key"))
            )
            .assertNext(result -> {
                assertThat(result.isAuthenticated()).isTrue();
                assertThat(result.getName()).isEqualTo("service-worker");
                assertThat(result.getAuthorities())
                    .extracting("authority")
                    .contains("SCOPE_jobs.read");
            })
            .verifyComplete();

        assertThat(laterCalls).hasValue(0);
    }

    @Test
    void wrongPasswordIsErrorAndDoesNotTryNextManager() {
        AtomicInteger fallbackCalls = new AtomicInteger();
        ReactiveAuthenticationManager riskyFallback = request -> {
            fallbackCalls.incrementAndGet();
            return Mono.just(UsernamePasswordAuthenticationToken.authenticated(
                "alice", null,
                List.of(new SimpleGrantedAuthority("ROLE_READER"))));
        };

        var combined = new DelegatingReactiveAuthenticationManager(
            passwordManager(), riskyFallback
        );

        StepVerifier.create(
                combined.authenticate(userRequest("WRONG"))
            )
            .expectError(BadCredentialsException.class)
            .verify();

        assertThat(fallbackCalls).hasValue(0);
    }

    @Test
    void wrongApiKeyIsAlsoError() {
        var combined = new DelegatingReactiveAuthenticationManager(
            passwordManager(), apiKeyManager()
        );

        StepVerifier.create(
                combined.authenticate(serviceRequest("WRONG"))
            )
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void unsupportedByAllManagersIsEmpty() {
        var combined = new DelegatingReactiveAuthenticationManager(
            passwordManager(), apiKeyManager()
        );

        Authentication unsupported = new TestingAuthenticationToken(
            "anything", "anything"
        );

        StepVerifier.create(combined.authenticate(unsupported))
            .verifyComplete();
    }

    @Test
    void continueOnErrorAllowsNextManagerToSucceed() {
        AtomicInteger secondCalls = new AtomicInteger();

        ReactiveAuthenticationManager rejects = request ->
            Mono.error(new BadCredentialsException("Rejected by first"));

        ReactiveAuthenticationManager second = request -> {
            secondCalls.incrementAndGet();
            return Mono.just(UsernamePasswordAuthenticationToken.authenticated(
                "alice", null,
                List.of(new SimpleGrantedAuthority("ROLE_READER"))));
        };

        var combined = new DelegatingReactiveAuthenticationManager(
            rejects, second
        );
        combined.setContinueOnError(true);

        StepVerifier.create(combined.authenticate(userRequest("WRONG")))
            .assertNext(result ->
                assertThat(result.getName()).isEqualTo("alice"))
            .verifyComplete();

        assertThat(secondCalls).hasValue(1);
    }
}
```

**Giải thích giới hạn của test:** `passwordManager()` và `apiKeyManager()` trong file này là **delegate test** dùng chuỗi credential cố định để minh họa contract, không phải provider production. `TestingAuthenticationToken` chỉ là token kiểm thử; `PreAuthenticatedAuthenticationToken` ở đây chỉ được **lựa chọn theo type** và kiểm tra key bởi code test. Trong hệ thống thật, phải kiểm chứng nguồn credential, chính sách account và quyền cấp ra.

Chạy:

```bash
./gradlew test --tests '*DelegatingManagersTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*DelegatingManagersTest'
```

Bảng kết quả **kỳ vọng của StepVerifier**, không phải stdout đã chạy trên máy này:

| Test | Tín hiệu kỳ vọng | Delegate phía sau |
| --- | --- | --- |
| `passwordRequestSkipsUnsupportedKeyManager` | Authenticated Alice, `ROLE_READER` | Password manager được gọi đúng một lần |
| `firstSuccessStopsLaterDelegates` | Authenticated service-worker, `SCOPE_jobs.read` | Manager sau **không** chạy |
| `wrongPasswordIsErrorAndDoesNotTryNextManager` | `BadCredentialsException` | Fallback **không** chạy vì `continueOnError=false` |
| `wrongApiKeyIsAlsoError` | `BadCredentialsException` | Không có authenticated result |
| `unsupportedByAllManagersIsEmpty` | Hoàn tất **không phát Authentication** | Các manager đều từ chối xử lý type |
| `continueOnErrorAllowsNextManagerToSucceed` | Kết quả thành công từ manager thứ hai | Chứng minh vì sao bật fallback theo error có thể nguy hiểm |

**Không copy policy của test cuối vào production.** Nó cố ý cho phép credential bị từ chối bởi manager A vẫn được manager B xác thực thành công để minh họa nguy cơ mở rộng trust boundary.

### 5.1 Bảng tín hiệu có cả thứ tự

Xét các chuỗi kết quả độc lập:

```text
A = empty, B = success    -> success từ B
A = success, B = anything -> success từ A, B không chạy
A = error, B = success    -> error của A (mặc định)
A = empty, B = empty      -> empty
A = empty, B = error      -> error của B
A = error, B = success    -> có thể đến B nếu continueOnError(true)
```

Nhớ rằng **“empty” không có nghĩa là password sai**. Nó có nghĩa manager **không có đủ cơ sở/không nhận trách nhiệm** xác thực request đó theo contract. Không biến mọi authentication exception thành empty bằng `onErrorResume(e -> Mono.empty())` để chạy qua các provider khác.

## 6. Kết nối vào WebFlux HTTP: converter → manager → SecurityContext

`DelegatingReactiveAuthenticationManager` tự nó **không thể đọc** `Authorization` hoặc `X-API-Key` từ HTTP request. Trong WebFlux, nhiệm vụ đó thuộc bộ lọc và converter:

```text
Request tới WebFlux
  |
  v
AuthenticationWebFilter / httpBasic() filter
  |
  +--> ServerAuthenticationConverter
  |       Basic header -> UsernamePasswordAuthenticationToken (chưa auth)
  |       X-API-Key    -> PreAuthenticatedAuthenticationToken (chưa auth)
  |
  v
DelegatingReactiveAuthenticationManager
  |
  +--> passwordManager cho UsernamePasswordAuthenticationToken
  +--> apiKeyManager cho PreAuthenticatedAuthenticationToken
  |
  +--> success: SecurityContext được đưa vào reactive pipeline
  +--> error: authentication failure handler xử lý
  +--> empty: không có authenticated result, policy phải deny protected request
  |
  v
authorizeExchange / method authorization -> Controller hoặc RouterFunction
```

Trong thực tế có thể **hai `AuthenticationWebFilter`** hoặc một filter do DSL tạo và một custom filter, cùng sử dụng một combined manager. Chúng thường có converter riêng, nhằm không làm mờ ranh giới Basic và API key.

`AuthenticationWebFilter` có hai entry point chính:

```java
new AuthenticationWebFilter(reactiveAuthenticationManager);
new AuthenticationWebFilter(authenticationManagerResolver);
```

Và có:

```java
filter.setServerAuthenticationConverter(converter);
filter.setRequiresAuthenticationMatcher(matcher);
filter.setSecurityContextRepository(repository);
```

Đây là snippet minh họa, không phải file độc lập. Trong Spring Security WebFlux, khi converter trả `Mono.empty()`, filter hiểu **request không chứa credential phù hợp để thử**, nên không gọi authentication manager. **Đây là tầng empty khác** với `Mono.empty()` trả ra từ delegate manager.

### 6.1 Ví dụ tích hợp hai loại credential trong một application context

Ví dụ dưới đây dùng:

- `GET /user/me` xác thực bằng **HTTP Basic**, được manager password xử lý.
- `GET /service/me` xác thực bằng **X-API-Key** của công việc tự động, được manager API key xử lý.
- Một `DelegatingReactiveAuthenticationManager` nhận hai manager loại trừ nhau bằng type.
- Một `SecurityWebFilterChain` đăng ký hạ tầng HTTP, trong đó Basic filter dùng combined manager và custom `AuthenticationWebFilter` dùng chính combined manager đó.
- Authorization phân biệt quyền: user cần `ROLE_READER`; service cần `SCOPE_service.read`.

Đây là **mẫu học tập**. Với giao tiếp service-to-service production, ưu tiên OAuth2 client credentials hoặc workload identity/mTLS; API key chỉ phù hợp khi đã thiết kế vòng đời/giới hạn/giám sát đầy đủ.

Trong `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chỉ dùng `spring-boot-starter-webflux` làm web server trong bài này. Nếu thêm cả `spring-boot-starter-web`, Spring Boot 3.x thường chọn Servlet/MVC mặc định và bộ `SecurityWebFilterChain` này không còn mô tả HTTP stack đang chạy.

Cấu trúc nguồn:

```text
src/main/java/com/example/delegatingauth/
  DelegatingAuthApplication.java
  DelegatingSecurityConfig.java
  IdentityController.java
src/test/java/com/example/delegatingauth/
  DelegatingManagersTest.java
  DelegatingHttpTest.java
src/main/resources/
  application.yml
```

### 6.2 DelegatingAuthApplication.java

`src/main/java/com/example/delegatingauth/DelegatingAuthApplication.java`:

```java
package com.example.delegatingauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DelegatingAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(DelegatingAuthApplication.class, args);
    }
}
```

### 6.3 DelegatingSecurityConfig.java: manager phối hợp và HTTP filters

`src/main/java/com/example/delegatingauth/DelegatingSecurityConfig.java`:

```java
package com.example.delegatingauth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DelegatingReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class DelegatingSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var user = User.withUsername("alice")
            .password(encoder.encode("demo-user-password"))
            .roles("READER")
            .build();
        return new MapReactiveUserDetailsService(user);
    }

    @Bean
    ReactiveAuthenticationManager combinedManager(
            MapReactiveUserDetailsService users,
            PasswordEncoder encoder,
            @Value("${demo.api-key}") String expectedApiKey) {

        if (expectedApiKey == null || expectedApiKey.isBlank()) {
            throw new IllegalArgumentException("API key must be configured");
        }

        var passwordDelegate =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        passwordDelegate.setPasswordEncoder(encoder);

        // UserDetails manager chỉ được gọi cho username/password.
        ReactiveAuthenticationManager passwordOnly = request -> {
            if (!(request instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }
            return passwordDelegate.authenticate(request);
        };

        // Demo: token pre-auth chưa xác thực, vẫn PHẢI kiểm API key.
        byte[] expectedDigest = sha256(expectedApiKey);
        ReactiveAuthenticationManager apiKeyOnly = request -> {
            if (!(request instanceof PreAuthenticatedAuthenticationToken)) {
                return Mono.empty();
            }
            Object credentials = request.getCredentials();
            if (!(credentials instanceof String supplied)
                    || !MessageDigest.isEqual(
                            expectedDigest, sha256(supplied))) {
                return Mono.error(new BadCredentialsException(
                    "Invalid API key"));
            }

            return Mono.just(new PreAuthenticatedAuthenticationToken(
                "trusted-service",
                null,
                List.of(new SimpleGrantedAuthority("SCOPE_service.read"))
            ));
        };

        // Thứ tự không làm đổi trách nhiệm: type không phù hợp -> empty.
        return new DelegatingReactiveAuthenticationManager(
            passwordOnly, apiKeyOnly
        );
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager combinedManager) {

        // Filter riêng chỉ thử X-API-Key trên đường dẫn service.
        var apiKeyFilter = new AuthenticationWebFilter(combinedManager);
        apiKeyFilter.setRequiresAuthenticationMatcher(
            new PathPatternParserServerWebExchangeMatcher("/service/**")
        );
        apiKeyFilter.setServerAuthenticationConverter(exchange -> {
            String rawKey = exchange.getRequest().getHeaders()
                .getFirst("X-API-Key");
            if (rawKey == null || rawKey.isBlank()) {
                return Mono.empty();
            }
            return Mono.just(new PreAuthenticatedAuthenticationToken(
                "api-key-request", rawKey
            ));
        });
        apiKeyFilter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance()
        );

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/user/**").hasRole("READER")
                .pathMatchers("/service/**").hasAuthority(
                    "SCOPE_service.read")
                .anyExchange().denyAll()
            )
            .httpBasic(basic -> basic.authenticationManager(combinedManager))
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .addFilterAt(
                apiKeyFilter,
                SecurityWebFiltersOrder.AUTHENTICATION
            )
            .build();
    }

    private static byte[] sha256(String text) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(text.getBytes(StandardCharsets.UTF_8));
        }
        catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
```

**Giải thích mã:**

1. `UserDetailsRepositoryReactiveAuthenticationManager` kiểm tra password qua `ReactiveUserDetailsService` và `PasswordEncoder`. Ta **bọc** nó bằng `passwordOnly` để mọi request không phải `UsernamePasswordAuthenticationToken` nhận `Mono.empty()` trước khi gọi delegate. Không mặc định cho rằng mọi manager framework đều xử lý sai type giống hệt nhau.
2. `apiKeyOnly` chỉ nhận `PreAuthenticatedAuthenticationToken` do API key converter tạo ra. **PreAuthenticated** là tên loại token, **không phải bảo đảm key đã được kiểm chứng**. Nó vẫn so khớp digest dự kiến và chỉ trả token authenticated **sau khi** kiểm tra đúng.
3. `MessageDigest.isEqual` so sánh hai digest SHA-256 đồng độ dài; ở demo, secret cấu hình nằm trong môi trường, không hardcode trong Java. Với production cần lưu key dưới dạng hash/HMAC hoặc hệ thống secret manager, rotation, expiry/revocation và giới hạn truy cập; SHA-256 thuần chưa đủ là giải pháp quản lý API key hoàn chỉnh.
4. `httpBasic(...authenticationManager(combinedManager))` đưa combined manager vào luồng Basic do Spring Security quản lý. Basic converter tạo username/password token. Nó **không tự đọc `X-API-Key`**.
5. Custom `AuthenticationWebFilter` dùng converter đọc `X-API-Key` chỉ trên `/service/**`. Nếu không có header, converter trả empty để không thử manager. Nếu key có mặt nhưng sai, API key manager trả lỗi; không trả empty để người dùng lách qua cơ chế khác.
6. `NoOpServerSecurityContextRepository` không lưu authentication vào session cho filter API key, nhưng request thành công vẫn có reactive SecurityContext trong xử lý hiện hành; request kế tiếp phải tự xuất trình credential.
7. `authorizeExchange` là **phân quyền sau xác thực**. `alice` có `ROLE_READER` nên truy cập `/user/**`; `trusted-service` có `SCOPE_service.read` nên truy cập `/service/**`.
8. Hai filter ở mức authentication có thể cùng xem một request khi xuất hiện nhiều loại credential. Ví dụ được thiết kế cho **mỗi request có một cơ chế dự kiến**. Trong sản phẩm thật, phải đặt policy rõ về **credential precedence**, từ chối hoặc xử lý có kiểm soát request mang đồng thời Basic và API key; chia chuỗi/filter theo path khi có yêu cầu tách biệt cứng.
9. Không tắt CSRF trong mẫu; ví dụ chỉ GET nên không cần CSRF token. Nếu thêm endpoint đổi dữ liệu, cần bảo vệ CSRF cho browser cookie và xem xét kỹ cơ chế credential trước khi quyết định cấu hình API stateless.

**Ghi chú an toàn:** Ví dụ giữ password demo trong mã để hướng dẫn. Không áp dụng user/key cứng như vậy ngoài môi trường học tập. API key vẫn là bearer secret: cần HTTPS, không log, không đặt vào URL/query, không gửi tới origin không tin cậy.

### 6.4 IdentityController.java: hai endpoint cùng đọc principal

`src/main/java/com/example/delegatingauth/IdentityController.java`:

```java
package com.example.delegatingauth;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class IdentityController {

    @GetMapping("/user/me")
    public Mono<String> user() {
        return principalName();
    }

    @GetMapping("/service/me")
    public Mono<String> service() {
        return principalName();
    }

    private Mono<String> principalName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> auth.getName());
    }
}
```

Controller này **không xác thực password/API key**. Nó chỉ đọc `Authentication` mà các WebFilter đã đưa vào Reactor Context khi xác thực thành công. Vì vậy cần giữ đúng `SecurityWebFilterChain` và không bỏ qua filters trong test.

### 6.5 application.yml: truyền key từ môi trường

`src/main/resources/application.yml`:

```yaml
demo:
  api-key: ${DEMO_API_KEY}
```

Trước khi chạy, cung cấp `DEMO_API_KEY` bằng cơ chế cấu hình an toàn. Chẳng hạn tại một terminal phát triển riêng, thiết lập biến môi trường cho **tiến trình** theo công cụ đang dùng. Không commit giá trị thật lên git, không đặt secret trong tài liệu hoặc HTTP request log.

Chạy ứng dụng bằng Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell: `.\gradlew.bat bootRun`. Nếu biến môi trường không có hoặc rỗng, cấu hình không khởi tạo thành công theo thiết kế; đó là fail-fast, không phải lý do để hardcode credential production.

## 7. Kiểm thử HTTP xác minh hai cơ chế qua cùng manager

Trong ví dụ trên, thêm integration test khởi chạy full WebFlux application với key **chỉ dùng trong test** và kiểm tra HTTP filter chain thật.

`src/test/java/com/example/delegatingauth/DelegatingHttpTest.java`:

```java
package com.example.delegatingauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "demo.api-key=test-only-service-key"
)
class DelegatingHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void basicPasswordAuthenticatesUserEndpoint() {
        client.get()
            .uri("/user/me")
            .headers(h -> h.setBasicAuth(
                "alice", "demo-user-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("alice");
    }

    @Test
    void apiKeyAuthenticatesServiceEndpoint() {
        client.get()
            .uri("/service/me")
            .header("X-API-Key", "test-only-service-key")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("trusted-service");
    }

    @Test
    void missingCredentialCannotAccessProtectedEndpoints() {
        client.get()
            .uri("/user/me")
            .exchange()
            .expectStatus().isUnauthorized();

        client.get()
            .uri("/service/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void incorrectBasicPasswordIsRejected() {
        client.get()
            .uri("/user/me")
            .headers(h -> h.setBasicAuth("alice", "WRONG"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void incorrectApiKeyIsRejected() {
        client.get()
            .uri("/service/me")
            .header("X-API-Key", "WRONG")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void basicUserCannotUseServiceOnlyAuthority() {
        client.get()
            .uri("/service/me")
            .headers(h -> h.setBasicAuth(
                "alice", "demo-user-password"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Chạy:

```bash
./gradlew test --tests '*DelegatingHttpTest'
```

Các trạng thái là **kỳ vọng của cấu hình minh họa**, không phải stdout đã quan sát từ một build ở đây. Nếu test không đi qua SecurityWebFilterChain (ví dụ test slice bind trực tiếp controller), kết quả có thể không phản ánh security thật. Với request có hai loại credential cùng lúc, mẫu cần bổ sung một chính sách rõ ràng trước khi coi là production-ready.

| Request | Authentication manager thực xử lý | Quyền cần có | Kỳ vọng |
| --- | --- | --- | --- |
| `GET /user/me` + Basic hợp lệ | Password | `ROLE_READER` | 200, `alice` |
| `GET /service/me` + API key hợp lệ | API key | `SCOPE_service.read` | 200, `trusted-service` |
| Hai route trên không credential | Không có kết quả authentication hợp lệ | Bị chặn | 401 |
| Password sai / API key sai | Manager tương ứng phát `BadCredentialsException` | Không được cấp quyền | 401 với handler phù hợp |
| Basic hợp lệ gọi `/service/me` | Password xác thực thành công | Thiếu `SCOPE_service.read` | 403 |

**Điểm suy luận:** `DelegatingReactiveAuthenticationManager` chỉ quyết định **danh tính đã được chứng minh bằng credential nào**. `hasRole` / `hasAuthority` quyết định **danh tính đó có được truy cập endpoint không**. 401 và 403 xuất phát từ chính sách/filter HTTP; không phải `authenticate` trực tiếp trả về status code.

## 8. Khi nào nên dùng resolver thay vì thử tất cả delegates?

`ReactiveAuthenticationManagerResolver<ServerWebExchange>` có thể trả về manager phù hợp với **ngữ cảnh request**, còn `DelegatingReactiveAuthenticationManager` thử nhiều manager trên **cùng đối tượng Authentication**.

Ví dụ có hai tenant, mỗi tenant có JWT issuer riêng:

- Phân tích request/claim cần thiết để xác định issuer.
- Chỉ chọn manager/decoder tin cậy đã đăng ký cho issuer đó.
- Manager được chọn vẫn phải xác minh chữ ký, `iss`, `aud`, hạn dùng và chính sách token.
- Không thử JWT của tenant A với manager tenant B chỉ vì A báo chữ ký sai.

Spring Security có các tích hợp chuẩn cho resource server và multi-tenancy như `JwtReactiveAuthenticationManager`, `ReactiveJwtDecoder`, `JwtIssuerReactiveAuthenticationManagerResolver` (tùy phiên bản/cách cấu hình). Hãy dùng chúng khi bài toán là JWT và issuer; không tự viết token parser hoặc tự tin claims chưa kiểm chứng để phân quyền.

Dưới đây là **pseudocode định tuyến** cho mục đích phân biệt, không phải code độc lập:

```text
Request -> determine trusted tenant/issuer candidate
        -> ReactiveAuthenticationManagerResolver.resolve(request)
        -> selected JwtReactiveAuthenticationManager
        -> validate signature/iss/aud/exp/scope
        -> authenticated principal or reject
```

Nếu chỉ cần **Basic cho browser** và **Bearer cho API**, cấu hình riêng cơ chế WebFlux HTTP Basic / OAuth2 Resource Server trong `ServerHttpSecurity`, hoặc nhiều `SecurityWebFilterChain` với `securityMatcher` theo path, là cách chuẩn hơn ghép hai validator thành một fallback mù.

### 8.1 Khác nhau giữa resolver và DelegatingReactiveAuthenticationManager

| Tiêu chí | DelegatingReactiveAuthenticationManager | ReactiveAuthenticationManagerResolver |
| --- | --- | --- |
| Input chính | Một `Authentication` request | Context như `ServerWebExchange` |
| Quyết định | Thử danh sách managers lần lượt dựa trên tín hiệu | Chọn manager theo context/tenant/path |
| Kiểu trả | `Mono<Authentication>` | `Mono<ReactiveAuthenticationManager>` |
| Dừng khi nào | Success đầu tiên; error mặc định dừng | Phụ thuộc resolver; manager được chọn tự authenticate |
| Thích hợp | Nhiều delegate biết từ chối unsupported type bằng empty | Tenant, issuer, route hoặc policy xác định manager |
| Rủi ro thiết kế | Fallback sai sau BadCredentials, thứ tự manager | Tin dữ liệu định tuyến chưa xác minh hoặc map tenant sai |

## 9. Những trường hợp dễ nhầm với servlet authentication

Ứng dụng Spring Security reactive sử dụng:

- `ReactiveAuthenticationManager`, `DelegatingReactiveAuthenticationManager`.
- `AuthenticationWebFilter` và `ServerHttpSecurity`.
- `SecurityWebFilterChain` và `ReactiveSecurityContextHolder`.

Ứng dụng Servlet/MVC có các khái niệm như `AuthenticationManager`, `ProviderManager`, `AuthenticationProvider`, `HttpSecurity`, `SecurityFilterChain`. Mục tiêu có thể tương tự nhưng API và request pipeline **khác nhau**. Đừng gắn `ProviderManager` vào `AuthenticationWebFilter` hoặc giả định `DelegatingReactiveAuthenticationManager` là lớp adapter cho Servlet providers.

Nếu app có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot 3.x thường chọn MVC mặc định. Cần kiểm tra application context đang là reactive trước khi dùng các cấu hình WebFlux ở bài này. Có `Mono` trong controller không tự chứng minh request đang đi qua reactive security.

## 10. Lỗi thực tế và cách sửa

### 10.1 Trả empty sau khi kiểm password sai

**Sai:**

```java
ReactiveAuthenticationManager wrong = request ->
    checkPassword(request)
        .onErrorResume(BadCredentialsException.class, error -> Mono.empty());
```

Đây là **snippet** phụ thuộc method `checkPassword`. Nó biến tín hiệu “đã kiểm và sai” thành “không biết xử lý”, khiến delegating manager có thể chạy tiếp provider khác. Nếu provider khác chấp nhận credential theo tiêu chuẩn yếu hơn, bạn vừa tạo bypass.

**Đúng:** Với credential phù hợp nhưng sai, giữ `Mono.error(new BadCredentialsException(...))`. Chỉ trả empty trước khi thực sự kiểm credential khi **loại token không thuộc trách nhiệm** của manager này.

### 10.2 Một manager nhận mọi Authentication rồi tự ép kiểu

**Sai:**

```java
ReactiveAuthenticationManager manager = authentication -> {
    UsernamePasswordAuthenticationToken token =
        (UsernamePasswordAuthenticationToken) authentication;
    return verifyPassword(token);
};
```

Snippet có thể gây `ClassCastException` khi danh sách manager nhận API-key token. Hãy kiểm tra `instanceof`, trả empty cho loại không hỗ trợ, rồi cast an toàn hoặc dùng pattern matching Java 17.

### 10.3 Dùng success để chứng minh hai bước xác thực đã hoàn tất

Một `DelegatingReactiveAuthenticationManager(A, B)` **không có nghĩa là “yêu cầu qua cả A và B”**. Nó dùng **kết quả phù hợp đầu tiên**. Nếu chính sách yêu cầu MFA (password + OTP) hoặc cả mTLS và token, phải tạo **authentication flow xác minh đủ các yếu tố** theo cơ chế Spring Security tương ứng; không dùng “delegation” như phép AND.

### 10.4 Trả token authenticated trước khi kiểm tra

`new PreAuthenticatedAuthenticationToken(principal, credentials, authorities)` là **constructor tạo authenticated token**. Chỉ gọi sau khi kiểm nguồn credential thực sự thành công, hoặc trong test. Tên class `PreAuthenticated` không tạo trust tự động.

### 10.5 Tự subscribe, block hoặc che lỗi

Không dùng `manager.authenticate(request).block()` trong WebFlux event loop; không gọi `subscribe` rồi lưu Authentication vào biến shared. Giữ chain:

```java
return manager.authenticate(request)
    .switchIfEmpty(Mono.error(
        new BadCredentialsException("No manager accepted credentials")))
    .flatMap(this::runForAuthenticatedPrincipal);
```

Snippet trên giả định class có `runForAuthenticatedPrincipal(Authentication)` trả về publisher tương thích. Việc đổi `empty` thành error phải do **caller biết policy** thực hiện; không gán `BadCredentialsException` cho mọi hệ thống mất kết nối hoặc lỗi server. Không log raw credentials, `Authentication.getCredentials()`, Bearer token hoặc API key.

### 10.6 Trộn xác thực và phân quyền

Một manager trả `Authentication` với authorities. API vẫn cần `authorizeExchange`/method authorization, kiểm tra tenant/resource ownership. Không coi “authenticated” là “được phép đọc mọi tài nguyên”.

### 10.7 Cấu hình nhiều chain nhưng không biết chain nào chạy

Khi có nhiều `SecurityWebFilterChain`, `securityMatcher` và `@Order` quyết định chain xử lý request. Một request thường chỉ chọn **chain đầu tiên khớp**, không tự đi qua mọi chains rồi thử mọi managers. Đừng nhầm **chọn security chain** với **delegating manager bên trong một filter**.

### 10.8 Đưa credential từ nguồn chưa tin cậy vào provider mạnh

Không dựa vào header `X-Tenant` hoặc claim JWT chưa kiểm chữ ký để cấp quyền hoặc chọn key tin cậy tùy ý. Nếu cần resolver theo tenant/issuer, hạn chế vào whitelist và xác minh cuối cùng trong manager đã chọn. Nếu một request cùng lúc có Basic và X-API-Key, nên định nghĩa chính sách reject/ưu tiên rõ thay vì để thứ tự filter tình cờ quyết định principal.

### 10.9 Credential đúng nhưng thiếu quyền

Đây là lỗi **authorization (403)**, không phải lý do gọi thêm authentication manager. Cấp quyền phải dựa vào kết quả authentication đã kiểm chứng và policy endpoint.

### 10.10 Phụ thuộc I/O blocking trong delegate reactive

Các manager phải trả publisher. Nếu gọi database/client blocking trực tiếp trên WebFlux event loop, app có thể bị nghẽn. Dùng reactive repository/client thích hợp; nếu buộc tích hợp blocking legacy, cô lập trên scheduler phù hợp và đánh giá tải, timeout/circuit breaker. Đừng coi `Mono.just(blockingCall())` là non-blocking: `blockingCall()` đã chạy đồng bộ trước khi Mono được tạo.

## 11. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân thường gặp | Điểm cần xem |
| --- | --- | --- |
| Delegate thứ hai không bao giờ được gọi | Delegate đầu phát success hoặc error | Kiểm thử tín hiệu `Mono.empty` vs `Mono.error` và thứ tự |
| Sai password nhưng vẫn login thành công | Đã bật continue-on-error hoặc chuyển BadCredentials thành empty | Trả error với credential được nhận diện; chặn fallback yếu |
| API key hợp lệ nhưng trả 401 | Converter không tạo đúng token, matcher sai, manager không đăng ký, key sai | HTTP filter, `ServerAuthenticationConverter`, request type, manager |
| Basic hợp lệ nhưng vào service route bị 403 | Authentication success nhưng thiếu authority yêu cầu | `ROLE_*` vs `SCOPE_*` và authorization policy |
| JWT lỗi vẫn được một cơ chế khác chấp nhận | Thử nhiều manager sau validation error | Ranh giới issuer/scheme; bỏ fallback lỗi token |
| Không có HTTP request nhưng manager được gọi | Caller test/service trực tiếp gọi `authenticate` | Phân biệt unit manager với WebFilter/HTTP |
| `Mono.empty()` dẫn tới hành vi khác mong đợi | Manager không quyết định, caller xử lý empty chưa rõ | Test policy fail-closed tại HTTP/service boundary |
| Hiệu năng xấu khi thử nhiều providers | Delegates tuần tự, mỗi cái có I/O | Định tuyến credential sớm, tránh thử nhiều IdP vô ích |
| Test unit pass nhưng WebFlux API vẫn 401 | Converter/filter/chain/matcher không hoạt động | Integration test `@SpringBootTest` với `WebTestClient` |
| Authentication object đã authenticated nhưng vô danh | Tạo token/authorities sai sau kiểm chứng | Kiểm tra principal mapping và lifecycle credential |

## 12. Bài tập tự kiểm tra

**Bài tập 1 — mô hình tín hiệu.** Manager A trả `Mono.empty()` cho `PreAuthenticatedAuthenticationToken`, manager B kiểm key đúng và trả authenticated token. Kết quả? **Dùng B**. A không xác thực hay từ chối, chỉ không hỗ trợ loại request.

**Bài tập 2 — lỗi credential.** Manager A kiểm password và phát `BadCredentialsException`; B vốn có khả năng cấp role READER. Mặc định B có được gọi không? **Không**. Error từ A dừng delegation. Không bật continue-on-error để “cứu” password sai.

**Bài tập 3 — tất cả empty.** Nếu A, B đều trả empty, request có được xem là authenticated không? **Không**. Không có `Authentication` thành công. Caller/web layer phải xử lý theo policy fail-closed.

**Bài tập 4 — thứ tự.** Đổi thứ tự hai manager có thể thay đổi kết quả không? **Có**, đặc biệt nếu cả hai cùng có thể xử lý một token type. Phân chia trách nhiệm tường minh để thứ tự không biến thành cơ chế cấp quyền ngoài ý muốn.

**Bài tập 5 — JWT và API key.** JWT đã nhận diện nhưng chữ ký sai; có thể thử giá trị JWT như API key để đăng nhập không? **Không nên**. Đây là credential đã bị từ chối theo một cơ chế cụ thể, không phải unsupported request cho provider khác.

**Bài tập 6 — MFA.** Gọi `new DelegatingReactiveAuthenticationManager(password, otp)` có bắt buộc người dùng qua cả password và OTP không? **Không**. Delegating manager thường lấy kết quả đầu tiên, không kết hợp hai authentication factors.

**Bài tập 7 — WebFilter.** Thêm một `@Bean DelegatingReactiveAuthenticationManager` mà không cấu hình HTTP converter/filter có tự khiến `X-API-Key` được đọc không? **Không**. Cần filter/converter xử lý header và gọi manager; đồng thời cần phân quyền với `SecurityWebFilterChain`.

**Bài tập 8 — 401 so với 403.** Password đúng nhưng user không có `SCOPE_service.read` khi gọi `/service/me`? **403** theo authorization policy. Không đưa request sang manager khác để “xin thêm scope”.

## 13. Checklist áp dụng trong dự án

- [ ] Đã xác định các kiểu credential và **đối tượng `Authentication` biểu diễn từng kiểu**.
- [ ] Mỗi delegate trả **`Mono.empty()` chỉ khi không thể ra quyết định/không hỗ trợ request**.
- [ ] Sai credential, account bị khóa, chữ ký token sai, token hết hạn → **error**, không tự chuyển thành empty.
- [ ] Thứ tự delegate có chủ đích; first success wins; không suy ra “đã qua tất cả managers”.
- [ ] Giữ `setContinueOnError(false)` mặc định trừ khi có chính sách failover được duyệt và kiểm thử chặt.
- [ ] Header/cookie/token được chuyển thành Authentication **chưa xác thực** qua converter hợp lệ.
- [ ] Filter hoặc `ServerHttpSecurity` thực sự dùng combined manager; không chỉ tạo bean rồi bỏ mặc.
- [ ] Quyền `hasRole`/`hasAuthority`, tenant và ownership được kiểm tra sau authentication.
- [ ] Khi route/tenant/issuer cho biết manager rõ ràng, cân nhắc resolver/chain riêng thay vì thử tất cả.
- [ ] Không dùng Servlet `ProviderManager` trong WebFlux reactive chain.
- [ ] Có unit test `StepVerifier` cho success/empty/error/order và HTTP test `WebTestClient` cho 401/403/200.
- [ ] Secret được bảo vệ, TLS bắt buộc, có rotation/revocation và không log credential; I/O không chặn event-loop.

**Ghi nhớ:** `DelegatingReactiveAuthenticationManager` nối nhiều `ReactiveAuthenticationManager` thành **quá trình thử tuần tự**. **`Mono.empty()` nói “không nhận trách nhiệm”; `Mono.error()` nói “xác thực thất bại”; `Mono.just(authenticated)` nói “đã xác thực thành công”.** Sự khác biệt này quyết định cả chức năng lẫn an toàn của hệ thống.

### Tài liệu tham khảo chính thức

- [Spring Security 6.5 — DelegatingReactiveAuthenticationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/DelegatingReactiveAuthenticationManager.html)
- [Spring Security 6.5 — ReactiveAuthenticationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html)
- [Spring Security 6.5 — AuthenticationWebFilter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Spring Security 6.5 — ServerHttpSecurity Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
