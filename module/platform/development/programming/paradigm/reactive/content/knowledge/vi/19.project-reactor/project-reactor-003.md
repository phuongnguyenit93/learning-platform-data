# `defer` và `fromCallable`: lựa chọn thời điểm tạo giá trị

Trong một pipeline reactive, thời điểm gọi một hàm có thể quan trọng không kém giá trị mà hàm trả về. Một lời gọi đọc database, lấy thời gian hiện tại hoặc tạo mã giao dịch có thể cần chạy riêng cho từng Subscriber. Nếu gọi hàm quá sớm khi đang lắp ráp pipeline, ứng dụng có thể giữ lại một giá trị cũ, thực hiện side effect dù chưa có ai đăng ký, hoặc không chạy lại công việc khi retry.

Project Reactor cung cấp `Mono.defer`, `Flux.defer` và `Mono.fromCallable` để kiểm soát thời điểm này. `defer` trì hoãn việc tạo Publisher đến lúc có subscription; `fromCallable` trì hoãn việc gọi một hàm đồng bộ tạo ra một giá trị. Hai API có liên quan nhưng phục vụ hai nhu cầu khác nhau: chọn hoặc tạo nguồn ở thời điểm subscribe, và tính giá trị ở thời điểm nguồn được yêu cầu.

Chủ đề này thuộc chương **Project Reactor** của REACTIVE_PROGRAMMING. Module học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; đồng thời thực hành Mono, Flux, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi chọn API, hãy phân biệt assembly, subscription và demand, rồi xác định mỗi Subscriber cần dùng chung một giá trị hay cần một lần thực thi mới.

## Ba thời điểm trong vòng đời một Publisher

Khi viết pipeline Reactor, có thể phân biệt ba giai đoạn:

1. **Assembly time (thời điểm lắp ráp):** mã tạo chuỗi operator và Publisher được thực thi. Ví dụ `Mono.just(loadProfile())` gọi `loadProfile()` ngay khi biểu thức được đánh giá.
2. **Subscription time (thời điểm đăng ký):** Subscriber đăng ký vào Publisher. Các toán tử như `defer` có thể chạy factory để tạo Publisher cho subscription đó.
3. **Request time (thời điểm yêu cầu):** Subscriber yêu cầu dữ liệu qua Subscription. Với `Mono.fromCallable`, Callable được gọi khi subscription yêu cầu giá trị; trong các cách `subscribe` tiện dụng, demand thường được yêu cầu ngay nên hai thời điểm này có thể diễn ra sát nhau.

```text
Assembly                 Subscription                 Request
   |                          |                           |
   | tạo pipeline             | đăng ký                   | request(n)
   |------------------------->|-------------------------->|
   |                          | defer factory chạy        | fromCallable chạy
   |                          | tạo inner Publisher       | phát onNext / onComplete
```

Không phải Publisher nào cũng có công việc ở cả ba giai đoạn. Sơ đồ chỉ ra các mốc cần phân biệt để hiểu vì sao một lời gọi có thể chạy ngay khi khai báo, khi subscribe hoặc khi có demand.

## `Mono.just`: đối số được tính ngay khi lắp ráp

`Mono.just(value)` nhận một giá trị đã được tính. Java đánh giá đối số trước khi gọi `just`, vì vậy hàm tạo giá trị chạy ngay tại thời điểm biểu thức được thực thi:

```java
import java.time.Instant;

Mono<Instant> capturedAtAssembly = Mono.just(Instant.now());
```

`Instant.now()` đã được gọi trước khi `Mono.just` trả về. Mỗi Subscriber nhận cùng một `Instant` đã lưu trong Mono, kể cả khi đăng ký sau đó nhiều giây.

Tương tự, ví dụ sau gọi `loadProfile` ngay khi lắp ráp:

```java
Mono<Profile> profile = Mono.just(repository.loadProfile("user-42"));
```

