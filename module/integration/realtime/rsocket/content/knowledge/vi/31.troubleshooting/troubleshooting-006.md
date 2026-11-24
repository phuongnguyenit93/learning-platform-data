# Bộ đệm tăng khi bên nhận chậm hoặc nguồn phát không tuân theo nhu cầu

Trong một pipeline reactive, bộ đệm thường tăng khi dữ liệu đi vào nhanh hơn tốc độ downstream xử lý. Tình trạng này có thể xuất hiện trong RSocket request-stream, event stream từ broker, callback của thư viện cũ hoặc các operator có hàng đợi bất đồng bộ.

Hai nguyên nhân cần phân biệt:

- **Consumer chậm:** nguồn phát tuân thủ Reactive Streams, nhưng subscriber yêu cầu hoặc xử lý dữ liệu chậm. Demand/backpressure có thể làm nguồn giảm tốc độ; tuy nhiên các ranh giới bất đồng bộ vẫn có thể giữ một lượng phần tử đã được request trước.
- **Producer không tuân thủ demand hoặc không thể tạm dừng:** nguồn nóng, callback hoặc API bên ngoài tiếp tục phát dù downstream không có demand. Dữ liệu phải được buffer, drop, coalesce hoặc từ chối theo chính sách rõ ràng.

Backpressure không làm cho một nguồn dữ liệu vô hạn tự biến mất và cũng không làm tăng năng lực xử lý của consumer. Nếu tốc độ trung bình của producer luôn lớn hơn tốc độ tiêu thụ, một hàng đợi không giới hạn chỉ trì hoãn thời điểm hết bộ nhớ. Cần tìm đúng ranh giới đang tích lũy dữ liệu, đo tốc độ vào/ra và chọn chính sách có giới hạn.

## 1. Hiểu demand và hàng đợi trong Reactive Streams

Trong Reactive Streams, subscriber gửi request(n) để báo số phần tử có thể nhận. Publisher tuân thủ hợp đồng không được phát nhiều phần tử hơn tổng demand đã nhận. Khi subscriber xử lý xong một phần tử, nó có thể yêu cầu thêm.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant O as Reactive operator
    participant P as Publisher
    C->>O: request(2)
    O->>P: request(prefetch)
    P-->>O: onNext(A)
    P-->>O: onNext(B)
    Note over O: Giữ phần tử đã request trong queue nếu downstream chưa lấy
    O-->>C: onNext(A)
    O-->>C: onNext(B)
    C->>O: request(2)
    O->>P: request thêm
~~~

Các operator có thể request trước một số phần tử để giữ pipeline hoạt động liên tục. Ví dụ publishOn chuyển tín hiệu sang scheduler khác và dùng queue ở ranh giới thread; flatMap có thể chạy nhiều inner publisher đồng thời và prefetch dữ liệu từ từng inner publisher.

Vì vậy, ngay cả khi mọi Publisher đều tuân thủ demand, vẫn có thể thấy một lượng dữ liệu đang chờ trong queue. Điều cần điều tra là queue có giới hạn không, có được tiêu thụ dần không và có tăng liên tục khi tải ổn định hay không.

## 2. Phân biệt consumer chậm và producer vi phạm demand

Không phải mọi queue tăng đều là lỗi giao thức. Hãy xác định nguồn phát thuộc loại nào:

| Loại nguồn | Hành vi | Cách xử lý chính |
|---|---|---|
| Publisher reactive tuân thủ demand | Chỉ phát trong phạm vi request | Kiểm tra tốc độ xử lý, prefetch và queue của operator |
| Nguồn nóng (hot source) | Phát theo sự kiện bên ngoài, không chờ subscriber | Buffer có giới hạn, drop, latest hoặc điều tiết ở adapter |
| Callback API imperative | Gọi callback bất kể downstream có demand | Đưa callback qua bounded queue hoặc cơ chế pause/resume |
| Publisher không tuân thủ Reactive Streams | Phát nhiều hơn demand | Sửa nguồn; nếu không kiểm soát được, cô lập và bảo vệ tại adapter |
| Nhiều subscriber dùng chung nguồn | Subscriber có tốc độ khác nhau | Chọn semantics multicast và chính sách cho subscriber chậm |

