# Truyền nhu cầu xuyên qua các tầng dịch vụ và nguồn dữ liệu

Trong một ứng dụng RSocket, backpressure chỉ có ích khi nhu cầu của bên nhận được truyền xuyên suốt từ kết nối tới nơi tạo dữ liệu. Nếu client chỉ muốn nhận 20 bản ghi nhưng controller, service hoặc repository lại đọc toàn bộ một triệu bản ghi vào bộ nhớ, luồng dữ liệu vẫn có thể làm hệ thống quá tải dù giao thức RSocket hỗ trợ `REQUEST_N`.

Với `INTEGRATION_REALTIME_RSOCKET`, cần thiết kế cả chuỗi xử lý theo Reactive Streams: client phát sinh demand, RSocket chuyển demand thành frame giao thức, handler chuyển tiếp publisher qua các tầng dịch vụ và nguồn dữ liệu chỉ tạo dữ liệu theo khả năng tiêu thụ. Bài học này tập trung vào cách giữ dòng demand đó liên tục và nhận biết những điểm có thể làm nó bị ngắt.

## 1. Demand đi từ subscriber về publisher

Trong Reactive Streams, subscriber không yêu cầu dữ liệu theo số byte mà theo số phần tử. Sau khi subscribe, subscriber gọi `Subscription.request(n)` để yêu cầu publisher phát tối đa `n` phần tử bổ sung. Khi cần dừng, subscriber gọi `cancel()`.

Ở biên RSocket, demand được biểu diễn bằng các frame:

- `REQUEST_STREAM` hoặc `REQUEST_CHANNEL` mở tương tác và mang Initial Request N, tức số payload ban đầu requester muốn nhận.
- `REQUEST_N` bổ sung demand trong một stream đang hoạt động.
- Với Request-Channel, mỗi hướng có demand riêng: client yêu cầu payload server gửi về, server yêu cầu payload client gửi lên.
- `CANCEL` hủy stream; việc hủy cần được truyền về publisher để giải phóng công việc và tài nguyên.

Khi frame được chuyển vào ứng dụng reactive, implementation RSocket nối demand của subscriber ở phía mạng với `Subscription.request(n)` của publisher. Ở bên trong ứng dụng, các tầng controller, service và repository thường không gửi frame `REQUEST_N` cho nhau; chúng truyền tín hiệu demand qua Reactive Streams. Chỉ tại ranh giới giao thức, implementation mới ánh xạ demand đó thành frame RSocket.

```text
Client subscriber
      |
      | request(n)
      v
RSocket requester  ---- REQUEST_N(n) ---->  RSocket responder
                                                |
                                                | Subscription.request(n)
                                                v
                                          @MessageMapping
                                                |
                                                v
                                           Service Flux
                                                |
                                                v
                                         Repository Flux
                                                |
                                                v
                                           Data source
```

Đường đi của dữ liệu là từ nguồn lên client; đường đi của demand ngược lại, từ subscriber về publisher. Khi consumer giảm demand hoặc hủy subscription, tín hiệu đó có thể đi ngược chuỗi để hạn chế đọc thêm dữ liệu.

## 2. Giữ publisher xuyên suốt các tầng ứng dụng

Một cách triển khai tốt là để mỗi tầng trả về `Mono` hoặc `Flux`, sau đó kết hợp publisher bằng các toán tử reactive. Controller không cần thu thập toàn bộ kết quả, service không tự subscribe, và repository không phải chuyển kết quả thành một collection lớn trước khi trả về.

Ví dụ: client đăng ký nhận lịch sử telemetry theo thiết bị. Client nhận một luồng `Reading`:

```java
Flux<Reading> readings = requester
    .route("telemetry.history")
    .data(new HistoryQuery(deviceId, from, to))
    .retrieveFlux(Reading.class);
```

Handler RSocket trả publisher từ service:

```java
@Controller
public class TelemetrySocketController {
    private final TelemetryHistoryService historyService;

    public TelemetrySocketController(TelemetryHistoryService historyService) {
        this.historyService = historyService;
    }

    @MessageMapping("telemetry.history")
    public Flux<Reading> history(HistoryQuery query) {
        return historyService.stream(query);
    }
}
```

Service tiếp tục trả publisher từ repository:

```java
@Service
public class TelemetryHistoryService {
    private final TelemetryRepository repository;

    public TelemetryHistoryService(TelemetryRepository repository) {
        this.repository = repository;
    }

    public Flux<Reading> stream(HistoryQuery query) {
        return repository
            .findByDeviceIdAndCapturedAtBetweenOrderByCapturedAtAsc(
                query.deviceId(), query.from(), query.to()
            )
            .map(this::toReading);
    }

    private Reading toReading(TelemetryEntity entity) {
        return new Reading(entity.deviceId(), entity.capturedAt(), entity.value());
    }
}
```

Repository sử dụng API reactive của R2DBC:

```java
public interface TelemetryRepository
        extends ReactiveCrudRepository<TelemetryEntity, Long> {

    Flux<TelemetryEntity>
    findByDeviceIdAndCapturedAtBetweenOrderByCapturedAtAsc(
        String deviceId,
        Instant from,
        Instant to
    );
}
```

Trong chuỗi này, handler không gọi `collectList()` để tạo `List<Reading>`. Service chỉ ánh xạ từng entity và repository phát dữ liệu theo publisher. Khi client chưa yêu cầu thêm phần tử, demand upstream có thể dừng ở ranh giới subscriber; khi client hủy, cancellation có thể truyền về query để driver giải phóng cursor hoặc tài nguyên liên quan nếu driver hỗ trợ.

Đây là cách giữ backpressure xuyên suốt: mỗi tầng giữ nguyên dạng reactive và tránh tiêu thụ trước dữ liệu mà tầng sau chưa yêu cầu.

## 3. Các thao tác làm đứt hoặc thay đổi demand

Không phải cứ dùng `Flux` là backpressure tự động được giữ nguyên. Một số thao tác làm publisher tiêu thụ sớm, giữ nhiều phần tử trong bộ nhớ hoặc thay đổi cách yêu cầu upstream.

| Thao tác | Ảnh hưởng tới demand | Cách sử dụng an toàn |
|---|---|---|
| `collectList()` / `collectMap()` | Phải tiêu thụ hết nguồn trước khi phát một collection. | Chỉ dùng khi dữ liệu có giới hạn nhỏ và nghiệp vụ thật sự cần toàn bộ kết quả. |
| `block()` / `blockFirst()` | Chuyển xử lý reactive thành chờ đồng bộ; có thể chiếm thread và làm tắc event loop. | Tránh trong controller/service reactive; giữ publisher hoặc chuyển đổi ở ranh giới blocking có kiểm soát. |
| `subscribe()` bên trong service | Tạo subscription tách rời, khiến caller không kiểm soát demand, lỗi và cancellation. | Trả publisher cho caller và để tầng sở hữu vòng đời thực hiện subscribe. |
| `buffer()` / `bufferTimeout()` | Tích lũy nhiều phần tử trước khi phát batch. | Giới hạn kích thước và thời gian batch; tính đến độ trễ và bộ nhớ. |
| `publishOn()` | Đưa xử lý sang scheduler khác và thường có hàng đợi/prefetch. | Chọn scheduler và prefetch phù hợp; tránh hàng đợi không giới hạn. |
| `flatMap()` | Cho phép nhiều inner publisher chạy đồng thời và thường có prefetch. | Giới hạn concurrency/prefetch; không mặc định rằng kết quả giữ thứ tự. |
| `onBackpressureBuffer()` | Có thể giữ phần tử khi downstream chậm. | Đặt giới hạn dung lượng và quy tắc khi buffer đầy. |

### 3.1. Thu thập toàn bộ dữ liệu

