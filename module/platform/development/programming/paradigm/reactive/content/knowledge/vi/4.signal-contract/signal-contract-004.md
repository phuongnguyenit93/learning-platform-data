# Tuần tự hóa tín hiệu và tính an toàn khi có nhiều luồng thực thi

Trong một hệ thống reactive, một `Publisher` có thể nhận dữ liệu từ nhiều nguồn: callback mạng, bộ hẹn giờ, hàng đợi sự kiện hoặc các tác vụ chạy trên những luồng khác nhau. Các nguồn này có thể phát dữ liệu gần như đồng thời. Tuy nhiên, mỗi `Subscriber` vẫn cần nhận một chuỗi tín hiệu có thể xử lý an toàn: callback không chồng lấn, tín hiệu kết thúc không xuất hiện sai vị trí và dữ liệu không bị đảo thứ tự một cách khó kiểm soát.

Bài học thuộc module `REACTIVE_PROGRAMMING`, nơi người học thực hành tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; đồng thời sử dụng `Mono`, `Flux`, các toán tử kết hợp, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trong chương **Hợp đồng tín hiệu**, tuần tự hóa là điều kiện để các thành phần đó phối hợp đúng khi có nhiều luồng thực thi.

## 1. Bài toán khi nhiều luồng cùng phát tín hiệu

Hãy hình dung một dịch vụ theo dõi đơn hàng. Một luồng nhận cập nhật trạng thái từ hệ thống kho, một luồng khác nhận cập nhật từ đơn vị vận chuyển. Cả hai cùng đưa sự kiện vào một `Publisher` đang phục vụ một `Subscriber`.

Nếu hai luồng gọi trực tiếp `onNext` trên cùng một `Subscriber` mà không có cơ chế điều phối, hai lần gọi có thể diễn ra đồng thời. Khi đó, callback `onNext` của subscriber có thể bị chạy chồng lấn. Một callback đang cập nhật trạng thái đơn hàng thì callback khác đã bắt đầu ghi đè trạng thái hoặc cập nhật cùng một cấu trúc dữ liệu.

Ví dụ dưới đây mô tả một cách phát tín hiệu không an toàn:

```java
void publish(Event event) {
    // Mỗi sự kiện được giao cho một tác vụ độc lập.
    // Hai tác vụ có thể gọi onNext cùng lúc.
    executor.execute(() -> subscriber.onNext(event));
}
```

Nếu `executor` có nhiều worker, hai tác vụ có thể chạy song song. Việc đưa lời gọi vào executor chỉ thay đổi nơi thực thi; nó không tự bảo đảm các callback của cùng một subscriber được tuần tự hóa. Ngay cả khi phương thức `publish` được gọi tuần tự, các tác vụ đã gửi vào executor vẫn có thể chạy đồng thời.

Reactive Streams đặt ra một hợp đồng để giải quyết vấn đề này: tín hiệu gửi đến một subscriber phải được tuần tự hóa.

## 2. Tuần tự hóa có nghĩa gì trong Reactive Streams?

Với một subscription, chuỗi tín hiệu hợp lệ có dạng:

```text
onSubscribe(subscription)
        |
        v
   onNext(item)       (có thể không có item nào)
        |
        v
   onNext(item)
        |
        v
   ...
        |
        v
   onComplete()  hoặc  onError(error)
```

Các điểm cần giữ đúng:

- `onSubscribe` được gửi trước các tín hiệu dữ liệu và tín hiệu kết thúc.
- Có thể có không hoặc nhiều lần gọi `onNext`.
- Khi kết thúc, publisher gửi tối đa một tín hiệu kết thúc: `onComplete` hoặc `onError`.
- Sau tín hiệu kết thúc, publisher không gửi thêm `onNext` hay một tín hiệu kết thúc khác.
- Những lời gọi tín hiệu đến cùng một subscriber phải diễn ra tuần tự: không có hai callback tín hiệu chồng lấn, và giữa các lời gọi có quan hệ *happens-before*.

Đây là yêu cầu về từng subscription. Hai subscriber khác nhau vẫn có thể nhận tín hiệu đồng thời trên các luồng khác nhau. Hợp đồng cũng không yêu cầu toàn bộ ứng dụng chỉ dùng một luồng.

### Tuần tự không đồng nghĩa với cùng một luồng

