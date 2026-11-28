# Xác định tài sản và đường đi bị ảnh hưởng trong sự cố mạng

## 1. Vì sao xác định phạm vi ảnh hưởng phải đi trước kết luận nguyên nhân?

Khi một tổ chức nhận được cảnh báo "không truy cập được API", "một chi nhánh mất VPN" hoặc "IDS phát hiện kết nối bất thường", hai câu hỏi cần trả lời sớm là:

1. **Những tài sản và dịch vụ nào đã bị ảnh hưởng, trong khoảng thời gian nào?**
2. **Các luồng mạng liên quan đi qua những thành phần nào, và lỗi hoặc hành vi bất thường xuất hiện ở đoạn nào?**

Trong mô-đun **SECURITY_NETWORK_SECURITY**, việc này kết nối kiến thức về phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, mạng không dây và kiến trúc cloud với quy trình **ứng phó sự cố mạng**. Một nhóm vận hành biết chính xác ranh giới ảnh hưởng sẽ ưu tiên được dịch vụ quan trọng, khoanh vùng điều tra, lựa chọn biện pháp ngăn chặn phù hợp và tránh làm gián đoạn các hệ thống chưa liên quan.

Ví dụ: ứng dụng Java báo **504 Gateway Timeout** khi gọi dịch vụ thanh toán. Nguyên nhân có thể nằm ở DNS, WAF, load balancer, firewall, route qua VPN, lỗi backend hoặc phụ thuộc của backend. Không thể kết luận "máy chủ thanh toán hỏng" chỉ từ HTTP 504. Cần xác định **client nào bị lỗi**, **đích logic nào liên quan**, **đường đi của request và response**, cùng **bằng chứng quan sát được tại mỗi điểm**.

Mục tiêu của bài học:

- Xác định được tài sản ảnh hưởng trực tiếp, tài sản phụ thuộc, tài sản có nguy cơ và tài sản đã kiểm chứng không bị ảnh hưởng.
- Nối định danh nghiệp vụ với tài sản kỹ thuật như host, VM, container, service, IP, subnet, firewall rule và cloud resource.
- Vẽ được đường đi thực tế của một luồng qua DNS, NAT, load balancer, proxy, firewall, VPN, mạng overlay và ứng dụng.
- Khoanh vùng đoạn nghi vấn bằng log, metric, flow telemetry, traceroute và packet capture có kiểm soát.
- Đánh giá mức độ tin cậy của từng kết luận, ghi nhận khoảng trống bằng chứng và cập nhật phạm vi ảnh hưởng trong suốt sự cố.

**Nguyên tắc quan trọng:** *tài sản xuất hiện trong đường đi* không đồng nghĩa *tài sản bị lỗi*, còn *tài sản bị ảnh hưởng* không nhất thiết là nơi phát sinh nguyên nhân gốc.

## 2. Những khái niệm phải phân biệt

| Khái niệm | Ý nghĩa khi ứng phó sự cố | Ví dụ |
| --- | --- | --- |
| **Tài sản (asset)** | Đối tượng cần theo dõi, bảo vệ hoặc khôi phục | Laptop, switch, router, firewall, pod, VM, cluster, DNS resolver, chứng chỉ, ứng dụng |
| **Dịch vụ (service)** | Chức năng mà tài sản cung cấp cho người dùng/hệ thống | API thanh toán, VPN truy cập từ xa, xác thực nội bộ |
| **Phụ thuộc (dependency)** | Quan hệ một thành phần cần thành phần khác để hoạt động | API thanh toán phụ thuộc DNS, gateway, database |
| **Đường đi lưu lượng (traffic path)** | Chuỗi các hop và cơ chế xử lý luồng request/response | Client → VPN → firewall → load balancer → server |
| **Phạm vi ảnh hưởng (impact scope)** | Người dùng, giao dịch, dịch vụ và tài sản thực sự bị suy giảm hoặc gián đoạn | Chỉ chi nhánh A không gọi được API |
| **Vùng có nguy cơ (potential exposure)** | Đối tượng có thể bị tác động nhưng chưa xác nhận | Các workload dùng cùng firewall rule |
| **Điểm nghi vấn (suspected fault domain)** | Đoạn mạng hoặc thành phần cần kiểm chứng tiếp | Đường từ VPN gateway sang firewall nội bộ |
| **Nguyên nhân gốc (root cause)** | Sự kiện/cơ chế được bằng chứng hậu thuẫn giải thích lỗi | Rule firewall thay đổi chặn subnet mới |
| **Blast radius** | Mức độ ảnh hưởng lan ra dịch vụ, người dùng hoặc vùng mạng khác | Ba chi nhánh và hệ thống đặt hàng |

Có thể dùng các nhãn trạng thái:

- **CONFIRMED_AFFECTED:** có bằng chứng dịch vụ/tài sản đang bị ảnh hưởng.
- **SUSPECTED_AFFECTED:** có dấu hiệu phù hợp nhưng chưa đủ dữ kiện.
- **AT_RISK:** chia sẻ tài nguyên hoặc phụ thuộc có nguy cơ lan truyền, chưa quan sát thấy lỗi.
- **CONFIRMED_UNAFFECTED:** đã kiểm tra bằng tiêu chí cụ thể trong cùng cửa sổ thời gian và không thấy tác động.
- **UNKNOWN:** chưa đủ khả năng quan sát để kết luận.

Trạng thái có thể thay đổi khi thu thập bằng chứng mới. **Không đánh dấu "không ảnh hưởng" chỉ vì không có cảnh báo**, vì một cảm biến im lặng có thể chưa thu được lưu lượng.

## 3. Bắt đầu từ tác động người dùng, sau đó truy ra tài sản

### 3.1. Chuẩn hóa triệu chứng và cửa sổ thời gian

Một phiếu sự cố tối thiểu nên ghi:

| Trường | Ví dụ |
| --- | --- |
| Thời điểm bắt đầu quan sát | 2026-11-28 06:10 UTC |
| Nguồn phát hiện | Alert về tỷ lệ lỗi API tại gateway |
| Triệu chứng có thể kiểm chứng | 48% request từ mạng chi nhánh A nhận timeout |
| Người dùng/nhóm bị ảnh hưởng | Nhân viên chi nhánh A sử dụng hệ thống bán hàng |
| Dịch vụ nghiệp vụ | Đặt hàng, thanh toán |
| Điểm truy cập logic | https://api.example.test/orders |
| Môi trường | Production, khu vực DC-1 |
| Tín hiệu ban đầu | Gateway log, VPN tunnel metric, firewall deny log |
| Những điều chưa biết | Có ảnh hưởng chi nhánh B? Server có nhận SYN? |

