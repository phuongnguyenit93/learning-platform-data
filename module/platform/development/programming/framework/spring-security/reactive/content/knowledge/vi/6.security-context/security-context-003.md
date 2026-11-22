# Phạm vi và chiều truyền của Reactor Context trong một chuỗi Publisher

> **Chủ đề:** Spring Security – reactive  
> **Nhóm kiến thức:** Ngữ cảnh bảo mật  
> **Mục tiêu:** Hiểu đúng `Context` của Project Reactor thuộc về **Subscriber/Subscription**, cách `contextWrite` tạo phạm vi nhìn thấy dữ liệu **từ downstream đi về upstream**, cách `deferContextual` đọc dữ liệu, và vì sao Spring Security WebFlux có thể giữ danh tính xác thực khi một reactive pipeline chuyển thread.

## 1. Bài toán: danh tính của ai đang thực thi pipeline?

Trong ứng dụng đồng bộ truyền thống, lập trình viên đôi khi dùng `ThreadLocal` để lưu một giá trị gắn với request, ví dụ `username`, `traceId` hoặc tenant. Cách đó dễ gây hiểu nhầm ở Spring WebFlux: một request có thể được xử lý qua nhiều callback và nhiều thread; ngược lại một thread có thể phục vụ nhiều request tại các thời điểm khác nhau. Vì vậy **không thể coi một thread là định danh của request hoặc của người dùng**.

Project Reactor cung cấp **`Context`**: một tập key–value liên kết với subscriber trong một reactive sequence, được truyền theo cơ chế subscription. Nó cho phép các thành phần thuộc một pipeline truy cập metadata ngữ cảnh mà không nhất thiết phải thêm `userId` hoặc `traceId` vào mọi tham số phương thức.

Spring Security reactive dùng cơ chế này để cung cấp `SecurityContext` cho các đoạn `Mono`/`Flux` thuộc cùng luồng xử lý được bảo vệ. Trọng tâm cần nắm là **nơi đặt `contextWrite`, nơi đặt toán tử đọc `ContextView`, và ranh giới subscription**.

### Kết quả cần đạt

1. Phân biệt `Context` với dữ liệu `onNext`, với `ThreadLocal` và với `SecurityContext`.
2. Mô tả hai hướng vận động: tín hiệu dữ liệu **upstream → downstream**, subscription/`Context` **downstream → upstream**.
3. Dự đoán chính xác giá trị trong `deferContextual` khi đổi vị trí `contextWrite`.
4. Giải thích nguyên tắc **mỗi subscription có ngữ cảnh riêng**, không tự rò rỉ giữa request.
5. Hiểu `flatMap`, inner publisher, `publishOn`, `subscribeOn`, `cache`, `share` ảnh hưởng đến phạm vi ra sao.
6. Dùng `ReactiveSecurityContextHolder` đúng cách và tránh tự tách pipeline khiến mất thông tin bảo mật.
7. Chạy và kiểm tra các ví dụ Java 17+ có đầu ra dự kiến rõ ràng.

## 2. Trước tiên phải tách bốn thứ dễ bị lẫn

| Thuật ngữ | Là gì? | Thời điểm/phạm vi | Ví dụ |
| --- | --- | --- | --- |
| **Dữ liệu `onNext`** | Giá trị do `Publisher` phát ra | Theo tín hiệu dữ liệu đến subscriber | `Mono<User>`, `Flux<Order>` |
| **Reactor `Context`** | Cấu trúc key–value bất biến (immutable API), gắn với một subscriber | Xác định theo subscription và phần pipeline mà context có thể nhìn thấy | `traceId`, `tenantId` |
| **`ThreadLocal`** | Biến gắn với thread Java | Gắn với thread hiện tại, không phải toàn bộ reactive chain | Logger MDC hoặc security context kiểu imperative |
| **Spring Security `SecurityContext`** | Object chứa `Authentication` của Spring Security | Trong WebFlux được cung cấp qua Reactor `Context` | Username và `GrantedAuthority` của principal |

**Quan hệ chính xác:** Reactor `Context` là **phương tiện mang ngữ cảnh**; Spring Security `SecurityContext` là **thông tin bảo mật được mang**. Chúng không phải cùng một kiểu dữ liệu và không nên dùng chung khái niệm.

Một `Mono<String>` có thể phát chuỗi `"OK"` trong `onNext`, còn Reactor Context gắn với subscriber giữ `traceId="r-42"`. Đổi hoặc thêm `traceId` không làm thay đổi chuỗi `"OK"` trừ khi code chủ động đọc Context để tạo ra một giá trị mới.

### 2.1. Khả năng của hai API

```java
import reactor.util.context.Context;
import reactor.util.context.ContextView;
```

- `Context`: giao diện có các thao tác tạo ngữ cảnh như `put(key, value)`, `delete(key)` và `putAll(...)`. Các thao tác **trả về Context mới**, không sửa object cũ tại chỗ.
- `ContextView`: giao diện chỉ đọc với `get(key)`, `getOrDefault(key, defaultValue)`, `hasKey(key)`, `getOrEmpty(key)`. Reactive operator thường chỉ đưa `ContextView` cho code tiêu thụ.
- Key có thể là `Object`, nhưng trong ứng dụng lớn nên dùng key được định nghĩa rõ để tránh va chạm. Value cũng là `Object`; **bản thân Context bất biến không làm cho object value trở thành immutable**.
- Giá trị trong Context không được `null` theo hợp đồng; muốn biểu diễn vắng mặt thì xóa key hoặc dùng `getOrDefault`/`getOrEmpty`.

Ví dụ ngắn:

```java
Context original = Context.of("tenant", "A");
Context changed = original.put("tenant", "B");

System.out.println(original.get("tenant")); // A
System.out.println(changed.get("tenant"));  // B
```

