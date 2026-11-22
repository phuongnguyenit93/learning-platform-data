# Thực nghiệm callback, nguồn hot và backpressure có giới hạn

## 1. Bài toán và mục tiêu

Nhiều API bên ngoài không trả về Publisher. Chúng đăng ký callback rồi gọi callback mỗi khi có sự kiện: listener của thiết bị, message broker client, SDK gửi telemetry, thư viện đọc file hoặc một adapter legacy.

Trong Reactor, ta thường cần biến callback thành Flux để ghép với WebFlux, R2DBC, WebClient và các operator khác. Nhưng ba câu hỏi phải được giải quyết cùng lúc:

1. **Callback được đăng ký và hủy lúc nào?** Khi subscriber hủy, listener, timer hoặc connection có được đóng không?
2. **Nguồn là hot hay cold?** Subscriber đến muộn có nhận sự kiện đã phát trước đó không? Một subscriber mới có tạo thêm listener mới không?
3. **Producer nhanh hơn consumer thì sao?** Có buffer không giới hạn, drop dữ liệu, giữ item mới nhất hay báo lỗi? Có thể truyền demand ngược tới API callback không?

Ví dụ API kiểu push:

~~~java
interface EventListener {
    void onEvent(String event);
    void onError(Throwable error);
    void onComplete();
}

interface LegacyEventSource {
    AutoCloseable register(EventListener listener);
}
~~~

API gọi callback bất cứ khi nào có event; nó không nhận Subscription.request(n) theo Reactive Streams. Nếu chuyển thẳng thành Flux.create mà không chọn chiến lược, ứng dụng có thể tích lũy buffer rất lớn khi consumer chậm.

**Mục tiêu bài học**

- Phân biệt cold Publisher, hot Publisher, multicast và replay.
- Chọn Flux.generate, Flux.create hoặc Flux.push theo đặc tính nguồn.
- Bridge callback với FluxSink, đăng ký listener và cleanup khi complete/error/cancel.
- Hiểu onRequest, requestedFromDownstream và push/pull hybrid.
- Chọn buffer giới hạn, drop, latest hoặc error theo ý nghĩa dữ liệu.
- Dùng Sinks.Many để tạo hot stream có nhiều subscriber và xử lý kết quả emit.
- Kiểm thử demand bằng StepVerifier, TestPublisher và JUnit.
- Xây dựng project Java 17, Reactor và Spring Boot 3.5.7 dependency management có thể chạy bằng Maven.

## 2. Cold và hot Publisher

### 2.1. Cold: mỗi subscriber có một lần thực thi riêng

Cold Publisher tạo nguồn dữ liệu khi có subscriber. Mỗi subscriber thường nhận một lần thực thi mới:

~~~java
AtomicInteger runs = new AtomicInteger();

Flux<Integer> cold = Flux.defer(() -> {
    int run = runs.incrementAndGet();
    return Flux.just(run, run + 1);
});
~~~

Hai subscriber lần lượt nhận hai chuỗi độc lập:

~~~java
cold.subscribe(value -> System.out.println("A: " + value));
cold.subscribe(value -> System.out.println("B: " + value));
~~~

Output:

~~~text
A: 1
A: 2
B: 2
B: 3
~~~

Nguồn được tạo lại ở mỗi subscription. Flux.defer hoãn việc tạo Publisher bên trong supplier cho tới subscription; điều này hữu ích khi mỗi subscriber cần listener hoặc request riêng.

Các ví dụ cold phổ biến: Flux.fromIterable, Mono.fromCallable, Mono.defer, Flux.defer, WebClient request và phần lớn repository query.

### 2.2. Hot: sự kiện phát theo thời gian

Hot source có thể phát độc lập với số subscriber. Subscriber mới thường chỉ nhận sự kiện sau khi nó đăng ký; lịch sử không tự động được phát lại.

~~~text
Thời gian  ------------------------------------------------>

Nguồn hot:       A       B       C       D       E
Subscriber 1:        subscribe -------------------------->
Nhận được:                   B       C       D       E

Subscriber 2:                            subscribe ----->
Nhận được:                                       E
~~~

Ví dụ điển hình là giá thị trường, telemetry, notification và event bus. Nếu subscriber 2 cần cả sự kiện đã xảy ra trước đó, phải chọn replay hoặc lưu trữ riêng.

### 2.3. Mono.just và defer

Mono.just(value) chụp giá trị ngay lúc assembly. Nó phát lại giá trị đã chụp cho subscriber sau đó; biểu thức tạo giá trị không chạy lại.

~~~java
String snapshot = readCurrentValue();
Mono<String> captured = Mono.just(snapshot);

Mono<String> perSubscription = Mono.defer(
    () -> Mono.just(readCurrentValue())
);
~~~

Nếu readCurrentValue() phải chạy cho mỗi subscriber, dùng defer. Nếu muốn chia sẻ một kết quả duy nhất, cân nhắc cache() hoặc một cơ chế chia sẻ có lifecycle rõ ràng.

### 2.4. Chuyển cold thành hot bằng share, publish và replay

- share() chia sẻ subscription upstream giữa các subscriber đang tham gia; phù hợp với live stream không cần lưu lịch sử.
- publish().refCount(n) chỉ kết nối upstream khi đủ subscriber theo ngưỡng.
- replay(n) giữ lại một số item gần nhất cho subscriber đến muộn.
- cache() lưu tín hiệu đã phát và phát lại cho subscriber sau, có thể giữ cả terminal signal; cần hiểu thời hạn/lifecycle cache.

Không dùng share() như durable event log. Nếu subscriber cần replay lâu dài, dùng broker/log/database có retention phù hợp.

## 3. Chọn API tạo sequence: generate, create hay push?

| API | Kiểu producer | Số thread phát | Backpressure | Trường hợp phù hợp |
| --- | --- | --- | --- | --- |
| Flux.generate | Đồng bộ, từng item | Một lần callback sinh item | Pull từng bước | Sinh dãy có state |
| Flux.create | Callback bất đồng bộ | Có thể nhiều thread | FluxSink và OverflowStrategy | Bridge listener API đa thread |
| Flux.push | Callback bất đồng bộ | Một producer thread tại một thời điểm | FluxSink và OverflowStrategy | Listener đảm bảo single-thread |
| Sinks.Many | Producer chủ động gọi emit | Phát hiện cạnh tranh thread | Tùy sink flavor | Tạo hot Publisher dùng chung |

### 3.1. Flux.generate: đồng bộ, một item mỗi vòng

~~~java
Flux<Integer> numbers = Flux.generate(
    () -> 0,
    (state, sink) -> {
        sink.next(state);
        if (state == 4) {
            sink.complete();
        }
        return state + 1;
    }
);
~~~

