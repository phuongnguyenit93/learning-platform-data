# Trì hoãn thực thi với `Mono.defer` và `Mono.fromCallable` khi tích hợp mã đồng bộ

## 1. Vì sao cần trì hoãn thực thi?

Trong ứng dụng Reactor/WebFlux, việc **tạo** một `Mono` không đồng nghĩa với việc **chạy** công việc bên trong. Ta thường xây dựng một pipeline trước, rồi Reactor mới thực thi khi có subscriber, chẳng hạn khi WebFlux subscribe để trả HTTP response.

Điều này đặc biệt quan trọng khi hệ thống reactive phải gọi mã đồng bộ cũ: JDBC/DAO blocking, SDK chỉ có API đồng bộ, đọc tệp bằng API blocking hoặc dịch vụ kiểm tra thông tin người dùng viết theo kiểu imperative. Nếu gọi trực tiếp trong lúc dựng pipeline, công việc sẽ diễn ra quá sớm. Nếu gọi bên trong pipeline nhưng trên event-loop thread, ứng dụng vẫn có thể bị nghẽn.

Sau bài này, bạn cần phân biệt được ba câu hỏi:
1. **Khi nào** mã đồng bộ được gọi: lúc dựng pipeline hay lúc subscribe?
2. **Mỗi lần subscribe** có tạo phép tính mới không?
3. **Trên thread nào** công việc chạy, và công việc đó có thể block thread không?

> Phạm vi: tập trung vào `Mono.defer`, `Mono.fromCallable` và mẫu bọc mã đồng bộ bằng Reactor. Chi tiết về xác thực, phân quyền hoặc thiết kế kho dữ liệu nằm ngoài bài này.

## 2. Ba thời điểm cần phân biệt

- **Assembly (lắp ghép):** tạo đối tượng `Mono` và nối các operator. Thông thường, công việc được mô tả nhưng chưa chạy.
- **Subscription (đăng ký):** một subscriber yêu cầu theo dõi publisher. Với nguồn cold thông thường, đây là thời điểm nguồn bắt đầu tạo tín hiệu.
- **Execution (thực thi):** mã thực tế chạy trên một thread do nguồn/operator/scheduler quyết định. *Lazy* không tự động có nghĩa là *non-blocking* hoặc chạy thread khác.

Ví dụ dễ nhầm:

```java
String user = legacyService.loadUser(); // chạy NGAY tại đây
Mono<String> mono = Mono.just(user);     // chỉ bọc giá trị đã có

// Tương đương về tính eager:
Mono<String> alsoEager = Mono.just(legacyService.loadUser());
```

`Mono.just(value)` nhận một giá trị đã được tính. Java phải đánh giá đối số `legacyService.loadUser()` trước khi gọi `just`, nên dù không ai subscribe, lời gọi đồng bộ vẫn đã xảy ra.

Chuyển biểu thức sang `fromCallable` thay đổi thời điểm chạy:

```java
Mono<String> lazy = Mono.fromCallable(legacyService::loadUser);
// Chưa gọi loadUser tại thời điểm tạo lazy.
// Mỗi lần subscribe đến nguồn này, Callable được thực hiện một lần.
```

Đó mới chỉ là giải pháp cho **thời điểm**. Nếu `loadUser` block, còn phải lựa chọn scheduler thích hợp ở phần 6.

## 3. `Mono.fromCallable`: trì hoãn một phép tính trả về giá trị

Chữ ký khái niệm: `Mono.fromCallable(Callable<? extends T>)`. Reactor giữ lại `Callable` và gọi nó khi có subscription tới nguồn. Một `Callable` có thể trả về một giá trị, trả về `null` hoặc ném exception.

```java
Mono<User> source = Mono.fromCallable(() -> legacyUserDao.findById(userId));
```

Ở đây `User`, `legacyUserDao` và `userId` là các kiểu/biến của ứng dụng, nên đoạn code **minh họa** này chỉ chạy khi chúng đã được định nghĩa. Hành vi nguồn là:

| Kết quả của `Callable.call()` | Tín hiệu từ `Mono` |
| --- | --- |
| Trả về đối tượng `user` khác `null` | `onNext(user)` rồi `onComplete()` |
| Trả về `null` | `onComplete()` mà không phát phần tử |
| Ném exception | `onError(exception)` |

Không dùng `Mono.just(null)`: `just` không chấp nhận giá trị null. Nếu API đồng bộ trả null để biểu thị “không tìm thấy”, `fromCallable` biến kết quả ấy thành một `Mono.empty()` hợp lệ.

```java
Mono<String> missing = Mono.fromCallable(() -> null);
Mono<String> withFallback = missing.defaultIfEmpty("not-found");

// Callable cho phép checked exception; Reactor chuyển lỗi thành onError.
Mono<String> failure = Mono.fromCallable(() -> {
    throw new java.io.IOException("legacy service unavailable");
});
```

**Mỗi subscription là một lần gọi lại** với `Mono.fromCallable` cold thông thường. Hai lần `subscribe()` hoặc `block()` có thể chạy lại truy vấn; `retry` cũng có thể khiến nguồn được subscribe lại. Đừng ngầm giả định kết quả đã được cache hoặc thao tác ghi chỉ xảy ra một lần.

`Mono.fromSupplier` cũng lười và phù hợp khi đầu vào là `Supplier<T>`, nhưng `Callable<T>` thuận tiện hơn khi API có thể ném checked exception. Với thao tác không trả giá trị, xem `Mono.fromRunnable` ở phần 8.

## 4. `Mono.defer`: trì hoãn việc **chọn/tạo cả publisher**

Chữ ký khái niệm: `Mono.defer(Supplier<? extends Mono<? extends T>>)`. Ở mỗi subscription, Reactor gọi supplier để nhận **một `Mono` mới**, rồi subscribe vào `Mono` đó. Điểm khác của `defer` là lambda trả về **publisher**, không đơn thuần là giá trị.

```java
AtomicBoolean useCache = new AtomicBoolean(false);

Mono<String> selected = Mono.defer(() ->
    useCache.get()
        ? cacheLookup()   // hàm trả về Mono<String>
        : remoteLookup()  // hàm trả về Mono<String>
);

// Nếu useCache thay đổi trước lần subscribe kế tiếp,
// nhánh được chọn cũng có thể khác.
```

Ví dụ trên là **đoạn minh họa**: `cacheLookup` và `remoteLookup` cần được định nghĩa. Với `defer`, quyết định chọn nguồn được đưa ra tại thời điểm subscription, rất hữu ích nếu trạng thái/configuration có thể thay đổi giữa các lần subscribe.

`Mono.defer(() -> Mono.just(legacyService.loadUser()))` cũng trì hoãn lời gọi `loadUser` vì cả biểu thức `Mono.just(...)` nằm *bên trong* supplier. Tuy nhiên, nếu chỉ có một phép tính đồng bộ trả về giá trị, viết `Mono.fromCallable(legacyService::loadUser)` đơn giản hơn và xử lý `null` tự nhiên hơn.

Cần nhớ:
- `defer` **không tự chuyển thread**; supplier vẫn có thể block thread gọi subscription.
- Không trả `null` làm publisher từ supplier của `defer`; hãy trả `Mono.empty()` khi cần publisher rỗng.
- `defer` không mặc định cache hoặc chia sẻ kết quả.
- Nếu cần chọn nguồn dựa trên Reactor `Context` của từng subscriber, API phù hợp là `Mono.deferContextual(...)`; đây là tình huống khác với đọc `ThreadLocal`.

## 5. Bảng chọn nhanh

