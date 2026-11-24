# Private endpoint, DNS riêng và đường mạng tới dịch vụ

Một ứng dụng Spring Boot có thể gọi API bằng HTTPS đúng cách nhưng vẫn không đáp ứng yêu cầu bảo vệ dữ liệu nếu traffic đi qua đường mạng công cộng ngoài dự kiến. **Private endpoint** đưa một điểm truy cập dịch vụ vào mạng riêng của workload; **private DNS** khiến hostname dịch vụ phân giải tới địa chỉ riêng; **routing và firewall** quyết định gói tin có đi được tới đích hay không.

Ba lớp này phải hoạt động đồng thời. Chỉ tạo private endpoint chưa đủ: ứng dụng cần nằm trong mạng có đường tới endpoint, DNS phải trả đúng IP riêng, route/NSG/security group/firewall phải cho phép kết nối, và dịch vụ phải chấp nhận endpoint. Khi kết nối thành công, TLS và xác thực ứng dụng vẫn tiếp tục được thực hiện như trước.

Bài thuộc chương **Bảo vệ dữ liệu** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua thư viện tương ứng, bao gồm danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử và so sánh provider. Trọng tâm bài là thiết kế đường truy cập riêng từ workload tới dịch vụ, hiểu DNS riêng và xác minh kết nối từ đúng môi trường chạy.

## 1. Mục tiêu và tình huống thực tế

Giả sử order-service chạy trên Kubernetes trong mạng riêng và cần:

- Đọc cấu hình từ Azure App Configuration.
- Lấy secret từ Azure Key Vault.
- Đọc object từ Amazon S3 trong một workload AWS.
- Gọi Google Cloud Storage hoặc một API nội bộ được publish qua Private Service Connect.
- Không gửi traffic dịch vụ qua public internet theo chính sách của tổ chức.

Sau bài này, bạn có thể:

1. Phân biệt private endpoint với service endpoint, NAT gateway, VPN và public endpoint.
2. Mô tả đường đi từ pod/VM tới private IP của dịch vụ qua DNS, route và firewall.
3. Cấu hình Azure Private Link/Private Endpoint và private DNS zone.
4. Phân biệt AWS interface VPC endpoint (PrivateLink) với gateway endpoint, đặc biệt với S3.
5. Giải thích Google Cloud Private Service Connect (PSC), endpoint, backend và DNS.
6. Cấu hình custom DNS, hybrid DNS và kiểm tra phân giải từ workload.
7. Giữ nguyên hostname/TLS verification khi traffic đi qua private IP.
8. Kiểm thử DNS, TCP, TLS, authorization và xử lý lỗi theo từng lớp.

~~~mermaid
flowchart LR
    A["Spring Boot pod / VM"] --> B["DNS resolver"]
    B --> C["FQDN dịch vụ"]
    C --> D["Private DNS record"]
    D --> E["Private IP endpoint"]
    E --> F["Route + firewall / security group"]
    F --> G["Private Link / PrivateLink / PSC"]
    G --> H["Managed service"]
    H --> I["TLS + authentication + authorization"]
~~~

**Nguyên tắc quan trọng:** private endpoint giải quyết **đường mạng**. Nó không thay thế TLS, Microsoft Entra ID, AWS IAM, Google Cloud IAM hoặc authorization của dịch vụ.

## 2. Phân biệt các khái niệm mạng

| Khái niệm | Chức năng | Ví dụ |
| --- | --- | --- |
| **Public endpoint** | Hostname/IP truy cập dịch vụ qua mặt phẳng mạng công khai | vault-name.vault.azure.net phân giải public IP từ mạng ngoài |
| **Private endpoint** | Giao diện mạng/IP riêng để kết nối tới dịch vụ qua private link | Azure Private Endpoint, AWS interface VPC endpoint, GCP PSC endpoint |
| **Private DNS** | Phân giải hostname thành IP riêng trong phạm vi mạng được liên kết | privatelink.vaultcore.azure.net |
| **Service endpoint (Azure)** | Mở rộng định danh subnet tới dịch vụ Azure qua backbone, dịch vụ vẫn có public endpoint | Azure Storage service endpoint |
| **Gateway endpoint (AWS)** | Thêm route tới dịch vụ AWS qua route table, không tạo ENI | S3/DynamoDB gateway endpoint |
| **NAT gateway** | Cho workload private subnet đi outbound tới đích public qua NAT | Tải package hoặc gọi API public |
| **VPN / ExpressRoute / Direct Connect / Cloud Interconnect** | Kết nối mạng riêng giữa cloud và mạng doanh nghiệp/on-premises | Hybrid connectivity |
| **Private Service Connect (GCP)** | Endpoint/backends riêng để consumer truy cập Google APIs hoặc service được publish | PSC endpoint tới service attachment |

### 2.1. Private endpoint không đồng nghĩa public access đã bị tắt

Tạo private endpoint thường bổ sung một đường truy cập riêng. Việc public endpoint có còn được phép hay không phụ thuộc cấu hình network access của dịch vụ:

- Với Azure App Configuration, tài liệu dịch vụ nêu khi thêm private endpoint, request dữ liệu qua public network mặc định bị từ chối; cần kiểm tra network setting thực tế.
- Với Azure Key Vault, cần cấu hình Public network access = Disabled nếu chính sách yêu cầu chỉ truy cập qua private endpoint.
- Với AWS/GCP, endpoint riêng không tự biến mọi đường public khác thành không tồn tại; IAM, endpoint policy, service firewall và DNS/routing cần được cấu hình theo mục tiêu.

Không kết luận “đã có private endpoint nên dữ liệu không thể truy cập qua internet”. Hãy kiểm tra **public network access**, firewall và policy của chính resource.

### 2.2. Private endpoint không thay thế quyền dữ liệu

Một request đi tới private IP vẫn có thể nhận 401/403 nếu danh tính không có quyền:

- Azure: Entra ID token + Azure RBAC/data-plane role hoặc access policy phù hợp.
- AWS: IAM role/policy, resource policy, endpoint policy và điều kiện VPC endpoint nếu có.
- Google Cloud: service account/workload identity + IAM role; PSC không tự cấp quyền đọc bucket/API.

Đường mạng riêng và authorization là hai lớp độc lập. Nếu DNS và TCP đều đúng nhưng dịch vụ trả 403, điều tra quyền trước khi thay DNS.

## 3. Đường đi của một request từ Spring Boot

Ví dụ ứng dụng dùng SDK để gọi FQDN Azure Key Vault là demo-checkout-kv.vault.azure.net:

1. Spring Cloud Azure/Azure SDK nhận endpoint hostname từ cấu hình.
2. JVM gọi DNS resolver của môi trường container/VM.
3. DNS trả về CNAME và A record theo private DNS zone, cuối cùng là IP riêng của private endpoint.
4. TCP mở kết nối tới IP riêng trên port 443.
5. NSG, route, firewall và network interface cho phép traffic.
6. Private Link chuyển request tới Key Vault service.
7. TLS xác minh certificate theo hostname gốc demo-checkout-kv.vault.azure.net.
8. SDK gửi bearer token; Key Vault kiểm tra quyền data-plane.
9. Secret response trở về ứng dụng.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant DNS as Private DNS resolver
    participant PE as Private endpoint IP
    participant FW as NSG / Firewall / Route
    participant Svc as Managed service
    App->>DNS: Resolve vault-name.vault.azure.net
    DNS-->>App: CNAME + private A record
    App->>PE: TCP 443
    PE->>FW: Kiểm tra đường mạng
    FW->>Svc: Private Link
    Svc-->>App: TLS response + HTTP status
    Note over App,Svc: TLS hostname và IAM/RBAC vẫn được kiểm tra
~~~

Nếu một bước thất bại, cần chẩn đoán đúng lớp:

- DNS trả public IP: cấu hình private DNS/link/forwarding.
- DNS trả private IP nhưng timeout: route, NSG, firewall, subnet hoặc endpoint state.
- TCP thành công nhưng TLS lỗi: certificate chain, hostname, proxy/TLS inspection.
- TLS thành công nhưng 403: IAM/RBAC hoặc service policy.
- 404: resource, subresource, hostname hoặc tên object/secret.

## 4. DNS riêng: phần thường gây lỗi nhất

### 4.1. FQDN vẫn là tên dịch vụ chuẩn

Ứng dụng nên tiếp tục gọi hostname chính thức của dịch vụ:

~~~text
https://demo-checkout-kv.vault.azure.net
https://demo-checkout-config.azconfig.io
https://s3.us-east-1.amazonaws.com
https://storage.googleapis.com
~~~

Private DNS làm cho **cùng hostname** phân giải tới địa chỉ private khi truy vấn từ mạng được cấu hình. Không sửa source code để thay hostname bằng private IP và không tùy tiện dùng hostname nội bộ privatelink trực tiếp.

Lý do:

- TLS certificate được cấp cho hostname dịch vụ chuẩn.
- SDK thường xây dựng Host header, SNI, signing scope hoặc endpoint metadata dựa trên hostname chính thức.
- DNS là lớp chuyển hostname thành IP; nó cho phép giữ nguyên ứng dụng và endpoint chuẩn.

**Ngoại lệ:** một số kiến trúc PSC hoặc dịch vụ publish riêng có thể yêu cầu custom endpoint/domain. Khi đó, phải cấu hình client endpoint và bảo đảm Host/SNI đúng theo tài liệu dịch vụ.

### 4.2. DNS resolution trong mạng riêng

Một câu trả lời DNS có thể đi qua nhiều alias:

~~~text
demo-checkout-kv.vault.azure.net
       |
       | CNAME
       v
demo-checkout-kv.privatelink.vaultcore.azure.net
       |
       | A record trong private DNS zone
       v
10.20.4.7
~~~

Từ workload nằm trong VNet có private DNS zone liên kết, hostname chuẩn sẽ kết thúc ở private IP. Từ máy ngoài VNet, public DNS có thể trả public ingress IP. Điều đó không chứng minh private endpoint không tồn tại; chỉ cho biết resolver đang dùng không có private zone view.

### 4.3. Split-horizon DNS

**Split-horizon DNS** trả lời khác nhau tùy nơi truy vấn:

| Nơi truy vấn | Kết quả mong đợi |
| --- | --- |
| VM/pod trong VNet đã link private zone | Private IP endpoint |
| On-premises qua DNS forwarding đúng | Private IP endpoint |
| Laptop ngoài VPN/VNet | Public DNS answer hoặc không có private route |
| Workload ở VNet khác chưa link/forward | Có thể nhận public IP |

Vì vậy, nslookup từ laptop lập trình không đủ chứng minh Spring Boot trong AKS/App Service/EC2/GCE có đường mạng đúng. Hãy kiểm tra **ngay trong pod/VM hoặc execution environment tương đương**.

### 4.4. Custom DNS và hybrid DNS

Nếu VNet dùng custom DNS server, private DNS zone có thể không được resolver tự động truy vấn. Cần thiết kế forwarding:

- DNS server nội bộ forward zone privatelink.* phù hợp tới Azure DNS Private Resolver hoặc resolver được cấu hình.
- Với AWS, Route 53 Resolver inbound/outbound endpoints và Resolver rules giúp tích hợp DNS giữa VPC và on-premises.
- Với GCP, Cloud DNS inbound server policy/forwarding và DNS peering có thể hỗ trợ hybrid name resolution.
- Không tạo wildcard forwarding rộng hơn phạm vi cần thiết nếu nó gây xung đột với các zone nội bộ hiện có.

Kiểm tra cả **DNS query path** và **network path** tới resolver. Một private zone đúng nhưng không được query từ subnet của workload vẫn không có tác dụng.

## 5. Azure Private Link và Private Endpoint

### 5.1. Mô hình hoạt động

Azure Private Endpoint là một network interface trong subnet của VNet, nhận private IP và liên kết với một **Private Link resource** cùng target subresource. Traffic từ workload tới IP này được chuyển qua Azure Private Link tới dịch vụ.

