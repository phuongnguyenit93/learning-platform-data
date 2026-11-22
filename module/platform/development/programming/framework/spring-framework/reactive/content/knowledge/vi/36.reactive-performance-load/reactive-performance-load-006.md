# Kiểm thử phía nhận chậm và nguồn phát nhanh trong Spring WebFlux và Reactor

## 1. Bài toán: producer nhanh hơn consumer

Trong hệ thống reactive, một publisher có thể phát dữ liệu nhanh hơn tốc độ subscriber xử lý. Ví dụ:

- Một service nhận hàng nghìn event mỗi giây từ message broker.
- Một client WebSocket đẩy dữ liệu liên tục nhưng service phía sau xử lý từng message chậm.
- Một API streaming đọc từ database nhanh hơn tốc độ mạng của HTTP client.
- Một pipeline gọi dịch vụ ngoài, mỗi request mất vài trăm mili giây, trong khi nguồn phát hàng nghìn phần tử.
- Một `Flux.interval` phát theo nhịp cố định nhưng downstream đang bận ghi file hoặc gọi database.

Nếu không điều tiết, hệ thống có thể tích lũy queue, tăng độ trễ, tăng heap, phát sinh GC pressure hoặc cuối cùng hết bộ nhớ. Một số nguồn có thể bị yêu cầu dừng/tạm giảm tốc; một số nguồn khác là hot source hoặc callback bên ngoài nên không thể tạm dừng dễ dàng.

Reactive Streams định nghĩa **backpressure** để subscriber báo cho publisher biết nó sẵn sàng nhận bao nhiêu phần tử. Reactor cung cấp các operator để giữ, bỏ, lấy phần tử mới nhất, giới hạn demand hoặc giới hạn số công việc đồng thời.

Bài học này tập trung vào việc **kiểm thử một phía nhận chậm khi nguồn phát nhanh**, hiểu chính sách xử lý quá tải và chọn cách phù hợp với semantics dữ liệu.

Sau bài này, bạn có thể:

1. Giải thích `request(n)` và `cancel()` trong Reactive Streams.
2. Phân biệt nguồn cold tuân thủ demand với hot/external source khó điều tiết.
3. Dùng `StepVerifier` để kiểm soát demand và mô phỏng subscriber nhận chậm.
4. Dùng `TestPublisher` để kiểm tra request propagation và hành vi của pipeline.
5. Kiểm thử bounded buffer, overflow, drop và latest-value policies.
6. Phân biệt `limitRate`, `publishOn(prefetch)`, `flatMap(concurrency)` và `onBackpressure...`.
7. Thiết kế adapter cho callback/event source bên ngoài.
8. Đánh giá queue, payload size, concurrency, cancellation và memory pressure.
9. Kiểm thử streaming endpoint của Spring WebFlux bằng `WebTestClient`.
10. Xây dựng dự án Java 17+ Spring Boot 3.3.5 với các bài test Reactor có thể chạy bằng Maven.

## 2. Backpressure trong Reactive Streams

Reactive Streams có bốn vai trò chính:

- `Publisher<T>`: phát dữ liệu.
- `Subscriber<T>`: nhận dữ liệu.
- `Subscription`: kết nối hai bên, cho phép yêu cầu thêm phần tử hoặc hủy.
- `Processor<T, R>`: vừa nhận vừa phát, thường được biểu diễn trong Reactor bằng các operator.

Khi subscribe, publisher gọi `onSubscribe(subscription)`. Subscriber có thể yêu cầu một số phần tử:

```java
subscription.request(1);
```

Khi cần thêm dữ liệu, subscriber gọi `request(n)` lần nữa. Khi không còn quan tâm, subscriber gọi:

```java
subscription.cancel();
```

Mô hình:

```text
Subscriber                         Publisher
    |                                  |
    |<----------- onSubscribe ---------|
    |                                  |
    |------------- request(2) -------->|
    |<-------------- onNext(A) --------|
    |<-------------- onNext(B) --------|
    |                                  |
    |------------- request(1) -------->|
    |<-------------- onNext(C) --------|
    |                                  |
    |------------- cancel() ---------->|
```

### 2.1. Demand là số phần tử được phép phát

Nếu subscriber đã yêu cầu 2 phần tử, publisher tuân thủ Reactive Streams không được tự ý phát phần tử thứ 3 trước khi nhận thêm demand.

Backpressure không phải là một lệnh “hãy chạy chậm 100 ms”. Nó là một giao thức demand theo số phần tử. Publisher có thể phát nhanh khi demand lớn, và phải điều tiết khi demand thấp.

### 2.2. Không yêu cầu vô hạn trong mọi tình huống

Một subscriber có thể gọi:

```java
subscription.request(Long.MAX_VALUE);
```

Điều đó biểu thị demand rất lớn. Khi một operator yêu cầu upstream vô hạn rồi tự buffer/drop ở phía mình, upstream không còn nhận được tín hiệu giới hạn tốc độ từ downstream. Vì vậy cần hiểu rõ operator đang áp dụng chính sách gì.

### 2.3. Cancellation là tín hiệu kết thúc nhu cầu

Khi HTTP client đóng kết nối hoặc subscriber cancel, cancellation nên truyền ngược upstream để dừng công việc khi có thể.

Tuy nhiên, cancel không bảo đảm một side effect đã bắt đầu sẽ rollback. Nếu service đã gửi lệnh tới database hoặc hệ thống ngoài, ứng dụng phải tự xác định transaction và cancellation semantics.

## 3. Nguồn phát và phía nhận có đặc tính khác nhau

### 3.1. Cold publisher có thể tuân thủ demand

Ví dụ:

```java
Flux<Integer> source = Flux.range(1, 5);
```

Mỗi subscriber tạo một subscription riêng. Source có thể phát theo demand của subscriber.

Các nguồn cold phổ biến:

- `Flux.range(...)`
- `Flux.fromIterable(...)`
- `Mono.fromCallable(...)`
- Một số reactive database/client publishers.
- Publisher được tạo bằng `defer(...)`.

Với nguồn tuân thủ demand, subscriber chậm có thể yêu cầu từng phần tử và upstream điều tiết theo.

### 3.2. Hot hoặc external source có thể không dừng được

Ví dụ:

- Callback của SDK thiết bị.
- Listener từ thư viện cũ.
- Event bus bên ngoài.
- Message broker consumer đã được cấu hình pull/push riêng.
- Nguồn đo telemetry phát theo chu kỳ cố định.
- `Flux.create` nối với API callback.

