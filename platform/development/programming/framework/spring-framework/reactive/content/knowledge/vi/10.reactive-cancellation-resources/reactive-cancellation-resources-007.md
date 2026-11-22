# Tránh subscribe lồng nhau làm mất liên kết lỗi và hủy

**Ngữ cảnh:** Spring Framework Reactive → **Hủy và tài nguyên**.

Trong Project Reactor, một `Mono<T>` hoặc `Flux<T>` là một `Publisher`: nó mô tả công việc và chuỗi tín hiệu. Khi gọi `subscribe()`, bạn tạo **một subscription mới**, với subscriber, nhu cầu dữ liệu (`request`), đường truyền `onError`, vòng đời `onComplete` và quyền hủy (`cancel`) của chính nó.

Một sai lầm phổ biến là gọi `subscribe()` **bên trong** callback của một chuỗi reactive đang chạy:

```java
return loadOrder(id)
        .doOnNext(order -> reserveStock(order).subscribe());
```

Mã này có thể trông như “tải đơn hàng rồi giữ hàng”, nhưng thực chất nó tạo **hai subscription độc lập**:

1. Subscription cha xử lý `loadOrder(id)` rồi có thể hoàn tất.
2. Subscription con do `reserveStock(order).subscribe()` tự tạo, không còn là một phần của kết quả mà phương thức `return` trả về.

Hệ quả: **cha có thể thành công trước khi con hoàn tất, lỗi của con không tự đi tới `onErrorResume`/HTTP handler của cha, và hủy cha không tự động hủy con**. Side effect con có thể tiếp tục sau khi client đã ngắt kết nối, làm rò rỉ tài nguyên, gửi dữ liệu trễ hoặc thực hiện công việc không còn cần thiết.

**Cách sửa khi công việc con là một phần của yêu cầu cha:** không subscribe con; **trả publisher của con vào operator kết hợp** như `flatMap`, `concatMap`, `flatMapMany`, `then` hoặc `Mono.when`. Chỉ subscription ở ranh giới cuối (ví dụ Spring WebFlux, một test hoặc một thành phần chủ động quản lý lifecycle) mới khởi chạy luồng đã kết hợp.

## 1. Cấu trúc đúng: một cây công việc do subscription cuối quản lý

Mẫu chưa đúng:

```java
Mono<Order> pipeline = findOrder(id)
        .doOnNext(order ->
                stockService.reserve(order).subscribe());
```

Mẫu đã kết hợp:

```java
Mono<Order> pipeline = findOrder(id)
        .flatMap(order ->
                stockService.reserve(order).thenReturn(order));
```

Đây là **snippets** cần `Order`, `findOrder` và `stockService` trong ứng dụng. Giả định `reserve(order)` trả `Mono<Void>` và hoàn tất khi thao tác reserve đã thành công theo hợp đồng service.

Sự khác nhau:

| Câu hỏi | `doOnNext(...subscribe())` | `flatMap(...thenReturn(...))` |
|---|---|---|
| Ai subscribe vào công việc reserve? | Callback tự tạo subscription con | Operator `flatMap` quản lý inner subscription |
| Cha đợi reserve thành công mới trả item? | **Không** | **Có**, vì `thenReturn(order)` đợi completion |
| Reserve báo `onError`? | Lỗi thuộc **subscription con** | Lỗi truyền vào **pipeline cha** |
| Client hủy subscription cha? | Không tự hủy subscription con | Hủy được truyền tới inner publisher còn hoạt động |
| Có thể áp dụng timeout/retry cho toàn chuỗi? | Không kiểm soát được công việc con | Có, theo vị trí operator và chính sách |
| Có thể quan sát tất cả bằng `doFinally` cuối chuỗi? | Không thấy vòng đời con độc lập | Quan sát kết thúc/hủy của kết quả đã kết hợp |

**Lưu ý:** hủy được **truyền đi**, nhưng không phải cơ chế hoàn tác giao dịch. Một yêu cầu HTTP/DB đã gửi, thanh toán đã ghi nhận hoặc side effect ngoài hệ thống không nhất thiết bị rollback khi Reactor gọi `cancel()`. Phần này được phân tích riêng ở mục 11.

## 2. Cách đọc ba loại tín hiệu vòng đời

Một subscription reactive có thể đi qua:

```text
subscribe → onSubscribe(subscription)
          → request(n)              (demand, có thể nhiều lần)
          → onNext(value)           (0..N lần; Mono tối đa 1)
          → onComplete()            (thành công)

Hoặc:
subscribe → ... → onError(Throwable) (lỗi, terminal)

Hoặc:
subscribe → ... → cancel()          (hủy, không phải terminal onError)
```

- `onError` và `onComplete` là hai tín hiệu kết thúc khác nhau; một subscription **không nhận cả hai**.
- `cancel()` thể hiện subscriber không còn cần dữ liệu. Nguồn phải phản ứng theo hợp đồng, nhưng hiệu lực thực tế đối với công việc ngoại vi phụ thuộc adapter.
- `doOnError` quan sát lỗi; **không tự phục hồi**.
- `doOnCancel` quan sát thao tác hủy.
- `doFinally(signalType)` chạy sau khi pipeline kết thúc bởi complete, error hoặc cancel, nhận `SignalType.ON_COMPLETE`, `SignalType.ON_ERROR` hay `SignalType.CANCEL`.

Nếu bạn tự `subscribe()` vào inner publisher, inner có **subscription của riêng nó**, nên người hủy hoặc handler lỗi của parent không có cơ chế tự động sở hữu đường đó.

### “Nested subscribe” khác “nested publisher” như thế nào?

```java
Mono<Mono<String>> nestedValue =
        Mono.just("user-1")
                .map(id -> lookupName(id));
```

`map` ở đây tạo một **giá trị kiểu Mono<String>** bên trong Mono ngoài, tức `Mono<Mono<String>>`. Điều này thường chưa đúng nhu cầu nhưng **chưa tự subscribe**; bạn vẫn có thể flatten.

```java
Mono<String> composed =
        Mono.just("user-1")
                .flatMap(id -> lookupName(id));
```

`flatMap` nhận `Publisher` con, đăng ký nó theo vòng đời operator rồi **phát kết quả/con lỗi vào parent**. Đừng thay bằng:

```java
Mono<String> wrong = Mono.just("user-1")
        .map(id -> {
            lookupName(id).subscribe();  // subscription tách khỏi parent
            return id;                  // không phải tên được lookup
        });
```

Ba đoạn là **snippets**; `lookupName` giả định trả `Mono<String>`.

## 3. Vì sao subscribe() trong doOnNext rất dễ sai?

