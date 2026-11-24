# Theo dõi reconnect, resume, lease và lỗi thiết lập phiên

Một kết nối RSocket không chỉ có trạng thái đang mở hoặc đã đóng. Trong suốt vòng đời, client và server có thể thương lượng tham số phiên, gửi KEEPALIVE, cấp và tiêu thụ lease, mất transport rồi thử resume, hoặc phải thiết lập một phiên mới. Nếu chỉ theo dõi số socket đang mở, đội vận hành khó xác định vì sao client liên tục kết nối lại, vì sao request bị chặn trước khi tới handler, hay vì sao một phiên không thể phục hồi sau sự cố mạng.

Cần quan sát riêng ba lớp: **transport**, **RSocket connection/session** và **interaction/stream**. TCP hoặc WebSocket có thể thất bại trước khi RSocket bắt đầu; SETUP có thể bị server từ chối sau khi transport đã mở; một stream có thể lỗi trong khi connection vẫn hoạt động. Các sự kiện reconnect, RESUME, LEASE và SETUP vì thế cần metric, log và trace riêng.

Bài học này hướng dẫn phân biệt reconnect với RSocket resumption, hiểu vai trò của KEEPALIVE và LEASE, đọc các mã ERROR liên quan đến thiết lập phiên, thiết kế telemetry và kiểm thử tình huống lỗi. Nội dung áp dụng cho client/server Java, Spring Boot và các ứng dụng realtime dùng TCP hoặc WebSocket.

Sau bài học, bạn có thể:

- Phân biệt transport reconnect, tạo RSocket session mới và RESUME một session cũ.
- Giải thích điều kiện để RSocket resumption thành công và những trường hợp phải fallback.
- Đọc ý nghĩa của RESUME, RESUME_OK và REJECTED_RESUME.
- Theo dõi LEASE, TTL và số request được cấp.
- Phân biệt lease-based admission control với backpressure REQUEST_N.
- Phân loại lỗi TCP, TLS, WebSocket, SETUP và lỗi từng stream.
- Theo dõi các mã INVALID_SETUP, UNSUPPORTED_SETUP, REJECTED_SETUP, CONNECTION_ERROR và CONNECTION_CLOSE.
- Thiết kế metric, log, trace và alert cho lifecycle của connection.
- Kiểm thử reconnect storm, resume rejection, lease exhaustion và setup failure.

## 1. Quan sát theo từng lớp của kết nối

Một interaction RSocket đi qua nhiều giai đoạn. Transport có thể kết nối thành công nhưng SETUP chưa được chấp nhận; connection có thể ổn định nhưng một stream riêng lẻ vẫn lỗi.

~~~mermaid
flowchart TD
    A[Client starts connection] --> B[Transport connect]
    B -->|TCP / TLS / WebSocket error| X[Transport failure telemetry]
    B -->|Connected| C[Send SETUP]
    C -->|ERROR on stream 0| Y[Setup failure telemetry]
    C -->|Accepted| D[RSocket session active]
    D --> E[KEEPALIVE and optional LEASE]
    E --> F[Interactions and streams]
    F -->|Stream ERROR| Z[Stream failure telemetry]
    D -->|Transport lost| G[Reconnect decision]
    G --> H{Resume supported and state retained?}
    H -->|Yes| I[Send RESUME]
    I -->|RESUME_OK| D
    I -->|REJECTED_RESUME| J[New session / application recovery]
    H -->|No| J
    J --> C
~~~

Nên tách ít nhất các khái niệm sau:

| Khái niệm | Ý nghĩa | Phạm vi quan sát |
|---|---|---|
| Transport connection | TCP hoặc WebSocket đã mở | Socket, TLS, handshake, close |
| RSocket SETUP | Hai peer thống nhất tham số ban đầu | Connection-level protocol |
| RSocket session | Ngữ cảnh protocol gắn với connection và có thể hỗ trợ resume | Session/resume state |
| Interaction | Request-response, FNF, stream hoặc channel | Stream ID và route |
| Lease | Quyền gửi một số request trong thời hạn | Admission control theo peer |
| Application workflow | Công việc nghiệp vụ có thể tồn tại qua nhiều session | Request ID, cursor, idempotency |

Không gộp mọi lỗi vào một metric tên connection_error. Nếu WebSocket handshake thất bại, RSocket SETUP chưa chạy. Nếu SETUP bị từ chối, TCP có thể đã hoạt động bình thường. Nếu một stream nhận APPLICATION_ERROR, connection có thể vẫn phục vụ các stream khác.

## 2. Phân biệt reconnect, RESUME và application retry

Ba hành động thường bị gọi chung là reconnect nhưng có ngữ nghĩa khác nhau.

| Cơ chế | Điều xảy ra | Trạng thái interaction cũ |
|---|---|---|
| Transport reconnect | Mở lại TCP/WebSocket | Chưa khôi phục session hay stream |
| RSocket RESUME | Dùng token và vị trí frame để tiếp tục session cũ | Có thể tiếp tục nếu hai phía còn đủ state |
| Application retry/recovery | Tạo interaction mới theo logic nghiệp vụ | Cần request ID, cursor hoặc idempotency để tránh trùng |

### Transport reconnect

Client mở một transport connection mới sau khi socket cũ bị đóng hoặc timeout. Nếu client gửi SETUP mới, đó là quá trình thiết lập một RSocket connection/session mới. Các interaction cũ không tự động sống lại chỉ vì transport mới đã mở.

Ứng dụng phải quyết định cách phục hồi:

- Request-response: gọi lại bằng idempotency key hoặc truy vấn kết quả theo request ID.
- Request-stream: mở stream mới từ cursor hoặc sequence đã lưu.
- Request-channel: thiết lập channel mới và khôi phục trạng thái ứng dụng theo giao thức riêng.
- Fire-and-forget: nếu cần biết đã xử lý hay chưa, phải có ACK hoặc cơ chế truy vấn/deduplication ở tầng ứng dụng.

### RSocket RESUME

RESUME là khả năng tùy chọn của protocol để khôi phục hoạt động trên một transport mới trong khi giữ session state. Mặc định không nên giả định peer hỗ trợ resume nếu chưa cấu hình/xác nhận rõ. Client dùng resume identification token từ SETUP ban đầu và vị trí frame đã nhận/đã giữ. Server chỉ chấp nhận nếu nhận diện được session và còn đủ frame/state để tiếp tục.

~~~mermaid
sequenceDiagram
    participant C as RSocket requester
    participant S as RSocket responder
    C->>S: SETUP (resume enabled, token)
    S-->>C: Session active
    C->>S: REQUEST / PAYLOAD frames
    Note over C,S: Transport connection bị mất
    C->>S: New TCP/WebSocket connection
    C->>S: RESUME (token, positions)
    alt Session state còn đủ
        S-->>C: RESUME_OK
        Note over C,S: Tiếp tục frame sequence và stream state
    else Không thể phục hồi
        S-->>C: ERROR[REJECTED_RESUME]
        Note over C,S: Client chuyển sang application recovery
    end
~~~

Resumption không phải cơ chế đảm bảo luôn thành công. Nó được thiết kế cho mất kết nối tạm thời trong khi cả hai phía vẫn giữ state cần thiết. Nếu server restart và mất resume state, token hết thời hạn, buffer không còn các frame cần phát lại hoặc peer không hỗ trợ resume, client không thể khôi phục session cũ.

### Application retry/recovery

Khi RESUME không được hỗ trợ hoặc bị từ chối, ứng dụng có thể mở một session mới rồi phục hồi nghiệp vụ. Đây là một quy trình riêng:

- Dùng request ID ổn định cho command.
- Dùng idempotency key cho thao tác có side effect.
- Dùng cursor/sequence cho event stream.
- Truy vấn trạng thái nếu kết quả trước timeout chưa xác định.
- Không tự gửi lại một command ghi dữ liệu với ID mới.

Không ghi nhận application retry như một lần RESUME thành công. Hai sự kiện cần metric và log riêng.

## 3. KEEPALIVE và phát hiện kết nối mất

SETUP mang các tham số KEEPALIVE: khoảng thời gian requester dự kiến gửi KEEPALIVE và thời gian tối đa nó chờ phản hồi trước khi coi peer không còn hoạt động. KEEPALIVE giúp phát hiện connection chết khi không có traffic nghiệp vụ.

Một kết nối có thể mất mà không nhận được FIN/RST rõ ràng, ví dụ thiết bị di động đổi mạng, NAT hết hạn mapping hoặc proxy đóng tunnel. KEEPALIVE giúp phát hiện tình trạng đó sau một khoảng thời gian.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: KEEPALIVE (periodic)
    S-->>C: KEEPALIVE response
    C->>S: KEEPALIVE (next interval)
    Note over C,S: Response không đến trong max lifetime
    C->>C: Mark transport/session unavailable
    C->>S: Reconnect or RESUME
~~~

Cần phân biệt:

- KEEPALIVE là frame của RSocket protocol.
- TCP keepalive là cơ chế ở tầng TCP và có cấu hình riêng.
- WebSocket ping/pong là control frame của WebSocket.
- Timeout của reverse proxy hoặc NAT có thể đóng connection độc lập với các cơ chế trên.

Không nên đặt KEEPALIVE interval lớn hơn idle timeout của proxy nếu hệ thống cần giữ connection qua proxy. Cũng không nên đặt quá thấp một cách tùy tiện: hàng nghìn client có thể tạo nhiều frame kiểm tra và reconnect cùng lúc khi mạng chập chờn.

Theo dõi:

- Số KEEPALIVE gửi và nhận.
- Số lần max lifetime bị vượt.
- Thời gian từ KEEPALIVE cuối tới lúc phát hiện connection chết.
- Close reason từ transport/proxy nếu có.
- Tỷ lệ reconnect sau KEEPALIVE timeout.

Protocol KEEPALIVE không chứng minh service nghiệp vụ khỏe. Một process có thể trả KEEPALIVE trong khi database hoặc dependency nghiệp vụ đang lỗi. Cần health check và business telemetry riêng.

## 4. RSocket RESUME hoạt động thế nào?

Resumption phải được bật và hỗ trợ ở cả hai phía. Trong SETUP, requester đặt cờ resume enable và gửi resume identification token. Khi transport mất, client tạo transport mới và gửi RESUME thay cho SETUP.

RESUME chứa thông tin nhận diện session cùng vị trí frame theo hai chiều. Protocol theo dõi vị trí của các REQUEST, CANCEL, ERROR và PAYLOAD frame; RESUME/RESUME_OK dùng các vị trí này để hai phía xác định phần nào cần tiếp tục hoặc phát lại.

Các bước chính:

1. Client và server thiết lập session ban đầu với resume được bật.
2. Hai phía duy trì resume state và các frame cần thiết.
3. Transport cũ bị mất.
4. Client mở transport mới.
5. Client gửi RESUME với token của SETUP ban đầu và vị trí frame.
6. Server xác định session và kiểm tra dữ liệu còn đủ để tiếp tục.
7. Nếu chấp nhận, server gửi RESUME_OK.
8. Hai phía tiếp tục theo vị trí frame đã thống nhất.

### Điều kiện để resume thành công

- Cả requester và responder hỗ trợ resumption.
- Resume token hợp lệ và ánh xạ tới session còn tồn tại.
- Server giữ session state trong thời gian client có thể thử resume.
- Các frame cần thiết vẫn nằm trong buffer/resume store.
- Vị trí frame client gửi phù hợp với vùng dữ liệu server còn giữ.
- Transport mới có thể kết nối tới peer đang giữ session state hoặc tới nơi state được chia sẻ/phục hồi.

Nếu client kết nối tới một instance khác mà instance đó không có resume state, RESUME có thể bị từ chối. Sticky routing hoặc chia sẻ resume state có thể giúp, nhưng cần được triển khai rõ ràng.

### REJECTED_RESUME và fallback

Khi nhận ERROR[REJECTED_RESUME], client không được tiếp tục thử RESUME cho session đó. Ứng dụng cần kết thúc nhánh resume và quyết định có thiết lập session mới hay không.

Một quy trình fallback an toàn:

1. Ghi nhận resume rejection cùng lý do đã được làm sạch.
2. Đánh dấu session cũ không thể phục hồi.
3. Tạo connection mới bằng SETUP nếu policy cho phép.
4. Khôi phục các subscription bằng cursor/sequence.
5. Retry command chỉ với idempotency key ổn định hoặc truy vấn trạng thái trước.
6. Phát metric riêng cho application recovery sau resume failure.

### Lease sau khi resume

Lease không mặc nhiên được kế thừa qua session resume. Sau khi resumption thành công, semantics của LEASE phải được khởi động lại trên connection mới bằng LEASE frame từ responder. Vì vậy client cần theo dõi lease grant sau resume, không giả định request quota cũ vẫn còn hiệu lực.

## 5. Quan sát resume token và resume buffer

Resume identification token là thông tin dùng để tìm session. Không ghi token thô vào log, trace hoặc metric label. Nếu cần liên kết sự kiện, dùng một session reference đã băm hoặc ID nội bộ không thể dùng để resume.

Các tín hiệu nên theo dõi:

| Tín hiệu | Ý nghĩa |
|---|---|
| resume enabled | SETUP đã yêu cầu resume |
| resume attempts | Số lần client bắt đầu RESUME |
| resume accepted | Server gửi RESUME_OK |
| resume rejected | Server từ chối session |
| resume latency | Thời gian từ khi bắt đầu RESUME tới kết quả |
| reconnect downtime | Thời gian interaction/session bị gián đoạn |
| replayed frames/bytes | Lượng frame được phát lại nếu implementation cung cấp |
| resume buffer usage | Dung lượng frame giữ lại |
| resume state expired | Session hết thời hạn có thể phục hồi |

Không phải implementation nào cũng công khai toàn bộ buffer positions hoặc số byte replay. Nếu không có API/metric chính thức, có thể instrument ở transport/interceptor layer hoặc chỉ đo số lần, latency và kết quả resume. Không suy ra số frame replay từ số request nghiệp vụ.

### Ví dụ log có cấu trúc

~~~json
{
  "event": "rsocket.resume.completed",
  "service": "order-service",
  "remoteService": "inventory-service",
  "transport": "tcp",
  "outcome": "accepted",
  "durationMs": 42,
  "sessionRef": "sha256:8b6d...",
  "resumeBufferBytes": 16384
}
~~~

sessionRef ở ví dụ là định danh quan sát đã được băm, không phải resume token. Không log payload, authentication metadata hoặc token gốc.

## 6. LEASE là gì?

LEASE là cơ chế admission control của RSocket. Responder cấp cho peer một số lượng request được phép khởi tạo trong một khoảng thời gian (TTL). LEASE frame chứa TTL và số request được cấp. Khi peer đã dùng hết quota hoặc TTL hết hạn, nó phải đợi lease mới trước khi gửi thêm request nếu SETUP đã thương lượng sẽ tuân thủ lease.

LEASE không phải là:

- Giới hạn số response item của một request-stream.
- Thay thế Reactive Streams backpressure REQUEST_N.
- Một semaphore tự động bảo vệ mọi tài nguyên nội bộ.
- Bằng chứng một request đã được xử lý thành công.
- Một queue tự động giữ request cho tới khi có lease mới.

~~~mermaid
sequenceDiagram
    participant R as Requester
    participant S as Responder
    R->>S: SETUP (L flag: will honor lease)
    S-->>R: LEASE (TTL, request count)
    R->>S: REQUEST_RESPONSE
    R->>S: REQUEST_STREAM
    Note over R: Request budget decreases
    Note over R: Budget exhausted or TTL expires
    R->>R: Stop sending new requests
    S-->>R: LEASE (new TTL, request count)
    R->>S: Next request
~~~

Cờ L trong SETUP cho biết requester sẽ tuân thủ lease. Nếu cờ này được bật, requester phải chờ LEASE trước khi gửi request. Nếu không bật, requester có thể gửi request ngay và không bị ràng buộc bởi lease của peer theo cơ chế này.

Hai phía đều có thể đóng vai requester/responder theo chiều interaction; lease áp dụng theo chiều peer được cấp quyền gửi request. Đừng nhầm chiều cấp lease với chiều phát response payload.