Nguồn có thể tiếp tục phát dù downstream chưa sẵn sàng. Khi đó phải quyết định giữ dữ liệu, bỏ dữ liệu, giữ giá trị mới nhất hoặc báo lỗi quá tải.

### 3.3. “Fast producer” không chỉ có nghĩa phát nhiều phần tử

Tải thực tế phụ thuộc cả:

- Tốc độ phần tử/giây.
- Kích thước trung bình của mỗi payload.
- Số subscriber đồng thời.
- Thời gian xử lý một phần tử.
- Số tác vụ con đang chạy.
- Số queue trung gian và prefetch.
- Tỷ lệ retry và thời gian chờ downstream.

Một stream 1.000 phần tử/giây với payload 1 KB có đặc tính bộ nhớ khác với stream 1.000 phần tử/giây nhưng payload 2 MB.

## 4. Dùng `StepVerifier` để mô phỏng subscriber chậm

`StepVerifier` của `reactor-test` cho phép điều khiển demand của subscriber trong test.

Ví dụ yêu cầu từng phần tử:

```java
StepVerifier.create(Flux.range(1, 3), 0)
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(1)
        .expectNext(2)
        .thenRequest(1)
        .expectNext(3)
        .verifyComplete();
```

Tham số `0` là demand ban đầu. Subscriber chưa yêu cầu phần tử nào cho đến khi gọi `thenRequest(1)`.

Test chứng minh:

1. Publisher không cần phát toàn bộ dữ liệu ngay.
2. Subscriber có thể tăng demand từng bước.
3. Các phần tử được phát theo thứ tự khi source tuân thủ demand.
4. Publisher complete sau phần tử cuối.

### 4.1. Kiểm tra không có dữ liệu khi chưa request

```java
StepVerifier.create(Flux.range(1, 3), 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext(1)
        .thenCancel()
        .verify();
```

Test hủy sau phần tử đầu. Nếu source có side effect hoặc resource, cần thêm kiểm tra cleanup/cancellation ở lớp service.

### 4.2. `initialRequest(0)` hữu ích hơn `Thread.sleep`

Không cần dùng `Thread.sleep` để cố tình làm consumer chậm. `StepVerifier` cho phép điều khiển demand một cách xác định, ít phụ thuộc tốc độ máy hoặc timing của test runner.

`thenAwait(Duration)` hữu ích khi test có clock/delay, nhưng nó không thay thế việc kiểm soát request. Với pipeline không phụ thuộc thời gian, hãy ưu tiên demand rõ ràng.

## 5. Dùng `TestPublisher` để điều khiển producer

`TestPublisher<T>` cho phép test phát dữ liệu theo ý muốn và kiểm tra subscription/demand.

```java
TestPublisher<Integer> source = TestPublisher.create();
```

Một test kiểm tra source chưa nhận request:

```java
StepVerifier.create(source.flux(), 0)
        .then(() -> source.assertNoRequest())
        .thenRequest(1)
        .then(() -> source.assertWasRequested())
        .then(() -> source.next(10))
        .expectNext(10)
        .thenCancel()
        .verify();
```

Ý nghĩa:

- Subscriber ban đầu không request.
- Test xác nhận source chưa được yêu cầu dữ liệu.
- Sau `thenRequest(1)`, source nhận demand.
- Test chủ động phát phần tử `10`.
- Subscriber nhận đúng một phần tử rồi cancel.

### 5.1. Các assertion hữu ích

| API | Mục đích |
|---|---|
| `assertNoRequest()` | Xác nhận chưa có demand upstream |
| `assertWasRequested()` | Xác nhận source đã được yêu cầu |
| `assertMinRequested(n)` | Xác nhận demand ít nhất bằng `n` |
| `assertMaxRequested(n)` | Xác nhận demand không vượt `n` |
| `assertSubscribers(n)` | Kiểm tra số subscriber |
| `assertCancelled()` | Xác nhận subscription đã bị cancel |
| `assertNotCancelled()` | Xác nhận chưa bị cancel |

Dùng assertion về demand để kiểm tra operator có truyền request ngược upstream hay không. Tránh assert một con số prefetch nội bộ cố định nếu code không sở hữu contract đó; chi tiết prefetch có thể thay đổi theo phiên bản/operator.

### 5.2. `TestPublisher` tuân thủ và không tuân thủ demand

`TestPublisher.create()` tạo publisher phục vụ test theo contract Reactive Streams.

Khi cần mô phỏng một nguồn cố tình phát vượt demand, Reactor Test có thể tạo non-compliant publisher:

```java
TestPublisher<Integer> brokenSource =
        TestPublisher.createNoncompliant(
                TestPublisher.Violation.REQUEST_OVERFLOW);
```

Chỉ dùng kiểu non-compliant để kiểm tra adapter hoặc code xử lý nguồn bên ngoài không tuân thủ demand. Không biến publisher test không tuân thủ thành ví dụ thiết kế ứng dụng thông thường.

## 6. Chọn chính sách khi producer nhanh hơn consumer

Không có một chiến lược đúng cho mọi loại dữ liệu.

| Chính sách | Hành vi | Phù hợp với |
|---|---|---|
| Propagate backpressure | Yêu cầu upstream giảm phát | Source có thể điều tiết |
| Buffer | Giữ phần tử chờ consumer | Burst ngắn, cần giữ mọi event |
| Bounded buffer + error | Giữ tối đa N phần tử, quá tải thì lỗi | Không được âm thầm mất dữ liệu |
| Drop | Bỏ phần tử khi không có demand | Telemetry hoặc dữ liệu có thể mất |
| Latest | Chỉ giữ giá trị mới nhất | Trạng thái snapshot, dashboard |
| Limit rate/demand | Chia nhỏ request upstream | Source tuân thủ demand |
| Bounded concurrency | Giới hạn số tác vụ đang chạy | I/O downstream chậm |
| Durable queue | Ghi dữ liệu ra hệ thống bền vững | Burst dài, cần khả năng phục hồi |

Trước khi chọn operator, hãy trả lời:

1. Có được phép mất dữ liệu không?
2. Nếu buffer đầy, cần báo lỗi, bỏ phần tử cũ hay bỏ phần tử mới?
3. Source có thể pause/resume không?
4. Có thể lưu vào broker/database bền vững không?
5. Payload lớn đến mức nào?
6. Một subscriber chậm có được làm chậm tất cả subscriber khác không?

## 7. `onBackpressureBuffer`: giữ phần tử khi downstream chưa sẵn sàng

