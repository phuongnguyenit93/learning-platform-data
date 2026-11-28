# Thiết kế VPN cho mô hình hybrid cloud: kết nối an toàn, định tuyến đúng và vận hành bền vững

Một doanh nghiệp giữ hệ thống dữ liệu tại data center riêng nhưng triển khai API, dịch vụ phân tích và ứng dụng khách hàng trên public cloud. Nhân viên có thể làm việc từ xa; các dịch vụ trong cloud cần gọi API hoặc truy cập một số tài nguyên on-premises. Nếu chỉ “bật một VPN tunnel” rồi cho phép toàn bộ địa chỉ hai phía kết nối, mạng có thể chạy trong bài kiểm thử ban đầu nhưng sẽ gặp rủi ro khi route đổi, một đường Internet lỗi, dải địa chỉ bị trùng, chứng chỉ hết hạn hoặc workload cloud được mở rộng sang vùng mới.

**Thiết kế VPN cho mô hình hybrid cloud** là quá trình thiết lập kết nối được bảo vệ giữa **hạ tầng tại chỗ (on-premises)**, một hoặc nhiều mạng cloud và **người dùng/thiết bị từ xa**, đồng thời bảo đảm các yêu cầu **xác thực, mã hóa, định tuyến, phân đoạn, khả năng sẵn sàng, quan sát và quản trị vòng đời**. VPN là phương tiện tạo đường truyền tin cậy ở mức nhất định; nó **không tự động xác thực ứng dụng, cấp quyền tối thiểu hay loại bỏ mọi nguy cơ của endpoint**.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, kiến trúc VPN liên hệ trực tiếp với firewall stateful, NAT, DNS, IDS/IPS, NAC, Wi-Fi, mô hình hóa mối đe dọa và bảo vệ mạng cloud. Bài này trình bày cách lựa chọn và kiểm chứng **một thiết kế có thể vận hành**, thay vì chỉ mô tả màn hình tạo VPN của một nhà cung cấp.

> **Giới hạn và nguyên tắc:** Mọi địa chỉ và cấu hình trong ví dụ chỉ là dữ liệu lab. Không kết nối tới tài nguyên của bên thứ ba, không thay đổi routing/firewall/VPN production hoặc thử ngắt dịch vụ nếu không được cấp quyền. Thuật ngữ và khả năng cụ thể của VPN gateway, transit hub, BGP và cơ chế HA phải được kiểm chứng trên nền tảng thực tế.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **site-to-site VPN**, **remote-access VPN**, **private connectivity** và **ZTNA/application access** trong một mạng hybrid.
2. Phác thảo kiến trúc **on-premises ↔ cloud hub ↔ spoke workloads**, xác định vùng tin cậy, VPN termination và điểm thực thi firewall.
3. Giải thích nền tảng của **IPsec/IKEv2**, ESP, NAT traversal, chứng chỉ/PSK và tính chất của tunnel mã hóa.
4. Thiết kế không gian **CIDR IPv4/IPv6**, tránh hoặc xử lý prefix trùng và xác định định tuyến chiều đi/chiều về.
5. Lựa chọn **BGP hoặc static routes**, kiểm soát route advertisement, failover, VRF, route leak và đường bypass.
6. Thiết kế **DNS hybrid**, phân giải tên nội bộ, split-horizon và chính sách resolver cho client từ xa.
7. Áp dụng **MFA, danh tính thiết bị, chứng chỉ, NAC, phân đoạn và least privilege** thay vì coi kết nối VPN là đủ tin cậy.
8. Xây dựng **monitoring, SLI/SLO, kiểm thử nghiệm thu, quy trình xử lý sự cố, bảo trì và rollback**.

## 2. Hybrid cloud cần kết nối những đối tượng nào?

Một môi trường hybrid có thể có nhiều loại lưu lượng với yêu cầu khác nhau:

| Luồng | Ví dụ | Yêu cầu cốt lõi |
|---|---|---|
| **On-prem → cloud** | API nội bộ gọi dịch vụ xử lý đơn hàng trong cloud | Route đúng, TLS ứng dụng, DNS và policy chỉ cho endpoint cần thiết |
| **Cloud → on-prem** | Workload cloud gọi dịch vụ dữ liệu đặt tại data center | Kiểm soát danh tính workload, giới hạn cổng/đích, log và HA |
| **Cloud ↔ cloud** | Ứng dụng tại VPC/VNet A gọi dịch vụ trong mạng B | Phân đoạn giữa môi trường, tránh tự mở transit quá rộng |
| **Remote user → ứng dụng nội bộ** | Nhân viên làm việc ở nhà truy cập portal, API quản trị | MFA, posture thiết bị, phân quyền theo ứng dụng/role |
| **Remote admin → hạ tầng** | Quản trị viên tới bastion/jump host hoặc control plane | PAM, MFA mạnh, session audit, subnet quản trị riêng |
| **Internet user → dịch vụ công khai** | Khách hàng gọi website được triển khai cloud | CDN/WAF/LB bảo vệ đường public; thường không đi qua corporate VPN |
| **Backup/DR** | Sao lưu hoặc chuyển dữ liệu giữa data center và cloud | Băng thông, mã hóa, lịch chạy, tính nhất quán và recovery test |

**Không nên đưa toàn bộ traffic vào một đường VPN chỉ vì môi trường là hybrid.** Người dùng Internet công khai, quản trị viên, batch backup và microservice có **đường đi, bề mặt rủi ro và nhu cầu hiệu năng** khác nhau.

### Các khái niệm dễ nhầm

- **Hybrid cloud** không đồng nghĩa một data center nối tới đúng một cloud; có thể có nhiều region, tài khoản, subscription hoặc nhà cung cấp.
- **VPN connectivity** không đồng nghĩa **authorization**. IP có route tới database không chứng minh user hay service có quyền truy cập.
- **Private IP** không mặc nhiên bảo đảm an toàn. Network segmentation và xác thực vẫn cần thiết dù traffic không đi trực tiếp qua Internet.
- **Một tunnel lên trạng thái UP** không chứng minh ứng dụng hoạt động: route, DNS, ACL, MTU, TLS và dịch vụ đích còn phải được kiểm chứng.

## 3. Kiến trúc tham chiếu: tách đường kết nối và quyền truy cập

Một sơ đồ logic có thể là:

~~~text
                  Người dùng Internet
                         |
                    [CDN / WAF]
                         |
                [Public App / LB]
                         |
                   [Cloud Spoke A]
                         |
                     [Cloud Hub]
                  /       |       \
       [VPN Gateway]   [Firewall]  [Cloud Spoke B]
          ||      ||
       IPsec A  IPsec B
          ||      ||
       [On-prem Edge / VPN GW]
                |
       [On-prem Internal FW]
          /       |        \
      [Apps]     [DB]    [Management]

       [Remote user / managed device]
                    |
             [Remote-access VPN
              hoặc ZTNA broker]
                    |
            [Policy enforcement]
                    |
          Chỉ ứng dụng được phép
~~~

Sơ đồ là **mô hình khái niệm**; từng cloud có cách tổ chức hub, route table, gateway và firewall khác nhau. Một số thiết kế kết thúc site-to-site VPN tại cloud gateway rồi định tuyến tới transit hub; một số đặt network virtual appliance ở vùng hub. Không mặc định có thể ghép bất kỳ loại gateway với bất kỳ topology nào.

### Ba mặt phẳng cần tách

1. **Control plane:** cấu hình VPN, khóa, chính sách, BGP, cloud API, identity và route propagation.
2. **Data plane:** gói ứng dụng thật đi qua các interface, tunnel, firewall, NAT và load balancer.
3. **Management/observability plane:** logs, metrics, tracing, SIEM, change ticket, PKI và điều khiển sự cố.

Một kiến trúc tốt xác định **ai quản lý mỗi mặt phẳng, dữ liệu nào có thể quan sát, ai được thay đổi policy và cách xác minh tác động lên data plane**.

## 4. Chọn hình thức kết nối phù hợp