Các bước tổng quát:

1. Chọn resource Azure cần truy cập.
2. Chọn đúng **subresource** (ví dụ Blob, File, Key Vault vault, App Configuration configurationStores).
3. Chọn VNet/subnet để tạo private endpoint.
4. Chờ connection state là **Approved**.
5. Tạo/liên kết private DNS zone và xác minh A record.
6. Kiểm tra NSG/UDR/firewall và đường hybrid nếu có.
7. Sau khi test thành công, cấu hình dịch vụ chặn public access nếu mục tiêu là private-only.

Connection có thể Pending khi cần resource owner phê duyệt thủ công. Endpoint ở trạng thái Pending/Rejected/Disconnected không được coi là kết nối hoạt động.

### 5.2. Private DNS zone thường gặp

| Azure service | Private DNS zone |
| --- | --- |
| App Configuration | privatelink.azconfig.io |
| Key Vault | privatelink.vaultcore.azure.net |
| Storage Blob | privatelink.blob.core.windows.net |
| Storage File | privatelink.file.core.windows.net |
| Azure SQL Database | privatelink.database.windows.net |
| Cosmos DB SQL API | privatelink.documents.azure.com |

Tên zone phụ thuộc dịch vụ, subresource và cloud environment. Với Azure Government/China hoặc sovereign cloud, suffix khác public Azure; luôn tra bảng Private Endpoint DNS chính thức của cloud đang triển khai.

### 5.3. App Configuration qua private endpoint

Với Azure App Configuration:

- Tạo private endpoint target store với subresource configurationStores.
- Private DNS zone chuẩn public Azure là privatelink.azconfig.io.
- Ứng dụng vẫn dùng endpoint chuẩn, ví dụ https://demo-checkout-config.azconfig.io.
- Không cấu hình Spring Cloud Azure endpoint thành hostname có privatelink subdomain.
- Khi private DNS hoạt động, hostname chuẩn được phân giải qua alias tới IP private endpoint.
- Với geo-replication, mỗi replica có endpoint/DNS record riêng; cân nhắc private endpoint cho từng region để giữ khả năng truy cập khi một vùng gặp sự cố.

Ví dụ Spring YAML vẫn dùng endpoint bình thường:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
~~~

AZURE_APPCONFIG_ENDPOINT chứa FQDN chuẩn của store. Không đưa private IP vào endpoint property. DNS và network do nền tảng xử lý.

### 5.4. Key Vault qua private endpoint

Với Azure Key Vault:

- Private DNS zone chuẩn public Azure là privatelink.vaultcore.azure.net.
- Private endpoint phải ở trạng thái Approved.
- Workload dùng hostname chuẩn https://<vault-name>.vault.azure.net/.
- Private DNS zone phải link tới VNet chứa workload hoặc có forwarding tương ứng.
- Có thể đặt **Public network access = Disabled** sau khi xác minh workload và quy trình quản trị đều truy cập được qua private path.

Ví dụ Spring Cloud Azure:

~~~yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - name: checkout-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              secret-keys:
                - payments-api-token
~~~

Property endpoint dùng FQDN chuẩn. Cơ chế private link không làm thay đổi secret-keys, Managed Identity hoặc Key Vault Secrets User role. Private endpoint chỉ cung cấp đường tới service.

### 5.5. Public DNS vẫn có thể trả lời

Một điểm dễ gây hiểu nhầm: Key Vault FQDN vẫn có thể được public DNS phân giải và có CNAME privatelink ngay cả khi public network access đã bị tắt. DNS trả lời không đồng nghĩa request public được phép. Khi public access Disabled, service từ chối data-plane request qua public ingress; private DNS overlay trong VNet mới trả private IP endpoint.

Vì vậy, **không dùng việc public DNS vẫn phân giải được làm bằng chứng public access còn mở**. Hãy kiểm tra network setting và thử kết nối từ một mạng ngoài không có private route.

### 5.6. Azure service endpoint khác private endpoint

| Tiêu chí | Service endpoint | Private endpoint |
| --- | --- | --- |
| Địa chỉ đích trong VNet | Dịch vụ vẫn có public service IP | Private IP của NIC trong subnet |
| DNS | Thường vẫn dùng public service FQDN/public IP | DNS private override về private IP |
| Phạm vi | Một số Azure services | Các dịch vụ hỗ trợ Private Link |
| Cách giới hạn | Service firewall có thể cho phép subnet identity | Private Link connection + network controls |
| Dữ liệu đi | Azure backbone sau khi rời subnet, vẫn tới public service endpoint | Private Link tới resource |
| Tích hợp DNS hybrid | Ít phức tạp hơn | Cần private DNS/forwarding đúng |

App Configuration hỗ trợ private endpoint; tài liệu dịch vụ nêu **không hỗ trợ service endpoint**. Đừng áp dụng hướng dẫn service endpoint của Storage cho App Configuration.

## 6. AWS PrivateLink và VPC endpoints

### 6.1. Interface VPC endpoint

AWS PrivateLink cho phép VPC consumer truy cập dịch vụ qua interface VPC endpoint. AWS tạo **Elastic Network Interface (ENI)** trong từng subnet được chọn và gán private IP. Traffic tới service được DNS phân giải về private IP của ENI rồi đi qua PrivateLink.

Các thành phần:

- VPC và subnet của workload.
- Interface endpoint gắn với service name và region.
- Endpoint ENI trong một hoặc nhiều Availability Zones.
- Security group gắn endpoint ENI cho phép inbound từ workload (thường TCP 443).
- Network ACL và route phù hợp.
- Private DNS nếu muốn dùng hostname service mặc định.

### 6.2. Private DNS cho interface endpoint

Khi bật Private DNS và VPC có DNS resolution/hostnames enabled, AWS tạo hidden private hosted zone để hostname regional mặc định của service phân giải về private IP endpoint ENI.

Ví dụ ứng dụng vẫn gọi AWS SDK với regional service endpoint:

~~~java
S3Client s3 = S3Client.builder()
        .region(Region.US_EAST_1)
        .build();
~~~

Nếu dịch vụ/endpoint hỗ trợ private DNS và cấu hình đúng, SDK dùng hostname mặc định; DNS bên trong VPC trả private IP endpoint. Không cần hard-code endpoint ENI IP vào Java.

Nếu private DNS tắt, có thể phải dùng endpoint-specific DNS name do AWS cung cấp. Cách này có thể yêu cầu cấu hình endpoint riêng trong SDK và phải xác minh hostname/signing behavior.

### 6.3. S3: gateway endpoint và interface endpoint

Amazon S3 có cả hai loại VPC endpoint:

| Tiêu chí | S3 Gateway endpoint | S3 Interface endpoint |
| --- | --- | --- |
| Kiểu | Route table target | ENI private IP qua AWS PrivateLink |
| DNS | Dùng DNS name S3 thông thường; route table đưa traffic qua gateway endpoint | Có endpoint DNS riêng; có thể bật private DNS |
| On-premises | Không hỗ trợ truy cập trực tiếp từ on-prem qua gateway endpoint | Có thể truy cập qua Direct Connect/Site-to-Site VPN theo thiết kế |
| VPC peering/Transit Gateway | Gateway endpoint không được chia sẻ qua peering/TGW theo cách đó | Interface endpoint có các lựa chọn kết nối mạng rộng hơn, theo điều kiện dịch vụ |
| Chi phí endpoint | Không tính phí gateway endpoint | Có phí theo giờ và dữ liệu xử lý |
| Cấu hình | Route table và endpoint policy | Security group, subnet, endpoint policy và DNS |

Nếu chỉ workload trong VPC cần S3, gateway endpoint thường là lựa chọn đơn giản và không tính phí endpoint. Nếu cần truy cập từ on-premises hoặc VPC khác theo kịch bản được hỗ trợ, đánh giá interface endpoint.

### 6.4. Security group và endpoint policy

AWS PrivateLink không bỏ qua kiểm soát mạng:

- Security group của endpoint ENI phải cho phép inbound từ nguồn phù hợp, ví dụ TCP 443 từ security group của workload.
- Network ACL phải cho phép traffic hai chiều cần thiết.
- Endpoint policy có thể giới hạn principal/action/resource được gọi qua endpoint, nhưng không thay IAM policy hay resource policy.
- Với interface endpoint, chọn subnet ở nhiều AZ để tăng khả năng chịu lỗi.
- Theo dõi endpoint state, ENI, DNS entries và quota.

Không mở inbound TCP 443 từ toàn bộ CIDR nếu chỉ một nhóm workload cần truy cập. Sử dụng security group reference hoặc CIDR hẹp theo kiến trúc.

## 7. Google Cloud Private Service Connect

### 7.1. PSC endpoint là gì?

**Private Service Connect (PSC)** cho phép consumer VPC truy cập Google APIs hoặc dịch vụ được publish trong VPC khác qua địa chỉ IP nội bộ của consumer network. Endpoint thường được tạo bằng forwarding rule trỏ tới:

- Service attachment của một service producer.
- Bundle Google APIs toàn cục.
- Regional hoặc multi-regional Google API được hỗ trợ.

Với dịch vụ publish riêng, producer có thể đặt service sau load balancer và công bố service attachment. Consumer tạo PSC endpoint trong VPC của mình, dùng internal IP để kết nối.

### 7.2. Endpoint, backend và interface khác nhau

| Thành phần PSC | Hướng dùng |
| --- | --- |
| **Endpoint** | Consumer dùng forwarding rule/internal IP để kết nối layer 4 tới service |
| **Backend** | Consumer đặt load balancer của mình trước PSC để có custom URL, advanced traffic management hoặc failover |
| **Interface** | Cho phép producer network khởi tạo kết nối tới consumer network thông qua network attachment; mô hình giao tiếp khác endpoint |

Đối với một Spring Boot client cần gọi service đã publish, PSC endpoint thường là điểm bắt đầu. Nếu cần consumer-side load balancer, custom certificate/domain hoặc failover phức tạp, đánh giá PSC backend.

### 7.3. DNS cho PSC

Endpoint có internal IP. Client có thể gọi hostname được DNS ánh xạ tới IP đó:

~~~text
orders-api.internal.example.com  ->  10.40.2.15
~~~

Với service attachment có cấu hình DNS domain, Google Cloud/Service Directory có thể tạo DNS entry cho endpoint. Với Google APIs, PSC có thể cung cấp tên dạng:

~~~text
storage-<endpoint-name>.p.googleapis.com
compute-<endpoint-name>.p.googleapis.com
~~~

Client Java cần hỗ trợ custom endpoint nếu sử dụng tên p.googleapis.com. Nếu client không thể cấu hình endpoint tùy chỉnh hoặc API không có record tự động, có thể tạo private DNS zone cho tên dịch vụ mặc định như googleapis.com và trỏ domain/A record tới endpoint IP theo hướng dẫn Google.

**Giữ Host header và SNI đúng:** với custom library, Google yêu cầu Host header/SNI là hostname dịch vụ hợp lệ, ví dụ storage.googleapis.com hoặc tên SERVICE-ENDPOINT.p.googleapis.com. Không thay URL thành IP thuần nếu điều đó làm sai TLS hostname và API routing.

### 7.4. Firewall và region

- Egress firewall của consumer VPC phải cho phép tới internal IP của PSC endpoint.
- Endpoint và published service có yêu cầu region; kiểm tra điều kiện cùng region của endpoint/service và tùy chọn global access nếu có.
- Với hybrid network qua Cloud VPN/Cloud Interconnect, cần route quảng bá endpoint IP và cấu hình DNS forwarding tới private zone.
- PSC endpoint không tự cấp IAM permission; service account của ứng dụng vẫn cần role truy cập API/resource.
- Kiểm tra consumer accept list/service attachment approval nếu producer yêu cầu phê duyệt.

### 7.5. PSC và Private Google Access

