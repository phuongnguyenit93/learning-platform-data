# Volumetric denial of service

> **Chương:** DDoS  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Bối cảnh:** Phòng vệ mạng từ phân đoạn, firewall, VPN, IDS/IPS và xác thực kết nối tới DNS, Wi-Fi, cloud, phân tích lưu lượng, giám sát xâm nhập và kiến trúc mạng an toàn.  
> **Mục đích:** Hiểu và phòng chống các cuộc tấn công làm cạn năng lực truyền tải mạng, không phải hướng dẫn tạo lưu lượng tấn công.

## 1. Volumetric denial of service là gì?

**Volumetric denial of service (DoS theo lưu lượng)** là kiểu làm gián đoạn tính sẵn sàng của dịch vụ bằng cách đưa lượng traffic quá lớn tới một hoặc nhiều điểm trên đường truyền, khiến **băng thông, năng lực chuyển tiếp gói hoặc thiết bị trung gian bị quá tải**. Hậu quả là lưu lượng hợp lệ bị mất gói, xếp hàng lâu, timeout hoặc không tới được ứng dụng.

Nếu lưu lượng đến từ **nhiều nguồn phân tán** theo cách phối hợp, cuộc tấn công thường được gọi là **Distributed Denial of Service (DDoS)**. Tuy nhiên **volumetric** mô tả **cơ chế gây nghẽn**, còn **distributed** mô tả **mô hình nguồn phát**: một nguồn đủ mạnh cũng có thể tạo DoS volumetric; nhiều nguồn có thể phối hợp tấn công tầng ứng dụng mà không cần tạo băng thông cực lớn.

Ví dụ, một doanh nghiệp có dịch vụ web đặt sau firewall tại văn phòng. Khi một lượng traffic không mong muốn vượt năng lực đường truyền Internet vào văn phòng, kết nối đã nghẽn **trước khi gói tin được firewall xem xét**. Firewall tại văn phòng dù chặn hoàn toàn các gói tấn công sau đó vẫn không thể lấy lại dung lượng đường truyền đã bị chiếm ở phía upstream.

**Đặc điểm nhận diện:** sự cố chủ yếu liên quan đến **khả năng phục vụ của đường truyền hoặc thành phần chuyển tiếp mạng**, không nhất thiết do server lỗi mã nguồn hay database chậm. Dù vậy, nhiều cuộc tấn công thực tế là **đa vector**: vừa làm nghẽn băng thông, vừa làm cạn bảng trạng thái của firewall hoặc gây nhiều request HTTP ở ứng dụng.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt volumetric DoS, protocol/state exhaustion và application-layer DoS.
2. Giải thích các khái niệm **bps, pps, packets dropped, link utilization, latency** và mối quan hệ với nút thắt cổ chai.
3. Hiểu ở mức phòng vệ cơ chế lưu lượng từ nhiều nguồn, source spoofing, reflection và amplification.
4. Lựa chọn lớp giảm thiểu thích hợp: ISP/upstream, scrubbing, Anycast, CDN, cloud DDoS protection, ACL, rate limiting và giám sát.
5. Viết runbook phát hiện, phân loại, điều phối giảm thiểu, xác minh hồi phục và tổng kết sự cố.
6. Xác định giới hạn của firewall, WAF, IDS/IPS, phân đoạn, DNS, VPN và cloud trong một sự cố bão hòa đường truyền.

## 2. Đặt volumetric DoS trong bức tranh các kiểu DoS

| Nhóm | Tài nguyên thường bị nhắm đến | Tín hiệu thường gặp | Biện pháp phòng vệ nổi bật |
|---|---|---|---|
| **Volumetric** | Đường truyền, upstream transit, băng thông/packet forwarding | bps/pps tăng mạnh, queue/drop, nhiều nguồn/luồng, link gần bão hòa | Lọc **trước nút nghẽn**, scrubbing, Anycast, CDN, ISP/cloud mitigation |
| **Protocol/state exhaustion** | Bảng kết nối, firewall state, NAT table, TCP backlog, CPU xử lý gói | SYN/connection attempt bất thường, state gần đầy, handshake lỗi | Stateful protections, SYN cookies/proxy theo thiết kế, giới hạn kết nối, upstream mitigation |
| **Application-layer (L7)** | Worker/thread, CPU app, database, cache, endpoint tốn tài nguyên | HTTP requests hoặc truy vấn nặng, độ trễ API tăng dù bps vừa phải | WAF, rate limit theo identity/path, cache, tối ưu ứng dụng, quota |

Đây là **cách phân nhóm theo điểm nghẽn chính**, không phải danh mục loại trừ nhau. Ví dụ lượng TCP SYN rất lớn có thể vừa làm tăng băng thông/pps vừa khiến bảng kết nối cạn. Một request HTTP nhỏ có thể rất tốn tài nguyên backend nhưng không phải volumetric theo nghĩa bão hòa đường truyền.

**Điểm quyết định:** tìm **nút thắt cổ chai đầu tiên**. Nếu upstream đã nghẽn, một WAF hoặc firewall đặt sau đường truyền khó giúp lưu lượng hợp lệ đi vào; nếu đường truyền vẫn thông mà API quá tải, các kiểm soát tầng ứng dụng sẽ phù hợp hơn.

## 3. Cơ chế gây mất dịch vụ: từ nguồn tới nút nghẽn

Một request hợp lệ đi từ client qua ISP, edge, router, firewall, load balancer rồi đến ứng dụng. Lưu lượng lớn bất thường có thể khiến một trong các đoạn đó quá tải.

~~~mermaid
flowchart LR
    L[Người dùng hợp lệ] --> I[Internet / ISP]
    M[Nhiều nguồn lưu lượng không mong muốn] --> I
    I --> B{Upstream link / peering còn dung lượng?}
    B -- Không --> X[Drop / queue trước firewall]
    B -- Có --> R[Router / edge]
    R --> F[Firewall / load balancer]
    F --> A[Ứng dụng]
    X -. Ảnh hưởng .-> L
~~~

**Ba mức tài nguyên** cần phân biệt:

- **Băng thông (bits/s):** tốc độ bit tới một link, cổng hoặc dịch vụ truyền tải. Một lượng byte lớn có thể lấp đầy năng lực truyền dẫn.
- **Năng lực xử lý gói (packets/s):** thiết bị phải nhận, tra bảng và chuyển tiếp từng gói. Số lượng rất lớn các gói nhỏ có thể gây quá tải CPU/ASIC hoặc queue ngay cả khi bps chưa chạm trần lý thuyết.
- **Năng lực xử lý luồng/trạng thái:** bảng kết nối, NAT, chống xâm nhập và các chức năng DPI có thể trở thành nút nghẽn trước khi cổng mạng đạt băng thông danh nghĩa.

Một thiết bị quảng cáo thông lượng “cao” không bảo đảm xử lý được mọi hỗn hợp **gói nhỏ, tính năng IPS/TLS inspection, số kết nối hoặc chính sách phức tạp** ở tốc độ tương đương. Nên dựa trên thông số theo **workload và cấu hình thực** thay vì chỉ tốc độ cổng.

### 3.1. Vì sao chặn sau điểm nghẽn không khôi phục được băng thông?

~~~text
Nguồn traffic lớn
    -> mạng nhà cung cấp / đường Internet vào doanh nghiệp [ĐÃ NGHẼN]
    -> firewall tại doanh nghiệp [DROP]
    -> ứng dụng
~~~

Firewall có thể giảm tải cho **server phía sau**, nhưng lưu lượng đã dùng dung lượng của đoạn link trước firewall. Để khôi phục khả năng nhận traffic hợp lệ, cần **lọc, hấp thụ, hoặc chuyển hướng traffic** tại một điểm upstream có đủ năng lực và đường đi thích hợp.