Một publisher có thể phát tín hiệu thứ nhất trên luồng A và tín hiệu tiếp theo trên luồng B, miễn là việc chuyển giao bảo đảm quan hệ thứ tự và hai callback không chạy chồng lấn. Vì vậy, tuần tự hóa không đồng nghĩa với *thread affinity* — ràng buộc mọi callback phải chạy trên cùng một thread.

Quan hệ *happens-before* giúp các thao tác của callback trước được sắp thứ tự trước callback sau trong cùng chuỗi tín hiệu. Đây là một phần quan trọng của hợp đồng tín hiệu và khả năng quan sát dữ liệu giữa các lần gọi. Tuy vậy, publisher vẫn phải chuyển giao dữ liệu đúng cách; việc tuần tự hóa không sửa được mọi data race có sẵn trong những đối tượng dùng chung bên ngoài pipeline.

### Tuần tự hóa không tự quyết định thứ tự nghiệp vụ

Nếu hai producer phát `A` và `B` đồng thời, subscriber sẽ nhận chúng theo một thứ tự tuần tự nào đó, chẳng hạn `A` rồi `B` hoặc `B` rồi `A`. Hợp đồng tín hiệu yêu cầu chuỗi đầu ra không chồng lấn; nó không tự biết sự kiện nào xảy ra trước trong nghiệp vụ.

Nếu thứ tự nghiệp vụ quan trọng, hệ thống cần định nghĩa điểm quyết định thứ tự. Có thể gán số thứ tự tại nơi tiếp nhận sự kiện, dùng sequence number từ nguồn, hoặc đưa sự kiện vào một bước sắp xếp theo quy tắc thời gian đã xác định. Không nên dựa vào tên thread hay thời điểm log xuất hiện để suy ra thứ tự nghiệp vụ.

## 3. Phân biệt tuần tự hóa, thread safety và thread affinity

Ba khái niệm này liên quan nhưng không thay thế cho nhau.

| Khái niệm | Câu hỏi cần trả lời | Ý nghĩa trong pipeline |
|---|---|---|
| Tuần tự hóa tín hiệu | Hai callback của cùng subscriber có chạy chồng lấn không? | Mỗi tín hiệu được chuyển đến theo một chuỗi tuần tự. |
| Thread safety | Nhiều luồng có thể truy cập trạng thái dùng chung mà không gây race condition không? | Cần đồng bộ, cấu trúc dữ liệu an toàn luồng hoặc cô lập trạng thái khi có nhiều bên cùng truy cập. |
| Thread affinity | Callback có bắt buộc chạy trên một thread cụ thể không? | Được quyết định bởi scheduler và cách tổ chức thực thi. |

Ví dụ, một `Flux` có thể bảo đảm callback của một subscriber không chạy chồng lấn, nhưng hai subscription cùng gọi một service có trạng thái mutable. Hai subscription đó có thể chạy đồng thời và cùng sửa trạng thái service. Trạng thái dùng chung vẫn cần được bảo vệ bằng thiết kế thread-safe.

Tương tự, `request(n)` và `cancel()` trên `Subscription` phải có khả năng được gọi an toàn từ nhiều luồng theo hợp đồng Reactive Streams. Điều đó không có nghĩa publisher được phép gọi đồng thời nhiều `onNext` đến cùng subscriber. An toàn của các thao tác điều khiển subscription và tuần tự hóa tín hiệu đi xuống là hai yêu cầu khác nhau.

## 4. Các lỗi thường gặp khi không tuần tự hóa

### Callback chạy chồng lấn

Hai producer cùng gọi `onNext`. Nếu subscriber hoặc operator đang cập nhật bộ đếm, bộ đệm hay trạng thái mutable mà không dự kiến truy cập đồng thời, kết quả có thể sai hoặc phát sinh lỗi khó tái hiện.

### Tín hiệu kết thúc đến sai vị trí

Giả sử một luồng phát `onNext`, trong khi luồng khác phát `onComplete`. Nếu publisher không điều phối các tín hiệu, subscriber có thể nhận `onComplete` trước khi callback `onNext` đang chạy kết thúc, hoặc nhận thêm dữ liệu sau khi đã kết thúc. Một publisher đúng phải đưa tín hiệu kết thúc vào cùng cơ chế tuần tự hóa với tín hiệu dữ liệu.

### Thứ tự thay đổi theo lịch chạy

Executor nhiều luồng có thể xử lý tác vụ theo thứ tự khác với thứ tự producer gửi chúng. Nếu nghiệp vụ cần thứ tự xác định, chỉ tuần tự hóa callback là chưa đủ; phải quy định thứ tự tại điểm hợp nhất dữ liệu.

