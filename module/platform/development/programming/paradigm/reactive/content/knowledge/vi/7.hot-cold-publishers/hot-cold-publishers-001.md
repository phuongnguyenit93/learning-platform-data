# Nguồn lạnh: dữ liệu và tác vụ được tạo theo từng đăng ký

Trong module `REACTIVE_PROGRAMMING`, ta học cách tổ chức các luồng sự kiện bất đồng bộ theo hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams, đồng thời thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Một khái niệm nền tảng khi làm việc với các luồng đó là **nguồn lạnh** (*cold publisher*): nguồn bắt đầu phát dữ liệu khi có subscriber và mỗi subscription thường nhận một lần thực thi độc lập của nguồn.

Đặc tính này phù hợp với những tác vụ như đọc một bản ghi, gọi dịch vụ từ xa, duyệt một tập dữ liệu hoặc tính toán kết quả theo yêu cầu của từng người tiêu thụ. Tuy nhiên, cần phân biệt hai câu hỏi: nguồn có phát dữ liệu độc lập cho từng subscription hay không, và phép tính tạo ra dữ liệu được thực hiện ở thời điểm lắp ráp hay lúc subscription bắt đầu. Hai đặc tính này liên quan nhưng không đồng nghĩa.

## 1. Nguồn lạnh hoạt động như thế nào?

Với một nguồn lạnh, việc tạo Publisher thường chỉ mô tả công việc cần làm. Khi subscriber đăng ký, nguồn bắt đầu thực thi và phát các tín hiệu theo hợp đồng Reactive Streams. Nếu có subscriber thứ hai, nguồn thực hiện một subscription khác; subscriber đó nhận chuỗi tín hiệu riêng của mình.

Ví dụ, `Flux.range(1, 3)` mô tả một luồng gồm ba số. Mỗi subscriber nhận một chuỗi `1, 2, 3`:

```java
Flux<Integer> numbers = Flux.range(1, 3);

numbers.subscribe(value -> System.out.println("A: " + value));
numbers.subscribe(value -> System.out.println("B: " + value));
```

Kết quả quan sát được có dạng:

```text
A: 1
A: 2
A: 3
B: 1
B: 2
B: 3
```

Mỗi subscriber có subscription và demand riêng. Subscriber A tiêu thụ luồng của A; subscriber B bắt đầu một lượt tiêu thụ khác. Một subscription kết thúc hoặc bị hủy không tự động kết thúc subscription còn lại.

```mermaid
flowchart TD
    P[Cold Publisher: Flux.range(1, 3)] --> S1[Subscription A]
    P --> S2[Subscription B]
    S1 --> A1[A nhận 1, 2, 3]
    S2 --> B1[B nhận 1, 2, 3]
```

Đây là cách hiểu về tính độc lập ở mức subscription. Nó không có nghĩa mọi đối tượng Java liên quan đều được sao chép sâu. Nếu Publisher giữ một tham chiếu đến collection có thể thay đổi, các subscription có thể đọc cùng collection đó ở những thời điểm khác nhau.

## 2. Những nguồn lạnh thường gặp trong Reactor

Reactor cung cấp nhiều cách tạo nguồn lạnh. Mỗi cách phù hợp với một kiểu dữ liệu hoặc tác vụ khác nhau.

| API | Mục đích | Hành vi chính |
|---|---|---|
| `Mono.just(value)` | Phát một giá trị đã có | Giữ giá trị khi lắp ráp; mỗi subscription phát giá trị đó |
| `Flux.just(a, b, c)` | Phát một số giá trị đã có | Giữ các tham chiếu đầu vào khi lắp ráp; mỗi subscription phát lại chuỗi |
| `Flux.range(start, count)` | Phát một dãy số | Tạo chuỗi số cho từng subscription |
| `Flux.fromIterable(iterable)` | Phát các phần tử từ `Iterable` | Mỗi subscription duyệt nguồn iterable |
| `Mono.fromSupplier(supplier)` | Tạo tối đa một giá trị bằng supplier | Gọi supplier theo subscription; `null` được xem như không có giá trị |
| `Mono.fromCallable(callable)` | Bọc tác vụ đồng bộ có thể ném lỗi | Thực thi callable theo subscription; ngoại lệ được truyền thành `onError` |
| `Mono.defer(factory)` / `Flux.defer(factory)` | Tạo Publisher theo từng subscription | Gọi factory khi có subscription và đăng ký vào Publisher được trả về |

