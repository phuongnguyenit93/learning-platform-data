# Phân phối một nguồn tới nhiều bên nhận với bộ đệm có giới hạn

Một hệ thống realtime thường có một nguồn dữ liệu nhưng nhiều bên cùng cần nhận dữ liệu đó. Ví dụ, dịch vụ thu thập nhiệt độ từ thiết bị rồi phân phối tới dashboard, dịch vụ cảnh báo và bộ ghi lịch sử. Mỗi bên nhận có tốc độ xử lý khác nhau: dashboard có thể cập nhật chậm, bộ ghi lịch sử có thể ghi theo batch, còn dịch vụ cảnh báo cần phản ứng nhanh.

Nếu mỗi bên nhận tự subscribe vào một nguồn cold publisher, nguồn có thể chạy nhiều lần và tạo ra nhiều kết nối hoặc nhiều truy vấn giống nhau. Nếu broadcast mà không kiểm soát tốc độ, bên nhận chậm có thể làm hàng đợi tăng vô hạn. Thiết kế fan-out tốt cần dùng một subscription nguồn chung, xác định cách phối hợp demand và đặt giới hạn rõ ràng cho mọi buffer.

## 1. Bài toán fan-out một nguồn tới nhiều subscriber

Giả sử một `Flux<SensorReading>` phát dữ liệu cảm biến. Ta muốn nhiều subscriber cùng nhận mỗi reading:

```text
                    Sensor source
                         |
                         | một subscription nguồn
                         v
                  Shared publisher
                    /     |      \
                   /      |       \
                  v       v        v
             Dashboard  Alert   History writer
               chậm     nhanh      theo batch
```

Ví dụ các bên cùng nhận kiểu dữ liệu sau:

```java
public record SensorReading(
        String sensorId,
        String tenantId,
        Instant measuredAt,
        double value
) {}
```

Fan-out có ba yêu cầu:

1. **Một nguồn dùng chung:** không gọi lại thiết bị, database hoặc upstream service cho từng subscriber.
2. **Điều tiết tốc độ:** subscriber có demand riêng; nguồn và các nhánh phải phối hợp khi có bên nhận chậm.
3. **Giới hạn bộ nhớ:** queue có dung lượng hữu hạn và có chính sách khi đầy, ví dụ backpressure, drop, báo lỗi hoặc ngắt subscriber chậm.

Fan-out là broadcast: mỗi subscriber đang hoạt động nhận cùng một phần tử nguồn. Nó khác mô hình competing consumers, trong đó mỗi phần tử chỉ được giao cho một worker trong nhóm để chia tải. Nếu mục tiêu là phân phối công việc, hãy dùng queue hoặc broker có semantics consumer group; không dùng multicast rồi kỳ vọng Reactor tự chia mỗi phần tử cho một subscriber.

Reactive Streams biểu diễn khả năng nhận dữ liệu qua `request(n)`. Subscriber yêu cầu thêm phần tử khi có khả năng xử lý. Fan-out cần quyết định cách tổng hợp demand của nhiều subscriber để không tích lũy dữ liệu vô hạn.

## 2. Vì sao subscribe trực tiếp nhiều lần có thể sai?

Một cold publisher thường thực thi công việc mới cho mỗi lần subscribe. Ví dụ:

```java
Flux<SensorReading> source = sensorGateway.readings();

source.subscribe(dashboard::update);
source.subscribe(alertService::evaluate);
source.subscribe(historyRepository::save);
```

Nếu `sensorGateway.readings()` là cold publisher, ba lần subscribe có thể tạo ba luồng đọc độc lập. Thiết bị có thể bị polling ba lần, database có thể bị truy vấn ba lần hoặc upstream service có thể tạo ba kết nối.

Để một nguồn được đọc một lần và phân phối cho nhiều subscriber, cần biến nguồn thành luồng multicast dùng chung. Trong Reactor, `publish()` tạo `ConnectableFlux`; `refCount()` hoặc `autoConnect()` quản lý thời điểm kết nối tới upstream.

