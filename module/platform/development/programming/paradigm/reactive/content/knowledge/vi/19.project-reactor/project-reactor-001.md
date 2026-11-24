# `Mono` và `Flux`: biểu diễn không–một và không–nhiều phần tử

Project Reactor cung cấp hai kiểu Publisher thường gặp nhất là `Mono<T>` và `Flux<T>`. Cả hai đều biểu diễn một nguồn dữ liệu reactive, nhưng khác nhau ở số phần tử mà nguồn có thể phát: `Mono<T>` phát tối đa một phần tử, còn `Flux<T>` có thể phát từ không đến nhiều phần tử. Chọn đúng kiểu giúp chữ ký phương thức thể hiện rõ cardinality của dữ liệu, làm cho cách kết hợp pipeline dễ hiểu và giúp người đọc nhận ra trường hợp rỗng, nhiều kết quả hoặc lỗi.

`Mono` và `Flux` thuộc Project Reactor, một thư viện reactive trong hệ sinh thái Java. Chúng triển khai hợp đồng Reactive Streams thông qua `Publisher`, nên dữ liệu được truyền bằng tín hiệu `onNext`, `onError`, `onComplete` và được điều tiết bằng demand. Module REACTIVE_PROGRAMMING học các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure, sau đó thực hành kết hợp operator, scheduler, xử lý lỗi và kiểm thử pipeline trong Java. Bài học này tập trung vào cách biểu diễn nguồn không–một và không–nhiều phần tử trong Reactor.

## Cardinality là gì?

Cardinality mô tả số lượng phần tử mà một nguồn có thể phát. Với các kiểu Reactor:

| Kiểu | Cardinality | Cách hiểu |
|---|---:|---|
| `Mono<T>` | 0 hoặc 1 | Có thể phát một giá trị rồi hoàn tất, hoàn tất rỗng, hoặc kết thúc bằng lỗi |
| `Flux<T>` | 0 đến N | Có thể phát không phần tử, một phần tử hoặc nhiều phần tử, rồi hoàn tất hoặc lỗi |

Hai kiểu đều có thể phát lỗi. Lỗi là terminal signal, không phải một phần tử có kiểu `T`. Một `Mono<T>` không phát hai giá trị; một `Flux<T>` không có giới hạn cardinality cố định trong kiểu Java.

```text
Mono<T>
  0 phần tử:  | onComplete
  1 phần tử:  | onNext(T) | onComplete
  lỗi:        | onError

Flux<T>
  0 phần tử:  | onComplete
  1 phần tử:  | onNext(T) | onComplete
  nhiều:      | onNext(T1) | onNext(T2) | ... | onComplete
  lỗi:        | onNext(T1) | ... | onError
```

`Mono` và `Flux` không mô tả một giá trị đồng bộ đã có sẵn; chúng mô tả một Publisher có thể phát tín hiệu trong tương lai khi được subscribe và có demand. Nguồn có thể chạy đồng bộ hoặc bất đồng bộ. Cardinality không quyết định thread thực thi, thời điểm phát hay việc dữ liệu có được tính toán ngay hay không.

## `Mono<T>`: không hoặc một phần tử

`Mono<T>` phù hợp với thao tác trả về tối đa một kết quả: tìm một khách hàng theo ID, tải cấu hình, xác thực một token, lấy kết quả của một phép tính hoặc thực hiện một thao tác chỉ cần báo hoàn tất.

### Tạo Mono có giá trị

`Mono.just(value)` phát đúng một giá trị rồi hoàn tất:

```java
import reactor.core.publisher.Mono;

Mono<String> greeting = Mono.just("Xin chào Reactor");
```

Giá trị truyền vào `just` phải khác `null`. Java đánh giá đối số trước khi gọi `Mono.just`, nên nếu biểu thức tạo giá trị có side effect thì biểu thức đó chạy ngay khi pipeline được lắp ráp:

```java
Mono<Profile> profile = Mono.just(repository.loadProfile("user-42"));
```

