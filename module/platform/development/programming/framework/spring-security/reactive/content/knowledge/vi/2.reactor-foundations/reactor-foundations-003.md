# Chuỗi toán tử `map`, `flatMap`, `filter` và `switchIfEmpty` trong xử lý xác thực

## 1. Bài toán và mục tiêu

Trong ứng dụng Spring WebFlux dùng Spring Security reactive, xác thực thường là một chuỗi bước bất đồng bộ: đọc thông tin đăng nhập → kiểm tra định dạng → tra cứu hoặc xác minh thông tin → đánh giá trạng thái tài khoản/token → tạo đối tượng người dùng đã xác thực. Project Reactor cho phép diễn tả luồng này bằng các toán tử trên `Mono<T>` mà không cần chặn luồng xử lý request.

Sau bài này, bạn cần phân biệt được:
- `map`: chuyển đổi **đồng bộ** một giá trị đang có.
- `flatMap`: gọi một bước tạo ra `Mono` mới (thường là I/O bất đồng bộ) và nối kết quả vào chuỗi.
- `filter`: chỉ cho giá trị đi tiếp khi điều kiện đồng bộ đúng; sai thì hoàn tất **rỗng**.
- `switchIfEmpty`: chuyển sang `Mono` dự phòng khi chuỗi phía trước hoàn tất **mà không phát ra giá trị**.

Điểm quan trọng nhất trong xác thực: **rỗng, lỗi và thành công là ba tín hiệu khác nhau**. Không được xem `Mono.empty()` là đã xác thực thành công hoặc tự coi mọi lỗi là rỗng.

## 2. Hiểu tín hiệu trước khi nối toán tử

`Mono<T>` phát tối đa một phần tử: `onNext(value)` rồi `onComplete`, hoặc chỉ `onComplete` (rỗng), hoặc `onError(error)`. Ví dụ:

~~~java
Mono.just("linh");                            // Có một giá trị.
Mono.<String>empty();                         // Không có giá trị, không có lỗi.
Mono.<String>error(new IllegalStateException("Failed")); // Có lỗi.
~~~

Một `Mono` điển hình là *cold*: việc xây chuỗi chưa đồng nghĩa với việc chạy truy vấn. Chuỗi thực thi khi được subscribe; trong Spring WebFlux, framework đảm nhận việc subscribe. Nếu nguồn rỗng, các lambda `map`, `flatMap` và `filter` nằm phía sau **không được gọi**; `switchIfEmpty` có thể cung cấp nhánh thay thế. Nếu nguồn lỗi, lỗi truyền xuống các toán tử sau và `switchIfEmpty` **không** bắt lỗi đó.

| Tín hiệu | Ý nghĩa trong ví dụ xác thực | Hành vi của `switchIfEmpty` |
| --- | --- | --- |
| Có giá trị | Đã lấy được token/claims/user | Không chạy nhánh dự phòng |
| Hoàn tất rỗng | Chưa có dữ liệu, bị `filter` loại, hoặc tra cứu không tìm thấy | Chạy nhánh dự phòng |
| `onError` | Xác thực thất bại, dịch vụ lỗi, hoặc toán tử phát lỗi | Không chạy; lỗi tiếp tục lan truyền |

Khi ghép các bước, hãy tự hỏi: “Bước này trả về một giá trị, một `Mono`, hay có thể trả về rỗng/lỗi?”

## 3. Vai trò chính xác của bốn toán tử

### 3.1. `map` — biến đổi dữ liệu đồng bộ

Cú pháp: `Mono<T>.map(T -> R)` tạo `Mono<R>`.

~~~java
Mono<String> raw = Mono.just("  Bearer demo-token  ");
Mono<String> normalized = raw.map(String::trim);
~~~

`map` thích hợp với cắt khoảng trắng, trích username/subject từ claims **đã được xác minh**, dựng DTO hoặc chuyển claims đã hợp lệ thành principal. Hàm ánh xạ phải trả về giá trị khác `null`. Ngoại lệ phát sinh trong hàm được chuyển thành tín hiệu `onError`.

Không dùng `map` để gọi dịch vụ trả `Mono<User>`:

~~~java
Mono<Mono<User>> nested = usernameMono.map(userRepository::findByUsername);
~~~

Đoạn trên tạo `Mono<Mono<User>>`, không cho ra trực tiếp `User`. Khi bước tiếp theo cần đợi kết quả từ repository/reactive API, dùng `flatMap`.