`just`, `range` và `fromIterable` hữu ích khi đã có dữ liệu hoặc cấu trúc dữ liệu để phát. `fromCallable` và `fromSupplier` phù hợp khi cần trì hoãn một phép tính trả về một giá trị. `defer` phù hợp khi cần tạo cả Publisher mới theo từng subscription, chẳng hạn chọn nguồn dựa trên trạng thái tại thời điểm đăng ký.

## 3. Lắp ráp Publisher không nhất thiết là thực thi tác vụ

Một nhầm lẫn thường gặp là cho rằng mọi biểu thức nằm trong `Mono.just(...)` đều được trì hoãn. Java đánh giá đối số trước khi gọi phương thức, vì vậy biểu thức tạo giá trị chạy ngay khi lắp ráp Publisher:

```java
Mono<Account> account = Mono.just(repository.loadAccount(accountId));
```

`repository.loadAccount(accountId)` chạy ngay tại dòng trên. `Mono.just` giữ kết quả đã có và phát giá trị đó cho mỗi subscriber. Publisher có thể phát theo subscription, nhưng tác vụ truy vấn đã hoàn thành trước khi subscriber đăng ký.

Để trì hoãn tác vụ đến lúc subscription, hãy dùng `fromCallable`:

```java
Mono<Account> account = Mono.fromCallable(
    () -> repository.loadAccount(accountId)
);
```

Với cách này, lời gọi repository nằm bên trong callable và được thực hiện khi subscription tiêu thụ nguồn. Nếu hai subscriber đăng ký, callable được thực hiện cho từng subscription. Nếu callable ném ngoại lệ, Reactor truyền lỗi xuống subscriber qua `onError`.

Có thể dùng `defer` nếu cần trì hoãn việc tạo Publisher:

```java
Mono<Account> account = Mono.defer(
    () -> Mono.just(repository.loadAccount(accountId))
);
```

Supplier truyền cho `defer` chạy theo từng subscription. Mỗi lần chạy, nó gọi repository rồi tạo một `Mono` mới. Nếu lời gọi repository ném ngoại lệ trong supplier, Reactor chuyển ngoại lệ thành tín hiệu lỗi của subscription tương ứng.

Hai cách `fromCallable` và `defer` đều có thể tạo hành vi thực thi theo subscription, nhưng khác mục đích: `fromCallable` bọc một tác vụ trả về giá trị; `defer` trì hoãn việc chọn hoặc tạo Publisher. Nếu tác vụ trả về một Publisher, có thể dùng `Mono.defer` hoặc `Flux.defer` để tránh tạo nguồn quá sớm.

## 4. Nguồn lạnh không có nghĩa dữ liệu luôn mới

Nguồn lạnh mô tả cách Publisher tương tác với subscription. Nó không bảo đảm rằng giá trị phát ra luôn là một bản sao mới hoặc được tính toán lại.

Ví dụ:

```java
Account sharedAccount = repository.loadAccount(accountId);
Mono<Account> account = Mono.just(sharedAccount);
```

Truy vấn chạy một lần khi lắp ráp. Mỗi subscription nhận cùng tham chiếu `sharedAccount`. Nếu `Account` là đối tượng mutable, subscriber này có thể quan sát thay đổi do subscriber hoặc thành phần khác thực hiện trên cùng đối tượng.

Trong khi đó:

```java
Mono<Account> account = Mono.fromCallable(
    () -> repository.loadAccount(accountId)
);
```

Mỗi subscription gọi repository lại. Kết quả có thể là những đối tượng khác nhau và dữ liệu có thể khác nhau nếu trạng thái lưu trữ đã thay đổi. Tuy nhiên, điều đó còn phụ thuộc repository và nguồn dữ liệu; Reactor không tự bảo đảm snapshot nhất quán hoặc tạo bản sao sâu.

Với `Flux.fromIterable`, mỗi subscription duyệt iterable. Nếu iterable là một collection dùng chung và collection bị sửa giữa các lần đăng ký, subscription sau có thể thấy nội dung mới. Nếu cần snapshot ổn định, hãy tạo snapshot rõ ràng, chẳng hạn sao chép collection trước khi tạo Publisher hoặc tạo collection bên trong `defer` theo yêu cầu nghiệp vụ.

| Cách tạo nguồn | Khi nào tác vụ tạo dữ liệu chạy? | Mỗi subscription nhận gì? |
|---|---|---|
| `Mono.just(load())` | Khi lắp ráp | Cùng giá trị đã tính trước |
| `Mono.fromCallable(this::load)` | Khi subscription tiêu thụ nguồn | Kết quả của lần gọi riêng |
| `Mono.defer(() -> Mono.just(load()))` | Khi factory chạy theo subscription | Publisher mới chứa kết quả lần gọi đó |
| `Mono.just(existingMutableObject)` | Không có phép tạo lại đối tượng | Cùng tham chiếu đối tượng |

