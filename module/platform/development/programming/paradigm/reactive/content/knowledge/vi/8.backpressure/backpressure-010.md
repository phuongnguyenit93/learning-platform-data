# Nhu cầu không giới hạn và nguy cơ tăng bộ nhớ ngoài dự kiến

Backpressure cho phép Subscriber báo cho Publisher biết nó sẵn sàng nhận bao nhiêu phần tử. Khi Subscriber yêu cầu `Long.MAX_VALUE`, nhu cầu được xem là **không giới hạn**: Publisher tuân thủ hợp đồng có thể phát liên tục mà không cần chờ Subscriber bổ sung demand. Cách tiêu thụ này tiện lợi, nhưng có thể làm mất một lớp kiểm soát tải nếu pipeline có bộ đệm hoặc ranh giới bất đồng bộ. Khi nguồn phát nhanh hơn tốc độ xử lý, phần tử chờ có thể tích tụ và làm bộ nhớ tăng ngoài dự kiến.

Chủ đề này thuộc chương **Áp lực ngược** của REACTIVE_PROGRAMMING. Module học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; sau đó thực hành Mono, Flux, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Để kiểm soát bộ nhớ, cần phân biệt nhu cầu không giới hạn với bộ đệm không giới hạn, nhận ra nơi dữ liệu được xếp hàng và chọn chính sách phù hợp với ý nghĩa nghiệp vụ.

## `request(Long.MAX_VALUE)` có nghĩa gì?

Trong Reactive Streams, `Subscription.request(n)` yêu cầu Publisher phát tối đa `n` phần tử bổ sung. `Long.MAX_VALUE` thường được dùng như giá trị đại diện cho nhu cầu không giới hạn. Publisher vẫn phải tuân thủ thứ tự tín hiệu, không phát `null`, và kết thúc đúng bằng `onComplete` hoặc `onError`; chỉ có giới hạn demand được nới tới mức không thực tế có thể cạn.

```text
Subscriber                         Publisher
    |                                  |
    |------ request(Long.MAX_VALUE) -->|
    |<------------- onNext(A) ---------|
    |<------------- onNext(B) ---------|
    |<------------- onNext(C) ---------|
    |                 ...              |
```

Subscriber đã cho phép phát bao nhiêu phần tử tùy nguồn cung cấp. Điều đó không có nghĩa Publisher phải tạo mọi phần tử ngay lập tức, cũng không có nghĩa Subscriber đã cấp phát bộ nhớ để giữ toàn bộ dữ liệu. Đây chỉ là thông tin về nhu cầu trong hợp đồng.

Reactor có các overload `subscribe(...)` tiện dụng dành cho callback, ví dụ `subscribe(value -> handle(value))`. Các overload này yêu cầu không giới hạn từ upstream. Vì thế, một pipeline dùng callback đơn giản có thể không còn tạo áp lực ngược từ Subscriber cuối cùng về nguồn. Khi cần kiểm soát số phần tử được yêu cầu, có thể triển khai `BaseSubscriber` hoặc dùng API kiểm thử để phát demand tường minh.

## Nhu cầu không giới hạn không tự động làm đầy bộ nhớ

Điểm này rất quan trọng: `request(Long.MAX_VALUE)` tự nó không tạo một hàng đợi và không cấp phát bộ nhớ cho mọi phần tử tương lai. Nếu nguồn phát đồng bộ và Subscriber xử lý mỗi `onNext` ngay trước khi Publisher phát phần tử tiếp theo, dữ liệu có thể đi qua lần lượt với lượng bộ nhớ bổ sung nhỏ.

Nguy cơ tăng bộ nhớ xuất hiện khi **sản xuất và tiêu thụ bị tách rời**. Ví dụ, nguồn phát trên một thread trong khi downstream xử lý trên thread khác; một toán tử lưu dữ liệu để chờ demand; hoặc một adapter nhận callback từ hệ thống push-only rồi đưa phần tử vào hàng đợi. Nếu nơi sản xuất tiếp tục nhanh hơn nơi tiêu thụ, hàng đợi giữ các phần tử chưa xử lý sẽ lớn dần.

