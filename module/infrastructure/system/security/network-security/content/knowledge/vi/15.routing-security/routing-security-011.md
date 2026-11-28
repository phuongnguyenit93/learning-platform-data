# Route change monitoring: giám sát thay đổi tuyến đường để bảo vệ mạng

Một hệ thống ứng dụng bỗng không truy cập được database dù máy chủ, firewall và dịch vụ đều đang chạy. Nhật ký định tuyến cho thấy prefix của database vừa được chuyển sang một **next hop** khác, khiến luồng chiều đi và chiều về không còn cùng đi qua cụm firewall stateful. Ở một tình huống khác, một phiên BGP nhận được thông báo quảng bá prefix không đúng nguồn gốc, có thể làm lưu lượng đi sai hướng hoặc mất khả năng truy cập. Những vấn đề này cho thấy **thay đổi tuyến đường** là một sự kiện có ý nghĩa vận hành **và bảo mật**.

**Route change monitoring** là quá trình quan sát, lưu dấu, so sánh, phát hiện bất thường và xác minh những thay đổi liên quan tới định tuyến: prefix được thêm hoặc rút, next hop đổi, đường mặc định chuyển hướng, metric/ưu tiên thay đổi, routing adjacency gián đoạn, policy bị sửa hoặc tuyến thực tế được lập trình khác tuyến mong muốn. Mục tiêu không phải ngăn **mọi** thay đổi: mạng cần hội tụ khi đường truyền lỗi hoặc bảo trì. Mục tiêu là **phân biệt thay đổi được kỳ vọng với thay đổi có thể gây gián đoạn, vượt ranh giới phân đoạn hoặc dẫn lưu lượng tới nơi không mong muốn**.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, chủ đề này liên kết phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, NAC, cloud và phân tích lưu lượng. Một cảnh báo route có ích khi nó giải thích được **tài sản nào bị ảnh hưởng, tuyến nào đã đổi, thay đổi có được phê duyệt không, traffic thật đi đâu và cần làm gì để khôi phục an toàn**.

> **Phạm vi học tập:** Nội dung sử dụng địa chỉ nội bộ và dải dành cho tài liệu. Các lệnh là ví dụ **đọc/quan sát** trên hệ thống được cấp quyền. Không tự thay đổi định tuyến production, quảng bá BGP/OSPF hay thử tác động đường đi của bên thứ ba.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **RIB, FIB, control plane, data plane** và lý do một thay đổi ở bảng định tuyến chưa chắc đồng nghĩa mọi gói đã đổi đường đi.
2. Nhận diện những dạng thay đổi: **route add/delete/replace, next hop, metric, preference, default route, ECMP, VRF, route leak**.
3. Mô tả tín hiệu từ **static routing, OSPF, BGP, BFD, DHCP/RA, VPN và cloud route tables**.
4. Thiết kế pipeline theo dõi route dựa trên **sự kiện, snapshot, normalized diff, source of truth và giám sát lưu lượng**.
5. Xây cảnh báo phù hợp cho **prefix quan trọng, thay đổi chưa phê duyệt, route flapping, mất tuyến và đường đi lệch firewall**.
6. Phân biệt biến động routing hợp lệ với sự cố cấu hình hoặc dấu hiệu **route hijack/leak**, giảm false positive bằng correlation.
7. Thực hiện các phép quan sát không phá hoại và viết runbook ứng cứu có kiểm chứng đường đi, quyền thay đổi và rollback.

## 2. Vì sao định tuyến là bề mặt cần giám sát an ninh?

Định tuyến quyết định **đường tiếp theo** mà gói IP có thể được gửi tới trên mỗi thiết bị trung gian. Một thay đổi không cần sửa firewall rule cũng có thể làm thay đổi:

- **Availability:** mất tuyến tới ứng dụng hoặc đường mặc định, gây timeout và lỗi truy cập.
- **Confidentiality:** traffic có thể đi qua một miền mạng/nhà cung cấp không được dự kiến, làm tăng rủi ro phơi bày metadata hoặc dữ liệu không được bảo vệ.
- **Integrity:** một số tình huống chiếm quyền đường đi có thể tạo cơ hội can thiệp nếu giao thức ứng dụng không xác thực/bảo vệ đầy đủ.
- **Segmentation:** lưu lượng có thể bỏ qua điểm kiểm tra firewall/IDS hoặc đi xuyên các VRF/zone ngoài thiết kế.
- **Observability:** sensor cũ không còn nằm trên tuyến, khiến log IDS/IPS giảm dù traffic vẫn tồn tại.
- **Service reliability:** đường dự phòng được chọn nhưng không đủ năng lực hoặc không hỗ trợ MTU/NAT/VPN phù hợp.

**Có route không đồng nghĩa được phép truy cập.** Firewall, host policy, NAC, xác thực ứng dụng, TLS và security group vẫn tác động độc lập. Ngược lại, **rule Allow đúng cũng không bảo đảm kết nối thành công** nếu route hoặc đường về không hợp lệ.

### Ba câu hỏi cần đặt khi có thay đổi

1. **Điều gì đổi?** Prefix, next hop, nguồn route, neighbor, priority, route table hay chính sách xuất/nhập route?
2. **Vì sao đổi?** Thay đổi được duyệt, sự cố link, failover, hội tụ bình thường, sai cấu hình hay hoạt động đáng ngờ?
3. **Tác động thực tế?** Những luồng nào đổi đường, có đi qua điểm bảo vệ mong muốn không, trải nghiệm dịch vụ có còn đạt yêu cầu không?

## 3. RIB và FIB: quan sát đúng lớp quyết định

Một router có thể học nhiều ứng viên cho cùng prefix. Không phải mọi ứng viên đều trở thành tuyến được dùng để chuyển gói.

| Khái niệm | Vai trò | Nguồn dữ liệu thường gặp |
|---|---|---|
| **Control plane** | Trao đổi và xử lý thông tin định tuyến, chính sách, chọn tuyến | BGP/OSPF event, neighbor state, routing daemon logs |
| **RIB – Routing Information Base** | Thông tin tuyến được lựa chọn/lưu theo thiết kế hệ thống; có thể tồn tại RIB riêng cho protocol và RIB tổng | Lệnh hiển thị routing table, API của routing stack |
| **FIB – Forwarding Information Base** | Thông tin tra cứu chuyển tiếp được lập trình cho data plane | Kernel/ASIC forwarding entries, lệnh FIB/CEF theo nền tảng |
| **Data plane** | Chuyển tiếp gói thực tế theo thông tin chuyển tiếp, ACL, encapsulation và các tính năng liên quan | Interface counters, flow logs, packet capture, active probe |
| **Routing policy** | Lọc, đánh dấu, thay đổi thuộc tính hoặc cho phép phân phối route | Route map, prefix list, import/export policy, VRF leak config |

**RIB ≠ FIB ≠ lưu lượng quan sát được.** Ví dụ một phiên BGP nhận bản tin cập nhật nhưng policy từ chối route: dữ liệu control plane thay đổi, còn FIB có thể không đổi. Một route được chọn trong RIB có thể chưa được lập trình vào FIB do next hop chưa resolve, giới hạn thiết bị hoặc lỗi nền tảng. Mặt khác, PBR, tunnel, overlay, ECMP và cache phần cứng có thể ảnh hưởng đường gói thực tế.

