# Peering và rủi ro kết nối mạng mở rộng trong cloud

**Network peering** là hình thức liên kết hai mạng ảo để các tài nguyên trong mạng này có thể trao đổi lưu lượng với mạng kia thông qua hệ thống định tuyến do nhà cung cấp cloud hoặc nền tảng mạng quản lý. Trong những môi trường phổ biến, ta gặp **VPC peering** (Virtual Private Cloud) và **VNet peering** (Virtual Network). Peering có thể giúp kết nối các ứng dụng nội bộ, các tài khoản/subscription khác nhau, hoặc hai vùng cloud mà không cần công bố mọi dịch vụ lên Internet. Tuy nhiên, **địa chỉ IP private không phải bằng chứng định danh và peering không tự động tạo một vùng mạng đáng tin duy nhất**.

Khi số mạng, tài khoản, vùng, nhóm dịch vụ và kết nối hybrid tăng, mỗi đường peering mới có thể mở rộng **khả năng đi tới tài nguyên**, làm đường định tuyến phức tạp hơn, xuất hiện những đường truy cập ngoài dự kiến, tăng **blast radius** khi một workload bị xâm nhập, gây khó khăn cho DNS, giám sát, xử lý sự cố và thu hồi quyền. Một thay đổi tưởng nhỏ—thêm route sang CIDR của mạng đối tác hoặc nới firewall từ một dải IP—có thể tạo ra một đường **lateral movement** giữa môi trường vốn được thiết kế cách ly.

Bài thuộc chương **Bảo mật mạng cloud** của module **SECURITY_NETWORK_SECURITY**. Kiến thức được đặt trong hệ thống phòng vệ nhiều lớp: **network segmentation, firewall/security group, VPN, IDS/IPS, DNS security, xác thực kết nối, TLS/mTLS, zero-trust, giám sát cloud và thiết kế kiến trúc mạng an toàn**. Nội dung tập trung vào nguyên lý và cách đánh giá bảo mật; tính năng chi tiết của từng nhà cung cấp, vùng và dịch vụ phải được xác minh trên nền tảng thực tế.

> **Phạm vi an toàn:** mọi địa chỉ, tên mạng, route và policy trong bài là ví dụ giả lập cho môi trường được cấp quyền. Không tự kiểm tra reachability, quét cổng hoặc thay bảng định tuyến của cloud account không được quản trị. Các đoạn YAML, HCL và lệnh mang tính minh họa cần được đối chiếu tính năng/syntax thực tế trước khi áp dụng; **không tạo hoặc mở kết nối production chỉ từ ví dụ của bài học**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **VPC/VNet peering**, các mặt phẳng **routing, security policy, DNS, identity** và lý do peering không đồng nghĩa quyền truy cập.
2. Phân biệt **peering trực tiếp, hub-and-spoke, transit gateway/virtual WAN, site-to-site VPN, dedicated private connectivity, Private Endpoint/PrivateLink-like services** theo ranh giới kết nối.
3. Hiểu nguyên tắc **non-transitive routing** trong peering trực tiếp của các dịch vụ phổ biến; không mặc định A↔B và B↔C tạo A↔C.
4. Đánh giá **CIDR overlap, route specificity, route propagation, default routes, asymmetric routing, NAT, MTU và DNS resolution** khi nhiều mạng được nối.
5. Thiết kế **least-privilege access giữa subnets, workloads, services và tenants**, không mở tràn bằng dải CIDR hoặc cổng quản trị.
6. Phân tích nguy cơ **lateral movement, data exfiltration, management-plane abuse, transit/route leaks, hybrid trust expansion và mất visibility**.
7. Xây dựng threat model, ma trận allow/deny, kiểm thử từ đúng nguồn/đích và cơ chế giám sát **flow logs, DNS logs, firewall, routing changes, audit events**.
8. Lập quy trình rollout/rollback peering, kiểm soát thay đổi, xử lý sự cố và phương án cô lập khi nghi compromise.

## 2. Mạng cloud là gì trong ngữ cảnh peering?

### 2.1. Mạng ảo và phạm vi cô lập

Một **VPC** hoặc **VNet** thường là phạm vi mạng logic chứa một hay nhiều **subnet**, dải địa chỉ và chính sách kết nối. VM, container, database, managed endpoints hoặc private service interfaces có thể được gắn vào các subnet hoặc network interfaces theo cách nhà cung cấp hỗ trợ.

Các thành phần hay gặp:

| Thành phần | Vai trò | Giới hạn bảo mật cần nhớ |
| --- | --- | --- |
| **VPC / VNet** | Biên quản trị mạng ảo, địa chỉ và định tuyến | Không tự đảm bảo mọi workload bên trong cùng mức tin cậy |
| **Subnet** | Chia dải IP/đơn vị định tuyến | Subnet private không đồng nghĩa mọi outbound bị chặn |
| **Route table / UDR** | Chọn next hop theo destination prefix | Có route không có nghĩa firewall hoặc IAM cho phép |
| **Security group / NSG / distributed firewall** | Kiểm soát lưu lượng cho interface/subnet/identity tùy sản phẩm | Chính sách có thể khác theo chiều, statefulness và vị trí |
| **Network ACL / firewall appliance** | Kiểm soát ingress/egress theo mạng | Stateful/stateless và thứ tự rule cần xác minh |
| **VPC/VNet peering attachment** | Cho hai mạng có đường kết nối logic trực tiếp | Không mặc định cho phép transit qua một mạng thứ ba |
| **VPN gateway** | Tunnel mã hóa giữa mạng/site theo cấu hình | Không thay workload authentication/authorization |
| **Transit hub / virtual WAN / routing appliance** | Kết nối nhiều mạng và lựa chọn routes | Có thể mở transit/routing rộng hơn peering trực tiếp |
| **Private service endpoint** | Truy cập một dịch vụ qua địa chỉ/đường private theo sản phẩm | Không giống kết nối tất cả subnet của hai VPC |
| **DNS resolver/private zone** | Phân giải private hostnames | Đúng IP không đảm bảo đường đi hoặc quyền truy cập |
| **Flow/audit logging** | Quan sát traffic và thay đổi cấu hình | Không tự ghi HTTP payload hay chứng minh định danh user |

Không nên gom “private subnet”, “private IP” và “private peering” thành một khái niệm. **Private address** chỉ mô tả phạm vi địa chỉ, không xác định danh tính workload hay mức độ an toàn của lưu lượng.

### 2.2. Ví dụ hai mạng độc lập

~~~text
VPC-A (Orders production)                 VPC-B (Reporting)
CIDR 10.10.0.0/16                         CIDR 10.20.0.0/16

  app: 10.10.10.0/24                         report: 10.20.20.0/24
  db:  10.10.30.0/24                         tools:  10.20.40.0/24
       |                                             |
       +------ Peering A <----> B -------------------+

Mục tiêu nghiệp vụ:
  Reporting service chỉ được truy cập Orders read-only API trên TCP/443.

Không phải mục tiêu:
  Reporting tools truy cập thẳng database TCP/5432.
  VPC-B được quản trị VPC-A.
  Mọi máy của VPC-B truy cập mọi cổng VPC-A.
~~~

Peering ở đây tạo điều kiện có **network reachability**. Để Reporting gọi Orders API thành công, còn cần route đúng, security controls cho phép **đúng hai đầu**, dịch vụ lắng nghe, DNS phù hợp và **xác thực/authorization API**. Database production phải có chính sách deny dù route table có đường tới subnet database.

### 2.3. Peering thuộc data plane và control plane nào?

**Control plane** gồm API/console/IaC điều khiển tạo peering, chấp nhận attachment, thay route, cập nhật security groups, DNS sharing và logging. Một tài khoản có quyền sửa peering/route có thể tạo **đường mạng mới** dù chưa có quyền vào ứng dụng.

**Data plane** là lưu lượng thực sự từ source workload tới destination. Data plane chịu tác động của route tables, packet filters, connection tracking, dịch vụ listening, TLS, proxy và trạng thái các đường nối.

**Management plane** có thể liên quan tới quản trị network gateway, secret store, IAM, cloud organizations và audit logs. Không cho service account xử lý nghiệp vụ quyền sửa các route tables hoặc peering nếu không cần.

Một threat model tốt phải xem đồng thời:

- Ai được phép **tạo/chấp nhận/xóa peering**?
- Ai được **thay route tables** hoặc bật route propagation?
- Ai được **sửa firewall/security group/NSG**?
- Ai được **sửa DNS private zones/resolver rules**?
- Ai được **đọc/cấu hình flow logs và secret/mTLS certificates**?
- Sau khi kết nối được tạo, service identity nào **được phép gọi API hoặc database**?

### 2.4. Khác nhau giữa có đường và có quyền

Một phiên kết nối thành công thường đòi nhiều điều kiện phối hợp:

~~~mermaid
flowchart LR
  A["Source workload\nIP/identity"] --> R["Route source → destination"]
  R --> P["Peering / transit attachment"]
  P --> F["Firewall/SG/NSG/NACL\ncả hai chiều phù hợp"]
  F --> L["Destination listener\nvà response path"]
  L --> T["TLS/mTLS peer validation"]
  T --> Z["Application authorization"]
  Z --> D["Tài nguyên được phép"]
~~~

Sơ đồ thể hiện **các điều kiện cần kiểm tra**, không khẳng định một hệ thống có pipeline đúng trình tự như hình. Trong mạng thực, filter có thể áp ở nhiều điểm và cả lưu lượng trả lời. **Reachability** không đảm bảo authorization, và một lỗi network timeout không đủ kết luận peering đã bị xóa.

## 3. VPC/VNet peering hoạt động như thế nào?

### 3.1. Peering trực tiếp

Một peering attachment thường có hai đầu, có thể nằm ở hai **projects/accounts/subscriptions**, hai vùng hoặc cùng vùng tùy sản phẩm và quyền được cho phép. Người quản trị hai phía có thể phải **đề nghị/chấp nhận** peering, cấu hình route và security policy theo cách nền tảng yêu cầu.

Lợi ích:

- Sử dụng **private addressing và đường cloud network nội bộ** mà không cần công bố một public listener cho mọi backend.
- Giảm thao tác quản lý VPN tunnel/gateway chuyên dụng khi chỉ cần kết nối ít mạng.
- Hỗ trợ giao tiếp service-to-service cross-account hoặc cross-project khi topology hợp lý.
- Thường tránh một số thành phần trung gian tự quản, nhưng chi phí và tính sẵn sàng vẫn tùy vùng/sản phẩm.

Giới hạn:

- **Không mặc định transitive** qua VPC/VNet khác.
- Phải giải quyết **CIDR trùng nhau hoặc chồng lấn** trước khi kỳ vọng route rõ ràng.
- Chỉ có peering attachment **không tự có policy ứng dụng**.
- DNS private name và service discovery có thể không tự hoạt động xuyên peering.
- Mỗi kết nối mới làm tăng số đường cần audit, kể cả kết nối dormant chưa có traffic.

### 3.2. Non-transitivity là nguyên lý cần nhớ

Giả sử:

~~~text
     Peering A-B             Peering B-C
 VPC-A  <---------->  VPC-B  <---------->  VPC-C
 10.10.0.0/16        10.20.0.0/16        10.30.0.0/16

Mối quan hệ:
  A và B có peering trực tiếp.
  B và C có peering trực tiếp.
  KHÔNG tự suy A có thể route đến C thông qua B.
~~~

Trên các dịch vụ peering trực tiếp phổ biến của AWS/GCP và cơ chế VNet peering cơ bản của Azure, cần coi **peering không tự cung cấp khả năng transit qua một peer khác**. Muốn A↔C, phải thiết kế **kết nối/route trực tiếp khác** hoặc một **transit architecture có chức năng forwarding được hỗ trợ**. Một vài triển khai cho phép kết hợp route server, network virtual appliance, gateway transit hay hub routing riêng; đó **không còn là kết luận từ hai liên kết peering đơn thuần**.

**Không bảo đảm non-transitivity chỉ bằng một sơ đồ:** khi đặt firewall/router appliance trong VPC-B và bật forwarded traffic theo tính năng được phép, kiến trúc có thể mở đường A→B→C. Phải xem **effective routes và các thiết lập transit/gateway** thực tế.

### 3.3. Peering không giống routing toàn bộ Internet

Peering giữa hai VPC/VNet **không có nghĩa peer sẽ tự dùng Internet gateway, NAT gateway hoặc VPN của nhau**. Một số loại peering không cho phép dùng **edge-to-edge transit** hoặc gateway của peer, trong khi một số tính năng riêng như **gateway transit** được thiết kế rõ trong từng nền tảng.

Khi yêu cầu “VPC-B ra Internet qua security VPC-A”, phải xác định:

1. Nền tảng có **hỗ trợ transit/forwarding qua attachment** theo topology không?
2. Route tables và policy ở từng mạng có cho next hop như thiết kế không?
3. Source IP/NAT và **đường trả lời** có đối xứng theo yêu cầu firewall không?
4. Firewall appliance được phép xử lý routed traffic và có HA không?
5. Có tạo một đường **bypass egress inspection** nào khác không?

Không thêm 0.0.0.0/0 trỏ vào peering theo cảm tính rồi giả định sẽ thay thế một transit gateway được quản trị.

### 3.4. Cùng vùng và khác vùng

Peering **intra-region** và **inter-region** có thể khác về **hỗ trợ, chi phí dữ liệu, latency, quota, chính sách mã hóa transport nội bộ và khả năng DNS/firewall**. Không đưa ra khẳng định tuyệt đối “peering luôn miễn phí”, “luôn được mã hóa end-to-end bằng TLS” hoặc “luôn hỗ trợ xuyên vùng/tài khoản” cho mọi cloud.

Việc traffic đi trên backbone/private network của nhà cung cấp **không thay TLS/mTLS ở tầng workload** khi dữ liệu nhạy cảm hoặc identity service cần được xác thực. Private peering không tự chứng minh peer đang là đúng ứng dụng/danh tính cần truy cập.

### 3.5. Quy trình tạo kết nối ở mức khái niệm

~~~text
REQUESTER: chủ VPC/VNet A
  1. Chọn peer B, scope tài khoản/project/subscription, region.
  2. Kiểm tra quyền, không gian CIDR và mục đích kết nối.
  3. Tạo/đề nghị attachment.

ACCEPTER: chủ VPC/VNet B
  4. Xác minh requester, mục đích, owner và phạm vi trust.
  5. Chấp nhận hoặc từ chối theo change policy.

BOTH SIDES:
  6. Cấu hình route đến CIDR/endpoint được phép.
  7. Cấu hình SG/NSG/firewall và route trả lời.
  8. Kiểm tra DNS, TLS peer identity và application authorization.
  9. Bật logs, negative tests và xác nhận kết quả.
 10. Đăng ký owner, expiration/review, rollback.
~~~

**Thứ tự và cú pháp API** khác theo nhà cung cấp; một số nền tảng tự cài route hệ thống trong peering còn những nơi khác yêu cầu quản lý route rõ. Điều bất biến là **phải xác minh effective connectivity và security policy tại từng đầu**, không chỉ trạng thái “Active/Connected” trên console.

## 4. Phân biệt peering, transit hub, VPN và private service connection

### 4.1. Bốn nhóm kiến trúc

~~~mermaid
flowchart TB
  subgraph Direct["A. Direct peering"]
    A1["VPC A"] <-->|"Peering"| B1["VPC B"]
  end
  subgraph Hub["B. Hub-and-spoke / transit"]
    S1["Spoke A"] <--> H["Routing / inspection hub"]
    S2["Spoke B"] <--> H
    S3["Spoke C"] <--> H
  end
  subgraph Hybrid["C. Hybrid connectivity"]
    DC["On-premises"] <-->|"VPN / dedicated private connectivity"| HC["Cloud gateway / hub"]
    HC <--> W["Cloud workloads"]
  end
  subgraph Service["D. Private service access"]
    CS["Consumer VPC"] --> PE["Private service endpoint"]
    PE --> PS["Provider service\nscoped exposure"]
  end
~~~

Sơ đồ so sánh **phạm vi kết nối logic**. Bất kỳ topology nào cũng cần route, security policy, kiểm tra peer identity và giới hạn quyền; việc tồn tại hub không tự bảo đảm inspection nếu route bypass hub.

### 4.2. Bảng so sánh

| Mô hình | Đơn vị kết nối | Route/transitivity | Giá trị nổi bật | Rủi ro đặc trưng |
| --- | --- | --- | --- | --- |
| **Direct VPC/VNet peering** | Hai mạng ảo | Thông thường kết nối trực tiếp, không mặc định transit | Đơn giản cho ít mạng có quan hệ rõ | Mesh peering khó quản lý khi tăng nhiều mạng, route/SG drift |
| **Hub-and-spoke** | Nhiều spoke qua hub | Có thể hỗ trợ transit nếu hub được thiết kế cho forwarding | Chính sách tập trung, dễ gắn inspection | Hub thành điểm tập trung rủi ro, bypass do route sai |
| **Transit gateway / cloud WAN** | Attachments và routing domains | Route theo các bảng/chức năng transit được cấu hình | Mở rộng nhiều VPC, account, region | Route propagation/leaks và quyền sửa route trên diện rộng |
| **Site-to-site VPN** | Tunnel giữa network gateways | Theo route/tunnel/BGP hoặc static config | Kết nối hybrid có mã hóa qua môi trường mạng thích hợp | PSK/certificate/gateway, tuyến bất đối xứng, split routes |
| **Dedicated private circuit** | Cloud–data center/provider | Cần routing/BGP/virtual interface thích hợp | Đường truyền ổn định/riêng hơn Internet tunnel | Không mặc định mã hóa end-to-end, route leaks, phụ thuộc provider |
| **Private endpoint / service attachment** | Consumer kết nối tới **dịch vụ cụ thể** | Không giống full network-to-network peering | Thu hẹp reachable service surface | Endpoint policy, DNS confusion, cross-tenant service exposure |
| **Shared VPC/network ownership** | Dùng chung network do owner kiểm soát | Không phải một peering attachment tự thân | Chính sách tập trung cho teams/projects | Quyền quản trị mạng, tenant isolation và phân chia ownership |

**Peering không phải lựa chọn duy nhất cho mọi tích hợp.** Khi chỉ cần Reporting gọi một API, **private service endpoint hoặc API exposure có xác thực rõ** có thể giữ blast radius hẹp hơn việc cấp route tới toàn bộ mạng production. Ngược lại, khi ứng dụng cần nhiều dịch vụ ở nhiều VPC, một hub/transit có inspection và route domains riêng có thể phù hợp hơn nhiều peering chéo.