Dòng trên là đoạn Java **minh họa trong method**, có thể chạy khi đặt vào một class có `main` hoặc test, import `reactor.util.context.Context`. Nó cho thấy phép `put` trả về bản mới.

## 3. Chiều truyền: data đi xuống, Context đi lên

Khi nhìn code Java, ta thường đọc theo thứ tự từ trên xuống:

```java
Mono.just("payload")
    .map(v -> v.toUpperCase())
    .flatMap(v -> callService(v))
    .contextWrite(ctx -> ctx.put("requestId", "r-42"));
```

Nhưng **thứ tự viết code không phải thứ tự tất cả sự kiện xảy ra**. Có ba giai đoạn:

1. **Assembly:** tạo chuỗi operator bằng lời gọi `just`, `map`, `flatMap`, `contextWrite`; chưa chạy nghiệp vụ ngay.
2. **Subscription:** subscriber cuối gọi `subscribe` hoặc framework subscribe giúp. Tín hiệu đăng ký đi **từ cuối chuỗi lên nguồn**. `contextWrite` lấy Context do downstream cung cấp, tạo ngữ cảnh mới cho upstream.
3. **Execution/data:** publisher phát `onNext`, `onError` hoặc `onComplete` từ nguồn theo hướng downstream. `deferContextual` khi được subscribe có thể quan sát Context thuộc phần upstream tương ứng.

```text
      SOURCE / UPSTREAM                        DOWNSTREAM / SUBSCRIBER

Mono.deferContextual(read) -- map -- flatMap -- contextWrite -- subscribe()
          |                                       |
          |<-------------  Context / subscribe --|
          |                                       |
          |--------------- onNext / onError ----->|

Chiều dữ liệu:     upstream  ----------------------> downstream
Chiều ngữ cảnh:    upstream  <---------------------- downstream
```

**Quy tắc để đọc code:** `contextWrite` nằm **bên dưới** điểm đọc trong chuỗi biểu thức (downstream) thì điểm đọc ở upstream có thể nhìn thấy giá trị. Nếu đặt `contextWrite` **bên trên** điểm đọc (upstream), không có nghĩa nó sẽ bơm Context ngược xuôi theo dữ liệu để điểm đọc ở downstream nhìn thấy.

### 3.1. `contextWrite` thực hiện việc gì?

Có hai dạng thông dụng:

```java
publisher.contextWrite(Context.of("traceId", "r-42"));

publisher.contextWrite(ctx -> ctx.put("traceId", "r-42"));
```

- `contextWrite(ContextView)`: hợp nhất các cặp key–value đầu vào với Context từ phía downstream, tạo Context mới cho upstream.
- `contextWrite(Function<Context, Context>)`: nhận Context mà downstream cung cấp và trả một Context để áp dụng cho upstream. Dạng lambda đặc biệt hữu ích để thêm hoặc thay một key mà vẫn giữ các key cũ.
- Không nên trả `Context.empty()` tùy tiện từ lambda vì có thể làm mất metadata của framework, gồm key mà Spring Security hoặc hệ thống trace đang cần.
- `contextWrite` không phải API sửa một "biến Context toàn cục", cũng không phải thao tác cập nhật mọi subscriber đang chạy.

## 4. Đặt `contextWrite` ở đâu thì nhìn thấy ở đó

Dưới đây là các ví dụ có đầu ra xác định, được gom thành project ở phần 9.

### 4.1. Viết downstream, đọc upstream: **nhìn thấy**

```java
Mono<String> sequence = Mono.deferContextual(view ->
        Mono.just("user=" + view.getOrDefault("user", "missing")))
    .contextWrite(ctx -> ctx.put("user", "lan"));

System.out.println(sequence.block());
```

Kết quả:

```text
user=lan
```

`deferContextual` nằm bên trên `contextWrite`; trong lúc subscription đi ngược lên, nguồn `Mono` nhận được Context có key `user`.

**`block()` trong code này chỉ dùng ở ví dụ chạy từ `main`/test** để minh họa. Trong WebFlux controller/service, không gọi `block()` trên event-loop; hãy trả `Mono`/`Flux` cho framework.

### 4.2. Viết upstream, đọc downstream: **không nhìn thấy**

```java
Mono<String> sequence = Mono.just("event")
    .contextWrite(ctx -> ctx.put("user", "lan"))
    .flatMap(value -> Mono.deferContextual(view ->
        Mono.just("user=" + view.getOrDefault("user", "missing"))));

System.out.println(sequence.block());
```

Kết quả:

```text
user=missing
```

`flatMap` đọc Context ở vị trí downstream so với `contextWrite` đã khai báo. Tín hiệu `onNext("event")` có thể đi qua `contextWrite`, nhưng **Context không phải một trường tự động đi kèm theo `onNext`**. Đây là lỗi thứ tự operator thường gặp nhất.

### 4.3. Ghi cùng một key nhiều lần: **điểm viết gần nguồn hơn thắng ở phạm vi upstream**

```java
Mono<String> sequence = Mono.deferContextual(view ->
        Mono.just("who=" + view.get("who")))
    .contextWrite(ctx -> ctx.put("who", "near"))
    .contextWrite(ctx -> ctx.put("who", "far"));

System.out.println(sequence.block());
```

Kết quả:

```text
who=near
```

Subscription bắt đầu ở `far`, đi ngược qua `near`, rồi mới đến `deferContextual`. Tại điểm đọc phía trên cả hai lần ghi, giá trị `near` là giá trị mới nhất cho **phần upstream này**.

**Không nên biến điều này thành quy tắc "ghi cuối trong source code luôn thắng".** Vị trí của điểm **đọc** quan trọng hơn vị trí của hai lần ghi khi nhìn riêng lẻ.

### 4.4. Hai điểm đọc ở hai phía của `contextWrite`: **mỗi điểm có tầm nhìn riêng**

