# Đóng nguồn dữ liệu khi không còn bên nhận và tránh đăng ký bị bỏ quên

Một luồng RSocket có thể phát dữ liệu liên tục trong thời gian dài: telemetry, trạng thái thiết bị, thông báo hoặc sự kiện nghiệp vụ. Khi client hủy subscription hoặc ngắt kết nối, server cần truyền tín hiệu hủy ngược về nguồn dữ liệu và giải phóng listener, cursor, socket hoặc tài nguyên đang mở. Nếu nguồn vẫn chạy sau khi không còn subscriber, ứng dụng sẽ tiêu tốn CPU, bộ nhớ, kết nối và có thể tiếp tục tạo dữ liệu không ai nhận.

Trong Project Reactor, vòng đời này được quản lý bằng subscription và cancellation. Các operator như **share() / refCount()** điều khiển nguồn dùng chung theo số subscriber; **using** và **usingWhen** gắn tài nguyên với vòng đời một subscription; **doFinally** quan sát kết thúc do complete, error hoặc cancel. Ở tầng Spring RSocket, handler nên trả về Flux để framework quản lý subscription và cancellation thay vì tự gọi subscribe() rồi bỏ quên Disposable.

Bài học này tập trung vào việc đóng nguồn khi không còn bên nhận, chia sẻ nguồn cho nhiều RSocket client và quản lý những subscription có chủ đích để tránh rò rỉ tài nguyên.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt cold publisher, hot publisher và subscription.
- Giải thích cancellation từ RSocket request-stream truyền về publisher như thế nào.
- Dùng share() và refCount() để ngắt upstream khi subscriber cuối cùng rời đi.
- Phân biệt refCount() với autoConnect() và kết nối thủ công.
- Gắn vòng đời resource vào subscription bằng using hoặc usingWhen.
- Dùng doFinally để quan sát complete, error và cancel.
- Viết adapter cho API listener để đóng đăng ký khi subscription kết thúc.
- Tránh gọi subscribe() bên trong service hoặc RSocket handler mà không quản lý Disposable.
- Kiểm thử việc giải phóng nguồn khi một hoặc tất cả subscriber hủy.

## 1. Subscription quyết định vòng đời luồng dữ liệu

Flux mô tả một nguồn có thể phát từ 0 đến nhiều phần tử. Khi tạo Flux, thông thường ứng dụng mới chỉ mô tả pipeline; nguồn chỉ bắt đầu hoạt động khi có subscriber đăng ký.

Một subscription có vòng đời gồm:

1. Subscriber đăng ký với publisher.
2. Publisher phát dữ liệu theo demand.
3. Subscriber có thể tiếp tục nhận dữ liệu, hoặc hủy subscription.
4. Publisher hoàn tất, phát lỗi hoặc nhận cancellation.
5. Tài nguyên gắn với subscription được giải phóng.

~~~mermaid
flowchart TD
    A["Tạo Flux pipeline"] --> B["Subscriber đăng ký"]
    B --> C["Nguồn bắt đầu phát dữ liệu"]
    C --> D{"Subscription còn hoạt động?"}
    D -- Có --> E["Phát dữ liệu theo demand"]
    E --> D
    D -- Hủy --> F["Cancellation truyền lên upstream"]
    D -- Complete / Error --> G["Tín hiệu kết thúc"]
    F --> H["Đóng listener / cursor / socket"]
    G --> H
~~~

Một nguồn dữ liệu được thiết kế đúng phải phản ứng với cancellation. Nếu nguồn tạo listener bên ngoài, publisher cần có logic gỡ listener. Nếu nguồn mở cursor hoặc kết nối, publisher cần đóng chúng khi subscription kết thúc.

### 1.1. Cold publisher

Cold publisher tạo công việc hoặc tài nguyên riêng cho từng subscriber. Ví dụ:

~~~java
Flux<DeviceEvent> events(String deviceId) {
    return Flux.defer(() ->
            repository.watchEvents(deviceId));
}
~~~

Mỗi lần subscribe vào events(deviceId), lambda trong defer được chạy để tạo publisher cho subscriber đó. Nếu repository.watchEvents mở cursor hoặc đăng ký listener, nó phải đóng tài nguyên khi subscriber cancel hoặc luồng kết thúc.

Các ví dụ cold source thường gặp:

- Mono.fromCallable(...) thực hiện công việc khi subscribe.
- Flux.defer(...) tạo publisher mới cho mỗi subscriber.
- Flux.interval(...) tạo lịch phát riêng theo subscription.
- Query hoặc cursor reactive có vòng đời gắn với subscription.

