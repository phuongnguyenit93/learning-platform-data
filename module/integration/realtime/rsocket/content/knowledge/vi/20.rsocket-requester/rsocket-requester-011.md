# Đặt timeout, hủy đăng ký và xử lý lỗi trong chuỗi gọi

Khi gọi RSocket bằng Spring `RSocketRequester`, mỗi tương tác trả về một publisher Reactor như `Mono<T>`, `Flux<T>` hoặc `Mono<Void>`. Nhờ vậy, client có thể đặt giới hạn thời gian, xử lý lỗi và hủy công việc bằng các toán tử reactive. Tuy nhiên, timeout, cancellation và lỗi kết nối là những tín hiệu khác nhau; nếu xử lý nhầm, ứng dụng có thể retry lệnh đã chạy, giữ stream không cần thiết hoặc che mất nguyên nhân sự cố.

Trong module `INTEGRATION_REALTIME_RSOCKET`, requester có thể khởi tạo Request-Response, Fire-and-Forget, Request-Stream và Request-Channel qua TCP hoặc WebSocket. Bài này tập trung vào việc quản lý vòng đời các publisher đó từ lúc kết nối, gửi request, nhận dữ liệu cho tới khi hoàn tất, timeout hoặc bị hủy.

## 1. Ba loại thời gian chờ cần phân biệt

Không có một timeout duy nhất điều khiển toàn bộ RSocket. Ứng dụng thường cần phân biệt ít nhất ba lớp:

| Loại timeout | Áp dụng cho | Câu hỏi được trả lời |
|---|---|---|
| Connection timeout | Quá trình mở transport và thiết lập RSocket session | Mất bao lâu mà client vẫn chưa kết nối/SETUP thành công? |
| Request timeout | Một Request-Response hoặc thao tác gửi cụ thể | Bao lâu mà tương tác này chưa hoàn tất? |
| Stream idle timeout | Request-Stream hoặc Request-Channel | Bao lâu mà stream không phát thêm phần tử? |

Ngoài ra còn có KEEPALIVE interval/Max Lifetime ở cấp kết nối, idle timeout của proxy/NAT và timeout của database hoặc dịch vụ downstream. Những giới hạn này giải quyết các vấn đề khác nhau và cần được cấu hình có chủ đích.

## 2. Timeout khi tạo kết nối

`connectTcp(...)` và `connectWebSocket(...)` trả về `Mono<RSocketRequester>`. Có thể áp dụng Reactor `timeout` để giới hạn thời gian chờ kết nối và SETUP hoàn tất:

```java
Mono<RSocketRequester> requesterMono = RSocketRequester.builder()
    .connectTcp("rsocket-service", 7000)
    .timeout(Duration.ofSeconds(5));
```

Với WebSocket:

```java
Mono<RSocketRequester> requesterMono = RSocketRequester.builder()
    .connectWebSocket(URI.create("wss://api.example.com/rsocket"))
    .timeout(Duration.ofSeconds(5));
```

Nếu publisher kết nối không phát requester trước thời hạn, Reactor phát `TimeoutException` và hủy subscription upstream. Transport/connector sẽ được yêu cầu dừng quá trình thiết lập nếu nó còn đang chạy. Đây là giới hạn ở tầng ứng dụng; cấu hình connect timeout riêng của Netty/transport vẫn có thể cần thiết để kiểm soát quá trình mở socket.

Timeout khi kết nối không giống timeout của một request được gửi sau đó. Khi đã có requester, mỗi tương tác cần chính sách thời gian phù hợp với nghiệp vụ riêng.

## 3. Request-Response: giới hạn thời gian cho một kết quả

Request-Response thường trả về `Mono<T>`. Dùng `.timeout(Duration)` để giới hạn thời gian chờ kết quả:

```java
Mono<DeviceStatus> status = requester
    .route("devices.{deviceId}.status.get", deviceId)
    .data(new StatusQuery())
    .retrieveMono(DeviceStatus.class)
    .timeout(Duration.ofSeconds(3));
```

