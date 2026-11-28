# Phân tích TLS handshake packet: Đọc từng lớp giao thức, xác minh bảo mật và chẩn đoán lỗi kết nối

## 1. Đặt vấn đề: Trong một bản packet capture, “TLS bắt tay” trông như thế nào?

Khi trình duyệt kết nối đến một dịch vụ **HTTPS**, nhiều thao tác diễn ra trước khi ứng dụng nhận được HTTP response: DNS resolution (nếu cần), định tuyến IP, kết nối TCP hoặc một transport khác, thỏa thuận tham số TLS, kiểm tra danh tính máy chủ, trao đổi khóa và cuối cùng là truyền dữ liệu ứng dụng được bảo vệ. **TLS handshake** là quá trình hai đầu kết nối thống nhất giao thức, bộ mật mã/cơ chế trao đổi khóa, xác thực danh tính phù hợp và tạo khóa phiên để bảo vệ traffic.

Trong học phần **SECURITY_NETWORK_SECURITY**, bài **Phân tích TLS handshake packet** thuộc chương **Packet capture và phân tích lưu lượng**. Mục tiêu không phải chỉ “nhìn thấy HTTPS trên Wireshark”, mà là đọc gói theo đúng thứ tự và hiểu **những gì packet capture chứng minh được, những gì bị mã hóa và những gì phải xác minh ở endpoint hoặc ở hệ thống ứng dụng**. Khả năng này giúp phân tích sự cố firewall/proxy, VPN, IDS/IPS, mTLS, certificate, DNS, network monitoring và cloud ingress/egress.

Ví dụ: client báo lỗi không truy cập được **https://api.lab.example**. Trong bản capture tại client, bạn thấy **TCP three-way handshake** thành công và **TLS ClientHello** rời đi, nhưng không thấy **ServerHello**. Đây là bằng chứng client đã bắt đầu TLS, **không đủ** để kết luận certificate server hết hạn. Lỗi có thể nằm ở network path, proxy, server overload hoặc capture thiếu chiều phản hồi. Ngược lại, khi ServerHello xuất hiện và phiên thất bại ngay sau đó, hướng điều tra phải thay đổi.

### 1.1. Mục tiêu học tập

Sau khi học xong, bạn có thể:

1. Xác định **capture point, TCP stream, TLS record và handshake message**; phân biệt retransmission với một lần handshake mới.
2. Đọc **ClientHello, ServerHello, Certificate, CertificateVerify, Finished, ChangeCipherSpec và Alert** theo phiên bản phù hợp.
3. So sánh **TLS 1.2 với TLS 1.3**, đặc biệt các trường còn nhìn thấy khi không có khóa giải mã.
4. Giải thích **SNI, ALPN, supported_versions, supported_groups, signature_algorithms, key_share, PSK, resumption, 0-RTT và ECH** mà không suy diễn sai.
5. Phân biệt **certificate đã được gửi**, **certificate đã được xác minh** và **danh tính đã được ứng dụng cấp quyền**.
6. Dùng **Wireshark, tshark, tcpdump** với capture/filter phù hợp cho một phiên TLS trong lab được ủy quyền.
7. Chẩn đoán **không có ServerHello, handshake failure, certificate errors, mTLS failure, protocol mismatch, handshake latency, TLS interception** theo bằng chứng.
8. Thiết kế telemetry kết hợp **PCAP, DNS, flow, proxy, TLS logs và application tracing**, tôn trọng quyền riêng tư và giới hạn quan sát do mã hóa.

### 1.2. Quy tắc an toàn khi học bằng packet capture

Packet capture có thể ghi lại địa chỉ IP, hostname, cookie, token, đường dẫn URL, thông tin định danh hoặc dữ liệu nội bộ. Chỉ capture **thiết bị, tài nguyên và lưu lượng bạn được phép quan sát**, với phạm vi, thời lượng và mục đích rõ ràng. Bài dùng **192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24** và các tên miền **.example** làm dữ liệu tài liệu; chúng không phải endpoint thực để kết nối.

Trong lab, ưu tiên **máy thử, chứng thư thử, dữ liệu giả và PCAP giới hạn số gói**. Không thu thập hoặc chia sẻ **TLS session secrets, private keys, cookie và token thực** của người khác. Việc giải mã TLS chỉ được thực hiện trên **phiên do bạn kiểm soát và đã được phê duyệt**, với bảo vệ khóa tương ứng.

## 2. Trước TLS: DNS, IP, TCP và điểm đặt sensor

### 2.1. Mô hình tầng giao thức

Một HTTPS request thông thường qua TCP:

~~~text
Application:   HTTP/1.1 hoặc HTTP/2
Security:      TLS 1.2 hoặc TLS 1.3
Transport:     TCP, ví dụ port 443
Network:       IPv4/IPv6, routing, NAT, firewall
Link:          Ethernet / Wi-Fi / overlay / virtual NIC
~~~

**HTTP/3** dùng **QUIC trên UDP**, không dùng các TLS record trên TCP theo cách trong ví dụ. QUIC có tích hợp TLS 1.3 handshake messages qua **CRYPTO frames**; cách đọc packet và khả năng giải mã khác. Phần QUIC được phân biệt ở mục riêng.

Một số ứng dụng dùng TLS ngoài cổng 443: database TLS, LDAP over TLS, SMTP submission, MQTT over TLS, VPN control channels hoặc giao thức đặc thù. Vì vậy **port 443 không chứng minh traffic là TLS**, và TLS có thể xuất hiện trên port khác.

### 2.2. TCP bắt tay không phải TLS bắt tay

~~~mermaid
sequenceDiagram
    participant C as TLS client
    participant S as TLS server
    C->>S: TCP SYN
    S-->>C: TCP SYN, ACK
    C->>S: TCP ACK
    Note over C,S: TCP connection established
    C->>S: TLS ClientHello
    S-->>C: TLS ServerHello và các handshake messages
    C->>S: TLS handshake response/Finished
    Note over C,S: TLS handshake hoàn tất nếu hai bên xác minh thành công
    C->>S: Application data được bảo vệ
~~~

Sơ đồ khái quát, không thể hiện chính xác từng message của mọi phiên bản. Khi đọc capture:

- **SYN/SYN-ACK/ACK** xác nhận tiến trình thiết lập TCP, không xác nhận certificate.
- **ClientHello** là phần khởi đầu của TLS handshake phía client.
- **ServerHello** là kết quả lựa chọn tham số TLS phía server trong luồng bình thường.
- **Application Data** có thể xuất hiện dưới dạng bản ghi đã mã hóa; không đồng nghĩa nội dung là HTTP nếu protocol đã thỏa thuận là giao thức khác.

### 2.3. Chọn đúng capture point

| Capture point | Có thể nhìn thấy | Điều không thể tự biết |
| --- | --- | --- |
| **Client NIC/host** | DNS/TCP/TLS do client phát/nhận trên interface đó | Đường đi sau firewall/proxy và luồng qua interface khác |
| **Server NIC/host** | Traffic tới endpoint/server listener thực | Traffic bị chặn trước khi đến server |
| **Network TAP/SPAN** | Packets đi qua port/segment được mirror | Traffic đi qua route/VLAN/overlay khác |
| **Firewall/egress gateway** | Flow verdict và packets nếu capture được | Process/browser context nếu không có telemetry khác |
| **Reverse proxy/WAF** | TLS giữa client và proxy, có thể cả upstream leg | TLS client→origin trực tiếp nếu bypass proxy |
| **Kubernetes Pod/Node** | Default pod networking hoặc host packets theo điểm đo | hostNetwork, SR-IOV/secondary interfaces ngoài hook |
| **Cloud flow logs** | 5-tuple, bytes, allow/deny theo dịch vụ | Thường không có raw TLS handshake payload |

**Không thấy ServerHello tại client** chưa chứng minh server không gửi nó: một chiều có thể mất trên đường hoặc sensor bỏ gói. Muốn kết luận phải xem **client capture, server capture, firewall verdict và logs theo thời điểm**.

### 2.4. TLS termination thay đổi đối tượng phân tích

~~~mermaid
flowchart LR
    C["Client / browser"] -->|"TLS session A"| P["Reverse proxy / WAF / LB"]
    P -->|"TLS session B nếu re-encrypt"| O["Application origin"]
    P -. "HTTP plaintext nếu kiến trúc cho phép" .-> O
    F["Firewall / network sensor"] -. "Chỉ thấy session trên đường sensor đo" .-> P
~~~

TLS session A và session B có thể có **certificate, protocol version, ALPN và handshake timings khác nhau**. Nếu đo ở origin, bạn có thể chỉ thấy **proxy là TLS client**. Không gán chứng thư origin hoặc SNI của proxy upstream thành chứng thư người dùng nhìn thấy trên browser nếu chưa đối chiếu đúng hop.

## 3. Ba cấp cấu trúc: Packet, TLS record và handshake message

### 3.1. TCP byte stream khác ranh giới packet

TLS sử dụng **record protocol** để đóng gói dữ liệu trên TCP. Nhưng TCP là **byte stream**, không bảo toàn message boundaries. Vì thế:

- **Một TCP segment** có thể chứa nhiều TLS records.
- **Một TLS record** có thể bị chia qua nhiều TCP segments.
- **Một handshake message** có thể bị chia qua nhiều TLS records.
- Một TLS record có thể chứa nhiều handshake messages, tùy phiên bản và trạng thái.
- **TCP retransmission** có thể làm các bytes handshake xuất hiện lại trong capture.
- **NIC offloading/GRO/TSO** hoặc capture ở host có thể làm frame size nhìn thấy khác kích thước gói trên wire.

**Đừng đếm số TCP packets chứa handshake bytes thành số lần thực hiện handshake.** Hãy sử dụng TCP stream reassembly và trạng thái protocol của Wireshark.

### 3.2. TLS record header truyền thống

Với TLS trên TCP, dạng record trước khi diễn giải phần mã hóa:

~~~text
TLS record header:
  ContentType       1 byte
  legacy_version    2 bytes
  length            2 bytes
  fragment          length bytes

Ví dụ ContentType:
  0x14 = change_cipher_spec (20)
  0x15 = alert              (21)
  0x16 = handshake          (22)
  0x17 = application_data   (23)
~~~

Trong TLS 1.3, **record header và legacy_version** phục vụ tương thích. Một TLS 1.3 connection có thể có **legacy record version 0x0303**, giống cách biểu diễn thường gắn với TLS 1.2. **Không dùng trường record version một mình để kết luận phiên chỉ hỗ trợ TLS 1.2**.

### 3.3. Handshake message header

Trong TLS handshake payload có khái niệm:

~~~text
Handshake:
  msg_type          1 byte
  length            3 bytes (24-bit)
  body              length bytes
~~~

Một số type thường gặp:

| Giá trị | Tên handshake message | Bối cảnh |
| ---: | --- | --- |
| **1** | ClientHello | Client đề xuất các tham số |
| **2** | ServerHello | Server chọn tham số / biểu diễn HRR đặc biệt trong TLS 1.3 |
| **4** | NewSessionTicket | Ticket cho nối lại phiên, phiên bản tùy cấu trúc |
| **8** | EncryptedExtensions | TLS 1.3, nằm trong phần mã hóa sau ServerHello |
| **11** | Certificate | Certificate chain nếu phương thức xác thực sử dụng |
| **13** | CertificateRequest | Yêu cầu chứng thư client trong các trường hợp thích hợp |
| **14** | ServerHelloDone | TLS 1.2; không nằm trong full TLS 1.3 handshake |
| **15** | CertificateVerify | Chứng minh sở hữu private key ký handshake transcript |
| **16** | ClientKeyExchange | TLS 1.2; không dùng theo cấu trúc TLS 1.3 |
| **20** | Finished | Xác nhận transcript bằng bí mật đã dẫn xuất |
| **24** | KeyUpdate | TLS 1.3, sau handshake theo điều kiện |

Các giá trị là handshake type codes; **không phải mọi message sẽ hiện plaintext trong capture**. TLS 1.3 mã hóa nhiều handshake messages sau ServerHello nên bạn có thể chỉ thấy outer record type **application_data** nếu không giải mã.

### 3.4. Những byte đầu không phải lúc nào cũng bắt đầu tại record boundary

Nếu capture bắt giữa TCP stream, Wireshark có thể không biết một số bytes đầu thuộc fragment nào; có thể có **TCP Previous segment not captured** hoặc TLS decode lỗi. Đừng kết luận “TLS record hỏng” chỉ từ một gói chưa đủ reassembly.

Ưu tiên:

1. Bắt được phần **đầu TCP connection** và segment chứa ClientHello.
2. Kiểm tra **capture loss, TCP reassembly, out-of-order/retransmission**.
3. Gắn **tcp.stream** hoặc kết nối theo 5-tuple + thời gian.
4. Xem **Follow TCP Stream** với hiểu biết dữ liệu sẽ có phần binary.

## 4. TLS 1.2 full handshake: Những gì có thể nhìn thấy

### 4.1. Luồng điển hình khi dùng certificate và ephemeral key exchange

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: ClientHello
    S-->>C: ServerHello
    S-->>C: Certificate
    S-->>C: ServerKeyExchange (ví dụ ECDHE)
    S-->>C: ServerHelloDone
    C->>S: ClientKeyExchange
    C->>S: ChangeCipherSpec
    C->>S: Finished (được bảo vệ)
    S-->>C: ChangeCipherSpec
    S-->>C: Finished (được bảo vệ)
    Note over C,S: Ứng dụng bắt đầu trao đổi dữ liệu đã bảo vệ
~~~

Đây là **ví dụ khái quát cho TLS 1.2 với ECDHE và xác thực server certificate**, không phải mọi cipher suite đều có đúng messages này. Chẳng hạn:

- Client hoặc server có thể yêu cầu/đưa **client certificate** trong mTLS.
- TLS 1.2 **resumed/abbreviated handshake** có thứ tự khác full handshake.
- Một số phương thức trao đổi khóa TLS 1.2 cũ dùng bộ message khác.
- Các extension, session ticket, status messages có thể bổ sung thành phần.

### 4.2. Khi nào Wireshark thấy certificate của server?

Với **TLS 1.2 full handshake** trong cấu hình thường gặp, **Certificate message** của server được gửi trước khi bên client bắt đầu bảo vệ handshake dưới các khóa phiên. Một passive capture đầy đủ thường có thể phân tích **certificate chain bytes** nếu không có một lớp bảo vệ/tunnel khác che nó.

Với **TLS 1.3**, certificate của server thường nằm **trong phần handshake đã mã hóa**, nên passive capture không có secrets thường **không đọc được certificate**. Đây là một khác biệt rất quan trọng khi nghiên cứu PCAP.

### 4.3. Độ trễ và round trips

Một full TLS 1.2 handshake qua TCP, theo luồng điển hình, cần thêm các trao đổi trước khi ứng dụng truyền data. Tuy nhiên con số RTT thực tế phụ thuộc vào:

- TCP connection mới hay đã có.
- TLS full hay abbreviated/resumed.
- Đường mạng và các proxy/tunnel.
- TCP retransmission, server processing và chứng thư/mTLS.
- Client có đợi hoàn tất xác minh và server Finished trước khi gửi request hay không.

**Đừng suy ra latency chỉ từ tên giao thức.** Đo **timestamp theo từng bước** trên đúng capture point và phân biệt network RTT với CPU/validation delay.

## 5. TLS 1.3 handshake: Nhanh hơn nhưng ít nhìn thấy hơn

### 5.1. Luồng đầy đủ cơ bản

~~~mermaid
sequenceDiagram
    participant C as TLS 1.3 client
    participant S as TLS 1.3 server
    C->>S: ClientHello + key_share + supported_versions
    S-->>C: ServerHello + key_share / selected_version
    Note over C,S: Sau ServerHello, handshake traffic được bảo vệ
    S-->>C: EncryptedExtensions (encrypted)
    S-->>C: Certificate (encrypted, nếu dùng)
    S-->>C: CertificateVerify (encrypted)
    S-->>C: Finished (encrypted)
    C->>S: Finished (encrypted)
    Note over C,S: Application Data protected
~~~