### 1.2. Hot publisher

Hot publisher có thể phát dữ liệu độc lập với từng subscriber. Ví dụ một adapter đang lắng nghe thiết bị hoặc một Sinks.Many nhận event từ callback bên ngoài.

Nếu không có subscriber, producer vẫn có thể chạy. Điều đó không tự động sai: một số producer là dịch vụ nền có chủ đích. Nhưng nếu nguồn chỉ tồn tại để phục vụ người đang xem stream, cần chính sách dừng producer khi subscriber cuối cùng rời đi.

### 1.3. Nhiều subscriber và một nguồn upstream

Khi nhiều client cùng theo dõi một thiết bị, có thể muốn chia sẻ một listener đến thiết bị thay vì mở một listener cho từng client:

~~~text
RSocket client A ----\
RSocket client B -----+--> shared Flux --> một device listener
RSocket client C ----/
~~~

Mỗi client có subscription riêng. Hủy subscription của client A chỉ loại A khỏi nhóm nhận dữ liệu. Nguồn upstream chỉ nên đóng khi không còn client B hoặc C nào đăng ký.

## 2. Cancellation từ RSocket đến Reactor

Với request-stream và request-channel, RSocket áp dụng Reactive Streams semantics qua ranh giới mạng. Requester gửi demand để responder biết số phần tử có thể phát; khi requester hủy interaction, RSocket gửi tín hiệu CANCEL cho interaction đó. Phía responder cần truyền cancellation vào publisher đang xử lý request.

Trong Spring Messaging, một handler có thể trả về Flux:

~~~java
@Controller
public class TelemetryController {

    private final TelemetryService telemetryService;

    public TelemetryController(TelemetryService telemetryService) {
        this.telemetryService = telemetryService;
    }

    @MessageMapping("telemetry.stream")
    public Flux<TelemetryEvent> stream(DeviceQuery query) {
        return telemetryService.watch(query.deviceId());
    }
}
~~~

Spring/RSocket đăng ký publisher để xử lý interaction. Khi client cancel stream hoặc interaction kết thúc, cancellation có thể đi ngược vào pipeline của telemetryService.watch.

Client có thể hủy subscription trong ứng dụng:

~~~java
Disposable subscription = requester
        .route("telemetry.stream")
        .data(new DeviceQuery("sensor-17"))
        .retrieveFlux(TelemetryEvent.class)
        .subscribe(this::render, this::showError);

// Khi người dùng rời màn hình hoặc không còn cần dữ liệu:
subscription.dispose();
~~~

Trong code reactive thông thường, hãy compose Flux với pipeline của component thay vì subscribe thủ công. Ví dụ trên chỉ phù hợp khi component thật sự sở hữu subscription và lưu Disposable để hủy trong lifecycle của nó.

**Cancellation một stream không đồng nghĩa đóng toàn bộ RSocket connection.** Một connection có thể multiplex nhiều interaction. Hủy telemetry.stream thường chỉ hủy interaction đó; các request khác trên cùng connection vẫn có thể tiếp tục.

### 2.1. Cancellation phải được nguồn hỗ trợ

Cancellation chỉ có hiệu quả nếu các operator và adapter phía trên truyền tín hiệu đó đến công việc thực tế. Một publisher có thể nhận cancel nhưng một callback API bên ngoài vẫn tiếp tục nếu adapter không gỡ listener.

Ví dụ sai:

~~~java
Flux<DeviceEvent> watch(String deviceId) {
    Sinks.Many<DeviceEvent> sink =
            Sinks.many().multicast().onBackpressureBuffer();

    eventBus.events(deviceId).subscribe(sink::tryEmitNext);
    return sink.asFlux();
}
~~~

Lời gọi subscribe tạo một Disposable nhưng code không giữ handle đó và không liên kết nó với subscription của sink. Client hủy stream nhưng subscription đến eventBus vẫn tiếp tục chạy. Adapter cần giữ Disposable và dispose nó khi subscriber cuối cùng rời đi, hoặc dùng using/refCount để quản lý vòng đời.

Hãy gắn đăng ký listener vào subscription bằng using, usingWhen hoặc callback cleanup phù hợp.

## 3. Chia sẻ nguồn bằng share() và refCount()

Khi nhiều subscriber cần nhận cùng một nguồn, Reactor cung cấp ConnectableFlux, share() và refCount().

### 3.1. share()

