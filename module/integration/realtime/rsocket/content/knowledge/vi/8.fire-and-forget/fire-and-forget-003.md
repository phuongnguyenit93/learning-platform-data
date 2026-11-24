# Các trường hợp phù hợp: tín hiệu đo lường và thông báo không cần phản hồi

Trong module `INTEGRATION_REALTIME_RSOCKET`, RSocket cung cấp giao tiếp bất đồng bộ, hai chiều và reactive qua TCP hoặc WebSocket. Bên cạnh các tương tác cần nhận kết quả, có những tình huống ứng dụng chỉ cần gửi một sự kiện rồi tiếp tục công việc. Ví dụ, thiết bị gửi số đo nhiệt độ định kỳ hoặc một dịch vụ phát thông báo rằng người dùng đang bắt đầu nhập nội dung.

**Fire-and-Forget** phù hợp với những tình huống như vậy: requester gửi một payload và không chờ phản hồi ứng dụng từ responder. Mô hình này giảm phần trao đổi cần thiết, nhưng cũng đặt ra yêu cầu rõ ràng về mức độ mất dữ liệu có thể chấp nhận, quan sát lỗi và điều tiết tốc độ gửi.

## 1. Fire-and-Forget hoạt động như thế nào?

Fire-and-Forget là một trong bốn mô hình tương tác của RSocket. Requester gửi một payload bằng frame `REQUEST_FNF` (Frame Type `0x05`). Responder nhận payload và xử lý nó; tương tác không tạo response payload để trả về requester.

```text
Requester                                  Responder
    |                                          |
    |-------- REQUEST_FNF(payload) ----------->|
    |                                          | xử lý sự kiện
    |                                          |
    |       không có response payload          |
    |                                          |
```

Trong Spring Boot, client thường gọi `RSocketRequester` với `send()`:

```java
Mono<Void> sent = requester
    .route("telemetry.sample")
    .data(sample)
    .send();
```

`Mono<Void>` biểu diễn việc gửi ở phía client hoàn tất theo API. Nó không phải xác nhận nghiệp vụ rằng server đã nhận, xử lý thành công hoặc lưu dữ liệu bền vững. Fire-and-Forget không có response payload để báo kết quả xử lý từ server về requester.

Vì không có phản hồi nghiệp vụ, mô hình này phù hợp khi bên gửi không cần kết quả ngay và có thể chấp nhận việc một số sự kiện bị mất trong những tình huống lỗi. Nếu bên gửi cần biết server đã chấp nhận lệnh, đã ghi dữ liệu hay đã hoàn thành tác vụ, hãy chọn Request-Response hoặc thiết kế một cơ chế xác nhận riêng.

## 2. Gửi tín hiệu đo lường và telemetry

Telemetry là dữ liệu mô tả trạng thái hoặc hoạt động của một hệ thống: nhiệt độ cảm biến, mức pin, tốc độ động cơ, số request, thời gian xử lý, số lỗi hoặc sự kiện quan sát được. Những dữ liệu này thường được gửi định kỳ hoặc phát sinh với tần suất cao.

Fire-and-Forget thích hợp khi telemetry được dùng để quan sát xu hướng và một vài mẫu bị thiếu không làm sai quyết định quan trọng. Ví dụ:

- Thiết bị IoT gửi nhiệt độ, độ ẩm hoặc mức pin theo chu kỳ.
- Ứng dụng gửi số liệu hiệu năng như latency, throughput và số lỗi.
- Dịch vụ phát sự kiện chẩn đoán để hệ thống giám sát tổng hợp.
- Client gửi vị trí hoặc trạng thái gần nhất trong một ứng dụng realtime, nếu nghiệp vụ chấp nhận bỏ lỡ một số cập nhật.

### 2.1. Ví dụ gửi một mẫu đo bằng Spring Boot

Giả sử một thiết bị gửi mẫu nhiệt độ lên dịch vụ giám sát. Client chỉ cần phát mẫu đo, không cần server trả về giá trị tính toán:

```java
public record TelemetrySample(
    String deviceId,
    Instant capturedAt,
    double temperatureC
) {}

Mono<Void> publishSample(TelemetrySample sample) {
    return requester
        .route("telemetry.sample")
        .data(sample)
        .send();
}
```

Phía server ánh xạ route và ghi nhận dữ liệu:

```java
@MessageMapping("telemetry.sample")
public Mono<Void> receiveSample(TelemetrySample sample) {
    return telemetryService.record(sample)
        .doOnError(error -> log.error(
            "Cannot record telemetry for device {}",
            sample.deviceId(),
            error
        ));
}
```

