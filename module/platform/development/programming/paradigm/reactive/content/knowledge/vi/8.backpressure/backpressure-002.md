# Điều tiết nhu cầu từ bên tiêu thụ về nguồn phát

Trong một pipeline reactive, tốc độ tạo dữ liệu và tốc độ xử lý dữ liệu thường không giống nhau. Một nguồn có thể đọc hàng nghìn bản ghi mỗi giây, trong khi dịch vụ downstream chỉ xử lý được vài trăm bản ghi. Nếu nguồn tiếp tục phát theo tốc độ tối đa, phần tử sẽ tích tụ trong hàng đợi, làm tăng độ trễ và có thể khiến ứng dụng hết bộ nhớ.

Reactive Streams giải quyết bài toán này bằng **backpressure**: subscriber thông báo số phần tử mà mình sẵn sàng nhận thông qua `Subscription.request(n)`. Publisher phải tôn trọng nhu cầu đã được yêu cầu và không phát vượt quá số lượng đó. Nhu cầu có thể truyền ngược qua các operator để điều tiết nguồn upstream.

Bài học thuộc module `REACTIVE_PROGRAMMING`, tập trung vào các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Trong hệ sinh thái Java, người học vận dụng `Mono`, `Flux`, operator, scheduler, xử lý lỗi và kiểm thử pipeline. Hiểu cách demand di chuyển từ subscriber về publisher là nền tảng để thiết kế các pipeline này với mức tiêu thụ tài nguyên có thể kiểm soát.

## 1. Demand là gì?

`request(n)` biểu thị subscriber muốn nhận thêm tối đa `n` phần tử. Đây là lượng demand bổ sung, không phải tổng số phần tử kể từ lúc đăng ký.

Ví dụ, subscriber gọi `request(3)`, sau đó nhận hai phần tử và gọi tiếp `request(2)`. Tổng lượng demand được cấp là năm phần tử; một phần tử đã được tiêu thụ nên tại thời điểm gọi lần hai, publisher có thể phát thêm tối đa ba phần tử nữa.

```text
Subscriber                         Publisher
    |                                  |
    |------ request(3) --------------->|  Demand = 3
    |<----- onNext(A) -----------------|  Demand = 2
    |<----- onNext(B) -----------------|  Demand = 1
    |------ request(2) --------------->|  Demand = 3
    |<----- onNext(C) -----------------|  Demand = 2
    |<----- onNext(D) -----------------|  Demand = 1
    |<----- onNext(E) -----------------|  Demand = 0
```

Các quy tắc quan trọng:

- `request(n)` yêu cầu thêm `n` phần tử; `n` phải lớn hơn 0.
- Publisher không được gửi nhiều `onNext` hơn tổng demand hiện có.
- Có thể gọi `request` nhiều lần trong một subscription; các lần yêu cầu được cộng dồn, với xử lý tràn số theo quy tắc bão hòa của Reactive Streams.
- `request(Long.MAX_VALUE)` biểu thị nhu cầu không giới hạn.
- `cancel()` thông báo subscriber không còn muốn nhận dữ liệu. Publisher cần ngừng phát cho subscription đã hủy và giải phóng tài nguyên liên quan theo khả năng của nguồn.
- `onComplete` và `onError` là tín hiệu kết thúc, không tiêu thụ demand như `onNext`.

Nếu subscriber gọi `request(0)` hoặc một số âm, publisher phải báo lỗi theo hợp đồng Reactive Streams, thường bằng `onError(IllegalArgumentException)`. Một publisher đã kết thúc hoặc subscription đã hủy không tiếp tục phát dữ liệu chỉ vì có yêu cầu mới.

## 2. Demand truyền ngược qua pipeline như thế nào?

Trong pipeline có nhiều operator, subscriber cuối cùng không cần biết cách nguồn dữ liệu hoạt động. Subscriber chỉ yêu cầu số phần tử mà mình có thể xử lý. Mỗi operator nhận demand downstream, kết hợp với trạng thái nội bộ của nó rồi quyết định cần yêu cầu upstream bao nhiêu phần tử.

