# High Availability Firewall: thiết kế, chuyển đổi dự phòng và kiểm chứng an toàn

## 1. High Availability Firewall là gì?

**High Availability (HA) firewall** là cách bố trí và vận hành hai hoặc nhiều firewall để **duy trì khả năng cung cấp dịch vụ mạng khi một thành phần gặp sự cố**. HA thường kết hợp phần cứng/instance dự phòng, cơ chế phát hiện lỗi, chuyển đổi vai trò hoặc đường đi, đồng bộ cấu hình và trong nhiều kiến trúc có cả **đồng bộ trạng thái phiên (session/state synchronization)**.

Ví dụ: Doanh nghiệp có ứng dụng thanh toán Production nằm sau firewall. Nếu chỉ dùng một firewall và thiết bị đó bị lỗi nguồn, các kết nối từ Internet vào ứng dụng có thể ngừng hoạt động. Với cụm HA được thiết kế đúng, một firewall khác có thể tiếp quản đường truyền và chính sách, giảm thời gian gián đoạn.

Trong module **SECURITY_NETWORK_SECURITY**, HA firewall liên quan đến nhiều lớp phòng vệ: phân đoạn mạng, firewall policy, VPN, IDS/IPS, xác thực kết nối, giám sát xâm nhập, DNS, môi trường cloud và xây dựng kiến trúc mạng an toàn. Thiết kế tốt phải giữ **đúng quyết định ALLOW/DENY và ranh giới tin cậy** sau khi chuyển đổi, chứ không chỉ bảo đảm gói tin vẫn đi qua một thiết bị nào đó.

Một cụm HA **không tự động** bảo vệ trước lỗi cấu hình chung, rule cho phép quá rộng, lộ khóa quản trị, mất toàn bộ trung tâm dữ liệu, tấn công vào ứng dụng hoặc sự cố upstream chung.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt HA **active/passive**, **active/active** với các mô hình dự phòng kết nối và cân bằng tải.
2. Giải thích vai trò của heartbeat, health check, leader election, configuration sync và session sync.
3. Dự đoán tác động của failover đến TCP, NAT, VPN, routing và chính sách bảo mật.
4. Nhận diện **split-brain**, các điểm lỗi chung và nguy cơ định tuyến bất đối xứng.
5. Thiết kế sơ đồ HA theo zone, ISP, LAN, cloud và nhu cầu dịch vụ.
6. Xây dựng ma trận kiểm thử và quy trình vận hành HA an toàn.

## 2. Phân biệt HA, dự phòng, cân bằng tải và DR

| Khái niệm | Mục tiêu chính | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| **High Availability** | Duy trì dịch vụ khi một thành phần bị lỗi | Hai firewall chạy thành cụm có failover | Không đồng nghĩa chống mọi sự cố hay không gián đoạn tuyệt đối |
| **Redundancy** | Có thành phần/đường dự phòng | Hai nguồn điện, hai switch, hai đường WAN | Có dự phòng nhưng chuyển sang đường mới vẫn có thể chậm hoặc thất bại |
| **Load balancing** | Phân phối lưu lượng lên nhiều thành phần | Bộ phân tải chia kết nối vào nhiều firewall | Không tự bảo đảm state, policy và đường trả về nhất quán |
| **Fault tolerance** | Tiếp tục phục vụ khi có lỗi trong phạm vi thiết kế | Cluster có dự phòng nhiều lớp, bảo toàn phiên | Mức chịu lỗi phụ thuộc kiến trúc và khả năng đồng bộ |
| **Disaster Recovery (DR)** | Phục hồi sau sự cố quy mô lớn | Chuyển dịch vụ sang site/region khác | Có thể có RTO/RPO dài hơn HA trong một site |
| **Business Continuity** | Duy trì các quy trình nghiệp vụ quan trọng | Phương án nhân sự, vận hành, mạng, ứng dụng và dữ liệu | Rộng hơn phạm vi firewall hoặc một giải pháp hạ tầng |

HA có thể cải thiện **availability** nhưng phải đo bằng kết quả đầu cuối: ví dụ người dùng truy cập API thành công, VPN được tái kết nối theo mục tiêu, hệ thống ghi nhận giao dịch đúng và chính sách truy cập không bị nới lỏng.

### 2.1. RTO và RPO có ý nghĩa gì với firewall?

- **Recovery Time Objective (RTO):** Mức thời gian gián đoạn tối đa được chấp nhận cho dịch vụ. Với firewall, cần phân biệt **thời gian failover của thiết bị** và **thời gian ứng dụng phục hồi**; hai giá trị có thể khác xa nhau.
- **Recovery Point Objective (RPO):** Mức dữ liệu trạng thái có thể mất. Với dịch vụ dữ liệu, đây thường là khái niệm ở tầng ứng dụng/DB; với firewall, có thể dùng tương tự để bàn về **session state**, NAT mappings, bộ đếm, hoặc cấu hình chưa được đồng bộ, nhưng không coi firewall HA là giải pháp sao lưu dữ liệu ứng dụng.
- **SLO/SLI:** Mục tiêu và chỉ số đo thực tế như tỷ lệ request thành công, tỉ lệ phiên bị ngắt khi failover hoặc khoảng thời gian mất kết nối từ phía người dùng.

Ví dụ mục tiêu nội bộ: “Khi một node firewall lỗi, ít nhất 99% request HTTPS thử nghiệm vẫn thành công trong cửa sổ đo; các kết nối quản trị từ mạng không được phép tiếp tục bị từ chối.” Con số chỉ mang tính **minh họa**; các ngưỡng phải do yêu cầu nghiệp vụ và thử nghiệm thực tế quyết định.

## 3. Hai mô hình phổ biến: Active/Passive và Active/Active

### 3.1. Active/Passive (A/P)

Trong thiết kế A/P điển hình, **node active** xử lý lưu lượng của các đường/zone đã được giao, còn **node passive/standby** sẵn sàng tiếp quản khi phát hiện lỗi hoặc khi quản trị viên chủ động chuyển vai trò.

~~~mermaid
flowchart TB
    I["Internet / WAN"] --> U["Upstream switches / routers"]
    U --> A["FW-A: ACTIVE"]
    U -. "Đường standby" .-> B["FW-B: PASSIVE"]
    A <-->|"Heartbeat + cấu hình + state (theo thiết kế)"| B
    A --> D["DMZ / Application / LAN"]
    B -. "Tiếp quản khi failover" .-> D
~~~

**Ưu điểm:** Dễ hiểu hơn, một thiết bị xử lý các phiên bình thường, giảm nguy cơ mất cân đối state giữa nhiều node và thường đơn giản hóa phân tích lưu lượng.

**Hạn chế:** Năng lực node dự phòng có thể không được dùng để xử lý lưu lượng bình thường; toàn bộ tải sau failover phải nằm trong **năng lực thực tế của node còn lại**. Trên một số nền tảng, thiết bị passive vẫn có các chức năng giám sát, kiểm tra đồng bộ hoặc xử lý một phần lưu lượng điều khiển.

### 3.2. Active/Active (A/A)

Trong A/A, nhiều node có thể **đồng thời xử lý lưu lượng**, chẳng hạn chia theo virtual firewall, partition, policy domain, flow owner hoặc cơ chế điều phối của nhà sản xuất. Không phải mọi cặp firewall đều hỗ trợ A/A, và cách chia tải khác nhau đáng kể giữa các sản phẩm.

~~~mermaid
flowchart TB
    I["WAN / LAN traffic"] --> L["Routing / load distribution"]
    L --> A["FW-A: xử lý một tập phiên"]
    L --> B["FW-B: xử lý một tập phiên"]
    A <-->|"State/ownership sync nếu được hỗ trợ"| B
    A --> S["Protected services"]
    B --> S
