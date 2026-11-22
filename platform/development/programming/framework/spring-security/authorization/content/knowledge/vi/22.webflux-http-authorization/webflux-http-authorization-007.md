# Kết hợp quyết định bằng toán tử Reactor mà không cấp quyền ngoài dự kiến

## 1. Bối cảnh: kết hợp nhiều quy tắc trong HTTP WebFlux

Trong Spring Security WebFlux, một endpoint có thể cần nhiều điều kiện cùng đúng trước khi trả tài liệu:

- Caller đã được xác thực và có authority `DOC_READ`.
- Caller được phép làm việc trong tenant của tài liệu.
- Caller là owner **hoặc** có chia sẻ READ hợp lệ.
- Tài liệu không ở trạng thái bị khóa.
- PDP bên ngoài, nếu là guard bắt buộc, phải trả PERMIT hợp lệ.

Ở lập trình đồng bộ, ta có thể thấy một biểu thức Boolean:

```java
boolean allowed =
        hasReadAuthority
        && tenantAllowed
        && (ownerAllowed || shareAllowed)
        && !documentLocked
        && remotePolicyPermitted;
```

Trong WebFlux, mỗi điều kiện có thể được tính bất đồng bộ bằng `Mono<Boolean>` hoặc `Mono<AuthorizationResult>`. Việc chuyển biểu thức trên thành các chuỗi `zip`, `flatMap`, `filter`, `switchIfEmpty`, `all`, `any` và `onErrorResume` **không chỉ là thay cú pháp**: Reactor phân biệt giá trị, hoàn tất rỗng và lỗi. Viết sai có thể biến **không nhận được quyết định** thành **được phép**.

Bài học này tập trung vào cách kết hợp quyết định trên HTTP WebFlux, dùng đúng `ReactiveAuthorizationManager`, chuẩn hóa các nhánh thành quyết định tường minh, phân biệt AND/OR và tránh fallback nguy hiểm. Các đoạn Java 17 được phân loại thành **chương trình Maven chạy được** và **snippet tích hợp Spring Security**.

### Kết quả cần đạt

1. Hiểu `Mono.just(true)`, `Mono.just(false)`, `Mono.empty()` và `Mono.error(...)` khác nhau.
2. Biết khi nào dùng `zip`, `flatMap`, `Flux.all` và `Flux.any` cho quyền bắt buộc hoặc thay thế.
3. Biết tránh `filter(...).switchIfEmpty(permit)`, `thenReturn(true)` và `hasElement()`.
4. Không để một nhánh empty/error/timeout/abstain mở quyền.
5. Biết cách nối logic vào `ServerHttpSecurity.authorizeExchange(...).access(...)`.
6. Biết cách test tổ hợp với `StepVerifier` và kiểm thử filter chain WebFlux.
7. Giữ nguyên tenant, caller, resource, action và context khi thay đổi Scheduler/subscription.

## 2. Bốn tín hiệu cần phân biệt của Mono

`Mono<T>` phát **tối đa một giá trị** hoặc hoàn tất rỗng, hoặc kết thúc với lỗi. Với quyết định Boolean:

| Publisher | Tín hiệu | Ý nghĩa nên dùng trong authorization |
| --- | --- | --- |
| `Mono.just(true)` | `onNext(true)` rồi `onComplete` | Điều kiện này cấp quyền |
| `Mono.just(false)` | `onNext(false)` rồi `onComplete` | Điều kiện này từ chối |
| `Mono.empty()` | Chỉ `onComplete` | Không có quyết định / thiếu dữ liệu cần thiết |
| `Mono.error(ex)` | `onError(ex)` | Không thể đánh giá hoặc có lỗi hạ tầng |
| `Mono.never()` | Không có tín hiệu kết thúc | Có thể treo nếu không đặt timeout |

**Không có `onNext` khác với `onNext(false)`.** Đây là điểm then chốt của Reactive Streams. Spring Security `ReactiveAuthorizationManager.authorize(...)` có thể trả một quyết định hoặc `Mono.empty()` khi manager không đưa ra quyết định; do đó không thể coi empty là GRANT một cách tùy tiện.

Ví dụ:

```java
Mono<Boolean> permit = Mono.just(true);
Mono<Boolean> deny = Mono.just(false);
Mono<Boolean> undecided = Mono.empty();
Mono<Boolean> failed = Mono.error(
        new IllegalStateException("Policy service unavailable"));
```

`null` không phải giá trị hợp lệ của `Mono.just(null)`; Mono không phát null theo Reactive Streams. Đừng dùng `Boolean` null như trạng thái thứ ba trong một publisher. Nếu cần phân biệt deny, abstain và lỗi vận hành, dùng một kiểu domain rõ như enum/record, không ép tất cả về Boolean quá sớm.

### Quyết định trong Spring Security

Trong Spring Security 6.5, `ReactiveAuthorizationManager<T>` có:

```java
Mono<AuthorizationResult> authorize(
        Mono<Authentication> authentication, T object);
```

Giao diện 6.5 vẫn có `check(...)` trả `Mono<AuthorizationDecision>` và được đánh dấu deprecated để chuyển sang `authorize(...)`. Một số class/library có thể còn dùng `check`; khi nâng cấp Spring Security 7.x cần kiểm tra lại API, không sao chép mã giữa hai major versions mà không biên dịch.

`AuthorizationResult.isGranted()` là boolean **khi đã có result**. Nếu upstream `Mono<AuthorizationResult>` empty, gọi `map(AuthorizationResult::isGranted)` cũng cho Mono rỗng, chứ **không** sinh false.

## 3. Viết biểu thức policy trước rồi mới chọn toán tử

Giả sử endpoint GET:

```text
/tenants/{tenantId}/documents/{documentId}
```

Policy yêu cầu:

```text
ALLOW =
    AUTHENTICATED
    AND DOC_READ_AUTHORITY
    AND TENANT_MEMBERSHIP_VALID
    AND RESOURCE_BELONGS_TO_TENANT
    AND (OWNER_READ OR SHARED_READ)
    AND NOT_LOCKED
    AND PDP_PERMIT_VALID
```

Đây là **AND giữa các nhóm điều kiện bắt buộc**, có duy nhất một **OR được chủ đích** giữa hai cách nhận quyền đọc. Nếu viết:

```java
boolean allowed = hasReadAuthority || tenantAllowed;
```

là sai: một caller có authority nhưng không thuộc tenant vẫn được đọc, hoặc caller thuộc tenant nhưng không có DOC_READ cũng được đọc.

