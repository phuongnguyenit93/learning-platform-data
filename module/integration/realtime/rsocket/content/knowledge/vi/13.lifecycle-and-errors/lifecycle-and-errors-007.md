# Truyền tín hiệu hủy xuống nguồn dữ liệu và tác vụ nền

Trong ứng dụng realtime, client có thể rời màn hình, đóng phiên cộng tác hoặc không còn cần một luồng dữ liệu đang chạy. Khi đó, việc ngừng gửi dữ liệu về client mới chỉ là một nửa công việc. Server còn cần dừng query, đóng cursor, hủy timer và ngăn các tác vụ nền tiếp tục tiêu thụ CPU hoặc kết nối.

RSocket có frame `CANCEL` để requester hủy một stream đang hoạt động. Trong ứng dụng Java reactive, tín hiệu này cần được truyền tiếp thành `cancel()` qua publisher, service, repository và nguồn dữ liệu. Bài học này tập trung vào cách giữ vòng đời của công việc gắn với vòng đời request, giải phóng tài nguyên đúng cách và nhận biết những loại công việc không thể dừng tức thời.

## 1. Hủy stream ở cấp RSocket

Khi requester không còn quan tâm đến một tương tác đang hoạt động, nó có thể hủy subscription. Ở cấp giao thức, RSocket biểu diễn thao tác này bằng frame **`CANCEL`**, Frame Type `0x09`, mang Stream ID của tương tác cần hủy.

Ví dụ, client đang nhận luồng dữ liệu cảm biến từ server:

```text
Client                                      Server
  |                                            |
  |---------- REQUEST_STREAM ----------------->|
  |                                            |
  |<------------- PAYLOAD ---------------------|
  |<------------- PAYLOAD ---------------------|
  |<------------- PAYLOAD ---------------------|
  |                                            |
  |------------- CANCEL --------------------->|
  |                                            | dừng publisher
  |                                            | giải phóng tài nguyên
```

`CANCEL` hủy stream tương ứng. Với Request-Stream, requester thường gửi frame này khi subscriber hủy. Với Request-Channel, requester hủy toàn bộ tương tác channel đang mở; việc hoàn tất một hướng gửi bằng cờ `C` trong `PAYLOAD` là half-close, không giống hủy toàn bộ stream.

Ở phía ứng dụng reactive, `cancel()` là tín hiệu điều khiển vòng đời của subscription. Nó không phải `onComplete` hay `onError`, và subscriber không nhận một tín hiệu terminal mới để thông báo rằng việc hủy đã xảy ra. Vì vậy, không nên chỉ dùng `doOnComplete` để dọn tài nguyên khi stream có thể bị hủy.

## 2. Tín hiệu hủy phải đi xuyên qua các tầng

Một pipeline reactive có thể truyền cancellation ngược từ subscriber tới publisher upstream nếu mỗi tầng giữ và kết hợp publisher đúng cách:

```text
Client UI / Subscriber
        |
        | cancel()
        v
RSocket requester
        |
        | CANCEL (Stream ID)
        v
RSocket responder
        |
        v
@MessageMapping handler
        |
        v
Service publisher
        |
        v
Repository / driver
        |
        v
Database cursor / query
```

Ví dụ, handler phát luồng telemetry:

```java
@Controller
public class TelemetrySocketController {
    private final TelemetryService telemetryService;

    public TelemetrySocketController(TelemetryService telemetryService) {
        this.telemetryService = telemetryService;
    }

    @MessageMapping("telemetry.live")
    public Flux<Reading> live(LiveQuery query) {
        return telemetryService.stream(query.deviceId())
            .doOnCancel(() -> log.debug(
                "Telemetry stream cancelled: device={}", query.deviceId()
            ));
    }
}
```

Service giữ publisher từ repository:

```java
public Flux<Reading> stream(String deviceId) {
    return repository.findLiveReadings(deviceId)
        .map(this::toReading);
}
```