Ví dụ trên sử dụng tên miền và thời gian minh họa. Khi vận hành thực tế phải lưu **thời điểm ở UTC hoặc kèm offset**, nguồn đồng hồ và thời điểm dữ liệu được lấy. Những cuộc gọi thử nghiệm ở thời điểm khác không tự chứng minh tình trạng của thời điểm sự cố.

Thu hẹp theo **ai / ở đâu / từ lúc nào / làm gì / thất bại theo cách nào**. Với sự cố an ninh, bổ sung sự kiện phát hiện, loại hành vi, độ chắc chắn của chỉ báo và các tài khoản/host có liên quan. Tỷ lệ lỗi có thể tăng ở một region mà không ảnh hưởng toàn hệ thống.

### 3.2. Đi từ thực thể nghiệp vụ đến định danh kỹ thuật

Một dịch vụ không tương đương một máy chủ; một máy chủ cũng có thể chạy nhiều dịch vụ. Việc truy ra tài sản cần nhiều lớp định danh:

| Lớp | Thông tin cần thu | Lưu ý |
| --- | --- | --- |
| Nghiệp vụ | Dịch vụ, chủ sở hữu, mức độ quan trọng, RTO/RPO nếu có | Dùng để ưu tiên khôi phục |
| Danh tính hệ thống | Service name, workload, cluster, tenant, environment | Có thể ổn định hơn IP |
| Máy tính/thiết bị | Hostname, instance ID, asset ID, serial, device ID | Giúp phân biệt máy thật với alias |
| Mạng | IP, subnet/CIDR, VLAN/VRF, VPC/VNet, interface, route table | Có thể thay đổi theo thời gian |
| Ứng dụng | DNS name, URL, port, protocol, certificate, API route | Một tên miền có thể trả nhiều IP |
| Vận hành | Owner, team on-call, vị trí, trạng thái giám sát | Để chuyển giao và xác minh |
| Bảo mật | Zone tin cậy, firewall policy, ACL, security group, identity | Để xác định ranh giới và nguy cơ |

**Định danh tài sản phải có mốc thời gian.** IP có thể được cấp lại bằng DHCP, pod trong Kubernetes có thể bị tạo lại, instance autoscaling thay đổi liên tục, DNS record có TTL và NAT có thể dùng chung một IP public cho nhiều host. Khi điều tra log cũ, cần tra mapping **đúng thời điểm xảy ra sự cố** thay vì dùng trạng thái hiện tại.

### 3.3. Nguồn xác minh tài sản

Ưu tiên kết hợp CMDB hoặc asset inventory với dữ liệu thực tế từ hạ tầng:

- **CMDB / service catalog:** quan hệ owner, service, mức ưu tiên và dependency do nhóm vận hành quản lý.
- **DHCP/DNS/IPAM:** IP được cấp cho thiết bị nào, tên miền phân giải tới đâu và TTL.
- **Cloud inventory:** instance/VM, private/public IP, NIC, VPC/VNet, subnet, security group, route table, load balancer target.
- **Kubernetes/service discovery:** pod, service, endpoint, node, namespace, network policy, ingress/egress.
- **Firewall/VPN/NAT:** session table, route, tunnel, rule, ánh xạ địa chỉ và trạng thái tunnel.
- **Identity/endpoint telemetry:** thiết bị thuộc ai, đăng nhập gần thời điểm sự cố, EDR/NDR alert nếu liên quan.
- **Monitoring và ứng dụng:** dependency map, service health, access log, trace và kiểm thử từ nhiều vị trí.

Không có nguồn nào luôn là "sự thật tuyệt đối". CMDB có thể chậm cập nhật; route hiện tại khác route tại thời điểm lỗi; flow log có thể tổng hợp hoặc lấy mẫu; cloud network policy thay đổi sau deploy. Ghi rõ nguồn và thời điểm lấy dữ liệu.

## 4. Xây dựng bản đồ phụ thuộc và ranh giới an ninh

Trước khi xác định chính xác hop mạng, vẽ đồ thị phụ thuộc từ dịch vụ mà người dùng truy cập:

~~~mermaid
flowchart LR
    U[Người dùng chi nhánh] --> E[Thiết bị và mạng chi nhánh]
    E --> V[VPN gateway]
    V --> F[Firewall phân đoạn]
    F --> L[Load balancer / API gateway]
    L --> A[Order API]
    A --> P[Payment API]
    A --> D[(Order database)]
    P --> PD[(Payment database)]
    R[DNS resolver] -. Phân giải tên .-> U
    R -. Phân giải backend .-> A
    O[Identity provider] -. Xác thực .-> L
~~~

Đồ thị này thể hiện **phụ thuộc logic**, chưa phải sơ đồ packet chính xác. Tất cả các dependency trên đều đáng xem xét, nhưng không phải mọi tài sản đều chịu ảnh hưởng khi một request thất bại. Ví dụ, lỗi truy cập từ một chi nhánh có thể chỉ nằm ở VPN hoặc ACL của chi nhánh đó; database có thể vẫn khỏe.

Với một hệ thống lớn, nên phân biệt:

1. **Data plane:** con đường mà dữ liệu request, response hoặc packet thực sự đi qua.
2. **Control plane:** DNS, route updates, SDN controller, load balancer control/configuration, service discovery, PKI/certificate policy quyết định đường đi hoặc khả năng kết nối.
3. **Management plane:** công cụ và quyền điều hành, logging, orchestration hoặc cấu hình của các thiết bị.

Một sự cố control plane có thể làm hỏng nhiều luồng data plane dù từng router hoặc server vẫn còn hoạt động. Khi đánh giá nguy cơ lan rộng, phải đưa các **shared dependencies** như DNS resolver, identity provider, VPN concentrator và gateway trung tâm vào bản đồ.

## 5. Dựng đường đi thực tế: request và response

### 5.1. Bắt đầu từ một luồng cụ thể

