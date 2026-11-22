# Kiểm soát lưu lượng, nhật ký mạng và xử lý sự cố kết nối

## 1. Vì sao cần thiết kế kiểm soát và khả năng quan sát mạng?

Một ứng dụng triển khai thành công lên cloud chưa chắc có đường truyền đúng, an toàn và dễ vận hành. Booking API có thể hoạt động ở môi trường thử nghiệm nhưng gặp sự cố khi lên production vì DNS trỏ sai địa chỉ private, route thiếu chiều về, firewall chặn health check, NAT hết năng lực xử lý kết nối hoặc backend phản hồi chậm.

**Kiểm soát lưu lượng mạng** xác định ai được kết nối tới đâu, bằng giao thức nào và theo đường đi nào. **Nhật ký mạng** ghi lại tín hiệu quan sát từ các điểm trên đường truyền để phục vụ vận hành, điều tra truy cập và phát hiện bất thường. **Xử lý sự cố kết nối** là hoạt động đối chiếu các tín hiệu đó theo từng lớp, từ phân giải tên và định tuyến đến TLS và logic ứng dụng.

Ba năng lực này phải đi cùng nhau. Một chính sách có thể chặn đúng traffic nguy hiểm nhưng nếu thiếu kiểm thử và log sẽ khó biết liệu traffic hợp lệ có bị ảnh hưởng. Ngược lại, nhiều log không có owner, thời gian lưu và câu hỏi điều tra cụ thể chỉ làm tăng chi phí.

Bài học thuộc module **CLOUD_ARCHITECTURE**, tập trung vào cách thiết kế đường truyền khi đưa ứng dụng lên cloud, đồng thời cân bằng **độ tin cậy, bảo mật, khả năng mở rộng, hiệu năng, chi phí và vận hành** theo tư duy Well-Architected.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt ingress, egress, east-west và các luồng kết nối hybrid.
2. Giải thích vai trò của route, DNS, firewall, ACL, security group, load balancer, WAF, NAT và IAM.
3. Xây dựng ma trận lưu lượng tối thiểu dựa trên nguồn, đích, giao thức, cổng và yêu cầu nghiệp vụ.
4. Đọc và liên kết flow log, DNS log, firewall log, load balancer log và application trace, không diễn giải quá giới hạn của từng nguồn.
5. Chẩn đoán timeout, connection refused, lỗi DNS, TLS, HTTP và các sự cố kết nối private/hybrid.
6. Tổ chức quy trình thay đổi, cảnh báo và runbook có tiêu chí kiểm chứng kết quả.

## 2. Lập bản đồ luồng trước khi viết policy

Một sơ đồ chỉ có VPC/VNet và subnet chưa đủ để đánh giá kết nối. Cần chỉ rõ traffic đi từ **nguồn nào** đến **đích nào**, qua **điểm kiểm soát nào**, và làm thế nào biết đường truyền đang hoạt động.

Giả sử một hệ thống đặt phòng có người dùng bên ngoài, Booking API, cơ sở dữ liệu managed, dịch vụ queue, nhà cung cấp thanh toán và hệ thống kế toán on-prem:

~~~mermaid
flowchart LR
    User["Người dùng Internet"] --> Edge["Public DNS / WAF / Load Balancer"]
    Edge --> API["Booking API - private workload"]
    API --> DB[("Private Booking DB")]
    API --> Queue[["Private queue endpoint"]]
    API --> NAT["Controlled egress / NAT"]
    NAT --> Pay["Payment provider"]
    Office["On-prem accounting"] <-->|"VPN / private connectivity"| Gateway["Hybrid gateway"]
    Gateway --> API
~~~

*Đây là sơ đồ logic. DNS thực hiện phân giải tên chứ không trực tiếp chuyển tiếp request HTTP; cách đặt WAF, load balancer, NAT và private endpoint thay đổi theo dịch vụ cloud.*

| Nhóm traffic | Ví dụ | Câu hỏi thiết kế |
|---|---|---|
| **Ingress** | Internet → public endpoint → Booking API | Điểm vào nào được công khai? TLS kết thúc ở đâu? Backend có bị lộ trực tiếp không? |
| **East-west** | API → DB, API → queue | Service nào thực sự cần giao tiếp? Đường truyền có phân quyền và cô lập phù hợp không? |
| **Egress** | Booking API → payment provider | Đường ra ở đâu, IP sau SNAT là gì, ai kiểm soát đích và chi phí? |
| **Hybrid** | Cloud ↔ on-prem qua VPN/private link | CIDR có chồng lấn, DNS và route hai chiều có đúng, dự phòng có được kiểm thử? |
| **Control plane** | Pipeline → cloud API thay route/firewall | Ai có quyền thay đổi và ai nhận audit/cảnh báo? |

**Data plane** là traffic ứng dụng thực tế. **Control plane** là các API và thao tác cấu hình hạ tầng. Cloud audit log ghi thay đổi control plane không đồng nghĩa ghi được toàn bộ packet data plane.

### Mẫu mô tả một đường kết nối