`doOnNext`, `doOnSuccess`, `doOnError` là các **hook quan sát/side effect**, không phải công cụ kết hợp publisher.

Ví dụ:

```java
Mono<Order> result = findOrder(id)
        .doOnNext(order ->
                emailService.sendConfirmation(order)
                        .subscribe());
```

Nếu `sendConfirmation` lỗi, lỗi đó thuộc child subscription. `result.onErrorResume(...)` chỉ nhìn thấy lỗi truyền **qua result**, không nhìn thấy lỗi từ subscription con độc lập. Nếu `sendConfirmation` chưa hoàn tất, `findOrder` vẫn có thể hoàn tất và controller có thể trả response.

Một vài hệ quả khó phát hiện:

- **Mất báo lỗi:** parent hoàn tất 200/202 dù email/stock/payment không thành công; nếu inner subscribe thiếu error consumer, Reactor còn có thể báo lỗi “ErrorCallbackNotImplemented”/dropped error qua cơ chế hook.
- **Mất hủy:** người dùng hủy request nhưng email vẫn gửi hoặc kết nối con vẫn đang mở.
- **Mất trình tự:** công việc sau trong parent có thể chạy mà chưa chờ việc con.
- **Mất backpressure:** demand của parent không tự điều tiết nhu cầu của subscriber mới. `subscribe()` không đối số/consumer thường yêu cầu unbounded cho subscription đó.
- **Mất context:** Reactor `Context`, dữ liệu tracing/security/transaction gắn với subscriber cha không được bảo đảm chuyển sang một subscription con tạo riêng.
- **Mất khả năng kiểm thử:** `StepVerifier` của parent có thể xanh dù child đã thất bại về sau.
- **Khó giải phóng tài nguyên:** handle `Disposable` trả về từ inner `subscribe` bị bỏ đi; không có chủ sở hữu để dispose khi request kết thúc.
- **Retry gây thực thi lặp:** retry parent có thể khởi động nhiều child độc lập nếu mỗi attempt đi qua callback.

**Không phải mọi lời gọi `subscribe()` đều sai:** tại **ranh giới ứng dụng chủ động sở hữu** như command-line main, scheduled background job, test harness hoặc một component được quản lý start/stop, subscribe có thể hợp lệ. Vấn đề là tạo subscription con vô chủ cho một công việc **đáng lẽ thuộc kết quả của yêu cầu hiện tại**.

## 4. Hình dung đường lỗi và hủy bị đứt

### Nested subscribe (bị tách)

```text
HTTP request / parent Subscriber
              |
              v
          findOrder()
              |
          doOnNext(order)
              |  \
              |   \--- reserveStock(order).subscribe()
              |           |
              |           +--- CHILD Subscription
              |                 +--- onError → child handler/hook
              |                 +--- cancel riêng, nếu có handle
              v
       parent onNext + onComplete

Client disconnect → cancel(parent) --X--> child không tự hủy
Parent onErrorResume(...)        --X--> child error không tự tới
```

**Không có mũi tên X** nghĩa không có liên kết quản lý tự động giữa hai subscriptions.

### flatMap (giữ thành phần con trong chuỗi)

```text
HTTP request / Subscriber
             |
             v
         findOrder()
             |
             v
        flatMap(order)
             |
             +--- reserveStock(order) [inner do operator quản lý]
                      |
                      +--- onComplete → tiếp tục thenReturn(order)
                      +--- onError ----→ parent onError
                      +--- cancel ←---- parent cancel
             |
             v
         parent onNext(order), onComplete

Client disconnect → cancel(parent) → cancel(inner còn hoạt động)
```

**Tại sao operator biết inner?** Vì callback `flatMap` **trả về Mono** để Reactor quản lý, thay vì gọi `subscribe` rồi ném handle đi.

## 5. Chọn toán tử kết hợp theo đúng mục đích

| Nhu cầu | Cách hợp lý | Tín hiệu/đặc tính cần biết |
|---|---|---|
| Có một `Mono<A>`, cần gọi `Mono<B>` theo giá trị A | `mono.flatMap(a -> loadB(a))` | Lỗi và hủy của inner thuộc kết quả đã compose |
| Có một `Mono<A>`, cần phát nhiều phần tử `Flux<B>` | `mono.flatMapMany(a -> streamB(a))` | Kết quả là `Flux<B>` |
| Có `Flux<A>`, xử lý nhiều inner publishers đồng thời | `flux.flatMap(a -> process(a), concurrency)` | Có thể xen kẽ kết quả, giới hạn mức đồng thời |
| Có `Flux<A>`, cần giữ thứ tự từng inner | `flux.concatMap(a -> process(a))` | Xử lý từng inner theo thứ tự; không cần nested subscribe |
| Cần chạy B sau khi A **hoàn tất thành công** | `a.then(b)` | B không chạy nếu A lỗi; giá trị A bị bỏ |
| Cần giữ A sau khi side effect B hoàn tất | `a.flatMap(v -> b(v).thenReturn(v))` | Trả lại giá trị ban đầu sau khi B thành công |
| Có các công việc `Mono<Void>` độc lập, cần chờ tất cả | `Mono.when(one, two)` | Chỉ hoàn tất khi các nguồn hoàn tất; lỗi có thể hủy phần còn lại |
| Cần gộp hai Mono **đều phát giá trị** | `Mono.zip(a, b)` | Kết hợp hai giá trị; nếu một nguồn empty thì không có tuple |
| Chỉ muốn ghi nhận item/error | `doOnNext`/`doOnError` | Quan sát, không compose tác vụ con |
| Cần dọn tài nguyên gắn với publisher | `using`/`usingWhen`, `doFinally` tùy ngữ nghĩa | Đảm bảo lifecycle thuộc cùng subscription |

### 5.1. flatMap: nghiệp vụ phụ thuộc giá trị

```java
Mono<ProfileCard> card = findUser(userId)
        .flatMap(user -> avatarService.findAvatar(user.id())
                .map(url -> new ProfileCard(user.name(), url)));
```

**Snippet:** `findUser` và `avatarService` giả định trả `Mono<User>` và `Mono<String>`. Nếu tìm user lỗi, lấy avatar lỗi hoặc client hủy trong lúc chờ avatar, cơ chế điều khiển đều nằm trong một chuỗi. Tuy nhiên, nếu avatar empty, `card` cũng empty; hãy quyết định fallback theo nghiệp vụ.

### 5.2. then: thao tác B phải đợi A thành công

```java
Mono<Void> workflow = validate(order)
        .then(reserve(order))
        .then(save(order));
```

