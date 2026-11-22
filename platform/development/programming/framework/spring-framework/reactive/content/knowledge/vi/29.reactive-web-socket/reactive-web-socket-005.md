# Xử lý text, binary và payload dùng bộ đệm trong Spring WebFlux WebSocket

## 1. Mục tiêu: xử lý message hai chiều mà không làm rò rỉ bộ nhớ

WebSocket tạo một kết nối hai chiều lâu dài giữa client và server. Sau HTTP handshake, cả hai bên có thể chủ động gửi message qua cùng một kết nối. Spring WebFlux cung cấp API reactive để xử lý kết nối đó thông qua `WebSocketHandler`, `WebSocketSession` và `WebSocketMessage`.

Mỗi WebSocket message có một kiểu payload chính:

- **Text**: dữ liệu văn bản, thường là JSON, command hoặc event.
- **Binary**: dữ liệu byte thô, thường là ảnh, audio, file chunk hoặc payload đã serialize.
- **Ping/Pong**: control message phục vụ kiểm tra kết nối và keep-alive.

Trong WebFlux, payload được biểu diễn bằng `DataBuffer`. Trên Reactor Netty, buffer thường được pool và reference-counted. Nếu giữ buffer sau khi callback hiện tại kết thúc mà không retain, dữ liệu có thể đã bị release khi code bất đồng bộ tiếp tục đọc. Ngược lại, retain mà quên release có thể gây memory leak.

Bài học này tập trung vào:

1. Vòng đời WebSocket handshake và reactive session.
2. Cách nhận và gửi text/binary message.
3. Phân biệt `WebSocketMessage`, frame, payload và `DataBuffer`.
4. Chuyển text thành DTO và xử lý byte payload.
5. Quản lý ownership bằng `retain()` và `release()`.
6. Dùng `concatMap`, `flatMap` và backpressure để xử lý luồng message.
7. Giới hạn kích thước, chia payload lớn thành chunk và xử lý lỗi.
8. Đóng session đúng cách, xử lý Ping/Pong và transport errors.
9. Kiểm thử server bằng `ReactorNettyWebSocketClient`.
10. Xây dựng dự án Java 17+ Spring Boot có thể chạy bằng Maven.

## 2. WebSocket hoạt động như thế nào?

WebSocket bắt đầu bằng một HTTP request yêu cầu nâng cấp kết nối. Nếu server chấp nhận, hai bên chuyển từ HTTP request/response sang giao thức WebSocket trên cùng kết nối TCP.

Ví dụ handshake rút gọn:

```http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
```

Server phản hồi `101 Switching Protocols` khi chấp nhận upgrade. Sau đó client và server có thể gửi message độc lập theo cả hai hướng.

```text
HTTP handshake
      |
      v
101 Switching Protocols
      |
      v
WebSocket connection
      |
      +------ Client -> Text message ------> Server
      |
      +<----- Binary message <------------- Server
      |
      +------ Client -> Ping --------------> Server
      |
      +<----- Pong ------------------------- Server
      |
      v
Close handshake
```

WebSocket khác HTTP polling ở chỗ không phải tạo một HTTP request mới cho mỗi message. Kết nối được giữ mở để trao đổi nhiều message, vì vậy server cần quản lý session, tài nguyên, timeout, cancellation và số lượng kết nối đồng thời.

WebSocket không tự định nghĩa schema nghiệp vụ. Ứng dụng phải quy định text JSON có field nào, binary payload là định dạng gì, message nào hợp lệ và lỗi nào dẫn tới đóng kết nối.

## 3. Reactive WebSocket API của Spring

Các abstraction quan trọng nằm trong package:

```java
org.springframework.web.reactive.socket
```

### 3.1. `WebSocketHandler`

Server implement `WebSocketHandler` và xử lý một session:

```java
public interface WebSocketHandler {
    Mono<Void> handle(WebSocketSession session);
}
```

`handle` trả `Mono<Void>` đại diện cho toàn bộ vòng đời xử lý session. Publisher này phải compose các luồng inbound và outbound. Không gọi `subscribe()` hoặc `block()` bên trong handler để tự chạy một luồng tách rời.

### 3.2. `WebSocketSession`

`WebSocketSession` đại diện cho một kết nối WebSocket đã handshake. Các API chính:

| API | Vai trò |
|---|---|
| `receive()` | Trả `Flux<WebSocketMessage>` chứa message inbound; hoàn tất khi kết nối đóng |
| `send(Publisher<WebSocketMessage>)` | Gửi publisher message outbound và trả `Mono<Void>` khi gửi xong |
| `textMessage(String)` | Tạo text message dùng buffer factory của session |
| `binaryMessage(Function<DataBufferFactory, DataBuffer>)` | Tạo binary message |
| `pingMessage(...)` | Tạo Ping control message |
| `pongMessage(...)` | Tạo Pong control message |
| `close()` | Đóng session với close status bình thường |
| `close(CloseStatus)` | Đóng session với status cụ thể |
| `closeStatus()` | Theo dõi close status khi kết nối kết thúc |
| `getId()` | Lấy session ID |
| `getHandshakeInfo()` | Đọc metadata của handshake |
| `getAttributes()` | Đọc session attributes |
| `bufferFactory()` | Lấy factory tạo `DataBuffer` cho session |

### 3.3. `WebSocketMessage`

`WebSocketMessage` chứa loại message và payload:

```java
WebSocketMessage.Type type = message.getType();
DataBuffer payload = message.getPayload();
```

Các kiểu phổ biến:

| `WebSocketMessage.Type` | Ý nghĩa |
|---|---|
| `TEXT` | Text message |
| `BINARY` | Binary message |
| `PING` | Ping control message |
| `PONG` | Pong control message |

