# Thiết kế theo Availability Zone và xử lý lỗi cục bộ

## 1. Bài toán: một zone gặp sự cố nhưng ứng dụng vẫn phục vụ

Một ứng dụng đang chạy tốt trên Azure có thể mất khả năng phục vụ dù nhiều máy ảo (VM) vẫn hoạt động: các VM được đặt trong cùng khu vực hạ tầng, bộ cân bằng tải chỉ chuyển lưu lượng đến một zone, hoặc cơ sở dữ liệu nằm trên một điểm lỗi đơn. Khi một **Availability Zone (AZ)** mất kết nối hay gặp trục trặc về điện, mạng hoặc làm mát, những thành phần cùng phụ thuộc vào zone đó có thể không còn sẵn sàng.

Trong chương **Độ tin cậy và khôi phục thảm họa** của module `CLOUD_PROVIDERS_AZURE`, bài học này kết nối kiến thức về **subscription, resource group, Entra ID, mạng ảo, compute, lưu trữ, dữ liệu, giám sát và chi phí** với một yêu cầu vận hành cụ thể: **một lỗi cục bộ trong một zone không được làm toàn bộ ứng dụng ngừng phục vụ**.

Hãy hình dung hệ thống đặt hàng có API, hàng đợi, database và trang quản trị. Đặt ba VM ở ba zone chỉ là điểm khởi đầu. Hệ thống chỉ tiếp tục xử lý đơn hàng khi đường vào, xử lý nghiệp vụ, dữ liệu, quyền truy cập và các phụ thuộc quan trọng đều chịu được sự cố của một zone.

Sau bài học, bạn có thể:

- Phân biệt lỗi máy, lỗi zone, lỗi region và phạm vi bảo vệ của từng cấu trúc Azure.
- Chọn **zonal resource** hay **zone-redundant resource** phù hợp, không giả định mọi dịch vụ đều hỗ trợ như nhau.
- Vẽ đường đi của yêu cầu và loại bỏ các điểm lỗi đơn trong cả ứng dụng lẫn dữ liệu.
- Ước lượng dung lượng để chịu được lỗi một zone, thiết kế phát hiện lỗi, chuyển lưu lượng và phục hồi.
- Xây dựng kịch bản thực hành, quan sát và thử nghiệm lỗi cục bộ mà không phải tạo sự cố thật trên production.

## 2. Availability Zone là gì?

Một **Azure region** là khu vực địa lý đặt hạ tầng đám mây. Tại những region có hỗ trợ Availability Zones, các zone là các nhóm datacenter có hạ tầng điện, làm mát và mạng được thiết kế tách biệt để giảm khả năng cùng hỏng bởi một sự cố cục bộ. Các zone trong một region kết nối qua mạng có độ trễ thấp phục vụ ứng dụng phân tán.

Ví dụ tư duy:

~~~text
Region: Southeast Asia (chỉ minh họa, cần xác nhận hỗ trợ của từng dịch vụ)
  ├── Availability Zone 1 ── API instance / worker
  ├── Availability Zone 2 ── API instance / worker
  └── Availability Zone 3 ── API instance / worker
~~~

`1`, `2`, `3` là **nhãn zone logic** được Azure trình bày cho subscription. Không nên coi zone `1` của hai subscription luôn tương ứng cùng một vị trí vật lý. Nếu cần ghép các tài nguyên thuộc nhiều subscription vào cùng vị trí vật lý, phải kiểm tra khả năng ánh xạ zone mà Azure hỗ trợ cho trường hợp đó.

**Không phải region nào, loại VM nào và dịch vụ Azure nào cũng hỗ trợ cùng số lượng zone hoặc cùng chế độ dự phòng.** Trước khi thiết kế, hãy xác nhận khả năng hỗ trợ theo đúng region, service tier/SKU và cấu hình. Ngay cả khi dịch vụ có chức năng zone redundancy, việc bật chức năng đó đôi khi yêu cầu chọn tier hoặc tùy chọn riêng.

### 2.1. Phân biệt các cấp lỗi

| Phạm vi lỗi | Ví dụ | Cơ chế bảo vệ thích hợp |
| --- | --- | --- |
| **Instance/process** | API crash, VM không phản hồi, container khởi động lại | Nhiều replica, health probe, restart, autoscale |
| **Host/rack hoặc lỗi bảo trì cục bộ** | Máy chủ vật lý hỏng hoặc được cập nhật | Nhiều instance, phân tán placement/fault domain |
| **Availability Zone** | Mất điện hoặc mất kết nối tại một zone | Phân bố workload qua nhiều zone, đường vào và dữ liệu chịu lỗi zone |
| **Region** | Sự cố ảnh hưởng diện rộng đến region | Kiến trúc đa region, dữ liệu nhân bản liên vùng, failover và kế hoạch DR |
| **Lỗi logic/chung** | Deploy code lỗi, xóa dữ liệu, credential bị thu hồi, cấu hình DNS sai | Rollback, backup, kiểm soát thay đổi, tách quyền và kiểm thử |

Một kiến trúc đa zone giảm rủi ro từ **lỗi cục bộ theo zone**. Nó không thay thế kiến trúc đa region để xử lý sự cố toàn region, và không bảo vệ khỏi mọi lỗi phần mềm hoặc lỗi thao tác đồng loạt.

