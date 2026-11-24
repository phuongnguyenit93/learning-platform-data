# Hợp đồng `io.rsocket.RSocket` và bốn phương thức tương tác

Trong RSocket Java, `io.rsocket.RSocket` là hợp đồng API cốt lõi để một peer gửi và nhận các tương tác reactive. Interface này biểu diễn một endpoint RSocket đã được thiết lập; cùng một kiểu API được dùng ở cả phía requester và responder. Bốn phương thức tương tác chính là `fireAndForget`, `requestResponse`, `requestStream` và `requestChannel`.

Các phương thức trả về `Mono` hoặc `Flux`, vì vậy lời gọi API mô tả một thao tác bất đồng bộ. Khi publisher được subscribe, runtime thực hiện tương tác trên kết nối. Kiểu publisher cho biết caller sẽ nhận được một kết quả, một chuỗi kết quả hay chỉ theo dõi việc gửi request.

## 1. Vai trò của interface RSocket

`RSocket` là abstraction ở tầng tương tác. Nó không phải socket TCP thông thường và cũng không phải class dùng để tự mã hóa frame. Transport và protocol runtime đảm nhiệm việc truyền frame, stream ID, serialization và flow control; ứng dụng gọi các phương thức trên interface để khởi tạo tương tác.

Một peer có thể vừa khởi tạo request vừa xử lý request từ peer bên kia. Vì vậy, không nên hiểu `RSocket` là interface chỉ dành cho client. Khi kết nối hai chiều đã được thiết lập, mỗi phía có thể giữ một endpoint để gửi request sang phía còn lại.

Các phương thức tương tác cốt lõi có dạng:

```java
public interface RSocket {
    Mono<Void> fireAndForget(Payload payload);

    Mono<Payload> requestResponse(Payload payload);

    Flux<Payload> requestStream(Payload payload);

    Flux<Payload> requestChannel(Publisher<Payload> payloads);
}
```

Đây là phần hợp đồng tương tác chính được rút gọn để dễ đọc. Interface trong thư viện còn có các phương thức phục vụ metadata và vòng đời kết nối, tùy phiên bản RSocket Java.

## 2. Payload là đơn vị dữ liệu của RSocket

Bốn phương thức nhận hoặc trả về `io.rsocket.Payload`. Payload có hai vùng nội dung:

| Vùng | Vai trò | Ví dụ |
|---|---|---|
| Data | Nội dung chính của request hoặc response. | JSON của `QuoteRequest`, bytes của ảnh, dữ liệu nhị phân. |
| Metadata | Thông tin bổ sung để định tuyến hoặc diễn giải data. | Route, authentication, trace context, tenant. |

Payload không tự mang một kiểu Java như `Quote` hay `Order`. Ở API mức thấp, ứng dụng làm việc với bytes và cần encoder/decoder để chuyển giữa object với payload. Spring RSocket có thể thực hiện việc này thông qua `RSocketStrategies` và message codecs.

Tạo payload đơn giản:

```java
Payload request = DefaultPayload.create("ACME");

Payload requestWithMetadata = DefaultPayload.create(
    "ACME",
    "{\"traceId\":\"trace-123\"}");
```

Ví dụ thứ hai minh họa data và nội dung metadata dưới dạng chuỗi. MIME type mô tả metadata phải được cấu hình/thống nhất riêng giữa hai phía; chuỗi JSON ở đây là nội dung metadata, không phải tên MIME type.

`Payload` thường được triển khai trên Netty `ByteBuf` và có thể là đối tượng reference-counted. Khi dùng API mức thấp, hãy tuân thủ quy tắc ownership của phiên bản thư viện: không truy cập buffer sau khi đã release, không release quá sớm khi runtime còn sử dụng, và release payload nhận được sau khi đã xử lý nếu ứng dụng đang sở hữu reference đó. Không giữ `ByteBuf` qua ranh giới bất đồng bộ nếu chưa `retain()` đúng cách.

## 3. Bốn phương thức tương tác

| Phương thức | Request đầu vào | Kết quả API | Mô hình tương tác |
|---|---|---|---|
| `fireAndForget(Payload)` | Một payload | `Mono<Void>` | Một chiều, không chờ response payload. |
| `requestResponse(Payload)` | Một payload | `Mono<Payload>` | Một request, một response. |
| `requestStream(Payload)` | Một payload | `Flux<Payload>` | Một request, nhiều response payload. |
| `requestChannel(Publisher<Payload>)` | Một publisher payload | `Flux<Payload>` | Hai luồng payload, mỗi phía vừa gửi vừa nhận. |