Sơ đồ thể hiện **full TLS 1.3 handshake có certificate authentication**, không thể hiện trường hợp PSK-only, 0-RTT, HelloRetryRequest hay client authentication. TLS 1.3 kết hợp key exchange và handshake để có khả năng **1-RTT cho full handshake** trong trường hợp thông thường, so với những bước nhiều hơn của TLS 1.2 full handshake.

### 5.2. Thấy “Application Data” chưa có nghĩa HTTP đã chạy

Kể từ sau **ServerHello**, phần lớn handshake TLS 1.3 được đóng trong **encrypted TLS records**, có **outer content type application_data**. Khi không giải mã, Wireshark có thể liệt kê chúng là **Application Data** dù payload thực sự là **EncryptedExtensions, Certificate, CertificateVerify hoặc Finished**.

Vì vậy:

> Một bản ghi outer **Application Data** đầu tiên sau ServerHello **không tự chứng minh client hoặc server đã gửi HTTP request/response**.

Muốn phân tích nội dung handshake ẩn, phải có **endpoint logs hoặc secrets phiên lab được cấp phép** và đúng Wireshark/TLS dissector.

### 5.3. TLS 1.3 không dùng cùng cipher suite naming như TLS 1.2

Trong TLS 1.2, tên cipher suite thường gộp **key exchange/authentication + symmetric cipher + hash** (ví dụ bộ suite ECDHE_RSA_...). Trong TLS 1.3, cipher suite chủ yếu chọn **AEAD symmetric cipher và hash**, còn key exchange/signature algorithms được thương lượng qua extensions riêng.

Không tìm chuỗi ECDHE trong **TLS_AES_128_GCM_SHA256** rồi kết luận phiên không dùng ephemeral key exchange. Cần xem **supported_groups, key_share, signature_algorithms** và các quyết định TLS 1.3 liên quan.

### 5.4. Legacy fields thường làm người mới đọc PCAP hiểu nhầm

Trong **TLS 1.3 ClientHello**:

- **legacy_version** thường mang **0x0303** (TLS 1.2) để tương thích.
- Phiên bản đề xuất nằm trong extension **supported_versions**.
- **legacy_session_id** có thể có giá trị dùng cho middlebox compatibility.
- Record header version cũng dùng giá trị tương thích.

Trong **ServerHello**, phiên bản được chọn cho TLS 1.3 thể hiện qua **supported_versions**; không chỉ nhìn trường legacy_version. Một số phiên có **dummy ChangeCipherSpec** cho middlebox compatibility; nó **không chứng minh TLS 1.3 đã chuyển sang một cách mã hóa cổ điển như TLS 1.2**.

### 5.5. Vì sao TLS 1.3 ẩn certificate?

TLS 1.3 bảo vệ các message xác thực server sau khi hai bên dẫn xuất được handshake traffic secrets. Một passive observer thường chỉ đọc **ClientHello, ServerHello và thông tin outer record**, không thấy thông tin certificate ở các encrypted messages tiếp theo.

Điều này tăng bảo mật metadata, nhưng không làm biến mất mọi rò rỉ: **IP, port, timing, packet sizes** vẫn có thể quan sát; **SNI** thường hiện trong ClientHello nếu chưa dùng ECH; **ALPN được gửi ở một số bước khác nhau và có giới hạn visibility**. Không dùng câu “TLS 1.3 che toàn bộ handshake” khi ClientHello vẫn chứa nhiều trường chưa mã hóa.

## 6. Giải mã ClientHello: Những câu hỏi quan trọng nhất

### 6.1. ClientHello là đề xuất, không phải quyết định cuối cùng

Một ClientHello có thể chứa:

| Thành phần | Client cung cấp | Điều có thể kết luận |
| --- | --- | --- |
| **Random** | 32-byte random field | Dữ liệu phục vụ bắt tay, không phải khóa bí mật |
| **legacy_version** | Giá trị tương thích | Không tự xác định TLS 1.3 hay TLS 1.2 |
| **Session ID / legacy_session_id** | Dữ liệu liên quan phiên/tương thích | Không đủ chứng minh resumption thành công |
| **Cipher Suites** | Danh sách suite client đề xuất | Không chứng minh suite nào được chọn |
| **Compression Methods** | Trường tương thích theo phiên bản | Không suy ra compression nội dung được phép |
| **Extensions** | SNI, ALPN, key shares, signature algorithms... | Phải hiểu extension và phiên bản cụ thể |

**Cặp ClientHello–ServerHello** giúp hiểu client chào gì và server chọn gì trong các phần nhìn thấy. Cần tiếp tục phân tích handshake hoàn tất mới có thể kết luận hai bên thực sự thiết lập phiên bảo vệ thành công.

### 6.2. SNI — Server Name Indication

**SNI** là extension cho client báo hostname mục tiêu để một server/proxy chia sẻ IP có thể chọn chứng thư và virtual host thích hợp. Ví dụ client kết nối đến **192.0.2.20:443** nhưng gửi SNI **api.lab.example**.

**Không nên suy diễn:**

- SNI không nhất thiết là một identity đã được xác thực.
- SNI do client cung cấp có thể không khớp HTTP Host/:authority.
- Không phải mọi TLS client đều gửi SNI.
- SNI có thể bị bảo vệ/ẩn trong những triển khai **Encrypted ClientHello (ECH)**.
- Một IP có thể phục vụ nhiều tên SNI và một hostname có thể phân giải nhiều IP.

Khi phân tích **SNI mismatch**, cần kiểm tra TLS certificate SAN, HTTP routing và policy của reverse proxy. Một thiết bị mạng **chỉ lọc dựa SNI nhìn thấy** không tự xác minh server identity hoặc application authorization.

### 6.3. ALPN — Application-Layer Protocol Negotiation

**ALPN** cho phép thỏa thuận protocol ứng dụng trên cùng kết nối TLS. Ví dụ client có thể đề xuất **h2** (HTTP/2) và **http/1.1**.

- **ClientHello ALPN list** là các lựa chọn client đề xuất.
- Với **TLS 1.2**, thông tin lựa chọn có thể nằm trong ServerHello và thường nhìn thấy trong capture.
- Với **TLS 1.3**, lựa chọn ALPN của server nằm trong **EncryptedExtensions**, thường **không nhìn thấy khi không giải mã**.
- Không thấy ALPN không chứng minh không có HTTP; một số ứng dụng có cơ chế mặc định hoặc giao thức riêng.
- Không được gán protocol **h2** chỉ vì client đề xuất nó; phải xác định server đã chọn nếu cần kết luận.

Ví dụ kiểm thử lỗi: client chỉ hỗ trợ **h2** nhưng upstream proxy/application không hỗ trợ protocol tương thích. Đối chiếu **ALPN offered, ALPN selected (nếu có), TLS logs và HTTP protocol logs** trước khi quy lỗi cho TCP.

### 6.4. supported_versions và việc thương lượng TLS phiên bản

ClientHello TLS 1.3 thường mang extension **supported_versions** có thể đề xuất TLS 1.3 cùng TLS 1.2 (tùy client policy). Server chọn phiên bản và biểu thị theo cơ chế tương ứng.

Những câu hỏi:

1. Client **đề xuất** phiên bản nào?
2. Server **chọn** phiên bản nào?
3. Có gateway trung gian tạo **hai TLS sessions khác phiên bản** không?
4. Có fallback do phiên bản, cipher suites hay cấu hình server?
5. Có chứng cứ handshake kết thúc thành công không?

**Không báo “server dùng TLS 1.2” chỉ vì ClientHello legacy_version là 0x0303**. Đây là lỗi đọc capture TLS 1.3 rất thường gặp.

### 6.5. supported_groups và key_share

Trong TLS 1.3, client có thể thông báo **supported_groups** (các nhóm trao đổi khóa được hỗ trợ) và gửi một hoặc nhiều **key_share entries**. Server chọn group/key share phù hợp hoặc yêu cầu client thử lại.

**Key share không phải private key**. Trong handshake trao đổi khóa kiểu ephemeral Diffie–Hellman, bytes public key share có thể được quan sát; không vì thấy public share mà suy ra đủ bí mật để giải mã phiên.

Khi điều tra **handshake_failure/illegal_parameter**, cần xem:

- Client và server có nhóm tương thích không?
- HelloRetryRequest có xuất hiện không?
- Các key shares có khớp nhóm được chọn?
- Có middlebox hoặc policy làm hỏng extension?
- TLS implementation có hỗ trợ nhóm/thuật toán được triển khai?

Không tự suy ra **độ an toàn tổng thể** chỉ từ tên group: còn thuật toán chữ ký, certificate, implementation, policy, trust và trạng thái cập nhật.

### 6.6. signature_algorithms và authentication

**signature_algorithms** mô tả những thuật toán/kiểu chữ ký liên quan client hỗ trợ cho handshake/certificate validation theo phiên bản. Nó **không phải** danh sách tất cả certificate chains được client chấp nhận.

Một lỗi có thể xuất hiện khi client/server không có thuật toán chữ ký tương thích, cert key type không phù hợp hoặc chain bị policy từ chối. Cần ghép **handshake message + server/client TLS logs + certificate details** nếu TLS 1.3 không cho nhìn certificate.

### 6.7. GREASE và extension lạ

Một số client gửi các giá trị **GREASE** (Generate Random Extensions And Sustain Extensibility) để kiểm tra khả năng bỏ qua những giá trị chưa biết. Những giá trị trông “lạ” trong cipher suite/extension/group lists **không tự chứng minh packet bị hỏng hay là tấn công**.

Wireshark thường có khả năng nhận diện các giá trị GREASE được biết. Đừng tạo báo cáo chỉ vì “unknown extension” mà không đối chiếu implementation/version và chuẩn mở rộng.

### 6.8. pre_shared_key, psk_key_exchange_modes và early_data

Khi client hỗ trợ **resumption**, ClientHello TLS 1.3 có thể mang thông tin PSK identities/binders, cùng **psk_key_exchange_modes** và các extensions khác. **PSK identity/binder không phải session secret để dùng giải mã**.

Khi bắt lại PCAP:

- Thấy extension **pre_shared_key** chỉ chứng minh **client đề xuất** một cơ chế PSK/resumption.
- Phải xem **ServerHello selection** và trạng thái phiên mới biết server có chấp nhận hay không.
- Nếu **early_data** được chào, chưa chắc server cho phép 0-RTT.
- TLS 1.3 PSK resumption có nhiều chế độ/key establishment; không mặc định mỗi phiên đều có certificate mới.

## 7. Đọc ServerHello và nhận diện thương lượng thực tế

### 7.1. ServerHello: Kết quả lựa chọn trong trường hợp bình thường

ServerHello thường chứa **server random, session ID compatibility value, selected cipher suite và các extensions** theo phiên bản. Những gì đã được chọn phải được đánh giá **cùng ClientHello**, không dùng ServerHello đơn lẻ.

Ví dụ tình huống giả lập:

~~~text
ClientHello:
  offered: TLS 1.3, TLS 1.2
  offered TLS 1.3 cipher suites:
    TLS_AES_128_GCM_SHA256
    TLS_AES_256_GCM_SHA384
  SNI: api.lab.example
  ALPN offered: h2, http/1.1
  key_share: supported group(s)

ServerHello:
  selected_version: TLS 1.3
  selected_cipher_suite: TLS_AES_128_GCM_SHA256
  selected_key_share: group chosen by server

After ServerHello:
  encrypted handshake records
  encrypted application traffic after completion
~~~

**Tất cả trường là dữ liệu minh họa.** Không gán lựa chọn ALPN **h2** nếu chưa nhìn thấy EncryptedExtensions đã giải mã hoặc endpoint logs; ClientHello offered list chưa xác định lựa chọn server.

### 7.2. HelloRetryRequest (HRR) của TLS 1.3

TLS 1.3 có **HelloRetryRequest** khi server cần client gửi ClientHello tiếp theo, chẳng hạn để dùng key share/group phù hợp. HRR được mã hóa theo **cấu trúc ServerHello với một giá trị random đặc biệt**, nên công cụ phân tích có thể hiển thị như một dạng ServerHello/HRR.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: ClientHello #1 (không có key share phù hợp)
    S-->>C: HelloRetryRequest (chỉ định yêu cầu)
    C->>S: ClientHello #2 (đã điều chỉnh)
    S-->>C: ServerHello
    S-->>C: Encrypted handshake flight
    C->>S: Encrypted Finished
~~~

**Hai ClientHello trong cùng TLS connection không tự là retransmission hoặc hai phiên độc lập.** Phân biệt:

- **TCP retransmission:** trùng cùng bytes/sequence range được gửi lại.
- **HRR:** client có **ClientHello #2 mới** để đáp ứng yêu cầu server.
- **TCP connection mới:** có 5-tuple/start time hoặc TCP stream khác.

Nếu HRR xuất hiện thường xuyên, có thể xem **key_share policy/group compatibility và latency cost**. HRR không tự là vulnerability.

### 7.3. Đàm phán không thành công và downgrade

Một số nguyên nhân:

- Không có TLS protocol versions giao nhau.
- Không có cipher suites hoặc nhóm trao đổi khóa/thuật toán ký phù hợp.
- Server policy yêu cầu certificate/mTLS mà client chưa đáp ứng.
- SNI routing tới sai listener/certificate.
- Middlebox làm thay đổi/hủy gói.

**TLS downgrade** là chủ đề riêng: không gọi mọi TLS 1.2 connection là downgrade attack. Phải xem **client/server capabilities, security policy, fallback mechanism và bằng chứng cụ thể**. TLS có các cơ chế chống downgrade tương ứng; TLS 1.3 có dấu hiệu downgrade trong server random khi đàm phán xuống những phiên bản nhất định, còn một số TLS clients cũ sử dụng **TLS_FALLBACK_SCSV** theo điều kiện.

Việc xác định **server đã chọn phiên bản thấp nhất hợp lệ do policy** khác với xác nhận có tấn công ép phiên bản xuống. Không được khẳng định MITM chỉ từ một handshake TLS 1.2 trong hệ thống còn hỗ trợ TLS 1.3.

### 7.4. Cipher suite và security posture

Một bảng kiểm tra phù hợp:

| Điều quan sát | Nên làm |
| --- | --- |
| Server chọn TLS 1.3 AEAD suite được policy hỗ trợ | Kiểm tra handshake/identity và ứng dụng |
| TLS 1.2 vẫn hoạt động ở môi trường yêu cầu TLS 1.3-only | Đối chiếu listener/proxy policy, exception và test |
| Cipher suite không tương thích với client | Xem offered/selected lists và server logs |
| Legacy/obsolete protocols xuất hiện | Xem đúng hop, inventory và kế hoạch deprecate |
| ClientHello chứa nhiều cipher suites lạ | Phân biệt GREASE, implementation specifics, policy |

Không cần lưu toàn bộ TLS handshake bytes của mọi user để đánh giá posture; nhiều môi trường có thể dùng **server TLS logs, scanner được ủy quyền và selected version/cipher telemetry** ở ingress/gateway.

## 8. Certificate handshake: Thấy certificate chưa có nghĩa tin cậy

### 8.1. Certificate chain và các khái niệm cần quan sát

Trong kết nối sử dụng chứng thư X.509, thông tin quan trọng gồm:

- **Subject và Subject Alternative Name (SAN)**: danh tính/hostname được chứng thư khai báo.
- **Issuer**: CA ký chứng thư hoặc định danh bên phát hành.
- **Validity**: notBefore/notAfter.
- **Public key và thuật toán chữ ký**: phục vụ xác minh chain/handshake.
- **Basic Constraints / Key Usage / Extended Key Usage**: hạn chế vai trò CA và mục đích.
- **Authority/Subject Key Identifier** và các thông tin hỗ trợ path-building.
- **Certificate chain/intermediates** mà server gửi trong handshake phù hợp.
- **Trust anchor** của client (thường trong trust store) và policy validation.

**Certificate message không xác minh chain hộ client.** Nó mang một hoặc nhiều chứng thư; client phải thực hiện **trust/path validation, hostname validation, validity/purpose checks** và các yêu cầu khác theo profile. Một server có thể gửi chain thiếu intermediate hoặc dùng chứng thư khác với hostname.

### 8.2. TLS 1.2 vs TLS 1.3 certificate visibility

