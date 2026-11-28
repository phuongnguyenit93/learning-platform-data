# Asymmetric Routing: định tuyến bất đối xứng và an toàn luồng mạng

## 1. Asymmetric routing là gì?

**Asymmetric routing (định tuyến bất đối xứng)** xảy ra khi **đường đi của lưu lượng từ A đến B khác với đường đi của lưu lượng từ B về A**. Hai đường có thể đi qua các router, ISP, vùng mạng hoặc thiết bị bảo mật khác nhau. Đây là đặc điểm có thể xuất hiện bình thường trong mạng IP lớn; **bản thân bất đối xứng không đồng nghĩa với tấn công hoặc lỗi cấu hình**.

Ví dụ, một máy khách tại chi nhánh gửi yêu cầu đến ứng dụng trong data center qua đường WAN 1, nhưng gói trả lời được định tuyến qua đường WAN 2. Nếu cả hai đường đều hoạt động và không có thiết bị phụ thuộc trạng thái của phiên, kết nối vẫn có thể thành công. Tuy nhiên, nếu gói đi qua **firewall stateful A** trong khi gói trả về chỉ đi qua **firewall stateful B**, thiết bị B có thể không có trạng thái phiên cần thiết để chấp nhận gói trả lời.

Trong module **SECURITY_NETWORK_SECURITY**, hiểu asymmetric routing là yêu cầu quan trọng khi thiết kế **phân đoạn mạng, firewall, VPN, IDS/IPS, kiểm soát nguồn IP, giám sát xâm nhập, bảo vệ DNS và hệ thống cloud/hybrid**. Chủ đề này nối kiến thức về bảng định tuyến với **trust boundary**: đường đi có thể đúng theo routing protocol nhưng không phù hợp với nơi cần thực thi chính sách an ninh.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt đường **forward** và **return**, hiểu vì sao IP routing không đòi hỏi hai chiều phải theo cùng một tuyến.
2. Nhận diện tình huống bất đối xứng do **BGP, OSPF, ECMP, PBR, VRF, NAT, VPN, HA và cloud routing**.
3. Phân tích ảnh hưởng lên **stateful firewall, connection tracking, IPS, IDS và NAT**.
4. Hiểu kiểm tra địa chỉ nguồn **uRPF** và lý do strict uRPF có thể chặn lưu lượng hợp lệ.
5. Đọc dấu hiệu kỹ thuật và lập quy trình chẩn đoán có bằng chứng, không nhầm ping/traceroute với chân lý tuyệt đối.
6. Chọn phương án xử lý bảo toàn **least privilege**, không vô hiệu hóa kiểm tra bảo mật chỉ để lưu lượng đi qua.
7. Thiết kế ma trận test và giám sát đường đi trước/sau failover.

## 2. Hiểu đường đi forward và return

Xét một kết nối TCP từ client tới server:

~~~mermaid
flowchart LR
    C["Client 10.10.10.10"] -->|"Forward: TCP SYN/HTTP request"| FA["Firewall A"]
    FA --> S["Server 192.0.2.20"]
    S -->|"Return: SYN-ACK/HTTP response"| FB["Firewall B"]
    FB --> C
~~~

Trong sơ đồ, chiều đi **Client → Firewall A → Server**, còn chiều về **Server → Firewall B → Client**. Nếu A và B là hai firewall stateful độc lập, B có thể nhận **SYN-ACK** nhưng không có bản ghi **SYN** đã đi qua A; kết quả có thể là **drop/invalid session** tùy thiết bị và chính sách.

Một phiên TCP được nhận diện phổ biến theo **5-tuple**:

~~~text
Source IP       10.10.10.10
Source port     51324
Destination IP  192.0.2.20
Destination port 443
Protocol        TCP

Chiều trả lời sẽ hoán đổi source/destination IP và port,
nhưng vẫn thuộc cùng kết nối xét theo trạng thái phiên.
~~~

**Quan trọng:** Định tuyến bất đối xứng thường nói về **tuyến theo hai chiều giao tiếp**, không nhất thiết mỗi packet sẽ theo đúng một đường cố định. Khi ECMP, thay đổi topology, congestion policy hoặc failover tác động, đường đi của các gói hoặc các luồng có thể thay đổi theo thời gian.

### 2.1. Symmetric và asymmetric routing

| Tiêu chí | Đường đối xứng | Đường bất đối xứng |
| --- | --- | --- |
| Lộ trình | Hai chiều đi qua các điểm kiểm soát tương ứng | Hai chiều có ít nhất một đoạn/thiết bị khác nhau |
| Router IP thông thường | Có thể hoạt động | Có thể hoạt động |
| Stateful firewall độc lập | Thường dễ có trạng thái đầy đủ | Có nguy cơ gói một chiều bị coi không hợp lệ |
| NAT/PAT có state | Mapping thường có thể dùng cả hai chiều | Return traffic có nguy cơ không đi qua thiết bị giữ translation |
| NIDS ngoài luồng | Có thể thấy đủ hai chiều nếu đặt đúng | Có thể chỉ thấy một chiều, giảm ngữ cảnh |
| Vận hành | Dễ truy vết một số topology | Cần quan sát cả hai hướng và nhiều control point |

**Không đồng nhất path symmetry với session continuity.** Hai chiều cùng đi qua một firewall vẫn có thể bị gián đoạn do ACL, NAT, MTU, timeout, TLS hoặc ứng dụng. Ngược lại, kiến trúc bất đối xứng được thiết kế có kiểm soát vẫn có thể hoạt động nếu thiết bị đúng chức năng và bảo toàn state.

## 3. Vì sao Internet và mạng nội bộ có thể đi bất đối xứng?

Router IP thường chọn **đường đi tới địa chỉ đích** dựa trên routing table/FIB và chính sách riêng của router. Router phía A và phía B không nhất thiết sở hữu cùng metric, cùng tuyến được công bố hay cùng chính sách định tuyến.

### 3.1. Những yếu tố thường gây khác tuyến

| Nguyên nhân | Cơ chế | Ví dụ |
| --- | --- | --- |
| **BGP policy** | LOCAL_PREF, AS_PATH, MED, communities, chính sách inbound/outbound và chọn next hop | Data center ưu tiên ISP 1 khi gửi, đối tác trả qua ISP 2 |
| **IGP metric (OSPF/IS-IS)** | Cost tới các đích khác nhau và topology khác nhau | Chiều đi ưu tiên router A, chiều về ưu tiên router B |
| **ECMP** | Nhiều đường có chi phí tương đương; hashing theo flow tùy nền tảng | Một số kết nối được đặt qua firewall A, một số qua B |
| **Policy-Based Routing (PBR)** | Chọn next hop theo source/port/DSCP/app/policy thay vì chỉ destination | Traffic đi từ subnet Dev bị đẩy qua inspection gateway riêng |
| **VRF / route leaking** | Nhiều bảng định tuyến và chỗ chuyển miền | Forward vào VRF app, return thoát qua VRF shared |
| **NAT / proxy / load balancer** | Thay địa chỉ đích/nguồn hoặc nguồn tuyến được xử lý | Reply chọn route theo IP được SNAT khác đường request |
| **BGP/OSPF convergence & HA** | Route đổi khi link/node mất, peer hội tụ không cùng lúc | Chuyển firewall active, return path chưa cập nhật |
| **Dual ISP/multi-homing** | Các mạng tự chọn đường ra/vào không giống nhau | Request đi WAN-A nhưng response về WAN-B |
| **Cloud route table/service insertion** | Subnet, AZ, transit hub hoặc appliance có chính sách riêng | Egress qua firewall AZ-A, ingress trả về AZ-B |
| **SD-WAN / VPN** | Chọn tunnel theo policy, chất lượng link hoặc failover | Request đi tunnel chính, reply đi tunnel dự phòng |

**BGP không bảo đảm tuyến hai chiều đối xứng**: mỗi hệ tự trị điều khiển lựa chọn riêng và có thể chịu quyết định của mạng bên ngoài. Một cấu hình tăng LOCAL_PREF ở tổ chức A chủ yếu tác động **lựa chọn đường ra trong AS A**, không ép mạng bên ngoài trả traffic theo cùng đường.

### 3.2. Đừng nhầm với longest-prefix match

**Longest Prefix Match (LPM)** là nguyên tắc chọn tuyến tới đích khớp với prefix cụ thể hơn trong bảng forwarding. Nó **không bắt buộc** chiều về phải theo cùng thiết bị.

~~~text
Router X:
  192.0.2.0/24  -> next-hop via FW-A
  0.0.0.0/0     -> ISP-1

Router Y:
  10.10.10.0/24 -> next-hop via FW-B
  0.0.0.0/0     -> ISP-2

Kết quả:
  X tới server dùng FW-A.
  Y tới client dùng FW-B.
~~~

LPM chỉ là một phần của forwarding decision; trong mạng thật còn có **policy routing, VRF, route preference/administrative distance, ECMP và xử lý tunnel**. Cần xem **effective forwarding path**, không suy từ một tuyến trên một router duy nhất.

## 4. Khi nào bất đối xứng là bình thường, khi nào thành sự cố?

Một mạng IP stateless có thể chuyển gói theo các đường khác nhau mà vẫn hoạt động, miễn gói tới đúng đích. Nhiều đường Internet vốn đã không đối xứng giữa các AS.

**Bất đối xứng là vấn đề an ninh/vận hành khi**:

- Thiết bị trên một chiều phải thấy gói trước đó để quyết định **stateful allow/deny**.
- NAT/PAT hoặc proxy có mapping được lưu ở thiết bị khác và không thể truy cập mapping đó.
- IPS/IDS cần đủ hai chiều hoặc stream reassembly để hiểu giao thức/phiên.
- Chính sách chống giả mạo IP kiểm tra **reverse path** theo interface không khớp tuyến hợp lệ.
- Một đường bypass khiến luồng vượt qua **điểm kiểm soát bắt buộc** (firewall, inspection, logging, data-loss controls).
- Chiều về bị đổi sang VPN/site/region không có quyền hoặc không có route tới nguồn.
- Cần chẩn đoán sự cố, nhưng công cụ chỉ quan sát một chiều và kết luận sai.

**Bất đối xứng không phải lỗ hổng bảo mật tự thân.** Một mạng có thể dùng nhiều đường theo thiết kế, miễn các ranh giới bắt buộc vẫn được thực thi, phiên có cơ chế xử lý phù hợp và đường đi có thể được kiểm chứng.

## 5. Stateful firewall và connection tracking

### 5.1. Vì sao session state quan trọng?

Một firewall stateful thường tạo bản ghi phiên khi gói khởi tạo được chấp nhận; sau đó những gói chiều về có thể được xác định là thuộc cùng phiên.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant FA as Firewall A
    participant FB as Firewall B
    participant S as Server
    C->>FA: TCP SYN
    FA->>S: SYN (state tạo trên A)
    S->>FB: TCP SYN-ACK (return qua B)
    Note over FB: B không thấy SYN và không có state tương ứng
    FB--xC: Có thể DROP vì invalid/no session
    Note over C,S: TCP handshake thất bại hoặc phải retransmit
~~~

Kết quả phụ thuộc platform và cấu hình: một số firewall cho phép xử lý bất đối xứng trong những trường hợp nhất định, có cơ chế **state sharing, asymmetric session support hoặc flow redirection**. Nhưng không nên bật chế độ bỏ kiểm tra chỉ để làm flow đi qua khi nguyên nhân gốc là routing sai.

### 5.2. Stateless ACL và stateful inspection khác nhau

**Stateless ACL** quyết định trên từng gói dựa trên nguồn, đích, protocol, port và rule; nó không cần biết trạng thái TCP theo nghĩa đầy đủ. Tuy nhiên, nếu muốn cho traffic trả về, chính sách stateless có thể phải cho phép **chiều về** một cách rõ ràng. Nếu luật ngược quá rộng, có thể tăng bề mặt tấn công.

**Stateful firewall** giữ ngữ cảnh phiên, nên không chỉ đọc header hiện tại. Bất đối xứng có thể làm mất dữ liệu phiên cần thiết ở thiết bị đang nhận gói.

| Mô hình | Đường về khác thiết bị | Điều phải bảo đảm |
| --- | --- | --- |
| Stateless ACL hai chiều | Có thể hợp lệ | Cả hai phía có rule cho phép đúng phạm vi, chống spoofing phù hợp |
| Stateful FW A/P cùng cụm | Phụ thuộc vai trò/khả năng sync | Node nhận traffic có state hoặc cơ chế xử lý do hãng hỗ trợ |
| Hai stateful FW độc lập | Thường có nguy cơ drop return | Hướng traffic đồng nhất hoặc state/flow ownership được xử lý đúng |
| Active/Active firewall | Tùy cluster và policy engine | Session owner, symmetry/affinity, đồng bộ đúng loại trạng thái |
| Proxy/tường lửa ứng dụng | Có thể tạo hai kết nối độc lập | Mỗi chặng được xác thực, kiểm tra và định tuyến phù hợp |

### 5.3. Các biểu hiện thường gặp

- TCP SYN xuất hiện trước firewall A, nhưng SYN-ACK xuất hiện ở firewall B rồi bị drop.
- Firewall/conntrack log báo **invalid state**, **no matching session**, **out-of-state packet** hoặc tên thông báo tương đương.
- TCP retransmission tăng, handshake timeout, kết nối ngắt từng lúc.
- Một nhóm source/destination hoạt động, nhóm khác lỗi do ECMP hash chọn đường khác.
- Sau failover hoặc route change, kết nối mới hoạt động nhưng session cũ reset (hoặc ngược lại).

**Cảnh báo:** Những triệu chứng trên không độc quyền cho asymmetric routing. Một rule deny, lỗi NAT, packet loss, TLS, MTU hoặc thiết bị quá tải cũng có thể tương tự. Cần xác minh cả **đường đi và trạng thái phiên** trước khi kết luận.

## 6. NAT/PAT: bất đối xứng có thể phá mapping

NAT thay đổi địa chỉ/port trên luồng và thường duy trì mapping theo phiên. Nếu request được NAT ở firewall A nhưng response quay về firewall B không có translation tương ứng, B khó biết **đích nội bộ** của gói trả lời.

~~~text
Trước NAT trên FW-A:
  Client: 10.10.10.10:51324
  Server: 203.0.113.20:443

FW-A tạo PAT:
  10.10.10.10:51324 -> 198.51.100.10:40201
  Gửi tới 203.0.113.20:443

Server trả lời:
  203.0.113.20:443 -> 198.51.100.10:40201

Nếu reply chỉ đến FW-B:
  FW-B không biết mapping cổng 40201 -> 10.10.10.10:51324,
  trừ khi mapping/state đã được đồng bộ hoặc traffic được
  đưa về FW-A theo cơ chế được hỗ trợ.
~~~

Các địa chỉ **198.51.100.0/24** và **203.0.113.0/24** thuộc dải tài liệu TEST-NET. Ví dụ này chỉ trình bày logic, không phải một route cấu hình có thật.

### 6.1. SNAT để ép traffic quay về có phải giải pháp tốt?

Trong một số kiến trúc proxy, load balancer hoặc dịch vụ nội bộ, **SNAT** được dùng có chủ đích để buộc response quay về thiết bị trung gian. Nó có thể giúp điều khiển đường đi nhưng có đánh đổi:

- Ứng dụng có thể chỉ thấy **địa chỉ dịch của gateway**, không thấy nguồn thật.
- Log, rate limit, phát hiện tấn công và danh tính người dùng cần nguồn metadata khác được bảo vệ.
- NAT state trở thành dependency và có thể cạn port/connection.
- Một số protocol hoặc cơ chế xác thực có ràng buộc với địa chỉ nguồn, nên thay địa chỉ có thể gây lỗi.

SNAT không thay cho việc sửa route và không phải lựa chọn mặc định cho mọi case. Trước khi áp dụng cần hiểu **cả hai chiều, mapping ownership, HA state và các điều kiện kiểm soát truy cập**.

### 6.2. Trường hợp có static NAT hoặc no-NAT

Không có PAT động không có nghĩa bất đối xứng vô hại: firewall vẫn có thể theo dõi trạng thái TCP; static NAT cũng cần được định nghĩa ở điểm có thể xử lý đúng cả chiều đi/về. Nếu mỗi đầu tunnel áp dụng **NAT exemption/no-NAT**, cần kiểm chứng rule đó áp dụng cho đúng prefix/traffic selector và sau khi failover không đổi.

## 7. ECMP, hashing và phân phối luồng

**Equal-Cost Multi-Path (ECMP)** cho phép router phân phối traffic trên nhiều next hop có chi phí tương đương. Nhiều nền tảng chọn next hop dựa trên **hash của các trường gói** (ví dụ IP nguồn/đích, protocol, port), thường nhằm giữ các gói của cùng một flow qua một nhánh tại router đó.

~~~text
                  +---- FW-A ----+
Client --- R1 ----|              |---- R2 --- Server
                  +---- FW-B ----+

R1 chọn FW-A cho chiều Client -> Server.
R2 không nhất thiết dùng cùng hash/next hop cho chiều
Server -> Client; return có thể được chọn qua FW-B.
~~~

**Per-flow hashing không bảo đảm đối xứng hai chiều.** Hash input bị đảo nguồn/đích, đường mạng hai phía có thể có tập next hop, seed hoặc implementation khác. Thêm/loại một đường ECMP có thể **re-hash** một số flow đang hoạt động và làm mất state nếu traffic chuyển tới thiết bị không sở hữu phiên.

| Cơ chế | Cần kiểm tra |
| --- | --- |
| Per-flow ECMP | Flow key, hashing algorithm/seed, danh sách next hop, mức ổn định khi thay đổi |
| Per-packet load balancing | Nguy cơ đảo thứ tự gói, ảnh hưởng performance và reassembly; có thể không phù hợp stateful inspection |
| Flow affinity / stickiness | Chỉ định cả hai chiều tới node giữ state hoặc cơ chế steering phù hợp |
| Stateful cluster | Sync/ownership có hỗ trợ loại session, NAT, IPS, VPN cần bảo toàn hay không |
| LAG/port-channel | Hash ở lớp liên kết; không được nhầm việc dùng LAG với state sharing giữa firewall |
| Route convergence | Thay đổi ECMP next hop có làm flow cũ đổi đường đột ngột không |

Một thiết kế active/active firewall chỉ thực sự phù hợp nếu **thiết bị và router/load balancer được phối hợp** cho lưu lượng đi-về, state và route. Không coi hai firewall đứng cạnh hai đường ECMP là một cluster tự động đồng bộ.

## 8. BGP, multi-homing và các tuyến Internet

Ở biên mạng có hai ISP, đường đi từ tổ chức ra Internet và đường trả về được quyết định bởi **những hệ thống mạng khác nhau**.

~~~mermaid
flowchart TD
    C["Corporate AS"] -->|"Outbound ưu tiên"| ISP1["ISP 1"]
    C -. "Đường thay thế" .-> ISP2["ISP 2"]
    ISP1 --> I["Internet peers"]
    ISP2 --> I
    I -->|"Inbound do AS khác chọn"| ISP2
    ISP2 --> C