share() là cách viết ngắn cho cơ chế chia sẻ có tham chiếu subscriber. Nguồn upstream được subscribe khi subscriber đầu tiên đăng ký và được cancel khi subscriber cuối cùng hủy:

~~~java
Flux<DeviceEvent> sharedEvents(String deviceId) {
    return Flux.defer(() -> deviceApi.watch(deviceId))
            .share();
}
~~~

share() phù hợp khi:

- Nhiều subscriber cần cùng một luồng sự kiện.
- Không cần phát lại các phần tử cũ cho subscriber đến sau.
- Muốn dừng upstream khi không còn subscriber.
- Subscriber cuối cùng rời đi trước khi nguồn terminal, sau đó một nhóm subscriber mới có thể tạo subscription upstream mới.

Nếu nguồn đã complete hoặc error, publisher dùng chung đã terminal; share() không biến nguồn hữu hạn đó thành nguồn tự khởi động lại. Nếu cần khởi động lại sau terminal, hãy định nghĩa retry/repeat hoặc tạo publisher mới theo lifecycle của ứng dụng.

Với nguồn tài nguyên bên ngoài, vẫn cần bảo đảm publisher trả về từ deviceApi.watch đóng listener khi bị cancel. share() điều khiển subscription; nó không tự biết cách đóng một callback API không hỗ trợ cancellation.

### 3.2. publish().refCount()

Có thể viết rõ ngưỡng subscriber:

~~~java
Flux<DeviceEvent> sharedEvents(String deviceId) {
    return Flux.defer(() -> deviceApi.watch(deviceId))
            .publish()
            .refCount(1);
}
~~~

refCount(1) kết nối upstream khi có ít nhất một subscriber và ngắt kết nối khi số subscriber còn lại giảm về 0. Dùng refCount(n) nếu nguồn chỉ nên khởi động sau khi có tối thiểu n subscriber.

### 3.3. Grace period khi subscriber rời đi

Client realtime có thể reconnect nhanh khi chuyển mạng hoặc khi giao diện chuyển màn hình. Nếu nguồn đắt để mở lại, có thể chờ một khoảng ngắn trước khi đóng:

~~~java
Flux<DeviceEvent> sharedEvents(String deviceId) {
    return Flux.defer(() -> deviceApi.watch(deviceId))
            .publish()
            .refCount(1, Duration.ofSeconds(3));
}
~~~

Khi subscriber cuối cùng hủy, Reactor chờ tối đa ba giây trước khi ngắt upstream. Nếu subscriber mới xuất hiện trong thời gian đó, việc ngắt kết nối được hủy. Grace period là một khoảng giữ tài nguyên có chủ đích; hãy chọn giá trị ngắn và đo số nguồn còn mở trong thời gian chờ.

### 3.4. Nhiều client: chỉ subscriber cuối cùng mới đóng nguồn

~~~mermaid
flowchart TD
    S["Một nguồn thiết bị"] --> F["Flux.share()"]
    F --> A["RSocket client A"]
    F --> B["RSocket client B"]
    F --> C["RSocket client C"]
    A --> X["A hủy subscription"]
    B --> Y["B vẫn nhận dữ liệu"]
    C --> Y
    Y --> Z["Nguồn vẫn hoạt động"]
    B --> Q["B và C đều hủy"]
    C --> Q
    Q --> R["RefCount = 0: cancel upstream"]
    R --> T["Đóng nguồn thiết bị"]
~~~

Không gọi close() nguồn ngay khi bất kỳ client nào rời đi. Nếu nguồn được chia sẻ, việc đóng phải dựa trên vòng đời upstream sau khi subscriber cuối cùng đã rời đi.

## 4. Phân biệt refCount, autoConnect và connect()

Các operator multicast có hành vi vòng đời khác nhau:

| Cách kết nối | Khi nào mở upstream? | Khi subscriber về 0 |
|---|---|---|
| share() | Subscriber đầu tiên | Cancel upstream |
| publish().refCount(1) | Đạt ít nhất 1 subscriber | Cancel upstream |
| publish().refCount(n) | Đạt ngưỡng n subscriber | Cancel khi số subscriber dưới ngưỡng |
| publish().autoConnect(n) | Đạt ngưỡng n subscriber | Không tự disconnect chỉ vì không còn subscriber |
| publish().connect() | Khi code gọi connect | Ứng dụng phải dispose connection |

Ví dụ autoConnect:

~~~java
Flux<DeviceEvent> feed = deviceApi.watch("sensor-17")
        .publish()
        .autoConnect(1);
