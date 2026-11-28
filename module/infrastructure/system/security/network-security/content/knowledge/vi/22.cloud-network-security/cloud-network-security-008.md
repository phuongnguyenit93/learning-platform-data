# Transit gateway và mô hình hub-and-spoke: kiến trúc định tuyến an toàn trong cloud

**Hub-and-spoke** là mô hình tổ chức mạng theo một vùng trung tâm (**hub**) kết nối với nhiều mạng vệ tinh (**spoke**). Trong môi trường cloud, hub thường là nơi tập trung kết nối hybrid, kiểm tra lưu lượng, dịch vụ mạng dùng chung hoặc điều phối định tuyến; các spoke là những VPC/VNet, nhóm ứng dụng, tài khoản, subscription hoặc môi trường sản xuất/kiểm thử có ranh giới riêng. **Transit gateway** là loại thành phần cung cấp khả năng trung chuyển/định tuyến giữa nhiều kết nối; tùy nhà cung cấp, nó có thể là dịch vụ managed, virtual network hub hoặc tập thiết bị mạng ảo.

Trong chương **Bảo mật mạng cloud** của học phần **SECURITY_NETWORK_SECURITY**, thiết kế hub-and-spoke phải giải quyết đồng thời **reachability** (gói tin có đường đến hay không), **segmentation** (vùng nào được kết nối), **security enforcement** (luồng nào thực sự được phép), **resilience** (khả năng phục hồi khi lỗi) và **observability** (chứng minh đường đi và quyết định an ninh). Mạng trung tâm có thể đơn giản hóa quản lý, nhưng cũng tạo ra **điểm tập trung rủi ro, chi phí và blast radius** nếu mọi spoke được kết nối mà không có chính sách rõ.

Bài học trình bày kiến trúc tham chiếu, đặc điểm của AWS Transit Gateway, các mô hình tương ứng tại Azure và Google Cloud, cách thiết kế bảng định tuyến, phân đoạn và inspection, kết nối hybrid, high availability, kiểm thử cả luồng được phép và bị cấm, cũng như quy trình ứng phó sự cố. Ví dụ IP sử dụng dải tài liệu/private; cấu hình YAML và bảng route là **pseudopolicy cho học tập**, không phải cấu hình có thể áp dụng trực tiếp cho một nhà cung cấp. Các chức năng cụ thể phụ thuộc phiên bản dịch vụ, loại attachment, khu vực triển khai và chính sách nhà cung cấp.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **hub, spoke, attachment, transit router, route domain, next hop** và trust boundary trong cloud.
2. So sánh mô hình **full mesh, point-to-point peering, hub-and-spoke và managed transit** theo quy mô và rủi ro.
3. Mô tả cách **route table association, route propagation và static route** ảnh hưởng tới khả năng kết nối trong AWS Transit Gateway.
4. Phân biệt **định tuyến thành công** với **được phép truy cập**; biết nơi cần firewall/SG/NACL/identity policy.
5. Thiết kế **prod/dev/management/shared-services isolation** và chống vô tình tạo đường east–west.
6. Hiểu cơ chế **centralized inspection** qua firewall/NVA và nguy cơ **asymmetric routing** với thiết bị stateful.
7. Lập kế hoạch **ingress, egress, NAT, DNS, IPv6, private endpoints và kết nối on-premises**.
8. Đánh giá **dynamic routing, BGP advertisement/withdrawal, overlapping CIDR và route leaks**.
9. Phân tích **multi-AZ, multi-region, HA, failover/failback và failure domain**.
10. Xây inventory, kiểm soát IAM/control plane, log/metrics, ma trận thử nghiệm và runbook có thể kiểm chứng.

## 2. Hub-and-spoke giải quyết vấn đề gì?

Giả sử doanh nghiệp có 20 VPC: một số phục vụ ứng dụng production, số khác là development, security, analytics và shared services. Nếu kết nối trực tiếp từng cặp mạng theo mô hình full mesh, số cặp có thể tăng rất nhanh.

Với N mạng, số cặp kết nối trong **full mesh hoàn chỉnh** là:

\[
E = \frac{N(N-1)}{2}
\]

Ví dụ 20 mạng có tối đa 190 cặp kết nối trực tiếp; 20 spoke nối một hub thường có khoảng 20 quan hệ kết nối spoke–hub ở mức logic, dù kiến trúc thực tế còn cần attachments/route tables, liên kết dự phòng, NAT và kiểm soát riêng.

### 2.1. Ba mô hình kết nối

| Mô hình | Đặc trưng | Ưu điểm | Hạn chế |
|---|---|---|---|
| **Isolated VPC/VNet** | Không có đường liên mạng trực tiếp | Blast radius nhỏ, dễ xác định trust boundary | Khó chia sẻ dịch vụ |
| **Full mesh/peering point-to-point** | Nhiều kết nối giữa từng cặp | Đường đi rõ cho một số hệ thống nhỏ | Route/peering tăng theo số mạng, governance phức tạp |
| **Hub-and-spoke** | Spokes tập trung qua transit hub | Quản lý hybrid, shared services và policy tập trung hơn | Hub thành điểm phụ thuộc, route leaks/inspection bottleneck |
| **Regional/multi-region managed transit** | Nhà cung cấp hỗ trợ định tuyến trung tâm và mạng liên vùng | Giảm vận hành router/NVA thủ công trong scope được hỗ trợ | Chi phí, giới hạn tính năng và scope có thể khác từng vùng |

**Full mesh không mặc định “ít an toàn”, hub-and-spoke không mặc định “an toàn hơn”.** Mức an toàn phụ thuộc route permissions, identity policies, visibility và operational discipline.

### 2.2. Kiến trúc khái niệm

~~~mermaid
flowchart TB
    ONP[On-premises / Branch] -->|VPN / Private connection| HUB[Transit Hub]
    PROD[Spoke: Production] --> HUB
    DEV[Spoke: Development] --> HUB
    SHARED[Spoke: Shared services] --> HUB
    MGMT[Spoke: Management] --> HUB
    INS[Centralized Firewall / Inspection] --> HUB
    HUB -.Route domains & attachment policies.-> CTRL[Route governance]
    INS -.Traffic and threat logs.-> SOC[SIEM / SOC]
    HUB -.Flow/route metadata.-> SOC
~~~

Sơ đồ chỉ thể hiện topology logic. **Một đường vẽ tới hub không có nghĩa các spoke được phép kết nối lẫn nhau**. Quyết định còn phụ thuộc route table, propagation, firewall và chính sách ở destination.

## 3. Từ vựng cốt lõi: phải tách ba loại quyết định

Một gói từ Production Spoke muốn đến Database Spoke thường cần:

1. **Source route:** bảng route trong VPC/subnet/virtual network biết next hop tới transit.
2. **Transit route:** transit hub nhận packet tại attachment và chọn next hop theo route domain/table được gắn.
3. **Destination route:** spoke đích có đường trả lời về source, qua transit hoặc policy tương đương.
4. **Security control:** firewall, security group, network ACL, workload identity hoặc application auth thực thi quyền.
5. **Operational state:** attachments, tunnels, AZ, appliances và các dependency đang hoạt động.

Nếu chỉ có bước 1–3, mạng có thể **routable nhưng không authorized**. Nếu chỉ có ACL allow mà thiếu route, ứng dụng vẫn timeout.

### 3.1. Các khái niệm

| Khái niệm | Ý nghĩa |
|---|---|
| **Hub** | Thành phần/trust domain trung tâm cho transit, inspection hoặc dịch vụ dùng chung |
| **Spoke** | Mạng vệ tinh có address space, workload, policy và owner riêng |
| **Attachment/connection** | Mối nối giữa mạng/spoke/VPN/peering và transit hub |
| **Route table / route domain** | Tập quy tắc xác định next hop cho traffic thuộc một miền |
| **Association** | Gắn một attachment với route table dùng để **tra cứu** tuyến cho traffic đi vào từ attachment đó, theo semantics dịch vụ |
| **Propagation** | Đưa tuyến học được của attachment vào một hoặc nhiều route tables đã chọn, khi dịch vụ hỗ trợ |
| **Static route** | Tuyến do cấu hình quản trị tạo, không tự thay đổi theo BGP hoặc attachment propagation |
| **Blackhole/discard** | Tuyến nhằm loại bỏ traffic khớp policy |
| **Transitive connectivity** | A có thể đi qua một router/hub để đến C, không nhất thiết cần direct A–C peer |
| **Inspection hop** | Điểm firewall/NVA/WAF/IDS hoặc security service cần đi qua trước đích |
| **Return path** | Đường ngược từ đích về nguồn, rất quan trọng cho stateful session |

**Tên thuật ngữ có thể giống nhau nhưng semantics khác nhau giữa AWS, Azure và GCP.** Không mang nguyên bảng lệnh hoặc giới hạn của một cloud sang cloud khác.

## 4. Những dạng hub khác nhau

Một hub có thể chứa nhiều vai trò, nhưng nên phân biệt:

- **Routing hub:** xử lý định tuyến L3 giữa VPC/VNet, VPN và các kết nối khác.
- **Inspection hub:** chứa network firewall, NVA hoặc hệ thống giám sát được phép xử lý traffic.
- **Shared services hub:** DNS, directory, bastion/jump host, proxy, observability, artifact services.
- **Hybrid connectivity hub:** nơi nối cloud với data center/chi nhánh qua VPN, đường riêng và BGP.
- **Internet egress hub:** tập trung NAT/firewall/proxy cho traffic ra Internet.
- **Remote-access hub:** VPN/ZTNA cho nhân viên/thiết bị; không nên mặc định cấp quyền đến mọi spoke.

Có thể đặt các vai trò trong một VPC/VNet hoặc tách riêng để giảm blast radius. Một **shared-services VPC** không nên trở thành nơi mọi workload có quyền quản trị chỉ vì được gắn vào hub.

### 4.1. Tập trung không đồng nghĩa đi qua firewall

Nếu mọi spoke gắn transit hub nhưng route cho phép **Spoke A → Spoke B trực tiếp qua transit**, traffic có thể **không đi qua** inspection VPC/NVA dù inspection VPC cũng gắn hub. Phải chứng minh cụ thể **tuyến nguồn, transit decision, appliance path và return path**.

## 5. AWS Transit Gateway: các thành phần cần hiểu

**AWS Transit Gateway (TGW)** là dịch vụ transit routing được quản lý, kết nối các mạng và attachment types được hỗ trợ. Các loại attachment phổ biến bao gồm **VPC**, **site-to-site VPN**, kết nối **Direct Connect qua thành phần tương ứng**, và **Transit Gateway peering**; khả năng và giới hạn cụ thể phải xác minh theo khu vực/tính năng.

### 5.1. TGW route tables

Một TGW có thể có **nhiều transit gateway route tables** để tách các miền định tuyến logic.

- Traffic **đi vào TGW từ một attachment** được tra cứu theo **route table mà attachment được associate**.
- Route của một attachment có thể được **propagate** tới các route tables được chọn nếu attachment/route type hỗ trợ.
- Route tĩnh có thể được thêm cho những prefix cần thiết.
- Một số kết nối/route types, chẳng hạn đường peering, cần quản trị tuyến tĩnh tùy tính năng, không suy rằng propagation tự động tồn tại.
- **Blackhole routes** có thể được dùng để loại bỏ prefix không được phép trong chính sách tương ứng.
- Default association/propagation khi tạo TGW/attachment là **một quyết định bảo mật**, phải rà soát theo cấu hình thực tế thay vì dựa vào giá trị mặc định.

Một attachment tại một thời điểm thường được **associate tới một TGW route table** để tra cứu khi traffic đi vào; route propagation là quyết định **riêng** và có thể tới nhiều tables theo hỗ trợ. Hai khái niệm không đồng nghĩa.

### 5.2. VPC route tables vẫn quan trọng

