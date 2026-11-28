# Private endpoint và private service access trong bảo mật mạng cloud

Một doanh nghiệp chuyển ứng dụng quản lý đơn hàng lên cloud. Ứng dụng chạy trong mạng riêng, còn cơ sở dữ liệu, object storage và dịch vụ quản lý khóa là các dịch vụ được nhà cung cấp cloud vận hành. Đội triển khai muốn workload truy cập các dịch vụ đó **không cần đi qua Internet công khai**, đồng thời không mở cơ sở dữ liệu cho bất kỳ ai chỉ biết URL. Họ bật một tính năng có tên "private endpoint", thấy tên miền dịch vụ trả địa chỉ `10.x.x.x`, rồi kết luận hệ thống đã an toàn.

Kết luận đó chưa đủ. Một kết nối có IP riêng vẫn có thể dùng **credential bị lộ**, đi qua **subnet không đúng quyền**, dùng **DNS cấu hình sai**, hoặc tới dịch vụ vẫn giữ **public endpoint** hoạt động. Ngược lại, một đường tới địa chỉ public của dịch vụ cloud cũng không nhất thiết đi qua Internet mở theo cách nhiều người hình dung: một số nền tảng có cơ chế truy cập qua mạng của nhà cung cấp nhưng **không tạo private endpoint IP**.

**Private endpoint và private service access** là các mô hình cung cấp khả năng kết nối từ mạng tiêu thụ dịch vụ (consumer) đến dịch vụ cloud hoặc dịch vụ của bên cung cấp (producer), thông qua cơ chế mạng riêng/đường truyền do nhà cung cấp kiểm soát. Cần phân biệt **định tuyến, DNS, quyền mạng, IAM, mã hóa và quyền ứng dụng** khi đánh giá mức độ an toàn.

Bài thuộc chương **Bảo mật mạng cloud** của module **SECURITY_NETWORK_SECURITY**. Nội dung liên hệ trực tiếp với phân đoạn VPC/VNet, firewall, VPN/Interconnect, IDS/IPS, TLS/PKI, bảo vệ DNS, network threat modeling và giám sát cloud.

**Nguyên tắc cốt lõi:** **private connectivity không tự đồng nghĩa private authorization, end-to-end encryption hoặc public access đã bị tắt**. Ba điều đó phải được kiểm tra và thực thi độc lập.

## 1. Mục tiêu học tập

Sau bài này, bạn cần có khả năng:

1. Phân biệt **private endpoint, private service access, service endpoint, gateway endpoint, private peering** và **Private Google Access** theo đúng ngữ cảnh.
2. Vẽ đường đi consumer → private connectivity → managed service và xác định các **trust boundaries**.
3. So sánh vai trò của **AWS PrivateLink, Azure Private Link/Private Endpoint, GCP Private Service Connect (PSC)** và **GCP Private Services Access (PSA)**.
4. Thiết kế **DNS private**, route, security group/NSG/firewall, service policy, IAM và TLS cho một ứng dụng dùng dịch vụ cloud.
5. Giải thích vì sao **không thể dựa vào một IP private hoặc một câu trả lời DNS** để chứng minh không có public exposure.
6. Phân tích rủi ro từ public fallback, DNS split-horizon, peering không chuyển tiếp, mở sai IAM, endpoint approval và multi-tenant isolation.
7. Đưa ra ma trận kiểm thử positive/negative, phương án quan sát, xử lý sự cố và quy trình thay đổi có rollback.

## 2. Mô hình consumer và producer: các bên thực sự tin ai?

**Consumer** là VPC/VNet, workload hoặc mạng doanh nghiệp muốn sử dụng dịch vụ. **Producer** là dịch vụ được truy cập: có thể là managed database, cloud service API, storage, service do nhóm khác quản trị, hoặc service được đối tác công bố.

~~~mermaid
flowchart LR
    subgraph CON["Consumer: vùng mạng ứng dụng"]
        APP["Workload / app"]
        DNS["Private DNS / resolver"]
        POLICY["Subnet, firewall, identity"]
    end
    subgraph PROVIDER["Nền tảng mạng cloud"]
        PE["Private endpoint / service access mechanism"]
        FABRIC["Provider network / connection control"]
    end
    subgraph PROD["Producer: dịch vụ đích"]
        SERVICE["Managed service / published API"]
        AUTH["Service IAM / DB auth / application AuthZ"]
    end
    APP --> DNS
    APP --> POLICY
    POLICY --> PE
    PE --> FABRIC
    FABRIC --> SERVICE
    SERVICE --> AUTH
~~~

Sơ đồ là **mô hình logic**, không phải tuyên bố rằng mọi loại private connectivity đều tạo một network interface giống nhau. Một số cơ chế dùng **IP riêng trong subnet consumer**, một số dùng **route tới prefix dịch vụ**, một số dựa vào **kết nối giữa các miền mạng**. Vì thế phải xem tài liệu và loại tài nguyên cụ thể thay vì chỉ tìm từ khóa "private".

### 2.1. Năm trust boundary tối thiểu

| Ranh giới | Câu hỏi an ninh | Ví dụ kiểm soát |
|---|---|---|
| **Workload → VPC/VNet** | Pod/VM nào được khởi tạo kết nối? | Namespace/workload identity, host firewall, security group, network policy |
| **VPC/VNet → endpoint** | Địa chỉ/port nào reachable? Có đường khác không? | Subnet, route, endpoint-level network policy, firewall, egress control |
| **Consumer → producer** | Ai được tạo/duyệt kết nối? Service đích nào thực sự được công bố? | Endpoint connection approval, producer allowlist, service attachment, IAM |
| **Connection → service API** | Danh tính nào được đọc/sửa dữ liệu? | IAM, DB login, OAuth, mTLS, object-level authorization |
| **Operator → control plane** | Ai được tạo endpoint, đổi DNS, bật public access, sửa policy? | RBAC/IAM, change approval, IaC review, cloud audit logs |

Nhãn "private" chủ yếu mô tả một phần **đường kết nối**. Nó không loại bỏ nhu cầu kiểm tra **danh tính workload và quyền tài nguyên**.

## 3. Bảng thuật ngữ đa nền tảng

| Nền tảng và công nghệ | Cơ chế chính | Có tạo IP private tại phía consumer không? | Điểm dễ nhầm |
|---|---|---|---|
| **AWS PrivateLink — interface VPC endpoint** | Endpoint network interfaces trong subnet VPC kết nối đến dịch vụ được hỗ trợ | **Có**, IP private trên endpoint ENI | Khác VPC peering và khác gateway endpoint |
| **AWS gateway VPC endpoint** | Route-table target để VPC truy cập dịch vụ được hỗ trợ như Amazon S3/DynamoDB | **Không phải** interface endpoint ENI | Dùng route table và service prefix list, không phải một NIC private cho mỗi dịch vụ |
| **AWS Gateway Load Balancer endpoint** | Endpoint phục vụ luồng qua thiết bị/giải pháp xử lý lưu lượng theo kiến trúc hỗ trợ | Có endpoint ENI; mục đích khác interface service endpoint | Không coi là một phương thức truy cập mọi managed API |
| **Azure Private Endpoint** | Private IP trong subnet VNet ánh xạ đến một tài nguyên hoặc subresource qua Azure Private Link | **Có** | Service endpoint của Azure là cơ chế khác |
| **Azure Private Link Service** | Producer công bố dịch vụ của mình qua mô hình Private Link Service | Consumer có thể tạo Private Endpoint tới dịch vụ được công bố | Private Link Service phía producer không tự là Private Endpoint của consumer |
| **Azure Virtual Network service endpoint** | Tích hợp nhận dạng subnet/VNet vào quyền truy cập của một số Azure service qua Azure backbone | **Không phải** Private Endpoint IP của dịch vụ | Service có thể vẫn có public-address endpoint |
| **GCP Private Service Connect (PSC) endpoint** | Consumer dùng forwarding rule/private address để truy cập published service hoặc Google APIs được hỗ trợ | **Có**, địa chỉ nội bộ theo cấu hình endpoint | Không phải VPC Network Peering tổng quát |
| **GCP Private Services Access (PSA)** | Kết nối private service networking bằng dải IP được cấp và VPC Network Peering tới mạng dịch vụ được quản lý | Không phải PSC endpoint riêng cho từng dịch vụ | Thường gặp ở Cloud SQL private IP và một số managed services |
| **GCP Private Google Access** | VM không có external IP truy cập các Google APIs được hỗ trợ theo tuyến/điều kiện mạng của Google | Không cần tạo PSC endpoint cho từng API | Không đồng nghĩa PSA hay PSC |