`getPayloadAsText()` giải mã payload thành String bằng UTF-8. `getPayloadAsText(Charset)` cho phép chỉ định charset khi payload thực sự được quy ước theo charset đó.

Với binary, dùng `getPayload()` và xử lý byte trực tiếp. Không gọi `getPayloadAsText()` trên dữ liệu nhị phân tùy ý vì byte không nhất thiết là văn bản hợp lệ.

## 4. Inbound và outbound là hai reactive stream

`session.receive()` và `session.send(...)` là hai hướng truyền độc lập:

```text
Client messages
      |
      v
session.receive()
      |
      v
Flux<WebSocketMessage>
      |
      v
Application processing
      |
      v
Flux<WebSocketMessage>
      |
      v
session.send(...)
      |
      v
Client receives messages
```

Một handler đơn giản chỉ nhận dữ liệu:

```java
@Override
public Mono<Void> handle(WebSocketSession session) {
    return session.receive()
            .doOnNext(message ->
                    log.debug("Received type={}", message.getType()))
            .then();
}
```

`then()` chuyển `Flux` thành `Mono<Void>` hoàn tất khi luồng inbound kết thúc. Ví dụ này không gửi response.

### 4.1. Echo text message

```java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> replies = session.receive()
            .filter(message ->
                    message.getType() == WebSocketMessage.Type.TEXT)
            .map(message ->
                    session.textMessage(
                            "echo: " + message.getPayloadAsText()));

    return session.send(replies);
}
```

Với mỗi text message nhận được, handler tạo một text message mới và gửi lại. `session.send` tiêu thụ publisher outbound; publisher vẫn hoạt động khi inbound tiếp tục phát message.

### 4.2. Ghép luồng inbound và outbound độc lập

Một ứng dụng có thể nhận command đồng thời phát notification từ một nguồn khác. Khi đó cần compose cả hai publisher vào vòng đời session:

```java
Mono<Void> inbound = session.receive()
        .concatMap(this::processInbound)
        .then();

Mono<Void> outbound = session.send(
        notificationPublisher.map(session::textMessage));

return inbound.and(outbound);
```

Ví dụ trên phù hợp khi hai luồng có lifecycle được phối hợp. Nếu `notificationPublisher` là stream vô hạn, phải thiết kế rõ cách hủy outbound khi client đóng kết nối; không để một publisher vô hạn khiến vòng đời handler tiếp tục giữ tài nguyên sau khi inbound đã kết thúc.

Không tạo một `subscribe()` riêng cho notification stream. Nếu làm vậy, publisher có thể tiếp tục chạy sau khi session đã đóng và lỗi/cancellation không được truyền đúng qua lifecycle của handler.

## 5. Xử lý text payload

Text WebSocket message thường chứa JSON, command hoặc event. `getPayloadAsText()` trả String UTF-8:

```java
String json = message.getPayloadAsText();
```

WebSocket text payload không tự động được Spring MVC/WebFlux deserialize thành DTO như `@RequestBody`. Handler cần chủ động parse theo schema ứng dụng.

Ví dụ DTO:

```java
public record ChatCommand(
        String type,
        String text,
        String requestId) {
}
```

Dùng Jackson `ObjectMapper` để decode:

```java
private final ObjectMapper objectMapper;

private ChatCommand decodeText(WebSocketMessage message) {
    if (message.getType() != WebSocketMessage.Type.TEXT) {
        throw new IllegalArgumentException("Expected text message");
    }

    try {
        return objectMapper.readValue(
                message.getPayloadAsText(),
                ChatCommand.class);
    }
    catch (JsonProcessingException error) {
        throw new IllegalArgumentException(
                "Invalid WebSocket JSON message", error);
    }
}
```

Trong một reactive handler, có thể parse và gọi service:

```java
return session.receive()
        .filter(message ->
                message.getType() == WebSocketMessage.Type.TEXT)
        .concatMap(message -> {
            ChatCommand command = decodeText(message);

            return chatService.handle(command)
                    .map(result ->
                            session.textMessage(
                                    objectMapper.writeValueAsString(result)));
        })
        .as(session::send);
```

Đoạn minh họa trên giả định `writeValueAsString` được bọc thành một helper có xử lý `JsonProcessingException`; không để checked exception lọt trực tiếp vào lambda `map`.

Với JSON nhỏ, decode đồng bộ ngay khi nhận message thường đơn giản. Nếu payload lớn hoặc parse tốn CPU, giới hạn kích thước và cân nhắc đưa công việc CPU-heavy sang scheduler phù hợp. Không chuyển một buffer pooled sang tác vụ bất đồng bộ mà quên retain.

### 5.1. Validate schema và loại command

Không nên chỉ kiểm tra JSON parse thành công. Cần kiểm tra:

- `type` có nằm trong danh sách command được phép không?
- Field bắt buộc có tồn tại không?
- Độ dài text có giới hạn không?
- `requestId` có đúng định dạng không?
- User hiện tại có quyền thực hiện command không?
- Có chống replay hoặc duplicate request khi nghiệp vụ yêu cầu không?

JSON hợp lệ về cú pháp vẫn có thể sai schema hoặc không được phép về nghiệp vụ.

## 6. Xử lý binary payload

Binary message chứa byte thô. Spring không tự chuyển bytes thành ảnh, file, protobuf hay object. Ứng dụng phải biết contract của payload.

Ví dụ binary có thể chứa:

- JPEG/PNG hoặc dữ liệu media.
- File chunk.
- Protobuf/Avro.
- Mảng byte do ứng dụng serialize.
- Dữ liệu nén hoặc mã hóa.