## 3. Chia sẻ một subscription bằng publish(prefetch)

`publish(prefetch)` tạo một luồng multicast có buffer/prefetch hữu hạn. Reactor điều phối demand của các subscriber: nếu một subscriber không còn demand (`request` chưa được gọi hoặc demand bằng 0), multicast tạm dừng việc kéo dữ liệu từ upstream. Khi subscriber yêu cầu thêm, luồng có thể tiếp tục.

Ví dụ chia sẻ nguồn và tự kết nối khi subscriber đầu tiên xuất hiện:

```java
Flux<SensorReading> sharedReadings = sensorGateway.readings()
        .publish(128)
        .refCount(1);
```

Sau đó nhiều thành phần có thể subscribe vào cùng publisher:

```java
sharedReadings.subscribe(dashboard::update);
sharedReadings.subscribe(alertService::evaluate);
sharedReadings.subscribe(historyWriter::append);
```

Trong vòng đời kết nối hiện tại, upstream chỉ được subscribe một lần và các subscriber nhận cùng chuỗi reading. `refCount(1)` bắt đầu kết nối khi có ít nhất một subscriber và ngắt upstream khi tất cả subscriber đã hủy. Khi có subscriber mới sau khi upstream đã bị ngắt, Reactor có thể tạo một subscription nguồn mới.

Đây là ví dụ rút gọn với callback tiêu thụ đồng bộ. Nếu `historyWriter.append` là thao tác reactive trả về `Mono` hoặc `Flux`, hãy nối nó vào nhánh bằng `flatMap` với concurrency hữu hạn thay vì bỏ qua publisher trả về. `share()` là cách viết ngắn cho mô hình chia sẻ `publish().refCount(1)` khi không cần chỉ định prefetch tường minh.

`prefetch` là số phần tử được yêu cầu trước từ upstream. Chọn giá trị vừa đủ để hấp thụ dao động ngắn của tốc độ xử lý. Giá trị lớn làm tăng bộ nhớ và lượng dữ liệu có thể đang chờ; giá trị nhỏ làm upstream bị dừng thường xuyên hơn.

### 3.1. Khi cần chờ đủ subscriber trước khi phát

Nếu muốn dashboard, alert service và history writer đều đăng ký xong trước khi nguồn bắt đầu, có thể điều khiển `ConnectableFlux` thủ công:

```java
ConnectableFlux<SensorReading> shared = sensorGateway.readings()
        .publish(128);

Disposable dashboard = shared.subscribe(dashboardService::update);
Disposable alerts = shared.subscribe(alertService::evaluate);
Disposable history = shared.subscribe(historyWriter::append);

Disposable upstreamConnection = shared.connect();
```

Gọi `connect()` sau khi đã đăng ký các subscriber cần thiết. Giữ `Disposable` trả về để chủ động ngắt subscription nguồn khi module hoặc phiên làm việc kết thúc. Nếu cần tự kết nối sau khi đủ một số subscriber, có thể dùng `autoConnect(n)`; khác với `refCount`, `autoConnect` không tự ngắt upstream khi subscriber rời đi.

### 3.2. Subscriber đến muộn

`publish().refCount(1)` là multicast trực tiếp: subscriber mới nhận các phần tử được phát sau khi nó đăng ký. Nó không tự nhận lại toàn bộ lịch sử đã phát trước đó.

Nếu cần gửi trạng thái gần nhất cho subscriber mới, dùng replay có giới hạn:

```java
Flux<SensorReading> latestReadings = sensorGateway.readings()
        .replay(1)
        .refCount(1);
```

`replay(1)` giữ tối đa một phần tử gần nhất để phát lại cho subscriber mới. Có thể dùng `replay(n)` hoặc cửa sổ thời gian nếu nghiệp vụ cần lịch sử ngắn. Tránh replay không giới hạn cho stream dài vì bộ nhớ sẽ tăng theo thời gian.

