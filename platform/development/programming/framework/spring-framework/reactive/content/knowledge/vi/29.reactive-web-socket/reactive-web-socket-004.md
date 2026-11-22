# Đọc receive, ghi send và kết hợp vòng đời hai hướng trong Spring WebFlux WebSocket

## 1. WebSocket là kênh giao tiếp hai chiều

WebSocket tạo một kết nối full-duplex giữa client và server trên cùng một TCP connection. Sau HTTP handshake thành công, hai phía có thể gửi và nhận message độc lập, không cần tạo một HTTP request mới cho từng message.

Trong Spring WebFlux, API reactive trung tâm là:

- `WebSocketHandler`: xử lý một phiên WebSocket; method `handle(WebSocketSession)` trả `Mono<Void>`.
- `WebSocketSession.receive()`: cung cấp `Flux<WebSocketMessage>` của message đi vào.
- `WebSocketSession.send(Publisher<WebSocketMessage>)`: ghi publisher message đi ra và trả `Mono<Void>` hoàn tất khi nguồn kết thúc và việc ghi xong.
- `WebSocketSession.close(...)`: yêu cầu đóng phiên với close status.
- `WebSocketSession.closeStatus()`: nhận close status của phiên nếu có.

Mỗi handler phải kết hợp luồng vào, luồng ra và quy tắc kết thúc phiên thành một reactive flow duy nhất. Nếu chỉ tạo publisher mà không trả nó từ `handle` hoặc không compose vào publisher được trả về, công việc có thể không chạy hoặc vòng đời session bị kết thúc sai.

## 2. Vòng đời từ handshake đến khi đóng

~~~text
Client                              Spring WebFlux
  |                                      |
  |--- HTTP Upgrade: websocket -------->|
  |<-- 101 Switching Protocols ---------|
  |                                      |
  |<====== WebSocket connection ========>|
  |                                      |
  |--- message A ----------------------->|
  |--- message B ----------------------->|
  |<-- reply A --------------------------|
  |<-- reply B --------------------------|
  |                                      |
  |--- Close frame --------------------->|
  |<-- Close frame / connection ends ---|
  |                                      |
  |        receive completes/errors      |
  |        send is completed/cancelled   |
  |        handle Mono terminates        |
~~~

Có ba mốc cần phân biệt:

1. **Handshake:** HTTP chuyển sang WebSocket. Handler chỉ được gọi khi phiên đã được thiết lập.
2. **Trao đổi message:** inbound và outbound hoạt động đồng thời; mỗi luồng có demand, completion, error và cancellation riêng.
3. **Kết thúc:** client đóng, server chủ động đóng, lỗi giao thức, lỗi xử lý hoặc caller cancel. Publisher trả về từ handler phải phản ánh đúng lúc ứng dụng kết thúc xử lý session.

WebSocket là một giao thức có trạng thái theo kết nối. Đừng xử lý nó như một controller HTTP trả response rồi kết thúc ngay.

## 3. Hai API chính: receive và send

### 3.1. receive(): đọc message đi vào

`receive()` trả `Flux<WebSocketMessage>`:

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    return session.receive()
            .doOnNext(message ->
                    log.debug("Inbound type={}", message.getType()))
            .then();
}
~~~

- Mỗi phần tử đại diện một WebSocket message.
- Luồng nhận phát completion hoặc error khi kết nối đóng.
- `then()` bỏ các phần tử và chuyển completion/error của Flux thành `Mono<Void>`.
- Publisher chỉ chạy khi có subscriber. Việc trả publisher từ `handle` khiến framework subscribe và quản lý lifecycle.

Không gọi `subscribe()` riêng trong handler:

~~~java
// Sai: tách receive khỏi lifecycle mà framework đang quản lý.
session.receive().subscribe(this::process);
return Mono.empty();
~~~

Handler trên có thể kết thúc ngay, trong khi tác vụ đọc message vẫn chạy độc lập. Khi đó lỗi, cancellation và đóng session không còn được phối hợp đúng.

### 3.2. send(): ghi message đi ra

`send(Publisher<WebSocketMessage>)` nhận một nguồn message và trả `Mono<Void>`:

~~~java
Flux<WebSocketMessage> outgoing = Flux.just(
        session.textMessage("first"),
        session.textMessage("second"));

return session.send(outgoing);
~~~

`send` hoàn tất khi nguồn outbound hoàn tất và các thao tác ghi message đã xong. Nếu nguồn không bao giờ hoàn tất, luồng send tiếp tục sống cho tới khi session hoặc nguồn bị kết thúc.

Dùng các factory của session để tạo message:

~~~java
WebSocketMessage text =
        session.textMessage("hello");

WebSocketMessage binary =
        session.binaryMessage(
                factory -> factory.wrap(new byte[] {1, 2, 3}));

WebSocketMessage ping =
        session.pingMessage(
                factory -> factory.wrap(new byte[] {1}));

WebSocketMessage pong =
        session.pongMessage(
                factory -> factory.wrap(new byte[] {1}));
~~~