### Hàng đợi tăng không giới hạn

Một cách sửa đơn giản là xếp mọi sự kiện vào hàng đợi rồi phát tuần tự. Nhưng nếu producer nhanh hơn subscriber trong thời gian dài, hàng đợi có thể tăng liên tục và tiêu thụ hết bộ nhớ. Cơ chế tuần tự hóa cần được thiết kế cùng với backpressure hoặc chính sách xử lý tràn.

## 5. Các cách tạo chuỗi tín hiệu an toàn

### Ưu tiên dùng operator và nguồn phát có hợp đồng rõ ràng

Trong ứng dụng Reactor, `Mono` và `Flux` cùng tuân theo hợp đồng tín hiệu của Reactive Streams. Các operator của Reactor tổ chức tín hiệu đi xuống theo hợp đồng này, kể cả khi một số thao tác upstream hoặc các publisher con được thực thi đồng thời.

Khi tích hợp một API callback bên ngoài, hãy chọn API tạo nguồn phù hợp với số luồng phát:

- `Flux.push` dành cho nguồn phát từ một luồng producer.
- `Flux.create` hỗ trợ nhiều luồng producer cùng phát dữ liệu vào sink.

Ví dụ dưới đây mô phỏng hai producer chạy đồng thời. `Flux.create` nhận các lời gọi `sink.next` từ nhiều luồng và điều phối tín hiệu để subscriber nhận chúng theo hợp đồng. Ví dụ dùng `BUFFER` để giữ các phần tử trong lúc downstream chưa yêu cầu; với tải thực tế cần đánh giá giới hạn bộ nhớ và chọn chính sách phù hợp.

```java
Flux<String> events = Flux.create(sink -> {
    ExecutorService producers = Executors.newFixedThreadPool(2);
    sink.onDispose(producers::shutdown);

    CompletableFuture<Void> warehouse = CompletableFuture.runAsync(() -> {
        for (int i = 1; i <= 3 && !sink.isCancelled(); i++) {
            sink.next("warehouse-" + i);
        }
    }, producers);

    CompletableFuture<Void> delivery = CompletableFuture.runAsync(() -> {
        for (int i = 1; i <= 3 && !sink.isCancelled(); i++) {
            sink.next("delivery-" + i);
        }
    }, producers);

    CompletableFuture.allOf(warehouse, delivery)
        .whenComplete((ignored, failure) -> {
            if (failure != null) {
                sink.error(failure);
            } else {
                sink.complete();
            }
        });
}, FluxSink.OverflowStrategy.BUFFER);

events.subscribe(value ->
    System.out.println(Thread.currentThread().getName() + " -> " + value)
);
```

Các sự kiện `warehouse-*` và `delivery-*` có thể xen kẽ theo lịch chạy của hai producer. Subscriber vẫn nhận callback tuần tự. Nếu cần mọi callback downstream chạy trên một worker được chọn, có thể đặt ranh giới scheduler bằng `publishOn`:

```java
events
    .publishOn(Schedulers.single())
    .doOnNext(value -> System.out.println(
        Thread.currentThread().getName() + " -> " + value
    ))
    .subscribe();
```

`publishOn` chuyển việc xử lý downstream qua scheduler đã chọn và tạo ranh giới hàng đợi giữa upstream với downstream. Nó giúp kiểm soát nơi thực thi của phần pipeline phía sau operator. Scheduler là công cụ điều phối thực thi; bản thân việc chọn scheduler không thay thế việc thiết kế nguồn phát đúng hợp đồng.

### Dùng `Sinks` khi cần cầu nối phát sự kiện chủ động

Reactor cung cấp `Sinks` cho trường hợp mã ứng dụng cần chủ động phát dữ liệu vào một `Flux` hoặc `Mono`. Sink phát hiện các lần emit cạnh tranh. Với `tryEmitNext`, kết quả `FAIL_NON_SERIALIZED` cho biết một lần emit khác đang cạnh tranh và thao tác hiện tại chưa được chấp nhận.

```java
Sinks.Many<String> sink = Sinks.many()
    .multicast()
    .onBackpressureBuffer();

Sinks.EmitResult result = sink.tryEmitNext("order-updated");

if (result == Sinks.EmitResult.FAIL_NON_SERIALIZED) {
    // Đưa sự kiện qua hàng đợi/đầu mối phát tuần tự rồi thử phát lại.
}
```

