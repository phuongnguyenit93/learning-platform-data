# RSocket và giao thức trao đổi dữ liệu phản ứng

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích RSocket là giao thức messaging hai chiều và cách nó hoạt động trên một kết nối.
- Phân biệt bốn mô hình tương tác: request-response, fire-and-forget, request-stream và request-channel.
- Hiểu vai trò của data, metadata, route, transport và quá trình thiết lập kết nối.
- Dùng Spring Framework với `RSocketRequester` ở phía requester và `@MessageMapping` ở phía responder.
- Kết hợp `Mono`, `Flux` và Reactive Streams để xử lý dữ liệu bất đồng bộ có backpressure.
- Xử lý lỗi, hủy stream, serialization và bảo mật trong ứng dụng RSocket.

## 1. RSocket là gì?

RSocket là một giao thức ứng dụng dành cho trao đổi message giữa hai đầu kết nối. Giao thức này được thiết kế cho giao tiếp bất đồng bộ, hai chiều và hỗ trợ luồng dữ liệu phản ứng. Một kết nối RSocket có thể mang nhiều stream độc lập cùng lúc, cho phép hai phía gửi request và response mà không phải mở một kết nối riêng cho từng thao tác.

Trong Spring Framework, RSocket tích hợp với hệ sinh thái Reactive Streams. Phía gửi dùng `RSocketRequester` để tạo request; phía nhận dùng các phương thức `@MessageMapping` để xử lý route và trả về `Mono` hoặc `Flux`.

RSocket không chỉ là cách gửi message qua WebSocket. Nó định nghĩa giao thức, frame, mô hình tương tác, metadata, flow control và quản lý stream. TCP và WebSocket là các transport phổ biến có thể mang RSocket frame.

Các đặc điểm chính:

- **Hai chiều (bidirectional):** cả client và server đều có thể khởi tạo request khi ứng dụng cho phép.
- **Multiplexing:** nhiều stream có thể cùng chạy trên một connection.
- **Reactive Streams:** hỗ trợ demand, backpressure và cancellation cho các luồng dữ liệu.
- **Metadata:** route và thông tin phụ trợ có thể được gửi tách khỏi data payload.
- **Nhiều mô hình tương tác:** từ một request/response đến luồng dữ liệu hai chiều.
- **Độc lập transport:** giao thức có thể chạy trên TCP hoặc WebSocket, cùng các transport khác được triển khai.

RSocket hữu ích khi hệ thống cần streaming, giao tiếp hai chiều, backpressure hoặc một API thống nhất cho nhiều kiểu tương tác. Với thao tác CRUD đơn giản, HTTP/REST vẫn có thể là lựa chọn phù hợp và dễ triển khai hơn.

## 2. RSocket trong Spring Messaging

Spring Framework cung cấp các abstraction để kết nối ứng dụng với RSocket:

| Thành phần | Vai trò |
|---|---|
| `RSocketRequester` | Phía gửi request, tạo route, data và nhận kết quả dạng reactive |
| `@MessageMapping` | Ánh xạ route đến phương thức xử lý ở phía responder |
| `@ConnectMapping` | Xử lý frame thiết lập kết nối, thường dùng để nhận metadata hoặc payload lúc kết nối |
| `RSocketMessageHandler` | Phân giải annotation và điều phối message đến phương thức phù hợp |
| `RSocketStrategies` | Cấu hình encoder, decoder và các thành phần chuyển đổi data/metadata |
| `Mono<T>` | Biểu diễn tối đa một kết quả bất đồng bộ |
| `Flux<T>` | Biểu diễn một chuỗi kết quả bất đồng bộ, có thể rỗng hoặc không giới hạn |

`RSocketRequester` không phải HTTP client. Nó tạo các RSocket request theo interaction model và xử lý phản hồi qua Reactive Streams.

Phía responder có thể khai báo controller Spring với `@MessageMapping`. Route trong annotation được dùng để chọn phương thức xử lý. Ví dụ, route `quotes.current` có thể ánh xạ đến phương thức lấy báo giá hiện tại.