### 2.2. Zonal, zone-redundant và non-zonal

Các khái niệm cần được phân biệt khi xem tài liệu của từng dịch vụ:

- **Zonal resource** được gắn với một zone cụ thể, chẳng hạn một VM triển khai vào zone `1`. Tài nguyên đó không tự di chuyển sang zone khác khi zone `1` gặp sự cố. Khả năng chịu lỗi xuất hiện khi ứng dụng có các instance thay thế ở zone khác.
- **Zone-redundant resource** được dịch vụ thiết kế để hoạt động qua nhiều zone trong region, có thể gồm nhân bản dữ liệu hoặc đường đi xử lý qua zone; cách failover là **đặc thù dịch vụ**.
- **Non-zonal/regional resource** không có lựa chọn zone trực tiếp hoặc không công bố bảo đảm zone redundancy cho cấu hình đang dùng. Không được tự suy luận rằng resource này chịu lỗi zone chỉ vì tên resource chứa tên region.

**Nguyên tắc:** Phân tán VM theo zone không đồng nghĩa mọi thành phần khác cũng tự có tính sẵn sàng theo zone. Phải kiểm tra toàn bộ đường đi của yêu cầu, từ DNS/điểm vào đến các hệ thống dữ liệu và phụ thuộc.

## 3. Mục tiêu độ tin cậy: SLI, SLO, RTO và RPO

Trước khi lựa chọn dịch vụ, đội kỹ thuật cần biến câu “phải chạy khi một zone lỗi” thành mục tiêu kiểm chứng được.

| Thuật ngữ | Câu hỏi cần trả lời | Ví dụ cho API đơn hàng |
| --- | --- | --- |
| **SLI** (Service Level Indicator) | Đo độ khỏe của hệ thống bằng đại lượng nào? | Tỷ lệ yêu cầu thành công; độ trễ p95 của thao tác đặt hàng |
| **SLO** (Service Level Objective) | Mức mục tiêu của SLI trong một khoảng thời gian? | Tỷ lệ yêu cầu thành công tối thiểu theo mục tiêu nội bộ |
| **RTO** (Recovery Time Objective) | Có thể gián đoạn tối đa bao lâu sau sự cố? | Đường vào phải phục hồi trong khoảng thời gian doanh nghiệp cho phép |
| **RPO** (Recovery Point Objective) | Chấp nhận mất bao nhiêu dữ liệu đã ghi? | Không mất đơn hàng đã được xác nhận, nếu kiến trúc dữ liệu đáp ứng |

Các con số cần được thỏa thuận theo nghiệp vụ và khả năng thực tế của dịch vụ. Đừng mặc định rằng zone redundancy luôn cho **RTO bằng 0** hoặc **RPO bằng 0**. Ví dụ, failover dịch vụ dữ liệu có thể gây ngắt kết nối ngắn và yêu cầu client kết nối lại; tính nhất quán và khả năng mất dữ liệu phụ thuộc chế độ nhân bản của dịch vụ.

Phân biệt **high availability (HA)** và **disaster recovery (DR)**:

- HA thường tự động hạn chế tác động của lỗi thường gặp và lỗi zone bằng replica, health check, redundancy, failover.
- DR bao gồm khôi phục trước sự cố nghiêm trọng hơn: backup, khôi phục dữ liệu, chuyển sang region khác, phân vai và runbook.

Bài học này ưu tiên HA khi **mất một zone**; kế hoạch DR toàn region vẫn phải được thiết kế riêng.

## 4. Kiến trúc tham chiếu cho ứng dụng ba lớp

Giả sử dịch vụ đặt hàng được triển khai vào một region Azure có ba zone và các SKU cần thiết có hỗ trợ tương ứng.

~~~mermaid
flowchart TB
    U["Client / ứng dụng người dùng"] --> I["Điểm vào có khả năng chịu lỗi zone<br/>VD: Standard Load Balancer + frontend phù hợp"]
    I --> H["Health probe / routing"]
    H --> A1["AZ 1<br/>API replicas + workers"]
    H --> A2["AZ 2<br/>API replicas + workers"]
    H --> A3["AZ 3<br/>API replicas + workers"]
    A1 --> D["Dịch vụ dữ liệu hỗ trợ zone redundancy<br/>và đã bật đúng cấu hình"]
    A2 --> D
    A3 --> D
    A1 --> Q["Queue / cache đã kiểm tra tính sẵn sàng theo zone"]
    A2 --> Q
    A3 --> Q
    M["Azure Monitor + Application Insights<br/>cảnh báo và kiểm tra từ nhiều vị trí"] -.-> I
    M -.-> A1
    M -.-> A2
    M -.-> A3
    M -.-> D
~~~

Sơ đồ này thể hiện **vai trò** của từng lớp, không cam kết rằng mọi dịch vụ được nêu đều có cùng kiểu triển khai zone. Khi hiện thực, cần chọn chính xác sản phẩm và SKU đáp ứng yêu cầu.

### 4.1. Đường vào phải tiếp tục nhận và chuyển lưu lượng

Một lựa chọn cho workload VM trong region là **Azure Standard Load Balancer** cùng frontend public IP được cấu hình phù hợp để chịu lỗi zone (nếu region hỗ trợ). Backend pool gồm các instance ở nhiều zone; health probe giúp ngừng gửi lưu lượng đến backend không khỏe.