| Nhu cầu | Operator hợp lý | Lý do |
| --- | --- | --- |
| Đã có sẵn một giá trị hợp lệ, không cần tính lại | `Mono.just(value)` | Đóng gói giá trị có sẵn, eager |
| Cần gọi một phương thức đồng bộ trả về 0 hoặc 1 giá trị khi subscribe | `Mono.fromCallable(callable)` | Lười, bắt exception, `null` thành empty |
| Cần tạo/chọn một `Mono` mới theo trạng thái ở mỗi subscription | `Mono.defer(() -> someMono)` | Hoãn cả quá trình tạo publisher |
| Phép tính đồng bộ không ném checked exception | `Mono.fromSupplier(supplier)` | Lười với `Supplier<T>` |
| Một hành động đồng bộ không có giá trị trả về | `Mono.fromRunnable(runnable)` | Phát complete/error, không phát `onNext` |
| Giá trị có thể null nhưng đã được tính từ trước | `Mono.justOrEmpty(value)` | Empty nếu null, nhưng không làm phép tính trở thành lazy |

**Quy tắc thực dụng:** “Trả về giá trị từ code cũ” thường bắt đầu bằng `fromCallable`; “quyết định sẽ chạy publisher nào” thường bắt đầu bằng `defer`.

## 6. Bọc **blocking call**: kết hợp `fromCallable` với `boundedElastic`

`fromCallable` chỉ dời công việc đến thời điểm subscribe. Nếu có I/O blocking, chờ socket, khóa đồng bộ hoặc `Thread.sleep`, lời gọi có thể giữ thread đang xử lý event loop và làm giảm khả năng phục vụ request khác.

Mẫu được Reactor khuyến nghị:

```java
Mono<User> userMono = Mono
    .fromCallable(() -> legacyUserDao.findById(userId))
    .subscribeOn(Schedulers.boundedElastic());
```

Đây là **đoạn minh họa trong một ứng dụng** đã có `User` và `legacyUserDao`. Import cần thiết: `reactor.core.publisher.Mono` và `reactor.core.scheduler.Schedulers`.

Luồng diễn ra như sau:
1. Lắp ghép pipeline không chạy `findById`.
2. Khi được subscribe, `subscribeOn(boundedElastic())` bố trí subscription của nguồn trên một worker của scheduler phù hợp với công việc blocking.
3. `Callable` gọi `findById` ở worker ấy và phát giá trị, empty hoặc lỗi.
4. Các operator tiếp theo xử lý tín hiệu theo quy tắc scheduling của Reactor.

Đặt `subscribeOn` **ngay sau nguồn blocking** để người đọc nhận ra ranh giới scheduler rõ ràng. `subscribeOn` tự nó **không subscribe**, và `boundedElastic` **không biến mã blocking thành non-blocking**: nó cách ly việc chờ khỏi những thread event loop, với giới hạn số worker/tác vụ chờ.

Không nhầm `publishOn` với `subscribeOn`. `publishOn` chuyển ngữ cảnh thực thi **phía downstream** từ vị trí operator đó; nếu nguồn blocking đã chạy ở phía upstream, đặt `publishOn` sau nguồn không bảo vệ được event loop khỏi lời gọi blocking ấy.

### Khi nguồn blocking nằm trong `flatMap`

Giả sử `tokenMono` là `Mono<String>` đã có trong luồng reactive:

```java
// SAI: legacyVerifier.verify(token) được gọi ngay trong mapper,
// có thể trên thread đang xử lý reactive pipeline.
Mono<Boolean> unsafe = tokenMono.flatMap(
    token -> Mono.just(legacyVerifier.verify(token))
);

// ĐÚNG: defer việc verify và chỉ chuyển đúng nhánh blocking sang boundedElastic.
Mono<Boolean> safe = tokenMono.flatMap(token ->
    Mono.fromCallable(() -> legacyVerifier.verify(token))
        .subscribeOn(Schedulers.boundedElastic())
);
```

`legacyVerifier` là đối tượng minh họa, `verify` là phương thức đồng bộ trả boolean. Nếu `verify` ném lỗi, `safe` phát `onError`. Với các phương thức trả `void`, có thể dùng `Mono.fromRunnable(() -> legacyAudit.write(event)).subscribeOn(Schedulers.boundedElastic())`.