```java
Mono<String> sequence = Mono.deferContextual(view ->
        Mono.just("up=" + view.get("who")))
    .contextWrite(ctx -> ctx.put("who", "near"))
    .flatMap(previous -> Mono.deferContextual(view ->
        Mono.just(previous + ",down=" + view.get("who"))))
    .contextWrite(ctx -> ctx.put("who", "far"));

System.out.println(sequence.block());
```

Kết quả:

```text
up=near,down=far
```

Điểm đọc `up` nằm upstream của cả `near` và `far`, thấy `near`. Điểm đọc bên trong `flatMap` thứ hai nằm downstream của `near` nhưng upstream của `far`, nên thấy `far`. Như vậy có thể xuất hiện **hai ContextView khác nhau trong cùng một chuỗi** mà không phải dữ liệu bị race hoặc mất ngẫu nhiên.

## 5. Phạm vi subscriber và ranh giới subscription

**Một Publisher không sở hữu một Context toàn cục.** Reactor gắn Context với `Subscriber`. Cùng một định nghĩa `Mono` có thể được subscribe hai lần với các giá trị Context khác nhau:

```java
Mono<String> common = Mono.deferContextual(view ->
    Mono.just("user=" + view.get("user")));

System.out.println(common
    .contextWrite(ctx -> ctx.put("user", "lan")).block());

System.out.println(common
    .contextWrite(ctx -> ctx.put("user", "minh")).block());
```

Kết quả:

```text
user=lan
user=minh
```

Không có phép gán user chung lên object `common` để request sau đọc lại. Mỗi lần subscribe được tạo đường subscriber riêng. Đó là nền tảng để bảo toàn ranh giới người dùng trong pipeline reactive, khi framework và ứng dụng thiết kế đúng.

### 5.1. `flatMap`: inner publisher có phạm vi riêng

`flatMap` nhận một phần tử và tạo một publisher lồng bên trong. Publisher lồng được subscribe như một chuỗi con; nó có thể quan sát Context thuộc vị trí tạo subscriber và có thể ghi thêm Context **cho chính chuỗi con**.

```java
Mono<String> sequence = Mono.just("event")
    .flatMap(value -> Mono.deferContextual(view ->
        Mono.just(value + ":" + view.get("who"))))
    .flatMap(value -> Mono.deferContextual(view ->
        Mono.just(value + ":" + view.get("who")))
        .contextWrite(ctx -> ctx.put("who", "inner")))
    .contextWrite(ctx -> ctx.put("who", "outer"));

System.out.println(sequence.block());
```

Kết quả:

```text
event:outer:inner
```

Giải thích:

- `contextWrite("outer")` ở cuối chuỗi tạo giá trị dùng cho nhánh chính và các inner publishers được subscribe trong `flatMap` của nhánh đó.
- Inner publisher ở `flatMap` thứ hai có thêm `contextWrite("inner")`, khiến chính điểm đọc của nó thấy `inner`.
- Lần ghi `inner` **không lan ngược ra toàn bộ nhánh chính** và không sửa kết quả đã tạo trong `flatMap` thứ nhất. Context của inner không trở thành một biến toàn cục.

Một phép `flatMap` có thể chạy nhiều inner sequence đồng thời. Khi xử lý theo tenant/user, đừng dùng chung biến mutable để truyền tenant giữa các inner; dùng Context cho metadata cần gắn với subscriber hoặc đưa tham số nghiệp vụ tường minh.

### 5.2. `subscribe()` gọi thủ công bên trong `map`/`flatMap` có vấn đề gì?

Mẫu sau **cố ý minh họa lỗi**, không phải chương trình được khuyến nghị:

```java
// Anti-pattern: tự subscribe tạo một luồng chạy tách khỏi luồng đang trả.
public Mono<String> wrong() {
    return Mono.just("start")
        .doOnNext(value ->
            expensiveOperation().subscribe(result -> saveResult(result)));
}
```

Đoạn này thiếu định nghĩa `expensiveOperation`/`saveResult` nên chỉ là minh họa. Điểm sai không chỉ ở việc bỏ qua kết quả: `subscribe()` bên trong tạo **subscription độc lập**, không tự bảo toàn Context của subscriber bên ngoài, lỗi và hủy subscription cũng khó đi theo cùng luồng.

Mẫu ghép pipeline đúng về cấu trúc:

```java
// Đoạn minh họa, cùng giả định có expensiveOperation và saveResult.
public Mono<String> better() {
    return Mono.just("start")
        .flatMap(value -> expensiveOperation()
            .doOnNext(this::saveResult)
            .thenReturn(value));
}
```

Dòng `flatMap` trả inner publisher cho Reactor quản lý trong pipeline, nên việc truyền Context, xử lý lỗi và cancellation nhất quán hơn. Trong ứng dụng thật, nếu `saveResult` cũng là thao tác bất đồng bộ, hãy trả `Mono` từ nó rồi dùng `flatMap` hoặc `then`, không nhét tác vụ async vào `doOnNext`.

## 6. Context qua `publishOn` và `subscribeOn`: không ràng buộc vào thread

`publishOn(scheduler)` đổi thread thực thi phía downstream; `subscribeOn(scheduler)` tác động việc subscribe vào nguồn và lịch chạy upstream theo cấu trúc chuỗi. Chúng là **toán tử điều phối thực thi**. Khi vẫn ở trong một reactive subscription hợp lệ, chúng không biến Reactor Context thành `ThreadLocal`, cũng không mặc định xóa Context.

```java
Mono<String> sequence = Mono.just("event")
    .publishOn(Schedulers.parallel())
    .flatMap(value -> Mono.deferContextual(view ->
        Mono.just("trace=" + view.get("trace"))))
    .contextWrite(ctx -> ctx.put("trace", "r-42"));

System.out.println(sequence.block());
```

Kết quả:

```text
trace=r-42
```