Một biểu thức đẹp về mặt Reactor vẫn có thể sai chính sách. Viết truth table nghiệp vụ trước:

| DOC_READ | Tenant hợp lệ | Owner | Shared | Resource unlocked | Remote permit | ALLOW |
| --- | --- | --- | --- | --- | --- | --- |
| true | true | true | false | true | true | true |
| true | true | false | true | true | true | true |
| true | false | true | true | true | true | **false** |
| false | true | true | true | true | true | **false** |
| true | true | false | false | true | true | **false** |
| true | true | true | false | false | true | **false** |
| true | true | true | false | true | false | **false** |
| true | true | true | false | true | **PDP empty/error** | **false / unavailable** |

Không để `OR` giữa các nhánh là guard bắt buộc. Với admin override, nếu có, phải là một rule riêng đã được policy xác định, không phải một `.onErrorReturn(true)` hoặc `.switchIfEmpty(allowAll)`.

## 4. Chuẩn hóa từng nhánh: empty và error không được thành true

Một helper fail-closed cho ví dụ:

```java
static Mono<Boolean> denyOnMissingOrError(Mono<Boolean> check) {
    return check
            .defaultIfEmpty(false)
            .onErrorReturn(false);
}
```

Ý nghĩa:

- `true` giữ nguyên true.
- `false` giữ nguyên false.
- `Mono.empty()` trở thành false.
- `Mono.error(...)` trở thành false.

Điều này **không đánh giá lỗi PDP là quyết định DENY của chính sách**; nó chỉ bảo đảm downstream không nhận true. Ở production, nên giữ typed reason code `POLICY_DENY`, `NO_DECISION`, `TIMEOUT`, `BACKEND_ERROR`, ghi metrics, và chỉ ánh xạ ra Boolean ở enforcement boundary.

Với Spring Security:

```java
Mono<AuthorizationResult> result = remoteManager
        .authorize(authentication, authorizationContext)
        .defaultIfEmpty(new AuthorizationDecision(false))
        .onErrorReturn(new AuthorizationDecision(false));
```

Đây là **snippet tích hợp**. Cần dùng đúng `Authentication` và `AuthorizationContext` do framework cung cấp. Nếu một lỗi cần trả HTTP 503 thay vì 403, dùng typed exception/handler ở đúng filter/service boundary; vẫn không cho protected action chạy.

**Không áp dụng một fallback cho phép** như:

```java
// SAI: không có quyết định hoặc policy service lỗi lại cấp quyền.
mono.defaultIfEmpty(true);
mono.onErrorReturn(true);
```

Với các guard độc lập, đặt fail-closed normalization **trước khi kết hợp** để mọi nhánh luôn phát một quyết định Boolean xác định.

## 5. Mono.zip: chỉ chạy combiner khi từng nguồn có giá trị

`Mono.zip(a,b)` chờ **mỗi Mono cung cấp một giá trị** rồi phát tuple. Nếu một nguồn hoàn tất rỗng, kết quả zip có thể hoàn tất rỗng và hủy các nguồn còn lại; nếu một nguồn lỗi, zip phát lỗi và hủy các nguồn phù hợp.

Ví dụ chưa an toàn:

```java
Mono<Boolean> authority = Mono.just(true);
Mono<Boolean> membership = Mono.empty();

Mono<Boolean> combined = Mono.zip(authority, membership)
        .map(pair -> pair.getT1() && pair.getT2());

// combined = Mono.empty(), không phát false.
```

Một developer có thể thêm đoạn nguy hiểm:

```java
// SAI: cho phép khi zip không phát giá trị.
Mono<Boolean> allowed = combined.defaultIfEmpty(true);
```

Với membership `Mono.empty()`, biến `allowed` bây giờ phát **true**. Đây là “empty-to-permit” rất dễ bỏ sót.

### Mẫu an toàn

```java
Mono<Boolean> allowed = Mono.zip(
        authority.defaultIfEmpty(false),
        membership.defaultIfEmpty(false))
    .map(pair -> pair.getT1() && pair.getT2())
    .onErrorReturn(false);
```

Nếu authority=true nhưng membership rỗng, zip vẫn nhận hai Boolean (true và false) và phát false. Nếu một nhánh lỗi, pipeline không được đi tiếp với PERMIT.

**Không zip `Mono<Void>` như một nguồn cung cấp quyết định:** `Mono<Void>` hoàn tất mà không phát giá trị, do đó một zip cần phần tử từ nguồn đó có thể không bao giờ gọi combinator.

### Khi cần nhiều điều kiện

```java
Mono<Boolean> allowed = Mono.zip(
        denyOnMissingOrError(authority),
        denyOnMissingOrError(tenant),
        denyOnMissingOrError(resource))
    .map(t -> t.getT1() && t.getT2() && t.getT3());
```

Tùy thiết kế, có thể chọn `flatMap` tuần tự để không gọi PDP nếu authority/tenant đã deny. Đừng chạy một kiểm tra remote chứa dữ liệu nhạy cảm trước khi biết caller có quyền vào tenant.

## 6. flatMap: điều kiện phụ thuộc nên chạy tuần tự và fail closed

Một số checks phải phụ thuộc nhau. Ví dụ chỉ truy vấn owner khi tenant membership hợp lệ:

```java
Mono<Boolean> permission = authorityCheck
        .defaultIfEmpty(false)
        .flatMap(authorityOk -> {
            if (!authorityOk) {
                return Mono.just(false);
            }

            return tenantCheck
                    .defaultIfEmpty(false)
                    .flatMap(tenantOk -> {
                        if (!tenantOk) {
                            return Mono.just(false);
                        }

                        return ownerOrShareCheck
                                .defaultIfEmpty(false);
                    });
        })
        .onErrorReturn(false);
```

`flatMap` chỉ gọi function nếu upstream **phát giá trị**. Nếu upstream empty và bạn quên `defaultIfEmpty(false)`, phần bên trong **không chạy**, kết quả có thể tiếp tục empty.

Phân biệt:

- `zip`: các nhánh độc lập có thể được đăng ký song song (nhưng cần normalize).
- `flatMap`: các bước có dependency, short-circuit theo kết quả; phù hợp khi cần kiểm tra tenant trước khi truy vấn ACL.
- `Mono.defer`: tạo publisher tại lúc subscription, hữu ích với identity/attributes/clock/policy version thay đổi; không xác thực được input tự nó.
- `map`: chuyển đổi giá trị đồng bộ; không dùng `map` trả về `Mono<Mono<Boolean>>` rồi tưởng đã flatten.

