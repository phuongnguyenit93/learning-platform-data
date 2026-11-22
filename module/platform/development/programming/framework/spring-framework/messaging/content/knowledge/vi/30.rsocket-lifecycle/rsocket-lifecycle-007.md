# Lease và phân biệt giới hạn yêu cầu với REQUEST_N

## 1. Vị trí trong vòng đời RSocket

RSocket là giao thức giao tiếp hai chiều. Sau khi kết nối TCP hoặc WebSocket và trao đổi frame `SETUP`, mỗi phía đều có thể đóng vai `Requester` (bên khởi tạo request) hoặc `Responder` (bên xử lý request). Vì vậy, không nên gắn cố định hai vai trò này với client và server.

RSocket có hai cơ chế kiểm soát lưu lượng ở hai cấp độ khác nhau:

- **Lease** kiểm soát việc một phía có được phép mở thêm request mới trên connection hay không.
- **Reactive Streams demand**, được truyền bằng `REQUEST_N`, kiểm soát số payload mà bên nhận sẵn sàng nhận trên một stream cụ thể.

Hai cơ chế có thể hoạt động đồng thời. Lease bảo vệ năng lực tiếp nhận request ở cấp connection; `REQUEST_N` giúp từng stream điều tiết tốc độ truyền dữ liệu theo khả năng tiêu thụ của subscriber.

Luồng khái quát khi bật Lease:

1. Requester gửi `SETUP` với cờ `L` để thông báo rằng nó sẽ tuân thủ Lease từ peer.
2. Sau khi chấp nhận kết nối, Responder gửi một frame `LEASE` cấp số request và thời hạn sử dụng.
3. Requester chỉ mở request mới trong phạm vi số lượng và thời hạn được cấp.
4. Với request dạng stream hoặc channel, demand ban đầu được gửi cùng frame mở stream; khi cần thêm payload, bên nhận gửi `REQUEST_N`.
5. Responder có thể phát Lease tiếp theo để cấp hạn mức mới. Một Lease mới thay thế giá trị Lease trước đó.

Nếu không bật cờ `L`, Requester có thể gửi request mà không cần chờ Lease. Khi đã bật cờ này, Requester phải chờ Lease hợp lệ trước khi gửi request.

## 2. Lease: hạn mức mở request mới theo thời gian

### 2.1. Lease giải quyết vấn đề gì?

Một connection có thể mang nhiều request đồng thời. Nếu Responder đang quá tải, việc chỉ kiểm soát từng stream chưa đủ để hạn chế số request mới được khởi tạo liên tục. Lease cho phép Responder thông báo năng lực tiếp nhận hiện tại để Requester điều chỉnh việc gửi request.

Một frame `LEASE` chứa hai giá trị chính:

| Trường | Ý nghĩa |
|---|---|
| `Time-To-Live (TTL)` | Thời gian Lease còn hiệu lực, tính bằng mili giây từ lúc Requester nhận frame |
| `Number of Requests` | Số request mới tối đa Requester được phép gửi theo Lease đó |

Frame `LEASE` thuộc cấp connection và dùng Stream ID bằng `0`. Nó có thể được gửi từ Responder ở một trong hai phía của connection để giới hạn request do phía còn lại khởi tạo.

### 2.2. Lease đếm những gì?

Mỗi lần Requester mở một request interaction mới sẽ tiêu thụ một đơn vị trong hạn mức Lease. Các loại request được tính gồm:

- `REQUEST_RESPONSE`
- `REQUEST_STREAM`
- `REQUEST_CHANNEL`
- `REQUEST_FNF` (Fire-and-Forget)

Ví dụ, Lease cấp `10` request trong `2 giây`. Trong thời hạn đó, Requester có thể mở tối đa 10 request mới thuộc các loại trên. Một `REQUEST_STREAM` vẫn chỉ tiêu thụ một đơn vị khi được khởi tạo, dù stream sau đó phát ra nhiều payload.

Khi hết số request được cấp hoặc TTL hết hạn, Requester không được mở thêm request theo Lease cũ. Khi nhận Lease mới, hạn mức và thời hạn của Lease trước được thay thế; không cộng dồn hai hạn mức. Nếu Responder nhận một request mà nó không thể chấp nhận do giới hạn Lease, giao thức quy định phản hồi bằng `ERROR[REJECTED]`.

### 2.3. Lease không phải giới hạn số message của stream

Lease điều tiết việc bắt đầu request. Khi một `REQUEST_STREAM` đã được chấp nhận, việc stream tiếp tục phát bao nhiêu payload được điều khiển bằng demand của stream đó.

