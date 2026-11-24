# Chọn nguồn dữ liệu theo từng đăng ký hoặc dùng chung cho nhiều bên nhận

Khi một route RSocket trả về `Flux<T>`, mỗi client đăng ký nhận dữ liệu có thể tạo một luồng xử lý riêng, hoặc nhiều client có thể cùng nhận dữ liệu từ một nguồn được chia sẻ. Hai cách này có chi phí, vòng đời và ngữ nghĩa khác nhau. Chọn sai có thể khiến server mở quá nhiều query, đọc cùng một nguồn nhiều lần, giữ tài nguyên sau khi client rời đi hoặc làm một subscriber chậm ảnh hưởng tới tất cả subscriber còn lại.

Trong module `INTEGRATION_REALTIME_RSOCKET`, bài toán này thường xuất hiện với telemetry, trạng thái thiết bị, sự kiện hệ thống và các phiên realtime. Bài viết trình bày cách phân biệt nguồn cold theo từng subscription với nguồn hot/shared multicast, cách triển khai trong Reactor và Spring RSocket, cùng những quyết định về backpressure, bảo mật và vòng đời.

## 1. Hai cách tổ chức nguồn dữ liệu

### 1.1. Nguồn riêng cho từng subscription

Với nguồn cold, mỗi lần có subscriber mới, publisher thực hiện công việc tạo dữ liệu cho subscriber đó. Ví dụ, mỗi client mở Request-Stream sẽ tạo một query R2DBC riêng hoặc một subscription riêng tới API downstream.

```text
Client A ── REQUEST_STREAM ──> Handler ──> Query A ──> Database
Client B ── REQUEST_STREAM ──> Handler ──> Query B ──> Database
Client C ── REQUEST_STREAM ──> Handler ──> Query C ──> Database
```

Mỗi subscription có demand, cancellation và trạng thái riêng. Khi client A hủy stream, query A có thể được dừng mà không hủy query B hoặc C.

### 1.2. Một nguồn dùng chung cho nhiều subscriber

Với nguồn shared, ứng dụng chỉ mở một subscription tới nguồn upstream rồi multicast các sự kiện tới nhiều subscriber RSocket.

```text
                         ┌──> Client A
Sensor / Broker ─> Shared feed ──> Client B
                         └──> Client C
```

Ví dụ, một adapter đăng ký callback thiết bị một lần và chia sẻ các sự kiện tới nhiều client đang theo dõi cùng feed. Cách này tránh tạo một listener hoặc một consumer upstream cho mỗi client, nhưng cần có chính sách cho subscriber mới, subscriber chậm và subscriber rời đi.

## 2. So sánh nguồn riêng và nguồn dùng chung

| Tiêu chí | Nguồn riêng theo subscription | Nguồn dùng chung |
|---|---|---|
| Số subscription upstream | Thường một cho mỗi client | Thường một cho nhóm subscriber đang chia sẻ |
| Trạng thái | Độc lập theo subscriber | Có trạng thái upstream chung và trạng thái downstream riêng |
| Demand | Mỗi subscriber điều tiết nguồn của mình | Demand có thể được phối hợp qua toán tử multicast hoặc cần buffer/drop riêng |
| Cancellation | Hủy một subscriber thường dừng nguồn riêng của subscriber đó | Hủy một subscriber không nên dừng nguồn khi subscriber khác còn dùng; nguồn dừng theo chính sách lifecycle |
| Dữ liệu lịch sử | Mỗi query có thể trả snapshot riêng | Subscriber mới thường chỉ thấy sự kiện từ lúc tham gia, trừ khi có replay/cache |
| Tài nguyên | Có thể tăng theo số client | Giảm số nguồn upstream nhưng cần quản lý fan-out và buffer |
| Cách ly dữ liệu | Dễ gắn query/filter/transaction riêng | Phải kiểm soát tenant, quyền và filter ở từng nhánh subscriber |
| Trường hợp phù hợp | Query cá nhân hóa, dữ liệu theo quyền, truy vấn có bộ lọc riêng | Telemetry chung, feed sự kiện, nguồn callback đắt hoặc broker subscription dùng chung |

Không có lựa chọn đúng cho mọi route. Hãy chọn theo ngữ nghĩa dữ liệu và cách nguồn upstream hoạt động, sau đó đo số subscription, chi phí query, buffer và tác động của subscriber chậm.

## 3. Nguồn cold: tạo dữ liệu theo từng lần đăng ký