### 4.3. Không gian địa chỉ lớn không phải lý do để mở toàn bộ mạng

Peering có thể nối hai dải **/16** nhưng yêu cầu nghiệp vụ chỉ cần một dịch vụ. Không vì attachment ở cấp VPC mà network policy phải cho **10.20.0.0/16 → 10.10.0.0/16 ALL PORTS**. Có thể:

- Chỉ tạo route cần thiết theo khả năng nền tảng.
- Giới hạn SG/NSG/firewall cho **source workload/SG/identity hoặc subnet hẹp**.
- Dùng **mTLS và API authorization** tại destination.
- Chọn private endpoint nếu nhu cầu chỉ là một service.
- Dùng route table riêng cho môi trường prod/dev và nguồn không đáng tin.

Nếu nền tảng tự tạo route cho toàn CIDR peer, vẫn có thể duy trì **least privilege bằng các lớp lọc và authorization**, nhưng cần ghi nhận route đã mở rộng reachability tới những subnet nào.

## 5. CIDR, routing và nguy cơ đường đi không mong muốn

### 5.1. CIDR là vấn đề thiết kế trước khi tạo peering

Địa chỉ private RFC 1918 được nhiều tổ chức sử dụng, như **10.0.0.0/8, 172.16.0.0/12 và 192.168.0.0/16**. Khi các nhóm phát triển tự cấp IP cho từng VPC mà không quản lý tập trung, rất dễ xuất hiện:

~~~text
VPC-A production: 10.10.0.0/16
VPC-B analytics:  10.10.20.0/24

VPC-B trùng/chồng lấn một phần CIDR của VPC-A.
~~~

Nhiều dịch vụ peering trực tiếp không cho thiết lập peering giữa hai VPC/VNet có dải CIDR overlap theo quy tắc sản phẩm. Trong kiến trúc qua appliance/VPN/transit có NAT, đôi khi có cách làm việc với các CIDR trùng nhau, nhưng đó là **bài toán địa chỉ, translation và routing riêng**, không phải tự động được peering giải quyết.

**Nguy cơ nếu quy hoạch kém:**

- Không thể tạo peering hoặc route mong muốn.
- Một địa chỉ IP có thể chỉ tới các máy khác nhau ở hai mạng, gây nhầm route.
- DNS private name phân giải ra IP không reachable hoặc trỏ sai đối tượng.
- NAT ẩn nguồn thật, khiến firewall/forensic khó quy nguồn.
- Chuyển dịch account/region/tenant sau này tốn công renumbering.
- Route specificity/longest-prefix match đưa traffic tới next hop không dự kiến.

Do đó cần **IPAM (IP Address Management)**, ownership, lifecycle và kế hoạch CIDR trước khi nối các mạng được quản trị độc lập.

### 5.2. Longest-prefix match: route nào thắng?

Thông thường IP routing chọn tuyến có **prefix cụ thể nhất phù hợp đích**. Ví dụ một workload muốn đến 10.30.20.50:

| Destination | Next hop | Độ cụ thể |
| --- | --- | --- |
| 0.0.0.0/0 | NAT/Internet egress hoặc transit được cấu hình | Mặc định |
| 10.30.0.0/16 | Peering/Transit attachment B | Cụ thể hơn default |
| 10.30.20.0/24 | Firewall/other attachment C | Cụ thể hơn /16 |

Trong những bảng route có cả **10.30.0.0/16** và **10.30.20.0/24**, địa chỉ 10.30.20.50 thường khớp /24 trước. Tuy nhiên, thứ tự ưu tiên giữa các route **cùng prefix** còn phụ thuộc loại route, nguồn propagate và nền tảng. Không kết luận toàn bộ routing policy chỉ bằng quy tắc prefix dài nhất khi có các đặc tính cloud đặc thù.

**Tình huống rủi ro:** Security team nghĩ traffic 10.30.20.0/24 được chuyển qua firewall inspection hub, nhưng một thay đổi route table tạo next hop khác/ưu tiên khác và traffic không còn qua firewall. Đây có thể là **security inspection bypass** dù peering attachment vẫn hiển thị healthy.

### 5.3. Route source, destination và return path

Giả sử:

~~~text
VPC-A / Subnet-A: 10.10.10.0/24
VPC-B / Subnet-B: 10.20.20.0/24

Ứng dụng: 10.10.10.15 TCP/443 -> 10.20.20.50 TCP/443

Route từ A đến B:   10.20.0.0/16 -> peering A-B
Route từ B về A:    10.10.0.0/16 -> peering B-A
Destination policy: allow từ 10.10.10.15 hoặc identity đã xác minh
Return traffic:    phải có route và chính sách phù hợp
~~~

Chỉ có route A→B **không bảo đảm kết nối thành công**, vì B phải có đường trả lời và policy cho traffic phù hợp. Trong các security groups **stateful**, return packets của một kết nối được cho phép có thể không cần một ingress/egress rule đối xứng theo cùng cách; **stateless NACL** hoặc firewall khác có thể yêu cầu cổng ephemeral và rule chiều trả lời rõ ràng.

**Không áp cùng một suy luận về statefulness cho AWS security group, Azure NSG, GCP VPC firewall, appliance firewall và NACL**: phạm vi, thứ tự rules, statefulness và default behavior khác nhau. Cần kiểm tra tại từng điểm lọc trên đường đi.

### 5.4. Asymmetric routing và stateful inspection

Ví dụ:

~~~text
Request:  VPC-A -> Transit Hub -> Firewall-A -> VPC-B
Response: VPC-B -> Direct Peering --------------> VPC-A
~~~

Firewall-A có thể chỉ thấy request, không thấy response, gây timeout/connection resets nếu firewall yêu cầu theo dõi state theo cặp lưu lượng. Dù hai hướng network reachability tồn tại, **đường không đối xứng** có thể làm hỏng stateful inspection hoặc khiến forensic không đầy đủ.

Khi dùng hub/firewall appliances nhiều availability zones/regions:

1. Xác định ingress và egress attachments cho từng flow.
2. Kiểm tra route symmetry theo **nguồn, đích, AZ và failover mode**.
3. Kiểm tra NAT và stateful session synchronization nếu traffic có thể đổi firewall node.
4. Thử failover khi một AZ/firewall node down.
5. Ghi log ở **đúng điểm kiểm soát**; không coi việc thiếu firewall logs là bằng chứng không có traffic.

### 5.5. Default route và nguy cơ transit ngoài ý định

Một cấu hình “cho mọi lưu lượng qua hub” bằng 0.0.0.0/0 có thể hợp lý cho kiểm soát egress, nhưng chỉ khi:

- Hub/attachment hỗ trợ forwarding và route propagation tương ứng.
- Không tạo vòng lặp hay blackhole với route ngược.
- Gateway/firewall áp chính sách egress đúng, kiểm soát DNS/HTTPS nếu cần.
- Availability/capacity phù hợp với toàn bộ traffic được tập trung.
- Những subnet nội bộ và private service paths không bị route sang Internet hoặc ra sai tenant.

Nếu đổi default route nhưng **chưa bật inspection hoặc chưa chặn direct outbound alternative**, có thể vô tình khiến đường đi mất kiểm soát hoặc dịch vụ ngừng hoạt động. **0.0.0.0/0 không tương đương một security policy**; nó chỉ là lựa chọn next hop.

### 5.6. Route propagation và các domain độc lập

Transit hubs thường có cơ chế **route tables, associations, propagations** hoặc policy định tuyến theo từng attachment. Kết nối một spoke mới có thể làm xuất hiện route mới ở những bảng được import/propagate. Rủi ro:

- **Spoke Dev** vô tình học route tới **Spoke Prod**.
- Một route on-prem prefix rộng bao phủ mạng quản trị cloud.
- Route mặc định do một attachment đưa vào được ưu tiên ngoài ý định.
- Một VPC của đối tác được đưa vào cùng routing domain với dữ liệu khách hàng.
- Route leak giữa hai nhóm/tenants do sai association hoặc import/export policy.

Nguyên tắc: **tách routing domains theo mức tin cậy**, dùng explicit attachments/route advertisements được duyệt, review effective routes sau mọi thay đổi và test deny giữa những spoke không được phép liên lạc.

### 5.7. IPv6 không được bỏ quên

Peering và routing có thể hỗ trợ **IPv6** theo quy tắc riêng; đừng chỉ kiểm tra IPv4 10.0.0.0/8 rồi tuyên bố đã cách ly mạng. Một ứng dụng dual-stack có thể kết nối qua IPv6 khi IPv4 bị chặn. Những điểm cần kiểm tra:

- IPv6 CIDR của các VPC/VNet, route prefixes và egress paths.
- IPv6 firewall/NSG/security group rules đối xứng mục đích với IPv4.
- DNS **AAAA records** và lựa chọn đường của client (Happy Eyeballs/dual-stack behavior).
- IPv6 inbound/outbound reachability sau peering hoặc transit change.
- Log flow và detection hỗ trợ địa chỉ IPv6, tránh regex hoặc parser chỉ hiểu IPv4.

**Một deny trên IPv4 không mặc nhiên deny trên IPv6**, và peering IPv4 thành công không chứng minh IPv6 topology đã được thiết kế đúng.

### 5.8. MTU, MSS và fragmentation

Các đường hybrid có VPN/tunnel encapsulation, inspection firewall hoặc một số private network devices có thể giảm **MTU hiệu dụng**, gây tình trạng TCP kết nối được nhưng HTTPS/gRPC large responses bị treo. Các vấn đề thường gặp:

- Path MTU Discovery không hoạt động do chặn ICMP/ICMPv6 cần thiết.
- MSS không phù hợp với overhead tunnel.
- UDP/QUIC có yêu cầu và hành vi packetization khác TCP.
- Một số path có hỗ trợ jumbo frames, path khác không.

Khi điều tra, xem **packet size, retransmissions, ICMP PTB, TCP MSS/QUIC stats** và bảo vệ ICMP phù hợp thay vì tắt mọi ICMP. Không dùng “ping nhỏ thành công” để chứng minh MTU của ứng dụng đúng.

## 6. Firewall, security groups và nguyên tắc truy cập tối thiểu

### 6.1. Peering chỉ mở đường, không cấp toàn quyền

Giả sử yêu cầu:

> Reporting workload trong VPC-B được phép gọi Orders API HTTPS trong VPC-A, nhưng không được truy cập database, SSH/RDP hoặc Kubernetes API management.

Một ma trận chính sách:

| Nguồn | Đích | Giao thức/cổng | Quyết định | Lý do |
| --- | --- | --- | --- | --- |
| Reporting service identity/subnet 10.20.20.0/24 | Orders API 10.10.10.10 | TCP/443 | **Allow** với mTLS/API authorization | Nghiệp vụ báo cáo |
| Reporting service | Orders DB 10.10.30.20 | TCP/5432 | **Deny** | Không dùng truy cập DB trực tiếp |
| Reporting tools subnet 10.20.40.0/24 | Orders API | TCP/443 | **Deny** mặc định | Không thuộc workload được duyệt |
| Reporting service | VPC-A management 10.10.50.0/24 | TCP/22,3389,6443 | **Deny** | Rủi ro quản trị |
| Orders API | Reporting service callback | Theo thiết kế cụ thể | **Deny trừ khi có use case được duyệt** | Không tự mở hai chiều |
| Any unapproved peer | Secrets/KMS/metadata service | Các API nhạy cảm | **Deny** bằng identity/service policies | Chặn lạm dụng quyền |

Đây là ý định an ninh, không phải rule cloud vendor cụ thể. Một số dịch vụ hỗ trợ tham chiếu **security group/identity nguồn qua peering** trong những điều kiện nhất định, một số chỉ hỗ trợ CIDR/IP; phải dùng những selector thực sự có hiệu lực và được kiểm thử.

### 6.2. Kiểm soát nhiều lớp

~~~mermaid
flowchart LR
    S["Reporting workload\nVPC-B"] --> SG1["Egress SG/NSG\nleast privilege"]
    SG1 --> RT["Effective routes + peering"]
    RT --> FW["Network Firewall\nnếu kiến trúc đi qua"]
    FW --> SG2["Ingress SG/NSG\nOrders API"]
    SG2 --> TLS["TLS/mTLS\npeer identity"]
    TLS --> AUTH["API authorization\nprincipal, action, tenant"]
    AUTH --> D["Orders API"]
    SG2 -. "Không cho TCP/5432" .-> DB[("Orders DB")]
~~~

**Không mặc định một firewall appliance có trên mọi đường peering**. Nếu traffic đi trực tiếp A↔B và firewall appliance nằm tại hub khác không nằm trên route, nó không kiểm tra luồng. Vị trí controls phải gắn với **effective path**, không chỉ sơ đồ logic.

### 6.3. Khác biệt inbound và outbound

Nhiều đội chỉ cấu hình **inbound allowlist** ở VPC đích mà quên egress. Kịch bản compromise một máy trong VPC-B có thể dùng bất kỳ đường egress đang được phép để di chuyển sang các VPC khác, gọi API ngoài hoặc chuyển dữ liệu.

Các lớp nên xét:

- **Egress ở workload nguồn:** chỉ cho đúng đích/protocol cần dùng nếu nền tảng hỗ trợ.
- **Ingress ở workload đích:** chỉ nhận từ nguồn/identity được duyệt.
- **Firewall/inspection giữa hai mạng:** khi topology bảo đảm traffic đi qua và policy cần central enforcement.
- **mTLS/HTTP authorization:** hạn chế thao tác với tài nguyên dù network connection đã tới nơi.
- **DNS egress policy và service endpoints:** giảm các đường truy cập không được dự kiến.

Egress deny phải được thiết kế có tính đến **DNS, time sync, certificate validation, secret retrieval, control plane, monitoring** và các dependency thiết yếu để tránh chặn chính hạ tầng vận hành.

### 6.4. Stateful/stateless khác nhau theo sản phẩm

Một nhóm cloud security controls là **stateful**: khi outbound connection được cho phép, response traffic thường được nhận theo state của connection; nhóm khác là **stateless ACLs**: phải cân nhắc inbound/outbound và ephemeral port ranges.

Không áp cùng một tập rules máy móc trên cả:

- Security groups (interface-associated stateful filtering theo sản phẩm).
- NSGs hoặc VPC firewall rules (vị trí, order, tag/selector và semantics theo provider).
- Subnet ACLs hoặc route-based virtual firewall appliances.
- Kubernetes NetworkPolicy/CNI rules (ingress/egress, namespace/pod identity).
- Host firewalls trên VM và WAF/HTTP gateway.

Đánh giá **thứ tự rule, implied allow/deny, connection tracking và default behavior** của nền tảng thực. Để chứng minh deny hoạt động, thử kết nối **từ nguồn không được cấp quyền** ở cả IPv4/IPv6 khi liên quan, không chỉ đọc một rule mô tả.

### 6.5. Không mở mạng quản trị xuyên peering nếu không cần

Điểm rủi ro cao: mở **SSH/22, RDP/3389, Kubernetes API/6443, database admin ports hoặc secret-management endpoints** từ một peer network chỉ vì “cùng tổ chức”.

Giải pháp:

- Dùng **identity-aware access / bastion quản lý tập trung / just-in-time access** nếu cần quản trị.
- Chỉ cho phép source identities/cidrs chặt và MFA/RBAC với audit.
- Tách network management khỏi application peering.
- Không expose cloud instance metadata endpoints hoặc workload IAM credentials qua các service proxy ngoài dự kiến.
- Duy trì controls của ứng dụng/quản trị: một TCP connection thành công không phải quyền admin.

### 6.6. VPC sharing, multi-account và cross-tenant boundaries

Một peering giữa hai tài khoản thuộc cùng tổ chức **không có nghĩa account kia được tin bằng production**. Tài khoản sandbox, đối tác, nhà thầu hoặc acquired business có thể có tiêu chuẩn patching, IAM và logging khác.

Kiểm tra:

1. **Owner và trách nhiệm** của từng peer.
2. Ai được sửa **attachments, routes, firewall rules, DNS private zones**.
3. Workload identity và service authorization giữa hai account/subscription/projects.
4. Network egress của peer có thể dẫn sang vùng khác hay Internet không.
5. Có **direct network access tới management plane** hoặc databases không.
6. Khi hợp đồng/nhóm dự án kết thúc, có **quy trình offboarding** và xác minh xóa route/peering/permissions không.

**Không xây trust chỉ dựa trên CIDR của một account khác**: IP có thể được tái cấp, workload thay owner, hoặc đối tác cấp thêm subnet, làm scope bị nới rộng ngoài ý định.

## 7. DNS, private zones và nhầm lẫn định danh qua peering

### 7.1. Route đúng không đồng nghĩa tên miền phân giải đúng

Khi hai mạng đã peering, một VM ở VPC-A có thể kết nối tới địa chỉ IP của workload trong VPC-B, nhưng chưa chắc phân giải được **service-b.internal.example.test**. Nguyên nhân gồm:

- Private DNS zone chỉ liên kết với một VPC/VNet nhất định.
- DNS resolver forwarding giữa các mạng chưa cấu hình hoặc route tới resolver chưa tồn tại.
- DNS firewall/resolver policy chặn query hoặc kết nối UDP/TCP/53 cần thiết.
- Split-horizon DNS trả kết quả khác nhau tùy nguồn truy vấn.
- Cloud-managed internal hostname không được tự chia sẻ qua peering.
- DNS record trỏ tới địa chỉ vừa đổi, hoặc tới CIDR không reachable.
- Peering DNS option/route import/share private zone chưa bật hoặc không được nền tảng hỗ trợ.

**Định tuyến IP và phân giải DNS là hai lớp riêng**. Một test **ping IP** không chứng minh DNS hoạt động; một test **nslookup/dig thành công** cũng không chứng minh destination TLS/API truy cập được.

### 7.2. Split-horizon / split-brain DNS

Ví dụ:

~~~text
Client trong VPC-A:
  orders.internal.example.test -> 10.10.10.20

Client trong VPC-B:
  orders.internal.example.test -> 10.20.10.20

Client từ on-prem:
  orders.internal.example.test -> NXDOMAIN / IP thứ ba
~~~

Điều này **có thể được thiết kế có chủ ý**, nhưng cũng có thể do cấu hình DNS thiếu nhất quán. Rủi ro:

- Traffic đi tới **một service khác** có cùng hostname nhưng trust level khác.
- TLS certificate SAN không khớp IP/hostname trả về, dẫn tới lỗi handshake.
- Workload dùng DNS fallback/public answer và tình cờ truy cập Internet thay vì private endpoint.
- Máy dev truy cập production vì DNS private zone được chia sẻ nhầm.
- Logging ở DNS resolver này không thấy queries dùng resolver khác.

Để khắc phục, cần có **ownership của private zones**, namespace phân tách dev/staging/prod, forwarding policy, DNSSEC/validation khi phù hợp và **negative tests** cho nguồn không được phép.

### 7.3. DNS không phải access control

Nếu chỉ “giấu” hostname trong private DNS zone nhưng security group mở TCP/5432 cho toàn peer CIDR, một workload biết IP có thể kết nối thẳng mà không cần DNS. **Không cung cấp DNS record** không tương đương **deny network access**.

Ngược lại, một hostname private có thể phân giải đúng nhưng backend phải **xác minh workload identity/mTLS/authorization**. DNS trả tên không phải chứng cứ ứng dụng là chính danh.

### 7.4. Private endpoint và DNS override

Khi dùng private service endpoint, client có thể kết nối tới **tên dịch vụ quen thuộc** nhưng DNS nội bộ trả địa chỉ **private endpoint**. Đây là mô hình phổ biến để giữ lưu lượng tới một dịch vụ qua đường được phép thay vì full VPC peering.

Điểm cần review:

1. Private DNS zone được **associate/attach** với đúng networks.
2. IP endpoint nằm trong vùng địa chỉ được kiểm soát và route/firewall cho phép.
3. Endpoint policy, service consumer/provider identity và quyền tài nguyên thực sự hạn chế thao tác.
4. Không có public service endpoint/route thay thế ngoài ý định.
5. Cập nhật endpoint/DNS không làm một service name trỏ sang tenant/dịch vụ khác.
6. TTL/cache của resolver ảnh hưởng thời gian chuyển đổi/failover; theo dõi chênh lệch giữa clients.

**Private endpoint không giống VPC peering:** thường nó expose **một dịch vụ/attachment cụ thể**, không tạo tuyến mạng đầy đủ giữa hai VPC, nhưng mức độ riêng tư và kiểm soát vẫn phụ thuộc endpoint policy và network path.

### 7.5. DNS forwarding trong mạng hybrid

Với site-to-site VPN/private circuit:

~~~mermaid
flowchart LR
    APP["Cloud workload\n10.10.10.15"] --> RES["Cloud resolver"]
    RES -->|"Forward zone corp.example.test"| DNS["On-prem DNS\nqua hybrid link"]
    DNS -->|"Response private IP"| RES
    RES --> APP
    APP --> ROUTE["Hybrid route/firewall"]
    ROUTE --> DB["On-prem database"]
~~~

**Một truy vấn DNS thành công không đảm bảo network path tới IP trả về**. Nếu cloud resolver forwarded tới on-prem qua một VPN riêng nhưng application traffic phải qua transit firewall khác, cần kiểm tra route, SG, VPN/firewall và TLS của đường truy cập thực.

**DNS forwarding hai chiều** cần được thiết kế chống loops, ambiguous authoritative zones và query leaks. Không forward mọi domain nội bộ tới một network khác mà không có ownership/trust và policy logging.

### 7.6. Theo dõi DNS để phát hiện kết nối bất thường

DNS logs có thể hỗ trợ:

- Phát hiện service name không mong đợi ở một VPC mới peered.
- So sánh DNS resolution giữa nguồn prod/dev/on-prem.
- Phát hiện query đột biến tới hostname nội bộ chưa được cấp phép.
- Nhận biết failover private endpoint hoặc resolver forwarding sai.
- Tương quan query với flow logs và application traffic.

Nhưng **DNS query không chứng minh request tới service đã thành công**; có thể chỉ là health check, library prefetch hoặc client retry. Với **DNS over HTTPS/TLS từ endpoint không thuộc resolver kiểm soát**, DNS logs tập trung có thể không nhìn thấy queries, cần egress policy/endpoint governance nếu có mục tiêu giám sát.

## 8. Hybrid connectivity: VPN, private circuit, BGP và route advertisement

### 8.1. Kết nối cloud–on-premises mở thêm một trust boundary

Một tổ chức có thể nối cloud VPC/VNet tới data center qua:

- **Site-to-site IPsec VPN** qua các gateways được thiết kế cho mạng với xác thực peer và mã hóa.
- **Dedicated private connectivity** như các dịch vụ private circuit/express connectivity của cloud providers, tùy mạng/cổng đối tác.
- **Transit hub/cloud WAN** nối nhiều VPC/VNet và nhiều site.
- **SD-WAN/virtual network appliances** có chức năng route và kiểm soát traffic.

Một dedicated private circuit **không mặc định cung cấp TLS/mTLS hoặc encryption end-to-end** cho ứng dụng; nếu cần mã hóa và peer identity, dùng TLS/mTLS ở workload hoặc IPsec/tunnel theo yêu cầu.

### 8.2. Route học tự động bằng BGP

**BGP (Border Gateway Protocol)** có thể trao đổi prefixes giữa cloud gateways, data center routers và dedicated circuits/VPN. Rủi ro không nằm riêng ở BGP protocol mà ở **prefix được phép công bố và chấp nhận**:

~~~text
Cloud VPC:
  10.10.0.0/16

On-prem:
  172.20.0.0/16

Approved advertisements:
  Cloud -> on-prem: 10.10.0.0/16
  On-prem -> cloud: 172.20.0.0/16

Unintended advertisement:
  0.0.0.0/0 hoặc 10.0.0.0/8
  có thể đổi đường mặc định hoặc bao phủ nhiều VPC khác.
~~~

Thực hiện **route filtering/prefix lists, limits, import/export policies, route-table isolation và change review** phù hợp sản phẩm. Một tuyến prefix quá rộng không được chấp nhận chỉ vì nó xuất phát từ router “nội bộ”.

### 8.3. BGP route leak và việc mở rộng đường đến mạng nhạy cảm

Ví dụ một chi nhánh mới chỉ được phép truy cập **Report API** trong cloud. Nhưng gateway on-prem công bố **10.0.0.0/8**, còn transit hub import vào tất cả route domains. Kết quả một số spokes cloud có thể **chọn đường tới mạng quản trị on-prem** hoặc đi sai next hop. Đây có thể là lỗ hổng reachability, lỗi availability hoặc cả hai, tùy firewall và ứng dụng.

Kiểm soát:

1. **Chỉ import/export prefixes được phê duyệt** theo domain.
2. Giới hạn số lượng prefix/route khi tính năng hỗ trợ.
3. Không propagate default route vào mọi VPC mà không có quyết định kiến trúc.
4. Tách spoke prod/dev, partner/on-prem trust zones bằng route tables và policies.
5. Thử **effective routes** từ workload đại diện, không chỉ danh sách advertisements.
6. Giữ logging thay đổi BGP sessions, learned routes, propagation và liveness.

### 8.4. Dynamic failover và đường “dự phòng” ít được kiểm tra

Hai đường hybrid có thể được cấu hình:

~~~text
Primary:   Cloud -> Private circuit -> Data center
Secondary: Cloud -> IPsec VPN -------> Data center
~~~

Vào ngày thường traffic đi primary, firewall và DNS hoạt động đúng. Khi primary fail, traffic chuyển sang VPN backup, nhưng có thể:

- Route backup bỏ qua một firewall/inspection point.
- MTU nhỏ hơn làm gRPC/large HTTPS responses lỗi.
- NAT đổi IP nguồn, phá allowlist hoặc audit mapping.
- VPN cipher/identity policy không tương đương baseline.
- On-prem DNS resolver reachable qua route khác so với application flows.
- BGP learned prefixes khác, mở thêm mạng ngoài ý định.

**Không coi backup path an toàn nếu chưa test trong phạm vi được phê duyệt.** Cần kiểm tra cả **tính sẵn sàng và tính tương đương chính sách** trên đường failover.

### 8.5. IPsec VPN không thay identity/authorization

VPN tunnel có thể mã hóa lưu lượng giữa gateways, nhưng một workload qua tunnel vẫn có thể không đáng tin. Những điểm cần bảo vệ:

- VPN peer identity, certificates/pre-shared keys và key rotation.
- Phase/negotiation policies và crypto algorithms được phép.
- Source/destination subnet selectors hoặc route-based network policy.
- Firewall/ACL khi traffic thoát tunnel.
- Logging, liveness, HA và route convergence.
- **mTLS/API authorization** cho dữ liệu nhạy cảm sau tunnel.

Không cấp toàn bộ **on-prem 172.16.0.0/12** quyền tới cloud production chỉ vì gateway VPN được tổ chức sở hữu.

### 8.6. Kết nối đối tác/nhà thầu khác với kết nối nội bộ

Đối tác có thể xin private connectivity để truy cập API doanh nghiệp. Tư duy **network-to-network peering toàn CIDR** có thể quá rộng cho yêu cầu một vài endpoints.

Ưu tiên khi phù hợp:

- Private service endpoint hoặc API gateway chỉ expose service cần thiết.
- Mạng đối tác **không học route** tới management/database prefixes.
- TLS/mTLS, client identity và token scopes tách theo đối tác.
- Egress/inbound firewall rules có ticket, thời hạn và owner.
- Theo dõi **thay đổi subnet/CIDR/peer ownership** phía đối tác.
- Offboarding khi hợp đồng chấm dứt: thu hồi route, peering attachment, endpoint permissions, certificates, API tokens và DNS records.

### 8.7. NAT để xử lý CIDR overlap: giải pháp có giới hạn

Nếu công ty sáp nhập và hai mạng dùng cùng CIDR, đôi khi thiết kế **translation** qua firewall/NAT gateway hoặc service proxy để phân biệt nguồn/đích. Tuy nhiên:

- NAT không làm danh tính peer trở nên đáng tin.
- Dữ liệu flow chỉ thấy translated IP cần **mapping logs** để điều tra.
- DNS phải trả địa chỉ translated tương ứng, tránh hai host cùng IP.
- Ứng dụng sử dụng IP literals, TLS SAN hoặc callback có thể hoạt động sai.
- Debug và policy khi failover trở nên khó hơn; NAT state có thể bị mất.
- Không phải mọi traffic/protocol thích hợp với translation.

**Không giải quyết peering overlap bằng cách thêm một route ambiguous rồi hy vọng longest prefix match đúng.** Renumbering, private service access hoặc architecture mediation có thể là phương án dễ duy trì hơn tùy bối cảnh.

## 9. Rủi ro bảo mật khi phạm vi kết nối mạng mở rộng

### 9.1. Lateral movement qua peered networks

Một workload trong môi trường dev bị xâm nhập không tự nhận được quyền trong production. Nhưng nếu dev↔prod peering và firewall mở rộng, kẻ tấn công có thể **tiếp cận** nhiều ports/services chưa từng được Internet công bố:

~~~text
Dev workload compromised
   |
   | Route qua peering/transit
   v
Production private API / database / management endpoint
   |
   | Nếu thiếu auth/patch/segmentation
   v
Rủi ro truy cập trái phép hoặc lan rộng sự cố
~~~

**Peering tạo reachability, không tự tạo compromise.** Điều kiện để xâm phạm còn phụ thuộc credential, lỗ hổng service, authorization và host controls. Do đó, giảm reachability là **một lớp phòng vệ giảm phạm vi tấn công** ngay cả khi endpoint security bị lỗi.

### 9.2. Data exfiltration qua đường private

Một số hệ thống giám sát tập trung vào Internet egress, nhưng dữ liệu nhạy cảm có thể bị chuyển **từ VPC production qua peering vào VPC ít được kiểm soát**, rồi đi ra ngoài bằng NAT/Internet gateway khác.

Ví dụ:

~~~mermaid
flowchart LR
  PROD["Prod VPC\ncustomer database"] -->|"Route/SG quá rộng"| PEER["Dev/partner VPC"]
  PEER -->|"Egress path khác"| OUT["Internet / external endpoint"]
  FW["Central egress inspection"] -. "Không nằm trên route này" .-> PEER
~~~

Phòng vệ:

- Chỉ cho phép **API/data flows cụ thể** thay vì database direct access.
- Restrict egress từ prod tới peer và từ peer ra destinations phù hợp.
- Ghi flow/audit logs ở cả hai VPC; biết VPC nào đang giữ dữ liệu.
- Dùng IAM/database authorization, encryption và DLP/classification phù hợp.
- Review các **đường transit/return path/bypass** so với inspection architecture.

Một kết nối private không mặc định là “approved data sharing”. **Data classification và mục đích xử lý** vẫn quyết định có được truyền dữ liệu hay không.

### 9.3. Management-plane abuse

Nếu một IAM principal có quyền **create peering + accept attachment + modify route tables + update security groups**, nó có thể làm một hệ thống vốn cô lập trở nên reachable. Các lệnh có thể xuất phát từ cloud control plane, không phải từ một host trong VPC.

Kiểm soát:

1. **Least privilege IAM** cho peering, route tables, SG/NSG và DNS sharing.
2. Tách người **đề nghị** và **phê duyệt** cross-account peering khi quy trình phù hợp.
3. **Organization policy/guardrails** giới hạn peer accounts/projects/regions được phép.
4. Infrastructure as Code (IaC) với review và policy-as-code trước deploy.
5. Audit mọi Create/Accept/Delete peering, route add/replace, firewall rule change, DNS zone attachment.
6. Báo động khi cấu hình thay đổi **ngoài pipeline** hoặc ngoài change window.

**Cloud API audit log** phải được bảo vệ khỏi sửa/xóa và được tổng hợp vào vùng quản trị an ninh có quyền kiểm soát riêng.

### 9.4. Cross-tenant trust và acquired networks

Một dự án sandbox, một đơn vị mới sáp nhập hoặc đối tác có thể chứa các endpoint không được quản lý giống production. Việc kết nối có thể đưa các điểm yếu hiện hữu gần tài sản quan trọng:

| Nguồn được peering | Điểm cần hỏi | Kiểm soát |
| --- | --- | --- |
| Dev → Prod | Có tài nguyên prod nào dev thực sự cần? | API/endpoint hẹp, deny DB/admin, identity controls |
| Partner → Corp | Có thể thay CIDR hoặc owner? | Contract/owner, endpoint access, mTLS, expiry |
| Acquired company → Corp | IP overlap, IAM/EDR/patching baseline? | Quarantine zone, inspection, staged onboarding |
| Region DR → Primary | Failover có tạo đường bypass hay không? | Symmetric policies, DR exercises, audit |
| Shared services → Many spokes | Một service bị xâm nhập ảnh hưởng bao nhiêu? | Segmented route tables, per-service roles |
| Security tooling VPC → Production | Tool agent có quyền quản trị broad? | JIT access, RBAC, audit, no default full network trust |

### 9.5. Shadow peering và cấu hình không được kiểm kê

Một peering attachment có thể được tạo tạm cho một ticket rồi tồn tại nhiều năm. Dù không có traffic vào ngày kiểm toán, nó vẫn là **đường khả năng** khi route/security policy thay đổi sau này.

Giám sát:

- Tất cả attachments có **owner, purpose, ticket, review date và expires_when** nếu phù hợp.
- Các route tables nào **tham chiếu tới attachment**.
- Những rules SG/NSG/firewall nào **cho phép source/destination peer**.
- Private DNS zones/resolvers nào đã được share.
- Lịch sử traffic và lỗ hổng/identities liên quan.
- Peering dormant đã hết nhu cầu có được **gỡ theo quy trình** không?

**Không tự động xóa peering chỉ vì không thấy flow logs**: có thể log coverage thiếu, DR path ít dùng, hoặc kết nối là dự phòng. Xác minh owner/dependencies trước khi gỡ.

### 9.6. Rủi ro outage và blast radius

Không phải mọi lỗi peering là security breach; những sự cố lớn thường là availability:

- Chèn route 10.0.0.0/8 làm traffic tới nhiều spokes đi sai.
- Transitive assumption sai khiến dịch vụ phụ thuộc A→C không reachable.
- DNS forwarding loop hoặc private zone override gây lỗi diện rộng.
- BGP failover làm đường reply bất đối xứng.
- Security group reference / identity policy không hỗ trợ cross-account theo loại peering thực tế.
- Central firewall/router quá tải hoặc một attachment bị xóa.
- Shared network owner thay policy làm hàng trăm workloads mất kết nối.

**Blast radius** là phạm vi workloads/data/traffic có thể bị ảnh hưởng bởi một thay đổi hoặc compromise. Trong một full mesh peering, số cạnh kết nối và policy dependencies tăng nhanh; một hub có thể giảm số kết nối vận hành nhưng cũng trở thành **điểm tập trung phụ thuộc**. Thiết kế nào phù hợp phải cân bằng **isolation, availability, chi phí, ownership và khả năng quan sát**.

### 9.7. Insecure protocol qua private peering

Một quan niệm sai: “Đã đi qua peering/private backbone thì HTTP, database plaintext hoặc credentials không cần TLS”. Trong môi trường đa tenant, cross-account, hybrid hoặc khi host bị xâm nhập, không nên dựa duy nhất vào nhãn “private”.

Ưu tiên:

- TLS 1.2/1.3 theo baseline, mTLS khi cần service identity.
- Backend certificate/hostname verification đúng trên từng hop, kể cả proxy trung gian.
- Credentials/secret management không nhúng khóa vào URL hoặc log.
- IAM/API authorization và database roles theo least privilege.
- Phân biệt transport encryption giữa các chặng, không gọi TLS bridging là TLS end-to-end không có điểm giải mã.

**Private peering không tự chứng minh ai đang ở đầu kia socket**, và IP nguồn có thể chịu NAT/proxy thay đổi.

## 10. Zero Trust, workload identity và kiểm soát kết nối giữa dịch vụ

### 10.1. Phân biệt bốn lớp quyền

Khi một microservice ở VPC-B gọi API ở VPC-A, không nên gộp cả quá trình thành “đã peered nên trusted”. Có bốn lớp cần đánh giá:

| Lớp | Câu hỏi | Ví dụ biện pháp |
| --- | --- | --- |
| **Network reachability** | Có route và filter cho tới đúng IP/cổng không? | Route tables, SG/NSG, ACL, NetworkPolicy |
| **Transport peer authentication** | Bên kia TLS là đúng service/host/tenant được tin cậy không? | TLS certificate hostname validation, mTLS identities |
| **Principal authentication** | Workload/service account/user thực hiện request là ai? | IAM workloads, signed tokens, workload identity, OAuth/OIDC |
| **Authorization** | Principal đó được phép thao tác gì với tài nguyên này? | API scopes, RBAC/ABAC, database permissions |

**Peering chỉ tác động rõ đến lớp reachability**, không thay ba lớp còn lại. Khi VPC-A và VPC-B nằm dưới cùng tổ chức, việc chủ yếu dùng CIDR allowlist mà không phân biệt service identity có thể khiến một compromised workload ở peer truy cập các API không dành cho nó.

### 10.2. Service-to-service access đúng quyền

Ví dụ **Reporting→Orders read-only API**:

~~~text
Network:
  Source: reporting-service trong VPC-B
  Destination: orders-api endpoint trong VPC-A
  Protocol: TCP/443
  Deny: other destinations and management ports

TLS:
  Client verifies orders-api server certificate/SAN.
  Orders API verifies reporting-service workload identity via mTLS
  hoặc một cơ chế xác thực dịch vụ được duyệt.

Application:
  Authorized scope: orders:read-summary
  Forbidden scope: orders:modify, payments:write, user:admin

Audit:
  Log source identity, destination service, action, decision, time.
  Không lưu private key, access token, raw customer data vào flow logs.
~~~

Nếu gateway terminate TLS rồi tạo TLS mới tới Orders API, backend phải hiểu rằng **chứng chỉ TLS chặng sau thuộc gateway**, không mặc nhiên thuộc reporting-service. Việc truyền identity gốc cần cơ chế **được bảo vệ và xác minh**; không chỉ tin một HTTP header do client tự ghi.

### 10.3. Access theo service identity tốt hơn IP rộng

IP/CIDR allowlist có giá trị để giới hạn reachability, nhưng trong môi trường tự động scale, ephemeral instances và multi-account, IP không nhất thiết ổn định hoặc gắn với danh tính ứng dụng. Khi khả năng nền tảng cho phép, kết hợp:

- **Security group references/identity-based selectors** trong đúng phạm vi được hỗ trợ.
- Kubernetes NetworkPolicy theo namespace/pod labels và CNI policy phù hợp.
- Service mesh mTLS identity/SPIFFE-like service identity theo implementation.
- API gateway IAM/OIDC/token validation với audience/issuer/expiry.
- Cloud IAM/resource policies cho managed services.

**Không thay thế route/firewall bằng IAM đơn thuần:** một dịch vụ bị định cấu hình sai, một legacy TCP listener hoặc lỗi proxy có thể không thực thi authorization mong đợi. Defense in depth cần **network controls + service identity + API permissions**.

### 10.4. East–west inspection không phải lúc nào cũng ở hub

**East–west traffic** là lưu lượng giữa workloads/services trong hoặc giữa các mạng nội bộ. Một tổ chức có thể dùng centralized firewall ở hub để inspect traffic giữa spokes; nhưng nếu một cặp VPC có direct peering bên ngoài hub, hoặc các workloads cùng subnet nói chuyện trực tiếp, traffic có thể **không đi qua firewall hub**.

Do đó cần phân biệt:

- **Central network firewall** chỉ kiểm soát routes đi qua nó.
- **Distributed SG/NSG/firewall policies** có thể kiểm soát gần workload.
- **Service mesh/gateway** kiểm soát và quan sát các requests thực sự đi qua proxy của mesh.
- **Host EDR** có khả năng quan sát process/network ở máy được cài agent.
- **Application audit logs** ghi actions/users/tokens mà flow logs không biết.

**Một dashboard có Firewall Allow/Deny không đại diện 100% lưu lượng cloud** khi có bypass, vùng chưa onboard hoặc đường private endpoint khác. Phải đo coverage.

### 10.5. Zero Trust khi dùng private endpoints

Private endpoint có thể hạn chế exposure từ mạng rộng xuống một service, nhưng vẫn cần:

1. Kiểm tra **consumer principal và endpoint/service policy**.
2. Bật TLS và xác minh peer certificate/hostname theo design.
3. Chặn unapproved public routes/alternate endpoints nếu bắt buộc private-only.
4. Chỉ cho phép API actions cần thiết qua IAM/token.
5. Bảo đảm endpoint DNS không trỏ nhầm cross-tenant resource.
6. Ghi audit các tạo/xóa endpoints và thay quyền tiếp nhận.

**Private route** không tự làm dữ liệu nhạy cảm “an toàn để chia sẻ” với mọi consumer có thể kết nối.

### 10.6. Nguyên tắc phân đoạn theo trust tiers

Một mô hình thực hành:

| Trust tier | Ví dụ mạng | Kết nối nên cho phép | Mặc định |
| --- | --- | --- | --- |
| Tier 0 — Quản trị bảo mật | Key management, IAM connector, security tooling | Chỉ các admin/service identities được duyệt | Deny từ dev/partner/guest |
| Tier 1 — Production data | Databases, secrets và PII services | Service-to-service có authn/authz cụ thể | Deny direct database cross-peer |
| Tier 2 — Production apps | API/frontend/internal services | API endpoints theo use case | Deny management, DB trừ khi cần |
| Tier 3 — Development/test | Test workloads, CI agents | Artifacts/synthetic data, approved APIs | Deny prod network access |
| Tier 4 — Partner/acquired | External tenant hoặc mạng mới onboard | Private endpoint, gateway limited routes | Deny all other reachable prefixes |
| Tier 5 — Guest/IoT | Wi-Fi guest, IoT và test devices | Broker/Internet theo policy | Deny internal admin/data |

Tên tier chỉ là **khung phân loại minh họa**, không phải tiêu chuẩn bắt buộc. Tách route domains và identity policies theo trust tiers giúp giảm cơ hội trust expansion khi thêm một peering mới.

## 11. Mẫu kiến trúc và quyết định mở rộng kết nối

### 11.1. Direct peering cho ít mạng có use case rõ

~~~mermaid
flowchart LR
  A["VPC A — Orders Prod\n10.10.0.0/16"] <-->|"Peering A–B"| B["VPC B — Reporting\n10.20.0.0/16"]
  B -->|"HTTPS/mTLS only"| API["Orders read-only API"]
  A --> API
  API -. "No direct DB access" .-> DB[("Orders DB")]
~~~

Khi chỉ có một consumer và một service, direct peering có thể đơn giản nếu:

- CIDR không overlap, route support được xác nhận.
- SG/NSG giới hạn đúng source/destination/port, egress tương ứng.
- Consumer chỉ dùng API được xác thực, không direct DB.
- Không có đòi hỏi A→C transit qua VPC-B.
- Owner và rollback/monitoring được xác định từ đầu.

**Không nên tạo peering giữa dev và prod chỉ để thuận tiện SSH**, vì lâu dài có thể trở thành đường truy cập vượt trust tier.

### 11.2. Full mesh peering và chi phí vận hành

Trong mô hình **mọi cặp VPC kết nối trực tiếp**, số cặp tiềm năng là:

\[
\frac{n(n-1)}{2}
\]

Ví dụ, 5 mạng có tối đa 10 cặp trực tiếp; 20 mạng có tối đa 190 cặp. Không có nghĩa phải tạo tất cả, nhưng số đường cần quản trị có thể tăng nhanh khi muốn kết nối full mesh.

**Vấn đề không chỉ là số attachments:** mỗi cặp kéo theo route tables, SG/NSG rules, DNS forwarding, owner, certificate trust, log coverage, failover tests, chi phí truyền dữ liệu và những giả định quyền truy cập. Mesh có thể hợp lý cho quy mô nhỏ nhưng rất khó kiểm soát nếu tổ chức có hàng trăm workloads và nhiều tenants.

### 11.3. Hub-and-spoke với các routing domains

~~~mermaid
flowchart TB
  PROD["Spoke Production"] <--> H["Transit hub / route tables"]
  DEV["Spoke Development"] <--> H
  PARTNER["Spoke Partner"] <--> H
  SHARED["Shared Services"] <--> H
  H <--> FW["Firewall / Inspection\nnếu path bị bắt buộc qua đây"]
  H <--> ONP["On-prem VPN/private circuit"]
~~~

Một hub có thể đơn giản hóa kết nối và thêm điểm kiểm soát, nhưng cần:

- **Tách route tables/association/propagation** cho prod/dev/partner.
- Giữ **inspection symmetric routing** cho stateful firewall.
- Bảo vệ **hub control plane**, bởi một sai cấu hình có thể mở nhiều spokes.
- Cho phép **shared services** theo policy, không coi shared VPC là mạng tin cậy tuyệt đối.
- Kiểm tra failover hub/firewall với route, NAT, DNS và logging.
- Loại bỏ **direct spoke peering bypass** không được phê duyệt.

**Hub là công cụ kiến trúc, không tự thực thi isolation.** Nếu tất cả spokes được attach vào cùng route domain cho nhau và SG mở quá rộng, hub có thể trở thành **điểm khuếch đại lateral movement**.

### 11.4. Security VPC và inspection hub

Một kiểu thiết kế đặt **virtual firewall appliances, central egress NAT, DNS security resolver và logging** tại một VPC chung. Traffic từ các spokes được route qua hub khi chính sách yêu cầu.

Điều kiện để có hiệu quả:

1. Route tables ở **spoke và hub** ép traffic cần kiểm tra đi qua firewall.
2. Không có peering/transit route trực tiếp hoặc Internet egress tùy tiện bypass.
3. Firewall đủ khả năng throughput, session state và failover giữa zones.
4. Return path không bỏ qua firewall và NAT mapping nhất quán.
5. Proxy/WAF/TLS decryption policy được đánh giá riêng; firewall L3/L4 không luôn thấy HTTP plaintext.
6. Logs từ firewall, DNS, VPC flow và cloud audit được tương quan với nhau.

**Không giả định mọi private endpoint đều đi qua central firewall.** Một số service-to-service paths hoặc private service endpoints có thể có routing đặc thù; hãy vẽ và test **effective data path** cho từng loại.

### 11.5. Dùng private service endpoint thay network peering rộng

Nếu team Analytics chỉ cần đọc **Orders summary API**, có hai lựa chọn:

| Lựa chọn | Tiếp xúc mạng | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| Peering Analytics↔Orders | Có khả năng route network prefixes theo policy | Linh hoạt cho nhiều dịch vụ | Reachability có thể rộng; cần SG/NSG và service auth chặt |
| Private service endpoint/attachment | Chỉ endpoint/service được publish theo capability | Giảm network surface, dễ tách tenant | Cần service endpoint support, DNS/endpoint policy |
| API gateway qua private link | Publish API theo route và auth policy | L7 validation, quotas, JWT/mTLS | Gateway trở thành trust boundary, chi phí/vận hành |

**Không khẳng định private endpoint luôn “an toàn nhất”** nếu endpoint policy quá rộng hoặc backend auth yếu; nó giúp thu hẹp phạm vi kết nối, nhưng không thay quyền nghiệp vụ.

### 11.6. Thiết kế đa vùng và disaster recovery

Các yêu cầu DR có thể tạo route từ primary tới standby và on-prem:

~~~text
Primary Region:
  Orders API + database active

DR Region:
  Orders standby + replicated data

Cloud WAN/Transit + region peering:
  Private API health and replication paths

Required controls:
  TLS/mTLS, DB replication identity, CIDR/IPAM, route and DNS failover
  Deny unapproved client traffic into standby databases
~~~

Rủi ro: replication ports mở quá rộng, standby environment thiếu patch/monitoring, DNS failover trỏ tới subnet không được bảo vệ, secret/cert rotation thiếu đồng bộ, default routes khác nhau. **DR phải được kiểm thử như một trust boundary đang tồn tại**, không chỉ như một sơ đồ bật lên khi có sự cố.

### 11.7. Multi-cloud network extension

Kết nối giữa AWS, Azure, GCP, private cloud hoặc data center thường không chỉ là **peering trực tiếp** theo cùng một API. Có thể cần VPN, dedicated circuits, managed routers hoặc WAN/interconnect services.

Những khác biệt cần xử lý:

- **CIDR/IPAM** và việc gán IPv6.
- **Control plane ownership** trên mỗi cloud account/subscription/project.
- **Route propagation/BGP** và firewall semantics khác nhau.
- **DNS private zone/resolver forwarding** xuyên nhà cung cấp.
- **Workload/service identity** không thống nhất theo một IAM chung.
- **Flow logs** có schema, retention và sampling khác nhau.
- **TLS trust roots và certificate rotation** trong mỗi cluster/service mesh.
- **Cost/latency/egress charges** và trách nhiệm vận hành khi lỗi.

Không gộp các mô hình này thành “cloud A peering cloud B” nếu thực tế traffic đi qua WAN/router/VPN và policies độc lập.

### 11.8. Mẫu phân tách route table ở hub

~~~yaml
# PSEUDO-YAML: mô tả route domains, không phải manifest dùng cho cloud vendor.
hub:
  name: security-transit-hub
  route_domains:
    production:
      attachments: [orders-prod, payments-prod]
      allowed_imports: [shared-auth-api, central-dns]
      denied_imports: [dev, partner, guest]
    development:
      attachments: [development]
      allowed_imports: [shared-artifact-mirror, central-dns]
      denied_imports: [production-data, production-management]
    partner:
      attachments: [partner-a]
      allowed_imports: [partner-facing-api]
      denied_imports: [production-subnets, shared-admin, development]
  inspection:
    route_sensitive_flows_via_firewall: true
    require_symmetric_return_path: true
  governance:
    config_review_required: true
    log_effective_routes: true
    deny_unapproved_attachment: true
~~~

Các trường **allowed_imports/denied_imports** ở đây chỉ thể hiện **ý định chính sách**. Nền tảng triển khai thật có thể không có một biểu thức deny tương ứng: người vận hành phải chứng minh bằng **effective route tables, firewall policies và negative connectivity tests**.

## 12. Observability: biết mạng nào thật sự được kết nối

### 12.1. Nguồn dữ liệu và khả năng chứng minh

| Nguồn | Thông tin quan sát | Không thể tự chứng minh |
| --- | --- | --- |
| Cloud network inventory | VPC/VNet, subnet, CIDR, peering, transit attachments, owner | Từng ứng dụng có thể kết nối thành công |
| Effective route tables | Destination prefix, next hop, route source/propagation | Firewall/identity cho phép hoặc API authorization |
| VPC/VNet flow logs | IP/port/protocol, bytes, action/status tùy nền tảng | HTTP body, user identity hoặc dữ liệu đã bị lấy |
| Firewall/IDS/IPS logs | Allow/deny, session, signature, network path | Mọi traffic nếu có bypass/coverage gaps |
| Cloud control-plane audit logs | Tạo/sửa peering, route, SG/NSG, DNS, IAM | Một route mới đã được ứng dụng sử dụng |
| DNS resolver logs | Query name, response IP/time theo capability | Client thực sự truy cập IP hoặc được ứng dụng cấp quyền |
| VPN/BGP gateway telemetry | Tunnel health, peer state, advertised/learned prefixes | Traffic qua mọi prefix không bị chặn ở endpoint |
| NAT/Proxy logs | Mappings nguồn–đích và thời gian | User cụ thể nếu thiếu workload/session identity |
| TLS/mTLS/API gateway logs | Xác thực peer, request ID, ứng dụng và decision | Network origin route nếu thiếu flow/correlation |
| IAM/resource policy audit | Quyền principal vào cloud API/data service | Workload chắc chắn đã dùng quyền đó |
| EDR/runtime monitoring | Process, network sessions và host behavior | Toàn bộ traffic của nơi không có agent |

**Cần đánh dấu giới hạn coverage** theo vùng, service type và thời gian. Một cảnh báo “không thấy traffic qua hub firewall” không chứng minh A↔B không trao đổi nếu còn direct peering hoặc private endpoints ngoài path giám sát.

### 12.2. Tương quan phải dựa trên event time và source

Ví dụ sự kiện chuỗi:

~~~text
10:00:00Z  IAM audit: principal X created peering A-B
10:00:04Z  Network audit: peer accepted
10:00:20Z  Route change: 10.20.0.0/16 via peering
10:00:30Z  SG changed: allow TCP/443 from 10.20.0.0/16
10:01:05Z  Flow log: 10.20.20.25 -> 10.10.10.10 TCP/443 allowed
10:01:08Z  API: principal reporting-service requested /summary, 200
~~~

Chỉ khi có nhiều nguồn đủ tin cậy mới có thể nói **peering được tạo, route và security policy thay đổi, flow đã xảy ra và API xử lý thành công**. Mỗi bước không tự kéo theo bước tiếp. Nếu audit log thiếu, đừng tự tạo timeline giả mà phải đánh dấu **unknown / missing evidence**.

### 12.3. Schema event gợi ý

~~~json
{
  "event_id": "cloud-net-lab-0007",
  "event_time": "2026-11-28T10:01:05Z",
  "source": "synthetic-flow-log",
  "environment": "lab",
  "network": {
    "source_vpc": "reporting-b",
    "destination_vpc": "orders-prod-a",
    "connectivity_type": "direct-peering",
    "attachment_id": "peer-lab-007",
    "route_policy_version": "routes-17"
  },
  "flow": {
    "src_ip": "10.20.20.25",
    "src_port": 51514,
    "dst_ip": "10.10.10.10",
    "dst_port": 443,
    "protocol": "tcp",
    "decision": "allow",
    "bytes": 12034
  },
  "validation": {
    "app_authn_observed": false,
    "app_authorization_observed": false,
    "identity_source": "network_flow_only"
  },
  "synthetic": true
}
~~~

Đây là schema **tự thiết kế để minh họa**, không phải cấu trúc flow log chính thức của AWS/Azure/GCP. **Flow log allowed** không có nghĩa ứng dụng đã trả HTTP 200 hoặc customer data đã được đọc; cần application logs với request IDs và identity được xác minh.

### 12.4. Những alert có giá trị