Sự khác nhau chính nằm ở số lượng dữ liệu và hướng truyền. Hãy chọn interaction model theo hợp đồng nghiệp vụ: gửi một sự kiện không cần phản hồi, hỏi một câu và nhận một kết quả, yêu cầu một luồng dữ liệu, hay mở một channel để trao đổi liên tục hai chiều.

## 4. `fireAndForget`: gửi request không chờ response

`fireAndForget(Payload)` gửi một request mà requester không yêu cầu response payload. Phương thức trả `Mono<Void>` để caller theo dõi việc hoàn tất hoặc lỗi của thao tác gửi.

```java
Mono<Void> sent = socket.fireAndForget(
    DefaultPayload.create("audit: user signed in"));

return sent;
```

Một ví dụ khác là gửi sự kiện telemetry hoặc audit mà caller không cần dữ liệu phản hồi:

```java
Mono<Void> recordAudit(AuditEvent event) {
    Payload payload = payloadEncoder.encode(event);
    return socket.fireAndForget(payload);
}
```

**Điểm cần hiểu:** fire-and-forget không có response payload ở tầng RSocket. Khi `Mono<Void>` hoàn tất, điều đó không tự chứng minh rằng nghiệp vụ ở server đã được ghi bền vững hoặc xử lý xong. Nó biểu thị trạng thái hoàn tất của thao tác gửi theo runtime/transport. Nếu caller cần xác nhận nghiệp vụ, hãy dùng request-response hoặc thiết kế acknowledgement riêng.

Nếu việc gửi thất bại, publisher có thể kết thúc bằng `onError`. Hãy xử lý lỗi ở caller hoặc để lỗi tiếp tục qua pipeline reactive; không bỏ qua lỗi bằng cách tự subscribe mà không có error handler.

## 5. `requestResponse`: một request và một response

`requestResponse(Payload)` gửi một payload và trả về `Mono<Payload>`. Đây là lựa chọn phù hợp cho các thao tác hỏi đáp có một kết quả, chẳng hạn tra cứu hồ sơ, lấy giá hiện tại hoặc xác nhận một lệnh.

```java
Mono<Quote> latestQuote(String symbol) {
    Payload request = DefaultPayload.create(symbol);

    return socket.requestResponse(request)
        .map(response -> {
            try {
                return quoteDecoder.decode(response.data());
            } finally {
                response.release();
            }
        });
}
```

`Mono` biểu diễn tối đa một response payload. Caller có thể dùng các operator như `map`, `flatMap`, `timeout`, `onErrorMap` hoặc `retryWhen` để xử lý kết quả và lỗi. Việc timeout hoặc retry cần cân nhắc side effect: timeout không chứng minh server chưa xử lý request.

Request-response dùng cùng stream ID cho request và response. Runtime xử lý việc tạo frame, nhận response và kết thúc tương tác; ứng dụng không cần tự quản lý stream ID.

## 6. `requestStream`: một request và nhiều response

`requestStream(Payload)` mở một tương tác request-stream và trả `Flux<Payload>`. Server có thể phát nhiều response payload theo thời gian. Subscriber kiểm soát demand bằng backpressure; runtime ánh xạ demand đó sang flow control của RSocket.

```java
Flux<Quote> watchQuotes(String symbol) {
    Payload request = DefaultPayload.create(symbol);

    return socket.requestStream(request)
        .map(payload -> {
            try {
                return quoteDecoder.decode(payload.data());
            } finally {
                payload.release();
            }
        });
}
```

Ví dụ trên trả về `Flux<Quote>` để caller quyết định lúc subscribe, cách xử lý từng quote và thời điểm hủy. Nếu caller chỉ cần mười phần tử đầu tiên, có thể dùng:

```java
return watchQuotes("ACME").take(10);
```

`take(10)` hủy upstream sau tối đa mười phần tử. Runtime có thể gửi `CANCEL` để responder dừng công việc liên quan. Với stream dài hạn, cần cleanup tài nguyên khi hoàn tất, lỗi hoặc bị hủy.

## 7. `requestChannel`: trao đổi payload hai chiều

`requestChannel(Publisher<Payload>)` nhận một publisher chứa các payload requester gửi lên và trả `Flux<Payload>` chứa các payload responder gửi về. Đây là mô hình hai chiều: mỗi phía có thể phát dữ liệu trong khi vẫn nhận dữ liệu từ peer.

