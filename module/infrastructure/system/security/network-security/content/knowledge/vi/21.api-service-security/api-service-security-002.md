# Bảo vệ gRPC và HTTP/2 trên mạng

Một hệ thống microservices có thể chuyển từ REST/HTTP/1.1 sang gRPC để giảm chi phí tuần tự hóa, hỗ trợ streaming và tận dụng nhiều luồng đồng thời trên một kết nối HTTP/2. Nhưng đổi giao thức không tự làm API an toàn hơn: kẻ tấn công vẫn có thể dùng thông tin xác thực bị lộ, gọi phương thức vượt quyền, gửi thông điệp quá lớn, giữ stream quá lâu hoặc khai thác những khác biệt giữa gateway và backend. Đặc biệt, **một kết nối TLS đã xác thực không đồng nghĩa mọi RPC trong kết nối đó đều được phép**.

**Bảo vệ gRPC và HTTP/2 trên mạng** là thiết kế, triển khai và kiểm chứng đồng thời nhiều lớp: **mã hóa kết nối, xác thực peer và caller, phân quyền theo RPC và đối tượng dữ liệu, giới hạn tiêu thụ tài nguyên, kiểm soát kết nối/stream, cấu hình proxy/gateway, phân đoạn mạng và khả năng quan sát**. Cần hiểu cả đặc trưng HTTP/2 (frame, stream, flow control, header compression) lẫn hành vi gRPC (service/method, Protocol Buffers, metadata, status, deadline và streaming).

Trong mô-đun **SECURITY_NETWORK_SECURITY**, chủ đề này nối bảo vệ API với TLS, VPN, firewall, WAF, IDS/IPS, NAC, cloud networking và mô hình hóa mối đe dọa. Bài học hướng đến **phòng thủ và vận hành có kiểm chứng**. Mọi lệnh, tên miền, địa chỉ và sơ đồ chính sách là ví dụ học tập; chỉ thử kết nối hoặc kiểm tra API thuộc phạm vi được cấp quyền.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **HTTP/2** là giao thức truyền tải HTTP có multiplexing với **gRPC** là mô hình RPC thường dùng HTTP/2 và Protocol Buffers.
2. Giải thích **connection, stream, frame, pseudo-header, HPACK, flow control, SETTINGS, RST_STREAM và GOAWAY** dưới góc nhìn an ninh.
3. Mô tả cấu trúc một RPC gRPC gồm **service/method, metadata, message framing, trailers và gRPC status**.
4. Thiết kế **TLS/ALPN, mTLS, service identity, JWT/OAuth và authorization theo phương thức/tài nguyên** với ranh giới tin cậy rõ ràng.
5. Nhận diện rủi ro **stream/resource exhaustion, header abuse, request translation ambiguity, retry storm, thông điệp quá lớn và streaming thiếu giới hạn**.
6. Áp dụng các biện pháp **quotas, rate limits, concurrency caps, deadlines, message size, backpressure, circuit breaker và retry budgets** theo từng lớp.
7. Kiểm soát **gateway, WAF, ingress, service mesh, cloud load balancer, HTTP/2↔HTTP/1.1 và gRPC-Web** mà không mất danh tính caller.
8. Thiết lập **logging, tracing, metrics, health checks, kiểm thử hồi quy và incident runbook** cho cả truy cập được phép và truy cập bị từ chối.

## 2. HTTP/2 và gRPC: quan hệ nhưng không đồng nhất

**HTTP/2** định nghĩa cách biểu diễn và vận chuyển các thông điệp HTTP, bao gồm multiplexing các stream trên một kết nối và nén header bằng HPACK. **gRPC** định nghĩa quy ước gọi hàm từ xa với service, method, request/response, metadata, deadline và status; triển khai gRPC thông dụng truyền các RPC qua HTTP/2, thường với message định dạng Protocol Buffers.

| Lớp | Khái niệm chính | Câu hỏi bảo mật |
|---|---|---|
| **IP/routing** | Subnet, VRF, route, firewall | Gói có đi qua đúng trust boundary không? |
| **Transport** | TCP, hoặc QUIC trong các kiến trúc khác | Kết nối có bị giới hạn và giám sát không? |
| **TLS** | Xác thực máy chủ/peer, mã hóa, ALPN | Đúng đối tác và đúng điểm kết thúc TLS không? |
| **HTTP/2** | Stream, frames, headers, HPACK, flow control | Có thể dùng quá nhiều stream/header/tài nguyên không? |
| **gRPC** | Service/method, protobuf, metadata, status, deadlines | Caller có quyền gọi method và đối tượng nào? |
| **Application** | Dữ liệu, giao dịch, tenant, nghiệp vụ | Có thể đọc/sửa tài nguyên ngoài quyền không? |

~~~text
      Caller / client
             |
             v
      gRPC stub / SDK
             |
        gRPC semantics
             |
      HTTP/2 streams/frames
             |
         TLS over TCP
             |
       Network / firewall
             |
      TLS termination/proxy
             |
      gRPC service + policy
~~~

**Không phải mọi HTTP/2 request đều là gRPC.** HTTP/2 có thể vận chuyển website, JSON API và nhiều kiểu request HTTP khác. Ngược lại, các biến thể như **gRPC-Web** có thể dựa vào cơ chế truyền tải thích hợp với browser/proxy, vì vậy phải kiểm tra khả năng hỗ trợ thực của từng thành phần.

## 3. Những thành phần HTTP/2 cần hiểu để bảo vệ mạng

HTTP/2 duy trì một kết nối nhưng cho phép nhiều **stream** độc lập được ghép xen kẽ, mỗi stream mang các frame của một luồng HTTP. Điều này cải thiện hiệu quả nhưng tạo thêm những giới hạn cần áp dụng theo **kết nối, stream, request và caller**.

### 3.1. Connection, stream và frame

| Thành phần | Mô tả | Ý nghĩa an ninh |
|---|---|---|
| **Connection** | Một kênh vận chuyển hai phía, thường TCP/TLS | Giới hạn số kết nối, timeout, authentication tại transport |
| **Stream** | Một luồng request/response HTTP/2 trong connection | Áp concurrency, deadline, reset/cancel và resource budget |
| **Frame** | Đơn vị đóng gói thông tin HTTP/2 | Parser phải xác minh kích thước, sequence và state |
| **Header block** | Header HTTP được mã hóa bằng HPACK | Giới hạn header size/count, bảo vệ tài nguyên giải nén |
| **Data flow** | Nội dung trao đổi trong DATA frames | Giới hạn message size, flow-control và backpressure |

HTTP/2 frame có **header cố định 9 octet** cộng phần payload có độ dài tùy frame và thiết lập hợp lệ. Không nên tự viết parser tùy tiện bằng cách đọc frame như văn bản; phải dùng HTTP/2 stack được bảo trì, tuân thủ trạng thái stream và giới hạn của giao thức.

### 3.2. Các loại frame thường gặp

| Frame | Vai trò khái quát | Dấu hiệu cần giám sát |
|---|---|---|
| **HEADERS / CONTINUATION** | Chuyển header block | Header count/size, chuỗi frame bất thường, header validation |
| **DATA** | Chuyển dữ liệu ứng dụng | Bytes, memory buffer, decompressed message size |
| **SETTINGS** | Trao đổi thông số kết nối | Đột biến cấu hình, giới hạn concurrency/header/frame |
| **WINDOW_UPDATE** | Cập nhật credit flow-control | Flow-control deadlock, bất thường throughput/backpressure |
| **RST_STREAM** | Hủy hoặc reset stream | Tỷ lệ reset/cancel bất thường, resource cleanup |
| **GOAWAY** | Báo ngừng nhận stream mới và hỗ trợ graceful shutdown | Kết nối bị đóng, drain khi deploy/failover |
| **PING** | Kiểm tra/duy trì phản hồi kết nối | Tần suất bất thường, chi phí xử lý |
| **PRIORITY** | Cơ chế ưu tiên theo đặc tả/triển khai tương ứng | Khác biệt khả năng hỗ trợ, không suy chính sách an ninh |

Không phải mọi frame đều mang request nghiệp vụ. Đặc biệt, **đếm số TCP connection** không phản ánh chính xác số RPC đang chạy vì một connection có thể multiplex nhiều stream.

### 3.3. Pseudo-header và quy tắc HTTP

HTTP/2 sử dụng một số pseudo-header có dấu hai chấm, ví dụ:

~~~text
:method: POST
:scheme: https
:authority: api.internal.example.test
:path: /inventory.v1.InventoryService/GetItem
content-type: application/grpc
~~~

Pseudo-header có quy tắc thứ tự, tính hợp lệ và tập được phép theo loại thông điệp. Ứng dụng/gateway phải dựa vào thư viện HTTP/2 đã kiểm chứng và **chuẩn hóa request trước khi áp policy**, không để những cách diễn giải khác nhau ở proxy/backend tạo đường vượt kiểm soát.

**:authority không phải chứng minh danh tính người gọi.** Nó liên quan host/authority đích của request. Quyền gọi RPC phải đến từ xác thực caller và authorization riêng.

## 4. HPACK: nén header không phải mã hóa

**HPACK** giảm lượng byte lặp bằng cách biểu diễn header qua bảng tĩnh, bảng động và mã hóa giá trị phù hợp. Nó **không cung cấp bảo mật hay bí mật dữ liệu**: nếu không có TLS bảo vệ đoạn kết nối, HPACK không ngăn người có khả năng quan sát mạng đọc thông tin sau giải mã.

Những rủi ro cần đánh giá:

1. **Header list quá lớn** gây tốn bộ nhớ, CPU hoặc vượt giới hạn proxy/backend.
2. **Nén/giải nén không đồng nhất** khiến hệ thống áp giới hạn trên byte đã nén nhưng backend lại phải xử lý dữ liệu đã giải nén lớn hơn.
3. Metadata chứa **Authorization, cookie, token, tenant ID** có thể bị log hoặc truyền qua điểm kết thúc TLS không mong muốn.
4. **Thay đổi dynamic table** và trạng thái decoder làm bộ xử lý header chịu thêm tải.
5. Nếu các lớp tự xử lý HTTP/2 không đúng chuẩn, có thể xuất hiện tình trạng parser/state không nhất quán.

Một số cơ chế header encoding có lựa chọn **không lập chỉ mục các giá trị nhạy cảm**, nhưng đây không phải lý do để coi token đã an toàn khỏi log, memory dump hoặc hop không mã hóa.

### Thực hành phòng thủ

- Giới hạn **header count, header list size và metadata size** ở điểm ingress cũng như backend, theo khả năng framework.
- Không ghi raw Authorization, Cookie hoặc metadata bí mật vào access log, span, tracing baggage.
- Tránh dùng user input tùy ý làm tên header/metadata, và kiểm tra giá trị theo schema.
- Giám sát header parse errors, 431/400, gRPC error mapping và số request bị giới hạn.
- Cập nhật HTTP/2 libraries/proxies theo bản vá bảo mật và kiểm thử tương thích.

## 5. Flow control, concurrency và khả năng cạn tài nguyên

HTTP/2 có **flow control ở mức stream và connection** cho **DATA frames**, giúp phía nhận điều tiết tốc độ dữ liệu. Nhưng flow control **không tự giải quyết toàn bộ DoS**: header processing, tạo stream, application CPU, goroutine/thread, database connection, heap và log có thể bị tiêu thụ trước hoặc ngoài phạm vi flow-control.

~~~text
Một HTTP/2 connection
           |
     +-----+-----+---------+
     |           |         |
   Stream 1    Stream 3   Stream 5   ... nhiều stream
     |           |         |
   RPC A       RPC B     RPC C
     |           |         |
   CPU/DB      Cache     Streaming buffers
~~~

### Các giới hạn bổ trợ

| Giới hạn | Ngăn điều gì? | Chú ý vận hành |
|---|---|---|
| **Connections/IP hoặc principal** | Quá nhiều kết nối đồng thời | IP dùng chung NAT/proxy, phải xét danh tính |
| **Concurrent streams/connection** | Một peer tạo quá nhiều RPC cùng lúc | Giới hạn h2 có thể khác với concurrency ở worker pool |
| **Concurrent RPC/principal** | Một user/service chiếm quá nhiều backend slots | Cần identity sau authentication |
| **Max header list/metadata** | Cạn tài nguyên parse headers | Tính cả dữ liệu sau giải nén |
| **Max request/response message** | Payload/gRPC message quá lớn | Xét kích thước sau giải nén và giới hạn application |
| **Memory and queue budgets** | Buffer/queue tăng vô hạn | Có backpressure và rejection rõ ràng |
| **Request deadline/idle timeout** | RPC tồn tại quá lâu | Ngoại lệ có kiểm soát cho streaming dài hạn |
| **Rate/byte quotas** | Chiếm băng thông hoặc API quota | Theo caller, method và cost, không chỉ TCP |

**Không có ngưỡng toàn cầu phù hợp cho mọi dịch vụ.** Một RPC unary đọc metadata có mô hình tải khác streaming telemetry hoặc upload file. Giới hạn phải dựa trên benchmark, tải đồng thời, latency SLO và khả năng backend; kiểm thử ở staging trước khi bật chặn.

## 6. gRPC message trên HTTP/2 được biểu diễn thế nào?

Một RPC gRPC thường sử dụng **HTTP POST**, đường dẫn thể hiện **service/method**, content-type thuộc họ **application/grpc**, cùng metadata và trailers. Dữ liệu mỗi thông điệp gRPC có một lớp **message framing** riêng; khi dùng Protocol Buffers, payload là dữ liệu nhị phân theo schema.

~~~text
HTTP/2 request stream
  HEADERS:
    :method = POST
    :path = /inventory.v1.InventoryService/GetItem
    content-type = application/grpc
    authorization = [sensitive, redacted]

  DATA:
    gRPC message framing + serialized request

HTTP/2 response stream
  HEADERS:
    :status = 200
    content-type = application/grpc

  DATA:
    gRPC message framing + serialized response

  TRAILERS:
    grpc-status = 0
~~~

Trong gRPC over HTTP/2 chuẩn, một thông điệp data thường được **prefix 5 byte** gồm cờ compression và độ dài message, rồi đến message body. **Không nên tự parse bytes bằng cách tách chuỗi theo ký tự**; dùng thư viện gRPC/Protobuf được bảo trì.

### Status của HTTP khác status của gRPC

| Thông tin | Ý nghĩa |
|---|---|
| **HTTP :status** | Trạng thái tầng HTTP; ví dụ 200 có thể đi cùng kết quả RPC lỗi |
| **grpc-status** | Mã kết quả ở tầng gRPC, thường nằm trong trailers |
| **grpc-message** | Mô tả lỗi nếu có; không nên chứa secret/stack trace |
| **grpc-status-details-bin** | Chi tiết lỗi nhị phân theo triển khai phù hợp | 

**HTTP 200 không tự chứng minh RPC thành công.** Cần quan sát **grpc-status**, request outcome và logic ứng dụng. Nếu một proxy trả lỗi HTTP trước khi gRPC headers/trailers hoàn tất, client có thể phải ánh xạ lỗi transport theo quy tắc thư viện; đừng giả định mọi lỗi đều có grpc-status.

## 7. Bốn kiểu RPC và tác động tới an ninh

| Kiểu RPC | Luồng message | Điểm cần bảo vệ |
|---|---|---|
| **Unary** | Một request → một response | Object-level authorization, timeout, request size |
| **Server streaming** | Một request → nhiều response | Số lượng/bytes trả, quota và kết thúc stream |
| **Client streaming** | Nhiều request → một response | Tổng dữ liệu nhận, tốc độ, per-message validation |
| **Bidirectional streaming** | Hai phía trao đổi message trên một stream | Kiểm soát mỗi message, trạng thái phiên, backpressure, idle timeout |

Ví dụ một service định nghĩa trong Protocol Buffers:

~~~proto
syntax = "proto3";

package inventory.v1;

service InventoryService {
  rpc GetItem(GetItemRequest) returns (GetItemResponse);
  rpc WatchItems(WatchItemsRequest) returns (stream ItemEvent);
  rpc UploadChanges(stream ItemChange) returns (UploadSummary);
  rpc Sync(stream SyncMessage) returns (stream SyncMessage);
}

message GetItemRequest {
  string item_id = 1;
}

message GetItemResponse {
  string item_id = 1;
  string tenant_id = 2;
  string display_name = 3;
}

message WatchItemsRequest {
  string tenant_id = 1;
}

message ItemEvent {
  string item_id = 1;
  string event_type = 2;
}

message ItemChange {
  string item_id = 1;
  string new_value = 2;
}

message UploadSummary {
  uint32 accepted_count = 1;
}

message SyncMessage {
  string correlation_id = 1;
  bytes payload = 2;
}
~~~

Đây là **schema học thuật**, không kèm code server hay cơ chế auth. Sự hiện diện của trường **tenant_id** do client gửi **không làm nó trở thành tenant identity đáng tin**; server phải kiểm tra caller có quyền với tenant/object tương ứng.

### Điểm dễ bỏ sót trong streaming

- Chỉ xác thực khi mở stream nhưng không kiểm tra quyền đối với từng object/message.
- Không áp **tổng byte limit** vì từng message vẫn dưới giới hạn.
- Client hủy stream nhưng server tiếp tục chạy tác vụ tốn tài nguyên.
- Mở stream rồi gửi rất chậm hoặc không gửi dữ liệu mà không bị idle/deadline policy.
- Tự động retry một stream ghi dữ liệu mà không có semantics chống trùng.
- Log toàn bộ các message, vô tình lưu PII/token hoặc bùng nổ storage.

## 8. TLS, ALPN và h2c: biết chính xác đoạn nào được mã hóa

Đối với dịch vụ gRPC qua TLS, client/server thường dùng **ALPN** để thương lượng **h2**. Không nên dựa vào việc port là 443 để suy ra mọi kết nối đều đang dùng HTTP/2; có thể xảy ra HTTP/1.1 fallback hoặc một proxy terminate và chuyển giao thức.

~~~text
          [gRPC Client]
                |
        TLS + ALPN "h2"
                |
         [Edge Gateway]
              /   \
       TLS/h2       cleartext h2c (nếu cấu hình)
          |            |
    [Service A]     [Service B]
~~~

### Phân biệt các phương thức

| Kết nối | Cơ chế | Đánh giá bảo mật |
|---|---|---|
| **HTTP/2 over TLS** | TCP/TLS, ALPN h2 khi phù hợp | Có mã hóa và xác thực server nếu validation đúng |
| **h2c** | HTTP/2 cleartext | Không tự có mã hóa/xác thực TLS; chỉ cân nhắc trong trust boundary được quản lý cùng lớp bảo vệ khác |
| **mTLS + HTTP/2** | TLS xác thực cả server/client theo chính sách | Cần ánh xạ identity tới quyền RPC |
| **HTTP/2 qua proxy có TLS termination** | Có các TLS hop tách biệt | Phải xác minh các đoạn sau điểm termination |

