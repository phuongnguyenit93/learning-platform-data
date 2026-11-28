# Làm việc với dữ liệu đã được mã hóa trong điều tra số trên mạng

## 1. Tại sao điều tra mạng ngày càng gặp ciphertext?

Trong một sự cố an ninh mạng, nhóm điều tra có thể nhận được tập tin PCAP chứa hàng nghìn phiên TLS hoặc QUIC, log lưu lượng đi qua VPN, hoặc một dòng TCP/SSH có nội dung gần như không thể đọc. Điều này **không có nghĩa dữ liệu điều tra vô dụng**. Kết nối đã mã hóa vẫn có thể để lại thông tin về *khi nào, từ đâu, tới đâu, đi bao nhiêu dữ liệu, qua giao thức nào, theo trật tự thời gian nào*; ở những hệ thống được tổ chức kiểm soát, còn có thể thu được **log phía endpoint, proxy, ứng dụng hoặc khóa phiên hợp lệ** để tái dựng nội dung trong phạm vi được cho phép.

Ngược lại, **không thể coi PCAP của kết nối TLS hiện đại là dữ liệu có thể tự giải mã** chỉ vì biết địa chỉ IP, chứng chỉ public của website, mật khẩu của user hoặc private key của server. Với các cấu hình có **forward secrecy**, private key dài hạn của server thường **không đủ** khôi phục khóa phiên từ một PCAP đã thu.

Mục tiêu của bài là xây dựng phương pháp **điều tra dữ liệu mạng đã mã hóa có căn cứ kỹ thuật, có thẩm quyền và giữ tính toàn vẹn chứng cứ**: phân loại mức nhìn thấy, chọn phương án quan sát không giải mã khi đủ, thu khóa phiên khi có quyền, liên kết nguồn bằng chứng và trình bày giới hạn của kết luận.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **plaintext, ciphertext, metadata, record/packet headers và khóa phiên**.
2. Hiểu vai trò của TLS 1.2/1.3, HTTPS, HTTP/2/3, QUIC, SSH, VPN/IPsec, WireGuard và DNS mã hóa trong forensic.
3. Giải thích tại sao **TLS 1.3 + (EC)DHE** không thể giải mã chỉ bằng RSA private key của server từ PCAP đã thu.
4. Xác định metadata có thể quan sát: **5-tuple, thời điểm, kích thước, hướng, DNS, SNI trong giới hạn, certificate logs và flow behavior**.
5. Thực hiện triage PCAP bằng **Wireshark/tshark/tcpdump chế độ đọc file**, không nhầm display filter với capture filter.
6. Xây dựng lab hợp pháp sử dụng **khóa phiên do client kiểm soát xuất ra**, bảo vệ tập tin key log.
7. Biết khi nào nên dùng **EDR, proxy logs, server access logs, DNS resolver, identity/IdP và cloud audit** thay cho giải mã.
8. Phân tích giới hạn của **JA3/JA4, traffic fingerprinting, SNI, ECH, DoH/DoT và QUIC**.
9. Bảo quản **PCAP, key logs, memory artifacts và kết quả giải mã** bằng hash, chain of custody, quyền truy cập và retention.
10. Viết phát hiện có **độ chắc chắn phù hợp**, phân biệt *observed evidence* và *inference* về exfiltration hay command-and-control.

Bài thuộc chương **Điều tra số trên mạng** của module **SECURITY_NETWORK_SECURITY**: vận dụng kiến thức TLS, VPN, DNS, firewall, IDS/IPS, phân đoạn, lưu lượng cloud và giám sát xâm nhập để điều tra mà không giả định việc mã hóa đồng nghĩa với “không có dấu vết”.

> **Ranh giới an toàn và pháp lý:** chỉ thu thập, đọc hoặc giải mã lưu lượng thuộc thiết bị, tài khoản, ứng dụng và môi trường đã được cấp quyền rõ ràng. Không truy cập khóa riêng tư hay session tokens của người khác, không triển khai TLS interception trái phép, không vượt certificate pinning và không dùng traffic analysis để kết luận nội dung nhạy cảm của người dùng khi không có bằng chứng. Ví dụ địa chỉ `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` và miền `example.test` là dữ liệu dành cho minh họa.

## 2. Phân biệt dữ liệu mã hóa và các lớp vẫn nhìn thấy

### 2.1. Bốn lớp của một quan sát mạng

| Lớp | Ví dụ | Khả năng đọc khi chỉ có PCAP |
|---|---|---|
| **Network/transport metadata** | IP nguồn/đích, cổng, protocol, TCP flags, packet length, thời điểm | Thường quan sát được tại điểm capture, trừ khi có đường tunnel/encapsulation che địa chỉ bên trong |
| **Handshake/protocol metadata** | TLS record framing, ClientHello thông thường, supported versions, ALPN được đề xuất trong ClientHello | Một phần nhìn thấy tùy TLS version, ECH, QUIC và vantage point |
| **Protected application data** | HTTP method/path, cookies, JSON, payload, file nội dung, SSH shell | Thường **không nhìn thấy** nếu TLS/SSH/VPN đang bảo vệ đúng |
| **Endpoint/control-plane evidence** | Access logs, identity, process tree, proxy transaction log, authorized key log | Có thể có qua nguồn riêng, không nhất thiết nằm trong PCAP |

**Metadata không đồng nghĩa nội dung.** Một flow gửi 500 MiB tới một IP bên ngoài không chứng minh chính xác dữ liệu bên trong là tài liệu bí mật. Nó có thể là backup, update, video upload, telemetry hợp lệ hoặc exfiltration; cần kết hợp identity, process, destination ownership, application/business context và các nguồn khác.

### 2.2. Sơ đồ điểm quan sát

~~~mermaid
flowchart LR
    C["Client process / browser"] -->|"Plaintext trước TLS"| E["Client TLS stack"]
    E -->|"Encrypted traffic"| N["Network sensor / PCAP"]
    N -->|"Encrypted traffic"| S["Server TLS termination"]
    S -->|"Plaintext sau TLS"| A["Application"]
    C -. "Authorized client logs/key log" .-> F["Evidence repository"]
    S -. "Access logs / keys if authorized" .-> F
    N -. "PCAP / flows / metadata" .-> F
~~~

Ở đoạn giữa Client TLS stack và Server TLS termination, sensor thường nhìn thấy **ciphertext và metadata**, không phải request body. Sau khi TLS được kết thúc, application hoặc reverse proxy có thể ghi request details; nếu reverse proxy mở kết nối TLS mới tới backend, đó là **một phiên mã hóa khác** với bộ khóa riêng.

### 2.3. Vị trí capture quyết định khả năng quan sát

Một packet sensor ở **ngoài VPN** có thể chỉ thấy địa chỉ IP của tunnel endpoints; sensor **bên trong VPN** sau giải mã do gateway hợp lệ có thể thấy inner flows. Sensor trước CDN/WAF có thể thấy một TLS session tới edge; backend phía sau gateway có thể có một TLS session thứ hai với certificate và identity khác.

Vì vậy, không viết “PCAP của server cho thấy user nói gì” trước khi xác định:

- Sensor nằm ở **client, edge, gateway, server hay network segment** nào?
- Có **NAT, TLS termination/re-encryption, QUIC, VPN, service mesh** hay proxy không?
- Host/process identity đã được ghép với flow theo **thời gian** chưa?
- Snaplen, packet drops, SPAN oversubscription, timestamp/clock skew có làm capture thiếu không?

### 2.4. Encryption bảo vệ những gì và không bảo vệ những gì?

| Cơ chế | Bảo vệ chính | Không bảo đảm |
|---|---|---|
| TLS/HTTPS | Bí mật và toàn vẹn dữ liệu trong phiên transport/application | Endpoint không bị chiếm, user có quyền nghiệp vụ, metadata mạng hoàn toàn ẩn |
| SSH | Bí mật, toàn vẹn kênh remote shell/tunnel, xác thực peer theo cấu hình | Host key luôn được kiểm tra, account được cấp đúng quyền |
| IPsec/WireGuard | Bí mật và toàn vẹn traffic trong tunnel theo cấu hình | Ẩn IP endpoints của tunnel khỏi đường Internet, bảo vệ plaintext sau khi rời tunnel |
| DoH/DoT | Bảo vệ DNS exchange giữa client và resolver | Resolver không biết truy vấn, mọi DNS-related metadata đều biến mất |
| Disk encryption | Bảo vệ data at rest trong điều kiện nhất định | Network session không lộ thông tin, RAM/live endpoint không chứa plaintext |

Một kết nối đã mã hóa vẫn có thể tới **đích độc hại**, vẫn bị lạm dụng bằng account hợp lệ hoặc vẫn làm lộ dữ liệu sau khi máy đích giải mã.

## 3. Kiến thức mật mã cần thiết khi đọc PCAP

### 3.1. Plaintext, ciphertext, secret và xác thực

- **Plaintext:** dữ liệu trước khi mã hóa hoặc sau khi giải mã thành công.
- **Ciphertext:** dữ liệu đã biến đổi bằng thuật toán và khóa bí mật; đọc trực tiếp không có ý nghĩa nội dung.
- **Symmetric session key/traffic secret:** khóa dùng cho mã hóa/xác thực bản ghi/packet trong một chiều và giai đoạn nhất định.
- **Public/private key pair:** thường phục vụ xác thực, chữ ký, trao đổi khóa hoặc các giao thức khác; không tự là khóa mã hóa mọi HTTP record.
- **AEAD:** cơ chế mã hóa có xác thực như AES-GCM/ChaCha20-Poly1305; dữ liệu bị sửa thường không vượt được kiểm tra integrity/tag.
- **Nonce/IV/sequence number:** yếu tố hỗ trợ bảo vệ từng record/packet; cách dùng khác giữa TLS, QUIC và SSH.

**Không thử giải mã bằng cách lấy public certificate rồi nhập vào Wireshark như một “password”.** Certificate công khai chủ yếu giúp định danh peer; giải mã cần đúng **session secrets** hoặc một cơ chế bảo vệ khóa khác đang được triển khai và có quyền tiếp cận.

### 3.2. Forward secrecy

Với **(Elliptic Curve) Diffie–Hellman ephemeral ((EC)DHE)**, các bên thỏa thuận secrets cho phiên từ thông tin tạm thời; việc tiết lộ private key chứng chỉ server về sau **không cho phép tự tính lại các traffic secrets** đã dùng, nếu implementation và secrets tạm thời được bảo vệ đúng.

Đây là mục đích của *forward secrecy*: giới hạn hậu quả khi khóa lâu dài bị lộ. Nó **không bảo đảm** plaintext an toàn nếu endpoint bị tấn công khi đang xử lý request, session secrets bị dump từ memory hoặc ứng dụng/proxy đang ghi log dữ liệu nhạy cảm.

### 3.3. Tại sao “có private key server” thường không đủ?

Trong **một số phiên TLS 1.2 cũ** sử dụng **RSA key exchange không có forward secrecy**, private key server có thể hỗ trợ giải mã nếu có đầy đủ handshake/PCAP và điều kiện kỹ thuật đúng. Với **TLS 1.2 (EC)DHE** và **TLS 1.3**, cách này không hoạt động vì private key của chứng chỉ dùng cho xác thực/chữ ký, không tái tạo secrets trao đổi khóa tạm thời.

| Giao thức/kiểu kết nối | Private key server có đủ giải mã PCAP? | Cách điều tra thích hợp hơn |
|---|---|---|
| TLS 1.2, RSA key exchange cũ và đầy đủ handshake | **Có thể**, tùy điều kiện; không áp dụng cho mọi cipher suite | Ưu tiên endpoint logs/session secrets; quản lý private key rất chặt |
| TLS 1.2 ECDHE/DHE | **Không** theo cách RSA private-key decryption | Authorized session key log, endpoint/server logs |
| TLS 1.3 | **Không**; luôn dùng key agreement có tính forward secrecy cho full handshake thông thường | Key log từ endpoint phù hợp, application/proxy evidence |
| HTTP/3 over QUIC | **Không**; QUIC dùng TLS 1.3 và packet protection riêng | QUIC-aware analyzer + authorized secrets hoặc telemetry ứng dụng |
| SSH | **Không** chỉ bằng SSH server host private key | SSH server audit, endpoint/session recording, process context |
| WireGuard | **Không** chỉ vì biết một public key hoặc interface IP | Gateway/host logs, endpoint evidence và flow metadata |

**Không khuyến khích chuyển hệ thống về RSA key exchange hoặc TLS yếu để “dễ điều tra”.** Hãy thiết kế observability tại endpoint/proxy đúng quyền thay vì làm yếu bảo mật đường truyền.

## 4. TLS 1.2 và TLS 1.3 qua góc nhìn điều tra

### 4.1. TLS handshake cơ bản

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as TLS Server
    C->>S: ClientHello (versions, cipher suites, extensions)
    S->>C: ServerHello + key agreement data
    Note over C,S: Traffic secrets được thiết lập theo handshake
    S-->>C: Encrypted handshake messages (TLS 1.3)
    C-->>S: Encrypted Finished
    C->>S: Encrypted application data
    S->>C: Encrypted application data
~~~

Trong TLS 1.3, sau ServerHello, phần lớn handshake tiếp theo (bao gồm certificate thông thường của server) được bảo vệ bằng handshake traffic keys. Với TLS 1.2, nhiều trường handshake như certificate thường có thể được quan sát trước khi application data được mã hóa.

### 4.2. Những trường có thể nhìn thấy từ PCAP

| Thành phần | TLS 1.2 phổ biến | TLS 1.3 phổ biến |
|---|---|---|
| Outer IP/port/transport | Có, tại vantage point không bị tunnel che | Có, tương tự |
| ClientHello | Thông thường hiển thị | Thông thường hiển thị nếu không có ECH |
| SNI | Có khi client gửi plaintext SNI | Có thể nhìn thấy outer SNI; inner SNI được bảo vệ khi ECH hiệu lực |
| Client-offered ALPN | Thường nhìn thấy trong ClientHello | Client-offered ALPN trong outer ClientHello có thể chỉ phản ánh outer và không bảo đảm application thật khi ECH |
| Server certificate | Thường plaintext trong TLS 1.2 full handshake | Thường nằm trong phần handshake mã hóa |
| HTTP path, cookies, body | Được mã hóa nếu HTTPS đúng | Được mã hóa nếu HTTPS đúng |
| TLS record sizes/timing | Có thể quan sát | Có thể quan sát, nhưng TLS 1.3 encrypted records ít lộ loại nội dung bên trong |

**SNI không phải một định danh đã xác thực của ứng dụng trong PCAP.** Nó do client đưa ra và có thể bị bỏ, dùng tên mặc định, hoặc bị ECH che. Kết nối tới một IP/CDN shared không tự chứng minh hostname thực.

### 4.3. TLS resumption, session tickets và 0-RTT

Session resumption có thể làm handshake ngắn hơn; TLS 1.3 PSK resumption dùng secrets phát sinh từ phiên trước hoặc cơ chế external PSK theo protocol. **0-RTT early data** có ngữ nghĩa riêng và rủi ro replay; việc phân tích chỉ từ một PCAP có thể thiếu context của phiên gốc và không biết nội dung bên trong.