Snippet giả định cả ba hàm trả `Mono<Void>` hoặc `Mono<?>` phù hợp. `then` bỏ item A và chỉ subscribe B sau `onComplete` thành công của A. Nếu `reserve` lỗi, `save` không được subscribe bởi đoạn chuỗi này. Cần chú ý **cách tạo nguồn**: `save(order)` có thể đã làm side effect ngay lúc gọi factory nếu implement sai/eager; muốn trì hoãn cả việc tạo publisher khi cần, dùng `Mono.defer(() -> save(order))`.

### 5.3. concatMap: xử lý từng item có trật tự

```java
Flux<Receipt> results = orders
        .concatMap(order ->
                paymentService.charge(order)
                        .flatMap(receipt -> auditService.record(receipt)
                                .thenReturn(receipt)));
```

Đây là snippet. `concatMap` đợi inner trước hoàn tất mới xử lý inner tiếp theo, giữ thứ tự đầu ra; lỗi/hủy vẫn thuộc một chuỗi. Không dùng `concatMap` như bảo đảm “thanh toán exactly-once”: cần thiết kế transaction, idempotency key, retry/compensation ở hệ thống bên ngoài.

### 5.4. flatMap concurrency: không đồng nghĩa fan-out vô hạn

```java
Flux<EnrichedUser> enriched = userIds
        .flatMap(id -> userService.enrich(id), 8);
```

Snippet có `userIds` và `userService`. Con số 8 là giới hạn số inner publishers đồng thời mà operator quản lý trong overload này, **không phải quota tổng request mạng toàn ứng dụng**. `flatMap` có thể làm kết quả xen kẽ, không bảo đảm thứ tự ID. Khi cần đầu ra đúng thứ tự nhưng muốn overlap tác vụ, cân nhắc `flatMapSequential` phù hợp, cùng giới hạn buffer/tài nguyên.

## 6. Chương trình Java 17+ chạy được: lỗi tách rời và hủy tách rời

Ví dụ sau **chạy độc lập với Maven + Reactor Core** và không dùng sleep/timer/mạng, vì vậy thứ tự output có thể kiểm tra chính xác. Có bốn tình huống:

1. Inner lỗi trong `doOnNext(...subscribe())` nhưng parent hoàn tất thành công.
2. Inner lỗi trong `flatMap` và parent nhận lỗi.
3. Hủy parent của nested subscription không hủy inner `Mono.never()`.
4. Hủy parent của `flatMap` hủy inner publisher đang chờ.

Cấu trúc thư mục:

```text
reactor-nested-subscribe-demo/
├── pom.xml
└── src/main/java/demo/NestedSubscribeDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-nested-subscribe-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Nội dung `src/main/java/demo/NestedSubscribeDemo.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class NestedSubscribeDemo {

    private static Mono<String> failStock() {
        return Mono.error(new IllegalStateException("stock unavailable"));
    }

    public static void main(String[] args) {
        System.out.println("1) nested error");
        Mono.just("order-7")
                .doOnNext(order -> failStock().subscribe(
                        ignored -> System.out.println("child:next=" + ignored),
                        error -> System.out.println(
                                "child:error=" + error.getMessage())))
                .subscribe(
                        order -> System.out.println("parent:next=" + order),
                        error -> System.out.println(
                                "parent:error=" + error.getMessage()),
                        () -> System.out.println("parent:complete"));

        System.out.println("2) composed error");
        Mono.just("order-7")
                .flatMap(order -> failStock())
                .subscribe(
                        value -> System.out.println("composed:next=" + value),
                        error -> System.out.println(
                                "composed:error=" + error.getMessage()),
                        () -> System.out.println("composed:complete"));

        System.out.println("3) nested cancellation");
        AtomicBoolean nestedChildCancelled = new AtomicBoolean();
        AtomicReference<Disposable> child = new AtomicReference<>();

        Flux<Integer> nestedParent = Flux.just(1)
                .concatWith(Flux.<Integer>never())
                .doOnNext(number -> child.set(
                        Mono.<String>never()
                                .doOnCancel(() ->
                                        nestedChildCancelled.set(true))
                                .subscribe()));

        Disposable parent = nestedParent.subscribe(
                number -> System.out.println("parent:next=" + number),
                error -> System.out.println(
                        "parent:error=" + error.getMessage()));

        parent.dispose();
        System.out.println("childCancelledAfterParentDispose="
                + nestedChildCancelled.get());

        child.get().dispose();
        System.out.println("childCancelledAfterManualDispose="
                + nestedChildCancelled.get());

        System.out.println("4) composed cancellation");
        AtomicBoolean composedChildCancelled = new AtomicBoolean();

        Disposable composed = Flux.just(1)
                .concatWith(Flux.<Integer>never())
                .flatMap(number ->
                        Mono.<String>never()
                                .doOnCancel(() ->
                                        composedChildCancelled.set(true)))
                .subscribe(
                        value -> System.out.println("composed:next=" + value),
                        error -> System.out.println(
                                "composed:error=" + error.getMessage()));

        composed.dispose();
        System.out.println("composedChildCancelledAfterDispose="
                + composedChildCancelled.get());
    }
}
```

Chạy từ thư mục có `pom.xml` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.NestedSubscribeDemo
```

**Standard output dự kiến** (không tính log của Maven):

```text
1) nested error
child:error=stock unavailable
parent:next=order-7
parent:complete
2) composed error
composed:error=stock unavailable
3) nested cancellation
parent:next=1
childCancelledAfterParentDispose=false
childCancelledAfterManualDispose=true
4) composed cancellation
composedChildCancelledAfterDispose=true
```

**Vì sao output ổn định trong demo?**

- `Mono.just`, `Mono.error` và `Flux.just` phát đồng bộ khi có subscription; `Mono.never`/`Flux.never` không phát và không hoàn tất.
- Ở tình huống 1, `doOnNext` chạy observer và tạo child subscription trước khi `onNext` của parent được chuyển xuống, nên callback child error được in trước `parent:next`; parent vẫn hoàn tất.
- Ở tình huống 2, `flatMap` nối inner error vào parent; không có `composed:complete`.
- Ở tình huống 3, parent vẫn hoạt động vì có `Flux.never()` sau item 1. Lệnh `parent.dispose()` hủy subscription của parent; child `Mono.never` do `subscribe` riêng **chưa** bị hủy. Chỉ `child.get().dispose()` mới kích hoạt `doOnCancel` của child.
- Ở tình huống 4, `flatMap` đang quản lý inner `Mono.never`. `composed.dispose()` hủy parent và inner còn hoạt động; flag chuyển thành `true`.

Trong ứng dụng thực, I/O có thể chạy bất đồng bộ trên nhiều thread, nên **thứ tự log không được coi là bằng chứng** về thứ tự hoàn tất. Ở đây các source và thao tác cancel đều đồng bộ, và dùng `AtomicBoolean` làm bằng chứng trực tiếp về callback hủy.

