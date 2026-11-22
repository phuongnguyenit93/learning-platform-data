# Chẩn đoán mất ngữ cảnh do `subscribe()` thủ công hoặc Publisher nằm ngoài chuỗi trong Spring Security WebFlux

## 1. Mục tiêu học tập và tình huống lỗi

Bài này thuộc chủ đề **Spring Security - reactive**, nhóm **Chuyển đổi và gỡ lỗi**. Trọng tâm là xác định **vì sao `ReactiveSecurityContextHolder.getContext()` trả `Mono.empty()` hoặc không thấy người dùng hiện tại**, mặc dù request đã đi qua xác thực; đặc biệt khi code gọi `.subscribe()` thủ công, `.block()`, tạo luồng nền, hoặc dùng một `Publisher` được thực thi ngoài chuỗi phản ứng của HTTP request.

Sau bài học, người đọc cần:

1. Phân biệt **Reactor `Context` theo `Subscriber`** với `ThreadLocal`, `SecurityContextHolder` của Servlet và các biến request-scope thông thường.
2. Tìm điểm tách subscription bằng cách truy vết pipeline từ HTTP handler/filter đến service và client async.
3. Phân biệt **Publisher được tạo ở nơi khác nhưng vẫn được compose** (thường an toàn về Context) với **Publisher được subscribe riêng** (không tự nhận Reactor Context của request).
4. Sửa lỗi bằng các toán tử `flatMap`, `then`, `zipWhen`, `Mono.when`, `defer`/`deferContextual`, `contextWrite` đúng phạm vi.
5. Kiểm thử được cả trường hợp lỗi và trường hợp sửa đúng bằng `StepVerifier`, rồi đối chiếu qua `WebTestClient` trong ứng dụng thật.
6. Không vô tình làm lộ danh tính giữa request, “sửa” bằng cách cấp quyền giả, hoặc chạy tác vụ bảo mật ngoài quyền kiểm soát của chuỗi phản ứng.

### Triệu chứng thường gặp

- Endpoint được bảo vệ đã đăng nhập/JWT hợp lệ; controller thấy `Authentication`, nhưng service gọi qua `subscribe()` ở `doOnNext` chỉ thấy anonymous hoặc `getContext()` rỗng.
- `@PreAuthorize` trong service reactive cho kết quả không mong đợi nếu tác vụ quan trọng được kích hoạt ngoài Publisher mà method trả về.
- Audit/event async có người dùng `null`, nhưng request trả 200; đôi khi lỗi chỉ xuất hiện khi callback chạy trên scheduler/executor khác.
- Code có một `Mono` được tạo trong bean field và dùng lại; có nơi thấy đúng user, có nơi thấy user cũ, hoặc `Mono` không hề chạy vì không được subscribe.
- `doOnError` trên request không thấy exception từ một tác vụ “fire-and-forget”, khiến lỗi rơi vào error handler riêng.

Các triệu chứng không tự chứng minh rằng Spring Security sai. Việc đầu tiên là phân loại: request chưa được xác thực, subscriber bị tách, operator đặt sai vị trí, dữ liệu bị cache sai, hay integration với callback/ThreadLocal đang không tương thích.

## 2. Mô hình đúng: `SecurityContext` nằm trong Reactor `Context` của subscription

Trong WebFlux, **`ReactiveSecurityContextHolder`** là API reactive để truy cập `SecurityContext`. Spring Security đưa context phù hợp vào luồng của request (ví dụ thông qua `ReactorContextWebFilter` và các security filters). Đây là một phần của **Reactor Context**, được truy cập theo `Subscriber`; không phải một `ThreadLocal` mặc định luôn tồn tại trên mọi thread.

```text
HTTP request
  └─ SecurityWebFilterChain xác thực
       └─ Subscriber của request mang Reactor Context
            └─ handler Mono/Flux
                 ├─ flatMap(service.read())     -> cùng ngữ cảnh subscriber
                 ├─ then(audit.write())        -> cùng ngữ cảnh subscriber
                 └─ zipWhen(profile.load())    -> vẫn được compose vào request
```

Reactor tách **assembly** (tạo mô tả pipeline) và **subscription** (thực thi). Context gắn vào subscriber khi có subscription, lan từ downstream về upstream theo chuỗi các toán tử. `contextWrite(...)` tạo Context mới cho **những toán tử upstream của chính nó**. `Mono.deferContextual(...)` đọc Context tại lúc subscribe. Do đó:

- Cùng một `Mono` có thể được subscribe hai lần với hai Context khác nhau.
- Tạo `Mono` ở ngoài một phương thức không tự làm mất context. **Đường subscribe và phạm vi `contextWrite` mới là yếu tố quyết định.**
- `publishOn`/`subscribeOn` chuyển scheduler hoặc thread, **không mặc định đánh rơi Reactor Context** khi vẫn là một pipeline Reactor hợp lệ.
- `SecurityContextHolder.getContext()` truyền thống dùng ThreadLocal và không phải API để đọc danh tính reactive theo cách chung. Hãy dùng `ReactiveSecurityContextHolder.getContext()` hoặc truyền `Authentication`/principal như tham số khi thiết kế luồng.
- Reactor Context thường đi qua `flatMap`, `concatMap`, `then`, `zip` và nhiều toán tử compose khác nhờ các subscription con do operator quản lý. Không đánh đồng chúng với một lời gọi `.subscribe()` tự tạo trong code nghiệp vụ.

