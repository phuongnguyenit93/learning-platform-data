# `Mono`, `Flux` và thời điểm kiểm tra quyền khi đăng ký xử lý trong Reactive Method Security

## 1. Vấn đề thực tế: tạo publisher khi có quyền, subscribe khi quyền đã bị thu hồi

Trong một dịch vụ Spring WebFlux, `alice` có authority `report:read`. Một tầng orchestration gọi service để tạo pipeline đọc dữ liệu:

```java
Mono<String> pending = reportService.readOne();
```

Sau khi tạo `pending`, quyền đọc của Alice bị thu hồi. Một thời điểm khác, ứng dụng mới đăng ký thực thi:

```java
pending.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(alice)
).block();
```

**Câu hỏi quan trọng:** quyền được kiểm tra ở lúc gọi `readOne()` để nhận `Mono`, ở lúc `subscribe()`/`block()`, hay ở từng phần tử mà `Flux` phát ra?

Trong Reactive Method Security, các lời gọi tới method được AOP proxy chặn, nhưng **đánh giá authorization cần được phối hợp với Reactor `Context` của subscriber**. Với `@EnableReactiveMethodSecurity` và `@PreAuthorize` trên method trả `Mono`/`Flux`, quyết định quyền là một phần của publisher bảo vệ và được thực thi khi luồng đó được subscribe. Vì vậy:

- **Chỉ tạo publisher không chứng minh đã được cho phép.**
- Với một publisher bảo vệ dạng cold, mỗi lần subscribe có thể đánh giá lại quyền theo `Authentication` của subscription tương ứng.
- `@PreAuthorize` bảo vệ **lượt thực thi method**, không mặc định kiểm tra lại trên **từng item** của một `Flux` kéo dài.
- Thay đổi quyền sau lần kiểm tra **không tự động hủy** tất cả subscription đang chạy.
- `cache()`, `share()`, hot publisher hoặc việc lưu/chuyển publisher đã được cấp quyền có thể làm mất ranh giới kiểm tra cho các lượt nhận dữ liệu sau.
- Để đảm bảo không có side effect trước khi subscriber được authorize, code bên trong method phải **lazy** (`Mono.defer`, `Mono.fromSupplier`, reactive repository), không khởi tạo tác vụ ghi/blocking một cách eager.

Bài này thuộc nhóm **Method security Reactive** của module **Spring Security – authorization**. Trọng tâm là `Mono`, `Flux` và **thời điểm kiểm tra quyền khi đăng ký xử lý (subscription)**, bao gồm thời điểm lắp ráp pipeline (*assembly*), thời điểm subscribe, xử lý dữ liệu, context và thực nghiệm kiểm thử.

Sau bài, bạn sẽ:

1. Phân biệt **method call**, **assembly**, **subscription**, **onNext**, **onComplete/onError** và **cancellation**.
2. Bật đúng `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` cho Spring Security 6.5.
3. Hiểu `@PreAuthorize`/`@PostAuthorize` ở môi trường reactive và khác biệt với synchronous method security.
4. Lấy `Authentication` bằng `ReactiveSecurityContextHolder` thay vì suy từ ThreadLocal.
5. Kiểm chứng rằng quyền có thể khác giữa hai subscription của **cùng một publisher**.
6. Hiểu lý do `Flux` được phép lúc bắt đầu **không đồng nghĩa mọi item trong tương lai vẫn được phép**.
7. Tránh rò quyền qua `Mono.cache()`, `Flux.cache()`, hot/multicast streams và detached subscription.
8. Viết ví dụ Java 17+ / Spring Boot 3.5.8 với `StepVerifier`, dynamic policy và kiểm tra side effects.
9. Phân biệt kiểm tra quyền trước khi xử lý với per-item filtering, owner/tenant ACL và recheck lúc ghi.
10. Tránh `block()` trong WebFlux event-loop, tự `subscribe()` fire-and-forget và self-invocation làm mất AOP.

**Thông điệp chính:** Trong reactive code, không thể suy ra “đã kiểm tra quyền” chỉ từ việc có biến kiểu `Mono<T>` hoặc `Flux<T>`. Phải biết ai subscribe, `Reactor Context` nào được dùng, subscription có thực sự đi qua publisher bảo vệ hay không, và data/permission thay đổi thế nào sau quyết định ban đầu.

---

## 2. `Mono` và `Flux`: publisher chưa phải kết quả đã được thực thi

**Reactive Streams `Publisher`** mô tả nguồn phát tín hiệu khi có subscriber. Reactor cung cấp:

| Type | Số phần tử `onNext` tối đa | Ví dụ |
| --- | --- | --- |
| `Mono<T>` | 0 hoặc 1 | Đọc một báo cáo, kiểm tra quyền async, ghi một tài liệu |
| `Flux<T>` | 0 đến nhiều | Danh sách tài liệu, feed sự kiện, nhiều hàng database |

Một publisher thường được tạo trước lúc thực thi nguồn dữ liệu:

```java
Mono<String> source =
    Mono.fromSupplier(() -> {
        System.out.println("READ_DB");
        return "record-42";
    });

System.out.println("ASSEMBLED");
// Chưa có READ_DB.
source.block();
// Lúc subscribe: READ_DB được in.
```

Với một lượt chạy đồng bộ đơn giản, stdout:

```text
ASSEMBLED
READ_DB
```

`Mono.fromSupplier` chỉ gọi supplier khi có subscribe. `block()` bản thân tạo **một subscription**, đợi kết quả và trả value; dùng nó trong CLI/test thì phù hợp, nhưng **không** gọi `block()` trên WebFlux/Netty event-loop để lấy dữ liệu trong controller/service reactive.

### 2.1. Assembly không tự bảo đảm lazy

Không phải mọi lời gọi Java tạo publisher đều lazy:

```java
// SAI nếu expensiveOrMutatingCall() có side effect ngay.
Mono<String> eager = Mono.just(expensiveOrMutatingCall());
```

Java tính `expensiveOrMutatingCall()` **trước** khi `Mono.just(...)` được tạo. Nếu method đó ghi DB, gửi email hoặc gọi dịch vụ từ xa, side effect đã xảy ra tại **method invocation/assembly**, không đợi subscription.

Đúng hơn:

```java
Mono<String> lazy =
    Mono.fromSupplier(() -> expensiveOrMutatingCall());
```

Với logic trả Publisher:

```java
Mono<String> lazyPublisher =
    Mono.defer(() -> reactiveRepositoryOperation());
```

Hai đoạn trên là **mảnh minh họa**: `expensiveOrMutatingCall` và `reactiveRepositoryOperation` phải được định nghĩa riêng nếu dùng trong ứng dụng.

`Mono.defer` trì hoãn **việc tạo publisher con** cho tới lúc subscribe; `Mono.fromSupplier` trì hoãn **việc tính một giá trị**. Với `Flux`, tương ứng `Flux.defer(...)` và `Flux.fromIterable(...)` cùng thời điểm tạo iterable cần xem xét.

### 2.2. Mỗi subscription có thể chạy nguồn lại

```java
AtomicInteger calls = new AtomicInteger();

Mono<Integer> mono = Mono.fromSupplier(
    calls::incrementAndGet
);

System.out.println(mono.block());
System.out.println(mono.block());
```

Output:

```text
1
2
```

Đây là publisher **cold**, tính lại ở mỗi subscription. Điều này có lợi khi muốn mỗi request có Authentication/policy riêng, nhưng với thao tác ghi cần chú ý: **subscribe lại có thể ghi lại**. Dùng idempotency key, transaction, unique constraint hoặc domain guard nếu một publisher có side effect có thể được retry/re-subscribe.