```text
Nguồn dữ liệu
    ^
    | request được điều chỉnh theo operator
    |
  Operator A
    ^
    | demand được truyền ngược
    |
  Operator B
    ^
    | request(n)
    |
 Subscriber

Tín hiệu dữ liệu onNext đi theo chiều ngược lại: từ nguồn đến subscriber.
```

Ví dụ với `map`, một phần tử upstream thường tạo ra một phần tử downstream, nên nhu cầu có thể được chuyển tiếp tương ứng. Với `filter`, publisher có thể phải yêu cầu thêm phần tử upstream để bù cho những phần tử bị loại bỏ, vì không phải phần tử nào cũng đến được downstream. Với `flatMap`, một phần tử nguồn có thể mở một publisher con; operator cần phối hợp concurrency, prefetch và demand của các publisher con.

Vì vậy, demand không nhất thiết được chuyển tiếp theo tỷ lệ một-một qua mọi operator. Mỗi operator phải giữ hợp đồng ở ranh giới của nó, đồng thời quản lý bộ đệm và công việc đang diễn ra.

### Demand được cấp theo từng subscription

Mỗi subscription có bộ đếm demand riêng. Hai subscriber đăng ký cùng một cold `Flux` có thể yêu cầu số lượng khác nhau và kích hoạt hai lần thực thi nguồn độc lập. Khi nhiều subscriber chia sẻ một nguồn upstream, operator chia sẻ phải phối hợp demand của từng subscriber theo chính sách của nó; subscriber chậm có thể ảnh hưởng đến tốc độ upstream hoặc lượng dữ liệu được đệm.

`Mono` tối đa phát một phần tử, nên demand dương đầu tiên đã đủ để cho phép phát phần tử đó nếu nguồn có dữ liệu. Với `Flux`, demand có thể được cấp thành nhiều đợt trong suốt vòng đời subscription.

## 3. Điều khiển demand trực tiếp với `BaseSubscriber`

Các overload `subscribe` đơn giản của Reactor thường yêu cầu dữ liệu không giới hạn. Khi cần kiểm soát thời điểm yêu cầu phần tử tiếp theo, có thể dùng `BaseSubscriber`.

Ví dụ sau yêu cầu từng phần tử một và chỉ yêu cầu phần tử tiếp theo sau khi xử lý xong phần tử hiện tại:

```java
class OneByOneSubscriber extends BaseSubscriber<Integer> {

    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(Integer value) {
        process(value);
        request(1);
    }

    private void process(Integer value) {
        System.out.println("Processing " + value);
    }
}

Flux.range(1, 5)
    .doOnRequest(n -> System.out.println("Upstream received request: " + n))
    .subscribeWith(new OneByOneSubscriber());
```

`hookOnSubscribe` gửi yêu cầu đầu tiên. Sau mỗi lần `hookOnNext`, subscriber xử lý phần tử rồi mới yêu cầu thêm một phần tử. Cách này tạo nhịp xử lý tuần tự và giúp nguồn chỉ cần cung cấp dữ liệu theo nhu cầu.

Nếu xử lý là bất đồng bộ, không nên gọi `request(1)` ngay sau khi chỉ khởi chạy tác vụ nền. Hãy yêu cầu phần tử tiếp theo khi tác vụ xử lý hiện tại hoàn tất; nếu không, nhiều tác vụ có thể cùng chạy và lượng công việc đang chờ sẽ tăng lên. Khi triển khai thực tế, cũng cần định nghĩa cách xử lý lỗi, timeout và cancel cho tác vụ đang chạy.

`BaseSubscriber` phù hợp khi cần một chính sách demand tùy chỉnh. Với pipeline thông thường, nên ưu tiên các operator declarative để Reactor điều phối demand và vòng đời subscription.

## 4. Giới hạn lượng request upstream bằng `limitRate`

Một subscriber có thể yêu cầu nhiều phần tử cùng lúc, nhưng nguồn upstream không nhất thiết phải nhận một yêu cầu rất lớn trong một lần. `limitRate` chia demand thành các đợt nhỏ hơn trước khi chuyển lên upstream.

```java
Flux<Integer> numbers = Flux.range(1, 1_000)
    .doOnRequest(n -> System.out.println("Source request: " + n))
    .limitRate(64);

numbers.subscribe(value -> consume(value));
```

