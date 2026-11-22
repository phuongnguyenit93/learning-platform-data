# Phân biệt Mono.empty(), giá trị false và tín hiệu lỗi trong quyết định bảo mật

## Mục tiêu bài học

Sau bài này, bạn có thể: (1) đọc đúng các tín hiệu Reactor từ `Mono<Boolean>` và `Mono<AuthorizationDecision>`; (2) phân biệt “không có quyết định”, “quyết định từ chối” và “không thể ra quyết định vì lỗi”; (3) dùng các toán tử Reactor để xây dựng chính sách từ chối mặc định mà không che giấu sự cố; (4) kiểm thử riêng từng đường đi trước khi tích hợp vào Spring Security WebFlux.

Bài thuộc **Nền tảng Reactor** của **Spring Security - reactive**. Trọng tâm là ý nghĩa của tín hiệu bất đồng bộ tại ranh giới **ủy quyền (authorization)**. Xác thực (authentication: người dùng là ai) cung cấp danh tính; ủy quyền (authorization: người dùng có được làm việc này không) mới tạo quyết định cho một tài nguyên hay hành động.

## 1. Một `Mono` có ba kiểu kết thúc cần phân biệt

`Mono<T>` phát **tối đa một giá trị**. Khi có giá trị, nó phát `onNext(value)` rồi `onComplete()`; khi không có giá trị, nó chỉ phát `onComplete()`; khi lỗi, nó phát `onError(error)`. Đây là **tín hiệu** của luồng, không phải ba cách viết cùng một kết quả.

| Nguồn `Mono<Boolean>` | Chuỗi tín hiệu quan sát được | Ý nghĩa tại tầng dữ liệu |
| --- | --- | --- |
| `Mono.just(true)` | `onNext(true) → onComplete` | Có kết quả, giá trị là `true` |
| `Mono.just(false)` | `onNext(false) → onComplete` | Có kết quả, giá trị là `false` |
| `Mono.empty()` | `onComplete` | Hoàn tất bình thường nhưng **không phát giá trị** |
| `Mono.error(new IllegalStateException("unavailable"))` | `onError(IllegalStateException)` | Luồng thất bại; không có kết quả thành công |

**Điểm mấu chốt:** `false` là một **giá trị hợp lệ**; `empty` là **vắng mặt giá trị**; `error` là **một thất bại**. `Mono.just(null)` không phải cách biểu diễn “không có dữ liệu” (Reactor không cho phát `null` bằng `onNext`). Hãy dùng `Mono.empty()` hoặc một kiểu miền nghiệp vụ thể hiện rõ lý do vắng mặt.

Đừng nhầm `Mono<Void>` với `Mono<Boolean>`: một `Mono<Void>` hoàn tất rỗng thường biểu thị **tác vụ thành công nhưng không trả dữ liệu** (ví dụ ghi log xong). Trong khi đó, một `Mono<AuthorizationDecision>` rỗng nghĩa là **không phát đối tượng quyết định**. Ý nghĩa phụ thuộc vào **kiểu trả về và hợp đồng của hàm tiêu thụ**.

## 2. Diễn giải trong quyết định bảo mật

Xét một quy tắc “tài khoản A có được đọc tài liệu D không?”. Nếu API quy tắc trả `Mono<Boolean>`, bạn có thể quy ước rõ:

| Kết quả quy tắc | Cách diễn giải phù hợp | Hành động thiết kế |
| --- | --- | --- |
| `Mono.just(true)` | Quy tắc xác nhận được phép | Biểu diễn **ALLOW** |
| `Mono.just(false)` | Quy tắc xác nhận không được phép | Biểu diễn **DENY** |
| `Mono.empty()` | Quy tắc không trả phán quyết: không tìm thấy dữ liệu, không áp dụng hoặc `abstain` tùy hợp đồng | **Không tự coi là ALLOW**; xác định quy tắc dự phòng |
| `Mono.error(cause)` | Quy tắc không hoàn thành do lỗi dữ liệu, kết nối, lập trình, timeout… | Giữ lại lỗi để xử lý/ghi nhận phù hợp; không giả làm `false` hay `empty` |