**Đừng nhầm** `Mono.just(value)` với `Mono.fromSupplier(...)`: `just` phát lại cùng value đã tính, còn `fromSupplier` thực thi supplier cho từng lượt đăng ký.

---

## 3. Reactive Method Security hoạt động qua Reactor Context

### 3.1. Bật đúng annotation

Với Spring Boot 3.5.x/Spring Security 6.5.x, ví dụ cấu hình:

```java
@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecurityConfiguration {
}
```

Method cần được gọi qua **Spring-managed proxy**:

```java
@Service
public class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public Mono<String> read(Long id) {
        return Mono.defer(() -> loadReportReactively(id));
    }
}
```

`loadReportReactively` là method minh họa chưa định nghĩa. Trong ứng dụng thật, nó có thể trả `Mono` từ R2DBC, reactive MongoDB, reactive HTTP client hoặc domain service khác.

**Vì sao cần `@EnableReactiveMethodSecurity`?** Starter Security và `@EnableWebFluxSecurity` cho web không tự thay thế cấu hình authorization **ở method**. `@EnableMethodSecurity` của Servlet/imperative method support cũng không nên dùng thay cho reactive method security khi mong đợi `Mono`/`Flux` và Reactor Context.

### 3.2. Reactive authorization đọc authentication từ đâu?

Spring Security reactive dùng `ReactiveSecurityContextHolder` để truy cập `SecurityContext` trong **Reactor Context của subscriber**. Đây không phải cùng mô hình với `SecurityContextHolder` dựa vào ThreadLocal ở Servlet truyền thống.

```java
Mono<String> currentUser =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
```

Trong HTTP WebFlux đã qua Spring Security, web filters thiết lập security context cho pipeline request. Trong unit/integration test ngoài HTTP, cần cấp context tường minh:

```java
Authentication alice = new UsernamePasswordAuthenticationToken(
    "alice", "unused",
    List.of(new SimpleGrantedAuthority("report:read"))
);

Mono<String> named =
    currentUser.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)
    );
```

`contextWrite` chỉ ảnh hưởng đúng phần upstream của chain liên quan theo quy tắc Reactor Context. Nó không biến `Authentication` thành một biến toàn cục và không cấp quyền tự động cho mọi thread/task trong JVM.

### 3.3. Authentication không nên do HTTP request tự khai

Đoạn `new UsernamePasswordAuthenticationToken(...)` ở ví dụ và test **chỉ để mô phỏng actor trong môi trường tin cậy**. Production phải xác minh session/token bằng Spring Security provider, JWT signature/issuer/audience hoặc cơ chế authentication phù hợp.

Không tạo authorities từ JSON như:

```json
{
  "username": "admin",
  "authorities": ["report:read", "ROLE_ADMIN"]
}
```

và coi đó là chứng thực hợp lệ.

### 3.4. Thread hop và `publishOn`/`subscribeOn`

Reactor Context được gắn với subscription, nên một pipeline có thể chuyển scheduler bằng `publishOn`/`subscribeOn` mà vẫn truy cập được `ReactiveSecurityContextHolder.getContext()` theo mô hình Reactor.

```java
Mono<String> result =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .publishOn(Schedulers.parallel());
```

Đây là **mảnh code**, cần import Reactor schedulers. Không kết luận rằng `SecurityContextHolder.getContext()` kiểu ThreadLocal trong callback trên scheduler mới luôn có authentication. Nếu đưa công việc sang `CompletableFuture`, `new Thread`, `@Async` hay background queue **ngoài pipeline Reactor**, context có thể không tự đi cùng; phải thiết kế propagation/identity cho tác vụ đó.

---

## 4. Bốn mốc thời gian cần phân biệt

```text
T0  method invocation qua Spring proxy
    service.readOne()
       |
       +--> trả về Publisher được bảo vệ
             (reactive authorization là một phần của pipeline)

T1  assembly/composition
    securedMono.map(...).filter(...).contextWrite(...)

T2  subscription
    subscribe(), block(), StepVerifier.create(...).verify()
       |
       +--> Reactor Context có Authentication của subscriber
       +--> reactive @PreAuthorize đánh giá quyền
       +--> Nếu DENY: phát lỗi authorization
       +--> Nếu ALLOW: tiếp tục thực thi nguồn business

T3  publisher phát tín hiệu
    onNext(...) -> onComplete() hoặc onError(...)

T4  kết thúc / cancel / retry / subscription tiếp theo
```

Tuy trong code AOP luôn có **lời gọi Java vào proxy** ở T0, với reactive method-security interceptor trong thiết lập minh họa, đánh giá quyền gắn với publisher và **được thực hiện trong subscription**. Đừng lấy một log từ constructor hoặc method call ở T0 rồi kết luận authorization đã xảy ra.

### 4.1. Tạo publisher trước khi có security context

Một caller có thể tạo pipeline trước:

```java
Mono<String> pipeline = service.readOne();
```

Sau đó subscriber dùng context:

```java
Mono<String> aliceView = pipeline.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(alice)
);
```

Điểm quan trọng: **quyết định không nên “đóng băng” theo người đang tạo biến `pipeline`**, mà phải dùng subscriber context của lượt thực thi. Ví dụ runnable ở mục 7 và test ở mục 8 sẽ xác minh điều này.

### 4.2. Cùng publisher, hai subscribers, hai identities

```text
securedMono (chưa subscribe)
      |
      +-- subscribe Alice / report:read --> ALLOW --> business source
      |
      +-- subscribe Bob / không read ---> DENY --> không chạy source
```

Điều này đúng đối với publisher bảo vệ **cold** và cả hai subscription **đều đi qua boundary authorization**. Nếu caller bọc publisher bằng `.cache()` rồi phát lại kết quả đã được tính, lượt nhận thứ hai **có thể không subscribe lại vào publisher gốc có security interceptor**. Mục 10 giải thích rủi ro.

### 4.3. Một `Flux` được chấp nhận khi subscribe không phải per-item authorization

```text
Subscribe Flux -> @PreAuthorize ALLOW
       |
       v
  onNext(item1)
       |
  quyền bị thu hồi bên ngoài
       |
  onNext(item2)
       |
  onNext(item3)
```

`@PreAuthorize` thường là **quyết định trước lượt thực thi được bảo vệ**. Nó không mặc định hỏi lại permission service ở mỗi `onNext` của một Flux kéo dài. Một hot stream có thể tiếp tục phát sau khi quyền của user bị thu hồi nếu hệ thống không có recheck/cancel protocol.

Nếu nghiệp vụ yêu cầu kiểm tra quyền từng item hoặc trước một mutation, phải bổ sung policy ở **điểm sử dụng**. Không suy từ một ALLOW ban đầu thành quyền truy cập vĩnh viễn.

---

## 5. `@PreAuthorize`, `@PostAuthorize` và filtering trong reactive

### 5.1. `@PreAuthorize`: chặn trước business execution

```java
@PreAuthorize("hasAuthority('report:read')")
public Flux<ReportView> list() {
    return reactiveRepository.findVisibleReports();
}
```

Đây là **mảnh code** phụ thuộc `ReportView`/repository. Khi bị từ chối, business publisher không được thực thi theo reactive security flow chuẩn; điều này phải được xác nhận bằng test nguồn dữ liệu/side-effect, không chỉ HTTP status.

### 5.2. `@PostAuthorize`: xét dữ liệu kết quả, không dùng làm bảo vệ duy nhất cho write