### Đừng gọi `block()` giữa reactive chain

```java
// SAI trên WebFlux event loop: có thể block và gây nghẽn.
boolean allowed = policyService.checkAccess(request).block();
```

Giữ pipeline reactive: trả `Mono<AuthorizationResult>` và để framework subscribe. Nếu adapter thật bắt buộc dùng blocking JDBC/HTTP cũ, cô lập đúng scheduler dành cho blocking và kiểm thử context, timeout; ưu tiên driver reactive khi phù hợp.

## 7. filter + switchIfEmpty: bẫy biến DENY thành fallback

`filter(predicate)` sẽ biến một `Mono.just(value)` thành empty nếu predicate không đạt. Điều đó rất hữu ích cho tìm kiếm, nhưng nguy hiểm cho authorization.

Phản ví dụ:

```java
Mono<Boolean> allowed = policyDecision
        .filter(Boolean::booleanValue)
        .switchIfEmpty(Mono.just(true));
```

Nếu `policyDecision` phát false, `filter` loại bỏ nó. `switchIfEmpty` thấy empty và phát **true**. Nghĩa là một DENY thực bị đổi thành PERMIT.

Cách đúng:

```java
Mono<Boolean> allowed = policyDecision
        .defaultIfEmpty(false)
        .onErrorReturn(false);
```

Nếu dùng `filter` để chọn những yêu cầu được phép trong một luồng nghiệp vụ, vẫn cần branch **deny tường minh** và không được dùng fallback cho phép khi empty. Không dùng `switchIfEmpty` như cách “thử policy khác” nếu không có OR policy hợp lệ.

### switchIfEmpty hợp lệ khi nào?

Trong API authorization có thể có fallback **cũng là một quyết định từ chối**:

```java
Mono<AuthorizationResult> safe = policy
        .authorize(authentication, context)
        .switchIfEmpty(
                Mono.just(new AuthorizationDecision(false)));
```

Hoặc có một chính sách **thay thế** được thiết kế và kiểm thử rõ (ví dụ owner OR shared) thì tính kết quả từ hai checks, thay vì coi thiếu quyết định của check A là dấu hiệu được phép bỏ qua nó.

## 8. Flux.all và Flux.any: đừng quên tập rỗng

Với `Flux<Boolean>`:

- `all(Boolean::booleanValue)` trả true nếu **mọi phần tử đều true**.
- `any(Boolean::booleanValue)` trả true nếu **ít nhất một phần tử true**.

Đối với tập rỗng:

```java
Flux.<Boolean>empty()
        .all(Boolean::booleanValue); // Mono.just(true)

Flux.<Boolean>empty()
        .any(Boolean::booleanValue); // Mono.just(false)
```

Điều này đúng về logic: mệnh đề “mọi phần tử đều đúng” trên tập rỗng là true (*vacuous truth*). Nhưng trong authorization, một list **chính sách bắt buộc bị thiếu** không phải bằng chứng tất cả policy đã thành công.

### Guard khi phải có ít nhất một check

```java
static Mono<Boolean> requireAll(List<Mono<Boolean>> checks) {
    if (checks.isEmpty()) {
        return Mono.just(false);
    }

    return Flux.fromIterable(checks)
            .concatMap(ReactivePolicyLab::safe)
            .all(Boolean::booleanValue);
}
```

Đoạn này thuộc project demo mục 12, `ReactivePolicyLab.safe` là helper chuyển empty/error thành false. `concatMap` giữ thứ tự nguồn trong ví dụ; nó vẫn đăng ký toàn bộ checks cho đến khi `all` gặp false hoặc hết. Nếu policy bắt buộc phải đánh giá đầy đủ cho audit, cần thiết kế khác thay vì trông chờ một toán tử vốn có thể short-circuit.

Với yêu cầu **ít nhất một quyền**, `any` có ý nghĩa:

```java
Mono<Boolean> hasAny = Flux.just(
        true, false, false)
        .any(Boolean::booleanValue); // true
```

Nhưng đừng biến “ít nhất một nhánh grant” thành quyền vượt tenant. Một trong hai cách grant owner/share là **một nhóm OR đã định nghĩa**; điều kiện tenant, authentication và resource vẫn phải AND bên ngoài.

### Flux.empty khi một service trả không có permission

Một `Flux<Permission>` rỗng có thể là “user không có quyền” hoặc “PIP không trả được dữ liệu”. Đừng dùng `.all(permission -> ...)` rồi nhận true chỉ vì không có permission nào. Nếu nghiệp vụ đòi một tập permission không rỗng, kiểm tra cardinality trước.

## 9. hasElement và hasElements không phải kiểm tra GRANT

`Mono.hasElement()` chỉ nói một Mono có phát giá trị hay không:

```java
Mono.just(false).hasElement(); // Mono.just(true)
Mono.empty().hasElement();     // Mono.just(false)
```

Nó **không** trả “decision có isGranted=true hay không”. Tương tự `Flux.hasElements()` chỉ phát hiện có ít nhất một item.

Phản ví dụ:

```java
// SAI: một Mono<AuthorizationResult> DENY cũng có phần tử.
Mono<Boolean> allowed = manager
        .authorize(authentication, context)
        .hasElement();
```

Đúng phải đọc `AuthorizationResult.isGranted()`:

```java
Mono<Boolean> allowed = manager
        .authorize(authentication, context)
        .map(AuthorizationResult::isGranted)
        .defaultIfEmpty(false)
        .onErrorReturn(false);
```

Không dùng `.count().map(count -> count > 0)` làm phép kiểm tra quyền: một DENY vẫn được đếm thành một giá trị.

## 10. then, when và Mono<Void> có thể làm mất quyết định

Các toán tử `then()`/`thenReturn(x)` chủ động **bỏ giá trị upstream** và chỉ quan tâm completion thành công (hoặc lỗi).

Phản ví dụ:

```java
Mono<Boolean> allowed = policyCheck
        .thenReturn(true); // SAI: upstream false vẫn complete bình thường.
```

Một `Mono.just(false)` hoàn tất thành công, `thenReturn(true)` phát true. Tương tự:

```java
Mono<Boolean> allowed = Mono.when(
        roleCheck.then(),
        tenantCheck.then())
    .thenReturn(true);
```

`Mono.when` chờ những publishers hoàn tất, nhưng kết quả Boolean của `roleCheck`/`tenantCheck` đã bị bỏ. **Deny=false không phải error**, nên hai nguồn false vẫn complete và đoạn trên có thể phát true.

