# Log theo vòng đời luồng và giới hạn dữ liệu payload được ghi

RSocket tạo ra các interaction bất đồng bộ và có thể kéo dài: request-response, fire-and-forget, request-stream và request-channel. Để vận hành hệ thống, log cần cho biết interaction bắt đầu khi nào, kết thúc ra sao, có lỗi hay bị client hủy, mất bao lâu và đã xử lý bao nhiêu phần tử. Đồng thời, log phải giới hạn dữ liệu payload được ghi để tránh làm lộ thông tin nhạy cảm, tăng chi phí lưu trữ hoặc làm chậm luồng realtime.

Một nguyên tắc hữu ích là **ghi nhận vòng đời và đặc điểm của payload, không mặc định ghi nội dung payload**. Route, interaction type, correlation ID, thời lượng, số phần tử, kích thước data/metadata và kết quả kết thúc thường đủ để chẩn đoán. Nếu nghiệp vụ thật sự cần ghi một phần nội dung, chỉ ghi các trường đã được cho phép, đã che dữ liệu nhạy cảm và có giới hạn kích thước rõ ràng.

Bài học trình bày cách log ở tầng Spring RSocket và Reactor, truyền correlation context qua pipeline, phân biệt complete/error/cancel, giới hạn nội dung log, xử lý MDC trong môi trường reactive, tránh log quá nhiều phần tử và kiểm thử để bảo đảm token hoặc payload riêng tư không lọt vào log.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Xác định các sự kiện vòng đời cần log cho bốn interaction model của RSocket.
- Dùng Reactor để ghi nhận subscribe, next, error, complete và cancel.
- Gắn correlation ID và route vào structured log.
- Phân biệt log ứng dụng, metrics và distributed tracing.
- Ghi kích thước payload mà không đọc hoặc làm thay đổi buffer.
- Thiết kế allowlist, redaction và giới hạn kích thước trường log.
- Tránh ghi bearer token, credential, dữ liệu cá nhân hoặc toàn bộ binary payload.
- Tránh tạo quá nhiều log trong request-stream và request-channel.
- Hiểu giới hạn của MDC khi Reactor chuyển thread.
- Kiểm thử lifecycle log và xác minh dữ liệu nhạy cảm không xuất hiện.

## 1. Vì sao cần log theo vòng đời interaction?

Một request-response thường kết thúc nhanh, nhưng request-stream hoặc request-channel có thể hoạt động nhiều phút hoặc nhiều giờ. Một log chỉ ghi lúc handler được gọi sẽ không cho biết stream có kết thúc bình thường, phát lỗi hay bị client hủy. Ngược lại, log từng payload có thể tạo ra hàng triệu dòng và làm lộ dữ liệu.

Một bản ghi lifecycle nên trả lời các câu hỏi:

- Interaction nào đang chạy? Route và interaction type là gì?
- Request đến từ client hoặc connection nào?
- Interaction bắt đầu và kết thúc lúc nào?
- Kết thúc do complete, error hay cancel?
- Thời lượng và số phần tử đã xử lý là bao nhiêu?
- Kích thước data và metadata có bất thường không?
- Nếu lỗi, lỗi thuộc loại nào và có correlation ID nào để truy vết?

~~~mermaid
sequenceDiagram
    participant C as RSocket client
    participant H as Spring handler
    participant P as Reactor publisher
    participant L as Structured logger
    C->>H: Request + route + metadata
    H->>P: Tạo publisher
    P->>L: interaction.started
    P-->>L: item count / payload size (sampled)
    alt Hoàn tất
        P->>L: interaction.terminated, complete
    else Có lỗi
        P->>L: interaction.error
        P->>L: interaction.terminated, error
    else Client hủy
        P->>L: interaction.terminated, cancel
    end
~~~

Log lifecycle không thay thế protocol metrics hoặc tracing. Nó bổ sung bối cảnh để người vận hành hiểu một interaction cụ thể đã đi qua hệ thống như thế nào.

## 2. Các điểm cần quan sát trong bốn interaction model

Mỗi interaction có vòng đời và số lượng phần tử khác nhau:

| Interaction | Sự kiện nên ghi | Điều cần chú ý |
|---|---|---|
| Request-response | start, complete/error/cancel, duration | Thường có tối đa một response payload |
| Fire-and-forget | start, handler completion/error | Không có response payload để requester nhận |
| Request-stream | start, count/sample, complete/error/cancel, duration | Có thể kéo dài và phát rất nhiều phần tử |
| Request-channel | start, inbound count, outbound count, complete/error/cancel | Hai phía có thể gửi dữ liệu đồng thời |

Đừng suy ra rằng một request-stream đã thành công chỉ vì handler được gọi. Stream chỉ hoàn tất khi publisher complete; client có thể hủy trước đó. Tương tự, một request-channel có thể nhận một số phần tử rồi bị hủy giữa chừng.

### 2.1. Phân biệt complete, error và cancel

Reactor cung cấp các tín hiệu kết thúc:

| SignalType | Ý nghĩa | Ví dụ log |
|---|---|---|
| ON_COMPLETE | Publisher hoàn tất bình thường | termination=complete |
| ON_ERROR | Publisher kết thúc do lỗi | termination=error |
| CANCEL | Subscriber hủy subscription | termination=cancel |

Cancellation không nhất thiết là lỗi. Client có thể rời màn hình, đổi route, hết nhu cầu dữ liệu hoặc đóng stream có chủ đích. Ghi cancel như một trạng thái kết thúc riêng để dashboard không hiểu nhầm mọi cancel là lỗi server.

Một connection RSocket có thể multiplex nhiều interaction. Cancel một stream không đồng nghĩa toàn bộ connection bị đóng. Log theo interaction ID/route để tránh gộp các sự kiện của nhiều stream thành một vòng đời duy nhất.

## 3. Structured logging cho RSocket

Log có cấu trúc lưu dữ liệu theo các field ổn định thay vì nối mọi thông tin vào một chuỗi văn bản. Ví dụ một bản ghi:

~~~json
{
  "timestamp": "2026-11-22T12:30:00.125Z",
  "level": "INFO",
  "event": "rsocket.interaction.terminated",
  "interactionType": "request-stream",
  "route": "telemetry.stream",
  "correlationId": "corr-8f31",
  "connectionId": "conn-42",
  "termination": "cancel",
  "durationMs": 18420,
  "itemsOut": 127,
  "dataBytesIn": 48,
  "metadataBytesIn": 24
}
~~~

Field nên dùng tên nhất quán giữa các service. Một bộ field cơ bản:

| Field | Ý nghĩa |
|---|---|
| timestamp | Thời điểm theo UTC |
| event | Tên sự kiện lifecycle |
| service | Tên service phát log |
| interactionType | request-response, fire-and-forget, request-stream hoặc request-channel |
| route | Route RSocket đã được chuẩn hóa |
| correlationId | ID nối request với các log liên quan |
| connectionId | ID nội bộ của connection nếu có |
| termination | complete, error hoặc cancel |
| durationMs | Thời lượng interaction |
| itemsIn / itemsOut | Số phần tử nhận và phát |
| dataBytesIn / metadataBytesIn | Kích thước phần data và metadata |
| errorType | Tên loại exception, không phải toàn bộ payload |

Không cần mọi log đều chứa mọi field. Chọn field phù hợp với sự kiện và tránh tạo một schema log quá lớn, khó truy vấn.

### 3.1. Dùng SLF4J parameterized logging

Với logger thông thường:

~~~java
log.info(
        "rsocket.interaction.started route={} type={} correlationId={}",
        route,
        interactionType,
        correlationId);
~~~

Không nối payload vào log bằng string concatenation. Parameterized logging giúp tránh tạo chuỗi không cần thiết khi level bị tắt, nhưng bản thân nó không tự che dữ liệu nhạy cảm.

Nếu hệ thống dùng SLF4J 2 fluent API hoặc JSON encoder của Logback, có thể thêm field có cấu trúc:

~~~java
log.atInfo()
        .addKeyValue("event", "rsocket.interaction.started")
        .addKeyValue("route", route)
        .addKeyValue("interactionType", interactionType)
        .addKeyValue("correlationId", correlationId)
        .log("RSocket interaction started");
~~~

Chọn một cách biểu diễn nhất quán. Không dùng correlation ID, user ID hoặc device ID làm metric label có cardinality cao; chúng phù hợp hơn với log hoặc trace attributes có kiểm soát.

## 4. Log lifecycle bằng Reactor