Trong Spring Security reactive, `ReactiveAuthorizationManager` dùng kết quả kiểu `Mono<AuthorizationDecision>` (và trong API mới là `Mono<AuthorizationResult>`). Một `AuthorizationDecision(true)` và một `AuthorizationDecision(false)` là **hai quyết định tường minh**. Tài liệu API mô tả `Mono.empty()` tại phương thức ra quyết định là **không thể đưa ra quyết định**, thường gọi là `abstain`. Tuy vậy, điều **cuối cùng** xảy ra với yêu cầu phụ thuộc cách bộ quản lý, bộ ghép quy tắc và bộ lọc tiêu thụ kết quả; không được suy ra “rỗng thì tự động cho qua”. Các đường xử lý như `verify(...)` có hợp đồng khác: hoàn tất `Mono<Void>` khi ủy quyền thành công và phát lỗi khi bị từ chối.

Ở các phiên bản Spring Security 6.5, `ReactiveAuthorizationManager.check(...)` trả `Mono<AuthorizationDecision>` nhưng đã được đánh dấu deprecated để chuyển sang `authorize(...)` (được thêm từ 6.4). Với Spring Security 7, hãy theo chữ ký `authorize(...)` của phiên bản đang dùng. Điều quan trọng xuyên phiên bản là **phân biệt tín hiệu không có quyết định với quyết định từ chối**.

Ví dụ nghiệp vụ:

- **Có bản ghi quyền và `allowed=false`**: trả về quyết định **DENY**.
- **Không có bản ghi quyền**: tầng truy vấn có thể trả `Mono.empty()`; chính sách “không có quyền được cấp thì từ chối” phải **chuyển rỗng thành DENY một cách chủ ý**.
- **Cơ sở dữ liệu quyền mất kết nối**: phát `onError`; đừng biến thành “quyền không tồn tại” khi chưa xác định chính sách xử lý sự cố.

## 3. Các toán tử Reactor dễ làm đổi ý nghĩa bảo mật

| Toán tử | Khi có `false` | Khi `empty` | Khi `error` |
| --- | --- | --- | --- |
| `map(f)` | Gọi `f(false)` | Bỏ qua `f`, vẫn rỗng | Truyền tiếp lỗi |
| `defaultIfEmpty(false)` | Giữ `false` | Phát `false` | Truyền tiếp lỗi |
| `switchIfEmpty(fallback)` | Không chạy fallback | Chạy fallback | Không chạy fallback, truyền lỗi |
| `onErrorResume(fallback)` | Giữ `false` | Giữ rỗng | Chạy fallback xử lý lỗi |
| `filter(Boolean::booleanValue)` | **Biến thành rỗng** | Vẫn rỗng | Truyền lỗi |
| `hasElement()` | Phát `true` vì **có một phần tử** | Phát `false` | Truyền lỗi |

Từ bảng trên có bốn bẫy thường gặp:

1. `defaultIfEmpty(true)` hoặc `switchIfEmpty(Mono.just(true))` biến việc **thiếu dữ liệu quyền** thành cho phép truy cập (**fail-open**). Tránh cấu hình này cho tài nguyên mặc định phải được bảo vệ.
2. `filter(Boolean::booleanValue)` hoặc `filterWhen(...)` có thể loại bỏ phần tử `false`, để kết quả chỉ còn `empty`. Khi ấy tầng sau không còn phân biệt “đã từ chối” với “chưa có quyết định”.
3. `hasElement()` trên `Mono.just(false)` trả `true`. Dùng nó để kiểm tra “được phép hay không” sẽ cho kết quả sai: toán tử hỏi **có phần tử không**, không hỏi **phần tử có giá trị true không**.
4. `onErrorComplete()` hoặc `onErrorResume(e -> Mono.empty())` có thể đổi lỗi hạ tầng thành `abstain`. Nếu tầng ghép chính sách sau đó chấp nhận kết quả rỗng, hệ thống có thể vượt qua kiểm tra. `onErrorReturn(true)` còn nguy hiểm hơn vì cấp quyền trực tiếp khi lỗi.