~~~

Ví dụ: Corporate AS chọn ISP 1 do **LOCAL_PREF** của tuyến đi tới đích cao hơn. Nhưng peer khác trên Internet có thể chọn trả về qua ISP 2 dựa trên policy, quảng bá prefix và tuyến của họ.

### 8.1. Những thuộc tính BGP liên quan

| Khái niệm | Ảnh hưởng chủ yếu |
| --- | --- |
| **LOCAL_PREF** | Ưu tiên đường ra trong AS đang áp dụng chính sách |
| **AS_PATH** | Một yếu tố ảnh hưởng chọn route giữa các AS; AS-path prepending có thể tác động lựa chọn của mạng khác nhưng **không bảo đảm** |
| **MED** | Gợi ý lựa chọn điểm vào cho AS láng giềng trong các điều kiện nhất định; không có hiệu lực phổ quát |
| **Communities/provider policy** | Điều khiển cách provider xử lý route theo hợp đồng/chính sách hỗ trợ |
| **More-specific route advertisement** | Có thể ảnh hưởng inbound path, nhưng chịu prefix filtering, yêu cầu định tuyến hợp lệ và tác động tới toàn Internet |
| **BGP failover/convergence** | Đường vào/ra có thể đổi ở những thời điểm khác nhau |

**Không dùng thay đổi BGP production như phép thử tự phát.** Công bố sai prefix, thao tác route leak hoặc điều chỉnh thuộc tính khi chưa có kế hoạch có thể làm gián đoạn rộng. Cần xét route filtering, nguồn prefix hợp lệ, RPKI/ROV, giám sát BGP và rollback.

### 8.2. Route origin security không giải quyết tất cả bất đối xứng

**RPKI Route Origin Validation (ROV)** giúp kiểm tra liệu một AS có được phép quảng bá một prefix theo ROA hay không, nhưng **không xác thực toàn bộ AS_PATH**, không ngăn mọi dạng route hijack và không bảo đảm path symmetry. Nó là một lớp bảo vệ định tuyến khác với bảo toàn phiên firewall.

**BGPsec**, khi được triển khai trong phạm vi hỗ trợ, hướng tới bảo vệ một số tính chất của AS-path; việc triển khai, giới hạn và khả năng tương thích cần xem theo hạ tầng thật. Không suy từ việc một route “valid” theo RPKI rằng đường hai chiều là an toàn hoặc đối xứng.

## 9. Bất đối xứng khi HA/failover

HA firewall và router redundancy thường chuyển vai trò, cập nhật **VRRP, VIP/VMAC, ARP/ND hoặc định tuyến động**. Một node tiếp quản nhanh không bảo đảm tất cả router/host đã cập nhật đường đi hoặc state ngay cùng lúc.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as FW-A (trước lỗi)
    participant B as FW-B (sau lỗi)
    participant R as Router/Upstream
    participant S as Server
    C->>A: Kết nối mới qua A
    A->>S: Forward, tạo state
    Note over A,B: Sự cố xảy ra / election
    B->>R: Nhận role và cập nhật đường đi
    S->>R: Response trên đường return
    R->>B: Chuyển tới B theo route mới
    Note over B: Có thể cần session/NAT state đã sync
    B-->>C: Chấp nhận hoặc drop/tái lập theo khả năng
~~~

### 9.1. Những lớp phải kiểm chứng

1. **Election/ownership:** Chỉ node hợp lệ tiếp quản, không split-brain.
2. **Symmetry/flow steering:** Router hai bên cùng chuyển các flow phù hợp tới owner.
3. **State sync:** Phiên TCP/UDP, NAT, VPN hoặc app inspection có được chuyển theo sản phẩm hỗ trợ không.
4. **Route/GARP/ND convergence:** Đường thực thi thay đổi kịp thời, không loop hay stale MAC/neighbor cache.
5. **Security profile/policy sync:** ALLOW/DENY, IPS, TLS và user identity không drift.
6. **Application recovery:** Client có thể phải reconnect dù dataplane đã hồi phục.

Đừng chỉ kiểm tra **role active** và **ping** rồi kết luận HA tốt. Đo **giao dịch HTTP, DNS, VPN, session reset, route và bảo toàn policy DENY** ở cả hai phía trước/sau failover.

## 10. Reverse Path Forwarding (uRPF) và chống spoofing

**Unicast Reverse Path Forwarding (uRPF)** là một kỹ thuật kiểm tra địa chỉ nguồn: thiết bị sử dụng thông tin định tuyến ngược về **source IP** để đánh giá gói nhận vào có hợp lệ theo policy kiểm tra hay không. Nó giúp giảm **source-address spoofing**, nhưng cấu hình không phù hợp có thể loại lưu lượng chính đáng trong topology bất đối xứng.

### 10.1. Strict và loose uRPF

| Chế độ | Cách diễn giải khái quát | Rủi ro/giới hạn |
| --- | --- | --- |
| **Strict uRPF** | Đường tốt nhất quay về địa chỉ nguồn phải đi ra đúng interface mà gói đi vào, theo mô hình nền tảng | Có thể drop traffic hợp lệ nếu inbound và reverse best path khác nhau |
| **Loose uRPF** | Có route tới địa chỉ nguồn được xem là hợp lệ theo điều kiện nền tảng, thường không bắt buộc đúng ingress interface | Ít nhạy với bất đối xứng, nhưng ngăn spoofing yếu hơn strict; default route có thể ảnh hưởng |
| **Feasible-path / biến thể theo vendor** | Có thể chấp nhận một tập đường quay về khả thi thay vì chỉ best path, nếu được hỗ trợ | Phụ thuộc FIB/RIB, platform và định nghĩa chính xác |
| **Explicit source ACL / anti-spoofing policy** | Kiểm tra những source prefixes được phép từ từng kết nối/tenant | Cần cập nhật khi topology hoặc allocation thay đổi |

### 10.2. Ví dụ false drop với strict uRPF

~~~text
Router biên có hai ISP:

Packet hợp lệ tới từ source 203.0.113.20 qua interface ISP-B.

Lookup route ngược tới 203.0.113.20:
  Best path theo FIB hiện tại đi ra interface ISP-A.

Strict uRPF trên interface ISP-B:
  Có thể DROP vì reverse best path không phải ISP-B.

Loose uRPF:
  Có thể PASS nếu source có route hợp lệ, tùy chính sách.
~~~

**Điểm cần phân biệt:** Một gói bị strict uRPF loại **không tự chứng minh đó là gói giả mạo**; cũng có thể do bất đối xứng hợp lệ. Loose uRPF **không đủ** để kiểm tra chống spoofing khi bảng định tuyến chứa default route hoặc nhiều source không nên xuất hiện; cần source ACL theo interface, validation phía nguồn và monitoring.

**BCP 38/84** định hướng các biện pháp lọc địa chỉ nguồn giả mạo phù hợp mạng. Lựa chọn strict/loose/ACL phải dựa vào vai trò interface (access, transit, peering, customer), route topology và chính sách ISP. Không tắt toàn bộ anti-spoofing chỉ để giải quyết một lỗi nghi ngờ.

## 11. IDS/IPS, NDR và những vùng mù do chỉ thấy một chiều

**Network IDS (NIDS)** thường quan sát packet qua TAP/SPAN, traffic mirroring hoặc kết nối đến sensor. Nếu đường request qua sensor A nhưng reply đi một nhánh khác, sensor A có thể chỉ nhìn thấy **một nửa phiên**.

Hậu quả có thể gồm:

- Không tái dựng được đầy đủ **TCP handshake, HTTP request/response, protocol state**.
- Chữ ký yêu cầu **established flow** hoặc chiều client/server không match đúng.
- Alert tăng giả do gói reply trông như **out-of-state** hoặc thiếu ngữ cảnh.
- **False negative** vì signature trong response hoặc chuỗi nhiều packet không được sensor nhận.
- Flow logs cho biết bytes chỉ theo một chiều, làm thống kê exfiltration hoặc throughput sai.
- Các phép đo về session duration, retry, reset có độ tin cậy thấp khi đường đi thay đổi.

### 11.1. Đặt cảm biến có chủ đích

~~~mermaid
flowchart TB
    C["Client"] --> R1["Router/Path A"]
    R1 --> S["Server"]
    S --> R2["Router/Path B"]
    R2 --> C
    R1 -. "Mirror forward" .-> N1["Sensor A"]
    R2 -. "Mirror return" .-> N2["Sensor B"]
    N1 --> CEN["Flow correlation / SIEM"]
    N2 --> CEN
~~~

Một hệ thống có thể đặt sensor tại **điểm hội tụ có cả hai chiều** hoặc thu telemetry từ **hai nhánh** rồi correlation. Tuy nhiên, **hai bản ghi NetFlow không đồng nghĩa một TCP stream đã được tái dựng đầy đủ**; điều này phụ thuộc công cụ, packet visibility, đồng bộ thời gian, flow key và NAT mapping.

### 11.2. NIDS khác IPS inline

- **NIDS passive:** Không trực tiếp làm rơi packet thông qua đường capture thông thường, nhưng vùng mù ảnh hưởng phát hiện.
- **IPS inline:** Nếu việc kiểm tra phụ thuộc stream state, đường bất đối xứng có thể dẫn tới **drop traffic hợp lệ** hoặc giảm hiệu quả phát hiện/chặn.
- **NGFW tích hợp IPS:** Firewall policy và inspection engine có thể cùng dựa trên session state; route đúng theo L3 vẫn có thể bị IPS/NGFW loại do không có ngữ cảnh.