**Giới hạn:** ví dụ chỉ chứng minh đường truyền tín hiệu Reactor. Thư viện HTTP/DB có thể không thể đảo ngược một side effect đã gửi tới server dù subscription đã bị cancel.

## 7. WebFlux controller: không tự subscribe khi chuẩn bị HTTP response

Một controller WebFlux có nhiệm vụ **trả lại publisher** hoặc response phù hợp. Framework đăng ký subscriber để kết nối chuỗi với HTTP request/response. Không gọi `subscribe` chỉ để “cho publisher chạy” nếu công việc đó quyết định response cuối.

### 7.1. Cách sai: response có thể hoàn tất quá sớm

```java
@GetMapping("/users/{id}/card")
public Mono<UserDto> wrong(@PathVariable String id) {
    return userService.findById(id)
            .doOnNext(user ->
                    avatarService.loadAvatar(user.id())
                            .subscribe());
}
```

Đây là snippet giả định một controller có `userService`, `avatarService`, `UserDto`. Phương thức chỉ trả user, không đợi avatar, không trả avatar và không truyền lỗi avatar vào luồng xử lý HTTP. Nếu client disconnect, inner subscription không tự bị framework hủy.

**Không sửa bằng `block()`**:

```java
// SAI trong WebFlux event loop: chặn luồng request.
UserDto user = userService.findById(id).block();
String avatar = avatarService.loadAvatar(user.id()).block();
```

`block()` phá mô hình non-blocking và có thể bị Reactor từ chối trên thread đánh dấu non-blocking. Hãy compose publisher.

### 7.2. Cách đúng: card phụ thuộc cả user và avatar

Ví dụ dưới đây là **controller Java 17 hợp lệ trong ứng dụng Spring Boot có WebFlux starter**, gồm cả những kiểu hỗ trợ; nó cần bean thực tế cho các service và main application.

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/users")
public class UserCardController {
    private final UserService userService;
    private final AvatarService avatarService;

    public UserCardController(UserService userService,
                              AvatarService avatarService) {
        this.userService = userService;
        this.avatarService = avatarService;
    }

    @GetMapping("/{id}/card")
    public Mono<UserCard> getCard(@PathVariable String id) {
        return userService.findById(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND, "User not found")))
                .flatMap(user ->
                        avatarService.loadAvatar(user.id())
                                .defaultIfEmpty("default.png")
                                .map(avatarUrl ->
                                        new UserCard(user.id(),
                                                user.displayName(),
                                                avatarUrl)));
    }
}

record UserDto(String id, String displayName) { }
record UserCard(String id, String displayName, String avatarUrl) { }

interface UserService {
    Mono<UserDto> findById(String id);
}

interface AvatarService {
    Mono<String> loadAvatar(String userId);
}
```

Luồng xử lý:

1. `userService.findById(id)` trả `Mono<UserDto>`; framework subscribe khi xử lý HTTP.
2. Nếu không có user, `switchIfEmpty` phát lỗi HTTP 404 theo hợp đồng ví dụ.
3. Nếu có user, `flatMap` kết hợp `loadAvatar` như một tác vụ con. Inner có thể phát URL, empty hoặc error.
4. `defaultIfEmpty("default.png")` chỉ phục hồi trường hợp **avatar không tồn tại (empty)**; nó **không che lỗi** kết nối avatar service.
5. Khi avatar thành công, `map` tạo `UserCard`; response 200 có dữ liệu của cả hai service.
6. Nếu load avatar lỗi, lỗi được truyền trong chuỗi trả về để WebFlux error handler xử lý.
7. Nếu client hủy trước khi avatar xong, đường hủy có thể tới inner publisher đang hoạt động; driver/service cần hỗ trợ hủy để giảm công việc thực.

Không có lời gọi `subscribe()` nào trong controller. Ví dụ là **snippet phụ thuộc ứng dụng Spring Boot**, không phải chương trình server độc lập; service implementation cần bảo đảm non-blocking I/O nếu yêu cầu WebFlux non-blocking end-to-end.

### 7.3. Nếu việc phụ là Mono<Void>

Khi chỉ cần thành công/thất bại của tác vụ phụ và vẫn trả user:

```java
Mono<UserDto> response = userService.findById(id)
        .flatMap(user -> auditService.recordAccess(user)
                .thenReturn(user));
```

Snippet giả định `recordAccess` trả `Mono<Void>`. `thenReturn(user)` chỉ phát user sau khi việc ghi audit hoàn tất thành công; nếu audit lỗi thì response pipeline lỗi. Nhưng **cancellation không bảo đảm audit đã được ghi bền vững**, nên nếu audit pháp lý bắt buộc phải sống qua client disconnect, hãy thiết kế mô hình durable/outbox hoặc background worker độc lập có trách nhiệm riêng, thay vì “sửa” bằng nested subscribe vô chủ.

## 8. Cạm bẫy với lỗi: onErrorResume của cha không bắt lỗi con tách rời

Xét:

```java
Mono<String> result = Mono.just("job")
        .doOnNext(job ->
                Mono.<String>error(
                        new IllegalStateException("child failed"))
                    .subscribe())
        .onErrorResume(error -> Mono.just("fallback"));
```

**Sai cho mục tiêu recovery.** Lỗi child không trở thành `onError` trong parent. Hơn nữa, `subscribe()` không truyền error handler có thể làm Reactor báo một lỗi chưa được xử lý. `onErrorResume` của parent không có dữ liệu lỗi này để xử lý, nên parent có thể vẫn phát `"job"` bình thường.

Cách đúng:

```java
Mono<String> result = Mono.just("job")
        .flatMap(job ->
                Mono.<String>error(
                        new IllegalStateException("child failed")))
        .onErrorResume(IllegalStateException.class,
                error -> Mono.just("fallback"));
```

Khi subscribe, lỗi child đi qua `flatMap` nên `onErrorResume` có thể thay bằng `fallback`. Trong nghiệp vụ thật, chỉ phục hồi loại lỗi **có thể phục hồi**; không dùng `onErrorResume(error -> Mono.empty())` cho mọi exception nếu việc đó che giấu lỗi hệ thống.

### Bố trí quan sát trước và sau recovery

```java
Mono<String> result = remoteCall()
        .flatMap(value -> childCall(value))
        .doOnError(error -> log.warn("Combined workflow failed", error))
        .onErrorResume(TransientFailure.class,
                error -> cachedFallback());
