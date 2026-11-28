# TLS metadata và giới hạn quan sát nội dung: giám sát lưu lượng mã hóa đúng bằng chứng

Trong chương **Giám sát mạng và telemetry** của module **SECURITY_NETWORK_SECURITY**, phần lớn kết nối ứng dụng hiện đại sử dụng **TLS** để bảo vệ dữ liệu trên đường truyền. HTTP qua TLS (HTTPS), gRPC qua TLS, kết nối database bảo mật, các giao thức quản trị, cũng như HTTP/3 trên QUIC đều đặt câu hỏi khó cho đội Network Security: **cảm biến mạng có thể nhìn thấy gì, không thể nhìn thấy gì và từ metadata có thể suy ra điều gì đáng tin?**

Một cảm biến đặt trên đường truyền có thể ghi lại **địa chỉ nguồn/đích, cổng, kích thước và thời điểm các gói tin**, và trong nhiều trường hợp quan sát được **ClientHello, một số trường TLS handshake hoặc những dấu vết của QUIC**. Nhưng nó thường **không thể đọc HTTP path, cookie, Authorization header, nội dung file hay response body** khi traffic được mã hóa và không có khóa/điểm giải mã được ủy quyền. Ngay cả một số metadata từng nhìn thấy trong TLS cũ cũng bị thu hẹp bởi **TLS 1.3, Encrypted ClientHello (ECH), session resumption và QUIC**.

Điều nguy hiểm là đánh đồng **“metadata nhìn thấy”** với **“nội dung đã được giải mã”**, hoặc dùng một hostname/SNI/fingerprint để kết luận chắc chắn người dùng đã truy cập URL nào, tải dữ liệu gì hay có hành vi độc hại. Một hệ thống giám sát tốt phải phân biệt **quan sát trực tiếp, suy luận có điều kiện, dữ liệu không quan sát được và bằng chứng từ endpoint/application bổ sung**.

**Mục tiêu bài học**

- Vẽ đúng các điểm quan sát TLS tại **network TAP/SPAN, firewall, proxy/LB, endpoint và ứng dụng**.
- So sánh metadata có thể thấy trong **TLS 1.2, TLS 1.3, TLS resumption, QUIC/HTTP/3 và ECH**.
- Phân tích **SNI, ALPN, certificate details, TLS versions, cipher suites, supported groups, JA3/JA4-style fingerprints, IP/port/flow statistics** mà không phóng đại ý nghĩa.
- Xác định ranh giới bảo mật của **TLS termination, TLS inspection, session-key logging và end-to-end encryption**.
- Thiết kế pipeline **Zeek/Suricata/PCAP/NetFlow-IPFIX/firewall/DNS/EDR/app logs** để tương quan sự kiện một cách có thể kiểm chứng.
- Đánh giá **metadata-based detection, false positives, privacy, ECH blind spots, asymmetric capture và sampling limitations**.
- Xây dựng bộ **positive/negative tests, troubleshooting, case studies, incident runbook** cho môi trường có quyền quản trị.

Các ví dụ hostname có hậu tố **.example** và địa chỉ IP thuộc các dải tài liệu được dùng làm tình huống giả định, không đại diện cho dịch vụ thật.

## 1. TLS bảo vệ những gì, và metadata khác plaintext ở đâu?

**Transport Layer Security (TLS)** giúp bảo vệ kênh giao tiếp bằng các cơ chế mã hóa, toàn vẹn và xác thực peer phù hợp với cấu hình. Khi client kiểm tra certificate và danh tính máy chủ đúng cách, kết nối HTTPS làm giảm nguy cơ một bên trên đường truyền đọc/chỉnh sửa nội dung ứng dụng.

Tuy nhiên, một số phần của luồng giao tiếp vẫn phải xuất hiện **trước khi hình thành khóa mã hóa** hoặc tồn tại ở tầng IP/transport bên ngoài TLS.

~~~mermaid
flowchart LR
    C["Client/ứng dụng"] --> N["Router / TAP / firewall"]
    N --> S["TLS server"]
    N -. "IP, port, packet sizes, timing, một số handshake metadata" .-> O["Passive sensor"]
    C -. "Request + response plaintext trước TLS" .-> E["Client endpoint telemetry"]
    S -. "TLS termination + application logs" .-> L["Server-side evidence"]
    O --> D["SIEM / correlation"]
    E --> D
    L --> D
~~~

### 1.1. Bốn nhóm dữ liệu phải được đặt nhãn

| Nhóm | Ví dụ | Mức khẳng định |
| --- | --- | --- |
| **Quan sát trực tiếp ngoài TLS** | IP/port, giao thức TCP/UDP, packet length, timestamps, TCP flags | Chứng minh packet/flow đã xuất hiện tại điểm capture |
| **Handshake metadata có thể quan sát** | ClientHello fields, SNI và ALPN offered khi không được che, TLS phiên bản/hỗ trợ | Phụ thuộc phiên bản, mode, vị trí và việc ghi đủ handshake |
| **Suy luận dựa trên metadata** | Đoán ứng dụng từ JA3/JA4, lưu lượng giống beaconing, phân nhóm client behavior | Là giả thuyết; cần confidence, baseline và xác minh bổ sung |
| **Application content** | HTTP URL path, request body, cookie, token, uploaded file, database query | Thường **không khả dụng** với passive capture của kết nối TLS hợp lệ |

**Ví dụ:** cảm biến nhìn thấy client mở TCP tới 203.0.113.10:443 và ClientHello có SNI là **api.partner.example**. Nó có thể nói rằng **client đã đề nghị dùng hostname đó trong handshake**. Nó **không thể tự khẳng định** đã thực hiện POST tới **/v1/orders**, nhận HTTP 200, hay gửi 20 MB hồ sơ khách hàng.

### 1.2. Confidentiality không có nghĩa không còn metadata

Mã hóa TLS không che toàn bộ IP headers và các đặc điểm quan sát ở ngoài TLS. Một observer vẫn có thể dùng **traffic analysis** để ước lượng connection duration, bytes, direction, RTT hoặc traffic burst, nhưng nội dung request vẫn không được xác định chắc chắn từ các đặc điểm đó.

Ngoài ra, **metadata cũng nhạy cảm**: hostname, thời điểm kết nối và thiết bị/người dùng có thể tiết lộ hoạt động hoặc mối quan hệ. Bảo vệ quyền riêng tư phải áp cho cả metadata, không chỉ plaintext.

### 1.3. Bối cảnh là điều kiện của mọi kết luận

Một bản ghi “TLS traffic to 203.0.113.10” cần thêm:

- **Điểm capture**: ở client LAN, trước NAT, sau NAT, trước proxy hay sau proxy?
- **Protocol**: TLS/TCP hay QUIC/UDP, có kết nối dài hay nhiều connections?
- **Handshake observed?** Có thấy ClientHello từ đầu hay chỉ midstream?
- **TLS version and feature set**: có resumption/ECH không?
- **Correlation**: DNS answer, endpoint process, ZTNA/proxy logs, app events?
- **Coverage**: packet drops, sampling, asymmetric routing, timestamp skew?

Không ghi bối cảnh sẽ biến một telemetry row thành bằng chứng dễ bị hiểu sai.

## 2. Điểm quan sát quyết định những gì nhìn thấy

### 2.1. Passive TAP/SPAN trước điểm giải mã

~~~text
Endpoint C  -- encrypted TLS -->  Switch TAP/SPAN  -- encrypted TLS -->  Server
                                      |
                                      +--> PCAP / NDR / IDS

Thường quan sát:
  IP/port, TCP/UDP, kích thước/timing,
  handshake metadata chưa mã hóa nếu được capture.

Không tự quan sát:
  HTTP path, Authorization header, POST body, response JSON.
~~~

TAP/SPAN không mặc định có quyền giải mã TLS. Một số hệ thống IDS có **protocol metadata parsing** nhưng không có content visibility; việc nhãn “TLS inspection” trên sản phẩm không nhất thiết đồng nghĩa **giải mã tất cả HTTPS**.

### 2.2. Sau TLS termination tại reverse proxy/LB

~~~mermaid
flowchart LR
    C["Client"] -->|"TLS #1"| L["Reverse proxy / LB termination"]
    L -->|"TLS #2 hoặc plaintext theo kiến trúc"| A["Backend application"]
    L -. "HTTP method/path/headers có thể được quan sát tại đây" .-> W["Proxy/WAF logs"]
    C -. "TLS #1 metadata" .-> P["Upstream passive sensor"]
    L -. "TLS #2 metadata" .-> Q["Backend passive sensor"]
~~~

Nếu proxy **terminate TLS #1**, nó có thể quan sát HTTP requests theo cấu hình ứng dụng. Nhưng:

- Một proxy **TLS passthrough** không nhìn được HTTP payload.
- Nếu proxy **re-encrypt** tới backend, cảm biến sau proxy lại chỉ thấy TLS #2.
- Logs có thể **không ghi body hoặc sensitive headers** vì data minimization.
- Upstream observer thường thấy **proxy IP**, không còn IP client thật sau NAT nếu thiếu trusted forwarding/correlation.

### 2.3. Endpoint/application telemetry

EDR, application gateway, browser instrumentation hoặc ứng dụng có thể biết **process, hostname, HTTP method, route, status và business operation** trước mã hóa hoặc sau giải mã. Nhưng nguồn dữ liệu này có **độ tin cậy và quyền truy cập khác nhau**, cũng có thể bị mất khi endpoint bị compromise.

Kết luận có giá trị cao thường đến từ **kết hợp network + endpoint + server logs**, không giả định một nguồn bao phủ tất cả.

### 2.4. Network vantage thay đổi vì proxy, NAT và service mesh

| Vị trí đo | Source/dest nhìn thấy | Rủi ro hiểu sai |
| --- | --- | --- |
| **Trước NAT** | Client private IP → external IP | Không ánh xạ được public IP nếu thiếu NAT log |
| **Sau NAT** | Public egress IP → external IP | Nhiều clients bị gộp thành một source |
| **Trước forward proxy** | Client → proxy | Không nhất thiết thấy external IP trực tiếp |
| **Sau forward proxy** | Proxy → external server | Identity của user bị ẩn nếu không có proxy audit |
| **Trước TLS terminator** | Client TLS handshake và encrypted records | Không thấy HTTP body |
| **Sau TLS terminator** | Backend connection mới | Client handshake nguyên thủy đã kết thúc |
| **Service mesh sidecar/gateway** | Hop mTLS và workload proxy behavior | Một flow logic có thể thành nhiều TLS hops |
| **Cloud flow log** | Aggregated flow/timing/counters | Không phải PCAP full handshake; có thể sampling |

### 2.5. Đọc pipeline theo hop

Một yêu cầu tới SaaS có thể trải qua:

~~~text
User process
  -> local agent / ZTNA / VPN
  -> enterprise forward proxy
  -> cloud NAT gateway
  -> CDN edge
  -> SaaS origin
~~~

Mỗi đoạn có thể là một kết nối khác nhau và **metadata không giữ nguyên end-to-end**. Hệ thống cần **session IDs, connection IDs, NAT mappings, proxy transaction IDs và UTC timestamps** để tương quan; không nối các dòng chỉ vì chúng có cùng TCP port 443.

## 3. TLS 1.2 handshake: những trường có thể nhìn thấy

Trong nhiều **TLS 1.2 full handshakes** qua TCP, bản ghi ClientHello và phần lớn thông tin chứng thư của máy chủ được gửi **trước khi hai bên bắt đầu bảo vệ application traffic**. Vì vậy một passive sensor bắt đầu capture đúng thời điểm có thể phân tích chúng.

### 3.1. Luồng giản lược

~~~mermaid
sequenceDiagram
    participant C as TLS client
    participant N as Passive sensor
    participant S as TLS server
    C->>S: ClientHello (SNI, ALPN offer, suites, extensions...)
    Note over N: Có thể thấy ClientHello khi đi qua sensor
    S-->>C: ServerHello, Certificate, key exchange...
    Note over N: TLS 1.2 full handshake thường lộ server certificate chain
    C->>S: Key establishment + Finished (protected theo tiến trình)
    S-->>C: Finished
    C<<->>S: Application Data (encrypted)
~~~

Sơ đồ bỏ qua nhiều messages/biến thể. **TLS 1.2 resumption**, cipher suites và các kiểu key exchange có thể làm handshake khác đi; không khẳng định mọi phiên TLS 1.2 đều gửi certificate chain đầy đủ.

### 3.2. Dữ liệu có thể có trong TLS 1.2

| Trường | Thường quan sát được ở full handshake? | Diễn giải đúng |
| --- | --- | --- |
| **ClientHello version/cipher list/extensions** | Có | Những thuật toán/tính năng client đề xuất; không nhất thiết là thứ được chọn |
| **SNI extension** | Có nếu client gửi | Hostname được client đề nghị; không phải HTTP URL |
| **ALPN offered protocols** | Có nếu client gửi | Các giao thức ứng dụng đề xuất, như h2 và http/1.1 |
| **ServerHello selected parameters** | Có trong TLS 1.2 | Tham số negotiated theo handshake |
| **Server certificate chain** | Thường có trong full certificate handshake | Có thể trích issuer/SAN/validity; không xác nhận app operation |
| **Encrypted application records** | Có packet và record metadata | Payload không đọc được nếu không có giải mã được ủy quyền |
| **HTTP Host/path/body** | Không trong passive encrypted traffic | Cần điểm giải mã/ứng dụng logs |

### 3.3. Session resumption và những trường bị thiếu

TLS 1.2 có **abbreviated handshake/session resumption**. Một sensor có thể thấy handshake ít messages hơn và **không có Certificate message** mới. Nếu chỉ nhìn một connection được resumed mà kết luận “máy chủ không có certificate” là sai.

Để suy ra certificate identity trong các kết nối resumed, cần **evidence từ initial authenticated handshake, endpoint/app logs hoặc inventory đáng tin**, đồng thời phải hiểu **session binding, ticket/caching và thời hạn**.

### 3.4. Server certificate thấy được không đồng nghĩa đã được client tin

Một passive sensor có thể đọc certificate chain được gửi trong TLS 1.2, nhưng không mặc nhiên biết:

- Client có **verify CA trust chain** không.
- Client có kiểm tra **DNS hostname/IP SAN** không.
- Client có bỏ qua lỗi certificate không.
- Application có dùng **pinning** hoặc trust store riêng không.
- Handshake có hoàn tất thành công và request có xảy ra không.