Thay vì nói "traffic đi tới hệ thống thanh toán", xác định:

- **Nguồn:** asset ID, IP nguồn (có thể là IP private hoặc IP sau NAT), zone, subnet.
- **Đích logic:** FQDN/API route và cổng/giao thức mà client dùng.
- **Đích đã phân giải:** địa chỉ IP, record DNS, TTL và resolver ở thời điểm kiểm tra.
- **5-tuple theo từng chặng:** source IP, source port, destination IP, destination port, protocol.
- **Ranh giới:** Wi-Fi/LAN, VLAN/VRF, firewall/ACL, VPN, NAT, CDN/WAF, load balancer, reverse proxy, service mesh.
- **Return path:** chiều ngược lại của response, có thể khác chiều đi do policy routing, NAT hoặc ECMP.
- **Thời gian và định danh:** timestamp, correlation ID/trace ID, firewall session ID, VPN tunnel ID và NAT translation.

Giả sử một request từ máy tại chi nhánh đến API:

~~~text
Laptop chi nhánh (10.12.6.25)
    |
Switch / Wi-Fi / VLAN người dùng
    |
VPN tunnel -> VPN gateway tại trung tâm
    |
Firewall nội bộ: zone BRANCH -> APP
    |
Load balancer VIP: 10.40.1.20:443
    |
Reverse proxy / API gateway
    |
Backend application: 10.40.2.17:8443
    |
Database / downstream services
~~~

Đây là topology giả định. **Không suy từ tên miền rằng request chắc chắn đi theo toàn bộ chuỗi**: DNS có thể trả endpoint khác, client có proxy hệ điều hành, VPN split tunnel có thể đưa traffic ra Internet và load balancer có thể chọn backend khác.

### 5.2. Hop nào forward packet, hop nào tạo kết nối mới?

| Thành phần | Hành vi thường gặp | Hệ quả khi so sánh log/PCAP |
| --- | --- | --- |
| Switch L2 | Chuyển frame theo MAC/VLAN | Không tự tạo HTTP request mới |
| Router / firewall L3 | Forward hoặc drop dựa trên route, policy và state | IP thường giữ nguyên nếu không NAT; TTL/hop-limit thay đổi |
| NAT gateway | Thay IP/port theo mapping | 5-tuple khác nhau trước và sau NAT |
| VPN gateway | Đóng gói/mã hóa hoặc giải đóng gói packet | Outer IP/protocol khác inner flow |
| Load balancer L4 | Có thể forward, NAT hoặc terminate TCP tùy sản phẩm/chế độ | Không được mặc định sequence number giữ nguyên |
| Reverse proxy / WAF L7 | Có thể kết thúc TLS/TCP và gọi upstream bằng connection mới | Client–proxy và proxy–server có 5-tuple, TCP state riêng |
| Service mesh sidecar | Có thể bắt/chuyển hướng request trong namespace | PCAP tại host NIC chưa chắc thấy leg bên trong |
| CDN / cache | Có thể đáp request tại edge | Origin/backend không có request tương ứng |

**Lưu ý TCP:** khi reverse proxy L7 tạo connection upstream mới, sequence/ack không trùng với connection phía client. Muốn ghép hai chặng, dùng timestamp, upstream address/port, access log, correlation ID và distributed trace. Với một TCP connection được dùng lại cho nhiều request, chỉ 5-tuple **không xác định duy nhất một request**.

### 5.3. Không quên chiều quay về

Một client gửi SYN nhưng không nhận SYN-ACK có thể gặp lỗi ở **đường đi hoặc đường về**. Nếu chỉ nhìn packet tại client, chưa thể biết SYN có tới server hay chưa. Cần kiểm tra điểm quan sát phía server và các ranh giới:

~~~mermaid
flowchart LR
    C[Client] -->|Request / SYN| F[Firewall, NAT, VPN]
    F -->|Request / SYN| S[Server]
    S -->|Response / SYN-ACK| F
    F -->|Response / SYN-ACK| C
~~~

Trong môi trường policy routing, kết nối hai chiều có thể đi qua **thiết bị firewall khác nhau**. Stateful firewall không thấy phiên đã được thiết lập có thể từ chối packet chiều về. Vì vậy, cần kiểm tra route cả hai phía và session state tại ranh giới, thay vì mặc định response quay về đúng đường request.

## 6. Phương pháp khoanh vùng từng hop bằng bằng chứng

Một quy trình thực dụng là đặt các **điểm quan sát A, B, C** hai phía của đoạn nghi vấn:

~~~text
Client --[A]--> VPN gateway --[B]--> Firewall --[C]--> LB --[D]--> Server
~~~

Tại mỗi điểm, chỉ hỏi những gì cảm biến thực sự chứng minh:

| Bằng chứng | Có thể khẳng định | Không nên khẳng định |
| --- | --- | --- |
| Client PCAP có SYN đi ra | Client đã gửi packet tại interface đó | Server đã nhận SYN |
| Firewall ingress có SYN và egress không có | SYN xuất hiện ở ingress nhưng không thấy ở egress trong cửa sổ đó | Firewall chắc chắn drop, nếu chưa kiểm tra filter, capture drop, route khác |
| Firewall deny log match đúng session | Policy đang từ chối flow được ghi log | Mọi luồng tương tự đều bị từ chối hoặc đây chắc chắn là nguyên nhân duy nhất |
| Server PCAP có SYN | Packet tới interface server | Ứng dụng đã chấp nhận request |
| TCP ACK từ server | TCP stack đã xác nhận byte theo sequence | Business logic đã chạy thành công |
| Gateway log có HTTP 504 | Gateway trả trạng thái timeout/không lấy được upstream response | Backend chắc chắn đã hỏng |
| Cloud flow log có ACCEPT | Flow được ghi nhận là được phép tại điểm ghi nhận theo ngữ nghĩa nhà cung cấp | Packet chắc chắn đến ứng dụng hoặc không bị chặn ở hop khác |
| IDS alert liên quan host | Sensor phát hiện mẫu khớp quy tắc/heuristic | Host chắc chắn đã bị xâm nhập thành công |

Với từng điểm, ghi **có thấy / không thấy / không đủ dữ liệu**, thời gian, filter và độ tin cậy. "Không thấy packet" chỉ có ý nghĩa mạnh nếu xác nhận đã chọn đúng interface, capture cả chiều cần thiết, đồng hồ phù hợp và không bị rơi packet tại cảm biến.