Nếu server không trả kết quả trong ba giây, publisher kết thúc bằng `TimeoutException`. Reactor hủy subscription tới request đang chạy; khi stream RSocket đã được tạo, implementation có thể gửi frame `CANCEL` để server dừng công việc gắn với stream.

### 3.1. Chuyển lỗi kỹ thuật thành lỗi miền nghiệp vụ

Có thể dùng `onErrorMap` để chuyển timeout thành ngoại lệ mà tầng trên hiểu:

```java
Mono<DeviceStatus> status = requester
    .route("devices.{deviceId}.status.get", deviceId)
    .data(new StatusQuery())
    .retrieveMono(DeviceStatus.class)
    .timeout(Duration.ofSeconds(3))
    .onErrorMap(TimeoutException.class,
        error -> new DeviceQueryTimeoutException(deviceId, error));
```

`onErrorMap` giữ nguyên việc kết thúc bằng lỗi nhưng đổi loại lỗi. Tầng controller hoặc API boundary có thể ánh xạ `DeviceQueryTimeoutException` thành phản hồi phù hợp. Không nên chuyển mọi lỗi thành timeout; lỗi xác thực, route không tồn tại và lỗi nghiệp vụ cần giữ nguyên ý nghĩa.

### 3.2. Dùng fallback có chủ đích

`onErrorResume` thay publisher lỗi bằng một publisher khác. Ví dụ, nếu trạng thái realtime không phản hồi kịp, sản phẩm có thể cho phép đọc bản cache gần nhất:

```java
Mono<DeviceStatus> status = requester
    .route("devices.{deviceId}.status.get", deviceId)
    .data(new StatusQuery())
    .retrieveMono(DeviceStatus.class)
    .timeout(Duration.ofSeconds(3))
    .onErrorResume(TimeoutException.class,
        error -> statusCache.findLatest(deviceId));
```

Fallback phải phù hợp với ý nghĩa dữ liệu. Nếu cache không có giá trị hoặc dữ liệu quá cũ, hãy trả lỗi rõ ràng hoặc kèm timestamp/staleness để caller không nhầm dữ liệu cũ là kết quả realtime mới nhất.

## 4. Request-Stream: timeout giữa các phần tử

Request-Stream trả `Flux<T>`. Khác với `Mono`, một stream có thể chạy lâu và phát nhiều phần tử. Khi gọi:

```java
Flux<TelemetryReading> readings = requester
    .route("devices.{deviceId}.telemetry.watch", deviceId)
    .data(new WatchRequest())
    .retrieveFlux(TelemetryReading.class)
    .timeout(Duration.ofSeconds(20));
```

`timeout(Duration)` trên `Flux` là timeout theo khoảng im lặng: nó áp dụng khi chờ phần tử đầu tiên và được đặt lại sau mỗi phần tử tiếp theo. Nếu không có `onNext` trong 20 giây, stream phát `TimeoutException` và subscription upstream bị hủy.

Đây là **idle timeout**, phù hợp khi server được kỳ vọng gửi dữ liệu hoặc heartbeat thường xuyên. Nếu thiết bị có thể không phát telemetry trong thời gian dài theo thiết kế, timeout 20 giây có thể tạo lỗi giả. Khi đó, hãy chọn thời hạn dựa trên nhịp dữ liệu thực tế hoặc dùng tín hiệu heartbeat ở tầng ứng dụng.

### 4.1. Idle timeout khác giới hạn tổng thời gian stream

`Flux.timeout(Duration)` không giới hạn tổng tuổi thọ của subscription. Nếu mỗi phần tử đều đến trong vòng 20 giây, stream có thể chạy nhiều giờ.

Nếu chỉ muốn một phiên theo dõi tồn tại tối đa 10 phút, có thể dùng:

```java
Flux<TelemetryReading> readings = requester
    .route("devices.{deviceId}.telemetry.watch", deviceId)
    .data(new WatchRequest())
    .retrieveFlux(TelemetryReading.class)
    .take(Duration.ofMinutes(10));
```