`Mono.zip(permissionA, permissionB)` cũng cần chú ý: nếu một nhánh kết thúc rỗng trước khi có giá trị, phép ghép không có đủ giá trị để tạo tuple và có thể hoàn tất rỗng. Nếu chính sách cần hai kết quả tường minh, chuẩn hóa **cả hai nguồn** về `true/false` ở đúng ranh giới dữ liệu trước khi ghép.

## 4. Thiết kế quy tắc từ chối mặc định (fail-closed)

Giả sử kho quyền cung cấp:

```java
// Mảnh mã minh họa: permissionService do ứng dụng cung cấp.
// Không phải chương trình Java độc lập.
Mono<Boolean> raw = permissionService.canRead(userId, documentId);
```

Hợp đồng của `canRead` cần được viết rõ: `true` nếu có quyền; `false` nếu kiểm tra quyền hoàn tất và bị từ chối; `empty` nếu không có bản ghi quyền; `error` nếu việc kiểm tra thất bại. Khi áp dụng chính sách “không có bản ghi thì không có quyền”:

```java
Mono<Boolean> allowed = permissionService.canRead(userId, documentId)
        .defaultIfEmpty(false);
```

Kết quả sau biến đổi là **true → true, false → false, empty → false, error → error**. Đó là lựa chọn có chủ đích: **thiếu dữ liệu quyền** được quy về **từ chối**; **sự cố hạ tầng** vẫn là lỗi để tầng xử lý có thể phản hồi theo chính sách vận hành và lưu bằng chứng.

Để biểu diễn kết quả cho Spring Security:

```java
// Mảnh mã cho ngữ cảnh dùng AuthorizationDecision.
Mono<AuthorizationDecision> decision =
        permissionService.canRead(userId, documentId)
                .map(AuthorizationDecision::new)
                .defaultIfEmpty(new AuthorizationDecision(false));
```

Chỉ định nguồn `empty` là “không có bản ghi” **khi đó là hợp đồng thật** của kho quyền. Nếu nguồn trả rỗng với nghĩa “quy tắc không áp dụng” (abstain) để một quy tắc khác quyết định, không tự động ép nó thành `false` tại tầng quá sớm. Hãy xác định chính sách kết hợp các quy tắc, sau đó đặt **một quyết định mặc định từ chối** tại điểm tổng hợp cuối cùng khi nghiệp vụ yêu cầu.

Nếu sự cố hạ tầng cần chuyển thành **DENY** thay vì để lỗi lan lên, giới hạn việc bắt lỗi vào đúng loại lỗi đã nhận diện, ghi nhận sự cố và tuyệt đối không chuyển thành **ALLOW**. Ví dụ dưới đây chỉ là chính sách tùy chọn đã được duyệt, không phải mặc định của Reactor:

```java
Mono<Boolean> allowed = permissionService.canRead(userId, documentId)
        .defaultIfEmpty(false)
        .onErrorResume(PermissionServiceUnavailableException.class, error -> {
            audit.recordPermissionCheckFailure(userId, documentId, error);
            return Mono.just(false);
        });
```

Ở mảnh mã trên, `PermissionServiceUnavailableException` và `audit` là thành phần do ứng dụng tự định nghĩa. Việc chuyển lỗi thành `false` có thể thay đổi mã HTTP và che sự cố khỏi các chỉ số nếu bỏ ghi nhận. Luôn cân nhắc khả năng phân biệt “bị cấm” và “hệ thống không thể kiểm tra”.

## 5. Ví dụ Java chạy được: thấy bốn kết quả trên cùng một pipeline

Ví dụ sau chỉ cần Reactor Core; không phụ thuộc Spring Security. Nó cố ý biến cả bốn trạng thái thành chuỗi để **in chẩn đoán**. Nhánh `onErrorResume` trong chương trình in này **không phải** mẫu policy cấp quyền.

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.7.0'
}

application {
    mainClass = 'SecuritySignalsDemo'
}
```

Tạo `src/main/java/SecuritySignalsDemo.java`:

```java
import reactor.core.publisher.Mono;