```java
// MẢNH CODE, ví dụ ý tưởng cho một kết quả Mono.
@PostAuthorize("returnObject.ownerId == authentication.name")
public Mono<ReportView> get(Long id) {
    return reactiveRepository.findById(id);
}
```

`@PostAuthorize` kiểm tra kết quả theo method-security contract, khác với `@PreAuthorize`. Với Flux, các cơ chế post-authorization/filtering có semantics cụ thể theo phiên bản và loại Publisher; **không được mặc định** rằng kiểm tra sau method là an toàn để chặn tất cả side effects hoặc từng tín hiệu trong stream dài. Hãy kiểm thử dữ liệu được phát và số lần áp policy trên version Spring Security đang dùng.

Đặc biệt, tránh:

```java
// CỐ TÌNH SAI VỀ THIẾT KẾ: kiểm tra sau khi chuyển tiền.
@PostAuthorize("hasAuthority('money:transfer')")
public Mono<String> transfer(...) {
    return sendMoney(); // side effect có thể đã xảy ra trước hậu kiểm
}
```

Mảnh trên không biên dịch độc lập (`sendMoney` và arguments chưa có) và nhằm nhấn mạnh **authorization phải đứng trước mutation**, bổ sung kiểm tra nghiệp vụ/DB atomic.

### 5.3. Lọc từng phần tử bằng policy reactive

Giả sử repository đã truy vấn **tenant-scoped** và trả về `Flux<Report>`; bạn muốn chỉ phát những báo cáo có quyền đọc riêng của actor:

```java
// MẢNH CODE: cần định nghĩa repository, policy, Report,
// actor và tenant từ verified Authentication.
Flux<Report> visible =
    repository.findByTenant(trustedTenant)
        .concatMap(report ->
            reactivePolicy.canRead(trustedActor, report)
                .flatMap(allowed ->
                    allowed ? Mono.just(report) : Mono.empty()
                )
        );
```

Ở đây một quyết định có thể được lấy **cho mỗi report** khi `concatMap` subscribe vào policy. `concatMap` giữ thứ tự, còn `flatMap` có thể cho concurrency lớn hơn và không giữ thứ tự phát như `concatMap` khi inner streams có timing khác.

Nhưng:

- **Chặn tại repository trước tiên:** không truy vấn toàn bộ tenant rồi chỉ filter trong Java nếu có thể tránh, và càng không truy vấn mọi tenant để lọc sau.
- Nếu policy trả error hoặc không có quyết định, không được mặc định ALLOW.
- Với pagination, lọc sau LIMIT có thể làm page/count sai và vẫn nạp dữ liệu bị cấm. Cần thiết kế truy vấn/policy phù hợp.
- Với `Flux` liên tục vô hạn, chọn tần suất recheck/cancel theo SLA revoke; không thể chỉ dựa `@PreAuthorize`.

### 5.4. Reactive SpEL bean có thể trả `Mono<Boolean>`

Spring Security 6.5 hỗ trợ gọi bean authorization logic từ biểu thức, ví dụ:

```java
@PreAuthorize("@gate.mayRead(authentication)")
public Mono<String> readOne() {
    return source.read();
}
```

Trong bài runnable, `gate.mayRead(Authentication)` sẽ trả `Mono<Boolean>` **lazy**, cho phép test thay đổi flag sau assembly nhưng trước subscription. Đối với policy phản hồi `Mono.empty()` (abstain), phải xác định rõ default behavior/combination; tránh biến “không có kết luận” thành ALLOW. Khi business bắt buộc có quyết định, một policy nên trả explicit `true` hoặc `false`.

---

## 6. Chuẩn bị ví dụ Java 17+/Spring Boot 3.5.8

Demo tách ba thành phần:

- `ReadGate`: chính sách động, trả `Mono<Boolean>` và đếm số lần **thực sự đánh giá**.
- `SecureNotes`: hai method bảo vệ `Mono` và `Flux`, mỗi method dùng `defer` và đếm lần nguồn business được subscribe.
- `ReactiveMethodDemo`: dựng một publisher **trước**, thu hồi quyền, subscribe và đối chiếu kết quả; sau đó cấp quyền lại và subscribe bằng actor khác.

**Phạm vi:** Ví dụ chạy trong CLI/test nhưng dùng Spring Security **reactive method security thật**. Không cần mở HTTP endpoint để thấy Reactor Context; trong WebFlux request thật, Spring Security WebFilters tạo context cho subscriber. CLI/test sẽ dùng `contextWrite(...)` để mô phỏng đúng authentication đã xác minh.

**Không dùng database:** bộ đếm chỉ giúp nhận biết có chạy source chưa. Khi dùng DB thực, cần tenant predicate, authorization version và transaction riêng; test CLI không chứng minh mọi DB hoặc stream hot an toàn.

### 6.1. Cấu trúc thư mục

```text
reactive-method-subscription/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/demo/
    │       ├── ReactiveMethodDemo.java
    │       ├── ReadGate.java
    │       └── SecureNotes.java
    └── test/
        └── java/demo/
            └── SubscriptionSecurityTest.java
```

### 6.2. Gradle

**`settings.gradle`:**

```groovy
rootProject.name = 'reactive-method-subscription'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'io.projectreactor:reactor-core'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot BOM chọn các phiên bản tương thích của Spring Security và Reactor. Spring Security 6.5 áp dụng cho Boot 3.5.x; nếu chuyển sang Spring Security 7/Boot 4, kiểm tra lại method-security APIs và dependency migration.

### 6.3. Chính sách đọc động: `ReadGate.java`

**`src/main/java/demo/ReadGate.java`:**

```java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component("gate")
public class ReadGate {

    private final AtomicBoolean open = new AtomicBoolean(true);
    private final AtomicInteger evaluations = new AtomicInteger();

    public void setOpen(boolean value) {
        open.set(value);
    }

    public int evaluations() {
        return evaluations.get();
    }

    public Mono<Boolean> mayRead(Authentication authentication) {
        return Mono.fromSupplier(() -> {
            // Đây là lúc publisher policy được SUBSCRIBE,
            // không phải lúc method mayRead trả Mono.
            evaluations.incrementAndGet();

            if (!open.get() || authentication == null
                    || !authentication.isAuthenticated()) {
                return false;
            }

            return authentication.getAuthorities().stream()
                .anyMatch(authority ->
                    "notes:read".equals(authority.getAuthority()));
        });
    }
}
```

`AtomicBoolean` mô phỏng **thu hồi/cấp lại** quyết định trong runtime; không phải policy store production. `AtomicInteger` đo số lần publisher quyết định được subscribe.

`Mono.fromSupplier` bảo đảm việc đọc flag `open` xảy ra **khi publisher của gate được subscribe**, không bị tính trước khi mã trong `@PreAuthorize` tạo pipeline.

Trong production, `mayRead` có thể gọi reactive permission service, tenant directory hoặc ACL; phải xử lý anonymous, account status, malformed response, timeout và `DENY` khi thiếu dữ liệu. Không coi boolean từ một endpoint client không tin cậy là quyết định.

### 6.4. Business service với cả `Mono` và `Flux`: `SecureNotes.java`

**`src/main/java/demo/SecureNotes.java`:**

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class SecureNotes {

    private final AtomicInteger monoSourceSubscriptions =
        new AtomicInteger();

    private final AtomicInteger fluxSourceSubscriptions =
        new AtomicInteger();

    private final AtomicInteger writes = new AtomicInteger();

    @PreAuthorize("@gate.mayRead(authentication)")
    public Mono<String> readOne() {
        return Mono.defer(() -> {
            monoSourceSubscriptions.incrementAndGet();

            return ReactiveSecurityContextHolder.getContext()
                .map(ctx ->
                    "NOTE:" + ctx.getAuthentication().getName()
                );
        });
    }

    @PreAuthorize("@gate.mayRead(authentication)")
    public Flux<String> readMany() {
        return Flux.defer(() -> {
            fluxSourceSubscriptions.incrementAndGet();
            return Flux.just("N1", "N2");
        });
    }

    @PreAuthorize("hasAuthority('notes:write')")
    public Mono<String> writeOne() {
        return Mono.fromSupplier(() -> {
            writes.incrementAndGet();
            return "WRITTEN";
        });
    }

    public int monoSubscriptions() {
        return monoSourceSubscriptions.get();
    }

    public int fluxSubscriptions() {
        return fluxSourceSubscriptions.get();
    }

    public int writes() {
        return writes.get();
    }
}
```