### 3.2. `flatMap` — ghép thao tác bất đồng bộ

Cú pháp: `Mono<T>.flatMap(T -> Mono<R>)` tạo `Mono<R>`.

~~~java
Mono<User> user = usernameMono.flatMap(userRepository::findByUsername);
~~~

`flatMap` đăng ký `Mono` do hàm trả về và truyền tiếp kết quả hoặc lỗi/rỗng của nó. Trường hợp xác thực điển hình: truy vấn người dùng bằng reactive repository, xác minh token qua API bất đồng bộ, tải thông tin quyền từ dịch vụ khác. Không `block()` bên trong `flatMap`; hành động đó làm mất lợi ích non-blocking và có thể gây lỗi trên luồng WebFlux.

Với `Mono`, `flatMap` xử lý tối đa một giá trị. Khi nguồn là `Flux` có nhiều giá trị, `flatMap` có thể cho các tác vụ xen kẽ thứ tự; đó là một vấn đề riêng khi xử lý nhiều phần tử, không cần áp dụng máy móc vào chuỗi xác thực một request.

### 3.3. `filter` — giữ hoặc loại giá trị

Cú pháp: `Mono<T>.filter(T -> boolean)` vẫn có kiểu `Mono<T>`.

~~~java
Mono<String> token = Mono.just("demo-token")
    .filter(value -> !value.isBlank());
~~~

Nếu predicate trả về `false`, phần tử bị loại và chuỗi hoàn tất rỗng; `filter` **không tự tạo lỗi “token không hợp lệ”**. Vì thế cần nhánh xử lý rỗng tại một vị trí có ngữ nghĩa rõ ràng.

`filter` phù hợp với quy tắc đồng bộ: token không rỗng, tài khoản đã bật, claims chưa bị đánh dấu thu hồi (nếu trạng thái đã nằm trong đối tượng). Nếu kiểm tra điều kiện phải gọi API trả `Mono<Boolean>`, sử dụng `filterWhen` hoặc `flatMap` kết hợp quyết định rõ ràng; không gọi `block()` trong predicate.

### 3.4. `switchIfEmpty` — xử lý nhánh không có kết quả

Cú pháp: `Mono<T>.switchIfEmpty(Mono<? extends T>)`.

~~~java
Mono<User> user = userRepository.findByUsername(username)
    .switchIfEmpty(Mono.error(
        new IllegalArgumentException("User not found")));
~~~

Nhánh này chỉ chạy khi publisher phía trước hoàn tất rỗng. Có thể dùng để tạo lỗi, lấy nguồn phụ hoặc trả giá trị mặc định **nếu việc dùng mặc định là an toàn**. Với xác thực, tuyệt đối tránh đặt một “principal mặc định đã đăng nhập” làm fallback.

Để trì hoãn cả việc *tạo* publisher dự phòng (ví dụ hàm dựng publisher có side effect), dùng:

~~~java
Mono<User> result = primaryLookup(username)
    .switchIfEmpty(Mono.defer(() -> secondaryLookup(username)));
~~~

`Mono.defer` tạo publisher phụ khi có subscribe vào nhánh fallback; nó cũng tránh tác dụng phụ khi xây chuỗi trước lúc cần fallback. `switchIfEmpty` không thay `onErrorResume`: lỗi xác thực cần được phát hoặc xử lý tường minh theo chính sách, không âm thầm biến thành người dùng hợp lệ.

## 4. Thiết kế một chuỗi xác thực theo thứ tự hợp lý

Xét đầu vào HTTP `Authorization: Bearer <token>`. Với một token nhận diện hợp lệ, luồng minh họa có dạng:

~~~text
Header có thể null
  │
  ▼
Mono.justOrEmpty(header)
  │ map(trim)                  Chuẩn hóa đồng bộ
  ▼
filter(startsWith("Bearer ")) Kiểm tra cấu trúc
  │ map(remove prefix)        Trích token
  ▼
filter(token không rỗng)
  │ switchIfEmpty(error)      Thiếu token / sai định dạng → lỗi
  ▼
flatMap(lookupOrVerifyToken)  Tra cứu/xác minh trả Mono<Claims>
  │ filter(claims.active)     Loại claims không còn hiệu lực
  ▼
switchIfEmpty(error)          Không tìm thấy / không còn hiệu lực → lỗi
  │ map(toPrincipal)          Tạo kết quả đã xác thực
  ▼