**Không dùng** `block()`, `blockFirst()` hay `blockLast()` để nối vào pipeline WebFlux/Spring Security reactive. Các hàm ấy chặn caller và có thể gây lỗi hoặc treo luồng khi chạy trên thread không cho phép blocking. Trong bộ xử lý HTTP reactive, hãy **trả về `Mono`/`Flux`** và để framework quản lý subscription.

## 7. Ví dụ Java 17+ có thể chạy: chứng minh đúng thời điểm gọi

Ví dụ độc lập này dùng Reactor Core; `block()` chỉ được dùng từ `main` để minh họa subscription tuần tự, không phải mẫu sử dụng trong WebFlux handler.

Tạo các tệp:

```text
lazy-mono-demo/
├── build.gradle
└── src/main/java/demo/LazyMonoDemo.java
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
}

application {
    mainClass = 'demo.LazyMonoDemo'
}
```

Nội dung `src/main/java/demo/LazyMonoDemo.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

public class LazyMonoDemo {
    private static final AtomicInteger CALLS = new AtomicInteger();

    private static String readSync() {
        int n = CALLS.incrementAndGet();
        System.out.println("readSync=" + n);
        return "user-" + n;
    }

    public static void main(String[] args) {
        Mono<String> eager = Mono.just(readSync());
        System.out.println("eager assembled");
        eager.block();
        eager.block();

        Mono<String> lazy = Mono.fromCallable(LazyMonoDemo::readSync);
        System.out.println("lazy assembled");
        System.out.println("lazy first=" + lazy.block());
        System.out.println("lazy second=" + lazy.block());

        AtomicInteger choices = new AtomicInteger();
        Mono<String> branch = Mono.defer(() ->
            choices.incrementAndGet() % 2 == 1
                ? Mono.just("A")
                : Mono.just("B")
        );
        System.out.println("branch first=" + branch.block());
        System.out.println("branch second=" + branch.block());
    }
}
```

Chạy từ thư mục `lazy-mono-demo` khi đã cài Gradle tương thích:

```bash
gradle --quiet run
```

`stdout` của chương trình:

```text
readSync=1
eager assembled
lazy assembled
readSync=2
lazy first=user-2
readSync=3
lazy second=user-3
branch first=A
branch second=B
```

Giải thích:
- `readSync=1` xuất hiện **trước** `eager assembled`: đối số của `Mono.just` đã được tính trong lúc assembly. Hai `eager.block()` chỉ đọc lại cùng một giá trị, không gọi thêm `readSync`.
- `lazy assembled` xuất hiện **trước** `readSync=2`: `fromCallable` chưa chạy trong lúc assembly. Hai `lazy.block()` tạo hai subscription và thực hiện lần lượt `readSync=2`, `readSync=3`.
- `branch` xây một publisher mới tại mỗi lần subscribe, lần lượt chọn `A` và `B` vì bộ đếm thay đổi.

Ví dụ không thực hiện thao tác chờ I/O thực tế, nên không thêm `boundedElastic` ở phần này để quan sát thứ tự stdout một cách xác định.

## 8. Áp dụng trong Spring Security reactive và mã đồng bộ cũ

Trong hệ thống dùng Spring Security reactive, điểm tích hợp thực tế có thể là adapter gọi repository/SDK cũ để lấy dữ liệu phục vụ authentication, kiểm tra token hoặc tra cứu tài khoản. Phần mã blocking nên được cô lập trong một **adapter trả về Mono**, rồi ghép bằng các operator reactive:

```java
// Ví dụ minh họa trong một service/adapter đã có legacyUserDao:
Mono<User> findUser(String username) {
    return Mono.fromCallable(() -> legacyUserDao.findByUsername(username))
        .subscribeOn(Schedulers.boundedElastic());
}

// Ở pipeline đang có usernameMono:
// usernameMono.flatMap(this::findUser)
```