Một producer phát theo tốc độ cố định không nhất thiết vi phạm Reactive Streams. Nó chỉ vi phạm nếu triển khai Publisher mà phát onNext vượt demand. Nếu producer là nguồn ngoài giao thức như callback hoặc UDP feed, vấn đề là adapter chưa chuyển đổi nguồn đó sang một Publisher có backpressure.

## 3. Dấu hiệu nhận biết buffer đang tăng

Các dấu hiệu thường thấy:

- Heap hoặc direct memory tăng theo thời gian dù số request đang hoạt động không đổi.
- Latency p95/p99 tăng dần, trong khi throughput hoàn tất không tăng tương ứng.
- Queue depth tăng liên tục hoặc không giảm sau khi tải đầu vào giảm.
- Consumer xử lý CPU cao, blocking I/O hoặc gọi dịch vụ phụ thuộc chậm.
- Các lỗi overflow xuất hiện khi dùng bounded buffer.
- Khi client hủy stream, listener hoặc tác vụ phía server vẫn tiếp tục chạy.
- Một số subscriber chậm làm các subscriber khác bị chậm theo khi dùng multicast policy không phù hợp.

Đừng chỉ nhìn tổng heap. Một queue có thể giữ tham chiếu tới payload lớn, buffer Netty hoặc object đồ thị sâu. Đếm số phần tử chưa đủ; cần theo dõi cả số byte ước tính và kích thước payload.

## 4. Lần theo ranh giới tạo queue

Hãy đọc pipeline từ nguồn tới subscriber và đánh dấu nơi có thể tích lũy:

~~~mermaid
flowchart TD
    SRC[Source / callback / broker]
    A[map / filter]
    B[publishOn queue]
    C[flatMap inner queues]
    D[onBackpressureBuffer]
    E[serialize / transport]
    F[RSocket client demand]
    G[UI hoặc downstream consumer]
    SRC --> A --> B --> C --> D --> E --> F --> G
    B -.-> Q1[Prefetch queue]
    C -.-> Q2[Concurrent inner queues]
    D -.-> Q3[Explicit buffer]
~~~

Các câu hỏi chẩn đoán:

1. Queue đầu tiên tăng nằm ở operator nào hoặc adapter nào?
2. Nguồn có nhận request(n) và có tuân thủ số lượng đó không?
3. Downstream đang request chậm hay đã ngừng request?
4. Có blocking call trong map, doOnNext hoặc callback không?
5. publishOn, flatMap, buffer, cache, replay hoặc collectList có giữ dữ liệu không?
6. Khi subscription cancel, nguồn và tài nguyên upstream có dừng không?

Đừng thêm onBackpressureBuffer() ở cuối pipeline trước khi biết dữ liệu đang được giữ ở đâu. Thêm một queue mới có thể che dấu nguyên nhân và làm bộ nhớ tăng nhanh hơn.

## 5. Đo tốc độ vào, tốc độ ra và demand

Một cách chẩn đoán đơn giản là đếm phần tử ở các ranh giới quan trọng:

~~~java
Flux<ProcessedOrderEvent> monitored = source
    .doOnRequest(n ->
        metrics.recordRequested(n)
    )
    .doOnNext(event ->
        metrics.incrementReceived()
    )
    .publishOn(Schedulers.parallel(), 32)
    .concatMap(event ->
        orderProcessor.process(event)
            .doOnSuccess(result -> metrics.incrementProcessed())
    );
~~~

Ví dụ giả định orderProcessor.process trả về Mono<ProcessedOrderEvent>. recordRequested ghi nhận demand đi qua vị trí doOnRequest; do publishOn có thể request theo prefetch, đây không nhất thiết là demand ban đầu của UI/client. Hàm này nên xử lý Long.MAX_VALUE như demand không giới hạn thay vì cộng số đó vào một counter thông thường. Bộ đếm received tăng khi event đi qua nguồn, còn processed chỉ tăng sau khi công việc nghiệp vụ hoàn tất.

Các metric hữu ích:

| Metric | Cách diễn giải |
|---|---|
| events received/s | Tốc độ dữ liệu đi vào |
| events processed/s | Tốc độ hoàn tất xử lý |
| queue depth | Số phần tử đang chờ |
| estimated queued bytes | Dung lượng payload đang giữ |
| outstanding demand | Nhu cầu đã yêu cầu nhưng chưa nhận |
| dropped events | Số phần tử bị loại bỏ |
| overflow count | Số lần vượt giới hạn buffer |
| processing duration | Thời gian xử lý mỗi phần tử |
| active subscriptions | Số stream đang hoạt động |
| cancelled subscriptions | Số stream đã bị hủy |