```

Đây là snippet với các hàm/service/exception giả định. Observer `doOnError` nằm **sau flatMap**, nên nhìn thấy lỗi truyền ra từ remote hoặc child. `onErrorResume` chỉ phục hồi lỗi khớp. Nếu đặt observer sau recovery, nó không nhìn thấy lỗi **đã được phục hồi**, nhưng vẫn có thể thấy lỗi không khớp hoặc lỗi của fallback.

**Lưu ý về checked exception:** nếu gọi API có checked exception trong `map`/`flatMap`, cần bao bọc đúng cách hoặc dùng `Mono.fromCallable` bên trong chuỗi. Không nên catch rồi gọi `subscribe()` như một lối tắt.

## 9. Cạm bẫy với cancellation: “đã hủy cha” không phải “đã hủy mọi việc”

Trong chain compose đúng, operator có quan hệ tới upstream/inner subscription. Khi subscriber bên ngoài gọi `cancel()` hoặc `Disposable.dispose()`, Reactor có thể phát cancellation tới những upstream/inner đang còn hoạt động.

Các điều kiện cần tách bạch:

| Vấn đề | Điều có thể bảo đảm trong pipeline | Điều không được tự suy diễn |
|---|---|---|
| Hủy `flatMap` | Inner subscription còn hoạt động được quản lý và nhận cancel | Hủy không tự rollback HTTP request đã xử lý |
| Hủy `then` | Nguồn hiện đang được subscribe có thể nhận cancel | Nguồn B đã hoàn tất không thể “hoàn tất ngược” |
| Hủy outer `Flux` | Operator ngừng yêu cầu/phát thêm khi thích hợp | Producer ở bên ngoài (broker/thiết bị) chắc chắn dừng |
| Hủy subscription `Mono.never` | Callback `doOnCancel` chạy nếu subscription được thiết lập và hủy | Bất kỳ công việc ngoài nào cũng có khả năng hủy |
| Hủy nested `subscribe` riêng | Chỉ khi có handle và chủ động dispose child đó | `cancel(parent)` sẽ tự tìm ra child |
| Client đóng HTTP connection | WebFlux/transport thường hủy subscription phản hồi | Việc phát hiện disconnect luôn tức thì và mọi side effect được đảo ngược |

### Dùng doOnCancel và doFinally để quan sát

```java
Mono<String> workflow = parentOperation()
        .flatMap(value -> childOperation(value))
        .doOnCancel(() ->
                log.info("Workflow subscription was cancelled"))
        .doFinally(signal ->
                metrics.counter("workflow.terminal",
                        "signal", signal.name()).increment());
```

Đây là snippet với `log`/`metrics` và các method giả định. `doOnCancel` quan sát tín hiệu hủy. `doFinally` nhận `CANCEL`, `ON_COMPLETE` hoặc `ON_ERROR` khi pipeline kết thúc theo cách tương ứng.

**Quan sát sau cùng:** `doFinally` là hook chạy **sau khi tín hiệu terminal đã được truyền downstream**. Với cancellation/concurrency, thứ tự log giữa thread khác nhau có thể gây nhầm; hãy kiểm thử bằng publisher có điều khiển và đồng bộ hóa rõ ràng khi cần, thay vì chỉ đoán từ log.

## 10. Backpressure và subscribe lồng nhau

Reactive Streams tạo một kênh demand giữa subscriber và upstream theo `request(n)`. Nếu bên trong một callback bạn gọi:

```java
source.doOnNext(item ->
        childFlux(item).subscribe(value -> process(value)));
```

thì `childFlux(item)` nhận **subscriber mới**. Overload subscribe với consumer thường yêu cầu dữ liệu không giới hạn (`Long.MAX_VALUE`), nên demand của parent **không giới hạn/chặn chính xác** nguồn con. Nếu nhiều item parent đến nhanh, mỗi item có thể tạo thêm subscription child, đẩy hệ thống vào:

- Số lượng HTTP connections vượt dự kiến.
- Nhiều truy vấn DB hoặc nguồn I/O đồng thời.
- Hàng đợi, CPU, direct memory và thời gian response tăng.
- Không có chiến lược cancel toàn bộ child khi request bị hủy.
- Kết quả phát ra không còn đúng thứ tự hoặc business transaction.

Cách compose:

```java
Flux<Result> limited = source
        .flatMap(item -> childFlux(item), 4);
```

Đây là snippet; `Result`, `source`, `childFlux` phải khai báo. Con số 4 giới hạn **các inner publisher hoạt động đồng thời tại operator này**, không phải limit tổng connections hoặc queue của mọi service. Downstream còn có thể dùng `limitRate` hoặc operator khác để định hình demand. Với dữ liệu cần thứ tự, dùng `concatMap` hoặc `flatMapSequential` phù hợp.

**Không dùng nested subscribe làm “async optimization”**. Việc tách child chỉ có thể làm response cha trả nhanh hơn vì **nó không còn đợi công việc cần đợi**, chứ không chứng minh hệ thống nhanh hơn, đúng hơn hoặc tiết kiệm tài nguyên hơn.

## 11. Tài nguyên, hủy và giới hạn thực tế của cancellation

### 11.1. Subscription có cleanup hook

Nếu một publisher sử dụng tài nguyên riêng theo subscription, cleanup cần gắn với cả ba đường **complete**, **error**, **cancel**.

```java
Flux<String> monitored = readEvents()
        .doOnCancel(() -> log.info("Consumer cancelled"))
        .doFinally(signal ->
                log.info("Read workflow finished: {}", signal));
```

Snippet giả định `readEvents` trả `Flux<String>`. Hook quan sát giúp biết vòng đời; nhưng nếu tài nguyên cần đóng một cách đáng tin cậy, đặt resource acquisition/cleanup trong operator thích hợp, không chỉ hy vọng việc ghi log sẽ giải phóng tài nguyên.

### 11.2. using: tài nguyên đồng bộ, cleanup khi kết thúc/hủy

Ví dụ giản lược về `Flux.using` với `AutoCloseable` giả định:

```java
Flux<String> lines = Flux.using(
        () -> openTextSource(),
        source -> readLinesAsFlux(source),
        source -> source.close());