| Trường | Ví dụ: Booking API → Database | Ý nghĩa |
|---|---|---|
| Source | Workload identity Booking + private subnet | Ai gọi, điểm xuất phát ở đâu? |
| Destination | Private DB hostname/endpoint | Đích nào có quyền nhận? |
| Transport | TCP 5432 | Giao thức và cổng thực tế |
| Business purpose | Đọc/ghi giao dịch đặt chỗ | Vì sao kết nối cần tồn tại? |
| Security | DB authentication, TLS, network policy | Bảo vệ dữ liệu và kiểm soát quyền |
| Route | Private network path | Không đi qua Internet ngoài ý muốn |
| Operational target | Timeout và error budget theo hành trình | Cách xử lý khi DB không sẵn sàng |
| Evidence | Effective routes, flow log, DB metrics, app trace | Cách xác minh thành công và chẩn đoán lỗi |

Những kết nối chưa có chủ sở hữu hoặc lý do nghiệp vụ nên được xem lại trước khi mở policy rộng.

## 3. Các lớp có thể làm một kết nối thất bại

**Mở được cổng không đồng nghĩa API trả lời thành công.** Một request đi qua nhiều bước:

| Lớp | Nhiệm vụ | Dấu hiệu lỗi | Nguồn bằng chứng |
|---|---|---|---|
| **DNS / service discovery** | Phân giải hostname thành endpoint | NXDOMAIN, SERVFAIL, IP trả về sai | Resolver, private zone, DNS query log |
| **Routing** | Chọn next hop và đường trả lời | Không tới đích, đi sai gateway | Effective route, BGP, VPN/peering |
| **Network policy** | Quyết định allow/deny theo IP, port, protocol | Timeout, deny, reset tùy vị trí chặn | Effective firewall/ACL rules, flow log |
| **NAT / proxy** | Dịch địa chỉ/port, chuyển tiếp và lọc | Cạn SNAT port, IP nguồn sai, proxy lỗi | NAT/proxy metrics và connection log |
| **Load balancer** | Chọn backend khỏe và xử lý listener | Target unhealthy, 502/503/504 tùy hệ thống | Listener, target health, access log |
| **Transport / TLS** | Thiết lập phiên TCP/TLS | SYN timeout, RST, lỗi SNI/chứng chỉ | Connection probe, TLS diagnostic |
| **Application / identity** | Xử lý HTTP, authorization và dependency | 401, 403, 404, 429, 5xx, request chậm | App log, trace, auth log, DB metric |

### 3.1. Stateful khác stateless ra sao?

**Stateful firewall/security policy** theo dõi trạng thái kết nối. Gói phản hồi thuộc phiên đã được phép có thể đi qua mà không cần một rule phản hồi riêng trong cùng lớp. AWS Security Groups, Azure Network Security Groups là ví dụ phổ biến về cơ chế stateful.

**Stateless ACL** xét từng chiều riêng; trong một số thiết kế phải cấu hình cả rule outbound/inbound cho traffic phản hồi và dải ephemeral port phù hợp. AWS Network ACL là ví dụ về lớp stateless.

Một đường truyền có thể đi qua **nhiều lớp policy**. Một security group stateful cho phép kết nối không khiến một ACL hoặc firewall trung tâm tự động cho phép. Thứ tự ưu tiên, implicit rules và deny semantics khác nhau giữa nền tảng; phải kiểm tra **effective policy**, không chỉ nhìn một rule tên ALLOW.

### 3.2. Network policy không thay thế IAM

Firewall trả lời “ai có thể kết nối đến endpoint nào”. IAM, workload identity, chứng chỉ và quyền ứng dụng trả lời “ai được thực hiện hành động nào trên tài nguyên nào”. DB ở private subnet vẫn cần authentication và phân quyền; WAF không ngăn được lỗi API cho phép người dùng xem dữ liệu đặt chỗ của người khác nếu business authorization sai.

## 4. Thiết kế kiểm soát ingress

Với ứng dụng HTTPS công khai, một phương án hợp lý là công bố điểm vào được quản lý rồi giới hạn backend:

1. Public DNS trỏ tới public edge/load balancer.
2. Edge áp dụng TLS, chứng chỉ và quy tắc HTTP/WAF khi cần; WAF chủ yếu kiểm soát lớp ứng dụng HTTP(S), không thay thế firewall TCP chung.
3. Load balancer phân phối request tới backend khỏe mạnh và thực hiện health probe với cổng/đường dẫn phù hợp.
4. Booking API chỉ nhận traffic từ nguồn ingress hợp lệ, tránh mở IP public trực tiếp cho backend.
5. API xác thực, kiểm tra quyền và truyền tiếp tới DB/queue theo policy nội bộ.

| Source | Destination | Protocol/port | Chính sách mong muốn | Kiểm chứng |
|---|---|---|---|---|
| Internet | Public load balancer | TCP 443 | Allow với TLS/WAF theo yêu cầu | HTTPS và LB access log |
| LB và nguồn health check hợp lệ | Booking API | TCP 8080 | Allow đúng phạm vi | Target healthy và request trace |
| Internet trực tiếp | Private Booking API | TCP 8080 | Không có đường truy cập / deny | Thử từ nguồn ngoài phạm vi |
| Internet trực tiếp | Private DB | TCP 5432 | Không có đường truy cập / deny | Network path và effective policy |

Bảng trên là **ý định thiết kế**, không phải syntax firewall dùng chung. Địa chỉ thật của health probe, chế độ proxy và đường đi giữa LB–backend phụ thuộc sản phẩm. Một health check bị rule mới chặn có thể khiến LB đánh dấu toàn bộ backend không khỏe dù ứng dụng còn chạy.

