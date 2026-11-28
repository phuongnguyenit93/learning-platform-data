# Kiểm thử đường đi dự phòng trong Routing Security

**Kiểm thử đường đi dự phòng (backup-path / failover testing)** là quá trình xác minh rằng khi đường mạng chính bị lỗi, suy giảm hoặc được bảo trì, hệ thống có thể **chuyển lưu lượng sang một đường đã được phê duyệt**, duy trì mức dịch vụ mong muốn, rồi khôi phục có kiểm soát khi đường chính hoạt động trở lại. Điều cần kiểm chứng không chỉ là “có tuyến dự phòng trong bảng định tuyến”, mà là **đường đó thực sự sử dụng được, không làm mất chính sách bảo mật và có bằng chứng đo được về thời gian gián đoạn**.

Trong chương **Routing security** của học phần **SECURITY_NETWORK_SECURITY**, đường đi dự phòng liên quan trực tiếp đến phân đoạn mạng, firewall stateful, VPN, IDS/IPS, DNS, cloud networking và an toàn control plane. Một hệ thống có hai ISP hoặc hai router vẫn có thể mất mạng nếu dùng chung một điểm lỗi, next-hop không reachable, quảng bá route sai, đường phản hồi bất đối xứng, NAT thay đổi hoặc firewall dự phòng chưa có chính sách giống đường chính.

Bài học trình bày mô hình dự phòng, cơ chế hội tụ tuyến, các kiểu sự cố, quy trình kiểm thử có kiểm soát, phương pháp đo thời gian, kiểm tra an toàn tuyến, các tình huống lab và checklist vận hành. Ví dụ dùng địa chỉ private/dải dành cho tài liệu, không đại diện hạ tầng thực tế. **Mọi thao tác có thể làm gián đoạn traffic phải được thực hiện trong lab hoặc theo change window đã phê duyệt.**

## 1. Mục tiêu học tập

Hoàn thành bài này, người học có thể:

1. Phân biệt **đường chính**, **đường dự phòng**, **failover**, **failback**, **convergence** và **high availability (HA)**.
2. Giải thích sự khác nhau giữa **RIB/FIB**, route preference, next-hop reachability và kết nối ứng dụng.
3. Liệt kê cơ chế dự phòng dùng static route, dynamic routing, VRRP/HSRP, ECMP, BFD, SD-WAN, VPN và cloud network.
4. Phân loại lỗi vật lý, lỗi next-hop, mất upstream, blackhole, lỗi chính sách, lỗi control plane và lỗi tầng ứng dụng.
5. Thiết kế ma trận kiểm thử cả **đường đi**, **đường về**, **policy allow/deny**, **IPv4/IPv6** và **VPN/cloud** khi failover.
6. Đo được thời gian phát hiện lỗi, hội tụ, gián đoạn gói, mất session, p95/p99 latency và khả năng hoàn thành giao dịch.
7. Nhận diện rủi ro routing security như route injection, giả mạo adjacency, route leak, misconfiguration hoặc đường dự phòng bỏ qua firewall.
8. Viết báo cáo kiểm thử có baseline, bằng chứng, tiêu chí đạt/không đạt, rollback và trách nhiệm rõ ràng.

## 2. Đường chính và đường dự phòng là gì?

Giả sử một công ty có hai đường Internet:

- **Primary path:** đi qua ISP-A, được ưu tiên khi trạng thái bình thường.
- **Backup path:** đi qua ISP-B, được sử dụng khi điều kiện failover đáp ứng.
- **Gateway/firewall nội bộ:** chọn đường ra và áp chính sách.
- **Ứng dụng quan trọng:** cần duy trì HTTPS, VPN hoặc kết nối tới dịch vụ cloud.

~~~mermaid
flowchart LR
    U[User / LAN] --> FW[Firewall hoặc Edge Router]
    FW -->|Primary| A[ISP-A]
    FW -->|Backup| B[ISP-B]
    A --> NET[Internet / Cloud Service]
    B --> NET
    FW -.Telemetry.-> OBS[Routing, firewall & SLO monitoring]
~~~

**Có hai đường được vẽ không chứng minh có hai đường độc lập.** ISP-A và ISP-B có thể dùng cùng ống cáp, thiết bị truy nhập, nguồn điện, router biên hoặc tuyến metro; sự cố chung vẫn làm cả hai mất kết nối. Kiểm thử dự phòng phải xét **shared fate / shared risk**.

### 2.1. Các khái niệm quan trọng

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Primary route** | Tuyến được lựa chọn theo chính sách trong trạng thái bình thường | Default route qua ISP-A |
| **Backup route** | Tuyến chỉ được chọn hoặc có thể sử dụng khi điều kiện phù hợp | Default route qua ISP-B với preference thấp hơn |
| **Failover** | Chuyển traffic khỏi đường gặp vấn đề | WAN-A mất reachability, traffic sang WAN-B |
| **Failback** | Quay về đường ưu tiên sau khi phục hồi | Route qua ISP-A được dùng lại sau health ổn định |
| **Convergence** | Các thiết bị/hệ thống cập nhật thông tin và hành vi forwarding đủ để sử dụng đường mới | BGP/OSPF cập nhật RIB/FIB |
| **ECMP** | Nhiều next-hop cùng chi phí được dùng đồng thời theo cơ chế forwarding | Chia luồng giữa hai đường |
| **Control plane** | Học, chọn, quảng bá tuyến và duy trì adjacency | OSPF, BGP, routing policy |
| **Data plane** | Chuyển tiếp packet theo quyết định forwarding | FIB, neighbor resolution, ASIC/OS forwarding |
| **Blackhole** | Traffic được gửi vào đường không chuyển đến đích | Default route còn nhưng upstream ngừng forward |
| **Asymmetric routing** | Hai chiều traffic đi qua các đường khác nhau | Request đi firewall A, response qua firewall B |

Điểm mấu chốt của bài là **route tồn tại ≠ đích reachable ≠ ứng dụng hoạt động**. Cần kiểm thử đủ ba lớp.

### 2.2. RIB và FIB

- **RIB (Routing Information Base):** tập thông tin tuyến và các route được chọn theo chính sách/protocol.
- **FIB (Forwarding Information Base):** dữ liệu forwarding được thiết bị dùng để quyết định next-hop cho packet.
- **Neighbor/adjacency state:** thông tin L2/L3 cần để gửi packet tới next-hop, ví dụ ARP hoặc IPv6 Neighbor Discovery.

Một route có thể được nhìn thấy trong RIB nhưng forwarding chưa được cài đặt đúng, next-hop chưa resolve, interface down hoặc một ACL khác chặn. Vì vậy cần đọc trạng thái forwarding và thử luồng trên đường mạng thực.

## 3. Điều gì phải tồn tại để dự phòng thật sự hoạt động?

Có thể hình dung đường dự phòng qua các lớp:

~~~text
Service / user transaction thành công?
             ^
             |
Backend, DNS, TLS, auth, VPN có hoạt động?
             ^
             |
Firewall, NAT, ACL, route chiều về có hợp lệ?
             ^
             |
Router chọn đúng next-hop, FIB được cập nhật?
             ^
             |
Routing adjacency, gateway health, link hoạt động?
             ^
             |
Cáp, nguồn, thiết bị và upstream có độc lập?
~~~

Đường dự phòng nên được thiết kế và kiểm chứng ở **từng lớp có thể gây lỗi**.

### 3.1. Các điều kiện tối thiểu

1. **Tuyến được quảng bá/cấu hình chính xác:** destination prefix, next-hop, VRF, metric/preference và policy route.
2. **Next-hop thực sự tới được:** neighbor và đường L2/L3 không bị đứt.
3. **Đường tới đích và về nguồn tồn tại:** đặc biệt khi hai ISP, VPN hoặc firewall khác nhau.
4. **Chính sách bảo mật tương đương:** các zone, subnet, source/destination/port, IPS và egress rule không bị mở quá mức.
5. **NAT/tunnel/identity phù hợp:** tránh thiếu SNAT/port mapping, IPsec/IKE state hoặc VPN authorization.
6. **Phụ thuộc hoạt động:** DNS, PKI, NTP, cloud/private endpoint, health check và monitoring dùng được qua backup.
7. **Năng lực đủ:** backup chịu được tải quan trọng hoặc có cơ chế giảm tải ưu tiên nghiệp vụ.
8. **Quy trình vận hành:** phát hiện, kiểm tra, rollback, failback, owner và nhật ký.

### 3.2. Backup có thể mang ít tải hơn primary

Không phải lúc nào WAN dự phòng cũng có công suất bằng WAN chính. Thiết kế phải ghi rõ:

- Những dịch vụ **bắt buộc** được duy trì.
- Những dịch vụ có thể **degrade** có kiểm soát.
- Giới hạn băng thông, kết nối và số user VPN còn phục vụ.
- Cơ chế ưu tiên QoS/traffic shaping theo chính sách.
- Tiêu chí SLO và trách nhiệm khi backup chỉ đáp ứng một phần.

**Đừng đánh dấu PASS chỉ vì một ping nhỏ đi được qua backup** nếu luồng ứng dụng quan trọng mất kết nối hoặc backup không đủ năng lực cho tải được cam kết.

## 4. Phân loại sự cố mà failover cần xử lý

Một bài test tốt cần nhiều kiểu lỗi thay vì chỉ “rút dây WAN”.

| Kiểu lỗi | Điều có thể xảy ra | Test cần xác minh |
|---|---|---|
| **Physical link down** | Interface mất carrier, router có thể loại tuyến trực tiếp | Đường backup có được chọn, ứng dụng phục hồi? |
| **Next-hop router mất** | Link local còn up nhưng gateway không forward | Health tracking/BFD/dynamic routing có phát hiện? |
| **Upstream blackhole** | Gateway trả lời nhưng mạng phía sau không đến đích | Probe nhiều điểm và end-to-end SLI có phát hiện? |
| **Routing adjacency down** | OSPF/BGP neighbor mất, route bị withdraw/đổi | RIB/FIB và upstream/downstream hội tụ ra sao? |
| **Sai route advertisement/policy** | Route không hợp lệ hoặc hướng ra không mong đợi | Prefix filter, priority, route maps và cảnh báo |
| **Asymmetric return path** | Gói đi về qua hai firewall khác nhau | Stateful sessions, NAT, return ACL có hoạt động? |
| **Firewall/cluster failover** | Thiết bị bảo mật chủ động mất | Session/state sync và policy đồng bộ hay không? |
| **VPN tunnel down** | Overlay mất dù underlay vẫn lên | Tunnel backup, route advertisement và authentication |
| **DNS/service discovery lỗi** | Route vẫn ổn nhưng hostname không phân giải | Resolver dự phòng, split DNS, cache, TLS |
| **Cloud zone/service failure** | Gateway/NAT/LB hoặc một AZ mất | Route/endpoint/instance ở AZ khác đủ điều kiện? |
| **Capacity failure** | Backup lên nhưng bão hòa | Loss, throughput, latency và business success |
| **Flapping/intermittent loss** | Đường nhảy qua lại liên tục | Hold-down, damping/hysteresis và cảnh báo |

**Lỗi không mất carrier (partial failure)** rất quan trọng. Đường truyền có thể vẫn báo “up” nhưng packet loss cao, DNS timeout hoặc một nhóm prefix không reachable. Một cơ chế chỉ dựa vào trạng thái vật lý sẽ không xử lý được mọi trường hợp đó.

## 5. Các cơ chế dự phòng trong routing

### 5.1. Static route và route ưu tiên thứ cấp

Một hệ thống nhỏ có thể dùng default route qua WAN-A và một **floating static route** qua WAN-B có ưu tiên thấp hơn. Khi primary không còn đủ điều kiện lựa chọn, secondary mới được sử dụng.

~~~text
Mô hình logic (không phải cú pháp vendor):

Destination: 0.0.0.0/0
Primary next-hop: ISP-A gateway, ưu tiên cao
Backup next-hop: ISP-B gateway, ưu tiên thấp

Khi primary không còn hợp lệ:
  -> route qua ISP-B có thể trở thành tuyến được chọn
~~~

**Hạn chế:** nếu interface WAN-A vẫn up và next-hop vẫn reachable nhưng phía upstream bị blackhole, primary static route có thể tiếp tục tồn tại. Trong tình huống này cần **route tracking hoặc health monitoring** phù hợp với nền tảng, không chỉ route preference.

Không dựa vào tên thông số “metric” giữa các hệ thống để so sánh: **administrative distance, route preference, metric, priority** có ý nghĩa và thứ tự lựa chọn khác nhau theo OS/vendor.

### 5.2. OSPF/IS-IS và hội tụ nội bộ

Các giao thức IGP như OSPF hoặc IS-IS có thể phân phối thông tin topology và tính lại đường khi link hoặc adjacency thay đổi. Tính sẵn sàng phụ thuộc vào:

- Neighbor/adjacency detection.
- Timers và phạm vi mạng.
- SPF calculation, cập nhật RIB/FIB.
- Khả năng fast reroute hoặc các tối ưu được hỗ trợ.
- Chính sách route summarization, filtering và security.
- Năng lực data plane và dịch vụ ở đích.

**OSPF có route dự phòng không tự chứng minh ứng dụng sẽ không gián đoạn.** TCP session, NAT và firewall state có thể chịu ảnh hưởng trong thời gian hội tụ.

### 5.3. BGP và đường Internet/đa nhà mạng

BGP dùng **policy và thuộc tính đường** để chọn/quảng bá route; không nên giản lược thành “chọn đường ngắn nhất”. Với hai ISP, cần xem:

- Quảng bá và nhận những **prefix được phép**.
- Local preference, AS path và chính sách outbound/inbound theo thiết kế.
- eBGP/iBGP session health, BFD nếu sử dụng.
- Default route so với full routing table.
- Return traffic và địa chỉ nguồn public khi đổi ISP.
- Giới hạn routes, cơ chế lọc và kiểm soát prefix bị quảng bá sai.
- Thời gian hội tụ ở mạng của **đối tác/upstream**, không chỉ trên router doanh nghiệp.

Nếu doanh nghiệp chỉ có NAT public IP thuộc một ISP, chuyển outbound sang ISP thứ hai có thể làm đổi public source IP. **TCP session đang mở có thể không tiếp tục được**, và traffic inbound tới public IP của ISP-A không tự chuyển được sang ISP-B.

### 5.4. ECMP: nhiều đường dùng đồng thời

**Equal-Cost Multi-Path (ECMP)** có thể chia các flow lên nhiều next-hop có chi phí tương đương, dựa trên hash 5-tuple hoặc cơ chế riêng. Khi một next-hop mất:

- Một số flow có thể được ánh xạ sang next-hop khác.
- Lưu lượng tập trung có thể làm bão hòa đường còn lại.
- Ứng dụng có thể bị gián đoạn nếu NAT hoặc stateful device thay đổi.
- Đường đi của **một flow** không nhất thiết giống đường của flow khác, kể cả cùng source/destination.

Không dùng một phép traceroute đơn lẻ để khẳng định tất cả traffic dùng cùng path trong môi trường ECMP.

### 5.5. FHRP: VRRP và HSRP

Các cơ chế **First-Hop Redundancy Protocol (FHRP)** như **VRRP** hoặc HSRP (đặc thù một số hệ sinh thái) cung cấp gateway ảo để client không phải thay cấu hình default gateway khi router active hỏng.

~~~text
Client --> Virtual Gateway IP/MAC
                    |
         Router A (active)
         Router B (standby)

Khi A không còn active:
  B có thể tiếp quản gateway ảo theo cơ chế FHRP
~~~

**VRRP/HSRP giải quyết dự phòng default gateway tại first hop, không tự thay thế định tuyến end-to-end, firewall cluster state synchronization hoặc bảo vệ đường Internet.** Gateway mới vẫn phải có route và policy phù hợp; cần kiểm thử cả khả năng phát hiện trạng thái chuyển đổi lẫn đường phản hồi.

### 5.6. BFD và cơ chế phát hiện nhanh

**Bidirectional Forwarding Detection (BFD)** là cơ chế phát hiện sự cố forwarding giữa các điểm tham gia, thường tích hợp với OSPF/BGP hoặc route tracking tùy thiết bị.

BFD có thể rút ngắn thời gian phát hiện so với các timers mặc định, nhưng:

- BFD chỉ đánh giá đường/phiên mà nó giám sát, không bảo đảm **ứng dụng ở đích** vẫn khỏe.
- Timers quá nhạy trên đường không ổn định có thể gây **false failover hoặc flapping**.
- BFD cần được bảo vệ bằng điều kiện neighbor/session thích hợp và cơ chế authentication nếu nền tảng hỗ trợ và chính sách yêu cầu.
- **Fast failure detection không đồng nghĩa fast end-to-end recovery** nếu RIB/FIB, NAT, firewall hoặc DNS chưa sẵn sàng.

### 5.7. SD-WAN và path health

SD-WAN thường theo dõi packet loss, latency, jitter và khả năng tới các điểm probe để chọn đường theo chính sách ứng dụng. Các overlay tunnel có thể dùng nhiều WAN và tự chuyển traffic.