```

Đây là **snippet mô hình**, không chạy độc lập: `openTextSource()`, `readLinesAsFlux(...)` và kiểu tài nguyên cần được triển khai. Ý tưởng quan trọng: resource được tạo **cho mỗi subscription**, nguồn đọc nằm trong phạm vi sở hữu resource, và cleanup được Reactor gọi khi hoàn tất, lỗi hoặc hủy. Tính blocking của việc mở/đọc/đóng nguồn còn phụ thuộc implementation; `using` tự nó không chuyển I/O chặn thành non-blocking.

### 11.3. usingWhen: resource và cleanup bất đồng bộ

Với tài nguyên cần cleanup trả publisher (ví dụ connection/transaction reactive), `Mono.usingWhen` và `Flux.usingWhen` mô hình hóa lifecycle:

```java
Mono<Report> report = Mono.usingWhen(
        acquireSession(),                     // Mono<Session>
        session -> fetchReport(session),      // Mono<Report>
        session -> closeSession(session),     // publisher cleanup khi complete
        (session, error) ->
                abortAndCloseSession(session, error), // cleanup khi error
        session -> cancelAndCloseSession(session)     // cleanup khi cancel
);
```

**Mã minh họa**, các hàm `acquireSession`, `fetchReport`, `closeSession`, `abortAndCloseSession`, `cancelAndCloseSession` và kiểu `Session`/`Report` cần được khai báo trong hệ thống thật. Các cleanup functions trả `Publisher<?>`; không gọi `subscribe` bên trong chúng.

Điểm quan trọng: resource closure và cleanup đều nằm trong **một publisher tổng hợp**, nên operator có thể quản lý đường complete/error/cancel. Với `Mono.usingWhen`, Reactor trì hoãn tín hiệu thành công/lỗi ra downstream cho đến khi cleanup bất đồng bộ tương ứng hoàn tất; **lỗi cleanup có thể thay đổi kết quả cuối**. Không coi cleanup là side effect có thể bỏ qua.

### 11.4. Cancellation không phải transaction rollback

Ví dụ một POST chuyển tiền:

1. Client gọi API.
2. Upstream gửi yêu cầu tới payment provider.
3. Client ngắt HTTP.
4. Reactor hủy subscription đang chờ.
5. Payment provider **có thể đã xử lý chuyển tiền** dù client không còn nghe response.

Do đó hệ thống cần idempotency key, ledger trạng thái, cơ chế truy vấn lại, outbox hoặc compensation đúng nghiệp vụ. **Không lấy cancellation làm bảo đảm “không xảy ra giao dịch”.**

### 11.5. Cleanup khi discard/buffer

Một publisher có thể phát `DataBuffer`/`ByteBuf` reference-counted. Khi operator bỏ phần tử (filter, drop, cancel...), đôi khi cần release theo hợp đồng tài nguyên. Reactor có `doOnDiscard` cho các operator hỗ trợ discard; Spring cung cấp các utility giải phóng `DataBuffer` phù hợp.

```java
Flux<DataBuffer> incoming = receiveBuffers()
        .filter(buffer -> keepBuffer(buffer))
        .doOnDiscard(DataBuffer.class,
                org.springframework.core.io.buffer.DataBufferUtils::release);
```

Đây là **snippet chỉ để minh họa hook**, yêu cầu `DataBuffer`, `receiveBuffers`, `keepBuffer` và import Spring tương ứng. Nó chưa đủ để khẳng định mọi path đều không leak: cần kiểm tra ownership, reference counting, các operators hỗ trợ discard và tránh double release. Trong pipeline thực tế, ưu tiên APIs được Spring quản lý thay vì tự trộn reference-counting vào nested subscribe.

## 12. Context, tracing, bảo mật và transaction cũng bị ảnh hưởng

Một subscription trong Reactor có `Context` gắn với subscriber. Các operator được compose có thể dùng `deferContextual` để đọc thông tin request/correlation ID nếu giá trị đó được cung cấp bằng `contextWrite` hoặc tích hợp tracing tương ứng.

Ví dụ:

```java
Mono<String> request = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("traceId", "missing")))
    .flatMap(id -> childService(id))
    .contextWrite(ctx -> ctx.put("traceId", "trace-123"));
```

Đây là snippet, `childService` giả định trả `Mono<String>`. Child publisher được ghép trong `flatMap` có thể quan sát Reactor Context được truyền theo chain. **Không dùng `ThreadLocal` tùy tiện** làm bằng chứng context tự đi theo tác vụ reactive, vì scheduler có thể chuyển thread.

Trái lại:

```java
Mono<String> detached = Mono.just("request")
        .doOnNext(value ->
            Mono.deferContextual(context ->
                Mono.just(context.getOrDefault("traceId", "missing")))
            .subscribe())
        .contextWrite(ctx -> ctx.put("traceId", "trace-123"));
```

Đây là snippet. Lời gọi `subscribe` mới tạo một subscriber/context riêng, nên **không thể mặc định** inner nhìn thấy `traceId` của parent. Ngoài tracing, cùng một lỗi thiết kế còn có thể làm sai kỳ vọng đối với Spring reactive transaction, bảo mật hay dữ liệu request scope. Không tuyên bố mọi giao dịch chắc chắn bị mất: hành vi phụ thuộc transaction manager, operator và cách source sử dụng `Context`; nguyên tắc là **không tự tách subscription nếu cần giữ vòng đời/context của parent**.

## 13. Kiểm thử lỗi và hủy bằng StepVerifier

Khi sửa nested subscribe, hãy test **terminal signal của parent** và **tác động cancellation tới child**, không chỉ xác nhận rằng callback đã được gọi.

Tạo `Mono<String>` có lỗi giả và compose:

```java
Mono<String> combined = Mono.just("order-7")
        .flatMap(order ->
                Mono.<String>error(
                        new IllegalStateException("stock unavailable")));
```

Test JUnit 5 + `reactor-test`:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

class CompositionTest {
    @Test
    void innerErrorBecomesOuterError() {
        Mono<String> combined = Mono.just("order-7")
                .flatMap(order -> Mono.<String>error(
                        new IllegalStateException("stock unavailable")));

        StepVerifier.create(combined)
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && error.getMessage().equals("stock unavailable"))
                .verify();
    }

    @Test
    void cancellingOuterCancelsInner() {
        AtomicBoolean innerCancelled = new AtomicBoolean();

        Mono<String> combined = Mono.just("order-7")
                .flatMap(order -> Mono.<String>never()
                        .doOnCancel(() -> innerCancelled.set(true)));

        StepVerifier.create(combined)
                .thenCancel()
                .verify();

        assertTrue(innerCancelled.get());
    }
}
```

Đây là **test class cho project có `reactor-test` và JUnit Jupiter**, không nằm trong demo Maven ở mục 6 trừ khi thêm các test dependencies/surefire phù hợp. Trong test cancel, `Mono.just` đồng bộ phát order, `flatMap` subscribe `Mono.never` trước khi StepVerifier yêu cầu cancel nên callback có thể được quan sát.

**Lưu ý thử nghiệm concurrency:** khi inner thực sự chạy trên scheduler hoặc network, đừng dùng `Thread.sleep` để “mong hủy xảy ra” rồi assert. Dùng publisher/sink điều khiển được, `PublisherProbe`, virtual time hoặc synchronization phù hợp. `PublisherProbe` còn hữu ích để xác nhận đường code đã thực sự subscribe/cancel một publisher được compose.