API cơ bản:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

Đây là **đoạn trích** để minh họa; sẽ có project kiểm thử hoàn chỉnh ở mục 5. Khi không có `SecurityContext` trong subscriber, `getContext()` có thể hoàn tất rỗng. Không nên thay việc kiểm tra quyền bằng `.defaultIfEmpty("admin")` hoặc một danh tính giả định. Trong test, một chuỗi `"ANONYMOUS"` dùng để quan sát tình huống rỗng là hợp lệ, nhưng **không cấp quyền** cho user đó trong production.

## 3. Lỗi gốc: `.subscribe()` thủ công mở một subscription mới

Ví dụ dưới đây minh họa **sai cách** thực hiện audit trong code ứng dụng (đoạn trích, không phải project độc lập):

```java
public Mono<String> handleRequest(String itemId) {
    auditService.recordCurrentUser("view-item:" + itemId)
        .subscribe(); // SAI: tạo subscriber riêng, tách khỏi HTTP request

    return itemService.loadDescription(itemId);
}
```

`recordCurrentUser(...)` có thể gọi `ReactiveSecurityContextHolder.getContext()`. Khi dùng `.subscribe()` trực tiếp, chương trình tạo một subscriber thứ hai mà mặc định không mang Context request đang được subscribe qua server. Tác vụ audit còn có thể chạy **trước khi** quyền truy cập được quyết định đầy đủ, chạy song song không kiểm soát, sống lâu hơn request bị cancel và phát sinh lỗi không xuất hiện ở `Mono` trả về.

Thay bằng **compose**:

```java
public Mono<String> handleRequest(String itemId) {
    return itemService.loadDescription(itemId)
        .flatMap(description ->
            auditService.recordCurrentUser("view-item:" + itemId)
                .thenReturn(description));
}
```

Ở ví dụ đã sửa, `recordCurrentUser` trả `Mono<Void>` và nằm trong pipeline do server subscribe. `thenReturn(description)` chỉ phát ra mô tả **sau khi audit hoàn thành**. Nếu audit lỗi, request nhận lỗi trừ khi có chính sách xử lý cụ thể; nếu request bị cancel, việc hủy có thể lan tới tác vụ tương ứng. Điều này cũng giúp phản hồi không tuyên bố hoàn thành trước các công việc mà nghiệp vụ yêu cầu.

Có thể thay theo ý nghĩa thao tác:

| Nhu cầu | Toán tử thường phù hợp | Ghi chú |
| --- | --- | --- |
| Gọi async để tạo ra giá trị tiếp theo | `flatMap(value -> service.load(value))` | Không gọi `subscribe()` trong lambda |
| Chạy async rồi giữ lại giá trị ban đầu | `flatMap(value -> audit.write(value).thenReturn(value))` | Audit là một bước bắt buộc |
| Chạy thao tác A rồi B, không dùng giá trị A | `a.then(b)` hoặc `a.then(Mono.defer(() -> b))` | Cả hai được nối vào cùng pipeline |
| Đợi nhiều Publisher cùng hoàn tất | `Mono.when(a, b)` | Nếu một tác vụ lỗi, kết quả tổng hợp phản ánh lỗi/hủy theo operator |
| Bổ sung giá trị liên quan | `zipWhen(value -> service.find(value))` | Context của operator được quản lý |
| Ghi log đồng bộ không phát sinh async Publisher | `doOnNext`, `doOnError`, `doFinally` | Không nhét async `.subscribe()` vào callback |
| Chỉ tạo Publisher khi thật sự được subscribe | `Mono.defer(() -> createPublisher())` | Đúng thời điểm tạo nhưng vẫn phải compose |
| Truy cập Reactor Context tại lúc subscribe | `Mono.deferContextual(ctx -> ...)` | Phù hợp dữ liệu context tự định nghĩa |

`doOnNext(v -> service.write(v))` **không chạy** `Mono` trả về nếu không ai subscribe vào Publisher đó; `doOnNext(v -> service.write(v).subscribe())` lại tạo subscription tách rời. Cả hai đều không tương đương `flatMap(v -> service.write(v))`.

### Điều gì xảy ra với `block()`?

```java
String username = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .block(); // Không dùng ở luồng xử lý WebFlux.
```

`block()` tạo subscription của chính nó và chặn thread, không có bảo đảm mang Reactor Context của request vào subscription mới. Trên thread event-loop, nó còn có thể ném lỗi liên quan blocking hoặc làm nghẽn hệ thống. Cách đúng là trả `Mono<String>` và tiếp tục `flatMap`/`map` hoặc dùng principal được framework inject.

## 4. Publisher “nằm ngoài chuỗi”: cần phân biệt hai trường hợp

### 4.1. Publisher được xây từ trước nhưng **compose khi sử dụng**: thường vẫn đúng

```java
private final Mono<String> userSource =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());

// Trong một phương thức nhận request:
public Mono<String> decorate(String itemId) {
    return itemService.loadDescription(itemId)
        .flatMap(value -> userSource.map(user -> user + ": " + value));
}
```