Các operator chính:

- doOnSubscribe: ghi nhận subscription bắt đầu.
- doOnNext: đếm phần tử hoặc ghi log mẫu.
- doOnError: ghi loại lỗi và stack trace theo chính sách.
- doFinally: ghi kết thúc do complete, error hoặc cancel.
- doOnCancel: chạy riêng khi subscriber hủy.

Với request-stream:

~~~java
public Flux<TelemetryEvent> watch(
        DeviceQuery query,
        String correlationId) {

    return Flux.defer(() -> {
        long startedAt = System.nanoTime();
        LongAdder itemsOut = new LongAdder();

        log.info(
                "event=rsocket.interaction.started type=request-stream route=telemetry.stream correlationId={}",
                correlationId);

        return Flux.defer(() ->
                        telemetryService.watch(query.deviceId()))
                .doOnNext(item -> itemsOut.increment())
                .doOnError(error ->
                        log.warn(
                                "event=rsocket.interaction.error type=request-stream route=telemetry.stream correlationId={} errorType={}",
                                correlationId,
                                error.getClass().getSimpleName(),
                                error))
                .doFinally(signal -> {
                    long durationMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - startedAt);

                    log.info(
                            "event=rsocket.interaction.terminated type=request-stream route=telemetry.stream correlationId={} termination={} durationMs={} itemsOut={}",
                            correlationId,
                            signal,
                            durationMs,
                            itemsOut.sum());
                });
    });
}
~~~

Flux.defer tạo bộ đếm và thời điểm bắt đầu riêng cho từng subscription. Lớp defer bên trong cũng chuyển lỗi đồng bộ khi tạo nguồn thành tín hiệu onError để terminal logging vẫn chạy. doFinally chạy ở cả ba trường hợp complete, error và cancel. doOnError ghi thêm exception để chẩn đoán; bản ghi terminated vẫn giữ trạng thái kết thúc tổng quát.

Trong service thật, hãy cân nhắc level log: start/terminated có thể ở DEBUG nếu lưu lượng rất lớn; lỗi có thể ở WARN hoặc ERROR tùy khả năng phục hồi. Tránh log cùng một exception nhiều lần ở mọi lớp nếu đã có một điểm chịu trách nhiệm ghi stack trace.

### 4.1. Request-response

~~~java
public Mono<DeviceStatus> status(
        DeviceQuery query,
        String correlationId) {

    return Mono.defer(() -> {
        long startedAt = System.nanoTime();

        log.debug(
                "event=rsocket.interaction.started type=request-response route=devices.status correlationId={}",
                correlationId);

        return Mono.defer(() ->
                        deviceService.status(query.deviceId()))
                .doOnError(error ->
                        log.warn(
                                "event=rsocket.interaction.error type=request-response route=devices.status correlationId={} errorType={}",
                                correlationId,
                                error.getClass().getSimpleName(),
                                error))
                .doFinally(signal -> log.debug(
                        "event=rsocket.interaction.terminated type=request-response route=devices.status correlationId={} termination={} durationMs={}",
                        correlationId,
                        signal,
                        TimeUnit.NANOSECONDS.toMillis(
                                System.nanoTime() - startedAt)));
    });
}
~~~

### 4.2. Fire-and-forget

Fire-and-forget không trả response payload. Handler vẫn có thể log khi xử lý bắt đầu và khi Mono hoàn tất:

~~~java
public Mono<Void> recordEvent(
        ClientEvent event,
        String correlationId) {

    return Mono.defer(() -> {
        long startedAt = System.nanoTime();

        log.debug(
                "event=rsocket.interaction.started type=fire-and-forget route=events.record correlationId={}",
                correlationId);

        return Mono.defer(() -> eventService.record(event))
                .doOnError(error ->
                        log.warn(
                                "event=rsocket.interaction.error type=fire-and-forget route=events.record correlationId={} errorType={}",
                                correlationId,
                                error.getClass().getSimpleName(),
                                error))
                .doFinally(signal -> log.debug(
                        "event=rsocket.interaction.terminated type=fire-and-forget route=events.record correlationId={} termination={} durationMs={}",
                        correlationId,
                        signal,
                        TimeUnit.NANOSECONDS.toMillis(
                                System.nanoTime() - startedAt)));
    });
}
~~~

