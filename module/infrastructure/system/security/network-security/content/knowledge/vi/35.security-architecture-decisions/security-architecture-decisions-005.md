# Thiết kế cho high availability

**High availability (HA) – tính sẵn sàng cao** là khả năng của một hệ thống tiếp tục cung cấp chức năng thiết yếu khi một hoặc nhiều thành phần gặp sự cố, được bảo trì hoặc phải chuyển vai trò. Trong kiến trúc bảo mật mạng, mục tiêu này không chỉ là giữ kết nối: firewall, VPN, DNS, IDS/IPS, xác thực, giám sát và hệ thống quản trị phải duy trì **các chính sách bảo vệ phù hợp** trong suốt quá trình suy giảm và phục hồi.

Một hệ thống có hai firewall chưa chắc đã có HA nếu chúng cùng phụ thuộc vào một switch, một nguồn điện, một đường Internet, một tuyến xác thực hay cùng nhận một cấu hình lỗi. Tương tự, một đường dự phòng hoạt động nhưng bỏ qua inspection có thể giúp lưu lượng thông suốt trong khi làm tăng rủi ro an ninh. Vì vậy, thiết kế HA cho module **SECURITY_NETWORK_SECURITY** cần đặt **availability**, **security** và **operability** trong cùng một quyết định kiến trúc.

Bài học thuộc chương **Quyết định kiến trúc bảo mật mạng** và bàn đến lựa chọn mô hình HA, miền lỗi, đường truyền, đồng bộ trạng thái, các tầng phòng vệ, cân bằng tải, giám sát, thử nghiệm và bằng chứng chấp nhận thiết kế.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt availability, reliability, resiliency, disaster recovery và redundancy; chuyển mục tiêu kinh doanh thành SLO, RTO, RPO.
2. Nhận diện **single point of failure (SPOF)** và **common-cause failure** trên đường đi của lưu lượng, đường quản trị và các phụ thuộc bảo mật.
3. So sánh active–passive, active–active, N+1 và dự phòng đa vùng/đa khu vực theo tính trạng thái của thiết bị.
4. Thiết kế failover cho firewall, VPN, IDS/IPS, DNS, dịch vụ định danh, Wi-Fi và cloud network mà không làm lệch chính sách.
5. Lựa chọn cơ chế health check, quorum/fencing, đồng bộ cấu hình/trạng thái, định tuyến và năng lực dự phòng.
6. Lập kịch bản kiểm thử, đo tác động chuyển đổi và ghi quyết định kiến trúc dưới dạng ADR.

## 2. Tính sẵn sàng cao thực sự đo điều gì?

### 2.1. Các khái niệm cơ bản

| Khái niệm | Ý nghĩa trong mạng bảo mật | Ví dụ |
| --- | --- | --- |
| Availability | Tỷ lệ thời gian chức năng được cung cấp theo tiêu chí đo | VPN người dùng truy cập ứng dụng trong khoảng thời gian được tính |
| Reliability | Xác suất hệ thống hoạt động đúng trong một khoảng thời gian | Firewall không gặp lỗi trong suốt kỳ hoạt động |
| Resilience | Khả năng chịu lỗi, suy giảm có kiểm soát và phục hồi | Mất một ISP nhưng traffic được định tuyến qua ISP khác |
| Redundancy | Bổ sung thành phần hoặc đường dự phòng | Hai firewall, hai switch, hai nguồn điện |
| HA/failover | Cơ chế tiếp tục dịch vụ khi một thành phần mất khả năng phục vụ | Firewall dự phòng nhận vai trò xử lý lưu lượng |
| Disaster recovery (DR) | Phục hồi sau sự cố lớn vượt phạm vi HA thông thường | Chuyển dịch vụ sang khu vực khác khi cả site mất |
| RTO | Thời gian tối đa được chấp nhận để phục hồi chức năng sau gián đoạn | Khôi phục đường VPN trong vài phút theo cam kết nội bộ |
| RPO | Mức mất dữ liệu/trạng thái tối đa có thể chấp nhận khi phục hồi | Mất tối đa một số thay đổi cấu hình/log gần nhất theo chính sách |
| SLI | Chỉ số thực tế phản ánh dịch vụ | Tỷ lệ bắt tay VPN thành công, tỉ lệ truy vấn DNS đạt |
| SLO | Mục tiêu của chỉ số dịch vụ | Một tỷ lệ truy cập thành công được phê duyệt trong kỳ đo |

**RTO và RPO không thay thế nhau.** RTO đo thời gian gián đoạn có thể chịu; RPO đặc biệt quan trọng với dữ liệu cấu hình, nhật ký, khóa, policy và state cần giữ. Một mạng chuyển mạch không lưu dữ liệu ứng dụng có thể không có RPO ở nghĩa truyền thống, nhưng vẫn có yêu cầu không mất thay đổi ACL hoặc bằng chứng điều tra.

SLA thường là cam kết giữa các bên, trong khi SLO là mục tiêu kỹ thuật nội bộ hoặc mục tiêu được thống nhất để theo dõi dịch vụ. Thiết kế phải định nghĩa rõ **dịch vụ nào** được tính là sẵn sàng: truy cập một URL, kết nối TCP, xác thực VPN hay giao dịch ứng dụng hoàn chỉnh.

### 2.2. Availability và thời lượng gián đoạn

Với một phép đo đơn giản trên cùng kỳ:

~~~text
Availability = thời gian dịch vụ đạt tiêu chí / tổng thời gian đo

Downtime budget = tổng thời gian đo × (1 − mục tiêu availability)
~~~

Ví dụ cho kỳ 30 ngày (43.200 phút), *không loại trừ bảo trì khỏi mẫu số*:

| Mục tiêu | Gián đoạn tối đa quy đổi trong 30 ngày |
| --- | --- |
| 99,0% | 432 phút (7 giờ 12 phút) |
| 99,9% | 43,2 phút |
| 99,95% | 21,6 phút |
| 99,99% | 4,32 phút |

Các giá trị chỉ là ngân sách tính toán, không phải kết quả thực tế hay lời hứa một mô hình HA sẽ đạt. Cách tính phụ thuộc cửa sổ đo, cách nhận diện gián đoạn và các trường hợp ngoại lệ trong SLO/SLA.

Một ước lượng cổ điển cho hệ thống có chu kỳ sửa chữa ổn định là:

~~~text
Availability ≈ MTBF / (MTBF + MTTR)
~~~

MTBF là thời gian trung bình giữa các lần hỏng, MTTR là thời gian trung bình phục hồi/sửa chữa. Công thức không mô tả hết các lỗi phụ thuộc, lỗi phần mềm đồng loạt, bảo trì có rủi ro, đứt kết nối giữa các site hoặc việc chuyển vai trò làm mất session; đừng dùng nó làm bằng chứng đủ cho thiết kế nhiều lớp.

### 2.3. Đo trải nghiệm thay vì chỉ kiểm tra thiết bị sống

Một firewall trả lời ping không có nghĩa ứng dụng đang được bảo vệ có thể hoạt động. Tương tự, trạng thái cluster là healthy không có nghĩa VPN xác thực thành công. Mỗi chức năng quan trọng nên có **SLI theo đường người dùng thực tế**, ví dụ:

- VPN: tỷ lệ thiết lập kết nối thành công, thời gian xác thực, số session bị rơi khi failover.
- DNS: truy vấn có đáp án hợp lệ, thời gian phản hồi, khả năng phân giải từ các vùng truy cập.
- Firewall: khả năng thiết lập phiên mới, duy trì phiên quan trọng, tỷ lệ policy deny/allow chính xác.
- Wi-Fi: client vẫn kết nối hoặc có thể roaming, xác thực 802.1X/RADIUS hoạt động.
- IDS/IPS: lưu lượng vẫn được xử lý **và** khả năng kiểm tra/phát hiện tiếp tục hoạt động theo chính sách.
- Cloud: truy cập dịch vụ từ các zone/VPC và khả năng egress không bị gián đoạn.

## 3. Bắt đầu từ yêu cầu kinh doanh và ranh giới tin cậy

Không nên chọn ngay hai thiết bị và giao thức heartbeat. Trước tiên hãy mô tả **hành trình của dịch vụ**:

1. Người dùng hoặc workload ở vùng nguồn nào? Kết nối qua LAN, WAN, VPN, Wi-Fi hay Internet?
2. Điểm bắt đầu và điểm kết thúc của luồng tin cậy là gì? Qua những firewall, proxy, DNS, hệ thống xác thực và inspection nào?
3. Luồng nào bắt buộc phải được cho phép, luồng nào phải từ chối ngay cả khi có sự cố?
4. Mức gián đoạn nào tổ chức chịu được? Session đã thiết lập có cần sống qua failover hay chỉ cần tạo lại nhanh?
5. Có yêu cầu tuân thủ, ghi log, phân loại dữ liệu, lưu trữ tại khu vực địa lý hoặc điều kiện mật mã nào?
6. Chi phí, kỹ năng vận hành, bản quyền, nhà cung cấp và khả năng kiểm thử định kỳ bị giới hạn ra sao?

Một **security invariant** là thuộc tính bảo mật không được thay đổi bởi thao tác failover. Ví dụ:

- Mạng khách không thể kết nối trực tiếp tới VLAN quản trị.
- Giao diện quản trị firewall chỉ truy cập qua VPN/bastion được xác thực.
- Traffic từ vùng người dùng tới vùng dữ liệu nhạy cảm luôn đi qua lớp kiểm soát bắt buộc.
- Log quan trọng không bị vô hiệu hóa chỉ vì một collector đang bảo trì.
- Đường dự phòng không tự động nới ACL hoặc tạo NAT quá rộng.

Ghi các invariant thành tiêu chí kiểm thử âm/dương trước khi chọn kiến trúc.

## 4. Phân tích single point of failure và common-cause failure

**SPOF** là thành phần mà khi hỏng sẽ làm mất chức năng quan trọng. **Common-cause failure** xảy ra khi nhiều bản sao bị ảnh hưởng bởi cùng nguyên nhân, dù từng bản sao đều lành mạnh trước đó.

| Lớp | SPOF hoặc nguyên nhân chung dễ bỏ sót | Hướng xử lý |
| --- | --- | --- |
| Điện và vật lý | Hai firewall cùng PDU, rack, phòng máy, đường cáp | Độc lập nguồn, tuyến cáp, rack/vùng khi có yêu cầu |
| Kết nối | Hai firewall nối chung một switch hoặc cùng ISP last-mile | Dual-switch, dual-uplink và đánh giá tính độc lập nhà mạng |
| Điều khiển | Một bộ điều phối cấu hình hoặc certificate service | Cơ chế dự phòng, cache/giới hạn phụ thuộc và recovery |
| Danh tính | VPN chỉ dùng một RADIUS/IdP hoặc một DNS resolver | Dịch vụ xác thực/DNS nhiều endpoint và đường truy cập |
| Phần mềm | Hai node chạy cùng bản lỗi hoặc nhận cùng cấu hình sai | Staged rollout, backup cấu hình, rollback được hỗ trợ |
| Data plane | Dự phòng thiết bị nhưng route trả về vẫn qua node lỗi | Kiểm tra định tuyến hai chiều và tính đối xứng phiên |
| Cluster | Heartbeat chạy chung link với traffic, không có xử lý split-brain | Liên kết độc lập, health/quorum/fencing theo nền tảng |
| Giám sát | Cùng mất collector và hệ thống cảnh báo | Giám sát độc lập, nhiều điểm quan sát, cảnh báo mất telemetry |
| Cloud | Hai instance cùng availability zone hoặc một quota/NAT gateway | Phân tán AZ, kiểm tra quota và các dependency zone-level |

**Hai bản sao giống hệt không loại trừ lỗi chung.** Các yếu tố có quan hệ phụ thuộc phải được thể hiện trong sơ đồ. Dự phòng đa AZ cũng không bảo đảm chống lỗi toàn region; dự phòng đa region lại tăng độ phức tạp vận hành, định tuyến, phân quyền và đồng bộ dữ liệu.

Đánh giá từng failure domain: interface, NIC, máy chủ, switch, rack, power domain, AZ, site, ISP, DNS, IdP, control plane và quyền quản trị. Không nhất thiết phải nhân đôi tất cả: chọn mức phân tán tương xứng mức mất mát kinh doanh và yêu cầu bảo mật.

## 5. Lựa chọn mô hình HA

### 5.1. Active–passive (A/P)

Một thiết bị xử lý traffic, thiết bị còn lại chờ nhận vai trò khi có điều kiện failover.

**Phù hợp:** cặp firewall stateful, gateway VPN, thiết bị mạng có cơ chế HA và state sync do hãng hỗ trợ, nơi ưu tiên đường đi dễ dự đoán.

**Ưu điểm:** quản lý session và định tuyến thường đơn giản hơn active–active; ít đường bất đối xứng hơn. **Đánh đổi:** thiết bị dự phòng thường ít khai thác công suất, failover vẫn có thể tạo gián đoạn, đồng bộ state/chính sách cần chính xác.

### 5.2. Active–active (A/A)

Nhiều node cùng xử lý lưu lượng. Có thể dùng load balancer, ECMP, routing hoặc cơ chế cluster phân phối flow.

**Phù hợp:** dịch vụ stateless, proxy có kiến trúc scale-out, một số nền tảng firewall/inspection hỗ trợ cluster A/A đúng nghĩa.

**Ưu điểm:** phân phối tải và sử dụng nhiều node, có thể giảm ảnh hưởng khi mất một node. **Đánh đổi:** route bất đối xứng, đồng bộ session, phân phối state, kết nối kéo dài và tải tăng đột ngột khi mất node khó xử lý hơn.

**Không suy từ “nhiều instance đang chạy” thành HA active–active an toàn.** Cần kiểm tra nền tảng có hỗ trợ stateful load sharing, session persistence, flow symmetry và policy nhất quán hay không.

### 5.3. N+1 và đa vùng/đa site

- **N+1:** có ít nhất một đơn vị năng lực dự phòng đủ tiếp quản khi một thành phần bất kỳ trong phạm vi thiết kế hỏng.
- **N+2:** tăng số dự phòng hoặc chịu nhiều sự cố hơn, nhưng chỉ đạt khi failure domains đủ độc lập và control plane không thành điểm đơn.
- **Multi-AZ:** phân tán instance/đường mạng qua vùng sẵn sàng; kiểm tra những dịch vụ cloud thực sự có phạm vi AZ hay region.
- **Multi-site/multi-region:** hướng đến chịu lỗi cấp địa điểm; phải giải quyết dữ liệu, DNS/routing, split-brain và ưu tiên vùng, chi phí cao hơn.