Nếu `loadProfile` là lời gọi blocking, nó chặn thread đang lắp ráp pipeline. Nếu hàm ném exception, exception xảy ra trước khi `Mono` được tạo; `onErrorResume` đặt sau `Mono.just` không thể bắt lỗi đó vì chưa có Publisher để phát tín hiệu.

`Mono.just` phù hợp khi giá trị đã có sẵn và muốn phát lại cùng giá trị cho mỗi Subscriber. Nó không phải cách trì hoãn một phép tính.

## `Mono.fromCallable`: trì hoãn một lời gọi tạo giá trị

`Mono.fromCallable(callable)` nhận một `Callable` và tạo Mono có thể phát giá trị do Callable trả về. Callable không được gọi tại assembly time; nó được gọi khi subscription có demand để lấy giá trị. Mỗi subscription độc lập thực hiện Callable của nó.

```java
import reactor.core.publisher.Mono;

Mono<Profile> profile = Mono.fromCallable(
    () -> repository.loadProfile("user-42")
);
```

Khai báo trên tạo pipeline mà chưa gọi `repository.loadProfile`. Khi có Subscriber yêu cầu giá trị, Callable mới thực hiện lời gọi. Nếu có hai Subscriber độc lập, Callable có thể chạy hai lần và mỗi lần có thể nhận dữ liệu khác nhau.

### Callable trả về null

Nếu Callable trả về `null`, `Mono.fromCallable` hoàn tất mà không phát `onNext` (tương đương Mono rỗng). Reactive Streams không cho phép `null` làm phần tử `onNext`.

```java
Mono<Profile> optionalProfile = Mono.fromCallable(
    () -> legacyRepository.findOrNull("user-42")
);
```

Nếu không tìm thấy hồ sơ và API cũ trả về `null`, Mono hoàn tất rỗng. Có thể biểu diễn rõ trường hợp không tìm thấy bằng `switchIfEmpty`:

```java
Mono<Profile> profile = Mono.fromCallable(
        () -> legacyRepository.findOrNull("user-42")
    )
    .switchIfEmpty(Mono.error(new ProfileNotFoundException("user-42")));
```

Điều này giúp downstream phân biệt kết quả có giá trị với trường hợp không tìm thấy. Nếu `null` không có ý nghĩa hợp lệ trong hợp đồng API cũ, nên chuyển đổi nó thành kiểu dữ liệu rõ ràng thay vì để ngầm hoàn tất rỗng.

### Exception từ Callable trở thành `onError`

Nếu Callable ném exception, Reactor chuyển exception đó thành tín hiệu `onError` của Mono:

```java
Mono<Profile> profile = Mono.fromCallable(
        () -> repository.loadProfile("user-42")
    )
    .onErrorResume(RepositoryUnavailableException.class,
        error -> loadProfileFromCache("user-42"));
```

Khác với lời gọi được đặt bên trong `Mono.just(...)`, exception ở đây xảy ra trong quá trình thực thi Publisher nên có thể được xử lý bằng các operator phục hồi như `onErrorResume`, `onErrorMap` hoặc retry.

`Callable` cho phép ném checked exception, vì vậy `fromCallable` hữu ích khi bọc API Java đồng bộ có thể ném lỗi đã kiểm tra. Hãy chỉ phục hồi những loại lỗi có chính sách rõ ràng; không biến mọi lỗi hạ tầng thành kết quả rỗng nếu nghiệp vụ cần biết thao tác đã thất bại.

## `Mono.defer`: tạo Publisher riêng cho mỗi subscription

`Mono.defer(supplier)` nhận một Supplier trả về Mono. Supplier được gọi khi có subscription; Publisher được trả về sẽ trở thành nguồn cho subscription đó.

```java
import reactor.core.publisher.Mono;

Mono<Config> config = Mono.defer(() -> {
    String tenant = tenantContext.currentTenant();
    return configRepository.loadForTenant(tenant);
});
```