| Use case | Điều kiện quan sát | Hành động điều tra |
| --- | --- | --- |
| **Unexpected peering created** | Tạo/chấp nhận attachment ngoài IaC/change ticket | Kiểm tra principal, owner và phạm vi route |
| **Route table expanded** | Thêm prefix rộng hoặc 0.0.0.0/0/new default route | Diff effective routes, next hops, blast radius |
| **Prod–Dev path opened** | Route + SG/NSG có quyền nối hai trust tiers | Negative test và xác minh owner/exception |
| **Transit propagation anomaly** | Hub import nhiều prefixes/new attachment ngoài baseline | Kiểm tra import/export/association route domains |
| **Hybrid BGP leak** | Learned prefixes lạ, số prefixes tăng đột biến | Review BGP policy, gateway peer và route fallback |
| **Sensitive port reached** | Flow từ peer tới DB/admin ports | Kiểm tra có allow sai hoặc chỉ là denied attempt |
| **Egress via peer** | Prod bytes lớn đến network có egress Internet | Data owner review, firewall/NAT and app audit |
| **DNS namespace conflict** | Private host trả IP khác theo region/VPC | Resolver policy, shared zones, change timeline |
| **Direct path bypass inspection** | Flow A↔B không có record tại expected firewall | Verify logging gaps và actual path |
| **IPv6 policy mismatch** | IPv6 flow được phép ngoài IPv4 policy | Review AAAA, IPv6 routes/firewall |
| **Peering owner removed** | Không có owner/ticket, vẫn active | Inventory review, dependency confirmation |
| **Log/flow coverage lost** | Collector disabled, lag hoặc sampling thay | Cảnh báo visibility gap, không suy là traffic giảm |

**Giám sát chỉ mạnh khi route coverage và log correctness được kiểm chứng.** Đừng chỉ tăng số rule SIEM mà bỏ qua nguy cơ thiếu logs do một VPC chưa bật export.

### 12.5. Khối lượng flow và phân loại dữ liệu

Flow logs có thể có sampling/aggregation; một record có thể đại diện nhiều packets theo cách provider định nghĩa. Không dùng **số records** như số connection chính xác nếu chưa đọc semantics.

Quản lý dữ liệu:

- Giới hạn thông tin **IP/hostname/user/account IDs** theo retention và quyền truy cập.
- Không log plaintext secret/tokens hoặc raw customer payload vào hệ thống quan sát network.
- Bảo vệ quyền thay cấu hình **flow log export, bucket/KMS, SIEM indexing** khỏi các principal vận hành app thường.
- Với forensic, giữ **raw event references, source, timestamp, ingestion delay và evidence chain**.
- Tránh quy gán dữ liệu từ **một IP NAT** thành một user/host nếu thiếu translation/session mapping.

### 12.6. Đo năng lực phòng vệ

Metric hữu ích:

- **Số peering/transit attachments** có owner/ticket/review date.
- **Số đường prod↔dev/partner** có thể route trên graph network, không chỉ connections đang active.
- **Số thay đổi route/SG/NSG/DNS** ngoài IaC/approved windows.
- **Số sensitive-port allow flows** giữa trust tiers; tỷ lệ deny theo use case.
- **Số VPC/VNet có flow/audit/DNS logs đầy đủ** và collector heartbeat.
- **Thời gian phát hiện và xử lý route leak hoặc unauthorized attachment**.
- **Thời gian failover hybrid**, cùng latency/availability sau khi chuyển path.
- **Số stale/expired peer permissions** đã được review và thu hồi đúng quy trình.

Đừng lấy **số lượng firewall denies** làm thước đo duy nhất: đôi khi deny tăng vì test hợp lệ, scanning nội bộ hoặc policy mới được áp; phải dựa trên **evidence về rủi ro, coverage và kết quả nghiệp vụ**.

## 13. Threat modeling với STRIDE, blast radius và trust graph

### 13.1. Tài sản cần bảo vệ

Trước khi tạo một attachment, hãy lập danh sách:

- **Data assets:** production database, customer data, backups, analytics warehouse, secrets.
- **Critical APIs:** identity provider, payments, administrative APIs, cloud metadata-related services.
- **Control-plane privileges:** IAM principals, route/peering/firewall update rights, DNS zone management.
- **Connectivity infrastructure:** VPN gateways, transit hubs, firewall appliances, NAT and DNS resolvers.
- **Workload identities:** service accounts, mTLS certificates, API tokens, private endpoint policies.
- **Observability:** flow/audit/DNS logs, SIEM, IDS/IPS, EDR và policy-as-code pipeline.
- **Availability dependencies:** shared DNS, route tables, hubs, firewall HA, VPN/private circuits.

**Tài sản và quyền quan trọng hơn số lượng CIDR**: một peering nhỏ tới service giữ secret production có thể rủi ro hơn một mạng lớn chỉ chứa dữ liệu synthetic.

### 13.2. Threat scenario matrix

| ID | Tình huống rủi ro | Điều kiện cần | Ảnh hưởng có thể xảy ra | Kiểm soát/kiểm thử |
| --- | --- | --- | --- | --- |
| CNP-01 | Dev workload di chuyển ngang sang Prod | Route và firewall quá rộng, dịch vụ/identity yếu | Truy cập trái quyền hoặc ransomware lan rộng | Prod–Dev deny matrix, network policy và API auth |
| CNP-02 | Data egress qua VPC peer | Prod cho chuyển dữ liệu sang mạng ít giám sát | Exfiltration ngoài đường Internet egress được kiểm tra | DLP, egress control, peer flow/NAT logs, service auth |
| CNP-03 | Peering được tạo ngoài quy trình | IAM cho phép create/accept peering trái quyền | Mở mạng mới không được review | Org guardrails, approvals, cloud audit alert |
| CNP-04 | Route propagation leak | Transit hub import/export prefix quá rộng | Dev/partner nhìn thấy prefix production/admin | Route table isolation, route policy tests |
| CNP-05 | CIDR overlap với acquired network | Hai site dùng cùng private address | Kết nối nhầm đích/blackhole, NAT phức tạp | IPAM, renumbering hoặc mediated service access |
| CNP-06 | Default route đổi qua peer | Route 0.0.0.0/0 sai hoặc transit ngoài ý định | Bypass egress inspection hoặc mất mạng | Effective-route review, staged rollout |
| CNP-07 | Stateful firewall bị bypass do asymmetric routing | Request/response đi đường khác nhau | Timeouts, session loss, inspection gap | Symmetric path tests, firewall session telemetry |
| CNP-08 | DNS private zone chia sẻ nhầm | Resolver/zone attachment sai | Service confusion, cross-tenant request | Private DNS owner, SAN/mTLS validation, negative DNS tests |
| CNP-09 | IPv6 mở hơn IPv4 | Dual-stack route/ACL thiếu đối xứng mục tiêu | Bypass chính sách chỉ kiểm IPv4 | IPv4/IPv6 access tests, AAAA record audit |
| CNP-10 | On-prem VPN/tunnel keys bị lộ | Credentials/gateway IAM yếu | Truy cập đường hybrid trái quyền | Key rotation, peer authentication, firewall |
| CNP-11 | Dedicated circuit bị coi là encryption | Không có TLS/IPsec theo yêu cầu | Data có thể bị lộ trên đường không đạt baseline | TLS/mTLS/IPsec theo threat model |
| CNP-12 | BGP quảng bá prefix quá rộng | Không có prefix filtering/import limits | Route hijack/leak nội bộ, outage | Explicit allowlists, max prefixes, alert |
| CNP-13 | Private endpoint nhầm service/tenant | Endpoint policy/service identity sai | Dữ liệu gửi sang resource không mong đợi | Endpoint acceptance, DNS, TLS/authn/authz |
| CNP-14 | Shared hub bị xâm phạm | Hub IAM/firewall policy quá rộng | Nhiều VPC và account bị tác động | Segmented route domains, RBAC, HA, audit |
| CNP-15 | Logging không nhìn thấy direct peering path | Chỉ đặt sensor tại central hub | Không phát hiện hoạt động east–west | Per-VPC flow logs, traffic path validation |
| CNP-16 | Shadow peering tồn tại sau dự án | Thiếu owner/review/offboarding | Tích lũy đường truy cập không cần thiết | Inventory expiry/review và dependency-based removal |
| CNP-17 | SG mở database cổng quản trị | “Tạm mở /16 all ports” rồi quên | Truy cập DB/admin ngoài use case | Port/identity allowlists, policy-as-code |
| CNP-18 | Cloud API principal sửa route/DNS | Quá nhiều quyền control plane | Re-route traffic, thay đích, gián đoạn dịch vụ | Least privilege, separation of duties, audit |
| CNP-19 | Hybrid failover đi đường không inspect | Backup VPN khác policy primary | Bypass hoặc outage sau DR | Failover game day, parity tests |
| CNP-20 | Route/attachment xóa nhầm | Không quản lý dependencies | Outage cross-account/region | Change review, dependency graph, rollback |

Đây là **rủi ro tiềm năng**, không phải bằng chứng một tài khoản cloud đã bị compromise. Việc phát hiện một route mở rộng phải được tương quan với firewall, identity và traffic mới kết luận mức ảnh hưởng.

### 13.3. STRIDE qua trust boundaries

| Nhóm STRIDE | Ví dụ trong peering | Kiểm soát chính |
| --- | --- | --- |
| **Spoofing** | Tin IP nguồn peer như danh tính người dùng, mTLS peer identity sai | Workload identity, TLS SAN verification, IAM |
| **Tampering** | Route table/SG/NSG/DNS bị sửa trái phép | IAM, approvals, IaC drift detection, audit |
| **Repudiation** | Không biết ai tạo peering, ai mở TCP/5432 | Control-plane logs, versioned change records |
| **Information Disclosure** | Dữ liệu prod qua peer tới môi trường không được kiểm soát | Egress, DLP, mTLS, data classification |
| **Denial of Service** | Hub/firewall/VPN quá tải hoặc route blackhole | HA, capacity, fallback, route tests |
| **Elevation of Privilege** | Dev network vào admin endpoint, trust based on CIDR | Segmentation, per-request authorization, JIT admin |

### 13.4. Attack tree mức phòng vệ

~~~mermaid
flowchart TD
    ROOT["Mục tiêu rủi ro: mở rộng truy cập trái ý định\nqua cloud network peering"] --> PATH{"Đường phát sinh"}
    PATH --> CTRL["Control-plane change"]
    PATH --> NET["Network route/firewall"]
    PATH --> NAME["DNS / service identity"]
    PATH --> DATA["Data movement/egress"]
    CTRL --> CT["IAM, approvals, audit,\npolicy-as-code"]
    NET --> NT["Route isolation, CIDR/IPAM,\nSG/NSG, effective path tests"]
    NAME --> DT["Private zone ownership,\nTLS/mTLS and authorization"]
    DATA --> ET["Egress restrictions,\nflow/DLP/application logs"]
    CT --> RESP["SOC/NOC detection,\ncontainment và verification"]
    NT --> RESP
    DT --> RESP
    ET --> RESP
~~~

Sơ đồ không hướng dẫn tấn công; nó chỉ xác định nơi cần đặt controls và bằng chứng kiểm chứng. **Một route có tồn tại không đủ để khẳng định attacker đang khai thác**, nhưng có thể tăng blast radius và cần được xử lý theo mức nhạy cảm tài sản.

### 13.5. Mô hình graph cho network exposure

Hãy mô hình hóa:

- **Node:** VPC/VNet, subnet, transit route domain, VPN gateway, private endpoint, workload/service.
- **Edge:** peering attachment, route, policy-allowed flow, identity-authorized API, DNS resolution.
- **Node attributes:** owner, environment, data classification, trust tier, IP prefixes, logging coverage.
- **Edge attributes:** source/destination, protocol/port, route next hop, SG/NSG/firewall, approval/expiry.

Quan trọng: **peering edge khác allowed-flow edge**. Hai VPC có attachment nhưng không có route hoặc bị firewall deny có thể chưa có workload reachability. Ngược lại, một service API qua private endpoint có thể reachable mà không có full peering.

### 13.6. Chấm mức rủi ro theo evidence

Một cách ưu tiên:

| Phát hiện | Network evidence | Tác động đã xác minh | Ưu tiên gợi ý |
| --- | --- | --- | --- |
| Peering mới nhưng chưa có route | Attachment change | Chưa có proof of reachability | Review governance |
| Dev route tới Prod management | Route + SG/NSG allow | Khả năng truy cập quản trị | Cao |
| Flow Dev→Prod DB bị deny | Flow deny từ peer | Không chứng minh compromise | Điều tra nguồn, giữ deny |
| API Prod→Partner bytes tăng mạnh | Flow/network telemetry | Khả năng data transfer, chưa chứng minh dữ liệu nào | Theo dữ liệu và ngữ cảnh |
| Route propagation làm 0.0.0.0/0 đổi next hop | Effective route diff | Outage/bypass có thể xảy ra | Cao nếu ảnh hưởng nhiều workloads |
| DNS zone mới attach vào production | Control-plane log | Khả năng đổi name resolution | Điều tra identity/service impact |
| Flow logs missing after gateway change | Health/collector | Không còn visibility | Ưu tiên khôi phục monitoring |

Đừng dùng một **“risk score” không giải thích được** thay cho evidence: ghi rõ route nào, source/đích nào, SG nào, thời điểm nào, chủ sở hữu nào và còn thiếu bằng chứng gì.

## 14. Triển khai peering có kiểm soát: từ phê duyệt đến rollback

### 14.1. W1 — Xác định use case và trust boundaries

Trước khi tạo một peering hoặc transit attachment:

1. Ghi **mục đích nghiệp vụ**: service cụ thể nào cần gọi gì?
2. Chỉ rõ **requester/owner** của hai VPC/VNet, tài khoản/project/subscription/region.
3. Kiểm kê **CIDR IPv4/IPv6**, subnet, route tables, DNS zones và các đường hiện hữu.
4. Xác định **dữ liệu nhạy cảm và network tiers** mà kết nối có thể tiếp cận.
5. Chọn **peering, private endpoint, transit hub hay VPN** theo nhu cầu và giới hạn sản phẩm.
6. Định nghĩa **allow/deny matrix** cho đúng nguồn, đích, protocol, port và workload identity.
7. Định nghĩa **path log/metric** và ai giám sát sau rollout.
8. Chuẩn bị rollback và danh sách dependencies bị ảnh hưởng.

Nếu chưa có owner hoặc mục đích kết nối chưa rõ, không mở peering toàn CIDR rồi “đoán sau”.

### 14.2. W2 — Review cấu hình bằng IaC và policy-as-code

Lưu ý định tuyến và security policy trong hạ tầng được quản lý có version/approval. Một định nghĩa mô phỏng:

~~~yaml
# PSEUDO-POLICY: không phải file cho AWS/Azure/GCP.
connection_request:
  id: PEER-ORDERS-REPORTING-2026
  requester: orders-platform
  peer_owner: reporting-platform
  source_network: reporting-b
  destination_network: orders-prod-a
  source_cidr: 10.20.0.0/16
  destination_cidr: 10.10.0.0/16
  authorized_flow:
    source_workload: reporting-service
    destination_service: orders-summary-api
    protocol: tcp
    port: 443
    transport_authentication: mTLS
    application_scope: orders:read-summary
  forbidden_flows:
    - reporting-to-orders-database
    - reporting-to-management
    - dev-to-prod-via-reporting
  routing:
    transit_allowed: false
    ipv6_reviewed: true
    dns_private_zone_scope: reviewed
  change_control:
    owner: network-security
    approval_required: true
    review_by: 2027-02-28
  logging:
    flow_logs_both_sides: true
    audit_route_changes: true
    sensitive_flows_alert: true
~~~

**transit_allowed: false** chỉ diễn đạt yêu cầu logic, không tự đảm bảo một transit hub hoặc gateway không thể forward. Cần enforce bằng **route tables, attachment associations, SG/NSG, firewall và kiểm thử**.

### 14.3. W3 — Pre-change snapshot và inventory

Trước khi thay:

- Xuất **effective route tables** của các subnet/workloads liên quan.
- Ghi lại peering/transit status và owner, account/region identifiers.
- Chụp **SG/NSG/firewall rules, DNS forwarding/private zone attachments**.
- Kiểm tra IPv6, Internet egress paths, NAT mappings và VPN/BGP status.
- Lưu **expected traffic flows** và tài sản đang dùng route hiện hữu.
- Đo baseline TCP/TLS latency, errors, ứng dụng, firewall/flow logs.

Snapshot là dữ liệu vận hành nhạy cảm; không công khai credentials, route inventories chứa IP riêng/tenant secrets hoặc kubeconfigs trong ticket không có kiểm soát.

### 14.4. W4 — Rollout có giới hạn

Một thứ tự gợi ý (phải điều chỉnh theo sản phẩm):

1. Đảm bảo **CIDR không overlap** hoặc có architecture xử lý được chấp thuận.
2. Tạo peering/attachment với **đúng peer và quyền phê duyệt**.
3. Cấu hình routes cho những subnets cần thiết theo khả năng.
4. Áp SG/NSG/firewall **deny-by-default với exceptions hẹp**.
5. Cấu hình DNS/private zone hoặc resolver forwarding trong phạm vi được duyệt.
6. Cấu hình mTLS, client identity, service authorization và secrets/certs nếu cần.
7. Bật flow/audit/DNS/TLS logs, xác nhận collector heartbeat.
8. Chạy **positive và negative tests** từ nguồn đúng, cả return path và IPv6 nếu áp dụng.
9. Xác nhận owner hai bên và ghi kết quả vào change ticket.
10. Theo dõi SLO/risk telemetry trước khi mở rộng nhiều mạng hơn.

**Không chỉ test kết nối bằng IP tới một host đã mở mọi cổng**: phải kiểm thử đúng service/port/identity và chứng minh những luồng bị cấm vẫn bị từ chối.

### 14.5. W5 — Acceptance criteria

| Điều kiện | PASS khi | FAIL / cần xử lý khi |
| --- | --- | --- |
| Attachment | Đúng peer, owner, region và trạng thái | Kết nối tới account/tenant không được duyệt |
| CIDR/IPAM | Không ambiguous/overlap ngoài architecture đã thiết kế | Overlap làm route/DNS nhầm |
| Routing | Effective routes đúng source/destination, return path | 0.0.0.0/0/production prefixes mở ngoài policy |
| Firewall | Chỉ allowed workload/port đi qua | Dev/partner tới DB/admin được allow |
| DNS | Private names trả đúng IP/service | Split zone sai hoặc queries rò sang resolver khác |
| TLS/mTLS | Peer cert/identity verified, API authorization đúng | Có kết nối nhưng bỏ verify/accept wrong principal |
| Hybrid | VPN/BGP/import/export prefixes theo policy | Route leak/gateway transit ngoài dự kiến |
| Logging | Hai đầu có telemetry và audit trail | Missing logs hay không có alert khi thay route |
| Resilience | Failover/drain đúng mà không bypass controls | Backup path có quyền khác primary |
| Ownership | Ticket và rollback rõ, re-review date | Shadow peering không ai phụ trách |