Đoạn code sau làm mất đặc tính streaming ở tầng service:

```java
public Mono<List<Reading>> loadAll(HistoryQuery query) {
    return repository.findByDeviceId(query.deviceId())
        .collectList();
}
```

`collectList()` phải đợi publisher nguồn hoàn tất rồi mới phát một `List`. Nếu nguồn có hàng triệu phần tử, toàn bộ danh sách có thể nằm trong heap trước khi client nhận được phần tử đầu tiên.

Nếu client cần duyệt dữ liệu theo thời gian, trả `Flux<Reading>` trực tiếp. Nếu nghiệp vụ cần một trang kết quả, dùng pagination với page size hữu hạn và trả từng trang; không dùng `collectList()` trên một nguồn không giới hạn.

### 3.2. Giới hạn concurrency và prefetch

`flatMap` hữu ích khi mỗi phần tử cần gọi một dịch vụ bất đồng bộ. Tuy nhiên, nếu không giới hạn concurrency, một nguồn nhanh có thể tạo quá nhiều tác vụ đang chờ:

```java
Flux<EnrichedReading> enriched = readings
    .flatMap(reading -> enrichmentService.enrich(reading), 8, 16);
```

Trong ví dụ, tối đa tám inner publisher được xử lý đồng thời; prefetch 16 điều chỉnh lượng phần tử được yêu cầu trước từ mỗi inner publisher theo API Reactor. Những con số này là lựa chọn cấu hình minh họa, cần đo tải thực tế. Nếu phải giữ thứ tự đầu vào, cân nhắc `concatMap`:

```java
Flux<EnrichedReading> ordered = readings
    .concatMap(enrichmentService::enrich);
```

`concatMap` giữ thứ tự xử lý nhưng giảm mức song song. Chọn toán tử dựa trên yêu cầu thứ tự và năng lực của dịch vụ downstream.

### 3.3. Giới hạn tốc độ upstream

`limitRate` có thể chia các yêu cầu upstream thành từng đợt nhỏ để tránh yêu cầu một lượng lớn phần tử trong một lần:

```java
Flux<Reading> controlled = repository
    .findByDeviceId(deviceId)
    .limitRate(64);
```

Đây là cách định hình demand bên trong pipeline. Nó không phải giới hạn số byte, không thay thế giới hạn buffer, và không bảo đảm mọi tầng phía dưới đều phát đúng 64 phần tử một lần. Các toán tử tiếp theo có thể tiếp tục thay đổi demand.

## 4. Nguồn dữ liệu có hỗ trợ backpressure và nguồn không hỗ trợ

Backpressure chỉ có thể đi tới nguồn nếu adapter hoặc driver chuyển được demand thành hành động đọc dữ liệu. Nguồn dữ liệu khác nhau có khả năng hỗ trợ khác nhau.

| Nguồn | Khả năng điều tiết | Cách thiết kế |
|---|---|---|
| R2DBC reactive database | Driver có thể đọc kết quả theo nhu cầu và hỗ trợ cancellation tùy driver/database. | Trả `Flux` trực tiếp; dùng query có giới hạn và kiểm tra hành vi cursor của driver. |
| Reactive HTTP client | Có thể truyền demand qua response body publisher. | Không gom body thành byte array lớn nếu cần streaming; giới hạn kích thước response. |
| Reactive message consumer | Phụ thuộc connector và broker; có thể dùng request/prefetch hoặc pause/resume. | Cấu hình prefetch, số consumer và ack policy; kiểm tra semantics của broker. |
| JDBC hoặc API blocking | Không có demand reactive tự nhiên trong thao tác blocking. | Chạy trên bounded scheduler, đọc theo trang hoặc theo batch hữu hạn. |
| Callback/hot event source | Có thể phát độc lập với tốc độ subscriber. | Dùng buffer hữu hạn, drop/latest hoặc pause/resume nếu nguồn hỗ trợ. |

### 4.1. Database reactive

