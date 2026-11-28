# Static và dynamic routing: Nền tảng định tuyến và bảo mật đường đi

## 1. Vì sao routing ảnh hưởng đến an toàn mạng?

**Routing (định tuyến)** xác định gói IP nên đi tới mạng đích qua interface và router kế tiếp nào. Nếu firewall trả lời câu hỏi **luồng nào được phép**, định tuyến góp phần trả lời câu hỏi **luồng đó đi qua những thành phần nào**. Một hệ thống phân đoạn mạng có thể cấu hình deny rất chặt trên firewall nhưng vẫn bị vượt qua nếu một đường dự phòng, more-specific route hoặc policy route đưa traffic theo nhánh khác.

Hai phương pháp cơ bản là:

- **Static routing:** route được khai báo bởi người quản trị hoặc hệ thống quản lý cấu hình, không được học tự động từ một giao thức định tuyến.
- **Dynamic routing:** router học, trao đổi hoặc rút thông tin reachability thông qua giao thức như **OSPF, IS-IS, BGP**, theo thuật toán và chính sách.

Không nên kết luận static luôn an toàn hoặc dynamic luôn rủi ro. Static dễ hiểu trên topology nhỏ nhưng khó bảo trì khi nhiều đường thay đổi; dynamic hỗ trợ hội tụ khi mạng biến động nhưng cần bảo vệ **control plane, neighbor, prefix và chính sách import/export**.

Trong module **SECURITY_NETWORK_SECURITY**, định tuyến liên hệ trực tiếp với phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, mạng không dây, cloud networking và xác thực kết nối. Đường đi thực tế của packet phải phù hợp với kiến trúc bảo vệ được phê duyệt.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt static và dynamic routing theo cách học route, hội tụ, quy mô, quản trị và rủi ro.
2. Giải thích prefix, next hop, RIB, FIB, longest prefix match, metric, preference, ECMP và VRF.
3. Nhận biết vai trò của OSPF, IS-IS và BGP, không nhầm policy BGP với metric của IGP.
4. Mô hình hóa route injection, route hijack/leak, blackhole, routing loop và security-policy bypass.
5. Áp dụng các lớp kiểm soát: xác thực láng giềng, route filtering, RPKI origin validation, management-plane hardening.
6. Viết bộ kiểm thử positive/negative trước và sau thay đổi route, kể cả failover, IPv6 và đường trả lời.

> **Phạm vi an toàn:** dùng địa chỉ private và IP dành cho tài liệu trong các ví dụ. Các lệnh minh họa ưu tiên **chỉ đọc**; việc đổi static route, OSPF/BGP, firewall hoặc NAT trên thiết bị thật phải thuộc thay đổi được phê duyệt, có kế hoạch rollback và người giám sát.

## 2. Các khái niệm cốt lõi trước khi chọn route

| Thuật ngữ | Giải thích | Ví dụ |
|---|---|---|
| **Prefix** | Mạng đích bằng địa chỉ và độ dài prefix | 10.30.10.0/24; 2001:db8:30::/48 |
| **Next hop** | Router kế tiếp để chuyển gói | 10.0.12.2 |
| **Outgoing interface** | Interface dùng chuyển gói | eth1, VLAN, tunnel |
| **RIB** | Routing Information Base: các route/ứng viên do hệ điều hành routing quản lý | Connected, static, learned |
| **FIB** | Forwarding Information Base: dữ liệu chuyển tiếp được dùng bởi dataplane | Prefix → next hop |
| **Longest prefix match** | Ưu tiên prefix cụ thể nhất khớp địa chỉ đích trong bảng được sử dụng | /24 trước /16 trước /0 |
| **Metric** | Chi phí/thuộc tính chọn đường theo định nghĩa giao thức | OSPF cost; RIP hop count |
| **Administrative distance/preference** | Ưu tiên nguồn route cạnh tranh cho cùng prefix, theo nền tảng | Static vs OSPF |
| **Default route** | Route nếu không có prefix cụ thể hơn | 0.0.0.0/0; ::/0 |
| **ECMP** | Nhiều đường có chi phí được xem là bằng nhau cùng được sử dụng | Hai next hop tới cùng mạng |
| **VRF** | Các bảng định tuyến tách biệt logic trên cùng hệ thống | PROD, MGMT, GUEST |

**RIB không đồng nghĩa FIB.** Router có thể nhận nhiều route nhưng chỉ cài route được chọn và hợp lệ vào dataplane. Khi BGP nhận một prefix từ neighbor, chưa thể kết luận router đã chuyển tiếp gói theo prefix ấy; cần xem **accepted/selected route, next-hop reachability, FIB và các policy**.

### 2.1. Ba mặt phẳng của hệ thống mạng

~~~mermaid
flowchart TD
    M["Management plane: cấu hình, SSH, API, IAM"] --> C["Control plane: static policy, OSPF/BGP, RIB"]
    N["Neighbor / routing updates"] --> C
    C --> F["FIB / Forwarding"]
    P["Packet đi vào"] --> F
    F --> D["Next hop / interface"]
    S["ACL / Firewall / NAT / PBR / VRF"] -. "Ảnh hưởng đường và quyền" .-> D
~~~

- **Management plane** là nơi vận hành cấu hình và cấp quyền quản trị.
- **Control plane** học, tính toán và lựa chọn route.
- **Data plane** chuyển tiếp packet theo FIB cùng các quy tắc xử lý đang áp dụng.

Quyền thay đổi route trên management plane có thể ảnh hưởng đường traffic và chính sách bảo mật ở cả hai mặt phẳng còn lại. Vì vậy, routing security không chỉ là bật authentication cho OSPF hay BGP.

### 2.2. Longest prefix match khác administrative preference

Giả sử FIB có:

~~~text
Destination       Next hop       Ý nghĩa
10.30.0.0/16      10.0.12.2      Vùng DATA chung
10.30.10.0/24     10.0.13.2      Database riêng
0.0.0.0/0         10.0.1.1       Default
~~~

Packet tới **10.30.10.15** chọn **route /24**, nếu cả ba route đều hợp lệ và nằm trong cùng bảng/VRF được sử dụng. Một static /32 hoặc /24 có thể khiến traffic đi khỏi đường firewall mong muốn dù route tổng quát /16 vẫn tồn tại.

**Administrative distance/preference** thường dùng khi quyết định chọn nguồn route cho **cùng prefix**. Nó không làm cho static default route /0 thắng một OSPF /24 khi /24 cụ thể hơn đang có trong FIB. Metric OSPF, local preference của BGP và administrative distance cũng **không phải cùng một thang đo**.

## 3. Static routing: cấu hình rõ ràng, cần quản trị vòng đời

### 3.1. Cách static route hoạt động

Static route khai báo prefix, next hop hoặc interface. Pseudocode:

~~~text
Router R1:
    10.30.10.0/24 -> next hop 10.0.12.2
    0.0.0.0/0     -> next hop 10.0.1.1

Router R2:
    10.10.10.0/24 -> next hop 10.0.12.1
~~~

Nếu APP ở phía R1 muốn tới DATA qua R2, cần cả đường đi, **route chiều trả lời**, firewall và dịch vụ đích. Static route **không phải rule cho phép truy cập**; USER và APP có thể cùng có route tới DATA nhưng chỉ APP mới được phép kết nối tới một cổng database nhất định.