Hai khái niệm này không giống nhau:

- **Private Google Access** cho phép VM không có external IP truy cập một số Google APIs qua hạ tầng Google.
- **Private Service Connect for Google APIs** cung cấp internal endpoint IP do consumer kiểm soát và DNS có thể hướng API traffic tới endpoint đó.
- **PSC published service** cho phép consumer VPC truy cập dịch vụ do producer publish.

Chọn theo yêu cầu về IP, DNS, kiểm soát endpoint, routing và mô hình service. Không gọi tất cả các phương án “private endpoint” rồi bỏ qua khác biệt.

## 8. So sánh ba nền tảng

| Khía cạnh | Azure Private Link | AWS PrivateLink | Google Cloud PSC |
| --- | --- | --- | --- |
| Điểm truy cập | Private Endpoint/NIC trong subnet | Interface VPC endpoint/ENI | Forwarding rule với internal IP (endpoint) |
| DNS | Private DNS zone và VNet link | Hidden AWS-managed private hosted zone hoặc Route 53 Resolver | Cloud DNS/Service Directory hoặc private zone tùy use case |
| Dịch vụ đích | Azure PaaS và service publish hỗ trợ | AWS services và service endpoint publish | Google APIs và service attachment |
| Network policy | NSG, UDR, firewall, endpoint approval | Security group, NACL, route, endpoint policy | VPC firewall egress, routes, service attachment accept list |
| Hybrid | VPN Gateway, ExpressRoute, DNS Private Resolver | Direct Connect, Site-to-Site VPN, Route 53 Resolver | Cloud VPN, Cloud Interconnect, Cloud DNS forwarding |
| Ứng dụng | Thường giữ FQDN dịch vụ chuẩn | Private DNS cho phép giữ regional service hostname | Có thể cần custom endpoint/DNS tùy PSC API/service |
| Identity | Entra ID + Azure RBAC | IAM role/policy | Service account/workload identity + IAM |

**Khác biệt cần nhớ:** Azure và AWS thường cung cấp cơ chế private DNS để client tiếp tục dùng hostname service chuẩn; Google PSC cho Google APIs có thể dùng tên p.googleapis.com hoặc DNS override theo service. Luôn kiểm tra yêu cầu endpoint của SDK đang dùng.

## 9. Tích hợp Spring Boot: cấu hình network ở đâu?

Spring Boot không có một property chung để bật private link cho tất cả cloud. Private endpoint được tạo và cấu hình ở **network/control plane**; ứng dụng dùng endpoint hostname và SDK client như bình thường.

### 9.1. Azure SDK/Spring Cloud Azure

Ví dụ App Configuration và Key Vault:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
      keyvault:
        secret:
          property-sources:
            - name: checkout-vault
              endpoint: "${AZURE_KEYVAULT_ENDPOINT}"
              secret-keys:
                - payments-api-token
~~~

Các biến môi trường phải chứa FQDN chuẩn:

~~~text
AZURE_APPCONFIG_ENDPOINT=https://demo-checkout-config.azconfig.io
AZURE_KEYVAULT_ENDPOINT=https://demo-checkout-kv.vault.azure.net/
~~~

Private DNS zone đưa hai FQDN này về private IP từ VNet của workload. Không cần thay đổi dependency Spring chỉ để dùng Private Endpoint. Credential/Managed Identity và Azure RBAC vẫn phải cấu hình như bình thường.

### 9.2. AWS SDK for Java 2.x

Với AWS service có interface endpoint và Private DNS enabled, giữ region và service client mặc định:

~~~java
S3Client s3 = S3Client.builder()
        .region(Region.US_EAST_1)
        .credentialsProvider(DefaultCredentialsProvider.create())
        .build();
~~~

SDK dùng regional endpoint, resolver trong VPC trả private IP endpoint. Với S3 gateway endpoint, route table quyết định đường đi; code SDK vẫn dùng hostname S3 thông thường.

Nếu phải dùng endpoint-specific DNS, SDK hỗ trợ endpoint override:

~~~java
S3Client s3 = S3Client.builder()
        .region(Region.US_EAST_1)
        .endpointOverride(URI.create("https://vpce-example.s3.us-east-1.vpce.amazonaws.com"))
        .build();
~~~

Ví dụ endpoint override chỉ dùng khi kiến trúc yêu cầu endpoint-specific hostname và endpoint/service hỗ trợ. Không thay bằng IP private trực tiếp vì TLS và AWS request signing phụ thuộc hostname/region.

### 9.3. Google Cloud Java client

Với client hỗ trợ custom endpoint, PSC p.googleapis.com có thể được chỉ định qua settings:

~~~java
Storage storage = StorageOptions.newBuilder()
        .setProjectId(projectId)
        .setHost("https://storage-checkout.p.googleapis.com")
        .build()
        .getService();
~~~

API cụ thể có thể khác theo Google Cloud Java library/version. Kiểm tra builder của client đang dùng và đảm bảo DNS có record phù hợp, Host/SNI đúng và service account có IAM permission. Nếu dùng private DNS override tên storage.googleapis.com, client có thể tiếp tục gọi endpoint mặc định mà không cần custom host; hãy chọn một phương án và kiểm tra bằng DNS từ workload.

## 10. Thiết kế DNS cho VNet/VPC nhiều mạng

Một hệ thống thực tế có thể có:

- Hub VNet/VPC chứa DNS resolver/firewall.
- Spoke VNet/VPC chạy ứng dụng.
- Private endpoint nằm ở subnet trung tâm hoặc subnet dịch vụ.
- On-premises nối qua VPN/ExpressRoute/Direct Connect/Cloud Interconnect.

### 10.1. Hub-and-spoke

~~~mermaid
flowchart TD
    OnPrem["On-prem DNS / workloads"] --> VPN["VPN / dedicated link"]
    VPN --> Hub["Hub VNet/VPC"]
    Hub --> DNS["Central DNS resolver"]
    Hub --> Spoke1["Spoke: Spring Boot"]
    Hub --> PE["Private endpoint subnet"]
    Spoke1 --> DNS
    Spoke1 --> PE
    PE --> PaaS["Managed service"]