`onBackpressureBuffer()` lưu các phần tử khi downstream không có demand.

```java
Flux<Integer> buffered = source.onBackpressureBuffer();
```

Dạng không giới hạn có thể giữ rất nhiều phần tử nếu producer tiếp tục nhanh hơn consumer. Với tải không kiểm soát, queue có thể tăng cho tới khi bộ nhớ cạn.

### 7.1. Bounded buffer

```java
Flux<Integer> buffered = source.onBackpressureBuffer(256);
```

Giới hạn số phần tử đang chờ. Khi vượt capacity, Reactor phát overflow error theo overload này.

Bounded buffer giúp đặt giới hạn bộ nhớ rõ ràng, nhưng cần có kế hoạch khi queue đầy:

- Trả lỗi để báo quá tải.
- Retry ở tầng có thể retry an toàn.
- Dừng/tạm giảm source nếu có API pause.
- Chuyển sang durable queue.
- Dùng drop/latest nếu nghiệp vụ cho phép mất dữ liệu.

### 7.2. Chọn phần tử bị bỏ khi buffer đầy

Reactor có `BufferOverflowStrategy` để định nghĩa cách xử lý overflow trong overload tương ứng:

```java
Flux<Integer> dropOldest = source.onBackpressureBuffer(
        256,
        BufferOverflowStrategy.DROP_OLDEST);

Flux<Integer> dropLatest = source.onBackpressureBuffer(
        256,
        BufferOverflowStrategy.DROP_LATEST);
```

- `DROP_OLDEST`: bỏ phần tử cũ nhất trong buffer để nhận phần tử mới.
- `DROP_LATEST`: bỏ phần tử mới đến khi buffer đầy.
- `ERROR`: báo overflow.

Đọc đúng semantics của dữ liệu trước khi chọn. Với trạng thái mới nhất, drop-oldest có thể hợp lý. Với event tài chính hoặc audit, drop có thể không chấp nhận được.

### 7.3. Buffer không phải là vô hạn năng lực

Nếu producer liên tục nhanh gấp đôi consumer, queue sẽ tăng cho tới khi đầy. Buffer chỉ hấp thụ burst trong một khoảng thời gian; nó không giải quyết mất cân bằng tốc độ kéo dài.

Một buffer có capacity 1.000 phần tử không có nghĩa hệ thống xử lý được tải vô hạn. Khi queue đầy, hệ thống phải có overflow policy hoặc source throttling.

### 7.4. Operator backpressure buffer thay đổi demand upstream

Các operator `onBackpressure...` cần tiếp nhận tín hiệu upstream để tự áp dụng chính sách, thường yêu cầu upstream demand lớn (unbounded) rồi quản lý phần tử ở phía mình. Vì vậy không nên đặt chúng ở mọi nơi mà không hiểu tác động tới upstream.

## 8. `onBackpressureDrop`: bỏ phần tử khi không có demand

```java
Flux<Integer> dropped = source.onBackpressureDrop();
```

Có thể nhận callback khi một phần tử bị bỏ:

```java
Flux<Integer> dropped = source.onBackpressureDrop(
        value -> metrics.incrementDropped(value));
```

`metrics.incrementDropped` là API minh họa của ứng dụng. Không log từng phần tử bị drop trong tải cao vì log có thể trở thành nguồn nghẽn mới; ưu tiên counter và sampling.

Dùng drop khi:

- Dữ liệu là telemetry có thể mất.
- Một số event trung gian không quan trọng.
- Consumer chỉ cần các mẫu dữ liệu tiếp theo.
- Hệ thống có quy tắc chấp nhận loss rõ ràng.

Không dùng drop cho event cần bảo đảm xử lý, chẳng hạn giao dịch, audit hoặc lệnh cập nhật trạng thái không thể tái tạo.

### 8.1. Test drop

Khi subscriber không request, phần tử được phát vào operator có thể bị drop. Test nên xác nhận cả callback lẫn phần tử được giữ lại sau khi demand xuất hiện.

```java
List<Integer> dropped = new ArrayList<>();
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(
                source.flux().onBackpressureDrop(dropped::add),
                0)
        .then(() -> source.next(1, 2))
        .then(() -> assertEquals(List.of(1, 2), dropped))
        .thenRequest(1)
        .then(() -> source.next(3))
        .expectNext(3)
        .thenCancel()
        .verify();
```

Khi source phát `1` và `2` trong lúc downstream không có demand, callback ghi nhận hai phần tử bị bỏ. Sau khi request một phần tử, `3` được phát và nhận.

## 9. `onBackpressureLatest`: chỉ giữ giá trị mới nhất

```java
Flux<Integer> latest = source.onBackpressureLatest();
```

Nếu downstream chậm, operator giữ giá trị gần nhất thay vì lưu toàn bộ chuỗi phần tử đang chờ.

Ví dụ:

```text
Producer:  1  2  3  4  5  6
Consumer:              nhận 6
```

Đây là chiến lược hữu ích cho:

- Nhiệt độ hiện tại.
- Trạng thái thiết bị.
- Giá trị progress.
- Snapshot dashboard.
- Vị trí hiện tại của một đối tượng.

Không phù hợp nếu từng event có ý nghĩa riêng và cần được xử lý đủ.

### 9.1. Test latest

```java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(
                source.flux().onBackpressureLatest(),
                0)
        .then(() -> source.next(1, 2, 3))
        .thenRequest(1)
        .expectNext(3)
        .thenCancel()
        .verify();
```

Downstream không có demand trong lúc producer phát ba giá trị. Khi demand xuất hiện, subscriber nhận giá trị cuối cùng.

### 9.2. Latest không đồng nghĩa debounce

`onBackpressureLatest()` giữ giá trị mới nhất khi downstream thiếu demand. Nó không chờ một khoảng yên lặng trước khi phát như `debounce(Duration)`.

- `latest`: chính sách khi downstream không có demand.
- `debounce`: chính sách thời gian, chỉ phát sau khi upstream không có item mới trong một khoảng.

Chọn theo nguyên nhân cần điều tiết.

## 10. `onBackpressureError`: báo quá tải ngay

```java
Flux<Integer> strict = source.onBackpressureError();
```

Khi source phát trong lúc downstream không có demand, operator báo lỗi overflow thay vì âm thầm giữ hoặc bỏ dữ liệu.

Dùng khi:

- Không cho phép mất dữ liệu.
- Không muốn queue tăng.
- Caller có thể xử lý lỗi quá tải rõ ràng.
- Hệ thống có cơ chế retry/backoff hoặc từ chối request ở tầng cao hơn.