| Phương án | Phù hợp với | Ưu điểm | Hạn chế/rủi ro |
|---|---|---|---|
| **Site-to-site IPsec VPN** | Kết nối định tuyến giữa on-prem và mạng cloud | Tạo tunnel mã hóa qua mạng IP, triển khai linh hoạt | Phụ thuộc Internet/underlay, thiết kế routing/HA phức tạp |
| **Remote-access VPN** | Laptop/thiết bị được quản lý truy cập vùng nội bộ | Kiểm soát danh tính/thiết bị và cấp đường truy cập | VPN quá rộng dễ tạo quyền lateral movement |
| **ZTNA / per-application access** | Cấp quyền tới ứng dụng cụ thể dựa trên identity và posture | Giảm việc phơi bày toàn subnet nếu được thiết kế đúng | Phụ thuộc broker/connector/policy, có giới hạn tương thích |
| **Private cloud connectivity** | Dịch vụ cần kết nối riêng hoặc throughput/latency có SLA | Đường vận chuyển chuyên dụng theo nhà cung cấp | Không phải mọi dịch vụ private link đều tự mã hóa end-to-end |
| **Private connection + IPsec overlay** | Cần cả đường riêng và kiểm soát mã hóa rõ ràng | Tách underlay khỏi bảo vệ dữ liệu | Thêm chi phí, MTU và vận hành |
| **SD-WAN với tunnel được bảo vệ** | Nhiều chi nhánh, nhiều nhà mạng và steering theo chất lượng | Có khả năng chọn tuyến và quản lý tập trung | Độ phức tạp policy, controller và route failover |

**Private connectivity không phải mặc nhiên tương đương VPN mã hóa.** Một leased/private circuit tạo cách vận chuyển riêng ở mức nhất định, nhưng nhu cầu TLS/IPsec vẫn phải được xác định theo mô hình đe dọa và hợp đồng dịch vụ.

**VPN site-to-site và VPN remote access là hai bài toán khác nhau.** Site-to-site thường tin cậy vào gateway/site và policy mạng. Remote access cần xác thực người dùng, kiểm tra thiết bị, quản lý phiên và quyền truy cập từng ứng dụng.

### Khi nào không nên mở toàn bộ mạng qua VPN?

Nếu mục đích chỉ là cho vài người sử dụng portal hoặc SSH tới jump host, có thể xem xét **ZTNA/app gateway, bastion hoặc giải pháp truy cập theo phiên**. VPN toàn mạng khiến client thấy nhiều route và dịch vụ hơn cần thiết, tạo yêu cầu chặt hơn về NAC, endpoint và host firewall.

## 5. IPsec và IKEv2: những thành phần phải hiểu

**IPsec** là tập hợp cơ chế bảo vệ traffic IP. Trong nhiều VPN site-to-site, **IKEv2** dùng để xác thực hai peer, thương lượng tham số và thiết lập những security association (SA); **ESP** bảo vệ dữ liệu trong các SA tương ứng.

~~~text
On-prem VPN Gateway                         Cloud VPN Gateway
        |                                           |
        |------ IKE negotiation / authentication -->|
        |<------ Peer authentication / SA state ----|
        |                                           |
        |<==== ESP-protected IP packets ===========>|
        |                                           |
        +------ Rekey / liveness / recovery -------+
~~~

Đây là **dòng khái quát**, không phải thứ tự đầy đủ mọi thông điệp IKEv2.

### IKE SA và Child SA

| Thành phần | Vai trò |
|---|---|
| **IKE SA** | Bảo vệ phiên điều khiển IKE và xác thực đối tác theo thuật toán được thương lượng |
| **Child SA** | Bảo vệ lưu lượng dữ liệu, với các thông số, hướng và traffic selectors tương ứng |
| **ESP** | Cung cấp cơ chế bảo mật gói IP, thường là mã hóa có xác thực và chống replay khi cấu hình phù hợp |
| **Traffic selectors** | Xác định tập nguồn/đích traffic được phép bảo vệ trong SA; ý nghĩa triển khai có thể khác route/ACL |
| **Rekey / SA lifetime** | Luân chuyển trạng thái/khóa theo chính sách, cần tương thích hai peer |
| **NAT traversal (NAT-T)** | Cho phép IPsec đi qua NAT khi hỗ trợ, thường qua UDP encapsulation |

Trong cấu hình phổ biến, **IKE dùng UDP/500**, NAT-T thường dùng **UDP/4500**, và ESP native dùng **IP protocol 50**. Những giá trị này **không phải danh sách universal** cho mọi VPN: TLS-based VPN, WireGuard và các sản phẩm đặc thù dùng cơ chế/cổng khác; IPsec có NAT-T có thể vận chuyển ESP đã encapsulate qua UDP thay vì ESP native trên đường ngoài.

### Nguyên tắc lựa chọn mật mã

- Ưu tiên bộ thuật toán **được nhà cung cấp hỗ trợ và chính sách hiện hành cho phép**, chẳng hạn các cơ chế AEAD hiện đại phù hợp.
- Dùng **xác thực peer mạnh** và cách trao đổi khóa cung cấp forward secrecy theo cấu hình, không tự chọn bộ mã cũ chỉ để kết nối được.
- Thiết lập **rekey/lifetime, chống replay và kiểm tra liveness** nhất quán; giám sát lỗi khi đổi khóa.
- Không đưa mật khẩu, PSK hoặc private key vào ticket, file cấu hình mẫu hoặc log công khai.
- Tránh coi tên giao thức một mình là bảo đảm: cấu hình, phiên bản, danh tính peer và vận hành khóa quyết định mức an toàn.

**IPsec bảo vệ đường truyền giữa hai điểm kết thúc tunnel.** Dữ liệu được giải mã ở gateway và có thể tiếp tục đi qua nhiều mạng nội bộ; các lớp bên trong vẫn cần **TLS/mTLS, firewall và authorization** phù hợp.

## 6. Route-based và policy-based VPN

Hai mô hình triển khai IPsec thường gặp:

| Tiêu chí | Route-based VPN | Policy-based VPN |
|---|---|---|
| Mô hình | Traffic chọn qua tunnel interface/route, có quan hệ với SA | Traffic được chọn theo tập policy/traffic selector |
| Định tuyến | Có thể thuận tiện cho BGP/dynamic routing nếu nền tảng hỗ trợ | Phụ thuộc cấu hình selector và khả năng nhà cung cấp |
| Thay đổi nhiều subnet | Quản lý qua route và firewall khi triển khai phù hợp | Có thể cần quản lý nhiều selector/policy |
| Failover | Có thể kết hợp nhiều tunnel/route/BGP | Cách chuyển lưu lượng tùy sản phẩm |
| Điểm cần thận trọng | Route đưa traffic vào tunnel **không thay thế** giới hạn firewall/selector | Selector không tự bảo đảm route chiều về hoặc khả năng phục vụ |

Không có nghĩa một loại luôn an toàn hơn loại kia. Hãy chọn dựa trên **số mạng, khả năng HA, dynamic routing, automation, cloud gateway và yêu cầu compliance**, rồi kiểm chứng tương thích cả hai đầu.

### Những điều phải đối chiếu giữa hai peer

1. Phiên bản IKE và thuật toán được hỗ trợ.
2. Danh tính gateway, PSK/certificate và cách xác thực peer.
3. IP public/endpoint, NAT-T, đường cho IKE/ESP.
4. Traffic selectors hoặc tunnel interface theo thiết kế.
5. Routing/route advertisement tới từng CIDR.
6. Dải IP không trùng, NAT nếu cần và kiểm soát chiều về.
7. DPD/liveness, rekey, lifetime, HA và log.
8. Firewall policy cả **trước và sau điểm kết thúc IPsec**.

Chỉ cần một mục không tương thích đã có thể khiến tunnel không lên hoặc lên rồi **chỉ một số flow hoạt động**.

## 7. Quy hoạch CIDR cho hybrid cloud

Mô hình địa chỉ nên có **source of truth/IPAM** trước khi dựng tunnel. Ví dụ:

| Zone | CIDR IPv4 lab | Chủ sở hữu | Vai trò |
|---|---|---|---|
| On-prem applications | **10.20.0.0/16** | Network/DC | Dịch vụ nội bộ |
| On-prem management | **10.20.40.0/24** | Network/Security | Jump host và thiết bị quản trị |
| Cloud hub/transit | **10.50.0.0/16** | Cloud networking | Gateway, firewall và shared services |
| Cloud production spoke | **10.60.0.0/16** | App platform | API và application workloads |
| Cloud analytics spoke | **10.70.0.0/16** | Data platform | Analytics, báo cáo và batch jobs |
| Remote-access pool | **10.90.8.0/22** | Identity/Network | Địa chỉ client VPN nếu mô hình sử dụng IP pool |

Những CIDR riêng trong bảng **chỉ là ví dụ**, phải kiểm tra chúng có trùng với các mạng thực hay không. **On-prem management là subnet con nằm trong 10.20.0.0/16**, nên không phải một dải địa chỉ độc lập được cấp chồng lên cho mục đích khác; cần quản lý policy chính xác ở cả subnet và vùng.