~~~

Các câu hỏi phải trả lời:

1. Spoke có route tới private endpoint IP không?
2. Spoke có thể truy vấn private DNS zone không?
3. Private DNS zone đã link tới đúng VNet chưa?
4. Nếu DNS tập trung ở hub, resolver có forwarding rule cho zone private không?
5. On-premises có route tới endpoint IP và truy vấn được private zone không?
6. NSG/firewall có cho phép TCP 443 từ nguồn thực tế không?

### 10.2. Peering không tự giải quyết mọi vấn đề DNS

VNet/VPC peering cung cấp đường mạng theo giới hạn của nền tảng, nhưng không phải lúc nào cũng tự chia sẻ private DNS zone. Với Azure, cần link zone tới VNet hoặc thiết lập DNS forwarding. Với AWS, private hosted zone cần association/Resolver rules phù hợp. Với Google Cloud, Cloud DNS private zone cần network binding/forwarding đúng.

Không coi “hai VNet đã peering” là bằng chứng hostname sẽ phân giải đúng.

### 10.3. Hybrid DNS

Khi on-premises cần gọi service qua private endpoint:

- Có route VPN/ExpressRoute/Direct Connect/Interconnect tới mạng chứa endpoint.
- DNS on-prem forward zone private tới resolver cloud tương ứng.
- Cloud resolver nhận query và trả private IP endpoint.
- Firewall on-prem và cloud cho phép chiều đi/về.
- Kiểm tra MTU, routing symmetry và NAT nếu có.

Nếu DNS trả private IP nhưng gói tin không có route về, TCP vẫn timeout. Nếu route đúng nhưng DNS trả public IP, traffic có thể đi sai đường hoặc bị service từ chối.

## 11. Kiểm tra từ đúng runtime environment

Đừng chỉ kiểm tra trên máy developer. Chạy các lệnh từ **pod/VM/container cùng subnet, DNS và route với Spring Boot**.

### 11.1. Kiểm tra DNS

Linux:

~~~bash
getent hosts demo-checkout-kv.vault.azure.net
nslookup demo-checkout-kv.vault.azure.net
dig +short demo-checkout-kv.vault.azure.net
~~~

Windows:

~~~powershell
Resolve-DnsName demo-checkout-kv.vault.azure.net
nslookup demo-checkout-kv.vault.azure.net
~~~

Kết quả mong đợi trong VNet có private endpoint: hostname cuối cùng resolve về private IP trong dải mạng của VNet. Không chỉ nhìn dòng CNAME; kiểm tra cả A/AAAA record cuối cùng.

### 11.2. Kiểm tra TCP 443

Linux:

~~~bash
nc -vz demo-checkout-kv.vault.azure.net 443
~~~

Windows PowerShell:

~~~powershell
Test-NetConnection demo-checkout-kv.vault.azure.net -Port 443
~~~

Nếu DNS trả private IP nhưng TCP fail, kiểm tra route, NSG, UDR, firewall, NACL, endpoint connection state và security group. Không chuyển hostname sang public IP để “thử cho nhanh” trong môi trường private-only.

### 11.3. Kiểm tra TLS giữ hostname chuẩn

~~~bash
openssl s_client \
  -connect demo-checkout-kv.vault.azure.net:443 \
  -servername demo-checkout-kv.vault.azure.net \
  -verify_return_error
~~~

Tùy chọn connect dùng hostname chuẩn; resolver sẽ chọn IP theo DNS hiện tại. Tùy chọn servername gửi SNI đúng FQDN. Không kết nối bằng private IP nếu mục tiêu là kiểm tra hostname certificate của dịch vụ.

### 11.4. Kiểm tra HTTP không tiết lộ secret

Có thể dùng request không kèm credential hoặc health endpoint phù hợp để xác minh TLS/network. Nếu service trả 401/403, điều đó có thể chứng minh TCP/TLS đã tới được service nhưng authorization chưa đúng. Không đưa bearer token, API key hoặc secret vào lệnh curl có thể bị lưu history.

### 11.5. Kiểm tra trong Java

Có thể log metadata không nhạy cảm:

~~~java
InetAddress[] addresses =
        InetAddress.getAllByName("demo-checkout-kv.vault.azure.net");

for (InetAddress address : addresses) {
    // Ghi nhận IP để chẩn đoán; không ghi token/secret.
    System.out.println("Resolved address: " + address.getHostAddress());
}
~~~

Đoạn này chỉ kiểm tra DNS mà JVM sử dụng. Nó không chứng minh TLS, authorization hoặc request của SDK dùng cùng HTTP transport. Bài integration test phải gọi client thật từ runtime tương đương.

## 12. Kiểm thử tích hợp private networking

### 12.1. Ma trận test theo lớp

| Lớp | Test | Kết quả mong đợi |
| --- | --- | --- |
| DNS | Resolve FQDN chuẩn từ pod | Private IP endpoint |
| DNS hybrid | Resolve từ on-prem | Private IP qua forwarding |
| TCP | Kết nối port 443 | Handshake TCP thành công |
| TLS | Verify CA + hostname | Certificate hợp lệ |
| Endpoint | Connection state | Approved/Available |
| Network policy | NSG/SG/NACL/firewall | Chỉ nguồn/port cần thiết được phép |
| Authentication | Token/credential | Đúng principal |
| Authorization | Đọc resource test | Được phép theo IAM/RBAC |
| Public isolation | Test từ mạng ngoài | Bị từ chối khi public access disabled |
| Application | Spring SDK request | Đọc/ghi dữ liệu test theo quyền được cấp |

### 12.2. Integration test với Azure

Dùng App Configuration/Key Vault dev:

1. Tạo private endpoint cho store và vault.
2. Link private DNS zones privatelink.azconfig.io và privatelink.vaultcore.azure.net tới VNet workload.
3. Đảm bảo App Configuration endpoint và Key Vault endpoint vẫn là FQDN chuẩn.
4. Deploy test pod vào đúng VNet/subnet hoặc môi trường có VNet integration.
5. Xác minh DNS trả private IP và TCP 443 thành công.
6. Chạy Spring Boot với Managed Identity và role App Configuration Data Reader/Key Vault Secrets User.
7. Xác minh request thành công; sau đó kiểm tra public access theo chính sách.
8. Gỡ quyền hoặc chặn route trong tài nguyên test để xác nhận test phân biệt 403 với timeout.

### 12.3. Integration test với AWS

1. Tạo interface VPC endpoint cho dịch vụ AWS cần truy cập; chọn subnet ở ít nhất hai AZ nếu yêu cầu HA.
2. Bật Private DNS khi dùng service hostname chuẩn và VPC có DNS hostnames/resolution enabled.
3. Cho phép inbound 443 trên endpoint security group từ workload security group.
4. Với S3, quyết định gateway hay interface endpoint theo vị trí client và chi phí.
5. Chạy AWS SDK Java test từ EC2/EKS/ECS trong VPC.
6. Xác minh endpoint ENI/DNS, IAM role, bucket policy và endpoint policy.
7. Thử từ mạng không thuộc VPC để xác minh giới hạn truy cập theo thiết kế.

### 12.4. Integration test với Google Cloud

1. Tạo PSC endpoint tới service attachment hoặc Google API bundle phù hợp.
2. Chọn internal IP và region theo yêu cầu dịch vụ.
3. Tạo/kiểm tra Cloud DNS zone và record.
4. Đảm bảo VPC firewall egress cho phép tới PSC endpoint IP.
5. Cấu hình Google Cloud Java client endpoint nếu dùng p.googleapis.com.
6. Kiểm tra DNS, Host/SNI, IAM service account và request thật.
7. Với hybrid, kiểm tra route quảng bá qua Cloud VPN/Interconnect và DNS forwarding.

### 12.5. Test không được bỏ qua

- Endpoint Pending hoặc Rejected.
- Private DNS zone tồn tại nhưng chưa link VNet.
- Custom DNS không forward zone privatelink.
- Hostname trả private IP nhưng NSG/SG chặn port 443.
- TLS hostname mismatch vì code gọi private IP.
- IAM/RBAC đúng ở môi trường dev nhưng thiếu ở production identity.
- Một AZ/region mất kết nối.
- Public endpoint còn mở ngoài ý muốn.
- SDK dùng endpoint override khác với endpoint đã kiểm tra.

## 13. Chẩn đoán lỗi theo dấu hiệu

| Triệu chứng | Lớp có thể lỗi | Hướng xử lý |
| --- | --- | --- |
| DNS trả public IP trong VNet | Private DNS zone chưa có, chưa link hoặc custom DNS không forward | Kiểm tra zone, A record, VNet link và resolver |
| DNS trả NXDOMAIN | Sai hostname, zone shadowing hoặc record thiếu | Kiểm tra FQDN và zone authority |
| DNS trả private IP nhưng timeout | Route/NSG/SG/NACL/firewall hoặc endpoint chưa Approved | Kiểm tra TCP 443, effective route và endpoint state |
| TCP thành công, TLS fail | Hostname/SNI sai, trust chain hoặc TLS interception | Dùng FQDN chuẩn, kiểm tra certificate |
| TLS thành công, HTTP 403 | RBAC/IAM, endpoint policy hoặc service firewall | Kiểm tra principal và data-plane permissions |
| HTTP 404 | Sai resource path, service subresource hoặc endpoint | Kiểm tra tên store/vault/bucket và endpoint target |
| Một pod truy cập được, pod khác không | Subnet, node pool, DNS policy hoặc network policy khác | So sánh route, DNS resolver và source IP |
| VNet peering có nhưng không resolve private name | Private zone chưa link hoặc DNS forwarding chưa cấu hình | Cấu hình zone association/forwarding |
| On-prem resolve private IP nhưng timeout | Thiếu route, return path, firewall hoặc MTU | Kiểm tra VPN/ExpressRoute/Direct Connect/Interconnect |
| App Configuration truy cập được nhưng Key Vault không | Hai dịch vụ có private endpoint/DNS/firewall riêng | Kiểm tra zone privatelink.vaultcore.azure.net và route |
| AWS SDK không đi qua endpoint | Private DNS disabled hoặc dùng endpoint hostname khác | Kiểm tra endpoint DNS entries, private DNS và region |
| GCP PSC endpoint có IP nhưng request không tới | DNS/route/egress firewall hoặc service attachment acceptance | Kiểm tra forwarding rule, firewall, region và consumer accept list |

## 14. Bảo mật và vận hành

### 14.1. Giảm bề mặt public

Khi private path đã được xác minh:

- Tắt public network access trên resource hỗ trợ và theo chính sách.
- Chỉ cho phép subnet/security group cần thiết.
- Dùng private DNS và resolver có kiểm soát.
- Hạn chế quyền tạo/sửa endpoint và private DNS zone.
- Theo dõi thay đổi endpoint, DNS records, route và firewall rules.
- Không dùng private endpoint thay cho IAM/RBAC hoặc TLS.

Với Azure, cần hoàn tất private DNS và kiểm thử workload trước khi disable public access để tránh tự khóa ứng dụng hoặc pipeline quản trị.

### 14.2. High availability

Private endpoint là một thành phần của đường mạng; cần xem xét failure domain:

- Azure: private endpoint theo region, DNS record cho từng replica, VNet peering và resolver dự phòng.
- AWS: interface endpoint ENI ở nhiều Availability Zones; không chỉ chọn một AZ cho dịch vụ production.
- Google Cloud: endpoint region, global access nếu hỗ trợ, PSC backend/load balancer hoặc phương án failover theo dịch vụ.
- DNS: TTL, resolver availability, cache của JVM/OS và thời gian propagation.
- Ứng dụng: timeout/retry có giới hạn, circuit breaker và health state phù hợp.

Không retry vô hạn khi DNS sai hoặc quyền bị từ chối. Retry không thể sửa cấu hình endpoint/authorization.