~~~

**Ưu điểm:** Có thể tận dụng nhiều node, phân phối tải và mở rộng trong những nền tảng được thiết kế hỗ trợ.

**Thách thức:** Phải hiểu **node sở hữu phiên**, định tuyến đối xứng, đồng bộ NAT/security state, cơ chế cân bằng tải và tải tăng lên trên node còn sống sau khi mất một thành phần. Hai thiết bị “đang chạy” không chứng minh mọi luồng đã được bảo vệ hoặc load balancing đúng.

### 3.3. Bảng so sánh

| Tiêu chí | Active/Passive | Active/Active |
| --- | --- | --- |
| Node xử lý lưu lượng thường ngày | Thường một active cho nhóm dịch vụ tương ứng | Hai hoặc nhiều node cùng xử lý những tập lưu lượng |
| Thiết kế failover | Standby tiếp quản tài nguyên/đường đi | Phân phối lại phiên/route và có thể chuyển ownership |
| Đồng bộ state | Thường cần để giữ phiên, nhưng có giới hạn | Phức tạp hơn tùy ownership và cơ chế cluster |
| Năng lực dự phòng | Cần node standby chịu được tải khi active lỗi | Cần tổng năng lực còn lại chịu được tải sau khi mất node |
| Vận hành | Thường đơn giản hơn | Cần kiểm soát bất đối xứng, routing và phân phối tải |
| Khi nên cân nhắc | Mục tiêu sẵn sàng rõ ràng, cấu trúc policy thống nhất | Sản phẩm hỗ trợ thực sự và nhu cầu chia tải/đa vùng chính đáng |

**Không nhầm A/A với HA có hai đường ISP.** Hai uplink có thể cùng hoạt động trong khi chỉ một firewall active; tương tự, hai firewall active có thể cùng phụ thuộc một router hoặc ISP, khiến mất mạng khi upstream đó gặp lỗi.

## 4. Các thành phần kỹ thuật của một cụm HA

### 4.1. Heartbeat và health detection

Các node cần phương thức biết node kia còn hoạt động hay không. **Heartbeat** là tín hiệu giữa các thành viên trong cụm; **health monitoring** còn có thể kiểm tra interface, gateway, process, route, dataplane, nguồn điện hoặc một dịch vụ kiểm tra ở xa.

| Tín hiệu | Điều có thể phát hiện | Điều không tự chứng minh |
| --- | --- | --- |
| Heartbeat giữa node | Khả năng liên lạc giữa các node | Internet thực sự đến được ứng dụng |
| Interface link status | Link vật lý còn UP/DOWN | Đường upstream ngoài link có hoạt động không |
| Gateway/route tracking | Khả năng tới next hop hoặc tuyến trọng yếu | Ứng dụng cụ thể có hoạt động không |
| Dataplane/process health | Thành phần xử lý gói có phản hồi | Toàn bộ policy hoặc IPS engine đều đúng |
| Synthetic transaction | Kết nối/HTTP request tới mục tiêu kiểm thử | Các path khác ngoài giao dịch mẫu đều khỏe |

Một **link UP** có thể không mang dữ liệu hiệu quả vì lỗi định tuyến, ACL, MTU hoặc upstream. Ngược lại, failover chỉ dựa trên một probe bên ngoài dễ gây **chuyển qua chuyển lại (flapping)** khi đích kiểm tra tạm thời không phản hồi.

### 4.2. Election, role và priority

Một cụm cần cơ chế chọn node hoặc phân công ownership khi khởi động, bảo trì và có lỗi. Có nền tảng dùng **priority/preemption**, có nền tảng dùng **quorum** hoặc thuật toán điều phối riêng.

- **Preemption** cho phép node ưu tiên cao lấy lại vai trò sau khi hồi phục, nếu được bật.
- **Non-preempt** có thể tránh một lần chuyển đổi không cần thiết khi node cũ trở lại.
- **Hold-down timer / dampening** có thể hạn chế failover liên tục.

Không có lựa chọn “bật preempt luôn tốt”: quyết định phải xét rủi ro gián đoạn phiên, độ ổn định link và bảo trì định kỳ.

### 4.3. Configuration synchronization

Cụm cần thống nhất các dữ liệu phù hợp như **firewall rules, objects, NAT, routing/zone mapping, VPN settings và cấu hình dịch vụ bảo mật**, trong phạm vi hỗ trợ. Một số tham số **gắn với từng node** như management IP, serial, interface ID hoặc priority có thể chủ đích khác nhau.

**Cấu hình được sync thành công chưa chắc an toàn:** Nếu rule Prod bị mở rộng sai và được tự động đồng bộ, cả active và standby cùng thực thi lỗi. Vì thế HA phải đi kèm **quản trị thay đổi, review policy, quyền triển khai, bản sao cấu hình và kiểm thử**.

### 4.4. Session/state synchronization

Firewall stateful theo dõi trạng thái phiên để quyết định gói trả về có hợp lệ không. Để duy trì phiên sau failover, node dự phòng có thể cần nhận:

- Bảng kết nối, IP/port nguồn–đích, protocol, timeout.
- NAT/PAT translation và ánh xạ public IP/port.
- Session ownership, sequence/window metadata liên quan đến xử lý TCP (theo sản phẩm).
- Một số trạng thái của VPN, kiểm tra nội dung, authentication hoặc IPsec Security Association **nếu thiết bị hỗ trợ**.

**Không đồng nghĩa mọi phiên đều giữ nguyên.** Stateful failover thường giảm số phiên phải thiết lập lại, nhưng TCP/UDP, NAT, TLS decryption, proxy, IPS, SIP/ALG, VPN, clientless SSL VPN và ứng dụng phụ thuộc trạng thái có mức độ giữ phiên khác nhau. Phải tra đúng khả năng phiên bản sản phẩm và **đo thực tế**.

### 4.5. Management plane

Đường quản trị giúp xem trạng thái cluster, đẩy cấu hình, lấy log, cập nhật phần mềm và khôi phục. Nên tách **quyền quản trị**, mạng quản trị và tài khoản định danh khỏi đường dữ liệu thông thường. Nếu dùng nền tảng điều phối trung tâm, đây cũng là một **trust boundary** cần bảo vệ và giám sát.

## 5. HA link: heartbeat, đồng bộ và nguy cơ split-brain

### 5.1. Không phụ thuộc duy nhất vào một đường HA

Một thiết kế có thể dùng **đường heartbeat riêng** và **đường state/config sync riêng**, hoặc cơ chế HA multiplexed tùy nền tảng. Mục tiêu là có đường liên lạc đáng tin, dung lượng phù hợp và không bị một sự cố mạng thông thường làm hai node hiểu nhầm rằng node còn lại đã chết.

Điểm cần xem xét:

- Kết nối trực tiếp hoặc qua switch HA chuyên dụng theo hướng dẫn của nhà sản xuất.
- Dự phòng HA link nếu nền tảng hỗ trợ; tránh hai cáp cùng phụ thuộc một điểm lỗi không nhận ra.
- Bảo vệ traffic HA sync (vùng mạng riêng, ACL, cơ chế xác thực/mã hóa nếu sản phẩm hỗ trợ), vì dữ liệu trạng thái và cấu hình có thể nhạy cảm.
- Giám sát packet loss, latency, backlog của session sync và trạng thái link.
- Đảm bảo đủ băng thông khi có nhiều phiên/ngày hoặc bật tính năng sync bổ sung.

### 5.2. Split-brain là gì?