Output:

~~~text
0
1
2
3
4
~~~

Mỗi invocation của generator phát tối đa một onNext, có thể complete/error và trả state mới. Không dùng generate để gọi callback bất đồng bộ từ một thread khác.

### 3.2. Flux.create: nhiều item và nhiều producer thread

Flux.create cung cấp FluxSink<T> để bridge callback API có thể phát nhiều item trong một lần callback hoặc từ nhiều thread.

~~~java
Flux<String> events = Flux.create(sink -> {
    EventListener listener = new EventListener() {
        @Override
        public void onEvent(String event) {
            sink.next(event);
        }

        @Override
        public void onError(Throwable error) {
            sink.error(error);
        }

        @Override
        public void onComplete() {
            sink.complete();
        }
    };

    AutoCloseable registration = source.register(listener);
    sink.onDispose(() -> closeQuietly(registration));
}, FluxSink.OverflowStrategy.ERROR);
~~~

Đây là cấu trúc minh họa; source và closeQuietly phải được cung cấp bởi ứng dụng. Điểm quan trọng là callback terminal phải được chuyển thành sink.error hoặc sink.complete, và đăng ký listener phải được cleanup.

Flux.create không tự biến code đồng bộ thành bất đồng bộ. Nếu lambda tạo source block vô hạn hoặc gọi blocking I/O, nó có thể chặn thread subscribe và gây deadlock. Hãy bridge callback thật, không chạy vòng lặp vô hạn bên trong lambda.

### 3.3. Flux.push: callback chỉ phát từ một thread

Flux.push có API tương tự create, nhưng chỉ phù hợp khi một producer thread duy nhất gọi next, error và complete.

~~~java
Flux<String> singleThreadEvents = Flux.push(sink -> {
    SingleThreadListener listener = new SingleThreadListener() {
        @Override
        public void onEvent(String value) {
            sink.next(value);
        }

        @Override
        public void onComplete() {
            sink.complete();
        }
    };

    AutoCloseable registration = source.register(listener);
    sink.onDispose(() -> closeQuietly(registration));
}, FluxSink.OverflowStrategy.DROP);
~~~

Nếu callback có thể đồng thời chạy từ nhiều thread, chọn create hoặc tuần tự hóa nguồn trước khi phát. Không dùng push rồi gọi sink.next song song.

### 3.4. FluxSink và các terminal signal

Các method chính:

- sink.next(value): phát một item.
- sink.error(error): kết thúc bằng lỗi.
- sink.complete(): kết thúc bình thường.
- sink.onRequest(consumer): nhận thông báo demand từ downstream.
- sink.requestedFromDownstream(): đọc lượng demand còn lại tại thời điểm truy vấn.
- sink.isCancelled(): kiểm tra subscriber đã cancel.
- sink.onCancel(disposable): callback chỉ dành cho cancellation.
- sink.onDispose(disposable): cleanup khi complete, error hoặc cancel.

Sau complete() hoặc error(), không tiếp tục phát item. Một callback đến muộn phải được ngăn chặn hoặc xử lý theo lifecycle; không phát terminal signal nhiều lần.

## 4. Cleanup callback: đăng ký, cancel và dispose

### 4.1. Listener phải có registration handle

Khi subscribe, callback adapter thường đăng ký listener. Khi sequence kết thúc hoặc bị cancel, phải gỡ listener:

~~~java
Flux<String> events = Flux.create(sink -> {
    Registration registration = eventBus.register(sink::next);
    sink.onDispose(registration::close);
});
~~~

Nếu bỏ onDispose, subscriber có thể đã rời đi nhưng event bus vẫn giữ listener và giữ tham chiếu đến object graph của request. Đây là nguyên nhân gây leak listener, task nền hoặc connection.

### 4.2. onCancel khác onDispose

- onCancel chỉ chạy khi downstream gửi cancellation.
- onDispose chạy khi sequence complete, error hoặc cancel.
- Nếu resource cần hủy subscription riêng khi cancel và đóng hẳn khi kết thúc, có thể đăng ký cả hai; các thao tác cleanup phải idempotent.
- Nếu một thao tác close() đã đủ cho cả ba trường hợp, chỉ cần onDispose.

~~~java
Flux<String> events = Flux.create(sink -> {
    Registration registration = eventBus.register(sink::next);

    sink.onCancel(registration::pause);
    sink.onDispose(registration::close);
});
~~~

Đoạn này chỉ phù hợp khi pause() và close() là hai thao tác khác nhau, an toàn khi gọi theo thứ tự. Không đăng ký cả hai callback để gọi cùng một release không idempotent.

### 4.3. Guard callback sau cancellation

~~~java
event -> {
    if (!sink.isCancelled()) {
        sink.next(event);
    }
}
~~~

Guard có thể tránh nhiều lần gọi callback không cần thiết, nhưng nó không thay thế việc deregister listener. Giữa lúc kiểm tra isCancelled() và lúc phát tín hiệu vẫn có race; hãy để sink quản lý signal lifecycle và dừng nguồn tại callback cleanup.

### 4.4. Cleanup khi source phát complete/error

Nếu nguồn callback tự complete, onDispose vẫn được gọi. Điều đó giúp gỡ listener cả khi không có downstream cancel.

Không nuốt lỗi trong quá trình đăng ký hoặc đóng resource. Nếu register có thể ném exception, hãy để nó trở thành error signal hoặc map sang exception nghiệp vụ phù hợp. Cleanup failure cần được log/đưa vào observability; không cố gửi sink.error sau khi sink đã complete/cancel.

## 5. Backpressure: consumer yêu cầu, producer phát

### 5.1. Reactive Streams demand

Subscriber gọi request(n) để báo số item nó sẵn sàng nhận. Producer chỉ nên phát không vượt demand đã được cấp. cancel() báo không cần dữ liệu nữa.

~~~text
Subscriber (pull)                     Producer (push)
       |                                    |
       | -------- request(2) -------------->|
       |<--------------- item 1 ------------|
       |<--------------- item 2 ------------|
       | -------- request(1) -------------->|
       |<--------------- item 3 ------------|
       | -------- cancel ------------------>|
~~~

Reactor là mô hình push/pull kết hợp: downstream pull bằng request; upstream push item khi dữ liệu có sẵn và demand cho phép.

### 5.2. Callback API thường không biết demand

Một event bus kiểu listener thường chỉ gọi onEvent khi có dữ liệu. Nó không biết downstream đã request 0, 1 hay 100 item.