`take(Duration)` kết thúc stream bình thường khi hết thời lượng và hủy upstream. Nếu nghiệp vụ cần phân biệt “đã hết thời hạn phiên” với “server hoàn tất bình thường”, hãy phát một trạng thái kết thúc riêng hoặc dùng timer/timeout signal phù hợp; đừng mặc định `take` tạo `TimeoutException`.

## 5. Fire-and-Forget: timeout không phải xác nhận xử lý

Fire-and-Forget dùng `send()` và trả về `Mono<Void>`:

```java
Mono<Void> send = requester
    .route("telemetry.publish")
    .data(event)
    .send()
    .timeout(Duration.ofSeconds(2));
```

Timeout giới hạn thời gian chờ thao tác gửi phía client hoàn tất theo API. `send()` hoàn tất không phải xác nhận rằng server đã xử lý event, lưu dữ liệu hay hoàn thành side effect. Ngược lại, timeout hoặc lỗi transport cũng không chứng minh server chưa nhận payload: server có thể đã nhận hoặc xử lý trước khi kết nối bị ngắt.

Nếu sự kiện có thể gửi lại, hãy dùng `eventId` ổn định và handler idempotent. Với dữ liệu không được phép mất, lưu sự kiện vào outbox hoặc durable queue trước khi gửi, rồi theo dõi trạng thái bằng một tương tác xác nhận riêng. Không retry Fire-and-Forget vô điều kiện.

## 6. Request-Channel: quản lý hai luồng và cancellation

Request-Channel nhận một publisher từ client và trả một luồng phản hồi. Ví dụ:

```java
Flux<DeviceUpdate> updates = requester
    .route("devices.{deviceId}.control.channel", deviceId)
    .data(commands, DeviceCommand.class)
    .retrieveFlux(DeviceUpdate.class)
    .timeout(Duration.ofSeconds(30))
    .doOnCancel(() -> log.info("Control channel cancelled: {}", deviceId))
    .doFinally(signal -> metrics.recordChannelTermination(deviceId, signal));
```

Ở đây, 30 giây là khoảng tối đa chờ một phần tử đầu ra tiếp theo. Nếu server có thể không gửi update trong thời gian đó dù vẫn nhận lệnh, timeout này không phù hợp; hãy định nghĩa heartbeat hoặc timeout theo giao thức ứng dụng.

Khi subscriber hủy `updates`, cancellation được truyền tới tương tác channel. RSocket có thể gửi `CANCEL` để hủy toàn bộ channel; publisher `commands` cần được hủy theo vòng đời tương tác. Nếu chỉ muốn requester ngừng gửi lệnh nhưng vẫn nhận update cuối cùng, hoàn tất publisher đầu vào theo cách half-close phù hợp thay vì hủy toàn bộ subscription.

## 7. Cancellation không phải một error signal

Trong Reactive Streams, cancellation là tín hiệu điều khiển từ subscriber tới subscription. Nó không gọi `onError` và cũng không gọi `onComplete` cho subscriber.

| Toán tử | Khi nào chạy? | Dùng cho việc gì? |
|---|---|---|
| `doOnError(...)` | Publisher phát lỗi | Ghi log/metric lỗi hoặc quan sát nguyên nhân. |
| `onErrorMap(...)` | Publisher phát lỗi | Chuyển lỗi kỹ thuật thành lỗi miền nghiệp vụ. |
| `onErrorResume(...)` | Publisher phát lỗi | Chọn fallback hoặc publisher thay thế. |
| `doOnCancel(...)` | Subscriber hủy | Ghi nhận hoặc kích hoạt hành động ngắn khi hủy. |
| `doFinally(...)` | Complete, error hoặc cancel | Thu thập trạng thái kết thúc và cleanup chung. |

Ví dụ ghi nhận cả lỗi lẫn lý do kết thúc:

```java
Flux<TelemetryReading> readings = requester
    .route("devices.{deviceId}.telemetry.watch", deviceId)
    .data(new WatchRequest())
    .retrieveFlux(TelemetryReading.class)
    .doOnError(error -> log.warn("Telemetry stream failed", error))
    .doOnCancel(() -> log.debug("Telemetry stream cancelled"))
    .doFinally(signal -> log.info("Telemetry stream ended: {}", signal));
```