Khi dùng key log để giải mã traffic, phải bảo đảm secret tương ứng với **đúng kết nối/epoch/chiều** và analyzer hỗ trợ. Một file key log không chứa đúng traffic secrets sẽ không tự giải mã tất cả phiên chỉ vì hostname trùng.

### 4.4. TLS termination nhiều lần

~~~text
Browser  --TLS session A-->  CDN/WAF
CDN/WAF  --TLS session B-->  Ingress proxy
Ingress  --mTLS session C--> Application service
~~~

Mỗi session có thể có **certificates, peer identities, keys và timing khác nhau**. Key log của browser chỉ liên quan session A; nó không tự mở session B/C. Điều tra phải ghi rõ đã giải mã **đoạn nào**, không diễn đạt “đã giải mã toàn bộ đường đi” khi chỉ có một đoạn.

## 5. QUIC và HTTP/3: khi TLS không còn nằm trên TCP

**QUIC** là giao thức transport sử dụng UDP, tích hợp TLS 1.3 handshake và cơ chế bảo vệ packet. **HTTP/3** sử dụng QUIC thay vì HTTP/2 over TCP. Người điều tra không nên gắn nhãn mọi UDP/443 là “DNS” hay mọi HTTPS là TCP/443.

### 5.1. Metadata QUIC có thể cung cấp gì?

- Outer IP/UDP ports, packet lengths, timestamps và hướng lưu lượng.
- QUIC long/short packet header **ở mức mà packet protection cho phép**, version, các Connection ID liên quan.
- Version Negotiation và một số handshake/transport events nhìn thấy tại vantage point.
- Packet count, burst, flow duration, kích cỡ và biến đổi path/NAT.

**QUIC Connection ID không phải định danh người dùng**. Nó hỗ trợ duy trì kết nối qua một số thay đổi network path và giảm phụ thuộc 5-tuple; định danh từ CID có thể thay đổi, được tạo ngẫu nhiên/đặc thù implementation và gây rủi ro nếu coi là user ID.

### 5.2. QUIC Initial và phần đã mã hóa

Trong QUIC v1, **Initial packet protection sử dụng những initial secrets có thể được suy ra từ thông tin công khai trong packet theo specification**. Công cụ phân tích hỗ trợ có thể giải mã tầng Initial để đọc phần handshake phù hợp trong phạm vi đó. Nhưng đây **không phải khả năng giải mã application data** và không mở được traffic keys của 1-RTT.

Sau khi các traffic secrets thông thường có hiệu lực, HTTP/3 frames/headers/body được bảo vệ. Hơn nữa, **QUIC version, key phase, packet number reconstruction, capture completeness và key log support** ảnh hưởng khả năng phân tích.

### 5.3. QUIC khác TCP trong forensic thế nào?

| Chủ đề | HTTPS trên TCP/TLS | HTTP/3 trên QUIC |
|---|---|---|
| Transport | TCP | UDP |
| Reconnect/path migration | TCP flow thường gắn 4-tuple/5-tuple | QUIC có thể dùng Connection ID và migration tùy endpoints |
| Retransmission metrics | TCP retransmission, ACK/SACK, RTT | QUIC loss recovery, ACK frames được bảo vệ ở nhiều packet spaces |
| HTTP method/path | TLS mã hóa | QUIC/TLS mã hóa |
| Network middlebox visibility | TCP flags, window, handshake | Không có TCP flags; QUIC packet protection che nhiều transport details |
| Decryption | Matching TLS session secrets | Matching QUIC/TLS secrets + QUIC-aware dissector |

Một UDP flow dài đến IP CDN có thể chứa QUIC, VPN, media streaming hoặc protocol khác. **Port 443/UDP là gợi ý**, không phải bằng chứng duy nhất.

### 5.4. Case xử lý khi TCP/443 cho kết quả khác UDP/443

Nếu client gặp sự cố trên HTTP/3 nhưng HTTP/2 hoạt động, hãy so **DNS/HTTPS records, client protocol negotiation, QUIC UDP path, firewall policy, loss/MTU, proxy capabilities và application logs**. Không khẳng định có tấn công chỉ vì UDP packets bị drop; nhiều firewall/network policies chủ ý giới hạn QUIC.

## 6. ECH, SNI và giới hạn của domain-based inference

### 6.1. Server Name Indication là gì?

Trong một TLS ClientHello thông thường, **Server Name Indication (SNI)** cho biết hostname client muốn kết nối. SNI giúp server/CDN chọn certificate và virtual host. Khi không có ECH, passive observer có thể thấy hostname trong ClientHello ở những phiên gửi SNI.

Tuy nhiên:

- Client có thể không gửi SNI hoặc dùng hostname không đại diện application cuối.
- Một domain có thể dùng **shared hosting/CDN/anycast**; IP không ánh xạ 1–1 với domain.
- SNI được client cung cấp, **không phải một bằng chứng đã được server xác thực**.
- DNS query có thể xảy ra trên resolver khác, cache, DoH/DoT hoặc trước thời gian PCAP.
- HTTP `Host`/`:authority` được bảo vệ khi HTTPS, không đồng nghĩa SNI.

### 6.2. Encrypted ClientHello (ECH)

**ECH** bảo vệ phần ClientHello bên trong (*inner ClientHello*) khi được triển khai thành công, bao gồm thông tin hostname nội bộ thường nhạy cảm. Passive observer có thể thấy **outer ClientHello/public name**, nhưng đó không phải hostname thực của application.

Không kết luận “SNI đã hoàn toàn biến mất trên toàn Internet” hoặc “outer SNI là website thực”. ECH support, DNS HTTPS/SVCB discovery, client/server/cdn policy và tình trạng rollout khác nhau theo hệ thống.

### 6.3. Kịch bản suy diễn sai

~~~text
Observed:
  Destination IP: shared CDN address
  Outer server name: public-cover.example.test
  UDP/443 / QUIC traffic

Invalid conclusion:
  "Người dùng chắc chắn truy cập public-cover.example.test,
   và payload chứa dữ liệu X."

Permissible conclusion:
  "Quan sát traffic QUIC tới CDN IP, với outer name hiển thị;
   website/application bên trong không được xác định từ các trường này."
~~~

Nếu cần xác nhận một hostname theo phạm vi pháp lý được phép, ưu tiên **browser/app history, DNS resolver logs, CDN/proxy request logs hoặc endpoint process telemetry**, kèm timestamp và provenance, thay vì đoán từ IP/outer SNI.

## 7. DNS đã mã hóa: DoH, DoT, DoQ và DNS metadata

**DNS** thường là nguồn dữ liệu hữu ích trong điều tra mạng: query name, response, TTL, rcode, resolver và timestamps. Nhưng người dùng/ứng dụng có thể sử dụng **DNS over HTTPS (DoH)**, **DNS over TLS (DoT)** hoặc **DNS over QUIC (DoQ)**.

### 7.1. Điểm quan sát khác nhau

| Giao thức | Transport thường gặp | Passive sensor ở giữa nhìn thấy gì? |
|---|---|---|
| DNS truyền thống | UDP/TCP 53 | Query/response plaintext nếu không qua lớp bảo vệ khác |
| DoT | TLS trên TCP, thường port 853 | IP/port, TLS metadata, kích cỡ/timing; không thấy QNAME trong TLS payload |
| DoH | HTTPS trên TCP/443 hoặc HTTP/3/QUIC | Outer HTTPS/QUIC metadata; DNS messages nằm trong nội dung đã mã hóa |
| DoQ | QUIC trên UDP, thường port 853 | QUIC metadata; DNS messages trong protected stream |

**Port không phải bằng chứng tuyệt đối**: DoH dùng HTTPS thông thường, có thể chạy trên hạ tầng CDN hoặc dùng tùy cổng; một resolver có thể hỗ trợ nhiều phương thức.

### 7.2. Nguồn chứng cứ thay thế

1. **Client resolver configuration:** OS, browser app DNS mode, corporate MDM settings.
2. **Managed resolver logs:** query/rcode/timestamps nếu resolver thuộc quyền tổ chức và bật logging.
3. **Endpoint process telemetry:** process nào mở session tới resolver, lúc nào.
4. **Proxy/egress logs:** destination/IP, hostname metadata có thể thấy nếu policy cho phép.
5. **Cloud DNS telemetry:** VPC/VNet DNS query logs khi được provider hỗ trợ và query đi qua resolver đó.

Nếu browser dùng DoH tới resolver ngoài tổ chức, DNS logs của resolver nội bộ **có thể không chứa truy vấn của browser**. Ngược lại, vắng mặt QNAME trong sensor không tự chứng minh có “DNS tunneling”.

### 7.3. Dấu hiệu dữ liệu DNS không đầy đủ

- Client có cache hoặc OS/browser prefetch.
- Split-horizon DNS, internal zones hoặc VPN DNS routing khác nhau.
- NAT/shared resolver gom nhiều user dưới một IP.
- DNS request được gửi qua encrypted resolver không được monitor.
- Lấy mẫu logs, rate-limiting, retention, mất collector hoặc clock skew.
- Application dùng IP literal hoặc cache endpoint từ phiên trước.

Vì vậy DNS query là bằng chứng **trong phạm vi điểm quan sát**, không phải lịch sử truy cập website đầy đủ.

## 8. SSH: encrypted shell và giới hạn của passive packet capture

**SSH** bảo vệ phiên đăng nhập, remote command, SFTP, SCP và port forwarding tùy cấu hình. Một sensor trên mạng thường quan sát:

- Kết nối TCP tới SSH port (mặc định thường 22, nhưng cấu hình có thể khác).
- Protocol identification/banner trước phần mã hóa theo phiên bản/implementation.
- Kích cỡ gói, timing, hướng, session duration, TCP resets/retransmissions.
- Có thể thấy những đặc trưng handshake/algorithm negotiation trước hoặc trong phần bảo vệ tùy phiên bản/protocol.

**SSH host private key không phải khóa giải mã toàn phiên** trong handshake hiện đại với ephemeral key exchange. Để xác định command hoặc file được chuyển, phải xem **endpoint process/audit logs, authorized session recording, file logs, SSH bastion/PAM records** và các nguồn khác.

### 8.1. Port forwarding là điểm forensic nhạy cảm

Một SSH connection có thể mang nhiều logical channels, port forwarding và transfer trong **cùng kênh mã hóa**. Chỉ thấy TCP/22 từ workstation tới bastion không chứng minh nội dung là “chỉ đăng nhập shell” hoặc đã có exfiltration. Khi điều tra:

- Kiểm tra policy `AllowTcpForwarding`, authorized_keys restrictions, broker session log.
- Ghép identity người dùng, source host, UTC và destination được mở qua bastion khi có audit.
- Phân biệt **port forwarding được duyệt** với đường pivot trái phép bằng business context.
- Không dùng heuristic packet size để kết luận chính xác người dùng gõ câu lệnh nào.

### 8.2. Không làm yếu SSH để ghi nội dung

Không tắt host key checking, chuyển sang giao thức plaintext hoặc ép cipher lỗi thời chỉ để điều tra. Nếu tổ chức cần session-level visibility, thiết kế **bastion có recording, OS command auditing, JIT/PAM và retention** theo quyền ngay từ trước sự cố.

## 9. IPsec, WireGuard, OpenVPN và traffic trong tunnel

### 9.1. Outer và inner addresses

~~~mermaid
flowchart LR
    C["Workstation / Site A"] -->|"Inner 10.x traffic"| V1["VPN Gateway A"]
    V1 -->|"Encrypted tunnel: outer IP A -> outer IP B"| NET["Internet sensor"]
    NET --> V2["VPN Gateway B"]
    V2 -->|"Decrypted inner flow"| APP["Private service"]
    V1 -. "Tunnel state / SA logs" .-> E["Forensic timeline"]
    V2 -. "VPN auth/flow logs" .-> E
~~~

Với **IPsec tunnel mode**, inner packet (bao gồm địa chỉ trong tunnel) được bảo vệ bên trong outer IP packet theo cấu hình. Passive sensor trên Internet nhìn thấy outer tunnel endpoints, ESP/NAT-T metadata và packet sizes/timing, không tự nhìn thấy inner user service flow.

Với **WireGuard**, UDP transport bảo vệ inner IP packets theo key agreement/session semantics; không thể suy HTTP/DNS payload bên trong chỉ từ outer UDP flow. **OpenVPN** có thể dùng UDP hoặc TCP và TLS-based control channel; cấu hình/data channel cipher/keys khác IPsec/WireGuard.

### 9.2. IKE và ESP không giống TLS

**IPsec/IKEv2** sử dụng security associations, key exchange và ESP/AH theo cấu hình. Không lấy `SSLKEYLOGFILE` của browser rồi kỳ vọng Wireshark giải mã ESP của VPN; đây là **hệ khóa và protocol khác**. Một số công cụ cho phép giải mã ESP nếu có đúng **SA parameters/keys/algorithm** được cung cấp hợp lệ và hỗ trợ.

Các giá trị như SPI, outer IP, ESP packet lengths và IKE session metadata có thể hỗ trợ nhận dạng tunnel, nhưng **không có giá trị giải thích nội dung gói bên trong** nếu không có tương quan ở tunnel endpoint.

### 9.3. Sự kiện phía gateway có giá trị cao

| Nguồn | Câu hỏi có thể trả lời |
|---|---|
| VPN user authentication | Identity nào đã thiết lập tunnel, từ thiết bị/địa chỉ nào? |
| Tunnel connection records | Bắt đầu/kết thúc lúc nào, được cấp IP nội bộ nào? |
| Inner flow logs tại gateway | Client sau giải mã kết nối tới private service nào? |
| Firewall policy/route | Flow nào bị chặn, qua vùng nào? |
| Endpoint EDR/OS | Process nào khởi tạo hoạt động qua VPN? |
| Service application logs | User action/business outcome nào thực sự xảy ra? |

Một VPN tunnel `UP` không chứng minh mọi application request thành công; tương tự một ESP flow lớn **không tự chứng minh exfiltration**.

### 9.4. Vấn đề site-to-site và shared identity

Ở site-to-site VPN, nhiều hosts đi qua **một cặp gateway outer IP**. Nếu chỉ có outer flow records, người điều tra có thể không biết host nào bên trong sinh traffic. Cần kết hợp **VPN gateway inner-flow telemetry, DHCP/NAC/NAT mapping và app logs**, theo thời gian.

## 10. Tư duy điều tra khi không có khả năng giải mã

### 10.1. Không có plaintext không có nghĩa không thể đưa ra kết luận

Có hai nhóm câu hỏi:

1. **Câu hỏi mạng:** host có thực sự liên lạc với destination không, timing/byte counts/duration thế nào, phiên có bị firewall chặn hay tới server, protocol/transport nào đang sử dụng?
2. **Câu hỏi nội dung/nghiệp vụ:** đường URL, user action, tài liệu nào đã gửi, credential nào có trong payload, request thành công hay không?

Nhóm thứ nhất thường được trả lời **tương đối tốt** từ packet/flow metadata kết hợp logs. Nhóm thứ hai cần **evidence từ endpoint, server, proxy có thẩm quyền hoặc decryption hợp lệ**. Không gộp hai nhóm để tạo kết luận “đã gửi dữ liệu X” khi chỉ có kích cỡ lưu lượng.