Các factory dùng đúng `DataBufferFactory` của session. Với binary payload, dữ liệu được cung cấp qua factory callback.

### 3.3. Message type và cách đọc payload

`WebSocketMessage.Type` có các loại:

| Type | Nội dung |
| --- | --- |
| `TEXT` | Text message |
| `BINARY` | Binary message |
| `PING` | Ping control message |
| `PONG` | Pong control message |

`getPayloadAsText()` giải mã payload bằng UTF-8 mặc định. Chỉ dùng khi message là text hoặc payload được quy ước là văn bản:

~~~java
String text = message.getPayloadAsText();
~~~

Với binary message, đọc `getPayload()` dưới dạng `DataBuffer` và xử lý bytes theo protocol của ứng dụng. Không dùng `getPayloadAsText()` để giải mã dữ liệu nhị phân tùy ý.

## 4. Mẫu đơn giản nhất: đọc message rồi phản hồi

Đối với echo server, outbound có thể được tạo trực tiếp từ inbound:

~~~java
@Component
public class EchoWebSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> replies = session.receive()
                .map(message ->
                        session.textMessage(
                                "echo:" + message.getPayloadAsText()));

        return session.send(replies);
    }
}
~~~

Luồng hoạt động:

1. `receive()` lấy message từ client.
2. `map` đọc text đồng bộ và tạo một text message mới.
3. `send` ghi từng message được tạo.
4. Handler tiếp tục sống trong khi nguồn inbound còn phát message và session còn hoạt động.

Đây là một flow kết hợp sẵn hai hướng: outbound được dẫn động bởi inbound. Không cần tạo hai subscription độc lập cho cùng một nguồn receive.

Ví dụ chỉ định nghĩa protocol text. Nếu endpoint cần nhận binary, hãy phân nhánh theo `message.getType()` và chuyển bytes bằng binary message factory.

## 5. Xử lý bất đồng bộ từng message bằng concatMap

Khi mỗi message cần gọi service, database hoặc một publisher khác, dùng operator nhận và chờ publisher con hoàn tất:

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> replies = session.receive()
            .concatMap(message ->
                    messageService.process(message.getPayloadAsText())
                            .map(result ->
                                    session.textMessage(result)));

    return session.send(replies);
}
~~~

`concatMap` xử lý lần lượt:

- Message kế tiếp chỉ được xử lý sau khi publisher của message hiện tại hoàn tất.
- Thứ tự đầu vào được giữ trong thứ tự phản hồi.
- Một xử lý chậm sẽ làm các message sau chờ; đây là lựa chọn có chủ đích khi thứ tự quan trọng.

Đừng dùng `doOnNext` để khởi chạy một tác vụ reactive rồi bỏ qua publisher:

~~~java
// Sai: process() không được compose vào lifecycle.
session.receive()
        .doOnNext(message ->
                messageService.process(message.getPayloadAsText()).subscribe());
~~~

Cách đúng là trả publisher từ `concatMap`, `flatMap` hoặc operator phù hợp khác.

### 5.1. concatMap, flatMap và flatMapSequential

| Operator | Cách xử lý | Khi phù hợp |
| --- | --- | --- |
| `concatMap` | Một inner publisher tại một thời điểm, giữ thứ tự | Chat, command, cập nhật state theo thứ tự |
| `flatMap` | Cho phép nhiều inner publisher chạy đồng thời; kết quả có thể xen kẽ | Message độc lập, cần throughput |
| `flatMapSequential` | Chạy inner publisher đồng thời nhưng phát kết quả theo thứ tự nguồn | Xử lý song song mà vẫn giữ thứ tự phản hồi |

Ví dụ song song có giới hạn:

~~~java
Flux<WebSocketMessage> replies = session.receive()
        .flatMap(
                message -> messageService.process(
                                message.getPayloadAsText())
                        .map(session::textMessage),
                8);
~~~

Con số `8` là concurrency tối đa cho inner publisher trong ví dụ. Hãy chọn theo khả năng của service downstream và giới hạn tải thực tế.

Nếu message làm thay đổi state hoặc phụ thuộc message trước, concurrency có thể làm sai thứ tự nghiệp vụ. Giữ `concatMap` trong trường hợp đó.

## 6. Hai luồng độc lập: xử lý inbound và chủ động push outbound

Không phải mọi message gửi đi đều là phản hồi cho message vừa nhận. Server có thể phải gửi thông báo từ event bus, tiến trình nền, đồng hồ hoặc service khác trong khi vẫn nhận lệnh từ client.

Mẫu composition:

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Mono<Void> input = session.receive()
            .concatMap(message ->
                    commandService.handle(
                            session.getId(),
                            message.getPayloadAsText()))
            .then();

    Flux<String> notifications =
            notificationService.eventsFor(session.getId());

    Mono<Void> output = session.send(
            notifications.map(session::textMessage));

    return input.and(output);
}
~~~

Ở đây:

- `input` sở hữu việc đọc và xử lý inbound.
- `output` sở hữu một nguồn thông báo độc lập.
- `and` ghép các termination signal thành một `Mono<Void>`.
- Lỗi từ một nhánh được truyền ra kết quả composition; nhánh còn lại được điều phối theo semantics của operator và trạng thái session.

`notificationService.eventsFor` và `commandService.handle` là service giả định của ứng dụng. Cần bảo đảm chúng trả publisher reactive, không block event loop.

### 6.1. Chọn chính sách kết thúc cho hai nhánh

Có nhiều yêu cầu lifecycle khác nhau:

**Chờ cả hai nhánh kết thúc bình thường:**

~~~java
return Mono.when(input, output);
~~~

`Mono.when` chờ tất cả publisher hoàn tất; nếu một publisher lỗi, các publisher còn lại đang chạy sẽ bị cancel.

**Kết thúc khi nhánh nào phát terminal signal trước:**

~~~java
return Mono.firstWithSignal(input, output);
~~~

`firstWithSignal` chọn signal đầu tiên (complete hoặc error) và cancel nhánh còn lại. Dùng khi một nhánh kết thúc phải làm handler kết thúc ngay.

**Dùng `and`:**

~~~java
return input.and(output);
~~~

`Mono.and` ghép termination signal của hai nguồn thành một `Mono<Void>`. Đây là pattern composition được Spring dùng trong ví dụ inbound/outbound độc lập. Cần hiểu semantics của hai publisher và cách connector kết thúc send khi socket đóng.

Không dùng `Mono.zip(input, output)` để chỉ phối hợp hai tác vụ void. Zip chờ mỗi Mono phát một giá trị; `Mono<Void>` hoàn tất rỗng nên zip không phù hợp với ý định chờ hai tác vụ. Dùng `and` hoặc `when` cho các publisher chỉ biểu diễn completion.

## 7. Hợp nhất nhiều nguồn outbound vào một send

Một session thường có nhiều nguồn gửi dữ liệu: thông báo nghiệp vụ, heartbeat ứng dụng, kết quả command hoặc sự kiện hệ thống.

Hợp nhất chúng trước khi gọi `send`:

~~~java
Flux<WebSocketMessage> outgoing = Flux.merge(
        chatEvents.map(session::textMessage),
        statusEvents.map(session::textMessage),
        heartbeatEvents.map(session::textMessage));

return session.send(outgoing);
~~~

`Flux.merge` cho phép các nguồn phát xen kẽ. Thứ tự giữa các nguồn phụ thuộc thời điểm phát, không có bảo đảm rằng tất cả chat message sẽ đứng trước status message.

Nếu cần thứ tự tuần tự giữa các nguồn:

~~~java
Flux<WebSocketMessage> outgoing = Flux.concat(
        initialSnapshot.map(session::textMessage),
        liveEvents.map(session::textMessage));

return session.send(outgoing);
~~~

`concat` hoàn tất nguồn trước rồi mới đăng ký nguồn tiếp theo. Không dùng cách này nếu nguồn đầu là stream vô hạn, vì nguồn sau sẽ không bao giờ được đăng ký.

**Quy tắc thực hành:** một session nên có một outbound publisher chính và một lời gọi `session.send(...)` quản lý việc ghi. Đưa các nguồn vào `merge`, `concat` hoặc một queue có chính sách rõ ràng trước khi send. Tránh nhiều thành phần gọi send độc lập làm việc kiểm soát thứ tự và lifecycle trở nên khó đoán.

## 8. Backpressure và client đọc chậm

Reactive Streams dùng demand để điều tiết lượng dữ liệu. `receive()` và `send()` đều nằm trong publisher chain, do đó tốc độ xử lý và ghi có thể ảnh hưởng đến demand.

Ví dụ:

~~~java
Flux<WebSocketMessage> replies = session.receive()
        .concatMap(message ->
                messageService.process(message.getPayloadAsText())
                        .map(session::textMessage));

return session.send(replies);
~~~

Nếu service xử lý chậm, `concatMap` không mở thêm nhiều tác vụ xử lý cùng lúc. Điều này giúp giới hạn công việc đang chạy và giữ thứ tự.

Nếu client nhận chậm, việc ghi outbound có thể bị chậm theo. Một nguồn phát nhanh hơn tốc độ ghi có thể tích lũy dữ liệu nếu ứng dụng chủ động buffer.

### 8.1. Không buffer vô hạn

Không nên biến event stream thành một queue không giới hạn:

~~~java
// Rủi ro: client chậm lâu có thể làm queue tăng không giới hạn.
events.onBackpressureBuffer()
~~~

Với server có nhiều session, mỗi queue có thể giữ payload và object cho tới khi client đọc hoặc ngắt kết nối. Điều này gây memory pressure và có thể làm toàn bộ service suy giảm.

Chọn một chính sách theo loại message:

- **Command/audit:** không âm thầm drop; giới hạn queue và trả lỗi hoặc đóng session khi vượt giới hạn.
- **Trạng thái mới nhất:** có thể coalesce, chỉ giữ giá trị mới nhất nếu protocol cho phép.
- **Telemetry:** có thể drop có kiểm soát và đo số lượng bị drop.
- **Chat/event quan trọng:** cần persistence hoặc broker để client có thể resume, thay vì chỉ dựa vào queue trong memory.