### 6.1. Phân biệt mất đường, bị chặn và ứng dụng lỗi

| Triệu chứng | Điểm kiểm chứng tiếp theo |
| --- | --- |
| Không có DNS response | Client resolver, DNS server, network path DNS/DoH/DoT, cache |
| Client gửi SYN, server không thấy | Firewall/VPN/NAT/route giữa hai phía, packet capture gần ranh giới |
| Server có SYN, có RST | Port listener, host firewall, TLS/protocol và ứng dụng |
| SYN/SYN-ACK thành công, TLS thất bại | TLS version/certificate/SNI, WAF/proxy logs, mTLS policy |
| TCP và TLS tốt, HTTP 403 | Auth/WAF/authorization/gateway policy, ứng dụng |
| Gateway 502/504 | Upstream connect/response timing, LB target, backend log và PCAP |
| Server trả response, client không nhận | Return path, proxy buffering, NAT/session, drop ở chiều về |
| Chỉ một subnet/tenant bị lỗi | Routing/ACL/segmentation/DNS view hoặc policy riêng subnet/tenant |

Một tầng hoạt động tốt trong một lần kiểm thử **không loại trừ** lỗi gián đoạn theo thời gian. Cần so sánh cả mẫu thành công và thất bại dưới điều kiện tương đương.

## 7. Công cụ và nguồn telemetry nên kết hợp

**Ưu tiên dữ liệu ít xâm lấn trước:** topology, change log, metric, firewall/NAT/VPN session, LB log, flow telemetry, DNS log và application trace. Chỉ dùng packet capture khi cần nhìn thứ tự hoặc trường cụ thể của packet mà nguồn hiện có chưa cung cấp.

### 7.1. Lệnh kiểm tra đọc trạng thái trên Linux

Các lệnh sau là ví dụ khi có quyền trên thiết bị liên quan; chạy trên **đúng namespace/máy** và thay địa chỉ cho môi trường thực:

~~~bash
# Kiểm tra IP, giao diện, trạng thái link tại nơi đang điều tra.
ip -br addr
ip -br link

# Kiểm tra quyết định route hiện tại cho một IP đích.
ip route get 10.40.1.20

# Xem bảng tuyến và policy routing (IPv4).
ip route show
ip rule show

# Kiểm tra kết nối TCP có liên quan trên host này.
ss -tn

# Nếu có quyền, xem bảng neighbor tại subnet cục bộ.
ip neigh show
~~~

`ip route get` phản ánh **quyết định định tuyến hiện tại trong network namespace đang chạy**, không phải lịch sử tại thời điểm sự cố và không phản ánh đầy đủ cách firewall, proxy hoặc overlay xử lý. `ip neigh show` chủ yếu cung cấp trạng thái ARP/neighbor tại các segment liên quan, không xác minh mọi hop trên toàn tuyến.

### 7.2. Kiểm tra DNS và probe có kiểm soát

~~~bash
# Quan sát record và TTL mà resolver được chỉ định trả về.
dig @10.12.6.53 api.example.test A
dig @10.12.6.53 api.example.test AAAA

# Kiểm tra HTTPS tới địa chỉ cụ thể với đúng hostname/SNI.
# Chỉ dùng endpoint kiểm thử được phép, tránh thao tác làm thay đổi dữ liệu.
curl -sS -v --connect-timeout 3 --max-time 8 \
  --resolve api.example.test:443:10.40.1.20 \
  -o /dev/null https://api.example.test/health
~~~

`--resolve` buộc `curl` dùng IP được chỉ định cho host/port của lần gọi, đồng thời giữ hostname trong URL cho Host/SNI theo khả năng của thư viện TLS. Kết quả giúp tách vấn đề DNS khỏi đường kết nối tới một IP, nhưng **một lệnh curl thành công không bảo đảm mọi client/route đều khỏe**. Hãy ghi lại nguồn gọi, IP, thời điểm và endpoint.

Traceroute/MTR có thể hữu ích để tìm dấu hiệu đường đi thay đổi, nhưng ICMP/TTL-expired có thể bị rate limit hoặc chặn; hop không phản hồi **không chứng minh** chính hop đó đang drop traffic ứng dụng. Với VPN, overlay, cloud và policy routing, các hop trung gian có thể cố ý không hiển thị.

### 7.3. Packet capture giới hạn vào đúng câu hỏi

~~~bash
# Ví dụ chỉ thu TCP/443 liên quan tới VIP trong 500 packet.
# Lựa chọn interface eth0, snaplen và đích cần thay theo thực tế.
sudo tcpdump -i eth0 -nn -s 160 -c 500 \
  -w incident-vip.pcap \
  'host 10.40.1.20 and tcp port 443'
~~~

Capture filter này **không** bao gồm DNS, ICMP, VPN outer traffic, UDP/443 (HTTP/3/QUIC) hoặc backend sau khi proxy đổi IP/port. Mở rộng filter theo giả thuyết và áp dụng giới hạn lưu trữ, quyền thu thập, bảo vệ nội dung nhạy cảm. Sau capture, kiểm tra thống kê dropped packets; hai PCAP ở hai phía NAT/proxy cần đối chiếu bằng mapping và log, không ép các TCP sequence phải giống nhau.

### 7.4. Dữ liệu chuyên biệt cho mạng bảo mật

| Nguồn | Trường cần ưu tiên | Câu hỏi |
| --- | --- | --- |
| Firewall/ACL | Src/dst IP, port, action, rule ID, zone, interface, session, timestamp | Rule nào cho phép/chặn đường này? |
| VPN gateway | Tunnel ID, peer, route, SA/state, packet/byte counters, rekey, error | Luồng có đi qua tunnel đúng không? |
| NAT/conntrack | Original tuple, translated tuple, state, timeout | Hai chặng thuộc cùng flow nào? |
| Load balancer | VIP, backend/target, health, connect time, target response, retry | Request được chọn tới backend nào? |
| Reverse proxy/WAF | Request ID, route, status, upstream, WAF rule/action, timing | Request bị chặn, trả từ cache hay chuyển tiếp? |
| DNS | QNAME, type, resolver, answer, RCODE, TTL, client | Client dùng đích IP nào, có split DNS không? |
| NetFlow/IPFIX | Flow tuple, byte/packet counts, start/end, interface | Những cặp endpoint nào giao tiếp? |
| IDS/IPS/NDR | Alert signature, flow, sensor, direction, timestamp | Alert gắn với luồng nào, sensor thấy đủ hai chiều? |
| Endpoint/EDR | Host identity, process/connection, thời điểm, trạng thái | Tiến trình nào chủ động kết nối? |
| Cloud/Kubernetes | Flow log, security group, route table, ENI, pod/service endpoints, network policy | Đường đi và chính sách dynamic tại thời điểm sự cố là gì? |