```text
Nguồn phát nhanh                 Consumer xử lý chậm
     |                                  |
     |---- event 1 ----> [hàng đợi] ----|---- xử lý 1
     |---- event 2 ----> [ event 2 ]    |---- xử lý 2
     |---- event 3 ----> [ event 3 ]    |
     |---- event 4 ----> [ event 4 ]    |
     |---- event 5 ----> [ event 5 ]    |
                hàng đợi tiếp tục tăng nếu chênh lệch kéo dài
```

Một ranh giới bất đồng bộ thường cần một lượng đệm để điều phối các thread. Lượng đệm hữu hạn có thể hấp thụ dao động ngắn; hàng đợi không giới hạn có thể tiếp tục tăng nếu tốc độ đầu vào luôn cao hơn tốc độ xử lý. Nhu cầu không giới hạn ở Subscriber cuối làm Publisher được phép phát nhanh tới mức downstream cho phép, nên cần xem xét các ranh giới trung gian và chính sách buffering.

## Ước lượng tốc độ tích tụ

Gọi:

- \(\lambda\) là tốc độ phần tử đi vào hàng đợi, tính bằng phần tử/giây.
- \(\mu\) là tốc độ consumer xử lý, cùng đơn vị.
- \(Q_0\) là số phần tử đang chờ tại thời điểm bắt đầu quan sát.

Nếu tốc độ đầu vào ổn định lớn hơn tốc độ xử lý, lượng tồn đọng tăng xấp xỉ:

\[
Q(t) \approx Q_0 + (\lambda - \mu)t \quad \text{khi } \lambda > \mu
\]

Dung lượng bộ nhớ cần giữ không chỉ là kích thước payload. Mỗi phần tử còn có thể mang object header, tham chiếu, node hoặc cấu trúc của hàng đợi, cùng các đối tượng được payload tham chiếu tới. Có thể ước lượng sơ bộ:

\[
M(t) \approx Q(t) \times S_{\text{retained}}
\]

Trong đó \(S_{\text{retained}}\) là lượng bộ nhớ trung bình thực sự được giữ lại cho mỗi phần tử, bao gồm chi phí đối tượng và dữ liệu còn được tham chiếu.

Ví dụ, nếu nguồn đưa vào 80.000 sự kiện/giây và consumer xử lý 50.000 sự kiện/giây, backlog tăng khoảng 30.000 sự kiện mỗi giây. Nếu mỗi sự kiện giữ trung bình khoảng 1,2 KB trong heap, lượng bộ nhớ được giữ có thể tăng xấp xỉ 36 MB mỗi giây, chưa tính biến động và chi phí bổ sung. Đây là phép ước lượng để nhận diện xu hướng; số đo thực tế cần lấy từ heap profiler và metric của ứng dụng.

Nếu tốc độ đầu vào nhỏ hơn hoặc bằng tốc độ xử lý trong dài hạn, backlog không tăng tuyến tính theo công thức trên. Tuy nhiên, burst ngắn vẫn có thể tạo đỉnh bộ nhớ, vì vậy cần xem cả tốc độ trung bình lẫn tốc độ cực đại và thời gian phục hồi sau burst.

## Những vị trí có thể giữ phần tử trong pipeline

Khi điều tra bộ nhớ, đừng chỉ nhìn `subscribe()`. Hãy lần theo toàn bộ pipeline để tìm nơi dữ liệu được lưu lại:

| Vị trí | Vì sao có thể giữ dữ liệu | Điều cần kiểm tra |
|---|---|---|
| `onBackpressureBuffer()` | Đệm phần tử khi upstream tiếp tục phát trong lúc downstream chưa có demand tương ứng; biến thể mặc định không đặt giới hạn kích thước | Dùng buffer không giới hạn hay giới hạn? Khi đầy thì làm gì? |
| `publishOn(...)` | Chuyển xử lý sang scheduler khác và dùng hàng đợi để tách upstream với downstream | Prefetch, số luồng xử lý và tốc độ drain |
| `flatMap(...)` | Có nhiều inner Publisher hoạt động đồng thời; mỗi inner có thể có phần tử đang chờ | `concurrency`, `prefetch` và thời gian hoàn tất của inner Publisher |
| `buffer(...)` | Gom nhiều phần tử thành collection trước khi phát | Kích thước batch, chu kỳ phát và batch còn đang mở |
| Adapter callback/event bus | Nguồn push có thể tiếp tục gọi callback khi consumer đang bận | Hàng đợi có giới hạn, overflow policy và khả năng điều tiết nguồn |
| Cache/replay | Giữ dữ liệu để phát lại cho Subscriber đến muộn | Giới hạn số phần tử hoặc thời gian lưu giữ |

Không phải mọi operator đều có hàng đợi không giới hạn. Ví dụ `publishOn` và `flatMap` có prefetch/concurrency mặc định hữu hạn, nhưng nhiều ranh giới cùng tồn tại vẫn có thể giữ một lượng dữ liệu đáng kể. Nguy cơ phụ thuộc cách các giới hạn kết hợp với kích thước phần tử, số subscription và thời gian consumer bị chậm.

## Ví dụ nguy cơ: buffer không giới hạn trước ranh giới bất đồng bộ

`onBackpressureBuffer()` là lựa chọn cần cân nhắc kỹ. Nó yêu cầu upstream phát theo cách không bị chặn bởi demand downstream và lưu phần tử trong buffer khi downstream chưa thể nhận tiếp. Nếu nguồn phát liên tục, consumer chậm và buffer không có giới hạn, backlog có thể tăng tới khi heap không còn đủ chỗ.

```java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

Flux.interval(Duration.ofMillis(1))
    .onBackpressureBuffer()
    .publishOn(Schedulers.single())
    .doOnNext(tick -> slowBusinessOperation(tick))
    .subscribe();
```

Nguồn phát tick mỗi mili giây. `onBackpressureBuffer()` giữ các tick khi downstream chưa tiêu thụ kịp; `publishOn` chuyển bước xử lý sang scheduler khác. Nếu `slowBusinessOperation` mất nhiều thời gian hơn khoảng phát trung bình, backlog có thể tăng liên tục. `subscribe()` callback ở cuối yêu cầu không giới hạn, nên không tạo một giới hạn demand hữu ích cho toàn pipeline.

Ví dụ này mô tả một thiết kế có rủi ro, không phải cách xử lý phù hợp cho mọi nguồn. Trong ứng dụng thực tế, hãy xác định rõ có cần giữ mọi tick hay không. Nếu mỗi tick chỉ đại diện cho trạng thái mới nhất, có thể chỉ giữ giá trị mới nhất. Nếu mọi sự kiện đều quan trọng, cần giới hạn buffer và có cách phản ứng khi vượt giới hạn.

## Kiểm soát demand ở Subscriber

Khi consumer cần xử lý từng phần tử trước khi nhận thêm, có thể dùng `BaseSubscriber` để yêu cầu theo từng bước:

```java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

Flux.range(1, 5).subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(Integer value) {
        processSynchronously(value);
        request(1);
    }
});
```

Subscriber bắt đầu với demand bằng một. Sau khi xử lý xong phần tử hiện tại, nó mới yêu cầu thêm một phần tử. Cách này tạo nhịp tiêu thụ tuần tự và tránh yêu cầu trước một lượng lớn dữ liệu. Trong ứng dụng thật, nếu `processSynchronously` chỉ đưa công việc vào một executor không giới hạn rồi trả về ngay, việc request từng phần tử vẫn có thể làm hàng đợi của executor tăng. Demand phải phản ánh khả năng hoàn tất công việc, không chỉ khả năng đưa việc sang nơi khác.