### 10.2. Network-only triage workflow

~~~mermaid
flowchart TD
    A["Nhận PCAP / flow alerts"] --> B["Validate source, scope, hash, time"]
    B --> C["Classify outer transport & tunnel"]
    C --> D["Build 5-tuple/connection timeline"]
    D --> E["Extract observable handshake/metadata"]
    E --> F["Correlate asset, DNS, NAT, proxy, identity"]
    F --> G{"Đã trả lời câu hỏi điều tra?"}
    G -- "Có" --> R["Report facts + limits"]
    G -- "Chưa" --> H["Request lawful endpoint/server evidence"]
    H --> I{"Authorized decryption possible?"}
    I -- "Có" --> J["Key log + controlled analysis"]
    I -- "Không" --> R
    J --> R
~~~

Lưu **nguồn gốc và giới hạn quan sát** ở mỗi bước: sensor location, packet loss, capture window, NAT/identity mapping confidence, ingestion delay và việc lưu lượng được mã hóa.

### 10.3. Những dấu hiệu đáng xem trong encrypted flows

| Quan sát | Giả thuyết có thể kiểm tra | Không được kết luận ngay |
|---|---|---|
| Periodic TLS/QUIC connections cứ 60 giây | Scheduled job, telemetry hoặc beacon | Chắc chắn C2 |
| Outbound bytes tăng đột ngột | Backup, upload hợp lệ hoặc exfiltration | Nội dung là database dump |
| Một process lạ mở phiên TLS mới | Phần mềm cập nhật, remote tool hoặc malware | Process chắc chắn độc hại |
| Đích mới liên hệ nhiều endpoints | CDN/platform service, analytics hoặc compromise | Toàn bộ endpoints đã bị xâm nhập |
| TLS handshake fail liên tục | Cert/clock/policy issue, scanning, malware | Đây là password brute force |
| QUIC/UDP443 gia tăng | HTTP/3 adoption, media traffic hoặc covert channel | NetworkPolicy bị bypass |
| DNS xuất hiện ít hơn sau thay đổi browser | DoH/DoT, cache, no traffic hoặc collector mất dữ liệu | DNS tunneling đã xảy ra |
| Upload vào IP mới ngay trước incident | Legitimate SaaS sync hoặc exfil | Dữ liệu khách hàng đã bị rò rỉ |

**Base rate và bối cảnh nghiệp vụ** rất quan trọng. Một đặc trưng đơn lẻ thường có false positives; kết luận cần xét thay đổi phần mềm, giờ làm việc, approved SaaS, vùng mạng, user identity và so với baseline.

## 11. Metadata hữu ích từ PCAP đã mã hóa

### 11.1. 5-tuple và thời điểm

Một flow được mô tả bằng:

~~~text
Source IP:      192.0.2.42
Source port:    51432
Destination IP: 203.0.113.50
Destination port: 443
Transport:      TCP
Start UTC:      2026-11-28T03:00:00Z
End UTC:        2026-11-28T03:04:30Z
Observed bytes: sensor-scope-specific
~~~

5-tuple giúp tương quan với firewall/NAT/EDR, **không phải định danh duy nhất suốt đời**. Source ports tái sử dụng; NAT đổi địa chỉ/cổng; DHCP cấp lại IP; các phiên có thể overlap trong nhiều devices/regions.

### 11.2. Hướng dữ liệu và đối xứng

Nếu PCAP thấy 800 MiB từ client ra ngoài, 4 MiB phản hồi, đó là **outbound-heavy session** theo cách sensor tính. Nhưng:

- Có thể gồm **retransmissions, protocol overhead hoặc capture duplicate**.
- Network tap không nhất thiết thấy hai chiều traffic giống nhau do asymmetric routing.
- Nếu sensor nằm sau NAT/proxy, chủ thể quan sát có thể là **gateway** chứ không phải endpoint gốc.
- Payload bị mã hóa; không thể suy file names hay dữ liệu kinh doanh chỉ từ byte counts.

### 11.3. TCP flags và transport signals

Trong TCP capture:

- `SYN`, `SYN-ACK`, `ACK` giúp xem thiết lập kết nối.
- `FIN`/`RST` giúp xem kết thúc/reset; không tự nêu lý do ứng dụng.
- Retransmission và RTT estimates gợi ý congestion/loss, có thể ảnh hưởng capture analysis.
- Zero window/receive window/context có thể cho thấy flow control.

**TCP stream được establish không chứng minh TLS handshake thành công hoặc HTTP request hợp lệ.** Phải phân lớp TCP/TLS/application.

### 11.4. Kích cỡ gói và timing

Traffic shape có thể phản ánh **interactive SSH**, bulk data transfer, streaming hoặc keepalive, nhưng chính các pattern đó cũng xuất hiện trong nhiều ứng dụng hợp pháp. Nén, padding, multiplexing, traffic shaping, CDN/proxy, VPN encapsulation và retransmission khiến **ước lượng nội dung từ kích cỡ khó tin cậy**.

Nếu sử dụng traffic fingerprinting, chỉ trình bày **xác suất/độ chắc chắn có kiểm định**, không khẳng định nội dung cá nhân hoặc tài liệu cụ thể.

## 12. TLS fingerprints: JA3, JA4 và rủi ro nhận diện nhầm

### 12.1. Fingerprint không phải user identity

**JA3** là một kỹ thuật tạo fingerprint từ một số thuộc tính của TLS ClientHello truyền thống như version, cipher suites, extensions, supported groups và EC point formats theo cách triển khai cụ thể. **JA4** là một nhóm phương pháp fingerprint được thiết kế mới hơn, với đặc trưng và canonicalization riêng; tính khả dụng phụ thuộc sensor/vendor/tooling.

**Không khẳng định JA3/JA4 là ID duy nhất của malware hoặc của người dùng**. Nhiều ứng dụng dùng chung TLS libraries, browser versions, load balancers hoặc middleboxes; cùng một fingerprint có thể đến từ nhiều nguồn, và client có thể thay cấu hình.

### 12.2. Lý do fingerprint thay đổi

- TLS library/browser/client version được cập nhật.
- Extension ordering hoặc GREASE values theo behavior của client.
- HTTP proxy/VPN/CDN/antivirus interception tạo một TLS connection khác.
- TLS 1.2 vs TLS 1.3, ALPN, QUIC/HTTP3 support.
- ECH làm khác phần thông tin observer có thể thấy.
- Network security products chuẩn hóa hoặc thay ClientHello.

### 12.3. Cách sử dụng hợp lý

~~~text
Observation:
  New TLS ClientHello fingerprint appears on 12 workstations.
  Endpoints share a recently installed app version.
  All connect to the same approved software update service.

Appropriate assessment:
  Fingerprint change aligns with authorized software rollout.
  No incident conclusion from fingerprint alone.
~~~

Trong điều tra thật, fingerprint có ích để **cluster sessions, tìm outliers và tìm endpoints cùng behavior**. Kết hợp với EDR process name/hash, signer, command line, DNS, cloud logs, firewall rule, identity và threat intelligence có provenance; tránh dùng một hash fingerprint như tiêu chí “block toàn bộ”.

### 12.4. ECH/QUIC và fingerprint quality

Khi visibility của ClientHello bị giới hạn hoặc QUIC transport thay đổi cấu trúc handshake, công cụ JA3 truyền thống có thể **không có đủ dữ liệu/không áp dụng**. Dùng analyzer hỗ trợ protocol/version và ghi **fingerprint method/version/scope** trong evidence; không coi “no JA3” là dấu hiệu xấu.

## 13. Chọn nguồn dữ liệu thay thế giải mã

### 13.1. Khi nào ưu tiên log hơn plaintext PCAP?

Nếu câu hỏi là “tài khoản nào tải object X”, thì **cloud object storage audit/access log** có thể trả lời chính xác hơn suy luận từ encrypted network flow. Nếu câu hỏi là “process nào mở kết nối đến domain mới”, **EDR socket/process telemetry** quan trọng hơn việc giải mã HTTP. Nếu câu hỏi là “giao dịch có thành công không”, **server application logs với request ID** thường trực tiếp nhất.

| Câu hỏi điều tra | Nguồn ưu tiên | Bẫy |
|---|---|---|
| Host nào kết nối tới IP/port? | Firewall/NAT logs, EDR, flow + DHCP | Shared public IP, NAT port mapping |
| Process nào tạo kết nối? | Endpoint EDR/socket telemetry | PID reuse, delayed capture, agent tamper |
| User identity nào? | IdP/SSO, VPN, PAM, application auth logs | Shared account, bearer token delegation |
| URL/method nào được gọi? | Server/reverse proxy/CDN access logs | TLS termination stage, route rewriting, logging gaps |
| Dữ liệu nào được upload? | Application/object storage audit, DLP, server logs | Multipart requests, encryption before application, incomplete logs |
| Có DNS lookup không? | Managed resolver, client logs, DNS flow | DoH/DoT, caching, VPN split DNS |
| VPN user truy cập service nội bộ nào? | VPN gateway inner flow + app logs | Site-to-site shared identity, missing flow logs |
| Có command trong SSH không? | Authorized bastion/PAM session record, OS audit | Session recording coverage, forwarding |
| Cloud IAM bị thay đổi không? | Cloud control-plane audit | Actor identity vs role/session chaining |
| Mã độc đã dùng C2 chưa? | EDR process tree + flow timing + TI | Beacon-like pattern cũng có ở software hợp lệ |

### 13.2. Correlate theo ID và thời điểm

~~~mermaid
flowchart LR
    E["EDR: process and device ID"] --> C["Investigation correlation"]
    N["NAT/VPN: address and port mapping"] --> C
    F["Firewall: 5-tuple and action"] --> C
    D["DNS/proxy: hostname/URL if visible"] --> C
    A["Server audit: request and user"] --> C
    C --> R["Timeline + evidence links + confidence"]
~~~

Với cloud/Kubernetes, đối chiếu **VM instance ID, Pod UID, namespace, node, service account, VPC network interface**. Một Pod IP tái sử dụng sau khi Pod cũ bị xóa có thể làm attribution sai nếu không có creation/deletion timestamp.

### 13.3. Negative evidence không phải bằng chứng không xảy ra

Nếu server không có request log, có thể request không tới server, server log bị tắt, dữ liệu bị sampling, request tới region khác hoặc bị chặn trước ingress. Nếu DNS logs không có domain, có thể client dùng cache/DoH. **Không suy “không có sự kiện” từ log trống** trước khi xác minh coverage, retention, sampling, vantage và logging configuration.

## 14. PCAP acquisition và forensic readiness

### 14.1. Thu từ đâu để chứng minh điều gì?

| Vantage | Nhìn thấy | Giới hạn |
|---|---|---|
| Client host NIC | Outer traffic, local interface context | Process attribution cần EDR/OS; traffic đã TLS mã hóa |
| Switch SPAN/TAP | Packets qua đoạn mạng đó | Port mirroring có thể drop/duplicate, asymmetric path |
| Firewall trước/ sau NAT | Flow tuples, policy actions ở boundary | Địa chỉ đã đổi, có thể không thấy cả hai chiều |
| CDN/reverse proxy | Client edge traffic + logs | Origin TLS segment khác client segment |
| VPN gateway outer interface | Encrypted tunnel packets | Inner endpoints bị che |
| VPN gateway inside interface | Inner traffic sau tunnel termination | Có thể lại được mã hóa bằng TLS end-to-end |
| Cloud VPC/VNet flow records | Aggregate flows/action metadata theo provider | Không phải packet-level PCAP; sampling/aggregation |
| Application server | Network flow tới service, app logs | Không tự chứng minh client IP khi qua proxy |

### 14.2. Capture cần ghi metadata đầy đủ

~~~yaml
# MẪU BẢO QUẢN CHỨNG CỨ, không phải dữ liệu đã thu thực tế.
case_id: NF-LAB-2026-010
evidence_id: PCAP-0001
sensor_id: sensor-branch-a
sensor_location: egress-firewall-outside-interface
interface: interface-id-from-inventory
acquisition_start_utc: pending
acquisition_end_utc: pending
sensor_clock_offset: pending
capture_format: pcapng
snap_length: pending
capture_filter: documented-and-reviewed
packet_drop_count: pending
file_size_bytes: pending
sha256: pending
collector_and_tool_version: pending
storage: restricted-encrypted-evidence-vault
chain_of_custody: pending
~~~

**PCAP chưa được hash/niêm phong không có nghĩa đã mất giá trị**, nhưng phải ghi các lỗ hổng của chuỗi chứng cứ. Cần giữ **original capture** và phân tích trên copy; không viết lại file gốc khi filter/cắt bớt.

### 14.3. Packet loss và truncation

Nếu snap length cắt ngắn packet, có thể thiếu phần handshake/application bytes cần reassembly hoặc decryption. Nếu sensor drop packets do quá tải, bản capture có thể thiếu TLS records/QUIC packets; việc analyzer báo **decryption failed** không tự chứng minh khóa sai.

Đối với high-rate links, xây kế hoạch **capture filter, rolling PCAP, storage budget, loss monitoring và retention** trước sự cố; tránh tạo PCAP chứa traffic của toàn tổ chức khi chưa có phạm vi và quyền.

### 14.4. Time correlation là một phần của chứng cứ

Giữ **event time, capture timestamp, ingest time, UTC offset và NTP/clock uncertainty**. Một sensor sai đồng hồ hai phút có thể làm người điều tra liên kết nhầm TLS session với process khác. Không sửa timestamp gốc; tạo timeline normalized kèm assumptions.

## 15. Phân tích PCAP mã hóa bằng công cụ ở chế độ đọc

Các lệnh sau **chỉ đọc file PCAP/PCAPNG đã được cấp phép** trong môi trường phân tích, không sniff hệ thống đang chạy và không sửa firewall. Một số command vẫn có thể tạo logs, cache hoặc shell history trên **máy phân tích**; nên dùng workstation forensic riêng và working copy.

### 15.1. Kiểm tra capture metadata

~~~bash
# Chỉ đọc file PCAP đã được ủy quyền.
capinfos capture-lab.pcapng

# In tối đa 20 packet summaries, tránh dump payload nhạy cảm ra terminal.
tcpdump -nn -r capture-lab.pcapng -c 20
~~~

`capinfos` có thể hiển thị capture size, packet count, time range, interface metadata và các trường khác tùy file format/tool version. Không tự coi capture duration = thời gian một session thực sự kéo dài nếu start/end packet nằm ngoài cửa sổ thu.

### 15.2. Thống kê TCP/UDP conversations

~~~bash
# Chỉ đọc, thống kê conversation trên file lab.
tshark -r capture-lab.pcapng -q -z conv,tcp
tshark -r capture-lab.pcapng -q -z conv,udp
~~~

Thống kê conversation thường cho **bytes/frames theo điểm capture**, không phải ứng dụng đã nhận payload thành công. NAT/tunnels có thể khiến một conversation liên quan nhiều endpoints bên trong.

### 15.3. Lọc TLS ClientHello

