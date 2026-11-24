# Gửi fire-and-forget bằng `send` và hiểu tín hiệu hoàn tất

Trong Spring RSocket, `RSocketRequester` cung cấp phương thức `send()` để thực hiện tương tác **fire-and-forget**. Caller gửi một request đến responder nhưng không yêu cầu response payload. API trả về `Mono<Void>` để theo dõi việc gửi ở phía requester: publisher hoàn tất khi thao tác gửi hoàn tất theo runtime, hoặc phát lỗi nếu không thể thực hiện thao tác gửi.

Điểm cần hiểu rõ là tín hiệu hoàn tất của `send()` không phải acknowledgement nghiệp vụ từ server. Fire-and-forget không có response trên giao thức RSocket, nên client không thể dựa vào `Mono<Void>` để kết luận server đã ghi dữ liệu, xử lý xong sự kiện hoặc commit transaction. Nếu cần xác nhận xử lý, hãy chọn request-response hoặc xây dựng một cơ chế acknowledgement riêng.

## 1. Fire-and-forget là gì?

Fire-and-forget là tương tác một chiều: requester gửi một payload, responder nhận và xử lý nhưng không trả response payload. Trong RSocket protocol, requester mở tương tác bằng frame `REQUEST_FNF`.

```text
Requester (Client)                    Responder (Server)
       |                                      |
       | REQUEST_FNF                         |
       | data + metadata                     |
       |------------------------------------->|
       |                                      | xử lý nghiệp vụ
       |                                      |
       |          không có response payload  |
       |                                      |
```

Không có frame `PAYLOAD` response để xác nhận rằng handler đã hoàn tất. Khi server xử lý xong, giao thức không gửi một kết quả thành công về client trong tương tác này.

Fire-and-forget phù hợp với các thông báo mà caller không cần kết quả ngay, ví dụ gửi telemetry, ghi nhận một sự kiện audit không yêu cầu xác nhận đồng bộ, phát tín hiệu refresh cache hoặc gửi một lệnh best-effort. Với thao tác có yêu cầu xác nhận, tính toàn vẹn giao dịch hoặc kết quả cần hiển thị cho người dùng, request-response thường phù hợp hơn.

## 2. Gửi fire-and-forget bằng `RSocketRequester.send()`

Một request của `RSocketRequester` thường được xây dựng qua các bước `route(...)`, `data(...)` và một terminal operation. Với fire-and-forget, terminal operation là `send()`:

```java
Mono<Void> sendAuditEvent(AuditEvent event) {
    return requester
        .route("audit.record")
        .data(event)
        .send();
}
```

Ý nghĩa từng bước:

1. `route("audit.record")` chọn route mà responder dùng để tìm handler.
2. `data(event)` cung cấp object nghiệp vụ để Spring serialize thành data payload.
3. `send()` chọn interaction model fire-and-forget và trả `Mono<Void>`.

`send()` không nhận kiểu response vì tương tác không có response payload. Khác với `retrieveMono(Receipt.class)`, nó không yêu cầu server trả một `Receipt` hoặc object nào khác.

Nếu cần thêm metadata, có thể gắn metadata trước khi gọi `send()`:

```java
Mono<Void> publishAudit(AuditEvent event, String traceId) {
    return requester
        .route("audit.record")
        .metadata(traceId, MimeType.valueOf("text/plain"))
        .data(event)
        .send();
}
```

Metadata cần có MIME type và decoder tương ứng ở phía nhận. Không đưa token bí mật hoặc dữ liệu nhạy cảm vào route; hãy dùng cơ chế xác thực/metadata phù hợp và bảo vệ transport khi cần.

## 3. Vì sao `send()` trả về `Mono<Void>`?

`Mono<Void>` biểu diễn một thao tác bất đồng bộ không phát giá trị dữ liệu. Publisher có thể:

- **Complete:** thao tác gửi ở phía requester đã hoàn tất theo contract của API/runtime.
- **Error:** thao tác gửi không thể hoàn tất, ví dụ kết nối đã đóng, lỗi serialize payload hoặc lỗi khi ghi dữ liệu ra transport.
- **Chưa terminal:** thao tác vẫn đang chờ được xử lý hoặc chờ điều kiện gửi phù hợp.