Nếu xử lý theo lô, có thể yêu cầu một lượng hữu hạn phù hợp rồi yêu cầu thêm khi phần lớn lô đã được xử lý. Cần tránh gọi `request(n)` quá sớm nếu các phần tử vẫn đang chờ trong hàng đợi downstream.

## Giới hạn lượng yêu cầu upstream bằng `limitRate`

Reactor có `limitRate(highTide)` để chia một demand lớn từ downstream thành các request nhỏ hơn tới upstream. Ví dụ:

```java
Flux<Integer> values = remoteSource()
    .limitRate(128)
    .publishOn(Schedulers.parallel())
    .map(this::transform);
```

`limitRate(128)` điều chỉnh cách yêu cầu upstream theo các đợt thay vì chuyển nguyên demand không giới hạn lên nguồn. Nó hữu ích khi upstream tuân thủ Reactive Streams và có thể điều tiết theo request. `limitRate` không phải bộ giới hạn tốc độ theo thời gian, không bảo đảm mọi hàng đợi trong ứng dụng đều có kích thước tối đa 128, và không thể ép một nguồn push-only bên ngoài dừng phát nếu adapter của nguồn không hỗ trợ demand.

`limitRate` cũng không thay thế việc giới hạn concurrency của `flatMap`, dung lượng buffer hay số tác vụ đang chờ trong executor. Hãy kết hợp các giới hạn ở đúng ranh giới: demand upstream, số tác vụ đồng thời, prefetch và bộ đệm.

## Chọn chính sách khi consumer không theo kịp

Không phải ứng dụng nào cũng cần giữ mọi phần tử. Chính sách phù hợp phụ thuộc ý nghĩa dữ liệu:

| Chính sách | Hành vi | Phù hợp khi |
|---|---|---|
| Buffer có giới hạn | Giữ phần tử chờ đến một giới hạn; khi vượt giới hạn có thể báo lỗi hoặc áp dụng overflow strategy đã chọn | Mọi sự kiện trong giới hạn đều quan trọng và ứng dụng có thể xử lý khi buffer đầy |
| Drop | Bỏ phần tử đến khi downstream chưa sẵn sàng | Dữ liệu là mẫu quan sát có thể mất mà không ảnh hưởng nghiệp vụ |
| Latest | Giữ giá trị mới nhất, thay thế giá trị đang chờ cũ hơn | Chỉ trạng thái mới nhất có ý nghĩa, như vị trí hiện tại hoặc giá trị cảm biến gần nhất |
| Error | Kết thúc bằng lỗi khi không thể tiếp nhận theo demand | Mất dữ liệu là không chấp nhận được và hệ thống cần báo lỗi để xử lý |
| Điều tiết nguồn | Giảm tốc độ hoặc tạm dừng việc phát tại nguồn | Nguồn hỗ trợ pull, demand hoặc cơ chế điều khiển tốc độ |

Trong Reactor, có thể thể hiện chính sách ở operator backpressure:

```java
Flux.interval(Duration.ofMillis(1))
    .onBackpressureBuffer(10_000)
    .publishOn(Schedulers.single(), 128)
    .subscribe(this::process);
```

Biến thể buffer có giới hạn giúp đặt ngưỡng số phần tử chờ. Khi buffer đầy, overload này báo overflow thay vì tiếp tục giữ dữ liệu vô hạn. Ứng dụng cần xử lý lỗi đó bằng cách ghi nhận, retry có kiểm soát, giảm tốc độ nguồn hoặc chuyển sang một chính sách mất dữ liệu đã được nghiệp vụ cho phép. Đặt giới hạn mà không định nghĩa hành vi khi đầy chỉ chuyển nguy cơ cạn heap thành lỗi vận hành khó giải thích.

Nếu dữ liệu có thể bỏ, `onBackpressureDrop(...)` hoặc `onBackpressureLatest()` có thể phù hợp hơn. Hãy ghi metric số phần tử bị bỏ hoặc bị thay thế; nếu không, hệ thống có thể trông ổn định trong khi âm thầm mất thông tin.