| Tiêu chí | Active–passive | Active–active | Multi-site |
| --- | --- | --- | --- |
| Duy trì session | Phụ thuộc state sync và hỗ trợ của hãng | Phụ thuộc flow ownership/symmetry, persistence | Thường khó giữ session xuyên site |
| Công suất thiết bị dự phòng | Có công suất chờ | Chia tải nhưng phải chừa headroom | Dự phòng theo năng lực site |
| Phức tạp vận hành | Trung bình | Cao hơn với dịch vụ stateful | Cao về routing, consistency và DR |
| Chịu lỗi chủ yếu | Node/link trong một failure domain | Node và tải phân tán | Sự cố site hoặc vùng lớn |
| Rủi ro nổi bật | Split-brain, failover chậm | Asymmetric routing, state divergence | Phụ thuộc chung, độ trễ, dữ liệu/khóa |
| Điều kiện quyết định | Cần session state ổn định | Nền tảng hỗ trợ phân tải thực tế | Mục tiêu dịch vụ yêu cầu chịu lỗi địa điểm |

## 6. Kiến trúc HA mẫu cho mạng doanh nghiệp

Một sơ đồ logic minh họa các miền chức năng:

~~~mermaid
flowchart TB
    U["Người dùng / chi nhánh / VPN"]
    I1["ISP-A"]
    I2["ISP-B"]
    ER1["Edge router A"]
    ER2["Edge router B"]
    FW1["Firewall A"]
    FW2["Firewall B"]
    SW1["Core switch A"]
    SW2["Core switch B"]
    APPS["Application & identity services"]
    OOB["OOB / management network"]
    SIEM["Log & monitoring"]

    U --> I1
    U --> I2
    I1 --> ER1
    I2 --> ER2
    ER1 --> FW1
    ER1 --> FW2
    ER2 --> FW1
    ER2 --> FW2
    FW1 <-->|"Health / config / state, liên kết bảo vệ"| FW2
    FW1 --> SW1
    FW1 --> SW2
    FW2 --> SW1
    FW2 --> SW2
    SW1 --> APPS
    SW2 --> APPS
    OOB -.-> FW1
    OOB -.-> FW2
    FW1 -.-> SIEM
    FW2 -.-> SIEM
~~~

Sơ đồ là **logic**, không khẳng định mọi tổ hợp cổng/cáp hoặc sản phẩm đều hỗ trợ topology này. Thiết kế triển khai cần xác nhận đường vật lý, định tuyến WAN/LAN, IP/VLAN, cách nối HA, MLAG/stack và các giới hạn của nhà sản xuất.

Các câu hỏi phải được giải đáp trong bản vẽ chi tiết:

- Có hai tuyến vật lý thực sự độc lập tới các ISP, hay hai hợp đồng dùng chung một tuyến cáp vào tòa nhà?
- Mỗi firewall có thể đi tới cả hai upstream và downstream không? Một switch hỏng có cắt cả cặp firewall không?
- Gateway logic dùng virtual IP/VRRP, cluster-specific virtual MAC, dynamic routing hay load balancer? Điều gì xảy ra với bảng ARP/ND?
- Nút đang xử lý session có nhìn thấy **cả hai chiều** lưu lượng sau khi chuyển node/route?
- Đường quản trị ngoài băng có hoạt động khi data plane hỏng? Nó có được bảo vệ độc lập và có log không?
- Nếu hệ thống xác thực và DNS nội bộ mất, VPN mới có thể đăng nhập và phân giải dịch vụ tối thiểu không?
- Các rule deny và mandatory inspection có còn hiệu lực ở mọi nhánh dự phòng không?

## 7. Thiết kế HA cho firewall stateful

### 7.1. Đồng bộ loại trạng thái nào?

Không nên đồng nhất việc **đồng bộ cấu hình** với **đồng bộ phiên**:

| Loại trạng thái | Nội dung ví dụ | Tác động khi thiếu |
| --- | --- | --- |
| Cấu hình/policy | ACL, object, NAT, zone, certificate profile | Nút mới áp rule khác hoặc thiếu đường truy cập |
| Session/connection state | TCP connection, UDP flow, timeout, session owner | Session hiện tại có thể bị rơi dù truy cập mới hoạt động |
| NAT mapping | Địa chỉ/cổng dịch và thời hạn | Gói trả về không khớp ánh xạ cũ |
| VPN/IKE/IPsec | Security association, khóa và tham số phiên tùy hãng | Tunnel phải thương lượng lại; gián đoạn |
| ARP/ND và route | Neighbor cache, virtual IP/MAC, FIB | Mất thời gian hội tụ hoặc gửi sai next-hop |
| Log/audit | Sự kiện từ hai node và thời gian | Khoảng trống điều tra trong quá trình failover |

Việc các trạng thái được sao chép đến đâu **phụ thuộc sản phẩm, phiên bản firmware và chế độ HA**. Không ghi trong thiết kế rằng “mọi session đều sống qua failover” khi hãng chỉ hỗ trợ đồng bộ một phần hoặc không hỗ trợ một số giao thức.

### 7.2. Các thành phần triển khai

- Cấu hình chính sách có nguồn chuẩn; kiểm soát thay đổi và kiểm tra hash/version policy giữa hai node.
- Dedicated HA/heartbeat và state synchronization link theo hướng dẫn hãng, có giới hạn truy cập và bảo vệ dữ liệu đồng bộ.
- Health monitor bao gồm interface, next hop, upstream/downstream reachability, process và critical service; không chỉ trạng thái nguồn điện của thiết bị.
- Chuyển virtual IP/MAC hoặc cập nhật định tuyến có kiểm soát để traffic đi tới node mới; kiểm tra ARP/ND và time convergence.
- Hành vi failback được chọn rõ: thủ công hoặc tự động có hold-down/preemption policy để tránh flapping.
- Giám sát sức khỏe state-sync: độ trễ, dropped updates, checksum/policy mismatch, CPU/memory và thiết bị trong cluster.

### 7.3. Đường đi đối xứng (symmetry)

Một firewall stateful cần đủ ngữ cảnh của flow để cho phép gói tin qua. Khi ECMP hoặc hai nhánh song song làm gói đi qua node A nhưng gói về qua node B, session có thể bị từ chối.

Các chiến lược hợp lệ tùy sản phẩm:

1. Pin/steer hai chiều của một flow về cùng firewall.
2. Dùng mô hình cluster có state-sharing được hãng hỗ trợ và kiểm thử tình huống bất đối xứng.
3. Điều chỉnh định tuyến, source NAT hoặc load balancer để tránh flow bị tách.
4. Kiểm tra các trường hợp routing failover, NAT, IPsec tunnel và luồng east–west.

**Không tắt stateful inspection chỉ để làm traffic đi qua.** Một kết nối bị drop sau failover có thể là bằng chứng state sync hoặc routing chưa đúng; giải quyết bằng thiết kế flow thay vì bỏ kiểm soát.

## 8. Heartbeat, split-brain, quorum và fencing

### 8.1. Vì sao hai nút cùng “active” là nguy hiểm?

Khi đường heartbeat đứt nhưng hai firewall vẫn hoạt động, mỗi node có thể nghĩ node còn lại đã chết và tự nhận quyền xử lý traffic. Tình huống **split-brain** có thể gây:

- Hai gateway phát cùng virtual IP/MAC; ARP/ND thay đổi liên tục.
- Trạng thái NAT/session không nhất quán; traffic mất ngẫu nhiên.
- Chính sách khác nhau giữa hai node; một số đường bypass kiểm soát.
- Log và sự kiện điều khiển khó đối chiếu.