~~~bash
# Display filter -Y áp sau khi đọc file; không phải capture filter -f.
tshark -r capture-lab.pcapng \
  -Y "tls.handshake.type == 1" \
  -T fields \
  -e frame.time_epoch \
  -e ip.src \
  -e ip.dst \
  -e tcp.stream \
  -e tls.handshake.extensions_server_name
~~~

Trong TLS 1.3/QUIC/ECH, dữ liệu hoặc trường hiển thị có thể khác và một số phần ClientHello không quan sát được như kỳ vọng. `tcp.stream` không phù hợp cho QUIC/UDP; dùng UDP/QUIC dissector và field names **đã kiểm tra theo version của tshark**.

### 15.4. Lọc traffic theo host có quyền phân tích

~~~bash
# Thay 192.0.2.42 bằng IP thuộc sample/lab được duyệt.
tshark -r capture-lab.pcapng \
  -Y "ip.addr == 192.0.2.42 && (tls || quic)" \
  -T fields \
  -e frame.time_epoch \
  -e ip.src \
  -e ip.dst \
  -e frame.len
~~~

Giải thích **điểm quan sát** trước khi tính bytes; `frame.len` là kích cỡ frame do dissector hiểu, không phải bytes ứng dụng. Với IPv6, cần filter/fields IPv6 tương ứng như `ipv6.addr`; một biểu thức chỉ `ip.addr` không bao phủ mọi traffic dual-stack.

### 15.5. Xem retransmission và resets

~~~bash
tshark -r capture-lab.pcapng \
  -Y "tcp.analysis.retransmission || tcp.flags.reset == 1" \
  -T fields \
  -e frame.time_epoch \
  -e ip.src \
  -e ip.dst \
  -e tcp.stream \
  -e frame.number
~~~

**Wireshark TCP analysis flags là heuristic** trên packet sequence nhìn thấy. Nếu capture bị drop/reorder hoặc asymmetric routing, một số cảnh báo có thể không phản ánh chính xác lỗi thật của kết nối. Đừng suy “attacker cố tình reset” từ `RST` đơn lẻ.

### 15.6. Wireshark GUI: các bước điều tra

1. Làm việc trên **working copy**; ghi hash của original và tool version.
2. Mở file với profile được kiểm soát, tránh tự load plugin không tin cậy.
3. Xem **Statistics → Protocol Hierarchy** và **Conversations/Endpoints**.
4. Xem **Statistics → I/O Graphs** theo thời gian; nhớ rằng giá trị chỉ phản ánh capture.
5. Lọc `tls`, `quic`, `tcp.stream eq N`, `ip.addr == ...` hoặc field tương ứng.
6. Xem **TLS handshake details**, SNI/ALPN nếu hiển thị và không bị bảo vệ.
7. Đối chiếu **EDR process/identity, DNS, firewall NAT** với session timestamp.
8. Ghi điểm hạn chế: missing handshake, ECH, incomplete capture, unknown payload.

### 15.7. Display filter khác capture filter

| Khái niệm | Ví dụ | Dùng khi nào? |
|---|---|---|
| **Capture filter** (BPF-like) | `host 192.0.2.42 and port 443` | Lọc khi thu; có thể làm **mất vĩnh viễn** packets ngoài filter |
| **Display filter** (Wireshark syntax) | `ip.addr == 192.0.2.42 && tls` | Lọc cách hiển thị **sau khi đã thu** |

Không gửi `ip.addr == ...` vào tùy chọn BPF rồi kỳ vọng đúng syntax, hoặc dùng `host ...` như một Wireshark display filter. Khi thu evidence, **capture filter quá hẹp** có thể loại handshake, DNS, reverse path hoặc traffic qua cổng khác khiến điều tra khó hơn.

## 16. Lab giải mã TLS hợp lệ bằng session key log

### 16.1. Mục đích và ranh giới

Lab này minh họa **tại sao key log của chính client trong môi trường mình sở hữu** có thể giúp Wireshark giải mã một session TLS để quan sát request/response, trong khi private key của certificate thông thường không đủ. Nó **không hướng dẫn chiếm khóa hay bẻ mã lưu lượng của người khác**.

Điều kiện tiên quyết:

- Có endpoint HTTPS test do bạn quản lý, ví dụ `https://api.lab.example.test/health`; tên miền này chỉ là ví dụ, **không thể chạy nguyên mẫu nếu không được cấu hình**.
- Một browser/HTTP client build có hỗ trợ **NSS-compatible TLS key log** (ví dụ biến môi trường `SSLKEYLOGFILE` với một số trình duyệt và TLS backends).
- Có quyền capture **chính lưu lượng test của client**, có phê duyệt cho việc lưu key log.
- Có workspace mã hóa, hạn chế truy cập; **không dùng real user cookies/tokens hoặc production credentials**.

### 16.2. Trình tự thử nghiệm

~~~mermaid
flowchart TD
    A["Own test client + own HTTPS endpoint"] --> B["Create restricted key-log destination"]
    B --> C["Enable client-supported session key logging"]
    C --> D["Capture only authorized lab connection"]
    D --> E["Generate benign HTTPS GET"]
    E --> F["Preserve original PCAP + key log separately"]
    F --> G["Load working copy into Wireshark"]
    G --> H["Configure TLS (Pre)-Master-Secret log filename"]
    H --> I["Confirm decrypted HTTP or supported protocol"]
    I --> J["Document tool/version, limitations, hashes and custody"]
~~~

**Thứ tự quan trọng:** môi trường client thường phải được cấu hình **trước khi tạo session**, và trình duyệt có thể cần khởi động phiên mới. Một file key log được bật sau khi kết nối đã hình thành **không bảo đảm** chứa secrets của phiên trước.

### 16.3. Cấu hình key log ở máy lab

~~~bash
# MINH HỌA trên máy lab Linux/macOS có client hỗ trợ SSLKEYLOGFILE.
# Directory phải được tạo/bảo vệ theo chính sách của hệ thống test.
# KHÔNG chạy trên profile trình duyệt chứa tài khoản production.
export SSLKEYLOGFILE="$HOME/forensic-lab/session-keys.log"

# Sau khi đã cấp quyền file system, mở browser/test client tương thích
# trong một phiên lab riêng rồi truy cập endpoint HTTPS do mình quản lý.
# Cách browser dùng biến môi trường thay đổi theo OS/browser/version.
~~~

Trên Windows, một quy trình tương đương có thể thiết lập environment variable cho **process chạy trình duyệt lab**, nhưng chính sách enterprise, backend TLS hoặc sandbox có thể không hỗ trợ. Không tạo biến môi trường global cho mọi ứng dụng production hay sử dụng profile user thật.

### 16.4. Giải mã bản capture có khóa hợp lệ

Trong Wireshark có hỗ trợ:

1. Mở **working copy của PCAP**.
2. Vào phần Preferences → Protocols → TLS.
3. Chỉ định **(Pre)-Master-Secret log filename** trỏ tới file key log lab.
4. Phân tích lại packets nếu cần và xem `tls`/`http`/`http2` theo protocol/dissector support.
5. Ghi chính xác **TLS segment và traffic** nào có thể giải mã, file nào vẫn mã hóa.

Với tshark/Wireshark CLI (cấu hình tùy version):

~~~bash
# Chỉ đọc input files của lab; key log chứa bí mật phiên.
# KHÔNG đưa key log path/nội dung vào public ticket.
tshark -r capture-lab.pcapng \
  -o "tls.keylog_file:/restricted/forensic-lab/session-keys.log" \
  -Y "http || http2" \
  -T fields \
  -e frame.time_epoch \
  -e frame.number \
  -e _ws.col.Protocol \
  -e _ws.col.Info
~~~

Field names và `tls.keylog_file` preferences cần được **xác nhận trên version Wireshark/tshark đang dùng**. Với QUIC/HTTP3 phải có dissector/secret support tương ứng, không kỳ vọng `http2` filter hiển thị HTTP/3.

### 16.5. Một số nhãn NSS key log

~~~text
# Các nhãn dưới đây chỉ minh họa format, KHÔNG phải secret thật.
# CLIENT_RANDOM <client_random> <master_secret> (TLS phiên bản/cách dùng tương ứng)
# CLIENT_HANDSHAKE_TRAFFIC_SECRET <client_random> <secret>
# SERVER_HANDSHAKE_TRAFFIC_SECRET <client_random> <secret>
# CLIENT_TRAFFIC_SECRET_0 <client_random> <secret>
# SERVER_TRAFFIC_SECRET_0 <client_random> <secret>
~~~

**Không chia sẻ key log thật** chỉ để chứng minh kết quả. Tập tin này có thể cho phép giải mã traffic của phiên đã được capture nếu secrets tương ứng còn được lưu; cần bảo vệ tương đương **credential/secret có độ nhạy cao**.

### 16.6. Vì sao có key log nhưng vẫn không giải mã?

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra an toàn |
|---|---|---|
| Không có records trong key log | TLS stack/client không hỗ trợ, biến môi trường không tới process | Kiểm tra backend/version và quy trình lab |
| PCAP không có full handshake | Capture bắt đầu muộn, sensor drop, traffic qua gateway khác | Kiểm tra time range/packet loss/vantage |
| Khóa không tương ứng connection | Nhiều profiles/sessions, reused IP/port, key log sai run | Correlate connection start/random/secret labels |
| Client có proxy/CDN | Key log của session A không áp cho session B | Xác định TLS termination/re-encryption |
| HTTP/3/QUIC không hiện HTTP2 | Dissector/protocol filter không tương ứng | Kiểm tra QUIC/HTTP3 support và keys |
| Một chiều vẫn bị mã hóa | Thiếu traffic secret cho chiều/key epoch | Xem những secrets/packets có thật trong lab |
| Dữ liệu sau giải mã vẫn là ciphertext | Application tự mã hóa end-to-end trước TLS | Đánh giá application encryption layer, không tự giải tiếp |
| Decryption errors sau packet loss | Missing packet numbers/records/reassembly | Kiểm tra capture completeness, tool limitations |

### 16.7. Nếu không có thẩm quyền xuất khóa

**Không cố tìm đường lấy key từ memory của máy người khác hoặc TLS interception trái phép.** Chuyển sang **endpoint/server logs, authorized reverse proxy telemetry, EDR process evidence và network metadata**. Việc không thể giải mã là một giới hạn có thể chấp nhận được và phải nêu trung thực trong báo cáo.

## 17. TLS interception/decryption tại proxy: lợi ích và đánh đổi

Một số tổ chức sử dụng **enterprise TLS inspection proxy** trên lưu lượng được phép theo chính sách. Proxy **kết thúc một TLS session từ client** và tạo session khác tới server, nên có khả năng quan sát HTTP plaintext tại điểm kiểm soát đó.

### 17.1. Điều kiện vận hành hợp pháp và tin cậy

- Có **cơ sở pháp lý, chính sách được thông báo và authorization scope** cho traffic/nhóm người dùng được giám sát.
- Client trust store được quản lý đúng; không lén cài một root CA cho thiết bị cá nhân ngoài quyền.
- Không làm suy yếu TLS certificate validation tới upstream server.
- Có policy **không giải mã** dữ liệu nhạy cảm theo quy định; phân loại exemptions có kiểm toán.
- Proxy có access control, HSM/CA protection, key rotation, audit và retention phù hợp.
- Đánh giá certificate pinning, mTLS, ECH, QUIC và ứng dụng có yêu cầu end-to-end encryption.
- Có performance/availability capacity plan và fail behavior minh bạch.

### 17.2. Interception không phải “giải mã thụ động toàn bộ Internet”

~~~mermaid
flowchart LR
    C["Managed enterprise client"] -->|"TLS A"| P["Authorized inspection proxy"]
    P -->|"TLS B"| S["External HTTPS server"]
    P -. "Policy-controlled transaction logs" .-> E["Evidence store"]
    N["Passive sensor outside proxy"] -. "Ciphertext/metadata" .-> P
~~~

PCAP bên ngoài proxy vẫn thường chỉ thấy session A hoặc B dưới dạng ciphertext. **Plaintext visibility** có ở chính proxy nếu được cấu hình/logging theo scope; không tự áp cho VPN khác, mobile app pinned certificates, E2E-encrypted payload hoặc traffic đi vòng proxy.

### 17.3. Chống tác dụng phụ

Một CA inspection proxy bị chiếm có thể tạo rủi ro lớn cho **mọi client tin CA đó**. Giải pháp kiểm soát phải cân bằng khả năng phát hiện với **quyền riêng tư, trust chain, availability và tấn công qua điểm tập trung**. Không đề xuất “tắt pinning” hay “cài CA lạ” như bước chuẩn của điều tra số.

## 18. Bảo quản key logs và ciphertext như chứng cứ nhạy cảm

### 18.1. Ba loại artifact cần tách biệt

| Artifact | Nội dung | Mức nhạy cảm | Cách bảo quản |
|---|---|---|---|
| **Original encrypted PCAP** | Ciphertext, metadata, đôi khi plaintext handshake/protocol | Có thể chứa PII/network intelligence | Evidence master read-only/immutable khi khả thi, hash và restricted storage |
| **TLS session key log** | Secrets của một hoặc nhiều phiên trong phạm vi được thu | **Rất nhạy cảm**, có thể giải mã session tương ứng | Encryption, tách quyền, không gửi qua ticket/chat, destruction theo retention |
| **Decrypted working artifact** | HTTP content, headers, cookies, auth tokens, business data | Có thể **nhạy cảm hơn PCAP gốc** | Need-to-know access, redaction, audit, không gắn vào public dashboard |

Một session key log có thể làm **thay đổi mức độ nhạy cảm của cả bộ PCAP**. Kho lưu chứng cứ nên áp dụng quyền chặt như đang giữ thông tin xác thực, dù file log có vẻ chỉ là những chuỗi hex.

### 18.2. Chain of custody

**Chain of custody** ghi lại ai, khi nào, từ đâu, bằng cách gì đã thu, chuyển, lưu, xem và xử lý bằng chứng. Mẫu:

~~~yaml
case_id: NF-LAB-2026-010
evidence_id: TLS-KEYLOG-0002
source: authorized-test-client
collection_method: client-supported-key-log
authorization_reference: lab-approval-002
collector: responder-lab-01
collection_time_utc: pending
file_name: client-session-keys.log
byte_size: pending
sha256: pending
encryption: restricted-vault
retention: case-specific
related_pcap_evidence_id: PCAP-0001
working_copy_id: pending
access_control:
  - authorized-forensic-analyst-role
transfers: []
limitations:
  - may-cover-only-supported-client-sessions
~~~

Không điền dữ liệu giả vào phần `sha256`/byte size rồi coi là evidence thật; phải thu từ artifact thực. File key log nếu được **append liên tục khi client đang chạy**, hash có thể đổi; ghi rõ snapshot time và sealing process trước khi xác minh bản master.

### 18.3. Hash file chỉ chứng minh điều gì?

~~~bash
# Chỉ chạy trên evidence copy được phép đã đóng/niêm phong,
# trong môi trường phân tích hạn chế quyền.
sha256sum /evidence/working/capture-lab.pcapng
sha256sum /evidence/working/client-session-keys.log
~~~