Backpressure không tự giải quyết mọi trường hợp. Nguồn event ngoài Reactive Streams có thể không biết demand của client; khi đó cần một adapter/queue có giới hạn và chính sách overflow rõ ràng.

### 8.2. Xử lý nhiều producer

Nếu nhiều thành phần nghiệp vụ cùng tạo outbound event cho một session, có thể đưa chúng vào một sink/queue rồi dùng một publisher duy nhất cho `send`.

Ví dụ về ý tưởng với queue hữu hạn:

~~~java
Queue<ServerEvent> queue = new ArrayBlockingQueue<>(256);

Sinks.Many<ServerEvent> sink =
        Sinks.many().unicast().onBackpressureBuffer(queue);

Mono<Void> output = session.send(
        sink.asFlux().map(event ->
                session.textMessage(event.toJson())));
~~~

Producer gọi `sink.tryEmitNext(event)` và phải xử lý kết quả emission. Nếu queue đầy hoặc emission thất bại, không được bỏ qua kết quả; hãy áp dụng policy như retry có giới hạn, reject, coalesce hoặc drop có metric.

Đây là một mảnh cấu trúc minh họa, cần quản lý sink theo từng session và complete/error nó khi session kết thúc. Không dùng một sink dùng chung cho mọi client nếu mỗi client phải nhận tập event riêng.

## 9. Buffer ownership: retain và release khi xử lý bất đồng bộ

`WebSocketMessage` chứa `DataBuffer`. Trên Reactor Netty, payload có thể dùng pooled buffer và reference counting. Khi code giữ payload sau callback nhận message, buffer có thể được release trước khi tác vụ bất đồng bộ đọc xong.

### 9.1. Đọc text đồng bộ

Nếu chuyển payload thành String ngay trong operator:

~~~java
Flux<String> textMessages = session.receive()
        .map(WebSocketMessage::getPayloadAsText);
~~~

String là object Java độc lập với DataBuffer. Nếu service chỉ cần String, có thể truyền String qua các bước bất đồng bộ mà không cần giữ WebSocketMessage.

### 9.2. Giữ message để xử lý bất đồng bộ

Nếu tác vụ cần đọc payload DataBuffer sau khi callback hiện tại kết thúc, retain trước khi chuyển quyền sử dụng và release sau khi publisher xử lý hoàn tất:

~~~java
Mono<Void> input = session.receive()
        .concatMap(message -> {
            message.retain();

            return Mono.defer(() ->
                            binaryService.store(message.getPayload()))
                    .doFinally(signal -> message.release());
        })
        .then();
~~~

Trong ví dụ:

- `retain()` giữ thêm một reference cho payload.
- `Mono.defer(...)` trì hoãn việc gọi service cho tới lúc subscribe.
- `doFinally(...)` release reference đã retain khi publisher complete, error hoặc cancel.
- `concatMap` chờ tác vụ hiện tại hoàn tất trước khi xử lý message tiếp theo.

`binaryService.store(...)` là service giả định và phải hoàn tất việc đọc payload trước khi publisher kết thúc. Nếu service tự retain hoặc chuyển buffer cho một tác vụ khác tồn tại lâu hơn publisher, ownership phải được chuyển giao rõ ràng và có release tương ứng ở chủ sở hữu cuối cùng.

### 9.3. Không retain nếu không cần

Retain thêm reference làm tăng trách nhiệm cleanup. Nếu chỉ cần text hoặc bytes nhỏ, copy/convert đồng bộ rồi xử lý object độc lập thường đơn giản hơn.

Không gọi release hai lần cho cùng một reference. Không release payload trước khi downstream hoặc writer hoàn tất. Không giữ WebSocketMessage trong field hoặc collection sau khi receive callback kết thúc nếu chưa retain và thiết kế lifecycle cleanup.

## 10. Kết thúc session: complete, error và cancel

`handle` trả `Mono<Void>` biểu diễn thời gian ứng dụng còn xử lý session.

Các tình huống:

| Sự kiện | Tín hiệu reactive | Ý nghĩa |
| --- | --- | --- |
| Client gửi close frame | receive hoàn tất theo session lifecycle | Inbound không còn message |
| Kết nối lỗi | receive hoặc send phát error | Handler phải kết thúc hoặc xử lý lỗi có chủ đích |
| Outbound publisher hoàn tất | send hoàn tất sau khi ghi xong | Nguồn gửi đã hết |
| Caller cancel handler | Subscription bị cancel | Công việc upstream được yêu cầu dừng |
| Server gọi close | close publisher hoàn tất/error | Ứng dụng chủ động yêu cầu đóng session |

Khi inbound và outbound được compose đúng, không cần vòng lặp polling `session.isOpen()` để đoán trạng thái kết nối. Reactive Streams truyền completion, error và cancellation qua các publisher.