~~~text
   BGP / OSPF / Static / Connected routes
                     |
                     v
             Routing protocols
           + policy + best-path
                     |
                     v
              RIB / route state
                     |
            Next-hop resolution
                     |
                     v
              FIB / data plane
                     |
               Forwarded packets
                     |
           Flow / counters / captures
~~~

**Hệ quả giám sát:** một hệ thống chỉ thu syslog BGP không chứng minh mọi tuyến của thiết bị đã đổi; một hệ thống chỉ đọc kernel route table cũng có thể bỏ sót những cập nhật BGP bị policy loại bỏ. Phải thu đúng lớp đáp ứng mục tiêu phát hiện.

## 4. Những dạng route change cần phân loại

| Dạng thay đổi | Ví dụ | Tác động tiềm tàng |
|---|---|---|
| **Add** | Xuất hiện tuyến tới 10.30.30.0/24 | Mở khả năng định tuyến mới, đôi khi vượt ý định phân đoạn |
| **Withdraw/Delete** | Mất tuyến tới 10.20.20.0/24 | Mất kết nối hoặc chuyển sang đường fallback |
| **Next-hop replace** | Đổi 10.0.0.2 sang 10.0.0.3 | Lưu lượng đi qua đường/thiết bị khác |
| **Metric/administrative preference** | Một route có cost thấp hơn được chọn | Đổi đường dù prefix không đổi |
| **Default route change** | 0.0.0.0/0 hoặc ::/0 đổi gateway | Ảnh hưởng nhiều đích chưa có route cụ thể |
| **More-specific route** | Xuất hiện 10.20.20.128/25 bên cạnh /24 | Lưu lượng tới nửa subnet được chọn theo **longest prefix match** |
| **ECMP member change** | Thêm/bớt một next hop trong nhóm equal-cost | Chỉ một phần flow đổi đường, có thể gây lệch trạng thái firewall |
| **VRF import/export** | Prefix xuất hiện ở VRF Guest vốn không được phép | Nguy cơ route leaking hoặc sai phân đoạn |
| **Routing adjacency change** | OSPF neighbor Down, BGP session reset | Hội tụ, rút nhiều route hoặc chọn đường dự phòng |
| **Policy change** | Route-map thay đổi lọc/import prefix | Có thể chưa có hiệu ứng ngay hoặc ảnh hưởng hàng loạt route |
| **Overlay/tunnel path change** | VPN/SD-WAN chuyển sang tunnel khác | MTU, NAT, độ trễ hoặc điểm kiểm tra bảo mật thay đổi |

**Một prefix có thể có nhiều tuyến ứng viên.** Route bị rút khỏi một protocol không nhất thiết khiến toàn bộ kết nối mất nếu còn đường khác. Cần xác định **tuyến được lựa chọn, FIB và trạng thái dịch vụ**, không chỉ đếm số bản tin withdraw.

### Longest prefix match khác route preference

Giả sử có hai route:

~~~text
10.20.20.0/24   via 10.0.0.2
10.20.20.128/25 via 10.0.0.3
~~~

Lưu lượng tới **10.20.20.150** thường khớp route **/25** cụ thể hơn; traffic tới **10.20.20.50** khớp **/24**. Sự xuất hiện của một more-specific route có thể đổi đường cho một phần mạng ngay cả khi **default route và route /24 vẫn nguyên**. Sau khi chọn độ dài prefix phù hợp, routing stack mới áp dụng các quy tắc chọn đường trong những tuyến cạnh tranh cùng đích theo thiết kế.

## 5. Theo dõi route thay đổi do đâu?

### 5.1. Static và connected routes

Route tĩnh có thể do người quản trị, automation, mạng VPN hoặc agent hệ điều hành tạo. Connected route thay đổi khi địa chỉ/giao diện hoặc trạng thái link thay đổi.

Những nguồn thường gặp:

- Network device configuration change log.
- Kernel routing notifications, system event logs, audit của automation.
- Interface up/down, thay đổi IP/prefix, DHCPv4 gateway hoặc IPv6 RA trên host.
- VPN client kết nối/ngắt, tạo route tới mạng công ty và thay đổi metric.

Một thay đổi route tĩnh **không nhất thiết là tấn công**; có thể là failover hoặc triển khai được phê duyệt. Nhưng route mặc định bị đổi không rõ lý do trên máy chủ quản trị là sự kiện đáng quan tâm hơn route tạm của VPN trên laptop đang đăng nhập.

### 5.2. OSPF và giao thức nội bộ

Các giao thức link-state như **OSPF** duy trì quan hệ neighbor, dữ liệu trạng thái liên kết và tính toán đường đi theo topology. Một link down hoặc cost change có thể khiến nhiều route đổi next hop sau hội tụ.

Nguồn tín hiệu:

- Neighbor state, interface state và authentication errors.
- Thay đổi LSA/topology database hoặc số lần SPF calculation, nếu nền tảng hỗ trợ.
- Route add/delete/replace trong RIB/FIB sau hội tụ.
- Thay đổi cấu hình area, summarization, redistribution, cost hoặc filter.

Một cảnh báo **“OSPF neighbor Down”** cho biết quan hệ neighbor có vấn đề; không tự chứng minh route đã bị chiếm quyền. Phải đối chiếu link, thiết bị, maintenance, thay đổi cấu hình và tuyến thực tế.

### 5.3. BGP và các phiên biên

**BGP** trao đổi thông tin reachability giữa các peer theo chính sách. Thay đổi best path có thể đến từ route withdrawal, cập nhật thuộc tính, sự kiện peering hoặc policy.

Các trường cần quan sát khi hệ thống hỗ trợ:

- Peer/neighbor và trạng thái phiên.
- Prefix family **IPv4 unicast / IPv6 unicast** và VRF/AFI/SAFI phù hợp.
- Prefix được **received**, **accepted** sau policy, **selected** và **advertised** — những tập này có thể khác nhau.
- AS_PATH, NEXT_HOP, LOCAL_PREF, MED, community và **origin AS**, tùy nhu cầu.
- Số prefixes theo peer, route churn, session resets và thay đổi policy.

**Đừng coi một BGP UPDATE là thay đổi FIB.** Update có thể không thắng best-path selection hoặc bị policy lọc. Tương tự, sự thay đổi best path có thể xảy ra do nhiều yếu tố mà prefix không biến mất khỏi RIB.

### 5.4. Cloud, SD-WAN và hạ tầng điều khiển tập trung

Mạng cloud có các route table được quản lý qua control-plane API; SD-WAN có thể chọn đường dựa trên policy, hiệu năng và tunnel health. Cần xem:

- **Control-plane change events**: ai thay route, lúc nào, bằng API/console/IaC nào.
- **Effective routes** cho NIC/subnet hoặc workload, nếu nền tảng hỗ trợ.
- **Tunnel/VPN/peering/Transit Gateway**: trạng thái kết nối và route propagation.
- **Network flow logs**: traffic thật có đi qua next hop/đường dự kiến không.

Không thể mặc định cloud route priority, propagation và security group giống router vật lý. **Nguồn route và rule chọn route phụ thuộc nhà cung cấp**; khi kiểm tra phải dựa trên mô hình đúng của nền tảng đó.

## 6. Route hijack và route leak dưới góc nhìn phát hiện