Hoàn tất handler không đồng nghĩa requester nhận được receipt nghiệp vụ. FNF chỉ phù hợp khi caller chấp nhận semantics không có response payload.

### 4.3. Request-channel

Channel cần theo dõi riêng số phần tử đầu vào và đầu ra:

~~~java
public Flux<CommandResult> process(
        Flux<ClientCommand> commands,
        String correlationId) {

    return Flux.defer(() -> {
        long startedAt = System.nanoTime();
        LongAdder itemsIn = new LongAdder();
        LongAdder itemsOut = new LongAdder();

        log.debug(
                "event=rsocket.interaction.started type=request-channel route=commands.process correlationId={}",
                correlationId);

        return commands
                .doOnNext(command -> itemsIn.increment())
                .concatMap(command ->
                        commandService.process(command))
                .doOnNext(result -> itemsOut.increment())
                .doOnError(error ->
                        log.warn(
                                "event=rsocket.interaction.error type=request-channel route=commands.process correlationId={} errorType={}",
                                correlationId,
                                error.getClass().getSimpleName(),
                                error))
                .doFinally(signal -> log.info(
                        "event=rsocket.interaction.terminated type=request-channel route=commands.process correlationId={} termination={} durationMs={} itemsIn={} itemsOut={}",
                        correlationId,
                        signal,
                        TimeUnit.NANOSECONDS.toMillis(
                                System.nanoTime() - startedAt),
                        itemsIn.sum(),
                        itemsOut.sum()));
    });
}
~~~

concatMap giữ thứ tự xử lý command. Nếu dùng flatMap, có thể tăng concurrency nhưng kết quả hoàn tất không nhất thiết theo thứ tự đầu vào. Log count riêng cho hai chiều giúp phát hiện tình huống nhận nhiều command nhưng trả ít kết quả.

## 5. Correlation ID và Reactor Context

Correlation ID nối các log của một interaction qua nhiều component. Nên lấy ID từ một nguồn có kiểm soát:

- Metadata do gateway hoặc client gửi, sau khi validate định dạng và độ dài.
- ID do server tạo nếu client không gửi.
- Trace ID từ hệ thống distributed tracing nếu đã có trace context.

Không tin giá trị correlation ID tùy ý mà không giới hạn độ dài và ký tự. Giá trị được log phải được sanitize để tránh log injection qua ký tự xuống dòng hoặc delimiter.

### 5.1. Truyền correlation ID bằng Reactor Context

Reactor Context gắn dữ liệu với subscription, phù hợp hơn việc dựa vào ThreadLocal trong pipeline có thể đổi thread:

~~~java
private static final String CORRELATION_ID = "correlationId";

public Mono<Receipt> handle(
        Command command,
        String correlationId) {

    return Mono.deferContextual(context -> {
        String id = context.getOrDefault(
                CORRELATION_ID, "unknown");

        return Mono.defer(() -> commandService.execute(command))
                .doFinally(signal ->
                        log.info(
                                "event=command.terminated correlationId={} termination={}",
                                id,
                                signal));
    }).contextWrite(context ->
            context.put(CORRELATION_ID, correlationId));
}
~~~

contextWrite làm giá trị có sẵn cho các operator upstream trong subscription. deferContextual đọc giá trị tại thời điểm subscribe, nên nhiều subscription có correlation ID khác nhau không ghi đè lẫn nhau.

### 5.2. MDC là ThreadLocal

MDC của SLF4J thường gắn với thread. Reactor có thể chuyển xử lý giữa nhiều thread; do đó không nên đặt MDC ở đầu request rồi giả định giá trị sẽ tự xuất hiện trong mọi callback.

Các lựa chọn:

1. Dùng Reactor Context làm nguồn dữ liệu correlation chính.
2. Dùng Micrometer Context Propagation khi ứng dụng đã tích hợp context propagation và cấu hình phù hợp.
3. Nếu phải ghi MDC thủ công, đặt và xóa trong phạm vi callback đồng bộ bằng try/finally hoặc MDCCloseable.

Ví dụ đặt MDC trong một callback:

~~~java
.doOnEach(signal -> {
    if (!signal.isOnNext()) {
        return;
    }

    String id = signal.getContextView()
            .getOrDefault(CORRELATION_ID, "unknown");

    try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("correlationId", id)) {
        log.debug("event=command.item.processed");
    }
})
~~~

