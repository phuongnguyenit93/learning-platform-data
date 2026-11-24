# Vị trí frame, bộ đệm lưu lại và cơ chế tiếp tục phiên

RSocket có thể duy trì một phiên giao tiếp khi kết nối TCP hoặc WebSocket bị gián đoạn tạm thời. Cơ chế **connection resumption** cho phép hai peer thiết lập lại transport rồi tiếp tục trao đổi các frame còn thiếu của phiên cũ. Để làm được điều đó, mỗi phía cần theo dõi vị trí dữ liệu đã gửi/đã nhận, giữ lại các frame chưa được peer xác nhận trong **replay buffer**, và nhận diện phiên bằng một **resume token**.

Resumption giúp phục hồi các tương tác RSocket đang hoạt động mà không phải tạo lại toàn bộ session ở tầng ứng dụng. Đây là khả năng tùy chọn của giao thức; nó chỉ thành công khi hai peer còn giữ trạng thái phiên, token hợp lệ và replay buffer vẫn chứa đủ dữ liệu cần gửi lại.

## 1. Vì sao cần vị trí frame?

Một kết nối RSocket có thể mang nhiều stream đồng thời. Frame của các stream được ghép xen kẽ trên cùng transport. Khi kết nối bị đứt, một phía có thể đã nhận một số frame trong khi phía còn lại chưa biết chính xác frame cuối cùng đã đến nơi.

RSocket dùng **position** để xác định tiến độ của luồng byte trên kết nối. Position là offset tích lũy tính theo byte của dữ liệu frame được truyền, không phải số thứ tự request và cũng không phải stream ID.

| Khái niệm | Ý nghĩa | Phạm vi |
|---|---|---|
| Stream ID | Xác định một tương tác request-response, request-stream, channel hoặc fire-and-forget. | Một stream trên kết nối |
| Frame position | Cho biết vị trí byte đã gửi/đã nhận trong luồng frame của một hướng truyền. | Toàn bộ luồng dữ liệu của một hướng trên kết nối |
| Resume token | Nhận diện phiên có thể tiếp tục sau khi transport cũ bị mất. | Phiên RSocket |

Ví dụ, trên cùng một kết nối có thể lần lượt xuất hiện frame của stream `1`, `3`, rồi lại stream `1`. Position vẫn tăng theo tổng byte của tất cả frame đã truyền, không bắt đầu lại khi đổi stream:

```text
Luồng byte Client -> Server

position 0       120              260              410
       |----------|----------------|----------------|
       | frame    | frame          | frame          |
       | stream=1 | stream=3       | stream=1       |
       |----------|----------------|----------------|
```

Position giúp peer xác định phần dữ liệu nào đã được nhận và phần nào cần phát lại. Stream ID vẫn được dùng để định tuyến frame đến đúng tương tác sau khi khôi phục.

## 2. Position được theo dõi độc lập theo từng hướng

Hai chiều truyền dữ liệu có hai tiến độ riêng. Client theo dõi số byte đã gửi cho server và số byte đã nhận từ server; server cũng theo dõi tương ứng cho chiều ngược lại.

```text
Client                                      Server
  |                                           |
  |---- frame bytes, client position ------->|
  |                                           |
  |<--- frame bytes, server position --------|
  |                                           |
```

Một position là điểm cuối của phần dữ liệu liên tục trong luồng frame, được tính theo byte. Khi phân tích log, không được cộng position của hai hướng với nhau. Ví dụ, client đã nhận 8.000 byte từ server không có nghĩa server đã nhận 8.000 byte từ client.

Position cũng không phải một bộ đếm frame đơn giản. Hai frame có kích thước khác nhau làm position tăng những lượng khác nhau. Khi cần replay, peer phải dùng đúng ranh giới frame và offset đã ghi nhận trong phiên; không thể lấy một stream ID hoặc số lượng frame để thay thế position.

## 3. KEEPALIVE xác nhận tiến độ nhận

Frame `KEEPALIVE` vừa giúp phát hiện kết nối không còn hoạt động, vừa có thể mang **last received position** để thông báo cho peer biết dữ liệu đã nhận đến đâu. Thông tin này đóng vai trò acknowledgement cho replay buffer.

Khi nhận được xác nhận rằng peer đã nhận dữ liệu đến một position, bên gửi có thể giải phóng những frame cũ hơn hoặc bằng vị trí đã được xác nhận khỏi replay buffer. Các frame mới hơn vẫn cần được giữ lại cho đến khi có xác nhận tiếp theo.

