# Resumption: resume token và trạng thái cần giữ ở hai phía

Một kết nối realtime có thể bị ngắt khi mạng di động chuyển vùng, Wi-Fi chập chờn, proxy đóng socket hoặc một process được khởi động lại. Với giao tiếp thông thường, client thường mở kết nối mới rồi gọi lại API hoặc đăng ký lại stream. Cách này tạo một phiên mới; các stream đang chạy, demand và những frame chưa được trao đổi có thể không còn.

RSocket có cơ chế **session resumption** để hai phía thử tiếp tục một phiên đã thiết lập sau khi transport bị gián đoạn. Khi resumption được bật và trạng thái cần thiết vẫn còn ở cả client lẫn server, một transport connection mới có thể được dùng để khôi phục phiên cũ và truyền lại những frame còn thiếu. `resume token` giúp hai phía nhận diện phiên có thể khôi phục; replay buffer và vị trí frame giúp xác định dữ liệu nào cần truyền lại.

Resumption không đơn giản là reconnect, cũng không phải một cơ chế lưu message bền vững. Nó phụ thuộc vào việc hai phía giữ đúng trạng thái phiên trong một khoảng thời gian, còn đủ frame để replay và có thể xác thực phiên đang yêu cầu tiếp tục. Bài này giải thích token, trạng thái cần giữ ở mỗi phía, trình tự RESUME/RESUME_OK, giới hạn phục hồi và cách thiết kế ứng dụng Java/Spring Boot quanh cơ chế đó.

## 1. Reconnect và resumption khác nhau thế nào?

**Reconnect** là thiết lập lại transport sau khi kết nối cũ bị mất. Khi reconnect theo cách thông thường, client tạo một phiên RSocket mới bằng `SETUP`; ứng dụng thường phải đăng ký lại stream, tải snapshot mới hoặc khôi phục trạng thái nghiệp vụ.

**Resumption** là tiếp tục phiên RSocket cũ trên transport mới. Hai đầu dùng thông tin nhận diện phiên và vị trí frame đã trao đổi để khôi phục trạng thái protocol, rồi replay dữ liệu còn thiếu. Nếu resumption thành công, các stream đang tồn tại trước khi đứt kết nối có thể tiếp tục mà không cần ứng dụng mở lại từng stream từ đầu.

| Khía cạnh | Reconnect thông thường | RSocket session resumption |
|---|---|---|
| Transport | Tạo kết nối mới | Tạo kết nối mới |
| Phiên RSocket | Tạo phiên mới qua `SETUP` | Tiếp tục phiên cũ nếu còn trạng thái |
| Stream đang chạy | Thường phải mở lại ở tầng ứng dụng | Có thể tiếp tục theo trạng thái stream được giữ |
| Frame đang chờ | Ứng dụng tự quyết định gửi lại | Protocol có thể replay frame còn thiếu từ buffer |
| Demand và vòng đời stream | Ứng dụng thường khởi tạo lại | Trạng thái protocol được phục hồi trong phạm vi implementation lưu giữ |
| Điều kiện thành công | Server chấp nhận phiên mới | Token hợp lệ, session còn hạn và hai phía còn đủ state/frame |

Resumption chỉ có thể hoạt động nếu client và server đều hỗ trợ, được cấu hình và giữ trạng thái tương thích. Bật reconnect hoặc bật TCP keepalive không tự động bật RSocket resumption.

## 2. Resume token là gì?

`resume token` là một giá trị opaque dùng để nhận diện phiên RSocket có thể tiếp tục. Opaque có nghĩa là bên nhận sử dụng token như một định danh, không dựa vào cấu trúc nội bộ hoặc diễn giải ý nghĩa nghiệp vụ của token.

Khi khởi tạo một phiên có hỗ trợ resumption, token được trao đổi trong quá trình thiết lập phiên. Khi transport bị mất và client mở transport mới, client gửi yêu cầu resume kèm token của phiên cũ. Server tra cứu trạng thái resumption tương ứng và quyết định có thể tiếp tục phiên hay không.