Phương thức server trả `Mono<Void>` vì không có kết quả nghiệp vụ gửi ngược về client. Lỗi ghi dữ liệu cần được quan sát và xử lý ở phía server. `doOnError` ở ví dụ trên giúp ghi log; trong ứng dụng thực tế, có thể bổ sung retry có giới hạn, lưu lỗi vào kho riêng hoặc chuyển sự kiện không xử lý được sang dead-letter queue tùy yêu cầu.

Route `telemetry.sample` là metadata định tuyến. Payload chứa dữ liệu đo. Nếu ứng dụng có nhiều loại telemetry, có thể dùng route riêng hoặc một schema sự kiện có trường `type` và `schemaVersion`; hai phía cần thống nhất hợp đồng dữ liệu.

### 2.2. Gửi theo lô để giảm overhead

Với thiết bị phát dữ liệu liên tục, gửi từng mẫu có thể tạo nhiều frame và tương tác nhỏ. Nếu nghiệp vụ cho phép xử lý theo lô, client có thể gom một số mẫu hoặc gom theo khoảng thời gian rồi gửi một payload:

```java
public record TelemetryBatch(List<TelemetrySample> samples) {}

Flux<TelemetrySample> samples = telemetrySource.samples();

Mono<Void> publishBatches = samples
    .bufferTimeout(100, Duration.ofMillis(500))
    .filter(batch -> !batch.isEmpty())
    .flatMap(batch -> requester
        .route("telemetry.batch")
        .data(new TelemetryBatch(batch))
        .send(), 4)
    .then();
```

Trong ví dụ, mỗi batch chứa tối đa 100 mẫu hoặc được phát khi hết 500 ms. `flatMap(..., 4)` giới hạn số lần gửi đồng thời ở mức 4. Nếu thứ tự batch phải được giữ, dùng `concatMap` để gửi tuần tự. Kích thước batch và mức đồng thời cần được chọn theo giới hạn payload, băng thông và khả năng xử lý của server.

Gom lô làm giảm overhead nhưng tăng độ trễ của mẫu đầu tiên trong batch. Với cảnh báo cần phát ngay, không nên chờ gom đủ batch; có thể dùng route riêng cho cảnh báo hoặc gửi ngay khi phát sinh.

## 3. Phát thông báo không cần phản hồi

Một dịch vụ có thể phát thông báo khi có sự kiện xảy ra mà không cần requester nhận kết quả xử lý ngay. Ví dụ:

- Phát sự kiện người dùng đang nhập (typing indicator) trong phòng chat.
- Thông báo một thiết bị vừa online hoặc offline để các thành phần khác cập nhật trạng thái tạm thời.
- Phát tín hiệu làm mới dữ liệu hoặc cập nhật dashboard.
- Gửi một sự kiện vào pipeline xử lý thông báo, khi bên phát không cần biết trạng thái gửi tới người nhận cuối cùng.

Các sự kiện dạng typing hoặc presence thường có giá trị trong một khoảng thời gian ngắn. Nếu một tín hiệu bị mất, tín hiệu tiếp theo hoặc cơ chế hết hạn trạng thái có thể sửa lại giao diện. Fire-and-Forget phù hợp vì requester không cần chờ server trả một kết quả cho từng tín hiệu.

Ví dụ client phát sự kiện thông báo:

```java
public record NotificationEvent(
    String eventId,
    String recipientId,
    String template,
    Instant occurredAt
) {}

Mono<Void> publishNotification(NotificationEvent event) {
    return requester
        .route("notifications.publish")
        .data(event)
        .send();
}
```

Server nhận sự kiện và chuyển cho dịch vụ thông báo:

```java
@MessageMapping("notifications.publish")
public Mono<Void> publish(NotificationEvent event) {
    return notificationService.accept(event);
}
```

Tên `accept` trong ví dụ chỉ thể hiện việc server nhận trách nhiệm xử lý nội bộ theo hợp đồng của ứng dụng. Fire-and-Forget không đảm bảo `notificationService` đã lưu sự kiện hoặc thông báo đã được gửi tới thiết bị người nhận.

### 3.1. Phân biệt phát sự kiện với xác nhận đã gửi thông báo

Một hệ thống thông báo có nhiều giai đoạn: nhận yêu cầu, tạo thông báo, đưa vào hàng đợi, gửi tới nhà cung cấp push, chuyển tới thiết bị và được người dùng nhìn thấy. Fire-and-Forget chỉ biểu thị rằng requester gửi payload mà không yêu cầu response trong tương tác RSocket đó.

Nếu nghiệp vụ chỉ cần phát tín hiệu để một thành phần khác tự xử lý, Fire-and-Forget có thể đủ. Nếu cần biết thông báo đã được lưu, đã được nhà cung cấp chấp nhận hoặc đã tới thiết bị, cần một trạng thái có thể truy vấn, Request-Response hoặc receipt được gửi qua một tương tác riêng. Không được diễn giải việc `send()` hoàn tất thành xác nhận người nhận đã xem thông báo.