### 14.3. Chi phí và giới hạn

Private connectivity có thể phát sinh chi phí và quota:

- Azure Private Endpoint có chi phí theo endpoint/region và dữ liệu theo pricing hiện hành.
- AWS interface endpoint tính phí theo giờ/AZ và dữ liệu xử lý; S3 gateway endpoint không có phí endpoint.
- GCP PSC có pricing/quota tùy endpoint, forwarding rule, load balancer và traffic.

Cần tính số endpoint, số AZ/region, data volume, DNS resolver, cross-region traffic và hybrid link. Không tạo một endpoint cho mọi ứng dụng mà không xem xét mô hình dùng chung, giới hạn bảo mật và blast radius.

### 14.4. DNS và IP không nên hard-code trong ứng dụng

Không lưu private IP endpoint trong application.yml, Java code hoặc Config Server. IP có thể thay đổi khi tái tạo endpoint hoặc triển khai lại mạng. Dùng hostname dịch vụ chuẩn và để DNS quản lý mapping.

Nếu dịch vụ yêu cầu custom endpoint như một số PSC Google API use case, quản lý hostname qua cấu hình theo môi trường, không hard-code IP.

## 15. Bài tập thực hành tổng hợp

Một order-service triển khai trên AKS cần:

- orders-config từ Azure App Configuration.
- orders-kv từ Azure Key Vault.
- Một bucket S3 của hệ thống tích hợp AWS ở VPC riêng.
- Google API qua PSC từ một workload chạy ở GCP.
- Mạng on-premises cũng cần truy cập API nội bộ.

**Yêu cầu thiết kế:**

1. Tạo Azure Private Endpoint riêng cho App Configuration và Key Vault; cấu hình đúng private DNS zone.
2. Giữ endpoint Spring Cloud Azure ở FQDN chuẩn, không dùng privatelink hostname.
3. Chọn AWS S3 gateway endpoint hay interface endpoint dựa trên vị trí workload và yêu cầu on-prem/cross-VPC.
4. Thiết lập GCP PSC endpoint và DNS record phù hợp; xác minh Host/SNI nếu dùng custom endpoint.
5. Thiết kế DNS forwarding từ on-prem tới resolver cloud.
6. Viết checklist NSG/SG/firewall/route cho TCP 443.
7. Kiểm tra TLS, Managed Identity/IAM và request SDK thật từ từng runtime.
8. Tắt public access sau khi chứng minh private path hoạt động và có phương án rollback.

**Câu hỏi tự đánh giá:**

- Vì sao private endpoint có thể tồn tại nhưng ứng dụng vẫn resolve ra public IP?
- Vì sao nên dùng hostname chuẩn thay vì IP riêng trong application.yml?
- App Configuration private endpoint yêu cầu private DNS zone nào?
- Vì sao AWS S3 có cả gateway endpoint và interface endpoint?
- PSC endpoint và PSC backend khác nhau ở điểm nào?
- DNS đúng nhưng TCP timeout cho biết cần điều tra lớp nào?
- TLS thành công nhưng 403 là lỗi DNS hay authorization?
- Vì sao tạo private endpoint không tự động chứng minh public access đã bị tắt?

**Đáp án định hướng:** private DNS chưa link/forward hoặc query từ resolver khác; hostname chuẩn giữ TLS/SNI và SDK behavior; App Configuration dùng privatelink.azconfig.io; S3 gateway dựa route table còn interface dùng ENI/private IP và hỗ trợ một số hybrid use case; PSC endpoint là L4 forwarding rule, backend thêm load balancer; timeout là route/firewall/endpoint; 403 là authorization/policy; public access phải kiểm tra riêng trên resource.

## 16. Tài liệu tham khảo chính thức

- [Microsoft Learn – What is a private endpoint?](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-overview): NIC/private IP, target subresource, approval, DNS và network security.
- [Microsoft Learn – Azure Private Endpoint DNS configuration](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns): private DNS zone cho từng dịch vụ Azure.
- [Microsoft Learn – Use private endpoints for Azure App Configuration](https://learn.microsoft.com/en-us/azure/azure-app-configuration/concept-private-endpoint): endpoint, DNS, public access và geo-replication.
- [Microsoft Learn – Integrate Key Vault with Azure Private Link](https://learn.microsoft.com/en-us/azure/key-vault/general/private-link-service): private DNS zone, endpoint state và kiểm tra kết nối Key Vault.
- [Microsoft Learn – DNS security and private name resolution](https://learn.microsoft.com/en-us/azure/networking/design-guide/dns-security): hybrid DNS, DNS Private Resolver và hub-spoke.
- [AWS – Access AWS services through AWS PrivateLink](https://docs.aws.amazon.com/vpc/latest/privatelink/privatelink-access-aws-services.html): interface endpoint, DNS và multi-AZ.
- [AWS – Create an interface VPC endpoint](https://docs.aws.amazon.com/vpc/latest/privatelink/create-interface-endpoint.html): subnet, ENI, security group và NACL.
- [AWS – Gateway endpoints for Amazon S3](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html): so sánh S3 gateway và interface endpoint.
- [Google Cloud – Private Service Connect overview](https://docs.cloud.google.com/vpc/docs/private-service-connect): endpoint, backend, interface và Google APIs.
- [Google Cloud – Access published services through endpoints](https://docs.cloud.google.com/vpc/docs/configure-private-service-connect-services): endpoint, subnet, firewall, region và hybrid access.
- [Google Cloud – Access global Google APIs through endpoints](https://docs.cloud.google.com/vpc/docs/configure-private-service-connect-apis): DNS p.googleapis.com, default hostname và Host/SNI.

**Ghi nhớ:** một kết nối riêng chỉ hoạt động khi **endpoint đã được chấp thuận, DNS phân giải đúng, route/firewall cho phép, TLS xác minh hostname và identity có quyền**. Trong Spring Boot, giữ endpoint hostname đúng theo dịch vụ và kiểm thử từ chính runtime network để chứng minh đường kết nối thực sự là private.