| Câu hỏi | TLS 1.2 full handshake | TLS 1.3 full handshake |
| --- | --- | --- |
| ClientHello/ServerHello cơ bản có thể thấy? | Thường có | Thường có |
| Server Certificate plaintext trong PCAP passive? | Thường có trong full handshake dùng cert | Thường **không**, nằm trong encrypted handshake |
| Có thể kiểm tra SAN/notAfter chỉ từ PCAP passive? | Có thể nếu có cert đủ | Thường cần endpoint logs hoặc session secrets lab |
| Client Certificate trong mTLS có thể đọc từ PCAP? | Có thể trong luồng TLS 1.2 bình thường | Thường encrypted |
| PCAP chứng minh client đã **tin** certificate? | Không tự chứng minh | Không tự chứng minh |
| Certificate chain lúc resumption? | Có thể không được gửi | PSK-only resumption có thể không gửi cert |

Khi thấy **TLS 1.3 PCAP không có Certificate message**, không được tuyên bố server “không sử dụng certificate”. Nó có thể đã gửi message **bên trong encrypted application_data records**.

### 8.3. Phân biệt hostname, SNI và HTTP Host

Một HTTPS client thường:

1. Chọn hostname đích từ URL (hoặc service configuration).
2. Có thể dùng hostname đó làm **SNI**.
3. Kiểm tra certificate SAN/chain cho tên được yêu cầu theo chính sách.
4. Khi TLS đã đủ điều kiện, gửi HTTP request với **Host** (HTTP/1.1) hoặc **:authority** (HTTP/2), nếu có HTTP.

**Ba giá trị có thể khác nhau trong một số kiến trúc** (proxy, IP direct, domain fronting attempts, custom SNI). Không coi SNI là bằng chứng cert hợp lệ hoặc là client đã thực hiện HTTP GET.

### 8.4. Vai trò CertificateVerify và Finished

- **CertificateVerify** (trong phiên bản có message phù hợp) chứng minh thực thể đang tham gia handshake sở hữu private key thích hợp liên quan chứng thư và transcript.
- **Finished** xác nhận các bên tính toán được bí mật phù hợp và có cùng transcript kỳ vọng theo cơ chế TLS.

Sự hiện diện của một message trên dây **không tự chứng minh phía nhận đã chấp nhận nó**. Để biết xác minh thành công, phải xem **handshake tiến triển, application data, endpoint/library return codes và TLS logs**.

### 8.5. Chain khác trust store

Server có thể gửi leaf và intermediate certificates, trong khi **root CA trust anchor** nằm trong trust store phía client; root thường không cần gửi trong chain. Một passive capture có thể chứa leaf/intermediate nhưng **không cho biết client tin root nào** hoặc đã kiểm tra revocation theo policy nào.

Khi điều tra lỗi **unknown_ca, certificate_unknown, bad_certificate, certificate_expired** hay lỗi hostname:

- Xác định **đúng TLS hop** và đúng runtime/trust store (OS, JVM, container, browser, proxy).
- Đối chiếu **client's requested hostname** và SAN thực.
- Xem chain/intermediate distribution, validity và EKU.
- Dùng **endpoint/client logs**; không suy một alert mã hóa của TLS 1.3 thành một mã lỗi chứng thư cụ thể khi không có giải mã.

### 8.6. mTLS: Xác minh danh tính client ở handshake

Trong **mutual TLS**, server cũng yêu cầu client trình chứng thư và chứng minh sở hữu private key, theo profile/policy. Điều này phổ biến ở **service-to-service, API gateways, VPN/tunnel controls** và một số hệ thống quản trị.

~~~mermaid
sequenceDiagram
    participant C as mTLS client
    participant S as mTLS server
    C->>S: ClientHello
    S-->>C: ServerHello
    S-->>C: EncryptedExtensions, CertificateRequest (encrypted)
    S-->>C: Server Certificate, CertificateVerify, Finished (encrypted)
    C->>S: Client Certificate, CertificateVerify, Finished (encrypted)
    Note over C,S: TLS 1.3 example, assuming certificate authentication succeeds
~~~

Sơ đồ là **ví dụ TLS 1.3 mTLS**, lược bỏ các nhánh/biến thể như PSK resumption và post-handshake client authentication. Thứ tự và khả năng nhìn thấy khác ở **TLS 1.2**; đặc biệt, trong TLS 1.3, **CertificateRequest và client Certificate** trong handshake thường bị mã hóa sau ServerHello. Nếu client không có certificate phù hợp hoặc bị từ chối, luồng sẽ không hoàn tất như sơ đồ.

**mTLS xác thực peer/workload**, không tự cấp quyền trên từng API path, tenant hay dữ liệu nghiệp vụ. Backend/API gateway vẫn cần policy ánh xạ danh tính chứng thư sang quyền.

## 9. Resumption, Session Ticket và 0-RTT: Không phải mọi phiên đều có full handshake

### 9.1. Vì sao cần session resumption?

Nếu một ứng dụng tạo nhiều TLS connections tới cùng dịch vụ, thực hiện full handshake và certificate authentication mỗi lần có thể tăng latency/CPU. **Session resumption** cho phép sử dụng thông tin từ phiên trước theo cơ chế của TLS version/implementation để giảm thao tác.

Trong TLS 1.2 có các cơ chế resumption dựa trên **session ID hoặc session ticket**. TLS 1.3 sử dụng cơ chế **PSK-based resumption**, thường gắn với NewSessionTicket và các PSK identities/binders trong ClientHello kế tiếp.

**Không lấy một TLS 1.3 ClientHello có session ID field làm bằng chứng resumption.** legacy_session_id thường dùng cho middlebox compatibility; phải xem PSK offer/acceptance và trạng thái handshake.

### 9.2. Full vs resumed TLS 1.2

| Đặc điểm | TLS 1.2 full handshake | TLS 1.2 resumed/abbreviated |
| --- | --- | --- |
| Server Certificate | Thường được gửi khi dùng cert auth | Có thể không cần gửi lại |
| ServerKeyExchange | Có ở nhiều ECDHE full handshakes | Không giống full handshake |
| Session ID/ticket | Có thể thiết lập cơ chế cho lần sau | Được dùng/đề xuất để nối lại |
| Round trips | Nhiều hơn resumption theo luồng điển hình | Có thể giảm |
| Khả năng đọc cert từ capture riêng của phiên | Có thể nếu đầy đủ và full | Có thể không có cert mới |

Nếu phiên resumed không gửi certificate, **không được gọi đó là “HTTPS không xác thực máy chủ”** chỉ dựa vào PCAP. Nó có thể dựa vào state đã được thiết lập từ phiên trước; cần **endpoint TLS session logs** và chính sách resumption.

### 9.3. TLS 1.3 PSK resumption

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    Note over C,S: Phiên trước đã xác thực và thiết lập resumption state
    S-->>C: NewSessionTicket (được bảo vệ, post-handshake)
    Note over C,S: Kết nối TLS mới
    C->>S: ClientHello + pre_shared_key + binder
    S-->>C: ServerHello (PSK selection nếu được chấp nhận)
    S-->>C: Encrypted handshake flight
    C->>S: Finished
    Note over C,S: Application data protected
~~~

Trong TLS 1.3, **NewSessionTicket là post-handshake message và được bảo vệ**; khi chỉ có passive capture, bạn không nhìn thấy cấu trúc ticket nếu không có session secrets. Một client có thể đề xuất PSK nhưng server từ chối và thực hiện full handshake.

### 9.4. 0-RTT early data

**TLS 1.3 0-RTT** cho phép một client có resumption state từ trước gửi **early application data** trong flight đầu, khi server/policy hỗ trợ. Nó giảm latency nhưng **không cung cấp cùng khả năng chống replay như dữ liệu của phiên 1-RTT thông thường**.

Điều cần phân biệt:

- **ClientHello early_data extension / early records**: client đề xuất/sử dụng cơ chế theo state.
- **Server acceptance**: server có thể từ chối early data; phải xem response hoặc endpoint logs.
- **0-RTT replay risk**: ứng dụng phải thiết kế/giới hạn các operations phù hợp, ví dụ tránh xử lý lại tác vụ không idempotent nếu không có biện pháp bảo vệ.
- **0-RTT không có nghĩa thiếu mã hóa**: early data được bảo vệ bằng secrets dẫn xuất từ resumption state, nhưng có thuộc tính an ninh khác.

**Một record Application Data xuất hiện trước ServerHello không đủ kết luận chắc chắn 0-RTT hợp lệ**, vì cần xác định đúng TLS stream, extension/PSK state và tính đầy đủ của capture.

### 9.5. Session ticket, expiry và incident response

Khi điều tra một certificate/identity vừa bị thu hồi hoặc proxy vừa đổi policy, **resumption state và existing connections** có thể làm client không gửi lại full certificate handshake ngay lập tức. Cần kiểm tra:

1. Resumption ticket lifetime và server key rotation theo triển khai.
2. Server có kiểm tra lại quyền/identity khi resumption không?
3. Client có dùng long-lived connections thay vì tạo phiên mới?
4. Sự thay đổi certificate/truststore có tác động tới existing/resumed sessions ra sao?
5. Có cách revoke/expire session phù hợp theo business risk không?

Không dùng “không nhìn thấy Certificate trong PCAP” làm bằng chứng server bỏ qua xác thực sau một thay đổi certificate.

## 10. TLS Alert, lỗi xác thực và đóng kết nối

### 10.1. TLS Alert là gì?

**Alert protocol** báo trạng thái lỗi hoặc đóng an toàn một TLS connection theo ngữ cảnh. Một số alert descriptions thường gặp:

| Alert | Giả thuyết cần xem | Không nên kết luận |
| --- | --- | --- |
| **handshake_failure** | Không thống nhất TLS parameters hoặc policy | Chắc chắn do certificate hết hạn |
| **protocol_version** | Version không được hỗ trợ/chấp nhận | Chắc chắn một downgrade attack |
| **insufficient_security** | Không chấp nhận mức bảo mật được đề xuất | Lỗi mạng vật lý |
| **unknown_ca** | Trust anchor/chain không được chấp nhận theo endpoint | Certificate leaf chắc chắn giả |
| **bad_certificate** | Certificate không hợp lệ theo logic của peer | Một lý do cụ thể nếu không có logs |
| **certificate_expired** | Chứng thư nằm ngoài validity period theo bên kiểm tra | Đồng hồ luôn chính xác hoặc cert thuộc đúng hop |
| **certificate_required** | Chứng thư client bắt buộc nhưng không được cung cấp theo profile | Server certificate hỏng |
| **decrypt_error** | Một bước xác minh mật mã thất bại | Chắc chắn kẻ khác sửa gói |
| **illegal_parameter** | Một thông số message bị coi không hợp lệ | Chắc chắn lỗi của client |
| **unexpected_message** | Message không đúng trạng thái dự kiến | Chắc chắn middlebox tấn công |
| **close_notify** | Bên gửi thông báo đóng TLS theo semantics | Handshake thất bại |

Tùy phiên bản, một số alert descriptions có thể không áp dụng hoặc được dùng khác. **TLS 1.3 thường bảo vệ các Alerts sau khi có khóa**, nên passive capture không có secrets có thể **không thấy mã alert thực**; lúc đó cần endpoint/server TLS library logs.

### 10.2. Alert level và message là hai thứ khác nhau

Trong những phiên bản cũ, alert có trường **level** như warning/fatal và description. Trong TLS 1.3, cách xử lý mức cảnh báo có thay đổi theo đặc tả. Không áp dụng cơ học “warning luôn bỏ qua được” hoặc “mọi record type 21 đều là fatal”.

**Không có plaintext Alert** không đồng nghĩa không có TLS error. Một số server chấm dứt kết nối bằng TCP FIN/RST, đóng socket do proxy timeout hoặc gửi alert đã mã hóa.

### 10.3. TCP RST/FIN khác TLS Alert

| Quan sát | Có thể nói | Chưa thể nói |
| --- | --- | --- |
| **TCP RST sau ClientHello** | Connection bị reset sau client flight | Chắc chắn lỗi cert hoặc TLS version |
| **TCP FIN sau encrypted flight** | TCP side đóng kết nối | TLS close_notify có/không nếu không giải mã |
| **TCP SYN retransmissions** | Chưa thấy TCP establishment hoàn tất | TLS handshake đã bắt đầu |
| **Plaintext TLS Alert trước ServerHello** | Peer phát thông báo TLS cụ thể nếu decode đúng | Chính xác module nào gây lỗi không cần logs |
| **TLS 1.3 outer Application Data rồi FIN** | Có encrypted records rồi kết thúc TCP | Nội dung là HTTP hay encrypted alert |
| **Không có response trong một capture** | Sensor không ghi response ở vị trí đó | Server tuyệt đối không phản hồi |

Trong Wireshark, cần xem **TCP flags, RTT, retransmissions, ACK progression và TLS records** cùng nhau, không chỉ expert info màu đỏ.

### 10.4. Một “lỗi certificate” cần hai bằng chứng

Nếu một client báo **certificate verify failed**, những bằng chứng tối thiểu nên có:

1. **Client-side TLS error/log** ghi rõ validation failure, verification code hoặc trust policy.
2. **Certificate thực từ đúng hop** và tên đích, chain/truststore context.

PCAP TLS 1.2 có thể cho bạn chứng thư đã gửi; **nó không chứa truststore đầy đủ của client**. PCAP TLS 1.3 không có secrets có thể thậm chí không thấy chứng thư. **Hostname mismatch, unknown CA, expired certificate, revoked cert** là các nguyên nhân khác nhau cần kiểm chứng riêng.

### 10.5. Lỗi mTLS ở đâu?

Một request bị **HTTP 403 sau khi handshake hoàn tất** không giống việc **TLS handshake bị từ chối do client cert không hợp lệ**. Cần phân biệt:

- Gateway **không yêu cầu client certificate**, nhưng app authorization chặn user.
- Gateway **yêu cầu client certificate** và thiếu/sai certificate nên handshake thất bại.
- Gateway **chấp nhận certificate**, nhưng mapping cert subject/SAN sang workload entitlement bị deny ở L7.
- Client đang truy cập **sai TLS hop**: ingress/mTLS upstream tới backend khác.

Với TLS 1.3, chỉ dựa outer encrypted records rất khó nói server có gửi CertificateRequest hay không. Dùng **server-side mTLS logs và policy config**.

## 11. Encrypted ClientHello (ECH), quyền riêng tư và metadata giới hạn

### 11.1. Bài toán SNI quan sát được

Trong nhiều kết nối TLS thông thường, **SNI** nằm trong ClientHello không mã hóa và có thể tiết lộ hostname mục tiêu cho passive observer. **Encrypted ClientHello (ECH)** được thiết kế để bảo vệ những phần nhạy cảm của ClientHello, trong đó có tên thực bên trong **ClientHelloInner**, khi client/server/hạ tầng hỗ trợ.

Khi ECH được sử dụng:

- Passive sensor có thể thấy một **ClientHelloOuter** với các trường công khai/chuyển tiếp.
- Hostname thật có thể nằm trong **ClientHelloInner đã được mã hóa**.
- Một giá trị SNI nhìn thấy ở outer không chắc là tên dịch vụ cuối cùng.
- Không tự suy ra **ECH đã được chấp nhận** chỉ vì thấy ECH-related extension; implementation/handshake result cần được xác minh.
- Tính khả dụng ECH phụ thuộc **client, DNS/HTTPS records/configuration, server/proxy và môi trường**.

### 11.2. Không thay SNI bằng suy đoán IP→Domain

Khi không thấy tên đích:

- Một public IP/CDN có thể phục vụ nhiều hostnames.
- DNS query của client có thể được cache, gửi tới DoH hoặc là lookup không dùng.
- TLS traffic có thể do proxy tạo cho application khác.
- **HTTP Host** nằm trong encrypted application data khi TLS không bị terminate tại sensor.

Vì thế **“IP thuộc CDN của example.com” không chứng minh user đã truy cập example.com**. Kết luận cần có **resolver/endpoint/proxy logs cùng source identity và time context**.

### 11.3. ALPN, TLS fingerprints và privacy

Các trường như offered ciphers, supported_versions, extensions, groups và đôi khi ALPN có thể giúp **phân loại loại client TLS hoặc thư viện**. Nhưng:

- Browser/OS versions, proxy/antivirus/TLS libraries và **GREASE** làm fingerprint thay đổi.
- Nhiều clients dùng chung thư viện nên có fingerprints tương tự.
- Một actor có thể bắt chước ClientHello hợp lệ.
- ECH có thể giới hạn một số trường quan sát được.
- Fingerprints có thể tăng rủi ro **theo dõi thiết bị/người dùng** nếu giữ lâu và gắn identity.

**JA3/JA4 hoặc fingerprints tương tự chỉ là tín hiệu tương quan**, không phải định danh tuyệt đối của malware, user hay thiết bị. Phải dùng với **tiêu chuẩn quản trị dữ liệu và đánh giá độ tin cậy**.

### 11.4. TLS inspection và trách nhiệm pháp lý

Một corporate proxy có khả năng **TLS termination/inspection** có thể nhìn thấy phần plaintext ở hop mà nó kiểm soát; nhưng đó là một **thay đổi trust boundary lớn**, có rủi ro:

- Nhìn thấy cookies, Authorization headers, PII, nội dung app.
- Certificate/key material của inspection CA cần bảo vệ mạnh.
- Endpoint certificate pinning và ứng dụng đặc biệt có thể không tương thích.
- Proxy có thể trở thành điểm tấn công/chặn/ghi log tập trung.
- Quy định pháp lý, hợp đồng và chính sách quyền riêng tư có thể hạn chế phạm vi.

Mục đích của bài là **phân tích handshake packet trong môi trường được phép**, không khuyến khích phá mã hay triển khai MITM ngoài thẩm quyền. Nếu có khả năng lấy session secrets từ endpoint lab, cần giới hạn chúng vào đúng lab/session và bảo vệ như dữ liệu nhạy cảm.

## 12. TLS qua QUIC/HTTP/3, DTLS và những giao thức dễ bị nhầm

### 12.1. HTTP/3 dùng QUIC chứ không dùng TLS record trên TCP

**QUIC** dùng UDP và tích hợp TLS 1.3 handshake để thiết lập khóa/đàm phán bảo mật, nhưng **handshake TLS được mang trong QUIC CRYPTO frames**, không qua TLS record layer TCP thông thường.

~~~mermaid
flowchart TD
    H12["HTTP/1.1 hoặc HTTP/2"] --> T["TLS records"]
    T --> TCP["TCP"]
    H3["HTTP/3"] --> QUIC["QUIC: streams + packet protection + TLS 1.3 handshake via CRYPTO frames"]
    QUIC --> UDP["UDP"]
    TCP --> IP["IPv4/IPv6"]
    UDP --> IP
~~~

Với capture **UDP/443**:

- Có thể là QUIC/HTTP/3 hoặc giao thức khác, không suy từ port đơn lẻ.
- Dissector QUIC có thể phân tích packet types/connection IDs và TLS handshake ở những **QUIC Initial packets** khi khả năng decode phù hợp.
- QUIC Initial secrets được dẫn xuất theo quy tắc công khai từ connection information, nên **Initial protection không cung cấp confidentiality tương đương với handshake/application secrets ở giai đoạn sau**; các công cụ có thể giải mã Initial để đọc ClientHello.
- Handshake/1-RTT QUIC packet payloads ở những giai đoạn sau cần secrets phù hợp để phân tích chi tiết.
- **Server certificate của QUIC/TLS 1.3 không tự hiện plaintext** chỉ nhờ đọc UDP header hoặc ClientHello Initial.

**Không dùng Wireshark display filter chỉ dành cho tls.record trên TCP để kết luận “không có TLS handshake” trong QUIC trace**. Chọn protocol dissector và fields thích hợp.

### 12.2. DTLS không phải TCP TLS

**Datagram Transport Layer Security (DTLS)** cung cấp bảo vệ TLS-like trên datagram transports như UDP, với cơ chế xử lý mất gói/sắp xếp lại phù hợp. Record/handshake structures và retransmission semantics không đồng nhất với TLS trên TCP.

Ví dụ một kết nối VPN hoặc real-time communication có thể dùng DTLS; khi đó phải xem **DTLS dissector, UDP flow, handshake epoch/sequence và version cụ thể**. Không áp quy tắc **TCP stream reassembly** cho DTLS như thể nó là TLS trên TCP.

### 12.3. STARTTLS và TLS chỉ bắt đầu giữa stream

Một số giao thức như **SMTP, IMAP, LDAP hoặc database protocols** có thể bắt đầu bằng giao thức ứng dụng plaintext rồi thực hiện **STARTTLS/upgrade** trên cùng TCP connection.

Trong PCAP:

~~~text
TCP connection established
Application protocol greeting / negotiation
STARTTLS command and acceptance (nếu giao thức dùng)
TLS ClientHello begins mid-stream
TLS handshake and encrypted application data
~~~

Nếu bắt đầu nhìn tại byte đầu TCP rồi kỳ vọng ngay ClientHello, có thể báo sai “không có TLS”. Cần xác định **application protocol upgrade point** và đặt dissector phù hợp. Không khuyến khích gửi password hoặc dữ liệu thật ở giai đoạn plaintext.

### 12.4. TLS interception và hai chứng thư khác nhau

Trong môi trường proxy/WAF/load balancer hoặc inspection hợp lệ:

- **Client→proxy** có thể negotiate TLS 1.3 với certificate do public CA hoặc enterprise inspection CA cấp.
- **Proxy→origin** có thể negotiate TLS 1.2/TLS 1.3 với certificate khác.
- **ClientHello SNI** ở hai chặng có thể khác.
- **ALPN selection** và ciphers khác do khả năng/proxy policy.
- Source IP tại origin thường là IP proxy, không là client thật.

Không gọi mọi trường hợp “hai phiên TLS” là tấn công. Cần đối chiếu **approved architecture, certificate issuer, proxy identity, network path và security logs**.

## 13. Quy trình đọc TLS PCAP trong Wireshark

### 13.1. Kiểm tra nguồn và phạm vi capture trước khi chọn filter

Mỗi PCAP nên có hồ sơ tối thiểu:

~~~text
Capture source:      client, server, gateway, proxy, Pod hay TAP?
Environment:         lab/staging/production đã được phê duyệt
Capture time:        UTC start/end, clock sync state
Interface:           physical, loopback, VPN, veth, overlay hay tunnel?
Target:              source/destination IP, TCP port, hostname nếu xác minh
Expected protocol:   TLS over TCP, QUIC over UDP, DTLS hoặc STARTTLS
Packet loss:         capture drop rate / offloading / sampling nếu có
Ownership:           người quản lý dữ liệu và retention
~~~

Nếu biết target chỉ qua **hostname**, hãy lưu ý tên có thể phân giải nhiều IP và một proxy có thể sử dụng IP khác với client. Đừng áp filter quá hẹp khiến mất handshake.

### 13.2. Capture filter khác display filter

**Capture filter** dùng ngữ pháp BPF để giới hạn gói được ghi ngay lúc thu; ví dụ:

~~~text
host 192.0.2.20 and tcp port 443
tcp port 8443
udp port 443
~~~

**Display filter** của Wireshark dùng fields của dissector để chọn các frame **đã được ghi**. Ví dụ:

~~~text
tcp.stream == 0
tls
tls.handshake.type == 1
tls.handshake.type == 2
tcp.flags.reset == 1
tcp.analysis.retransmission
~~~

**Không dùng cú pháp display filter ở tcpdump -f** hoặc ngược lại. Capture filter quá hẹp **làm dữ liệu mất từ đầu**, display filter chỉ ẩn những frames khỏi giao diện hiển thị. Wireshark versions/dissectors có thể dùng fields khác nhau, cần kiểm tra trường tồn tại bằng autocomplete/field reference.

### 13.3. Bước đọc 1 — Chọn TCP stream

1. Xác nhận IP nguồn/đích, port, direction và capture time.
2. Lọc **tcp.port == 443** hoặc port ứng dụng thật.
3. Chọn frame SYN của kết nối cần điều tra.
4. Xem **tcp.stream** hoặc nhấp **Follow → TCP Stream**.
5. Trở lại packet details để xem thứ tự SYN, SYN-ACK, ACK và các TLS records.

**tcp.stream là index do Wireshark gán trong một capture/file**, không phải số định danh toàn mạng; không dùng làm key trực tiếp giữa hai PCAP độc lập. Hai file capture ở client/server thường cần ghép theo **5-tuple, timestamps, NAT/proxy mappings và request/connection IDs**.

### 13.4. Bước đọc 2 — Xem ClientHello

Wireshark display filter:

~~~text
tls.handshake.type == 1
~~~

Mở phần **Transport Layer Security → Handshake Protocol: Client Hello**, xem:

- **Handshake Type** và record context.
- **legacy_version** so với **supported_versions**.
- **Cipher Suites** và extension/values được chào.
- **SNI** nếu có và không nằm bên trong ECH.
- **ALPN offered protocols**, groups, key shares, signature schemes.
- **PSK/early data** offer nếu có.
- Source IP, destination, TCP stream, frame time.

Đừng lấy ClientHello cipher list làm kết quả phiên: client có thể đề xuất một thuật toán mà server **không chọn**.

### 13.5. Bước đọc 3 — Xem ServerHello hoặc HRR

~~~text
tls.handshake.type == 2
~~~

Đối chiếu:

1. Phiên bản được chọn so với **supported_versions**.
2. Cipher suite được chọn có trong danh sách đề xuất không.
3. Group/key share selection theo TLS 1.3.
4. Có **HelloRetryRequest** không.
5. ServerHello có thuộc **cùng TCP stream** và đến từ đúng peer không.
6. Thời gian từ ClientHello tới ServerHello.

Nếu không thấy ServerHello, đừng chuyển ngay sang đọc certificate: lúc này cần xem **TCP drops, retransmissions, firewall/proxy/server logs và capture coverage**.

### 13.6. Bước đọc 4 — Xác định TLS 1.2 hay 1.3

Làm theo thứ tự:

- Đọc **ServerHello selected version** theo semantics của phiên bản.
- Với TLS 1.3 xem **supported_versions** extension, không chỉ legacy_version.
- Kiểm tra **sau ServerHello** các messages/records có mã hóa hay không.
- Nhớ TLS 1.3 có thể có **dummy ChangeCipherSpec**, không đánh đồng với TLS 1.2.
- Nếu một proxy terminates TLS, phân tích **đúng hop** thay vì tổng hợp hai TLS sessions.

### 13.7. Bước đọc 5 — Xác định bằng chứng xác thực

Nếu là **TLS 1.2 full handshake**, xem Certificate message nếu capture có đủ; nếu là **TLS 1.3**, chứng thư nằm sau mã hóa. Không kết luận certificate valid chỉ vì Wireshark parse được subject/SAN.

Để chứng minh chain/hostname validation thực sự thành công, cần **TLS endpoint/library logs hoặc test TLS do bạn sở hữu** với đúng truststore, hostname và verify flags. Handshake progression chỉ cung cấp bằng chứng hỗ trợ, không thay kiểm tra policy của client.

### 13.8. Bước đọc 6 — Theo dõi phần cuối phiên

Theo dõi:

- TLS 1.2 **CCS/Finished** và encrypted records.
- TLS 1.3 **encrypted handshake flight** (outer Application Data).
- TCP ACK, FIN/RST và retransmission.
- Giao thức ứng dụng sau handshake theo khả năng giải mã/log.

Với TLS 1.3 không có secrets, không thể xác định một encrypted record chính xác là **Finished**, **Certificate** hay **HTTP application data** chỉ từ outer content type.

### 13.9. Bước đọc 7 — Kiểm tra Expert Information một cách phê phán

Wireshark có thể gắn **TCP Previous segment not captured**, **Retransmission**, **Out-of-order**, **Malformed packet** hoặc **TLS Alert**. Nhưng:

- “Malformed” có thể do bắt giữa stream/offloading/parser không hiểu phiên bản.
- Retransmission là **TCP phenomenon**, không tự là TLS negotiation failure.
- Packet loss tại sensor khác network packet loss thật.
- “Encrypted Alert” không có plaintext description khi không có secrets.

Đối chiếu **TCP sequence/ACK, capture loss, TLS server logs và kết quả ứng dụng**.

## 14. Dùng tshark, tcpdump và OpenSSL để kiểm tra có cấu trúc

### 14.1. Tạo PCAP hẹp trong môi trường được phép

Ví dụ hệ thống Linux có **tcpdump**, với **đích lab thực** thay cho IP ví dụ:

~~~bash
# Chỉ chạy trên interface và đích lab được cấp quyền.
# Thay eth0 và 192.0.2.20 bằng interface / IP lab thật.
# -c 200 giới hạn tối đa 200 packets; -s 0 ghi đủ snaplen.
sudo tcpdump -i eth0 -nn -s 0 -c 200 \
  -w tls_lab.pcap \
  'host 192.0.2.20 and tcp port 443'
~~~

Trong ví dụ, **192.0.2.20 là địa chỉ tài liệu**, không có ý định capture Internet thật. Nếu thử TLS qua **loopback**, hãy dùng interface loopback như **lo** trên Linux và port của server lab. Đừng để capture hoạt động vô hạn trên production vì dễ thu dữ liệu nhạy cảm.

Các tùy chọn chính:

| Tùy chọn | Vai trò |
| --- | --- |
| **-i** | Chọn interface phải có traffic |
| **-nn** | Không phân giải tên DNS/service ports trong output |
| **-s 0** | Không cắt payload do snaplen quá nhỏ theo công cụ |
| **-c 200** | Giới hạn số packet được ghi |
| **-w** | Ghi PCAP để phân tích sau |

Giới hạn số packets không bảo đảm chỉ một TLS handshake nếu host có nhiều connections; cần kiểm tra các flows thực tế sau thu thập.

### 14.2. Đọc PCAP offline với tshark

~~~bash
# Tóm tắt ClientHello trong file PCAP đã được phép thu.
tshark -r tls_lab.pcap \
  -Y 'tls.handshake.type == 1' \
  -T fields \
  -e frame.time_epoch \
  -e ip.src -e ip.dst \
  -e tcp.stream \
  -e tls.handshake.extensions_server_name
~~~

Lưu ý fields và naming có thể thay đổi theo **Wireshark/tshark version**. Đặc biệt với IPv6, **ip.src/ip.dst** không chứa địa chỉ **ipv6.src/ipv6.dst**; cần bổ sung fields tương ứng.

Ví dụ ServerHello:

~~~bash
tshark -r tls_lab.pcap \
  -Y 'tls.handshake.type == 2' \
  -T fields \
  -e frame.number \
  -e frame.time_epoch \
  -e tcp.stream
~~~

Ví dụ đọc những TCP retransmissions:

~~~bash
tshark -r tls_lab.pcap \
  -Y 'tcp.analysis.retransmission' \
  -T fields \
  -e frame.number -e tcp.stream \
  -e ip.src -e ip.dst
~~~

**Một bộ lọc không trả kết quả không đồng nghĩa không có handshake**: có thể capture thiếu bytes đầu, sai port/dissector, TLS đang chạy qua QUIC/DTLS/STARTTLS, hoặc không có traffic tại interface đã chọn.

### 14.3. Kiểm tra hỗ trợ field theo phiên bản

Một cách tự kiểm tra giao diện tshark:

~~~bash
# Xem version của dissector.
tshark --version

# Liệt kê các protocol fields rồi lọc theo TLS theo công cụ shell lab.
tshark -G fields | grep -E 'tls.handshake|tls.record' | head -n 30
~~~

Đây là thao tác **đọc danh sách fields**, không gửi traffic. Nếu hệ thống dùng Windows PowerShell, bộ lọc shell **grep/head** cần thay bằng công cụ tương đương; không vì thiếu grep mà kết luận tshark không hỗ trợ TLS.

### 14.4. Kiểm tra negotiated TLS bằng OpenSSL client lab

Khi có **dịch vụ HTTPS lab thật** với hostname/certificate được phép:

~~~bash
# Thay api.lab.example:443 bằng dịch vụ lab bạn kiểm soát.
# -verify_return_error yêu cầu dừng khi xác minh chứng thư thất bại.
openssl s_client \
  -connect api.lab.example:443 \
  -servername api.lab.example \
  -verify_hostname api.lab.example \
  -verify_return_error \
  -tls1_3 \
  -alpn h2,http/1.1 \
  -brief < /dev/null
~~~