Nếu DAO trả `null` khi không thấy tài khoản, kết quả `findUser` là `Mono.empty()`. Tầng xác thực cần quyết định tường minh empty nghĩa là gì (ví dụ ánh xạ thành lỗi xác thực phù hợp), thay vì giả định nó tương đương một user hợp lệ. Không ghi token, mật khẩu, thông tin xác thực hoặc dữ liệu nhạy cảm vào log khi xử lý lỗi.

Trong reactive security, không dựa vào `SecurityContextHolder` dạng ThreadLocal của luồng servlet để đọc ngữ cảnh sau khi đổi thread. Ngữ cảnh bảo mật reactive được lan truyền thông qua Reactor `Context` và các API tương ứng như `ReactiveSecurityContextHolder`. Đổi scheduler và trì hoãn execution là hai mối quan tâm độc lập.

Nếu có thư viện thực sự non-blocking (R2DBC, reactive WebClient, reactive SDK), ưu tiên dùng trực tiếp API reactive đó. `boundedElastic` là **cầu nối** với mã blocking không thể thay thế ngay; nó vẫn tiêu tốn thread trong thời gian chờ và có giới hạn công suất.

## 9. Null, lỗi, retry và hủy subscription

### Null và luồng empty

```java
Mono<String> loaded = Mono.fromCallable(() -> legacyLookup("alice"));
Mono<String> required = loaded.switchIfEmpty(
    Mono.error(new IllegalStateException("No matching record"))
);
```

`legacyLookup` là phương thức minh họa. `switchIfEmpty` phân biệt “không có dữ liệu” với “đã có dữ liệu”; chỉ dùng kiểu lỗi phù hợp với nghiệp vụ thực tế. Với dữ liệu xác thực, nên chọn lỗi bảo mật đúng nghĩa ở tầng xử lý tương ứng.

### Exception và phục hồi

```java
Mono<String> source = Mono.fromCallable(() -> legacyLookup("alice"))
    .subscribeOn(Schedulers.boundedElastic());

Mono<String> recovered = source.onErrorResume(
    java.io.IOException.class,
    ex -> Mono.just("temporary-fallback")
);
```

Đoạn minh họa này giả định `legacyLookup` có thể ném `IOException`. Reactor đưa exception đến `onError`; `onErrorResume` chỉ dùng fallback cho nhóm lỗi được chỉ định. Không biến mọi lỗi authentication/authorization thành thành công, và không nuốt exception để che giấu lỗi hạ tầng.

### Resubscribe và tác dụng phụ

Nguồn `fromCallable`/`defer` thông thường sẽ chạy lại khi có subscription mới; `retry` tạo lại subscription sau lỗi. Vì vậy, nếu Callable ghi dữ liệu, gửi email, trừ tiền, thay đổi trạng thái hoặc gọi API có side effect, phải xét idempotency và khả năng chạy lại. `Mono.cache()` có thể thay đổi hành vi này bằng cách lưu tín hiệu để chia sẻ cho subscription kế tiếp, nhưng chỉ áp dụng cache khi đã xem xét vòng đời và tính đúng đắn dữ liệu.

### Cancellation

Hủy subscription không phải bảo đảm có thể dừng một JDBC call/SDK call đang block. Khả năng dừng phụ thuộc thư viện và cơ chế interrupt/cancel của nó. Cần cấu hình timeout ở client/driver, giới hạn đồng thời, theo dõi hàng đợi boundedElastic và xử lý tải tăng đột biến. Không coi `timeout` ở mức Reactor là bảo đảm dừng công việc I/O bên dưới.

