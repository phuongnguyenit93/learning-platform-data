# Ảnh hưởng của kết nối dài hạn đến phân phối tải giữa các máy chủ

RSocket thường giữ một kết nối transport mở trong thời gian dài và multiplex nhiều stream trên cùng kết nối. Khi client kết nối qua TCP hoặc WebSocket đến một cụm server phía sau load balancer, load balancer thường chọn backend tại thời điểm thiết lập connection. Những request và stream RSocket tiếp theo trên connection đó tiếp tục đi đến cùng backend.

Vì vậy, **cân bằng đều số connection mới không đồng nghĩa cân bằng đều tải xử lý**. Một node có thể giữ ít connection nhưng mỗi connection mang nhiều stream hoặc lưu lượng lớn; node khác có nhiều connection nhàn rỗi. Khi scale out, node mới thường chỉ nhận connection mới, còn các connection cũ vẫn ghim vào node hiện tại. Muốn phân phối tải tốt, cần tính đến số connection, số stream đang hoạt động, lưu lượng, thời gian xử lý, session affinity, resumption và quy trình drain node.

## 1. Connection, session và stream là ba lớp khác nhau

Khi thiết kế load balancing cho RSocket, cần phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa | Ảnh hưởng đến cân bằng tải |
|---|---|---|
| Transport connection | Kết nối TCP hoặc WebSocket giữa client và server/gateway. | Thường là đơn vị mà L4/L7 load balancer chọn backend. |
| RSocket session | Trạng thái giao thức gắn với một kết nối RSocket; có thể có resumption nếu hai bên hỗ trợ. | Có thể cần affinity hoặc trạng thái dùng chung khi reconnect/resume. |
| RSocket stream | Một tương tác như request-response, request-stream, fire-and-forget hoặc channel. | Nhiều stream có thể multiplex trên cùng connection và cùng backend. |

Một connection có thể mang nhiều stream đồng thời:

```text
Client
  |
  | TCP / WebSocket connection
  v
Load balancer
  |
  +--------------------------> RSocket node A
                                 |
                                 +-- stream 1: request-response
                                 +-- stream 3: telemetry stream
                                 +-- stream 5: request-channel
                                 +-- stream 7: fire-and-forget
```

Nếu load balancer chọn node A cho connection này, các stream trên connection đó không tự được phân phối sang node B hoặc C. Đây là hệ quả của việc multiplex stream trên một transport connection.

## 2. Load balancer thường chọn backend ở thời điểm nào?

Với RSocket qua TCP, L4 load balancer thường chọn backend khi thiết lập TCP connection. Với RSocket qua WebSocket, L7 proxy xử lý HTTP Upgrade handshake rồi giữ một tunnel WebSocket lâu dài đến backend đã chọn.

```text
Browser / Java client
        |
        | mở TCP hoặc WebSocket
        v
Load balancer
        |
        | chọn backend một lần cho connection
        v
   RSocket node B
        |
        +-- mọi stream trên connection
        +-- mọi request tiếp theo
        +-- metadata và payload của các tương tác
```

Load balancer HTTP thông thường không nhìn thấy từng RSocket frame bên trong WebSocket tunnel. Nó có thể định tuyến handshake dựa trên host, path, header hoặc cookie, nhưng sau khi tunnel được thiết lập, nó thường không phân phối từng request-response hoặc từng stream sang backend khác.

Chỉ một proxy hiểu RSocket protocol và được thiết kế để xử lý multiplexing mới có thể áp dụng chính sách ở cấp stream. Không giả định một cấu hình round-robin HTTP thông thường sẽ cân bằng từng RSocket request.

## 3. Vì sao kết nối dài hạn gây lệch tải?

Các thuật toán round-robin hoặc least-connections thường được áp dụng khi có connection mới. Với HTTP request ngắn, request hoàn tất rồi kết nối có thể được tái sử dụng hoặc đóng; qua thời gian, nhiều request mới có cơ hội đi tới nhiều node. Với RSocket, connection có thể tồn tại hàng giờ hoặc hàng ngày, vì vậy quyết định ban đầu có ảnh hưởng lâu dài.