## 4. Khi nào nên dùng và khi nào nên chọn mô hình khác?

Fire-and-Forget nên được chọn dựa trên yêu cầu về phản hồi và độ tin cậy của dữ liệu:

| Nhu cầu | Fire-and-Forget có phù hợp? | Lý do |
|---|---|---|
| Gửi metric hoặc mẫu telemetry định kỳ, có thể mất một vài mẫu | Có | Bên gửi không cần kết quả xử lý cho từng mẫu. |
| Phát typing indicator hoặc trạng thái tạm thời | Có | Sự kiện có thời hạn ngắn và có thể được cập nhật lại. |
| Gửi tín hiệu làm mới dashboard | Có | Client chỉ cần phát tín hiệu; trạng thái mới có thể được tải qua luồng khác. |
| Tạo giao dịch thanh toán và cần biết kết quả | Không | Cần phản hồi nghiệp vụ và xử lý lỗi rõ ràng. |
| Gửi lệnh điều khiển thiết bị quan trọng, cần xác nhận đã thực thi | Không | Cần xác nhận từ thiết bị hoặc truy vấn trạng thái. |
| Gửi thông báo cần chứng minh đã lưu bền vững | Không nên dùng riêng FNF | Cần lưu trữ/queue bền vững và cơ chế truy vấn hoặc receipt. |

Nếu cần một kết quả duy nhất, dùng Request-Response. Nếu cần nhận nhiều cập nhật sau một yêu cầu đăng ký, dùng Request-Stream. Nếu hai phía cùng gửi dữ liệu liên tục, dùng Request-Channel. Fire-and-Forget dành cho một payload một chiều mà requester không cần response payload.

## 5. Độ tin cậy: mất dữ liệu, retry và chống trùng

Fire-and-Forget không cung cấp xác nhận nghiệp vụ. Khi kết nối bị ngắt đúng lúc gửi, client có thể không biết server đã nhận payload hay chưa. Có hai khả năng: payload chưa tới server, hoặc server đã nhận và xử lý nhưng client chưa có cách xác nhận điều đó.

Vì vậy, không nên tự động retry vô hạn một sự kiện có tác động thay đổi trạng thái. Retry có thể làm một sự kiện được xử lý nhiều lần. Nếu cần retry, hãy thiết kế:

- **Event ID:** mỗi sự kiện có định danh duy nhất để server nhận diện lần gửi lặp.
- **Idempotent handler:** xử lý cùng một event ID nhiều lần vẫn tạo ra một kết quả nghiệp vụ tương đương một lần.
- **Retry có giới hạn:** có backoff, giới hạn số lần và chính sách loại bỏ hoặc chuyển lỗi.
- **Durable outbox hoặc message broker:** lưu sự kiện trước khi gửi nếu không được phép mất dữ liệu khi client hoặc mạng gặp sự cố.
- **Trạng thái có thể truy vấn:** nếu người gửi cần biết kết quả cuối cùng, lưu trạng thái theo event ID và cung cấp API hoặc stream riêng.

Đối với telemetry, có thể chấp nhận mất mẫu, lấy mẫu (sampling), gửi batch hoặc giữ bộ đệm ngắn hạn. Với lệnh quan trọng và thông báo bắt buộc phải giao, cần một cơ chế lưu giữ và xác nhận rõ ràng. Không có lựa chọn retry nào tự biến Fire-and-Forget thành bảo đảm exactly-once.

## 6. Điều tiết tải và xử lý lỗi

Fire-and-Forget không có response stream và không có demand theo số response để producer dùng làm tín hiệu điều tiết. Transport vẫn có cơ chế buffer và flow control riêng, nhưng chúng không thay thế chính sách giới hạn tốc độ và hàng đợi ở tầng ứng dụng. Vì vậy, producer phải kiểm soát tốc độ tạo và gửi sự kiện. Nếu thiết bị phát nhanh hơn khả năng tiếp nhận, ứng dụng có thể tích lũy payload trong bộ nhớ, làm tăng độ trễ hoặc gây cạn tài nguyên.

Các biện pháp thường dùng:

- Gom batch theo kích thước hoặc thời gian khi dữ liệu cho phép.
- Giới hạn số lần gửi đồng thời; không gọi `subscribe()` không kiểm soát cho từng sự kiện.
- Dùng hàng đợi có giới hạn và quy định rõ khi đầy: bỏ mẫu cũ, bỏ mẫu mới, giảm tần suất hoặc ghi ra bộ đệm bền vững.
- Áp dụng rate limit, sampling hoặc aggregation cho telemetry có tần suất cao.
- Theo dõi số sự kiện tạo ra, số lần gửi hoàn tất ở client, số sự kiện server xử lý, số lỗi và độ sâu hàng đợi.

