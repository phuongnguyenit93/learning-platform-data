# Mất kết nối định kỳ do keepalive, proxy hoặc thời gian chờ nhàn rỗi

Một ứng dụng RSocket có thể hoạt động bình thường khi vừa kết nối, nhưng sau một khoảng không truyền dữ liệu lại bị đóng kết nối. Hiện tượng này thường xuất hiện theo chu kỳ khá ổn định: kết nối mất sau 60 giây, 5 phút hoặc 1 giờ; gửi request liên tục thì không gặp lỗi, nhưng để connection idle thì bị ngắt. Client sau đó reconnect và mọi thứ lại hoạt động cho đến lần idle tiếp theo.

Nguyên nhân thường nằm ở một trong các lớp sau: RSocket `KEEPALIVE`, TCP keepalive, WebSocket ping/pong, proxy/load balancer, NAT/firewall hoặc timeout của chính ứng dụng. Những cơ chế này kiểm tra các loại trạng thái khác nhau và có thể có giá trị timeout độc lập. Chỉ tăng timeout ở một lớp không bảo đảm connection được giữ sống xuyên suốt đường truyền.

## 1. Nhận diện đúng triệu chứng

Trước khi thay đổi cấu hình, hãy xác định mẫu lỗi:

| Triệu chứng | Hướng điều tra ban đầu |
|---|---|
| Mất sau khoảng thời gian idle gần như cố định | Proxy/LB/NAT idle timeout hoặc RSocket keepalive lifetime. |
| Request đang chạy liên tục vẫn bị đóng | Network reset, server restart, overload, timeout request hoặc lỗi transport. |
| Chỉ WebSocket bị lỗi, TCP trực tiếp ổn định | WebSocket proxy, HTTP Upgrade, ping/pong hoặc L7 idle timeout. |
| Chỉ một số mạng/VPN gặp lỗi | Firewall, NAT, VPN gateway hoặc policy mạng trung gian. |
| Chỉ browser tab nền hoặc mobile gặp lỗi | Timer throttling, page suspension hoặc browser lifecycle. |
| Reconnect về node khác thì resume thất bại | Session/resumption state gắn với node cũ hoặc routing affinity. |
| Cả client và server log timeout gần cùng thời điểm | Kiểm tra keepalive interval/lifetime và event-loop stall. |

Một dấu hiệu rất hữu ích là so sánh connection idle với connection có traffic. Nếu stream đang truyền dữ liệu đều không bị ngắt nhưng connection không có payload lại bị đóng sau một khoảng cố định, hãy kiểm tra các timeout nhàn rỗi trước khi thay đổi business timeout.

## 2. Có nhiều loại keepalive và timeout khác nhau

Không nên dùng chung từ “heartbeat” cho mọi cơ chế. Mỗi lớp có mục tiêu và phạm vi riêng:

| Cơ chế | Lớp | Mục tiêu |
|---|---|---|
| RSocket `KEEPALIVE` | RSocket protocol | Kiểm tra peer/session RSocket còn hoạt động; có thể mang position phục vụ resumption. |
| WebSocket Ping/Pong | WebSocket | Kiểm tra transport WebSocket giữa hai endpoint. |
| TCP keepalive | TCP/OS | Phát hiện peer TCP không còn phản hồi sau thời gian idle dài. |
| Proxy/LB idle timeout | Hạ tầng trung gian | Đóng connection/tunnel không có traffic trong thời hạn cấu hình. |
| NAT/firewall state timeout | Mạng | Xóa mapping hoặc state của flow khi không thấy traffic đủ lâu. |
| Application heartbeat | Tầng nghiệp vụ | Xác minh service hoặc luồng nghiệp vụ còn đáp ứng. |
| Request timeout | Tầng request | Giới hạn thời gian chờ kết quả của một request cụ thể. |

Ví dụ một kết nối RSocket qua WebSocket có thể đi qua:

```text
RSocket client
    |
    | RSocket KEEPALIVE frame
    v
WebSocket transport
    |
    | TLS / TCP
    v
Ingress / reverse proxy / load balancer
    |
    | NAT / firewall / VPN
    v
RSocket server
```

RSocket `KEEPALIVE` có thể giữ hoạt động tunnel nếu các frame được truyền qua WebSocket và proxy coi chúng là traffic. TCP keepalive có thể phát hiện peer TCP không phản hồi nhưng thường không thay thế được RSocket protocol keepalive. Một proxy vẫn có thể đóng tunnel nếu idle timeout ngắn hơn khoảng traffic thực tế mà proxy quan sát được.