Đọc payload:

```java
DataBuffer payload = message.getPayload();
int byteCount = payload.readableByteCount();
```

Sao chép thành `byte[]` khi payload nhỏ và cần một bản sao độc lập:

```java
private static byte[] copyBytes(DataBuffer buffer) {
    byte[] bytes = new byte[buffer.readableByteCount()];
    buffer.read(bytes);
    return bytes;
}
```

`read(bytes)` tiến read position của `DataBuffer`. Nếu nhiều thành phần cần đọc cùng payload, hãy tạo bản sao hoặc thiết kế rõ quyền sở hữu và vị trí đọc.

### 6.1. Tạo binary message outbound

Dùng `WebSocketSession.binaryMessage(...)`:

```java
byte[] bytes = new byte[] {0, 1, 2, 3, (byte) 0xFF};

WebSocketMessage response = session.binaryMessage(
        factory -> factory.wrap(bytes));
```

`factory` là `DataBufferFactory` của session. Cách này tạo buffer outbound từ byte array đã có.

### 6.2. Echo binary payload

```java
private WebSocketMessage echoBinary(
        WebSocketSession session,
        WebSocketMessage inbound) {

    byte[] copy = copyBytes(inbound.getPayload());

    return session.binaryMessage(
            factory -> factory.wrap(copy));
}
```

Bản sao byte được tạo đồng bộ trong lúc xử lý inbound event. Lambda tạo outbound buffer chỉ tham chiếu tới byte array độc lập, không đọc lại `DataBuffer` inbound có thể đã được release trước thời điểm gửi.

### 6.3. Không chuyển binary thành String tùy tiện

Không dùng:

```java
String text = new String(bytes, StandardCharsets.UTF_8);
```

trừ khi protocol của ứng dụng xác định bytes đó là UTF-8 text. Binary có thể chứa byte không hợp lệ theo charset, dữ liệu nén hoặc cấu trúc có offset. Việc chuyển sang String có thể làm mất dữ liệu hoặc tạo nội dung không thể khôi phục.

## 7. `DataBuffer`: payload là vùng byte có vòng đời

`DataBuffer` là abstraction của Spring cho dữ liệu byte. Nó có thể bọc `ByteBuffer`, Netty `ByteBuf` hoặc implementation khác.

Một số connector như Reactor Netty sử dụng pooled buffer và reference counting:

```text
Inbound WebSocketMessage
        |
        v
DataBuffer (pooled)
        |
        +---- đọc đồng bộ / copy byte
        |             |
        |             v
        |        xử lý xong
        |
        +---- giữ qua async boundary
                      |
                      v
                  retain()
                      |
                      v
              async processing
                      |
                      v
                  release()
```

Điều cần hiểu là payload không phải lúc nào cũng là một `byte[]` do ứng dụng sở hữu. Buffer có thể được tái sử dụng sau khi framework/connector kết thúc xử lý message.

### 7.1. Đọc đồng bộ trong callback

Ví dụ:

```java
session.receive()
        .map(message -> {
            String text = message.getPayloadAsText();
            return session.textMessage("echo:" + text);
        });
```

Việc đọc text được thực hiện đồng bộ ngay trong callback `map`, sau đó tạo message outbound mới. Không giữ tham chiếu tới inbound buffer để đọc ở thời điểm khác.

Tương tự, copy binary thành `byte[]` ngay trong callback nếu cần giữ dữ liệu sau callback.

### 7.2. Giữ message qua nested asynchronous operation

Nếu cần sử dụng inbound message trong một publisher bất đồng bộ lồng bên trong, gọi `retain()` trước khi message có thể được release:

```java
return session.receive()
        .concatMap(message -> {
            message.retain();

            return binaryService.store(message.getPayload())
                    .doFinally(signal -> message.release());
        })
        .then();
```

Trong ví dụ, service phải hoàn tất việc đọc/ghi buffer trước khi publisher kết thúc. `doFinally` giải phóng reference đã retain khi publisher complete, error hoặc cancel.

Quy tắc:

1. Chỉ retain khi cần giữ buffer vượt qua callback hiện tại.
2. Release đúng một lần cho mỗi lần retain.
3. Release trong đường complete, error và cancellation.
4. Không release khi downstream vẫn còn đang sử dụng buffer.
5. Không giữ buffer pooled trong collection/cache lâu dài nếu không có ownership policy rõ ràng.

### 7.3. Dùng `DataBufferUtils` trực tiếp

`WebSocketMessage.retain()` và `release()` là shortcut cho thao tác trên payload:

```java
DataBufferUtils.retain(message.getPayload());

// Sau khi sử dụng xong:
DataBufferUtils.release(message.getPayload());
```

Chỉ dùng một cách quản lý ownership nhất quán. Không vừa gọi `message.retain()` vừa retain cùng payload lần nữa nếu không có lý do và không cân bằng đủ số lần release.

### 7.4. Tránh memory leak và double release

Các lỗi thường gặp:

- Lưu `DataBuffer` vào field rồi đọc sau khi receive callback kết thúc.
- Đưa payload vào `Mono.delay`, `publishOn` hoặc callback bất đồng bộ mà không retain.
- Retain buffer nhưng không release khi exception.
- Release buffer trước khi async service đọc xong.
- Release hai lần cùng một reference.
- Chuyển payload vào queue không giới hạn và giữ connection/session mở lâu dài.

Nếu ứng dụng chỉ cần dữ liệu nhỏ để xử lý sau, copy sang `byte[]` hoặc immutable DTO thường dễ quản lý hơn. Với file/binary lớn, nên stream tới storage với ownership rõ ràng và giới hạn bộ nhớ.

