# Khác biệt giữa logical RPC và network exchange

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt một **logical RPC** ở tầng ứng dụng với một **network exchange** ở tầng HTTP/2 và transport.
- Mô tả quan hệ giữa generated stub, ClientCall, attempt, HTTP/2 stream, frame, TCP connection, TLS record và packet.
- Giải thích vì sao một logical RPC có thể tạo nhiều network attempt, còn một stream có thể mang nhiều message và nhiều frame.
- Đọc request/response headers, DATA và trailers của một RPC unary hoặc streaming.
- Hiểu tác động của retry, deadline, cancellation và reconnect lên số attempt và trạng thái quan sát ở client/server.
- Thiết kế metrics, logs và tracing để không đếm nhầm RPC, stream, connection và packet trong ứng dụng Spring gRPC.

## 1. Logical RPC là thao tác mà ứng dụng yêu cầu

Trong **SPRING_GRPC**, service contract định nghĩa các method như GetOrder hoặc WatchOrder. Khi code Spring gọi một generated stub, ứng dụng yêu cầu thực hiện một **logical RPC**: một thao tác từ xa có method, request, response hoặc stream, deadline, metadata và kết quả cuối cùng.

Ví dụ:

~~~java
GetOrderResponse response = orderStub
        .withDeadlineAfter(800, TimeUnit.MILLISECONDS)
        .getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("order-42")
                        .build());
~~~

Ở góc nhìn ứng dụng, đây là một lần gọi GetOrder. Caller quan tâm response hoặc lỗi cuối cùng; không cần biết runtime đã phải resolve DNS, mở connection, gửi bao nhiêu HTTP/2 frame hay thực hiện retry.

Một logical RPC có các đặc điểm:

- Được xác định bởi service/method, ví dụ **demo.orders.v1.OrderService/GetOrder**.
- Có request và kiểu giao tiếp được khai báo trong Protocol Buffers.
- Có call options như deadline, credentials và compressor.
- Có vòng đời bắt đầu/kết thúc ở API gRPC: response hoàn tất hoặc call kết thúc bằng status.
- Có thể đi qua resolver, load balancer, proxy và nhiều thành phần transport.

Logical RPC là khái niệm ở tầng API/ứng dụng. Nó không đồng nghĩa với một TCP connection, một HTTP/2 frame hay một packet trên mạng.

## 2. Network exchange là cách RPC được vận chuyển

Một **network exchange** là phần trao đổi thực tế giữa client và server qua các tầng giao thức. Với native gRPC trên HTTP/2, một attempt thường được biểu diễn bằng một HTTP/2 stream trên một HTTP/2 connection.

~~~mermaid
flowchart TB
    A["Spring application call"]
    B["Generated stub"]
    C["Logical RPC / ClientCall"]
    D["Attempt 1"]
    E["HTTP/2 stream"]
    F["HTTP/2 HEADERS + DATA + trailers"]
    G["TCP connection"]
    H["TLS records"]
    I["IP packets / network"]
    A --> B --> C --> D --> E --> F --> G --> H --> I
~~~

Các tầng không có quan hệ một-một:

| Tầng | Đơn vị | Ý nghĩa |
| --- | --- | --- |
| Ứng dụng | **Logical RPC** | Một thao tác mà caller yêu cầu |
| gRPC runtime | **ClientCall / attempt** | Quản lý call và một lần thử thực hiện call |
| HTTP/2 | **Stream** | Kênh hai chiều logic cho một attempt |
| HTTP/2 | **Frame** | HEADERS, DATA, RST_STREAM, WINDOW_UPDATE... |
| Transport | **TCP connection** | Kết nối byte stream có thể mang nhiều HTTP/2 stream |
| Bảo mật | **TLS record** | Đơn vị mã hóa của TLS |
| Mạng | **IP packet** | Đơn vị truyền ở tầng IP |

Vì vậy, không thể kết luận một RPC tương ứng với một connection hoặc một packet. Một connection có thể mang hàng trăm RPC đồng thời; một RPC có thể tạo nhiều frame; frame và TLS record lại có thể được chia/ghép thành các packet theo cách transport thực hiện.


## 3. Quan hệ giữa logical RPC, attempt và HTTP/2 stream

