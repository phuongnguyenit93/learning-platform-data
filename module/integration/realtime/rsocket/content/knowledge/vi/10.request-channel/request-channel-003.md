# Trình tự REQUEST_CHANNEL và các PAYLOAD tiếp theo

RSocket hỗ trợ Request-Channel cho những phiên giao tiếp mà hai bên đều cần gửi nhiều thông điệp trong cùng một tương tác. Ví dụ, một giao diện cộng tác gửi thao tác chỉnh sửa liên tục lên server trong khi server đồng thời đẩy trạng thái mới về client. Để hiểu mô hình này, cần theo dõi cách stream được mở bằng `REQUEST_CHANNEL`, cách các `PAYLOAD` tiếp theo đi theo hai hướng và cách hai bên điều tiết lượng dữ liệu bằng demand.

Trong module `INTEGRATION_REALTIME_RSOCKET`, Request-Channel là mô hình phù hợp cho giao tiếp realtime hai chiều qua TCP hoặc WebSocket. Nó kết hợp một luồng dữ liệu từ requester tới responder với một luồng dữ liệu ngược lại, nhưng cả hai hướng vẫn thuộc cùng một stream RSocket.

## 1. REQUEST_CHANNEL mở một stream hai chiều

Requester bắt đầu tương tác bằng frame `REQUEST_CHANNEL` (Frame Type `0x07`). Frame này mang:

- Stream ID mới để định danh tương tác.
- Giá trị **Initial Request N**: số payload ban đầu mà requester muốn nhận từ responder.
- Payload mở đầu của requester, có thể gồm metadata và data.

Initial Request N là demand theo chiều responder gửi dữ liệu về requester. Giá trị này phải lớn hơn `0`. Nó không phải số lượng payload mà requester được phép gửi lên server.

Payload nằm trong `REQUEST_CHANNEL` chính là thông điệp đầu tiên của requester. Sau khi mở stream, requester có thể gửi thêm các frame `PAYLOAD` theo chiều client → server; responder cũng có thể gửi các frame `PAYLOAD` theo chiều server → client. Các frame của hai hướng có thể xen kẽ nhau.

```text
Requester (Client)                         Responder (Server)
       |                                           |
       |-- REQUEST_CHANNEL                         |
       |   initialRequestN=8, payload=C1 ---------->|
       |                                           |
       |<---------------- PAYLOAD (S1) ------------|
       |                                           |
       |-- PAYLOAD (C2) -------------------------->|
       |<---------------- PAYLOAD (S2) ------------|
       |                                           |
       |<---------------- REQUEST_N (4) ------------|
       |                                           |
       |-- PAYLOAD (C3) -------------------------->|
       |-- PAYLOAD (C4) -------------------------->|
       |                                           |
       |-- PAYLOAD (C5, COMPLETE) ---------------->|
       |                                           |
       |<---------------- PAYLOAD (S3) ------------|
       |<---------------- PAYLOAD (S4, COMPLETE) --|
       |                                           |
```

Sơ đồ minh họa hai luồng payload cùng tồn tại. Client bắt đầu bằng C1 và yêu cầu tối đa 8 payload từ server. Server gửi thêm `REQUEST_N(4)` để yêu cầu client cung cấp thêm tối đa bốn payload. Cuối cùng, mỗi phía có thể hoàn tất luồng gửi của chính mình; việc một phía hoàn tất không tự động đóng luồng gửi còn lại.

## 2. Trình tự các frame trong một Request-Channel

### 2.1. Bước 1 — requester mở channel

Requester cấp một Stream ID mới và gửi `REQUEST_CHANNEL`. Frame chứa payload mở đầu cùng Initial Request N để cho responder biết requester đang sẵn sàng nhận bao nhiêu payload.

Ví dụ về nội dung logic:

```text
REQUEST_CHANNEL
  Stream ID       = 5
  Initial Request N = 8
  Metadata        = route: "session.interact"
  Data            = ClientCommand(type="JOIN", sessionId="room-42")
```

Metadata định tuyến giúp Spring tìm đúng handler. Data mang nội dung ứng dụng. Initial Request N điều khiển lượng dữ liệu server có thể gửi ban đầu về client.

### 2.2. Bước 2 — hai bên trao đổi PAYLOAD

Sau khi stream được mở, mỗi bên có thể gửi `PAYLOAD` (Frame Type `0x0A`) theo hướng dữ liệu của mình. Mỗi PAYLOAD mang một thông điệp ứng dụng, có thể có metadata, data hoặc cả hai.