```text
Client                                      Server
  |                                           |
  |---- PAYLOAD frames, positions 100-500 --->|
  |                                           |
  |<--- KEEPALIVE, last received = 500 -------|
  |                                           |
  | giải phóng các frame đã được xác nhận     |
  | khỏi replay buffer chiều Client -> Server|
```

Việc xác nhận position là theo hướng dữ liệu đã được nhận. `KEEPALIVE` có thể yêu cầu peer phản hồi bằng cờ respond; keepalive và acknowledgement không làm thay đổi stream ID của các tương tác nghiệp vụ.

Nếu một peer không nhận được keepalive trong thời gian cấu hình, nó có thể xem kết nối đã mất và bắt đầu quy trình reconnect/resume. Thời gian keepalive cần được chọn phù hợp với độ trễ mạng và chính sách phát hiện lỗi; quá ngắn có thể tạo reconnect giả khi mạng chỉ chậm tạm thời.

## 4. Replay buffer lưu những gì?

Mỗi peer cần giữ lại các frame đã gửi nhưng chưa được xác nhận là peer đã nhận. Những frame này được lưu trong **replay buffer** cùng position của chúng để có thể phát lại theo đúng thứ tự sau khi kết nối được khôi phục.

Replay buffer thường cần lưu:

- Byte/frame đã serialize để gửi ra transport.
- Position bắt đầu/kết thúc của phần dữ liệu tương ứng.
- Thứ tự gửi để có thể replay chính xác.
- Thông tin cần thiết để biết phần nào đã được peer xác nhận và có thể loại bỏ.

Ví dụ:

```text
Replay buffer phía Client (gửi sang Server)

+-------------------+-------------------+-------------------+
| Frame A           | Frame B           | Frame C           |
| position 100-220  | position 220-360  | position 360-500  |
+-------------------+-------------------+-------------------+
       đã ACK             đã ACK          chưa ACK
       có thể bỏ          có thể bỏ       phải giữ lại
```

Khi peer xác nhận đã nhận đến position `360`, client có thể bỏ Frame A và B. Frame C vẫn nằm trong buffer cho đến khi được xác nhận hoặc phiên hết thời gian lưu giữ.

Replay buffer có giới hạn dung lượng và thời gian giữ. Nó không phải kho lưu trữ vô hạn. Nếu ứng dụng phát dữ liệu nhanh hơn tốc độ peer xác nhận trong thời gian dài, buffer có thể đầy. Khi không còn đủ frame để phát lại từ position mà peer yêu cầu, phiên không thể resume an toàn và phải bị từ chối.

## 5. Resume token nhận diện phiên

Khi muốn hỗ trợ resumption, bên khởi tạo kết nối đưa một **resume token** vào frame `SETUP`. Token là dữ liệu opaque đối với ứng dụng; peer dùng nó để tìm phiên đã lưu và các trạng thái cần thiết như replay buffer, position, stream đang hoạt động.

Token không phải mật khẩu người dùng, stream ID hoặc mã request nghiệp vụ. Nó là định danh phiên có thể tiếp tục. Vì ai có token hợp lệ có thể yêu cầu tiếp tục phiên tương ứng, ứng dụng nên xem token như một capability nhạy cảm:

- Dùng token đủ khó đoán nếu ứng dụng tự tạo token.
- Không ghi token đầy đủ vào log, trace hoặc metric.
- Bảo vệ kết nối bằng TLS khi truyền qua mạng không tin cậy.
- Giới hạn thời gian lưu session và xóa trạng thái khi hết hạn.
- Không tái sử dụng token cho một phiên mới không liên quan.

Peer nhận token trong `SETUP` phải có khả năng gắn token với đúng trạng thái phiên. Nếu server lưu session trong bộ nhớ của một node, reconnect vào node khác có thể không tìm thấy token. Khi triển khai nhiều node, cần sticky routing hoặc một cơ chế lưu/chia sẻ trạng thái resume phù hợp.

## 6. Trình tự RESUME và RESUME_OK

Khi transport cũ bị mất nhưng phiên vẫn còn hiệu lực, một peer mở transport mới và gửi frame `RESUME`. Frame này mang resume token cùng position cuối cùng mà peer đó đã nhận từ phía bên kia.