Với một call không retry, mô hình thường gặp là:

~~~text
Một lần gọi generated stub
    |
    +-- một logical RPC
           |
           +-- một attempt
                  |
                  +-- một HTTP/2 stream
                         |
                         +-- HEADERS
                         +-- một hoặc nhiều DATA frames
                         +-- trailing HEADERS
~~~

**Attempt** là một lần runtime thử thực hiện logical RPC. Trong trường hợp thông thường, một attempt dùng một HTTP/2 stream. Khi gRPC retry policy tạo attempt mới, runtime mở một stream mới; stream cũ có thể đã kết thúc hoặc bị hủy tùy tình huống.

~~~text
Một logical RPC: GetOrder(order-42)
    |
    +-- Attempt 1: stream 17 trên connection A
    |      +-- upstream reset / UNAVAILABLE
    |
    +-- Attempt 2: stream 23 trên connection A hoặc B
           +-- grpc-status: 0

Caller nhận một kết quả cuối cùng cho logical RPC.
~~~

Đây là ví dụ retry nội bộ của gRPC runtime. Ứng dụng vẫn chỉ gọi stub một lần và nhận một kết quả cuối cùng. Tuy nhiên server hoặc proxy có thể quan sát nhiều attempt, tùy attempt đầu đã đi tới đâu và retry policy có cho phép thử lại hay không.

Cần phân biệt hai trường hợp:

- **gRPC retry nội bộ:** runtime thực hiện thêm attempt trong cùng logical call theo retry/service config và điều kiện commitment.
- **Application retry:** code ứng dụng gọi lại phương thức stub sau khi nhận lỗi. Đây là một logical RPC mới, có thể có deadline và trace riêng.

Không phải mọi lỗi đều được retry. Khi response headers đã được nhận hoặc call đã được commit theo quy tắc retry của runtime, một số retry không còn được thực hiện. Với streaming đã trao đổi message, không được giả định runtime có thể phát lại toàn bộ luồng như một unary request mới.

## 4. Một HTTP/2 stream chứa những gì?

Native gRPC thường dùng HTTP/2 POST. Một attempt có request headers, request message data và phần kết thúc response:

~~~text
Client -> Server
  HEADERS
    :method: POST
    :scheme: https
    :authority: orders.example.com
    :path: /demo.orders.v1.OrderService/GetOrder
    content-type: application/grpc
    te: trailers
    grpc-timeout: 800m

  DATA
    [compressed flag][4-byte message length][protobuf request]

Server -> Client
  HEADERS
    :status: 200
    content-type: application/grpc

  DATA
    [compressed flag][4-byte message length][protobuf response]

  HEADERS (trailers, END_STREAM)
    grpc-status: 0
~~~

Một số điểm quan trọng:

- **HEADERS** chứa HTTP/2 pseudo-header và gRPC metadata. HTTP/2 dùng HPACK để nén header block.
- **DATA** mang byte stream của gRPC message; mỗi message có prefix 5 byte: một byte cờ nén và bốn byte độ dài message.
- **Trailers** thường chứa grpc-status và metadata kết thúc RPC.
- HTTP status 200 không tự chứng minh logical RPC thành công; phải đọc grpc-status.
- Một RPC lỗi sớm có thể trả **trailers-only**, tức block HEADERS cuối chứa status mà không có response DATA.

### 4.1. Frame không đồng nghĩa message

Một gRPC message có prefix length và payload protobuf. HTTP/2 DATA frame chỉ là đơn vị vận chuyển bytes. Do đó:

- Một message có thể trải qua nhiều DATA frame nếu payload lớn hoặc transport phân mảnh dữ liệu.
- Một DATA frame có thể chứa bytes thuộc nhiều phần của message stream.
- Ranh giới DATA frame không nhất thiết trùng với ranh giới protobuf message.
- TCP segment, TLS record và IP packet cũng không bảo toàn ranh giới của gRPC message.

Ứng dụng nên giải mã theo gRPC framing và protobuf, không tự giả định một DATA frame là một message hoàn chỉnh. Packet capture ở tầng mạng cũng không phải bản ghi trực tiếp của logical RPC.

## 5. Streaming thay đổi số message, không đổi bản chất logical call