```java
Flux<Payload> commands = Flux.just(
    DefaultPayload.create("subscribe:ACME"),
    DefaultPayload.create("set-frequency:1s"),
    DefaultPayload.create("pause:false"));

Flux<Payload> updates = socket.requestChannel(commands);
```

Trong request-channel, publisher đầu vào mô tả luồng dữ liệu đi từ requester đến responder; `Flux` trả về mô tả luồng dữ liệu chiều ngược lại. Channel bắt đầu bằng payload mở đầu theo quy tắc protocol. Vì vậy, ứng dụng cần cung cấp phần tử mở đầu hợp lệ thay vì giả định một publisher rỗng có thể tạo channel.

Hai chiều có demand và vòng đời riêng:

- Demand của subscriber đối với `Flux` response điều tiết số payload responder gửi về.
- Demand mà responder cấp cho publisher đầu vào điều tiết số payload requester gửi lên.
- Publisher đầu vào hoàn tất nghĩa là requester không gửi thêm payload; responder vẫn có thể còn dữ liệu response.
- Response `Flux` hoàn tất nghĩa là responder đã kết thúc chiều gửi về; không nhất thiết cùng thời điểm publisher đầu vào hoàn tất.

Đây là mô hình hữu ích cho điều khiển realtime, trao đổi lệnh và sự kiện, hoặc một client vừa gửi trạng thái vừa nhận cập nhật liên tục.

## 8. Luồng frame tương ứng với bốn interaction model

Ở tầng giao thức, các phương thức Java được ánh xạ sang các frame mở đầu khác nhau:

| API Java | Frame mở đầu | Luồng response điển hình |
|---|---|---|
| `fireAndForget` | `REQUEST_FNF` | Không có response payload. |
| `requestResponse` | `REQUEST_RESPONSE` | Một `PAYLOAD` terminal hoặc `ERROR`. |
| `requestStream` | `REQUEST_STREAM` | Nhiều `PAYLOAD`, sau đó `COMPLETE` hoặc `ERROR`. |
| `requestChannel` | `REQUEST_CHANNEL` | `PAYLOAD` hai chiều, có thể tiếp tục cho đến khi hai phía hoàn tất hoặc bị hủy. |

Các frame điều khiển như `REQUEST_N`, `CANCEL`, `ERROR` và cờ `COMPLETE` được runtime xử lý. Ứng dụng nên thao tác qua `Mono`, `Flux` và `Publisher` thay vì tự xây dựng frame nếu không viết một implementation protocol.

## 9. Hợp đồng Reactive Streams: subscribe, demand và cancel

Các phương thức tương tác trả về publisher. Vì vậy, cần hiểu ba tín hiệu trong Reactive Streams:

1. **Subscribe:** subscriber đăng ký nhận kết quả. Runtime bắt đầu hoặc kích hoạt tương tác khi publisher được subscribe.
2. **Request:** subscriber yêu cầu số phần tử có thể tiêu thụ. Với stream và channel, demand điều tiết lượng payload được phát.
3. **Cancel:** subscriber không còn cần dữ liệu. Cancellation được truyền ngược lên upstream và có thể kết thúc stream RSocket.

Không gọi `subscribe()` bên trong service chỉ để “cho request chạy” rồi trả về một publisher khác. Cách đó tạo một subscription tách rời, làm caller khó kiểm soát lỗi, cancellation và thời điểm hoàn tất. Hãy kết hợp các publisher bằng operator và trả publisher cho framework hoặc caller sở hữu vòng đời.

Ví dụ kết hợp request-response:

```java
Mono<QuoteView> loadQuote(String symbol) {
    return socket.requestResponse(DefaultPayload.create(symbol))
        .map(this::decodeAndRelease)
        .timeout(Duration.ofSeconds(2))
        .map(this::toView);
}
```

Với `requestStream` và `requestChannel`, không yêu cầu dữ liệu không giới hạn nếu consumer có tốc độ xử lý thấp hoặc dữ liệu có thể tăng liên tục. Có thể điều khiển demand bằng `BaseSubscriber`, `limitRate` hoặc operator phù hợp.

## 10. Lỗi và cancellation

Lỗi trong tương tác được truyền qua publisher bằng `onError`. Ở tầng giao thức, lỗi của một stream được biểu diễn bằng frame `ERROR` trên stream ID tương ứng. Không phải lỗi stream nào cũng đồng nghĩa kết nối đã hỏng; các stream độc lập khác có thể tiếp tục.