SHA-256 giúp kiểm tra sự đồng nhất **bytes của bản đã hash**, không tự chứng minh dữ liệu ban đầu đến từ đúng thiết bị, đầy đủ hoặc không bị sửa **trước khi capture/export**. Provenance phải dựa asset identity, collector logs, event timestamps, tool version và cross-source corroboration.

### 18.4. Original, master và working copy

~~~text
Original sensor / source client
        |
        v
Evidence master (verified hash + restricted + preserve)
        |
        +-- Working copy 1: metadata-only analysis
        |
        +-- Working copy 2: controlled decryption
        |
        +-- Derived report: sanitized indicators and findings
~~~

**Không ghi đè original PCAP bằng một bản “đã giải mã”**. Nếu xuất decrypted HTTP objects hoặc filtered PCAP, phải tạo **derived evidence ID**, mô tả phương pháp, filter, những packets bị loại và quyền truy cập riêng.

### 18.5. Data minimization

Nhiều câu hỏi có thể trả lời chỉ bằng metadata và flow counts. Nếu chỉ cần chứng minh client kết nối đến destination lúc 03:04 UTC, **không nên mở toàn bộ cookies, Authorization headers và user data**. Ưu tiên mức dữ liệu thấp nhất đủ chứng minh giả thuyết, với legal/privacy approval khi cần.

## 19. Correlation: từ flow mã hóa đến đúng process, user và service

### 19.1. Vì sao một IP không đủ?

Một luồng network nhìn thấy:

~~~text
Sensor: FW-EGRESS-A
UTC: 2026-11-28T03:10:15Z
Post-NAT source: 198.51.100.7:51001
Destination: 203.0.113.60:443
Protocol: TCP/TLS
Transferred: 120 MiB outbound within observation window
~~~

Giả sử NAT gateway phục vụ **nhiều Pods và VMs**. Để xác định host nguồn, cần mapping tương ứng:

~~~text
Firewall/NAT record:
  pre-NAT IP:port   -> post-NAT IP:port
  start/end UTC and device/policy context

Kubernetes/cloud record:
  pre-NAT IP at event time -> Pod UID / NIC ID / VM instance ID

EDR/OS record:
  host and socket time -> PID/process/signature/user

Identity/application:
  session/token context -> actual actor/business action
~~~

Nếu thiếu NAT mapping hoặc process telemetry, báo cáo phải nói **“địa chỉ sau NAT có flow tới...”** thay vì gán chắc cho một nhân viên.

### 19.2. Ghép records theo khoảng thời gian, không chỉ bằng timestamp chính xác

Các nguồn có **clock skew, delayed log ingestion và sampling**. Một phép join đòi timestamp khớp tới mili giây có thể bỏ sót evidence. Dùng **bounded time window được giải thích**, sequence/event IDs và direction/ports cùng các nguồn độc lập để tăng độ tin cậy.

### 19.3. Định danh mỗi TLS session

Một endpoint có thể mở nhiều TCP sessions song song tới cùng server IP:443. Khi phân tích:

1. Tách **tcp.stream**, 5-tuple và thời gian bắt đầu/kết thúc.
2. Đối chiếu ClientHello/TLS handshake nếu capture đầy đủ.
3. Cẩn thận với TLS **session resumption**, HTTP/2 multiplexing, proxy pooling.
4. Với QUIC, dùng **connection IDs và session context** theo dissector, không chỉ UDP 5-tuple.
5. Chỉ gắn session key log cho **đúng traffic secrets**, tránh giải mã nhầm luồng.
6. Khi quy kết user, xác minh request application/session logs; HTTP connection không luôn tương ứng một user duy nhất.

### 19.4. Các dấu mốc trong một timeline tốt

~~~text
03:00:01Z  EDR process A started                     [host evidence]
03:00:03Z  DNS resolver answered domain D            [resolver evidence]
03:00:04Z  NAT translation created                   [network evidence]
03:00:05Z  TLS ClientHello observed                  [PCAP evidence]
03:00:05Z  Encrypted application data observed       [PCAP evidence]
03:00:09Z  Server audit: accepted upload request     [server evidence]
03:00:12Z  Firewall byte counters increased          [flow evidence]
03:00:40Z  Endpoint EDR containment requested        [EDR audit]
03:00:43Z  Egress network policy blocked new flows   [PEP log]
~~~

Đây là **timeline giả định**, không phải sự kiện đã xảy ra. Mỗi dòng trong báo cáo thực cần **source record ID, time confidence, device clock/offset và inference level**. Sự gần nhau về thời gian không tự chứng minh quan hệ nhân quả.

### 19.5. Đâu là bằng chứng upload đã thành công?

- **Network bytes out:** chỉ chứng minh sensor quan sát bytes đi qua, không chứng minh server đã ghi object.
- **TLS encrypted response:** có phản hồi nhưng chưa biết HTTP status/body nếu không giải mã.
- **Proxy/server application access log:** có thể ghi status, request ID, bytes_received, object path nếu được cấu hình.
- **Object storage audit:** có thể cung cấp operation success, object version/size và principal.
- **Data-loss prevention alert:** gợi ý nội dung/rule match, cần kiểm tra confidence, scope và false positives.

Muốn kết luận exfiltration cụ thể, cần **liên hệ asset, process, destination, successful operation và data classification**, nêu lỗ hổng bằng chứng nếu thiếu.

## 20. Phát hiện bất thường từ lưu lượng mã hóa mà không đọc nội dung

### 20.1. Xây baseline theo hành vi

Một baseline hữu ích gồm:

- Những destination domains/IP/ASNs phù hợp với approved services và update mechanisms.
- Flow duration, packet/byte distribution, upstream/downstream ratio.
- Periodicity, time-of-day, first-seen destinations, cross-region differences.
- DNS behavior theo resolver, DoH/DoT adoption nếu thuộc enterprise policy.
- TLS/QUIC handshake failures, version/ALPN changes, uncommon fingerprints trong bối cảnh.
- Process lineage, binary signer/hash, user session, host security posture.
- Security policy events: firewall deny, WAF block, proxy allow, VPN identity.

Không lấy baseline làm whitelist tuyệt đối: **malware có thể dùng CDN/legitimate SaaS**, còn phần mềm hợp lệ có thể thay domains/traffic pattern sau update.

### 20.2. Phân tích periodicity

Giả sử sensor quan sát 30 phiên TLS, bắt đầu cách nhau gần 60 giây trong 30 phút. Điều đó có thể giống một **beaconing pattern**, nhưng cũng có thể là:

- Monitoring heartbeat, device management check-in.
- Cloud SDK refresh, proxy health polling, software update.
- Browser background sync, analytics, endpoint protection agent.

Chỉ đánh giá nghi vấn cao khi có **process context, destination reputation với nguồn đáng tin, user/host behavior, thay đổi bất thường và bằng chứng bổ sung**.

### 20.3. Outbound-heavy và bất thường tải

Một host upload nhiều bytes trong 10 phút có thể đáng điều tra nếu:

- Host không có business reason để truyền dữ liệu ra vùng đó.
- Process mới/không ký mở kết nối sau một execution event đáng ngờ.
- Destination mới thuộc hạ tầng không có quan hệ nghiệp vụ.
- Object/API logs xác nhận data transfer có thành công và khớp sensitive data.
- Tương quan với account privilege change, data staging hoặc file access bất thường.

Nhưng **outbound bytes tăng một mình không đủ**. Kết nối backup, video conference, đồng bộ file hợp pháp hoặc container image push cũng có thể có lưu lượng lớn.

### 20.4. Detection rule phải dùng xác suất và chứng cứ

~~~yaml
# PSEUDOCODE POLICY-AS-INTENT, không triển khai nguyên văn.
rule: unusual-encrypted-egress-investigate
window: 15m
conditions:
  - first_seen_destination_for_asset
  - outbound_bytes_exceed_asset_baseline
  - process_not_in_approved_inventory
corroboration:
  - dns_or_proxy_resolution
  - cloud_nat_mapping_and_process_identity
  - endpoint_file_or_object_access_context
severity: analyst-triage-not-automatic-guilt
actions:
  - open-case-with-evidence-references
  - verify-asset-and-destination-ownership
  - preserve-external-network-and-identity-logs
  - escalate-containment-only-per-approved-playbook
~~~

Đây là mô hình **xếp ưu tiên điều tra**, không phải chữ ký chính xác của một malware family. Automated containment có thể gây gián đoạn; cần policy, mức độ chắc chắn và impact assessment.

### 20.5. Traffic analysis có giới hạn về quyền riêng tư

Ngay cả khi không giải mã, patterns lưu lượng đôi khi hé lộ hành vi cá nhân. Vì vậy áp dụng **purpose limitation, minimization, retention, transparency và access controls** theo chính sách/pháp luật. Không dùng các thuật toán đoán hành vi từ traffic shape để đưa ra nhận định cá nhân chắc chắn khi thiếu validation.

## 21. Case study 1 — HTTPS upload lớn bị nghi là exfiltration

### 21.1. Tình huống giả định

Một máy trạm của nhóm nghiên cứu có flow HTTPS outbound dài 12 phút tới một IP thuộc hạ tầng cloud/CDN chưa từng xuất hiện trong baseline của máy. Sensor egress nhận thấy **1,2 GiB network bytes từ client ra ngoài**. EDR ghi một process mới được khởi chạy gần cùng thời điểm. Cảnh báo tự động gắn nhãn **possible data exfiltration**.

~~~text
03:00:00Z  Process creation event on workstation      [EDR]
03:00:10Z  DNS lookup to a previously unseen domain   [resolver logs]
03:00:12Z  TLS ClientHello and handshake observed     [PCAP]
03:00:14Z  Outbound application-data records begin    [PCAP]
03:12:15Z  Flow ends, high outbound bytes recorded    [firewall]
03:15:00Z  SOC analyst opens investigation case       [case management]
~~~

Tất cả mốc, bytes và entity là **giả định phục vụ đào tạo**, không phải bằng chứng của một sự cố thực.

### 21.2. Điều gì được xác nhận ngay?

| Dữ liệu quan sát | Kết luận có thể hỗ trợ | Điều chưa biết |
|---|---|---|
| Firewall flow 1,2 GiB outbound | Có lượng bytes đi qua điểm đo theo semantics log | Có bao nhiêu application payload thực, có retransmissions? |
| TLS ClientHello | Client bắt đầu một TLS handshake, có metadata được quan sát | Đã gửi file nào qua HTTPS? |
| DNS query trước đó | Resolver ghi lookup tại thời điểm liên quan | Process đó chắc chắn dùng response DNS này? |
| EDR process mới | Host tạo process vào thời điểm gần session | Process này có thực sự sở hữu socket không? |
| Destination thuộc CDN | Traffic đi tới shared/cloud infrastructure | Có độc hại hay chỉ legitimate SaaS? |

**Không viết “đã đánh cắp 1,2 GiB tài liệu”** từ flow count. Đây chỉ là **nghi vấn upload lượng lớn** cần điều tra có định hướng.

### 21.3. Phương pháp điều tra

1. Ghi **host/agent/asset ID**, IP/MAC và thời gian phiên, xác minh NAT mappings.
2. Xác định đúng **PID/process image/hash/signature, parent process, user session** qua EDR.
3. Kiểm tra change/approved software inventory: backup client, storage sync, software updater có liên quan?
4. Xác minh DNS/HTTPS metadata ở phạm vi không bị ECH/DoH che; không dựa chỉ SNI/CDN IP.
5. Thu **proxy logs, server/cloud object storage audit** nếu hệ thống/đối tác thuộc quyền và logging hợp lệ.
6. Đối chiếu **application file activity** theo pháp lý/thẩm quyền, tránh tự mở dữ liệu cá nhân không liên quan.
7. Nếu có quyền truy cập server/app logs, xem **request outcome, content length, object key, user identity** trong scope được cho phép.
8. Đánh giá risk và quyết định **containment tại endpoint/network** theo playbook nếu nghi hoạt động vẫn tiếp diễn.
9. Ghi phân biệt `observed`, `inferred`, `confirmed` và những giả thuyết đã bác bỏ.

### 21.4. Hai kết quả có thể khác nhau

~~~text
Branch A — Legitimate explanation:
  EDR process matches approved backup sync client.
  Job ID corresponds to scheduled encrypted backup.
  Server audit shows an authorized backup object.
  Conclusion: high outbound encrypted traffic was expected.

Branch B — Suspicious explanation:
  Process hash/signature is unrecognized.
  Identity accessed sensitive local objects outside expected role.
  Server/object audit confirms upload to an unauthorized destination.
  Conclusion: probable or confirmed exfiltration based on combined evidence.
~~~

Nếu không có app/server evidence, báo cáo phải nói **“suspected encrypted egress with high outbound volume; exact content/outcome not established”** thay vì nâng mức chắc chắn.

### 21.5. Bài học

**Traffic metadata giúp phát hiện và khoanh vùng**, nhưng cần nguồn độc lập để gán actor và xác định dữ liệu. Dùng HTTPS không làm traffic tự động đáng tin hoặc đáng ngờ; **ngữ cảnh và bằng chứng** quyết định.

## 22. Case study 2 — Có PCAP TLS 1.3 nhưng không có khóa phiên

### 22.1. Bối cảnh giả định

Một nhóm IR có PCAP của một API nội bộ sử dụng TLS 1.3, từ 02:00–02:30 UTC. Họ muốn biết một request đã gọi `/admin/export` hay `/v1/health`. Sensor nằm **ngoài ingress gateway**, capture đầy đủ TCP handshake nhưng không có NSS session key log. Nhóm sở hữu public certificate và server private key tương ứng từ kho vận hành.

**Sai lầm dễ gặp:** “Chỉ cần nhập RSA private key của server vào Wireshark là mở được HTTPS.” Với TLS 1.3 điều đó không đúng theo cách RSA key transport cũ.

### 22.2. Trình tự xử lý đúng

~~~mermaid
flowchart TD
    PC["TLS 1.3 PCAP"] --> META["Read ClientHello/flow metadata"]
    META --> ASK{"Need exact HTTP path?"}
    ASK -- "Không" --> REPORT["Report metadata + limitations"]
    ASK -- "Có" --> LOG["Obtain authorized ingress/app access logs"]
    LOG --> COVER{"Logs sufficiently complete?"}
    COVER -- "Có" --> MATCH["Correlate request ID/time/identity"]
    COVER -- "Không" --> K{"Authorized matching session secrets available?"}
    K -- "Có" --> DEC["Decrypt working copy in controlled lab"]
    K -- "Không" --> GAP["Document evidence gap"]
    MATCH --> REPORT
    DEC --> REPORT
    GAP --> REPORT
~~~

### 22.3. Thực tế của PFS

- Server certificate public key **không mã hóa HTTP records trực tiếp**.
- TLS 1.3 sử dụng traffic secrets xuất phát từ key schedule; server certificate private key **không tái tạo** session secrets từ PCAP.
- Nếu một **test client** được tổ chức kiểm soát đã tạo session key log cho đúng phiên, analyzer có thể giải mã theo khả năng hỗ trợ.
- Không có session secrets không có nghĩa phải dùng “brute force TLS”; ưu tiên **ingress access logs, app traces, identity/audit**.
- Nếu reverse proxy kết thúc TLS rồi nối vào backend, request logs của proxy có thể cung cấp path/status mà không đụng raw cryptographic keys.