Bốn kiểu RPC trong Protocol Buffers mô tả số lượng message ở hai chiều:

| Kiểu RPC | Request messages | Response messages | Logical call |
| --- | --- | --- | --- |
| **Unary** | Một | Một | Một lần gọi method |
| **Server-streaming** | Một | Nhiều | Một lần gọi method, nhiều response |
| **Client-streaming** | Nhiều | Một | Một lần gọi method, nhiều request |
| **Bidirectional-streaming** | Nhiều | Nhiều | Một lần gọi method, hai chiều cùng tồn tại |

Ví dụ contract:

~~~proto
service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
  rpc WatchOrder(WatchOrderRequest) returns (stream OrderUpdate);
  rpc UploadEvents(stream OrderEvent) returns (UploadSummary);
  rpc SyncOrders(stream OrderCommand) returns (stream OrderUpdate);
}
~~~

Khi client gọi **WatchOrder** một lần, đó là một logical RPC. Server có thể gửi hàng nghìn OrderUpdate trên cùng stream đó. Số message không phải số logical RPC và cũng không phải số HTTP/2 stream.

Với bidirectional streaming, client và server có thể gửi message độc lập theo flow control trên cùng RPC stream. RPC chỉ kết thúc khi một phía đóng theo semantics và phía còn lại kết thúc, hoặc call bị lỗi/hủy. Một message nghiệp vụ mới không tạo stream mới.

## 6. Một TCP connection có thể chứa nhiều stream

HTTP/2 multiplexing cho phép nhiều stream cùng tồn tại trên một connection:

~~~text
TCP/TLS connection A
  HTTP/2 stream 1  -> GetOrder, attempt 1
  HTTP/2 stream 3  -> WatchOrder, attempt 1
  HTTP/2 stream 5  -> UploadEvents, attempt 1
  HTTP/2 stream 7  -> GetCustomer, attempt 1
  HTTP/2 stream 9  -> SearchOrders, attempt 1
~~~

Mỗi stream có ID riêng trong phạm vi connection. Stream ID không phải request ID nghiệp vụ, không phải ID toàn cục và không thể dùng để liên kết log qua nhiều connection như một correlation ID.

Một ManagedChannel có thể quản lý một hoặc nhiều Subchannel/connection tùy resolver và load-balancing policy. Nếu backend hoặc connection thay đổi, RPC mới có thể được gửi qua connection khác. Một stream đang chạy thường vẫn gắn với connection đã tạo nó; nó không tự chuyển sang connection khác giữa chừng.

HTTP/2 cũng có frame điều khiển ở cấp connection như **SETTINGS**, **PING**, **GOAWAY** và **WINDOW_UPDATE**. Các frame này không nhất thiết tương ứng với một logical RPC:

- SETTINGS thương lượng giới hạn và tính năng HTTP/2.
- PING hỗ trợ kiểm tra tình trạng connection theo policy.
- WINDOW_UPDATE điều khiển flow control.
- GOAWAY báo peer ngừng tạo stream mới trên connection.
- RST_STREAM kết thúc một stream cụ thể.

Do đó, packet capture có thể chứa dữ liệu của nhiều RPC đan xen cùng frame điều khiển của connection.


## 7. Deadline, cancellation và retry nhìn từ hai tầng

**Deadline** thuộc logical call: caller đặt một ngân sách tổng cho thao tác. Nếu runtime thực hiện nhiều attempt, thời gian retry/backoff cũng tiêu thụ ngân sách của logical call. Không nên hiểu mỗi attempt luôn có một deadline mới đầy đủ bằng deadline ban đầu.

**Cancellation** cũng được caller áp dụng lên logical call. Runtime hủy attempt đang hoạt động và cố gắng truyền tín hiệu hủy tới server. Nếu đã có nhiều công việc ở downstream hoặc thread tùy chỉnh, việc cleanup còn phụ thuộc ứng dụng truyền Context và hỗ trợ cancel đúng cách.

**Retry** tạo thêm attempt/network exchange cho cùng logical call khi policy cho phép. Điều đó có một hệ quả quan trọng: server có thể nhìn thấy nhiều lần xử lý gần giống nhau dù caller chỉ gọi stub một lần.