Overflow error không tự động giải quyết vấn đề tải. Nếu caller retry ngay không backoff, nó có thể làm overload nặng hơn.

## 11. `limitRate`: điều tiết demand upstream

`limitRate(highTide)` chia demand downstream thành các batch nhỏ hơn khi yêu cầu upstream.

```java
Flux<Integer> limited = source.limitRate(32);
```

Có thể chỉ định cả high-tide và low-tide:

```java
Flux<Integer> limited = source.limitRate(64, 48);
```

- High-tide biểu thị kích thước batch demand.
- Low-tide điều khiển ngưỡng replenishment trước khi yêu cầu thêm.

`limitRate` giúp tránh một request cực lớn được truyền thẳng lên upstream và cho phép điều tiết theo batch.

### 11.1. `limitRate` không phải giới hạn số phần tử mỗi giây

Đừng hiểu:

```java
.limitRate(10)
```

là “chỉ phát 10 phần tử/giây”. Nó điều tiết request theo demand, không phải bộ temporal rate limiter.

Nếu cần giới hạn theo thời gian, hãy dùng một thiết kế rate limiting riêng hoặc operator thời gian phù hợp. `limitRate` cũng không thay thế bounded queue cho nguồn hot không thể pause.

### 11.2. Test demand shaping

```java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux().limitRate(2), 0)
        .then(() -> source.assertNoRequest())
        .thenRequest(1)
        .then(() -> source.assertWasRequested())
        .then(() -> source.next(7))
        .expectNext(7)
        .thenCancel()
        .verify();
```

Test xác nhận khi chưa có downstream demand, source chưa được yêu cầu; sau khi demand xuất hiện, upstream nhận request. Không phụ thuộc vào một con số prefetch nội bộ ngoài contract của ứng dụng.

## 12. `publishOn(prefetch)`: async boundary và queue

`publishOn` chuyển việc xử lý downstream sang scheduler và dùng prefetch để yêu cầu trước một lượng phần tử từ upstream.

```java
Flux<Result> results = source
        .publishOn(Schedulers.parallel(), 32)
        .map(this::cpuWork);
```

Prefetch kiểm soát số phần tử được yêu cầu trước tại async boundary. Một prefetch lớn có thể tăng throughput khi downstream có thể xử lý nhanh sau một khoảng ngắn, nhưng cũng làm tăng lượng phần tử có thể nằm trong queue.

### 12.1. `publishOn` khác `subscribeOn`

- `publishOn` ảnh hưởng nơi các operator phía sau nó xử lý tín hiệu.
- `subscribeOn` ảnh hưởng nơi subscription/request upstream bắt đầu.
- Cả hai không tự làm một blocking operation trở thành non-blocking.

Nếu dùng `publishOn(Schedulers.parallel())` cho một hàm blocking dài, có thể chiếm các thread của scheduler. Blocking I/O cần được cô lập bằng scheduler phù hợp, thường là `boundedElastic`, hoặc thay bằng reactive client.

### 12.2. Prefetch không phải dung lượng tổng của toàn ứng dụng

Một pipeline có thể có nhiều async boundaries, `flatMap` inner queues, buffering operators và source queues. Tổng lượng dữ liệu đang chờ có thể lớn hơn một prefetch đơn lẻ.

Đánh giá toàn pipeline, không chỉ một tham số `publishOn`.

## 13. Giới hạn số tác vụ đồng thời với `flatMap`

Một nguồn phát nhanh có thể tạo ra nhiều tác vụ I/O cùng lúc:

```java
Flux<Result> results = ids.flatMap(
        id -> remoteClient.fetch(id),
        8);
```

Tham số concurrency giới hạn số inner publishers đang được subscribe đồng thời.

Có thể điều chỉnh prefetch của mỗi inner publisher:

```java
Flux<Result> results = ids.flatMap(
        id -> remoteClient.fetch(id),
        8,
        16);
```

Điều này hữu ích khi downstream chậm vì không để hàng nghìn request con chạy đồng thời và giữ response trong bộ nhớ.

### 13.1. `concatMap` nếu thứ tự quan trọng

```java
Flux<Result> results = ids.concatMap(
        id -> remoteClient.fetch(id));
```

`concatMap` chỉ xử lý inner publisher theo thứ tự, đợi inner hiện tại hoàn tất trước khi chuyển sang item tiếp theo. Concurrency thấp hơn nhưng giữ thứ tự dễ dự đoán.

### 13.2. Chọn concurrency theo năng lực downstream

Không có một con số concurrency đúng cho mọi ứng dụng. Cần xem:

- Connection pool của HTTP/database client.
- Giới hạn request của dịch vụ ngoài.
- Thời gian phản hồi trung bình và p95/p99.
- Payload size.
- Số request đồng thời trên mỗi instance.
- Số instance chạy song song.
- Retry và timeout.

Nếu mỗi instance cho phép concurrency 100 và có 20 instance, downstream có thể nhận tới 2.000 tác vụ đồng thời. Hãy tính theo toàn hệ thống.

## 14. Nối nguồn callback bên ngoài bằng `Flux.create`

Một nguồn callback không hiểu Reactive Streams có thể được chuyển thành `Flux` bằng `Flux.create`.

Ví dụ minh họa adapter:

```java
Flux<Event> events = Flux.create(sink -> {
    Listener listener = event -> sink.next(event);

    externalSource.register(listener);

    sink.onDispose(() ->
            externalSource.unregister(listener));
}, FluxSink.OverflowStrategy.ERROR);
```

`Listener`, `externalSource.register` và `unregister` là API giả định của SDK bên ngoài. Đoạn code minh họa lifecycle adapter: đăng ký listener khi subscribe và gỡ listener khi cancel/terminate.

### 14.1. Các overflow strategies của `Flux.create`

| Strategy | Ý nghĩa |
|---|---|
| `BUFFER` | Buffer phần tử; có nguy cơ tăng không giới hạn |
| `DROP` | Bỏ phần tử khi không có demand |
| `LATEST` | Giữ phần tử mới nhất |
| `ERROR` | Phát lỗi khi không thể phát theo demand |
| `IGNORE` | Không điều tiết theo demand; dễ làm downstream quá tải |

Đừng chọn `BUFFER` chỉ vì nó làm test pass. Với producer vô hạn, queue không giới hạn có thể dẫn tới `OutOfMemoryError`.