**HTTP 403 không tự chứng minh lỗi firewall.** Nó có thể phát sinh tại WAF, gateway hoặc ứng dụng. Tương tự, 502/503/504 từ LB không tự xác định là route sai: backend, timeout, health check hoặc dependency cũng có thể gây lỗi.

## 5. Kiểm soát egress: NAT, proxy và private endpoint

### 5.1. Nguồn IP bên ngoài nhìn thấy

Workload private thường truy cập đối tác bên ngoài qua NAT gateway hoặc proxy. Dịch địa chỉ nguồn (SNAT) có thể làm IP/cổng public khác với IP/cổng ở container:

~~~text
Trước SNAT: 10.20.4.18:53124   -> 198.51.100.40:443
Sau SNAT:   203.0.113.17:41002 -> 198.51.100.40:443
Phản hồi:   198.51.100.40:443 -> 203.0.113.17:41002
~~~

*198.51.100.0/24 và 203.0.113.0/24 là dải IP dành cho tài liệu; số port mang tính minh họa.*

Hệ quả:

- Đối tác dùng **IP allowlist** cần được cung cấp IP egress sau NAT, không phải IP private của app.
- **SNAT port exhaustion** có thể xảy ra khi số kết nối/port khả dụng không đáp ứng tải; giới hạn và khả năng mở rộng khác nhau theo sản phẩm.
- Connection pooling, keep-alive, timeout, retry và số workload dùng chung NAT ảnh hưởng tới số phiên hoạt động.
- NAT không tự giới hạn được mọi loại đích và không thay thế ứng dụng xác thực với đối tác.
- Đường qua NAT, firewall tập trung hoặc xuyên zone/region có thể phát sinh network cost đáng kể.

Khi kết nối tới một managed cloud service, **private endpoint/private connectivity** có thể là lựa chọn phù hợp nếu dịch vụ hỗ trợ. Tuy nhiên phải kiểm tra đồng thời endpoint, DNS private, route, policy, IAM và network association. Một private endpoint đã tạo nhưng workload vẫn giải hostname thành IP public là lỗi cấu hình khá phổ biến.

### 5.2. East-west và cô lập phạm vi lỗi

Giữa các workload nội bộ, chỉ mở những luồng có yêu cầu thực tế. Booking API có thể cần DB và queue; Notification worker không mặc nhiên cần quyền DB production. Cơ chế áp dụng có thể là security group/NSG/firewall, Kubernetes NetworkPolicy, service mesh policy và workload identity phù hợp.

**Private IP không tự đồng nghĩa trusted.** Một workload nội bộ bị chiếm quyền vẫn có thể truy cập các destination mà mạng và IAM cho phép. Khi khóa traffic east-west phải tính tới DNS, time sync, health check, secrets, telemetry và các endpoint nền tảng để tránh làm gián đoạn chính workload cần bảo vệ.

## 6. Routing và DNS: tìm nguyên nhân trước khi mở firewall

### 6.1. Kiểm tra đường đi và đường về

Routing quyết định next hop của packet; thiết bị stateful trên đường đi có thể cần thấy cả hai chiều của cùng phiên. Những vấn đề hay gặp:

- **CIDR chồng lấn:** on-prem và cloud dùng dải IP trùng nhau, khiến route không rõ hoặc không thể kết nối theo cách dự tính.
- **Thiếu return route:** cloud biết đường tới on-prem nhưng on-prem không biết đường về workload.
- **Asymmetric routing:** chiều đi qua firewall A, chiều về qua firewall B; phiên không được nhận diện đúng và có thể bị chặn.
- **Transit giả định sai:** peering A–B không mặc nhiên cho A đi qua B để tới C; hành vi tùy sản phẩm và cấu hình.
- **Routing sai next hop:** traffic đi qua NAT/firewall/zone không phù hợp hoặc khác sơ đồ.

Trong nhiều ngữ cảnh định tuyến IP, prefix cụ thể hơn được ưu tiên (longest-prefix match); cách xử lý route cùng độ dài/nguồn route khác nhau theo cloud. Cần xem **effective route** tại đúng subnet/interface và các route quảng bá qua hybrid gateway.

### 6.2. DNS và các cấu hình private

- **NXDOMAIN:** resolver cho biết tên không tồn tại trong ngữ cảnh truy vấn; kiểm tra zone, bản ghi và search suffix.
- **SERVFAIL:** resolver không hoàn tất truy vấn; kiểm tra forwarding, upstream, DNSSEC nếu liên quan và độ sẵn sàng của DNS.
- **Trả IP public thay vì private:** kiểm tra private hosted/managed zone, network association, resolver và split-horizon DNS.
- **IP cũ sau thay đổi:** xem TTL, cache của resolver/ứng dụng và thời gian chuyển đổi.
- **DNS đúng nhưng TCP lỗi:** chuyển sang route, policy, listener và TLS.

**Chạy phép thử từ đúng môi trường lỗi.** Laptop vận hành, VM staging và pod production có thể dùng resolver, network và private zone khác nhau nên trả kết quả DNS khác nhau.

## 7. Phân loại nhật ký mạng và giới hạn quan sát

Không có một nguồn log nào giải thích toàn bộ đường truyền.

