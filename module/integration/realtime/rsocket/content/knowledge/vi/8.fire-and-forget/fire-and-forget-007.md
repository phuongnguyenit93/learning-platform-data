# Thực hành gửi dữ liệu cảm biến và xác minh việc tiếp nhận

Fire-and-Forget (FNF) phù hợp khi một client cần gửi một sự kiện tới RSocket server mà không cần nhận response cho từng lần gửi. Ví dụ, thiết bị IoT gửi nhiệt độ, độ ẩm hoặc trạng thái pin định kỳ. Client gửi payload và tiếp tục công việc; server tiếp nhận sự kiện để ghi log, lưu trữ hoặc chuyển tới pipeline xử lý.

Điểm cần hiểu rõ là FNF không cung cấp biên nhận nghiệp vụ. Việc thao tác gửi ở client hoàn tất không chứng minh server đã lưu dữ liệu hay xử lý xong. Bài thực hành này xây dựng luồng gửi sensor reading, kiểm tra ở phía server và bổ sung cách xác minh riêng khi nghiệp vụ cần biết sự kiện đã được tiếp nhận.

## 1. FNF hoạt động như thế nào?

Trong RSocket, requester gửi frame `REQUEST_FNF` chứa payload và không chờ response payload từ responder. Ở Spring RSocket, client thường gọi `RSocketRequester` với `.send()`, còn server dùng handler trả về `Mono<Void>`.

```text
Sensor device / Client                  RSocket Server
        |                                      |
        |------ REQUEST_FNF (sensor data) ---->|
        |                                      |  nhận payload
        |                                      |  xác thực dữ liệu
        |                                      |  lưu / chuyển tiếp
        |                                      |
        |     không có response nghiệp vụ      |
        |                                      |
        |------ REQUEST_FNF (event tiếp) ----->|
```

FNF có các đặc điểm:

- Một request mang một payload và không tạo response nghiệp vụ tương ứng.
- Client không chờ kết quả xử lý ở server như request-response.
- Server vẫn có thể thực hiện công việc bất đồng bộ sau khi nhận payload.
- Lỗi trong quá trình xử lý ở server không được trả về dưới dạng response nghiệp vụ của FNF. Server cần ghi log, metric hoặc đưa sự kiện lỗi vào cơ chế xử lý nội bộ.
- FNF không tự cung cấp xác nhận lưu bền, bảo đảm xử lý đúng một lần hay khả năng truy vấn trạng thái xử lý.

Trong Spring, `Mono<Void>` từ `.send()` biểu diễn việc gửi hoàn tất hoặc thất bại ở phía client theo API và transport. Nó không phải ACK xác nhận server đã ghi dữ liệu vào cơ sở dữ liệu. Khi kết nối bị ngắt, client có thể không biết server đã nhận payload ngay trước thời điểm ngắt hay chưa.

## 2. Thiết kế payload cho dữ liệu cảm biến

Một sensor reading nên có định danh sự kiện ổn định để có thể đối chiếu log, kiểm tra trạng thái và loại bỏ bản gửi trùng. Ví dụ:

```java
public record SensorReading(
        String eventId,
        String deviceId,
        long sequence,
        long measuredAtEpochMs,
        double temperatureC,
        double humidityPercent
) {}
```

Ý nghĩa các trường:

| Trường | Mục đích |
| --- | --- |
| `eventId` | ID duy nhất của reading, giữ nguyên khi gửi lại cùng một sự kiện |
| `deviceId` | Định danh thiết bị phát dữ liệu |
| `sequence` | Số thứ tự tăng dần theo thiết bị để phát hiện thiếu hoặc đảo thứ tự |
| `measuredAtEpochMs` | Thời điểm thiết bị đo, tính bằng epoch milliseconds |
| `temperatureC` | Nhiệt độ theo độ C |
| `humidityPercent` | Độ ẩm tương đối, từ 0 đến 100 phần trăm |

Ví dụ một payload ở dạng JSON:

```json
{
  "eventId": "7e5b2c4e-1db9-4f5c-9e73-4fbb63d7e5b1",
  "deviceId": "sensor-hcm-014",
  "sequence": 1827,
  "measuredAtEpochMs": 1795348800000,
  "temperatureC": 29.4,
  "humidityPercent": 76.2
}
```

`eventId` nên được tạo một lần tại nguồn và được giữ nguyên khi retry. Nếu mỗi lần retry lại tạo ID mới, server không thể nhận ra hai payload là cùng một sự kiện. `sequence` giúp phát hiện khoảng trống dữ liệu theo thiết bị, nhưng không thay thế event ID vì một sequence có thể được tái sử dụng sau khi thiết bị reset hoặc đổi phiên.

## 3. Xây dựng handler nhận dữ liệu ở server

Tạo một route để nhận sensor reading. Với Spring RSocket, phương thức `@MessageMapping` trả về `Mono<Void>` phù hợp với kiểu tương tác fire-and-forget:

```java
@Controller
public class SensorController {

    private final SensorService sensorService;

    public SensorController(SensorService sensorService) {
        this.sensorService = sensorService;
    }

    @MessageMapping("sensors.reading")
    public Mono<Void> receive(SensorReading reading) {
        return sensorService.storeIfAbsent(reading)
                .doOnSuccess(ignored -> log.info(
                        "Sensor reading stored: eventId={}, deviceId={}, sequence={}",
                        reading.eventId(), reading.deviceId(), reading.sequence()))
                .doOnError(error -> log.error(
                        "Cannot store sensor reading: eventId={}",
                        reading.eventId(), error));
    }
}
```

`storeIfAbsent` là thao tác lưu có tính idempotent: nếu `eventId` đã tồn tại thì không tạo bản ghi thứ hai. Tùy hệ thống, có thể thực hiện bằng unique constraint trên `event_id`, lệnh insert-if-absent hoặc upsert có kiểm soát.

Handler nên hoàn tất `Mono<Void>` sau khi công việc cần thiết ở server kết thúc. Nếu chỉ ghi log rồi đẩy công việc vào một hàng đợi nội bộ, log đó chỉ xác nhận handler đã nhận và chuyển tiếp theo logic hiện tại; nó chưa chứng minh tác vụ cuối cùng đã hoàn tất. Hãy định nghĩa rõ mốc nào được gọi là “đã tiếp nhận”: nhận vào bộ nhớ, ghi vào database, hay ghi vào hàng đợi bền vững.

Server cũng cần kiểm tra dữ liệu đầu vào. Ví dụ, từ chối `eventId` rỗng, `deviceId` không hợp lệ, `humidityPercent` nằm ngoài khoảng 0–100 hoặc giá trị số không hữu hạn. Định danh thiết bị trong payload không tự chứng minh quyền gửi; cần xác thực peer và kiểm tra thiết bị có thuộc tenant hoặc tài khoản đã xác thực hay không.

## 4. Gửi sensor reading từ client

Client dùng route trùng với `@MessageMapping` ở server:

```java
public Mono<Void> sendReading(SensorReading reading) {
    return requester
            .route("sensors.reading")
            .data(reading)
            .send();
}
```

`requester` là một `RSocketRequester` đã được cấu hình với data MIME type và codec tương thích với server. Ví dụ, nếu hai phía dùng JSON, cả hai cần hỗ trợ JSON cho kiểu `SensorReading`.

Không gọi `.block()` trong luồng xử lý reactive của ứng dụng. Hãy trả về `Mono<Void>` để tầng gọi quyết định cách subscribe, kết hợp timeout và xử lý lỗi gửi. Ví dụ một publisher phát nhiều reading có thể gửi tuần tự:

```java
public Mono<Void> sendReadings(Flux<SensorReading> readings) {
    return readings
            .concatMap(this::sendReading)
            .then();
}
```

`concatMap` chờ thao tác gửi cục bộ của reading trước hoàn tất rồi mới gửi reading tiếp theo. Nó không chờ server xác nhận đã lưu reading. Nếu cần tăng throughput, có thể dùng `flatMap(this::sendReading, concurrency)` với giới hạn concurrency phù hợp. Không nên tạo concurrency hoặc hàng đợi không giới hạn khi thiết bị phát dữ liệu nhanh hơn khả năng gửi và xử lý của hệ thống.