## 8. Backpressure và xử lý tuần tự

WebSocket có thể gửi message liên tục. Reactive Streams giúp điều tiết demand, nhưng ứng dụng vẫn có thể tự tạo hàng đợi lớn nếu xử lý không giới hạn.

### 8.1. `concatMap`: giữ thứ tự và xử lý tuần tự

```java
return session.receive()
        .concatMap(message ->
                messageService.process(message))
        .then();
```

`concatMap` chờ publisher của message hiện tại hoàn tất rồi mới xử lý message kế tiếp. Đây là lựa chọn tốt khi:

- Thứ tự message có ý nghĩa.
- Mỗi message cập nhật cùng một trạng thái.
- Không muốn nhiều tác vụ cùng ghi vào một session state.
- Downstream xử lý có thời gian hoàn tất rõ ràng.

### 8.2. `flatMap`: xử lý đồng thời có giới hạn

```java
return session.receive()
        .flatMap(
                message -> messageService.process(message),
                8)
        .then();
```

Concurrency `8` cho phép tối đa một số tác vụ cùng chạy. Kết quả có thể hoàn tất khác thứ tự nhận message. Chỉ dùng khi nghiệp vụ cho phép và downstream có thể xử lý đồng thời.

Không dùng concurrency vô hạn cho một stream có thể kéo dài. Nếu mỗi message giữ buffer, concurrency cao sẽ làm tăng số buffer sống cùng lúc.

### 8.3. Cẩn thận với queue và buffer operator

Các operator như `onBackpressureBuffer`, `publishOn`, `flatMap` có prefetch, `cache` hoặc queue tự tạo có thể giữ thêm message/buffer.

Nếu dùng queue, cần đặt:

- Dung lượng tối đa.
- Chính sách khi queue đầy.
- Timeout hoặc drop policy phù hợp.
- Cách release payload của message bị loại bỏ.
- Metrics về queue depth và thời gian chờ.

Không dùng `onBackpressureBuffer()` không giới hạn để che việc producer nhanh hơn consumer. Với WebSocket, queue tăng vô hạn có thể làm heap tăng đến khi ứng dụng không còn hoạt động.

## 9. Payload lớn và chia thành chunk

Một WebSocket message có thể chứa payload lớn. Nếu ứng dụng copy toàn bộ message thành `byte[]`, heap sẽ phải giữ bản sao có kích thước tương ứng, chưa kể buffer gốc và các object khác.

Đối với file hoặc media lớn, hãy thiết kế application-level chunking:

```text
Message 1: metadata {transferId, fileName, totalBytes}
Message 2: binary chunk {transferId, sequence=0}
Message 3: binary chunk {transferId, sequence=1}
Message 4: binary chunk {transferId, sequence=2}
Message 5: completion {transferId, checksum}
```

Một protocol chunk nên có:

- Transfer/session ID.
- Sequence number.
- Tổng số byte hoặc total chunks nếu biết trước.
- Cờ kết thúc hoặc message loại completion.
- Checksum/hash để kiểm tra dữ liệu.
- ACK hoặc window khi cần giới hạn lượng dữ liệu đang chờ.
- Timeout và cơ chế hủy transfer.
- Chính sách resume/retry nếu nghiệp vụ yêu cầu.

### 9.1. Fragmentation của WebSocket khác chunk của ứng dụng

WebSocket protocol có thể chia một logical message thành nhiều frame ở tầng giao thức. Frame boundaries không phải ranh giới nghiệp vụ và không nên được dùng làm sequence number của file transfer.

Application-level chunking tạo nhiều WebSocket message độc lập với metadata riêng. Cách này cho phép ứng dụng kiểm soát thứ tự, ACK, resume, giới hạn kích thước và lưu trữ từng phần.

Không giả định một TCP packet tương ứng một WebSocket message hoặc một frame. TCP segmentation và WebSocket framing là các tầng khác nhau.

### 9.2. Giới hạn kích thước message

Nên giới hạn cả:

- Kích thước text message.
- Kích thước binary message.
- Kích thước JSON sau decode.
- Số message mỗi giây.
- Tổng byte đang xử lý của một session.
- Tổng số session và transfer đồng thời.

Kiểm tra `message.getPayload().readableByteCount()` cho biết số byte payload mà ứng dụng đang nhận được. Tuy nhiên, kiểm tra ở handler diễn ra sau khi connector đã nhận/assemble message. Nếu connector/server có cấu hình giới hạn frame hoặc message, hãy đặt giới hạn ở tầng đó nữa để từ chối payload lớn sớm hơn.

Không dùng `String.length()` làm giới hạn byte. Một ký tự Unicode có thể chiếm nhiều byte UTF-8.

## 10. Ping, Pong và giữ kết nối

WebSocket định nghĩa control frame Ping và Pong. Ping có thể dùng để kiểm tra peer còn hoạt động; Pong là phản hồi tương ứng.

Spring biểu diễn chúng bằng:

```java
WebSocketMessage.Type.PING
WebSocketMessage.Type.PONG
```

`WebSocketSession` có factory:

```java
session.pingMessage(factory -> factory.wrap(payload));
session.pongMessage(factory -> factory.wrap(payload));
```

Các connector có thể tự xử lý một phần control frame. Nếu ứng dụng cần xử lý Ping/Pong ở tầng handler, hãy xác minh hành vi của connector đang dùng để tránh gửi phản hồi trùng.

Ping/Pong không phải application data. Không parse payload Ping như JSON command hoặc lưu vào file binary transfer.

Đối với session lâu dài:

- Đặt heartbeat interval hợp lý.
- Timeout session khi không nhận heartbeat theo contract.
- Xử lý client disconnect/cancel.
- Không giữ tài nguyên database/file khi session đã đóng.
- Không gửi heartbeat nhanh tới mức gây tải lớn.

## 11. Đóng session và xử lý lỗi

`WebSocketSession.close()` đóng session với status bình thường. Có thể truyền `CloseStatus` để mô tả lý do:

```java
return session.close(CloseStatus.NORMAL);
```

Một số close code chuẩn của WebSocket:

| Code | Ý nghĩa |
|---:|---|
| 1000 | Normal Closure |
| 1001 | Going Away |
| 1002 | Protocol Error |
| 1003 | Unsupported Data |
| 1007 | Invalid Payload Data |
| 1008 | Policy Violation |
| 1009 | Message Too Big |
| 1011 | Internal Server Error |

Ví dụ đóng vì payload vượt giới hạn:

```java
CloseStatus tooLarge = new CloseStatus(
        1009,
        "Message exceeds application limit");

return session.close(tooLarge);
```

Close reason nên ngắn, không chứa stack trace, secret hoặc thông tin nội bộ.

### 11.1. Lỗi trong reactive handler

Nếu xử lý message phát error, publisher `handle` có thể kết thúc bằng error và connector đóng session theo lifecycle của server. Có thể log lỗi có kiểm soát hoặc map lỗi nghiệp vụ trước khi kết thúc.

```java
return session.receive()
        .concatMap(this::processMessage)
        .then()
        .doOnError(error ->
                log.warn("WebSocket session processing failed: {}",
                        error.getClass().getSimpleName()));
```

Không nuốt mọi exception bằng `onErrorResume(error -> Mono.empty())` nếu điều đó khiến client nghĩ message đã được xử lý thành công. Hãy xác định lỗi nào có thể phục hồi, lỗi nào cần gửi error message và lỗi nào cần đóng session.

### 11.2. Phân biệt lỗi application và transport

| Nhóm | Ví dụ | Xử lý |
|---|---|---|
| Payload/schema | JSON sai, command thiếu field | Gửi error event hoặc close theo policy |
| Binary format | Header file không hợp lệ, checksum sai | Từ chối transfer và giải phóng buffer |
| Policy | Message quá lớn, user không có quyền | Close status phù hợp hoặc error response |
| Transport | TCP reset, network disconnect | Dọn tài nguyên và kết thúc session |
| Timeout | Client không gửi dữ liệu trong deadline | Close session và giải phóng state |
| Internal error | Database/storage thất bại | Log correlation ID, trả lỗi an toàn hoặc close |

## 12. Bảo mật WebSocket

WebSocket không bỏ qua security chỉ vì handshake ban đầu là HTTP. Cần bảo vệ cả handshake lẫn message sau khi kết nối.

- Xác thực người dùng trước hoặc trong handshake bằng cơ chế Spring Security.
- Giới hạn Origin theo ứng dụng browser-facing; không coi `Origin` là cơ chế authentication.
- Phân quyền theo từng message/command, không chỉ kiểm tra lúc kết nối.
- Giới hạn kích thước text/binary và số message mỗi giây.
- Validate JSON schema và binary file signature.
- Đặt quota cho số session, số transfer và tổng dung lượng.
- Đóng session khi token/session hết hạn hoặc quyền bị thu hồi theo policy.
- Không log access token, cookie, raw binary hoặc nội dung chat nhạy cảm.
- Dùng `wss://` trong môi trường production qua TLS.
- Xử lý reconnect và duplicate message bằng request ID/idempotency khi nghiệp vụ yêu cầu.

Một kết nối WebSocket kéo dài có thể sống lâu hơn thời hạn access token ban đầu. Ứng dụng phải xác định policy re-authentication, token expiry và session termination.

## 13. Đăng ký WebSocket endpoint trong Spring Boot WebFlux

Có thể map `WebSocketHandler` vào URL bằng `SimpleUrlHandlerMapping`.

```java
@Configuration
public class WebSocketConfiguration {

    @Bean
    public HandlerMapping webSocketMapping(
            EchoWebSocketHandler handler) {

        Map<String, WebSocketHandler> handlers = new HashMap<>();
        handlers.put("/ws/echo", handler);

        SimpleUrlHandlerMapping mapping =
                new SimpleUrlHandlerMapping();

        mapping.setUrlMap(handlers);
        mapping.setOrder(-1);

        return mapping;
    }
}
```

`order = -1` đặt WebSocket mapping trước annotated controller mapping. Khi dùng Spring WebFlux Java configuration hoặc Spring Boot WebFlux auto-configuration, `WebSocketHandlerAdapter` được cung cấp bởi hạ tầng WebFlux; không cần tự tạo adapter trừ khi ứng dụng không dùng cấu hình WebFlux tương ứng.

Không nhầm reactive `WebSocketHandler` với Servlet `WebSocketHandler`. Hai stack có API và session type khác nhau.

## 14. Dự án Java 17+ chạy được: echo text và binary

Dự án dưới đây sử dụng:

- Java 17.
- Spring Boot 3.3.5.
- Spring WebFlux và Reactor Netty.
- JUnit 5.
- `ReactorNettyWebSocketClient` để kiểm thử kết nối thật tới server cục bộ.

Server nhận text hoặc binary, thêm prefix cho text và echo nguyên bytes của binary. Binary được copy đồng bộ sang `byte[]` trước khi tạo outbound message, vì vậy code không giữ inbound pooled `DataBuffer` qua thời điểm xử lý callback.

### 14.1. Cấu trúc