Token cần có các đặc tính:

- **Duy nhất trong phạm vi cần thiết:** tránh hai phiên khác nhau vô tình dùng chung một token.
- **Khó đoán:** nếu token có thể bị bên thứ ba đoán hoặc lấy cắp, họ có thể thử tiếp tục phiên của client.
- **Có thời hạn:** token chỉ hợp lệ trong khoảng resumption window đã cấu hình.
- **Gắn với phiên:** token phải trỏ đến đúng state, vị trí frame và chính sách của phiên đó.
- **Được bảo vệ:** không ghi token vào log công khai, URL, metric label hoặc thông báo lỗi.

Resume token không phải access token OAuth, API key hay bằng chứng duy nhất để cấp quyền nghiệp vụ. Nó nhận diện trạng thái phiên protocol. Server vẫn cần xác thực danh tính kết nối mới và kiểm tra quyền truy cập theo chính sách bảo mật của hệ thống. Nếu implementation dùng token như một bí mật bearer, cần bảo vệ nó như credential có khả năng cho phép chiếm phiên.

## 3. Trình tự thiết lập và tiếp tục phiên

Trong phiên đầu tiên, client gửi `SETUP` với thông tin thiết lập RSocket. Nếu bật resumption, phần setup có thêm cờ và token resume. Hai phía tạo trạng thái phiên, sau đó trao đổi các frame và theo dõi vị trí dữ liệu đã nhận.

Khi transport bị ngắt:

1. Client phát hiện connection không còn hoạt động qua lỗi transport hoặc timeout keepalive.
2. Client giữ lại token và trạng thái phiên trong resumption window.
3. Client mở transport mới đến peer và gửi frame `RESUME` cùng token và thông tin vị trí đã trao đổi.
4. Server tìm phiên tương ứng, kiểm tra thời hạn và khả năng replay.
5. Nếu có thể tiếp tục, server trả `RESUME_OK` với thông tin vị trí đã nhận.
6. Hai phía replay các frame còn thiếu theo thứ tự protocol; khi replay bắt kịp, stream tiếp tục trao đổi frame mới.

```mermaid
sequenceDiagram
    participant C as RSocket Client
    participant S as RSocket Server
    C->>S: SETUP (resume enabled, token T)
    S-->>C: Phiên RSocket được thiết lập
    C->>S: PAYLOAD / REQUEST_N / các frame stream
    S-->>C: PAYLOAD / các frame stream
    Note over C,S: Transport bị ngắt; hai phía giữ state trong resume window
    C->>S: Mở transport mới
    C->>S: RESUME (token T, vị trí frame)
    S-->>C: RESUME_OK (vị trí đã nhận)
    Note over C,S: Replay frame còn thiếu theo thứ tự
    C->>S: Frame mới sau khi replay bắt kịp
    S-->>C: Frame mới; stream cũ tiếp tục
```

Nếu server không tìm thấy token, phiên đã hết hạn hoặc một phía không còn giữ đủ frame cần replay, server có thể từ chối resumption. Khi đó client cần chuyển sang quy trình khôi phục ở tầng ứng dụng: tạo phiên mới, tải snapshot, đăng ký lại stream và đối soát dữ liệu.

## 4. Hai loại trạng thái quan trọng: vị trí frame và replay buffer

Resumption cần hai phía biết frame nào đã được peer nhận và frame nào vẫn cần giữ để có thể truyền lại. Vì vậy, mỗi phía cần theo dõi tiến độ theo từng hướng và giữ những frame đã gửi nhưng chưa thể loại bỏ an toàn.

### 4.1. Vị trí frame đã gửi và đã nhận

RSocket sử dụng vị trí tích lũy để biểu diễn tiến độ frame trên connection. Vị trí này cho phép peer xác định phần dữ liệu đã nhận và phần dữ liệu còn thiếu khi resume. Nó là thông tin protocol, không phải sequence number nghiệp vụ do ứng dụng tự gán.

Ở mức khái niệm, mỗi phía cần biết:

- Vị trí cuối cùng mà mình đã gửi.
- Vị trí cuối cùng mà mình biết peer đã nhận.
- Vị trí cuối cùng mà mình đã nhận từ peer.
- Ranh giới replay buffer còn giữ được dữ liệu từ vị trí nào.

Các vị trí này được cập nhật trong quá trình trao đổi frame và keepalive. Không nên tự tạo hoặc sửa các vị trí này ở tầng ứng dụng; RSocket runtime quản lý chúng.

### 4.2. Replay buffer

Mỗi phía cần giữ các frame đã gửi nhưng peer chưa xác nhận đã nhận, để có thể phát lại nếu transport bị ngắt. Khi peer báo đã nhận đến một vị trí mới, các frame cũ hơn vị trí đó có thể được giải phóng khỏi buffer theo quy tắc protocol.

Replay buffer cần có giới hạn về:

- **Dung lượng byte:** tổng dữ liệu frame được giữ.
- **Thời gian lưu:** thời gian tối đa giữ session và frame sau khi transport mất.
- **Số lượng stream/connection:** số phiên đồng thời cần buffer.
- **Kích thước frame:** giới hạn payload để một frame lớn không chiếm hết buffer.
- **Hành vi overflow:** khi không còn chỗ để giữ frame cần thiết, resumption có thể không còn khả thi.

Nếu một phía không còn frame bắt đầu từ vị trí peer cần, không thể replay đầy đủ phiên. Vì vậy, resume window và replay buffer phải được thiết kế cùng nhau. Một khoảng thời gian giữ session dài nhưng buffer quá nhỏ có thể làm resumption thất bại khi lưu lượng cao.

## 5. Trạng thái cần giữ ở client và server

Resumption thành công đòi hỏi cả hai phía giữ state tương ứng. Có thể hình dung state tối thiểu theo nhóm sau:

| Nhóm trạng thái | Client cần giữ | Server cần giữ |
|---|---|---|
| Session identity | Resume token, định danh phiên và thông tin peer | Bản tra cứu token đến session đang được giữ |
| Vị trí protocol | Vị trí frame đã gửi/đã nhận theo từng hướng | Vị trí frame đã gửi/đã nhận theo từng hướng |
| Replay buffer | Frame client đã gửi nhưng chưa được peer xác nhận | Frame server đã gửi nhưng chưa được peer xác nhận |
| Stream registry | Stream ID, kiểu tương tác và trạng thái vòng đời | Stream ID, handler/session tương ứng và trạng thái vòng đời |
| Demand/flow control | Demand response còn lại và trạng thái subscription phía client | Demand request còn lại và trạng thái subscription phía server |
| Thời hạn | Thời điểm bắt đầu mất kết nối, thời hạn resume | Thời điểm session hết hạn và chính sách dọn dẹp |
| Bảo mật | Danh tính client, token được bảo vệ và thông tin kết nối | Ràng buộc token với session/principal, quyền và chính sách xác thực |

Đây là mô hình khái niệm. Chi tiết state thực tế do implementation RSocket quản lý; ứng dụng không nên tự lưu từng frame hay tự tính stream ID để thay thế runtime.

### 5.1. Phía client

Client cần giữ token của phiên đang hoạt động, biết phiên đó còn trong thời hạn resume hay không, và duy trì trạng thái replay do RSocket runtime quản lý. Nếu process client bị tắt hoàn toàn và state trong bộ nhớ mất, chỉ còn token lưu trong file hoặc database thường không đủ để resume: replay buffer, vị trí frame và state stream cũng phải còn tương thích.

Client cũng cần biết cách xử lý các publisher/subscriber đang chạy khi transport mất. Thay vì tạo subscription mới ngay lập tức, runtime có thể giữ stream trong trạng thái chờ resumption. Ứng dụng nên phân biệt trạng thái `temporarily disconnected/resuming` với `session lost` để UI không đăng ký lại cùng stream một cách mù quáng.

### 5.2. Phía server