Nếu tốc độ vào liên tục lớn hơn tốc độ ra, queue sẽ tăng. Nếu tốc độ trung bình bằng nhau nhưng có burst ngắn, buffer hữu hạn có thể hấp thụ burst. Đây là khác biệt giữa burst tạm thời và mất cân bằng năng lực kéo dài.

Có thể ước tính thời gian để buffer đầy:

\[
T_{\text{full}} \approx \frac{C - Q_0}{R_{\text{in}} - R_{\text{out}}}
\]

Trong đó C là capacity theo phần tử, Q0 là số phần tử đang có, Rin là tốc độ vào và Rout là tốc độ ra. Công thức chỉ có ý nghĩa khi Rin lớn hơn Rout và tốc độ tương đối ổn định. Ví dụ queue còn 400 slot, producer nhanh hơn consumer 200 event/giây thì queue có thể đầy sau khoảng 2 giây. Với payload kích thước khác nhau, cần tính thêm byte budget thay vì chỉ đếm event.

## 6. Kiểm tra các operator có prefetch

### publishOn

publishOn chuyển việc xử lý các operator downstream sang scheduler khác. Nó cần queue để bàn giao tín hiệu giữa thread. Có thể chỉ định prefetch thay vì dùng giá trị mặc định:

~~~java
Flux<OrderEvent> events = source
    .publishOn(Schedulers.parallel(), 32)
    .map(this::transform);
~~~

Prefetch nhỏ làm giảm số phần tử được giữ trước ở ranh giới đó, nhưng có thể giảm throughput nếu consumer xử lý nhanh và phải chờ request bổ sung thường xuyên. Chọn giá trị bằng benchmark và quan sát queue, latency, CPU.

### flatMap

flatMap cho phép nhiều inner publisher chạy đồng thời. Concurrency và prefetch ảnh hưởng tổng số phần tử có thể đang được xử lý hoặc chờ:

~~~java
Flux<PaymentResult> results = commands.flatMap(
    command -> paymentService.process(command),
    8,
    16
);
~~~

Ví dụ giới hạn tối đa 8 inner publisher đang hoạt động và prefetch 16 phần tử cho mỗi inner publisher. Đây không phải giới hạn byte; nếu mỗi phần tử rất lớn, bộ nhớ vẫn có thể đáng kể. Nếu thứ tự phải được giữ, cân nhắc concatMap hoặc một chiến lược tuần tự khác.

### Các operator giữ nhiều dữ liệu

Các operator như collectList, cache, replay, buffer hoặc window có thể giữ dữ liệu theo mục đích thiết kế. Với stream vô hạn, collectList() không hoàn tất cho tới khi nguồn complete và có thể tích lũy vô hạn. Không dùng các operator giữ toàn bộ lịch sử cho stream dài nếu không có giới hạn hoặc chính sách lưu trữ.

## 7. Giới hạn buffer thay vì dùng hàng đợi vô hạn

onBackpressureBuffer() không tham số có thể giữ dữ liệu chờ downstream mà không đặt giới hạn hữu ích cho ứng dụng. Nếu nguồn có thể phát liên tục trong khi consumer chậm, queue có thể làm cạn bộ nhớ.

Dùng buffer có giới hạn và định nghĩa rõ hành vi khi đầy:

~~~java
Flux<OrderEvent> buffered = hotSource
    .onBackpressureBuffer(
        512,
        droppedOrOverflowed -> metrics.incrementBufferOverflow()
    );
~~~

Overload giới hạn kích thước ở ví dụ này phát lỗi overflow khi buffer vượt dung lượng; callback dùng để ghi nhận phần tử gây overflow. Hãy xác minh overload và hành vi chính xác theo phiên bản Reactor đang dùng. Khi buffer đầy, lỗi cần được xử lý ở tầng thích hợp và hiển thị bằng metric/alert.

Giới hạn theo số phần tử chưa chắc giới hạn bộ nhớ nếu payload có kích thước khác nhau. Với payload lớn hoặc không đồng nhất, nên giới hạn kích thước message, ước tính byte đang giữ và đặt giới hạn ở tầng adapter hoặc queue có byte budget.