### 14.6. W6 — Rollback theo phạm vi và dependency

Khi phát hiện route leak hoặc policy nới quá rộng:

1. Xác định **attachment, route tables, security rules và workloads** bị ảnh hưởng.
2. Chọn hành động thu hẹp ít gián đoạn nhất: **revert route, remove unexpected propagation, thu hẹp SG/NSG, block service ports** theo phê duyệt.
3. Nếu buộc gỡ peering, kiểm tra **DR, DNS, service discovery và legitimate dependencies** trước khi hành động.
4. Đảm bảo **return path, NAT state và firewall sessions** sau thay đổi không gây lỗi rộng hơn.
5. Xác minh traffic bị cấm đã deny và traffic cần thiết vẫn chạy.
6. Thu thập logs và timeline, làm rõ nguồn thay đổi, khắc phục IAM/change process.

**Không mặc định xóa tất cả routes/attachments ngay khi có alert**, vì một peering có thể phục vụ business-critical API hoặc DR path. Phải cân bằng **containment và availability** dựa trên mức nghiêm trọng, quyền và kế hoạch ứng cứu.

### 14.7. W7 — Đánh giá định kỳ

Review định kỳ khi:

- Thêm account/project/subscription, region, CIDR hoặc IPv6 range.
- Một team chuyển từ dev sang prod hoặc đổi owner.
- Thêm partner/acquired business, on-prem site hoặc VPN/private circuit mới.
- Bật route propagation, default route hoặc inspection hub.
- Gắn private DNS zone/private endpoint mới.
- Thay cloud provider product/region hoặc service mesh/mTLS CA.
- Có incident, audit finding, thay đổi data classification hoặc regulatory requirement.

Mỗi thay đổi có thể làm “peering hiện tại” **an toàn hôm qua nhưng quá rộng hôm nay**. Giữ ownership và test regression xuyên suốt vòng đời.

## 15. Lab phòng vệ: phân tích peering, route và allow/deny bằng dữ liệu giả lập

Lab sau sử dụng **synthetic topology, route tables, firewall decisions và audit events** để kiểm tra tư duy, không cần có cloud account thật hoặc thay network configuration. Nếu người học có sandbox được cấp quyền, có thể áp một số bước kiểm tra **read-only** theo chính sách môi trường; tuyệt đối không thử truy cập mạng không thuộc quyền.

### 15.1. Topology của bài lab

~~~mermaid
flowchart TB
  R["VPC-B Reporting\n10.20.0.0/16"] <-->|"Direct peering P-AB"| O["VPC-A Orders Prod\n10.10.0.0/16"]
  O --> API["Orders API\n10.10.10.10:443"]
  O --> DB[("Orders DB\n10.10.30.20:5432")]
  R --> RS["Reporting Service\n10.20.20.25"]
  R --> RT["Reporting Tools\n10.20.40.10"]
  O -. "Không tự có transit" .-> H["Hub VPC-C / Shared Services\n10.30.0.0/16"]
  H <-->|"VPN / hybrid link"| ON["On-premises\n172.20.0.0/16"]
~~~

**Yêu cầu nghiệp vụ:** chỉ Reporting Service 10.20.20.25 được phép gọi Orders API trên TCP/443 bằng mTLS/API scope **orders:read-summary**. Nó không được truy cập Orders DB TCP/5432 hoặc mạng quản trị. Reporting Tools cũng không có quyền vào Orders API. Việc VPC-A có kết nối riêng tới hub/on-prem **không khiến VPC-B tự transit tới on-prem**.

### 15.2. Tập dữ liệu route giả lập

~~~text
# VPC-A — ứng dụng Orders production
route_table_A:
  10.10.0.0/16    -> local
  10.20.0.0/16    -> peering P-AB
  10.30.0.0/16    -> hub attachment P-AC
  0.0.0.0/0       -> controlled egress (nếu được thiết kế)

# VPC-B — Reporting
route_table_B:
  10.20.0.0/16    -> local
  10.10.0.0/16    -> peering P-AB
  0.0.0.0/0       -> approved egress

# VPC-C — Shared Services / Hub
route_table_C:
  10.30.0.0/16    -> local
  10.10.0.0/16    -> attachment P-AC
  172.20.0.0/16   -> VPN attachment

Important:
  Không có route B -> C hoặc B -> on-prem được cấp phép.
  Đây là mô hình dữ liệu, không phải cloud vendor route syntax.
~~~

### 15.3. Tập dữ liệu firewall/identity giả lập

~~~yaml
# PSEUDO-POLICY; không áp thẳng vào một cloud firewall.
policies:
  - id: ALLOW-REPORT-API
    source: 10.20.20.25/32
    destination: 10.10.10.10/32
    protocol: tcp
    destination_port: 443
    require_mtls_identity: reporting-service
    require_api_scope: orders:read-summary
    decision: allow
  - id: DENY-REPORT-DB
    source: 10.20.0.0/16
    destination: 10.10.30.0/24
    protocol: any
    decision: deny
  - id: DENY-REPORT-MGMT
    source: 10.20.0.0/16
    destination: 10.10.50.0/24
    protocol: any
    decision: deny
  - id: DENY-REPORT-TOOLS
    source: 10.20.40.0/24
    destination: 10.10.10.10/32
    protocol: tcp
    destination_port: 443
    decision: deny
  - id: DEFAULT-DENY-CROSS-PEER
    source: 10.20.0.0/16
    destination: 10.10.0.0/16
    decision: deny
~~~

**Lưu ý semantics:** trong policy minh họa, thứ tự hiệu lực và default deny được mô tả rõ để thảo luận, **không đại diện thứ tự evaluation của mọi SG/NSG/cloud firewall**. Một SG stateful thường không có cấu trúc explicit deny giống một rule engine tổng quát. Triển khai thật phải ánh xạ ý định sang product semantics và kiểm chứng bằng tests.

### 15.4. Chuỗi audit events mô phỏng

~~~json
[
  {
    "id": "E01",
    "event_time": "2026-11-28T09:00:00Z",
    "source": "cloud-audit",
    "action": "CreatePeering",
    "attachment": "P-AB",
    "requester": "network-admin-lab",
    "approved_change": "CHG-007"
  },
  {
    "id": "E02",
    "event_time": "2026-11-28T09:02:00Z",
    "source": "cloud-network",
    "action": "UpdateRoute",
    "network": "VPC-B",
    "destination": "10.10.0.0/16",
    "next_hop": "P-AB",
    "approved_change": "CHG-007"
  },
  {
    "id": "E03",
    "event_time": "2026-11-28T09:03:00Z",
    "source": "cloud-network",
    "action": "UpdateFirewall",
    "network": "VPC-A",
    "rule": "ALLOW-REPORT-API",
    "approved_change": "CHG-007"
  },
  {
    "id": "E04",
    "event_time": "2026-11-28T09:04:00Z",
    "source": "flow-log",
    "src_ip": "10.20.20.25",
    "dst_ip": "10.10.10.10",
    "dst_port": 443,
    "decision": "allow",
    "bytes": 7600
  },
  {
    "id": "E05",
    "event_time": "2026-11-28T09:04:01Z",
    "source": "app-audit",
    "principal": "reporting-service",
    "resource": "orders-summary",
    "action": "read-summary",
    "decision": "allow",
    "http_status": 200
  },
  {
    "id": "E06",
    "event_time": "2026-11-28T09:04:10Z",
    "source": "flow-log",
    "src_ip": "10.20.40.10",
    "dst_ip": "10.10.10.10",
    "dst_port": 443,
    "decision": "deny"
  },
  {
    "id": "E07",
    "event_time": "2026-11-28T09:05:00Z",
    "source": "flow-log",
    "src_ip": "10.20.20.25",
    "dst_ip": "10.10.30.20",
    "dst_port": 5432,
    "decision": "deny"
  },
  {
    "id": "E08",
    "event_time": "2026-11-28T09:10:00Z",
    "source": "cloud-network",
    "action": "UpdateRoute",
    "network": "VPC-B",
    "destination": "10.30.0.0/16",
    "next_hop": "P-AB",
    "approved_change": null
  },
  {
    "id": "E09",
    "event_time": "2026-11-28T09:10:10Z",
    "source": "siem",
    "action": "RouteDriftAlert",
    "route": "VPC-B 10.30.0.0/16 via P-AB",
    "evidence": "E08"
  },
  {
    "id": "E10",
    "event_time": "2026-11-28T09:11:00Z",
    "source": "dns-log",
    "client_network": "VPC-B",
    "query": "shared.internal.example.test",
    "response": "10.30.10.10"
  },
  {
    "id": "E11",
    "event_time": "2026-11-28T09:12:00Z",
    "source": "flow-log-exporter",
    "network": "VPC-B",
    "event": "missing-heartbeat"
  }
]
~~~

**Những điểm quan trọng:**

- E01–E03 chứng minh control-plane setup được ghi nhận, **chưa chứng minh application đã gọi**.
- E04 chỉ chứng minh flow được cho phép theo nguồn log; E05 mới thêm bằng chứng application principal/action.
- E06/E07 là **deny** ở network layer, không phải compromise.
- E08 là **unauthorized route drift**, nhưng **A-B direct peering không tự chuyển transit từ B tới C**. Route 10.30.0.0/16 qua P-AB có thể là một route không sử dụng được hoặc bị service cấm; **không kết luận B đã vào C** nếu thiếu effective path và flow.
- E10 chứng minh DNS trả IP, **không chứng minh client có thể đi đến IP đó**.
- E11 báo **mất visibility**; sau thời điểm này không thể khẳng định “VPC-B không có traffic khác” chỉ từ flow logs.

### 15.5. Phân tích expected decisions

| Case | Nguồn → đích | Kết quả kỳ vọng | Vì sao |
| --- | --- | --- | --- |
| C01 | Reporting Service → Orders API TCP/443 | **Allow** khi mTLS/API scope đúng | Đúng use case |
| C02 | Reporting Service → Orders API nhưng không có mTLS identity | **Deny tại TLS/app** | Route/SG allow không đủ |
| C03 | Reporting Service → Orders API nhưng scope sai | **Deny authorization** | Workload đúng nhưng action không được cấp |
| C04 | Reporting Tools → Orders API TCP/443 | **Deny** | Source ngoài workload được duyệt |
| C05 | Reporting Service → Orders DB TCP/5432 | **Deny** | Không direct database |
| C06 | Reporting Service → Prod management TCP/22 | **Deny** | Không được quản trị prod |
| C07 | Reporting → Shared VPC-C qua VPC-A | **Không tự được route** | Non-transitivity direct peering |
| C08 | Reporting → On-prem qua VPC-A | **Không tự được route** | Không có transit được cấp phép |
| C09 | Dev→Prod qua hub route không có policy | **Deny** | Trust tier isolation |
| C10 | Peer source → IPv6 sensitive endpoint | **Deny nếu ngoài quyền** | Không bỏ qua IPv6 |
| C11 | Client peer tới private endpoint không được cấp policy | **Deny** | Endpoint/service permissions |
| C12 | Reporting API → permitted destination nhưng DNS trỏ sai | **Fail hoặc alert**, không truy nhầm service | DNS/SAN/route mismatch |
| C13 | BGP announce 0.0.0.0/0 từ partner | **Reject/import deny** theo policy | Không cho default route leak |
| C14 | Route drift không có change ticket | **Alert** và review | Control-plane integrity |
| C15 | Flow exporter heartbeat mất | **Health alert** | Không có telemetry không phải không có traffic |
| C16 | Peering bị remove nhưng ứng dụng vẫn có đường public thay thế | **Không tự nhận là đóng exposure** | Cần kiểm tra alternate routes |
| C17 | Partner subnet thay CIDR, SG vẫn allow dải cũ | **Review/quarantine**, không tự mở toàn CIDR | Ownership/renumbering |
| C18 | Primary hybrid VPN down, traffic chuyển backup | **Allow only approved flows** và SLO đạt | Policy parity khi failover |
| C19 | API Logs HTTP 403 sau TLS/mTLS thành công | **Deny ứng dụng là bình thường** | Network success khác app authorization |
| C20 | Direct DB IP reachable qua peer nhưng authn sai | **Network policy nên chặn từ trước**, DB auth vẫn deny | Defense in depth |

**Không được tự thử C07/C08 bằng cách cấu hình router B thành transit trái chính sách**. Ở lab lý thuyết, phân tích effective route và capabilities đã đủ để chứng minh giả định “A↔B↔C tự cho A↔C” là sai.

### 15.6. Những lệnh kiểm tra read-only trong sandbox được cấp quyền

Nếu có một VM Linux trong mạng lab đã được phép kiểm tra, có thể xem:

~~~bash
# Xem interface, IP và route của chính máy lab.
ip -brief address
ip route
ip -6 route

# Kiểm tra route chọn cho một địa chỉ lab cụ thể.
ip route get 10.10.10.10

# Kiểm tra DNS của hostname thuộc lab.
getent ahosts orders.internal.example.test

# Nếu công cụ và policy lab cho phép:
# curl thực hiện TLS/HTTP request tới chính endpoint sandbox của bạn.
curl --verbose --max-time 10 \
  https://orders.internal.example.test/health
~~~

Các lệnh này **không thay thế cloud effective route tables** vì route trên guest VM chỉ thấy một phần quyết định trong cloud virtual network. Khi chưa được cấp hostname/IP lab thực, không nên chạy lệnh kết nối; DNS ví dụ có thể không tồn tại. Với Windows có thể dùng các công cụ quản trị mạng tương đương như **Get-NetRoute, Resolve-DnsName, Test-NetConnection** trong quyền lab.

**Không dùng tùy chọn bỏ kiểm tra certificate** để làm cho phép thử TLS “thành công”. Nếu lab dùng CA nội bộ, hãy cấu hình trust store theo đúng CA được cấp quyền.

### 15.7. Phân biệt các loại lỗi từ lab

| Triệu chứng | Câu hỏi kiểm tra | Không nên kết luận |
| --- | --- | --- |
| DNS NXDOMAIN | Zone/resolver/link association có đúng không? | Peering tự hỏng |
| DNS trả đúng 10.10.10.10, TCP timeout | Route, firewall, return path, listener thế nào? | Auth token sai |
| TCP connect được nhưng TLS verify fail | CA, SAN/SNI/hostname có đúng không? | Network peering không tồn tại |
| TLS/mTLS đúng nhưng HTTP 403 | Principal/scope/authorization? | Phải nới SG/NSG |
| Một chiều flow allow, response timeout | Route reply, stateless filter, firewall state? | Chỉ cần tăng app timeout |
| BGP route import có 0.0.0.0/0 | Policy import/export và effective next hop? | Internet egress đã được bảo vệ |
| E08 báo route B→C qua A | Cloud peering có hỗ trợ transit hay không? | Đã bypass vào C |
| Không có flow logs sau E11 | Collector/exporter heartbeat có phục hồi không? | Đã chặn hết traffic |

### 15.8. Bài thực hành cần nộp

Người học viết tài liệu khoảng 1–2 trang:

1. Xác định **peering attachment**, source/destination CIDR và route tables.
2. Liệt kê **đúng 3 allowed/forbidden flows quan trọng nhất** và controls.
3. Phân tích E01–E11 theo **control-plane event, flow evidence, application evidence và telemetry health**.
4. Giải thích vì sao E08 không tự tạo transitive route.
5. Xây negative tests cho **DB, management, IPv6, private endpoint và on-prem**.
6. Đề xuất biện pháp khi E08 xuất hiện ngoài IaC mà **không làm Orders API gián đoạn**.
7. Chỉ rõ **lớp TLS/mTLS và application authorization** cho C01/C02/C03.
8. Nêu ít nhất **3 trường dữ liệu còn thiếu** trước khi có thể khẳng định data exfiltration.

**Đáp án định hướng:** peering có thể mở network reachability nhưng không tự biến identity/authorization hợp lệ; unauthorized route drift cần kiểm tra và rollback đúng scope; flow allow không chứng minh business action hoặc exfil; **mất logs làm giảm độ tin cậy kết luận**.

## 16. Troubleshooting peering và mở rộng kết nối cloud

### 16.1. Quy trình chẩn đoán theo lớp

~~~mermaid
flowchart TD
    A["Ứng dụng không kết nối được qua mạng cloud mở rộng"] --> B{"DNS trả đúng service IP?"}
    B -- "Không" --> BD["Private zones, resolver forwarding,\nrecord/TTL và split horizon"]
    B -- "Có" --> C{"CIDR overlap / effective route đúng?"}
    C -- "Không" --> CR["IPAM, longest-prefix match,\nattachment, route propagation"]
    C -- "Có" --> D{"Peering/hub/VPN gateway active\nvà có path được hỗ trợ?"}
    D -- "Không" --> DR["Attachment status, nontransitivity,\nBGP/VPN tunnel"]
    D -- "Có" --> E{"Network policy/return path đúng?"}
    E -- "Không" --> ER["SG/NSG/ACL, firewall, NAT,\nasymmetry, IPv4/IPv6"]
    E -- "Có" --> F{"TCP/UDP + TLS/mTLS hợp lệ?"}
    F -- "Không" --> FR["Port/listener, MTU, CA/SAN,\nSNI, workload identity"]
    F -- "Có" --> G{"Application authorized?"}
    G -- "Không" --> GR["User/service role, API scopes,\ndatabase permissions"]
    G -- "Có" --> H["Đo latency/SLO,\nlogs và test failover"]
~~~

**Không chạy ngay một lệnh thay route trên production** khi chỉ thấy timeout. Cần xác định lỗi thuộc **DNS, route, attachment, firewall, transport, TLS hay authorization** trước khi sửa tầng tương ứng.