`tenantContext.currentTenant()` và lời gọi tạo Publisher của repository được thực hiện khi subscribe. Mỗi subscription có thể đọc tenant hiện tại và tạo Publisher tương ứng với tenant đó. Nếu viết `Mono<Config> config = configRepository.loadForTenant(tenantContext.currentTenant())`, lời gọi lấy tenant và tạo Publisher sẽ diễn ra ngay lúc biểu thức được đánh giá; nếu việc tạo Publisher có side effect hoặc phụ thuộc trạng thái thay đổi, thời điểm đó có thể quá sớm.

### Factory của `defer` được gọi một lần cho mỗi subscription

`defer` không gọi Supplier mỗi lần downstream yêu cầu thêm một phần tử. Nó gọi Supplier để lấy Publisher khi subscription bắt đầu; Publisher bên trong tự quản lý demand và phát dữ liệu theo hợp đồng của nó.

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger created = new AtomicInteger();

Mono<String> requestScoped = Mono.defer(() ->
    Mono.just("publisher-" + created.incrementAndGet())
);
```

Hai Subscriber độc lập tạo hai inner Mono khác nhau, vì vậy có thể nhận `publisher-1` và `publisher-2`. Trong một subscription, Supplier không được gọi lại cho mỗi `request(1)`.

Nếu Supplier của `defer` ném exception khi tạo Publisher, Reactor chuyển exception thành `onError` cho subscription đó. Nếu Supplier trả về `null` thay vì một Publisher, đó là lỗi hợp đồng; hãy trả về `Mono.empty()` khi muốn biểu diễn không có kết quả.

## `defer` và `fromCallable` khác nhau thế nào?

| Tiêu chí | `Mono.fromCallable` | `Mono.defer` |
|---|---|---|
| Đầu vào | Một Callable tạo giá trị `T` | Supplier tạo một Publisher `Mono<T>` |
| Thời điểm chính | Callable được gọi khi subscription có demand để lấy giá trị | Supplier được gọi khi subscription bắt đầu |
| Kết quả | Mono phát một giá trị, hoàn tất rỗng nếu Callable trả `null`, hoặc phát lỗi | Dùng Publisher được Supplier trả về; Publisher đó quyết định dữ liệu và vòng đời |
| Trường hợp phù hợp | Bọc một lời gọi đồng bộ hoặc phép tính có thể ném checked exception | Chọn nguồn động, tạo Publisher mới theo từng Subscriber, trì hoãn việc gọi factory |
| Mỗi subscription | Thực thi Callable riêng khi có demand | Gọi Supplier riêng để tạo Publisher cho subscription |

Có thể kết hợp hai API khi cần cả hai tầng trì hoãn:

```java
Mono<Result> result = Mono.defer(() -> {
    Request request = requestContext.currentRequest();
    return Mono.fromCallable(() -> blockingClient.execute(request));
});
```

`defer` đọc request và chọn cách tạo Publisher tại subscription time. `fromCallable` bọc lời gọi đồng bộ, thực hiện khi inner Mono nhận demand. Cấu trúc này hữu ích khi factory phụ thuộc Subscriber, còn thao tác tạo giá trị là một lời gọi đồng bộ.

## `Flux.defer` cho nguồn nhiều phần tử

`Flux.defer` có cùng nguyên tắc với `Mono.defer`, nhưng Supplier trả về `Publisher` nhiều phần tử:

```java
import java.util.List;
import reactor.core.publisher.Flux;