Cần đọc chính xác **đối tượng probe, tần suất, ngưỡng, hysteresis, SLA và loại ứng dụng**. Một tunnel báo up không chứng minh API bên trong tunnel hoàn thành request. Nên kết hợp synthetic transactions và telemetry application.

## 6. Routing security trong quá trình failover

Failover phải giữ **đường đi an toàn**, không chỉ đường đi còn hoạt động.

### 6.1. Chính sách tuyến và điểm tin cậy

Các nhóm rủi ro:

- **Route injection:** một neighbor hoặc nguồn cấu hình gửi route trái phép.
- **Route leak:** prefix được quảng bá sang phạm vi không mong muốn do policy lỗi.
- **Route hijack:** mạng khác quảng bá route khiến traffic bị thu hút/chuyển hướng.
- **Misconfiguration:** default route, prefix hoặc next-hop trỏ sai, gây blackhole hay bỏ qua firewall.
- **Unauthorized adjacency:** thiết bị không được phép tham gia routing domain.
- **Control-plane exhaustion:** nhiều update/session hoặc lỗi phần mềm làm routing process quá tải.

Một đường backup có thể bị chọn vì route độc hại/không được phê duyệt được coi “tốt hơn” theo chính sách. Vì thế kiểm thử phải xác minh **tuyến được chọn thuộc tập đường được phép**, không chỉ kiểm tra reachability.

### 6.2. Các kiểm soát nên xét

| Kiểm soát | Mục tiêu | Giới hạn |
|---|---|---|
| Neighbor authentication khi protocol hỗ trợ | Hạn chế tạo routing adjacency không hợp lệ | Không thay thế lọc route sau khi neighbor được tin |
| Prefix/route filtering | Chỉ nhận/quảng bá prefix được cấp phép | Sai policy vẫn có thể cho route ngoài phạm vi |
| Maximum-prefix / route limits | Hạn chế tăng đột biến bảng route | Cần ngưỡng phù hợp và xử lý khi vượt |
| BGP communities / policy review | Diễn đạt chính sách định tuyến có kiểm soát | Community chỉ có ý nghĩa khi các bên thực thi đúng |
| RPKI Route Origin Validation | Giúp xác minh origin AS đối với BGP prefix có thông tin ROA phù hợp | Không tự xác minh toàn bộ AS_PATH và không ngăn mọi route leak |
| Route change monitoring | Phát hiện default/prefix/next-hop thay đổi bất thường | Cần baseline và điều tra ngữ cảnh |
| ACL/control-plane protection | Giới hạn traffic tới management/routing plane | Cần không chặn nhầm neighbor hoặc giao thức thiết yếu |
| IAM/RBAC/change control | Bảo vệ quyền sửa router, cloud routes, firewall và SD-WAN policy | Quyền thừa có thể vô hiệu tất cả các kiểm soát khác |

**RPKI ROA và Route Origin Validation chỉ giải quyết một phần bài toán bảo mật BGP.** Một route có origin hợp lệ chưa chắc đường AS-level hoặc chính sách transit đều mong muốn. Kiểm soát lọc, giám sát và quản trị đối tác vẫn cần thiết.

### 6.3. Đường dự phòng không được bypass firewall

Giả sử khi đường chính hoạt động, traffic Staff → Database đi qua firewall liên vùng và bị deny. Nếu backup route dẫn packet thẳng từ Staff vào Data subnet qua một router khác không có ACL, failover có thể **mở ra quyền mà đường chính không có**.

~~~mermaid
flowchart LR
    STAFF[Staff subnet] --> FW[Firewall liên vùng]
    FW -->|Luồng được kiểm soát| DATA[Data subnet]
    STAFF -.Backup route sai.-> BYPASS[Router không có policy]
    BYPASS -.Truy cập không mong muốn.-> DATA
~~~

Trong test failover cần kiểm thử **positive cases** (luồng nghiệp vụ được phép vẫn chạy) và **negative cases** (luồng bị cấm vẫn bị từ chối), đặc biệt với Management, Data, Backup và Guest.

## 7. Threat model của một kiến trúc có đường dự phòng

Một tình huống giả định:

- Công ty có hai edge router kết nối ISP-A/ISP-B.
- App server cần gọi DB qua firewall nội bộ.
- VPN admin truy cập jump host.
- Có DNS nội bộ và hệ thống giám sát.
- Một actor không được phép có thể thử sửa route/cloud policy hoặc giả traffic định tuyến trong một đoạn mạng.

Các câu hỏi:

1. Đối thủ **ở đâu**: Internet, LAN, VPN, cloud IAM, router quản trị hay thiết bị ISP?
2. Đối thủ **điều khiển gì**: route announcement, BGP neighbor, config API, DNS, NAT hay chỉ gửi packet tới ứng dụng?
3. Điểm nào là **single point of failure** dù nhìn có nhiều đường?
4. Trong failover, traffic có rời khỏi zone/firewall/IPS dự kiến không?
5. Backup interface có nhận những prefix được cấp phép không?
6. Lưu lượng phản hồi có đi qua stateful device tương ứng không?
7. Ai có quyền **trigger, approve, rollback** và xem logs?
8. Alert nào sẽ báo một route được chọn ngoài baseline hoặc thay đổi trái lịch?
9. Nếu backup còn ít công suất, nghiệp vụ quan trọng nào được ưu tiên?

**Đừng dùng route failover như một cơ chế tin cậy người dùng.** Việc packet đi qua WAN-B không có nghĩa source có thêm quyền. Identity, VPN authorization, application auth và firewall policy vẫn phải thực thi.

## 8. Định nghĩa tiêu chí thành công trước khi kiểm thử

Nếu chỉ viết “sau khi rút dây, ping lại được” thì tiêu chí thiếu rõ ràng. Một kế hoạch test nên ghi:

| Thành phần | Chỉ số | Câu hỏi |
|---|---|---|
| **Detection time** | Từ khi lỗi bắt đầu đến khi cơ chế health nhận lỗi | Link tracking, BFD hay probe phản ứng khi nào? |
| **Routing convergence** | Thời điểm FIB và next-hop cập nhật tới đường mới | Các router liên quan đã đồng thuận đủ chưa? |
| **Packet loss** | Số packet/transaction mất trong cửa sổ thử | Có microloop, blackhole hoặc MTU issue không? |
| **Application recovery** | Từ khi lỗi đến khi giao dịch hợp lệ thành công ổn định | User mất dịch vụ trong bao lâu? |
| **Session continuity** | Các phiên TCP/TLS/VPN đang mở còn sống không? | Có cần reconnect/reauthenticate không? |
| **Latency/jitter** | p50/p95/p99 và biến động trên backup | Backup có đáp ứng nghiệp vụ realtime không? |
| **Throughput/capacity** | Mức tải có thể phục vụ an toàn | Backup có bị nghẽn khi dồn traffic? |
| **Policy parity** | Các luồng allow/deny đúng như baseline | Có bỏ qua firewall, thay đổi NAT/ACL không? |
| **Failback behavior** | Thời gian và độ ổn định khi quay lại primary | Có flap hoặc session drop thứ hai không? |
| **Observability** | Sự kiện có xuất hiện ở log/router/SIEM/APM | Có đủ bằng chứng dựng timeline không? |

### 8.1. Tách các mốc thời gian

Một mô hình khái niệm:

\[
T_{\text{app recovery}} \approx
T_{\text{detection}} +
T_{\text{route update}} +
T_{\text{session/application recovery}}
\]

Các pha có thể **chồng lấn**, nên không coi đây là công thức cộng chính xác cho mọi kiến trúc. Một router có thể chuyển FIB rất nhanh nhưng ứng dụng vẫn mất thời gian timeout/retry hoặc thiết lập TLS session mới.

### 8.2. SLI/SLO và RTO

- **SLI:** phép đo thực tế như tỷ lệ request thành công hoặc p99 latency khi failover.
- **SLO:** mục tiêu như tỷ lệ request hợp lệ hoàn tất trong khoảng thời gian giám sát.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để dịch vụ phục hồi sau sự cố, cần định nghĩa mốc đầu/cuối.
- **RPO (Recovery Point Objective):** lượng dữ liệu có thể mất trong phục hồi dữ liệu; **không trực tiếp là thời gian hội tụ tuyến**.

Một bài test routing có thể đạt “FIB hội tụ dưới ngưỡng” nhưng **không đạt SLO ứng dụng** nếu DB TCP session bị reset hoặc DNS không hoạt động. Đánh giá phải dựa vào tiêu chí đã xác định trước, không đổi ngưỡng sau khi có kết quả.

## 9. Giới hạn phạm vi và an toàn trước khi test

**Tắt interface hoặc rút dây trên mạng sản xuất có thể ảnh hưởng người dùng thật.** Việc thử đường dự phòng là thay đổi có nguy cơ, cần quản lý:

1. Xác định **chủ sở hữu hệ thống và quyền thử nghiệm**.
2. Ghi chính xác router, interface, peer, VRF, prefix, dịch vụ và đường backup.
3. Chọn **lab/staging** hoặc change window được phê duyệt.
4. Kiểm tra backup thực sự sẵn sàng trước khi làm primary lỗi.
5. Chuẩn bị cách thu hồi test và truy cập quản trị **out-of-band** nếu mất mạng.
6. Có người theo dõi ứng dụng, NOC/SOC và đối tác ISP/cloud cần thiết.
7. Đặt điểm dừng nếu error budget, mất gói hoặc người dùng bị ảnh hưởng quá ngưỡng.
8. Bảo vệ log, timestamp và dữ liệu packet capture theo phạm vi quyền.
9. Thông báo các nhóm liên quan và chuẩn bị phương án khôi phục.
10. Chỉ thực hiện **thay đổi gây lỗi** sau khi các điều kiện kiểm soát đã đạt.

Trong tài liệu học tập có thể thiết kế scenario và ma trận test mà **không cần chạy lệnh shutdown hoặc sửa route thật**. Thực hành đọc trạng thái và kiểm thử traffic nhỏ trong lab thường đủ để học nguyên lý trước.

## 10. Baseline cần thu thập trước failover

Trước sự kiện, cần chụp trạng thái của **routing control plane**, **data plane**, **security path** và **application**.

### 10.1. Baseline control plane

- Running routing config và phiên bản/ID thay đổi được phê duyệt.
- Các BGP/OSPF/IS-IS neighbor đang up và prefixes được nhận/quảng bá.
- Bảng route RIB/FIB cho những prefix quan trọng, default route và VRF.
- Metric/route preference, policy, communities, route maps và filtering.
- BFD session health, FHRP role, SD-WAN SLA state.
- Interface status, counters, next-hop/neighbor table.
- Cloud route table, transit gateway/peering/VPN attachment nếu có.

### 10.2. Baseline data plane và chính sách

- Luồng **Staff → Web HTTPS**, **App → DB**, **VPN → Jump host** được phép.
- Luồng **Guest → DB**, **Internet → Management** phải bị chặn.
- Điểm thực thi firewall/NAT, rule ID, security group/network ACL và logging.
- Trạng thái TCP session/firewall HA sync nếu hệ thống hỗ trợ quan sát.
- Địa chỉ public/source NAT và reverse route.
- MTU/PMTUD, IPv4/IPv6 routing và các overlay tunnel đang sử dụng.

### 10.3. Baseline ứng dụng

- Synthetic HTTPS/API transaction từ các vị trí khách hàng được cấp quyền.
- DNS lookup của tên public và private qua resolver chính và dự phòng.
- VPN authentication/tunnel/route health.
- p95/p99 latency, error rate, packet loss và throughput theo đường.
- Database connectivity, TLS verification và các yêu cầu nghiệp vụ.
- Log forwarding tới SIEM, APM và monitoring system.

**Một ứng dụng có lỗi sẵn trước test phải được ghi lại**; nếu không, sự cố có thể bị gán nhầm cho failover.

## 11. Ma trận kiểm thử failover chuẩn

Ví dụ dùng hai WAN và một hệ thống App–DB. Mỗi hàng phải có **test ID, phạm vi, sự kiện giả lập, đường kỳ vọng, kết quả application và bằng chứng**.

| Test | Điều kiện | Hành vi mong đợi | Kiểm chứng chính |
|---|---|---|---|
| F01 | Trạng thái bình thường | Primary được chọn theo policy | Route/FIB, traffic path, app success |
| F02 | Primary link lỗi trong lab | Backup được chọn, dịch vụ phục hồi trong mục tiêu | Health log, convergence, HTTPS transaction |
| F03 | Gateway primary không forward nhưng link up | Health tracking phát hiện và tránh blackhole | Probe/route change, data-plane test |
| F04 | Routing neighbor primary mất | Route withdraw/đổi hợp lệ | BGP/OSPF state, RIB/FIB, ứng dụng |
| F05 | Backup path packet loss/latency cao | Cảnh báo/degrade theo chính sách | SLA monitor, p95/p99, loss |
| F06 | WAN primary trở lại | Failback ổn định, không loop/flap | Hold-down, FIB, app SLO |
| F07 | Traffic đi WAN-B | NAT/public source và return path chính xác | NAT log, firewall state, public endpoint |
| F08 | Guest cố tới DB khi dùng backup | Vẫn bị deny | Firewall deny tại đường backup |
| F09 | App hợp lệ tới DB qua backup | Vẫn được phép | TCP connect + DB/application auth |
| F10 | VPN tunnel primary lỗi | Backup tunnel/route phù hợp | IKE/IPsec state, user transaction |
| F11 | IPv6 primary lỗi riêng | IPv6 dự phòng xử lý theo chính sách | IPv6 RIB/FIB, traceroute6, app |
| F12 | DNS resolver/đường DNS primary lỗi | Resolver được phép vẫn phân giải | DNS logs, split DNS, TLS, TTL |
| F13 | Một cloud AZ/attachment không sẵn sàng trong lab | Đường phù hợp qua AZ khác | Cloud route, SG/NACL, app success |
| F14 | ECMP member bị loại trong lab | Flow được chuyển và còn capacity | FIB/flow, loss, hash behavior |
| F15 | Sensor/collector mất kết nối | Phát hiện mất telemetry, không tuyên bố PASS giả | Health alert, log pipeline |
| F16 | Route/prefix không được cấp phép xuất hiện | Policy từ chối hoặc alert theo thiết kế | Route filters, audit, policy evidence |

**Một test không chạy không được ghi PASS.** Có thể đánh dấu “NOT_RUN”, “BLOCKED”, “FAILED”, “PASSED” kèm lý do và bằng chứng.

### 11.1. Positive và negative testing

**Positive:** một đường nghiệp vụ hợp lệ hoạt động khi primary lỗi, như App → DB TCP/5432, client → API HTTPS/443, admin VPN → jump host theo role.

**Negative:** đường không được phép **vẫn bị chặn** trong trạng thái dự phòng, như Guest → DB hoặc workload không có quyền → Management. Đây là tiêu chí đặc biệt quan trọng của Routing security: failover không tạo một đường bypass cho lateral movement.

### 11.2. Kiểm tra chiều đi và chiều về

Với TCP/UDP, một kết nối có **5-tuple** (source IP/port, destination IP/port, protocol) và traffic phản hồi theo hướng đảo chiều. Trong hệ thống có stateful firewall, NAT, ECMP hoặc WAN song song, đường về khác đường đi có thể khiến state không khớp.

Cần đối chiếu cả:
- Client/source và firewall outbound.
- Đường vào destination.
- Firewall/NAT ở chiều trả lời.
- Route ngược về source, gồm policy route và VRF.
- Listener, TLS/DB auth và kết quả ứng dụng.

## 12. Thực hành quan sát routing không thay đổi cấu hình

Những lệnh sau **chỉ đọc trạng thái** trên host được phép quản trị. Không phải phép thử failover gây gián đoạn.

### 12.1. Linux

~~~bash
# Xem bảng route IPv4 và IPv6
ip -4 route show
ip -6 route show

# Xem route mà Linux dự kiến dùng để tới một địa chỉ private
ip route get 10.20.30.15

# Xem các rule policy routing
ip rule show

# Xem địa chỉ/interface/neighbor
ip -br addr
ip neigh show

# Theo dõi các sự kiện route thay đổi; dừng bằng Ctrl+C
ip monitor route
~~~

**Lưu ý:** output của **ip route get** cho biết quyết định route trên máy tại thời điểm hỏi, không chứng minh packet đã đi hết tới đích, không thể kiểm tra firewall trung gian hay health ứng dụng. Nếu ứng dụng dùng một source IP, namespace hoặc routing table khác, kết quả có thể khác.

### 12.2. Windows PowerShell

~~~powershell
# Xem route và interface
Get-NetRoute |
  Select-Object DestinationPrefix, NextHop, RouteMetric, InterfaceIndex

Get-NetAdapter |
  Select-Object Name, Status, InterfaceDescription

Get-NetIPConfiguration

# Phép thử kết nối chủ động nhỏ: chỉ dùng với đích được cấp phép
Test-NetConnection -ComputerName 10.20.30.15 -Port 5432
~~~

Test-NetConnection kiểm tra khả năng kết nối mạng tới một port TCP; nó **không chứng minh** kết nối DB đã được xác thực hoặc ứng dụng hoàn thành giao dịch. Đừng tự chạy tới các endpoint ngoài quyền kiểm tra.

### 12.3. Lệnh đọc trên router/firewall