`repository.loadProfile` được gọi ngay tại dòng khai báo. Nếu cần trì hoãn lời gọi đồng bộ, có thể dùng `Mono.fromCallable`; nếu cần tạo Publisher riêng theo từng subscription, dùng `Mono.defer`. Hai API này sẽ được tìm hiểu sâu ở bài về thời điểm tạo giá trị.

### Mono rỗng

`Mono.empty()` hoàn tất mà không phát `onNext`:

```java
Mono<Profile> profile = repository.findById("missing-id");
```

Một phương thức tìm kiếm có thể trả `Mono.empty()` khi không có bản ghi. Đây là kết quả hợp lệ, không phải lỗi. Downstream có thể xử lý bằng `switchIfEmpty`:

```java
Mono<Profile> profile = repository.findById(id)
    .switchIfEmpty(Mono.error(new ProfileNotFoundException(id)));
```

`switchIfEmpty` chỉ chạy Publisher dự phòng khi nguồn hoàn tất mà không phát phần tử. Nếu nguồn phát lỗi, lỗi vẫn truyền xuống theo đường xử lý lỗi.

### Mono lỗi

`Mono.error(error)` tạo Publisher kết thúc bằng `onError`:

```java
Mono<Profile> profile = Mono.error(
    new IllegalArgumentException("profile id không hợp lệ")
);
```

Lỗi không được xem là một giá trị `Profile`. Có thể chuyển đổi hoặc phục hồi lỗi bằng các operator như `onErrorMap`, `onErrorResume` và `retry` tùy chính sách ứng dụng.

### `Mono<Void>` cho thao tác chỉ cần hoàn tất

Một thao tác như lưu bản ghi, gửi thông báo hoặc xóa dữ liệu đôi khi không cần trả về đối tượng nghiệp vụ. Khi đó, `Mono<Void>` biểu diễn một Publisher chỉ quan tâm đến terminal signal:

```java
Mono<Void> saveAudit = auditRepository.save(entry).then();
```

`Mono<Void>` thường hoàn tất mà không phát `onNext`. Nó vẫn có thể kết thúc bằng lỗi. Không nên gọi `block()` chỉ để đợi hoàn tất trong một pipeline reactive đang chạy; hãy kết hợp bằng `then`, `thenReturn` hoặc các operator phù hợp để giữ luồng bất đồng bộ.

### Biểu diễn giá trị có thể null

Reactive Streams không cho phép `null` làm phần tử `onNext`. Nếu API cũ có thể trả `null`, dùng `Mono.justOrEmpty` để chuyển `null` thành Mono rỗng:

```java
Profile found = legacyRepository.findOrNull(id);
Mono<Profile> profile = Mono.justOrEmpty(found);
```

`Mono.justOrEmpty(Optional<T>)` cũng có thể chuyển `Optional.empty()` thành Mono rỗng và `Optional.of(value)` thành Mono có một phần tử. Cách này giúp biểu diễn sự vắng mặt mà không đưa `null` vào pipeline.

## `Flux<T>`: không hoặc nhiều phần tử

`Flux<T>` phù hợp với danh sách kết quả, luồng sự kiện, dữ liệu đọc theo trang hoặc các giá trị được phát theo thời gian. Một Flux có thể hoàn tất ngay mà không có phần tử, phát một phần tử hoặc phát vô hạn cho đến khi bị hủy.

### Tạo Flux từ các giá trị có sẵn

`Flux.just` phát các đối số theo thứ tự:

```java
import reactor.core.publisher.Flux;

Flux<String> statuses = Flux.just(
    "CREATED", "PAID", "PACKED", "SHIPPED"
);
```

`Flux.fromIterable` chuyển một `Iterable` thành Flux:

```java
import java.util.List;

List<Order> orders = loadOrdersFromMemory();
Flux<Order> orderStream = Flux.fromIterable(orders);
```