Buffer hữu hạn hấp thụ burst trong khoảng thời gian ngắn. Nó không giải quyết được tình huống producer luôn nhanh hơn consumer.

## 8. Chọn chính sách khi consumer chậm

Không có một chính sách overflow phù hợp cho mọi loại dữ liệu. Hãy quyết định dữ liệu có thể mất hay không và consumer cần lịch sử hay chỉ cần trạng thái mới nhất.

| Chính sách | Reactor operator / cách làm | Khi phù hợp | Đánh đổi |
|---|---|---|---|
| Giữ mọi phần tử trong giới hạn | onBackpressureBuffer(maxSize, ...) | Burst ngắn, sự kiện không được mất trong giới hạn đã chọn | Overflow cần xử lý; buffer đầy thì stream lỗi |
| Bỏ phần tử mới khi không có demand | onBackpressureDrop(...) | Telemetry hoặc cập nhật có thể bỏ | Mất dữ liệu mới |
| Chỉ giữ phần tử mới nhất | onBackpressureLatest() | Snapshot, giá trị trạng thái hiện tại | Bỏ các trạng thái trung gian |
| Làm chậm producer | Propagate demand hoặc pause/resume nguồn | Producer có thể điều tiết | Có thể làm chậm toàn pipeline |
| Ghi bền vững rồi đọc theo cursor | Durable broker/log/database | Cần replay và không muốn giữ toàn bộ trong RAM | Tăng độ phức tạp và I/O |
| Từ chối sớm | Overflow/error hoặc reject tại ingress | Hệ thống cần giới hạn tải rõ ràng | Caller phải retry hoặc xử lý lỗi |

Ví dụ bỏ phần tử khi downstream chưa sẵn sàng:

~~~java
Flux<MetricEvent> metricsStream = hotMetrics
    .onBackpressureDrop(event ->
        metrics.incrementDropped()
    );
~~~

Ví dụ chỉ giữ snapshot mới nhất:

~~~java
Flux<AccountSnapshot> latestSnapshot = hotSnapshots
    .onBackpressureLatest();
~~~

Không dùng drop/latest cho command thanh toán, cập nhật tồn kho hoặc sự kiện audit nếu nghiệp vụ yêu cầu không mất dữ liệu. Với dữ liệu cần giữ đầy đủ, dùng producer flow control hoặc lưu trữ bền vững thay vì hy vọng RAM đủ lớn.

## 9. Xử lý nguồn nóng hoặc callback không hỗ trợ backpressure

Một API callback có thể gọi listener bất cứ lúc nào, bất kể subscriber đã request bao nhiêu phần tử. Khi bridge loại nguồn này vào Reactor, cần tạo một ranh giới có dung lượng giới hạn và xử lý kết quả phát.

Ví dụ dùng unicast sink với queue hữu hạn:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

public final class EventBridge {

    private final Sinks.Many<OrderEvent> sink =
        Sinks.many().unicast()
            .onBackpressureBuffer(new ArrayBlockingQueue<>(256));

    public Flux<OrderEvent> events() {
        return sink.asFlux();
    }

    public void onExternalEvent(OrderEvent event) {
        Sinks.EmitResult result = sink.tryEmitNext(event);

        if (result.isFailure()) {
            handleEmitFailure(result, event);
        }
    }

    private void handleEmitFailure(
        Sinks.EmitResult result,
        OrderEvent event
    ) {
        // Ghi metric và áp dụng chính sách reject, retry hoặc drop.
    }
}
~~~

Unicast sink chỉ cho phép một subscriber. Queue ArrayBlockingQueue đặt giới hạn số event được giữ. Khi queue đầy, tryEmitNext có thể trả về FAIL_OVERFLOW; producer adapter phải kiểm tra và xử lý kết quả đó. Các kết quả như FAIL_ZERO_SUBSCRIBER, FAIL_CANCELLED, FAIL_TERMINATED hoặc FAIL_NON_SERIALIZED cũng cần được phân loại theo tình huống. Đặc biệt, nếu nhiều callback thread gọi sink đồng thời, hãy serialize việc phát hoặc xử lý FAIL_NON_SERIALIZED theo chính sách retry có giới hạn. Không bỏ qua EmitResult vì như vậy dữ liệu có thể mất mà không có metric hoặc log.