**Route hijack** là tình huống thông tin định tuyến được công bố/sử dụng không đúng quyền, khiến traffic có thể bị dẫn đi sai đích hoặc mất khả năng truy cập. **Route leak** là tình huống một route được phân phối ra ngoài phạm vi chính sách dự kiến, ví dụ giữa những quan hệ BGP hoặc VRF không được phép.

Ở mức phòng thủ, cần theo dõi những dấu hiệu như:

1. **Origin AS bất thường** đối với prefix công khai mà tổ chức quản lý.
2. More-specific advertisement xuất hiện từ nguồn hoặc đường đi không mong đợi.
3. Prefix nội bộ xuất hiện trong **VRF/zone** lẽ ra không được phép nhận.
4. Số route nhận từ một peer tăng bất thường hoặc danh sách prefix vượt chính sách import.
5. Route của đối tác được quảng bá tới peer khác trái hợp đồng routing.
6. Traffic path thay đổi từ đường bảo vệ sang một đường không được kiểm soát.

**Không được kết luận route hijack chỉ từ một AS_PATH khác trước.** Internet có các thay đổi hợp lệ do bảo trì, traffic engineering, failover và hoạt động của nhà cung cấp. Một sự cố cần xác minh **prefix ownership, nguồn thông báo, chính sách peering, các điểm quan sát độc lập và tác động thực tế**.

### RPKI ROA và Route Origin Validation

Với BGP công khai, **Resource Public Key Infrastructure (RPKI)** và **Route Origin Authorization (ROA)** hỗ trợ kiểm chứng việc một AS được chủ tài nguyên IP ủy quyền **origin** một prefix. Các kết quả Route Origin Validation (ROV) thường được diễn giải là **Valid, Invalid hoặc NotFound**, dựa trên dữ liệu ROA và prefix/origin quan sát.

| Kết quả | Ý nghĩa | Không được suy diễn |
|---|---|---|
| **Valid** | Có ROA phù hợp cho prefix và origin AS theo quy tắc xác minh | Không chứng minh toàn bộ AS_PATH an toàn, traffic không bị can thiệp |
| **Invalid** | Mâu thuẫn với dữ liệu ROA áp dụng theo cơ chế ROV | Có thể do cấu hình ROA/prefix sai hoặc chưa cập nhật; cần xác minh trước khi kết luận cố ý tấn công |
| **NotFound** | Không có ROA đủ phù hợp để xác định trạng thái Valid/Invalid | Không đồng nghĩa tuyến độc hại; cũng không đồng nghĩa được chứng minh hợp lệ |

**ROV chỉ kiểm tra origin authorization**, không bảo đảm tất cả quan hệ quảng bá trong AS_PATH đúng chính sách hay ngăn được mọi route leak. Khi sử dụng trên mạng production, cần quản lý ROA, giám sát thay đổi và hiểu chính sách xử lý tuyến Invalid của nhà cung cấp.

### Guardrail vận hành BGP

Những biện pháp có thể kết hợp gồm **prefix filtering, max-prefix theo peer, ROV, kiểm soát export/import, giám sát BGP session, logging và quản lý thay đổi**. Max-prefix có thể giúp giảm rủi ro nhận quá nhiều route nhưng cũng có thể khiến session bị ảnh hưởng nếu ngưỡng đặt sai; cần lựa chọn theo hợp đồng, baseline và năng lực thiết bị.

## 7. Giám sát route trên nhiều ngữ cảnh: VRF, IPv4 và IPv6

Một network device có thể duy trì nhiều routing table:

- **Global/default routing table**.
- **VRF** dành cho Guest, Employee, Production, Management hoặc khách hàng khác.
- **IPv4 và IPv6 routing tables** độc lập về địa chỉ, prefix và next hop.
- Routing namespace hoặc container/host network stack trong hệ điều hành.
- Tables cho policy-based routing trong một số nền tảng.

**Route cùng prefix nhưng nằm ở hai VRF không phải cùng một đối tượng**, và việc xuất hiện thêm prefix ở VRF khác có thể là dấu hiệu **route leaking** hoặc thay đổi được duyệt. Hệ thống giám sát không được gộp các route khác VRF thành một bản ghi rồi kết luận sai.

### Những lưu ý riêng cho IPv6

IPv6 có địa chỉ default **::/0**; next hop có thể là **link-local address** cần gắn với interface hoặc zone phù hợp. Trên nhiều hệ điều hành, interface nhận default router qua **Router Advertisement (RA)**, nên một host có thể đổi default route ngay khi nhận RA, không cần sửa DHCPv6.

~~~text
IPv4 default route:  0.0.0.0/0    via 10.10.10.1
IPv6 default route:  ::/0        via fe80::1%eth0
                     (ví dụ tên interface mang tính minh họa)
~~~

**Không giám sát chỉ IPv4 khi mạng dual-stack.** Một sự cố IPv6 có thể khiến client thử đường khác, chọn kết nối chậm hoặc đi qua ranh giới bảo mật chưa được kiểm chứng. Ngược lại, IPv6 route thay đổi bình thường do RA hoặc privacy addresses không tự là tấn công.

## 8. Định nghĩa source of truth và baseline có thể đối chiếu

**Source of truth** là dữ liệu quy hoạch/đã phê duyệt về các prefix, nguồn route, VRF, next hop và chính sách. Một tập route được quan sát tại một thời điểm (**snapshot**) là **observed state**. Giám sát thay đổi có ích khi đối chiếu:

~~~text
             Desired state / Source of truth
            Prefix ownership, VRF, expected peers,
            allowed next hops, maintenance windows
                             |
                             v
                     Policy comparison
                             ^
                             |
           Observed state / Route telemetry
        RIB/FIB, BGP/OSPF events, cloud routes,
        interface/tunnel state, timestamps
                             |
                             v
                 Alert + impact correlation
~~~

Baseline không nên là bản chụp cứng bất biến. Một hệ thống có HA, ECMP, BGP nhiều peer hoặc SD-WAN có thể có **nhiều tuyến hợp lệ**. Nên biểu diễn **tập trạng thái cho phép**, điều kiện failover và khoảng thời gian thay đổi đã được duyệt.

### Mẫu dữ liệu mô tả route

| Trường | Ý nghĩa |
|---|---|
| **Device ID / site** | Thiết bị và vị trí; không chỉ hostname có thể bị đổi |
| **VRF / routing table** | Miền định tuyến có hiệu lực |
| **Address family** | IPv4 hoặc IPv6 |
| **Destination prefix** | Prefix đích, độ dài rõ ràng |
| **Protocol / origin** | Connected, static, OSPF, BGP, RA... |
| **Selected next hop(s)** | Một hoặc nhiều next hop/egress interface; cần lưu ECMP |
| **Preference / metric** | Thông tin chọn route theo nền tảng |
| **Status / reason** | Active/inactive, withdrawn, unresolved next hop, thay đổi policy |
| **Peer/source** | Neighbor hoặc nơi phát sinh thông tin tuyến |
| **Observed timestamp** | Thời gian event/snapshot và múi giờ |
| **Change reference** | Ticket, phiên bản cấu hình hoặc sự kiện cloud automation |
| **Expected policy** | Allowed/Unexpected/Pending review theo nguồn sự thật |

**Thời gian rất quan trọng.** Prefix được cấp lại, tunnel thay đổi, DHCP/RA đổi gateway hoặc HA failover có thể khiến cùng một route trỏ về thiết bị khác ở thời điểm khác. Không nên kết luận dựa trên snapshot hiện tại để suy hoàn toàn lịch sử.