Một số nguyên nhân tạo ra skew:

- **Thời điểm kết nối khác nhau:** node nhận nhiều connection trong một khoảng thời gian có thể tiếp tục giữ chúng lâu sau khi tải cụm thay đổi.
- **Tuổi thọ connection khác nhau:** connection cũ không tự chuyển sang node mới khi thêm replica.
- **Số stream khác nhau:** một connection có thể mang một stream nhàn rỗi hoặc hàng nghìn stream hoạt động.
- **Lưu lượng không đồng đều:** một số client phát telemetry liên tục, client khác chỉ gửi lệnh thỉnh thoảng.
- **Chi phí xử lý khác nhau:** stream có thể chạy truy vấn nặng, giữ buffer lớn hoặc gọi downstream chậm.
- **Kết nối idle:** số socket lớn có thể làm tăng memory/file descriptor dù CPU thấp.

Ví dụ, ba node mỗi node có 100 connection không có nghĩa tải bằng nhau:

| Node | Connection | Active streams | Lưu lượng vào | CPU |
|---|---:|---:|---:|---:|
| A | 100 | 1.800 | 80 MB/s | 78% |
| B | 100 | 420 | 18 MB/s | 31% |
| C | 100 | 260 | 9 MB/s | 19% |

Số connection bằng nhau nhưng node A nóng hơn nhiều. Nếu chỉ dùng connection count để quyết định autoscaling hoặc phân phối, hệ thống sẽ không nhìn thấy chênh lệch này.

## 4. Round-robin không tự cân bằng các stream trên connection

Giả sử load balancer phân phối 6 connection mới theo round-robin:

```text
Connection 1 -> Node A
Connection 2 -> Node B
Connection 3 -> Node C
Connection 4 -> Node A
Connection 5 -> Node B
Connection 6 -> Node C
```

Sau đó connection 1 mở 500 stream còn connection 2 chỉ mở 2 stream. Phân phối connection vẫn đều, nhưng tải không đều.

Round-robin có ích khi connection có workload tương đối giống nhau và được tạo/đóng thường xuyên. Nó kém phản ánh tải khi connection sống lâu, có số stream hoặc throughput khác nhau đáng kể.

Least-connections có thể tốt hơn khi connection count tương quan với chi phí giữ socket. Tuy nhiên, nó vẫn chỉ quan sát connection, không nhất thiết quan sát số stream, bytes, CPU hoặc độ trễ. Một connection nặng và một connection idle được tính như nhau nếu thuật toán chỉ đếm socket.

## 5. Các tầng cân bằng tải

Không có một thuật toán duy nhất phù hợp cho mọi kiến trúc RSocket. Cần xác định tầng nào thực sự có thể phân phối lại công việc.

| Tầng | Đơn vị phân phối | Ví dụ chính sách | Giới hạn |
|---|---|---|---|
| DNS/client discovery | Địa chỉ endpoint hoặc node khi client kết nối | DNS nhiều A record, service discovery | Client có thể cache DNS và giữ connection rất lâu. |
| L4 load balancer | TCP connection | Round-robin, least connections, weighted backend | Không hiểu RSocket stream bên trong connection. |
| L7 WebSocket proxy | WebSocket handshake/tunnel | Host/path/header/cookie routing | Sau Upgrade, thường giữ tunnel đến một backend. |
| RSocket-aware proxy | Có thể hiểu protocol/stream nếu triển khai hỗ trợ | Chính sách theo route hoặc stream | Cần proxy chuyên dụng, kiểm tra semantics và hỗ trợ resumption. |
| Client-side connection pool | Lựa chọn một connection trong pool | Round-robin, least-loaded, consistent hash | Client cần quản lý nhiều connection và state. |
| Application/service layer | Công việc nghiệp vụ hoặc message/event | Partition theo key, worker queue, consumer group | Không thay thế cân bằng transport connection. |