### Test một nested subscription có thể xanh sai cách

```java
Mono<String> wrong = Mono.just("order-7")
        .doOnNext(order ->
                Mono.<String>error(
                        new IllegalStateException("stock unavailable"))
                    .subscribe(
                        value -> { },
                        error -> System.out.println("Detached: " + error)));

StepVerifier.create(wrong)
        .expectNext("order-7")
        .verifyComplete();
```

Đoạn snippet này cho thấy **parent có thể qua test thành công**, dù child có lỗi riêng. Điều test cần chứng minh là nghĩa nghiệp vụ mong muốn; nếu reserve stock bắt buộc thành công trước khi trả order, parent `verifyComplete()` như trên **không phải kiểm thử hợp lệ cho workflow**.

## 14. “Fire-and-forget” có khi nào là thiết kế có chủ đích?

Có, nhưng nó là **một workflow độc lập có ownership và độ tin cậy riêng**, chứ không phải lời gọi `subscribe()` vô chủ giấu trong `map`/`doOnNext` của request.

Ví dụ người dùng gửi lệnh lập báo cáo và server chỉ cần trả HTTP 202 Accepted. Hệ thống có thể ghi **job vào durable queue** trong transaction thích hợp, rồi trả 202 sau khi xác nhận queue đã nhận bền vững. Background worker được quản lý lifecycle sẽ tiêu thụ job; việc client ngắt kết nối sau 202 không làm mất job.

Thiết kế khái niệm:

```text
HTTP request → validate → persist job / enqueue durably → 202 + jobId
                                                    |
                                          Background worker
                                                    |
                                       process + retry + audit
```

Nếu một component thực sự subscribe chủ động ngoài request, nó phải có:

1. **Chủ sở hữu vòng đời**: start/stop của ứng dụng hoặc scheduler/job manager.
2. **Handle `Disposable` hoặc quản lý subscription**: có cách dừng khi shutdown.
3. **Error handler rõ**: log/metrics/dead-letter hoặc chiến lược phục hồi.
4. **Giới hạn đồng thời/tài nguyên**: không tạo vô hạn công việc từ mỗi request.
5. **Cơ chế lưu bền hoặc chấp nhận mất**: reboot có mất công việc không?
6. **Idempotency và retry có kiểm soát**: tránh gửi email/thu tiền nhiều lần.
7. **Tracing/context do chính workflow thiết lập**: không dựa vào thread-local hoặc context của request đã kết thúc.

Với tác vụ phải sống qua request, đừng tự động lấy `subscribe()` lồng nhau làm chiến lược. Dùng hệ thống quản lý job hoặc message broker đáng tin cậy; nếu cần chỉ là một phép tính phụ thuộc request, hãy compose và trả publisher.

## 15. Những lỗi code review thường thấy

### Lỗi 1 — subscribe trong map hoặc doOnNext

```java
// Sai: tạo tác vụ con không thuộc vòng đời parent.
return loadUser(id)
        .map(user -> {
            sendEmail(user).subscribe();
            return user;
        });
```

**Sửa:**

```java
return loadUser(id)
        .flatMap(user -> sendEmail(user).thenReturn(user));
```

Đây là snippets. Nếu email thất bại, kết quả sẽ lỗi; muốn email optional phải thiết kế recovery **trong inner** và công bố chính sách đó.

### Lỗi 2 — subscribe trong flatMap nhưng không trả Mono

```java
// Sai: flatMap trả Mono.just(...) nhưng child thật đã bị detach.
return loadUser(id)
        .flatMap(user -> {
            updateAvatar(user).subscribe();
            return Mono.just(user);
        });
```

**Sửa:** trả `updateAvatar(user).thenReturn(user)` để operator quản lý công việc. Tên operator `flatMap` tự nó không cứu được nếu callback vẫn tự `subscribe()`.

### Lỗi 3 — dùng then nhưng factory B đã thực hiện side effect eagerly

```java
// Có thể sai nếu updateB() tự chạy công việc ngay lúc được gọi.
Mono<Void> workflow = updateA().then(updateB());
```

**Sửa:** các API reactive nên trả publisher cold/lazy. Nếu cần trì hoãn cả lệnh tạo publisher, dùng `updateA().then(Mono.defer(() -> updateB()))`. `Mono.defer` không tự chuyển blocking I/O thành non-blocking.

### Lỗi 4 — thêm onErrorResume vào cha rồi tưởng đã bảo vệ child

```java
return loadOrder(id)
        .doOnNext(order -> reserve(order).subscribe())
        .onErrorResume(error -> fallbackOrder());
```

**Sửa:** ghép reserve bằng `flatMap` trước, sau đó đặt recovery theo loại lỗi và vị trí cần thiết. Parent không thể tự bắt lỗi của child subscription độc lập.

### Lỗi 5 — child bị tạo vô hạn từ Flux nhanh

```java
return source.doOnNext(item ->
        remoteRequest(item).subscribe());
```

Mỗi item mở một inner subscription mới, có thể làm tăng connections/CPU. **Sửa:** `flatMap(item -> remoteRequest(item), concurrency)` hoặc `concatMap` nếu cần tuần tự.

### Lỗi 6 — gọi subscribe trong WebFlux controller rồi return Mono.empty

```java
@PostMapping("/tasks")
public Mono<Void> wrong() {
    processTask().subscribe();
    return Mono.empty();
}
```

Parent response có thể hoàn tất ngay dù task chưa xong; lỗi/cancel task không thuộc HTTP workflow. **Sửa:** nếu task phải hoàn tất trước response, `return processTask();`. Nếu cần job chạy độc lập sau HTTP 202, thiết kế một job/queue có ownership thật.

### Lỗi 7 — không hủy Disposable do subscribe riêng tạo ra

```java
Disposable child = eventStream.subscribe(event -> handle(event));
```

Nếu subscribe là hợp lệ tại application boundary, **giữ `Disposable` và dispose khi stop**; cũng cần error consumer và giới hạn nguồn. Nếu subscription này được tạo trong request để làm một phần response, hãy thay bằng compose.

### Lỗi 8 — nghĩ cancel là rollback

Đã gửi yêu cầu tới payment provider thì hủy subscription không bảo đảm hoàn tác. **Sửa:** idempotency key, transaction state, durable queue, reconciliation và compensation theo nghiệp vụ.

### Lỗi 9 — doFinally của parent được xem là cleanup cho child vô chủ

Nếu child là subscription độc lập, `doFinally` của parent không đảm bảo đóng child. **Sửa:** compose inner hoặc quản lý handle con có ownership rõ. Với tài nguyên thuộc subscription, dùng `using`/`usingWhen`.

