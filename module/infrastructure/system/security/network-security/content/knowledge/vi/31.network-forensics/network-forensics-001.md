# Nguồn bằng chứng của network forensics

## 1. Network forensics cần những loại bằng chứng nào?

**Network forensics** (điều tra số trên mạng) là quá trình thu thập, bảo toàn, phân tích và liên hệ dữ liệu về hoạt động truyền thông mạng để tái dựng sự kiện, xác định phạm vi ảnh hưởng và kiểm chứng các giả thuyết về sự cố hoặc hành vi an ninh. Trong mô-đun **SECURITY_NETWORK_SECURITY**, hoạt động này sử dụng kiến thức về phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, lưu lượng không dây và hạ tầng đám mây để giải thích **ai giao tiếp với ai, qua tuyến nào, lúc nào và có điều gì thực sự xảy ra ở mỗi điểm quan sát**.

Ví dụ, hệ thống phát hiện một máy trạm kết nối định kỳ tới IP lạ và truyền nhiều dữ liệu. Dữ liệu lưu lượng có thể giúp trả lời:

1. Máy trạm hoặc workload nào tạo kết nối, thuộc người dùng và phân đoạn mạng nào?
2. Tên miền nào đã được phân giải, IP nào được sử dụng tại thời điểm đó?
3. Kết nối có vượt firewall/VPN/proxy không, được cho phép hay bị chặn?
4. Có bao nhiêu kết nối, byte và gói đã được quan sát; chiều truyền nào chiếm ưu thế?
5. Có dấu hiệu chuyển dữ liệu bất thường không, hay đây là cập nhật/phụ thuộc hợp lệ?
6. Có bằng chứng từ endpoint và ứng dụng để xác định tiến trình, tài khoản hoặc hành động liên quan không?

Không một nguồn duy nhất luôn trả lời được tất cả. **PCAP** có thể lưu packet tại một điểm quan sát, **flow record** tóm tắt kết nối, **firewall log** mô tả quyết định policy, **DNS log** liên hệ tên miền với truy vấn, **endpoint log** liên hệ kết nối với tiến trình. Kết quả điều tra vững chắc đến từ sự **đối chiếu nhiều nguồn độc lập** cùng thời gian, đi kèm những giới hạn đã biết.

**Phân biệt ba khái niệm:**

- **Dữ liệu gốc:** packet, bản ghi sự kiện, cấu hình hoặc snapshot được thu từ nguồn có xác định.
- **Hiện vật/bản sao bảo toàn:** tệp hoặc tập bản ghi đã lưu cùng nguồn gốc, thời gian, phương pháp thu, hash và lịch sử tiếp cận.
- **Kết luận phân tích:** nhận định rút ra sau khi kiểm tra dữ liệu; có thể thay đổi khi xuất hiện bằng chứng mới.

Một cảnh báo IDS, một bản ghi IP trong SIEM hoặc một đồ thị tăng traffic là **dấu hiệu mở đầu**, chưa đủ để khẳng định máy đã bị xâm nhập hay dữ liệu đã bị đánh cắp.

## 2. Bức tranh tổng thể các nguồn bằng chứng

Có thể chia nguồn theo vị trí được tạo ra và độ chi tiết:

| Nhóm nguồn | Ví dụ | Trả lời tốt nhất | Giới hạn điển hình |
| --- | --- | --- | --- |
| **Packet-level** | PCAP/PCAPNG tại TAP, SPAN, host, NDR | Cờ TCP, thứ tự packet, header và nội dung không mã hóa tại điểm bắt | Thiếu packet, mã hóa, dung lượng lớn |
| **Flow-level** | NetFlow, IPFIX, sFlow, VPC flow logs | Cặp endpoint, protocol, volume, hướng và khoảng thời gian | Tổng hợp/sampling; thường không có payload |
| **Thiết bị kiểm soát** | Firewall, router ACL, NAT, VPN, WAF | Quyết định allow/deny, session, route, tunnel, mapping | Chỉ mô tả phạm vi của thiết bị và chính sách ghi log |
| **Phát hiện an ninh** | IDS/IPS, NDR, Zeek logs, SIEM | Sự kiện, protocol metadata, chữ ký/hành vi nghi vấn | Alert có thể là false positive; sensor có thể thiếu một chiều |
| **Hạ tầng tên và danh tính mạng** | DNS, DHCP, IPAM, RADIUS, 802.1X, NAC | Tên miền, IP được cấp, MAC, tài khoản và cổng truy cập | Mapping biến động theo thời gian; shared IP/NAT |
| **Trung gian ứng dụng** | Web proxy, CDN, reverse proxy, API gateway, load balancer | URL/route, request ID, upstream, HTTP status, latency | Có thể che mất client gốc, sửa request hoặc không ghi payload |
| **Endpoint và dịch vụ** | EDR, audit, web/app logs, process/socket telemetry | Tiến trình/tài khoản phát sinh kết nối, hành vi ứng dụng | Phụ thuộc cấu hình, quyền và tình trạng endpoint |
| **Cloud/container** | Cloud flow/security logs, load balancer logs, Kubernetes/CNI | VPC/subnet/NIC, security policy, pod/service/namespace | Tài sản ngắn hạn, log trễ/tổng hợp, nhiều lớp NAT/overlay |
| **Trạng thái và thay đổi cấu hình** | Route/ARP/neighbor, firewall rule, config audit, IaC, change record | Đường đi dự kiến và những gì đã thay đổi | Snapshot hiện tại không luôn phản ánh lúc sự cố |

Một nguồn có thể thuộc nhiều nhóm. Ví dụ Zeek phân tích packet để tạo các log ở mức kết nối/giao thức; kết quả Zeek không phải bản sao toàn bộ packet gốc. SIEM tập trung nhiều nguồn nhưng **không tự biến bản ghi tổng hợp thành bằng chứng có độ chi tiết cao hơn nguồn gốc**.

### 2.1. Sơ đồ điểm tạo chứng cứ

~~~mermaid
flowchart LR
    C[Client / Endpoint] -->|DNS, TCP, UDP| F[Firewall / VPN / NAT]
    F --> P[CDN / WAF / Proxy / LB]
    P --> S[Server / Workload]
    C -.-> E[EDR, DHCP, DNS, NAC]
    F -.-> N[Firewall, Flow, VPN Logs]
    P -.-> L[Access, WAF, LB Logs]
    S -.-> A[Application, Host, Container Logs]
    F -.-> PC[PCAP / NDR Sensors]
    P -.-> PC
    E --> X[Kho bằng chứng]
    N --> X
    L --> X
    A --> X
    PC --> X
    X --> Y[Timeline, phân tích, báo cáo]