### 10.1. Đóng session có chủ đích

`close()` mặc định dùng `CloseStatus.NORMAL`:

~~~java
Mono<Void> closeNormally(WebSocketSession session) {
    return session.close();
}
~~~

Hoặc chọn close status:

~~~java
Mono<Void> closeWithReason(WebSocketSession session) {
    return session.close(
            new CloseStatus(1008, "Policy violation"));
}
~~~

Các mã thường gặp theo WebSocket protocol:

| Code | Ý nghĩa |
| --- | --- |
| 1000 | Normal closure |
| 1001 | Going away |
| 1002 | Protocol error |
| 1003 | Unsupported data |
| 1008 | Policy violation |
| 1009 | Message too big |
| 1011 | Unexpected server condition |

Một số code như 1005 và 1006 là giá trị dành cho mô tả trạng thái đóng trong nội bộ protocol; không gửi chúng như close frame bình thường.

`close` trả Publisher. Phải compose nó vào handler:

~~~java
return processCommand()
        .then(session.close(CloseStatus.NORMAL));
~~~

Không gọi `session.close()` rồi bỏ qua Mono trả về. Nếu không subscribe/compose, thao tác đóng không nằm trong lifecycle được điều khiển.

### 10.2. Đọc close status

Sau khi session kết thúc, có thể ghi nhận close status:

~~~java
return session.receive()
        .then(session.closeStatus())
        .doOnNext(status ->
                log.info("WebSocket closed: {}", status))
        .then();
~~~

`closeStatus()` trả `Mono<CloseStatus>`. Publisher có thể hoàn tất rỗng nếu phiên kết thúc mà không có close status.

`isOpen()` chỉ phản ánh trạng thái tại thời điểm gọi; nó không thay thế các terminal signal của receive/send.

### 10.3. Cleanup bằng doFinally

`doFinally` được gọi sau complete, error hoặc cancel:

~~~java
return session.send(outgoing)
        .doFinally(signal ->
                sessionRegistry.remove(session.getId()));
~~~

Đây là vị trí phù hợp cho cleanup đồng bộ nhẹ như xóa session khỏi registry, ghi metric hoặc cập nhật trạng thái. Nếu cleanup là bất đồng bộ và phải hoàn tất trước khi handler kết thúc, hãy compose Publisher cleanup bằng các operator như `then`, `onErrorResume` hoặc `usingWhen` phù hợp.

Không thực hiện I/O blocking hoặc công việc nặng trong callback `doFinally`.

## 11. Error handling trong hai hướng

Lỗi có thể đến từ:

- Payload không đúng format hoặc protocol.
- Service xử lý message phát error.
- Nguồn outbound phát error.
- Network/connection đóng bất thường.
- Writer không thể ghi message.

Đừng biến mọi lỗi thành complete rỗng:

~~~java
// Không nên: làm mất nguyên nhân và che lỗi session.
return session.receive()
        .onErrorResume(error -> Flux.empty())
        .then();
~~~

Nếu lỗi nghiệp vụ của một message có thể phục hồi, xử lý trong inner publisher:

~~~java
Flux<WebSocketMessage> replies = session.receive()
        .concatMap(message ->
                messageService.process(message.getPayloadAsText())
                        .map(session::textMessage)
                        .onErrorResume(
                                RecoverableMessageException.class,
                                error -> Mono.just(
                                        session.textMessage(
                                                "error:" + error.getMessage()))));

return session.send(replies);
~~~

Lỗi không khôi phục được nên tiếp tục truyền ra handler để framework/connector kết thúc phiên theo lifecycle. Nếu cần close status riêng, chuyển lỗi thành một luồng đóng session có chủ đích và compose kết quả đó.

Ghi log session ID, message type, error category và correlation ID. Tránh log toàn bộ payload nếu message có token, dữ liệu cá nhân hoặc bí mật.

## 12. Một WebSocketHandler hoàn chỉnh cho echo

Ví dụ sau chỉ nhận text message và gửi lại prefix `echo:`. Việc chuyển text sang String xảy ra đồng bộ trước khi tạo message outbound, nên không cần retain inbound buffer.

~~~java
package example.websocket;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class EchoWebSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> replies = session.receive()
                .map(message -> {
                    if (message.getType()
                            != WebSocketMessage.Type.TEXT) {
                        throw new IllegalArgumentException(
                                "This endpoint accepts text messages only");
                    }

                    String text = message.getPayloadAsText();
                    return session.textMessage("echo:" + text);
                });

        return session.send(replies);
    }
}
~~~

Đây là handler đủ để minh họa receive-to-send flow. Endpoint production cần xác định cách trả lỗi cho message type không hỗ trợ, giới hạn message size, xác thực session và chính sách đóng kết nối.

## 13. Chương trình Spring Boot WebFlux Java 17+ chạy được

Dự án sau tạo WebSocket endpoint `/ws/echo` và integration test dùng chính `WebSocketClient` của Spring để gửi hai message rồi xác nhận hai phản hồi.