## 3. RSocket KEEPALIVE hoạt động như thế nào?

RSocket protocol định nghĩa frame `KEEPALIVE` để peer kiểm tra trạng thái của session. Frame được gửi trên cùng transport connection và có thể mang thông tin vị trí đã nhận trong session resumption.

Các điểm cần nhớ:

- `KEEPALIVE` là frame ở tầng RSocket, không phải TCP keepalive hay WebSocket control Ping.
- Frame có cờ `RESPOND`; khi cờ này được đặt, peer nhận cần gửi một frame `KEEPALIVE` phản hồi với cờ yêu cầu phản hồi được bỏ.
- Khi resumption được sử dụng, frame có thể mang vị trí frame đã nhận để hỗ trợ theo dõi/replay.
- Runtime dùng khoảng thời gian keepalive và giới hạn lifetime để phát hiện peer im lặng quá lâu.
- Cấu hình được thương lượng/trao đổi trong quá trình RSocket SETUP theo giao thức và implementation.

Minh họa:

```text
Requester                                      Responder
    |                                               |
    |---------- KEEPALIVE (RESPOND) --------------->|
    |                                               |
    |<--------- KEEPALIVE (response) ---------------|
    |                                               |
    |---------- KEEPALIVE ------------------------->|
    |                                               |
    |       không có response nếu không được yêu cầu|
```

Không phải mỗi frame keepalive đều nhất thiết yêu cầu một frame phản hồi. Việc gửi định kỳ và yêu cầu response phụ thuộc runtime/flags. Khi chẩn đoán, cần kiểm tra frame thực tế hoặc log của implementation thay vì giả định cứ có traffic keepalive là luôn có cặp request-response.

### Keepalive interval và max lifetime

Hai giá trị quan trọng:

- **Keepalive interval:** khoảng thời gian runtime chờ trước khi gửi keepalive tiếp theo.
- **Keepalive max lifetime:** khoảng thời gian tối đa peer có thể không được quan sát là còn sống trước khi session bị coi là mất.

Ví dụ minh họa:

```text
Keepalive interval = 20 giây
Max lifetime       = 90 giây

0s       20s       40s       60s       80s       90s
|---------|---------|---------|---------|---------|
SETUP   KA #1     KA #2     KA #3     KA #4    lifetime
```

Đây chỉ là timeline khái niệm. Runtime còn chịu ảnh hưởng của scheduler, network delay và việc có yêu cầu phản hồi hay không. `maxLifetime` cần đủ lớn để chịu được jitter và một số lần keepalive bị trễ, nhưng cũng phải đủ ngắn để phát hiện connection chết trong thời gian sản phẩm chấp nhận.

## 4. Phân biệt TCP keepalive với RSocket KEEPALIVE

TCP keepalive là tính năng của socket/OS. Khi bật, hệ điều hành có thể gửi probe trên TCP connection để phát hiện peer không phản hồi. Nó không biết RSocket stream nào đang hoạt động, không xác nhận handler nghiệp vụ và không thay thế timeout ở tầng ứng dụng.

RSocket `KEEPALIVE` chạy ở tầng protocol. Nó kiểm tra peer RSocket và có thể tham gia semantics của resumption. Nó được gửi như dữ liệu của transport, do RSocket runtime quản lý.

| Tiêu chí | TCP keepalive | RSocket KEEPALIVE |
|---|---|---|
| Được quản lý bởi | Hệ điều hành/socket | RSocket runtime |
| Vị trí | TCP | Payload/frame của transport ở tầng RSocket |
| Kiểm tra | Peer TCP có phản hồi probe không | Peer RSocket/session có phản hồi theo protocol không |
| Nhận biết stream nghiệp vụ | Không | Không kiểm tra logic handler; chỉ ở tầng session/protocol |
| Thời gian mặc định | Phụ thuộc OS và socket options, có thể khá dài | Do RSocket setup/runtime cấu hình |
| Có thay thế nhau không? | Không | Không |

TCP keepalive có thể được bật nhưng probe đầu tiên xảy ra sau một thời gian dài hơn idle timeout của load balancer. Khi đó proxy đã đóng flow trước khi TCP keepalive kịp phát hiện. Nếu cần giữ flow sống, hãy dùng cơ chế traffic phù hợp với timeout của đường truyền và xác minh nó thực sự đi qua proxy.

## 5. WebSocket Ping/Pong khác RSocket KEEPALIVE

WebSocket định nghĩa control frame Ping và Pong. Một endpoint có thể gửi Ping và peer phải phản hồi Pong theo WebSocket protocol. Các frame này thuộc transport WebSocket, không phải RSocket payload frame.