### 14.2. Dùng `Flux.push` khi nguồn đơn luồng

`Flux.push` phù hợp cho callback phát tín hiệu từ một producer đơn luồng. `Flux.create` hỗ trợ producer đa luồng hơn và có cơ chế phối hợp signal. Chọn API theo thread model của nguồn.

Nếu callback có thể được gọi từ nhiều thread, hãy kiểm tra contract của adapter và bảo đảm việc đăng ký/gỡ listener đúng lifecycle. Không giữ listener hoặc resource sau cancellation.

## 15. `buffer(...)` khác `onBackpressureBuffer(...)`

Hai API có tên gần giống nhưng mục tiêu khác nhau.

| API | Mục đích |
|---|---|
| `buffer(n)` | Gom N phần tử thành một `List<T>` rồi phát list |
| `bufferTimeout(n, duration)` | Gom theo kích thước hoặc thời gian |
| `onBackpressureBuffer()` | Giữ từng phần tử khi downstream chưa có demand |
| `onBackpressureBuffer(maxSize)` | Giữ tối đa N phần tử chờ và báo overflow khi đầy |

Ví dụ gom batch:

```java
Flux<List<Integer>> batches = Flux.range(1, 10)
        .buffer(3);
```

Output:

```text
[1, 2, 3]
[4, 5, 6]
[7, 8, 9]
[10]
```

`buffer(3)` thay đổi hình dạng dữ liệu thành `Flux<List<Integer>>`. `onBackpressureBuffer(3)` vẫn phát từng phần tử `Integer`, chỉ xếp hàng khi downstream chậm.

Không dùng `buffer(n)` như cách thay thế chung cho backpressure.

## 16. WebFlux streaming: client chậm và server phát nhanh

Controller WebFlux có thể trả `Flux<T>` để stream dữ liệu. Với HTTP streaming, connector và network write demand có thể truyền ngược để nguồn reactive điều tiết.

Ví dụ NDJSON:

```java
@RestController
public class StreamController {

    @GetMapping(
            value = "/numbers",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Integer> numbers() {
        return Flux.range(1, 3);
    }
}
```

`Flux.range` là cold source và có thể tuân thủ demand. WebFlux không cần gom toàn bộ kết quả thành một `List` trước khi trả response.

### 16.1. Server-Sent Events với nguồn theo nhịp

```java
@GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<Long>> events() {
    return Flux.interval(Duration.ofMillis(250))
            .map(value -> ServerSentEvent.builder(value)
                    .id(Long.toString(value))
                    .event("tick")
                    .build())
            .onBackpressureLatest();
}
```

Đây là ví dụ stream trạng thái theo nhịp. Nếu client chậm, policy latest giữ giá trị gần nhất; những tick trung gian có thể mất. Chỉ dùng nếu semantics cho phép.

Nếu mỗi event là một giao dịch hoặc audit record, không chọn latest/drop. Hãy dùng cơ chế durable delivery, queue có giới hạn và acknowledgement phù hợp.

### 16.2. Disconnect phải dừng công việc

Khi client ngắt kết nối, subscription của response có thể bị cancel. Nguồn phải dọn resource trong `doFinally`, `usingWhen` hoặc lifecycle tương ứng.

Không chạy publisher vô hạn tách rời bằng `subscribe()` trong controller. Làm vậy có thể khiến nguồn tiếp tục chạy sau khi HTTP client đã rời đi.

## 17. Ước lượng bộ nhớ và giới hạn queue

Một cách ước lượng sơ bộ cho queue:

```text
Memory gần đúng
  ≈ số phần tử đang chờ
    × kích thước payload trung bình
    + overhead object/queue/reference
```

Ví dụ, 10.000 phần tử đang chờ với payload trung bình 16 KB đã tương đương khoảng 160 MB dữ liệu payload thô, chưa tính object headers, wrapper, buffer copies, queue nodes và các phần tử khác trong heap.

Với nhiều subscriber:

```text
Tổng queue memory
  ≈ tổng capacity của các subscriber
    × payload size trung bình
    + overhead
```

Đây chỉ là ước lượng; payload có thể được chia sẻ hoặc copy tùy operator và connector.

### 17.1. Capacity nên dựa trên burst budget

Nếu producer phát 2.000 event/s và consumer xử lý 1.500 event/s, queue tăng khoảng 500 event/s trong thời gian mất cân bằng. Buffer 5.000 phần tử chỉ hấp thụ được khoảng 10 giây ở mức chênh lệch đó.

Nếu burst kéo dài, cần giảm tốc producer, scale consumer, drop theo policy hoặc chuyển sang durable queue.

### 17.2. Giới hạn cả số phần tử lẫn kích thước

Một queue 100 phần tử có thể nhỏ nếu mỗi phần tử 100 byte, nhưng rất lớn nếu mỗi phần tử 20 MB. Cần giới hạn:

- Số phần tử.
- Payload bytes.
- Số stream/subscriber.
- Concurrency.
- Thời gian chờ trong queue.
- Số lần retry.

## 18. Dự án Java 17+ chạy được: kiểm thử slow consumer và fast producer

Dự án sử dụng:

- Java 17.
- Spring Boot 3.3.5.
- Spring WebFlux.
- Reactor Core do Spring Boot BOM quản lý.
- `reactor-test` và JUnit 5.
- `WebTestClient` để kiểm tra endpoint streaming.

Bộ test minh họa:

1. Subscriber yêu cầu từng phần tử.
2. TestPublisher chưa nhận request trước demand.
3. Bounded buffer giữ dữ liệu cho consumer chậm.
4. Bounded buffer phát overflow khi vượt capacity.
5. Drop policy ghi nhận phần tử bị bỏ.
6. Latest policy chỉ phát giá trị mới nhất.
7. `limitRate` truyền demand lên upstream.
8. WebFlux trả một stream NDJSON hữu hạn.

### 18.1. Cấu trúc dự án

```text
webflux-backpressure-tests/
├── pom.xml
└── src/
    ├── main/java/edu/demo/backpressure/
    │   ├── BackpressureApplication.java
    │   ├── BackpressurePolicy.java
    │   └── StreamController.java
    └── test/java/edu/demo/backpressure/
        ├── BackpressurePolicyTests.java
        └── StreamControllerTests.java
```

### 18.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webflux-backpressure-tests</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

### 18.3. `BackpressureApplication.java`

```java
package edu.demo.backpressure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BackpressureApplication {

    public static void main(String[] args) {
        SpringApplication.run(BackpressureApplication.class, args);
    }
}
```