Yêu cầu: **JDK 17+**, **Maven 3.6.3+**, **Spring Boot 4.1.2**. Spring Boot BOM quản lý Spring Framework, Reactor và Reactor Netty tương thích.

### 13.1. Cấu trúc thư mục

~~~text
webflux-websocket-demo/
  pom.xml
  src/main/java/example/websocket/WebSocketDemoApplication.java
  src/main/java/example/websocket/WebSocketConfiguration.java
  src/main/java/example/websocket/EchoWebSocketHandler.java
  src/test/java/example/websocket/WebSocketIntegrationTest.java
~~~

### 13.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webflux-websocket-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 13.3. Class khởi động

**src/main/java/example/websocket/WebSocketDemoApplication.java**

~~~java
package example.websocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSocketDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                WebSocketDemoApplication.class, args);
    }
}
~~~

### 13.4. Đăng ký endpoint WebSocket

**src/main/java/example/websocket/WebSocketConfiguration.java**

~~~java
package example.websocket;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;

@Configuration
public class WebSocketConfiguration {

    @Bean
    HandlerMapping webSocketMapping(EchoWebSocketHandler handler) {
        Map<String, WebSocketHandler> handlers =
                Map.of("/ws/echo", handler);

        SimpleUrlHandlerMapping mapping =
                new SimpleUrlHandlerMapping();

        mapping.setUrlMap(handlers);
        mapping.setOrder(-1);

        return mapping;
    }
}
~~~

`SimpleUrlHandlerMapping` ánh xạ URL tới `WebSocketHandler`. Khi dùng Spring Boot WebFlux auto-configuration, `WebSocketHandlerAdapter` được cấu hình bởi hạ tầng WebFlux. Nếu ứng dụng không dùng WebFlux config, cần đăng ký adapter tương ứng.

Không thêm `@EnableWebFlux` chỉ để đăng ký WebSocket endpoint trong ứng dụng Boot thông thường, vì annotation đó thay đổi cách Boot auto-configure WebFlux.

### 13.5. Handler echo

**src/main/java/example/websocket/EchoWebSocketHandler.java**

~~~java
package example.websocket;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class EchoWebSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> replies = session.receive()
                .map(message -> {
                    if (message.getType()
                            != WebSocketMessage.Type.TEXT) {
                        throw new IllegalArgumentException(
                                "Text messages only");
                    }

                    return session.textMessage(
                            "echo:" + message.getPayloadAsText());
                });

        return session.send(replies);
    }
}
~~~

Handler dùng một pipeline nhận và chuyển đổi message rồi đưa publisher kết quả cho send. Khi inbound/session kết thúc, outbound publisher cũng kết thúc theo lifecycle kết nối.

### 13.6. Integration test với WebSocketClient

**src/test/java/example/websocket/WebSocketIntegrationTest.java**

~~~java
package example.websocket;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebSocketIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void sendsAndReceivesMessagesConcurrently() {
        WebSocketClient client =
                new ReactorNettyWebSocketClient();

        URI url = URI.create(
                "ws://localhost:" + port + "/ws/echo");

        Mono<Void> sessionResult = client.execute(url, session -> {
            Flux<WebSocketMessage> messages = Flux.just(
                    session.textMessage("one"),
                    session.textMessage("two"));

            Mono<Void> send = session.send(messages);

            Mono<List<String>> receive = session.receive()
                    .map(WebSocketMessage::getPayloadAsText)
                    .take(2)
                    .collectList();

            return Mono.zip(
                            send.thenReturn(Boolean.TRUE),
                            receive)
                    .doOnNext(result ->
                            assertEquals(
                                    List.of("echo:one", "echo:two"),
                                    result.getT2()))
                    .then();
        });

        sessionResult.block(Duration.ofSeconds(5));
    }
}
~~~

Điểm quan trọng trong test:

- `send` và `receive` được subscribe cùng lúc qua `Mono.zip`.
- Client không đợi gửi xong rồi mới bắt đầu đọc; server có thể phản hồi trong khi client vẫn đang ghi.
- `take(2)` giới hạn hai phản hồi cần xác nhận.
- `block(Duration)` chỉ được dùng ở test boundary để chờ toàn bộ session; không dùng block trong WebFlux handler hoặc service reactive.

### 13.7. Chạy dự án và test

Tại thư mục có `pom.xml`:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Maven test chạy integration test với một server ngẫu nhiên trên localhost. Test xác nhận đúng hai phản hồi theo thứ tự:

~~~text
echo:one
echo:two
~~~

Có thể kiểm tra bằng browser sau khi ứng dụng chạy:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");

socket.onopen = () => {
  socket.send("one");
  socket.send("two");
};

socket.onmessage = event => {
  console.log(event.data);
};
~~~

Console nhận:

~~~text
echo:one
echo:two
~~~

## 14. Ví dụ client có inbound và outbound độc lập

Phía client cũng dùng cùng một API session. Ví dụ client vừa gửi command vừa nhận thông báo:

~~~java
WebSocketClient client = new ReactorNettyWebSocketClient();