Nếu cần hỗ trợ asymmetric flows trên một sản phẩm, phải xác minh **cách engine xử lý TCP stream, NAT, rule actions, flow ownership, nội dung TLS được giải mã và khả năng logging**. Không tắt stream inspection theo hướng mở rộng để “làm network chạy” khi chưa xác minh rủi ro.

## 12. VPN, IPsec, SD-WAN và định tuyến qua tunnel

Tunnel tạo một lớp đường đi khác: **outer IP header** đi qua ISP/WAN, còn **inner IP packet** chứa nguồn và đích của ứng dụng. Định tuyến bất đối xứng có thể xảy ra ở outer route, inner route hoặc cả hai.

~~~text
Client site A                         Service site B
  10.10.10.10                            10.20.20.20
       |                                        |
     VPN-A ====== Internet / WAN-1 ======== VPN-B
       \                                        /
        ======== Internet / WAN-2 ============

Chiều request chọn tunnel/WAN-1.
Chiều reply có thể chọn tunnel/WAN-2 theo policy/route khác.
~~~

### 12.1. Những điều kiện phải cùng đúng

| Thành phần | Cần xác minh |
| --- | --- |
| **Route tới subnet từ xa** | Forward và return tới đúng tunnel/next hop/VRF |
| **IPsec selectors / traffic selectors** | Inner source/destination được phép và tương ứng cả hai phía |
| **IKE/CHILD SA và anti-replay** | Tunnel/SA phù hợp với traffic, state và thiết kế đa đường |
| **NAT exemption / translation** | Các subnet cần đi qua tunnel có được no-NAT hoặc NAT đúng theo kế hoạch |
| **SD-WAN policy** | Application path, SLA probes, brownout/failover và cơ chế steering |
| **Firewall stateful** | Có session cho flow được nhận trên mỗi chiều hoặc state được chia sẻ đúng cách |
| **Tunnel monitoring** | Link UP có thực sự chở được traffic ứng dụng, không chỉ IKE liveness |

**Không mặc định hai tunnel hoạt động đồng thời có thể tùy ý chia request/reply.** Một giải pháp SD-WAN có thể hỗ trợ path steering và flow affinity theo thiết kế, nhưng với IPsec/cụm firewall khác nhau, tunnel traffic selector, session state và anti-replay có thể yêu cầu đường ổn định.

### 12.2. Triệu chứng sau chuyển đường SD-WAN

Ví dụ, đường WAN-1 mất chất lượng khiến thiết bị ở site A chuyển request sang WAN-2, nhưng site B chưa thay bảng routing return. HTTP có thể timeout dù VPN status đều **UP**. Cần đo **request flow, reply flow, SA counters, route/VRF và firewall policy hits** tại mỗi đầu. Không suy rằng lệnh ping một tunnel endpoint chứng minh ứng dụng đi đúng đường.

## 13. Cloud/hybrid routing và các điểm thực thi chính sách

Trong cloud, traffic có thể đi qua nhiều **route tables, peering/transit attachments, load balancers, gateway endpoints và virtual firewalls**. Hai subnet cùng VPC/VNet không nhất thiết có cùng route table hoặc cùng policy. Khi đặt firewall appliance ở giữa, đường về phải đi qua **thiết bị và tuyến phù hợp với khả năng state**.

### 13.1. Sơ đồ service insertion nhiều vùng

~~~mermaid
flowchart LR
    WA["Workload AZ-A"] --> RTA["Route table A"]
    RTA --> FWA["FW AZ-A"]
    FWA --> HUB["Transit / shared services"]
    HUB --> FWB["FW AZ-B"]
    FWB --> RTB["Route table B"]
    RTB --> WA
~~~

Đây là sơ đồ **cố ý bất đối xứng để phân tích nguy cơ**, không phải kiến trúc khuyến nghị. Nếu workload AZ-A gửi qua **FW AZ-A** nhưng return qua **FW AZ-B** độc lập, có thể thiếu session/NAT mapping. Với một số giải pháp load balancing dành cho network appliances, có cơ chế **flow stickiness/symmetry** hoặc stateful cluster; phải xem giới hạn cụ thể của dịch vụ và triển khai.

### 13.2. Cần kiểm tra những gì trên cloud?

1. **Route table gắn với từng subnet/AZ**, cùng hướng đích và cách lựa chọn route ưu tiên.
2. Đường **inbound/outbound** qua internet gateway, NAT gateway, transit gateway/hub, peering, firewall endpoint.
3. **Security Group/NSG/Network ACL**: mô hình allow/deny, statefulness và chiều áp dụng khác nhau theo nền tảng.
4. Lớp NAT và **flow/session ownership** của firewall appliance hoặc dịch vụ managed.
5. **Route propagation/attachment** có mở đường ngoài ý định giữa Dev, Staging, Prod không.
6. Các thay đổi **autoscaling, failover, zone outage** có đưa traffic qua node khác không.
7. **IPv4 và IPv6** có dùng cùng điểm kiểm soát hay một address family có đường bypass.
8. Log cho flow tại **trước và sau NAT**, đồng bộ timestamp và asset/cloud account metadata.

### 13.3. Kubernetes và CNI

Pod IP, Service IP, Node IP, egress gateway, overlay và NAT có thể làm **đường đi vật lý khác với đường logic giữa service**. Một request Pod A → Service B có thể được chuyển đến Pod backend cụ thể theo cơ chế CNI/kube-proxy/service load balancer; chiều reply có thể đi qua node/gateway khác theo cách định tuyến.

**NetworkPolicy chuẩn** thường là bộ quy tắc L3/L4 theo Pod/namespace/IPBlock, nhưng cách thực thi phụ thuộc CNI. Không suy rằng namespace tự tạo đường đối xứng, hoặc một service VIP đồng nghĩa traffic đã qua firewall được thiết kế. Khi chẩn đoán, cần phân biệt **inner Pod IP, node IP, overlay tunnel IP, Service VIP và SNAT**.

### 13.4. Hybrid network: cloud ↔ on-premises

Tổ chức kết nối private circuit và IPsec VPN dự phòng có thể có:

~~~text
On-premises -> Cloud: private circuit ưu tiên
Cloud -> On-premises: IPsec VPN vì route preference khác
~~~

Nhìn ở L3, kết nối có thể vẫn đến đúng mạng; nhưng một **firewall/NAT appliance** ở một nhánh không thấy return sẽ mất ngữ cảnh. Cần kiểm tra **BGP advertisements**, effective routes của mỗi đầu, traffic selectors, NAT exemption và các ranh giới cloud account/VRF.

**Điều cần tránh:** Tự thay default route của toàn VPC hoặc route propagation trong production để thử chẩn đoán khi chưa được phê duyệt. Thay đổi định tuyến có thể làm dịch vụ khác, đường quản trị và kết nối bảo vệ đi theo tuyến mới ngoài dự kiến.

## 14. Quy trình chẩn đoán asymmetric routing theo bằng chứng

Quy trình dưới đây phù hợp khi ứng dụng báo **TCP handshake timeout, intermittent drops, unexpected RST hoặc session invalid**. Chỉ thao tác trên hệ thống được phép quản trị, ưu tiên phép đọc/log trước.

### Bước 1. Xác định luồng chính xác

Ghi ít nhất:

~~~text
Incident / time UTC:        INC-EXAMPLE / 2026-01-10T09:30:00Z
Client IP:port:             10.10.10.10:51324
Server IP:port:             192.0.2.20:443
Protocol:                   TCP
Environment / VRF:          branch-users / vrf-users
Observed source before NAT: 10.10.10.10
Observed source after NAT:  [nếu có, xác minh qua log]
Symptoms:                   SYN retransmit / no HTTP response
Last network change:         BGP policy/HA/routing revision
Owner / scope:               application + network + security
~~~

Một log chỉ chứa IP mà thiếu **port, protocol, timestamp, VRF và NAT context** có thể không đủ phân biệt hai kết nối khác nhau.

### Bước 2. Phân biệt sự cố ứng dụng và mạng

- Kiểm tra DNS có trả đúng IP/AAAA không; nếu có nhiều backend/load balancer, đích thực sự là node nào?
- Kiểm tra ứng dụng có listening trên cổng, TLS/certificate hợp lệ và DB/dependency khỏe không.
- Dựa vào flow logs hoặc packet capture đã được phép, xem có SYN, SYN-ACK, ACK/RST hay timeout ở những điểm quan sát.
- Kiểm tra có thay đổi firewall rule, NAT, VPN, peering, routing hoặc HA gần thời điểm lỗi không.

**Không kết luận asymmetric routing chỉ vì TCP không kết nối được.** Cần chứng minh đường đi/về khác nhau **tại điểm liên quan** và giải thích vì sao khác biệt đó gây triệu chứng.

### Bước 3. Thu bằng chứng đường đi của cả hai chiều

Lập bảng với từng điểm kiểm soát:

| Vị trí | Forward nhìn thấy | Return nhìn thấy | State/policy/action |
| --- | --- | --- | --- |
| Client interface | SYN đi | SYN-ACK về hoặc không? | App/session |
| Router bên client | Next hop nào? | Gói trở về interface nào? | Routing/PBR/uRPF |
| Firewall A | Flow khởi tạo có qua không? | Có gói trả về không? | Session/NAT/deny logs |
| Firewall B | Có gói khởi tạo không? | Có reply đến không? | No session/invalid/allow |
| Router/server side | Gói tới server không? | Route tới source chọn đâu? | FIB/VRF |
| Server | Có nhận SYN và gửi SYN-ACK không? | N/A | Host firewall/TCP logs |