Ví dụ, client gửi thao tác kéo thả hoặc vị trí con trỏ; server gửi trạng thái phiên, kết quả xử lý hoặc thông tin đồng bộ. Hai luồng không cần gửi số lượng payload bằng nhau và không cần luân phiên nghiêm ngặt.

Một PAYLOAD có thể mang cờ `N` (Next) để biểu thị frame này mang một payload mới, cờ `C` (Complete) để báo bên gửi đã hoàn tất luồng payload của mình, và cờ `M` nếu có metadata. Frame cuối có thể vừa mang payload vừa đánh dấu hoàn tất. Khi payload được phân mảnh, cờ `F` (Follows) được dùng theo quy tắc fragmentation của giao thức. Cờ `C` thường quan trọng trong Request-Channel vì nó cho phép một phía đóng hướng gửi của mình mà không kết thúc hướng ngược lại.

### 2.3. Bước 3 — hai bên điều tiết demand bằng REQUEST_N

Trong channel, mỗi hướng có demand riêng:

- Client gửi `REQUEST_N(n)` để yêu cầu server gửi thêm tối đa `n` payload về client.
- Server gửi `REQUEST_N(n)` để yêu cầu client gửi thêm tối đa `n` payload lên server.

`REQUEST_N` có Frame Type `0x08`, mang số lượng payload bổ sung được yêu cầu. Giá trị `n` phải lớn hơn `0`. Demand là số payload mà bên gửi có thể tiếp nhận, không phải số byte và cũng không phải cam kết rằng bên kia sẽ có đúng số payload đó.

Ví dụ: client mở channel với Initial Request N bằng 8. Sau khi nhận đủ tám payload server gửi, client cần gửi `REQUEST_N(8)` để yêu cầu thêm. Độc lập với việc đó, nếu server muốn nhận thêm lệnh từ client, server gửi `REQUEST_N(20)`. Hai giá trị demand không phụ thuộc nhau.

### 2.4. Bước 4 — một phía hoàn tất hoặc requester hủy stream

Khi một phía không còn dữ liệu cần gửi, phía đó có thể gửi `PAYLOAD` với cờ `C` (Complete). Đây là thao tác **half-close**: đóng hướng gửi của phía đó. Hướng còn lại vẫn có thể tiếp tục phát payload cho tới khi nó cũng hoàn tất hoặc toàn bộ tương tác bị hủy/kết thúc.

Requester có thể gửi frame `CANCEL` (Frame Type `0x09`) để hủy toàn bộ tương tác đang mở, ví dụ người dùng rời khỏi phòng cộng tác. Khi nhận CANCEL, responder nên dừng công việc gắn với stream và giải phóng tài nguyên liên quan. Hủy subscription ở client trong API reactive thường là cách để yêu cầu hủy tương tác; hành vi cụ thể phụ thuộc implementation.

Lỗi stream được truyền bằng `ERROR` (Frame Type `0x0B`). Lỗi kết thúc tương tác; ứng dụng cần quyết định hiển thị lỗi, thử lại hoặc thiết lập một channel mới. Không nên coi half-close của một hướng là lỗi hay là kết thúc toàn bộ channel.

## 3. Hai hướng dữ liệu có demand độc lập

Điểm quan trọng nhất của Request-Channel là không có một bộ đếm demand chung cho cả hai hướng. Mỗi receiver điều khiển lượng payload mà mình sẵn sàng nhận từ peer.

| Frame | Bên gửi | Ý nghĩa |
|---|---|---|
| `REQUEST_CHANNEL(initial N, payload)` | Requester | Mở stream, gửi payload đầu tiên và công bố demand ban đầu cho dữ liệu responder gửi về. |
| `PAYLOAD` | Cả hai bên | Gửi thêm một payload trên stream đã mở. |
| `REQUEST_N(n)` | Cả hai bên | Yêu cầu peer gửi thêm tối đa `n` payload về phía mình. |
| `PAYLOAD` với `C=1` | Cả hai bên | Hoàn tất hướng gửi của bên phát frame. |
| `CANCEL` | Requester | Hủy toàn bộ stream channel. |
| `ERROR` | Bên phát hiện lỗi | Kết thúc stream bằng lỗi. |

Ví dụ, trong một ứng dụng điều khiển thiết bị, client có thể gửi các lệnh di chuyển trong khi server phát trạng thái vị trí. Nếu client xử lý trạng thái chậm, client giảm hoặc tạm dừng demand cho hướng server → client. Nếu server xử lý lệnh chậm, server giảm demand cho hướng client → server. Việc điều tiết một hướng không nhất thiết phải dừng hướng kia.