Vì kiểu là `Void`, không có `onNext` mang response. Khi thành công, subscriber nhận `onComplete` mà không nhận một object kết quả.

```java
requester.route("audit.record")
    .data(event)
    .send()
    .doOnSuccess(ignored -> log.debug("FNF send completed"))
    .doOnError(error -> log.warn("FNF send failed", error));
```

Với `Mono<Void>`, callback `doOnSuccess` có thể được gọi với giá trị `null` khi publisher complete bình thường. Nếu muốn quan sát mọi tín hiệu terminal, `doFinally` cũng hữu ích:

```java
return requester.route("audit.record")
    .data(event)
    .send()
    .doFinally(signal -> log.debug("FNF finished: {}", signal));
```

`doFinally` nhận `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`. `CANCEL` không phải thành công; nó cho biết subscriber đã hủy subscription trước khi publisher kết thúc.

## 4. Complete ở client không phải acknowledgement từ server

Đây là điểm quan trọng nhất khi thiết kế fire-and-forget.

`Mono<Void>` của `send()` cho biết kết quả của thao tác gửi ở phía requester theo runtime. Nó không tạo một round-trip để hỏi server đã xử lý nghiệp vụ hay chưa. Vì không có response payload, client không thể phân biệt chắc chắn các trường hợp như:

- Server đã nhận và xử lý xong sự kiện.
- Server đã nhận request nhưng handler vẫn đang xử lý.
- Server nhận request rồi gặp lỗi trong logic nghiệp vụ.
- Kết nối bị gián đoạn ở thời điểm khiến client không biết request đã đến server hay chưa.

Vì vậy, không nên đặt tên log hoặc metric là `serverProcessedSuccessfully` chỉ dựa trên `send().doOnSuccess(...)`. Tên chính xác hơn là `sendCompleted` hoặc `outboundSendCompleted`.

```text
Client                                      Server
  |                                           |
  | REQUEST_FNF ----------------------------->|
  |                                           | bắt đầu handler
  | Mono<Void> complete ở client              | tiếp tục xử lý
  |                                           |
  |                                           | handler có thể complete
  |                                           | hoặc phát sinh lỗi
  |                                           |
  |       không có acknowledgement response   |
```

Nếu nghiệp vụ yêu cầu xác nhận server đã xử lý, hãy dùng một trong các cách sau:

1. Đổi sang request-response để server trả receipt hoặc trạng thái xử lý.
2. Gửi fire-and-forget kèm correlation ID, sau đó nhận kết quả qua một stream/event riêng.
3. Dùng một hệ thống message broker có acknowledgement/durable delivery nếu yêu cầu lưu trữ và giao nhận vượt quá contract của fire-and-forget.

## 5. Subscribe mới kích hoạt pipeline

Các publisher Reactor thường lazy. Việc tạo `Mono<Void>` không có nghĩa request đã được gửi. Subscription mới kích hoạt quá trình thực thi:

```java
Mono<Void> pending = requester
    .route("audit.record")
    .data(event)
    .send();

// Chưa có subscription: thao tác gửi chưa được kích hoạt.

return pending; // Caller hoặc framework subscribe ở ranh giới phù hợp.
```

Nếu một method service trả `Mono<Void>` cho controller WebFlux hoặc một pipeline reactive khác, framework/caller sẽ subscribe khi xử lý request bên ngoài. Nếu viết một tác vụ độc lập không có caller reactive, ứng dụng cần tạo subscription có quản lý:

```java
Disposable sendTask = requester
    .route("audit.record")
    .data(event)
    .send()
    .subscribe(
        ignored -> { },
        error -> log.error("Cannot send audit event", error),
        () -> log.debug("Audit send completed")
    );
```

Overload `subscribe(onNext, onError, onComplete)` được minh họa ở đây để thể hiện nơi xử lý lỗi và hoàn tất. Vì publisher là `Mono<Void>`, callback `onNext` không phát giá trị; phần quan trọng là error và completion. Nếu subscription có thể sống lâu, hãy quản lý `Disposable` theo vòng đời của tác vụ.

Không gọi `subscribe()` bên trong service rồi bỏ qua publisher trả về. Cách đó tách lỗi và cancellation khỏi caller, khiến ứng dụng khó điều phối shutdown và kiểm thử.