### 3.2. Các biến thể

| Loại | Mục đích | Rủi ro |
|---|---|---|
| Host route /32 hoặc /128 | Chỉ định đường tới một máy | More-specific route có thể bypass policy |
| Network route | Định tuyến một subnet | Cần cập nhật khi topology đổi |
| Default route /0 | Đường thoát tổng quát | Có thể gửi traffic nhạy cảm ra sai uplink |
| Summary route | Gộp nhiều prefix | Có thể làm blackhole mạng con không có thật |
| Floating static | Dự phòng với mức ưu tiên thấp hơn route chính | Backup chỉ nổi lên khi route chính không còn được chọn |
| Tracked static | Liên kết trạng thái route với một health/tracking mechanism | Probe sai ngữ cảnh hoặc quá nhạy gây đổi đường sai |
| Discard/blackhole route | Cố ý loại bỏ traffic tới prefix | Cấu hình sai gây mất kết nối hợp lệ |

Ở nhiều router, administrative distance **số nhỏ được ưu tiên**; vì vậy floating static dùng làm backup thường được đặt **số lớn hơn** route chính cùng prefix. Giá trị mặc định, cú pháp và cách rút route chính phụ thuộc nền tảng.

### 3.3. Ưu điểm

- Dễ dự đoán trên mạng nhỏ hoặc stub network.
- Không cần duy trì adjacency của giao thức routing ở link không cần thiết.
- Hợp với tuyến mặc định, những đường cố định và route được review chặt chẽ.
- Thuận lợi cho audit nếu cấu hình được quản lý bằng version control và có người sở hữu.

### 3.4. Hạn chế

- Link trực tiếp vẫn up nhưng upstream hỏng có thể khiến route **tiếp tục trỏ vào blackhole**.
- Cập nhật thủ công nhiều router dễ tạo **configuration drift**.
- Thay IP, VPN, cloud peering, route aggregation hoặc firewall có thể để lại route cũ.
- Floating/backup route không tự bảo đảm **bảo mật tương đương** đường chính.
- Static route sai /32, /24 hoặc /0 có thể tạo đường vòng qua security boundary.

## 4. Dynamic routing: neighbor, update và convergence

**Dynamic routing** dùng giao thức để trao đổi reachability hoặc trạng thái link giữa những thiết bị được phép tham gia. Khi link hoặc router thay đổi, các router cập nhật cơ sở dữ liệu/routing information và có thể chọn đường mới. Quá trình đi tới trạng thái định tuyến ổn định được gọi là **convergence (hội tụ)**.

~~~mermaid
flowchart LR
    R1["R1 / APP"] <-->|"Routing updates"| R2["R2 / Core"]
    R2 <-->|"Routing updates"| R3["R3 / DATA"]
    R2 <-->|"Backup routing updates"| R4["R4 / DR"]
    R1 -. "Packet theo FIB" .-> R2
    R2 -. "Packet theo FIB" .-> R3
~~~

**Routing updates thuộc control plane**, không phải luồng ứng dụng đi giữa các subnet. Chấp nhận một router làm neighbor nghĩa là cho nó khả năng cung cấp thông tin ảnh hưởng đường đi. Phải xác định ai được phép làm neighbor và những prefix nào được quyền quảng bá.

### 4.1. Giao thức điển hình

| Protocol | Mô hình và vai trò | Quan tâm bảo mật |
|---|---|---|
| **OSPFv2** | Link-state IGP cho IPv4, thiết kế theo area | Neighbor, LSA, bảo vệ interface và route redistribution |
| **OSPFv3** | Link-state cho IPv6 và address families tùy triển khai | Giới hạn neighbor và cơ chế bảo vệ tương ứng |
| **IS-IS** | Link-state IGP, thường trong mạng core/provider | Xác thực adjacency, phạm vi interface và leak giữa level |
| **RIP/RIPng** | Distance-vector, ít phù hợp mạng hiện đại lớn | Cập nhật sai từ nguồn không tin cậy, giới hạn hop count |
| **BGP** | Path-vector, policy-driven, giữa hoặc bên trong AS | Peer, prefix, import/export, route leak, hijack, RPKI |

**IGP** hỗ trợ định tuyến trong một miền quản trị. **eBGP** trao đổi route giữa autonomous systems, còn **iBGP** phân phối thông tin bên trong một AS. BGP lựa chọn đường bằng các thuộc tính và chính sách; không đơn giản lấy đường “ngắn nhất” theo số router hop.

### 4.2. Convergence có những giai đoạn nào?

1. Phát hiện link/neighbor lỗi bằng trạng thái link, hello/dead timers, **BFD** hoặc health/tracking khác.
2. Giao thức rút/trao đổi thông tin topology hoặc prefix.
3. Router tính toán/chọn route, rồi cập nhật RIB/FIB.
4. Packet dùng đường mới và ứng dụng phục hồi nếu đường mới đủ route, firewall, NAT và dependency.

**Convergence time không phải RTO của ứng dụng.** Một BGP session đã Established hoặc OSPF neighbor đã Full vẫn có thể có prefix sai, next hop không phù hợp hoặc đường về bất đối xứng.

## 5. So sánh static và dynamic routing

| Tiêu chí | Static | Dynamic |
|---|---|---|
| Cách hình thành route | Cấu hình trực tiếp hoặc IaC | Protocol + routing policy |
| Quản lý mạng nhỏ | Đơn giản, dễ audit | Có thể quá phức tạp so với nhu cầu |
| Quản lý mạng lớn | Nhiều công việc, dễ drift | Có thể mở rộng tốt khi thiết kế đúng |
| Khi có lỗi | Có thể cần tracking hoặc thao tác thủ công | Có cơ chế phát hiện và hội tụ tự động |
| Bề mặt tấn công nổi bật | Management plane, static route sai/cũ | Rogue peer, route injection/leak/hijack, policy |
| Thực thi chuyển tiếp | Đường được chọn cài vào FIB | Đường được chọn cũng cài vào FIB |
| Kiểm thử | Route, next hop, tracker, reachability | Thêm neighbor, received/selected/advertised, filters |
| Vận hành | Change control, owner, rollback | Change control cộng bảo vệ protocol/peer |

Một kiến trúc có thể dùng **static default** tại chi nhánh ít router, **OSPF trong core** và **BGP tại biên Internet hoặc kết nối cloud**. Lựa chọn phải dựa trên topology, mức độ biến động, RTO, năng lực bảo vệ neighbor và yêu cầu an toàn.

## 6. Mô hình lab để học định tuyến và segmentation

| Vùng | Prefix | Vai trò |
|---|---|---|
| USER | 10.10.10.0/24 | Máy người dùng |
| APP | 10.20.10.0/24 | API và ứng dụng |
| DATA | 10.30.10.0/24 | Database |
| MGMT | 10.40.10.0/24 | Bastion, quản trị |
| DR | 10.80.10.0/24 | Site dự phòng |

~~~mermaid
flowchart LR
    U["USER"] --> F["Segmentation FW"]
    A["APP"] --> F
    F --> R1["Core R1 / primary"]
    F -. "Backup path" .-> R2["Core R2"]
    R1 --> FD["DATA firewall"]
    R2 --> FD
    FD --> DB["DATA / DB"]
    R2 --> DR["DR site"]
    M["MGMT / bastion"] --> F