Với nguồn dữ liệu realtime, hãy định nghĩa chính sách khi quá tải: giữ hàng đợi có giới hạn, loại bỏ mẫu cũ, chỉ giữ mẫu mới nhất, giảm tần suất lấy mẫu hoặc chuyển sang một kênh có xác nhận. Lựa chọn phụ thuộc vào việc mất một số mẫu có chấp nhận được hay không.

## 5. Xác minh việc tiếp nhận ở phía server

Vì FNF không trả response nghiệp vụ, việc xác minh phải dựa trên dấu hiệu ở phía nhận hoặc một kênh kiểm tra riêng. Có ba mức thường gặp:

| Mức xác minh | Bằng chứng | Có thể kết luận |
| --- | --- | --- |
| Handler được gọi | Log hoặc counter tại handler | Server đã đi vào handler |
| Đã lưu bền | Bản ghi có `eventId` trong database hoặc hàng đợi bền vững | Sự kiện đã được lưu tại mốc được định nghĩa |
| Đã xử lý nghiệp vụ | Trạng thái xử lý hoặc kết quả downstream | Công việc nghiệp vụ đã đạt trạng thái tương ứng |

### 5.1. Ghi log và metric tại server

Ghi `eventId`, `deviceId` và kết quả lưu giúp đối chiếu từng sự kiện. Metric có thể theo dõi số reading nhận được, số reading lưu thành công, số lỗi validation, số bản trùng và độ trễ xử lý.

Không nên chỉ đếm số lần client gọi `.send()` rồi xem đó là số sự kiện server đã nhận. Counter có ý nghĩa xác minh phải được đặt tại handler hoặc sau bước lưu bền tương ứng.

### 5.2. Kiểm tra trạng thái bằng request-response riêng

Nếu client cần biết một event đã được lưu hay chưa, có thể cung cấp route tra cứu bằng `eventId`:

```java
public record SensorReceipt(
        String eventId,
        String status,
        long acceptedAtEpochMs
) {}

@MessageMapping("sensors.reading.status")
public Mono<SensorReceipt> status(String eventId) {
    return sensorService.findReceipt(eventId);
}
```

Client gửi FNF trước, sau đó dùng request-response riêng để hỏi trạng thái:

```java
public Mono<SensorReceipt> sendAndVerify(SensorReading reading) {
    return sendReading(reading)
            .then(Mono.defer(() -> requester
                    .route("sensors.reading.status")
                    .data(reading.eventId())
                    .retrieveMono(SensorReceipt.class)));
}
```

Đoạn mã trên minh họa một lần tra cứu ngay sau thao tác gửi. Trong hệ thống thực tế, việc lưu ở server có thể hoàn tất muộn hơn lần tra cứu đầu tiên. Hãy dùng retry có giới hạn và timeout cho trường hợp chưa tìm thấy receipt, hoặc cung cấp một luồng trạng thái riêng. Route status phải phân biệt rõ “chưa thấy”, “đã nhận”, “đã lưu” và “đã xử lý”; không trả `accepted` trước khi đạt mốc lưu bền mà hệ thống cam kết.

Kênh status là một request-response độc lập, không phải ACK được gửi ngược lại cho FNF. Nếu cần xác nhận ngay và chính xác cho từng lệnh, request-response thường đơn giản hơn.

### 5.3. Xác minh bằng dữ liệu lưu trữ

Trong integration test hoặc vận hành, có thể truy vấn database theo `eventId` sau khi gửi. Đây là cách kiểm chứng trực tiếp mốc lưu bền. Khi dữ liệu được xử lý bất đồng bộ, truy vấn cần chờ trong một deadline hữu hạn thay vì giả định bản ghi xuất hiện ngay khi `.send()` hoàn tất.

## 6. Những điều FNF không xác nhận

Cần tách riêng ba sự kiện:

1. **Client gửi xong:** publisher `.send()` hoàn tất ở phía client.
2. **Server nhận request:** frame tới server và handler được gọi.
3. **Server xử lý xong:** dữ liệu đã được lưu hoặc công việc nghiệp vụ đã hoàn tất.

FNF không gửi response để xác nhận bước 2 hoặc bước 3 cho client. Nếu kết nối mất trong lúc gửi, client có thể không biết server đã nhận payload trước khi kết nối đứt hay chưa. Nếu client retry, server có thể nhìn thấy cùng một reading nhiều lần.

Vì vậy:

- Không diễn giải `Mono<Void>` hoàn tất là server đã ghi database.
- Không giả định FNF có exactly-once delivery.
- Không retry một sự kiện bằng ID mới; giữ nguyên `eventId` để server deduplicate.
- Không bỏ qua lỗi ở handler server; ghi log, metric và đưa lỗi vào cơ chế retry hoặc dead-letter phù hợp.
- Không dùng FNF cho thao tác cần kết quả quyết định ngay như thanh toán, cập nhật trạng thái quan trọng hoặc lệnh điều khiển cần xác nhận.

Nếu mất dữ liệu là không thể chấp nhận, hãy cân nhắc request-response với ACK sau khi lưu bền, request-channel có giao thức xác nhận riêng, hoặc một message broker có lưu trữ và cơ chế consumer acknowledgment. Lựa chọn phải phản ánh yêu cầu độ bền và khả năng phục hồi của nghiệp vụ.

## 7. Retry, chống trùng và thứ tự dữ liệu

Một client có thể gặp lỗi gửi do kết nối đóng, timeout hoặc lỗi transport. Khi retry, không thể luôn biết lần gửi trước đã tới server hay chưa. Cách xử lý an toàn là thiết kế thao tác lưu idempotent.

Ví dụ:

- `eventId` là khóa duy nhất của một reading và được giữ nguyên qua mọi lần gửi lại.
- Database đặt unique constraint trên `event_id`.
- Nếu nhận event đã tồn tại, server không tạo bản ghi mới và có thể cập nhật metric `duplicate_event`.
- `sequence` tăng theo từng thiết bị để phát hiện mất mẫu hoặc dữ liệu tới sai thứ tự.
- Nếu cần xử lý đúng thứ tự, server phải có chính sách buffer/reorder hoặc từ chối sequence cũ; không dựa vào thứ tự hoàn tất của nhiều request FNF song song.

Retry nên có giới hạn, backoff và jitter. Không retry vô hạn với payload không hợp lệ hoặc lỗi xác thực. Với sự kiện quan trọng, lưu reading vào outbox hoặc local durable queue trước khi gửi để tiến trình có thể tiếp tục sau khi thiết bị khởi động lại.

## 8. Điều tiết tốc độ và xử lý quá tải

FNF không cung cấp demand từ server cho từng reading. Vì vậy client phải chủ động kiểm soát tốc độ gửi và server phải có giới hạn tài nguyên rõ ràng.

Một số biện pháp:

- Dùng `concatMap` hoặc `flatMap` với concurrency hữu hạn để giới hạn số thao tác gửi đang chạy ở client.
- Giới hạn kích thước queue và chọn chính sách overflow phù hợp với loại telemetry.
- Đặt giới hạn payload và kiểm tra kích thước trước khi encode.
- Dùng rate limit theo thiết bị hoặc tenant ở server.
- Theo dõi latency lưu dữ liệu, queue depth, số lỗi và số sự kiện trùng.
- Nếu kết nối bật RSocket leasing, requester phải tuân thủ TTL và request count được peer cấp; lease giới hạn số request được khởi tạo, không xác nhận việc xử lý payload.

Nếu server cần điều tiết tốc độ dựa trên tải hiện tại và client phải biết chính xác khi nào được tiếp tục, hãy thiết kế cơ chế phản hồi hoặc chuyển sang interaction model phù hợp. Đừng coi FNF là một stream có backpressure ở cấp ứng dụng.

## 9. Kiểm thử luồng gửi dữ liệu cảm biến

Kiểm thử cần phân biệt thao tác gửi của client với hành vi nhận và lưu của server.