### Vấn đề CIDR overlap

Giả sử mạng on-prem và cloud đều dùng **10.10.0.0/16**. Một router không thể chỉ dựa vào địa chỉ IP đích để xác định gói 10.10.5.10 phải tới máy nào nếu cùng một route context có hai nơi cùng công bố prefix.

**Ưu tiên lựa chọn:**

1. **Renumber** một bên thành prefix không trùng nếu khả thi, nhất là với thiết kế dài hạn.
2. Nếu không thể đổi ngay, dùng **translation/NAT có kiểm soát**, các lớp proxy hoặc tách ứng dụng với địa chỉ đại diện khác biệt, theo khả năng nền tảng.
3. Dùng **VRF/segmentation và route policy** để cô lập các không gian địa chỉ chồng lấn nếu kiến trúc và ứng dụng phù hợp.

**NAT để xử lý overlap không phải phép sửa miễn phí:** có thể làm sai DNS, audit identity, ACL, logging, protocol dùng IP nhúng trong payload và đường phản hồi. Phải ghi rõ **địa chỉ gốc, địa chỉ dịch, chiều dịch, vị trí NAT và log mapping theo thời gian**.

### Kế hoạch IPv6

Nếu tổ chức dùng dual-stack, phải quy hoạch **GUA/ULA, route ::/0, firewall IPv6, DNS AAAA, VPN client IPv6 và khả năng hỗ trợ IPv6 của cloud gateway**. Nhiều triển khai không hỗ trợ IPv6 qua VPN giống IPv4; không giả định bật dual-stack ở VPC/VNet là tunnel hiện có tự mang IPv6.

Một host có thể truy cập dịch vụ qua IPv6 ngoài VPN trong khi chính sách IPv4 buộc đi qua tunnel. Vì vậy cần test **route leak IPv6, DNS, split tunneling, firewall và identity posture** theo thiết kế thật.

## 8. Thiết kế routing: hướng đi, chiều về và giới hạn quảng bá

**Tunnel UP không đồng nghĩa route đã đúng.** Muốn một request từ on-prem tới cloud thành công, ít nhất cần:

1. Nguồn biết route tới CIDR đích qua gateway/tunnel được duyệt.
2. Gateway hai đầu chuyển tiếp đúng qua IPsec và route tables.
3. Firewall/security group cho phép đúng flow.
4. **Đích có tuyến phản hồi hợp lệ** và không bị policy chặn.
5. Dịch vụ đích lắng nghe, xác thực và xử lý request theo mong đợi.

~~~text
On-prem app 10.20.10.25
        |
        | To 10.60.20.10
        v
On-prem route -> VPN GW -> Tunnel -> Cloud hub route
                                      |
                                      v
                                Cloud firewall
                                      |
                                      v
                              Cloud API 10.60.20.10
                                      |
                                      | Return to 10.20.10.25
                                      v
                           Cloud return route -> VPN
                                      |
                                      v
                                  On-prem app
~~~

### Static route hay BGP?

| Phương án | Lợi thế | Hạn chế |
|---|---|---|
| **Static routing** | Đơn giản, dễ hiểu khi có ít prefix/đường | Khó quản lý nhiều tunnel và failover; dễ stale route khi thay đổi |
| **Dynamic BGP routing** | Có thể trao đổi prefix, chọn đường, rút route khi phiên/peer thay đổi | Cần peer policy, filtering, ASN, next-hop, route propagation và giám sát |

**BGP là cơ chế phân phối thông tin tuyến, không phải cơ chế bảo mật tunnel.** IPsec bảo vệ đường truyền; BGP giúp truyền đạt reachability theo cấu hình. Một phiên BGP Established không tự chứng minh traffic đã đi vào FIB hoặc ACL cho phép.

### Guardrails cho BGP trong hybrid

- Chỉ **advertise các CIDR đã duyệt**, không phát toàn bộ routing table không cần thiết.
- Dùng **prefix filtering** ở cả import/export, max-prefix theo thiết bị và khả năng nền tảng.
- Phân biệt route **received, accepted, selected, advertised**; chúng có thể khác nhau.
- Xác định route ưu tiên, failover và nguyên tắc **không route leak giữa Guest/Production/Management**.
- Không đưa **default route 0.0.0.0/0 hoặc ::/0** qua VPN nếu không có yêu cầu egress routing rõ ràng.
- Nếu dùng summarization, xác minh subnet nằm trong summary có thực sự định tuyến được và policy không mở rộng ngoài mong muốn.
- Theo dõi BGP session, route count, withdrawal, next hop, ECMP và route churn theo baseline.

**Một tuyến được học là điều kiện để chuyển gói, không phải giấy phép truy cập.** Security policy phải kiểm soát riêng.

### Định tuyến bất đối xứng

Khi chiều đi qua firewall A nhưng chiều về qua firewall B, stateful firewall không chia sẻ phiên có thể từ chối gói phản hồi. Điều đó thường biểu hiện bằng **một số ứng dụng timeout**, đặc biệt sau failover hoặc thay đổi ECMP.

Phải kiểm tra **route ở hai đầu và trạng thái phiên firewall**, NAT, VRF cùng policy return path. Không sửa bằng cách mở Allow Any–Any chỉ vì không thấy response ở client.

## 9. Chọn topology: point-to-point, hub-and-spoke hay multi-hub?

### 9.1. Point-to-point

Khi có một data center và một mạng cloud, đường site-to-site tương đối đơn giản. Nhưng cần lưu ý **tunnel redundancy, DNS và route overlap** ngay từ đầu nếu dự kiến mở rộng.

### 9.2. Hub-and-spoke

~~~text
                 [On-prem DC]
                      |
               Redundant VPNs
                      |
                  [Cloud Hub]
                   /      \
              [Spoke A]  [Spoke B]
               Prod App   Analytics
~~~

Hub có thể tập trung routing, firewall, DNS forwarding, egress và logging. Ưu điểm là quản trị nhất quán; nhược điểm là **hairpin traffic, chi phí truyền qua hub, giới hạn công suất và fault domain**. Không nên mặc định spoke A có thể đi tới spoke B chỉ vì cả hai đã gắn hub — cần route và security policy được duyệt.

### 9.3. Multi-hub/multi-region

Với nhiều region hoặc nhiều nhà cung cấp, có thể dùng **nhiều hub độc lập** để giảm một điểm lỗi. Tuy nhiên, phải tránh **route loop, quảng bá chéo không kiểm soát và hairpin liên vùng**. Quyết định active-active hay active-standby phụ thuộc khả năng gateway, BGP, firewall state, path symmetry và ngân sách.

### 9.4. Mesh khi nào phù hợp?

Full mesh có thể giảm số hop giữa các site, nhưng số quan hệ kết nối và policy tăng nhanh khi số site lớn. Một tổ chức ít site quan trọng có thể cần direct connectivity riêng cho vài luồng latency-sensitive, trong khi phần lớn workload vẫn đi qua hub.

**Chọn topology dựa trên luồng nghiệp vụ và fault domain**, không chỉ theo số nút trong sơ đồ.

## 10. High availability và thiết kế failover

Một tunnel có thể mất vì Internet uplink, thiết bị VPN, cloud gateway, routing peer, chứng chỉ, rekey hoặc một vùng hạ tầng cloud gặp lỗi. Do đó, **“có hai tunnel” chưa chắc là HA** nếu cả hai cùng đi qua một router, một ISP hoặc một gateway duy nhất.

### Những lớp dự phòng

| Lớp | Khả năng dự phòng | Điều cần xác minh |
|---|---|---|
| **On-prem edge** | Hai VPN gateway/firewall theo HA phù hợp | State, routing ownership, heartbeat, firmware và config sync |
| **Internet uplink** | Hai ISP/đường độc lập khi có thể | Thực sự khác failure domain; BGP/route ưu tiên đúng |
| **IPsec tunnels** | Hai hoặc nhiều tunnel độc lập theo khả năng cloud | Rekey, DPD, failover, path symmetry |
| **Cloud VPN gateway** | Gateway/zone dự phòng theo kiến trúc provider | SLA, điểm kết thúc, giới hạn route/BGP, khả năng thay đổi |
| **Cloud transit/hub** | Năng lực xử lý và dự phòng network path | Không tạo điểm nghẽn duy nhất ở firewall/NVA |
| **DNS và identity** | Resolver/RADIUS/IdP/PKI có kế hoạch dự phòng | VPN lên nhưng đăng nhập hoặc phân giải tên vẫn có thể lỗi |
| **Ứng dụng** | Multi-AZ/region, LB, database HA | VPN khỏe không đồng nghĩa ứng dụng có HA |