Cancellation xảy ra khi subscriber hủy subscription, ví dụ người dùng rời màn hình hoặc operator `take` đã nhận đủ dữ liệu. Runtime có thể gửi `CANCEL` đến peer. Responder nên quan sát cancellation để dừng truy vấn, đóng resource hoặc ngừng tác vụ nền nếu có thể.

```java
Flux<Quote> quotes = socket.requestStream(
        DefaultPayload.create("ACME"))
    .doOnCancel(() -> log.debug("Quote stream cancelled"))
    .doFinally(signal -> log.debug("Quote stream ended: {}", signal));
```

Không giả định cancellation hoàn tác side effect đã thực hiện. Nếu một request tạo đơn hàng đã được xử lý trước khi cancel hoặc timeout đến nơi, việc hủy stream không tự động rollback giao dịch nghiệp vụ.

## 11. Vòng đời của RSocket endpoint

Ngoài bốn interaction method, `RSocket` còn có các API liên quan đến trạng thái endpoint và vòng đời kết nối. Tùy phiên bản, các API thường gặp gồm:

| API | Ý nghĩa |
|---|---|
| `availability()` | Trả về mức availability của endpoint dưới dạng giá trị từ `0.0` đến `1.0`; ứng dụng có thể dùng làm tín hiệu sức khỏe/khả năng nhận request. |
| `onClose()` | Publisher hoàn tất khi endpoint đóng hoặc kết nối kết thúc. |
| `dispose()` | Bắt đầu đóng endpoint và giải phóng tài nguyên liên quan. |
| `metadataPush(Payload)` | Gửi metadata một chiều ở cấp kết nối; đây là API riêng, không phải một trong bốn interaction model chính. |

Ví dụ theo dõi vòng đời:

```java
socket.onClose()
    .doFinally(signal -> log.info("RSocket closed: {}", signal))
    .subscribe();
```

Trong ứng dụng Spring, framework thường quản lý vòng đời requester và connection. Nếu tự dùng `RSocketConnector` hoặc `RSocketServer`, cần đóng endpoint đúng lúc và xử lý `onClose()` để tránh rò rỉ tài nguyên.

## 12. Sử dụng RSocket qua Spring Boot

Spring cung cấp abstraction mức cao hơn `RSocket` để ứng dụng làm việc với object Java và route. `RSocketRequester` xây dựng các tương tác tương ứng:

```java
Mono<Quote> quote = requester
    .route("quotes.latest")
    .data(new QuoteRequest("ACME"))
    .retrieveMono(Quote.class);

Flux<Quote> stream = requester
    .route("quotes.stream")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(Quote.class);
```

Phía server có thể dùng `@MessageMapping` và kiểu trả về để biểu đạt interaction:

```java
@Controller
class QuoteController {

    @MessageMapping("quotes.latest")
    Mono<Quote> latest(QuoteRequest request) {
        return quoteService.latest(request.symbol());
    }

    @MessageMapping("quotes.stream")
    Flux<Quote> stream(QuoteRequest request) {
        return quoteService.stream(request.symbol());
    }

    @MessageMapping("audit.record")
    Mono<Void> record(AuditEvent event) {
        return auditService.record(event);
    }

    @MessageMapping("quotes.channel")
    Flux<Quote> channel(Flux<QuoteCommand> commands) {
        return quoteService.handle(commands);
    }
}
```

Spring chuyển đổi payload và metadata qua message codecs, định tuyến theo route và quản lý subscription cho publisher mà handler trả về. Ở cấp ứng dụng, nên giữ `Mono`/`Flux` xuyên suốt service để lỗi và cancellation được truyền đúng vòng đời request.

## 13. Chọn phương thức theo yêu cầu nghiệp vụ

| Nhu cầu | Phương thức phù hợp | Lưu ý |
|---|---|---|
| Gửi log/sự kiện mà caller không cần response | `fireAndForget` | Không dùng khi caller cần xác nhận xử lý nghiệp vụ. |
| Tra cứu một đối tượng hoặc yêu cầu một kết quả | `requestResponse` | Xử lý timeout và lỗi rõ ràng. |
| Nhận giá, trạng thái hoặc sự kiện liên tục từ một request | `requestStream` | Chú ý demand, cancellation và cleanup. |
| Vừa gửi lệnh vừa nhận dữ liệu liên tục | `requestChannel` | Quản lý demand và completion ở cả hai chiều. |