Vì vậy, khi Lease hết hạn:

- Requester không thể mở request mới cho đến khi có Lease hợp lệ tiếp theo.
- Các stream đã được mở không tự động bị hủy chỉ vì Lease hết hạn.
- Payload của các stream đang chạy vẫn phải tuân thủ `REQUEST_N` và vòng đời stream.

Lease cũng không đồng nghĩa với giới hạn số request đang chạy đồng thời. Nó giới hạn số request được khởi tạo trong một khoảng thời gian. Nếu cần giới hạn concurrency, hàng đợi hoặc tải xử lý thực tế, ứng dụng vẫn cần chính sách phù hợp ở tầng xử lý.

## 3. REQUEST_N: demand cho payload trên từng stream

### 3.1. REQUEST_N là gì?

`REQUEST_N` là tín hiệu flow control của Reactive Streams trong RSocket. Nó cho biết bên nhận muốn nhận thêm bao nhiêu payload từ bên gửi trên một stream cụ thể.

Với `REQUEST_STREAM` và `REQUEST_CHANNEL`, frame mở stream mang theo demand ban đầu. Sau đó, khi cần thêm dữ liệu, bên nhận gửi frame `REQUEST_N` với số lượng bổ sung.

Ví dụ:

1. Requester mở stream bằng `REQUEST_STREAM` và demand ban đầu là `3`.
2. Responder gửi tối đa 3 frame `PAYLOAD` trên stream đó.
3. Khi Requester muốn nhận thêm, nó gửi `REQUEST_N(N=2)` trên cùng Stream ID.
4. Responder được phép gửi thêm tối đa 2 payload theo demand vừa nhận.

`REQUEST_N` gắn với Stream ID của stream đang hoạt động, khác với `LEASE` dùng Stream ID `0` ở cấp connection.

### 3.2. Quan hệ với Reactive Streams

Trong Reactive Streams, subscriber gọi `Subscription.request(n)` để báo số phần tử mà nó có khả năng tiếp nhận. RSocket truyền tín hiệu demand này qua mạng để Responder điều tiết việc phát payload.

Với Spring Framework, ứng dụng thường làm việc qua `Mono` và `Flux`. Khi dùng `RSocketRequester` để nhận kết quả dạng `Flux`, nhu cầu của subscriber được Reactor và RSocket Java chuyển thành cơ chế flow control của giao thức. Thông thường ứng dụng không cần tự tạo frame `REQUEST_N`.

Cơ chế này giúp producer không phải phát dữ liệu nhanh hơn khả năng tiêu thụ của subscriber. Nó cũng giảm lượng dữ liệu phải giữ trong buffer và giúp các stream độc lập chia sẻ connection hiệu quả hơn.

`REQUEST_N` không có TTL. Demand tồn tại trên stream cho đến khi được tiêu thụ hoặc stream kết thúc; khi cần thêm payload, bên nhận gửi thêm demand.

### 3.3. REQUEST_N trong Request-Channel

`REQUEST_CHANNEL` hỗ trợ dữ liệu theo cả hai chiều. Demand luôn thuộc về phía nhận payload: mỗi phía cần cấp demand cho dữ liệu mà mình nhận từ phía kia. Khi đọc frame log của Channel, hãy xem Stream ID và chiều truyền để xác định `REQUEST_N` đang cấp quyền gửi payload theo hướng nào.

`REQUEST_RESPONSE` chỉ có một response nên không cần chuỗi demand `REQUEST_N` như stream. `REQUEST_FNF` không có response stream.

## 4. So sánh Lease và REQUEST_N

| Tiêu chí | Lease | REQUEST_N |
|---|---|---|
| Phạm vi | Toàn connection, theo hướng Responder cấp quyền cho Requester | Một stream cụ thể |
| Kiểm soát | Số request mới được mở | Số payload được phép gửi tiếp |
| Đơn vị đếm | Request interaction | Payload/message |
| Thông tin chính | TTL và Number of Requests | N |
| Frame | `LEASE` | `REQUEST_N` |
| Stream ID | `0` | Stream ID đang hoạt động |
| Thời gian | Có TTL; hết hạn thì không còn hạn mức | Không có TTL riêng |
| Áp dụng | Request-Response, Request-Stream, Channel, Fire-and-Forget | Luồng payload của Request-Stream và Channel |
| Mục tiêu | Admission control, điều tiết request mới và bảo vệ năng lực xử lý | Back pressure, điều tiết tốc độ dữ liệu theo consumer |