### 18.4. `BackpressurePolicy.java`

```java
package edu.demo.backpressure;

import java.util.function.Consumer;

import org.springframework.stereotype.Component;

import reactor.core.publisher.Flux;

@Component
public class BackpressurePolicy {

    public Flux<Integer> buffer(
            Flux<Integer> source,
            int capacity) {

        if (capacity <= 0) {
            throw new IllegalArgumentException(
                    "capacity must be positive");
        }

        return source.onBackpressureBuffer(capacity);
    }

    public Flux<Integer> latest(Flux<Integer> source) {
        return source.onBackpressureLatest();
    }

    public Flux<Integer> drop(
            Flux<Integer> source,
            Consumer<? super Integer> dropped) {

        return source.onBackpressureDrop(dropped);
    }

    public Flux<Integer> limit(
            Flux<Integer> source,
            int highTide) {

        if (highTide <= 0) {
            throw new IllegalArgumentException(
                    "highTide must be positive");
        }

        return source.limitRate(highTide);
    }
}
```

Policy class giữ các chiến lược ở một chỗ để test riêng. Trong hệ thống thật, không nên để capacity tùy ý từ request client; cấu hình qua application properties hoặc giới hạn do service owner quản lý.

### 18.5. `StreamController.java`

```java
package edu.demo.backpressure;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class StreamController {

    @GetMapping(
            value = "/numbers",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Integer> numbers() {
        return Flux.range(1, 3);
    }
}
```

Endpoint trả `Flux` trực tiếp. `Flux.range` có thể điều tiết theo demand; controller không gọi `collectList()` hoặc `block()`.

### 18.6. `BackpressurePolicyTests.java`

```java
package edu.demo.backpressure;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BackpressurePolicyTests {

    private final BackpressurePolicy policy =
            new BackpressurePolicy();

    @Test
    void subscriberRequestsOneItemAtATime() {
        StepVerifier.create(Flux.range(1, 3), 0)
                .thenRequest(1)
                .expectNext(1)
                .thenRequest(1)
                .expectNext(2)
                .thenRequest(1)
                .expectNext(3)
                .verifyComplete();
    }

    @Test
    void compliantSourceWaitsForDemand() {
        TestPublisher<Integer> source = TestPublisher.create();

        StepVerifier.create(source.flux(), 0)
                .then(() -> source.assertNoRequest())
                .thenRequest(1)
                .then(() -> source.assertWasRequested())
                .then(() -> source.next(10))
                .expectNext(10)
                .thenCancel()
                .verify();
    }

    @Test
    void boundedBufferQueuesWhileConsumerHasNoDemand() {
        TestPublisher<Integer> source = TestPublisher.create();

        StepVerifier.create(
                        policy.buffer(source.flux(), 2),
                        0)
                .then(() -> source.next(1, 2))
                .thenRequest(2)
                .expectNext(1, 2)
                .thenCancel()
                .verify();
    }

    @Test
    void boundedBufferErrorsWhenCapacityIsExceeded() {
        TestPublisher<Integer> source = TestPublisher.create();

        StepVerifier.create(
                        policy.buffer(source.flux(), 2),
                        0)
                .then(() -> source.next(1, 2, 3))
                .expectError(IllegalStateException.class)
                .verify();
    }

    @Test
    void dropPolicyReportsDiscardedItems() {
        TestPublisher<Integer> source = TestPublisher.create();
        List<Integer> dropped = new ArrayList<>();

        StepVerifier.create(
                        policy.drop(source.flux(), dropped::add),
                        0)
                .then(() -> source.next(1, 2))
                .then(() -> assertEquals(
                        List.of(1, 2),
                        dropped))
                .thenRequest(1)
                .then(() -> source.next(3))
                .expectNext(3)
                .thenCancel()
                .verify();
    }

    @Test
    void latestPolicyKeepsOnlyNewestPendingItem() {
        TestPublisher<Integer> source = TestPublisher.create();

        StepVerifier.create(
                        policy.latest(source.flux()),
                        0)
                .then(() -> source.next(1, 2, 3))
                .thenRequest(1)
                .expectNext(3)
                .thenCancel()
                .verify();
    }

    @Test
    void limitRatePropagatesDemandToSource() {
        TestPublisher<Integer> source = TestPublisher.create();

        StepVerifier.create(
                        policy.limit(source.flux(), 2),
                        0)
                .then(() -> source.assertNoRequest())
                .thenRequest(1)
                .then(() -> source.assertWasRequested())
                .then(() -> source.next(7))
                .expectNext(7)
                .thenCancel()
                .verify();
    }
}
```

Test bounded buffer phát overflow khi có phần tử thứ ba trong lúc consumer chưa request và capacity bằng 2. Các test drop/latest cố tình không request ở thời điểm producer phát để xác nhận policy của operator.

### 18.7. `StreamControllerTests.java`

```java
package edu.demo.backpressure;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class StreamControllerTests {

    @Autowired
    WebTestClient client;

    @Test
    void numbersEndpointStreamsNdjson() {
        Flux<Integer> body = client.get()
                .uri("/numbers")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_NDJSON)
                .returnResult(Integer.class)
                .getResponseBody();

        assertNotNull(body);

        StepVerifier.create(body)
                .expectNext(1, 2, 3)
                .verifyComplete();
    }

    @Test
    void streamCanBeCancelledBySubscriber() {
        Flux<Integer> body = client.get()
                .uri("/numbers")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .returnResult(Integer.class)
                .getResponseBody();

        StepVerifier.create(body)
                .expectNext(1)
                .thenCancel()
                .verify(Duration.ofSeconds(3));
    }
}
```

`WebTestClient` kiểm tra HTTP endpoint và body publisher. Test này xác nhận streaming response được serialize thành NDJSON và subscriber có thể cancel. Các test demand chi tiết vẫn nằm ở `StepVerifier`/`TestPublisher`, nơi có thể điều khiển request một cách chính xác.

### 18.8. Chạy Maven

Trong thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi khi chạy thành công:

```text
Tests run: 9, Failures: 0, Errors: 0, Skipped: 0
```

Tổng cộng 7 unit tests cho policy/demand và 2 integration tests cho HTTP streaming. Đây là kết quả kỳ vọng; cần chạy Maven trong môi trường có JDK 17 và dependency access để xác nhận thực tế.

## 19. Kiểm thử quá tải và load test ngoài StepVerifier

`StepVerifier` kiểm tra semantics của publisher ở mức deterministic. Nó không thay thế load test nhiều client đồng thời.