| Nguồn | Giải đáp điều gì? | Giới hạn |
|---|---|---|
| **VPC/VNet flow logs** | Source/destination IP, port, protocol, bytes/packets, action, thời gian tùy dịch vụ | Thường không có payload; ACCEPT không chứng minh app thành công; có thể sampling/aggregation |
| **Firewall logs** | Rule nào allow/deny, traffic nào, đôi khi NAT và threat verdict | Không thấy mọi xử lý phía ứng dụng |
| **DNS query logs** | Hostname nào được hỏi, từ resolver nào, kết quả gì | Trả đúng IP không chứng minh TCP/TLS thông suốt |
| **Load balancer access/health logs** | Listener/target nào xử lý, status, thời gian, tình trạng health | Mã lỗi gateway chưa đủ xác định nguyên nhân gốc |
| **NAT/proxy telemetry** | Tình trạng translation, số connection, lỗi port và throughput tùy sản phẩm | Không phải mọi dịch vụ đều xuất từng bản ghi phiên |
| **VPN/BGP metrics** | Tunnel và peer, throughput, packet drop, route trạng thái | Tunnel up chưa đủ để chứng minh ứng dụng kết nối thành công |
| **Host/container metrics** | Socket, retransmission, conntrack, readiness, pod policy | Không phản ánh toàn bộ cloud firewall trước host |
| **Cloud audit logs** | Ai đổi route, DNS, IAM, LB, policy và lúc nào | Ghi control plane, không phải từng packet |
| **Application logs/traces** | Request ID, timeout, dependency, lỗi nghiệp vụ | Có thể không biết packet bị chặn ở lớp nào |

Các tên dịch vụ thường gặp là **AWS VPC Flow Logs**, **Azure Virtual Network flow logs** và **Google Cloud VPC Flow Logs**. Chúng khác nhau về phạm vi, trường dữ liệu, sampling, aggregation, độ trễ và cách bật. Không được giả định log ghi mọi packet hay có schema giống nhau.

### 7.1. Ví dụ bản ghi flow log

~~~json
{
  "startTime": "2026-11-18T03:10:00Z",
  "endTime": "2026-11-18T03:11:00Z",
  "srcIp": "10.20.4.18",
  "srcPort": 53124,
  "dstIp": "10.20.8.25",
  "dstPort": 5432,
  "protocol": "TCP",
  "action": "ACCEPT",
  "bytes": 18452,
  "packets": 38,
  "interfaceId": "example-interface"
}
~~~

*Schema JSON này chỉ dùng để học cách phân tích; đây không phải format chuẩn của bất kỳ nhà cung cấp cloud nào.*

Đối chiếu **5-tuple** gồm source IP, source port, destination IP, destination port và protocol. Hỏi thêm: log nằm trước hay sau NAT? Đây là traffic chiều đi hay chiều về? Trường action phản ánh quyết định ở lớp nào? Thời gian và số liệu được tổng hợp hay sampling ra sao?

Một record có **ACCEPT** chỉ cho biết lớp ghi log cho phép/quan sát luồng theo ngữ nghĩa của nó. Destination vẫn có thể không lắng nghe, chứng chỉ sai, proxy từ chối hoặc API trả lỗi. Một record **REJECT** cần khớp đúng địa chỉ, port, thời gian và vị trí quan sát trước khi liên hệ với sự cố đang điều tra.

**Không thấy log không chứng minh không có traffic.** Có thể chưa bật thu thập, lọc, sampling, log đến muộn, log nằm ở interface khác hoặc đường đi không được loại log đó hỗ trợ. Trước khi kết luận cần xác minh cấu hình và độ phủ của pipeline.

### 7.2. Thu thập log với quyền và thời hạn phù hợp

Flow log, hostname, IP, request URL và timestamp có thể chứa dữ liệu cần bảo vệ. Hãy xác định retention, mã hóa, quyền truy cập, khu vực lưu, masking dữ liệu nhạy cảm và quy trình xóa theo chính sách. Không ghi token, mật khẩu hoặc payload giao dịch vào log để phục vụ debug. Packet capture có thể nhìn thấy dữ liệu nhạy cảm; chỉ bật có mục tiêu, thời gian ngắn và quyền phù hợp.

## 8. Thiết kế pipeline quan sát mạng

~~~mermaid
flowchart LR
    Flow["Flow / Firewall logs"] --> Collect["Collect + Normalize"]
    DNS["DNS / LB logs"] --> Collect
    Audit["Control-plane audit"] --> Collect
    Collect --> Store[("Log store: IAM + retention")]
    Store --> Search["Search / Investigation"]
    Store --> Detect["Detection rules"]
    Detect --> Alert["Actionable alert + owner"]
    NAT["NAT / VPN / LB metrics"] --> Monitor["Monitoring"]
    Monitor --> Alert
    Trace["Application traces"] --> Search
~~~

Một pipeline dùng được cần có:

1. **Độ phủ rõ ràng:** network/subnet/interface nào đang bật logging; đường managed service, gateway, NAT, queue nào không có dữ liệu?
2. **Thời gian có thể liên kết:** UTC hoặc timezone rõ ràng, clock đồng bộ, khoảng thời gian quan sát và độ trễ ingestion.
3. **Trường tra cứu:** 5-tuple, network/interface, rule ID, request/trace ID hoặc connection ID nếu có.
4. **Theo dõi chính pipeline:** mất log, lỗi parsing, trễ ingestion, quota và dung lượng.
5. **Owner cảnh báo:** cảnh báo mô tả tác động, người nhận, bằng chứng và hướng runbook.
6. **Quyền và chi phí:** lọc nguồn cần thiết, retention hợp lý và dashboard phân bổ chi phí log.