Quan sát **cả hai đầu** nếu có thể. Một packet capture tại firewall A chỉ chứng minh A nhìn thấy traffic của chiều được capture, **không chứng minh traffic chưa đến server** hoặc không có response từ server.

### Bước 4. So sánh định tuyến dự kiến và thực thi

Tại mỗi router/firewall quan trọng, kiểm tra:

- **RIB/FIB** và longest-prefix match tới đích của gói ở mỗi chiều.
- **Policy-based routing**, VRF, route leaking, interface và next hop.
- ECMP next hops và cách flow được phân bổ; route thay đổi sau failover?
- NAT trước/sau policy và nơi mapping được lưu.
- BGP/IGP route update, neighbor state và convergence timers.
- Strict/loose uRPF/source ACL; gói nào bị drop và ở interface nào?
- Những đường khác như VPN, private endpoint, proxy, cloud routing và IPv6.

**RIB không nhất thiết bằng toàn bộ hành vi dataplane**: Policy routing, hardware FIB, offload, session pinning hoặc bug có thể làm tuyến thực tế khác suy đoán. Cần đối chiếu counters/logs/capture theo đúng nền tảng.

### Bước 5. Xem trạng thái firewall/NAT/IPS

Tìm session lookup, rule ID, NAT translation và thống kê drop/invalid ở **cả hai thiết bị**. Một kết luận có căn cứ thường gồm:

> “SYN đi qua FW-A và tạo state/NAT tại A; SYN-ACK từ server đi qua FW-B, trên B không có state tương ứng và log cho thấy B drop vì out-of-state. Route chiều về tới client đang ưu tiên FW-B do một thay đổi routing gần đây.”

Đây là **kịch bản minh họa có cấu trúc bằng chứng**, không phải suy đoán tự động từ một dòng log.

### Bước 6. Đánh giá thay đổi và rollback

Chọn thay đổi nhỏ nhất phục hồi **đường đi và chính sách bảo mật mong muốn**; xác định người phê duyệt, config/route diff, các dịch vụ bị ảnh hưởng, ca test ALLOW và DENY, cùng cách hoàn nguyên. Không thay nhiều routing policies cùng lúc nếu có thể thử theo từng đợt và đo kết quả.

### Bước 7. Kiểm chứng sau sửa

Kiểm tra **kết nối mới, kết nối lâu, TCP/UDP, DNS, VPN, IPv4/IPv6**, session trước/sau HA và khả năng giám sát. Ghi **bằng chứng cả flow hợp lệ hoạt động và flow không có quyền vẫn bị chặn**. Nếu chọn giải pháp cho phép asymmetry có chủ đích, ghi lại lý do và rủi ro còn lại.

## 15. Công cụ quan sát và giới hạn khi suy luận

Không có một lệnh đơn lẻ nào chứng minh toàn bộ đường đi hai chiều. Những công cụ dưới đây là **gợi ý quan sát trong mạng được phép**, không phải yêu cầu chạy trên tài sản bên ngoài.

| Công cụ / dữ liệu | Dùng để xem | Giới hạn |
| --- | --- | --- |
| **Route table/FIB** | Next hop dự kiến cho destination | Không chứng minh packet thực đi nhánh nào nếu có PBR/ECMP/offload |
| **PBR/VRF policy** | Quy tắc chọn route theo source, interface hoặc policy | Phải xét đúng rule order/priority và thiết bị |
| **Traceroute / tracepath / mtr** | Các hop trả lời probe theo chiều gửi | ICMP/UDP/TCP probe có thể đi khác ứng dụng; router có thể không phản hồi |
| **Ping** | Khả năng phản hồi ICMP cơ bản | Không chứng minh TCP/UDP, TLS hay stateful session hoạt động |
| **Packet capture/tcpdump/Wireshark** | Packet nhận/gửi tại một điểm quan sát | Một điểm chỉ thấy những packet đi qua đó; cần ủy quyền thu thập |
| **Firewall session/NAT logs** | Session owner, translation và nguyên nhân drop | Tên log khác theo vendor; có sampling/timeout |
| **VPC/NSG/flow logs** | Metadata flow ở cloud | Thường không chứa nội dung payload, có giới hạn sampling/góc nhìn |
| **BGP/OSPF telemetry** | Neighbor, route change, next hop | Route control-plane không đủ mô tả policy dataplane |
| **Application traces** | Request/response success, latency và backend | Có thể không chỉ rõ vị trí packet bị mất |
| **IDS/IPS metrics** | Flow reassembly, invalid session, packet loss | Alert phụ thuộc placement/coverage, không phải ground truth |

### 15.1. Ví dụ lệnh đọc routing trên Linux

Chỉ để **học cách đọc output** và dùng khi được giao quyền:

~~~sh
# Thông tin interface và địa chỉ IP cục bộ
ip -br addr

# Các tuyến trong bảng định tuyến được chọn
ip route show

# Chính sách định tuyến theo rule và các bảng
ip rule show
ip route show table all

# Query route cục bộ tới một địa chỉ tài liệu, với nguồn hợp lệ trên host
ip route get 192.0.2.20

# Xem kết nối TCP tại host
ss -tn
~~~

**Không coi kết quả của host Linux là route của firewall bên kia.** Lệnh **ip route get** mô phỏng quyết định local forwarding tại host; nếu có forwarding theo PBR hoặc route tables trên router/cloud, phải quan sát đúng thiết bị. Những lệnh capture như tcpdump có thể thu nội dung nhạy cảm, nên chỉ dùng trên interface/filter/khung thời gian được phê duyệt, với quản lý dữ liệu và retention phù hợp.

### 15.2. Tại sao traceroute có thể gây hiểu nhầm?

- Probe và traffic ứng dụng có thể khác **source port, destination port, protocol hoặc DSCP**, dẫn tới khác ECMP hash/PBR.
- Router trung gian có thể giới hạn phản hồi ICMP hoặc không phản hồi TTL-expired.
- NAT, tunnel, MPLS, overlay và load balancer có thể ẩn các hop.
- Đường từ A đến B được đo không tự cung cấp kết quả **B đến A**.
- Route có thể thay đổi giữa hai lần đo, nhất là khi link flapping.

Khi cần so sánh, dùng **probe có đặc tính phù hợp phiên ứng dụng** và đo **hai chiều** ở các điểm có quyền quan sát. Bằng chứng mạnh hơn khi kết hợp traceroute với **FIB/PBR, firewall state, packet/flow logs và timestamp**.

## 16. Mô hình hóa offline bằng Python: đánh dấu flow cần xem xét

Chương trình sau dùng **dữ liệu mô phỏng**, không phát packet, không thay route và không truy cập thiết bị. Mục tiêu là nhận diện một luồng đi-về qua **hai firewall stateful khác nhau**, sau đó nêu câu hỏi liệu có cơ chế state sharing được kiểm chứng hay không.

~~~python
from dataclasses import dataclass


@dataclass(frozen=True)
class ObservedFlow:
    name: str
    forward_fw: str
    return_fw: str
    stateful: bool
    shared_state_verified: bool
    nat_on_forward: bool
    nat_mapping_verified: bool


def assess(flow: ObservedFlow) -> dict:
    """Không quyết định ALLOW/DENY, chỉ yêu cầu review."""
    split_device = flow.forward_fw != flow.return_fw
    session_risk = (
        split_device and flow.stateful
        and not flow.shared_state_verified
    )
    nat_risk = (
        split_device and flow.nat_on_forward
        and not flow.nat_mapping_verified
    )
    return {
        "flow": flow.name,
        "path_asymmetric_at_firewall": split_device,
        "needs_session_review": session_risk,
        "needs_nat_review": nat_risk,
    }


cases = [
    ObservedFlow("same-firewall", "fw-a", "fw-a", True, False,
                 True, False),
    ObservedFlow("split-unsynced", "fw-a", "fw-b", True, False,
                 True, False),
    ObservedFlow("split-synced", "fw-a", "fw-b", True, True,
                 True, True),
    ObservedFlow("stateless-paths", "acl-a", "acl-b", False, False,
                 False, False),
]

for flow in cases:
    result = assess(flow)
    print(
        result["flow"],
        "asym=", result["path_asymmetric_at_firewall"],
        "session_review=", result["needs_session_review"],
        "nat_review=", result["needs_nat_review"],
    )

assert assess(cases[1])["needs_session_review"] is True
assert assess(cases[2])["needs_nat_review"] is False
~~~

Kết quả dự kiến:

~~~text
same-firewall asym= False session_review= False nat_review= False
split-unsynced asym= True session_review= True nat_review= True
split-synced asym= True session_review= False nat_review= False
stateless-paths asym= True session_review= False nat_review= False
~~~

**Giới hạn quan trọng:**

- **shared_state_verified=True** và **nat_mapping_verified=True** chỉ là **giả định đầu vào cho lab**, không chứng minh vendor bảo toàn mọi TCP/VPN/TLS/IPS session.
- Bất đối xứng có thể xảy ra **giữa router hoặc sensor** dù hai chiều cùng đi qua firewall; ví dụ chỉ mô hình một điểm firewall.
- Một flow không có NAT vẫn có thể bị route/uRPF/firewall policy chặn; kết quả **False** nghĩa là *không phát hiện rủi ro thuộc quy tắc kiểm tra này*, không có nghĩa an toàn tuyệt đối.
- Với ACL stateless, muốn hai chiều hoạt động cần **rule phù hợp**, không phải cứ stateless là traffic chắc chắn được cho phép.
- Không thể dùng đoạn code này làm công cụ tự thay đổi cấu hình production; cần kết hợp thiết kế, kiểm thử và logs thật.