Ví dụ, một RPC ghi đơn hàng bị mất connection sau khi server commit nhưng trước khi client nhận trailers. Client có thể thấy lỗi transport hoặc deadline; nếu retry không an toàn, thao tác ghi có thể bị lặp. Dùng idempotency key hoặc cơ chế tra cứu kết quả cho các RPC có tác dụng phụ.

| Sự kiện | Tầng logical RPC | Tầng network |
| --- | --- | --- |
| Caller gọi stub | Bắt đầu một logical call | Chưa chắc đã có stream ngay lập tức |
| Channel đang CONNECTING | Call có thể chờ theo policy/deadline | Resolver và transport thiết lập kết nối |
| Retry nội bộ | Vẫn cùng logical call | Có attempt/HTTP2 stream mới |
| Application gọi lại sau lỗi | Logical call mới | Exchange mới |
| Caller hủy | Logical call kết thúc theo cancellation | Active stream bị hủy nếu đã được tạo |
| Deadline hết | Logical call hết ngân sách chờ | Runtime hủy/chấm dứt attempt đang hoạt động |
| Một stream nhận nhiều message | Vẫn một logical call | Nhiều DATA bytes/message trên cùng stream |

## 8. Vì sao server logs có thể đếm nhiều lần hơn client?

Một client interceptor thường đếm logical call ở lúc ứng dụng gọi stub và ghi kết quả ở callback cuối. Server interceptor ghi nhận mỗi lần một request attempt tới server. Hai con số có thể khác nhau vì:

- Một logical call có thể có nhiều attempt do retry.
- Một attempt có thể thất bại trước khi đến server, nên server không ghi nhận.
- Client có thể hủy hoặc hết deadline khi request đang trên đường truyền.
- Gateway có thể retry upstream, tạo thêm một exchange backend.
- Một RPC streaming tạo nhiều message nhưng vẫn chỉ là một logical call.

Ví dụ:

~~~text
Client metrics:
  GetOrder logical calls = 100

Server metrics:
  GetOrder requests observed = 108

Possible explanation:
  6 calls có một retry tới server
  2 calls có attempt đầu thất bại trước server nhưng attempt sau tới server
~~~

Các con số trên chỉ minh họa. Muốn giải thích chênh lệch thực tế, cần trace/correlation ID và metrics riêng cho attempt; không suy luận số retry chỉ bằng phép trừ hai bộ đếm.

## 9. Thiết kế observability theo đúng đơn vị

Nên tách ba nhóm telemetry:

| Nhóm đo | Ví dụ | Dùng để trả lời |
| --- | --- | --- |
| **Logical RPC metrics** | Calls, final status, end-to-end latency theo method | Caller có gọi thành công và đúng hạn không? |
| **Attempt/stream metrics** | Attempt count, retry reason, stream duration, reset | Runtime/gateway đã phải thử bao nhiêu lần? |
| **Connection metrics** | Active connections, reconnect, TLS handshake, GOAWAY | Transport và topology có ổn định không? |

Một trace có thể mô hình hóa một span logical RPC, bên dưới là các span/event cho attempt hoặc downstream call. Ghi full method name, status, duration và attempt number khi có instrumentation hỗ trợ.

Không dùng HTTP/2 stream ID, request ID hoặc user ID làm metric label có cardinality cao. Stream ID chỉ có ý nghĩa trên một connection; request ID phù hợp hơn để liên kết logs/traces nhưng không nên làm nhãn metric. Hãy redact authorization metadata và payload nhạy cảm.

## 10. Chẩn đoán theo triệu chứng

| Triệu chứng | Cách phân tích |
| --- | --- |
| Client đếm một call, server đếm hai request | Kiểm tra retry policy, proxy retry và attempt trace |
| Một RPC streaming gửi hàng nghìn message | Đếm logical call và message riêng; không coi mỗi message là RPC |
| Một connection có nhiều RPC đồng thời | Xem HTTP/2 stream multiplexing; không kết luận connection bị dùng sai |
| Packet capture cho thấy nhiều DATA frame | Kiểm tra gRPC framing; frame không tương ứng một message cố định |
| Client thấy DEADLINE_EXCEEDED, server ghi đã commit | So sánh thời điểm commit, response/trailers và deadline |
| Server không có log dù client gọi stub | Call có thể chờ resolver, lỗi kết nối trước server hoặc bị hủy trước khi tới backend |
| Server thấy CANCELLED nhưng client báo DEADLINE_EXCEEDED | Đối chiếu nguồn cancellation, deadline và thời điểm mỗi phía nhận tín hiệu |
| Retry làm thao tác ghi bị lặp | Kiểm tra idempotency và việc retry ở client hay gateway |
| Stream đang chạy bị mất khi connection reset | Một attempt/stream đã kết thúc; ứng dụng cần mở logical call mới và resume nếu contract hỗ trợ |