Spring hỗ trợ DTO, `Publisher`, `Mono` và `Flux`. Encoder/decoder chuyển đổi payload giữa object Java và dạng dữ liệu truyền trên wire.

## 3. Bốn mô hình tương tác của RSocket

RSocket có bốn interaction model chính. Việc chọn đúng mô hình giúp API thể hiện rõ số lượng request, số lượng response và hướng của luồng dữ liệu.

### 3.1. Request-response

Một request tạo ra tối đa một response.

```text
Requester  ---- request ---->  Responder
Requester  <--- response ----  Responder
```

Đặc điểm:

- Request là một payload.
- Response là một payload.
- Phù hợp với truy vấn hoặc lệnh cần một kết quả duy nhất.
- Phía requester thường dùng `retrieveMono(Response.class)`.
- Phía responder có thể trả về object hoặc `Mono<T>`.

### 3.2. Fire-and-forget

Requester gửi một payload và không chờ application response.

```text
Requester  ---- request ---->  Responder
                (no response)
```

Đặc điểm:

- Phù hợp với sự kiện một chiều hoặc tác vụ không cần kết quả trả về ngay.
- Phía requester thường dùng `send()`.
- Phía responder có thể xử lý bằng phương thức không trả dữ liệu hoặc trả `Mono<Void>`.
- Không có response payload để xác nhận nghiệp vụ đã hoàn tất.

Không dùng fire-and-forget nếu caller cần biết lệnh đã được xử lý thành công, cần nhận ID kết quả hoặc cần retry dựa trên phản hồi. Việc publisher phía client hoàn tất gửi không đồng nghĩa nghiệp vụ phía server đã hoàn tất và được lưu bền vững.

### 3.3. Request-stream

Một request duy nhất khởi tạo một stream gồm nhiều response.

```text
Requester  ---- request ---->  Responder
Requester  <--- response 1 --  Responder
Requester  <--- response 2 --  Responder
Requester  <--- response 3 --  Responder
                    ...
```

Đặc điểm:

- Request ban đầu là một payload.
- Response là một chuỗi phần tử.
- Phù hợp với dữ liệu cập nhật liên tục, giá thị trường, trạng thái tác vụ hoặc kết quả tìm kiếm dạng stream.
- Phía requester thường dùng `retrieveFlux(Response.class)`.
- Phía responder thường trả về `Flux<T>`.

### 3.4. Request-channel

Cả request và response đều là stream. Requester gửi nhiều phần tử và responder có thể trả về nhiều phần tử tương ứng hoặc được xử lý độc lập.

```text
Requester  ---- request 1 ---> Responder
Requester  ---- request 2 ---> Responder
Requester  ---- request 3 ---> Responder
Requester  <--- response 1 -- Responder
Requester  <--- response 2 -- Responder
Requester  <--- response 3 -- Responder
```

Đặc điểm:

- Requester cung cấp một publisher.
- Responder nhận một publisher và trả về publisher khác.
- Phù hợp với xử lý dữ liệu theo luồng hai chiều.
- Phía requester truyền `Flux` hoặc `Publisher` vào `data(...)` rồi gọi `retrieveFlux(...)`.
- Phía responder nhận `Publisher<T>` hoặc `Flux<T>` và trả về `Flux<R>`.

### Bảng so sánh

| Mô hình | Request | Response | Spring requester |
|---|---|---|---|
| Request-response | Một payload | Tối đa một payload | `retrieveMono(T.class)` |
| Fire-and-forget | Một payload | Không có response payload | `send()` |
| Request-stream | Một payload | Nhiều payload | `retrieveFlux(T.class)` |
| Request-channel | Một stream | Một stream | `data(Publisher).retrieveFlux(T.class)` |

Ngoài bốn interaction model, giao thức còn có các frame điều khiển như SETUP, KEEPALIVE, LEASE, RESUME và METADATA_PUSH. Chúng hỗ trợ thiết lập, duy trì hoặc quản lý connection; không nên nhầm chúng với bốn kiểu request nghiệp vụ ở trên.