~~~

Sơ đồ mang tính khái niệm: sensor chỉ quan sát lưu lượng đúng giao diện/nhánh được cấu hình. Một mạng có CDN, split VPN, nhiều route hoặc service mesh có thể có các đường đi khác nhau cho từng request.

## 3. PCAP và packet-level evidence

### 3.1. PCAP cung cấp gì?

Tệp **PCAP** hoặc **PCAPNG** lưu các packet đã được cảm biến quan sát và thường kèm timestamp, độ dài packet; PCAPNG có khả năng lưu thêm thông tin interface và metadata thu thập. Đây là nguồn đặc biệt hữu ích khi cần kiểm chứng:

- TCP three-way handshake: SYN, SYN-ACK, ACK; đóng kết nối FIN/RST.
- Thứ tự gói, sequence/ACK, retransmission, receive window và các dấu hiệu packet loss.
- ICMP lỗi đích, Path MTU Discovery, packet bị fragmentation hoặc phản hồi không mong đợi.
- DNS, DHCP, ARP, ICMPv6 Neighbor Discovery trong phạm vi nhìn thấy và không mã hóa.
- TLS/QUIC handshake metadata còn hiển thị, thời gian và kích thước các bản ghi đã mã hóa.
- Giao thức plaintext mà việc thu thập payload được cấp quyền.

Một đoạn dữ liệu có thể đọc ở mức gói:

~~~text
2026-11-28T03:12:10.001Z  10.10.4.22:50214 -> 10.20.8.10:443  TCP SYN
2026-11-28T03:12:10.012Z  10.20.8.10:443 -> 10.10.4.22:50214  TCP SYN,ACK
2026-11-28T03:12:10.013Z  10.10.4.22:50214 -> 10.20.8.10:443  TCP ACK
2026-11-28T03:12:10.042Z  Client -> Server                    TLS ClientHello
~~~

Các dòng trên chỉ mô tả **mẫu minh họa**, chưa cho biết handshake TLS đã hoàn thành hay ứng dụng gửi request thành công. Muốn đánh giá tình trạng thật cần capture đủ hai chiều và kiểm tra các packet tiếp theo.

### 3.2. Vị trí bắt quyết định điều gì được thấy

| Điểm bắt | Thế mạnh | Cần kiểm tra |
| --- | --- | --- |
| Máy client | Những packet host gửi/nhận tại interface đang bắt | DNS qua resolver nào, NIC offload, VPN client, local proxy |
| Máy server | Có packet tới server và response phát ra không | Reverse proxy phía trước, container namespace, host firewall |
| Hai phía firewall | So sánh packet ingress/egress, NAT, ACL | Cổng đúng, hướng, sampling và đồng hồ |
| TAP/SPAN | Quan sát thụ động trên đoạn mạng vật lý | Mirror quá tải, thiếu chiều, VLAN/interface cấu hình |
| Điểm trong VPN | Có thể thấy inner traffic sau giải mã | Vị trí relative với tunnel, quyền thu thập |
| Điểm ngoài VPN | Thấy outer tunnel và metadata | Payload inner thường được mã hóa |
| Cloud traffic mirror | Quan sát traffic của resource được hỗ trợ | Giới hạn loại interface, encapsulation, phạm vi cloud |
| Pod/node/service mesh | Tách traffic workload, sidecar và overlay | Interface/veth/namespace nào thực sự có flow |

**Không thấy packet không đồng nghĩa packet chưa tồn tại trên đường truyền.** Có thể đã đặt sai interface, filter quá hẹp, packet đi qua route khác hoặc công cụ capture bị drop.

### 3.3. Những giới hạn phải ghi nhận

- **Mã hóa:** TLS, SSH, IPsec và QUIC che nội dung ứng dụng. PCAP không tự giải mã HTTPS chỉ vì có tệp gói tin. Một phần metadata TLS cũng có thể được che bởi ECH.
- **Snaplen:** thu 96 hoặc 160 byte đầu mỗi packet giúp giảm dữ liệu nhưng có thể cắt trường cần phân tích hoặc packet encapsulated.
- **Offloading:** GRO/GSO/TSO/LRO và checksum offload có thể làm packet trong host capture không giống packet trên dây; cảnh báo "bad checksum" có thể là hiện tượng quan sát.
- **Sensor loss:** capture throughput, disk I/O, SPAN oversubscription hoặc buffer có thể gây thiếu packet.
- **Asymmetric routing:** một sensor có thể chỉ nhìn một chiều; dữ liệu sequence/ACK không đầy đủ.
- **Thời gian:** timestamp và timestamp precision khác nhau giữa sensor; cần kiểm tra đồng bộ giờ.

Khi viết kết luận, phân biệt **"không quan sát thấy SYN-ACK tại client trong 10 giây"** với **"server không gửi SYN-ACK"**. Mệnh đề thứ hai cần thêm chứng cứ ở phía server hoặc các điểm trung gian.

## 4. Flow records: NetFlow, IPFIX, sFlow và cloud flow logs

Một **flow** thường mô tả luồng giao tiếp bằng các trường như giao thức, source/destination IP, port, start/end time, packet/byte count, interface và các thuộc tính mở rộng tùy exporter. Flow record phù hợp cho điều tra trên phạm vi hàng nghìn thiết bị và thời gian dài hơn PCAP.

Ví dụ bản ghi khái niệm:

~~~json
{
  "start_utc": "2026-11-28T03:10:00Z",
  "end_utc": "2026-11-28T03:11:00Z",
  "src_ip": "10.10.4.22",
  "src_port": 50214,
  "dst_ip": "10.20.8.10",
  "dst_port": 443,
  "protocol": 6,
  "packets": 140,
  "bytes": 124580,
  "exporter": "edge-router-01"
}
~~~

Đây là bản ghi **minh họa**, không phải schema chuẩn chung cho mọi NetFlow/IPFIX exporter.

### 4.1. Khi nào flow evidence hữu ích?

Flow giúp dựng **communication graph** để tìm endpoint lạ, tần suất kết nối, xu hướng volume, đường egress, phạm vi host liên hệ một đích, và các kết nối trước/sau thời điểm cảnh báo. Dữ liệu này thường ít tốn dung lượng hơn full PCAP.