### Bài tập mở rộng

1. Thêm trường **route_change_timestamp** và đánh dấu flow đổi đường sau một lần failover.
2. Thêm trường **rpf_mode** và **reverse_egress_interface** để minh họa vì sao strict uRPF có thể chặn một nguồn hợp lệ.
3. Tách **session sync** và **VPN SA sync** thành hai khả năng độc lập, không gộp mọi protocol thành một boolean.
4. Bổ sung một sensor trên mỗi nhánh, xác định sensor nào thiếu dữ liệu return.
5. Thiết kế output chỉ sinh **triage ticket** (gồm flow ID, thời gian và lý do), không tự cập nhật firewall/routing.

## 17. Mô hình hóa mối đe dọa và các trust boundary

Asymmetric routing là một **tín hiệu cấu trúc**: nếu packet đi theo đường không như dự tính, một ranh giới cần có firewall/IPS/logging có thể bị vượt qua hoặc được đánh giá thiếu ngữ cảnh.

| Threat/failure scenario | Điều kiện | Rủi ro | Kiểm soát |
| --- | --- | --- | --- |
| **Return path bypass firewall** | Route trả về không qua firewall bắt buộc | Một chiều không chịu security policy/inspection như thiết kế | Enforce security chokepoint trên mọi đường, test cả hai chiều |
| **Stateful session drop** | Reply qua firewall khác không có state | Mất TCP/UDP session, ứng dụng không khả dụng | Symmetric routing/flow steering hoặc cơ chế HA được hỗ trợ |
| **NAT state unavailable** | Reply đến node khác không sở hữu translation | Không giải NAT/PAT đúng, timeouts | Đồng bộ mapping có kiểm chứng hoặc đưa reply về NAT owner |
| **Strict uRPF false drop** | Best reverse path khác interface nhận gói hợp lệ | Traffic hợp lệ bị coi là spoofed | Chọn anti-spoofing theo topology, source ACL, feasible/loose khi phù hợp |
| **Source spoofing accepted** | Nới lỏng uRPF/ACL quá mức để hết lỗi | Gói giả mạo có thể đi vào mạng | Ingress source validation theo peer/customer, log và review |
| **NIDS only sees forward** | Sensor chỉ đặt ở nhánh đi | False negatives, thiếu stream context | Capture cả chiều hoặc correlation từ nhiều điểm phù hợp |
| **IPS state bypass/fail-open** | Thao tác khẩn vô hiệu hóa kiểm tra | Lưu lượng không được inspection đúng | Thẩm quyền thay đổi, monitor, rollback và kiểm chứng DENY |
| **Route leak giữa VRF** | Transit/peering mở đường không mong muốn | Dev/guest có thể thấy Prod/service quản trị | VRF separation, route filtering, firewall zones và IAM |
| **Failover split-brain** | Nhiều node cùng nhận vai trò, route không hội tụ | Gói đi sai node, trùng VIP/MAC, state không nhất quán | Election/fencing theo platform, HA health và test |
| **Cloud AZ appliance bypass** | Route table gắn sai subnet/AZ | Traffic bỏ qua firewall inspection | IaC validation, effective route review, flow logs và canary |

### 17.1. Phân biệt tính sẵn sàng và an toàn

Một network engineer có thể muốn “làm TCP bắt tay thành công”. Một security engineer còn cần chắc rằng:

- Cả request và response vẫn chịu **các điểm enforcement bắt buộc**.
- Không có **allow-any**, **fail-open** hoặc “accept invalid state” được áp dụng vô thời hạn để né lỗi.
- Phân đoạn Prod/Dev, quản trị, VPN và dữ liệu nhạy cảm vẫn theo **least privilege**.
- Các log, mapping NAT và dữ liệu phiên vẫn đủ cho phân tích sau sự cố.
- Việc tạo đường về mới không mở **đường đi trái quyền** cho một chiều khác.

Một phương án sửa chỉ được coi là đạt khi **tính khả dụng và ý định bảo mật** đều đúng.

## 18. Case study 1: ECMP qua hai firewall làm TCP handshake thất bại

**Bối cảnh lab giả định:** Một tổ chức có router R1 phía client và R2 phía server. Giữa chúng là hai firewall stateful độc lập **FW-A** và **FW-B** với hai next hop ECMP. Không có cluster/session synchronization giữa hai firewall.

~~~mermaid
flowchart LR
    C["Client 10.10.10.10"] --> R1["Router R1"]
    R1 -->|"SYN chọn A"| A["FW-A"]
    R1 -. "Nhánh khác" .-> B["FW-B"]
    A --> R2["Router R2"]
    B --> R2
    R2 --> S["Server 192.0.2.20"]
    S -->|"SYN-ACK"| R2
    R2 -->|"Return chọn B"| B
    B --> R1
~~~

### 18.1. Triệu chứng và quan sát

| Bằng chứng | Quan sát giả định | Diễn giải |
| --- | --- | --- |
| Client capture | SYN retransmission, thiếu SYN-ACK hợp lệ | TCP handshake không hoàn tất |
| FW-A session log | Có SYN và state mới | Forward traffic đi qua FW-A |
| FW-B drop log | SYN-ACK đến nhưng “no session” | Return traffic đi qua FW-B |
| Router R1/FIB | Flow chọn nhánh FW-A | ECMP choice ở chiều đi |
| Router R2/FIB | Flow trả về chọn FW-B | ECMP choice ở chiều về |
| Application server log | TCP SYN đến, phát SYN-ACK | Server có phản hồi, vấn đề ở đường trả về |

**Chẩn đoán:** Có **asymmetry tại firewall stateful**, không chỉ khác một router trung gian. FW-B không có state nên bỏ gói return theo policy. Đây là cơ chế có khả năng giải thích triệu chứng.

### 18.2. Lựa chọn sửa

**Phương án A — Điều chỉnh đường đi để giữ flow symmetry:** Thay đổi route/ECMP/flow steering đã được phê duyệt để hai chiều cùng qua một firewall; cần xác minh các prefix, trạng thái khi failover và capacity.

**Phương án B — Dùng giải pháp HA/cluster thực sự hỗ trợ:** Chỉ khi vendor hỗ trợ ownership/state/NAT synchronization hoặc flow redirection đúng loại lưu lượng, và đã kiểm thử. Không bật một cờ “sync” rồi mặc nhiên cho rằng tất cả session đã được bảo toàn.

**Phương án C — Phân bố mạng theo zone/security chokepoint:** Thiết kế điểm qua firewall rõ ràng, loại route song song vượt kiểm soát. Có thể tăng độ phức tạp hoặc giảm độ linh hoạt nhưng giúp audit.

**Không khuyến nghị:** Chấp nhận mọi packet out-of-state trên FW-B, tắt toàn bộ stateful inspection hoặc mở ALLOW any-any như “sửa nhanh”. Điều này có thể làm mất chức năng bảo vệ cốt lõi.

### 18.3. Regression test tối thiểu

- TCP/443 **được phép** hoạt động qua nhiều source port khác nhau và sau route recalculation.
- TCP/22 **bị từ chối** vẫn bị chặn trên cả FW-A và FW-B.
- NAT mappings nếu có không bị chuyển tới node không có state.
- Các kết nối cũ và mới trong lúc failover được đo riêng.
- NIDS/IPS vẫn nhìn thấy luồng theo mức bao phủ được thiết kế.
- Không có hiện tượng **route loop, ECMP oscillation hoặc firewall session invalid** tăng bất thường.

## 19. Case study 2: dual ISP và strict uRPF chặn traffic hợp lệ

**Bối cảnh giả định:** Một tổ chức nhận Internet qua ISP-A và ISP-B. Router/firewall có strict uRPF ở hai uplink. Do policy inbound của mạng ngoài, kết nối từ một đối tác có IP **203.0.113.20** đến qua ISP-B, trong khi route tốt nhất từ tổ chức quay về đối tác lại đi ISP-A.

~~~text
Partner 203.0.113.20
            |
Internet BGP domain
          /   \
      ISP-A   ISP-B
       ^        |
       |        v
 Reverse best   Incoming legitimate packet
 path -> A      through B
          \    /
       Border router
        strict uRPF
~~~

### 19.1. Tại sao không phải gói giả mạo chắc chắn?

Một IP nguồn có thể hoàn toàn hợp lệ nhưng mạng bên ngoài chọn đường vào khác với router của tổ chức chọn đường quay về. **Strict uRPF** có thể loại gói vì điều kiện interface, chứ không phải vì có bằng chứng nguồn IP bị giả.

### 19.2. Cách điều tra và giảm thiểu

1. Xác nhận **nguồn đối tác và luồng ứng dụng** qua log đáng tin, không chỉ dựa vào địa chỉ trong một packet.
2. Kiểm tra **route/FIB tới source IP** và giao diện nhận gói tại đúng thiết bị.
3. Kiểm tra **uRPF drops** và chính sách ingress source validation trên ISP-B.
4. Xác định topology có chủ đích dùng đường bất đối xứng hay do route drift.
5. Nếu cần chấp nhận multi-homing hợp lệ, chọn **source ACL theo peer/prefix**, feasible-path hoặc loose uRPF theo năng lực thiết bị và risk policy; vẫn duy trì chống spoofing phù hợp.
6. Thử cả traffic hợp lệ từ ISP-A/B và traffic có source không thuộc phạm vi được phép trong **lab hoặc công cụ kiểm thử có quyền**, tránh tạo gói giả trên Internet.
7. Lưu thay đổi, owner, counter trước/sau và review interval.