Khi client hủy subscription, responder nhận `CANCEL`; cancellation đi qua handler và service tới publisher của repository. Driver có thể dùng tín hiệu này để dừng đọc hoặc đóng cursor nếu hỗ trợ. `doOnCancel` chỉ ghi nhận sự kiện; nó không tự hủy một công việc độc lập mà service đã tạo ra bên ngoài publisher.

Để propagation hoạt động, các tầng nên trả `Mono`/`Flux` cho tầng gọi và kết hợp bằng toán tử reactive. Nếu service gọi `.subscribe()` riêng rồi trả về một publisher khác, subscription độc lập đó không tự động bị hủy khi client hủy stream.

## 3. Phân biệt giảm demand và hủy subscription

Hai trạng thái này có ý nghĩa khác nhau:

| Trạng thái | Ý nghĩa | Hành vi mong đợi |
|---|---|---|
| Demand tạm thời bằng `0` | Subscriber hiện chưa yêu cầu thêm phần tử. | Publisher giữ trạng thái và chờ demand mới; stream vẫn còn sống. |
| `cancel()` | Subscriber không còn quan tâm đến subscription. | Publisher dừng phát, giải phóng công việc và không phát thêm phần tử cho subscriber đó. |
| `onComplete` | Publisher đã phát xong dữ liệu bình thường. | Dọn tài nguyên theo nhánh hoàn tất. |
| `onError` | Publisher kết thúc do lỗi. | Dọn tài nguyên theo nhánh lỗi và truyền lỗi đến subscriber. |

Ví dụ, một giao diện tạm thời không cần thêm dữ liệu vì đang xử lý frame trước có thể giảm demand; không nên hủy stream nếu nó vẫn cần nhận dữ liệu sau đó. Ngược lại, khi người dùng đóng màn hình, hủy subscription giúp server dừng công việc gắn với màn hình đó.

## 4. Dọn tài nguyên theo mọi đường kết thúc

Một publisher có thể kết thúc bằng hoàn tất, lỗi hoặc cancellation. Các hook Reactor có mục đích khác nhau:

- `doOnCancel(...)` chạy khi subscription bị hủy.
- `doFinally(...)` chạy sau khi kết thúc bằng complete, error hoặc cancel; có thể kiểm tra `SignalType` để phân biệt.
- `doOnError(...)` quan sát lỗi nhưng không thay thế việc giải phóng tài nguyên.
- `using(...)` phù hợp với tài nguyên có thao tác đóng đồng bộ.
- `usingWhen(...)` phù hợp khi việc acquire/release tài nguyên là bất đồng bộ và cần xử lý riêng complete, error, cancel.

Ví dụ ghi nhận lý do kết thúc:

```java
Flux<Reading> stream(String deviceId) {
    return repository.findLiveReadings(deviceId)
        .doFinally(signal -> log.info(
            "Stream ended: device={}, signal={}", deviceId, signal
        ));
}
```

`doFinally` giúp quan sát cả ba đường kết thúc. Nếu chỉ cần hành động khi cancel, dùng `doOnCancel`. Callback của các hook nên ngắn và không blocking; không nên gọi thao tác I/O đồng bộ hoặc chờ một tác vụ khác hoàn tất ngay trên callback hủy.

### 4.1. Tài nguyên cần đóng bất đồng bộ

Giả sử một publisher tự mở cursor và cursor có phương thức `close()` trả về `Mono<Void>`. Có thể gắn vòng đời cursor với publisher bằng `usingWhen`:

```java
Flux<Row> rows = Flux.usingWhen(
    cursorFactory.open(),
    Cursor::readRows,
    Cursor::close,
    (cursor, error) -> cursor.close(),
    Cursor::close
);
```

Trong ví dụ, `usingWhen` dùng nhánh cleanup tương ứng khi nguồn hoàn tất, phát lỗi hoặc bị hủy. `Cursor` và `cursorFactory` là kiểu minh họa của ứng dụng; API thực tế phụ thuộc thư viện truy cập dữ liệu. Cần ghi nhận lỗi cleanup và kiểm tra driver có thực sự hủy truy vấn/đóng cursor khi subscription bị cancel hay không.