## 4. Slow subscriber ảnh hưởng đến fan-out ra sao?

Với `publish(prefetch)`, Reactor phối hợp demand theo subscriber chậm nhất. Đây là lựa chọn phù hợp khi:

- Không được phép bỏ mất reading.
- Upstream có thể tuân thủ backpressure.
- Việc một bên nhận chậm tạm thời làm chậm các bên còn lại là chấp nhận được.

Ví dụ, dashboard không yêu cầu thêm dữ liệu trong một khoảng thời gian. Khi demand của dashboard về 0, `publish` tạm dừng kéo dữ liệu. Buffer prefetch có giới hạn sẽ hấp thụ phần dữ liệu đang đến; sau khi hết khả năng chứa, backpressure truyền ngược về upstream.

```text
Dashboard demand = 0
        |
        v
Shared publish tạm dừng pull upstream
        |
        v
Prefetch buffer có giới hạn dần đầy
        |
        v
Upstream nhận backpressure
        |
        v
Dashboard request thêm -> luồng tiếp tục
```

Đây là cơ chế lossless nếu toàn bộ nguồn và transport tuân thủ backpressure. Nếu nguồn là callback từ thiết bị, UDP feed hoặc API không thể dừng phát, adapter ở biên vẫn cần queue có giới hạn và chính sách overflow riêng.

## 5. Ba kiểu đặt buffer thường gặp

Không có một buffer duy nhất phù hợp cho mọi fan-out. Vị trí đặt buffer quyết định ai bị ảnh hưởng khi subscriber chậm.

| Mô hình | Buffer nằm ở đâu? | Khi một subscriber chậm |
| --- | --- | --- |
| `publish(prefetch)` | Một buffer multicast chung | Demand thấp nhất điều khiển upstream; mọi nhánh có thể chậm theo |
| `Sinks.many().multicast().onBackpressureBuffer(capacity)` | Buffer multicast chung của sink | Buffer phục vụ demand thấp nhất; overflow được báo cho producer |
| Buffer sau từng nhánh subscriber | Một queue riêng cho mỗi subscriber | Nhánh chậm có thể overflow và kết thúc riêng; nhánh khác tiếp tục |

Hãy chọn mô hình dựa trên ý nghĩa dữ liệu. Với giao dịch hoặc lệnh điều khiển cần mọi bên nhận cùng chuỗi sự kiện, có thể chọn backpressure chung hoặc lưu bền. Với telemetry có thể chấp nhận mất một số mẫu, có thể cô lập subscriber chậm bằng queue riêng và drop/disconnect khi đầy.

## 6. Dùng multicast Sink với buffer giới hạn

Khi nguồn dữ liệu được đẩy vào từ callback hoặc một thành phần imperative, `Sinks.Many` cung cấp API để phát dữ liệu an toàn tới nhiều subscriber.

```java
Sinks.Many<SensorReading> readings = Sinks.many()
        .multicast()
        .onBackpressureBuffer(256, true);

Flux<SensorReading> broadcast = readings.asFlux();
```

Các subscriber đăng ký vào cùng một `Flux` view:

```java
Disposable dashboard = broadcast.subscribe(dashboardService::update);
Disposable alerts = broadcast.subscribe(alertService::evaluate);
Disposable history = broadcast.subscribe(historyWriter::append);
```

Producer phát dữ liệu bằng `tryEmitNext` và phải kiểm tra kết quả:

```java
void publishReading(SensorReading reading) {
    Sinks.EmitResult result = readings.tryEmitNext(reading);

    if (result.isFailure()) {
        handleEmitFailure(reading, result);
    }
}
```

Với `onBackpressureBuffer(256, true)`:

- Sink hỗ trợ nhiều subscriber và giữ buffer tối đa 256 phần tử.
- Demand được điều phối theo subscriber có demand thấp nhất.
- Nếu chênh lệch giữa subscriber nhanh và chậm vượt sức chứa, `tryEmitNext` trả `FAIL_OVERFLOW`.
- Tham số `autoCancel = true` yêu cầu sink tự đóng khi subscriber cuối cùng hủy.
- Subscriber mới chỉ nhận dữ liệu phát sau khi nó đăng ký, cùng các phần tử còn nằm trong buffer do backpressure hoặc warm-up; sink không replay toàn bộ lịch sử cũ.

Không bỏ qua `EmitResult`. Nếu producer cứ tiếp tục phát mà không xử lý `FAIL_OVERFLOW`, dữ liệu có thể mất hoặc sink có thể đi vào trạng thái lỗi tùy API được gọi. Với `emitNext`, lỗi overflow có thể kết thúc sink bằng overflow error. `tryEmitNext` giúp ứng dụng chủ động quyết định cách xử lý.

Ví dụ xử lý kết quả emit:

```java
private void handleEmitFailure(
        SensorReading reading,
        Sinks.EmitResult result) {

    switch (result) {
        case FAIL_OVERFLOW -> {
            metrics.counter("sensor.fanout.overflow").increment();
            overflowStore.record(reading);
        }
        case FAIL_NON_SERIALIZED -> {
            // Có nhiều producer gọi đồng thời; chuyển qua một hàng đợi
            // hoặc serialize các lần emit.
            producerQueue.offer(reading);
        }
        case FAIL_ZERO_SUBSCRIBER -> {
            // Chưa có subscriber: quyết định có lưu, bỏ hay chờ subscriber.
            metrics.counter("sensor.fanout.no_subscriber").increment();
        }
        default -> log.warn("Không thể phát reading: {}", result);
    }
}
```

Các trường hợp `EmitResult` phụ thuộc trạng thái sink và phiên bản Reactor. Trong ứng dụng thực tế, hãy xử lý đầy đủ các giá trị mà phiên bản đang dùng cung cấp. Nếu nhiều thread phát vào cùng sink, các sink mặc định phát hiện concurrent emission; hãy serialize producer hoặc xử lý `FAIL_NON_SERIALIZED` thay vì gọi lại vô hạn trong vòng lặp bận.

`Sinks.Many` là bộ phát trong bộ nhớ. Nó không phải durable queue và không đảm bảo dữ liệu tồn tại sau khi process khởi động lại.

## 7. Tạo buffer riêng cho từng subscriber

Buffer multicast chung khiến subscriber chậm nhất ảnh hưởng tới cả nhóm. Nếu cần cô lập từng client, có thể đặt một `onBackpressureBuffer` riêng sau publisher đã được chia sẻ.

Ví dụ xây dựng một nguồn dùng chung rồi tạo nhánh riêng cho mỗi client:

```java
@Component
public class SensorFanout {

    private final Flux<SensorReading> sharedReadings;
    private final MeterRegistry metrics;

    public SensorFanout(SensorGateway gateway, MeterRegistry metrics) {
        this.metrics = metrics;
        this.sharedReadings = gateway.readings()
                .publish(128)
                .refCount(1);
    }

    public Flux<SensorReading> streamForClient() {
        return sharedReadings.onBackpressureBuffer(
                64,
                reading -> metrics.counter("sensor.client.buffer.overflow").increment()
        );
    }
}
```

Mỗi lần `streamForClient()` được gọi, nó tạo một nhánh với buffer riêng có tối đa 64 phần tử. Khi RSocket client không yêu cầu dữ liệu đủ nhanh, nhánh giữ dữ liệu trong queue của nó. Nếu queue đầy, callback overflow được gọi, nhánh bị hủy ở upstream và kết thúc bằng overflow error. Các nhánh khác vẫn có thể tiếp tục nhận dữ liệu từ publisher chung.

Nếu mỗi client chỉ được xem một tập reading nhất định, hãy lọc theo principal/tenant đã xác thực ở nhánh riêng trước khi trả publisher. Không đặt filter phụ thuộc người dùng trước `publish`, vì kết quả đã lọc có thể bị chia sẻ sang subscriber khác.