RSocket chạy bên trong WebSocket thường gửi `KEEPALIVE` dưới dạng dữ liệu của RSocket transport. Browser WebSocket API không cung cấp API JavaScript phổ thông để ứng dụng tự gửi control Ping; browser/runtime có thể quản lý ping/pong nội bộ ở tầng WebSocket tùy implementation.

Do đó:

- WebSocket Ping/Pong kiểm tra peer ở tầng WebSocket.
- RSocket KEEPALIVE kiểm tra session ở tầng RSocket.
- Một proxy có thể xử lý hoặc tạo WebSocket Ping/Pong độc lập với RSocket runtime.
- Ứng dụng JavaScript không nên giả định có thể gọi `socket.ping()` trên WebSocket browser API.

Nếu dùng WebSocket qua reverse proxy, hãy xác minh proxy hỗ trợ HTTP Upgrade, giữ tunnel lâu dài và không áp idle timeout ngắn hơn khoảng traffic. Cần kiểm tra cả timeout đọc từ upstream và timeout ghi về upstream vì một số proxy cấu hình hai hướng riêng.

## 6. Proxy và load balancer idle timeout

Proxy/LB thường có giới hạn thời gian connection không có dữ liệu. Với HTTP request ngắn, timeout này ít lộ rõ; với WebSocket hoặc RSocket connection dài hạn, nó trở thành yếu tố quan trọng.

Các tên cấu hình có thể gặp:

- `idle timeout` hoặc `connection idle timeout`.
- `backend timeout`, `upstream timeout` hoặc `read timeout`.
- `stream idle timeout`.
- `WebSocket idle timeout`.
- `client timeout` và `server timeout`.
- `maximum connection duration` hoặc connection lifetime.

Tên gọi và semantics khác nhau theo nhà cung cấp. Có proxy tính khoảng im lặng kể từ byte cuối cùng theo một hướng; có hệ thống reset idle timer khi có traffic ở bất kỳ hướng nào; một số giới hạn riêng thời gian đọc upstream, thời gian ghi downstream hoặc tuổi thọ connection tối đa.

Đừng chỉ tìm một trường có chữ “timeout” rồi tăng giá trị. Hãy xác định:

1. Timeout bắt đầu tính từ lúc nào: accept, handshake hoàn tất hay byte cuối cùng?
2. Traffic theo hướng client-to-server có reset timer không?
3. Traffic server-to-client có reset timer không?
4. WebSocket control frames có được tính là activity không?
5. RSocket binary `KEEPALIVE` có được proxy coi là data activity không?
6. Có giới hạn tuổi thọ tuyệt đối dù vẫn có traffic không?
7. Timeout được áp dụng ở listener, frontend, backend pool hay từng route?

## 7. NAT, firewall và VPN cũng có thể xóa flow

Ngay cả khi client và server đều giữ socket mở, thiết bị mạng trung gian có thể xóa state của một flow sau thời gian idle. Khi client gửi dữ liệu tiếp theo, NAT mapping cũ không còn hoặc firewall từ chối flow, dẫn đến reset, timeout hoặc packet bị drop.

Các tình huống phổ biến:

- Client ở mạng di động chuyển cell hoặc đổi địa chỉ IP.
- Wi-Fi router xóa NAT mapping sau một khoảng idle.
- VPN gateway áp idle timeout riêng.
- Firewall state table đầy hoặc policy đóng flow lâu không hoạt động.
- Corporate proxy chỉ cho phép WebSocket theo policy cụ thể.
- TLS inspection thiết lập giới hạn riêng cho tunnel.

TCP keepalive hoặc RSocket keepalive có thể giúp duy trì state nếu probe/frame được gửi đủ thường xuyên và được phép đi qua. Tuy nhiên, một số mạng chặn hoặc xử lý khác các gói keepalive; phải kiểm tra trên đường truyền thật.

## 8. Căn chỉnh các giá trị timeout

Giả sử đường truyền có proxy idle timeout ngắn nhất là 60 giây. Nếu RSocket keepalive interval là 90 giây, proxy có thể đóng tunnel trước khi keepalive tiếp theo được gửi.

Một nguyên tắc thiết kế thường dùng:

```text
keepAliveInterval + worstCaseScheduling/networkDelay
    < shortestIdleTimeoutOnPath
```

Giữ một khoảng đệm đáng kể, không đặt interval sát đúng timeout. Ví dụ nếu timeout nhàn rỗi ngắn nhất đã xác minh là 60 giây, có thể bắt đầu thử interval 15–20 giây, sau đó đo CPU, traffic và hành vi trên thiết bị thực tế. Đây là ví dụ tuning, không phải giá trị mặc định phù hợp cho mọi hệ thống.