Trong Reactor, nhiều publisher từ database reactive hoặc lời gọi reactive HTTP là cold: công việc bắt đầu khi có subscription. `Flux.defer(...)` giúp trì hoãn việc tạo publisher nguồn tới thời điểm subscriber đăng ký, nhờ đó mỗi subscriber có thể nhận một query mới.

Ví dụ service tạo query telemetry riêng:

```java
@Service
public class TelemetryHistoryService {
    private final TelemetryRepository repository;

    public TelemetryHistoryService(TelemetryRepository repository) {
        this.repository = repository;
    }

    public Flux<TelemetryReading> watch(
            String tenantId,
            String deviceId,
            Instant from) {

        return Flux.defer(() -> repository
            .streamForTenantAndDevice(tenantId, deviceId, from)
            .map(this::toReading));
    }

    private TelemetryReading toReading(TelemetryEntity entity) {
        return new TelemetryReading(
            entity.deviceId(), entity.capturedAt(), entity.value());
    }
}
```

Handler RSocket trả publisher cho từng request:

```java
@Controller
public class TelemetryHandler {
    private final TelemetryHistoryService service;
    private final TenantResolver tenantResolver;

    public TelemetryHandler(
            TelemetryHistoryService service,
            TenantResolver tenantResolver) {
        this.service = service;
        this.tenantResolver = tenantResolver;
    }

    @MessageMapping("telemetry.watch")
    public Flux<TelemetryReading> watch(
            @Payload WatchRequest request,
            Principal principal) {
        String tenantId = tenantResolver.tenantFor(principal);
        return service.watch(tenantId, request.deviceId(), request.from());
    }
}
```

Mỗi lần client gọi route `telemetry.watch`, Spring tạo một tương tác và service trả một publisher. Khi publisher được subscribe, `defer` gọi repository để mở nguồn dữ liệu cho subscriber đó. Việc lọc theo tenant được thực hiện ở server bằng danh tính đã xác thực, không tin tenant ID do client tự khai báo.

### 3.1. Khi nào nên tạo nguồn riêng?

Nguồn riêng thường phù hợp khi:

- Mỗi client có bộ lọc, khoảng thời gian hoặc quyền truy cập khác nhau.
- Mỗi subscriber cần snapshot nhất quán hoặc transaction riêng.
- Nguồn hỗ trợ cancellation theo subscriber, ví dụ query cursor của R2DBC.
- Số subscriber đồng thời đủ thấp để server chịu được số query hoặc upstream request tương ứng.
- Việc một subscriber chậm không được làm chậm subscriber khác.

Đổi lại, nếu 2.000 client cùng gọi một route và mỗi lần mở query phức tạp, database có thể phải xử lý 2.000 query. Cần giới hạn số subscription đồng thời, giới hạn khoảng thời gian truy vấn và theo dõi connection pool.

## 4. Nguồn shared: multicast một upstream cho nhiều subscriber

Khi nhiều client cần cùng một feed, có thể chia sẻ một publisher upstream bằng `publish().refCount(1)`. Publisher bắt đầu kết nối tới nguồn khi subscriber đầu tiên tham gia; khi subscriber cuối cùng hủy, upstream được disconnect. Subscriber tiếp theo có thể kích hoạt một kết nối nguồn mới.

```java
@Service
public class SharedTelemetryFeed {
    private final Flux<TelemetryEvent> sharedFeed;

    public SharedTelemetryFeed(SensorGateway gateway) {
        this.sharedFeed = Flux.defer(gateway::events)
            .publish()
            .refCount(1);
    }

    public Flux<TelemetryEvent> watch(
            String tenantId,
            String deviceId) {
        return sharedFeed.filter(event ->
            event.tenantId().equals(tenantId)
                && event.deviceId().equals(deviceId));
    }
}
```

`SensorGateway.events()` đại diện cho publisher từ SDK thiết bị hoặc broker. `Flux.defer` tạo subscription nguồn mới khi nhóm subscriber bắt đầu lại sau khi đã không còn subscriber nào. `publish().refCount(1)` chia sẻ một subscription upstream giữa các subscriber đồng thời và disconnect khi subscriber cuối cùng rời đi.

Handler vẫn tạo một nhánh riêng cho mỗi client:

```java
@MessageMapping("telemetry.live")
public Flux<TelemetryEvent> live(
        @Payload WatchRequest request,
        Principal principal) {
    String tenantId = tenantResolver.tenantFor(principal);
    return sharedFeed.watch(tenantId, request.deviceId());
}
```