Không để MDC tồn tại sau callback vì thread có thể được dùng lại cho request khác. Nếu hệ thống dùng Micrometer Tracing hoặc Observation, ưu tiên tích hợp context propagation chuẩn của hệ sinh thái thay vì tự viết một cơ chế ThreadLocal riêng.

## 6. Ghi kích thước payload mà không ghi nội dung

Một log thường chỉ cần biết payload lớn bao nhiêu, không cần biết toàn bộ bytes bên trong. Với RSocket raw Payload, có thể đo số byte có thể đọc:

~~~java
int dataBytes = payload.data().readableBytes();
int metadataBytes = payload.metadata().readableBytes();

log.debug(
        "event=rsocket.payload.received dataBytes={} metadataBytes={}",
        dataBytes,
        metadataBytes);
~~~

Đọc readableBytes không cần chuyển buffer thành String và không làm lộ nội dung payload. Không gọi readBytes hoặc thay đổi readerIndex chỉ để ghi log. Payload có thể sử dụng reference-counted ByteBuf; code quan sát không được retain/release tùy tiện hoặc thay đổi quyền sở hữu buffer.

Ở tầng Spring Messaging, handler thường nhận DTO đã decode thay vì raw Payload. Khi đó có thể log kích thước từ transport instrumentation hoặc từ serializer có kiểm soát; không serialize DTO lần nữa chỉ để tính kích thước nếu việc đó tốn CPU hoặc có thể tạo side effect.

### 6.1. Data và metadata có độ nhạy khác nhau

Metadata có thể chứa route, correlation ID, MIME type, tenant context hoặc bearer authentication. Không mặc định metadata là an toàn chỉ vì nó không phải data section.

Một số trường nên tránh ghi:

- Authorization hoặc bearer token.
- Cookie, session ID, API key và secret.
- Password, mã xác thực một lần và private key.
- Nội dung message có PII, thông tin thanh toán hoặc dữ liệu sức khỏe.
- Binary payload hoặc nội dung người dùng chưa được phân loại.

Metadata size cũng có thể hữu ích cho việc phát hiện payload bất thường, nhưng không ghi nguyên metadata buffer.

## 7. Giới hạn dữ liệu payload được ghi

Mặc định an toàn là không ghi raw payload. Nếu có yêu cầu nghiệp vụ cần ghi một phần nội dung, hãy áp dụng nhiều lớp kiểm soát:

1. **Allowlist**: chỉ chọn field cụ thể đã được phê duyệt.
2. **Redaction**: che token, email, số điện thoại hoặc định danh nhạy cảm theo chính sách.
3. **Truncation**: giới hạn số ký tự hoặc byte sau khi redaction.
4. **Sanitization**: loại hoặc escape CR, LF và control characters để tránh log injection.
5. **Access control**: giới hạn ai có thể đọc log chứa dữ liệu nghiệp vụ.
6. **Retention**: đặt thời hạn lưu trữ phù hợp với mục đích vận hành.

Ví dụ một DTO có thể được chuyển thành log summary:

~~~java
public record CommandLogSummary(
        String commandType,
        String deviceId,
        int payloadBytes,
        String correlationId) {
}

CommandLogSummary summarize(
        DeviceCommand command,
        int payloadBytes,
        String correlationId) {

    return new CommandLogSummary(
            command.type(),
            safeIdentifier(command.deviceId()),
            payloadBytes,
            safeCorrelationId(correlationId));
}
~~~

Summary chỉ chứa các trường đã chọn. Nếu deviceId hoặc correlationId được xem là dữ liệu nhạy cảm trong hệ thống, cần hash bằng HMAC với khóa bí mật hoặc thay bằng ID nội bộ; hash thường không khóa của các giá trị ít entropy có thể bị dò ngược.

### 7.1. Truncation không thay thế redaction

Không cắt payload trước rồi cho rằng phần còn lại an toàn. Token hoặc số định danh nhạy cảm có thể nằm ngay đầu chuỗi. Trình tự đúng là chọn field, redaction, sanitize, rồi mới truncation.

Nếu cắt chuỗi Unicode, dùng giới hạn code point hoặc byte theo một quy tắc rõ ràng; không cắt tùy tiện giữa một ký tự UTF-8. Với binary payload, chỉ ghi kích thước và content type, trừ khi có bộ parser chuyên biệt và chính sách rõ ràng.