Đồng thời:

- `maxLifetime` phải lớn hơn interval đủ để chịu được một số lần trễ hoặc mất keepalive.
- `maxLifetime` phải phù hợp với thời gian ứng dụng chấp nhận phát hiện peer chết.
- Request timeout cần độc lập với session keepalive lifetime.
- Proxy maximum connection duration có thể đóng connection dù keepalive vẫn đều; phải có reconnect/resume strategy.
- Browser tab nền có thể bị throttle/suspend, vì vậy interval quá ngắn cũng không bảo đảm timer luôn chạy đúng lịch.

Một bảng cấu hình minh họa:

| Thành phần | Giá trị minh họa | Quan hệ cần kiểm tra |
|---|---:|---|
| Proxy idle timeout | 60 giây | Timeout nhàn rỗi ngắn nhất trên đường truyền. |
| RSocket keepalive interval | 20 giây | Nhỏ hơn proxy timeout với khoảng đệm. |
| RSocket max lifetime | 90 giây | Lớn hơn interval và chịu được jitter. |
| TCP keepalive initial delay | Theo OS/socket config | Không để probe đầu tiên đến sau proxy idle timeout nếu muốn dùng nó để giữ flow. |
| Request timeout | 3 giây | Chỉ áp dụng cho một request, không phải connection lifetime. |

Không sao chép nguyên bảng này vào production. Hãy lấy timeout thực từ nhà cung cấp LB, gateway, NAT/firewall và runtime đang triển khai.

## 9. Cấu hình keepalive trong RSocket Java

Với RSocket Java, client connector cho phép cấu hình keepalive interval và max lifetime. Tên API có thể khác theo phiên bản thư viện, nên kiểm tra Javadoc/dependency đang dùng.

```java
Duration keepAliveInterval = Duration.ofSeconds(20);
Duration keepAliveMaxLifetime = Duration.ofSeconds(90);

RSocketConnector connector = RSocketConnector.create()
    .keepAlive(keepAliveInterval, keepAliveMaxLifetime);
```

Khi kết nối qua TCP, connector có thể được dùng cùng transport TCP:

```java
Mono<RSocket> connection = connector.connect(
    TcpClientTransport.create("rsocket.internal", 7000));
```

Phía server cũng cần cấu hình keepalive phù hợp với client và deployment:

```java
RSocketServer server = RSocketServer.create(acceptor)
    .keepAlive(keepAliveInterval, keepAliveMaxLifetime);
```

Đây là ví dụ API ở tầng RSocket Java; phần bind transport và cấu hình Spring Boot tùy ứng dụng. Nếu dùng Spring Boot starter, hãy xác minh cách phiên bản đang dùng expose cấu hình server/client trước khi thêm property tùy ý. Không giả định một property YAML không có trong phiên bản hiện tại sẽ được runtime áp dụng.

### Chọn giá trị ban đầu

1. Lấy idle timeout ngắn nhất đã biết trên toàn tuyến.
2. Đặt keepalive interval nhỏ hơn timeout đó với khoảng đệm.
3. Đặt max lifetime đủ lớn để chịu jitter và scheduling delay nhưng vẫn đáp ứng yêu cầu phát hiện lỗi.
4. Kiểm tra tải tăng thêm do frame định kỳ khi có nhiều connection.
5. Kiểm tra hành vi khi event loop bị block hoặc browser tab bị suspend.
6. Đo reconnect rate và false timeout trước/sau thay đổi.

## 10. Cấu hình reverse proxy cho WebSocket

Ví dụ Nginx minh họa các thành phần thường cần có cho WebSocket tunnel:

```nginx
location /rsocket {
    proxy_pass http://rsocket_backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}
```

`proxy_read_timeout` và `proxy_send_timeout` có semantics riêng về thời gian giữa các thao tác đọc/ghi; chúng không nhất thiết là một maximum connection lifetime tổng quát. Cấu hình chính xác còn phụ thuộc phiên bản Nginx, upstream, ingress controller và các LB đứng trước/sau nó.

Nếu có nhiều tầng proxy, tăng timeout ở Nginx không giúp ích khi cloud load balancer phía trước vẫn đóng tunnel sau 60 giây. Hãy lập sơ đồ toàn bộ tuyến và kiểm tra timeout ở từng hop.

## 11. Vì sao mất kết nối theo chu kỳ?

Một số mẫu thời gian giúp khoanh vùng:

| Thời điểm mất | Giả thuyết cần kiểm tra |
|---|---|
| Gần đúng 30/60 giây | Idle timeout ngắn ở proxy, gateway hoặc NAT. |
| Gần 5 phút | Default idle timeout của một LB/firewall hoặc policy VPN. |
| Gần đúng `maxLifetime` của RSocket | Peer không nhận được keepalive theo ngưỡng session. |
| Đúng một maximum connection age dù vẫn có traffic | Connection lifetime/rotation policy của LB. |
| Chỉ sau deploy/scale event | Drain, pod termination, backend health hoặc session affinity. |
| Thời gian không cố định, tăng khi server bận | Event-loop starvation, GC pause, CPU saturation hoặc network congestion. |

Các mốc trên chỉ là dấu hiệu để điều tra, không phải fingerprint chắc chắn của một nhà cung cấp. Nhiều hệ thống có thể cấu hình cùng một khoảng timeout.

## 12. Half-open connection và peer im lặng

Half-open connection là trường hợp một phía nghĩ socket vẫn mở nhưng phía kia hoặc đường truyền đã mất. Ví dụ laptop chuyển Wi-Fi, router bị reset hoặc server process bị kill mà FIN/RST không tới client.

Khi đó:

- `isConnected()` hoặc trạng thái object local có thể vẫn báo kết nối.
- Không có exception ngay khi không gửi dữ liệu.
- Request tiếp theo có thể treo đến TCP retransmission timeout hoặc application timeout.
- Keepalive có thể phát hiện peer không phản hồi sau lifetime.
- Proxy/NAT có thể đã xóa state dù hai process chưa biết.

Không dùng một boolean local làm nguồn sự thật duy nhất cho connection health. Theo dõi signal close/error, keepalive timeout, request timeout và trạng thái reconnect; khi gửi request quan trọng, luôn có deadline phù hợp.

## 13. Phân biệt lỗi keepalive với request timeout

Request timeout có nghĩa một interaction không hoàn thành trong thời gian cho phép. Session keepalive timeout có nghĩa peer/session không được quan sát còn sống. Hai lỗi có thể xảy ra độc lập:

| Tình huống | Request | Session |
|---|---|---|
| Handler xử lý chậm nhưng connection khỏe | Có thể timeout | Vẫn connected |
| Peer chết hoặc tunnel bị đóng | Request đang chờ có thể fail | Session mất |
| Proxy idle timeout khi không có request | Không có request nào đang chờ | Connection bị đóng |
| Server event loop bị block | Request chậm; keepalive cũng có thể trễ | Có thể bị timeout nhầm |

Không tăng request timeout để chữa idle disconnect. Cũng không tăng keepalive max lifetime để chữa handler xử lý quá chậm nếu session vẫn khỏe.

## 14. Chẩn đoán theo từng lớp

Một quy trình có thứ tự giúp tìm đúng lớp gây lỗi:

### Bước 1: Ghi lại thời điểm và trạng thái

Ghi nhận:

- Thời điểm connection được tạo và thời điểm bị đóng.
- Connection có traffic hay idle trước khi mất.
- Client/server close code, error type và reason nếu có.
- RSocket error/keepalive timeout và transport error.
- Instance ID của server xử lý connection.
- Browser/OS, loại mạng và việc tab có ở background hay không.

Không log access token, resume token hoặc payload nhạy cảm.

### Bước 2: So sánh đường truyền trực tiếp và qua proxy

Nếu có thể, chạy cùng client tới endpoint trực tiếp trong môi trường kiểm soát và tới endpoint qua ingress/LB. Nếu direct ổn định nhưng qua proxy bị ngắt sau một khoảng idle cố định, tập trung vào proxy/LB và WebSocket tunnel.

Không bỏ qua firewall hoặc NAT chỉ vì proxy đã được kiểm tra; các thiết bị này có thể nằm trên đường đi của cả hai trường hợp.

### Bước 3: So sánh idle và active traffic

Thử ba trường hợp:

1. Giữ connection mở nhưng không gửi application payload.
2. Gửi application heartbeat định kỳ.
3. Chỉ bật RSocket keepalive và không gửi application payload.

Nếu trường hợp 3 ổn định nhưng trường hợp 1 bị ngắt, RSocket keepalive có thể đang giữ tunnel. Nếu cả 2 và 3 đều bị ngắt, hãy kiểm tra proxy có nhìn thấy frame, cấu hình keepalive, direction và timer thực tế.

### Bước 4: Đối chiếu log các hop