**Split-brain** xảy ra khi nhiều node **cùng tin rằng mình phải giữ vai trò active/owner của cùng một tài nguyên**, thường do mất liên lạc giữa các node trong khi những đường khác vẫn hoạt động.

~~~text
Trạng thái bình thường:
  FW-A: ACTIVE     <--- heartbeat --->     FW-B: STANDBY
                     sync state/config

Mất liên lạc HA (ví dụ một link lỗi):
  FW-A: ACTIVE     -X- heartbeat -X-      FW-B: không thấy FW-A
                                               |
                             Nếu cơ chế election/fencing lỗi:
                             FW-B cũng có thể trở thành ACTIVE

Hậu quả tiềm ẩn:
  Trùng ownership VIP/VMAC, ARP/MAC flapping, routing không nhất quán,
  phiên rơi rớt, policy/state lệch và lưu lượng đi sai đường.
~~~

**Cách phòng ngừa:** Dùng cơ chế **quorum/witness/fencing/peer isolation** phù hợp sản phẩm, phát hiện đa đường và logic election đã được kiểm chứng. Trong cụm hai node, một số nền tảng có quy tắc xác định cụ thể node nào tiếp tục hoạt động khi heartbeat mất. Không tự suy diễn mọi hệ thống dùng “majority vote” hoặc có thể thêm witness.

**Nguy cơ vận hành:** Không tự ý rút HA link trên firewall Production để thử “split-brain” nếu chưa có quy trình, phạm vi, khả năng khôi phục và cửa sổ thay đổi được phê duyệt.

## 6. Chuyển đổi dự phòng thực sự xảy ra như thế nào?

Mô hình A/P minh họa:

~~~mermaid
sequenceDiagram
    participant A as FW-A Active
    participant B as FW-B Standby
    participant R as Routers/Switches
    participant C as Client
    A->>B: Heartbeat + state/config sync
    C->>A: Kết nối ứng dụng bình thường
    A--xB: Heartbeat ngừng vì sự cố A
    B->>B: Kiểm tra health/election
    B->>R: Nhận vai trò active và cập nhật đường đi
    Note over B,R: GARP/ND, route update, VIP/VMAC hoặc cơ chế khác
    C->>B: Packet/phiên tiếp theo (nếu route hội tụ)
    B->>B: Tra state đã sync hoặc tạo phiên mới
~~~

Để failover có tác dụng, cần **tất cả** các khâu:

1. **Phát hiện sự cố** trong thời gian phù hợp.
2. **Chọn đúng node tiếp quản**, tránh active đồng thời không mong muốn.
3. **Chuyển tiếp được traffic**: VIP, ARP/ND, MAC hoặc routing hội tụ.
4. **Áp dụng cùng mục tiêu chính sách**: zone, rule, NAT, bảo mật và logging không mở quyền ngoài dự kiến.
5. **Khôi phục state hoặc cho tái thiết lập phiên** theo đặc điểm giao thức.
6. **Ứng dụng/client phục hồi**: retransmission, reconnect, retry/idempotency nếu cần.

Nếu node đổi role trong vài giây nhưng bảng định tuyến hội tụ chậm hoặc client VPN phải xác thực lại, trải nghiệm đầu cuối có thể gián đoạn lâu hơn thời gian role change được quảng bá.

### 6.1. Phân biệt loại sự cố

| Sự cố | Node active có thể quan sát gì? | Điều kiện để HA bảo vệ |
| --- | --- | --- |
| Hỏng nguồn hoặc crash active | Heartbeat/process mất | Standby khỏe, phát hiện đúng lỗi, đường tới standby thông suốt |
| Mất một uplink của active | Interface down; heartbeat có thể vẫn UP | Theo dõi uplink/route và có đường WAN thay thế |
| ISP upstream mất kết nối ngoài gateway | Interface vẫn UP, probe tới xa thất bại | Có ISP/route khác; health check đủ chính xác |
| Mất switch chung của cả hai firewall | Cả hai có thể mất đường đi | Cần switch/đường kết nối dự phòng, tránh điểm lỗi chung |
| Mất HA/sync link nhưng data path còn khỏe | Peer không nhìn thấy nhau | Election/quorum/fencing tránh split-brain |
| Policy sai được sync sang cả hai node | Cả hai cùng có thể ALLOW/DENY sai | HA không khắc phục; cần rollback và review policy |
| Phiên IPS/TLS proxy không thể đồng bộ | Data path hồi phục nhưng phiên cụ thể reset | Ứng dụng tự kết nối lại, thiết kế/protocol hỗ trợ |
| Mất toàn bộ site/region | Toàn bộ cluster tại site bị ảnh hưởng | Cần DR hoặc multi-site/multi-region theo thiết kế riêng |

## 7. Routing, NAT và địa chỉ IP khi failover

### 7.1. Layer 2: floating IP, virtual MAC và ARP/ND

Một số cụm A/P dùng **virtual IP (VIP)** hoặc **virtual MAC (VMAC)** để node active đại diện cho gateway hoặc địa chỉ dịch vụ. Sau failover, node mới có thể phát **gratuitous ARP (GARP)** trên IPv4, **Neighbor Advertisement** trên IPv6 hoặc thông điệp tương ứng để cập nhật bảng láng giềng.

Các điểm kiểm tra:

- Cả hai node có kết nối đến **đúng các VLAN/zone**; port trunk cho phép VLAN cần thiết.
- Switch/host upstream chấp nhận MAC movement và cập nhật ARP/ND đúng thời gian.
- Không có bảo vệ giả MAC/ARP làm chặn các frame cần thiết của cơ chế HA; đồng thời không vô hiệu hóa bảo vệ LAN trên diện rộng.
- MTU, VLAN tagging và đường đi dự phòng thống nhất.
- Có phương án khi GARP/ND bị chặn, bảng neighbor cũ chưa hết hạn hoặc upstream không hỗ trợ virtual MAC.

**VRRP** là giao thức dự phòng default gateway ở L3 với địa chỉ ảo; nó có thể là một phần thiết kế, nhưng **VRRP đơn lẻ không đồng bộ firewall session, NAT hay policy**. Không gọi hai router dùng VRRP là “stateful firewall HA” nếu không có các khả năng đó.

### 7.2. Layer 3: dynamic routing và route convergence

Trong thiết kế không dựa vào chuyển VIP trên cùng VLAN, cụm hoặc các firewall độc lập có thể công bố tuyến bằng **BGP/OSPF** hoặc dùng static route có tracking, ECMP hoặc load balancer điều phối.

- **Routing convergence:** Thời gian các router/người gửi cập nhật lựa chọn đường đi sau lỗi.
- **Route advertisement/withdrawal:** Một node mất khả năng forward không nên tiếp tục quảng bá đường hợp lệ như thể dịch vụ vẫn khỏe.
- **BFD:** Có thể giúp phát hiện lỗi nhanh hơn trong mô hình routing phù hợp, nhưng phải cân nhắc timer và tải hệ thống.
- **ECMP và hashing:** Phải bảo đảm lưu lượng hai chiều của phiên đến được thiết bị có state hoặc có cơ chế chia sẻ state phù hợp.
- **VRF/zone/routing domain:** Rule có thể đánh giá khác sau khi traffic được chuyển qua interface hoặc zone khác.

L3 HA đòi hỏi kiểm chứng cả **chiều đi và chiều về**. Nếu gói đi qua FW-A nhưng gói trả về qua FW-B không có trạng thái phiên cần thiết, stateful firewall có thể loại gói hợp lệ. Một số nền tảng hỗ trợ xử lý asymmetry trong phạm vi nhất định; không mặc định tính năng luôn bật hoặc an toàn như thiết kế đối xứng.