Mỗi subscriber có filter riêng sau nguồn shared. Cần bảo đảm filter được thực hiện phía server trước khi serialize và gửi payload; không gửi toàn bộ feed tới client rồi trông chờ client tự lọc.

### 4.1. `share()`, `publish()` và `refCount()`

Các API Reactor thường gặp có ngữ nghĩa khác nhau:

| API | Hành vi chính | Điểm cần lưu ý |
|---|---|---|
| `publish()` | Tạo `ConnectableFlux` để nhiều subscriber dùng chung một upstream khi kết nối được kích hoạt. | Cần quyết định lúc connect/disconnect. |
| `publish().refCount(1)` | Tự kết nối khi có subscriber đầu tiên và ngắt khi subscriber cuối cùng hủy. | Hợp với nguồn chỉ cần hoạt động khi có người nhận. |
| `share()` | Cách viết ngắn cho mô hình chia sẻ/ref-count phổ biến. | Ít thể hiện rõ chính sách kết nối; dùng `publish().refCount(...)` khi cần diễn đạt lifecycle cụ thể. |
| `autoConnect(1)` | Kết nối sau khi đủ số subscriber; không tự ngắt chỉ vì subscriber rời đi. | Phù hợp nguồn sống theo lifecycle ứng dụng, nhưng cần đóng/dispose rõ ràng. |
| `replay(n)` | Giữ lại tối đa `n` phần tử gần nhất cho subscriber đến sau khi kết nối còn hoạt động. | Có chi phí bộ nhớ và có thể giữ dữ liệu nhạy cảm/cũ. |
| `cache()` | Lưu và phát lại dữ liệu đã phát theo chính sách cache. | Với nguồn vô hạn, có thể giữ dữ liệu không giới hạn và không phù hợp làm live feed mặc định. |

Chọn `refCount` nếu nguồn chỉ cần hoạt động khi có subscriber. Chọn lifecycle gắn với ứng dụng nếu nguồn cần chạy liên tục ngay cả khi không có client. Trong trường hợp đó, phải có hook đóng nguồn khi ứng dụng shutdown.

## 5. Subscriber đến muộn: live-only hay cần replay?

Nguồn shared kiểu multicast thường chỉ phát sự kiện mới cho subscriber đang tham gia. Một client kết nối sau sẽ không tự nhận lại những sự kiện đã phát trước khi nó subscribe.

| Nhu cầu | Cách tổ chức |
|---|---|
| Chỉ cần dữ liệu mới kể từ lúc đăng ký | Shared live feed, không replay. |
| Cần một số sự kiện gần nhất | Replay buffer có giới hạn số phần tử hoặc thời gian. |
| Cần lịch sử đầy đủ | Đọc snapshot/lịch sử từ database hoặc event store rồi chuyển sang live feed. |
| Cần phát lại sau khi mất kết nối | Dùng sequence/cursor và cơ chế lưu bền vững; không dựa riêng vào bộ nhớ của `cache()`. |

Nếu dùng replay, đặt giới hạn rõ ràng về số phần tử hoặc thời gian lưu. Một feed phát 500 event/giây với replay 60 giây có thể giữ tới 30.000 event cho mỗi vùng replay. Nếu mỗi event chứa payload lớn, chi phí heap tăng nhanh.

Không dùng `cache()` không giới hạn cho một nguồn realtime vô hạn. Với dữ liệu theo tenant hoặc người dùng, replay/cache cần được phân vùng theo quyền truy cập; không để một cache toàn cục phát dữ liệu của tenant này sang tenant khác do filter sai hoặc thứ tự operator không phù hợp.

### 5.1. Kết hợp snapshot và live feed

Một màn hình thường cần cả lịch sử ban đầu lẫn cập nhật mới. Có thể đọc snapshot tới một sequence boundary rồi đăng ký live feed từ sequence tiếp theo:

```text
1. Đọc snapshot có watermark = 4200
2. Đăng ký live feed với afterSequence = 4200
3. Bỏ event <= 4200 nếu nguồn có thể phát trùng
4. Ghép snapshot với event mới theo sequence
```

Nếu chỉ gọi query lịch sử rồi sau đó mới subscribe live feed, có thể bỏ lỡ event phát ra giữa hai thao tác. Cần watermark, cursor hoặc cơ chế subscribe-before-snapshot có quy tắc deduplicate để tránh gap/duplicate.