Một số nền tảng có các lệnh mang tên tương tự:

~~~text
show ip route
show ipv6 route
show bgp summary
show ip ospf neighbor
show interfaces
show logging
show redundancy
~~~

Đây là **tên lệnh tham khảo mang tính vendor-specific**, không phải tất cả đều có trên mọi thiết bị. Hãy dùng lệnh read-only và quyền phù hợp với router/firewall cụ thể; xem thêm FIB/forwarding và VRF nếu platform có giao diện đọc riêng.

### 12.4. Traceroute và ping có thể gây ngộ nhận

- **ping:** cho biết phản hồi ICMP theo cấu hình, không mặc nhiên phản ánh HTTPS/DB.
- **traceroute/tracepath:** quan sát các hop có phản hồi phù hợp; hop có thể ẩn, rate-limit hoặc không gửi ICMP time exceeded.
- **ECMP:** các probe có 5-tuple khác nhau có thể đi qua nhiều đường.
- **MPLS/tunnel:** đường dưới có thể không hiển thị hết.
- **Firewall:** có thể chặn riêng ICMP/traceroute nhưng vẫn cho ứng dụng.

Vì vậy không dùng một traceroute thiếu hop để khẳng định một tuyến bị mất. Kết hợp route/FIB, interface counters, flow logs và kiểm tra ứng dụng.

## 13. Giám sát convergence theo timeline

Một bài test cần đồng bộ mốc thời gian để giải thích các giai đoạn.

~~~mermaid
flowchart LR
    T0["T0: lỗi bắt đầu"] --> T1["T1: health phát hiện"]
    T1 --> T2["T2: route/FIB thay đổi"]
    T2 --> T3["T3: packet theo backup"]
    T3 --> T4["T4: giao dịch ứng dụng phục hồi"]
    T4 --> T5["T5: failback được kiểm chứng"]
~~~

### 13.1. Bảng ghi thời điểm minh họa

Các số dưới đây là **giả lập cho bài tập**, không phải kết quả đo từ hệ thống thật.

| Mốc | Thời điểm minh họa | Diễn giải |
|---|---|---|
| T0 | 10:00:00.000 | Test harness ghi nhận sự kiện lỗi ở lab |
| T1 | 10:00:00.650 | Health tracking báo primary unavailable |
| T2 | 10:00:01.200 | Router ghi nhận route backup được chọn |
| T3 | 10:00:01.350 | Flow mới được quan sát qua WAN-B |
| T4 | 10:00:02.100 | Synthetic HTTPS transaction thành công liên tiếp |
| T5 | Sau khi primary phục hồi và ổn định | Hoàn thành failback theo kế hoạch, ghi mốc riêng |

Từ dữ liệu giả lập:
- Detection interval từ T0 tới T1: 0,650 giây.
- Route selection từ T1 tới T2: 0,550 giây.
- App recovery từ T0 tới T4: 2,100 giây.

Những khoảng này chỉ có ý nghĩa khi **đồng hồ được đồng bộ và định nghĩa sự kiện tương đương**. Độ trễ ingest log, độ phân giải timestamp và thời gian synthetic probe có thể làm số đo sai nếu không xử lý.

### 13.2. Cần đo cả mất kết nối và giao dịch mới

Một phiên TCP/VPN tồn tại trước failover có thể bị reset, trong khi kết nối mới phục hồi nhanh. Vì vậy cần hai nhóm quan sát:

- **Long-lived sessions:** WebSocket, database connection, SSH session được cấp quyền, VPN tunnel.
- **New transactions:** HTTP API call độc lập, DNS resolution, kết nối DB mới và health probe.

Báo cáo nên ghi rõ **session continuity có hoặc không**, không chỉ đưa ra một con số “downtime”.

## 14. Stateful firewall và NAT khi đổi đường

Đây là một trong những nguyên nhân failover “route đã đúng nhưng ứng dụng vẫn lỗi”.

### 14.1. Firewall state tracking

Firewall stateful thường theo dõi connection state. Nếu luồng ban đầu đi qua FW-A nhưng phản hồi qua FW-B:

~~~text
Client --> FW-A --> App
Client <-- FW-B <-- App
~~~

FW-B có thể không có state và chặn packet phản hồi, tùy policy và cơ chế session synchronization. Trường hợp hai firewall thuộc một cluster HA vẫn cần kiểm tra **session/state sync**, cấu hình NAT, vùng và cơ chế failover; không phải mọi phiên được duy trì tự động.

### 14.2. SNAT/DNAT và public IP khi đổi WAN

~~~text
Trước lỗi:
Client 10.20.20.42:52000
   -> NAT qua WAN-A -> Public IP A -> SaaS

Sau lỗi:
Client 10.20.20.42:52000
   -> NAT qua WAN-B -> Public IP B -> SaaS
~~~

Nếu public source IP đổi, kết nối TCP đang mở thường **không thể giữ nguyên 5-tuple end-to-end**. Dịch vụ SaaS có thể yêu cầu allowlist public IP B, xác thực lại hoặc tạo session mới. Với inbound traffic, một public endpoint thuộc ISP-A không tự chuyển thành endpoint thuộc ISP-B; có thể cần DNS/service failover, BGP multihoming có điều kiện hoặc cơ chế front door khác.

**Không đặt tiêu chí “mọi TCP session phải sống” nếu kiến trúc vật lý/NAT không cho phép**, mà nên đặt mục tiêu phục hồi ứng dụng và chỉ ra session có thể reconnect.

### 14.3. ACL theo interface và zone

Cùng một luồng qua WAN-B có thể đi qua **interface/zone khác**. Một rule allow áp WAN-A chưa chắc tự áp WAN-B. Cần kiểm tra:

- Source/destination sau NAT tại từng interface.
- Zone mapping và policy direction.
- NAT order theo sản phẩm.
- Stateful/stateless và phản hồi ephemeral ports.
- IPv4 và IPv6 policy.
- IPS/IDS logs và SSL/VPN termination.
- Egress filtering, split tunnel và anti-spoofing.

**Kiểm thử security parity** nhằm giữ cùng ý định quyền truy cập, không nhất thiết bắt buộc mọi dòng cấu hình hai đường giống hệt.

## 15. Failover của VPN và các đường overlay

VPN có thể chạy trên hai underlay ISP hoặc hai gateway/tunnel riêng. Một đường WAN còn hoạt động **không bảo đảm tunnel backup đã sẵn sàng**.

### 15.1. Những lớp cần xét

1. **Underlay path:** WAN, route tới VPN peer, NAT và gateway availability.
2. **IKE/IPsec hoặc cơ chế tunnel:** authentication, certificate/PSK, SA, keepalive/DPD theo thiết kế.
3. **Overlay routing:** route quảng bá qua tunnel chính/phụ, BGP hoặc static route.
4. **Security policy:** vùng VPN, ACL, identity/role và kiểm soát phân đoạn.
5. **Ứng dụng qua tunnel:** DNS nội bộ, HTTPS, DB hoặc quản trị hợp lệ.
6. **Session behavior:** có thay gateway/source IP hoặc cần thương lượng lại tunnel không.

### 15.2. DPD không thay thế end-to-end health

Dead Peer Detection và các cơ chế keepalive hỗ trợ nhận biết tình trạng peer hoặc tunnel, nhưng một tunnel up không chứng minh mọi subnet phía sau đều reachable. Cần **probe tới điểm đại diện** và kiểm thử dịch vụ được cấp quyền, nhất là khi dynamic routing hoặc route-based VPN đang dùng.

### 15.3. Lưu lượng đi và về qua VPN

Trong site-to-site VPN, route backup chỉ ở một phía có thể tạo **asymmetric path** hoặc traffic bị gửi vào tunnel sai. Hai site cần có chính sách/route tương thích, kiểm tra cả tunnel selectors nếu triển khai policy-based VPN, ACL, NAT exemption và DNS nội bộ.

**Đừng tắt IKE/IPsec authentication để “cho đường dự phòng chạy”**. Mục tiêu là khôi phục đường mã hóa, được xác thực đúng.

## 16. Dự phòng trong cloud, đa AZ và đa khu vực

Cloud cung cấp nhiều lớp networking managed, nhưng mức độ HA và tính năng tự động khác nhau theo dịch vụ/nhà cung cấp.

### 16.1. Các đối tượng liên quan