## Xử lý nguồn push-only

Một số nguồn bên ngoài không có API request/pause. Ví dụ, thiết bị gửi UDP, callback của thư viện cũ hoặc event bus đẩy sự kiện theo nhịp riêng. Adapter không thể làm nguồn dừng chỉ bằng cách giảm demand nếu API gốc không hỗ trợ điều khiển. Nó cần một chính sách tại ranh giới:

1. Buffer có giới hạn và báo lỗi khi đầy nếu phải giữ mọi sự kiện trong giới hạn.
2. Drop hoặc latest nếu nghiệp vụ cho phép bỏ dữ liệu cũ.
3. Ghi vào hàng đợi bền vững bên ngoài heap nếu cần giữ sự kiện qua thời gian dài và có thể xử lý chậm.
4. Áp dụng flow control ở tầng giao thức nếu nguồn hỗ trợ tín hiệu tạm dừng hoặc điều tiết.

Không nên dùng một queue trong heap làm kho lưu trữ bền vững. Nếu ứng dụng cần giữ toàn bộ sự kiện trong nhiều phút hoặc nhiều giờ khi consumer không theo kịp, hãy chuyển backlog sang broker hoặc storage có giới hạn và chính sách retention rõ ràng.

## Đo lường để phát hiện backlog trước khi cạn heap

Theo dõi riêng tốc độ phát và tốc độ xử lý. Một metric throughput duy nhất có thể che giấu sự chênh lệch nếu chỉ đếm phần tử đã hoàn tất. Các tín hiệu hữu ích gồm:

- Số phần tử được nhận từ nguồn và số phần tử đã xử lý xong mỗi giây.
- Độ sâu queue hoặc số phần tử đang chờ tại các adapter và ranh giới bất đồng bộ.
- Độ trễ từ lúc tạo sự kiện đến lúc xử lý xong.
- Số lần overflow, drop, latest replacement hoặc retry.
- Heap used, allocation rate, thời gian và tần suất garbage collection.
- Số subscription, số tác vụ đang hoạt động và số tác vụ đang chờ.

Nếu tốc độ đầu vào duy trì cao hơn tốc độ xử lý, backlog sẽ tăng. Nếu heap tăng đồng thời với queue depth và event lag, đó là dấu hiệu cần điều chỉnh tải hoặc chính sách buffer. Nếu heap tăng nhưng queue depth ổn định, hãy tìm các nguyên nhân giữ tham chiếu khác như cache, replay không giới hạn hoặc collection tích lũy ở tầng ứng dụng.

Khi log, nên ghi timestamp, số thứ tự sự kiện và định danh subscription để theo dõi độ trễ mà không cần in toàn bộ payload. Với hệ thống có tải lớn, metric tổng hợp và sampling thường hữu ích hơn việc ghi log mọi phần tử.

## Kiểm thử hành vi khi buffer đầy

Kiểm thử nên xác nhận chính sách overflow thực sự xảy ra khi consumer chậm, không chỉ xác nhận pipeline xử lý được dữ liệu trong điều kiện bình thường. Có thể dùng `TestPublisher` để điều khiển việc phát và `StepVerifier` để điều khiển demand:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