Khi phân tích sự cố, hãy xác định backend được chọn ở tầng nào. Nếu WebSocket gateway đã gắn tunnel vào node A, thay đổi thuật toán trong service layer sẽ không tự chuyển các stream của tunnel đó sang node B.

## 6. Sticky session và connection affinity

Một connection TCP/WebSocket đang mở tự nhiên có affinity với backend đã accept connection. Sticky session ở L7 thường dùng cookie hoặc một routing key trong handshake để chọn lại cùng backend khi client tạo connection mới.

Affinity cần thiết nếu server giữ trạng thái chỉ có trong bộ nhớ local, ví dụ:

- Session hoặc subscription state không được lưu ở nơi dùng chung.
- Replay buffer của RSocket resumption chỉ tồn tại trên một node.
- Một workflow đang giữ tài nguyên local hoặc actor state.
- Dữ liệu tạm thời chỉ có thể được truy cập tại node đã tạo nó.

Tuy nhiên, sticky session cũng có mặt trái: node đang nóng có thể tiếp tục nhận các reconnect của nhóm client gắn với nó; node mới không nhận được phần tải của những connection cũ. Affinity cải thiện tính liên tục của state nhưng làm giảm khả năng tái phân phối linh hoạt.

Nếu ứng dụng stateless hoặc state được lưu ở shared store, có thể cân nhắc phân phối connection mới tự do hơn. Khi đó vẫn phải xử lý đúng trạng thái của stream đang chạy và connection resumption.

## 7. Connection resumption cần được định tuyến đúng node

RSocket resumption có thể tiếp tục một session sau khi transport bị gián đoạn, nhưng server cần tìm được session state và replay buffer tương ứng. Nếu client reconnect qua load balancer rồi được đưa sang node khác, node mới có thể không biết resume token hoặc không có dữ liệu replay.

Có hai hướng kiến trúc chính:

**Giữ affinity đến node cũ:** load balancer dùng routing affinity hoặc cơ chế discovery để request RESUME quay lại đúng node còn giữ session. Cần xử lý trường hợp node cũ đã chết hoặc session hết hạn.

**Chia sẻ/phân tán trạng thái resumption:** các node có thể tìm session và replay state từ một kho hoặc cơ chế cluster dùng chung, nếu RSocket implementation hỗ trợ. Không phải mọi thư viện/server đều cung cấp khả năng này chỉ bằng cách bật resumption.

```text
Client reconnect
      |
      | RESUME(token, positions)
      v
Load balancer
      |
      +--> Node A: có session/replay buffer -> RESUME_OK
      |
      +--> Node B: không có state -> resume bị từ chối
```

Nếu resume bị từ chối, client cần mở session mới và phục hồi trạng thái nghiệp vụ bằng cursor, subscription intent hoặc command ID. Không giả định sticky cookie luôn được gửi trong mọi kiểu reconnect; hãy kiểm tra transport và cơ chế resume thực tế của client library.

## 8. Tác động khi scale out

Khi thêm node mới, load balancer thường đưa node vào pool cho các connection mới sau khi health check và service discovery cập nhật. Các connection đang mở vẫn giữ backend cũ.

```text
Trước scale out:
  Client A ----> Node 1 (nhiều connection cũ)
  Client B ----> Node 2 (nhiều connection cũ)

Thêm Node 3:
  Client C ----> Node 3 (chỉ nhận connection mới)
  Client A ----> Node 1 (vẫn giữ nguyên)
  Client B ----> Node 2 (vẫn giữ nguyên)
```

Kết quả có thể là node 3 ít tải trong một thời gian dài, trong khi node 1 vẫn quá tải. Autoscaling thêm replica không tự di chuyển connection hoặc stream hiện tại.

Các cách xử lý:

- Cho client mở một pool connection có kích thước phù hợp để những connection mới có thể phân phối tới node mới.
- Dùng chính sách drain/reconnect có kiểm soát để giải phóng dần connection cũ.
- Thiết kế service stateless hoặc chia sẻ state để giảm phụ thuộc node.
- Phân phối workload ở tầng application queue/partition thay vì trông chờ load balancer di chuyển stream.
- Theo dõi thời gian cần để tải hội tụ sau scale out; không chỉ nhìn replica count.

Không ép tất cả client reconnect cùng lúc sau khi scale out. Reconnect storm có thể làm tăng handshake, authentication, TLS và tải khởi tạo stream.

## 9. Tác động khi scale in hoặc triển khai phiên bản mới

Scale in nguy hiểm hơn vì node sắp bị loại có thể đang giữ nhiều connection dài hạn. Nếu chỉ xóa node khỏi service discovery, connection đã được thiết lập có thể vẫn tồn tại đến khi client/server đóng hoặc timeout.

Một quy trình drain có kiểm soát:

1. Đánh dấu node không nhận connection mới bằng readiness/endpoint discovery.
2. Chờ load balancer và service registry ngừng gửi connection mới tới node.
3. Đánh dấu ứng dụng đang draining và từ chối tạo workload mới nếu contract cho phép.
4. Cho request/stream đang chạy hoàn tất trong một grace period có giới hạn.
5. Gửi tín hiệu ứng dụng hoặc đóng connection còn lại theo chính sách.
6. Client reconnect với backoff và jitter, thử resume nếu session còn hợp lệ.
7. Xác minh node đã giải phóng connection, stream và tài nguyên trước khi process kết thúc.

Nếu node bị kill ngay lập tức, client có thể mất transport và phải resume/reconnect. Với request đang có tác dụng phụ, dùng idempotency key để retry an toàn.

## 10. Graceful draining trong môi trường container

Trong Kubernetes hoặc nền tảng container tương tự, readiness probe thường quyết định pod có còn nhận traffic mới hay không. Khi triển khai:

- Chuyển readiness sang trạng thái không sẵn sàng trước khi dừng process.
- Dùng `preStop`/termination hook để bắt đầu drain nếu nền tảng hỗ trợ.
- Đặt `terminationGracePeriodSeconds` đủ dài cho khoảng drain đã thiết kế.
- Chờ endpoint propagation và load balancer cập nhật backend pool.
- Đóng connection còn lại trước khi hết grace period.
- Theo dõi số connection/stream còn lại trong lúc drain.

Readiness không tự đóng connection đã mở. Nó chủ yếu ngăn các kết nối mới được định tuyến tới pod. Ứng dụng vẫn cần logic drain và timeout để xử lý connection hiện hữu.

Nếu có WebSocket proxy phía trước, cần kiểm tra proxy có tiếp tục giữ tunnel tới pod sau khi pod bị đánh dấu unready hay không. Hành vi phụ thuộc nền tảng và cấu hình; không giả định endpoint removal sẽ tự động kết thúc mọi WebSocket.

## 11. Client-side connection pool

Một client có thể duy trì nhiều RSocket connection tới cùng service thay vì dồn mọi stream vào một connection duy nhất. Khi cần mở một tương tác mới, client chọn một connection trong pool theo round-robin, least-active hoặc hash theo key.

```text
Client connection pool
  |
  +-- connection 1 ----> Load balancer ----> Node A
  +-- connection 2 ----> Load balancer ----> Node C
  +-- connection 3 ----> Load balancer ----> Node B
  +-- connection 4 ----> Load balancer ----> Node A

Mỗi connection có thể multiplex nhiều RSocket stream.
```

Pool giúp một client có nhiều cơ hội được phân phối qua các node, nhưng không bảo đảm mọi connection đi tới node khác nhau. Quyết định backend vẫn thuộc load balancer. Nếu sticky routing dùng cùng cookie hoặc key, nhiều connection có thể tiếp tục về cùng node.