So sánh timestamp giữa client, proxy, load balancer và server. Xác định bên nào chủ động đóng trước, hoặc bên nào ghi nhận timeout trước. Đồng bộ clock bằng NTP và dùng correlation/connection ID để ghép log.

### Bước 5: Quan sát packet/frame

Trong môi trường test, packet capture hoặc log protocol có thể xác nhận:

- TCP FIN/RST đến từ phía nào.
- Có dữ liệu RSocket KEEPALIVE đi qua không.
- WebSocket Ping/Pong có xuất hiện không nếu transport dùng chúng.
- Có khoảng trống traffic dài hơn idle timeout không.
- Connection bị đóng ngay sau một proxy-generated close/reset hay sau keepalive lifetime.

Nếu dùng TLS, packet capture thường không hiển thị nội dung RSocket frame nếu không có giải mã phù hợp; vẫn có thể quan sát thời điểm, kích thước và hướng packet. Không tắt TLS trên production chỉ để đọc payload.

## 15. Checklist log và metrics

Các chỉ số hữu ích:

| Metric | Ý nghĩa |
|---|---|
| `rsocket.connections.active` | Số connection RSocket đang mở. |
| `rsocket.connections.closed` | Số connection đóng theo thời gian. |
| `rsocket.keepalive.sent` | Số keepalive frame được gửi. |
| `rsocket.keepalive.received` | Số keepalive frame nhận được. |
| `rsocket.keepalive.timeout` | Số session bị đóng do keepalive lifetime. |
| `rsocket.transport.error` | Lỗi TCP/WebSocket/transport. |
| `websocket.close.count` | Số lần WebSocket đóng, phân theo close code khi có thể. |
| `proxy.upstream.reset` | Reset từ backend hoặc upstream theo metric của proxy. |
| `connection.duration` | Tuổi thọ connection trước khi đóng. |
| `reconnect.attempt` | Số lần client thử kết nối lại. |
| `resume.success` / `resume.rejected` | Kết quả resumption nếu runtime hỗ trợ. |

Log nên chứa connection ID, remote endpoint đã được phép ghi, transport, server instance, close code/reason, elapsed idle duration và loại timeout. Tránh dùng connection ID hoặc IP đầy đủ làm metric label cardinality cao; có thể giữ chi tiết trong log/trace.

Nếu reconnect rate tăng cùng thời điểm deploy, scale event hoặc proxy config change, đối chiếu với event vận hành trước khi chỉnh keepalive.

## 16. Browser tab nền và mobile sleep

Browser có thể throttle timer khi tab ở background. Trên mobile, hệ điều hành có thể freeze hoặc suspend browser process khi khóa màn hình/chuyển sang ứng dụng khác. Nếu RSocket JavaScript runtime phụ thuộc timer trong event loop để phát keepalive, frame có thể bị trễ hoặc không được gửi trong thời gian trang bị suspend.

Khi đó server có thể kết luận client đã mất sau `maxLifetime`, dù người dùng chỉ chuyển ứng dụng trong một thời gian. Khi quay lại foreground, client cần kiểm tra connection, thử resume nếu runtime hỗ trợ và session còn hiệu lực, nếu không thì reconnect và khôi phục subscription/cursor ở tầng ứng dụng.

Không đặt `maxLifetime` quá ngắn chỉ để phát hiện peer chết nhanh trong môi trường browser. Cân bằng giữa khả năng phát hiện lỗi và hành vi background của nền tảng. Nếu sản phẩm cần nhận sự kiện khi browser không chạy, dùng cơ chế push phù hợp thay vì dựa vào WebSocket luôn sống trong tab bị suspend.

## 17. Reconnect và resumption sau idle disconnect

Keepalive giúp phát hiện connection chết; nó không tự khôi phục session. Khi connection đóng:

1. Dừng gửi request mới trên connection lỗi.
2. Phát signal lỗi tới các request/stream đang chạy theo contract runtime.
3. Đợi reconnect với exponential backoff và jitter.
4. Thử RSocket resumption nếu client/server hỗ trợ và session state còn được giữ.
5. Nếu resume thất bại, mở session mới.
6. Khôi phục subscription bằng cursor hoặc application checkpoint.
7. Retry command có tác dụng phụ bằng cùng idempotency key.

Nếu load balancer route reconnect tới node khác, node mới có thể không có resume state/replay buffer. Cần affinity về node cũ hoặc cơ chế state dùng chung mà implementation thực sự hỗ trợ. Không giả định bật resumption tự động tạo cluster-wide session store.

## 18. Chính sách reconnect tránh tạo bão kết nối