Kết quả có thể cung cấp **protocol version, cipher, certificate verification, ALPN** theo khả năng của OpenSSL phiên bản đang chạy. **-tls1_3** là lựa chọn để kiểm thử **TLS 1.3-only** trong lab, không phải cách cấu hình mọi production client.

Nếu dùng private CA, cần cung cấp **trust anchor phù hợp** bằng **-CAfile** hoặc cấu hình trust đúng. Đừng thêm **-verify_quiet** hoặc **-k** theo thói quen rồi coi một phiên không xác minh chứng thư là thành công. Với OpenSSL s_client, việc bật một số tùy chọn không có nghĩa tất cả chính sách ứng dụng/browser đã được mô phỏng.

### 14.5. Phân biệt CLI handshake test và ứng dụng thật

Một lần OpenSSL s_client thành công chứng minh **CLI có thể thương lượng TLS và xác minh theo flags/truststore được cấu hình**. Nó **không chứng minh**:

- JVM/Android/browser có cùng truststore, cipher policy hoặc SNI.
- Reverse proxy xử lý đúng **HTTP Host/:authority**.
- Backend API cho phép user/tenant.
- Service đi được qua mTLS, SOCKS/HTTP proxy hoặc ZTNA tunnel riêng.
- Các clients cũ đều hỗ trợ TLS 1.3.
- Dữ liệu được chấp nhận khi **ALPN h2** đã được chào nhưng ứng dụng dùng giao thức khác.

Khi phân tích production incident, hãy lấy **client/application-specific logs** để bổ sung kết quả thử độc lập.

## 15. Lab tự chứa: TLS 1.2 và TLS 1.3 trên loopback

### 15.1. Mục tiêu và giới hạn

Lab này tạo một **TLS server trên 127.0.0.1** và dùng một **client của chính bạn** để tạo handshake. Không có yêu cầu gửi traffic tới Internet. Chỉ nên dùng trên máy lab, với OpenSSL và tcpdump/Wireshark được phép sử dụng. Bạn sẽ tạo **private key thử nghiệm**: phải bảo vệ file trong quá trình lab và hủy theo chính sách sau khi kết thúc.

Không sử dụng private key lab này cho production, không đưa file key hoặc decryption secrets vào chat, issue tracker hay repo.

### 15.2. Sinh self-signed test certificate

Trong **thư mục lab tách biệt**, với OpenSSL hỗ trợ tùy chọn **-addext**:

~~~bash
openssl req -x509 -newkey rsa:2048 -sha256 -days 1 \
  -nodes -keyout lab.key -out lab.crt \
  -subj '/CN=localhost' \
  -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1'
~~~

Đây là **self-signed certificate dùng riêng cho lab**. Không đưa nó vào trust store của toàn OS hoặc dùng như CA nội bộ chính thức. Client lab có thể dùng **-CAfile lab.crt** để chủ động tin cert này trong lần test; đó là trust cấu hình có phạm vi, không phải chứng minh nó được public CA phát hành.

### 15.3. Terminal A — Chạy server TLS 1.3

~~~bash
# Chỉ bind loopback; không mở service ra mạng ngoài.
openssl s_server \
  -accept 127.0.0.1:8443 \
  -cert lab.crt -key lab.key \
  -tls1_3 -www
~~~

**-www** phục vụ một trang trả lời thử của OpenSSL server. Chỉ dùng session ngắn trong lab. Nếu bản OpenSSL không hỗ trợ cú pháp bind/flag này, xem **openssl s_server -help** của chính phiên bản đang cài.

### 15.4. Terminal B — Capture traffic loopback

~~~bash
# Trên Linux lab, dùng loopback interface lo.
# Các OS khác có tên/cơ chế loopback capture riêng.
sudo tcpdump -i lo -nn -s 0 -c 100 \
  -w tls13_loopback.pcap \
  'tcp port 8443 and host 127.0.0.1'
~~~

Lệnh sẽ dừng sau tối đa **100 packets**; nếu ít gói hơn, có thể dừng bằng Ctrl+C sau khi đã hoàn tất phiên. Không kéo dài capture để “đủ số gói” bằng cách tạo traffic ngoài mục đích.

### 15.5. Terminal C — Kết nối client có xác minh hostname

~~~bash
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername localhost \
  -verify_hostname localhost \
  -CAfile lab.crt \
  -verify_return_error \
  -tls1_3 \
  -brief
~~~

Chỉ khi handshake thành công mới thử một yêu cầu HTTP lab nhỏ, theo hướng dẫn phiên bản OpenSSL bạn dùng; có thể mở kết nối khác bằng công cụ HTTPS test phù hợp. Với s_client, nếu chỉ kết nối rồi thoát ngay, **không có HTTP request/response** nhưng vẫn có TLS handshake để phân tích.

### 15.6. Kỳ vọng trong Wireshark

| Điểm đọc | TLS 1.3 loopback |
| --- | --- |
| TCP SYN/SYN-ACK/ACK | Có trong capture đầy đủ của TCP connection |
| ClientHello | Có; có thể đọc các đề xuất |
| ServerHello | Có; selected TLS 1.3/AEAD suite |
| Server Certificate plaintext | **Không** dưới dạng TLS 1.2 Certificate thông thường |
| EncryptedExtensions/Certificate/Finished | Outer encrypted records, cần secrets phù hợp để đọc |
| Server CA trust | Được client lab cấp qua **-CAfile lab.crt**, không nhìn thấy từ PCAP |
| TLS Alert khi thoát | Tùy đường đóng/phiên bản; không tự đoán alert code |

### 15.7. Lặp lại có chủ đích với TLS 1.2

Đóng server lab, chạy lại cùng cổng với **-tls1_2** thay cho **-tls1_3**; client cũng chọn **-tls1_2**. Capture ra file **riêng** để tránh nhầm TCP streams.

So sánh:

- Server Certificate message có thể đọc từ TLS 1.2 full handshake.
- TLS 1.2 full handshake có các message như **ServerKeyExchange/ClientKeyExchange/ServerHelloDone** tùy cipher suite.
- ChangeCipherSpec/Finished được quan sát khác với TLS 1.3.
- Đo thời gian ClientHello–ServerHello–Finished và TCP latency cùng điều kiện lab.

Đây là **so sánh cấu trúc**, không phải bài benchmark hiệu năng: loopback RTT quá thấp và ảnh hưởng CPU/scheduling rất khác mạng thực.

### 15.8. Không đưa cipher suite cũ vào lab production

Không bật **SSLv2/SSLv3/TLS 1.0/TLS 1.1, cipher suites yếu hoặc bỏ verification** trên hệ thống dùng thật chỉ để “cho thấy khác biệt”. Nếu cần nghiên cứu legacy trong lab an toàn, chỉ thực hiện trên môi trường cô lập theo yêu cầu tổ chức và tránh tạo listener public.

## 16. Khi cần đọc encrypted handshake: Session secrets trong lab được phép

### 16.1. Mã hóa TLS được thiết kế để ngăn passive observer đọc nội dung

Một packet capture thông thường **không chứa bí mật phiên**. Với TLS 1.3 và TLS 1.2 dùng forward-secret key exchange, chỉ có **certificate public key và network packets** không đủ để giải mã data. Điều này là **tính chất bảo mật mong muốn**, không phải lỗi của Wireshark.

Nếu bạn cần nghiên cứu chi tiết TLS 1.3 EncryptedExtensions/Certificate/Finished trong **phiên do chính mình tạo**:

- Ưu tiên **TLS endpoint logs** nếu chỉ cần biết protocol, cipher, certificate/trust errors.
- Chỉ sử dụng **TLS key log** do endpoint thử nghiệm xuất ra trong môi trường được phép, không tìm cách lấy secrets từ người khác.
- Giữ file secret ở nơi riêng, giới hạn quyền, thời gian lưu và không gắn vào báo cáo được chia sẻ.
- Không dùng server private key thực tế chỉ vì muốn “mở khóa PCAP”.

### 16.2. SSLKEYLOGFILE và key log trong lab

Một số TLS client (ví dụ phần mềm dùng TLS library hỗ trợ cơ chế key logging) có thể xuất **NSS key log format** qua cấu hình được phép. Cách bật khác nhau theo ứng dụng/OS/runtime và version; không phải mọi ứng dụng đều tôn trọng biến môi trường **SSLKEYLOGFILE**.

Với OpenSSL **s_client** phiên bản có hỗ trợ, có thể dùng tùy chọn **-keylogfile** trong phiên thử loopback:

~~~bash
# Chỉ dùng với client/server và PCAP thử nghiệm do bạn kiểm soát.
# lab.keys là file chứa TLS traffic secrets, phải được bảo vệ.
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername localhost \
  -verify_hostname localhost \
  -CAfile lab.crt \
  -verify_return_error \
  -tls1_3 \
  -keylogfile lab.keys \
  -brief
~~~

**Lệnh này tạo secret-bearing file chỉ dành cho lab.** Nếu bản OpenSSL không có tùy chọn, xem help hoặc chọn một TLS client khác do bạn kiểm soát. Không bật key logging hàng loạt trên endpoint production/nhân viên.

### 16.3. Wireshark TLS key log workflow

Trong Wireshark, ở phần preferences của **TLS protocol**, chọn file chứa **(Pre)-Master-Secret log filename** hoặc tên tương đương của phiên bản đang sử dụng. Sau đó mở **đúng PCAP của phiên được ghi secrets**.

Khi secrets khớp với đúng phiên, Wireshark có thể:

- Giải mã một số encrypted TLS records và hiển thị handshake messages đã bị che.
- Cho thấy Certificate/EncryptedExtensions/Finished của TLS 1.3 khi supported.
- Phân tích application data nếu dissector có protocol keys và support thích hợp.

Không thành công có thể do **khác phiên, key log trống, secret type không khớp, capture thiếu handshake, unsupported algorithm hoặc dissector version**. Đừng đổi TLS sang plaintext hoặc tắt xác minh certificate để “sửa” việc Wireshark không đọc được.

### 16.4. Cẩn thận với PCAPNG Decryption Secrets Block

Một số công cụ/định dạng có thể **đính kèm decryption secrets vào capture** hoặc đưa bí mật vào file xuất. Vì vậy:

1. Xem file có chứa session secrets hay không trước khi chia sẻ.
2. Không tải PCAP/PCAPNG có secrets lên nơi không được cấp quyền.
3. Lưu **phiên bản đã làm sạch/redacted** nếu báo cáo chỉ cần metadata/diagrams.
4. Xóa hoặc hết hạn file secrets theo chính sách lab/incident.
5. Không chuyển một **lab private key** thành credential dùng lại cho dịch vụ khác.

### 16.5. Private key của server có giải mã mọi phiên không?

**Không.** Các cơ chế **(EC)DHE** tạo forward secrecy có đặc tính không thể giải mã traffic đã ghi chỉ với **private key chứng thư server**. TLS 1.3 yêu cầu key establishment theo các cơ chế hỗ trợ forward secrecy trong full handshake thông thường. Những trường hợp TLS 1.2 **RSA key exchange cũ** có thuộc tính khác, nhưng **không nên bật lại cơ chế lỗi thời chỉ để xem plaintext**.

Muốn phân tích một session production, ưu tiên **server/client/proxy TLS logs, metrics, request tracing và endpoint diagnostics được phê duyệt** thay vì tìm cách lấy key material.

### 16.6. Giới hạn của key logs

Ngay cả khi Wireshark giải mã thành công:

- Một ứng dụng có thể gửi dữ liệu nhị phân/gRPC/WebSocket, không phải HTTP text.
- Traffic qua proxy có **nhiều TLS sessions**, cần đúng secrets từng hop.
- Key log phía client có thể không có secrets của **proxy→origin session**.
- Một capture giữa stream có thể thiếu context để phân tích.
- **Application authentication/authorization** không được chứng minh chỉ vì có nội dung giải mã.

**Giải mã để hiểu handshake** là hoạt động kỹ thuật giới hạn trong hệ thống được cấp phép, không phải mục tiêu mặc định của mọi chương trình network telemetry.

## 17. Đo độ trễ TLS handshake từ packet timestamps

### 17.1. Những thành phần của thời gian kết nối

Một client request qua HTTPS có thể tiêu tốn thời gian:

~~~text
DNS lookup / cache                      (không phải TLS)
TCP three-way handshake                 (không phải TLS)
TLS ClientHello → ServerHello           (một phần TLS flight)
TLS encrypted handshake exchanges       (TLS)
Certificate chain/path validation       (client CPU / crypto / có thể fetch phụ)
HTTP request → response                 (application + network)
~~~

Không lấy **time-to-first-byte của HTTP** rồi gọi là TLS handshake time. TTFB có thể gồm DNS, TCP, TLS, proxy, authentication, application processing và server/network queue.

### 17.2. Các timestamp cần lấy

| Ký hiệu | Sự kiện | Ý nghĩa |
| --- | --- | --- |
| **t0** | Client TCP SYN | Bắt đầu thử kết nối TCP |
| **t1** | Client ACK hoàn tất TCP establishment theo điểm đo | TCP setup hoàn tất ở bên quan sát |
| **t2** | ClientHello rời client | Bắt đầu TLS flight |
| **t3** | ServerHello tới client | First server TLS response |
| **t4** | Server's final handshake flight đến client (khi nhìn được) | Mốc handshake từ server |
| **t5** | Client Finished được gửi (khi nhìn được) | Bước client xác nhận handshake |
| **t6** | First application request được gửi (khi xác minh được) | Chỉ chứng minh app bắt đầu dùng kênh |

Với **TLS 1.3 passive capture không có secrets**, **t4/t5** có thể không chỉ được chính xác message type vì outer records đã mã hóa. Khi đó dùng **endpoint TLS event timestamps** nếu cần đo handshake hoàn tất chính xác.

### 17.3. Chênh lệch thời gian đơn giản

\[
\Delta_{\text{serverhello}} = t_3 - t_2
\]

Khoảng này gồm **network RTT thành phần, xử lý server và các trung gian** giữa ClientHello/ServerHello. Nó không phải toàn bộ TLS handshake time, và không thể phân rã thành pure network delay chỉ từ một PCAP tại client.

Ví dụ dữ liệu giả lập:

~~~text
t0  12:00:00.000  TCP SYN
t1  12:00:00.042  TCP established (client observation)
t2  12:00:00.043  TLS ClientHello
t3  12:00:00.088  TLS ServerHello
Δ   45 milliseconds from ClientHello to ServerHello
~~~

**45 ms** chỉ là khoảng đo tại capture point của ví dụ. Không dùng làm SLO chung cho mọi TLS connection; khoảng địa lý, client, proxy, TLS phiên bản, server CPU và handshake mode khác nhau.

### 17.4. Network jitter và packet loss

Một ClientHello có thể xuất hiện vài lần do **TCP retransmission**, hoặc TCP handshake cần nhiều SYN retries. Khi tính latency:

- Xác định **first unique ClientHello bytes** trong một TCP stream.
- Không tính retransmitted packet thành handshake mới.
- Xem **TCP RTT estimates, ACK timing, out-of-order và capture loss**.
- Nếu server response có trong **server PCAP** nhưng không tới client, điều tra mạng trung gian.
- Nếu traffic qua proxy, đo **cả client→proxy và proxy→origin legs**.

### 17.5. Handshake hoàn thành không đồng nghĩa app khỏe

TLS có thể thành công, nhưng HTTP trả:

- **401/403** do authentication/authorization.
- **429** do quota/rate limit.
- **502/503/504** do upstream lỗi hoặc timeout.
- **404** do route/Host không khớp.

Vì vậy nên ghép **TLS negotiation logs** với **proxy/application status/traces** thay vì gán mọi 5xx cho certificate.

## 18. Chẩn đoán từng mẫu lỗi bắt tay thường gặp

### 18.1. TCP SYN đi nhưng không có SYN-ACK

**Chưa có TLS handshake.** Khả năng:

- Host/port không reachable, route/NACL/SG/firewall drop.
- Server listener không mở hoặc service không ready.
- Đích thuộc IP/port sai do DNS/NAT.
- Client capture không thấy response do route bất đối xứng.

**Bằng chứng:** route, SYN retransmissions, firewall verdict, server listener logs, endpoint state. **Không bắt đầu từ certificate renewal**.

### 18.2. TCP kết nối được nhưng không có ClientHello

