# Hủy đăng ký từ phía nhận và dừng nguồn phát ở phía gửi

RSocket request-stream cho phép một requester mở stream và nhận nhiều payload từ responder theo thời gian. Stream có thể kéo dài trong vài giây, vài phút hoặc suốt vòng đời của một phiên realtime. Khi người dùng rời màn hình, thiết bị không còn được theo dõi hoặc client đã có đủ dữ liệu, requester cần hủy đăng ký. Việc hủy phải được truyền đến responder để nguồn phát dừng công việc dành riêng cho stream đó và giải phóng tài nguyên.

Trong RSocket, frame `CANCEL` biểu diễn việc hủy một stream đang hoạt động. Ở tầng ứng dụng, Reactive Streams biểu diễn thao tác này bằng `Subscription.cancel()`. Adapter RSocket nối hai cơ chế: subscriber hủy subscription, RSocket gửi `CANCEL` trên stream tương ứng, responder nhận frame và hủy subscription của Publisher nguồn. Khi thiết kế đúng, việc hủy đi xuyên suốt từ client đến nguồn dữ liệu, thay vì chỉ ngừng hiển thị dữ liệu ở giao diện.

## 1. Vì sao cần hủy request-stream?

Một stream không tự kết thúc chỉ vì client không còn quan tâm đến dữ liệu. Nếu subscriber vẫn tồn tại, nguồn phát có thể tiếp tục truy vấn database, giữ subscription đến message broker, đọc cảm biến hoặc tạo dữ liệu định kỳ. Điều này làm tăng số stream hoạt động, buffer, kết nối downstream và tài nguyên CPU/bộ nhớ.

Các tình huống thường cần cancellation:

- Người dùng rời màn hình dashboard hoặc đóng trang theo dõi realtime.
- Client chỉ cần một số lượng phần tử nhất định, chẳng hạn 20 sự kiện mới nhất.
- Điều kiện nghiệp vụ đã thỏa mãn và không cần nhận thêm dữ liệu.
- Request vượt quá deadline hoặc timeout của ứng dụng.
- Client mất kết nối hoặc tiến trình bị dừng.
- Một tác vụ khác thay thế stream hiện tại, ví dụ người dùng chọn thiết bị khác.

Cancellation giúp tiết kiệm tài nguyên và giảm tải cho hệ thống. Nó cũng là một phần của contract vận hành stream: bên nhận có thể kết thúc nhu cầu bất kỳ lúc nào, vì vậy bên gửi phải thiết kế nguồn phát có khả năng phản ứng với việc hủy.

## 2. Vòng đời cancellation trong RSocket

Khi requester mở request-stream, frame `REQUEST_STREAM` tạo một stream mới và mang payload đầu vào cùng initial request-N. Responder trả các frame `PAYLOAD` theo demand. Nếu requester hủy, nó gửi frame `CANCEL` có cùng stream ID. Frame này chỉ tác động đến stream đó, không đóng toàn bộ kết nối RSocket và không hủy các stream khác đang chạy trên kết nối.

```mermaid
sequenceDiagram
    participant C as Requester / Client
    participant R as RSocket transport
    participant S as Responder / Server
    participant P as Publisher nguồn
    C->>R: REQUEST_STREAM (stream 5, initial N)
    R->>S: REQUEST_STREAM (stream 5)
    S->>P: subscribe()
    P-->>S: PAYLOAD 1, 2, 3...
    S-->>R: PAYLOAD (stream 5)
    R-->>C: Phát dữ liệu cho subscriber
    C->>R: Subscription.cancel()
    R->>S: CANCEL (stream 5)
    S->>P: cancel()
    Note over P: Dừng nguồn riêng của stream và cleanup
    Note over C,S: Stream 5 kết thúc; các stream khác vẫn hoạt động
```

Trình tự có thể tóm tắt như sau:

1. Client subscribe vào `Flux` nhận từ request-stream.
2. RSocket tạo stream và gửi `REQUEST_STREAM`.
3. Server xử lý request và subscribe vào Publisher nguồn.
4. Server phát `PAYLOAD` theo demand được cấp.
5. Client không còn cần dữ liệu và gọi `cancel()` hoặc một operator kết thúc upstream.
6. RSocket gửi `CANCEL` với stream ID tương ứng.
7. Server hủy subscription nguồn, dừng tác vụ có thể dừng và giải phóng tài nguyên.

`CANCEL` là frame cấp stream, có stream ID dương. Nó không phải `KEEPALIVE`, không phải đóng transport và cũng không phải tín hiệu `onComplete`. Khi stream bị hủy, bên nhận không cần gửi một payload hoàn tất để xác nhận cancellation.

## 3. Phân biệt demand và cancellation

`REQUEST_N` và `CANCEL` đều là frame điều khiển stream nhưng có mục đích khác nhau:

| Cơ chế | Ý nghĩa | Stream tiếp tục hoạt động? |
|---|---|---|
| `REQUEST_N(N)` | Cấp thêm demand để nhận tối đa N payload | Có; stream tiếp tục nếu còn dữ liệu |
| Không cấp thêm demand | Tạm thời chưa yêu cầu thêm payload | Có; stream có thể chờ demand mới |
| `CANCEL` | Kết thúc nhu cầu nhận dữ liệu của stream | Không; stream bị hủy |

Không có demand không đồng nghĩa với cancellation. Một subscriber có thể tạm thời chưa yêu cầu thêm phần tử vì downstream đang bận; Publisher phải tuân thủ backpressure và chờ demand. Khi subscriber gọi `cancel()`, nó tuyên bố không cần bất kỳ phần tử nào tiếp theo trên subscription đó. Không thể dùng một `REQUEST_N(0)` để thay thế cancellation; request-N phải là số dương.

Ví dụ, client mở stream với initial demand bằng 10. Sau khi nhận 10 payload, client chưa gửi `REQUEST_N` mới. Server không được tự phát thêm payload vượt demand, nhưng stream vẫn tồn tại. Nếu client gọi `cancel()`, RSocket gửi `CANCEL`; stream kết thúc và không còn demand nào được cấp thêm.

## 4. Hủy từ phía client bằng Reactor và Spring RSocket

Spring `RSocketRequester` trả về `Flux<T>` khi gọi `retrieveFlux`. Việc subscribe tạo nhu cầu nhận dữ liệu; hủy subscription của Flux sẽ được Reactor RSocket truyền thành cancellation của stream.

### Hủy thủ công bằng Disposable

Khi gọi `subscribe(...)`, Reactor trả về một `Disposable`. Gọi `dispose()` khi không còn cần stream:

```java
import reactor.core.Disposable;
import reactor.core.publisher.Flux;

Flux<Telemetry> telemetry = requester
    .route("device.telemetry")
    .data(new DeviceQuery("device-42"))
    .retrieveFlux(Telemetry.class);

Disposable subscription = telemetry.subscribe(
    item -> display(item),
    error -> showError(error),
    () -> showCompleted()
);

// Khi người dùng rời màn hình hoặc đổi thiết bị:
subscription.dispose();
```

`dispose()` hủy subscription hiện tại. Trong ứng dụng UI, cần gắn việc dispose với lifecycle của màn hình hoặc component. Nếu bỏ quên subscription, stream có thể tiếp tục chạy sau khi người dùng đã rời màn hình.

### Hủy tự động bằng operator

Nhiều operator Reactor tự hủy upstream khi điều kiện đã đạt:

```java
Flux<Telemetry> firstHundred = requester
    .route("device.telemetry")
    .data(new DeviceQuery("device-42"))
    .retrieveFlux(Telemetry.class)
    .take(100);
```

`take(100)` hoàn tất downstream sau khi nhận đủ 100 phần tử và hủy upstream để không nhận thêm dữ liệu. Tương tự, `timeout(...)` hủy upstream khi hết thời gian chờ; các operator như `takeUntil(...)` cũng có thể kết thúc luồng khi điều kiện dừng được thỏa mãn.