**Không kết luận ACCEPT trong một loại log đồng nghĩa end-to-end success.** Mỗi log chỉ mô tả hành vi ở phạm vi thiết bị/dịch vụ tạo ra nó. Cũng cần kiểm tra sampling, retention và field nào có thể bị thiếu.

## 8. Nối các bản ghi khi IP và đường đi thay đổi

### 8.1. Xác định cùng một flow qua NAT

Ví dụ NAT gateway thay địa chỉ nguồn:

~~~text
Trước NAT:
10.12.6.25:51844   -> 10.40.1.20:443  TCP

Sau NAT:
10.99.0.8:62011    -> 10.40.1.20:443  TCP
~~~

Không thể ghép hai phía chỉ bằng source IP/port vì chúng đã đổi. Cần đối chiếu **NAT session mapping**, thời điểm, protocol, original/translated tuple và trạng thái phiên. Nếu NAT port được tái sử dụng theo thời gian, tuple đơn lẻ thiếu timestamp có thể ghép nhầm các kết nối khác nhau.

### 8.2. Xác định một request xuyên reverse proxy

~~~text
Client -> Gateway:
10.12.6.25:51844 -> 10.40.1.20:443   TCP/TLS

Gateway -> Backend:
10.40.1.10:39420 -> 10.40.2.17:8443  TCP/TLS
~~~

Ở đây có **hai connection khác nhau**. Hãy dùng access log của gateway (request ID, upstream address, upstream connect/response time), application log và trace ID để nối cùng request logic. Nếu gateway retry sang backend khác, một request ở phía client có thể tạo ra nhiều **attempts** ở phía server.

### 8.3. DNS, dual-stack và nhiều đích

Một hostname có thể trả **A và AAAA**, nhiều địa chỉ theo region/health, hoặc kết quả khác nhau giữa các resolver. Một client có thể thử IPv6 rồi fallback IPv4; hai client ở hai vị trí có thể chọn VIP khác nhau. Khi ghi bản đồ ảnh hưởng cần lưu **FQDN → resolver → answer → IP đã chọn tại thời điểm kiểm thử**, thay vì chỉ ghi "api.example.test".

### 8.4. Container, service mesh và cloud

Pod IP, node IP, service IP, overlay outer IP và egress gateway có thể là các danh tính khác nhau của cùng workload theo từng điểm quan sát. Đối chiếu namespace, service endpoint, deployment revision, network policy, node mapping và label **tại thời điểm sự cố**. Với cloud managed service, nhiều hop không cho truy cập PCAP trực tiếp; dùng flow logs, provider logs, route/security policy và quan sát tại endpoint được phép. Không vẽ một hop "vật lý" khi chỉ biết tồn tại một đối tượng logical.

## 9. Xác định blast radius theo phạm vi và mức độ nghiêm trọng

### 9.1. Bốn vòng cần rà soát

1. **Vòng 1 — tác động xác nhận:** tài sản hoặc người dùng có giao dịch lỗi, kết nối mất, tunnel down hoặc alert được chứng minh.
2. **Vòng 2 — phụ thuộc trực tiếp:** các service gọi hoặc được gọi bởi thành phần ở vòng 1, cùng các mạng/zone chứa traffic liên quan.
3. **Vòng 3 — phụ thuộc chia sẻ:** DNS, identity, VPN gateway, LB, firewall policy, route, cluster, cloud region dùng chung.
4. **Vòng 4 — đối tượng có nguy cơ:** tài sản cùng subnet/segment, cùng rule, cùng image/config, cùng danh tính hoặc cùng đường egress nhưng chưa xác nhận lỗi.

Phân loại dựa trên **bằng chứng và chiều phụ thuộc**. Nếu API A gọi DB B thì lỗi B có thể ảnh hưởng A; nhưng chỉ vì B nằm trong cùng subnet với A không chứng minh B đã bị ảnh hưởng. Với sự cố nghi xâm nhập, bản đồ lateral movement phải phân biệt "có đường có thể truy cập" với "đã có lưu lượng" và "đã xâm nhập thành công".

### 9.2. Ma trận phạm vi ảnh hưởng

| Đối tượng | Mức độ tác động | Trạng thái | Bằng chứng | Độ tin cậy | Owner |
| --- | --- | --- | --- | --- | --- |
| Người dùng chi nhánh A | Không tạo được đơn | CONFIRMED_AFFECTED | Giao dịch lỗi và probe từ chi nhánh | Cao | Helpdesk |
| Người dùng chi nhánh B | Chưa ghi nhận lỗi | UNKNOWN | Chưa kiểm tra cùng thời điểm | Thấp | Helpdesk |
| API gateway | Nhận request, có timeout | CONFIRMED_AFFECTED | Access log 504, upstream timing | Cao | Platform |
| Backend order-service | Chưa kết luận | SUSPECTED_AFFECTED | Gateway timeout, thiếu server trace | Trung bình | Backend |
| Firewall zone BRANCH→APP | Có dấu hiệu chặn | SUSPECTED_AFFECTED | Deny counter và log trùng cửa sổ | Trung bình | Network |
| DNS resolver | Trả record hợp lệ từ client thử | CONFIRMED_UNAFFECTED cho truy vấn đã thử | Query/response có timestamp | Trung bình | Infrastructure |

**Độ tin cậy không phải phần trăm tùy ý.** Có thể định nghĩa:

- **Cao:** nhiều nguồn độc lập khớp nhau, có timestamp và điểm quan sát rõ, kiểm thử lặp lại được.
- **Trung bình:** một hoặc vài nguồn phù hợp nhưng còn thiếu hop, log có sampling hoặc chưa tái hiện.
- **Thấp:** dựa trên triệu chứng gián tiếp, suy đoán topology hoặc dữ liệu cũ.