Đoạn này minh họa context vẫn được truy cập ở phía sau `publishOn`. Tên thread cụ thể không cố định, nhưng giá trị trace được mong đợi chính xác.

**Không đồng nhất với MDC/`ThreadLocal`:** `MDC.get("trace")` ở thread mới có thể không còn dữ liệu nếu không có cơ chế truyền ThreadLocal. Reactor có tích hợp context-propagation tùy cấu hình và thư viện, nhưng không nên tự suy rằng mọi `ThreadLocal` được sao chép sang thread khác chỉ vì `contextWrite`. Với logic xác thực, đọc `ReactiveSecurityContextHolder` trong pipeline reactive thay vì dùng `SecurityContextHolder.getContext()` của luồng imperative.

### 6.1. `deferContextual` đọc lúc nào?

`Mono.deferContextual(view -> ...)` tạo publisher **theo ngữ cảnh tại lúc subscription**. Không phải code "đọc Context một lần khi JVM tạo biến Mono". Đó là lý do một `Mono` được định nghĩa chung vẫn cho kết quả khác nhau giữa hai subscriber (ví dụ user `lan` và `minh` ở mục 5).

`transformDeferredContextual((publisher, view) -> ...)` là lựa chọn khác khi muốn transform một publisher trong khi quan sát `ContextView`. Với trường hợp nhập môn và truy cập một key, `deferContextual` thường dễ hiểu hơn.

## 7. Những chỗ Context vẫn có thể bị "mất" hoặc bị dùng sai

### 7.1. Kết quả chung được `cache()` hoặc `share()`: cẩn trọng dữ liệu theo người dùng

Xem biểu thức sau:

```java
Mono<String> cached = Mono.deferContextual(view ->
    Mono.just("user=" + view.get("user"))).cache();

String first = cached.contextWrite(ctx ->
    ctx.put("user", "lan")).block();

String second = cached.contextWrite(ctx ->
    ctx.put("user", "minh")).block();
```

Vì `cache()` ghi nhớ kết quả thành công của lần subscribe đầu tiên, khi cả hai gọi tuần tự như trên, `first` là `user=lan` và `second` cũng là `user=lan`. **Không phải Context bị chia sẻ như biến mutable.** Chính **giá trị kết quả** đã được cache và sử dụng lại giữa các subscriber.

Trong Spring Security, không tạo một cached `Mono` toàn cục mà nội dung được dựng theo `Authentication` hoặc tenant. Dữ liệu theo người dùng cần được tải theo request hoặc cache theo khóa bảo đảm phân tách người dùng/quyền, có cơ chế kiểm soát quyền riêng. `share()`/`publish().refCount()` cũng có thể làm nhiều subscriber dùng chung nguồn, nên không được suy rằng metadata subscriber này sẽ biến thành identity subscriber khác một cách an toàn.

### 7.2. Ranh giới không có cơ chế Reactor

Nếu bạn chuyển sang `CompletableFuture` thuần, callback của thư viện ngoài hoặc tự tạo thread và chỉ mang theo giá trị `Mono` dưới dạng object, không thể giả định thư viện kia tự mang `ContextView` qua mọi bước. Khi tích hợp một API ngoài Reactor, cần kiểm tra adapter, truyền metadata tường minh hoặc dùng giải pháp context propagation được hỗ trợ. Đừng dùng `ThreadLocal` theo thói quen để "vá" danh tính.

### 7.3. Context không thay thế input nghiệp vụ

Một hàm `approveInvoice(invoiceId, tenantId)` thường nên nhận `tenantId` qua tham số nếu đây là điều kiện nghiệp vụ quan trọng và có thể kiểm tra độc lập. Reactor Context phù hợp với metadata xuyên suốt pipeline (trace ID hoặc security context) hơn là trở thành kho giấu mọi tham số, gây khó test và khó tái sử dụng.

### 7.4. Không làm Context chứa dữ liệu nhạy cảm không cần thiết

- Không chèn password, raw bearer token, refresh token hoặc secret vào Context chỉ để tiện đọc.
- Không ghi toàn bộ `Context`, `Authentication` hay raw headers vào log.
- Dùng key định danh rõ, ví dụ một class/enum private hoặc constant object, để tránh va chạm với key của framework.
- Context API immutable nhưng value có thể mutable: tránh lưu một `Map` mutable chia sẻ qua nhiều request và rồi cập nhật nó từ nhiều luồng.
- Không tự thay thế toàn bộ Context bằng `Context.empty()` trong pipeline Spring Security, vì có thể loại key quan trọng của framework.

## 8. Tích hợp Spring Security WebFlux: ai đặt và ai đọc SecurityContext?

Trong reactive security, `SecurityContext` chứa `Authentication`. Spring Security cấu hình các thành phần như `ReactorContextWebFilter` và cơ chế xác thực tương ứng để thông tin bảo mật sẵn có trong Reactor Context của request. Lớp ứng dụng thường **đọc qua**:

```java
ReactiveSecurityContextHolder.getContext()
```

Phương thức trả về `Mono<SecurityContext>`, cho phép sử dụng trong pipeline không blocking:

```java
Mono<String> currentUsername = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);
```

Đoạn này có thể nằm trong method của WebFlux controller/service đã được bảo vệ, với import:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
```

Khi request HTTP Basic/JWT/session đã xác thực được phép đi tiếp, Spring Security thiết lập đúng SecurityContext cho publisher của request. **Không tự tin** username/role từ body/query/header tự khai rồi gắn vào Context để vượt qua authorization.

### 8.1. Test không HTTP: cấp Authentication cho một subscription cụ thể

`ReactiveSecurityContextHolder.withAuthentication(authentication)` tạo một `Context` có thể được sử dụng với `contextWrite` **trong test**:

```java
Authentication auth =
    new TestingAuthenticationToken("lan", "unused", "ROLE_USER");

Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth));