Khi cần kiểm thử tải:

1. Tạo producer với tốc độ và payload size gần thực tế.
2. Tạo consumer có latency đại diện cho downstream thật.
3. Chạy nhiều subscriptions đồng thời.
4. Theo dõi queue capacity, drop count, overflow count và active tasks.
5. Tăng tốc producer theo từng mức để tìm điểm queue bắt đầu tăng liên tục.
6. Giảm tốc consumer để xác nhận backpressure/overflow policy hoạt động.
7. Ngắt client giữa stream để kiểm tra cancellation và cleanup.
8. Chạy đủ lâu để quan sát heap, GC và connection pool.

### 19.1. Những metric nên theo dõi

- Số phần tử nhận/phát mỗi giây.
- Số phần tử bị drop.
- Số overflow errors.
- Độ sâu queue và thời gian chờ trong queue.
- Số tác vụ `flatMap` đang chạy.
- Request latency p50/p95/p99.
- Heap usage và GC pause.
- Số subscription bị cancel.
- Active HTTP connections và pending network writes.
- Downstream error/retry rate.

Không cần log từng item. Dùng Micrometer counters, timers và gauges với tag cardinality được kiểm soát. Không dùng ID người dùng hoặc payload làm metric tag.

### 19.2. Đọc kết quả load test

| Quan sát | Khả năng nguyên nhân | Hướng điều tra |
|---|---|---|
| Queue tăng đều theo thời gian | Consumer không theo kịp producer | Scale/slow producer/durable queue |
| Heap tăng rồi GC liên tục | Queue hoặc payload đang được giữ quá lâu | Giới hạn capacity, payload size, lifecycle |
| Drop tăng nhưng latency ổn định | Drop policy đang hấp thụ quá tải | Xác nhận loss có chấp nhận được |
| Overflow tăng nhanh | Capacity quá nhỏ hoặc burst vượt budget | Tăng có kiểm soát, throttle hoặc từ chối |
| In-flight request tăng | `flatMap` concurrency quá cao hoặc downstream chậm | Giới hạn concurrency và timeout |
| Cancel không dừng upstream | Adapter tách subscription hoặc thiếu cleanup | Sửa lifecycle/`onDispose` |
| Latency tăng dù queue nhỏ | CPU, lock, network hoặc database bottleneck | Profile và trace downstream |

## 20. Những lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Dùng `onBackpressureBuffer()` không giới hạn cho nguồn vô hạn | Queue tăng tới khi cạn heap | Bounded buffer và overflow policy |
| Cho rằng buffer giải quyết mất cân bằng tốc độ lâu dài | Độ trễ tăng không giới hạn | Điều tiết producer hoặc scale consumer |
| Drop event giao dịch/audit | Mất dữ liệu nghiệp vụ | Durable queue và acknowledgement |
| Dùng latest cho event cần đủ thứ tự | Mất event trung gian | Buffer/durable log và sequence |
| Nghĩ `limitRate(10)` là 10 item/giây | Hiểu sai temporal rate | Dùng rate limiter theo thời gian |
| Nghĩ `publishOn` làm source tự chậm vô hạn | Queue prefetch vẫn có giới hạn | Đánh giá prefetch và nguồn hot |
| `flatMap` không giới hạn | Quá nhiều request con và memory | Đặt concurrency/prefetch |
| `concatMap` cho workload cần throughput cao | Xử lý tuần tự làm giảm throughput | Chọn concurrency hữu hạn nếu thứ tự cho phép |
| Dùng `Thread.sleep` để test slow consumer | Test chậm và không ổn định | `StepVerifier` initial demand |
| Chỉ test output cuối | Bỏ sót demand/overflow/drop semantics | Test request propagation và queue policy |
| Dùng TestPublisher non-compliant trong mọi test | Test không phản ánh publisher chuẩn | Chỉ dùng để mô phỏng nguồn lỗi |
| Không kiểm tra overflow | Queue đầy tạo lỗi không được xử lý | Test bounded capacity và error path |
| Không đếm dropped elements | Mất dữ liệu không được quan sát | Callback/counter và alert |
| `Flux.create` dùng BUFFER mặc định cho callback vô hạn | Queue có thể tăng vô hạn | Chọn DROP/LATEST/ERROR hoặc bounded adapter |
| Quên unregister callback khi cancel | Leak listener/resource | `sink.onDispose(...)` |
| Block event loop trong consumer | Mọi request cùng scheduler chậm | Reactive I/O hoặc boundedElastic phù hợp |
| Tạo queue cho mỗi subscriber không giới hạn | Tổng bộ nhớ vượt capacity dự tính | Tính tổng theo số subscriber |
| Chỉ giới hạn số phần tử, bỏ qua payload bytes | Một phần tử rất lớn vẫn gây OOM | Giới hạn payload size |
| Retry overflow ngay lập tức | Khuếch đại overload | Backoff, jitter, admission control |
| Không test disconnect | Upstream tiếp tục chạy sau client | Test cancel và resource cleanup |

## 21. Checklist thiết kế và kiểm thử

### Nguồn dữ liệu

- Source cold hay hot?
- Có tuân thủ Reactive Streams demand?
- Có thể pause/resume hoặc pull theo batch không?
- Producer có phát từ nhiều thread?
- Có giới hạn payload size và tốc độ không?

### Chính sách quá tải

- Có được phép mất dữ liệu?
- Buffer có giới hạn số phần tử và byte?
- Khi đầy sẽ error, drop-oldest, drop-latest hay chuyển durable queue?
- Có metric cho overflow/drop?
- Có timeout cho phần tử chờ quá lâu?
- Có admission control để từ chối tải mới?

### Consumer và concurrency

- Có xử lý tuần tự hay đồng thời?
- `flatMap` có concurrency/prefetch hữu hạn?
- `publishOn` có prefetch hợp lý?
- Có blocking I/O trên event loop không?
- Cancellation có truyền tới upstream?

### StepVerifier tests

- Có `initialRequest(0)` để kiểm soát demand?
- Có test `thenRequest(n)` từng bước?
- Có dùng TestPublisher để kiểm tra upstream request?
- Có test bounded buffer và overflow?
- Có test drop/latest semantics?
- Có test cancellation?
- Có timeout/virtual time khi pipeline phụ thuộc thời gian?

### Spring WebFlux integration

- Controller trả `Flux` trực tiếp khi cần streaming?
- Có tránh `collectList()` cho dữ liệu lớn?
- Có test content type và serialization?
- Client disconnect có cleanup upstream?
- Queue và payload size có được giới hạn theo deployment?