### Active-active so với active-standby

- **Active-active:** nhiều đường có thể vận chuyển traffic cùng lúc, hữu ích cho cân bằng tải hoặc redundancy nhưng phải quan tâm **ECMP hashing, asymmetric return và stateful firewall**.
- **Active-standby:** đường dự phòng ít được sử dụng cho đến khi có lỗi; dễ kiểm soát một số path nhưng dễ để sót lỗi trên đường standby nếu không kiểm thử định kỳ.

### Failover không phải luôn tức thời

Thời gian khôi phục có thể bao gồm:

~~~text
Fault xảy ra
    |
    v
Phát hiện link/peer lỗi (DPD/BFD/health)
    |
    v
Tunnel/route rút hoặc đổi ưu tiên
    |
    v
RIB/FIB hội tụ + firewall state xử lý
    |
    v
DNS/app retry hoặc client reconnect
    |
    v
Giao dịch người dùng phục hồi
~~~

**RTO và RPO khác nhau:** Recovery Time Objective (RTO) nói về thời gian khôi phục dịch vụ; Recovery Point Objective (RPO) liên quan mức dữ liệu có thể mất trong quy trình recovery. VPN failover có thể đóng góp vào RTO nhưng không thay thế thiết kế sao lưu/nhất quán dữ liệu cho RPO.

## 11. Remote access: không cấp toàn mạng chỉ vì người dùng đăng nhập VPN

Remote-access VPN bổ sung một loại endpoint **không luôn nằm trong vùng vật lý do doanh nghiệp kiểm soát**. Laptop có thể kết nối từ Wi-Fi tại nhà, sân bay hoặc hotspot công cộng. Vì thế cần kết hợp:

1. **MFA/phương thức xác thực chống phishing phù hợp**, đặc biệt với quyền quản trị.
2. **Device posture:** trạng thái MDM/EDR, bản vá, mã hóa đĩa, certificate, khóa màn hình theo chính sách.
3. **Least privilege:** cấp route và ACL chỉ tới tài nguyên, cổng, ứng dụng được phép.
4. **Session controls:** timeout, xác thực lại khi rủi ro thay đổi, revoke khi user/device bị thu hồi.
5. **Phân đoạn theo vai trò:** nhân viên, nhà thầu, vendor và admin không nhận cùng mức quyền.
6. **Logging:** user/device/session ID, IP pool, thay đổi role, thất bại MFA và hoạt động tại điểm thực thi.
7. **Endpoint hardening:** local firewall, EDR, certificate validation và kiểm soát tách dữ liệu.

### Remote access và site-to-site đi chung đường hay tách?

Một số doanh nghiệp kết thúc hai loại VPN tại cùng nền tảng, số khác dùng các gateway hoặc tenant riêng. Quyết định phụ thuộc **khả năng cách ly policy, tải, HA, quản lý identity, kiểm toán và blast radius**. Không nên mặc định người dùng remote được gắn trực tiếp vào mạng database chỉ vì gateway cùng site-to-site có tuyến tới database.

### Mô hình phân quyền minh họa

| Vai trò | Tài nguyên được phép | Điều không nên cấp mặc định |
|---|---|---|
| Employee | Portal và app nội bộ qua gateway | Truy cập trực tiếp DB hoặc mọi subnet cloud |
| Cloud developer | Dev/test API theo role và phiên | Production network, management interface không có phê duyệt |
| Operations admin | Bastion và control plane đã xác thực mạnh | SSH/RDP thẳng tới mọi máy từ client không quản lý |
| Vendor | Một ứng dụng hoặc môi trường được chỉ định, có thời hạn | Route tới toàn bộ VPC/VNet hoặc data center |
| Incident responder | Quyền khẩn cấp theo quy trình, có audit | Quyền vĩnh viễn không cần review |

**MFA ở cửa VPN không thay thế authorization tại ứng dụng.** Một kết nối đã được xác thực vẫn có thể bị lợi dụng nếu tài khoản bị chiếm hoặc endpoint nhiễm mã độc.

## 12. Split tunneling và full tunneling

**Full tunnel** thường đưa phần lớn hoặc toàn bộ traffic theo policy vào VPN trước khi ra Internet. **Split tunnel** chỉ đưa những đích cụ thể vào VPN, còn traffic khác đi qua đường mạng cục bộ.

| Tiêu chí | Full tunnel | Split tunnel |
|---|---|---|
| Đường Internet thông thường | Qua gateway tổ chức nếu chính sách định tuyến như vậy | Có thể đi trực tiếp từ client |
| Khả năng kiểm soát egress | Tập trung hơn nếu traffic thực sự đi qua gateway | Cần endpoint/secure web gateway/DNS controls bổ trợ |
| Băng thông/độ trễ | Có thể tăng backhaul và tải VPN | Có thể giảm tải và độ trễ cho SaaS/Internet |
| Khả năng làm việc từ xa | Phụ thuộc năng lực VPN gateway và uplink | Có thể phù hợp SaaS, nhưng tăng yêu cầu bảo vệ client |
| Rủi ro đáng chú ý | Gateway là điểm nghẽn; chính sách quá rộng | Route/DNS leak, traffic bypass điểm giám sát, IPv6 khác IPv4 |

**Không nên coi full tunnel luôn an toàn hơn hoặc split tunnel luôn kém an toàn.** Phải dựa trên loại dữ liệu, thiết bị có quản lý, chính sách truy cập và kiến trúc giám sát. Ngay cả full tunnel có thể có **local-subnet exceptions, IPv6 routes hoặc ứng dụng bypass** theo cấu hình; cần kiểm chứng traffic thực tế.

### DNS leak và IPv6 leak

Một máy nhận DNS resolver nội bộ qua VPN nhưng browser vẫn sử dụng DoH bên ngoài, hoặc có IPv6 default route đi trực tiếp ra Internet trong khi IPv4 dùng VPN. Điều đó có thể vi phạm chính sách nếu tổ chức yêu cầu resolver/egress tập trung.

Kiểm tra cần thực hiện theo **OS/browser/client/VPN mode**, không chỉ nhìn một dòng default route. Những kiểm soát như kill switch, local LAN access, always-on VPN và policy DoH phải có **thiết kế và ngoại lệ rõ**, vì bật sai có thể khiến người dùng mất kết nối ngay cả khi VPN đang lỗi.

## 13. DNS hybrid: phân giải tên qua nhiều môi trường

VPN lên nhưng ứng dụng không hoạt động thường bắt nguồn từ **DNS resolution**, không phải mã hóa. Tổ chức có thể có:

- DNS nội bộ cho tên tài nguyên on-prem.
- DNS private của cloud cho workload trong VPC/VNet.
- DNS public cho website Internet.
- Split-horizon DNS trả lời khác nhau tùy nguồn truy vấn và chính sách.
- Conditional forwarding giữa recursive resolver theo namespace được phê duyệt.

~~~text
Employee / Remote VPN
          |
     [Corp Resolver]
       /         \
Internal zone   Conditional forward
 on-prem          tới Cloud Resolver
                      |
                Cloud private zone
                      |
                  Cloud API
~~~

### Ví dụ domain phân giải

| Tên ví dụ | Nguồn dữ liệu DNS | Điều kiện |
|---|---|---|
| **db01.corp.example.test** | Internal DNS on-prem | Chỉ trả lời phù hợp với mạng/vùng được phép |
| **api.prod.cloud.example.test** | Cloud private DNS zone | Resolver nội bộ forward qua đường được quản lý nếu cần |
| **www.example.test** | Public authoritative DNS | Không mặc nhiên đưa qua VPN nếu split tunnel và policy không yêu cầu |

Những tên **example.test** là ví dụ tài liệu. Với sản phẩm cloud thực tế, tên resolver endpoint, cách forward, inbound/outbound resolver và security policy phụ thuộc nhà cung cấp.

### Checklist DNS khi dựng VPN

1. Định nghĩa **namespace nào thuộc đâu** và owner của mỗi zone.
2. Cấu hình resolver có **quyền truy cập qua VPN** và định tuyến chiều về phù hợp.
3. Tránh forwarding loop giữa on-prem và cloud.
4. Kiểm tra split-horizon và cache/TTL khi đổi địa chỉ workload.
5. Kiểm soát DNS egress/DoH của remote client theo chính sách.
6. Phân biệt lỗi **DNS NXDOMAIN/SERVFAIL/timeout** với lỗi TCP/TLS hoặc firewall.
7. Kiểm tra DNS theo cả **IPv4/IPv6**, gồm AAAA và các interface có thể dùng resolver khác.