## 9. Pipeline route change monitoring

Một hệ thống phù hợp có thể kết hợp **event-driven** và **periodic snapshot**:

~~~text
Network devices / Hosts / Cloud controllers
           |        |             |
           |        |             +-- Audit/API/IaC changes
           |        +-- Kernel route notifications
           +-- Routing protocol events / telemetry
                       |
                       v
                Collector / Transport
                       |
                  Normalize fields
                       |
               Deduplicate / Time align
                       |
              Route diff and correlation
                /                   \
          Source of truth        Live health
          / Change ticket       Flow/Probe/Logs
                \                   /
                       |
                       v
               Alert + investigation
                       |
                Runbook / response
~~~

### Các phương án thu thập

| Phương án | Lợi ích | Hạn chế |
|---|---|---|
| **Syslog/router event log** | Phát hiện thay đổi neighbor và một số route nhanh | Không phải thiết bị nào cũng ghi mọi route hoặc cung cấp đủ before/after |
| **Streaming telemetry / gNMI** | Có thể cập nhật gần thời gian thực và theo mô hình dữ liệu | Khả năng và đường dẫn dữ liệu phụ thuộc sản phẩm/phiên bản |
| **SNMP polling/traps** | Hữu ích cho interface/neighbor và các object được hỗ trợ | Polling có thể bỏ lỡ thay đổi ngắn; trap thiếu chi tiết hoặc mất gói |
| **BGP Monitoring Protocol (BMP)** | Quan sát thông tin BGP từ router hỗ trợ theo cấu hình | Không thay thế quan sát FIB hoặc xác minh gói thật |
| **Route snapshots bằng CLI/API** | Đối chiếu theo lịch, dễ hiểu với hệ thống nhỏ | Có thể bỏ qua route flap ngắn giữa hai lần poll |
| **Linux netlink route events** | Theo dõi add/delete/replace trong kernel | Chỉ thấy namespace/host tương ứng, không toàn bộ mạng |
| **Cloud audit/effective routes** | Truy nguồn user/API/IaC và các route cloud có hiệu lực khi hỗ trợ | API khác nhau theo provider, độ trễ và scope khác nhau |
| **Synthetic reachability/flow logs** | Cho bằng chứng tác động người dùng và data plane | Không tự xác định nguyên nhân route change |

**Tốt nhất dùng nhiều nguồn bổ trợ:** event cho tốc độ phát hiện, snapshot để đối chiếu trạng thái cuối cùng, log thay đổi để tìm nguyên nhân, flow/probe để xác nhận tác động.

### Tổ chức và bảo vệ telemetry

- Sử dụng đồng bộ thời gian, lưu timestamp kèm timezone và độ trễ nhận event.
- Thu thập qua kênh xác thực, giới hạn quyền đọc cấu hình/route theo vai trò.
- Cấu hình retention, phân loại dữ liệu nhạy cảm về topology và địa chỉ quản trị.
- Ghi rõ nguồn thiết bị và VRF; tránh nhầm tên thiết bị/IP quản trị đã đổi.
- Xử lý duplicate, event out of order, collector restart và mất event.
- Không dùng sự **vắng mặt của event** làm bằng chứng chắc chắn không có thay đổi.

## 10. Cách tạo route diff có ý nghĩa

**Route diff** là so sánh trạng thái tuyến trước/sau, không chỉ so sánh chuỗi output CLI. Nên chuẩn hóa route thành các trường có nghĩa rồi mới đối chiếu.

### Ví dụ trước và sau

~~~text
BEFORE (lúc 09:50)
Device: core-r1
VRF: production
Prefix: 10.20.20.0/24
Selected next hop: 10.0.0.2
Protocol: OSPF
Status: installed

AFTER (lúc 10:02)
Device: core-r1
VRF: production
Prefix: 10.20.20.0/24
Selected next hop: 10.0.0.3
Protocol: OSPF
Status: installed
~~~

Ở đây **route vẫn tồn tại**, nhưng **next hop đổi**. Một detector chỉ cảnh báo khi prefix biến mất sẽ bỏ lỡ sự kiện này.

### Pseudocode so sánh được kiểm soát

~~~text
key = (device, VRF, address_family, destination_prefix)

For each key:
    Compare normalized selected routes before and after.
    Detect:
        - prefix appeared / disappeared
        - next-hop set changed
        - protocol, metric or preference changed
        - selected route vs FIB mismatch if telemetry exists
    Correlate:
        - interface / BGP / OSPF / tunnel health
        - approved maintenance / automation change
        - application health and flow evidence
    Prioritize impact:
        - critical prefix?
        - crosses security boundary?
        - default route or broad route?
        - unexpected source / peer / next hop?
~~~

Đây là **pseudocode học thuật**, không phải script dùng trên router thật. Với ECMP, cần so sánh **tập các next hop** và những thuộc tính liên quan, tránh đánh dấu khác biệt chỉ vì thứ tự hiển thị thay đổi. Với routing policy, phải xác định khóa dữ liệu còn gồm route distinguisher, address family hoặc ngữ cảnh phù hợp theo nền tảng.

### Phân biệt “route changed” với “path changed”

Một route có thể giữ cùng next hop nhưng đường nằm phía sau next hop lại đổi do định tuyến của mạng trung gian. Ngược lại, route FIB đổi nhưng ECMP hashing có thể khiến một flow mẫu tiếp tục đi đường cũ. Vì thế muốn đánh giá ảnh hưởng, cần **telemetry nhiều hop và probe được thiết kế có kiểm soát**, không chỉ một snapshot trên một router.

## 11. Alert engineering: ưu tiên điều quan trọng

Một cảnh báo route tốt không nên chỉ thông báo “routing table changed”. Nó phải chỉ ra **đối tượng, phạm vi, lý do nghi ngờ, độ tin cậy và tác động cần xác minh**.

| Use case | Điều kiện phát hiện | Ưu tiên gợi ý | Bằng chứng cần thêm |
|---|---|---|---|
| **Default route đổi bất thường** | 0.0.0.0/0 hoặc ::/0 chuyển gateway ngoài tập cho phép | Cao trên server/thiết bị trọng yếu | Change log, interface state, cloud/RA event |
| **Critical prefix mất** | Route tới mạng DB/auth/management biến mất khỏi RIB/FIB cần thiết | Cao nếu dịch vụ bị ảnh hưởng | Health checks, route khác còn tồn tại, failover |
| **More-specific route mới** | /25 xuất hiện dưới /24 trọng yếu, next hop lạ | Trung bình–cao tùy phạm vi | Route origin, policy và packet path |
| **VRF leak** | Prefix production xuất hiện trong Guest VRF ngoài quy hoạch | Cao nếu ranh giới bị thay đổi | VRF import/export config, reachability test |
| **BGP origin thay đổi** | Prefix công khai xuất hiện từ origin AS không kỳ vọng | Cao nếu xác minh bất thường | RPKI/ROA, nhiều điểm nhìn, nhà mạng |
| **BGP route churn** | Prefix update/withdraw vượt baseline theo peer | Tùy dịch vụ/tác động | Peer health, maintenance, counter và route stability |
| **OSPF neighbor flapping** | Neighbor Up/Down lặp lại trong cửa sổ thời gian | Tùy topology | Link errors, BFD, CPU, change ticket |
| **FIB/RIB inconsistency** | Route được chọn nhưng forwarding entry không phù hợp | Cao nếu ảnh hưởng đường đi | Device state, platform health, counters |
| **VPN/SD-WAN path failover** | Route chuyển tunnel ngoài kế hoạch hoặc liên tục | Tùy thiết kế dự phòng | Tunnel telemetry, latency/loss và chính sách |