public class SecuritySignalsDemo {
    public static void main(String[] args) {
        print("true", Mono.just(true));
        print("false", Mono.just(false));
        print("empty", Mono.empty());
        print("error", Mono.error(
                new IllegalStateException("permission store unavailable")));
    }

    private static void print(String name, Mono<Boolean> source) {
        // Chỉ để quan sát tín hiệu, không dùng để quyết định HTTP.
        String description = source
                .map(allowed -> allowed ? "ALLOW" : "DENY")
                .switchIfEmpty(Mono.just("ABSTAIN"))
                .onErrorResume(error ->
                        Mono.just("ERROR:" + error.getClass().getSimpleName()))
                .block();

        System.out.println(name + " -> " + description);
    }
}
```

Chạy từ thư mục dự án bằng `gradle run --quiet` (hoặc `./gradlew run --quiet` khi đã có Gradle Wrapper). Với JDK 17+ và các phụ thuộc được tải thành công, stdout là:

```text
true -> ALLOW
false -> DENY
empty -> ABSTAIN
error -> ERROR:IllegalStateException
```

**Giải thích:** `map` hoạt động với cả `true` lẫn `false` vì cả hai đều có `onNext`; `switchIfEmpty` chỉ khởi động với `empty`; `onErrorResume` chỉ xử lý `error`. `block()` chỉ xuất hiện trong ví dụ `main` độc lập để quan sát kết quả; **không dùng `block()` trong luồng request WebFlux** vì có thể chặn thread xử lý phản ứng.

Thử thay `.switchIfEmpty(Mono.just("ABSTAIN"))` bằng `.defaultIfEmpty("DENY")` để thấy trường hợp rỗng được quy về từ chối, còn lỗi vẫn đến nhánh `onErrorResume`.

## 6. Tích hợp với ReactiveAuthorizationManager

Trong Spring Security WebFlux, một `ReactiveAuthorizationManager<AuthorizationContext>` có thể kiểm tra `Authentication` và thông tin yêu cầu để phát một quyết định. Đoạn dưới đây minh họa **chữ ký `check(...)` của Spring Security 6.5**, vốn là API đã deprecated tại phiên bản này; các bản mới chuyển sang `authorize(...)` và kiểu `AuthorizationResult`. Đây là **mảnh tích hợp**, cần các dependency Spring Security WebFlux và `PermissionService` của ứng dụng:

```java
import org.springframework.security.authentication.*;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import reactor.core.publisher.Mono;

final class DocumentReadManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final PermissionService permissions;

    DocumentReadManager(PermissionService permissions) {
        this.permissions = permissions;
    }

    @Override
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication, AuthorizationContext context) {

        String path = context.getExchange().getRequest().getPath().value();

        return authentication
                .flatMap(auth -> permissions.canRead(auth.getName(), path))
                .map(AuthorizationDecision::new)
                .defaultIfEmpty(new AuthorizationDecision(false));
    }
}