`userSource` được assembly từ trước, nhưng `flatMap` subscribe nó **trong pipeline** của request. `ReactiveSecurityContextHolder.getContext()` đọc Context tại subscription time nên có thể thấy đúng người dùng. Dùng mẫu này vẫn cần chú ý tính tái sử dụng, side effect và dữ liệu nhạy cảm; không tự áp dụng `cache()` lên Publisher phụ thuộc vào user.

### 4.2. Publisher được subscribe từ nơi khác: Context của request không tự đi theo

```java
private final Mono<String> userSource =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());

// Trong controller/service:
public Mono<String> bad(String itemId) {
    userSource.subscribe(user -> auditSink.send(user, itemId));
    return Mono.just("accepted");
}
```

Subscriber thứ hai được tạo trực tiếp, nên Context nó nhìn thấy không tự kế thừa Context của request. Nếu `getContext()` hoàn tất rỗng, callback success có thể **không hề được gọi**. Request trả `"accepted"` cũng không bảo đảm event đã được ghi.

### 4.3. Publisher không được subscribe: thao tác không chạy

```java
public Mono<String> bad(String id) {
    itemService.save(id);     // chỉ tạo Mono, chưa chạy
    return Mono.just("saved"); // thông báo sai tình trạng
}
```

Sửa:

```java
public Mono<String> good(String id) {
    return itemService.save(id).thenReturn("saved");
}
```

### 4.4. Cẩn thận với `cache()`, `share()` và hot Publisher

```java
// Nguy hiểm nếu shared giữa các request khác nhau:
private final Mono<String> cachedUser = currentUsername().cache();
```

Nếu subscription đầu tiên dưới tài khoản Alice làm cache giá trị `"alice"`, request của Bob sau đó có thể nhận lại `"alice"` từ cache mà không thực hiện việc đọc context mới. Đây là **rò rỉ dữ liệu/quyền liên request**, không phải chỉ lỗi context rỗng. Không cache kết quả phụ thuộc danh tính ở một `Mono` singleton dùng chung; cache dữ liệu nếu thật sự cần thì dùng khóa theo tenant/user và kiểm soát phân quyền, TTL, invalidation rõ ràng. `Sinks.Many`/hot stream có subscriber riêng; không giả định Context của producer sẽ tự truyền tới mọi consumer.

Một `Publisher` là **cold** hay **hot**, đã được subscribe chưa và ai giữ reference mới quyết định cách nó hoạt động; vị trí tạo biến trong file Java đơn thuần không đủ để kết luận mất Context.

## 5. Project JUnit 5 + StepVerifier có thể chạy để tái hiện và sửa lỗi

Ví dụ sau dùng **Java 17, Spring Boot 3.5.0, Reactor Test và Spring Security 6.x**. Project này chạy test Reactor **không cần Redis, IdP hoặc HTTP server**. Nó minh họa trực tiếp sự khác biệt giữa subscription tách rời, operator được compose, ranh giới của `contextWrite` và cache chia sẻ. Đây là bộ test cho **cơ chế Context**; kiểm thử qua HTTP thực tế được bổ sung ở mục 8.

Tạo cấu trúc:

```text
reactive-context-diagnostics/
├── pom.xml
└── src/test/java/example/context/ContextLossTest.java
```