class BackpressureBufferTest {
    @Test
    void boundedBufferFailsWhenCapacityIsExceeded() {
        TestPublisher<Integer> source = TestPublisher.create();

        Flux<Integer> buffered = source.flux()
            .onBackpressureBuffer(2);

        StepVerifier.create(buffered, 0)
            .then(() -> source.next(1, 2, 3))
            .expectError()
            .verify();
    }
}
```

Ví dụ này minh họa mục tiêu kiểm thử: downstream bắt đầu với demand bằng không, `onBackpressureBuffer` vẫn yêu cầu nguồn phát và giữ tối đa hai phần tử; phần tử thứ ba làm buffer tràn và pipeline kết thúc bằng lỗi. Bài test chỉ khẳng định tín hiệu lỗi, không giả định các phần tử đang chờ vẫn được phát sau khi overflow. Khi áp dụng vào dự án, hãy kiểm tra phiên bản Reactor Test đang dùng và chọn loại `TestPublisher` phù hợp để mô phỏng chính xác nguồn push cùng demand. Không dựa vào timing của thread hoặc `Thread.sleep` để tạo tình huống chậm một cách ngẫu nhiên.

Với chính sách drop/latest, kiểm thử cần xác nhận phần tử nào bị bỏ hoặc được giữ lại. Với điều tiết nguồn, cần xác nhận số request được gửi upstream và số phần tử tối đa được phát trước lần request tiếp theo.

## Những nhầm lẫn thường gặp

**Cho rằng demand không giới hạn đồng nghĩa với buffer không giới hạn.** Demand là số phần tử Subscriber cho phép phát; buffer là nơi lưu phần tử đang chờ. Chúng liên quan nhưng là hai khái niệm khác nhau.

**Cho rằng `request(Long.MAX_VALUE)` luôn gây OOM.** Nếu pipeline xử lý tuần tự và không tích lũy phần tử, demand không giới hạn có thể hoạt động với bộ nhớ ổn định. Nguy cơ tăng bộ nhớ xuất hiện khi có hàng đợi hoặc trạng thái tích lũy mà producer lấp đầy nhanh hơn consumer drain.

**Cho rằng `subscribe()` callback tạo backpressure hữu hạn.** Các overload tiện dụng của Reactor thường yêu cầu không giới hạn. Nếu cần demand hữu hạn, hãy dùng Subscriber có điều khiển hoặc thiết kế operator giới hạn upstream.

**Cho rằng `limitRate` là rate limiter.** `limitRate` điều chỉnh các đợt request theo số phần tử; nó không đặt giới hạn sự kiện mỗi giây và không thay thế bộ giới hạn tốc độ ở tầng nghiệp vụ.

**Tăng buffer để giải quyết consumer chậm vĩnh viễn.** Buffer lớn chỉ kéo dài thời gian trước khi đầy nếu tốc độ đầu vào vẫn cao hơn tốc độ xử lý. Hãy giải quyết chênh lệch tốc độ hoặc chọn chính sách overflow.

**Bỏ dữ liệu mà không đo lường.** Drop/latest có thể bảo vệ bộ nhớ nhưng làm thay đổi dữ liệu nghiệp vụ. Cần ghi nhận số phần tử bị bỏ và xác nhận nghiệp vụ cho phép.

## Tự kiểm tra

1. `request(Long.MAX_VALUE)` thay đổi điều gì trong hợp đồng demand? Nó có tự cấp phát bộ nhớ cho toàn bộ phần tử tương lai không?
2. Vì sao một pipeline xử lý đồng bộ từng `onNext` có thể dùng bộ nhớ ổn định dù Subscriber yêu cầu không giới hạn?
3. Nếu nguồn phát 90.000 sự kiện/giây và consumer xử lý 60.000 sự kiện/giây, backlog tăng xấp xỉ bao nhiêu phần tử sau 10 giây nếu tốc độ giữ nguyên?
4. Một pipeline dùng `onBackpressureBuffer()` trước `publishOn` có thể gặp rủi ro gì khi downstream xử lý chậm trong thời gian dài?
5. `limitRate(100)` kiểm soát điều gì và không kiểm soát điều gì?
6. Khi nào nên chọn buffer có giới hạn, drop hoặc latest cho một nguồn push-only?
7. Những metric nào giúp phân biệt backlog đang tăng với cache hoặc collection giữ bộ nhớ ở tầng ứng dụng?

Khi phân biệt được demand với buffering, xác định đúng nơi dữ liệu chờ và đo được chênh lệch giữa tốc độ phát với tốc độ xử lý, bạn có thể chọn giới hạn, chính sách overflow và cách điều tiết phù hợp để pipeline reactive không tích lũy bộ nhớ ngoài dự kiến.