Không phải mọi tài nguyên đều được giải phóng chỉ bằng `doFinally`. Hook này quan sát tín hiệu; `usingWhen` hoặc cơ chế quản lý tài nguyên tương ứng mới gắn thao tác acquire/release với vòng đời publisher.

## 5. Hủy query và công việc ở tầng dữ liệu

### 5.1. Database reactive

Với R2DBC, repository có thể trả `Flux` để driver đọc dữ liệu theo demand. Khi downstream hủy, driver có cơ hội hủy việc đọc kết quả, dừng query hoặc giải phóng cursor/connection. Mức độ hỗ trợ phụ thuộc driver và database; không nên giả định tất cả truy vấn đều dừng ngay lập tức.

Các điểm cần kiểm tra:

- Query đang chạy có nhận cancellation từ driver hay không.
- Cursor hoặc result publisher có được đóng khi subscription bị hủy hay không.
- Connection có được trả lại pool sau khi cleanup hoàn tất hay không.
- Query có đang thực hiện thao tác ghi hoặc commit hay không; cancellation không tự động hoàn tác tác động đã commit.
- Timeout ở database và timeout ở RSocket có được cấu hình nhất quán hay không.

Với JDBC, thao tác blocking không tự hỗ trợ Reactive Streams cancellation. Nếu cần dùng JDBC cũ, cô lập nó trên scheduler phù hợp, đọc theo trang hữu hạn và dùng cơ chế cancel của driver nếu driver hỗ trợ. Việc hủy một `Future` không đảm bảo câu lệnh SQL đã dừng; phải kiểm tra hành vi thực tế của JDBC driver và database.

### 5.2. HTTP request và kết nối tới dịch vụ khác

Nếu service gọi một reactive HTTP client và trả publisher đó về handler, cancellation có thể truyền tới HTTP client để hủy request hoặc ngừng đọc response body. Điều này phụ thuộc connector và trạng thái request; nếu server downstream đã thực hiện tác động nghiệp vụ, việc client hủy response không có nghĩa tác động đó đã được rollback.

### 5.3. Timer và nguồn sự kiện

Các nguồn như `Flux.interval`, `Flux.create` hoặc callback SDK cần được quản lý vòng đời. Khi publisher bị hủy, timer nên bị dispose và callback listener nên được unregister. Ví dụ adapter cho SDK có thể dùng `Flux.create` và đăng ký cleanup:

```java
Flux<DeviceEvent> events = Flux.create(sink -> {
    Listener listener = event -> sink.next(event);
    deviceSdk.addListener(listener);

    sink.onDispose(() -> deviceSdk.removeListener(listener));
});
```

`onDispose` chạy khi sink bị hủy hoặc kết thúc; nhờ đó listener được gỡ khỏi SDK khi subscription không còn hoạt động. API callback thực tế cần đảm bảo `removeListener` an toàn khi được gọi đồng thời với callback đang phát sự kiện. Nếu nguồn có thể phát đồng thời, cần chọn cách serialize hoặc đồng bộ phù hợp.

## 6. Hủy tác vụ nền và giới hạn của interrupt

Một tác vụ chạy trên `ExecutorService`, `Future` hoặc API blocking không tự động dừng chỉ vì RSocket stream bị hủy. Ứng dụng phải giữ handle của tác vụ và nối cancellation với thao tác hủy tương ứng.

Ví dụ minh họa với `Future`:

```java
Mono<Report> generateReport(String deviceId) {
    return Mono.create(sink -> {
        Future<?> task = executor.submit(() -> {
            try {
                Report report = reportGenerator.generate(deviceId);
                sink.success(report);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                sink.error(ex);
            } catch (Exception error) {
                sink.error(error);
            }
        });

        sink.onCancel(() -> task.cancel(true));
    });
}
```