Sử dụng `zip`/`flatMap` để kết hợp giá trị thực của quyết định. `Mono.when` hữu ích cho những side-effect operations cần đợi completion; nó không thay công thức authorization.

### Tránh onErrorComplete ở policy guard

```java
// SAI nếu downstream có switchIfEmpty(Mono.just(true)).
Mono<Boolean> allowed = pdpCheck
        .onErrorComplete()
        .switchIfEmpty(Mono.just(true));
```

`onErrorComplete` biến lỗi thành completion rỗng; nếu fallback kế tiếp là allow thì PDP outage sẽ thành bypass. Nếu muốn fail-closed, dùng `onErrorReturn(false)` hoặc typed failure không dẫn tới grant.

## 11. Timeout, retry và cancellation trong chuỗi quyết định

PDP/ACL repository có thể timeout. `Mono.timeout(duration)` tạo lỗi timeout khi nguồn không phát tín hiệu đúng hạn. Không để một lỗi như vậy rơi vào `onErrorReturn(true)` hoặc `switchIfEmpty(permit)`.

```java
Mono<Boolean> safePdp = remotePdpCheck
        .timeout(Duration.ofMillis(300))
        .defaultIfEmpty(false)
        .onErrorResume(error -> {
            // Ghi metric/log mã lỗi phù hợp, KHÔNG log secrets.
            return Mono.just(false);
        });
```

Đây là **snippet tích hợp**, thời gian 300 ms chỉ để minh họa; config thực cần deadline end-to-end. Cần nhập `java.time.Duration`. Khi PDP unavailable có thể trả lỗi vận hành 503 theo contract, nhưng không chạy protected action.

### Retry chỉ khi an toàn

`Retry.backoff(...)` của Reactor có thể retry lỗi transient. Đừng retry cả:

- DENY của policy (false không phải exception).
- Invalid token, wrong tenant/resource, signature mismatch.
- Lỗi schema nghiêm trọng mà retry không thay đổi.
- Một mutation có side effects không idempotent.

Không dùng `retry()` không giới hạn cho authorization check. Bounded retry phải nằm trong deadline. Kiểm tra có làm lộ tài nguyên nhạy cảm sang PDP trước khi tenant membership được xác minh hay không.

### Cancellation

Reactor có cancellation; một `Mono.zip` có thể hủy các nhánh còn lại khi một nhánh empty/error. Đừng dựa vào “mọi policy call chắc chắn đã chạy” để bảo đảm audit. Nếu cần ghi audit, tạo một sự kiện quyết định trung tâm và test việc phát hành/không phát hành tương ứng; đừng dùng việc các publishers được subscribe làm bằng chứng chính sách đã được đánh giá đầy đủ.

## 12. Project Java 17 Maven chạy được: Reactor decisions với fail-closed

Ví dụ hoàn chỉnh sau dùng **Reactor Core thật** (không cần web server), Spring Boot BOM để quản lý phiên bản dependency và JUnit 5 + reactor-test. Mục tiêu là kiểm chứng semantics operator, không phải giả lập HTTP một cách tùy tiện.

Cấu trúc:

```text
reactive-policy-lab/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   └── ReactivePolicyLab.java
    └── test/java/demo/
        └── ReactivePolicyLabTest.java
```

### 12.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-policy-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Phiên bản 3.5.16 dùng để cố định một project học tập với Java 17 và các APIs Reactor tương ứng; **nhánh Spring Boot 3.5 đã kết thúc OSS support**, nên production phải chọn nhánh đang được hỗ trợ và đồng bộ dependency theo BOM. Project này không tạo HTTP endpoint hay cần `spring-boot-starter-security`; Spring WebFlux integration ở các mục sau là **snippet riêng**.

### 12.2. ReactivePolicyLab.java

```java
package demo;

import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class ReactivePolicyLab {

    private ReactivePolicyLab() {}

    // Tất cả required checks phải phát một Boolean.
    // Empty/error => false. Production nên giữ reason code.
    public static Mono<Boolean> safe(Mono<Boolean> check) {
        return check.defaultIfEmpty(false)
                .onErrorReturn(false);
    }

    // Role AND tenant AND (owner OR shared).
    public static Mono<Boolean> canRead(
            Mono<Boolean> authority,
            Mono<Boolean> tenant,
            Mono<Boolean> owner,
            Mono<Boolean> shared) {

        Mono<Boolean> ownerOrShare = Mono.zip(
                safe(owner), safe(shared))
                .map(pair -> pair.getT1() || pair.getT2());

        return Mono.zip(
                safe(authority),
                safe(tenant),
                ownerOrShare)
                .map(all -> all.getT1()
                        && all.getT2()
                        && all.getT3());
    }

    // Một tập REQUIRED checks trống bị từ chối rõ ràng.
    public static Mono<Boolean> requireAll(
            List<Mono<Boolean>> checks) {
        if (checks.isEmpty()) {
            return Mono.just(false);
        }
        return Flux.fromIterable(checks)
                .concatMap(ReactivePolicyLab::safe)
                .all(Boolean::booleanValue);
    }

    private static void scenario(String label,
                                 Mono<Boolean> authority,
                                 Mono<Boolean> tenant,
                                 Mono<Boolean> owner,
                                 Mono<Boolean> shared) {

        // block() chỉ dùng trong chương trình command-line demo.
        boolean result = Boolean.TRUE.equals(
                canRead(authority, tenant, owner, shared).block());

        System.out.println(label + "=" + result);
    }

    public static void main(String[] args) {
        scenario("ownerAllowed",
                Mono.just(true), Mono.just(true),
                Mono.just(true), Mono.just(false));

        scenario("sharedAllowed",
                Mono.just(true), Mono.just(true),
                Mono.just(false), Mono.just(true));

        scenario("tenantDenied",
                Mono.just(true), Mono.just(false),
                Mono.just(true), Mono.just(true));

        scenario("authorityDenied",
                Mono.just(false), Mono.just(true),
                Mono.just(true), Mono.just(true));

        scenario("notOwnerAndNotShared",
                Mono.just(true), Mono.just(true),
                Mono.just(false), Mono.just(false));

        scenario("missingAuthority",
                Mono.empty(), Mono.just(true),
                Mono.just(true), Mono.just(false));

        scenario("missingOwner",
                Mono.just(true), Mono.just(true),
                Mono.empty(), Mono.just(false));

        scenario("shareError",
                Mono.just(true), Mono.just(true),
                Mono.just(false),
                Mono.error(new IllegalStateException("PIP offline")));

        System.out.println("rawAllEmpty="
                + Flux.<Boolean>empty()
                    .all(Boolean::booleanValue).block());

        System.out.println("guardedAllEmpty="
                + requireAll(List.of()).block());
    }
}
```