## 4. Data, metadata và route

Một RSocket payload có thể chứa hai phần độc lập:

- **Data:** nội dung chính, thường là DTO hoặc dữ liệu nhị phân.
- **Metadata:** thông tin mô tả hoặc điều khiển cách xử lý data.

Metadata có thể chứa route, thông tin xác thực, tracing hoặc dữ liệu phụ trợ khác. Metadata không thay thế payload nghiệp vụ.

Trong Spring, requester chọn route bằng `route(...)`:

```java
Mono<Quote> result = requester
        .route("quotes.current")
        .data(new QuoteRequest("ACME"))
        .retrieveMono(Quote.class);
```

Ở đây:

- `quotes.current` là route metadata để responder chọn handler.
- `QuoteRequest` là data payload.
- `retrieveMono(Quote.class)` yêu cầu một response được giải mã thành `Quote`.

Route không phải URL path của HTTP và cũng không phải STOMP destination. Route là metadata định tuyến trong RSocket. Tên route phải khớp với mapping ở phía responder.

Ví dụ responder:

```java
@Controller
public class QuoteController {

    @MessageMapping("quotes.current")
    public Mono<Quote> current(QuoteRequest request) {
        return quoteService.findCurrent(request.symbol());
    }
}
```

Nếu route không khớp với mapping nào, request có thể bị từ chối hoặc trả lỗi tùy cấu hình và cách ứng dụng xử lý lỗi.

### Metadata tùy chỉnh

Requester có thể đính kèm metadata ngoài route:

```java
Mono<Quote> result = requester
        .route("quotes.current")
        .metadata("trace-42", MimeType.valueOf("text/plain"))
        .data(new QuoteRequest("ACME"))
        .retrieveMono(Quote.class);
```

Phía responder có thể đọc metadata qua các cơ chế hỗ trợ của Spring. Metadata MIME type cho biết cách diễn giải giá trị. Nếu cần nhiều loại metadata trong cùng payload, RSocket hỗ trợ composite metadata; từng metadata entry cần có MIME type và cách mã hóa tương ứng.

Không đặt thông tin nhạy cảm vào metadata chỉ vì nó không nằm trong data. Metadata vẫn được truyền qua mạng và cần được bảo vệ bằng transport security, xác thực và chính sách log phù hợp.

## 5. Xây dựng responder với @MessageMapping

Một controller có thể cung cấp nhiều route tương ứng với các interaction model khác nhau.

Ví dụ mô hình báo giá:

```java
import java.math.BigDecimal;

import org.reactivestreams.Publisher;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class QuoteController {

    private final QuoteService quoteService;

    public QuoteController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    // Request-response: một request, một kết quả.
    @MessageMapping("quotes.current")
    public Mono<Quote> current(QuoteRequest request) {
        return quoteService.findCurrent(request.symbol());
    }

    // Request-stream: một request, nhiều kết quả.
    @MessageMapping("quotes.watch")
    public Flux<Quote> watch(QuoteRequest request) {
        return quoteService.watch(request.symbol());
    }

    // Fire-and-forget: không trả response payload.
    @MessageMapping("quotes.audit")
    public Mono<Void> audit(AuditEvent event) {
        return quoteService.recordAudit(event);
    }

    // Request-channel: nhận một stream và trả về một stream.
    @MessageMapping("quotes.exchange")
    public Flux<QuoteAck> exchange(
            Publisher<QuoteUpdate> updates) {

        return Flux.from(updates)
                .concatMap(quoteService::applyUpdate);
    }
}

record QuoteRequest(String symbol) {}

record Quote(String symbol, BigDecimal price) {}

record AuditEvent(String action, String reference) {}

record QuoteUpdate(String symbol, BigDecimal price) {}

record QuoteAck(String symbol, boolean accepted) {}
```

Cách đọc ví dụ:

1. `quotes.current` trả về `Mono<Quote>`, phù hợp request-response.
2. `quotes.watch` trả về `Flux<Quote>`, phù hợp request-stream.
3. `quotes.audit` trả về `Mono<Void>`, không phát response payload cho requester.
4. `quotes.exchange` nhận publisher của các cập nhật và trả về publisher của acknowledgment, phù hợp request-channel.
5. `concatMap` xử lý từng update theo thứ tự và đợi publisher của update trước hoàn tất trước khi chuyển sang update tiếp theo.

Các method trên minh họa chữ ký và cách ánh xạ route. Để chạy thực tế, ứng dụng cần cấu hình RSocket server transport, `RSocketMessageHandler`, `RSocketStrategies` và các service tương ứng. Những cấu hình này phụ thuộc cách ứng dụng tự khởi tạo server hoặc dùng Spring Boot.

## 6. Gửi request bằng RSocketRequester

Requester cung cấp API fluent để chọn route, gửi data và khai báo kiểu response mong muốn.

### Request-response

```java
Mono<Quote> current = requester
        .route("quotes.current")
        .data(new QuoteRequest("ACME"))
        .retrieveMono(Quote.class);
```

`retrieveMono` trả về `Mono<Quote>`. Khi subscribe, request được thực hiện và response được giải mã thành kiểu đã khai báo.

### Request-stream

```java
Flux<Quote> updates = requester
        .route("quotes.watch")
        .data(new QuoteRequest("ACME"))
        .retrieveFlux(Quote.class);
```

`retrieveFlux` trả về một stream. Consumer có thể xử lý từng phần tử thay vì đợi toàn bộ dữ liệu được gom thành một collection.

### Fire-and-forget

```java
Mono<Void> sent = requester
        .route("quotes.audit")
        .data(new AuditEvent("VIEW", "ACME"))
        .send();
```

`send()` không trả về payload nghiệp vụ. Đây là lựa chọn cho lệnh một chiều khi caller không cần response. Nếu cần xác nhận đã ghi nhận hoặc xử lý, hãy dùng request-response và trả về acknowledgment rõ ràng.

### Request-channel

```java
Flux<QuoteUpdate> updates = Flux.just(
        new QuoteUpdate("ACME", new BigDecimal("101.25")),
        new QuoteUpdate("ACME", new BigDecimal("101.50")),
        new QuoteUpdate("ACME", new BigDecimal("101.75"))
);

Flux<QuoteAck> acknowledgements = requester
        .route("quotes.exchange")
        .data(updates)
        .retrieveFlux(QuoteAck.class);
```

Requester truyền một publisher làm request stream và nhận response stream. Consumer cần subscribe vào `acknowledgements` để bắt đầu tiêu thụ kết quả.

Reactive chain là lazy: tạo `Mono` hoặc `Flux` thường chưa thực hiện I/O cho đến khi có subscription. Cần kết nối chain với runtime reactive, ví dụ WebFlux handler hoặc subscriber. Không gọi `block()` tùy tiện trong event loop hoặc luồng xử lý reactive.

## 7. Thiết lập kết nối và transport

RSocket protocol độc lập với transport. Các transport thường gặp:

- **TCP:** phù hợp giao tiếp service-to-service trong mạng nội bộ hoặc môi trường cần kết nối trực tiếp.
- **WebSocket:** phù hợp khi cần kết nối RSocket từ trình duyệt hoặc đi qua hạ tầng đã hỗ trợ WebSocket.

Ví dụ tạo requester kết nối TCP:

```java
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

Mono<RSocketRequester> requesterMono = RSocketRequester.builder()
        .connectTcp("localhost", 7000);
```

`connectTcp` trả về `Mono<RSocketRequester>` vì việc thiết lập kết nối là bất đồng bộ. Có thể kết hợp với các thao tác tiếp theo bằng `flatMap` hoặc quản lý requester trong lifecycle của ứng dụng.

Ví dụ sử dụng requester sau khi kết nối:

```java
Mono<Quote> quote = requesterMono.flatMap(requester ->
        requester.route("quotes.current")
                .data(new QuoteRequest("ACME"))
                .retrieveMono(Quote.class)
);
```