~~~

Sau khi có subscriber đầu tiên, nguồn được kết nối. Khi mọi subscriber hủy, autoConnect không tự ngắt nguồn. Nó phù hợp với producer nền có chủ đích sống đến khi complete hoặc được quản lý ở nơi khác, nhưng không phù hợp nếu yêu cầu là đóng nguồn khi không còn người nhận.

Với kết nối thủ công:

~~~java
ConnectableFlux<DeviceEvent> connectable =
        deviceApi.watch("sensor-17").publish();

Disposable connection = connectable.connect();

// Khi component sở hữu nguồn dừng:
connection.dispose();
~~~

connect() trả về Disposable đại diện cho kết nối upstream. Component gọi connect() phải giữ handle đó và dispose khi dừng. Đừng để handle trong biến cục bộ rồi mất khả năng đóng nguồn.

## 5. Gắn resource vào subscription bằng using()

Nếu mỗi subscription cần mở một resource đồng bộ như listener registration, cursor hoặc handle, Flux.using đảm bảo cleanup khi nguồn complete, error hoặc subscriber cancel.

~~~java
Flux<DeviceEvent> watch(String deviceId) {
    return Flux.using(
            () -> deviceApi.openListener(deviceId),
            ListenerHandle::events,
            ListenerHandle::close);
}
~~~

Trong ví dụ:

- Supplier mở listener khi subscription bắt đầu.
- Function tạo Flux từ listener đó.
- Cleanup consumer đóng listener khi luồng kết thúc hoặc bị cancel.

using tạo resource theo từng subscription. Nếu muốn chia sẻ một listener cho nhiều subscriber, đặt using ở upstream rồi chia sẻ publisher bên ngoài:

~~~java
Flux<DeviceEvent> sharedWatch(String deviceId) {
    return Flux.defer(() ->
            Flux.using(
                    () -> deviceApi.openListener(deviceId),
                    ListenerHandle::events,
                    ListenerHandle::close))
            .share();
}
~~~

share() tạo một upstream subscription dùng chung. Vì vậy chỉ có một ListenerHandle cho nhóm subscriber hiện tại; khi nhóm đó không còn subscriber, cancellation đi vào using và listener được đóng.

## 6. Cleanup bất đồng bộ bằng usingWhen()

Một số tài nguyên cần đóng bất đồng bộ: consumer của message broker, cursor reactive, session đến dịch vụ ngoài hoặc stream handle có lệnh close trả về Mono<Void>.

Dùng Flux.usingWhen để khai báo cleanup riêng cho complete, error và cancel:

~~~java
Flux<TelemetryEvent> watch(String deviceId) {
    return Flux.usingWhen(
            telemetryClient.openStream(deviceId),
            StreamHandle::receive,
            StreamHandle::closeAsync,
            (handle, error) -> handle.abortAsync(error),
            StreamHandle::cancelAsync);
}
~~~

Các tham số có ý nghĩa:

| Callback | Khi nào chạy? | Ví dụ |
|---|---|---|
| Resource supplier | Khi subscribe và mở được resource | openStream(deviceId) |
| Resource closure | Tạo publisher đọc từ resource | StreamHandle::receive |
| Async complete | Nguồn hoàn tất bình thường | closeAsync() |
| Async error | Nguồn phát lỗi | abortAsync(error) |
| Async cancel | Subscriber hủy | cancelAsync() |

usingWhen chờ publisher cleanup hoàn tất trước khi kết thúc tín hiệu tương ứng ở downstream. Điều này hữu ích khi đóng resource cần I/O bất đồng bộ. Cần thiết kế các callback cleanup idempotent và xử lý lỗi đóng tài nguyên theo chính sách của ứng dụng.

## 7. doFinally và doOnCancel

doFinally chạy khi sequence complete, error hoặc cancel. Nó nhận SignalType để phân biệt nguyên nhân:

~~~java
Flux<TelemetryEvent> watch(String deviceId) {
    return telemetryService.watch(deviceId)
            .doFinally(signal -> {
                metrics.recordTermination(deviceId, signal);
            });
}
~~~

Các tín hiệu thường gặp:

- SignalType.ON_COMPLETE: nguồn hoàn tất bình thường.
- SignalType.ON_ERROR: nguồn kết thúc do lỗi.
- SignalType.CANCEL: subscriber hủy.

doOnCancel chỉ chạy khi cancellation:

~~~java
return source
        .doOnCancel(() -> log.info("Subscriber cancelled"))
        .doFinally(signal -> metrics.record(signal));