| Chỉ số | Phục vụ việc gì? | Cảnh báo về diễn giải |
|---|---|---|
| DNS SERVFAIL/NXDOMAIN theo resolver | Phát hiện vấn đề tên của dịch vụ trọng yếu | NXDOMAIN có thể do client hỏi tên không tồn tại; cần xem ngữ cảnh |
| Firewall deny theo rule/đích | Nhận diện policy sai hoặc traffic không mong muốn | Nhiều deny chưa chắc là lỗi người dùng |
| LB healthy targets và lỗi target | Phát hiện backend không khỏe hoặc chậm | Health check sai cũng gây unhealthy |
| NAT port/connection utilization | Dự báo cạn kết nối outbound | Tên metric và giới hạn khác nhau theo provider |
| VPN/BGP tunnel/peer health | Giám sát kết nối hybrid | Tunnel up không đồng nghĩa route và ứng dụng thông suốt |
| Egress traffic và log ingestion | Theo dõi chi phí, luồng bất thường | Cần đối chiếu traffic nghiệp vụ và đường đi thật |

## 9. Runbook chẩn đoán kết nối theo từng lớp

### Bước 0: Ghi nhận triệu chứng và phạm vi

Thu thập source workload/subnet, destination hostname/IP/port, giao thức, thời điểm bắt đầu, môi trường và mức ảnh hưởng tới người dùng. Phân biệt **NXDOMAIN, timeout, connection refused, TLS error, HTTP 4xx/5xx**. Kiểm tra thay đổi gần đây về DNS, IAM, route, security rule, deploy, TLS và firewall. Chỉ định incident owner và dùng cùng time window giữa các nguồn log.

### Bước 1: Kiểm tra DNS từ đúng nguồn lỗi

Giải hostname từ pod/VM hoặc môi trường có resolver giống client lỗi. Nếu IP không đúng, xem private zone, forwarding, search suffix, bản ghi và cache. Nếu DNS đúng, chuyển sang routing thay vì tiếp tục sửa DNS.

### Bước 2: Kiểm tra route đi và về

Đối chiếu IP đích, route hiệu lực, next hop, peering/transit, BGP/VPN, NAT/proxy và return path. Đừng mặc định thấy một chiều route hợp lệ là phiên TCP sẽ hoàn tất. Với stateful firewall, xem liệu phản hồi có quay về qua đúng điểm có trạng thái phiên.

### Bước 3: Kiểm tra policy ở mọi lớp

Rà firewall/security group/ACL ở cloud, network policy tại container và proxy/service mesh nếu có. Xem source/destination **thực tế sau NAT** khi liên quan, direction, protocol/port, priority, default deny và trạng thái connection. Tìm record phù hợp trong firewall/flow log.

### Bước 4: Kiểm tra listener, transport và TLS

Xác minh cổng đích đang lắng nghe, load balancer có backend healthy và TCP handshake hoạt động. Nếu thấy SYN timeout, RST hoặc retransmission, điều tra tiếp endpoint/network; nếu lỗi TLS, kiểm tra hostname, SNI, chứng chỉ, thời hạn, trust chain và cấu hình proxy.

**Ping không thành công không chứng minh kết nối TCP thất bại**, vì ICMP có thể bị chặn. Traceroute cũng có thể không hiển thị đủ hop trong cloud; chỉ xem là bằng chứng bổ trợ.

### Bước 5: Kiểm tra HTTP, auth và dependency ứng dụng

Khi TCP/TLS thành công nhưng request còn lỗi, xem WAF/gateway status, application logs, request ID và distributed traces. Timeout có thể do DB lock, thread pool, queue hoặc upstream xử lý chậm, không chỉ do đường truyền.

### Bước 6: Sửa có kiểm soát và đo lại

Chỉnh nguyên nhân ở phạm vi tối thiểu bằng quy trình thay đổi được phép. Sau đó thử **từ nguồn bị lỗi ban đầu**, kiểm tra các luồng được phép và bị chặn, đo lại SLO/độ trễ, theo dõi một khoảng phù hợp và ghi lại rủi ro còn lại.

~~~mermaid
flowchart TD
    Start["Kết nối lỗi: source / dest / time"] --> Dns{"DNS đúng IP?"}
    Dns -- "Không" --> FixDns["Resolver / zone / forwarding"]
    Dns -- "Có" --> Route{"Route hai chiều đúng?"}
    Route -- "Không" --> FixRoute["Route / NAT / VPN / transit"]
    Route -- "Có" --> Policy{"Policy có cho phép?"}
    Policy -- "Không" --> FixPolicy["Rule / direction / priority"]
    Policy -- "Có" --> Transport{"Listener, TCP, TLS ổn?"}
    Transport -- "Không" --> FixTransport["Health / port / cert / SNAT / MTU"]
    Transport -- "Có" --> App{"L7 và ứng dụng thành công?"}
    App -- "Không" --> FixApp["WAF / auth / app trace / dependency"]
    App -- "Có" --> Verify["Đo lại từ nguồn và xác nhận SLO"]
~~~

Sơ đồ là quy trình gợi ý, không ngăn điều tra song song nhiều giả thuyết khi có bằng chứng rõ.

## 10. Công cụ chẩn đoán thực tế

Các ví dụ sau chỉ dùng hostname mô phỏng; chạy trong môi trường được phép và tránh quét mạng production ngoài phạm vi incident.