Ở ví dụ này, `limitRate(64)` điều tiết cách operator yêu cầu dữ liệu từ nguồn theo các đợt có kích thước giới hạn. Nó giúp kiểm soát lượng dữ liệu được lấy trước và giảm khả năng một yêu cầu upstream duy nhất kéo về một lượng phần tử quá lớn.

Các tham số của `limitRate` điều khiển kích thước đợt yêu cầu và ngưỡng bổ sung demand. Khi cần tinh chỉnh thời điểm yêu cầu thêm dữ liệu, có thể dùng overload `limitRate(highTide, lowTide)`. Hãy chọn các giá trị dựa trên kích thước phần tử, khả năng xử lý downstream và độ trễ chấp nhận được.

`limitRate` không thay thế backpressure ở subscriber. Nó điều chỉnh cách demand được chuyển qua một ranh giới operator. Nếu subscriber không yêu cầu dữ liệu, pipeline vẫn không có demand downstream để phát `onNext`.

## 5. Backpressure với các nguồn phát dữ liệu

Không phải nguồn nào cũng có thể giảm tốc độ phát theo yêu cầu. Một `Flux.range` có thể dừng phát cho đến khi có demand. Một callback từ thư viện bên ngoài hoặc bộ cảm biến có thể tiếp tục gọi callback bất kể subscriber đã sẵn sàng hay chưa.

Với nguồn tuân thủ Reactive Streams, demand có thể truyền đến tận nguồn để điều tiết việc tạo dữ liệu. Với nguồn push bên ngoài không hỗ trợ demand, adapter phải quyết định cách tiếp nhận khi downstream chậm: lưu đệm, loại bỏ, giữ giá trị mới nhất hoặc báo lỗi.

### `Flux.generate`: tạo dữ liệu theo yêu cầu

`Flux.generate` phù hợp với nguồn đồng bộ tạo từng phần tử theo yêu cầu. Mỗi lần gọi generator chỉ phát tối đa một phần tử:

```java
Flux<Long> sequence = Flux.generate(
    () -> 0L,
    (state, sink) -> {
        sink.next(state);
        return state + 1;
    }
);
```

Nguồn này tạo phần tử khi có demand và giữ trạng thái giữa các lần gọi generator. Nó phù hợp với quá trình sinh dữ liệu tuần tự, nơi việc tạo phần tử tiếp theo có thể chờ cho đến khi downstream yêu cầu.

### `Flux.create`: chọn chính sách khi nguồn push nhanh hơn

`Flux.create` dùng để tích hợp API callback hoặc nguồn bất đồng bộ. Vì callback bên ngoài có thể phát nhanh hơn downstream xử lý, cần chọn `FluxSink.OverflowStrategy` phù hợp:

```java
Flux<Event> events = Flux.create(sink -> {
    externalApi.register(event -> sink.next(event));
    sink.onDispose(() -> externalApi.unregister());
}, FluxSink.OverflowStrategy.ERROR);
```

Các chiến lược thường gặp:

| Chiến lược | Hành vi khi downstream không theo kịp | Khi cân nhắc |
|---|---|---|
| `BUFFER` | Giữ các phần tử chờ demand. | Có thể chấp nhận độ trễ và có giới hạn bộ nhớ phù hợp. |
| `DROP` | Bỏ phần tử mới khi không thể chuyển xuống. | Sự kiện mới không bắt buộc phải được xử lý đầy đủ. |
| `LATEST` | Giữ giá trị mới nhất, thay thế các giá trị cũ đang chờ. | Dữ liệu trạng thái có thể thay thế như nhiệt độ hoặc vị trí. |
| `ERROR` | Báo lỗi khi không thể tiếp nhận phần tử vì thiếu demand. | Muốn biểu diễn tình trạng quá tải rõ ràng. |
| `IGNORE` | Bỏ qua demand của downstream. | Chỉ dùng khi hệ thống tự kiểm soát tải ở nơi khác và chấp nhận rủi ro quá tải. |