## 7. Theo dõi lease grant, TTL và request budget

Một lease có hai thông tin vận hành quan trọng:

- TTL: thời gian lease còn hiệu lực.
- Request count: số request mới được phép gửi trong thời hạn đó.

Khi quan sát, nên ghi:

- Số LEASE frame nhận/gửi.
- TTL được cấp (phân bố hoặc histogram).
- Request count được cấp.
- Số request đã sử dụng trong lease.
- Số request còn lại nếu implementation cung cấp.
- Số lần hết quota.
- Thời gian chờ lease mới.
- Số request bị từ chối hoặc xếp hàng ở application layer vì chưa có lease.

Request count là ngân sách cho số interaction request mới, không phải số PAYLOAD frame. Một request-stream chỉ tiêu thụ một lượt request khi khởi tạo, dù sau đó có thể phát nhiều response item theo demand.

### Khi lease hết hạn

Nếu TTL hết hạn hoặc request budget đã dùng hết, requester không được khởi tạo thêm request cho tới khi có lease phù hợp tiếp theo. Protocol không tự quyết định ứng dụng nên queue, reject hay drop công việc đang chờ. Đây là trách nhiệm của ứng dụng.

Một client có thể chọn:

- Queue command trong một hàng đợi có giới hạn.
- Trả lỗi overload/retry-after cho caller.
- Drop telemetry có thể mất.
- Giảm tốc producer hoặc từ chối nhận công việc mới.
- Phân phối request sang peer khác có lease còn hiệu lực, nếu nghiệp vụ và routing cho phép.

Không giữ queue vô hạn khi lease không được cấp lại. Queue phải có giới hạn, deadline và metric để tránh biến admission control thành memory exhaustion.

### Lease sau reconnect/resume

Sau khi tạo session mới, lease được thương lượng lại theo SETUP. Sau RESUME, lease semantics cũng phải được khởi động lại bằng LEASE frame mới. Client cần chuyển trạng thái admission về "chưa có quota" cho tới khi nhận grant mới nếu nó đang tuân thủ lease.

## 8. Phân biệt LEASE với REQUEST_N và backpressure

Hai cơ chế đều điều tiết nhưng ở hai hướng và hai cấp khác nhau.

| Cơ chế | Điều tiết cái gì? | Hướng tác động |
|---|---|---|
| LEASE | Số interaction request mới được phép khởi tạo trong TTL | Responder cấp quyền cho requester |
| REQUEST_N | Số response item mà requester sẵn sàng nhận trên một stream | Subscriber/requester điều khiển demand |
| Application queue | Công việc chờ trước khi gửi request | Logic ứng dụng |
| Connection limit | Số transport connection/session | Hạ tầng hoặc client pool |

Ví dụ một client có lease 20 request trong 5 giây. Client mở một request-stream, sau đó yêu cầu 100 response item bằng REQUEST_N. Lease tiêu thụ một request để khởi tạo stream; REQUEST_N điều khiển số item server được phép phát tiếp theo demand.

Không tăng request budget chỉ vì subscriber đã yêu cầu thêm response item. Ngược lại, nhận thêm lease không tự động làm subscriber có demand lớn hơn.

## 9. SETUP là ranh giới bắt đầu protocol session

Sau khi transport kết nối thành công, client gửi SETUP frame với Stream ID 0. SETUP truyền tham số protocol và khả năng kết nối như:

- Protocol major/minor version.
- KEEPALIVE interval và max lifetime.
- Resume enable flag và resume token nếu dùng.
- Lease flag nếu requester sẽ tuân thủ lease.
- Data MIME type.
- Metadata MIME type.
- Setup payload theo implementation/application.

Server chấp nhận hoặc từ chối SETUP. Nếu từ chối, server gửi ERROR connection-level (Stream ID 0) rồi đóng kết nối. Các mã cần phân biệt theo giai đoạn:

| Giai đoạn | Mã lỗi | Ý nghĩa |
|---|---|---|
| SETUP | INVALID_SETUP | SETUP không hợp lệ |
| SETUP | UNSUPPORTED_SETUP | Một hoặc nhiều tham số SETUP không được hỗ trợ |
| SETUP | REJECTED_SETUP | Server từ chối thiết lập theo policy |
| RESUME | REJECTED_RESUME | Không chấp nhận khôi phục session cũ |
| Connection lifecycle | CONNECTION_ERROR | Kết nối bị kết thúc; peer có thể đóng ngay |
| Connection lifecycle | CONNECTION_CLOSE | Kết nối sẽ đóng sau khi các stream đang chạy kết thúc theo protocol |

Lỗi SETUP khác lỗi của một interaction. ERROR với Stream ID 0 liên quan đến connection, bao gồm thiết lập phiên. ERROR với Stream ID lớn hơn 0 liên quan tới một stream cụ thể.

### Những nguyên nhân SETUP thường gặp

- Client và server không tương thích protocol version.
- Data hoặc metadata MIME type không được hỗ trợ.
- Server không chấp nhận setup payload hoặc metadata bắt buộc.
- Client yêu cầu resume nhưng server không hỗ trợ.
- Chính sách bảo mật hoặc admission của ứng dụng từ chối kết nối.
- Server đang draining hoặc không còn nhận session mới.

Cần log error code và lý do an toàn từ ERROR frame, nhưng không gửi thông tin nội bộ hoặc credential vào log.

## 10. Phân biệt lỗi transport với lỗi SETUP