Certificate metadata là **đầu vào đánh giá**, không phải bằng chứng client đã xác thực server đúng cách.

## 4. TLS 1.3: metadata ngoài vẫn có, nhiều handshake fields đã được mã hóa

TLS 1.3 thay đổi đáng kể vị trí các messages được bảo vệ. **ClientHello ban đầu vẫn có các trường quan sát được** trong trường hợp không dùng ECH, nhưng sau ServerHello, phần lớn handshake tiếp theo (như **EncryptedExtensions, Certificate, CertificateVerify, Finished**) được mã hóa.

### 4.1. Sơ đồ quan sát

~~~mermaid
sequenceDiagram
    participant C as TLS 1.3 client
    participant O as Passive observer
    participant S as TLS 1.3 server
    C->>S: ClientHello (cleartext fields if no ECH)
    Note over O: Quan sát thông tin ClientHello có thể có
    S-->>C: ServerHello
    Note over O: Quan sát phần ServerHello có thể có
    S-->>C: EncryptedExtensions + Certificate + Finished (encrypted)
    C->>S: Finished (encrypted)
    C<<->>S: Application Data (encrypted)
    Note over O: Không đọc server Certificate trong TLS 1.3 bình thường
~~~

Sơ đồ là bản giản lược của **TLS 1.3 full handshake**; PSK, resumption, HelloRetryRequest và 0-RTT có thể thay thứ tự/mức quan sát.

### 4.2. So sánh nhanh TLS 1.2 và TLS 1.3

| Thành phần | TLS 1.2 full handshake điển hình | TLS 1.3 full handshake điển hình |
| --- | --- | --- |
| ClientHello ban đầu | Quan sát được nhiều fields | Quan sát được outer ClientHello khi chưa có ECH hoặc phần outer ECH |
| SNI | Thường thấy nếu gửi | Thường thấy nếu không có ECH; inner SNI được bảo vệ khi ECH hoạt động |
| Client ALPN offered | Thường thấy | Thường thấy nếu không bị che trong ECH inner |
| Server selected ALPN | Có thể quan sát trong handshake TLS 1.2 | Nằm trong **EncryptedExtensions**, không đọc được bằng passive sensor thông thường |
| Server certificate | Thường nhìn thấy trong full handshake | **Certificate message đã được mã hóa** |
| HTTP content | Được mã hóa | Được mã hóa |
| Session resumption | Có thể không lặp đầy đủ certificates | PSK/resumption có thể bỏ certificate handshake |
| 0-RTT | Không có kiểu TLS 1.3 0-RTT | Có thể có early data, được mã hóa và có risk model riêng |

**Điểm cốt lõi:** không thể dùng passive TLS 1.3 capture để trích ra server certificate như cách một công cụ thường làm với TLS 1.2 full handshake; nếu dashboard vẫn hiển thị certificate thì phải kiểm tra **nguồn khác** hoặc phương thức thu thập có quyền.

### 4.3. Legacy version marker và downgrade confusion

Trường **legacy_version** trong TLS 1.3 ClientHello/ServerHello không được dùng đơn độc để kết luận negotiated TLS version. TLS 1.3 báo hiệu phiên bản qua **supported_versions extension**; một parser cũ có thể gán nhãn TLS 1.2 sai vì chỉ nhìn legacy record/version fields.

Để xây KPI “TLS 1.3 adoption”, cần:

- Protocol parser hỗ trợ TLS 1.3.
- Phân biệt **offered versions** và **negotiated version**.
- Chú ý captured handshake đủ hay midstream.
- Có thể phải kết hợp **server/proxy logs** nếu trường negotiated không quan sát được đáng tin.

### 4.4. Early data và 0-RTT

TLS 1.3 có cơ chế **0-RTT early data** trong những trường hợp resumption được hỗ trợ. Early data vẫn được mã hóa, nên sensor passive không đọc plaintext. Tuy nhiên, 0-RTT có **rủi ro replay** và application/server cần policy phù hợp cho các thao tác có side effects.

Không dùng “không đọc được early data” để suy **không có request**; cũng không khẳng định mọi TLS 1.3 session đều dùng 0-RTT.

## 5. Bảng mức quan sát theo giao thức và vị trí

| Thuộc tính | TLS 1.2 full trên TCP | TLS 1.3 trên TCP, không ECH | TLS 1.3 có ECH hoạt động | QUIC/HTTP/3 |
| --- | --- | --- | --- | --- |
| IP/port/packet timing ngoài mã hóa | Thấy ở điểm capture | Thấy | Thấy | Thấy UDP/IP và QUIC envelope thích hợp |
| ClientHello offered ciphers/extensions | Thường thấy | Thường thấy | Thấy **outer**, inner được che | Initial handshake có khả năng giải mã với hỗ trợ phiên bản, nhưng ECH vẫn che inner |
| SNI hostname thực | Thấy nếu client gửi | Thấy nếu client gửi | **Không đáng tin từ outer SNI** | Có thể thấy khi không ECH và decode đúng Initial; ECH che inner |
| ALPN offered thực | Thấy nếu gửi | Thấy nếu gửi | Inner có thể bị che | Có thể có trong Initial handshake nếu decode được và không ECH |
| ALPN cuối cùng được chọn | Có thể thấy | Được mã hóa trong TLS 1.3 | Được bảo vệ | Được bảo vệ trong TLS handshake của QUIC |
| Server certificate của full handshake | Thường thấy | Được mã hóa | Được mã hóa | Được mã hóa |
| HTTP method/path/headers/body | Không | Không | Không | Không |
| JA3/JA4-style fingerprint | Có nếu đủ handshake | Có tùy parser | Outer fingerprint có thể chỉ phản ánh ECH-facing features | Cần fingerprint model hỗ trợ QUIC và trạng thái ECH |
| Packet/flow volume inference | Có | Có | Có | Có, nhưng migration/multiplexing thay đổi ý nghĩa |

**Cảnh báo:** “Thấy” ở bảng là khả năng trong điều kiện **có packet capture đầy đủ và parser phù hợp**, không phải cam kết mọi deployment/phiên đều có giá trị đó. TLS 1.3 over TCP và TLS 1.3 handshake trong QUIC có cấu trúc truyền dẫn khác nhau.

### 5.1. Không đồng nhất “handshake observed” và “application accessed”

Khi thấy ClientHello, có thể client:

- Bị từ chối vì trust/TLS mismatch.
- Bị rate-limit hoặc firewall/ngắt kết nối.
- Chỉ thử connectivity/health check.
- Hoàn thành TLS nhưng bị ứng dụng trả 401/403.
- Mở HTTP/2 connection nhưng không gửi request nào đáng kể.

Muốn kết luận đã truy cập tài nguyên, cần **handshake completion**, network outcome và **ứng dụng/proxy log** phù hợp.

## 6. TLS metadata inventory: trường nào hữu ích, giới hạn ở đâu?

### 6.1. Network five-tuple và session metadata

Một flow thường được mô tả bằng **source IP, source port, destination IP, destination port và transport protocol**. Bổ sung start/end, packets, bytes, TCP flags, direction và NAT mappings giúp nhóm flow.

Giới hạn:

- NAT gộp nhiều người dùng thành cùng public IP.
- DHCP/IP reuse và IPv6 privacy addresses làm ánh xạ thiết bị thay đổi.
- HTTP/2 multiplex nhiều request trong một TLS/TCP connection.
- QUIC connection migration/CID có thể duy trì logical connection khi five-tuple thay đổi.
- Packet capture chỉ một chiều hoặc sampler không thấy toàn lưu lượng.

Không lấy số lượng TCP connections làm **số lượng HTTP requests**.

### 6.2. TLS version và cryptographic parameters

Metadata có thể hỗ trợ:

- Phát hiện **client còn đề xuất các phiên bản/cipher suites yếu**.
- Kiểm tra baseline migration từ TLS 1.2 sang TLS 1.3.
- Phát hiện handshake pattern bất thường ở nhóm server/clients.
- Xây **inventory theo client family** khi có thêm endpoint/application evidence.

Nhưng offered suites khác negotiated suite. Không tự báo “server dùng cipher X” chỉ vì ClientHello liệt kê X.

### 6.3. SNI và ALPN offered

- **SNI**: hint hostname client muốn kết nối trước khi TLS được hình thành, khi không bị ECH che.
- **ALPN offered list**: client đề xuất giao thức ứng dụng như **h2**, **http/1.1**, **h3** trong ngữ cảnh thích hợp.
- **Selected ALPN**: giao thức hai bên thống nhất, có thể không quan sát trực tiếp trong TLS 1.3 passive capture.

Một ClientHello có h2 trong danh sách **không chứng minh** HTTP/2 được chọn. Nếu client gửi SNI là một hostname, chưa đủ chứng minh nó gửi đúng HTTP Host/:authority hoặc đi tới resource/business endpoint nào.

### 6.4. Record lengths, duration, timing

Kích thước/timing có thể giúp:

- Ước lượng **volume outbound** theo host/service/network zone.
- Nhận diện **định kỳ connection attempts**, retries hoặc burst traffic.
- Phát hiện **large data transfer** khác baseline của một resource.
- Gắn context cho **sudden destination changes** và incident time window.

Hạn chế: cùng một mẫu có thể do **backup, video meeting, software updates, telemetry agent hoặc malware**. HTTP/2/3 multiplex, CDN, congestion, compression và padding có thể làm traffic-shape thay đổi mà nội dung không đổi.

### 6.5. Metadata nên được đặt nhãn confidence

Ví dụ một normalized event:

~~~json
{
  "observation": "TLS ClientHello contained SNI",
  "sni": "api.partner.example",
  "evidence_type": "observed_handshake_field",
  "claim_allowed": "client proposed this hostname",
  "claim_not_supported": "client posted customer data to this URL",
  "capture_completeness": "client_hello_present",
  "tls_termination_present": false
}
~~~

Đây là **schema minh họa**, không phải output chuẩn từ một IDS. Mục đích là ngăn việc chuyển thông tin parser thẳng thành kết luận về hành vi người dùng.

## 7. SNI, ECH và vì sao hostname ngày càng khó quan sát

### 7.1. SNI trong ClientHello truyền thống

**Server Name Indication (SNI)** là extension cho phép client nêu hostname mà nó muốn TLS server phục vụ. Trong trường hợp thông thường không dùng ECH, một passive observer có thể đọc được hostname đó từ ClientHello.

Ví dụ:

~~~text
Client IP:       192.0.2.10
Destination IP:  203.0.113.20
Destination:     TCP 443
Observed SNI:    billing.partner.example
Observed ALPN:   h2, http/1.1
~~~

Chỉ từ dữ liệu này, có thể nói client **đề nghị** kết nối tới billing.partner.example. Không kết luận đã gọi URL **/invoices/2026**, không xác nhận server certificate đã được client verify và không biết response body.

### 7.2. SNI không phải authentication

SNI do client cung cấp có thể:

- Không khớp certificate/hostname sau handshake, khiến TLS client từ chối.
- Là giá trị bất thường hoặc cố ý giả mạo trong một probe.
- Khác HTTP **Host/:authority** được truyền bên trong TLS trong một số tình huống.
- Không xuất hiện vì client dùng IP literal, cấu hình riêng hoặc cơ chế bảo vệ hostname.
- Được sử dụng với nhiều dịch vụ/CDN trên cùng IP.

Một hệ thống kiểm soát egress chỉ dựa trên SNI **không thay TLS server identity verification, DNS control hoặc network/application authorization**.

### 7.3. Encrypted ClientHello (ECH)

**ECH** là cơ chế giúp mã hóa phần **ClientHelloInner** chứa các chi tiết nhạy cảm, bao gồm hostname thực trong SNI, khi client/server hỗ trợ và sử dụng đúng. Một observer bên ngoài có thể nhìn thấy **ClientHelloOuter** với những trường dành cho kết nối bên ngoài, nhưng **không nên coi outer SNI/public name là hostname ứng dụng thật**.

~~~mermaid
flowchart LR
    C["TLS client"] --> O["ClientHelloOuter có thể nhìn thấy"]
    C --> I["ClientHelloInner được mã hóa bằng ECH"]
    I --> O
    O --> N["Passive network sensor"]
    N --> D["Outer fields, IP/port/timing; inner SNI bị che"]
    O --> S["ECH-capable server/frontend"]
    S --> X["Khôi phục inner context theo thiết kế ECH"]
~~~

Sơ đồ chỉ giải thích **vùng quan sát**. Việc ECH được offer/accepted, retry config, public name, certificate handling và nội dung outer thay đổi theo implementation và cấu hình. Không tuyên bố tất cả TLS hiện nay đều có ECH hoặc một passive observer luôn xác định chắc chắn ECH đã được chấp nhận.

### 7.4. Tác động tới giám sát

Nếu tổ chức trước đây xây rule:

~~~text
IF ClientHello SNI == blocked.example
THEN raise critical alert
~~~

thì ECH có thể khiến **hostname thực không xuất hiện** tại passive sensor. Điều này không có nghĩa client không truy cập domain đó, cũng không chứng minh người dùng cố tình tránh giám sát.

Biện pháp phù hợp:

1. Ghi rõ **SNI observed / absent / outer-only / unknown** theo khả năng parser.
2. Dùng **managed DNS resolver/enterprise proxy/endpoint/application logs** khi có căn cứ và quyền.
3. Áp **network egress controls** tới nơi bắt buộc như proxy/gateway, không chỉ dựa trên một chuỗi trong ClientHello.
4. Đánh giá chính sách doanh nghiệp đối với **ECH** theo threat model và quyền riêng tư; không mặc định chặn toàn bộ lưu lượng mới chỉ vì không nhìn thấy SNI.
5. Chuyển báo cáo từ **exact-domain visibility** sang những metric có thể được chứng minh khi hostname không quan sát được.

### 7.5. Chặn ECH không tự phục hồi mọi visibility

Các chiến lược vô hiệu hóa/chặn ECH có thể ảnh hưởng tới **compatibility, privacy, quy định, hiệu quả bảo mật và các giao thức khác**. Kể cả khi ClientHello còn cleartext, passive sensor vẫn không đọc được **HTTP body trong TLS**. Vì vậy, không nên quảng bá việc “tắt ECH” là cách quan sát toàn bộ nội dung HTTPS.

## 8. DNS metadata và giới hạn khi dùng để suy hostname TLS

**DNS logs** là nguồn bổ trợ nhưng không thay SNI hoặc application logs.

### 8.1. Liên kết DNS và TLS có điều kiện