**Định danh cloud-specific là thiết yếu.** Nếu một nhóm nói "bật private service access", hãy hỏi ngay **cloud nào, service nào, loại tài nguyên nào, đường DNS và route nào**.

### 3.1. Ba câu hỏi trước khi chọn công nghệ

1. **Dịch vụ đích hỗ trợ cơ chế nào?** Không phải mọi managed service đều hỗ trợ mọi loại endpoint.
2. **Điểm cuối do ai quản lý?** Cloud vendor, một nhóm nội bộ, một tenant khác hay đối tác?
3. **Mục tiêu là gì?** Loại bỏ public exposure, giới hạn egress, tránh IP overlap, kết nối hybrid, chia sẻ API đa tenant hay giảm bề mặt routing?

## 4. AWS: PrivateLink, interface endpoint và gateway endpoint

### 4.1. Interface VPC endpoint

**AWS PrivateLink** cho phép truy cập dịch vụ được hỗ trợ thông qua **interface VPC endpoint**. Endpoint có **network interface và địa chỉ private** trong các subnet/AZ được cấu hình, kèm các kiểm soát mạng/phê duyệt/chính sách phụ thuộc loại service.

~~~mermaid
flowchart LR
    subgraph VPC["Consumer VPC"]
        VM["EC2 / workload"]
        ENI["Interface endpoint ENI: private IP"]
        RES["VPC DNS resolver"]
    end
    subgraph AWS["AWS provider network"]
        LINK["PrivateLink connection"]
        SVC["AWS service hoặc endpoint service"]
    end
    VM --> RES
    VM -->|"HTTPS / service protocol"| ENI
    ENI --> LINK --> SVC
~~~

Lợi ích điển hình là workload có thể gọi **dịch vụ được hỗ trợ** mà không cần đường egress Internet truyền thống cho luồng này. Tuy nhiên:

- Endpoint phải ở subnet/AZ, VPC và region mà service hỗ trợ; topology và reachability có khác biệt tùy dịch vụ.
- **Security group** gắn với interface endpoint ENI phải cho phép traffic cần thiết; workload side SG, NACL và host firewall vẫn quan trọng.
- Nếu endpoint hỗ trợ **private DNS**, tên service tiêu chuẩn có thể được giải về địa chỉ endpoint private từ phạm vi resolver/VPC phù hợp; điều kiện bật private DNS và DNS support phải được kiểm tra.
- **Endpoint policy** (nếu loại endpoint/service hỗ trợ) bổ sung điều kiện tài nguyên/hành động; nó **không tự thay** IAM identity policy, resource policy hay xác thực của service.
- Khi dùng **endpoint service** được bên thứ ba công bố, phải kiểm tra service name/owner, connection acceptance và dữ liệu gửi tới producer nào.
- Endpoint có thể phát sinh **chi phí theo thời gian hoạt động và lưu lượng**; xem bảng giá thực tế theo region/loại dịch vụ.

### 4.2. Gateway VPC endpoint khác interface endpoint

Với các dịch vụ được hỗ trợ như S3 và DynamoDB, **gateway endpoint** sử dụng **route table** trong VPC để định tuyến traffic tới dịch vụ qua cơ chế của AWS.

~~~text
Workload trong subnet gắn route table
  -> DNS phân giải tên dịch vụ AWS
  -> Route table có entry service prefix list -> gateway endpoint target
  -> AWS service theo policy áp dụng
~~~

Những khác biệt quan trọng:

| Thuộc tính | Interface endpoint | Gateway endpoint |
|---|---|---|
| Private ENI trong subnet | Có | Không theo mô hình interface endpoint |
| Chọn đường chính | Gửi tới IP endpoint/private DNS, network controls | Route table gắn service prefix list/endpoint target |
| Security group gắn endpoint | Có với endpoint ENI | Không gắn SG lên gateway endpoint |
| DNS private override | Có ở những interface service hỗ trợ | Không vận hành như interface endpoint private DNS |
| Truy cập hybrid | Có thể thiết kế qua VPN/Direct Connect và DNS/routing khi hỗ trợ | Gateway endpoint không phải đường endpoint xuyên VPN/peering từ mạng ngoài VPC |
| Chính sách endpoint | Tùy loại service hỗ trợ | Dùng endpoint policy khi hỗ trợ |

**Không kết luận “muốn truy cập private S3 từ on-prem chỉ cần gateway endpoint”**: gateway endpoint phục vụ luồng từ các subnet trong VPC có route phù hợp, không tự mang lưu lượng từ on-premises qua VPN/Direct Connect tới gateway endpoint như một NIC đích. Kiến trúc hybrid phải chọn loại endpoint hoặc proxy/đường dịch vụ thích hợp.

### 4.3. IAM vẫn là điều kiện độc lập

Ví dụ một EC2 instance có route tới S3 qua endpoint **chưa đồng nghĩa** role của instance được đọc mọi bucket. Phải kết hợp:

- **Identity-based IAM policy** của principal gọi API.
- **Bucket/resource policy** khi phù hợp, có thể ràng buộc nguồn kết nối bằng điều kiện endpoint/VPC được hỗ trợ.
- **Endpoint policy** như một lớp hạn chế bổ sung ở những endpoint hỗ trợ.
- Các điều kiện service khác: encryption, object ACL/ownership và audit theo kiến trúc.

Không dùng một điều kiện `aws:SourceVpce` ở resource policy mà chưa xem ảnh hưởng đến admin, console, automation, replication hoặc các đường truy cập hợp lệ khác. Resource policy sai có thể làm gián đoạn production; test canary và có đường khôi phục an toàn.

## 5. Azure: Private Endpoint, Private Link Service và service endpoint

### 5.1. Azure Private Endpoint

**Azure Private Endpoint** là một network interface có **địa chỉ IP private trong VNet** để truy cập một tài nguyên/subresource hỗ trợ Azure Private Link, chẳng hạn một loại storage hoặc database service.

~~~mermaid
flowchart LR
    subgraph VNET["Consumer Azure VNet"]
        APP["VM / AKS workload"]
        DNS["Private DNS Zone + resolver"]
        PE["Private Endpoint NIC"]
    end
    LINK["Azure Private Link"]
    PAAS["PaaS resource / subresource"]
    APP --> DNS
    APP --> PE --> LINK --> PAAS
~~~

Các điểm cần hiểu:

1. **Endpoint connection** có thể yêu cầu approval theo tài nguyên/đơn vị sở hữu/luồng cấp quyền. Không coi việc tạo NIC thành công là nhà cung cấp đã chấp nhận kết nối.
2. Một tài nguyên có thể có **nhiều subresource/group ID** (ví dụ blob, file, dfs tùy dịch vụ). Endpoint cho một loại chưa tự bao phủ mọi endpoint dịch vụ liên quan.
3. **Private DNS zone** được liên kết phù hợp với VNet/resolver giúp tên dịch vụ trả về private IP. Với Storage blob, mẫu private-link DNS zone thường có dạng `privatelink.blob.core.windows.net`; cần kiểm tra đúng loại dịch vụ và DNS theo tài liệu.
4. **Public network access** của tài nguyên cần kiểm tra và hạn chế **riêng**. Tạo Private Endpoint không nhất thiết tự làm public endpoint không truy cập được.
5. **NSG, UDR và private endpoint network policies** có khả năng/hành vi phụ thuộc cấu hình subnet và nền tảng; không khẳng định mọi NSG hoặc route mặc định đều tự áp lên Private Endpoint NIC.
6. Azure RBAC, data-plane credential, storage access key/SAS hoặc database authentication vẫn cần được bảo vệ theo service.

### 5.2. Service endpoint khác Private Endpoint

**Azure Virtual Network service endpoint** hỗ trợ một số dịch vụ Azure và có thể cho phép resource firewall giới hạn quyền theo **subnet/VNet được cấu hình**, với traffic đi theo cơ chế mạng của Azure. Tuy nhiên service endpoint **không tạo IP private của PaaS resource trong consumer subnet** giống Private Endpoint.