Peer còn giữ session tra cứu token, kiểm tra khả năng replay và phản hồi `RESUME_OK` kèm position cuối cùng mà nó đã nhận từ phía khởi tạo resume. Sau khi handshake thành công, hai phía phát lại những frame còn thiếu dựa trên position đã trao đổi.

```text
Client                                      Server
  |                                           |
  |       transport cũ bị gián đoạn           |
  X                                           X
  |                                           |
  |========= thiết lập transport mới =========|
  |                                           |
  | RESUME (streamId=0, token=T,               |
  |        lastReceivedServerPosition=500) --->|
  |                                           | kiểm tra token,
  |                                           | session và buffer
  |<--- RESUME_OK (streamId=0,                 |
  |        lastReceivedClientPosition=900) ---|
  |                                           |
  | replay frame phía Client sau position 900 |
  |------------------------------------------>|
  |                                           |
  |<---------- replay frame phía Server ------|
  |                                           |
  |========== tiếp tục frame mới ==============|
```

Trong ví dụ:

1. Client thông báo đã nhận dữ liệu từ server đến position `500`.
2. Server thông báo đã nhận dữ liệu từ client đến position `900`.
3. Client replay những frame phía client đã gửi nhưng server chưa xác nhận nhận đến.
4. Server replay những frame phía server đã gửi nhưng client chưa xác nhận nhận đến.
5. Khi phần replay hoàn tất, hai bên tiếp tục truyền frame mới trên transport vừa khôi phục.

`RESUME` và `RESUME_OK` là frame cấp kết nối, dùng `streamId = 0`. Chúng không mở stream nghiệp vụ mới. Các stream ID cũ và trạng thái tương tác được khôi phục cùng phiên.

## 7. Điều gì được khôi phục sau khi resume?

Khi resumption thành công, RSocket tiếp tục phiên đã tồn tại. Điều này có nghĩa các stream đang hoạt động, vị trí truyền, frame còn chờ xác nhận và các thông tin điều khiển liên quan được duy trì theo trạng thái phiên.

Ví dụ, một request-stream đang phát dữ liệu có thể tiếp tục sau reconnect:

```text
Trước khi mất kết nối:
Client -> Server  REQUEST_STREAM (streamId=1)
Server -> Client  PAYLOAD (streamId=1, position=100)
Server -> Client  PAYLOAD (streamId=1, position=200)

Transport bị ngắt.

Sau khi resume:
Client <-> Server  RESUME / RESUME_OK
Server -> Client  replay PAYLOAD còn thiếu của streamId=1
Server -> Client  PAYLOAD mới của streamId=1
```

Ứng dụng không cần gửi lại `REQUEST_STREAM` chỉ để khôi phục cùng tương tác nếu phiên đã resume thành công. Việc phát lại frame là trách nhiệm của giao thức/runtime. Nếu resumption thất bại và ứng dụng phải tạo kết nối/phiên mới, lúc đó request nghiệp vụ có thể cần được gửi lại theo chính sách riêng.

## 8. Vị trí frame và stream ID giải quyết hai bài toán khác nhau

Hai khái niệm này thường bị nhầm khi đọc log:

| Câu hỏi | Dùng thông tin nào? |
|---|---|
| Frame thuộc request hoặc stream nào? | Stream ID |
| Peer đã nhận dữ liệu đến đâu trong hướng truyền này? | Position |
| Phiên cũ có thể tiếp tục trên transport mới không? | Resume token và trạng thái session |
| Frame nào cần phát lại? | Position kết hợp replay buffer |

Một frame `PAYLOAD` của stream `1` có thể nằm ở position `12.000`, trong khi frame kế tiếp của stream `3` nằm ở position `12.500`. Khi reconnect, peer dùng position để tìm byte/frame cần replay; sau khi nhận lại, runtime vẫn dùng stream ID để đưa payload đến đúng subscriber.

## 9. Khi nào resumption bị từ chối?

Resumption không được đảm bảo trong mọi trường hợp. Peer có thể từ chối resume nếu:

- Resume token không hợp lệ hoặc không tìm thấy session tương ứng.
- Session đã hết thời gian lưu giữ hoặc đã bị đóng.
- Replay buffer đã bị xóa, tràn hoặc không còn chứa frame cần thiết từ position được yêu cầu.
- Position được gửi không phù hợp với trạng thái phiên mà peer đang lưu.
- Peer không bật hỗ trợ resumption hoặc cấu hình giao thức không tương thích.
- Reconnect đi đến node không có trạng thái phiên và không thể truy xuất trạng thái từ node trước.