Heartbeat loss **không nhất thiết đồng nghĩa peer đã chết**. Phải xem cơ chế mà nhà sản xuất hỗ trợ: nhiều kênh heartbeat, tie-breaker, node priority, witness/quorum hoặc cơ chế fencing/STONITH khi thích hợp. Quorum một mình không giải quyết mọi lỗi mạng; thiết kế cần bảo đảm node không đủ quyền sẽ **không tiếp tục chiếm tài nguyên dùng chung**.

### 8.2. Lựa chọn và thử nghiệm

Một số appliance HA 2-node có logic riêng để xử lý split-brain và không hỗ trợ witness. Không áp một mô hình cluster chung lên sản phẩm không hỗ trợ. Xác minh hướng dẫn hãng cho phiên bản thực tế và thử ít nhất:

- Mất một đường heartbeat, nhưng data path vẫn tốt.
- Mất toàn bộ heartbeat trong khi cả hai node còn nguồn.
- Peer không còn trả lời nhưng virtual IP vẫn xuất hiện.
- Nút vừa khởi động lại khi nút còn lại đang active.
- Link trở lại sau thời gian chia tách: ai giữ vai trò, cấu hình/state nào được ưu tiên?

Đặt **hold-down, hysteresis và failback policy** hợp lý để tránh chuyển vai trò liên tiếp khi mạng chập chờn. Tự động failback ngay khi node cũ hồi phục có thể tạo thêm gián đoạn không cần thiết.

## 9. HA cho VPN và truy cập từ xa

VPN thường phụ thuộc vào nhiều hơn hai cổng tunnel:

| Thành phần | Yêu cầu HA | Lỗi hay gặp |
| --- | --- | --- |
| Gateway VPN | Có endpoint dự phòng và chính sách session phù hợp | Endpoint mới lên nhưng tunnel chưa thương lượng lại |
| Identity provider/RADIUS | Nhiều endpoint khả dụng, timeout/fallback được định nghĩa | Không ai đăng nhập mới khi node xác thực chính lỗi |
| DNS | Resolver dự phòng và khả năng cập nhật endpoint | Client còn dùng địa chỉ gateway cũ |
| Route và split/full tunnel | Đường tới ứng dụng được công bố đúng sau failover | VPN connected nhưng không truy cập app |
| Certificate/PKI | Chứng chỉ, trust chain, khóa và vòng đời được quản trị | Endpoint dự phòng thiếu cert hoặc sai tên |
| Policy người dùng/thiết bị | MFA, posture và authorization tương đương | Đường dự phòng nới kiểm soát danh tính |

Đối với site-to-site IPsec, cần kiểm tra thời gian IKE/IPsec renegotiation, thay đổi outer IP, DPD, khả năng giữ tunnel song song và route preference. Với remote-access VPN, đo **thời gian người dùng truy cập lại ứng dụng**, không chỉ thời gian tunnel hiển thị là up.

Sử dụng BGP/BFD hoặc cơ chế định tuyến mà nền tảng hỗ trợ có thể rút ngắn phát hiện/hội tụ, nhưng tuning quá gắt dễ gây flap. Kiểm thử tải, jitter, packet loss và behavior của client trước khi chọn timer. Trong giải pháp SaaS/ZTNA, xác định failure domain của nhà cung cấp và đường truy cập khi IdP bị gián đoạn.

## 10. HA cho DNS, DHCP, PKI và định danh

Dịch vụ bảo mật mạng có thể ngừng hoạt động dù firewall còn khỏe nếu những phụ thuộc sau không sẵn sàng.

### DNS

- Cấp ít nhất các resolver đáp ứng cùng chính sách DNS filtering, forwarder và zone.
- Kiểm tra phân giải từ **nhiều mạng nguồn**, gồm guest, VPN, ứng dụng và quản trị.
- Với authoritative DNS, cân nhắc đa nhà cung cấp, nhiều vùng và khả năng cập nhật bản ghi khi failover.
- DNS TTL giúp giới hạn tuổi thọ cache trong điều kiện bình thường, nhưng không bảo đảm mọi client đổi endpoint đúng tại TTL; còn có resolver caching, negative caching và connection reuse.
- Nếu dùng anycast hoặc health-based DNS, kiểm tra có cùng chính sách và tác động của route convergence, health assessment và khả năng định tuyến sai.

### DHCP

- Split scope, failover hoặc DHCP cluster theo hệ thống thực tế, tránh cấp trùng IP.
- Kiểm tra trạng thái lease, relay agent ở các VLAN, thời hạn gia hạn và các option cho DNS/NTP.
- Không coi một server DHCP dự phòng là đầy đủ khi relay/router đầu mạng vẫn là SPOF.

### PKI, AAA, IdP và secrets

- Nhiều node/dịch vụ cho RADIUS/TACACS+, LDAP/IdP, cấp phát chứng chỉ, KMS hoặc secret manager theo mức độ quan trọng.
- Kiểm soát khóa riêng, khả năng thu hồi, certificate expiration và phân quyền khi failover; HA không đồng nghĩa sao chép khóa vô điều kiện.
- Quy định **hành vi khi dịch vụ định danh mất**: cho phép session còn hiệu lực, giới hạn truy cập khẩn cấp qua break-glass có kiểm soát hay dừng xác thực mới; không tự động bỏ qua MFA.
- Có cơ chế quản trị khẩn cấp được kiểm soát để đội vận hành xử lý sự cố mà không phụ thuộc hoàn toàn vào dịch vụ đang bị hỏng.

## 11. HA cho IDS/IPS, WAF và các lớp inspection

Thiết bị **inline IPS** nằm trên đường truyền; lỗi của nó có thể đồng thời gây mất availability và thay đổi khả năng bảo vệ. Thiết bị **IDS out-of-band** thường không nằm trên data path nhưng có thể mất visibility.

### 11.1. Fail-open và fail-closed

| Chính sách lỗi | Hành vi khi lớp inspection bị lỗi | Lợi ích | Rủi ro cần chấp nhận |
| --- | --- | --- | --- |
| Fail-closed | Chặn luồng khi không thể kiểm tra theo yêu cầu | Giữ invariant về inspection/segmentation | Có thể gián đoạn ứng dụng |
| Fail-open / bypass | Cho lưu lượng tiếp tục dù mất inspection | Giảm nguy cơ gián đoạn dịch vụ | Traffic đi qua mà không được kiểm tra, tăng rủi ro xâm nhập |
| Chuyển sang node inspection dự phòng | Giữ inspection bằng node khác | Cân bằng bảo mật và liên tục dịch vụ | Phức tạp về capacity, session, route và đồng bộ |

Không có lựa chọn phổ quát. Luồng dữ liệu nhạy cảm hoặc biên bắt buộc inspection có thể yêu cầu fail-closed; một số môi trường công nghiệp ưu tiên tính liên tục ở mức khác. Quyết định phải được **phê duyệt dựa trên phân tích rủi ro**, có giám sát rõ khi mất inspection và có biện pháp giảm thiểu. Không được tự bật bypass để “đạt SLO” mà không thay đổi quyết định kiến trúc.

### 11.2. Những điểm cần kiểm tra