Trong một ứng dụng lâu dài, nên quản lý một requester/connection phù hợp với lifecycle thay vì tạo kết nối mới cho từng message. Khi ứng dụng đóng, cần dispose tài nguyên kết nối theo cơ chế mà client quản lý cung cấp.

### SETUP và connection lifecycle

Khi kết nối được tạo, hai phía trao đổi SETUP frame để thiết lập session RSocket và thương lượng thông tin cần thiết, bao gồm MIME type cho data và metadata. Sau đó, connection có thể mang nhiều request stream độc lập.

Các frame điều khiển khác có vai trò riêng:

- **KEEPALIVE:** kiểm tra và duy trì connection.
- **LEASE:** giới hạn hoặc cấp quyền khởi tạo request theo cơ chế lease nếu được sử dụng.
- **RESUME:** hỗ trợ tiếp tục session trong điều kiện và cấu hình tương thích.
- **METADATA_PUSH:** gửi metadata cấp connection.
- **ERROR:** báo lỗi ở phạm vi stream hoặc connection tùy loại lỗi.

Không phải ứng dụng nào cũng cần bật lease hoặc resume. Hãy chọn tính năng theo yêu cầu về quản lý tải, khả năng phục hồi và hạ tầng triển khai.

## 8. Reactive Streams, backpressure và cancellation

Backpressure là khả năng consumer kiểm soát lượng dữ liệu mà producer được phép phát. Đây là điểm quan trọng khi server cung cấp stream lớn hoặc dữ liệu cập nhật liên tục.

Trong Reactive Streams, subscriber phát tín hiệu demand thông qua `request(n)`. Với RSocket request-stream và request-channel, demand được truyền qua cơ chế flow control của protocol. Producer không nên phát dữ liệu vô hạn nhanh hơn khả năng tiêu thụ của client.

Ví dụ consumer giới hạn số phần tử:

```java
Flux<Quote> firstTen = requester
        .route("quotes.watch")
        .data(new QuoteRequest("ACME"))
        .retrieveFlux(Quote.class)
        .take(10);
```

`take(10)` hoàn tất sau khi nhận đủ mười phần tử và hủy subscription upstream. Điều này giúp ngừng tiêu thụ stream khi không còn cần dữ liệu.

### Backpressure không phải là rate limit nghiệp vụ

Backpressure điều tiết nhu cầu của subscriber và khả năng phát dữ liệu trong stream. Nó không thay thế:

- Rate limit theo user hoặc tenant.
- Giới hạn kích thước payload.
- Giới hạn số connection hoặc số stream đồng thời.
- Quota API hoặc chính sách chống lạm dụng.
- Kiểm soát tài nguyên database và downstream service.

Một client có thể tiêu thụ chậm nhưng vẫn tạo quá nhiều stream. Ứng dụng cần quản lý cả flow control lẫn giới hạn tài nguyên ở tầng hệ thống.

### Cancellation và tài nguyên

Khi consumer hủy subscription, RSocket có thể gửi CANCEL cho stream tương ứng. Responder nên giải phóng tài nguyên liên quan, dừng truy vấn hoặc hủy công việc có thể hủy.

Tuy nhiên, cancellation không tự động rollback các side effect đã hoàn tất. Nếu một request-channel đã ghi một phần dữ liệu vào database trước khi client hủy, ứng dụng phải có transaction hoặc quy tắc nghiệp vụ riêng để bảo đảm tính nhất quán.

### Xử lý stream hữu hạn và vô hạn

- Với stream hữu hạn, hãy phát completion khi dữ liệu kết thúc.
- Với stream vô hạn, cần chiến lược cancellation, timeout, heartbeat hoặc giới hạn thời gian phù hợp.
- Dùng operator như `take`, `timeout`, `onErrorResume` và `limitRate` theo nhu cầu.
- Tránh gom toàn bộ stream vô hạn vào bộ nhớ bằng `collectList`.

## 9. Lỗi và timeout