~~~

**Yêu cầu:** APP → DATA TCP/5432 được phép; USER → DATA TCP/5432 bị chặn; MGMT chỉ qua bastion được duyệt. Khi R1 lỗi và R2 thay thế, **cả luồng cho phép lẫn luồng phải chặn** vẫn phải đúng. Route qua R2 không được bypass các điểm kiểm soát.

**Static option:** khai báo static routes và tracked/floating backup khi cần. **Dynamic option:** OSPF trao đổi route giữa core routers; firewall vẫn kiểm soát traffic của từng security zone. Đây là sơ đồ minh họa, không phải cấu hình áp dụng trực tiếp.

## 7. Longest prefix, metric và ECMP: các trường hợp dễ nhầm

### 7.1. More-specific route thay đổi security path

~~~text
Prefix            Source       Next hop
10.30.0.0/16      OSPF         10.0.12.2   (đường qua firewall)
10.30.10.0/24     STATIC       10.0.13.2   (đường mới)
0.0.0.0/0         STATIC       10.0.1.1
~~~

Traffic tới **10.30.10.15** theo prefix /24 nếu nó được cài hợp lệ. Kiểm thử không được chỉ xác minh có route /16 “qua firewall”: một route cụ thể hơn có thể làm tất cả packet tới DB đi lối khác.

### 7.2. Administrative distance khác metric

Metric OSPF, BGP local preference, MED và administrative preference **không nằm trên một thang điểm chung**. OSPF cost phục vụ lựa chọn đường trong OSPF; BGP có quy tắc best-path policy riêng; administrative preference của hệ điều hành thường giải quyết những route cùng prefix từ các nguồn khác nhau. Các giá trị mặc định phụ thuộc vendor, không sao chép một con số cho mọi hệ thống.

### 7.3. ECMP và định tuyến bất đối xứng

**ECMP (Equal-Cost Multi-Path)** có thể phân phối nhiều flow qua nhiều next hop cùng chi phí. Cơ chế hash, weights và số next hop khác nhau theo thiết bị. Vì vậy:

- Một packet capture ở chỉ một đường có thể bỏ sót traffic qua nhánh kia.
- Hai nhánh phải có **firewall/IPS và logging** theo yêu cầu.
- Tránh một nhánh cho phép USER tới DATA trong khi nhánh còn lại chặn.
- Đường đi và đường về có thể khác nhau; stateful firewall, NAT và session tracking có thể bị ảnh hưởng.
- Sau failover phải kiểm tra **ứng dụng và security boundary**, không chỉ route state.

## 8. Các mối đe dọa đối với routing

### 8.1. Rogue neighbor và route injection

Nếu router tạo adjacency hoặc nhận route từ nguồn không được phép, thông tin điều khiển giả hoặc sai có thể thay đổi hướng traffic. Nguyên nhân có thể là cấu hình sai, một thiết bị mới được nối vào segment tin cậy, tài khoản quản trị bị lộ hoặc một peer hợp lệ bị xâm phạm.

**Phòng vệ:** chạy routing protocol trên đúng interface; xác thực và giới hạn peer theo cơ chế được hỗ trợ; lọc prefix; áp dụng ACL/control-plane protection và giám sát neighbor bất thường. **Xác thực neighbor không ngăn được mọi lỗi do neighbor hợp lệ tự quảng bá prefix sai.**

### 8.2. Route hijack

**Route hijack** xảy ra khi thông tin reachability không đúng thẩm quyền khiến mạng khác có thể chọn đường đến một nguồn không mong muốn. Trong môi trường BGP Internet, nó có thể liên quan AS không được ủy quyền quảng bá một prefix hoặc quảng bá một more-specific prefix.

Hậu quả có thể là mất kết nối, chuyển hướng đường đi, truy cập vào một next hop không đáng tin hoặc gây gián đoạn. **Một thay đổi AS_PATH khác thường là tín hiệu để điều tra**, không tự chứng minh có kẻ tấn công.

### 8.3. Route leak

**Route leak** là việc route được xuất/nhập giữa các quan hệ định tuyến trái với chính sách, ví dụ một AS vô tình quảng bá route học từ upstream cho một upstream/peer khác, khiến traffic đi vòng hoặc biến AS thành đường transit ngoài dự kiến.

Ngăn route leak cần **chính sách import/export theo quan hệ peer**, lọc prefix/AS, giới hạn route, quan sát những prefix đang quảng bá và các cơ chế peer role được hỗ trợ. **RPKI origin validation không tự ngăn mọi route leak.**

### 8.4. Blackhole và routing loop

- **Blackhole:** traffic tới một prefix bị loại bỏ hoặc không thể tới đích do next hop hỏng, discard route, route sai, failover không hoạt động. Một số blackhole được áp dụng **có chủ đích** nhằm giảm tác động DDoS; cần phân biệt với sự cố ngoài ý muốn.
- **Routing loop:** các thiết bị tiếp tục chuyển tiếp gói qua nhau do thông tin route không nhất quán. IPv4 TTL hoặc IPv6 Hop Limit ngăn packet tồn tại vô hạn nhưng loop vẫn có thể gây mất gói và cạn băng thông.

### 8.5. Route redistribution sai phạm vi

Redistribution cho phép chuyển thông tin route từ một nguồn/protocol vào nguồn/protocol khác. Nếu quảng bá nhầm **default route, prefix quản trị, mạng tenant khác hoặc nhiều route connected**, các thiết bị có thể chọn đường ngoài dự kiến. Giới hạn prefix được redistribute, gắn owner và route policy/tag, kiểm tra nguy cơ vòng redistribution và đối chiếu toàn bộ downstream.

### 8.6. Management-plane compromise và config drift

Một static route /32, một BGP export rule hay một OSPF default injection sai có thể làm đổi hướng traffic trên diện rộng. Tài khoản quản trị và automation cần **MFA, least privilege, logging, version control, review, đường quản trị độc lập và rollback**. Định kỳ so running/effective configuration với bản được phê duyệt.

## 9. Bảo vệ static routing

### 9.1. Quản trị inventory

Với mỗi route, cần có **prefix, VRF, next hop, interface, mục đích, người sở hữu, ticket, trạng thái primary/backup và kỳ rà soát**. Cần xác nhận rằng điểm chuyển tiếp nằm trên đường qua firewall/IPS nếu chính sách yêu cầu.

### 9.2. Rà soát default và host routes

Route **0.0.0.0/0**, **::/0** hoặc host route cụ thể /32, /128 có thể tác động nhiều kết nối hoặc làm đổi đường của một tài sản trọng yếu. Trước khi thay đổi:

1. Tính toán longest prefix match và cùng-prefix preference.
2. Xem **policy-based routing (PBR)**, VRF, ECMP và NAT.
3. Xác định route của **đường về**.
4. Xác nhận firewall, IDS/IPS và audit log được thực thi trên đường dự kiến.
5. Thử các lưu lượng hợp lệ và không được phép ở **đúng vùng nguồn**.

### 9.3. Floating và tracked static