Một TGW attachment không tự làm mọi subnet trong VPC gửi traffic vào TGW. Cần kiểm tra:
- Route table của **subnet nguồn** có tuyến tới prefix đích qua TGW hay không.
- Attachment được cấu hình cho những Availability Zones/subnets phù hợp.
- Security groups/NACL chặn hay cho phép traffic.
- Địa chỉ của đích thuộc prefix được TGW/VPC route đúng.
- Return route tại destination spoke/hub có hợp lệ không.
- Appliance firewall có interface/route và connection state đúng không.

**Tuyến trong TGW và tuyến trong VPC là hai lớp cấu hình độc lập.** Có route ở một lớp nhưng không có lớp kia thường dẫn đến timeout mà dashboard attachment vẫn báo available.

### 5.3. Attachment state không chứng minh application connectivity

Một TGW attachment ở trạng thái sẵn sàng chỉ chứng minh một số điều kiện control plane/data plane đã đạt. Nó không chứng minh:
- Route của source subnet đã tồn tại.
- Transit lookup chọn đúng next hop.
- Security group/ACL cho phép cổng yêu cầu.
- Firewall inspection đã kiểm tra cả hai chiều.
- DNS resolver/endpoint hoạt động.
- Database/API chấp nhận credential và request.

**Không đánh dấu test PASS chỉ vì attachment active hoặc BGP session Established.**

## 6. Route table association và propagation

Đây là phần dễ nhầm nhất khi thiết kế TGW.

Giả định có ba spoke:
- **Prod**: 10.70.0.0/16.
- **Dev**: 10.71.0.0/16.
- **Shared**: 10.80.0.0/16.

Nếu mọi attachment được associate cùng một table và propagate tất cả prefixes vào table đó, các spoke **có thể có đường định tuyến** tới nhau (nếu VPC routes và controls còn lại cho phép). Đây là một dạng **route domain rộng** có thể trái mục tiêu cô lập Prod–Dev.

### 6.1. Ví dụ logic trước khi áp security inspection

| Attachment nguồn | TGW association | Table có route tới | Ý định |
|---|---|---|---|
| Prod | RT_PROD | Shared DNS/approved services, on-prem cần thiết | Chỉ những đích được duyệt |
| Dev | RT_DEV | Shared dev tooling, không chứa Prod CIDR | Chặn Dev→Prod ở lớp routing |
| Shared | RT_SHARED | Prod/Dev theo quyền thực tế | Tránh tự động mở mọi chiều |
| Management | RT_MGMT | Bastion/management endpoints | Chỉ nhóm quản trị được cấp |
| Inspection | RT_INSPECT | Các spoke cần được kiểm tra sau firewall | Không tạo vòng lặp inspection |

Mô tả trên là **mục tiêu topology**, chưa đủ để deploy vì phải xét route từng VPC, firewall/appliance next hop, prefix specificity, topology hybrid và default route.

### 6.2. Association quyết định table vào; propagation quyết định học route

~~~mermaid
flowchart LR
    A[Spoke Prod attachment] -->|Associate| T1[RT_PROD]
    B[Spoke Dev attachment] -->|Associate| T2[RT_DEV]
    S[Shared attachment] -->|Propagate theo policy| T1
    S -->|Propagate theo policy| T2
    T1 -->|Chỉ destination hợp lệ| X[Next hop]
    T2 -.Không có route Prod.-> DENY[No route / blackhole]
~~~

Không được nghĩ **“Prod propagate vào RT_SHARED”** tức Prod đã sử dụng RT_SHARED khi gửi packet. Attachment source dùng **associated table** của nó, không tự chuyển table theo route destination. Tương tự, một prefix xuất hiện trong nhiều tables không đồng nghĩa mọi attachment đều có thể dùng prefix đó.

### 6.3. Static routes và prefix priority

Khi nhiều tuyến có thể khớp destination, router thường áp **longest prefix match** cùng các quy tắc ưu tiên khác của dịch vụ. Do đó một route tổng hợp 10.0.0.0/8 có thể bị một route cụ thể 10.70.0.0/16 hoặc 10.70.10.0/24 lấn át.

**Không chỉ so default route hoặc tổng hợp CIDR.** Khi điều tra một luồng, luôn kiểm tra **prefix cụ thể nhất thực tế đang có** và next hop sau mọi quy tắc priority của nhà cung cấp.

### 6.4. Route propagation không phải firewall rule

Một route được propagate cho phép transit route table biết nơi đến prefix, nhưng không nhất thiết cấp quyền truy cập. Ngược lại, bỏ route có thể tạo cô lập L3, song không thay thế firewall/identity vì có thể tồn tại **đường khác** như VPC peering, PrivateLink, service endpoint, endpoint proxy hoặc kết nối ngoài transit.

## 7. Phân tích đường đi của một luồng

Giả sử Prod App tại **10.70.12.10** cần gọi Shared DNS tại **10.80.1.53**.

~~~mermaid
sequenceDiagram
    participant A as Prod 10.70.12.10
    participant V as Prod VPC router
    participant T as Transit Hub
    participant S as Shared VPC router
    participant D as DNS 10.80.1.53
    A->>V: DNS request theo policy
    V->>T: Next hop tới 10.80.0.0/16
    T->>S: Lookup RT_PROD và forwarding
    S->>D: NACL/SG/host policy cho phép
    D-->>S: DNS response
    S-->>T: Route trả về 10.70.0.0/16
    T-->>V: Lookup RT_SHARED và forwarding
    V-->>A: Response theo return path
~~~

Để phép thử thành công, phải có **cả hai chiều**:
- Source subnet route đưa prefix 10.80.0.0/16 tới hub.
- RT_PROD có tuyến tới Shared attachment.
- Destination subnet/host chấp nhận traffic.
- Shared subnet có tuyến trả về 10.70.0.0/16 qua hub.
- RT_SHARED có tuyến về Prod attachment.
- SG/NACL/host ACL, firewall, identity và DNS server cho phép.
- Nếu có centralized inspection, **tuyến hai chiều phải đi qua điểm kiểm tra theo policy**.

### 7.1. Reachability, authentication, authorization

Với một API/DB thay vì DNS:
- **Reachability:** packet đến đúng endpoint.
- **Transport authentication:** TLS/mTLS xác minh server/service identity.
- **Application authorization:** user hoặc workload có quyền thực hiện thao tác.
- **Data authorization:** chỉ được đọc/ghi dữ liệu thuộc phạm vi.

**Private connectivity không thay thế TLS/identity.** Một workload bên trong cloud vẫn có thể giả mạo request nếu API chỉ kiểm tra nguồn private IP.

## 8. Transitive routing và blast radius

Mạng A peering với B không nhất thiết cho phép A đi qua B để đến C; nhiều mô hình **VPC/VNet peering không cung cấp transitive routing mặc định**. Một transit hub/virtual appliance được thiết kế để hỗ trợ nhiều kiểu trung chuyển, nhưng **transitivity phải được kiểm soát theo policy**.

### 8.1. Rủi ro east–west mở quá rộng

Nếu Dev, Prod, Security Tools và Data Spokes đều có route tới nhau:
- Một workload Dev bị chiếm có thể có đường mạng thử kết nối tới Prod.
- Rủi ro lateral movement tăng nếu security groups/host firewalls có rule rộng.
- API nội bộ có thể chỉ tin network location và bỏ identity.
- Shared services có thể trở thành điểm pivot giữa các trust domains.
- Sự cố route table hoặc prefix advertisement có blast radius trên nhiều accounts.

### 8.2. Phân vùng theo rủi ro

Một chiến lược có thể dùng:
- **RT_PROD**: ứng dụng production và dịch vụ dùng chung được duyệt.
- **RT_DEV**: development và môi trường test, không có route Prod.
- **RT_MGMT**: đường vào bastion/management.
- **RT_PARTNER**: kết nối đối tác, chỉ các service endpoints cần thiết.
- **RT_INSPECTION**: domain sau khi traffic qua firewall.
- **RT_HYBRID**: chỉ prefixes cần thiết đến data center, không tự quảng bá mọi subnet.

Không cần đúng số lượng này. Mỗi route table làm tăng chi phí vận hành; **ít tables nhưng có kiểm soát rõ** đôi khi tốt hơn quá nhiều bảng không ai sở hữu.

### 8.3. Không tin mô hình “allow all internal”

Một route 10.0.0.0/8 hoặc 0.0.0.0/0 tới transit có thể vô tình tạo đường đến nhiều spoke hoặc Internet egress. Nếu toàn bộ private address space được quảng bá mà security policy thiếu phân đoạn, “mạng nội bộ” trở thành một miền tin cậy quá lớn.

**Cơ chế mặc định nên là deny theo yêu cầu nghiệp vụ**, sau đó mở các prefixes/ports/identities thật sự cần, có owner và audit.

## 9. Thiết kế route domains cho Prod, Dev và Shared

Giả định:

| Spoke/Vùng | CIDR | Ý nghĩa |
|---|---|---|
| Production App | 10.70.0.0/16 | Ứng dụng sản xuất |
| Development | 10.71.0.0/16 | Test/dev |
| Shared Services | 10.80.0.0/16 | DNS, directory, artifact mirror |
| Management | 10.90.0.0/16 | Bastion, admin agents |
| Inspection | 10.95.0.0/16 | Firewall và security services |
| On-premises | 172.20.0.0/16 | Data center doanh nghiệp |

### 9.1. Ma trận reachability mục tiêu

| Nguồn → Đích | Prod | Dev | Shared | Mgmt | On-prem |
|---|---|---|---|---|---|
| Prod | Theo app segmentation | **Deny** | Chỉ DNS/dịch vụ cần | Chỉ agent/management đã phê duyệt | Các prefix được duyệt |
| Dev | **Deny** | Theo dev policy | Chỉ dev tooling | Hạn chế | Chỉ lab services cần |
| Shared | Không tự all-access | Không tự all-access | Theo owner | Chỉ vận hành | Hạn chế |
| Mgmt | Chỉ qua bastion/RBAC | Theo admin role | Quản trị cần thiết | Theo admin | Qua kênh quản trị |
| On-prem | Chỉ dịch vụ được công bố | Thường deny hoặc hẹp | Chỉ dịch vụ hybrid | Chỉ admin path | Theo mạng nội bộ |

Bảng trên là **policy intent**. Để đạt được, phải kết hợp:
- Route table association/propagation hoặc route domain isolation.
- Firewall policy theo source/destination/port.
- Security group và host authorization.
- Workload identity, mTLS hoặc application authentication.
- Chặn đường phụ bypass transit.
- Positive và **negative connectivity tests**.

### 9.2. Route-based isolation và firewall-based isolation

**Không có route** tới Prod từ RT_DEV là một lớp cô lập tốt, nhưng vẫn cần kiểm tra alternate connectivity. **Firewall deny** giữa hai CIDR là lớp khác, giúp ngăn luồng khi routing vô tình thay đổi. Có thể kết hợp hai lớp để phòng lỗi cấu hình.

Cần hiểu giới hạn: việc một **route table không có prefix Prod** không chứng minh một dev service không gọi được Prod thông qua **shared proxy, private endpoint hoặc API gateway**; các đường đó cần identity và authorization riêng.

## 10. Centralized inspection: vì sao khó hơn “thêm firewall vào hub”?

Một **inspection VPC/VNet** thường chứa firewall hoặc **Network Virtual Appliance (NVA)** để kiểm tra east–west, north–south hoặc hybrid traffic. Kiến trúc mong muốn:

~~~mermaid
flowchart LR
    A[Prod Spoke] -->|Transit hop| F[Inspection Firewall]
    F -->|Sau policy| B[Shared/On-prem Spoke]
    B -->|Return path| F
    F -->|Return path| A
    F -.Rule, session & threat logs.-> SOC[SIEM]
~~~

Hình là **đường logic được phép**, không phải mô tả định tuyến tự sinh khi attachment mới được tạo.

### 10.1. Vì sao routing symmetry quan trọng?

Một **stateful firewall** theo dõi trạng thái của kết nối. Nếu packet đi **A → firewall X → B** nhưng response đi **B → firewall Y → A** mà X/Y không chia sẻ state, response có thể bị drop. Ngay cả khi đều đi qua một nhóm firewall, load balancing, AZ placement, NAT và session affinity vẫn ảnh hưởng stateful inspection.