Nếu callback có thể pause/resume, hãy nối trạng thái queue với API điều tiết nguồn: tạm dừng khi queue đạt high-water mark và tiếp tục khi queue xuống low-water mark. Nếu nguồn không thể tạm dừng, phải chọn drop, reject, persist hoặc chấp nhận lỗi có kiểm soát.

Với nhiều subscriber, cần chọn sink multicast phù hợp và xác định subscriber chậm ảnh hưởng tới subscriber khác như thế nào. Không thay unicast bằng multicast một cách máy móc vì semantics về buffering và subscriber mới có thể khác.

## 10. Phân biệt queue của ứng dụng và flow control của RSocket

RSocket request-stream và request-channel có demand được truyền qua giao thức bằng REQUEST_N. Khi subscriber yêu cầu thêm dữ liệu, phía gửi có thể tiếp tục phát theo demand. Khi subscriber hủy stream, CANCEL báo kết thúc tương tác.

Điều này không đồng nghĩa transport TCP/WebSocket tự biết ứng dụng đã xử lý xong payload. TCP flow control điều tiết byte giữa hai socket; RSocket demand điều tiết payload giữa hai đầu RSocket; queue của ứng dụng có thể nằm trước hoặc sau cả hai lớp.

~~~mermaid
flowchart TD
    P[Producer trong service]
    Q[Queue/operator của server]
    RS[RSocket stream]
    NET[TCP hoặc WebSocket transport]
    CQ[Queue phía client]
    C[Consumer/UI]
    P --> Q --> RS --> NET --> CQ --> C
    C -. REQUEST_N .-> RS
    C -. CANCEL .-> RS
~~~

Nếu client nhận payload nhanh nhưng xử lý UI chậm, client có thể đã request trước nhiều phần tử. Hãy xem demand do subscriber phát ra, prefetch ở client và hàng đợi do ứng dụng tạo. Nếu server queue tăng, kiểm tra demand nhận từ peer và các operator phía server. Nếu client queue tăng, kiểm tra tốc độ xử lý client và số phần tử client đã request.

Với Spring RSocket, Flux trả về từ @MessageMapping được kết nối với demand của tương tác. Tránh tự gọi subscribe() bên trong handler vì subscription tách rời có thể không còn chịu cancellation/demand của RSocket request.

## 11. Xử lý nhiều subscriber với tốc độ khác nhau

Một stream multicast có thể phục vụ nhiều subscriber, trong đó một subscriber nhanh và một subscriber chậm. Cần chọn chính sách:

- Tất cả subscriber phải nhận đủ mọi event: subscriber chậm có thể làm tăng buffering hoặc làm chậm publisher chung.
- Subscriber độc lập: mỗi subscriber có queue và giới hạn riêng; phải giới hạn tổng bộ nhớ theo số subscriber.
- Subscriber chỉ cần snapshot mới nhất: dùng latest/coalescing semantics.
- Subscriber có thể bỏ event: drop theo subscriber và ghi metric riêng.

Không để một subscriber chậm giữ queue vô hạn cho toàn bộ nhóm. Với fan-out lớn, tính ngân sách bộ nhớ theo subscriber count × queue capacity × payload size, rồi đặt giới hạn kết nối hoặc giới hạn số subscriber.

Nếu một subscriber hủy, kiểm tra nguồn dùng chung còn subscriber khác hay không. Chỉ đóng upstream khi không còn consumer theo đúng chính sách ownership, ví dụ ref-count hoặc connection manager.

## 12. Điều tiết producer bằng high-water và low-water mark

Với nguồn có thể pause/resume, dùng hai ngưỡng để tránh bật/tắt liên tục:

- **High-water mark:** khi queue đạt ngưỡng này, yêu cầu producer tạm dừng.
- **Low-water mark:** khi queue giảm xuống ngưỡng thấp hơn, cho phép producer tiếp tục.

~~~java
if (queueDepth >= HIGH_WATER_MARK && producer.isRunning()) {
    producer.pause();
}

if (queueDepth <= LOW_WATER_MARK && producer.isPaused()) {
    producer.resume();
}
~~~

Đoạn code là pseudocode vì API pause/resume tùy loại broker hoặc nguồn ngoài. Chọn low-water thấp hơn high-water để tạo hysteresis. Khi pause, vẫn cần tính dữ liệu đang trên đường truyền hoặc callback đã được xếp hàng nhưng chưa thực thi.