### Tránh báo động giả bằng correlation

Một sự kiện route mới có thể hoàn toàn hợp lệ nếu:

- Bảo trì đường truyền có ticket đã phê duyệt.
- Router dự phòng tiếp quản sau khi link chính lỗi.
- OSPF/BGP hội tụ trong khoảng ngắn do thiết bị được nâng cấp.
- SD-WAN chuyển đường khi đo được chất lượng dưới ngưỡng đã thiết kế.
- Cloud automation cập nhật route cùng một deployment được phê duyệt.

Nhưng **có change ticket không tự động chứng minh an toàn**. Vẫn cần kiểm tra route thực tế, phạm vi thay đổi và kết quả dịch vụ. Một ticket hợp lệ có thể triển khai sai.

### Các kỹ thuật giảm noise

1. **Dedupe** sự kiện trùng theo thiết bị/VRF/prefix/điều kiện trong cửa sổ phù hợp.
2. **Group by root cause:** một link down có thể kéo theo hàng trăm route withdraw.
3. **Maintenance window awareness:** điều chỉnh mức ưu tiên, không xóa toàn bộ log trong cửa sổ thay đổi.
4. **Hysteresis/debounce có chọn lọc:** tránh bắn cảnh báo mỗi lần hội tụ rất ngắn, nhưng không làm mất sự kiện nguy hiểm.
5. **Impact-based severity:** route tới mạng DB, management, DNS hoặc identity quan trọng hơn route lab ít sử dụng.
6. **Cross-check source of truth:** chỉ tạo cảnh báo nghiêm trọng khi vượt ranh giới được phê duyệt hoặc gây tác động.

Không đặt một ngưỡng “N route/minute” giống nhau cho Internet BGP full table, router chi nhánh và host laptop. Baseline phải theo **loại thiết bị và tập prefix**.

## 12. Route flapping và sự ổn định của hệ thống

**Route flapping** là tình trạng tuyến hoặc các điều kiện dẫn đến chọn tuyến thay đổi lặp đi lặp lại. Nó có thể làm tăng CPU/control-plane load, gây mất gói, tạo hội tụ liên tục và khiến log nhiễu.

~~~text
09:00  Route A selected
09:01  Route A withdrawn -> Route B selected
09:02  Route A returns   -> Route A selected
09:04  Route A withdrawn -> Route B selected
09:05  Route A returns   -> Route A selected
~~~

Những nguyên nhân thường gặp:

- Link/interface vật lý lỗi hoặc mất ổn định.
- BFD/keepalive/hello timeout hoặc cấu hình không phù hợp.
- Thiết bị quá tải, lỗi routing daemon, MTU hoặc packet loss trên đường control plane.
- Routing policy hoặc automation liên tục thay đổi cấu hình.
- Dịch vụ tunnel/SD-WAN chuyển đường do chất lượng chập chờn.

Phát hiện nên đo **số lần chuyển đổi, tổng thời gian route bất ổn, prefix/neighbor bị ảnh hưởng và tỷ lệ lỗi dịch vụ**. Phải kiểm tra liệu các chuyển đổi có được hệ thống HA chủ động thiết kế hay không trước khi gắn nhãn sự cố.

**BGP route flap dampening** tồn tại như một kỹ thuật giảm tác động quảng bá bất ổn, nhưng cấu hình không phù hợp có thể trì hoãn khôi phục route hợp lệ. Không bật/điều chỉnh trên production chỉ vì phát hiện nhiều UPDATE mà chưa đánh giá mạng và khuyến nghị thiết bị.

## 13. Định tuyến bất đối xứng và firewall stateful

Nhiều firewall stateful dựa trên trạng thái kết nối quan sát được. Nếu **chiều đi** và **chiều về** đi qua các firewall khác nhau mà không có đồng bộ state hoặc cơ chế hỗ trợ phù hợp, một thiết bị có thể không nhận ra gói phản hồi của phiên đã được cho phép.

~~~text
Client 10.10.10.25
       |
     FW-A  ------>  App 10.20.20.10
       ^                   |
       |                  FW-B
       |                   |
       +------ Không đi cùng đường --------

  FW-A thấy phiên khởi tạo.
  FW-B có thể chỉ thấy phản hồi, không có state phù hợp.
~~~

Trong giám sát route, cần theo dõi:

1. Tuyến tới mạng ứng dụng và tuyến **trả về mạng client**.
2. Next hop, ECMP, NAT và VRF của cả hai chiều.
3. Vị trí các firewall, trạng thái HA synchronization và điểm đặt IDS/IPS.
4. Flow logs có cho thấy traffic chuyển qua thiết bị khác sau route change không.
5. MTU/tunnel và đường dự phòng có thay đổi cách xử lý phiên không.

**Không tự sửa bằng cách mở rộng Allow Any–Any.** Nếu nguyên nhân là định tuyến bất đối xứng hoặc mất state, nới firewall rule có thể làm giảm bảo mật mà chưa khôi phục kết nối. Cần làm rõ đường đi hai chiều trước.

## 14. Route change và ranh giới phân đoạn

Giả sử có ba VRF: **Guest**, **Production** và **Management**. Theo chính sách, Guest chỉ ra Internet qua gateway kiểm soát, không có route trực tiếp tới mạng database Production.

~~~text
                   [Guest VRF]
                  10.50.0.0/16
                       |
                [Security gateway]
                       |
                   [Internet]

                 [Production VRF]
                  10.20.0.0/16
                       |
                 [DB subnet]
                  10.20.30.0/24

          [Management VRF]
            10.40.0.0/16
~~~

Nếu một thay đổi import/export route khiến **10.20.30.0/24** xuất hiện trong Guest VRF, đó là **sai lệch quy hoạch** cần ưu tiên kiểm tra. Tuy nhiên, **có route không đủ chứng minh Guest đã truy cập thành công database**: còn phụ thuộc data-plane path, ACL/firewall, chính sách host và ứng dụng. Điều này đòi hỏi kiểm tra ở cả **routing table và điểm thực thi truy cập**.

### Ma trận ranh giới

| Nguồn | Đích | Trạng thái route mong muốn | Chính sách truy cập mong muốn |
|---|---|---|---|
| Guest | Internet | Qua gateway kiểm soát | Dịch vụ công khai theo policy |
| Guest | Production DB | Không có route trực tiếp trái phép | Deny |
| Employee | App HTTPS | Route qua firewall được kiểm soát | Allow TCP/443 theo nguồn và ứng dụng |
| App | Database | Route nội bộ theo vùng tin cậy | Chỉ app được phê duyệt tới DB service |
| Management | Thiết bị mạng | Qua đường quản trị có giám sát | Chỉ identity và nguồn đã xác thực |

Khi route thay đổi, hệ thống cần so với **ma trận nghiệp vụ**, không chỉ trạng thái reachability. Một đường đi cho phép Guest tới DB có thể là vấn đề dù server chưa ghi nhận request độc hại.