**Ba tầng lazy được minh họa:**

1. `@PreAuthorize` làm việc trong reactive method authorization.
2. `ReadGate.mayRead` chỉ tính policy decision khi publisher của gate được subscribe.
3. `Mono.defer`, `Flux.defer`, `Mono.fromSupplier` chỉ chạy business source khi subscription đã được phép đi qua.

Với `readOne()`, dữ liệu `"NOTE:alice"` được tạo bằng **Reactor Context của subscriber**, không lấy từ ThreadLocal người đã tạo publisher.

Với `readMany()`, một lần subscription cho phép thì publisher phát **hai phần tử**. Điều đó không có nghĩa gate được đánh giá hai lần. Nếu muốn kiểm tra mỗi item, cần thiết kế thêm ở pipeline như mục 5.3.

`writeOne()` chỉ mô phỏng side effect bằng bộ đếm; ở production, write phải có transaction/conditional update và guard object/tenant/state.

### 6.5. Application + CLI chứng minh assembly khác subscription

**`src/main/java/demo/ReactiveMethodDemo.java`:**

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class ReactiveMethodDemo {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveMethodDemo.class, args);
    }

    @Bean
    @Profile("!test")
    CommandLineRunner demonstrate(
            SecureNotes notes,
            ReadGate gate) {

        return args -> {
            Authentication alice =
                actor("alice", "notes:read");
            Authentication bob =
                actor("bob", "notes:view");

            // T0: dựng publisher; CHƯA subscribe.
            Mono<String> sharedCold = notes.readOne();
            System.out.println("CHECKS_BEFORE_SUBSCRIBE: "
                + gate.evaluations());

            // T1: revoke sau assembly nhưng trước subscribe.
            gate.setOpen(false);
            denied("ALICE_AFTER_REVOKE", () ->
                sharedCold.contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(alice)
                ).block()
            );

            // T2: cấp lại và subscribe CÙNG publisher.
            gate.setOpen(true);
            System.out.println("ALICE_AFTER_GRANT: "
                + sharedCold.contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(alice)
                ).block()
            );

            // T3: Bob thiếu authority, vẫn CÙNG publisher.
            denied("BOB_NO_AUTHORITY", () ->
                sharedCold.contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(bob)
                ).block()
            );

            // T4: Flux có 2 items nhưng gate được xét
            // theo lượt subscription, không tự xét 2 lần.
            Flux<String> many = notes.readMany();
            List<String> values = many.contextWrite(
                ReactiveSecurityContextHolder
                    .withAuthentication(alice)
            ).collectList().block();

            System.out.println("ALICE_FLUX: " + values);
            System.out.println("POLICY_EVALUATIONS: "
                + gate.evaluations());
            System.out.println("MONO_SOURCE_SUBSCRIPTIONS: "
                + notes.monoSubscriptions());
            System.out.println("FLUX_SOURCE_SUBSCRIPTIONS: "
                + notes.fluxSubscriptions());
        };
    }

    static Authentication actor(
            String name, String authority) {
        return new UsernamePasswordAuthenticationToken(
            name,
            "demo-only",
            List.of(new SimpleGrantedAuthority(authority))
        );
    }

    private static void denied(
            String label, Runnable task) {
        try {
            task.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (AccessDeniedException expected) {
            System.out.println(label + ": DENIED");
        }
    }
}
```

Tại sao chương trình này hữu ích?

- `notes.readOne()` được gọi **một lần** để tạo `sharedCold`.
- Các lần `.contextWrite(...).block()` subscribe **cùng publisher** dưới Alice hoặc Bob.
- Gate bị đóng sau assembly; lần subscribe đầu không được dùng một quyết định allow “đóng băng” từ trước.
- Sau khi mở lại gate, Alice đọc thành công.
- Bob không có `notes:read`; publisher không vì đã từng được Alice dùng mà tự cấp quyền cho Bob.
- `readMany()` chỉ cho thấy hai phần tử cùng nằm trong một Flux subscription, gate không tự recheck ở mỗi phần tử.

**Chương trình chạy trên Spring-managed service bean** do `CommandLineRunner` inject, nên proxy method-security được áp dụng. Đừng dùng `new SecureNotes()` rồi mong có `@PreAuthorize` interception.

### 6.6. Dòng console dự kiến

Chạy bằng Gradle Wrapper tại thư mục project:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu chưa có wrapper, tạo wrapper với Gradle tương thích hoặc dùng `gradle bootRun` khi Gradle đã cài.

Các dòng do `System.out.println` trong `CommandLineRunner` sinh ra được kỳ vọng:

```text
CHECKS_BEFORE_SUBSCRIBE: 0
ALICE_AFTER_REVOKE: DENIED
ALICE_AFTER_GRANT: NOTE:alice
BOB_NO_AUTHORITY: DENIED
ALICE_FLUX: [N1, N2]
POLICY_EVALUATIONS: 4
MONO_SOURCE_SUBSCRIPTIONS: 1
FLUX_SOURCE_SUBSCRIPTIONS: 1
```

**Phân tích:**

1. Trước subscribe: gate chưa đánh giá -> 0.
2. Alice khi gate đóng: deny; source mono không được subscribe.
3. Alice sau khi mở gate: allow; source mono được subscribe một lần.
4. Bob khi gate mở nhưng không có authority: deny; source không chạy thêm.
5. Alice subscribe Flux: allow; source Flux được subscribe một lần và phát hai giá trị.
6. Tổng bốn subscriptions qua gate (`deny`, `allow`, `deny`, `allow`) -> bốn evaluations; mono source = 1, flux source = 1.

**Lưu ý kiểm chứng:** Đây là output **dự kiến từ thiết kế và source code**, không phải kết quả biên dịch/chạy đã xác nhận tại môi trường soạn bài. Cần chạy test ở mục tiếp theo trên đúng Spring Boot/Spring Security phiên bản sử dụng. Nếu dự án tùy biến reactive interceptor, điều này cần được kiểm nghiệm lại.

---

## 7. Integration tests với `StepVerifier` và Reactor Context

### 7.1. File test đầy đủ

**`src/test/java/demo/SubscriptionSecurityTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("test")
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD
)
class SubscriptionSecurityTest {

    @Autowired
    SecureNotes notes;

    @Autowired
    ReadGate gate;

    private static Authentication alice() {
        return ReactiveMethodDemo.actor(
            "alice", "notes:read");
    }

    private static Authentication bob() {
        return ReactiveMethodDemo.actor(
            "bob", "notes:view");
    }