| Đối tượng | Rủi ro / câu hỏi cần kiểm tra |
|---|---|
| Cloud route table | Route tới NAT/VPN/transit/private endpoint có next-hop đúng không? |
| VPC/VNet peering | Route hai chiều và security policy đã được cấu hình chưa? |
| Transit hub/gateway | Attachment nào là primary/backup, có propagation/association phù hợp? |
| NAT gateway | Có phù hợp vùng khả dụng và đường route khi AZ lỗi không? |
| Load balancer | Health check của backend, cross-zone behavior và target availability |
| Site-to-site VPN | Hai tunnel, BGP/static route, failover, quảng bá prefix |
| Direct/private interconnect | Dự phòng vật lý/provider, VLAN/BGP session/route |
| Security group / NACL | Luồng backup vẫn được cho/chặn như thiết kế? |
| DNS/private DNS | Endpoint vẫn phân giải đúng trong trạng thái failover? |
| IAM/audit | Ai được đổi route, prefix, tunnel và firewall rule? |

**Không giả định một route tĩnh trong cloud tự chuyển next-hop khi AZ mất.** Một số dịch vụ gateway có HA do provider quản lý, một số route cần orchestration/monitoring hoặc thiết kế riêng. Phải kiểm tra đúng tài liệu và cơ chế của nhà cung cấp đang dùng.

### 16.2. Multi-AZ không đồng nghĩa multi-region

- **Multi-AZ** giảm một số rủi ro trong phạm vi region nếu app/data/network được phân tán đúng.
- **Multi-region** bổ sung ranh giới địa lý/quản trị nhưng phức tạp hơn về replication, DNS, dữ liệu và routing.
- **Route failover** không thay thế replication dữ liệu hay khôi phục ứng dụng; RPO/RTO của dịch vụ có thể chịu ảnh hưởng lớn từ tầng dữ liệu.
- **Security policy và IAM** ở vùng dự phòng phải được chuẩn bị trước, không chỉ sau khi chuyển traffic mới cấu hình.

### 16.3. Một ví dụ cloud có primary/backup

~~~mermaid
flowchart LR
    OFFICE[On-prem] --> VPN1[VPN tunnel A]
    OFFICE --> VPN2[VPN tunnel B]
    VPN1 --> TG[Cloud transit / VPN gateway]
    VPN2 --> TG
    TG --> APP1[App AZ-1]
    TG --> APP2[App AZ-2]
    APP1 --> DATA[(Data service)]
    APP2 --> DATA
    TG -.Flow & route events.-> MON[Monitoring + audit]
~~~

Kiểm thử cần xác minh không chỉ tunnel B kết nối, mà cả **route propagation, SG/NACL, ứng dụng qua AZ còn sống, DB, DNS và đường trả về**. Một VPN tunnel đã up nhưng policy cloud từ chối TCP/443 hoặc DB port vẫn làm dịch vụ không dùng được.

## 17. DNS failover có giống routing failover không?

**Không.** Routing failover thay đổi cách packet được forward qua mạng. **DNS failover** thay đổi câu trả lời tên miền hoặc endpoint được chọn; thời gian ảnh hưởng bởi TTL, cache, resolver/client behavior và session đang mở.

Ví dụ công ty có API ở hai region. Khi region A lỗi, DNS có thể hướng các client mới tới region B. Nhưng:

- Resolver hoặc client có thể tiếp tục dùng record cũ trong một thời gian.
- Phiên TLS/TCP đang mở không tự chuyển sang backend mới.
- Backend B cần đủ dữ liệu, chứng chỉ, IAM, security group và capacity.
- Split DNS/VPN có thể trả câu trả lời khác public DNS.
- DNSSEC hoặc DNS over HTTPS/TLS không làm TTL/route convergence tức thì.
- DNS query thành công không bảo đảm HTTPS transaction thành công.

Nên kiểm thử **DNS resolution và business transaction** từ ít nhất hai loại client đại diện, kèm thời gian và trạng thái cache, thay vì chỉ đọc TTL từ authoritative DNS rồi kết luận failover đạt mục tiêu.

## 18. IPv4, IPv6, VRF và policy routing

### 18.1. Dual-stack phải có test độc lập

Một mạng dual-stack có thể có đường IPv4 dự phòng nhưng IPv6 chỉ có một default gateway, hoặc ngược lại.

Các bước kiểm chứng cần phân tách:
- IPv4 RIB/FIB và đường DNS A.
- IPv6 RIB/FIB và đường DNS AAAA.
- Neighbor Discovery/Router Advertisement hợp lệ.
- Firewall/NAT hoặc cơ chế riêng cho IPv6.
- MTU và ICMPv6 thiết yếu.
- Quy tắc chọn kết nối của ứng dụng có thể ưu tiên IPv6 trong một số tình huống.

**Đừng kết luận toàn bộ mạng phục hồi khi chỉ ping IPv4 thành công.**

### 18.2. VRF và routing domain

**VRF** cho phép các bảng routing logic riêng. Hai subnet trùng IP ở hai VRF có thể đại diện hệ thống khác nhau. Khi test cần ghi rõ:

- VRF/routing table của source và destination.
- Interface binding, route leaking được phê duyệt.
- NAT/firewall policy giữa các VRF nếu có.
- Next-hop và health probe có chạy trong đúng VRF không.
- Monitoring có gắn VRF và address family vào event không.

Một probe chạy trong default VRF **không** chứng minh route của VPN/Management VRF hợp lệ.

### 18.3. Policy-based routing (PBR)

PBR có thể chọn đường dựa trên source, destination, port, DSCP hoặc policy thay vì chỉ destination prefix. Khi failover:

- Traffic của một nhóm user/ứng dụng có thể bị giữ ở đường khác.
- Rule PBR có thể vẫn trỏ vào next-hop lỗi nếu không có tracking.
- Traffic phản hồi có thể không đi cùng hướng.
- Các chính sách bảo mật/giám sát phải theo sát đường được PBR chọn.

Do đó test matrix nên có **các lớp source/ứng dụng** thay vì một máy khách duy nhất.

## 19. ECMP, MTU và chất lượng đường dự phòng

### 19.1. ECMP và phương pháp đo

Trong ECMP, thiết bị có thể ánh xạ flow theo hash để tránh đổi đường từng packet. Khi thử:

- Dùng nhiều **flow được phép** đại diện, nhưng kiểm soát tải và scope.
- Ghi rõ source/destination ports và protocol khi xem kết quả.
- Quan sát counter từng next-hop và session state nếu có.
- Đánh giá khi một member bị loại, các flow còn lại có dồn tới đường đủ năng lực không.

Một flow duy nhất đi tốt không chứng minh tất cả flow trên ECMP đều tốt, cũng không chứng minh tất cả đường đã được dùng.

### 19.2. MTU và Path MTU Discovery

Đường backup có thể đi qua VPN/overlay làm **effective MTU** nhỏ hơn. Kết quả có thể là:

- Ping nhỏ thành công.
- TCP handshake hoàn tất.
- Request lớn hoặc ứng dụng trao đổi dữ liệu bị timeout.
- Một số TLS handshake hoặc file transfer lỗi.

Cần kiểm tra MTU, tunnel overhead, MSS adjustment (nếu áp dụng), ICMP Packet Too Big/fragmentation-needed theo address family và Path MTU Discovery. **Không chặn mọi ICMP/ICMPv6 tùy tiện**, vì điều này có thể khiến những lỗi MTU rất khó chẩn đoán.

### 19.3. Chất lượng và hysteresis

Một đường backup có độ trễ và loss cao hơn vẫn có thể tốt hơn mất kết nối hoàn toàn, nhưng thuật toán failover phải tránh chuyển qua lại vì một mẫu probe ngắn.

Các cơ chế thường gồm **hold-down, recovery threshold, hysteresis, route dampening hoặc cooldown** tùy nền tảng. Không bật hoặc điều chỉnh timers cực thấp khi chưa đánh giá nguy cơ flap và overload control plane.

## 20. Quan sát và tương quan telemetry trong bài test

Một bài failover có thể cần dữ liệu từ nhiều điểm:

| Nguồn | Bằng chứng | Giới hạn |
|---|---|---|
| Interface counters/physical logs | Link errors, drops, interface status | Link up không chứng minh upstream reachable |
| BFD/IGP/BGP logs | Neighbor change, reason, route withdraw | Control plane state không chứng minh app |
| RIB/FIB/forwarding | Next-hop/prefix được chọn | Có thể khác traffic thực vì PBR/VRF/ECMP |
| Firewall traffic/deny logs | Rule, zone, NAT, session action | Chỉ thấy đường qua điểm thực thi |
| VPN/IKE/IPsec logs | Tunnel, SA, rekey, peer state | Tunnel up không chứng minh route nội bộ |
| Flow/NetFlow/IPFIX/VPC logs | 5-tuple, bytes/packets, path context | Sampling, mất log, không luôn có payload |
| DNS logs | Resolver, record/RCODE, timing | DNS query không chứng minh kết nối HTTP |
| APM/synthetic tests | Transaction success, response code, p95/p99 | Cần agent đặt đúng vị trí/source |
| Cloud audit | Thay đổi route, SG, attachment, IAM | Audit control plane không thay data-plane measurement |
| NIDS/IPS | Behavior/alert trên đường quan sát | Có thể bị mất traffic khi failover chuyển sang đường khác |