Server cần tra cứu resume token để tìm session cũ, giữ replay buffer gửi đi, vị trí frame, stream registry và thời hạn session. Khi client resume, server phải nối transport mới vào đúng session cũ, xác nhận vị trí và tiếp tục replay.

Trong hệ thống nhiều instance, việc tra cứu token và state phải nhất quán với nơi kết nối mới được định tuyến. Nếu session nằm trong bộ nhớ của instance A nhưng reconnect đến instance B không thể truy cập state của A, resume có thể thất bại. Sticky routing có thể giúp kết nối mới đến đúng instance trong một số kiến trúc; shared session store hoặc cơ chế replication cần được đánh giá kỹ theo khả năng implementation. Không nên giả định RSocket tự đồng bộ replay buffer giữa các node.

### 5.3. State protocol không thay thế state nghiệp vụ

RSocket runtime giữ trạng thái để tiếp tục trao đổi frame và stream. Nó không tự lưu transaction database, trạng thái đơn hàng, offset của Kafka, tiến độ xử lý batch hoặc side effect bên ngoài.

Nếu server đã ghi database nhưng client chưa nhận được event xác nhận trước khi ngắt kết nối, ứng dụng vẫn cần event ID, sequence nghiệp vụ, idempotency key hoặc API truy vấn trạng thái để đối soát. Resumption phục hồi đường truyền protocol; ứng dụng vẫn chịu trách nhiệm bảo toàn ý nghĩa nghiệp vụ.

## 6. Resume token, replay buffer và resumption window phối hợp ra sao?

Ba yếu tố này phải tồn tại đồng thời:

1. **Token hợp lệ:** xác định đúng phiên cũ ở cả hai phía.
2. **State còn sống:** session và stream registry chưa bị dọn khỏi bộ nhớ hoặc store.
3. **Replay data còn đủ:** các frame mà peer chưa nhận vẫn nằm trong buffer.

Resumption window là khoảng thời gian session được giữ sau khi transport bị mất. Nếu client quay lại sau thời hạn này, server có thể đã dọn session và token không còn dùng được. Dung lượng replay buffer quyết định lượng dữ liệu chưa xác nhận có thể giữ trong khoảng thời gian đó.

Ước lượng dung lượng buffer cần thiết có thể bắt đầu từ:

\[
B \approx R \times T \times S
\]

Trong đó:

- \(B\) là dung lượng byte replay buffer ước lượng cho một hướng.
- \(R\) là tốc độ frame trung bình (frame/giây).
- \(T\) là thời gian có thể không nhận được xác nhận/replay window cần chịu đựng (giây).
- \(S\) là kích thước frame trung bình (byte).

Ví dụ, một phía gửi trung bình 200 frame/giây, frame trung bình 1 KiB và muốn dự phòng khoảng 30 giây dữ liệu chưa được xác nhận. Dung lượng thô ước lượng là:

\[
200 \times 30 \times 1\text{ KiB} = 6.000\text{ KiB} \approx 5,86\text{ MiB}
\]

Đây chỉ là ước lượng ban đầu. Cần tính cả overhead, burst, hai hướng, số session đồng thời và giới hạn thực tế của implementation. Nếu có 1.000 session với mức buffer này, tổng ngân sách bộ nhớ có thể lên đến nhiều GiB. Vì vậy, phải đặt giới hạn theo từng session và toàn server.

## 7. Điều gì xảy ra khi resumption thất bại?

Không phải mọi lỗi kết nối đều có thể resume. Các trường hợp thường gặp:

| Nguyên nhân | Vì sao không thể resume | Cách ứng dụng phục hồi |
|---|---|---|
| Token không tồn tại hoặc sai | Server không tìm được phiên tương ứng | Xác thực lại và tạo phiên mới |
| Session hết thời hạn | State đã được dọn khỏi server/client | Mở session mới, tải snapshot và đăng ký lại |
| Replay buffer overflow | Frame cần replay đã bị loại bỏ hoặc không còn đủ | Khởi tạo lại stream và đối soát dữ liệu |
| Server instance mất state | Reconnect đến node không có session cũ | Định tuyến đúng node nếu còn state, nếu không thì tạo phiên mới |
| Client process restart | State cục bộ của runtime có thể đã mất | Khởi tạo session mới; phục hồi nghiệp vụ từ store riêng |
| Version/transport không tương thích | Hai phía không thể tiếp tục cùng protocol state | Dùng kết nối mới và phiên bản tương thích |
| Peer từ chối resume vì chính sách bảo mật | Token/principal hoặc điều kiện phiên không hợp lệ | Xác thực lại; không retry vô hạn cùng token |