Nếu nguồn không có pause/resume, có thể điều tiết tại ingress bằng semaphore, giới hạn concurrency, rate limit hoặc trả lỗi quá tải. Hãy để producer biết khi hệ thống không thể nhận thêm dữ liệu thay vì âm thầm tăng queue.

## 13. Dùng giới hạn concurrency và batch

Một consumer chậm có thể bị quá tải bởi quá nhiều tác vụ chạy song song. Giới hạn concurrency thường hiệu quả hơn việc tăng prefetch:

~~~java
Flux<PaymentResult> results = paymentCommands
    .flatMap(
        command -> paymentService.process(command),
        8,
        1
    );
~~~

Ở đây tối đa 8 lệnh được xử lý đồng thời, mỗi inner publisher có prefetch 1. Giá trị thực tế phải dựa trên khả năng database/service downstream và yêu cầu thứ tự. Nếu thứ tự tuyệt đối quan trọng, cân nhắc concatMap.

Nếu consumer có thể xử lý theo lô, gom một batch hữu hạn:

~~~java
import java.time.Duration;
import java.util.List;

Flux<List<OrderEvent>> batches = events.bufferTimeout(
    100,
    Duration.ofMillis(50)
);
~~~

Batch giảm overhead cho consumer nhưng làm tăng latency của phần tử đầu batch và giữ nhiều phần tử cùng lúc. Đặt cả giới hạn số phần tử lẫn thời gian chờ, và cân nhắc kích thước byte nếu event có payload lớn.

## 14. Kiểm tra nguồn phát không tuân thủ demand bằng TestPublisher

Reactor TestPublisher có chế độ non-compliant để cố ý mô phỏng publisher vi phạm Reactive Streams. Ví dụ REQUEST_OVERFLOW cho phép nguồn phát onNext vượt demand:

~~~java
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

TestPublisher<Integer> source =
    TestPublisher.createNoncompliant(
        TestPublisher.Violation.REQUEST_OVERFLOW
    );

StepVerifier.create(source.flux(), 0)
    .then(() -> source.next(1))
    .expectNext(1)
    .thenCancel()
    .verify();
~~~

Đây là test phòng thủ để thấy nguồn vi phạm có thể đẩy dữ liệu dù subscriber chưa request. Không dùng non-compliant TestPublisher cho test nghiệp vụ thông thường. Trong production, ưu tiên sửa publisher hoặc cô lập nguồn ngoài bằng adapter có giới hạn và kiểm tra overflow.

## 15. Chẩn đoán theo triệu chứng

| Triệu chứng | Khả năng cần kiểm tra | Hành động |
|---|---|---|
| Queue tăng đều dù tải ổn định | Producer rate lớn hơn consumer rate | Giảm tốc độ vào, tăng năng lực xử lý hoặc persist |
| Queue tăng sau publishOn | Scheduler downstream chậm hoặc prefetch quá lớn | Đo thời gian xử lý và thử prefetch nhỏ hơn |
| Queue tăng theo số inner publisher | flatMap concurrency/prefetch cao | Giới hạn concurrency và prefetch |
| Heap tăng khi stream chạy lâu | Buffer không giới hạn, collectList, cache hoặc replay | Đặt capacity/retention và kiểm tra object retention |
| Chỉ một client chậm làm cả nhóm chậm | Multicast policy giữ theo subscriber chậm | Tách queue/chính sách theo subscriber hoặc latest/drop |
| Overflow khi broker/callback burst | Adapter không có bounded queue hoặc pause/resume | Giới hạn queue và xử lý emit failure |
| Queue còn tăng sau CANCEL | Subscription bị tách hoặc cleanup không chạy | Compose pipeline, kiểm tra cancellation và resource cleanup |
| CPU thấp nhưng latency tăng | Queueing hoặc dependency bên ngoài chậm | Đo queue wait time và downstream latency |
| CPU cao và throughput không tăng | Quá nhiều concurrency, context switch hoặc serialization | Profile CPU và giảm concurrency/prefetch |

## 16. Quy trình xử lý sự cố

Khi phát hiện queue hoặc memory tăng, thực hiện theo thứ tự:

1. Ghi lại thời điểm, route, số stream, tốc độ event vào/ra và kích thước payload.
2. Xác định queue nằm ở operator, adapter, broker client, RSocket peer hay UI.
3. Kiểm tra demand và request pattern; xác nhận nguồn có tuân thủ demand không.
4. Đo processing time, queue wait time, CPU, heap/direct memory và GC.
5. Kiểm tra các operator có prefetch, buffer, replay hoặc concurrency cao.
6. Nếu nguồn là callback/hot source, thêm bounded queue và xử lý overflow.
7. Chọn buffer, drop, latest, pause/resume, persist hoặc reject theo yêu cầu dữ liệu.
8. Kiểm tra cancellation và cleanup khi client ngắt kết nối.
9. Chạy lại với burst ngắn và tải kéo dài để phân biệt queue hấp thụ burst với mất cân bằng lâu dài.

Không giải quyết sự cố bằng cách tăng heap trước khi hiểu tốc độ vào/ra. Tăng heap có thể kéo dài thời gian trước khi OOM nhưng cũng làm GC pause dài hơn và không sửa được queue không giới hạn.

## 17. Kiểm thử giới hạn và overflow

Một test cần xác minh cả trường hợp bình thường lẫn khi buffer đầy. Với nguồn nóng, có thể dùng TestPublisher để phát theo bước và StepVerifier để kiểm tra chính sách drop hoặc error:

~~~java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(
        source.flux().onBackpressureBuffer(2),
        0
    )
    .then(() -> source.next(1, 2, 3))
    .expectError()
    .verify();
~~~

Ví dụ minh họa nguồn phát ba phần tử khi downstream chưa request phần tử nào. Operator yêu cầu nguồn và giữ tối đa hai phần tử; phần tử thứ ba làm buffer overflow nên pipeline kết thúc bằng lỗi. Test chỉ xác nhận lỗi overflow, không giả định hai phần tử đã buffer sẽ được phát trước terminal signal. Trong test dự án, xác nhận rõ prefetch và request ban đầu để assertion không phụ thuộc giả định sai.

Các trường hợp nên kiểm thử:

- Burst nhỏ hơn capacity được giữ đầy đủ.
- Burst vượt capacity tạo overflow đúng chính sách.
- Drop/latest chỉ bỏ dữ liệu theo semantics đã chọn.
- Consumer tiếp tục request thì queue giảm.
- Cancel dừng nguồn và giải phóng resource.
- Một subscriber chậm không làm rò dữ liệu hoặc giữ queue vô hạn.
- Payload lớn không vượt byte budget dù số phần tử còn dưới capacity.

## 18. Checklist phòng ngừa

- Mọi queue do ứng dụng tạo đều có capacity hoặc retention policy.
- Không dùng buffer vô hạn cho stream dài hoặc nguồn nóng không kiểm soát.
- Prefetch và concurrency được cấu hình có chủ đích.
- Tốc độ vào, tốc độ xử lý, queue depth và overflow được đo.
- Nguồn ngoài được bridge qua adapter có bounded queue.
- Emit failure không bị bỏ qua.
- Chọn drop/latest chỉ khi nghiệp vụ cho phép mất dữ liệu.
- Dữ liệu cần giữ đầy đủ được điều tiết hoặc lưu bền vững.
- RSocket handler compose publisher và tôn trọng demand/cancellation.
- Cancellation giải phóng listener, queue và resource upstream.
- Có test cho burst, sustained overload, overflow và slow consumer.

## 19. Kết luận

Bộ đệm tăng là dấu hiệu dữ liệu đang chờ lâu hơn khả năng tiêu thụ hiện tại. Với Publisher tuân thủ Reactive Streams, kiểm tra demand, prefetch, scheduler và concurrency. Với nguồn nóng hoặc callback không hỗ trợ backpressure, cần tạo ranh giới có giới hạn và quyết định rõ buffer, drop, latest, pause/resume, persist hoặc reject.

Buffer chỉ hấp thụ burst ngắn. Nếu producer liên tục nhanh hơn consumer, phải điều tiết tốc độ vào, tăng năng lực xử lý hoặc thay đổi cách lưu trữ. Trong RSocket, theo dõi riêng demand của stream, queue của ứng dụng và flow control của TCP/WebSocket để tìm đúng nơi tích lũy. Giới hạn queue, đo tốc độ vào/ra và kiểm thử overflow giúp hệ thống realtime giữ được bộ nhớ ổn định khi tải tăng.