Khi xây dựng pool, cân nhắc:

- Số connection tối đa trên mỗi client/process.
- Số stream đồng thời và giới hạn request trên từng connection.
- Cách chọn connection theo active streams, latency hoặc lỗi gần đây.
- Reconnect/resume cho từng connection độc lập.
- Giới hạn file descriptor, memory và TLS handshake ở client/server.
- Đóng pool đúng vòng đời ứng dụng.

Không tạo một connection mới cho mọi request. Điều đó làm mất lợi ích multiplexing và tăng chi phí handshake, socket, TLS, keepalive và tài nguyên server.

## 12. Chọn connection theo tải ở client

Nếu client quản lý pool, có thể chọn connection dựa trên số stream đang hoạt động hoặc độ trễ gần đây. Ví dụ thuật toán khái niệm:

```text
for each new interaction:
    candidates = healthy connections
    choose connection with lowest weighted score
    open the RSocket stream on that connection

score(connection) =
    activeStreams * streamWeight
  + pendingRequests * pendingWeight
  + recentLatency * latencyWeight
```

Đây là thuật toán minh họa, không phải API chuẩn của RSocket. Client chỉ nhìn thấy connection mà nó đã mở; nó không nhất thiết biết node backend nào đang phục vụ connection nếu load balancer không cung cấp thông tin an toàn. Vì vậy, lựa chọn connection ít stream ở client giúp phân phối trong pool nhưng không thay thế telemetry và capacity management phía server.

Nếu một interaction mở stream dài hạn, pool có thể cần dành riêng một số connection cho subscription hoặc chia pool theo loại workload. Điều này tránh các stream lâu dài chiếm hết khả năng mở request ngắn trên một connection, nhưng làm tăng số socket và độ phức tạp vận hành.

## 13. Phân vùng theo khóa nghiệp vụ

Một số hệ thống cần mọi thao tác trên cùng một aggregate đi tới cùng partition hoặc owner, ví dụ tất cả lệnh của một thiết bị hoặc một tài khoản. Khi đó, consistent hashing hoặc partition routing có thể tạo affinity theo key nghiệp vụ.

```text
device-01 -> partition 0 -> owner node A
device-02 -> partition 1 -> owner node B
device-03 -> partition 0 -> owner node A
device-04 -> partition 2 -> owner node C
```

Hash theo key giúp duy trì locality, nhưng khi thêm/bớt node có thể làm thay đổi mapping. Consistent hashing hoặc virtual nodes giảm lượng key phải di chuyển, song không loại bỏ yêu cầu chuyển trạng thái và xử lý request đang chạy.

Không dùng client-supplied key để bỏ qua authorization. Server phải xác minh caller có quyền với tenant/aggregate trước khi định tuyến hoặc thực hiện lệnh. Nếu partition owner thay đổi, cần cơ chế epoch/fencing để node cũ không tiếp tục ghi dữ liệu sau khi quyền sở hữu đã chuyển.

## 14. Cân bằng tải theo số stream và công việc thực tế

Nếu hạ tầng chỉ cân bằng theo connection, ứng dụng cần cung cấp metric cấp cao hơn để phát hiện node nóng. Các chỉ số hữu ích:

| Chỉ số | Cho biết điều gì? |
|---|---|
| Open connections | Số socket/transport đang tồn tại. |
| Active RSocket streams | Số tương tác đang hoạt động trên các connection. |
| Streams theo interaction model | Tỷ lệ request-response, stream, channel và fire-and-forget. |
| Inbound/outbound messages và bytes | Throughput thực tế của node. |
| Pending requests/queued work | Áp lực backlog và khả năng xử lý không theo kịp. |
| CPU/event-loop utilization | Mức bận xử lý và nguy cơ event loop bị nghẽn. |
| Heap/direct memory và buffer usage | Chi phí giữ payload, connection và queue. |
| p95/p99 latency | Chất lượng phản hồi dưới tải. |
| Error, timeout, cancel và reconnect rate | Tín hiệu quá tải hoặc kết nối không ổn định. |