`doFinally` nhận `SignalType` như `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`. Callback nên ngắn và không blocking. Nếu cần giải phóng tài nguyên bất đồng bộ, hãy gắn cleanup vào publisher bằng cơ chế như `usingWhen`; không chỉ ghi log rồi để query/listener tiếp tục chạy.

`onErrorResume` không xử lý cancellation. Nếu client đã hủy, fallback không được chạy để tự mở một stream mới. Đây là điểm quan trọng để tránh vô tình tạo subscription mới sau khi người dùng rời màn hình.

## 8. Xử lý lỗi theo interaction model

Mỗi interaction model có hình dạng lỗi khác nhau:

| Model | Kết quả bình thường | Lỗi thường gặp | Cách xử lý |
|---|---|---|---|
| Request-Response | Một giá trị hoặc empty completion | Application ERROR, timeout, transport đóng | `onErrorMap`/`onErrorResume`; retry chỉ khi an toàn. |
| Fire-and-Forget | `Mono<Void>` hoàn tất gửi | Lỗi encode, gửi hoặc transport | Log/metric, outbox hoặc retry có idempotency; không coi send completion là ack nghiệp vụ. |
| Request-Stream | Nhiều phần tử rồi complete | Lỗi giữa stream, idle timeout, disconnect | Quyết định kết thúc, fallback hoặc subscribe lại từ checkpoint. |
| Request-Channel | Hai hướng trao đổi cùng lúc | Lỗi một phía, cancellation, disconnect | Hủy tài nguyên liên quan; khôi phục phiên bằng sequence/event ID nếu cần. |

Lỗi ứng dụng từ peer, lỗi giao thức, lỗi transport và timeout ở client có thể được biểu diễn bằng các exception khác nhau tùy phiên bản Spring/RSocket Java. Nên phân loại theo loại lỗi và nguyên nhân gốc thay vì chỉ bắt `Exception` rồi trả một thông báo chung.

## 9. Retry: tạo lại subscription có thể gửi lại request

`retryWhen` subscribe lại vào publisher khi có lỗi phù hợp. Với publisher xây dựng từ `RSocketRequester`, điều này có thể tạo một tương tác RSocket mới. Nếu server đã thực hiện side effect nhưng response bị mất, retry có thể khiến cùng một lệnh chạy lần thứ hai.

Ví dụ retry có giới hạn cho một truy vấn idempotent:

```java
Mono<DeviceStatus> status = requester
    .route("devices.{deviceId}.status.get", deviceId)
    .data(new StatusQuery())
    .retrieveMono(DeviceStatus.class)
    .timeout(Duration.ofSeconds(3))
    .retryWhen(Retry.backoff(2, Duration.ofMillis(300))
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5)
        .filter(this::isTransientFailure));
```

Retry ở ví dụ này chỉ nên dùng khi truy vấn có thể lặp an toàn và lỗi được phân loại là tạm thời. `isTransientFailure` là chính sách do ứng dụng định nghĩa; không nên retry lỗi validation, authorization hoặc lỗi nghiệp vụ không thể tự hết.

### 9.1. Retry với thao tác thay đổi trạng thái

Với lệnh điều khiển, thanh toán hoặc ghi dữ liệu, timeout không cho biết server đã thực hiện hay chưa. Nếu retry, hãy gửi cùng một idempotency key hoặc command ID để server nhận diện lần lặp:

```java
public record DeviceCommand(
    String commandId,
    String deviceId,
    String action
) {}
```

Server lưu kết quả theo `commandId` hoặc bảo đảm handler idempotent. Khi client gửi lại cùng command ID, server trả/truyền trạng thái đã biết thay vì thực hiện side effect lần nữa.

Với Request-Stream, retry có thể tạo subscription mới và phát lại dữ liệu từ đầu. Nếu cần tiếp tục từ vị trí trước đó, payload đăng ký cần có cursor/sequence number hoặc ứng dụng cần dùng cơ chế Resume đã cấu hình. Với Request-Channel, retry có thể gửi lại lệnh đã phát; cần sequence number, event ID và quy tắc khử trùng lặp.