Nếu adapter chỉ gọi sink.next khi callback đến, Reactor phải áp dụng một chiến lược khi consumer chậm. Không có chiến lược nào vừa giữ vô hạn mọi item, vừa giới hạn bộ nhớ, vừa không mất dữ liệu nếu producer không thể bị điều tiết. Phải chọn chính sách phù hợp với nghiệp vụ.

### 5.3. Backpressure có thể truyền ngược nếu source hỗ trợ

Một số API hỗ trợ request(n), pause/resume, fetch(n) hoặc polling theo batch. Khi đó FluxSink.onRequest có thể truyền demand tới nguồn:

~~~java
Flux<String> bridge = Flux.create(sink -> {
    Registration registration = channel.register(sink::next);

    sink.onRequest(n -> channel.request(n));
    sink.onDispose(registration::close);
}, FluxSink.OverflowStrategy.ERROR);
~~~

n là lượng demand tăng thêm mà sink nhận được. API ngoài phải diễn giải đúng demand, cộng dồn an toàn và không phát quá lượng đã cấp. Nếu nguồn không có khả năng pull/pause, onRequest không thể ép callback ngừng phát.

### 5.4. requestedFromDownstream chỉ là snapshot

~~~java
if (sink.requestedFromDownstream() > 0) {
    sink.next(event);
}
~~~

Đây chỉ là quan sát demand tại thời điểm kiểm tra. Nếu callback nhiều thread hoặc nhiều event đồng thời, nhiều callback có thể cùng thấy demand dương rồi cùng phát. Không tự viết bộ đếm demand cạnh tranh nếu không cần; ưu tiên FluxSink overflow strategy hoặc source có API pull thật.

## 6. Các chiến lược overflow trong Flux.create/push

Khi gọi Flux.create/Flux.push, có thể chọn FluxSink.OverflowStrategy:

| Strategy | Khi downstream không theo kịp | Hệ quả |
| --- | --- | --- |
| BUFFER | Buffer tất cả item | Mặc định; không giới hạn và có nguy cơ OutOfMemoryError |
| DROP | Bỏ item mới đến | Giữ item cũ đang chờ, bỏ dữ liệu mới |
| LATEST | Chỉ giữ item mới nhất | Phù hợp snapshot/trạng thái hiện tại |
| ERROR | Phát IllegalStateException | Báo producer vượt khả năng tiêu thụ |
| IGNORE | Bỏ qua demand | Có thể làm queue downstream tràn; chỉ dùng khi có lý do đặc biệt |

### 6.1. BUFFER: không phải lúc nào cũng an toàn

~~~java
Flux<Event> events = Flux.create(
    sink -> registerListener(sink),
    FluxSink.OverflowStrategy.BUFFER
);
~~~

BUFFER là mặc định của Flux.create. Nếu producer phát 10.000 item/giây và consumer chỉ xử lý 1.000 item/giây, backlog tăng khoảng 9.000 item/giây. Sau một thời gian, heap có thể cạn.

Không chọn BUFFER chỉ vì “không muốn mất dữ liệu”. Nếu dữ liệu không được phép mất, phải có giới hạn, khả năng backpressure nguồn, durable queue hoặc lưu trữ ngoài bộ nhớ.

### 6.2. DROP: giữ backlog cũ, bỏ item mới khi thiếu demand

~~~java
Flux<Integer> values = Flux.create(
    sink -> registerNumbers(sink),
    FluxSink.OverflowStrategy.DROP
);
~~~

Dùng cho tín hiệu có thể bỏ mẫu mới trong lúc consumer bận hoặc khi source đã có backlog. Nếu cần biết item nào bị drop, có thể dùng operator onBackpressureDrop(consumer) sau nguồn và ghi metric/counter.

### 6.3. LATEST: chỉ quan tâm trạng thái gần nhất

~~~java
Flux<Position> positions = Flux.create(
    sink -> registerGpsListener(sink),
    FluxSink.OverflowStrategy.LATEST
);
~~~

Nếu người dùng chỉ cần vị trí mới nhất, giữ mọi tọa độ cũ có thể vô ích. LATEST thay item đang chờ bằng item mới hơn khi downstream chưa có demand. Khi downstream request tiếp, nó nhận snapshot gần nhất.

Không dùng LATEST cho event cần xử lý tất cả: payment, order transition, audit log hoặc message cần bảo đảm giao hàng.

### 6.4. ERROR: fail fast khi consumer không theo kịp

~~~java
Flux<Event> events = Flux.create(
    sink -> registerCriticalListener(sink),
    FluxSink.OverflowStrategy.ERROR
);
~~~

Khi thiếu demand, sink phát overflow error. Đây là cách phát hiện consumer chậm hoặc producer vượt giới hạn. Caller cần có error handling, retry/reconnect và metric; ERROR không tự lưu event để xử lý sau.

### 6.5. IGNORE: không phải cách tăng tốc an toàn

IGNORE bỏ qua backpressure. Downstream queue/operator có thể tràn hoặc phát lỗi ở nơi khác. Chỉ cân nhắc khi nguồn/consumer có bảo đảm riêng về tốc độ và buffer; nếu không, tránh sử dụng.

## 7. Operator backpressure: buffer có giới hạn, drop, latest và error

Các operator này hữu ích khi nguồn đã là Publisher nhưng phát nhanh hơn downstream.

### 7.1. Buffer có giới hạn

~~~java
Flux<Event> bounded = source.onBackpressureBuffer(
    256,
    event -> metrics.incrementOverflow()
);
~~~

- Tối đa 256 item được giữ khi downstream chưa request đủ.
- Khi item vượt capacity, callback nhận item overflow.
- Source bị cancel và sequence kết thúc bằng overflow error.
- Lỗi có thể được phát sau khi backlog hiện tại đã được tiêu thụ.

Đây là buffer giới hạn theo số item, không theo byte. Nếu mỗi item có payload 5 MB, capacity 256 vẫn có thể giữ hơn 1 GB dữ liệu. Ước lượng kích thước item và đặt capacity phù hợp.

### 7.2. Drop và đo số lượng bị bỏ

~~~java
AtomicLong dropped = new AtomicLong();

Flux<Event> bestEffort = source.onBackpressureDrop(
    event -> dropped.incrementAndGet()
);
~~~

Operator bỏ item khi downstream không có demand và gọi callback cho item bị bỏ. Đây là lựa chọn cho telemetry, mouse movement hoặc metric sample nếu bỏ mẫu không ảnh hưởng nghiệp vụ.

### 7.3. Latest

~~~java
Flux<Snapshot> latest = source.onBackpressureLatest();
~~~

Khi consumer chậm, operator giữ lại item gần nhất và loại item cũ đang chờ. Phù hợp snapshot dashboard, trạng thái hiện tại hoặc sensor value.

### 7.4. Error khi thiếu demand