## 4. Backpressure và cách xử lý publisher

RSocket sử dụng Reactive Streams để truyền demand qua `REQUEST_N`. Một publisher chỉ nên phát số phần tử mà subscriber đã yêu cầu. Điều này giúp kiểm soát luồng dữ liệu trong từng hướng của channel.

Trong Java, các toán tử Reactor ảnh hưởng đến cách ứng dụng xử lý payload:

- `concatMap` xử lý tuần tự và giữ thứ tự kết quả theo thứ tự đầu vào.
- `flatMap` cho phép nhiều tác vụ chạy đồng thời; kết quả có thể đến không theo thứ tự đầu vào.
- `onBackpressureBuffer` có thể lưu phần tử chờ xử lý, nhưng cần giới hạn dung lượng và định nghĩa hành vi khi đầy.
- `limitRate` có thể điều chỉnh cách upstream được yêu cầu phần tử; nó không thay thế việc thiết kế demand và giới hạn bộ đệm ở toàn bộ pipeline.

Không nên dùng hàng đợi vô hạn để che giấu việc consumer không theo kịp producer. Với dữ liệu realtime, hãy xác định rõ có thể bỏ sự kiện cũ, gộp cập nhật, giảm tần suất hay phải lưu bền vững.

## 5. Ví dụ Request-Channel bằng Spring Boot

### 5.1. Client gửi luồng lệnh và nhận luồng cập nhật

Client tạo một `Flux<ClientCommand>` chứa các lệnh phát sinh trong phiên. `data(commands)` đưa publisher vào request; `retrieveFlux(ServerUpdate.class)` nhận các cập nhật từ server:

```java
public record ClientCommand(
    String sessionId,
    String type,
    long sequence
) {}

public record ServerUpdate(
    String sessionId,
    String state,
    long version
) {}

Flux<ClientCommand> commands = commandSource.commands();

Flux<ServerUpdate> updates = requester
    .route("session.interact")
    .data(commands, ClientCommand.class)
    .retrieveFlux(ServerUpdate.class);
```

Vì client truyền một publisher có nhiều phần tử và đồng thời nhận một Flux kết quả, tương tác được ánh xạ thành Request-Channel. Client nên giữ subscription và hủy nó khi phiên kết thúc hoặc người dùng rời màn hình.

### 5.2. Server nhận luồng lệnh và trả luồng cập nhật

Handler phía server có thể nhận `Flux<ClientCommand>` và trả về `Flux<ServerUpdate>`:

```java
@MessageMapping("session.interact")
public Flux<ServerUpdate> interact(Flux<ClientCommand> commands) {
    return commands.concatMap(command ->
        sessionService.apply(command)
            .map(state -> new ServerUpdate(
                command.sessionId(),
                state.name(),
                state.version()
            ))
    );
}
```

Ví dụ này phát một cập nhật cho mỗi lệnh và xử lý lệnh tuần tự để giữ thứ tự. Một channel thực tế có thể phát thêm sự kiện độc lập từ server, chẳng hạn thành viên khác vừa tham gia hoặc trạng thái phòng thay đổi. Khi cần kết hợp nhiều nguồn, có thể dùng `merge` hoặc `mergeWith`, nhưng phải xác định rõ thứ tự, khả năng trùng lặp và cách hủy các nguồn khi channel kết thúc.

### 5.3. Kết thúc phiên

Khi client không còn lệnh để gửi, publisher đầu vào hoàn tất. Framework truyền trạng thái hoàn tất tương ứng để server biết requester đã half-close hướng gửi. Server vẫn có thể gửi những cập nhật cuối cùng rồi hoàn tất publisher đầu ra. Nếu người dùng rời phiên đột ngột, client hủy subscription để yêu cầu hủy channel.

Không nên gọi `.subscribe()` rời rạc cho từng lệnh trong service. Hãy giữ publisher trong chuỗi reactive của phiên để cancellation, demand và lỗi được truyền xuyên suốt.

## 6. Khi nào nên dùng Request-Channel?

Request-Channel phù hợp khi hai bên cần trao đổi nhiều payload trong cùng một phiên và thời điểm phát dữ liệu ở hai phía có thể xen kẽ:

- Phiên cộng tác: client gửi thao tác chỉnh sửa, server gửi thay đổi từ thành viên khác.
- Điều khiển thiết bị: client gửi lệnh liên tục, server phát trạng thái cảm biến và kết quả thực thi.
- Trò chơi realtime: client gửi input, server phát trạng thái thế giới.
- Phiên tương tác trực tiếp: client gửi câu trả lời hoặc thao tác, server gửi tiến độ và thông tin mới.