### 3.2. Hệ quả với ứng dụng

- TCP handshake thất bại hoặc phải truyền lại nhiều lần.
- UDP response thất lạc, các tác vụ thời gian thực gián đoạn.
- DNS, VPN, API, email hoặc ứng dụng cùng dùng chung đường truyền bị ảnh hưởng dây chuyền.
- Health checks thất bại khiến load balancer/routing thực hiện failover ngoài ý muốn.
- Log và telemetry có thể đến chậm do chính tuyến mạng gửi log đang nghẽn.

**Tính sẵn sàng** là mục tiêu trực tiếp bị tác động, nhưng việc thiếu kết nối tới hệ thống IAM, DNS, backup hoặc SOC có thể làm sự cố trở nên nghiêm trọng hơn.

## 4. Những dạng lưu lượng thường xuất hiện trong volumetric DoS

Không nên quyết định loại sự cố chỉ từ một giao thức. Cần quan sát **hướng, bps, pps, số nguồn, trạng thái phản hồi, dịch vụ đích và tài nguyên bị quá tải**.

| Dạng quan sát | Vì sao có thể gây nghẽn | Điểm cần xác minh |
|---|---|---|
| **UDP flood** | Lượng lớn datagram đi tới đích/đường truyền; có thể gồm nhiều cổng và nguồn | Bps, pps, port distribution, traffic được chấp nhận hay bị drop |
| **ICMP flood** | Nhiều gói ICMP có thể tiêu tốn đường truyền hoặc khả năng xử lý gói | Type/code, lưu lượng hợp lệ cần cho chẩn đoán/PMTU |
| **DNS reflection/amplification** | Nhiều phản hồi DNS đi tới địa chỉ bị giả làm nguồn yêu cầu | Response-heavy DNS traffic, hoạt động resolver, kiểm soát spoofing ở upstream |
| **Reflection qua dịch vụ UDP khác** | Máy chủ trung gian gửi response tới nạn nhân theo thông tin nguồn giả mạo | Loại protocol, địa chỉ nguồn là reflector, điểm upstream có thể lọc |
| **Traffic TCP cường độ cao** | Có thể gây tải bps/pps và bảng state; một số sự cố thiên về protocol exhaustion | SYN/ACK ratios, conntrack, retransmit, backlog và link utilization |
| **Nhiều request HTTP tải dữ liệu lớn** | Có thể gây tải egress/origin và app; thường xếp vào tầng ứng dụng nhưng ảnh hưởng băng thông | CDN cache, origin egress, URL/path, HTTP status và request rate |

**Không chặn toàn bộ ICMP như một phản xạ tự động.** ICMPv4 Fragmentation Needed hoặc ICMPv6 Packet Too Big hỗ trợ Path MTU Discovery; Neighbor Discovery cần cho các liên kết IPv6. Lọc theo **type/code, nguồn/đích, vị trí và nhu cầu thực** để tránh phá mạng hợp lệ.

## 5. Reflection, amplification và source-address spoofing

Đây là ba khái niệm cần hiểu ở **mức mô hình phòng vệ**, không phải công thức triển khai tấn công.

**Source-address spoofing** là việc gói IP mang địa chỉ nguồn không phải địa chỉ thực sự được phép sử dụng trên đường phát. Trong một số mạng cho phép traffic có IP nguồn giả rời đi, người gửi có thể khiến hệ thống khác phản hồi tới địa chỉ bị giả mạo.

**Reflection** là cách lưu lượng trả lời từ một dịch vụ trung gian hướng về địa chỉ nạn nhân, mặc dù nạn nhân không chủ động gửi yêu cầu tương ứng. **Amplification** xuất hiện khi khối lượng phản hồi do dịch vụ tạo ra **lớn hơn đáng kể** so với yêu cầu kích hoạt theo cách hoạt động của giao thức/dịch vụ.

~~~mermaid
flowchart LR
    A[Nguồn gửi lưu lượng với địa chỉ nguồn giả] -->|Yêu cầu tới dịch vụ trung gian| R[Dịch vụ phản hồi]
    R -->|Phản hồi về địa chỉ đã bị giả| V[Nạn nhân / đường truyền của nạn nhân]
    V --> X[Nguy cơ nghẽn đường nhận]
    N[Biện pháp phòng vệ] -. Egress anti-spoofing .-> A
    N -. Giới hạn dịch vụ phản hồi .-> R
    N -. Lọc upstream / scrubbing .-> V
~~~

**Dấu hiệu cần xem:** traffic nhiều response, nguồn thuộc nhiều máy chủ trung gian, protocol/cổng không đúng luồng ứng dụng mong đợi, thiếu tương ứng giữa outbound query và inbound response trong các dữ liệu quan sát được. Tuy nhiên **việc không thấy query không tự chứng minh reflection**: có thể log thiếu, đường đi bất đối xứng hoặc request đi qua nơi sensor không nhìn thấy.

### 5.1. Phòng vệ ở nhiều phía

1. **Mạng nguồn:** triển khai **Source Address Validation / ingress filtering** để ngăn packet có IP nguồn giả mạo rời khỏi mạng theo RFC 2827 (BCP 38) và các biện pháp bổ sung của RFC 3704 (BCP 84).
2. **Nhà vận hành dịch vụ có thể phản hồi:** hạn chế truy cập không cần thiết, không cung cấp dịch vụ mở cho mọi nguồn khi không có yêu cầu; cập nhật cấu hình và phần mềm.
3. **Mạng đích/nạn nhân:** giám sát lưu lượng bất thường, phối hợp với upstream hoặc DDoS provider để lọc trước khi bão hòa link, giữ đường quản trị và liên lạc khẩn cấp.

Đối với DNS, **resolver đệ quy (recursive resolver)** chỉ nên phục vụ tập client được phép; không nên vô tình vận hành open resolver có thể bị lạm dụng. DNS authoritative public cần phục vụ truy vấn công khai theo vai trò của nó và sử dụng các bảo vệ phù hợp với loại dịch vụ.

### 5.2. Giới hạn phòng vệ bằng chặn IP

Một IP nguồn quan sát được trong reflection có thể thuộc **máy chủ trung gian hợp pháp**, không phải kẻ điều khiển. Chặn mọi IP như vậy có thể chặn cả dịch vụ hợp lệ. Nếu IP spoofing hoặc botnet phân tán, danh sách IP ngắn hạn còn dễ bị thay đổi. Cần dựa vào **ngữ cảnh protocol, đặc điểm luồng, chính sách khách hàng và năng lực lọc của upstream**, không chỉ danh sách nguồn.

## 6. Đo volumetric DoS: bps, pps, utilization và chất lượng dịch vụ

### 6.1. Các chỉ số cơ bản

| Chỉ số | Đơn vị | Câu hỏi trả lời |
|---|---|---|
| **Ingress bitrate** | bits/s, Mbps, Gbps | Bao nhiêu dữ liệu đang vào link/thiết bị? |
| **Packet rate** | packets/s, kpps, Mpps | Có bao nhiêu packet phải xử lý mỗi giây? |
| **Utilization** | % dung lượng link đo tại đúng hướng | Đoạn truyền nào gần bão hòa? |
| **Packet drop/discard** | packets/s hoặc số đếm tăng | Packet mất ở interface, queue, ACL hay pipeline nào? |
| **Error/retransmission** | packet errors, retransmits | Có mất gói hoặc lỗi truyền làm TCP chậm? |
| **Connection attempts** | connections/s, SYN/s khi phù hợp | Có áp lực lên state table hoặc TCP handshake? |
| **Concurrent states** | số mục bảng state/NAT | Có nguy cơ cạn tài nguyên của firewall/load balancer? |
| **Service success rate** | % request/transaction thành công | Người dùng có còn sử dụng dịch vụ được không? |
| **Latency và jitter** | ms, p95/p99 | Truy cập hợp lệ đang chậm tới mức nào? |