Ví dụ dùng timeout:

```java
Flux<Telemetry> idleTimeoutStream = requester
    .route("device.telemetry")
    .data(new DeviceQuery("device-42"))
    .retrieveFlux(Telemetry.class)
    .timeout(Duration.ofSeconds(30));
```

Với `Flux.timeout(Duration)`, thời hạn được áp dụng cho tín hiệu đầu tiên và khoảng chờ giữa các tín hiệu tiếp theo. Nếu stream không phát phần tử trong 30 giây, downstream nhận timeout error và upstream bị hủy. Nếu yêu cầu là giới hạn tổng thời gian sống của stream, dùng `take(Duration)`:

```java
Flux<Telemetry> maxFiveMinutes = requester
    .route("device.telemetry")
    .data(new DeviceQuery("device-42"))
    .retrieveFlux(Telemetry.class)
    .take(Duration.ofMinutes(5));
```

Một stream telemetry có thể sống lâu nhưng phát dữ liệu không đều, vì vậy cần chọn giữa timeout theo khoảng im lặng và giới hạn tổng thời gian. Chọn operator theo đúng ý định nghiệp vụ.

## 5. Dừng nguồn phát ở responder

Phía server thường trả về `Flux<T>` từ phương thức `@MessageMapping`. Khi RSocket nhận `CANCEL`, adapter hủy subscription của Publisher mà handler trả về. Publisher và các API nguồn bên dưới cần phản ứng đúng với `cancel()`.

```java
@Controller
public class TelemetryController {
    private final TelemetryService telemetryService;

    public TelemetryController(TelemetryService telemetryService) {
        this.telemetryService = telemetryService;
    }

    @MessageMapping("device.telemetry")
    public Flux<Telemetry> telemetry(@Payload DeviceQuery query) {
        return telemetryService.stream(query.deviceId())
            .doOnCancel(() -> log.info(
                "Telemetry stream cancelled for device {}", query.deviceId()))
            .doFinally(signal -> metrics.recordStreamTermination(signal));
    }
}
```

`doOnCancel` phù hợp để ghi nhận sự kiện hủy. `doFinally` chạy khi luồng kết thúc bằng complete, error hoặc cancel, nên phù hợp cho metric vòng đời tổng quát. Các hook quan sát không thay thế việc đóng resource; việc cleanup phải được gắn trực tiếp với vòng đời của resource.

Nếu nguồn là Publisher reactive có khả năng cancellation, như `Flux.interval`, driver database reactive hoặc client message broker reactive, subscription cancellation thường được truyền về nguồn để dừng lịch phát hoặc hủy thao tác đang chờ. Tuy nhiên, không phải API nào cũng hỗ trợ hủy ngay lập tức. Cần kiểm tra contract của thư viện nguồn và tránh bọc một API blocking trong Publisher rồi giả định `cancel()` sẽ ngắt được lời gọi blocking đó.

## 6. Giải phóng tài nguyên khi stream bị hủy

Một stream có thể giữ subscription đến broker, cursor database, listener thiết bị, file handle hoặc một tác vụ nền. Chỉ dừng phát payload mà không đóng resource vẫn gây rò rỉ tài nguyên.

Với resource cần đóng đồng bộ, `Flux.using` gắn disposer vào vòng đời Publisher:

```java
Flux<Telemetry> stream(String deviceId) {
    return Flux.using(
        () -> telemetrySource.openSubscription(deviceId),
        subscription -> subscription.events(),
        TelemetrySubscription::close
    );
}
```

Resource được tạo khi có subscription. Khi stream hoàn tất, phát lỗi hoặc bị hủy, disposer được gọi để đóng subscription nguồn.

Nếu thao tác cleanup bất đồng bộ, dùng `usingWhen` để mô tả riêng đường hoàn tất, lỗi và cancellation:

```java
Flux<Telemetry> stream(String deviceId) {
    return Flux.usingWhen(
        telemetrySource.openSubscription(deviceId),
        subscription -> subscription.events(),
        TelemetrySubscription::closeAsync,
        (subscription, error) -> subscription.closeAsync(),
        TelemetrySubscription::closeAsync
    );
}
```

Trong ví dụ, `openSubscription` trả về một Publisher chứa resource; `closeAsync()` trả về Publisher hoàn tất khi cleanup xong. Cần bảo đảm thao tác đóng có tính idempotent hoặc an toàn khi được gọi trong nhiều đường kết thúc. Nếu cleanup thất bại, hãy ghi nhận và áp dụng chính sách retry/timeout phù hợp để không giữ resource vô thời hạn.

Với nguồn tự tạo bằng `Flux.create`, có thể đăng ký callback dọn dẹp khi sink bị dispose:

```java
Flux<Telemetry> streamFromListener(String deviceId) {
    return Flux.create(sink -> {
        DeviceListener listener = deviceBus.listen(deviceId, sink::next);
        sink.onDispose(listener::close);
    });
}
```

`onDispose` được gọi khi sink kết thúc, bao gồm complete, error hoặc cancel. Vì vậy callback đóng listener cần an toàn nếu quá trình kết thúc đến từ nhiều nhánh. Với nguồn dùng chung cho nhiều client, phải chỉ đóng listener riêng của subscriber hiện tại; không được dừng nguồn toàn cục khi một client hủy stream của mình.

## 7. Nguồn riêng và nguồn chia sẻ cho nhiều subscriber

Cancellation luôn tác động đến subscription cụ thể. Điều đó có hệ quả khác nhau tùy nguồn dữ liệu:

- **Nguồn riêng cho mỗi request:** hủy subscription có thể dừng truy vấn, timer, listener hoặc tác vụ được tạo riêng cho request đó.
- **Nguồn chia sẻ:** hủy một subscriber chỉ nên loại subscriber đó khỏi nguồn multicast. Nguồn dùng chung tiếp tục hoạt động cho các subscriber còn lại.
- **Nguồn nóng (hot publisher):** dữ liệu có thể được phát độc lập với subscriber. Hủy một subscription dừng việc chuyển dữ liệu đến subscriber đó, nhưng không nhất thiết dừng thiết bị, broker hoặc publisher toàn cục.

Ví dụ, một `Sinks.Many<Telemetry>` được dùng chung cho 100 client. Khi một client gửi `CANCEL`, server chỉ cần loại bỏ subscriber của stream đó. Nếu callback cleanup đóng luôn sink dùng chung hoặc tắt thiết bị, 99 client còn lại cũng mất dữ liệu. Vì vậy, hãy phân định quyền sở hữu resource: ai tạo, ai dùng chung và ai được phép đóng.

Với nguồn dùng chung, có thể quản lý vòng đời bằng ref-count hoặc một service quản lý subscription tập trung. Chỉ dừng nguồn toàn cục khi chính sách chia sẻ xác định rằng không còn subscriber nào cần nó hoặc khi service chủ động shutdown.

## 8. Cancellation không phải complete, error hay rollback

Các tín hiệu kết thúc của Reactive Streams có ý nghĩa khác nhau:

| Tín hiệu | Ý nghĩa | Phía nhận có nhận tín hiệu không? |
|---|---|---|
| `onComplete` | Publisher kết thúc bình thường | Có; subscriber nhận complete |
| `onError` | Publisher kết thúc do lỗi | Có; subscriber nhận lỗi |
| `cancel()` | Subscriber không còn yêu cầu dữ liệu | Không có `onComplete` hoặc `onError` được gửi ngược lại cho subscriber đã hủy |

Cancellation là hành động từ phía subscriber, không phải một tín hiệu terminal mà Publisher gửi đến subscriber. Vì vậy, không nên đợi callback `onComplete` để cleanup sau khi người dùng hủy. Dùng `doOnCancel`, `doFinally` hoặc resource operator phù hợp.

