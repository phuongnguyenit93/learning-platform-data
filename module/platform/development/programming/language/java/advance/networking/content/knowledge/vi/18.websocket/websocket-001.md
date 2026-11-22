# WebSocket dùng trong trường hợp nào? Trao đổi hai chiều kéo dài với Java 17+

## 1. Câu trả lời trước: chọn WebSocket khi cả hai phía cần chủ động gửi nhiều lần

**WebSocket** phù hợp khi **client và server phải giữ một phiên kết nối mở lâu hơn một request đơn lẻ**, **cả hai phía có thể chủ động đẩy thông điệp** và ứng dụng cần **phản ứng gần thời gian thực** với lượng trao đổi lặp lại: chat, cộng tác trực tuyến, sự kiện trạng thái liên tục, điều khiển tương tác, bảng giám sát, trò chơi có kênh thông điệp đáng tin cậy hoặc một phiên quản trị/điều phối kéo dài.

Ý nghĩa “hai chiều” không chỉ là “client gửi request, server trả response”. Trên một WebSocket đã mở, **server có thể gửi message mới khi client chưa phát request mới**, và client có thể gửi message bất cứ lúc nào. Cả hai phía **không phải thiết lập HTTP request mới cho mỗi thông điệp**.

~~~text
HTTP request/response truyền thống:

Client            Server
  | --- GET -----> |
  | <--- 200 ----- |
  |                |
  | --- GET -----> |   hỏi lại lần nữa (polling)
  | <--- 200 ----- |

WebSocket:

Client            Server
  | - Upgrade ---> |
  | <--- 101 ----- |   kết nối WebSocket được thiết lập
  | <--- event A - |   server chủ động gửi
  | ---- cmd 1 --> |   client chủ động gửi
  | ---- cmd 2 --> |
  | <--- event B - |
  | <--- ack 2 --- |
  | <--- event C - |
  | -- Close ----> |
  | <--- Close --- |   bắt tay đóng
~~~

**Không phải cứ có cập nhật mới là dùng WebSocket.** Nếu chỉ cần client gọi API một lần, lấy danh sách có thể cache, gửi biểu mẫu, tải file, hoặc nhận sự kiện **một chiều** từ server với cơ chế đơn giản, HTTP thông thường, polling/long-polling hoặc **Server-Sent Events (SSE)** có thể là lựa chọn đúng và dễ vận hành hơn.

Bài học tập trung vào: **dấu hiệu nên/không nên dùng WebSocket**, cách hoạt động của kênh song công kéo dài, khác biệt với REST, polling và SSE; giới hạn về đảm bảo giao nhận, bảo mật, trạng thái, backpressure, heartbeat, reconnect và scale; và một demo **Java 17+** dùng WebSocket client có sẵn trong JDK để kết nối tới server loopback tối giản.

## 2. WebSocket thực sự là gì?

Theo RFC 6455, WebSocket là một giao thức giao tiếp trên **một kết nối hai chiều**, thường dùng TCP làm transport. Bắt đầu bằng **HTTP/1.1 Upgrade handshake**, rồi hai phía chuyển sang trao đổi **WebSocket frames** thay vì mỗi message đều là một HTTP response đầy đủ.

Một số điểm bản chất:

1. **Full-duplex:** client và server có thể truyền dữ liệu **đồng thời** trên cùng phiên; không cần client phải hỏi thì server mới được gửi.
2. **Message-oriented:** WebSocket có **text messages** (UTF-8) và **binary messages**, không chỉ một chuỗi byte vô định hình kiểu TCP thô.
3. **Connection-oriented và stateful ở tầng phiên:** sau handshake, mỗi endpoint giữ socket/phiên, bộ đệm, trạng thái xác thực và những subscriptions liên quan; connection có thể kéo dài từ vài giây tới nhiều giờ tùy điều kiện mạng và ứng dụng.
4. **Thứ tự trên một connection:** vì transport phổ biến là TCP, bytes được truyền có thứ tự, không bị reorder như datagram UDP. Tuy nhiên điều đó **không tạo bảo đảm exactly-once xuyên qua disconnect/reconnect**.
5. **Kênh sự kiện, không phải API RPC tự động:** WebSocket không định nghĩa sẵn “gọi method/nhận status 200”, schema JSON, request ID, ACK hoặc retry. Những quy tắc đó phải được **ứng dụng thiết kế** hoặc dùng protocol/framework phù hợp.

### 2.1. “WebSocket luôn mở” có đúng không?

Không. Một WebSocket *có khả năng* được giữ lâu, nhưng **không có cam kết giữ mãi**. Wi-Fi chuyển mạng, thiết bị ngủ, điện thoại vào background, proxy idle timeout, deploy restart, load balancer rotation, NAT mapping expiry, server overload hoặc peer crash đều có thể khiến kết nối đóng. Vì vậy “long-lived” nghĩa là **mục tiêu thiết kế của phiên**, không phải SLA rằng socket sẽ không bao giờ đứt.

Một ứng dụng production cần **phát hiện stale connections, reconnect có kiểm soát, xác thực lại và khôi phục trạng thái/subscription**, không giả định cùng một TCP socket sẽ tồn tại suốt phiên người dùng.

### 2.2. Message không đồng nghĩa frame

WebSocket chia dữ liệu thành frames. Một **message** có thể chứa **một frame hoặc nhiều continuation frames**. APIs có thể thông báo từng phần message (ví dụ Java `WebSocket.Listener.onText(..., last)`), do đó parser không được giả định “mỗi callback = một message hoàn chỉnh”.

~~~text
WebSocket TEXT message "abcdef"
   |
   +-- frame 1: "abc" (FIN=0)
   +-- frame 2: "def" (continuation, FIN=1)

Java Listener.onText có thể được gọi nhiều lần:
   onText(ws, "abc", false)
   onText(ws, "def", true)
   -> ghép thành một application message "abcdef"
~~~

Các **control frames** như Ping/Pong/Close có quy tắc riêng. Không trộn bytes của hai text messages chỉ vì chúng tới trên cùng một connection; hãy dựa vào ranh giới message/flag `last` do API cung cấp.

## 3. Khi nào WebSocket thực sự phù hợp?

### 3.1. Chat, nhắn tin và sự kiện hội thoại

Một người gửi message trong phòng chat; những người khác cần thấy ngay mà không bấm refresh. Client cũng có thể gửi typing indicator, read receipts, reactions, presence hoặc yêu cầu tham gia/ra khỏi phòng. **Hai chiều liên tục, nhiều message nhỏ và sự kiện bất ngờ từ server** là trường hợp đặc trưng.

Ví dụ thông điệp ứng dụng:

~~~json
{"type":"chat.send","roomId":"java","requestId":"req-17","text":"Chào mọi người"}
{"type":"chat.message","roomId":"java","sequence":381,"text":"Chào mọi người"}
{"type":"presence.changed","userId":"u42","online":true}
~~~

Mỗi dòng JSON trên là **ví dụ định dạng của ứng dụng**, không phải frame format mặc định WebSocket. Server vẫn cần authz phòng chat, giới hạn message và chống spam. Nếu cần gửi message offline cho user vắng mặt, phải lưu vào database/queue và phát lại khi user kết nối; WebSocket **không tự lưu offline messages**.

### 3.2. Cộng tác trực tuyến: tài liệu, bảng trắng, con trỏ

Trong một tài liệu nhiều người cùng sửa, mỗi thao tác có thể tạo sự kiện nhỏ: chèn ký tự, sửa ô, di chuyển con trỏ, trạng thái user. Server phân phối thay đổi tới nhiều người trong thời gian ngắn.

**WebSocket chỉ là kênh truyền thao tác.** Nó **không tự giải quyết** conflict resolution, OT (Operational Transformation), CRDT, locking, version vectors, ordering xuyên nhiều server hoặc durable history. Ứng dụng phải chọn mô hình nhất quán và cơ chế khôi phục sau disconnect.

### 3.3. Dashboard hoạt động, trading quotes, trạng thái đơn hàng đang chạy