### 22.4. Trường hợp log thiếu

Giả sử ingress logs chỉ ghi request count mà **không có method/path**, và session keys không được thu. Kết luận hợp lý:

~~~text
Confirmed:
  Client IP 192.0.2.42 opened TLS 1.3 connection to ingress.
  Application data was exchanged during observed window.
  No reliable plaintext request path was observed in PCAP.

Not established:
  Whether /admin/export was called.
  Whether export action succeeded.
  Which object, if any, was transferred.

Next evidence needed:
  Server/application audit, authorized client telemetry,
  request tracing, object storage access logs, IAM events.
~~~

Không “giải mã bằng đoán” dựa vào packet lengths mà khẳng định path cụ thể. Nếu nguồn khác cũng thiếu, ghi **unresolved finding**.

### 22.5. Cải tiến kiến trúc

- Đảm bảo ingress/API có **privacy-aware structured access logs** với request ID và đủ method/route/status.
- Liên kết client/service identity, timestamp UTC và TLS termination point.
- Retention đủ cho IR, bảo vệ log khỏi bị attacker xóa.
- Không log Authorization headers, cookies, bearer tokens hay user data tràn lan.
- Với lab/tests do tổ chức sở hữu, có thể tạo **controlled client session key logs** theo change/approval để kiểm tra dissector, không duy trì key log rộng của mọi user.

### 22.6. Bài học

**Forward secrecy là thuộc tính bảo mật nên giữ lại**, không phải trở ngại cần tắt. Giải pháp điều tra bền vững là **forensic readiness và telemetry đúng điểm**, không làm yếu TLS production.

## 23. Case study 3 — QUIC và DoH làm thiếu DNS/HTTP logs

### 23.1. Bối cảnh giả định

Đội network phát hiện UDP/443 traffic tới một IP CDN tăng trên nhiều laptops sau một bản cập nhật browser. Đồng thời DNS resolver nội bộ thấy lượng queries giảm 30%. Một analyst đưa ra giả thuyết **“mọi máy đã dùng DNS tunneling hoặc malware chuyển sang kết nối bí mật”**.

Những quan sát ban đầu **không đủ** cho kết luận đó:

- HTTP/3 adoption có thể làm tỷ lệ traffic QUIC tăng.
- Browser/OS có thể bật DoH theo policy hoặc sử dụng cache nhiều hơn.
- Resolver logs có thể bị thiếu do collector/sampling.
- UDP/443 không đồng nghĩa DoH; QUIC có thể chở nhiều loại ứng dụng.

### 23.2. Phân rã giả thuyết

| Giả thuyết | Bằng chứng cần | Phép kiểm tra có trách nhiệm |
|---|---|---|
| Browser update bật HTTP/3 | Browser/version rollout, ALPN/protocol metrics | So baseline trước/sau update |
| DoH được cấu hình hợp lệ | Managed browser/OS resolver policy | Đọc cấu hình quản lý và logs, không ép giải mã |
| DNS collector bị thiếu dữ liệu | Scrape/ingest/retention metrics | Kiểm tra coverage, lag, sampling |
| Malicious encrypted DNS traffic | Endpoint process evidence, domains/identities, unusual behavior | Correlate EDR và policy, không suy chỉ theo port |
| Legitimate CDN traffic tăng | App inventory, user journey/load, CDN IP/hostname context | Xác nhận service ownership |
| UDP fallback ảnh hưởng connectivity | Firewall/QUIC support, HTTP2 comparison | Controlled test trên endpoint thuộc quyền |

### 23.3. Tối thiểu hóa truy cập nội dung

Để xác minh browser DoH/HTTP3 rollout, **không cần giải mã tất cả HTTPS payload của người dùng**. Có thể dùng managed client configuration, software inventory, OS/browser protocol metrics, synthetic tests và egress logs theo phạm vi.

Nếu một số endpoints còn có process behavior bất thường, tạo case riêng với evidence, không gắn toàn bộ người dùng vào incident chỉ từ quy mô traffic tăng.

### 23.4. Bài học

**Mất visibility một phần không đồng nghĩa đã xảy ra tấn công.** Khi giao thức mã hóa thay đổi, nhiệm vụ của đội an ninh là điều chỉnh **điểm đo, dữ liệu từ endpoint và tiêu chí phát hiện**, đồng thời tôn trọng quyền riêng tư.

## 24. Troubleshooting dữ liệu mã hóa và kết quả giải mã

### 24.1. Bảng triệu chứng và nguyên nhân cần kiểm chứng

| Triệu chứng | Giả thuyết | Cách kiểm tra an toàn |
|---|---|---|
| Wireshark chỉ hiện `Application Data` | TLS/QUIC payload mã hóa bình thường | Kiểm tra protocol/session/có khóa hợp lệ không |
| Có certificate server nhưng không giải mã TLS 1.3 | Private key server không tái tạo traffic secrets | Tìm authorized session key log hoặc app/proxy logs |
| TLS 1.2 vẫn không giải mã bằng RSA private key | Handshake ECDHE, incomplete capture, wrong key | Xác định cipher suite/key exchange; không hạ TLS |
| Key log rỗng | Client/TLS backend không hỗ trợ, env chưa tới process | Kiểm tra client build/profile và thời điểm bật logging |
| Key log có entries nhưng request vẫn mã hóa | Sai phiên, sai direction/epoch, proxy, missing packets | Correlate secrets/handshake/time, tool version |
| HTTP/2 không hiển thị sau khi “giải mã” | Analyzer chưa cấu hình ALPN/dissector, incomplete data | Kiểm tra protocol negotiation và dissector |
| Có QUIC nhưng không nhìn thấy `http2` | HTTP/3 sử dụng QUIC, không phải HTTP/2 | Dùng QUIC/HTTP3 dissector/filter được hỗ trợ |
| UDP/443 không được nhận dạng là QUIC | Protocol khác, nonstandard traffic, dissector/version | Xem signature/handshake/endpoint telemetry |
| QUIC Initial có thể đọc nhưng content vẫn mã hóa | Initial protection khác 1-RTT/application keys | Không suy decrypt Initial là decrypt HTTP3 |
| SNI biến mất hoặc thành cover name | ECH, no SNI, QUIC client mode hoặc incomplete capture | Check ECH/client/app/proxy logs theo quyền |
| DNS query logs biến mất | DoH/DoT, cache, split DNS, collector outage | Client resolver config, coverage metrics |
| Fingerprint JA3 thay đổi toàn fleet | Browser update, GREASE/order, TLS library | So change timeline, TLS/endpoint versions |
| Một JA3 khớp malware TI nhưng app hợp lệ | Shared TLS library, false positive | Process/signer/destination context, threat intel provenance |
| PCAP chỉ thấy outer VPN endpoints | Sensor ở ngoài IPsec/WireGuard tunnel | Tìm inner-flow gateway logs, authorized inside sensor |
| Flow bytes không khớp application bytes | Headers, retransmissions, sampling, NAT, two-way capture | Ghi measurement semantics, vantage/units |
| Server không ghi request nhưng PCAP có TLS | TLS trước server, ingress/CDN, log gap | Correlate termination point, edge/proxy logs |
| Một IP ánh xạ nhiều hosts | NAT/DHCP/VPN/CDN/shared resolver | Thu mapping đúng 5-tuple và UTC range |
| tcp.stream không ổn định qua reboot/capture | Index là ID local của file/dissector | Không dùng tcp.stream như global identity |
| Decrypted artifact có nhiều request trong một stream | HTTP/2 multiplexing hoặc keepalive | Dùng stream/request IDs, app logs |
| Dữ liệu sau TLS vẫn trông ngẫu nhiên | App encryption/compression/custom protocol | Kiểm tra app contract trước khi suy |
| PCAP mở không đủ handshake | Sensor bắt đầu muộn, packet drops, snaplen cắt | Capture metadata, logs, handshake availability |
| Chỉ thấy một hướng traffic | Asymmetric routing, SPAN config, filter | Network topology, counters, second vantage |
| TLS handshake errors tăng sau deploy | Certificate/SAN, SNI, trust, time, TLS policy | Client/server TLS logs, certificate inventory |
| Time trong PCAP lệch EDR | Sensor NTP/clock skew, timezone, ingest delay | Giữ original UTC offset, normalize trên copy |
| Hash artifact khác sau truyền | File còn append, copy lỗi, sai version | So size, snapshot/sealing, custody history |
| Packet timestamps khác flow logs | Flow aggregation/start/end semantics, delayed export | So source clocks/window và sampling |
| Tách HTTP object không thấy file cụ thể | TLS vẫn mã hóa, app compress/chunk/multipart | Server/application audit và transaction ID |
| IDS báo packet “suspicious” dù TLS không giải mã | Rule match metadata/TLS handshake hoặc heuristic | Xem rule field/detection method, không giả định payload inspect |
| Proxy có plaintext nhưng outside PCAP vẫn mã hóa | TLS termination/re-encryption tách hai phiên | Mô hình hóa TLS A/B và vị trí capture |
| Evidence phân tích có bearer token | Decrypted content chứa credentials | Dừng phát tán, restrict/redact/access audit theo quy trình |

### 24.2. Trình tự xử lý khi không thể giải mã

1. **Xác định protocol thật:** TLS/TCP, QUIC, SSH, VPN hay ứng dụng tự mã hóa?
2. **Kiểm tra PCAP completeness:** capture window, handshake, packets bị drop, snaplen.
3. **Xác định vị trí sensor:** trước hay sau proxy/NAT/VPN/TLS termination?
4. **Phân loại key exchange và version:** TLS 1.2 RSA legacy hay (EC)DHE/TLS 1.3?
5. **Xác nhận secret source có hợp pháp không:** controlled client key log, authorized app/proxy logs.
6. **Kiểm tra key log coverage:** session, direction, time/epoch, client/TLS backend.
7. **Kiểm tra tool/dissector:** Wireshark/tshark version, field filters, HTTP2/3 support.
8. **Nếu vẫn không giải mã:** tiếp tục metadata, endpoint, IAM, DNS, flow và application logs.
9. **Ghi giới hạn:** chưa biết content/response, mức chắc chắn attribution và nguyên nhân.
10. **Bảo quản kết quả:** hash master, custody và sanitized reporting.

### 24.3. Mã lỗi không phải kết luận về attacker

TLS alert `handshake_failure` có thể do **cipher/version mismatch hoặc certificate issue**, không chứng minh intrusion. TCP RST có thể do app close, firewall policy, idle timeout, middlebox hoặc network error. Một QUIC connection migration có thể là hành vi mobile/roaming bình thường. Mọi quyết định bảo mật phải có context và evidence từ nhiều nguồn.

## 25. Ma trận 40 kiểm thử điều tra traffic đã mã hóa

Ma trận dưới đây là các **kiểm thử đề xuất cho lab và đánh giá quy trình có thẩm quyền**, không phải kết quả đã chạy. Những test liên quan keys/HTTP content chỉ thực hiện trên **client và endpoint do nhóm sở hữu**, sử dụng dữ liệu test không nhạy cảm. Trường hợp không có thẩm quyền giải mã, **PASS** có thể là báo cáo chính xác giới hạn và tìm nguồn thay thế, chứ không phải buộc phải lấy plaintext.

| Test ID | Nội dung kiểm chứng | Phương pháp/nguồn | Tiêu chí PASS |
|---|---|---|---|
| **CAP-01** | Đúng asset và sensor location | Asset inventory + PCAP metadata | Source/vantage/time rõ ràng |
| **CAP-02** | Capture có đủ handshake | Xem first packets và time range | Có hoặc ghi rõ phần bị thiếu |
| **CAP-03** | Snaplen/packet drops được kiểm tra | `capinfos`, sensor counters | Không kết luận quá mức khi capture thiếu |
| **CAP-04** | Flow hướng RX/TX rõ | TCP/UDP conversations + topology | Không đếm hai lần qua tunnel/NAT |
| **CAP-05** | Packet vs flow semantics tách biệt | So PCAP và cloud flow logs | Biết sampling/aggregation/overhead |
| **CAP-06** | IPv4/IPv6 đều được xét | Display filters + interface inventory | Không bỏ sót IPv6 traffic |
| **TLS-01** | Nhận đúng TLS 1.2 vs TLS 1.3 | ClientHello/ServerHello, dissector | Giao thức và handshake version được ghi |
| **TLS-02** | TLS 1.3 không bị suy decrypt từ cert key | Kiểm thử trên PCAP lab | Không khẳng định private key server đủ |
| **TLS-03** | TLS 1.2 ECDHE không nhầm RSA key exchange | Phân tích cipher suite | Giải thích đúng forward secrecy |
| **TLS-04** | Key log thuộc đúng controlled session | Client-controlled lab test | Decrypt đúng session, không trộn sessions |
| **TLS-05** | Thiếu key log được xử lý đúng | Test trong lab không bật log | Metadata-only, không kết luận HTTP content |
| **TLS-06** | Phân biệt TLS A/B sau proxy | Topology và proxy/server logs | Key của segment A không áp segment B |
| **TLS-07** | Certificate identity không suy từ IP/SNI | Client/server TLS records hợp lệ | Hostname/certificate validation được phân biệt |
| **TLS-08** | Resumption/PSK/0-RTT được cân nhắc | Controlled lab resumption test | Không suy full handshake luôn có |
| **TLS-09** | Decrypted HTTP content không phát tán | Key log/working copy access review | Raw token/body được bảo vệ và redacted |
| **ENC-01** | QUIC được phân biệt với TCP/TLS | UDP/443 samples + QUIC dissector | Không tìm `tcp.stream` cho QUIC |
| **ENC-02** | QUIC Initial khác application secrets | QUIC lab capture | Không kết luận Initial decrypt = HTTP3 decrypt |
| **ENC-03** | ECH inner hostname được bảo vệ | ECH-capable controlled test nếu hỗ trợ | Không coi outer SNI là site thực |
| **ENC-04** | DoH/DoT queries không nhìn từ middlebox | Controlled resolver traffic | Không tự suy QNAME từ ciphertext |
| **ENC-05** | DoH vs DNS logging gaps | Browser/resolver configuration | Vắng log có coverage explanation |
| **ENC-06** | SSH không bị suy command từ packet sizes | SSH lab + authorized OS audit | Command evidence chỉ từ nguồn có nội dung |
| **ENC-07** | VPN outer/inner địa chỉ phân biệt | Tunnel topology + inside/outside logs | Không gán outer gateway IP cho individual host |
| **ENC-08** | JA3/JA4 không là unique identity | Browser version rollout/fingerprint | Có false-positive review và corroboration |
| **COR-01** | NAT source mapping đúng | Pre/post NAT 5-tuple + UTC | Không gán nhầm host từ public IP |
| **COR-02** | DHCP/Pod IP reuse được xử lý | Lease/Pod UID creation timestamps | Không quy kết endpoint bằng IP hiện tại |
| **COR-03** | Process attribution có đủ thời gian | EDR socket/PID/process creation | Không suy từ PID có thể reuse |
| **COR-04** | DNS/flow correlation đúng | Resolver logs, UTC, cache context | Không gắn hostname chắc chắn khi không có dữ liệu |
| **COR-05** | Application success khác network bytes | Server audit + flow evidence | Không coi uploaded bytes = confirmed exfil |
| **COR-06** | Missing request log không thành “không xảy ra” | Log coverage/ingest/retention | Nêu đúng blind spot và uncertainty |
| **COR-07** | Timeline đa nguồn nhất quán | EDR, FW, proxy, cloud events | Giữ original timestamps + uncertainty |
| **EVD-01** | PCAP master được bảo quản | Evidence vault, hash, permissions | Master không bị sửa ngoài quy trình |
| **EVD-02** | Key log được bảo vệ như secret | Encryption, access audit, retention | Không lộ secrets ngoài forensic role |
| **EVD-03** | Working copy tách bản gốc | Master/workcopy evidence IDs | Derived outputs dẫn nguồn |
| **EVD-04** | Chain of custody đầy đủ | Collector/transfers/UTC/receipts | Mọi lần bàn giao truy vết được |
| **EVD-05** | Hash và byte size được xác minh | SHA-256 before/after transfer | Bản đã chuyển không đổi hoặc có giải trình |
| **EVD-06** | Privacy/data minimization | Decrypted report review | Không chứa credentials/PII ngoài scope |
| **IR-01** | Chọn đúng evidence khi không thể decrypt | Tabletop encrypted incident | Endpoint/server logs được tìm có căn cứ |
| **IR-02** | Suspected exfil không bị khẳng định quá mức | Case study review | Separates observed/inferred/confirmed |
| **IR-03** | Có quyết định containment phù hợp | Approved IR decision tree | Không đợi decrypt nếu đang mất dữ liệu |
| **IR-04** | Báo cáo có reproducibility/limitations | Independent analyst review | Method/version/coverage/unknowns rõ |