Nếu dùng **Application Gateway v2** hoặc dịch vụ ingress khác, phải kiểm tra hỗ trợ và cấu hình zone redundancy của chính dịch vụ đó. Một frontend có khả năng chịu lỗi zone chỉ giải quyết **đường vào**; nếu toàn bộ backend đặt trong một zone thì ứng dụng vẫn mất dịch vụ khi zone ấy lỗi.

Lưu ý: **Azure Front Door** phục vụ định tuyến ở phạm vi toàn cầu, đặc biệt hữu ích cho đa region; nó không thay thế việc phân tán workload và dữ liệu trong region.

### 4.2. Tầng xử lý nên stateless và phân tán

Dùng nhiều replica độc lập ở các zone, chẳng hạn:

- **Virtual Machines hoặc Virtual Machine Scale Sets (VMSS)** được triển khai/phân bố theo zone khả dụng, với cấu hình scaling và quy tắc phân bố được kiểm tra theo loại orchestration đang sử dụng.
- **Azure Kubernetes Service (AKS)** với node pool và các replica workload có placement phù hợp theo zone; xem xét `topologySpreadConstraints` và `PodDisruptionBudget` để giảm tình huống dồn mọi pod vào một zone.
- **Dịch vụ ứng dụng được Azure quản lý** có tùy chọn zone redundancy (nếu hỗ trợ ở region/tier đã chọn).

API stateless hạn chế phụ thuộc vào disk cục bộ hoặc session giữ trên một instance. Những dữ liệu như session, thông tin phiên làm việc, trạng thái xử lý lâu dài cần lưu ở hệ thống hỗ trợ truy cập qua nhiều replica, có khả năng chịu lỗi phù hợp.

Đừng chỉ đếm “ba replica”; phải biết **chúng nằm ở đâu** và bộ điều phối có thể dồn chúng về cùng một zone hay không.

### 4.3. Tầng dữ liệu phải chịu được lỗi của zone

Cách xử lý phụ thuộc loại dữ liệu và dịch vụ:

| Nhu cầu | Hướng thiết kế | Điều cần xác minh |
| --- | --- | --- |
| Blob/storage account | Chọn **ZRS** hoặc **GZRS** khi SKU, region và yêu cầu cho phép | Dịch vụ và loại dữ liệu có hỗ trợ; chi phí; semantics failover |
| Cơ sở dữ liệu quan hệ | Chọn tier/cấu hình **zone-redundant high availability** khi dịch vụ Azure SQL hoặc giải pháp tương ứng hỗ trợ | Kiểu replica, failover, RPO/RTO kỳ vọng, kết nối lại |
| Dữ liệu chạy trên VM | Tự thiết kế replication/cluster qua zone; xem xét loại Managed Disk và khả năng hỗ trợ ZRS | Một disk gắn với VM không tự biến workload thành cluster |
| Queue, cache, broker | Chọn tier/triển khai hỗ trợ độ sẵn sàng theo zone; bảo vệ state và xử lý lại | Cấu hình thực tế, thứ tự message, duplicate, failover |
| Shared secrets/configuration | Dùng dịch vụ quản lý danh tính, secret và cấu hình với độ tin cậy phù hợp | Truy cập Entra ID, DNS, Private Endpoint, quota, network rules |

**ZRS (Zone-Redundant Storage)** nhân bản dữ liệu đồng bộ qua các zone trong region được hỗ trợ theo mô hình của Azure Storage; **GZRS** bổ sung nhân bản liên vùng theo đặc tính dịch vụ. Việc chọn **LRS**, **ZRS**, **GRS** hay **GZRS** liên quan đến vùng chịu lỗi, cách truy cập và chi phí; không coi các tùy chọn là hoán đổi trực tiếp.

Đối với database, “có nhiều bản sao” chưa đủ: cần rõ số replica có thể mất, quorum, cơ chế leader election, semantics ghi đã xác nhận và hành vi của client trong failover. Nếu dùng cluster tự quản lý, đặt các thành viên ở các zone độc lập và kiểm tra rằng mất một zone vẫn đủ **quorum** để tránh split-brain.

### 4.4. Các phụ thuộc ẩn vẫn có thể là điểm lỗi đơn

Vẽ đường đi thực tế của một yêu cầu: DNS → ingress → API → identity/token → database → queue → worker → storage → phản hồi. Phải kiểm tra cả **outbound connectivity**, NAT, mạng riêng/Private Endpoint, DNS resolution, chứng chỉ, Entra ID, Key Vault và dịch vụ dùng chung.

Ví dụ API ở cả ba zone nhưng worker chỉ chạy ở zone `1` thì đặt hàng có thể trả HTTP 202 mà không bao giờ xử lý xong. Hoặc API sống nhưng một hệ thống cache duy nhất bị lỗi làm mọi request hết thời gian chờ. Điểm lỗi đơn thường nằm ở **phụ thuộc và trạng thái**, không chỉ ở nơi đặt máy.

## 5. Thiết kế dung lượng chịu lỗi một zone

Một kiến trúc có ba zone có thể vẫn không đủ năng lực sau khi mất một zone. Nhu cầu phải được tính theo **tải đỉnh thực tế** và phần tài nguyên còn sống.