Khi proxy đóng hàng nghìn connection cùng lúc, tất cả client có thể reconnect đồng thời. Điều này tạo tải đột biến lên TLS handshake, authentication, SETUP, service discovery và subscription restoration.

Dùng exponential backoff có jitter:

\[
delay_n = \min(maxDelay, baseDelay \times 2^n) + jitter
\]

Ví dụ một client có thể chờ 0,5 giây, 1 giây, 2 giây, 4 giây rồi tăng tới giới hạn 30 giây; thêm jitter ngẫu nhiên để client không đồng bộ. Reset backoff sau khi connection ổn định một khoảng thời gian, không chỉ ngay sau handshake.

Không retry lỗi authentication hoặc authorization vô hạn. Refresh credential nếu cần rồi tạo session mới theo chính sách bảo mật.

## 19. Kiểm tra server event-loop và GC pause

Keepalive timeout không phải lúc nào cũng do mạng. Server có thể khỏe về kết nối nhưng event loop bị block bởi:

- Gọi blocking database/HTTP API trên event-loop thread.
- CPU-bound computation không offload.
- GC pause dài hoặc native memory pressure.
- Quá nhiều connection/stream trên một event loop.
- Scheduler starvation hoặc thread pool cạn.
- Logging đồng bộ chậm.

Nếu keepalive frame đến nhưng event loop không xử lý kịp hoặc không gửi response đúng hạn, peer có thể timeout. So sánh keepalive timeout với CPU, GC pause, event-loop pending tasks và latency cùng thời điểm. Đừng chỉ tăng interval nếu nguyên nhân là event-loop bị nghẽn; cần loại bỏ blocking work và giới hạn concurrency.

## 20. Kiểm thử timeout nhàn rỗi có kiểm soát

Tạo test matrix cho đường truyền thực:

| Kịch bản | Điều cần xác minh |
|---|---|
| Connection idle dưới timeout | Không bị đóng sớm. |
| Connection idle lâu hơn proxy timeout nhưng có RSocket keepalive | Proxy giữ tunnel nếu frame được tính là activity. |
| Tắt RSocket keepalive trong test | Quan sát idle timeout thực và xác định hop đóng. |
| Keepalive interval lớn hơn proxy idle timeout | Tái hiện lỗi để xác nhận giả thuyết. |
| Keepalive response bị chặn/mất | Runtime phát hiện peer chết theo max lifetime. |
| Event loop bị block có kiểm soát | Đánh giá false timeout khi scheduler trễ. |
| Browser tab background/mobile sleep | Quan sát timer throttle và reconnect khi foreground. |
| Node restart hoặc connection drain | Client reconnect/resume hoặc resync đúng cách. |
| Resume tới node khác | Xác minh affinity/shared-state behavior. |
| Nhiều client cùng reconnect | Backoff/jitter tránh connection storm. |

Đối với unit test logic Reactor, có thể dùng virtual time cho timeout/retry. Nhưng virtual time không điều khiển timer của proxy, TCP stack hoặc Netty event loop. Các tình huống idle timeout thực phải dùng integration test với thời gian thật và giới hạn thời gian test rõ ràng.

## 21. Những lỗi cấu hình thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Keepalive interval lớn hơn proxy idle timeout | Proxy đóng tunnel trước keepalive kế tiếp. | Giảm interval với khoảng đệm hoặc tăng timeout proxy. |
| Chỉ bật TCP keepalive | Probe OS có thể đến quá muộn; không kiểm tra RSocket session. | Cấu hình RSocket keepalive phù hợp và hiểu TCP options riêng. |
| Nghĩ WebSocket Ping/Pong là RSocket KEEPALIVE | Chẩn đoán nhầm tầng và API. | Xác định frame thuộc WebSocket hay RSocket. |
| Chỉ tăng `maxLifetime` | Proxy vẫn có thể đóng tunnel theo idle timeout. | Căn chỉnh traffic interval với timeout từng hop. |
| Đặt max lifetime quá ngắn | Mất kết nối giả khi scheduler/network trễ. | Tính jitter, latency, browser background và event-loop delay. |
| Bỏ qua timeout ở một hop trung gian | Một LB/NAT khác vẫn đóng connection. | Lập sơ đồ toàn tuyến và kiểm tra mọi timeout. |
| Chỉ thử khi có request liên tục | Không phát hiện idle timeout. | Thử connection im lặng trong thời gian dài. |
| Dùng application heartbeat quá thường xuyên | Tăng traffic và tải mà không cần thiết. | Ưu tiên protocol keepalive khi phù hợp; đo tần suất. |
| Giả định browser luôn gửi keepalive khi tab nền | Timer có thể bị throttle hoặc suspend. | Test browser/mobile thực và có reconnect/resume. |
| Retry reconnect ngay lập tức | Connection storm khi nhiều client cùng mất. | Exponential backoff và jitter. |
| Nghĩ keepalive timeout tự resume session | Connection đóng nhưng state không tự khôi phục. | Triển khai resume hoặc reconnect và app-level resync. |
| Chỉ nhìn client log | Không biết proxy/server bên nào đóng trước. | Correlate log giữa client, ingress, LB và server. |