    private static <T> Mono<T> as(
            Mono<T> publisher, Authentication auth) {
        return publisher.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth));
    }

    private static <T> Flux<T> as(
            Flux<T> publisher, Authentication auth) {
        return publisher.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth));
    }

    @Test
    void assemblingMonoDoesNotEvaluatePolicy() {
        Mono<String> publisher = notes.readOne();

        assertEquals(0, gate.evaluations());
        assertEquals(0, notes.monoSubscriptions());

        StepVerifier.create(as(publisher, alice()))
            .expectNext("NOTE:alice")
            .verifyComplete();

        assertEquals(1, gate.evaluations());
        assertEquals(1, notes.monoSubscriptions());
    }

    @Test
    void revocationBeforeSubscriptionIsEffective() {
        Mono<String> publisher = notes.readOne();

        gate.setOpen(false);

        StepVerifier.create(as(publisher, alice()))
            .expectError(AccessDeniedException.class)
            .verify();

        assertEquals(1, gate.evaluations());
        assertEquals(0, notes.monoSubscriptions());

        // Cùng publisher, nhưng policy đã được bật lại.
        gate.setOpen(true);
        StepVerifier.create(as(publisher, alice()))
            .expectNext("NOTE:alice")
            .verifyComplete();

        assertEquals(2, gate.evaluations());
        assertEquals(1, notes.monoSubscriptions());
    }

    @Test
    void sameColdPublisherUsesEachSubscribersIdentity() {
        Mono<String> publisher = notes.readOne();

        StepVerifier.create(as(publisher, alice()))
            .expectNext("NOTE:alice")
            .verifyComplete();

        StepVerifier.create(as(publisher, bob()))
            .expectError(AccessDeniedException.class)
            .verify();

        assertEquals(2, gate.evaluations());
        assertEquals(1, notes.monoSubscriptions());
    }

    @Test
    void fluxAuthorizationIsPerSubscriptionNotPerItem() {
        Flux<String> publisher = notes.readMany();

        StepVerifier.create(as(publisher, alice()))
            .expectNext("N1", "N2")
            .verifyComplete();

        assertEquals(1, gate.evaluations());
        assertEquals(1, notes.fluxSubscriptions());

        gate.setOpen(false);

        StepVerifier.create(as(publisher, alice()))
            .expectError(AccessDeniedException.class)
            .verify();

        assertEquals(2, gate.evaluations());
        assertEquals(1, notes.fluxSubscriptions());
    }

    @Test
    void writeCannotExecuteWithOnlyReadAuthority() {
        StepVerifier.create(as(notes.writeOne(), alice()))
            .expectError(AccessDeniedException.class)
            .verify();

        assertEquals(0, notes.writes());

        Authentication writer = ReactiveMethodDemo.actor(
            "writer", "notes:write");

        StepVerifier.create(as(notes.writeOne(), writer))
            .expectNext("WRITTEN")
            .verifyComplete();

        assertEquals(1, notes.writes());
    }

    @Test
    void missingSubscriberSecurityContextCannotRead() {
        // Trong test chưa có WebFlux request/security context.
        // Không có Authentication trusted cho subscription.
        StepVerifier.create(notes.readOne())
            .expectError()
            .verify();

        assertEquals(0, notes.monoSubscriptions());
    }
}
```

Chạy:

```bash
./gradlew test
```

**Tại sao đây là integration tests chứ không chỉ unit tests?**

- `@SpringBootTest` tạo ApplicationContext thật, Bean `SecureNotes`, `ReadGate` và Spring AOP Method Security interceptor.
- `@ActiveProfiles("test")` ngăn CLI runner chạy trước test.
- `@DirtiesContext` giữ state counters/gate độc lập giữa các test.
- `StepVerifier` **thực sự subscribe**; nếu chỉ gọi method rồi assert không có exception, bạn không kiểm tra được reactive authorization.
- `as(publisher, auth)` đặt đúng `ReactiveSecurityContextHolder` cho mỗi subscription.
- Tests dùng **một publisher** qua hai subscription để phát hiện việc cache/giữ quyền sai thời điểm.
- Assertions về source subscriptions chứng minh denial **không chỉ đổi response thành lỗi sau khi business source đã chạy**.

### 7.2. Vì sao test “assembly không check” quan trọng?

Nếu test chỉ viết:

```java
notes.readOne();
```

và không subscribe, test có thể vẫn pass kể cả implementation không kiểm tra quyền nào. Phải dùng `StepVerifier` hoặc một subscriber thực để kiểm tra hành vi:

```java
StepVerifier.create(
    notes.readOne().contextWrite(
        ReactiveSecurityContextHolder
            .withAuthentication(alice())
    )
).expectNext("NOTE:alice").verifyComplete();
```

Điểm ranh giới **subscriber context** chính là điều khiến reactive method authorization khác lời gọi synchronous truyền thống.

### 7.3. Tại sao không dùng `@WithMockUser` ở mọi test này?

`@WithMockUser` là một công cụ có ích cho Spring Security tests. Nhưng bài này cố ý tạo hai subscriber **trên cùng publisher**, có identity và state khác nhau, nên `contextWrite(withAuthentication(...))` làm thời điểm và phạm vi authentication **rõ ràng hơn**.

Đối với WebFlux HTTP integration tests, có thể dùng `WebTestClient` cùng `SecurityMockServerConfigurers.mockUser(...)` và `springSecurity()`. Chỉ cần bảo đảm test subscribe thật và đi qua WebFilter/proxy, không chỉ gọi controller method trực tiếp.

---

## 8. Khi nào `@PreAuthorize` được xét lại trên `Flux`?

Phân biệt **lượt subscribe** và **từng phần tử**:

```text
Subscription #1 (Alice):
  check policy -> ALLOW
  Flux source -> onNext(A), onNext(B), onComplete()

Subscription #2 (Bob):
  check policy -> DENY
  Flux source -> KHÔNG subscribe

Subscription #3 (Alice, grant revoked):
  check policy -> DENY
  Flux source -> KHÔNG subscribe
```

Đây là behavior của publisher cold được bảo vệ như trong ví dụ; không có per-element ACL evaluation chỉ nhờ dùng Flux.

### 8.1. Quyền có thể thay đổi giữa các `onNext`

Nếu stream kéo dài vài giờ, có thể xuất hiện:

```text
t1: @PreAuthorize ALLOW, subscribe
t2: emit report A
t3: admin thu hồi grant
t4: emit report B
t5: emit report C
```

Không mặc định rằng Spring Security sẽ tự lắng nghe mọi thay đổi ACL và hủy subscription sau t3. Nếu sản phẩm đòi **revocation có hiệu lực ngay trên stream đang chạy**, cần thiết kế chủ động:

- Recheck trước **mỗi item nhạy cảm** hoặc trên từng batch với freshness SLA.
- Theo dõi policy version/tenant membership và chủ động cancel subscriptions khi revoke.
- Dùng nguồn dữ liệu tenant-scoped tại database hoặc query, không nạp dữ liệu mọi tenant rồi filter sau.
- Với WebSocket/SSE hoặc hot streams, gắn principal/tenant vào từng session/subscriber và thực thi policy tại điểm phát.
- Khi quyền bị thu hồi, tránh tiếp tục đưa nội dung đã prefetch hoặc buffer ra ngoài vượt quá guarantee sản phẩm.

### 8.2. Cảnh báo về prefetch và buffering

Các operator như `publishOn`, `flatMap`, `buffer`, `window` và `limitRate` có thể thay đổi prefetch/request pattern. Dù policy được recheck mỗi phần tử ở một vị trí trong pipeline, **dữ liệu có thể đã được đọc ở upstream** trước khi check downstream.

Nếu yêu cầu “DB không bao giờ đọc object tenant khác”, phải filter ngay query/repository. Nếu yêu cầu “item không bao giờ được trả cho client thiếu quyền”, phải bảo đảm kiểm tra **trước emission ra subscriber**. Hai yêu cầu không hoàn toàn giống nhau.

### 8.3. `@PostFilter` không phải phép màu

Reactive Method Security hỗ trợ các annotation filter phù hợp với phiên bản, nhưng không nên coi `@PostFilter` là bảo đảm tự động cho bất kỳ hot infinite Flux nào: cần test thực tế từng item, context, authorization caching, lỗi giữa stream và giới hạn tài nguyên.

Với policy phức tạp, viết explicit `filterWhen`, `concatMap` hoặc policy-aware repository có thể dễ quan sát và kiểm thử hơn. `filterWhen` với policy trả `Mono<Boolean>` có thể hữu ích, nhưng phải xác định behavior khi policy lỗi/empty, concurrency và backpressure; đừng gộp lỗi PDP thành `true`.

---

## 9. `cache()` và hot publisher: ranh giới bảo mật dễ bị bỏ qua

### 9.1. Có thể tái phát dữ liệu cho subscriber không còn quyền

Một pattern nguy hiểm:

```java
// MẢNH CODE CỐ TÌNH NGUY HIỂM:
Flux<String> secured = notes.readMany();