### 20.1. Đồng bộ thời gian

Cần giữ **event time, ingestion time, timezone, thiết bị và độ lệch đồng hồ**. Một BGP log tới SIEM chậm hơn một HTTP alert không có nghĩa BGP thay đổi sau khi ứng dụng hồi phục. Nên chuẩn hóa UTC khi correlating và ghi sai số.

### 20.2. Sensor coverage thay đổi khi failover

Một NIDS ở WAN-A có thể mất traffic sau khi chuyển sang WAN-B, khiến dashboard alert giảm. Đây **không** phải bằng chứng đối thủ ngừng hoạt động. Cần có sensor/log phù hợp ở backup path, hoặc xác định coverage gap và bổ sung nguồn telemetry khác.

### 20.3. Phát hiện route change trái phép

So sánh route/prefix/best-path bình thường với trạng thái mới. Một route change ngoài change window hoặc từ neighbor lạ cần được review, kể cả khi giao dịch ứng dụng vẫn chạy. Route selection có thể thay đổi đường đi dữ liệu qua vùng an ninh khác.

## 21. Quy trình chạy test có kiểm soát

### Pha A — Chuẩn bị

1. Chọn **một scenario cụ thể**, ví dụ primary link failure trong lab.
2. Xác nhận backup đủ route, firewall, NAT, VPN và capacity.
3. Ghi baseline hiện tại từ router/FIB/firewall/monitoring và application.
4. Phê duyệt thời điểm, phạm vi và phương pháp giả lập lỗi; ghi owner và rollback.
5. Mở dashboard và đồng bộ timestamp, bắt đầu synthetic transactions ở mức thấp.
6. Xác định sẵn điều kiện **abort** và đường quản trị độc lập.

### Pha B — Tạo điều kiện lỗi trong phạm vi được phép

Trong lab cô lập, tình huống lỗi có thể được **mô phỏng bởi topology/emulator**, hoặc bởi một phương pháp thay đổi được quản trị viên phê duyệt. Bài học **không yêu cầu lệnh tắt interface, ngắt neighbor hoặc gây mất route trên production**.

Khi lỗi được ghi nhận, đánh dấu T0, theo dõi các bước detection, route update và thay đổi flow. Không thay nhiều điều kiện cùng lúc nếu muốn truy nguyên chính xác.

### Pha C — Xác minh backup

- RIB/FIB chọn đúng next-hop.
- Traffic và phản hồi dùng đường đã được phê duyệt.
- Synthetic HTTPS/API/DNS/VPN transaction phục hồi.
- Firewall/ACL/IPS allow/deny đúng.
- Session đang mở được ghi nhận là giữ hay phải reconnect.
- MTU, latency, packet loss, throughput phù hợp mục tiêu.
- Mọi log quan trọng còn được gửi tới nơi giám sát.

### Pha D — Phục hồi, failback và rollback

- Khôi phục primary theo phương án đã phê duyệt.
- Kiểm tra health ổn định trước failback; tránh chuyển qua lại.
- Xem RIB/FIB, NAT, session, app SLO sau khi quay về.
- Nếu phát hiện lỗi, áp kế hoạch rollback và dừng test theo ngưỡng.
- Lưu toàn bộ log, kết quả, sai lệch, ticket và owner xử lý.

**Thành công cuối cùng:** hệ thống chạy trên primary hoặc backup như thiết kế **và chính sách bảo mật không bị nới ngoài ý muốn**.

## 22. Mẫu báo cáo kiểm thử

Mẫu cấu trúc dưới đây có thể lưu trong hệ thống quản lý thay đổi của tổ chức.

~~~yaml
test_id: "ROUTE-FAILOVER-LAB-01"
title: "Primary WAN unavailable -> backup WAN"
environment: "isolated-lab"
owner_team: "network-operations"
approved_scope:
  source_segments: ["app-vlan-20", "staff-vlan-10"]
  destinations: ["internal-api", "database", "dns"]
  address_families: ["ipv4", "ipv6"]
  test_window: "approved-change-window"
baseline:
  primary_path: "WAN-A"
  backup_path: "WAN-B"
  route_selection: "primary-preferred"
  security_policy_version: "approved-baseline"
hypothesis:
  expected_path: "WAN-B after primary unavailable"
  expected_security: "allow/deny decisions unchanged"
acceptance_criteria:
  application_recovery: "meet-service-specific-SLO"
  packet_loss: "within-approved-threshold"
  no_unauthorized_route: true
  negative_policy_tests_pass: true
observations:
  failure_start: null
  route_change: null
  application_recovered: null
  session_continuity: "not-measured"
  routing_evidence: []
  firewall_evidence: []
  application_evidence: []
  issues: []
result: "NOT_RUN"
rollback:
  procedure_reference: "approved-change-runbook"
  abort_conditions: "service-SLO-or-security-policy-violated"
review:
  verified_by: null
  next_action_owner: null
~~~

Đây là **YAML mẫu để ghi chép**, không phải cấu hình trực tiếp của router, firewall hoặc cloud platform. Trường acceptance criteria cần được thay bằng ngưỡng cụ thể **đã phê duyệt trước khi chạy test**; không ghi “PASSED” khi dữ liệu chưa đo.

### 22.1. Kết luận có bằng chứng

Một báo cáo tốt có thể ghi:

> “Trong lab, sau sự kiện mất route primary đã được mô phỏng, router chuyển next-hop sang WAN-B theo policy. Synthetic HTTPS phục hồi sau khoảng thời gian được đo, nhưng một phiên TCP đang mở phải reconnect. Negative test Guest → DB vẫn bị deny. Các log đính kèm bao gồm route event, firewall rule và application transaction.”

Không nên ghi “hệ thống HA 100%” từ một lần thử hoặc khẳng định **mọi failure mode** đã được bao phủ nếu chỉ thử link down.

## 23. Các tình huống phân tích và đáp án gợi ý

### Tình huống A — WAN-A mất link, WAN-B ping được nhưng API vẫn lỗi

Router đã chuyển default route qua WAN-B. Ping tới một địa chỉ ngoài thành công, nhưng client không hoàn tất HTTPS API.

**Câu hỏi:** đã xác định backup path hoạt động đầy đủ chưa?

**Gợi ý:** chưa. Kiểm tra DNS, TLS, origin IP allowlist, SNAT public IP, firewall zone, MTU, reverse route và application logs. Ping chỉ là một phần data-plane test.

### Tình huống B — Primary gateway trả lời nhưng upstream bị blackhole

WAN-A interface vẫn up, ARP thấy gateway, static default route không bị xóa; traffic Internet mất.

**Câu hỏi:** tại sao failover không xảy ra?

**Gợi ý:** route tồn tại vì trạng thái local/next-hop còn hợp lệ; hệ thống có thể chưa có end-to-end health tracking. Cần xem target/logic của probe, lựa chọn route và thiết kế xử lý partial failure; chỉ dựa vào carrier không đủ.

### Tình huống C — Ping thành công nhưng Guest truy cập được DB sau failover

Đường WAN dự phòng đi qua một router khác và firewall liên vùng ban đầu không còn nằm trên đường đi.

**Câu hỏi:** có coi failover thành công không?

**Gợi ý:** **không** về mặt Routing security. Dù availability có thể đạt, một **negative security test** đã thất bại. Cần sửa topology/policy để mọi đường được phê duyệt đều thực thi phân đoạn tương đương, rồi kiểm chứng lại.

### Tình huống D — ECMP mất một đường, một số session bị reset

Một next-hop ECMP biến mất, những flow được ánh xạ sang đường còn lại vẫn gửi packet nhưng một số TCP session dừng.

**Gợi ý:** xem flow hashing, firewall state, NAT consistency, asymmetry, buffer/capacity và khả năng reconnect. ECMP forwarding không đảm bảo mọi phiên sống xuyên đổi đường.

### Tình huống E — BGP hội tụ nhưng user mất truy cập SaaS

Sau failover từ ISP-A sang ISP-B, ứng dụng SaaS từ chối request từ những client nội bộ.

**Gợi ý:** xem source NAT public IP mới, SaaS IP allowlist, VPN/identity, geolocation/reputation policy và các session TLS/TCP đang mở. BGP đúng không đảm bảo đối tác chấp nhận public source mới.

### Tình huống F — VRRP chuyển active, nhưng mất kết nối database

Router B tiếp quản virtual gateway, user đến được một số server nhưng App → DB không chạy.