Với dịch vụ nghiệp vụ, nên ghi thêm lượng người dùng, giao dịch thất bại, thời gian gián đoạn và mức độ ưu tiên khôi phục. Không cộng số lỗi hoặc số IP một cách cơ học thành "số người dùng bị ảnh hưởng": một user có thể thử lại nhiều lần; một NAT IP có thể đại diện cho cả chi nhánh.

## 10. Quy trình điều tra theo từng giai đoạn

### Giai đoạn A — Phân loại và bảo toàn dấu vết

Khi nhận cảnh báo:

1. Xác nhận đây là sự cố đang xảy ra, sự cố đã kết thúc hay cảnh báo cần xác minh.
2. Ghi **UTC start time** và cửa sổ quan sát, triệu chứng cụ thể, nguồn alert, service/business owner.
3. Gắn nhãn phạm vi ban đầu, đưa điều chưa biết vào danh sách rõ ràng.
4. Bảo lưu log, flow record, phiên VPN/NAT, cấu hình/route và change history có nguy cơ bị xoay vòng hoặc ghi đè.
5. Đồng bộ cách ghi thời gian và tên tài sản giữa các nhóm.

Nếu nghi có xâm nhập, cân nhắc bảo toàn bằng chứng trước khi thay đổi route, firewall hoặc tắt host; song khi có rủi ro đang diễn ra, nhóm chỉ huy sự cố cần cân bằng giữa ngăn chặn và giữ chứng cứ theo quy trình tổ chức.

### Giai đoạn B — Lập danh sách tài sản theo luồng

Xác định **điểm vào**, **dịch vụ đích**, **đường đi phổ biến**, **shared dependencies** và owner. Với mỗi tài sản, ghi rõ asset ID, hostname/IP theo thời điểm, vai trò, zone và trạng thái confirmed/suspected/unknown. Ưu tiên tài sản đang tạo ảnh hưởng nghiệp vụ lớn.

### Giai đoạn C — Khoanh đoạn lỗi

Thực hiện một số kiểm tra có kiểm soát từ **điểm bị lỗi** và **điểm hoạt động bình thường** trong cùng thời gian. Ví dụ nếu chi nhánh A lỗi và chi nhánh B khỏe, so sánh DNS answer, VPN route, firewall policy, NAT mapping, LB target và application log để tìm điểm khác biệt.

Không suy diễn từ một lệnh ping: host có thể từ chối ICMP trong khi HTTPS vẫn hoạt động. Dùng phép thử gần với giao thức đang lỗi (ví dụ TCP/TLS tới đúng FQDN/IP/port, health endpoint được phép).

### Giai đoạn D — Kiểm tra cả chiều đi và chiều về

Với từng đoạn, kiểm tra:

- Gói tới ingress interface chưa?
- Có được forward ra egress hoặc được xử lý tại proxy không?
- Nếu NAT hoặc proxy chuyển kết nối, tuple/ID mới là gì?
- Thiết bị đích có nhận request/packet chưa?
- Response đã đi qua ranh giới nào và dừng ở đâu?

Khi packet "biến mất", xác nhận capture filter, interface, tunnel/namespace, sampling, clock skew và packet drops trước khi xác định thiết bị gây lỗi.

### Giai đoạn E — Cập nhật ảnh hưởng và điều phối

Sau mỗi kết quả mới, cập nhật ma trận tài sản, sơ đồ đường đi, trạng thái, mức độ tin cậy và người phụ trách. Chỉ mở rộng blast radius khi có cơ sở như cùng policy, cùng shared dependency, cùng lỗi đã quan sát hoặc bằng chứng lateral movement. Trình bày cụ thể điều gì **đã xác nhận**, **đang nghi ngờ** và **cần kiểm tra tiếp** cho nhóm điều phối ứng phó.

## 11. Tình huống thực hành: chi nhánh mất kết nối API qua VPN

### 11.1. Mô tả

Chi nhánh A sử dụng subnet **10.12.6.0/24** và chi nhánh B sử dụng **10.12.7.0/24**. Cả hai kết nối về trung tâm qua VPN để truy cập API tại **10.40.1.20:443**, được load balancer chuyển tiếp tới backend **10.40.2.17:8443**.

Sau đợt thay đổi policy phân đoạn, người dùng tại chi nhánh A báo timeout; chi nhánh B vẫn thao tác được. Cần xác định **tài sản nào thực sự bị tác động** và **packet dừng ở đoạn nào**, trước khi quyết định rollback rule hay điều tra backend.

~~~mermaid
flowchart LR
    A[Chi nhánh A<br/>10.12.6.0/24] --> VA[VPN A]
    B[Chi nhánh B<br/>10.12.7.0/24] --> VB[VPN B]
    VA --> F[Firewall BRANCH → APP]
    VB --> F
    F --> VIP[LB 10.40.1.20:443]
    VIP --> GW[API Gateway]
    GW --> APP[Backend 10.40.2.17:8443]
~~~

### 11.2. Tập hợp bằng chứng giả định

| Mốc quan sát UTC | Nguồn | Dữ liệu | Ý nghĩa |
| --- | --- | --- | --- |
| 06:10 | API monitoring | Tỷ lệ timeout từ chi nhánh A tăng, B bình thường | Ảnh hưởng có tính phân vùng |
| 06:12 | VPN gateway | Hai tunnel A/B đều up, counters tăng | Tunnel còn hoạt động; chưa chứng minh API path khỏe |
| 06:14 | Client A PCAP | SYN tới 10.40.1.20:443, không thấy SYN-ACK | Client không thiết lập được TCP |
| 06:15 | Firewall ingress | SYN từ 10.12.6.25 xuất hiện | Traffic A tới mặt vào firewall |
| 06:15 | Firewall egress | Không thấy SYN tương ứng | Nghi vấn đoạn xử lý tại firewall |
| 06:15 | Firewall deny log | Deny rule R-214 match 10.12.6.0/24 → 10.40.1.20:443 | Có bằng chứng policy chặn flow A |
| 06:16 | LB access/connection logs | Không có attempt A tương ứng; các flow B thành công | Phù hợp với việc A bị chặn trước LB |
| 06:17 | Kiểm tra cấu hình | Rule R-214 mới chỉ cho phép 10.12.7.0/24 | Sai lệch policy có khả năng là nguyên nhân |