~~~

Nên dùng doFinally để đo lường, ghi log hoặc thực hiện side effect đơn giản. Nếu cần sở hữu resource và bảo đảm đóng đúng một lần, ưu tiên using hoặc usingWhen. Không dùng doOnComplete làm cleanup duy nhất vì nó không chạy khi subscriber cancel hoặc nguồn lỗi.

### 7.1. Đặt doFinally trước hay sau share?

Vị trí operator quyết định tín hiệu được quan sát:

~~~java
Flux<Event> shared = source
        .doFinally(signal -> log.info("Upstream ended: {}", signal))
        .share();
~~~

doFinally nằm trước share() quan sát vòng đời của upstream dùng chung. Nó thường chạy khi upstream complete, error hoặc bị refCount cancel.

~~~java
Flux<Event> shared = source.share()
        .doFinally(signal -> log.info("One subscriber ended: {}", signal));
~~~

doFinally nằm sau share() chạy theo từng subscriber downstream. Khi một client hủy, callback của subscriber đó chạy dù upstream vẫn còn subscriber khác.

Nếu dùng callback để xóa entry trong registry của nguồn dùng chung, cần đặt callback ở upstream boundary để chỉ xóa khi upstream thực sự dừng, không phải khi một client riêng lẻ rời đi.

## 8. Adapter cho API listener bên ngoài

Nhiều thư viện cung cấp API dạng đăng ký callback và trả về handle để gỡ đăng ký. Hãy chuyển API đó thành publisher có cleanup:

~~~java
Flux<DeviceEvent> watch(String deviceId) {
    return Flux.using(
            () -> eventApi.register(deviceId),
            ListenerRegistration::events,
            ListenerRegistration::close);
}
~~~

ListenerRegistration đại diện cho một đăng ký cụ thể và có method close() để gỡ listener. Mỗi subscriber mở một registration; complete, error hoặc cancel đều đóng registration đó.

Nếu muốn nhiều client chia sẻ cùng một registration:

~~~java
Flux<DeviceEvent> sharedWatch(String deviceId) {
    return Flux.defer(() ->
            Flux.using(
                    () -> eventApi.register(deviceId),
                    ListenerRegistration::events,
                    ListenerRegistration::close))
            .share();
}
~~~

Đừng chỉ gọi eventApi.register(...) khi tạo bean service. Nếu registration được tạo lúc khởi động ứng dụng và không gắn với subscriber, nó có thể tồn tại suốt vòng đời process dù không còn client nào cần dữ liệu.

## 9. Tránh subscription bị bỏ quên

Một lỗi phổ biến là gọi subscribe() trong service hoặc handler rồi không giữ Disposable:

~~~java
// Không nên: subscription tách khỏi vòng đời request
public Flux<DeviceEvent> watch(String deviceId) {
    eventApi.events(deviceId)
            .subscribe(this::storeEvent);

    return Flux.never();
}
~~~

Đoạn code trên tạo một subscription độc lập. Khi RSocket client hủy Flux.never(), subscription bên trong vẫn tiếp tục nhận event. Framework không thể hủy subscription mà service tự tạo và không trả về.

Hãy trả publisher cho caller:

~~~java
public Flux<DeviceEvent> watch(String deviceId) {
    return eventApi.events(deviceId)
            .doOnNext(this::storeEvent);
}
~~~

Khi đó subscription do Spring/RSocket quản lý và cancellation có thể truyền về nguồn.

### 9.1. Khi nào subscribe() là hợp lệ?

Có những subscription không thuộc request cụ thể, ví dụ consumer nền đọc event để cập nhật projection. Khi đó component phải sở hữu vòng đời subscription:

~~~java
@Component
public class ProjectionWorker {

    private final Disposable.Composite subscriptions =
            Disposables.composite();

    private final EventSource eventSource;
    private final ProjectionService projectionService;