### 25.1. Kết luận bài test thế nào?

**PASS:** dùng đúng tool/protocol/vantage, evidence có nguồn và time, bảo vệ data theo phạm vi, đáp ứng điều kiện cần chứng minh. Với test “TLS 1.3 không thể giải mã từ private key”, một kết luận đúng về giới hạn **là PASS của kiến thức và quy trình**.

**FAIL:** gán content chưa nhìn thấy, ghi nhầm domain từ ECH outer SNI, mở rộng thu thập ngoài quyền, lộ key log hoặc sai source attribution do NAT/DHCP.

**INCONCLUSIVE:** PCAP mất handshake, sai point of capture, no matching session secrets, không có logs để đối chiếu, clock skew chưa xác định hoặc chưa biết tool hỗ trợ protocol. Không biến sự thiếu evidence thành “không có xâm nhập”.

### 25.2. Test record mẫu

~~~yaml
test_id: TLS-05
environment: approved-encrypted-traffic-lab
time_utc: pending
case_id: NF-LAB-2026-010
protocol: TLS1.3-over-TCP
sensor_location: outside-of-lab-server
client_identity: test-client-01
key_log_present: false
expected:
  read_visible_handshake_metadata: true
  plaintext_http_available: false
  no_private_key_bruteforce_or_weakened_tls: true
  record_limitations: true
evidence_required:
  - original-pcap-hash-and-size
  - sensor-location-and-time-window
  - handshake-version-analysis
  - analyzer-version-and-display-filters
  - log-source-correlation-plan
result: pending-execution
~~~

Đây là **biểu mẫu học tập**, không phải kết quả của một thực nghiệm đã diễn ra. Không điền `result: pass` trước khi kiểm chứng.

## 26. Runbook điều tra dữ liệu mạng đã mã hóa

Runbook dành cho nhóm **SOC/CSIRT/DFIR, network/security operations và application/platform owners**. Các bước phải được điều chỉnh theo sự cố thật, chính sách pháp lý/quyền riêng tư và **điểm nào tổ chức kiểm soát**. Không bắt buộc giải mã để có báo cáo hữu ích.

### Bước 1 — Nêu câu hỏi điều tra thật cụ thể

Tránh câu hỏi mơ hồ “hãy giải mã PCAP”. Thay bằng:

- Một endpoint có kết nối đến destination bị nghi vấn trong cửa sổ 10 phút không?
- Có bao nhiêu data bytes theo **điểm capture** và hướng đi?
- Đúng **process/identity** nào mở kết nối?
- Website/domain hoặc service nào có thể xác minh, bằng nguồn nào?
- HTTP method/route có sẵn trong **app/proxy logs** không?
- Dữ liệu thực sự được upload/download và ghi thành công không?
- Traffic có bị chặn, TLS handshake thất bại hay ứng dụng trả lỗi?

Mỗi câu hỏi cần đánh dấu **chỉ metadata đủ** hay **cần nội dung/khóa có thẩm quyền**. Cách này giảm thu thập quá mức.

### Bước 2 — Kiểm tra authorization và privacy scope

~~~text
Incident ID and investigator role:      documented
Assets and network segments allowed:   documented
Purpose and time range:                 limited
Required approval for TLS key logs:     documented
Expected personal/secret data exposure: assessed
Evidence storage and retention:         approved
Oversight/escalation contacts:          identified
~~~

Không nhập khóa bí mật hoặc load decrypted PCAP lên dịch vụ online không được tổ chức phê duyệt. Trong một tổ chức nhiều tenant, quyền quản trị sensor **không tự cấp quyền đọc mọi nội dung của các tenant**.

### Bước 3 — Bảo quản bản gốc

1. Ghi source sensor, interface, location/topology, UTC time range, acquisition method.
2. Copy PCAP vào evidence repository có restriction theo quyền; hash và ghi file size.
3. Bảo toàn **original**, tạo working copy riêng cho filter, parse hoặc decryption.
4. Bảo quản DNS, firewall/NAT, VPN, IdP, EDR, cloud, proxy/app logs trong cùng incident time window.
5. Ghi sampling, packet loss, snaplen, collector lag và clock offset; không “sửa” bản gốc cho vừa lý thuyết.

### Bước 4 — Phân loại protocol và điểm mã hóa

~~~mermaid
flowchart TD
    A["Preserved encrypted capture"] --> B["Identify transport and tunnel"]
    B --> TLS{"TLS TCP?"}
    B --> QUIC{"QUIC UDP?"}
    B --> VPN{"SSH/VPN/other?"}
    TLS -- "Có" --> TM["TLS handshake/metadata + PFS assessment"]
    QUIC -- "Có" --> QM["QUIC version/IDs/packet protection"]
    VPN -- "Có" --> VM["Outer/inner mapping and gateway logs"]
    TM --> COR["Correlate with endpoint, server, identity, DNS"]
    QM --> COR
    VM --> COR
~~~

Nếu có nhiều lớp mã hóa (WireGuard bên ngoài, HTTPS bên trong; TLS A tới CDN rồi TLS B tới backend), xác định **mỗi layer và key domain** trước khi xin thêm evidence.

### Bước 5 — Dựng timeline chỉ từ metadata

- Phân tách sessions theo 5-tuple/timestamp và TCP stream local ID; QUIC có connection ID logic riêng.
- Lấy first/last observed packet, bytes/packets theo hướng và packet loss indicators.
- Ghi visible handshake fields **với giới hạn ECH/TLS1.3/QUIC**.
- Correlate DNS/NAT/IdP/EDR để gắn source asset và process.
- So software rollout/change history và user activity authorized context.
- Tạo giả thuyết có thể kiểm chứng, không gắn nhãn “đã đánh cắp” chỉ từ upload bytes.

### Bước 6 — Quyết định có cần giải mã hay không

~~~mermaid
flowchart TD
    C["Investigation question not yet answered"] --> Q{"Can endpoint/server logs answer it?"}
    Q -- "Có" --> L["Collect approved structured logs"]
    Q -- "Không" --> K{"Matching session secrets available lawfully?"}
    K -- "Có" --> D["Controlled decryption of working copy"]
    K -- "Không" --> N["Document limitation and alternatives"]
    D --> P["Protect/redact decrypted results"]
    L --> P
    N --> P
    P --> R["Evidence-based findings"]
~~~

**Không hạ bảo mật TLS, gỡ certificate pinning trái phép hoặc dùng token/key ngoài scope** để đạt mục đích. Nếu có active threat đang gây hại, containment theo IR playbook không phải chờ quá trình giải mã hoàn thành.

### Bước 7 — Nếu đã có key log được phép

1. Xác minh key log source/client, phạm vi sessions và authorization reference.
2. Bảo quản key log **separate restricted storage**, ghi hash/size/chain of custody.
3. Dùng working copy của PCAP và Wireshark/tshark version đã ghi.
4. Nạp session key log theo analyzer preferences; quan sát chỉ **traffic được giải mã thật**.
5. Không suy từ một session sang mọi sessions/các TLS segments khác.
6. Chỉ xuất **trường dữ liệu cần cho câu hỏi**, redact credentials/PII theo chính sách.
7. Nếu dữ liệu sau TLS còn được app mã hóa, ghi rõ encryption layer tiếp theo.
8. Xác nhận với **application/server audit** khi có thể và ghi confidence.

### Bước 8 — Viết báo cáo và bàn giao

Một báo cáo tốt cần:

| Phần | Yêu cầu |
|---|---|
| **Question and scope** | Mục tiêu, assets, data/time scope, approval |
| **Evidence inventory** | IDs, source, hashes, size, timestamps, custody |
| **Observation point** | PCAP ở đâu, trước/sau NAT/VPN/CDN/TLS termination |
| **Protocol assessment** | TLS/QUIC/SSH/VPN version, metadata visible, encryption limit |
| **Timeline** | Original UTC times, clock offsets, confidence |
| **Correlation** | EDR process, IP mapping, DNS, identity, app audit |
| **Decryption status** | Không giải mã / một phần / đã giải mã có thẩm quyền; đúng session nào |
| **Findings** | Observed facts, inferences, alternatives, uncertainty |
| **Response recommendation** | Containment/revocation/patch/monitoring theo policy |
| **Privacy and retention** | Tài liệu nhạy cảm đã bảo vệ, retention và access owners |

### Bước 9 — Kiểm tra lại và cải tiến forensic readiness

Đánh giá sau sự cố:

- Endpoint, proxy và application logs có đủ request IDs/actor mà **không log raw tokens**?
- DNS/VPN/flow logs có retention đủ cho thời gian phát hiện?
- Có biết chính xác NAT/Cloud/Kubernetes identity mapping theo event time?
- QUIC/DoH/ECH visibility gap đã được **ghi trong threat model**?
- Công cụ Wireshark/tshark/collector có version và testcase kiểm chứng riêng?
- Hash/chain-of-custody, encryption, secure sharing và incident evidence permissions có hiệu quả?
- Các detection rules encrypted traffic có false positives và feedback loop?
- Khi một protocol thay đổi, có kế hoạch nâng instrumentation thay vì hạ encryption security?

**Forensic readiness** được xây từ trước: log có cấu trúc, time sync, endpoint identities và các điểm đo hợp pháp. Đó là cách giữ khả năng điều tra trong khi vẫn bảo vệ bí mật đường truyền cho người dùng.

## 27. Bài tập vận dụng và đáp án gợi ý

### Bài 1 — Ciphertext hay plaintext?

Một PCAP có nhiều TLS Application Data records. Analyst khẳng định đã nhìn thấy nội dung JSON bên trong dù chưa có giải mã hoặc proxy/app logs. Nhận định đúng không?

*Đáp án:* không. PCAP chỉ cho thấy records mã hóa và metadata trong phạm vi capture; nội dung JSON chưa được xác minh.

### Bài 2 — TLS 1.3 và server private key

Nhóm IR có TLS 1.3 PCAP, public certificate và private key server. Có thể giải mã tất cả HTTPS request bằng RSA private key như TLS 1.2 RSA key exchange cũ không?

*Đáp án:* không. TLS 1.3 sử dụng traffic secrets từ key schedule; private key certificate không tự tái tạo session secrets. Cần matching authorized session keys hoặc logs tại endpoint/proxy.

### Bài 3 — Forward secrecy

Vì sao server private key bị tiết lộ sau một năm không tự làm toàn bộ những phiên TLS 1.3 trước đó có thể giải mã?

*Gợi ý:* với ephemeral key agreement/forward secrecy thích hợp, traffic secrets không suy ra từ private key chứng chỉ dài hạn; nhưng nếu endpoint lưu keys/traffic logs thì bí mật có thể vẫn bị ảnh hưởng.

### Bài 4 — RSA key exchange legacy

Đối với một phiên TLS 1.2 sử dụng RSA key exchange cũ, có thể giải mã thụ động từ PCAP và server private key không?

*Gợi ý:* **có thể** trong những điều kiện đúng, gồm key exchange, complete handshake, đúng key và analyzer support; không khái quát cho TLS 1.2 ECDHE/DHE.

### Bài 5 — TLS A/B

Client nối TLS đến CDN, CDN tạo TLS mới tới ingress. Key log của client có tự giải mã traffic giữa CDN và ingress không?

*Đáp án:* không. Hai sessions có secrets khác nhau. Phải định danh segment và evidence source cho từng session.

### Bài 6 — SNI và ECH

Một QUIC ClientHello cho thấy outer SNI `public-cover.example.test`. Có thể kết luận người dùng thực truy cập website đó không?

*Đáp án:* không. ECH có thể bảo vệ inner ClientHello và hostname thực; outer SNI không là user action đã xác thực.

### Bài 7 — DNS encrypted resolver

DNS logs nội bộ thiếu truy vấn khi browser bật DoH. Có thể coi browser không phân giải domain hoặc cố tình exfiltration không?

*Gợi ý:* không. Kiểm tra browser/MDM resolver policy, cache, traffic tới resolver, logging coverage và process context.

### Bài 8 — QUIC Initial

Một Wireshark analyzer đọc được QUIC Initial packets. Nó có tự đọc toàn bộ HTTP/3 requests mà không có matching secrets không?

*Đáp án:* không. Initial protection khác 1-RTT application traffic protection.

### Bài 9 — SSH host private key

Có SSH host private key và PCAP của phiên shell. Có thể giải mã lệnh người dùng đã gõ trong SSH hiện đại không?

*Gợi ý:* không chỉ bằng host key. Cần authorized OS auditing, bastion/session recording hoặc endpoint forensic evidence.

### Bài 10 — IPsec outer/inner flow

Một sensor Internet thấy ESP flow giữa hai VPN gateways. Có thể xác định workstation bên trong nào truy cập database không?

*Gợi ý:* không trực tiếp. Thu gateway inner-flow logs, VPN session/user identity, DHCP/NAT và application audit theo thời điểm.

### Bài 11 — JA3 fingerprint

Một JA3 hash khớp với một dòng threat intelligence về malware. Có thể tự động xóa máy hoặc kết luận máy đã nhiễm không?

*Đáp án:* không. Fingerprint không duy nhất, cần corroborate bằng process, signer, behavior, destination và TI provenance.

### Bài 12 — Throughput so với nội dung

Firewall ghi nhận 600 MiB outbound tới IP mới. Có thể báo đã lấy cắp 600 MiB tài liệu mật không?

*Đáp án:* không. Đó là lượng traffic theo điểm đo; cần xác nhận application bytes, object/data type, transfer success, actor và policy.