Khả năng:

- Client đang chờ application greeting/STARTTLS.
- Client connect rồi idle hoặc tự đóng.
- Traffic không phải TLS dù port giống HTTPS.
- Capture thiếu bytes đầu, dissector nhận nhầm.
- Một proxy/tunnel đang được thử thay vì kết nối app.

**Bằng chứng:** TCP payload và application protocol, client logs, SNI/proxy settings. Đừng ép decode as TLS cho dữ liệu không phải TLS rồi suy ra packet malformed.

### 18.3. ClientHello đi, không có ServerHello

Các giả thuyết:

| Tầng | Điều cần xem |
| --- | --- |
| **Network** | TCP retransmissions, RST/FIN, firewall/IDS/IPS drop, asymmetric routing |
| **Server** | Listener, process crash, overload, TLS config/version/ciphers |
| **Proxy/WAF** | SNI route, ACL, max connections, timeout |
| **Protocol** | ClientHello malformed/truncated, unsupported extension, HRR/fragmentation |
| **Capture quality** | Missing packets/incorrect interface/one-way mirror |

Nếu một **plaintext Alert** xuất hiện trước ServerHello, phân tích **alert description**, nhưng vẫn cần server logs để biết nguyên nhân gốc. Nếu chỉ có TCP RST, không gán thành **handshake_failure** mặc định.

### 18.4. ServerHello có, nhưng connection reset ngay sau

Khả năng:

- Client từ chối certificate/trust policy hoặc algorithm (bằng chứng thường ở client logs).
- Server gửi encrypted handshake lỗi/timeout.
- Middlebox xử lý TLS records không đúng hoặc chặn policy.
- MTU/PMTUD, fragmentation, TCP loss ảnh hưởng flight kích thước lớn.
- Client/server đóng do authentication/mTLS failure.

Kiểm tra **TCP sequence progression, packet sizes, retransmissions, client/server library errors và capture ở hai đầu**.

Với TLS 1.3, do certificate ẩn sau ServerHello, **chỉ nhìn thấy encrypted records + RST không đủ chẩn đoán certificate mismatch**.

### 18.5. TLS 1.2 nhìn thấy Certificate, sau đó client đóng

Có thể là:

- Hostname/SAN mismatch.
- Chain thiếu intermediate hoặc CA không được tin.
- Chứng thư hết hạn/chưa hiệu lực.
- EKU/signature algorithm không phù hợp với policy.
- Revocation/status/certificate constraints theo client.
- Một lỗi khác không liên quan certificate.

**Thấy Certificate trước khi client đóng chỉ là tương quan thời gian.** Cần **verify result từ client** để kết luận lỗi chứng thư.

### 18.6. TLS 1.3 client/server có cipher list nhưng handshake_failure

Không nên dừng ở cipher suite. TLS 1.3 còn có:

- supported_versions compatibility.
- supported_groups/key_share selection.
- signature_algorithms và certificate/key compatibility.
- SNI routing/cert selection.
- PSK identities/binders, HRR behavior.
- Policy mTLS, server/client authentication.
- Middlebox interoperability.

Một cipher suite trùng không bảo đảm **mọi tham số còn lại đều hợp lệ**.

### 18.7. TLS handshake thành công, browser báo certificate warning

Có thể handshake đã hoàn tất ở mức mật mã nhưng browser **không chấp nhận danh tính theo policy**, hoặc một hop/phiên khác được quan sát. Không dùng packet completion để bác bỏ lỗi browser. Cần xem **hostname, SAN, CA store, HSTS/trust policies, browser certificate details** và ứng dụng có bị proxy inspection không.

### 18.8. mTLS hoạt động với máy A nhưng thất bại trên máy B

Đối chiếu:

- Client certificate issuance/expiry/identity mapping.
- Private key availability và client certificate selection.
- Trusted client CAs trên server và client chain.
- Signature schemes/TLS policy.
- TLS hop, proxy client cert forwarding/termination.
- Runtime truststore/keystore khác nhau.

Không dùng thử bằng cách **vô hiệu hóa client certificate requirement** trên production; nếu cần isolate vấn đề thì test bằng cấu hình riêng trong lab.

### 18.9. Handshake chỉ lỗi khi qua firewall/proxy

So sánh hai tuyến **có kiểm soát và được phép**:

~~~text
Client -> server direct through permitted test path
Client -> approved proxy -> server
~~~

Đối chiếu SNI, ALPN, client certificate behavior, TLS version, proxy termination, firewall logs, TCP MSS/MTU, fragment sizing và backend certificate trust. **Không tự ý đi vòng security gateway production** để làm test; cần change/owner approval và lab route rõ ràng.

### 18.10. Lỗi chỉ xảy ra ở một số regions/nodes

Có thể:

- Load balancer chọn backend với certificate hoặc TLS config cũ.
- Truststores không đồng bộ.
- Proxy/ingress regional versions khác.
- CNI/network path/MTU khác.
- Anycast/CDN phục vụ các IP khác.

Gắn **destination IP, SNI, backend identity, region, pod/node, deployment revision** vào events. Một PCAP từ một node không bảo đảm toàn bộ service đã đúng.

### 18.11. TLS 1.3 capture “không có Certificate” nhưng ứng dụng hoạt động

Đây thường là **hành vi quan sát bình thường**: server cert nằm trong encrypted handshake hoặc phiên được resume theo PSK. Kiểm tra actual protocol selection, endpoint TLS logs và session mode; đừng coi đây là dấu hiệu traffic không có certificate/trust validation.

## 19. Cây quyết định điều tra TLS handshake packet

~~~mermaid
flowchart TD
    A["Ứng dụng không thiết lập được phiên bảo vệ"] --> B{"Đã bắt đúng flow/đường mạng?"}
    B -->|Không chắc| C["Capture point, 5-tuple, TCP vs QUIC, time/flow logs"]
    B -->|Có| D{"TCP established / transport ready?"}
    D -->|Không| E["Routing, firewall, SYN/ACK, listener, NAT/MTU"]
    D -->|Có| F{"Có ClientHello / TLS Initial?"}
    F -->|Không| G["STARTTLS, proxy protocol, wrong port, capture gap"]
    F -->|Có| H{"Có ServerHello / retry / alert?"}
    H -->|Không| I["TCP drops/RST, proxy routing, server logs, policy"]
    H -->|Có| J{"Phiên đã negotiate / hoàn tất?"}
    J -->|Không| K["TLS version/ciphers, key_share, HRR, cert/mTLS, endpoint errors"]
    J -->|Có| L{"Application request có thành công?"}
    L -->|Không| M["ALPN, HTTP route, app auth, backend 4xx/5xx"]
    L -->|Có| N["Ghi nhận negotiated state và baseline"]
    C --> O["Correlate evidence, scope và owner"]
    E --> O
    G --> O
    I --> O
    K --> O
    M --> O
    N --> O
~~~

**Cây quyết định này không tự giải mã encrypted TLS messages.** Với TLS 1.3 sau ServerHello, một số điều kiện phải xác định qua **client/server/proxy TLS logs**, chứ không chỉ nhìn màu Wireshark.

### 19.1. Những kết luận có thể viết từ một capture

| Bằng chứng thực | Cách diễn đạt được hỗ trợ | Cách diễn đạt quá mức |
| --- | --- | --- |
| TCP SYN retransmit, không thấy SYN-ACK tại client | “Client chưa nhận TCP handshake response trong capture này.” | “Server chắc chắn down.” |
| ClientHello có SNI X | “Client đề xuất SNI X trên đường đo.” | “User đã gửi HTTP request tới website X.” |
| ServerHello TLS 1.3 | “Server chọn TLS 1.3 trong kết nối này.” | “Certificate đã được client tin.” |
| TLS 1.2 Certificate visible | “Server gửi certificate chain có SAN/issuer như quan sát.” | “Mọi client đều tin chain này.” |
| TLS 1.3 outer Application Data | “Có encrypted TLS records sau ServerHello.” | “Đây chắc chắn là HTTP POST và không có lỗi handshake.” |
| TCP RST sau handshake flight | “Một bên reset connection sau flight đó.” | “Lỗi chắc chắn do expired cert.” |
| HTTP 403 từ app log | “Ứng dụng/gateway đã từ chối operation theo log.” | “TLS không bắt tay thành công.” |

### 19.2. Tạo timeline đầy đủ thay vì chụp một screenshot

Một incident report hiệu quả nên có:

~~~text
UTC timestamp | source/destination/hop | packet/TLS event
Observed facts | source of evidence | confidence
TLS mode: 1.2 full / 1.3 / resumed / QUIC / unknown
Selected version and cipher if visible
SNI and ALPN: offered vs selected, visibility constraints
Certificate/trust verification: endpoint result or unknown
TCP: loss/retransmission/RST/FIN
Application: success/error code and server-side logs if available
Unanswered questions and next safe verification step
~~~

Không cần đưa raw secrets, token hay toàn bộ decrypted HTTP body vào case nếu metadata và TLS logs đã đủ.

## 20. Case study: Ba sự cố nhìn gần giống nhau nhưng khác tầng

### 20.1. Case A — “Website timeout” vì SYN không vượt firewall

**Tình huống giả lập:** client ở mạng đối tác gọi **https://admin.lab.example**, nhưng timeout.

~~~text
13:00:00.000 Client -> 192.0.2.20 TCP SYN
13:00:01.000 Client -> 192.0.2.20 TCP SYN retransmission
13:00:03.000 Client -> 192.0.2.20 TCP SYN retransmission
13:00:03.010 Firewall log: egress rule DENY TCP/443
No SYN-ACK and no TLS ClientHello observed at client
~~~

**Diễn giải:** DNS hoặc IP lookup trước đó có thể thành công nhưng TCP chưa established; **TLS certificate chưa có cơ hội được trình**. Kiểm tra network policy và quyền thực của client theo approved path. Không “gia hạn certificate” để chữa lỗi này.

**Cách xử lý:** xác minh client có được cấp quyền tới ứng dụng không, chọn đường VPN/ZTNA/ACL phù hợp và **thử lại với host/port lab được ủy quyền**. Giữ firewall audit cho thay đổi.

### 20.2. Case B — TLS handshake negotiation thành công, cert validation lỗi

**Tình huống giả lập:** client đã nhận ServerHello TLS 1.2 và Certificate, sau đó application báo **hostname mismatch**.

~~~text
13:10:00.000 TCP established
13:10:00.005 ClientHello: SNI api.lab.example
13:10:00.038 ServerHello: TLS 1.2 selected
13:10:00.039 Certificate: SAN = DNS:backend.lab.example
13:10:00.050 Client-side TLS library: hostname mismatch for api.lab.example
13:10:00.051 TCP connection closed
~~~

**Diễn giải:** certificate trong ví dụ không có SAN khớp hostname được client xác minh, và **client library log** xác nhận lỗi. Chỉ thấy khác SNI/SAN chưa đủ trong mọi kiến trúc, vì có thể policy/use-case chỉ định verification name khác; nhưng ở đây có evidence trực tiếp của client.

**Cách xử lý:** sửa **certificate/SNI virtual-host routing hoặc requested hostname** theo ownership, không tắt hostname verification hoặc bật trust-all.

### 20.3. Case C — TLS 1.3 “chỉ có Application Data” nhưng backend 403

**Tình huống giả lập:** user gọi web app qua identity-aware proxy.

~~~text
13:20:00.000 TCP established
13:20:00.006 ClientHello: TLS 1.3 offered, SNI portal.lab.example
13:20:00.041 ServerHello: TLS 1.3 selected
13:20:00.043 ... outer TLS Application Data records ...
13:20:00.091 Client HTTP stack: 403 Forbidden
13:20:00.093 Proxy app log: user has no permission for /admin
~~~

**Diễn giải:** PCAP không tự cho biết Certificate/Finished/HTTP contents do mã hóa; tuy nhiên **client HTTP stack nhận 403 hợp lệ và proxy log** cho biết request bị từ chối ở authorization layer. **Không thể sửa bằng thay cipher suite hoặc mở firewall toàn mạng**.

**Cách xử lý:** kiểm tra application entitlement, route authorization và identity propagation; TLS có thể đã hoàn tất theo ứng dụng nhưng backend policy vẫn deny. Ghi rõ nguồn log dùng chứng minh thay vì giả vờ PCAP đọc được 403 bên trong TLS.

### 20.4. Case D — mTLS upstream lỗi dù public HTTPS hoạt động

**Tình huống giả lập:** client browser tới ingress thành công, nhưng ingress gọi private backend qua mTLS thất bại.

~~~text
Client -> Ingress:
  TLS 1.3 handshake completed
  HTTP request accepted by ingress

Ingress -> Backend:
  New TCP and TLS session
  Backend requires client certificate
  Ingress TLS log: no configured client certificate for backend identity
  Backend TLS log: client certificate required

Client receives:
  HTTP 502 from ingress
~~~

**Diễn giải:** đây là **hai TLS sessions**. Browser certificate và SNI chỉ liên quan phía client→ingress; lỗi nằm ở **ingress→backend mTLS client identity**. Một PCAP từ browser không giải thích được đầy đủ upstream handshake.

**Cách xử lý:** kiểm tra backend trusted client CA, ingress mTLS key/cert configuration, workload identity mappings và correct route. Không bỏ mTLS requirement để “sửa nhanh” trên production.

### 20.5. Case E — HRR và thêm một lượt trao đổi

**Tình huống giả lập:** ClientHello đầu chỉ gửi key share không phù hợp với chính sách server; server yêu cầu thử lại.

~~~text
13:30:00.000  ClientHello #1 (supported groups list, offered key share)
13:30:00.030  HelloRetryRequest
13:30:00.031  ClientHello #2 with requested key share
13:30:00.062  ServerHello
13:30:00.090  Encrypted handshake continues
~~~

**Diễn giải:** HRR theo chuẩn không tự là lỗi bảo mật; nhưng có thể làm tăng thời gian negotiation. Nếu xảy ra thường xuyên, kiểm tra offered groups, server preference và client compatibility, không cho rằng client tạo hai handshake độc lập.

## 21. TLS handshake metadata trong IDS/IPS, proxy và SIEM

### 21.1. Tại sao packet capture thường không phải nguồn monitoring duy nhất?

PCAP giữ dữ liệu giàu chi tiết nhưng:

- Tốn storage và chi phí xử lý ở tốc độ cao.
- Có thể chứa dữ liệu/metadata nhạy cảm.
- Dễ mất packets hoặc bỏ lỡ link/route.
- Không luôn nhìn thấy encrypted handshake/certificate.
- Không có process/workload/user identity đầy đủ.

Trong vận hành, **flow telemetry + TLS handshake metadata + endpoint/server logs + PCAP ngắn theo sự cố** thường thực tế hơn ghi mọi packet vô hạn.

### 21.2. Metadata nên thu thập

| Trường | Lợi ích | Rủi ro suy diễn |
| --- | --- | --- |
| **event_time_utc** | Correlation/timeouts | Clock skew ảnh hưởng độ chính xác |
| **src/dst IP, port, protocol** | Xác định network connection | NAT/proxy che workload gốc |
| **sensor/hop ID** | Phân biệt client→proxy và proxy→origin | Một event không đại diện mọi hop |
| **TLS selected version** | Xác minh protocol policy | Cần đúng ServerHello, không chỉ ClientHello legacy_version |
| **Cipher suite selected** | Đánh giá negotiation | Không tự xác minh trust |
| **SNI** | Hostname do client đề xuất khi nhìn được | ECH/absence/mismatch và privacy |
| **ALPN offered/selected** | Phân tích HTTP/2 vs HTTP/1.1, gRPC | TLS 1.3 selected ALPN có thể encrypted |
| **Client fingerprint** | Phát hiện biến đổi hành vi client | Không phải identity tin cậy |
| **HelloRetryRequest count** | Quan sát handshake extra flight | Không tự là lỗi |
| **Resumption/PSK signal** | Phân tích full/resumed connection | Offer khác selection |
| **TLS Alert code** | Gợi ý lỗi khi nhìn được/đã giải mã | TLS 1.3 encrypted alert |
| **TCP RTT/retransmission** | Hiểu network latency/loss | Sensor capture loss/host offloading |
| **Handshake result from endpoint** | Thành công/lỗi thật theo TLS library | Vẫn khác app authorization |
| **Certificate validation result** | Thấy nguyên nhân trust policy | Không tự có trong PCAP |
| **Session/correlation ID** | Nối events giữa các hops | Không log actual session secrets |
| **Telemetry loss/coverage** | Biết kết luận có đủ dữ liệu? | Không thấy log chưa chắc an toàn |