Flux<String> lines = Flux.defer(() -> {
    List<String> currentLines = fileService.readCurrentLines();
    return Flux.fromIterable(currentLines);
});
```

Trong ví dụ, `readCurrentLines()` được gọi khi mỗi subscription bắt đầu. Nếu tạo `List` trước rồi dùng `Flux.fromIterable(list)`, danh sách đã được đọc ở assembly time và các Subscriber sẽ duyệt cùng danh sách đó. Với file lớn hoặc nguồn vô hạn, không nên đọc toàn bộ nội dung vào `List`; hãy dùng API streaming phù hợp và quản lý tài nguyên theo vòng đời subscription.

`Flux.defer` cũng hữu ích khi nguồn phụ thuộc vào tham số thay đổi hoặc cần tạo một cursor mới cho mỗi Subscriber. Tuy nhiên, việc tạo nguồn mới không đảm bảo dữ liệu mới nếu chính factory đọc từ cache hoặc Publisher bên trong chia sẻ kết quả đã lưu.

## Đặt `subscribeOn` đúng chỗ cho Callable blocking

`fromCallable` trì hoãn lời gọi nhưng không tự biến nó thành bất đồng bộ. Nếu không chỉ định scheduler, Callable thường chạy trên thread thực hiện request, thường là thread gọi `subscribe` với subscriber yêu cầu ngay. Nếu Callable gọi JDBC, thư viện file blocking hoặc HTTP client đồng bộ, nó có thể chặn event loop hoặc thread xử lý request.

Với lời gọi blocking, thường chuyển nguồn sang `Schedulers.boundedElastic()` bằng `subscribeOn`:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Profile> profile = Mono.fromCallable(
        () -> blockingRepository.loadProfile("user-42")
    )
    .subscribeOn(Schedulers.boundedElastic());
```

`subscribeOn` điều khiển nơi subscription bắt đầu và nơi nguồn Callable được thực thi. `boundedElastic` được thiết kế cho tác vụ có thể blocking và có giới hạn tài nguyên. `fromCallable` vẫn là một lời gọi đồng bộ bên trong worker; nó không biến JDBC thành API non-blocking.

Không nên dùng `Schedulers.parallel()` cho lời gọi blocking kéo dài vì có thể chiếm worker dành cho CPU. Cũng không nên tạo scheduler mới cho mỗi request; hãy dùng scheduler phù hợp đã được quản lý hoặc tạo scheduler ở cấp thành phần với vòng đời rõ ràng.

`publishOn` có vai trò khác: nó chuyển xử lý downstream kể từ vị trí đặt toán tử. Nếu đặt `publishOn` sau `fromCallable`, lời gọi Callable vẫn có thể chạy trước ranh giới đó trên thread request. Để cô lập chính lời gọi nguồn, dùng `subscribeOn`.

## Tác động với retry và resubscribe

Vì `fromCallable` và `defer` thực thi lại theo subscription, chúng thường phù hợp khi dùng retry. Mỗi lần retry tạo subscription mới cho nguồn; Callable được gọi lại và factory của `defer` cũng được gọi lại.

```java
import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger attempts = new AtomicInteger();

Mono<String> retried = Mono.fromCallable(() -> {
        int attempt = attempts.incrementAndGet();
        if (attempt < 3) {
            throw new IOException("temporary failure");
        }
        return "success";
    })
    .retry(2);
```

Callable được thực thi tối đa ba lần: lần đầu và hai lần retry. Khi thành công ở lần thứ ba, Mono phát `success`. Nếu dùng `Mono.just(call())`, lời gọi `call()` đã xảy ra trước khi operator `retry` được gắn vào Publisher; retry không thể chạy lại biểu thức Java đã thực thi.

Với `defer`, mỗi lần resubscribe có thể chọn Publisher mới:

```java
Mono<Response> response = Mono.defer(() -> {
    Endpoint endpoint = endpointSelector.nextEndpoint();
    return httpClient.get(endpoint);
}).retry(2);
```

Mỗi lần subscription lại gọi `endpointSelector.nextEndpoint()` và tạo Publisher cho endpoint được chọn. Đây là cách hữu ích khi muốn đổi endpoint hoặc tạo request mới cho từng lần thử. Tuy nhiên, retry có thể lặp side effect; với thao tác ghi dữ liệu hoặc thanh toán, cần idempotency key và chính sách retry có kiểm soát.