~~~text
Đường đi:
Prod -> TGW -> Firewall A -> TGW -> Shared

Đường về sai:
Shared -> TGW -> Firewall B -> TGW -> Prod

Hậu quả có thể:
- Response bị stateful firewall drop.
- Session không ổn định, reset/timeout bất thường.
- Logs tại firewall không thấy đủ cả hai chiều.
~~~

### 10.2. AWS TGW appliance mode

Trong một số mô hình **centralized inspection có stateful appliances**, AWS Transit Gateway có tùy chọn **appliance mode** trên **VPC attachment phù hợp** nhằm hỗ trợ giữ traffic của một flow theo đường AZ/appliance thiết kế. **Không nên diễn giải appliance mode là tự bật firewall, tự kiểm tra packet hoặc giải quyết mọi bất đối xứng**: còn route tables, appliance routing, attachment AZ, firewall scaling, NAT và return path.

Phải kiểm tra:
- Attachment nào thực sự bật appliance mode.
- Firewall deployment theo AZ và state management/HA.
- Route từ spokes tới inspection attachment.
- Route sau inspection tới đích và ngược lại.
- Tác động của cross-AZ traffic và failover.
- Vendor-specific guidance cho stateful appliances và TGW.

### 10.3. Vì sao inspection VPC có thể bị bypass?

Một mạng có thể có:
- Route trực tiếp từ RT_PROD đến Shared attachment bên cạnh route qua inspection.
- VPC peering song song hoặc private endpoint không qua hub.
- Legacy VPN/direct connection đến đích.
- CIDR cụ thể hơn định tuyến khác với route tổng.
- Security group cho phép luồng mà firewall không quan sát được.

**Kiểm tra cấu hình firewall không đủ**; phải chứng minh packet đi đúng **ingress, inspection và egress path** trong tất cả kịch bản cần bảo vệ.

### 10.4. Fail-open và fail-closed

- **Fail-closed:** khi inspection service không khả dụng, traffic được bảo vệ bị chặn; bảo toàn security boundary nhưng ảnh hưởng availability.
- **Fail-open:** traffic vẫn có thể đi đường khác khi inspection lỗi; tăng availability có thể đánh đổi giảm kiểm soát.

Lựa chọn phải được **phê duyệt theo dữ liệu/ứng dụng**, không để xảy ra ngẫu nhiên do một tuyến dự phòng rộng. Một hệ thống thanh toán và một dịch vụ public cache có thể có yêu cầu khác nhau.

## 11. Centralized egress và NAT

Nhiều tổ chức đưa outbound Internet traffic từ workloads qua **egress VPC/VNet** có firewall, NAT, proxy, DNS filtering và logging.

### 11.1. Đường đi khái niệm

~~~mermaid
flowchart LR
    APP[Private App Spoke] --> TGW[Transit Hub]
    TGW --> FW[Egress Firewall / Proxy]
    FW --> NAT[NAT Gateway / Egress Service]
    NAT --> NET[Internet]
    NET --> NAT
    NAT --> FW
    FW --> TGW
    TGW --> APP
~~~

Thực tế tuyến có thể qua subnet/IGW và các hop khác; cần tuân thủ yêu cầu cụ thể của cloud provider.

### 11.2. Những điều phải kiểm chứng

- Source spoke có **default route 0.0.0.0/0** hay chỉ prefixes cụ thể về egress?
- TGW route table của source có đích 0.0.0.0/0 đi inspection/egress attachment theo ý định?
- Firewall/egress subnet có đường ra Internet và return path đúng không?
- NAT xử lý địa chỉ nguồn, port exhaustion và logging ra sao?
- Có hỗ trợ HTTP CONNECT, TLS inspection hay egress proxy theo policy không?
- DNS resolution có dùng resolver được phê duyệt và DNS egress controls không?
- IPv6 có đường khác bypass inspection/NAT IPv4 không?
- Các cloud endpoints có thể dùng **private endpoint/service endpoint** thay vì Internet không?
- Có chính sách egress riêng cho system updates, artifact repos, identity và telemetry không?

**NAT không phải firewall đầy đủ**. NAT thay đổi địa chỉ/port theo cơ chế, không tự cấp application authorization hoặc chống SSRF tới private/metadata endpoints.

### 11.3. Chi phí và độ trễ

Centralized egress có thể gây:
- Cross-AZ/cross-region data processing và transfer charges.
- Tăng latency/hairpin route.
- Nút nghẽn tại firewall, NAT, proxy hoặc tunnel.
- Single failure domain nếu chỉ có một AZ.
- Tác động tới tốc độ download artifacts và update.

Không phải mọi traffic bắt buộc đi hub. Có thể kết hợp **local egress được kiểm soát** cho một số spoke, nếu threat model và khả năng giám sát cho phép.

## 12. Hybrid networking: VPN, đường riêng và BGP

Hub thường là điểm nối cloud với data center hoặc chi nhánh qua **site-to-site IPsec VPN**, kết nối riêng và các giải pháp SD-WAN. Một số nền tảng hỗ trợ BGP để tự động quảng bá/thu hồi prefixes.

### 12.1. Lợi ích và rủi ro BGP

| Mục tiêu | Lợi ích | Rủi ro nếu thiếu policy |
|---|---|---|
| Học prefix tự động | Ít phải cập nhật static routes thủ công | Học cả mạng không được phép |
| Failover link | Có thể rút route khi link/BGP lỗi | Route churn, reconvergence, flapping |
| Đa đường | Phân phối traffic theo thiết kế | Asymmetry qua firewall stateful |
| Mở rộng chi nhánh | Quản lý nhiều prefixes | Prefix overlap, route table bloat |
| Tách prod/dev | Có thể dùng route filtering/domain | Route leak xuyên trust boundary |
| Đường mặc định | Có thể đưa Internet/hybrid qua hub | Vô tình quảng bá default route tới sai spoke |

**BGP session Established không chứng minh chính sách an toàn**. Cần kiểm tra **prefixes thực tế được nhận/quảng bá, next hops và route tables mà prefixes được đưa vào**.

### 12.2. Route leak và prefix advertisement

Một route leak có thể khiến:
- Dev học đường tới Prod qua on-prem.
- On-prem học default route đi ra cloud ngoài chủ ý.
- Spoke học prefix không thuộc đối tác.
- Đường về chọn một gateway khác, bypass inspection hoặc gây asymmetry.
- Một route ngắn/tổng hợp vô tình hút traffic của nhiều VPC.

Phòng vệ bao gồm **prefix allowlists/filters**, maximum-prefix limits nếu platform hỗ trợ, kiểm soát route propagation, route table segmentation và cảnh báo khi quảng bá prefix bất thường.

### 12.3. Không dùng IPsec/VPN để bỏ qua phân quyền

IPsec giữa cloud và data center bảo vệ traffic trên tunnel theo profile, nhưng không tự giới hạn ứng dụng nào được phép gọi database. Phải áp firewall/SG và identity policy sau VPN. Một link private cũng cần đánh giá **thông tin đi qua, ranh giới tin cậy và quyền giữa các đội vận hành**.

## 13. Quy hoạch CIDR và xử lý mạng bị trùng địa chỉ

Hub-and-spoke khó hoạt động ổn định nếu các spoke hoặc on-prem dùng CIDR trùng nhau.

### 13.1. Ví dụ overlap

- Spoke A: 10.70.0.0/16.
- Spoke B: 10.70.0.0/16.
- On-prem: 10.70.20.0/24.

Một route tới 10.70.0.0/16 không thể xác định cùng lúc nên đến A hay B chỉ từ destination IP. Thêm NAT hoặc các giải pháp định danh/segmentation có thể giải quyết một số trường hợp, nhưng tăng độ phức tạp và rủi ro.

### 13.2. Cách giảm vấn đề

1. Quản lý **IPAM tập trung** theo organization, account, region và env.
2. Dành CIDR không trùng cho từng spoke, tối ưu đủ chỗ tăng trưởng.
3. Kiểm tra overlap **trước khi tạo attachment** hoặc quảng bá BGP.
4. Với mạng đối tác khó đổi IP, xem **NAT/translational gateway, proxy, private service access hoặc application-level integration**.
5. Lập map giữa original và translated addresses, đảm bảo DNS, log, return path đồng nhất.
6. Cân nhắc **IPv6** có kế hoạch thay vì xem đó là bản vá tự động cho CIDR overlap.
7. Kiểm thử route specificity và prefix conflicts sau khi merge mạng hoặc chuyển cloud.

**NAT chồng nhiều lớp có thể làm attribution và troubleshooting khó**; cần flow logs có NAT mapping hoặc session metadata phù hợp.

### 13.3. Prefix summarization

Tuyến tổng hợp giúp giảm số route nhưng có thể **mở rộng reachability** nếu tổng hợp bao gồm mạng không được phép hoặc mạng chưa tồn tại. Mỗi route summary phải có owner, policy intent và kiểm thử negative paths.

## 14. Firewall, security group, NACL và Zero Trust

Transit hub chủ yếu quyết định **packet sẽ đi đâu**. Nó không tự thay thế firewall, IDS/IPS hoặc authorization.

### 14.1. Các lớp thực thi

| Lớp | Khả năng | Giới hạn |
|---|---|---|
| TGW/transit route table | Chỉ định đích/next hop, route segmentation, discard | Không hiểu user/REST API permissions |
| VPC/VNet subnet routes | Đưa traffic tới hub/NVA/gateway | Không bảo đảm caller được phép |
| Security group / NSG tương ứng | Lọc kết nối theo IP/port/identity constructs tùy cloud | Không thay object authorization |
| Network ACL/subnet firewall | Lọc theo rule/đường mạng | Có thể stateless, phải xét cả hai chiều |
| Stateful network firewall/NVA | Connection tracking và policy L3–L7 theo năng lực | Cần symmetric path và capacity |
| WAF/API gateway | Kiểm soát HTTP route, headers, token và abuse theo tính năng | Không giải quyết mọi lỗi business logic |
| IDS/IPS/NDR | Phát hiện/chặn dấu hiệu mạng theo sensor placement | TLS encryption có thể ẩn payload |
| mTLS/service identity | Xác thực workload/peer | Không tự cấp quyền tất cả API |
| Application RBAC/ABAC | Quyền theo user, tenant, operation và object | Cần code/policy đúng và audit |

Các tên **security group, NACL, NSG** không có semantics y hệt giữa providers. Ví dụ AWS security groups thường stateful, còn AWS network ACLs thường stateless; không áp kết luận đó lên mọi firewall cloud.

### 14.2. Nguồn private IP có thể bị giả định sai

Nếu database cho phép 10.0.0.0/8 trên TCP/5432, nó có thể reachable từ nhiều spoke nếu transit hub có route. **Private source IP là thuộc tính mạng, không phải identity mạnh**. Với dữ liệu nhạy cảm, dùng service identity, DB auth, TLS, firewall và scope IP phù hợp.

### 14.3. Microsegmentation trong spokes

Hub segmentation nên bổ sung **microsegmentation**:
- Prod API chỉ gọi Prod DB trên port cần thiết.
- Dev workload không gọi Production management.
- Bastion chỉ cho account/operator được duyệt và ghi audit.
- Egress chỉ tới đối tác/updates/telemetry được phép.
- Kubernetes namespaces/pods theo NetworkPolicy/mTLS khi phù hợp.

**Cô lập ở TGW route table không thay thế microsegmentation trong cùng một VPC**: traffic giữa hai subnet trong một spoke có thể không đi qua TGW.

## 15. DNS, resolver và service discovery qua hub

Trong mô hình hub-and-spoke, **DNS là một dependency quan trọng**. Workload có thể có route tới IP đích nhưng không phân giải được hostname, hoặc phân giải đúng tên nhưng nhận IP thuộc mạng mà policy chặn.

### 15.1. Các lựa chọn thường gặp