Một user query DNS cho **api.partner.example**, sau đó kết nối tới IP được trả về, có thể gợi ý ý định sử dụng host đó. Nhưng:

- DNS cache/client cache có thể khiến **không xuất hiện query mới**.
- Một IP CDN phục vụ **nhiều hostnames**.
- Prefetch/speculative DNS lookup có thể diễn ra **mà không có connection**.
- Client có thể dùng **DoH, DoT, DoQ, DNS proxy hoặc hardcoded IP** khác resolver doanh nghiệp.
- Record TTL thấp hoặc DNS failover làm IP thay đổi rất nhanh.
- Resolver logs có thể ghi **DNS resolver IP** thay vì đúng user khi nhiều clients cùng dùng forwarder.

### 8.2. DoH/DoT/DoQ và quyền quan sát

DNS-over-HTTPS (DoH), DNS-over-TLS (DoT) và DNS-over-QUIC (DoQ) mã hóa nội dung DNS trên các transports phù hợp. Passive sensor đặt giữa client và resolver có thể thấy **một kết nối mã hóa tới resolver** nhưng không tự đọc được các câu hỏi DNS bên trong.

Tuy nhiên, DNS logs tại **resolver do tổ chức vận hành** có thể vẫn chứa truy vấn nếu nguồn đó thật sự nhận và ghi log hợp lệ. Đừng nói “DoH đồng nghĩa không ai có thể ghi DNS” hoặc “DoH luôn là hành vi tấn công”.

### 8.3. Domain attribution là suy luận có confidence

Một mẫu event có thể:

~~~json
{
  "flow_id": "flow-demo-201",
  "destination_ip": "203.0.113.20",
  "observed_sni": null,
  "related_dns_name": "api.partner.example",
  "dns_correlation_window_seconds": 30,
  "domain_attribution": "inferred_from_managed_resolver",
  "attribution_confidence": "medium",
  "limitations": [
    "shared CDN IP",
    "DNS caching",
    "resolver-client mapping"
  ]
}
~~~

Đây là **schema minh họa**, không phải bằng chứng tên miền cuối cùng đã được TLS xác minh. Nếu nhiều hostname cùng trỏ tới một IP và nhiều clients dùng NAT, attribution có thể yếu.

### 8.4. DNS + ECH không khôi phục plaintext

Ngay cả khi managed resolver biết hostname thực, network sensor không tự biết **HTTP URL path, request headers hay body**. DNS correlation chủ yếu hỗ trợ **resource attribution và policy analytics**, không phải HTTP content inspection.

## 9. ALPN, extensions và version negotiation: đọc đúng handshake

### 9.1. ALPN offered khác selected protocol

**Application-Layer Protocol Negotiation (ALPN)** cho phép client đề xuất giao thức application chạy trên TLS. Một ClientHello có thể liệt kê:

~~~text
Offered ALPN:
  h2
  http/1.1
~~~

Không thể suy từ danh sách này rằng **HTTP/2 đã được chọn**. Với TLS 1.3, server-selected ALPN nằm trong **EncryptedExtensions** và không hiển thị cho passive observer nếu không có thông tin giải mã thích hợp.

### 9.2. Nhận diện QUIC/HTTP/3 phải dùng đúng ngữ cảnh

HTTP/3 thông thường chạy trên **QUIC**, QUIC bảo vệ giao tiếp dựa trên TLS 1.3 nhưng không đóng gói giống TLS records trên TCP. Parser chỉ nhận dạng **TCP port 443** có thể bỏ qua **UDP port 443**, dù UDP 443 không phải lúc nào cũng là QUIC.

Một client ALPN có **h3** trong QUIC handshake hỗ trợ nhận diện HTTP/3, nhưng vẫn phải phân biệt:

- QUIC version/header parsing.
- TLS handshake information qua CRYPTO frames.
- Negotiation thành công vs chỉ đề xuất.
- HTTP/3 request contents luôn nằm trong phần được bảo vệ.

### 9.3. Cipher suites và extensions là tín hiệu, không phải định danh user

TLS libraries, browser versions, OS stacks và middleboxes có fingerprint khác nhau. Nhưng nhiều người dùng có thể dùng **cùng TLS library**, và một client có thể thay thứ tự extension do cập nhật, GREASE hoặc randomization.

Không coi một danh sách cipher/extensions lạ là bằng chứng malware, đặc biệt khi không có **process identity, destination reputation, time-series baseline và application context**.

## 10. QUIC: quan sát UDP, Initial và giới hạn sau handshake

QUIC tích hợp TLS 1.3 handshake vào cơ chế truyền tải của mình. Dù QUIC mã hóa phần lớn packet payload, **một số thông tin trong header vẫn hỗ trợ định tuyến/connection management**.

### 10.1. Các trường network observer có thể thấy

| Thuộc tính | Khả năng quan sát | Ghi chú |
| --- | --- | --- |
| **UDP source/destination IP/port** | Thấy tại điểm capture | UDP/443 phổ biến nhưng không đồng nghĩa QUIC trong mọi trường hợp |
| **Packet length, timing, direction** | Thấy | Không xác định HTTP request body |
| **QUIC version và một số header fields** | Có thể phân tích trong packets phù hợp | Version negotiation, long/short header khác nhau |
| **Connection IDs** | Có thể quan sát ở những packets/headers thích hợp | Giúp liên hệ paths trong một số điều kiện; không phải user identity |
| **TLS ClientHello trong QUIC Initial** | Có thể decode với parser hỗ trợ QUIC version | Initial protection của QUIC v1 không nhằm giữ bí mật trước passive observer; ECH vẫn che ClientHelloInner |
| **Handshake/1-RTT protected payloads** | Không đọc được bởi passive sensor thông thường | QUIC mã hóa frames và HTTP/3 nội dung |
| **HTTP/3 method/path/body** | Không | Cần endpoint/proxy/application telemetry có quyền |

### 10.2. Điểm đặc biệt của QUIC Initial

Với **QUIC version 1**, bí mật bảo vệ các Initial packets được dẫn xuất theo thuật toán từ những thông tin quan sát được trong Initial header. Vì vậy một công cụ phân tích có thể **bỏ Initial packet protection và đọc TLS ClientHello** mà không có private key của server, trong điều kiện packet và phiên bản được hỗ trợ.

Điều này **không áp dụng cho toàn bộ traffic QUIC**. Các giai đoạn handshake tiếp theo và 1-RTT application data được bảo vệ bằng secrets khác. Các QUIC versions/cấu hình cũng có thể thay cách diễn giải, nên không viết rule “QUIC Initial luôn đọc được mọi field”.

### 10.3. Connection migration và thay đổi five-tuple

QUIC có thể hỗ trợ **connection migration** hoặc đường mạng đổi giữa Wi-Fi/cellular, làm source IP/port thay đổi nhưng logical connection vẫn tồn tại theo cơ chế QUIC. Tính năng Connection ID có thể hỗ trợ endpoints định tuyến packet, nhưng:

- Không phải mọi connection sử dụng migration giống nhau.
- CID có thể thay đổi vì privacy, routing hoặc rotation.
- Không nên coi CID là **định danh người dùng lâu dài**.
- L7 request count không thể suy trực tiếp từ số UDP five-tuples.

### 10.4. Multiplexing và packet-size analysis

HTTP/3 hỗ trợ nhiều streams trên một QUIC connection, đồng thời QUIC có ACK, retransmission và flow-control behavior riêng. Một burst UDP packets có thể chứa nhiều streams hoặc packetization khác nhau.

**Bytes/packets lớn không chứng minh một file nhạy cảm đã bị upload.** Chỉ có thể nêu **outbound data volume bất thường so với baseline**, rồi dùng endpoint/app/audit evidence xác minh.

### 10.5. QUIC fallback và policy coverage

Một browser có thể thử HTTP/3 qua QUIC rồi fallback sang HTTP/2 trên TLS/TCP nếu QUIC không dùng được. Một detection chỉ theo TCP ClientHello hoặc một firewall chỉ giám sát UDP/443 có thể:

- Thấy hai connection attempts cho một phiên truy cập.
- Bỏ sót flow ở transport còn lại.
- Hiểu sai retransmission/fallback là beaconing.

Metric “TLS coverage” nên thống nhất scope **TLS-over-TCP và QUIC-based TLS** nếu ứng dụng yêu cầu.

## 11. JA3, JA3S, JA4-style fingerprinting: dùng làm tín hiệu hỗ trợ

**TLS fingerprinting** biến một tập trường ClientHello/handshake thành chuỗi/hash hoặc representation để nhóm các clients. Chẳng hạn **JA3** truyền thống sử dụng các trường như TLS version, cipher suites, extension list, elliptic-curve supported groups và EC point formats; các giá trị kiểu **GREASE** thường được loại theo quy tắc thuật toán.

### 11.1. Fingerprint giúp điều gì?

- Phát hiện client family/thư viện TLS xuất hiện lần đầu trong môi trường.
- Tìm flows có handshake profiles tương tự một mẫu đang điều tra.
- Kết hợp với **destination/time/bytes/EDR process** để ưu tiên triage.
- Phát hiện một server/service đột ngột có clients thuộc nhóm không thường thấy.
- Theo dõi tác động cập nhật TLS stack/browser ở mức cohort.

### 11.2. Những điều không thể kết luận

- **JA3 hash không phải người dùng hoặc thiết bị duy nhất**.
- Nhiều ứng dụng dùng chung library có thể cho fingerprint giống nhau.
- Malware có thể **mô phỏng fingerprint browser**, hoặc benign tools có profile lạ.
- Extension ordering/GREASE/randomization làm giá trị thay đổi.
- Handshake visibility bị ảnh hưởng **ECH, QUIC, resumption, middleboxes**.
- Server response fingerprint không cho thấy nội dung HTTP.
- Cách tính JA4-style fingerprints và field definitions **phụ thuộc thuật toán/phiên bản/implementation**; đừng gộp các loại fingerprint khác nguồn mà không chuẩn hóa.

### 11.3. Một detection yếu và một detection tốt hơn

~~~text
WEAK RULE:
  IF ja3 == "hash-of-interest" THEN "confirmed malware"

BETTER HYPOTHESIS:
  IF tls_client_fingerprint in investigation watchlist
     AND destination previously unseen for this endpoint/process
     AND egress bytes/timing differ materially from the cohort
     AND endpoint/process telemetry does not match approved software
  THEN prioritize triage with confidence + evidence IDs.
~~~

Hash và các field chỉ minh họa; không có mẫu hash cụ thể nào được tuyên bố độc hại.

### 11.4. Baseline và drift

Fingerprint rule cần có:

1. **Baseline period** theo OS/browser/library/app cohort.
2. Cập nhật phiên bản TLS stack gây những thay đổi gì.
3. Correlation với **process, certificate identity khi có nguồn hợp lệ, DNS, remote service**.
4. False-positive review và test cases có nhãn.
5. Time-to-live của IOC và rule owner.

Nếu gần như toàn bộ laptops vừa cập nhật browser, một fingerprint mới xuất hiện hàng loạt là **expected drift** cho tới khi có bằng chứng ngược lại, không phải chiến dịch tấn công được xác nhận.

### 11.5. JA4-style không giải quyết bài toán ECH hoàn toàn

Những phương pháp fingerprint ổn định hơn có thể giảm độ nhạy với extension ordering, nhưng **không giải mã ClientHelloInner hay application body**. Khi ECH được dùng, fingerprint từ outer fields phản ánh **outer handshake**, có thể không mang đủ đặc trưng của application client mà analytics kỳ vọng.

## 12. Giới hạn khi suy nội dung HTTP/API từ metadata TLS

Một **HTTPS connection** có thể chứa:

- 0 HTTP requests do handshake/test/idle connection.
- 1 hoặc nhiều HTTP/1.1 requests theo reuse semantics.
- Nhiều HTTP/2 streams được multiplex.
- Nhiều HTTP/3 streams trên QUIC.
- Upload, download, long-polling hoặc WebSocket được bảo vệ.

Do vậy:

| Kết luận | Passive TLS metadata đủ chứng minh? | Bằng chứng bổ sung cần có |
| --- | --- | --- |
| Client kết nối IP:port tại một thời điểm | Có nếu packet/flow capture đúng | NAT mapping nếu muốn biết endpoint thực |
| Client đề xuất SNI hostname cụ thể | Có nếu trường quan sát được và parser đúng | Lưu ý ECH/outer SNI |
| Client truy cập URL path cụ thể | **Không** | Authorized proxy/app access log hoặc endpoint telemetry |
| User gửi Authorization token nào | **Không** | Không nên thu token raw; app auth event/log đã làm sạch |
| Server trả HTTP 200/403 | **Không** | Proxy/app logs có quyền |
| Có dữ liệu lớn đi ra external IP | Có thể ước lượng flow bytes | Hướng, NAT, retransmits, application context |
| Dữ liệu đó là hồ sơ khách hàng | **Không** | DLP/app audit hoặc điều tra được phép, có kiểm soát dữ liệu |
| TLS server certificate đã được client verify | **Không trực tiếp** | Client/server-side TLS validation result |
| Connection hoàn tất một giao dịch thanh toán | **Không** | Business transaction audit và request correlation |
| Traffic có biểu hiện beaconing | Có thể hình thành giả thuyết | Baseline, endpoint/process evidence, test khác |

**Quy tắc điều tra:** không chuyển một **inference** thành một **confirmed application action** nếu chưa có bằng chứng tại tầng ứng dụng hoặc endpoint.

## 13. TLS termination và giải mã: khi nào nội dung có thể được quan sát?

Quan sát nội dung ứng dụng chỉ có thể xảy ra tại nơi **có plaintext theo thiết kế** hoặc khi một hệ thống có **cơ chế giải mã được ủy quyền với vật liệu khóa và ngữ cảnh phù hợp**. Không nên coi private key máy chủ TLS là một “chìa khóa vạn năng” mở mọi phiên đã capture.

### 13.1. Bốn mô hình

| Mô hình | Ai thấy nội dung? | Điều kiện và rủi ro |
| --- | --- | --- |
| **Passive metadata monitoring** | Không đọc HTTPS application content | Ít tác động đường dữ liệu, phụ thuộc handshake visibility |
| **TLS termination tại reverse proxy/LB** | Proxy và backend sau termination theo kiến trúc | Proxy xử lý plaintext, cần log redaction, authorization và cert lifecycle |
| **Forward-proxy TLS inspection** | Proxy được endpoint tin và được phép terminate rồi tạo TLS mới | Thay đổi trust boundary; yêu cầu chính sách, client trust và privacy governance |
| **Endpoint-assisted decryption/diagnostics** | Authorized client/server diagnostic tooling được cung cấp session secrets trong lab | Session secrets cực nhạy cảm, chỉ dùng controlled scope và TTL |