```java
public Flux<SensorReading> streamForTenant(String authorizedTenantId) {
    return sharedReadings
            .filter(reading -> reading.tenantId().equals(authorizedTenantId))
            .onBackpressureBuffer(64,
                    ignored -> metrics.counter("sensor.client.buffer.overflow").increment());
}
```

`authorizedTenantId` phải lấy từ security context đã xác thực và phân quyền ở server, không lấy trực tiếp từ một query parameter hoặc metadata chưa kiểm chứng của client.

Điều này có hai hệ quả:

- Một client chậm không bắt buộc làm chậm mọi client khác.
- Khi buffer của client đầy, client đó phải được thông báo, ngắt hoặc kết nối lại theo chính sách. `onBackpressureBuffer(64, callback)` không âm thầm bỏ phần tử rồi tiếp tục; overload này báo overflow và kết thúc nhánh.

Nếu muốn drop thay vì kết thúc nhánh, dùng `onBackpressureDrop` hoặc `onBackpressureLatest` cho từng nhánh. Cần ghi metric về số phần tử bị bỏ để biết client nào thường xuyên không theo kịp.

## 8. Phân phối cùng nguồn qua RSocket request-stream

Spring RSocket có thể trả một `Flux` từ `@MessageMapping`. Mỗi client mở route `sensors.live` sẽ tạo một subscription tới nhánh của publisher dùng chung:

```java
@Controller
public class SensorStreamController {

    private final SensorFanout fanout;

    public SensorStreamController(SensorFanout fanout) {
        this.fanout = fanout;
    }

    @MessageMapping("sensors.live")
    public Flux<SensorReading> live() {
        return fanout.streamForClient();
    }
}
```

Client nhận luồng bằng request-stream:

```java
Flux<SensorReading> readings = requester
        .route("sensors.live")
        .retrieveFlux(SensorReading.class);
```

Khi nhiều client subscribe, tất cả nhánh đều đọc từ `sharedReadings`, vì vậy `SensorGateway` chỉ có một upstream subscription trong thời gian `refCount` đang kết nối. RSocket flow control truyền demand từ từng client về stream tương ứng. Queue riêng ở server hấp thụ chênh lệch ngắn; nếu client quá chậm và queue đầy, chỉ stream đó kết thúc theo chính sách overflow.

Không tạo một `SensorGateway.readings()` mới trong từng lần gọi handler rồi subscribe riêng. Cách đó có thể mở một nguồn cho mỗi client và làm mất mục tiêu phân phối một nguồn tới nhiều bên nhận.

## 9. Chọn chính sách khi buffer đầy

Buffer giới hạn chỉ giải quyết việc giữ dữ liệu trong một khoảng ngắn. Khi tốc độ đầu vào tiếp tục cao hơn tốc độ tiêu thụ, buffer chắc chắn sẽ đầy. Ứng dụng phải chọn hành vi khi đó.

| Chính sách | Hành vi | Phù hợp khi |
| --- | --- | --- |
| Backpressure | Dừng yêu cầu upstream cho tới khi có demand | Upstream có thể chậm lại và không được mất dữ liệu |
| Buffer rồi error | Giữ tối đa N phần tử, sau đó kết thúc nhánh hoặc báo lỗi | Muốn phát hiện client không theo kịp và yêu cầu reconnect |
| Drop | Bỏ phần tử mới khi consumer chậm | Một số mẫu telemetry có thể mất |
| Latest | Chỉ giữ giá trị mới nhất, bỏ dữ liệu cũ | Dashboard chỉ cần trạng thái hiện tại |
| Disconnect slow consumer | Ngắt client vượt ngưỡng và giải phóng queue | Bảo vệ hệ thống trước client chậm kéo dài |
| Durable queue | Ghi dữ liệu vào kho bền và consumer đọc lại sau | Không được mất sự kiện và cần replay sau reconnect |