Không dùng một metric đơn lẻ làm đại diện cho mọi tải. Ví dụ số connection thấp nhưng bytes/s cao có thể cho thấy một node xử lý stream nặng; số connection cao nhưng active streams thấp có thể chủ yếu tạo áp lực memory và file descriptor.

## 15. Lease và giới hạn phát request

RSocket protocol có extension LEASE cho phép responder quảng bá giới hạn số request mà requester được phép khởi tạo trong một khoảng thời gian. Nếu implementation và deployment hỗ trợ lease, nó có thể giúp server kiểm soát admission và giảm quá tải.

Lease không phải cơ chế tự động chuyển stream đang chạy sang node khác và không thay thế load balancer. Nó điều tiết việc mở request mới theo contract của protocol. Cần xác minh cả client và server runtime hỗ trợ, cách cấu hình lease và cách ứng dụng phản ứng khi không còn lease.

Khi không có lease, ứng dụng vẫn cần giới hạn concurrency ở client, backpressure, rate limit và admission control ở server. Không dựa vào load balancer để giải quyết quá tải bên trong một connection đã được thiết lập.

## 16. Timeout của proxy và keepalive

WebSocket/RSocket connection có thể bị proxy hoặc load balancer đóng nếu không có traffic trong idle timeout. RSocket KEEPALIVE và WebSocket ping/pong có vai trò khác nhau ở các tầng khác nhau:

- WebSocket ping/pong kiểm tra transport WebSocket giữa hai endpoint.
- RSocket KEEPALIVE là frame ở tầng RSocket để peer theo dõi session và có thể mang position phục vụ resumption.
- TCP keepalive là cơ chế ở tầng TCP/OS, phụ thuộc cấu hình socket và hệ điều hành.

Các timeout cần tương thích với nhau. Nếu proxy idle timeout ngắn hơn khoảng keepalive hiệu dụng, tunnel có thể bị đóng dù RSocket runtime nghĩ connection vẫn hoạt động. Nếu keepalive quá thường xuyên, hệ thống tăng traffic và chi phí pin/CPU.

Hãy cấu hình và kiểm thử:

1. Idle timeout của load balancer và WebSocket gateway.
2. RSocket keepalive interval và lifetime ở cả hai phía.
3. TCP keepalive nếu được dùng.
4. Timeout của firewall/NAT/proxy trung gian.
5. Hành vi khi tab browser nền bị throttle hoặc thiết bị sleep.

## 17. Failure isolation và giới hạn trên mỗi node

Một node nhận quá nhiều connection hoặc stream có thể ảnh hưởng các client khác. Cần giới hạn tài nguyên ở nhiều cấp:

- Số connection tối đa trên node.
- Số stream hoặc request đang hoạt động.
- Số request đồng thời tới downstream.
- Kích thước payload và buffer.
- Rate limit theo principal/tenant/route.
- Timeout cho stream và request có thể kết thúc.
- Admission control khi node vượt ngưỡng tải.

Khi node quá tải, từ chối sớm một request mới có thể tốt hơn nhận mọi request rồi làm toàn bộ event loop chậm. Tuy nhiên, chính sách từ chối phải trả lỗi có thể hiểu được để client backoff; không để client retry ngay lập tức theo vòng lặp.

Với stream dài hạn, đặt giới hạn thời gian hoặc quy trình renew nếu nghiệp vụ cho phép. Không cắt stream chỉ để cân bằng tải mà không có cursor/replay hoặc hợp đồng phục hồi ở tầng ứng dụng.

## 18. Ví dụ triển khai kiến trúc cân bằng tải

Một triển khai điển hình có browser client qua WebSocket và Java service qua TCP hoặc WebSocket:

```text
Browser clients
      |
      | WSS
      v
WebSocket ingress / L7 load balancer
      |
      +--------+---------+
      |        |         |
      v        v         v
    Node A   Node B    Node C
      |        |         |
      +--------+---------+
               |
       Shared application state
       - session/ownership metadata
       - idempotency records
       - event log / cursor store
       - distributed cache (nếu phù hợp)
```

Trong kiến trúc này:

- Ingress phân phối WebSocket connection mới tới các node healthy.
- Mỗi connection giữ backend đã chọn trong suốt vòng đời tunnel.
- Các node dùng shared state cho dữ liệu nghiệp vụ cần truy cập chéo node.
- Event log/cursor cho phép client khôi phục subscription sau session mới.
- Idempotency record giúp retry command an toàn khi connection bị mất.
- Drain loại node khỏi pool connection mới rồi cho connection cũ kết thúc có kiểm soát.

Nếu RSocket resumption yêu cầu state local, cần bổ sung affinity hoặc cơ chế chia sẻ state tương thích với implementation; shared application database không tự động đồng nghĩa replay buffer cũng được chia sẻ.

## 19. Đọc một tình huống mất cân bằng

Giả sử cụm có ba node và node A đang CPU 85%, trong khi B và C dưới 30%. Trước khi tăng replica, hãy kiểm tra:

1. A có nhiều connection hơn hay chỉ nhiều active streams hơn?
2. Một vài connection có throughput hoặc stream count vượt trội không?
3. Có sticky session khiến một nhóm client luôn quay về A không?
4. A có giữ session/replay buffer hoặc actor state local không?
5. Các request nặng có bị dồn vào cùng route/tenant/partition không?
6. B và C có thực sự healthy và được đưa vào backend pool không?
7. Connection mới có được phân phối tới B/C sau lần deploy gần nhất không?
8. Node A có backlog downstream hoặc event loop bị block khiến latency tăng không?

Nếu A có ít connection nhưng mỗi connection mang nhiều stream nặng, thay đổi thuật toán từ round-robin sang least-connections có thể không giải quyết vấn đề. Cần phân phối connection mới, dùng client pool, partition workload hoặc drain connection nóng theo chính sách có kiểm soát.

## 20. Kiểm thử load balancing với connection dài hạn

Kiểm thử cần mô phỏng tuổi thọ connection và phân bố stream, không chỉ tạo nhiều request ngắn rồi đo response time.

Các kịch bản nên có:

1. Tạo nhiều connection WebSocket/TCP và xác minh phân phối backend ban đầu.
2. Giữ connection mở lâu, sau đó mở thêm connection và quan sát phân phối.
3. Trên một connection, mở nhiều stream; xác minh tất cả được phục vụ bởi backend gắn với connection đó trong kiến trúc LB thông thường.
4. Tạo workload lệch: một số connection phát nhiều bytes/streams, số khác idle.
5. Scale out thêm node và đo thời gian tải chuyển dần sang node mới.
6. Drain một node đang giữ connection dài hạn; xác minh connection mới không đến node đó và connection cũ kết thúc theo grace period.
7. Làm node mất đột ngột; xác minh reconnect, resume hoặc app-level resync.
8. Kiểm tra resume khi reconnect tới đúng node và khi bị route sang node khác.
9. Kiểm tra retry command có tác dụng phụ với idempotency key.
10. Tăng số client đồng thời để đo connection limit, active streams, memory, CPU và p99 latency.
11. Kiểm tra proxy idle timeout và keepalive khi stream không phát dữ liệu.
12. Kiểm tra client pool có phân phối connection và giới hạn số socket như dự kiến.

Nên gắn backend instance ID vào log/metric nội bộ để quan sát connection được accept ở node nào. Không đưa instance ID hoặc connection ID có cardinality cao vào metric label nếu làm hệ thống monitoring quá tải; có thể dùng log hoặc trace cho chi tiết từng connection.