Giá thị trường, số liệu vận hành, log tác vụ, trạng thái giao hàng hoặc phiên theo dõi job có thể phát sinh **bất kỳ thời điểm nào**. Server chủ động gửi cập nhật giúp tránh polling dày đặc.

Nhưng hãy hỏi: dashboard chỉ **nhận** updates hay cũng cần gửi lệnh tương tác liên tục? Nếu chỉ nhận một chiều, **SSE** thường đơn giản hơn; WebSocket có lợi hơn khi cần thay đổi subscriptions, điều khiển server, filter hoặc trao đổi hai chiều thường xuyên ngay trên phiên.

Với thị trường tài chính hay dữ liệu quan trọng, còn cần sequence, snapshot/replay, phát hiện mất sự kiện, rate limiting và clock policy. **Kênh luôn mở không bảo đảm mọi cập nhật được ứng dụng xử lý đúng một lần**.

### 3.4. Multiplayer game và điều khiển tương tác

WebSocket phù hợp cho nhiều **lệnh chơi game theo lượt hoặc cập nhật trạng thái cần độ tin cậy/đúng thứ tự**: chat trong game, matchmaking, lobby, kiểm soát phiên, game ô chữ, board game, hoặc các event điều khiển không quá nhạy với head-of-line blocking.

Với trò chơi real-time yêu cầu **latency cực thấp và chấp nhận bỏ bản cũ** (ví dụ vị trí nhân vật 60 lần/giây), độ tin cậy/đúng thứ tự của TCP có thể khiến mất một segment làm dữ liệu mới bị chờ theo. Khi ấy UDP/QUIC DATAGRAM/WebRTC DataChannel cấu hình phù hợp có thể hợp lý hơn, tùy platform. Đừng cho rằng WebSocket là “giao thức nhanh nhất” cho mọi game.

### 3.5. Remote terminal, tương tác thiết bị và phiên điều khiển

Một terminal từ xa hoặc tác vụ debug có lệnh client gửi và output server đẩy liên tục. Một phiên streaming logs mà người dùng có thể **pause/resume, đổi filter, gửi command** là trường hợp full-duplex hữu ích.

Cần kiểm soát quyền rất chặt: mỗi lệnh phải được authz, ghi audit, lọc input và có giới hạn tốc độ/timeout. WebSocket chỉ mang bytes/messages; nó không biến lệnh shell nguy hiểm thành an toàn.

### 3.6. Theo dõi job dài và cập nhật tiến độ

Client bắt đầu một tác vụ phân tích, server đẩy `started`, `progress`, `warning`, `completed`. Nếu client còn có nút `pause`, `resume`, `cancel` và thay đổi ưu tiên trên cùng kênh, WebSocket có thể rất tiện.

Tuy nhiên, nếu chỉ **nhận tiến độ một chiều**, SSE hoặc HTTP polling theo khoảng thời gian hợp lý có thể ít phức tạp hơn. Với job kéo dài nhiều giờ, trạng thái chuẩn phải được lưu trên server; nếu WebSocket bị mất, job **không nên tự biến mất**.

### 3.7. Hệ thống cần thuê bao động

Client có thể gửi:

~~~json
{"type":"subscribe","channels":["orders.123","alerts"]}
{"type":"unsubscribe","channels":["alerts"]}
{"type":"filter.update","severity":"warning"}
~~~

Server chủ động gửi những sự kiện thuộc subscription đang được phép. Đây là điểm mạnh khi **subscriptions thay đổi nhanh**: client có thể sửa nội dung muốn nhận ngay trên một phiên. Nhưng server vẫn phải kiểm tra ACL **mỗi subscribe**, không mặc định user có quyền vì đã kết nối.

## 4. Trường hợp KHÔNG nên dùng WebSocket chỉ vì “muốn hiện đại”

| Nhu cầu | Giải pháp thường đơn giản hơn | Vì sao |
| --- | --- | --- |
| GET một hồ sơ hoặc danh sách | HTTP GET + caching, ETag | Không có yêu cầu server push liên tục |
| POST biểu mẫu, tạo đơn hàng, PUT tài nguyên | REST/HTTP API | Method, status, idempotency, caching, proxy/log thuận tiện |
| Thông báo một chiều từ server tới browser | SSE (`EventSource`) | HTTP stream đơn giản, tự hỗ trợ event IDs/reconnect ở mức API browser |
| Cập nhật vài chục giây/phút một lần | Polling HTTP hợp lý | Tránh quản lý hàng nghìn socket stateful |
| Chờ một job kết thúc, ít updates | Long polling/SSE/periodic GET | Full-duplex có thể không cần |
| Upload/download file rất lớn | HTTP streaming, multipart/resumable upload | HTTP có hỗ trợ progress, range, retry, CDN phù hợp |
| Dữ liệu công khai muốn cache tại CDN | HTTP GET/Cache-Control | WebSocket messages không tự đi qua HTTP object cache |
| Streaming video/audio cho người xem | HLS/DASH/WebRTC/RTP tùy yêu cầu | WebSocket không tự xử lý codec, congestion/jitter hoặc media semantics |
| Real-time media/video call | WebRTC | Có NAT traversal, media transports, jitter handling phù hợp |
| Chỉ cần nhận webhook giữa các backend | HTTPS webhook/event queue | Không cần duy trì kết nối hai chiều từ bên nhận |
| Tác vụ backend có transaction, độ bền cao | Queue/broker + HTTP/RPC | WebSocket không thay thế persistence/transaction |

**Nguyên tắc thiết kế:** chọn giao thức đơn giản nhất đáp ứng **hướng luồng, tần suất, latency, độ tin cậy, khả năng mở rộng và chi phí vận hành**. Giữ một WebSocket mở “phòng khi có thể cần” có chi phí socket, bộ nhớ, auth state, heartbeat và reconnect không nhỏ.

## 5. So sánh WebSocket với HTTP, polling, SSE và các lựa chọn khác

| Tiêu chí | HTTP request/response | Short polling | Long polling | SSE | WebSocket |
| --- | --- | --- | --- | --- | --- |
| Hướng truyền chủ đạo | Client gọi, server trả | Client hỏi nhiều lần | Client hỏi, server chờ sự kiện rồi trả | Server → client trên một HTTP response stream | **Client ↔ server** |
| Server chủ động đẩy giữa các request | Không theo mô hình đơn giản | Không | Trả lời request đang treo | **Có**, một chiều | **Có**, hai chiều |
| Client chủ động gửi message sau thiết lập | Phải tạo request | Request tiếp theo | Request tiếp theo | Dùng HTTP request khác | **Gửi trên cùng kết nối** |
| Mức overhead khi liên tục nhiều thông điệp | Nhiều request/headers | Nhiều request rỗng | Nhiều vòng request | Stream giữ mở | Frames nhỏ trên kết nối mở |
| Tính dễ dùng với cache/CDN HTTP | Rất tốt | Tùy response | Phức tạp hơn | Tùy proxy; không phải object cache thông thường | Không có caching HTTP cho từng message |
| Khả năng resume/replay | Dựa request/API | Dựa API | Dựa API | Browser có Last-Event-ID nếu server thiết kế ID | **Ứng dụng phải tự thiết kế** |
| Trạng thái server kết nối lâu | Thường thấp hơn | Thấp/dao động | Có request chờ | Có stream đang mở | Có WebSocket session đang mở |
| Phù hợp nhất | CRUD/đọc tài nguyên | Thay đổi thưa, đơn giản | Sự kiện không đều, không dùng WebSocket | Live feed một chiều | Giao tiếp tương tác hai chiều liên tục |

### 5.1. SSE khác WebSocket ở chỗ nào?

**Server-Sent Events** dùng HTTP response có media type `text/event-stream`; server đẩy text events xuống browser, còn client muốn gửi command phải dùng HTTP request khác. Browser `EventSource` có hành vi tự reconnect và gửi lại last event ID trong những trường hợp được hỗ trợ.