- Shared internal DNS resolvers/forwarders ở hub/shared services.
- Private DNS zones được liên kết với những mạng được phép.
- DNS forwarding giữa cloud và on-prem theo suffix/domain.
- DNS Firewall/filtering tại resolver hoặc egress.
- Private endpoint DNS để dịch vụ cloud được phân giải về private IP.
- Split-horizon DNS cho các môi trường khác nhau.

### 15.2. Những rủi ro phổ biến

| Vấn đề | Triệu chứng | Cần xác minh |
|---|---|---|
| Không route tới resolver | DNS timeout | Source route, TGW, SG, UDP/TCP 53 hoặc giao thức được dùng |
| Forwarder loop | Truy vấn lặp/timeout | Forwarding rules và suffix ownership |
| Private zone gắn sai VPC | NXDOMAIN hoặc IP không mong muốn | Zone associations, namespace/tenant |
| Resolver public được dùng ngoài policy | DNS leak hoặc sai zone | Client OS/app resolver và egress |
| TTL/caching trong failover | App tới endpoint cũ | DNS TTL, cache, app retry, cutover |
| Dùng DoH riêng | Bỏ qua DNS policy dự định | Egress/application enterprise policy |
| CNAME tới public endpoint | Traffic đi ra Internet ngoài chủ ý | Full chain và route/security policy |

**Không coi DNS resolution là authorization**. Một tên nội bộ có thể bị gọi bởi workload không được phép nếu route/firewall/app policy quá rộng.

### 15.3. DNS qua transit không nhất thiết phải qua một server IP

Một số cloud DNS service có resolver đặc thù theo VPC/VNet hoặc các endpoint managed. Không giả định mọi cloud-provided resolver sẽ cho phép truy vấn xuyên TGW chỉ vì có route; cần xem **dịch vụ DNS endpoint, association, forwarding rules và phạm vi hỗ trợ**.

## 16. IPv6, NAT và dual-stack trong hub-and-spoke

Khi thêm IPv6, một mạng có thể có **hai mặt phẳng định tuyến và lọc**: IPv4 và IPv6. Hệ thống có thể bảo vệ IPv4 tốt nhưng cho IPv6 đi một đường khác.

### 16.1. Câu hỏi cần trả lời

- Mỗi spoke có IPv6 CIDR nào và có trùng/mâu thuẫn policy không?
- Transit attachments và route tables có hỗ trợ IPv6 cho đúng loại kết nối?
- Default IPv6 route **::/0** đi đâu?
- Firewall/IDS/egress có kiểm tra IPv6 như IPv4 không?
- DNS AAAA trả private/public IPv6 nào?
- VPN/on-prem có hỗ trợ dual-stack thực tế hay chỉ IPv4?
- Local egress cho IPv6 có bypass centralized inspection không?
- Security groups/ACL ở IPv6 có mirror policy cần thiết không?

### 16.2. NAT IPv4 không tự bảo vệ IPv6

Một **NAT gateway dành cho IPv4** không mặc định xử lý mọi IPv6 traffic. Nhiều kiến trúc IPv6 dùng routing trực tiếp, egress-only gateway hoặc các mô hình translation khác tùy provider. Không copy route 0.0.0.0/0 rồi nghĩ traffic ::/0 cũng đi qua inspection.

### 16.3. Dual-stack test matrix

Nếu một API có cả A và AAAA record, kiểm thử:
1. Kết nối IPv4 qua đường đã định.
2. Kết nối IPv6 qua đường đã định.
3. Return path của từng address family.
4. TLS/hostname verification giống nhau.
5. Firewall deny cho unauthorized source ở cả IPv4 và IPv6.
6. DNS/resolver và egress logs đúng path.
7. Failover khi một address family lỗi.

**“IPv4 PASS” không chứng minh “dual-stack PASS”.**

## 17. So sánh cách triển khai trên AWS, Azure và Google Cloud

Các cloud khác nhau về thuật ngữ, default behavior, routing domain và service limits. Không thể chuyển nguyên file route table từ provider này sang provider khác.

| Mục tiêu | AWS (khái niệm) | Azure (khái niệm) | Google Cloud (khái niệm) |
|---|---|---|---|
| Mạng spoke | VPC | VNet | VPC network |
| Managed transit/hub | Transit Gateway | Hub VNet với gateway/NVA; Azure Virtual WAN virtual hub | Network Connectivity Center (NCC) và các kết nối hỗ trợ |
| Route isolation | TGW route table association/propagation | VNet routes, UDR, route tables/intent trong hub theo mô hình | NCC connectivity/routing topology, VPC routes, router policies theo dịch vụ |
| Hybrid | Site-to-site VPN / Direct Connect liên quan | VPN Gateway / ExpressRoute / vWAN | Cloud VPN / Cloud Interconnect / Cloud Router |
| Inspection | Inspection VPC, managed firewall/NVA | Azure Firewall/NVA, secured virtual hub | Cloud firewall/NVA/inspection pattern phù hợp sản phẩm |
| Private service access | PrivateLink/endpoints và lựa chọn khác | Private Link/private endpoints | Private Service Connect và các lựa chọn tương ứng |
| Quan sát | VPC/TGW flow logs, CloudTrail và firewall logs theo cấu hình | VNet flow/network/security logs và Azure activity theo sản phẩm | VPC Flow Logs, Cloud Audit Logs, firewall logs theo cấu hình |

Các mục trong bảng **không hoàn toàn tương đương**. “Có managed hub” không có nghĩa mọi provider cho cùng loại peering, propagation, kiểm tra stateful traffic hoặc HA. Cần kiểm tra tài liệu dịch vụ và giới hạn **đúng ngày, region, attachment type, account/subscription/project và version** khi triển khai thật.

### 17.1. AWS TGW không phải Azure VNet Peering

- AWS TGW là thành phần transit được quản lý với TGW route tables và attachment semantics riêng.
- Azure **VNet Peering** không cung cấp transitivity tổng quát mặc định. Mô hình **hub VNet** thường cần NVA/gateway và UDR/gateway transit theo tính năng.
- Azure **Virtual WAN** cung cấp mô hình virtual hub managed với route policy/intent khác cách vận hành một VNet hub tự xây.

### 17.2. GCP NCC không phải chỉ “Cloud Router”

- **Network Connectivity Center (NCC)** là khái niệm hub/spoke managed cho kết nối mạng phù hợp.
- **Cloud Router** hỗ trợ điều khiển dynamic routing/BGP trong những trường hợp được hỗ trợ, **không phải một router truyền packet data plane tự động tương đương toàn bộ transit hub**.
- VPC route exchange, NCC spoke types, firewall, private connectivity và policy phải được kiểm chứng theo topology thật.

**Không suy rằng một VPC đã join NCC thì có thể giao tiếp mọi VPC khác**; route/topology policies và network controls vẫn quyết định.

## 18. High availability: multi-AZ và vùng lỗi

Một transit hub managed có thể có khả năng chịu lỗi ở cấp dịch vụ, nhưng **ứng dụng của bạn vẫn có thể mất mạng** nếu các thành phần xung quanh chỉ triển khai một AZ, một đường WAN hoặc một firewall instance.

### 18.1. Vùng lỗi phải được xác định cụ thể

| Lớp | Ví dụ lỗi | Phòng vệ và kiểm chứng |
|---|---|---|
| Workload subnet | Một AZ mất tài nguyên | Multi-AZ workload, route và LB targets phù hợp |
| Transit attachment | Attachment/subnet/AZ không sẵn sàng | Đủ attachment coverage và route fallback theo nhà cung cấp |
| Inspection appliance | Một NVA hoặc firewall node lỗi | HA/scale-out, health checks, session behavior |
| NAT/egress | NAT instance/gateway hoặc proxy quá tải | Egress HA, capacity, AZ-local design nếu phù hợp |
| VPN tunnel | Một tunnel/IPsec endpoint lỗi | Nhiều tunnels/peers, BGP/health và route policy |
| Dedicated connection | Link/circuit provider down | Circuit diversity và backup theo SLA |
| DNS/resolver | Resolver/forwarder không truy cập được | Redundant resolvers, forwarding correctness, synthetic checks |
| Identity/control plane | IAM/API/certificate issue | Break-glass có kiểm soát, cached auth phù hợp, runbook |
| Monitoring | Flow logs/SIEM mất ingest | Telemetry loss alert và kiểm chứng độc lập |

**Một TGW “Available” không bảo đảm mọi spoke vẫn liên lạc được.** Phải đo luồng thực tế giữa source và destination qua chính route tables, SG/firewall và dependencies.

### 18.2. Kiến trúc đa AZ

~~~mermaid
flowchart TB
    A1[Spoke A - AZ 1] --> TGW[Transit Hub]
    A2[Spoke A - AZ 2] --> TGW
    TGW --> F1[Firewall - AZ 1]
    TGW --> F2[Firewall - AZ 2]
    F1 --> S1[Shared Service - AZ 1]
    F2 --> S2[Shared Service - AZ 2]
    F1 -.Health/Flow logs.-> SOC[Monitoring]
    F2 -.Health/Flow logs.-> SOC
~~~

Đây là sơ đồ logic. Việc forward đến firewall ở AZ nào cần tuân thủ **dịch vụ và appliance routing behavior**, không mặc định TGW tự phân phối theo đúng quy tắc bạn muốn.

### 18.3. Failover và failback

Thử nghiệm cần đo:
- Thời gian **route withdrawal/convergence**.
- Tỷ lệ request thành công trong và sau failover.
- Số connection state bị mất do chuyển firewall.
- Chênh lệch latency và data-transfer cost khi đi cross-AZ.
- Độ lệch cấu hình firewall/SG và route ở standby.
- Đường trở lại khi failback có sinh route flapping hoặc session resets không.
- Luồng bị cấm trước sự cố có **vẫn bị cấm** sau failover không.

**Không gắn nhãn “HA đạt” nếu chỉ thấy ping quay lại** nhưng database/TLS sessions và identity policy bị lỗi.

## 19. Multi-region, peering và disaster recovery

Khi tổ chức có các workload ở nhiều regions, một hub trong region A không nhất thiết có reachability tự động tới region B. Nhiều nhà cung cấp có cơ chế **inter-region peering hoặc managed backbone connectivity**, nhưng phải xét route policy, hạn chế attachment và chi phí.

### 19.1. Những quyết định kiến trúc

- **Một hub mỗi region** hay một hub toàn tổ chức?
- Prod và Dev có cần đi xuyên region hay tách hẳn?
- Traffic inter-region có cần qua inspection ở một hoặc cả hai phía?
- On-prem kết nối tới region chính hay có hai đường độc lập?
- DNS failover đổi endpoint, nhưng route và policy có đồng bộ không?
- Nếu primary region down, backup có đúng truststore, IAM, keys và BGP prefixes không?
- Dữ liệu có yêu cầu **residency**, tuyến vận chuyển và log storage trong vùng nhất định không?
- Có giới hạn egress cost hoặc cross-region latency/SLO?

### 19.2. Peering không tự tạo route propagation toàn cục

Trong một số thiết kế TGW peering, cần **static route** cho remote prefixes, và không thể kỳ vọng transit peering chain tự tạo connectivity qua nhiều TGWs. Các provider có khác biệt lớn. Luôn xác minh:
1. Peering/connection state.
2. Route ở source VPC.
3. Route trong local transit table.
4. Route trong remote transit table.
5. Destination subnet route.
6. Return path và firewall/SG.
7. Security policy khi traffic đi qua nhiều jurisdictions/regions.

### 19.3. Failover đa vùng có thể tăng blast radius

Một rule “khi region A mất thì route toàn bộ 10.0.0.0/8 sang region B” có thể hút cả traffic của môi trường không thuộc DR scope. Nên dùng **prefixes và application groups đã được duyệt**, kiểm soát thay đổi tự động bằng điều kiện/owner và test rollback.

## 20. Hub-and-spoke trong Kubernetes và service mesh

Kubernetes có networking riêng với **Pod CIDRs, Service CIDRs, CNI, Gateway/Ingress, NetworkPolicy và service discovery**. Kết nối cluster VPC với transit hub không tự bảo đảm định tuyến tới từng Pod CIDR.