**Gợi ý:** xác minh route/ACL đến DB, interface/VLAN và ARP/ND, trạng thái firewall/NAT, routing table của Router B và chính sách DB. VRRP chỉ giải quyết first hop, không bảo đảm mọi tuyến end-to-end.

### Tình huống G — Đường dự phòng hoạt động nhưng p99 tăng mạnh

Backup WAN có băng thông thấp hơn, dưới tải thực tế các API chậm, timeout tăng.

**Gợi ý:** test failover có thể đạt route selection nhưng **không đạt application SLO**. Cần đo loss/jitter/congestion, điều chỉnh traffic prioritization hoặc bổ sung capacity; phân biệt dịch vụ quan trọng với tải có thể giảm.

### Tình huống H — DNS failover làm client tiếp tục vào region cũ

Authoritative DNS đã đổi record sang region B, nhưng một số client tiếp tục cố kết nối IP region A.

**Gợi ý:** DNS caches, TTL và client session behavior khác route convergence. Kiểm chứng resolver/client caching, business transaction, connection retry và backend B, không kết luận routing network bị lỗi.

### Tình huống I — IPv4 hoạt động, IPv6 thất bại

Sau mất primary, các request tới IPv4 phục hồi nhưng client ưu tiên IPv6 tới website bị timeout.

**Gợi ý:** kiểm tra IPv6 RIB/FIB, next-hop, RA/ND, ICMPv6/PMTUD và firewall IPv6. Không dùng kết quả IPv4 để đại diện cho dual-stack.

### Tình huống J — Route ngoài danh sách được chọn khi primary mất

Một prefix nhận qua BGP backup neighbor có thuộc tính/policy khiến nó được chọn và gửi traffic qua mạng không được phép.

**Gợi ý:** đây là vấn đề **route security**, kể cả khi dịch vụ tạm hoạt động. Kiểm tra route policy, prefix filters, neighbor trust, RPKI origin validation khi phù hợp, change log và kiểm soát quảng bá. Không chỉ điều chỉnh metric để làm traffic quay lại mà bỏ nguyên nhân bất thường.

## 24. Sai lầm phổ biến

1. **Có hai ISP nghĩa là đã HA hoàn chỉnh.** Có thể chung cáp, thiết bị, nguồn hoặc gateway.
2. **Chỉ thử link down.** Không bắt được upstream blackhole, partial loss và route misconfiguration.
3. **Route trong RIB đồng nghĩa forwarding đúng.** FIB, neighbor, ACL và PBR còn có thể sai.
4. **Ping phục hồi nghĩa ứng dụng phục hồi.** TLS, DNS, DB, NAT và policy có thể vẫn lỗi.
5. **BGP/OSPF hội tụ nghĩa TCP session giữ nguyên.** NAT/source IP và firewall state có thể đổi.
6. **VRRP/HSRP thay thế firewall HA.** FHRP chỉ xử lý first-hop redundancy.
7. **BFD nhận biết mọi lỗi end-to-end.** Nó đo đường/peer đã cấu hình, không thay thế transaction health.
8. **Dự phòng nhanh bằng timers cực thấp.** Có thể gây flap và quá tải control plane.
9. **Cho phép rule Any → Any trên backup để bảo đảm kết nối.** Đây là rủi ro bỏ qua phân đoạn.
10. **Chỉ test allowed traffic.** Cần kiểm tra denied flows để bảo vệ east–west isolation.
11. **Không kiểm tra đường phản hồi.** Stateful firewall/NAT có thể chặn asymmetric flow.
12. **Quên public source IP thay đổi khi chuyển ISP.** SaaS allowlist và session có thể lỗi.
13. **Không kiểm tra VPN overlay.** Underlay up chưa chắc tunnel và route bên trong sẵn sàng.
14. **Cloud route table có backup tức tự failover.** Provider/service có cơ chế HA khác nhau.
15. **DNS TTL bằng downtime.** Cache, app state và replication có thể làm thời gian phục hồi khác.
16. **IPv4 PASS nghĩa IPv6 PASS.** Dual-stack có policy và đường độc lập.
17. **Dùng một traceroute để khẳng định ECMP path.** Hash 5-tuple và phản hồi ICMP ảnh hưởng quan sát.
18. **Không quan sát MTU.** Ping nhỏ được nhưng packet lớn bị chặn có thể do PMTUD.
19. **Không đo SLO user.** Route đã chọn nhưng backend/DB quá tải vẫn là lỗi availability.
20. **Không giám sát sensor trên backup.** Traffic chuyển đường làm IDS “mù” mà không báo.
21. **Không bảo vệ control plane.** Route leak/injection và quyền sửa policy có thể gây chuyển hướng.
22. **Không có rollback và quản trị out-of-band.** Test có thể khiến mất chính đường quản trị.
23. **Thay nhiều cấu hình đồng thời.** Khó xác định nguyên nhân test fail/pass.
24. **Không kiểm thử failback.** Sau khi primary trở lại có thể xảy ra flap hoặc gián đoạn mới.
25. **Ghi PASS nhưng không kèm bằng chứng.** Không có timeline, route/log và kết quả business transaction thì không thể review.

## 25. Checklist kiểm thử đường đi dự phòng

- [ ] Đã xác định rõ primary, backup, các prefix/VRF và tuyến đi–về.
- [ ] Đã đánh giá shared risk: cáp, nguồn, upstream, gateway, vùng cloud.
- [ ] Đã xác định link, next-hop, BFD, dynamic route và end-to-end probe kiểm tra điều gì.
- [ ] Đã ghi route preference/policy, control plane authentication và prefix filtering.
- [ ] Đã kiểm tra BGP route security, origin validation và giám sát route changes khi phù hợp.
- [ ] Có baseline RIB/FIB, neighbor, interface, FHRP và VPN state.
- [ ] Có baseline firewall/NAT, security group, ACL, IDS/IPS và quyền ứng dụng.
- [ ] Có test **primary healthy**, **primary unavailable**, **backup active**, **primary recovered**, **failback**.
- [ ] Có kịch bản link down, upstream blackhole và partial degradation phù hợp phạm vi.
- [ ] Có positive application transactions và negative security policy tests.
- [ ] Có test TCP/UDP, return path, stateful session và NAT source IP theo nhu cầu.
- [ ] Có test VPN, DNS/private DNS, TLS/certificate, MTU/PMTUD và cloud attachment khi áp dụng.
- [ ] Có kiểm tra IPv4 và IPv6 riêng trên hệ thống dual-stack.
- [ ] Có kiểm tra ECMP/SD-WAN path quality, capacity và route flapping.
- [ ] Đã định nghĩa SLI/SLO, detection, convergence, recovery, loss và session continuity.
- [ ] Có synthetic transaction ở mức tải phù hợp và giám sát business outcome.
- [ ] Có timestamp đồng bộ, event time/ingest time, log và khả năng dựng timeline.
- [ ] Đã xác minh sensor/log coverage không biến mất khi chuyển đường.
- [ ] Có test được phê duyệt, change window, người trực và out-of-band access.
- [ ] Có điều kiện abort, rollback và kế hoạch khôi phục nếu backup không đạt.
- [ ] Đã ghi kết quả PASSED/FAILED/NOT_RUN/INCONCLUSIVE theo từng test case.
- [ ] Có bằng chứng từ route/FIB, firewall, VPN/cloud và application tương ứng.
- [ ] Có owner xử lý sai lệch và lịch kiểm thử định kỳ sau các thay đổi lớn.
- [ ] Không đánh dấu “HA hoàn chỉnh” chỉ từ một failure scenario hoặc một điểm quan sát.

## 26. Kết luận

**Kiểm thử đường đi dự phòng** là bài toán vừa về **tính sẵn sàng**, vừa về **bảo mật định tuyến**. Thành công không chỉ là thấy một default route đổi sang next-hop khác, mà còn phải chứng minh **traffic đến đúng đích, phản hồi trở lại, ứng dụng phục hồi theo mục tiêu và các chính sách phân đoạn/firewall/VPN/IDS vẫn có hiệu lực**. Các yếu tố như BFD, BGP/OSPF, VRRP, ECMP, NAT, DNS và cloud routing cần được đánh giá theo phạm vi và điểm quan sát chính xác.

Trong kiến trúc **SECURITY_NETWORK_SECURITY**, một đường dự phòng đáng tin là đường đã được thiết kế với **kiểm soát control plane, route filtering, quyền tối thiểu, khả năng giám sát, capacity và runbook**, rồi kiểm chứng có bằng chứng qua nhiều kiểu lỗi. Khi đo cả **convergence lẫn trải nghiệm người dùng hợp lệ**, kiểm thử failover giúp giảm single point of failure mà không biến đường dự phòng thành lối đi bỏ qua những ranh giới bảo mật của hệ thống.