| Tiêu chí | Azure service endpoint | Azure Private Endpoint |
|---|---|---|
| Endpoint của dịch vụ có private IP trong subnet consumer | Không theo mô hình Private Endpoint | Có |
| Resource firewall có thể dùng subnet/VNet identity | Có với những service hỗ trợ | Dùng private connection và policy tương ứng |
| DNS private-link zone là yếu tố trọng tâm | Không cùng mô hình | Thường rất quan trọng |
| Truy cập từ on-prem qua private IP endpoint | Không tự đáp ứng yêu cầu đó | Có thể thiết kế qua VPN/ExpressRoute và DNS phù hợp |
| Cần xét public network access | Có | **Có**, độc lập với việc tạo endpoint |

**Azure Private Link Service** lại là khả năng **producer công bố dịch vụ của mình** (thường phía sau kiến trúc load balancing được hỗ trợ) để consumer tạo Private Endpoint. Không gọi Private Link Service là cùng tài nguyên với Private Endpoint.

### 5.3. Một lỗi điển hình: bật private DNS không đủ

Giả sử `orders-db.example.test` là tên ứng dụng tự đặt, CNAME tới FQDN được nhà cung cấp cloud công bố. Khi tạo Private Endpoint, nhà quản trị chỉ tạo private DNS record thủ công trong một VNet, quên link zone vào VNet khác và quên conditional forwarding từ on-prem.

Kết quả:

- Workload trong VNet A có thể nhận private IP.
- Workload trong VNet B vẫn phân giải sang public endpoint hoặc gặp NXDOMAIN tùy DNS path.
- Máy từ on-prem có VPN nhưng hỏi public DNS, nhận câu trả lời không theo ý định.

**Cần kiểm tra kết quả từ từng mạng nguồn**, không chỉ chạy `nslookup` trên một máy ảo gần endpoint.

## 6. GCP: Private Service Connect khác Private Services Access

### 6.1. Private Service Connect (PSC)

**GCP Private Service Connect** cung cấp mô hình consumer kết nối riêng đến **service producer đã công bố** hoặc **Google APIs được hỗ trợ**, thường thông qua endpoint forwarding rule có địa chỉ IP internal tại consumer.

~~~mermaid
flowchart LR
    subgraph CVPC["Consumer VPC"]
        CLIENT["GCE / GKE / workload"]
        PSC["PSC endpoint: internal forwarding rule/IP"]
        CDNS["Private DNS mapping"]
    end
    subgraph PROD["Producer / Google APIs"]
        ATTACH["Service attachment hoặc API bundle"]
        APP["Published service"]
    end
    CLIENT --> CDNS
    CLIENT --> PSC --> ATTACH --> APP
~~~

Một endpoint PSC cho service producer dùng **service attachment** và các điều kiện accept/reject/consumer permission tùy cấu hình producer. PSC cho **Google APIs** có target và DNS semantics khác; không coi mọi PSC endpoint đều đi tới một service attachment do đối tác tạo.

Lưu ý:

- PSC là **kết nối hướng dịch vụ**, không phải kết nối L3 mọi subnet như VPC Network Peering.
- Producer có thể áp cơ chế chấp thuận consumer, giới hạn capacity/connection và policy được sản phẩm hỗ trợ.
- Consumer kiểm soát private IP/DNS, mạng được phép gửi traffic và IAM của API nếu service yêu cầu.
- Muốn kết nối từ on-prem hay mạng khác, phải đánh giá **reachability của endpoint theo cơ chế PSC, routing, hybrid network và DNS**; không suy PSC tự chuyển tiếp qua mọi peering.
- Các biến thể PSC endpoint và PSC backend/published-service architecture khác nhau; không gộp mọi tính năng vào một cấu hình mặc định.

### 6.2. Private Services Access (PSA)

**Private Services Access** là tên của mô hình dùng **private service networking connection**, liên quan **VPC Network Peering** tới mạng do dịch vụ Google quản lý, cùng **dải địa chỉ được dành trước** cho tài nguyên của managed service. Nó thường xuất hiện trong bài toán tạo **private IP cho Cloud SQL** và một số dịch vụ được hỗ trợ.

~~~mermaid
flowchart LR
    subgraph USER["Consumer VPC"]
        VM["Workload"]
        RANGE["Allocated private services IP range"]
    end
    PEER["Private service networking / VPC Peering"]
    subgraph SERV["Service producer VPC / managed services"]
        DB["Cloud SQL private IP / managed resource"]
    end
    VM --> PEER --> DB
    RANGE -.->|"Cấp phát range cho service networking"| DB
~~~

Không thể tạo một Private Services Access connection rồi kỳ vọng nó tự hoạt động như **PSC forwarding rule đến bất kỳ API nào**. PSA có yêu cầu dải prefix, peering, service networking và **quy tắc định tuyến/non-transitivity của VPC Peering** cần được đánh giá theo từng managed service.

### 6.3. Private Google Access (PGA) là mô hình thứ ba

**Private Google Access** cho phép một số workload (ví dụ VM không có external IP) truy cập **Google APIs/services được hỗ trợ** thông qua cơ chế mạng của Google khi subnet, DNS, route và firewall được cấu hình phù hợp.

- PGA **không tạo PSC endpoint cho từng API**.
- Có các phương án DNS/VIP cho Google APIs như `private.googleapis.com` hoặc `restricted.googleapis.com` tùy chính sách và yêu cầu dịch vụ; cần cấu hình đúng trên nền tảng và xác minh service support.
- "Truy cập private" theo tên tính năng không có nghĩa tất cả FQDN đều phân giải ra **địa chỉ RFC1918**.
- API IAM, service perimeter/organization policy (nếu có) và credential vẫn là kiểm soát độc lập.

### 6.4. Bảng tránh nhầm các dịch vụ GCP

| Nhu cầu | Cơ chế nên đánh giá | Điều không nên suy |
|---|---|---|
| VM private gọi Google API | Private Google Access hoặc PSC cho Google APIs theo thiết kế | "Có private IP VM là đủ; không cần DNS/route" |
| Managed database có private IP qua service networking | Private Services Access khi dịch vụ dùng cơ chế này | "PSA là một PSC endpoint" |
| Consumer cần published service của producer | Private Service Connect endpoint/service attachment | "Nó cho route toàn VPC producer" |
| Kết nối toàn hai VPC ở layer 3 | Peering/VPN/Interconnect tùy nhu cầu | "PSC thay được mọi topology peering" |
| Từ on-prem tới cloud managed service | Hybrid route + DNS + cơ chế service tương thích | "Chỉ cần bật private setting là on-prem tự tới được" |

## 7. So sánh AWS, Azure và GCP qua một kịch bản

**Bài toán:** API xử lý đơn hàng cần truy cập một managed service (storage/database) qua đường riêng, và ứng dụng không được phép dùng public endpoint của service đó.

| Mối quan tâm | AWS | Azure | GCP |
|---|---|---|---|
| Chọn dịch vụ phù hợp | Interface endpoint/PrivateLink, gateway endpoint hoặc cơ chế khác theo service | Private Endpoint qua Azure Private Link nếu PaaS hỗ trợ | PSC endpoint hoặc PSA/PGA tùy service và access path |
| Điểm kết nối ở consumer | ENI private cho interface; route-table target cho gateway | Private Endpoint NIC/private IP | PSC forwarding rule/private IP; PSA private service networking |
| DNS | Private DNS/VPC resolver/Resolver rules tùy loại | Private DNS Zone, VNet links, conditional forwarders | Private Cloud DNS, PSC DNS, API DNS/PSA semantics |
| Mạng và egress | Security groups, NACL, routes, policies | NSG/UDR/subnet PE network policies khi áp dụng, firewall | VPC firewall, routes, service attachment/peering policies |
| Giới hạn public access | IAM/resource policy và trạng thái public endpoint của service | Public network access + firewall rules của tài nguyên | Public IP/authorized networks/service policy theo managed service |
| Identity | IAM principal + service policy/credential | Entra/RBAC hoặc data-plane identity/credential theo dịch vụ | IAM/service account và service authentication |
| Hybrid | VPN/Direct Connect + đúng endpoint/DNS route | VPN/ExpressRoute + private DNS/routing | Cloud VPN/Interconnect + connectivity/DNS theo PSC/PSA |

**Không có công thức một-một** giữa các cột. Tính năng tương tự về mục tiêu **không bảo đảm giống nhau về DNS, billing, approval, region, AZ hoặc security enforcement**.

## 8. DNS là điều kiện sống còn của private endpoint

### 8.1. Đường DNS mong muốn

Giả sử ứng dụng gọi `orders-db.example.test`; tên này được hệ thống quản lý DNS ánh xạ tới tên dịch vụ chính thức đã cấu hình private connectivity. Đường mong muốn:

~~~mermaid
sequenceDiagram
    participant W as App trong private subnet
    participant R as VPC/VNet resolver
    participant Z as Private DNS policy / zone
    participant E as Private endpoint / private service
    participant S as Managed service
    W->>R: Resolve tên dịch vụ
    R->>Z: Chọn view/zone theo nguồn và policy
    Z-->>R: Private address/record được quản lý
    R-->>W: DNS answer phù hợp
    W->>E: Kết nối tới địa chỉ được cấp phép
    E->>S: Luồng qua private connectivity
    S-->>W: Kết quả theo identity/TLS/service policy
~~~

Đây là **luồng ví dụ cho endpoint có private-IP DNS mapping**. Với AWS gateway endpoint hoặc GCP PSA/PGA, cơ chế định tuyến/DNS có thể khác; không bắt buộc mọi kết nối private phải trả về IP của một **endpoint NIC**.

### 8.2. Sai lầm phổ biến về private DNS

| Tình huống | Triệu chứng | Rủi ro |
|---|---|---|
| Private DNS zone không được link đúng VPC/VNet | Một mạng dùng private IP, mạng khác thấy public IP/NXDOMAIN | Public fallback hoặc outage |
| Resolver on-prem không forward đúng zone | VPN/ExpressRoute đã có nhưng FQDN không phân giải đúng | Người dùng thử truy cập public endpoint |
| CNAME/subresource sai | Storage blob chạy, file/dfs chưa chạy | Thiếu route/private endpoint riêng cho subresource |
| Overlapping private zone | Private record che mất các tên dịch vụ khác | NXDOMAIN hoặc sai đích ở cùng zone |
| Hardcode private IP | Endpoint được tạo lại/đổi AZ/DR gây lỗi | Fragile failover và khó kiểm toán |
| Client dùng DoH riêng / custom resolver | Không dùng split DNS của doanh nghiệp | Không thấy private records, rò tên hoặc đi ngoài policy |
| Record TTL/cache cũ | Sau migration vẫn dùng public/private answer cũ | Kết nối nhầm tuyến và sự cố khó tái hiện |
| DNS đúng nhưng firewall sai | Tên trả private IP nhưng TCP timeout | Ngộ nhận là DNS lỗi khi thực chất SG/NSG/route không cho phép |

**Đừng suy "DNS trả 10.x" là đủ chứng minh packet đến đúng producer.** IP đó có thể thuộc endpoint khác, một private load balancer, một dải overlap hoặc một dịch vụ chưa được phê duyệt. Cần liên hệ **resource ID, endpoint connection, route và service audit**.

### 8.3. Split-horizon DNS cho hybrid network

Khi có on-prem và nhiều VPC/VNet:

~~~mermaid
flowchart TD
    ON["On-prem client"] --> FOR["On-prem resolver"]
    FOR -->|"Conditional forward zone được phê duyệt"| CLOUD["Cloud inbound resolver / DNS forwarding"]
    CLOUD --> PZ["Private zone / service DNS"]
    PZ --> IP["Private IP / đúng service path"]
    ON --> VPN["Site-to-site VPN / Direct Connect / ExpressRoute / Interconnect"]
    VPN --> IP
~~~

DNS forwarding và **đường network** là hai mặt riêng:

- Resolver phải **có quyền trả lời** tên private cho network nguồn.
- Client phải **có route và firewall permission** đến endpoint IP hoặc mạng dịch vụ.
- Dải địa chỉ on-prem và cloud không được chồng lấn ngoài kiến trúc NAT/VRF được thiết kế.
- Nếu dùng outbound resolver forwarding, phải chặn DNS recursion loop và **không public hóa private zone**.
- Khi dịch vụ có nhiều region/endpoint, policy DR và TTL cần được thử trước.

## 9. Routing, peering và giới hạn non-transitivity

Private endpoint không phải là một **router chung** nối VPC/VNet consumer với mọi mạng của producer. Cần xác minh:

1. Endpoint có reachable từ **đúng nguồn**: same VPC, peered VPC, transit network, on-prem hoặc VPN client không?
2. Route lookup và return path có hợp lệ không?
3. Transit Gateway, VNet peering, hub-and-spoke, Cloud Router hoặc NCC có tham gia và được hỗ trợ không?
4. Cơ chế endpoint có giới hạn **region, AZ, subnet hoặc account/project/subscription** nào?
5. Security group/NSG/firewall có áp lên **endpoint IP** hay chỉ workload interface?
6. Với peering, có **non-transitivity** làm mạng A không thể tự qua B tới mạng C không?

### 9.1. Peering là hai bên, không tự thành transit

VPC/VNet peering truyền thống thường không tự cho phép transitive routing. Ví dụ:

~~~text
On-prem -- VPN --> Network A -- Peering --> Service network B

Không được tự kết luận:
  "Có đường tới Network A" => "đi xuyên peering tới mọi địa chỉ B".

Phải xác minh:
  - Cơ chế dịch vụ có hỗ trợ truy cập hybrid hay không?
  - Route import/export, reserved range và return path?
  - Policy service/network có cho phép network nguồn?
~~~

Đặc biệt với **GCP Private Services Access**, các giới hạn VPC Network Peering, route advertisement và phạm vi managed service có ý nghĩa lớn. Với **PSC**, endpoint là kết nối dịch vụ, nên không thể dùng nó để vận chuyển tùy ý lưu lượng L3 từ consumer sang mọi subnet của producer.

### 9.2. IP overlap và nhiều tenant

Trong môi trường hybrid hoặc đa tenant, hai mạng có thể cùng dùng `10.0.0.0/16`. Một endpoint private trong một VPC/VNet không tự giải quyết sự chồng lấn địa chỉ:

- IPAM phải lưu **project/account/subscription, VPC/VNet, VRF và prefix**.
- DNS phải trả địa chỉ **reachable từ đúng network**.
- Đường đi có thể cần NAT, proxy/service endpoint hoặc renumbering, tùy architecture.
- Audit phải gắn traffic với **tenant, workload identity, endpoint resource ID và thời gian**, không chỉ IP.

## 10. Network controls và identity: bảo vệ theo nhiều lớp

### 10.1. Chọn nguồn được phép kết nối tới endpoint

| Lớp | Câu hỏi | Hướng kiểm soát |
|---|---|---|
| **Workload identity** | Đây có phải đúng service account/role không? | IAM, workload identity, runtime hardening |
| **Endpoint network reachability** | Chỉ subnet/workload nào tới được IP/cổng private? | SG/NSG/VPC firewall, subnet policy, firewall appliance |
| **Producer acceptance** | Đúng consumer nào được kết nối? | Approval, service attachment/connection policy |
| **Service API authorization** | Principal được thao tác tài nguyên nào? | IAM resource policy, DB roles, API authz |
| **Encryption/authentication** | TLS có xác minh đúng peer hay không? | PKI, SAN/hostname validation, mTLS khi phù hợp |
| **Egress restrictions** | Workload có thể bỏ private path và dùng Internet không? | Public access disable, egress firewall/proxy, DNS policy |

**Một IAM allow không tạo route**; **một route đến private IP không cấp IAM allow**. Cả hai đều cần cho hoạt động được phép, nhưng thuộc những boundary khác nhau.

### 10.2. Public network access phải được xử lý riêng

Một số PaaS resource cho phép đồng thời:

- **Private endpoint/connection** cho nguồn trong mạng private.
- **Public endpoint** hoặc quy tắc cho phép từ Internet/public source theo cấu hình.

Nếu mục tiêu yêu cầu **chỉ private**, cần tắt hoặc hạn chế public access **ngay tại service** nơi sản phẩm hỗ trợ, kết hợp firewall và IAM. Không chỉ đổi DNS từ public IP sang private IP rồi kết luận không ai gọi được public FQDN/IP.

### 10.3. TLS trên private connectivity vẫn quan trọng

Đường private không thay **TLS peer authentication**, mã hóa dữ liệu in-transit và quyền truy cập:

- Client phải xác minh **đúng FQDN/certificate SAN** theo PKI của managed service. Trỏ DNS tới private IP không đồng nghĩa nên bỏ hostname verification.
- Không "fix" lỗi TLS bằng cách đặt `verify=false`, bỏ SNI hay chấp nhận mọi certificate.
- Với managed database, kiểm tra server certificate và kết hợp database authentication/authorization.
- Với private API do đối tác công bố, dùng mTLS hoặc application authentication khi thích hợp.
- Edge/proxy nếu terminate TLS sẽ tạo **một trust boundary mới**; kiểm tra kết nối giữa các hop.