StepVerifier.create(name)
    .expectNext("lan")
    .verifyComplete();
```

Import `TestingAuthenticationToken` từ `org.springframework.security.authentication`, `StepVerifier` từ `reactor.test`. Đây là **đoạn code đặt trong test method**, dùng token giả để mô phỏng context; nó không chứng minh rằng mật khẩu đã được xác thực qua HTTP hoặc JWT.

Cấu hình ở phía trên có `contextWrite` đặt **downstream** của đoạn `getContext()`, đúng chiều truyền. Nếu đặt nó phía **upstream** của `getContext()`, điểm đọc ở downstream không tự nhận danh tính vừa đặt.

### 8.2. Đọc SecurityContext sau một điểm bất đồng bộ

Một service có thể trả:

```java
public Mono<String> currentUserAfterAsync() {
    return Mono.delay(Duration.ofMillis(1))
        .flatMap(ignored -> ReactiveSecurityContextHolder.getContext())
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

Đoạn này là method minh họa, cần import `java.time.Duration` cùng các class Reactor/Security. `Mono.delay` phát tín hiệu trên scheduler bất đồng bộ; chuỗi vẫn tiếp tục truy cập security context qua Reactor. Không cần giữ thread ban đầu, và không `block()`.

## 9. Ví dụ Java 17+ hoàn chỉnh: Reactor Context + API WebFlux bảo mật

Project Maven dưới đây dùng **Spring Boot 3.5.16** với Java 17+, bao gồm mã đọc/ghi Context thuần Reactor, một WebFlux API dùng Spring Security reactive, và JUnit/`StepVerifier`/`WebTestClient` để kiểm tra. Đây là phiên bản cố định để học và tái lập; với dự án sản xuất nên chọn nhánh Spring Boot còn được hỗ trợ và sử dụng phiên bản thư viện nhất quán theo BOM tương ứng.

```text
reactor-context-security-demo/
├── pom.xml
└── src/
    ├── main/java/demo/context/
    │   ├── Application.java
    │   ├── ContextDirectionExamples.java
    │   ├── SecurityConfiguration.java
    │   └── ContextController.java
    └── test/java/demo/context/
        ├── ContextDirectionTests.java
        └── WebSecurityContextTests.java
```

### 9.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactor-context-security-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot quản lý phiên bản Reactor và Spring Security phù hợp. Không thêm version riêng tùy tiện cho `reactor-core`, `reactor-test` hoặc `spring-security-test` trong project dùng Spring Boot parent. `reactor-core` được đưa vào bởi WebFlux starter; `reactor-test` chỉ cần ở test scope.

### 9.2. `src/main/java/demo/context/Application.java`

```java
package demo.context;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 9.3. `src/main/java/demo/context/ContextDirectionExamples.java`

Class này chỉ chứa các hàm trả `Mono` để test; không gọi `block()` trong ứng dụng reactive.

```java
package demo.context;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class ContextDirectionExamples {

    private static final String KEY = "who";

    private ContextDirectionExamples() {
    }

    public static Mono<String> visibleUpstream() {
        return Mono.deferContextual(view ->
                Mono.just("user=" + view.getOrDefault(KEY, "missing")))
            .contextWrite(ctx -> ctx.put(KEY, "lan"));
    }

    public static Mono<String> invisibleDownstream() {
        return Mono.just("event")
            .contextWrite(ctx -> ctx.put(KEY, "lan"))
            .flatMap(value -> Mono.deferContextual(view ->
                Mono.just("user=" + view.getOrDefault(KEY, "missing"))));
    }

    public static Mono<String> nearerWriteWins() {
        return Mono.deferContextual(view ->
                Mono.just("who=" + view.get(KEY)))
            .contextWrite(ctx -> ctx.put(KEY, "near"))
            .contextWrite(ctx -> ctx.put(KEY, "far"));
    }

    public static Mono<String> twoReadPositions() {
        return Mono.deferContextual(view ->
                Mono.just("up=" + view.get(KEY)))
            .contextWrite(ctx -> ctx.put(KEY, "near"))
            .flatMap(previous -> Mono.deferContextual(view ->
                Mono.just(previous + ",down=" + view.get(KEY))))
            .contextWrite(ctx -> ctx.put(KEY, "far"));
    }

    public static Mono<String> nestedScope() {
        return Mono.just("event")
            .flatMap(value -> Mono.deferContextual(view ->
                Mono.just(value + ":" + view.get(KEY))))
            .flatMap(value -> Mono.deferContextual(view ->
                Mono.just(value + ":" + view.get(KEY)))
                .contextWrite(ctx -> ctx.put(KEY, "inner")))
            .contextWrite(ctx -> ctx.put(KEY, "outer"));
    }

    public static Mono<String> acrossScheduler() {
        return Mono.just("event")
            .publishOn(Schedulers.parallel())
            .flatMap(value -> Mono.deferContextual(view ->
                Mono.just("trace=" + view.get("trace"))))
            .contextWrite(ctx -> ctx.put("trace", "r-42"));
    }

    public static Mono<String> currentSubscriber() {
        return Mono.deferContextual(view ->
            Mono.just("user=" + view.get(KEY)));
    }
}
```

Đặt các method này trong một lớp `final` thuần Java giúp tách quy tắc Reactor Context ra khỏi Spring HTTP config. `Mono.deferContextual` được đánh giá theo subscription; `Mono.just` phát giá trị, còn các `contextWrite` định phạm vi nhìn thấy giá trị của key.

### 9.4. `src/main/java/demo/context/SecurityConfiguration.java`

```java
package demo.context;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public-context").permitAll()
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails lan = User.withUsername("lan")
            .password("{noop}learn123")
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(lan);
    }
}
```

`SecurityWebFilterChain` là cấu hình cho WebFlux, khác `SecurityFilterChain` trong Servlet. User trong bộ nhớ và `{noop}` chỉ dùng để minh họa cục bộ; production phải có password encoder mạnh, HTTPS, quản lý secret và cơ chế định danh đúng chuẩn.

### 9.5. `src/main/java/demo/context/ContextController.java`

```java
package demo.context;