// cache bọc BÊN NGOÀI publisher đã được method interceptor bảo vệ
Flux<String> cached = secured.cache();
```

Giả sử Alice subscribe `cached` khi có quyền. Cache subscribe một lần vào `secured`, lấy dữ liệu rồi lưu. Sau đó Bob subscribe **chính `cached`**. Nếu cache replay giá trị mà **không tạo subscription mới tới `secured`**, method-security check của publisher gốc không chạy lại cho Bob.

```text
Alice -> cached
          -> subscribe secured -> authz ALLOW -> Flux source
          -> cache [N1, N2]

Bob   -> cached
          -> replay [N1, N2]
          -> không re-subscribe secured -> không recheck authz
```

Đây là lỗ hổng nếu `cached` được chia sẻ **qua identities/tenants**. Tương tự với `Mono.cache()`, `share()`, multicast `ConnectableFlux`, Sinks và các mô hình hot streams nếu policy chỉ đặt ở lần subscription vào nguồn shared.

Không nói “mọi cache trong Reactor đều không an toàn”; vấn đề là **vị trí cache so với authorization boundary** và **phạm vi chia sẻ cache**.

### 9.2. Nguyên tắc thiết kế cache an toàn

- Không cache **publisher đã chứa quyết định quyền của user A** rồi dùng lại như kết quả an toàn cho user B.
- Nếu cache raw domain data, key cần chứa tenant/resource/version thích hợp; vẫn phải authorize tại **mỗi request/subscriber** trước khi phát.
- Nếu response khác nhau theo principal/field-level policy, cache key có thể cần subject, action, policyVersion.
- ACL/membership/revoke phải trigger invalidation hoặc có freshness semantics rõ ràng.
- Với hot stream đa subscriber, áp permission **per subscriber** trước khi tiếp xúc dữ liệu nhạy cảm, không chỉ authorize kết nối nguồn.

Một ý tưởng là dựng publisher bảo vệ bên trong defer:

```java
Flux<String> perSubscription =
    Flux.defer(() -> notes.readMany());
```

Mỗi subscriber tạo **một lời gọi qua Spring bean proxy** và subscribe publisher mới. Đây không phải thay thế mọi policy (hot source có thể share dữ liệu), nhưng tránh cố định một publisher đã cache-authorized ngoài ranh giới kiểm tra.

### 9.3. `retry` và `repeat` cũng tạo subscription mới

```java
Mono<String> read = notes.readOne();

// Dùng khi có retry policy đúng; đây chỉ là minh họa.
Mono<String> retried = read.retry(1);
```

Retry là **đăng ký lại** ở một số trường hợp lỗi và có thể kích hoạt thêm một policy check. Nếu `read` là thao tác ghi, retry có thể làm side effect lặp lại. Không tự động retry `AccessDeniedException`, vì **deny không phải lỗi mạng tạm thời** và việc retry trái phép có thể làm bão PDP.

### 9.4. `subscribe()` fire-and-forget

Một code path không nên gọi:

```java
// CỐ TÌNH KHÔNG KHUYẾN NGHỊ:
notes.writeOne().subscribe();
```

rồi trả “đã ghi thành công” trước khi authorization, transaction hoặc mutation thực sự hoàn tất. Subscription có thể phát lỗi sau khi method caller đã trả response; Security Context cũng có thể không được thiết lập theo cách mong muốn nếu detached.

Hãy **return publisher** để WebFlux/framework quản lý lifecycle, hoặc orchestration subscribe có quản lý rõ trạng thái/identity/error/cancellation. Trên luồng HTTP, nên:

```java
return notes.writeOne();
```

và để WebFlux subscribe trong request pipeline có Reactor Security Context đúng.

---

## 10. Authorization tại thời điểm subscribe vẫn có TOCTOU

Dù một quyền được đánh giá lúc subscribe, nó vẫn có thể đổi trước khi transaction dữ liệu ghi:

```text
t1: subscribe -> @PreAuthorize ALLOW
t2: Admin revoke ACL hoặc chuyển owner/tenant
t3: DB UPDATE theo state cũ
t4: Commit
```

Đặc biệt với `Mono.delay`, remote calls, processing lâu hoặc `Flux` ghi nhiều items, khoảng cách giữa t1 và t3 có thể đáng kể.

**Một ALLOW lúc subscribe không phải chứng chỉ quyền tồn tại mãi tới commit.**

### 10.1. Cập nhật dữ liệu bằng conditional SQL

```sql
UPDATE documents
SET content = :newContent,
    version = version + 1
WHERE id = :documentId
  AND tenant_id = :trustedTenantId
  AND owner_id = :trustedActorId
  AND state = 'DRAFT'
  AND version = :expectedVersion;
```

Đây là **SQL minh họa**, không phải schema trong demo. Kiểm tra số hàng updated; `0` có thể nghĩa không còn quyền/trạng thái/version phù hợp, không tự chuyển thành thành công.

Nếu permission phụ thuộc bảng grants/ACL khác, cần một protocol version/locking/transaction giữa **writer** và **revoker**. Chỉ `@Transactional` bao bọc một publisher không bảo đảm dữ liệu quyền đã được kiểm tra mới nhất nếu manager chạy trước transaction.

### 10.2. Reactive transaction scope

Với R2DBC, có thể dùng reactive transaction manager và:

```java
// MẢNH CODE: requires TransactionalOperator/secured repository.
return transactionalOperator.transactional(
    repository.findByIdAndTenantId(id, tenant)
        .flatMap(doc -> recheckAndUpdate(doc, actor))
);
```

`TransactionalOperator` gắn transaction với Reactor Context của publisher; nó **khác** với tự quản lý thread-bound imperative transaction bằng JDBC. `recheckAndUpdate` phải thực sự kiểm tra lại policy, không lấy ALLOW cũ từ một cache toàn cục.

**Không gọi JDBC blocking** trong WebFlux event-loop; nếu buộc tích hợp legacy blocking API cần boundary scheduler riêng, timeout và transaction management phù hợp. Offload blocking không biến nó thành R2DBC transaction.

---

## 11. Spring AOP: những đường đi có thể bỏ qua kiểm tra quyền

### 11.1. Self-invocation

```java
@Service
class ReportService {

    public Mono<String> outer() {
        // CẢNH BÁO: gọi trực tiếp trên this, không qua proxy.
        return inner();
    }