Giả sử tải đỉnh thiết kế là **900 requests/second (RPS)**. Hệ thống phân bố replica đều ở ba zone; mỗi zone được benchmark có thể xử lý an toàn **600 RPS** ở mức latency mục tiêu.

| Trạng thái | Zone phục vụ | Tổng năng lực an toàn | So với tải đỉnh 900 RPS |
| --- | --- | ---: | --- |
| Bình thường | 1, 2, 3 | 1.800 RPS | Đủ, có dự phòng |
| Zone 2 lỗi | 1, 3 | 1.200 RPS | Đủ, còn biên 300 RPS |
| Zone 1 và 2 cùng lỗi | 3 | 600 RPS | Không đáp ứng tải đỉnh |

Công thức kiểm tra cho yêu cầu chịu lỗi **bất kỳ một zone**:

~~~text
Với mỗi zone z:
  SUM(năng_lực_an_toàn_của_các_zone_còn_lại) >= tải_đỉnh_yêu_cầu × hệ_số_dự_phòng

Nếu cả 3 zone có cùng năng lực C:
  2 × C >= tải_đỉnh_yêu_cầu × hệ_số_dự_phòng
~~~

Ví dụ, nếu quy định hệ số dự phòng là `1,2` thì sau khi mất một zone phải còn ít nhất `900 × 1,2 = 1.080 RPS`. Hai zone còn lại đạt `1.200 RPS`, do đó vượt ngưỡng trong giả định benchmark. Đây là ví dụ minh họa về tính toán năng lực, **không phải cam kết hiệu năng của Azure**.

Cũng phải tính:

1. **Nút thắt chung:** Database, queue, NAT/outbound connections, connection pool, storage throughput có đủ khi toàn bộ tải dồn qua các zone còn lại không?
2. **Quota và stock:** Azure có đủ quota vCPU, hạn mức tài nguyên và khả năng cấp phát VM ở các zone còn hoạt động không?
3. **Thời gian mở rộng:** Autoscale mất thời gian; phải giữ **headroom sẵn có** khi mục tiêu RTO không cho phép chờ thêm replica.
4. **Phân phối tải:** Health probe và thuật toán cân bằng tải có thực sự chuyển request sang zone khỏe không? Có session affinity làm lệch tải không?
5. **Sự cố theo thời gian:** Tải có tăng khi client retry hoặc backlog được xử lý lại không?

## 6. Hai mẫu cấu hình Bicep: zonal và zone-redundant

Trong IaC, cần phân biệt khai báo **đặt tài nguyên vào một zone cụ thể** với khai báo **dịch vụ tự quản lý redundancy qua nhiều zone**. Ví dụ dưới đây chỉ triển khai một public IP và một storage account để minh họa cú pháp; nó **chưa phải kiến trúc HA hoàn chỉnh**, vì không tạo backend, load balancer hoặc database.

**Giả định:** Region mục tiêu hỗ trợ đúng các zone `1`, `2`, `3` cho loại Standard public IP và hỗ trợ Storage ZRS với SKU đã chọn; tên storage account là duy nhất toàn Azure, đúng quy tắc đặt tên.

~~~bicep
targetScope = 'resourceGroup'

param location string = resourceGroup().location

@description('Tên storage account duy nhất trên Azure, chữ thường và chữ số.')
@minLength(3)
@maxLength(24)
param storageAccountName string

// Standard Public IP có cấu hình nhiều zone.
// Khả năng sử dụng phụ thuộc region và SKU.
resource ingressPublicIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: 'pip-orders-zr'
  location: location
  sku: {
    name: 'Standard'
    tier: 'Regional'
  }
  zones: [
    '1'
    '2'
    '3'
  ]
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

// Với Azure Storage, redundancy được chọn qua SKU.
// Không thêm zones: ['1', '2', '3'] vào Storage Account.
resource ordersStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_ZRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
  }
}

output ingressPublicIpId string = ingressPublicIp.id
output storageAccountId string = ordersStorage.id
~~~

Ý nghĩa:

- `zones: ['1', '2', '3']` trên loại public IP được hỗ trợ tạo frontend có cấu hình zone redundancy; điều đó **chưa** bảo đảm backend khỏe.
- Storage account dùng `sku.name: 'Standard_ZRS'` để yêu cầu Azure Storage lưu dữ liệu theo mô hình ZRS tại nơi được hỗ trợ. ZRS là đặc tính của dịch vụ; không phải danh sách ba VM do người dùng tạo.
- Khi tạo **VM zonal**, dùng thuộc tính `zones` của chính resource VM hoặc cấu hình zone của VMSS/AKS theo tài liệu dịch vụ; cần đủ thành phần network/OS/disk và replication để triển khai thực tế.
- Cần chạy **what-if**, xác nhận SKU, location, quota và policy trước khi tạo. Bicep compile thành công không chứng minh rằng mọi zone đều được cung cấp tại region đã chọn.

**Lựa chọn triển khai:** Với nhiều dịch vụ PaaS, cấu hình zone redundancy không phải thuộc tính `zones` của resource, mà nằm trong tier, SKU hoặc thuộc tính dịch vụ. Luôn đọc đặc tả resource provider thay vì sao chép cấu hình VM sang storage/database.

### 6.1. Kiểm tra placement sau triển khai