Khi subscriber hủy, `task.cancel(true)` yêu cầu hủy tác vụ và có thể gửi interrupt tới thread đang chạy. Tác vụ chỉ dừng kịp thời nếu code bên trong thường xuyên kiểm tra interrupt hoặc gọi API có hỗ trợ interrupt. Nếu đang ở thư viện native, I/O blocking không hỗ trợ interrupt hoặc đoạn code bỏ qua interrupt, công việc có thể tiếp tục chạy.

Với tác vụ dài, hãy chia công việc thành các bước có thể kiểm tra cancellation, đặt timeout, giới hạn số worker và giải phóng tài nguyên trong `finally`. Không được nuốt `InterruptedException` rồi tiếp tục chạy; thường cần khôi phục cờ interrupt như ví dụ.

Nếu dùng `CompletableFuture`, hủy future cũng không bảo đảm computation nền đã dừng. Hành vi phụ thuộc executor và cách computation được triển khai. Nếu cần dừng thật sự, giữ `Future` từ executor hoặc một cancellation token mà tác vụ chủ động kiểm tra.

## 7. Công việc gắn với request và công việc phải tiếp tục sau khi client rời đi

Không phải mọi tác vụ bắt đầu từ một request đều nên bị hủy khi client ngắt kết nối. Cần phân biệt hai loại:

| Loại công việc | Vòng đời | Cách xử lý khi client hủy |
|---|---|---|
| Truy vấn dữ liệu cho màn hình đang mở | Gắn với subscription của màn hình | Hủy query, đóng cursor và dừng phép biến đổi không còn cần thiết. |
| Theo dõi telemetry trực tiếp | Gắn với phiên theo dõi | Unsubscribe khỏi nguồn và gỡ listener. |
| Tính toán preview hoặc gợi ý tạm thời | Thường gắn với request | Hủy nếu không còn người nhận và có thể dừng an toàn. |
| Tạo báo cáo đã được người dùng đặt hàng | Có thể cần hoàn tất độc lập | Ghi job bền vững, trả job ID/trạng thái rồi xử lý qua worker riêng. |
| Thanh toán hoặc cập nhật nghiệp vụ đã được chấp nhận | Theo vòng đời giao dịch nghiệp vụ | Không dùng disconnect làm tín hiệu rollback; quản lý giao dịch và trạng thái rõ ràng. |

Với công việc phải tiếp tục sau khi client rời đi, hãy tách nó khỏi subscription của request. Một quy trình thường dùng:

1. Xác thực và kiểm tra yêu cầu.
2. Lưu job hoặc sự kiện vào database/outbox hay hàng đợi bền vững.
3. Chỉ sau khi lưu thành công, trả xác nhận hoặc job ID cho client bằng Request-Response.
4. Worker độc lập đọc job, xử lý, cập nhật trạng thái và retry theo chính sách.
5. Client có thể truy vấn trạng thái hoặc đăng ký nhận cập nhật qua Request-Stream.

Nhờ vậy, vòng đời của công việc được quản lý bởi hàng đợi và trạng thái job, không phụ thuộc vào việc socket của người dùng còn mở hay không. Nếu nghiệp vụ không cần phản hồi xác nhận, vẫn cần ghi rõ mức độ bền vững và cách người dùng kiểm tra kết quả.

## 8. Race condition và tính an toàn khi cleanup

Cancellation có thể đến gần cùng thời điểm publisher hoàn tất hoặc phát lỗi. Vì vậy, cleanup cần an toàn khi được kích hoạt trong các tình huống cạnh tranh:

- **Idempotent cleanup:** đóng cursor, unregister listener hoặc release permit nhiều lần không gây lỗi hoặc giải phóng nhầm tài nguyên.
- **Không phát dữ liệu sau cancel:** publisher và callback cần kiểm tra trạng thái hủy trước khi tiếp tục phát hoặc lập lịch công việc mới.
- **Không chặn event loop:** cleanup đồng bộ phải ngắn; cleanup I/O nên dùng cơ chế bất đồng bộ như `usingWhen` hoặc scheduler phù hợp.
- **Không giả định rollback:** hủy subscription chỉ dừng việc truyền/tiêu thụ dữ liệu; transaction đã commit hoặc side effect bên ngoài cần cơ chế bù trừ riêng.
- **Giới hạn thời gian cleanup:** tránh để việc đóng một tài nguyên treo vô hạn; theo dõi lỗi và timeout cleanup.