**`pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>reactive-context-diagnostics</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Spring Boot dependency management chọn các phiên bản Reactor và Spring Security tương thích. `spring-boot-starter-test` bao gồm JUnit Jupiter, Reactor Test và công cụ assertion; không cần viết `@SpringBootApplication` chỉ để chạy các unit test không dùng Spring context dưới đây.

**`src/test/java/example/context/ContextLossTest.java`:**

```java
package example.context;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ContextLossTest {
    private static final Authentication ALICE =
        new TestingAuthenticationToken("alice", "test", "ROLE_USER");
    private static final Authentication BOB =
        new TestingAuthenticationToken("bob", "test", "ROLE_USER");

    // "ANONYMOUS" chỉ là giá trị quan sát trong test,
    // KHÔNG phải danh tính được cấp quyền trong production.
    private static Mono<String> currentUsername() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .defaultIfEmpty("ANONYMOUS");
    }

    @Test
    void directContextWriteIsVisibleAtSubscription() {
        Mono<String> request = currentUsername()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE));

        StepVerifier.create(request)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void manualSubscribeInsidePipelineCreatesDetachedSubscriber() {
        AtomicReference<String> observed = new AtomicReference<>("not-run");

        Mono<String> request = Mono.defer(() -> {
            // Cố ý mô phỏng anti-pattern để chẩn đoán.
            // currentUsername() là Mono đồng bộ trong ví dụ này.
            currentUsername().subscribe(observed::set);
            return Mono.just("response-complete");
        }).contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(ALICE));

        StepVerifier.create(request)
            .expectNext("response-complete")
            .verifyComplete();

        assertEquals("ANONYMOUS", observed.get());
    }

    @Test
    void flatMapKeepsInnerPublisherUnderRequestContext() {
        Mono<String> request = Mono.just("request")
            .flatMap(ignored -> currentUsername())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE));

        StepVerifier.create(request)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void publisherBuiltOutsideChainStillUsesSubscriptionContext() {
        Mono<String> builtEarlier = currentUsername();

        Mono<String> request = Mono.just("request")
            .flatMap(ignored -> builtEarlier)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE));

        StepVerifier.create(request)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void publishOnChangesThreadButKeepsReactorContext() {
        Mono<String> request = Mono.just("request")
            .publishOn(Schedulers.parallel())
            .flatMap(ignored -> currentUsername())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE));

        StepVerifier.create(request)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void contextWriteOnlyAffectsItsUpstreamScope() {
        Mono<String> wrongScope = Mono.just("ready")
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE))
            .then(currentUsername());

        StepVerifier.create(wrongScope)
            .expectNext("ANONYMOUS")
            .verifyComplete();

        Mono<String> correctScope = Mono.just("ready")
            .then(currentUsername())
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE));

        StepVerifier.create(correctScope)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void eachSubscriptionCanSeeDifferentUser() {
        Mono<String> reusable = currentUsername();

        StepVerifier.create(reusable.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE)))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(reusable.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(BOB)))
            .expectNext("bob")
            .verifyComplete();
    }

    @Test
    void sharedCacheDemonstratesCrossUserLeakageAntiPattern() {
        // Cố ý minh họa cách không được viết trong production.
        Mono<String> cachedAcrossRequests = currentUsername().cache();

        StepVerifier.create(cachedAcrossRequests.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE)))
            .expectNext("alice")
            .verifyComplete();

        // Kết quả là "alice" dù context của subscriber mới là Bob.
        StepVerifier.create(cachedAcrossRequests.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(BOB)))
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void composedAsyncFailureReachesRequest() {
        Mono<String> request = currentUsername()
            .flatMap(user -> Mono.<Void>error(
                    new IllegalStateException("audit unavailable"))
                .thenReturn(user))
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(ALICE));

        StepVerifier.create(request)
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && "audit unavailable".equals(error.getMessage()))
            .verify();
    }
}
```

**Chạy:**

```bash
mvn test
```

Khi Maven có thể tải dependency và JDK 17+ đã được cài, kỳ vọng **9 phép thử pass**; stdout chi tiết do Maven/Surefire quyết định. Hai phép thử `manualSubscribe...` và `sharedCache...` được viết để **khẳng định lại lỗi**: chúng pass vì kết quả `"ANONYMOUS"` và `"alice"` sai ngữ cảnh đúng như anti-pattern đang mô phỏng. Đây là regression test học tập, **không phải hành vi hệ thống nên duy trì**.

Điểm đáng nhớ từ test:

- `flatMap` sử dụng publisher con trong pipeline của subscription hiện tại.
- `Mono` được assembly bên ngoài nhưng subscribe bởi `flatMap` vẫn đọc đúng context.
- `publishOn` đổi thread và không làm mất Reactor Context theo mặc định.
- `contextWrite` không cấp context cho các toán tử nằm downstream ngoài phạm vi của nó.
- `.cache()` trên dữ liệu phụ thuộc principal có thể tạo lỗ hổng rò rỉ giữa user.
- Lỗi async được compose có thể đi qua chuỗi `onError`; lỗi từ subscription tách rời thường không được phản ánh vào kết quả request.

## 6. Phân tích sâu các “điểm gãy” trong code

### 6.1. `subscribe()` giấu trong `doOnNext`/`map`

**Sai:**

```java
return repository.findById(id)
    .doOnNext(entity ->
        auditService.writeAsync(entity.getId()).subscribe())
    .map(Entity::getName);
```

**Đúng (audit bắt buộc):**

```java
return repository.findById(id)
    .flatMap(entity ->
        auditService.writeAsync(entity.getId())
            .thenReturn(entity.getName()));
```

Trong bản đúng, lỗi audit sẽ phát ngược lên request; bản sai có hai subscription độc lập. Nếu audit chỉ là telemetry không bắt buộc, vẫn cần một kiến trúc thu nhận event rõ ràng (ví dụ message broker/outbox/worker chịu trách nhiệm), cùng yêu cầu retry/error handling và context identity được truyền như dữ liệu đã kiểm soát. Không dùng `subscribe()` tách rời làm “hàng đợi” không bảo đảm.

### 6.2. Sử dụng `Mono.defer` chưa đủ nếu bên trong vẫn tự `subscribe()`

**Sai:**

```java
return Mono.defer(() -> {
    permissionService.checkCurrentUser().subscribe();
    return Mono.just("done");
});
```

`defer` trì hoãn việc tạo Publisher tới subscription time, nhưng lambda vẫn gọi `.subscribe()` thứ hai. **Đúng:** trả chuỗi composed:

```java
return Mono.defer(() ->
    permissionService.checkCurrentUser()
        .thenReturn("done"));
```

`Mono.deferContextual(ctx -> ...)` cũng không tự sửa một nested `.subscribe()`; nó chỉ cho phép đọc Context của subscriber đang chạy. Không nên lấy một `ContextView` có toàn bộ thông tin bảo mật rồi truyền tùy tiện sang tác vụ khác; khi thật sự cần crossing async boundary, truyền **các giá trị đã được xác thực và được phép chia sẻ**, có hạn chế phạm vi.

### 6.3. `flatMap` có thực sự mất Context không?

Trong chuỗi Reactor bình thường:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMap(authentication ->
        customerService.load(authentication.getName()));
```

`customerService.load` được subscribe bởi `flatMap`, nên nó có thể dùng Context của request nếu bản thân không phá chuỗi. Nếu trong implementation `load` lại chạy `future.thenAccept(...); someMono.subscribe()` thì điểm gãy nằm **bên trong service**, không phải do `flatMap`.