Mono<Void> connected = client.execute(
        URI.create("ws://localhost:8080/ws/notifications"),
        session -> {
            Mono<Void> sendCommands = session.send(
                    Flux.just(
                            session.textMessage("subscribe:orders"),
                            session.textMessage("subscribe:alerts")));

            Mono<Void> receiveEvents = session.receive()
                    .concatMap(message -> {
                        String event = message.getPayloadAsText();
                        return eventProcessor.handle(event);
                    })
                    .then();

            return sendCommands.and(receiveEvents);
        });
~~~

Đây là đoạn minh họa client, giả định có `eventProcessor`. Client vẫn phải giữ một handler publisher làm owner của session. Nếu chỉ cần gửi một số command rồi tiếp tục nhận vô hạn, composition phải cho phép inbound tiếp tục sau khi nguồn gửi finite hoàn tất.

## 15. Kiểm thử lifecycle và các tình huống biên

Một test echo cơ bản chỉ xác nhận đường thành công. Ứng dụng thực tế nên kiểm tra thêm:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Client gửi nhiều message liên tiếp | Không mất message và thứ tự đúng theo contract |
| Client đóng bình thường | receive kết thúc và handler cleanup chạy |
| Client ngắt mạng đột ngột | error/cancel được xử lý, session registry được dọn |
| Service xử lý message phát error | Lỗi được truyền hoặc chuyển thành error message theo policy |
| Outbound publisher hoàn tất | Handler áp dụng đúng chính sách đóng hoặc tiếp tục nhận |
| Outbound publisher phát vô hạn | Connection close làm luồng outbound được cancel |
| Client đọc chậm | Queue có giới hạn và memory không tăng vô hạn |
| Message quá lớn | Server từ chối theo giới hạn đã cấu hình |
| Message binary gửi vào endpoint text | Endpoint từ chối hoặc xử lý theo protocol rõ ràng |
| Handler bị cancel | Tác vụ downstream và tài nguyên được cleanup |
| Server chủ động close | Client nhận close frame/status theo contract |

Dùng `WebSocketClient` để integration test qua connector thực tế. Test bằng một Flux giả có thể xác nhận operator logic, nhưng không tái hiện đầy đủ handshake, close frame, network disconnect hoặc behavior của Netty.

## 16. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi receive().subscribe() bên trong handle | Handler kết thúc trước inbound task | Trả publisher hoặc compose vào Mono<Void> |
| Chỉ gọi receive mà quên then/send | Không phản ánh lifecycle session | Trả Mono<Void> từ luồng xử lý |
| Gọi send nhiều lần từ nhiều nguồn | Khó kiểm soát thứ tự và concurrent writer | Hợp nhất nguồn rồi gọi một send |
| Dùng doOnNext để chạy service reactive | Không chờ tác vụ, lỗi không được compose | Dùng concatMap/flatMap |
| Dùng flatMap cho message phụ thuộc thứ tự | Reply có thể đảo thứ tự | Dùng concatMap hoặc flatMapSequential |
| Dùng collectList trên stream dài vô hạn | Tích lũy vô hạn trong memory | Xử lý streaming theo từng message |
| Buffer outbound không giới hạn | Client chậm làm memory tăng | Queue hữu hạn và overflow policy |
| Gọi block trong handler | Chặn event loop | Compose Mono/Flux |
| Giữ WebSocketMessage cho tác vụ async mà không retain | Payload có thể đã release trước khi đọc | retain trước, release trong doFinally |
| Retain nhưng quên release | Leak pooled buffer | Cân bằng retain/release |
| Release message trước khi send ghi xong | Writer có thể đọc buffer đã release | Chuyển ownership đúng contract |
| Gọi session.close() rồi bỏ qua Mono | Close operation không nằm trong lifecycle | Compose close publisher |
| Poll isOpen() trong vòng lặp | Race condition và code phức tạp | Dùng complete/error/cancel signal |
| Nuốt mọi error bằng onErrorResume | Không phát hiện lỗi giao thức hoặc hệ thống | Chỉ fallback lỗi có thể phục hồi |
| Dùng một publisher infinite nhưng không nối với receive lifecycle | Session có thể giữ tài nguyên sau disconnect | Compose hai nhánh và xác định cancellation |
| Dùng Mono.zip cho Mono<Void> | Zip không có giá trị để ghép | Dùng and/when/firstWithSignal |
| Không giới hạn payload | Tốn memory và dễ bị DoS | Cấu hình giới hạn frame/message phù hợp |
| Log toàn bộ payload | Có thể lộ dữ liệu nhạy cảm | Log metadata và payload đã redact |

## 17. Checklist thiết kế WebSocket hai chiều