### 7.3. NAT/PAT và egress public IP

NAT có thể biến một địa chỉ nội bộ thành địa chỉ công khai và port mới. Nếu sau failover **public egress IP thay đổi**, phiên TCP đến dịch vụ ngoài thường bị mất và ứng dụng có thể cần reconnect. Nếu giữ cùng egress IP nhưng không sync **NAT mapping**, phiên cũng có thể reset.

Ví dụ:

~~~text
Trước failover:
  Client 10.20.0.10:50500  -> FW-A NAT 198.51.100.10:40001
                            -> Dịch vụ Internet 203.0.113.20:443

Sau failover mong muốn:
  FW-B tiếp quản đúng egress IP, đường đi và mapping phù hợp
  để có khả năng tiếp tục phiên (nếu state/protocol được hỗ trợ).

Nếu FW-B sử dụng 198.51.100.11 hoặc port mapping khác:
  Kết nối cũ thường không thể tiếp tục liền mạch;
  client phải tạo kết nối mới theo khả năng ứng dụng.
~~~

Các IP **198.51.100.0/24** và **203.0.113.0/24** là dải tài liệu TEST-NET, không phải địa chỉ của hệ thống thật.

## 8. VPN, IDS/IPS, TLS và dịch vụ bảo mật khi HA

Firewall ngày nay không chỉ lọc IP/port. Có thể còn đóng vai trò **VPN gateway, IPS, TLS inspection proxy, DNS security gateway hoặc điểm thực thi xác thực người dùng**. Mỗi chức năng có yêu cầu HA riêng:

| Chức năng | Trạng thái/điểm phụ thuộc | Cần kiểm chứng khi failover |
| --- | --- | --- |
| **IPsec site-to-site** | IKE SA, CHILD SA, khóa, anti-replay window, peer address, route | Tunnel có được giữ hoặc tái thương lượng? Traffic selector và đường return có đúng? |
| **Remote-access VPN/SSL VPN** | Client session, certificate, MFA, IP pool, user identity | Client có phải reconnect/reauth? IP được cấp và quyền sau reconnect còn đúng? |
| **IDS/IPS inline** | Signature version, policy, engine, flow reassembly/state | Engine mới có được áp chính sách tương đương? Phiên đang kiểm tra có bị reset? |
| **TLS inspection/proxy** | TLS keys, handshake, certificate, proxy session | Có giữ được kết nối hay cần bắt tay lại? Private keys được bảo vệ? |
| **User/group identity policy** | User-to-IP mapping, identity source, session TTL | Sau failover quyền theo người dùng có được áp dụng đúng? |
| **DNS security/resolver** | Cache, policy, DNS upstream, logging | Truy vấn DNS có thất bại hoặc thay đổi policy? Có đường bypass ngoài ý muốn? |
| **Application control/URL filter** | Dynamic signatures, cloud lookup, cache, license | Phiên mới có thực thi đúng profile, policy và feed? |
| **Logging/telemetry** | Node identity, timestamps, correlation ID, log queue | Có khoảng trống log, trùng log hoặc mất mapping phiên không? |

**Lưu ý bảo mật:** Không “giải quyết HA” bằng cách làm IPS chuyển sang chế độ bỏ qua kiểm tra, tắt xác thực VPN, bật allow-any-any hoặc tự động **fail-open** trên đường vào vùng nhạy cảm. Nếu cần hỗ trợ fail-open cho một dịch vụ bắt buộc, phải nêu rõ điều kiện, rủi ro, thời gian, giám sát và quyết định đã được phê duyệt.

### 8.1. Fail-open và fail-closed

- **Fail-closed:** Khi không thể đánh giá chính sách, lưu lượng bị từ chối. Giảm nguy cơ vượt ranh giới nhưng có thể làm gián đoạn nghiệp vụ.
- **Fail-open:** Lưu lượng có thể tiếp tục được chuyển ngay cả khi một lớp kiểm soát không hoạt động. Giúp duy trì dịch vụ trong một số kiến trúc nhưng có thể tạo **cửa sổ không được kiểm tra**.

Hai thuật ngữ phải được hiểu theo **đúng lớp và đúng cơ chế**. Một thiết bị bypass ở lớp vật lý, IPS engine fail-open và cluster firewall HA có hành vi khác nhau. Với hệ thống chứa dữ liệu nhạy cảm, thiết kế cần ưu tiên **tính đúng đắn của chính sách** và tách biệt rõ các rủi ro nghiệp vụ.

## 9. Thiết kế HA không có điểm lỗi đơn lẻ

Có **hai firewall** không đủ nếu cả hai dùng chung một nguồn điện, một switch, một router, một ISP hoặc một đường sync duy nhất.

### 9.1. Sơ đồ tham chiếu

~~~mermaid
flowchart TB
    I1["ISP/Edge 1"] --> U1["Upstream switch/router 1"]
    I2["ISP/Edge 2"] --> U2["Upstream switch/router 2"]
    U1 --> A["Firewall A"]
    U1 --> B["Firewall B"]
    U2 --> A
    U2 --> B
    A <-->|"HA heartbeat/state (redundant theo hỗ trợ)"| B
    A --> D1["Inside switch 1"]
    A --> D2["Inside switch 2"]
    B --> D1
    B --> D2
    D1 --> P["Production services"]
    D2 --> P
~~~

Đây là **sơ đồ khái niệm**. Trong triển khai thật, loại link, số port, LAG/MLAG, peer routing, VLAN, STP, cluster mode và kết nối đến switch phải tuân theo thiết kế được nhà sản xuất hỗ trợ. Không phải mọi firewall HA đều cắm đồng thời hai switch theo cách bất kỳ.

### 9.2. Kiểm tra failure domain

| Failure domain | Rủi ro nếu dùng chung | Biện pháp thiết kế |
| --- | --- | --- |
| Nguồn điện/PDU | Mất điện một nhánh làm tắt cả cụm | Nguồn, UPS/PDU và đường điện độc lập |
| Upstream/inside switch | Mất switch chặn traffic của cả hai firewall | Switch đôi, kết nối dự phòng và kiểm chứng topology |
| WAN/ISP | Cả cụm mất Internet dù firewall khỏe | Đường/nhà cung cấp dự phòng, route failover |
| HA link | Split-brain hoặc thiếu state sync | Đường HA dự phòng/cơ chế quorum/fencing phù hợp |
| Management/control plane | Không khôi phục hoặc quản lý được khi lỗi | Quản trị out-of-band, backup cấu hình và quyền riêng |
| Nền tảng phần mềm | Lỗi chung trên cả hai node cùng phiên bản | Quy trình nâng cấp được hỗ trợ, rollback, kiểm thử |
| Policy/IaC | Rule sai được áp cho mọi node | Review, mô phỏng, kiểm thử DENY/ALLOW và version control |
| Datacenter/AZ/region | Sự cố diện rộng đánh sập cả cụm | Thiết kế DR/multi-AZ/multi-region khi yêu cầu |

## 10. HA firewall trong cloud và môi trường hybrid

Trong cloud, nhiều thành phần mạng do nhà cung cấp quản lý. HA có thể dựa trên **nhiều instance firewall**, **Gateway Load Balancer**, **route table failover**, **transit gateway**, **load balancer/target group** hoặc dịch vụ firewall managed. Cách thực thi phụ thuộc kiến trúc và nhà cung cấp; không thể sao chép nguyên mô hình floating MAC/GARP của LAN vào mọi VPC/VNet.

### 10.1. Thiết kế multi-AZ

