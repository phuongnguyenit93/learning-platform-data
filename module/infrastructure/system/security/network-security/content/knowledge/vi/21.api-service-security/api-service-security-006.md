# Request size limit cho network service: giới hạn đầu vào để bảo vệ API và tài nguyên mạng

Trong chương **API và network service security** của module **SECURITY_NETWORK_SECURITY**, **request size limit** là tập hợp các giới hạn đối với kích thước dữ liệu mà một dịch vụ mạng cho phép nhận, chuyển tiếp, giải mã, phân tích và xử lý trong **một yêu cầu hoặc một đơn vị thông điệp**. Đây là biện pháp phòng vệ thiết thực trước rủi ro cạn kiệt **RAM, CPU, file descriptor, băng thông, bộ nhớ đệm, dung lượng đĩa và tài nguyên backend**.

Ví dụ: một endpoint JSON chỉ cần vài kilobyte nhưng lại nhận body hàng trăm megabyte; một client gửi số lượng lớn trường header; một tệp nén rất nhỏ phình thành nhiều gigabyte khi giải nén; hoặc một phiên HTTP/2 chứa nhiều streams với thông điệp lớn đồng thời. Dù hành vi là lỗi client, tăng tải hợp lệ hay có chủ đích, nếu hệ thống không có ngân sách tài nguyên rõ ràng thì proxy, WAF, API gateway hoặc ứng dụng có thể bị quá tải.

**Giới hạn request không chỉ là đặt một con số max body size.** Cần xác định loại dữ liệu nào được tính, đo ở bước nào, có giải nén không, có xử lý streaming hay multipart không, điểm nào có quyền từ chối, phản hồi HTTP ra sao và có còn đường bypass ở một gateway khác không.

Sau bài học, bạn có thể:

- Phân biệt **request-line/URI, headers, body, file part, dữ liệu giải nén, gRPC message, HTTP stream** và các ngưỡng kích thước tương ứng.
- Hiểu giới hạn khi request dùng **Content-Length, Transfer-Encoding: chunked, HTTP/2 hoặc HTTP/3**; không tin tuyệt đối số bytes do client tự khai.
- Thiết kế nhiều lớp kiểm soát từ **CDN/WAF, reverse proxy, API gateway** đến **ứng dụng, parser, queue và storage**.
- Đọc cấu hình NGINX minh họa cho **client_max_body_size, client_body_buffer_size, client_body_timeout** và giải thích vì sao chúng không tương đương nhau.
- Bảo vệ **JSON, XML, multipart upload, payload nén, WebSocket và gRPC**, cùng những yêu cầu streaming dài.
- Phân biệt **413, 414, 415, 429, 431, 503** và các phản hồi do backend/proxy tạo ra.
- Lập ngân sách tài nguyên, giám sát, kiểm thử giới hạn an toàn và giảm false positive với request hợp lệ.

## 1. Bài toán: một request có thể tiêu thụ bao nhiêu tài nguyên?

Một API request bình thường đi qua nhiều tầng:

~~~mermaid
flowchart LR
    C["Client / SDK / thiết bị IoT"] --> E["CDN / WAF / Edge"]
    E --> L["Load balancer / Reverse proxy"]
    L --> G["API gateway"]
    G --> A["Application / Parser"]
    A --> S["DB / Object storage / Queue"]
    E -. "Size / limit / telemetry" .-> O["SOC / SRE / Observability"]
    L -. "Bytes / buffering / 413" .-> O
    G -. "Route quotas" .-> O
    A -. "Decode / memory / validation" .-> O
~~~

Ở mỗi tầng, **request có thể được biểu diễn khác nhau**: bytes trên mạng, bytes body sau HTTP framing, payload sau giải nén, cấu trúc JSON/XML đã parse, đối tượng ứng dụng, tệp tạm hoặc một bản ghi đưa vào queue. Một giới hạn chỉ kiểm tra **Content-Length** chưa chắc ngăn ứng dụng tạo cấu trúc trong RAM lớn hơn hàng trăm lần.

| Tài nguyên | Cách request lớn ảnh hưởng | Dấu hiệu cần theo dõi |
| --- | --- | --- |
| **Băng thông ingress** | Client truyền quá nhiều bytes, nhất là ở upload hoặc telemetry | Bytes/s, throughput, ingress drops |
| **Proxy buffers / RAM** | Nhiều request bodies và headers được giữ đồng thời | RSS, heap, per-request buffer, OOM |
| **Temporary disk** | Reverse proxy ghi body lớn xuống tệp tạm | Dung lượng trống, I/O, inode, temporary file count |
| **CPU** | JSON/XML/protobuf parser, giải nén, kiểm tra chữ ký, antivirus | CPU time/request, saturation, parser duration |
| **App workers / queues** | Request lớn xử lý lâu, chiếm slot, gây hàng đợi | In-flight requests, queue wait, timeout |
| **DB và object store** | Payload tạo nhiều write/query hoặc đối tượng rất lớn | Write bytes, DB pool, transaction time |
| **TLS, sockets và conntrack** | Kết nối dài hoặc đồng thời với nhiều body streams | Active connections, streams, FD, conntrack usage |
| **Giám sát và logging** | Ghi raw body hoặc header lớn vào log | Log pipeline drops, storage usage, chi phí thu thập |

**Giới hạn kích thước không thay thế rate limit hoặc connection limit.** Một request cực lớn và một triệu request nhỏ có thể gây quá tải theo những cơ chế khác nhau. Kiến trúc phải có nhiều ngân sách độc lập.

### 1.1. Request hợp lệ vẫn có thể lớn

Ví dụ những nhu cầu có thể chính đáng:

1. API CRUD thường nhận JSON vài kilobyte.
2. Thiết bị IoT gửi telemetry theo lô vài trăm kilobyte.
3. Người dùng upload một hình ảnh hoặc tài liệu hàng chục megabyte.
4. Khách hàng upload video dung lượng lớn qua **resumable/chunked application uploads**.
5. gRPC hoặc WebSocket trao đổi nhiều message có kích thước khác nhau.

**Không đặt một ngưỡng toàn hệ thống chỉ theo request nhỏ nhất hoặc lớn nhất.** Nên áp **mức nền an toàn tại ingress** và **policy theo route, phương thức, loại media, user/tenant và nhu cầu nghiệp vụ**. Một ngoại lệ upload lớn phải có hạn mức, xác thực, quota, storage controls và giám sát riêng.

## 2. Phải định nghĩa chính xác “kích thước request”

Từ **request size** có thể chỉ những đại lượng khác nhau:

| Đại lượng | Đếm gì? | Ví dụ về hạn mức |
| --- | --- | --- |
| **Request target / URI** | Path, query string, request target của HTTP/1.x | Giới hạn độ dài URI và số query parameters |
| **HTTP header block** | Tổng tên/giá trị headers và các giới hạn từng field | Tổng header bytes, số fields, kích thước cookie/auth header |
| **Encoded body size** | Bytes body sau khi lớp HTTP transfer framing được diễn giải, nhưng có thể **chưa giải nén Content-Encoding** | Max body 1 MiB |
| **Decoded body size** | Bytes sau khi giải nén hoặc decode nội dung theo policy | Max decoded body 4 MiB |
| **Multipart total size** | Tổng body kể cả boundaries, field data, file parts và metadata | Max multipart 25 MiB |
| **Per-file / per-part size** | Bytes của từng file hoặc part trong multipart | Max mỗi file 20 MiB |
| **Object count / field count** | Số part, JSON items, XML nodes hoặc số phần tử | Max 5 files, 50 fields |
| **Parser complexity** | Depth, nesting, số tokens, tham chiếu hoặc thời gian xử lý | Max JSON depth 32 |
| **gRPC message** | Một thông điệp gRPC sau xử lý framing/nén phù hợp | Max received message theo service |
| **WebSocket frame/message** | Kích thước frame và message tích lũy qua nhiều frame | Max message 256 KiB |
| **Aggregate concurrency** | Tổng bytes đang chờ đọc/parse trên nhiều request cùng lúc | Tổng buffer/queue budget |

**1 MiB = 1.048.576 bytes**. Cần ghi rõ đơn vị **MiB/MByes**, tránh người viết policy hiểu 1 MB là 1.000.000 bytes còn công cụ cấu hình tính theo lũy thừa hai. Một số proxy sử dụng hậu tố **k/m/g** theo quy tắc riêng; xác minh trên phiên bản triển khai.

### 2.1. Header size và body size không cùng một loại control

Một request body 1 KiB nhưng chứa nhiều header fields hoặc cookie quá lớn vẫn có thể tạo áp lực parser/buffer ở proxy. **Body limit không thay header limit**. Tương tự, một URI/query cực dài cần chính sách riêng.

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Content-Length: 48
Authorization: Bearer <redacted-token>

{"item":"demo","quantity":2,"note":"example"}
~~~

Đây là biểu diễn **khái niệm**; Content-Length trong ví dụ chỉ để minh họa trường header, không được coi là phép đo chính xác cho chuỗi JSON hiển thị. Khi tính bytes thật, phải đếm **octets truyền qua HTTP theo quy tắc của giao thức**, không dùng số ký tự Unicode hay giá trị ước lượng.