**Không mặc nhiên bật h2c cho mạng internal chỉ vì nó là mạng riêng.** Cloud VPC, Kubernetes cluster và mạng doanh nghiệp vẫn có workload bị xâm nhập hoặc đường truyền đi qua ranh giới khác. Nếu sử dụng cleartext trong một môi trường đã cô lập theo kiến trúc, phải có threat model, policy và bằng chứng bảo vệ bù trừ.

### ALPN và yêu cầu tương thích

Một số gateway nhận HTTPS/HTTP/2 từ client rồi gọi backend bằng HTTP/1.1. Điều đó không sai trong mọi ứng dụng, nhưng **không bảo toàn native gRPC streaming/trailers tự động**. Cần xác minh sản phẩm có hỗ trợ **gRPC end-to-end, gRPC-Web translation hoặc HTTP/2 upstream** theo đúng yêu cầu.

## 9. mTLS xác thực workload nhưng không thay authorization

**Mutual TLS** có thể xác minh danh tính client certificate và server certificate trên một TLS connection. Trong service mesh, danh tính thường liên quan workload/service account hoặc trust domain, tùy PKI/SPIFFE và mô hình triển khai.

~~~text
       Workload A
       identity A
            |
           mTLS
            |
        [Service B]
         identity B
            |
   Verify caller identity
            |
   Apply method + resource policy
            |
       Business logic
~~~

### Những câu hỏi bắt buộc

1. Certificate **được cấp bởi CA nào**, có mục đích và SAN/identity phù hợp không?
2. Workload A có thực sự là service được phép gọi method này không?
3. Nếu A là gateway đại diện người dùng, **end-user identity** được chuyển tiếp thế nào và có được xác thực lại không?
4. Certificate/client identity có thể bị thu hồi, đổi workload hoặc hết hạn không?
5. Caller được phép với **mọi resource/tenant** hay chỉ một tập được chỉ định?
6. Sidecar hoặc proxy có thể bị đi vòng qua bằng đường trực tiếp tới ứng dụng không?

**mTLS chỉ xác thực một thực thể trên kết nối**, không tự chứng minh user cuối cùng là ai. Không dùng SAN của gateway làm lý do cấp quyền admin cho mọi RPC được gateway chuyển tiếp.

### Chính sách phân quyền nhiều lớp

| Lớp | Kiểm soát | Ví dụ |
|---|---|---|
| **Network/mesh** | Chỉ service identity A được kết nối B | Chặn workload ngoài trust domain |
| **Method authorization** | A có quyền GetItem nhưng không có quyền DeleteItem | Service-level ACL |
| **Resource/tenant authorization** | Người gọi chỉ đọc item của tenant mình | Kiểm tra owner trong database |
| **Data validation** | Item ID, payload, bytes nằm trong giới hạn | Không tin mọi field của protobuf |
| **Auditing** | Ghi principal, method, resource và kết quả đã che dữ liệu | Điều tra lạm dụng có căn cứ |

## 10. Xác thực người dùng: JWT, OAuth và API tokens

Trong một hệ thống gRPC, client có thể gửi **access token trong request metadata** (ví dụ Authorization) để server hoặc gateway xác minh. Phải **tách việc truyền token với việc xác minh và cấp quyền**.

### Kiểm tra token phù hợp

- **Signature/issuer/trust:** token thực sự do authority được chấp thuận phát hành.
- **Audience:** token dành cho API/service này, không phải token dùng cho ứng dụng khác.
- **Expiration/not-before:** thời gian còn phù hợp, có xử lý clock skew được quy định.
- **Scopes/roles:** đúng hành động/method, không suy chỉ từ việc token hợp lệ.
- **Subject/tenant:** định danh nguồn đủ tin cậy để đối chiếu resource được yêu cầu.
- **Revocation/session policy:** kiểm tra theo yêu cầu hệ thống; JWT tự chứa có hạn chế khi cần thu hồi ngay.
- **Token binding/sender constraint nếu áp dụng:** có cần gắn token với client/mTLS hoặc bằng chứng khác không?

**Không chấp nhận token chỉ bằng cách giải mã payload mà không kiểm tra chữ ký và policy.** Không ghi nguyên token trong access logs, tracing metadata hoặc exception.

### Metadata và danh tính bị chuyển tiếp

~~~text
Browser / Mobile / Service
          |
       API Gateway
    validate token + rate limit
          |
     internal identity context
          |
       gRPC backend
    authorize method/resource
          |
      tenant data store
~~~

Nếu gateway chuyển danh tính bằng header nội bộ, backend chỉ nên tin header đó từ **điểm tin cậy đã xác thực**, và gateway phải xóa/ghi đè header do client bên ngoài tự cung cấp. Thiết kế vững chắc có thể dùng token được ký/giới hạn audience hoặc xác thực trực tiếp ở backend, tùy trust model.

## 11. Phân quyền theo RPC method và object

Một hệ thống có thể bảo vệ cổng API bằng JWT/mTLS nhưng vẫn mắc lỗi **Broken Object Level Authorization (BOLA)**: caller thay đổi item_id để truy cập dữ liệu của tenant khác. Đối với gRPC, tên method và protobuf schema **không tự xác nhận** quyền dữ liệu.

### Tình huống ví dụ

~~~text
Caller: tenant A
Method: /inventory.v1.InventoryService/GetItem
Request item_id: item-b-123

Network connection: mTLS OK
Access token: valid for tenant A
Item owner in database: tenant B

Expected application result: PERMISSION_DENIED
~~~

### Cách thiết kế authorization

1. Dùng identity **được xác minh**, không tin tenant_id do caller khai báo.
2. Gắn policy với **service/method**, sau đó kiểm tra resource thật ở tầng nghiệp vụ.
3. Ràng buộc quyền trên **mỗi message** khi stream cho phép đổi đối tượng hoặc hành động.
4. Ưu tiên **deny-by-default** với method mới và role/tenant mới.
5. Kiểm tra các trường hợp **list/search/export** có thể lộ nhiều object hơn GetItem.
6. Ghi kết quả từ chối và principal hợp lệ, **không tiết lộ object có tồn tại hay không** khi điều đó tạo rủi ro.

### Pseudocode của interceptor

~~~text
onIncomingRpc(call, context):
    principal = authenticateCaller(context.verifiedCredentials)
    if principal is absent:
        reject UNAUTHENTICATED

    if not allowedMethod(principal, call.fullMethodName):
        reject PERMISSION_DENIED

    applyRateAndConcurrencyBudget(principal, call.fullMethodName)
    validateRequestSizeAndSchema(call.request)

    for each requested or streamed resource:
        if not isAuthorized(principal, resource):
            reject PERMISSION_DENIED

    executeWithDeadlineAndAuditContext()
~~~

Đây chỉ là **mô hình chính sách**, không phải đoạn mã triển khai hoàn chỉnh: với stream, interceptor có thể cần wrapper cho từng message; nếu xử lý quota, authentication hoặc authorization bằng nhiều component khác nhau cần đảm bảo không có đường bypass.

## 12. Kiểm tra dữ liệu Protobuf và kích thước message

**Protocol Buffers** mô tả cấu trúc serialization nhưng không tự đảm bảo dữ liệu thỏa ràng buộc nghiệp vụ. Có trường string không có nghĩa nó tự hợp lệ về độ dài, ký tự, ý nghĩa hoặc quyền truy cập. Các phiên bản schema có thể cho phép **unknown fields/unknown enum values** theo hành vi của runtime.

Các kiểm soát cần có:

| Đối tượng | Ràng buộc cần xét |
|---|---|
| **String/bytes fields** | Độ dài, định dạng, mã hóa, giới hạn dữ liệu nhạy cảm |
| **Repeated fields** | Số lượng phần tử, tổng kích thước và chi phí xử lý |
| **Nested messages** | Độ sâu, số nút, parser recursion/memory |
| **Enum/numeric** | Giá trị nằm trong tập hỗ trợ, biên số và trạng thái unknown |
| **Optional/presence** | Phân biệt giá trị default với trường thật sự được đặt khi nghiệp vụ yêu cầu |
| **Resource IDs** | Ownership/authorization, không tin chỉ vì đúng kiểu chuỗi |
| **Timestamps/durations** | Range hợp lệ, timezone/clock, deadline và lưu trữ |
| **Compression** | Max decompressed size, tỷ lệ giải nén và CPU budget |

### Giới hạn kép: trên wire và sau giải nén

~~~text
Network receives compressed gRPC message
                 |
        Check framing / byte limit
                 |
        Decompress within budget
                 |
      Check decompressed size/CPU
                 |
        Parse / validate schema
                 |
       Authorize resource/action
                 |
           Business logic
~~~

Một message có **ít byte trên wire** vẫn có thể tiêu thụ bộ nhớ lớn khi giải nén. Không coi cài đặt max frame size của HTTP/2 tương đương **max gRPC message**, và cũng không coi max message bảo vệ được mọi tài nguyên backend (DB query, CPU, fan-out).

## 13. Deadline, cancellation và retry policy

Trong gRPC, **deadline** quy định thời điểm một lời gọi không còn nên chờ kết quả. Client có thể hủy stream; server phải cố gắng tôn trọng tín hiệu hủy và **giải phóng tài nguyên** theo ngữ nghĩa thư viện. Streaming dài hạn có thể cần heartbeat/idle timeout và lifecycle riêng.

### Deadline không giống timeout TCP