## 6. Handler phía server xử lý fire-and-forget

Ở phía server Spring RSocket, handler có thể nhận payload và trả `Mono<Void>`:

```java
@Controller
public class AuditController {

    private final AuditService auditService;

    public AuditController(AuditService auditService) {
        this.auditService = auditService;
    }

    @MessageMapping("audit.record")
    public Mono<Void> record(@Payload AuditEvent event) {
        return auditService.record(event);
    }
}
```

Spring kết nối handler với interaction model mà requester đã chọn. Với fire-and-forget, publisher của handler được framework subscribe và theo dõi ở phía server; không có response payload được gửi về requester.

Nếu service hoàn tất, handler hoàn tất. Nếu service phát lỗi, lỗi thuộc phía server và cần được ghi nhận/xử lý ở server. Vì tương tác không có response, client không nhận được exception nghiệp vụ đó qua `send()`.

Ví dụ thêm xử lý lỗi tại server:

```java
@MessageMapping("telemetry.ingest")
public Mono<Void> ingest(@Payload Telemetry telemetry) {
    return telemetryService.store(telemetry)
        .doOnError(error -> log.error(
            "Telemetry processing failed: device={}",
            telemetry.deviceId(), error));
}
```

Không nuốt lỗi bằng `onErrorComplete()` chỉ để handler không báo lỗi. Nếu nghiệp vụ thất bại, server vẫn cần metric, log có correlation ID hoặc một cơ chế retry nội bộ phù hợp.

## 7. Kết hợp `send()` với pipeline reactive

`send()` có thể được ghép với các publisher khác bằng operator Reactor. Ví dụ, gửi một sự kiện sau khi một bước nghiệp vụ hoàn tất:

```java
Mono<Void> createOrder(CreateOrder command) {
    return orderService.create(command)
        .flatMap(order -> requester
            .route("orders.created")
            .data(new OrderCreated(order.id(), order.createdAt()))
            .send());
}
```

Ở ví dụ này, `flatMap` đợi `orderService.create(...)` phát ra order rồi mới khởi tạo thao tác gửi. `Mono<Void>` cuối cùng complete sau khi publisher gửi complete; nó không xác nhận consumer phía xa đã xử lý event.

Nếu cần gửi nhiều sự kiện từ một nguồn `Flux`, có thể dùng `concatMap` để giữ thứ tự gửi theo từng phần tử:

```java
Mono<Void> publishAll(Flux<AuditEvent> events) {
    return events
        .concatMap(event -> requester
            .route("audit.record")
            .data(event)
            .send())
        .then();
}
```

`concatMap` thực hiện từng publisher con theo thứ tự, chỉ chuyển sang phần tử tiếp theo sau khi `send()` trước đó complete. Nếu dùng `flatMap`, nhiều thao tác gửi có thể được thực hiện đồng thời; thứ tự hoàn tất có thể khác thứ tự đầu vào.

Đối với nguồn sự kiện có tốc độ cao, cần cân nhắc backpressure, giới hạn concurrency và buffer. Không tạo một hàng đợi vô hạn các `Mono<Void>` trong bộ nhớ khi server hoặc kết nối không theo kịp.

## 8. Xử lý lỗi gửi và retry

Lỗi từ `send()` có thể xuất hiện khi không thể gửi request, chẳng hạn requester đã đóng, transport lỗi hoặc dữ liệu không serialize được. Có thể chuyển lỗi sang loại lỗi miền ứng dụng:

```java
Mono<Void> publish(AuditEvent event) {
    return requester
        .route("audit.record")
        .data(event)
        .send()
        .onErrorMap(error -> new AuditPublishException(
            "Unable to send audit event", error));
}
```

Có thể retry với backoff khi chính sách nghiệp vụ cho phép:

```java
Mono<Void> publishWithRetry(AuditEvent event) {
    return requester
        .route("audit.record")
        .data(event)
        .send()
        .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(2)));
}
```

Tuy nhiên, retry fire-and-forget có thể gửi cùng sự kiện nhiều lần. Nếu lần gửi trước đã đến server nhưng client mất kết nối trước khi nhận biết thao tác gửi hoàn tất, retry có thể tạo bản sao. Với các sự kiện cần xử lý đúng một lần ở góc nhìn nghiệp vụ, hãy đưa event ID/idempotency key vào payload và để server deduplicate.