Nếu Publisher được cache bằng `cache()` hoặc một cơ chế chia sẻ có lưu kết quả, subscription sau có thể nhận tín hiệu đã cache thay vì thực hiện lại nguồn. Vì vậy, tính lazy của `defer`/`fromCallable` không đồng nghĩa mọi subscription trong mọi pipeline đều luôn gọi lại công việc; cần xem các operator cache/share được đặt ở đâu.

## Ví dụ chọn API theo tình huống

| Tình huống | Cách viết gợi ý | Lý do |
|---|---|---|
| Giá trị đã có sẵn, mọi Subscriber dùng chung | `Mono.just(value)` | Giá trị đã được tính và có thể phát lại |
| Gọi hàm đồng bộ để tạo một giá trị mới khi có demand | `Mono.fromCallable(this::load)` | Trì hoãn lời gọi và chuyển exception thành `onError` |
| Chọn Publisher theo tenant hoặc request hiện tại | `Mono.defer(() -> selectSource())` | Factory chạy riêng cho từng subscription |
| Nguồn Flux cần được tạo mới cho từng Subscriber | `Flux.defer(this::createSource)` | Tạo Publisher mới ở subscription time |
| Bọc lời gọi blocking trong Reactor | `Mono.fromCallable(this::blockingCall).subscribeOn(boundedElastic())` | Lazy và cô lập thread thực thi |
| Chọn nguồn động rồi thực hiện lời gọi đồng bộ bên trong | `Mono.defer(() -> Mono.fromCallable(...))` | Điều khiển cả thời điểm chọn nguồn và thời điểm gọi Callable |

Một tiêu chí đơn giản là hỏi: “Tôi đã có giá trị chưa, hay mới có hàm tạo giá trị?” Nếu đã có giá trị, `just` thường phù hợp. Nếu có một Callable tạo giá trị, dùng `fromCallable`. Nếu cần tạo hoặc chọn Publisher theo từng Subscriber, dùng `defer`.

## Kiểm thử thời điểm thực thi

Kiểm thử nên xác nhận hàm chưa chạy trước subscription, chạy đúng số lần theo số subscription và chỉ chạy khi demand được gửi nếu đang kiểm soát demand thủ công.

### Kiểm thử `fromCallable` chạy riêng cho từng Subscriber

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertEquals;

class LazySourceTest {
    @Test
    void callableRunsOncePerSubscription() {
        AtomicInteger calls = new AtomicInteger();
        Mono<Integer> source = Mono.fromCallable(calls::incrementAndGet);

        assertEquals(0, calls.get());

        StepVerifier.create(source)
            .expectNext(1)
            .verifyComplete();

        StepVerifier.create(source)
            .expectNext(2)
            .verifyComplete();

        assertEquals(2, calls.get());
    }
}
```

Test chứng minh assembly chưa gọi Callable và mỗi subscription hoàn chỉnh tạo một lần gọi. Verifier yêu cầu dữ liệu khi bắt đầu xác minh nên Callable được thực thi trong quá trình test.

### Kiểm thử `defer` tạo Publisher mới cho mỗi subscription

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertEquals;

class DeferSourceTest {
    @Test
    void supplierRunsForEachSubscription() {
        AtomicInteger factories = new AtomicInteger();
        Mono<String> source = Mono.defer(() ->
            Mono.just("source-" + factories.incrementAndGet())
        );

        assertEquals(0, factories.get());

        StepVerifier.create(source)
            .expectNext("source-1")
            .verifyComplete();

        StepVerifier.create(source)
            .expectNext("source-2")
            .verifyComplete();

        assertEquals(2, factories.get());
    }
}
```

Test xác nhận Supplier được gọi một lần cho mỗi subscription, và mỗi lần tạo inner Mono mang giá trị khác nhau.

### Phân biệt subscription time và request time

Với `fromCallable`, có thể tạo Subscriber chưa yêu cầu dữ liệu để kiểm tra Callable chưa được gọi. `StepVerifier` cho phép bắt đầu với demand bằng không:

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertEquals;