Reactor có các lựa chọn multicast không dùng buffer:

- `directAllOrNothing()`: nếu bất kỳ subscriber nào không có demand, phần tử bị bỏ cho tất cả subscriber.
- `directBestEffort()`: subscriber có demand vẫn nhận; subscriber chậm bị bỏ qua phần tử đó.

Hai lựa chọn này không giữ hàng đợi để bù lại phần tử đã bỏ. Chỉ dùng khi nghiệp vụ chấp nhận mất dữ liệu.

## 10. Tính dung lượng buffer và ngân sách bộ nhớ

Đừng chọn capacity chỉ bằng cảm tính. Hãy ước tính tốc độ đầu vào, thời gian chậm tối đa cần hấp thụ và kích thước phần tử.

Một ước lượng đơn giản:

```text
capacity ≈ arrival_rate × tolerated_lag
```

Ví dụ nguồn phát 200 reading/giây và muốn hấp thụ độ trễ 0,5 giây:

```text
capacity ≈ 200 × 0,5 = 100 reading
```

Với buffer riêng cho mỗi client:

```text
memory ≈ client_count × buffer_capacity × average_event_size
```

Ví dụ 500 client, mỗi client có queue 64 reading, kích thước trung bình 1 KB:

```text
500 × 64 × 1 KB ≈ 32 MB payload data
```

Con số thực tế còn có object overhead, reference, queue node, codec buffer, network buffer và dữ liệu đang xử lý. Vì vậy cần đo heap và direct memory dưới tải thật. Nếu payload có kích thước biến động lớn, giới hạn số phần tử chưa đủ; cần giới hạn cả kích thước từng payload hoặc tổng byte được giữ.

Khi tính ngân sách, cộng tất cả các tầng queue: prefetch của `publish`, buffer riêng từng subscriber, queue của transport, queue ở adapter nguồn và queue trong service downstream. Một buffer 64 phần tử ở mỗi tầng không có nghĩa tổng hệ thống chỉ giữ 64 phần tử.

## 11. Theo dõi subscriber chậm và vận hành

Fan-out production cần quan sát tình trạng của từng nhánh:

- Số subscriber đang hoạt động và số lần subscribe/cancel.
- Queue depth hoặc số lần overflow trên từng nhánh.
- Số phần tử bị drop hoặc latest replacement.
- Độ trễ từ lúc nguồn phát tới lúc client nhận.
- Số lần reconnect sau overflow hoặc network disconnect.
- Tốc độ phát nguồn so với tốc độ tiêu thụ của từng nhóm client.

Gắn client ID hoặc tenant ID vào metric/log một cách có kiểm soát. Tránh dùng ID có cardinality quá lớn làm tag metric nếu hệ thống metrics không hỗ trợ. Có thể log chi tiết theo client và dùng metric tổng hợp theo nhóm.

Khi overflow xảy ra, đừng chỉ tăng capacity liên tục. Trước hết xác định client có thực sự cần nhận mọi sự kiện không, upstream có thể backpressure không và liệu queue đang che giấu một consumer lỗi kéo dài hay không.

## 12. Vòng đời subscriber và xử lý không có người nhận

`refCount(1)` kết nối nguồn khi subscriber đầu tiên xuất hiện và ngắt nguồn khi subscriber cuối cùng hủy. Cách này tiết kiệm tài nguyên khi không có client theo dõi.

Nếu nguồn cần luôn chạy dù không có subscriber, có thể dùng `autoConnect(1)` hoặc quản lý `connect()` theo lifecycle của ứng dụng. Khi đó cần xác định dữ liệu phát ra lúc không có subscriber sẽ bị bỏ, được buffer hay được lưu bền ở nơi khác.

Với `Sinks.many().multicast().onBackpressureBuffer`, sink có thể warm-up và giữ một số phần tử trước subscriber đầu tiên. Nó không replay toàn bộ lịch sử sau khi subscriber đã rời đi. Tham số `autoCancel` quyết định sink có đóng hẳn khi subscriber cuối cùng hủy hay không.