Với R2DBC, repository trả `Flux` giúp driver có cơ hội đọc kết quả theo demand. Tuy nhiên, hành vi thực tế phụ thuộc driver, database và cách query được thực thi. Một query có sort hoặc aggregation lớn vẫn có thể khiến database cần tài nguyên đáng kể; backpressure ở ứng dụng không tự làm query rẻ hơn.

Hãy kết hợp streaming với:

- Điều kiện lọc và khoảng thời gian phù hợp.
- Index hỗ trợ điều kiện truy vấn và thứ tự sắp xếp.
- Projection chỉ lấy các cột cần thiết.
- Giới hạn kết quả hoặc pagination khi người dùng không cần toàn bộ lịch sử.
- Kiểm thử cancellation để chắc chắn cursor và connection được trả lại pool.

### 4.2. Nguồn blocking hoặc JDBC cũ

Nếu phải tích hợp một API blocking, không gọi nó trực tiếp trên event-loop thread. Có thể cô lập thao tác blocking trên bounded elastic scheduler:

```java
Mono<LegacySnapshot> snapshot = Mono
    .fromCallable(() -> legacyClient.fetchSnapshot(deviceId))
    .subscribeOn(Schedulers.boundedElastic());
```

Đoạn code này cô lập một lời gọi blocking, nhưng không biến API đó thành streaming. Nếu `fetchSnapshot` tải toàn bộ dữ liệu vào bộ nhớ, nó vẫn làm như vậy. Với tập dữ liệu lớn, nên dùng API phân trang hoặc cursor có kích thước hữu hạn:

```java
record LegacyPage(List<LegacyRow> rows, String nextCursor) {}

Flux<LegacyRow> fetchAllPages(String cursor) {
    return Flux.defer(() -> Mono
        .fromCallable(() -> legacyClient.fetchPage(deviceId, cursor, 200))
        .subscribeOn(Schedulers.boundedElastic())
        .flatMapMany(page -> Flux.fromIterable(page.rows())
            .concatWith(page.nextCursor() == null
                ? Flux.empty()
                : fetchAllPages(page.nextCursor()))
        )
    );
}

Flux<LegacyRow> rows = fetchAllPages(null);
```

Mỗi lần gọi API chỉ tải tối đa 200 bản ghi. `concatWith` chỉ subscribe trang tiếp theo sau khi các bản ghi của trang hiện tại đã được phát hết; `Flux.defer` giữ thao tác đọc trang ở dạng lazy. Đây là ví dụ minh họa, cần điều chỉnh theo kiểu cursor và semantics của API thực tế. Implementation production cần xử lý lỗi, cursor hết hạn, cancellation và xác nhận không truy vấn thêm trang sau khi downstream đã hủy. Cần kiểm tra API blocking không giữ một transaction hoặc connection quá lâu.

### 4.3. Nguồn hot và callback

Một nguồn hot như callback từ SDK thiết bị có thể phát sự kiện ngay cả khi subscriber chưa yêu cầu. Nguồn như vậy không tự động tôn trọng demand. Adapter phải định nghĩa hành vi khi consumer chậm:

- **Buffer hữu hạn:** giữ tối đa một số sự kiện rồi báo overflow hoặc áp dụng chính sách khi đầy.
- **Drop:** bỏ sự kiện mới hoặc cũ theo chính sách được chọn.
- **Latest:** chỉ giữ giá trị mới nhất khi các giá trị trung gian không còn hữu ích, ví dụ vị trí con trỏ.
- **Pause/resume:** yêu cầu nguồn tạm ngừng phát khi subscriber không theo kịp, nếu SDK hỗ trợ.
- **Durable queue:** ghi sự kiện vào kho bền vững nếu không thể mất dữ liệu.

Không nên chọn `LATEST` cho các lệnh tài chính hoặc sự kiện cần xử lý đầy đủ. Chính sách overflow phải dựa trên ý nghĩa dữ liệu, không chỉ dựa trên hiệu năng.