Nếu dashboard chỉ cần feed “có sự kiện mới”, SSE thường đủ. Nếu ứng dụng cần gửi **nhiều command nhỏ, điều khiển subscription, typing indicator hoặc trạng thái tương tác liên tục**, WebSocket tạo kênh hai chiều tự nhiên hơn.

SSE không tự làm event durable: server vẫn phải lưu history nếu muốn replay từ event ID. WebSocket cũng vậy, nhưng WebSocket không có sẵn cơ chế `Last-Event-ID` giống API SSE.

### 5.2. WebSocket và HTTP/2 / HTTP/3

Mô tả handshake cơ bản ở đây là WebSocket **RFC 6455 qua HTTP/1.1 Upgrade**. Có cơ chế mở WebSocket qua **HTTP/2 extended CONNECT** (RFC 8441) trong những môi trường hỗ trợ, nhưng không được giả định mọi proxy/client Java tự động dùng hoặc hỗ trợ chế độ đó. Khái niệm **một phiên hai chiều kéo dài** vẫn là điều cần quyết định.

Một số hệ thống dùng gRPC bidirectional streaming trên HTTP/2 trong backend. Với backend Java-to-Java, gRPC streaming có schema/service contracts và tooling riêng, đôi khi phù hợp hơn WebSocket; với browser trực tiếp, khả năng truy cập gRPC streaming truyền thống khác WebSocket. **HTTP/2 multiplexing không tự biến REST request thành WebSocket**.

### 5.3. WebSocket và WebRTC/QUIC DATAGRAM

WebSocket thường đi trên **reliable ordered stream** (TCP). Những transport/datagram API khác có thể ưu tiên latency và cho phép mất gói, hoặc cung cấp streams đa luồng. Nếu hệ thống thật sự cần bỏ mẫu cập nhật cũ thay vì đợi retransmission, hãy đánh giá WebRTC DataChannel/QUIC theo môi trường và thư viện.

Không gọi WebSocket là “UDP cho web”, không suy ra có NAT traversal cho P2P, không coi WebSocket là giải pháp tự động cho media codecs hay tín hiệu điều khiển real-time có deadline siêu ngắn.

## 6. Kết nối WebSocket hoạt động thế nào?

### 6.1. HTTP Upgrade handshake cơ bản

Trên HTTP/1.1, client đề xuất chuyển giao thức:

~~~http
GET /realtime HTTP/1.1
Host: example.test
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
~~~

Nếu server chấp nhận theo RFC 6455, nó có thể trả:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
~~~

Ví dụ trên dùng key/accept nổi tiếng trong RFC 6455 để minh họa. `Sec-WebSocket-Accept` được tính từ key và magic GUID. **Handshake này không phải authentication**: bất kỳ client nào có thể tự tạo một key hợp lệ. Khi ứng dụng cần đăng nhập, phải dùng session/token/authz với kiểm tra quyền thực sự.

Khi handshake thành công, endpoint chuyển sang **WebSocket frames**. Không tiếp tục gửi từng JSON message dưới dạng `POST /realtime` theo HTTP request thông thường trên chính socket đã nâng cấp.

### 6.2. ws:// và wss://

- `ws://`: WebSocket qua kết nối không có bảo vệ TLS của WebSocket URL; có thể phù hợp **demo loopback**.
- `wss://`: WebSocket qua TLS, thích hợp cho dữ liệu thực trên Internet; cần kiểm tra certificate/trust/hostname, không tắt xác thực để kết nối cho bằng được.

Một trang HTTPS trên browser thường không được phép kết nối tới `ws://` không an toàn do mixed-content policy. Với ứng dụng triển khai thật, hãy dùng `wss://`, bảo đảm reverse proxy cho phép upgrade và cấu hình thời gian idle, keepalive, close đúng.

### 6.3. WebSocket frames không phải HTTP messages

Sau handshake, payload có các loại opcode phổ biến:

| Opcode | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `0x1` | Text frame | Nội dung message là UTF-8, có thể phân mảnh |
| `0x2` | Binary frame | Byte array/binary payload |
| `0x0` | Continuation frame | Phần tiếp theo của fragmented message |
| `0x8` | Close control frame | Bắt tay đóng và close status/reason |
| `0x9` | Ping control frame | Kiểm tra liveness ở protocol level |
| `0xA` | Pong control frame | Phản hồi Ping hoặc thông báo tương ứng |

Trong WebSocket RFC 6455, **client-to-server frames phải được mask**; server-to-client frames **không được mask**. Masking **không phải mã hóa** và không thay TLS: nó là cơ chế framing/protection đặc thù giao thức. Các control frames có ràng buộc độ dài/fragmentation nghiêm ngặt.

`WebSocket.Listener` của JDK giúp client quản lý frames, masking, handshake và callback; bạn **không cần tự gõ masked bytes** khi dùng client API. Server tự viết phải xử lý đầy đủ RFC, security và extensions — không nên triển khai thủ công để đưa production.

## 7. Thiết kế message protocol ứng dụng trên WebSocket

WebSocket đảm bảo có text/binary message, nhưng **không định nghĩa nội dung nghiệp vụ**. Một JSON envelope có thể được ứng dụng quy ước như:

~~~json
{
  "version": 1,
  "type": "order.subscribe",
  "requestId": "req-8f3",
  "channel": "orders/123",
  "lastSeenSequence": 501
}
~~~

Server có thể gửi:

~~~json
{
  "version": 1,
  "type": "order.updated",
  "channel": "orders/123",
  "sequence": 502,
  "occurredAt": "2026-11-01T10:00:00Z",
  "payload": {
    "status": "shipped"
  }
}
~~~

Đây là **schema minh họa do ứng dụng thiết kế**, không phải WebSocket RFC bắt buộc. Các trường nên được chọn theo nhu cầu thật:

- `type` phân loại event/command; `version` giúp tương thích schema.
- `requestId` liên hệ command với ACK/error, hữu ích khi có nhiều yêu cầu in-flight.
- `sequence` giúp phát hiện gap và tái đồng bộ event stream.
- `channel`/`topic` biểu diễn subscription, nhưng server **phải kiểm tra authorization**.
- `occurredAt` hỗ trợ quan sát/thứ tự thời gian, nhưng **không thay sequence hay clock-safe ordering**.
- `payload` chứa domain data, cần size limit, validation và kiểm soát field nhạy cảm.

### 7.1. Command và acknowledgment

Ví dụ:

~~~text
Client -> Server: {"type":"order.cancel","requestId":"q77","orderId":"123"}
Server -> Client: {"type":"ack","requestId":"q77","accepted":true}
Server -> Client: {"type":"order.updated","sequence":503,"status":"cancelled"}
~~~

ACK “accepted” không nhất thiết đồng nghĩa nghiệp vụ đã **commit**; phải định nghĩa rõ ACK khi nào có giá trị. Nếu mất kết nối sau lệnh nhưng trước ACK, client không thể tự đoán lệnh đã thất bại. Với side effects, cần **idempotency key, request status lookup và transaction policy** để retry an toàn.

### 7.2. Không phụ thuộc thứ tự toàn hệ thống từ một WebSocket

Một kết nối TCP có thứ tự bytes. Nhưng nếu server A và B cùng gửi event qua một pub/sub, source cập nhật trên nhiều partition, hoặc client reconnect sang node khác, **global ordering** không tự xuất hiện. Cần định nghĩa per-topic/per-entity ordering, sequence/version ở origin và cách xử lý event cũ.

### 7.3. JSON hay binary?

- JSON text: dễ debug, có schema rõ, phù hợp command/event nhỏ.
- Binary (protobuf, CBOR hoặc định dạng riêng): có thể giảm byte và CPU parse trong một số điều kiện; cần versioning/schema và kiểm tra validation.
- Không dùng binary như cách bỏ qua input validation; server luôn phải kiểm tra type, size, permission và rate.
- Không nên gửi tệp nhiều gigabyte qua WebSocket chỉ vì hỗ trợ binary. HTTP streaming/resumable upload thường có ecosystem hỗ trợ tốt hơn.

## 8. Java 17 có WebSocket client nhưng không cung cấp server WebSocket cấp cao tương đương