## 10. Sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `Mono.just(blockingCall())` | Chạy blocking call ngay khi dựng Mono | `Mono.fromCallable(() -> blockingCall())` |
| Nghĩ `fromCallable` tự chạy nền | Có thể block thread của subscriber | Với call thật sự blocking, gắn `subscribeOn(Schedulers.boundedElastic())` |
| Dùng `publishOn` sau nguồn blocking và nghĩ đã bảo vệ upstream | Blocking source vẫn có thể chạy trên event loop | Đưa `subscribeOn` sát nguồn |
| `Mono.defer(() -> Mono.just(syncCall()))` ở mọi nơi | Dài dòng, dễ quên xử lý null | Dùng `fromCallable` nếu chỉ cần một giá trị |
| `Mono.justOrEmpty(syncCall())` để “làm lazy” | `syncCall()` vẫn được đánh giá ngay | `fromCallable(syncCall)` hoặc lambda |
| Gọi `block()` từ reactive handler | Chặn thread, có thể gây lỗi/đứng xử lý | Trả về Mono và kết hợp bằng `flatMap` |
| Cho rằng mỗi Mono chỉ chạy một lần | Subscription mới/retry có thể lặp side effect | Đánh giá idempotency, retries và cache |
| Chuyển mọi việc sang `boundedElastic` | Lãng phí thread khi việc đã non-blocking | Chỉ offload thực sự blocking |

**Lưu ý về cú pháp:** `fromCallable(syncCall)` ở bảng là ký hiệu ngắn cho callable phù hợp (chẳng hạn `() -> syncCall()`), không phải lời gọi Java độc lập nếu `syncCall` là một phương thức.

## 11. Tự kiểm tra kiến thức

1. Đặt `Mono.just(dao.load())` trong hàm trả Mono rồi không subscribe: `dao.load()` có chạy không? **Có**, vì Java phải tính đối số trước khi gọi `just`.
2. Đổi thành `Mono.fromCallable(dao::load)`: khi nào chạy? **Khi nguồn được subscribe**, thường một lần mỗi subscription.
3. DAO trả null: nguồn `fromCallable` báo gì? **Complete rỗng**, không phát `null`.
4. Khi nào chọn `defer`? **Khi muốn tạo/chọn một Mono khác nhau tại thời điểm mỗi subscription**, ví dụ căn cứ trạng thái lúc đó.
5. `defer` hoặc `fromCallable` tự làm nguồn blocking non-blocking chưa? **Chưa**; để bảo vệ event loop, áp dụng `subscribeOn(Schedulers.boundedElastic())` cho nguồn blocking.
6. Hai lần subscribe vào `fromCallable` và một lần retry có thể gọi lại DAO không? **Có**; kiểm soát tác dụng phụ và dữ liệu thay đổi giữa các lần.

### Bài tập nhỏ

Viết adapter `Mono<String> loadLegacyProfile(String id)` từ phương thức blocking `legacyClient.loadProfile(id)` sao cho:
- Không gọi client trong lúc tạo Mono.
- Mỗi subscription có thể tải lại dữ liệu.
- Phần blocking chạy trên `boundedElastic`.
- Null được biểu diễn bằng empty, exception được phát thành error.

Đáp án tham khảo (đặt trong class đã khai báo `legacyClient` và import các kiểu Reactor):

```java
Mono<String> loadLegacyProfile(String id) {
    return Mono.fromCallable(() -> legacyClient.loadProfile(id))
        .subscribeOn(Schedulers.boundedElastic());
}
```

Hãy tự kiểm thử với fake client ghi đếm số lời gọi: trước subscription bộ đếm là 0, sau subscription đầu tiên là 1, sau lần tiếp theo là 2. Thêm trường hợp trả null và ném exception để xác nhận ba tín hiệu có thể xảy ra.

## Tài liệu chính thức

- [Reactor Core Reference — FAQ: How Do I Wrap a Synchronous, Blocking Call?](https://projectreactor.io/docs/core/release/reference/faq.html)
- [Reactor Core `Mono` API — `fromCallable`, `defer`, `deferContextual`](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Reactor Core `Schedulers` API](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html)

Ghi nhớ: **`fromCallable` trì hoãn phép tính tạo giá trị; `defer` trì hoãn việc tạo/chọn publisher; `subscribeOn(boundedElastic)` là ranh giới thread phù hợp khi phép tính bị blocking.**