Hai công thức đo lường:

~~~text
bitrate (bps) = delta(received_bytes) * 8 / observation_seconds
packet_rate (pps) = delta(received_packets) / observation_seconds

utilization (%) = observed_bps / effective_link_capacity_bps * 100
~~~

Đọc **counter delta**, không dùng tổng số byte kể từ khi thiết bị khởi động làm tốc độ. Cần lưu ý counter wrap/reset và dữ liệu lấy mẫu. Với link full-duplex, **hướng ingress và egress đo riêng**; không cộng mù quáng để kết luận một hướng đã bão hòa.

### 6.2. Băng thông danh nghĩa không đồng nghĩa năng lực ứng dụng

Một đường truyền có tốc độ danh nghĩa nhất định vẫn có thể gặp vấn đề sớm hơn vì shaping/policing, packet per second limit, queue, MTU, thiết bị firewall, IPS hoặc chính sách nhà cung cấp. Ngược lại, sử dụng link cao trong một đợt cập nhật hợp lệ **không tự chứng minh DDoS**.

Để xác định **nút nghẽn**, so:

- Traffic ở interface hoặc peer trước điểm nghi ngờ với traffic sau điểm đó.
- Drop/discard, CPU, queue và session table của router/firewall.
- SLI của dịch vụ: DNS resolution, TCP handshake, TLS handshake, API success.
- Chỉ số do **ISP hoặc nhà cung cấp cloud nhìn thấy** trước khi traffic đến doanh nghiệp.

### 6.3. Ví dụ đánh giá dung lượng

Giả sử đường truyền Internet vào văn phòng có năng lực hiệu dụng theo hợp đồng **500 Mbps** và thiết bị tại biên cho thấy inbound traffic tăng vượt mức này, cùng packet drop và tỷ lệ kết nối hợp lệ thất bại. Đó là dấu hiệu **nghẽn đường truyền**, không phải bằng chứng trực tiếp về nguồn gốc tấn công. Cần phối hợp với ISP kiểm tra thống kê phía upstream, xác minh traffic hợp lệ/không hợp lệ và áp biện pháp phù hợp ở phía có đủ năng lực.

Không nên kết luận rằng “firewall chặn 100% gói xấu thì dịch vụ sẽ tự hồi phục”: nếu link đã nghẽn trước firewall, lượng packet bị drop tại firewall **không giải quyết** nút nghẽn upstream.

## 7. Nhận diện sự cố: phân biệt DDoS với traffic hợp lệ tăng đột biến

Một sự kiện **flash crowd** (người dùng hợp lệ truy cập đồng thời do tin tức, chiến dịch hoặc sự kiện) có thể tạo spike traffic rất giống biểu đồ DDoS. Ngoài ra còn có sự cố định tuyến, đứt tuyến, cấu hình firewall, deploy lỗi hoặc một batch job nội bộ dùng băng thông quá lớn.

| Tín hiệu | Có thể nghiêng về volumetric attack | Có thể do hoạt động hợp lệ / lỗi khác |
|---|---|---|
| Inbound bps/pps tăng gấp nhiều lần baseline | Lưu lượng bất thường từ nhiều nguồn, tới IP/port ít sử dụng | Chiến dịch marketing, bản cập nhật, backup hoặc đợt phát hành |
| Link/drop tăng | Băng thông hoặc packet forwarding bị đẩy tới giới hạn | Interface lỗi, QoS sai, nghẽn theo lịch |
| Phân bố protocol/port bất thường | Nhiều packet đến dịch vụ không dùng | Ứng dụng mới hoặc cấu hình sai hướng |
| Nhiều IP và ASN nguồn khác thường | Nguồn phân tán hoặc reflector | CDN/proxy, traffic khách hàng tăng theo địa lý |
| Tỷ lệ request thành công giảm | Legitimate flows bị mất gói/timeout | Origin lỗi, DNS, TLS, database hoặc deploy |
| WAF không ghi traffic tương ứng | Traffic ở dưới L7 hoặc bypass WAF | Logging thiếu, cache, TLS pass-through hoặc mất pipeline |

**Không dựa vào địa lý, IP reputation hoặc một mẫu thống kê đơn lẻ** để kết luận mọi request là độc hại. Xác thực với telemetry nhiều nguồn, thay đổi gần đây, lịch nghiệp vụ và tình trạng dịch vụ.

### 7.1. Tạo baseline

Baseline cần có **nhịp theo giờ/ngày/tuần**, cao điểm khuyến mãi, traffic theo dịch vụ, theo zone/ASN, inbound/outbound và độ trễ bình thường. Ngưỡng cảnh báo nên kết hợp:

1. **Giới hạn tài nguyên đã biết:** dung lượng link, pps forwarding, session table.
2. **Biến động so baseline:** tăng đột biến hoặc kéo dài theo cửa sổ thời gian phù hợp.
3. **Tác động thực:** lỗi kết nối, packet drop và user-facing SLI suy giảm.

Chỉ dùng threshold “bps cao” sẽ tạo nhiều false positive; chỉ dùng “ứng dụng chậm” có thể phát hiện quá muộn khi upstream đã nghẽn.

## 8. Nguồn telemetry và giới hạn quan sát

### 8.1. Ở router và link

- **SNMP/interface counters** hoặc API thiết bị: tốc độ nhận/gửi byte/packet, discards, errors.
- **NetFlow, IPFIX, sFlow**: đặc trưng flow, protocol, IP/port, phân bố traffic; sFlow có thể lấy mẫu.
- **QoS/queue stats**: queue depth, shaping/policing drops, congestion counters.
- **BGP/route status**: bất thường đường đi, sự cố peering, traffic engineering và tính nhất quán route.

**Số liệu tại điểm sau upstream nghẽn có thể thấp hơn lưu lượng tấn công thực** vì một phần đã bị drop trước đó. Khi đó báo cáo chỉ của doanh nghiệp không đủ; cần số liệu của ISP/cloud/DDoS provider.

### 8.2. Ở firewall, WAF và IDS/IPS

- Firewall: allow/deny, conntrack usage, new connection rate, hardware drops.
- WAF: HTTP request rate, rule matches, final action, 403/429, response latency; **không thấy toàn bộ UDP/ICMP flood**.
- IDS/IPS/NDR: bất thường traffic ở nơi sensor quan sát được; nếu sensor đứng sau link nghẽn, có thể không thấy toàn bộ đợt traffic.
- DNS: query/response rate, lỗi truy vấn, resolver saturation và khả năng phục vụ authoritative/recursive.

### 8.3. Ở hệ thống và trải nghiệm người dùng

- OS network counters, application metrics, latency và error rate.
- **Synthetic monitoring** từ nhiều mạng/vị trí được cấp quyền để kiểm tra dịch vụ thật.
- Telemetry của client và tình trạng VPN/SSO nếu dịch vụ phụ thuộc.

**Không chỉ nhìn “server CPU vẫn thấp” để kết luận không bị DDoS**: lưu lượng có thể bị rơi trước khi tới server.

## 9. Lệnh quan sát an toàn trên Linux và hệ giám sát

Các lệnh sau dành cho **đo trạng thái và chẩn đoán có quyền trên tài sản của mình**. Chúng không tạo flood và không thay thế dashboard của ISP/upstream.