**DNS name resolution không chứng minh quyền truy cập.** Client có thể phân giải tên private mà vẫn bị firewall/authorization từ chối — đó có thể là hành vi đúng của hệ thống.

## 14. Phân đoạn, firewall và Zero Trust trong VPN hybrid

Một lỗi thiết kế thường gặp là khai báo route tổng thể rồi tạo rule **allow all traffic between on-prem and cloud** để “đỡ vướng”. Cách này biến VPN thành đường đi rộng, tăng khả năng lateral movement khi một host bị xâm nhập.

### Phân tầng trust zone

~~~text
        [On-prem Employee]    [Remote VPN Client]
                 \                 /
                [Identity/Network Policy]
                          |
                      [Cloud Hub]
                          |
                    [Hub Firewall]
                     /        \
               [App Spoke]   [Data Spoke]
                    |             |
                  API           Database
                    \             /
                  Application Identity
~~~

Chính sách nên ràng buộc:

- **Nguồn:** site, VLAN/VRF, device posture, identity group hoặc service identity.
- **Đích:** application, subnet và port cần thiết; tránh cho quyền cả CIDR nếu không cần.
- **Chiều truy cập:** ai được **khởi tạo phiên** tới đâu; stateful reply khác với cho phép kết nối mới.
- **Môi trường:** dev/test/prod và tài nguyên quản trị có boundary riêng.
- **Logging/inspection:** traffic nào phải qua IDS/IPS/WAF/NDR/DLP, và điểm đặt sensor có thấy dữ liệu đã mã hóa không.
- **Ứng dụng:** mTLS/TLS, authorization, secret management và logging nghiệp vụ sau gateway.

### Mã hóa hai tầng khi cần

~~~text
Application Client
     |
     | HTTPS/mTLS (end-to-end ứng dụng)
     v
 On-prem VPN Gateway == IPsec == Cloud VPN Gateway
                                        |
                                        v
                                  Cloud Firewall
                                        |
                                        v
                                 Application Server
~~~

IPsec bảo vệ đoạn gateway-to-gateway; **TLS/mTLS** có thể tiếp tục bảo vệ end-to-end ở tầng ứng dụng theo thiết kế. IDS trên đường Internet thường chỉ thấy **outer IPsec metadata**; sensor sau điểm giải mã IPsec có thể thấy inner IP flow nhưng **chưa chắc đọc được HTTPS**. Phải xác định visibility theo từng lớp, không tuyên bố giám sát được toàn bộ payload chỉ vì có tunnel.

## 15. Quản lý danh tính, chứng chỉ và khóa theo vòng đời

VPN phụ thuộc thông tin xác thực peer và user. Cần có quy trình **tạo, cấp phát, lưu giữ, sử dụng, xoay vòng và thu hồi** các bí mật đó.

### Chứng chỉ so với pre-shared key

| Khía cạnh | PSK | Certificate/PKI |
|---|---|---|
| Cấp phát | Chia sẻ bí mật phù hợp cấu hình | Cấp chứng chỉ từ PKI tin cậy |
| Quản lý nhiều peer | Khó khi dùng chung bí mật hoặc cần đổi đồng loạt | Thường hỗ trợ định danh riêng và thu hồi theo chứng chỉ |
| Rủi ro | PSK yếu/lộ hoặc bị chia sẻ quá rộng | Sai PKI, trust chain, key protection, thời hạn và revocation |
| Rotation | Cần phối hợp hai đầu | Cần quản trị vòng đời CA, cert và private key |
| Điều kiện chọn | Khả năng cloud gateway, quy định tổ chức | Khả năng platform, PKI, danh tính và automation |

**Không tự giả định certificate luôn được hỗ trợ ở mọi kiểu cloud VPN gateway**, hoặc mọi sản phẩm xác minh danh tính peer theo cùng quy tắc. Phải kiểm chứng tính năng, key storage và thông số xác thực của sản phẩm.

### Checklist secret management

1. Mỗi VPN peer/gateway có định danh và owner rõ.
2. Không đưa PSK/private key vào mã nguồn, CI logs hoặc ticket.
3. Giới hạn quyền đọc/đổi bí mật; audit toàn bộ thao tác.
4. Có lịch thay và kiểm tra **hết hạn chứng chỉ**, rekey và khả năng rollback.
5. Xác minh peer identity/trust chain, không chỉ “certificate tồn tại”.
6. Xử lý user offboarding, thiết bị mất, nhà thầu hết hạn quyền và token/session revoke.
7. Có phương án ứng cứu khi khóa/CA/PSK bị lộ hoặc thất lạc.

### Tách quyền cấu hình VPN khỏi quyền ứng dụng

Người có quyền **sửa route hoặc firewall** ở cloud hub có thể tạo tác động rộng hơn người chỉ được **truy cập một ứng dụng**. Vì vậy cần phân quyền quản trị VPN, cloud network, IAM, security rule và log bằng **least privilege + separation of duties** khi phù hợp.

## 16. Hiệu năng: throughput, latency, MTU và chi phí

Một kiến trúc VPN vừa phải đáp ứng bảo mật, vừa phải có đủ năng lực cho tải thật. Những giới hạn thường gặp:

- Khả năng mã hóa/giải mã của VPN gateway/CPU hoặc accelerator.
- Băng thông underlay, độ trễ Internet và packet loss.
- Số tunnel/SA/BGP peer theo giới hạn sản phẩm.
- MTU và overhead của IPsec/NAT-T, overlay hoặc tunnel bổ sung.
- Thông lượng của cloud transit, virtual firewall, NAT, proxy và link on-prem.
- Chi phí egress/inter-region, thiết bị, subscription và logging.

### MTU và Path MTU Discovery

IPsec thêm header/overhead; kích thước **inner packet** thích hợp có thể nhỏ hơn MTU của liên kết vật lý. Nếu một gói có cờ/điều kiện không cho fragmentation mà đường đi không hỗ trợ kích thước đó, có thể xảy ra **black-hole MTU**: một số ping nhỏ chạy, nhưng HTTPS/upload/tác vụ lớn lỗi.

~~~text
Inner packet (IP + TCP/UDP + data)
          |
          v
IPsec Encapsulation (ESP / NAT-T nếu dùng)
          |
          v
Outer packet lớn hơn inner packet
          |
     Underlay path MTU
          |
          +-- Vừa: chuyển tiếp
          |
          +-- Quá lớn: fragmentation hoặc ICMP
                Packet Too Big / Fragmentation Needed
                tùy IP version và điều kiện đường truyền
~~~

**Không nên chặn toàn bộ ICMP/ICMPv6**: Path MTU Discovery có thể cần những thông báo lỗi thích hợp. **TCP MSS adjustment** có thể là một phần giải pháp trên thiết bị hỗ trợ, nhưng không áp dụng mù một giá trị cho mọi VPN, giao thức hoặc flow UDP. Cần kiểm tra overhead thật, giao thức, path MTU, xử lý IPv4/IPv6 và ứng dụng.

### Độ trễ và hairpin

Nếu một cloud service ở region gần người dùng lại gọi về on-prem để xác thực/dữ liệu rồi chuyển tiếp sang region khác, mỗi lượt request có thể tạo thêm nhiều RTT. Hãy đo **p95/p99 latency theo luồng nghiệp vụ**, không chỉ ping giữa hai gateway. Tối ưu topology, DNS và vị trí dịch vụ có thể quan trọng hơn chỉ tăng thông lượng VPN.

## 17. Monitoring và logging: biết tunnel khỏe chưa đủ

Một dashboard VPN hybrid nên có **ba lớp**:

| Lớp | Chỉ số/nhật ký | Điều nó giúp trả lời |
|---|---|---|
| **Tunnel/control plane** | IKE SA/Child SA, DPD/liveness, rekey errors, peer status, BGP neighbor, route updates | Tunnel/peer có đang thương lượng và duy trì trạng thái? |
| **Network/data plane** | Byte/packet theo tunnel, latency/loss, drop, firewall denies, NAT, route/FIB, flow logs | Gói có thực sự được chuyển qua đường dự kiến? |
| **Identity/application** | Login/MFA, device posture, DNS resolution, API success, HTTP status, app trace, transaction result | Người dùng/dịch vụ có hoàn thành nghiệp vụ đúng không? |