// Hợp đồng ví dụ: không có bản ghi quyền -> Mono.empty();
// kho quyền lỗi -> Mono.error(...); có bản ghi -> Mono.just(true/false).
interface PermissionService {
    Mono<Boolean> canRead(String principalName, String resourcePath);
}
```

Diễn biến:

1. `authentication` phát một `Authentication` → truy vấn quyền, phát `AuthorizationDecision(true/false)` nếu có kết quả.
2. `authentication` không phát giá trị, hoặc kho quyền kết thúc `empty` → `defaultIfEmpty` tạo `AuthorizationDecision(false)`.
3. Kho quyền phát lỗi → `flatMap` và `map` không biến nó thành một quyết định; lỗi đi tiếp đến tầng xử lý của ứng dụng/framework.

Chú ý `Authentication` có thể đại diện người dùng ẩn danh tùy chuỗi filter. Không chỉ kiểm tra `isAuthenticated()` rồi mặc định suy ra đã đăng nhập thật: ứng dụng phải áp dụng các quy tắc xác thực/ẩn danh thích hợp. Mã trên bảo vệ bằng việc yêu cầu kho quyền trả **quyết định cấp quyền rõ ràng**. Nếu không có bằng chứng cấp quyền, nó từ chối.

**HTTP 401, 403 và lỗi máy chủ là bước xử lý khác:** `Mono.just(false)` ở đây không tự tạo response 403; Spring Security chuyển quyết định từ chối thành luồng xử lý truy cập bị chặn, rồi bộ lọc/entry point quyết định phản hồi. Tùy tình trạng authentication và cấu hình, yêu cầu chưa xác thực có thể kích hoạt 401 hoặc cơ chế đăng nhập; người đã xác thực nhưng thiếu quyền thường nhận 403. `Mono.error(...)` do kho quyền mất kết nối không mặc nhiên có cùng ý nghĩa với `AccessDeniedException`; nếu chưa có nhánh xử lý riêng, đó có thể là lỗi 5xx. Vì thế không đồng nhất **tín hiệu Reactor**, **quyết định policy** và **HTTP status**.

## 7. Ba tình huống thực tế và cách ra quyết định

**Tình huống A — chưa được cấp quyền.** Database trả không có dòng ACL cho `(user, document)`. Nếu API trả `Mono.empty()`, rule chỉ định `defaultIfEmpty(false)` tại ranh giới kho quyền. Kết quả cuối là **DENY**; việc thiếu dòng quyền không trở thành quyền truy cập.

**Tình huống B — ACL có dòng `allow=false`.** API trả `Mono.just(false)`. Rule ghi nhận **từ chối tường minh**; không chạy `switchIfEmpty`. Nếu mã dùng `filter(Boolean::booleanValue)` trước khi audit thì `false` có thể bị chuyển thành rỗng, khiến mất thông tin “đã từ chối”.

**Tình huống C — dịch vụ ACL bị timeout.** API trả `Mono.error(TimeoutException)`. `defaultIfEmpty(false)` **không** bắt lỗi này. Cơ chế báo lỗi/giám sát nhận nguyên nhân, còn việc trả 5xx hay từ chối tường minh theo chính sách khắc phục phải được định nghĩa. Không dùng `onErrorReturn(true)`. Chỉ dùng chuyển lỗi sang `false` khi đó là policy đã cân nhắc, đồng thời bảo đảm đo đạc và kiểm tra hậu quả.

Một tình huống thứ tư rất khác: **quy tắc không áp dụng**. Ví dụ một manager chỉ đánh giá tài nguyên thuộc nhóm “document”, còn tài nguyên thuộc nhóm khác do manager khác quản lý. Nếu hợp đồng kết hợp chấp nhận `abstain`, manager có thể trả `Mono.empty()` để nhường quyết định. Khi không có manager nào cấp quyền, cần có quy tắc chặn cuối; không cho truy cập chỉ vì tất cả đều không phát quyết định.

## 8. Kiểm thử từng đường tín hiệu, không chỉ kiểm thử status

Với `reactor-test` (thêm `testImplementation 'io.projectreactor:reactor-test:3.7.0'` cho ví dụ Gradle ở trên), `StepVerifier` kiểm tra tín hiệu gốc chính xác:

```java
// Mảnh mã dùng trong test JUnit/StepVerifier; cần import Mono, StepVerifier.
StepVerifier.create(Mono.just(false))
        .expectNext(false)
        .verifyComplete(); // Có giá trị false.

StepVerifier.create(Mono.<Boolean>empty())
        .verifyComplete(); // Không có onNext.

StepVerifier.create(
        Mono.<Boolean>error(new IllegalStateException("ACL down")))
        .expectError(IllegalStateException.class)
        .verify(); // Có onError, không phải empty.

StepVerifier.create(
        Mono.<Boolean>empty().defaultIfEmpty(false))
        .expectNext(false)
        .verifyComplete(); // Quy tắc fallback đã đổi empty thành deny.