### 9.2. Retry request không phải reconnect policy

Retry một request và tái kết nối RSocket session là hai hành vi khác nhau. `retryWhen` trên một lời gọi không tự định nghĩa cách tạo requester mới, khôi phục Resume, đăng ký lại stream hay khôi phục trạng thái ứng dụng.

Một reconnect policy cần quyết định:

- Kết nối mới hay thử Resume session cũ.
- Backoff, jitter và số lần thử tối đa.
- Cách tạo lại subscription và cursor.
- Cách chống lặp lệnh có side effect.
- Hành vi khi quá thời gian reconnect hoặc session đã hết hạn.

Không đặt retry vô hạn với khoảng cố định; nhiều client cùng retry có thể tạo retry storm khi server vừa phục hồi.

## 10. Phối hợp timeout với KEEPALIVE và timeout hạ tầng

KEEPALIVE được dùng để kiểm tra peer còn phản hồi trên logical connection. `RSocketConnector.keepAlive(interval, maxLifetime)` cấu hình chu kỳ gửi và thời gian client chờ phản hồi KEEPALIVE theo semantics của giao thức. Nó không thay thế timeout của từng request.

Ví dụ:

```java
RSocketRequester.Builder builder = RSocketRequester.builder()
    .rsocketConnector(connector -> connector.keepAlive(
        Duration.ofSeconds(20),
        Duration.ofSeconds(90)
    ));
```

Một request có thể timeout sau 3 giây dù connection vẫn khỏe mạnh. Ngược lại, một stream có thể tồn tại lâu nếu vẫn nhận dữ liệu, trong khi transport có thể bị proxy đóng nếu idle timeout của proxy ngắn hơn khoảng không có frame. Hãy phối hợp:

- Request timeout theo SLA của thao tác.
- Stream idle timeout theo nhịp dữ liệu dự kiến.
- KEEPALIVE interval/Max Lifetime theo mục tiêu phát hiện peer lỗi.
- TCP/NAT/proxy idle timeout theo hạ tầng.
- Database/HTTP timeout theo dịch vụ downstream.

Không nhất thiết đặt mọi giá trị bằng nhau. Cần xác định timeout nào có quyền kết thúc request, timeout nào đánh dấu connection chết và timeout nào chỉ đóng transport nhàn rỗi.

## 11. Một chuỗi gọi hoàn chỉnh có timeout và xử lý lỗi

Ví dụ sau đóng gói chính sách cho một truy vấn trạng thái:

```java
Mono<DeviceStatus> getStatus(String deviceId) {
    return requester
        .route("devices.{deviceId}.status.get", deviceId)
        .data(new StatusQuery())
        .retrieveMono(DeviceStatus.class)
        .timeout(Duration.ofSeconds(3))
        .doOnError(error -> log.warn(
            "Cannot load status for device {}", deviceId, error
        ))
        .onErrorMap(TimeoutException.class,
            error -> new DeviceQueryTimeoutException(deviceId, error));
}
```

Chuỗi này định tuyến request, chuyển DTO thành payload, nhận một response, áp dụng deadline ba giây, ghi nhận lỗi và chuyển timeout thành ngoại lệ miền. Nó không retry tự động; caller quyết định retry dựa trên loại thao tác và chính sách nghiệp vụ.

Đối với một stream theo dõi:

```java
Flux<TelemetryReading> watch(String deviceId) {
    return requester
        .route("devices.{deviceId}.telemetry.watch", deviceId)
        .data(new WatchRequest())
        .retrieveFlux(TelemetryReading.class)
        .timeout(Duration.ofSeconds(30))
        .doOnCancel(() -> log.info("Watcher left: {}", deviceId))
        .doFinally(signal -> metrics.recordWatcherEnd(deviceId, signal));
}
```

Đây là idle timeout 30 giây. Khi caller hủy subscription, `doOnCancel` ghi nhận việc rời stream; `doFinally` ghi nhận mọi loại kết thúc. Việc dừng publisher phía server phụ thuộc vào handler và nguồn dữ liệu có truyền cancellation đúng cách.