## 21. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ round-robin cân bằng từng RSocket stream | Một connection có nhiều stream vẫn đi về một node. | Hiểu load balancer đang phân phối TCP/WebSocket connection hay RSocket stream. |
| Chỉ đo số connection | Bỏ qua stream count, throughput và độ nặng của workload. | Theo dõi active streams, bytes, backlog, CPU, memory và latency. |
| Scale out rồi kỳ vọng connection cũ tự chuyển node | Node mới chỉ nhận connection mới. | Drain/reconnect có kiểm soát hoặc dùng tầng phân phối workload khác. |
| Dùng sticky session cho mọi tình huống | Node nóng tiếp tục giữ client và khó tái phân phối. | Chỉ dùng affinity khi state/session thực sự yêu cầu. |
| Resume sang node bất kỳ | Node mới có thể không có session/replay buffer. | Affinity về node cũ hoặc dùng resumption state phân tán được hỗ trợ. |
| Chỉ dùng readiness để drain | Connection cũ có thể tiếp tục mở trên pod đã unready. | Có drain logic, grace period và đóng connection rõ ràng. |
| Tạo một connection cho mỗi request | Tăng socket, handshake, TLS và chi phí keepalive. | Reuse connection và multiplex stream; dùng pool có giới hạn khi cần. |
| Một connection duy nhất cho toàn bộ workload client | Một tunnel có thể trở thành điểm nóng hoặc giới hạn fault isolation. | Cân nhắc connection pool và phân loại workload. |
| Timeout proxy ngắn hơn keepalive | Tunnel bị đóng ngoài dự kiến. | Đồng bộ timeout ở proxy, WebSocket, RSocket và TCP. |
| Reconnect đồng loạt khi node restart | Tạo connection storm và quá tải handshake. | Exponential backoff, jitter và giới hạn reconnect. |
| Retry command sau disconnect mà không có idempotency | Side effect có thể chạy lặp. | Giữ idempotency key ổn định và deduplicate ở server. |
| Dùng connection count làm giới hạn duy nhất | Một connection nặng có thể làm node quá tải dù socket count thấp. | Kết hợp giới hạn stream, concurrency, throughput và resource. |

## 22. Checklist thiết kế

Trước khi đưa RSocket vào cụm production, hãy xác định:

- Load balancer phân phối ở TCP connection, WebSocket handshake hay cấp RSocket stream?
- Một connection có thể giữ tối đa bao nhiêu stream và bao nhiêu dữ liệu?
- Node có state local nào buộc phải dùng sticky session không?
- Connection resumption được route về đúng node bằng cách nào?
- Khi scale out, connection cũ được giữ, drain hay reconnect theo chính sách nào?
- Khi scale in/deploy, readiness và graceful shutdown có phối hợp với LB không?
- Client có cần pool nhiều connection; pool được giới hạn và giám sát ra sao?
- Có metric active streams, throughput, pending work, CPU, memory và latency theo node không?
- Keepalive có tương thích với idle timeout của proxy/firewall không?
- Retry có backoff/jitter và idempotency cho side effect không?
- Có kiểm thử node failure, resume rejection, scale out/in và connection skew không?

## Kết luận

Kết nối RSocket dài hạn làm thay đổi cách cân bằng tải: load balancer thường chọn backend khi TCP/WebSocket connection được thiết lập, rồi giữ mọi stream multiplex trên connection đó ở cùng node. Round-robin theo connection count vì thế không phản ánh đầy đủ tải thực tế. Hệ thống cần quan sát active streams, throughput, backlog, CPU, memory và latency; cân nhắc sticky session chỉ khi state yêu cầu; bảo đảm resumption quay lại node có session state hoặc dùng cơ chế chia sẻ được hỗ trợ; và drain connection có kiểm soát khi scale in. Client-side connection pool, partition routing, admission control và idempotent retry có thể bổ sung cho cân bằng transport. Kiểm thử với connection sống lâu và workload lệch mới cho thấy phân phối tải thực tế của cụm RSocket.