| Cơ chế | Ý nghĩa |
|---|---|
| **Connection timeout** | Giới hạn thời gian mở kết nối hoặc hoàn tất handshake |
| **Per-RPC deadline** | Giới hạn vòng đời của một lời gọi ứng dụng |
| **Idle timeout** | Giới hạn khoảng không hoạt động trên stream/kết nối theo mục đích |
| **Stream total duration** | Hạn chế stream tồn tại vô thời hạn nếu nghiệp vụ không cho phép |
| **Queue timeout** | Giới hạn thời gian request chờ slot |
| **Backoff/retry budget** | Hạn chế số lần thử lại và tổng tải do retry tạo ra |

### Retry storm và khuếch đại lỗi

Khi một backend chậm, nếu gateway, client SDK và service trung gian **đều tự retry**, một request từ người dùng có thể sinh nhiều request xuống database. Với thao tác ghi dữ liệu, retry cũng có thể gây **lặp giao dịch** nếu thiếu idempotency semantics.

~~~text
Client request
    |
  Gateway retries (theo policy)
    |
  Service A retries (theo policy)
    |
  Service B retries
    |
  Database overload

Nhiều tầng retry không phối hợp -> có thể tăng tải khi hệ thống đang lỗi.
~~~

Biện pháp:

- Đặt **deadline tổng thể** và truyền ngân sách thời gian còn lại qua các hop.
- Chỉ retry lỗi **thực sự có khả năng tạm thời** và phù hợp phương thức.
- Giới hạn **số lần retry, exponential backoff có jitter và retry budget**.
- Với thao tác ghi, dùng **idempotency key hoặc thiết kế giao dịch chống trùng** nếu nghiệp vụ cần.
- Khi client cancel hoặc deadline hết, dừng xử lý/DB query còn có thể dừng, tránh tiếp tục đốt tài nguyên.
- Đo **retry attempts và retry-amplification** bên cạnh request count.

**Deadline không phải công cụ xác thực**; một caller có thể đặt timeout dài nếu server không áp giới hạn. Phải có **server-side policy** để giữ SLO và bảo vệ tài nguyên.

## 14. Bảo vệ chống lạm dụng HTTP/2 ở tầng kết nối

Multiplexing giúp một connection phục vụ nhiều RPC, nhưng cũng có thể làm một client sử dụng tài nguyên lớn trong khi số lượng kết nối quan sát ở firewall vẫn thấp. Các kiểu lạm dụng cần nhận biết ở mức phòng thủ gồm:

- Tạo và hủy nhiều stream khiến proxy phải cấp phát/dọn tài nguyên liên tục.
- Gửi headers phức tạp, nhiều trường hoặc lớn hơn giới hạn hợp lý.
- Duy trì stream lâu, gửi dữ liệu nhỏ giọt làm tốn slot và buffer.
- Gây nhiều lần mở kết nối, thất bại handshake hoặc SETTINGS bất thường.
- Tận dụng sự khác biệt trong trạng thái HTTP/2 giữa edge, reverse proxy và backend.
- Tạo lượng RPC đồng thời vượt khả năng worker pool, DB connection hoặc phụ trợ.

### HTTP/2 Rapid Reset: bài học từ lỗ hổng đã công bố

**CVE-2023-44487 (HTTP/2 Rapid Reset)** là ví dụ lịch sử về khả năng tạo áp lực lên hạ tầng HTTP/2 thông qua việc mở và hủy stream với nhịp độ cao. Bài học quan trọng cho người phòng thủ không phải cách tạo mẫu traffic tấn công, mà là:

1. **Đếm concurrent streams đơn thuần có thể chưa đủ** để giới hạn tốc độ tạo/hủy stream.
2. Cần **vá phiên bản server/proxy/ingress** theo khuyến cáo của nhà cung cấp.
3. Giám sát **stream creation, RST_STREAM rate, CPU, queue, p95/p99 latency và 5xx** theo nguồn và dịch vụ.
4. Áp đặt **admission control/rate limit/resource budget** ở điểm xử lý có khả năng quan sát đúng, không chỉ L3 firewall.
5. Kiểm thử bản vá/giới hạn theo **khả năng ứng dụng hợp lệ**, không gây tải chủ động trên production ngoài phê duyệt.

**Không coi một RST_STREAM là độc hại.** Client có thể cancel khi người dùng chuyển trang, deadline hết hoặc network mất kết nối. Điều cần phát hiện là **mẫu bất thường và ảnh hưởng tài nguyên**, so với baseline cùng loại client/ứng dụng.

### Defense-in-depth cho HTTP/2

| Lớp | Biện pháp |
|---|---|
| **L3/L4** | Anti-DDoS phù hợp, số connections, firewall egress/ingress và theo dõi traffic |
| **TLS/edge** | TLS policy, connection timeout, client identity nếu dùng mTLS, cập nhật bản vá |
| **HTTP/2 proxy** | Header limits, stream/rate controls, frame validation, request queue budget |
| **gRPC framework** | Max message, deadline, metadata limits, authentication interceptors |
| **Application** | Authorization, per-tenant quotas, DB limits, backpressure và cancellation |
| **Monitoring** | Connection/RPC/stream metrics, alerting khi lệch baseline và synthetic tests |

Giới hạn phải áp **đúng nơi có thông tin cần thiết**. Firewall L3 thường không biết tên RPC bên trong TLS; gateway sau TLS termination mới có thể phân biệt method và principal.

## 15. HTTP/2↔HTTP/1.1 translation và nguy cơ diễn giải request khác nhau

Trong hệ thống cloud/hybrid, một request có thể đi qua các lớp hỗ trợ giao thức không giống nhau:

~~~text
Client --HTTP/2--> CDN/WAF
                         |
                         +--HTTP/1.1--> Legacy upstream
                         |
                         +--HTTP/2----> gRPC backend
~~~

Khi chuyển đổi giao thức, proxy phải **chuyển headers, body framing, authority, connection semantics và trailers** theo chuẩn. Nếu edge và backend diễn giải khác nhau **độ dài thông điệp hoặc ranh giới request**, có nguy cơ xuất hiện **request smuggling/desynchronization**.

### Những chỗ cần kiểm soát

- HTTP/2 **không sử dụng Transfer-Encoding: chunked** như HTTP/1.1 để đóng khung body. Proxy phải từ chối hoặc chuẩn hóa những tổ hợp header không hợp lệ theo chuẩn và chính sách.
- Không chuyển tiếp header hop-by-hop hoặc connection-specific theo cách làm sai HTTP/2.
- Đảm bảo các trường **:authority, Host khi chuyển đổi, Content-Length và payload** có cách diễn giải nhất quán, reject input mơ hồ.
- Áp cùng một logic normalize/reject giữa WAF, API gateway, reverse proxy và service.
- Kiểm thử các đường **HTTP/2→HTTP/1.1→HTTP/2**, failover và các ứng dụng legacy có trong phạm vi.
- Cập nhật proxy libraries, kiểm thử hồi quy sau khi đổi sản phẩm hoặc bật HTTP/2.

**Không dùng payload request smuggling thử trên hệ thống production không được cấp quyền.** Với bài này, tập trung vào kiểm kê đường chuyển đổi, cấu hình parser/validation và test vectors an toàn trên lab/staging.

### Sự khác nhau giữa HTTP/2 security và gRPC semantics

Một lỗi trong HTTP/2 parser hoặc protocol translation có thể ảnh hưởng **mọi ứng dụng dùng HTTP/2**, không riêng gRPC. Ngược lại, lỗi authorization theo item_id của gRPC có thể tồn tại dù proxy HTTP/2 hoàn toàn tuân thủ chuẩn.

## 16. Gateway, WAF và gRPC-Web: phạm vi nhìn thấy khác nhau

**API gateway** thường là nơi kết thúc TLS, xác thực caller, giới hạn rate và định tuyến tới backend. **WAF** có thể hỗ trợ kiểm tra request theo bộ quy tắc, nhưng mức hiểu **gRPC/Protobuf binary payload** rất khác nhau theo sản phẩm, phiên bản và cấu hình.

| Thành phần | Có thể làm tốt khi được hỗ trợ | Giới hạn cần xác minh |
|---|---|---|
| **L3/L4 firewall** | Kiểm soát nguồn/đích, port, flow, vùng mạng | Không biết method hoặc token bên trong TLS |
| **TLS-aware proxy** | Xác thực server/client TLS, SNI/ALPN, connection controls | Không tự hiểu quyền nghiệp vụ |
| **API gateway gRPC-aware** | Method routing, token verification, quotas, metadata filters | Phải hỗ trợ streaming/trailers chính xác |
| **WAF gRPC-aware** | Kiểm tra các trường có thể giải mã/parse theo khả năng sản phẩm | Không mặc định parse được mọi protobuf schema |
| **Service mesh** | mTLS workload identity, service policy, telemetry | Không thay object-level authorization |
| **Backend service** | Business validation, tenant checks, transaction controls | Phải có resource limits, không thể tin mọi upstream |

### gRPC-Web khác native gRPC

Browser truyền thống thường không cho ứng dụng JavaScript dùng tùy ý tất cả chi tiết HTTP/2 mà native gRPC cần. **gRPC-Web** dùng một giao thức/định dạng trung gian qua proxy/gateway để backend gRPC xử lý theo cách phù hợp.

~~~text
Browser
  |
  | gRPC-Web request (CORS, browser auth)
  v
gRPC-Web proxy / API Gateway
  |
  | Native gRPC over HTTP/2
  v
Backend gRPC server
~~~

Điểm cần kiểm thử:

1. **CORS policy** cho browser origins cần thiết; không dùng wildcard rộng khi có credential nếu không phù hợp.
2. Token/cookie/CSRF policy khi ứng dụng web dùng cookie hoặc session.
3. Translation **trailer/status/error** từ backend về client gRPC-Web.
4. Giới hạn message, metadata và timeout ở cả gateway và backend.
5. Xác minh gateway không biến request browser không tin cậy thành **internal superuser**.
6. Không tự suy rằng mọi kiểu **client/bidirectional streaming** được hỗ trợ như native gRPC; phụ thuộc thư viện và proxy.

### Reflection service và bề mặt khám phá

**gRPC Server Reflection** có thể giúp công cụ tìm service/method/schema mà không cần file proto cục bộ. Nó rất hữu ích cho phát triển và vận hành, nhưng có thể bộc lộ cấu trúc API nếu không được kiểm soát.

- Không mở reflection production cho mọi nguồn một cách mặc định.
- Nếu cần hỗ trợ vận hành, giới hạn identity/network và ghi audit.
- Không xem **tắt reflection** là thay thế authentication/authorization; tên method có thể được biết qua client/app.
- Có thể dùng **proto descriptors được quản lý** cho công cụ kiểm thử, thay vì phụ thuộc reflection public.

## 17. Thiết kế egress, service discovery và ranh giới mạng

Microservices thường không gọi nhau bằng IP cố định mà dùng DNS hoặc service discovery. Cùng một service name có thể trỏ tới nhiều pod/VM, region hoặc gateway. Vì vậy kiểm soát chỉ theo một IP đơn lẻ có thể không bền và không đủ.

~~~text
        [External client]
                |
           [API Gateway]
                |
     [Production security zone]
             /        \
    [Service A]      [Service B]
         |               |
       mTLS            mTLS
         |               |
   [Data access]    [Message broker]
         |
      [Database]
~~~

**Mạng có route đến một service không chứng minh caller có quyền gọi service đó.** Phân đoạn và authorization phải phối hợp:

- **Ingress:** chỉ cho các nguồn hợp lệ vào API gateway, không công bố backend gRPC trực tiếp khi không có yêu cầu.
- **East–west:** service A chỉ được kết nối tới những service cần thiết, có identity và policy.
- **Egress:** giới hạn kết nối ra ngoài cloud/Internet và API của đối tác.
- **DNS:** resolver và service discovery phải được kiểm soát; gRPC client kết nối tới đúng authority/service.
- **IPv4/IPv6:** kiểm thử dual-stack, vì rule IPv4 không tự áp dụng cho đường IPv6.
- **VPN/hybrid:** kiểm tra route, trust domain và TLS hop ở kết nối on-prem–cloud.
- **Network policy:** Kubernetes/CNI/SG/NACL hỗ trợ các lớp tương ứng nhưng không tự hiểu mọi RPC method.

### TLS termination và sidecar bypass

Nếu policy mTLS/rate limit đặt ở service mesh sidecar nhưng pod/application còn lắng nghe một **đường trực tiếp ngoài mesh**, attacker hoặc workload nội bộ khác có thể bỏ qua điểm kiểm soát dự kiến. Kiến trúc cần xác định đường traffic được phép, listener và policy tại host/network, không chỉ trạng thái mesh dashboard.

## 18. Cloud load balancer, ingress và connection draining

HTTP/2/gRPC thường giữ kết nối lâu hơn một số HTTP request truyền thống. Khi một node được deploy, autoscale hoặc lỗi, cần quản lý **connection draining và RPC lifecycle** để tránh gián đoạn bất ngờ.

### Những câu hỏi thiết kế

| Chủ đề | Cần xác minh |
|---|---|
| **TLS termination** | Client→LB, LB→backend có TLS/mTLS riêng không? |
| **HTTP/2 upstream** | LB có hỗ trợ gRPC native, trailers và stream cancellation không? |
| **Health** | Probe là TCP/TLS, HTTP hay gRPC health service? Nó có đúng tình trạng ứng dụng không? |
| **Drain/shutdown** | Node ngừng nhận stream mới, chờ RPC hợp lệ bao lâu trước khi thoát? |
| **Sticky/connection routing** | Long-lived connection có khiến một backend nhận quá nhiều RPC không? |
| **Per-connection limits** | Có quá nhiều stream trong một connection dù connection count thấp không? |
| **Retry/failover** | Có tránh gửi lại request thay đổi trạng thái không an toàn không? |
| **Regional failover** | CA/trust, DNS, service identity và quotas ở region dự phòng có tương đương? |

**GOAWAY** có thể giúp server báo ngừng nhận stream mới khi graceful shutdown theo quy tắc HTTP/2, nhưng không bảo đảm một request nghiệp vụ đã hoàn tất hoặc có thể retry an toàn. Cần ứng dụng/SDK theo dõi deadline, kết quả và idempotency khi phục hồi.

### Load balancing và multiplexing

Một HTTP/2 connection bám vào một upstream có thể vận chuyển nhiều RPC, làm phân bố tải theo **số kết nối** khác phân bố theo **số request**. Nếu bộ cân bằng tải chỉ nhìn connection count, một node có thể chịu quá nhiều stream. Giám sát phải có **in-flight RPCs, per-backend queue, CPU/memory và latency**, không chỉ số active TCP sessions.

## 19. Bảo vệ dữ liệu bí mật và quyền riêng tư trong metadata

gRPC metadata có thể chứa **Authorization token, trace ID, session ID, tenant ID, device identity, client cert context hoặc giá trị ứng dụng**. Một số metadata có hậu tố **-bin** biểu thị dữ liệu nhị phân theo quy ước gRPC và có cách mã hóa trên wire tương ứng; không nên giả định đó là dữ liệu vô hại chỉ vì không đọc được như văn bản.

### Nguyên tắc thu thập

1. Chỉ ghi **method name, service ID, principal ID được phép, status, thời lượng và bytes** khi đủ cho giám sát.
2. Che hoặc không lưu **Authorization, Cookie, client certificate private key, payload nhạy cảm và toàn bộ protobuf body**.
3. Giới hạn trace baggage và propagation headers để ngăn người dùng đưa dữ liệu tùy ý vào log.
4. Không trả về **stack trace nội bộ, cấu trúc database hay secret** trong grpc-message.
5. Áp retention, RBAC, audit access và chính sách dữ liệu theo môi trường.
6. Nếu cần forensic packet capture, thu tại điểm được cấp quyền, hạn chế giải mã và bảo quản theo quy trình.

### Tracing và caller identity

Trace ID giúp nối request qua gateway và services, nhưng **trace ID không phải danh tính đáng tin**; client có thể tự cung cấp header trace trong nhiều mô hình. Hệ thống phải tạo/chuẩn hóa ngữ cảnh cần thiết và gắn user/service identity qua cơ chế xác thực riêng.

**Ẩn metadata trong dashboard không đồng nghĩa nó không còn nằm trong raw logs**. Cần thực thi redaction tại nguồn thu và kiểm thử bằng token giả, không chỉ cấu hình ở lớp hiển thị.

## 20. Quan sát traffic đã mã hóa và giới hạn của IDS/IPS

Trên đường mạng, sensor thường thấy **TCP/IP flow và TLS metadata**, nhưng không tự đọc gRPC method hoặc protobuf payload bên trong TLS. Nếu service mesh mTLS bảo vệ east–west traffic, một NIDS nằm giữa các node có thể chỉ thấy lưu lượng mã hóa.

| Điểm đặt sensor | Dữ liệu có thể thấy | Giới hạn |
|---|---|---|
| **Trước TLS termination** | IP, port, flow, TLS/certificate metadata tùy phiên bản và điểm quan sát | Không tự thấy RPC method/payload |
| **Tại API gateway** | SNI/ALPN, metadata, method, auth decision nếu gateway hỗ trợ | Không thấy trực tiếp mọi downstream resource check |
| **Sidecar/service mesh** | Workload identity, service traffic, một số RPC metadata | Phụ thuộc mode, filter và nơi TLS được giải mã |
| **Backend application** | Method, principal, resource, status và nghiệp vụ | Cần instrument đúng, tránh lưu secret |
| **Host/EDR** | Process, connections, tài nguyên, socket state | Không phải lúc nào có payload hoặc tenant context |
| **Firewall/NDR** | Flow, byte count, zone, route/deny | Không đại diện authorization thành công |

**Không có HTTP/2 payload trong packet capture không chứng minh không có gRPC traffic.** Có thể traffic được mã hóa, đi qua VPN, dùng đường cloud khác hoặc sensor không đứng trên path.

### Sự khác biệt giữa WAF và authorization

WAF có thể lọc những mẫu request theo khả năng parser/policy, nhưng không nên để WAF quyết định caller có được đọc **item của tenant B** hay không. Quyết định này cần trạng thái nghiệp vụ và identity ở backend/authorization service.

## 21. Xây dựng metrics, logs và tracing cho gRPC

Nên thiết kế telemetry tối thiểu theo ba cấp: **connection, RPC và business resource**.

| Nhóm | Metric / event hữu ích |
|---|---|
| **TLS/connection** | Handshake failures, ALPN, active connections, connection age, GOAWAY |
| **HTTP/2** | Open/closed streams, concurrent streams, resets, header errors, flow-control stalls |
| **gRPC** | RPC count by service/method/status, in-flight RPC, deadline exceeded, cancellations |
| **Resource** | CPU/memory, queue depth, worker pool, DB pool, decompression failures |
| **Authorization** | UNAUTHENTICATED, PERMISSION_DENIED by method/role, tenant access denials |
| **Reliability** | Retry attempts, latency p50/p95/p99, streaming duration, goodput |
| **Network** | Drop/deny, connection failures, MTU/PMTUD, VPN path, route changes |
| **Deployment** | Error surge after release, old/new proxy version, cert rotation, config drift |