`Mono<Void>` từ `send()` vẫn là một publisher reactive ở phía client. Hãy kết hợp nó vào chuỗi reactive để quản lý vòng đời và lỗi gửi; tránh gọi `.subscribe()` thủ công ở sâu trong service vì sẽ tách công việc khỏi luồng điều khiển của caller. Tuy vậy, việc publisher hoàn tất vẫn không xác nhận server đã xử lý payload.

Lỗi phía server cũng cần một đường quan sát riêng vì requester không nhận response lỗi nghiệp vụ từ Fire-and-Forget. Server nên ghi log có correlation/event ID, đếm lỗi, áp dụng retry có giới hạn nếu phù hợp hoặc chuyển sự kiện lỗi sang dead-letter queue. Không nên bỏ qua exception âm thầm.

## 7. Định tuyến, metadata và bảo mật

Trong Spring RSocket, `.route("telemetry.sample")` hoặc `.route("notifications.publish")` tạo metadata định tuyến để server chọn handler tương ứng. Metadata cũng có thể mang thông tin theo hợp đồng ứng dụng, nhưng không nên đưa bí mật hoặc token vào metadata nếu chưa có cơ chế bảo vệ phù hợp.

Một endpoint Fire-and-Forget vẫn cần kiểm soát truy cập:

- Xác thực peer qua cơ chế bảo mật của kết nối hoặc metadata đã được bảo vệ.
- Phân quyền theo route và loại sự kiện; client được gửi telemetry không nhất thiết được phát mọi loại notification.
- Kiểm tra schema, kích thước payload, timestamp và định danh thiết bị trước khi ghi nhận.
- Giới hạn tốc độ theo client/thiết bị để tránh một producer chiếm tài nguyên.
- Không tin `deviceId`, `recipientId` hoặc tenant ID chỉ vì chúng xuất hiện trong payload; đối chiếu với danh tính đã xác thực.

Với thông báo, cần xác thực quyền phát cho recipient. Với telemetry, cần kiểm tra thiết bị có thuộc tenant hoặc nhóm được phép gửi dữ liệu hay không.

## 8. Kiểm thử các tình huống thực tế

Các bài kiểm thử nên bao gồm cả đường gửi bình thường và những tình huống requester không thể quan sát kết quả xử lý:

1. Client gửi một `TelemetrySample`; server nhận đúng route, giải mã payload và gọi service lưu dữ liệu.
2. Client gửi `NotificationEvent`; handler chuyển sự kiện sang dịch vụ thông báo, nhưng không tạo response payload.
3. Server phát sinh lỗi khi xử lý; xác nhận log/metric hoặc dead-letter ghi nhận được lỗi dù client không nhận response nghiệp vụ.
4. Ngắt kết nối trước và trong lúc gửi; xác nhận ứng dụng không giả định rằng `send()` hoàn tất đồng nghĩa dữ liệu đã được lưu.
5. Retry cùng event ID; xác nhận handler idempotent không tạo tác động trùng.
6. Gửi liên tục với tốc độ cao; xác nhận batch size, concurrency, rate limit và hàng đợi đều có giới hạn.
7. Gửi payload sai schema, sai route hoặc vượt kích thước; xác nhận server từ chối và ghi nhận phù hợp.
8. Client không có quyền phát route; xác nhận xác thực/phân quyền ngăn sự kiện đi vào xử lý nghiệp vụ.

Nên kiểm thử qua cả TCP và WebSocket nếu sản phẩm hỗ trợ cả hai transport, vì các lỗi kết nối và đặc điểm mạng trung gian có thể khác nhau. Kiểm thử tích hợp cần xác nhận server đã xử lý sự kiện bằng cách kiểm tra kho dữ liệu hoặc metric phía server, không dựa riêng vào trạng thái `Mono<Void>` của client.

## 9. Kết luận

Fire-and-Forget phù hợp để gửi telemetry, metric và thông báo dạng best-effort khi requester không cần phản hồi nghiệp vụ. Dùng `REQUEST_FNF` để phát một payload, định tuyến bằng metadata và xử lý ở server qua handler tương ứng. Vì không có response payload, ứng dụng phải tự thiết kế quan sát lỗi, giới hạn tải, chống trùng và lưu trữ bền vững nếu nghiệp vụ yêu cầu. Khi cần xác nhận kết quả hoặc bảo đảm giao nhận, hãy chọn mô hình và cơ chế xác nhận phù hợp với mức độ quan trọng của dữ liệu.