~~~mermaid
flowchart LR
    SRC["Workloads / Edge"] --> R["Route/load distribution"]
    R --> A["Firewall node / endpoint AZ-A"]
    R --> B["Firewall node / endpoint AZ-B"]
    A --> DST["Protected workload"]
    B --> DST
~~~

Khi một Availability Zone hoặc node lỗi, hệ thống cần **đưa luồng mới đến nơi còn khỏe** và xử lý traffic hiện hữu theo khả năng state/flow affinity của giải pháp.

Cần xác minh:

- Route table của **từng subnet/AZ**; route không nhất thiết tự thay đổi theo trạng thái VM.
- **Flow affinity/symmetry** trong các dịch vụ cân bằng tải mạng: hai chiều của cùng phiên phải đến firewall có state phù hợp.
- Health check phản ánh **khả năng kiểm tra và forward traffic**, không chỉ VM còn chạy.
- NAT/public IP, DNS, VPN endpoint, identity và logging sau khi thay node.
- Các thành phần đi kèm như gateway, endpoint, service insertion, security group và quyền tự động sửa route.
- Quyền IAM của automation failover, giới hạn thay đổi và audit trail.

### 10.2. Multi-region là một bài toán rộng hơn

Cluster hai node trong cùng một AZ/site không bảo vệ trước sự cố toàn vùng. Thiết kế multi-region có thể cần:

- DNS/Global Load Balancer và health check theo ứng dụng.
- Đường routing/BGP/VPN mới và chính sách cùng ý định ở region dự phòng.
- Cơ chế đồng bộ cấu hình, secrets và quyền truy cập phù hợp.
- DR cho ứng dụng và dữ liệu, gồm DB replication, backup/restore và kiểm thử RTO/RPO.

**Firewall tiếp quản đường đi không đồng nghĩa database và dịch vụ ứng dụng đã sẵn sàng ở site dự phòng.**

### 10.3. Hybrid network

Khi kết nối on-prem ↔ cloud qua **IPsec VPN/leased circuit/SD-WAN**, phải xem **đường hầm, địa chỉ tunnel endpoint, BGP neighbor, MTU, route priority và firewall policy ở cả hai đầu**. Mất một firewall có thể buộc đường VPN tái thương lượng hoặc chọn site khác; ứng dụng vẫn có thể chịu gián đoạn.

## 11. Những yêu cầu an ninh phải giữ qua failover

Mô hình hóa mối đe dọa giúp chỉ ra rằng một thiết kế HA có thể **sẵn sàng nhưng thiếu an toàn**.

| Threat scenario | Điều kiện xảy ra | Tác động | Kiểm soát đề xuất |
| --- | --- | --- | --- |
| **Split-brain / duplicate active** | Mất heartbeat, election/fencing không bảo đảm | IP/MAC flapping, state lệch, traffic bị rơi hoặc sai đường | HA link dự phòng, quorum/fencing, lab kiểm thử logic election |
| **Policy drift giữa node** | Thay đổi không đồng bộ, object/firmware lệch | Failover mở hoặc chặn sai dịch vụ | Versioned config, sync health, kiểm thử quyết định policy |
| **Cấu hình sai được đồng bộ** | Thay rule rộng từ hệ thống quản lý | Cả hai node cùng có lỗ hổng | Phê duyệt, lint/policy-as-code, review và rollback |
| **HA link bị truy cập trái phép** | Sync/management mở vào mạng không tin cậy | Lộ cấu hình/state, thay đổi hoạt động cụm tùy năng lực tấn công | Cô lập, xác thực, mã hóa, ACL và giám sát |
| **Node standby lâu không được cập nhật** | Chỉ active được kiểm tra định kỳ | Failover chạy firmware/signature lỗi thời hoặc thiếu license | Patch/signature, licensing, hardware health check cả hai node |
| **Asymmetric route** | ECMP hoặc NAT đưa chiều về qua node khác | Kết nối ngắt hoặc bị drop vì không có state | Flow affinity, route kiểm soát, session sync nếu hỗ trợ |
| **Fail-open ngoài dự kiến** | IPS/proxy/bypass chuyển qua chế độ bỏ kiểm tra khi lỗi | Lưu lượng độc hại được đi qua | Chính sách fail mode được duyệt và thử nghiệm |
| **HA failover bị lạm dụng** | Tác nhân có quyền điều khiển node/health signal | Đảo role lặp, gián đoạn hoặc vượt policy | Phân quyền admin, MFA, audit, giới hạn automation |
| **Rớt log khi chuyển node** | Buffer/collector/clock không đồng nhất | Mất bằng chứng điều tra | Đồng bộ thời gian, forward log đến collector, correlation |

### 11.1. Ranh giới giữa availability và security

HA phải giữ các điều kiện:

1. Chỉ luồng **được phép trước sự cố** mới tiếp tục được phép, trừ thay đổi đã phê duyệt.
2. Các luồng cần từ chối, đặc biệt **Dev → Prod DB**, **Internet → Management** và **VPN user ngoài quyền → subnet nhạy cảm**, vẫn bị từ chối sau failover.
3. Xác thực quản trị, mTLS, chứng chỉ VPN, IPS signatures và security profiles vẫn có hiệu lực trên node tiếp quản.
4. Sự kiện failover, policy sync và hành động của người vận hành được ghi nhận có dấu thời gian tin cậy.

## 12. Ví dụ cấu hình tư duy: yêu cầu HA trước khi chọn vendor

Tài liệu yêu cầu nên mô tả hành vi cần thiết thay vì bắt đầu từ lệnh CLI của một hãng.

~~~yaml
# Ví dụ mô tả THIẾT KẾ, không phải cấu hình thực thi của sản phẩm nào.
environment: production
service: internet-egress-and-api-ingress
topology:
  model: active-passive
  nodes:
    - fw-a
    - fw-b
  failure_domains:
    power: independent
    upstream_switch: redundant
    downstream_switch: redundant
    wan: two-approved-paths
health:
  signals:
    - peer-heartbeat
    - critical-interface
    - supported-route-or-gateway-check
  anti_flap: required
state:
  configuration_sync: required
  session_sync: required-where-supported
  nat_mapping_sync: required-where-supported
traffic:
  routing_convergence: verify-in-lab
  deny_rules_must_remain_effective: true
security:
  management_access: restricted
  ha_link_protection: required
  logging_to_external_collector: required
operations:
  backup_and_rollback: documented
  failover_runbook: documented
  expected_disruption: measured-not-assumed
~~~

Để đưa thành cấu hình thật, cần đối chiếu từng trường với **tính năng được hỗ trợ**, license, phần cứng, phiên bản firmware, cách xử lý routing/NAT và giới hạn sync state của nền tảng đã chọn.

## 13. Quy trình triển khai an toàn

### Bước 1. Thu thập yêu cầu và điểm lỗi

Liệt kê ứng dụng, phân loại dữ liệu, số kết nối đồng thời, throughput thực khi bật IPS/TLS inspection, VPN tunnels, mức gián đoạn chấp nhận được và các đường WAN/LAN. Vẽ sơ đồ **failure domains**: nguồn, switch, ISP, site, account cloud, route, bộ điều khiển và đường quản trị.

### Bước 2. Chọn mô hình HA và kiểm tra tương thích

Xác minh thiết bị/VM, version, license, port mapping, HA feature, state sync, NAT, VPN, IPS, HA-over-WAN và ràng buộc topology. Không giả định hai thiết bị cùng hãng nhưng khác phiên bản luôn có thể cùng cluster.

### Bước 3. Thiết kế routing/zone/identity

Xác định **traffic path của cả chiều đi/về**, vùng Internet/DMZ/App/DB/Management/VPN, các địa chỉ VIP, route và NAT sẽ di chuyển ra sao. Vẽ cả tình huống khi node A active lẫn node B active.