**Floating static** là tuyến dự phòng thường đặt preference kém hơn tuyến chính cùng prefix. Nếu tuyến chính vẫn tồn tại mặc dù đích xa không tới được, backup có thể không được chọn. Cơ chế **tracking** có thể buộc rút route hoặc đổi chính sách khi health check thất bại.

**Không lấy ICMP ping next hop làm bằng chứng ứng dụng end-to-end đã khỏe.** Gateway có thể trả ping trong khi link sau gateway hoặc database đã lỗi. Health check phải phản ánh phạm vi sự cố muốn phát hiện và có chống flapping hợp lý.

### 9.4. Ví dụ danh mục route

~~~yaml
route_id: STATIC-DR-LAB-001
router: core-r1
vrf: PROD
destination: 10.80.10.0/24
next_hop: 10.0.12.2
role: backup
business_purpose: reach disaster-recovery subnet
owner: network-platform-team
change_reference: CHG-LAB-001
review_due: "2027-02-28"
expected_security_path: segmentation-firewall
validation:
  allowed_flow: APP-to-DR-approved-service
  denied_flow: GUEST-to-DR
  result: pending
~~~

Các giá trị hoàn toàn **giả định**. Bản ghi inventory giúp review và audit nhưng không thay thế cấu hình router hoặc kết quả kiểm thử.

## 10. Bảo vệ OSPF và IS-IS

### 10.1. Chỉ cho neighbor cần thiết

Với IGP link-state, cần:

- Chỉ bật adjacency trên các interface/router được phép.
- Sử dụng **passive-interface** ở nơi chỉ cần quảng bá mạng nhưng không muốn hình thành adjacency, theo ngữ nghĩa nền tảng. Passive-interface **không nhất thiết dừng quảng bá chính subnet**.
- Giới hạn trust boundary ở L2/VLAN/tunnel, tránh tạo adjacency với mạng người dùng hoặc Wi-Fi khách.
- Cấu hình authentication/message integrity theo đúng phiên bản và hỗ trợ của thiết bị. **OSPFv2 và OSPFv3 không có cùng một cơ chế bảo vệ trong mọi triển khai**.
- Kiểm soát area, summary, default advertisement và redistribution.
- Giám sát neighbor resets, thay đổi link-state database, tần suất chạy SPF và sự tăng đột biến route.

### 10.2. Xác thực không thay thế lọc và kiểm thử

OSPF/IS-IS neighbor hợp lệ vẫn có thể quảng bá trạng thái không mong muốn do lỗi cấu hình hoặc thiết bị bị chiếm. Cần bảo vệ **management plane** của router, xác nhận topology dự kiến và kiểm tra đường gói. Các vấn đề thường gặp khi adjacency không lên gồm sai authentication, area, router ID, timer, MTU, interface và policy lọc traffic điều khiển.

### 10.3. Điều chỉnh thời gian hội tụ có rủi ro

Giảm hello/dead timers hoặc bật BFD có thể giúp phát hiện lỗi nhanh hơn trong một số kiến trúc, nhưng cũng có thể làm **flapping** khi link hoặc CPU bất ổn. Kiểm chứng trên topology đại diện, theo dõi control-plane CPU và sự kiện không mong muốn trước khi thay đổi trên mạng thực.

## 11. Bảo vệ BGP: peer, prefix và chính sách

### 11.1. Xác thực peer và bảo vệ control plane

BGP thường thiết lập phiên qua **TCP/179**. Một router edge phải biết chính xác peer IP, peer ASN, interface và loại quan hệ đang sử dụng. Có thể cân nhắc:

- **TCP MD5 Signature Option** hoặc **TCP-AO** khi hai đầu hỗ trợ và có chính sách quản lý khóa phù hợp.
- **GTSM / TTL security** khi topology cho phép nhằm hạn chế một số nguồn giả mạo từ xa; không thay thế xác thực.
- Chỉ cho phép lưu lượng BGP từ peer hợp lệ bằng network ACL/firewall/CoPP.
- Theo dõi kết nối/reset bất thường và thay đổi prefix count.

**Một BGP session Established chỉ chứng minh kênh phiên hoạt động**, chưa chứng minh route được quảng bá đúng thẩm quyền hay phù hợp chính sách.

### 11.2. Import policy và export policy

**Import policy** giới hạn route được chấp nhận từ peer; **export policy** giới hạn route mà router của mình được phép quảng bá cho peer. Chính sách nên xác định:

| Kiểm soát | Câu hỏi |
|---|---|
| Prefix allowlist | Peer được phép gửi/nhận đúng những prefix nào? |
| Prefix length | Có chặn prefix quá cụ thể hoặc bất thường ngoài thiết kế? |
| ASN / AS_PATH policy | Có danh sách peer/AS và nguồn tin cậy rõ không? |
| Max-prefix | Nếu peer quảng bá quá nhiều prefix thì xử lý thế nào? |
| Default route | Có vô tình leak 0.0.0.0/0 hoặc ::/0? |
| Internal/MGMT routes | Có leak prefix nội bộ, quản trị, lab hoặc tenant khác? |
| Communities / role | Có thực thi quan hệ upstream, customer, peer theo chính sách? |
| Route monitoring | Đã xem accepted/selected và advertised routes theo từng peer chưa? |

Không tin rằng “route đã nhận từ neighbor” tự động nên được quảng bá tiếp. Mỗi quan hệ eBGP cần export policy cụ thể để tránh biến hệ thống thành **transit ngoài ý muốn**.

### 11.3. RPKI Route Origin Validation (ROV)

**RPKI** là hạ tầng chứng thực liên quan quyền tài nguyên địa chỉ. **ROA (Route Origin Authorization)** thể hiện AS nào được ủy quyền làm origin cho một prefix, kèm giới hạn độ dài prefix. Router thực hiện **ROV** có thể phân loại route:

| Kết quả | Ý nghĩa |
|---|---|
| **Valid** | Origin AS/prefix length phù hợp ROA liên quan |
| **Invalid** | Có ROA liên quan nhưng origin hoặc prefix length không khớp |
| **NotFound** | Không có ROA phù hợp để đưa ra xác nhận origin |

Với **Invalid**, các mạng triển khai ROV thường ưu tiên loại bỏ hoặc xử lý theo policy đã đánh giá tác động, nhưng cần lưu ý ROA và dữ liệu validator sai/cũ có thể chặn nhầm traffic hợp lệ. **NotFound không tự đồng nghĩa route xấu**; Valid cũng không xác nhận toàn bộ AS_PATH là đáng tin.

ROV **không** xác minh mọi AS path, không chặn tất cả route leak, không xác thực nguồn nội dung ứng dụng và không thay thế prefix filtering. Giám sát tình trạng validator/RPKI-to-router cache và quy trình xử lý ROA là bắt buộc khi bật ROV.

### 11.4. BGP roles và route leak prevention

**BGP Role** và thuộc tính **Only-To-Customer (OTC)** giúp một số triển khai hạn chế route leak dựa trên quan hệ BGP peer khi hai phía hỗ trợ. Tuy nhiên, chúng không loại bỏ yêu cầu thiết kế import/export policies, lọc route và kiểm thử khả năng truyền quảng bá theo peer.

### 11.5. Điều cần đo khi đổi chính sách BGP