```

Khi kiểm thử tích hợp WebFlux, thiết kế tối thiểu bốn ca: có quyền, bị từ chối rõ ràng, không có bản ghi quyền, dịch vụ quyền lỗi. Kiểm tra **đường đi của quyết định, side effect và phản hồi HTTP** riêng; dùng `WebTestClient` với security chain thực thay vì suy đoán mã HTTP từ một `Mono` đơn lẻ. Nếu có nhiều manager, bổ sung ca **tất cả đều abstain** và **một manager abstain, manager khác deny/allow** theo quy tắc kết hợp đã định nghĩa.

## 9. Những lỗi thường gặp

- **Đọc `false` như `empty`:** `switchIfEmpty` không chạy khi `Mono.just(false)` có giá trị. Viết test cho cả hai.
- **Dùng `hasElement()` để cấp quyền:** `Mono.just(false).hasElement()` phát `true` vì có phần tử. Muốn biết giá trị Boolean, hãy kiểm tra chính giá trị đó.
- **Dùng `filter(Boolean::booleanValue)` sớm:** nó loại quyết định deny, dễ gây sai ở tầng fallback/audit.
- **Mặc định cho phép khi thiếu dữ liệu:** `defaultIfEmpty(true)` có thể tạo lỗ hổng khi kho quyền không chứa dòng cần thiết.
- **Nuốt lỗi bằng `onErrorComplete()`:** lỗi bị đổi thành tín hiệu rỗng; việc truy cập tiếp theo phụ thuộc một fallback có thể thiếu an toàn.
- **Đổi mọi lỗi thành 403:** che giấu lỗi kết nối, hỏng dịch vụ hoặc bug; vận hành không biết vì sao bị từ chối.
- **Đánh đồng `Mono<Void>` với kết quả authorization rỗng:** hai kiểu API mang hợp đồng khác nhau.
- **Tin rằng HTTP 401/403 suy ra trực tiếp từ `Mono`:** các filter, exception handler, anonymous authentication và cấu hình quyết định HTTP cuối cùng.
- **Gọi `block()` trong request reactive:** làm mất tính nonblocking và có thể làm nghẽn luồng xử lý.

## 10. Quy tắc ghi nhớ và câu hỏi tự kiểm tra

Khi đọc một luồng kiểm tra quyền, tự hỏi theo thứ tự:

1. **Publisher trả kiểu gì?** `Mono<Boolean>`, `Mono<AuthorizationDecision>` hay `Mono<Void>`?
2. **Có phát `onNext` không?** Nếu có, giá trị là `true` hay `false`? Nếu không, đó là `onComplete` rỗng hay `onError`?
3. **`empty` mang ý nghĩa nào theo hợp đồng nguồn?** Không có dữ liệu, abstain hay hoàn tất tác vụ không cần giá trị?
4. **Toán tử nào đổi tín hiệu?** `filter`, `defaultIfEmpty`, `switchIfEmpty`, `onErrorResume`, `zip` có làm mất phân biệt không?
5. **Ai quyết định cuối cùng?** Quy tắc, manager kết hợp, Spring Security filter hay HTTP exception handler?
6. **Đã kiểm thử đủ bốn đường?** Allow, deny, empty và error.

**Tự kiểm tra:** Với `Mono.just(false).switchIfEmpty(Mono.just(true))`, kết quả là gì? **`false`**, vì publisher đã có phần tử. Với `Mono.<Boolean>empty().defaultIfEmpty(false)`? **`false`** do fallback. Với `Mono.<Boolean>error(new IllegalStateException()).defaultIfEmpty(false)`? **`onError(IllegalStateException)`**, vì lỗi không phải tín hiệu hoàn tất rỗng.

**Ghi nhớ cuối:** `false` = **có quyết định từ chối**; `empty` = **không có giá trị/quyết định phát ra**; `error` = **không thể hoàn thành kiểm tra**. Hệ thống bảo mật an toàn cần hợp đồng rõ cho từng trạng thái, một điểm quyết định mặc định từ chối phù hợp và kiểm thử đường lỗi độc lập.

## Tài liệu tham khảo

- [Project Reactor — Mono, an Asynchronous 0–1 Result](https://projectreactor.io/docs/core/release/reference/coreFeatures/mono.html) — mô hình `onNext`, `onComplete`, `onError`.
- [Spring Security 6.5 — ReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html) — `check`, `authorize`, `verify` và khái niệm không có quyết định.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html) — custom reactive authorization, `Mono<Boolean>` và `abstain`.
- [Reactor Core — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html) — ngữ nghĩa các toán tử thay đổi đường tín hiệu.