~~~bash
# Xem lưu lượng và lỗi ở interface Linux (đổi eth0 theo môi trường)
ip -s link show dev eth0

# Quan sát số kết nối, trạng thái socket tại host
ss -s

# Xem các counter giao thức theo hệ điều hành
nstat -az

# Xem bảng định tuyến và đường ra đến một địa chỉ được phép kiểm tra
ip route

# Thu thập mẫu gói có giới hạn trên interface sở hữu,
# chú ý quyền truy cập và dữ liệu nhạy cảm trong packet capture.
sudo tcpdump -ni eth0 -c 100 'ip or ip6'
~~~

Nếu máy có Prometheus Node Exporter, các truy vấn minh họa theo interface:

~~~promql
# Tốc độ inbound bit/s; thay device theo tên interface thực
rate(node_network_receive_bytes_total{device="eth0"}[5m]) * 8

# Tốc độ inbound packets/s
rate(node_network_receive_packets_total{device="eth0"}[5m])

# Tốc độ tăng số packet bị drop ở interface
rate(node_network_receive_drop_total{device="eth0"}[5m])
~~~

Các metric trên **phụ thuộc exporter và tên thiết bị**; không mặc định mọi môi trường có metric hoặc quyền truy cập tương ứng. Một flow có thể được đếm ở nhiều hop, vì vậy không cộng tất cả interface rồi gọi là “lưu lượng độc nhất” của toàn hệ thống. Với cloud, có thể dùng các chỉ số traffic và DDoS mitigation của nhà cung cấp kèm flow logs khi được hỗ trợ.

**Lưu ý quyền riêng tư:** packet capture có thể chứa địa chỉ IP, nội dung không mã hóa hoặc metadata nhạy cảm. Chỉ thu ở phạm vi được phép, giới hạn số lượng/thời gian, bảo vệ file và thực hiện quy trình giữ/xóa chứng cứ.

## 10. Kiến trúc phòng thủ nhiều lớp trước volumetric DoS

Thứ tự phòng thủ nên bắt đầu ở **vị trí có thể hấp thụ/lọc traffic trước khi gây nghẽn**:

~~~mermaid
flowchart LR
    I[Internet traffic] --> U[ISP / upstream mitigation]
    U --> S[Scrubbing hoặc cloud DDoS protection]
    S --> E[Anycast edge / CDN / load balancer]
    E --> F[Firewall / ACL / IPS]
    F --> A[Origin / API / DNS service]
    E -. Edge metrics .-> O[SOC / NOC]
    F -. Flow logs .-> O
    A -. Availability metrics .-> O
    U -. Traffic / mitigation telemetry .-> O
~~~

| Lớp | Khả năng bảo vệ | Giới hạn / lưu ý |
|---|---|---|
| **ISP/upstream filtering** | Xử lý hoặc hạn chế lưu lượng trước đường vào doanh nghiệp | Cần quy trình phối hợp, chính sách và thỏa thuận dịch vụ |
| **Scrubbing center / DDoS protection** | Phân tích, loại traffic không mong muốn rồi chuyển “clean traffic” về đích | Phụ thuộc năng lực xử lý, phương án chuyển hướng, latency và đường trả về |
| **Anycast** | Phân tán traffic tới nhiều điểm hiện diện theo routing | Không bảo đảm mọi điểm có đủ năng lực; BGP/routing còn có bất đối xứng |
| **CDN/cache** | Hấp thụ request và giảm tải origin cho nội dung có thể cache | Không xử lý mọi UDP/ICMP; API không cache và origin bypass vẫn có rủi ro |
| **Network ACL/firewall** | Chặn traffic không được phép tới subnet/tài sản phía sau | Nếu đặt sau link nghẽn, không cứu được băng thông trước đó |
| **WAF/rate limit** | Chặn request HTTP/API bất thường, abuse ở L7 | Không phải giải pháp chính cho volumetric UDP/ICMP flood hoặc nghẽn upstream |
| **IDS/IPS/NDR** | Phát hiện mẫu bất thường và hỗ trợ phản ứng | Sensor có giới hạn throughput, visibility, false positive/negative |
| **Hạ tầng ứng dụng** | Cache, quota, timeout, graceful degradation và scale | Không thay được bảo vệ đường mạng; scale có chi phí và giới hạn |

### 10.1. Defense in depth không có nghĩa mọi lớp đều làm cùng việc

WAF có thể thấy request HTTP đã qua TLS termination, trong khi firewall L3/L4 thấy IP/port/protocol. IDS/IPS quan sát vị trí được đặt. Các biện pháp segmentation, VPN và IAM giúp bảo vệ **origin và mặt phẳng quản trị** khỏi đường truy cập trái phép. Để xử lý volumetric DoS, phải ưu tiên **năng lực upstream** và sau đó sử dụng các lớp còn lại để giữ môi trường ổn định.

## 11. Scrubbing center và chuyển hướng lưu lượng

**Scrubbing** là quá trình đưa traffic qua một hạ tầng có năng lực lớn để phân loại, loại hoặc giảm traffic không mong muốn và gửi traffic còn lại tới dịch vụ đích.

Có hai mô hình điển hình:

- **Always-on:** traffic thường xuyên đi qua hệ thống bảo vệ; thuận lợi cho phát hiện/giảm thiểu liên tục, đổi lại là yêu cầu thiết kế tuyến, chi phí, latency và phụ thuộc nhà cung cấp.
- **On-demand:** chỉ chuyển traffic khi được kích hoạt bởi ngưỡng/cảnh báo/quyết định vận hành; có thể giảm chi phí bình thường nhưng cần quản lý **thời gian kích hoạt, chuyển tuyến và trạng thái**.

### 11.1. Những vấn đề phải xác minh trước khi dùng

1. **Đường chuyển hướng:** route/BGP, DNS hoặc cơ chế cloud-specific; phải biết traffic nào được chuyển và ai được quyền kích hoạt.
2. **Đường “clean traffic”:** kết nối bảo vệ từ scrubbing về origin, có thể qua tunnel hoặc private link; cần kiểm tra MTU, route hai chiều, NAT và anti-spoofing.
3. **Phạm vi IP/protocol:** nhà cung cấp bảo vệ toàn bộ prefix, từng IP/service, UDP/ICMP hay chỉ HTTP?
4. **Nguồn và danh tính:** IP client thật có được giữ qua các proxy/tunnel không; rule rate limit có vô tình dùng IP của scrubbing provider?
5. **Tác động ứng dụng:** health check, session affinity, TCP connection reset, TLS, API gateway hoặc VPN có thay đổi khi reroute?
6. **Giới hạn và chi phí:** năng lực theo bps/pps, chính sách fair-use, cam kết thời gian kích hoạt, retention log và quyền truy cập telemetry.
7. **Tình trạng khi lỗi:** scrubbing provider hoặc tunnel lỗi thì có phương án fallback nào được phê duyệt?

Không xem “có hợp đồng anti-DDoS” là bằng chứng đủ. Cần **diễn tập kích hoạt**, đo end-to-end, xác minh traffic hợp lệ và rollback.

## 12. Các kỹ thuật điều phối mạng ở mức phòng vệ

### 12.1. Upstream ACL hoặc lọc theo đặc trưng traffic

Khi nhận diện một loại traffic thực sự không thuộc dịch vụ được cung cấp, đội NOC/ISP có thể thiết kế **lọc giao thức, cổng, đích hoặc đặc trưng luồng** ở điểm đủ gần nguồn hoặc trước link nghẽn. Cần xác định chính xác scope, vì chặn một giao thức phổ biến có thể làm hỏng ứng dụng hợp lệ.

### 12.2. Rate limiting và traffic policing