Vì vậy, khi thiết kế nguồn lạnh, hãy xác định cả vòng đời của Publisher lẫn vòng đời của dữ liệu mà Publisher giữ hoặc tạo.

## 5. Ví dụ: đếm số lần thực thi

Một bộ đếm giúp quan sát rõ một tác vụ được thực thi một lần cho mỗi subscription:

```java
AtomicInteger executions = new AtomicInteger();

Mono<Integer> cold = Mono.fromCallable(executions::incrementAndGet);

cold.subscribe(value -> System.out.println("A: " + value));
cold.subscribe(value -> System.out.println("B: " + value));
```

Kết quả:

```text
A: 1
B: 2
```

Publisher `cold` được tạo một lần, nhưng callable được gọi hai lần. Đây là một ví dụ về việc tái sử dụng cùng một mô tả Publisher cho nhiều subscription độc lập.

Có thể kiểm tra bằng `StepVerifier`:

```java
AtomicInteger executions = new AtomicInteger();
Mono<Integer> cold = Mono.fromCallable(executions::incrementAndGet);

StepVerifier.create(cold)
    .expectNext(1)
    .verifyComplete();

StepVerifier.create(cold)
    .expectNext(2)
    .verifyComplete();

assertEquals(2, executions.get());
```

Mỗi lần `StepVerifier.create(cold)` tạo một subscription mới. Vì callable tăng bộ đếm, kết quả lần đầu là `1`, lần thứ hai là `2`.

## 6. Lỗi và retry trên nguồn lạnh

Vì tác vụ của nguồn lạnh thường được thực hiện theo subscription, lỗi cũng thường gắn với lần thực thi tương ứng. Một subscriber có thể nhận lỗi trong khi một subscriber khác vẫn thực hiện thành công nếu trạng thái nguồn hoặc điều kiện bên ngoài đã thay đổi.

```java
Mono<String> response = Mono.fromCallable(() -> remoteClient.fetch());
```

Nếu `fetch()` ném ngoại lệ, subscription đó kết thúc bằng `onError`. Một subscriber khác đăng ký sau sẽ gọi `fetch()` một lần nữa. Kết quả của lần sau phụ thuộc hệ thống từ xa ở thời điểm thực thi lần đó.

Toán tử `retry` tạo subscription lại khi nguồn lỗi:

```java
Mono<String> response = Mono.fromCallable(() -> remoteClient.fetch())
    .retry(2);
```

`retry(2)` cho phép tối đa hai lần đăng ký lại sau lần thử đầu tiên. Với nguồn lạnh, mỗi lần thử lại thực thi callable lần nữa. Điều này hữu ích khi lỗi có tính tạm thời, nhưng có thể lặp lại side effect. Nếu `fetch()` thực chất là lệnh ghi dữ liệu, gửi thanh toán hoặc tạo tài nguyên, cần bảo đảm thao tác idempotent hoặc dùng khóa/idempotency key trước khi retry.

Nếu muốn chuyển lỗi sang nguồn thay thế, có thể dùng `onErrorResume`:

```java
Mono<Config> config = Mono.fromCallable(configClient::loadRemote)
    .onErrorResume(error -> Mono.fromCallable(configStore::loadLocal));
```

Nguồn chính và nguồn dự phòng đều được thực thi theo subscription. Khi nguồn chính lỗi, Reactor đăng ký vào Publisher dự phòng. Nếu nguồn dự phòng cũng lỗi, downstream nhận lỗi đó.

## 7. Backpressure, cancellation và scheduler

Mỗi subscription của nguồn lạnh có nhu cầu riêng. Một subscriber yêu cầu một phần tử không làm subscriber khác tự động nhận hoặc mất demand. Với nguồn hỗ trợ backpressure như `Flux.range` và `Flux.fromIterable`, Publisher phát theo lượng demand mà subscription yêu cầu.

```java
Flux<Integer> cold = Flux.range(1, 5);

StepVerifier.create(cold, 0)
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(1)
    .expectNext(3)
    .thenCancel()
    .verify();
```

Trong ví dụ, subscriber ban đầu chưa yêu cầu phần tử. Sau đó subscriber yêu cầu hai phần tử, tiếp tục yêu cầu một phần tử rồi hủy. Subscription đó dừng tại phần tử thứ ba. Một subscription khác vào cùng `cold` vẫn có thể bắt đầu một lượt phát mới.