## 22. Quy trình xử lý một incident

Khi production có báo cáo “RSocket mất kết nối mỗi vài phút”, thực hiện theo thứ tự:

1. Thu thập thời gian connection mở/đóng và thời gian idle cuối cùng.
2. Xác định transport TCP hay WebSocket và liệt kê mọi hop.
3. Lấy idle timeout, maximum connection age và read/write timeout của từng hop.
4. Lấy keepalive interval/max lifetime thực tế của client và server, không chỉ giá trị trong file cấu hình.
5. So sánh active traffic với idle connection.
6. Correlate close/error/timeout log giữa các thành phần.
7. Thử endpoint trực tiếp và qua proxy trong môi trường kiểm soát.
8. Kiểm tra event-loop lag, GC pause và CPU nếu lỗi không theo chu kỳ cố định.
9. Thử giá trị interval nhỏ hơn timeout ngắn nhất với khoảng đệm.
10. Kiểm thử reconnect/resumption và command retry an toàn.
11. Theo dõi connection duration, timeout count và reconnect rate sau thay đổi.

Ghi lại cấu hình trước/sau, phạm vi rollout và kết quả trên từng loại client. Thay đổi một nhóm timeout tại một thời điểm để biết yếu tố nào thực sự làm thay đổi triệu chứng.

## 23. Checklist phòng ngừa

- Phân biệt RSocket KEEPALIVE, WebSocket Ping/Pong, TCP keepalive và application heartbeat.
- Biết idle timeout ngắn nhất trên toàn bộ đường truyền.
- Đặt keepalive interval thấp hơn timeout đó với khoảng đệm đủ lớn.
- Đặt max lifetime phù hợp với interval, jitter và mục tiêu phát hiện peer chết.
- Xác minh proxy tính traffic theo hướng nào và có tính RSocket frame là activity không.
- Kiểm tra cả read timeout, write timeout, idle timeout và maximum connection duration.
- Kiểm tra NAT, firewall, VPN và mobile network policy.
- Theo dõi close code, transport error, keepalive timeout và connection duration.
- Không block Netty event loop; theo dõi GC/event-loop lag.
- Có reconnect backoff/jitter, resumption hoặc app-level resync.
- Giữ idempotency key ổn định khi retry command có tác dụng phụ.
- Kiểm thử connection idle thật, browser background và node restart.
- Không dùng virtual time để kết luận proxy/TCP/Netty timer đã được kiểm thử.

## Tài liệu tham khảo

- [RSocket Protocol](https://rsocket.io/about/protocol/) — frame KEEPALIVE, SETUP và connection resumption.
- [RSocket Java](https://github.com/rsocket/rsocket-java) — API connector/server và cấu hình runtime.
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455) — WebSocket Ping/Pong và control frames.
- [RFC 1122 — Requirements for Internet Hosts](https://www.rfc-editor.org/rfc/rfc1122) — TCP keepalive behavior và các yêu cầu liên quan.
- [NGINX WebSocket proxying](https://nginx.org/en/docs/http/websocket.html) — cấu hình tunnel WebSocket qua reverse proxy.

## Kết luận

Mất kết nối định kỳ khi idle thường do timeout ở một lớp trên đường truyền hoặc do RSocket peer không nhận được keepalive trong thời hạn cho phép. RSocket KEEPALIVE, WebSocket Ping/Pong và TCP keepalive kiểm tra các lớp khác nhau; proxy, NAT và firewall lại có idle timeout riêng. Hãy xác định timeout ngắn nhất trên toàn tuyến, đặt keepalive interval thấp hơn với khoảng đệm, chọn max lifetime phù hợp và xác minh frame thực sự đi qua proxy. Khi điều tra, so sánh connection idle với active traffic, correlate log các hop và kiểm tra event-loop/GC nếu lỗi không theo chu kỳ. Keepalive chỉ phát hiện session mất; ứng dụng vẫn cần reconnect/resumption, phục hồi subscription và retry command có idempotency để chịu được gián đoạn.