RSocket có thể báo lỗi ở phạm vi stream hoặc connection. Trong Spring, lỗi từ phương thức responder có thể được chuyển thành tín hiệu lỗi của RSocket stream và đến requester dưới dạng reactive error.

Ví dụ xử lý lỗi ở phía requester:

```java
Mono<Quote> quote = requester
        .route("quotes.current")
        .data(new QuoteRequest("UNKNOWN"))
        .retrieveMono(Quote.class)
        .timeout(Duration.ofSeconds(3))
        .onErrorResume(error -> {
            // Ghi log có kiểm soát hoặc chuyển thành fallback.
            return Mono.empty();
        });
```

Ví dụ này minh họa timeout và fallback. Trong ứng dụng thực tế, không nên biến mọi lỗi thành kết quả rỗng nếu caller cần phân biệt not found, unauthorized, timeout và lỗi hệ thống.

Một số nguyên tắc:

- Dùng timeout cho request có giới hạn thời gian nghiệp vụ.
- Phân biệt lỗi validation, lỗi quyền truy cập, lỗi tạm thời và lỗi không thể retry.
- Chỉ retry khi thao tác an toàn để lặp lại hoặc có idempotency key.
- Không retry vô hạn; đặt số lần thử và backoff.
- Ghi log stream/route và correlation ID cần thiết, tránh ghi payload nhạy cảm.
- Xử lý cancellation riêng với lỗi; client hủy stream không nhất thiết là lỗi hệ thống.
- Nếu cần xác nhận kết quả một lệnh ghi, hãy thiết kế response có trạng thái rõ ràng thay vì dùng fire-and-forget.

## 10. Serialization và RSocketStrategies

RSocket truyền payload dưới dạng data và metadata. Object Java cần được encoder chuyển thành dạng wire; phía nhận dùng decoder để tạo lại object.

`RSocketStrategies` là nơi cấu hình các thành phần như:

- Encoder cho payload đầu ra.
- Decoder cho payload đầu vào.
- MIME type mặc định hoặc các MIME type được hỗ trợ.
- Metadata extractor và các thành phần xử lý metadata phù hợp.

Ứng dụng thường dùng JSON cho DTO, nhưng có thể chọn CBOR hoặc định dạng nhị phân khác nếu cả hai phía thống nhất. Định dạng và MIME type phải tương thích giữa requester và responder.

Khi cấu hình codec, cần lưu ý:

- DTO phải có cấu trúc mà encoder/decoder hiểu được.
- Không giả định mọi class đều tự serialize được chỉ vì đã thêm dependency.
- Data MIME type và metadata MIME type là hai khái niệm riêng.
- Với composite metadata, từng metadata entry cần được mã hóa và nhận diện theo MIME type.
- Payload lớn cần có giới hạn và chiến lược streaming phù hợp.

Không nhầm việc serialize thành công với validation thành công. Sau khi decoder tạo object, ứng dụng vẫn phải kiểm tra dữ liệu và quyền nghiệp vụ.

## 11. @ConnectMapping và xử lý lúc thiết lập kết nối

`@ConnectMapping` cho phép responder xử lý thông tin được gửi trong quá trình thiết lập RSocket connection. Nó hữu ích khi server cần nhận metadata ban đầu như thông tin client, phiên bản giao thức hoặc dữ liệu khởi tạo phiên.

Khác với `@MessageMapping`, vốn xử lý request theo route, `@ConnectMapping` gắn với lifecycle của connection. Có thể dùng nó để:

- Ghi nhận client/session mới.
- Kiểm tra thông tin khởi tạo ở tầng ứng dụng.
- Gắn metadata phục vụ tracing hoặc quản lý session.
- Từ chối kết nối nếu thông tin bắt buộc không hợp lệ theo chính sách ứng dụng.

Không đưa bí mật hoặc dữ liệu xác thực chưa được bảo vệ vào setup metadata. Nếu setup metadata mang thông tin nhận dạng, phải xác minh bằng cơ chế authentication đáng tin cậy và dùng transport security phù hợp.