- Bypass phần cứng, heartbeat và cơ chế khôi phục của inline appliance theo đúng đặc tính hãng.
- IPS/WAF policy parity: cùng phiên bản rule, whitelist, certificate, signature feed và exception đã duyệt.
- Công suất xử lý dưới tải cao, khi TLS inspection bật, log tăng hoặc chỉ còn một node.
- Gương traffic/TAP/SPAN của IDS: một switch mirror hỏng hoặc SPAN oversubscription có thể tạo **khoảng trống phát hiện** dù ứng dụng vẫn hoạt động.
- Trạng thái bản cập nhật chữ ký, quy trình phát hành từng đợt và khả năng rollback rule khi false positive.

## 12. HA cho Wi-Fi và phân đoạn mạng

Mạng không dây doanh nghiệp có thể có nhiều AP nhưng vẫn phụ thuộc controller, RADIUS, DHCP và DNS.

- Phủ sóng AP có chồng lấn phù hợp để mất một AP không tạo vùng mất tín hiệu quan trọng.
- Có phương án dự phòng controller hoặc cloud management theo khả năng sản phẩm; kiểm tra AP có tiếp tục chuyển tiếp traffic nếu controller tạm mất không.
- Kiểm tra roaming, 802.1X/RADIUS, VLAN assignment và chính sách truy cập khách khi failover.
- Với controller active–standby, xác minh thời gian AP rejoin, client reconnect và độ ổn định roaming.
- Kiểm tra ACL/segmentation ở các đường dự phòng để mạng khách không được chuyển nhầm vào mạng nội bộ.
- Trong site có hai switch, điểm đấu nối AP có thể vẫn là một uplink hoặc một PoE switch; cân nhắc failure domain điện, cáp và đường LAN.

Lưu ý: việc control plane Wi-Fi gián đoạn không luôn có nghĩa data plane bị gián đoạn ngay. Hành vi phụ thuộc sản phẩm, chế độ forwarding và trạng thái client hiện tại.

## 13. HA trên cloud và kiến trúc hybrid

Cloud cung cấp nhiều dịch vụ managed nhưng **không tự động mang HA cho kiến trúc ứng dụng hoặc security chain**. Cần xác định phạm vi và giới hạn từng dịch vụ: zone-level, regional, global, endpoint-specific.

| Thành phần | Ví dụ quyết định HA cần kiểm chứng |
| --- | --- |
| Virtual firewall/NVA | Nhiều instance ở AZ khác nhau, route propagation và khả năng giữ đối xứng traffic |
| Cloud load balancer | Health check end-to-end, zone coverage, target draining và policy TLS/WAF |
| NAT/egress | Endpoint/NAT gateway cho từng AZ hoặc topology được nhà cung cấp hỗ trợ; tránh route mọi AZ qua một egress SPOF |
| Private connectivity | Kết nối Direct Connect/ExpressRoute hoặc tương đương với tuyến/địa điểm độc lập, VPN dự phòng |
| DNS và service discovery | Resolver/zone dự phòng, endpoint health và behavior của cache |
| IAM/KMS/secrets | Availability theo region, quyền truy cập dự phòng và giới hạn sao chép khóa |
| Logging và SIEM | Nhiều đường ingest, buffer có giới hạn, phát hiện mất log |
| Region failover | Routing/DNS, dữ liệu, certificates, policy parity, egress IP và khu vực lưu dữ liệu |

Ở multi-region, các yêu cầu **data residency**, khóa mã hóa, định tuyến, độ trễ và chi phí sao chép có thể quyết định thiết kế. Active–active giữa hai region yêu cầu ứng dụng và hệ thống dữ liệu xử lý nhất quán; HA của firewall không tự giải quyết phân tán dữ liệu hay conflict.

**Hybrid VPN/SD-WAN** cần thử các tình huống một site, ISP hoặc private link mất: route có chuyển đúng không, có loop, có tunnel đi qua vùng không được duyệt, DNS/IdP có khả dụng từ đường phụ và có mất visibility không?

## 14. Capacity planning và mô hình N+1

Dự phòng chỉ có ích khi tài nguyên còn lại **đủ sức phục vụ** sau sự cố. Một cặp firewall chạy ở mức 75% mỗi node khi bình thường có thể vượt tải khi một node chịu toàn bộ traffic, dù cả hai đều healthy trước khi lỗi.

Ví dụ giả định:

~~~text
Lưu lượng giờ cao điểm đã đo: 6 Gbps
Yêu cầu headroom sau khi mất 1 node: 25% so với mức tải
Throughput hữu dụng tối thiểu cho node còn lại = 6 / (1 − 0,25) = 8 Gbps
~~~

Đây là mô hình đơn giản cho throughput. Còn phải kiểm tra:

- **Concurrent connections**, new connections/second, session setup rate.
- Số lượng tunnel VPN, throughput IPsec, mức sử dụng CPU khi mã hóa.
- TLS inspection, IPS signatures, logging/telemetry và các tính năng bảo mật đồng thời.
- Kích thước packet, tỷ lệ packet/s, traffic burst, east–west và asymmetric traffic.
- NIC, uplink, switch fabric, đường backplane và service quotas.
- Thời gian warm-up/cold-start của node mới hoặc instance cloud.

Thông số throughput quảng cáo của nhà sản xuất có thể được đo trong cấu hình không giống traffic thực tế. Thiết kế cần dùng **effective capacity** sau khi bật đầy đủ chức năng bảo mật, lấy từ tài liệu đo phù hợp và kiểm thử trên profile tải gần thực tế.

### Công suất dự phòng và mục tiêu lỗi

Với N node active chia đều, phải bảo đảm sau khi mất một node:

~~~text
Tổng năng lực hữu dụng của (N − 1) node
    >= tải đỉnh dự kiến + headroom đã thống nhất
~~~

Điều kiện này giả định các node có năng lực tương đương và tải phân phối lại được. Cần hiệu chỉnh theo bottleneck thực, mất vùng, session affinity, khả năng chuyển route và tăng tải do retry sau failover. N+1 theo **số node** không đảm bảo N+1 theo **throughput**.

## 15. Health check và phát hiện sự cố

Health check tốt phải phản ánh chức năng cần giữ sống, kết hợp **liveness**, **readiness** và quan sát end-to-end:

| Lớp kiểm tra | Ví dụ | Giới hạn |
| --- | --- | --- |
| Liveness | Node có nguồn, tiến trình đang chạy | Có thể vẫn không forward traffic |
| Interface/link | NIC/uplink up, mất link vật lý | Upstream phía xa vẫn có thể lỗi |
| Reachability | Ping next hop, BFD/session routing | Chưa chắc ứng dụng hoặc DNS hoạt động |
| Data plane | Kết nối qua firewall/proxy tới ứng dụng thử nghiệm | Cần giới hạn và kiểm soát tránh health-check gây tải |
| Security correctness | Luồng hợp lệ được phép, luồng cấm bị chặn | Cần cả phép thử dương và âm |
| User experience | DNS/VPN/login/transaction từ nhiều vùng | Phụ thuộc hệ thống phụ trợ, cần phân biệt nguyên nhân |

**False positive** có thể làm chuyển vai trò khi hệ thống vẫn khỏe; **false negative** có thể giữ traffic trên node hỏng. Thiết lập số lần thử, timeout, hysteresis và ưu tiên cảnh báo dựa trên đo thực tế, không chỉ một timer mặc định.

Không dùng một endpoint health check duy nhất để đại diện cho mọi tuyến, zone hay dịch vụ. Cũng tránh để hệ thống kiểm tra và hệ thống được kiểm tra phụ thuộc vào cùng một nguồn điện hoặc mạng điều khiển.