Trong các trường hợp này, peer có thể trả frame `ERROR` với mã `REJECTED_RESUME` hoặc một lỗi kết nối phù hợp. Client phải coi phiên cũ không thể tiếp tục, giải phóng tài nguyên liên quan và quyết định có tạo phiên mới hay không.

Không nên tự động coi lỗi resume là lý do để replay mọi request nghiệp vụ. Với request có side effect, hãy dùng idempotency key hoặc cơ chế đối soát để tránh thực hiện lặp khi ứng dụng chuyển sang phiên mới.

## 10. Giới hạn dung lượng và thời gian của replay buffer

Replay buffer cần được thiết kế theo thông lượng và thời gian gián đoạn mà hệ thống muốn chịu được. Một ước lượng ban đầu cho dung lượng có thể dựa trên:

\[
\text{buffer bytes} \approx \text{outbound bytes/second} \times \text{resume window seconds}
\]

Ví dụ, nếu một kết nối phát trung bình `200 KB/s` và muốn giữ đủ dữ liệu cho khoảng gián đoạn `30 s`, buffer lý thuyết cần khoảng `6 MB` cho chiều đó, chưa tính overhead, biến động burst và các giới hạn nội bộ của implementation.

| Tham số | Tác động khi đặt quá thấp | Tác động khi đặt quá cao |
|---|---|---|
| Replay buffer capacity | Dễ hết chỗ trước khi peer xác nhận; resume thất bại. | Tốn bộ nhớ, đặc biệt khi có nhiều session đồng thời. |
| Session retention duration | Phiên bị xóa trước khi client kịp reconnect. | Giữ state và buffer lâu, tiêu tốn tài nguyên. |
| Keepalive interval | Phát hiện lỗi chậm nếu quá dài; overhead tăng nếu quá ngắn. | Có thể phát hiện kết nối hỏng muộn hơn. |
| Reconnect retry window | Bỏ cuộc trước khi mạng hồi phục. | Giữ tài nguyên và request chờ quá lâu. |

Buffer nên có giới hạn theo byte và theo thời gian nếu implementation hỗ trợ. Cần theo dõi số byte đang giữ, số frame chờ xác nhận, tuổi frame cũ nhất, số lần resume thành công/thất bại và số session bị loại bỏ do quá hạn.

## 11. Cấu hình resumption trong RSocket Java

RSocket Java cung cấp API cấu hình resume cho connector và server. Resumption phải được bật ở các peer liên quan; chỉ cấu hình retry kết nối TCP không đủ để khôi phục session RSocket.

Ví dụ cấu hình khái niệm cho client:

```java
RSocketConnector connector = RSocketConnector.create()
    .resume()
    .resumeSessionDuration(Duration.ofMinutes(2))
    .retry(Retry.backoff(10, Duration.ofMillis(500)));

Mono<RSocket> connection = connector.connect(transport);
```

Phía server cũng cần bật resumption và giữ session đủ lâu:

```java
RSocketServer server = RSocketServer.create(socketAcceptor)
    .resume()
    .resumeSessionDuration(Duration.ofMinutes(2));

Mono<CloseableChannel> bound = server.bind(transport);
```

Đây là mẫu cấu hình theo API của các bản RSocket Java 1.1.x; tên phương thức và cách cung cấp replay store có thể thay đổi theo phiên bản. Hãy kiểm tra Javadoc đúng dependency đang dùng, đặc biệt các tùy chọn resume duration, retry và frame store. Trong production, cần xem xét giới hạn buffer, nơi lưu session và chính sách khi resume không thành công.

## 12. Resumption không đồng nghĩa exactly-once ở tầng nghiệp vụ

Resumption phát lại các frame chưa được xác nhận trong cùng một phiên và giúp runtime khôi phục thứ tự truyền. Nó không thay thế cơ chế idempotency cho nghiệp vụ khi ứng dụng phải tạo phiên mới.

Ví dụ, client gửi request tạo đơn hàng rồi mất kết nối trước khi nhận response:

- Nếu phiên cũ resume thành công, các frame còn thiếu được replay theo position; tương tác đang chạy có thể tiếp tục.
- Nếu phiên cũ không thể resume, client có thể không biết server đã xử lý request trước khi mất kết nối hay chưa.
- Nếu client tạo phiên mới và gửi lại request, server có thể tạo đơn hàng lần thứ hai nếu nghiệp vụ không có idempotency.