    @PreAuthorize("hasAuthority('report:read')")
    public Mono<String> inner() {
        return Mono.just("SECRET");
    }
}
```

Đoạn này là mảnh minh họa. Nếu `outer` được gọi qua proxy nhưng nó gọi `this.inner()` nội bộ, Spring AOP có thể **không áp** `@PreAuthorize` cho `inner`. Tách method cần bảo vệ ra Spring bean khác rồi gọi qua injected proxy, hoặc đặt guard tại domain boundary để không thể bypass.

### 11.2. Không gọi `new` rồi mong method-security hoạt động

```java
SecureNotes notes = new SecureNotes();
// new object không được Spring proxy quản lý.
```

Trong demo, `SecureNotes` phải được inject từ ApplicationContext; test phải là `@SpringBootTest` hoặc một test context có bật reactive method security. Không tự khởi tạo class rồi khẳng định annotation hoạt động.

### 11.3. Return type và API không reactive

Theo tài liệu Spring Security 6.5, reactive method security dựa vào **Reactor Context** và hỗ trợ publisher types như `Mono`/`Flux` (hoặc reactive types được version tương ứng hỗ trợ). Đừng trộn `@PreAuthorize` của reactive method security với một method trả `String` synchronous rồi mặc định context/pointcut/deny behavior giống Servlet. Với function không reactive, hãy chọn đúng phương pháp security và kiểm chứng.

### 11.4. Tự subscribe nội bộ

Một service gọi method protected nhưng tự `.subscribe()` vào detached publisher có thể bỏ mất error/identity lifecycle của request. Với WebFlux, nên return/combine Publisher:

```java
return auditService.saveEvent()
    .then(notes.writeOne());
```

Đây là mảnh code (cần `auditService`/bean và contract riêng); nó cho framework giám sát completion/errors. Khi cần side effects độc lập với request, tạo **background job có identity/authority và policy riêng**, không sao chép bừa `SecurityContext` của user sang tác vụ chạy nhiều giờ.

---

## 12. Lỗi HTTP so với lỗi reactive stream

Một subscription bị từ chối có thể nhận `AccessDeniedException`/`AuthorizationDeniedException` dưới dạng **error signal**, thay vì Java exception được ném trực tiếp tại lúc tạo publisher.

```java
Mono<String> pending = notes.readOne();

// Chỉ dựng pipeline, chưa xác nhận được phép.
StepVerifier.create(asAlice(pending))
    .expectError(AccessDeniedException.class)
    .verify();
```

Đây là mảnh test; `asAlice` cần định nghĩa. Trong HTTP WebFlux, Spring Security xử lý lỗi authorization qua cơ chế web security để trả status như 401/403 tùy state và entry point. Với non-HTTP CLI/scheduler, caller phải xử lý lỗi publisher, ví dụ kiểm thử `StepVerifier.expectError(...)`.

**Không dùng**:

```java
// CỐ TÌNH NGUY HIỂM:
.onErrorResume(AccessDeniedException.class,
    e -> Mono.just("SECRET"))