### 9.1. Kiểm tra thao tác gửi ở client

```java
StepVerifier.create(
        requester.route("sensors.reading")
                .data(reading)
                .send())
        .verifyComplete();
```

Bài kiểm thử này chỉ xác nhận publisher gửi hoàn tất theo API. Nó không chứng minh handler đã chạy hoặc database đã có bản ghi.

### 9.2. Kiểm tra service lưu dữ liệu

Kiểm thử `SensorService` riêng để xác nhận reading hợp lệ được lưu, event trùng không tạo bản ghi thứ hai, dữ liệu sai bị từ chối và lỗi repository được ghi nhận đúng cách.

### 9.3. Kiểm tra tích hợp end-to-end

1. Khởi động RSocket server và kết nối client bằng transport thực tế.
2. Tạo reading với `eventId` cố định.
3. Gửi qua route `sensors.reading` bằng FNF.
4. Chờ trong một deadline hữu hạn và truy vấn receipt hoặc database theo `eventId`.
5. Xác nhận dữ liệu đã lưu có đúng `deviceId`, `sequence`, timestamp và giá trị đo.
6. Gửi lại cùng `eventId` để xác nhận server không tạo bản ghi trùng.
7. Gửi payload sai hoặc mô phỏng lỗi lưu để kiểm tra log, metric và cơ chế xử lý lỗi phía server.

Một test end-to-end có thể chờ trạng thái bằng Awaitility hoặc cơ chế polling tương đương. Không dùng `Thread.sleep` cố định làm bằng chứng rằng server đã xử lý xong; điều đó khiến test chậm và dễ flaky.

## 10. Khi nào nên dùng Fire-and-Forget?

FNF phù hợp với dữ liệu telemetry, metric, sự kiện quan sát hoặc thông báo mà client không cần kết quả cho từng lần gửi và hệ thống có chính sách chấp nhận mất dữ liệu hoặc xác minh riêng.

Nên cân nhắc interaction model khác nếu:

- Client phải biết server đã lưu thành công trước khi tiếp tục: dùng request-response với ACK sau lưu bền.
- Client gửi một luồng dữ liệu liên tục và cần điều tiết theo nhu cầu: xem xét request-stream hoặc request-channel cùng giao thức flow control phù hợp.
- Dữ liệu phải tồn tại qua mất kết nối và tiến trình khởi động lại: dùng durable queue/outbox hoặc broker có lưu trữ.
- Mỗi lệnh cần kết quả nghiệp vụ hoặc lỗi cụ thể: dùng request-response.

## 11. Checklist thực hành

- [ ] Mỗi sensor reading có `eventId` ổn định và `sequence` theo thiết bị.
- [ ] Client và server thống nhất route, data MIME type và codec.
- [ ] Server validate payload và xác thực quyền gửi của thiết bị.
- [ ] Handler FNF trả về `Mono<Void>` và hoàn tất sau mốc xử lý đã định nghĩa.
- [ ] Server ghi log/metric tại nơi nhận và nơi lưu bền.
- [ ] Client hiểu `.send()` chỉ xác nhận thao tác gửi phía client, không phải ACK nghiệp vụ.
- [ ] Retry giữ nguyên `eventId`; server deduplicate bằng khóa duy nhất.
- [ ] Queue, concurrency, payload size và rate limit có giới hạn.
- [ ] Integration test xác minh dữ liệu ở phía server bằng receipt hoặc database.
- [ ] Nếu cần bảo đảm tiếp nhận, đã chọn cơ chế ACK hoặc lưu trữ bền phù hợp.

Khi thực hành gửi sensor reading, hãy xác định trước mốc nào được gọi là “đã tiếp nhận” và đặt bằng chứng xác minh tại đúng mốc đó. FNF giúp gửi sự kiện nhẹ và không phải chờ response cho từng payload; độ tin cậy của toàn bộ quy trình vẫn phụ thuộc vào cách server lưu dữ liệu, cách client retry và cách hệ thống phát hiện sự kiện bị thiếu hoặc gửi trùng.