## 16. Tính toán chuỗi phụ thuộc và rủi ro lỗi chung

Một đường phục vụ có nhiều thành phần mắc **nối tiếp**: DNS, IdP, VPN, firewall, route, ứng dụng. Nếu một mắt xích không sẵn sàng và không có đường thay thế, dịch vụ end-to-end sẽ thất bại.

Với giả định độc lập và cùng khoảng thời gian, có thể minh họa:

~~~text
Availability_path ≈ A_DNS × A_VPN × A_Firewall × A_App
~~~

Nếu bốn thành phần nối tiếp đều có availability 99,9% thì ước lượng đường tổng thể:

~~~text
0,999 ^ 4 ≈ 0,996006 ≈ 99,60%
~~~

Con số minh họa chỉ đúng khi giả định độc lập và định nghĩa availability phù hợp; trong thực tế sự cố tương quan và khả năng degrade khiến mô hình phức tạp hơn.

Đối với hai thành phần **dự phòng độc lập** mà chỉ một hoạt động cũng đủ phục vụ, ước lượng lý tưởng là:

~~~text
Availability_parallel ≈ 1 − (1 − A1) × (1 − A2)
~~~

Tuy nhiên, không được nhân/cộng công thức rồi kết luận đáp ứng SLO nếu hai node chung nguồn, cùng software bug hoặc phụ thuộc một mạng heartbeat. **Common-cause failure** làm lợi ích redundancy giảm mạnh.

## 17. Chuyển vai trò, hội tụ định tuyến và session continuity

Một chuỗi failover thường gồm:

~~~text
Sự cố xuất hiện
    ↓
Phát hiện đủ điều kiện failover
    ↓
Chọn node/đường tiếp quản hợp lệ
    ↓
Chuyển địa chỉ/route/tunnel hoặc phân phối flow
    ↓
Khởi tạo hoặc phục hồi state cần thiết
    ↓
Kiểm tra policy và ứng dụng end-to-end
    ↓
Xác nhận service restored, cảnh báo và audit
~~~

**Thời gian gián đoạn quan sát được** có thể bao gồm thời gian phát hiện + bầu chọn + hội tụ routing/ARP/ND + tái thiết lập tunnel/session + retry ứng dụng. Các bước có thể chồng lấn; công thức cộng chỉ để nhận diện thành phần đóng góp.

Khi thiết kế và nghiệm thu, phân biệt:

- **Cold session:** người dùng mở kết nối mới sau failover.
- **Warm/existing session:** TCP, UDP, TLS và VPN session đang chạy có sống qua failover không?
- **Long-lived flows:** cuộc gọi, phiên giao dịch, truyền tệp, streaming hoặc replication.
- **Stateful NAT:** địa chỉ/cổng dịch có được giữ nguyên hoặc ánh xạ lại đúng?
- **Route symmetry:** cả chiều request và response có qua đúng node xử lý state không?
- **Stability:** sau khi node cũ hồi phục có xảy ra failback/flapping không?

Bộ kiểm thử chỉ ping gateway có thể bỏ qua mất TCP session, lỗi NAT, mất VPN và sự lệch kiểm soát bảo mật.

## 18. Giám sát HA và quản trị sự cố

HA không chỉ là thiết kế vật lý; phải có **bằng chứng vận hành**.

Các chỉ số nên theo dõi:

- Cluster role, peer state, interface health, link heartbeat/state-sync.
- Số lần failover/failback, nguyên nhân, thời lượng phát hiện và thời gian hồi phục.
- Tỉ lệ thành công của truy cập ứng dụng, DNS, VPN, Wi-Fi sau chuyển vai trò.
- Throughput, CPU/memory, session table, connection creation rate và tunnel count trên node còn lại.
- Sự khác biệt policy/config/cert/signature trên các node.
- Loss/latency/jitter, packet drops, routing changes và trạng thái ISP/cloud service.
- Tỉ lệ mất log, hàng đợi gửi log, độ trễ SIEM, các alert IDS/IPS/WAF.
- Sự kiện liên quan tới split-brain, flapping, fail-open/bypass và thay đổi control plane.

Cần theo dõi từ **ít nhất hai góc nhìn phù hợp**: health của thiết bị và probe end-to-end từ một vùng người dùng/ứng dụng. Alert phải phân biệt “đã chuyển dự phòng thành công” với “mất khả năng dự phòng”: khi chỉ còn một node, dịch vụ còn chạy nhưng mức rủi ro đã tăng và cần khôi phục redundancy.

Chuẩn hóa thời gian (NTP), lưu cấu hình thay đổi, giữ bản ghi trước/sau failover và đảm bảo log không bị mất đồng loạt với thiết bị đang lỗi.

## 19. Quy trình bảo trì và cập nhật không gây lỗi đồng loạt

Một cluster HA có thể vẫn bị outage do thao tác bảo trì sai trình tự. Quy trình khuyến nghị, tùy tính năng hãng:

1. Kiểm tra cluster khỏe, cấu hình đồng bộ, state-sync và headroom đủ để một node tiếp quản.
2. Backup cấu hình, firmware/image và xác minh phương án quay lại theo hỗ trợ của nhà cung cấp.
3. Xem compatibility matrix: phiên bản cho phép chạy lệch tạm thời, migration schema, bootloader, certificate, IPS signatures.
4. Chuyển tải hoặc đặt node đầu tiên vào maintenance mode theo runbook được phê duyệt; theo dõi dịch vụ end-to-end.
5. Cập nhật node thứ nhất, xác minh health, policy và lưu lượng; không cập nhật cả hai node đồng thời nếu yêu cầu HA liên tục.
6. Chuyển vai trò nếu quy trình yêu cầu; cập nhật node còn lại; xác minh session và việc quay lại trạng thái redundancy.
7. Kiểm tra sau triển khai: phép thử allow/deny, DNS/VPN/inspection, logging, performance và alert.
8. Đóng thay đổi khi đạt tiêu chí và giữ giám sát trong cửa sổ đã định.

**Rolling upgrade chỉ có thể áp dụng nếu nền tảng thực sự hỗ trợ phối hợp phiên bản tạm thời.** Với bản nâng cấp có thay đổi schema không tương thích, có thể cần maintenance window và phương án DR rõ ràng. Không ép failover bằng cách rút dây hoặc tắt nguồn trước khi xác nhận an toàn vận hành và phạm vi thử nghiệm.

## 20. Ma trận kiểm thử HA và security invariant

Xây dựng bài kiểm thử dựa trên **failure injection được phê duyệt** hoặc mô phỏng qua lab/staging trước khi áp dụng sản xuất. Mỗi kịch bản cần có phép đo **tính liên tục** và **chính sách bảo mật**.