**Điểm an toàn:** `safe` đảm bảo mỗi nhánh là true hoặc false, nên `Mono.zip` không tạo “empty decision” ngoài ý muốn. Điều kiện tổng đúng là `authority && tenant && (owner || shared)`, không phải OR toàn bộ. `requireAll` chặn trường hợp không có một rule bắt buộc nào.

### 12.3. Cách chạy

Với JDK 17+ và Maven:

```bash
mvn -q clean test
mvn -q exec:java -Dexec.mainClass=demo.ReactivePolicyLab
```

Dòng stdout của chương trình (không tính log của Maven/plugin):

```text
ownerAllowed=true
sharedAllowed=true
tenantDenied=false
authorityDenied=false
notOwnerAndNotShared=false
missingAuthority=false
missingOwner=false
shareError=false
rawAllEmpty=true
guardedAllEmpty=false
```

`rawAllEmpty=true` là một **minh họa về bẫy của Flux.all**, không phải kết quả nên dùng để cấp quyền. `guardedAllEmpty=false` là hành vi policy mong muốn khi danh sách kiểm tra bắt buộc vắng mặt.

Code được rà soát về syntax và expected output theo semantics Reactor; **chưa thực thi Maven build thực tế trong quá trình soạn nội dung**. Khi chạy trong dự án, nếu dependency APIs đã nâng major, cần xem migration notes của Spring/Reactor.

## 13. Kiểm thử Reactor bằng StepVerifier

Tệp `src/test/java/demo/ReactivePolicyLabTest.java`:

```java
package demo;

import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactivePolicyLabTest {

    @Test
    void ownerGrantNeedsAuthorityAndTenant() {
        StepVerifier.create(ReactivePolicyLab.canRead(
                    Mono.just(true), Mono.just(true),
                    Mono.just(true), Mono.just(false)))
                .expectNext(true)
                .verifyComplete();

        StepVerifier.create(ReactivePolicyLab.canRead(
                    Mono.just(true), Mono.just(false),
                    Mono.just(true), Mono.just(true)))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void sharedGrantWorksOnlyInsideValidTenant() {
        StepVerifier.create(ReactivePolicyLab.canRead(
                    Mono.just(true), Mono.just(true),
                    Mono.just(false), Mono.just(true)))
                .expectNext(true)
                .verifyComplete();

        StepVerifier.create(ReactivePolicyLab.canRead(
                    Mono.just(false), Mono.just(true),
                    Mono.just(false), Mono.just(true)))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void emptyDecisionNeverGrants() {
        StepVerifier.create(ReactivePolicyLab.canRead(
                    Mono.<Boolean>empty(), Mono.just(true),
                    Mono.just(true), Mono.just(false)))
                .expectNext(false)
                .verifyComplete();

        StepVerifier.create(ReactivePolicyLab.canRead(
                    Mono.just(true), Mono.<Boolean>empty(),
                    Mono.just(true), Mono.just(true)))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void errorDecisionNeverGrants() {
        StepVerifier.create(ReactivePolicyLab.canRead(
                    Mono.just(true), Mono.just(true),
                    Mono.just(false),
                    Mono.error(new IllegalStateException("PIP failed"))))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void ownerAndShareBothMissingDoNotGrant() {
        StepVerifier.create(ReactivePolicyLab.canRead(
                    Mono.just(true), Mono.just(true),
                    Mono.<Boolean>empty(), Mono.<Boolean>empty()))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void emptyAllMustBeRejectedByContract() {
        StepVerifier.create(
                    Flux.<Boolean>empty().all(Boolean::booleanValue))
                .expectNext(true)   // Reactor semantics, KHÔNG phải policy.
                .verifyComplete();

        StepVerifier.create(ReactivePolicyLab.requireAll(List.of()))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void requiredChecksAreConjoined() {
        StepVerifier.create(ReactivePolicyLab.requireAll(
                    List.of(Mono.just(true),
                            Mono.just(true),
                            Mono.just(false))))
                .expectNext(false)
                .verifyComplete();

        StepVerifier.create(ReactivePolicyLab.requireAll(
                    List.of(Mono.just(true), Mono.just(true))))
                .expectNext(true)
                .verifyComplete();
    }

    @Test
    void hasElementIsNotSameAsGranted() {
        StepVerifier.create(Mono.just(false).hasElement())
                .expectNext(true)
                .verifyComplete();
    }
}
```

Bộ test có **8 phương thức JUnit 5** (một số phương thức có nhiều assertions). Nó chứng minh:

- Một owner/share grant không vượt tenant hoặc authority bắt buộc.
- Empty/error ở một policy branch không trở thành PERMIT.
- `Flux.all` trên tập rỗng có semantics true và guard explicit khắc phục.
- `hasElement` trên một DENY=false vẫn true; không được dùng làm authorization result.

Sau khi chạy `mvn test`, xem báo cáo Surefire trong `target/surefire-reports`. Không đổi kỳ vọng false thành true để làm test xanh nếu phát hiện regression; điều đó là lỗi bảo mật.

### Kiểm thử trường hợp khó hơn

Thêm tests với `StepVerifier.withVirtualTime` để kiểm tra `Mono.timeout`/retry mà không chờ thật. Thêm `PublisherProbe` nếu cần xác nhận một policy branch không bị subscribe khi tenant/authority đã deny. Với source delay/side effects, kiểm tra cancellation và tổng số lần gọi remote PDP.

`StepVerifier` dùng trong unit tests Reactor; nó không thay thế `WebTestClient` xác minh HTTP filter chain và resource security thực tế.

## 14. Tích hợp Spring Security ReactiveAuthorizationManager

Ở WebFlux, `ServerHttpSecurity.authorizeExchange(...)` có thể dùng `.access(ReactiveAuthorizationManager<AuthorizationContext>)`. Giao diện nhận `Mono<Authentication>` và authorization context của exchange.

Đoạn dưới là **mã tích hợp cho Spring Security 6.5**, không thuộc project `reactive-policy-lab` (vì project đó chỉ phụ thuộc Reactor/JUnit). Nó minh họa một manager chặn toàn bộ non-PERMIT. Vì giao diện 6.5 còn `check` abstract/deprecated, class cài cả `check` và `authorize`; khi nâng lên 7.x phải đối chiếu chữ ký interface mới và bỏ override không còn tồn tại.