Ở đây, so sánh chi nhánh A/B và dữ liệu từ **hai phía firewall** là quan trọng. Trạng thái "VPN up" không bác bỏ sự cố tại firewall phía sau tunnel. Các log và capture phải được kiểm tra bằng thời điểm, interface, filtering và packet drop để tránh ghép nhầm luồng.

### 11.3. Kết quả phân loại tài sản

| Tài sản/nhóm | Trạng thái | Căn cứ |
| --- | --- | --- |
| Người dùng subnet 10.12.6.0/24 gọi API | CONFIRMED_AFFECTED | Timeout tái hiện và telemetry |
| Người dùng subnet 10.12.7.0/24 trong phép thử | CONFIRMED_UNAFFECTED cho luồng thử | Request thành công cùng cửa sổ |
| Firewall policy R-214 | Điểm nghi vấn có bằng chứng mạnh | Deny log + cấu hình + PCAP hai phía |
| VPN gateway | Hoạt động, chưa thấy nguyên nhân tại tunnel | Tunnel up và lưu lượng đến firewall |
| Load balancer/backend API | Chưa thấy lỗi nội tại trong phép thử này | B hoạt động; A không tới LB |
| Các dịch vụ khác dùng rule R-214 | AT_RISK | Chia sẻ cùng policy, cần rà soát phạm vi |

**Kết luận có điều kiện:** trong cửa sổ 06:10–06:17 UTC, lưu lượng TCP/443 từ subnet A đến VIP API bị chặn bởi rule R-214 tại firewall. Để xác nhận đầy đủ nguyên nhân, đối chiếu change record và rule evaluation; sau khi điều chỉnh theo quy trình, phải kiểm thử lại cùng luồng từ A và rà soát các subnet cùng policy.

**Không kết luận rằng toàn bộ VPN hỏng, backend bị xâm nhập hay database bị ảnh hưởng**, vì các bằng chứng hiện có không ủng hộ các mệnh đề đó.

### 11.4. Kiểm chứng sau khắc phục

Theo quy trình thay đổi đã được phê duyệt, nhóm network sửa policy cho các nguồn được phép; không vội mở rộng thành rule "any-to-any" làm mất phân đoạn an toàn. Sau thay đổi:

1. Kiểm thử từ đúng subnet A tới đúng FQDN/VIP/port, ghi kết quả và thời gian.
2. Xác nhận firewall log chuyển từ deny sang allow cho flow hợp lệ; NAT/session đúng.
3. Xác nhận LB và API gateway có request, backend phản hồi đúng.
4. So sánh metric lỗi, latency và transaction success trước/sau.
5. Rà soát các subnet, rule, route dùng chung để phát hiện tác động phụ.
6. Lưu timeline, cấu hình trước/sau, quyết định thay đổi và bằng chứng đóng sự cố.

Việc chi nhánh A hoạt động trở lại là điều kiện quan trọng nhưng cần kiểm chứng theo giao thức ứng dụng, không chỉ ping hoặc nhìn trạng thái VPN.

## 12. Khi có chỉ báo tấn công: mở rộng phạm vi có kiểm soát

Với sự cố an ninh, câu hỏi "tài sản nào bị ảnh hưởng" còn liên quan khả năng đối tượng tấn công đã sử dụng host, tài khoản hoặc kết nối nào:

- **Tài sản phát cảnh báo:** host hoặc cảm biến đầu tiên ghi nhận dấu hiệu.
- **Tài sản giao tiếp liên quan:** các endpoint có flow thực tế với host đó trong cửa sổ liên quan.
- **Tài sản có cùng danh tính/quyền:** workload hoặc hệ thống dùng cùng credential, token, service account, khóa VPN.
- **Tài sản có đường truy cập khả dĩ:** đối tượng mà segmentation, firewall hoặc IAM policy cho phép truy cập.
- **Tài sản có hành vi xác nhận:** endpoint log, authentication record hoặc network trace có sự kiện phù hợp.

Không đồng nhất **reachable** với **compromised**. Một flow TCP thành công, một IDS alert hoặc một DNS lookup chỉ là tín hiệu cần kiểm tra; xác nhận xâm nhập đòi hỏi chuỗi bằng chứng phù hợp. Có thể dùng network segmentation map và service identity để tìm **các hướng lan truyền khả dĩ**, đồng thời sử dụng EDR, authentication log, proxy log và threat intelligence phù hợp để phân loại.

Khi nghi có command-and-control, data exfiltration hoặc lateral movement, nên ghi đường egress, DNS resolver, proxy, NAT mapping, nguồn/đích, thời điểm, số byte, process và principal liên quan. Tăng mức giám sát hoặc cô lập cần tuân theo quyền hạn và quy trình điều phối sự cố để tránh mất dấu vết hoặc gián đoạn dịch vụ ngoài phạm vi.

## 13. Các sai lầm thường khiến phạm vi ảnh hưởng bị đánh giá sai

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Dùng IP hiện tại để diễn giải log cũ | IP có thể tái sử dụng, pod/VM thay đổi | Tra DHCP, cloud instance, NAT mapping có timestamp |
| Chỉ đọc dashboard toàn hệ thống | Lỗi một subnet/tenant bị che bởi trung bình | Tách metric theo region, subnet, route, tenant thích hợp |
| Thấy một host khỏe thì kết luận subnet khỏe | Khác DNS view, identity, route và policy | Kiểm thử đa điểm, kiểm tra mẫu đại diện |
| Không có firewall deny log thì kết luận không bị chặn | Có thể không bật log, sampling hoặc chặn ở nơi khác | Kiểm tra rule/counter và hai phía ranh giới |
| VPN tunnel up đồng nghĩa mọi ứng dụng hoạt động | Tunnel chỉ là một phần đường đi | Kiểm tra route, policy, NAT, return traffic và ứng dụng |
| Coi traceroute hop im lặng là điểm lỗi | ICMP có thể bị chặn hoặc rate limit | Đối chiếu flow/probe cùng protocol và log thiết bị |
| Bỏ qua chiều về | Asymmetric route hoặc stateful firewall gây drop response | Dựng cả forward và return path |
| Ghép client PCAP với server PCAP bằng TCP sequence | Proxy L7 tạo TCP connection mới | Ghép bằng log, ID, timestamp và mapping từng leg |
| Không thấy packet ở capture rồi kết luận drop | Chọn sai interface, thiếu chiều, offloading hoặc capture loss | Kiểm tra vị trí, filter, counters, packet drop |
| Tên miền chỉ có một IP | DNS split-horizon, GeoDNS, dual stack, failover | Ghi answer/TTL/resolver theo nguồn và thời gian |
| Nhầm shared dependency với tác động đã xảy ra | Phóng đại blast radius, ưu tiên sai | Gắn trạng thái AT_RISK, kiểm tra trước khi CONFIRMED |
| Xóa/reset cấu hình ngay khi nghi ngờ | Có thể làm mất session, chứng cứ và tạo lỗi mới | Lưu trạng thái/bằng chứng và theo quy trình điều phối |
| Xem ACCEPT của flow log là end-to-end success | Flow log ghi nhận tại một điểm, có thể là sampled metadata | Đối chiếu session, application log, response |
| Bỏ qua thời gian đồng hồ lệch | Timeline sai, ghép nhầm flow/retry | UTC, NTP/PTP và nguồn timestamp rõ ràng |