Nếu cần trạng thái mới nhất cho client vừa kết nối, dùng replay giới hạn như `replay(1)`. Nếu cần client offline nhiều phút rồi nhận lại toàn bộ sự kiện chưa xử lý, dùng durable log/message broker hoặc database outbox; không dùng replay không giới hạn trong RAM.

## 13. Kiểm thử fan-out và overflow

Kiểm thử nên xác nhận một nguồn chỉ được subscribe một lần, nhiều subscriber nhận cùng sự kiện và buffer không vượt capacity.

Ví dụ xác nhận hai subscriber cùng nhận dữ liệu từ một lần subscribe nguồn:

```java
@Test
void subscribersShareOneUpstreamSubscription() {
    AtomicInteger upstreamSubscriptions = new AtomicInteger();
    List<Integer> first = new ArrayList<>();
    List<Integer> second = new ArrayList<>();

    Flux<Integer> shared = Flux.range(1, 3)
            .doOnSubscribe(ignored -> upstreamSubscriptions.incrementAndGet())
            .publish(8)
            .autoConnect(2);

    shared.subscribe(first::add);
    shared.subscribe(second::add);

    assertThat(upstreamSubscriptions).hasValue(1);
    assertThat(first).containsExactly(1, 2, 3);
    assertThat(second).containsExactly(1, 2, 3);
}
```

`autoConnect(2)` đợi subscriber thứ hai rồi mới kết nối nguồn. Vì nguồn `Flux.range` phát đồng bộ trong ví dụ, cả hai list đều được điền trước khi các assertion chạy.

Ví dụ kiểm tra buffer multicast có giới hạn:

```java
@Test
void multicastBufferReportsOverflow() {
    Sinks.Many<Integer> hub = Sinks.many()
            .multicast()
            .onBackpressureBuffer(2, true);

    StepVerifier.create(hub.asFlux(), 0)
            .then(() -> {
                assertThat(hub.tryEmitNext(1)).isEqualTo(Sinks.EmitResult.OK);
                assertThat(hub.tryEmitNext(2)).isEqualTo(Sinks.EmitResult.OK);
                assertThat(hub.tryEmitNext(3))
                        .isEqualTo(Sinks.EmitResult.FAIL_OVERFLOW);
            })
            .thenRequest(2)
            .expectNext(1, 2)
            .thenCancel()
            .verify();
}
```

Test bắt đầu với demand bằng 0, phát hai phần tử vào buffer có capacity 2 và xác nhận phần tử thứ ba bị từ chối với `FAIL_OVERFLOW`. Sau đó subscriber yêu cầu hai phần tử và nhận đúng dữ liệu đã buffer.

Các bài test khác nên bao gồm:

1. Hai subscriber đăng ký trước khi nguồn kết nối; xác nhận cả hai nhận cùng một chuỗi và upstream chỉ có một lần subscribe.
2. Một subscriber chậm, một subscriber nhanh; xác nhận chính sách chung hoặc queue riêng hoạt động đúng như thiết kế.
3. Buffer riêng của một client đầy; stream client đó kết thúc, các client còn lại vẫn nhận dữ liệu.
4. Tất cả subscriber cancel; xác nhận `refCount` ngắt upstream hoặc sink autoCancel theo cấu hình.
5. Subscriber đến muộn; xác nhận chỉ nhận dữ liệu mới hoặc nhận số phần tử replay đúng giới hạn.
6. Nguồn phát nhanh hơn consumer; xác nhận queue depth không vượt capacity và overflow/drop metric tăng đúng.
7. Nguồn phát lỗi hoặc hoàn tất; mọi nhánh nhận terminal signal và giải phóng tài nguyên.

Không dùng `Thread.sleep` để kiểm tra buffer. Dùng `StepVerifier`, `TestPublisher`, `Sinks.Many` và `PublisherProbe` để điều khiển demand và xác minh số lần subscribe.