## 5. Truyền demand qua Request-Channel

Trong Request-Channel, có hai chuỗi demand độc lập. Với luồng client → server, server là subscriber của publisher lệnh từ client. Với luồng server → client, client là subscriber của publisher cập nhật từ server.

Ví dụ phía server nhận lệnh và trả cập nhật:

```java
@MessageMapping("device.control")
public Flux<DeviceState> control(Flux<DeviceCommand> commands) {
    return commands
        .concatMap(command -> deviceService.apply(command));
}
```

Demand của server đối với `commands` điều tiết số lệnh client gửi lên. Demand của client đối với `DeviceState` điều tiết số trạng thái server gửi xuống. `concatMap` xử lý lệnh tuần tự; nếu `deviceService.apply` chậm, nhu cầu đối với upstream giảm theo chuỗi reactive. Ngược lại, nếu client đọc trạng thái chậm, demand ở đầu ra có thể giảm độc lập mà không nhất thiết dừng việc client gửi lệnh lên.

Đừng dùng một hàng đợi vô hạn giữa hai hướng để che giấu chênh lệch tốc độ. Nếu cần tách tốc độ xử lý, hãy đặt giới hạn queue, xác định chính sách overflow và đo độ sâu queue.

## 6. Cancellation cũng phải đi xuyên qua các tầng

Backpressure không chỉ là yêu cầu thêm dữ liệu. Khi người dùng đóng màn hình hoặc hủy subscription, cancellation nên truyền ngược qua RSocket, handler, service và repository.

Ví dụ, khi client hủy `Flux<Reading>`:

1. Subscriber phía client gọi `cancel()`.
2. RSocket requester gửi tín hiệu hủy stream (CANCEL) tới responder.
3. Handler và publisher phía server nhận cancellation.
4. Service ngừng các tác vụ không còn cần thiết.
5. Repository/driver có cơ hội hủy query hoặc giải phóng cursor và connection.

Việc giải phóng tài nguyên phụ thuộc publisher và driver có hỗ trợ cancellation đúng cách hay không. Nếu service đã gọi `.subscribe()` tách rời hoặc chuyển công việc sang một executor mà không giữ handle hủy, công việc có thể tiếp tục chạy sau khi client rời đi.

Với `doFinally` có thể quan sát tín hiệu kết thúc hoặc hủy ở một tầng:

```java
public Flux<Reading> stream(String deviceId) {
    return repository.findByDeviceId(deviceId)
        .doFinally(signal -> log.debug(
            "Telemetry stream ended: device={}, signal={}",
            deviceId,
            signal
        ));
}
```

Không dùng log kết thúc như bằng chứng duy nhất rằng mọi tài nguyên bên dưới đã được giải phóng; hãy kiểm tra pool, cursor và tác vụ ngoài luồng trong integration test.

## 7. Cách thiết kế một pipeline có backpressure

Khi thiết kế luồng realtime hoặc lịch sử dữ liệu, hãy lần lượt trả lời:

1. **Ai là subscriber cuối?** Xác định UI, service khác hay broker tiêu thụ dữ liệu và cách nó yêu cầu phần tử.
2. **Demand được nối qua những tầng nào?** Mỗi tầng nên trả `Mono`/`Flux` và giữ publisher, thay vì tự subscribe hoặc thu thập toàn bộ.
3. **Nguồn có hỗ trợ demand không?** Kiểm tra driver, broker, callback API hoặc adapter có thể pause, cursor, pagination hay không.
4. **Operator nào tạo prefetch hoặc buffer?** Ghi rõ concurrency, prefetch, kích thước batch và giới hạn queue.
5. **Điều gì xảy ra khi consumer chậm?** Chọn chờ, buffer hữu hạn, drop/latest, giảm tốc độ nguồn hoặc lưu bền vững.
6. **Cancellation giải phóng được gì?** Kiểm tra query, cursor, connection, tác vụ và publisher phụ có dừng hay không.
7. **Quan sát bằng chỉ số nào?** Theo dõi demand, tốc độ phát/tiêu thụ, queue depth, thời gian xử lý, số lần overflow và số lần cancel.