Mono<Principal> hoặc onError
~~~

Đặt `switchIfEmpty` **ngay sau nhóm kiểm tra đầu vào** giúp phân biệt “thiếu token” với “token đã đưa vào nhưng không hợp lệ”. Đặt fallback thứ hai sau tra cứu giúp phân biệt không tìm thấy hoặc trạng thái không còn hiệu lực. Khi cả hai nhánh đều kết thúc bằng cùng một loại lỗi, có thể gom logic, nhưng mất sự tách bạch cần thiết cho việc kiểm thử.

## 5. Ví dụ Java 17+ chạy được với Reactor

Ví dụ dưới đây mô phỏng việc tra cứu token bằng `Map` trong bộ nhớ để quan sát tín hiệu. **Đây không phải cơ chế xác minh JWT hay mật khẩu cho production**; dịch vụ thật phải xác minh chữ ký, hạn dùng, issuer/audience, trạng thái thu hồi và các ràng buộc áp dụng trước khi chấp nhận danh tính.

Tạo ứng dụng Gradle tối thiểu với tệp `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ReactiveAuthDemo'
}
~~~

Tạo `src/main/java/demo/ReactiveAuthDemo.java`:

~~~java
package demo;

import java.util.Map;
import reactor.core.publisher.Mono;

public class ReactiveAuthDemo {

    record TokenClaims(String subject, boolean active) {}
    record Principal(String username, String authority) {}

    private static final Map<String, TokenClaims> TOKENS = Map.of(
        "valid-token", new TokenClaims("linh", true),
        "disabled-token", new TokenClaims("linh", false)
    );

    private static Mono<TokenClaims> lookupToken(String token) {
        // Mô phỏng nguồn reactive: không tìm thấy => Mono.empty().
        return Mono.defer(() -> Mono.justOrEmpty(TOKENS.get(token)));
    }

    static Mono<Principal> authenticate(String authorization) {
        return Mono.justOrEmpty(authorization)
            .map(String::trim)
            .filter(header -> header.startsWith("Bearer "))
            .map(header -> header.substring("Bearer ".length()).trim())
            .filter(token -> !token.isBlank())
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Missing Bearer token")))
            .flatMap(ReactiveAuthDemo::lookupToken)
            .filter(TokenClaims::active)
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Invalid or inactive token")))
            .map(claims -> new Principal(claims.subject(), "ROLE_USER"));
    }

    private static void show(String header) {
        try {
            // block() chỉ dùng ở hàm main demo, KHÔNG dùng trong WebFlux handler.
            Principal principal = authenticate(header).block();
            System.out.println("OK: " + principal.username()
                + " (" + principal.authority() + ")");
        } catch (IllegalArgumentException ex) {
            System.out.println("FAIL: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        show("Bearer valid-token");
        show("Bearer disabled-token");
        show("Bearer unknown-token");
        show(null);
    }
}
~~~

Chạy từ thư mục dự án bằng `gradle run --quiet` (cần Gradle, JDK 17 và có thể tải dependency từ Maven Central). Nếu dự án có Gradle Wrapper, dùng `./gradlew run --quiet` trên Unix/macOS hoặc `gradlew.bat run --quiet` trên Windows.

Kết quả stdout:

~~~text
OK: linh (ROLE_USER)
FAIL: Invalid or inactive token
FAIL: Invalid or inactive token
FAIL: Missing Bearer token
~~~

**Giải thích từng trường hợp:**
1. `valid-token` → `map` trích chuỗi, `flatMap` tìm thấy claims đang active, `filter` giữ lại, `map` tạo `Principal`.
2. `disabled-token` → tra cứu có claims nhưng `filter(TokenClaims::active)` trả false → rỗng → fallback lỗi “Invalid or inactive token”.
3. `unknown-token` → `lookupToken` hoàn tất rỗng → `flatMap` phát rỗng → cùng fallback lỗi.
4. `null` → `Mono.justOrEmpty` rỗng ngay từ đầu, các `map`/`filter`/`flatMap` trước fallback không được gọi → lỗi “Missing Bearer token”.

Lưu ý: việc dùng `Mono.defer` ở đây minh họa cách tạo publisher cho mỗi lần đăng ký, **không** biến tra cứu `Map` thành I/O bất đồng bộ. Trong ứng dụng thật, repository hoặc client reactive sẽ cung cấp publisher non-blocking.

## 6. Liên hệ với Spring Security reactive

Trong WebFlux, `ReactiveAuthenticationManager.authenticate(Authentication)` trả `Mono<Authentication>`. Hợp đồng của interface có ý nghĩa quan trọng:
- Phát ra `Authentication` khi xác thực thành công.
- Hoàn tất rỗng khi manager **không thể đưa ra quyết định** đối với yêu cầu đó (ví dụ kiểu authentication không được hỗ trợ).
- Phát `onError` với lỗi xác thực khi đã xử lý thông tin đăng nhập và xác định là không hợp lệ.

Ví dụ sau **chỉ là đoạn tích hợp minh họa**, giả định ứng dụng đã có `TokenVerifier` trả `Mono<VerifiedClaims>` sau khi kiểm tra token đầy đủ và đã cấu hình Spring Security WebFlux/Resource Server:

~~~java
import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import reactor.core.publisher.Mono;

record VerifiedClaims(String subject, boolean active) {}

interface TokenVerifier {
    // Chỉ trả claims khi token đã qua kiểm tra an toàn.
    Mono<VerifiedClaims> verify(String rawToken);
}

final class CustomReactiveAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final TokenVerifier verifier;

    CustomReactiveAuthenticationManager(TokenVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    public Mono<Authentication> authenticate(Authentication incoming) {
        if (!(incoming instanceof BearerTokenAuthenticationToken bearer)) {
            return Mono.empty(); // Manager này không xử lý kiểu token khác.
        }

        return verifier.verify(bearer.getToken())
            .filter(VerifiedClaims::active)
            .switchIfEmpty(Mono.error(
                new BadCredentialsException("Invalid credentials")))
            .map(claims -> (Authentication)
                new UsernamePasswordAuthenticationToken(
                    claims.subject(),
                    null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER"))));
    }
}
~~~

Các điểm cần đọc đúng:
- `verifier.verify(...)` là bước bất đồng bộ đã trả `Mono`; trong biến thể có bước đọc token từ reactive source, dùng `flatMap(verifier::verify)` để nối nó. Không nên dùng `map` tạo `Mono<Mono<VerifiedClaims>>`.
- `filter(VerifiedClaims::active)` chỉ chấp nhận claims đã xác minh và còn hiệu lực.
- `switchIfEmpty` chuyển “token có loại hỗ trợ nhưng không xác minh được” sang `BadCredentialsException`. Ngược lại, `Mono.empty()` ở nhánh kiểu đầu vào không hỗ trợ có nghĩa “manager này không quyết định được”, phù hợp hợp đồng interface.
- `map` chuyển claims hợp lệ thành `Authentication` có authorities. Trong hệ thống thật, chỉ gán quyền đã được xác định một cách đáng tin cậy từ chính sách/claims; `ROLE_USER` ở đây là vai trò demo, không phải quy tắc cấp quyền thực tế.

Spring Security thường đã có bộ giải mã/xác minh JWT hoặc opaque token của Resource Server. Hãy dùng khả năng sẵn có khi phù hợp; ví dụ custom phía trên phục vụ việc hiểu chuỗi toán tử, không phải khuyến nghị tự xây cơ chế mật mã.

**Xác thực khác phân quyền:** xác thực chứng minh *ai* đang truy cập; phân quyền quyết định danh tính đó *được phép làm gì*. Kết quả HTTP 401/403 phụ thuộc SecurityWebFilterChain, entry point và access-denied handler đã cấu hình; bản thân `switchIfEmpty` không phát HTTP status. Đối với WebFlux, ngữ cảnh bảo mật được lan truyền qua Reactor Context (ví dụ `ReactiveSecurityContextHolder`), không nên dựa vào ThreadLocal như luồng servlet thông thường.

## 7. Phân biệt các nhánh rỗng và lỗi

Một chuỗi dễ gây lỗi logic:

~~~java
Mono<VerifiedClaims> claims = verifier.verify(rawToken)
    .filter(VerifiedClaims::active);
~~~

Nếu `verifier.verify` trả rỗng khi không có token, `filter` cũng có thể trả rỗng khi token hết hiệu lực. Không có fallback, downstream có thể nhận thành công rỗng mà không có câu trả lời xác thực tường minh. Cần xác định hợp đồng của từng bước và thêm xử lý lỗi phù hợp:

~~~java
Mono<VerifiedClaims> claims = verifier.verify(rawToken)
    .filter(VerifiedClaims::active)
    .switchIfEmpty(Mono.error(
        new BadCredentialsException("Invalid credentials")));
~~~

Nếu `verify` phát lỗi (chẳng hạn invalid signature được thể hiện bằng `AuthenticationException`), `switchIfEmpty` không bắt lỗi và cũng không biến lỗi thành giá trị. Các lỗi kỹ thuật như timeout hoặc database unavailable cần được giám sát/xử lý theo chính sách hệ thống, không được tự động cho phép đăng nhập.

Đôi khi cần dự phòng cho nguồn tra cứu không có dữ liệu (ví dụ cache miss → database). Khi đó:

~~~java
Mono<VerifiedClaims> claims = cache.find(rawToken)
    .switchIfEmpty(Mono.defer(() -> database.find(rawToken)))
    .filter(VerifiedClaims::active)
    .switchIfEmpty(Mono.error(
        new BadCredentialsException("Invalid credentials")));
~~~

Chỉ dùng cơ chế cache/database trên nếu dữ liệu trả về đã được xác thực và cache không thể bị dùng để vượt qua kiểm tra token. Không chọn nguồn phụ có mức tin cậy thấp hơn để bỏ qua lỗi xác minh từ nguồn chính.

## 8. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `map(service::findUser)` khi service trả `Mono<User>` | Tạo `Mono<Mono<User>>` | `flatMap(service::findUser)` |
| Dùng `filter` rồi mặc định coi rỗng là hợp lệ | Có thể bỏ qua yêu cầu xác thực | Đặt `switchIfEmpty(Mono.error(...))` đúng vị trí |
| Nghĩ `switchIfEmpty` sẽ bắt `onError` | Lỗi vẫn truyền xuống | Tách rõ lỗi và rỗng; chỉ dùng `onErrorResume` khi có chính sách cụ thể |
| Dùng `block()` / `subscribe()` trong WebFlux handler | Chặn luồng hoặc tách xử lý ra khỏi vòng đời request | Trả thẳng `Mono` cho framework |
| Ánh xạ thành `null` trong `map` | Reactor không chấp nhận giá trị `null` | Dùng `Mono.justOrEmpty` / `mapNotNull` khi có chủ đích |
| Ghi log raw password/token | Lộ bí mật xác thực | Chỉ log mã lỗi, correlation ID và metadata an toàn |
| `switchIfEmpty(Mono.just(authenticatedFallback))` | Có thể tạo đăng nhập giả | Fallback xác thực phải tuân thủ chính sách; thường là lỗi |
| Dùng `filter` với lời gọi blocking đến database | Chặn event loop | Dùng reactive repository/client với `flatMap` hoặc `filterWhen` |

Với bước đồng bộ, chọn `map` hoặc `filter`. Với lời gọi trả publisher, chọn `flatMap`. Với trường hợp *không có phần tử*, chọn `switchIfEmpty` sau khi đã định nghĩa ý nghĩa của rỗng. Với lỗi xác thực, sử dụng tín hiệu lỗi và cơ chế xử lý lỗi của Spring Security đúng tầng.

## 9. Tự kiểm tra kiến thức

1. Nếu repository trả `Mono.empty()`, `map(User::getUsername)` có chạy không? **Không**; không có `onNext` để ánh xạ.
2. `filter(claim -> false)` có ném `BadCredentialsException` không? **Không**; nó tạo kết quả rỗng. Muốn lỗi, thêm `switchIfEmpty(Mono.error(...))`.
3. Vì sao `map(tokenService::verify)` có thể sai? Vì `verify` trả `Mono<Claims>`, `map` tạo publisher lồng; `flatMap` mới nối được kết quả.
4. Nếu `verify` trả `Mono.error(...)`, `switchIfEmpty` có chạy không? **Không**; đó là lỗi, không phải rỗng.
5. Trong `ReactiveAuthenticationManager`, `Mono.empty()` có luôn mang nghĩa sai mật khẩu? **Không**; theo hợp đồng interface, manager không xác định được kết quả. Sai thông tin xác thực của loại token manager hỗ trợ cần phát lỗi xác thực.
6. Có nên gọi `.block()` trong handler WebFlux để lấy principal? **Không**; giữ nguyên publisher và để framework subscribe.

## Tài liệu chính thức

- Project Reactor, API `Mono`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Spring Security, `ReactiveAuthenticationManager`: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/authentication/ReactiveAuthenticationManager.html
- Spring Security, phương thức reactive và Reactor Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
