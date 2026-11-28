# Đọc HTTP request trong môi trường được phép: từ packet capture đến diễn giải đúng bằng chứng

Trong chương **Packet capture và phân tích lưu lượng** thuộc module **SECURITY_NETWORK_SECURITY**, khả năng đọc một **HTTP request** giúp người học hiểu cách ứng dụng trao đổi qua mạng, tìm lỗi proxy/firewall, điều tra sự kiện và đối chiếu các hoạt động được phép với log ở lớp mạng, ứng dụng và bảo mật. Một HTTP request có thể chứa **method, request-target, HTTP version, header fields và body**, nhưng các thành phần đó **không mặc nhiên hiện ra dưới dạng văn bản trong mỗi packet**.

Hai nguyên tắc xuyên suốt bài:

1. **Chỉ thu thập và phân tích lưu lượng do bạn sở hữu hoặc được ủy quyền rõ ràng.** Lab sử dụng **localhost và dữ liệu giả**, không thu lén thông tin đăng nhập, cookie, request payload của người khác.
2. **Tách quan sát trực tiếp khỏi suy luận.** Một TCP packet không tương đương một HTTP request; TLS ClientHello không chứa HTTP URL/path; HTTP 200 nằm trong response, không phải request; proxy log có thể thấy nhiều hơn cảm biến mạng thụ động.

**Sau bài học, bạn có thể:**

- Đọc đúng **HTTP/1.1 request line, Host, headers, CRLF, message framing và body**.
- Phân biệt **Ethernet frame → IP packet → TCP segment → TCP byte stream → HTTP message**, hiểu TCP reassembly và retransmission.
- Dùng **curl, tcpdump, Wireshark, TShark, Zeek, ứng dụng/proxy logs** trên hệ thống được cấp phép để đối chiếu cùng một request.
- Giải thích khác biệt giữa **HTTP/1.1 plaintext, HTTPS, HTTP/2 và HTTP/3**, cũng như giới hạn khi không có điểm giải mã được ủy quyền.
- Xác định cách **forward/reverse proxy, load balancer, NAT, WAF và service mesh** thay đổi traffic và ranh giới tin cậy.
- Diễn giải **URI encoding, Content-Length, Transfer-Encoding: chunked, JSON, form/multipart, compression và keep-alive**.
- Thiết lập **lab loopback**, tạo request và đọc PCAP/log an toàn, kèm phép kiểm chứng và xử lý sự cố.

Các hostname **.example** và địa chỉ trong dải dành cho tài liệu là giá trị minh họa; không có credential hay dịch vụ bên ngoài thực nào cần được truy cập.

## 1. “Môi trường được phép” nghĩa là gì?

**PCAP có thể chứa nhiều dữ liệu hơn dự kiến**: URL query, session ID, Cookie, Authorization header, request body, API key hoặc dữ liệu người dùng. Quyền truy cập một máy chủ **không tự động đồng nghĩa** có quyền ghi lại lưu lượng của tất cả người dùng đi qua máy chủ đó.

| Bối cảnh | Cách làm phù hợp | Ranh giới cần giữ |
| --- | --- | --- |
| **localhost lab** | Client/server do bạn tạo, dữ liệu giả | Chỉ loopback và port lab |
| **staging do tổ chức sở hữu** | Ticket, owner, capture scope và thời gian được duyệt | Không lấy production data ngoài phạm vi |
| **production troubleshooting** | Ưu tiên logs/metrics đã redacted; capture hẹp khi được phê duyệt | RBAC, retention, bảo quản bằng chứng |
| **third-party/SaaS** | Dùng API/log do đối tác cấp quyền, phối hợp qua quy trình | Không sniff hay cố giải mã traffic của người khác |
| **TAP/SPAN tại mạng doanh nghiệp** | Sensor được cấp quyền, có data governance | Không lấy traffic nhân viên ngoài mục đích được duyệt |

### 1.1. Tối thiểu hóa thu thập

- **Phạm vi:** xác định interface, IP/port, giao thức, thời gian và chủ hệ thống.
- **Nội dung:** chỉ dùng dữ liệu test, không dùng password/token/cookie thật.
- **Lưu trữ:** PCAP/log có RBAC, mã hóa khi cần, retention và dọn dẹp theo chính sách.
- **Bằng chứng:** ghi UTC timestamps, packet loss, capture filter, tool version và nguồn dữ liệu.
- **Ngừng xử lý:** khi thấy dữ liệu nhạy cảm ngoài phạm vi, không sao chép ra chat/ticket; xử lý theo quy trình được phê duyệt.

### 1.2. Quan sát không đồng nghĩa được phép khai thác thông tin

Ngay cả khi packet capture kỹ thuật cho phép xem plaintext HTTP, dữ liệu có thể thuộc người dùng khác. Mục tiêu bài là **đọc cấu trúc và xác minh behavior trong hệ thống có quyền**, không trích xuất thông tin cá nhân hoặc tái sử dụng session credentials.

## 2. HTTP request nằm ở tầng nào?

HTTP/1.1 truyền trên TCP dưới dạng **một luồng bytes có thứ tự**. TCP chia luồng thành segments, IP đóng vào packets, rồi link layer truyền frames.

~~~mermaid
flowchart TD
    A["Ứng dụng tạo HTTP/1.1 request"] --> B["TCP byte stream"]
    B --> C["TCP segments và retransmissions"]
    C --> D["IP packets"]
    D --> E["Ethernet/Wi-Fi frames"]
    E --> F["Capture ở host/TAP/SPAN"]
    F --> G["TCP reassembly và HTTP parser"]
    G --> H["Một hoặc nhiều HTTP messages"]
~~~

**Không có quan hệ 1:1** giữa TCP packet và HTTP request. Một request có thể chia nhiều segments; một segment có thể chứa bytes thuộc nhiều HTTP messages; một TCP connection có thể phục vụ nhiều requests nhờ keep-alive.

### 2.1. Request và response khác nhau

~~~text
Client                                  HTTP server
  |                                         |
  |---- GET /health HTTP/1.1 -------------->|
  |     Host: 127.0.0.1:18080               |
  |                                         |
  |<--- HTTP/1.1 200 OK --------------------|
  |     Content-Type: text/plain            |
  |     Body: lab-ok                         |
~~~

**Request** mô tả hành động mà client yêu cầu; **response** cho biết kết quả từ server. Để xác định một request có thực sự được xử lý hay không, phải xét **response, application logs và ngữ nghĩa ứng dụng**, không nhìn request line đơn độc.

### 2.2. Protocol/transport và nội dung quan sát được

| Giao thức | Transport | Passive packet capture nhìn được HTTP content? |
| --- | --- | --- |
| **HTTP/1.1 không TLS** | TCP | Có, nếu capture đủ byte stream và tái ghép đúng |
| **HTTPS HTTP/1.1** | TLS/TCP | **Không**, trừ khi có giải mã/termination được phép |
| **HTTP/2 plaintext (h2c) trong lab** | TCP | Có thể parse frames với công cụ hiểu HTTP/2; không phải text HTTP/1.1 |
| **HTTP/2 qua TLS** | TLS/TCP | Không đọc HTTP headers/body bằng passive capture thông thường |
| **HTTP/3** | QUIC/UDP với TLS 1.3 | Không đọc HTTP request từ passive packets thông thường |

Port **80/443/18080** chỉ là gợi ý, không bảo đảm parser có thể suy protocol chỉ từ port.

## 3. Giải phẫu HTTP/1.1 request

Một request HTTP/1.1 điển hình có **request line**, nhiều **header fields**, **dòng trống** và **body** nếu có.

~~~http
POST /api/check?source=lab HTTP/1.1
Host: 127.0.0.1:18080
User-Agent: curl/lab
Accept: */*
Content-Type: application/json
Content-Length: 15
X-Lab-Trace: read-http-007

{"event":"lab"}
~~~

Đây là bản **hiển thị dễ đọc**. Trên dây, HTTP/1.1 dùng **CRLF** (carriage return + line feed) để kết thúc mỗi dòng của phần header, và **CRLF CRLF** để kết thúc header section. Body JSON trong ví dụ có **15 bytes ASCII**.

### 3.1. Request line

~~~text
POST /api/check?source=lab HTTP/1.1
^^^^ ^^^^^^^^^^^^^^^^^^^^^ ^^^^^^^^
 |            |                |
method   request-target  HTTP version
~~~

- **Method** chỉ semantics của yêu cầu, ví dụ GET hay POST.
- **Request-target** ở ví dụ là path và query; không bao gồm scheme/hostname.
- **HTTP version** là phiên bản HTTP/1.x của thông điệp văn bản này.

### 3.2. Header fields

Các trường như **Host**, **Content-Type**, **Content-Length** và **X-Lab-Trace** hỗ trợ định tuyến, message framing hoặc trace. Tên header fields trong HTTP **không phân biệt chữ hoa/thường**, nhưng việc server/proxy xử lý có đúng và nhất quán không vẫn cần kiểm tra.

### 3.3. Dòng trống và request body

Dòng trống phân cách **header section** và **message content**. GET thường không gửi body, trong khi POST/PUT/PATCH thường có; tuy nhiên **không suy rằng method tự quyết định có/không có body**.

Content có thể là JSON, form, multipart, compressed bytes hoặc binary; **Content-Type** chỉ mô tả media type chứ không chứng minh body hợp lệ.

## 4. Request-target forms: path khác full URL

HTTP/1.1 có các dạng request-target quan trọng:

| Dạng | Minh họa | Ngữ cảnh |
| --- | --- | --- |
| **origin-form** | GET /items?page=1 HTTP/1.1 | Gửi tới origin server |
| **absolute-form** | GET http://service.example/items HTTP/1.1 | Thường dùng với forward HTTP proxy |
| **authority-form** | CONNECT service.example:443 HTTP/1.1 | Thiết lập một HTTP CONNECT tunnel |
| **asterisk-form** | OPTIONS * HTTP/1.1 | Nhắm tới server theo semantics của OPTIONS |

### 4.1. Origin-form và Host

~~~http
GET /catalog?lang=vi HTTP/1.1
Host: shop.example

~~~

Một request trực tiếp thường có **path ở request line** và **target authority ở Host header**. Nếu chỉ tìm hostname trong request line, sẽ bỏ sót Host.

### 4.2. Absolute-form qua forward proxy

~~~http
GET http://service.example/catalog HTTP/1.1
Host: service.example

~~~

Ở client-side capture, **destination IP có thể là proxy**, không phải server thật của service.example. Phải tách hai network hops và proxy logs nếu muốn truy nguyên.

### 4.3. CONNECT không làm lộ HTTP path bên trong TLS

~~~http
CONNECT service.example:443 HTTP/1.1
Host: service.example:443

~~~

Khi CONNECT được chấp nhận, client có thể thiết lập **TLS bên trong tunnel**. Passive sensor phía client→proxy có thể nhìn CONNECT authority nếu đoạn đó là plaintext, nhưng **không tự nhìn được path/headers/body của HTTPS qua tunnel**.

### 4.4. URL encoding và normalization

Một raw path như **/docs/report%20a.txt** có percent-encoding; query string có thể có **percent-encoded UTF-8**, dấu cộng hoặc nhiều giá trị cho một key. Luôn tách:

- **Raw request target** thu được từ capture.
- **Decoded/normalized target** do proxy, framework hoặc application tạo.
- **Actual route/handler** được ứng dụng chọn sau normalization.

Không tự thay raw URL evidence bằng đường dẫn đã giải mã nếu chưa giữ bản gốc. Khi các hop normalize khác nhau, lỗi routing và security policy có thể xảy ra.

## 5. HTTP methods và ý nghĩa bảo mật