### Lỗi 10 — test chỉ nhìn kết quả parent

`StepVerifier.create(parent).verifyComplete()` có thể pass khi parent bỏ qua lỗi child. **Sửa:** kiểm tra error propagation và cancel tới inner, có thể dùng `PublisherProbe` để xác nhận lifecycle.

### Lỗi 11 — context trace/auth/transaction bị mất

`subscribe()` mới tạo subscriber và context mới. **Sửa:** compose, để framework truyền context đến inner; nếu thật sự cần workflow độc lập, thiết lập security/tracing context riêng và không giữ dữ liệu request đã hết vòng đời.

### Lỗi 12 — “mọi lỗi trong async callback sẽ tự chảy vào cha”

Callback ngoài Publisher có thể ném exception ở thread khác, không nằm trong signal chain; `onErrorResume` của cha không thấy. **Sửa:** bọc callback API bằng `Mono.create`/`Flux.create`/`Sinks` đúng hợp đồng, quản lý disposal và error signal; không gọi `subscribe` để vá.

## 16. Checklist lựa chọn phương án

Khi đọc code có một lời gọi `subscribe()`, hãy trả lời theo thứ tự:

1. **Ai là subscriber cuối cùng?** WebFlux, test, CLI hay component quản lý workflow? Nếu đã có framework subscribe, tại sao cần một subscriber nữa?
2. **Tác vụ con có phải thành công trước khi cha hoàn tất?** Nếu có, compose bằng `flatMap`/`then`.
3. **Kết quả con có phải phát nhiều item?** Nếu có, xét `flatMapMany` hoặc `Flux.flatMap`, `concatMap`.
4. **Lỗi con phải ảnh hưởng đến request?** Nếu có, không tách subscription.
5. **Client hủy thì có cần dừng việc con?** Nếu có, giữ child trong chain và kiểm tra driver hỗ trợ cancel.
6. **Có bao nhiêu child đồng thời?** Có giới hạn concurrency, queue, connection và demand?
7. **Tài nguyên ai đóng?** Có `usingWhen`, cleanup khi cancel/error/complete và test không leak?
8. **Có retry/timeout?** Operator đặt ở đâu, tác vụ con có thuộc phạm vi retry/timeout không?
9. **Có Reactor Context/tracing/security không?** Nếu có, subscription mới có thể làm đứt context.
10. **Nếu chủ đích fire-and-forget, job có owner thật không?** Có error handling, shutdown, durability và idempotency?
11. **Test đã kiểm tra lỗi inner và cancel inner?** Không chỉ test response cha.
12. **Có side effect không thể rollback?** Nếu có, cancel chỉ là tín hiệu, phải thiết kế bù trừ.

## 17. Bài tập vận dụng

**Bài 1 — Phát hiện lỗi:**

```java
Mono<String> bad = Mono.just("A")
        .doOnNext(v ->
                Mono.<String>error(
                        new IllegalArgumentException("child"))
                        .subscribe())
        .onErrorReturn("fallback");
```

Câu hỏi: `bad` có trả `fallback` không?

**Đáp án:** Không chỉ vì lỗi child. `onErrorReturn` của parent không nhận lỗi child độc lập. Nếu thiếu error consumer, sẽ phát sinh lỗi subscriber con chưa xử lý.

**Bài 2 — Sửa chuỗi:**

Yêu cầu: load user, ghi audit thành công, sau đó trả user. Nếu audit lỗi, cả workflow lỗi.

```java
Mono<User> correct = loadUser(id)
        .flatMap(user ->
                auditService.record(user).thenReturn(user));
```

Đây là snippet. `record` trả `Mono<Void>`. Vì inner được compose, lỗi/hủy là một phần của parent. Không dùng `doOnNext(user -> auditService.record(user).subscribe())`.

**Bài 3 — Cancellation:**

`Flux.just(1).concatWith(Flux.never())` đang hoạt động, trong `doOnNext` đã tự subscribe `Mono.never`. Hủy outer có hủy child không?

**Đáp án:** Không tự động. Child có subscription độc lập; phải có handle để hủy, hoặc compose child bằng `flatMap`.

**Bài 4 — Retry:**

Nếu `source.doOnNext(v -> remote(v).subscribe()).retry(2)`, mỗi attempt có thể tạo thêm child khi item v được phát. `retry` không biết các child đã detach, nên có nguy cơ side effect lặp/chạy song song. **Sửa:** compose remote vào source trước retry, phân loại lỗi và thiết kế idempotency.

**Bài 5 — Resource cleanup:**

Một nguồn có kết nối DB reactive, cần cleanup bất đồng bộ khi complete/error/cancel. Dùng callback `doOnNext` để mở kết nối rồi `subscribe()` đóng kết nối có đúng không?

**Đáp án:** Không nên. Sử dụng publisher-scoped resource management (`usingWhen`/transaction operator phù hợp) để cleanup thuộc cùng lifecycle; kiểm thử cả cancellation và lỗi cleanup.

**Bài 6 — Một tác vụ phải tồn tại dù client ngắt:**

Client yêu cầu xuất báo cáo tốn 20 phút. Có nên gọi `reportService.generate().subscribe()` trong controller rồi return HTTP 202 ngay?

**Đáp án:** Không phải mô hình đáng tin nếu subscription không được một job manager quản lý; request không còn sở hữu cancel/error, tiến trình restart có thể làm mất việc. Hãy ghi job bền vững hoặc dùng công cụ quản lý công việc độc lập, trả job ID và cung cấp trạng thái/đường truy xuất kết quả.

**Ghi nhớ cuối cùng:** Trong reactive programming, **subscription là một ranh giới ownership**. `subscribe()` tạo một luồng vòng đời mới. Nếu công việc bên trong phải đóng góp vào kết quả cha, hãy **trả publisher con cho một operator compose**, không gọi `subscribe` rồi bỏ qua nó. Làm vậy giữ liên kết lỗi, hủy, demand, context và khả năng quản lý tài nguyên; còn một workflow thực sự độc lập phải có chủ sở hữu và hợp đồng riêng.

## Tài liệu tham khảo

- Project Reactor — [Reference: Nothing Happens Until You subscribe()](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html) và [Reactive Programming: Asynchronicity](https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html).
- Project Reactor — [Mono API: flatMap, then, doFinally, usingWhen](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
- Project Reactor — [Flux API: flatMap, concatMap, flatMapSequential](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor — [Handling Errors: onErrorResume, onErrorMap](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- Project Reactor — [Using Resources and the Finally Block](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html#_using_resources_and_the_finally_block).
- Project Reactor — [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
- Spring Framework — [WebFlux annotated controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html).
- Spring Framework — [Reactive transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html).