### 20.1. Những lớp cần phân biệt

| Lớp | Ví dụ | Cần kiểm tra |
|---|---|---|
| VPC/subnet | Node và load balancer addresses | Route tới transit, SG/NACL |
| CNI/Pod network | Pod IP, overlay hoặc native routing | Pod CIDRs, SNAT, policy, data plane |
| Service network | ClusterIP, NodePort, LoadBalancer | Có thể route được từ ngoài cluster hay không |
| Ingress/Gateway | HTTP/API entry | Identity, TLS, authZ và WAF |
| Egress gateway | Pod gọi external services | SNAT, egress ACL, DNS, SSRF policy |
| Service mesh | mTLS/service identity | Trust domain, authorization, bypass paths |
| Control plane | Kubernetes API và cluster management | Private endpoint, RBAC/IAM, admin VPN |

### 20.2. Đừng giả định mọi Pod subnet có route xuyên hub

Một số CNI dùng overlay hoặc SNAT khi Pod truy cập ngoài cluster. Flow logs ở TGW có thể chỉ thấy **node/subnet source IP**, không phải Pod IP. Khi điều tra, tương quan:
- Cloud network flow logs.
- CNI/egress gateway logs và NAT mapping.
- Kubernetes namespace/pod/workload identity.
- Application trace và service mesh telemetry.
- NetworkPolicy allow/deny evidence.

### 20.3. East–west không phải tất cả đều qua hub

Traffic giữa Pods cùng VPC/cluster hoặc cùng subnet có thể đi qua CNI/data plane nội bộ và **không chạm TGW/firewall hub**. Do đó centralized inspection qua transit không thay thế **NetworkPolicy, SG for Pods, service mesh authorization hoặc egress controls**.

Nếu cần giám sát lưu lượng East–West bên trong cluster, thiết kế sensor/telemetry theo vị trí dữ liệu thật thay vì chỉ đặt NIDS tại Internet gateway.

## 21. IAM và bảo vệ network control plane

Một lỗi cấu hình route ở quy mô transit hub có thể thay đổi đường đi cho hàng chục mạng trong vài giây. Vì thế quyền sửa route tables, attachments và propagation là **đặc quyền an ninh**.

### 21.1. Đối tượng cần kiểm soát

- Ai được tạo hoặc xóa **transit gateway** và attachments?
- Ai được thay **association** hoặc enable **propagation**?
- Ai được tạo **static route/blackhole route**?
- Ai được gắn **route VPC/VNet** đi qua transit?
- Ai có thể cấu hình **BGP advertisements** trên VPN/on-prem router?
- Ai thay firewall policy, appliance mode hoặc HA settings?
- Ai thay IPAM CIDR allocation và DNS forwarding?
- Ai có thể bật **VPC peering/private endpoints** tạo đường bypass?
- Ai được tắt flow logs hoặc thay retention/policy của SIEM?

### 21.2. Nguyên tắc quyền tối thiểu

Tách các vai trò:
- **Network reader/auditor:** xem route, attachments, logs.
- **Network operator:** thay đổi đúng scope với review và rollback.
- **Security policy owner:** quản trị firewall/rule và kiểm thử.
- **Hybrid network owner:** quản lý BGP/edge circuits và phối hợp on-prem.
- **Break-glass admin:** quyền khẩn cấp có kiểm soát, session recording/audit nếu áp dụng.

Cần **MFA/SSO**, quyền theo tổ chức/project/account, **just-in-time elevation** ở môi trường phù hợp và guardrails cho thay đổi diện rộng. Không dùng một shared permanent admin credential cho mọi môi trường.

### 21.3. Infrastructure as Code và review

Route table changes nên có:
1. Requirement/ticket và owner.
2. Diff trước/sau của CIDR, next hop, association, propagation.
3. Phân tích reachability thay đổi, đặc biệt **Dev→Prod** và **Internet→Management**.
4. Security review khi tạo transit sharing hoặc egress route rộng.
5. Canary/staged change theo phạm vi hỗ trợ.
6. Test và monitoring.
7. Rollback path rõ và approval.
8. Audit trail cho thay đổi ngoài IaC.

**Policy-as-code không tự an toàn** nếu rule template cho phép 0.0.0.0/0 hoặc tự propagate mọi attachment. Phải review nội dung policy và test negative paths.

## 22. Threat model: hub-and-spoke bị lạm dụng như thế nào?

Một threat model phải xác định assets, trust boundaries, actor capabilities và đường đi dữ liệu. Chọn ví dụ tổ chức có Prod/Dev/Mgmt/Shared spokes và kết nối on-prem.

### 22.1. Assets

- API production và database chứa dữ liệu người dùng.
- Bảng route TGW/VPC, firewall policies và routing control plane.
- Secrets của network automation, VPN/BGP và certificate.
- Private endpoints, DNS, PKI, directory và Bastion.
- Flow logs, SIEM, telemetry và change audit.
- Availability/SLO của ứng dụng quan trọng.

### 22.2. Các nguồn rủi ro

| Nguồn | Khả năng | Hệ quả tiềm tàng |
|---|---|---|
| Dev workload bị xâm nhập | Có route trong Dev VPC, quyền app hạn chế | Thử lateral movement qua hub/shared services |
| Cloud IAM credential bị lộ | Sửa TGW/VPC routes nếu policy yếu | Tạo route leak, blackhole hoặc bypass firewall |
| On-prem routing config sai | Quảng bá prefix/default route không đúng | Hút traffic, route asymmetry, outage |
| Inspection NVA lỗi | Drop flows hoặc mất session state | Mất availability/visibility |
| Automation pipeline sai | Sửa tất cả route tables cùng lúc | Blast radius diện rộng |
| Staging/private endpoint public nhầm | Tạo alternate network path | Bypass central inspection |
| Source NAT bị cấu hình sai | Thay đổi source IP attribution | Firewall policy/mapping và logs sai |
| Monitoring mất logs | Không thấy route drift hoặc flow anomalies | Chậm phát hiện và điều tra |
| ISP/link lỗi | BGP failover sang đường khác | Traffic không theo policy/latency mục tiêu |

### 22.3. Attack path khái niệm

~~~text
Workload Dev bị chiếm
  -> tìm shared service reachable
  -> shared service có quyền rộng hoặc trust network-only
  -> đường shared-service tới Prod qua transit
  -> truy cập dữ liệu nếu identity/authorization yếu
~~~

Phòng vệ là **định tuyến tối thiểu + firewall + identity/least privilege** ở từng chặng. Chặn Dev→Prod ở TGW chỉ là một lớp; shared service vẫn cần kiểm tra quyền caller và có policy egress.

### 22.4. Mô hình hóa rủi ro từ route changes

Câu hỏi quan trọng không chỉ “route này hợp lệ không?” mà là **“route này tạo thêm khả năng reachability nào so với baseline?”**. Một route mới từ RT_DEV tới 10.70.0.0/16 hoặc một default route tới spoke không đúng có thể làm thay đổi trust boundary mà không có một lỗ hổng phần mềm nào.

## 23. Logging và observability: chứng minh đường đi thực tế

Định tuyến cloud cần kết hợp **control plane evidence** và **data plane evidence**.

### 23.1. Nguồn telemetry

| Nguồn | Cho biết | Không tự chứng minh |
|---|---|---|
| Transit attachment inventory | Attachment type, state, account/region, CIDR metadata | Ứng dụng kết nối thành công |
| Transit route table inspection | Routes, association và propagation | Firewall đã được đi qua |
| VPC/VNet flow logs | Source/destination IP, ports, action và metadata theo sản phẩm | Toàn bộ HTTP payload/auth user |
| TGW flow logs nếu provider hỗ trợ | Flow qua transit và hành vi route ở phạm vi được ghi | Mọi internal path nằm ngoài TGW |
| Firewall/NVA logs | Allow/deny, session và threat events | App đã xác thực user thành công |
| Cloud audit/control plane logs | Ai sửa route/SG/attachment và khi nào | Packet đã đi đúng route |
| VPN/BGP logs | Peer state, prefix changes, tunnel health | Per-app authorization |
| DNS logs | Resolver, tên miền và phản hồi theo policy | Client cuối cùng đã dùng IP nào |
| Application/DB logs | User/service identity và business action | Tất cả network hops an toàn |
| Monitoring/SLI | Availability, latency, packet loss, resets | Nguyên nhân cụ thể nếu thiếu correlation |

### 23.2. Kết nối các mảnh bằng một case

Giả định Dev workload cố gọi Prod DB:
- TGW RT_DEV không có route đến Prod → VPC/TGW có thể ghi nhận drop/route behavior theo tính năng.
- Nếu request tới firewall, firewall ghi **deny** theo source/destination/port.
- Nếu DB nhận được nhưng trả auth failure, application/DB log cần xác nhận.
- Nếu một egress proxy trung gian thay source IP, cần NAT/proxy mapping để quy về workload.
- Cloud audit giúp biết gần thời điểm đó có ai sửa routing/SG.

**Một log có source 10.71.10.5 không nhất thiết xác định người dùng**, vì workload IP có thể thay đổi và NAT/overlay có thể che danh tính. Cần time-bounded mapping và service identity.

### 23.3. Mẫu log minh họa

~~~json
{
  "timestamp_utc": "2026-11-28T06:00:00Z",
  "environment": "production",
  "region": "example-region",
  "transit_hub_id": "tgw-example",
  "source_attachment": "spoke-dev-example",
  "destination_prefix": "10.70.0.0/16",
  "route_policy_version": "network-policy-v12",
  "decision": "denied_no_route",
  "evidence_type": "policy_evaluation_example",
  "request_id": "lab-correlation-id-42"
}
~~~

**Đây là schema minh họa cho ghi nhận policy test, không phải JSON native của AWS/Azure/GCP.** Log thực tế khác nhau theo dịch vụ; không giả định mọi route lookup denial đều tạo event với trường trên.

### 23.4. Chỉ số quan trọng

- Attachment/tunnel health theo account, AZ, region.
- BGP neighbor state, prefix counts, unexpected route advertisements.
- Route/association/propagation drift và số thay đổi ngoài IaC.
- Firewall allow/deny, session drops, out-of-state packets.
- Throughput/packets-per-second/connection count của NVA/NAT/proxy.
- Packet loss, latency p95/p99 và retransmission theo ứng dụng.
- Cross-AZ/region traffic và chi phí bất thường.
- DNS lookup failures, resolver latency và private zone inconsistencies.
- Flow log coverage, logging delay, mất ingest.
- Count/tỷ lệ **denied-flow tests** không còn đúng theo baseline.

**Không suy “hệ thống an toàn” từ việc số alert giảm**, vì traffic có thể đổi đường và đi ngoài điểm sensor.

## 24. Network governance và cấu hình như mã

Trong môi trường nhiều accounts/projects, quản trị nên kết hợp **IPAM, account/subscription boundaries, tagging, IaC, kiểm soát IAM và kiểm thử policy**.

### 24.1. Hồ sơ cho mỗi spoke/attachment

~~~yaml
# Schema policy quản trị minh họa, KHÔNG phải AWS/Azure/GCP deployment YAML.
spoke_id: "orders-prod"
owner: "platform-team"
environment: "production"
region: "region-a"
cidrs:
  ipv4: ["10.70.0.0/16"]
transit:
  hub_id: "regional-transit-hub"
  attachment_id: "spoke-orders-attachment"
  ingress_route_domain: "RT_PROD_IN"
allowed_destinations:
  - prefix: "10.80.1.53/32"
    service: "corporate-dns"
    ports: ["udp/53", "tcp/53"]
  - prefix: "172.20.10.0/24"
    service: "approved-hybrid-api"
    ports: ["tcp/443"]
inspection_required: true
internet_egress: "managed-egress"
deny_destinations:
  - "10.71.0.0/16"
change_owner: "network-security"
review_status: "approved-example"
~~~

Policy này thể hiện **business intent**, không thay thế route tables, firewall rules hoặc native IaC. Cụ thể, trường ports cần được thực thi bằng firewall/SG, không phải transit route table thuần.