Một lỗi thiết kế phổ biến là dùng `requestStream` cho trường hợp cần trao đổi dữ liệu hai chiều. Nếu client cũng cần gửi payload liên tục trong lúc nhận response, `requestChannel` thể hiện đúng hợp đồng hơn. Ngược lại, nếu chỉ cần gửi một request rồi nhận một luồng response, `requestStream` đơn giản hơn.

## 14. Kiểm thử bốn interaction model

Nên kiểm thử cả ngữ nghĩa publisher và hành vi giao thức qua kết nối thật hoặc transport test phù hợp.

**Fire-and-forget:** xác minh server nhận request và publisher phía client hoàn tất/lỗi đúng với trạng thái gửi. Nếu cần kiểm tra side effect, xác minh bằng trạng thái nghiệp vụ riêng vì fire-and-forget không trả response payload.

**Request-response:** xác minh đúng một response được giải mã, lỗi được truyền về client và timeout được xử lý.

**Request-stream:** kiểm tra thứ tự payload, demand theo lô, hoàn tất, lỗi và cancellation sau `take(n)`.

**Request-channel:** kiểm tra nhiều payload chiều lên và chiều xuống, hai chiều hoàn tất độc lập, backpressure và hủy channel.

Ở tầng Reactor, `StepVerifier` có thể kiểm tra publisher:

```java
StepVerifier.create(socket.requestStream(
        DefaultPayload.create("ACME")))
    .expectNextCount(3)
    .thenCancel()
    .verify();
```

Đây là kiểm thử minh họa cho stream có ít nhất ba phần tử trước khi hủy. Trong test thực tế, cần cấu hình server test phát dữ liệu xác định và giải phóng mọi `Payload` đã nhận.

## 15. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ `fireAndForget` xác nhận server đã xử lý xong. | Caller có thể báo thành công dù nghiệp vụ phía server chưa hoàn tất. | Dùng request-response hoặc acknowledgement riêng nếu cần xác nhận. |
| Dùng `requestResponse` cho dữ liệu phát liên tục. | Phải tạo nhiều request riêng và khó biểu đạt stream. | Dùng `requestStream` hoặc `requestChannel` tùy hướng dữ liệu. |
| Dùng `requestStream` khi client cũng cần gửi dữ liệu liên tục. | Không biểu đạt được chiều gửi request dạng stream. | Dùng `requestChannel`. |
| Gọi `subscribe()` thủ công bên trong service. | Mất khả năng truyền lỗi và cancellation về caller. | Trả `Mono`/`Flux` và compose bằng operator. |
| Bỏ qua demand trong stream/channel. | Buffer tăng hoặc consumer bị quá tải. | Điều khiển backpressure và giới hạn buffer. |
| Quên giải phóng Payload/ByteBuf. | Rò rỉ bộ nhớ native hoặc truy cập buffer sau release. | Tuân thủ ownership, retain/release đúng vòng đời. |
| Không xử lý lỗi và cancellation. | Stream tiếp tục giữ tài nguyên hoặc lỗi bị mất. | Xử lý `onError`, `doFinally`, `doOnCancel` và cleanup. |
| Retry thao tác có side effect mà không idempotency. | Có thể thực hiện nghiệp vụ nhiều lần sau timeout hoặc reconnect. | Dùng idempotency key và đối soát kết quả. |

## Tài liệu tham khảo

- [RSocket Java — API](https://github.com/rsocket/rsocket-java) — interface `io.rsocket.RSocket`, `Payload`, connector và server.
- [RSocket Protocol](https://rsocket.io/about/protocol/) — bốn interaction model và các frame tương ứng.
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — `RSocketRequester`, `@MessageMapping` và tích hợp reactive.
- [RSocket Java 1.1.5 — RSocket Javadoc](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/RSocket.html) — hợp đồng API ở tầng Java.

## Kết luận

`io.rsocket.RSocket` định nghĩa cách một peer khởi tạo các tương tác reactive. `fireAndForget` gửi một chiều không chờ response payload; `requestResponse` nhận một response; `requestStream` nhận nhiều response; `requestChannel` trao đổi publisher payload hai chiều. Các phương thức này kết hợp với `Mono`, `Flux`, demand và cancellation để mô tả vòng đời tương tác. Khi triển khai, hãy chọn interaction model theo luồng nghiệp vụ, để publisher được compose xuyên suốt, quản lý Payload/ByteBuf đúng ownership và xử lý lỗi, backpressure cùng cancellation ở cả hai phía.