AtomicInteger calls = new AtomicInteger();
Mono<Integer> source = Mono.fromCallable(calls::incrementAndGet);

StepVerifier.create(source, 0)
    .then(() -> assertEquals(0, calls.get()))
    .thenRequest(1)
    .expectNext(1)
    .verifyComplete();
```

Subscriber đã đăng ký nhưng chưa yêu cầu phần tử, nên Callable chưa được gọi. Khi `thenRequest(1)` phát demand, Callable mới chạy và phát kết quả. Đây là cách kiểm thử hữu ích khi cần chứng minh công việc tạo giá trị phụ thuộc demand.

## Những lỗi thiết kế thường gặp

**Gọi hàm bên trong `Mono.just`.** Đối số được tính trước khi `just` được gọi; side effect hoặc blocking xảy ra ở assembly time. Dùng `fromCallable` nếu cần trì hoãn lời gọi đồng bộ.

**Nhầm `defer` với `fromCallable`.** `defer` trì hoãn việc tạo Publisher; `fromCallable` trì hoãn một Callable tạo giá trị. Nếu đã có Publisher cần chọn theo từng Subscriber, dùng `defer`.

**Cho rằng `fromCallable` tự chạy bất đồng bộ.** Callable vẫn chạy đồng bộ trên thread thực hiện request nếu không có scheduler phù hợp. Dùng `subscribeOn` để cô lập công việc blocking.

**Đặt `publishOn` và mong nó chuyển lời gọi Callable upstream.** `publishOn` chỉ ảnh hưởng downstream kể từ vị trí của nó. Dùng `subscribeOn` cho nguồn Callable cần chuyển thread.

**Cho rằng `defer` gọi Supplier cho mỗi `request(n)`.** Supplier chạy để tạo Publisher ở subscription time; demand sau đó được xử lý bởi Publisher bên trong.

**Cho rằng mọi subscription luôn gọi lại nguồn.** `cache` hoặc cơ chế chia sẻ có lưu tín hiệu có thể làm subscription sau nhận kết quả đã lưu. Hãy kiểm tra vị trí các operator cache/share.

**Retry một side effect không idempotent.** `fromCallable` và `defer` có thể thực thi lại khi retry resubscribe. Cần idempotency key, giới hạn retry và xử lý trường hợp kết quả lần trước không rõ ràng.

**Không phân biệt null với lỗi.** Callable trả `null` tạo Mono rỗng; Callable ném exception tạo `onError`. Chọn cách biểu diễn phù hợp để downstream không hiểu nhầm “không có dữ liệu” thành “thao tác thất bại”.

## Tự kiểm tra

1. Vì sao `Mono.just(repository.load(id))` gọi repository trước khi có Subscriber?
2. `Mono.fromCallable` gọi Callable ở thời điểm nào và điều gì xảy ra nếu Callable trả về `null`?
3. `Mono.defer` trì hoãn điều gì? Supplier có được gọi lại cho từng `request(1)` không?
4. Khi nào nên dùng `defer` thay vì `fromCallable`, và khi nào có thể kết hợp cả hai?
5. Vì sao `fromCallable` không tự làm lời gọi blocking trở thành bất đồng bộ? `subscribeOn` giúp gì?
6. Vì sao retry có thể gọi lại Callable hoặc factory của `defer`, nhưng không thể tính lại đối số đã truyền vào `Mono.just`?
7. Làm thế nào kiểm thử rằng Callable chỉ chạy sau khi Subscriber gửi demand?

Khi phân biệt được assembly, subscription và request, bạn có thể chọn `just` cho giá trị đã có, `fromCallable` cho lời gọi đồng bộ cần trì hoãn và `defer` cho Publisher cần tạo theo từng subscription. Việc chọn đúng thời điểm giúp pipeline tránh side effect quá sớm, hỗ trợ retry đúng cách và giữ rõ ranh giới thực thi trong Project Reactor.