### 13.2. TLS 1.3, forward secrecy và private key

TLS 1.3 sử dụng cơ chế trao đổi khóa hiện đại hướng tới **forward secrecy**; chỉ có **server certificate private key** thông thường không đủ để thụ động giải mã toàn bộ TLS 1.3 connections đã capture.

Với TLS 1.2, tính khả thi của giải mã từ server private key còn **phụ thuộc key exchange**: ví dụ một số legacy RSA key transport khác với các phiên ECDHE có forward secrecy. Không hướng dẫn vận hành dựa trên giả định “có certificate key thì đọc được mọi HTTPS”.

### 13.3. TLS key logging trong lab

Một số TLS clients/browsers hỗ trợ xuất **session secrets** để phục vụ debug. Trong một **lab thuộc quyền quản trị**, analyst có thể kết hợp secrets và PCAP để xem traffic theo đúng phiên/giao thức được hỗ trợ.

Nhưng:

- File session secrets có thể cho phép giải mã **dữ liệu nhạy cảm của nhiều phiên** trong phạm vi nó chứa.
- Không bật thu keylog đại trà trên endpoints production.
- Không tải secrets/PCAP lên dịch vụ bên ngoài không được phê duyệt.
- Giới hạn người truy cập, phân vùng, mã hóa lưu trữ và **xóa theo thời hạn**.
- Việc giải mã có thể vẫn không thành công nếu capture thiếu packets, library/QUIC version không được hỗ trợ hoặc secrets không khớp.

Một **PCAP sau giải mã trong lab** không đại diện cho những gì IDS passive có thể quan sát ở production.

### 13.4. TLS inspection có thể ảnh hưởng chức năng

Khi một proxy thay đổi điểm TLS termination, nó có thể ảnh hưởng:

- **Client certificate/mTLS authentication** giữa app và external server.
- **Certificate pinning**, custom trust stores và security controls của ứng dụng.
- HTTP/2, HTTP/3, gRPC, WebSocket, streaming, ALPN và TLS negotiation.
- Khả năng xác minh server identity, CA rotation và policy về TLS versions.
- Quyền riêng tư, dữ liệu tài chính/y tế/nội bộ và pháp lý.
- Băng thông, latency, resource capacity và availability của proxy.

Không chấp nhận **insecure certificate verification** như một giải pháp cho lỗi inspection. Với trường hợp không thể inspection, nên dùng **endpoint/app telemetry, network policy và metadata phù hợp** thay vì tự động downgrade security.

### 13.5. Log nội dung chỉ khi có mục đích rõ

Một proxy có thể thấy HTTP headers và body, nhưng điều đó không có nghĩa nên lưu tất cả chúng. Ưu tiên:

- **Request ID, authenticated principal, route/template, status, bytes, timing**.
- Redact **tokens, passwords, cookies, card data và PII**.
- Hạn chế logs chi tiết theo **incident, app, TTL và approval**.
- Tách app business evidence khỏi raw network capture.

**Có khả năng giải mã không đồng nghĩa có quyền thu thập nội dung.**

## 14. Thiết kế telemetry pipeline cho encrypted traffic

Một kiến trúc kết hợp network và endpoint evidence có thể như sau:

~~~mermaid
flowchart LR
    T["TAP/SPAN / virtual mirroring"] --> N["Zeek / Suricata / packet sensor"]
    F["NetFlow / IPFIX / firewall / NAT"] --> B["Normalizer + enrichment"]
    N --> B
    D["Managed DNS resolver"] --> B
    P["Proxy / LB / WAF TLS termination logs"] --> B
    E["EDR / process / app audit"] --> B
    B --> Q["Quality, dedup, timestamps, confidence"]
    Q --> S["SIEM / NDR detections"]
    Q --> M["Dashboards / metrics"]
    S --> R["SOC triage / response"]
~~~

### 14.1. Thu thập ở đúng vantage

| Nguồn | Lợi ích | Giới hạn |
| --- | --- | --- |
| **TAP/SPAN hoặc cloud packet mirroring** | Quan sát packets/handshake tại đường mạng | Không thấy traffic không đi qua sensor; capture có thể drop/mirror sai |
| **Zeek protocol logs** | Chuẩn hóa TLS/conn/DNS-related metadata khi parser nhận diện | Không tự giải mã HTTPS; log fields tùy phiên bản/protocol |
| **Suricata EVE TLS/flow events** | TLS metadata, IDS events và flow telemetry | Khả năng parser/signature phụ thuộc phiên bản/cấu hình |
| **NetFlow/IPFIX/sFlow** | Theo dõi hướng, bytes, packets, flows ở quy mô lớn | Sampling/aggregation, thường không có TLS ClientHello |
| **Firewall/NAT logs** | Allow/deny path và public source mappings | NAT translation, log drops, không có HTTP payload |
| **Managed DNS logs** | Domain queries/answers từ resolver được quản lý | Cache, DoH/DoT/DoQ và client-to-resolver mapping |
| **Proxy/LB/WAF logs** | HTTP details nếu TLS terminate hợp lệ | Không phải mọi traffic đều qua proxy; sensitive data risk |
| **EDR/app logs** | Process identity, user/operation, validation outcome | Endpoint tampering, permission/retention và coverage |

### 14.2. Chọn điểm capture để thấy hai chiều

Một TLS parser muốn ghép đúng handshake thường cần:

- Thấy **client-to-server và server-to-client traffic** của cùng luồng.
- Bắt đầu capture **trước handshake**, không chỉ midstream.
- Không bị **packet loss, truncated snaplen** hoặc offload artifacts làm parser thiếu dữ liệu.
- Đúng network namespace/virtual switch/vNIC/subnet.
- Có timing đủ chính xác để correlate NAT/proxy/app events.

Trong mạng cloud, **asymmetric routing** có thể làm chỉ một chiều traffic đi qua sensor. Một gateway node có nhiều NIC hoặc overlay encapsulation có thể khiến capture nhìn thấy packet ở lớp khác dự kiến.

### 14.3. Cân nhắc throughput và storage

**Full PCAP** hữu ích cho điều tra nhưng tiêu tốn storage và chứa nhiều metadata nhạy cảm. Có thể chia dữ liệu:

1. **Flow counters** luôn thu trong vùng quan trọng theo năng lực và chính sách.
2. **TLS handshake metadata** khi parser và cảm biến có thể xử lý.
3. **Small bounded PCAP windows** theo change/incident có phê duyệt.
4. **Application audit events** giữ theo business/security retention.

Thiết kế **sampling, buffering, backpressure, packet drop metrics, log retention và loss alerts** trước khi công bố tỷ lệ quan sát.

### 14.4. Detection coverage không thể cao hơn sensor coverage

Nếu chỉ **70% egress paths** đi qua một NDR sensor, detection metrics của sensor đó không được diễn giải là bao phủ toàn bộ doanh nghiệp. Dashboard cần hiển thị:

- % **in-scope network paths instrumented**.
- % packets/flows bị drop hoặc sample theo từng sensor.
- % TLS connections có **ClientHello observed**.
- % event được correlate với **user/device/process/resource**.
- % flows **ECH suspected/observed, unknown SNI, QUIC vs TCP** theo cách phân loại và confidence được định nghĩa.

**“Unknown” là dữ liệu chất lượng đo lường, không phải mặc định benign hay malicious.**

## 15. Zeek, Suricata và normalized event examples

### 15.1. Zeek: conn.log và ssl.log

Trong nhiều triển khai Zeek, **conn.log** lưu connection-level telemetry, **ssl.log** có thể chứa TLS/SSL handshake-related fields; tùy plugin/version có thể có thông tin khác. Một số trường như **server_name, version, cipher, resumed, established** chỉ có khi parser/traffic hỗ trợ và không nên áp một schema cố định cho mọi version.

Ví dụ **JSON đã chuẩn hóa để học**, không phải bản ghi Zeek thô:

~~~json
{
  "source": "zeek-ssl-joined",
  "conn_uid": "C-demo-001",
  "orig_h": "192.0.2.10",
  "orig_p": 51342,
  "resp_h": "203.0.113.20",
  "resp_p": 443,
  "transport": "tcp",
  "tls_version_observed": "TLSv1.3",
  "client_sni_observed": "api.partner.example",
  "server_certificate_visible": false,
  "capture_scope": "client_hello_seen",
  "note": "Normalized example; actual Zeek logs vary"
}
~~~

**Lưu ý:** trường **server_certificate_visible** là nhãn do pipeline gán để giải thích coverage; không tuyên bố Zeek luôn phát sinh field đó.

### 15.2. Suricata: EVE flow và TLS events

Suricata có thể ghi TLS event fields, flow metadata và alerts trong **EVE JSON** khi cấu hình và parser hỗ trợ. Một normalized example:

~~~json
{
  "sensor": "suricata-edge",
  "event_type": "tls",
  "flow_id": "flow-demo-201",
  "src_ip": "192.0.2.10",
  "src_port": 51342,
  "dest_ip": "203.0.113.20",
  "dest_port": 443,
  "proto": "TCP",
  "tls": {
    "sni": "api.partner.example",
    "version": "TLS 1.3"
  },
  "pipeline_annotations": {
    "content_decrypted": false,
    "sni_confidence": "observed_when_no_ech"
  }
}
~~~

Đây **không phải schema EVE cam kết đúng mọi phiên bản**, đặc biệt trường **pipeline_annotations** là bổ sung do tổ chức tự định nghĩa. Kết hợp conn/flow/tls/events bằng **flow UID hoặc 5-tuple + time** với NAT/proxy caveats.

### 15.3. Những fields không nên luôn có giá trị

Trong nhiều luồng thực, **SNI, version, certificate, handshake completion, ALPN, fingerprint** có thể thiếu vì:

- Sensor chỉ thấy **midstream**.
- TLS resumption/PSK.
- ECH bảo vệ ClientHelloInner.
- QUIC version/parser không được hỗ trợ.
- Capture packet loss hoặc asymmetric path.
- Client thực sự không gửi extension.
- TLS được terminate tại proxy nằm trước cảm biến.

Đừng suy “SNI null = attacker cố tình che giấu” khi chưa loại trừ các nguyên nhân lành tính.

## 16. Công cụ kiểm tra trong lab có ủy quyền

Mục tiêu của lab là **xác định metadata quan sát được** trên đường truyền của **hệ thống do người thực hiện sở hữu**, không phải thu thập plaintext hoặc credentials của người khác.

### 16.1. Kiểm tra server TLS qua OpenSSL

~~~bash
# Chỉ dùng với TLS endpoint lab/do tổ chức sở hữu.
# Hostname .example ở đây phải được thay bằng hostname lab phù hợp.
openssl s_client \
  -connect tls-lab.example:443 \
  -servername tls-lab.example \
  -verify_hostname tls-lab.example \
  -verify_return_error \
  -brief
~~~

Lệnh **s_client** chủ động đóng vai TLS client, có thể hiển thị thông tin negotiated protocol/certificate verification mà **client này nhìn thấy**. Đừng coi output của s_client là điều một passive sensor trên Internet sẽ thấy, đặc biệt với **TLS 1.3 encrypted Certificate**.

### 16.2. So sánh TLS versions trong lab

~~~bash
# Chỉ khi lab server hỗ trợ; đây là phép kiểm tra chủ động.
openssl s_client -connect tls-lab.example:443 \
  -servername tls-lab.example -tls1_2 \
  -verify_hostname tls-lab.example -verify_return_error -brief

openssl s_client -connect tls-lab.example:443 \
  -servername tls-lab.example -tls1_3 \
  -verify_hostname tls-lab.example -verify_return_error -brief
~~~

Nếu một phiên bản không được server hỗ trợ theo chính sách, handshake có thể thất bại **đúng dự kiến**. Không hạ cấu hình production chỉ để tạo “success” khi thử TLS cũ.

### 16.3. Thu metadata gói tin theo phạm vi hẹp

~~~bash
# Chỉ ở interface và mạng được phép, giới hạn 100 packets.
# tcpdump tóm tắt packet headers, KHÔNG giải mã HTTPS payload.
sudo tcpdump -i eth0 -nn -c 100 'tcp port 443 or udp port 443'
~~~

Không capture ngẫu nhiên mọi interface/mọi user trên production. Nếu cần PCAP, phải có **change/incident authorization, thời gian, filter, storage/quyền và TTL**; một PCAP có thể chứa dữ liệu nhạy cảm ngay cả khi chủ yếu là TLS encrypted.

### 16.4. Xem TLS ClientHello trong capture đã được phép lưu

~~~bash
# trace.pcapng được thu trong lab. Field names có thể tùy TShark version.
tshark -r trace.pcapng \
  -Y 'tls.handshake.type == 1' \
  -T fields \
  -e frame.time_epoch \
  -e ip.src \
  -e ip.dst \
  -e tls.handshake.extensions_server_name
~~~

Nếu output SNI trống:

1. Capture có ClientHello phù hợp không?
2. Traffic thật là **QUIC** hay TCP?
3. Parser/version có hỗ trợ traffic không?
4. SNI thực không được gửi hay ECH khiến inner hostname không hiện?
5. Capture có packet loss hoặc snaplen không đủ?

Không “sửa” dữ liệu trống bằng cách giả định destination domain theo IP CDN.

### 16.5. TShark/Wireshark QUIC

~~~bash
# Lab capture: liệt kê QUIC packets nếu dissector nhận dạng được.
tshark -r trace.pcapng -Y 'quic' \
  -T fields -e frame.time_epoch -e ip.src -e ip.dst
~~~

Kết quả phụ thuộc **version/dissector/keys và packet capture**. Một QUIC initial packet có thể được giải mã để thấy một số TLS handshake fields, nhưng HTTP/3 requests không hiện plaintext chỉ nhờ packet capture.

### 16.6. Một bảng kết quả lab nên thu