`subscribeOn`, `publishOn`, `delayElement` và gọi vào `Schedulers.boundedElastic()` thông qua operator Reactor không mặc định xóa Reactor Context. Ngược lại, `new Thread`, `Executor.execute`, `CompletableFuture.thenApply` là API Java async không hiểu Reactor Context một cách tự động. Khi nối lại thành `Mono`/`Flux`, phần **Reactor của pipeline** có thể đọc Context, nhưng logic đang chạy **bên trong callback ngoại lai** không đương nhiên có cùng context. Đừng suy luận mất ngữ cảnh chỉ từ tên thread trong log.

### 6.4. `then()`: Context vẫn còn, nhưng đừng đặt `contextWrite` sai phía

```java
Mono<String> wrong = Mono.just("start")
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))
    .then(readCurrentUsername()); // readCurrentUsername không ở upstream contextWrite
```

```java
Mono<String> correct = Mono.just("start")
    .then(readCurrentUsername())
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));
```

Đây là ví dụ **chỉ minh họa phạm vi operator**, với `auth` và `readCurrentUsername()` đã khai báo. Trong ứng dụng thật, framework thiết lập security context sau xác thực; không dùng `withAuthentication(auth)` để cấp quyền tùy ý cho một request. Dùng `contextWrite` để thiết lập context test có chủ đích hoặc trong hạ tầng bảo mật đáng tin.

### 6.5. `Mono.fromFuture`, `@Async`, raw `Executor`

**Đoạn minh họa không độc lập:** giả sử `legacyClient.callAsync(userId, action)` trả `CompletableFuture<Result>`:

```java
public Mono<Result> good(String action) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(authentication ->
            Mono.fromFuture(
                () -> legacyClient.callAsync(authentication.getName(), action)));
}
```

Lấy danh tính **trong pipeline đang có Context**, rồi truyền username được phép sử dụng như tham số tường minh sang API async. Không mong callback Java bên trong `CompletableFuture` tự gọi được `ReactiveSecurityContextHolder.getContext()`; và không lưu `Authentication` object vào job log/queue nếu không thật sự cần. Trong hệ thống nhiều tenant, phải xác định rõ tenant/authorization phù hợp tại thời điểm tạo yêu cầu, và worker tiếp nhận cần tự thực thi các kiểm soát được giao.

Nếu callback bên ngoài tạo một `Mono` rồi tự `.subscribe()`, nó lại mở subscriber mới. Nếu dùng `Mono.fromFuture`/`Mono.create` đúng cách để bridge kết quả của callback về **một** Publisher và return Publisher này, client của bridge vẫn compose được vào request. Với `Mono.create`, quản lý cancellation/resource cleanup và chỉ complete sink một cách an toàn; không đánh dấu thành công trước khi callback thật hoàn tất.

### 6.6. `SecurityContextHolder` kiểu Servlet và MDC/ThreadLocal

Trong servlet stack, `SecurityContextHolder` mặc định dựa vào thread-bound strategy. WebFlux vận hành nonblocking, có thể đổi thread ngay giữa các operator. Dùng `SecurityContextHolder.getContext()` ở service reactive thường cho kết quả sai hoặc thiếu. Dùng API reactive hoặc principal injection.

Reactor 3.5+ có tích hợp thư viện Micrometer Context Propagation để **khôi phục một số ThreadLocal đã đăng ký accessor**, gồm chế độ hạn chế/mặc định và chế độ tự động (`Hooks.enableAutomaticContextPropagation()`). Tính năng này chủ yếu phục vụ bridge giữa Reactor Context và `ThreadLocal` (ví dụ tracing/MDC) theo cấu hình; **không phải một cơ chế tự động sửa mọi `.subscribe()` tách rời**, cũng không có nghĩa là được bỏ `ReactiveSecurityContextHolder` hoặc tự gắn quyền người dùng vào ThreadLocal toàn cục.

Nếu log mất `traceId`/MDC nhưng `ReactiveSecurityContextHolder` vẫn thấy auth, đây có thể là vấn đề propagation của telemetry khác với vấn đề mất SecurityContext. Tránh trộn hai loại lỗi trong một giả thuyết.

### 6.7. Custom `WebFilter` chạy trước/sai vị trí

Một custom `WebFilter` chạy **trước** khi bộ lọc Spring Security thiết lập context có thể đọc rỗng ngay cả khi các phần sau đã xác thực thành công. Kiểm tra cấu hình `SecurityWebFilterChain`, các matcher và thứ tự lọc thực tế.

`WebFilter.filter(...)` phải **trả về** `Mono<Void>` được compose, thường chứa `chain.filter(exchange)`; đừng gọi `chain.filter(exchange).subscribe()` rồi trả `Mono.empty()`. Nếu cần kiểm tra `Authentication` trong filter, bố trí nó ở vị trí phù hợp với security filter chain; chỉ log tên/trạng thái kiểm thử đã hạn chế nhạy cảm, không log toàn bộ security object hay token.

### 6.8. `@PreAuthorize` và thao tác chạy ngoài luồng được bảo vệ