Ứng dụng phải xử lý kết quả emit phù hợp với từng trường hợp. Không nên bỏ qua lỗi cạnh tranh vì khi đó sự kiện có thể không được phát. Nếu nhiều producer thường xuyên emit đồng thời, hãy đưa chúng qua một hàng đợi chung với một consumer phát tuần tự, hoặc chọn một cơ chế retry có giới hạn và có chủ đích. Vòng lặp bận vô hạn có thể làm tăng tải CPU mà không giải quyết được tình trạng tranh chấp kéo dài.

### Dùng hàng đợi và một vòng drain khi tự tích hợp nguồn

Khi phải tự viết adapter cho một API nhiều producer, một cấu trúc phổ biến là **nhiều producer, một consumer** (*MPSC — multi-producer, single-consumer*):

1. Mỗi producer đưa một sự kiện vào hàng đợi an toàn luồng.
2. Một bộ đếm nguyên tử `work-in-progress` chọn đúng một luồng làm nhiệm vụ drain tại một thời điểm.
3. Luồng drain lấy lần lượt các sự kiện và phát xuống subscriber, đồng thời tôn trọng lượng demand còn lại.
4. Tín hiệu kết thúc cũng được điều phối qua cùng hàng đợi; chỉ phát nó sau các phần tử đã được chấp nhận trước đó.
5. Khi subscription bị hủy, vòng drain dừng phát và giải phóng các phần tử còn chờ theo chính sách của nguồn.

Mã khung sau chỉ minh họa điểm tranh quyền của vòng drain, không phải một `Publisher` hoàn chỉnh:

```java
void enqueue(Signal<T> signal) {
    queue.offer(signal);

    // Chỉ luồng chuyển work-in-progress từ 0 sang 1 bắt đầu drain.
    if (workInProgress.getAndIncrement() == 0) {
        drain();
    }
}
```

Phần `drain()` thực tế phải xử lý demand, hủy subscription, lỗi, tín hiệu kết thúc, tranh chấp khi producer thêm phần tử trong lúc drain và việc giải phóng hàng đợi. Chỉ thêm `ConcurrentLinkedQueue` là chưa đủ: nếu nhiều luồng cùng lấy phần tử và gọi `onNext`, callback vẫn có thể chồng lấn. Mục tiêu của vòng drain là duy trì một consumer duy nhất tại ranh giới phát tín hiệu.

## 6. Tuần tự hóa khi dùng operator có xử lý đồng thời

Tuần tự hóa tín hiệu không cấm xử lý song song. Reactor có thể chạy nhiều công việc upstream hoặc nhiều publisher con đồng thời, sau đó hợp nhất kết quả thành chuỗi tín hiệu tuần tự ở downstream.

| Cách tổ chức | Đặc điểm về thực thi | Lưu ý về thứ tự đầu ra |
|---|---|---|
| `concatMap` | Xử lý publisher con lần lượt. | Giữ thứ tự theo phần tử nguồn. |
| `flatMap` | Có thể subscribe và xử lý nhiều publisher con đồng thời. | Kết quả có thể xen kẽ theo thời điểm hoàn tất; callback downstream vẫn được tuần tự hóa. |
| `flatMapSequential` | Cho phép xử lý publisher con đồng thời. | Giữ thứ tự kết quả theo thứ tự phần tử nguồn, có thể phải đệm kết quả đến sớm. |
| `parallel().runOn(...).sequential()` | Chia công việc thành nhiều rail để xử lý song song rồi hợp nhất. | Các rail chạy độc lập; sau khi hợp nhất, subscriber downstream vẫn nhận tín hiệu theo hợp đồng tuần tự. |

Ví dụ, ba yêu cầu được gửi đi đồng thời có thể hoàn tất theo thứ tự khác với thứ tự khởi chạy:

```java
Flux<Integer> results = Flux.just(1, 2, 3)
    .flatMap(id -> fetchAsync(id), 3);
```

`flatMap` cho phép kết quả đến theo thứ tự hoàn tất. Subscriber không nhận hai callback `onNext` chồng lấn, nhưng không thể giả định kết quả luôn là `1, 2, 3`. Nếu cần giữ thứ tự nguồn trong khi vẫn chạy công việc đồng thời, cân nhắc `flatMapSequential`. Nếu cần xử lý publisher con hoàn toàn lần lượt, dùng `concatMap`.