Ngoài ra, thay đổi tự động từ autoscaling, service discovery, CDN và cloud load balancing có thể làm topology chuyển động liên tục. Bản đồ trong incident report nên ghi **thời điểm snapshot**, nguồn xác minh và mức độ tin cậy, không mô tả bản đồ tĩnh như cấu hình bất biến.

## 14. Mẫu ghi nhận tài sản và đường đi

Có thể dùng mẫu sau trong ticket hoặc biên bản ứng phó sự cố:

~~~text
INCIDENT ID: INC-EXAMPLE-003
Thời gian (UTC): 2026-11-28 06:10 - đang điều tra
Triệu chứng: Timeout TCP/443 từ chi nhánh A tới API VIP
Ảnh hưởng nghiệp vụ: Người dùng tại chi nhánh A không tạo được đơn

Nguồn:
  Asset ID / Host: branch-a-client-25
  IP quan sát: 10.12.6.25
  Zone / subnet: BRANCH_A / 10.12.6.0/24

Đích:
  Service: Order API
  FQDN: api.example.test
  DNS answer tại thời điểm thử: 10.40.1.20
  Port / protocol: 443 / TCP-TLS

Đường đi:
  Client -> LAN -> VPN -> Firewall R-214 -> LB VIP -> API Gateway -> App
Đường về: Chưa xác minh đầy đủ

Tài sản ảnh hưởng xác nhận:
  - Nhóm client subnet A sử dụng Order API

Tài sản nguy cơ / chưa rõ:
  - Các subnet sử dụng cùng policy R-214
  - Các service sử dụng VIP này

Bằng chứng:
  E1: client PCAP, 06:14 UTC, thấy SYN và retry
  E2: firewall ingress PCAP, 06:15 UTC, thấy SYN
  E3: firewall deny log rule R-214, 06:15 UTC
  E4: flow thành công của subnet B, 06:16 UTC

Kết luận hiện tại:
  - Có căn cứ mạnh cho thấy firewall rule R-214 chặn subnet A
  - Chưa có bằng chứng backend lỗi hoặc VPN toàn bộ bị hỏng

Thiếu dữ liệu:
  - Kiểm tra các subnet khác dùng cùng rule
  - Xác nhận đường về và kiểm thử sau thay đổi

Owner: Network on-call
Bước tiếp theo: Rà rule scope, kiểm thử có kiểm soát, cập nhật impact matrix
~~~

Mẫu này cần được cập nhật khi có bằng chứng mới, bao gồm quyết định containment/recovery và mức độ chắc chắn. Không điền **"không ảnh hưởng"** cho tài sản chưa kiểm tra.

## 15. Tiêu chí hoàn tất bước xác định phạm vi

Trước khi chuyển từ đánh giá phạm vi sang xử lý nguyên nhân hoặc khôi phục, hãy tự kiểm tra:

- [ ] Có mô tả triệu chứng, cửa sổ UTC, nguồn phát hiện, mức độ tác động nghiệp vụ và owner.
- [ ] Danh sách tài sản dùng định danh đủ ổn định, ghi IP/hostname/instance mapping tại thời điểm xảy ra sự cố.
- [ ] Có bảng **CONFIRMED_AFFECTED / SUSPECTED_AFFECTED / AT_RISK / CONFIRMED_UNAFFECTED / UNKNOWN** cùng căn cứ cho từng hàng.
- [ ] Xác định điểm vào, đích logic, IP được phân giải, port/protocol và các network zone liên quan.
- [ ] Dựng đường đi **request và response**; xác định nơi NAT, VPN encapsulation, TLS termination, firewall policy, load balancing và proxy thay đổi dữ liệu.
- [ ] Liên hệ ít nhất các nguồn telemetry cần thiết: flow/firewall/VPN, DNS, proxy/LB và application logs; dùng PCAP có kiểm soát khi cần.
- [ ] Đã kiểm tra những giả thuyết cạnh tranh, bao gồm DNS sai, mất route, policy deny, return-path lỗi và backend chậm.
- [ ] Ghi rõ bằng chứng đã thấy, điểm chưa quan sát, sampling/capture loss, clock skew và độ tin cậy.
- [ ] Đánh giá shared dependencies và blast radius; ưu tiên dịch vụ quan trọng trước, không đánh đồng khả năng tiếp cận với bị xâm nhập.
- [ ] Có đầu mối xử lý tiếp, tiêu chí xác nhận phục hồi và kế hoạch cập nhật ma trận ảnh hưởng.

Xác định đúng **tài sản và đường đi bị ảnh hưởng** là thao tác thu hẹp phạm vi bằng dữ liệu: bắt đầu từ triệu chứng của người dùng, truy ra định danh tài sản, dựng hai chiều lưu lượng qua từng ranh giới và đối chiếu các nguồn telemetry. Khi mọi mệnh đề đều gắn với thời gian, vị trí quan sát và độ tin cậy, nhóm ứng phó có thể lựa chọn biện pháp khắc phục chính xác, bảo toàn chứng cứ và hạn chế ảnh hưởng ngoài ý muốn.