Reactive method security dựa vào Reactor Context, thích hợp cho phương thức trả `Mono`/`Flux`. Nếu một method có annotation security khởi chạy side effect bằng `.subscribe()` riêng và lập tức trả `Mono.empty()`, việc hoàn tất của response hoặc điều kiện authorization trên chuỗi được trả **không tự quản lý** side effect kia. Với thao tác có quyền, luôn nối thao tác đó vào Publisher được trả về để chính sách bảo mật và xử lý lỗi/cancel áp dụng theo đường thực thi dự kiến.

Đừng “giải quyết” context rỗng bằng cách tạo `UsernamePasswordAuthenticationToken` giả rồi `contextWrite(withAuthentication(...))` trong service nghiệp vụ. Làm vậy có thể bỏ qua xác thực thật, gây leo thang quyền. Khi không đủ context, fail closed theo cơ chế authorization được thiết kế.

## 7. Quy trình chẩn đoán theo thứ tự có thể kiểm chứng

### Bước 1 — Xác nhận request có được xác thực không

Kiểm tra endpoint thật: request có Bearer token/cookie phù hợp không, SecurityWebFilterChain nào match, authentication thành công hay chưa, `401`/`403`/redirect có phải do quyền hoặc CSRF thay vì context? Khi chạy test, đảm bảo `WebTestClient` đã áp dụng security integration. **Không** ngầm coi mọi `Mono.empty()` là do `.subscribe()`.

Trong handler, một đoạn thăm dò hạn chế phạm vi có thể dùng:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(auth -> "authPresent=" + (auth != null))
    .defaultIfEmpty("authPresent=false");