Nguồn trên duyệt danh sách đã có trong bộ nhớ. Nó không tự biến việc tải danh sách thành I/O bất đồng bộ và cũng không làm cho một collection lớn trở nên streaming nếu collection đã được tải toàn bộ trước đó.

`Flux.range(start, count)` phát một dãy số nguyên liên tiếp, hữu ích cho ví dụ, phân trang hoặc tạo chỉ số:

```java
Flux<Integer> pages = Flux.range(0, 5);
```

Kết quả là `0, 1, 2, 3, 4`. `count` là số phần tử cần phát, không phải giá trị kết thúc.

### Flux rỗng, lỗi và không phát tín hiệu

Các nguồn sau có ngữ nghĩa khác nhau:

```java
Flux<String> empty = Flux.empty();
Flux<String> failed = Flux.error(new IllegalStateException("source failed"));
Flux<String> never = Flux.never();
```

- `Flux.empty()` phát `onComplete` ngay mà không có phần tử.
- `Flux.error(error)` phát `onError` và kết thúc.
- `Flux.never()` không phát `onNext`, `onComplete` hoặc `onError`; subscription tồn tại cho tới khi bị hủy.

`never()` hữu ích trong một số phép kết hợp hoặc kiểm thử, nhưng thường không phải nguồn dữ liệu nghiệp vụ thông thường. Khi một pipeline dường như chờ mãi, hãy kiểm tra xem nguồn có thể không bao giờ phát terminal signal hay không.

### Flux từ sự kiện hoặc nguồn bất đồng bộ

Một Flux có thể đại diện cho sự kiện được phát theo thời gian, ví dụ tick định kỳ:

```java
import java.time.Duration;

Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));
```

`interval` phát số tăng dần theo chu kỳ và tiếp tục cho đến khi bị hủy. Nguồn bất đồng bộ cần được tiêu thụ theo vòng đời phù hợp; không nên dùng `blockLast()` trên event loop hoặc thread phục vụ request để chờ một Flux vô hạn.

## So sánh `Mono` và `Flux` qua tình huống nghiệp vụ

| Nhu cầu | Kiểu thường phù hợp | Ví dụ chữ ký |
|---|---|---|
| Tìm một khách hàng theo ID | `Mono<Customer>` | `Mono<Customer> findById(String id)` |
| Tìm danh sách đơn hàng | `Flux<Order>` | `Flux<Order> findByCustomer(String customerId)` |
| Tính một tổng tiền | `Mono<BigDecimal>` | `Mono<BigDecimal> calculateTotal(String orderId)` |
| Theo dõi sự kiện trạng thái | `Flux<OrderEvent>` | `Flux<OrderEvent> events(String orderId)` |
| Thực hiện thao tác không trả dữ liệu | `Mono<Void>` | `Mono<Void> deleteById(String id)` |
| Đọc một cấu hình có thể không tồn tại | `Mono<Config>` | `Mono<Config> findConfig(String key)` |

Không nên chọn `Mono` chỉ vì hiện tại bạn nghĩ nguồn thường trả một phần tử nếu hợp đồng có thể trả nhiều kết quả. Ngược lại, không cần dùng `Flux` cho một giá trị đơn lẻ nếu `Mono` diễn tả chính xác hơn cardinality. Kiểu trả về là một phần của hợp đồng API và giúp caller biết cách xử lý kết quả rỗng hoặc nhiều phần tử.

## Kết hợp `Mono` và `Flux`

Hai kiểu có thể kết hợp với nhau vì đều là Publisher. Toán tử được chọn sẽ quyết định cardinality của kết quả.

### Chuyển Mono thành Flux

`mono.flux()` chuyển một Mono thành Flux có tối đa một phần tử:

```java
Mono<Customer> customer = customerRepository.findById(id);
Flux<Customer> customerStream = customer.flux();
```

Đây là phép chuyển kiểu cardinality: nếu Mono phát một khách hàng, Flux phát khách hàng đó; nếu Mono rỗng, Flux cũng rỗng. Không có thêm phần tử được tạo ra.