Một pipeline có backpressure tốt không chỉ tránh lỗi bộ nhớ. Nó còn giúp hệ thống phản ứng ổn định khi tốc độ dữ liệu thay đổi, tránh tạo công việc không còn cần thiết và phân bổ tài nguyên theo năng lực thực tế của consumer.

## 8. Những lỗi thường gặp

- **Controller trả `List` thay vì `Flux`:** dữ liệu bị thu thập trước khi RSocket có thể truyền từng phần tử theo demand.
- **Service tự gọi `.subscribe()`:** caller mất quyền điều khiển demand, lỗi và cancellation.
- **Dùng `collectList()` cho nguồn lớn hoặc vô hạn:** toàn bộ dữ liệu có thể chiếm heap và không thể phát sớm.
- **Đặt `onBackpressureBuffer()` không giới hạn:** biến tốc độ producer vượt consumer thành tăng bộ nhớ không kiểm soát.
- **Dùng `flatMap` concurrency quá lớn:** nhiều tác vụ và kết quả chờ có thể đồng thời chiếm tài nguyên.
- **Tin rằng R2DBC làm query luôn rẻ:** driver reactive không thay thế index, giới hạn kết quả và thiết kế query.
- **Đưa API blocking lên event loop:** làm tắc các stream khác đang dùng chung event loop.
- **Không kiểm tra cancellation:** client đã rời phiên nhưng query hoặc callback vẫn tiếp tục tạo dữ liệu.

## 9. Kiểm thử và quan sát end-to-end

Để chứng minh demand được truyền xuyên qua các tầng, nên kiểm thử ở mức tích hợp thay vì chỉ kiểm tra một toán tử riêng lẻ:

1. Tạo nguồn dữ liệu có thể đếm số phần tử đã phát.
2. Subscribe client với demand ban đầu nhỏ, ví dụ 5 phần tử; xác nhận server không đọc trước một lượng lớn ngoài mức prefetch/buffer đã cấu hình.
3. Yêu cầu thêm một lượng phần tử và xác nhận nguồn tiếp tục phát tương ứng, có tính đến prefetch của các operator.
4. Hủy subscription giữa luồng; xác nhận CANCEL tới server và nguồn dừng đọc hoặc giải phóng cursor.
5. Làm consumer chậm; xác nhận queue không tăng vô hạn và chính sách overflow hoạt động.
6. Chèn `collectList`, `publishOn`, `flatMap` hoặc adapter blocking vào pipeline thử nghiệm để quan sát cách demand/buffer thay đổi.
7. Với Request-Channel, kiểm thử demand riêng cho luồng lệnh và luồng cập nhật.

Trong production, quan sát tối thiểu số phần tử được yêu cầu, số phần tử phát ra, số phần tử tiêu thụ, prefetch/concurrency, queue depth, thời gian query, thời gian xử lý từng phần tử, số lần cancel và số lần overflow. Chỉ số cần được gắn với stream hoặc correlation ID để có thể lần theo một phiên cụ thể.

## 10. Kết luận

Demand chỉ thực sự kiểm soát được tải khi được truyền xuyên suốt từ subscriber RSocket qua handler, service và repository tới nguồn dữ liệu. Giữ `Mono`/`Flux` qua các tầng, tránh `block()`, `subscribe()` và thu thập toàn bộ dữ liệu ngoài ý muốn; kiểm soát prefetch, concurrency và buffer; dùng adapter phù hợp cho nguồn blocking hoặc hot; và xác nhận cancellation giải phóng tài nguyên. Khi nguồn không thể tôn trọng demand, hãy chọn chính sách hữu hạn như pause/resume, batch, drop/latest hoặc durable queue dựa trên ý nghĩa nghiệp vụ.