| Test | Hành động | Kỳ vọng passive observation |
| --- | --- | --- |
| **L1 – TLS 1.2 full** | Kết nối tới server lab hỗ trợ TLS 1.2 | ClientHello; có thể thấy server certificate trong full handshake |
| **L2 – TLS 1.3 full** | Kết nối mới TLS 1.3 | ClientHello nếu không ECH; certificate không hiện plaintext trong passive capture |
| **L3 – Session resumption** | Reconnect bằng client lab có PSK/ticket | Handshake có thể rút gọn, metadata/cert thiếu |
| **L4 – ECH capable test** | Dùng môi trường ECH lab thực sự hỗ trợ | Outer ClientHello; không kết luận outer SNI là inner hostname |
| **L5 – QUIC/HTTP3** | Client và server lab hỗ trợ HTTP/3 | QUIC headers/Initial theo parser; không có HTTP plaintext |
| **L6 – TLS termination** | Reverse proxy lab terminate TLS rồi log request ID | Proxy thấy HTTP metadata theo chính sách; upstream passive không |
| **L7 – TLS trust failure** | Client test kết nối server cert không khớp hostname | Client-side verification failure; passive không thể tự kết luận user bỏ qua cert |
| **L8 – Capture loss** | Giảm/cố ý bỏ qua ClientHello trong lab capture | Parser thiếu SNI/cert, gắn nhãn incomplete thay vì suspicious |

### 16.7. Không đánh đồng tool output và nguồn dữ liệu

OpenSSL s_client là **active endpoint client**; tshark là **offline packet parser**; Zeek/Suricata có thể là **network sensors**; proxy/application logs là **sau TLS termination**. Những nguồn này có vantage khác nhau và câu trả lời của chúng **không mâu thuẫn** khi một nguồn thấy server certificate còn nguồn kia không.

## 17. Data contract cho TLS telemetry

### 17.1. Normalized schema minh họa

~~~json
{
  "event_id": "tls-telemetry-demo-006",
  "event_time": "2026-11-28T06:10:00Z",
  "sensor_id": "ndr-edge-a",
  "capture_point": "inside-nat-before-proxy",
  "transport_protocol": "TCP",
  "src_ip": "192.0.2.10",
  "src_port": 51342,
  "dest_ip": "203.0.113.20",
  "dest_port": 443,
  "observed_tls_version": "TLSv1.3",
  "handshake_observed": "client_hello_and_server_hello",
  "sni_observation_type": "cleartext_clienthello",
  "observed_sni": "api.partner.example",
  "alpn_offered": ["h2", "http/1.1"],
  "alpn_selected_observed": false,
  "certificate_observed_from_passive_tls": false,
  "ech_state": "unknown",
  "content_decrypted": false,
  "orig_bytes": 24500,
  "resp_bytes": 63100,
  "capture_loss_known": false,
  "nat_translation_ref": "nat-demo-078",
  "endpoint_process_ref": "edr-demo-018",
  "confidence": "handshake_metadata_observed",
  "privacy_class": "restricted-network-metadata"
}
~~~

Đây là **event do pipeline tự định nghĩa**, không phải các fields mà Zeek/Suricata có thể bảo đảm đưa ra nguyên vẹn. Đặc biệt:

- **ech_state=unknown** không có nghĩa ECH đã thất bại hoặc không được dùng.
- **certificate_observed_from_passive_tls=false** khác **server không có certificate**.
- **alpn_selected_observed=false** khác **ALPN không được negotiated**.
- **content_decrypted=false** nghĩa event này không có plaintext payload, không phủ nhận app logs ở nơi khác.
- **capture_loss_known=false** không chứng minh zero packet loss; chỉ có nghĩa chưa có evidence mất gói tại lúc ghi record.

### 17.2. Hệ thống phân loại nguồn gốc trường

Nên gắn provenance cho mỗi thông tin:

~~~text
ip_tuple                  -> directly observed packet headers
sni                       -> client_hello field when visible
dns_attributed_name       -> inferred from managed DNS correlation
process_name              -> endpoint telemetry
app_operation             -> application audit or authorized proxy
tls_verified_by_client    -> endpoint/application TLS validation result
business_data_transferred -> application/DLP evidence, not flow bytes alone
~~~

Nếu telemetry chỉ có DNS inference, không ghi nó thành **observed_sni**. Nếu certificate được lấy từ **active scanning** hoặc inventory, không đánh dấu là **passive TLS 1.3 certificate**.

### 17.3. Identity correlation và NAT

Một public egress IP có thể đại diện hàng nghìn endpoints. Muốn map flow về đúng device/process:

1. Thu **client private source, NAT translation, precise timestamps**.
2. Đồng bộ đồng hồ giữa sensor, NAT, DNS, EDR và proxy.
3. Tương quan **connection/session IDs**, không chỉ hostname hoặc IP.
4. Xử lý **IP reuse, port reuse, QUIC migration và proxy connection pooling**.
5. Gắn **confidence và unknown** nếu không tìm được mapping đáng tin.

**Không quy hành vi cho cá nhân chỉ từ shared NAT IP** nếu thiếu chứng cứ bổ sung.

### 17.4. Data minimization và retention ngay tại schema

Không đưa **raw cookies, access tokens, mật khẩu, client private keys, payload hoặc hồ sơ cá nhân** vào event chỉ để phục vụ dashboard. Tùy use case, có thể:

- Rút gọn/sanitize hostname nhạy cảm.
- Hash/pseudonymize device/user identifiers theo chính sách.
- Giữ **raw IP mappings** với RBAC và TTL ngắn hơn aggregated metrics.
- Chặn xuất logs/PCAP sang môi trường không được ủy quyền.
- Theo dõi **schema changes** để analysts không vô tình hiểu sai một field mới.

## 18. Detection engineering trên traffic mã hóa

### 18.1. Thiết kế một detection như một giả thuyết kiểm chứng được

Một detection nên ghi:

~~~text
Threat hypothesis:
  A compromised endpoint may initiate unusual outbound TLS
  to an external service not approved for that application role.

Direct observations:
  destination IP, port, timing, bytes, TLS handshake metadata,
  network zone, capture quality.

Enrichment:
  endpoint process identity, managed DNS, asset criticality,
  approved software inventory, previous baseline.

Conclusion:
  suspicious outbound connection requiring triage,
  NOT confirmed data exfiltration without further evidence.
~~~

### 18.2. Các tín hiệu kết hợp

| Tín hiệu | Ý nghĩa có thể | False positives thường gặp |
| --- | --- | --- |
| **New destination country/ASN/IP** | Resource liên lạc với nơi chưa biết | CDN move, SaaS provider migration |
| **Rare TLS fingerprint** | Client/library/automation mới | Browser/SDK update, enterprise proxy |
| **Periodic small outbound flows** | Beacon-like communication | Health checks, telemetry, polling |
| **Large outbound bytes** | Batch upload hoặc exfiltration hypothesis | Backup, approved sync, video, package publishing |
| **SNI absent/outer-only** | Hạn chế visibility | ECH, no-SNI client, capture loss, session shape |
| **Unusual TLS versions/ciphers** | Legacy/misconfigured client | Approved embedded systems, proxies |
| **Repeated failed handshakes** | Scan, credential/TLS config issue | Certificate rotation/expiry, network outage |
| **Traffic outside approved proxy** | Potential policy bypass | Missing route inventory, emergency exception |
| **New QUIC flows** | Protocol usage shift | Browser HTTP/3 rollout, CDN feature |

**Một tín hiệu đơn lẻ hiếm khi đủ để khẳng định compromise.**

### 18.3. Tách detection classes

Có thể phân loại:

1. **Policy violation:** external connection ngoài approved egress path; có control objective rõ và negative test.
2. **Operational anomaly:** TLS handshake failures, certificate chain issues tại proxy, DNS problems, QUIC fallback spikes.
3. **Threat hypothesis:** suspicious destination, rare fingerprint, timing/volume pattern chưa được ứng dụng giải thích.
4. **Confirmed malicious activity:** cần endpoint/app/incident evidence khẳng định hành động trái phép, không chỉ metadata.

Dashboard phải hiển thị **confidence, event provenance và trạng thái triage** theo từng class.

### 18.4. Baseline theo cohort

Để tránh cảnh báo mỗi lần browser update, xây baseline theo:

- Device OS/browser/approved app/SDK family.
- Asset risk tier và network zone.
- Human interactive vs server-to-server automation.
- Hour/day/seasonality.
- Transport protocol TCP/TLS vs QUIC.
- Cloud CDN/SaaS destinations và approved egress patterns.

“Unusual” phải được so với một **cohort hợp lý**. Một máy backup truyền 200 GB mỗi đêm không nên được so với laptop nhân viên văn phòng rồi mặc định coi là exfiltration.

### 18.5. Alert tuning không được che sensor gaps

Nếu ECH khiến SNI coverage giảm, rule dựa trên exact SNI có thể tạo ít alerts hơn. Không diễn giải là **giảm malicious destinations**; phải hiển thị **visibility loss** và chuyển sang controls khác có hiệu lực.

Một mục tiêu detection tốt gồm **positive simulated cases, negative benign cases và coverage metrics**, không chỉ số alerts thấp.

## 19. Đánh giá false positives, false negatives và concept drift

### 19.1. Không thể tính recall chỉ từ alerts

Với một bộ test có nhãn chuẩn:

\[
\text{Precision} = \frac{TP}{TP+FP}
\]

\[
\text{Recall} = \frac{TP}{TP+FN}
\]

Trong đó **TP** là alert đúng, **FP** là alert nhầm và **FN** là hành vi đáng báo nhưng không được phát hiện.

Một sản phẩm chỉ ghi các alerts đã bắn **không tự biết FN trong production**. Cần **scenario simulations có quyền, ground-truth endpoint/app evidence hoặc incident hindsight** để đánh giá.

### 19.2. Ví dụ với bộ lab có nhãn

Một controlled exercise chứa:

- **30** suspicious outbound scenarios thực sự cần alert theo policy.
- Hệ thống phát hiện **24**; bỏ sót **6**.
- Đồng thời có **8 alerts** trên traffic benign.

Kết quả trong bộ test:

- Precision = **24 / (24 + 8) = 75%**.
- Recall = **24 / (24 + 6) = 80%**.

Đây chỉ là **test-set results**, không phải tuyên bố production efficacy khi traffic/attacker behavior khác nhau.

### 19.3. False positives đặc biệt phổ biến với metadata

| Detection | Tình huống benign tương tự | Cách giảm nhầm |
| --- | --- | --- |
| **Beaconing theo chu kỳ** | Agent monitoring, EDR check-in, scheduled API polling | Correlate process owner, approved destinations |
| **Rare JA3/JA4-style fingerprint** | SDK version mới, IoT embedded TLS | Cohort baseline, change inventory |
| **High outbound byte ratio** | Cloud backup, log shipping, artifact upload | Business schedules, expected endpoints |
| **Unknown SNI/ECH** | Privacy feature trong browser | Parser visibility status, ECH rollout context |
| **TLS handshake failures tăng** | Certificate expiry, proxy health issue | Error type, change timeline, affected clients |
| **UDP 443 volume tăng** | HTTP/3 adoption | QUIC parser và transport baseline |
| **New external IP/ASN** | SaaS/CDN load balancing, disaster recovery | Asset/partner DNS and approval records |

### 19.4. Concept drift: model/rule bị lỗi thời

Môi trường thay đổi theo:

- TLS libraries/browser/OS updates.
- ECH adoption hoặc thay đổi ClientHello layout.
- HTTP/3 rollout và QUIC versions.
- CDN/DNS migrations.
- Service mesh/gateway/inspection policy changes.
- New fleet/IoT/SDK cohorts.

Nếu telemetry definition thay đổi (ví dụ parser bắt đầu gắn **outer_sni** thay vì **sni**), việc so sánh alerts qua hai kỳ có thể vô nghĩa. **Lưu parser version, schema version và detection rule version** cùng metric trend.

### 19.5. Đừng dùng detection accuracy để thay kiểm soát phòng ngừa

Một rule có precision/recall tốt không thay **egress firewall, workload authorization, endpoint hardening và data-protection controls**. Các detection trên encrypted traffic có thể gợi ý investigation, còn yêu cầu “chặn direct Internet” nên kiểm tra ở **đường mạng thực**, không dựa vào dự đoán từ TLS fingerprint.

## 20. Threat model: những điều telemetry TLS có thể bỏ sót

| Mối đe dọa/kịch bản | Metadata có thể gợi ý | Điều metadata không thể khẳng định | Control bổ trợ |
| --- | --- | --- | --- |
| **Data exfiltration qua HTTPS** | Egress bytes lớn, đích hiếm, time anomaly | File và nội dung bị gửi | DLP/app audit, EDR/process, least-privilege egress |
| **Command and control qua TLS** | Periodic flows, fingerprint lạ, destination profile | Nội dung lệnh hoặc malware family | Endpoint detections, threat intel có kiểm chứng |
| **Tạo TLS tới domain giả mạo** | Observed SNI, cert metadata ở TLS 1.2, DNS | Client đã verify cert đúng hay dữ liệu gì đã trao đổi | Endpoint TLS validation, DNS/proxy policy |
| **ECH làm giảm hostname visibility** | Outer ClientHello/ECH-related fields nếu parser hỗ trợ | Hostname thật trong ClientHelloInner | Managed resolver, proxy/app logs có quyền |
| **DoH/DoT che DNS queries** | Kết nối tới resolver được biết, timing | Những qname cụ thể | Managed DNS egress policy và resolver logs |
| **QUIC migration/fallback** | UDP packets, CIDs, changed five-tuple | Một flow UDP là một HTTP request | QUIC-aware telemetry + app audit |
| **Phishing site dùng CDN chung** | CDN IP/outer TLS metadata | Trang/URL người dùng đã mở | Browser/endpoint/web-proxy telemetry |
| **TLS downgrade/misconfiguration** | Offered/selected params nếu quan sát đủ | Security posture toàn server chỉ từ một client | Approved active TLS validation, server config |
| **Certificate-based mTLS misuse** | Handshake metadata không đủ với TLS 1.3 | Client cert identity/authorization trong mỗi request | Gateway/app mTLS auth logs |
| **Insider access ngoài proxy** | Network flows ngoài approved route | Nội dung operation | Firewall route tests + app/EDR logs |
| **Malicious traffic trong approved SaaS** | Traffic tới SaaS hợp lệ | User có quyền upload nội dung bất kỳ | SaaS audit, tenant/API policies, DLP |
| **Proxy TLS inspection bypass** | Direct flows, transport switch | Mọi bypass đã được tìm thấy | Egress controls, test paths và telemetry coverage |

### 20.1. Threat model phải định nghĩa đối thủ và điểm quan sát

Một insider có thể:

- Thực hiện request tới dịch vụ được phê duyệt bằng user account hợp lệ.
- Dùng ứng dụng/cloud sync hợp lệ nhưng thao tác dữ liệu trái quyền.
- Có quyền cài proxy/agent riêng hoặc sử dụng client libraries khác.

Metadata network có thể phát hiện **điều bất thường** nhưng **không tự phân loại authorized vs unauthorized business operation**. Cần role-based app logging và data authorization evidence.

### 20.2. Không đẩy trách nhiệm kiểm soát nội dung sang NDR duy nhất

Nếu chính sách cần biết một user đã **xuất báo cáo payroll nào**, **gửi object nào lên storage** hoặc **gọi API method nhạy cảm nào**, nên đặt audit tại **ứng dụng/SaaS/API gateway**, nơi có danh tính nghiệp vụ và request context. NDR passive giúp giám sát **network-path integrity và traffic anomalies**, không thay audit logic nghiệp vụ.

## 21. Case study 1: SNI visibility giảm sau khi một nhóm client bật ECH

### 21.1. Tình huống

Một SOC dashboard theo dõi tỷ lệ kết nối TLS có SNI. Sau cập nhật browser và DNS configuration, tỷ lệ có hostname cụ thể giảm từ **91% xuống 66%** trong một nhóm clients, nhưng tổng encrypted connections không giảm tương ứng. Đội vận hành lo có chiến dịch “ẩn lưu lượng”.

### 21.2. Evidence giả định

| Evidence | Quan sát | Kết luận hợp lệ |
| --- | --- | --- |
| **Client/browser rollout** | Một số browser cohorts vừa thay version | Có thay đổi phần mềm cùng thời điểm |
| **Passive TLS logs** | Nhiều flows chỉ có outer handshake info hoặc SNI không dùng được | Độ quan sát hostname đã giảm |
| **DNS managed logs** | Vẫn thấy domain resolutions cho tập clients được quản lý | Có thêm nguồn domain context, không chứng minh URL |
| **Firewall flow logs** | Total IP/port traffic tương đối ổn định | Không có bằng chứng volume tương ứng tăng bất thường |
| **Endpoint telemetry** | Browser processes trùng cohorts | Có ngữ cảnh benign đáng xem |
| **ECH support/capture review** | Parser nhận diện theo khả năng hiện tại | Cần xác minh feature/handshake shape, không chỉ null SNI |

### 21.3. Cách xử lý

1. Kiểm tra **sensor packet loss, parser version và ClientHello capture rate** trước khi quy mọi SNI null cho ECH.
2. Phân loại **cleartext SNI / ECH outer only / no SNI sent / missing handshake / unknown**.
3. So sánh theo **browser/OS cohorts** và thời điểm rollout, không gộp tất cả clients.
4. Correlate **managed DNS/proxy/endpoint logs** trong phạm vi chính sách.
5. Đánh giá những rule phụ thuộc exact SNI có **false-negative risk** tăng đến đâu.
6. Chuyển một phần kiểm soát sang **proxy access policies, endpoint/app audit hoặc network allowlist**, thay vì cố đọc hostname không còn hiển thị.
7. Cập nhật dashboard để không gọi **unknown SNI** là **confirmed malicious encrypted traffic**.

**Bài học:** giảm **TLS hostname visibility** không đồng nghĩa tăng hành vi độc hại; phải đo **visibility change và detection coverage** riêng.

## 22. Case study 2: fingerprint đổi đồng loạt sau cập nhật TLS library

### 22.1. Tình huống

Rule giám sát gắn “rare TLS fingerprint” với risk cao. Sau một đợt cập nhật client SDK, nhiều microservices có fingerprint mới và SOC nhận hàng trăm alerts.

### 22.2. Các bước kiểm tra

~~~text
Before:
  Fleet version A -> ClientHello fingerprint family F1

After:
  Fleet version B -> ClientHello fingerprint family F2

Same business services:
  destinations, approved service identities và business operations
  largely unchanged according to independent evidence.
~~~

- Xác minh **release/change records**, image hashes, software inventory và service owners.
- Nhóm alerts theo **cohort**, không xem mỗi kết nối là một attacker khác.
- Kiểm tra **destination reputation, new egress paths, volume và endpoint process**.
- Xác định parser và fingerprint algorithm version có đổi không.
- Chạy **benign positive samples** với SDK mới và **malicious-like negative simulations** trong lab.
- Điều chỉnh rule để giữ giá trị phát hiện **unexplained process + unusual destination + flow anomaly**.

### 22.3. Rủi ro của điều chỉnh quá mức

Không whitelist mọi connection có fingerprint F2 trên mọi host; fingerprint đó có thể được **giả lập**. Whitelist chỉ trong scope **approved app/identity/process/route**, có owner và TTL.

**Bài học:** fingerprint là **đặc điểm handshake**, không phải proof of software identity hay maliciousness.

## 23. Case study 3: nhìn thấy 8 GB TLS outbound nhưng không biết file gì

### 23.1. Tình huống

Một máy chủ gửi khoảng **8 GB encrypted outbound** tới IP thuộc một cloud storage provider trong một giờ ngoài khung giờ thường gặp. SOC mở incident nghi vấn data exfiltration.

### 23.2. Những gì biết và chưa biết

**Có thể quan sát được:**

- IP nguồn/đích, transport, thời gian, bytes/packet counters ở vị trí capture.
- DNS/SNI metadata nếu có và đáng tin.
- Kết nối có đi qua approved egress firewall/proxy không.
- So sánh với baseline của máy chủ và business schedule.

**Chưa thể kết luận chỉ từ passive TLS metadata:**

- Có bao nhiêu file được upload, tên file là gì.
- Có chứa dữ liệu cá nhân/bí mật hay không.
- Business owner đã phê duyệt giao dịch chưa.
- Server trả HTTP status nào, object storage account/tenant nào nhận dữ liệu.

### 23.3. Quy trình điều tra

1. Xác định **application/service owner, workload process và change calendar**.
2. Correlate **EDR process + command lineage** với network flow timestamp.
3. Xem **cloud object storage/SaaS audit logs** nếu endpoint thuộc quyền tổ chức hoặc partner có phối hợp chính thức.
4. Kiểm tra **proxy/app upload logs** có business transaction/user identity nhưng không thu raw contents ngoài nhu cầu.
5. Đánh giá **data classification và access entitlement** tại nguồn dữ liệu.
6. Nếu có dấu hiệu trái quyền, áp **containment/revoke** theo IR và giữ log evidence.
7. Ghi kết luận ở mức chính xác: **large encrypted transfer observed**, **likely approved backup**, hoặc **confirmed unauthorized file transfer** tùy bằng chứng.

**Bài học:** bytes outbound là **tín hiệu điều tra**, không phải bằng chứng file khách hàng đã bị đánh cắp.

## 24. Case study 4: chuyển lên TLS 1.3 làm dashboard chứng thư “biến mất”

### 24.1. Bối cảnh

Một dashboard cũ trích issuer, SAN và ngày hết hạn từ **TLS 1.2 Certificate messages** trong PCAP. Sau khi hệ thống chuyển sang TLS 1.3, nhiều dòng certificate fields thành null; nhóm vận hành cho rằng server đang dùng certificate không hợp lệ.

### 24.2. Giải thích

Trong TLS 1.3, **Certificate message được mã hóa trong full handshake**. Passive sensor thường không còn thấy certificate details để điền trường như trong TLS 1.2.

**NULL certificate field ≠ server không gửi certificate**.

Ngoài ra, TLS resumption/PSK hoặc capture thiếu full handshake cũng làm certificate metadata không có ngay cả trong một số trường hợp trước đó.

### 24.3. Sửa hệ đo

| Mục tiêu | Nguồn thích hợp |
| --- | --- |
| **Server cert inventory** | Server config/PKI platform, reverse proxy/LB config, approved active TLS checks |
| **TLS handshake behavior** | Passive sensor, client/server TLS logs |
| **Client certificate validation success** | Client/SDK/app or gateway trust-validation logs |
| **Certificate expiry alerts** | Certificate management + endpoint checks |
| **Certificate used by specific session** | Authenticated endpoint/proxy/session audit, với limitations |

Ghi **field provenance**: certificate lấy từ approved active check, không từ passive TLS 1.3.

**Bài học:** TLS 1.3 thay phạm vi dữ liệu có thể quan sát; không suy sự cố PKI từ sự biến mất của một trường telemetry.

## 25. Case study 5: QUIC/HTTP3 rollout bị báo là tăng traffic đáng ngờ

### 25.1. Tình huống

Một nhóm SaaS chuyển CDN sang HTTP/3. Trước đó flow analytics dựa chủ yếu trên **TLS over TCP 443**. Sau rollout, hệ thống thấy tăng đáng kể **UDP 443**, tăng “unknown protocol” và giảm tỷ lệ TLS SNI logged ở TCP.

### 25.2. Giả thuyết cần kiểm tra

- Clients có thực sự negotiated **QUIC/HTTP3** không?
- QUIC Initial packets có được decoder hỗ trợ và capture đủ không?
- QUIC connections có **migration/rebinding** làm đếm flows thay đổi không?
- Clients có fallback sang TLS/TCP gây **duplicate attempts** không?
- DNS/CDN destination set có thay đổi hợp lệ không?
- Có **policy bypass** thực hay chỉ telemetry parser chưa được cấu hình cho UDP?

### 25.3. Biện pháp

1. Cập nhật **monitoring inventory** bao phủ UDP 443 và QUIC theo parser capability.
2. Gắn **transport type + QUIC version + initial visibility state** cho telemetry.
3. So sánh traffic theo **logical app/service activity** khi có application evidence, không chỉ số five-tuples.
4. Đánh giá **firewall/egress rules** cho TCP/UDP riêng, tránh giả định chính sách 443/TCP cũng áp cho 443/UDP.
5. Thử **QUIC success và TCP fallback** với test endpoints thuộc quyền sở hữu.
6. Cập nhật detection baselines và SOC runbook tránh alert storm vô nghĩa.

**Bài học:** giao thức thay đổi có thể làm **thay đổi hình dạng dữ liệu đo** mà không tự phản ánh thay đổi hành vi độc hại.

## 26. Case study 6: TLS inspection tạo lỗi mTLS và certificate pinning

### 26.1. Tình huống

Đội Network Security bật proxy TLS inspection cho tất cả outbound HTTPS để tăng visibility. Một ứng dụng tài chính dùng **client certificate mTLS** tới partner, và một số mobile clients có **certificate pinning**. Sau thay đổi, các calls thất bại, trong khi dashboard proxy ghi nhiều “TLS errors”.

### 26.2. Nguyên nhân khả dĩ

- TLS inspection proxy trình bày certificate riêng, khiến client không chấp nhận trust/pinning.
- Client certificate authentication không được chuyển đúng theo mô hình TLS termination/re-origination.
- ALPN/HTTP2/gRPC/streaming behavior không tương thích.
- Partner yêu cầu end-to-end client identity mà proxy không được phép đại diện.
- Gateway/proxy route hoặc SNI policy không hỗ trợ trường hợp cụ thể.

### 26.3. Phương án phù hợp

1. Xác định **phân loại dữ liệu, mục tiêu inspection và trách nhiệm PKI** trước khi sửa.
2. Kiểm tra **client/app TLS error**, trust store, pinning và mTLS requirements.
3. Tách **traffic cần end-to-end TLS** khỏi vùng inspection có thể áp, theo exception được phê duyệt.
4. Dùng **app/API audit, EDR, network metadata và partner logs** cho traffic không được terminate.
5. Đo lại **authorized success rate, TLS error rate và security visibility coverage**; đừng chỉ đếm số HTTPS có body được giải mã.
6. Không hướng dẫn client bỏ certificate verification chỉ để vượt proxy.

**Bài học:** tăng khả năng xem plaintext có thể làm giảm **tính toàn vẹn danh tính và availability** nếu đặt sai điểm trust boundary.

## 27. KPI/SLI cho encrypted traffic visibility

Đo lường chất lượng telemetry phải trả lời hai câu hỏi khác nhau:

1. **Mạng đã thực sự được quan sát bao nhiêu?**
2. **Trong phần đã quan sát, parser và pipeline hiểu được bao nhiêu với mức tin cậy nào?**

### 27.1. Những metric quan trọng

| Metric | Định nghĩa | Điều cần tránh |
| --- | --- | --- |
| **Network path coverage** | % in-scope egress/ingress paths có sensor/flow source đúng vantage | Chỉ đếm số sensor đang online |
| **Bidirectional capture coverage** | % test flows có cả hai hướng để correlate handshake | Dùng một chiều traffic và giả định đủ |
| **ClientHello observation rate** | Connections đủ điều kiện có ClientHello captured / eligible full-handshake connections | Lấy mọi midstream flows vào denominator |
| **TLS/QUIC parse success** | % supported test handshakes được parser nhận dạng đúng | Kết luận unknown protocol là malicious |
| **Observed hostname availability** | % eligible handshakes có hostname được quan sát theo category | Gộp ECH outer hostname với real hostname |
| **Observed certificate availability** | % cases mà expected passive certificate visible | Phạt TLS 1.3 vì certificate được mã hóa |
| **Endpoint/process correlation** | % flows map đáng tin tới asset/process | Gán NAT IP cho một user cụ thể |
| **Capture loss/drop rate** | Packets missed/overrun theo counters có thể đo | Giả sử drop=0 khi thiết bị không expose counters |
| **Telemetry freshness** | Event-to-SIEM ingest delay, p95/p99 | Dùng ingest time làm event time |
| **Schema/parser consistency** | % events có version/provenance/quality fields đúng | So trends khi parser đổi nghĩa trường |
| **Detection scenario coverage** | % threat/test scenarios được thực hiện và có evidence | Dùng alert count làm recall |
| **Alert review quality** | Precision/test recall, triage latency, open findings | Ưu tiên giảm alert bất kể visibility |

### 27.2. Một tỷ lệ phải có denominator đúng

Ví dụ:

\[
\text{ClientHello capture rate}
=
\frac{\text{eligible connections có ClientHello được quan sát}}
{\text{eligible new TLS connections qua sensor}} \times 100\%
\]

Định nghĩa **eligible** cần loại trừ hoặc phân lớp:

- Connections bắt đầu trước khi sensor capture.
- Lưu lượng không thuộc path mà sensor có nhiệm vụ thấy.
- QUIC/TCP chưa có parser hỗ trợ hoặc được đo ở population khác.
- Handshake chỉ có midstream/retransmitted partial packets.