## 6. Backpressure khi nhiều subscriber dùng chung nguồn

Nguồn riêng có thể điều tiết độc lập theo demand của từng client. Với nguồn multicast, một publisher upstream phải phục vụ nhiều nhánh subscriber, do đó cần chọn chính sách khi tốc độ tiêu thụ khác nhau.

### 6.1. Subscriber chậm có thể ảnh hưởng cả nhóm

Toán tử `publish()` của Reactor phối hợp demand giữa các subscriber. Khi một subscriber chưa có demand, upstream có thể bị tạm dừng để không phát vượt nhu cầu chung. Điều này giữ backpressure, nhưng subscriber chậm có thể làm chậm cả feed dùng chung.

Nếu mọi subscriber cần nhận đầy đủ từng event theo thứ tự, việc phối hợp demand có thể là lựa chọn đúng. Nếu feed là telemetry trạng thái mới nhất và có thể bỏ các giá trị trung gian, cần chính sách buffer/drop riêng cho mỗi nhánh.

### 6.2. Buffer hữu hạn cho từng nhánh

Ví dụ một client theo dõi vị trí thiết bị chỉ cần trạng thái gần nhất. Có thể đặt buffer hữu hạn và bỏ phần tử cũ nhất khi client không theo kịp:

```java
public Flux<TelemetryEvent> watchLatest(
        String tenantId,
        String deviceId) {

    return sharedFeed
        .filter(event -> event.tenantId().equals(tenantId)
            && event.deviceId().equals(deviceId))
        .onBackpressureBuffer(
            128,
            dropped -> metrics.incrementDroppedTelemetry(),
            BufferOverflowStrategy.DROP_OLDEST
        );
}
```

Buffer nằm trên nhánh subscriber, giới hạn tối đa 128 phần tử. Khi vượt giới hạn, `DROP_OLDEST` bỏ trạng thái cũ và giữ dữ liệu mới hơn. Đây là lựa chọn có thể chấp nhận cho một số telemetry hoặc vị trí; không phù hợp cho command, giao dịch tài chính hay event cần xử lý đầy đủ.

Buffer hữu hạn không biến dữ liệu thành durable. Khi buffer đầy, dữ liệu vẫn bị loại bỏ theo chính sách. Cần đo số phần tử bị drop và hiển thị/ghi nhận tình trạng mất dữ liệu nếu nghiệp vụ cần.

### 6.3. Không dùng một chiến lược drop cho mọi loại dữ liệu

| Loại dữ liệu | Chính sách thường phù hợp |
|---|---|
| Vị trí con trỏ, telemetry trạng thái mới nhất | Có thể `DROP_OLDEST` hoặc latest-value nếu chấp nhận bỏ trạng thái trung gian. |
| Metric quan sát có thể lấy mẫu | Sampling, aggregation hoặc buffer hữu hạn. |
| Lệnh điều khiển thiết bị | Không drop âm thầm; cần xác nhận, sequence và queue có giới hạn. |
| Sự kiện giao dịch/kiểm toán | Durable log/broker, offset hoặc acknowledgement; không dựa vào in-memory multicast. |
| Notification có thể truy vấn lại | Lưu trạng thái bền vững và cho phép client đọc lại theo cursor. |

Nếu một subscriber chậm không được phép ảnh hưởng subscriber khác và cũng không được mất event, cân nhắc tách consumer/queue riêng cho từng subscriber hoặc dùng broker có retention/offset. Một shared `Flux` trong bộ nhớ không thể tự cung cấp mọi bảo đảm giao nhận.

## 7. Multicast khác với competing consumers

Chia sẻ một nguồn cho nhiều bên nhận thường có nghĩa **mỗi subscriber nhận một bản của mỗi event**. Đây là multicast/pub-sub.

Trong mô hình competing consumers hoặc consumer group, nhiều worker chia nhau xử lý event; mỗi event thường được giao cho một worker trong nhóm theo semantics của broker. Hai mô hình phục vụ mục đích khác nhau:

| Mục tiêu | Mô hình |
|---|---|
| Mỗi client đang xem dashboard đều nhận cùng bản cập nhật | Multicast/pub-sub |
| Nhiều worker chia tải xử lý một hàng đợi công việc | Competing consumers/consumer group |
| Mỗi người dùng có lịch sử và trạng thái riêng | Subscription/queue hoặc query riêng theo người dùng |
| Cần lưu và phát lại event sau khi client offline | Durable topic/log với cursor hoặc offset |