**Bài học:** Không nên kết luận “uRPF drop nghĩa là attack” và cũng không nên loại bỏ hoàn toàn kiểm tra nguồn chỉ vì một đường multi-homed có asymmetry.

## 20. Chọn phương án thiết kế và sửa chữa

### 20.1. Bảng quyết định

| Phương án | Khi phù hợp | Đánh đổi và điều kiện |
| --- | --- | --- |
| **Routing symmetry qua cùng stateful firewall** | Hai chiều cần chung session/NAT/inspection | Phải kiểm tra route failover, headroom và redundancy |
| **Flow affinity/stickiness** | Load balancer/ECMP có điểm điều phối hỗ trợ | Tính ổn định hash, flow ownership, health check |
| **Stateful HA/cluster được vendor hỗ trợ** | Cần nhiều node, yêu cầu chuyển phiên | Session/NAT/VPN sync có giới hạn; cần lab thực tế |
| **Stateless ACL có scope rõ** | Các traffic/giao thức cho phép mô hình stateless và ranh giới phù hợp | Rule ở cả hai chiều; nguy cơ cho phép return quá rộng |
| **SNAT tại proxy/load balancer** | Muốn return path qua một điểm trung gian và chấp nhận thay source IP | Mất source visibility ở app, NAT capacity, audit |
| **Tune uRPF/source validation** | Multi-homing làm strict uRPF chặn nguồn hợp lệ | Không làm yếu chống spoofing quá mức, xác minh prefix/source |
| **Điều chỉnh PBR/VRF/route leak** | Route qua sai zone hoặc default route lấn đường | Thay đổi có thể tác động nhiều dịch vụ; test full prefix scope |
| **Bổ sung packet/flow visibility** | Bất đối xứng hợp lệ nhưng NIDS chỉ thấy một chiều | Chi phí sensor/correlation và bảo vệ dữ liệu thu thập |
| **Thêm proxy/security gateway được kiểm soát** | Phải thực thi auth/inspection tại một chokepoint | Thêm latency, capacity, HA và dependency |
| **Thiết kế private service access thay L3 mesh** | Cần hạn chế kết nối xuyên Prod/Dev/cloud | Cần quản lý identity, DNS và API governance |

### 20.2. Quy trình thay đổi an toàn

~~~mermaid
flowchart TB
    A["Xác nhận 5-tuple, timestamp, owner"] --> B["Vẽ forward và return path"]
    B --> C["Kiểm tra state/NAT/uRPF/inspection"]
    C --> D{"Asymmetry có chủ đích?"}
    D -- "Không" --> E["Sửa route/PBR/VRF tại nguồn gốc"]
    D -- "Có" --> F["Thiết kế flow ownership / security equivalent"]
    E --> G["Review policy, blast radius và rollback"]
    F --> G
    G --> H["Lab/canary + ALLOW/DENY regression"]
    H --> I["Thay đổi được phê duyệt"]
    I --> J["Readback/flow logs/application SLI"]
~~~

**Không “sửa cho ping chạy” bằng việc bật tunnel/route rộng bất kỳ.** Trước thay đổi cần xác định **trust boundary, phạm vi address families, IPAM, VPN selectors, NAT rule order, firewall policy và năng lực đường dự phòng**.

### 20.3. Yêu cầu cụ thể cho rollback

Hồ sơ thay đổi nên có:

~~~text
CHANGE ID:          CHG-EXAMPLE
OWNER / APPROVER:   Network + Security
SYMPTOM:            SYN-ACK dropped on FW-B, no corresponding session
EVIDENCE:           Flow 5-tuple, route snapshots and firewall logs
DESIRED PATH:       Both directions traverse state owner as designed
CHANGE SCOPE:       Specific route/PBR/ECMP group and affected prefixes
PRE-CHANGE:         Effective route, NAT policy, security posture
VALIDATION:         Approved ALLOW and DENY test matrix
ROLLBACK TRIGGER:   New drops, route leak, application impact or bypass
ROLLBACK METHOD:    Restore approved prior route/policy and verify
READBACK:           Both directions, session/NAT and application health
~~~

**Tốt nhất không thay route, NAT và firewall rules đồng thời** nếu có thể cô lập nguyên nhân và kiểm chứng từng phần. Khi buộc đổi nhiều thành phần, ghi rõ thứ tự và dependency để tránh một trạng thái trung gian mất kiểm soát.

## 21. Ma trận kiểm thử asymmetric routing

Những ca dưới đây dành cho **lab, staging hoặc cửa sổ thay đổi được cấp quyền**; không thực hiện giả mạo nguồn, ngắt link hay chỉnh BGP trên hạ tầng công cộng khi chưa có thẩm quyền.

| Test ID | Tình huống | Kỳ vọng / bằng chứng |
| --- | --- | --- |
| AR-01 | Flow TCP/443 đi-về cùng firewall stateful | Ứng dụng thành công; session/NAT đúng |
| AR-02 | Flow TCP/443 có forward FW-A, return FW-B độc lập | Có nhận diện nguy cơ out-of-state; xác minh bằng logs, không đoán |
| AR-03 | TCP/443 qua cặp HA có state sync được hỗ trợ | Session hoạt động theo giới hạn vendor, đo reconnect |
| AR-04 | TCP/22 từ vùng không được phép | **DENY** trên mọi đường và cả sau failover |
| AR-05 | UDP service được phê duyệt | Return path hợp lệ theo timeout/state của sản phẩm |
| AR-06 | NAT/PAT mapping từ một node, reply về node khác | Phát hiện mapping mismatch hoặc có cơ chế sync được chứng minh |
| AR-07 | ECMP có nhiều source/destination ports | Không có nhóm flow bị ngắt ngẫu nhiên do hash/path mismatch |
| AR-08 | ECMP next hop bị rút trong lab | Flow cũ/mới chuyển theo policy, số session loss được đo |
| AR-09 | BGP path đổi do failover mô phỏng | Route cả hai hướng hội tụ, không có loop/blackhole |
| AR-10 | Strict uRPF trong mạng multi-homed | Không drop nhầm nguồn hợp lệ trong profile được phê duyệt |
| AR-11 | Source IP không thuộc prefix ingress hợp lệ trong lab | Anti-spoofing policy vẫn ngăn được theo thiết kế |
| AR-12 | SD-WAN chuyển một tunnel dự phòng | VPN traffic selectors, route, state và ứng dụng đúng |
| AR-13 | Cloud subnet/AZ route table thay đổi | Return qua firewall/endpoint phù hợp, không bypass zone |
| AR-14 | Kubernetes/CNI Pod/Service egress đi qua gateway | Quan sát outer/inner/NAT đúng và policy thực thi |
| AR-15 | Traffic IPv6 giữa hai site | Không có đường IPv6 bypass policy chỉ thiết kế cho IPv4 |
| AR-16 | NIDS chỉ thấy forward rồi bổ sung sensor return | Coverage/correlation tốt hơn và không nhầm stream state |
| AR-17 | DNS request/reply qua hai đường khác nhau | Resolver hoạt động; thống kê flow/log phù hợp |
| AR-18 | DDoS scrubbing đổi inbound route | Return path, MTU, VPN và inspection vẫn đúng |
| AR-19 | Ứng dụng hoạt động qua TCP handshake nhưng lỗi TLS/HTTP | Phân biệt routing và lỗi ứng dụng bằng telemetry |
| AR-20 | Rollback route/PBR sau test lỗi | Trở lại đường/policy trước, không để lại ngoại lệ rộng |

### 21.1. Cần ghi gì cho mỗi ca?

Một test case có thể có:

~~~text
Test ID:
Service / environment / VRF:
Timestamp UTC:
Source IP:port / destination IP:port / protocol:
Forward path observations:
Return path observations:
NAT and session owner:
Expected ALLOW/DENY:
Actual decision + device/rule ID:
Application outcome:
Monitoring/IDS visibility:
Owner / approval:
Rollback or next action:
~~~

**Bằng chứng “ứng dụng hoạt động” và “đường bảo mật đúng” là hai kiểm tra khác nhau.** Một flow có thể thành công vì đi vòng firewall, nên cả hai phải cùng PASS.

## 22. Giám sát liên tục và phát hiện thay đổi bất đối xứng

| Nhóm quan sát | Tín hiệu | Ý nghĩa |
| --- | --- | --- |
| **Firewall state** | Invalid/no-session drops theo zone, interface, 5-tuple | Có thể có flow bất đối xứng, timeout hoặc policy lỗi |
| **NAT/PAT** | Translation miss, stale mapping, port allocation errors | Gói quay về node sai hoặc state hết hạn |
| **Routing** | BGP/OSPF changes, ECMP group membership, next-hop flapping | Đường đi có thể đổi mà app chưa kịp phục hồi |
| **HA** | Role switch, session-sync backlog, peer health | Return traffic có thể đến node chưa đồng bộ |
| **uRPF** | Drops theo ingress interface và source prefix | Phát hiện spoofing hoặc false drops trên multi-homing |
| **VPN/SD-WAN** | Tunnel state, SA, path-quality, failover counters | Hai hướng bị steering khác nhau |
| **NIDS/IPS** | One-sided flows, stream reassembly gaps, packet loss | Sensor thiếu chiều/thiếu dữ liệu |
| **Cloud** | Effective routes, route table changes, gateway attachments | Nguy cơ bypass inspection/AZ mismatch |
| **Application SLI** | TCP handshake failures, 5xx, latency, reconnect | Tác động cuối cùng tới người dùng |
| **Governance** | Route/PBR/VRF/NAT change audit và owner | Điều tra cấu hình drift, truy vết phê duyệt |