`subscribeOn` và `publishOn` cũng có vai trò khác nhau. `subscribeOn` tác động đến nơi thực hiện quá trình subscribe và phần nguồn upstream tương ứng; `publishOn` tạo ranh giới scheduler cho các operator downstream sau nó. Cả hai đều không phải khóa bảo vệ trạng thái mutable dùng chung trong ứng dụng.

## 7. Kết hợp tuần tự hóa với backpressure

Tuần tự hóa quy định cách tín hiệu được chuyển đến subscriber. Backpressure quy định subscriber báo cho publisher biết mình sẵn sàng nhận bao nhiêu phần tử thông qua `request(n)`. Hai cơ chế giải quyết hai vấn đề khác nhau và cần được thiết kế cùng nhau.

Một nguồn nhiều producer có thể phát nhanh hơn tốc độ subscriber xử lý. Nếu adapter chỉ xếp mọi phần tử vào bộ đệm không giới hạn, callback vẫn tuần tự nhưng bộ nhớ có thể tăng đến mức gây lỗi. Với `Flux.create`, có thể chọn `FluxSink.OverflowStrategy` theo ngữ nghĩa nghiệp vụ:

| Chiến lược | Hành vi khi downstream chưa có demand | Trường hợp cân nhắc |
|---|---|---|
| `BUFFER` | Giữ phần tử trong bộ đệm cho đến khi có demand. | Số phần tử có giới hạn hoặc tốc độ nguồn được kiểm soát; cần chú ý nguy cơ tăng bộ nhớ. |
| `DROP` | Bỏ phần tử mới khi không thể chuyển xuống. | Dữ liệu mới không bắt buộc phải được xử lý đầy đủ. |
| `LATEST` | Giữ giá trị mới nhất, loại bỏ các giá trị đang chờ cũ hơn. | Trạng thái ảnh chụp như nhiệt độ hoặc vị trí hiện tại, nơi giá trị mới thay thế giá trị cũ. |
| `ERROR` | Báo lỗi khi không thể phát do thiếu demand. | Muốn biểu diễn quá tải thành lỗi rõ ràng để tầng trên xử lý. |

`BUFFER` không tự tạo ra giới hạn bộ nhớ. `DROP` và `LATEST` làm mất một số sự kiện theo chủ đích; chỉ dùng chúng khi nghiệp vụ cho phép. Với sự kiện tài chính, đơn hàng hoặc kiểm toán, việc bỏ dữ liệu thường không phù hợp; cần cơ chế lưu trữ, giới hạn tải hoặc điều tiết producer phù hợp. `IGNORE` bỏ qua demand và có thể khiến downstream bị quá tải, vì vậy không nên chọn nếu chưa hiểu rõ hậu quả.

Backpressure cũng không phải khóa đồng bộ. Một subscriber yêu cầu một phần tử tại một thời điểm không tự làm cho mọi trạng thái dùng chung trong ứng dụng trở nên thread-safe. Hãy giữ riêng ba câu hỏi: callback có tuần tự không, producer có bị điều tiết theo demand không, và dữ liệu dùng chung có được bảo vệ không.

## 8. Kiểm thử tính tuần tự của callback

`StepVerifier` giúp kiểm tra số phần tử, thứ tự mong đợi và tín hiệu kết thúc. Để kiểm tra callback không chạy chồng lấn, có thể thêm bộ đếm nguyên tử vào một operator quan sát. Dùng nguồn `events` từ ví dụ `Flux.create` ở trên:

```java
AtomicInteger callbacksInProgress = new AtomicInteger();
AtomicBoolean overlapDetected = new AtomicBoolean();

StepVerifier.create(events.doOnNext(value -> {
        if (callbacksInProgress.incrementAndGet() != 1) {
            overlapDetected.set(true);
        }

        try {
            Thread.yield();
        } finally {
            callbacksInProgress.decrementAndGet();
        }
    }))
    .expectNextCount(6)
    .verifyComplete();

assertFalse(overlapDetected.get());
```

Ví dụ giả định đã có các import Reactor, `StepVerifier`, `AtomicInteger`, `AtomicBoolean` và assertion của thư viện kiểm thử. `Thread.yield()` chỉ làm tăng cơ hội các luồng cạnh tranh bộc lộ lỗi; nó không bảo đảm một bài kiểm thử sẽ tái hiện mọi race condition. Với adapter tự viết, nên chạy kiểm thử cạnh tranh nhiều lần, kiểm tra cả trường hợp cancel và lỗi, và xác minh rằng tín hiệu kết thúc chỉ xuất hiện một lần sau các phần tử đã được chấp nhận.