Giới hạn tốc độ có thể hữu ích khi lưu lượng không mong muốn tương đối rõ và **điểm policing còn đủ năng lực xử lý**. Tuy nhiên policing ngay sau link đã bão hòa vẫn không giải quyết congestion upstream; giới hạn quá thấp có thể ưu tiên nhầm kẻ tấn công hơn người dùng thật hoặc tạo false positive.

Không nên dùng một ngưỡng tĩnh cho mọi dịch vụ, vì lưu lượng DNS, VPN, API, streaming và tải cập nhật có profile rất khác.

### 12.3. BGP Flow Specification và các policy upstream

**BGP Flow Specification (FlowSpec)** có thể phân phối thông tin lọc traffic giữa các router/miền được phép theo RFC 8955 (IPv4) và các cơ chế liên quan. Đây là công cụ **vận hành của nhà mạng/đơn vị sở hữu mạng**, không phải một lệnh chặn tùy ý gửi ra Internet. Triển khai phải kiểm soát **nguồn chấp nhận policy, tính hợp lệ, phạm vi lan truyền, hành động và rollback**, vì policy sai có thể làm gián đoạn dịch vụ ở diện rộng.

### 12.4. Remote Triggered Black Hole (RTBH)

**Blackholing** chủ động làm rơi traffic tới một đích/prefix nhất định ở upstream hoặc tại điểm được cấu hình. Nó có thể bảo vệ **phần còn lại của hạ tầng** khi không thể tách traffic xấu khỏi tốt, nhưng **cũng chặn cả traffic hợp lệ tới đích bị blackhole**. Vì thế RTBH là biện pháp **giảm thiệt hại có đánh đổi lớn**, không phải cách khôi phục khả dụng cho dịch vụ đích.

Khi cân nhắc blackhole: xác định phạm vi IP, ảnh hưởng nghiệp vụ, người có quyền phê duyệt, điều kiện thu hồi, thời hạn và cách kiểm tra dịch vụ sau khi bỏ blackhole.

## 13. DNS, dịch vụ UDP và tính sẵn sàng của hạ tầng chung

### 13.1. DNS là cả phụ thuộc và mục tiêu

Khi authoritative DNS hoặc recursive resolver bị quá tải, người dùng có thể không truy cập được hệ thống dù web origin vẫn chạy. DNS còn là một trong các giao thức có thể bị lạm dụng trong reflection/amplification nếu dịch vụ và mạng nguồn cấu hình thiếu an toàn.

Các biện pháp thích hợp có thể gồm:

- **Authoritative DNS:** triển khai hạ tầng có khả năng phân tán/Anycast và bảo vệ upstream phù hợp; theo dõi response rate, error rate, độ trễ truy vấn, tính khả dụng từ nhiều khu vực.
- **Recursive DNS:** giới hạn client được phép sử dụng; tránh open resolver không có nhu cầu, theo dõi bất thường.
- **DNS Response Rate Limiting (RRL)** trên sản phẩm hỗ trợ và phù hợp với vai trò authoritative có thể giảm một số hành vi abuse; cần đánh giá false positive và traffic DNS hợp lệ.
- **DNS security và thay đổi định tuyến:** quản lý bản ghi, TTL và quy trình chuyển DNS/CDN, nhưng **DNS failover không tự bảo đảm** traffic đã được lọc hoặc origin không còn public.

### 13.2. Đừng làm hỏng giao thức điều khiển mạng khi lọc

Khi sự cố gắn với UDP/ICMP, đội vận hành có thể muốn chặn mọi UDP hoặc ICMP. Điều này có thể làm hỏng **DNS, VPN dùng UDP, ứng dụng thời gian thực, Path MTU Discovery và các chức năng IPv6**. Chính sách cần dựa vào dịch vụ, source/destination, interface, ICMP type/code và trạng thái, phối hợp với người phụ trách ứng dụng.

## 14. Cloud, CDN, VPN và phân đoạn mạng trong phòng chống DDoS

### 14.1. Dịch vụ Internet-facing trên cloud

Cloud có thể cung cấp edge phân tán, dịch vụ chống DDoS, load balancing và log. Nhưng **cần xác nhận đúng phạm vi bảo vệ**: public IP/hostname, protocol, region, network tier, loại resource và kịch bản traffic thực. Không suy rằng một tài nguyên “nằm trên cloud” đương nhiên có chống DDoS cho mọi đường đi.

Khi đưa website qua CDN/WAF:

- Chặn **direct-to-origin traffic** bằng security group/ACL, private networking và xác thực edge-origin nếu khả thi.
- Đảm bảo **mọi hostname và IPv4/IPv6 public** cần bảo vệ đều qua đúng điểm kiểm soát.
- Đo **upstream traffic và origin traffic** riêng để phân biệt lượng được hấp thụ ở edge.
- Xem lưu lượng không phải HTTP, như VPN, DNS, UDP service hoặc giao thức riêng, vì chúng có thể không đi qua CDN.

### 14.2. VPN và kết nối đối tác

VPN gateway có thể chịu ảnh hưởng nếu public IP hoặc upstream link của gateway bị nghẽn. Đường truyền được mã hóa **không tự chống volumetric DoS**, và chỉ tăng số VPN client được cấp phép không giải quyết vấn đề upstream. Nên cân nhắc đường truy cập dự phòng, kiểm soát danh tính/MFA, giới hạn quyền tới subnet quản trị, khả năng chống DDoS của endpoint VPN và quy trình liên lạc ngoài băng.

### 14.3. Phân đoạn, Wi-Fi và mạng nội bộ

Subnet segmentation, VLAN, ACL và microsegmentation giúp **giới hạn vùng ảnh hưởng** và ngăn lateral movement, nhưng **không giúp lấy lại băng thông Internet đã nghẽn**. Trong LAN, một nguồn traffic nội bộ lớn cũng có thể gây nghẽn uplink, Wi-Fi airtime hoặc switch; khi đó áp dụng NAC, QoS, phát hiện thiết bị nguồn và chính sách tại access/distribution layer.

Nếu dấu hiệu cho thấy nguồn nằm trong mạng nội bộ, cần điều tra endpoint/IoT, Wi-Fi guest và loop hoặc cấu hình broadcast sai trước khi mặc định đây là DDoS Internet.

## 15. Kiến trúc tham chiếu và ma trận trách nhiệm

Giả sử doanh nghiệp có **website public, API, authoritative DNS và VPN quản trị**. Internet vào trung tâm dữ liệu giới hạn dung lượng, trong khi dịch vụ web có thể đặt sau CDN/WAF và VPN đi tới gateway riêng.

~~~mermaid
flowchart TB
    U[Người dùng Internet] --> I[ISP / Upstream]
    T[Traffic bất thường] --> I
    I --> S[Upstream scrubbing / DDoS provider]
    S --> C[Anycast CDN + WAF cho Web/API]
    S --> G[Đường bảo vệ DNS/VPN phù hợp]
    C --> F[Cloud / DC network policy]
    F --> W[Private Web/API origin]
    F --> D[(Private database)]
    G --> V[VPN gateway / Authoritative DNS]
    V --> M[Management network với IAM / MFA]
    I -. Link metrics .-> N[NOC / SOC]
    S -. Mitigation event .-> N
    C -. WAF events .-> N
    F -. Flow logs .-> N
    W -. Availability metrics .-> N
    V -. Service metrics .-> N
~~~

Sơ đồ là **minh họa kiến trúc**, không có nghĩa DNS và VPN sẽ dùng đúng cùng một hạ tầng lọc: mỗi dịch vụ cần được bảo vệ theo giao thức, địa chỉ và hợp đồng thực tế.