**Authorization và Cookie** đôi khi lớn vì JWT, nhiều cookies hoặc cơ chế session. Tăng header limit vô hạn để chữa lỗi đăng nhập thường che nguyên nhân gốc và làm tăng bề mặt DoS.

### 2.2. Raw bytes, decoded bytes và objects là ba ngân sách khác nhau

Ví dụ body dùng Content-Encoding: gzip:

~~~text
Độ dài body truyền trên HTTP:          120 KiB
Độ dài sau giải nén Content-Encoding:  18 MiB
Object tạo ra khi parse JSON:          Có thể dùng > 18 MiB RAM
~~~

Một gateway chỉ giới hạn **120 KiB bytes nén** có thể cho phép payload mở rộng đến 18 MiB hoặc hơn ở tầng ứng dụng. Cần tính riêng **giới hạn bytes nén, bytes giải nén, tỷ lệ mở rộng, độ sâu parse và thời gian CPU** nếu stack xử lý compressed request bodies.

Một số proxy/WAF có thể **không tự giải nén** body trước khi đo limit. Đừng khẳng định đã bảo vệ decoded payload khi chưa xác minh thứ tự các filter/decompression thực tế.

## 3. HTTP/1.1: Content-Length và Transfer-Encoding

### 3.1. Khi client gửi Content-Length

**Content-Length** biểu thị kích thước body theo ngữ nghĩa HTTP phù hợp. Nếu request khai Content-Length lớn hơn mức cho phép và server/proxy đã kiểm tra được nó, hệ thống có thể **từ chối sớm** mà không cần nhận toàn bộ body.

~~~text
Client:
  POST /api/profile
  Content-Length: 12582912

API ingress policy:
  Max request body: 1048576 bytes

Kết quả mong đợi:
  Reject theo policy (thường HTTP 413),
  không phân bổ buffer 12 MiB để xử lý body.
~~~

Nhưng **Content-Length là thông tin từ phía client**. Không được lấy giá trị này làm bằng chứng request thực tế chỉ có đúng chừng đó bytes trong mọi giao thức/trường hợp. Server HTTP phải tuân thủ framing, phát hiện request không hợp lệ và **đo bytes thực sự được nhận/đưa vào body**.

### 3.2. Khi body được truyền theo chunked framing

Với **HTTP/1.1 Transfer-Encoding: chunked**, tổng kích thước body có thể **không được biết trước** khi request bắt đầu. Proxy/ứng dụng cần đếm dần phần nội dung đã nhận và **ngừng nhận/parse khi vượt limit**, thay vì chỉ kiểm tra Content-Length.

~~~text
Nhận body theo dòng dữ liệu:
  accumulated = 0
  for each decoded HTTP body chunk:
      accumulated += chunk.byteLength
      if accumulated > route.maxEncodedBodyBytes:
          reject request as too large
          stop expensive processing and clean up resources
~~~

Đây là **pseudocode**, không phải parser HTTP tự viết. Phải để **HTTP stack được bảo trì** xử lý chunk framing, tiêu đề, trailers và các trạng thái kết nối. Không tự triển khai một parser HTTP bằng cách quét chuỗi Content-Length hay boundary thủ công.

### 3.3. Request smuggling/desynchronization và framing nhất quán

Trong một chuỗi nhiều proxy, rủi ro xuất hiện nếu **frontend và backend diễn giải ranh giới request khác nhau** (chẳng hạn các trường framing không hợp lệ hoặc mâu thuẫn). Đây là một lớp vấn đề độc lập với max body size; chỉ đặt ngưỡng bytes không giải quyết được.

Các nguyên tắc phòng vệ:

- Sử dụng HTTP parser và reverse proxy được hỗ trợ, cập nhật bản vá.
- **Từ chối request framing mơ hồ/không hợp lệ** theo chính sách giao thức.
- Hạn chế các chuyển đổi HTTP/1.1 ↔ HTTP/2 ↔ HTTP/3 không được kiểm thử.
- Đồng bộ cách xử lý **Content-Length, Transfer-Encoding, trailers và connection reuse** giữa các hop.
- Thử nghiệm các **invalid framing fixtures được cấp quyền** tại staging để xác nhận frontend/backend không hiểu khác nhau.

Không cần thử kỹ thuật request desynchronization vào dịch vụ không sở hữu để đánh giá chính sách của mình.

### 3.4. Expect: 100-continue

Client HTTP/1.1 có thể dùng **Expect: 100-continue** để hỏi server trước khi gửi body lớn. Nếu gateway biết request vượt limit dựa trên header/authorization, nó có thể từ chối sớm theo giao thức.

Tuy nhiên, không thể dựa vào cơ chế này để bảo vệ: **không phải client nào cũng dùng Expect**, một số client không chờ lâu và body có thể không có độ dài khai trước. Vẫn phải có kiểm soát **bytes thực nhận**.

## 4. HTTP/2 và HTTP/3: nhiều streams trên một connection

HTTP/2 vận chuyển request qua **streams** cùng một TCP connection; HTTP/3 dùng **QUIC streams** qua UDP. Không còn cách diễn giải đơn giản “một kết nối TCP = một request”.

~~~mermaid
flowchart TB
    C["Một client connection"] --> S1["Stream 1: /api/search"]
    C --> S2["Stream 3: /api/events"]
    C --> S3["Stream 5: /upload"]
    S1 --> G["Proxy / API gateway"]
    S2 --> G
    S3 --> G
    G --> L["Per-stream body limit + aggregate concurrency/buffer budget"]
~~~

### 4.1. Limit theo stream và theo connection phải tách riêng

Một hệ thống cần xem:

1. **Giới hạn body của từng request/stream**.
2. **Giới hạn header list** sau khi giải mã HPACK (HTTP/2) hoặc QPACK (HTTP/3) theo khả năng stack.
3. **Số streams đang hoạt động đồng thời** trên một connection và trên toàn listener.
4. **Tổng bytes đang buffer** của nhiều request streams.
5. **Flow-control và timeout** để client không giữ tài nguyên vô hạn mà không tiến triển.
6. **Giới hạn upstream concurrency**, vì một client connection có thể khuếch đại thành nhiều công việc backend.

Việc header được nén trên wire **không đồng nghĩa kích thước header sau giải nén nhỏ**. Cần giới hạn **header list/metadata** ở cấp HTTP parser và application, không chỉ theo số bytes wire.

### 4.2. Content-Length trong HTTP/2/3

Một HTTP/2/3 request có thể có trường Content-Length hợp lệ trong ngữ cảnh thích hợp, nhưng framing dùng **DATA frames/streams** chứ không dùng chunked transfer coding của HTTP/1.1. Vì vậy:

- Không dùng parser chunked của HTTP/1.1 áp vào HTTP/2/3.
- Kiểm tra nhất quán giữa Content-Length khai báo và số bytes DATA theo quy tắc protocol.
- Đo số bytes body sau HTTP framing, không cộng tất cả kích thước frame headers vào “body limit” trừ khi policy nói rõ.
- Cân nhắc việc proxy **downgrade** request xuống upstream HTTP/1.1; giới hạn cần giữ nguyên ý nghĩa sau chuyển đổi.

### 4.3. Giới hạn tổng thể

Nếu mỗi stream được phép 2 MiB và có 1.000 streams active, hệ thống có thể phải xử lý tới **khoảng 2.000 MiB body data** trong một khoảng, trước khi cộng overhead/parser. Con số này **không nhất thiết đồng thời ở RAM** nếu hệ thống streaming/buffering hợp lý, nhưng chỉ có per-stream limit là chưa đủ cho tài nguyên node.

Cần dùng **concurrency budget, bounded buffers, connection/stream limits và admission control**, đo bằng telemetry thay vì suy từ một cấu hình đơn lẻ.

## 5. Phân loại API trước khi chọn ngưỡng

Một bảng phân loại theo **hợp đồng nghiệp vụ và đặc tính lưu lượng**:

| Loại endpoint | Payload thường gặp | Chính sách nên xem xét |
| --- | --- | --- |
| **Authentication / token** | JSON hoặc form nhỏ, metadata xác thực | Body nhỏ, header/cookie limits, rate/abuse controls |
| **CRUD REST JSON** | Vài KiB đến giới hạn nghiệp vụ cụ thể | Encoded body + parsed structure + schema constraints |
| **Batch/telemetry ingestion** | Hàng trăm hoặc hàng nghìn events | Total bytes, item count, per-event size, per-tenant quota |
| **GraphQL** | JSON có query và variables | Body size **và** query complexity/depth/cost limits |
| **File upload** | Multipart hoặc binary body | Total body, per-file size, count, MIME validation, storage quota |
| **Compressed payload ingestion** | gzip/br/định dạng nén được hỗ trợ | Encoded bytes, decoded bytes, expansion ratio, CPU/time |
| **gRPC unary** | Một message cho request/response theo RPC | Max received message, metadata size, RPC deadline |
| **gRPC streaming** | Chuỗi messages theo stream | Per-message, aggregate stream, concurrency và backpressure |
| **WebSocket** | Nhiều frames/messages qua phiên dài | Max frame/message, aggregate rate, connection lifetime |
| **IoT/binary protocols** | Length-prefixed frames hoặc datagrams | Message length validation trước allocation, quotas theo device |