### 10.1. Phân giải tên

~~~bash
# Chạy từ chính workload/network có triệu chứng.
nslookup booking.internal.example
dig booking.internal.example A
dig booking.internal.example AAAA
dig booking.internal.example @10.20.0.2
~~~

So sánh resolver mặc định với resolver chỉ định. Công cụ DNS và thư viện phân giải tên của ứng dụng có thể dùng cache/search domain khác nhau, nên kết quả phải đối chiếu với hành vi runtime.

### 10.2. TCP, TLS và HTTP

~~~bash
# Kiểm tra đúng TCP port.
nc -vz booking.internal.example 443

# Đo thời gian phân giải, kết nối, TLS và tổng request.
curl -sS -o /dev/null --connect-timeout 3 --max-time 10 \
  -w 'dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} total=%{time_total} code=%{http_code}\n' \
  https://booking.internal.example/health

# Xác minh handshake/certificate với hostname SNI.
openssl s_client -connect booking.internal.example:443 \
  -servername booking.internal.example
~~~

Không dùng tùy chọn tắt kiểm tra TLS để “sửa” lỗi chứng chỉ ở production. Khi bật verbose HTTP hoặc packet capture, cần tránh để lộ token/cookie và dữ liệu cá nhân.

### 10.3. Windows PowerShell

~~~powershell
Resolve-DnsName booking.internal.example
Test-NetConnection booking.internal.example -Port 443
~~~

TCP hoạt động không chứng minh ứng dụng có quyền hay trả kết quả đúng; nếu lỗi xảy ra ở HTTP, cần tiếp tục kiểm tra tầng cao hơn.

### 10.4. Packet capture và network mirroring

Packet capture có thể giúp xác nhận SYN/SYN-ACK/RST, retransmission hoặc MTU, nhưng chỉ thấy traffic ở điểm đặt capture. Với cloud managed services, proxy và NAT, không thể cho rằng capture một host biểu diễn toàn bộ đường truyền. Việc thu payload phải tuân thủ quyền và quy định bảo vệ dữ liệu.

## 11. Case study A: 504 sau khi siết firewall

**Bối cảnh:** Load balancer công khai chuyển HTTPS tới Booking API private. Sau cập nhật network rule, người dùng nhận 504; CPU backend thấp.

**Các giả thuyết hợp lệ:**

- Security rule chặn nguồn LB hoặc health check.
- Routing chiều về sai, phản hồi không tới LB.
- Request vào backend nhưng Booking chờ DB/queue quá lâu.
- Backend không lắng nghe đúng port hoặc không đáp ứng health probe.

**Điều tra:** xác định nơi sinh 504 từ LB log, target health, thời gian xử lý, rồi đối chiếu 5-tuple trong flow/firewall log và application trace. Nếu target không khỏe và có deny tương ứng ở thời điểm thay đổi, có cơ sở kiểm tra lại rule. Nếu target nhận request nhưng ứng dụng chờ DB 30 giây, mở port LB chưa giải quyết được nguyên nhân.

**Khắc phục:** thay đúng rule/route hoặc sửa dependency, kiểm thử health check và hành trình tạo booking; theo dõi error rate/latency sau thay đổi. Ghi kết quả vào network policy tests để tránh tái diễn.

## 12. Case study B: lỗi private database endpoint

**Bối cảnh:** Staging dùng managed DB qua private endpoint thành công, production báo timeout. Từ laptop kỹ sư truy cập được DB hostname.

| Bằng chứng | Giả thuyết cần kiểm tra | Hướng xử lý |
|---|---|---|
| DNS production trả IP public | Private zone chưa liên kết đúng | Kiểm tra zone association, forwarding và resolver |
| DNS private IP đúng, TCP timeout | Route hoặc network policy sai | Kiểm tra route hai chiều, DB firewall và security rule |
| TCP được thiết lập nhưng DB từ chối | Authentication/authorization hoặc TLS lỗi | Kiểm tra DB identity, chứng chỉ và quyền |
| Chỉ một subnet/pod lỗi | Cấu hình mạng/identity cục bộ khác | So sánh effective policy, DNS, network attachment |
| Không có flow log | Chưa đủ dữ liệu để kết luận | Kiểm tra log đã bật ở đúng vị trí và độ trễ/sampling |

Laptop không phải cùng nguồn với pod production: DNS, VPN, IP nguồn, route và quyền khác nhau. **Kết quả từ laptop không thể thay thế phép thử từ nguồn phát sinh lỗi.**

## 13. Case study C: thanh toán timeout vào giờ cao điểm

**Bối cảnh:** Booking API gọi payment provider qua NAT. Trong giờ cao điểm, lỗi kết nối tăng; DB bình thường; bên cung cấp thanh toán dùng IP allowlist.

Cần phân biệt:

1. **SNAT port exhaustion** do quá nhiều phiên hoặc kết nối kéo dài.
2. **Egress IP đổi** sau failover/route, không còn trong allowlist.
3. **Retry storm** khiến số outbound requests tăng mạnh so với giao dịch thật.
4. **Đối tác rate limit / chậm xử lý**, dù TCP/TLS đã thành công.
5. **DNS/proxy thay đổi** làm request tới endpoint khác.

Đối chiếu NAT connection metric/port allocation errors, egress IP, client connect time, HTTP status và retry count. Khi xác nhận cạn port, có thể tối ưu connection pool, thời gian giữ kết nối, concurrency hoặc mở rộng NAT theo tính năng hỗ trợ. Khi có 429 từ đối tác, tăng retry không kiểm soát có thể làm vấn đề nặng hơn.