Một kết nối có thể thất bại trước khi RSocket gửi SETUP. Các lỗi đó không phải ERROR frame của RSocket.

| Lớp | Ví dụ lỗi | Dấu hiệu quan sát |
|---|---|---|
| DNS | Không resolve được hostname | UnknownHostException, DNS failure |
| TCP | Connection refused, reset, timeout | ConnectException, SocketException |
| TLS | Certificate invalid, handshake failure | SSLHandshakeException |
| HTTP/WebSocket | Upgrade bị từ chối, sai path, Origin không hợp lệ | HTTP status/handshake exception |
| RSocket SETUP | Invalid/unsupported/rejected setup | ERROR stream ID 0 |
| RSocket RESUME | Session không thể phục hồi | ERROR[REJECTED_RESUME] |
| Interaction | Route, validation hoặc nghiệp vụ lỗi | ERROR stream ID > 0 hoặc application onError |

Nếu chỉ ghi "RSocket connection failed", người vận hành không biết nên kiểm tra DNS, firewall, certificate, reverse proxy, MIME type hay cấu hình protocol. Hãy phân loại ngay ở ranh giới nơi lỗi xảy ra.

## 11. Phân biệt connection-level ERROR và stream-level ERROR

RSocket dùng ERROR frame cho cả connection và interaction. Stream ID giúp xác định phạm vi:

- Stream ID = 0: lỗi connection hoặc setup/resume.
- Stream ID > 0: lỗi của một interaction.

Một số mã stream-level:

| Mã | Ý nghĩa |
|---|---|
| APPLICATION_ERROR | Logic ứng dụng phát Reactive Streams onError |
| REJECTED | Responder từ chối request và bảo đảm chưa xử lý request |
| CANCELED | Responder hủy request; có thể đã bắt đầu xử lý nên side effect chưa chắc bằng không |
| INVALID | Request không hợp lệ |

Sự khác nhau giữa REJECTED và CANCELED quan trọng khi retry command. REJECTED bảo đảm responder chưa xử lý request; CANCELED không bảo đảm điều đó. Với timeout hoặc CANCELED, hãy xem kết quả nghiệp vụ là chưa xác định nếu chưa có idempotency/status lookup.

Không đánh dấu toàn connection unhealthy chỉ vì một stream gặp APPLICATION_ERROR do dữ liệu đầu vào không hợp lệ. Ngược lại, một connection-level CONNECTION_ERROR cần được ghi nhận ở tầng session và có thể ảnh hưởng nhiều stream.

## 12. Bộ metric cho connection lifecycle

Nên thiết kế metric theo outcome, transport và loại sự kiện. Tên dưới đây là gợi ý, có thể điều chỉnh theo convention của hệ thống.

| Metric | Loại | Mục đích |
|---|---|---|
| rsocket.connection.attempts | Counter | Số lần bắt đầu transport connect |
| rsocket.connection.established | Counter | Số transport connection mở thành công |
| rsocket.connection.closed | Counter | Số connection đóng |
| rsocket.setup.duration | Timer | Thời gian từ connect tới SETUP accepted |
| rsocket.setup.failures | Counter | SETUP bị từ chối hoặc lỗi |
| rsocket.reconnect.attempts | Counter | Số lần reconnect |
| rsocket.reconnect.success | Counter | Reconnect thành công |
| rsocket.resume.attempts | Counter | Số RESUME frame/operation bắt đầu |
| rsocket.resume.success | Counter | RESUME_OK nhận được |
| rsocket.resume.rejected | Counter | RESUME bị từ chối |
| rsocket.resume.duration | Timer | Thời gian hoàn tất resume |
| rsocket.resume.buffer.bytes | Gauge | Dung lượng resume buffer nếu có |
| rsocket.lease.received | Counter | Số LEASE frame nhận được |
| rsocket.lease.ttl | Distribution summary/histogram | TTL được cấp |
| rsocket.lease.request_budget | Distribution summary/histogram | Request count được cấp |
| rsocket.lease.exhausted | Counter | Số lần cạn request budget |
| rsocket.setup.error | Counter | Lỗi SETUP theo code |
| rsocket.connection.error | Counter | Lỗi connection-level |
| rsocket.stream.error | Counter | Lỗi stream-level |

### Tag nên dùng

Tag có cardinality kiểm soát:

- service
- peer/service name
- transport: tcp hoặc websocket
- outcome: success, timeout, rejected, error
- error_code
- interaction_type
- zone/region
- protocol_version

Không dùng các giá trị biến thiên cao làm metric tag:

- session token.
- resume token.
- requestId duy nhất.
- streamId.
- userId hoặc tenantId tùy ý.
- remote ephemeral port.

Những giá trị này phù hợp hơn với log hoặc trace đã kiểm soát quyền truy cập. Metric label có cardinality quá cao sẽ làm tăng chi phí bộ nhớ và truy vấn của hệ thống metrics.

## 13. Log có cấu trúc cho reconnect và SETUP

Mỗi sự kiện lifecycle nên có event name ổn định, outcome và thông tin đủ để nối các bước.

Ví dụ reconnect:

~~~json
{
  "event": "rsocket.reconnect.started",
  "service": "order-service",
  "peer": "inventory-service",
  "transport": "tcp",
  "attempt": 3,
  "reason": "keepalive_timeout",
  "backoffMs": 800
}
~~~

Ví dụ SETUP bị từ chối:

~~~json
{
  "event": "rsocket.setup.failed",
  "service": "order-service",
  "peer": "inventory-service",
  "transport": "tcp",
  "errorCode": "UNSUPPORTED_SETUP",
  "protocolVersion": "1.0",
  "dataMimeType": "application/json",
  "metadataMimeType": "message/x.rsocket.composite-metadata.v0"
}
~~~

Ví dụ lease cạn:

~~~json
{
  "event": "rsocket.lease.exhausted",
  "service": "order-service",
  "peer": "inventory-service",
  "remainingRequests": 0,
  "leaseTtlRemainingMs": 120
}
~~~

Ví dụ trên minh họa trường log; chỉ ghi remainingRequests hoặc TTL nếu implementation thực sự cung cấp. Không tự suy ra quota còn lại bằng cách đếm request nếu có nhiều producer hoặc request bị hủy giữa chừng.

### Không log bí mật

- Không log resume token.
- Không log authentication token hoặc password.
- Không log nguyên metadata nếu có tenant credential hoặc PII.
- Không log stack trace vào metric label.
- Làm sạch error data từ peer trước khi ghi vì nội dung đó có thể chứa dữ liệu không tin cậy.

Dùng session reference đã băm nếu cần liên kết các sự kiện cùng phiên. Phải giữ secret hashing key an toàn và không biến session reference thành token có thể dùng lại.

## 14. Trace theo connection và interaction

Connection có vòng đời dài, còn interaction có thời lượng ngắn hoặc stream dài. Không nên tạo một span khổng lồ kéo dài nhiều ngày cho toàn bộ connection rồi đặt tất cả request làm child span.

Có thể quan sát theo các lớp:

- Event/span ngắn cho transport connect.
- Event/span cho SETUP negotiation.
- Event/span cho mỗi reconnect attempt.
- Event/span cho mỗi RESUME attempt và kết quả.
- Span cho request-response hoặc request-FNF.
- Span lifecycle cho request-stream/channel với policy phù hợp; với stream dài, dùng event hoặc link để tránh span giữ quá lâu.
- Propagate trace context qua metadata theo chuẩn tracing mà hệ thống chọn.

Ví dụ trace:

~~~text
order.create
  ├─ rsocket.connect
  ├─ rsocket.setup
  ├─ inventory.reserve
  ├─ rsocket.transport_lost
  ├─ rsocket.resume
  └─ inventory.reserve.response
~~~

Nếu RESUME khôi phục stream, cần liên kết event resume với trace/request context trước đó khi implementation cung cấp. Nếu application recovery tạo interaction mới, có thể dùng span link tới trace cũ thay vì giả vờ đó là cùng một request execution.

Không truyền trace context trong một custom format không được thống nhất giữa các dịch vụ. Dùng W3C Trace Context hoặc convention tracing đã chọn và kiểm thử extractor/propagator ở cả hai phía.

## 15. Ví dụ instrument quá trình connect và SETUP trong Spring

RSocketRequester kết nối bất đồng bộ. Có thể đo thời gian connect/SETUP ở lớp tạo requester bằng Reactor hooks và Micrometer. Ví dụ dưới đây chỉ đo kết quả của thao tác connect; nó không tự đo từng frame RESUME hoặc LEASE.

~~~java
@Component
public class ObservedRSocketConnector {

    private final RSocketStrategies strategies;
    private final MeterRegistry registry;

    public ObservedRSocketConnector(
            RSocketStrategies strategies,
            MeterRegistry registry) {
        this.strategies = strategies;
        this.registry = registry;
    }

    public Mono<RSocketRequester> connectTcp(
            String host,
            int port) {

        return Mono.defer(() -> {
            Timer.Sample sample = Timer.start(registry);

            return RSocketRequester.builder()
                .rsocketStrategies(strategies)
                .connectTcp(host, port)
                .doOnSuccess(requester -> {
                    sample.stop(
                        Timer.builder("rsocket.setup.duration")
                            .tag("transport", "tcp")
                            .tag("outcome", "success")
                            .register(registry)
                    );

                    registry.counter(
                        "rsocket.setup.success",
                        "transport", "tcp"
                    ).increment();
                })
                .doOnError(error -> {
                    sample.stop(
                        Timer.builder("rsocket.setup.duration")
                            .tag("transport", "tcp")
                            .tag("outcome", "error")
                            .register(registry)
                    );

                    registry.counter(
                        "rsocket.setup.failures",
                        "transport", "tcp",
                        "error_type", classify(error)
                    ).increment();
                });
        });
    }

    private String classify(Throwable error) {
        // Map exception classes to a small, stable set of categories.
        return "connect_or_setup";
    }
}
~~~

Tên metric và phân loại exception cần điều chỉnh theo implementation đang dùng. connectTcp có thể thất bại ở transport hoặc trong quá trình protocol setup; nếu cần tách chính xác, hãy instrument transport connect và RSocket setup ở tầng connector/transport nơi có đủ thông tin.

Đừng thêm retry vô hạn vào method connect. Reconnect policy cần backoff, jitter, deadline, giới hạn attempt và phối hợp với lifecycle của connection pool.

## 16. Theo dõi LEASE và RESUME ở tầng protocol

RSocketRequester là abstraction cấp ứng dụng. Nó không nhất thiết công khai mọi chi tiết frame mà đội vận hành muốn quan sát. Nếu cần metric chính xác cho LEASE, RESUME, RESUME_OK hoặc ERROR frame, có thể cần instrumentation tại RSocketConnector, interceptor, transport hoặc protocol implementation mà ứng dụng sử dụng.