### 10.4. Chính sách deny-by-default có ngoại lệ rõ

Ví dụ logical access matrix:

| Nguồn → đích | Quyền dự kiến |
|---|---|
| App subnet → private database endpoint | Cho phép port DB cụ thể, service identity được phê duyệt |
| App subnet → object storage private service path | Cho phép API cần thiết, IAM hạn chế bucket/container |
| Guest/BYOD → private database endpoint | Từ chối |
| App subnet → public database endpoint | Từ chối khi yêu cầu private-only |
| Admin role → endpoint management plane | Chỉ qua IAM/MFA/change approval |
| Cross-tenant workload → endpoint tenant khác | Từ chối nếu không có quan hệ chia sẻ được phê duyệt |
| CI/CD → create endpoint/DNS policy | Chỉ pipeline có quyền theo vai trò và audit |

**Nguyên tắc quan sát:** test deny không được dựa duy nhất vào "timeout". Đích có thể không hoạt động; cần đối chiếu firewall decision, IAM deny hoặc cloud control-plane state.

## 11. Private endpoint không giải quyết mọi bài toán egress

### 11.1. NAT gateway còn cần không?

Nếu workload truy cập một tập dịch vụ cloud qua private endpoints, **những luồng đó** có thể không cần NAT/Internet egress. Nhưng workload còn có thể cần:

- Public software repositories và cập nhật OS/packages.
- Public SaaS hoặc API đối tác không hỗ trợ private connectivity.
- Identity endpoints, certificate revocation, telemetry hoặc service bootstrap được thiết kế khác.
- Các service phụ trợ chưa có endpoint hoặc chưa có DNS/route phù hợp.

Vì vậy không xóa NAT/egress mặc định chỉ vì đã tạo một endpoint. Trước khi bỏ, phải lập **dependency inventory và negative/positive tests**. Ngược lại, nếu muốn môi trường hoàn toàn không có Internet egress, phải kiểm soát các đường khác như public subnet, IPv6 internet gateway, proxy, transit routes và DNS.

### 11.2. Vùng riêng không thay Zero Trust

Một endpoint private dùng chung cho toàn VPC có thể reachable từ nhiều workload. Nếu chỉ dựa IP nguồn hoặc một service account rộng, một workload bị chiếm quyền vẫn có thể gọi service. Các lớp bù trừ:

1. Identity ngắn hạn và secret management phù hợp.
2. Service-specific IAM/resource policies hạn chế hành động và tài nguyên.
3. Network microsegmentation, security groups hoặc workload network policy.
4. Audit các lệnh đọc/sửa dữ liệu, object-level authorization khi cần.
5. Giám sát egress bất thường và khởi tạo endpoint/connection trái phép.

## 12. Threat modeling: 18 tình huống rủi ro

| ID | Rủi ro | Kịch bản | Kiểm soát phòng vệ |
|---|---|---|---|
| C01 | **Public endpoint vẫn bật** | App đi private nhưng attacker ngoài mạng gọi public resource | Tắt/giới hạn public access, public-path negative test |
| C02 | **DNS public fallback** | Private zone không link, workload phân giải public IP | Private DNS/forwarding, endpoint-specific tests, egress deny |
| C03 | **Sai endpoint/service owner** | Consumer kết nối tới producer/attachment giả hoặc không phê duyệt | Xác minh service ID, producer approval và IaC review |
| C04 | **IAM quá rộng** | App role được đọc mọi bucket/DB dù route private | Least privilege, resource policy, IAM Access analysis |
| C05 | **Endpoint policy không có tác dụng như kỳ vọng** | Tưởng policy thay IAM hoặc service không hỗ trợ | Xác minh loại endpoint/service và effective permissions |
| C06 | **Port reachability quá rộng** | Mọi subnet đều tới được interface private | SG/NSG/firewall scoped source, workload identity |
| C07 | **Peering/transit hiểu sai** | On-prem không tới private IP dù VPN kết nối | Route support, peering limits, return path |
| C08 | **Overlap RFC1918** | Một IP private thuộc hai miền định tuyến | IPAM per VRF/VPC, NAT/renumber/proxy khi cần |
| C09 | **Private DNS zone che tên hợp lệ** | NXDOMAIN hoặc answer sai do zone rộng | Review DNS scope, resolver tests theo nguồn |
| C10 | **TLS verification bị bỏ** | Endpoint IP đúng nhưng peer certificate không được xác thực | Hostname/SAN/CA validation, mTLS khi phù hợp |
| C11 | **Credential bị đánh cắp** | Attacker từ workload hợp lệ truy cập dữ liệu | IAM, secrets, rotation, audit và anomaly detection |
| C12 | **Cross-tenant exposure** | Endpoint/connection hoặc policy dùng sai tenant | Producer approval, resource binding, app-level tenant AuthZ |
| C13 | **Control-plane privilege escalation** | User có quyền tạo endpoint/đổi public network access tùy ý | Least-privilege IAM/RBAC, approval, cloud audit |
| C14 | **Endpoint bị xóa/thay** | IP/DNS stale, phụ thuộc một region/AZ | IaC drift detection, DNS lifecycle, HA/DR tests |
| C15 | **Không giám sát service data plane** | Chỉ xem DNS và endpoint state, bỏ qua API data access | Service audit, DB logs, network flow logs |
| C16 | **Chồng sai hybrid DNS** | On-prem query vòng lặp hoặc truy vấn rò ra public resolver | Conditional forwarding, split DNS, resolver health |
| C17 | **Chi phí hoặc quota bất ngờ** | Tạo endpoint ở quá nhiều subnet/AZ, traffic hairpin | Capacity/quotas, cost estimation, topology review |
| C18 | **IPv6/đường thứ cấp bypass** | IPv4 dùng private endpoint nhưng client dùng public IPv6 hoặc proxy | Dual-stack routing/DNS/egress tests, endpoint capabilities |

### 12.1. Một chuỗi sự cố giả định

~~~mermaid
sequenceDiagram
    participant A as Workload trong private subnet
    participant D as DNS resolver
    participant P as Public endpoint
    participant E as Private endpoint
    A->>D: Resolve DB FQDN
    D-->>A: Public address vì zone chưa liên kết
    Note over A: Egress firewall/NAT vẫn cho public access
    A->>P: Kết nối theo public path
    P-->>A: Service chấp nhận credential hợp lệ
    Note over E: Private endpoint có tồn tại nhưng không được sử dụng
~~~

**Bài học:** giao diện quản trị cloud hiển thị endpoint trạng thái "Available/Approved" **không chứng minh application traffic sử dụng nó**. Phải kiểm tra DNS và network path thật, đồng thời xác minh public path được đóng nếu yêu cầu.

## 13. Thiết kế theo nguồn sự thật và Infrastructure as Code

### 13.1. Những thuộc tính nên lưu trong inventory

| Thuộc tính | Ví dụ | Tác dụng |
|---|---|---|
| Cloud/provider | AWS / Azure / GCP | Tránh áp sai cơ chế endpoint |
| Account/project/subscription | `prod-app` | Kiểm soát ownership và boundary |
| VPC/VNet, subnet, AZ/region | `app-vpc`, `app-subnet-a` | Định tuyến và HA |
| Consumer workload | `orders-api` | Scope của người gọi |
| Producer service ID | Service resource ARN/ID/link | Xác minh đích thật |
| Endpoint mechanism | Interface endpoint / Azure PE / PSC / PSA... | Chính sách phù hợp loại |
| Private IP/DNS name/zone | `10.90.12.40`, zone nội bộ | Truy vấn, troubleshooting |
| Routing/security | SG/NSG/firewall/VPC firewall/route owner | Quyền đường mạng |
| AuthN/AuthZ | IAM role, DB principal, mTLS policy | Quyền tài nguyên |
| Public access policy | Disabled hoặc exceptions đã duyệt | Không có đường ngoài dự kiến |
| Approval/audit | Owner, change ticket, trạng thái connection | Truy vết control plane |
| Cost/quota/DR | Endpoint count, traffic, region backup | Vận hành và phục hồi |

### 13.2. Pseudo-policy để review, không phải file cloud thực thi