`BUFFER` mặc định có thể tích lũy dữ liệu rất lớn nếu nguồn liên tục nhanh hơn subscriber. Với nguồn push, buffer hữu hạn hoặc chính sách drop/latest/error giúp giới hạn hậu quả khi quá tải. Tuy nhiên, drop và latest làm mất dữ liệu theo chủ đích; chỉ sử dụng khi ngữ nghĩa nghiệp vụ cho phép.

## 6. Phân biệt truyền backpressure với xử lý overflow

Hai nhóm operator thường được dùng để kiểm soát tốc độ nhưng có mục đích khác nhau.

| Operator | Vai trò | Tác động chính |
|---|---|---|
| `limitRate(n)` | Điều tiết demand truyền lên upstream theo các đợt. | Giữ cơ chế backpressure và giới hạn lượng request upstream. |
| `onBackpressureBuffer()` | Đệm phần tử khi downstream thiếu demand. | Yêu cầu upstream không giới hạn rồi giữ phần tử chờ ở ranh giới operator; cần giới hạn bộ đệm nếu tải có thể tăng. |
| `onBackpressureDrop()` | Bỏ phần tử khi downstream chưa có demand. | Nguồn upstream có thể tiếp tục phát; phần tử không chuyển được sẽ bị loại bỏ. |
| `onBackpressureLatest()` | Giữ phần tử mới nhất trong lúc downstream chậm. | Các giá trị cũ đang chờ bị thay thế bởi giá trị mới. |
| `onBackpressureError()` | Báo lỗi khi phần tử đến lúc downstream chưa có demand. | Biến tình trạng thiếu khả năng tiếp nhận thành lỗi. |

Các operator `onBackpressure...` này áp dụng chính sách tại ranh giới downstream và thường yêu cầu upstream không giới hạn để tự xử lý phần tử đến nhanh. Vì vậy, chúng không truyền ngược tín hiệu giảm tốc độ đến nguồn theo cách `limitRate` thực hiện. Chúng là chính sách overflow, không phải bằng chứng rằng toàn bộ pipeline đã được điều tiết end-to-end.

Ví dụ dùng buffer có giới hạn:

```java
Flux<Event> bounded = eventSource
    .onBackpressureBuffer(
        256,
        dropped -> log.warn("Buffer overflow, event rejected: {}", dropped)
    );
```

Khi bộ đệm đạt giới hạn, pipeline xử lý tình trạng tràn theo overload được chọn và có thể phát lỗi. Ứng dụng cần bắt lỗi ở tầng phù hợp, ghi nhận số lần tràn và quyết định có retry, lưu bền vững hay từ chối tải mới.

Ví dụ bỏ phần tử có quan sát:

```java
Flux<Position> positions = positionSource
    .onBackpressureDrop(position ->
        metrics.increment("position.events.dropped")
    );
```

Đối với vị trí hiện tại, bỏ một số mẫu cũ có thể chấp nhận được. Đối với giao dịch tài chính hoặc cập nhật trạng thái đơn hàng, bỏ sự kiện có thể phá vỡ tính đúng đắn nghiệp vụ.

## 7. Scheduler và prefetch cũng ảnh hưởng đến lượng dữ liệu chờ

`publishOn` chuyển xử lý downstream sang scheduler khác và dùng hàng đợi nội bộ để chuyển phần tử giữa các luồng thực thi. Operator này có tham số `prefetch` để kiểm soát số phần tử được yêu cầu trước và giữ trong hàng đợi.

```java
Flux<Event> pipeline = eventSource
    .publishOn(Schedulers.parallel(), 32)
    .map(this::transform)
    .publishOn(Schedulers.boundedElastic(), 16)
    .map(this::persist);
```

Hai ranh giới `publishOn` có hàng đợi và mức prefetch riêng. Khi chọn prefetch quá lớn, pipeline có thể giữ nhiều phần tử trong bộ nhớ và tăng độ trễ. Khi chọn quá nhỏ, scheduler có thể phải điều phối nhiều lượt request hơn và giảm thông lượng trong một số tình huống.

Với `flatMap`, có thể giới hạn số publisher con chạy đồng thời và số phần tử được prefetch từ mỗi publisher con:

```java
Flux<Result> results = requests.flatMap(
    request -> callRemoteService(request),
    8,  // concurrency: tối đa số publisher con đang hoạt động
    4   // prefetch: lượng phần tử lấy trước từ mỗi publisher con
);
```