### Ví dụ log tổng hợp đã che dữ liệu

~~~text
time=2026-11-28T11:00:00+07:00
environment=staging
gateway=grpc-edge-01
service=inventory.v1.InventoryService
method=GetItem
principal=service-account-inventory-reader
caller_tenant=tenant-a
grpc_status=PERMISSION_DENIED
http_status=200
duration_ms=14
request_bytes=96
response_bytes=0
trace_id=lab-trace-001
authorization_token=[REDACTED]
source_ip=10.20.10.15
~~~

Đây là **log giả lập**. HTTP 200 đi kèm grpc_status PERMISSION_DENIED có thể là kết quả gRPC hợp lệ. Cần xem dữ liệu do **client/gateway/server** ghi, vì không phải mọi lớp log đều đọc được trailers.

### Chỉ số chất lượng detection

- **Coverage:** tỷ lệ service/method và đường traffic có metrics từ đúng điểm.
- **Attribution:** tỷ lệ request gắn được với service/caller identity và tenant đã xác minh.
- **Alert precision:** tỷ lệ alert đã được review là vấn đề thực trên tập được gắn nhãn.
- **MTTD/MTTR:** thời gian phát hiện và xử lý lỗi.
- **False block:** lưu lượng hợp lệ bị gateway/rate limits từ chối.
- **Sampling bias:** tracing có thể chỉ lấy mẫu request, không đảm bảo phản ánh mọi lỗi hiếm.
- **Availability:** tỷ lệ RPC thành công theo nghiệp vụ, không chỉ HTTP status và trạng thái TCP.

## 22. Phân biệt các mã lỗi gRPC khi điều tra

| gRPC status | Ý nghĩa thường gặp | Không tự kết luận |
|---|---|---|
| **OK** | RPC hoàn tất theo gRPC protocol | Chưa tự chứng minh business transaction đúng |
| **UNAUTHENTICATED** | Thiếu hoặc không xác minh được thông tin xác thực | Không tự chứng minh có tấn công |
| **PERMISSION_DENIED** | Caller đã xác định hoặc request không được phép theo policy | Cần xem phương thức/tài nguyên và thiết kế phản hồi |
| **INVALID_ARGUMENT** | Request không thỏa điều kiện được kiểm tra | Có thể do bug client hoặc dữ liệu sai |
| **RESOURCE_EXHAUSTED** | Vượt resource/quota | Có thể do quá tải hợp lệ hoặc lạm dụng |
| **DEADLINE_EXCEEDED** | Deadline hết trước khi RPC hoàn thành | Có thể do mạng, DB chậm hoặc timeout không phù hợp |
| **CANCELLED** | RPC bị hủy từ client hoặc tầng liên quan | Không phải mọi cancel đều độc hại |
| **UNAVAILABLE** | Dịch vụ tạm thời không thể xử lý/tiếp cận theo nghĩa giao thức | Điều tra route, gateway, failover, app và health |
| **INTERNAL** | Lỗi nội bộ hoặc sai điều kiện của hệ thống | Không trả stack trace/secret ra client |

**Không ánh xạ máy móc một grpc-status sang một HTTP status duy nhất.** Với gRPC native, transport có thể trả HTTP 200 ngay cả khi kết quả RPC là lỗi; với proxy không gRPC-aware có thể xuất hiện lỗi HTTP khác. Tracing và incident dashboard cần hiểu cả hai lớp.

## 23. Runbook bảo vệ và ứng cứu sự cố gRPC/HTTP/2

### Bước 1 — Xác định điều thật sự xảy ra

- Thời gian, nguồn, endpoint, SNI/ALPN, route/VPN và proxy chain.
- Service/method, grpc-status, HTTP status, bytes và request duration.
- Mẫu tăng **RST_STREAM, concurrent streams, CPU, deadline, unauthorized calls hoặc 5xx**.
- Release/config change gần thời điểm lỗi, version gateway/library và trạng thái certificates.
- Phân biệt **một client bị lỗi** với ảnh hưởng rộng nhiều tenants/regions.

### Bước 2 — Tách lớp sự cố

~~~text
RPC lỗi hoặc latency tăng
        |
        +-- DNS/TCP/TLS chưa thông? -> route, firewall, SNI, mTLS
        |
        +-- HTTP/2 handshake/frame lỗi? -> ALPN, proxy, h2 config
        |
        +-- gRPC status lỗi? -> auth, quota, deadline, service
        |
        +-- Stream mở lâu? -> cancellation, flow control, buffering
        |
        +-- CPU/queue tăng? -> concurrency, backend, retry amplification
        |
        +-- Chỉ resource lạ bị truy cập? -> authorization, tenant checks
~~~

Một hệ thống có thể đồng thời mắc nhiều lỗi. Đừng kết luận từ một thông báo “stream closed” mà không có timeline kết nối và log server.

### Bước 3 — Kiềm chế đúng phạm vi

1. Nếu có dấu hiệu overload, điều chỉnh **rate/concurrency limit** ở lớp nhìn được caller/method, kiểm tra false block.
2. Nếu một caller/token bị nghi lạm dụng, sử dụng **quy trình thu hồi/điều tra danh tính** đã được phê duyệt.
3. Nếu gateway có lỗ hổng HTTP/2 đã biết, ưu tiên **cập nhật bản vá/mitigation do vendor khuyến cáo**, có kiểm thử tương thích.
4. Nếu traffic bypass gateway/mesh, sửa **route, network policy, listener hoặc firewall boundary**.
5. Nếu vấn đề retry storm, giảm khuếch đại bằng retry budget/circuit breaker và kiểm soát backend.
6. Nếu nghi dữ liệu bị lộ, bảo toàn bằng chứng theo quyền riêng tư và quy trình incident response.

**Không tắt TLS/mTLS, mở allow-all hoặc bỏ authorization chỉ để làm một RPC thử nghiệm chạy thành công.** Hành động chữa cháy phải duy trì kiểm soát tối thiểu và có kế hoạch rollback.

### Bước 4 — Xác minh sau thay đổi

- RPC hợp lệ hoạt động từ đúng caller/tenant và trên những đường mạng cần thiết.
- Caller thiếu quyền bị từ chối đúng bằng chứng method/resource.
- Tỷ lệ reset, deadline, resource exhaustion và latency trở lại baseline.
- Streaming dài hạn không rò memory, ứng dụng cancel/release tài nguyên đúng.
- Gateway/sidecar/backend có policy và telemetry nhất quán.
- Sự cố không tái diễn khi deploy/failover hoặc client reconnect.

## 24. Case study 1: HTTP/2 stream reset tăng và API chậm

**Bối cảnh giả định:** Dịch vụ inventory public được tiếp nhận qua API gateway gRPC-aware, chuyển vào backend. SOC nhận thấy CPU ở gateway tăng, số stream mở/hủy tăng mạnh, nhưng số TCP connections không thay đổi nhiều. p99 latency của method GetItem tăng và một số client hợp lệ bị timeout.

### Dữ liệu ban đầu

~~~text
Service: inventory.v1.InventoryService
Endpoint: api.example.test:443 (lab)
Transport: TLS + HTTP/2
Observation window: 10 minutes
TCP connection count: relatively stable
Stream creation / reset: increased sharply
Gateway CPU/queue: elevated
RPC failures: DEADLINE_EXCEEDED / UNAVAILABLE increased
Client attribution: incomplete
Verdict: SUSPICIOUS RESOURCE PRESSURE, chưa xác định nguồn
~~~

### Giả thuyết cạnh tranh

1. Một client library mới có bug hủy RPC sau timeout quá ngắn.
2. Một đợt deploy làm backend chậm, client cancel/retry nhiều hơn.
3. Một service-to-service loop hoặc retry policy sai gây request amplification.
4. Hoạt động lạm dụng HTTP/2 stream state/connection resources.
5. Gateway có lỗi/phiên bản không được vá hoặc thiết lập giới hạn quá lỏng.

### Hướng điều tra an toàn

1. Thu **rates và timeline** của stream creation, resets, connections, CPU và grpc-status theo nguồn đã cho phép.
2. Đối chiếu release change, client SDK versions, latency backend và retry attempts.
3. Xem vendor advisory, phiên bản gateway/HTTP2 library và giới hạn đã cấu hình.
4. Xác định client principal/tenant có được xác thực không và có cần containment có mục tiêu không.
5. Nếu cần, kích hoạt giới hạn phù hợp và giám sát **false positive với client hợp lệ**.
6. Kiểm thử theo traffic sinh từ lab **được kiểm soát** thay vì tạo tải giống tấn công trên production.

**Kết luận đúng khi chưa đủ bằng chứng:** “Có áp lực tài nguyên và stream reset bất thường; nguyên nhân chưa được xác nhận.” Không gắn nhãn Rapid Reset chỉ vì reset count tăng.

## 25. Case study 2: gọi RPC hợp lệ nhưng đọc nhầm tenant

**Bối cảnh giả định:** Hai dịch vụ trong cloud dùng mTLS. Service A có quyền gọi InventoryService/GetItem. Một bug ở backend chỉ xác thực mTLS peer và quyền gọi method, nhưng **không đối chiếu item_id với tenant được phép**.

~~~text
Peer mTLS identity: service-a (verified)
Method: GetItem (allowed)
Caller tenant: tenant-a (verified by gateway)
Requested item: item-tenant-b-045
Actual item owner: tenant-b