```

để biến DENY thành việc phát dữ liệu nhạy cảm. Với API muốn trả response đặc biệt, thông báo fallback phải **không tiết lộ dữ liệu** và không làm side effect. Khi PDP không có quyết định, fail closed.

Nếu lỗi đến **sau khi HTTP response đã bắt đầu stream**, không thể mặc định thay toàn bộ response thành 403 sạch sẽ; có thể phải đóng stream/error session. Vì vậy các dữ liệu nhạy cảm cần kiểm tra quyền tại điểm thích hợp **trước khi phát item**.

---

## 13. Tránh nhầm `Reactor Context`, ThreadLocal và identity bị chuyển sai

### 13.1. Security context đi theo subscription, không theo biến publisher

```java
Mono<String> pipeline = notes.readOne();
```

`pipeline` không chứa một “username toàn cục” cố định trong mọi trường hợp. `ReactiveSecurityContextHolder` lấy context theo lượt subscribe và cách bạn composition/contextWrite. Hai subscribers có context khác nhau sẽ được đánh giá khác nhau nếu cả hai đi qua authorization boundary.

### 13.2. Không phát tán `Authentication` sang mọi stream

Nếu cache `Authentication` ở field singleton rồi tái sử dụng:

```java
// NGUY HIỂM: singleton giữ identity từ request trước.
private Authentication lastActor;
```

một request sau có thể vô tình dùng actor của người trước. Không dùng field singleton hoặc ThreadLocal tự chế làm current principal trong reactive pipeline. Dùng `ReactiveSecurityContextHolder.getContext()` khi cần identity trong subscriber chain.

### 13.3. `contextWrite` đặt sai chỗ

Reactor Context có quy tắc **luồng truy cập upstream**; nếu gắn context sau một operator không thuộc cùng chain hoặc tạo detached subscription, người tiêu thụ context có thể không nhìn thấy giá trị mong muốn. Test bằng `StepVerifier` trên **publisher cuối cùng** được WebFlux xử lý, không chỉ trên một mảnh riêng của pipeline.

### 13.4. Async và scheduler

`publishOn`/`subscribeOn` trong Reactor được thiết kế cùng Context propagation, nhưng một future/thread tự tạo ở ngoài Reactor không tự giữ `ReactiveSecurityContextHolder`. Nếu bạn phải gọi remote service hoặc truyền dữ liệu tới queue, hãy dùng identity/policy scope được xác minh theo hợp đồng, có correlation/audit và không lưu token thô trong log.

---

## 14. Kiểm thử timing, replay và quyền thay đổi

Một ma trận kiểm thử quan trọng:

| Tình huống | Kỳ vọng |
| --- | --- |
| Tạo publisher, chưa subscribe | Không chạy DB/source; chưa coi là đã authorize |
| Subscribe Alice có READ | ALLOW, nhận dữ liệu |
| Subscribe Bob không READ cùng cold publisher | DENY, không chạy source |
| Tạo publisher khi gate mở, đóng trước subscribe | DENY |
| Tạo publisher khi gate đóng, mở trước subscribe | Đánh giá trạng thái lúc subscribe, có thể ALLOW |
| Flux một subscription phát hai items | Không mặc định recheck mỗi item |
| Subscribe Flux lần hai sau revoke | DENY nếu đi qua publisher bảo vệ mới/lại |
| Đóng gate sau item đầu trong stream dài | Cần protocol per-item/cancel nếu muốn chặn item sau |
| `.cache()` bao ngoài secured publisher, share sang actor khác | Rủi ro replay bỏ qua authorization |
| `Mono.fromSupplier` vs `Mono.just(doWrite())` | Supplier lazy; method trong `just` đã được gọi eager |
| `retry`/`repeat` | Có thể tạo subscription/side effect mới |
| Method bị self-invocation | Có thể bypass AOP |
| Mono lỗi authorization | `StepVerifier.expectError(...)`; không coi constructor throw là bắt buộc |
| Không có Reactor Security Context | Fail closed, không dùng default admin/tenant |
| Grant bị thu hồi trước commit nhưng sau precheck | Cần DB/policy recheck tại mutation |
| Hot SSE/WebSocket stream | Quyền kết nối ban đầu chưa đủ cho revoke tức thì |

### 14.1. Lỗi phổ biến

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Test gọi method mà không subscribe | Reactive auth chưa được kích hoạt | Dùng StepVerifier/block trong test CLI |
| Cho rằng authority được chốt lúc tạo `Mono` | Nhầm assembly và subscription | Tạo publisher rồi thay quyền trước subscribe để kiểm chứng |
| Cho rằng `Flux` kiểm tra mọi `onNext` | `@PreAuthorize` xét lượt thực thi | Per-item policy / cancellation / version |
| Reader Bob thấy cache của Alice | Cache bao ngoài secured publisher và dùng chung | Cache scope + authorize từng subscriber |
| Side effect ghi xảy ra dù không subscribe | `Mono.just(doWrite())` eager | `defer`/`fromSupplier` và transaction |
| Cùng command bị ghi hai lần | Publisher cold subscribe/retry hai lần | Idempotency, unique constraint, retry policy |
| Code dùng `SecurityContextHolder` trong Reactor | ThreadLocal không phải subscriber Context | `ReactiveSecurityContextHolder` |
| Chuyển sang `CompletableFuture` mất identity | Thoát Reactor Context | Explicit trusted context/adapter |
| `@PreAuthorize` không chạy khi gọi `this.inner()` | Self-invocation bypass proxy | Tách bean + integration tests |
| User cùng role nhưng khác tenant đọc được dữ liệu | Chỉ xét authority tĩnh | Tenant-scoped repository + ACL |
| PDP lỗi rồi `.onErrorReturn(true)` | Fail-open | DENY/error không thực hiện mutation |
| `@PostAuthorize` đặt trên write có side effect | Kiểm tra quyền quá muộn | Pre-authorize và DB guard |
| Method trả publisher nhưng code block trong body | Làm mất tính reactive, event-loop bị nghẽn | Reactive I/O, `Mono.defer`, scheduler boundary |
| Test chạy ngoài Spring context | Không có advisor | Inject proxy qua `@SpringBootTest` |
| Flux đã phát một phần rồi mới lỗi | HTTP response đã stream | Kiểm soát quyền trước data emission |
| Cho rằng revoke tự hủy subscription | Không có cơ chế notify/cancel | Policy epoch, stream cancel/recheck |

---

## 15. Câu hỏi tự đánh giá

**1.** `Mono<String> p = securedService.readOne();` đã chứng minh Alice có quyền chưa?

**Đáp:** Chưa. Trong reactive method security, cần quan sát subscription đi qua publisher được bảo vệ cùng Reactor Security Context hợp lệ.

**2.** Gọi `block()` có tạo subscription không?

**Đáp:** Có; `block()` subscribe và chờ giá trị/terminal signal. Chỉ dùng hợp lý ở CLI/test hoặc boundary chấp nhận blocking.

**3.** Nếu Gate open lúc assembly nhưng đóng trước subscribe, chương trình demo cho kết quả gì?

**Đáp:** DENY, vì gate được đánh giá khi subscription chạy.

**4.** Hai subscriber có cùng một publisher cold, một người có READ và một người không. Có được nhận cùng dữ liệu không?

**Đáp:** Không nếu cả hai đều đi qua Method Security publisher; mỗi subscription dùng context và quyền tương ứng.

**5.** `Flux` phát 100 items có nghĩa `@PreAuthorize` kiểm tra 100 lần không?

**Đáp:** Không mặc định. Nó bảo vệ lượt method/subscription, không tự per-item ACL check.

**6.** Nếu quyền bị thu hồi giữa stream, Spring Security có tự ngừng phát mọi item sau đó không?

**Đáp:** Không có bảo đảm chung. Cần recheck/cancel policy theo contract sản phẩm.

**7.** Vì sao `Mono.just(repository.save(entity))` không giống `Mono.defer(...)`?

**Đáp:** `save` được gọi ngay khi đánh giá argument của `Mono.just`; `defer` chỉ gọi supplier lúc subscribe.

**8.** Một secured publisher bị `.cache()` sau khi Alice đọc. Bob được nhận giá trị replay có nguy hiểm không?

**Đáp:** Có nếu cache dùng chung và lượt Bob không tạo subscription lại vào boundary authorization.

**9.** `@EnableWebFluxSecurity` đã bật Reactive Method Security chưa?

**Đáp:** Không mặc định. Cần bật `@EnableReactiveMethodSecurity` và kiểm thử AOP proxy.

**10.** Tại sao test phải assert source subscription count sau DENY?

**Đáp:** Để chứng minh không có side effect/source chạy trái phép dù kết quả cuối là lỗi quyền.

**11.** Vì sao `@PostAuthorize` không nên làm chặn duy nhất cho lệnh ghi?

**Đáp:** Mutation có thể xảy ra trước hậu kiểm; cần pre-check và điều kiện DB/transaction.

**12.** Nếu gọi `this.secured()` trong cùng bean, có chắc Method Security chạy?

**Đáp:** Không. Spring AOP proxy có thể bị bypass bởi self-invocation.

**13.** `ReactiveSecurityContextHolder` và `SecurityContextHolder` truyền thống có giống nhau không?

**Đáp:** Không. Reactive holder dựa vào Reactor Context của subscriber, không mặc định là ThreadLocal theo request.

**14.** Nếu `Flux` đã phát một phần HTTP response, sau đó phát lỗi AccessDeniedException, có thể đổi toàn bộ response thành 403 không?

**Đáp:** Không chắc. Khi response đã bắt đầu, cần xử lý stream termination; bảo vệ dữ liệu trước emission.

**15.** Khi policy nằm trong database/ACL bị sửa sau lúc subscribe nhưng trước commit, cần gì?

**Đáp:** Gắn tenant/owner/authorization constraints vào transaction/conditional update hoặc lock/recheck tương ứng; một ALLOW ở subscribe không tự bảo vệ commit.

---

## 16. Tài liệu chính thức và định hướng mở rộng

- [Spring Security 6.5 – Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, reactive authorization interceptor, Reactor Context.
- [Spring Security 6.5 – Reactive Method Security with AuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html#_enablereactivemethodsecurity_with_authorizationmanager): đăng ký method-security advisors và biểu thức trả `Mono<Boolean>`.
- [Spring Security – Reactive Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html): authentication trong WebFlux.
- [Spring Security – Testing WebFlux Method Security](https://docs.spring.io/spring-security/reference/reactive/test/method.html): Spring Security test support cho reactive method.
- [Spring Security – Testing WebFlux Applications](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html): `WebTestClient`, `mockUser`, reactive security integration.
- [Reactor Core – Reference Guide](https://projectreactor.io/docs/core/release/reference/): cold/hot publishers, assembly/subscription, backpressure và operator semantics.
- [Reactor – Context Propagation](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): subscriber context và `contextWrite`.
- [Reactor Test – StepVerifier](https://projectreactor.io/docs/test/release/reference/): kiểm thử `Mono`/`Flux` có subscription và terminal signals.
- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): reactive `TransactionalOperator` và transaction boundary.
- [Spring Framework – AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): self-invocation/proxy limitations.

**Kết luận:** Trong Reactive Method Security, cần nghĩ theo **publisher + subscription + Reactor Security Context**. Việc gọi `service.method()` để nhận `Mono`/`Flux` không tương đương thực thi công việc hay “đã được cấp quyền”. Với publisher cold được Spring Method Security bảo vệ, subscription là điểm quan trọng để đánh giá policy và thực thi nguồn; mỗi subscription có thể dùng identity/quyền khác nhau. Nhưng `@PreAuthorize` không tự kiểm tra mỗi item, không tự chặn hot replay, không bảo đảm revoke sau lúc subscribe sẽ hủy stream, và không thay authorization ở thời điểm ghi DB. Hãy dùng lazy publishers, đúng context, StepVerifier, cache scope, per-item policy khi cần và transaction/conditional mutation để bảo vệ dữ liệu thật.