Không dùng một multicast in-memory để thay thế hàng đợi công việc. Nếu mọi consumer cùng nhận mọi event rồi cùng xử lý side effect, hệ thống có thể thực hiện cùng một công việc nhiều lần.

## 8. Bảo mật và cách ly dữ liệu khi dùng nguồn shared

Nguồn shared làm giảm số upstream subscription nhưng tăng yêu cầu cách ly ở mỗi nhánh downstream. Một lỗi filter có thể khiến event của tenant hoặc thiết bị khác được phát tới client không có quyền.

Các nguyên tắc quan trọng:

- Lấy tenant/principal từ cơ chế xác thực của server; không tin tenant ID do client tự gửi.
- Áp dụng filter theo tenant và resource ở server trước khi serialize event.
- Không cache hoặc replay dữ liệu cá nhân qua một vùng cache toàn cục nếu chưa có partition theo quyền.
- Kiểm tra quyền khi mở stream và khi quyền có thể thay đổi trong lúc stream còn sống.
- Hủy nhánh subscription khi client rời đi hoặc quyền truy cập bị thu hồi.
- Không ghi raw event chứa thông tin cá nhân/credential vào log chỉ để debug fan-out.

Ví dụ, `sharedFeed` có thể chứa event từ nhiều thiết bị. Mỗi handler phải lấy tenant từ `Principal` đã xác thực rồi lọc ở server. Không gửi toàn bộ feed cho một client để client tự quyết định event nào thuộc về mình.

## 9. Vòng đời nguồn upstream

Nguồn shared cần một chủ sở hữu vòng đời rõ ràng. Với `publish().refCount(1)`, nguồn được kết nối khi subscriber đầu tiên tham gia và bị hủy khi subscriber cuối cùng rời đi. Cần kiểm tra `gateway.events()` có thực sự unregister listener/đóng broker consumer khi cancellation hay không.

Với nguồn sống theo vòng đời ứng dụng, có thể chủ động connect và giữ `Disposable` để dispose khi shutdown:

```java
@Component
public class ApplicationTelemetryFeed implements DisposableBean {
    private final Disposable connection;
    private final Flux<TelemetryEvent> shared;

    public ApplicationTelemetryFeed(SensorGateway gateway) {
        ConnectableFlux<TelemetryEvent> connectable =
            Flux.defer(gateway::events).publish();

        this.shared = connectable;
        this.connection = connectable.connect();
    }

    public Flux<TelemetryEvent> stream() {
        return shared;
    }

    @Override
    public void destroy() {
        connection.dispose();
    }
}
```

Trong ví dụ, nguồn được kết nối ngay khi bean được tạo và tồn tại cho tới khi ứng dụng shutdown. Nếu không có subscriber, nguồn vẫn có thể hoạt động và tiêu thụ tài nguyên. Chỉ dùng cách này khi thật sự cần feed luôn chạy; nếu nguồn chỉ cần khi có người xem, `refCount` thường phù hợp hơn.

Khi server restart, nguồn in-memory được tạo lại và subscriber RSocket hiện tại sẽ mất kết nối. Nếu cần tiếp tục dữ liệu sau restart, dùng broker/event store bền vững và sequence/cursor; không coi `Flux` trong bộ nhớ là trạng thái phục hồi.

## 10. Kết hợp nguồn riêng và nguồn dùng chung

Một ứng dụng không cần chọn một chiến lược duy nhất cho mọi route. Có thể dùng nguồn shared cho feed thô và nguồn riêng cho truy vấn lịch sử hoặc filter cá nhân:

```text
                         ┌─> subscriber A filter tenant/device
Gateway / Broker ─> Shared live feed ─┼─> subscriber B filter tenant/device
                         └─> subscriber C filter tenant/device

Client D ── REQUEST_STREAM ──> History query riêng ──> Database
Client E ── REQUEST_STREAM ──> History query riêng ──> Database
```

Ví dụ route có thể tách:

- `telemetry.live`: dùng nguồn shared để nhận event mới.
- `telemetry.history`: query riêng theo thiết bị, khoảng thời gian và quyền của từng subscriber.
- `telemetry.snapshot`: Request-Response trả trạng thái tại một thời điểm.

Nếu cần kết hợp history và live, hãy dùng sequence/watermark như phần trước để không bỏ lỡ event ở ranh giới chuyển đổi. Cách tổ chức này vừa tránh lặp lại nguồn live đắt tiền, vừa giữ query lịch sử và quyền truy cập độc lập.