Khi resume thất bại, không nên lặp yêu cầu resume vô hạn. Dùng retry có giới hạn và backoff; sau khi xác định phiên không thể tiếp tục, chuyển sang full reconnect và quy trình đồng bộ nghiệp vụ.

## 8. Cấu hình resumption trong Java và Spring

Trong rsocket-java, resumption được bật ở cấu hình `RSocketConnector`/transport. Cùng với resume, cần cấu hình keepalive, thời hạn giữ session và giới hạn lưu frame theo API của phiên bản thư viện đang sử dụng. Tên và cách nối builder có thể khác giữa các phiên bản rsocket-java, vì vậy cần đối chiếu dependency thực tế trước khi chép cấu hình vào ứng dụng.

Một cấu hình khái niệm cần có các thành phần:

```java
Duration keepAliveInterval = Duration.ofSeconds(20);
Duration keepAliveMaxLifetime = Duration.ofMinutes(2);
Duration resumeWindow = Duration.ofMinutes(3);

// Minh họa các tham số cần cấu hình trong RSocketConnector:
// - enable resume support on both client and server
// - retain session state for resumeWindow
// - configure replay storage/limits for unacknowledged frames
// - configure keepaliveInterval and keepAliveMaxLifetime
// - provide a secure, session-scoped resume token
```

Đoạn trên thể hiện chính sách cấu hình, không phải API builder hoàn chỉnh. Hãy dùng đúng API resumption và replay store của phiên bản rsocket-java trong dự án; không tự tạo một `resumeToken` trong payload nghiệp vụ rồi cho rằng protocol đã bật resumption.

Ví dụ kết nối TCP ở mức transport thông thường:

```java
Mono<RSocket> connection = connector.connect(
    TcpClientTransport.create("rsocket.internal", 7000)
);
```

`connector` trong ví dụ phải được cấu hình resumption trước khi gọi `connect`. Với RSocket over WebSocket, thay transport bằng WebSocket transport tương ứng; các nguyên tắc token, replay buffer và session state vẫn giống nhau. WebSocket reconnect thành công ở tầng transport chưa chứng minh RSocket session đã resume.

### 8.1. Cấu hình phía server

Server phải chấp nhận setup có bật resumption và có khả năng giữ/tra cứu session theo token. Ngoài giới hạn per-session, cần đặt giới hạn tổng số session đang chờ resume để tránh client tạo nhiều phiên rồi bỏ kết nối.

Ở hệ thống nhiều node, cần chọn chiến lược định tuyến và lưu state. Nếu implementation chỉ giữ state trong memory của một instance, hãy bảo đảm reconnect đến đúng instance trong thời hạn session. Nếu cần shared storage, phải xác minh implementation có hỗ trợ loại store đó; không thể chỉ đặt token vào Redis rồi mặc định replay buffer đã được replicate.

### 8.2. Bảo mật token và phiên

Token cần được tạo đủ khó đoán, truyền qua transport bảo mật và ràng buộc với session/principal. Khi client reconnect, server cần xác minh danh tính và quyền theo chính sách hệ thống, tránh để một token bị lộ trở thành cách chiếm phiên. Không ghi token vào access log hoặc metric. Khi session hết hạn hoặc bị thu hồi, xóa token mapping và state tương ứng.

## 9. Resumption và keepalive

Keepalive và resumption phối hợp nhưng có vai trò khác nhau:

- Keepalive giúp phát hiện peer hoặc connection không còn phản hồi ở cấp RSocket.
- Resumption dùng state và replay buffer để tiếp tục phiên trên transport mới sau khi connection cũ bị mất.