### 24.2. Kiểm thử policy-as-code

Một pipeline có thể phát hiện:
- CIDR overlap.
- Thêm 0.0.0.0/0 hoặc ::/0 vào route domain nhạy cảm ngoài allowlist.
- Route tới Prod từ RT_DEV.
- Attachment mới associate default transit table rộng.
- Propagation bật cho các domain không được phê duyệt.
- Ingress/egress security group mở port nhạy cảm quá rộng.
- Inspection route có đường bypass hoặc route loop dễ phát hiện.
- Trust/certificate/IAM policies lệch giữa AZ/regions.
- Thay config mà không có owner/change ticket.

**Static analysis không thay thế data-plane validation.** Thử nghiệm thật trong staging/lab vẫn cần để phát hiện tính năng provider, đường return path và session handling.

## 25. Chi phí, năng lực và trade-off vận hành

Transit hub giúp giảm số kết nối trực tiếp nhưng có thể tăng data processing/transfer costs và độ trễ.

### 25.1. Những thành phần chi phí

| Thành phần | Chi phí/rủi ro vận hành có thể có |
|---|---|
| Transit attachments | Phí theo thời gian/số lượng theo provider |
| Data processing | Dữ liệu đi qua transit, inspection hoặc gateway |
| Cross-AZ / cross-region | Truyền dữ liệu giữa vùng lỗi/region |
| VPN/private connectivity | Tunnel, đường riêng, băng thông, circuits |
| Firewall/NVA | License, compute, throughput/pps, scaling |
| NAT/proxy/egress | Giờ chạy và lưu lượng, log processing |
| Observability | Flow logs, SIEM ingestion/retention, metrics cardinality |
| Automation/operations | Chính sách, kiểm thử, on-call, change management |

**Không cung cấp một giá USD cố định** vì giá và tính năng phụ thuộc region/provider/thời điểm. Khi lập dự toán, lấy số liệu cập nhật từ billing và price calculator của nhà cung cấp.

### 25.2. Chọn kiến trúc theo traffic pattern

Một hệ thống tải rất lớn giữa hai spokes có thể chịu thêm latency/cost nếu ép mọi byte qua centralized inspection. Cần đánh giá:
- Dữ liệu nào bắt buộc qua firewall?
- Traffic nào có thể dùng private service endpoint kèm auth mạnh?
- Có thể giới hạn route/identity thay cho hairpin không?
- Những luồng lớn có thể dùng regional inspection/local policy mà vẫn đạt yêu cầu?
- Có cần connection tracking tại transit hop hay đủ layer-7 controls ở service?
- Có blind spots khi giảm inspection không?

Quyết định phải dựa trên **threat model, security requirements và số liệu traffic thật**, không tối ưu chi phí bằng cách tắt toàn bộ logging/inspection.

## 26. Ví dụ thiết kế route xuyên centralized inspection

Xem ba spoke:
- Prod: **10.70.0.0/16**.
- Shared: **10.80.0.0/16**.
- Inspection: **10.95.0.0/16**, có firewall stateful.
- Dev: **10.71.0.0/16**, bị cô lập khỏi Prod.

Mục tiêu: **Prod → Shared DNS 10.80.1.53:53** được phép **qua firewall**, chiều về cũng qua firewall; **Dev → Prod** không được phép.

### 26.1. Route intent trên TGW

| Attachment traffic **đi vào từ** | Associated TGW table | Destination | Next hop theo policy |
|---|---|---|---|
| Prod | RT_PROD_IN | 10.80.0.0/16 | Inspection attachment |
| Shared | RT_SHARED_IN | 10.70.0.0/16 | Inspection attachment |
| Inspection | RT_POST_INSPECTION | 10.70.0.0/16 | Prod attachment |
| Inspection | RT_POST_INSPECTION | 10.80.0.0/16 | Shared attachment |
| Dev | RT_DEV_IN | 10.70.0.0/16 | **Không có route/blackhole** |

**Mấu chốt:** packet trước firewall **đi vào transit từ Prod/Shared**, nên tra lookup table tương ứng; packet sau firewall **quay lại transit từ Inspection attachment**, nên tra RT_POST_INSPECTION. Cách này tạo điều kiện để traffic đi qua firewall thay vì tới đích ngay, nhưng chỉ đúng khi cấu hình VPC/inspection path và return routes được thiết kế phù hợp.

### 26.2. Các route trong VPC

~~~text
Prod App subnet route table:
  10.70.0.0/16  -> local
  10.80.0.0/16  -> Transit Hub

Shared subnet route table:
  10.80.0.0/16  -> local
  10.70.0.0/16  -> Transit Hub

Inspection routing (logic):
  traffic từ TGW -> Firewall inspection -> TGW
  chọn đúng subnet/ENI/NVA path và tránh routing loop
~~~

Ví dụ **không đầy đủ để triển khai thực tế**. Với AWS, một VPC có những route tables/subnets gắn với TGW attachment và firewall endpoints/ENIs; tùy sản phẩm, việc áp route để buộc traffic qua inspection có thể khá phức tạp. Cần kiểm tra behavior cụ thể của TGW, AZ, appliance mode và firewall implementation, thay vì cấu hình mọi hướng bằng một default route.

### 26.3. Firewall policy và return path

~~~yaml
# Pseudopolicy, không phải cú pháp firewall vendor cụ thể.
flow:
  source: "10.70.0.0/16"
  destination: "10.80.1.53/32"
  protocols: ["udp/53", "tcp/53"]
  action: "allow"
  inspection: "stateful"
  logging: "enabled"

default_between_prod_and_shared: "deny"
dev_to_prod: "deny"
return_flow: "same-inspection-path"
~~~

Cần xác minh:
- Firewall có state đúng và không đổi nguồn bất ngờ do NAT?
- Cả request/response qua cùng security enforcement context?
- DNS reply tới source subnet có đúng đường?
- SG/NACL trên hai spokes cho phép đúng traffic?
- Firewall deny những port khác, ví dụ 22/5432 khi không được cấp?
- Không có peering/private link/alternate VPN bypass policy?

**Một bảng route không thể lọc UDP/53 khác TCP/22 nếu cùng IP prefix**. Việc giới hạn port phải đặt ở firewall/SG/NACL hoặc service ACL phù hợp.

### 26.4. Kiểm thử đường đi

- **Positive:** Prod instance được cấp phép → DNS 10.80.1.53 UDP/TCP 53 hoạt động.
- **Negative:** Prod → Shared DB TCP/5432 bị deny theo policy.
- **Negative:** Dev → Prod TCP/443 bị no-route hoặc firewall deny.
- **Symmetry:** firewall log thấy hai hướng/session tương ứng.
- **Failover:** một inspection appliance/AZ lỗi; traffic được phép phục hồi trong RTO đã định và denied flows vẫn bị chặn.
- **Observability:** flow logs và config snapshots chứng minh attachment/table/next hop được sử dụng.

## 27. Vì sao route table đúng vẫn chưa đủ?

Có ít nhất bảy điểm có thể làm kết nối thất bại:

1. **Local subnet route thiếu** hoặc không thuộc đúng subnet/instance.
2. **TGW associated route table sai**, ví dụ Prod vô tình dùng RT_DEV.
3. **Route propagation không được bật** hoặc prefix chưa xuất hiện.
4. **Security group/NACL** chặn source/destination/port hoặc chiều về.
5. **Inspection appliance** thiếu route, state, policy hoặc capacity.
6. **DNS/app configuration** trỏ tới địa chỉ/port khác dự kiến.
7. **Return route** về source đi qua đường khác, bị NAT hoặc BGP chọn nhầm.

Ngược lại, kết nối có thể **thành công trái phép** nếu:
- Có alternate VPC peering hoặc public endpoints.
- Dev được học route Prod do default propagation.
- Firewall rule quá rộng.
- Shared service đóng vai proxy với identity policy yếu.
- IPv6 route chưa được bảo vệ.

Vì thế kiểm thử phải gồm **connectivity + route path + authorization + negative cases**.

## 28. Ma trận kiểm thử an toàn cho transit hub

Mỗi test cần owner, environment, account/project, region/AZ, route table snapshot, thời gian, evidence và trạng thái **PASSED/FAILED/NOT_RUN/BLOCKED/INCONCLUSIVE**.

| ID | Kịch bản | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| T01 | Spoke Prod attachment đúng hub/table | Association đúng policy | Attachment inventory + RT association |
| T02 | Dev attachment không propagate tới RT_PROD | Prod không học Dev ngoài ý định | Propagation snapshot |
| T03 | Prod → Shared DNS được duyệt | Thành công qua firewall | Route + firewall + DNS logs |
| T04 | Dev → Prod không có quyền | No route/deny | Route tables + connectivity test |
| T05 | Prod → DB port ngoài allowlist | Bị deny dù có route | SG/firewall logs |
| T06 | Return path từ Shared về Prod | Hoạt động qua inspection | Flow/session bidirectional logs |
| T07 | Stateful firewall một AZ lỗi trong lab | Failover đúng policy/SLO | NVA+route+app telemetry |
| T08 | VPN tunnel chính mất | BGP/route chuyển sang backup được duyệt | Tunnel/BGP events |
| T09 | BGP quảng bá prefix ngoài allowlist trong lab | Không được nhận/propagate vào domain nhạy cảm | Route filters + RT diff |
| T10 | CIDR mới overlap spoke hiện hữu | Provisioning bị chặn/review | IPAM/IaC validation |
| T11 | AWS/Azure/GCP route policy drift | Phát hiện và có owner | IaC diff + cloud audit |
| T12 | Public Internet tới management private IP | Không reachable | SG/firewall/route evidence |
| T13 | IPv6 source tới Prod restricted endpoint | Cùng deny policy IPv4 | IPv6 routes + logs |
| T14 | Shared service DNS failure | Có alert và recovery đúng | DNS/forwarder logs |
| T15 | Prod → on-prem API hợp lệ | Chỉ prefix và port được phê duyệt | VPN/BGP + app logs |
| T16 | On-prem → Dev bị cấm | Không có route/deny | Transit hybrid RT + firewall |
| T17 | Inter-region peering thiếu route return | Nhận diện đúng lỗi | Local/remote RT snapshots |
| T18 | Service mesh mTLS identity sai | L7/app từ chối dù L3 có route | Mesh + app authorization |
| T19 | Kubernetes Pod traffic đi qua SNAT | Truy vết được workload thực | CNI/NAT + flow logs |
| T20 | Egress tới private cloud endpoint | Đi đúng private path | DNS resolution + flow logs |
| T21 | Workload thử egress trái policy | Bị chặn | Egress ACL/proxy/firewall |
| T22 | Origin ingress ngoài edge allowlist | Không bypass WAF/API gateway | Edge + SG + origin logs |
| T23 | TGW default table được tạo mới | Không tự mở connectivity rộng | Default settings + guardrail |
| T24 | Route cụ thể hơn lấn route tổng | Traffic đi đúng next hop đã duyệt | Longest-prefix route inspection |
| T25 | Flow logs/SIEM bị mất ingest | Có alert telemetry loss | Pipeline health |
| T26 | Region failover | Security parity ở region dự phòng | Positive+negative tests |
| T27 | Network admin thay propagation | Có change approval và audit | IAM/cloud audit |
| T28 | Egress/NAT quá tải theo POC hợp lệ | Trong capacity/SLO; không bypass firewall | NAT/NVA metrics |
| T29 | Client ở mạng hybrid dùng DNS tên private | Resolver và route đúng policy | DNS queries + flow |
| T30 | Firewall policy fail-closed theo yêu cầu | Traffic bị chặn khi inspection unavailable | Change-window test |
| T31 | No-route trong TGW nhưng alternate PrivateLink tồn tại | Phát hiện alternate path, app authZ đúng | Service endpoint inventory + logs |
| T32 | Restore sau disaster | Routes, key/cert, monitoring và deny paths còn đúng | DR report + logs |

**Không gửi traffic gây tải hoặc làm gián đoạn production** để kiểm thử. Những case firewall/AZ/BGP failover phải chạy trong lab hoặc change window được phê duyệt và có rollback.