## 11. Ma trận quyết định

| Điều kiện | Chọn nguồn riêng | Chọn nguồn shared |
|---|---|---|
| Mỗi client có query/filter khác nhau | Có | Chỉ share nguồn thô rồi filter riêng nếu an toàn |
| Nguồn upstream mở connection/listener tốn kém | Cân nhắc giới hạn số client | Thường phù hợp |
| Cần transaction/snapshot riêng | Phù hợp | Không nên share kết quả transaction |
| Client có thể đến và rời liên tục | Mỗi nguồn tạo/hủy riêng | Dùng `refCount` nếu nguồn chỉ cần khi có người nhận |
| Cần mọi subscriber nhận cùng event | Tạo nguồn riêng có thể lặp công việc | Multicast phù hợp |
| Một subscriber chậm không được làm chậm người khác | Dễ cô lập demand | Cần buffer/drop/queue riêng cho từng nhánh |
| Không được mất event | Cần nguồn/queue bền vững riêng hoặc cursor | Shared in-memory không đủ; dùng durable broker/log |
| Dữ liệu cá nhân theo tenant | Dễ cô lập query | Cần partition/filter và kiểm tra quyền chặt chẽ |

Trước khi triển khai, hãy ước lượng số subscriber đồng thời, tốc độ event, kích thước payload, thời gian sống stream, chi phí mở nguồn và mức độ mất dữ liệu cho phép. Dùng những số liệu này để chọn mô hình thay vì chỉ dựa vào việc code ngắn hơn.

## 12. Kiểm thử và quan sát

Nên kiểm thử cả số subscription upstream lẫn hành vi của từng subscriber:

1. Với nguồn cold, tạo hai subscriber và xác nhận nguồn được subscribe hai lần.
2. Hủy subscriber thứ nhất; xác nhận chỉ query/nguồn của subscriber đó bị cancel.
3. Với `publish().refCount(1)`, tạo nhiều subscriber đồng thời và xác nhận chỉ có một subscription upstream.
4. Hủy một subscriber nhưng giữ subscriber khác; xác nhận nguồn shared vẫn hoạt động.
5. Hủy subscriber cuối cùng; xác nhận nguồn upstream được cancel/unregister.
6. Cho subscriber mới tham gia sau khi feed đã phát event; xác nhận live-only không phát lại event cũ.
7. Kiểm tra replay/cache có giới hạn và không giữ dữ liệu vượt retention đã định.
8. Làm một subscriber chậm; xác nhận chính sách publish/backpressure/buffer/drop hoạt động như thiết kế.
9. Gửi event của nhiều tenant; xác nhận mỗi subscriber chỉ nhận dữ liệu được phép.
10. Restart nguồn/server; xác nhận reconnect, snapshot và cursor xử lý gap/duplicate theo yêu cầu.

Các chỉ số nên theo dõi:

- Số subscriber RSocket đang hoạt động theo route.
- Số subscription upstream và số lần connect/disconnect nguồn.
- Throughput event, số byte fan-out và số bản sao được phát.
- Buffer occupancy, số event bị drop và số subscriber chậm.
- Query count, thời gian query, connection pool và cancellation count.
- Số lần subscriber join/leave, thời gian stream sống và lỗi nguồn upstream.
- Số event bị trùng hoặc gap theo sequence nếu có replay/snapshot.

Trong test tích hợp, kiểm tra hành vi qua `RSocketRequester` thật để xác nhận nhiều client có semantics đúng như nguồn riêng/shared dự kiến; unit test cho `Flux` không đủ để kiểm tra route, cancellation và network disconnect.

## 13. Kết luận

Chọn nguồn riêng theo subscription khi mỗi client cần query, quyền, transaction hoặc cancellation độc lập. Chọn nguồn shared khi nhiều client cần cùng một feed và chi phí mở nguồn upstream lớn; dùng multicast có lifecycle rõ ràng như `publish().refCount(1)` nếu nguồn chỉ cần hoạt động khi có người nhận. Với nguồn shared, phải quyết định subscriber đến muộn có replay hay không, cách xử lý subscriber chậm, giới hạn buffer, cách ly tenant và hành vi khi nguồn/server restart. Với event không được phép mất hoặc cần xử lý bền vững, dùng broker/event store có cursor thay vì chỉ dựa vào một publisher trong bộ nhớ.