Không chỉ kiểm tra routing table trên router: cần xem **received routes**, **accepted/selected routes**, **advertised routes**, next-hop reachability, effective filter, prefix count và RPKI state. Một route chưa được chọn vào FIB vẫn có thể **bị quảng bá nhầm** theo cấu hình/chính sách của hệ thống khác.

## 12. Cloud, VPN, Wi-Fi và microsegmentation

### 12.1. Cloud VPC/VNet

Cloud route tables có thể dẫn traffic tới **Internet gateway, NAT gateway, peering, transit, VPN, private endpoints hoặc thiết bị bảo mật ảo**. Một tuyến cụ thể hơn có thể tạo đường không đi qua security appliance. Kiểm tra theo **subnet association và effective routes** của đúng workload; không chỉ xem bảng route tổng.

Security groups/NSG/NACL còn điều khiển quyền truy cập, nên có route chưa chắc kết nối được. Ngược lại, policy ACL có thể đúng nhưng không có hiệu lực với traffic **không đi qua điểm kiểm soát đó**.

### 12.2. VPN site-to-site và SD-WAN

Dynamic BGP qua VPN/hybrid connectivity giúp nhận nhiều prefix nhưng có rủi ro **đối tác quảng bá prefix ngoài mong đợi**. Giới hạn import/export theo prefix, kiểm tra tunnel health, NAT, asymmetric return path, MTU và yêu cầu xác thực. Không mặc định mọi mạng mà peer học được nên mở quyền đến mạng nội bộ.

### 12.3. Wi-Fi khách và NAC

NAC/802.1X có thể đặt thiết bị vào VLAN/role; router L3 vẫn có thể biết đường giữa VLAN người dùng và subnet DATA. **Route tồn tại không đồng nghĩa truy cập được phép**. Phải có firewall/segmentation ngăn guest hoặc thiết bị chưa được xác thực chạm tài sản nhạy cảm.

### 12.4. Kubernetes và overlay

Trong container/cloud-native, CNI, overlay, service routing hoặc eBPF có thể điều khiển đường pod-to-pod. **NetworkPolicy** có vai trò giới hạn kết nối nếu được thực thi đúng; nó khác với routing. Một route tới DB có thể tồn tại mà traffic vẫn bị NetworkPolicy/host firewall chặn.

## 13. Failover nhanh nhưng không được bypass security

Khi một route chuyển sang dự phòng, hãy xem đồng thời:

- **Control-plane convergence:** lỗi được phát hiện, update được xử lý, route được chọn.
- **Data-plane forwarding:** FIB cài đúng next hop và traffic không loop/blackhole.
- **Security path:** cả đường chính và dự phòng đều đi qua enforcement point dự kiến.
- **Return path:** stateful firewall và NAT thấy đúng chiều của phiên.
- **Application readiness:** TLS, DNS, MTU, database, Identity Provider và các dependency phục hồi.

Một mô hình phục hồi giản lược:

\[
T_{\text{recovery}} \approx T_{\text{detection}} + T_{\text{route selection}} + T_{\text{FIB installation}} + T_{\text{application recovery}}
\]

Các giai đoạn có thể chồng nhau và không có một giới hạn thời gian bảo đảm cho mọi client. BFD có thể giảm **thời gian phát hiện lỗi** nhưng không chữa lỗi chính sách firewall trên đường backup.

**Trade-off:** một thiết kế fail-open có thể ưu tiên giữ đường truyền nhưng nếu bypass IPS/firewall theo cách chưa được duyệt sẽ làm giảm bảo vệ. Thiết kế an toàn nên có **backup path với các kiểm soát tương đương**, capacity dự phòng và cảnh báo khi lớp bảo vệ bị bỏ qua.

### Ma trận an toàn trước và sau failover

| Luồng | Primary path | Backup path | Kỳ vọng |
|---|---|---|---|
| APP → DB TCP/5432 | Qua DATA firewall | Qua DATA firewall | ALLOW ở cả hai |
| USER → DB TCP/5432 | Qua DATA firewall | Qua DATA firewall | DENY ở cả hai |
| GUEST → MGMT SSH | Bị chặn | Bị chặn | DENY ở cả hai |
| MGMT bastion → server quản trị | Theo allowlist | Theo allowlist | ALLOW theo role đã duyệt |
| APP → DNS resolver | Theo mạng dịch vụ | Theo mạng dịch vụ | Không gián đoạn dịch vụ nền |

Nếu backup route không đi qua firewall và thiếu cơ chế thay thế tương đương, yêu cầu “mạng vẫn an toàn khi hỏng R1” **không đạt**, dù APP còn mở được kết nối.

## 14. Công cụ đọc route và quan sát đường đi

Các lệnh dưới đây dùng để **quan sát trong môi trường có quyền**, không sửa route, BGP peer hay OSPF configuration.

### 14.1. Linux: route lookup và policy routing

~~~bash
# Xem IPv4 và IPv6 routing table
ip -4 route show
ip -6 route show

# Xem policy routing rules có thể làm chọn bảng khác
ip rule show

# Hỏi route lookup tới địa chỉ DATA giả định
ip route get 10.30.10.15

# Khi cần xem toàn bộ các bảng trên máy lab
ip route show table all

# Xem địa chỉ/interface để xác định nguồn traffic
ip -br addr
~~~

**Giới hạn:** lệnh `ip route get` phản ánh **network namespace, IP nguồn, policy rules và ngữ cảnh** của host chạy lệnh. Nếu traffic thực xuất phát từ container khác, VRF khác hoặc bị policy-based routing, kết quả có thể khác. Nó cũng không nói lên kết quả firewall ở các chặng tiếp theo.

### 14.2. FRRouting (nếu lab sử dụng FRR)

~~~bash
# Các lệnh show của FRR, giả định daemon liên quan đã bật
vtysh -c "show ip route"
vtysh -c "show ipv6 route"
vtysh -c "show ip ospf neighbor"
vtysh -c "show bgp summary"
vtysh -c "show bgp ipv4 unicast"
~~~

Cú pháp có thể khác theo phiên bản FRR và các daemon đang hoạt động. Khi thấy BGP neighbor Established, tiếp tục xem **prefix được nhận, được chọn, được quảng bá và policy**; chỉ xem summary không đủ để xác minh route an toàn.

### 14.3. Lệnh quan sát theo phong cách Cisco

~~~text
show ip route
show ipv6 route
show ip ospf neighbor
show ip bgp summary
show ip bgp
show interfaces
show logging
~~~

Đây là **ví dụ các lệnh read-only kiểu Cisco**, không phải cú pháp chung cho mọi router hoặc phiên bản hệ điều hành. Với Juniper, cloud gateway hoặc thiết bị khác, dùng phương thức xem trạng thái tương ứng.

### 14.4. Traceroute và packet capture

~~~bash
# Traceroute cơ bản, chỉ sử dụng tới endpoint lab được phép
traceroute -n 10.30.10.15

# Quan sát lưu lượng ICMP/ICMPv6 trong phạm vi có quyền
sudo tcpdump -ni any 'icmp or icmp6'
~~~