```text
webflux-websocket-payload/
├── pom.xml
└── src/
    ├── main/java/edu/demo/ws/
    │   ├── WebSocketApplication.java
    │   ├── EchoWebSocketHandler.java
    │   └── WebSocketConfiguration.java
    └── test/java/edu/demo/ws/
        └── WebSocketIntegrationTests.java
```

### 14.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webflux-websocket-payload</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
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
```

### 14.3. `WebSocketApplication.java`

```java
package edu.demo.ws;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSocketApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebSocketApplication.class, args);
    }
}
```

### 14.4. `EchoWebSocketHandler.java`

```java
package edu.demo.ws;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.CloseStatus;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Mono;

@Component
public class EchoWebSocketHandler implements WebSocketHandler {

    private static final int MAX_MESSAGE_BYTES = 1024 * 1024;

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.send(
                session.receive()
                        .concatMap(message -> {
                            int size = message.getPayload()
                                    .readableByteCount();

                            if (size > MAX_MESSAGE_BYTES) {
                                return session.close(
                                                new CloseStatus(
                                                        1009,
                                                        "Message too large"))
                                        .then(Mono.<WebSocketMessage>empty());
                            }

                            return switch (message.getType()) {
                                case TEXT -> Mono.just(
                                        session.textMessage(
                                                "echo: "
                                                        + message.getPayloadAsText()));

                                case BINARY -> {
                                    byte[] copy = copyBytes(
                                            message.getPayload());

                                    yield Mono.just(
                                            session.binaryMessage(
                                                    factory -> factory.wrap(copy)));
                                }

                                case PING -> {
                                    byte[] copy = copyBytes(
                                            message.getPayload());

                                    yield Mono.just(
                                            session.pongMessage(
                                                    factory -> factory.wrap(copy)));
                                }

                                case PONG -> Mono.empty();
                            };
                        }));
    }

    private static byte[] copyBytes(DataBuffer buffer) {
        byte[] bytes = new byte[buffer.readableByteCount()];
        buffer.read(bytes);
        return bytes;
    }
}
```

Handler giới hạn mỗi message ở 1 MiB sau khi connector đã đưa message vào ứng dụng. Production nên đặt giới hạn tương ứng ở connector/server để từ chối message quá lớn sớm hơn.

`PING` được trả lời bằng `PONG` nếu control message được chuyển tới handler. Một số connector tự xử lý control frame; kiểm tra hành vi của connector trước khi thêm logic phản hồi thủ công trong ứng dụng thật.

### 14.5. `WebSocketConfiguration.java`

```java
package edu.demo.ws;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;

@Configuration
public class WebSocketConfiguration {

    @Bean
    public HandlerMapping webSocketMapping(
            EchoWebSocketHandler handler) {

        SimpleUrlHandlerMapping mapping =
                new SimpleUrlHandlerMapping();

        mapping.setUrlMap(
                Map.of("/ws/echo", (WebSocketHandler) handler));

        mapping.setOrder(-1);
        return mapping;
    }
}
```

### 14.6. `WebSocketIntegrationTests.java`

```java
package edu.demo.ws;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebSocketIntegrationTests {

    @LocalServerPort
    int port;

    private final WebSocketClient client =
            new ReactorNettyWebSocketClient();

    private URI endpoint() {
        return URI.create("ws://127.0.0.1:" + port + "/ws/echo");
    }

    @Test
    void echoesTextMessage() {
        AtomicReference<String> received = new AtomicReference<>();

        client.execute(endpoint(), session -> {
            Mono<Void> send = session.send(
                    Mono.just(session.textMessage("hello")));

            Mono<Void> receive = session.receive()
                    .take(1)
                    .doOnNext(message -> {
                        assertEquals(
                                WebSocketMessage.Type.TEXT,
                                message.getType());

                        received.set(message.getPayloadAsText());
                    })
                    .then();

            return send.then(receive);
        }).block(Duration.ofSeconds(5));

        assertEquals("echo: hello", received.get());
    }

    @Test
    void echoesBinaryPayloadWithoutChangingBytes() {
        byte[] sent = new byte[] {
                0,
                1,
                2,
                3,
                (byte) 0x80,
                (byte) 0xFF
        };

        AtomicReference<byte[]> received = new AtomicReference<>();

        client.execute(endpoint(), session -> {
            Mono<Void> send = session.send(
                    Mono.just(session.binaryMessage(
                            factory -> factory.wrap(sent))));

            Mono<Void> receive = session.receive()
                    .take(1)
                    .doOnNext(message -> {
                        assertEquals(
                                WebSocketMessage.Type.BINARY,
                                message.getType());

                        received.set(copyBytes(message.getPayload()));
                    })
                    .then();

            return send.then(receive);
        }).block(Duration.ofSeconds(5));

        assertNotNull(received.get());
        assertArrayEquals(sent, received.get());
    }

    @Test
    void preservesOrderForMultipleTextMessages() {
        List<String> received = new CopyOnWriteArrayList<>();

        client.execute(endpoint(), session -> {
            Mono<Void> send = session.send(
                    Flux.just(
                            session.textMessage("first"),
                            session.textMessage("second"),
                            session.textMessage("third")));

            Mono<Void> receive = session.receive()
                    .take(3)
                    .doOnNext(message ->
                            received.add(message.getPayloadAsText()))
                    .then();

            return send.then(receive);
        }).block(Duration.ofSeconds(5));

        assertEquals(
                List.of(
                        "echo: first",
                        "echo: second",
                        "echo: third"),
                received);
    }

    private static byte[] copyBytes(DataBuffer buffer) {
        byte[] bytes = new byte[buffer.readableByteCount()];
        buffer.read(bytes);
        return bytes;
    }
}
```

Test dùng `block(Duration)` ở ranh giới JUnit để chờ WebSocket exchange hoàn tất. Code xử lý session trong ứng dụng vẫn dùng reactive composition.

### 14.7. Chạy dự án

Từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Chạy server:

```bash
mvn spring-boot:run
```

WebSocket endpoint:

```text
ws://localhost:8080/ws/echo
```

Có thể kết nối bằng WebSocket client như `wscat`:

```bash
wscat -c ws://localhost:8080/ws/echo
```

Gửi text:

```text
hello
```

Response:

```text
echo: hello
```

Bộ test có ba trường hợp:

1. Text message được echo với prefix.
2. Binary payload được trả lại với bytes chính xác, gồm cả byte `0x80` và `0xFF`.
3. Nhiều text message được xử lý và trả theo thứ tự.

Kết quả mong đợi sau khi Maven chạy thành công:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

Đây là kết quả mong đợi cần đối chiếu sau khi chạy trong môi trường có Maven/dependencies; tài liệu không tuyên bố test đã được thực thi trong môi trường biên soạn.

## 15. Kết nối tới WebSocket server bằng WebSocketClient

Spring WebFlux cũng cung cấp `WebSocketClient` abstraction. Với Reactor Netty:

```java
WebSocketClient client = new ReactorNettyWebSocketClient();