## 29. Công cụ đọc và phương pháp quan sát

Có thể bắt đầu bằng **inventory và lệnh chỉ đọc**. Các ví dụ sau không tạo, thay hoặc xóa route. Kết quả chứa identifiers/private IP; chỉ chia sẻ trong hệ thống quản trị phù hợp.

### 29.1. AWS CLI: xem TGW và route tables

~~~bash
# Chỉ đọc; profile/region đã được cấp quyền và xác minh
aws ec2 describe-transit-gateways \
  --region ap-southeast-1

aws ec2 describe-transit-gateway-attachments \
  --region ap-southeast-1

aws ec2 describe-transit-gateway-route-tables \
  --region ap-southeast-1
~~~

Đầu ra có thể dài. Để xem một bảng cụ thể trong tài khoản lab, các read-only API/CLI thường gồm:

~~~bash
# Thay tgw-rtb-PLACEHOLDER bằng ID thật của tài nguyên do bạn quản trị
aws ec2 get-transit-gateway-route-table-associations \
  --region ap-southeast-1 \
  --transit-gateway-route-table-id tgw-rtb-PLACEHOLDER

aws ec2 get-transit-gateway-route-table-propagations \
  --region ap-southeast-1 \
  --transit-gateway-route-table-id tgw-rtb-PLACEHOLDER
~~~

**Đây là cú pháp ví dụ**; lệnh cụ thể phụ thuộc AWS CLI/permissions và tính năng đang dùng. Không đưa IDs, ARN hoặc private topology thật vào nơi công khai. Nếu account không có quyền xem route tables, **không nâng quyền hoặc dùng credential khác trái phép**.

### 29.2. Xem VPC subnet route table

~~~bash
# Chỉ đọc, có thể lọc theo VPC ID của chính lab
aws ec2 describe-route-tables \
  --region ap-southeast-1 \
  --filters Name=vpc-id,Values=vpc-PLACEHOLDER
~~~

Lệnh này cần **đối chiếu route table được associate với subnet nguồn**, không chỉ nhìn một VPC-level danh sách routes. Hệ thống có thể có nhiều bảng/subnet associations.

### 29.3. Quan sát từ Linux workload được phép

~~~bash
# Local OS routes, chỉ đọc
ip -4 route show
ip -6 route show
ip rule show

# Kiểm tra quyết định route ở host tới IP nội bộ được duyệt
ip route get 10.80.1.53
~~~

**Host route chỉ phản ánh quyết định tại hệ điều hành/VM/Pod**, không phản ánh đầy đủ quyết định bên trong TGW, VPC virtual router hoặc firewall. Cần ghép cùng cloud route tables và flow logs.

### 29.4. Traces và phép thử ứng dụng

Dùng một request nhỏ tới endpoint lab được cấp phép, ví dụ:

~~~bash
# Lab-only: DNS hoặc HTTPS tới tài nguyên nội bộ đã được phê duyệt
getent hosts dns.corp.example
curl --silent --show-error --max-time 5 \
  -I https://api.corp.example/
~~~

Các hostname là placeholder. Với TLS, cần **certificate validation đúng**, không tắt kiểm tra để làm request “thành công”. Một kết quả HTTP 403 có thể chứng minh network/TLS tới app đã tới nhưng application authorization từ chối, **khác** timeout do route.

### 29.5. Lưu ý về traceroute/ping

ICMP có thể bị firewall chặn dù TCP/443 hợp lệ, và một số managed transit fabric **không hiện toàn bộ hop trong traceroute**. Không lấy traceroute thiếu một hop làm bằng chứng firewall đã bị bypass; đối chiếu route policy, firewall logs và flow metadata.

## 30. Chẩn đoán lỗi theo triệu chứng

### 30.1. Attachment available nhưng source không tới destination

Kiểm tra theo thứ tự:
1. VPC subnet route table nguồn.
2. Attachment và associated TGW table.
3. Destination prefix xuất hiện trong TGW table nào.
4. Next hop, longest prefix match và blackhole.
5. Target attachment/AZ và destination VPC route.
6. SG/NACL/firewall, state/return path.
7. App listener, TLS, auth và DNS.

Không sửa hàng loạt SG/firewall trước khi xác định lỗi **routing** hay **authorization**.

### 30.2. Chỉ một chiều có traffic

Khả năng:
- Return route thiếu hoặc đi qua table khác.
- NAT translation thay source không được ghi nhận.
- NACL stateless chặn response.
- Stateful firewall hai chiều đi qua khác appliance.
- Hybrid BGP chọn đường khác cho return path.

Cần so flow logs ở source, destination, TGW và firewall **cùng time window**. Không chỉ xem một packet gửi đi rồi kết luận return path đúng.

### 30.3. Prod gọi Shared được nhưng Dev cũng gọi Prod được

Kiểm tra:
- RT_DEV có route Prod trực tiếp/tổng hợp/default không.
- Dev source VPC có peering/private endpoint/alternate VPN bypass không.
- RT_SHARED có đường từ shared service tới Prod rộng không.
- Firewall/SG không có deny by default hoặc policy theo identity sai.
- Cross-account attachment được share/associate nhầm route table không.
- IPv6 có bypass IPv4 deny hay không.

**Đây là lỗi segmentation**, không phải bằng chứng TGW hoạt động tốt.

### 30.4. Failover sang region B: app success nhưng inspection logs biến mất

Có thể:
- Route B bypass inspection.
- Log collector/firewall B chưa cấu hình.
- Sensor placement không thấy traffic do route thay đổi.
- App traffic đi qua PrivateLink/peering ngoài hub.
- SIEM pipeline hoặc endpoint certificate mất hiệu lực.

Phải xác minh **data-plane path và telemetry**, không chỉ health check 200.

### 30.5. Latency tăng sau centralized egress

Xem:
- Traffic hairpin qua hub và cross-AZ/cross-region.
- Firewall deep inspection, TLS proxy và CPU/pps.
- NAT port exhaustion, connection reuse.
- DNS resolver latency hoặc forwarding loop.
- BGP route thay đổi qua link xa.
- Packet MTU/fragmentation hoặc packet loss.

Tối ưu theo measurements và security requirements. **Không tắt inspection để chữa latency** trước khi có đánh giá/approval và phương án bù rủi ro.

### 30.6. BGP Established nhưng route tới on-prem vẫn timeout

BGP session up không đảm bảo prefix đã được:
- Advertise từ đúng peer.
- Accept qua route filters.
- Propagate vào đúng transit route tables.
- Đưa vào VPC subnet routes.
- Cho phép qua firewall/SG.
- Có return path hợp lệ từ on-prem.

Cũng cần xem on-prem VRF, route summarization, IPSec tunnel selectors/transport và ứng dụng.

## 31. Runbook sự cố transit routing hoặc route leak

### Giai đoạn A — Phát hiện

1. Ghi **incident time**, region, accounts/projects, attachments và ứng dụng bị ảnh hưởng.
2. Phân loại: mất kết nối, latency, bất đối xứng, bypass inspection, route leak hay data exposure.
3. Thu cấu hình **trước/sau** thay đổi route, association, propagation, firewall và BGP.
4. Xem cloud audit để biết actor/automation tạo thay đổi.
5. Phân tích flow logs, firewall, DNS, app SLO và ticket/deployment gần thời điểm lỗi.
6. Ước lượng phạm vi Dev/Prod/Mgmt/on-prem và dữ liệu nhạy cảm có thể reachable.

### Giai đoạn B — Khoanh vùng và giảm tác động

- Nếu **route leak**: xác định prefix và attachment gây leak, áp thay đổi hạn chế với owner/approval, không vội gỡ tất cả routes của hub.
- Nếu **inspection bypass**: áp đường kiểm soát đã phê duyệt, chặn alternate path trái phép và chứng minh lại traffic path.
- Nếu **outage do firewall/NVA**: dùng HA/failover đã thiết kế; quyết định fail-open/closed theo policy.
- Nếu **BGP route churn**: phối hợp hybrid network owner, xử lý nguồn advertisement/filter và giữ logs.
- Nếu **IAM credential bị lộ**: thu hồi/rotate, điều tra cloud audit và chặn thay đổi control plane trái phép.
- Nếu **production bị ảnh hưởng**: khôi phục kết nối được phép nhưng không mở Dev→Prod hay Mgmt public ngoài quyền.

### Giai đoạn C — Phục hồi

1. Khôi phục baseline route tables, attachment associations và propagation.
2. Xác minh VPC subnet routes, SG/NACL, inspection và return path.
3. Kiểm tra DNS, TLS, IAM và application transaction.
4. Chạy **positive và negative tests** ở tất cả affected route domains.
5. Theo dõi latency, session drops, route convergence và cost spike.
6. Kiểm tra multi-AZ/multi-region failback và policy parity.
7. Chỉ đóng incident khi có bằng chứng **availability + segmentation + logging** đạt.

### Giai đoạn D — Hậu kiểm

Đánh giá root cause:
- Guardrails nào thiếu hoặc không hoạt động?
- Ai có quyền tạo route rộng?
- Tại sao một attachment mới được propagate tới sai table?
- Có alternate path nào không được inventory?
- Monitoring/flow logs có phát hiện đủ sớm không?
- Thay đổi có negative tests, rollback và owner không?

Cập nhật IaC, IPAM, architecture decision record, audit và runbook. Tránh chỉ “sửa route bằng tay” mà không sửa nguyên nhân tái diễn.

## 32. Tình huống luyện tập và đáp án gợi ý

### Tình huống A — Dev và Prod cùng route table

Một tổ chức gắn tất cả attachments vào một TGW route table, bật default propagation cho mọi VPC. Dev instance có thể kết nối TCP tới Prod subnet.

**Đáp án:** topology tạo reachability rộng. Tách route domains/associations và propagation theo policy, bổ sung firewall/SG và backend auth. Sau sửa phải test **Dev→Prod deny** và **Prod→Shared allow**.

### Tình huống B — Route được propagate nhưng App vẫn timeout

Prod attachment propagate prefix 10.70.0.0/16 vào RT_SHARED, nhưng request từ Prod tới Shared timeout.

**Đáp án:** propagation của Prod vào RT_SHARED chủ yếu giúp **traffic từ những attachments associate RT_SHARED biết đường tới Prod**, không tự cấp route từ Prod tới Shared. Kiểm tra **RT_PROD association**, VPC route nguồn, SG và return path.

### Tình huống C — Firewall inspection không nhìn thấy traffic

Dev và Shared có TGW attachment, firewall cũng có attachment, nhưng traffic Dev–Shared không xuất hiện trong firewall logs.

**Đáp án:** thêm inspection attachment không tự service-chain. Phải thiết kế route tables bắt buộc đi qua firewall, đảm bảo outbound/return path và loại alternate route/peering bypass.

### Tình huống D — Stateful firewall bị drop response

Request qua Firewall AZ 1, response qua Firewall AZ 2. Hai appliances không chia sẻ session state.

**Đáp án:** asymmetric path. Kiểm tra AZ routing, attachment appliance mode nơi hỗ trợ, firewall vendor deployment, NAT và routes hai chiều. Không sửa bằng cách mở allow-all response.

### Tình huống E — Cloud NAT hoạt động nhưng IPv6 bypass

IPv4 egress từ spoke qua TGW/firewall/NAT. Ứng dụng nhận AAAA và kết nối IPv6 trực tiếp ngoài inspection.

**Đáp án:** thiết kế dual-stack chưa đầy đủ. Kiểm tra ::/0, IPv6 firewall, DNS AAAA, egress-only gateway nếu dùng và endpoint policies. Kiểm thử IPv4/IPv6 riêng.

### Tình huống F — BGP quảng bá nhầm 0.0.0.0/0

On-prem router quảng bá default route ngoài ý định; nhiều workloads cloud đổi next hop và ngừng truy cập Internet.

**Đáp án:** route leak/traffic hijack do routing policy sai. Cần prefix filters, governance của default route, BGP audit, rollback và nghiệm thu outbound route paths. Không chỉ restart VPN.