### Sự kiện cần cảnh báo

1. Tunnel mất hoặc liveness thất bại, đặc biệt nếu **tất cả đường dự phòng** cùng ảnh hưởng.
2. BGP neighbor down, prefix quan trọng bị withdraw hoặc route xuất hiện ngoài policy.
3. Chứng chỉ sắp hết hạn, lỗi rotation, tăng IKE negotiation/rekey failure.
4. Traffic đổi next hop/điểm kết thúc và firewall session errors tăng.
5. DNS conditional forwarding không hoạt động hoặc resolver timeout.
6. Remote VPN login thất bại/MFA bất thường, thiết bị posture không đạt, session bất thường.
7. Tunnel byte counters vẫn tăng nhưng **API success rate giảm**, gợi ý vấn đề app/DNS/MTU/ACL.
8. Lưu lượng VPN tăng bất thường so với baseline, đặc biệt tới những subnet không nằm trong ma trận truy cập.
9. Tunnel health bình thường nhưng **latency, loss hoặc DB connection errors** vượt SLO.

**Tunnel UP không phải SLI cuối cùng.** Hãy dùng synthetic probe hoặc giao dịch kiểm thử có quyền từ đúng zone, qua đường dự kiến và kiểm tra ứng dụng thật.

### Quyền riêng tư trong logs

Remote VPN logs có thể chứa user ID, device ID, địa chỉ IP tại nhà, thời gian làm việc và hoạt động ứng dụng. Cần:

- Chỉ thu trường phục vụ security/operations với mục đích và retention rõ ràng.
- Che token, password, PSK, private key và dữ liệu nhạy cảm trong log/ticket.
- Ghi audit khi xem/cấp quyền truy cập log.
- Phân biệt **IP pool của VPN** với identity của người dùng; NAT hoặc IP tái sử dụng cần gắn timestamp và session ID.

## 18. Infrastructure as Code, drift và quản lý thay đổi

Với nhiều VPC/VNet, region và tunnel, thao tác thủ công dễ tạo cấu hình lệch nhau. Có thể dùng **Infrastructure as Code (IaC)** và nguồn sự thật được phê duyệt để quản lý:

- CIDR, VPN peers, tunnel endpoints và route propagation policy.
- Prefix lists, route tables, firewall/security group rule và DNS forwarders.
- Danh tính quản trị, logging, metric/alert và owner.
- Cấu hình HA, dự phòng, change ticket và rollback.

### Cần phân biệt desired và observed state

~~~text
           IaC / Approved Network Design
                  (desired state)
                         |
                         v
                  Cloud API / Gateways
                         |
                         v
              Actual routes / SA / ACL
                  (observed state)
                         |
             Diff + peer/flow validation
                         |
                Drift alert / review
~~~

**Không tự động sửa mọi drift ngay khi phát hiện** nếu chưa xác định đó là can thiệp ứng cứu khẩn cấp, failover có chủ đích hay lỗi cấu hình. Một vòng reconcile thiếu hiểu biết có thể hoàn tác bản sửa sự cố đang cần thiết. Cần có change owner, phê duyệt, giám sát và phương án đảo chiều.

### Thay đổi đặc biệt rủi ro

- Thêm default route đi qua VPN.
- Quảng bá summary prefix quá rộng.
- Mở firewall giữa cloud production và on-prem management.
- Thay authentication/certificate của VPN gateway.
- Đổi BGP ASN/peer address/route preference ở cả hai đầu.
- Bật remote access cho unmanaged device không kiểm soát posture.
- Thay DNS forwarding hoặc split-horizon cho domain nội bộ.
- Đổi topology hub-spoke thành đường direct mà bỏ qua inspection.

Các thay đổi này cần **kiểm thử có kiểm soát, kế hoạch rollback và xác minh chiều đi–chiều về**.

## 19. Thiết kế mẫu: kết nối data center với cloud production

**Bối cảnh giả định:** Data center cung cấp một dịch vụ xác thực và cơ sở dữ liệu; cloud triển khai API production. Nhân viên làm việc từ xa chỉ cần truy cập cổng ứng dụng và bastion theo vai trò. Tổ chức muốn tránh công bố DB ra Internet và có đường VPN dự phòng.

### 19.1. Phân vùng và topology

~~~text
             [Remote Managed Laptop]
                     |
          MFA + Device posture check
                     |
             [VPN/ZTNA Access]
                     |
           [Application/Bastion policy]
                     |
                      v
                [Cloud Hub 10.50/16]
                   /          \
                  /            \
       IPsec Tunnel A      IPsec Tunnel B
            |                   |
     [ISP/Edge A]          [ISP/Edge B]
            \                   /
               [On-prem GW/FW]
                       |
       On-prem 10.20.0.0/16 (Apps/Auth/DB)

                 [Cloud Hub FW]
                       |
             Cloud Prod 10.60.0.0/16
                       |
                   [API Service]
~~~

**Sơ đồ mô tả hai đường logic độc lập**, không bảo đảm vật lý khác nhau. Trước triển khai phải xác minh hai ISP/edge/gateway có thật sự giảm failure domain, chính sách route của nền tảng và việc remote VPN client cần đi qua hub hay app gateway.

### 19.2. Bảng route mong muốn

| Thiết bị/vùng | Destination | Next hop/đường mong muốn | Điều cần kiểm tra |
|---|---|---|---|
| On-prem edge | **10.60.0.0/16** | VPN A, VPN B theo failover/BGP policy | Route không quảng bá nhầm Guest |
| Cloud hub | **10.20.0.0/16** | Site-to-site VPN được quản lý | Route tới đúng on-prem gateway |
| Cloud prod spoke | **10.20.0.0/16** | Transit/hub security path | Không bypass hub firewall |
| On-prem apps | **10.60.0.0/16** | Internal firewall/edge | Có return route và ACL |
| Remote-access client | Chỉ app/bastion prefixes được phép | VPN/ZTNA policy theo role | Không đưa toàn bộ DB subnet vào client nếu không cần |
| Guest / untrusted zone | Internal management/db ranges | Không có đường truy cập được cấp quyền | Deny tại firewall, không chỉ dựa vào thiếu route |

Nếu cloud có thêm **10.70.0.0/16** cho analytics, việc thêm route không nên mặc nhiên tạo quyền đến data center. Cần cập nhật **IPAM + route policy + firewall + DNS + monitoring** theo luồng được duyệt.

### 19.3. Ma trận firewall và ứng dụng

| Nguồn | Đích | Dịch vụ | Quyết định minh họa |
|---|---|---|---|
| On-prem service **10.20.10.0/24** | Cloud API **10.60.20.0/24** | TCP 443 | **ALLOW** với TLS và xác thực ứng dụng |
| Cloud API service identity | On-prem auth service **10.20.30.0/24** | TCP 443 | **ALLOW** theo identity/policy nếu platform hỗ trợ |
| Cloud API | On-prem DB **10.20.50.0/24** | DB port được chỉ định | Chỉ **ALLOW** cho workload đã duyệt; ưu tiên service proxy/gateway khi phù hợp |
| Guest/Unmanaged client | On-prem DB hoặc Management | Bất kỳ | **DENY** |
| Remote employee | Internal portal | HTTPS qua access gateway | **ALLOW** sau MFA/posture/authorization |
| Remote operations admin | Bastion/Jump host | Protocol quản trị được duyệt | **ALLOW** theo phiên và audit |
| Cloud analytics | Production DB | Bất kỳ ngoài danh mục | **DENY** mặc định |

**Đây là chính sách khái niệm**, không phải cấu hình firewall production. Với rule thực tế, cần xác định chiều khởi tạo, NAT, source workload identity hoặc IP/subnet cụ thể, log, TTL của quyền và cách rule stateful xử lý phản hồi.

### 19.4. DNS và danh tính

- On-prem resolver sở hữu namespace nội bộ; cloud private resolver quản lý tên cloud application.
- Chỉ forward những zone được phê duyệt, tránh vòng lặp DNS.
- Remote client nhận/áp dụng DNS phù hợp với split/full tunnel và device policy.
- Backend dùng TLS/mTLS, service identity, authorization; không tin mọi request chỉ vì đến từ IP tunnel.
- Admin dùng MFA mạnh và truy cập qua bastion, không công bố cổng quản trị trực tiếp ra Internet.

### 19.5. Điều kiện chấp nhận thiết kế