```java
import reactor.core.publisher.Mono;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authorization.AuthorizationContext;

final class DocumentReactiveGate
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final DocumentReactivePolicy policy;

    DocumentReactiveGate(DocumentReactivePolicy policy) {
        this.policy = policy;
    }

    // Tương thích Spring Security 6.5.
    @Override
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            AuthorizationContext context) {
        return decide(authentication, context)
                .map(AuthorizationDecision::new);
    }

    @Override
    public Mono<AuthorizationResult> authorize(
            Mono<Authentication> authentication,
            AuthorizationContext context) {
        return decide(authentication, context)
                .map(allowed ->
                        (AuthorizationResult) new AuthorizationDecision(allowed));
    }

    private Mono<Boolean> decide(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        return authentication
                .filter(auth -> auth.isAuthenticated()
                        && !(auth instanceof AnonymousAuthenticationToken))
                .flatMap(auth -> policy.canRead(
                        auth, context.getExchange()))
                .defaultIfEmpty(false)
                .onErrorReturn(false);
    }
}
```

`DocumentReactivePolicy` là **service nghiệp vụ** cần implement; Spring không tự biết membership, owner/share hoặc PDP của dự án. Đầu ra `canRead(Authentication, ServerWebExchange)` là `Mono<Boolean>` và **chỉ true sau khi tất cả guard bắt buộc hợp lệ**. Nếu cần 503 cho PDP outage, dùng typed failure mapping riêng ở ranh giới filter/service, không biến lỗi thành true.

### Tại sao dùng Mono<Authentication> do framework truyền?

- Không tự lấy username/role từ header do client đặt.
- Spring Security Reactive có cách truyền context theo subscriber, không phụ thuộc việc ThreadLocal giữ đúng identity khi thread switch.
- `authentication` có thể empty nếu chưa xác thực; chain `defaultIfEmpty(false)` bảo đảm non-permit.
- Nếu cần bảo vệ guest endpoints, cấu hình `permitAll` riêng; protected endpoint không tự cho guest qua khi authentication empty.

Không cache toàn cục `Mono<Authentication>` hoặc kết quả `policy.canRead(...)` giữa requests. Cùng một publisher cached có thể giữ decision của caller khác nếu đặt sai scope.

## 15. SecurityWebFilterChain và thứ tự matcher

Ví dụ cấu hình reactive HTTP:

```java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        DocumentReactiveGate documentGate) {

    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/public/**").permitAll()
                    .pathMatchers(
                        HttpMethod.GET,
                        "/tenants/*/documents/*")
                    .access(documentGate)
                    .anyExchange().denyAll())
            .oauth2ResourceServer(resource ->
                    resource.jwt(Customizer.withDefaults()))
            .build();
}
```

Cần imports `@Bean`, `HttpMethod`, `ServerHttpSecurity`, `SecurityWebFilterChain` và `Customizer`. Ứng dụng phải có `spring-boot-starter-webflux`, `spring-boot-starter-security` và JWT Resource Server dependencies/configuration đúng issuer/audience; đây chỉ là snippet tích hợp.

Trong `authorizeExchange`, **thứ tự matcher quan trọng**. Nếu:

```java
.anyExchange().permitAll()
.pathMatchers("/tenants/**").access(documentGate)
```

là sai: một rule rộng phía trước có thể khiến rule bảo vệ phía sau không bao giờ được xét hoặc cấu hình từ chối build, tùy DSL/version. Đặt rule cụ thể trước và `anyExchange().denyAll()` cuối. Mẫu WebFlux thường dùng `pathMatchers(...).access(manager)` cho một route family; không phải mọi rule dưới mỗi exchange đều tự được AND với nhau.

**Phân biệt servlet và reactive:**

| Servlet MVC | Reactive WebFlux |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `authorizeHttpRequests` | `authorizeExchange` |
| `AuthorizationManager<RequestAuthorizationContext>` | `ReactiveAuthorizationManager<AuthorizationContext>` |
| `SecurityContextHolder` thường theo thread | `ReactiveSecurityContextHolder` theo Reactor Context |
| Blocking servlet repository thường hợp lệ theo cấu hình | Tránh blocking trên event-loop, dùng reactive repository/adapter |

Không lấy mẫu servlet rồi chỉ đổi tên `HttpSecurity` sang `ServerHttpSecurity`; chữ ký manager và luồng Authentication khác nhau.

## 16. Quyền tenant và resource phải tính từ dữ liệu được xác minh

Một policy có thể viết:

```text
authenticated
AND hasAuthority("DOC_READ")
AND requestTenant ∈ activeMemberships(subject)
AND resource.tenantId == authorizedTenant
AND (owner == subject OR validShare(subject, resource))
AND resource.status != LOCKED
```

**Điều kiện tenant phải áp dụng trước owner/share.** Một record có cùng local document ID tại tenant khác vẫn không được cấp quyền.

Mẫu reactive policy pseudocode Java:

```java
Mono<Boolean> canRead(Authentication auth, ServerWebExchange exchange) {
    return tenantResolver.resolveVerified(auth, exchange)
            .flatMap(scope ->
                documentRepository.findByIdAndTenant(
                        documentIdFromRoute(exchange),
                        scope.tenantId())
                    .flatMap(doc ->
                        Mono.zip(
                            authorityCheck(auth, "DOC_READ"),
                            ownerOrShareCheck(auth, scope, doc),
                            unlockedCheck(doc))
                        .map(t -> t.getT1() && t.getT2() && t.getT3())
                    )
            )
            .defaultIfEmpty(false)
            .onErrorReturn(false);
}
```

Đây là **pseudocode tích hợp**: `tenantResolver` phải xác thực membership server-side, `documentIdFromRoute` phải validate, `documentRepository` phải dùng scope tenant trong query, các checks được định nghĩa cụ thể. Trong code thật, cần normalize **từng nhánh** trước `zip`, không chỉ `defaultIfEmpty(false)` ngoài cùng, để cả non-decision và lỗi không bị xử lý bất ngờ. Đối với remote PDP errors, typed outcome giúp phân biệt outage với policy DENY.

### Query-time enforcement vẫn cần

Ngay cả khi HTTP manager đã cho phép một request, repository không được gọi `findById(id)` rồi chỉ dựa vào policy check nếu resource có thể đổi tenant/owner giữa check và read. Dùng query tenant-scoped, transaction/version predicates và least privilege; với search/count/stats phải áp cùng row-level scope. HTTP authorization không tự thêm `WHERE tenant_id = ...`.