Traceroute là công cụ chẩn đoán **không phải chứng cứ tuyệt đối về mọi router đang có trên đường**: một số thiết bị không trả ICMP, traffic có thể đi tunnel, ECMP hoặc có return path khác. Packet capture chỉ có ý nghĩa tại vị trí bắt gói; cần đối chiếu với flow logs và telemetry của điểm kiểm soát thực.

## 15. Giám sát routing security

| Tín hiệu | Có thể chỉ ra | Điều cần xác minh |
|---|---|---|
| OSPF adjacency reset tăng | Link flap, lỗi cấu hình, CPU/timer, neighbor lạ | Giao diện, auth, nhật ký thay đổi, baseline |
| BGP session reset hoặc neighbor mới | Lỗi kết nối/peer hoặc thay đổi ngoài kế hoạch | IP/ASN peer, change ticket, ACL |
| Prefix mới xuất hiện | Route mới, redistribute, route injection | Prefix allowlist, owner, next hop |
| More-specific route bất thường | Đường bị chuyển khỏi policy route cũ | /32, /24, FIB và firewall boundary |
| Route rút hoặc thay next hop | Hội tụ/failover hoặc thay đổi sai | Cả primary và backup, đường về |
| BGP prefix count đột biến | Leak hoặc migration/full table thay đổi | Giới hạn max-prefix và advertised routes |
| RPKI Invalid tăng | ROA/origin sai hoặc route đáng nghi | Trạng thái validator, dữ liệu ROA, policy |
| OSPF LSDB/SPF churn | Topology không ổn định | Interface lỗi, link state, CPU |
| Firewall đột nhiên ít log traffic | Có thể thay path hoặc do logging | Flow logs, FIB, packet capture tại các đường |
| Lỗi ứng dụng sau failover | NAT, MTU, ACL, DNS hoặc backend | Request success, latency, dependency |

Đội mạng và SOC nên tương quan **route changes, interface health, firewall logs, VPN events, SIEM/IDS/IPS và ứng dụng** theo thời gian UTC. Một route đúng ở bảng BGP nhưng được cài sai vào FIB hoặc đi theo đường ngoài inspection vẫn cần xử lý.

### 15.1. Mẫu sự kiện thay đổi route

~~~yaml
event_id: ROUTE-LAB-CHANGE-001
time_utc: "2026-11-28T08:00:00Z"
router: core-r1
vrf: PROD
prefix: 10.30.10.0/24
route_source: OSPF
old_next_hop: 10.0.12.2
new_next_hop: 10.0.13.2
reason: authorized-failover-exercise
change_reference: CHG-LAB-001
security_boundary: segmentation-fw-data
expected:
  allow_test: APP-to-DATA-TCP-5432
  deny_test: USER-to-DATA-TCP-5432
validation_result: pending
~~~

Mẫu trên là **dữ liệu giả định**, không chứng minh một lần failover đã diễn ra. Trong vận hành thật cần gắn bằng chứng route, trạng thái firewall, phiên ứng dụng và người phê duyệt thay đổi.

## 16. Bộ kiểm thử static/dynamic routing và đường truy cập

| Test ID | Mục tiêu | Cách kiểm tra an toàn | PASS khi |
|---|---|---|---|
| **STATIC-01** | Static route tới DATA đúng | Đọc bảng route/FIB trên R1/R2 | Prefix, next hop, VRF khớp thiết kế |
| **STATIC-02** | Backup static đủ điều kiện được dùng | Mô phỏng lỗi trong lab được phép | Tracker/primary/backup hoạt động theo thiết kế |
| **DYN-01** | OSPF neighbor chỉ gồm router được duyệt | Đọc neighbor và interface config | Không có neighbor ngoài phạm vi |
| **DYN-02** | BGP nhận prefix hợp lệ | Đọc received, accepted, selected | Route đúng peer/prefix/AS/policy |
| **DYN-03** | Không quảng bá MGMT subnet sai peer | Đọc advertised route từng neighbor | Không có prefix nhạy cảm ngoài policy |
| **DYN-04** | Áp dụng RPKI origin validation | Kiểm tra ROV state và route mẫu trên lab | Xử lý Valid/Invalid/NotFound đúng policy |
| **ROUTE-01** | Longest prefix match đúng | Route lookup tới IP thuộc /16 và /24 | Next hop khớp security path |
| **ECMP-01** | Các nhánh cùng mức bảo vệ | So route, flow logs/capture từng nhánh | Không có nhánh bypass firewall |
| **ALLOW-01** | APP → DB TCP/5432 hoạt động | Kết nối test từ đúng APP zone | Đúng TCP/ứng dụng, đường qua firewall |
| **DENY-01** | USER → DB TCP/5432 bị chặn | Thử kết nối có giới hạn, đọc log | Firewall deny đúng flow, không có session |
| **MGMT-01** | Quản trị chỉ qua bastion được duyệt | So route, ACL và phép thử theo role | Đúng phân đoạn và quyền |
| **IPV6-01** | Không có đường IPv6 bypass | Xem ::/0, IPv6 prefixes, test nếu dùng dual-stack | IPv6 tương đương IPv4 theo chính sách |
| **HA-01** | Failover không phá kết nối hợp lệ hay mở quyền thừa | Chạy lại allow/deny sau đổi đường trong lab | Kết quả khớp SLO và policy |
| **REG-01** | Regression sau deploy | So baseline, logs, application health | Không có sai lệch chưa chấp thuận |

### 16.1. PASS/FAIL/INCONCLUSIVE

- **PASS:** quyết định route, đường packet và chính sách đúng như thiết kế, có đủ bằng chứng. Ví dụ APP → DATA TCP/5432 hoạt động còn USER → DATA TCP/5432 bị firewall từ chối tại điểm thực thi đã chỉ định.
- **FAIL:** tồn tại bằng chứng trái policy, như route /24 mới đưa USER → DATA qua đường không có inspection.
- **INCONCLUSIVE:** thiếu bằng chứng hoặc kịch bản không hợp lệ, ví dụ đích DB đang tắt, chỉ thấy timeout nhưng không có log/positive control, hoặc test từ sai VRF.

**Ping bị chặn không chứng minh TCP/5432 được phân đoạn đúng.** Nếu cần kiểm tra luồng ứng dụng, phải tạo request hợp lệ từ nguồn được phép và một negative test có kiểm soát từ nguồn không được phép, kết hợp log.

### 16.2. Dữ liệu tối thiểu lưu cho từng test

~~~text
Test ID:            DENY-01
Environment:        authorized lab
Source:             USER 10.10.10.21
Destination:        DATA 10.30.10.15:5432/TCP
Route expectation:  through segmentation-fw-data
Network policy:     DENY for direct USER -> DATA
Observed result:    pending
Required evidence:  source result + route lookup + firewall log
Positive control:   APP -> same DB:5432 should succeed
Owner:              network-security-team
~~~

Không sử dụng mẫu này như kết quả thực tế khi chưa có phép thử, thời gian và bằng chứng.

## 17. Quy trình triển khai thay đổi routing an toàn

### Bước 1 — Xác định phạm vi

Ghi **prefix, ASN/area khi liên quan, peer, VRF, source/destination zone, routing policy và next hop** dự kiến. Xác định thay đổi là static, dynamic, redistribution hay thay policy của cloud gateway.

### Bước 2 — Thu baseline