Một bài kiểm thử đầy đủ nên xác minh ít nhất các thuộc tính sau:

- Không có hai callback tín hiệu của cùng subscriber chạy đồng thời.
- Không có `onNext` sau `onComplete` hoặc `onError`.
- Chỉ có một tín hiệu kết thúc.
- Khi có demand giới hạn, publisher không phát vượt quá số phần tử được yêu cầu.
- Khi cancel, nguồn dừng phát theo hợp đồng và giải phóng tài nguyên.
- Khi producer đồng thời gửi dữ liệu, số lượng và chính sách thứ tự của sự kiện đúng với thiết kế.

## 9. Tình huống áp dụng: hợp nhất cập nhật đơn hàng

Một dịch vụ nhận cập nhật từ kho và đơn vị giao hàng. Mỗi nguồn chạy trên executor riêng. Subscriber tổng hợp trạng thái đơn hàng và gửi thông báo cho khách.

Thiết kế an toàn cần quyết định rõ các điểm sau:

1. **Điểm hợp nhất:** hai nguồn đưa sự kiện vào một nguồn reactive có hỗ trợ producer đồng thời, chẳng hạn `Flux.create`, hoặc một hàng đợi MPSC với một vòng drain.
2. **Quy tắc thứ tự:** nếu sự kiện có sequence number từ hệ thống nguồn, dùng số đó để phát hiện sự kiện đến muộn hoặc bị thiếu. Nếu không có, định nghĩa thứ tự tại điểm tiếp nhận và không giả định thứ tự giữa hai producer.
3. **Chính sách quá tải:** cập nhật trạng thái nào có thể gộp thành trạng thái mới nhất, cập nhật nào bắt buộc phải lưu đủ, và bộ đệm tối đa là bao nhiêu.
4. **Xử lý downstream:** nếu gửi thông báo cho mỗi đơn hàng phải giữ thứ tự, chọn toán tử phù hợp như `concatMap`; nếu xử lý độc lập và chấp nhận kết quả về không theo thứ tự, có thể dùng `flatMap` với mức concurrency giới hạn.
5. **Trạng thái dùng chung:** nếu nhiều đơn hàng được xử lý đồng thời, trạng thái của từng đơn hàng phải được cô lập hoặc cập nhật bằng cơ chế thread-safe.

Thiết kế này tận dụng xử lý đồng thời ở nơi có ích, đồng thời duy trì hợp đồng tín hiệu tại từng subscriber. Nó cũng làm rõ thứ tự nghiệp vụ và giới hạn tài nguyên thay vì để các yếu tố đó phụ thuộc vào lịch chạy của thread.

## 10. Checklist khi thiết kế nguồn phát nhiều luồng

- Xác định một subscription có thể nhận dữ liệu từ bao nhiêu producer.
- Bảo đảm mọi tín hiệu đến cùng subscriber được tuần tự hóa, bao gồm cả tín hiệu kết thúc.
- Không xem việc dùng executor hoặc scheduler là bằng chứng rằng callback đã an toàn.
- Chọn `Flux.push` cho một producer và `Flux.create` cho nhiều producer khi dùng các API tạo nguồn tương ứng của Reactor.
- Với `Sinks`, kiểm tra `EmitResult` và xử lý trường hợp emit cạnh tranh.
- Nếu tự viết adapter, dùng một cơ chế single-consumer drain có xử lý demand, cancel, lỗi và terminal signal đầy đủ.
- Định nghĩa thứ tự nghiệp vụ riêng khi nhiều nguồn phát đồng thời.
- Chọn chính sách buffer/overflow phù hợp với ý nghĩa dữ liệu và giới hạn bộ nhớ.
- Bảo vệ trạng thái mutable được chia sẻ giữa nhiều subscription hoặc nhiều luồng.
- Kiểm thử callback chồng lấn, terminal signal, backpressure và cancellation.

Khi những quy tắc này được giữ đúng, pipeline `Mono`/`Flux` có thể tận dụng scheduler và xử lý song song mà vẫn cung cấp một chuỗi tín hiệu có thể dự đoán cho từng subscriber. Đó là nền tảng để các operator, cơ chế backpressure và phần xử lý lỗi phối hợp đúng trong một hệ thống reactive.