~~~java
Flux<Event> strict = source.onBackpressureError();
~~~

Nếu upstream phát item khi downstream không có demand, operator phát overflow error. Dùng khi mất dữ liệu không chấp nhận được và caller cần xử lý rõ ràng.

### 7.5. Điều quan trọng: các operator này yêu cầu unbounded upstream

onBackpressureBuffer, onBackpressureDrop, onBackpressureLatest và onBackpressureError yêu cầu upstream một lượng demand không giới hạn, rồi tự xử lý khoảng cách demand ở phía downstream.

Vì vậy, chúng không làm producer callback chậm lại. Chúng là adapter cho nguồn push; buffer/drop/latest/error quyết định điều gì xảy ra khi downstream không nhận kịp.

Nếu source có khả năng request(n) hoặc pause/resume, hãy truyền demand ngược bằng onRequest hoặc API tương đương thay vì chỉ hấp thụ tốc độ bằng queue.

### 7.6. limitRate không phải giới hạn bộ nhớ

~~~java
Flux<Event> controlled = source.limitRate(64);
~~~

limitRate chia request lớn thành các batch nhỏ khi truyền ngược tới upstream Reactive Streams compliant. Nó giúp điều chỉnh nhịp request/prefetch. Nhưng nếu source là callback push không tuân thủ demand, limitRate không tự ngăn source phát thêm dữ liệu và không thay thế overflow strategy.

## 8. Hot source với Sinks.Many

### 8.1. Vì sao dùng Sinks?

Sinks.Many<T> là API chủ động phát tín hiệu và cung cấp một Publisher view qua asFlux(). Nó hữu ích khi nhiều phần của ứng dụng muốn phát sự kiện vào một stream dùng chung.

~~~java
Sinks.Many<String> sink =
    Sinks.many().multicast().onBackpressureBuffer();

Flux<String> events = sink.asFlux();

Sinks.EmitResult result = sink.tryEmitNext("order-created");
if (result.isFailure()) {
    log.warn("Could not emit event: {}", result);
}
~~~

Không bỏ qua EmitResult. OK nghĩa là sink chấp nhận emission theo trạng thái tại thời điểm gọi; nó không bảo đảm consumer đã xử lý hoặc lưu event xuống database.

### 8.2. Ba flavor Many

| Flavor | Subscriber | Sự kiện trước subscription | Replay |
| --- | --- | --- | --- |
| unicast().onBackpressureBuffer() | Tối đa một subscriber | Buffer chờ subscriber đầu tiên | Không replay cho subscriber thứ hai |
| multicast().onBackpressureBuffer() | Nhiều subscriber | Chỉ chuyển sự kiện sau khi subscriber đã đăng ký | Không replay lịch sử |
| replay().limit(n) | Nhiều subscriber | Lưu lịch sử theo giới hạn | Subscriber muộn nhận tối đa n item gần nhất |

Multicast buffer vẫn tôn trọng backpressure của từng subscriber, nhưng không có nghĩa nó lưu lịch sử cho subscriber đến muộn. Unicast buffer có thể giữ item trước subscriber đầu tiên nhưng chỉ cho một subscriber. Replay sink lưu lịch sử theo cấu hình.

### 8.3. directAllOrNothing và directBestEffort

- directAllOrNothing(): nếu bất kỳ subscriber nào không có demand, item bị drop cho tất cả subscriber.
- directBestEffort(): subscriber chậm bị drop riêng; subscriber có demand vẫn nhận item.

Hai flavor này không giữ backlog cho subscriber chậm. Chọn theo yêu cầu consistency giữa người nhận.

### 8.4. Concurrent producer và EmitResult

Sinks mặc định phát hiện nhiều producer gọi đồng thời. tryEmitNext có thể trả:

| EmitResult | Ý nghĩa |
| --- | --- |
| OK | Emission được chấp nhận |
| FAIL_ZERO_SUBSCRIBER | Không có subscriber và sink không có buffer cho trường hợp đó |
| FAIL_OVERFLOW | Không còn capacity |
| FAIL_NON_SERIALIZED | Có producer cạnh tranh, emission không được serialize |
| FAIL_CANCELLED | Sink đã bị subscriber cancel |
| FAIL_TERMINATED | Sink đã complete/error trước đó |

Khi gặp FAIL_NON_SERIALIZED, serialize producer, dùng queue/single writer hoặc một emission failure handler phù hợp. Không lặp tryEmitNext vô hạn trong vòng spin. Khi FAIL_OVERFLOW, phải quyết định drop, retry, persist hoặc báo lỗi; không được giả định item đã được nhận.

### 8.5. Không nhầm sink với durable broker

Sinks là in-memory. Process restart có thể làm mất event chưa được xử lý. Nếu cần replay sau crash, acknowledgement, consumer group, retention hoặc delivery guarantee, dùng message broker/log bền vững và thiết kế idempotency.

## 9. Mẫu callback adapter có cleanup

Một adapter thực tế nên có interface đăng ký rõ ràng:

~~~java
package example.callback;

import java.util.function.Consumer;

public interface CallbackEventBus {

    interface Registration {
        void close();
    }

    Registration register(Consumer<String> listener);
}
~~~

Adapter:

~~~java
package example.callback;

import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;

public final class CallbackFluxAdapter {

    public Flux<String> events(CallbackEventBus bus) {
        return Flux.create(sink -> {
            CallbackEventBus.Registration registration =
                bus.register(event -> {
                    if (!sink.isCancelled()) {
                        sink.next(event);
                    }
                });

            sink.onDispose(registration::close);
        }, FluxSink.OverflowStrategy.ERROR);
    }
}
~~~

Mỗi subscriber của Flux này đăng ký một listener riêng. Khi subscriber cancel, complete hoặc error, onDispose đóng registration. Strategy ERROR giúp phát hiện producer đẩy nhanh hơn consumer.

Nếu muốn một callback registration dùng chung cho nhiều subscriber, không tạo một adapter cold như trên cho mỗi subscriber; hãy thiết kế shared source bằng Sinks hoặc publish/share với lifecycle của connection/listener rõ ràng.

### 9.1. Khi nguồn hỗ trợ demand

~~~java
return Flux.create(sink -> {
    Registration registration = bus.register(sink::next);
    sink.onRequest(bus::request);
    sink.onDispose(registration::close);
}, FluxSink.OverflowStrategy.ERROR);
~~~

Đoạn này giả định bus.request(long n) thực sự điều tiết nguồn. Nếu register vẫn phát event tùy ý, onRequest chỉ là tín hiệu thông báo, không bảo đảm source tuân thủ demand.

## 10. Ví dụ Maven đầy đủ: Java 17, Spring Boot 3.5.7 và Reactor Test