### Lấy phần tử đầu tiên của Flux thành Mono

`flux.next()` tạo Mono phát phần tử đầu tiên của Flux rồi hủy subscription upstream:

```java
Mono<Order> firstOrder = orderRepository.findByCustomer(customerId)
    .next();
```

Nếu Flux rỗng, Mono kết quả cũng rỗng. Nếu Flux có nhiều phần tử, chỉ phần tử đầu tiên được giữ. Hãy dùng khi yêu cầu nghiệp vụ thực sự là lấy một phần tử đầu tiên; không dùng để che giấu việc API đáng lẽ phải trả danh sách.

### Đảm bảo Flux có đúng một phần tử

`single()` biến Flux thành Mono nhưng yêu cầu nguồn có chính xác một phần tử. Nếu nguồn rỗng hoặc có nhiều hơn một phần tử, Mono kết quả phát lỗi:

```java
Mono<Order> exactlyOne = orderRepository.findByExternalId(externalId)
    .single();
```

Nếu nguồn có thể rỗng nhưng không được có hơn một phần tử, `singleOrEmpty()` cho phép 0 hoặc 1 phần tử và vẫn báo lỗi nếu có nhiều hơn một:

```java
Mono<Order> zeroOrOne = orderRepository.findByExternalId(externalId)
    .singleOrEmpty();
```

Khác biệt này quan trọng khi kiểm tra tính duy nhất. `next()` âm thầm lấy phần tử đầu tiên; `singleOrEmpty()` xác nhận nguồn không phát quá một phần tử.

### Gom nhiều phần tử của Flux thành một Mono

`collectList()` thu thập các phần tử của Flux thành một `List` rồi phát list khi nguồn hoàn tất:

```java
import java.util.List;

Mono<List<Order>> allOrders = orderRepository.findByCustomer(customerId)
    .collectList();
```

Kiểu kết quả là `Mono<List<Order>>`: Mono phát đúng một list, kể cả khi list rỗng. Điều này khác với Flux rỗng, vốn không phát phần tử nào. `collectList()` cần giữ các phần tử cho tới khi nguồn hoàn tất, vì vậy không phù hợp với nguồn vô hạn hoặc nguồn có kích thước không được kiểm soát.

### Từ một Mono mở rộng thành nhiều phần tử

`flatMapMany` cho phép lấy một giá trị từ Mono rồi chuyển nó thành Flux:

```java
Flux<Order> orders = customerRepository.findById(customerId)
    .flatMapMany(customer -> orderRepository.findByCustomer(customer.id()));
```

Nếu Mono khách hàng rỗng, mapper không được gọi và Flux kết quả hoàn tất rỗng. Nếu có khách hàng, Publisher của các đơn hàng được subscribe và phát 0 đến nhiều đơn hàng.

## Chọn operator theo cardinality mong muốn

Các operator có thể giữ nguyên, giảm hoặc mở rộng cardinality:

| Operator | Đầu vào | Cardinality đầu ra thường gặp | Ý nghĩa |
|---|---|---|---|
| `map` | `Mono<T>` hoặc `Flux<T>` | Giữ nguyên số phần tử | Biến đổi mỗi phần tử thành một giá trị |
| `filter` | `Mono<T>` hoặc `Flux<T>` | Có thể giảm | Loại bỏ phần tử không thỏa điều kiện |
| `flatMap` | Publisher của `T` | Phụ thuộc Publisher con | Mỗi phần tử có thể tạo Publisher 0..N phần tử |
| `next` | `Flux<T>` | `Mono<T>` 0..1 | Lấy phần tử đầu tiên |
| `singleOrEmpty` | `Flux<T>` | `Mono<T>` 0..1 | Xác nhận không có hơn một phần tử |
| `collectList` | `Flux<T>` | `Mono<List<T>>` | Gom toàn bộ phần tử trước khi phát một list |
| `then` | `Mono<T>` hoặc `Flux<T>` | `Mono<Void>` | Bỏ giá trị, chỉ quan tâm hoàn tất hoặc lỗi |