Cancellation cũng không đảm bảo hoàn tác tác động phụ đã xảy ra. Ví dụ server đã ghi một bản ghi database trước khi nhận frame `CANCEL`; hủy subscription không tự rollback transaction đã commit. Với thao tác ghi, cần xác định ranh giới commit, idempotency và cách client tra cứu kết quả nếu response không đến.

## 9. Race condition và dữ liệu đang trên đường truyền

Trong hệ thống phân tán, cancellation không xảy ra đồng thời tuyệt đối ở hai phía. Client có thể gọi `cancel()` tại thời điểm server vừa phát một payload. Frame `PAYLOAD` đã được gửi hoặc đang trên đường truyền có thể đến gần thời điểm frame `CANCEL` được xử lý. Khi server nhận cancellation, nó dừng việc phát tiếp theo khả năng của nguồn và transport; client không nên giả định rằng không còn byte nào đã rời server trước thời điểm đó.

Một số tình huống cần tính đến:

- **Payload đang bay:** một payload đã gửi trước khi server nhận `CANCEL` có thể đã nằm trong buffer hoặc mạng.
- **Complete và cancel cùng lúc:** stream có thể hoàn tất tự nhiên trước khi cancellation được xử lý; chỉ một trạng thái kết thúc có hiệu lực đối với subscriber.
- **Nguồn không hủy tức thời:** một truy vấn hoặc API blocking có thể tiếp tục chạy dù subscription đã bị hủy.
- **Cleanup chậm:** callback đóng resource có thể cần thời gian hoặc có thể thất bại; cần quan sát và giới hạn thời gian cleanup.
- **Hủy một stream trong connection nhiều stream:** không được đóng toàn bộ connection hoặc hủy các stream không liên quan.

Với dữ liệu telemetry hoặc trạng thái mới nhất, client có thể bỏ qua payload đến sau khi UI đã kết thúc. Với lệnh ghi hoặc sự kiện có tác động phụ, cần idempotency và mã tham chiếu để tránh diễn giải cancellation thành thất bại chắc chắn.

## 10. Cancellation và lỗi trong request-stream

Cancellation là kết thúc có chủ đích do subscriber yêu cầu. Error là kết thúc vì Publisher không thể tiếp tục. Server nên phân biệt hai trường hợp trong log và metric:

- `CANCEL`: client không còn cần dữ liệu; thường không phải lỗi hệ thống.
- `onError`: nguồn hoặc logic xử lý thất bại; cần phân loại và theo dõi nguyên nhân.
- `onComplete`: nguồn kết thúc bình thường; đây có thể là kết thúc mong đợi của một stream hữu hạn.

Không nên ghi mọi cancellation ở mức ERROR. Tỷ lệ cancel cao có thể bình thường nếu UI thường xuyên đổi bộ lọc hoặc người dùng rời màn hình. Cần so sánh cancellation với thời lượng stream, số phần tử đã phát và nguồn tài nguyên được giải phóng để phát hiện vấn đề thực sự.

Nếu server phát lỗi sau khi stream đã bị hủy, lỗi đó không thể được dùng để gửi một tín hiệu lỗi mới trên stream đã kết thúc. Hãy log lỗi cleanup hoặc lỗi tác vụ nền theo cơ chế giám sát nội bộ.

## 11. Kiểm thử cancellation

Kiểm thử cần xác minh cả hai điều: subscriber dừng nhận dữ liệu và nguồn upstream thực sự nhận cancellation.

### Unit test với StepVerifier

```java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> source = Flux.interval(Duration.ofMillis(20))
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source)
    .expectNext(0L)
    .thenCancel()
    .verify();

assertTrue(cancelled.get());
```

Test này xác minh Reactor gọi cancellation trên nguồn khi StepVerifier hủy subscription. Cần thêm kiểm thử cho disposer/resource để bảo đảm listener, cursor hoặc subscription ngoài được đóng.

### Kiểm thử tích hợp RSocket

Với requester và responder chạy thật, có thể mở stream rồi chỉ lấy một số phần tử:

```java
Flux<Telemetry> firstItems = requester
    .route("device.telemetry")
    .data(new DeviceQuery("device-42"))
    .retrieveFlux(Telemetry.class)
    .take(3);
```

Sau khi `take(3)` hoàn tất, adapter phải hủy stream upstream. Phía server nên có một tín hiệu kiểm thử riêng để xác minh callback cancellation đã chạy và resource được đóng. Không nên chỉ kiểm tra rằng client nhận đúng ba phần tử; test đó chưa chứng minh nguồn server đã dừng.

Các trường hợp kiểm thử nên bao gồm:

1. Client hủy thủ công bằng `Disposable.dispose()`.
2. Client dùng `take(n)` và upstream nhận cancellation sau phần tử thứ n.
3. Client timeout và server cleanup resource.
4. Client ngắt kết nối khi stream đang phát.
5. Nguồn server hoàn tất hoặc lỗi trước khi client hủy.
6. Hai client subscribe cùng nguồn chia sẻ; một client hủy nhưng client còn lại tiếp tục nhận dữ liệu.
7. Nguồn blocking hoặc không hỗ trợ cancellation; xác minh cách cô lập và giới hạn tài nguyên.
8. Một connection có nhiều stream; hủy một stream không ảnh hưởng stream khác.

## 12. Quan sát trong môi trường vận hành

Nên theo dõi vòng đời stream ở cả client, RSocket transport và nguồn dữ liệu:

- Số stream đang hoạt động theo route và theo client/session.
- Số cancellation, complete và error riêng biệt.
- Thời gian từ lúc client hủy đến lúc server nhận `CANCEL` và cleanup hoàn tất, nếu có thể đo.
- Số listener, cursor, broker subscription và tác vụ nền đang mở.
- Số payload đã phát trước khi hủy và số payload đang chờ trong buffer.
- Lỗi cleanup, timeout cleanup và nguồn không phản ứng với cancellation.
- Tỷ lệ client disconnect và thời gian sống trung bình của stream.

Log nên có correlation ID hoặc stream ID phù hợp để nối sự kiện mở stream, phát dữ liệu, cancel và cleanup. Không ghi payload nhạy cảm. Cancellation thường là một sự kiện vòng đời bình thường; chỉ cảnh báo khi cleanup thất bại, số stream bị bỏ lại tăng hoặc nguồn phát tiếp tục chạy sau khi stream đã kết thúc.

## 13. Quy tắc thiết kế

1. Luôn xem cancellation là một phần của contract request-stream.
2. Khi subscriber hủy, để RSocket gửi `CANCEL` cho đúng stream ID.
3. Trên server, trả Publisher có khả năng truyền cancellation đến nguồn thật.
4. Gắn cleanup resource với complete, error và cancel; không chỉ cleanup khi complete.
5. Phân biệt nguồn riêng với nguồn chia sẻ để hủy một subscriber không dừng các subscriber khác.
6. Không dùng cancellation như rollback cho thao tác đã commit.
7. Tính đến payload đang bay và race giữa cancel với complete/error.
8. Tránh API blocking hoặc không thể hủy trong nguồn phát; nếu bắt buộc, giới hạn concurrency và thời gian chờ.
9. Kiểm thử cả frame/adapter lẫn cleanup ở nguồn; chỉ kiểm tra số payload client nhận là chưa đủ.
10. Theo dõi số stream đang mở và thời gian giải phóng resource để phát hiện leak.

Khi requester hủy một request-stream, frame `CANCEL` kết thúc stream ở tầng giao thức và `Subscription.cancel()` truyền ý định đó đến Publisher ở tầng ứng dụng. Responder cần dừng nguồn phát dành riêng cho stream, giải phóng resource và xử lý an toàn các race có thể xảy ra. Nếu nguồn dùng chung, chỉ hủy subscriber tương ứng. Thiết kế cancellation xuyên suốt giúp dịch vụ RSocket duy trì stream realtime lâu dài mà không để công việc và tài nguyên tiếp tục tồn tại sau khi người nhận đã rời đi.