`concurrency` giới hạn số tác vụ con đang hoạt động; `prefetch` điều khiển lượng phần tử được lấy trước từ mỗi publisher con. Cả hai tham số ảnh hưởng đến lượng công việc và dữ liệu đang chờ trong pipeline. Nếu cần giữ thứ tự đầu ra, cân nhắc `flatMapSequential`; nếu cần xử lý publisher con lần lượt, dùng `concatMap`.

Chọn scheduler không tự tạo ra backpressure. Một executor có hàng đợi không giới hạn vẫn có thể tích lũy tác vụ khi tốc độ gửi lớn hơn tốc độ xử lý. Cần kết hợp scheduler với demand, giới hạn concurrency và chính sách hàng đợi phù hợp.

## 8. Thiết kế chính sách backpressure theo ý nghĩa dữ liệu

Không có một chính sách overflow đúng cho mọi nguồn. Hãy phân loại dữ liệu trước khi chọn operator:

| Loại dữ liệu | Yêu cầu thường gặp | Hướng thiết kế |
|---|---|---|
| Giao dịch, thanh toán, kiểm toán | Không được âm thầm mất sự kiện. | Backpressure end-to-end, buffer hữu hạn có giám sát, lưu bền vững hoặc từ chối tải rõ ràng. |
| Cập nhật trạng thái mới nhất | Giá trị mới có thể thay thế giá trị cũ. | `LATEST` hoặc cơ chế gộp trạng thái. |
| Telemetry tần suất cao | Có thể chấp nhận mất mẫu trong điều kiện tải cao. | Drop có đo lường, sampling hoặc batch. |
| Gọi dịch vụ bên ngoài | Cần giới hạn số yêu cầu đang chạy. | Giới hạn concurrency, timeout, retry có giới hạn và demand phù hợp. |
| Xử lý tệp lớn | Không muốn nạp toàn bộ tệp vào bộ nhớ. | Đọc theo chunk, yêu cầu theo nhu cầu và xử lý từng phần. |

Khi chọn buffer, hãy ước lượng kích thước phần tử và tốc độ chênh lệch giữa producer với consumer. Ví dụ, nếu trung bình có 500 phần tử mỗi giây đến nhanh hơn khả năng xử lý trong 10 giây, hàng đợi có thể tích lũy khoảng 5.000 phần tử. Đây mới là ước lượng số lượng; dung lượng bộ nhớ thực tế còn phụ thuộc kích thước object, tham chiếu và overhead của hàng đợi.

Một pipeline an toàn nên có giới hạn ở nhiều lớp: giới hạn request upstream, giới hạn concurrency, prefetch hữu hạn, buffer có giới hạn và chính sách khi quá tải. Chỉ giới hạn ở một điểm có thể để dữ liệu tích tụ tại một hàng đợi khác.

## 9. Kiểm thử demand với `StepVerifier`

`StepVerifier` cho phép bắt đầu subscription với demand bằng 0, sau đó cấp thêm demand theo từng bước. Điều này giúp xác minh publisher chỉ phát phần tử khi có yêu cầu.

```java
Flux<Integer> source = Flux.range(1, 3);

StepVerifier.create(source, 0)
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .verifyComplete();
```

Ở đây subscriber ban đầu chưa yêu cầu phần tử nào. Sau `thenRequest(1)`, verifier nhận một phần tử. Sau đó, `thenRequest(2)` cấp thêm demand cho hai phần tử còn lại.

Có thể quan sát lượng request upstream bằng `doOnRequest`:

```java
Flux<Integer> observed = Flux.range(1, 10)
    .doOnRequest(n -> System.out.println("Source demand: " + n))
    .limitRate(4);

StepVerifier.create(observed, 0)
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(3)
    .expectNext(3, 4, 5)
    .thenCancel()
    .verify();
```

Bài kiểm thử này xác minh hành vi phía subscriber và cho phép quan sát các đợt request do `limitRate` chuyển đến nguồn. Không nên khẳng định chính xác một lịch request nội bộ nếu bài kiểm thử không kiểm tra trực tiếp các giá trị đó; mục tiêu là xác minh giới hạn và hành vi demand mà ứng dụng phụ thuộc vào.