### Bước 4. Bảo vệ HA/control plane

Thiết lập HA link và mạng quản trị, account, MFA, RBAC, logging, đồng bộ thời gian, sao lưu cấu hình. Hạn chế việc node mới tự kích hoạt hoặc đổi cấu hình khi điều kiện election chưa xác thực.

### Bước 5. Đồng bộ chính sách và kiểm thử tĩnh

Đối chiếu zone, ACL, NAT, service object, VPN selectors, certificate, identity mapping, IPS profiles, signatures và license. Kiểm tra **rule order/shadowing** hoặc quyền allow quá rộng; so sánh kết quả policy trên cả node.

### Bước 6. Kiểm thử chức năng trong lab/staging

Chạy các phép thử ở mục 14 với các tình huống lỗi được mô phỏng trong môi trường được phép. Đo **thời điểm phát hiện lỗi, đổi role, hội tụ đường đi, kết nối ứng dụng hồi phục**.

### Bước 7. Triển khai theo quy trình có rollback

Lưu backup cấu hình và phiên bản firmware được phê duyệt, phân công owner/giám sát, có cửa sổ thay đổi và phương án chuyển về trạng thái trước. Khi bắt đầu vận hành, theo dõi sát **dropped sessions, VPN reconnects, NAT errors, latency và security policy hits**.

### Bước 8. Diễn tập định kỳ và nâng cấp rolling

Khi nhà sản xuất hỗ trợ, có thể nâng cấp từng node theo **trình tự được khuyến nghị**, chuyển vai trò và xác minh. **Rolling upgrade không mặc nhiên zero downtime**; các thay đổi session format, firmware, signature, routing và state sync có thể khiến một số phiên bị ngắt.

## 14. Ma trận kiểm thử HA firewall

**Nguyên tắc:** Mọi thử nghiệm ngắt nguồn, ngắt link hay ép failover đều phải được thực hiện trong **môi trường lab/staging hoặc cửa sổ thay đổi đã được phê duyệt**. Không thử phá hủy đường mạng Production tùy tiện.

| Test ID | Tình huống | Kết quả kỳ vọng | Bằng chứng cần ghi |
| --- | --- | --- | --- |
| HA-01 | Hoạt động bình thường | Chỉ đúng node/partition được chỉ định xử lý; node dự phòng khỏe | Role, heartbeat, config/state sync |
| HA-02 | Failover chủ động theo quy trình | Node mới nhận vai trò đúng và đường dữ liệu hồi phục | Timestamp role, ARP/ND/route, request success |
| HA-03 | Mất node active (lab) | Node còn sống tiếp quản trong mức mục tiêu đã định | Health/election log, thời gian mất traffic |
| HA-04 | Mất một uplink của active | Failover hoặc đổi tuyến theo chính sách health | Link/route status, next hop, flow test |
| HA-05 | Mất upstream ISP, link vật lý vẫn UP | Điều hướng qua ISP dự phòng nếu được thiết kế | Probe, route withdrawal, public reachability |
| HA-06 | HA heartbeat link lỗi (lab) | Không có hai node cùng nhận sai ownership | Role/quorum/fencing log, VIP/MAC ownership |
| HA-07 | TCP/HTTPS tải liên tục khi failover | Tỉ lệ request lỗi/khả năng reconnect đạt SLO | Client success rate, reconnect count, p95 latency |
| HA-08 | NAT/PAT flow đang hoạt động | State/egress IP/mapping đúng khả năng thiết bị | Flow/NAT table, IP public, app traces |
| HA-09 | IPsec/remote VPN đang kết nối | Tunnel/phiên khôi phục theo mục tiêu, chính sách quyền không sai | IKE/VPN state, client reconnect/reauth |
| HA-10 | Luồng **được phép** qua nhiều zone | Tiếp tục đúng policy trên node mới | Rule ID, allow log, application health |
| HA-11 | Luồng **bị từ chối** vào zone quản trị/DB | Vẫn **DENY** trước và sau failover | Deny log/rule hit, không có session thành công |
| HA-12 | IPS/TLS inspection được bật | Profile hoạt động theo thiết kế, không bypass bất ngờ | Security engine state, log/test mẫu được phép |
| HA-13 | Node cũ hồi phục | Không gây flapping/preempt ngoài kế hoạch | Role history, session loss, timers |
| HA-14 | Tính năng đồng bộ cấu hình bị gián đoạn | Cảnh báo và không áp dụng policy sai khi đổi node | Config checksum/diff, sync health |
| HA-15 | Log collector/NTP bị gián đoạn | Hệ thống phát hiện thiếu telemetry và phục hồi đúng | Collector backlog, clock drift, audit gaps |

Không chỉ kiểm tra **ping**. ICMP còn thông nhưng DNS, TCP, TLS, HTTP, VPN hoặc kết nối DB có thể không hoạt động. Ngược lại, ping bị chặn đúng policy không chứng minh HA thất bại.

### 14.1. Đo gián đoạn đầu cuối

Ghi ít nhất bốn mốc thời gian:

~~~text
t0 = thời điểm sự cố bắt đầu
t1 = HA phát hiện lỗi và bầu node tiếp quản
t2 = routing/ARP/ND hội tụ, có thể forward packet
t3 = giao dịch ứng dụng đầu tiên thành công trở lại

Thời gian phát hiện      = t1 - t0
Thời gian hội tụ         = t2 - t1
Thời gian hồi phục app   = t3 - t0
~~~

**t3 - t0 là giá trị quan trọng đối với người dùng**, nhưng cần ghi rõ cách định nghĩa giao dịch thành công, tần suất probe, timeout và cơ chế retry. Khi một phần request thành công trước khi toàn bộ hệ thống ổn định, nên đo thêm **mất gói/phiên, lỗi HTTP, latency và thời điểm phục hồi ổn định**.

### 14.2. Công cụ quan sát

Tùy sản phẩm, sử dụng giao diện/CLI **chỉ đọc** để quan sát:

- Cluster role, peer connectivity, HA election reason, last failover time.
- Config synchronization status và chênh lệch phiên bản policy.
- Session count, sync queue/backlog, NAT mapping, VPN SA.
- Interface/route/BGP/OSPF/BFD status, ARP/ND và MAC table.
- Firewall rule hits, denied flows, IPS events, TLS/VPN errors.
- Synthetic monitor nhìn từ **ngoài** và **trong** vùng bảo vệ.

Đối với các lệnh thật phải tra hướng dẫn theo hãng và firmware; một chuỗi lệnh “show ha” chung không thể áp dụng chính xác cho mọi firewall.

## 15. Thực hành tại máy cục bộ: phân tích log failover mô phỏng

Ví dụ Python dưới đây **chỉ xử lý sự kiện giả lập**, không truy cập firewall, không tạo gói tin và không thực hiện chuyển đổi role. Nó giúp thực hành đo khoảng thời gian từ sự cố đến khi API phục hồi.

~~~python
from datetime import datetime, timezone

# Mốc thời gian giả lập: UTC, định dạng ISO 8601.
events = [
    {"time": "2026-01-10T09:00:00.000Z", "event": "failure_started"},
    {"time": "2026-01-10T09:00:01.100Z", "event": "standby_elected"},
    {"time": "2026-01-10T09:00:02.400Z", "event": "path_converged"},
    {"time": "2026-01-10T09:00:03.000Z", "event": "api_healthy"},
]