| Vùng / thành phần | Vai trò | Owner và dữ liệu cần có |
|---|---|---|
| **ISP/upstream** | Nhìn traffic trước đường vào và triển khai lọc/chuyển hướng theo thỏa thuận | NOC + ISP: bps/pps, peering, thời gian kích hoạt |
| **Scrubbing / DDoS provider** | Hấp thụ/lọc, chuyển clean traffic | Network Security + provider: traffic trước/sau, mitigation action |
| **CDN/WAF** | Phục vụ cache và giảm HTTP request abuse | AppSec/SRE: edge request, final WAF action, origin hit |
| **Firewall/VPC/subnet** | Ngăn direct-origin access và kiểm soát network zones | Network/SecOps: route, ACL, flow log, NAT |
| **Web/API/DNS/VPN** | Cung cấp chức năng hợp lệ, authn/authz và khả dụng | Service owner/SRE: error rate, latency, health, dependency |
| **SOC/IR** | Tương quan tín hiệu, đưa ra quyết định sự cố, lưu bằng chứng | SOC/Incident commander: timeline, ticket, các quyết định |

### 15.1. Mục tiêu thiết kế đo được

Thay vì chỉ ghi “có chống DDoS”, nên mô tả:

- Những **dịch vụ/public IP/hostname** nào nằm trong phạm vi bảo vệ.
- Những loại traffic/protocol nào được bảo vệ và loại nào chưa được hỗ trợ.
- Nút nghẽn dự kiến và **điểm đo** của doanh nghiệp lẫn nhà cung cấp.
- Thời gian chuyển hướng/kích hoạt theo thỏa thuận (nếu có), tác động đến user SLI và đường rollback.
- Người có quyền điều phối ISP, thay DNS/routing, thay policy WAF hoặc duyệt blackhole.
- Ngưỡng cảnh báo và điều kiện kết thúc mitigation theo dữ liệu vận hành.

## 16. Runbook ứng phó volumetric DDoS

### Giai đoạn 0 — Chuẩn bị trước sự cố

1. **Inventory:** public IP, ASN/prefix thuộc tổ chức, DNS, CDN, WAF, VPN, ISP, cloud resources, BGP/route, circuit và sơ đồ phụ thuộc.
2. **Baseline và alert:** bps/pps/drop/error/SLI theo dịch vụ và link, kể cả giờ cao điểm hợp lệ.
3. **Liên hệ khẩn:** SOC/NOC/SRE, ISP, DDoS provider, quản lý sự cố và người có quyền đổi tuyến/blackhole.
4. **Chế độ bảo vệ:** xác nhận always-on hoặc on-demand, dịch vụ nào được bảo vệ, cách kích hoạt và lưu log.
5. **Thử nghiệm an toàn:** diễn tập tabletop hoặc test được nhà cung cấp phê duyệt, không tự tạo lưu lượng gây nghẽn.
6. **Phương án duy trì dịch vụ:** cache, status page, kênh liên lạc ngoài băng, ưu tiên tính năng trọng yếu và fallback đã kiểm thử.

### Giai đoạn 1 — Phát hiện và xác nhận

Xác minh **sự cố khả dụng** (người dùng timeout, DNS lỗi, VPN không kết nối), rồi kiểm tra dữ liệu **upstream + interface + service**. So giờ bắt đầu với thay đổi hệ thống, chiến dịch kinh doanh, sự kiện truyền thông hoặc lỗi ISP.

**Bằng chứng tối thiểu:** khoảng thời gian, IP/dịch vụ bị ảnh hưởng, inbound bps/pps ở các điểm đo, drop/latency, protocol distribution và tỷ lệ giao dịch hợp lệ thất bại. Nếu thiếu số liệu upstream, ghi rõ khoảng trống và yêu cầu provider hỗ trợ.

### Giai đoạn 2 — Phân loại và xác định nút nghẽn

| Câu hỏi | Nếu câu trả lời là “Có” | Hướng xử lý |
|---|---|---|
| Link/ISP bị bão hòa trước firewall? | bps/pps/drop cao và upstream xác nhận | Kích hoạt lọc/scrubbing **trước nút nghẽn** |
| Link ổn nhưng bảng trạng thái firewall cạn? | conntrack/NAT/state metrics bất thường | Điều chỉnh bảo vệ state, giảm tải và phối hợp upstream |
| Link ổn nhưng API quá tải? | HTTP request/CPU/database latency tăng | WAF/API rate limit, cache và tối ưu ứng dụng |
| DNS không phản hồi? | authoritative/recursive DNS lỗi hoặc quá tải | Phối hợp DNS provider/Anycast, kiểm tra resolver và dependency |
| Một subnet/Wi-Fi nội bộ nghẽn? | Uplink/airtime LAN bị dùng quá mức | Khoanh vùng nội bộ, NAC/QoS và xử lý nguồn |

**Lưu ý:** một sự cố có thể đồng thời thỏa nhiều hàng; khi đó ưu tiên hành động giảm điểm nghẽn tác động lớn nhất nhưng không bỏ qua các lớp còn lại.

### Giai đoạn 3 — Điều phối giảm thiểu

1. Báo ISP/DDoS provider bằng **mốc thời gian, tài sản đích, chỉ số quan sát và mức tác động**, không chỉ thông báo “đang bị DDoS”.
2. Kích hoạt hoặc điều chỉnh **scrubbing/edge filtering** theo runbook và thỏa thuận, đảm bảo traffic hợp lệ vẫn có đường đi.
3. Nếu lọc theo protocol/đích, đánh giá **dịch vụ hợp lệ** bị ảnh hưởng (DNS, ICMP cần thiết, VPN UDP, API, health checks).
4. Với dịch vụ web, dùng WAF/CDN/rate limit **nếu** traffic đã đến được edge HTTP; không coi đây là thay thế upstream filtering.
5. Khi dùng kỹ thuật định tuyến hoặc blackhole, cần **phê duyệt đúng thẩm quyền**, scope tối thiểu và phương án hoàn tác.
6. Duy trì đường quản trị và giám sát; cập nhật incident channel để các nhóm không đồng thời đưa ra thay đổi mâu thuẫn.

### Giai đoạn 4 — Đo kết quả và khôi phục

So **traffic trước/sau mitigation**, hiệu quả lọc, packet drop, latency, error rate, DNS/VPN availability và trải nghiệm người dùng thực. Không tuyên bố xử lý xong chỉ vì bps ở interface doanh nghiệp giảm: có thể lưu lượng hợp lệ cũng đã bị chặn.

Khi traffic ổn định theo cửa sổ quan sát phù hợp, lần lượt thu hồi policy khẩn, route thay đổi hoặc blackhole; tiếp tục giám sát **rebound**, bảo đảm route, DNS, ACL và log trở lại cấu hình mong muốn.

### Giai đoạn 5 — Hậu kiểm

Lập timeline, nguồn bằng chứng, mức độ ảnh hưởng, quyết định đã đưa ra, các sai sót/false positive, chi phí và rủi ro còn lại. Cập nhật playbook, threat model, ngưỡng cảnh báo, capacity plan và diễn tập. Ghi **cấu hình khẩn cấp nào vẫn đang còn hiệu lực** để không tạo điểm yếu lâu dài.

~~~mermaid
flowchart TD
    A[Cảnh báo về availability và traffic] --> B[Đối chiếu baseline và thay đổi gần đây]
    B --> C{Nút nghẽn chính ở đâu?}
    C -- Upstream / link --> D[ISP / scrubbing / filtering trước link]
    C -- Firewall state --> E[State protections + kiểm soát nguồn hợp lệ]
    C -- HTTP / API --> F[CDN / WAF / API quota]
    C -- LAN --> G[NAC / QoS / xử lý nội bộ]
    D --> H[Đo user SLI và traffic sau mitigation]
    E --> H
    F --> H
    G --> H
    H --> I{Khả dụng phục hồi và không chặn nhầm?}
    I -- Không --> C
    I -- Có --> J[Thu hồi policy khẩn + hậu kiểm]