## 12. Những lỗi thường gặp

- **Dùng một timeout cho mọi tương tác:** truy vấn ngắn và stream realtime có nhịp dữ liệu khác nhau.
- **Nhầm `Flux.timeout(Duration)` với tổng thời lượng stream:** toán tử này đo thời gian chờ phần tử kế tiếp, không giới hạn toàn bộ tuổi thọ stream.
- **Cho rằng timeout chỉ báo lỗi:** timeout còn hủy subscription upstream và có thể kích hoạt `CANCEL` ở RSocket.
- **Dùng `onErrorResume` để bắt cancellation:** cancellation không phải error signal nên fallback không chạy.
- **Chỉ dùng `doOnComplete` để cleanup:** cancellation không phát `onComplete`; cần `doOnCancel`, `doFinally` hoặc resource operator phù hợp.
- **Retry lệnh không idempotent:** server có thể đã thực hiện lệnh trước khi response bị mất.
- **Coi `send()` là xác nhận nghiệp vụ:** Fire-and-Forget không trả response payload xác nhận server đã xử lý.
- **Nhầm request retry với reconnect:** retry publisher không tự phục hồi session hoặc cursor của stream.
- **Đặt stream idle timeout ngắn hơn khoảng dữ liệu hợp lệ:** stream bị hủy dù hệ thống vẫn hoạt động đúng.

## 13. Kiểm thử timeout, cancellation và lỗi

Các ca kiểm thử nên xác nhận cả kết quả phía client lẫn tác động phía server:

1. Kết nối tới server không hoạt động; xác nhận connection timeout phát sinh đúng thời hạn.
2. Request-Response phản hồi chậm; xác nhận `TimeoutException` và stream phía server nhận cancellation nếu request còn hoạt động.
3. Request-Stream không phát phần tử đầu tiên hoặc ngừng phát giữa chừng; xác nhận idle timeout hoạt động.
4. Request-Stream tiếp tục phát đều; xác nhận `timeout(Duration)` không giới hạn tổng tuổi thọ stream.
5. Dùng `take(Duration)`; xác nhận stream hoàn tất bình thường và upstream bị hủy.
6. Hủy subscriber thủ công; xác nhận `doOnCancel`/`doFinally(CANCEL)` chạy và `onErrorResume` không được gọi.
7. Gây application error và transport error; xác nhận hai loại lỗi được phân loại khác nhau.
8. Retry một request idempotent; xác nhận số lần thử có giới hạn và backoff được áp dụng.
9. Retry command có cùng idempotency key; xác nhận server không thực hiện side effect trùng.
10. Với Fire-and-Forget, xác nhận send completion không bị diễn giải thành server processing acknowledgment.
11. Với Request-Channel, hủy output subscription và xác nhận publisher lệnh đầu vào cùng tài nguyên phía server được dọn.

Nên dùng `StepVerifier` để kiểm tra publisher ở cấp đơn vị và test tích hợp qua RSocket transport để xác nhận frame `CANCEL`, timeout thực tế, lỗi protocol và cleanup của nguồn dữ liệu.

## 14. Kết luận

`timeout(Duration)` giới hạn thời gian chờ kết quả của `Mono` và khoảng im lặng giữa các phần tử của `Flux`; `take(Duration)` giới hạn thời lượng stream nhưng hoàn tất bình thường. Timeout hủy subscription upstream và có thể dẫn tới RSocket `CANCEL`. Cancellation không phải lỗi nên không đi qua `onErrorResume`; dùng `doOnCancel`/`doFinally` để quan sát và gắn cleanup vào publisher. Retry có thể tạo tương tác mới và gửi lại lệnh, vì vậy chỉ retry lỗi tạm thời với thao tác idempotent hoặc có event/command ID. Cuối cùng, giữ riêng timeout kết nối, request, stream, KEEPALIVE và hạ tầng để ứng dụng realtime có hành vi lỗi dễ dự đoán.