Ví dụ, `map` không biến Flux thành Mono chỉ vì mapper trả về một object. Nếu nguồn có 100 phần tử, `map` có thể phát 100 phần tử đã biến đổi. Muốn lấy một kết quả tổng hợp, dùng `reduce` hoặc `collectList`; muốn lấy phần tử đầu tiên, dùng `next`; muốn xác nhận đúng một phần tử, dùng `single` hoặc `singleOrEmpty`.

## Backpressure và demand trong Mono, Flux

Vì cả `Mono` và `Flux` đều tuân thủ Reactive Streams, Subscriber kiểm soát lượng dữ liệu được phép phát thông qua `request(n)`. `Mono` chỉ có tối đa một phần tử, nên demand tối đa một phần tử là đủ để nhận giá trị; `Flux` có thể có nhiều phần tử và tiếp tục phát theo nhu cầu.

```java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

Flux.range(1, 5).subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(2);
    }

    @Override
    protected void hookOnNext(Integer value) {
        System.out.println(value);
        request(1);
    }
});
```

Subscriber bắt đầu bằng cách yêu cầu hai phần tử, sau đó yêu cầu thêm một phần tử sau mỗi lần xử lý. Đây là cách thể hiện demand tường minh. Các overload `subscribe` tiện dụng thường yêu cầu không giới hạn, vì vậy nếu cần điều tiết lượng dữ liệu, hãy dùng Subscriber có điều khiển hoặc thiết kế operator backpressure phù hợp.

Backpressure điều khiển số phần tử được phát, không tự quyết định tốc độ theo giây. Nếu nguồn là push-only và không thể dừng theo demand, adapter cần buffer hoặc overflow policy có giới hạn. Khi chuyển `Flux` thành `Mono` bằng `next()`, Reactor hủy upstream sau phần tử đầu tiên để không tiếp tục tiêu thụ phần còn lại.

## Subscribe và vòng đời Publisher

Khai báo `Mono` hoặc `Flux` thường chỉ tạo pipeline; nguồn bắt đầu thực thi theo semantics của Publisher khi có subscription. Nếu không có Subscriber, nhiều nguồn lazy sẽ không thực hiện công việc. Khi subscribe, Subscriber nhận `onSubscribe`, yêu cầu demand rồi nhận dữ liệu hoặc terminal signal.

```java
Flux<Integer> pipeline = Flux.range(1, 3)
    .map(value -> value * 10);

// Pipeline đã được lắp ráp; chưa có subscriber ở thời điểm này.
pipeline.subscribe(System.out::println);
```

Mỗi lần subscribe vào một nguồn lạnh thường tạo một lần thực thi độc lập. Một nguồn nóng có thể phát dữ liệu theo vòng đời riêng, nên Subscriber đến muộn có thể bỏ lỡ phần tử đã phát. Cardinality của `Mono`/`Flux` không tự cho biết nguồn là hot hay cold.

Trong ứng dụng reactive, ưu tiên kết hợp Publisher bằng operator thay vì gọi `block()`. Các phương thức `block`, `blockFirst` và `blockLast` có thể hữu ích trong test hoặc ở ranh giới imperative được kiểm soát, nhưng gọi chúng trên event loop hoặc trong pipeline có thể chặn thread và làm mất lợi ích của mô hình non-blocking.

## Kiểm thử cardinality bằng `StepVerifier`

`StepVerifier` cho phép xác nhận số phần tử và terminal signal. Test cho Mono có thể kiểm tra một giá trị, hoàn tất rỗng hoặc lỗi:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class MonoCardinalityTest {
    @Test
    void monoEmitsOneValue() {
        StepVerifier.create(Mono.just("ready"))
            .expectNext("ready")
            .verifyComplete();
    }

    @Test
    void monoCanCompleteEmpty() {
        StepVerifier.create(Mono.empty())
            .verifyComplete();
    }
}
```

Test cho Flux xác nhận nhiều phần tử theo thứ tự:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class FluxCardinalityTest {
    @Test
    void fluxEmitsManyValues() {
        StepVerifier.create(Flux.range(1, 3))
            .expectNext(1, 2, 3)
            .verifyComplete();
    }
}
```