| Công nghệ | Đặc điểm cần nhớ |
| --- | --- |
| **NetFlow** | Các version và cấu hình exporter khác nhau về trường dữ liệu, timeout và sampling |
| **IPFIX** | Mô hình mở rộng thông qua information elements/templates; xem schema exporter thực tế |
| **sFlow** | Thường dùng sampling packet/counter; không mặc định có đầy đủ mọi flow |
| **Cloud flow logs** | Dữ liệu do dịch vụ cloud cung cấp ở phạm vi resource; có thể tổng hợp, trễ hoặc thiếu payload |

Các trường **bytes** và **packets** có thể là tổng số ghi nhận, giá trị được lấy mẫu hoặc đã chuẩn hóa tùy exporter. Record flow cũng có thể bị chia thành nhiều phần do **active timeout**, **inactive timeout**, rollover hoặc thay đổi trạng thái. Trước khi cộng tổng dữ liệu trong một cuộc điều tra, phải hiểu cơ chế tạo bản ghi và chống đếm trùng.

**Flow log ACCEPT** thường mô tả quyết định hoặc trạng thái tại điểm thu log của nhà cung cấp, không chứng minh request đã đến ứng dụng hay response về client. **Không có flow** cũng chưa chứng minh không có kết nối nếu log bị sampling, cấu hình thiếu coverage hoặc đang trễ.

### 4.2. Phân biệt lưu lượng với nội dung

Nếu flow log cho biết host A truyền 5 GB tới IP B, có thể ghi nhận **lượng dữ liệu mạng được quan sát**. Chưa thể kết luận 5 GB tài liệu mật bị lộ, vì flow không mô tả chính xác nội dung payload, có thể có dữ liệu hợp lệ hoặc retransmission. Muốn đánh giá dữ liệu nào bị truy cập, cần thêm proxy/app logs, DLP, endpoint file activity hoặc nguồn nghiệp vụ được cấp quyền.

## 5. Firewall, ACL, NAT, VPN và log thiết bị mạng

### 5.1. Firewall và ACL

Log firewall có thể bao gồm timestamp, action allow/deny, rule ID, source/destination zone, interface, original tuple, translated tuple, session duration và byte counters. Nó trả lời **thiết bị đã xử lý policy với flow nào**.

Ví dụ:

~~~text
time=2026-11-28T03:12:10Z
device=fw-seg-01 action=deny rule=R-214
src=10.10.4.22:50214 dst=10.20.8.10:443 proto=tcp
src_zone=USERS dst_zone=APP ingress=eth1
~~~

Đây là bản ghi mô phỏng. Cần xác minh log được phát ở thời điểm tạo session, khi kết thúc session hay khi match từng packet; các sản phẩm khác nhau có ngữ nghĩa khác nhau.

Một rule "allow" tại firewall A không chứng minh firewall B, host firewall hoặc network policy của Kubernetes cũng cho phép. Một alert "deny" khớp địa chỉ chưa chứng minh chính packet ấy bị chặn nếu timestamp, NAT mapping hoặc retry chưa được đối chiếu.

### 5.2. NAT và session/connection tracking

NAT khiến cùng một flow có tuple khác nhau tại hai phía thiết bị:

~~~text
Trước NAT:  10.10.4.22:50214 -> 203.0.113.10:443 TCP
Sau NAT:   198.51.100.7:62001 -> 203.0.113.10:443 TCP
~~~

Để liên hệ activity với tài sản cụ thể, cần **original tuple, translated tuple, start/end timestamp, protocol và thiết bị NAT**. Public IP đơn lẻ có thể đại diện cho hàng nghìn máy; port có thể được dùng lại. Nếu mapping đã hết hạn, việc tái dựng có thể chỉ đạt mức xác suất thấp và phải nêu rõ giới hạn.

### 5.3. VPN và thiết bị mạng

**VPN logs** hữu ích cho việc xác định peer, địa chỉ tunnel, người dùng hoặc certificate được xác thực, trạng thái Security Association, kết nối/rekey, bytes/counters, lỗi negotiation và route được phân phối. Với VPN split tunnel, một phần traffic có thể không qua gateway doanh nghiệp.

**Router/switch logs** và telemetry bổ sung thông tin về route adjacency, BGP/OSPF events, interface flap, errors/drops, VLAN/VRF, MAC address table, ARP/Neighbor Discovery, port counters và thay đổi cấu hình. Một switch log xác nhận MAC xuất hiện trên cổng vào thời điểm nhất định chưa tự xác định người đang sử dụng máy đó.

**Configuration audit / change records** có vai trò riêng: giải thích firewall policy, route, ACL hoặc VPN profile **đã thay đổi khi nào và bởi ai**. Snapshot cấu hình hiện tại cần đi kèm lịch sử thay đổi, vì một route đang tồn tại bây giờ có thể chưa tồn tại tại thời điểm sự cố.

## 6. IDS/IPS, NDR và các log giao thức

**IDS** phát hiện dấu hiệu dựa trên packet, protocol hoặc hành vi mà sensor nhìn thấy. **IPS** có thể vừa phát hiện vừa thực thi block/drop tùy cấu hình. **NDR** có thể kết hợp packet, flow và phân tích hành vi để phát hiện các mẫu bất thường.

Những trường hữu ích khi bảo toàn alert gồm:

- Rule/signature ID, tên và phiên bản rule.
- Timestamp, sensor ID, interface, direction và vùng mạng.
- Source/destination tuple và trạng thái liên quan tới NAT.
- Severity, confidence và action: alert, drop, reject hoặc block.
- Packet reference, flow/session ID, raw event và enrichment đã áp dụng.

**Cần phân biệt "alert" với "khẳng định tấn công thành công".** Một cảnh báo quét cổng có thể là công cụ vận hành hợp lệ, một kết nối TCP bất thường có thể do client retry, và một signature match có thể là false positive. Kiểm tra packet/flow và endpoint context trước khi nâng mức kết luận.

### 6.1. Log từ bộ phân tích giao thức như Zeek

Zeek có thể tạo nhiều loại log, chẳng hạn:

| Log/nhóm dữ liệu | Thông tin thường cần | Lưu ý |
| --- | --- | --- |
| **conn** | Connection identifiers, thời gian, địa chỉ/port, byte, trạng thái | State suy ra từ dữ liệu sensor thấy; có thể thiếu một chiều |
| **dns** | Query, type, answer, response code | Không thấy nội dung DNS mã hóa nếu sensor ở ngoài điểm giải mã |
| **http** | Host, URI, method, status khi có thể phân tích | Chỉ giải mã HTTP plaintext hoặc luồng có khả năng phân tích thích hợp |
| **ssl/tls** | Phiên TLS và một phần metadata handshake | ECH và phiên bản TLS mới có thể che thông tin |
| **files** | Metadata về đối tượng truyền tải được nhận diện | Không phải mọi dữ liệu đều được trích xuất; cần chính sách lưu trữ |
| **notice** | Các sự kiện được engine/rule đánh dấu | Notice là đầu mối phân tích, chưa phải kết luận |

Các trường, tên file và khả năng quan sát phụ thuộc **phiên bản, cấu hình analyzer và gói script**. Dữ liệu Zeek được suy ra từ lưu lượng sensor nhận được, có thể mất context khi capture loss hoặc khi traffic mã hóa.

## 7. DNS, DHCP, IPAM và ánh xạ danh tính tài sản

Một IP hiếm khi tự nó xác định chắc chắn người, máy và tiến trình. Trong điều tra số, **khả năng ánh xạ đúng tài sản vào đúng thời điểm** quyết định giá trị của hàng loạt flow record.

### 7.1. DNS: tên miền mà hệ thống đã hỏi

DNS logs có thể cho biết client, resolver, **QNAME**, record type, response code, response IP và timestamp. Các câu hỏi cần xác minh:

- DNS query đến từ client hay từ resolver trung gian?
- Bản ghi A/AAAA/CNAME nào đã trả về, TTL là bao nhiêu?
- Có split-horizon DNS, CDN, cache hoặc DNS search suffix không?
- Host thực sự kết nối IP nào sau khi phân giải?

**Một DNS lookup không chứng minh có HTTP connection**, và một HTTP connection không bắt buộc đi kèm query DNS mới nếu client đã có cache. Nếu dùng DoH/DoT, sensor mạng thụ động bên ngoài kết nối mã hóa có thể không thấy tên miền; cần log tại resolver/endpoint được cấp quyền.

### 7.2. DHCP và IPAM: IP thuộc máy nào?

DHCP lease records hữu ích để nối **IP ↔ MAC/client identifier ↔ thời điểm lease**. Kết hợp IPAM, inventory và event cấu hình giúp xác định subnet, VLAN và chủ sở hữu dự kiến. Khi có NAT, vẫn cần session mapping để truy ra thiết bị thực.

**Không lấy trạng thái DHCP hiện tại để gán một IP trong log tuần trước.** Lease có thể hết hạn, thiết bị khác nhận lại IP hoặc MAC bị thay đổi/giả mạo. Kết quả nên chỉ ra bằng chứng lịch sử và mức độ chắc chắn.

### 7.3. NAC, RADIUS, Wi-Fi controller

Trong mạng không dây và mạng truy cập doanh nghiệp, các nguồn như **802.1X/RADIUS accounting**, controller/AP logs và NAC logs có thể liên hệ username/device identity, session, SSID, VLAN, AP, switch port, roaming và khoảng thời gian kết nối.

Đặc biệt:

- Roaming giữa các AP khiến một client xuất hiện ở nhiều điểm trong khoảng thời gian ngắn.
- MAC randomization của thiết bị có thể làm ánh xạ kém ổn định.
- Shared credentials hoặc tài khoản được cấp cho nhiều thiết bị không đủ để xác nhận cá nhân.
- Wi-Fi association thành công không chứng minh traffic đã tới đích ứng dụng.

## 8. Web proxy, CDN, WAF, load balancer và ứng dụng

### 8.1. Dữ liệu HTTP và định danh request

Proxy/access logs thường là nguồn tốt nhất để xác định host, URL path hoặc API route, method, status, upstream, request duration, TLS parameters, WAF action và request/correlation ID **nếu cấu hình có ghi**. Ví dụ:

~~~json
{
  "timestamp": "2026-11-28T03:12:10Z",
  "request_id": "f8b6e770b4754c8795f5e59d34c1d462",
  "client_ip_observed": "198.51.100.7",
  "method": "POST",
  "route": "/orders",
  "status": 504,
  "upstream": "10.20.8.10:8443",
  "upstream_time_ms": 30000
}
~~~

Một **504 tại gateway** nói rằng gateway không lấy được response upstream đúng hạn theo cơ chế của nó; chưa chứng minh server bị tấn công hay đường mạng bị drop. Cần đối chiếu upstream logs, trace, connect timing và packet/flow ở hai phía.

### 8.2. Tại sao phải tách từng chặng?

Reverse proxy L7 thường kết thúc TCP/TLS phía client rồi tạo connection upstream mới. Do đó:

~~~text
Client --[TCP/TLS #1]--> CDN/WAF/Proxy --[TCP/TLS #2]--> Backend
                           |  request_id
                           +-- access/WAF log, upstream mapping
~~~

Hai chặng có **5-tuple, sequence/ACK và TLS session khác nhau**. Nếu upstream connection được reuse hoặc HTTP/2 multiplexed, một 5-tuple có thể chứa nhiều request. Ghép bằng request ID/trace ID và log proxy, không dựa vào việc packet có cùng sequence number.

**CDN cache hit** và **WAF block** có thể tạo response mà không hề gửi request đến origin. Nên giữ cả edge security/access logs lẫn origin logs; không thấy record backend có thể là hành vi hợp lệ hoặc hạn chế của log pipeline.

### 8.3. TLS và giới hạn điều tra nội dung

Với HTTPS/TLS, packet ngoài điểm giải mã thường chỉ cho thấy metadata ở mức IP/TCP/UDP, kích thước, thời gian và một phần handshake. **HTTP/3 sử dụng QUIC trên UDP**, thường ở cổng 443, vì vậy filter chỉ chọn TCP/443 có thể bỏ sót.

Tên miền thực có thể không hiển thị qua SNI khi ECH được sử dụng. Certificate, SNI hoặc ALPN có thể cung cấp đầu mối tùy phiên/cấu hình, nhưng không phải bằng chứng xác định URL/path hay nội dung. Ưu tiên proxy logs hoặc endpoint logs đã được quản trị theo chính sách; giải mã traffic chỉ thực hiện khi có quyền và biện pháp bảo vệ key phù hợp.

## 9. Cloud, container và service mesh

Trong hạ tầng đám mây, tài sản và network path có thể thay đổi chỉ sau vài phút. Một private IP có thể chuyển sang instance khác, pod bị thay mới, hoặc load balancer chọn target khác.

### 9.1. Những nguồn cần lưu

| Môi trường | Dữ liệu có ích | Điều cần phân biệt |
| --- | --- | --- |
| VPC/VNet | Flow logs, route table, security group/NSG, subnet, NAT gateway | Allowed ở một hop chưa có nghĩa end-to-end thành công |
| Cloud load balancer | Listener, target, health, access log, request ID | Client VIP khác backend IP; có thể TLS termination |
| Kubernetes | Pod UID/IP, node, namespace, Service/EndpointSlice, ingress | Pod name/IP có thể tái sử dụng hoặc thay đổi |
| CNI/network policy | Policy decision, veth/overlay, eBPF flow events | Điểm bắt ở node có thể chỉ thấy outer tunnel |
| Service mesh | Sidecar proxy access log, trace, mTLS identity, route | Chặng ứng dụng và sidecar có thể khác nhau |
| Cloud audit/control plane | Tạo/xóa resource, thay đổi IAM, route, policy | Là bằng chứng về thay đổi, không tự chứng minh packet đi qua |
| Object storage/data services | Access audit, request logs, object operations | Tác vụ đọc object không luôn tương đương dữ liệu được tải ra qua mạng công khai |

### 9.2. Điều tra theo snapshot lịch sử

Khi đối chiếu IP **10.20.8.10** lúc 03:12 UTC, cần xác định **instance/pod UID tại 03:12**, node/cluster, security policy và endpoint mapping ở thời điểm đó. Trạng thái hiện tại từ giao diện cloud hoặc Kubernetes có thể là một tài sản hoàn toàn khác.

Một số dịch vụ managed không cho bắt PCAP tại chính thiết bị trung gian. Trong trường hợp đó, kết hợp cloud flow logs, LB/security logs, config audit, endpoint PCAP và application trace. Mô tả rõ **điểm chưa có quan sát trực tiếp**, thay vì vẽ suy đoán như một tuyến đã xác nhận.

## 10. Endpoint, định danh và ứng dụng: nguồn đối chiếu bắt buộc

Network evidence thường chỉ xác định địa chỉ và hoạt động kết nối. Để biết **tiến trình nào** tạo traffic, cần thêm:

- **EDR/endpoint telemetry:** process ID, executable, parent process, user context, socket connection, event time, file operations và alert details.
- **Host OS logs:** đăng nhập, dịch vụ khởi động, firewall host, network configuration, lỗi TCP/driver và restart.
- **Identity/SSO/VPN auth logs:** principal, nguồn xác thực, MFA, session, device identity và kết quả.
- **Application/API/database logs:** request/correlation ID, resource được truy cập, status, thao tác và transaction outcome.
- **DLP/data access logs:** nếu cần xác định tập dữ liệu cụ thể được truy cập, tải xuống hoặc xuất ra.

**Tiến trình gắn với socket ở thời điểm hiện tại không mặc nhiên là tiến trình đã mở kết nối trong quá khứ.** Cần log lịch sử hoặc telemetry có timestamp và process identity đủ tin cậy. Tài khoản dùng chung, service account và thông tin xác thực bị đánh cắp cũng khiến việc quy trách nhiệm cho một cá nhân cần thêm bằng chứng.

Nếu máy nghi bị xâm nhập có thể làm sai lệch log cục bộ, hãy ưu tiên đối chiếu bản ghi gửi ra hệ thống tập trung trước sự cố, nguồn sensor độc lập và audit trail của hệ thống khác. Không mặc định endpoint log hoàn toàn tin cậy.

## 11. Đánh giá chất lượng nguồn: độ bao phủ, tính đầy đủ và rủi ro sai lệch

Không phải nguồn log có dữ liệu thì dữ liệu đó đủ để kết luận. Trước khi dựa vào một nguồn, đánh giá:

| Tiêu chí | Câu hỏi thực hành |
| --- | --- |
| **Provenance** | Thiết bị, sensor, service, account và collector nào sinh bản ghi? |
| **Coverage** | Sensor thấy những interface, subnet, tenant, chiều lưu lượng nào? |
| **Timestamp** | Giờ ở UTC hay local; có offset, NTP, độ trễ pipeline không? |
| **Granularity** | Packet, flow, request, session hay alert? |
| **Completeness** | Có sampling, truncation, drop, filter hoặc retention thiếu không? |
| **Integrity** | Raw record có được bảo toàn, hash, quyền chỉnh sửa và audit đầy đủ không? |
| **Semantics** | ACCEPT, timeout, bytes, session duration có nghĩa gì đối với chính sản phẩm đó? |
| **Independence** | Hai log có thật sự độc lập hay một nguồn chỉ sao chép lại nguồn kia? |
| **Privacy** | Có IP, credential, cookie, dữ liệu cá nhân hoặc payload nhạy cảm không? |
| **Reproducibility** | Người khác có thể dùng metadata và phương pháp đã ghi để kiểm chứng phân tích không? |

**Hai dashboard hiển thị cùng một log ingestion không phải hai bằng chứng độc lập.** Sự đồng thuận mạnh hơn đến từ các điểm quan sát khác nhau, ví dụ firewall session log kết hợp server PCAP và endpoint process telemetry.

### 11.1. Thứ tự ưu tiên bảo toàn theo tính dễ mất

| Nguồn | Nguy cơ mất dữ liệu | Quyết định thu thập |
| --- | --- | --- |
| Live NAT/conntrack/session, ARP/neighbor, route, process/socket table | Rất dễ biến mất khi timeout, restart hoặc đổi kết nối | Snapshot sớm bằng phương pháp được phép; ghi thời gian và ngữ cảnh |
| Packet capture đang chạy / rolling buffer | Có thể bị ghi đè nhanh | Lưu khoảng sự cố ngay khi có tín hiệu, kiểm tra dropped packet |
| Log firewall/IDS/DNS với retention ngắn | Xoay vòng hoặc trễ ingest | Bảo lưu bản raw và metadata trước khi retention xóa |
| Pod/container logs và ephemeral resources | Có thể biến mất khi reschedule/scale down | Xuất đúng pod UID, node, namespace và cửa sổ thời gian |
| Cloud/provider audit logs | Có thể có độ trễ, giới hạn retention/quyền | Giữ bản xuất đúng thời gian, schema và account/project |
| CMDB, config history, asset inventory | Thường tồn tại lâu hơn nhưng có thể cập nhật | Lưu snapshot lịch sử cần dùng để ánh xạ |

Đây là định hướng, không phải thứ tự cố định cho mọi cuộc điều tra. Khi có dấu hiệu đe dọa đang diễn ra, quyết định containment và preservation phải được phối hợp với người chỉ huy ứng phó, theo chính sách và quyền hạn thực tế.

## 12. Kết nối bằng chứng thành timeline có thể kiểm chứng

### 12.1. Mẫu timeline

| UTC | Nguồn | Sự kiện | Mức xác nhận |
| --- | --- | --- | --- |
| 03:11:58 | DHCP history | 10.10.4.22 thuộc asset WS-042 trong lease đang hiệu lực | Ánh xạ IP → tài sản theo lịch sử |
| 03:12:00 | DNS resolver log | WS-042 hỏi tên miền cập nhật; resolver trả IP đích | Có DNS query/response |
| 03:12:10 | Firewall/NAT log | Session từ WS-042 tới IP:443, mapping public IP/port | Có xử lý session ở firewall |
| 03:12:10 | PCAP egress | Quan sát SYN/SYN-ACK, TLS handshake | Kết nối đi qua điểm capture |
| 03:12:11 | Proxy log | Yêu cầu có request ID, status và số byte ghi nhận | Hoạt động tại proxy |
| 03:12:12 | EDR | Tiến trình trên WS-042 tạo network connection | Liên hệ tiến trình với host |

Toàn bộ bảng là **tình huống minh họa**. Muốn kết luận về một sự cố thực tế cần điền ID bản ghi gốc, timestamp, query, hash và giới hạn cho từng hàng.

### 12.2. Tránh bẫy ghép nhầm

1. **Clock skew:** chuẩn hóa timezone về UTC nhưng giữ raw timestamp; đo hoặc ước lượng độ lệch và độ chính xác của từng nguồn.
2. **NAT:** nối original/translated 5-tuple theo timestamp và session mapping; không dùng public IP một mình.
3. **Proxy:** nối request ID, upstream và attempt; không ghép hai chặng TCP bằng sequence number.
4. **DNS:** một query không chứng minh connection; cache, nhiều A/AAAA, split DNS và CDN làm một tên có nhiều đích.
5. **Flow aggregation:** một record có thể bao phủ nhiều giây/phút; không ép nó thành sự kiện tại một thời điểm chính xác.
6. **Log pipeline:** collector có thể ingest muộn, reorder hoặc deduplicate; phân biệt event time với ingestion time.
7. **Retry và multiplexing:** nhiều connection có thể là một request logic và một connection có thể mang nhiều request.
8. **Host identity:** kết hợp asset ID, MAC, DHCP lease, authenticated identity, instance/pod UID và thời gian.

Nếu timeline có lỗ hổng, ghi **UNKNOWN** và nguồn cần thu thêm. Không điền khoảng trống bằng sự kiện giả định rồi mô tả như kết quả quan sát.

## 13. Thu thập và bảo toàn bằng chứng đúng cách

Một workflow điều tra số phải bảo vệ **nguồn gốc, tính toàn vẹn, quyền truy cập và khả năng truy vết thao tác** của bằng chứng. Quy trình áp dụng cụ thể theo chính sách pháp lý và tổ chức; các nguyên tắc chung:

### Bước 1: xác định phạm vi và thẩm quyền

Ghi incident/case ID, mục tiêu phân tích, hệ thống/tenant/segment được phép thu, người phê duyệt nếu quy trình yêu cầu, khoảng thời gian và loại dữ liệu. Chỉ thu phần dữ liệu cần thiết; PCAP plaintext có thể chứa cookie, mật khẩu và dữ liệu cá nhân.

### Bước 2: bảo toàn nguồn đang dễ mất

Giữ raw logs, ring buffer PCAP, NAT session, DNS cache/lease hoặc trạng thái endpoint phù hợp. Ưu tiên **snapshot/copy** khi cần; thao tác trực tiếp trên hệ thống sống có thể làm thay đổi trạng thái. Ghi rõ lệnh/phương pháp, công cụ, phiên bản và thời điểm.

### Bước 3: ghi provenance cùng metadata

Tối thiểu cần: evidence ID, case ID, hostname/device ID, source IP/interface, người thực hiện, thời điểm UTC thu, khoảng thời gian sự kiện, nguồn đồng hồ, filter hoặc query, timezone, file format/schema, byte count, tình trạng sampling/drop/truncation và vị trí lưu.

Ví dụ manifest khái niệm:

~~~yaml
case_id: INC-EXAMPLE-2026-042
evidence_id: E-007
source: edge-fw-01
source_type: firewall-session-log
event_time_window_utc:
  start: "2026-11-28T03:10:00Z"
  end: "2026-11-28T03:20:00Z"
collected_at_utc: "2026-11-28T03:30:00Z"
collector: analyst-on-duty
query_scope: "src_ip=10.10.4.22 AND dst_port=443"
format: jsonl
limitations:
  - "Nguồn có thể chỉ ghi một sự kiện khi session đóng"
  - "Chưa kiểm chứng độ lệch đồng hồ thiết bị"
sha256: "<ghi kết quả hash của tệp thu được tại đây>"
storage: restricted-evidence-repository
~~~

Manifest chỉ là ví dụ về dữ liệu cần ghi trong hồ sơ vụ việc, không phải cấu trúc chuẩn bắt buộc.

### Bước 4: hash, hạn chế sửa đổi và quản lý bản sao

Dùng thuật toán hash mạnh như **SHA-256** để nhận diện nội dung tệp tại thời điểm thu. Ví dụ trên bản sao đã được cấp quyền:

~~~bash
# Tính hash sau khi lưu file bằng chứng:
sha256sum incident-edge.pcapng

# Ghi cả file size và timestamp file để bổ trợ metadata:
stat incident-edge.pcapng
~~~

Ghi hash cùng thời điểm, nguồn và người thu. Lưu bản gốc trong kho có phân quyền, audit và retention thích hợp; phân tích trên **bản sao làm việc**; ghi rõ mọi chuyển đổi/lọc/ẩn danh vào hồ sơ. Khi chuyển giao, ghi người gửi, người nhận, thời điểm, phương thức và hash đã kiểm chứng.

**Hash khớp chứng minh hai dãy byte giống nhau tại thời điểm kiểm tra**, không tự chứng minh log không bị làm giả trước khi thu hay phương pháp thu đúng. Tính xác thực cần thêm provenance, kiểm soát hệ thống nguồn và chuỗi bảo quản (chain of custody).

### Bước 5: tách dữ kiện khỏi suy luận

Một báo cáo nên ghi: **quan sát**, **nguồn và trích dẫn bằng chứng**, **giả thuyết**, **phép kiểm tra**, **điều chưa kiểm chứng** và **mức tự tin**. Khi cần loại thông tin cá nhân trước khi chia sẻ, giữ riêng bản gốc có kiểm soát và bản xuất đã xử lý; không tự chỉnh sửa bản gốc.

## 14. Minh họa công cụ đọc và lọc dữ liệu

Các lệnh dưới đây dành cho môi trường **được phép giám sát**. IP, interface và đường dẫn tệp là ví dụ; thu thập nên giới hạn đủ cho câu hỏi điều tra và lưu trong kho an toàn.

### 14.1. Thu PCAP có giới hạn

~~~bash
sudo tcpdump -i eth0 -nn -s 160 -c 2000 \
  -w incident-edge.pcap \
  'host 10.10.4.22 and (tcp port 443 or udp port 53)'
~~~

- **-i eth0**: interface thực cần bắt.
- **-nn**: tắt phân giải tên khi hiển thị.
- **-s 160**: giới hạn số byte của mỗi packet được lưu; có thể bỏ lỡ trường dài hoặc encapsulation.
- **-c 2000**: dừng sau số packet tối đa đã chỉ định, giới hạn thời gian gián tiếp.
- **-w**: ghi packet ra file.
- Biểu thức **host ...** là capture filter theo cú pháp libpcap/BPF.

Filter này chỉ là ví dụ TCP/443 và UDP/53. Nó sẽ không tự thu DoH/DoT, UDP/443 QUIC, ICMP hoặc DNS qua TCP nếu không mở rộng. Với capture phục vụ pháp chứng, phải ghi rõ việc loại bỏ gói ngay từ đầu làm giảm độ bao phủ.

### 14.2. Đọc tệp và lọc sự kiện

~~~bash
tcpdump -nn -tttt -r incident-edge.pcap

# Liệt kê một số trường có liên quan từ PCAP:
tshark -r incident-edge.pcap \
  -T fields -e frame.time_epoch -e ip.src -e ip.dst \
  -e tcp.srcport -e tcp.dstport -e tcp.flags -e frame.len

# Chỉ xem TCP SYN chưa có ACK trong Wireshark/TShark:
tshark -r incident-edge.pcap \
  -Y 'tcp.flags.syn == 1 && tcp.flags.ack == 0'
~~~

**Capture filter** dùng trong tcpdump trước khi lưu khác với **display filter** của Wireshark/TShark sau khi thu. Thu packet thiếu ngay từ đầu thì display filter không thể phục hồi phần dữ liệu đã bỏ. Phần lớn log/flow dùng cú pháp query riêng (SIEM/SQL/CLI), không được lấy một ví dụ query rồi áp dụng cho mọi công cụ.

### 14.3. Kiểm tra điều kiện đủ chứng cứ

Sau khi thu, cần đọc thống kê **packets captured/received/dropped**, kiểm tra tệp có thể mở được, xác nhận thời điểm có khớp với hiện tượng, cả hai chiều lưu lượng có xuất hiện khi kỳ vọng và có bằng chứng bị cắt do snaplen hay không. Nếu độ bao phủ không đạt, kết luận phải thu hẹp hoặc bổ sung nguồn khác.

## 15. Tình huống điều tra: kết nối bất thường từ một máy trạm

### 15.1. Dấu hiệu ban đầu

Hệ thống NDR phát cảnh báo một máy trạm thường xuyên kết nối tới tên miền hiếm gặp ngoài giờ làm việc. Trước khi phân loại thành hành vi độc hại, nhóm điều tra đặt ba giả thuyết:

1. Ứng dụng doanh nghiệp hoặc tác vụ cập nhật hợp lệ.
2. Phần mềm ngoài danh mục được người dùng cài đặt hoặc cấu hình sai.
3. Hành vi nghi vấn cần điều tra thêm về giao tiếp điều khiển hoặc chuyển dữ liệu.

**Không dùng tên miền "hiếm gặp" hay lưu lượng nhiều làm bằng chứng độc lập cho kết luận xâm nhập.**

### 15.2. Ma trận thu thập

| Câu hỏi điều tra | Nguồn ưu tiên | Kỳ vọng xác minh |
| --- | --- | --- |
| IP thuộc tài sản nào lúc sự kiện? | DHCP history, IPAM, EDR inventory | Lease + asset ID đúng thời gian |
| Máy hỏi tên miền nào? | DNS resolver logs, endpoint DNS telemetry | Query, answer, TTL và resolver |
| Máy có thực sự kết nối IP đó? | Firewall session, NetFlow/IPFIX, PCAP | 5-tuple, start/end, chiều và volume |
| NAT public IP nào đã sử dụng? | NAT/session log | Original/translated tuple và timestamp |
| Kết nối đi qua proxy/WAF không? | Proxy access log, LB log | Route, action, request ID và timing |
| Tiến trình/tài khoản nào tạo kết nối? | EDR, OS log, identity log | Process lineage, signer/path, principal |
| Gói có nội dung nhìn được không? | PCAP được phép, protocol metadata | Chỉ các trường sensor nhìn thấy; mã hóa là giới hạn |
| Có dấu hiệu truy cập dữ liệu nhạy cảm? | File/data access audit, ứng dụng, DLP | Đối tượng truy cập và thao tác được log |
| Host khác có cùng hành vi không? | Flow/DNS/NDR theo nhiều asset | Phạm vi ảnh hưởng có xác minh |

### 15.3. Ví dụ timeline giả định

~~~text
03:10:10 UTC - DHCP: 10.10.4.22 thuộc laptop WS-042 (lease hiệu lực).
03:10:12 UTC - DNS: WS-042 hỏi updates.example.test.
03:10:12 UTC - DNS: Resolver trả 203.0.113.70.
03:10:15 UTC - Firewall: Cho phép TCP/443 từ 10.10.4.22 tới 203.0.113.70.
03:10:15 UTC - NAT: 10.10.4.22:50214 -> 198.51.100.7:62001.
03:10:15 UTC - Egress PCAP: TLS handshake được quan sát.
03:10:16 UTC - EDR: Một tiến trình cập nhật tự động tạo kết nối.
03:11:00 UTC - Flow: Ghi nhận bytes gửi/nhận trong khoảng session.
~~~

Tên miền, IP và sự kiện trong ví dụ đều mang tính minh họa. Với dữ liệu trên, có thể xác nhận kết nối xảy ra và liên hệ với tiến trình, nhưng **chưa thể khẳng định dữ liệu nào đã truyền** qua TLS. Muốn phân loại hành vi là hợp lệ, cần kiểm tra nguồn gốc phần mềm, lịch cập nhật, quyền thực thi và đối chiếu với policy doanh nghiệp. Nếu nghi rò rỉ dữ liệu, bổ sung endpoint file activity và data-access logs thay vì suy đoán từ số byte.

### 15.4. Mẫu báo cáo kết luận

> **Đã xác nhận:** WS-042 (theo lịch sử DHCP) có phiên TCP/443 tới 203.0.113.70 trong cửa sổ 03:10–03:11 UTC. NAT và firewall logs khớp flow; PCAP egress quan sát TLS handshake; EDR ghi tiến trình có liên quan.
>
> **Chưa xác nhận:** Nội dung dữ liệu đã truyền, mục đích của endpoint và có hay không hành vi xâm nhập. Payload mã hóa; chưa có log ứng dụng hoặc kết quả phân tích tiến trình đầy đủ.
>
> **Bước điều tra:** Đối chiếu tiến trình với inventory và nhà cung cấp phần mềm, kiểm tra access log dữ liệu, mở rộng tìm kiếm DNS/flow tới các host liên quan trong cùng thời gian, đánh giá chính sách xử lý với người phụ trách sự cố.

Loại báo cáo này giúp người nhận phân biệt **sự kiện quan sát được** với **đánh giá rủi ro** và các khoảng trống cần tiếp tục điều tra.

## 16. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Đồng nhất alert IDS với xâm nhập thành công | Kết luận sai và ứng phó quá mức | Xác minh flow, packet, endpoint và ngữ cảnh |
| Gán public IP cho một người dùng | Sai attribution vì NAT/shared egress | NAT mapping, DHCP, identity và mốc thời gian |
| Dùng IP/hostname hiện tại để đọc log cũ | Sai tài sản do DHCP, cloud, pod thay đổi | Snapshot/history đúng thời điểm |
| ACCEPT trong flow log = request tới app | Bỏ qua hop khác, response, gateway | Đối chiếu access log và điểm quan sát tiếp theo |
| Không có PCAP = không có packet | Sensor sai vị trí hoặc capture loss | Kiểm tra interface, filter, drop và route |
| Mã hóa nghĩa là không thể điều tra | Bỏ qua timing/volume và endpoint/proxy logs | Dùng metadata, session và nguồn tại endpoint |
| Flow bytes = dữ liệu bí mật bị lấy | Nhầm volume với nội dung và ý nghĩa nghiệp vụ | Data access, DLP, endpoint/app evidence |
| Timestamp bản ghi = thời điểm ingest | Ghép nhầm thứ tự sự kiện | Lưu event time, receive time và clock offset |
| PCAP trên host cho thấy chính xác packet trên dây | Sai do offloading và encapsulation | Kiểm tra GRO/TSO/checksum và điểm capture |
| Có hai dashboard là hai nguồn độc lập | Phóng đại độ tin cậy | Truy provenance đến sensor/collector gốc |
| Chỉ hash sau khi đã chỉnh sửa/lọc | Mất khả năng đối chiếu bản gốc | Giữ bản gốc, hash khi thu và ghi mọi bản dẫn xuất |
| Thu toàn bộ payload không giới hạn | Lộ dữ liệu, tốn dung lượng, không rõ mục tiêu | Xác định câu hỏi, phạm vi, retention và quyền |
| Xóa/khởi động lại thiết bị trước khi bảo toàn | Mất session/route/log dễ biến mất | Phối hợp preservation với containment |
| Không ghi limitations/sampling | Người khác hiểu sai mức độ bao phủ | Manifest có filter, loss, sampling và thời gian |

## 17. Checklist nguồn bằng chứng trước khi kết luận

- [ ] Đã định nghĩa câu hỏi điều tra và phạm vi hệ thống/tenant được phép thu.
- [ ] Đã xác định asset ID, người sở hữu, IP/MAC, zone và mapping theo **đúng thời điểm**.
- [ ] Có nguồn về **kết nối**: PCAP, flow, firewall/NAT, VPN hoặc proxy logs phù hợp.
- [ ] Có nguồn về **tên và danh tính**: DNS, DHCP, NAC, identity/endpoint khi cần.
- [ ] Có nguồn về **hành vi ứng dụng** nếu kết luận liên quan request, tài liệu hoặc transaction.
- [ ] Có sơ đồ đường đi, cả chiều request và response, qua firewall, VPN, NAT, proxy và cloud boundary.
- [ ] Đã kiểm tra dữ liệu còn thiếu do sampling, log rotation, packet drop, mã hóa, offloading hoặc sensor không đủ chiều.
- [ ] Đã chuẩn hóa timeline nhưng giữ raw timestamps và ghi clock skew/ingest delay.
- [ ] Đã bảo toàn raw evidence, metadata, hash và lịch sử truy cập/chuyển giao theo chính sách.
- [ ] Đã đối chiếu nguồn độc lập, phân biệt quan sát với giả thuyết và ghi mức độ chắc chắn.
- [ ] Báo cáo nêu rõ kết luận hỗ trợ bằng chứng nào, còn thiếu gì và phép kiểm tra tiếp theo.

Nguồn bằng chứng của network forensics trải từ **packet**, **flow**, **log kiểm soát mạng** đến **dịch vụ, danh tính, endpoint và cấu hình cloud**. Mỗi nguồn chỉ quan sát một phần của luồng và có các giả định riêng về thời gian, độ bao phủ và độ tin cậy. Thu đúng nguồn, bảo toàn nguyên trạng, ánh xạ tài sản đúng thời điểm và đối chiếu độc lập sẽ giúp tái dựng sự kiện mạng có căn cứ, đồng thời tránh khẳng định những điều mà bằng chứng chưa chứng minh.