## 17. Đừng để Scheduler switch làm mất identity hoặc tenant scope

Trong WebFlux, lời gọi có thể chuyển giữa event-loop, `Schedulers.parallel()` và `Schedulers.boundedElastic()`. `ThreadLocal` thường không đại diện cho identity của subscriber. Dùng `ReactiveSecurityContextHolder` cho SecurityContext reactive, và `Reactor Context` để mang **authorized tenant scope đã được giải quyết** nếu framework/service cần.

```java
static final String SCOPE_KEY = "authorizedTenantScope";

Mono<Document> read(AuthorizedTenantScope scope) {
    return Mono.deferContextual(context -> {
        AuthorizedTenantScope actual = context.get(SCOPE_KEY);
        return repository.findByIdAndTenant(
                scope.documentId(), actual.tenantId());
    }).contextWrite(ctx -> ctx.put(SCOPE_KEY, scope));
}
```

Đây là **snippet ý tưởng**, cần định nghĩa `AuthorizedTenantScope` (bao gồm resource ID nếu dùng đoạn trên), `Document` và repository, không phải chương trình độc lập. Reactor Context lưu state theo subscription, **không tự xác thực tenant**. Dùng dữ liệu đã giải quyết qua membership/policy; không đưa raw `X-Tenant-Id` thẳng vào `contextWrite` rồi cho là quyền.

### Nên truyền scope qua tham số khi có thể

`repository.findByIdAndTenant(id, authorizedTenantId)` dễ audit hơn lấy từ ThreadLocal ngầm. Reactor Context hữu ích cho tracing/security context, nhưng không nên dùng nó để che giấu việc quyền thực tế chưa được kiểm tra.

### Không đặt `block()` trong pipeline

Gọi `block()` giữa WebFlux có thể khóa event loop, làm cạn threads và hỏng context propagation. Khi cần tích hợp thư viện blocking legacy, đặt nó trong `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` và giữ tenant policy, deadline, cancellation theo thiết kế; không dùng boundedElastic như giấy phép bỏ qua authorization.

## 18. Subscription, defer và Mono.cache: quyết định thuộc request nào?

Reactor publishers thường **cold**: không thực thi logic cho đến khi có subscriber. Nhưng bạn có thể vô tình bắt một giá trị quá sớm hoặc cache quyết định ở phạm vi quá rộng.

Phản ví dụ:

```java
// SAI: quyết định có thể bị dùng cho nhiều calls/users
// nếu shared Mono được cache và tái sử dụng toàn cục.
Mono<Boolean> sharedCachedPermission =
        policyService.canRead(currentUser, document)
                .cache();
```

`Mono.cache()` có thể cache kết quả/error/completion cho các subscribers của **cùng instance**. Nếu instance sống trong singleton và không được key theo subject+tenant+resource+action+version, quyết định của Alice có thể được phát cho Bob.

Mẫu đúng:

```java
Mono<Boolean> authorizationForThisRequest =
        Mono.defer(() -> policyService.canRead(
                verifiedPrincipal, resource, action));
```

`Mono.defer` tạo publisher mới tại subscription; nó **không thay việc xác minh principal/resource**. Nếu dùng cache business, key phải có tenant, subject/authority, resource ID và version/expiry phù hợp; thu hồi quyền cần invalidation hoặc TTL theo SLA.

### Cancellation và “đã gọi PDP” không bằng “đã cho phép”

`zip`/`flatMap` có thể cancel upstream; một audit event nên ghi **kết quả enforcement cuối cùng**, không chỉ đếm “PDP đã được subscribe”. Nếu request hủy sau khi policy check, không nên tiếp tục một mutation ở background mà không còn guard/transaction cần thiết.

## 19. Test matrix trước khi triển khai endpoint thật

| Case | Authority | Tenant | Owner | Shared | PDP / dữ liệu | Kỳ vọng |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | true | true | true | false | PERMIT | ALLOW |
| 2 | true | true | false | true | PERMIT | ALLOW |
| 3 | false | true | true | true | PERMIT | DENY |
| 4 | true | false | true | true | PERMIT | DENY |
| 5 | true | true | false | false | PERMIT | DENY |
| 6 | true | true | true | false | DENY | DENY |
| 7 | true | true | true | false | PDP `Mono.empty()` | DENY |
| 8 | true | true | true | false | PDP `Mono.error()` | DENY/unavailable |
| 9 | true | `Mono.empty()` | true | false | PERMIT | DENY |
| 10 | `Mono.empty()` | true | true | false | PERMIT | DENY |
| 11 | true | true | false | `Mono.error()` | PERMIT | DENY/unavailable |
| 12 | true | true | true | false | Resource not found | DENY/404 theo contract |
| 13 | true | true | true | false | Wrong tenant resource | DENY |
| 14 | true | true | true | false | Locked | DENY |
| 15 | true | true | true | false | Wrong PDP action/resource | DENY/invalid |
| 16 | true | true | true | false | PDP timeout | DENY/unavailable |
| 17 | true | true | true | false | PDP response expired | DENY/invalid |
| 18 | true | true | true | false | Empty required check list | DENY |
| 19 | true | true | true | false | `Flux.all` empty source | Test phát hiện true nhưng policy guard từ chối |
| 20 | true | true | true | false | Reused cached permission from other user | DENY; test cache isolation |

Các ca trên đòi tổng hợp **cả local và remote PDP** ở production; project Maven mục 12 chỉ kiểm tra authority, tenant, owner/shared và một số lỗi operator. Không nên tuyên bố nó đã kiểm thử HTTP filter chain/remote PDP.

### WebTestClient

Với WebFlux, dùng `WebTestClient` để kiểm tra:

- `GET /public/info` được permit theo policy public.
- `GET /tenants/alpha/documents/42` không có auth → 401.
- Authenticated Alice có DOC_READ, tenant hợp lệ, owner/shared → thành công.
- Alice thuộc alpha nhưng path tenant beta → 403/404 theo contract.
- Policy service Mono.empty/error/timeout → không nhận protected content và không gọi service xử lý.
- Wrong resource ID, resource tenant mismatch, locked document → không lộ dữ liệu.
- HTTP status mapping khi PDP unavailable nếu app chọn 503.