## 14. Case study D: VPN báo healthy nhưng dịch vụ hybrid không truy cập được

**Bối cảnh:** Tunnel VPN giữa on-prem và cloud đang up, nhưng người dùng văn phòng không kết nối được API private.

Điều tra theo thứ tự:

1. DNS của client on-prem có trả IP private đúng không? Forwarder và private zone hoạt động ra sao?
2. CIDR hai bên có chồng lấn? IP đích thuộc mạng được advertise không?
3. BGP peer hoặc static route có cung cấp đường đi và chiều về đúng prefix?
4. Firewall on-prem/cloud, stateless ACL và stateful device có cho phép đúng flow?
5. TLS/endpoint/application có hoạt động khi kiểm tra từ nguồn được phép?
6. Nếu có tunnel dự phòng, failover và asymmetric routing được xử lý ra sao?

Tunnel up chỉ là **một phần điều kiện của kết nối**, không phải bằng chứng ứng dụng hoạt động.

## 15. Kiểm soát thay đổi và runbook xử lý sự cố

Thay đổi mạng thường có phạm vi ảnh hưởng lớn. Một thay đổi route/DNS/firewall cần ghi **owner, nguồn/đích/cổng cụ thể, policy trước–sau, các luồng có nguy cơ bị ảnh hưởng, kết quả kiểm thử, rollback và người thực hiện**. Nên dùng IaC và policy review nơi phù hợp để giảm drift.

Mẫu runbook ngắn:

~~~text
Sự cố: Booking API không kết nối DB private
Incident owner: Booking on-call + Cloud Platform on-call
Thời gian (UTC): ...
Nguồn và đích: workload/subnet/IP:port -> hostname/IP:port
Tác động: tỷ lệ lỗi / latency / SLO bị ảnh hưởng
Triệu chứng: DNS / refused / timeout / TLS / HTTP / auth

Bằng chứng:
  1. DNS answer từ nguồn bị lỗi:
  2. Effective routes đi/về:
  3. Effective network policy + flow/firewall log:
  4. TCP/TLS probe + LB health + app trace:
  5. Thay đổi gần thời điểm phát sinh:

Giả thuyết được xác nhận:
Thay đổi khắc phục có phạm vi:
Kết quả thử lại từ nguồn ban đầu:
SLI/SLO sau khắc phục:
Vấn đề cần sửa trong IaC, cảnh báo, runbook:
~~~

Khi khôi phục, hãy kiểm tra **cả luồng được phép và luồng phải bị chặn** để tránh sửa lỗi bằng cách mở mạng quá rộng. Postmortem cần chỉ ra nguyên nhân hệ thống, khoảng trống quan sát và cách ngăn tái diễn.

## 16. Đánh đổi theo tư duy Well-Architected

| Góc nhìn | Quyết định kiến trúc | Lợi ích và đánh đổi |
|---|---|---|
| **Security** | Least-privilege network policy, private endpoint, kiểm soát ingress/egress | Thu hẹp bề mặt tấn công nhưng tăng công quản lý rule và DNS |
| **Reliability** | Health check, route dự phòng, timeout và giới hạn lỗi lan truyền | Giảm single point of failure nhưng tăng nhu cầu failover test |
| **Performance efficiency** | Tránh network hop không cần thiết, connection pooling, chọn đường đi phù hợp | Giảm latency, SNAT pressure nhưng phải bảo vệ cô lập |
| **Cost optimization** | Chọn retention log, NAT/firewall/gateway và đường traffic hợp lý | Dễ quan sát nhưng có phí log ingestion, cross-zone/region và egress |
| **Operational excellence** | IaC, policy test, runbook và alert có owner | Chẩn đoán nhanh hơn nhưng cần đầu tư công cụ và quy trình |
| **Sustainability** | Tránh traffic vòng và lưu log quá mức | Giảm lãng phí nếu vẫn đáp ứng bảo mật/khả năng khôi phục |

Ví dụ: ép mọi outbound traffic qua một firewall trung tâm giúp policy nhất quán, tập trung quan sát. Đồng thời nó có thể tạo điểm nghẽn, tăng độ trễ, chi phí và phạm vi sự cố. Cần xác định **luồng nào bắt buộc đi qua điểm kiểm soát**, luồng nào phù hợp private endpoint hoặc kiểm soát tại workload, cấu hình dự phòng nào cần và cách đo kết quả.

## 17. Phản mẫu và sai lầm suy luận