Có thể ghi nhớ bằng hai câu:

- **Lease hỏi: “Tôi còn được mở bao nhiêu request mới trong thời hạn này?”**
- **REQUEST_N hỏi: “Trên stream này, tôi được gửi thêm bao nhiêu payload?”**

Không được dùng số trong Lease thay cho demand của stream, hoặc dùng `REQUEST_N` như một quota request cho toàn connection.

## 5. Ví dụ kết hợp hai cơ chế

Giả sử Responder gửi Lease với TTL 2 giây và Number of Requests bằng 10.

Trong thời hạn đó, Requester mở một `REQUEST_STREAM`. Request này tiêu thụ một đơn vị Lease. Khi mở stream, Requester cấp demand ban đầu là 3:

~~~text
Requester -> Responder: SETUP (L = 1)
Responder -> Requester: LEASE (TTL = 2000 ms, Requests = 10)

Requester -> Responder: REQUEST_STREAM (Stream ID = 1, initial REQUEST_N = 3)
Responder -> Requester: PAYLOAD (Stream ID = 1)
Responder -> Requester: PAYLOAD (Stream ID = 1)
Responder -> Requester: PAYLOAD (Stream ID = 1)

Requester -> Responder: REQUEST_N (Stream ID = 1, N = 2)
Responder -> Requester: PAYLOAD (Stream ID = 1)
Responder -> Requester: PAYLOAD (Stream ID = 1)
~~~

Sau chuỗi này:

- Hạn mức Lease còn 9 request mới, nếu vẫn nằm trong TTL và chưa có Lease mới thay thế.
- Stream ID 1 đã nhận 5 payload theo hai lần cấp demand.
- Hai payload bổ sung không tiêu thụ thêm hai đơn vị Lease.
- Requester có thể gửi thêm `REQUEST_N` trên Stream ID 1 để nhận thêm payload.
- Requester có thể mở request mới nếu Lease vẫn còn hiệu lực và còn hạn mức.

Ví dụ này cho thấy Lease và `REQUEST_N` hoạt động độc lập: một cơ chế quản lý số lần bắt đầu request, cơ chế còn lại quản lý dữ liệu được truyền trong từng stream.

## 6. Cấu hình trong Spring Framework và RSocket Java

### 6.1. Bật Lease cho RSocketRequester

Spring cung cấp `RSocketRequester` để tạo request theo kiểu fluent API. Builder cho phép cấu hình `io.rsocket.core.RSocketConnector` thông qua `rsocketConnector`:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector ->
        connector.lease(spec -> spec.maxPendingRequests(128)))
    .tcp("localhost", 7000);
~~~

Lệnh `lease` bật hỗ trợ Lease trên connector để Requester tuân thủ hạn mức mà peer cấp. Peer vẫn phải phát Lease hợp lệ; bật ở phía Requester không tự tạo hạn mức từ phía Responder.

`maxPendingRequests(128)` là giới hạn số request đang chờ trong hàng đợi cục bộ khi chưa có Lease. Đây không phải Number of Requests trong frame `LEASE`, cũng không phải số payload mà stream được nhận.

### 6.2. Phát Lease ở phía Responder

Với RSocket Java, server có thể cấu hình nguồn phát Lease bằng `RSocketServer.lease`. Đây là mảnh cấu hình server; `RSocketController` là lớp `@Controller` của ứng dụng, chứa các method `@MessageMapping`. Ví dụ cấp 10 request với TTL 2 giây và phát một Lease mới mỗi giây:

~~~java
import java.time.Duration;

import io.rsocket.SocketAcceptor;
import io.rsocket.core.RSocketServer;
import io.rsocket.lease.Lease;
import io.rsocket.transport.netty.server.TcpServerTransport;
import org.springframework.messaging.rsocket.RSocketMessageHandler;
import org.springframework.messaging.rsocket.RSocketStrategies;
import reactor.core.publisher.Flux;

// RSocketController là @Controller có các method @MessageMapping.
RSocketStrategies strategies = RSocketStrategies.builder().build();
SocketAcceptor acceptor = RSocketMessageHandler.responder(
    strategies, new RSocketController());

RSocketServer.create(acceptor)
    .lease(spec -> spec.sender(() ->
        Flux.interval(Duration.ZERO, Duration.ofSeconds(1))
            .map(tick -> Lease.create(Duration.ofSeconds(2), 10))))
    .bind(TcpServerTransport.create("localhost", 7000))
    .block();
~~~