    public ProjectionWorker(
            EventSource eventSource,
            ProjectionService projectionService) {
        this.eventSource = eventSource;
        this.projectionService = projectionService;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void start() {
        Disposable subscription = eventSource.events()
                .concatMap(projectionService::apply)
                .subscribe(
                        ignored -> { },
                        error -> log.error("Projection worker stopped", error));

        subscriptions.add(subscription);
    }

    @PreDestroy
    public void stop() {
        subscriptions.dispose();
    }
}
~~~

Ở đây subscription là một worker nền có chủ đích sống trong vòng đời ứng dụng. Disposable.Composite giữ các handle và dispose tất cả khi Spring context dừng. Trong production, cần thêm chiến lược retry, giám sát lỗi và xử lý khi worker kết thúc ngoài dự kiến.

### 9.2. Không để mất Disposable

Khi gọi subscribe(...), giữ Disposable nếu component cần khả năng hủy. Nếu chỉ cần pipeline reactive theo request, không gọi subscribe thủ công. Nếu cần nhiều subscription nền, quản lý chúng bằng Disposable.Composite hoặc một lifecycle component tương đương.

Không lưu Disposable trong static field hoặc map không có cleanup. Chính registry quản lý subscription cũng có thể trở thành nguồn rò rỉ nếu không xóa entry khi component dừng.

## 10. Chia sẻ nguồn theo khóa và dọn registry

Một service có thể chia sẻ telemetry theo deviceId. Nếu lưu publisher dùng chung trong map, cần dọn map entry khi upstream kết thúc hoặc bị ngắt. Không xóa entry trong doFinally của từng subscriber downstream vì một client rời đi không có nghĩa nguồn dùng chung đã dừng.

Ví dụ đơn giản:

~~~java
@Component
public class SharedDeviceFeeds {

    private final ConcurrentMap<String, Flux<DeviceEvent>> feeds =
            new ConcurrentHashMap<>();

    private final EventApi eventApi;

    public SharedDeviceFeeds(EventApi eventApi) {
        this.eventApi = eventApi;
    }

    public Flux<DeviceEvent> watch(String deviceId) {
        return Flux.defer(() ->
                feeds.computeIfAbsent(deviceId, this::createSharedFeed));
    }

    private Flux<DeviceEvent> createSharedFeed(String deviceId) {
        AtomicReference<Flux<DeviceEvent>> entryRef =
                new AtomicReference<>();

        Flux<DeviceEvent> shared = Flux.defer(() ->
                Flux.using(
                        () -> eventApi.register(deviceId),
                        ListenerRegistration::events,
                        ListenerRegistration::close))
                .doFinally(signal -> {
                    Flux<DeviceEvent> entry = entryRef.get();
                    if (entry != null) {
                        feeds.remove(deviceId, entry);
                    }
                })
                .share();

        entryRef.set(shared);
        return shared;
    }
}
~~~

Ở đây:

- computeIfAbsent trả cùng một shared publisher cho các client cùng device ID.
- Flux.defer chỉ tạo hoặc lấy entry khi thực sự có subscriber; nếu caller lấy Flux nhưng không subscribe thì registry không giữ entry vô ích.
- Flux.defer trì hoãn việc mở registration đến khi có subscriber đầu tiên.
- using gắn registration với upstream subscription.
- share giữ một registration cho nhóm subscriber hiện tại.
- doFinally đặt trước share, nên chỉ chạy khi upstream hoàn tất, lỗi hoặc bị hủy do refCount về 0.
- Registry xóa đúng publisher instance khi upstream dừng để lần yêu cầu sau có thể tạo nguồn mới mà không xóa nhầm entry được tạo đồng thời.

Ví dụ giả định ListenerRegistration.close() là thao tác đồng bộ, an toàn khi được gọi một lần; cần import AtomicReference cùng các kiểu collection liên quan. Khi upstream complete, error hoặc bị cancel sau khi nhóm subscriber rời đi, entry được xóa; một subscription mới sẽ tạo publisher và registration mới. Nếu cleanup bất đồng bộ, dùng usingWhen. Với registry phức tạp có nhiều lần tạo/hủy đồng thời, nên bọc entry trong một đối tượng quản lý vòng đời có định danh và xóa có điều kiện.

## 11. Những operator không tự đóng nguồn như mong đợi

Một số operator có thể giữ nguồn hoặc dữ liệu lâu hơn vòng đời subscriber:

| Operator/cách dùng | Hành vi cần lưu ý |
|---|---|
| autoConnect() | Sau khi đạt ngưỡng, không tự disconnect khi subscriber về 0 |
| cache() | Giữ và phát lại phần tử đã cache; không phải chính sách dừng producer khi không còn người nhận |
| replay() | Có thể giữ buffer để phát lại cho subscriber đến sau; cần giới hạn và lifecycle rõ |
| subscribe() không giữ Disposable | Tạo subscription tách khỏi caller và khó hủy |
| onBackpressureBuffer() không giới hạn | Có thể tích lũy dữ liệu khi downstream chậm |
| Sinks.Many dùng như event bus | Producer bên ngoài vẫn có thể tiếp tục emit khi không có subscriber |

cache() phù hợp khi muốn memoize kết quả hữu hạn hoặc phát lại dữ liệu theo chính sách rõ ràng. Nó không phải lựa chọn mặc định cho telemetry vô hạn cần dừng khi subscriber cuối cùng rời đi. Nếu cần replay, hãy đặt giới hạn số phần tử hoặc TTL và quản lý nguồn upstream riêng.

Sinks.Many chỉ là điểm phát dữ liệu. Nó không tự mở hoặc đóng producer bên ngoài. Nếu sink được nối với một subscription đến message broker, component sở hữu sink cũng phải giữ và dispose subscription đó.

## 12. Backpressure và cleanup giải quyết hai vấn đề khác nhau

Backpressure giới hạn lượng dữ liệu producer phát theo demand của subscriber. Cancellation kết thúc subscription và yêu cầu upstream dừng công việc. Cleanup giải phóng resource đã mở.

| Cơ chế | Câu hỏi được giải quyết |
|---|---|
| Backpressure | Subscriber hiện có thể nhận bao nhiêu phần tử? |
| Cancellation | Subscriber còn muốn tiếp tục nhận dữ liệu không? |
| Resource cleanup | Listener, cursor hoặc socket nào cần được đóng khi subscription kết thúc? |
| refCount/share | Có còn subscriber nào cần nguồn upstream dùng chung không? |

Một stream có thể backpressure đúng nhưng vẫn rò rỉ listener nếu adapter không gỡ callback khi cancel. Ngược lại, nguồn có thể đóng đúng nhưng vẫn tạo buffer quá lớn khi downstream chậm. Cần thiết kế cả flow control và lifecycle.

## 13. Kiểm thử cleanup khi subscriber rời đi

Kiểm thử nên xác minh resource được đóng trong cả ba trường hợp: complete, error và cancel.

### 13.1. Kiểm thử using khi cancel

~~~java
class TestHandle {
    private final AtomicBoolean closed;