Đối với xác thực và phân quyền payload, Spring Security có hỗ trợ riêng cho RSocket. Cấu hình này khác với bảo mật STOMP/WebSocket message channel. Không áp dụng máy móc matcher `/app/**`, `/topic/**` của STOMP cho RSocket route.

## 12. Bảo mật RSocket

Một connection RSocket lâu dài có thể mang nhiều request stream, vì vậy bảo mật cần được xem xét ở cả connection setup lẫn từng request.

Các nguyên tắc:

- **Bảo vệ transport:** dùng TLS khi dữ liệu đi qua mạng không đáng tin cậy; WebSocket cũng cần cấu hình bảo mật tương ứng.
- **Xác thực danh tính:** không tin username hoặc role chỉ vì client gửi chúng trong payload/metadata.
- **Phân quyền theo route:** giới hạn route mà từng user/role được phép gọi.
- **Kiểm tra quyền nghiệp vụ:** xác minh ownership, tenant và quyền trên từng tài nguyên trong service.
- **Giới hạn payload:** giới hạn kích thước data và metadata, số stream và tốc độ request.
- **Quản lý connection:** xử lý timeout, disconnect và cleanup tài nguyên.
- **Bảo vệ log:** không ghi token, credential hoặc payload nhạy cảm.

Spring Security có tích hợp bảo mật cho RSocket, với cấu hình như `@EnableRSocketSecurity`, authentication metadata và payload authorization. Cơ chế cụ thể phụ thuộc phiên bản Spring Security và cách ứng dụng truyền credential trong setup hoặc per-request metadata.

Một route có tên khó đoán không phải là cơ chế phân quyền. Server phải kiểm tra authentication và authority trước khi xử lý request.

## 13. So sánh RSocket với STOMP và HTTP

| Tiêu chí | RSocket | STOMP trên WebSocket | HTTP/REST |
|---|---|---|---|
| Mô hình chính | Request-response, FNF, stream, channel | SEND/SUBSCRIBE qua destination | Request/response |
| Streaming | Có request-stream và request-channel | Có thể nhận nhiều message qua subscription | Có thể dùng streaming tùy phiên bản/transport |
| Backpressure | Flow control tích hợp với Reactive Streams | Không có cùng mô hình request-N flow control của RSocket | Phụ thuộc API/transport |
| Định tuyến | Route metadata | Destination và broker prefix | URL, method, query |
| Multiplexing | Nhiều stream trên một connection | Một WebSocket session với nhiều subscription | Thường request độc lập; HTTP/2 có multiplexing |
| Hai chiều | Hỗ trợ giao tiếp hai phía | Client/server trao đổi qua broker | Mô hình request/response |
| Phù hợp | Reactive service-to-service, streaming, giao tiếp hai chiều | Realtime pub/sub và tích hợp message broker | API web, CRUD, tích hợp phổ thông |

Cả RSocket và STOMP đều có thể chạy trên WebSocket, nhưng chúng là hai protocol khác nhau. Một endpoint STOMP không tự động trở thành endpoint RSocket chỉ vì cả hai dùng WebSocket làm transport.

Chọn RSocket khi cần interaction model đa dạng, stream và backpressure. Chọn STOMP khi ứng dụng cần mô hình destination/subscription và message broker quen thuộc. Chọn HTTP/REST cho API request-response phổ thông, dễ tích hợp với hệ sinh thái web.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Route không tìm thấy handler | Route trong requester không khớp `@MessageMapping` | Kiểm tra route metadata và mapping |
| Requester chờ response mãi | Dùng nhầm interaction model hoặc responder không phát completion | Kiểm tra `retrieveMono`/`retrieveFlux` và kiểu trả về |
| Dùng `send()` nhưng mong nhận kết quả | Fire-and-forget không có response payload | Dùng request-response với acknowledgment |
| Stream tiêu thụ quá nhiều bộ nhớ | Gom stream không giới hạn hoặc thiếu backpressure | Xử lý từng phần tử, giới hạn demand và tránh collect vô hạn |
| JSON không chuyển thành DTO | Thiếu codec hoặc MIME type không tương thích | Kiểm tra `RSocketStrategies`, encoder/decoder và content type |
| Request-channel chỉ nhận một phần dữ liệu | Publisher bị complete/error hoặc bị cancel | Kiểm tra lifecycle, demand, timeout và cancellation |
| Tạo quá nhiều connection | Mở connection cho từng request | Tái sử dụng requester/connection theo lifecycle |
| Dùng STOMP destination trong RSocket | Nhầm route metadata với destination broker | Dùng route RSocket và cấu hình responder tương ứng |
| User gọi được route trái phép | Chỉ kiểm tra route tồn tại, chưa authorization | Thêm authentication, payload authorization và kiểm tra nghiệp vụ |