### 7.2. Giới hạn log sample

Nếu có lý do cần sample một phần nội dung đã được cho phép:

- Giới hạn rất nhỏ, ví dụ tối đa 256 ký tự sau redaction.
- Không sample authentication metadata.
- Không sample payload thuộc loại dữ liệu bị cấm ghi.
- Đặt sampling rate để không log tất cả request.
- Ghi thêm field payloadTruncated=true khi nội dung đã bị cắt.

Không dùng ví dụ 256 ký tự như một giới hạn bắt buộc cho mọi hệ thống. Giá trị thực tế cần được xác định bởi chính sách dữ liệu, loại payload và chi phí lưu trữ.

## 8. Tránh log quá nhiều phần tử trong stream

Một request-stream có thể phát hàng nghìn hoặc hàng triệu phần tử. Ghi một log INFO cho từng item sẽ làm tăng I/O, chi phí ingest và áp lực lên logging pipeline. Nó còn có thể làm chậm chính stream đang được quan sát.

Thay vì log từng item:

- Ghi một log start và một log terminal.
- Đếm số phần tử vào/ra.
- Ghi sample theo tỷ lệ hoặc mỗi N phần tử ở DEBUG.
- Ghi log WARN khi payload vượt ngưỡng hoặc stream có hành vi bất thường.
- Dùng metrics histogram/counter cho số lượng và thời lượng.

Ví dụ sample mỗi 100 phần tử:

~~~java
AtomicLong count = new AtomicLong();

return source.doOnNext(item -> {
    long current = count.incrementAndGet();
    if (current % 100 == 0) {
        log.debug(
                "event=rsocket.stream.progress route={} itemsOut={}",
                route,
                current);
    }
});
~~~

Với nhiều subscriber, bộ đếm phải được tạo bên trong defer để mỗi subscription có trạng thái riêng. Nếu nguồn được share, hãy quyết định rõ đang đếm phần tử ở upstream một lần hay đếm số phần tử mỗi client nhận.

## 9. Log payload lớn và cảnh báo kích thước

Giới hạn payload được ghi trong log khác với giới hạn payload được phép nhận qua transport:

| Giới hạn | Mục đích |
|---|---|
| Maximum inbound payload size | Bảo vệ memory, decoder và server trước message quá lớn |
| Maximum logged field size | Giới hạn dung lượng log và dữ liệu được lưu |
| Maximum metadata size | Giảm rủi ro metadata bất thường hoặc chứa quá nhiều thông tin |
| Maximum stream item count/rate | Giới hạn công việc hoặc log phát sinh theo thời gian |

Một payload có thể hợp lệ với transport nhưng vẫn không được phép ghi nội dung vào log. Ngược lại, log chỉ ghi size không thay thế việc đặt giới hạn payload ở protocol, server hoặc application layer.

Ví dụ cảnh báo khi payload vượt ngưỡng:

~~~java
private static final int WARN_PAYLOAD_BYTES = 64 * 1024;

void logPayloadSize(
        String route,
        int dataBytes,
        int metadataBytes) {

    if (dataBytes > WARN_PAYLOAD_BYTES) {
        log.warn(
                "event=rsocket.payload.large route={} dataBytes={} metadataBytes={}",
                route,
                dataBytes,
                metadataBytes);
        return;
    }

    log.debug(
            "event=rsocket.payload.received route={} dataBytes={} metadataBytes={}",
            route,
            dataBytes,
            metadataBytes);
}
~~~

Ngưỡng trong ví dụ chỉ minh họa. Hãy căn cứ vào payload contract, transport frame limits, memory budget và kích thước message thực tế.

## 10. Log ở đâu trong Spring RSocket?

Có ba lớp quan sát phổ biến:

| Lớp | Thông tin phù hợp |
|---|---|
| RSocket transport/protocol instrumentation | Connection, frame/interaction type, setup, cancel và lỗi transport |
| Spring Messaging handler | Route, nghiệp vụ, correlation ID và kết quả xử lý |
| Reactor publisher | Subscription, item count, error, completion, cancellation và duration |