## 22. Bài tập tự kiểm tra

**Bài 1.** Backpressure trong Reactive Streams được truyền qua API nào?

**Đáp án:** Subscriber gọi `Subscription.request(n)` để yêu cầu thêm phần tử và `cancel()` để hủy subscription.

**Bài 2.** Vì sao `Flux.range` phù hợp để test demand từng phần tử?

**Đáp án:** Đây là cold publisher có thể phát theo demand, nên StepVerifier điều khiển request và quan sát từng phần tử.

**Bài 3.** `StepVerifier.create(publisher, 0)` có ý nghĩa gì?

**Đáp án:** Subscriber của StepVerifier bắt đầu với demand bằng 0; test phải gọi `thenRequest(n)` để yêu cầu phần tử.

**Bài 4.** Khi nào chọn `onBackpressureBuffer(maxSize)`?

**Đáp án:** Khi cần giữ một burst hữu hạn trong lúc consumer chậm và muốn giới hạn rõ số phần tử đang chờ. Khi capacity đầy, cần xử lý overflow error.

**Bài 5.** `onBackpressureDrop` và `onBackpressureLatest` khác nhau thế nào?

**Đáp án:** Drop bỏ các phần tử đến khi không có demand; latest giữ giá trị mới nhất để phát khi demand quay lại.

**Bài 6.** `limitRate(20)` có giới hạn 20 phần tử mỗi giây không?

**Đáp án:** Không. Nó điều tiết batch request upstream, không phải temporal rate limiter.

**Bài 7.** `publishOn(scheduler, 32)` tác động gì?

**Đáp án:** Tạo async boundary, chuyển xử lý downstream sang scheduler và dùng prefetch 32 để yêu cầu trước phần tử từ upstream.

**Bài 8.** Vì sao `flatMap(mapper, 8)` giúp kiểm soát tải?

**Đáp án:** Giới hạn số inner publishers đang chạy đồng thời ở mức 8, giảm số tác vụ downstream cùng lúc.

**Bài 9.** Vì sao queue vô hạn nguy hiểm?

**Đáp án:** Khi producer nhanh hơn consumer kéo dài, queue tăng không giới hạn, làm tăng latency/heap và có thể gây OutOfMemoryError.

**Bài 10.** Khi nào `onBackpressureLatest` phù hợp?

**Đáp án:** Khi chỉ cần trạng thái mới nhất như nhiệt độ hoặc progress, và các giá trị trung gian có thể bỏ.

**Bài 11.** `buffer(10)` có tương đương `onBackpressureBuffer(10)` không?

**Đáp án:** Không. `buffer(10)` gom 10 phần tử thành `List`; `onBackpressureBuffer(10)` giữ từng phần tử chờ demand với capacity giới hạn.

**Bài 12.** Khi client HTTP đóng kết nối, ứng dụng nên làm gì?

**Đáp án:** Cho cancellation truyền upstream và giải phóng listener/resource; không giữ một subscription tách rời tiếp tục phát dữ liệu.

## 23. Ghi nhớ

- Backpressure là giao thức demand qua `request(n)` và `cancel()`, không phải bộ đếm thời gian.
- Cold publisher có thể tuân thủ demand; hot/external source có thể cần buffer/drop/latest hoặc adapter.
- `StepVerifier.create(publisher, 0)` cho phép mô phỏng subscriber chưa sẵn sàng nhận dữ liệu.
- `TestPublisher` kiểm tra demand propagation và phát dữ liệu có kiểm soát.
- `onBackpressureBuffer(maxSize)` giữ burst hữu hạn; overflow phải được xử lý.
- `onBackpressureDrop` bỏ phần tử không có demand; `onBackpressureLatest` giữ giá trị mới nhất.
- `onBackpressureError` báo quá tải thay vì âm thầm giữ hoặc bỏ dữ liệu.
- `limitRate` điều tiết request batch, không giới hạn số phần tử mỗi giây.
- `publishOn(prefetch)` tạo queue/async boundary; prefetch ảnh hưởng lượng dữ liệu đang chờ.
- `flatMap(concurrency, prefetch)` giới hạn công việc con; `concatMap` giữ thứ tự bằng xử lý tuần tự.
- `Flux.create` phải có overflow strategy và cleanup cho external listener.
- `buffer(n)` gom batch, khác `onBackpressureBuffer(n)` giữ item chờ demand.
- Queue cần giới hạn theo cả số phần tử, kích thước payload, subscriber và thời gian chờ.
- WebFlux streaming nên trả `Flux` trực tiếp, kiểm thử cancellation và không block event loop.
- Load test phải quan sát queue, drop, overflow, latency, in-flight work, heap và GC.

**Quy tắc chọn nhanh:** nếu source có thể chậm lại, hãy truyền demand ngược upstream; nếu source không thể dừng, chọn buffer có giới hạn, drop, latest hoặc durable queue theo yêu cầu bảo toàn dữ liệu. Sau đó kiểm thử bằng subscriber demand bằng 0, tăng demand từng bước và mô phỏng overflow.

## 24. Tài liệu chính thức

- Reactive Streams Specification — **Publisher, Subscriber, Subscription and backpressure**: https://www.reactive-streams.org/
- Project Reactor 3.6 Reference — **Backpressure and request shaping**: https://projectreactor.io/docs/core/3.6.11/reference/
- Project Reactor 3.6 Reference — **Handling backpressure**: https://projectreactor.io/docs/core/3.6.11/reference/#_on_backpressure
- Reactor Core 3.6.11 Javadoc — **Flux backpressure operators**: https://projectreactor.io/docs/core/3.6.11/api/reactor/core/publisher/Flux.html
- Reactor Test 3.6.11 Javadoc — **StepVerifier**: https://projectreactor.io/docs/test/3.6.11/api/reactor/test/StepVerifier.html
- Reactor Test 3.6.11 Javadoc — **TestPublisher**: https://projectreactor.io/docs/test/3.6.11/api/reactor/test/publisher/TestPublisher.html
- Spring Framework 6.1 Reference — **Reactive WebFlux return values and streaming**: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/controller/ann-methods/return-types.html
- Spring Framework 6.1 Reference — **WebTestClient**: https://docs.spring.io/spring-framework/reference/6.1/testing/webtestclient.html
- Spring Boot 3.3 — **Dependency versions**: https://docs.spring.io/spring-boot/3.3/appendix/dependency-versions/coordinates.html