Một thay đổi route hợp lệ vẫn cần theo dõi khi **thêm ISP, site, peering, tenant, transit hub, VPN và IPv6**. Đặc biệt nên chạy lại **ALLOW/DENY regression** sau thay đổi lớn vì một tuyến mới có thể âm thầm tạo đường bỏ qua inspection.

### 22.1. Đặt ngưỡng dựa trên baseline

Không đặt ngưỡng tuyệt đối cho mọi firewall, ví dụ “10 invalid packets/giây nghĩa là bị tấn công”. Cần phân biệt:

- Dịch vụ có nhiều short-lived flows hay long-lived TCP.
- Giai đoạn vừa failover hay hoạt động ổn định.
- Các loại ICMP/UDP không cùng trạng thái như TCP.
- Sensor có thiếu gói, link có packet loss hoặc session timeout được cấu hình ngắn không.
- Sự kiện xảy ra với một source/route cụ thể hay toàn hệ thống.

Giám sát tốt kết hợp **tỉ lệ invalid trên tổng phiên phù hợp**, thay đổi route gần đó, gói SYN/SYN-ACK ở hai điểm, NAT owner và tác động ứng dụng.

## 23. Những hiểu lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Mạng có asymmetric routing là bị tấn công.” | IP routing hai chiều khác nhau có thể là thiết kế bình thường. |
| “Có route tới destination thì TCP chắc chắn chạy.” | Firewall state, NAT, return route, DNS, TLS và ứng dụng còn ảnh hưởng. |
| “Một đường traceroute đủ xác nhận path của cả hai chiều.” | Probe chỉ quan sát chiều gửi và có thể đi khác luồng ứng dụng. |
| “ECMP per-flow luôn giữ request và reply trên cùng firewall.” | Hash/tuyến ở hai đầu có thể khác, flow cần symmetry/ownership rõ. |
| “Hai firewall cùng hãng tự chia session state.” | Phải là kiến trúc HA/cluster được hỗ trợ, cấu hình và kiểm thử đúng. |
| “State sync luôn bảo toàn mọi session TCP/VPN/IPS.” | Phụ thuộc loại state, phiên bản, ownership và thời điểm sync. |
| “NAT là cách chữa mọi bất đối xứng.” | NAT có thêm mapping state, đổi source visibility và rủi ro capacity. |
| “Bật allow invalid packets là sửa được vấn đề.” | Có thể bỏ qua bảo vệ stateful; cần sửa route hoặc dùng cơ chế được duyệt. |
| “Strict uRPF drop là bằng chứng nguồn giả mạo.” | Multi-homing có đường hợp lệ khác reverse best path. |
| “Loose uRPF bảo vệ mọi source spoofing.” | Default route và route rộng có thể khiến kiểm tra quá yếu. |
| “Nếu IDS không báo, không có traffic nguy hiểm.” | Sensor có thể chỉ thấy một chiều, bị packet loss hoặc traffic mã hóa. |
| “Tắt IPS để đỡ drop là tối ưu an ninh.” | Có thể làm mất inspection bắt buộc; cần đánh giá risk/policy. |
| “Firewall HA role active nghĩa là traffic đã hội tụ.” | Router, ARP/ND, NAT, VPN và ứng dụng có thể chưa phục hồi. |
| “Cloud route table giống nhau ở mọi subnet.” | Mỗi subnet/AZ/attachment có thể có tuyến và policy khác nhau. |
| “Sửa route chiều đi xong không cần xem chiều về.” | Chính return path có thể là nguyên nhân gói rơi hoặc bypass. |

## 24. Câu hỏi tự kiểm tra và bài tập kiến trúc

1. **Asymmetric routing là gì?** Hai chiều của một giao tiếp mạng đi qua những đường/thiết bị khác nhau.
2. **Nó có luôn là lỗi không?** Không. Nó trở thành vấn đề khi vi phạm yêu cầu state, NAT, kiểm soát hoặc hiệu năng.
3. **Vì sao FW-B có thể drop SYN-ACK khi SYN qua FW-A?** FW-B không có session state tương ứng và coi reply là invalid/out-of-state.
4. **ECMP per-flow có bảo đảm hai chiều cùng firewall?** Không; hai router có thể hash/next-hop khác nhau.
5. **Tại sao PAT dễ gặp lỗi nếu reply về sai node?** Mapping public IP/port → private IP/port có thể chỉ tồn tại ở node tạo translation.
6. **Strict uRPF có thể chặn traffic hợp lệ trong tình huống nào?** Khi packet đến từ interface khác interface mà FIB chọn để quay về source.
7. **Loose uRPF có phải phòng vệ anti-spoofing đầy đủ không?** Không; chỉ xác minh điều kiện route nguồn theo chế độ, thường yếu hơn strict và chịu ảnh hưởng default route.
8. **BGP LOCAL_PREF ép được peer bên ngoài trả cùng ISP không?** Không; nó chủ yếu ảnh hưởng chọn tuyến đi trong AS áp dụng.
9. **Nếu chỉ NIDS A thấy HTTP request mà không thấy response, có kết luận server không phản hồi?** Không; response có thể đi nhánh khác hoặc sensor mất gói.
10. **Vì sao cần kiểm tra sau HA failover?** Route và session/NAT ownership có thể đổi, gây packet drop hoặc bypass policy.
11. **Một cấu hình SG/NSG/ACL trên cloud có tự đảm bảo route đi qua firewall không?** Không; phải kiểm tra effective route và insertion point.
12. **Cách chứng minh sửa lỗi thành công là gì?** Có bằng chứng hai chiều, kết nối hợp lệ phục hồi, các luồng DENY vẫn bị chặn và monitoring không mất coverage.

### Bài tập tình huống

Một hệ thống hybrid gồm data center và cloud kết nối qua hai đường: private circuit và IPsec VPN. Tại data center, traffic hướng cloud đi qua **FW-A** theo PBR; tại cloud, reply ưu tiên VPN và đến **FW-B** độc lập. Ứng dụng báo TCP handshake timeout; đồng thời NIDS ở FW-A không thấy response.

Hãy:

1. Vẽ luồng **forward/return** và xác định chính xác chỗ đường đi trở thành bất đối xứng.
2. Lập bảng **5-tuple, VRF, route/PBR, NAT và session owner** tại hai điểm.
3. Đề xuất ba giả thuyết có thể gây timeout ngoài asymmetric routing, và bằng chứng phân biệt.
4. Chọn hai phương án sửa (ví dụ route symmetry hoặc cluster/flow ownership đúng sản phẩm), nêu rủi ro.
5. Đánh giá strict uRPF nếu áp trên hai đường WAN và trường hợp source hợp lệ bị false drop.
6. Thiết kế **ít nhất 10 ca regression test**, có TCP/443 ALLOW, SSH DENY, VPN failover, route convergence và NIDS coverage.
7. Mô tả change approval, rollback, cách đo SLI và điều kiện kết thúc sự cố.

## 25. Checklist review Asymmetric Routing

- [ ] Đã xác định flow **source/destination IP:port, protocol, timestamp, VRF và NAT context**?
- [ ] Có bằng chứng forward path **và** return path ở các điểm quan trọng?
- [ ] Đã kiểm tra FIB, policy-based routing, routing domain và ECMP ở hai đầu?
- [ ] Có xem BGP/OSPF update, route preference và thay đổi HA gần thời điểm lỗi?
- [ ] Stateful firewall nhận traffic có session state hoặc cơ chế ownership được hỗ trợ?
- [ ] NAT/PAT mapping còn hiệu lực và nằm đúng thiết bị xử lý reply?
- [ ] Có phân biệt stateless ACL với stateful inspection khi phân tích return traffic?
- [ ] Các profile IPS/TLS/VPN/user identity còn hoạt động trên node/đường dự phòng?
- [ ] Strict/loose uRPF và source ACL phù hợp multi-homing, vẫn chống spoofing?
- [ ] NIDS/flow monitoring nhìn thấy đủ dữ liệu hoặc ghi rõ blind spots?
- [ ] Đã xét route qua cloud AZ, transit gateway, VPC/VNet, private endpoint và IPv6?
- [ ] Đã kiểm tra tunnel selectors, NAT exemptions và SD-WAN steering hai chiều?
- [ ] Không có route leak hoặc đường đi vòng bỏ qua firewall giữa Dev/Prod/Management?
- [ ] Traceroute/ping đã được đối chiếu với logs/capture/route tại đúng điểm?
- [ ] Sửa đổi được phê duyệt, scope hẹp, có owner và rollback?
- [ ] Đã kiểm thử kết nối **ALLOW hợp lệ và DENY bắt buộc** trước/sau thay đổi?
- [ ] Có metrics về session invalid, NAT failures, route changes và application SLI?
- [ ] Đã cập nhật runbook, network topology, change history và monitoring sau sửa?

**Kết luận:** Asymmetric routing không nhất thiết là lỗi; nó là thực tế phổ biến của những mạng có nhiều router, ISP, ECMP, tunnel và cloud connectivity. Rủi ro an ninh xuất hiện khi **đường đi không thống nhất với nơi giữ trạng thái phiên, NAT mapping, chính sách chống giả mạo hoặc điểm kiểm tra bắt buộc**. Để xử lý đúng, hãy **quan sát cả hai chiều, xác minh forwarding và session thực tế, chọn thiết kế kiểm soát phù hợp**, rồi chứng minh bằng test rằng **dịch vụ được phép hoạt động và những truy cập trái quyền vẫn bị chặn**.