### 16.2. Ma trận triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra có giá trị |
| --- | --- | --- |
| Peering báo connected nhưng TCP timeout | Thiếu effective route, return path, SG/NSG deny | Routes hai đầu, firewall/flow logs |
| Không tạo được peering | CIDR overlap, quyền/region/quota/peer request không phù hợp | CIDR/IPAM, control-plane error/audit |
| A↔B và B↔C chạy, A↔C timeout | Giả định transitivity sai | Direct peering vs transit architecture |
| Chỉ một subnet không kết nối | Subnet route table hoặc NSG/ACL khác | Effective routes và policy ở subnet đó |
| Connection lúc được lúc không | Multi-AZ route/policy khác, LB/backend health | Per-node/AZ flow, config diff |
| SSH/DB từ peer bị deny | Đây có thể là policy đúng | Xác nhận use case, không vội mở cổng |
| DNS trả public IP thay private | Private zone chưa liên kết hoặc split DNS/fallback | Resolver query nguồn cụ thể |
| DNS đúng nhưng TLS SAN mismatch | Hostname/CA/SNI sai hoặc service identity khác | TLS handshake validation |
| IPv4 deny nhưng IPv6 kết nối được | IPv6 route/ACL/AAAA chưa kiểm soát | IPv6 effective routes & policy |
| Ứng dụng large response treo | MTU/MSS, Path MTU Discovery qua VPN | Packet size, ICMP/PTB, TCP/QUIC stats |
| VPN tunnel up nhưng không truy cập | Routes/BGP import/filter, SG, DNS hoặc NAT | Tunnel routes, flow logs, identity |
| Failover hybrid gây outage | Asymmetric return route, BGP convergence, backup policy khác | Primary/secondary effective paths |
| Prod data bytes tăng sang peer | Data transfer hợp lệ/không hợp lệ, backup, batch | Application audit, flow, data owner, DLP |
| Hub firewall không ghi flow | Traffic bypass hub, log coverage gap, capture lỗi | Effective path và collector health |
| Một IP peer không xác định owner | NAT, ephemeral IP, shared service, dynamic workloads | NAT mappings, instance/ENI inventory, timestamps |
| SG rule đề cập peer SG nhưng không có hiệu lực | Cross-account/reference không được hỗ trợ theo topology | Product constraints, effective rules/tests |
| Gateway trả lỗi sau peering | TLS/mTLS, Host/authority, API authorization | Per-hop proxy/gateway logs |
| Costs tăng sau peering mới | Inter-region egress, transit/firewall data processing | Bill/flow by path, architecture review |
| Một peering bị xóa làm nhiều service lỗi | Hidden dependencies, DR backup use | Service inventory, logs, route dependency graph |

### 16.3. Khi ứng dụng báo 403/401

HTTP 401/403 có thể là kết quả **authorization hoạt động đúng**. Nếu service trả được HTTP response, thường network/TLS đã hoàn thành đủ để ứng dụng phản hồi. Không sửa peering route hoặc mở SG rộng hơn chỉ để đổi 403 thành 200.

Phân tích:

- Principal OAuth/IAM/mTLS có đúng không?
- Resource/tenant/API scope có được cấp không?
- Token/certificate còn hạn? Audience/issuer đúng?
- Gateway/mesh có truyền identity với nguồn tin cậy không?
- Backend policy có thể vừa thay ngoài network change không?

Nếu HTTP response thực chất từ **proxy/gateway chứ không phải backend**, phải xác định đúng nơi phát 403; một WAF rule có thể chặn trước ứng dụng.

### 16.4. Khi VPN/BGP có route nhưng TCP vẫn timeout

Một VPN tunnel có thể hoạt động và BGP có routes, nhưng firewall chặn đích. Ngược lại một route có thể được học nhưng chọn next hop khác vì policy/priorities.

Thứ tự:

1. Xem prefix được quảng bá/import và route effective từ workload nguồn.
2. Xem route trả lời và NAT mapping phía on-prem/cloud.
3. Kiểm tra firewall/SG/NSG, cả stateless và stateful semantics.
4. Kiểm tra MTU/MSS nếu lỗi phụ thuộc packet size.
5. Thử TLS server certificate/hostname và workload identity đúng.
6. Kiểm tra application listener và readiness.

Đừng dùng IPsec tunnel “UP” làm một kết luận rằng **mọi subnet selector/service đều reachable**.

### 16.5. Khi cùng service hoạt động ở một region nhưng lỗi region khác

Những điểm cần xem:

- CIDR/IPv6 route table khác nhau giữa AZ/regions.
- Transit attachment associations/propagation khác nhau.
- DNS private zone được attach ở region A nhưng không ở B.
- Firewall/SG/NSG hoặc network policy chưa deploy đồng bộ.
- mTLS trust store/CA và certificate SAN của service DR khác.
- Cloud egress/NAT source IP thay khi failover, bị deny bởi ứng dụng.
- Flow log exporter chỉ bật ở một vùng, tạo sai lệch quan sát.

Đối chiếu **effective config per-region** thay vì chỉ so hai file IaC được kỳ vọng giống nhau.

### 16.6. Khi nghi route leak hoặc unauthorized peering

Đây là sự kiện liên quan cả security và availability:

1. Xác nhận **control-plane audit event**, actor, action time, target attachment/route/SG.
2. Kiểm tra **effective reachability** đã thay đổi hay chỉ là config drift chưa áp.
3. Phân loại các tài sản bị phơi lộ: production DB/admin, identity, secrets, regulated data.
4. Đối chiếu flow/firewall/DNS/app logs đúng thời điểm để tìm access thực tế.
5. Chọn containment theo mức rủi ro: **revert route, block SG/NSG, remove unexpected propagation**, hoặc cô lập attachment có phê duyệt.
6. Kiểm tra liệu còn **alternate path** qua private endpoint, VPN, Internet egress hoặc direct peering.
7. Xác minh allowed flows vẫn hoạt động; lưu evidence và xử lý root cause IAM/IaC.

**Không coi một route đã được xóa là đủ chứng minh sự cố đã hết** nếu vẫn còn peering khác, NAT, private endpoint hoặc cached DNS dẫn traffic qua đường khác.

## 17. Tình huống vận hành thực tế

### Tình huống A — Dev peering Prod để thử API và vô tình mở rộng database exposure

Một nhóm development cần truy cập Orders read-only API trong production. Để tiện test, họ đề nghị peering giữa VPC Dev và VPC Prod, rồi mở security group database **TCP/5432 từ 10.20.0.0/16** vì “bị timeout”.

**Phân tích:** yêu cầu chỉ là API, không có lý do cấp database direct access. TCP timeout có thể do deny policy **đúng thiết kế**, không phải lỗi cần sửa. Giải pháp:

1. Xác minh service cần truy cập đúng URL/mTLS/API identity.
2. Cho phép **đúng nguồn dev workload được duyệt → API TCP/443** hoặc private service endpoint phù hợp.
3. Giữ deny Dev→Prod DB/admin; chạy negative tests.
4. Audit SG change và owner; thu hồi rule database rộng nếu đã tạo.
5. Khi phát triển xong, review/xóa quyền tạm có thời hạn.

**Bài học:** route tới toàn VPC không cấp quyền toàn subnet, và “private network” không miễn yêu cầu authorization.

### Tình huống B — Peering A–B và B–C nhưng Reporting không thấy Shared Services

Orders VPC-A có peering tới Reporting VPC-B. Reporting VPC-B có peering tới Shared VPC-C. Team A giả định app trong A có thể truy cập C bằng cách đi qua B; ứng dụng timeout.

**Phân tích:** **non-transitive peering** là nguyên nhân có khả năng. Muốn A↔C, thiết kế direct peering A–C hoặc kết nối qua transit gateway/hub forwarding được hỗ trợ theo chính sách. Không cố sửa bằng cách thêm rule allow all ở B nếu nền tảng không cho transit; chỉ mở firewall không tự tạo route hợp lệ.

### Tình huống C — Công ty mua lại một đơn vị có cùng CIDR 10.0.0.0/16

Hai mạng đều dùng 10.0.0.0/16, nhiều ứng dụng dùng IP literals. Đội kỹ thuật muốn tạo peering trực tiếp để tích hợp HR và ERP.

**Phân tích:** CIDR overlap khiến địa chỉ không phân biệt được theo đích từ cùng một routing domain, và nhiều peering products từ chối tình huống. Lựa chọn:

- **Renumbering** theo kế hoạch/IPAM.
- Expose các API hẹp qua **private service endpoint/gateway** thay vì toàn-network peering.
- Dùng NAT/translation riêng khi có use case và product hỗ trợ, với DNS/flow mapping được kiểm soát.
- Phân đoạn trust tier và kiểm tra account ownership trước khi nhập mạng.

**Không thêm route mơ hồ và giả định routing engine tự biết 10.0.0.10 là máy của công ty nào.**

### Tình huống D — Hub-and-spoke bị route propagation leak

Một transit hub nối Prod, Dev và một partner network. Sau thay đổi policy, bảng route của Dev học thêm prefix **10.10.30.0/24** thuộc database subnet production.

**Phân tích:** đây là sự mở rộng reachability cần review, dù database firewall vẫn có thể deny. Đội NOC/SOC cần:

1. Xác định attachment nào advertise/import prefix.
2. Kiểm tra route domain association và policy change.
3. Đối chiếu SG/NSG, database listeners và flow logs.
4. Thu hồi propagation sai scope và test Dev→DB deny.
5. Audit actor, pipeline và policy-as-code regression.

**Bài học:** không chỉ nhìn attachment count; **effective route graph** mới cho biết mạng nào có thể đi tới mạng nào.

### Tình huống E — DNS private zone của staging đè production name

Một private zone dùng chung hostname **orders.internal.example.test** được attach thêm vào Production VPC, vô tình làm resolver trả IP của staging. Một số clients báo TLS certificate error, số khác nhận dữ liệu synthetic.

**Phân tích:** sự cố thuộc **DNS namespace/control plane**, không phải cứ liên quan peering là peering hỏng. Cần kiểm tra zone associations, forwarding rules, authoritative records và TLS SAN/mTLS. **Không tắt TLS hostname verification** để làm cho client kết nối với staging. Sau sửa, test từ nhiều subnet/regions và tính tới TTL/cache.

### Tình huống F — Primary private circuit fail, backup VPN đưa traffic qua đường ít kiểm soát

Cloud data center traffic bình thường đi private circuit + central firewall. Khi primary down, BGP chuyển sang VPN backup nhưng một phần traffic được route thẳng tới production app, bỏ qua inspection.

**Phân tích:** kiến trúc DR chưa có **policy parity**. Cần so effective routes và firewall path cả hai chế độ, bảo đảm stateful return traffic; không chỉ test “VPN tunnel up”. Thực hiện game day trong khung được phê duyệt, giám sát route changes, MTU và session continuity. Nếu backup không thể đáp ứng controls bắt buộc, phải có quyết định an ninh/availability rõ thay vì mặc định mở mọi traffic.

### Tình huống G — Flow logs cho thấy nhiều bytes Prod→Partner VPC

Security team thấy Prod VPC gửi lượng lớn bytes sang Partner VPC lúc nửa đêm. Dữ liệu có thể là backup/ETL hợp lệ hoặc luồng exfiltration.

**Phân tích:** không đủ chứng cứ để kết luận dữ liệu nào bị lấy chỉ từ flow bytes. Cần:

- Đối chiếu batch schedule và business owner.
- Kiểm tra source workload/process, target service identity, TLS/API/database logs.
- Xem data classification và DLP/audit khả dụng.
- So với baseline theo site, thời điểm, protocol và port.
- Đánh giá network egress từ Partner VPC ra ngoài Internet.

Nếu phát hiện flow ngoài policy, có thể **thu hẹp route/SG hoặc service authorization** theo quy trình mà không làm gián đoạn các job hợp lệ không liên quan.

### Tình huống H — Một peer source IP đang truy cập quản trị nhưng owner không xác định

Flow log tại Prod thấy 10.20.40.55→10.10.50.10 TCP/22. VPC-B có nhiều containers/VM tự động scale, IP 10.20.40.55 vừa được tái sử dụng.

**Phân tích:** IP đơn lẻ không đủ gắn danh tính người hoặc workload trong mọi thời điểm. Cần network interface/instance allocation logs, Kubernetes pod/IP lifecycle, NAT/ENI mapping, clock sync và IAM/EDR data theo thời điểm. Xem **flow decision allow/deny** trước khi suy có SSH session thành công. **Giới hạn management access ngay từ policy** thay vì trông chờ luôn biết IP thuộc ai.

### Tình huống I — VPC flow logs im lặng sau migration nhưng app vẫn hoạt động

Một nhóm chuyển networking resource sang VPC mới; dashboard không còn report traffic giữa peer networks nên kết luận các kết nối cũ đã hết sử dụng và đề xuất xóa attachment.

**Phân tích:** log collector/exporter có thể chưa bật hoặc thiếu quyền với network mới. Cần kiểm tra health, effective routing, application requests và owner dependency. Không dùng **absence of logs** như bằng chứng chắc chắn không còn traffic; xóa peering có thể làm DR path hoặc API critical hỏng.

### Tình huống J — IPv6 tạo đường đi ngoài chính sách IPv4

Một ứng dụng dual-stack có AAAA record trỏ đến IPv6 endpoint. SG/NSG chỉ review IPv4 CIDR, khiến traffic IPv6 từ một peer có đường được phép ngoài dự kiến.

**Phân tích:** review IPv6 peering/routing, firewall, DNS AAAA, EDR/app logs và exposure. Chạy negative tests với IPv6 từ nguồn không được cấp quyền; đồng bộ **mục tiêu an ninh** giữa IPv4 và IPv6, không chỉ copy rules máy móc.

### Tình huống K — Peering tồn tại hai năm sau khi nhà thầu rời dự án

Nhà thầu từng được cấp peering và DNS forwarding tới một VPC integration. Dự án đã kết thúc, nhưng attachment, SG allowlist và API tokens vẫn tồn tại.

**Phân tích:** đây là **lỗi lifecycle/offboarding**. Điều tra owner, dependencies, logs, credential validity và đường khác có thể dùng; sau đó:

1. Thu hồi token/cert/service principal được cấp cho nhà thầu.
2. Xóa/thu hẹp route/SG/NSG/endpoint permissions theo change control.
3. Gỡ peering, DNS forwarding và private zone associations không còn cần.
4. Chạy regression/deny tests và xác minh không ảnh hưởng dịch vụ khác.
5. Bổ sung expiry/review và automated drift alerts.

### Tình huống L — Peering tốt nhưng HTTPS tới backend 502

Một API gateway ở VPC-A gọi service trong VPC-B qua peering. L4 connection và route đều hoạt động, nhưng proxy trả HTTP 502 sau khi backend certificate đổi CA.

**Phân tích:** lỗi có thể nằm ở **TLS backend verification**, không phải peering. Kiểm tra CA/trust store, SAN/SNI và TLS B, cập nhật chứng chỉ đúng. **Không nới peering/firewall hoặc tắt TLS verify** để sửa lỗi thuộc PKI.

### Tình huống M — Một CIDR rộng được quảng bá làm thay route egress

Data center router đưa vào BGP prefix 10.0.0.0/8 hoặc 0.0.0.0/0 mà cloud transit không có filter phù hợp. Một số service có đường đi khác trước; IDS/IPS tại expected hub không còn logs, SLA giảm.

**Phân tích:** cần tìm **effective longest-prefix/route priority**, BGP import/export rules, route-table association và next hop thực. Thực hiện rollback advertisement/import theo phạm vi được duyệt, test cả request/response, IPv6 và policy inspection. Không suy outage chỉ do firewall vì có route drift.

### Tình huống N — Private endpoint ngăn peering rộng nhưng cấp quyền dịch vụ quá mức

Đội Analytics thay full VPC peering bằng private endpoint tới object storage, nhưng endpoint/resource policy lại cho Analytics service account quyền đọc mọi bucket của production.

**Phân tích:** network surface đã thu hẹp nhưng **resource permissions vẫn quá rộng**. Cần sửa IAM/resource policy, scope bucket/object/prefix và data classification. Đây là ví dụ **private networking không thay authorization**.

## 18. Checklist kiểm tra peering và network extension

### 18.1. Governance và quy hoạch

- [ ] Mỗi peering/transit/VPN/private endpoint có **owner, purpose, peer identity, region, account/project/subscription và ticket**.
- [ ] CIDR IPv4/IPv6 được quản lý qua **IPAM**, tránh overlap/ambiguous routes.
- [ ] Chọn direct peering, hub/transit, VPN, private circuit hay private endpoint theo **đúng use case**.
- [ ] Có phân loại prod/dev/partner/on-prem/management **trust tiers**.
- [ ] Có approval/IaC/policy-as-code cho create/accept peering, route, firewall và DNS changes.
- [ ] Không cho app service accounts quyền sửa route/attachment/SG/NSG nếu không cần.
- [ ] Có audit log ở control plane và alert thay đổi ngoài ticket/change window.
- [ ] Có thời hạn review/thu hồi của peering tạm, contractor/partner và môi trường acquired.

### 18.2. Routes và connectivity

- [ ] Đã xác nhận tính **non-transitive** hoặc transit forwarding theo đúng sản phẩm/topology.
- [ ] Route tables hai đầu, return path, prefix specificity và effective next hop đã được kiểm tra.
- [ ] Transit attachment associations/propagations tách các routing domains nhạy cảm.
- [ ] Không nhận **0.0.0.0/0, ::/0 hoặc prefix broad** ngoài thiết kế.
- [ ] Đường primary/secondary VPN/circuit có **routing và security policy parity**.
- [ ] Kiểm tra IP overlap và NAT/translation mapping nếu cần.
- [ ] Kiểm tra stateful firewall symmetry, NAT/conntrack và MTU/MSS cho đường tunnel.
- [ ] Không bỏ quên **IPv6 routes/SG/NSG/DNS AAAA**.
- [ ] Kiểm tra route bypass trung tâm qua direct peering, Internet hoặc private endpoint.

### 18.3. Security policy và identity

- [ ] Chỉ cho phép **đúng source workload/subnet → destination service/port**.
- [ ] Dev/partner/guest/IoT **không truy cập production DB/admin** ngoài ngoại lệ được kiểm soát.
- [ ] Egress policy tại nguồn và ingress policy tại đích tương ứng mục đích.
- [ ] SG/NSG/NACL/firewall rules được kiểm tra **theo semantics riêng của sản phẩm**.
- [ ] API có TLS/mTLS peer validation và application authorization độc lập với IP route.
- [ ] Database và management ports không mở cho toàn peer CIDR.
- [ ] Private endpoint/service policy giới hạn đúng principal/action/resource.
- [ ] Origin/private services không có alternate public path gây bypass.
- [ ] IAM/secrets/certificates từ môi trường partner/dev không mặc định được tin như prod.

### 18.4. DNS và hybrid connectivity