| Nhu cầu | Mô hình phù hợp hơn | Vì sao |
|---|---|---|
| Gửi một lệnh và nhận một kết quả | Request-Response | Không cần giữ hai luồng mở. |
| Gửi một sự kiện không cần phản hồi | Fire-and-Forget | Không cần luồng dữ liệu ngược lại. |
| Gửi một yêu cầu đăng ký, sau đó chỉ nhận cập nhật | Request-Stream | Chỉ cần luồng responder → requester. |
| Gửi liên tục và nhận liên tục trong cùng phiên | Request-Channel | Hai hướng đều có nhiều payload. |

## 7. Lỗi và các tình huống cần xử lý

Khi thiết kế channel, cần xác định trước hành vi cho các trường hợp:

- **Client gửi nhanh hơn server xử lý:** server giảm demand bằng REQUEST_N; client cần tuân thủ demand và giới hạn buffer.
- **Server gửi nhanh hơn client xử lý:** client giảm demand đối với hướng server → client và có thể gộp hoặc bỏ các cập nhật cũ nếu nghiệp vụ cho phép.
- **Một hướng hoàn tất trước:** hướng còn lại tiếp tục cho đến khi tự hoàn tất, bị hủy hoặc gặp lỗi.
- **Client hủy channel:** dừng publisher phía client và giải phóng công việc liên quan ở server.
- **Mất kết nối:** channel có thể bị lỗi hoặc được khôi phục nếu Resume đã được cấu hình và điều kiện phục hồi đáp ứng; không mặc định rằng reconnect sẽ tự tiếp tục mọi publisher.
- **Thông điệp gửi lại:** dùng sequence number hoặc event ID và xử lý idempotent nếu việc áp dụng một lệnh nhiều lần gây sai trạng thái.

Request-Channel không tự bảo đảm exactly-once. Nếu stream bị ngắt sau khi server đã xử lý một lệnh nhưng trước khi client nhận cập nhật, client có thể không biết lệnh đã được áp dụng hay chưa. Với thao tác thay đổi trạng thái, cần mã định danh lệnh, sequence number hoặc API truy vấn trạng thái để phục hồi an toàn.

## 8. Kiểm thử trình tự channel

Các ca kiểm thử nên xác nhận cả thứ tự frame lẫn hành vi reactive:

1. Client mở `REQUEST_CHANNEL` với payload đầu tiên và Initial Request N hợp lệ.
2. Server nhận payload mở đầu đúng route và phát các PAYLOAD về client.
3. Client gửi PAYLOAD tiếp theo; server chỉ phát thêm dữ liệu đầu vào theo demand đã cấp.
4. Client và server gửi `REQUEST_N` độc lập; xác nhận mỗi hướng chỉ phát trong giới hạn demand.
5. Client gửi PAYLOAD có `C=1`; xác nhận server không chờ thêm payload từ client nhưng vẫn có thể gửi phản hồi.
6. Server gửi PAYLOAD có `C=1`; xác nhận client nhận hoàn tất hướng server → client.
7. Client hủy subscription; xác nhận CANCEL được xử lý và tài nguyên server được giải phóng.
8. Một phía phát sinh lỗi; xác nhận stream kết thúc với lỗi và publisher liên quan được hủy.
9. Producer nhanh hơn consumer; xác nhận không có buffer vô hạn và chính sách backpressure hoạt động.
10. Mất kết nối giữa phiên; xác nhận hành vi reconnect/Resume và tính idempotent của lệnh.

Nên kiểm thử tích hợp trên TCP và WebSocket nếu ứng dụng hỗ trợ cả hai. Ngoài việc kiểm tra kết quả cuối, hãy ghi nhận số payload theo từng hướng, demand đã cấp, số lần cancellation, độ sâu buffer và thời gian xử lý để phát hiện tắc nghẽn.

## 9. Kết luận

`REQUEST_CHANNEL` mở một stream hai chiều bằng payload đầu tiên và Initial Request N. Sau đó, hai bên gửi các `PAYLOAD` tiếp theo theo hai hướng; `REQUEST_N` điều khiển demand độc lập cho từng hướng. `PAYLOAD` với cờ `C` half-close hướng gửi của bên phát, còn `CANCEL` từ requester hủy toàn bộ tương tác. Hiểu rõ trình tự này giúp thiết kế phiên realtime có backpressure, vòng đời và phục hồi kết nối phù hợp.