| Sai lầm | Vấn đề | Cách cải thiện |
|---|---|---|
| “Ping thất bại nên TCP chắc chắn bị chặn.” | ICMP có thể bị chặn riêng | Thử đúng giao thức/cổng và đối chiếu log |
| “Flow log ACCEPT nghĩa là API đã thành công.” | Log quan sát ở một lớp, chưa phản ánh HTTP/DB | Kiểm tra TCP/TLS, LB status và trace |
| “Không có flow log tức là không có packet.” | Có thể thiếu độ phủ, log đến muộn hoặc sampling | Kiểm tra cấu hình logging và điểm quan sát |
| “Cứ mở mọi nguồn với 0.0.0.0/0 là được.” | Tạo rủi ro bảo mật và không giải quyết lỗi routing/DNS | Xác định 5-tuple và policy tối thiểu |
| “Private endpoint tự làm DNS đúng ở mọi mạng.” | Private zone/forwarding có thể thiếu ở hybrid | Kiểm tra phân giải tên từ client thật |
| “VPN up là ứng dụng phải chạy.” | Return route, firewall, TLS, IAM vẫn có thể lỗi | Kiểm tra đủ lớp |
| “502/504 luôn là lỗi mạng.” | Backend, gateway timeout, dependency cũng có thể lỗi | Dùng LB log và application trace |
| “Thêm retry vô hạn sẽ chữa timeout.” | Retry storm làm quá tải và cạn kết nối | Giới hạn retry, backoff/jitter và idempotency |
| “Ghi toàn bộ packet càng lâu càng tốt.” | Tăng chi phí và rủi ro lộ dữ liệu | Thu có mục đích, hạn chế quyền và retention |
| “Route chiều đi đúng là đủ.” | Phản hồi có thể đi sai đường hoặc bị stateful firewall chặn | Xác minh đường về và NAT |

## 18. Checklist kiểm chứng một đường kết nối production

- [ ] Có owner, lý do nghiệp vụ, source/destination, protocol/port, hướng và thời hạn quyền.
- [ ] DNS được kiểm tra từ đúng môi trường nguồn, trả về endpoint mong muốn.
- [ ] Route chiều đi và về đúng; CIDR, VPN/peering/transit và NAT được xem xét.
- [ ] Mọi lớp firewall/security group/ACL/pod policy được kiểm tra theo hiệu lực.
- [ ] Backend không phơi ra Internet ngoài thiết kế; listener và health check hoạt động.
- [ ] Có TLS, authentication/authorization và quản lý secrets phù hợp.
- [ ] Egress IP, allowlist, NAT capacity và quota được kiểm tra theo tải dự kiến.
- [ ] Có flow/firewall/DNS/LB/NAT/VPN logs hoặc metrics phù hợp để điều tra.
- [ ] Biết giới hạn sampling, thời gian đến log và điểm thu thập của từng nguồn.
- [ ] Quyền đọc log, retention, mã hóa và chi phí đã được kiểm soát.
- [ ] Đã thử lỗi DNS, dependency chậm/không sẵn sàng và hành vi timeout phù hợp.
- [ ] Có alert theo tác động tới hành trình người dùng, owner, runbook và cách rollback.
- [ ] Đã thử luồng hợp lệ **và** luồng phải bị chặn sau thay đổi.

## 19. Bài tập thực hành

**Tình huống:** Công ty vận hành Booking API ở cloud. Public LB → private app; app → DB private endpoint; app → payment provider qua NAT. Đội platform mới thêm firewall tập trung và sửa DNS private. Sau thay đổi, khoảng 30% yêu cầu tạo booking timeout. Từ laptop kỹ sư vẫn truy cập được DB bằng hostname cũ; metric NAT báo lỗi kết nối tăng lúc tải cao; firewall log có cả ACCEPT và REJECT.

**Yêu cầu:**

1. Vẽ lại ingress, east-west và egress, đánh dấu ít nhất sáu điểm có thể gây lỗi.
2. Đưa ra ba giả thuyết khác nhau và nêu bằng chứng cần để bác bỏ từng giả thuyết.
3. Giải thích tại sao kết quả kết nối DB từ laptop không đại diện cho pod Booking production.
4. Lập trình tự tra cứu DNS, effective route, firewall/flow log, NAT, LB và application trace theo cùng time window.
5. Đề xuất cách sửa nếu DNS production trả IP sai, route chiều về không qua cùng firewall hoặc NAT cạn port.
6. Xác định phép thử trước khi đóng incident: đặt phòng, thanh toán, độ trễ dưới tải, luồng bị chặn, log và SLO.
7. So sánh hai phương án egress: tập trung toàn bộ tại firewall chung hoặc kết hợp private endpoint với policy theo workload; nêu tradeoff chi phí, khả năng quan sát và reliability.

**Gợi ý tự kiểm tra:** Không lấy một record ACCEPT/REJECT không khớp 5-tuple và thời gian để kết luận. Trước hết kiểm tra DNS từ đúng pod, route hai chiều, vị trí NAT, TCP/TLS và trace theo request. Có thể tồn tại **nhiều lỗi đồng thời**: một phần traffic theo DNS sai, trong khi NAT chỉ cạn port lúc tải cao. Mọi hành động sửa cần được đối chiếu bằng số liệu.

## 20. Ghi nhớ

Kiểm soát lưu lượng bắt đầu từ **bản đồ luồng cần thiết**, rồi được thực thi qua các lớp DNS, routing, network policy, NAT, load balancer, TLS và quyền ứng dụng. Nhật ký mạng là **bằng chứng tại điểm quan sát cụ thể**, nên phải hiểu độ phủ, ý nghĩa và giới hạn của nguồn log trước khi kết luận.

Khi sự cố xảy ra, hãy xác định **nguồn, đích, triệu chứng, thời điểm và mức ảnh hưởng**, sau đó kiểm tra các lớp theo giả thuyết, sửa đúng nguyên nhân và xác nhận lại hành trình người dùng. Cách tiếp cận này giúp kiến trúc cloud cân bằng bảo mật, độ tin cậy, khả năng mở rộng, hiệu năng, chi phí và vận hành thay vì chỉ tìm cách “mở được cổng”.