Khi instrument ở tầng thấp:

- Đếm frame theo loại và outcome.
- Đọc error code và stream ID để phân biệt connection/stream.
- Đo TTL/request count của LEASE.
- Không ghi token hoặc payload nhạy cảm.
- Tránh làm chậm event-loop bằng logging đồng bộ.
- Không parse frame hai lần nếu implementation đã có hook chính thức.
- Pin phiên bản library và kiểm thử interceptor khi nâng cấp.

Nếu implementation không cung cấp resume buffer size hoặc frame replay count, đừng tạo metric giả. Ghi rõ metric không khả dụng và quan sát kết quả resume, latency cùng downtime ở mức session.

## 17. Alert và ngưỡng vận hành

Alert cần phản ánh ảnh hưởng tới người dùng và khả năng phục hồi, không chỉ đếm một sự kiện đơn lẻ.

| Alert | Dấu hiệu | Điều cần kiểm tra |
|---|---|---|
| Setup failure spike | Tỷ lệ SETUP lỗi tăng | Protocol/MIME version, auth policy, rollout |
| Reconnect storm | Reconnect rate tăng đột biến | Network, proxy timeout, deploy, keepalive |
| Resume rejection spike | REJECTED_RESUME tăng | Server restart, session affinity, buffer/lifetime |
| Resume latency high | RESUME mất nhiều thời gian | Transport, replay volume, server load |
| Lease starvation | Request thường xuyên chờ lease | Lease TTL/quota, server admission, traffic burst |
| Lease not renewed | Không nhận grant mới trước khi hết hạn | Responder, connection state, implementation |
| Connection churn | Open/close tăng liên tục | Pool lifecycle, health flapping, idle timeout |
| Stream error spike | APPLICATION_ERROR/INVALID tăng | Route, schema, business validation |
| Setup latency high | Connect thành công nhưng setup chậm | Server initialization, TLS/proxy, setup handler |

Nên đặt alert theo tỷ lệ và cửa sổ thời gian, có baseline theo service/transport. Ví dụ một resume rejection trong một ngày có thể bình thường; tỷ lệ rejection tăng mạnh sau rollout có thể là dấu hiệu server mới không chia sẻ resume state.

## 18. Ma trận chẩn đoán

| Triệu chứng | Lớp có khả năng | Bằng chứng cần lấy |
|---|---|---|
| Không mở được socket | DNS/TCP | Resolve, connect timeout/refused |
| TLS handshake thất bại | TLS | Certificate chain, hostname, truststore |
| WebSocket không upgrade | HTTP/WebSocket | Status code, path, Origin, proxy log |
| SETUP bị INVALID_SETUP | RSocket setup | Protocol version, frame parameters |
| SETUP bị UNSUPPORTED_SETUP | RSocket setup | MIME types, extension, capability |
| SETUP bị REJECTED_SETUP | Server policy | Setup payload, authentication/admission reason |
| RESUME bị REJECTED_RESUME | Session recovery | Token lookup, session TTL, retained positions |
| Reconnect thành công nhưng stream không tiếp tục | Application recovery | Có dùng SETUP mới thay vì RESUME? cursor có được lưu? |
| Request bị chặn dù connection khỏe | Lease | L flag, lease TTL, request budget |
| Một stream lỗi nhưng connection còn mở | Stream | Stream ID, route, APPLICATION_ERROR/INVALID |
| Nhiều client cùng reconnect | Network/timeout | Proxy idle timeout, keepalive, backoff/jitter |

Một lỗi chỉ nên được quy về đúng lớp khi có bằng chứng. Ví dụ ECONNRESET là lỗi transport; UNSUPPORTED_SETUP là lỗi protocol negotiation; APPLICATION_ERROR là lỗi interaction. Không chuyển tất cả thành một mã "server unavailable".

## 19. Kiểm thử reconnect, resume và lease

Kiểm thử happy path không đủ để chứng minh lifecycle được quan sát đúng. Cần mô phỏng transport loss, resume state mất, lease hết hạn và setup rejection.

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| TCP/WebSocket mất tạm thời, state còn đủ | Client reconnect và RESUME_OK |
| Server không hỗ trợ resume | SETUP resume bị từ chối theo protocol |
| Resume token không còn hợp lệ | REJECTED_RESUME, client ngừng thử resume session đó |
| Resume buffer không còn frame cần thiết | Resume bị từ chối hoặc fallback theo implementation |
| Server restart mất session state | Client tạo session mới và application recovery |
| Lease flag bật | Client chờ LEASE trước request đầu tiên |
| Request budget cạn | Client không gửi request mới cho tới lease tiếp theo |
| TTL hết hạn | Lease cũ không còn được sử dụng |
| Resume thành công | Client chờ lease mới nếu lease semantics được dùng |
| MIME type không hỗ trợ | SETUP thất bại với error phù hợp |
| Một stream bị APPLICATION_ERROR | Connection vẫn có thể phục vụ stream khác |
| Proxy idle timeout | Keepalive/timeout telemetry chỉ ra tầng đóng kết nối |
| Nhiều client reconnect cùng lúc | Backoff/jitter tránh reconnect storm |

### Kiểm thử application reconnect sau resume rejection

Tạo một request có idempotency key, để server commit nhưng làm mất response hoặc làm session không thể resume. Client nhận REJECTED_RESUME hoặc timeout, tạo session mới rồi truy vấn trạng thái hoặc gửi lại cùng idempotency key. Xác nhận server chỉ thực hiện side effect một lần.