- [ ] `handle(session)` trả `Mono<Void>` đại diện lifecycle xử lý session.
- [ ] Chỉ có một pipeline inbound owner cho `session.receive()`.
- [ ] Outbound messages đi qua một publisher và một lời gọi `session.send()`.
- [ ] Inbound và outbound được compose rõ ràng.
- [ ] Quy tắc complete/error/cancel được xác định cho từng nhánh.
- [ ] Dùng concatMap khi thứ tự xử lý message quan trọng.
- [ ] Dùng flatMap với concurrency có giới hạn khi message độc lập.
- [ ] Có backpressure và giới hạn queue outbound.
- [ ] Xác định protocol text/binary/control message.
- [ ] Payload DataBuffer được retain/release đúng khi xử lý bất đồng bộ.
- [ ] Không block event loop.
- [ ] Close publisher được compose vào flow.
- [ ] Cleanup registry/resource chạy khi complete, error và cancel.
- [ ] Có timeout/idle policy và heartbeat phù hợp nếu cần.
- [ ] Có authentication, authorization và origin policy cho handshake.
- [ ] Test handshake, echo, inbound/outbound đồng thời, disconnect và slow consumer.
- [ ] Có metric số session, message rate, send latency, queue depth và close reason.

## 18. Tự kiểm tra

**Câu 1.** `session.receive()` trả kiểu gì?

`Flux<WebSocketMessage>`, đại diện cho luồng message đi vào.

**Câu 2.** `session.send(...)` trả kiểu gì?

`Mono<Void>`, hoàn tất khi nguồn outbound hoàn tất và việc ghi message xong.

**Câu 3.** Vì sao handle phải trả Mono<Void>?

Để framework biết khi nào ứng dụng đã hoàn tất xử lý session và phối hợp lifecycle, error, cancellation.

**Câu 4.** Làm sao echo message trong WebFlux?

Map từng message từ `session.receive()` thành một WebSocketMessage mới rồi đưa Flux đó vào `session.send()`.

**Câu 5.** Khi cần gọi service reactive cho từng message và giữ thứ tự thì dùng operator nào?

`concatMap`, vì nó chờ inner publisher hiện tại hoàn tất trước khi xử lý message kế tiếp.

**Câu 6.** Khi nào dùng flatMap?

Khi message độc lập có thể xử lý đồng thời; cần giới hạn concurrency và chấp nhận hoặc xử lý thứ tự output.

**Câu 7.** Làm sao gửi notification độc lập với inbound?

Tạo một publisher outbound riêng, gọi session.send cho publisher đó, rồi compose Mono<Void> của inbound và outbound.

**Câu 8.** `Mono.and` và `Mono.firstWithSignal` khác nhau thế nào?

`and` ghép termination của hai nguồn; `firstWithSignal` kết thúc theo signal đầu tiên và cancel nguồn còn lại.

**Câu 9.** Vì sao không dùng Mono.zip cho hai Mono<Void>?

Hai Mono<Void> hoàn tất rỗng, không phát giá trị để zip tạo tuple. Dùng operator phối hợp completion như and hoặc when.

**Câu 10.** Khi nào cần `message.retain()`?

Khi giữ payload pooled qua callback nhận message để một tác vụ bất đồng bộ tiếp tục đọc sau đó.

**Câu 11.** Sau retain phải làm gì?

Release đúng reference bổ sung khi tác vụ hoàn tất, lỗi hoặc bị cancel.

**Câu 12.** `session.closeStatus()` có luôn phát một giá trị không?

Không. Nó có thể hoàn tất rỗng nếu session kết thúc mà không có close status.

**Câu 13.** Vì sao không nên dùng onBackpressureBuffer vô hạn?

Client chậm có thể khiến outbound queue tăng không giới hạn và tiêu thụ hết bộ nhớ.

**Câu 14.** `doFinally` phù hợp cho việc gì?

Quan sát complete/error/cancel và cleanup đồng bộ nhẹ. Cleanup bất đồng bộ cần được compose nếu phải chờ hoàn tất.

## 19. Tài liệu tham khảo chính thức

- [Spring Framework — WebSockets trên WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html): WebSocketHandler, receive/send, compose lifecycle, client và server.
- [WebSocketSession JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/WebSocketSession.html): receive, send, close, closeStatus, message factories và session metadata.
- [WebSocketMessage JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/WebSocketMessage.html): type, payload, getPayloadAsText, retain và release.
- [WebSocketHandler JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/WebSocketHandler.html): contract của handle và sub-protocol.
- [WebSocketClient JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/client/WebSocketClient.html): execute handshake và lifecycle handler phía client.
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): pooled DataBuffer, reference counting và cleanup.
- [Reactor Core — Mono JavaDoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): and, when, firstWithSignal, doFinally và cancellation.
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html): handshake, full-duplex framing, control frames và close handshake.

**Ghi nhớ:** `receive()` là luồng inbound, `send()` là luồng outbound và `handle` phải trả một Mono<Void> điều khiển vòng đời kết nối. Có thể dẫn outbound từ inbound để echo hoặc chạy hai publisher độc lập rồi compose chúng. Dùng operator phù hợp với chính sách kết thúc, giữ backpressure, tránh nhiều writer, và retain/release payload đúng cách khi xử lý bất đồng bộ. Khi session đóng hoặc bị cancel, mọi nhánh và tài nguyên phụ phải được kết thúc theo cùng lifecycle.