Project minh họa cold/hot, callback registration, cancellation cleanup, bounded queue, drop/latest, onRequest và sink overflow. Spring Boot parent quản lý dependency version; WebFlux cung cấp Reactor Core, còn reactor-test và JUnit dùng ở test scope.

### 10.1. Cấu trúc

~~~text
callback-backpressure-demo/
├── pom.xml
├── src/main/java/example/callback/
│   ├── CallbackEventBus.java
│   └── CallbackFluxAdapter.java
└── src/test/java/example/callback/
    └── CallbackBackpressureTest.java
~~~

### 10.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>callback-backpressure-demo</artifactId>
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
~~~

### 10.3. CallbackEventBus.java

~~~java
package example.callback;

import java.util.function.Consumer;

public interface CallbackEventBus {

    interface Registration {
        void close();
    }

    Registration register(Consumer<String> listener);
}
~~~

### 10.4. CallbackFluxAdapter.java

~~~java
package example.callback;

import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;

public final class CallbackFluxAdapter {

    public Flux<String> events(CallbackEventBus bus) {
        return Flux.create(sink -> {
            CallbackEventBus.Registration registration =
                bus.register(event -> {
                    if (!sink.isCancelled()) {
                        sink.next(event);
                    }
                });

            sink.onDispose(registration::close);
        }, FluxSink.OverflowStrategy.ERROR);
    }
}
~~~

### 10.5. CallbackBackpressureTest.java

~~~java
package example.callback;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;

import org.junit.jupiter.api.Test;

import reactor.core.Exceptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.FluxSink;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

class CallbackBackpressureTest {

    static final class InMemoryEventBus implements CallbackEventBus {
        private final List<Consumer<String>> listeners =
            new CopyOnWriteArrayList<>();

        @Override
        public Registration register(Consumer<String> listener) {
            listeners.add(listener);
            return () -> listeners.remove(listener);
        }

        void publish(String event) {
            listeners.forEach(listener -> listener.accept(event));
        }

        int listenerCount() {
            return listeners.size();
        }
    }

    @Test
    void coldPublisherRunsAgainForEachSubscriber() {
        AtomicInteger runs = new AtomicInteger();

        Flux<Integer> cold = Flux.defer(() ->
            Flux.just(runs.incrementAndGet()));

        StepVerifier.create(cold)
            .expectNext(1)
            .verifyComplete();

        StepVerifier.create(cold)
            .expectNext(2)
            .verifyComplete();

        assertEquals(2, runs.get());
    }

    @Test
    void callbackRegistrationIsClosedAfterCancellation() {
        InMemoryEventBus bus = new InMemoryEventBus();
        CallbackFluxAdapter adapter = new CallbackFluxAdapter();

        StepVerifier.create(adapter.events(bus))
            .then(() -> {
                assertEquals(1, bus.listenerCount());
                bus.publish("temperature:25");
            })
            .expectNext("temperature:25")
            .thenCancel()
            .verify();

        assertEquals(0, bus.listenerCount());
    }

    @Test
    void boundedBufferDrainsCapacityThenSignalsOverflow() {
        TestPublisher<Integer> source = TestPublisher.create();
        List<Integer> overflow = new ArrayList<>();

        Flux<Integer> guarded =
            source.flux().onBackpressureBuffer(2, overflow::add);

        StepVerifier.create(guarded, 0)
            .then(() -> source.next(1, 2, 3))
            .thenRequest(2)
            .expectNext(1, 2)
            .expectErrorMatches(Exceptions::isOverflow)
            .verify();

        assertEquals(List.of(3), overflow);
    }

    @Test
    void dropStrategyReportsValuesWithoutDemand() {
        TestPublisher<Integer> source = TestPublisher.create();
        List<Integer> dropped = new ArrayList<>();

        Flux<Integer> guarded =
            source.flux().onBackpressureDrop(dropped::add);

        StepVerifier.create(guarded, 0)
            .then(() -> source.next(1, 2))
            .thenRequest(1)
            .then(() -> source.next(3))
            .expectNext(3)
            .then(source::complete)
            .verifyComplete();

        assertEquals(List.of(1, 2), dropped);
    }

    @Test
    void latestKeepsOnlyNewestValueWithoutDemand() {
        TestPublisher<Integer> source = TestPublisher.create();

        Flux<Integer> guarded =
            source.flux().onBackpressureLatest();

        StepVerifier.create(guarded, 0)
            .then(() -> source.next(1, 2, 3))
            .thenRequest(1)
            .expectNext(3)
            .then(source::complete)
            .verifyComplete();
    }

    @Test
    void sinkWithBoundedUnicastQueueReportsOverflow() {
        Sinks.Many<Integer> sink =
            Sinks.many().unicast().onBackpressureBuffer(
                new ArrayBlockingQueue<>(2));

        StepVerifier.create(sink.asFlux(), 0)
            .then(() ->
                assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1)))
            .then(() ->
                assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2)))
            .then(() ->
                assertEquals(
                    Sinks.EmitResult.FAIL_OVERFLOW,
                    sink.tryEmitNext(3)))
            .thenRequest(2)
            .expectNext(1, 2)
            .then(() ->
                assertEquals(
                    Sinks.EmitResult.OK,
                    sink.tryEmitComplete()))
            .verifyComplete();
    }

    @Test
    void onRequestReceivesIncrementalDemand() {
        AtomicLong requested = new AtomicLong();

        Flux<Integer> bridge = Flux.create(
            sink -> sink.onRequest(requested::addAndGet),
            FluxSink.OverflowStrategy.ERROR
        );

        StepVerifier.create(bridge, 0)
            .thenRequest(3)
            .then(() -> assertEquals(3L, requested.get()))
            .thenRequest(2)
            .then(() -> assertEquals(5L, requested.get()))
            .thenCancel()
            .verify();
    }

    @Test
    void multicastSinkDoesNotReplayPastEvents() {
        Sinks.Many<Integer> sink =
            Sinks.many().multicast().onBackpressureBuffer();

        assertEquals(
            Sinks.EmitResult.FAIL_ZERO_SUBSCRIBER,
            sink.tryEmitNext(1)
        );

        StepVerifier.create(sink.asFlux())
            .then(() ->
                assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2)))
            .expectNext(2)
            .then(() ->
                assertEquals(
                    Sinks.EmitResult.OK,
                    sink.tryEmitComplete()))
            .verifyComplete();
    }

    @Test
    void replaySinkDeliversConfiguredHistoryToLateSubscriber() {
        Sinks.Many<Integer> sink =
            Sinks.many().replay().limit(1);

        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(10));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(20));

        StepVerifier.create(sink.asFlux())
            .expectNext(20)
            .thenCancel()
            .verify();
    }
}
~~~