### 21.3. Event normalized minh họa

~~~json
{
  "event_time_utc": "2026-11-28T08:05:10.050Z",
  "sensor": {
    "id": "edge-lab-01",
    "observation_point": "client_to_edge"
  },
  "flow": {
    "source_ip": "198.51.100.15",
    "source_port": 52100,
    "destination_ip": "192.0.2.20",
    "destination_port": 443,
    "transport": "TCP"
  },
  "tls": {
    "client_hello_seen": true,
    "server_hello_seen": true,
    "selected_version": "TLSv1.3",
    "selected_cipher_suite": "TLS_AES_128_GCM_SHA256",
    "sni_observed": "api.lab.example",
    "alpn_offered": ["h2", "http/1.1"],
    "alpn_selected": null,
    "alpn_selected_visibility": "encrypted_tls13_no_keylog",
    "certificate_validation_result": "unknown_from_packet_sensor",
    "handshake_result": "unknown_from_packet_sensor"
  },
  "capture": {
    "truncated": false,
    "packet_loss_status": "unknown"
  }
}
~~~

**Đây là schema tự xây để minh họa**, không phải output bắt buộc của Wireshark, Zeek, Suricata hoặc cloud logs. **alpn_selected=null** thể hiện không có dữ liệu đã xác minh, không phải server chắc chắn không chọn ALPN. Địa chỉ đều là ví dụ dành cho tài liệu.

### 21.4. Rules có thể áp dụng trong network monitoring

~~~text
Rule 1: TLS version downgrade in a protected environment
  Source: endpoint/server or negotiated ServerHello metadata
  Trigger: app requiring TLS 1.3 negotiates TLS 1.2 unexpectedly
  Correlate: allowed exceptions, LB hops, change records

Rule 2: Handshake failures above baseline
  Source: server TLS library logs + TCP metadata
  Trigger: high failure rate across a service/region
  Correlate: deploy, certificate rotation, client distribution

Rule 3: Unapproved client TLS behavior
  Source: ClientHello fingerprint metadata + workload identity
  Trigger: source has new characteristics outside its approved software role
  Correlate: EDR process and deployment

Rule 4: Certificate validation failure
  Source: client endpoint verification logs
  Trigger: unexpected unknown_ca / hostname / expiry errors
  Correlate: cert inventory, truststore changes, TLS hop

Rule 5: Missing TLS telemetry coverage
  Source: sensors/collectors and independent flow counters
  Trigger: flows continue but handshake events disappear
  Correlate: ECH/QUIC migration, parser upgrade, sensor health
~~~

Không coi **fingerprint mới, TLS 1.2 được chọn hoặc một handshake_failure** là bằng chứng tấn công. Trong hệ thống có nhiều clients, phiên bản, proxy và kiểm soát, đây thường là **tín hiệu cần phân loại theo bối cảnh**.

### 21.5. Liên hệ network security controls

- **Firewall/segmentation:** chặn IP/port/zone trái policy, nhưng không tự xác minh certificate.
- **IDS/IPS/NDR:** phân tích metadata/traffic bất thường tại sensor, có giới hạn vì TLS encryption.
- **WAF/reverse proxy:** thấy HTTP traffic khi terminate TLS, nhưng phải bảo vệ direct-to-origin.
- **VPN/ZTNA:** có thể thêm một TLS/DTLS/QUIC tunnel; TLS bên trong/ngoài cần tách đúng hop.
- **DNS security:** tên được phân giải giúp bổ sung context nhưng không chứng minh app đã kết nối.
- **mTLS/PKI:** cung cấp peer authentication khi validator đúng; application authorization vẫn riêng.
- **Cloud monitoring:** flow logs và identity audit giúp gắn handshake với workload/VM/service.

**Một hệ thống mạng an toàn cần phối hợp các lớp**, không dùng mỗi một SNI/ClientHello fingerprint như chứng thực danh tính và quyền truy cập.

## 22. Bảo vệ PCAP, quyền riêng tư và độ tin cậy của kết luận

### 22.1. Dữ liệu capture có thể chứa gì?

Một file **PCAP/PCAPNG** có thể chứa:

- IP/MAC addresses, ports, network topology và thông tin thiết bị.
- **SNI, DNS hostname**, ALPN, TLS client fingerprint và certificate ở những trường hợp quan sát được.
- Plaintext traffic từ những giao thức không mã hóa khác nếu capture filter rộng.
- Cookie, Authorization header, mật khẩu hoặc dữ liệu nghiệp vụ **nếu có plaintext/decrypted traffic**.
- TLS **Decryption Secrets Block** hoặc những thông tin nhạy cảm được nhúng/đính kèm.

Vì thế **“chỉ là packet metadata” không luôn đúng**. Phải gắn classification, access control, retention và quy trình xử lý bằng chứng.

### 22.2. Chỉ thu những gì thực sự cần

Một quy trình được khuyến nghị:

1. Giới hạn **capture interface, host/port và thời gian** phù hợp sự cố.
2. Dùng **snapshot/packet count limit** khi có thể.
3. Không đưa PCAP chưa làm sạch vào **ticket công khai, email nhóm lớn hoặc repository**.
4. Không mặc định bật TLS key logging trên thiết bị của nhân viên.
5. Dùng **structured TLS logs** thay raw PCAP nếu đã đủ chẩn đoán.
6. Nếu cần packet payload, áp phê duyệt, retention và quyền truy cập riêng.
7. Bảo toàn **raw evidence** khi incident và tạo bản chia sẻ có redaction đúng chính sách.

### 22.3. Làm sạch PCAP mà không làm hỏng bằng chứng

Nếu một báo cáo muốn minh họa handshake:

- Dùng **PCAP lab** hoặc bảng extracted TLS metadata thay vì đưa bytes của phiên thật.
- Có thể ẩn IP/user identities trong bảng báo cáo, nhưng cần ghi phương pháp mapping/giữ original trong kho điều tra nếu được phép.
- Không chỉnh sửa raw PCAP duy nhất rồi tuyên bố nó còn nguyên trạng.
- Khi chuyển định dạng hoặc strip secrets, cần xác minh **timestamps, packet count, field integrity** còn phù hợp với mục tiêu.
- Không để **TLS secrets hoặc private key** còn trong bản export chia sẻ.

### 22.4. Capture loss và clock drift

Một PCAP có thể thiếu bytes do:

- Mirror port bị oversubscription.
- Host packet capture drops.
- NIC offloading và buffer limitations.
- Interface được chọn sai, traffic qua tunnel khác.
- Capture bắt khi connection đã established.
- Hết file quota, disk I/O hoặc sampling.

Hai PCAP từ client/server có thể dùng đồng hồ khác nhau. **Không suy một chiều network latency bằng cách trừ timestamp giữa hai máy khi clocks chưa đồng bộ**. Nếu bắt buộc ghép, sử dụng time synchronization status, TCP sequence/ACK và correlation đáng tin.

### 22.5. Giữ chain of custody cho incident

Khi một PCAP là bằng chứng sự cố:

~~~text
Evidence ID:
Capture owner / authorized scope:
Capture device/interface:
Start/end UTC and clock sync:
Original filename and size:
Integrity digest:
Storage location and access policy:
Packet loss indication:
Transformations / display filters used:
Decryption secrets involved? yes/no and authorization reference:
Analyst conclusions and uncertainty:
~~~

Đây là **mẫu thực hành**, không phải quy chuẩn pháp lý cố định. Nội dung điều tra phải nêu rõ **fact, hypothesis và limits** của từng kết luận.

## 23. Checklist nghiệm thu bài thực hành TLS handshake packet

### 23.1. Kiểm tra kỹ thuật packet và protocol

| Hạng mục | Câu hỏi nghiệm thu | Bằng chứng |
| --- | --- | --- |
| **Capture authorization** | Đã có quyền, scope, thời gian và người sở hữu? | Lab plan/capture approval |
| **Capture point** | Biết sensor ở client, server, proxy hay overlay? | Interface/topology và time |
| **Flow selection** | TCP stream được chọn đúng 5-tuple/hop? | SYN/ACK + stream tracking |
| **Packet completeness** | Có đoạn đầu connection, packet loss/retransmission? | Capture health/TCP analysis |
| **Record framing** | Phân biệt TLS record và TCP segment? | Reassembled record details |
| **TLS version** | Đọc selected version đúng, không dùng legacy_version đơn lẻ? | ClientHello/ServerHello |
| **Cipher suite** | Phân biệt offered và selected? | ServerHello selection |
| **Key exchange** | Đọc supported_groups/key_share/HRR đúng? | Extensions/HRR record |
| **SNI** | Ghi rõ observed vs absent/ECH-hidden? | ClientHello/endpoint context |
| **ALPN** | Phân biệt offered vs selected và TLS 1.3 visibility? | ClientHello/EncryptedExtensions khi có |
| **Certificate** | Có biết TLS 1.2 plaintext vs TLS 1.3 encrypted? | Protocol + record analysis |
| **Certificate verification** | Có endpoint trust/hostname result thay vì chỉ xem cert? | TLS client/server logs |
| **mTLS** | Có phân biệt cert client và quyền ứng dụng? | Gateway/backend mTLS/authz logs |
| **Resumption** | Không gọi PSK offer là resumption accepted? | Handshake selection/endpoint evidence |
| **Early data** | Có hiểu 0-RTT replay considerations? | Endpoint logs/policy/traffic context |
| **Encrypted alerts** | Không gán alert reason khi TLS 1.3 chưa giải mã? | Logs hoặc plaintext alert khi có |
| **QUIC/DTLS** | Không dùng TCP TLS record filters với UDP security protocols? | QUIC/DTLS dissector đúng |
| **STARTTLS** | Đã xác định upgrade point giữa stream? | App greeting/command + ClientHello |

### 23.2. Kiểm tra điều tra và vận hành

| Hạng mục | Câu hỏi nghiệm thu | Bằng chứng |
| --- | --- | --- |
| **Error classification** | TCP, TLS, certificate và HTTP đã được tách? | Timeline + multiple logs |
| **Proxy/ingress hop** | Không trộn client→edge với edge→origin? | Per-hop captures/requests |
| **Latency** | Có tính time deltas theo cùng capture point? | Timestamp method rõ |
| **Clock sync** | Có biết drift giữa captures? | Sync status/time reference |
| **Identity correlation** | NAT, proxy, Pod UID/client session được map đúng time? | Temporal inventory |
| **Traffic decryption** | Chỉ dùng secrets của phiên lab có quyền? | Authorization/key log inventory |
| **Data minimization** | PCAP và key logs đã được bảo vệ? | Retention/access control |
| **SIEM fields** | Version/cipher/SNI/ALPN đúng semantics? | Schema tests |
| **Telemetry coverage** | Có phát hiện sensor/gateway log mất dữ liệu? | Heartbeat/loss metrics |
| **Investigation quality** | Phân biệt fact/hypothesis/unknown? | Incident case report |
| **Negative test** | Unsupported TLS/certificate mismatch được test an toàn? | Lab and endpoint errors |
| **Application** | Không coi handshake success là application success? | HTTP status/authz traces |
| **Rollback** | Một thay đổi TLS/certificate sai có cách phục hồi? | Versioned change/runbook |

### 23.3. Mẫu checklist cuối một phiên

~~~text
[ ] Đúng service, đúng TLS hop và đúng source/destination.
[ ] Capture đủ TCP/QUIC handshake, có thông tin packet loss.
[ ] Đã nhận diện ClientHello/ServerHello, version/cipher selected.
[ ] SNI/ALPN được ghi là offered/selected/unknown đúng trạng thái.
[ ] Không gán certificate/trust success chỉ từ passive PCAP.
[ ] Có client/server/proxy logs nếu TLS 1.3 handshake encrypted.
[ ] TCP/transport lỗi đã được loại trừ/ghi rõ.
[ ] Resumption/HRR/0-RTT được đánh giá theo phiên bản.
[ ] Application status được xem riêng.
[ ] Không có raw secrets, PII hoặc key logs trong báo cáo chung.
[ ] Kết luận có bằng chứng, uncertainty và hành động hợp lệ.
~~~

## 24. Câu hỏi tự kiểm tra và đáp án gợi ý

**1. TCP three-way handshake và TLS handshake khác nhau thế nào?**

TCP thiết lập kết nối byte stream và quản lý truyền dữ liệu; TLS thương lượng bảo mật, xác thực và dẫn xuất khóa trên transport phù hợp. TCP SYN/SYN-ACK/ACK không chứng minh TLS đã hoàn tất.

**2. Một TCP segment luôn chứa đúng một TLS record không?**

Không. TLS records có thể bị phân mảnh qua nhiều TCP segments hoặc nhiều records nằm trong một segment. TCP stream reassembly là cần thiết.

**3. Một handshake message có thể bị chia qua nhiều TLS records không?**

Có, cần đọc đúng record/handshake boundaries và reassembly; không đếm từng packet thành một message độc lập.

**4. Vì sao TLS 1.3 ClientHello thường có legacy_version 0x0303?**

Để tương thích với hệ thống cũ; phiên bản được đề xuất/chọn qua **supported_versions**. 0x0303 không đủ kết luận TLS 1.2.

**5. TLS 1.2 và TLS 1.3 khác nhau thế nào về khả năng nhìn certificate trên PCAP passive?**

TLS 1.2 full handshake thường gửi server Certificate plaintext; TLS 1.3 mã hóa Certificate sau ServerHello. TLS 1.3 cần session secrets/endpoint logs để xem chi tiết.

**6. Vì sao “Application Data” sau TLS 1.3 ServerHello chưa có nghĩa HTTP đã bắt đầu?**

Vì encrypted handshake messages cũng dùng **outer application_data records**. Không thể phân biệt inner content khi chưa giải mã.

**7. ClientHello offered cipher suite có chứng minh server đã dùng suite đó không?**

Không. Cần xem server chọn gì trong ServerHello và handshake có thành công.

**8. SNI có là bằng chứng người dùng đã truy cập nội dung website không?**

Không. SNI do client đề xuất, có thể khác HTTP Host, bị ECH bảo vệ, và handshake có thể thất bại trước HTTP.

**9. ALPN offered và selected khác nhau ra sao?**

Client đề xuất protocol list; server chọn một lựa chọn. Trong TLS 1.3, selection nằm trong encrypted EncryptedExtensions, không đọc được từ PCAP passive khi thiếu secrets.

**10. supported_groups và key_share có chứa private keys không?**

Thông thường key_share chứa public share và group information dùng thiết lập khóa, không phải private key hoặc session secret.

**11. HelloRetryRequest có thể giải thích hai ClientHello trong một connection không?**

Có. HRR yêu cầu client gửi ClientHello #2, khác TCP retransmission. Cần đọc HRR và stream context.

**12. Thấy GREASE extension có chứng minh TLS client lỗi không?**

Không. GREASE là cơ chế kiểm tra tương thích mở rộng, những giá trị chưa biết có thể là hành vi bình thường.

**13. Một Certificate message đủ chứng minh client tin server không?**

Không. Client cần xác minh chain, trust anchor, hostname, validity và policy; passive PCAP không có kết quả nội bộ của client.

**14. TLS certificate thường khẳng định hostname nằm ở đâu?**

Ở SAN phù hợp với identity được yêu cầu; CN chỉ có ý nghĩa tùy profile/legacy behavior, không thay cách hostname validation hiện đại.

**15. Vì sao root CA thường không có trong certificate chain được server gửi?**

Root thường là trust anchor nằm sẵn trong trust store của client; không phải cứ thiếu root trên wire là chain lỗi.

**16. CertificateVerify và Finished phục vụ mục tiêu gì?**

CertificateVerify chứng minh quyền dùng private key thích hợp trên handshake transcript; Finished xác nhận các bên có bí mật/handshake transcript phù hợp theo TLS version.

**17. mTLS có bảo đảm user được phép gọi mọi API không?**

Không. mTLS xác thực client/workload peer; API authorization, tenant/resource policy vẫn cần.