Lưu cấu hình running/effective, bảng RIB/FIB, neighbor, route filtered/advertised, các flow đi qua firewall, metric ứng dụng, IPv4/IPv6 và route chiều về. Ghi thời gian để đối chiếu khi sự cố xảy ra.

### Bước 3 — Phân tích rủi ro

Xem longest prefix match, same-prefix preference, ECMP, PBR, NAT, firewall stateful, VPN/tunnel MTU, cloud route tables và khả năng tạo đường không qua IDS/IPS. Xác định những tài sản quan trọng và luồng bắt buộc phải bị chặn.

### Bước 4 — Chuẩn bị policy và rollback

Review static destination/next hop, auth peer, prefix import/export, max-prefix, RPKI/ROA nếu có, tracked/floating route và đường truy cập quản trị dự phòng. Chuẩn bị phiên bản trước thay đổi để khôi phục.

### Bước 5 — Kiểm thử có kiểm soát

Trong lab hoặc vùng thử nghiệm, xác minh **positive và negative paths**, route learned/selected/advertised, hội tụ failover và sức khỏe ứng dụng. Đừng thử phá neighbor hoặc gửi route sai vào phiên production không thuộc một đợt diễn tập được phê duyệt.

### Bước 6 — Triển khai và giám sát

Áp dụng thay đổi theo cửa sổ và người chịu trách nhiệm rõ ràng. Theo dõi prefix count, neighbor sessions, FIB, packet drops, firewall logs, latency, application SLO và đường quản trị.

### Bước 7 — Regression/rollback

Nếu xuất hiện bypass, blackhole hoặc tác động không chấp thuận, kích hoạt phương án rollback phù hợp. Nếu đạt mục tiêu, lưu kết quả kiểm thử, owner, version config và update topology để tránh route drift.

~~~mermaid
flowchart TD
    A["Yêu cầu route + trust boundary"] --> B["Baseline RIB/FIB, peer, ACL"]
    B --> C["Phân tích prefix, next hop, return path"]
    C --> D["Review filters, auth, rollback"]
    D --> E["Thử trong lab / mô phỏng có phép"]
    E --> F{"Đủ điều kiện an toàn?"}
    F -- "Chưa" --> C
    F -- "Có" --> G["Triển khai giới hạn"]
    G --> H["Quan sát route, firewall, ứng dụng"]
    H --> I{"Đúng kỳ vọng?"}
    I -- "Không" --> J["Rollback và điều tra"]
    I -- "Có" --> K["Lưu bằng chứng, cập nhật inventory"]
~~~

## 18. Case study: Route backup vô tình bypass firewall

### 18.1. Tình huống giả định

Một doanh nghiệp có APP ở **10.20.10.0/24**, DATA ở **10.30.10.0/24** và USER ở **10.10.10.0/24**. Đường chính tới DATA qua firewall phân đoạn, cho phép APP → DB TCP/5432 và chặn USER → DB. Do nhu cầu HA, đội mạng thêm đường dự phòng qua Core-R2.

Sau một thay đổi route, một số lưu lượng được đưa tới **10.30.10.0/24** qua Core-R2. Core-R2 không có enforcement tương đương firewall. Trong lab, một kết nối USER → DB có thể hoàn tất TCP handshake.

### 18.2. Các câu hỏi điều tra

1. **Route nào thắng?** Có phải more-specific /24 static, OSPF /24 hoặc ECMP qua R2?
2. **Từ nguồn nào?** Test thực sự xuất phát từ vùng USER hay từ MGMT có quyền đặc biệt?
3. **Đường nào đã đi?** Flow logs/capture tại R2 và firewall có xác nhận không?
4. **Đường về ra sao?** DATA có return route và firewall state đúng không?
5. **DB có hoạt động?** Positive control APP → DB chứng minh endpoint test thực sự lắng nghe không?
6. **Policy có nằm trên tuyến?** Firewall chính có rule deny nhưng packet có đi qua firewall đó không?

### 18.3. Ví dụ bằng chứng giả định

~~~text
Expected:
  APP -> DATA TCP/5432         ALLOW via segmentation firewall
  USER -> DATA TCP/5432        DENY at segmentation firewall

Observed in fictional lab:
  APP -> DATA                  TCP connect success
  USER -> DATA                 Unexpected TCP connect success
  FIB route DATA /24           Next hop Core-R2
  Core-R2 telemetry            USER -> DATA flow observed
  Primary firewall             No matching deny event

Conclusion:
  FAIL - backup routing path bypasses intended segmentation control.
~~~

**Chú ý:** thiếu firewall log đơn lẻ **không chứng minh bypass**, vì logging có thể tắt hoặc bị lấy mẫu. Kết luận cần dựa trên toàn bộ route/path evidence và kết quả kết nối.

### 18.4. Hướng xử lý

- Bảo đảm cả primary và backup đều đi qua **điểm kiểm soát tương đương** hoặc chỉnh lại topology/policy được phê duyệt.
- Rà soát prefix cụ thể hơn, ECMP, PBR, VRF và return route.
- Cập nhật ma trận kiểm thử **ALLOW/DENY cho từng đường**, không chỉ cho topology bình thường.
- Giám sát thay đổi next hop/FIB của các prefix nhạy cảm DATA/MGMT.
- Chạy lại ứng dụng và test segmentation sau khắc phục, lưu rule ID, logs và kết quả.

**Bài học:** firewall có cấu hình đúng vẫn không bảo vệ luồng **không đi qua nó**. Routing security phải được kiểm chứng cùng access control.

## 19. Troubleshooting: bảng route đúng nhưng traffic sai

| Triệu chứng | Giả thuyết | Cần quan sát |
|---|---|---|
| Route có ở BGP RIB nhưng không có trong FIB | Next hop không resolve, bị filter hoặc route khác được chọn | Selected route, recursive next hop, FIB |
| Static route vẫn tồn tại dù đích xa hỏng | Link gần vẫn up, không có tracking phù hợp | Route tracker, health của next hop xa |
| OSPF neighbor không lên | Area/auth/timer/MTU/router ID/interface mismatch | Neighbor state, interface, log |
| BGP Established nhưng thiếu prefix | Import filter, next-hop, ROV policy, max-prefix | Received/accepted routes, route maps |
| Peer nhận prefix không nên có | Export/redistribution sai | Advertised routes, prefix policy |
| DATA traffic bypass firewall | More-specific route, ECMP, PBR hoặc VRF leak | FIB, packet/flow logs trên nhiều chặng |
| Chỉ chiều đi tới đích | Return routing, NAT, stateful firewall | Capture hai phía và firewall session |
| Chỉ IPv6 lỗi | ::/0, IPv6 prefix hoặc ACL khác IPv4 | A/AAAA, bảng IPv6, firewall logs |
| Failover thành công nhưng app lỗi | MTU, TLS, DNS, database, session cũ | App tracing, LB, VPN và dependency |
| BGP prefix count tăng nhanh | Route leak, migration hoặc thay đổi được duyệt | Change ticket, route count, policy |
| Route thay đổi liên tục | Link flap, timers, conflicting advertisements | Timeline, CPU, interface errors |

### Trình tự điều tra một flow lỗi