### 10.6. Giải thích kết quả từng test

1. coldPublisherRunsAgainForEachSubscriber: mỗi subscriber kích hoạt supplier một lần, kết quả tăng từ 1 lên 2.
2. callbackRegistrationIsClosedAfterCancellation: subscription đăng ký listener; sau khi nhận event và cancel, listener được gỡ khỏi event bus.
3. boundedBufferDrainsCapacityThenSignalsOverflow: buffer giữ 1 và 2; item 3 vượt capacity, được callback nhận diện; sau khi backlog được request, sequence phát overflow error.
4. dropStrategyReportsValuesWithoutDemand: khi initial request bằng 0, 1 và 2 bị drop; sau khi request, item 3 được chuyển tiếp.
5. latestKeepsOnlyNewestValueWithoutDemand: ba item đến trong lúc demand bằng 0; khi request, subscriber nhận 3.
6. sinkWithBoundedUnicastQueueReportsOverflow: queue có capacity 2 nhận hai item; item thứ ba bị từ chối bằng FAIL_OVERFLOW.
7. onRequestReceivesIncrementalDemand: request 3 rồi request 2; callback nhận tổng demand tăng thêm 5.
8. multicastSinkDoesNotReplayPastEvents: emission trước subscriber không được giữ; subscriber chỉ nhận item phát sau khi đăng ký.
9. replaySinkDeliversConfiguredHistoryToLateSubscriber: replay limit 1 nên subscriber muộn nhận item 20, không nhận item 10.

### 10.7. Chạy project

Yêu cầu JDK 17+ và Maven:

~~~bash
java -version
mvn test
~~~

Kết quả dự kiến khi toàn bộ test pass:

~~~text
Tests run: 9, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là kết quả mong đợi từ ví dụ, không phải log đã chạy. Project không cần HTTP server, database hay kết nối Internet; test kiểm tra Reactor trực tiếp.

## 11. Backpressure theo từng loại dữ liệu

| Dữ liệu | Strategy thường cân nhắc | Vì sao |
| --- | --- | --- |
| GPS position, dashboard snapshot | LATEST | Vị trí mới nhất có giá trị hơn backlog cũ |
| Mouse movement, UI preview | DROP hoặc LATEST | Có thể bỏ mẫu trung gian |
| Telemetry có thể tổng hợp | DROP + metric hoặc batch | Không nhất thiết xử lý mọi sample |
| Audit log, payment, order event | Durable queue/broker; buffer hữu hạn + fail | Không được âm thầm mất event |
| Command cần phản hồi producer | ERROR/acknowledgement | Producer phải biết consumer không theo kịp |
| Một consumer xử lý tuần tự | Unicast sink với bounded queue | Một subscriber, có capacity rõ |
| Nhiều subscriber live | Multicast sink | Mỗi subscriber nhận event mới |
| Subscriber đến muộn cần lịch sử ngắn | Replay sink limit(n) | Replay có giới hạn |

### 11.1. Bounded buffer cần một overflow policy

Một queue hữu hạn chỉ trả lời “giữ được bao nhiêu item”. Khi đầy, hệ thống vẫn phải quyết định:

- Reject producer và trả lỗi.
- Drop item mới.
- Drop item cũ nhất.
- Giữ item mới nhất.
- Persist item vào disk/broker.
- Pause producer nếu API nguồn hỗ trợ.

Không có policy thì buffer đầy sẽ chuyển thành lỗi ngẫu nhiên hoặc mất dữ liệu không quan sát được.

### 11.2. Kích thước item cũng quan trọng

Giới hạn 1.000 item không nói được memory tối đa nếu payload có kích thước thay đổi. Ước lượng:

~~~text
memory ≈ queue capacity × average retained item size + object/queue overhead
~~~

Đối với payload lớn, cần giới hạn byte, giới hạn kích thước message, streaming chunk nhỏ hoặc persist ra ngoài heap.

### 11.3. Thời gian chờ và tốc độ tiêu thụ

Nếu producer phát trung bình λ item/giây, consumer xử lý μ item/giây và λ > μ, backlog tăng xấp xỉ λ − μ item/giây. Capacity B có thể đầy sau khoảng:

~~~text
time to overflow ≈ B / (λ − μ)
~~~

Đây chỉ là ước lượng khi tốc độ ổn định; burst traffic, GC, scheduler và kích thước item làm thay đổi thực tế. Dùng load test để đo.

### 11.4. Không buffer vô hạn để che vấn đề vận hành

Buffer vô hạn chỉ trì hoãn lúc thất bại và làm sự cố khó dự đoán. Nếu consumer chậm kéo dài, cần giảm tốc producer, tăng năng lực xử lý, giới hạn concurrency hoặc dùng queue bền vững.

## 12. Threading, concurrency và ordering

### 12.1. create và push

- Flux.create: phù hợp callback có thể phát từ nhiều thread; Reactor xử lý việc serialize signal.
- Flux.push: phù hợp callback chỉ phát từ một producer thread tại một thời điểm.
- Flux.generate: synchronous, từng item; không phải bridge asynchronous event listener.

Chọn sai abstraction có thể gây signal race hoặc vi phạm Reactive Streams. Nếu nguồn nhiều thread nhưng cần thứ tự toàn cục, phải định nghĩa ordering tại source/queue; việc serialize signal không tạo ra thứ tự nghiệp vụ nếu callback vốn chạy song song.

### 12.2. Sinks an toàn với concurrent access nhưng vẫn có kết quả thất bại

Sinks mặc định phát hiện concurrent emission. Nếu nhiều thread gọi tryEmitNext cùng lúc, một call có thể trả FAIL_NON_SERIALIZED. Có thể:

- Đưa mọi emission qua một single-writer queue.
- Serialize producer bằng executor/lock phù hợp.
- Dùng emitNext với EmitFailureHandler khi policy retry contention rõ ràng.

Không dùng Sinks.unsafe() chỉ để bỏ qua lỗi concurrency; API unsafe yêu cầu caller tự đảm bảo serialization và Reactive Streams contract.

### 12.3. Ordering của callback

Nếu API ngoài có thể gọi listener đồng thời, thứ tự onEvent có thể khác thứ tự timestamp hoặc sequence number của nghiệp vụ. Nếu cần ordering, gắn sequence number, sort/reorder ở một buffer có giới hạn hoặc dùng nguồn đảm bảo thứ tự.

### 12.4. Tránh blocking trong callback

Callback thường chạy trên thread do thư viện ngoài quản lý. Không gọi database blocking, file blocking hoặc block() trực tiếp trong callback. Phát event vào Flux/Sink rồi compose công việc reactive; nếu cần isolate blocking API, dùng scheduler thích hợp và giới hạn concurrency.