Không nên chỉ dựa vào log ở controller nếu cần biết cancellation hoặc lỗi xảy ra sau khi handler đã trả publisher. Operator đặt trong pipeline theo dõi toàn bộ vòng đời subscription.

Ở raw RSocket API, có thể dùng interceptor hoặc wrapper quanh RSocket để quan sát interaction ở mức protocol. Khi làm vậy, interceptor phải bảo toàn semantics của publisher, demand, cancellation và ownership của Payload. Không đọc buffer, subscribe thêm hoặc thay đổi subscription chỉ để ghi log.

Với Spring Messaging, cách đơn giản thường là đặt logging operator quanh publisher mà handler trả về. Điều này giúp log gắn trực tiếp với route và nghiệp vụ, trong khi framework tiếp tục quản lý subscription.

## 11. Phân biệt log, metrics và tracing

Ba loại telemetry bổ sung cho nhau:

| Loại | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Log | Điều gì đã xảy ra với interaction cụ thể? | route, correlation ID, exception, termination |
| Metric | Hệ thống có đang hoạt động tốt trên diện rộng? | request rate, error count, duration histogram, active streams |
| Trace | Một request đi qua những service/span nào? | RSocket ingress → broker publish → downstream service |

Không dùng log thay thế metric. Để biết p95 latency hoặc số stream đang hoạt động, dùng histogram/gauge. Để nối một request qua nhiều service, dùng distributed tracing với trace context đã được truyền đúng cách.

Tránh đưa user ID, connection ID, correlation ID hoặc device ID vào label metric có cardinality cao. Các giá trị đó phù hợp với log/trace khi đã có chính sách bảo vệ dữ liệu.

## 12. Async logging và ảnh hưởng tới realtime

Logging có thể tạo I/O và serialization. Nếu appender ghi đồng bộ vào file hoặc mạng, callback xử lý có thể bị chậm. Với stream có tần suất cao, cân nhắc async appender nhưng cần cấu hình rõ:

- Queue có giới hạn để tránh tăng heap vô hạn.
- Chính sách khi queue đầy: block, drop hoặc discard theo level.
- Theo dõi số log bị drop và queue utilization.
- Không chuyển log audit bắt buộc sang một appender có thể âm thầm drop.
- Không tạo thread hoặc executor mới cho từng interaction.

Async logging giảm công việc ghi log trên thread xử lý, nhưng không làm miễn phí việc tạo event, format và serialize. Sampling và giảm field vẫn cần thiết.

Không dùng một scheduler reactive riêng cho mỗi log event. Hãy để logging framework quản lý appender và queue.

## 13. Lỗi thường gặp

### Ghi toàn bộ payload ở INFO

Điều này dễ làm lộ dữ liệu, tăng chi phí lưu trữ và làm chậm stream. Chỉ ghi field allowlist và size.

### Chỉ log lúc handler bắt đầu

Không biết stream hoàn tất, phát lỗi hay bị hủy. Gắn doFinally để ghi terminal state.

### Xem cancel là lỗi server

Client có thể hủy hợp lệ. Ghi termination=cancel riêng với error.

### Ghi log từng item của request-stream

Lưu lượng log có thể lớn hơn lưu lượng nghiệp vụ. Đếm, sample hoặc log định kỳ.

### Đọc raw buffer chỉ để log

Có thể làm thay đổi reader index, copy dữ liệu hoặc gây lỗi ownership. Chỉ đọc readableBytes khi cần đo kích thước.

### Log metadata vì nghĩ metadata không nhạy cảm

Metadata có thể chứa bearer token hoặc credential. Không log nguyên metadata section.

### Dùng MDC như context tự động trong Reactor

MDC là ThreadLocal; thread switch có thể làm mất hoặc rò giá trị. Dùng Reactor Context và cơ chế context propagation phù hợp.

### Nuốt lỗi sau khi log

Logging không phải xử lý lỗi. Không chuyển error thành complete chỉ để tránh stack trace nếu caller hoặc framework cần biết request thất bại.

### Đưa ID duy nhất vào metric labels

Cardinality tăng nhanh và làm hệ thống metrics tốn bộ nhớ. Dùng log hoặc trace cho ID chi tiết.

## 14. Kiểm thử lifecycle log và giới hạn payload

Kiểm thử cần xác minh cả sự kiện lẫn dữ liệu được phép xuất hiện:

1. Request-response phát log start và terminal complete.
2. Request-stream bị client cancel có terminal cancel.
3. Publisher phát lỗi có error log và terminal error.
4. Request-channel đếm inbound và outbound riêng.
5. Correlation ID đúng theo từng subscription và không rò giữa hai request.
6. Payload summary chỉ chứa field allowlist.
7. Bearer token và credential không xuất hiện trong log.
8. Payload vượt ngưỡng chỉ tạo log size/warning, không ghi raw content.
9. Stream lớn không tạo một log INFO cho mỗi phần tử.
10. MDC được xóa sau callback và không xuất hiện trên request tiếp theo.
11. Log appender queue có giới hạn và hành vi khi đầy được kiểm tra.

### 14.1. Kiểm thử complete và cancel

~~~java
@Test
void logsCancellationAsItsOwnTermination() {
    List<SignalType> terminations = new CopyOnWriteArrayList<>();

    Flux<Long> stream = Flux.interval(Duration.ofMillis(20))
            .doFinally(terminations::add);

    StepVerifier.create(stream)
            .expectNext(0L)
            .thenCancel()
            .verify();

    assertThat(terminations).containsExactly(SignalType.CANCEL);
}
~~~

Test trên xác minh Reactor phát tín hiệu CANCEL ở terminal hook. Với logger thực tế, dùng test appender để kiểm tra event name và field termination.

### 14.2. Kiểm thử không ghi secret

~~~java
@Test
void payloadSummaryDoesNotExposeBearerToken() {
    String token = "test-secret-token";
    CommandLogSummary summary =
            logSummaryFactory.create(
                    new DeviceCommand("restart", "device-17"),
                    128,
                    "corr-17");

    String serialized = objectMapper.writeValueAsString(summary);

    assertThat(serialized).doesNotContain(token);
    assertThat(serialized).contains("device-17");
}
~~~

Test này kiểm tra summary allowlist. Nên bổ sung test appender cho toàn bộ lifecycle logger để bảo đảm exception message, metadata hoặc debug log không vô tình chứa token.

## 15. Checklist triển khai

Trước khi bật logging cho RSocket trong production, hãy xác nhận:

1. Mỗi interaction có log start và terminal state phù hợp.
2. Complete, error và cancel được phân biệt.
3. Request-channel đếm inbound và outbound riêng.
4. Log dùng route, interaction type và correlation ID có kiểm soát.
5. Reactor Context là nguồn context phù hợp; MDC không bị giữ qua thread reuse.
6. Payload mặc định không ghi raw content.
7. Chỉ field allowlist được ghi; dữ liệu nhạy cảm được redacted.
8. Payload sample có giới hạn và sanitize CR/LF.
9. Data bytes và metadata bytes được đo mà không thay đổi buffer ownership.
10. Stream item log được sample hoặc aggregate.
11. Log level và sampling phù hợp với lưu lượng.
12. Async appender có queue hữu hạn và chính sách overflow rõ.
13. Metrics và tracing được dùng cho latency, rate và distributed flow.
14. Correlation ID chi tiết không được dùng làm metric label.
15. Test xác minh token/secret không xuất hiện trong log.
16. Retention và quyền truy cập log phù hợp với dữ liệu được ghi.

## 16. Tổng kết

Log RSocket hiệu quả cần mô tả vòng đời interaction thay vì ghi tràn lan nội dung payload. Dùng Reactor operator để quan sát start, error và terminal signal; phân biệt complete, error và cancel; ghi duration, item count, route, correlation ID và kích thước data/metadata. Với stream lớn, hãy sample hoặc aggregate thay vì log từng phần tử.

Payload mặc định không nên được ghi nguyên văn. Hãy dùng allowlist, redaction, sanitization và truncation có giới hạn; không log bearer token hoặc metadata chưa được phân loại. Trong pipeline reactive, truyền correlation bằng Reactor Context và chỉ dùng MDC trong phạm vi callback có cleanup. Kết hợp log với metrics và tracing để chẩn đoán hệ thống mà không làm logging trở thành nguồn rò rỉ dữ liệu hoặc nút thắt của luồng realtime.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Project Reactor Reference — Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Project Reactor API — Flux doFinally and lifecycle operators](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [SLF4J Manual — MDC](https://www.slf4j.org/manual.html#mdc)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