## 15. Quan sát route bằng công cụ chỉ đọc

### 15.1. Host Linux được phép quản trị

~~~bash
ip -4 route show
ip -6 route show
ip rule show
ip -6 rule show
ip -br addr
ip -br link
~~~

Các lệnh trên quan sát route, policy routing và trạng thái interface. Nếu hệ thống dùng **network namespace**, VRF hoặc container, cần xem đúng ngữ cảnh; route table của host không tự đại diện mọi namespace/workload.

Có thể dùng lệnh theo dõi event tương ứng khi được phép:

~~~bash
ip monitor route
~~~

Lệnh này **quan sát thay đổi kernel route từ thời điểm bắt đầu chạy**, không cung cấp đầy đủ lịch sử quá khứ và không tự cho biết ai sửa route. Nó có thể chạy liên tục tới khi dừng thủ công. Trên hệ thống thật, chỉ dùng theo quy trình vận hành và log collection được chấp thuận.

### 15.2. Host Windows được phép quản trị

~~~powershell
route print
Get-NetRoute -AddressFamily IPv4
Get-NetRoute -AddressFamily IPv6
Get-NetIPInterface
Get-NetAdapter
~~~

**Windows PowerShell/NetTCPIP cmdlets** cần phiên bản hệ điều hành/module phù hợp. Route print cho snapshot, còn để xác định nguyên nhân thay đổi cần **event logs, VPN client logs, cấu hình interface/DHCP/RA và audit từ endpoint management**.

### 15.3. Router và thiết bị mạng

Lệnh khác nhau theo nhà sản xuất. Các nhóm truy vấn cần tìm trong tài liệu thiết bị:

~~~text
Show IPv4/IPv6 routing table in selected VRF
Show selected routes vs forwarding entries
Show BGP neighbors, accepted/selected/advertised routes
Show OSPF neighbors and interface state
Show interface, BFD and tunnel health
Show running configuration and approved configuration diff
Show logs/audit trail related to routing changes
~~~

Không đưa cú pháp vendor cụ thể vào hệ thống khác mà chưa xác minh. Một lệnh **show** được kỳ vọng chỉ đọc, nhưng có thể trả về rất nhiều thông tin ở thiết bị lớn; cần tuân thủ giới hạn quyền, công suất và bảo mật topology.

### 15.4. Kiểm chứng đường đi

Trong lab được phép, có thể dùng phép thử tới **đích đã được cấp quyền**:

~~~bash
ping -c 3 10.20.20.10
traceroute 10.20.20.10
~~~

Trên Windows, công cụ tương ứng có thể là **ping** và **tracert**. **ICMP bị chặn, ECMP hashing, overlay/tunnel và thiết bị không trả TTL exceeded** có thể khiến traceroute thiếu hop hoặc trả đường khác. Một traceroute đơn lẻ **không chứng minh toàn bộ đường đi thực của mọi phiên TCP/UDP**, và cũng không đủ chứng minh có tấn công.

## 16. Đọc sự kiện route change có cấu trúc

Một log nên chứa đủ dữ liệu để điều tra:

~~~yaml
# Synthetic event; không phải schema của một sản phẩm cụ thể.
event_time: "2026-11-28T10:02:12+07:00"
device: core-r1
site: data-center-a
vrf: production
address_family: ipv4
destination: 10.20.20.0/24
change_type: next_hop_replaced
old_next_hops: [10.0.0.2]
new_next_hops: [10.0.0.3]
route_source: ospf
rib_selected: true
fib_confirmed: unknown
expected: unknown
change_ticket: none_found
business_service: internal-application
review_status: needs_investigation
~~~

Đây là **sự kiện tổng hợp**. Sự tồn tại của trường **fib_confirmed: unknown** phản ánh rằng việc thấy route RIB đổi **chưa** chứng minh FIB đã cập nhật. Trường **change_ticket: none_found** cũng **không có nghĩa chắc chắn không được phép**: hệ thống tích hợp có thể thiếu ticket hoặc sự cố failover xảy ra tự động.

### Thứ tự ưu tiên điều tra sự kiện

1. **Xác định device/VRF/prefix chính xác** và xem event được tạo từ nguồn nào.
2. Đọc trước–sau và xem có thay đổi next hop, metric, source hoặc route cụ thể hơn không.
3. Kiểm tra ticket, automation, thay đổi link/tunnel/neighbor và thời điểm tương ứng.
4. So sánh route ở các thiết bị liên quan, FIB nếu khả dụng, và đường đi chiều về.
5. Kiểm tra health của ứng dụng và counter của firewall/IPS.
6. Đánh giá việc xử lý cần phối hợp network/SOC/app owner hay chỉ cập nhật baseline.

## 17. Runbook khi phát hiện route change đáng ngờ

### Giai đoạn 1 — Triage và xác minh

- Xác định **sự kiện thật hay dữ liệu trùng/thiếu do collector**.
- Ghi **thiết bị, VRF, AFI, prefix, next hop trước/sau, timestamp và nguồn thông tin**.
- Xác minh criticality của prefix và owner dịch vụ; kiểm tra user-facing error, DNS, API, VPN và telemetry.
- Tìm liên quan tới change ticket, maintenance, link down, BFD/OSPF/BGP state.
- Đánh dấu trạng thái **EXPECTED / UNEXPECTED / UNCONFIRMED**, không gọi ngay là route hijack.

### Giai đoạn 2 — Xác định phạm vi và nguyên nhân

- Tra tuyến tới đích và **tuyến phản hồi** từ khu vực dịch vụ.
- Kiểm tra route more-specific, default, VRF import/export, ECMP và FIB.
- Đối chiếu firewall/NAT/IDS path; xác minh sensor còn nằm trên traffic path không.
- Nếu liên quan BGP công khai, kiểm tra nguồn công bố, RPKI/ROA, các góc nhìn đáng tin và làm việc với ISP/peer.
- Nếu cloud, xem audit log người dùng/API, IaC changes, effective route và trạng thái gateway/tunnel.

### Giai đoạn 3 — Kiềm chế và phục hồi có phê duyệt

- Nếu thay đổi được xác minh là lỗi cấu hình, chuẩn bị **rollback cụ thể** trên đúng thiết bị/VRF/prefix.
- Nếu sự kiện do failover chính đáng, kiểm tra **tuyến dự phòng có đủ điều kiện an toàn và dung lượng** trước khi đưa traffic trở lại.
- Nếu nghi route leak/hijack, phối hợp nhóm mạng/nhà cung cấp và quy trình ứng cứu, không tự quảng bá route đối kháng.
- Tránh “sửa nhanh” bằng cách mở **Allow Any–Any**, tắt BGP policy hoặc vô hiệu hóa toàn bộ kiểm soát import/export.
- Ghi thời gian áp dụng, người duyệt, cấu hình thay đổi và tác động dịch vụ.

### Giai đoạn 4 — Xác nhận end-to-end

1. RIB/FIB đã thể hiện tuyến mong muốn và không có route lạ cụ thể hơn.
2. Luồng đi/chiều về qua đúng security boundary.
3. Firewall/IPS và VPN có phiên/luồng hoạt động theo thiết kế.
4. DNS, ứng dụng, database, API và người dùng đại diện truy cập thành công.
5. Latency, packet loss, BGP/OSPF stability và flow metrics hồi phục.
6. Cảnh báo liên quan giảm hợp lý, không biến mất chỉ vì sensor bị mất visibility.