`WebTestClient` và `@WithMockUser` giúp kiểm tra Spring Security integration nhưng mock auth **không xác minh chữ ký JWT thật**. Với resource server cần thêm tests ở decoder/security filter bằng JWT ký test key và xác minh issuer/audience.

### StepVerifier test cả empty/error, không chỉ true/false

Một bộ test chỉ dùng `Mono.just(true)` và `Mono.just(false)` không đủ: bug thường nằm ở `Mono.empty()`, `Mono.never()`, `Mono.error()`, cancellation và timeouts. Với `Mono.never()`, dùng virtual time hoặc timeout test rõ ràng để tránh treo test suite.

## 20. Các lỗi phổ biến khi kết hợp Reactor operators

**1. `zip` một nhánh empty rồi ngoài cùng `defaultIfEmpty(true)`.** Thiếu quyết định biến thành PERMIT.

**2. `filter(isGranted).switchIfEmpty(Mono.just(PERMIT))`.** Một DENY thật trở thành empty, rồi fallback cấp quyền.

**3. `Flux.all(...)` trên tập rỗng.** Trả true vì vacuous truth; cần quy định danh sách required rules không được rỗng.

**4. `hasElement()/hasElements()` thay `isGranted()`.** DENY vẫn là một emitted element.

**5. `thenReturn(true)` sau `Mono.just(false)`.** Bỏ qua boolean DENY và phát PERMIT.

**6. `Mono.when(...)` để kết hợp các điều kiện Boolean.** Chỉ chờ completion, không AND quyết định.

**7. `onErrorReturn(true)` hoặc `onErrorComplete().switchIfEmpty(permit)`.** Outage PDP trở thành đường bypass.

**8. Dùng OR cho hai guard bắt buộc.** `role || tenant` cho phép caller không thuộc tenant hoặc thiếu role.

**9. Dùng `Flux.any(...)` cho toàn bộ mandatory checks.** Chỉ một grant là đủ dù các checks khác deny.

**10. `Mono.empty()` trong `ReactiveAuthorizationManager` như một “DENY chắc chắn”.** Nó có nghĩa không đưa ra decision; composition có thể hiểu khác.

**11. Đặt remote PDP call trước tenant check.** Có thể gửi resource/tenant attrs chưa được phép sang PDP và tốn tài nguyên.

**12. `block()` trên WebFlux event loop.** Dễ gây nghẽn request và phá lợi thế nonblocking.

**13. Dùng `SecurityContextHolder` thread-local như servlet trong reactive chain.** Identity có thể sai khi thread switch; dùng reactive security context.

**14. `Mono.cache()` cho một kết quả authorization dùng chung giữa users.** Quyết định của caller này có thể bị phát lại cho caller khác.

**15. Chỉ test happy path.** Không phát hiện empty, error, timeout, no-decision và cancellation.

**16. Không có `anyExchange().denyAll()` cuối.** Endpoint mới có thể không được bảo vệ theo chính sách dự kiến.

**17. Tưởng hai pathMatchers nối nhau tương đương AND.** Rule matching HTTP theo precedence; muốn AND nhiều chính sách, hãy tạo một manager/policy tổ hợp đúng.

**18. Quyền trên endpoint không đi kèm data query tenant-scoped.** Có thể đọc/đếm/thống kê ngoài phạm vi ngay sau khi HTTP policy permit.

**19. Bỏ qua obligations/attributes khi PDP trả PERMIT.** Authorization thành công chỉ khi policy contract được đáp ứng đầy đủ.

**20. Không phân biệt policy DENY với lỗi hạ tầng.** Cả hai chặn nghiệp vụ, nhưng logging, monitoring và status mapping nên khác.

## 21. Checklist production

- [ ] Viết công thức Boolean nghiệp vụ, xác định rõ nhóm AND và nhóm OR.
- [ ] Mọi guard bắt buộc đều có kết quả tường minh; empty/error không thành allow.
- [ ] Normalize `Mono.empty()` thành deny trước khi `zip` khi phù hợp.
- [ ] Không dùng `defaultIfEmpty(true)`/`onErrorReturn(true)` trong authorization.
- [ ] Không dùng `filter(...).switchIfEmpty(permit)` trên một decision.
- [ ] Không dùng `thenReturn(true)`/`hasElement()` để đánh giá quyền.
- [ ] Với `Flux.all`, xử lý danh sách checks rỗng theo policy, không dựa vacuous truth.
- [ ] `Flux.any` chỉ áp dụng cho nhóm alternative grants được phê duyệt.
- [ ] Dependency chains dùng `flatMap` để kiểm tra tenant/role trước khi gọi resource/PDP.
- [ ] Xử lý timeout/cancellation và bounded retry mà không mở quyền.
- [ ] `ReactiveAuthorizationManager` trả quyết định tường minh cho protected endpoint.
- [ ] `ServerHttpSecurity.authorizeExchange` match đúng route và có `denyAll` cuối.
- [ ] Không trộn servlet `AuthorizationManager` với reactive manager.
- [ ] Lấy Authentication từ nguồn Spring Security reactive, không từ raw request/header.
- [ ] Tenant resolved bằng membership server, resource truy vấn kèm tenant predicate.
- [ ] Không block event loop; dùng reactive driver hoặc cô lập blocking adapter đúng cách.
- [ ] Không cache quyết định xuyên caller/tenant/resource/action; đặt TTL/version phù hợp.
- [ ] Có `StepVerifier` tests cho true, false, empty, error, timeout và tập rỗng.
- [ ] Có `WebTestClient` tests cho HTTP 401/403/503 và không có side effect.
- [ ] Có regression tests sau nâng Spring Security/Reactor version, nhất là `check` → `authorize`.

**Kết luận:** Reactor xử lý **giá trị, empty, error và cancellation** chứ không chỉ true/false. Để kết hợp quyết định trên HTTP WebFlux an toàn, hãy chuyển từng nhánh bắt buộc thành một **quyết định rõ**, áp dụng **AND/OR đúng chính sách**, chặn empty/error/timeout, và chỉ cấp quyền khi **mọi guard bắt buộc** thật sự thành công. Một toán tử có semantics hoàn toàn đúng của Reactor vẫn có thể tạo **lỗ hổng phân quyền** nếu dùng nó như một phép kiểm tra grant khác với ý nghĩa thực.

## Tài liệu chính thức

- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — ReactiveAuthorizationManager JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Project Reactor — Reactor Core Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Project Reactor — FAQ: Mono zipWith/zipWhen never called](https://projectreactor.io/docs/core/release/reference/faq.html)
- [Project Reactor — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor — Mono JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