    TestHandle(AtomicBoolean closed) {
        this.closed = closed;
    }

    Flux<Long> events() {
        return Flux.interval(Duration.ofMillis(50));
    }

    void close() {
        closed.set(true);
    }
}

@Test
void closesResourceWhenSubscriberCancels() {
    AtomicBoolean closed = new AtomicBoolean();

    Flux<Long> stream = Flux.using(
            () -> new TestHandle(closed),
            TestHandle::events,
            TestHandle::close);

    StepVerifier.create(stream)
            .expectNextCount(1)
            .thenCancel()
            .verify();

    assertThat(closed).isTrue();
}
~~~

thenCancel() hủy subscription sau khi nhận một phần tử. Cleanup consumer phải được gọi dù nguồn chưa complete.

### 13.2. Kiểm thử shared source với nhiều subscriber

~~~java
@Test
void closesSharedSourceOnlyAfterLastSubscriberCancels() {
    AtomicInteger closed = new AtomicInteger();

    Flux<Long> shared = Flux.<Long>never()
            .doFinally(signal -> closed.incrementAndGet())
            .share();

    Disposable first = shared.subscribe();
    Disposable second = shared.subscribe();

    first.dispose();
    assertThat(closed).hasValue(0);

    second.dispose();
    assertThat(closed).hasValue(1);
}
~~~

Khi subscriber đầu tiên hủy, subscriber thứ hai vẫn cần nguồn nên upstream chưa đóng. Khi subscriber cuối cùng hủy, upstream nhận cancel và doFinally chạy một lần.

### 13.3. Ma trận kiểm thử cần có

| Kịch bản | Kết quả cần xác minh |
|---|---|
| Subscriber nhận đủ dữ liệu và nguồn complete | Resource được đóng |
| Nguồn phát error | Resource được đóng và lỗi được truyền đúng |
| Client cancel request-stream | Cancellation đến upstream và resource được đóng |
| Hai client cùng subscribe | Chỉ mở một nguồn nếu dùng share/refCount |
| Một trong hai client cancel | Nguồn vẫn hoạt động cho client còn lại |
| Client cuối cùng cancel | Upstream bị cancel và nguồn được đóng |
| Subscriber quay lại trong grace period | Nguồn chưa bị đóng nếu refCount grace period còn hiệu lực |
| Dừng Spring context | Subscription nền và resource do component sở hữu được dispose |
| Adapter listener nhận cancel | Callback được gỡ, không còn event được chuyển vào sink |
| Nguồn được tạo lại sau cleanup | Không tái sử dụng handle đã đóng |

## 14. Các lỗi thường gặp

### Gọi subscribe() bên trong @MessageMapping

Handler trả về một publisher nhưng đồng thời tự subscribe một publisher khác. Client cancel chỉ ảnh hưởng publisher do framework quản lý; subscription tự tạo có thể tiếp tục chạy. Hãy trả Flux trực tiếp.

### Đóng nguồn khi một client rời đi

Nếu nguồn được share, một subscriber rời đi không có nghĩa những subscriber khác đã rời đi. Dùng refCount hoặc share để đóng upstream khi số subscriber về 0.

### Dùng autoConnect cho nguồn cần tự dừng

autoConnect không theo dõi việc subscriber giảm về 0 để tự ngắt. Chọn refCount hoặc quản lý Disposable từ connect().

### Chỉ cleanup khi complete

Client thường hủy stream trước khi nguồn complete. Cleanup cần chạy cả khi cancel và error. Dùng using/usingWhen hoặc doFinally phù hợp.

### Đăng ký listener khi tạo service bean

Listener được mở trước khi có subscriber và có thể sống suốt vòng đời ứng dụng. Dùng defer và resource operator để mở theo subscription.

### Cache một Flux vô hạn

Cache/replay có thể giữ dữ liệu và subscription lâu hơn dự kiến. Đặt giới hạn buffer/TTL hoặc chọn share/refCount cho luồng realtime không cần replay.

### Quên cleanup subscription nền

Subscription nền là hợp lệ khi có chủ đích, nhưng phải lưu Disposable và dispose khi component hoặc application dừng.

### Nghĩ hủy stream sẽ đóng cả RSocket connection

Cancellation thường áp dụng cho một interaction. Connection có thể tiếp tục phục vụ request khác.

## 15. Checklist triển khai

Trước khi phát hành luồng dữ liệu realtime, hãy xác nhận:

1. Nguồn được mở khi subscribe, không mở sớm ngoài lifecycle.
2. Mỗi subscription sở hữu resource riêng hoặc tham gia một shared source có ref-count.
3. Cancellation từ RSocket truyền đến publisher upstream.
4. Adapter của callback/listener gỡ đăng ký khi cancel, error hoặc complete.
5. Dùng share()/refCount() khi nguồn chỉ cần tồn tại lúc có subscriber.
6. Không dùng autoConnect() nếu yêu cầu là tự dừng khi subscriber về 0.
7. Resource đồng bộ dùng using; cleanup bất đồng bộ dùng usingWhen.
8. doFinally được dùng để quan sát lifecycle và không thay thế resource ownership.
9. Không gọi subscribe() trong handler/service nếu không sở hữu và quản lý Disposable.
10. Subscription nền được giữ trong Disposable.Composite hoặc lifecycle manager.
11. Registry theo key xóa entry khi upstream dừng, không xóa khi một subscriber riêng lẻ rời đi.
12. Buffer/backpressure có giới hạn và phù hợp với tốc độ downstream.
13. Có kiểm thử complete, error, cancel và nhiều subscriber.
14. Hủy một request-stream không làm đóng nhầm các interaction khác trên cùng RSocket connection.

## 16. Tổng kết

Một luồng dữ liệu realtime chỉ nên giữ nguồn upstream khi còn subscriber cần nhận dữ liệu, trừ khi producer được thiết kế để chạy nền. RSocket truyền cancellation của request-stream về responder; Spring handler nên trả Flux để framework quản lý subscription. Với nguồn dùng chung, share() hoặc refCount() giúp đóng upstream khi subscriber cuối cùng rời đi. Với resource gắn với một subscription, using và usingWhen bảo đảm cleanup khi complete, error hoặc cancel.

Tránh gọi subscribe() rồi bỏ quên Disposable. Nếu thật sự cần subscription nền, để một component sở hữu handle và dispose khi dừng. Phân biệt cleanup upstream với kết thúc của từng subscriber, đặc biệt khi chia sẻ nguồn theo device hoặc tenant. Kiểm thử cancellation cùng nhiều subscriber sẽ giúp phát hiện listener, cursor và producer bị bỏ quên trước khi chúng trở thành rò rỉ tài nguyên trong production.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Project Reactor Reference — Using Resources and Finally](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Project Reactor Reference — Broadcasting with ConnectableFlux](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html)
- [Reactor Flux API — share, refCount, doFinally and usingWhen](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