~~~

## 17. Hai tình huống phân tích điển hình

### Tình huống A — Website tại datacenter bị nghẽn trước firewall

**Hiện tượng:** website, DNS nội bộ và VPN cùng timeout; CPU application thấp; firewall log tăng nhưng interface của tổ chức chỉ đo một mức inbound bị giới hạn. ISP báo traffic tới public prefix tăng rất mạnh và có drop ở tuyến upstream.

**Phân tích:** nhiều dịch vụ cùng bị ảnh hưởng và nút nghẽn nằm trước firewall. Đổi rule firewall tại datacenter có thể giảm tải server nhưng không giải phóng link. Điều phối với ISP/DDoS provider để lọc/chuyển hướng ở upstream; xác minh đường clean traffic về datacenter, đặc biệt route chiều về và MTU nếu dùng tunnel.

**Tiêu chí phục hồi:** người dùng từ nhiều mạng khác nhau truy cập được; packet drop tại link giảm; DNS/VPN kiểm tra đạt; hệ thống không bị blackhole nhầm; service SLI phục hồi.

### Tình huống B — Đợt ra mắt sản phẩm bị nhầm với DDoS

**Hiện tượng:** CDN và origin nhận nhiều traffic, request rate tăng theo sự kiện ra mắt, một số API chậm. Tuy nhiên link upstream còn dung lượng; tỷ lệ request được xác thực thành công cao và dữ liệu nghiệp vụ tăng tương ứng.

**Phân tích:** có khả năng là **flash crowd** kết hợp bottleneck của backend hơn là volumetric DDoS. Nên kiểm tra capacity origin, cache hit, connection pool và database; điều chỉnh cache/quota theo khách hàng, tránh chặn tất cả nguồn địa lý hoặc IP NAT đang có người dùng thật.

**Bài học:** ưu tiên **bằng chứng về nguồn, điểm nghẽn và tác động** thay vì một đường biểu đồ traffic đột biến.

### Tình huống C — WAF không báo bất thường nhưng DNS ngừng hoạt động

**Hiện tượng:** API và website không truy cập được theo tên miền ở một số khu vực; WAF log ít request, origin và database khỏe. Authoritative DNS ghi nhận tăng mạnh lưu lượng truy vấn và lỗi.

**Phân tích:** WAF HTTP không thấy mọi traffic DNS. Cần kiểm tra authoritative DNS, DNS provider/Anycast, hiệu quả rate limit đúng dịch vụ và upstream. Khi DNS được bảo vệ, xác minh cả IPv4/IPv6, nhiều khu vực và TTL/caching, tránh suy rằng WAF không ghi log nghĩa là không có sự cố.

## 18. Kiểm thử và diễn tập mà không tạo tấn công thật

**Không tự gửi flood, không kiểm thử khuếch đại/phản xạ với dịch vụ công cộng, không “stress test” đường mạng của nhà cung cấp khi chưa có phê duyệt**. Kiểm chứng thiết kế phòng vệ có thể thực hiện bằng cách an toàn hơn:

1. **Tabletop exercise:** giả lập số liệu bps/pps, cảnh báo và tình huống ISP yêu cầu quyết định blackhole.
2. **Review cấu hình:** xác minh asset scope, route, hợp đồng scrubbing, ACL origin, nguồn log và contact list.
3. **Failover ở môi trường test:** kiểm tra đường chuyển mạch đã được cấp phép, theo dõi DNS, tunnel, MTU, API latency và rollback.
4. **Traffic replay giới hạn trong lab được cách ly:** chỉ dùng lưu lượng tổng hợp nhỏ/được phê duyệt để kiểm tra parser, dashboard, alert và rule; không cần tạo nghẽn thật.
5. **Synthetic availability checks:** từ các vị trí do tổ chức kiểm soát, dùng tần suất an toàn để xác minh user path.
6. **Kịch bản log pipeline lỗi:** kiểm tra NOC/SOC có nhận ra mất telemetry và có cách lấy số liệu từ ISP/provider khác.

### Ma trận xác minh phòng vệ

| Kiểm thử | Điều cần chứng minh | Bằng chứng |
|---|---|---|
| T-01 | Đúng tài sản/public IP nằm trong phạm vi anti-DDoS | Provider scope, inventory, kiến trúc |
| T-02 | Có thể liên lạc và kích hoạt mitigation đúng thẩm quyền | Contact list, ticket rehearsal, thời gian phản hồi |
| T-03 | Dashboard có traffic trước/sau điểm lọc | Metrics của ISP/scrubbing và origin |
| T-04 | Origin không bị truy cập trực tiếp ngoài đường hợp lệ | Route, firewall policy, reachability test có phép |
| T-05 | Chặn một protocol nguy cơ không phá DNS/VPN/ICMP cần thiết | Danh sách ứng dụng phụ thuộc và bài thử allow/deny |
| T-06 | Có kế hoạch rollback tuyến/policy khẩn | Biên bản diễn tập, cấu hình và owner |
| T-07 | SOC phát hiện mất log/độ trễ ingest | Dashboard telemetry coverage, alert test |
| T-08 | Sau mitigation, dịch vụ hợp lệ phục hồi | Synthetic availability, error rate, latency, DNS/VPN tests |
| T-09 | Nhóm vận hành biết khi nào **không** nên blackhole | Kịch bản tác động nghiệp vụ và quyết định phê duyệt |
| T-10 | Hậu kiểm tạo hành động cải tiến có thể theo dõi | Ticket cải tiến, owner, điều kiện hoàn thành |

## 19. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Có firewall mạnh thì không bị volumetric DoS.” | Nếu link upstream nghẽn trước firewall, cần lọc/hấp thụ **ở upstream**. |
| “WAF là giải pháp cho mọi DDoS.” | WAF chủ yếu kiểm soát HTTP/L7; volumetric UDP/ICMP và nghẽn ISP cần năng lực mạng tương ứng. |
| “Traffic tăng đột biến chắc chắn là tấn công.” | Có thể flash crowd, backup, batch job hoặc lỗi định tuyến; phải xem baseline và tác động. |
| “Bps chưa đạt tốc độ cổng thì mạng không thể nghẽn.” | Thiết bị có thể hết năng lực pps, state, queue hoặc chịu QoS/policing. |
| “Blackhole sẽ khôi phục dịch vụ.” | Blackhole làm rơi cả traffic hợp lệ tới đích; chỉ là quyết định đánh đổi để giới hạn thiệt hại. |
| “Chặn mọi ICMP/UDP là an toàn hơn.” | Có thể phá DNS, VPN, PMTUD và IPv6; phải xét protocol/type theo nhu cầu. |
| “Firewall log ít nghĩa là traffic tấn công ít.” | Upstream có thể drop trước điểm quan sát; phải lấy dữ liệu ISP/provider. |
| “Tất cả IP nguồn trong sự cố reflection đều là attacker.” | Nhiều IP có thể thuộc reflector; cần hiểu mô hình source spoofing. |
| “DNS trỏ về CDN thì origin chắc chắn được bảo vệ.” | IP/route/hostname origin có thể bị truy cập trực tiếp; cần network/origin policy. |
| “DDoS được hấp thụ nghĩa là người dùng không còn lỗi.” | Cần đo tỷ lệ truy cập hợp lệ, false positive, latency và sự cố các phụ thuộc. |
| “Có cloud là luôn được chống DDoS đầy đủ.” | Mức bảo vệ phụ thuộc resource, giao thức, gói dịch vụ và cấu hình đúng. |
| “Rate limit tại server cứu được uplink Internet đã bão hòa.” | Giới hạn sau link không lấy lại dung lượng đã chiếm trước đó. |