### 12.5. Callback không nên giữ payload mutable

Nếu callback phát object mutable rồi producer tiếp tục sửa object đó, downstream có thể nhìn thấy trạng thái thay đổi ngoài dự kiến. Phát immutable value/record hoặc copy dữ liệu trước khi đưa vào stream.

## 13. Kiểm thử backpressure và hot source đúng cách

### 13.1. StepVerifier với initial request bằng 0

~~~java
StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext("first")
    .thenRequest(2)
    .expectNext("second", "third")
    .verifyComplete();
~~~

Initial request 0 giúp tạo tình huống downstream chưa có demand. Sau đó thenRequest(n) điều khiển chính xác thời điểm consumer nhận item.

### 13.2. TestPublisher tạo nguồn phát có kiểm soát

TestPublisher cho phép test chủ động phát next, complete hoặc error. Nó hữu ích để kiểm tra operator backpressure khi downstream request 0, sau đó mới request.

Không dùng Thread.sleep để chờ event trong test. Dùng then, thenRequest, thenCancel và timeout của verifier.

### 13.3. Kiểm tra drop/overflow bằng side effect quan sát

Với onBackpressureDrop(consumer) hoặc onBackpressureBuffer(maxSize, onOverflow), test callback nhận đúng item bị drop/overflow. Không chỉ kiểm tra terminal signal vì có thể strategy chạy nhưng item bị mất không đúng chính sách.

### 13.4. Test cleanup sau cancel

Một test callback bridge nên xác nhận listener count giảm về 0 sau thenCancel(). Đây là kiểm thử resource lifecycle; chỉ xác minh Flux không phát thêm item là chưa đủ.

### 13.5. Test hot source và subscriber đến muộn

Dùng Sinks.many().multicast() để xác minh subscriber muộn không nhận item cũ. Dùng replay().limit(n) để xác minh lịch sử được replay đúng giới hạn.

### 13.6. Kiểm tra concurrency

Khi source phát từ nhiều thread hoặc nhiều producer cùng gọi sink, cần test emission result, ordering và serialization. Không viết test chỉ dựa vào Thread.sleep; dùng CountDownLatch, executor có kiểm soát hoặc test harness phù hợp, và cleanup thread sau test.

## 14. Các lỗi thường gặp

**1 — Dùng Flux.create mặc định với callback tần suất cao.** Strategy mặc định BUFFER không giới hạn, có thể gây OutOfMemoryError. Chọn overflow policy hoặc truyền demand tới source.

**2 — Dùng Flux.push cho callback nhiều thread.** push dành cho một producer thread tại một thời điểm. Dùng create hoặc serialize nguồn.

**3 — Quên gỡ listener khi cancel.** Event bus giữ callback và giữ tham chiếu đến subscriber. Dùng onDispose/onCancel theo lifecycle.

**4 — Chỉ gỡ listener khi cancel mà quên complete/error.** Resource vẫn bị giữ nếu nguồn kết thúc tự nhiên. Dùng onDispose cho cleanup mọi terminal path.

**5 — Dùng onDispose và onCancel để gọi cùng close không idempotent.** Cancellation có thể chạy cả hai callback. Thiết kế close an toàn khi lặp hoặc chỉ đăng ký onDispose.

**6 — Nghĩ create làm code tự chạy bất đồng bộ.** create chỉ bridge callback; lambda blocking có thể chặn thread subscribe.

**7 — Nghĩ onRequest tự điều tiết mọi callback API.** Nó chỉ báo demand. Nguồn phải có request/pause/fetch thực sự.

**8 — Dùng requestedFromDownstream như khóa đồng bộ.** Giá trị là snapshot; nhiều callback cạnh tranh có thể cùng thấy demand dương.

**9 — Dùng DROP cho payment hoặc audit.** Dữ liệu mất là lỗi nghiệp vụ. Chọn durable queue hoặc fail/ack policy.

**10 — Dùng LATEST cho event cần xử lý tất cả.** LATEST cố ý bỏ trạng thái trung gian.

**11 — Dùng unbounded replay sink.** Subscriber đến muộn có thể làm memory tăng theo toàn bộ lịch sử. Chọn replay limit/time window.

**12 — Dùng multicast khi cần replay cho subscriber muộn.** Multicast chỉ chuyển event mới sau subscription. Chọn replay nếu cần lịch sử.

**13 — Dùng unicast sink nhưng có nhiều subscriber.** Unicast chỉ hỗ trợ một subscriber.

**14 — Bỏ qua EmitResult từ tryEmitNext.** FAIL_OVERFLOW, FAIL_ZERO_SUBSCRIBER hoặc FAIL_NON_SERIALIZED có thể làm mất event. Xử lý từng trạng thái theo policy.

**15 — Retry FAIL_NON_SERIALIZED bằng vòng lặp vô hạn.** Có thể spin CPU. Serialize producer hoặc dùng failure handler có giới hạn.

**16 — Nghĩ limitRate giới hạn queue của callback source.** limitRate chỉ điều chỉnh request upstream; source push không tuân thủ demand vẫn có thể phát quá nhanh.

**17 — Nghĩ bounded buffer là giới hạn byte.** Capacity thường tính theo item. Payload lớn vẫn có thể chiếm nhiều memory.

**18 — Không đo overflow/drop.** Hệ thống mất dữ liệu nhưng không có metric. Ghi counter, rate và cảnh báo.

**19 — Không dừng producer khi downstream cancel.** Producer tiếp tục tạo event và tiêu thụ CPU/network dù không còn subscriber.

**20 — Dùng blocking I/O trong callback.** Làm nghẽn thread của thư viện ngoài và kéo dài event dispatch.

**21 — Phát mutable object rồi sửa sau đó.** Downstream có thể quan sát dữ liệu bị thay đổi. Dùng immutable event hoặc copy.

**22 — Cho rằng Sinks là durable message queue.** Sink là in-memory; restart có thể làm mất dữ liệu chưa xử lý.

## 15. Checklist production

### Nguồn và lifecycle

1. Nguồn callback có thể phát từ một thread hay nhiều thread?
2. Có cần create, push hay generate?
3. Listener registration có handle để unregister/close không?
4. Cleanup có chạy khi complete, error và cancel không?
5. Có race khi callback phát đồng thời với cancellation không?
6. Một subscriber tạo listener riêng hay chia sẻ một listener?
7. Hot source có cần replay lịch sử cho subscriber đến muộn không?

### Backpressure và memory