Đối với VM và tài nguyên đã có, có thể kiểm tra thuộc tính `zones` qua Azure CLI:

~~~bash
az account show --query "{subscription:id,tenant:tenantId}" -o json

az vm show \
  --resource-group rg-orders \
  --name vm-orders-z1 \
  --query "{name:name,location:location,zones:zones}" -o json

az network public-ip show \
  --resource-group rg-orders \
  --name pip-orders-zr \
  --query "{name:name,sku:sku.name,zones:zones}" -o json

az storage account show \
  --resource-group rg-orders \
  --name storderssample001 \
  --query "{name:name,location:location,sku:sku.name}" -o json
~~~

Tên resource group, VM và storage account ở đây chỉ là ví dụ; các lệnh `show` thành công khi tài nguyên tồn tại và identity có quyền đọc. Với nhiều PaaS, cần xem **cấu hình HA thực tế** trong thuộc tính dành riêng của dịch vụ; một trường `zones` vắng mặt không đủ để kết luận không có zone redundancy.

**Lưu ý mạng:** Resource group không phải ranh giới mạng riêng hay vùng sẵn sàng. Các subnet của một VNet có thể phục vụ workload trải trên nhiều zone trong cùng region; kiến trúc bảo mật NSG, route, firewall, private DNS và private endpoints phải được xem xét đồng bộ.

## 7. Phát hiện lỗi và cô lập zone gặp sự cố

**Failover đúng** đòi hỏi hệ thống phân biệt lỗi instance với lỗi zone và chỉ đưa **backend thực sự không khỏe** ra khỏi đường nhận request.

### 7.1. Health probe và readiness

Phân biệt ba phép kiểm tra:

| Phép kiểm tra | Nội dung | Cách dùng |
| --- | --- | --- |
| **Liveness** | Tiến trình còn hoạt động, chưa deadlock? | Khởi động lại tiến trình/container khi không khỏe |
| **Readiness** | Instance hiện có xử lý được request của dịch vụ? | Quyết định có nhận lưu lượng qua load balancer/ingress |
| **Synthetic end-to-end** | Một giao dịch mẫu từ bên ngoài có thành công? | Phát hiện lỗi đường đi hoặc phụ thuộc mà probe cục bộ bỏ sót |

Ví dụ endpoint `/ready` có thể chỉ trả `200` khi instance đã khởi tạo xong, đang xử lý được request và không ở trạng thái drain. Endpoint `/live` có thể kiểm tra vòng đời tiến trình. Tránh biến cả hai thành truy vấn sâu tới mọi dịch vụ bên ngoài trên mỗi lần probe: một sự cố nhỏ ở dependency chung có thể khiến **toàn bộ instance đồng loạt bị loại** và làm sự cố lan rộng.

Với Azure Load Balancer, probe phù hợp xác định backend nào còn được nhận lưu lượng. Cần chọn tần suất kiểm tra, ngưỡng lỗi và hành vi kết nối hiện có theo dịch vụ; **không giả định failover tức thì**.

### 7.2. Một luồng xử lý lỗi điển hình

~~~mermaid
sequenceDiagram
    participant U as Client
    participant LB as Ingress / Load Balancer
    participant Z2 as API AZ 2
    participant Z1 as API AZ 1
    participant DB as Database HA
    U->>LB: POST /orders
    LB->>Z2: Chuyển request
    Note over Z2: AZ 2 ngừng đáp ứng
    Z2--xLB: Timeout / mất health probe
    LB->>Z1: Request mới đến backend khỏe
    Z1->>DB: Ghi đơn hàng
    DB-->>Z1: Kết quả / xác nhận
    Z1-->>U: Phản hồi
    Note over U,Z1: Request cũ có thể thất bại; client cần retry an toàn
~~~

Các kết nối hoặc request đang thực thi ở AZ 2 có thể thất bại; chuyển lưu lượng chỉ giúp **request mới** đi về backend khỏe. Vì vậy client và ứng dụng phải có cơ chế xử lý lỗi, timeout và retry phù hợp.

### 7.3. Retry, timeout, idempotency và circuit breaker

Nếu mọi client đều retry vô hạn và đồng thời, một sự cố zone có thể tạo **retry storm** làm quá tải hai zone còn lại. Phần mềm cần:

- Đặt **timeout hữu hạn** cho mạng, database và lời gọi API; theo dõi budget cho cả chuỗi request.
- Retry có giới hạn, **exponential backoff và jitter**, chỉ với lỗi tạm thời có khả năng phục hồi.
- Dùng **idempotency key** hoặc ràng buộc duy nhất cho thao tác ghi quan trọng. Nếu request đặt hàng bị timeout sau khi database đã commit, retry phải trả cùng kết quả hoặc xử lý trùng an toàn.
- Dùng **circuit breaker** khi dependency liên tục lỗi; tránh làm cạn connection pool và thread.
- Có backpressure, queue depth limit, load shedding hoặc chế độ suy giảm dịch vụ nếu năng lực còn lại không đủ.
- Với tác vụ bất đồng bộ, chấp nhận khả năng **at-least-once processing**, duplicate và out-of-order tùy dịch vụ queue; worker phải xử lý an toàn.

Lỗi phải được cô lập theo tầng: mất một zone không nên kéo theo thác lỗi do kết nối giữ lâu, retry dồn dập hoặc một cache cục bộ trở thành dependency bắt buộc.