1. Ghi **source IP, destination IP, port, protocol, VRF và thời điểm UTC**.
2. Xem route lookup ở **đúng host/router/namespace**, không từ máy quản trị khác vùng.
3. Xác định route đã được chọn vào FIB, next hop, interface và các policy bổ sung.
4. Kiểm tra đường đi và return path, ECMP, NAT, tunnel và firewall state.
5. Đối chiếu firewall/IPS logs tại **đúng đường** đã ghi nhận, không chỉ điểm kiểm soát theo sơ đồ.
6. Với dynamic routing, xem neighbor, received/selected/advertised routes, filters và trạng thái hội tụ.
7. Kiểm tra DNS, ứng dụng và các dependency trước khi quy trách nhiệm cho định tuyến.

## 20. Bài tập

### Bài 1 — Longest prefix match

Router có /16 tới DATA qua firewall, /24 tới database subnet qua Core-R2, và default route. Traffic tới một IP thuộc /24 sẽ đi đâu?

*Gợi ý:* /24 nếu được cài hợp lệ trong đúng FIB. Cần xác minh Core-R2 có duy trì security boundary không.

### Bài 2 — Static và dynamic

Chi nhánh có một uplink chính, một uplink backup và rất ít prefix. Nêu lợi ích/giới hạn của static có tracker và dynamic routing.

*Gợi ý:* static đơn giản, dễ audit nhưng tracking có thể không phản ánh lỗi xa; dynamic linh hoạt khi topology lớn hơn nhưng cần neighbor auth, filter và giám sát convergence.

### Bài 3 — Route priority

Một static default route có administrative preference tốt, trong khi OSPF học /24 cho APP. Static default có chắc chắn thắng khi gửi packet tới APP không?

*Đáp án:* không. /24 cụ thể hơn /0 trong FIB; preference thường giải quyết route cho **cùng prefix**.

### Bài 4 — OSPF neighbor từ Wi-Fi khách

Vì sao một router không nên hình thành OSPF adjacency với host trong guest VLAN? Hãy đề xuất ba biện pháp.

*Gợi ý:* giới hạn interface, passive-interface theo ngữ cảnh, xác thực thông điệp, L2 segmentation, ACL/CoPP và alert neighbor lạ.

### Bài 5 — BGP route leak

Một BGP peer có TCP MD5 hợp lệ vẫn quảng bá route học từ upstream theo chiều không được phép. Vì sao authentication không đủ?

*Gợi ý:* peer hợp lệ có thể cấu hình sai; cần import/export policy, lọc prefix, role/OTC nếu hỗ trợ và giám sát advertised routes.

### Bài 6 — RPKI origin validation

Một route được ROV xác nhận **Valid**. Có thể kết luận mọi AS_PATH/peering relationships đều chính xác không?

*Đáp án:* không. ROV chỉ xác thực **origin authorization** theo dữ liệu ROA liên quan, không xác thực toàn bộ đường AS.

### Bài 7 — Failover security

Sau khi chuyển từ R1 sang R2, APP vẫn truy cập DATA nhưng USER cũng kết nối được DB. Cần xác minh và khắc phục điều gì?

*Gợi ý:* xem route/FIB, test source zone, firewall path, return traffic, rồi khôi phục điểm kiểm soát trên backup; regression-test cả ALLOW và DENY.

### Bài 8 — Read-only investigation

Khi một Linux app host timeout tới DATA, hãy đề xuất bốn phép quan sát không sửa hệ thống.

*Gợi ý:* `ip route get`, `ip rule show`, `ip -6 route show`, interface status, traceroute giới hạn, capture có quyền và firewall/route telemetry.

### Bài 9 — Cloud hybrid routing

Cloud vừa nhận nhiều subnet qua BGP VPN. Làm sao bảo đảm không làm lộ MGMT network?

*Gợi ý:* prefix allowlist/import-export, route association, NSG/security group, NAT, identity, next hop và giám sát received/advertised routes.

## 21. Checklist an toàn trước khi đổi routing

- Biết rõ **prefix, VRF, next hop, interface, owner và mục đích**.
- Đã kiểm tra **longest prefix match, route source preference, protocol metric và ECMP**.
- Management plane có **least privilege, MFA, audit, config diff và backup cấu hình**.
- OSPF/IS-IS chỉ tạo adjacency trên interface tin cậy, dùng cơ chế authentication và control-plane protection phù hợp.
- BGP có **peer allowlist, prefix import/export policy, max-prefix, RPKI origin validation khi áp dụng và route leak monitoring**.
- Route redistribution, default route và more-specific route **không tạo đường vòng** qua firewall/IDS/IPS.
- Đã kiểm tra **IPv4/IPv6, NAT, PBR, VRF, VPN, asymmetric return path và cloud routes**.
- Đường backup có **security controls tương đương** và được giám sát.
- Có **positive/negative test** từ đúng vùng, cùng tiêu chí PASS/FAIL/INCONCLUSIVE.
- Đo recovery ở **tầng ứng dụng**, không chỉ trạng thái neighbor hoặc bảng route.
- Có **rollback, kênh quản trị an toàn và trách nhiệm triển khai rõ**.

**Kết luận:** static routing cho khả năng điều khiển tuyến rõ ràng ở topology phù hợp; dynamic routing giúp mạng thích nghi với lỗi và thay đổi ở quy mô lớn hơn. **An toàn định tuyến** không nằm ở việc chọn static hay dynamic, mà ở việc bảo vệ control/management plane, kiểm soát route được quảng bá và chứng minh packet thực đi qua những ranh giới bảo mật đã định.

### Tài liệu tham khảo

- [RFC 2328 — OSPF Version 2](https://www.rfc-editor.org/rfc/rfc2328): link-state, area và tính toán SPF.
- [RFC 5340 — OSPF for IPv6](https://www.rfc-editor.org/rfc/rfc5340): OSPFv3.
- [RFC 4271 — A Border Gateway Protocol 4 (BGP-4)](https://www.rfc-editor.org/rfc/rfc4271): cách vận hành BGP.
- [RFC 7454 — BGP Operations and Security](https://www.rfc-editor.org/rfc/rfc7454): kiểm soát và vận hành BGP an toàn.
- [RFC 9234 — Route Leak Prevention and Detection Using Roles in UPDATE and OPEN Messages](https://www.rfc-editor.org/rfc/rfc9234): BGP roles và Only-To-Customer.
- [RFC 6811 — BGP Prefix Origin Validation](https://www.rfc-editor.org/rfc/rfc6811): origin validation bằng RPKI.
- [RFC 8210 — RPKI to Router Protocol, Version 1](https://www.rfc-editor.org/rfc/rfc8210): dữ liệu RPKI tới router.
- [RFC 5925 — The TCP Authentication Option](https://www.rfc-editor.org/rfc/rfc5925): TCP-AO cho peer.
- [RFC 5082 — The Generalized TTL Security Mechanism](https://www.rfc-editor.org/rfc/rfc5082): bảo vệ dựa trên TTL khi phù hợp.
- [RFC 5880 — Bidirectional Forwarding Detection](https://www.rfc-editor.org/rfc/rfc5880): phát hiện lỗi forwarding path.
- [NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy](https://csrc.nist.gov/pubs/sp/800/41/r1/final): thiết kế ranh giới firewall và kiểm soát đường truy cập.