### Giai đoạn 5 — Hậu kiểm

Lưu diễn tiến sự kiện, root cause, phạm vi tác động, độ trễ phát hiện, tác động đến người dùng, lý do chọn mitigation, kết quả rollback và cách cải thiện. Cập nhật source of truth, detection và quy trình review theo bài học thực tế.

## 18. Case study: đổi next hop khiến truy cập API không ổn định

**Bối cảnh giả định:** Công ty có hai firewall **FW-A** và **FW-B** phân tách Employee và Application. Cụm firewall có cơ chế quản lý state riêng, nhưng một thay đổi định tuyến khiến một số traffic chiều về không còn đi qua thiết bị đã nhìn thấy phiên khởi tạo. Nhân viên báo lỗi HTTPS ngẫu nhiên, trong khi server API vẫn khỏe.

### Topology tối giản

~~~text
             Employee 10.10.10.0/24
                       |
                     FW-A
                       |
                  App 10.20.20.10
                       |
                Next hop đổi
                       |
                     FW-B

    Trước: request và reply cùng path được hỗ trợ
    Sau:  một phần reply không khớp state ở FW-B
~~~

### Dữ liệu quan sát

| Nguồn | Bằng chứng giả định |
|---|---|
| Route snapshot | Prefix 10.10.10.0/24 ở router phía app đổi next hop từ FW-A sang FW-B |
| OSPF events | Neighbor/cost change gần thời điểm lỗi bắt đầu |
| Firewall logs | FW-B thấy một số gói reply không có state tương ứng |
| App logs | Có request được xử lý và phản hồi được gửi |
| Client | Một số kết nối HTTPS timeout hoặc phải thử lại |
| Change calendar | Không có triển khai ứng dụng; lịch maintenance mạng cần xác minh |

### Các giả thuyết cần phân biệt

1. **Asymmetric routing:** gói phản hồi đi qua thiết bị không có state phù hợp.
2. **State sync/HA issue:** đồng bộ phiên không hoạt động như thiết kế.
3. **ECMP distribution:** chỉ một số flow bị ảnh hưởng do next hop set thay đổi.
4. **MTU/PMTUD hoặc tunnel:** đường mới có MTU thấp hơn và ICMP thiết yếu bị chặn.
5. **Lỗi ứng dụng độc lập:** request timeout do backend chậm, không do route change.

### Quy trình phân tích

1. Xác minh route ở **cả hai đầu**, không chỉ router gần client.
2. Lấy route diff có timestamp, protocol source, metric và next-hop set.
3. Đối chiếu OSPF neighbor, interface/BFD, state sync và change ticket.
4. Kiểm tra packet/flow evidence tại đúng các điểm trên đường; xác minh NAT và trạng thái phiên.
5. Nếu lỗi routing được xác nhận, triển khai khôi phục theo phê duyệt và kiểm tra lại **phiên mới** lẫn ứng dụng.
6. Cập nhật monitor để cảnh báo **critical prefix next-hop changed + firewall path asymmetry**, thay vì chỉ thông báo tổng quát “route changed”.

**Kết luận phù hợp nếu chỉ có route diff:** “Thay đổi next hop có khả năng liên quan tới gián đoạn”. Chỉ gọi là nguyên nhân trực tiếp sau khi có bằng chứng từ đường đi thực, phiên firewall và phép kiểm thử khôi phục.

## 19. Bài thực hành đọc dữ liệu giả lập

Thực hành này **không yêu cầu thay đổi routing production** hoặc tạo BGP UPDATE. Người học phân tích snapshot và mô tả quyết định giám sát.

### Dữ liệu lab

~~~text
Device: edge-r1
VRF: production
Maintenance window: 10:00-10:30 (approved)

09:55:
  0.0.0.0/0       via 192.0.2.1       [static primary]
  10.20.20.0/24   via 10.0.0.2       [OSPF]
  10.30.30.0/24   via 10.0.0.4       [OSPF]

10:05:
  0.0.0.0/0       via 192.0.2.2       [static backup]
  10.20.20.0/24   via 10.0.0.3       [OSPF]
  10.30.30.0/24   via 10.0.0.4       [OSPF]

10:35:
  0.0.0.0/0       via 192.0.2.2       [static backup]
  10.20.20.0/24   via 10.0.0.3       [OSPF]
  10.30.30.0/24   via 10.0.0.4       [OSPF]
~~~

Các địa chỉ **192.0.2.0/24** dành cho ví dụ tài liệu, không phải next hop Internet thật. Dữ liệu lab chưa nói rõ đây là FIB hay RIB thực tế, và không chứng minh packet đã qua các next hop này.

### Yêu cầu phân tích

1. Những route nào thay đổi giữa 09:55 và 10:05? Thay đổi thuộc nhóm nào?
2. Route nào không thay đổi?
3. Vì sao trạng thái 10:35 đáng theo dõi dù maintenance window đã kết thúc?
4. Cần những bằng chứng nào để xác nhận chuyển default route là failover **đúng kế hoạch**?
5. Nếu tuyến tới app đổi next hop, phải kiểm tra thêm gì tại firewall và luồng chiều về?
6. Vì sao không thể kết luận một route bị tấn công chỉ từ việc đổi next hop?
7. Hãy đề xuất hai cảnh báo: một cho **critical prefix**, một cho **default route ngoài tập cho phép**.
8. Nếu chuyển đường được kỳ vọng, nên cập nhật source of truth và dashboard ra sao?

### Mẫu biên bản điều tra

~~~text
Test/Incident ID:        ROUTE-MON-01
Timestamp/timezone:      [thời gian thực]
Device/site/VRF:         [đã xác minh]
Address family:          [IPv4 / IPv6]
Prefix:                  [đích và prefix length]
Change category:         [add / withdraw / next-hop / policy / ...]
Before:                  [route data chuẩn hóa]
After:                   [route data chuẩn hóa]
Routing source:          [static / OSPF / BGP / RA / cloud...]
Expected allowed paths:  [source of truth]
Change ticket:           [ID hoặc chưa tìm thấy]
FIB status:              [confirmed / not confirmed]
Observed packet path:    [flow/capture/probe nếu có]
Impacted assets:         [app, subnet, user]
Security boundary:       [FW/VRF/VPN/IDS]
Assessment:              [EXPECTED / UNEXPECTED / UNCONFIRMED]
Recommended action:      [investigate / monitor / approved rollback]
Evidence and reviewer:   [nguồn log, owner]
Result:                  [PASS / FAIL / INCONCLUSIVE]
~~~

**INCONCLUSIVE** dùng khi không có đủ dữ liệu từ VRF/FIB/flow hoặc không xác định được change owner. Không coi ping fail là bằng chứng một route bị xóa: host firewall, DNS, ICMP policy và ứng dụng đều có thể tác động.

## 20. Đánh giá chất lượng giám sát route