### Kiểm thử lease exhaustion

Dùng một peer test có lease request count nhỏ. Gửi đúng số interaction được cấp, xác nhận client dừng gửi request mới, chờ LEASE tiếp theo rồi tiếp tục. Kiểm tra queue ở application layer có giới hạn và timeout.

### Kiểm thử SETUP rejection

Cấu hình server test từ chối một MIME type hoặc setup option. Xác nhận:

- Lỗi được phân loại là setup failure.
- Stream ID được nhận diện là connection-level.
- Metric error code tăng.
- Không ghi token hoặc payload nhạy cảm.
- Client không retry nhanh vô hạn với cùng cấu hình không tương thích.

## 20. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Reconnect thành công nghĩa là session cũ đã phục hồi | SETUP mới tạo session mới; chỉ RESUME mới thử khôi phục session cũ |
| RSocket RESUME luôn thành công | Resume là tùy chọn và phụ thuộc state còn được giữ |
| REJECTED_RESUME có thể retry mãi | Không thử RESUME lại cho session đã bị từ chối; chuyển sang application recovery |
| Lease là backpressure của response stream | Lease giới hạn request mới; REQUEST_N điều khiển response demand |
| Lease quota cũ còn sau resume | Lease phải được cấp lại trên connection được resume |
| SETUP error và TCP error là một loại | TCP/TLS/WebSocket có thể thất bại trước khi RSocket SETUP chạy |
| Mọi ERROR frame làm connection đóng | Stream-level ERROR có thể chỉ kết thúc một interaction |
| CANCELED bảo đảm server chưa xử lý | Server có thể đã bắt đầu xử lý; side effect chưa chắc bằng không |
| KEEPALIVE chứng minh business service khỏe | Nó chỉ cho biết peer/connection phản hồi protocol keepalive |
| Log resume token giúp debug | Token là dữ liệu nhạy cảm; dùng session reference đã băm |
| Chỉ cần đo số connection đang mở | Cần đo setup, reconnect, resume, lease và stream outcome |

## 21. Quy trình xây dựng observability

Khi triển khai RSocket trong môi trường production, hãy thực hiện theo thứ tự:

1. Định nghĩa lifecycle event cho transport, SETUP, session, RESUME, LEASE và stream.
2. Tách lỗi trước protocol khỏi ERROR frame connection-level và stream-level.
3. Ghi nhận transport type, protocol version và MIME type đã thương lượng.
4. Đo reconnect attempt, outcome, downtime và backoff.
5. Đo resume attempt, RESUME_OK, REJECTED_RESUME và buffer usage nếu có.
6. Đo LEASE TTL, request count, exhaustion và thời gian chờ grant mới.
7. Đo setup duration và phân loại error code.
8. Propagate trace context qua metadata đã thống nhất.
9. Giới hạn metric cardinality; không đưa token, session ID hoặc request ID vào tag.
10. Thiết lập alert cho reconnect storm, setup rejection, resume rejection và lease starvation.
11. Kiểm thử transport loss, server restart, buffer expiry, lease exhaustion và stream error.
12. Xác định application recovery bằng idempotency key/cursor khi protocol resume không thể tiếp tục.

Quan sát đúng lifecycle giúp phân biệt sự cố mạng với lỗi cấu hình protocol, sự cố admission với backpressure và phục hồi session với retry nghiệp vụ. Khi mỗi lớp có metric và log riêng, đội vận hành có thể tìm đúng nguyên nhân, giới hạn reconnect storm và xác định liệu dữ liệu đang được tiếp tục từ session cũ hay đang được khôi phục bằng một interaction mới.

## Ghi nhớ

- Transport reconnect chỉ mở lại TCP/WebSocket; nó không tự phục hồi RSocket interaction cũ.
- RESUME là khả năng tùy chọn, cần token và state/frame positions còn đủ ở cả hai phía.
- RESUME_OK xác nhận tiếp tục session; REJECTED_RESUME yêu cầu chuyển sang application recovery.
- Lease không mặc nhiên được kế thừa sau resume; cần LEASE mới.
- LEASE cấp request count trong TTL; REQUEST_N điều tiết response item.
- Khi SETUP bật cờ L, requester phải chờ LEASE trước khi gửi request.
- SETUP dùng Stream ID 0; ERROR stream ID 0 là lỗi connection/setup, còn stream ID lớn hơn 0 là lỗi interaction.
- TCP/TLS/WebSocket handshake failure xảy ra trước RSocket SETUP và cần phân loại riêng.
- KEEPALIVE phát hiện peer không phản hồi protocol, không thay thế business health check.
- Không log resume token hoặc authentication metadata.
- Metric nên tách setup, reconnect, resume, lease và stream; tránh tag có cardinality cao.
- Retry command sau timeout cần idempotency key hoặc truy vấn trạng thái.

## Tài liệu tham khảo

- [RSocket Protocol — SETUP, ERROR, RESUME, LEASE và KEEPALIVE](https://rsocket.io/about/protocol/)
- [RSocket Protocol trên GitHub](https://github.com/rsocket/rsocket/blob/master/Protocol.md)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — RSocketRequester API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [RSocket Java — SetupFrameCodec API](https://javadoc.io/doc/io.rsocket/rsocket-core/latest/io/rsocket/frame/SetupFrameCodec.html)
- [Micrometer — Concepts and meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html)
- [OpenTelemetry — Semantic conventions](https://opentelemetry.io/docs/specs/semconv/)