Bug: method authorization PASS,
     resource/tenant authorization missing.
~~~

### Vì sao lớp mạng không chặn được?

Firewall và mesh có thể xác minh đúng service A được kết nối tới B. Tuy nhiên **item_id** là dữ liệu nghiệp vụ trong protobuf, và quyền truy cập một object cần biết owner của object. Lỗi này là **authorization trong ứng dụng**, không phải TLS hay subnet route.

### Hướng khắc phục

1. Bắt buộc kiểm tra **principal → tenant → object ownership** khi đọc/ghi.
2. Không tin tenant_id từ request nếu chưa xác minh và ghép với identity.
3. Với list/export/streaming, lọc tất cả kết quả theo phạm vi caller.
4. Bổ sung test âm tính: tenant A không đọc/ghi được item thuộc tenant B.
5. Giới hạn trường và thông báo lỗi tránh làm lộ object existence ngoài quyền.
6. Giữ lớp network/mesh authorization làm kiểm soát bổ trợ, không xóa vì backend đã có logic.

**Kết luận:** mTLS và JWT giúp xác thực caller; bảo vệ gRPC hoàn chỉnh còn đòi hỏi kiểm soát quyền **tới từng tài nguyên và hành động**.

## 26. Thực hành kiểm thử ít tác động trong lab

Thực hành này chỉ dùng **dịch vụ/staging do nhóm học hoặc tổ chức cho phép**, không quét mạng công cộng hoặc thử đo tải, fuzz hay gửi request phá hoại.

### Mục tiêu

1. Xác minh endpoint hỗ trợ TLS/ALPN theo dự kiến.
2. Gọi một RPC **read-only** với client đã xác thực phù hợp.
3. Đọc gRPC status và latency, không đánh đồng HTTP 200 với thành công.
4. Kiểm chứng một trường hợp **thiếu quyền trong lab**.
5. Quan sát logging/redaction và trace correlation.

### 26.1. Quan sát ALPN bằng OpenSSL

~~~bash
openssl version
openssl s_client \
  -connect api.example.test:443 \
  -servername api.example.test \
  -verify_hostname api.example.test \
  -verify_return_error \
  -alpn h2 \
  -brief
~~~

**Phải thay hostname bằng tên lab/staging được phép.** OpenSSL s_client giúp thấy kết quả TLS và ALPN nếu build hỗ trợ, **không tự thực hiện một RPC gRPC có nghĩa**. Một TLS handshake PASS không chứng minh backend đã cho phép method.

### 26.2. Kiểm tra HTTP/2 với curl phù hợp

~~~bash
curl -V
curl -vI --http2 https://api.example.test/health
~~~

**Lưu ý quan trọng:** Lệnh này chỉ thích hợp nếu endpoint được duyệt thực sự hỗ trợ **HTTP HEAD** tại đường /health; nhiều gRPC server **không hỗ trợ HEAD/REST** và trả 404/405 dù gRPC hoạt động tốt. Tùy chọn --http2 yêu cầu curl build hỗ trợ HTTP/2, và có thể không ép được native gRPC semantics. Không dùng kết quả HEAD làm kết luận gRPC application FAIL.

### 26.3. Dùng grpcurl với proto đã được cấp

Với gRPC server không mở reflection, người học có thể dùng **file .proto/descriptor được service owner cung cấp**. Ví dụ cú pháp minh họa:

~~~bash
grpcurl \
  -cacert lab-ca.pem \
  -import-path ./proto \
  -proto inventory.proto \
  -d '{"item_id":"item-a-001"}' \
  api.example.test:443 \
  inventory.v1.InventoryService/GetItem
~~~

Điều kiện:

- **lab-ca.pem** là CA certificate công khai do tổ chức cấp, không chứa private key.
- Method GetItem phải tồn tại theo proto thật và **được cấp phép thử**.
- Nếu method cần token/client cert, lấy credential qua cơ chế bảo mật được duyệt; **không dán secret vào tài liệu, shell history hay log**.
- Không dùng tùy chọn bỏ qua TLS verification để tuyên bố kết nối an toàn.
- Một số phiên bản công cụ có cú pháp flag/định dạng khác, phải đọc help của bản cài.
- Không mở reflection cho toàn Internet chỉ để làm bài lab.

### 26.4. Mẫu ghi kết quả

~~~text
Test ID:             GRPC-SEC-LAB-01
Environment:         staging / lab approved
Source/owner:        [test client identity]
Hostname/port:       [FQDN:port]
IP and network path: [IPv4/IPv6, VPN, gateway]
TLS/ALPN:            [verified / failed / not observed]
Method:              [package.Service/Method]
RPC type:            [unary / client/server/bidi stream]
Authentication:      [type, no secrets recorded]
Authorization:       [role, tenant/resource scope]
HTTP status:         [if logged]
gRPC status:         [code]
Duration / bytes:    [metrics]
Trace ID:            [test trace]
Expected result:     [allow / deny]
Observed result:     [outcome]
Verdict:             [PASS / FAIL / INCONCLUSIVE]
Evidence / reviewer: [approved logs and owner]
~~~

## 27. Ma trận kiểm thử bảo vệ HTTP/2 và gRPC

| Test ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| **GSEC-01** | Client hợp lệ gọi unary RPC trong phạm vi | TLS, authentication, resource authorization và response đúng |
| **GSEC-02** | Client thiếu authentication gọi method bảo vệ trong lab | UNAUTHENTICATED hoặc kết quả từ chối phù hợp policy |
| **GSEC-03** | Caller hợp lệ nhưng không có quyền method | PERMISSION_DENIED; không tiết lộ dữ liệu |
| **GSEC-04** | Caller tenant A đọc object tenant B | Deny tại resource authorization |
| **GSEC-05** | Client mTLS tin cậy nhưng access token thiếu quyền | Không có quyền vượt cấp |
| **GSEC-06** | Request metadata lớn hơn policy trong lab | Rejected theo giới hạn, server ổn định |
| **GSEC-07** | gRPC request lớn hơn max message lab | Bị giới hạn, không OOM |
| **GSEC-08** | Payload nén vượt decompressed budget trong lab | Reject an toàn, không cạn CPU/memory |
| **GSEC-09** | Quá số RPC đồng thời được cấp ở staging | Rate/concurrency limit áp đúng, có đo false block |
| **GSEC-10** | Stream idle/deadline hết | Cleanup tài nguyên, metrics/cancellation đúng |
| **GSEC-11** | Client chủ động cancel một stream hợp lệ | Không làm rò goroutine/thread/DB |
| **GSEC-12** | Upload stream nhiều message hợp lệ | Áp tổng bytes/quota và validate từng message |
| **GSEC-13** | Retry với thao tác ghi có idempotency | Không tạo bản ghi/giao dịch trùng |
| **GSEC-14** | Gateway HTTP/2→HTTP/1.1 | Header/body/trailer xử lý đúng, reject input không hợp lệ |
| **GSEC-15** | Native gRPC qua gateway/LB | Streaming/trailers/status được bảo toàn |
| **GSEC-16** | Browser gRPC-Web qua gateway | CORS, token, translation và giới hạn đúng |
| **GSEC-17** | Reflection từ nguồn không được cấp quyền | Không cung cấp schema nếu policy không cho phép |
| **GSEC-18** | Backend bị gọi trực tiếp ngoài mesh trong lab | Network/host policy chặn đường bypass |
| **GSEC-19** | IPv4 và IPv6 dual-stack | Cùng authentication và firewall policy |
| **GSEC-20** | TLS/mTLS certificate rotation | Không mất trust; method behavior không đổi |
| **GSEC-21** | Graceful drain/failover | RPC mới được định tuyến hợp lệ, RPC đang chạy xử lý đúng |
| **GSEC-22** | HTTP/2 parser/proxy patch | Không regression, vẫn đáp ứng SLO và giới hạn |
| **GSEC-23** | Log của RPC có token giả | Token bị redacted ở raw logs/traces |
| **GSEC-24** | Deny từ WAF/gateway, backend và ứng dụng | Kết quả/telemetry đủ phân biệt lớp từ chối |
| **GSEC-25** | HTTP status 200 cùng grpc-status lỗi trong lab | Monitoring báo RPC failure đúng |
| **GSEC-26** | Mất đường VPN/DNS trong diễn tập được phép | Phân loại network failure, không nhầm auth failure |
| **GSEC-27** | Load thường và giờ cao điểm trong staging | Bảo toàn latency/error budget theo khả năng đã xác định |
| **GSEC-28** | Runtime/framework bị cấu hình thiếu limit | Cảnh báo policy gap và khắc phục trước production |

**Các bài thử gây tải, stream abuse hoặc giao thức lỗi phải được mô phỏng ở lab/staging với tài nguyên, nhịp và ngưỡng dừng đã được phê duyệt.** Bảng trên là ma trận kỳ vọng, không phải lời hướng dẫn thực hiện tấn công thực tế.

## 28. Đánh giá chất lượng kiểm soát và false positive

Một chính sách chặn hiệu quả không chỉ làm giảm số lỗi bảo mật mà còn phải bảo vệ **dịch vụ hợp lệ**:

| Chỉ số | Ý nghĩa | Rủi ro diễn giải |
|---|---|---|
| **Authorized RPC success rate** | Request hợp lệ hoàn thành theo nghiệp vụ | HTTP 200 không luôn bằng grpc-status OK |
| **Unauthorized access prevention** | Request ngoài quyền được từ chối | Test thiếu object-level case có thể tạo tự tin giả |
| **Rate-limit false blocks** | Caller hợp lệ bị từ chối nhầm | NAT/shared identity hoặc burst hợp lệ có thể bị chặn |
| **Stream resource efficiency** | CPU/memory/queue theo in-flight streams | Connection count thấp không đồng nghĩa tài nguyên thấp |
| **Deadline/cancel cleanup** | Tài nguyên được giải phóng sau cancel | App có thể vẫn chạy tác vụ dưới nền |
| **Patch coverage** | Proxy/framework/SDK theo phiên bản hỗ trợ | Edge đã vá nhưng backend hoặc sidecar còn cũ |
| **Observability coverage** | Phần trăm RPC có log/tracing đáng tin | Sampling và encrypted paths tạo blind spot |
| **p95/p99 latency** | Chất lượng trải nghiệm khi tăng tải | Có thể do database hoặc downstream, không chỉ HTTP/2 |

### Giảm false positive cho giới hạn tài nguyên

- Không dùng ngưỡng giống nhau cho **GetItem**, **WatchItems**, **UploadChanges**.
- Định nghĩa quota theo **principal, tenant, method và cost**, có cửa sổ burst phù hợp.
- Với client qua NAT/proxy, hạn mức theo source IP duy nhất có thể chặn nhầm nhiều người dùng.
- Không tự coi mọi **CANCELLED/RST_STREAM** là tấn công.
- Khi điều chỉnh timeout/stream limit, chạy canary và quan sát retry amplification.
- Đánh dấu **INCONCLUSIVE** nếu thiếu log/trailer hoặc không biết điểm kết thúc TLS.

## 29. Những hiểu nhầm thường gặp

| Nhận định sai | Vì sao không đúng | Cách hiểu phù hợp |
|---|---|---|
| “gRPC dùng HTTP/2 nên tự an toàn hơn REST” | Giao thức không thay auth, authorization và giới hạn tài nguyên | Bảo vệ nhiều lớp |
| “HTTP/2 = luôn có TLS” | h2c tồn tại, TLS còn phụ thuộc kiến trúc | Xác định từng transport hop |
| “HPACK là mã hóa header” | HPACK là nén, không phải bảo mật | TLS và dữ liệu nhạy cảm vẫn cần bảo vệ |
| “Một TCP connection chỉ có một request” | HTTP/2 multiplex streams | Đo stream/RPC, không chỉ connection |
| “Flow control bảo vệ mọi loại DoS” | Không giới hạn mọi CPU/header/DB và stream lifecycle | Resource budgets ở nhiều lớp |
| “RST_STREAM nào cũng độc hại” | Client cancel và deadline là bình thường | Điều tra tỷ lệ, ngữ cảnh và tác động |
| “mTLS peer hợp lệ có toàn quyền API” | Peer identity khác method/resource authorization | Deny-by-default và kiểm tra tenant |
| “JWT signature hợp lệ thì mọi claim đáng tin cho API này” | Cần issuer, audience, lifetime, scopes và policy | Validate token đầy đủ |
| “Tenant ID trong protobuf do client gửi là identity” | Client có thể tự thay đổi trường | Bind resource với principal đã xác minh |
| “HTTP 200 có nghĩa gRPC OK” | RPC status thường nằm trong trailers | Đọc grpc-status và business outcome |
| “Một max frame size sẽ chặn mọi payload lớn” | Message có thể trải qua nhiều frames và compression | Max message, decompressed budget |
| “Gateway đã auth nên backend khỏi kiểm tra” | Proxy/header bypass hoặc lỗi mapping có thể xảy ra | Ranh giới tin cậy, authz tại backend |
| “WAF mặc nhiên đọc được protobuf binary” | Phụ thuộc parser/gateway/schema | Xác minh khả năng sản phẩm |
| “grpcurl cần bật reflection public” | Có thể dùng proto descriptors được cấp | Hạn chế reflection |
| “Mọi gRPC-Web streaming giống native gRPC” | Transport/browser/proxy có giới hạn | Test từng kiểu RPC được hỗ trợ |
| “Client hủy RPC là server chắc chắn dừng việc” | Cancellation phải được app/downstream xử lý | Propagate cancel, đo cleanup |
| “Retry luôn giúp availability” | Retry storm và thao tác ghi lặp | Retry budget + idempotency |
| “Gateway GOAWAY nghĩa mọi RPC đã thành công” | Drain không xác nhận business result | Deadline, result và app logs |
| “IDS không thấy request tức là không có traffic” | TLS/mTLS/VPN/sensor placement tạo blind spot | Gateway/backend telemetry |
| “Quy tắc IPv4 bảo vệ luôn IPv6” | Dual-stack có đường/rule khác nhau | Test cả hai address family |

## 30. Câu hỏi tự kiểm tra

1. HTTP/2 khác HTTP/1.1 ở multiplexing như thế nào, và vì sao việc giám sát chỉ đếm connections có thể bỏ sót vấn đề?
2. gRPC sử dụng HTTP/2 như thế nào? Mối quan hệ giữa HTTP status và grpc-status là gì?
3. HPACK có cung cấp mã hóa không? Header metadata có thể lộ ở đâu sau TLS termination?
4. Frame HEADERS, DATA, SETTINGS, RST_STREAM và GOAWAY có vai trò khác nhau thế nào?
5. Vì sao HTTP/2 flow control không tự bảo vệ server khỏi việc tiêu thụ quá nhiều CPU hoặc database connections?
6. Các bài học phòng thủ quan trọng từ CVE-2023-44487 là gì mà không cần tái tạo traffic tấn công?
7. Những ranh giới an ninh nào cần kiểm tra khi gateway chuyển HTTP/2 sang HTTP/1.1?
8. gRPC unary, server streaming, client streaming và bidi streaming cần những giới hạn khác nhau ra sao?
9. Khi client cancel một stream, server cần xử lý downstream work và memory thế nào?
10. TLS + ALPN h2 khác h2c ở bảo mật kết nối như thế nào?
11. mTLS giúp xác thực điều gì? Vì sao không tự giải quyết BOLA ở item_id?
12. Khi xác minh JWT cho gRPC, cần kiểm tra những claim/thuộc tính nào ngoài chữ ký?
13. Vì sao metadata do client tự gửi không được tin làm internal identity context nếu gateway chưa kiểm chứng?
14. Protobuf có tự đảm bảo string/bytes và repeated fields nằm trong giới hạn nghiệp vụ không?
15. Vì sao max compressed message size cần đi cùng max decompressed budget?
16. Deadline, idle timeout và retry budget giải quyết những vấn đề khác nhau ra sao?
17. gRPC-Web có những lưu ý gì về CORS, translation, method/status và streaming?
18. Server reflection có ích gì, và vì sao không nên mở mặc định cho nguồn không được quản lý?
19. Khi một RPC tăng lỗi RESOURCE_EXHAUSTED, cần phân biệt quá tải hợp lệ với lạm dụng thế nào?
20. Một NIDS ngoài service mesh có thể không thấy gRPC method vì những lý do nào?
21. Trường hợp nào HTTP 200 vẫn phải tính vào tỷ lệ RPC lỗi?
22. Vì sao phải test sự nhất quán của policy ở cả IPv4/IPv6, VPN, edge và backend?
23. Nếu một load balancer báo healthy nhưng streaming RPC liên tục failover, cần kiểm tra những gì?
24. Hãy thiết kế test chứng minh tenant A không đọc được dữ liệu tenant B dù gRPC peer và JWT của tenant A hợp lệ.
25. Những dữ liệu nào phải redacted khỏi logs/tracing khi kiểm tra token và client identity?
26. Hãy đề xuất dashboard gồm tối thiểu 5 metrics giúp bảo vệ gRPC khỏi resource exhaustion mà không chặn nhầm dịch vụ hợp lệ.

## 31. Ghi nhớ trọng tâm

**gRPC là mô hình gọi hàm từ xa, còn HTTP/2 là lớp truyền tải HTTP có streams, frames, multiplexing, header compression và flow control.** Những đặc tính hiệu quả này cũng đòi hỏi kiểm soát tài nguyên theo **connection, stream, RPC, principal, tenant và nghiệp vụ**. TLS/ALPN, mTLS, JWT và service identity cần được xác minh **ở đúng trust boundary**, nhưng **method-level và object-level authorization** vẫn bắt buộc để ngăn truy cập sai quyền.

Để bảo vệ hệ thống gRPC/HTTP/2, hãy kết hợp **HTTP/2 stack và proxy được cập nhật bản vá, giới hạn headers/metadata/messages/concurrency, backpressure, deadlines, cancellation, retry budgets, protobuf validation, phương án streaming và ingress/egress segmentation**. Khi có HTTP/2→HTTP/1.1 hoặc gRPC-Web translation, phải kiểm chứng request parsing, status, trailers và danh tính caller không bị thay đổi sai. WAF/IDS/IPS chỉ có hiệu quả trong phạm vi chúng **thật sự quan sát/giải mã được**; lớp nghiệp vụ phải tự thực thi authorization và data validation.

Vận hành an toàn cần **dashboard theo grpc-status, resets/stream rates, latency, resource budgets, xác thực/phân quyền, DNS/VPN/TLS và trạng thái rollout**, cùng **runbook, phép thử có quyền, ma trận ALLOW/DENY và rollback**. Không đánh đồng **HTTP 200, một TLS handshake thành công, một kết nối mTLS được xác thực hoặc một ping mạng** với kết luận toàn bộ RPC đã an toàn. Kết luận tốt phải nêu rõ **đo ở đâu, quan sát được gì, policy nào được kiểm tra và điều gì còn chưa được xác minh**.