~~~yaml
# Đặc tả minh họa dùng để thảo luận thiết kế, không phải AWS/Azure/GCP schema.
connection:
  workload: orders-api
  environment: production
  cloud: provider-selected-after-service-support-review
  consumer:
    network: app-vpc
    subnetClass: application-private
    identity: orders-api-workload
  producer:
    service: managed-orders-database
    resourceOwner: database-platform-team
    privateConnectivityRequired: true
  endpoint:
    type: approved-service-specific-mechanism
    connectionApproval: required-when-supported
    dns:
      useCanonicalServiceFqdn: true
      privateResolutionRequiredFromApprovedSources: true
    allowedSourceWorkloads:
      - orders-api
    allowedServicePorts:
      - approved-database-port
  publicAccess:
    disabledWhereSupported: true
    fallbackToPublic: false
  security:
    requireTlsPeerVerification: true
    enforceLeastPrivilegeServiceIdentity: true
    denyCrossTenantByDefault: true
  operations:
    owner: network-security-team
    auditChanges: true
    testDnsAndNetworkPath: true
    testIamDeny: true
    testFailoverAndRollback: true
~~~

`approved-database-port`, `app-vpc` và các tên tài nguyên là **placeholder**. Không thể áp file này trực tiếp vào Terraform, AWS CloudFormation, Azure Bicep hoặc GCP Deployment Manager. Nó mô tả **những quyết định phải được chuyển thành resource và policy cụ thể**, có kiểm tra trạng thái.

### 13.3. Pipeline thay đổi có kiểm soát

~~~mermaid
flowchart LR
    REQ["Yêu cầu dịch vụ/private access"] --> REVIEW["Review service support, identity, cost, DNS, routing"]
    REVIEW --> APPROVE["Producer/owner approval"]
    APPROVE --> IAC["IaC tạo endpoint, DNS, network policies"]
    IAC --> TEST["Positive + negative tests"]
    TEST --> OBS["Audit/flow logs và service logs"]
    OBS --> DRIFT["Drift/rotation/DR review"]
~~~

Trong nhiều cloud, **tạo endpoint** và **chấp nhận connection** là hai hành động độc lập. Một pipeline IaC không nên tuyên bố triển khai thành công chỉ vì resource được tạo nếu backend connection còn pending, DNS chưa phù hợp hoặc IAM deny mọi request hợp lệ.

## 14. Vận hành: tính availability, cost và quotas

### 14.1. High availability không tự có ở mọi endpoint

Tùy loại dịch vụ/region, có thể cần endpoint ở **nhiều subnet/AZ**, private DNS hoặc cơ chế load balancing/failover riêng. Kiểm tra:

- Endpoint ENI/NIC/forwarding rule nằm ở region, AZ/subnet nào?
- Khi một AZ lỗi, workload ở AZ khác còn tới được service qua đường mong muốn không?
- Service producer có trạng thái healthy không, có giới hạn connection/consumer quota không?
- Private DNS có trả đúng endpoint còn sẵn sàng hoặc có stale cache không?
- Nếu failover cross-region, tên miền, chứng chỉ và IAM có thay đổi không?

Một "endpoint available" là trạng thái của tài nguyên kết nối, **không chứng minh ứng dụng, database và IAM đều sẵn sàng**.

### 14.2. Chi phí cần đo

Đối với những mô hình có tính phí, chi phí có thể phụ thuộc:

- Thời gian tồn tại endpoint/connection.
- Dữ liệu qua endpoint theo chiều và loại dịch vụ.
- Cross-zone/cross-region traffic và NAT/egress nếu vẫn còn.
- DNS resolver endpoints/forwarding, hybrid VPN hoặc Interconnect.
- Số lượng endpoint phục vụ nhiều subnet, region, project và tenant.

Không dùng một mức giá cố định để suy ngân sách; billing model, quotas và khả năng miễn phí **thay đổi theo cloud, dịch vụ và region**. Cần đo thực tế, forecast peak và lưu owner/cost center.

### 14.3. Telemetry đa lớp

| Nguồn | Tín hiệu nên thu | Lý do |
|---|---|---|
| Cloud audit/control plane | Endpoint create/delete/update, connection approval, public access change | Phát hiện sửa quyền hoặc thay endpoint |
| DNS resolver logs | Query source/network, qname, response/rcode, resolver path | Bắt public fallback hoặc NXDOMAIN |
| VPC/VNet flow logs | Source/dest, port, action khi có, bytes | Xác minh traffic vào endpoint và network denies |
| Firewall/NSG/SG-related data | Policy version, allow/deny evidence | Khoanh vùng network boundary |
| Service audit logs | API principal, resource, operation, result | Xác minh quyền dữ liệu, không chỉ đường mạng |
| TLS/application telemetry | Peer identity, handshake error, DB/API status, latency | Phân biệt PKI và ứng dụng |
| Inventory/IaC | Endpoint IDs, private DNS zones, owners, quotas | Drift, tài nguyên thừa, sai tenant |

Flow logs có thể **không ghi mọi packet hoặc mọi quyết định endpoint** tùy dịch vụ và cấu hình sampling. Không yêu cầu một nguồn log chứng minh tất cả; phối hợp **cloud audit + DNS + network + service logs**.

## 15. Kiểm thử an toàn bằng các lệnh chỉ đọc

Chỉ thử trên workload/môi trường được ủy quyền. Ví dụ tên `orders-db.example.test` và IP private là giả định; các lệnh dưới đây **không thay DNS, route, firewall hay tài nguyên cloud**.

### 15.1. Linux: DNS và kết quả route

~~~bash
# Đọc DNS theo resolver mặc định nếu các tiện ích đã được cài đặt.
getent ahostsv4 orders-db.example.test
getent ahostsv6 orders-db.example.test

# Kiểm tra địa chỉ và route đang có.
ip -br address
ip -4 route show
ip -6 route show

# Nếu lab trả private IP 10.90.12.40, kiểm tra quyết định route tới IP đó.
ip route get 10.90.12.40

# Đọc resolver per-link khi hệ thống dùng systemd-resolved.
resolvectl status
~~~

Lệnh `getent` tuân thủ name service configuration của hệ thống và có thể chịu ảnh hưởng của nhiều nguồn tên, không phải chỉ DNS. `ip route get` mô tả quyết định route của OS trong ngữ cảnh hiện tại, **không chứng minh packet đã thực sự tới managed service** hoặc service IAM đã cấp quyền.

### 15.2. Windows: DNS và route

~~~powershell
# Xem địa chỉ, default gateway và DNS của endpoint.
Get-NetIPConfiguration
Get-DnsClientServerAddress

# Đọc câu trả lời A/AAAA từ resolver được cấu hình.
Resolve-DnsName -Name "orders-db.example.test" -Type A
Resolve-DnsName -Name "orders-db.example.test" -Type AAAA

# Xem route hiện hành, chỉ đọc.
Get-NetRoute | Select-Object DestinationPrefix, NextHop, InterfaceAlias, RouteMetric
~~~

Trên máy có nhiều interface, VPN hoặc proxy, cần kiểm tra **đường đi của tiến trình ứng dụng thật**. Một câu trả lời DNS từ laptop quản trị không thay cho kiểm thử từ subnet/VM/pod tiêu thụ dịch vụ.

### 15.3. Đọc trạng thái endpoint trên cloud control plane

Ví dụ lệnh quan sát **chỉ đọc** khi đã có quyền hợp lệ:

~~~bash
# AWS CLI: liệt kê các VPC endpoints trong account/region được chọn.
aws ec2 describe-vpc-endpoints

# Azure CLI: liệt kê Private Endpoints trong resource group được phép.
az network private-endpoint list --resource-group <RESOURCE_GROUP>

# GCP CLI: liệt kê forwarding rules trong region (có thể gồm PSC).
gcloud compute forwarding-rules list --regions=<REGION>
~~~

`<RESOURCE_GROUP>` và `<REGION>` là **placeholder**, phải được thay bằng tên thực. Kết quả lệnh có thể chứa **resource IDs, IP, service names, approval status** nhạy cảm; giới hạn chia sẻ và lưu log. Lệnh `gcloud compute forwarding-rules list` **không tự lọc chỉ PSC**; cần đối chiếu target/loại forwarding rule và service attachment trong dữ liệu thực.

Danh sách endpoint trên control plane **không chứng minh** DNS, network path hay service authentication đã hoạt động. Cần kết hợp kiểm thử ứng dụng và quyền.

### 15.4. TLS/peer validation

Nếu dịch vụ private sử dụng TLS, hãy thử handshake bằng client chính thức hoặc thư viện thích hợp với service protocol, và bảo đảm client **xác minh đúng hostname/certificate**. Không kết nối thẳng tới private IP rồi tắt hostname verification để tránh SAN mismatch.