Khi resumption được hỗ trợ, thông tin vị trí frame đã nhận có thể được trao đổi cùng các frame keepalive để peer biết phần nào đã được nhận và có thể loại bỏ khỏi replay buffer. Keepalive không tự replay frame; nó hỗ trợ duy trì và theo dõi trạng thái kết nối/tiến độ protocol.

Nếu max lifetime quá ngắn so với jitter mạng, connection có thể bị coi là mất quá sớm. Nếu resume window quá ngắn, client có thể không kịp kết nối lại. Nếu window quá dài, server phải giữ nhiều state và buffer lâu hơn. Hãy chọn các giá trị dựa trên thời gian gián đoạn mạng mà sản phẩm cần chịu đựng, giới hạn bộ nhớ và timeout của proxy/load balancer.

## 10. Resumption không bảo đảm exactly-once nghiệp vụ

Resumption có thể replay frame chưa được peer xác nhận ở tầng protocol, nhưng không nên xem nó là cam kết exactly-once cho side effect nghiệp vụ. Ví dụ, server nhận command, cập nhật database thành công, sau đó kết nối đứt trước khi client nhận event kết quả. Client có thể không biết thao tác đã hoàn tất hay chưa.

Để xử lý an toàn:

1. Gắn `commandId` hoặc idempotency key ổn định vào payload nghiệp vụ.
2. Lưu trạng thái xử lý và kết quả theo ID trong database.
3. Khi reconnect/resume thất bại, client truy vấn trạng thái trước khi gửi lại command.
4. Consumer dùng unique constraint hoặc thao tác idempotent để tránh áp dụng side effect hai lần.
5. Với stream event, dùng sequence number/offset nghiệp vụ để phát hiện khoảng dữ liệu bị thiếu và đồng bộ lại.

Protocol position và stream ID phục vụ việc tiếp tục trao đổi frame. Chúng không thay thế ID của đơn hàng, transaction, sự kiện hoặc command ở tầng domain.

## 11. Quan sát session và kiểm soát tài nguyên

Resumption tăng khả năng chịu gián đoạn nhưng làm tăng trạng thái cần giữ. Nên theo dõi ít nhất:

| Metric | Ý nghĩa |
|---|---|
| `rsocket_resume_attempt_total` | Tổng số lần client thử resume |
| `rsocket_resume_success_total` | Số lần resume thành công |
| `rsocket_resume_rejected_total` | Số lần peer từ chối resume |
| `rsocket_resume_expired_total` | Số session hết resume window |
| `rsocket_resume_buffer_bytes` | Dung lượng replay buffer đang sử dụng |
| `rsocket_resume_buffer_overflow_total` | Số lần buffer vượt giới hạn |
| `rsocket_resumable_sessions` | Số session đang được giữ để có thể resume |
| `rsocket_replay_frames_total` | Số frame được replay |
| `rsocket_resume_duration` | Thời gian từ lúc mất kết nối đến khi resume hoàn tất |

Log có cấu trúc nên có session ID nội bộ đã được làm mờ, transport type, resume outcome, số byte/frame replay và nguyên nhân thất bại. Không log resume token. Tránh dùng token hoặc session ID duy nhất làm label metric vì cardinality cao và có thể lộ thông tin nhạy cảm.

Đặt giới hạn:

- Dung lượng replay buffer tối đa cho một session.
- Tổng dung lượng replay buffer trên server.
- Số session chờ resume.
- Thời gian giữ session sau khi mất transport.
- Kích thước payload/frame tối đa.
- Số lần retry resume và thời gian backoff.

Khi đạt giới hạn, hệ thống phải có hành vi rõ ràng: từ chối session mới, kết thúc session cũ, hoặc buộc client full reconnect. Không để state chờ resume tăng không giới hạn.

## 12. Kiểm thử resumption

Một integration test nên chạy client và server RSocket thật, bật resumption ở cả hai phía và chủ động làm gián đoạn transport. Các kịch bản nên có:

1. **Resume bình thường:** mở stream, trao đổi frame, ngắt transport ngắn rồi kết nối lại trong resume window; xác minh phiên và stream tiếp tục.
2. **Frame chưa được xác nhận:** tạo lưu lượng hai chiều, cắt kết nối khi còn frame trong replay buffer; xác minh frame cần thiết được replay theo thứ tự.
3. **Resume token sai:** gửi token không khớp; xác minh peer từ chối và không gắn nhầm session.
4. **Session hết hạn:** chờ quá resume window rồi thử resume; xác minh fallback sang session mới.
5. **Replay buffer đầy:** tạo lưu lượng lớn hơn capacity trong thời gian mất kết nối; xác minh resume thất bại có kiểm soát.
6. **Server restart:** khởi động lại instance làm mất state trong memory; xác minh hệ thống không giả định token cũ đủ để khôi phục.
7. **Nhiều instance:** reconnect đến node khác; xác minh sticky routing/shared state hoạt động đúng hoặc fallback được xử lý.
8. **Bảo mật:** token không bị log; token bị thu hồi hoặc principal không hợp lệ không thể tiếp tục phiên.
9. **Nghiệp vụ idempotent:** ngắt kết nối quanh thời điểm commit; xác minh command ID giúp tránh side effect lặp.
10. **Giải phóng tài nguyên:** sau khi session hết hạn, replay buffer và stream registry được dọn đúng lúc.

Khi test, ghi nhận sequence/command ID ở tầng nghiệp vụ song song với frame position ở tầng protocol. Điều này giúp phân biệt replay frame thành công với việc nghiệp vụ đã xử lý đúng.

## 13. Quy trình thiết kế resumption

Trước khi bật resumption trong production, hãy trả lời:

1. Mạng có thể gián đoạn tối đa bao lâu mà ứng dụng muốn tiếp tục cùng phiên?
2. Token được tạo, trao đổi, bảo vệ, thu hồi và hết hạn như thế nào?
3. Client và server giữ replay buffer theo byte, theo thời gian và theo session ra sao?
4. Vị trí frame đã gửi/nhận được runtime lưu và cập nhật thế nào?
5. Stream registry và demand được giữ trong thời gian transport mất ra sao?
6. Server có nhiều instance không; reconnect được định tuyến đến nơi giữ session như thế nào?
7. Điều gì xảy ra khi token sai, buffer overflow hoặc session hết hạn?
8. Khi resumption thất bại, client tải snapshot và đăng ký lại stream ra sao?
9. Những command/event nào cần idempotency hoặc sequence number nghiệp vụ?
10. Metric nào cảnh báo buffer tăng, session chờ quá lâu hoặc resume thất bại?

Hãy bắt đầu bằng resume window ngắn, giới hạn buffer nhỏ trong môi trường thử nghiệm, sau đó tăng tải và thời gian gián đoạn có kiểm soát. Đo tỷ lệ resume thành công, lượng dữ liệu replay, bộ nhớ mỗi session và tác động đến latency trước khi chọn cấu hình production.

## 14. Kết luận

RSocket resumption cho phép tiếp tục một phiên cũ trên transport mới nếu cả hai phía còn giữ token, trạng thái protocol, vị trí frame và replay buffer cần thiết. Resume token nhận diện phiên; vị trí frame xác định tiến độ đã nhận; replay buffer giữ các frame chưa được xác nhận; resumption window quy định session còn được giữ trong bao lâu.

Client và server đều cần giữ state tương ứng. Server phải tìm đúng session theo token và có đủ frame để replay; client phải giữ state cục bộ để gửi yêu cầu resume và tiếp tục stream. Nếu một phía mất state, buffer overflow hoặc session hết hạn, cần full reconnect và đồng bộ lại ở tầng ứng dụng. Cuối cùng, resumption phục hồi giao tiếp protocol, còn tính đúng đắn của transaction, idempotency và dữ liệu nghiệp vụ vẫn cần được ứng dụng thiết kế riêng.