Không bỏ các trường hợp bị packet loss khỏi quality report; chúng nên được phản ánh trong **capture quality** chứ không âm thầm xóa để tỷ lệ đẹp.

### 27.3. Không lập KPI “% HTTPS được xem nội dung” mà thiếu phạm vi

Một doanh nghiệp có thể cố tăng tỷ lệ TLS-decrypted connections bằng cách terminate thêm mọi traffic. Nhưng đó **không phải mục tiêu bảo mật phổ quát**: một số kết nối yêu cầu **end-to-end mTLS, pinning hoặc confidentiality**, và việc thu plaintext còn tạo rủi ro.

Một KPI tốt hơn cho từng resource class:

- **Monitoring objective đạt hay không?**
- Đã có **network path metadata** đủ phát hiện bypass chưa?
- Có **application audit** cho các operations nhạy cảm chưa?
- Có **TLS identity verification evidence** ở endpoint phù hợp chưa?
- Có chấp nhận risk/visibility exception được phê duyệt không?

### 27.4. Dashboard ví dụ

Các số sau **hoàn toàn minh họa**, không phải một hệ thống thật:

| Chỉ số | Giá trị giả định | Quyết định |
| --- | ---: | --- |
| In-scope egress paths instrumented | 18/20 = **90%** | Bổ sung 2 paths chưa có sensor |
| TLS/TCP eligible full-handshake ClientHello capture | **96%** | Kiểm tra capture loss/route |
| QUIC/UDP 443 paths có parser supported | **72%** | Ưu tiên nâng capability/sensor placement |
| Known outer-only/ECH-affected hostname observations | **18%** | Cập nhật assumptions SNI-based detections |
| Flow events correlate được tới endpoint/process | **81%** | Sửa NAT/EDR mapping và clock alignment |
| Packet drops tại peak | **2,1%** | Sizing/mirroring/filtering review |
| p95 log pipeline delay | **75 giây** | Điều tra collector/queue |
| TLS certificate visibility trong TLS 1.3 passive flow | **Không áp dụng** | Dùng PKI/server-side source; không tính failure |
| Confirmed critical direct egress bypass paths | **2** | Contain theo change/IR process |
| Detection scenario tests đúng theo ground truth | **23/27** | Review 4 missed scenarios |

Dashboard nên hiển thị **coverage, unknown, false positives, parser version và risk findings**, không chỉ số lượng kết nối TLS.

## 28. Quyền riêng tư và bảo vệ telemetry nhạy cảm

Ngay cả khi không có plaintext HTTP, metadata có thể tiết lộ **thói quen truy cập, hostname có tính riêng tư, quan hệ đối tác, vị trí mạng, thiết bị và thời điểm làm việc**. Trong một số môi trường, nó có thể là dữ liệu cá nhân hoặc dữ liệu được quản trị nghiêm ngặt.

### 28.1. Thu thập tối thiểu

- Chỉ thu **fields cần thiết** cho approved security objectives.
- Không bật **full packet capture rộng** khi flow metadata đủ cho use case.
- Nếu một điều tra yêu cầu PCAP chi tiết, đặt **thời gian, filter, owner, legal/privacy approval và TTL**.
- Hạn chế truy cập user/device mappings, tên hostname nhạy cảm và incident notes.
- Tách **aggregate dashboards** khỏi **raw event drill-down** theo role.
- Chọn chính sách giữ lại dữ liệu theo tính nhạy cảm, nhu cầu điều tra và quy định áp dụng.

### 28.2. Chuỗi bảo quản bằng chứng

Đối với một sự cố:

1. Ghi **sensor ID/capture point/collection time UTC**.
2. Ghi **filter/scope, packet drop counters, sampling và tool/parser version**.
3. Lưu file ở nơi có **access controls, encryption và integrity validation**.
4. Nếu chia sẻ sample, làm sạch **IP/host/user fields** theo quy trình nhưng giữ khả năng truy vết bản gốc.
5. Ghi **chain of custody** cho analyst access/exports khi cần.
6. Không đưa **session secrets/keylogs/credentials** vào tài liệu công khai hoặc ticket hỗ trợ không phù hợp.

### 28.3. Metadata không phải danh tính chính xác của con người

Một IP có thể là NAT/proxy/router; một SNI có thể được client tự khai; một JA3/JA4 có thể do hàng nghìn ứng dụng chia sẻ. Vì vậy không đưa ra **kết luận cá nhân đã truy cập nội dung cụ thể** từ một fingerprint hoặc domain alone.

Cần correlate với **authenticated application/proxy/endpoint evidence** theo nguyên tắc cần biết và luật/chính sách áp dụng.

### 28.4. Kiểm soát giải mã phải có mục tiêu cụ thể

Nếu doanh nghiệp cân nhắc TLS interception:

- Xác định rõ **resource class**, căn cứ xử lý và mục đích (DLP, malware screening, enterprise policy).
- Đánh giá **client cert/pinning, protocol compatibility, data residency và sensitive category exclusions**.
- Bảo vệ **proxy CA private keys**, root-store distribution và certificate rotation.
- Theo dõi false certificate errors, app failures, TLS downgrade incidents và latency overhead.
- Có **exception process** cho traffic đòi end-to-end trust, không mặc định “không giải mã = độc hại”.

## 29. Runbook điều tra encrypted traffic bất thường

### 29.1. Giai đoạn 1 — Xác nhận cảnh báo và mức dữ liệu có thể thấy

Thu:

- **Incident ID, UTC time window, sensor/capture point, parser version**.
- Network 5-tuple, NAT mappings, session/flow IDs, bytes, packet counts và hướng lưu lượng.
- TLS/QUIC type/version và handshake completeness.
- SNI field provenance: **observed clear / outer ECH / inferred DNS / unknown**.
- ALPN offered vs selected khi có nguồn đúng.
- Fingerprint algorithm/version và mức confidence.
- Sensor loss, asymmetric routing, DNS/proxy/endpoint telemetry availability.

**Không gắn nhãn “confirmed exfiltration” từ bytes+SNI alone.**

### 29.2. Giai đoạn 2 — Xác minh identity và business context

1. Ánh xạ source qua **NAT mappings và endpoint inventory** với độ tin cậy phù hợp.
2. Correlate **EDR process, binary signer/hash, service owner, approved deployment changes**.
3. Xem **managed DNS, proxy/WAF, cloud network và application audit logs** trong thời gian tương ứng.
4. Kiểm tra destination có thuộc **approved partner, CDN, SaaS, backup target** không.
5. Xác định ứng dụng có **expected scheduled transfer/polling/telemetry job** không.
6. Tìm những **bất thường độc lập**: privilege changes, process lineage, unexpected executable, app actions trái policy.

### 29.3. Giai đoạn 3 — Phân loại và containment

| Phân loại | Hành động |
| --- | --- |
| **Benign/expected change** | Cập nhật app inventory/cohort baseline, đóng với evidence |
| **Parser/visibility limitation** | Cập nhật dữ liệu quality và detection logic, không kết luận malicious |
| **Network policy bypass** | Chặn/tái lập route/firewall ở điểm có hiệu lực, kiểm thử positive/negative |
| **Credential or endpoint compromise suspected** | SOC phối hợp EDR/IAM, containment theo IR |
| **Confirmed unauthorized transfer** | Quản lý evidence, credentials, source/app/sink theo incident plan |
| **TLS trust failure** | Sửa CA/SAN/client configuration, không bỏ verification |
| **Monitoring blind spot nghiêm trọng** | Bổ sung vantage/log source hoặc tạm thời compensating control |

Containment phải có **business impact review**. Không tự chặn toàn bộ HTTPS/QUIC hoặc tắt TLS security chỉ vì thiếu một trường quan sát.

### 29.4. Giai đoạn 4 — Khôi phục và kiểm chứng

- Đường đi hợp lệ đã được phục hồi theo SLO.
- Direct trái quyền bị chặn tại **network/identity/policy enforcement** phù hợp.
- Detection có **new negative/positive regression tests**.
- Parser/log schema changes được version control và có owner.
- Incident kết luận theo mức **observed, inferred, confirmed**, không trộn.
- Dữ liệu nhạy cảm, PCAP và session secrets được xử lý/retained theo policy.
- Telemetry quality và sensor coverage phục hồi nếu trước đó mất.

### 29.5. Mẫu báo cáo

~~~text
Case ID / severity / time window UTC:
Sensor, capture point, parser/schema versions:
Network flow and NAT attribution:
TLS/QUIC/ECH observed fields and unavailable fields:
Packet loss / partial capture / asymmetry:
Endpoint process / app resource / owner:
DNS, proxy, firewall, application audit correlations:
Observed fact:
Hypotheses and confidence:
Evidence proving or refuting data transfer:
Containment, service impact and rollback:
Validation tests, residual risk and owner:
Privacy/access/retention controls applied:
~~~

## 30. Ma trận kiểm thử độ chính xác và vùng mù

Chỉ dùng **lab/staging hoặc production test windows có ủy quyền**; không thu packet/traffic của bên thứ ba ngoài scope. Mục tiêu là kiểm chứng **quan sát và kết luận**, không tạo tấn công vào external services.

| Test | Setup có kiểm soát | Expected outcome |
| --- | --- | --- |
| **P1 – TLS 1.2 full** | Lab endpoint, full handshake | ClientHello và cert fields có thể thấy theo TLS 1.2 |
| **P2 – TLS 1.3 full** | Lab endpoint, no ECH | ClientHello quan sát được, server Certificate mã hóa |
| **N1 – TLS 1.3 cert visibility** | Passive sensor-only | Không dựng certificate metadata từ packet không chứa plaintext cert |
| **P3 – Client TLS validation** | Test client + known CA/SAN | Client-side evidence chứng minh verify thành công |
| **N2 – Wrong CA/SAN** | Lab server có cert sai | Client reject; sensor không tự suy từ capture |
| **P4 – QUIC Initial parsing** | HTTP/3 lab, supported QUIC version | Initial handshake metadata có thể phân tích theo capability |
| **N3 – QUIC content visibility** | Passive QUIC capture | Không claim HTTP/3 body/path |
| **P5 – ECH protected hostname** | ECH-capable lab setup | Outer available; inner hostname không lộ |
| **N4 – Unknown SNI behavior** | No SNI/midstream/ECH test cases | Pipeline phân loại đúng lý do/unknown |
| **P6 – TLS resumption** | Client/server lab hỗ trợ session resume | Không báo “missing certificate means invalid” |
| **P7 – Fingerprint baseline** | Multiple benign browsers/SDK versions | Fingerprint similarity và drift được hiểu đúng |
| **N5 – Fingerprint false positive** | Approved SDK mới giống watchlist feature | Không kết luận malware nếu thiếu evidence |
| **P8 – Proxy termination** | Approved lab reverse proxy | Proxy có HTTP context; passive upstream không |
| **N6 – HTTPS body inference** | Lab requests khác URL/body nhưng traffic gần giống | Không tạo false claim về nội dung từ packet sizes |
| **P9 – Managed DNS correlation** | Resolver logs và flow same endpoint | Attribution có timestamp/provenance |
| **N7 – Shared CDN IP** | Hai hostname cùng destination IP | Pipeline không tự khẳng định domain từ IP alone |
| **N8 – NAT multi-user** | Hai test clients chung public IP | Không gán flow sai user |
| **N9 – Asymmetric path** | Lab sensor một chiều | Mark handshake completeness insufficient |
| **P10 – Capture loss** | Controlled drops | Packet-loss metrics và quality flags tăng |
| **P11 – Egress bypass** | Authorized direct route outside proxy | Firewall/flow telemetry phát hiện đúng path |
| **P12 – TCP vs QUIC fallback** | Controlled browser/server | Metrics không đếm double logical operation từ hai attempts |
| **P13 – Privacy** | Synthetic tokens/PII in lab requests | Sanitized logs không lưu secret raw |
| **F1 – Sensor outage** | Lab collector disabled | Alert mất coverage; unknown được hiển thị |

### 30.1. Kiểm tra hai loại chất lượng

**Control-effectiveness tests** kiểm tra policy thực sự chặn direct egress, TLS verification đúng hoặc application authorization hoạt động. **Telemetry-quality tests** kiểm tra sensor có thấy đầy đủ đúng trường hay không.

Một telemetry-quality test PASS **không chứng minh security control PASS**. Ngược lại, TLS 1.3 giấu certificate khỏi passive observer là **hành vi giao thức đúng**, không phải giám sát lỗi nếu dashboard đánh nhãn trường đó **not observable by design**.

### 30.2. Hạn chế kết luận từ một test

Nếu một kết nối lab có SNI được trích đúng, không thể suy “100% TLS SNI coverage” cho production. Có thể còn **ECH, QUIC version khác, no-SNI clients, resumption, packet loss hoặc alternate routes**. Báo rõ **population, parser version, số trường hợp và unknowns**.

### 30.3. Checklist evidence cho một test

~~~text
Test ID / authorized owner:
Client, server and network zone:
Protocol, TLS/QUIC version, ECH state if known:
Capture point, sensor/parser version:
Expected visible metadata:
Expected encrypted/unobservable content:
Observed fields + provenance:
Handshake and packet-capture completeness:
Endpoint/app/PKI evidence when used:
Data privacy treatment:
Pass/fail, limits, timestamp UTC:
Remediation/rollback and owner:
~~~

## 31. Những nhầm lẫn thường gặp