URI uri = URI.create("wss://stream.example.com/ws");

Mono<Void> connection = client.execute(uri, session ->
        session.receive()
                .doOnNext(message ->
                        log.info("Received type={}", message.getType()))
                .then());
```

`execute` mở handshake, gọi callback với session và trả `Mono<Void>` đại diện cho vòng đời kết nối.

Gửi một message rồi tiếp tục nhận:

```java
Mono<Void> connection = client.execute(uri, session -> {
    Mono<Void> outbound = session.send(
            Mono.just(session.textMessage("{\"type\":\"subscribe\"}")));

    Mono<Void> inbound = session.receive()
            .doOnNext(message -> process(message))
            .then();

    return outbound.then(inbound);
});
```

Với kết nối lâu dài, `inbound` thường chỉ hoàn tất khi server đóng hoặc transport kết thúc. Hãy có timeout, cancellation và policy reconnect phù hợp.

Không tạo một client mới cho mỗi message. Tái sử dụng connector/client theo lifecycle ứng dụng để quản lý connection resources hợp lý.

## 16. Những lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Dùng `getPayloadAsText()` cho binary | Mất hoặc biến dạng dữ liệu | Kiểm tra type và đọc `DataBuffer` thành bytes |
| Nghĩ JSON tự được decode thành DTO | Không có object nghiệp vụ | Parse text theo schema ứng dụng |
| Giữ `DataBuffer` qua async boundary mà không retain | Buffer có thể đã được release | `message.retain()` và release sau khi xử lý |
| Retain nhưng không release | Pooled memory leak | Release trong complete/error/cancel |
| Release trước khi service đọc xong | Buffer có thể không còn hợp lệ | Release sau khi publisher sử dụng hoàn tất |
| Copy file rất lớn vào `byte[]` | Tăng heap và tạo bản sao lớn | Chunk payload và stream tới storage |
| Dùng `flatMap` concurrency không giới hạn | Nhiều buffer/tác vụ cùng tồn tại | Dùng `concatMap` hoặc concurrency hữu hạn |
| Dùng queue không giới hạn | Heap tăng khi consumer chậm | Queue bounded và policy khi đầy |
| Gọi `subscribe()` trong handler | Tách task khỏi session lifecycle | Return và compose `Mono`/`Flux` |
| Gọi `block()` trong event loop | Chặn I/O thread | Compose reactive publisher |
| Cho rằng TCP packet là WebSocket message | Parse sai ranh giới payload | Xử lý `WebSocketMessage`, không dựa vào packet boundary |
| Cho rằng protocol fragmentation là file chunk | Không kiểm soát sequence/resume | Định nghĩa application-level chunk protocol |
| Không giới hạn payload | Client có thể gửi message quá lớn | Giới hạn ở connector và application |
| Dùng `String.length()` để giới hạn byte | Sai với UTF-8 và Unicode | Dùng `readableByteCount()` cho byte payload |
| Không phân biệt Ping/Pong với data | Parse control frame như command | Xử lý control message theo connector/protocol |
| Không xử lý client disconnect | Giữ resource sau khi socket đóng | Dựa vào completion/cancellation để dọn tài nguyên |
| Trả stack trace trong close reason | Rò rỉ nội bộ | Close reason ngắn, an toàn |
| Chỉ xác thực lúc handshake | User có thể mất quyền khi session còn mở | Có policy kiểm tra quyền/token expiry theo session |

## 17. Checklist production

### Message contract

- Text message có schema và version rõ ràng.
- Binary message có định dạng và metadata xác định.
- Có giới hạn text/binary payload.
- Có request ID hoặc sequence number khi cần.
- Có quy tắc xử lý message không hỗ trợ.
- Ping/Pong được xử lý phù hợp với connector.

### Buffer lifecycle

- Đọc/copy buffer đồng bộ khi có thể.
- Nếu giữ buffer qua async boundary, đã retain.
- Mỗi retain có release tương ứng.
- Release được thực hiện khi complete, error và cancel.
- Không lưu pooled buffer trong collection/queue vô thời hạn.
- Binary lớn được chunk hoặc stream thay vì copy toàn bộ vào heap.

### Reactive lifecycle

- Handler trả `Mono<Void>` đại diện cho session.
- Không tự `subscribe()` hoặc `block()` trong handler.
- `concatMap` được dùng khi cần thứ tự.
- `flatMap` có concurrency hữu hạn.
- Outbound publisher dừng khi session kết thúc.
- Queue có giới hạn và policy khi đầy.

### Security và vận hành

- Handshake được xác thực và kiểm tra Origin phù hợp.
- Mỗi message được validate và authorize theo nhu cầu.
- Có rate limit, size limit và session quota.
- Có timeout/heartbeat và reconnect policy.
- Log session ID, message type và correlation ID an toàn.
- Không log raw text/binary nhạy cảm.
- Session cleanup giải phóng resource khi disconnect.
- Metrics theo dõi active sessions, message rate, payload bytes, queue depth và lỗi.

### Testing

- Test text message.
- Test binary message với byte ngoài ASCII.
- Test nhiều message và thứ tự.
- Test empty payload.
- Test message vượt giới hạn.
- Test malformed JSON/schema.
- Test disconnect/cancellation.
- Test retain/release trong custom async processing nếu code giữ buffer.
- Test Ping/Pong theo connector nếu ứng dụng xử lý control frame.

## 18. Bài tập tự kiểm tra

**Bài 1.** `session.receive()` trả kiểu gì?

**Đáp án:** `Flux<WebSocketMessage>`, phát các message inbound và hoàn tất khi kết nối đóng.

**Bài 2.** `session.send(...)` trả kiểu gì?

**Đáp án:** `Mono<Void>`, hoàn tất khi publisher outbound hoàn tất và việc ghi message xong.

**Bài 3.** `getPayloadAsText()` sử dụng charset nào mặc định?

**Đáp án:** UTF-8.

**Bài 4.** Vì sao không dùng `getPayloadAsText()` để đọc ảnh JPEG?

**Đáp án:** JPEG là binary bytes, không phải văn bản UTF-8. Cần đọc `DataBuffer` hoặc copy bytes.

**Bài 5.** Khi nào cần gọi `message.retain()`?

**Đáp án:** Khi giữ inbound payload qua nested asynchronous operation hoặc sau callback hiện tại trên connector dùng pooled buffer, chẳng hạn Netty.

**Bài 6.** Sau khi retain, phải làm gì?

**Đáp án:** Gọi `message.release()` khi xử lý xong, kể cả complete, error hoặc cancel.

**Bài 7.** `concatMap` khác `flatMap` ở điểm nào quan trọng khi xử lý message?

**Đáp án:** `concatMap` xử lý publisher tuần tự và giữ thứ tự; `flatMap` cho phép xử lý đồng thời, có thể hoàn tất khác thứ tự.

**Bài 8.** Vì sao không nên dùng `onBackpressureBuffer()` không giới hạn?

**Đáp án:** Khi producer nhanh hơn consumer, queue tăng vô hạn và có thể làm heap cạn.

**Bài 9.** WebSocket protocol fragmentation có thay thế application-level chunking không?

**Đáp án:** Không. Fragmentation là cách chia frame ở tầng giao thức; chunking của ứng dụng cần sequence, metadata, ACK, checksum và quy tắc resume riêng.

**Bài 10.** Vì sao cần kiểm tra payload size ở connector lẫn handler?

**Đáp án:** Kiểm tra ở handler diễn ra sau khi message đã được nhận/assemble. Giới hạn connector có thể từ chối message lớn sớm hơn; kiểm tra handler bổ sung policy nghiệp vụ.

## 19. Ghi nhớ

- `WebSocketHandler` xử lý một `WebSocketSession` và trả `Mono<Void>` cho toàn bộ lifecycle.
- `receive()` là inbound `Flux<WebSocketMessage>`; `send(Publisher)` là outbound `Mono<Void>`.
- `WebSocketMessage.Type` phân biệt TEXT, BINARY, PING và PONG.
- `getPayloadAsText()` giải mã UTF-8; binary cần đọc `DataBuffer`/bytes.
- `session.textMessage()` và `session.binaryMessage()` tạo outbound message bằng buffer factory của session.
- Trên Netty, `DataBuffer` có thể pooled và reference-counted.
- Nếu giữ inbound message qua async boundary, retain trước và release sau khi sử dụng.
- Copy sang byte array đồng bộ phù hợp với payload nhỏ; file lớn nên được chunk/stream.
- `concatMap` giữ thứ tự; `flatMap` cần concurrency hữu hạn.
- Reactive backpressure không thay thế queue bound, payload size limit hoặc session quota.
- WebSocket fragmentation khác application-level chunk protocol.
- Close status, Ping/Pong, authentication, Origin và message authorization cần được thiết kế rõ.
- Handler phải compose lifecycle reactive; không tự subscribe hoặc block.

Khi xử lý WebSocket payload, hãy xác định theo thứ tự: **message type → payload format → kích thước → ownership của DataBuffer → cách xử lý reactive → cách kết thúc session**. Trình tự này giúp tránh nhầm text với binary và tránh lỗi memory leak khi chuyển xử lý sang bất đồng bộ.

## Tài liệu chính thức

- Spring Framework 6.2, **WebSockets on the Reactive Stack**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-websocket.html
- Spring Framework 6.1, **`WebSocketSession` API**: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/reactive/socket/WebSocketSession.html
- Spring Framework 6.1, **`WebSocketMessage` API**: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/reactive/socket/WebSocketMessage.html
- Spring Framework 6.1, **`WebSocketMessage.Type` API**: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/reactive/socket/WebSocketMessage.Type.html
- Spring Framework 6.2, **Data Buffers and Codecs**: https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html
- Spring Framework 6.2, **WebTestClient**: https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html
- IETF, **RFC 6455 – The WebSocket Protocol**: https://www.rfc-editor.org/rfc/rfc6455