**18. Resumption có thể khiến Certificate không xuất hiện trong một phiên không?**

Có. TLS 1.2 abbreviated và TLS 1.3 PSK resumption có thể không gửi certificate mới, dựa trên session state hợp lệ theo cơ chế.

**19. TLS 1.3 pre_shared_key extension có nghĩa server đã chấp nhận PSK không?**

Không. Nó là offer. Cần ServerHello selection và handshake state.

**20. 0-RTT có rủi ro bảo mật nào nổi bật?**

Early data có rủi ro **replay** nếu ứng dụng không thiết kế phù hợp; không coi việc mã hóa early data là loại bỏ replay risk.

**21. TLS 1.3 Alert có thể không đọc được mã trong passive PCAP vì sao?**

Vì alerts sau khi có keys thường được mã hóa; ngoài packet outer type cần endpoint TLS logs hoặc giải mã phiên lab có quyền.

**22. TCP RST sau ClientHello có phải lúc nào cũng là expired certificate?**

Không. Có thể là network/proxy/server/timeout hoặc policy; cần server logs và chứng cứ xác thực certificate.

**23. HTTP/3 TLS handshake nằm trong lớp nào?**

TLS 1.3 handshake messages được mang trong QUIC CRYPTO frames trên UDP, không trong TLS records trên TCP.

**24. Vì sao QUIC Initial không bảo mật giống QUIC 1-RTT traffic?**

Initial protection keys có thể được dẫn xuất từ thông tin công khai của connection; payload Initial có thể được dissector phân tích. Handshake/1-RTT secrets ở giai đoạn sau có tính bảo mật khác.

**25. STARTTLS ảnh hưởng việc tìm ClientHello thế nào?**

ClientHello có thể xuất hiện sau application greeting/STARTTLS command giữa TCP stream; không nhất thiết ở packet ứng dụng đầu tiên.

**26. SSLKEYLOGFILE có được bật mặc định trên endpoints production để giám sát không?**

Không nên. TLS traffic secrets rất nhạy cảm; chỉ ghi trong lab hoặc tình huống đã được phê duyệt, với quyền truy cập và retention chặt.

**27. Có thể dùng private key server để giải mã mọi TLS 1.3 PCAP không?**

Không. Private key chứng thư không đủ giải mã ephemeral handshake traffic; cần secrets phiên được cấp quyền hoặc endpoint logs.

**28. Vì sao một sensor thấy không có ServerHello chưa đủ kết luận server im lặng?**

Có thể capture thiếu một chiều, sai interface, packet loss hoặc firewall chặn response. Đối chiếu client/server captures và network logs.

**29. Time from ClientHello to ServerHello bằng toàn bộ TLS handshake latency không?**

Không. Nó chỉ là một khoảng con, còn server flight, client verification, Finished và application processing.

**30. TLS fingerprint có là danh tính không thể giả mạo của malware không?**

Không. Fingerprint thay theo thư viện/phiên bản/GREASE, có thể trùng ở clients hợp lệ và bị bắt chước.

**31. TLS handshake thành công nhưng HTTP 403 có phải TLS sai không?**

Không mặc định. HTTP 403 thường liên quan authorization, WAF/proxy/app policy sau khi kênh bảo vệ đã hoạt động.

**32. Vì sao một proxy có thể tạo hai bộ TLS events khác nhau cho cùng request?**

Vì nó có thể terminate TLS phía client và mở TLS session khác tới origin, với ciphers, SNI, certificates và ALPN riêng.

**33. Trong TLS 1.3, không thấy certificate có phải server bỏ qua certificate auth không?**

Không. Certificate thường encrypted hoặc session được resume qua PSK; cần endpoint/session context.

**34. Điều kiện để một bản báo cáo handshake packet có thể tin cậy?**

Ghi rõ capture point, time, TCP/QUIC stream, packet loss, TLS version/handshake mode, offered/selected/unknown fields, endpoint logs hỗ trợ, trust validation evidence và giới hạn kết luận.

**35. Bằng chứng nào cần để nói một user bị từ chối do certificate?**

Kết quả xác minh từ **TLS client/server library logs**, certificate/hostname/truststore của đúng hop và timeline; không chỉ một packet chứa Alert hoặc TCP RST.

## 25. Những hiểu lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “TCP SYN-ACK nghĩa là TLS đã thành công.” | TCP và TLS có hai quá trình bắt tay khác nhau. |
| “Cứ TCP port 443 thì là TLS.” | Port không tự xác minh protocol; có thể là QUIC trên UDP hoặc dịch vụ khác. |
| “Một TCP packet tương ứng một TLS record.” | TCP là byte stream, record có thể phân mảnh hoặc gộp. |
| “Một TLS record luôn có một handshake message.” | Handshake messages và records không có quan hệ 1:1. |
| “Đếm handshake packets là biết số TLS connections.” | Retransmission/fragmentation và multiple records làm sai số đếm. |
| “Wireshark hiện TLSv1.2 record thì phiên không thể là TLS 1.3.” | TLS 1.3 dùng legacy_version/record version tương thích. |
| “ClientHello offered TLS 1.3 tức server đã chọn TLS 1.3.” | Phiên bản thực phải xem ServerHello/supported_versions. |
| “Cipher suite đầu tiên trong ClientHello là suite đã dùng.” | Server chọn suite phù hợp từ danh sách được phép. |
| “TLS_AES_128_GCM_SHA256 không có ECDHE nghĩa không có key exchange.” | TLS 1.3 negotiation của group/key_share tách khỏi cipher suite name. |
| “Key share public là khóa giải mã bí mật.” | Public shares không đủ tạo traffic secrets. |
| “GREASE là extension độc hại.” | GREASE thường là hành vi hợp lệ để kiểm tra extensibility. |
| “Hai ClientHello chắc chắn là hai sessions khác nhau.” | Có thể là HRR trong cùng connection hoặc retransmission bytes. |
| “Mọi TLS 1.3 connection có đầy đủ certificate trong PCAP.” | Certificate thường encrypted và resumption có thể không gửi mới. |
| “TLS 1.2 Certificate xuất hiện là client đã tin server.” | Packet chứa certificate, không chứa toàn bộ trust/hostname validation result. |
| “Root CA thiếu khỏi wire chain là lỗi.” | Root thường nằm trong client trust store, không bắt buộc gửi cùng chain. |
| “SNI là danh tính user.” | SNI là hostname client đề xuất, không phải xác thực user. |
| “SNI bằng HTTP Host trong mọi tình huống.” | Proxy, routing và custom clients có thể tạo khác biệt. |
| “ECH SNI outer luôn là hostname thật.” | ClientHelloInner có thể bảo vệ tên thật; outer metadata không đáng dùng để suy tên. |
| “Không có SNI nghĩa không có TLS.” | TLS vẫn có thể diễn ra không dùng extension SNI. |
| “ALPN h2 offered là server đã chọn HTTP/2.” | Client offered khác server selected; selected ALPN TLS 1.3 thường encrypted. |
| “TLS 1.3 Application Data đầu tiên chắc chắn chứa HTTP.” | Nó có thể chứa encrypted handshake messages. |
| “ChangeCipherSpec xuất hiện là TLS 1.2.” | TLS 1.3 có thể có dummy CCS cho middlebox compatibility. |
| “Không thấy plaintext TLS alert nghĩa phiên không lỗi.” | TLS 1.3 alerts có thể encrypted, hoặc connection đóng ở TCP level. |
| “TCP RST sau TLS record chứng minh bad_certificate.” | RST có nhiều nguyên nhân; cần client/server logs. |
| “Handshake_failure alert luôn do certificate.” | Có thể do protocol/cipher/group/policy và nhiều nguyên nhân khác. |
| “ServerHello có tức đã kiểm tra certificate thành công.” | Certificate verification xảy ra sau hoặc ngoài ServerHello tùy flow. |
| “CertificateVerify đồng nghĩa backend cho phép user.” | Cryptographic proof khác application authorization. |
| “mTLS certificate là user role trong ứng dụng.” | Certificate/workload identity phải được ánh xạ vào entitlement/authorization. |
| “Không có Certificate message trong resumed TLS 1.2 là không xác thực.” | Phiên có thể nối lại security context hợp lệ của phiên trước. |
| “ClientHello pre_shared_key nghĩa resumption đã chấp nhận.” | Cần biết ServerHello selection và endpoint state. |
| “0-RTT là plaintext vì gửi sớm.” | Early data được bảo vệ nhưng có replay risk riêng. |
| “Chỉ cần server private key để giải mã mọi TLS 1.3 PCAP.” | Forward-secret key exchange làm điều đó không khả thi từ cert private key đơn lẻ. |
| “Có key log từ browser là giải mã được upstream TLS của proxy.” | Các hop có secrets/handshake riêng. |
| “PCAPNG luôn không chứa session secrets.” | Một số exports có thể nhúng decryption secrets; phải kiểm tra trước chia sẻ. |
| “QUIC dùng TLS record layer trên TCP.” | QUIC dùng UDP và mang TLS handshake qua CRYPTO frames. |
| “Port UDP/443 luôn là HTTP/3.” | Có thể là protocol khác; cần decode hợp lệ. |
| “Không có TLS ClientHello đầu TCP là traffic không mã hóa.” | STARTTLS và protocol upgrades có thể bắt đầu giữa stream. |
| “Packet loss alert trong Wireshark chứng minh network packet loss.” | Có thể do sensor capture drops, offloading hoặc mirror limitations. |
| “Handshake latency là chênh ClientHello→ServerHello.” | Đó chỉ là một phần handshake, chưa gồm client Finished/validation. |
| “TLS handshake thành công là HTTP/API đúng quyền.” | App auth/authz, WAF, rate limits và backend còn có thể từ chối. |
| “Một PCAP tại client đủ biết mọi lý do lỗi origin.” | Proxy, firewall, server và mTLS upstream có những chặng/log riêng. |
| “TLS fingerprint là chữ ký không thể giả mạo của malware.” | Fingerprint có thể trùng, thay đổi hoặc bị bắt chước; cần nguồn khác. |
| “Ghi full PCAP và keylog trên production luôn tốt cho SOC.” | Tăng nguy cơ lộ session secrets/PII và chi phí; phải tối thiểu hóa và cấp quyền. |

## 26. Tổng kết

**Phân tích TLS handshake packet** đòi hỏi tách **transport/network events** khỏi **cryptographic handshake**, rồi tách **handshake đã hoàn tất** khỏi **application authorization và giao dịch nghiệp vụ**. Một bản PCAP là bằng chứng về **những packet được quan sát tại một điểm và thời điểm**, không phải sự thật đầy đủ về mọi hop hoặc kết quả nội bộ của TLS library.

Những nguyên tắc cốt lõi:

1. **Bắt đúng datapath và session:** xác định sensor/hop, TCP stream, thời gian, 5-tuple, packet loss và proxy/NAT.
2. **Hiểu reassembly:** TLS record khác TCP segment; handshake message có thể bị chia/gộp; retransmission không tạo phiên mới.
3. **Đọc negotiation theo chiều:** ClientHello là **offer**, ServerHello là **selection**, completion cần thêm bằng chứng.
4. **Tôn trọng khác biệt TLS 1.2/TLS 1.3:** certificate và nhiều handshake messages của TLS 1.3 được mã hóa; legacy_version không định danh phiên bản được chọn.
5. **Phân biệt metadata và danh tính:** SNI/ALPN/key_share là tín hiệu giao thức; certificate validation và application authorization là những kiểm tra riêng.
6. **Hiểu các biến thể:** HRR, PSK resumption, 0-RTT, ECH, mTLS, STARTTLS, QUIC và DTLS khiến handshake không luôn giống sơ đồ full TLS trên TCP.
7. **Chẩn đoán theo tầng:** TCP SYN/RST, TLS Alert, client certificate error, proxy ingress, origin mTLS và HTTP 4xx/5xx có nguyên nhân khác nhau.
8. **Dùng công cụ có giới hạn:** Wireshark/tshark/tcpdump/OpenSSL được vận hành trong lab/incident có quyền, không bỏ TLS verification để “debug cho nhanh”.
9. **Kết hợp observability:** PCAP + TLS endpoint logs + DNS/flow/firewall + proxy/app traces, có gắn độ tin cậy và coverage.
10. **Bảo vệ bí mật:** giới hạn PCAP, tránh thu hoặc chia sẻ TLS traffic secrets, certificate private keys và decrypted application data.

Trong **SECURITY_NETWORK_SECURITY**, năng lực đọc handshake là nền tảng để xác định ranh giới của **firewall, VPN/ZTNA, IDS/IPS, WAF, reverse proxy, network PKI, Kubernetes networking, DNS và cloud telemetry**. Một người phân tích tốt không chỉ biết đọc **ClientHello, ServerHello, Certificate hoặc Finished**, mà còn biết khi nào một trường **không hiện vì bị mã hóa**, khi nào một packet **bị thiếu do capture gap**, và lúc nào **phải dùng nguồn bằng chứng khác** thay vì đoán.

### Tài liệu tham khảo và hướng đọc thêm

- **RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3:** TLS 1.3 record/handshake, key schedule, extensions, resumption, early data, HRR và alerts.
- **RFC 5246 — The Transport Layer Security (TLS) Protocol Version 1.2:** TLS 1.2 full/abbreviated handshake và certificate/exchange message structures.
- **RFC 6066 — TLS Extensions:** SNI và các TLS extensions được định nghĩa trong nhóm quy chuẩn liên quan.
- **RFC 7301 — Transport Layer Security (TLS) Application-Layer Protocol Negotiation Extension:** ALPN offer/selection.
- **RFC 8701 — Applying GREASE to TLS Extensibility:** giá trị GREASE và khả năng tương thích của TLS implementations.
- **RFC 5077 — Transport Layer Security (TLS) Session Resumption without Server-Side State:** session tickets trong TLS 1.2.
- **RFC 7507 — TLS Fallback Signaling Cipher Suite Value (SCSV):** cơ chế chống fallback không an toàn trong phạm vi tương ứng.
- **RFC 9325 — Recommendations for Secure Use of Transport Layer Security (TLS) and Datagram Transport Layer Security (DTLS):** lựa chọn phiên bản/thuật toán và vận hành TLS/DTLS an toàn.
- **RFC 9000 — QUIC: A UDP-Based Multiplexed and Secure Transport:** QUIC connections, packet types và stream design.
- **RFC 9001 — Using TLS to Secure QUIC:** TLS handshake trong QUIC CRYPTO frames và secret derivation.
- **RFC 9147 — The Datagram Transport Layer Security (DTLS) Protocol Version 1.3:** khác biệt TLS/DTLS trên datagram.
- **RFC 9110 — HTTP Semantics**, **RFC 9113 — HTTP/2**, **RFC 9114 — HTTP/3:** semantics và những protocol/application transports liên quan.
- **RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile:** certificate path validation, KeyUsage, EKU và chain.
- **RFC 6960 — Online Certificate Status Protocol (OCSP):** trạng thái chứng thư và yêu cầu triển khai theo profile.
- **RFC 9460 — SVCB and HTTPS Resource Records:** định hướng DNS records có thể hỗ trợ lựa chọn dịch vụ/parameters trong kiến trúc hiện đại.
- **Wireshark User's Guide và Display Filter Reference (TLS, TCP, QUIC, DTLS):** giao diện, field names và dissector capabilities theo version.
- **tcpdump và libpcap documentation:** giới hạn capture scope, BPF capture filters, snaplen, packet drops và interface behavior.
- **OpenSSL s_client/s_server manual:** TLS test harness, certificate verification và key logging options theo phiên bản.
- **NIST SP 800-52 Rev. 2 — Guidelines for the Selection, Configuration, and Use of Transport Layer Security (TLS) Implementations:** baseline TLS configuration và verification policy.
- **NIST SP 800-207 — Zero Trust Architecture:** xác thực kết nối và access policy theo resource/trust boundary.
- **OWASP Transport Layer Security Cheat Sheet:** certificate validation, TLS hardening và implementation considerations.
- **Tài liệu firewall/IDS/IPS/WAF/ingress/cloud provider và TLS library đang sử dụng:** xác minh vị trí TLS termination, metadata visibility, packet loss, selected cipher/version, client auth và alert handling theo đúng deployment.