1. VPN A/B được xác thực, rekey và giám sát.
2. BGP/static route đúng prefix, có đường về qua boundary mong muốn.
3. Cloud prod chỉ tới đúng app/auth/DB cần thiết.
4. Remote employee không có lateral access vượt role.
5. DNS private resolve đúng, không leak/bypass ngoài chính sách.
6. Khi hỏng một đường được phép kiểm thử, đường còn lại phục hồi trong SLO.
7. Ứng dụng/DB hoạt động, có log truy vết giữa network và app.
8. Keys/certs, IaC, owner, alerts và rollback được tài liệu hóa.

## 20. Kiểm thử nghiệm thu: cả thành công và từ chối đúng chính sách

Mỗi phép thử cần có **nguồn và đích được phép**, thời gian, request/connection ID, kết quả tại gateway/firewall và kết quả ứng dụng. Test production chỉ thực hiện khi được phê duyệt, có giới hạn và stop conditions.

| Test ID | Tình huống | Kỳ vọng |
|---|---|---|
| **HYB-01** | On-prem → Cloud API HTTPS hợp lệ | Tunnel, route, TLS/app authorization và response thành công |
| **HYB-02** | Cloud API → On-prem service được duyệt | Đúng route chiều đi/về, firewall state, log |
| **HYB-03** | Guest/unmanaged → DB/management qua mọi đường | Bị từ chối ở đúng security boundary |
| **HYB-04** | Remote employee đăng nhập với MFA và thiết bị đạt posture | Chỉ nhận ứng dụng/route được phép |
| **HYB-05** | Remote user không đạt posture hoặc bị thu hồi quyền | Không được cấp truy cập dù có network path |
| **HYB-06** | DNS private từ on-prem tới cloud API | Resolve đúng, không loop/timeout |
| **HYB-07** | DNS từ remote client trên split tunnel | Resolver đúng policy; không có DNS leak ngoài dự kiến |
| **HYB-08** | Kiểm tra IPv4/IPv6 dual-stack nếu được hỗ trợ | Không có đường bypass, route và firewall tương ứng |
| **HYB-09** | Một tunnel/peer mất trong lab hoặc maintenance được duyệt | Failover theo thiết kế, SLO dịch vụ chấp nhận được |
| **HYB-10** | Rekey/certificate rotation theo lịch thử | Kết nối duy trì hoặc phục hồi theo thiết kế; log rõ nguyên nhân |
| **HYB-11** | Kiểm tra đường truyền với kích thước dữ liệu ứng dụng khác nhau | Không có MTU black-hole, timeout bất thường |
| **HYB-12** | Prefix không được phép xuất hiện từ peer (mô phỏng policy trong lab) | Không được import/quảng bá ngoài source of truth |
| **HYB-13** | VPN tunnel UP nhưng route/cloud SG sai trong bài kiểm thử | Monitoring phát hiện ứng dụng không phục vụ, không chỉ coi tunnel UP là PASS |
| **HYB-14** | Cloud spoke khác thử tới Production DB không có quyền | Deny theo ranh giới đã duyệt |
| **HYB-15** | Khôi phục cấu hình sau bài thử failover | Route, DNS, log, app health và IaC desired state nhất quán |

**Chỉ kiểm tra ping nhỏ là chưa đủ.** ICMP có thể bị chặn; HTTPS/DB có thể lỗi vì MTU, TLS trust, auth hoặc return path. Phải kiểm tra **ứng dụng thật và những luồng bị cấm**.

### Mẫu biên bản nghiệm thu

~~~text
Test ID:                HYB-01
Environment:            [lab / staging / production approved]
Time + timezone:        [timestamp]
Source asset/identity:  [host / role / device posture]
Destination service:    [host / application / CIDR]
Expected path:          [site, tunnel, VRF, cloud route]
Observed path:          [RIB/FIB/flow evidence]
IKE/Child SA status:    [evidence or N/A]
BGP/static routes:      [evidence]
Firewall action:        [allow/deny and rule ID]
DNS resolution:         [resolver, answer]
Application outcome:    [success/fail, latency]
Security expectation:   [least privilege / blocked path]
Result:                 [PASS / FAIL / INCONCLUSIVE]
Evidence/Reviewer:      [ticket, logs, owner]
Rollback if needed:     [approved procedure]
~~~

**INCONCLUSIVE** đúng khi không chứng minh được request đã đi qua tuyến định kiểm tra, log chỉ có một phía hoặc thiếu bằng chứng về firewall/ứng dụng. Không ghi PASS chỉ vì tunnel báo UP.

## 21. Runbook điều tra sự cố VPN hybrid

### Giai đoạn 1 — Tách lớp lỗi

~~~text
Người dùng/API báo lỗi
          |
          +-- DNS không resolve? -> resolver, split DNS, forwarding
          |
          +-- VPN SA không lên? -> peer, IKE, auth, NAT-T, underlay
          |
          +-- SA UP, BGP DOWN? -> peering, selectors, route control plane
          |
          +-- BGP UP, thiếu route? -> filtering, propagation, RIB/FIB
          |
          +-- Route đúng nhưng timeout? -> firewall, NAT, return path, MTU
          |
          +-- TCP/TLS được nhưng app lỗi? -> cert, IAM, backend, DB
~~~

Đây là **sơ đồ gợi ý thứ tự điều tra**, không có nghĩa các lỗi không thể cùng xuất hiện.

### Giai đoạn 2 — Thu thập bằng chứng

1. Timestamp, nguồn/đích, zone, request ID hoặc connection ID nếu có.
2. VPN peer state, IKE SA/Child SA, thương lượng và lỗi rekey gần thời điểm sự cố.
3. Underlay Internet/ISP health, NAT-T và đường đi tới gateway.
4. BGP neighbor, prefix advertised/accepted, route/FIB hai đầu, route chiều về.
5. Firewall deny, NAT translation, IPS, cloud security policy, VPC/VNet route table.
6. DNS resolver/trả lời, VPN client configuration và endpoint posture khi liên quan.
7. Ứng dụng/DB health, trace, TLS certificate và lỗi authorization.

### Giai đoạn 3 — Xác minh và phục hồi an toàn

- Phân loại **tunnel failure, routing failure, policy failure, DNS failure hoặc app failure** dựa vào bằng chứng.
- Xác định thay đổi gần đây từ IaC/cloud API, gateway config, route và certificate.
- Chọn phương án có **phạm vi tác động nhỏ nhất**, đủ log, change owner và rollback.
- Nếu cần failover, bảo đảm đường dự phòng đã được kiểm thử và không bypass firewall/IDS.
- Không mở **0.0.0.0/0 any-any**, tắt xác thực peer hoặc dùng thuật toán yếu để “khôi phục nhanh”.
- Xác nhận **dịch vụ thật** phục hồi từ đúng nguồn, không chỉ kiểm tra một đèn xanh gateway.

### Giai đoạn 4 — Hậu kiểm

Ghi sự cố, thời gian phát hiện/phục hồi, route diff, đường bị ảnh hưởng, log IAM/DNS/app, người phê duyệt, thay đổi đã rollback, bí mật có cần xoay không và kế hoạch ngăn tái diễn. Nếu lỗi phát sinh từ một cấu hình đã được duyệt, cần cập nhật test suite và source of truth.

## 22. Case study: VPN UP nhưng API cloud không truy cập được

**Bối cảnh giả định:** Doanh nghiệp chuyển API sang Cloud Production tại **10.60.20.10**. Kỹ sư thấy hai IPsec tunnel đều UP và BGP Established. Tuy nhiên ứng dụng on-prem **10.20.10.25** gọi API qua HTTPS thường timeout sau khi thay đổi route table cloud.

### Bằng chứng ban đầu

~~~text
VPN gateways:       IPsec tunnel A = UP; tunnel B = UP
BGP sessions:       ESTABLISHED
On-prem RIB:        10.60.0.0/16 via VPN
Cloud hub RIB:      10.20.0.0/16 received
Cloud spoke route:  changed during deployment
Firewall logs:      no conclusive application flow yet
DNS:                api.prod.cloud.example.test -> 10.60.20.10
Client:             HTTPS timeout
Verdict:            routing/policy/MTU/application not yet isolated
~~~

Những dữ liệu này **chưa chứng minh tunnel có vấn đề**. BGP Established chỉ cho biết peer control plane, không bảo đảm spoke route, firewall hoặc đường về đã đúng.

### Những giả thuyết cạnh tranh