## 14. Những lỗi thiết kế thường gặp

**Subscribe nguồn riêng cho từng client.** Điều này tạo nhiều upstream subscription, lặp công việc và có thể tạo tải lớn hơn số client.

**Dùng `share()` mà không hiểu slowest subscriber.** Multicast có phối hợp demand; một subscriber không yêu cầu thêm có thể làm upstream dừng.

**Dùng buffer không giới hạn.** Khi consumer chậm kéo dài, bộ nhớ tăng theo thời gian và có thể làm process hết heap.

**Đặt buffer trước fan-out nhưng nghĩ nó cô lập từng client.** Buffer chung hấp thụ cho cả nhóm; demand thấp nhất vẫn chi phối.

**Bỏ qua `FAIL_OVERFLOW`.** Producer không biết dữ liệu bị từ chối và hệ thống có thể mất sự kiện mà không có metric hoặc cảnh báo.

**Dùng `directBestEffort` cho dữ liệu bắt buộc đầy đủ.** Subscriber chậm sẽ mất phần tử; cơ chế này chỉ phù hợp với dữ liệu có thể bỏ.

**Replay không giới hạn.** Subscriber đến muộn có thể khiến toàn bộ lịch sử bị giữ trong bộ nhớ vô thời hạn.

**Chỉ giới hạn số phần tử.** Một phần tử có thể chứa payload rất lớn; cần giới hạn kích thước từng message và tổng byte.

## 15. Checklist triển khai

- [ ] Tạo một publisher nguồn dùng chung và xác nhận chỉ có một upstream subscription.
- [ ] Chọn `publish(prefetch).refCount(...)`, `autoConnect(...)` hoặc `Sinks.Many` theo lifecycle mong muốn.
- [ ] Xác định subscriber chậm sẽ backpressure toàn nhóm hay có queue riêng.
- [ ] Đặt capacity hữu hạn cho prefetch và từng queue subscriber.
- [ ] Chọn chính sách overflow rõ ràng: error, drop, latest, disconnect hoặc lưu bền.
- [ ] Kiểm tra kết quả `Sinks.EmitResult` khi phát thủ công.
- [ ] Xác định subscriber đến muộn có cần replay không và giới hạn lịch sử.
- [ ] Giới hạn kích thước payload và tổng bộ nhớ của mọi queue.
- [ ] Quản lý cancel, reconnect và trường hợp không có subscriber.
- [ ] Theo dõi queue depth, overflow, drop, latency và số subscriber.
- [ ] Kiểm thử một nguồn nhiều subscriber, slow consumer, overflow và upstream cancellation.

Phân phối một nguồn tới nhiều bên nhận hiệu quả khi upstream chỉ được subscribe một lần, demand được phối hợp đúng và mọi buffer đều có giới hạn. `publish(prefetch)` phù hợp khi muốn backpressure chung; multicast sink phù hợp khi cần chủ động phát sự kiện; buffer riêng từng nhánh phù hợp khi muốn cô lập client chậm. Hãy chọn chính sách theo mức độ mất dữ liệu mà nghiệp vụ cho phép và kiểm thử hành vi khi buffer đầy trước khi đưa hệ thống vào tải thực tế.

## Tài liệu tham khảo

- [Project Reactor — Broadcasting to Multiple Subscribers with ConnectableFlux](https://projectreactor.io/docs/core/3.6.7/reference/html/#advanced.broadcasting)
- [Project Reactor — Sinks](https://projectreactor.io/docs/core/3.6.7/reference/html/#sinks)
- [Reactor `Flux.publish(int prefetch)` API](https://projectreactor.io/docs/core/3.6.16/api/reactor/core/publisher/Flux.html)
- [Reactor `Sinks.MulticastSpec` API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.MulticastSpec.html)
- [Reactor `Flux.onBackpressureBuffer` API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