Với adapter callback tự viết, nên bổ sung kiểm thử cho các trường hợp: downstream không request, request từng phần, cancel khi đang có phần tử chờ, buffer đầy, nguồn phát lỗi và nguồn kết thúc. Cần xác minh số phần tử được phát, số phần tử bị bỏ hoặc bị từ chối và tài nguyên đã được giải phóng.

## 10. Tình huống thực tế: xử lý luồng đơn hàng có tải biến động

Một dịch vụ nhận sự kiện đơn hàng từ broker. Mỗi sự kiện cần được xác thực, gọi dịch vụ tồn kho và ghi kết quả vào cơ sở dữ liệu. Tải có thể tăng đột biến vào giờ cao điểm, trong khi dịch vụ tồn kho chỉ chịu được một số lượng yêu cầu đồng thời nhất định.

Một pipeline có thể giới hạn số lời gọi dịch vụ con:

```java
Flux<InventoryResult> results = orderEvents
    .limitRate(100)
    .flatMap(
        order -> inventoryService.check(order),
        12,
        4
    )
    .publishOn(Schedulers.boundedElastic(), 32)
    .flatMap(result -> orderRepository.save(result), 8, 2);
```

Trong thiết kế này:

1. `limitRate(100)` điều tiết lượng request chuyển đến nguồn sự kiện theo từng đợt.
2. `flatMap(..., 12, 4)` giới hạn số lời gọi kiểm tra tồn kho đồng thời và lượng prefetch từ các publisher con.
3. `publishOn(..., 32)` tạo ranh giới scheduler với prefetch được chỉ định.
4. `flatMap(..., 8, 2)` giới hạn số thao tác lưu đồng thời và lượng prefetch tương ứng.

Các con số chỉ là ví dụ khởi đầu. Cần đo độ trễ, thông lượng, kích thước phần tử, số kết nối cơ sở dữ liệu và khả năng của dịch vụ tồn kho để chọn giá trị thực tế. Nếu broker adapter không hỗ trợ demand, `limitRate` chỉ kiểm soát request tại ranh giới Reactive Streams; adapter vẫn cần buffer hữu hạn hoặc cơ chế pause/resume broker để tránh tích lũy dữ liệu bên ngoài pipeline.

Khi dịch vụ tồn kho quá tải, hệ thống nên có timeout và xử lý lỗi rõ ràng. Retry cần giới hạn số lần, có backoff và tránh tạo thêm tải lớn hơn khi dịch vụ đang suy giảm. Backpressure điều tiết lượng công việc được tiếp nhận; nó không thay thế circuit breaker, timeout hay chính sách phục hồi lỗi.

## 11. Checklist khi thiết kế demand

- Xác định subscriber có thể xử lý bao nhiêu phần tử trong một khoảng thời gian.
- Không dùng `request(Long.MAX_VALUE)` nếu cần giới hạn tải và chưa đánh giá tác động.
- Để demand truyền ngược qua pipeline khi nguồn có khả năng tuân thủ Reactive Streams.
- Dùng `limitRate` khi cần chia request upstream thành các đợt nhỏ.
- Giới hạn concurrency và prefetch ở các operator tạo nhiều công việc con.
- Chọn buffer có giới hạn hoặc chính sách drop/latest/error cho nguồn push không thể giảm tốc độ.
- Không nhầm `onBackpressure...` với cơ chế điều tiết end-to-end; các operator này xử lý overflow tại ranh giới của chúng.
- Tính đến hàng đợi của scheduler và operator, không chỉ hàng đợi ở nguồn.
- Xác định hành vi khi cancel, timeout, lỗi và buffer đầy.
- Dùng `StepVerifier` để kiểm tra publisher không phát vượt demand và phản ứng đúng với cancel.

Khi demand được thiết kế xuyên suốt từ subscriber về nguồn, pipeline có thể điều tiết tốc độ theo khả năng tiêu thụ và giữ lượng công việc đang chờ trong giới hạn. Với nguồn không thể giảm tốc độ, một chính sách overflow rõ ràng giúp ứng dụng xử lý quá tải có chủ đích thay vì để bộ nhớ và độ trễ tăng không kiểm soát.