Khi một tác vụ đã thực hiện side effect, hủy phần còn lại không xóa được tác động đã xảy ra. Với thao tác không thể lặp hoặc không thể đảo ngược, hãy dùng idempotency key, trạng thái giao dịch và quy trình bù trừ.

## 9. Kiểm thử cancellation end-to-end

Không chỉ kiểm tra rằng client ngừng nhận dữ liệu. Cần kiểm tra nguồn và công việc phía server cũng dừng hoặc được giải phóng:

1. Tạo publisher test có thể ghi nhận khi `cancel()` được gọi.
2. Mở Request-Stream từ client, nhận một vài payload rồi hủy subscription.
3. Xác nhận responder nhận `CANCEL` và publisher upstream nhận cancellation.
4. Với R2DBC, kiểm tra query/cursor kết thúc và connection được trả lại pool.
5. Với callback SDK, xác nhận listener được unregister đúng một lần.
6. Với `Future`, xác nhận interrupt/cancel được gửi và tác vụ hợp tác dừng trong thời gian giới hạn.
7. Giả lập cancel đồng thời với complete/error; xác nhận cleanup không chạy lặp gây lỗi hoặc rò rỉ tài nguyên.
8. Với durable job, ngắt kết nối sau khi job được lưu; xác nhận worker vẫn xử lý và trạng thái job có thể truy vấn.

Trong Reactor, `StepVerifier` có thể kiểm tra cancellation ở cấp publisher:

```java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> source = Flux.interval(Duration.ofMillis(50))
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source)
    .expectNext(0L)
    .thenCancel()
    .verify();

assertThat(cancelled).isTrue();
```

Đây là unit test cho publisher. Integration test vẫn cần xác nhận frame CANCEL, hành vi driver, listener và tài nguyên thật được giải phóng trên transport đang triển khai.

## 10. Những lỗi thường gặp

- **Chỉ dừng gửi dữ liệu mà không hủy nguồn:** query, timer hoặc listener vẫn tiếp tục hoạt động.
- **Chỉ dùng `doOnComplete` để cleanup:** cancellation không phát `onComplete`, nên cleanup bị bỏ qua.
- **Tự gọi `.subscribe()` trong service:** tạo công việc độc lập không gắn với vòng đời request.
- **Cho rằng `Future.cancel(true)` luôn dừng code:** interrupt là yêu cầu hợp tác; code blocking hoặc bỏ qua interrupt có thể tiếp tục chạy.
- **Dùng disconnect để rollback nghiệp vụ:** tác động đã commit hoặc side effect ngoài hệ thống không tự được hoàn tác.
- **Dùng cancellation cho job cần hoàn tất:** client đóng màn hình khiến công việc quan trọng bị dừng giữa chừng; cần durable job/queue.
- **Cleanup không idempotent:** race giữa cancel và complete có thể đóng tài nguyên nhiều lần hoặc gây lỗi thứ cấp.

## 11. Kết luận

`CANCEL` ở RSocket cần được nối với `cancel()` của Reactive Streams và truyền qua handler, service, repository tới query, cursor, timer, listener hoặc tác vụ nền. Giữ publisher trong cùng chuỗi reactive, dùng `doOnCancel`/`doFinally` để quan sát và `usingWhen` để quản lý tài nguyên bất đồng bộ. Với công việc blocking, interrupt chỉ có tác dụng khi tác vụ hợp tác; với công việc cần tiếp tục sau khi client rời đi, hãy lưu thành durable job và quản lý vòng đời độc lập. Kiểm thử cả tín hiệu hủy lẫn việc tài nguyên thực sự được giải phóng để tránh rò rỉ và công việc chạy vô ích.