| Kịch bản | Mong đợi availability | Mong đợi security | Bằng chứng |
| --- | --- | --- | --- |
| Mất node firewall active | Node dự phòng phục vụ trong RTO | ACL/NAT/inspection không đổi sai | Event HA, flow test, rule hit, log |
| Mất một upstream ISP | Route chuyển sang đường hợp lệ | Không bypass firewall hay tạo mở quản trị Internet | BGP/route history, traceroute phù hợp, allow/deny |
| Mất một core switch | Luồng qua đường còn lại | Phân đoạn VLAN/zone không suy giảm | Interface/MLAG logs, test ứng dụng và deny |
| Mất liên kết heartbeat | Cluster xử lý an toàn theo hãng | Không split-brain và không cùng chiếm VIP | Peer/role event, ARP/ND, route, policy |
| Mất IdP/RADIUS chính | Luồng hiện hữu theo chính sách, failover xác thực nếu có | Không tự bỏ qua MFA hoặc cấp quyền quá rộng | Authentication logs, session test |
| Mất DNS resolver chính | Truy vấn chuyển resolver còn lại | DNS filtering và logging giữ nguyên | DNS query results, policy logs |
| Mất node inline IPS | Chuyển inspection hợp lệ hoặc xử lý theo risk decision | Không tự bypass trái chính sách | IPS status, path probe, detection evidence |
| Mất collector log | Bảo vệ network service theo thiết kế | Có cảnh báo mất telemetry và cơ chế buffer | SIEM ingest gap, queue metrics |
| Node trở lại sau outage | Ổn định, không flapping | Không chuyển về policy cũ, không split-brain | Role history, config diff, application checks |
| Mất AZ/cloud NVA | Đường đi hoạt động theo thiết kế AZ | Security group, routes, WAF/inspection tương đương | Cloud health, flow logs, test nhiều AZ |

### 20.1. Bộ phép thử dương và âm

Ví dụ kiểm tra từ các nguồn được ủy quyền:

| Luồng | Mong đợi trước lỗi | Mong đợi sau failover |
| --- | --- | --- |
| App client → HTTPS ứng dụng | ALLOW | ALLOW, thời gian phục hồi trong RTO |
| User VPN có MFA → ứng dụng | ALLOW | ALLOW sau thiết lập lại nếu cần |
| Guest VLAN → management subnet | DENY | DENY |
| Internet → giao diện quản trị firewall | DENY | DENY |
| App → DNS resolver dự phòng | ALLOW | ALLOW và filtering đúng |
| Thiết bị trong vùng nhạy cảm → egress ngoài allowlist | DENY | DENY |

Nếu luồng được phép hoạt động mà luồng cấm bỗng kết nối thành công, bài test **không đạt security invariant** dù SLO kết nối có thể vẫn được đáp ứng.

### 20.2. Tiêu chí nghiệm thu

- Thời gian thực tế đáp ứng mục tiêu RTO/SLO theo phương pháp đo đã thống nhất.
- Session loss, packet loss và thời gian tái xác thực nằm trong giới hạn người dùng chấp nhận.
- Không có luồng trái phép được mở, không bị mất mandatory inspection ngoài chế độ sự cố đã phê duyệt.
- Log, cảnh báo, timeline và nguyên nhân failover truy vết được.
- Tài nguyên của các node còn lại không vượt ngưỡng năng lực đã thiết kế.
- Khi sửa xong lỗi, redundancy trở lại đầy đủ, policy và phiên bản đồng nhất.
- Kịch bản có bằng chứng không rõ nguyên nhân phải đánh dấu **INCONCLUSIVE** thay vì kết luận PASS.

## 21. Ví dụ bài toán quyết định kiến trúc

### Bối cảnh giả định

Một doanh nghiệp có 500 nhân viên truy cập ứng dụng nội bộ qua VPN và Internet. Mạng có firewall biên, hai ISP, DNS nội bộ, IdP, hệ thống SIEM và Wi-Fi quản lý tập trung. Các yêu cầu được định nghĩa cho ví dụ:

- Mất một node firewall không khiến truy cập ứng dụng ngừng quá 60 giây; đây là **mục tiêu cần kiểm thử**, không phải thông số đã được bảo đảm.
- Đường tới VLAN tài chính và quản trị phải luôn qua chính sách kiểm soát bắt buộc.
- Không có giao diện quản trị firewall được truy cập trực tiếp từ Internet.
- Dữ liệu cấu hình và log thay đổi cần có phương án backup và khôi phục đã thử.
- Mất một ISP không cắt toàn bộ VPN; việc kết nối lại của client được đo riêng.

### Phương án A — Một firewall lớn và một ISP

Đơn giản, ít chi phí, nhưng nhiều SPOF. Không đáp ứng yêu cầu chịu lỗi một node hoặc một ISP; có thể chỉ phù hợp môi trường chấp nhận downtime lớn.

### Phương án B — Cặp firewall active–passive và hai ISP

Phù hợp hơn cho stateful security gateway khi nhà sản xuất hỗ trợ HA, state sync và đường uplink/downlink độc lập. Phải kiểm tra route symmetry, hội tụ, VPN re-establishment, license và công suất khi chỉ còn một node. Không tự động giải quyết mất toàn site.

### Phương án C — Active–active hai site

Có khả năng chịu lỗi lớn hơn và phục vụ nhiều nguồn, nhưng đòi hỏi thiết kế WAN, DNS/GSLB, định danh, dữ liệu, session steering và policy parity phức tạp. Nếu mục tiêu hiện tại chỉ yêu cầu chịu lỗi một node/site link tại cùng cơ sở, phương án này có thể vượt nhu cầu và tăng rủi ro vận hành.

**Lựa chọn minh họa:** phương án B với tuyến ISP và switch độc lập, failover manual/automatic theo khả năng hãng, VPN và DNS dự phòng, backup/OOB và quy trình kiểm thử định kỳ. Phương án này là một lựa chọn trong bối cảnh giả định, không thay thế khảo sát thực tế. Nếu yêu cầu chịu lỗi toàn site, phải tiếp tục đánh giá C hoặc DR riêng.

## 22. Ghi lại quyết định bằng Architecture Decision Record

Một **ADR** làm rõ vì sao kiến trúc được chọn và các đánh đổi cần bảo vệ khi hệ thống thay đổi.

~~~markdown
# ADR-NET-HA-005: HA cho firewall biên và truy cập VPN

Trạng thái: Proposed (chờ phê duyệt)

Bối cảnh:
- Dịch vụ Internet/VPN là thiết yếu.
- Một firewall hoặc một ISP hỏng không được gây outage kéo dài.
- Chính sách quản trị/segmentation phải giữ nguyên ở đường dự phòng.

Yêu cầu:
- RTO cho luồng ứng dụng quan trọng: tối đa 60 giây (mục tiêu).
- Chỉ cho phép quản trị qua VPN/bastion.
- Cần kiểm thử route, NAT, session, DNS và IdP trong failover.

Các phương án:
A. Single firewall/ISP
B. Firewall active-passive + dual ISP/switch
C. Active-active đa site

Quyết định đề xuất:
- B, với đồng bộ config/state và health check end-to-end
  theo khả năng sản phẩm được chọn.
- Luồng guest→management và Internet→admin luôn DENY.

Hệ quả:
- Chi phí thêm thiết bị, nguồn, link và giám sát.
- Cần đủ throughput của một node khi node còn lại lỗi.
- VPN/TCP session có thể phải tạo lại; phải đo trước nghiệm thu.

Kiểm chứng:
- Lab failover, đo RTO và tỷ lệ session còn hoạt động.
- Thử cả luồng ALLOW và DENY ở hai trạng thái.
- Kiểm tra split-brain, upgrade path và khả năng phục hồi.

Chủ sở hữu: Network & Security Architecture
Ngày rà soát: theo quy trình thay đổi của tổ chức
~~~

ADR cần có **trạng thái, owner, bằng chứng thử nghiệm, rủi ro còn lại và điều kiện xem xét lại**. Không tự ghi “Accepted” nếu chưa có phê duyệt của chủ kiến trúc và vận hành.