1. **“HTTPS dùng TLS nên cảm biến mạng hoàn toàn không thấy gì.”** IP/port/timing, packet lengths và một số handshake metadata có thể còn nhìn thấy.
2. **“Có SNI đồng nghĩa biết URL người dùng mở.”** SNI không chứa HTTP path/query/body.
3. **“SNI là hostname chắc chắn server đã xác thực.”** Đây là hostname client đề nghị, không phải proof of certificate validation.
4. **“SNI trống nghĩa client cố tình ẩn hành vi.”** Có thể do ECH, no-SNI, missing ClientHello, resumption hoặc capture lỗi.
5. **“ECH che luôn địa chỉ IP và packet sizes.”** ECH bảo vệ ClientHelloInner, không tự mã hóa IP headers.
6. **“Outer SNI trong ECH là hostname ứng dụng thực.”** Nó có thể chỉ là public-facing name, không phải inner hostname.
7. **“DoH làm không ai còn biết DNS query.”** Resolver được phép nhận truy vấn vẫn có thể có server-side logs.
8. **“DNS query chứng minh client đã mở website.”** Cache/prefetch và shared CDN làm attribution có điều kiện.
9. **“TLS 1.3 gửi certificate plaintext như TLS 1.2.”** Certificate message của TLS 1.3 được mã hóa.
10. **“Không thấy certificate trong capture nghĩa server không có certificate.”** Có thể do TLS 1.3, resumption hoặc packet loss.
11. **“Server cert trong TLS 1.2 capture chứng minh client đã verify.”** Client verification là hành vi ở endpoint.
12. **“Có server private key là giải mã được mọi TLS 1.3 PCAP.”** TLS 1.3 forward secrecy làm giả định này sai.
13. **“TLS 1.2 full handshake và resumed handshake cho cùng metadata.”** Resumption có thể bỏ certificate exchange.
14. **“TLS legacy_version=1.2 chứng minh negotiated version là 1.2.”** TLS 1.3 dùng supported_versions; parser cần đúng.
15. **“Có ALPN h2 trong ClientHello nghĩa HTTP/2 chắc chắn được chọn.”** Offered list khác selected ALPN.
16. **“Chọn ALPN ở TLS 1.3 luôn nhìn thấy từ passive capture.”** Server-selected ALPN được bảo vệ trong EncryptedExtensions.
17. **“UDP 443 nào cũng là QUIC.”** Có thể là giao thức khác; cần parser/protocol evidence.
18. **“QUIC Initial được giải mã nghĩa HTTP/3 body cũng đọc được.”** Initial khác protected application data.
19. **“Một QUIC five-tuple là một user session cố định.”** Migration/rebinding/CID có thể làm tuple đổi.
20. **“Số TCP connections tương đương số HTTP requests.”** Keepalive, HTTP/2/3 multiplex và resumption làm sai phép đếm.
21. **“JA3/JA4 xác định duy nhất malware.”** Fingerprint dùng chung, thay đổi và có thể được mô phỏng.
22. **“JA3 lạ chắc chắn đáng chặn.”** Browser/SDK updates có thể tạo fingerprint mới.
23. **“JA4-style cải tiến có thể khôi phục ECH inner hostname.”** Không thể suy như vậy; đây vẫn là fingerprint.
24. **“Large encrypted outbound bytes chứng minh dữ liệu nhạy cảm bị lấy.”** Chỉ là tín hiệu volume, cần app/EDR/DLP evidence.
25. **“Periodic encrypted flows luôn là C2.”** Monitoring agents và application polling cũng định kỳ.
26. **“Không có log ở IDS nghĩa không có kết nối.”** Route khác, packet drops, sampling, parser blind spots có thể là nguyên nhân.
27. **“NetFlow/IPFIX tương đương full PCAP.”** Flow aggregation thường không có payload/handshake fields chi tiết.
28. **“Proxy terminate TLS là passive observer có nội dung.”** Proxy có content context, cảm biến trước proxy vẫn không.
29. **“Mọi kết nối qua forward proxy đều an toàn.”** Proxy auth/TLS policy và direct bypass cần kiểm tra riêng.
30. **“TLS inspection luôn tăng bảo mật mà không ảnh hưởng ứng dụng.”** Có thể phá mTLS/pinning/gRPC/QUIC và privacy.
31. **“Cứ tắt certificate verification để debug.”** Tắt xác minh peer làm suy yếu bảo mật.
32. **“Có một PCAP sau giải mã là network observer luôn thấy plaintext.”** Lab keylog/termination là quyền quan sát đặc biệt.
33. **“IP destination đủ biết domain người dùng truy cập.”** CDN/shared hosting và proxies làm suy luận không chắc chắn.
34. **“Một NAT public IP chỉ là một user.”** Nhiều clients có thể chia sẻ egress IP.
35. **“Chỉ dùng timestamp là đủ correlate endpoint/process.”** Cần NAT mapping, identities, session IDs và quality flags.
36. **“Một sensor online nghĩa toàn bộ mạng được giám sát.”** Phải kiểm tra path coverage, asymmetric routing và captures.
37. **“Bỏ unknown flows khỏi denominator giúp đo đúng.”** Che visibility gaps và làm đẹp tỷ lệ.
38. **“SNI-based alert giảm chứng minh tấn công giảm.”** ECH và parser changes có thể làm giảm visibility.
39. **“Metadata không phải dữ liệu nhạy cảm.”** Hostnames/timestamps/IPs có thể tiết lộ hành vi và người dùng.
40. **“Log càng nhiều nội dung càng tốt.”** Raw tokens, cookies và payload làm tăng rủi ro dữ liệu.
41. **“Mọi TLS failures là indicator of compromise.”** Certificate expiry, configuration errors và outage cũng tạo lỗi.
42. **“Không cần log parser version.”** Version drift làm chỉ số trước/sau mất tính so sánh.
43. **“Không có source process vẫn có thể kết luận actor cá nhân qua IP.”** NAT/shared hosts và endpoint mappings cần kiểm chứng.
44. **“Có detector accuracy cao là không cần firewall.”** Detection và preventive enforcement khác nhau.

## 32. Bài tập vận dụng và gợi ý đáp án

### Bài 1 — SNI có đủ suy URL?

Một passive NDR log ghi source **192.0.2.10**, destination **203.0.113.20:443**, TLS 1.3, SNI **api.partner.example**, bytes outbound **4 MB**. Analyst viết “User đã POST dữ liệu khách hàng tới /upload”.

**Gợi ý:** kết luận quá mức. Chỉ biết flow và SNI/volume tại capture; HTTP method/path/data type không đọc được. Cần application/proxy/EDR/DLP logs có thẩm quyền và correlation đáng tin.

### Bài 2 — TLS 1.2 và TLS 1.3 certificate

Hai servers lab sử dụng certificate hợp lệ. Trong TLS 1.2 full handshake, Wireshark thấy server Certificate, còn trong TLS 1.3 capture nó không hiển thị.

**Gợi ý:** hành vi phù hợp vì TLS 1.3 mã hóa Certificate message. Không kết luận TLS 1.3 server thiếu certificate; dùng client-side validation/server PKI inventory.

### Bài 3 — Outer SNI với ECH

Một client dùng ECH. Sensor đọc outer SNI là một tên public frontend. Có thể xác nhận client đang truy cập hostname đó như application destination cuối cùng không?

**Gợi ý:** không. ECH bảo vệ ClientHelloInner chứa inner SNI; outer name không nhất thiết là hostname ứng dụng thật. Có thể dùng authorized DNS/endpoint telemetry, ghi provenance.

### Bài 4 — Fingerprint lạ

Sau khi rollout TLS SDK mới, 70% microservices xuất hiện JA3 fingerprint mới, nhưng destinations và app deployments khớp change record.

**Gợi ý:** phân nhóm theo release/identity/process, so baseline và flow metrics, kiểm tra IOC độc lập. Không chặn mọi instance fingerprint mới; ghi drift và test các trường hợp thực sự xấu.

### Bài 5 — QUIC Initial

Sensor QUIC v1 đọc được một ClientHello trong Initial packets nhưng không thể xuất HTTP/3 request path.

**Gợi ý:** QUIC Initial packet protection không nhằm bảo mật against passive observation như 1-RTT; TLS handshake metadata có thể decode nhưng HTTP/3 contents được bảo vệ. Chú ý ECH inner.

### Bài 6 — DNS và CDN

Một resolver log cho biết một endpoint hỏi DNS về **report.partner.example**, rồi endpoint gửi TLS tới IP CDN chung. Một hostname khác cũng dùng IP đó.

**Gợi ý:** đây là DNS-to-flow inference với confidence phụ thuộc time window/cache/client mapping; không được coi IP alone chứng minh domain/URL. Correlate endpoint/proxy/active app evidence.

### Bài 7 — mTLS và TLS interception

Ứng dụng gọi partner bằng client certificate mTLS. Enterprise forward proxy muốn terminate TLS, khiến app handshake lỗi.

**Gợi ý:** proxy đã thay trust boundary và có thể phá client certificate semantics/pinning. Xem mTLS/P KI design, scoped exclusions/approved alternatives, endpoint/app audit; không tắt certificate verification.

### Bài 8 — Không thấy ClientHello

NDR ghi một TCP 443 flow dài, không có ClientHello. SOC đánh nhãn “encrypted tunnel evasive”.

**Gợi ý:** kiểm tra capture start time, midstream, sensor packet drops, NAT/asymmetric route, parser supported protocols và handshake. Không suy malicious từ field trống.

### Bài 9 — Tính precision và recall

Trong một bộ lab có nhãn, 24 suspicious scenarios được alert, 6 bị bỏ sót; 8 benign scenarios bị alert. Hãy tính precision/recall.

**Gợi ý:** TP=24, FN=6, FP=8. Precision = 24/32 = **75%**; recall = 24/30 = **80%** trên **bộ lab**, không tuyên bố đó là production efficacy.

### Bài 10 — Xây hệ đo cho tổ chức đa vùng

Một doanh nghiệp có office LAN, cloud VPCs, VPN remote, service mesh, SaaS và QUIC browser traffic. Hãy:

1. Vẽ **network vantage** trước/sau NAT, proxy và mesh gateway.
2. Ghi **TLS 1.2/1.3/QUIC/ECH** fields nào mỗi sensor có thể thu.
3. Tạo schema **source provenance + confidence + visibility status**.
4. Thiết kế correlate **Zeek/Suricata, DNS, NAT, EDR và app logs**.
5. Định nghĩa **sensor coverage, packet loss, handshake capture, unknown SNI, certificate observability**.
6. Xây **negative tests** cho parser-missing, shared CDN IP, QUIC fallback và NAT reuse.
7. Nêu policy **PCAP/session keylog/privacy** với retention và RBAC.
8. Đưa ra quy tắc viết SOC conclusion phân biệt **observed, inferred, confirmed**.

**Gợi ý:** bắt đầu từ khả năng nhìn thấy ở mỗi điểm/hop rồi mới định nghĩa IOC/detection. Không chọn tool trước khi hiểu control objectives và trust boundary.

## 33. Checklist triển khai giám sát TLS metadata

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Tất cả in-scope ingress/egress paths đã được lập bản đồ? | Architecture, route/NAT/PEP diagrams |
| Sensor nằm trước hay sau TLS termination? | Packet path và LB/proxy mode |
| TLS 1.2, TLS 1.3 và QUIC/HTTP3 được nhận diện đúng? | Parser capability và test captures |
| Có xử lý ECH outer/inner visibility đúng không? | ECH-specific test và schema labels |
| Có phân biệt offered và negotiated TLS parameters/ALPN? | Protocol parser logic và validation |
| Có dùng supported_versions thay legacy markers phù hợp? | TLS 1.3 handshake tests |
| Certificate fields có provenance (passive/active/PKI)? | Data contract, source attributes |
| TLS resumption/0-RTT được phân lớp đúng? | Handshake variant tests |
| QUIC Initial và 1-RTT khác nhau trong parser? | Supported version tests, no plaintext assumptions |
| SNI absent có nhiều lý do được mã hóa thành reason? | Visibility state, capture completeness |
| DNS attribution không bị đánh nhãn observed SNI? | Separate inferred and observed fields |
| TLS fingerprint được versioned và contextualized? | Algorithm version, cohort baseline |
| NAT/proxy/mesh mapping đủ xác định endpoint? | NAT logs, proxy session IDs, EDR identities |
| Sensor có capture cả hai chiều và packet-drop metrics? | Interface counters, end-to-end test |
| Có kiểm thử IPv4/IPv6, UDP/TCP, multi-zone? | Coverage matrix và evidence |
| Có đủ application evidence cho câu hỏi nội dung? | App/proxy audit, user/action/status |
| Detection kết luận ở mức observed/inferred/confirmed? | Alert playbook và review records |
| False positives/negatives có test samples có nhãn? | Scenario test set và metrics |
| Metrics có denominator và unknown rõ? | Definitions + quality dashboard |
| Policy bypass được chặn ở enforcement point phù hợp? | Firewall/PEP positive/negative tests |
| TLS interception đã đánh giá mTLS/pinning/privacy? | Risk assessment, approval/exception |
| PCAP/keylog có phạm vi, RBAC, retention? | Data-handling controls và audit |
| Logs không chứa raw tokens/cookies trái chính sách? | Redaction checks và access review |
| Parser/schema changes có regression tests và owner? | Versioned config và release validation |
| Các findings có owner, severity và revalidation? | Incident/remediation tickets |

## 34. Tổng kết

**TLS metadata và giới hạn quan sát nội dung** là một chủ đề nền tảng của **giám sát mạng và telemetry**. Passive network sensors có thể quan sát **địa chỉ/port, thời điểm, lưu lượng, một số trường handshake và đặc điểm fingerprint**, nhưng không nên bị nhầm với việc **đọc HTTP requests, API headers, dữ liệu tải lên hay application actions** trong các kết nối TLS/QUIC được mã hóa đúng cách.

Đặc biệt, **TLS 1.3 mã hóa server Certificate và selected ALPN**, **ECH che ClientHelloInner cùng hostname thực**, và **QUIC/HTTP3 thay transport, handshake parsing, multiplexing và connection tracking**. TLS 1.2 full handshake, TLS 1.3, session resumption và QUIC không có cùng mức observability. SNI, DNS, ALPN offered, JA3/JA4-style fingerprints và traffic timing là **tín hiệu để hình thành giả thuyết**, không phải bằng chứng chắc chắn về URL, nội dung, danh tính user hoặc hành vi độc hại.

Trong hệ thống **SECURITY_NETWORK_SECURITY**, một mô hình giám sát đáng tin phải đặt cảm biến ở **đúng đường mạng**, công khai **packet loss/coverage/parser limitations**, tương quan **Zeek/Suricata/flow logs/DNS/firewall/NAT với EDR, proxy và application audit** theo thời gian/identity có thể kiểm chứng, và bảo vệ quyền riêng tư của telemetry. Khi nội dung ứng dụng cần được xác minh, phải tìm bằng chứng tại **điểm TLS termination hoặc endpoint có thẩm quyền**, không suy quá mức từ encrypted packets.

Một kết quả điều tra hoặc dashboard được xem là có chất lượng khi phân biệt được **observed facts, inferred context, unknown fields và confirmed application events**, có **positive/negative tests, confidence/coverage metrics, chủ sở hữu và quy trình xử lý sự cố**. Đó là cách giám sát lưu lượng mã hóa có giá trị thực tế mà vẫn giữ đúng giới hạn kỹ thuật, bảo mật và quyền riêng tư.