1. **Cloud spoke thiếu return route** tới 10.20.0.0/16, hoặc route bị chọn sai next hop.
2. **Cloud firewall/NSG/SG** chặn TCP/443 hoặc response.
3. **Định tuyến bất đối xứng** qua hai tunnel/firewall không chia sẻ state đúng cách.
4. **MTU/PMTUD** khiến gói lớn lỗi trong khi các phép kiểm tra nhỏ thành công.
5. DNS cache trỏ tới IP workload cũ hoặc application endpoint thay đổi.
6. Dịch vụ/API bị lỗi, TLS trust/authorization sai hoặc backend chưa sẵn sàng.

### Quy trình kiểm chứng

1. Xác minh IP DNS và request tới **đúng host, port và ứng dụng**.
2. Xem effective route ở cloud spoke và hub, route on-prem, **chiều đi và chiều về**.
3. Đối chiếu firewall flow logs/rule hit/NAT, xác định gói có đến cloud API không.
4. Kiểm tra TLS/application log ở server; nếu request đã tới app thì tìm lỗi ở lớp đó.
5. Kiểm tra sự khác nhau giữa payload nhỏ/lớn nếu nghi MTU, không chỉ dựa vào ping.
6. Đối chiếu route diff với change ticket; xác định đúng phạm vi tác động.
7. Khôi phục bằng thay đổi đã phê duyệt và kiểm thử lại các đường **ALLOW** lẫn **DENY**.
8. Xác minh tunnel failover và security inspection path sau sửa, không bỏ qua HA.

### Kết luận mẫu

Nếu phát hiện cloud spoke thiếu route trả về qua hub, có thể kết luận **nguyên nhân đã được xác minh ở lớp định tuyến** sau khi bổ sung route theo quy trình và thấy ứng dụng hoạt động trở lại, log hai chiều khớp. Nếu chỉ thấy VPN UP nhưng client timeout, đánh giá đúng là **“chưa xác định nguyên nhân”**, không phải “VPN khỏe nên lỗi chắc do app”.

## 23. Những sai lầm thường gặp

| Hiểu nhầm | Vì sao nguy hiểm hoặc sai | Cách làm đúng |
|---|---|---|
| “Tunnel UP là hybrid network hoạt động” | Route/DNS/ACL/MTU/app có thể lỗi | Kiểm tra RIB/FIB, flow và giao dịch thật |
| “Có VPN thì mọi máy hai phía được tin cậy” | VPN không thay authorization/NAC/app security | Least privilege theo zone, identity và workload |
| “Kết nối riêng chắc chắn đã mã hóa” | Private connectivity có thể chỉ là đường vận chuyển riêng | Xác định yêu cầu IPsec/TLS theo threat model |
| “BGP Established nghĩa route đã đúng” | Prefix có thể bị filter, không selected hoặc không vào FIB | Kiểm tra received/accepted/selected, chiều về |
| “Hai tunnel luôn là HA” | Có thể chung ISP/router/region và cùng lỗi | Phân tích failure domain, thử failover |
| “Allow all giữa hai CIDR giúp vận hành dễ” | Mở lateral movement và vượt segmentation | Rule theo ứng dụng/role, mặc định deny |
| “Cloud và on-prem dùng trùng CIDR không sao” | Route không phân biệt đúng đích | Renumber hoặc translation/VRF có kiểm soát |
| “Chỉ cần route chiều đi” | State return path và NAT có thể làm timeout | Kiểm tra hai chiều và firewall state |
| “Chặn mọi ICMP tăng bảo mật” | Có thể hỏng PMTUD/đường kết nối | Lọc đúng loại và phạm vi cần thiết |
| “Full tunnel luôn tốt hơn split tunnel” | Hairpin, bottleneck và các ngoại lệ khác tạo tradeoff | Chọn theo dữ liệu, policy, thiết bị và SLO |
| “Remote VPN MFA cho phép vào DB trực tiếp” | MFA ở VPN không cấp quyền ứng dụng | Authorization riêng và bastion/app gateway |
| “IPv4 rule đã bảo vệ luôn IPv6” | Dual-stack có thể đi đường khác | Kiểm thử IPv6 route/firewall/DNS |
| “PSK/cert đã cài là không cần quản lý nữa” | Hết hạn, lộ khóa hoặc rekey lỗi gây outage | PKI, lifecycle, alerts, rotation |
| “Traceroute một lần chứng minh toàn bộ path” | ECMP, ICMP policy, tunnel/overlay có thể che hop | Dùng flow, routing telemetry và test đa nguồn |
| “Cloud hub là nơi duy nhất cần firewall” | Spoke/workload có thể có đường khác và policy riêng | Kiểm kê routing + SG/NACL + endpoint |
| “Có change ticket thì mọi route change hợp lệ” | Thay đổi được duyệt vẫn có thể triển khai sai | Desired vs observed + kiểm thử |
| “Đo ping tốt là API tốt” | DNS, TLS, DB, MTU và ứng dụng còn ảnh hưởng | Synthetic transaction và app tracing |

## 24. Câu hỏi tự kiểm tra

1. Vì sao site-to-site VPN và remote-access VPN cần thiết kế chính sách danh tính khác nhau?
2. IPsec/IKEv2, IKE SA, Child SA, ESP và NAT-T đóng vai trò gì?
3. Tại sao có **hai tunnel UP** vẫn chưa chứng minh HA?
4. Vì sao định tuyến tới cloud phải có cả route chiều đi lẫn return route?
5. Route-based và policy-based VPN khác nhau ở điểm nào? Tại sao không thể chỉ chọn bằng tên gọi?
6. Điều gì xảy ra khi on-prem và cloud dùng cùng CIDR **10.10.0.0/16**? Ưu tiên giải pháp nào?
7. BGP Established có chứng minh mọi prefix đã vào FIB không? Cần kiểm tra những tập route nào?
8. Vì sao chỉ quảng bá CIDR được phê duyệt và không tự phát default route qua VPN?
9. Trong topology hub-spoke, traffic bypass hub firewall có thể xuất hiện ở đâu?
10. MFA cho nhân viên remote có đủ để cấp quyền tới mọi subnet cloud không?
11. Full tunnel và split tunnel ảnh hưởng DNS/IPv6 leak, egress visibility và hiệu năng như thế nào?
12. Conditional DNS forwarding giữa on-prem/cloud cần kiểm tra điều gì để tránh loop và timeout?
13. Vì sao ứng dụng HTTPS có thể lỗi với gói lớn trong khi ping nhỏ vẫn chạy?
14. Khi xem SA trạng thái UP nhưng API timeout, nên kiểm tra những lớp nào trước khi thay cấu hình VPN?
15. Một private cloud connection có bảo đảm bí mật dữ liệu end-to-end không? Cần bổ sung điều gì theo threat model?
16. Những tín hiệu nào giúp phát hiện chứng chỉ VPN sắp hết hạn hoặc rekey lỗi?
17. Vì sao một bản cập nhật route table cloud được duyệt vẫn cần regression test cả ALLOW và DENY?
18. Hãy đề xuất một ma trận kiểm thử HA, DNS, IPv6, route leak, policy và application success cho hệ thống hybrid của bạn.

## 25. Ghi nhớ trọng tâm

**Thiết kế VPN hybrid cloud là thiết kế một đường truyền an toàn có vận hành, định tuyến và kiểm soát quyền đầy đủ — không chỉ dựng IPsec tunnel.** Site-to-site VPN, remote-access VPN, ZTNA, private connectivity và hub/spoke có vai trò khác nhau; chọn dựa trên **luồng nghiệp vụ, fault domain, yêu cầu bảo mật và SLO**. Một tunnel an toàn cần xác thực peer, bảo vệ mật mã phù hợp, quản lý khóa, routing chính xác, DNS đúng và điểm thực thi firewall/identity rõ ràng.

Mạng hybrid vững chắc phải có **IPAM/CIDR không chồng lấn, BGP/static route có lọc, return path, HA thực sự độc lập, bảo vệ IPv4/IPv6, DNS hybrid, phân đoạn và quyền tối thiểu**. Người dùng từ xa cần **MFA, posture và quyền theo ứng dụng**, không mặc nhiên được vào toàn mạng. Vận hành cần theo dõi **IKE/SA, BGP, FIB/flow, DNS, firewall, latency và giao dịch ứng dụng**, có IaC/change management, kiểm thử failover, rotation, MTU và rollback. Chỉ coi bài toán hoàn thành khi **traffic hợp lệ đi đúng đường và hoạt động**, còn **traffic ngoài quyền bị chặn** theo bằng chứng từ cả mạng lẫn ứng dụng.