Nên có test cho các trường hợp biên: Flux rỗng, Mono lỗi, `next()` hủy sau phần tử đầu, `singleOrEmpty()` báo lỗi khi có hai phần tử và `collectList()` phát list rỗng thay vì hoàn tất rỗng. Những test này giúp xác nhận API đang diễn tả đúng cardinality mà nghiệp vụ mong muốn.

## Những nhầm lẫn thường gặp

**Cho rằng Mono luôn có một giá trị.** Mono có thể phát 0 hoặc 1 phần tử; `Mono.empty()` là trường hợp hợp lệ.

**Cho rằng Flux luôn có nhiều phần tử.** Flux cũng có thể rỗng hoặc chỉ phát một phần tử. Nó chỉ cho phép cardinality 0..N.

**Cho rằng Mono và Flux quyết định đồng bộ hay bất đồng bộ.** Hai kiểu mô tả cardinality. Nguồn có thể phát đồng bộ trên thread gọi subscribe hoặc bất đồng bộ trên scheduler khác.

**Dùng `next()` khi cần xác nhận tính duy nhất.** `next()` lấy phần tử đầu tiên và hủy phần còn lại. Dùng `singleOrEmpty()` nếu cần phát hiện trường hợp có hơn một kết quả.

**Dùng `collectList()` cho nguồn vô hạn.** List sẽ tiếp tục giữ phần tử và có thể làm bộ nhớ tăng không giới hạn. Hãy dùng batch/window hoặc xử lý từng phần tử.

**Truyền `null` vào `Mono.just`.** Reactive Streams không cho phép `null` trong `onNext`. Dùng `justOrEmpty` hoặc biểu diễn trường hợp thiếu bằng kiểu dữ liệu rõ ràng.

**Gọi `block()` bên trong pipeline.** Blocking có thể chiếm thread xử lý và gây deadlock hoặc giảm throughput. Hãy kết hợp Publisher bằng operator và chỉ block tại ranh giới imperative được kiểm soát.

**Cho rằng không subscribe thì mọi nguồn đều không chạy.** Nhiều nguồn Reactor là lazy, nhưng biểu thức Java truyền vào `just` hoặc lời gọi tạo Publisher có thể đã được đánh giá ở assembly time. Phân biệt việc tạo Publisher với việc thực thi nguồn.

## Tự kiểm tra

1. Cardinality của `Mono<T>` và `Flux<T>` khác nhau như thế nào?
2. Vì sao `Mono.empty()` là một kết quả hợp lệ dù không phát `onNext`?
3. `Flux.empty()`, `Flux.error(...)` và `Flux.never()` có những terminal signal khác nhau nào?
4. Khi nào dùng `Flux.next()` và khi nào dùng `singleOrEmpty()`?
5. Vì sao `collectList()` tạo `Mono<List<T>>` và có thể nguy hiểm với nguồn vô hạn?
6. `Mono<Void>` biểu diễn điều gì và vì sao nó vẫn có thể kết thúc bằng lỗi?
7. Cardinality có quyết định nguồn hot/cold hoặc thread thực thi không?
8. Backpressure được thể hiện như thế nào khi Subscriber tiêu thụ một Flux nhiều phần tử?

Khi chọn `Mono` cho nguồn không–một và `Flux` cho nguồn không–nhiều, chữ ký API sẽ diễn tả rõ số kết quả có thể xuất hiện. Kết hợp cardinality đúng với operator như `next`, `singleOrEmpty`, `collectList` và `flatMapMany` giúp pipeline Reactor dễ đọc, dễ kiểm thử và giữ đúng hợp đồng dữ liệu.