Đây là ví dụ về chính sách cấp Lease cố định để minh họa API. Trong hệ thống thật, nguồn phát Lease nên dựa trên năng lực hiện tại như số request đang chờ, tải CPU, giới hạn worker hoặc trạng thái dịch vụ. Không nên sao chép hạn mức cố định vào production nếu chưa đánh giá tải.

Nếu ứng dụng cần cho cả hai phía chủ động mở request, mỗi hướng phải được cấu hình đúng vai trò: Requester bật việc tuân thủ Lease trong `SETUP`, còn Responder ở phía đối diện cung cấp nguồn phát Lease. Cấu hình Lease cho một hướng không có nghĩa là hướng ngược lại đã có chính sách cấp hạn mức.

### 6.3. REQUEST_N qua Flux

Khi nhận stream qua Spring, dùng `retrieveFlux` để nhận `Flux`:

~~~java
Flux<Event> events = requester
    .route("events")
    .data(command)
    .retrieveFlux(Event.class);
~~~

Demand của subscriber đối với `events` được truyền qua Reactor và RSocket Java. Nếu subscriber yêu cầu thêm dữ liệu theo từng đợt, RSocket gửi tín hiệu demand tương ứng cho stream. Các toán tử back pressure của Reactor có thể giúp điều tiết cách ứng dụng tiêu thụ dữ liệu; chúng không thay thế chính sách Lease ở cấp connection.

## 7. Lỗi hiểu nhầm thường gặp

1. **Coi Lease là số message tối đa của một stream.** Lease chỉ đếm request interaction mới; payload của stream được kiểm soát bằng demand.
2. **Coi REQUEST_N là hạn mức request toàn connection.** REQUEST_N thuộc một Stream ID, không cấp quyền mở request mới.
3. **Cho rằng một request stream tiêu thụ Lease cho từng payload.** Một request stream tiêu thụ một đơn vị khi khởi tạo; các payload tiếp theo tuân theo REQUEST_N.
4. **Nhầm maxPendingRequests với Number of Requests.** maxPendingRequests giới hạn hàng đợi request cục bộ đang chờ Lease; Number of Requests là quota do peer cấp trong frame LEASE.
5. **Bật Lease ở requester nhưng không phát Lease ở responder.** Khi requester đã yêu cầu tuân thủ Lease, nó phải chờ hạn mức hợp lệ trước khi gửi request.
6. **Cho rằng Lease hết hạn sẽ hủy các stream đang chạy.** Hết hạn ngăn request mới theo Lease cũ; vòng đời của stream đang chạy vẫn được điều khiển bằng flow control và các tín hiệu kết thúc stream.
7. **Cho rằng Lease là cơ chế xác thực hoặc rate limit đầy đủ.** Lease là cơ chế admission control ở tầng giao thức. Ứng dụng vẫn cần xác thực, phân quyền, giới hạn theo người dùng và xử lý quá tải phù hợp.

## 8. Cách kiểm tra khi debug

Khi phân tích frame log, hãy kiểm tra theo thứ tự:

- Trong `SETUP`, requester có bật cờ `L` hay không.
- Responder có phát `LEASE` hay không; kiểm tra TTL và Number of Requests.
- Request mới có được mở khi Lease còn hiệu lực và còn quota hay không.
- Với `REQUEST_STREAM` hoặc `REQUEST_CHANNEL`, kiểm tra demand ban đầu.
- Với frame `REQUEST_N`, kiểm tra Stream ID, chiều truyền và số payload được cấp thêm.
- Nếu gặp `ERROR[REJECTED]`, kiểm tra việc request vượt hạn mức Lease hoặc Lease đã hết hạn.

Có thể bật log frame của RSocket Java ở mức DEBUG cho logger `io.rsocket.FrameLogger` khi cần quan sát giao thức trên dây.

## 9. Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): mô hình request, back pressure, `RSocketRequester` và cấu hình connector.
- [RSocket Protocol — Lease Semantics](https://github.com/rsocket/rsocket/blob/master/Protocol.md#lease-semantics): quy tắc TTL, số request, cờ Lease trong SETUP và hành vi khi vượt hạn mức.
- [RSocket Protocol — Flow Control](https://github.com/rsocket/rsocket/blob/master/Protocol.md#flow-control): Reactive Streams semantics và `REQUEST_N`.
- [RSocket Java — RSocketServer API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html): cấu hình nguồn phát Lease ở phía server.
- [RSocket Java — RSocketConnector API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html): bật Lease ở phía connector.
- [RSocket Java — LeaseSpec API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/LeaseSpec.html): cấu hình hàng đợi request đang chờ Lease và LeaseSender.