Khi cần thử bằng một TLS lab riêng:

~~~bash
# Chỉ chạy với TLS server lab đã được cấp quyền và có CA hợp lệ.
openssl s_client \
  -connect 127.0.0.1:8443 \
  -servername private-api.example.test \
  -verify_hostname private-api.example.test \
  -verify_return_error \
  -CAfile /path/to/lab-root-ca.pem \
  -brief
~~~

Lệnh trên **không tự thử endpoint cloud thật** và không đo IAM. Với database managed service, cần dùng driver chính thức và kiểm tra TLS settings theo dịch vụ, không mặc định coi mọi service hoạt động như HTTPS trên cổng 443.

## 16. Ma trận positive/negative tests cho private connectivity

| ID | Nguồn/hoàn cảnh | Phép kiểm thử | Kết quả mong muốn |
|---|---|---|---|
| P01 | App subnet được phép | Resolve canonical service name | DNS trả record phù hợp private path đã thiết kế |
| P02 | App subnet được phép | Kết nối đúng port tới private service | Connection và ứng dụng thành công với principal hợp lệ |
| N01 | Workload không có service IAM | Cùng network/path nhưng gọi API | **IAM/DB authorization DENY** |
| N02 | Guest/untrusted subnet | Kết nối private endpoint | **Network policy DENY** theo kiến trúc |
| N03 | Public Internet source | Gọi public endpoint của private-only service | **Public network access DENY** khi mục tiêu yêu cầu |
| P03 | DNS resolver khác đã được phê duyệt | Resolve FQDN từ VNet/VPC/site thứ hai | Đúng private answer và path nếu được phép |
| N04 | Site không được cấp quyền | Resolve hoặc dùng endpoint private | Không tạo quyền truy cập trái phép; DNS có thể khác theo policy |
| P04 | On-prem qua VPN/Interconnect được hỗ trợ | Private service access | Route, DNS và quyền đúng, return path hoạt động |
| N05 | On-prem không có route hoặc không được phép | Thử tới private service | Bị ngăn theo policy, không public fallback |
| N06 | Service endpoint/connection chờ approval | Thử dùng trước khi duyệt | Không được coi connection usable/approved |
| P05 | Endpoint service khác AZ khi hỗ trợ | Failover theo thiết kế | Service vẫn reachable theo SLO mục tiêu |
| N07 | Đổi DNS zone/link trong lab | Quan sát public fallback | Cảnh báo hoặc chặn, không lặng lẽ chuyển public path |
| N08 | Endpoint đã bị xóa | App còn stale DNS cache | Fail có kiểm soát, không gửi dữ liệu sang địa chỉ sai |
| N09 | IAM principal của tenant A | Gọi tài nguyên tenant B | Bị từ chối ở IAM/app |
| P06 | Cloud audit | Tạo/duyệt endpoint qua luồng hợp lệ | Có owner, ticket, resource ID, log |
| N10 | User không có IAM tạo endpoint | Thử thao tác IaC trong lab | Control-plane permission DENY |
| P07 | TLS client hợp lệ | Kết nối managed service với đúng hostname | Certificate/peer validation PASS |
| N11 | TLS endpoint trình chứng chỉ sai | Kết nối ứng dụng | Client từ chối, không bỏ hostname verify |
| P08 | Storage/DB private path | Ghi nhận flow+API logs | Có correlation network/identity/service activity |
| N12 | IPv6/public secondary path | Thử truy cập public service không được phép | Không bypass private-only policy |
| N13 | Cross-tenant/cloud project | Dùng sai PSC attachment/Private Link resource | Connection/resource access bị từ chối |
| P09 | DR hoặc region migration | Kiểm tra endpoint và DNS mới | Không mất AuthN/AuthZ và không lộ public path |
| N14 | Direct endpoint IP không khớp hostname | Gọi mà bỏ qua tên dịch vụ | Không tắt TLS validation để ép hoạt động |

### 16.1. Đọc kết quả cho đúng

- **DNS private PASS** không đồng nghĩa **service authorization PASS**.
- **TCP port reachable** không chứng minh **TLS/DB identity** hợp lệ.
- **TCP timeout** không đủ chứng minh firewall deny nếu service đang lỗi.
- **Public IP không xuất hiện trong DNS answer** không chứng minh public endpoint đã tắt.
- **Private Endpoint approved** không chứng minh client dùng endpoint đó.
- **Cloud control-plane RBAC DENY** không thay data-plane IAM/DB authorization.

Mỗi test cần lưu **network source, time, endpoint resource ID, DNS answer, route/flow evidence, principal, service result và policy version** ở mức cần thiết, không để lộ secrets/token.

## 17. Chẩn đoán sự cố theo từng boundary

| Triệu chứng | Nguyên nhân thường gặp | Bằng chứng hữu ích |
|---|---|---|
| DNS trả public IP ngoài ý định | Private zone link/forwarder thiếu, resolver khác | QNAME, resolver path, private DNS zone và TTL |
| NXDOMAIN với tên private | Private zone che tên nhưng record thiếu | Zone scope, record set, conditional forwarding |
| DNS private đúng, TCP timeout | SG/NSG/firewall, route, endpoint approval, service listener | Flow logs, route, endpoint state, listener health |
| TCP vào được, TLS validation lỗi | SNI/SAN/cert chain, IP-only connection | TLS library logs, certificate metadata |
| TLS OK nhưng 403/permission denied | IAM/resource policy/DB role hoặc service identity | Service audit và principal context |
| Một subnet/AZ chạy, subnet khác lỗi | Endpoint placement, SG, subnet policy, DNS/route | Source-specific traces, endpoint ENIs/NICs |
| On-prem lỗi, cloud VM chạy | DNS conditional forwarding, hybrid route, peering limitation | On-prem DNS result, VPN/ExpressRoute path |
| Chỉ một cloud project/tenant lỗi | Approval, IAM, endpoint binding khác | Resource IDs, connection status, audit |
| Service vẫn public reachable | Public network access chưa disable, firewall exceptions | Resource public access config và negative test |
| Workload bị gián đoạn sau rotation | Endpoint resource replaced, IP cache, service certificate đổi | IaC diff, DNS TTL, SLO, PKI logs |
| Chi phí tăng đột biến | Endpoint count, data processing, cross-zone traffic | Billing + per-endpoint usage |
| Private access bật nhưng workload vẫn dùng NAT | Route/DNS chưa trỏ private hoặc service không hỗ trợ | NAT flow, resolver logs, API endpoint target |

### 17.1. Quy trình khoanh vùng nhanh

~~~mermaid
flowchart TD
    A["Ứng dụng không gọi được managed service"] --> B{"Endpoint/connection đúng loại & approved?"}
    B -->|"Không"| P["Kiểm tra loại service, producer ID, IAM/approval"]
    B -->|"Có"| D{"DNS answer đúng theo source?"}
    D -->|"Không"| Z["Private zone/link/forwarder/cache"]
    D -->|"Có"| N{"Network route/flow tới đích đúng?"}
    N -->|"Không"| R["Routes, subnet SG/NSG/firewall, hybrid reachability"]
    N -->|"Có"| T{"TLS/peer validation PASS?"}
    T -->|"Không"| C["Certificate/SAN/SNI/trust"]
    T -->|"Có"| I["Kiểm tra service IAM/DB AuthZ, quota, app health"]
    P --> END["Sửa có phê duyệt, regression và monitor"]
    Z --> END
    R --> END
    C --> END
    I --> END
~~~

**Không sửa lỗi kết nối bằng cách bật public access, mở `0.0.0.0/0` hay đặt `verify=false`** mà chưa đánh giá rủi ro và xác định nguyên nhân. Những đường tắt này có thể biến sự cố availability thành sự cố bảo mật.

## 18. Quy trình triển khai private service access có thể kiểm toán

### Bước 1 — Xác định service và cơ chế hỗ trợ

Ghi service, phiên bản/tier/region, loại private connectivity hỗ trợ trên cloud đó, giới hạn availability/approval và ai quản lý producer. Không chọn "PrivateLink" cho mọi trường hợp chỉ vì tên quen thuộc.

### Bước 2 — Dựng data flow và threat model

Vẽ workload, VPC/VNet, private endpoint hoặc peering, DNS, hybrid connectivity, firewall, IAM và backend. Đánh dấu **public endpoint** và mọi đường egress thay thế.

### Bước 3 — Quy hoạch IP, DNS và routing