**Các giá trị dưới đây là minh họa, không phải khuyến cáo cấu hình mặc định**:

~~~yaml
# Policy ví dụ để thảo luận, KHÔNG phải syntax chuẩn của một API gateway.
default:
  max_encoded_body: "256 KiB"
  max_header_list: "16 KiB"
  max_uri_length: "4 KiB"

routes:
  - path: "/api/profile"
    methods: ["POST", "PUT"]
    max_encoded_body: "256 KiB"
    max_json_depth: 32
  - path: "/api/telemetry/batch"
    methods: ["POST"]
    max_encoded_body: "2 MiB"
    max_decoded_body: "8 MiB"
    max_events: 1000
  - path: "/uploads"
    methods: ["POST"]
    max_encoded_body: "25 MiB"
    max_files: 5
    max_per_file: "20 MiB"
    require_auth: true
    storage_quota: "Per user / tenant policy"
~~~

Khi sử dụng policy-as-code, cần xác định **bytes tính trước hay sau decompression**, cách làm tròn đơn vị, việc kiểm tra ở hop nào và cơ chế áp dụng khi body không khai độ dài.

### 5.1. Effective limit trong chuỗi nhiều tầng

Giả sử:

~~~text
CDN/WAF edge         : 10 MiB body
Reverse proxy        : 4 MiB body
API gateway          : 2 MiB body
Application JSON     : 1 MiB body
~~~

Nếu cùng đo **một kiểu biểu diễn body**, request 1,5 MiB có thể qua CDN/proxy/gateway rồi bị application từ chối. **Giới hạn hiệu lực** cho luồng này là mức thấp nhất trong đường đi, nhưng điều đó chỉ đúng nếu các tầng đang đếm **cùng một đại lượng**.

Nếu edge đo compressed bytes còn app đo decoded bytes, không thể suy ra effective limit bằng phép lấy min của bốn con số. Cần ghi **định nghĩa, đơn vị, thứ tự xử lý và nơi trả lỗi** của từng control.

### 5.2. Tránh cho route ít quyền mở ngoại lệ lớn