Từ Java 11, module `java.net.http` chứa:

- `HttpClient.newWebSocketBuilder()` để tạo builder.
- `WebSocket.Builder.buildAsync(URI, WebSocket.Listener)` để bắt đầu handshake bất đồng bộ và nhận `CompletableFuture<WebSocket>`.
- `WebSocket.sendText(text, last)`, `sendBinary(ByteBuffer, last)`, `sendPing`/`sendPong` và `sendClose`.
- `WebSocket.Listener` với `onOpen`, `onText`, `onBinary`, `onPing`, `onPong`, `onClose` và `onError`.

**Điểm dễ nhầm:** JDK 17 chuẩn có **WebSocket client API**, nhưng **không có một WebSocket server high-level tương đương trong `java.net.http`**. Java `com.sun.net.httpserver.HttpServer` đơn giản không tự cung cấp WebSocket server endpoint. Nếu cần server thật, thường dùng Jakarta WebSocket, Spring WebSocket, Netty, Jetty, Undertow hoặc runtime/framework phù hợp.

Ví dụ client WebSocket:

~~~java
WebSocket client = HttpClient.newHttpClient()
        .newWebSocketBuilder()
        .buildAsync(URI.create("wss://example.test/live"), listener)
        .join();

client.sendText("hello", true);
~~~

**Mã minh họa**, giả định `listener` là `WebSocket.Listener` đã cài đặt và có import `java.net.URI`, `java.net.http.*`. Không gọi `join()` trong event-loop/I/O worker nếu có thể dùng continuation `thenAccept`/`thenCompose`; đoạn trên chỉ dạy thứ tự tạo connection rồi gửi.

### 8.1. `WebSocket.Listener` là event/callback API

Trong Listener, `onOpen` chạy khi WebSocket đã thiết lập. `onText` có thể được gọi nhiều lần cho một message, tham số `last` cho biết phần cuối. `onClose` nhận mã đóng và reason; `onError` thông báo lỗi.

Quan trọng trong JDK API: listener điều khiển **receive demand** bằng `webSocket.request(n)`. Nếu không request thêm khi cần, ứng dụng có thể không nhận tiếp các callbacks dữ liệu như mong muốn. Với message đã xong, hãy phân phối nó sang processing queue phù hợp; không block lâu trong callback.

### 8.2. `sendText` hoàn tất không phải business acknowledgment

`client.sendText(text, true)` trả `CompletableFuture<WebSocket>`. Khi future hoàn thành, nó báo tiến độ gửi theo hợp đồng của client API; **không chứng minh server đã lưu message vào database**. Muốn biết xử lý thành công, phải đợi **application-level ACK** mang requestId hoặc kết quả nghiệp vụ tương ứng.

### 8.3. `last` là cờ kết thúc message, không phải kết thúc connection

~~~java
// Gửi một message "hello" thành hai phần:
client.sendText("hel", false)
      .thenCompose(ws -> ws.sendText("lo", true));
~~~

Đây là fragment minh họa với `client` đã kết nối. `last=false` nghĩa là còn phần tiếp theo trong **cùng message**, `last=true` hoàn tất message. Nó **không** tự đóng WebSocket. Nếu gửi nhiều phần, dùng continuation chain để tránh hoạt động gửi text chồng nhau hoặc làm rối ranh giới message.

## 9. Ví dụ Java 17+ tự chạy: client chuẩn WebSocket và server loopback tối giản

Để không phụ thuộc Internet hoặc dịch vụ echo công cộng, demo sau dựng một **server minh họa RFC 6455 cực tối giản trên `ServerSocket`**, rồi dùng **client WebSocket của JDK** để kết nối. Server:

1. Nhận đúng một HTTP/1.1 Upgrade request và đọc header tới `\r\n\r\n` với giới hạn nhỏ.
2. Lấy `Sec-WebSocket-Key`, tính `Sec-WebSocket-Accept` bằng SHA-1 theo **yêu cầu bắt tay của RFC 6455** (đây **không phải** hash mật khẩu hay mã hóa payload).
3. Trả `101 Switching Protocols`; đọc **một client text frame FIN=1, length <=125 byte**, bắt buộc client masking.
4. Echo nguyên text payload bằng **server text frame không mask**.
5. Đọc **một Close frame** của client, trả Close frame và đóng socket.

Client sử dụng `HttpClient.newWebSocketBuilder()`, `WebSocket.Listener`, `sendText` và `sendClose`. Server được giới hạn cố ý để thể hiện wire protocol; **không dùng server demo làm sản phẩm** vì nó không xử lý đầy đủ fragmented/extended frames, Unicode validation, TLS, Ping/Pong, Origin/auth, concurrency, rate limit hoặc mọi trường hợp RFC 6455.

Tạo file **WebSocketLoopbackDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Base64;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

public class WebSocketLoopbackDemo {
    record Frame(int opcode, byte[] payload) {}

    static String readHeaders(InputStream in) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        final String delimiter = "\r\n\r\n";
        int matched = 0;
        int b;

        while ((b = in.read()) != -1) {
            bytes.write(b);
            if (bytes.size() > 8192) {
                throw new IOException("Header too large");
            }

            if (b == delimiter.charAt(matched)) {
                matched++;
                if (matched == 4) {
                    return bytes.toString(StandardCharsets.ISO_8859_1);
                }
            } else {
                matched = b == '\r' ? 1 : 0;
            }
        }