Ví dụ DTO có event ID:

```java
public record AuditEvent(
    UUID eventId,
    String actor,
    String action,
    Instant occurredAt
) {}
```

Server có thể lưu `eventId` với unique constraint hoặc dùng kho deduplication có thời hạn. Fire-and-forget tự nó không cung cấp exactly-once processing.

## 9. Timeout và cancellation

Có thể đặt timeout cho thao tác gửi:

```java
Mono<Void> sendWithTimeout(AuditEvent event) {
    return requester
        .route("audit.record")
        .data(event)
        .send()
        .timeout(Duration.ofSeconds(1));
}
```

Nếu timeout xảy ra, operator phát lỗi timeout và hủy subscription upstream. Điều này dừng việc chờ publisher ở phía client và runtime có thể dừng thao tác chưa hoàn tất nếu còn khả năng. Nhưng timeout không chứng minh server chưa nhận request hoặc chưa bắt đầu xử lý.

Tương tự, caller có thể hủy subscription khi không còn cần chờ thao tác gửi. Cancellation không phải một thông điệp hủy nghiệp vụ được bảo đảm đến server. Nếu server đã nhận `REQUEST_FNF`, handler có thể vẫn tiếp tục chạy.

Với tác vụ quan trọng, hãy xác định rõ deadline và trạng thái nghiệp vụ thay vì suy luận từ timeout/cancel ở client.

## 10. Phân biệt send complete, handler complete và business acknowledgement

Ba khái niệm này nằm ở các ranh giới khác nhau:

| Tín hiệu | Quan sát ở đâu? | Có chứng minh server xử lý xong nghiệp vụ? |
|---|---|---|
| `send()` complete | Requester/client | Không. Chỉ cho biết publisher gửi hoàn tất theo runtime. |
| Handler `Mono<Void>` complete | Responder/server | Cho biết publisher handler đã hoàn tất; không có tín hiệu này gửi ngược về requester trong FNF. |
| Business acknowledgement | Một tương tác/response/event riêng được ứng dụng thiết kế | Có thể, nếu contract định nghĩa rõ điều kiện xác nhận và thời điểm commit. |

Nếu yêu cầu là “server đã lưu audit event thành công”, cần một acknowledgement được gửi sau khi thao tác lưu hoàn tất, chẳng hạn:

```java
Mono<AuditReceipt> receipt = requester
    .route("audit.record-and-confirm")
    .data(event)
    .retrieveMono(AuditReceipt.class);
```

Khi đó server trả `AuditReceipt` sau khi ghi thành công. Client có thể phân biệt thành công, lỗi và timeout theo response contract. Đây là request-response, không còn là fire-and-forget.

## 11. So sánh `send()` với `retrieveMono()` và `retrieveFlux()`

Các terminal operations của `RSocketRequester` biểu diễn các interaction model khác nhau:

| Terminal operation | Tương tác | Publisher trả về | Có response payload? |
|---|---|---|---:|
| `send()` | Fire-and-forget | `Mono<Void>` | Không |
| `retrieveMono(Type.class)` | Request-response | `Mono<T>` | Tối đa một |
| `retrieveFlux(Type.class)` | Request-stream | `Flux<T>` | Nhiều |
| `retrieveFlux(Type.class)` với publisher đầu vào theo API channel | Request-channel | `Flux<T>` | Nhiều, hai chiều |

Không chọn `send()` chỉ vì muốn code ngắn. Hãy chọn nó khi caller thực sự không cần response payload và chấp nhận không có xác nhận xử lý ở phía xa.

## 12. Gửi metadata và correlation ID

Một fire-and-forget request vẫn có thể chứa routing metadata và custom metadata. Correlation ID hữu ích để nối log ở client với log server dù không có response:

```java
Mono<Void> publish(AuditEvent event, UUID correlationId) {
    return requester
        .route("audit.record")
        .metadata(correlationId.toString(), MimeType.valueOf("text/plain"))
        .data(event)
        .send()
        .doOnError(error -> log.warn(
            "Audit send failed, correlationId={}", correlationId, error));
}
```