Khi điều tra, lần theo thứ tự: **application invocation → ClientCall → attempt → HTTP/2 stream → connection → gateway/upstream → server handler**. Xác định điểm đầu tiên không còn quan sát thấy call giúp thu hẹp lỗi vào đúng tầng.

## 11. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo service có một unary method GetOrder và một server-streaming method WatchOrder.
2. Gọi GetOrder bằng blocking stub, ghi một metric logical call ở client và một metric request ở server.
3. Gọi WatchOrder và gửi nhiều OrderUpdate; xác minh message count tăng nhưng logical call count chỉ tăng một.
4. Cấu hình retry cho một method đọc an toàn trong môi trường test; quan sát attempt count và số HTTP/2 stream mà server nhìn thấy.
5. Mô phỏng lỗi connection trước khi nhận trailers; so sánh status cuối client với logs server.
6. Dùng packet capture hoặc proxy access log để quan sát HEADERS, DATA, trailers và connection multiplexing; không giả định frame/packet là message.
7. Thêm correlation ID/trace context để liên kết client, gateway và server; phân biệt logical call ID với attempt/stream ID.
8. Với RPC ghi, thử retry sau timeout và triển khai idempotency key để ngăn tác dụng phụ lặp.

### Câu hỏi tự kiểm tra

**1. Logical RPC có phải một HTTP/2 stream không?**  
Không hoàn toàn. Một attempt thường dùng một HTTP/2 stream; một logical RPC có thể có nhiều attempt nếu retry được thực hiện.

**2. Một HTTP/2 connection có thể mang nhiều logical RPC không?**  
Có. HTTP/2 multiplex nhiều stream trên một connection.

**3. Một streaming RPC có tạo một logical RPC cho mỗi message không?**  
Không. Các message thuộc cùng một logical call và thường đi qua cùng stream của attempt đó.

**4. Một DATA frame có luôn chứa đúng một protobuf message không?**  
Không. DATA frame mang byte stream; ranh giới frame không nhất thiết trùng ranh giới gRPC message.

**5. Client retry nội bộ và application retry khác nhau thế nào?**  
Retry nội bộ có thể tạo attempt mới trong cùng logical call. Ứng dụng gọi lại stub sau lỗi tạo logical call mới.

**6. Vì sao server có thể ghi nhận nhiều request hơn số call client báo?**  
Do retry nội bộ hoặc proxy retry; cũng cần tính đến attempt không tới được server và các lỗi trước khi handler chạy.

**7. Stream ID có thể dùng làm correlation ID xuyên service không?**  
Không. Nó chỉ có phạm vi trong một HTTP/2 connection. Dùng request/trace ID ở tầng ứng dụng để liên kết các hop.

**8. Deadline có được cấp lại đầy đủ cho mỗi retry attempt không?**  
Không nên giả định như vậy. Deadline giới hạn logical call tổng thể; backoff và các attempt tiêu thụ ngân sách còn lại.

## Tổng kết

**Logical RPC** là thao tác từ xa mà ứng dụng yêu cầu qua generated stub; **network exchange** là cách runtime vận chuyển thao tác đó qua attempt, HTTP/2 stream, frame và connection. Một attempt thường tương ứng một stream, nhưng retry có thể tạo nhiều stream cho cùng logical call; một stream có thể mang nhiều message và nhiều DATA frame. TCP connection lại multiplex nhiều stream, còn TLS record và IP packet không giữ ranh giới của RPC/message. Khi phát triển và vận hành Spring gRPC, cần đo riêng logical calls, attempts, streams và connections, phối hợp deadline/cancellation/retry, đồng thời dùng correlation ID để truy vết xuyên các tầng.