## 23. Những sai lầm thiết kế thường gặp

| Sai lầm | Vì sao rủi ro | Cách tránh |
| --- | --- | --- |
| Mua hai thiết bị và gọi là HA | Có thể chung switch, nguồn, ISP hoặc lỗi cấu hình | Phân tích failure domain và test một node mất |
| Chỉ kiểm tra ping và trạng thái cluster | Data plane, VPN, DNS hoặc ứng dụng có thể đã hỏng | Đo synthetic transaction end-to-end và security invariants |
| Cho rằng VRRP đồng bộ session | VRRP chủ yếu cung cấp cơ chế gateway ảo | Đánh giá state sync/NAT/session của sản phẩm |
| Active–active firewall nhưng route bất đối xứng | Gói trả về tới node không có session state | Flow pinning hoặc cluster được hỗ trợ và test hai chiều |
| Nâng cấp hai node cùng lúc | Mất đường dự phòng, lỗi chung khi firmware có sự cố | Staged rollout và kiểm tra compatibility |
| Fail-open IPS mà không có quyết định rủi ro | Giữ traffic nhưng bỏ inspection bắt buộc | Chính sách lỗi được phê duyệt, alert và bù trừ |
| Dự phòng gateway nhưng IdP/DNS là SPOF | VPN hoặc ứng dụng vẫn không dùng được | Xem phụ thuộc theo service journey |
| Không giữ headroom | Node còn lại quá tải ngay khi failover | Capacity sizing theo N−1 và tải đỉnh |
| Auto-failback quá nhạy | Flapping gây nhiều lần gián đoạn | Hold-down/hysteresis và failback policy |
| Không test IPv6 hoặc WAN dự phòng | Đường phụ có thể bypass ACL | Ma trận kiểm thử mọi nguồn và đường đi |
| Chỉ kiểm thử điều kiện ALLOW | Luồng trái phép có thể mở sau failover | Thử DENY và kiểm tra policy parity |
| Giám sát nằm trong chính failure domain | Mất luôn bằng chứng khi xảy ra sự cố | Out-of-band monitoring và log buffering |

## 24. Checklist thiết kế và vận hành

### Trước khi phê duyệt kiến trúc

- [ ] Đã xác định dịch vụ quan trọng, SLI/SLO, RTO và RPO áp dụng.
- [ ] Đã vẽ đường dữ liệu, đường quản trị và mọi phụ thuộc bảo mật.
- [ ] Đã phân tích SPOF, common-cause failure và failure domain cần chịu.
- [ ] Đã chọn A/P, A/A, N+1 hoặc đa site có giải thích đánh đổi.
- [ ] Đã kiểm tra khả năng hỗ trợ HA/state sync/session theo đúng phiên bản sản phẩm.
- [ ] Đã đảm bảo công suất khi mất node/ISP/AZ theo phạm vi thiết kế.
- [ ] Đã mô tả xử lý heartbeat loss, split-brain, failback và fencing.
- [ ] Đã chốt các security invariant ở đường chính và dự phòng.
- [ ] Đã xác định hành vi fail-open/fail-closed của thiết bị inspection.
- [ ] Đã có runbook, backup, OOB access, người chịu trách nhiệm và thời gian xử lý.

### Khi triển khai và kiểm thử

- [ ] Đã kiểm tra luồng TCP/UDP, stateful NAT, VPN và đường đi hai chiều.
- [ ] Đã đo DNS, IdP, Wi-Fi, logging và sự phụ thuộc vào controller.
- [ ] Đã thử các điểm lỗi theo ma trận với phạm vi và quyền phù hợp.
- [ ] Đã kiểm tra cả kết nối hợp lệ và kết nối bị từ chối.
- [ ] Đã đo time-to-detect, failover time, recovery time và session impact.
- [ ] Đã xác minh capacity/headroom, log/alert, policy parity và certificate.
- [ ] Đã ghi PASS/FAIL/INCONCLUSIVE cùng evidence, issue owner và retest.

### Trong vận hành

- [ ] Đã theo dõi node/cluster role và cảnh báo mất redundancy.
- [ ] Đã có kế hoạch cập nhật firmware, certificate, IPS signatures theo đợt.
- [ ] Đã rà soát ngoại lệ ACL, rule drift và thay đổi cloud/ISP.
- [ ] Đã thử lại failover theo lịch hoặc sau thay đổi quan trọng.
- [ ] Đã cập nhật ADR và runbook theo các giả định mới và sự cố đã xảy ra.

## 25. Tình huống và câu hỏi tự kiểm tra

**Tình huống 1 — Firewall dự phòng nhưng mất toàn bộ kết nối:** hai firewall dùng cùng một core switch. Khi switch lỗi, cả hai firewall còn chạy nhưng ứng dụng không truy cập được. Hãy xác định failure domain bị bỏ sót và cách thay đổi topology.

**Tình huống 2 — VPN báo kết nối lại nhưng không mở được ứng dụng:** ISP chuyển qua dự phòng, tunnel đã lên nhưng DNS nội bộ không phân giải. Cần đo SLI nào và bổ sung dependency gì trong runbook?

**Tình huống 3 — Active–active và mất phiên:** luồng đi qua firewall A, đường trả về qua firewall B. Hai node không có state-sharing phù hợp. Vì sao kết nối bị rơi và nên thay đổi cách điều hướng flow thế nào?

**Tình huống 4 — IPS tiếp tục cho traffic khi lỗi:** một inline IPS tự bypass, ứng dụng không gián đoạn nhưng lớp kiểm tra mã độc biến mất. Quyết định fail-open/fail-closed phải dựa trên tiêu chí và phê duyệt nào?

**Tình huống 5 — Dự phòng hai zone nhưng một rule sai:** cấu hình IaC triển khai ACL cho cả hai zone, vô tình cho phép guest VLAN vào management subnet. Vì sao multi-AZ không giúp phòng lỗi này? Biện pháp kiểm soát thay đổi và thử âm nào cần có?

Tự trả lời thêm:

1. Vì sao RTO của VPN không thể đo chỉ bằng trạng thái “gateway up”?
2. Tại sao hai node 99,9% không tự động tạo hệ thống 99,9999%?
3. Phân biệt việc đồng bộ cấu hình và đồng bộ session của firewall.
4. Tại sao DNS TTL thấp chưa chắc bảo đảm failover ứng dụng ngay?
5. Nếu hệ thống đạt SLO nhưng mất log kiểm tra lưu lượng trong failover, phải ghi nhận kết quả như thế nào?
6. Khi nào chọn active–passive thay vì active–active cho security gateway stateful?
7. Làm thế nào chứng minh đường dự phòng vẫn chặn traffic ngoài chính sách?
8. Những thay đổi nào có thể làm mất hiệu quả HA dù topology không đổi?

**Ghi nhớ:** thiết kế high availability cho bảo mật mạng là thiết kế **khả năng tiếp tục dịch vụ trong ranh giới bảo mật đã xác định**. Redundancy chỉ là một thành phần; cần kiểm soát lỗi chung, đường đi hai chiều, đồng bộ trạng thái, năng lực N−1, phụ thuộc DNS/VPN/IdP, hành vi inspection, phát hiện sự cố và quy trình failover được kiểm thử. Một thiết kế được nghiệm thu khi **luồng hợp lệ phục hồi đúng mục tiêu, luồng bị cấm tiếp tục bị chặn và đội vận hành có đủ quan sát để giải thích sự cố**.