Kiểm tra IPAM, prefix overlap, reserved ranges (đặc biệt PSA khi áp dụng), VPC/VNet links, DNS forwarding, IPv4/IPv6, on-prem source và response route. Xác định phương án DR trước khi tạo DNS record tĩnh.

### Bước 4 — Tạo kết nối theo IaC và phê duyệt

Tạo endpoint/connection dưới quyền tối thiểu; yêu cầu producer chấp nhận nếu service đòi approval. Đối chiếu resource IDs, target service attachment và endpoint policy, tránh phê duyệt nhầm producer.

### Bước 5 — Áp network restrictions, identity và TLS

Cho phép chỉ nguồn/cổng cần thiết, hạn chế public network access riêng, xác minh IAM/DB/application role và bật TLS peer verification. Cấu hình audit logging bảo vệ dữ liệu nhạy cảm.

### Bước 6 — Kiểm thử hai chiều

Positive: workload và principal hợp lệ vào được service. Negative: subnet/tenant/principal không được phép bị từ chối; public endpoint không reachable nếu yêu cầu; không có DNS/NAT fallback; các mạng hybrid và IPv6 có kết quả đúng.

### Bước 7 — Canary rollout và rollback

Thử một workload hoặc subnet trước. Ghi baseline latency, error rate, API denied rate, DNS, flow logs và billing; xác định tiêu chí rollback. Nếu phải revert DNS/endpoint, tránh tạo đường public fallback trái chính sách.

### Bước 8 — Giám sát drift và vòng đời tài nguyên

Theo dõi endpoint approvals, private DNS updates, route/SG/NSG/IAM changes, service public access state, chi phí/quota, certificate rotation và region DR. Xóa endpoint không còn dùng theo quy trình owner/retention.

## 19. Bài tập tình huống: Database đã có private endpoint mà vẫn truy cập công khai được

**Bối cảnh giả định:** Doanh nghiệp có API `orders-api` chạy trong private subnet `10.90.10.0/24` và một managed database. Họ đã tạo endpoint private có IP `10.90.12.40`. Workload trong subnet app kết nối DB thành công, nhưng bộ giám sát phát hiện database vẫn có public endpoint hoạt động. Một chi nhánh nối VPN cũng không truy cập được DB.

| Quan sát | Câu hỏi cần đặt |
|---|---|
| Workload trong app subnet phân giải DB thành `10.90.12.40` | Chứng minh được đường/private service và identity nào? |
| Chi nhánh hỏi DNS trả public IP | Conditional forwarding hoặc DNS private scope đã đúng chưa? |
| DB public firewall vẫn cho một dải IP rộng | Có vi phạm yêu cầu private-only không? |
| Một workload khác trong cùng VPC nhưng role không có DB quyền | Network reachability có đồng nghĩa được login DB? |
| Private endpoint vừa được approve | Approval có chứng minh producer đúng và app traffic thực sự sử dụng nó? |
| Thêm một service mới vào cloud | Có phải cùng cơ chế private endpoint không, hay cần loại khác? |

### 19.1. Yêu cầu thiết kế

1. Vẽ ít nhất **năm trust boundaries** từ `orders-api` tới DB, ghi DNS, network route và service authentication.
2. Phân biệt việc **DNS trả private IP**, **TCP reachability**, **TLS peer identity** và **DB authorization**.
3. Đề xuất cách làm rõ và loại bỏ public endpoint không được phép **mà không làm hỏng automation hợp lệ**.
4. Giải thích vì sao VPN nối được vào VPC/VNet nhưng chi nhánh chưa có private DNS/route tới managed service.
5. Lập tối thiểu ba positive và ba negative tests, gồm public-path test và một IAM/DB deny test.
6. Nếu chọn AWS, Azure hoặc GCP, xác định **đúng service mechanism** thay vì dùng tên chung "private access".

### 19.2. Gợi ý đối chiếu

- **DNS/private IP** chỉ là dấu hiệu đường mong muốn. Phải đối chiếu **endpoint ID/target service, route/flow và service logs** để chứng minh traffic thực.
- Endpoint được approved **không tự tắt public network access**; cần cập nhật service firewall/public access theo quy trình change và xem các principal hợp lệ từ CI/CD, admin, backup hoặc DR có bị ảnh hưởng không.
- Chi nhánh cần **hybrid reachability, return path và private DNS forwarding**. Với GCP PSA và một số cơ chế peering, xem giới hạn non-transitive routing; với AWS gateway endpoint, không suy có thể dùng làm destination từ on-prem.
- Identity vẫn độc lập: principal không có quyền DB không nên login được dù TCP port reachable và TLS hợp lệ.
- Positive: workload hợp lệ kết nối DB, DNS nội bộ trả đúng, site hybrid được cấp quyền kết nối. Negative: principal không phép bị DB deny, nguồn Internet/public không vào DB, mạng tenant/guest không được phép không vào private endpoint.
- Khi chọn công nghệ: AWS interface/gateway endpoint **tùy service**; Azure Private Endpoint khác service endpoint; GCP PSC khác PSA/PGA. Luôn xác minh service support và producer ownership.

## 20. Checklist private endpoint và private service access

- [ ] Đã xác định **cloud, service và loại cơ chế**: AWS interface/gateway endpoint, Azure Private Endpoint/service endpoint, GCP PSC/PSA/PGA.
- [ ] Phân biệt consumer/producer, network permission, service IAM và application authorization.
- [ ] Xác định rõ TLS endpoint, DNS FQDN, hostname validation và connection approval.
- [ ] Kiểm kê account/project/subscription, VPC/VNet, subnet, region/AZ, tenant và resource owner.
- [ ] Biết endpoint là IP NIC/forwarding rule, route-table target hay private service networking peering tùy công nghệ.
- [ ] Có IPAM kiểm tra prefix overlap, allocated PSA ranges và các tuyến VPN/on-prem/cloud khác.
- [ ] Private DNS/link/forwarding được thử từ **mọi nguồn được phép**, không chỉ từ một VM.
- [ ] Không hardcode endpoint IP nếu DNS/lifecycle có thể thay đổi và service hỗ trợ FQDN chuẩn.
- [ ] Không mặc định DNS private đồng nghĩa network path hoặc service identity đúng.
- [ ] Endpoint connection approved đúng producer; service attachment/resource binding được kiểm tra.
- [ ] Có SG/NSG/VPC firewall/subnet policies phù hợp đúng endpoint loại và đường dữ liệu thật.
- [ ] Kiểm tra khả năng áp NSG/UDR cho Azure Private Endpoint theo subnet policies, không giả định tự hiệu lực.
- [ ] Public network access của managed service được tắt/giới hạn riêng khi yêu cầu private-only.
- [ ] Không để fallback qua public DNS/NAT/Internet egress trái chính sách khi private endpoint lỗi.
- [ ] IAM/resource policy/DB roles/service account theo least privilege, không dựa duy nhất IP nguồn.
- [ ] Không bỏ TLS hostname/certificate verification khi chuyển từ public IP sang private IP.
- [ ] Đã xét hybrid connectivity, peering non-transitivity, return path và consumer reachability.
- [ ] Đã kiểm thử IPv4/IPv6, dual-stack và các đường public/secondary khi sản phẩm hỗ trợ.
- [ ] Positive tests cho workload hợp lệ và negative tests cho principal, subnet, tenant, Internet không phép.
- [ ] Có audit control plane, DNS/flow logs, service API/DB logs và correlation theo resource IDs.
- [ ] Đánh giá HA/DR, region/AZ, quotas, cost theo thời gian/lưu lượng và khả năng phục hồi.
- [ ] Mọi endpoint, DNS, IAM, route và public access changes đi qua IaC/review/change ticket.
- [ ] Đã có rollback không mở lại public path trái yêu cầu và kiểm tra sau failover.
- [ ] Không kết luận bảo mật chỉ vì private endpoint hiển thị "Available", DNS trả RFC1918 hoặc TCP kết nối thành công.

**Ghi nhớ:** **Private endpoint và private service access giúp thu hẹp hoặc định hướng đường kết nối tới dịch vụ cloud, không tự cấp quyền sử dụng dịch vụ đó.** Kiến trúc an toàn phải xác minh **đúng cơ chế từng cloud, đúng producer, DNS và routing từ từng nguồn, network policy, IAM/DB authorization, TLS peer identity, public exposure thực tế và khả năng quan sát/khôi phục**. Chỉ khi các lớp này cùng đáp ứng policy, "private" mới trở thành một đặc tính bảo mật có thể kiểm chứng thay vì chỉ là tên của một tài nguyên.