Một endpoint upload lớn có thể cần policy riêng, nhưng **không có nghĩa mở body limit 100 MiB cho toàn bộ /api/**. Nên giới hạn theo:

- Route và HTTP method đã phê duyệt.
- Identity/user/tenant nếu đã xác thực, nhưng vẫn có baseline bảo vệ **trước auth**.
- Content type và parser thực tế.
- Concurrency, bytes-per-minute hoặc storage quota.
- Môi trường, đường đi, vùng mạng và thiết bị hợp lệ.

Đừng xem giá trị **Content-Type** client tự gửi là bằng chứng payload thuộc loại an toàn; application cần xác minh và parse theo định dạng/kiểu đã hỗ trợ.

## 6. Reverse proxy, WAF và API gateway giới hạn body ở đâu?

Các lớp có vai trò khác nhau:

~~~mermaid
flowchart LR
    C["Client"] --> E["CDN / WAF: early size/abuse control"]
    E --> P["Reverse proxy: header/body/buffer/time"]
    P --> G["API gateway: route/auth/quota"]
    G --> A["App parser: decoded/semantic limits"]
    A --> D["Storage/DB: object/file/quota"]
    E -. "413 / other rejection" .-> C
    P -. "413" .-> C
    G -. "413 / 429" .-> C
~~~

### 6.1. Edge/WAF: từ chối sớm khi có thể

Đặt body/header limit ở **đường ingress Internet** giúp giảm bytes đi sâu vào hạ tầng. Nhưng cần xem:

- Dịch vụ CDN/WAF có **maximum inspection size** khác **maximum accepted request size** không?
- Payload quá mức inspect được xử lý thế nào: **reject, bypass inspection, log only hay partial inspection** theo cấu hình?
- Nếu WAF chỉ inspect vài KiB đầu, có nguy cơ phần còn lại tới ứng dụng mà chưa được kiểm tra nội dung theo nhu cầu bảo mật không?
- Traffic **trực tiếp tới origin**, đường VPN/private network hoặc load balancer khác có thể đi vòng edge không?
- HTTP/2/3, compressed bodies và multipart có được kiểm tra cùng semantics không?

**WAF inspection limit không đồng nghĩa request size limit.** Một WAF có thể ngừng inspect phần payload vượt ngưỡng nhưng vẫn chuyển request, tùy sản phẩm/chính sách. Cần kiểm tra hành vi thực của mỗi chế độ.

### 6.2. Reverse proxy: đọc và buffer có giới hạn

Reverse proxy có thể **đọc toàn bộ request trước khi gửi upstream**, ghi phần lớn xuống temporary files, hoặc **stream request** tới backend. Chọn cách nào ảnh hưởng tài nguyên:

| Cách xử lý | Lợi ích | Rủi ro cần kiểm soát |
| --- | --- | --- |
| **Buffer trước khi proxy_pass** | Có thể kiểm tra/ngắt request trước khi backend nhận toàn bộ; tách client chậm khỏi upstream | Tiêu thụ RAM/disk, tăng thời gian đợi, cần quota temporary storage |
| **Streaming passthrough** | Giảm lưu body ở proxy, hỗ trợ upload lớn | Backend phải chịu client chậm, partial writes và enforcement streaming |
| **Direct-to-object-storage upload** | Tách bytes lớn khỏi API workers/proxy nếu hạ tầng hỗ trợ | Cần size/TTL/content-type/identity quotas, kiểm tra file sau upload |

Tắt buffering **không tự làm hệ thống an toàn hơn**; có thể chuyển áp lực từ proxy sang backend, khiến số upstream connections và thời gian giữ worker tăng.

### 6.3. Backend: giới hạn cuối cùng không thể bỏ

Ngay cả khi edge đã đặt 1 MiB limit, backend vẫn cần kiểm tra riêng vì có thể nhận request từ **internal service, service mesh, VPN, localhost hoặc gateway khác**. Một bên có quyền gọi nội bộ không có nghĩa được phép gửi body không giới hạn.

Application phải từ chối payload vượt schema/size **trước khi đưa vào parser hoặc cơ sở dữ liệu với tài nguyên không giới hạn**, đồng thời kiểm tra authentication và authorization sau khi xử lý đủ thông tin cần thiết.

## 7. Cấu hình mẫu NGINX cho request size limit

Ví dụ này minh họa **một private reverse proxy được cấp quyền**. Nó không phải cấu hình production đầy đủ; phải bổ sung TLS hardening, audit, WAF, rate limit, trusted proxy chain, monitoring và quy trình rollback theo nền tảng thực.

~~~nginx
events {
    worker_connections 2048;
}

http {
    upstream api_backend {
        server 10.20.30.11:8080;
        server 10.20.30.12:8080;
    }

    log_format request_limits
        '$time_iso8601 source=$remote_addr '
        'uri=$uri status=$status request_bytes=$request_length '
        'request_time=$request_time upstream=$upstream_status';

    server {
        listen 443 ssl;
        server_name api.example.test;

        ssl_certificate     /etc/nginx/tls/api-chain.pem;
        ssl_certificate_key /etc/nginx/tls/api.key;

        # Giới hạn cơ sở cho endpoint không có ngoại lệ riêng.
        client_max_body_size    256k;
        client_header_timeout   10s;
        client_body_timeout     15s;
        client_body_buffer_size 128k;
        proxy_request_buffering on;

        access_log /var/log/nginx/api-limits.log request_limits;

        location /api/ {
            client_max_body_size 1m;
            proxy_pass http://api_backend;
        }

        location /uploads/ {
            # Chỉ dùng cho route upload có authentication/quota ở backend.
            client_max_body_size 20m;
            proxy_pass http://api_backend;
        }
    }
}
~~~

Tên **api.example.test** dùng cho ví dụ; backend IP thuộc dải private. Đoạn này chỉ cho thấy các directives liên quan, **không định nghĩa toàn bộ firewall/authentication, authorization hoặc body parser policy**.

### 7.1. Đọc chính xác từng directive

| Directive | Ý nghĩa | Không phải |
| --- | --- | --- |
| **client_max_body_size** | Mức tối đa body của request theo ngữ nghĩa NGINX; có thể đặt trong http/server/location | Không phải giới hạn header, JSON nesting hay decoded payload |
| **client_body_buffer_size** | Kích thước buffer dùng khi NGINX đọc body; body lớn hơn có thể ghi ra file tạm | Không phải hard max size của request |
| **client_body_timeout** | Thời gian chờ khi đọc body từ client theo semantics **inactivity giữa các lần đọc** | Không phải tổng deadline của upload |
| **client_header_timeout** | Thời gian chờ để nhận đủ headers theo logic NGINX | Không tự đặt giới hạn tổng bytes header |
| **proxy_request_buffering** | Kiểm soát cách NGINX buffer request body trước khi chuyển upstream | Không thay thế giới hạn body hoặc quota đĩa |
| **request_length** | Thông số log độ dài request theo định nghĩa NGINX | Không phải kích thước JSON sau giải nén |
| **proxy_pass** | Chuyển request đến upstream phù hợp | Không xác minh logic nghiệp vụ hay schema của backend |

Với NGINX, nếu body vượt **client_max_body_size**, phản hồi thường là **413 Content Too Large**. Khi gửi body lớn, một số client có thể quan sát hành vi đóng/gián đoạn kết nối tùy thời điểm reject và cách xử lý HTTP; cần kiểm thử với client thật.

### 7.2. Điểm cần xác minh trước triển khai

1. **Route matching:** location /uploads/ có khớp đúng endpoint upload thật không? Có route khác dễ đi vòng không?
2. **Đơn vị:** 256k, 1m, 20m cần được xác nhận theo semantics phiên bản NGINX và acceptance tests.
3. **Header limits:** cấu hình riêng cho request-line/header fields và buffers theo nhu cầu.
4. **Temporary files:** NGINX có quyền ghi và dung lượng/quotas đủ, không để đầy root filesystem.
5. **Timeout:** client_body_timeout không đo toàn thời gian upload; cần tổng ngân sách ở ứng dụng hoặc hệ thống khác nếu nghiệp vụ yêu cầu.
6. **Upstream:** app cũng có giới hạn tương thích; NGINX không bảo đảm body giải nén ở backend nhỏ.
7. **TLS/SNI:** certificate của api.example.test phải hợp lệ; test size limit qua đúng HTTPS endpoint.
8. **Logs:** request_length hữu ích nhưng không phải độ dài decompressed; không log raw Authorization, Cookies hay body.
9. **Validation:** sử dụng cấu hình/phiên bản thực và kiểm tra cú pháp trước rollout; chạy positive/negative tests có giới hạn.

### 7.3. Vì sao 413 ở proxy không phải lúc nào cũng đến backend?

Nếu edge/proxy **từ chối trước khi proxy_pass**, application có thể **không nhìn thấy request** và không có application log tương ứng. Khi điều tra, cần kiểm tra **access/error logs tại nơi trả 413**, chứ không kết luận gateway bị bypass chỉ vì backend không ghi event.

Ngược lại, nếu proxy cho qua mà ứng dụng từ chối do limit nhỏ hơn, HTTP status do backend tạo có thể được proxy chuyển về client. Correlation theo **request ID/tracing và ingress logs** giúp xác định chính xác nơi kiểm soát được thực thi.

## 8. Kiểm soát streaming: không chờ đọc xong mới kiểm tra

Một sai lầm phổ biến là **đọc toàn bộ request body vào RAM** rồi mới so sánh kích thước. Cách đó để request lớn tiêu tốn bộ nhớ **trước khi policy có tác dụng**.

Pseudocode cho application/gateway streaming có giới hạn:

~~~text
policy = lookupVerifiedRoutePolicy(route, identity)

if declaredContentLength exists and declaredContentLength > policy.maxBodyBytes:
    reject(413)

bytesReceived = 0
for chunk in parserProvidedRequestBodyStream:
    bytesReceived += chunk.byteLength

    if bytesReceived > policy.maxBodyBytes:
        cancelParsingAndStorage()
        releaseTemporaryResources()
        reject(413)

    writeToBoundedSink(chunk)

finishValidation()
~~~

**Đây là pseudocode nguyên tắc**, không phải một HTTP parser thay thế cho thư viện/framework. Muốn triển khai đúng cần:

- Dùng body stream **sau khi HTTP stack đã xử lý framing**, không tự ghép TCP bytes.
- Giới hạn **bytes thực nhận** kể cả khi không có Content-Length.
- Giới hạn **buffers** và khả năng ghi xuống sink (backpressure).
- Có xử lý **cleanup file tạm, rollback transaction, release quotas và cancel upstream** khi vượt ngưỡng.
- Biết **điểm nào đã tạo side effect**, vì một phần dữ liệu có thể đã được ghi trước khi phát hiện quá limit.
- Kiểm tra **Content-Encoding** ở lớp giải nén, không nhầm raw bytes với decoded bytes.
- Có chính sách **response/connection draining** theo giao thức/HTTP stack, tránh phá lệch ranh giới request trên keepalive connection.

### 8.1. Bảo vệ khi Content-Length không đáng tin

Content-Length có thể vắng, sai hoặc không áp dụng theo cách người viết code giả định. Đừng tạo buffer với kích thước client khai mà không áp **trần phân bổ** và kiểm tra điều kiện hợp lệ.

Ví dụ nguy hiểm về mặt thiết kế: cấp ngay một mảng RAM với độ lớn do header chưa xác minh quyết định. Thiết kế an toàn hơn là **bounded streaming reads** và phân bổ bộ nhớ có giới hạn phù hợp với workload.

### 8.2. Dữ liệu đã bị ứng dụng tiêu thụ trước khi reject

Trong API xử lý streaming upload, nếu từng chunk được ghi ngay vào storage chính, việc reject ở chunk cuối có thể để lại **partial object**. Cần:

- Ghi vào **temporary/quarantine area** trước khi xác thực tổng thể và commit.
- Sử dụng **atomic move/commit** hoặc protocol application đã hỗ trợ resumable upload.
- Xóa hoặc expire dữ liệu tạm sau abort; theo dõi cleanup failure.
- Không công khai object chưa qua **size/type/authorization/malware checks** khi quy trình yêu cầu.

Đặt limit có ý nghĩa nhất khi **hệ thống biết cách hủy an toàn** một request vượt ngưỡng.

## 9. Payload nén và decompression bomb

Một payload sử dụng **Content-Encoding** như gzip có thể nhỏ trên mạng nhưng giải nén ra dữ liệu lớn. Ngoài kích thước, **CPU và thời gian giải nén** cũng là tài nguyên phải giới hạn.

~~~mermaid
flowchart LR
    W["Encoded HTTP body: 100 KiB"] --> D["Decompressor"]
    D --> B["Decoded body: nhiều MiB"]
    B --> P["JSON/XML Parser"]
    P --> O["Object graph và nghiệp vụ"]
    W -. "Encoded bytes cap" .-> G["Defense budgets"]
    D -. "Decoded bytes/ratio/time cap" .-> G
    P -. "Depth/items/CPU cap" .-> G
~~~

### 9.1. Những hạn mức cần tách

| Ngưỡng | Mục đích | Nhầm lẫn cần tránh |
| --- | --- | --- |
| **Max compressed body bytes** | Không nhận quá nhiều dữ liệu truyền vào | Không ngăn payload nhỏ nở rất lớn |
| **Max decompressed bytes** | Giới hạn dữ liệu sau giải nén | Phải đo **trong khi giải nén**, không tạo toàn bộ kết quả trước |
| **Max expansion ratio** | Phát hiện tình huống nén quá chặt bất thường | Có thể false positive với dữ liệu lặp hợp lệ; dùng cùng trần decoded size |
| **Max nesting/recursion depth** | Hạn chế parser tạo cấu trúc quá sâu | Body nhỏ vẫn có thể gây chi phí parse lớn |
| **CPU/time budget** | Ngăn xử lý vô hạn hoặc thuật toán giải nén quá tốn | Timeout không đồng nghĩa thư viện tự giải phóng bộ nhớ |
| **Max aggregate in-flight decoded bytes** | Không để nhiều request cùng dùng hết RAM | Per-request limit một mình chưa đủ |

Nếu định dạng hỗ trợ nhiều lớp nén/encoding, cần policy cho **số lớp giải mã** và kiểm tra mỗi bước. Không tự động tin extension file hay Content-Type để quyết định giải nén.

### 9.2. XML, JSON và dữ liệu phức tạp

Một request có thể ít bytes nhưng parser tạo nhiều đối tượng do:

- JSON arrays rất dài hoặc **nested objects** sâu.
- XML entities/references nếu parser cho phép cơ chế không cần thiết.
- Protobuf hoặc định dạng binary có các trường lặp/số lượng phần tử lớn.
- GraphQL query body nhỏ nhưng dẫn tới **fan-out hoặc độ phức tạp tính toán lớn**.

Giới hạn body là lớp đầu tiên; vẫn cần **schema validation, depth/item count, query complexity, timeouts và DB/work quotas**. Với XML, cấu hình parser để **vô hiệu hóa external entity resolution và các tính năng không cần thiết** theo threat model, không chỉ tăng max body.

## 10. Multipart/form-data và file upload

Với multipart, **total request size** gồm boundary và metadata của từng part; một form có nhiều field/file có thể tiêu thụ nhiều tài nguyên hơn chỉ số “file lớn nhất”.

### 10.1. Bộ giới hạn cho upload

| Control | Mục tiêu |
| --- | --- |
| **Max total multipart body** | Tránh tổng request vượt ngân sách |
| **Max file count** | Tránh hàng chục nghìn file nhỏ gây overhead |
| **Max per-file size** | Ngăn một file vượt nhu cầu nghiệp vụ |
| **Max field count/value length** | Giới hạn metadata và parser allocations |
| **Max filename/part header length** | Tránh header của part cực dài |
| **Memory-to-disk threshold** | Xác định khi nào ghi tạm thay vì giữ trong RAM |
| **Storage quota và lifetime** | Không để uploads không hoàn tất lấp đầy disk/bucket |
| **Content validation** | Kiểm tra file type/magic bytes/format theo nghiệp vụ |
| **Malware scanning/quarantine** | Giới hạn tác động của tệp không đáng tin theo chính sách |

**client_max_body_size 20m** ở reverse proxy không có nghĩa ứng dụng tự giới hạn mỗi file ở 20 MiB, số file hay metadata. Ứng dụng/framework multipart parser cần cấu hình riêng và có test.

### 10.2. Xử lý filename và định dạng

- Không tin **filename** do client tự đặt làm đường dẫn lưu trực tiếp.
- Chuẩn hóa tên và dùng ID do server cấp; chống path traversal ở lớp storage.
- Kiểm tra Content-Type nhưng **không chỉ dựa vào giá trị do client gửi**.
- Giới hạn số trang/frames/pixels khi giải mã PDF/ảnh hoặc các định dạng cần parse sâu.
- Tách quyền upload với quyền **đọc hoặc thực thi** tệp.
- Giới hạn thời gian lưu dữ liệu tạm và xử lý file scan failures có kiểm soát.

Một request vừa đúng 20 MiB nhưng tạo **file giải nén/ảnh giải mã** cực lớn vẫn cần các ngưỡng theo định dạng.

### 10.3. Upload lớn qua object storage

Khi tệp hợp lệ có thể tới hàng gigabyte, kiến trúc tốt hơn thường là **upload trực tiếp tới object storage** bằng quyền tạm thời, thay vì đưa toàn bộ bytes qua API workers:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API service
    participant S as Object storage
    participant V as Validation / Scanner
    C->>A: Xin quyền upload với metadata
    A-->>C: Cấp upload authorization scope/time limit
    C->>S: Upload theo cơ chế được phê duyệt
    S-->>A: Upload completion event / callback
    A->>V: Kiểm tra kích thước, loại, quyền và nội dung
    V-->>A: Pass / quarantine / reject
    A-->>C: File sẵn sàng hoặc lý do từ chối
~~~

**Signed upload URL không mặc nhiên bảo đảm kích thước**. Tùy dịch vụ/storage API, cần cấu hình điều kiện kích thước, method, key prefix, content type, expiration và quyền upload trong phạm vi tính năng thực hỗ trợ. Sau upload, phải **đo kích thước thực của object**, kiểm tra checksum khi phù hợp và chỉ publish sau validation.

Không dùng một URL ghi tùy ý vào mọi object trong bucket. Hạn chế **identity, key prefix, TTL, số lần dùng và tenant quota** khi có khả năng.

## 11. gRPC, WebSocket và các network services không phải REST

### 11.1. gRPC

gRPC dùng framing riêng cho các messages và thường chạy qua HTTP/2; các message có thể được nén tùy cấu hình. Cần phân biệt:

- **Max receive message size** tại gRPC server/client theo framework và phiên bản.
- **HTTP/2 transport limits** và gateway body limits.
- **Max metadata/header list size**.
- **Unary RPC** có một request message theo semantics của phương thức, khác **client/bidirectional streaming** có nhiều messages.
- **Per-message cap, aggregate stream cap và stream lifetime/rate** đều có giá trị độc lập.
- **RPC deadline, cancellation, concurrent streams** hạn chế việc giữ worker lâu.

Một gRPC request có thể trả **gRPC status như RESOURCE_EXHAUSTED** thay vì một HTTP 413 được phơi bày trực tiếp, phụ thuộc tầng kiểm tra, framework và giao thức. Không mặc định quan sát HTTP status là đủ để biết lỗi kích thước gRPC.

### 11.2. WebSocket

Sau HTTP Upgrade hoặc thiết lập WebSocket tương ứng, giới hạn body HTTP ban đầu **không tự đảm bảo** từng **WebSocket frame/message** đều bị giới hạn.

Các control cần có:

- Max frame size và **max reconstructed message size** qua nhiều frames.
- Giới hạn số messages hoặc bytes trên thời gian theo identity/connection.
- Thời gian idle, heartbeat và max connection lifetime khi nghiệp vụ cần.
- Giới hạn aggregate buffers của các clients đồng thời.
- Backpressure cho client gửi nhanh hoặc nhận chậm.
- Authorization theo channel/event, không chỉ vào được WebSocket là được gửi mọi message.

### 11.3. TCP binary protocol

Một network service tùy chỉnh có thể dùng **length-prefixed messages**:

~~~text
Message:
  [4-byte length field][payload bytes]

Server logic:
  validate length <= route/protocol maximum
  bound allocation and stream reads
  verify actual bytes and framing
  reject malformed/incomplete frame
~~~

Không phân bổ mảng/byte buffer trực tiếp theo length field chưa xác thực. Bảo vệ **integer bounds, signed/unsigned conversions, cumulative totals** và số messages trong một session.

### 11.4. UDP và IoT/datagram services

UDP không có stream body giống HTTP. Tuy nhiên, ứng dụng vẫn cần giới hạn kích thước datagram, fragments/reassembly, số messages và chi phí parser. Với các giao thức có thể phản hồi lớn hơn request, phải xét nguy cơ **reflection/amplification**; size limit chỉ là một phần cùng với xác thực nguồn hợp lý, rate limiting và chính sách mạng.

## 12. Status code, lỗi và hợp đồng với API client

| HTTP status | Ngữ cảnh thường gặp | Hướng xử lý |
| --- | --- | --- |
| **400 Bad Request** | Framing/syntax không hợp lệ hoặc lỗi parse chung theo server | Ghi nguyên nhân nội bộ; không lộ parser internals nhạy cảm |
| **413 Content Too Large** | Request body lớn hơn mức server cho phép | Client cần giảm body/chia lô hoặc dùng upload flow được hỗ trợ |
| **414 URI Too Long** | Request target/URI vượt giới hạn | Không đưa payload lớn vào query string; dùng contract thích hợp |
| **415 Unsupported Media Type** | Media type/encoding không được endpoint hỗ trợ | Client chuyển định dạng hợp lệ; đừng dùng để báo mọi trường hợp quá cỡ |
| **422 Unprocessable Content** | Syntax hợp lệ nhưng dữ liệu không đạt quy tắc ngữ nghĩa theo API | Chỉnh nội dung; không đồng nghĩa vượt byte limit |
| **429 Too Many Requests** | Quota hoặc rate limit theo thời gian | Backoff theo hợp đồng; Retry-After nếu có và phù hợp |
| **431 Request Header Fields Too Large** | Một hoặc nhiều header fields lớn quá mức | Giảm cookie/header/metadata hoặc sửa client |
| **503 Service Unavailable** | Dịch vụ tạm không thể xử lý do quá tải/maintenance | Kiểm tra overload policy và retry budget |

**413** là cách phổ biến khi request body vượt giới hạn. Nhưng quan sát thực tế có thể bị ảnh hưởng bởi **kết nối bị reset, gRPC mapping, framework exceptions hoặc proxy tạo HTML error page**. Cần kiểm tra từ client và tại từng hop, không mặc định application luôn nhận request và tự trả 413.

### 12.1. Mẫu phản hồi 413 thân thiện cho client

~~~json
{
  "type": "https://api.example.test/problems/request-too-large",
  "title": "Request body exceeds permitted size",
  "status": 413,
  "detail": "Maximum request body for this endpoint is 1048576 bytes",
  "requestId": "req-demo-006"
}
~~~

Đây là **ví dụ minh họa** định dạng tương tự Problem Details, không phải mọi proxy tự trả JSON như trên. Thông tin limit có thể giúp client sửa request, nhưng có hệ thống cần tránh tiết lộ chi tiết nội bộ; cân bằng giữa usability và thông tin có thể cung cấp công khai.

### 12.2. Có nên retry request bị 413?

Nếu body không được sửa hoặc route không đổi, **retry cùng một request lớn thường tiếp tục bị từ chối**, gây tải vô ích. Client nên:

1. Đọc API contract hoặc max-size được tài liệu hóa.
2. **Giảm batch size, chia chunk ứng dụng hoặc dùng resumable upload** khi được hỗ trợ.
3. Không đổi Content-Length giả để cố vượt limit.
4. Không tự động retry vô hạn; áp backoff và idempotency semantics phù hợp cho các lỗi có thể phục hồi.

**413 không phải 429**; tăng delay nhưng không giảm payload chưa chắc khắc phục được vấn đề.

## 13. Request size limit, rate limit và timeout phối hợp ra sao?

Ba control phải phối hợp chứ không thay thế nhau:

| Control | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Size limit** | Một request được mang bao nhiêu bytes/objects? | Max 1 MiB JSON |
| **Rate limit** | Một identity/tenant có thể gửi bao nhiêu request hoặc bytes trong một khoảng? | 30 requests/s hoặc bytes/min |
| **Concurrency limit** | Bao nhiêu request đồng thời được phép giữ tài nguyên? | Max 100 in-flight requests per route |
| **Timeout/deadline** | Một thao tác có thể giữ tài nguyên bao lâu? | Total request deadline và body read inactivity timeout |
| **Storage/DB quota** | Tác động thực của các request tới backend được phép tới đâu? | 5 GiB files per tenant; DB pool |

### 13.1. Ví dụ sizing tài nguyên

Giả sử gateway cho phép mỗi request body tối đa **2 MiB**, có **300 request bodies** đang được xử lý đồng thời. Nếu hệ thống giữ toàn bộ body trong RAM, riêng dữ liệu body có thể lên tới:

~~~text
2 MiB/request x 300 requests = 600 MiB

Chưa tính:
  - Headers, TLS buffers, HTTP metadata
  - JSON object graphs / decoded data
  - App workers, logs và caches
~~~

Nếu gateway streaming từng chunk 64 KiB, lượng dữ liệu **đang buffer** có thể ít hơn nhiều, nhưng vẫn cần xem concurrency, disk spill, upstream backpressure và decoded payload allocations.

**Không lấy công thức này làm sizing thực tế nếu chưa biết số buffer copies**, shared memory, compression, queue, allocator overhead và hành vi khi client chậm.

### 13.2. Slow uploads

Một client có thể gửi request body dưới 1 MiB **rất chậm** và giữ kết nối hàng phút. Size limit không tự đóng kết nối; cần **client body read timeout, min data-rate policy khi được hỗ trợ, connection quota và tổng deadline** phù hợp.

Ngược lại, timeout quá nhỏ có thể chặn người dùng trên mạng di động yếu khi upload hợp lệ. Phải thử nghiệm với workload và SLO thực, không coi mọi client gửi chậm là attacker.

### 13.3. Requests nhỏ nhưng đắt

Một GraphQL query 2 KiB có thể tạo hàng nghìn truy vấn phụ thuộc, hoặc một API JSON 1 KiB có thể khởi động công việc tính toán lớn. **Body size limit không đo chi phí nghiệp vụ**; cần **query cost, resource quotas, execution timeout, caching, concurrency và authorization**.

## 14. Threat model cho request size ở network service

| Threat / sai lệch | Nguyên nhân hoặc đường tác động | Biện pháp cần kiểm tra |
| --- | --- | --- |
| **Oversized body DoS** | Proxy/app nhận body cực lớn | Early 413, max body tại mọi ingress, streaming bounded reads |
| **Oversized headers/cookies** | Header parser/buffer bị bão hòa | Header count/size limits, 431, cookie/session design |
| **Very long URI/query** | Parser/router/logs tốn tài nguyên | URI/query limits, 414, contract validation |
| **Compressed payload expansion** | Body nén nhỏ giải nén thành dữ liệu khổng lồ | Encoded + decoded size, expansion ratio, CPU/time budget |
| **Deep JSON/XML/protobuf** | Parser dùng nhiều CPU/RAM hoặc recursion | Depth/items/schema limits, hardened parsers |
| **Multipart part flood** | Rất nhiều files/fields nhỏ vượt giới hạn tổng | Part count, per-file limits, total limit, tmp disk quota |
| **Incomplete/slow streaming** | Client giữ connection/buffers kéo dài | Read inactivity timeout, connection/concurrency cap, backpressure |
| **HTTP framing inconsistency** | Proxy/backend hiểu khác nhau về ranh giới request | Standards-compliant parsing, reject ambiguous framing, upgrade tests |
| **HTTP/2/3 multiplex saturation** | Nhiều streams/messages trên một transport connection | Per-stream body/header limits, concurrent streams, aggregate budgets |
| **Bypass proxy size rule** | Origin hoặc gateway khác tiếp nhận request trực tiếp | Network boundary, service auth, policy at every ingress, negative tests |
| **Log/storage exhaustion** | Hệ thống log raw body hoặc tmp files không dọn | Redaction, bounded logs, quota, lifecycle cleanup |
| **Misconfigured per-route exception** | Upload lớn vô tình áp cho /api hoặc anonymous traffic | Explicit route/method auth, config review, tests |
| **Request size false positive** | Giới hạn dưới nhu cầu nghiệp vụ, CDN/proxy khác policy | Per-route baseline, app contract, pilot, error metrics |
| **Retry storm sau 413/5xx** | Client lặp request lớn không thay đổi | Client SDK contract, retry budget, 413 nonretryable |

**Mục tiêu không phải chặn mọi request lớn.** Mục tiêu là **cho đúng tải hợp lệ chạy trong ngân sách**, còn dữ liệu vượt nhu cầu hoặc ngữ nghĩa không hợp lệ phải bị từ chối trước khi tạo tác động lớn.

## 15. Observability: đo được limit nào đã thực thi

### 15.1. Các metrics thiết yếu

| Metric | Ý nghĩa | Cần phân biệt |
| --- | --- | --- |
| **Request body bytes** theo route/method/tenant | Đo phân phối payload và tail size | Wire/decoded/parsed bytes khác nhau |
| **Header bytes/count** | Phát hiện oversized metadata | Header wire compression vs decoded header list |
| **413/414/431 rate** | Số requests bị size policy từ chối | Nơi tạo status: CDN, proxy, gateway, app |
| **File upload size/count** | Xác định hợp đồng upload thực | Partial/failed upload không được nhầm với completed |
| **Compressed/decoded ratio** | Phát hiện expansion lớn | Chỉ có nếu thực sự có decompressor instrumentation |
| **Parser CPU/time/memory** | Phát hiện request nhỏ nhưng tốn tài nguyên | Khác network body bytes |
| **Proxy temporary disk usage** | Tránh file buffering làm đầy volume | Total disk, inode, cleanup age |
| **Active requests/HTTP streams** | Đo tổng bytes có khả năng xử lý đồng thời | TCP connections không đủ cho H2/H3 |
| **Client read timeout/abort** | Phân biệt request quá chậm hoặc bị dở | Không tự quy kết attacker |
| **Backend OOM/GC/worker saturation** | Đo hiệu ứng sau khi qua size policy | Có thể là parser, DB, retry hay bug |
| **Policy drift / route overrides** | Phát hiện giới hạn thay đổi ngoài kế hoạch | Review theo version/env/owner |

### 15.2. Schema log minh họa

~~~json
{
  "timestamp": "2026-11-28T03:40:12Z",
  "requestId": "req-size-006",
  "service": "api.example.test",
  "route": "/api/profile",
  "method": "POST",
  "status": 413,
  "enforcementPoint": "reverse-proxy-01",
  "policyId": "api-profile-body-1m",
  "limitType": "encoded_body_bytes",
  "maxBytes": 1048576,
  "observedBytes": 1310720,
  "bodyFullyReceived": false,
  "identityCategory": "authenticated-user",
  "action": "reject"
}
~~~

Đây là **mẫu schema tự thiết kế**; các trường **observedBytes** và **bodyFullyReceived** có thể không được proxy cung cấp nếu reject sớm theo Content-Length. Nếu log đang ghi **declared Content-Length** thay vì bytes thực nhận, phải đặt tên rõ để tránh hiểu nhầm.

**Không log raw request body, password, Authorization, Cookie, API key hoặc upload file chỉ để debug size limit.** Dùng counters, request ID, policy ID, hash phù hợp khi cần và log có giới hạn truy cập/thời gian lưu.

### 15.3. Tương quan nhiều tầng

~~~text
Client -> CDN -> WAF -> Reverse proxy -> API -> Parser -> Storage

Request ID: req-size-006
CDN:           accepted / recorded encoded bytes
WAF:           inspected relevant portion / action recorded
Reverse proxy: rejected 413 / route-size-policy
API:           no application request log for this ID
Storage:       no object created
~~~

Kịch bản trên **hoàn toàn có thể bình thường**, vì proxy ngăn request trước khi đến API. Không có log backend không đủ để kết luận log bị mất hoặc WAF không hoạt động. Dựa vào **tracing ID, timestamps và mỗi hop's policy outcome**.

## 16. Case study: endpoint JSON bị chặn nhầm sau triển khai gateway

### 16.1. Bối cảnh

Một hệ thống quản lý thiết bị nhận **telemetry batch**. Team ứng dụng định nghĩa payload tối đa **2 MiB** và tối đa **1.000 events/batch**; tuy nhiên gateway mới được cấu hình giới hạn **1 MiB** cho toàn bộ API. Một số thiết bị gửi batch hợp lệ lớn hơn 1 MiB bắt đầu nhận 413.

### 16.2. Evidence giả định

| Evidence | Quan sát | Điều có thể kết luận |
| --- | --- | --- |
| **E1 – API contract** | /api/telemetry/batch cho tối đa 2 MiB encoded body | Gateway 1 MiB không khớp contract |
| **E2 – reverse proxy log** | 413 tăng ở route telemetry, kèm policy 1 MiB | Proxy có thể đang từ chối trước ứng dụng |
| **E3 – application log** | Không thấy request ID của các sự kiện 413 | Phù hợp với việc reject ở proxy, không tự là mất log |
| **E4 – client telemetry** | Payload bị từ chối phần lớn 1,2–1,8 MiB | Có nhóm request phù hợp ngưỡng contract nhưng vượt proxy |
| **E5 – baseline resource** | API/DB chịu được 2 MiB khi số batch hợp lý | Cần giữ quota/CPU/item count trước khi nới edge |
| **E6 – staging tests** | 2 MiB được chấp nhận, >2 MiB bị từ chối, 1.000 events limit hoạt động | Policy alignment được xác nhận trong phạm vi test |

Đây là **case giả định**, không phải dữ liệu production. Cần xác minh **bytes đang đo theo encoded hay decoded representation**, vì một số thiết bị có thể nén telemetry.

### 16.3. Cách xử lý

1. Xác định **route, method và body representation** của contract, không đổi global limit tùy tiện.
2. Cấu hình **ngoại lệ hẹp cho /api/telemetry/batch**, vẫn giữ baseline nhỏ cho các endpoint khác.
3. Kiểm tra backend có **decoded-size, event-count và per-device quotas**, không chỉ dựa vào 2 MiB.
4. Test payload đúng ngưỡng, dưới và trên ngưỡng, có Content-Length, không biết trước độ dài, compressed nếu hỗ trợ.
5. Triển khai canary, đo 413 và metrics backend, giám sát **giảm false positive** mà không tăng OOM/CPU.
6. Cập nhật API documentation và SDK batching/retry behavior; 413 không nên được retry y hệt vô hạn.

**Bài học:** giới hạn đúng phải theo **contract và sức chịu tải của backend**, không chỉ copy một cấu hình tối thiểu cho mọi route.

## 17. Case study: payload nén nhỏ làm parser quá tải

### 17.1. Bối cảnh

Một API cho phép **Content-Encoding: gzip** để tiết kiệm bandwidth. Proxy giới hạn body truyền trên mạng ở **1 MiB**, nhưng ứng dụng giải nén body mà không kiểm tra bytes decoded. Một request dưới 100 KiB tạo dữ liệu nhiều chục MiB, làm độ trễ/GC tăng và gây áp lực bộ nhớ khi nhiều request đồng thời.

### 17.2. Dòng điều tra

~~~mermaid
flowchart TD
    A["Encoded body < 1 MiB"] --> B["Proxy body size check: PASS"]
    B --> C["Application decompress"]
    C --> D["Decoded bytes rất lớn"]
    D --> E["JSON parser + object allocation"]
    E --> F["CPU/RAM pressure / queue latency"]
    F --> G["Service degradation"]
    D -. "Chặn bằng decoded-size budget" .-> M["Mitigation"]
    E -. "Depth/items/time limits" .-> M
    A -. "Concurrency/bytes quota" .-> M
~~~

### 17.3. Giải pháp có kiểm soát

- Xác định application có thực sự cần nhận compressed request bodies không; nếu không, **từ chối Content-Encoding không được hỗ trợ** theo hợp đồng.
- Nếu cần, dùng **streaming decompressor** và dừng khi vượt **max decoded bytes**.
- Đặt **time/CPU, JSON depth, item count** và ngân sách bộ nhớ hợp lý.
- Giới hạn tổng **concurrent decompression operations** để tránh khuếch đại áp lực.
- Từ chối/quarantine request trước khi tạo side effects; cleanup buffers/file tạm.
- Có telemetry riêng cho compressed và decoded size, không suy luận từ Content-Length.

Không chỉ tăng RAM hoặc max body size để giải quyết vấn đề. Giới hạn đầu vào cần được thực thi đúng lớp **sau giải nén và trước parser**.

## 18. Checklist kiểm thử có quyền

Các kiểm thử dưới đây áp dụng cho **staging/lab hoặc hệ thống đã được chủ sở hữu cho phép**, có giới hạn requests, bytes, concurrency và thời gian. Không thử các payload gây kiệt quệ tài nguyên trên hệ thống công cộng hoặc bên thứ ba.

| Test | Mô tả an toàn | Kết quả kỳ vọng |
| --- | --- | --- |
| **P1 – body nhỏ hợp lệ** | JSON dưới limit, đúng schema | Thành công; ghi đúng policy/request ID |
| **P2 – sát ngưỡng** | Body đúng limit bytes theo định nghĩa đã ghi | Xử lý đúng; không off-by-one |
| **N1 – vượt ngưỡng một byte** | Body lớn hơn limit một byte trong fixture | 413 hoặc error mapping theo contract; không tạo side effect |
| **N2 – Content-Length lớn** | Request test khai và gửi body vượt limit | Reject sớm nếu công nghệ hỗ trợ, không allocate quá mức |
| **N3 – unknown length / stream** | Staging client gửi body theo kiểu không biết tổng trước | Limit vẫn được thực thi qua bytes thực nhận |
| **N4 – encoded vs decoded** | Fixture gzip nở lớn, trong phạm vi lab | Decoded cap/ratio/time budget từ chối đúng |
| **N5 – headers** | Test header list vượt chính sách trong lab | Bị từ chối theo header policy, không nhầm body limit |
| **N6 – URI/query** | Request target vượt limit staging | 414 hoặc error behavior được xác nhận |
| **N7 – multipart count** | Nhiều file/fields nhỏ vượt count limit | Parser từ chối, cleanup file tạm |
| **N8 – per-file size** | Một file part vượt limit đã cấu hình | Không persist file vượt policy |
| **N9 – JSON nesting/items** | Fixture hợp lệ về bytes nhưng vượt depth/count | Validation từ chối mà không tràn RAM/stack |
| **P3 – HTTP/2 hoặc H3** | Tập request trong nhiều streams có giới hạn | Body/header limits trên từng stream, aggregate budget hoạt động |
| **N10 – gRPC/WebSocket** | Message test vượt per-message limit | Từ chối theo protocol, giải phóng session resources |
| **N11 – direct origin bypass** | Kiểm thử đường truy cập origin nội bộ được cấp quyền | Không thể vượt size policy do bỏ qua edge |
| **P4 – upload hợp lệ** | Tệp đúng quota, authorization và content policy | Upload/scan/commit đúng, không gián đoạn |
| **F1 – abort giữa upload** | Client lab đóng kết nối sau một phần body | Temp data được cleanup, quota được hoàn lại đúng |
| **O1 – logs/alerts** | Một request hợp lệ và một request vượt giới hạn | Ghi đúng policy/hop/status, không lộ secrets |

### 18.1. Những tiêu chí chấp nhận tối thiểu

Một thay đổi size policy đạt yêu cầu khi:

- Các route có **định nghĩa kích thước, đơn vị, ownership và ngoại lệ** rõ ràng.
- Request đúng contract không bị từ chối sai ở bất kỳ hop nào.
- Request vượt giới hạn được từ chối **trước hoặc trong lúc đọc/parse có ràng buộc**, không chiếm RAM/disk không giới hạn.
- **Compressed/decoded/multipart/message limits** được kiểm thử ở đúng chặng có xử lý các dạng dữ liệu đó.
- **HTTP/2/3, gRPC/WebSocket, VPN/private ingress và direct-origin access** không tạo bypass ngoài policy.
- Tài nguyên tạm và quota được **giải phóng sau abort**, không có partial object được công khai.
- Có **metrics về 413/431/414 và resource usage**, phân biệt edge/proxy/backend enforcement.
- Có owner, rollout canary, rollback và tiêu chí theo dõi false positive.

## 19. Runbook xử lý lỗi 413 hoặc resource exhaustion

### Bước 1 — Xác định chính xác nơi trả lỗi

Thu **request ID, timestamp, method/route, status, content type/encoding và hop log**. Kiểm tra CDN/WAF, reverse proxy, API gateway, application và storage. Nếu API không thấy request, có thể đã bị từ chối sớm ở proxy.

### Bước 2 — Phân biệt loại limit

Đó là **body**, **header**, **URI**, **multipart file**, **decoded payload**, **gRPC message** hay **quota theo tenant**? Nếu client thấy 413 nhưng body nhỏ, kiểm tra header/request-framing, bytes thực nhận, middleware, encoding và rule route cụ thể.

### Bước 3 — Đối chiếu contract với config

So sánh **accepted representation** và hạn mức tại từng hop. Một tầng đo decoded body có thể lớn hơn encoded bytes ở edge. Kiểm tra thay đổi phiên bản hoặc cấu hình được triển khai theo canary.

### Bước 4 — Xác minh backend capacity

Đừng nới limit chỉ để hết 413. Đo **RAM, temporary disk, parser CPU, DB pool, object storage quotas, in-flight requests**; xem liệu backend xử lý ổn định ở kích thước lớn hơn không.

### Bước 5 — Chọn giải pháp ít rủi ro nhất

Các lựa chọn: **giảm batch size ở client, chia chunk ở application, dùng resumable/direct upload, ngoại lệ hẹp theo route, áp decoded limit** hoặc nâng capacity có kiểm soát. Không mở unlimited trên mọi API và không tắt WAF/IDS vì một endpoint upload cần body lớn.

### Bước 6 — Kiểm tra lại toàn đường đi

Thử request ngay dưới/đúng/trên limit, có/không khai Content-Length, dạng nén nếu được hỗ trợ, multipart, HTTP/2/3 và trường hợp client abort. Xác nhận **không phát sinh side effect khi reject**.

### Bước 7 — Theo dõi sau thay đổi

Giám sát 413 rate, client complaints, latency, CPU/RAM/tmp disk, số request xử lý thành công, storage usage và bất thường theo tenant. Ghi **config revision, ticket, owner, phạm vi và điều kiện rollback**.

## 20. Những nhầm lẫn thường gặp

1. **“Body limit 1 MiB là toàn bộ request không thể lớn hơn 1 MiB.”** Headers, URI, framing và parser overhead không nhất thiết nằm trong body count.
2. **“Kiểm tra Content-Length là đủ.”** Có request streaming/unknown length và dữ liệu khai sai; phải đo bytes thực nhận.
3. **“HTTP/2 dùng Transfer-Encoding: chunked như HTTP/1.1.”** H2/H3 có stream framing riêng.
4. **“Một HTTP/2 connection chỉ có một request.”** Multiplexing cho phép nhiều concurrent streams.
5. **“client_body_buffer_size là body size hard limit trong NGINX.”** Đây là kích thước buffer, không thay client_max_body_size.
6. **“client_body_timeout là tổng thời gian upload.”** Trong NGINX nó chủ yếu kiểm tra khoảng không hoạt động khi đọc body.
7. **“WAF inspection limit bằng request acceptance limit.”** Một số WAF có thể bỏ qua việc inspect phần vượt ngưỡng nhưng vẫn forward, tùy policy.
8. **“Đặt size limit tại CDN thì origin không cần kiểm tra.”** Direct origin/private ingress có thể bypass edge.
9. **“Một payload gzip 100 KiB chắc chỉ tốn 100 KiB RAM.”** Giải nén và parse có thể làm dữ liệu lớn hơn nhiều.
10. **“Multipart tổng 20 MiB tự giới hạn số files và các field.”** Cần count/per-part/depth limits riêng.
11. **“Tăng limit là luôn khắc phục 413 đúng cách.”** Có thể cần thay hợp đồng client, chia lô hoặc sửa endpoint.
12. **“413 là rate limiting.”** 413 nói tới request content size; 429 mới liên quan quá nhiều requests/quota theo policy.
13. **“Không thấy log ở app nghĩa request không hề đến hệ thống.”** Reverse proxy có thể reject trước khi proxy_pass.
14. **“Chỉ JSON schema validation là đủ chống parser exhaustion.”** Cần giới hạn bytes, depth, item count, time và số request đồng thời.
15. **“File upload đúng byte limit thì chắc chắn an toàn.”** Còn content validation, malware scanning, storage quota và authorization.
16. **“Một request bị timeout chắc chắn không tạo dữ liệu.”** Backend có thể còn chạy hoặc đã tạo partial object.
17. **“Client khai Content-Type: image/png thì có thể tin.”** Cần kiểm tra nội dung thực theo policy.
18. **“Limit 1 MiB áp được mọi service.”** Telemetry, gRPC stream, upload và REST JSON có nhu cầu khác nhau.
19. **“Body limit thay cho concurrency/rate limit.”** Nhiều request nhỏ vẫn có thể cạn tài nguyên.
20. **“Đã có 413 nghĩa storage sạch.”** Nếu request bị reject sau partial write, phải cleanup/rollback.

## 21. Bài tập vận dụng

### Bài 1 — Tìm giới hạn hiệu lực

Một tuyến API có CDN limit **10 MiB**, reverse proxy **4 MiB**, gateway **2 MiB** và application **1 MiB**. Tất cả cùng đo **encoded HTTP body bytes**. Request 1,5 MiB bị chặn ở đâu?

**Gợi ý:** application nếu các hop trước đều forward và cùng đếm một đại lượng. Hạn mức hiệu lực là 1 MiB; đừng kết luận dựa trên phép min nếu một tầng đo decoded bytes còn tầng khác đo encoded.

### Bài 2 — Content-Length không có

Một client upload bằng HTTP/1.1 chunked framing và không khai tổng body size trước. Gateway đang chỉ kiểm tra Content-Length. Cần sửa thiết kế nào?

**Gợi ý:** giới hạn bytes thực nhận sau HTTP framing trong lúc streaming, có trần buffer/storage, timeout và cleanup. Không cần viết parser chunked mới nếu stack HTTP đã hỗ trợ.

### Bài 3 — Payload nén phình to

Body truyền 80 KiB, sau giải nén là 32 MiB. Edge limit 1 MiB cho encoded body và không giải nén; app dùng 64 MiB RAM để parse. Có vi phạm edge size policy không, và cần control nào?

**Gợi ý:** có thể **không** vi phạm encoded cap, nhưng app cần **decoded-size/ratio/depth/concurrency budgets**. Edge và app phải khai rõ loại bytes mình đo.

### Bài 4 — HTTP/2 stream saturation

Một connection HTTP/2 duy nhất chứa 50 concurrent requests, mỗi request 1 MiB. Connection limit = 2 có bảo vệ đủ application không?

**Gợi ý:** không. Cần **per-stream body size**, concurrent stream/request budget, aggregate buffer/upstream limits và service quotas.

### Bài 5 — Multipart upload

API cho upload tối đa 5 tệp, mỗi tệp 10 MiB, tối đa 25 MiB total request. Một client gửi 100 tệp 1 KiB. Vì sao vẫn cần từ chối?

**Gợi ý:** tổng bytes nhỏ nhưng **file count** vượt hợp đồng và gây parser/storage overhead; phải kiểm tra count độc lập với total body bytes.

### Bài 6 — Lỗi 413 sau rollout

Một ứng dụng telemetry bắt đầu tăng 413 sau khi chuyển sang gateway mới. Contract cho phép 2 MiB, gateway chỉ cho 1 MiB. Có nên nâng toàn bộ API lên 10 MiB để hết lỗi?

**Gợi ý:** không. Xác minh contract và backend capacity, áp **ngoại lệ hẹp theo route**; kiểm thử ngưỡng, event count và compression, giữ baseline thấp cho API khác.

### Bài 7 — Thiết kế threat → control → evidence

Cho hệ thống **CDN/WAF → NGINX → API gateway → Java service → object storage**, hỗ trợ REST JSON, GraphQL, gRPC và file upload. Hãy xây dựng ma trận:

- Mỗi route đo **encoded body, decoded body, header/URI, part/message count và parser cost** ở lớp nào?
- Điểm nào trả **413/431/414**, và làm sao biết response đến từ proxy hay application?
- Request không có Content-Length, HTTP/2 streams và compressed body được kiểm tra thế nào?
- Có **rate/concurrency/deadline/storage quotas** nào bổ sung per-request size limit?
- Làm sao **không lộ secrets** trong logs và xóa partial uploads khi reject?
- Những **positive/negative/abort tests** nào chứng minh policy đúng với request hợp lệ lẫn trường hợp quá ngưỡng?

**Gợi ý:** bắt đầu từ dữ liệu đầu vào thực tế và hợp đồng API, chọn limit theo **đơn vị chính xác** và **trust boundary**, rồi thiết kế telemetry để xác minh tại từng hop.

## 22. Checklist triển khai cho đội API, Network và Security

| Câu hỏi | Evidence mong đợi |
| --- | --- |
| Có inventory route/method và kích thước payload hợp lệ? | API contract, p95/p99 request sizes, owner |
| Đã định nghĩa encoded, decoded, header, URI và object-count limits? | Policy-as-code có đơn vị và phạm vi |
| Có bảo vệ khi body không có hoặc có Content-Length không đáng tin? | Streaming limit tests và reject logs |
| HTTP/2/3 có limit theo stream và aggregate concurrency? | Gateway config, metrics streams/requests |
| WAF inspect toàn bộ phần payload cần thiết hay có bypass policy? | WAF inspection behavior tests |
| Direct-origin/private access có cùng size controls? | Network restrictions + negative tests |
| NGINX client_max_body_size có đúng location? | Config review và 413 tests từng route |
| client_body_buffer_size/temp disk có quota? | Proxy memory/disk monitoring, cleanup tests |
| Compressed request có decoded-size/time policy? | Decompression fixture và metrics encoded/decoded |
| Multipart có per-file/count/field limits? | Upload parser tests và storage quotas |
| gRPC/WebSocket có per-message và per-stream policy? | Protocol-specific tests |
| Client có contract và hướng xử lý 413? | SDK documentation, retry budget và batch guidance |
| Có rate/concurrency/deadline cùng với size limit? | Capacity/overload plan, measured SLO |
| Logs có request ID, policy ID và nơi trả reject? | SIEM dashboard, sanitized event sample |
| Có bảo vệ private data trong logs/temporary files? | RBAC, encryption/retention, redaction |
| Có chủ sở hữu, canary, rollback và theo dõi false positive? | Change ticket, validation report |

## 23. Tổng kết

**Request size limit cho network service** là cơ chế phòng vệ giúp mỗi request chỉ tiêu thụ lượng dữ liệu và tài nguyên phù hợp với **hợp đồng API và năng lực hệ thống**. Để triển khai đúng cần phân biệt **URI, headers, encoded body, decoded body, multipart file/part, gRPC message, WebSocket message và số concurrent HTTP streams**, bởi một con số max body size không bao quát mọi hình thức cạn kiệt tài nguyên.

Trong kiến trúc **SECURITY_NETWORK_SECURITY**, nên kiểm soát đầu vào theo nhiều lớp: **CDN/WAF từ chối sớm khi có thể, reverse proxy kiểm tra framing/size/buffer, API gateway áp quota theo route và identity, application giới hạn parser/decoded content, storage kiểm soát tệp và quyền truy cập**. Kết hợp size limits với **rate limiting, connection/concurrency controls, timeouts, backpressure, IDS/IPS và giám sát mạng** để không bỏ sót các request nhỏ nhưng nhiều hoặc request lớn và chậm.

Một chính sách được xem là hiệu quả khi **request hợp lệ được phục vụ đúng SLO**, **request vượt ngưỡng bị chặn và giải phóng tài nguyên an toàn**, **không có đường bypass ngoài chính sách**, và **có đủ log, metrics, tests cùng owner để chứng minh nơi giới hạn được áp dụng và xử lý những ngoại lệ hợp lệ**.