| Chỉ số | Cách đo | Điều cần tránh |
|---|---|---|
| **Critical-prefix coverage** | Tỷ lệ prefix trọng yếu có dữ liệu route và owner | Không tính một thiết bị edge là đủ cho toàn bộ đường đi |
| **RIB/FIB observation coverage** | Những thiết bị/VRF có đủ dữ liệu cho mục tiêu phát hiện | Không tuyên bố có FIB nếu chỉ đọc BGP updates |
| **Time to detect** | Thời gian từ event thực đến alert | Cần đồng bộ timestamp và xét độ trễ collector |
| **Time to triage** | Thời gian phân loại đúng nguyên nhân/phạm vi | Chỉ đóng alert không có nghĩa điều tra xong |
| **Unexpected-route precision** | TP / (TP + FP) trên tập có nhãn | Ticket không đầy đủ và thay đổi HA hợp lệ dễ gây FP |
| **Alert duplication/noise** | Số alert cho một root cause | Không tạo hàng nghìn ticket khi một link down kéo theo nhiều route |
| **Change attribution** | Tỷ lệ event gắn được với peer, device, user/API/ticket | Không suy ra tác nhân từ IP router đơn thuần |
| **Service impact correlation** | Tỷ lệ route alert ghép được với flow/health/user error | Reachability không chứng minh mọi giao dịch thành công |
| **Data gaps** | Missing event, collector loss, polling gap, incomplete VRFs | Không mặc định khoảng trống dữ liệu là trạng thái ổn định |

Một chương trình giám sát tốt không nhất thiết thu **mọi** BGP UPDATE của toàn Internet để bảo vệ một số dịch vụ nội bộ. Nên chọn **thiết bị, VRF, prefix, peer và chỉ số theo rủi ro**, rồi mở rộng coverage sau khi có quy trình triage, storage và owner.

## 21. Những hiểu nhầm thường gặp

| Nhận định sai | Vì sao không đúng? | Cách làm phù hợp |
|---|---|---|
| “Route xuất hiện nghĩa là kết nối được phép” | Firewall, policy, host và app vẫn có thể chặn | Xác minh reachability và authorization riêng |
| “Có BGP UPDATE nghĩa FIB đổi” | Update có thể bị policy lọc hoặc không được chọn | So control plane, RIB và FIB |
| “BGP best path không đổi thì data path chắc chắn không đổi” | Các hop phía sau có thể hội tụ/đổi tuyến | Kết hợp flow, path telemetry và probe |
| “Mất route trong một protocol là mất mạng” | Có thể còn route thay thế từ nguồn khác | Xem selected route và FIB |
| “Prefix vẫn tồn tại nên không có sự cố” | Next hop, preference hoặc more-specific có thể đổi | Theo dõi đầy đủ thuộc tính route |
| “Route default chỉ cần giám sát 0.0.0.0/0” | IPv6 dùng ::/0 và host có nhiều table/VRF | Giám sát dual-stack, VRF, host/VPN |
| “Có RPKI Valid là cả AS_PATH an toàn” | ROV xác minh origin, không bảo vệ mọi quan hệ route | Kết hợp policy, filtering, monitoring |
| “RPKI NotFound nghĩa route độc hại” | Không có ROA phù hợp là tình trạng thường gặp | Xác minh ownership và ngữ cảnh |
| “Mọi route flap là tấn công” | Hội tụ, link lỗi và maintenance có thể hợp lệ | Tương quan baseline, neighbor, dịch vụ |
| “Chỉ cần đọc route trên router edge” | Route leak ở VRF, cloud, VPN và host vẫn có thể xảy ra | Coverage theo luồng và ranh giới |
| “Có change ticket thì an toàn” | Thay đổi được duyệt vẫn có thể triển khai sai | Kiểm chứng desired vs observed và tác động |
| “Traceroute cho thấy toàn bộ đường đi mọi phiên” | ICMP policy, ECMP, overlay và NAT làm sai lệch quan sát | Nhiều nguồn dữ liệu, không suy tuyệt đối |
| “Lỗi HTTPS sau route change thì mở Allow rộng” | Nguyên nhân có thể là đường về/state/MTU | Kiểm tra routing, FIB, firewall và app |
| “Không thấy event nghĩa route không đổi” | Collector có thể mất event hoặc bỏ thay đổi giữa polls | Dùng event cộng snapshot đối chiếu |

## 22. Câu hỏi tự kiểm tra

1. RIB, FIB, control plane và data plane khác nhau thế nào? Vì sao cần quan sát nhiều lớp?
2. Một prefix vẫn tồn tại nhưng next hop chuyển sang thiết bị khác. Detector chỉ tìm route bị xóa sẽ bỏ lỡ gì?
3. Nếu xuất hiện một route /25 dưới prefix /24 đã biết, traffic tới những địa chỉ nào có thể đổi đường?
4. BGP UPDATE, received route, accepted route và selected route có luôn giống nhau không?
5. Vì sao OSPF neighbor flapping không tự chứng minh có tấn công?
6. Khi nghi route hijack công khai, RPKI ROA/ROV có thể giúp xác minh điều gì và không thể bảo đảm điều gì?
7. Route leak giữa Guest VRF và Production VRF nguy hiểm ra sao dù firewall vẫn có rule Deny?
8. Vì sao phải giám sát cả default route **0.0.0.0/0** và **::/0** trong hệ thống dual-stack?
9. Vì sao route change trên máy laptop dùng VPN có thể là bình thường, nhưng thay đổi tương tự trên server database lại đáng điều tra?
10. Hệ thống giám sát cần những trường nào để tạo route diff đáng tin cậy với ECMP?
11. Một rule WAF/IDS không còn nhận traffic sau bảo trì mạng. Những bằng chứng nào giúp phân biệt không có traffic với traffic đổi đường?
12. Nếu đường chiều đi qua FW-A và chiều về qua FW-B, cần kiểm tra những nguồn thông tin nào trước khi sửa firewall?
13. Một route change có change ticket nhưng dịch vụ mất kết nối. Có nên tự đánh dấu EXPECTED và đóng sự cố không? Tại sao?
14. Làm sao thiết kế cảnh báo route flap không tạo hàng trăm sự kiện trùng cho một link down?
15. Tại sao snapshot 10:35 trong bài thực hành cần kiểm tra tiếp dù thay đổi bắt đầu trong maintenance window?

## 23. Ghi nhớ trọng tâm

**Route change monitoring là giám sát việc thay đổi quyết định định tuyến và khả năng chuyển tiếp, không chỉ đếm route hoặc bản tin giao thức.** Những sự kiện quan trọng gồm thay đổi next hop, default route, more-specific prefix, metric/preference, ECMP, VRF import/export, routing neighbor và policy. Cần phân biệt **BGP/OSPF control-plane events**, **RIB**, **FIB** và **đường đi thực của traffic** trước khi xác định nguyên nhân hay tác động.

Thiết kế phòng thủ hiệu quả kết hợp **source of truth, cấu hình được phê duyệt, telemetry/snapshot, route diff, BGP/OSPF/cloud audit, firewall/IDS/IPS/VPN flow logs và kiểm thử ứng dụng**. Với Internet BGP, RPKI/ROV hỗ trợ kiểm tra **origin authorization** nhưng không thay thế filtering và kiểm soát route leak. Với mạng nội bộ, phải xét **VRF, IPv4/IPv6, phân đoạn, tuyến chiều về, stateful firewall và các đường bypass**. Kết quả giám sát đáng tin khi có thể nói rõ **đã quan sát điều gì, mức độ chắc chắn, tài sản nào bị ảnh hưởng, thay đổi nào được phép và bước phục hồi nào đã được kiểm chứng**.