## 15. Bài tập tự kiểm tra

Một dịch vụ giá cổ phiếu có các yêu cầu:

1. Lấy giá hiện tại của một mã và nhận một kết quả.
2. Theo dõi giá liên tục cho đến khi client hủy.
3. Gửi một sự kiện audit mà không cần response.
4. Gửi nhiều cập nhật giá lên server và nhận acknowledgment cho từng cập nhật.
5. Không cho client chưa xác thực gọi route cập nhật.

Hãy chọn interaction model và API phù hợp:

| Yêu cầu | Interaction model | Spring requester API |
|---|---|---|
| Lấy giá hiện tại | Request-response | `retrieveMono(Quote.class)` |
| Theo dõi giá | Request-stream | `retrieveFlux(Quote.class)` |
| Gửi audit một chiều | Fire-and-forget | `send()` |
| Gửi và nhận stream cập nhật | Request-channel | `data(updates).retrieveFlux(QuoteAck.class)` |
| Chặn client chưa xác thực | Authentication/authorization | Spring Security RSocket |

Câu hỏi bổ sung:

1. Vì sao `Mono` phù hợp cho request-response?
2. Vì sao `Flux` phù hợp cho request-stream?
3. Khi client gọi `take(10)` trên một stream, điều gì xảy ra sau phần tử thứ mười?
4. Vì sao hoàn tất `send()` không chứng minh server đã hoàn tất nghiệp vụ?
5. Route metadata có thay thế được authentication không?

Đáp án:

1. `Mono` biểu diễn tối đa một kết quả hoặc không có kết quả.
2. `Flux` biểu diễn nhiều phần tử theo thời gian.
3. Consumer hoàn tất và hủy subscription upstream, cho phép responder dừng công việc liên quan nếu có thể.
4. Fire-and-forget không có response payload xác nhận xử lý nghiệp vụ.
5. Không. Route chỉ định tuyến request; danh tính và quyền phải được xác thực riêng.

## 16. Ghi nhớ

- RSocket là giao thức messaging hai chiều, reactive và hỗ trợ multiplexing.
- Bốn interaction model là request-response, fire-and-forget, request-stream và request-channel.
- Data chứa payload; metadata chứa route và thông tin phụ trợ.
- `RSocketRequester` tạo request; `@MessageMapping` xử lý route ở responder.
- `Mono` biểu diễn tối đa một kết quả; `Flux` biểu diễn stream nhiều phần tử.
- Backpressure giúp điều tiết demand; cancellation giúp giải phóng stream khi không còn nhu cầu.
- TCP và WebSocket là transport; chúng không phải interaction model.
- Fire-and-forget không cung cấp response xác nhận nghiệp vụ.
- Cấu hình codec, MIME type, authentication và authorization phải tương thích giữa hai phía.

## Tài liệu tham khảo

- Spring Framework Reference — [RSocket](https://docs.spring.io/spring/reference/rsocket.html)
- Spring Framework Reference — [RSocket Messaging](https://docs.spring.io/spring/reference/rsocket.html#rsocket-messaging)
- Spring Framework Javadoc — [RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- Spring Framework Javadoc — [RSocketMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketMessageHandler.html)
- RSocket Protocol — [Protocol Specification](https://rsocket.io/about/protocol/)
- Reactive Streams — [Specification](https://www.reactive-streams.org/)