## 8. Dữ liệu có trạng thái: vấn đề khó hơn cân bằng tải

Stateless API có thể thay thế instance tương đối dễ; **stateful workload** cần kế hoạch riêng.

**Tình huống A — database do Azure quản lý:** Chọn cấu hình HA theo zone mà dịch vụ và tier hỗ trợ, xác minh failover tự động hay thủ công, độ trễ trong chuyển vai trò, kết nối bị cắt và giới hạn thông lượng sau failover. Ứng dụng phải có connection retry, timeout, pool recovery và giao dịch idempotent. Đừng suy ra RPO/RTO chính xác nếu chưa xác nhận tài liệu và kiểm thử đúng tier.

**Tình huống B — cluster tự quản lý:** Giả sử có ba node có quyền biểu quyết, mỗi node ở một zone và quorum là hai. Nếu mất zone chứa một node, hai node khỏe có thể giữ quorum; tuy nhiên điều này **chỉ đúng nếu** cơ chế consensus, placement và truy cập lưu trữ được cấu hình chuẩn. Nếu hai node vô tình nằm cùng một zone, mất zone đó có thể làm cluster không còn quorum.

**Tình huống C — object storage:** ZRS hỗ trợ lỗi cục bộ theo mô hình của Azure Storage, nhưng không thể tự sửa lỗi người dùng xóa object hoặc ứng dụng ghi đè nội dung sai. Cần thêm versioning, soft delete, backup hoặc chính sách lưu giữ tùy yêu cầu phục hồi logic và tuân thủ.

Không đồng nhất **replication** với **backup**. Replication thường sao chép cả thay đổi không mong muốn; backup/restore phục vụ khôi phục từ những thay đổi đó và phải được kiểm tra khả năng khôi phục. Tương tự, zone redundancy trong một region chưa đủ cho kế hoạch mất cả region.

## 9. Runbook: ứng phó khi AZ 2 mất khả năng phục vụ

Giả sử hệ thống ở mục 4 có ba zone, toàn bộ request đi qua ingress có health probe và các zone còn lại đã có capacity dự phòng.

| Giai đoạn | Dấu hiệu / thao tác | Tiêu chí đạt |
| --- | --- | --- |
| **Phát hiện** | Probe ở AZ 2 lỗi; tỷ lệ 5xx, timeout hoặc độ trễ tăng | Có cảnh báo dựa trên SLI end-to-end và thông tin backend |
| **Khoanh vùng** | So sánh sức khỏe backend theo zone, trạng thái dữ liệu và service health | Xác nhận phạm vi ảnh hưởng thay vì vội coi toàn region hỏng |
| **Cô lập** | Ingress dừng chuyển request **mới** đến backend AZ 2 không khỏe; workload rút readiness nếu cần | Không còn request mới đi vào backend lỗi sau thời gian hội tụ |
| **Duy trì dịch vụ** | AZ 1 và AZ 3 nhận lưu lượng; kiểm tra database, queue, cache và headroom | Đặt hàng tiếp tục chạy trong SLO, error rate giảm |
| **Ổn định** | Giới hạn retry, mở rộng có kiểm soát, ưu tiên đường nghiệp vụ quan trọng | Không xuất hiện retry storm hoặc backlog không kiểm soát |
| **Phục hồi** | Chờ Azure/service khôi phục zone; kiểm tra data sync, readiness và instance mới | Backend được đưa lại vào pool từng bước, không gây tải đột ngột |
| **Hậu kiểm** | Ghi nhận timeline, RTO/RPO thực tế, nơi có bottleneck, hành động phòng ngừa | Có số liệu, owner và thay đổi có thể kiểm chứng |

Trong sự cố, đừng liên tục tạo lại tài nguyên tại zone đang hỏng nếu việc đó chỉ tạo thêm lỗi và tiêu tốn quota. Khi zone phục hồi, kiểm tra **reconciliation và rebalance**: instance/data có về trạng thái mong muốn, đặt đúng zone và không còn lệch tải?

### 9.1. Khi nào failover thủ công?

Tùy dịch vụ, zone failover có thể tự động. Với thành phần tự quản lý hoặc stateful, thao tác chuyển leader, gỡ node, đổi endpoint có thể cần quy trình thủ công được phê duyệt. Runbook phải mô tả rõ **quyền thực hiện, điều kiện kích hoạt, cách xác minh và cách quay lại**; không tạo tự động hóa mù quáng có thể gây split-brain hoặc mất dữ liệu.

## 10. Giám sát và diễn tập lỗi cục bộ

Một hệ thống chỉ có thể chứng minh chịu lỗi zone khi quan sát được tác động thực tế. Có thể sử dụng **Azure Monitor, Application Insights, Log Analytics, cảnh báo theo metric/log, Availability Tests và Service Health** tùy khả năng của từng dịch vụ.

Theo dõi tối thiểu:

- **Người dùng:** success rate, p95/p99 latency, số request timeout và số giao dịch chưa hoàn thành.
- **Ingress:** health probe state, backend khỏe, phân phối request giữa zone, tỷ lệ 4xx/5xx do từng tầng gây ra.
- **Compute:** replica khỏe theo zone, CPU/memory, hàng đợi request, connection pool, CPU throttling, thời gian scale-out.
- **Dữ liệu:** tình trạng leader/replica, failover events, thời gian commit, kết nối lỗi, replication lag (nếu có), backlog.
- **Nền tảng:** sự kiện Service Health, hạn mức/quota, DNS/Private Endpoint/route và cảnh báo thay đổi cấu hình.