        throw new EOFException("Incomplete HTTP upgrade");
    }

    static String header(String headers, String name)
            throws IOException {
        for (String line : headers.split("\r\n")) {
            int sep = line.indexOf(':');
            if (sep > 0
                    && line.substring(0, sep).trim()
                            .equalsIgnoreCase(name)) {
                return line.substring(sep + 1).trim();
            }
        }
        throw new IOException("Missing HTTP header " + name);
    }

    static Frame readClientFrame(InputStream in) throws IOException {
        int first = in.read();
        int second = in.read();

        if (first < 0 || second < 0) {
            throw new EOFException("Missing frame");
        }
        if ((first & 0x80) == 0) {
            throw new IOException("Demo only supports FIN=1");
        }

        int opcode = first & 0x0f;
        if ((second & 0x80) == 0) {
            throw new IOException("Client frame must be masked");
        }

        int length = second & 0x7f;
        if (length > 125) {
            throw new IOException("Demo only supports short frames");
        }

        byte[] mask = in.readNBytes(4);
        byte[] payload = in.readNBytes(length);
        if (mask.length != 4 || payload.length != length) {
            throw new EOFException("Truncated frame");
        }

        for (int i = 0; i < payload.length; i++) {
            payload[i] ^= mask[i % 4];
        }
        return new Frame(opcode, payload);
    }

    static void writeServerFrame(
            OutputStream out, int opcode, byte[] payload)
            throws IOException {

        if (payload.length > 125) {
            throw new IOException("Too long for demo frame");
        }

        out.write(0x80 | opcode); // FIN=1 + opcode.
        out.write(payload.length); // Server không mask.
        out.write(payload);
        out.flush();
    }

    static void serveOne(
            ServerSocket listener,
            CompletableFuture<Void> done) {

        try (Socket socket = listener.accept()) {
            socket.setSoTimeout(5000);
            InputStream in = socket.getInputStream();
            OutputStream out = socket.getOutputStream();

            String headers = readHeaders(in);
            if (!headers.startsWith("GET ")) {
                throw new IOException("Expected HTTP GET");
            }
            String key = header(headers, "Sec-WebSocket-Key");

            String acceptInput = key
                    + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
            String accept = Base64.getEncoder().encodeToString(
                    MessageDigest.getInstance("SHA-1")
                            .digest(acceptInput.getBytes(
                                    StandardCharsets.US_ASCII)));

            String response = "HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\n"
                    + "Connection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + accept
                    + "\r\n\r\n";

            out.write(response.getBytes(StandardCharsets.US_ASCII));
            out.flush();

            Frame text = readClientFrame(in);
            if (text.opcode() != 1) {
                throw new IOException("Expected text frame");
            }
            writeServerFrame(out, 1, text.payload());

            Frame close = readClientFrame(in);
            if (close.opcode() != 8) {
                throw new IOException("Expected close frame");
            }
            writeServerFrame(out, 8, close.payload());

            done.complete(null);
        } catch (Throwable error) {
            done.completeExceptionally(error);
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {

            CompletableFuture<Void> serverDone =
                    new CompletableFuture<>();
            Thread worker = new Thread(
                    () -> serveOne(listener, serverDone));
            worker.setDaemon(true);
            worker.start();

            CompletableFuture<String> received =
                    new CompletableFuture<>();
            CompletableFuture<Integer> closed =
                    new CompletableFuture<>();

            WebSocket.Listener callbacks = new WebSocket.Listener() {
                final StringBuilder parts = new StringBuilder();

                @Override
                public void onOpen(WebSocket socket) {
                    // Chấp nhận ít nhất một callback message.
                    socket.request(1);
                }

                @Override
                public CompletionStage<?> onText(
                        WebSocket socket,
                        CharSequence data, boolean last) {

                    parts.append(data);
                    if (last) {
                        received.complete(parts.toString());
                    }
                    socket.request(1);
                    return null;
                }

                @Override
                public CompletionStage<?> onClose(
                        WebSocket socket,
                        int statusCode, String reason) {
                    closed.complete(statusCode);
                    return null;
                }

                @Override
                public void onError(
                        WebSocket socket, Throwable error) {
                    received.completeExceptionally(error);
                    closed.completeExceptionally(error);
                }
            };

            String endpoint = "ws://127.0.0.1:"
                    + listener.getLocalPort() + "/";

            WebSocket client = HttpClient.newHttpClient()
                    .newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .buildAsync(URI.create(endpoint), callbacks)
                    .join();

            client.sendText("hello WebSocket", true).join();
            System.out.println("echo: "
                    + received.get(5, TimeUnit.SECONDS));

            client.sendClose(WebSocket.NORMAL_CLOSURE, "done")
                    .join();
            System.out.println("close: "
                    + closed.get(5, TimeUnit.SECONDS));

            serverDone.get(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Biên dịch/chạy với **JDK 17+**:

~~~bash
javac -encoding UTF-8 WebSocketLoopbackDemo.java
java WebSocketLoopbackDemo
~~~

Stdout đã được chạy kiểm tra trên Java 17:

~~~text
echo: hello WebSocket
close: 1000
~~~

### 9.1. Từng bước trong code

**Bước 1 — ServerSocket lắng nghe trên loopback.** Một server socket được mở tại `127.0.0.1` với port 0 (OS tự cấp một port còn trống); demo cho server chạy trên một daemon thread. Client sẽ lấy port thực tế, nên output không chứa giá trị port ngẫu nhiên.

**Bước 2 — HTTP Upgrade handshake.** Client WebSocket của JDK tự gửi HTTP upgrade request với `Sec-WebSocket-Key`. Server demo dùng công thức RFC 6455 để trả `Sec-WebSocket-Accept` hợp lệ và mã 101. Đây là lý do JDK client chấp nhận kết nối, không phải vì server đã cấp một token login.

**Bước 3 — Client gửi text.** `sendText("hello WebSocket", true)` gửi một text message. Demo server hỗ trợ **chỉ một frame ngắn FIN=1** từ client, đọc 4 byte masking key và unmask payload, rồi gửi lại một text frame unmasked. WebSocket client của JDK tự đọc/giải mã frame và gọi Listener.

**Bước 4 — Listener nhận message.** `onOpen` gọi `request(1)`. `onText` cộng các text chunks vào `StringBuilder`, khi `last=true` thì hoàn thành `received`; `received.get(5s)` giúp main chờ và in `echo: hello WebSocket`. Trong ứng dụng nhiều message, phải **reset buffer sau mỗi complete message** và xử lý concurrency/demand thích hợp; demo chỉ nhận một message.

**Bước 5 — Close handshake.** Client gọi `sendClose(1000,"done")`; server nhận Close frame và trả một Close frame. Listener `onClose` thấy status `1000` (normal closure), hoàn thành future `closed`; main in `close: 1000`. Việc đóng bình thường khác với peer mất mạng khiến connection đứt mà không có Close frame.

### 9.2. Giới hạn rõ ràng của server minh họa

Đây **không phải WebSocket server RFC-compliant đầy đủ**. Các phần nó **không** làm:

- Không xác thực danh tính `Origin`, cookie/session/token, ACL hay chống Cross-Site WebSocket Hijacking.
- Không phục vụ HTTPS/WSS hoặc kiểm tra TLS; chỉ bind loopback để học.
- Không hỗ trợ extension, subprotocol, compression, fragmentation/continuation frames, binary messages, ping/pong hoặc extended payload lengths 126/127.
- Không parse/validate mọi chi tiết của handshake RFC 6455 (version, Upgrade/Connection token, key length, duplicates, protocol negotiation, error responses).
- Không kiểm tra text UTF-8 validity hoặc Close code/reason thật đầy đủ.
- Không có nhiều client đồng thời, heartbeat, idle timeout hai chiều, rate limit, per-user quotas, backpressure hoặc application-level ACK.
- Không dùng framework server đã được harden; không phù hợp để nhận client từ Internet.

Giá trị bài demo là **thấy client API Java chuẩn hoạt động end-to-end với HTTP upgrade, text echo, masking và close frame**. Khi viết production WebSocket server, hãy dùng framework/WebSocket implementation có kiểm thử giao thức và bảo mật, không copy server demo rồi gắn vào cổng public.

## 10. Long-lived connection yêu cầu giữ trạng thái gì?

Server production thường có các lớp state:

| State | Thuộc về | Ví dụ |
| --- | --- | --- |
| **Transport** | Một WebSocket connection | socket, buffers, close state, last ping/pong |
| **Authentication** | Người dùng/thiết bị đã xác thực | user ID, token expiry, allowed scopes |
| **Subscriptions** | Phiên đang lắng nghe các topics | rooms, order IDs, filters |
| **Application protocol** | Một luồng command/event | request IDs, sequence, ACK và phase |
| **Durable state** | Kho lưu trữ server-side | messages, job progress, last committed event |
| **Recovery state** | Có thể sống qua reconnect | resume token, last confirmed sequence |

Không phải thứ gì cũng được giữ trong RAM của WebSocket session. Một socket sẽ biến mất khi server restart; **durable state phải ở database/broker** nếu nghiệp vụ cần phục hồi.

Ví dụ người dùng ở phòng chat: server nên kiểm tra quyền vào phòng khi subscribe và khi quyền thay đổi, không giữ mãi một boolean `authorized=true` từ lúc mở socket mà bỏ qua revocation.

## 11. Heartbeat, Ping/Pong và kiểm tra còn sống

Giữ WebSocket lâu có thể gặp connection **nửa mở**: một phía tưởng socket vẫn sống trong khi đường mạng đã hỏng. Có hai tầng kiểm tra:

1. **WebSocket protocol-level Ping/Pong:** một endpoint gửi Ping, peer trả Pong theo RFC. Dùng để phát hiện kết nối không có đáp ứng trong một khoảng phù hợp; không đánh đồng một lần thiếu pong với user cố ý đăng xuất.
2. **Application heartbeat/presence:** client/server trao message `{"type":"heartbeat"}` hoặc timestamp/sequence, dùng để xác định tình trạng nghiệp vụ/phiên và chính sách hiện diện, nếu cần.

### 11.1. Ping/Pong không bảo đảm dữ liệu đã được xử lý

`Pong` chỉ cho biết peer WebSocket layer phản hồi ping; **không** chứng minh lệnh `order.cancel` đã commit. ACK nghiệp vụ vẫn là message khác.

### 11.2. Tần suất heartbeat không phải càng cao càng tốt

Ping mỗi 100 ms ở một triệu connections làm tăng CPU/network/battery. Chọn interval dựa vào **proxy/load balancer idle timeout, SLA phát hiện disconnect, môi trường mobile, số connections, jitter và khả năng backpressure**. Ví dụ heartbeat mỗi vài chục giây có thể phù hợp một số hạ tầng, nhưng không phải thông số chuẩn bắt buộc.

Nếu không thấy Pong quá deadline, đóng session và reconnect có backoff. Không để client “bão reconnect” cùng lúc sau một lần restart; thêm jitter và giới hạn tối đa attempts.

### 11.3. Client browser khác Java client

Browser WebSocket API thường **không cho ứng dụng JavaScript gửi Ping control frame trực tiếp**; browser/transport xử lý control frames. Nếu muốn heartbeat có thể quan sát từ JavaScript, thiết kế application ping/pong message với server.

Java JDK `WebSocket` client có phương thức `sendPing(ByteBuffer)`; payload của Ping control frame có giới hạn **125 byte** theo RFC. Không lạm dụng Ping như kênh gửi payload nghiệp vụ lớn.

## 12. Mất kết nối, reconnect và delivery semantics

### 12.1. Không có exactly-once qua reconnect

Một kịch bản:

~~~text
Client -> Server: command id=42 "submit"
Server xử lý và commit id=42
Server -> Client: ack id=42
                 X (mất mạng trước khi client nhận)

Client reconnect: không biết id=42 đã commit hay chưa.
~~~

Nếu client tự gửi lại lệnh bằng id mới mà không kiểm tra, có thể tạo tác dụng phụ **hai lần**. WebSocket đảm bảo thứ tự truyền **trên một kết nối đang hoạt động**, không giải quyết trạng thái không chắc chắn **sau disconnect**.

Thiết kế an toàn cho hành vi có side effect:

- Mỗi command có **idempotency key/request ID** ổn định qua retry.
- Server lưu kết quả đã xử lý hoặc có cơ chế kiểm tra trạng thái transaction.
- Client sau reconnect có thể hỏi “command id=42 đã xử lý chưa?” thay vì tự tạo lệnh mới.
- Event stream có `sequence` hoặc cursor, server có cách trả snapshot/replay; nếu log đã bị trim, client fetch snapshot rồi tiếp tục.
- Business errors và transport errors không bị trộn lẫn; “không thấy ACK” không đồng nghĩa “server chưa xử lý”.

### 12.2. Resume subscription

Sau reconnect, các subscriptions gắn với **socket cũ** có thể đã mất. Client cần gửi lại danh sách topics được phép, cursor cuối, phiên bản protocol và auth. Server xác thực lại, trả snapshot hoặc missed events nếu hỗ trợ.

~~~json
{"type":"resume","channels":["orders.123"],"lastSeenSequence":502}
~~~

Server nên quyết định có replay từ 503 được không; nếu có gap không thể phục hồi, gửi tín hiệu `resync.required` để client tải lại trạng thái qua HTTP. Không tự gắn event mới vào một UI đã mất sự kiện cũ mà không thông báo.

### 12.3. Reconnect có backoff

~~~text
disconnect -> chờ + jitter -> kết nối lại
           -> nếu lỗi: delay tăng dần tới mức trần
           -> nếu thành công: authenticate, resubscribe, resync, reset retry budget
~~~

Đây là luồng minh họa; delay cụ thể phụ thuộc mạng và server policy. Đừng tái kết nối vô hạn mỗi 1 ms. Khi user logout/hủy, cần **dừng retry** và đóng socket thay vì tiếp tục chạy nền.

## 13. Backpressure: client đọc chậm có thể làm server hết bộ nhớ

Giả sử producer sinh 50.000 events/s nhưng client chỉ xử lý được 500 events/s. Dù WebSocket chạy trên TCP, **độ chênh lệch không tự biến mất**. Nếu server cứ đưa mọi message vào một `ArrayList` không giới hạn, heap sẽ tăng.

Các cách xử lý:

1. **Giới hạn outbound queue theo byte và message count** cho mỗi connection.
2. **Coalesce** các cập nhật có thể thay thế nhau (ví dụ chỉ cần số liệu sensor mới nhất), thay vì xếp mọi event lịch sử.
3. **Bỏ bớt dữ liệu không thiết yếu** như typing indicators quá hạn theo quy tắc ứng dụng; không được âm thầm bỏ giao dịch tài chính quan trọng.
4. **Giảm tốc producer** hoặc đóng session quá chậm với close/error reason phù hợp.
5. **Giới hạn số connection và subscription/user**; mỗi connection có chi phí file descriptor, buffer và authentication state.
6. Theo dõi pending bytes, oldest queued message age, send latency, slow-consumer disconnects.

### 13.1. `WebSocket.Listener.request(n)` chỉ là receive demand của client JDK

`request(n)` cho biết listener sẵn sàng nhận thêm callbacks tương ứng; **không tự tạo end-to-end backpressure policy** cho broker, producer, database hoặc mọi server. Khi callback nhận một message, đừng block lâu để ghi database trên thread callback; có thể chuyển sang executor/queue có giới hạn và chỉ request tiếp khi tiêu thụ đủ.

Không dùng một `StringBuilder` vô hạn để ghép fragmented text mà không có **max message size**: kẻ xấu có thể gửi rất nhiều fragments và làm cạn RAM.

### 13.2. Head-of-line blocking

WebSocket RFC 6455 phổ biến qua TCP: mất một segment khiến các bytes sau phải chờ TCP retransmission, dù message mới đã được phát. Đây là đánh đổi của reliability/ordering. Với telemetry/game mà dữ liệu cũ mất giá trị rất nhanh, cần đánh giá latency và lựa chọn transport khác nếu cần.

## 14. Scale nhiều kết nối và fan-out nhiều người dùng

Server WebSocket giữ state trên mỗi connection, nên thiết kế **scale-out** khác phần lớn request/response HTTP stateless:

~~~text
Client A --WebSocket--> Node 1 --\
                                  \        +--------------------+
Client B --WebSocket--> Node 2 ---->-------| Pub/Sub / broker   |
                                  /        +--------------------+
Client C --WebSocket--> Node 3 --/
        |
        +-- mỗi node chịu trách nhiệm gửi tới các WebSocket của mình
~~~

Nếu một người trên Node 1 gửi vào room chứa người ở Node 2, Node 1 cần có một cơ chế phân phối sự kiện (broker/pub-sub hoặc service bus), chứ không tự tìm thấy socket ở memory của Node 2.

### 14.1. Sticky sessions có giải quyết mọi thứ?

Load balancer có thể dùng sticky routing để kết nối của một client không đổi node trong vòng đời connection; nhưng sau reconnect hoặc deploy, client vẫn có thể tới node khác. **Sticky routing không thay database, broker hoặc resume protocol**. Nên lưu durable state ngoài process khi cần, và thiết kế connection-state cleanup đúng cách.

### 14.2. Fan-out tới nhiều người

Một sự kiện broadcast cho 100.000 users không có nghĩa server chỉ gọi `sendText` một lần là đủ. Cần fan-out strategy, partitioning, batching/coalescing, ưu tiên message, bandwidth cap và không để một slow client kéo chậm tất cả clients khác.

Có thể phân chia theo room/topic hoặc shard, nhưng vẫn phải bảo đảm **ACL và event ordering** theo entity. Một broker có thể giữ history, còn WebSocket nodes chịu trách nhiệm các connections đang online.

### 14.3. Deploy và graceful shutdown

Khi rolling deployment:

1. Ngừng nhận connection mới trên node cũ.
2. Thông báo drain/reconnect nếu protocol có hỗ trợ.
3. Cho phép buffered messages xử lý trong deadline hợp lý.
4. Gửi WebSocket Close hợp lệ nếu có thể, đóng sessions, release subscriptions.
5. Client reconnect với backoff và resubscribe; server mới có thể replay/snapshot.

Không đợi vô hạn vì có vài WebSocket chưa đóng; đồng thời không cắt ngay mọi socket nếu ứng dụng đang gửi message quan trọng mà có phương án drain.

## 15. Bảo mật cho WebSocket: Upgrade không phải là xác thực

### 15.1. Dùng WSS trên mạng thật

`wss://` bảo vệ luồng bằng TLS, giúp chống nghe lén/chỉnh sửa trên đường đi khi cấu hình trust đúng. Với browser, trang HTTPS thường phải dùng WSS để tránh mixed content. Java `HttpClient` cũng phải xác minh certificate/hostname; **không tắt TLS verification** để sửa lỗi chứng chỉ.

### 15.2. Origin và Cross-Site WebSocket Hijacking

Browser có thể gửi header `Origin` khi khởi tạo WebSocket. Server phải áp dụng **allowlist Origin** phù hợp cho browser clients; không mặc định dựa vào chính sách CORS của `fetch`/XHR để chặn WebSocket handshake.

Nếu server dùng cookie session và không kiểm tra Origin, trang độc hại có thể thử tạo WebSocket cross-site với cookie của user theo điều kiện trình duyệt/cookie policy, dẫn đến **Cross-Site WebSocket Hijacking (CSWSH)**. Ngoài Origin, phải xác thực phiên, kiểm soát cookie/SameSite theo nhu cầu và **ủy quyền từng subscription/command**.

Với non-browser clients, `Origin` có thể bị giả mạo; Origin validation **không phải authentication** và không thể thay access token/mTLS hoặc session authorization.

### 15.3. Tokens và browser limitations

Browser `WebSocket` API không cung cấp cách tổng quát để tự gắn **bất kỳ custom Authorization header** như dùng với `fetch`. Các cách phổ biến gồm cookie được bảo vệ, short-lived scoped token trong một handshake flow được thiết kế chặt, hoặc subprotocol khi có quy ước an toàn. Không tùy tiện đưa bearer token vào query string vì nó dễ bị ghi trong URL/proxy/access logs. Nếu sử dụng query token trong kiến trúc cụ thể, cần TTL ngắn, scope chặt và log-redaction.

Java backend WebSocket client có builder APIs cho header theo ràng buộc của implementation, nhưng **không suy ra browser có y hệt khả năng đó**.

### 15.4. Kiểm soát mọi message, không chỉ connect

Sau khi WebSocket handshake xong, mỗi text/binary message vẫn là **dữ liệu người dùng chưa đáng tin**. Server cần:

- Kiểm tra schema, type, length, encoding và message size.
- Xác thực và **authorize hành động ở thời điểm xử lý**, nhất là khi quyền user có thể bị thu hồi.
- Rate-limit message count và bytes/user/IP.
- Giới hạn số room/topic subscribers và subscription churn.
- Không chạy lệnh shell/SQL từ text tùy ý; tránh injection.
- Hạn chế decompression ratio nếu bật `permessage-deflate`; không coi compression luôn miễn phí.
- Kiểm soát log/PII và token, dùng metrics không lộ payload nhạy cảm.

### 15.5. Ping không phải authentication

Nhận Pong chỉ chứng minh một kết nối có peer phản hồi; **không chứng minh user còn quyền** hoặc token chưa hết hạn. Với phiên kéo dài hàng giờ, có chiến lược token refresh/re-auth hoặc server có thể đóng subscription khi quyền thay đổi.

## 16. Cấu hình hạ tầng: proxy, load balancer và idle timeout

WebSocket làm việc qua nhiều hạ tầng HTTP nhưng cần hỗ trợ đúng:

- Proxy/reverse proxy phải cho phép WebSocket Upgrade (trong HTTP/1.1), truyền header `Upgrade`/`Connection` phù hợp và không buffer toàn bộ stream.
- TLS termination tại proxy phải cấu hình WSS origin, certificate và forwarding headers đáng tin theo kiến trúc.
- Idle timeout của load balancer có thể ngắn hơn ý định giữ phiên; heartbeat hoặc cập nhật timeout phù hợp với cấu hình.
- NAT/firewall/thiết bị di động có thể làm rớt kết nối; client phải reconnect và resume.
- Các cổng và mạng doanh nghiệp có thể chặn hoặc kiểm tra WebSocket khác HTTP thường; cần phương án fallback nếu sản phẩm yêu cầu.
- Không dùng HTTP CDN object cache để giả định các message WebSocket có cache semantics.

**Quan trọng:** sau một lần HTTP Upgrade thành công, **không phải mọi HTTP middleware vẫn còn xử lý từng WebSocket message**. Logging/auth/audit/size limits ở message layer phải được thực thi trong server WebSocket/framework.

### 16.1. Khi WebSocket “không kết nối được”

Checklist chẩn đoán:

1. URL là `ws://` hay `wss://` đúng scheme, host, port, path?
2. TLS certificate/hostname và trust chain có hợp lệ?
3. Server/proxy trả `101 Switching Protocols` (hoặc handshake phù hợp transport) hay `400/401/403/404/502`?
4. `Upgrade` và `Connection` headers có được reverse proxy truyền đúng?
5. Origin/session/auth có bị từ chối?
6. Proxy/LB idle timeout, firewalls và giới hạn số connections có phù hợp?
7. Có lỗi subprotocol/extension negotiation không?
8. Client nhận `onError`/close code gì? Đã kiểm tra server logs/correlation ID chưa?

Không khuyến khích “khắc phục” bằng cách **bỏ kiểm tra Origin, tắt TLS hoặc mở public endpoint không auth**.

## 17. Lỗi phổ biến khi thiết kế ứng dụng WebSocket

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng WebSocket cho một lần GET/POST đơn giản | Thêm state, reconnect và hạ tầng vô ích | Dùng HTTP request/response |
| Cần server push một chiều nhưng dùng WebSocket bắt buộc | Thêm protocol phức tạp | Đánh giá SSE |
| Xem WebSocket là UDP không mất thứ tự | Nhầm latency/reliability | Hiểu TCP và Head-of-line blocking |
| Tưởng một message = một frame/callback | Parse thiếu hoặc trộn text fragments | Gom phần cho tới `last=true` |
| Không gọi `request(n)` trong Java listener | Không nhận đủ callbacks như mong đợi | Quản lý demand có chủ đích |
| Gọi `sendText().join()` rồi cho là server đã commit | Không có ACK nghiệp vụ | Dùng request ID và application ACK |
| Một socket mất nghĩa là dữ liệu cũng phải mất | Không có resume/durable state | Database/queue + snapshot/replay |
| Retry command có side effect bằng ID mới | Giao dịch trùng | Idempotency key và transaction lookup |
| Không giới hạn queued messages | OOM với slow consumers | Per-connection byte quotas/backpressure |
| Mọi node chỉ lưu room members trong RAM | Gửi thiếu event tới users trên node khác | Shared broker/presence coordination |
| Bật heartbeat quá dày cho mọi client | Tốn CPU/network/pin | Dựa SLA/proxy idle và tải thực |
| Không kiểm tra Origin khi dùng browser cookies | Rủi ro CSWSH | Origin allowlist + auth/session checks |
| Chỉ xác thực ở handshake | User bị revoke vẫn nhận event | Re-auth/authorize commands/subscriptions |
| Coi `ws://` là đủ trên Internet | Dữ liệu có thể bị quan sát/sửa | Dùng `wss://` và validate TLS |
| Đẩy file lớn qua messages không giới hạn | Tăng memory và khó resume | HTTP streaming/resumable upload |
| Không gửi Close hoặc không xử lý network drop | Leak session, presence sai | Close handshake, idle timeout, cleanup |
| Dùng server demo raw `ServerSocket` làm public server | Thiếu RFC edge cases và security | Framework WebSocket chuẩn |
| Coi close status 1000 là ACK business | Không biết lệnh đã xử lý | Dựa trạng thái ứng dụng |
| Không test phiên dài khi deploy/đổi mạng | Mất subscriptions, bão reconnect | Load/reconnect/rolling-deploy tests |

## 18. Các bài tập quyết định kiến trúc

### Bài A — Trang thông báo đơn giản

Một trang chỉ cần nhận thông báo “có thông báo mới” và không gửi lệnh trong phiên. Chọn gì?

**Đáp án:** **SSE** thường đáng thử trước vì là kênh server → browser, dùng HTTP và browser EventSource hỗ trợ reconnect. WebSocket vẫn khả thi, nhưng không bắt buộc chỉ vì chữ “real-time”.

### Bài B — Phòng chat có typing và reactions

Client gửi tin, typing, reaction; server đẩy message và presence tới tất cả thành viên liên tục.

**Đáp án:** WebSocket phù hợp nhờ song công và latency thấp cho nhiều message nhỏ. Nhưng vẫn phải thiết kế authentication, authorization theo room, lưu lịch sử, sequence, rate-limit và ACK.

### Bài C — Dashboard thay đổi 1 lần mỗi 10 phút

Server có khoảng 100.000 người xem; dữ liệu đổi 10 phút/lần, không có command từ client.

**Đáp án:** HTTP GET có cache headers, polling thưa hoặc SSE có thể đơn giản và tiết kiệm hơn duy trì 100.000 kết nối WebSocket. Cần đo chi phí thực tế trước khi chọn.

### Bài D — Trò chơi bắn súng 60 updates/giây

State position cũ hết giá trị sau vài frame; ứng dụng muốn bỏ thông điệp cũ hơn là chờ retransmit.

**Đáp án:** WebSocket/TCP ordered delivery có thể gây head-of-line latency. Nên đánh giá transport cho real-time datagram/partial reliability (tùy client/platform) thay vì mặc định chọn WebSocket cho tất cả dữ liệu.

### Bài E — Job xử lý 2 giờ

Client cần theo dõi progress, thỉnh thoảng gửi pause/cancel và có thể tắt laptop rồi quay lại.

**Đáp án:** WebSocket có thể tiện cho progress + commands khi online, nhưng **job state phải durable**. Khi user reconnect, lấy snapshot qua HTTP và/hoặc resume event stream từ sequence; không gắn job lifetime vào socket lifetime.

### Bài F — Mobile mất Wi-Fi giữa một giao dịch

Client gửi command hủy đơn hàng rồi mất mạng trước khi thấy ACK. Khi online lại có nên tạo command mới và gửi lại?

**Đáp án:** không tự gửi lại với ID mới. Cần request ID/idempotency key, kiểm tra trạng thái server và resend an toàn theo policy. WebSocket không cung cấp exactly-once xuyên reconnect.

### Bài G — WSS thông qua reverse proxy

Trong môi trường local `ws://` chạy, nhưng production `wss://` trả 502 hoặc 400.

**Đáp án:** kiểm tra TLS termination, route/path, Upgrade/Connection headers, proxy support, auth/Origin, timeout và logs. Không sửa bằng cách tắt TLS.

### Bài H — 500.000 online clients

Một node giữ 500.000 sockets và room memberships trong heap; deploy khiến node mất mọi state.

**Đáp án:** cần thiết kế scale-out, phân chia connections, quotas, broker/pubsub, durable offsets/subscriptions và reconnect/resume. Sticky sessions một mình không giải quyết các state đã mất.

### Bài I — Một text message được chia 3 callback

Java listener gọi `onText(ws, part1, false)`, `onText(ws, part2, false)`, `onText(ws, part3, true)`.

**Đáp án:** ghép các phần theo ranh giới message cho tới `last=true`, sau đó parse một JSON/document duy nhất; giới hạn tổng kích thước và không ghép chéo nhiều messages.

### Bài J — Dùng browser cookies và không kiểm tra Origin

Một trang web khác có thể mở WebSocket tới server đã có login cookie của user trong một số điều kiện. Rủi ro gì?

**Đáp án:** CSWSH; server phải kiểm tra allowed Origin (đối với browser), xác thực, SameSite/cookie policy và authorize từng action. CORS của fetch không tự thay Origin validation của WebSocket.

### Bài K — `sendText` future đã complete

Client gọi `sendText(...).join()` và lập tức hiển thị “đơn đã thanh toán thành công”. Đúng không?

**Đáp án:** không. Future chỉ nói hoạt động gửi đạt trạng thái hoàn tất theo API; không có nghiệp vụ ACK/commit. Chờ message response/HTTP status nghiệp vụ có requestId và xác minh server state.

### Bài L — Client chậm, server gửi nhanh

Server tạo 10.000 events/s cho client không đọc, hàng đợi tăng không giới hạn. Biện pháp?

**Đáp án:** giới hạn queued bytes, coalesce sự kiện có thể thay thế, bỏ sự kiện không quan trọng theo policy, chậm producer hoặc đóng slow consumer; không hy vọng TCP tự loại bỏ mọi RAM pressure.

## 19. Checklist trước khi đưa WebSocket vào production

- [ ] **Có thực sự cần cả hai phía chủ động gửi** trong một phiên kéo dài và nhiều tương tác?
- [ ] Đã đánh giá HTTP, polling, long-polling, SSE và alternative transports?
- [ ] Phân biệt message, frame, fragmented text/binary và control frames?
- [ ] Client Java `Listener` quản lý `request(n)` và kết thúc message theo `last`?
- [ ] Có message schema/type/version, request ID, validation, max size và quyền từng action?
- [ ] Có ACK nghiệp vụ riêng, không coi gửi xong hoặc Pong là commit?
- [ ] Có sequence/cursor, snapshot/replay hoặc resync khi reconnect?
- [ ] Có timeout, Ping/Pong hoặc heartbeat theo SLA, không quá dày?
- [ ] Có reconnect backoff/jitter, max attempts và dừng khi user logout?
- [ ] Có giới hạn outbound queue, subscriptions, users, connections, rate và bộ nhớ?
- [ ] Có broker/pubsub hoặc fan-out architecture nếu nhiều server nodes?
- [ ] Durable state không bị gắn chặt vào đời socket?
- [ ] WSS/TLS, origin allowlist và session/token authentication đã cấu hình phù hợp?
- [ ] Có chống CSWSH khi dùng cookie trong browser và authz từng subscription/command?
- [ ] Reverse proxy/LB/CDN hỗ trợ Upgrade và idle timeout/rolling deploy?
- [ ] Có observability: concurrent sockets, connection lifetime, handshake failure, RTT, queue bytes, slow consumers, close codes, reconnect rate, missed events?
- [ ] Đã test mất mạng, offline/resume, đổi Wi-Fi, deploy restart, duplicate commands, large frames, malformed JSON và unauthorized subscribe?
- [ ] Không dùng server raw Socket của demo thay implementation RFC-compliant đầy đủ?

**Kết luận:** WebSocket thích hợp **khi trao đổi hai chiều và liên tục là nhu cầu cốt lõi**, không chỉ vì ứng dụng muốn “real-time”. Nó cho phép client và server cùng chủ động gửi text/binary messages trên một kết nối dài hạn, rất hữu ích cho chat, cộng tác, interactive dashboards và điều khiển. Nhưng WebSocket **không cung cấp durable messaging, exactly-once delivery, authorization, schema, offline replay hay tự scale**. Một thiết kế đúng phải đi kèm authentication, message protocol, backpressure, heartbeat, reconnect, persistence và vận hành hạ tầng. Nếu chỉ cần một chiều từ server hoặc requests thưa, **SSE hoặc HTTP thường đơn giản hơn**.

## 20. Tài liệu tham khảo

- **RFC 6455 — The WebSocket Protocol:** https://www.rfc-editor.org/rfc/rfc6455
- **RFC 8441 — Bootstrapping WebSockets with HTTP/2:** https://www.rfc-editor.org/rfc/rfc8441
- **Java 17 — WebSocket client API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html
- **Java 17 — WebSocket.Listener:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html
- **Java 17 — WebSocket.Builder:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html
- **Java 17 — HttpClient:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **WHATWG HTML — WebSocket API trong trình duyệt:** https://websockets.spec.whatwg.org/

Các RFC định nghĩa khung giao thức, còn Java API xác định callback, future và flow control của JDK. Khi phát triển production server, sử dụng WebSocket framework đúng chuẩn và kiểm thử cả hạ tầng proxy, TLS, browser Origin và quá trình reconnect.