Hủy một subscription lạnh sẽ hủy công việc thuộc subscription đó theo khả năng của nguồn. Nó không nhất thiết hủy một subscription khác. Với tác vụ đồng bộ không thể ngắt giữa chừng, cancellation có thể không dừng ngay phần code đang chạy; vì vậy cần xem xét khả năng hủy của API bên dưới.

Nếu tác vụ đồng bộ có blocking, có thể đưa phần thực thi nguồn sang scheduler phù hợp:

```java
Mono<Account> account = Mono.fromCallable(
        () -> repository.loadAccount(accountId)
    )
    .subscribeOn(Schedulers.boundedElastic());
```

`subscribeOn` điều khiển scheduler cho quá trình thực thi nguồn. Mỗi subscription vẫn là một lần gọi riêng; scheduler chỉ quyết định nơi công việc chạy. Khi nhiều subscriber cùng đăng ký, nhiều lần thực thi có thể diễn ra trên các worker khác nhau tùy scheduler và tải. Không nên dùng scheduler để suy ra thứ tự hoàn tất giữa các subscription.

## 8. Khi nào một nguồn lạnh trở thành nguồn chia sẻ?

Nguồn lạnh có thể được chuyển thành nguồn chia sẻ bằng các toán tử chia sẻ hoặc lưu cache. Khi đó, nhiều subscriber có thể cùng tiêu thụ một lần thực thi upstream hoặc nhận lại tín hiệu đã lưu.

**`share()`** chia sẻ subscription upstream giữa các subscriber cùng tham gia vào nguồn đã chia sẻ. Những subscriber đến sau có thể chỉ nhận phần dữ liệu được phát từ thời điểm họ tham gia; chúng không mặc nhiên được phát lại toàn bộ lịch sử.

```java
Flux<Event> shared = Flux.defer(
        () -> Flux.fromIterable(loadEvents())
    )
    .share();
```

**`cache()`** lưu các tín hiệu đã phát và có thể phát lại chúng cho subscriber đăng ký sau. Với `Mono`, điều này thường hữu ích khi muốn chia sẻ kết quả của một lần tải:

```java
Mono<Config> cached = Mono.fromCallable(configClient::load)
    .cache();
```

Khi dùng `cache`, cần hiểu chính sách lưu và thời hạn của cache, bởi dữ liệu có thể cũ so với trạng thái nguồn. `share` và `cache` thay đổi cách các subscriber phối hợp sử dụng nguồn; hãy chọn theo yêu cầu về phát lại, thời gian sống dữ liệu và việc có cần thực thi lại nguồn hay không.

## 9. Những lỗi thiết kế thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Gọi tác vụ tốn thời gian trong `Mono.just(load())` | Tác vụ chạy ngay khi lắp ráp | Dùng `fromCallable` hoặc `defer` |
| Nghĩ mỗi subscription luôn có object mới | `just` có thể giữ cùng tham chiếu | Tạo dữ liệu bên trong callable/factory hoặc sao chép rõ ràng |
| Retry một thao tác ghi không idempotent | Side effect có thể lặp nhiều lần | Thiết kế idempotency hoặc chính sách retry an toàn |
| Cho rằng hai subscriber chia sẻ cùng một lần chạy | Nguồn lạnh thường thực thi riêng theo subscription | Dùng `share` hoặc `cache` nếu thực sự muốn chia sẻ |
| Cho rằng `share` phát lại toàn bộ dữ liệu cũ | Subscriber đến muộn có thể bỏ lỡ phần đã phát | Dùng cache/replay có giới hạn nếu cần phát lại |
| Cho rằng cancellation luôn dừng ngay tác vụ blocking | API blocking có thể không hỗ trợ ngắt | Dùng API có timeout/cancellation hoặc cô lập tác vụ |

Khi thiết kế Publisher, hãy trả lời ba câu hỏi: tác vụ bắt đầu khi nào, mỗi subscription có thực thi riêng hay dùng chung kết quả, và subscriber có thể điều khiển demand/cancellation đến mức nào. Những câu trả lời này giúp chọn đúng giữa `just`, `fromCallable`, `defer`, `share` và `cache`.

Nguồn lạnh là nền tảng cho các pipeline mà mỗi người tiêu thụ cần một lượt thực thi độc lập. Hiểu rõ sự khác biệt giữa phát dữ liệu theo subscription và trì hoãn phép tính sẽ giúp tránh các truy vấn chạy quá sớm, side effect ngoài dự kiến và việc chia sẻ dữ liệu mutable không an toàn.