Với thao tác ghi dữ liệu, thanh toán hoặc tạo tài nguyên, nên gắn một idempotency key duy nhất với yêu cầu nghiệp vụ. Server lưu kết quả theo key để request gửi lại có thể trả cùng kết quả thay vì thực hiện side effect lần nữa.

## 13. Kiểm thử resumption

Một kiểm thử resumption nên tạo kết nối thật giữa requester và responder, mở ít nhất một stream, tạo frame hai chiều rồi chủ động làm gián đoạn transport.

Các kịch bản quan trọng:

1. **Resume thành công:** ngắt transport tạm thời, reconnect với token cũ, xác minh `RESUME`/`RESUME_OK` và stream tiếp tục.
2. **Replay frame chưa ACK:** tạo dữ liệu đang chờ xác nhận, ngắt kết nối và xác minh các frame còn thiếu được phát lại đúng thứ tự.
3. **Không replay dữ liệu đã ACK:** xác minh peer không nhận lại các frame trước position đã xác nhận.
4. **Token không hợp lệ:** gửi token không tồn tại và xác minh resume bị từ chối.
5. **Session hết hạn:** chờ quá retention duration rồi reconnect; xác minh không khôi phục nhầm phiên cũ.
6. **Replay buffer không đủ:** tạo lưu lượng vượt capacity trước khi resume; xác minh phiên bị từ chối thay vì tiếp tục với dữ liệu thiếu.
7. **Nhiều stream:** chạy đồng thời request-response, request-stream hoặc channel; xác minh position toàn kết nối không làm lẫn stream ID.
8. **Reconnect sang node khác:** kiểm tra sticky routing hoặc cơ chế chia sẻ session state trong môi trường nhiều node.
9. **Fallback sang session mới:** xác minh ứng dụng áp dụng idempotency hoặc chính sách retry an toàn khi resume thất bại.

Khi đo kiểm, ghi lại position theo từng hướng, số byte trong replay buffer, số frame được replay, thời gian reconnect, kết quả resume và nguyên nhân từ chối. Không ghi resume token hoặc payload nhạy cảm vào log.

## 14. Cách chẩn đoán khi resume thất bại

Khi client reconnect nhưng session không tiếp tục, kiểm tra theo trình tự:

1. Xác định kết nối cũ có bật resumption từ lúc `SETUP` hay không; không thể bật resume hồi tố sau khi phiên đã được tạo.
2. Kiểm tra token gửi trong `RESUME` có khớp session đang lưu ở peer không.
3. Kiểm tra thời gian từ lúc mất kết nối có vượt `resumeSessionDuration` hoặc retention policy không.
4. So sánh position cuối đã nhận với phạm vi position còn nằm trong replay buffer của peer.
5. Kiểm tra buffer capacity, frame bị loại bỏ, session bị eviction và log `REJECTED_RESUME`.
6. Nếu chạy nhiều node, xác minh reconnect có đến node sở hữu session hoặc node có thể truy xuất session đó.
7. Nếu resume bị từ chối, xác định request nghiệp vụ nào cần được khởi tạo lại và áp dụng idempotency cho thao tác có side effect.

Ví dụ log rút gọn:

```text
connection lost: session=opaque-token
reconnect attempt: transport=tcp
RESUME sent: lastReceivedServerPosition=12000
RESUME rejected: code=REJECTED_RESUME
reason: requested position is older than retained replay buffer
application action: create new session after reconciliation
```

Position yêu cầu nằm ngoài phạm vi dữ liệu còn giữ nên peer không thể replay đầy đủ. Cách xử lý an toàn là tạo phiên mới sau khi ứng dụng xác định trạng thái nghiệp vụ; không giả vờ rằng stream cũ đã được khôi phục.

## Kết luận

Connection resumption dùng position để xác định tiến độ byte theo từng hướng, replay buffer để giữ frame chưa được peer xác nhận và resume token để tìm lại phiên cũ. Khi reconnect, `RESUME` và `RESUME_OK` trao đổi vị trí nhận cuối cùng; hai phía phát lại frame còn thiếu rồi tiếp tục các stream đang chạy. Resumption chỉ thành công khi session và buffer còn đủ trạng thái. Vì vậy, cần giới hạn dung lượng/thời gian lưu, theo dõi position và keepalive acknowledgement, bảo vệ token, và thiết kế idempotency cho nghiệp vụ khi phải chuyển sang một phiên mới.