```

**Đoạn trích** trên chỉ cho biết có Authentication object; `AnonymousAuthenticationToken` cũng là một `Authentication`, nên muốn phân biệt người dùng thật với anonymous phải xét loại token/chính sách. Tránh log credentials, bearer raw token hoặc nguyên vẹn `SecurityContext`.

### Bước 2 — Vẽ đường subscribe, không chỉ nhìn call stack

Dọc theo luồng `handler → service → repository/client → callback`, ghi nhận những điểm:

- Lời gọi `.subscribe(`, `.block(`, `.toFuture()`, `CompletableFuture.*Async`, `@Async`, `Executor.execute`, `new Thread`, `Sinks` được consume riêng.
- `Mono` được tạo nhưng không trả lại, hoặc `.map`/`.doOnNext` gọi phương thức trả `Mono` mà không compose.
- `.contextWrite(...)` xuất hiện ở giữa chain; các operator cần context có nằm **upstream** của nó không?
- `cache()`, `share()`, `replay()`, Publisher lưu trong bean singleton có chứa kết quả phụ thuộc identity hay không?
- Custom WebFilter hoặc event listener tạo subscription ngoài vòng đời request.

Một bản đồ ngắn:

```text
request subscription + security context
  ├─ controller.flatMap(service) ------------ OK
  │    └─ repository.find().flatMap(audit) -- OK
  ├─ controller.doOnNext(v -> audit.subscribe())
  │                                      └── NEW subscriber, Context mặc định khác
  └─ handler -> executor.execute(callback)
                                         └── raw callback không tự có Reactor Context
```

### Bước 3 — Dùng “probe” ở trước và sau điểm nghi vấn

Đặt các kiểm tra tạm thời gọi `ReactiveSecurityContextHolder.getContext()` **trong Publisher đang được compose**, xác nhận có context ở controller, service, trước/sau operator, trong inner Publisher và ở callback thực thi. Ví dụ khi debug test:

```java
static Mono<String> probeUser(String stage) {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .defaultIfEmpty("<no-security-context>")
        .doOnNext(user -> System.out.println(stage + ": " + user));
}
```

Đây là **đoạn trích dùng trong môi trường test**; log username trên production cần theo chính sách riêng. Dùng `.flatMap(v -> probeUser("after-service").thenReturn(v))` để probe tham gia pipeline. Tránh gọi `probeUser("stage").subscribe()` trong khi debug, vì chính probe này sẽ tạo lỗi giống triệu chứng đang kiểm tra.

Nếu cần marker không nhạy cảm theo request, có thể thêm `requestId` qua `contextWrite(ctx -> ctx.put("requestId", id))` ở một lớp tích hợp đáng tin và đọc bằng `Mono.deferContextual(...)`. Marker này giúp phân biệt subscriber context, nhưng **không thay thế security identity** và không tự chứng minh context bảo mật còn nguyên.

### Bước 4 — Kiểm tra hủy, lỗi và thời điểm hoàn tất

Tác vụ bị `.subscribe()` riêng thường không chịu cùng cancellation với request. Một request có thể trả 200 trước khi audit/permission check hoàn tất; lỗi async không tới `doOnError` của pipeline chính. Khi chuyển sang `flatMap/then`, xác nhận:

- Kết quả được phát **sau khi** tác vụ bắt buộc hoàn tất;
- Lỗi được propagate hoặc được xử lý bằng một chính sách rõ ràng;
- Cancellation/budget thời gian được quản lý theo yêu cầu;
- Tác vụ không thực thi khi luồng chính chưa được subscribe.

Dùng `StepVerifier` kiểm tra `expectNext`, `verifyComplete`, `expectErrorMatches` và `verifyThenAssertThat` khi cần quan sát luồng; dùng scheduler/test clock có kiểm soát với test bất đồng bộ. Hạn chế `.block()` trong production; dùng `.block()` trong fixture test chỉ khi thực sự hợp lý và không làm mất ý nghĩa test Context.

### Bước 5 — So sánh hai request với hai danh tính

Kiểm tra Alice/Bob **độc lập** qua cùng service/reusable Publisher, xác nhận không còn cache sai, state singleton hoặc một ThreadLocal tồn dư. Nếu dữ liệu liên quan đến tenant, thêm kiểm tra chéo tenant; request Bob phải không thể xem dữ liệu đã resolve cho Alice chỉ vì một `Mono` được cache chung.

### Bước 6 — Gỡ instrumentation tạm và giữ regression tests

Tách log tạm ra khỏi production, giữ test tái hiện bug và test thành công sau sửa. Khi cần đi sâu, Reactor hỗ trợ `checkpoint("stage-name")` để gắn dấu mốc cho assembly traceback và `Hooks.enableContextLossTracking()` trong một số trường hợp integration với operator không giữ Context đúng; các công cụ này **không bảo đảm phát hiện mọi `subscribe()` thủ công** và có overhead. Dùng log/metrics có kiểm soát, không dump toàn bộ Context, credentials, token hoặc thông tin cá nhân.

## 8. Đối chiếu ở mức Spring Security WebFlux và `WebTestClient`

Unit test `contextWrite(withAuthentication(...))` ở mục 5 chứng minh cơ chế Reactor, **không chứng minh** request production thật đã qua xác thực. Khi tích hợp vào ứng dụng WebFlux:

1. Đảm bảo `SecurityWebFilterChain` bảo vệ URL và bật đúng phương thức authentication (JWT, session, HTTP Basic, OAuth2 Login tùy hệ thống).
2. Test endpoint có authentication thành công: `WebTestClient` dùng `mockUser()` hoặc `mockJwt()` thông qua `spring-security-test` để kiểm tra luồng security context/authorization ở mức test. Bài test này **giả lập** authentication, không kiểm tra chữ ký/issuer JWT.
3. Test request không có authentication và request thiếu quyền; xác nhận status 401/403 hoặc redirect theo policy thật.
4. Với lỗi do `subscribe()` thủ công, viết một test ban đầu chứng minh service mất danh tính, sửa thành compose rồi yêu cầu user được thấy ở mọi tầng. Kiểm tra async error và cancel riêng nếu quan trọng.
5. Nếu nghi một WebFilter chạy quá sớm, log/trace thứ tự filter của ứng dụng hoặc cô lập filter trong test, điều chỉnh vị trí đúng rồi test lại.

**Mảnh ghép minh họa, phụ thuộc ApplicationContext và Spring Security filter đã cấu hình** (không phải ví dụ Java độc lập):

```java
WebTestClient client = WebTestClient.bindToApplicationContext(context)
    .apply(SecurityMockServerConfigurers.springSecurity())
    .build();

client.mutateWith(SecurityMockServerConfigurers.mockUser("alice"))
    .get()
    .uri("/api/whoami")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("alice");
```

Để biên dịch đoạn này cần các import liên quan `WebTestClient`, `ApplicationContext`, `SecurityMockServerConfigurers` và dependency `spring-security-test` ở scope test, cùng endpoint `/api/whoami` trả username từ `ReactiveSecurityContextHolder` trong ứng dụng đang test.

**Phân biệt:** `mockUser()`/`mockJwt()` phù hợp kiểm tra Context/ủy quyền trong pipeline; nếu cần chứng minh chính đường đọc Bearer decoder/chữ ký thực tế, phải gửi token thật qua `Authorization` và cấu hình `ReactiveJwtDecoder` thật trong integration test. Đừng biến bài debug Context thành giả định rằng JWT decoder đã được kiểm thử.

## 9. Khi nào cố tình tách tác vụ khỏi request?

Một số nghiệp vụ cần background work tiếp tục sau khi HTTP response hoàn tất. Khi đó có **một ranh giới tin cậy mới**: tác vụ nền không còn được phép ngầm dựa vào `ReactiveSecurityContextHolder` của HTTP request. Thiết kế phù hợp:

- Trong request đã xác thực, lấy các trường **đã được cho phép** (ví dụ user ID/tenant ID/action ID) theo pipeline reactive; đánh giá quyền trước khi tạo job.
- Lưu event/job vào hệ thống đáng tin (outbox/message broker/queue) trong quy trình có bảo đảm và error handling rõ ràng. Trả `202 Accepted` chỉ khi công việc đã được nhận theo tiêu chí nghiệp vụ.
- Consumer/worker sử dụng danh tính dịch vụ, chính sách ủy quyền và thông tin đã ký/kiểm soát riêng; nếu quyền có thể bị thu hồi, cần kiểm tra lại ở thời điểm thực thi theo yêu cầu.
- Định nghĩa retry, dead-letter, idempotency, timeout, auditing, correlation ID và phạm vi dữ liệu nhạy cảm. Tránh serializing toàn bộ `Authentication`/`SecurityContext` vào message.
- Khi thật sự cần context cho thư viện tương thích Reactor, context phải được thiết lập **tường minh bởi một thành phần tin cậy** dựa trên identity/authorization đã xác minh; không sao chép mù quáng `SecurityContext` request vào luồng nền chạy lâu.

Phương án `auditService.record(...).subscribe()` trong controller **không** cung cấp queue, durable delivery, kiểm soát quyền hay error handling nói trên. Nếu hoạt động phải thực hiện đồng bộ theo nghĩa nghiệp vụ, hãy compose trong pipeline; nếu thực sự là asynchronous workflow độc lập, hãy thiết kế ranh giới đó thành hệ thống riêng.

## 10. Những ngộ nhận và lỗi phổ biến

| Ngộ nhận / thao tác | Vì sao sai | Cách làm phù hợp |
| --- | --- | --- |
| “Đổi thread bằng `publishOn` làm mất SecurityContext” | Reactor Context theo subscriber, không theo thread | Trước tiên tìm subscription tách rời, contextWrite sai phạm vi hoặc bridge callback |
| “Publisher được khởi tạo trong bean field sẽ luôn thiếu context” | Context thường được đọc khi subscribe | Kiểm tra nó được compose hay tự subscribe/cache/share |
| “`Mono.defer()` tự sửa context mất” | `defer` không sửa nested `.subscribe()` | Bỏ subscribe thủ công và return publisher được compose |
| “`doOnNext(x -> service.save(x))` đã lưu rồi” | `Mono` được tạo nhưng không có subscriber | `flatMap(x -> service.save(x))` hoặc `then(...)` |
| “Phải gọi `.subscribe()` để WebFlux làm việc” | Spring WebFlux là subscriber của Publisher được handler/filter trả về | Ở tầng controller/service/filter, trả Mono/Flux |
| “Dùng `.block()` để đọc username trong service reactive” | Blocking + subscription riêng, có thể nghẽn event-loop | Compose reactive hoặc principal injection |
| “`SecurityContextHolder` luôn đọc được user như MVC” | ThreadLocal không phải contract Context của WebFlux | Dùng `ReactiveSecurityContextHolder` |
| “Đăng ký automatic ThreadLocal propagation là đủ” | Chỉ bridge ThreadLocal có accessor, không gắn mọi subscriber vào request | Kiểm tra Context Reactor và boundary thật |
| “Nếu `getContext()` rỗng thì cấp một admin mặc định” | Bỏ qua xác thực, mở đường leo thang quyền | Giữ deny-by-default, trả lỗi/anonymous đúng chính sách |
| “Chỉ test với Alice là đủ” | Shared cache/singleton có thể giữ user đầu tiên | Test chéo Alice/Bob/tenant |
| “`doOnError` của request sẽ thấy lỗi background `.subscribe()`” | Subscription mới có lifecycle và error path khác | Compose hoặc dùng queue/worker có giám sát |
| “Không thấy auth nghĩa là filter hỏng” | Có thể request chưa xác thực hoặc filter chạy trước authentication | Kiểm tra matching, thứ tự filter và status 401/403 |

Một lỗi ít thấy hơn: chỉ báo `"user=alice"` trong `doOnNext` rồi kết luận downstream không mất Context. Nếu `flatMap` bên trong gọi callback ngoại lai rồi tạo subscription khác, Context có thể mất **sau** điểm log đó. Muốn chẩn đoán đúng phải probe trong Publisher nằm ở bước bị nghi, dưới đúng subscriber.

## 11. Checklist trước khi chốt sửa lỗi

1. Trong đường thực thi HTTP reactive, controller, filter và service **trả** `Mono`/`Flux` được compose; không gọi `.subscribe()`/`.block()` để thực hiện thao tác nghiệp vụ cần Context.
2. Phân biệt request chưa xác thực với Context mất; kiểm tra status, `SecurityWebFilterChain`, filter order, anonymous authentication và quyền thật.
3. Các `Publisher` tạo ở nơi khác đều được xem theo **lúc subscribe**; tránh singleton `cache()` chứa identity/data theo user hoặc tenant.
4. `contextWrite` có phạm vi upstream đúng; không cài authentication giả vào nghiệp vụ để lấp lỗi.
5. Bridge với `CompletableFuture`, executor và thư viện callback được thiết kế sao cho kết quả trở về pipeline, đồng thời chỉ truyền dữ liệu identity/tenant đã được cho phép nếu callback cần.
6. Test JUnit có đủ ca `manual subscribe` bị mất context, `flatMap` đúng, `publishOn` đúng, phạm vi `contextWrite`, nhiều user, cache rò rỉ và async error propagation.
7. Test tích hợp WebFlux chứng minh context truy cập được trong request thật với authentication đã cấu hình. Test security theo phương thức xác thực thực tế khi cần.
8. Dữ liệu người dùng/token không xuất hiện trong log Context; tác vụ background có ranh giới bảo mật, retry và auditing riêng.
9. Lỗi context được sửa tại **điểm gãy subscription**; không “sửa” bằng cách tắt authorization, bỏ CSRF hoặc cấp quyền mặc định.

## Tài liệu tham khảo chính thức

- Spring Security 6.5 — Reactive method security và `ReactiveSecurityContextHolder`: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security 6.5 — WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security API — `ReactiveSecurityContextHolder`: https://docs.spring.io/spring-security/site/docs/6.5.0/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Project Reactor — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor — From Reactive Programming to `subscribe()`: https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html
- Project Reactor — Context Propagation Support: https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html
- Project Reactor — Testing with `StepVerifier`: https://projectreactor.io/docs/core/release/reference/testing.html