import java.time.Duration;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ContextController {

    @GetMapping("/api/public-context")
    public Mono<String> publicContext() {
        return Mono.deferContextual(view ->
                Mono.just("trace=" +
                    view.getOrDefault("traceId", "missing")))
            .contextWrite(ctx -> ctx.put("traceId", "r-42"));
    }

    @GetMapping("/api/me")
    public Mono<String> currentUser() {
        return Mono.delay(Duration.ofMillis(1))
            .flatMap(ignored -> ReactiveSecurityContextHolder.getContext())
            .map(SecurityContext::getAuthentication)
            .map(auth -> "user=" + auth.getName());
    }
}
```

Giải thích hai endpoint:

- `GET /api/public-context`: cho phép không cần đăng nhập. Method tự thêm `traceId="r-42"` vào **subscription cục bộ của publisher này** rồi đọc ở upstream, trả `trace=r-42`. Đây là key ứng dụng để minh họa, **không phải security authentication**.
- `GET /api/me`: cần HTTP Basic hợp lệ; Spring Security đặt `SecurityContext` của người gọi vào Reactor Context. `Mono.delay` tạo một ranh giới bất đồng bộ rồi `flatMap` vẫn truy cập `ReactiveSecurityContextHolder.getContext()`. Kết quả với tài khoản `lan` là `user=lan`. Chúng ta không tự đặt danh tính bằng `contextWrite` trong controller.

### 9.6. `src/test/java/demo/context/ContextDirectionTests.java`

```java
package demo.context;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ContextDirectionTests {

    @Test
    void downstreamWriteIsVisibleUpstream() {
        StepVerifier.create(ContextDirectionExamples.visibleUpstream())
            .expectNext("user=lan")
            .verifyComplete();
    }

    @Test
    void upstreamWriteIsInvisibleDownstream() {
        StepVerifier.create(ContextDirectionExamples.invisibleDownstream())
            .expectNext("user=missing")
            .verifyComplete();
    }

    @Test
    void nearestWriteWinsInUpstreamScope() {
        StepVerifier.create(ContextDirectionExamples.nearerWriteWins())
            .expectNext("who=near")
            .verifyComplete();
    }

    @Test
    void readingOnTwoSidesSeesDifferentValues() {
        StepVerifier.create(ContextDirectionExamples.twoReadPositions())
            .expectNext("up=near,down=far")
            .verifyComplete();
    }

    @Test
    void innerWriteIsLocalToInnerPublisher() {
        StepVerifier.create(ContextDirectionExamples.nestedScope())
            .expectNext("event:outer:inner")
            .verifyComplete();
    }

    @Test
    void contextSurvivesPublishOn() {
        StepVerifier.create(ContextDirectionExamples.acrossScheduler())
            .expectNext("trace=r-42")
            .verifyComplete();
    }

    @Test
    void separateSubscribersCarrySeparateValues() {
        Mono<String> source = ContextDirectionExamples.currentSubscriber();

        StepVerifier.create(source.contextWrite(ctx ->
                ctx.put("who", "lan")))
            .expectNext("user=lan")
            .verifyComplete();

        StepVerifier.create(source.contextWrite(ctx ->
                ctx.put("who", "minh")))
            .expectNext("user=minh")
            .verifyComplete();
    }

    @Test
    void reactiveSecurityContextCanBeProvidedForOneTest() {
        Authentication authentication =
            new TestingAuthenticationToken("lan", "unused", "ROLE_USER");

        Mono<String> username = ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(authentication));

        StepVerifier.create(username)
            .expectNext("lan")
            .verifyComplete();
    }
}
```

Các test này kiểm tra **hành vi Context bằng dữ liệu có giá trị được dự đoán chính xác**. Không test kiểu "xem print ra gì" hoặc đoán thread name. Test cuối chỉ chứng minh security context có thể được gắn vào một subscription và đọc lại; nó không xác minh HTTP credentials.

### 9.7. `src/test/java/demo/context/WebSecurityContextTests.java`

```java
package demo.context;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class WebSecurityContextTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicContextHasLocalTrace() {
        client.get().uri("/api/public-context")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("trace=r-42");
    }

    @Test
    void missingAuthenticationIsRejected() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validBasicUserRemainsAvailableAfterAsyncBoundary() {
        client.get().uri("/api/me")
            .headers(headers -> headers.setBasicAuth("lan", "learn123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("user=lan");
    }

    @Test
    void invalidPasswordIsRejected() {
        client.get().uri("/api/me")
            .headers(headers -> headers.setBasicAuth("lan", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

`WebTestClient` kiểm tra lớp HTTP WebFlux và Spring Security; `springSecurity()` đến từ `spring-security-test`. Các test HTTP xác nhận danh tính của một request sau ranh giới bất đồng bộ, trong khi test `StepVerifier` kiểm tra việc đặt và đọc Context ở các vị trí operator.

### 9.8. Chạy project và kết quả mong đợi

Cần Java 17+ và Maven tương thích. Tại thư mục chứa `pom.xml`:

```bash
java -version
mvn -version
mvn clean test
```

Bộ test có **12 phương thức `@Test`** (8 test Context + 4 test HTTP). Với cấu hình và dependency tương thích, dự kiến tất cả đều PASS. Maven sẽ ghi các báo cáo trong `target/surefire-reports`. Nếu test không chạy, kiểm tra `spring-boot-starter-test`, `reactor-test`, phiên bản JDK và classpath.

Khởi động server:

```bash
mvn spring-boot:run
```

Gọi API:

```bash
curl -i http://localhost:8080/api/public-context
curl -i http://localhost:8080/api/me
curl -i -u lan:learn123 http://localhost:8080/api/me
curl -i -u lan:wrong http://localhost:8080/api/me
```

| Request | Status mong đợi | Body của phản hồi thành công |
| --- | --- | --- |
| GET `/api/public-context` | **200** | `trace=r-42` |
| GET `/api/me` không credentials | **401** | Phụ thuộc authentication entry point |
| GET `/api/me` với `lan:learn123` | **200** | `user=lan` |
| GET `/api/me` với `lan:wrong` | **401** | Phụ thuộc authentication failure handler |

Trên PowerShell, dùng `curl.exe` nếu `curl` trỏ đến lệnh PowerShell. Tất cả ví dụ HTTP đều dùng GET, không cần vô hiệu CSRF cho bài này. Không cố định header/body lỗi 401 do có thể khác nhau giữa các cấu hình.

## 10. Tự chứng minh ba quy tắc với `StepVerifier`

`StepVerifier` là công cụ quan sát một subscription. Nó có thể cấp một Context ban đầu **ngay ở subscriber test**, rất hữu ích khi kiểm tra một hàm độc lập không gọi `contextWrite` nội bộ:

```java
Mono<String> source = Mono.deferContextual(view ->
    Mono.just("trace=" + view.get("trace")));

StepVerifier.create(source)
    .expectAccessibleContext()
    .then()
    .expectNext("trace=t-1")
    .verifyComplete();
```

**Chú ý:** đoạn ở trên cố ý **chưa hoàn chỉnh** vì chưa cấp key `trace`: nếu chạy nguyên như vậy, `view.get("trace")` sẽ lỗi. Phải cấu hình Context cho subscriber theo API `StepVerifierOptions`:

```java
StepVerifierOptions options = StepVerifierOptions.create()
    .withInitialContext(Context.of("trace", "t-1"));

StepVerifier.create(source, options)
    .expectAccessibleContext()
    .contains("trace", "t-1")
    .then()
    .expectNext("trace=t-1")
    .verifyComplete();
```

Đây là **đoạn bổ sung trong JUnit test method**, với imports:

```java
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.util.context.Context;
import reactor.core.publisher.Mono;
```

Nếu không muốn dùng `StepVerifierOptions`, cách đơn giản hơn là `StepVerifier.create(source.contextWrite(Context.of("trace", "t-1")))`. Cả hai đều kiểm tra được cơ chế cấp Context từ phía subscriber; điểm khác biệt là `withInitialContext` trực tiếp nạp Context khi tạo StepVerifier.

### Bài kiểm tra A: Dời `contextWrite` đi một bước

Bắt đầu bằng `deferContextual(...).contextWrite(...)` và thấy key. Sau đó chuyển `contextWrite` **về phía trên** `flatMap` có điểm đọc. Dự đoán `missing` trước khi chạy test. Nếu chỉ nhớ "context đi cùng dữ liệu" thì bạn sẽ đoán sai.

### Bài kiểm tra B: Thêm `contextWrite` vào một inner publisher

Giữ outer Context bằng `outer`. Trong inner thứ hai, thêm `contextWrite(...inner...)`. Chạy StepVerifier cho chuỗi nested và nhận `event:outer:inner`, chứng minh phạm vi inner độc lập.

### Bài kiểm tra C: Hai subscriber cùng dùng một Mono

Định nghĩa một lần `source = Mono.deferContextual(...)`. Dùng `contextWrite` ở từng subscription với `lan` và `minh`. Đọc được hai giá trị riêng, không có "user cuối cùng" toàn cục.

## 11. Lỗi phổ biến khi dùng Reactor Context cho bảo mật

| Sai lầm | Triệu chứng/hệ quả | Cách sửa |
| --- | --- | --- |
| Cho rằng `Context` truyền theo `onNext` | Đọc ở downstream nhận `missing` dù đã `contextWrite` ở phía trên | Đặt `contextWrite` **downstream** của điểm đọc cần nhìn thấy nó |
| Coi Context là biến toàn cục của `Mono` | Lo bị ghi đè giữa hai request hoặc cố sửa shared mutable state | Nhớ Context gắn với subscriber; dùng `deferContextual` |
| Dùng `ThreadLocal`/imperative `SecurityContextHolder` trong WebFlux | Mất danh tính sau `publishOn`/`delay`, nhầm người gọi | Dùng `ReactiveSecurityContextHolder` và Reactor chain |
| Tự `subscribe()` trong controller/service | Tác vụ tách khỏi request, context/error/cancel không theo luồng cha | Trả publisher và compose bằng `flatMap`/`then` |
| Trả `Context.empty()` trong `contextWrite` | Xóa key có sẵn của security/tracing ở upstream | Dùng `ctx.put`/merge để giữ key khác |
| Ghi Context ở inner `flatMap` rồi kỳ vọng outer đọc được | Outer không thấy key của inner | Đưa thao tác ghi xuống đúng phạm vi bao quanh điểm đọc |
| Cache publisher có kết quả theo user | Request thứ hai có thể nhận dữ liệu đã tính cho request trước | Không cache kết quả theo user toàn cục; phân vùng cache và kiểm soát quyền |
| Đặt access-control logic dựa trên header `X-User` | Client có thể giả danh nếu hệ thống tin header tự khai | Dựa trên `Authentication` đã xác minh từ Spring Security |
| Copy Context nhưng chứa `Map` mutable dùng chung | Race condition và thay đổi giá trị ngoài kiểm soát | Dùng value immutable hoặc thiết kế rõ owner/lifetime |
| Dùng Context như kho tất cả dữ liệu nghiệp vụ | Hàm khó test, phụ thuộc ngữ cảnh ẩn | Truyền đối số rõ ràng cho nghiệp vụ; Context cho metadata xuyên pipeline |
| Nhầm Context propagation tự động với ThreadLocal propagation | MDC có thể trống dù Reactor Context vẫn có giá trị | Cấu hình bridge được hỗ trợ nếu cần; test với scheduler |
| Test chỉ dùng `mockUser` rồi kết luận login thật hoạt động | Authorization pass nhưng cơ chế xác thực thật có thể lỗi | Thêm test HTTP Basic/JWT/session thực tế qua `WebTestClient` |

### Khi không thấy SecurityContext, kiểm tra theo thứ tự

1. Publisher có đang được subscribe **bởi framework** trong request WebFlux đã được bảo vệ không, hay tự `subscribe()` ở một chỗ khác?
2. Authentication đã thành công chưa? Trước khi đọc context, xác định luồng có chạy trong security chain không.
3. Có dòng `contextWrite(ctx -> Context.empty())`, `Context.of(...)` thay thế context cũ hoặc key trùng ghi đè không?
4. Có `flatMap` tạo inner subscription và `contextWrite` được đặt ngoài phạm vi điểm đọc không?
5. Có `cache()`, `share()` hoặc một `Mono` có kết quả gắn người dùng được dùng chung không?
6. Có chuyển sang callback/Future bên ngoài Reactor mà quên ranh giới context propagation không?
7. Có thử nghiệm dùng `SecurityContextHolder` kiểu Servlet thay cho `ReactiveSecurityContextHolder` không?

Đừng log raw credentials, JWT hoặc toàn bộ `Authentication` để debug. Dùng thông tin phân loại trạng thái, correlation ID và kiểm tra authorities an toàn nếu cần.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Trong chuỗi `Mono.deferContextual(...).contextWrite(...)`, tại sao điểm đọc nằm **bên trên** lần ghi vẫn nhìn thấy key?  
**Trả lời:** Vì `contextWrite` làm thay đổi Context mà subscriber ở downstream cung cấp cho phần upstream khi subscription đi ngược từ cuối chuỗi lên nguồn.

**Câu 2.** Nếu `contextWrite` được đặt bên trên một `flatMap` có `deferContextual`, tại sao `flatMap` có thể đọc `missing`?  
**Trả lời:** Vì `Context` không đi kèm theo `onNext`; điểm đọc ở downstream không được thừa hưởng một lần ghi chỉ áp dụng cho upstream.

**Câu 3.** Hai request cùng dùng một `Mono` khai báo ở field. Request A có user `lan`; request B có user `minh`. Reactor Context có tự trở thành một user chung không?  
**Trả lời:** Không. Context gắn với subscriber/đường subscription, trừ khi code tạo trạng thái hoặc kết quả chung không an toàn như cache chứa dữ liệu theo user.

**Câu 4.** `publishOn(Schedulers.parallel())` có tự xóa Reactor Context không?  
**Trả lời:** Không. Đổi thread không đồng nghĩa mất Reactor Context trong pipeline Reactor hợp lệ. `ThreadLocal` có quy tắc riêng và cần cơ chế propagation nếu muốn dùng.

**Câu 5.** Một inner publisher trong `flatMap` ghi `tenant="B"` bằng `contextWrite`. Inner khác có tự thấy `B` không?  
**Trả lời:** Không. Việc ghi riêng trong một inner subscription chỉ có hiệu lực ở phần upstream của inner đó.

**Câu 6.** `ReactiveSecurityContextHolder.withAuthentication(auth)` có hợp lý khi dùng trong production để nhận role do client tự gửi không?  
**Trả lời:** Không. Nó có thể dùng trong test hoặc tích hợp có kiểm soát, nhưng production phải dựa vào authentication đã được xác minh bởi cơ chế bảo mật tin cậy.

**Câu 7.** Vì sao `cachedMono.contextWrite(user=lan)` và `cachedMono.contextWrite(user=minh)` có thể cùng trả giá trị của Lan?  
**Trả lời:** Nếu `cachedMono` đã cache **kết quả theo Context của lần subscribe đầu**, lần sau có thể nhận lại chính giá trị cache. Đó là lỗi thiết kế cache dữ liệu nhạy cảm, không phải Reactor tự dùng chung một Context mutable.

**Câu 8.** Muốn kiểm tra context theo từng subscription mà không viết handler HTTP, dùng gì?  
**Trả lời:** Kết hợp `StepVerifier`, `Mono.deferContextual`, `contextWrite` hoặc `StepVerifierOptions.withInitialContext`, rồi xác nhận giá trị `onNext` cụ thể.

## 13. Tổng kết và tài liệu đọc thêm

- **Reactor Context gắn với subscriber**, không gắn với thread và không phải trường của từng `onNext`.
- **Data signal đi upstream → downstream; Context có thể được cung cấp downstream → upstream** theo đường subscription.
- **`contextWrite` chỉ ảnh hưởng phần upstream của vị trí nó được đặt**. Vị trí điểm đọc và các ghi gần điểm đọc quyết định giá trị quan sát.
- **`flatMap` tạo inner publisher có phạm vi riêng**; ghi trong một inner không sửa Context của các nhánh còn lại.
- **`publishOn`/`subscribeOn` không mặc định làm mất Reactor Context**; nhưng ThreadLocal bridge và hệ thống ngoài Reactor cần xem xét riêng.
- Trong Spring Security WebFlux, dùng **`ReactiveSecurityContextHolder`**; tránh tự tách subscription, sửa context toàn phần hoặc cache dữ liệu gắn với user không kiểm soát.

**Nguồn chính thức:**

- Project Reactor – Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/3.7.0/reference/advancedFeatures/context.html
- Project Reactor – Reference Guide (Context, threading và testing): https://projectreactor.io/docs/core/3.7.0/reference/
- Project Reactor – Reactor Test `StepVerifier`: https://projectreactor.io/docs/test/release/reference/
- Spring Security – Reactive Method Security và Reactor Context: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security – WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security – Reactive Web Testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/index.html