| Method | Ngữ nghĩa điển hình | Giới hạn khi diễn giải |
| --- | --- | --- |
| **GET** | Truy xuất representation | Safe theo HTTP semantics, nhưng app triển khai sai vẫn có side effects |
| **HEAD** | Lấy metadata tương tự GET, không có response content | Không suy bytes thấp là request thất bại |
| **POST** | Yêu cầu xử lý data theo resource | Không mặc định idempotent hoặc đã tạo object thành công |
| **PUT** | Tạo/thay trạng thái resource theo semantics | Idempotent, nhưng có thể tạo logs/counters khi gọi lại |
| **PATCH** | Thực hiện thay đổi một phần | Không mặc định idempotent |
| **DELETE** | Xóa target resource theo semantics | Idempotent không đồng nghĩa request đầu thành công |
| **OPTIONS** | Truy vấn options/capabilities | Có thể là CORS preflight, không phải luôn vậy |
| **CONNECT** | Tạo tunnel | Không đủ để thấy content trong tunnel TLS |
| **TRACE** | Diagnostic loopback | Không thử trên server ngoài scope; thường bị giới hạn |

**Safe, idempotent và cacheable** là các thuộc tính khác nhau. Method là input khi triage, **không phải bằng chứng thao tác nghiệp vụ đã hoàn tất**.

### 5.1. POST không chứng minh dữ liệu đã được lưu

Nếu capture thấy một POST tới /api/orders, request có thể bị WAF chặn, app trả 401/400/500, transaction rollback hoặc client disconnect. Muốn nói “đơn hàng đã được tạo”, cần **response status + app/DB transaction audit** thích hợp.

### 5.2. Phân biệt application retry và TCP retransmission

TCP có thể truyền lại cùng bytes do thiếu ACK mà ứng dụng **không hề gọi lại API**. Ngược lại, HTTP client retry có thể tạo **request mới**. Phân biệt qua TCP sequence numbers, stream boundaries và application correlation ID khi có.

## 6. Những headers cần biết khi đọc request

| Header | Mục đích | Giới hạn/điểm chú ý |
| --- | --- | --- |
| **Host** | HTTP/1.1 target authority | Client khai, cần server validate |
| **User-Agent** | Client tự mô tả software | Không phải software identity đáng tin |
| **Accept** | Content media types mong muốn | Không chứng minh response thực trả loại đó |
| **Accept-Encoding** | Content codings client chấp nhận | Không đồng nghĩa request body đang nén |
| **Content-Type** | Media type của content gửi | Có thể sai so với body, cần validation |
| **Content-Length** | Số octets message content | Không phải tổng TCP packet size |
| **Transfer-Encoding** | Transfer coding trong HTTP/1.1 | Cần hiểu framing và parser consistency |
| **Authorization** | Credential/authorization scheme | **Secret**; không dán giá trị thật vào báo cáo |
| **Cookie** | State/session token | Có thể chứa credential hoặc PII |
| **Origin** | Origin theo browser semantics | Không thay authentication/authorization |
| **Referer** | URI tham chiếu nếu có | Có thể thiếu/bị cắt/chứa dữ liệu nhạy cảm |
| **Forwarded / X-Forwarded-For** | Thông tin proxy hops/client IP | Phải có trusted proxy chain, không tin header do client tự khai |
| **X-Request-ID / traceparent** | Correlate requests | Có thể do client tự chèn; cần validate |
| **Connection** | Thông tin connection của HTTP/1.x | Không chuyển nguyên sang HTTP/2/3 |
| **Upgrade** | Đề nghị đổi giao thức | Không đồng nghĩa đã được server chấp nhận |

### 6.1. Authorization và Cookie được che giá trị

~~~http
GET /profile HTTP/1.1
Host: app.example
Authorization: Bearer [REDACTED]
Cookie: session=[REDACTED]

~~~

Trong tài liệu, chỉ nên ghi **có header hay không, scheme và policy outcome**, không đưa token/cookie thật. Giá trị của Authorization hoặc Cookie có thể cấp quyền truy cập như một mật khẩu.

### 6.2. X-Forwarded-For không tự là client IP đáng tin

Nếu request có **X-Forwarded-For: 192.0.2.60**, không kết luận người gửi thật có IP đó chỉ từ header. Cần kiểm tra **source socket IP**, reverse-proxy trusted peers, policy ghi đè/nối chuỗi header và **NAT mappings**.

### 6.3. CORS preflight là một request riêng

~~~http
OPTIONS /api/inventory HTTP/1.1
Host: api.example
Origin: https://portal.example
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type

~~~

Đây có thể là **CORS preflight** của browser, không phải chính thao tác POST mà frontend dự định làm. CORS không thay server-side authorization.

## 7. Content-Length, chunked, JSON, form và multipart

### 7.1. Content-Length tính theo bytes

~~~http
POST /api/check HTTP/1.1
Host: 127.0.0.1:18080
Content-Type: application/json
Content-Length: 15

{"event":"lab"}
~~~

Content-Length là **octets** của content, không phải số Unicode characters. Với UTF-8, ký tự có dấu có thể dài hơn một byte. Thường để HTTP library tính framing thay vì tự gán.

### 7.2. Transfer-Encoding: chunked

~~~http
POST /stream HTTP/1.1
Host: 127.0.0.1:18080
Transfer-Encoding: chunked
Content-Type: text/plain

4
test
3
123
0

~~~

Trong wire format, các dòng chunk-size, chunk data và chunk boundaries sử dụng **CRLF** theo giao thức; 4 và 3 là **hexadecimal chunk sizes**, 0 kết thúc chunks, sau đó có thể có trailer section. Một text dump có thể không hiển thị CRLF rõ ràng; dùng parser và bytes thực.

### 7.3. Framing mơ hồ là vấn đề cần nhận biết

Khi proxy và backend xử lý **Content-Length/Transfer-Encoding** không nhất quán, ranh giới message có thể bị hiểu sai, dẫn tới lỗi security như request smuggling. Nếu thấy đồng thời các fields bất thường, duplicate length hoặc parser disagreement:

- Giữ **raw request evidence** và parser logs theo quyền.
- Không tự sửa boundary bằng trực giác.
- Dùng **strict HTTP parsing**, reject ambiguous messages.
- Kiểm tra bằng **fixture an toàn trên lab**, không gửi thử payload khai thác tới dịch vụ ngoài scope.

Bài này tập trung **đọc cấu trúc và phát hiện bất thường**, không cung cấp payload request-smuggling để tấn công.

### 7.4. JSON, form/multipart và compression

Body có thể là **application/json**, **application/x-www-form-urlencoded**, **multipart/form-data** (nhiều parts, file, boundary), binary hoặc compressed bytes. **Content-Encoding: gzip** là mã hóa representation, khác **Transfer-Encoding** và khác **TLS encryption**.

Nếu một dump plaintext trông “không đọc được”, trước khi kết luận đã được TLS mã hóa hãy kiểm tra **compression, content type, encoding, framing và TCP reassembly**.

## 8. TCP reassembly: vì sao một packet không phải một request?

### 8.1. Ví dụ request phân mảnh

~~~text
TCP stream client -> server:

Segment A: POST /api/check HTTP/1.1\r\nHost: 127.0.0.1:
Segment B: 18080\r\nContent-Length: 15\r\n\r\n{"event":
Segment C: "lab"}

Reassembled byte stream:
POST /api/check HTTP/1.1
Host: 127.0.0.1:18080
Content-Length: 15

{"event":"lab"}
~~~

Cách chia segment chỉ để minh họa, **không dự đoán TCP sẽ chia ở những vị trí này**. TCP có thể bị ảnh hưởng bởi MSS, Nagle, TCP segmentation offload, congestion, retransmission và scheduling.

### 8.2. Các bước giải mã logic

1. Xác định **transport** và flow theo source/destination IP, ports, protocol, capture vantage.
2. Tái lập chiều **client → server** bằng TCP sequence numbers.
3. Xử lý **retransmissions và out-of-order segments** theo byte ranges, không đếm lặp.
4. Phân tích **HTTP request line và header section** khi có đủ bytes.
5. Tìm message body boundary theo quy tắc **HTTP framing**.
6. Kiểm tra request kế tiếp trong cùng connection nếu **keep-alive/reuse**.
7. Đối chiếu với **response direction** và app/proxy logs nếu muốn kết luận outcome.

### 8.3. Phân biệt TCP retransmission và HTTP retry

- **TCP retransmission:** cùng dải bytes được transport gửi lại; không tự tạo business request mới.
- **HTTP retry:** client hoặc proxy tạo một request khác; có thể mang cùng URI/body nhưng là attempt mới.
- **Application transaction:** một operation được server xử lý; không nhất thiết bằng số HTTP attempts khi có retry/idempotency.

Vì vậy, một dashboard đếm mọi packet chứa chữ POST sẽ **đếm sai** nếu header bị chia/gửi lại, và cũng có thể bỏ sót requests mà parser không thể ráp.

### 8.4. Những vấn đề reassembly điển hình

| Triệu chứng | Khả năng | Bằng chứng cần |
| --- | --- | --- |
| Chỉ thấy phần giữa request | Bắt đầu capture midstream | TCP SYN, thời gian bắt đầu |
| Header bị cắt | Packet loss/snaplen quá nhỏ | Captured vs original length, drops |
| Request xuất hiện hai lần | Retransmission hoặc HTTP retry | TCP seq/stream, request ID |
| Không parse HTTP | Protocol thực là TLS hoặc port không được parser nhận diện | TLS handshake, TCP payload, protocol decode |
| Body không đủ | Capture dừng sớm, missing segments, streaming body | Reassembly diagnostics, end-of-message |
| Có nhiều requests trong một stream | Keep-alive hoặc pipelining theo client | Message boundaries và response association |
| Server response vắng mặt | Capture một chiều/asymmetric route | Interface, return path, app logs |

### 8.5. TCP stream ID là nhãn nội bộ công cụ

Wireshark/TShark có thể gắn **tcp.stream** để nhóm packets trong một capture. ID đó có ý nghĩa **trong PCAP đang mở**, không phải một định danh ổn định xuyên qua NAT, proxy, capture khác, hay transaction trong ứng dụng. Nếu điều tra nhiều hops, cần **flow tuples + timestamps + NAT/proxy/app correlation IDs**.

## 9. Điểm đặt cảm biến thay đổi những gì bạn đọc được

~~~mermaid
flowchart LR
    A["Client workstation"] --> T["TAP/SPAN tại LAN"]
    T --> F["Firewall / NAT"]
    F --> P["Forward/reverse proxy"]
    P --> S["Backend HTTP server"]
    T -. "Client IP/transport" .-> L["Network PCAP"]
    F -. "Allow/deny + NAT translations" .-> N["Firewall/NAT logs"]
    P -. "HTTP context nếu terminate phù hợp" .-> X["Proxy/WAF logs"]
    S -. "Route, user, application result" .-> Y["App logs"]
~~~

### 9.1. Trước và sau NAT

Trước NAT, sensor có thể nhìn **private source IP** của một máy. Sau NAT, nhiều máy có thể có chung **public source IP**. Đừng quy mọi request từ public IP đó cho một người dùng; cần **NAT connection mapping với thời gian và source port**, cùng asset/identity evidence.

### 9.2. Trước và sau reverse proxy

Một client gửi request tới reverse proxy, proxy có thể mở connection mới tới backend:

~~~text
Hop A:
  client:51530 -> reverse-proxy:443  (TLS session #1)

Hop B:
  reverse-proxy:41220 -> backend:8080 (HTTP plaintext trong vùng lab
                                    hoặc TLS session #2 theo kiến trúc)
~~~

Sensor ở **Hop A** không đọc request HTTPS nếu không có authorized decryption. Sensor ở **Hop B** có thể đọc HTTP plaintext nếu backend hop được thiết kế như vậy. Cả hai đều có thể thuộc **cùng một logical request**, nhưng có **5-tuple/TCP stream/TLS session khác nhau**.

### 9.3. Forward proxy và CONNECT

Một forward proxy có thể thấy **absolute-form HTTP requests** hoặc **CONNECT authority**. Nếu CONNECT chỉ tunnel TLS, proxy **không tự thấy HTTP path/body bên trong**. Nếu doanh nghiệp dùng TLS termination/inspection, đó là **điểm trust/data handling khác**, cần governance và chú ý certificate pinning, mTLS, privacy.

### 9.4. Service mesh và sidecars

Trong mesh, cùng một application request có thể thành các hops **workload proxy → gateway → backend**, có mTLS riêng. Source IP mà backend thấy có thể là sidecar/gateway thay vì client. Muốn biết **workload identity**, nên tham chiếu mesh/authenticated proxy telemetry, không gắn identity vào TCP source IP một cách máy móc.

### 9.5. Asymmetric routing và capture một chiều

Khi traffic hai chiều đi qua routes khác nhau, một sensor có thể chỉ thấy requests, không thấy responses. Việc không có HTTP 200 trong capture **không chứng minh server không gửi response**. Cần kiểm tra **vantage, NIC mirroring, VLAN, VPC traffic mirror, return path và packet drop counters**.

## 10. Lab localhost: tạo HTTP request không cần Internet

**Mục tiêu:** tạo một HTTP/1.1 request rõ ràng trên **127.0.0.1:18080**, ghi lại packet trên loopback và so sánh cách nhìn của **server log, curl verbose, TCP capture và HTTP parser**.

**Phạm vi:** chỉ thực hiện trên máy/lab bạn có quyền sử dụng. Không dùng credential, dữ liệu người dùng thật hoặc endpoint của bên thứ ba. Ví dụ shell bên dưới dành cho **Linux**; macOS thường dùng **lo0**, Windows cần chọn **Npcap Loopback Adapter** và dùng **curl.exe** thay vì alias PowerShell.

### 10.1. Tạo HTTP server tối giản

Lưu mã sau dưới tên **lab_http.py** trong **môi trường học của bạn**, không phải trong kho dữ liệu bài học:

~~~python
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 18080
MAX_BODY_BYTES = 1024


class LabHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def respond(self, code: int, message: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(message)))
        self.end_headers()
        self.wfile.write(message)

    def do_GET(self) -> None:
        # Log chỉ method/path test, không log Cookie/Authorization.
        print("LAB GET", self.path)
        self.respond(200, b"lab-ok")

    def do_POST(self) -> None:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None or not raw_length.isdecimal():
            self.respond(411, b"content-length-required")
            return

        content_length = int(raw_length)
        if content_length > MAX_BODY_BYTES:
            self.respond(413, b"body-too-large")
            return

        payload = self.rfile.read(content_length)
        # Chỉ in độ dài, tránh ghi body/credentials vào console.
        print("LAB POST", self.path, "body_bytes=", len(payload))
        self.respond(200, b"lab-ok")


if __name__ == "__main__":
    print(f"Listening only on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), LabHandler).serve_forever()
~~~

**Giới hạn server lab:** chỉ hỗ trợ GET và POST với Content-Length, **không tự xử lý chunked**, không có authentication/TLS và không dùng làm production server. Nó bind **127.0.0.1** để không mở cổng ra LAN/Internet. Mã ví dụ không được chạy bởi worker khi tạo bài; đây là **bài thực hành độc lập cho người học**.

### 10.2. Khởi động server trên terminal A

~~~bash
python3 lab_http.py
~~~

Kiểm tra console hiển thị **Listening only on http://127.0.0.1:18080**. Nếu port đã bị chiếm, dùng một port lab khác và thay nhất quán trong lệnh capture/curl.

### 10.3. Bắt gói loopback trên terminal B

~~~bash
# Linux: capture có giới hạn theo interface/host/port.
# Dừng bằng Ctrl+C ngay sau khi thực hiện request lab.
sudo tcpdump -i lo -nn -s 0 -w lab-http.pcap \
  'tcp port 18080 and host 127.0.0.1'
~~~

**-i lo** chỉ chọn loopback Linux; **-nn** không tự resolve tên/port; **-s 0** yêu cầu snaplen đầy đủ; **-w** ghi PCAP. Dữ liệu PCAP chỉ dùng lab nhưng vẫn được coi là **file nhạy cảm** nếu bạn lỡ gửi credentials thật.

Tùy OS, packet capture có thể hiển thị hai hướng trên loopback theo format/interface khác nhau. Không kết luận có hai HTTP requests chỉ vì thấy packets lặp tại capture.

### 10.4. Tạo GET với curl trên terminal C

~~~bash
curl --http1.1 --noproxy '*' -v \
  -H 'X-Lab-Trace: read-http-007-get' \
  'http://127.0.0.1:18080/health?source=lab'
~~~

Trong **curl -v**, các dòng bắt đầu bằng **>** thường là request headers được curl trình bày, các dòng bắt đầu bằng **<** thường là response headers. Output verbose là **góc nhìn client**, không phải packet capture trực tiếp. Không dùng **-v** với credentials thật rồi chia sẻ toàn bộ output.

### 10.5. Tạo POST JSON có Content-Length

~~~bash
curl --http1.1 --noproxy '*' -v \
  -H 'Content-Type: application/json' \
  -H 'X-Lab-Trace: read-http-007-post' \
  --data-binary '{"event":"lab"}' \
  'http://127.0.0.1:18080/api/check?source=lab'
~~~

**--data-binary** gửi bytes JSON đúng như mẫu. Curl thường tự chọn POST khi có data; không cần thêm một method override. Trong lab server log bạn sẽ thấy **body_bytes=15**, không cần in body.

### 10.6. Dừng capture và server

Sau khi đã có đủ hai requests:

1. Dừng **tcpdump** bằng Ctrl+C.
2. Dừng **lab server** bằng Ctrl+C.
3. Ghi **thời gian, port, file PCAP, command/test ID**.
4. Không tải PCAP lên dịch vụ public hoặc chat nếu chưa kiểm tra dữ liệu.
5. Xóa file khi hết mục đích hoặc lưu đúng retention policy.

**Kết quả mong đợi:** request GET và POST được gửi tới loopback, server trả **200** cho cả hai, PCAP có TCP packets liên quan; parser HTTP/1.1 tái ghép được request line/headers/body theo điều kiện capture đầy đủ.

## 11. Đọc PCAP bằng Wireshark

### 11.1. Mở file và chọn đúng protocol

Mở **lab-http.pcap** bằng Wireshark. Do server chạy port 18080, một bản Wireshark có thể tự nhận HTTP hoặc yêu cầu **Decode As → HTTP** cho luồng TCP đó.

Một số display filters:

~~~text
tcp.port == 18080
http.request
http.request.method == "POST"
http.host == "127.0.0.1:18080"
ip.addr == 127.0.0.1
~~~

**Display filter** lọc dữ liệu đã capture; nó **không thay đổi** những packets đã được ghi. Nếu filter HTTP không match, trước tiên hãy xem **tcp.port == 18080**, xác định payload thực, reassembly và decode-as; không kết luận request không tồn tại.

### 11.2. Các pane nên quan sát

| Pane | Bạn thấy gì | Dùng để làm gì |
| --- | --- | --- |
| **Packet List** | Số frame, thời điểm, source/dest, protocol, summary | Tìm request và response |
| **Packet Details** | Ethernet/IP/TCP/HTTP fields theo parser | Kiểm tra method, Host, Content-Type, Content-Length |
| **Packet Bytes** | Hex và ASCII bytes | Xem raw bytes và CRLF; tránh sao chép secrets |
| **Follow TCP Stream** | TCP bytes được tái dựng theo hướng | Xem message boundaries và request/response trong cùng connection |
| **Expert Information** | Hints về malformed, retransmission, handshake | Định hướng nhưng không thay evidence |

### 11.3. Follow TCP Stream

Chọn một packet thuộc luồng lab, dùng **Follow → TCP Stream**. Wireshark có thể hiển thị dữ liệu client/server bằng màu khác nhau; request và response có thể ở cùng cửa sổ.

**Đừng nhầm**:

- TCP reassembled bytes và **một packet duy nhất**.
- Một stream chứa **nhiều HTTP requests** với một transaction.
- Reassembly output có dữ liệu ứng dụng thật với evidence được phép chia sẻ.
- Encrypted TLS byte stream với HTTP plaintext chỉ vì nằm ở TCP port 443.

### 11.4. Kiểm tra request/response association

Trong capture hoàn chỉnh, request GET/POST có thể liên kết với response bằng cùng TCP stream, thứ tự HTTP messages hoặc transaction tracking của parser. Tuy nhiên **connection reuse, pipelining, proxy hops, incomplete captures và HTTP/2 multiplexing** làm association phức tạp hơn; không chỉ tìm một frame HTTP 200 gần nhất rồi coi đó là response của request đang xét.

## 12. Dùng TShark để trích thông tin request từ lab PCAP

TShark là công cụ dòng lệnh dùng dissectors của Wireshark. Các ví dụ chỉ đọc **file lab đã được phép ghi**.

### 12.1. Lọc requests và fields

~~~bash
tshark -r lab-http.pcap \
  -Y 'http.request' \
  -T fields \
  -e frame.number \
  -e frame.time_epoch \
  -e tcp.stream \
  -e http.request.method \
  -e http.host \
  -e http.request.uri
~~~

Với capture đầy đủ và parser đúng, bạn sẽ thấy **GET** và **POST** cùng Host/path. **tcp.stream** chỉ là ID trong file PCAP này.

### 12.2. Trích thông tin message framing

~~~bash
tshark -r lab-http.pcap \
  -Y 'http.request' \
  -T fields \
  -e http.request.method \
  -e http.request.uri \
  -e http.content_length
~~~

Một field có thể trống vì **không có header**, parser không nhận, hoặc capture thiếu. Không biến giá trị trống thành “bằng 0” nếu chưa kiểm chứng.

### 12.3. Chọn một TCP stream

~~~bash
# Thay stream number bằng giá trị thực đã quan sát trong lab.
tshark -r lab-http.pcap -Y 'tcp.stream == 0'
~~~

Nếu muốn xem nhiều packet details, có thể xuất trong môi trường lab nhưng **không trích toàn bộ bytes/cookie/token** ra ticket. Để chứng minh một request, thường chỉ cần **time, method, path template, Host, connection ID và app response** đã redacted.

### 12.4. Capture filter và display filter khác nhau

| Loại | Ví dụ | Thời điểm áp |
| --- | --- | --- |
| **BPF capture filter** | tcp port 18080 and host 127.0.0.1 | Trước/khi bắt packets bằng tcpdump |
| **Wireshark/TShark display filter** | http.request.method == "POST" | Sau khi packets được capture và dissector xử lý |

**BPF filter** không hiểu HTTP method ở payload. Một capture filter quá hẹp có thể làm mất những packets cần cho reassembly; không thể khôi phục bằng display filter sau đó.

## 13. Zeek HTTP logs và giới hạn khi dùng thay PCAP

Zeek có thể phân tích HTTP plaintext và tạo các events trong **http.log**, liên hệ với flow/connection bằng UID tùy phiên bản/cấu hình. Một log HTTP thường có thể cho **method, host, uri, status_code, user_agent, request_body_len** và thời gian.

### 13.1. Ví dụ normalized record

~~~json
{
  "source": "zeek-http-normalized-demo",
  "connection_uid": "C-demo-http-007",
  "client_ip": "127.0.0.1",
  "server_ip": "127.0.0.1",
  "server_port": 18080,
  "method": "POST",
  "host": "127.0.0.1:18080",
  "uri": "/api/check?source=lab",
  "request_body_length": 15,
  "response_status": 200,
  "content_capture": "not_collected",
  "lab_test_id": "read-http-007"
}
~~~

Đây là **schema minh họa do pipeline tạo**, không phải cam kết trường nào cũng có/đúng tên ở mọi bản Zeek. Nếu Zeek chỉ có **conn.log**, hoặc http.log không xuất hiện, hãy xem **protocol detection, capture integrity, TLS, packet loss và configuration**, không mặc định HTTP không xảy ra.

### 13.2. Log nội dung request có bắt buộc không?

Không. Một HTTP-aware sensor có thể parse method/path/status mà **không lưu toàn bộ request body hoặc Authorization/Cookie**. Điều đó thường là lựa chọn đúng về **data minimization**, và đôi khi làm ứng dụng/endpoint audit đáng tin hơn PCAP trong điều tra nghiệp vụ.

### 13.3. Zeek, Suricata, firewall và WAF làm việc khác nhau

- **Zeek:** thường dùng cho network protocol metadata và hoạt động phân tích có lập trình.
- **Suricata:** IDS/IPS, rule matching, EVE events, có thể log HTTP/flow metadata theo cấu hình.
- **Firewall/NetFlow/IPFIX:** network 5-tuples, byte counters, allow/deny, NAT, thường **không** cung cấp request line/body.
- **WAF/reverse proxy:** có thể có HTTP context **nếu** thực sự terminate/parse lớp ứng dụng.

Không yêu cầu một nguồn dữ liệu trả lời những câu hỏi nằm ngoài lớp mà nó quan sát.

## 14. Đọc HTTP request từ application/proxy logs khi thích hợp

Trên production, **application access log** hoặc **reverse-proxy log được redacted** thường phù hợp hơn full PCAP để trả lời “URL/HTTP method/status của một request hợp lệ là gì?”.

### 14.1. Mẫu log tối thiểu

~~~json
{
  "event_time": "2026-11-28T07:20:00Z",
  "resource": "finance-api",
  "method": "POST",
  "route_template": "/api/check",
  "response_status": 200,
  "request_bytes": 15,
  "duration_ms": 12,
  "trusted_client_identity": "lab-test-user",
  "request_id": "req-demo-007",
  "request_body_logged": false,
  "secrets_redacted": true
}
~~~

Đây là một **schema ứng dụng giả định**. Log production thực có fields khác; không điền giá trị **secrets_redacted=true** nếu chưa xác minh redaction.

### 14.2. Ưu tiên route template hơn raw URL

Raw URLs có thể chứa **search text, email, personal IDs, tokens trong query**. Đối với KPI và correlation, **route template** như /users/{id} và request ID thường đủ, giảm data retention risk.

### 14.3. Giới hạn của proxy access log

Proxy log có thể:

- Chỉ ghi request sau khi **TLS termination**.
- Không có request bị drop trước proxy.
- Ghi **upstream retry** thành nhiều backend attempts.
- Gắn client IP theo header không tin cậy nếu sai cấu hình.
- Có **sampling** hoặc mất log khi overload.

Muốn khẳng định “mọi traffic đều qua proxy”, phải kiểm tra **network direct paths**, không chỉ nhìn proxy logs.

## 15. HTTP response và cách ghép với request

Một response HTTP/1.1 điển hình:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=utf-8
Content-Length: 6

lab-ok
~~~

**200** là status code của response. Khi phân tích:

| Status family | Ý nghĩa chung | Cần thận trọng |
| --- | --- | --- |
| **1xx** | Thông tin/protocol processing | Có thể có 100 Continue trước final response |
| **2xx** | Request được xử lý thành công theo semantics | Không chứng minh mọi downstream business transaction ngoài ứng dụng |
| **3xx** | Redirection/conditional behavior | Một request có thể dẫn tới request khác ở client |
| **4xx** | Client-side request/authorization/framing issue theo nghĩa chung | 401/403/404/429 cần xác định điểm sinh status |
| **5xx** | Server/gateway/upstream không đáp ứng thành công | 502/503/504 có thể do proxy hoặc backend |

### 15.1. 100 Continue và request body

Client có thể gửi **Expect: 100-continue** để server quyết định trước khi client gửi body. Khi thấy response 100 trong capture, đó không phải **final outcome**. Cần tìm response tiếp theo và kiểm tra body có thật đã được gửi hay không.

### 15.2. Redirect chain

Một GET có thể nhận 301/302/307/308, sau đó client tạo request khác tới Location đã được giải thích. **Số requests không bằng số thao tác mà người dùng chủ động nhấp**; browser có thể thực hiện preflight, redirects, resource loads, favicon, telemetry.

### 15.3. Error có thể được sinh từ nhiều lớp

Nếu request tới reverse proxy trả **403**, nguồn có thể là WAF policy, proxy AuthorizationPolicy hoặc chính application. Nếu 504, có thể là gateway timeout trước khi backend xử lý xong. Cần ghép **gateway request ID, response source header/log, upstream status, app logs** để xác định origin của status.

### 15.4. Không dùng status thay transaction audit

Đối với hoạt động liên quan thanh toán, đổi quyền hoặc xóa dữ liệu, **HTTP 200/201/204** chỉ chứng minh một phần giao tiếp; có thể ứng dụng trả success nhưng downstream job sau đó thất bại. Bằng chứng cuối cần **application business event + transaction ID + data store audit** phù hợp.

## 16. HTTP/1.1 plaintext khác HTTPS như thế nào?

**HTTPS** là HTTP được bảo vệ bởi TLS (trong các trường hợp sử dụng TCP; HTTP/3 sử dụng QUIC và TLS 1.3). Khi phân tích packet capture, câu hỏi đầu tiên không phải “HTTP request nằm ở frame nào?”, mà là **“ở điểm capture này, HTTP message có thực sự ở dạng plaintext hay không?”**.

### 16.1. Cảm biến trước TLS termination

~~~mermaid
flowchart LR
    C["Browser / API client"] -->|"TLS encrypted"| T["Passive TAP / NDR"]
    T -->|"TLS encrypted"| G["TLS terminating proxy / server"]
    G -->|"App request sau giải mã"| A["Application"]
    T -. "IP, port, timing, TLS handshake metadata" .-> N["Network analytics"]
    G -. "HTTP method/route/status được log có chọn lọc" .-> L["Proxy/app logs"]
~~~

Cảm biến TAP có thể biết **TCP flow, TLS ClientHello, SNI khi có thể quan sát, packet sizes, duration**, nhưng không thể đọc **HTTP method, path, Cookie, request body** của kết nối HTTPS bình thường chỉ bằng PCAP.

### 16.2. TLS 1.2, TLS 1.3 và ECH

- TLS 1.2 full handshake có thể cho sensor passive thấy **một số TLS metadata** và server certificate.
- TLS 1.3 mã hóa phần lớn các handshake messages sau ServerHello, bao gồm **Certificate**, nên không được suy “không thấy certificate = server không có certificate”.
- **Encrypted ClientHello (ECH)** có thể che **ClientHelloInner** và SNI hostname thực; outer SNI không chắc là application hostname.
- Các trường handshake có thể thiếu do **resumption, capture midstream, packet loss, client không gửi hoặc parser không hỗ trợ**.
- Không thấy HTTP plaintext trong HTTPS là **đặc tính bảo mật đúng**, không phải lỗi của packet sniffer.

### 16.3. Server private key không phải khóa giải mã mọi phiên

Trong TLS 1.3 và các chế độ trao đổi khóa có **forward secrecy**, chỉ có private key của server certificate **thường không đủ** để thụ động giải mã các phiên đã capture. Một số ứng dụng lab có thể cung cấp **session secrets** cho công cụ phân tích được phép, nhưng đó là quyền truy cập đặc biệt, không phải khả năng mặc định của packet capture.

### 16.4. Khi cần biết HTTP method/path ở production

Ưu tiên **TLS terminator/reverse proxy/WAF/access logs hoặc application audit**, nơi request đã được giải mã theo kiến trúc và có thể sanitize. Không tự triển khai TLS interception để đọc traffic người khác hoặc tắt certificate verification chỉ vì muốn xem HTTP content.

## 17. HTTP/2: request tồn tại nhưng không có request line văn bản

HTTP/2 khác HTTP/1.1 ở **binary framing, multiplexed streams và HPACK header compression**. Một request HTTP/2 được biểu diễn bằng frames với headers như **:method, :scheme, :authority, :path** và content frames, không phải chuỗi văn bản kiểu **GET /path HTTP/1.1**.

### 17.1. Mô hình khái niệm

~~~text
HTTP/1.1 (text form):
  GET /api/items HTTP/1.1
  Host: api.example

HTTP/2 (logical headers, not literal TCP text):
  :method    GET
  :scheme    https
  :authority api.example
  :path      /api/items
~~~

Với HTTP/2 qua TLS, **cả header blocks và DATA frames đều được mã hóa trên đường truyền**. Ngay cả trong lab có h2c, cần **dissector hiểu HTTP/2**; tìm chuỗi GET trong TCP payload thường không có ý nghĩa.

### 17.2. Streams và multiplexing

- Một TCP connection có thể chứa **nhiều HTTP/2 streams** song song.
- TCP stream ID do Wireshark gán **không phải HTTP/2 stream ID**.
- Response association cần theo **HTTP/2 stream IDs**, không chỉ thứ tự frames.
- **Header compression** khiến bytes trên wire khác dạng header text dễ đọc.
- Headers có tên chữ thường trong HTTP/2 và có các quy tắc cho connection-specific fields.

Đừng dùng số TCP connections làm số HTTP/2 requests.

### 17.3. HTTP/2 qua reverse proxy

Một front proxy có thể nhận **HTTP/2 qua TLS** rồi gửi **HTTP/1.1 plaintext** tới backend trong lab, hoặc ngược lại. Khi phân tích, cần ghi **HTTP version của mỗi hop**, tránh nói “browser gửi GET HTTP/1.1” chỉ vì backend capture có GET text.

### 17.4. h2c trong lab không đại diện Internet

Một số môi trường nội bộ/test có **HTTP/2 cleartext (h2c)**. Khi phân tích h2c, parser có thể đọc HTTP/2 frames không mã hóa; nhưng không vì vậy mà khẳng định **HTTP/2 trên Internet** cũng plaintext. Giao thức và transport phải được ghi tách biệt.

## 18. HTTP/3 và QUIC: vì sao TCP Follow Stream không đủ?

HTTP/3 dùng **QUIC trên UDP** và header compression **QPACK**. Nếu chỉ dùng filter **tcp.port == 443** hoặc tìm request line trong TCP stream, bạn có thể bỏ lỡ toàn bộ HTTP/3 traffic.

### 18.1. Những gì cảm biến passive thường thấy

| Trường | Khả năng quan sát | Giới hạn |
| --- | --- | --- |
| UDP source/destination IP/port | Có tại điểm capture | UDP/443 không luôn là QUIC |
| Packet size/timing | Có | Không xác định URL hay file content |
| QUIC headers/version/connection IDs | Có thể thấy các trường phù hợp | CID không phải user identity |
| QUIC Initial handshake | Parser có thể trích một số TLS ClientHello fields ở QUIC v1 | ECH vẫn có thể che inner SNI |
| HTTP/3 :method, :path, headers/body | Không qua passive encrypted capture thông thường | Cần endpoint/proxy/app telemetry có thẩm quyền |

### 18.2. HTTP/3 multiplexing

HTTP/3 có nhiều request streams trên một QUIC connection. **QUIC connection migration** có thể thay đổi IP/port mà logical connection vẫn tồn tại; không thể đối chiếu request count bằng số UDP five-tuples.

### 18.3. QUIC fallback

Client có thể thử QUIC/HTTP3 rồi fallback sang HTTP/2 qua TLS/TCP do firewall, server support hoặc network conditions. Điều này có thể tạo **nhiều connection attempts cho một thao tác người dùng**, không tự chứng minh replay hay scan.

### 18.4. Chọn nguồn evidence đúng

Để biết **HTTP method/path/status** của HTTP/3 trong production, tìm **browser/endpoint, CDN/edge, reverse proxy hoặc app logs có quyền**, không kỳ vọng TShark từ UDP capture tự giải mã request contents.

## 19. Correlation qua NAT, proxy và ứng dụng

Một logical request có thể xuất hiện tại các nguồn khác nhau:

~~~text
User/client process
   |  request/trace ID (nếu app phát)
   v
Local host TCP flow
   |  client private IP, ephemeral port
   v
NAT / corporate proxy
   |  source translated hoặc proxy egress IP/port
   v
Reverse proxy/WAF
   |  authenticated principal, route, policy decision
   v
Application
   |  app session and business transaction
   v
Database / service dependencies
~~~

### 19.1. Một data contract có provenance

~~~json
{
  "event_id": "http-lab-demo-007",
  "event_time": "2026-11-28T07:30:00Z",
  "network_observation": {
    "capture_point": "loopback-lab",
    "source_ip": "127.0.0.1",
    "destination_ip": "127.0.0.1",
    "destination_port": 18080,
    "protocol": "TCP",
    "tcp_stream_local_id": 1,
    "complete_request_bytes": true
  },
  "http_observation": {
    "source_type": "http1_plaintext_parser",
    "method": "POST",
    "request_target": "/api/check?source=lab",
    "host": "127.0.0.1:18080",
    "content_type": "application/json",
    "content_length_bytes": 15,
    "body_stored": false
  },
  "app_observation": {
    "request_id": "read-http-007-post",
    "response_status": 200,
    "recorded_by": "authorized_lab_server"
  },
  "data_quality": "lab_only_complete"
}
~~~

Đây là **schema minh họa**, không phải output thô của một công cụ. Các trường **complete_request_bytes, response_status, recorded_by** cần evidence từ parser/server; không điền “true” chỉ vì capture có một packet chứa POST.

### 19.2. Các keys liên kết

| Nguồn | Correlation key | Lưu ý |
| --- | --- | --- |
| **PCAP/TCP** | 5-tuple + time + capture-local stream ID | NAT/reuse/port changes |
| **NAT/firewall** | Translated source/dest mapping và time | Nhiều users có chung public IP |
| **Proxy** | Proxy connection/transaction ID | HTTP/2 multiplex và upstream retries |
| **App** | Request ID/trace ID, authenticated user, route | Client-supplied IDs có thể giả nếu không normalize |
| **Service mesh** | Workload identity, trace context và hop IDs | mTLS identity khác user identity |
| **Database/business** | Transaction ID, committed action | Không suy transaction chỉ từ HTTP status |

### 19.3. Clock synchronization

Sensor, NAT, proxy, EDR, application và DB có thể có **độ lệch thời gian**. Khi correlate, ghi **event time UTC, ingest time, clock skew estimate và time window**, tránh nối hai requests chỉ vì cùng source IP và thời điểm gần nhau.

### 19.4. Request ID là dữ liệu cần xác minh nguồn

Một X-Request-ID do client tự gửi có thể tùy ý. Trên shared trust boundary, gateway nên **validate, replace hoặc normalize** theo chính sách, tránh một client cố gắn ID trùng với giao dịch của người khác làm SIEM correlate sai.

### 19.5. NAT không chứng minh danh tính người

Nếu thấy một HTTP request từ public source IP, bạn chưa biết người nào gửi. Cần **device inventory, NAT mapping, authenticated proxy/app identity** và time context; đừng quy hành vi nhạy cảm cho cá nhân chỉ từ public IP.

## 20. Security use cases khi đọc HTTP requests

### 20.1. Điều tra WAF rule và false positives

WAF có thể đưa ra quyết định dựa trên **method, path, headers, body size, content type** ở vị trí có khả năng đọc HTTP. Khi một request hợp lệ bị block, thu:

- Policy/rule ID và action.
- **Normalized route**, host và method.
- Lượng content, encoding và parser errors.
- **Request ID** để đối chiếu application và gateway.
- Lỗi từ client và response source/status.
- Bằng chứng về **tài khoản/test permission**, không cần raw credentials/body.

Không tắt toàn bộ WAF chỉ để một test qua được; dùng exception hẹp, có owner/TTL, và positive/negative regression tests.

### 20.2. Điều tra unexpected methods/paths

Một endpoint bình thường chỉ nhận GET nhưng xuất hiện PUT/PATCH/DELETE hoặc request-target lạ có thể đáng xem. Tuy nhiên bots/health checks/developer tools cũng có thể tạo traffic khác thường. Nên correlate **app routes, authenticated principal, source environment, deploy changes và response outcome** trước khi phân loại.

### 20.3. Xác minh authentication và authorization

Packet capture có thể cho biết một HTTP plaintext request có header Authorization, nhưng **không chứng minh token hợp lệ hoặc user được cấp quyền**. Cần **IdP/app auth logs và response/operation audit**. Không đọc hay sao chép token trong quá trình triage.

### 20.4. Kiểm tra request framing và proxy/backend parser

Sự khác nhau khi các hop xử lý **Host, Content-Length, Transfer-Encoding, URL normalization và headers trùng** có thể gây lỗi. Khi gặp dấu hiệu:

1. Ghi **request ID, thời điểm, request line/headers đã sanitize**.
2. Xác định hop nào nhận hoặc reject, qua policy logs.
3. Test bằng **fixture không gây hại trong staging**, không gửi malformed exploit đến hệ thống ngoài scope.
4. Sửa validation/consistent parsing và test regressions.

### 20.5. Quan sát nguy cơ lộ dữ liệu qua URL

Nếu access logs chứa **token/password/PII trong query string**, vấn đề có thể là application design, không chỉ logging. Nên chuyển secrets khỏi URL/query và thực hiện **redaction, appropriate token handling, short TTL, rotation khi cần**, thay vì chỉ giấu một trường trong dashboard.

### 20.6. Phân biệt policy enforcement và traffic telemetry

- **Passive IDS/NDR** có thể nhận diện bất thường và phát hiện sự kiện trên đường đi.
- **IPS/WAF/proxy** có thể block nếu nằm đúng đường và có policy được triển khai.
- **Application authz** mới quyết định một user được phép thao tác lên dữ liệu gì.

Log “request observed” không có nghĩa request được phép; log “403” không nhất thiết có nghĩa firewall đã chặn từ tầng IP.

## 21. Case study 1: Wireshark không thấy GET dù browser mở trang được

### 21.1. Bối cảnh giả định

Một nhân viên được phép phân tích kết nối tới ứng dụng nội bộ. Browser mở **https://portal.example** thành công, nhưng khi dùng display filter **http.request**, Wireshark không hiển thị request nào trên interface client.

### 21.2. Những giả thuyết cần phân biệt

| Giả thuyết | Dữ liệu xác minh |
| --- | --- |
| Browser dùng **HTTPS/TLS** | TCP 443 và TLS handshake; không có HTTP plaintext |
| Browser dùng **HTTP/3/QUIC** | UDP 443, QUIC Initial/header parsing phù hợp |
| Capture nhầm interface | NIC, VPN tunnel, virtual adapter, route |
| Capture bắt đầu sau handshake | Start time, TCP SYN, packet chronology |
| BPF capture filter bỏ packets | Filter trên interface, expected 5-tuple |
| Có proxy/agent trung gian | Proxy settings, CONNECT/TLS hops |
| HTTP dissector không nhận dạng port | Protocol decode và Wireshark configuration |

### 21.3. Quy trình giải quyết

1. Ghi **URL scheme, destination resolution, proxy setting và thời gian**.
2. Dùng filter mạng cơ bản như **tcp.port == 443** hoặc **udp.port == 443** theo đúng scope được phép.
3. Kiểm tra có **TLS/QUIC** hay không thay vì ép giải mã thành HTTP text.
4. Nếu cần method/path/status, xin **reverse-proxy/application access log** có request ID và được redacted.
5. Đối chiếu app log với network flow qua **timestamp, proxy/NAT mapping và correlation ID**.
6. Không bật TLS verification bypass hoặc thu session secrets của người dùng thật.

**Kết luận đúng:** “Passive capture của kết nối được TLS/QUIC bảo vệ không hiển thị HTTP request plaintext”; không phải “browser chưa gửi HTTP”.

## 22. Case study 2: một POST bị đếm hai lần vì TCP retransmission

### 22.1. Bối cảnh

Một bảng báo cáo tự phát hiện chuỗi **POST /api/check** trong raw packets. Sau một sự kiện packet loss lab, dashboard báo **hai lần POST** trong cùng kết nối, nhưng server log chỉ có **một request**.

### 22.2. Evidence

~~~text
Raw packet capture:
  seq 1000..1199 -> bytes containing request header/body
  seq 1000..1199 -> retransmission of same byte range

Reassembled TCP byte stream:
  one contiguous request message

Server application log:
  one request handled, one response recorded
~~~

Đây là ví dụ minh họa, không phải gói TCP thực được tạo bởi một host cụ thể.

### 22.3. Cách phân biệt

- Kiểm tra **TCP sequence/ack number và retransmission analysis**.
- Dùng **Follow TCP Stream** hoặc protocol parser có reassembly.
- Đối chiếu **application request ID** và số requests server thực xử lý.
- Kiểm tra có **HTTP client retry** nào tạo **request mới** trên stream khác không.
- Không tính tổng số packets chứa chữ POST thành số thao tác tạo bản ghi.

### 22.4. Bài học

**Tầng transport retransmission không đồng nghĩa retry của tầng ứng dụng**. Một request-level metric đúng cần **HTTP parsing trên byte stream**, deduplication và app audit khi cần.

## 23. Case study 3: X-Forwarded-For làm sai client attribution

### 23.1. Bối cảnh

Một ứng dụng ở sau reverse proxy ghi trong access log:

~~~text
remote_addr: 10.0.4.20     (proxy IP trong ví dụ)
x_forwarded_for: 192.0.2.60
request: GET /admin HTTP/1.1
~~~

Một analyst định kết luận người dùng tại **192.0.2.60** đã truy cập /admin. Nhưng client có thể đã chủ động gửi header **X-Forwarded-For** trước khi request đi vào reverse proxy.

### 23.2. Các câu hỏi bắt buộc

1. Reverse proxy có **xóa/ghi đè** untrusted forwarding headers từ client không?
2. Có bao nhiêu **trusted proxy hops** và proxy nào chịu trách nhiệm gắn source IP đã xác thực?
3. **TCP peer** ở gateway là IP nào?
4. NAT/VPN có source translation và mapping theo đúng timestamp không?
5. Application log lấy client IP từ **socket** hay từ header?
6. Có **mTLS/SSO/application authenticated identity** độc lập hỗ trợ attribution không?

### 23.3. Kết quả cần đưa ra

Nếu chưa xác minh trusted proxy chain, ghi:

> Request đã xuất hiện tại reverse proxy, với X-Forwarded-For tự khai như trên; client IP thực **chưa được xác nhận**.

Nếu có đầy đủ LB/proxy/NAT/auth evidence, mới tiến hành attribution phù hợp; không suy từ header client-controlled alone.

### 23.4. Bài học

**Một header không tự đáng tin chỉ vì được in trong HTTP log.** Ranh giới giữa client-provided và proxy-verified fields là phần của security architecture.

## 24. Case study 4: server thấy body thiếu dù Content-Length được khai báo

### 24.1. Tình huống

Một ứng dụng test gửi POST body qua HTTP/1.1, proxy báo lỗi malformed request và server log thiếu bytes. Đội vận hành nhìn thấy header **Content-Length** và đoán toàn bộ body đã tới server.

### 24.2. Những nguyên nhân có thể

- Capture **thiếu segments** hoặc dừng quá sớm, trong khi server thực đã nhận body.
- Client **đã khai Content-Length nhưng ngắt kết nối trước khi gửi đủ**.
- Proxy/body-size limit khiến request bị từ chối/truncated theo policy.
- Request có **Transfer-Encoding** và Content-Length được xử lý không nhất quán.
- **chunked encoding** bị parser ghi dưới dạng chunks, analyst cộng bytes sai.
- **Expect: 100-continue** khiến client chưa gửi body nếu bị từ chối sớm.
- **Content-Encoding** khiến body không hiển thị văn bản dù đã nhận đủ compressed bytes.

### 24.3. Cách điều tra

| Bước | Evidence |
| --- | --- |
| Xác định request ID/hop | Client log, proxy transaction, backend request |
| Kiểm tra byte stream | TCP reassembly, missing segments, completeness flags |
| Kiểm tra HTTP framing | Content-Length, Transfer-Encoding, chunk boundaries |
| Kiểm tra gateway policy | Request-body size, timeout, parser reject rule |
| Kiểm tra app parser | Số bytes thật đã đọc, error code, request completion |
| Kiểm tra response | 100 Continue, 4xx/5xx, connection resets |
| Xác minh kết quả | Controlled positive fixture và server log, không cần body thật |

### 24.4. Bài học

**Header Content-Length là thông tin framing**, không phải bằng chứng server chắc chắn đã nhận đủ content. Cần xem **actual bytes, transport, intermediary behavior và application outcome**.

## 25. Case study 5: WAF ghi 403 nhưng ứng dụng báo không có request

### 25.1. Bối cảnh

User thấy HTTP 403 khi gọi API, WAF log có method/path, nhưng backend app không có request ID tương ứng. Một nhóm kết luận app authorization bị lỗi.

### 25.2. Giải thích có thể

WAF/reverse proxy có thể trả **403 ngay ở edge**, trước khi route request tới backend, do:

- Source/identity/rate policy.
- Path/header/body validation.
- Rule chống bot hoặc anomaly.
- CORS/configuration misunderstanding.
- Parser rejection.

Nếu WAF sinh response, **backend không nhất thiết nhận request**.

### 25.3. Điều tra đúng lớp

1. Thu **gateway/WAF transaction ID**, policy rule và timestamp.
2. Xác định 403 đến từ **WAF hay backend**, thông qua logs/response source.
3. Đối chiếu **request method, normalized path, Host, content length và client identity**, tất cả đã redacted.
4. Kiểm tra **policy phù hợp role/source/application contract**.
5. Dùng **test identity và valid request fixture** trong staging để xác nhận false positive nếu có.
6. Nếu cần exception, áp **scope hẹp với owner, TTL, negative test**, không tắt cả WAF.

### 25.4. Bài học

Một HTTP 403 trong client trace **không chứng minh backend đã từ chối**. Muốn biết điểm từ chối, cần xác định **chính xác hop tạo response**.

## 26. Case study 6: POST upload làm rò dữ liệu qua bản PCAP hỗ trợ

### 26.1. Tình huống

Trong một sự cố upload chậm trên HTTP plaintext nội bộ, kỹ sư thu **full PCAP** ở server interface rồi gửi file cho nhóm lớn để cùng đọc. PCAP chứa các **multipart form fields**, filename và dữ liệu tài liệu thật.

### 26.2. Vấn đề

Vấn đề không chỉ là HTTP request latency. Việc chia sẻ PCAP không có scope tạo ra **rủi ro lộ dữ liệu mới**:

- Multipart payload có thể chứa **file bytes**.
- Query/body có thể chứa **PII, token, session IDs**.
- Một PCAP có thể chứa **các requests không liên quan** cùng thời điểm.
- File có thể còn tồn tại sau khi incident được đóng.
- Người đọc cần biết request framing có thể vô tình xem toàn bộ content.

### 26.3. Phương pháp đúng

1. Dừng phân phối PCAP rộng và áp quyền truy cập theo **incident/data-handling process**.
2. Ưu tiên **request ID, method, route template, body size, duration, retries và status** thay vì raw payload.
3. Nếu cần chứng cứ raw bytes, giới hạn **phạm vi, approver, retention, encryption và chain of custody**.
4. Làm sạch artifacts trước khi đưa vào ticket/QA documentation, bảo đảm không giữ credential hoặc file thật.
5. Đánh giá liệu có cần **rotation/incident notification** theo chính sách nếu sensitive data đã bị lộ ngoài scope.
6. Sau khắc phục, giảm khả năng lập lại qua **logging standards, packet capture SOP và đào tạo**.

### 26.4. Bài học

**Kỹ thuật đọc được HTTP plaintext là một khả năng nhạy cảm**, phải giới hạn sử dụng theo nhiệm vụ; bảo vệ request contents cũng là trách nhiệm của đội giám sát mạng.

## 27. Đo chất lượng capture và độ tin cậy của HTTP parser

Một packet analyzer có thể hiển thị **request hợp lệ với độ tin cậy thấp** nếu capture thiếu đầu luồng, packet bị drop hoặc traffic đi qua một path khác. Vì vậy cần đo chất lượng nguồn dữ liệu trước khi biến nó thành security KPI.

### 27.1. Các chỉ số hữu ích

| Metric | Điều cần đo | Rủi ro diễn giải |
| --- | --- | --- |
| **In-scope path coverage** | % đường cần giám sát có sensor/flow evidence | Một sensor online không đồng nghĩa mọi subnet được bao phủ |
| **Bidirectional capture coverage** | % test flows có client→server và server→client | Không thấy response không chắc server không phản hồi |
| **Packet drop rate** | Drops/overruns theo sensor/interface khi khả dụng | Counters không có không đồng nghĩa 0 drops |
| **Full-stream observation** | % eligible connections có handshake/đầu stream đầy đủ | Midstream không thể parse request đầu |
| **HTTP decode rate** | % eligible plaintext HTTP flows parser xử lý được | Không tính TLS encrypted thành parser failure |
| **Request message completeness** | % parsed requests có header và framing đầy đủ | Body có thể streaming hoặc không được lưu theo privacy |
| **Application correlation rate** | % requests map được tới app request ID | Client-supplied ID có thể sai |
| **Timestamp/clock quality** | Event-time skew và ingestion delay | Time mismatch tạo false join |
| **Schema/parser version coverage** | % events có nguồn/phiên bản parser rõ ràng | Parser upgrade làm đổi ý nghĩa fields |
| **PII/credential redaction compliance** | % logs theo data-handling policy | Full payload làm tăng security risk |

### 27.2. Denominator phải chỉ rõ loại traffic

Ví dụ:

\[
\text{HTTP/1.1 parse coverage} =
\frac{\text{số kết nối HTTP/1.1 plaintext đủ dữ liệu được parser nhận}}
{\text{số kết nối HTTP/1.1 plaintext eligible được quan sát}} \times 100\%
\]

Chỉ số này **không bao gồm** HTTPS/HTTP2/HTTP3 mà passive sensor không đọc plaintext theo thiết kế. Cần báo riêng những traffic types **not observable by design**, **unsupported parser** và **not captured**.

### 27.3. Data quality có nhiều trạng thái

~~~text
observed_full_http_request
observed_partial_http_request
connection_observed_no_http_parse
encrypted_transport_no_plaintext
protocol_not_supported
capture_incomplete_or_asymmetric
not_in_instrumented_path
unknown
~~~

Không gộp tất cả các trạng thái thành **“request không xảy ra”**.

### 27.4. Quy tắc kết luận có confidence

Một incident note có thể ghi:

> Ở sensor S1 trong khoảng UTC đã xác định, một HTTP/1.1 POST plaintext tới /api/check được tái ghép đầy đủ, request body framing hợp lệ. Application log cùng request ID ghi nhận server đã trả 200. Không có bằng chứng trong những nguồn này cho các hoạt động downstream ngoài phạm vi app log.

Kết luận này mạnh hơn “PCAP chứa POST nên dữ liệu đã được ghi thành công” vì chỉ rõ **nguồn, hop, kết quả và giới hạn**.

## 28. Runbook khi cần đọc HTTP request phục vụ sự cố

### 28.1. Giai đoạn 1 — Xác định câu hỏi và quyền truy cập

Trước khi capture, viết cụ thể:

- **Câu hỏi:** cần xác minh method/path? 4xx/5xx đến từ đâu? Có body truncation? Có proxy rewrite Host?
- **Resource owner** và thời gian sự cố.
- **Source/destination/port/protocol** dự kiến; IPv4/IPv6, VPN/NAT/proxy.
- **Scope pháp lý/nội bộ**: có quyền thu plaintext headers/body không?
- Có thể dùng **access log hoặc trace ID** thay PCAP không?
- Nếu cần PCAP: chọn **điểm capture, filter, thời lượng, lưu trữ và retention**.

### 28.2. Giai đoạn 2 — Xác định đúng hop và protocol

~~~mermaid
flowchart TD
    A["Cần xác minh HTTP request"] --> B{"Có app/proxy log hợp lệ đủ thông tin?"}
    B -->|Có| C["Dùng log đã redacted + request ID"]
    B -->|Không| D{"Authorized capture scope?"}
    D -->|Không| E["Dừng và xin approval/scope"]
    D -->|Có| F{"Traffic plaintext HTTP tại vantage?"}
    F -->|Có| G["Capture hẹp → TCP reassembly → HTTP parse"]
    F -->|Không, HTTPS/HTTP2/3 encrypted| H["Dùng endpoint/terminator logs theo quyền"]
    G --> I["Correlate response/application outcome"]
    H --> I
    C --> I
~~~

### 28.3. Giai đoạn 3 — Thu bằng chứng an toàn

1. Capture **trước khi tái hiện** nếu cần xem request đầu.
2. Dùng **giới hạn host/port/interface/time** và kiểm tra counters.
3. Chọn **test identity**, dùng nội dung không nhạy cảm.
4. Lưu **timestamp UTC và capture point**; chú ý server/host clock skew.
5. Chạy request từ client đã ủy quyền, ghi **curl request/response details** đã sanitized.
6. Kiểm tra **message body size/framing** thay vì lưu raw payload nếu không cần.
7. Dừng capture ngay khi đủ evidence.

### 28.4. Giai đoạn 4 — Phân tích và xác nhận

| Câu hỏi | Source đầu tiên | Source xác nhận |
| --- | --- | --- |
| Client có gửi GET/POST? | Client log/HTTP plaintext capture | Proxy/app log |
| Host/path là gì? | HTTP parser ở hop có plaintext | App routing logs |
| Body có đủ không? | TCP reassembly + HTTP framing | Server bytes-read/error log |
| 403 do đâu? | Proxy/WAF response event | Backend request absence/authorization log |
| Server có nhận request? | Backend access log | App trace/transaction |
| User/device nào gửi? | Authenticated proxy/app identity | NAT/EDR/IdP correlation |
| Có direct bypass không? | Firewall/flow evidence | PEP/proxy/access inventory |
| Request là HTTP/2/3? | ALPN/proxy/browser/app logs | Protocol-aware parser/terminator evidence |

### 28.5. Giai đoạn 5 — Đưa ra kết luận, dọn dẹp

- Viết rõ **observed / inferred / confirmed**, nơi quan sát và quality caveats.
- Không trích **Authorization, Cookie, private user data, API keys** vào bản báo cáo.
- Gắn **owner và remediation** cho từng finding, cùng evidence revalidation.
- Kiểm tra có **PCAP/data dump** vượt scope đã được tạo không và xử lý đúng.
- Đóng lab/capture, xóa dữ liệu tạm theo retention, không để server demo mở port lâu dài.

### 28.6. Mẫu incident evidence

~~~text
Case ID / owner / UTC time window:
Approved resource and scope:
Network vantage / interface / capture filter:
Transport, IPs/ports, NAT/proxy hops:
Plaintext HTTP or TLS/QUIC:
Request method, target, Host (redacted if sensitive):
Header/body framing, completeness and parser version:
Response status and source hop:
Proxy transaction ID / app request ID:
Authenticated principal (source and confidence):
Packet drops / asymmetric path / unknowns:
Observed facts, hypotheses and confirmed application outcome:
Fix, positive/negative validation, rollback:
PCAP/log access controls and retention:
~~~

## 29. Ma trận kiểm thử đọc HTTP request trong lab

Tất cả tests đều dùng **localhost hoặc staging được cấp phép**, hạn chế số lần/gói và không đưa credentials thật. Với h2c/HTTP3 và TLS variations, cần test server có hỗ trợ tương ứng; server Python mẫu ở mục 10 **chỉ dùng HTTP/1.1 plaintext**.

| Test | Kịch bản | Expected evidence |
| --- | --- | --- |
| **P1 – HTTP/1.1 GET** | curl tới localhost /health | Parser thấy GET, Host, URI; server 200 |
| **P2 – HTTP/1.1 POST** | JSON 15 bytes tới /api/check | Parser thấy POST, Content-Length=15, server đọc 15 bytes |
| **P3 – Query encoding** | Path/query chứa percent-encoding giả | Raw request target được giữ, normalized path ghi riêng |
| **P4 – Keep-alive** | Hai requests hợp lệ trên một connection test | Hai HTTP messages, một TCP stream nếu client thật sự reuse |
| **P5 – Headers case-insensitivity** | Host vs host trong lab | Parser xử lý cùng field semantics |
| **P6 – Separate response** | Request GET nhận 200 | Status nằm trong response, không trong request |
| **P7 – TCP segmentation** | Lab network tạo header/body qua nhiều segments | Reassembly vẫn tái dựng một request |
| **P8 – TCP retransmission** | Controlled loss/retransmission trong lab | Không nhân đôi HTTP request count |
| **N1 – Partial capture** | Bắt midstream có chủ đích | Parser đánh dấu incomplete, không tự bịa request |
| **N2 – Capture truncation** | Lab snaplen thấp | Trường/body thiếu được đánh dấu, có quality alert |
| **N3 – Wrong interface/filter** | Capture sai loopback/port trong lab | Không thấy flow, kiểm tra vantage trước khi kết luận |
| **N4 – TLS encrypted** | Owned HTTPS lab endpoint | Passive capture không đọc HTTP method/path/body |
| **P9 – Authorized TLS termination** | Reverse proxy lab có access log | Proxy có HTTP details, upstream passive vẫn encrypted |
| **P10 – HTTP/2 capable lab** | Server và client có h2/h2c hỗ trợ | Request có pseudo-headers/streams, không HTTP/1.1 text line |
| **P11 – HTTP/3 capable lab** | QUIC/HTTP3 supported endpoints | UDP/QUIC observed, HTTP request content không plaintext passive |
| **P12 – CONNECT** | Test forward proxy do tổ chức sở hữu | CONNECT authority visible ở HTTP hop; inner HTTPS không |
| **N5 – Untrusted XFF** | Test client gửi X-Forwarded-For giả | Gateway/app không tin IP nếu không qua trusted chain |
| **N6 – Content-Length inconsistency** | Safe invalid-body fixture trong staging | Parser/server reject hoặc xử lý nhất quán theo policy |
| **P13 – 100 Continue** | Owned client/server hỗ trợ | 100 interim và final response được phân biệt |
| **P14 – Multipart test** | Dummy file/test fields | Multipart parser hiểu boundary; PCAP được bảo vệ |
| **P15 – Compression** | Gửi payload gzip giả vào endpoint lab có hỗ trợ | Content-Encoding giải thích body bytes |
| **P16 – Proxy/WAF deny** | Controlled policy deny trên staging | Proxy 403 có transaction ID, backend có thể không nhận |
| **N7 – Data protection** | Dummy token/cookie có thể nhận biết | Logs/reports che token; raw captures xử lý theo policy |
| **P17 – NAT correlation** | Two test clients qua known NAT | Không gán nhầm cùng public IP là cùng user |
| **F1 – Sensor outage** | Controlled collector failure | Monitoring thể hiện mất coverage, không báo “0 traffic” |

### 29.1. Positive controls là bắt buộc

Nếu negative test không kết nối được, nguyên nhân có thể là **app down, DNS sai, route hỏng**, không phải firewall/authorization. Cần **positive control ở cùng thời điểm** để chứng minh resource vẫn hoạt động và **deny event tại đúng enforcement point**.

### 29.2. Test pass phải có giới hạn chính xác

Một báo cáo “P1–P17 đều PASS” không chứng minh hệ thống production hoàn toàn an toàn. Nó chứng minh **bộ test đã chọn đạt trong môi trường/cấu hình/time window xác định**. Khi app, parser, proxy route hoặc network policy đổi, phải revalidate phù hợp.

### 29.3. Gắn parser version và source

TShark/Wireshark, Zeek, Suricata, proxy và application logs có **schemas/capabilities khác nhau**. Một test chuẩn phải ghi **phiên bản công cụ, protocol, capture point, IP/port, request ID, privacy treatment và những trường không thể quan sát**.

## 30. Quản trị nội dung HTTP, PCAP và bằng chứng

### 30.1. HTTP plaintext có thể mang secrets ngay trong request line

Không chỉ Authorization/Cookie, **query string** cũng có thể chứa API token, personal identifier, reset link hoặc mã giao dịch. Vì vậy:

- Đừng log raw URL rộng nếu chỉ cần **route template**.
- Hạn chế in **body** vào console hoặc SIEM khi chỉ đang kiểm tra latency.
- Dùng **request ID**, method, sanitized path, content type/length, status và timestamps.
- Với yêu cầu điều tra nội dung thật, chỉ cấp quyền **tối thiểu theo nhiệm vụ**, retention hạn chế và dữ liệu được mã hóa/bảo quản đúng.

### 30.2. Một bản PCAP không chỉ có request mục tiêu

Nếu dùng capture filter quá rộng, file có thể chứa requests của **nhiều người dùng hoặc hệ thống ngoài scope**. Khi chưa chắc, không gửi bản PCAP nguyên gốc cho toàn nhóm qua chat. Hãy trích **summary đã sanitize** hoặc nhờ người có quyền xem nguồn gốc theo quy trình.

### 30.3. Phân tách quyền capture, phân tích và công bố

| Khả năng | Kiểm soát cần |
| --- | --- |
| **Bắt packet** | Authorized source/network, ticket và bounded scope |
| **Đọc nội dung** | Data classification, approved analyst role |
| **Giải mã TLS** | Điểm/khóa được cấp phép, TLS/PKI/Privacy approval riêng |
| **Xuất báo cáo** | Redaction, provenance, confidence, đúng người nhận |
| **Lưu PCAP/key material** | Encryption, RBAC, audit, retention, deletion |
| **Chia sẻ với vendor** | Hợp đồng, DPA/approval, giới hạn trường dữ liệu |

### 30.4. Chứng cứ kỹ thuật phải lưu nguồn gốc

Ghi **original file hash/integrity metadata** theo quy trình, nguồn thu, filter, sensor ID, timestamps và công cụ parser. Khi tạo bản trích hoặc sanitized PCAP, tách **bản gốc** và **bản dùng để báo cáo**, không thay đổi nội dung bản gốc rồi quên ghi chép.

### 30.5. Không dùng giải mã như giải pháp mọi sự cố

Việc bật TLS inspection có thể phá **certificate pinning, mTLS, HTTP/2/3 compatibility**, tăng latency và tạo rủi ro giữ plaintext. Nếu mục tiêu chỉ là biết **method/path/status** của ứng dụng do tổ chức sở hữu, **server-side access log có redaction** thường ít rủi ro và đáng tin hơn triển khai inspection đại trà.

## 31. Những nhầm lẫn thường gặp

1. **“Một packet chứa toàn bộ HTTP request.”** Request là message được xây trên TCP byte stream.
2. **“HTTP request và HTTP response là cùng thứ.”** Request có method/target; response có status.
3. **“Thấy POST nghĩa giao dịch đã ghi thành công.”** Phải kiểm tra response và application audit.
4. **“Request-line trong mọi HTTP đều là GET /path HTTP/1.1.”** HTTP/2/3 dùng binary frames/pseudo-headers.
5. **“TCP port 80 luôn là HTTP.”** Ports không chứng minh protocol.
6. **“TCP/443 luôn chứa HTTP body.”** HTTPS mã hóa application content.
7. **“Wireshark không thấy http.request nên không có HTTP.”** Có thể là TLS/QUIC, capture sai hoặc parser thiếu.
8. **“HTTP/3 nằm trong TCP stream.”** HTTP/3 chạy trên QUIC/UDP.
9. **“QUIC Initial đọc được thì HTTP/3 path cũng đọc được.”** HTTP content vẫn được bảo vệ.
10. **“ClientHello SNI chứng minh HTTP URL cụ thể.”** SNI không phải path/query/body.
11. **“Có server TLS private key là đọc được mọi TLS 1.3 PCAP.”** Forward secrecy làm giả định này sai.
12. **“Content-Length là số ký tự hoặc tổng packet bytes.”** Nó chỉ số octets content theo framing.
13. **“Mọi POST đều có Content-Length.”** Chunked/khác phương thức framing có thể áp dụng.
14. **“Body bắt đầu sau header đầu tiên.”** Body bắt đầu sau kết thúc header section CRLF CRLF.
15. **“Một dòng trống nghĩa body luôn tồn tại.”** Request có thể không có content.
16. **“GET không bao giờ mang message content.”** Không nên suy tuyệt đối chỉ từ method; semantics của body trên GET không được định nghĩa chung.
17. **“Content-Type cho biết dữ liệu luôn đúng định dạng.”** Header do client cung cấp, parser phải validate.
18. **“Content-Encoding gzip chính là TLS encryption.”** Compression và transport encryption là hai lớp khác nhau.
19. **“Chunk size là số thập phân.”** Trong HTTP/1.1 chunked, size được biểu diễn bằng hex.
20. **“Content-Length và Transfer-Encoding không bao giờ cần review.”** Parser inconsistency có thể tạo ambiguity.
21. **“Retransmitted segment là HTTP request mới.”** TCP retransmission chỉ phát lại bytes.
22. **“Một TCP connection bằng một HTTP request.”** Keep-alive, pipelining/multiplexing phá quan hệ đó.
23. **“TCP stream ID là transaction ID chung toàn hệ thống.”** Nó chỉ cục bộ trong capture.
24. **“HTTP 200 nằm trong request.”** 200 nằm trong response.
25. **“HTTP 403 luôn do backend tạo.”** Proxy, WAF hoặc gateway cũng có thể trả 403.
26. **“Thấy 100 Continue nghĩa thao tác đã xong.”** Đó là interim response.
27. **“GET 301 rồi GET 200 nghĩa user nhấp hai lần.”** Có thể do redirect.
28. **“Host và X-Forwarded-For là bằng chứng identity.”** Các giá trị có thể được client tự khai.
29. **“Forward proxy destination IP luôn là IP đích ứng dụng.”** Có thể là proxy hop.
30. **“CONNECT hiển thị được URL bên trong HTTPS tunnel.”** Thường chỉ thấy authority/tunnel setup.
31. **“Cùng NAT IP là cùng một người.”** Nhiều clients có thể dùng chung source IP.
32. **“Thiếu response trong PCAP nghĩa server không trả.”** Có thể capture một chiều.
33. **“Đọc payload trong packet bytes dễ hơn Follow TCP Stream.”** Segmentation/retransmissions có thể làm sai.
34. **“Display filter có thể khôi phục packet chưa capture.”** Nó chỉ lọc packets hiện có.
35. **“BPF filter có thể lọc bằng http.request.method.”** BPF thông thường không parse HTTP method như display filter.
36. **“HTTP/2 Connection header được xử lý y hệt HTTP/1.1.”** HTTP/2 có quy tắc riêng cho connection-specific headers.
37. **“Mọi http.log của Zeek đều ghi body và credentials.”** Logs/schema/config có thể chỉ ghi metadata.
38. **“NetFlow/IPFIX tương đương PCAP chi tiết.”** Flow aggregation khác packet-level capture.
39. **“Không có app log nghĩa request không tới server.”** Có thể log sampling, ingestion delay, khác hop.
40. **“Request ID client cung cấp là bằng chứng không thể giả.”** Cần normalize/trust boundary.
41. **“Capture càng rộng càng tốt.”** Dễ thu ngoài scope, tăng privacy/retention risk.
42. **“PCAP đã mã hóa thì không nhạy cảm.”** Metadata, DNS, session keys ngoài band vẫn có thể nhạy cảm.
43. **“Dùng curl -v với token thật rồi gửi log cho mọi người là vô hại.”** Verbose output có thể để lộ secrets.
44. **“Có khả năng giải mã nghĩa có quyền thu nội dung.”** Kỹ thuật và authorization khác nhau.
45. **“Một HTTP request hợp lệ nghĩa request được phép.”** Authentication/authorization ở app và gateway quyết định.
46. **“Không cần positive control khi negative test timeout.”** Timeout có thể do app outage, không phải policy.
47. **“Một lần parser PASS chứng minh toàn production được giám sát.”** Cần coverage/quality/unknowns và nhiều protocol paths.
48. **“TLS inspection luôn tốt cho mọi ứng dụng.”** Có thể xung đột mTLS/pinning, privacy và availability.

## 32. Bài tập vận dụng và gợi ý đáp án

### Bài 1 — Đọc request line

Cho request:

~~~http
GET /reports?month=11&format=json HTTP/1.1
Host: portal.example
Accept: application/json

~~~

**Câu hỏi:** method là gì? Request target là gì? Host nằm ở đâu? HTTP status có trong ví dụ chưa?

**Gợi ý:** method **GET**; target **/reports?month=11&format=json**; authority trong **Host**; chưa thấy response nên **không có status**.

### Bài 2 — Body length

Một lab POST có:

~~~http
POST /api/check HTTP/1.1
Host: 127.0.0.1:18080
Content-Type: application/json
Content-Length: 15

{"event":"lab"}
~~~

**Câu hỏi:** 15 là số bytes gì? Có tính luôn headers không? Nếu body UTF-8 chứa ký tự tiếng Việt thì dùng số chữ cái để tính được không?

**Gợi ý:** Content-Length là **số octets của content**, không tính headers; với UTF-8, một ký tự có thể nhiều bytes.

### Bài 3 — Phân biệt request và response

Wireshark hiển thị **POST /api/check HTTP/1.1**, sau đó **HTTP/1.1 403 Forbidden**. Có thể khẳng định backend đã từ chối vì thiếu quyền không?

**Gợi ý:** chưa. Status có thể do WAF/proxy/backend; cần **proxy transaction logs + app logs + policy reason**.

### Bài 4 — CONNECT và HTTPS

Một forward proxy log cho biết client gửi **CONNECT api.partner.example:443**. Analyst kết luận client đã POST tới **/payments/transfer**.

**Gợi ý:** kết luận vượt evidence. CONNECT cho biết authority để thiết lập tunnel; **HTTP path bên trong TLS** không nhìn thấy nếu proxy không terminate hoặc không có authorized application logs.

### Bài 5 — TCP retransmission

Một PCAP có hai TCP segments với **cùng sequence byte range** và cùng phần đầu request. Server ghi nhận một request.

**Gợi ý:** nhiều khả năng là retransmission của cùng bytes; dùng TCP reassembly và server logs, không đếm gói thành HTTP requests.

### Bài 6 — Header trust

Server access log ghi X-Forwarded-For **192.0.2.30**, TCP peer của server là **10.0.1.5**. Có thể xác nhận client IP là 192.0.2.30 ngay không?

**Gợi ý:** chưa. Xác định **trusted proxies, NAT mappings, overwrite policy** và authenticated identity. Header có thể bị client spoof.

### Bài 7 — Chunked

Trong HTTP/1.1, chunk-size line có **A** và sau đó 10 bytes content. Có gì bất thường không?

**Gợi ý:** ký tự hex **A** có giá trị thập phân **10**; phù hợp với chunk-size semantics. Phải kiểm tra **CRLF/chunk boundaries** và các chunks tiếp theo.

### Bài 8 — Không thấy HTTP trên HTTPS

Một sensor thấy TCP handshake và TLS 1.3 ClientHello tới server, nhưng không có HTTP method/path. Có nên đánh dấu “HTTP parser fail” không?

**Gợi ý:** không; passive sensor không được giải mã thì request content được bảo vệ **by design**. Dùng **proxy/app logs** có thẩm quyền hoặc test HTTPS lab với endpoint diagnostics nếu cần.

### Bài 9 — HTTP/2 và request count

Một connection h2 chứa 12 application requests được ghép thành HTTP/2 streams. Dashboard chỉ có 1 TCP connection.

**Gợi ý:** TCP connection count **không bằng HTTP request count**; phải đo HTTP/2 streams/requests ở parser hoặc application logs.

### Bài 10 — Thiết kế lab có thể kiểm toán

Hãy đề xuất bước đo cho một ứng dụng lab dùng HTTP/1.1 GET và POST:

1. Chọn interface/port và **chỉ bind 127.0.0.1**.
2. Tạo server không log raw body/token và test client curl.
3. Capture hẹp bằng tcpdump; ghi source/destination và timestamp.
4. Đọc bằng Wireshark, **Follow TCP Stream** và TShark.
5. Tách headers, body, response và TCP retransmissions.
6. Correlate với app log theo **X-Lab-Trace** do lab kiểm soát.
7. Trình bày **observed, inferred, unknown**.
8. Dừng capture, che nội dung nhạy cảm và dọn file lab.

**Gợi ý:** ưu tiên chứng minh **cùng một request từ client→packet→server response**, thay vì thu nhiều traffic không cần thiết.

### Bài 11 — Lỗi framing cần điều tra

Proxy ghi “request framing invalid”, app không có request log. Một bản text dump chứa các dấu hiệu **Content-Length và Transfer-Encoding** không thống nhất.

**Gợi ý:** giữ raw evidence đã sanitize, tìm parser/reject log ở proxy, xem capture completeness và dùng **safe staging fixture** để kiểm tra strict parsing; không gửi payload khai thác lên production.

### Bài 12 — Quyết định nguồn bằng chứng

Đội SOC cần biết một tài khoản đã thay đổi **quyền quản trị** tại application thông qua HTTPS hay chưa. Passive PCAP chỉ có TLS handshake/bytes và destination IP.

**Gợi ý:** dùng **application authorization/operation audit**, proxy/gateway request ID và identity events; PCAP chỉ hỗ trợ network path/timing. Không kết luận quyền đã đổi từ encrypted traffic volume.

## 33. Checklist đọc HTTP request an toàn

| Câu hỏi | Bằng chứng/kết quả mong đợi |
| --- | --- |
| Có quyền thu thập và phân tích resource này? | Ticket, owner, scope/retention |
| Capture có giới hạn host/port/interface/time? | BPF filter và timestamps |
| Đã dùng test data thay credentials thật? | Dữ liệu giả, data-classification review |
| Biết traffic dùng HTTP/1.1, HTTP/2, HTTP/3 hay TLS? | Protocol detection và app/client context |
| Chọn đúng network vantage và capture hai chiều? | Route/NAT/proxy diagram, capture point |
| Có đầy đủ đầu TCP stream và handshake khi cần? | SYN, sequence, packet completeness |
| Tool có support protocol/port đang phân tích? | Parser/Decode As và version |
| Request line được tách method/target/version đúng? | HTTP parser result |
| Host/authority được diễn giải đúng từng HTTP version? | Headers/pseudo-headers |
| URL raw và normalized được giữ khác nhau? | Request-target + app route |
| Message body framing đúng Content-Length/chunked? | Actual bytes, protocol validation |
| Dữ liệu JSON/form/multipart/compression được phân biệt? | Content-Type, Content-Encoding, parser |
| Có xử lý TCP retransmissions/out-of-order? | TCP reassembly evidence |
| Không đếm connection như số requests? | HTTP messages/HTTP2 streams |
| Response status được gắn với đúng request? | Stream/transaction mapping và app logs |
| Có phân biệt gateway/WAF response với backend response? | Rule IDs/upstream status |
| Proxy headers được tin theo chain đúng? | Trusted peer policy và NAT correlation |
| Client/session identity có nguồn đáng tin? | Authenticated app/gateway records |
| PCAP thiếu requests do TLS by design có được ghi rõ? | TLS/QUIC classification |
| Có phân biệt partial/midstream với app không gửi request? | Data-quality flags |
| CORS preflight/redirect có được tách khỏi app action? | Request/response chain |
| Các findings nghiêm trọng có positive control? | App health + policy deny evidence |
| Logs đã che Authorization, Cookie, PII và body? | Redaction review |
| Có cần giữ full PCAP không? | Minimum evidence và retention decision |
| Parser/sensor version và unknown fields được ghi? | Schema provenance |
| Có owner, remediation và regression tests? | Incident ticket + validation |
| Lab server/capture đã dừng và dọn artifacts? | Cleanup record |

## 34. Tổng kết

**Đọc HTTP request trong môi trường được phép** bắt đầu từ hiểu **HTTP message semantics** chứ không phải tìm chữ “GET” hoặc “POST” trong một packet ngẫu nhiên. Với HTTP/1.1 plaintext, người phân tích cần tái ghép **TCP byte stream**, đọc đúng **request line, Host, headers, CRLF, content framing và body**; sau đó đối chiếu **response và application outcome** để không nhầm một request đã gửi với một thao tác nghiệp vụ đã hoàn tất.

HTTP/2 sử dụng **binary frames, pseudo-headers và multiplexing**; HTTP/3 dùng **QUIC/UDP**; còn HTTPS bảo vệ method/path/headers/body bên trong TLS. Một passive sensor có thể thấy network/TLS metadata mà **không có quyền hoặc khả năng thấy HTTP plaintext**. Khi cần câu trả lời ở tầng ứng dụng, hãy tìm **proxy/TLS terminator/app audit logs có quyền** thay vì suy từ IP/port/SNI hoặc cố giải mã traffic ngoài scope.

Trong module **SECURITY_NETWORK_SECURITY**, năng lực này phục vụ **packet capture, phân tích lưu lượng, WAF/firewall/IDS/IPS troubleshooting, proxy trust boundaries, network threat investigation và giám sát an toàn**. Một kết luận đáng tin phải cho biết **đã quan sát gì, ở hop nào, bằng parser nào, mức độ hoàn chỉnh của capture, response/identity được xác minh ra sao**, cũng như những điều **chưa thể biết**.

Vì HTTP plaintext có thể chứa secrets và dữ liệu người dùng, tiêu chuẩn kỹ thuật phải đi cùng **ủy quyền, capture tối thiểu, redaction, bảo quản bằng chứng và thời hạn lưu trữ**. Phương pháp tốt nhất là thực hành trên **localhost/staging được cấp phép**, kiểm chứng bằng **PCAP + client + proxy/app logs**, dùng **positive/negative tests** và ghi rõ giới hạn suy luận. Đó là cách đọc HTTP request chính xác, có ích cho bảo mật mạng mà vẫn bảo vệ quyền riêng tư và dữ liệu.