8. Nguồn có hỗ trợ request/pause/resume thật không?
9. Nếu không, chọn BUFFER, DROP, LATEST hay ERROR theo semantics nào?
10. Capacity bao nhiêu item và ước lượng byte bao nhiêu?
11. Overflow callback có ghi metric/log an toàn không?
12. Khi buffer đầy, producer bị cancel hay tiếp tục phát?
13. Có giới hạn queue, payload, concurrency và thời gian chờ không?
14. Có chính sách shutdown và drain backlog không?
15. Có kiểm tra slow consumer trong load test không?

### Concurrency và độ tin cậy

16. Sinks có thể nhận emission đồng thời không?
17. FAIL_NON_SERIALIZED và FAIL_OVERFLOW được xử lý ra sao?
18. Có cần ordering theo sequence number không?
19. Event có immutable và có idempotency key không?
20. Có cần durable broker thay cho in-memory sink không?
21. Có metrics cho active subscribers, queue depth, dropped count, overflow count và event lag không?
22. Integration test có xác nhận listener được cleanup sau cancel không?

## 16. Câu hỏi ôn tập

1. Cold Publisher thực thi thế nào? **Tạo lại nguồn cho mỗi subscriber.**
2. Hot Publisher xử lý subscriber đến muộn thế nào? **Thường chỉ nhận item phát sau khi subscribe, trừ flavor có replay/cache.**
3. Mono.just chụp giá trị lúc nào? **Lúc assembly.**
4. Operator nào hoãn tạo Publisher đến subscription? **defer.**
5. Flux.generate phù hợp kiểu nguồn nào? **Đồng bộ, sinh tối đa một item mỗi invocation.**
6. Flux.create phù hợp khi nào? **Bridge callback bất đồng bộ, có thể nhiều producer thread.**
7. Flux.push khác create thế nào? **Chỉ một producer thread tại một thời điểm.**
8. onDispose chạy khi nào? **Complete, error hoặc cancel.**
9. onCancel chạy khi nào? **Chỉ cancellation.**
10. Flux.create default overflow strategy là gì? **BUFFER không giới hạn.**
11. Strategy nào giữ item mới nhất? **LATEST.**
12. Strategy nào bỏ item mới khi thiếu demand? **DROP.**
13. Strategy nào báo lỗi khi consumer không theo kịp? **ERROR.**
14. onRequest dùng để làm gì? **Truyền demand đến nguồn nếu nguồn hỗ trợ pull/request.**
15. requestedFromDownstream có phải lock không? **Không; chỉ là snapshot demand.**
16. onBackpressureBuffer(maxSize) làm gì khi đầy? **Báo overflow và cancel source; backlog hiện tại có thể được drain trước error.**
17. onBackpressureDrop có yêu cầu unbounded upstream không? **Có; operator tự drop khi downstream thiếu demand.**
18. limitRate có giới hạn memory của callback push không? **Không.**
19. Multicast sink có replay lịch sử không? **Không; nó phát event mới cho subscriber đã đăng ký.**
20. Unicast sink cho phép bao nhiêu subscriber? **Một.**
21. Replay sink giới hạn lịch sử bằng API nào? **replay().limit(n).**
22. FAIL_NON_SERIALIZED có nghĩa gì? **Emission cạnh tranh chưa được serialize.**
23. OK từ tryEmitNext có đảm bảo consumer xử lý xong không? **Không.**
24. Vì sao bounded queue cần overflow policy? **Khi đầy vẫn phải quyết định reject, drop, latest, persist hoặc pause producer.**

## 17. Tóm tắt và tài liệu tham khảo

- Cold Publisher tạo nguồn mới theo mỗi subscription; hot source phát theo thời gian và subscriber đến muộn thường không nhận lịch sử nếu không cấu hình replay.
- Flux.generate dành cho sinh đồng bộ từng item; Flux.create cho callback có thể đa thread; Flux.push cho một producer thread.
- onDispose cleanup khi complete/error/cancel; onCancel chỉ xử lý cancellation.
- Callback source không hỗ trợ pull thì không thể bị điều tiết chỉ bằng downstream demand. Cần chọn bounded buffer, drop, latest hoặc error.
- Flux.create mặc định BUFFER không giới hạn; không dùng nó vô thức cho event source tần suất cao.
- onBackpressureBuffer(maxSize, callback) giới hạn backlog theo số item và báo overflow; drop/latest/error có semantics khác nhau.
- onRequest có thể truyền demand tới nguồn có API request/pause/fetch.
- Sinks.Many cung cấp hot Publisher với unicast/multicast/replay; phải kiểm tra EmitResult và xử lý concurrency/overflow.
- Test phải điều khiển demand bằng StepVerifier, dùng TestPublisher, xác minh cleanup listener sau cancel và phân biệt multicast với replay.
- In-memory sink không thay durable broker; chọn chiến lược dựa trên yêu cầu mất dữ liệu, ordering, replay và memory.

**Tài liệu chính thức**

1. [Project Reactor 3.7 — Programmatically Creating a Sequence](https://projectreactor.io/docs/core/3.7.17/reference/coreFeatures/programmatically-creating-sequence.html): generate, create, push, overflow strategy, onRequest, onCancel và onDispose.
2. [Project Reactor 3.7 — Hot Versus Cold](https://projectreactor.io/docs/core/3.7.0/reference/advancedFeatures/reactor-hotCold.html): cold/hot, defer, share và replay.
3. [Project Reactor 3.7 — Sinks](https://docs.spring.io/projectreactor/reactor-core/docs/3.7.x/reference/html/coreFeatures/sinks.html): unicast, multicast, replay, concurrent producers và EmitResult.
4. [Project Reactor 3.7 — Flux Javadoc](https://projectreactor.io/docs/core/3.7.17/api/reactor/core/publisher/Flux.html): onBackpressureBuffer, onBackpressureDrop, onBackpressureLatest, onBackpressureError và limitRate.
5. [Project Reactor — FluxSink Javadoc](https://projectreactor.io/docs/core/3.7.10/api/reactor/core/publisher/FluxSink.html): onRequest, onCancel, onDispose và requestedFromDownstream.
6. [Project Reactor — Sinks.EmitResult Javadoc](https://projectreactor.io/docs/core/3.7.12/api/reactor/core/publisher/Sinks.EmitResult.html): OK, FAIL_OVERFLOW, FAIL_NON_SERIALIZED, FAIL_ZERO_SUBSCRIBER, FAIL_CANCELLED và FAIL_TERMINATED.
7. [Reactive Streams Specification](https://www.reactive-streams.org/): Publisher/Subscriber/Subscription, request(n), cancellation và signal rules.
8. [Spring Framework 6.2 — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): tích hợp Publisher trong WebFlux và reactive request handling.