### Bài 13 — NAT mapping

Hai VMs dùng chung public NAT IP. Làm sao phân biệt VM nguồn của một TLS connection?

*Gợi ý:* sử dụng pre/post NAT source port mapping, UTC time window, cloud NIC/instance ID và endpoint logs.

### Bài 14 — DHCP/Pod IP reuse

Pod `A` bị xóa lúc 10:00, Pod `B` nhận lại IP đó lúc 10:03; flow lúc 09:58 thuộc ai?

*Gợi ý:* cần Pod UID/creation-deletion events, CNI flow logs và timestamps. Không quy flow cho Pod B chỉ vì B giữ IP hiện tại.

### Bài 15 — Packet loss trong capture

Wireshark giải mã một số packets nhưng bỏ sót những records sau một thời điểm. Có thể do đâu ngoài key sai?

*Gợi ý:* packets thiếu, capture drop, snaplen truncation, QUIC packet number context, key update/epoch, tool limitations.

### Bài 16 — Key log và tính bí mật

Tại sao không được đưa session key log từ browser vào ticket công khai, kể cả khi PCAP đã có trên ticket?

*Đáp án:* matching session secrets có thể biến ciphertext trong PCAP thành plaintext có credentials/PII. Cần restricted encrypted storage và custody.

### Bài 17 — Hash

File PCAP có SHA-256 đúng sau khi copy. Điều này có chứng minh sensor chắc chắn không bỏ lỡ packets hoặc bị attacker sửa trước khi capture không?

*Đáp án:* không. Hash kiểm tra bản bytes sau khi thu; provenance và completeness cần metadata, sensor health, packet drop counters và nguồn khác.

### Bài 18 — Display filter

Khác biệt giữa `host 192.0.2.42 and port 443` và `ip.addr == 192.0.2.42 && tls` trong Wireshark là gì?

*Gợi ý:* biểu thức đầu là dạng capture/BPF filter, có thể loại packets lúc thu; biểu thức sau là display filter chỉ lọc phần hiển thị từ capture đã có.

### Bài 19 — TTFB/error không nhìn thấy

Client hoàn thành TLS handshake, nhưng không có server application access log. Có đủ để nói client không gửi HTTP request không?

*Đáp án:* không. Có thể request bị chặn ở ingress, logs không bật/thiếu, traffic tới region khác, hoặc capture chỉ có một phần. Kiểm tra đường đi và telemetry coverage.

### Bài 20 — Bất thường periodicity

Một endpoint tạo kết nối TLS đúng 60 giây/lần. Nêu ít nhất ba giải thích hợp lệ và ba nguồn evidence để phân biệt với C2.

*Gợi ý:* heartbeat EDR, sync agent, cloud API polling; dùng EDR process lineage, approved software inventory, destination ownership/proxy logs, change schedule và identity/context.

### Bài 21 — Traffic qua CDN

PCAP thấy IP CDN và không có SNI rõ. Vì sao không nên báo chính xác URL đã truy cập?

*Gợi ý:* shared IP hosting, ECH, TLS encrypted HTTP Host/path và routing/connection reuse; cần proxy/app/browser logs được ủy quyền.

### Bài 22 — Incident response

Một host đang exfiltration nghiêm trọng. Nhóm phân tích muốn giữ kết nối thêm một giờ để cố lấy key log. Bạn xử lý thế nào?

*Gợi ý:* phối hợp incident commander, ưu tiên ngăn hại đang diễn ra theo playbook; preservation ở EDR/network/identity, không trì hoãn containment vô hạn chỉ để có plaintext.

### Bài 23 — Báo cáo uncertainty

Một PCAP và firewall logs chỉ chứng minh **attempted encrypted connection**, không có server outcome. Hãy viết hai câu kết luận: một được phép và một không đủ bằng chứng.

*Gợi ý:* được phép: “Sensor quan sát kết nối TLS tới 203.0.113.50:443 trong cửa sổ X”. Không đủ: “Server đã nhận và lưu file dữ liệu Y” nếu không có application/object logs.

### Bài 24 — Thiết kế forensic readiness

Xây bộ log tối thiểu cho hệ thống **browser → CDN/WAF → ingress → microservices → cloud database** để điều tra TLS 1.3 mà không phải lưu session keys của toàn bộ người dùng.

*Gợi ý:* CDN request IDs/edge results, ingress route/status/latency, application authn/authorization events, service-to-service trace IDs, cloud DB audit, EDR process/socket context, IdP events, network flow and NAT mapping, UTC/time sync, privacy-safe retention.

### Bài 25 — Thiết kế tổng hợp

Cho một doanh nghiệp có **DoH browsers, QUIC/HTTP3, SSH bastion, IPsec site-to-site, endpoint EDR và cloud VPC flow logs**, thiết kế:

- **Bốn luồng quan sát được** không cần giải mã, kèm giới hạn của từng luồng.
- **Ba tình huống cần application/endpoint logs** để biết user action.
- **Hai trường hợp có thể giải mã hợp lệ** và cách bảo vệ secrets.
- **Năm negative tests** để ngăn suy luận quá mức, gắn nhầm IP, lộ key logs và vượt scope.

*Gợi ý:* metadata TLS/QUIC, VPN outer flows, firewall denied connections và approved DNS resolver logs là bốn nguồn không cần ciphertext decryption; URL/object/action cần logs; lab session keys và proxy termination có thẩm quyền là hai cơ chế có điều kiện; phải kiểm thử ECH outer-name, NAT shared IP, incomplete PCAP, unauthorized key access và attacker/beacon false positives.

## 28. Checklist làm việc an toàn và chính xác với dữ liệu mã hóa

### 28.1. Phạm vi, quyền và câu hỏi điều tra

- [ ] Có **incident/case ID, owner, investigator identity và authorization** cho assets/time range.
- [ ] Đã nêu câu hỏi: cần **flow metadata, process identity hay HTTP/business content**?
- [ ] Không dùng “cần giải mã” như một mục tiêu tự thân; cân nhắc **ít dữ liệu nhất đủ trả lời**.
- [ ] Đánh giá **PII, secrets, compliance, multi-tenant boundaries và privacy notice** trước khi thu.
- [ ] Có legal/privacy approval khi cần xử lý plaintext hoặc bật TLS inspection.
- [ ] Không thu khóa/session traffic của tài khoản/thiết bị ngoài quyền được giao.
- [ ] Không đề xuất hạ TLS/SSH/VPN, bỏ pinning hoặc thêm root CA trái phép.

### 28.2. Capture và protocol awareness

- [ ] Biết rõ **sensor location**, trước/sau NAT, VPN, CDN, proxy và TLS termination.
- [ ] Đã ghi capture start/end UTC, interface, link direction, filter, snaplen và packet drops.
- [ ] Đã phân biệt **TCP/TLS 1.2/1.3, UDP/QUIC, SSH, IPsec/WireGuard và DNS encrypted protocols**.
- [ ] Không mặc định mọi HTTPS là TCP/443 hoặc mọi UDP/443 là QUIC.
- [ ] Đã kiểm tra **TLS key exchange/PFS** trước khi đánh giá khả năng giải mã.
- [ ] Hiểu server certificate/private key **không đủ** cho TLS 1.3/modern ECDHE PCAP decryption.
- [ ] Không coi QUIC Initial parsing là đã giải mã toàn HTTP/3.
- [ ] Đã xem **TLS resumption/0-RTT, sessions, key epochs** nếu liên quan.
- [ ] Đã xét **ECH outer SNI vs inner hostname**, no-SNI và shared CDN IP.
- [ ] Đã phân biệt DoH/DoT/DoQ với DNS plaintext và kiểm tra resolver logging coverage.
- [ ] Trong VPN, phân biệt **outer vs inner flows**, gateway identity và endpoint identity.
- [ ] Biết `tcp.stream`/quic dissector streams là **IDs trong tập tin/công cụ**, không là global identity.
- [ ] Đã xét **IPv4/IPv6, QUIC migration, proxy pooling, HTTP/2 multiplexing** và asymmetric routing.

### 28.3. Nguồn chứng cứ và suy luận

- [ ] Đã đối chiếu **EDR process/socket, DNS, firewall/NAT, VPN/IdP, proxy, cloud và application logs** khi có quyền.
- [ ] Mapping IP/port thuộc **đúng thời điểm**; có DHCP/NAT/Pod UID/VM ID nếu cần.
- [ ] Không gắn **shared public IP, CDN IP, SNI, JA3/JA4** thành user identity chắc chắn.
- [ ] Đã kiểm tra **packet loss, retransmission, flow sampling, collector outage và retention gaps**.
- [ ] Không kết luận HTTP URL, command SSH, tài liệu hoặc credential từ ciphertext đơn thuần.
- [ ] Không coi **outbound bytes** là số bytes đã exfiltrate hoặc chứng minh server đã lưu object.
- [ ] Không coi DNS log vắng là user không truy cập domain hoặc có DNS tunneling.
- [ ] Không coi periodic connections/fingerprint mới là malware khi thiếu bối cảnh.
- [ ] Tách **observed facts, inferred behavior, confirmed outcomes và unresolved evidence gaps**.
- [ ] Có bằng chứng độc lập khi mô tả **tác động người dùng, account abuse, content transfer hoặc exfil**.
- [ ] Ghi rõ nguồn threat intelligence, rule version, false positives và mức độ chắc chắn.

### 28.4. Key logs và decryption

- [ ] Nếu cần giải mã, đã xác nhận **matching authorized session secrets** thật sự tồn tại.
- [ ] Lab key log chỉ bật trên **test client/endpoint được sở hữu và được phép**, không phải production browsing.
- [ ] Ghi browser/TLS backend và Wireshark/tshark versions, trường hợp resumption/QUIC support.
- [ ] Không dùng server RSA private key để thử giải mã TLS 1.3 khi thiếu session secrets.
- [ ] Key log được lưu **mã hóa, tách quyền, audited access và có retention/destruction policy**.
- [ ] Không đăng key log, cookies, Authorization headers, bearer tokens lên chat/ticket công khai.
- [ ] **Original PCAP, key log, decrypted working copy và derived report** có IDs/quyền riêng.
- [ ] Decryption output được giới hạn ở những fields cần thiết, redaction và review dữ liệu nhạy cảm.
- [ ] Không khẳng định giải mã được mọi session khi chỉ giải mã được một TLS segment.
- [ ] Khi không có keys/authorization, dùng **metadata và endpoint/server evidence**, báo rõ giới hạn.

### 28.5. Tính toàn vẹn, timeline và báo cáo

- [ ] Evidence có **source, time, acquisition method/tool version, byte size, hash và evidence ID**.
- [ ] Có chain of custody cho mọi transfer, access và derived artifact.
- [ ] Master được bảo quản, phân tích trên working copy; không sửa raw PCAP cho phù hợp giả thuyết.
- [ ] Giữ timestamps gốc, normalization UTC, clock offset và mức bất định.
- [ ] Mỗi báo cáo nêu **sensor vantage, NAT/termination context, encryption/protocol limitations**.
- [ ] Các kết luận nhạy cảm về dữ liệu/nhân sự có nguồn chứng minh, scope và confidence.
- [ ] Có disposition cho evidence, retention, restricted access và post-incident review.
- [ ] Monitoring/forensic readiness được cải tiến nhưng **không làm suy yếu mã hóa đang bảo vệ người dùng**.

**Kết luận:** với dữ liệu mạng được mã hóa, nhiệm vụ điều tra không phải “mở bằng được ciphertext”. Hướng tiếp cận vững chắc là **xác định chính xác điều nhìn thấy, ghép metadata với endpoint/network/application evidence và chỉ giải mã ở điểm có thẩm quyền với đúng session secrets**. TLS 1.3, QUIC, SSH, VPN, DoH/DoT và ECH làm thay đổi trường quan sát nhưng **không xóa mọi dấu vết**. Một báo cáo có giá trị khi nó bảo vệ quyền riêng tư, duy trì chain of custody và phân biệt được **flow đã quan sát**, **hành vi suy luận** và **nội dung/giao dịch thật sự đã xác minh**.

### Tài liệu tham khảo và đọc thêm

- [NIST SP 800-86 — Guide to Integrating Forensic Techniques into Incident Response](https://csrc.nist.gov/pubs/sp/800/86/final): acquisition, collection, preservation, analysis và reporting.
- [NIST SP 800-61 Rev. 3 — Incident Response Recommendations and Considerations for Cybersecurity Risk Management](https://csrc.nist.gov/pubs/sp/800/61/r3/final): ứng phó sự cố, điều phối và quản trị rủi ro.
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final): log collection, retention và integrity.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): handshake, key schedule, traffic secrets và record protection.
- [RFC 5246 — TLS 1.2](https://www.rfc-editor.org/rfc/rfc5246): historical TLS 1.2 handshake và cipher suites.
- [RFC 9000 — QUIC: A UDP-Based Multiplexed and Secure Transport](https://www.rfc-editor.org/rfc/rfc9000): QUIC connection IDs, packet structure, migration.
- [RFC 9001 — Using TLS to Secure QUIC](https://www.rfc-editor.org/rfc/rfc9001): QUIC key protection và TLS 1.3 integration.
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114): HTTP semantics over QUIC.
- [RFC 8484 — DNS Queries over HTTPS](https://www.rfc-editor.org/rfc/rfc8484): DoH.
- [RFC 7858 — Specification for DNS over TLS](https://www.rfc-editor.org/rfc/rfc7858): DoT.
- [RFC 9250 — DNS over Dedicated QUIC Connections](https://www.rfc-editor.org/rfc/rfc9250): DoQ.
- [RFC 4253 — SSH Transport Layer Protocol](https://www.rfc-editor.org/rfc/rfc4253): SSH transport/security mechanisms.
- [RFC 7296 — Internet Key Exchange Protocol Version 2](https://www.rfc-editor.org/rfc/rfc7296): IPsec IKEv2 control plane.
- [RFC 4303 — IP Encapsulating Security Payload](https://www.rfc-editor.org/rfc/rfc4303): ESP packet and tunnel protection.
- [WireGuard — Protocol & Cryptography](https://www.wireguard.com/protocol/): WireGuard tunnel and handshake overview.
- [RFC 7011 — IP Flow Information Export](https://www.rfc-editor.org/rfc/rfc7011): IPFIX flow data.
- [Wireshark User's Guide](https://www.wireshark.org/docs/wsug_html_chunked/): Wireshark display filters, statistics, protocol analysis.
- [Wireshark Wiki — TLS](https://wiki.wireshark.org/TLS): TLS dissection và key-log-based decryption.
- [Wireshark — tshark manual](https://www.wireshark.org/docs/man-pages/tshark.html): command-line offline packet analysis.
- [Salesforce — JA3](https://github.com/salesforce/ja3): phương pháp fingerprint TLS ClientHello và giới hạn khi sử dụng.
- [MITRE ATT&CK — Exfiltration Over Web Service](https://attack.mitre.org/techniques/T1567/): mô hình hóa hành vi exfiltration, không thay bằng chứng sự cố thực.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): cấu trúc logs, dữ liệu nhạy cảm và giới hạn lưu trữ.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): bảo vệ session secrets, keys và token-related artifacts.