## 20. Checklist chuẩn bị và vận hành

- [ ] Đã phân loại tài sản: website/API, DNS, VPN, public IP/prefix, ISP/circuit, cloud và các phụ thuộc.
- [ ] Có sơ đồ traffic path và xác định **điểm nghẽn** trước/sau firewall, CDN, scrubbing.
- [ ] Theo dõi **bps, pps, drop, state, errors và user-facing availability** theo dịch vụ.
- [ ] Có baseline phù hợp với giờ cao điểm và sự kiện nghiệp vụ hợp lệ.
- [ ] Có telemetry từ **ISP/upstream** chứ không chỉ từ máy chủ hoặc firewall nội bộ.
- [ ] Có quy trình liên hệ và kích hoạt mitigation theo thỏa thuận nhà cung cấp.
- [ ] Đã kiểm tra đúng phạm vi IP/protocol/region và năng lực DDoS provider.
- [ ] Biết cơ chế lọc/chuyển hướng ở upstream, scrubbing, Anycast/CDN và điều kiện kích hoạt.
- [ ] Có runbook BGP/policy do người đủ quyền thực hiện; blackhole chỉ dùng khi biết tác động.
- [ ] Ngăn origin bypass bằng route, security group/ACL, xác thực kết nối và kiểm tra IPv4/IPv6.
- [ ] Không làm hỏng DNS, VPN, ICMP/ICMPv6 cần thiết, health check và dịch vụ hỗ trợ.
- [ ] Kết hợp WAF/rate limit cho HTTP abuse nhưng không coi chúng thay upstream mitigation.
- [ ] Có giám sát DNS, IDS/IPS, firewall, VPN và cloud cùng dữ liệu trải nghiệm người dùng.
- [ ] Có kế hoạch liên lạc ngoài băng, rollback và thời điểm thu hồi policy khẩn.
- [ ] Có tiêu chí phục hồi dựa trên **lưu lượng hợp lệ thành công**, không chỉ traffic giảm.
- [ ] Có đánh giá rủi ro còn lại, quyền phê duyệt và hành động hậu kiểm sau sự cố.
- [ ] Diễn tập an toàn, không tạo traffic gây nghẽn thật hoặc sử dụng hệ thống người khác.

## 21. Câu hỏi tự kiểm tra

**1. Điều gì phân biệt volumetric DoS và application-layer DoS?**  
Volumetric nhắm tới khả năng truyền/chuyển tiếp traffic (bps/pps) là nút nghẽn chính; application-layer có thể làm CPU, worker, database hoặc logic nghiệp vụ quá tải chỉ bằng lượng request không quá lớn.

**2. Vì sao firewall đặt trong văn phòng không thể tự khôi phục một uplink Internet đã bị bão hòa?**  
Vì traffic đã chiếm băng thông trên đoạn upstream trước khi tới firewall. Cần lọc/chuyển hướng hoặc hấp thụ traffic trước nút nghẽn.

**3. bps và pps nói lên điều khác nhau như thế nào?**  
bps đo tốc độ dữ liệu bit; pps đo số packet phải xử lý mỗi giây. Gói nhỏ với pps lớn có thể quá tải thiết bị dù bps chưa đạt trần danh nghĩa.

**4. Reflection và amplification liên quan gì đến spoofing?**  
Khi địa chỉ nguồn giả mạo có thể rời mạng, dịch vụ trung gian có thể gửi phản hồi tới nạn nhân. Amplification có thể làm khối lượng phản hồi lớn hơn request. Phòng vệ gồm source-address validation, hạn chế dịch vụ có nguy cơ và lọc upstream.

**5. Nếu WAF không ghi nhiều request nhưng người dùng không truy cập được dịch vụ, nên kiểm tra gì?**  
Kiểm tra DNS, VPN, upstream link, packet drop, route, cloud/CDN, logging coverage và traffic không phải HTTP; WAF chỉ thấy những request đi qua và được nó ghi log.

**6. RTBH nên được xem là giải pháp khôi phục dịch vụ hay giảm thiệt hại?**  
Chủ yếu là **giảm thiệt hại**, vì blackhole làm mất cả traffic hợp lệ tới đích. Cần owner phê duyệt, giới hạn scope và kế hoạch hoàn tác.

**7. Một biểu đồ inbound traffic tăng mạnh đã đủ để kết luận DDoS chưa?**  
Chưa. Cần xác minh thay đổi hợp lệ, baseline, phân bố traffic, điểm nghẽn, đường đi và tác động đến user SLI.

**8. Vì sao không nên chặn toàn bộ ICMPv6 để chống volumetric traffic?**  
ICMPv6 chứa thông điệp cần thiết cho IPv6 như Neighbor Discovery trên liên kết và Packet Too Big cho PMTU. Chặn quá mức có thể làm hỏng kết nối hợp lệ.

**9. Biện pháp nào giúp tránh bị lợi dụng làm nguồn traffic giả địa chỉ trên mạng của mình?**  
Source Address Validation/anti-spoofing tại biên mạng theo BCP 38/BCP 84 và quản lý chính sách định tuyến, prefix/nguồn được phép.

## 22. Tài liệu tham khảo

- [RFC 4732 — Internet Denial-of-Service Considerations](https://www.rfc-editor.org/rfc/rfc4732): các đặc trưng và hướng suy nghĩ về khả năng phục vụ khi bị DoS.
- [RFC 2827 / BCP 38 — Network Ingress Filtering](https://www.rfc-editor.org/rfc/rfc2827): phòng ngừa lưu lượng mang địa chỉ nguồn giả mạo.
- [RFC 3704 / BCP 84 — Ingress Filtering for Multihomed Networks](https://www.rfc-editor.org/rfc/rfc3704): mở rộng source-address validation cho mạng có nhiều đường kết nối.
- [RFC 5358 — Preventing Use of Recursive Nameservers in Reflector Attacks](https://www.rfc-editor.org/rfc/rfc5358): cấu hình giảm rủi ro open recursive DNS bị lạm dụng.
- [RFC 8955 — Dissemination of Flow Specification Rules](https://www.rfc-editor.org/rfc/rfc8955): BGP FlowSpec cho IPv4 và điều kiện vận hành phù hợp.
- [RFC 8201 — Path MTU Discovery for IPv6](https://www.rfc-editor.org/rfc/rfc8201): nhu cầu ICMPv6 Packet Too Big và PMTU.
- [NIST SP 800-61 Rev. 3 — Incident Response Recommendations and Considerations](https://csrc.nist.gov/pubs/sp/800/61/r3/final): tổ chức hoạt động ứng phó sự cố và cải tiến liên tục.
- [NIST Cybersecurity Framework 2.0](https://www.nist.gov/cyberframework): quản trị, bảo vệ, phát hiện, ứng phó và khôi phục rủi ro an ninh mạng.

**Ghi nhớ:** Volumetric DoS là bài toán **tính sẵn sàng của đường truyền và năng lực xử lý traffic**, không chỉ là một loại gói “xấu” có thể chặn ở firewall. Phòng vệ hiệu quả bắt đầu từ **xác định nút nghẽn**, đo **bps/pps và trải nghiệm người dùng**, phối hợp **ISP/upstream, scrubbing và cloud/edge**, kiểm soát những đường vòng vào origin và xác minh rằng **lưu lượng hợp lệ thực sự được phục hồi** sau mỗi quyết định giảm thiểu.