- [ ] Private DNS zones/resolver rules có owner, TTL/records và association đúng.
- [ ] Split-horizon DNS được thử từ đúng nguồn/VPC/on-prem/region.
- [ ] DNS forwarding không loop, không lộ private queries trái mục đích.
- [ ] Private service hostname trỏ tới đúng private endpoint; TLS SAN/peer identity khớp.
- [ ] VPN peer identity/crypto policy và key rotation được quản lý.
- [ ] Dedicated circuit **không được mặc định coi là encrypted application session**.
- [ ] BGP prefix import/export/route filters có allowlist và alert.
- [ ] Đường failover hybrid được kiểm tra DNS, route, firewall, MTU, mTLS và logging.

### 18.5. Quan sát và phản ứng

- [ ] Flow logs ở cả hai VPC/VNet/route domains liên quan được bật theo policy và có heartbeat.
- [ ] Cloud audit logs bao phủ peering, route, SG/NSG, DNS, IAM và endpoint policy changes.
- [ ] Firewall/IDS/IPS logs phản ánh **đúng các đường đi thật**, không suy mọi traffic qua hub.
- [ ] Có application logs/identity/request IDs để phân biệt flow allow với API success.
- [ ] Có alert khi prod→dev/partner mới reachable hoặc có sensitive-port access.
- [ ] Có cảnh báo khi số BGP prefixes/route propagation hoặc default route thay ngoài baseline.
- [ ] Có kiểm tra **IPv6 flows và direct path bypass**.
- [ ] SIEM không chứa passwords, raw tokens, secret keys hoặc payload dữ liệu nhạy cảm không cần.
- [ ] Có runbook khi nghi data exfil, route leak, unauthorized peering, DNS conflict và mất visibility.
- [ ] Khi containment có phương án rollback, chỉ gỡ attachment sau khi xác minh dependencies/DR.

### 18.6. Bảng nghiệm thu tối thiểu

| Hạng mục | Evidence bắt buộc | Đạt khi |
| --- | --- | --- |
| Peering owner | Asset registry, peer IDs, ticket, approver | Hai phía xác nhận đúng đối tượng và phạm vi |
| Routing | Effective route cả hai đầu, IPv4/IPv6 | Không có unwanted transit/default route |
| Firewall | SG/NSG/ACL/NetworkPolicy + allow/deny tests | Sensitive ports và nguồn trái quyền bị deny |
| Identity | TLS/mTLS/API auth logs | Chỉ principal/scope được cấp phép truy cập |
| DNS | Query logs từ mỗi nguồn liên quan | Đúng private name/IP/CA, không leak |
| Hybrid | BGP/tunnel sessions, import/export lists | Route learned/propagated theo policy |
| HA | Failover test, return path, MTU, app SLO | Backup không bypass security, traffic hợp lệ phục hồi |
| Logging | Flow/audit/DNS/health timestamps | Không có coverage gaps không được ghi nhận |
| Lifecycle | Change record, review date, rollback | Có người chịu trách nhiệm và điều kiện thu hồi |

**Không nghiệm thu chỉ bằng “Peering status = Active”.** Tối thiểu phải chứng minh một flow hợp lệ hoạt động, các flow cấm bị chặn, route không mở transit ngoài ý định và logging quan sát được thay đổi.

## 19. Bài tập thiết kế và câu hỏi ôn tập

### 19.1. Bài tập kiến trúc: mở kết nối cloud nhưng giữ ranh giới Prod

Một công ty có:

~~~text
Production Cloud Account:
  VPC-P Orders: 10.10.0.0/16
  VPC-Q Payments: 10.11.0.0/16

Development Cloud Account:
  VPC-D Dev: 10.20.0.0/16

Analytics Account:
  VPC-A Analytics: 10.30.0.0/16

Shared Services:
  VPC-S: 10.40.0.0/16 (DNS, audit, artifact mirror)

Data Center:
  172.20.0.0/16 (legacy ERP via VPN/private circuit)

Partner:
  10.50.0.0/16 (may add new subnets)
~~~

Nhu cầu:

- Analytics chỉ cần **Orders summary API** TCP/443 theo service identity.
- Dev cần **artifact mirror** và test data synthetic, không được truy cập DB production.
- Orders API cần gọi một service ERP ở on-prem.
- Payments API có dữ liệu nhạy cảm, không muốn expose trực tiếp vào Dev/Partner routes.
- Central Network Security muốn quản lý **egress/inspection**, nhưng không muốn hub trở thành một vùng route all-to-all.
- Một partner chỉ cần truy cập **Partner API** được phê duyệt; mạng partner có tiêu chuẩn quản trị khác.
- Production và DR cần failover qua nhiều vùng và kiểm soát IPv6.

**Yêu cầu nộp:**

1. Vẽ **network topology** và đánh dấu mỗi peering/transit/VPN/private endpoint, cùng owner.
2. Chọn **direct peering hay private service endpoint** cho Analytics→Orders; giải thích về blast radius.
3. Thiết kế **hub route domains** tách Production, Development và Partner; không cho route leaks.
4. Lập **CIDR/IPAM và IPv6 review**, kể cả nếu Partner bổ sung subnet.
5. Lập ma trận **10 allow/deny flows** gồm Orders→ERP, Analytics→Orders API, Dev→Artifact, Partner→API và các forbidden DB/admin.
6. Mô tả **BGP/VPN route advertisements** giữa on-prem và cloud, có prefix filters và DR paths.
7. Thiết kế **DNS private zone/resolver forwarding**; chứng minh names trả đúng IP khi failover.
8. Gắn **mTLS/service identity và API authorization** cho Analytics/Partner, không dùng CIDR làm quyền cuối cùng.
9. Chỉ rõ **điểm đặt firewall/IDS/IPS** và những direct paths có thể bypass hub.
10. Thiết kế **SIEM alerts** khi route table thêm 0.0.0.0/0 hoặc Dev học Production database prefix.
11. Viết **rollout/canary/rollback** khi tạo partner connection, gồm offboarding.
12. Chuẩn bị **DR game day** để chứng minh backup route không mở quyền khác primary.

**Tiêu chí đạt:** không có “mọi VPC nhìn mọi VPC” mặc định; route/SG/NSG và identity đều least-privilege; DNS và IPv6 được xét; hybrid route advertisement có giới hạn; logs đủ để chứng minh allow/deny; rollback không làm production mất kết nối không cần thiết.

### 19.2. Câu hỏi tự kiểm tra

**Câu 1.** Peering đang ở trạng thái Active có nghĩa hai ứng dụng chắc chắn nói chuyện được không?

*Gợi ý:* Không. Cần effective routes, firewall/SG/NSG, return path, service listener, DNS và TLS/authorization.

**Câu 2.** Vì sao A peering B và B peering C không tự có A→C?

*Gợi ý:* Peering trực tiếp phổ biến là non-transitive; transit cần kiến trúc/gateway/forwarding được hỗ trợ và được cấp quyền.

**Câu 3.** Peering và private endpoint khác nhau thế nào?

*Gợi ý:* Peering mở quan hệ route giữa các networks; private endpoint thường expose một service/attachment cụ thể với phạm vi quyền riêng.

**Câu 4.** Nếu hai VPC có CIDR overlap, có nên tự thêm route trùng rồi mong hệ thống chọn đúng không?

*Gợi ý:* Không. Cần IPAM, renumbering, NAT/translation hoặc service-level architecture được thiết kế.

**Câu 5.** Vì sao longest-prefix match có thể làm traffic bypass firewall?

*Gợi ý:* Route prefix cụ thể hơn có thể thắng tuyến rộng hơn tới inspection hub; cần review effective routing và product priorities.

**Câu 6.** Một route từ VPC-A tới VPC-B đủ để TCP connection hoàn thành không?

*Gợi ý:* Không. Còn route return, firewall/state, listener, NAT/MTU và authorization.

**Câu 7.** Security group stateful khác stateless network ACL ở điểm gì?

*Gợi ý:* Return traffic có thể được connection tracking cho phép theo state ở nhóm stateful; ACL stateless cần xét rules chiều trả lời/ephemeral ports.

**Câu 8.** IPv4 deny policy có tự chặn kết nối qua IPv6 không?

*Gợi ý:* Không. Cần xem IPv6 routes, AAAA DNS records và firewall/SG/NSG IPv6.

**Câu 9.** VPC-A có private DNS record trả IP 10.20.20.20 của VPC-B; đây có phải chứng cứ peering cho phép truy cập không?

*Gợi ý:* Không. DNS name resolution và network reachability là hai lớp riêng.

**Câu 10.** Làm thế nào phát hiện DNS private zone bị share nhầm vào production?

*Gợi ý:* Review zone associations/forwarding rules, cloud audit logs, queries từ từng VPC, hostname/TLS SAN và test đúng namespace.

**Câu 11.** Một VPN tunnel hoạt động có chứng minh mọi subnet on-prem reachable không?

*Gợi ý:* Không. Cần route selectors/BGP advertisements, firewall/return path, DNS và service policy.

**Câu 12.** Dedicated private circuit có mặc định bảo vệ thông tin ứng dụng bằng TLS/mTLS không?

*Gợi ý:* Không. Đây là loại đường kết nối; encryption/peer identity ứng dụng hoặc IPsec phải được thiết kế riêng khi cần.

**Câu 13.** Route leak 0.0.0.0/0 từ data center có thể gây vấn đề gì?

*Gợi ý:* Thay default next hop, bypass egress inspection hoặc blackhole traffic; cần prefix filters/route policy.

**Câu 14.** Nếu central hub có firewall, có chắc mọi direct VPC peering traffic đi qua nó không?

*Gợi ý:* Không. Phải xem effective routes, alternate paths, DNS/private endpoints và log coverage.

**Câu 15.** Vì sao chỉ mở TCP/443 qua peering chưa đủ để cấp quyền cho Reporting đọc Orders?

*Gợi ý:* TLS peer identity, API authentication và application scope còn phải được xác minh.

**Câu 16.** Flow log cho biết TCP/443 allowed và 2 MB bytes; có thể nói dữ liệu khách hàng đã bị đánh cắp không?

*Gợi ý:* Chưa đủ. Cần context workload, API/database access, data classification, session identity và owner.

**Câu 17.** Vì sao một private VPC của Dev không nên mặc định được tin như Prod?

*Gợi ý:* Khác owner, credentials, patching, workload trust, secrets và policy; private address không đại diện mức bảo mật.

**Câu 18.** Hub-and-spoke có thể tăng blast radius trong trường hợp nào?

*Gợi ý:* Nếu tất cả spokes học route lẫn nhau, firewall/route domain cấu hình quá rộng hoặc hub control plane bị chiếm.

**Câu 19.** Tại sao một route đến subnet DB không đồng nghĩa có quyền đọc DB?

*Gợi ý:* Route cho reachability, nhưng firewall, TLS, DB authentication, RBAC và app authorization vẫn phải hoạt động. Tuy nhiên route quá rộng làm tăng surface.

**Câu 20.** Một kỹ sư thêm 10.0.0.0/8 qua partner peering để “đảm bảo không bị thiếu subnet”. Cần đánh giá gì?

*Gợi ý:* Scope rất rộng, có thể overlap/hijack routes, tăng risk; cần explicit prefixes và change approval.

**Câu 21.** Khi hybrid primary failover sang VPN backup, sao cần test an ninh riêng?

*Gợi ý:* Route/firewall/NAT/DNS/MTU và VPN crypto policies có thể khác, tạo bypass hoặc lỗi availability.

**Câu 22.** Vì sao PrivateLink/private service endpoint không tự bảo đảm không thể data exfiltration?

*Gợi ý:* Endpoint/IAM/resource policy và egress/data permissions vẫn có thể quá rộng.

**Câu 23.** Một flow log bị mất do collector lỗi, có thể xem không có connections trong thời gian đó không?

*Gợi ý:* Không. Phải ghi coverage gap, khôi phục telemetry và đối chiếu logs khác.

**Câu 24.** Những control-plane actions nào cần audit khi quản lý peering?

*Gợi ý:* Create/Accept/Delete attachment, route table changes, SG/NSG/firewall updates, DNS associations, IAM permissions và transit propagation.

**Câu 25.** Khi peering dự án kết thúc, cần thu hồi những gì ngoài attachment?

*Gợi ý:* Route, SG/NSG, DNS forwarding/zone association, private endpoints, IAM, mTLS cert/token và monitoring exceptions.

**Câu 26.** Vì sao cùng một IP ở hai VPC overlap làm điều tra source identity khó khăn?

*Gợi ý:* IP có thể là hai assets; NAT mapping, owner, route domain và event time cần được xác minh.

**Câu 27.** Nếu HTTP 403 xuất hiện sau peering, có nên mở rộng firewall không?

*Gợi ý:* Không vội. Xác định 403 từ gateway/app, principal/scope/authorization; network đã có thể hoàn tất.

**Câu 28.** Làm thế nào chứng minh policy deny Dev→Prod DB thật sự hoạt động?

*Gợi ý:* Negative connectivity test từ đúng Dev workload và cả IPv4/IPv6, đối chiếu firewall/flow logs, không chỉ đọc IaC.

**Câu 29.** Khi mở transit route domain cho partner, làm sao kiểm soát network exposure?

*Gợi ý:* Tách route tables/import/export policies, giới hạn prefixes/service endpoints, firewall/identity và audit, test từ nguồn chưa được duyệt.

**Câu 30.** Tại sao số route/peering attachments tăng không đồng nghĩa hệ thống an toàn hơn hoặc yếu đi đúng bằng cùng tỷ lệ?

*Gợi ý:* Rủi ro phụ thuộc assets, privileges, reachable paths, policy, owner, monitoring và resilience; số attachment chỉ là một dữ liệu inventory.

### 19.3. Bài tập phân tích nhật ký sau thay đổi

Một bảng trạng thái mô phỏng:

~~~text
Trước thay đổi:
  Peering Prod–Reporting: active
  Allowed flow: Reporting→Orders API TCP/443
  Denied flows: Reporting→DB, Reporting→Management
  Flow logs healthy: both VPCs

Sau thay đổi:
  Event A: Dev subnet 10.20.40.0/24 được cho phép tới Orders DB TCP/5432.
  Event B: Transit route table nhận 10.10.0.0/16 từ attachment không rõ owner.
  Event C: VPC flow exporter ở Reporting báo mất heartbeat 15 phút.
  Event D: Orders API thành công 200 với Reporting service identity.
  Event E: DNS resolver ở Dev trả private endpoint IP của prod-admin.
~~~

**Câu hỏi:**

1. Event nào là **thay đổi control plane**, event nào là **mất visibility**, event nào chứng minh application success?
2. Có đủ chứng cứ để kết luận Dev đã truy cập DB hay prod-admin chưa?
3. Hãy xếp thứ tự điều tra **A–E** theo mức ảnh hưởng và mức tin cậy evidence, có lý do.
4. Đề xuất **containment ít gián đoạn** nếu A là thay đổi trái quyền, nhưng D là luồng sản xuất quan trọng.
5. Cần những log bổ sung nào để biết đã có data exfiltration?
6. Đề xuất policy-as-code rule ngăn A/B tái diễn và test DNS/IPv6 cho E.

**Đáp án định hướng:**

- **A/B/E** là các dấu hiệu policy, route hoặc DNS có thể mở rộng exposure; cần xác minh effective config và quyền sử dụng. **C** là telemetry health issue; **D** là một application success cho workload hợp lệ.
- Không thể kết luận Dev đã đọc DB chỉ từ một rule allow mới; cần **flow TCP/5432, DB audit, principal/queries/data access**. Một DNS answer prod-admin cũng không chứng minh network path/access thành công.
- Nên ưu tiên **thu hẹp rule A, route policy B và kiểm tra DNS E**, đồng thời khôi phục C để không bỏ lỡ dấu vết; giữ allow Reporting→Orders API theo đúng policy để tránh ảnh hưởng D.
- Bằng chứng bổ sung gồm **cloud audit actor/change ticket, effective routes, firewall/flow logs, DB/API logs, NAT/session mapping, data owner, DLP và outbound network flow** theo đúng event-time.

## 20. Tổng kết

- **VPC/VNet peering** cho phép hai mạng cloud có quan hệ kết nối logic, **không tự cấp quyền application, database hoặc management**. Địa chỉ private không thay identity và authorization.
- **Peering trực tiếp phổ biến là non-transitive**: A↔B và B↔C **không tự cho A↔C**. Transit phải được thiết kế bằng topology/gateway/forwarding được sản phẩm hỗ trợ và kiểm soát rõ.
- **CIDR overlap, longest-prefix routes, route propagation, default routes, NAT, asymmetric routing và IPv6** là các nguồn gây lỗi connectivity và mở rộng reachability ngoài ý định.
- **SG/NSG/firewall, egress controls, segmentation và workload/API identity** phải giới hạn **đúng nguồn–đích–port–hành động**, không mở toàn peer CIDR chỉ vì hai mạng thuộc cùng doanh nghiệp.
- **DNS/private zones và private endpoints** có ranh giới riêng: phân giải được hostname không chứng minh kết nối hoặc service identity hợp lệ; private service access không đồng nghĩa full network peering.
- **Hub-and-spoke, transit gateway/cloud WAN, VPN và dedicated private links** cho phép mở rộng nhiều mạng/hybrid, nhưng cần giới hạn routing domains, BGP prefixes, inspection path và failover policies. Đường private không mặc định mã hóa dữ liệu ứng dụng.
- **Rủi ro chính** gồm lateral movement, data exfil qua peer, control-plane/IAM misuse, route leaks, shadow peering, trust expansion qua partner/acquired network và mất khả năng giám sát.
- **Flow logs, cloud audit, DNS, firewall/IDS/IPS, TLS/mTLS và application logs** bổ trợ nhau; flow allow không chứng minh API authorization, và log im lặng không chứng minh không có traffic.
- **Thiết kế Zero Trust** đặt API/mTLS authorization ở điểm dịch vụ, tách trust tiers và không coi CIDR hay VPN gateway là danh tính người dùng.
- **Triển khai an toàn** bắt đầu từ use case, IPAM, route/SG/NSG/DNS/identity policy, IaC approval và negative tests. Mỗi peering phải có owner, expiry/review, telemetry, rollback và offboarding.
- **Mục tiêu cuối cùng không phải nối được nhiều VPC nhất**, mà là chỉ mở đúng những đường cần thiết, ngăn các đường không được cấp phép và giảm **blast radius** khi sự cố xảy ra trong một mạng cloud được mở rộng.