def parse_utc(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return result.astimezone(timezone.utc)


times = {row["event"]: parse_utc(row["time"]) for row in events}
detect = times["standby_elected"] - times["failure_started"]
converge = times["path_converged"] - times["standby_elected"]
recover = times["api_healthy"] - times["failure_started"]

assert times["failure_started"] <= times["standby_elected"]
assert times["standby_elected"] <= times["path_converged"]
assert times["path_converged"] <= times["api_healthy"]

print(f"Detection/election: {detect.total_seconds():.1f}s")
print(f"Path convergence:  {converge.total_seconds():.1f}s")
print(f"App recovery:      {recover.total_seconds():.1f}s")
~~~

Kết quả dự kiến:

~~~text
Detection/election: 1.1s
Path convergence:  1.3s
App recovery:      3.0s
~~~

**Giới hạn:** Thời gian trong bài lab được đặt sẵn để minh họa. Trong môi trường thực, cần thu dữ liệu từ **client hoặc synthetic monitor** và thiết bị theo nguồn đồng hồ đã đồng bộ; log từ hai node có thể lệch thời gian. Giá trị failover phải đo qua nhiều lần với nhiều kiểu traffic và tải khác nhau, đồng thời ghi percentile và số session mất, không chỉ lấy một lần đo “đẹp”.

### Bài tập mở rộng

1. Thêm sự kiện **vpn_reconnected** sau **api_healthy**; tính thời gian hồi phục riêng của VPN.
2. Thêm một sự cố có **path_converged** nhanh nhưng **api_healthy** muộn; thảo luận nguyên nhân ở client, NAT, TLS, DB hoặc ứng dụng.
3. Tạo ba lần failover giả lập; tính median và giá trị lớn nhất của thời gian phục hồi ứng dụng.
4. Định nghĩa hai nhóm test: **ALLOW hợp lệ** và **DENY bắt buộc**, rồi giải thích vì sao phải kiểm tra cả hai sau failover.

## 16. Case study: HA vẫn gián đoạn vì đường đi bất đối xứng

**Bối cảnh giả định:** Doanh nghiệp dùng hai firewall FW-A/FW-B ở hai vị trí khác nhau trong trung tâm dữ liệu. Kết nối Internet đi qua hai router chạy ECMP. Ứng dụng Web đặt sau firewall; thiết bị đã bật session sync ở mức hỗ trợ. Khi FW-A bị lỗi, FW-B chuyển sang xử lý luồng mới nhưng một phần kết nối TCP liên tục reset.

~~~text
                    Router 1 ---- FW-A ----+
Client Internet ----                     +---- App server
                    Router 2 ---- FW-B ----+

Nguyên nhân đang nghi ngờ:
  Traffic chiều đi sau failover chọn FW-B.
  Traffic trả về có lúc vẫn đi qua đường/route gắn với FW-A,
  hoặc mapping/session trên FW-B không đủ để duy trì phiên cũ.
~~~

### 16.1. Phân tích theo các lớp

| Lớp | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Health/election** | FW-B có thực sự trở thành owner hợp lệ của luồng? | Role/election logs |
| **Routing** | Route/ECMP hash ở cả hai chiều đã cập nhật chưa? | BGP/OSPF/route table, flow path |
| **NAT** | Public IP/port của phiên được giữ hay thay đổi? | NAT translation state |
| **Session** | FW-B có state của phiên đang diễn ra? | Session table, sync metrics |
| **Policy** | Rule và security profile nào áp dụng trên FW-B? | Policy logs/config sync |
| **Ứng dụng** | Client có reconnect hoặc retry an toàn không? | HTTP/TCP errors, application traces |

### 16.2. Hướng khắc phục

1. Kiểm tra thiết kế **return path** và đặc tính ECMP; áp dụng cơ chế đảm bảo symmetry/flow ownership được hãng hỗ trợ.
2. Điều chỉnh routing và health tracking để route bị lỗi bị withdraw theo đúng điều kiện, tránh tiếp tục đẩy traffic vào node không khỏe.
3. Xác minh NAT và session sync cho kiểu traffic cụ thể; đánh dấu các phiên **không thể giữ** để ứng dụng chủ động reconnect khi cần.
4. Thực hiện failover test bằng HTTP/TLS và giao dịch thực tế trong lab, không kết luận dựa vào duy nhất ping.
5. Đặt cảnh báo cho session drops, routing convergence, IPsec renegotiation và tỷ lệ HTTP errors trong cửa sổ failover.

**Bài học:** Hai firewall hoạt động tốt và có heartbeat đầy đủ vẫn có thể không đạt mục tiêu HA nếu **routing, NAT, session ownership và ứng dụng** không thống nhất khi node tiếp quản.

## 17. Giám sát và bảo trì lâu dài

### 17.1. Các tín hiệu quan trọng

| Tín hiệu | Lý do cần theo dõi |
| --- | --- |
| Role/election history, số lần failover | Phát hiện flapping hoặc thay đổi ngoài lịch |
| HA heartbeat loss/latency, state sync backlog | Cảnh báo node dự phòng không sẵn sàng tiếp quản |
| Config checksum, firmware/signature version | Tìm policy drift và sự khác nhau giữa node |
| CPU, memory, session table, throughput, SSL/IPS load | Kiểm tra node còn sống có đủ headroom sau failover |
| Uplink status, BGP/OSPF/BFD peer, route health | Phát hiện lỗi đường đi ngoài phạm vi heartbeat |
| GARP/ND, MAC flapping hoặc VIP ownership | Phát hiện vấn đề hội tụ L2 hoặc split-brain |
| NAT allocation/translation errors | Tìm lỗi duy trì/thiết lập phiên sau chuyển đổi |
| VPN SA/tunnel availability, reconnect rate | Đo ảnh hưởng lên người dùng/tunnel từ xa |
| Synthetic transaction success, p95/p99 latency | Đo trải nghiệm đầu cuối, không chỉ health của firewall |
| Deny/allow logs và IPS events trước/sau failover | Kiểm tra tính đúng đắn của chính sách bảo mật |
| Audit log của quản trị và thay đổi cấu hình | Điều tra nguyên nhân và người thực hiện thay đổi |

### 17.2. Chuẩn bị năng lực N+1 và độ tin cậy

Nếu cụm có hai node cùng chạy bình thường và mỗi node đang sử dụng **75% năng lực xử lý đo tại tải có bật IPS**, việc mất một node có thể khiến node còn lại bị quá tải khi phải gánh toàn bộ traffic. Đừng cộng đơn giản throughput quảng cáo của thiết bị rồi cho rằng vẫn có đủ năng lực khi mất node.

Thiết kế phải xác minh **throughput khi bật security features, số concurrent connections, new sessions per second, VPN tunnel count và burst capacity** trong trạng thái suy giảm, có dự phòng tăng trưởng.

Một cách diễn đạt SLO:

~~~text
Trong bài diễn tập được phê duyệt:
- Node còn lại không vượt ngưỡng năng lực đã được kiểm chứng.
- Không có thay đổi quyền truy cập ngoài danh mục ALLOW đã duyệt.
- Mỗi lớp dịch vụ có mức gián đoạn và tỷ lệ phục hồi đo riêng.
- Những phiên không hỗ trợ stateful failover có phương án reconnect.
- Không mất khả năng ghi log/điều tra quá mức được phép.
~~~

### 17.3. Runbook tối thiểu

Runbook vận hành cần trả lời: ai có quyền chuyển vai trò, trạng thái khỏe trông như thế nào, bước nào xác minh peer và sync, khi nào **không** được failback, dấu hiệu split-brain, cách kiểm tra routing/NAT/VPN/IPS, tiêu chí rollback và cách liên hệ owner ứng dụng. Mọi thao tác phá kết nối thực tế cần theo quy trình thay đổi và kịch bản dự phòng đã được duyệt.

## 18. Những hiểu nhầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Có hai firewall là HA hoàn chỉnh.” | Còn phải dự phòng nguồn, switch, đường WAN, route, HA link và quản trị. |
| “Failover vài giây nghĩa là ứng dụng chỉ ngắt vài giây.” | Router, NAT, VPN, client và ứng dụng có thể hồi phục lâu hơn. |
| “Active/Active luôn nhanh và an toàn hơn.” | Cần cơ chế ownership, state và symmetry; vận hành có thể phức tạp hơn. |
| “VRRP tự đồng bộ phiên firewall.” | VRRP dự phòng gateway; stateful firewall sync là chức năng khác. |
| “Config sync chứng minh mọi rule đều đúng.” | Rule sai có thể được đồng bộ sang tất cả các node. |
| “Heartbeat UP nghĩa là hệ thống truy cập Internet bình thường.” | Uplink, route và ứng dụng có thể lỗi dù peer link khỏe. |
| “Session sync chắc chắn giữ mọi TCP/VPN/TLS phiên.” | Phụ thuộc loại phiên, phiên bản sản phẩm và khả năng đồng bộ. |
| “Một ISP dự phòng sẽ bảo vệ khi toàn bộ site mất điện.” | Sự cố hạ tầng/site đòi hỏi DR và dự phòng failure domain khác. |
| “Fail-open luôn tốt vì dịch vụ không ngắt.” | Có thể tạo đường vượt kiểm tra bảo mật; phải đánh giá rủi ro. |
| “Khi failover không cần kiểm tra các rule DENY.” | Node dự phòng có thể có drift và biến đổi đường đi; DENY là thuộc tính cần kiểm chứng. |
| “Cloud tự động HA khi chạy hai VM firewall.” | Route, health, state, traffic symmetry và quyền automation phải được thiết kế. |
| “Không thấy packet loss nghĩa là đạt HA.” | Phải đo thêm giao dịch ứng dụng, IPS/VPN, bảo mật và telemetry. |

## 19. Câu hỏi tự kiểm tra và bài tập thiết kế

1. **HA firewall khác dự phòng hai nguồn điện như thế nào?** Hai nguồn chỉ giảm một kiểu lỗi vật lý; HA cần phát hiện lỗi, chuyển traffic và duy trì ý định policy trên node còn lại.
2. **Khi nào Active/Passive phù hợp hơn Active/Active?** Khi cần thiết kế đơn giản, node standby đủ năng lực gánh tải, và không có nhu cầu/khả năng chia flow phức tạp.
3. **Heartbeat link lỗi có nhất thiết phải failover không?** Không. Cần dựa vào thiết kế election/quorum/fencing và tình trạng dataplane; tự chuyển cả hai active có thể gây split-brain.
4. **Vì sao failover TCP có thể rớt dù VIP được giữ nguyên?** State của phiên/NAT/inspection có thể không được đồng bộ hoặc route/neighbor cache chưa hội tụ.
5. **Có thể dùng VRRP thay cho session synchronization không?** Không. Chúng giải quyết các lớp vấn đề khác nhau.
6. **Làm sao bảo đảm chính sách DENY vẫn đúng?** Kiểm tra đồng bộ policy/zone, cấu hình thực thi, và thử các luồng đáng lẽ bị chặn trước/sau failover.
7. **Vì sao phải kiểm tra đường trả về khi có hai firewall hoặc ECMP?** Stateful firewall có thể loại packet đến node không sở hữu state của phiên.
8. **Một cụm HA cùng phụ thuộc một switch có rủi ro gì?** Switch trở thành điểm lỗi đơn lẻ khiến cả hai node không thể chuyển tiếp traffic.
9. **IPsec VPN có nhất thiết giữ kết nối sau failover không?** Không. Khả năng chuyển state hoặc tái thương lượng SA phụ thuộc sản phẩm và thiết kế tunnel.
10. **Sự khác nhau giữa t2 và t3 trong phép đo failover là gì?** t2 cho biết đường dữ liệu đã hội tụ; t3 cho biết giao dịch ứng dụng mới thành công trở lại.

### Bài tập tình huống

Một công ty có hai firewall, hai ISP, một switch nội bộ duy nhất, một HA link duy nhất và API Production nằm sau cụm. Đội vận hành thông báo “HA hoạt động” vì có thể tắt FW-A trong lab và FW-B chuyển role. Tuy nhiên, khách hàng vẫn ghi nhận lỗi HTTPS kéo dài và khi switch nội bộ lỗi thì toàn hệ thống mất kết nối.

Hãy thiết kế phương án:

1. Vẽ các **failure domain** và chỉ ra ít nhất **ba điểm lỗi/điểm chưa kiểm chứng**.
2. Đề xuất mô hình kết nối và quản trị để giảm phụ thuộc switch, HA link và ISP.
3. Chỉ ra những state cần quan sát đối với **TLS/HTTPS, NAT, VPN và IPS**.
4. Xây dựng **ít nhất tám test**, có cả ALLOW, DENY, failover, split-brain prevention, đường trả về và hội tụ ứng dụng.
5. Đề xuất ba SLI để đo trải nghiệm ứng dụng và nêu yêu cầu rollback khi failover liên tục.
6. Giải thích vì sao thiết kế HA trong một site không tự thay thế multi-site DR.

## 20. Checklist review HA firewall

- [ ] Đã phân biệt rõ mục tiêu HA, SLO, RTO ứng dụng và nhu cầu DR?
- [ ] Đã chọn mô hình active/passive hoặc active/active được sản phẩm hỗ trợ?
- [ ] Đã xem xét khả năng node còn lại chịu toàn tải khi mất node?
- [ ] Đã kiểm tra nguồn, uplink, inside switch, ISP, HA link và site như các failure domain?
- [ ] Heartbeat, health probes và cơ chế election/quorum/fencing có được kiểm chứng?
- [ ] Cấu hình HA và session/NAT state sync có theo dõi lỗi, độ trễ và giới hạn?
- [ ] Có kiểm thử chính sách ALLOW **và** DENY trên node còn lại?
- [ ] Đã kiểm tra VIP/VMAC/GARP/ND hoặc routing/BGP/ECMP/VRF theo kiến trúc?
- [ ] Đã đánh giá luồng đi và về, symmetry, NAT/egress IP và trạng thái phiên?
- [ ] Đã kiểm tra IPsec VPN, remote VPN, IPS, TLS inspection, DNS và authentication?
- [ ] Mạng HA và quản trị được phân quyền, cách ly và giám sát?
- [ ] Cloud/hybrid routing và failover automation có quyền tối thiểu và audit?
- [ ] Đã có ma trận kiểm thử, thông số đo đầu cuối và kết quả diễn tập?
- [ ] Đã chuẩn bị runbook, backup cấu hình, quy trình nâng cấp và rollback?
- [ ] Đã theo dõi drift cấu hình, split-brain, link flapping và sự cố gián đoạn phiên?

**Kết luận:** HA firewall là **một kiến trúc bảo đảm đường dữ liệu và chính sách tiếp tục hoạt động khi thành phần gặp lỗi**, không chỉ là việc thêm thiết bị dự phòng. Muốn đạt mục tiêu thực tế phải phối hợp **heartbeat, election, state sync, routing/NAT, security policy, năng lực tải, ứng dụng và kiểm thử đầu cuối**. Chất lượng của thiết kế thể hiện qua cả hai kết quả: **dịch vụ hợp lệ hồi phục theo mục tiêu** và **những luồng không có quyền vẫn bị chặn sau failover**.