Server cần cấu hình metadata extractor tương ứng để đọc metadata đó, hoặc đưa correlation ID vào payload nếu đó là một phần của hợp đồng nghiệp vụ. Không ghi token xác thực hoặc metadata nhạy cảm đầy đủ vào log.

## 13. Những lỗi thường gặp

| Lỗi | Vì sao sai? | Cách xử lý |
|---|---|---|
| Coi `send()` complete là server đã xử lý xong | FNF không có response payload/acknowledgement. | Dùng request-response hoặc acknowledgement riêng nếu cần xác nhận. |
| Tạo `Mono<Void>` nhưng không subscribe hoặc không trả cho framework | Publisher lazy nên thao tác gửi không chạy. | Trả publisher cho caller reactive hoặc subscribe có quản lý ở ranh giới tác vụ. |
| Dùng `send()` cho thao tác cần kết quả | Caller không nhận được receipt hoặc trạng thái nghiệp vụ. | Dùng `retrieveMono(...)`. |
| Nuốt mọi lỗi bằng `onErrorComplete()` | Mất dấu vết lỗi gửi và lỗi hệ thống. | Log/metric, chuyển lỗi hoặc retry theo chính sách. |
| Retry không có event ID | Sự kiện có thể được xử lý trùng. | Dùng idempotency key và deduplication ở server. |
| Gọi `subscribe()` trong service rồi bỏ subscription | Lỗi/cancellation tách khỏi caller, khó quản lý shutdown. | Compose `Mono<Void>` và trả về caller. |
| Dùng timeout như bằng chứng request chưa đến server | Server có thể đã nhận hoặc đang xử lý. | Đối soát bằng event ID hoặc trạng thái nghiệp vụ. |
| Cho rằng cancel ở client hủy chắc chắn handler server | FNF không có response channel để xác nhận hủy nghiệp vụ. | Thiết kế command/cancel riêng nếu cần dừng công việc phía server. |
| Gửi luồng sự kiện không giới hạn concurrency | Có thể tạo nhiều thao tác gửi đang chờ và tăng bộ nhớ. | Dùng `concatMap`, giới hạn concurrency và buffer có giới hạn. |

## 14. Kiểm thử fire-and-forget

Kiểm thử cần xác minh hai mặt: client phát đúng interaction và server nhận/thi hành handler. Chỉ kiểm tra `Mono<Void>` complete không đủ để khẳng định nghiệp vụ đã được xử lý.

Các trường hợp nên có:

1. Client gửi request qua route đúng và server handler được gọi.
2. Data payload được deserialize thành đúng DTO.
3. Metadata/correlation ID được trích xuất nếu ứng dụng sử dụng.
4. `send()` complete khi thao tác gửi hoàn tất ở client.
5. Lỗi kết nối hoặc serialize được truyền thành `onError`.
6. Server handler phát lỗi; xác minh lỗi được quan sát ở server vì FNF không trả lỗi nghiệp vụ về client.
7. Retry gửi cùng event ID; server deduplicate và không lặp side effect.
8. Cancellation/timeout phía client không bị hiểu nhầm là rollback xử lý server.

Ví dụ kiểm thử publisher phía client:

```java
StepVerifier.create(
        requester.route("audit.record")
            .data(event)
            .send())
    .verifyComplete();
```

Để xác minh server đã xử lý event, dùng một test probe, repository test hoặc latch ở test fixture phía server. Không suy luận việc handler đã chạy chỉ từ `verifyComplete()` của client.

## Kết luận

`RSocketRequester.send()` thực hiện fire-and-forget: gửi một payload qua route và trả `Mono<Void>`. Publisher chỉ phát tín hiệu hoàn tất hoặc lỗi, không phát response payload. `send()` cần subscription để chạy; complete biểu thị thao tác gửi hoàn tất theo runtime phía client, không phải xác nhận server đã xử lý nghiệp vụ. Ở phía server, handler có thể trả `Mono<Void>` và cần tự ghi nhận lỗi vì chúng không được gửi ngược về requester trong FNF. Hãy dùng fire-and-forget cho thông báo không cần kết quả, quản lý retry bằng event ID/idempotency và chuyển sang request-response khi cần acknowledgement rõ ràng.