### Tình huống G — CIDR đối tác overlap Production

Partner dùng 10.70.0.0/16 trùng Prod VPC. TGW không định tuyến phân biệt bằng destination IP như kỳ vọng.

**Đáp án:** cần IPAM/điều chỉnh địa chỉ hoặc thiết kế translation/proxy/private API có identity rõ. Không cấu hình hai next hops cùng CIDR và mong router tự biết tenant.

### Tình huống H — VPC attachment nằm ở một AZ

VPC có workloads ở hai AZ, nhưng attachment/subnet routing chưa hỗ trợ đường từ một AZ theo thiết kế; traffic chỉ lỗi ở zone đó.

**Đáp án:** kiểm tra attachment AZ coverage, source route tables, cloud provider semantics và inspection topology. “TGW available” không bảo đảm cả hai AZ được cấu hình đúng.

### Tình huống I — Kubernetes Pod bị ghi log là Node IP

Một Pod gọi on-prem qua transit; TGW logs ghi source là node address, không phải Pod IP.

**Đáp án:** CNI/SNAT có thể đổi source. Cần kết hợp node/Pod/namespace metadata, egress gateway/NAT mapping và service identity; không quy một IP cho một user.

### Tình huống J — On-prem tới Shared DNS chạy, tới API vẫn lỗi

Hybrid VPN và BGP up, DNS private trả đúng IP. HTTPS đến API timeout hoặc 403.

**Đáp án:** phân biệt **route/SG/firewall/TLS** với application authorization. DNS đúng không đảm bảo reachable. Nếu 403 có thể là deny hợp lệ, không mở firewall mù quáng.

### Tình huống K — Centralized firewall quá tải

Đưa toàn bộ backup và artifact download qua một NVA duy nhất khiến CPU/pps bão hòa, Prod API latency tăng.

**Đáp án:** capacity planning, scale/HA, phân loại traffic theo trust/policy và kiểm soát egress. Giảm tải bằng kiến trúc có phê duyệt, không bypass inspection toàn bộ.

### Tình huống L — Route table của region B mở Dev→Prod

DR failover hoạt động với API 200, nhưng standby TGW vẫn có default association và propagation rộng.

**Đáp án:** security parity thất bại. Sử dụng IaC/policy checks và negative tests tại DR, sửa associations/propagations trước khi công bố failover hoàn tất.

### Tình huống M — Shared service trở thành pivot

Dev không có route tới Prod, nhưng có thể gọi shared proxy; proxy có quyền truy cập Prod và không kiểm tra identity người gọi.

**Đáp án:** route isolation đã bị vượt qua **qua proxy ở layer ứng dụng**. Cần authorization tại shared service, service identity, resource scopes và egress policies của proxy.

### Tình huống N — Đã xóa route nhưng traffic vẫn chạy

Quản trị viên gỡ route Dev→Prod trong TGW, nhưng một API vẫn reachable qua private endpoint hoặc peering khác.

**Đáp án:** có alternate network path. Cần inventory service endpoints, peering, public LB, VPN và application proxy; routing controls chỉ bao phủ đường thuộc domain đó.

### Tình huống O — NIDS không thấy east–west trong cluster

NIDS đặt ở TGW không thấy traffic Pod↔Pod cùng VPC/cluster.

**Đáp án:** traffic có thể đi qua CNI nội bộ, không qua transit hub. Dùng CNI/mesh flow telemetry, endpoint sensors và policy trong cluster.

### Tình huống P — Ping fail, HTTPS lại thành công

Một instance không ping được API qua hub nhưng HTTPS/TLS request có thể kết nối và được backend trả 200.

**Đáp án:** ICMP có thể bị SG/firewall chặn độc lập với TCP/443; routing vẫn có thể đúng. Kiểm tra đúng protocol/service và policy; không dùng ping đơn lẻ làm kết luận.

## 33. Những sai lầm thường gặp

1. **Gắn mọi VPC vào hub rồi coi là đã phân đoạn.** Transit connectivity và segmentation là hai quyết định khác.
2. **Bật default association/propagation cho mọi attachment.** Có thể mở rộng routes ngoài business requirement.
3. **Nhầm association với propagation.** Traffic từ attachment tra table được associate.
4. **Chỉ xem TGW routes mà quên VPC subnet routes.** Source không gửi packet tới TGW.
5. **Có route chiều đi mà quên chiều về.** TCP/DB/app vẫn timeout.
6. **Mặc định centralized firewall kiểm tra mọi traffic.** Có thể có direct route hoặc alternate path.
7. **Không kiểm tra stateful symmetry.** Return đi firewall khác có thể bị drop.
8. **Cho rằng appliance mode tự biến TGW thành firewall.** Còn appliance/data path/HA/policy.
9. **Tách Dev/Prod bằng route table nhưng shared proxy không xác thực.** App proxy trở thành pivot.
10. **Mở 10.0.0.0/8 cho mọi private workload.** Trust domain quá rộng.
11. **NAT thay firewall và authorization.** NAT chỉ là một chức năng mạng.
12. **Không quản lý CIDR overlap.** BGP/route tables có thể chọn sai hoặc không định tuyến được.
13. **Quảng bá default route tùy tiện qua BGP.** Dẫn đến traffic hijack/outage.
14. **Dùng full mesh peering không quản trị.** Route/attachment tăng nhanh và khó audit.
15. **Tin VPC peering transit tự động.** Provider có giới hạn; cần architecture tương ứng.
16. **Xem GCP Cloud Router là data-plane TGW.** Vai trò BGP/control plane khác.
17. **Xem Azure Virtual WAN như một VNet peering thường.** Hub/route intent có semantics riêng.
18. **Chỉ dựng một inspection AZ.** Mất AZ kéo theo outage.
19. **Bỏ qua cross-AZ/cross-region charges.** Chi phí tăng ngoài dự đoán.
20. **Không xét IPv6.** ::/0 có thể bypass egress kiểm soát IPv4.
21. **DNS phân giải đúng rồi kết luận route đúng.** Có thể không có đường tới IP đã phân giải.
22. **Route đến private endpoint đồng nghĩa API được phép.** Vẫn cần service identity/authZ.
23. **Chỉ dựa trên private IP để tin workload.** Internal compromise vẫn tạo nguy cơ.
24. **Không bật/apply firewall policy tại đúng hop.** Traffic đi vòng ngoài sensor.
25. **Coi SG/NACL giống nhau trên mọi cloud.** Stateful/stateless semantics khác.
26. **Không áp microsegmentation trong spoke.** TGW không quản lý mọi luồng cùng VPC.
27. **Không kiểm tra Pod SNAT/CNI overlay.** Attribution và policy sai.
28. **Không có IAM guardrails cho route changes.** Một credential bị lộ có blast radius rộng.
29. **Không quản lý route drift bằng IaC.** Region/DR có cấu hình lệch.
30. **Chỉ nhìn attachment Available hoặc BGP Established.** Không chứng minh app end-to-end.
31. **Chỉ test positive flows.** Dev→Prod có thể âm thầm mở.
32. **Chỉ kiểm tra ping/traceroute.** ICMP hoặc managed fabric không phản ánh đầy đủ.
33. **Không giám sát log loss.** Traffic đổi đường khiến SOC mù.
34. **Không thử failback.** Route flapping hoặc sessions có thể lỗi khi quay về primary.
35. **Coi traffic backup/artifact giống API nhạy cảm.** Chọn đường không theo threat/cost/SLO.
36. **Không có owner của attachment/prefix.** Khó biết route có còn cần hay không.
37. **Không có plan thu hồi trust khi share hub liên account.** Tenant cũ có thể còn route/attachment.
38. **Thay đổi route rộng không có rollback.** Khó khoanh vùng outage và security regression.

## 34. Checklist thiết kế và vận hành transit gateway hub-and-spoke

- [ ] Có sơ đồ **hub, spokes, attachments, route tables, inspection, egress và hybrid paths**.
- [ ] Mỗi spoke có owner, environment, CIDR/IPAM và data classification.
- [ ] Đã xác định các **trust boundaries** Prod, Dev, Mgmt, Shared, Partner, On-prem.
- [ ] Có policy intent rõ **nguồn→đích→port→identity**, không chỉ “allow internal”.
- [ ] Transit route table associations đúng theo từng attachment.
- [ ] Route propagation chỉ tới các tables đã phê duyệt.
- [ ] Default association/propagation đã được review và guardrail.
- [ ] Static, blackhole và summary routes được kiểm tra longest-prefix behavior.
- [ ] Source/destination VPC subnet routes và return paths đầy đủ.
- [ ] Có cách chặn **Dev→Prod** ở L3 và firewall/identity phù hợp.
- [ ] Có inventory alternate paths: peering, PrivateLink/private endpoints, VPN, proxies, public LB.
- [ ] Centralized inspection thực sự nằm trên cả đường đi và đường về.
- [ ] Stateful firewall có symmetry, AZ placement, capacity và HA phù hợp.
- [ ] TGW appliance mode và vendor routing behavior được kiểm chứng khi cần.
- [ ] Đã chọn fail-open/fail-closed có approval theo tài sản.
- [ ] Internet egress có policy về NAT, firewall/proxy, DNS và logs.
- [ ] IPv4/IPv6 policies, 0.0.0.0/0, ::/0 và DNS AAAA được kiểm thử.
- [ ] DNS private zones, forwarding, resolver endpoints và TTL/failover phù hợp.
- [ ] Kết nối on-prem qua VPN/private circuits có BGP prefix filtering và backup.
- [ ] Không có overlapping CIDRs ngoài thiết kế NAT/proxy đã được phê duyệt.
- [ ] Multi-AZ/multi-region topology và security parity đã được thử.
- [ ] Kubernetes/Pod/service traffic được kiểm soát tại CNI/mesh/egress khi không qua hub.
- [ ] IAM tối thiểu cho network routing, attachments, firewall và DNS control plane.
- [ ] Có change approval, IaC diff, route policy checks và rollback.
- [ ] Có flow logs, firewall logs, cloud audit, DNS và app-level correlation.
- [ ] Có alerts cho route drift, BGP prefix changes, unexpected propagation và log loss.
- [ ] Có capacity/cost tracking cho TGW, NVA, VPN, NAT và cross-zone data transfer.
- [ ] Chạy positive tests cho Prod→Approved Shared/On-prem services.
- [ ] Chạy negative tests cho Dev→Prod, Internet→Mgmt, unauthorized egress.
- [ ] Kiểm tra route/symmetry trên các luồng TCP, UDP, TLS và service identity thật.
- [ ] Có kiểm thử failure/failback của AZ, firewall, VPN link, DNS và region trong phạm vi được duyệt.
- [ ] Có incident runbook cho route leak, inspection bypass và availability loss.
- [ ] Các bảng route và policy ngoại lệ được review định kỳ theo thay đổi ứng dụng.
- [ ] Không coi TGW active, ping thành công hoặc HTTP 200 là bằng chứng security tổng thể.

## 35. Tổng kết

**Transit gateway và hub-and-spoke** giúp tổ chức cloud networking theo các miền kết nối rõ ràng, tập trung hybrid routing, chia sẻ dịch vụ và điều phối lưu lượng cần kiểm tra. Nhưng **một hub là công cụ định tuyến, không tự là firewall hoặc cơ chế Zero Trust**. Quyền thực tế phụ thuộc route table association/propagation, VPC subnet routes, return paths, inspection path, security groups, identity và application authorization.

Trong phạm vi **SECURITY_NETWORK_SECURITY**, thiết kế an toàn phải **tách Prod/Dev/Mgmt/Shared, áp least privilege, ngăn route leaks và alternate paths, giữ stateful inspection đối xứng, quản lý DNS/IPv6/egress/hybrid, bảo vệ IAM control plane và kiểm chứng multi-AZ/multi-region failover**. Giá trị của hub-and-spoke chỉ được chứng minh bằng **dữ liệu mạng và bằng chứng kiểm thử đầy đủ cả luồng được phép lẫn bị cấm**, không phải bằng sơ đồ topology hay số lượng attachments đang hoạt động.