Các bài diễn tập nên bắt đầu với môi trường thử nghiệm, theo cấp độ tăng dần:

1. **Tắt một instance**: xác minh load balancer ngừng chuyển request tới backend lỗi và phục hồi khi instance sẵn sàng.
2. **Giả lập mất toàn bộ backend ở một zone**: drain/disable các replica của zone đó trong môi trường kiểm soát, trong khi các zone còn lại hoạt động. Không cần gây mất điện hay phá mạng thật.
3. **Tăng tải đến mức đỉnh thiết kế** với một zone bị cô lập: so sánh capacity tính toán với throughput, latency và độ ổn định thực tế.
4. **Diễn tập stateful failover** theo cơ chế hỗ trợ của dịch vụ dữ liệu; kiểm tra ghi thành công, transaction idempotency, reconnect và backlog.
5. **Khôi phục zone**: đưa replica vào pool từng bước, kiểm tra data consistency, rebalance và các cảnh báo trở về bình thường.

Trước mỗi lần diễn tập, cần có owner, thời gian, điều kiện dừng, phạm vi môi trường và phương án phục hồi. Với production, chỉ thực hiện theo quy trình thay đổi được tổ chức chấp thuận. Giải pháp thử lỗi phải giữ khả năng quan sát, tránh che dấu giao dịch mất hoặc phá dữ liệu.

### 10.1. Tiêu chí nghiệm thu bài diễn tập

Ví dụ cho hệ thống đơn hàng:

~~~text
Given:
  - 3 zone có backend khỏe; các zone còn lại đủ capacity.
  - Tải được giữ tại 900 RPS trong bài benchmark.
When:
  - Toàn bộ backend ở AZ 2 bị đánh dấu không khỏe.
Then:
  - Ingress chuyển request mới về AZ 1 và AZ 3 theo probe.
  - Success rate và p95 latency trở về trong SLO đã thống nhất.
  - Không có đơn hàng trùng do retry; không thất lạc đơn đã xác nhận.
  - Queue backlog được xử lý hết trong ngưỡng quy định.
  - Có log, metric và timeline để đo RTO/RPO thực tế.
~~~

Các tiêu chí dùng ngưỡng SLO/RTO/RPO **do nhóm đề ra**, không giả định giá trị cố định cho mọi dịch vụ Azure.

## 11. Chi phí, hiệu năng và vận hành

Thiết kế chịu lỗi zone mang lại lợi ích về availability nhưng có chi phí vận hành:

| Yếu tố | Tác động | Cách kiểm soát |
| --- | --- | --- |
| **Replica/capacity dự phòng** | Cần đủ năng lực còn lại sau khi mất một zone | Tính N-1 capacity, benchmark, autoscale cùng mức sẵn có tối thiểu |
| **Storage/data replication** | SKU ZRS/zone redundancy có thể đắt hơn tùy loại dịch vụ | Chọn redundancy theo RPO/RTO và phân loại dữ liệu |
| **Lưu lượng giữa zone** | Có thể phát sinh phí truyền dữ liệu và tăng latency | Đo luồng thực tế; cân nhắc data locality nhưng tránh khóa ứng dụng vào một zone |
| **Quản trị nhiều zone** | Tăng số placement rule, health probes, cảnh báo, runbook | Chuẩn hóa IaC, cấu hình theo môi trường và diễn tập định kỳ |
| **Rủi ro cấu hình lệch** | Một zone thiếu quyền, DNS/route hoặc bản triển khai sai | Đồng nhất image/config, kiểm soát thay đổi và kiểm tra post-deploy |

Cần tránh tối ưu chi phí bằng cách xóa sạch capacity ở hai zone khi tải thấp rồi mặc định autoscale sẽ khôi phục tức thì trong sự cố. Khả năng cấp phát tài nguyên, thời gian khởi động và dữ liệu cần warm-up đều ảnh hưởng RTO. Mức headroom phù hợp phụ thuộc SLO và chi phí của việc ngừng dịch vụ.

Azure RBAC và Microsoft Entra ID cũng tham gia vào vận hành: danh tính automation phải có quyền cần thiết với tài nguyên tại mọi zone/scope, nhưng giữ **least privilege** để giảm lỗi thao tác và rủi ro bảo mật.

## 12. Bài thực hành: thiết kế lại ứng dụng chỉ chạy tại một zone

**Bối cảnh:** `orders-api` hiện có hai VM đều ở AZ 1, Standard Load Balancer, database trên một VM riêng và storage account chưa được xác minh redundancy. Người dùng cần đặt đơn ngay cả khi AZ 1 không khả dụng.

**Yêu cầu:** Thiết kế hệ thống chịu được mất bất kỳ **một** zone trong region, với tải đỉnh 900 RPS và phải có cách đo RTO/RPO.

### Bước 1: Vẽ dependency và đánh dấu điểm lỗi đơn

Ghi rõ đường đi:

~~~text
Client -> Ingress -> orders-api -> Database
                              -> Queue -> Worker
                              -> Storage
                              -> Auth / Secret / DNS
~~~

Với mỗi thành phần, ghi service/tier/SKU, vùng triển khai, zone placement, phương án health check, dữ liệu có trạng thái và cơ chế khôi phục.

### Bước 2: Chọn mô hình zone

Đưa replica `orders-api` và worker đến nhiều zone, cấu hình ingress/frontend phù hợp, phân phối backend và đặt readiness probe. Đối với dữ liệu, đánh giá có thể dùng dịch vụ PaaS zone-redundant hoặc cluster tự quản lý với replication/quorum theo zone; kiểm tra availability và tier ở đúng region.

### Bước 3: Kiểm tra N-1 capacity

Từ benchmark, giả sử mỗi zone đủ phục vụ 600 RPS trong mục tiêu latency. Tính lại khi từng zone lần lượt mất khả năng phục vụ; xem xét database throughput, queue processing rate và retry. Nếu chỉ có hai zone được hỗ trợ cho dịch vụ đang chọn, phải tính lại năng lực/kiến trúc theo vùng thực tế, không áp công thức ba zone máy móc.

### Bước 4: Viết kịch bản failure injection

Lập runbook cho sự cố toàn bộ backend một zone không khỏe. Xác định SLI, ngưỡng cảnh báo, điều kiện loại khỏi load balancer, quy tắc retry, xác minh dữ liệu, cách phục hồi và tiêu chí rollback.

### Bước 5: Báo cáo kết quả

Nộp sơ đồ phụ thuộc, bảng placement và redundancy cho các lớp, phép tính N-1, log/metric diễn tập, RTO/RPO đo được và danh sách các điểm lỗi đơn còn lại. Nếu một dịch vụ chưa có hỗ trợ zone redundancy ở tier đã chọn, phải nêu rõ rủi ro còn tồn tại và phương án xử lý phù hợp.

**Bảng tự đánh giá:**

| Câu hỏi | Đạt khi |
| --- | --- |
| AZ 1 lỗi có còn đường vào? | Frontend và các backend còn lại vẫn nhận request |
| VM/pod có được phân tán? | Placement thực tế thể hiện replica tại nhiều zone |
| Khi mất một zone có đủ năng lực? | N-1 capacity đáp ứng tải đỉnh và biên dự phòng đã đặt |
| Database còn ghi được dữ liệu? | Failover/quorum và thử nghiệm ghi xác nhận thành công |
| Client có thể retry an toàn? | Timeout/backoff giới hạn, thao tác quan trọng idempotent |
| Có bằng chứng RTO/RPO và quan sát được lỗi? | Dashboard, logs, bài diễn tập và kết quả đối chiếu mục tiêu |
| Nếu cả region lỗi thì sao? | Có DR/đa region/backup riêng, không nhầm với zone redundancy |

## 13. Những ngộ nhận cần tránh

**“Có ba VM ở ba zone là đủ.”** Chưa đủ: ingress, database, queue, cache, DNS, outbound và dependency dùng chung vẫn có thể là điểm lỗi đơn.

**“Zone redundancy đồng nghĩa dữ liệu không bao giờ mất.”** Không đúng cho mọi lớp và mọi kiểu lỗi. Chế độ replication, consistency, failover và backup quyết định khả năng khôi phục dữ liệu; xóa nhầm và lỗi logic có thể được nhân bản.

**“Autoscale sẽ tạo tài nguyên mới đúng lúc.”** Không nên đặt toàn bộ khả năng chịu lỗi vào scaling sau sự cố. Quota, VM availability, thời gian startup và warm-up có thể khiến RTO vượt mục tiêu.

**“Health probe xanh là giao dịch nghiệp vụ thành công.”** Một process có thể trả HTTP 200 nhưng không ghi được dữ liệu. Cần kết hợp readiness, synthetic transactions và SLI người dùng.

**“Mất zone là mất region.”** Một lỗi zone có phạm vi nhỏ hơn sự cố toàn region. Nên cách ly và xử lý đúng phạm vi; dùng đa region khi yêu cầu chịu lỗi cấp region.

**“Zone 1 luôn cùng vị trí vật lý giữa mọi subscription.”** Nhãn zone logic có thể ánh xạ khác nhau; phải kiểm tra khi triển khai phụ thuộc vị trí vật lý xuyên subscription.

## 14. Tổng kết kiến thức áp dụng

Thiết kế theo Availability Zone là thiết kế **toàn bộ luồng phục vụ** để một zone có thể ngừng hoạt động mà hệ thống vẫn đáp ứng mục tiêu nghiệp vụ. Hãy phân bố compute, bảo đảm frontend và các phụ thuộc dữ liệu có cơ chế chịu lỗi zone, tính N-1 capacity, dùng health probe và retry an toàn, sau đó chứng minh kết quả bằng quan sát và diễn tập.

Trong hệ sinh thái Azure, lựa chọn vùng, subscription, resource group, Entra ID/RBAC, VNet, compute, storage, database và monitoring phải được xem như **một kiến trúc thống nhất**. Một mẫu Bicep hoặc một tùy chọn zone redundancy trên từng resource chỉ có ý nghĩa khi những phần còn lại của hệ thống cũng hoạt động đúng trong kịch bản lỗi cục bộ.
