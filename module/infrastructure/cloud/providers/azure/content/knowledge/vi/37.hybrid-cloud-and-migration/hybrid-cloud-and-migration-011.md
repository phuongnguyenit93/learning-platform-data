# Azure Resource Mover và kế hoạch chuyển tài nguyên giữa region

Một hệ thống đang hoạt động ổn định ở một Azure region có thể cần chuyển sang region khác do yêu cầu lưu trú dữ liệu, độ trễ tới khách hàng, sáp nhập hạ tầng, thay đổi kiến trúc hoặc kế hoạch ngừng sử dụng một địa điểm triển khai. Tuy nhiên, **chuyển region không giống đổi resource group**: tài nguyên điện toán, mạng, địa chỉ IP, đĩa, dữ liệu và các dịch vụ liên quan có thể phải được tạo mới, đồng bộ, cấu hình lại và chuyển lưu lượng theo một kế hoạch có thời gian gián đoạn được kiểm soát.

Trong chương **Hybrid cloud và di chuyển lên Azure** của lộ trình **CLOUD_PROVIDERS_AZURE**, bài học này giải thích vai trò của **Azure Resource Mover**, cách khảo sát khả năng hỗ trợ và dependency, thiết kế đích đến, tổ chức các giai đoạn di chuyển, kiểm thử, cutover, rollback và dọn tài nguyên nguồn. Bài học liên kết kiến thức về Azure subscription, resource group, Microsoft Entra ID, Virtual Network, máy ảo, lưu trữ, database, giám sát, bảo mật, độ tin cậy và kiểm soát chi phí.

**Nguyên tắc xuyên suốt:** công cụ có thể tự động hóa một số thao tác hạ tầng, nhưng **ứng dụng chỉ được xem là di chuyển thành công khi dữ liệu, kết nối, chức năng nghiệp vụ và tiêu chí vận hành đã được xác minh**.

> **Lưu ý về phạm vi:** Khả năng hỗ trợ của Azure Resource Mover phụ thuộc loại tài nguyên, source/target region, subscription, trạng thái dịch vụ và các giới hạn tại thời điểm triển khai. Các tài nguyên, thao tác, thời gian và chi phí trong bài là ví dụ minh họa. Trước khi thực hiện trên hệ thống thật, phải xác minh tính năng/điều kiện được hỗ trợ trong chính tenant và subscription đích. Bài học không yêu cầu tự động di chuyển tài nguyên production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **cross-region resource move**, **resource group/subscription move**, **replication**, **failover** và **disaster recovery**.
2. Giải thích vai trò của Azure Resource Mover, move collection, dependency validation, prepare, initiate move, commit và cleanup.
3. Lập inventory cho compute, disk, mạng, danh tính, dữ liệu, backup, DNS, ứng dụng và những tài nguyên không được công cụ hỗ trợ trực tiếp.
4. Chọn **Resource Mover**, phương án triển khai lại bằng Infrastructure as Code hoặc cơ chế migration/failover riêng của dịch vụ.
5. Thiết kế source/target region, resource group, network topology, quota, RBAC, naming, monitoring và chính sách dữ liệu.
6. Lập kế hoạch đồng bộ dữ liệu, migration waves, runbook cutover và phương án quay lui an toàn.
7. Tính sơ bộ băng thông, thời gian sao chép, capacity dự phòng và chi phí chạy song song hai region.
8. Thiết kế bài thử nghiệm và điều kiện **go/no-go** trước khi đưa hệ thống vào hoạt động ở region mới.

## 2. Hiểu chính xác “chuyển resource giữa region”

Azure region là khu vực địa lý có hạ tầng cung cấp các dịch vụ Azure. Không phải mọi dịch vụ hoặc SKU đều có ở mọi region, và không phải tài nguyên nào cũng hỗ trợ thay đổi trường **location** sau khi tạo.

| Hoạt động | Mục tiêu | Điều không nên giả định |
| --- | --- | --- |
| **Chuyển resource group** | Thay đổi nhóm quản lý tài nguyên trong phạm vi được hỗ trợ | Không có nghĩa tài nguyên được chuyển sang region khác |
| **Chuyển subscription** | Thay đổi phạm vi quản lý/billing của tài nguyên được hỗ trợ | Không tự thay location hoặc giải quyết mọi dependency |
| **Cross-region move** | Chuyển workload/tài nguyên đến region đích, thường phải có đại diện/tài nguyên ở đích | Không phải thao tác đổi nhãn location tại chỗ |
| **Replication** | Đồng bộ dữ liệu hoặc trạng thái giữa hai nơi | Không tự chuyển DNS/traffic hoặc quyền sở hữu ghi |
| **Failover/DR** | Khôi phục dịch vụ sau sự cố theo RTO/RPO đã thiết kế | Không tự động là kế hoạch chuyển region lâu dài |
| **Rebuild/redeploy** | Tạo hệ thống mới bằng IaC và nạp dữ liệu | Không tự bảo đảm trạng thái, identity, IP và dữ liệu được giữ nguyên |

**Azure Resource Mover** hướng tới việc lập kế hoạch, kiểm tra dependency và điều phối một số thao tác **di chuyển tài nguyên Azure giữa các region**. Nó không phải công cụ chuyển mọi dịch vụ Azure, cũng không thay thế backup, dịch vụ khôi phục sau thảm họa hoặc bản thiết kế hoạt động đa vùng.

### 2.1. “Region move” khác “high availability”

Một hệ thống có thể chuyển thành công sang region mới nhưng chỉ có một VM và một database. Khi đó nó **vẫn có thể có điểm lỗi đơn**. Để đạt khả năng chịu lỗi, phải thiết kế Availability Zone, khả năng dự phòng, backup, replication và vận hành tương ứng với dịch vụ đích.

Ngược lại, ứng dụng dùng dịch vụ dữ liệu nhiều region có thể **failover** khi có sự cố mà không dùng Resource Mover để chuyển từng VM. Chọn công cụ theo mục tiêu, không lấy tên tính năng làm kiến trúc.

## 3. Khi nào nên xem xét Azure Resource Mover?

Một tình huống điển hình là nhóm vận hành một số Azure VM và tài nguyên mạng phụ thuộc, muốn chuyển workload từ region A sang region B đã được duyệt, hạn chế thao tác thủ công và có khả năng theo dõi từng bước di chuyển.

**Có thể xem xét Resource Mover khi:**

- Workload đang nằm trong Azure, thuộc các loại tài nguyên mà tính năng cross-region move hỗ trợ.
- Source/target region và subscription phù hợp với điều kiện công cụ.
- Các tài nguyên phụ thuộc có thể được phát hiện, bổ sung hoặc xử lý bằng phương án bổ trợ.
- Có kế hoạch cutover và quyền kiểm soát thời điểm chuyển traffic.
- Chủ ứng dụng chấp nhận thời gian chuẩn bị, replication và khoảng gián đoạn nếu cần.

**Không nên mặc định dùng Resource Mover cho:**

- Toàn bộ dữ liệu của mọi dịch vụ PaaS như database managed, Cosmos DB hay Storage Account.
- Workload cần thay đổi cấu trúc ứng dụng lớn hoặc chuyển hệ điều hành/runtime.
- Một hệ thống cần failover tự động thường trực với RTO/RPO được cam kết.
- Nhu cầu chuyển resource group mà không thay region.
- Tình huống tài nguyên không hỗ trợ đích đến hoặc có dependency không thể thay đổi.

Trong các trường hợp đó, hãy khảo sát dịch vụ đích và cơ chế riêng như **triển khai lại bằng Bicep/Terraform**, replication/backup-restore của database, **Azure Site Recovery** khi phù hợp cho chiến lược DR/migration, hoặc công cụ di chuyển dữ liệu chuyên dụng. Các cơ chế này có phạm vi và điều kiện sử dụng khác nhau, không phải những lựa chọn tương đương có thể thay thế tùy tiện.

## 4. Các khái niệm cốt lõi của Resource Mover

| Khái niệm | Ý nghĩa | Vai trò trong kế hoạch |
| --- | --- | --- |
| **Source region** | Region hiện chứa tài nguyên đang hoạt động | Xác định nguồn dữ liệu, cấu hình và traffic |
| **Target region** | Region dự kiến chạy workload sau chuyển | Kiểm tra SKU, quota, bảo mật, network, capacity |
| **Move collection** | Tập hợp metadata/tài nguyên di chuyển được quản lý trong Resource Mover | Theo dõi phạm vi, dependency và tiến độ |
| **Move resource** | Đại diện cho tài nguyên được đưa vào kế hoạch di chuyển | Theo dõi trạng thái thao tác của từng thành phần |
| **Dependency validation** | Kiểm tra những tài nguyên liên quan được yêu cầu cho kế hoạch | Phát hiện tài nguyên thiếu, xung đột hoặc điều kiện chưa đạt |
| **Target settings** | Thiết lập tương ứng ở region đích theo loại resource | Kiểm soát đích đến, tên, network hoặc cấu hình phù hợp |
| **Prepare** | Bước chuẩn bị đích hoặc dữ liệu/replication khi loại tài nguyên yêu cầu | Tạo điều kiện trước cutover |
| **Initiate move** | Bắt đầu thao tác chuyển đích theo cơ chế của loại tài nguyên | Một trong những bước then chốt của chuyển region |
| **Commit move** | Hoàn tất/xác nhận thao tác move của tài nguyên theo quy trình hỗ trợ | Phân biệt hoàn tất thao tác với rollback/discard khi còn khả thi |
| **Cleanup** | Xử lý tài nguyên nguồn, bản sao và đối tượng tạm sau xác nhận | Chấm dứt dual-run cost và tránh resource rác |

Tên thao tác/trạng thái được hiển thị có thể khác theo loại tài nguyên và giao diện công cụ. **Không phải mọi resource có cùng thứ tự hoặc cùng tập thao tác Prepare → Initiate move → Commit**. Cần đi theo trạng thái hiện tại và hướng dẫn chi tiết cho loại tài nguyên đó, thay vì chạy một quy trình chung cho mọi item.

### 4.1. Resource Mover không “xóa source ngay”

Quy trình chuyển có thể tạo tài nguyên hoặc bản sao ở region đích, trong khi resource nguồn vẫn còn. Việc **commit** và việc **xóa/dọn resource ở nguồn** phải được hiểu là những trách nhiệm khác nhau theo tài nguyên và giai đoạn.

Hậu quả vận hành quan trọng:

- Hai region có thể tạo **chi phí đồng thời** trong một khoảng thời gian.
- Có thể tồn tại disk, NIC, IP, backup hoặc resource tạm không còn phục vụ workload.
- Việc xóa source quá sớm có thể làm mất đường quay lui hoặc vi phạm retention.
- Việc giữ source không kiểm soát có thể tạo tình trạng **hai hệ thống cùng nhận ghi**, gây xung đột dữ liệu.

Do đó, **không xóa tài nguyên nguồn chỉ vì portal đã hiện bước move thành công**. Phải qua kiểm thử ứng dụng, phê duyệt và kế hoạch dọn dẹp riêng.

## 5. Khảo sát tài nguyên trước khi chuyển

Đầu vào quan trọng nhất là **inventory đúng theo workload**, không chỉ danh sách tài nguyên của resource group.

| Nhóm | Cần ghi nhận | Câu hỏi trước khi chuyển |
| --- | --- | --- |
| **Subscription/Resource group** | IDs, tên, RBAC, tags, policy, locks | Có quyền và cấu trúc đích phù hợp không? |
| **Compute** | VM name, size, OS/image, zone/availability, extension, boot diagnostics | Size, image và thành phần phụ có ở target region không? |
| **Disk** | OS/data disks, size/tier, encryption, snapshot, backup, throughput | Có đủ performance/quota và cơ chế bảo vệ dữ liệu không? |
| **Network** | VNet, subnet, NSG, route table, NIC, load balancer, public IP, gateway | CIDR/DNS/routing có xung đột hoặc đổi không? |
| **Identity** | Managed identity, service principal, RBAC, AD/Entra dependencies | Principal ID/quyền có cần cấp lại không? |
| **Secrets/Keys** | Key Vault, certificate, CMK, secret references | Workload ở region mới truy cập được key không? |
| **Data** | Database, file share, object storage, backup, logs | Công cụ nào sẽ chuyển từng phần dữ liệu? |
| **Application** | URLs, webhooks, client allowlists, cron, integration endpoints | Client và đối tác có biết điểm đến mới không? |
| **Observability** | Alerts, diagnostic settings, dashboards, logs, SLO | Có phát hiện lỗi ngay sau cutover không? |
| **Business** | Owners, peak time, downtime window, RTO/RPO, critical transactions | Khi nào có thể chuyển và bằng chứng nghiệm thu là gì? |

### 5.1. Inventory mẫu

~~~csv
workload,resource,source_region,type,owner,move_path,dependency_status
orders,orders-vm01,region-a,VirtualMachine,orders-team,resource-mover,candidate
orders,orders-vnet,region-a,VirtualNetwork,platform-team,resource-mover,review
orders,orders-osdisk,region-a,ManagedDisk,orders-team,resource-mover,review
orders,orders-db,region-a,ManagedDatabase,dba-team,service-native,pending
orders,orders-keyvault,region-a,KeyVault,security-team,separate-design,pending
orders,orders-dns,global-or-external,DNS,network-team,traffic-cutover,pending
~~~

Đây là **danh mục ví dụ để luyện kế hoạch**, không phải danh sách xác nhận các resource được Resource Mover hỗ trợ. Cột **move_path** là lựa chọn ban đầu cần xác minh theo từng loại resource và source/target.

### 5.2. Thu thập thông tin bằng lệnh chỉ đọc

Ví dụ Azure CLI giúp xác nhận đúng subscription và lấy danh sách ban đầu:

~~~bash
az account show \
  --query "{subscription:id,tenant:tenantId,name:name}" \
  -o json

az resource list \
  --resource-group rg-orders-source \
  --query "[].{name:name,type:type,location:location,id:id}" \
  -o table

az vm list \
  --resource-group rg-orders-source \
  --query "[].{name:name,size:hardwareProfile.vmSize,location:location}" \
  -o table
~~~

Các lệnh giả định bạn đã đăng nhập, được cấp quyền đọc và **rg-orders-source** tồn tại. Chúng **không di chuyển tài nguyên** và không cung cấp đầy đủ dependency graph. Chỉ dùng tên resource group thực đã được phê duyệt, tránh trộn subscription nếu có nhiều tenant.

Không thu thập khóa truy cập, mật khẩu, connection string hoặc private key vào file inventory. Ghi thông tin tham chiếu và owner để kiểm tra theo kênh bảo mật phù hợp.

## 6. Kiểm tra khả năng hỗ trợ và điều kiện tiên quyết

Trước khi tạo kế hoạch move, người phụ trách phải lập **ma trận compatibility**. Không chỉ kiểm tra “VM có thể chuyển” mà phải kiểm tra **toàn bộ cấu hình và dependency**.

### 6.1. Những điều kiện cần kiểm chứng

1. **Resource type:** loại tài nguyên, SKU, tính năng phụ, extension và trạng thái có được Resource Mover hỗ trợ hay không.
2. **Source/target region:** cặp region có khả dụng, dịch vụ đích có hỗ trợ model, size, availability options và các tính năng đã chọn.
3. **Subscription:** đăng ký Resource Provider theo yêu cầu, trạng thái subscription và ranh giới hỗ trợ của thao tác.
4. **RBAC:** danh tính thực thi có đủ quyền tối thiểu ở resource nguồn, move collection, resource group và resource đích không.
5. **Quota/capacity:** số vCPU theo VM family, disk, IP, NIC, subnet address space và quota riêng của dịch vụ.
6. **Policy/locks:** Azure Policy có chặn loại/tier/region không; delete/resource locks có làm thao tác không thể hoàn tất không.
7. **Network:** CIDR, subnet, NSG, UDR, DNS, private endpoint, public IP, firewall/allowlist và đường outbound.
8. **Data/security:** mã hóa disk, customer-managed key, backup, replication, resource identity và dữ liệu có được phép đặt ở đích.
9. **Operations:** tính sẵn sàng của monitoring, log, bảo vệ dữ liệu, quy trình patch và incident handling sau move.
10. **Rollback:** phương pháp khôi phục/cutback cụ thể cho loại workload, bao gồm dữ liệu đã ghi mới ở đích.

Không nên “sửa lỗi” quyền bằng cách cấp **Owner trên toàn subscription** nếu chỉ thiếu một quyền cần thiết. Thiết lập role theo least privilege và tuân thủ mô hình phê duyệt của tổ chức.

### 6.2. Kiểm tra region và quota

Ví dụ một VM source dùng size **Standard_D8s_v5** (chỉ là size minh họa). Trước khi chọn target, cần kiểm tra VM size đó có mặt và có **capacity thực tế** tại region/zone mong muốn. Giá có thể khác giữa hai region.

**Quota khác capacity availability:** có đủ quota 32 vCPU không bảo đảm Azure có thể cấp bốn VM cùng size tại thời điểm cần thiết. Hãy kiểm tra trước và chuẩn bị phương án SKU tương đương nếu phù hợp với workload.

### 6.3. Chính sách cư trú dữ liệu và compliance

Chuyển workload qua region có thể làm thay đổi nơi dữ liệu được xử lý/lưu trữ, bao gồm:

- Disk và các bản replica/tạm của quá trình di chuyển.
- Backup, snapshot, log, diagnostic data và nơi đặt key.
- Đường truyền tới dịch vụ phụ trợ hoặc region dự phòng.
- Cách xử lý dữ liệu bởi dịch vụ quản lý tương ứng.

**Không coi hai region trong cùng quốc gia hoặc khu vực địa lý là tự động tương đương về pháp lý.** Quyết định phải dựa vào chính sách tổ chức, phân loại dữ liệu và đặc điểm dịch vụ đích.

## 7. Dependency graph: phần dễ bị bỏ sót nhất

Một VM thường phụ thuộc vào NIC, subnet, VNet, NSG, route, disk, identity và một số dịch vụ ngoài resource group. Nếu chỉ chọn VM, quá trình validate có thể phát hiện thiếu thành phần cần thiết; nhưng **không nên giả định công cụ sẽ phát hiện mọi dependency ở cấp ứng dụng**.

~~~mermaid
flowchart LR
    U["Người dùng"] --> DNS["DNS / Front Door / Gateway"]
    DNS --> LB["Load balancer"]
    LB --> VM["VM ứng dụng"]
    VM --> DISK["OS + data disks"]
    VM --> NIC["NIC"]
    NIC --> SUB["Subnet / VNet"]
    SUB --> NSG["NSG / routing / firewall"]
    VM --> DB["Database PaaS"]
    VM --> KV["Key Vault / managed identity"]
    VM --> EXT["API đối tác / IP allowlist"]
    VM --> MON["Monitoring / backup"]
~~~

### 7.1. Ba loại dependency cần tách

| Loại | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Infrastructure dependency** | VM → NIC → subnet/VNet; VM → disk | Xác minh có trong move plan và target settings |
| **Service dependency** | VM → Azure SQL, Storage, Key Vault, Service Bus | Xác định phương pháp riêng, đồng bộ, network, RBAC |
| **Business/external dependency** | VM → payment provider, DNS, identity, mail relay | Lập runbook và xác nhận với owner/đối tác |

### 7.2. Ma trận dependency mẫu

| Nguồn → Đích phụ thuộc | Critical? | Dự kiến ở region đích | Kiểm tra |
| --- | --- | --- | --- |
| Orders VM → NIC/VNet | Có | VNet/subnet mới hoặc tương thích | Route, NSG, DHCP/DNS, IP |
| Orders VM → data disk | Có | Disk tương ứng theo phương án hỗ trợ | Data integrity, performance, encryption |
| Orders API → database | Có | PaaS replica/migration riêng | Giao dịch, consistency, failover |
| Orders API → Key Vault | Có | Vault/secret/identity plan | RBAC, key access, private endpoint |
| Orders API → payment partner | Có | HTTPS outbound từ region mới | IP allowlist, certificate, idempotency |
| Users → API endpoint | Có | DNS/gateway switch | TTL, cache DNS, TLS, health probes |
| VM → backup/monitoring | Có | Backup/alerts mới hoặc điều chỉnh | Restore test, alerts, log routing |

Nếu database và API trao đổi nhiều truy vấn tuần tự, để database ở source region sau khi chuyển VM có thể khiến latency tăng mạnh. Nên **đo số round-trip và RTT thực** trước khi tách chúng thành hai wave.

## 8. Thiết kế kiến trúc đích trước khi thao tác

Không nên tạo move collection rồi mới quyết định địa chỉ mạng, permission hoặc nơi lưu dữ liệu. Hãy có một **target architecture** được phê duyệt trước.

~~~mermaid
flowchart TB
    subgraph SRC["Source region"]
      S_APP["Orders VM + NIC + disks"]
      S_VNET["VNet, subnet, NSG"]
      S_DB["Database và dữ liệu nguồn"]
      S_APP --> S_VNET
      S_APP --> S_DB
    end
    subgraph DST["Target region"]
      T_APP["VM/compute target"]
      T_VNET["VNet, subnet, NSG, firewall"]
      T_DB["Database target theo kế hoạch riêng"]
      T_MON["Monitor, backup, identity, Key Vault"]
      T_APP --> T_VNET
      T_APP --> T_DB
      T_APP --> T_MON
    end
    RM["Azure Resource Mover / move collection"] -. "Điều phối tài nguyên đủ điều kiện" .-> T_APP
    RM -. "Dependency/target settings" .-> T_VNET
    S_APP -. "Move/replication tùy resource" .-> RM
    S_DB -. "DB native migration/replication" .-> T_DB
    IN["DNS / ingress / client routing"] -. "Cutover có phê duyệt" .-> T_APP
~~~

### 8.1. Thiết kế network

Trong target region cần xác định:

- VNet/subnet address spaces; tránh CIDR overlap với mạng nguồn nếu cần peering, VPN hoặc ExpressRoute.
- NSG/UDR/firewall và việc phân tách public/private subnets.
- Private endpoints và private DNS zones; **không mặc định private endpoint ở region nguồn có thể dùng y nguyên ở đích**.
- Public ingress, WAF/gateway, health probes, certificate và DNS.
- NAT/outbound IP; kiểm tra allowlist của đối tác và giới hạn egress.
- Kết nối hybrid hoặc cross-region tạm thời trong giai đoạn dual-run.

**Có thể phải thay IP hoặc endpoint.** Hãy thiết kế cutover qua DNS, routing hoặc load balancing thay vì hardcode IP của tài nguyên nguồn. Không giả định mọi public IP, private IP, Resource ID hoặc tên tài nguyên được giữ nguyên sau move; xác minh cho loại resource và target settings cụ thể.

### 8.2. Identity và secret

Không chỉ sao chép VM rồi cho rằng quyền đã giữ nguyên. Khi resource được tạo lại, **system-assigned managed identity**, principal hoặc quan hệ RBAC có thể cần thiết lập lại. User-assigned identity, role assignments, service principal, certificate, Key Vault references và chính sách private network cần được kiểm tra theo cách thức hỗ trợ của từng tài nguyên.

Các kiểm tra tối thiểu:

1. Workload đăng nhập bằng cơ chế nào và có secret hardcode không.
2. Quyền đọc Storage/database/Key Vault có đúng phạm vi ở đích không.
3. Key/certificate có còn hiệu lực và có thể truy cập từ network đích không.
4. Logs và audit trail có phản ánh danh tính mới khi cần không.
5. Các vai trò tạm trong quá trình migration đã được thu hồi sau cutover chưa.

Không export password hoặc private key vào log, ảnh chụp portal hay file inventory.

## 9. Quy trình Resource Mover theo các giai đoạn

Một quy trình có kiểm soát gồm **khảo sát → thêm tài nguyên → xác minh dependency → chuẩn bị → move → commit/cleanup**, song các bước cụ thể có thể khác theo resource type.

~~~mermaid
flowchart TD
    A["Lập inventory và xác minh support"] --> B["Chọn source/target, tạo move collection"]
    B --> C["Thêm tài nguyên và kiểm tra dependencies"]
    C --> D{"Dependency và target settings hợp lệ?"}
    D -->|"Không"| E["Bổ sung resource / đổi cấu hình / chọn phương án khác"]
    E --> C
    D -->|"Có"| F["Prepare khi resource yêu cầu"]
    F --> G["Initiate move theo trạng thái resource"]
    G --> H["Kiểm thử target và cutover ứng dụng"]
    H --> I{"Business & technical checks đạt?"}
    I -->|"Không"| J["Khắc phục / rollback hoặc roll forward theo runbook"]
    I -->|"Có"| K["Commit theo quy trình hỗ trợ"]
    K --> L["Xác nhận ổn định, dọn source và artifacts"]
~~~

### 9.1. Bước 1 — Thiết lập move collection

Trong Azure Portal, tìm **Azure Resource Mover** hoặc trải nghiệm **Move → Move to another region** nếu khả dụng cho tài nguyên. Chọn source, target, subscription/resource group theo phạm vi hỗ trợ, tạo hoặc dùng move collection theo hướng dẫn giao diện.

**Điều kiện cần trước thao tác:** có change ticket, danh sách tài nguyên đã duyệt, thông tin chủ sở hữu, thời gian thực hiện, quyền thực thi, budget và người trực vận hành. Nếu portal không cho chọn target hoặc tài nguyên báo unsupported, đó là thông tin assessment quan trọng; **không cố vượt kiểm tra bằng cách dùng công cụ không rõ tác động**.

### 9.2. Bước 2 — Thêm tài nguyên và kiểm tra dependencies

Chọn các resource thuộc workload; dùng khả năng **validate dependencies** để tìm các thành phần thiếu được công cụ nhận diện. Khi một VM cần VNet hoặc tài nguyên hỗ trợ, thực hiện bổ sung/thiết lập theo hướng dẫn và kiểm tra cấu hình đích.

Tại bước này cần ghi:

- Tên/ID của từng source resource.
- Loại resource và trạng thái hỗ trợ.
- Target settings sẽ sử dụng.
- Các dependencies đã xử lý trong công cụ.
- Các dependencies **không được công cụ quản lý** và runbook tương ứng.

**Dependency check pass không đồng nghĩa application dependency pass.** Hãy thử đường gọi database, identity, external API và các batch hiếm gặp bằng phương pháp bổ sung.

### 9.3. Bước 3 — Prepare

Với loại resource yêu cầu, bước **Prepare** thiết lập các điều kiện để chuyển đích: có thể liên quan đến tạo hạ tầng, kiểm tra trạng thái hoặc cơ chế đồng bộ/replication. Một số resource có thể cần thao tác chuẩn bị khác hoặc không có cùng bước này.

Trước khi tiếp tục:

- Xem trạng thái từng resource và lỗi dependency.
- Kiểm tra vùng đích đủ VM/disk/network capacity.
- Xác nhận dữ liệu đang được đồng bộ theo phương pháp áp dụng.
- Ghi nhận initial sync/backlog/replication health nếu có.
- Đối chiếu chi phí tạm thời do hai region/replica cùng tồn tại.

Không suy luận rằng **Prepare thành công = workload sẵn sàng phục vụ user**. Ứng dụng, database, DNS và identity có thể chưa được chuyển.

### 9.4. Bước 4 — Initiate move

**Initiate move** là hành động tiến hành chuyển đích cho tài nguyên đủ điều kiện theo trạng thái công cụ. Với workload có trạng thái, đây có thể là điểm yêu cầu điều phối cutover hoặc downtime, tùy loại tài nguyên/cơ chế di chuyển.

Người vận hành cần:

1. Xác nhận go/no-go trước thao tác gây ảnh hưởng.
2. Đảm bảo dependency và đường chuyển dữ liệu đã sẵn sàng.
3. Thực hiện thao tác theo thứ tự mà công cụ/resource type yêu cầu.
4. Theo dõi move status, Azure Activity Log và hệ thống quan sát.
5. Không để hai hệ thống cùng ghi lên một dữ liệu nếu chưa có thiết kế dual-write hợp lệ.

**Thao tác move hạ tầng không đồng nghĩa cutover DNS hoặc ứng dụng thành công.** Có thể cần những bước ngoài Resource Mover để chuyển traffic.

### 9.5. Bước 5 — Commit và hoàn tất

Sau khi target đã được kiểm tra, thao tác **Commit** theo quy trình hỗ trợ xác nhận bước move. Hãy đọc chính xác hậu quả và khả năng **Discard/rollback** trên trạng thái của từng resource trước khi bấm.

**Không xem Commit là bảo đảm rollback tự động về trạng thái cũ.** Sau commit, việc quay lại region nguồn có thể yêu cầu một dự án migration ngược hoặc rebuild/restore, đặc biệt khi hệ thống mới đã nhận các bản ghi mới.

### 9.6. Bước 6 — Cleanup

Sau thời gian hypercare và được chủ ứng dụng phê duyệt, dọn:

- Compute, disks, NICs, public IP, VNet resources không còn dùng ở source.
- Snapshot, recovery artifacts, temporary storage và kết nối tạm.
- Backup/monitoring rule, alert và endpoint cũ; giữ lại audit cần thiết.
- Role assignments/permissions/identities tạm phục vụ migration.
- Move collection/metadata tạm theo vòng đời và hướng dẫn công cụ.

**Không xóa bằng suy đoán từ tên.** Xác minh Resource ID, dependencies và quyền sở hữu từng tài nguyên. Giữ nguồn đủ thời gian theo chính sách backup, retention và khả năng rollback; sau đó giải phóng tránh chi phí kép.

## 10. Phân biệt loại tài nguyên được move và loại phải dùng phương án riêng

Đánh giá phải làm ở cấp **resource type + cấu hình**. Bảng sau là hướng tiếp cận, không phải danh sách hỗ trợ cố định của Azure Resource Mover:

| Thành phần | Đường di chuyển cần khảo sát | Lưu ý |
| --- | --- | --- |
| **Azure VM và các phụ thuộc cơ sở hạ tầng** | Resource Mover nếu loại/config/region được hỗ trợ | Sizing, disks, NIC, VNet, availability, encryption |
| **VNet/subnet và network resources** | Resource Mover cho các loại đủ điều kiện hoặc triển khai lại bằng IaC | CIDR, NSG, UDR, peering, private DNS, IP |
| **Azure SQL Database/Managed Instance** | Khả năng replication, failover/migration/backup-restore riêng của dịch vụ | Compatibility, dữ liệu, logins, downtime, failover |
| **Azure Storage** | Các cơ chế copy/object replication/backup hoặc migration dữ liệu phù hợp | Namespace, consistency, ACL, tier, lưu lượng, dữ liệu mới |
| **Azure Cosmos DB** | Tính năng region/replication và migration theo mô hình tài khoản/dữ liệu | Consistency, write region, RU/s, failover strategy |
| **App Service/Functions** | Deploy lại hạ tầng và ứng dụng; cơ chế backup/migration phù hợp | Settings, secrets, custom domains, slots, plan và state |
| **AKS/Container Apps** | Dựng môi trường/cluster mới bằng IaC, triển khai workload và chuyển dữ liệu | Container registry, secrets, network, ingress, persistent volumes |
| **Key Vault/managed identities** | Thiết kế vùng đích và kế hoạch key/secret/RBAC riêng | Không mặc định copy được private key, principal hoặc quyền |
| **DNS/Front Door/APIM/third-party** | Kế hoạch traffic/endpoint và chuyển cấu hình phù hợp | TTL, certificate, custom domains, routing, IP allowlist |

Một số công cụ được mô tả có thể thay đổi chức năng hoặc không áp dụng cho biến thể dịch vụ bạn dùng. Luôn xác minh điều kiện hỗ trợ trước khi chọn cách triển khai.

### 10.1. Vì sao không nên đưa cả hệ thống PaaS vào một move collection rồi kỳ vọng tất cả đi theo?

Database có dữ liệu thay đổi liên tục, Storage có semantics consistency riêng, dịch vụ định danh và chứng chỉ có quyền truy cập nghiêm ngặt. Các thành phần này có thể cần **replication ở tầng dịch vụ**, kiểm thử tích hợp và cutover ngoài Resource Mover. Bước di chuyển VM có thể thành công, nhưng API vẫn lỗi nếu connection string trỏ về database cũ.

Vì vậy, lập hai danh sách song song:

1. **Resource Mover-managed items:** đã được xác nhận hỗ trợ và có trạng thái trong move collection.
2. **Externally managed items:** database, secrets, DNS, application release, network policy hoặc những thành phần khác cần runbook riêng.

## 11. Thiết kế dữ liệu và downtime

### 11.1. Di chuyển VM không có nghĩa database đã chuyển

Với ứng dụng stateful:

- Chụp ảnh hiện trạng OS/data disk theo chính sách.
- Xác định dữ liệu nào ở disk VM và dữ liệu nào ở PaaS database/storage.
- Đo thời gian initial sync và tốc độ thay đổi dữ liệu.
- Thiết kế **final sync/quiesce writes** khi cutover.
- Kiểm tra consistency bằng row counts, checksums, transaction IDs và invariants nghiệp vụ.
- Lập kế hoạch xử lý request đang chạy, cron jobs, queue consumers và background tasks.

Nếu sử dụng replication, phải kiểm tra **replication lag và checkpoint thực**, không coi biểu tượng “Healthy” là bằng chứng RPO bằng 0. Nếu downtime chỉ cho phép vài phút, initial copy cần hoàn tất từ trước và cutover phải được diễn tập.

### 11.2. RTO, RPO và cutover downtime

| Chỉ số | Ý nghĩa | Ví dụ mục tiêu |
| --- | --- | --- |
| **RTO** | Thời gian khôi phục dịch vụ sau sự cố | 2 giờ |
| **RPO** | Mức mất dữ liệu cho phép khi có sự cố | 15 phút |
| **Planned downtime** | Khoảng gián đoạn cho phép khi chuyển có kế hoạch | 30 phút |
| **Cutover execution time** | Thời gian thực thi chuyển traffic/dữ liệu và xác minh | Phải đo khi rehearsal |
| **Hypercare** | Giai đoạn theo dõi tăng cường sau chuyển | Ví dụ 48 giờ, tùy độ quan trọng |

RTO/RPO cho DR không đồng nhất với planned downtime của migration. Một workload có RTO 2 giờ vẫn có thể yêu cầu cutover không quá 10 phút trong giờ kinh doanh.

### 11.3. Single writer và dữ liệu sau cutover

Khi chuyển database hoặc dịch vụ ghi, quyết định rõ **nguồn nào có quyền ghi tại mỗi thời điểm**. Nếu ứng dụng ở region mới ghi giao dịch mà hệ thống cũ không được đồng bộ ngược, việc đổi DNS về nguồn cũ **không phục hồi những giao dịch đó**.

Nếu cần rollback dữ liệu sau khi target nhận ghi, phải có **reverse replication, transaction replay, reconciliation hoặc roll-forward plan** đã thử nghiệm. Với quy trình không có reverse path an toàn, cần nêu rõ điểm **không thể rollback bằng thao tác đơn giản** trước khi cấp phép cutover.

## 12. Ước lượng thời gian sao chép và kết nối liên vùng

Quá trình di chuyển có thể bị giới hạn bởi network, tốc độ đọc nguồn/ghi đích, số lượng file, service throttling, encryption và tốc độ dữ liệu phát sinh mới.

Phương pháp gần đúng:

\[
T_{\text{copy}} \approx
\frac{\text{Dung lượng cần truyền (bit)}}{\text{Throughput hữu dụng (bit/giây)}}
\]

### 12.1. Ví dụ 2 TiB trên liên kết 250 Mbit/s

Giả sử lượng dữ liệu cần copy là **2 TiB** và throughput danh nghĩa dành cho hoạt động copy là **250 Mbit/s**:

\[
2\ \mathrm{TiB} = 2\times2^{40}\ \text{byte}
\]

\[
T_{\text{lý tưởng}} =
\frac{2\times2^{40}\times8}{250\times10^6}
\approx70.369\ \text{giây}
\approx19{,}55\ \text{giờ}
\]

Nếu hiệu suất hữu dụng chỉ đạt **60%** thì:

\[
250\times60\%=150\ \text{Mbit/s}
\]

\[
T_{\text{ước lượng}}\approx19{,}55/0{,}6\approx32{,}58\ \text{giờ}
\]

Đây là **ước lượng giáo dục**, không phải thời gian Resource Mover hoặc Azure Site Recovery cam kết. Quá trình thực có thể nhanh/chậm khác do replication engine, thay đổi dữ liệu, read/write IOPS, bottleneck và nhiều tài nguyên chạy đồng thời.

### 12.2. Dữ liệu thay đổi khi đang sao chép

Nếu nguồn liên tục ghi **15 MiB/s** trong quá trình sync, một vòng copy nền có thể đi cùng một backlog thay đổi lớn. Phải đo:

- Tốc độ thay đổi dữ liệu theo giờ và lúc peak.
- Throughput replication hữu dụng và giới hạn tài nguyên nguồn/đích.
- Backlog/lag tại thời điểm dự kiến cutover.
- Thời gian final sync khi dừng ghi.
- Cơ chế xử lý write consistency trên database hoặc file system.

Chỉ nhìn kích thước disk mà không xét tốc độ ghi thường dẫn đến kế hoạch downtime không khả thi.

## 13. Quota, capacity và những ràng buộc không hiển thị trên sơ đồ

Mỗi region có tình trạng capacity và giới hạn khác nhau. Những mục cần kiểm tra:

- **vCPU quota** theo VM family và region; VM size/zone thực có sẵn.
- **Disk SKU, performance tier**, IOPS/throughput yêu cầu, giới hạn theo VM.
- **IP address space** đủ cho số NIC/VM/Pod trong giai đoạn đồng thời.
- **Network topology** có thể route qua peering/hybrid mà không CIDR overlap.
- **Azure Policy** có cho phép resource type/SKU/region đích.
- **Subscription limits** của public IP/load balancer và dịch vụ liên quan.
- **Resource names** có tính duy nhất toàn cục hoặc điều kiện đặc biệt theo từng provider.
- **Capacity for failover/scale**, không chỉ capacity ở tải bình thường.
- **Giới hạn concurrency/throttling của dịch vụ** trong giai đoạn copy.

### 13.1. Ví dụ sizing

Workload source dùng **3 VM × 8 vCPU**. Target cần chạy đồng thời ba VM tương đương, tức ít nhất **24 vCPU theo family phù hợp**, chưa tính hạ tầng thử nghiệm, HA và scale. Nếu còn một VM dự phòng 8 vCPU, phải dự trù **32 vCPU** và kiểm tra từng size/zone.

**Tính toán vCPU là điều kiện cần, không đủ.** Disk throughput, memory, database, IP, capacity thực và SLO có thể là bottleneck. Nếu target SKU khác, phải benchmark lại thay vì giả định tăng/giảm số vCPU tuyến tính với throughput.

## 14. Ước tính chi phí di chuyển và giai đoạn chạy song song

Chi phí của dự án không chỉ là giá VM ở target region. Một số nhóm chi phí:

| Khoản | Nguồn tăng phí tiềm năng | Cách kiểm soát |
| --- | --- | --- |
| **Dual-run compute** | VM/app ở cả source và target cùng tồn tại | Giới hạn cửa sổ, kế hoạch cleanup |
| **Disks và snapshots** | Bản sao disk, snapshot hoặc staging storage | Inventory, retention và cleanup |
| **Replication/transfer** | Dữ liệu di chuyển, bandwidth, các thành phần replication | Kiểm tra giá/điều kiện dịch vụ cụ thể |
| **Network** | Cross-region traffic, gateway, NAT, public IP, load balancer | Thiết kế topology và đo data flow |
| **Observability** | Log ingestion ở hai region, duplication, alert | Kiểm soát sampling/retention phù hợp |
| **Database dual-run** | Hai database/replica cùng được tính phí | Chọn thời gian đồng bộ, scale và chốt cutover |
| **Backup/DR** | Vault, backup storage, điểm khôi phục | Duy trì an toàn nhưng tránh trùng không cần thiết |
| **Labor/risk** | Nhân sự, trực ngoài giờ, thử nghiệm, downtime | TCO và risk budget |

Không khẳng định một thao tác Resource Mover có “giá bằng 0” cho toàn bộ workload. Dù chi phí điều phối riêng của dịch vụ có thể khác theo chính sách hiện hành, **tài nguyên nguồn/đích, replication, transfer và dịch vụ phụ** vẫn cần tính theo meter thực tế.

### 14.1. Mô hình ngân sách giả định

Giả sử trong **7 ngày** chạy song song, nguồn và đích có các khoản giả định:

| Khoản chi minh họa | Số tiền giả định |
| --- | ---: |
| Compute ở source trong 7 ngày | 420 USD |
| Compute ở target trong 7 ngày | 455 USD |
| Disk/replica/snapshot bổ sung | 95 USD |
| Network/replication phát sinh | 70 USD |
| Monitoring bổ sung | 20 USD |
| **Subtotal** | **1.060 USD** |
| Dự phòng sai số 20% | 212 USD |
| **Ngân sách minh họa** | **1.272 USD** |

Những con số này **không phải báo giá Azure**, chỉ để minh họa cách dự phòng chi phí. Cần thay bằng Azure Pricing Calculator, điều kiện giá hợp đồng, Cost Management và dữ liệu đo thực tế. Không tính trùng các meter đã nằm trong hạng mục khác.

### 14.2. Số tiền không phải tiêu chí duy nhất

Một phương án tiết kiệm được vài trăm USD nhưng tăng rủi ro mất giao dịch hoặc kéo dài downtime có thể không phù hợp với ứng dụng quan trọng. Cần cân bằng **chi phí, RTO/RPO, bảo mật, workload performance và năng lực vận hành**.

## 15. Migration waves và thứ tự di chuyển

Không nên chuyển tất cả VM/network/database cùng lúc khi chưa thử nghiệm. Hãy chọn các wave theo **dependency** và độ quan trọng nghiệp vụ:

| Wave | Nội dung | Điều kiện vào | Điều kiện thoát |
| --- | --- | --- | --- |
| **0 – Foundation** | Target subscription/RG, network, identity, policy, quota, backup, monitoring | Kiến trúc được duyệt | Kết nối, quyền, alert, restore test đạt |
| **1 – Pilot** | Một workload phi trọng yếu | Inventory/rollback rõ | Chuyển và xác minh thành công |
| **2 – Infrastructure dependencies** | Những tài nguyên đủ điều kiện cần tồn tại ở target | Validation và target settings đạt | Đích và dependencies sẵn sàng |
| **3 – Application/data** | VM/app, database migration riêng, jobs | Data sync và cutover rehearsal đạt | Functional/integration/data test đạt |
| **4 – Traffic cutover** | DNS/gateway, external allowlist, single writer | Go/no-go được duyệt | SLO và nghiệp vụ đạt |
| **5 – Stabilization & cleanup** | Hypercare, tối ưu, gỡ source | Business sign-off và chính sách retention | Không còn dependency nguồn; chi phí kép được dọn |

**Thứ tự hạ tầng có thể khác thứ tự business wave.** Một VNet target có thể phải có sẵn trước khi VM target được tạo; database phải đồng bộ trước khi API có thể chuyển ghi; DNS chuyển sau khi service thực sự healthy. Resource Mover hướng dẫn dependency theo tài nguyên được quản lý, còn **migration lead** phải xác định dependency ứng dụng.

### 15.1. Chọn pilot tốt

Một pilot phù hợp có owner rõ, dữ liệu giả hoặc ít nhạy cảm, thời gian phục hồi chấp nhận được, dependency đơn giản và có phương án quay lui. Pilot phải kiểm tra được **thao tác thật** như resource move, target settings, DNS, monitoring và cleanup, chứ không chỉ khởi tạo VM rỗng.

## 16. Chuẩn bị cutover: mẫu runbook có trách nhiệm

### 16.1. Bảng trước cutover

| Mốc | Công việc | Bằng chứng | Owner |
| --- | --- | --- | --- |
| **T−14 ngày** | Chốt danh sách, target settings, compatibility, licensing | Assessment và owner sign-off | Migration lead |
| **T−7 ngày** | Hoàn thành landing zone, quota, identity/network | Test network, RBAC và restore | Platform/Security |
| **T−3 ngày** | Đồng bộ nền/Prepare cho loại resource phù hợp | Move state, replication lag, checks | Infra/DBA |
| **T−1 ngày** | Kiểm thử rehearsal, check backup và rollback | Kết quả đo downtime, data checks | App/DBA/SRE |
| **T−30 phút** | Go/no-go, đóng thay đổi, thông báo user | Approval + contact list | Business/Operations |
| **T0** | Ngừng/giới hạn ghi, final sync theo phương án | Checkpoint, queue status, transaction state | App/DBA |
| **T+** | Initiate move/cutover theo trạng thái và plan | Resource operation state, functional smoke tests | Platform/App |
| **T+** | Chuyển DNS/gateway/traffic, quan sát | Endpoint health, TLS, API, auth | Network/SRE |
| **T+** | Kiểm tra dữ liệu, batch, SLO, external integrations | Reconciliation, dashboard, error rate | App/QA/Business |
| **Sau hypercare** | Commit/cleanup theo hỗ trợ và chính sách | Sign-off, backup, inventory cleanup | Migration lead |

Các mốc trên là **mẫu lập kế hoạch**, không phải thời lượng được Azure Resource Mover bảo đảm. Với resource type có thứ tự thao tác đặc biệt, phải tuân thủ tài liệu/giao diện công cụ thay vì ép cùng một thứ tự.

### 16.2. Go/no-go

**Go** khi:

- Source/target region, SKU, quota, network và security đã được kiểm tra.
- Tài nguyên trong move collection không còn dependency blocker.
- Database/data migration riêng đạt checkpoint và lag cho phép.
- Backups và restore đã được kiểm thử.
- SLO/cutover time và rollback/run-forward được diễn tập.
- Chủ ứng dụng, DBA, Network, Security và Operations đã xác nhận phạm vi trách nhiệm.

**No-go** nếu:

- Resource type/target không được hỗ trợ và chưa có phương án khác.
- VNet/DNS/IP gây lỗi hoặc xung đột chưa giải quyết.
- Replication lag vượt giới hạn mất dữ liệu/downtime.
- Không có bản backup có thể restore hoặc chưa kiểm tra dữ liệu quan trọng.
- Payment/webhook/AD/certificate dependency chưa xác minh.
- Không có cách xử lý dữ liệu mới nếu buộc quay về source sau cutover.

## 17. Kiểm thử sau khi tài nguyên đã xuất hiện ở region mới

Một move hạ tầng thành công chưa phải nghiệm thu ứng dụng. Kiểm thử phải có số liệu và chủ sở hữu:

| Loại test | Ví dụ kiểm tra | Tiêu chí |
| --- | --- | --- |
| **Infrastructure** | VM health, attached disks, NIC/VNet, DNS, availability | Cấu hình mục tiêu đúng, tài nguyên healthy |
| **Network/security** | TLS, NSG/firewall, private endpoint, RBAC, managed identity | Đúng đường truy cập; không mở quyền quá rộng |
| **Functional** | Đăng nhập, tạo đơn, đọc/ghi file, tác vụ nền | Luồng critical pass |
| **Data integrity** | Counts/checksum/invariants giao dịch | Không mất hoặc nhân đôi dữ liệu đã xác nhận |
| **Performance** | Peak RPS, latency p95/p99, CPU, DB throughput | Đạt SLO đã thống nhất |
| **Operations** | Logs, alerts, backup job, restore rehearsal | Nhóm SRE vận hành và xử lý sự cố được |
| **Resilience** | Mất replica/zone, recovery, retry, failover | Đạt tiêu chí HA/DR riêng |
| **Business** | Payment sandbox, email/webhook, đối soát báo cáo | Owner xác nhận |
| **Cost** | Chi phí chạy kép, resource rác, egress | Trong ngân sách, có cleanup plan |

### 17.1. Ví dụ acceptance matrix

Giả sử Orders API trước move xử lý **120 RPS peak**, p95 **350 ms**, dữ liệu ghi không được mất và planned downtime không quá **30 phút**.

| Chỉ số | Mục tiêu | Kết quả test giả định | Trạng thái |
| --- | ---: | ---: | --- |
| Peak throughput | ≥120 RPS | 132 RPS | Đạt |
| API p95 | ≤400 ms | 365 ms | Đạt |
| Functional critical flows | 100% luồng bắt buộc | 100% | Đạt |
| Giao dịch đã xác nhận bị mất | 0 | 0 sau đối soát | Đạt |
| Cutover downtime | ≤30 phút | 24 phút | Đạt |
| Backup restore test | Bắt buộc | Chưa hoàn tất | **Chưa nghiệm thu** |
| Outbound allowlist partner | Bắt buộc | Chưa được xác nhận | **No-go** |

Các số này chỉ là ví dụ. **Không được tuyên bố thành công** khi restore hoặc tích hợp quan trọng còn chưa có bằng chứng, dù VM và các API chính đã hoạt động.

## 18. Rollback, Discard và roll forward

### 18.1. Ba hành động khác nhau

| Hành động | Mục đích | Phải kiểm tra |
| --- | --- | --- |
| **Discard move** | Hủy một thao tác move chưa hoàn tất khi resource/trạng thái hỗ trợ | Có còn khả năng discard? Các bản sao/metadata sẽ bị xử lý thế nào? |
| **Rollback/cutback ứng dụng** | Đưa traffic hoặc chức năng trở lại hệ thống nguồn | Source còn nguyên vẹn, dữ liệu mới đã được xử lý chưa? |
| **Roll forward** | Khắc phục trên đích hoặc triển khai bước tiếp để hệ thống đích hoạt động | Có bảo vệ dữ liệu và giới hạn tác động không? |

**Discard của Resource Mover không phải cơ chế hoàn tác mọi giao dịch nghiệp vụ.** Sau commit hoặc khi target đã nhận dữ liệu mới, có thể phải lập kế hoạch migration ngược hoặc phục hồi dữ liệu riêng; không giả định có nút rollback tức thì.

### 18.2. Đường quay lui theo thời điểm

1. **Trước khi target nhận ghi:** thông thường dễ giữ source làm hệ thống chính hơn; vẫn phải kiểm tra thao tác hạ tầng đã được commit/đổi trạng thái đến đâu.
2. **Đang chuyển traffic:** cần tạm dừng các tác vụ gây ghi, xác định request in-flight và đảm bảo chỉ một nơi được xem là nguồn dữ liệu chính.
3. **Sau khi target nhận ghi:** phải xử lý giao dịch mới bằng reverse sync/replay hoặc chọn roll forward.
4. **Sau khi xóa source:** không còn đường cutback dựa trên source cũ; phụ thuộc backup/restore hoặc migration mới.

Nếu không thể bảo toàn giao dịch đã xác nhận khi rollback, **không được mô tả kế hoạch đó là rollback an toàn**. Quyết định no-go hoặc chuyển sang roll-forward cần được phê duyệt trước.

## 19. Giám sát trong và sau khi chuyển region

### 19.1. Ba lớp quan sát

**Lớp Resource Mover:** trạng thái move collection/resource, dependency validation, lỗi thao tác và thời gian thực hiện. Sử dụng màn hình công cụ, Azure Activity Log và khả năng diagnostics theo dịch vụ khi được hỗ trợ.

**Lớp hạ tầng:** VM availability, CPU, memory, disk latency/IOPS, VNet connection, network latency, load balancer probe, backup và status của các tài nguyên đích.

**Lớp ứng dụng/nghiệp vụ:** request success, latency p95/p99, payment callback, queue age, database replication lag, số giao dịch đã xác nhận và các invariants dữ liệu.

Không dùng **Azure Resource Mover move status** làm chỉ số thay thế cho SLO ứng dụng. Công cụ có thể hoàn tất thao tác trong khi endpoint HTTPS hoặc database vẫn không hoạt động.

### 19.2. Dashboard trước cutover

| Metric | Source | Target | Ngưỡng/ý nghĩa |
| --- | --- | --- | --- |
| Request latency p95 | Baseline | Test/cutover | Không vượt mục tiêu nghiệm thu |
| Business success rate | Baseline | Live | Không giảm quá ngưỡng |
| Database replication lag | Theo cơ chế dữ liệu | Theo cơ chế dữ liệu | Phải đạt mức cho phép trước final sync |
| Network RTT | Đã đo | Đã đo | Nhận diện cross-region chatty calls |
| Disk latency | Peak baseline | Target measured | Đánh giá SKU/IOPS |
| Error/timeout | Source history | Target live | Kích hoạt rollback/no-go theo policy |
| Backup/restore status | Source | Target | Bắt buộc đủ bằng chứng |
| Cost by region | Source cost | Target cost | Theo dõi dual-run và cleanup |

Nên dùng Azure Monitor/Application Insights/OpenTelemetry khi có thể, gắn version/region/instance để so sánh. Không đưa secret, token hoặc dữ liệu giao dịch nhạy cảm vào telemetry.

## 20. Tình huống tổng hợp: Orders chuyển từ region A sang region B

### 20.1. Hiện trạng

Một hệ thống đơn hàng gồm:

- **2 Azure VM** phục vụ API, dùng NIC/data disk và VNet riêng.
- **Load balancer và public endpoint** nhận request.
- **Managed database PaaS** phục vụ giao dịch.
- **Key Vault** lưu secret; API dùng danh tính quản lý.
- **Log Analytics/Application Insights** theo dõi vận hành.
- Một đối tác thanh toán chỉ cho phép outbound IP đã đăng ký.

Mục tiêu: chuyển ứng dụng sang region B vì kế hoạch quản trị dữ liệu và giảm độ trễ tới người dùng mới. Chấp nhận planned downtime **tối đa 30 phút**, không được mất giao dịch đã xác nhận, yêu cầu vẫn đạt **120 RPS** và p95 dưới **400 ms**.

### 20.2. Chiến lược theo thành phần

| Thành phần | Chiến lược đề xuất | Điều kiện trước triển khai |
| --- | --- | --- |
| VM, disks và network đủ điều kiện | Đánh giá và dùng Resource Mover | Hỗ trợ loại resource/region, dependency, target settings |
| Database | Phương án migration/replication native được hỗ trợ | Consistency, schema, write freeze, failover, data checks |
| Key Vault, identity, secrets | Thiết kế/cấu hình đích riêng theo cơ chế hỗ trợ | Quyền, key access, private networking |
| Public endpoint | DNS/gateway/traffic cutover có kiểm soát | Certificate, health probe, rollback strategy |
| Partner IP allowlist | Điều chỉnh qua phối hợp với đối tác | IP egress target được chấp thuận |
| Monitoring/backup | Deploy/configure phù hợp tại target | Alert, logging, restore test |

### 20.3. Migration waves

**Wave 0 — Foundation:** tạo VNet/subnet, cấu hình routing và security, xác nhận quota và target access, chuẩn bị monitoring/backup. Tổ chức có thể dùng IaC cho phần resource không thích hợp với Resource Mover, nhưng phải tránh tạo trùng tài nguyên mà công cụ cũng định tạo.

**Wave 1 — Pilot:** thử một VM không critical có cùng kiểu kết nối. Ghi những thao tác thực tế, thời gian từng trạng thái và lỗi gặp phải.

**Wave 2 — Sync:** hoàn thành move collection/validation và chuẩn bị hạ tầng, database replication theo phương án riêng. Đo replication lag, bandwidth, disk IO và verify secrets.

**Wave 3 — Cutover:** quiesce writes, final sync và checks; chuyển VM/app và traffic theo runbook, kiểm tra TLS, DNS, payment, dữ liệu và SLO.

**Wave 4 — Hypercare & cleanup:** giữ source trong thời hạn đã duyệt nếu còn cần, theo dõi chi phí kép; sau business sign-off thực hiện commit/cleanup theo trạng thái công cụ và chính sách dữ liệu.

### 20.4. Các blocker phải giải quyết

- Chưa xác nhận SKU VM đích và quota/capacity thực.
- Database đích chưa có phương án đồng bộ/failover được thử.
- Identity ở target chưa có quyền đọc Key Vault hoặc database.
- Network VNet/subnet target xung đột CIDR với link hybrid.
- Đối tác chưa duyệt outbound IP mới.
- Không có test restore và kế hoạch khôi phục giao dịch sau cutover.
- Không có dấu mốc “single writer” khi đồng bộ dữ liệu.

Nếu một blocker liên quan bảo toàn dữ liệu chưa được xử lý, **không cho production go-live**, dù giao diện Resource Mover cho phép initiate move.

## 21. Một mẫu kế hoạch di chuyển có thể kiểm toán

~~~yaml
planId: orders-cross-region-illustration
source:
  region: region-a
  resourceGroup: rg-orders-source
target:
  region: region-b
  resourceGroup: rg-orders-target
workloadOwner: commerce-team
migrationLead: platform-team
moveMethod:
  infrastructure: resource-mover-for-verified-supported-items
  database: separately-validated-service-native-migration
  dnsAndTraffic: controlled-cutover
goals:
  maxPlannedDowntimeMinutes: 30
  maxLostConfirmedTransactions: 0
  peakRpsAtLeast: 120
  latencyP95MsAtMost: 400
dependencies:
  - target-network
  - keyvault-and-identity
  - managed-database
  - payment-egress-allowlist
  - monitoring-and-backup
requiredEvidence:
  - dependency-validation
  - backup-restore-test
  - database-reconciliation
  - performance-rehearsal
  - business-approval
  - rollback-or-rollforward-plan
cleanup:
  sourceDeletionRequiresBusinessSignoff: true
  trackTemporaryResources: true
~~~

Đây là **manifest lập kế hoạch minh họa** do bài học định nghĩa, không phải JSON/YAML có thể gửi trực tiếp vào Azure Resource Mover API. Cần bổ sung tên/ID thực, người duyệt, deadline, runbook và thông số hỗ trợ đã xác minh ở dự án thật.

### 21.1. Mẫu risk register

| ID | Rủi ro | Tác động | Biện pháp và bằng chứng | Owner |
| --- | --- | --- | --- | --- |
| RM-01 | VM SKU không đủ capacity tại target | Chậm/không tạo được VM | Kiểm tra region/SKU/zone/quota; PoC | Platform |
| RM-02 | Thiếu VNet/NSG dependency | Move bị chặn hoặc API không có mạng | Validate dependency + test routing | Network |
| RM-03 | Replication không bắt kịp thay đổi dữ liệu | Downtime vượt 30 phút | Đo lag và final sync rehearsal | DBA |
| RM-04 | Managed identity/RBAC thay đổi | Ứng dụng bị từ chối truy cập | Test identity tại target | Security/App |
| RM-05 | DNS/IP mới không được đối tác tin cậy | Payment lỗi | Cấp trước endpoint/IP, chạy integration test | Integration |
| RM-06 | Xóa source khi chưa đủ bằng chứng | Không thể quay lui, mất dữ liệu | Business sign-off và cleanup gate | Migration lead |
| RM-07 | Cả hai region cùng nhận ghi | Duplicate/conflict | Single-writer protocol và đối soát | DBA/App |
| RM-08 | Dual-run lâu hơn dự kiến | Tăng chi phí | Budget, deadline và owner cleanup | FinOps |

## 22. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không chọn được target region | Cặp region hoặc resource type chưa hỗ trợ | Xem compatibility và chọn phương án khác |
| Validate báo thiếu dependency | VM liên quan NIC, VNet, disk hoặc resource khác chưa được thêm | Bổ sung/resolve theo hướng dẫn, không bỏ qua |
| Target VM size không tạo được | Quota, SKU hoặc capacity/zone không phù hợp | Kiểm tra quota, target SKU/zone và capacity thực |
| Prepare thất bại | Quyền, trạng thái resource, replication, policy/lock | Xem lỗi theo item, kiểm tra RBAC và trạng thái nguồn/đích |
| Initiate move bị lỗi | Resource chưa đủ trạng thái hoặc dependency không sẵn sàng | Theo dõi move status; không retry mù nhiều thao tác gây tác động |
| VM ở target hoạt động nhưng app không có mạng | DNS, route, NSG, UDR, firewall, private endpoint | Test từng hop và đường outbound |
| App chạy nhưng database chậm | Cross-region latency và nhiều round-trip | Đo RTT, query fan-out, cân nhắc chuyển DB cùng wave |
| Lỗi 403 khi đọc Storage/Key Vault | Identity/role assignment/private network chưa đúng | Kiểm tra principal, scope, secret reference, network |
| Partner payment trả timeout/403 | IP allowlist/certificate/endpoint thay đổi | Phối hợp đối tác, xác nhận egress IP |
| Resource move thành công nhưng DNS chưa chuyển | Traffic cutover là bước riêng | Thực hiện runbook DNS/gateway với health checks |
| Rollback làm thiếu giao dịch | Target đã nhận ghi, source chưa sync ngược | Dừng thay đổi, đối soát và thực hiện data recovery plan |
| Tài nguyên nguồn vẫn bị tính phí | Chưa cleanup disks, IP, VM, backup hoặc artifact | Inventory sau sign-off và xóa có kiểm soát |
| Cost tăng trong ngày move | Dual-run, snapshot, data transfer và logging | Đối chiếu Cost Management theo hai region |
| Monitoring không thấy lỗi target | Diagnostic settings/agent/alerts chưa cấu hình | Test end-to-end telemetry trước go-live |

**Không xử lý lỗi bằng cách cấp Owner toàn subscription hoặc tắt toàn bộ Azure Policy, NSG, diagnostic logging.** Nếu cần ngoại lệ tạm, phải giới hạn phạm vi và thời gian với người có thẩm quyền phê duyệt.

## 23. Bài thực hành: lập kế hoạch Resource Mover an toàn

Thực hành dựa trên một **workload giả định** gồm 2 VM, VNet, NIC, disks và một database PaaS riêng. Không yêu cầu thao tác phá hủy hay di chuyển tài nguyên thật.

### Bài A — Inventory và phân loại

1. Tạo bảng các tài nguyên như phần 5.
2. Đánh dấu resource nào **cần xác minh hỗ trợ Resource Mover**, resource nào cần migration theo dịch vụ và resource nào chỉ cần đổi traffic.
3. Ghi owner, dữ liệu nhạy cảm, RBAC, VM size, disk capacity, network và endpoint.
4. Tạo dependency graph từ người dùng tới VM, database, Key Vault và payment provider.

**Tiêu chí đạt:** không tự kết luận tất cả resource đều được Resource Mover hỗ trợ chỉ vì cùng thuộc một resource group.

### Bài B — Đánh giá target

1. Chọn source region và target region **được tổ chức cho phép**.
2. Kiểm tra SKU/availability, vCPU quota, disk performance, policy và network CIDR.
3. Thiết kế VNet/subnet/NSG/route, DNS, TLS và outbound allowlist cho target.
4. Đề xuất cách cấu hình Key Vault/managed identity và giám sát.

**Tiêu chí đạt:** có ma trận compatibility với cột **verified, pending, unsupported** và không che blocker.

### Bài C — Vẽ runbook theo trạng thái

1. Chia tài nguyên thành những item quản lý bằng Resource Mover và những item cần runbook ngoài công cụ.
2. Mô tả bước move collection, dependency validation, target settings, Prepare/Initiate move/Commit **theo điều kiện của từng loại tài nguyên**.
3. Đánh dấu những bước thay đổi dịch vụ và những bước chỉ chuẩn bị.
4. Xác định thời điểm quiesce writes và cutover DNS/gateway.
5. Nêu điều kiện được phép cleanup resource nguồn.

**Tiêu chí đạt:** không đánh đồng “Move completed” với “Application accepted” hoặc “Source safe to delete”.

### Bài D — Tính thời gian và capacity

Giả sử phải sao chép 2 TiB, throughput 250 Mbit/s và hiệu suất hữu dụng 60%. Tính thời gian truyền lý tưởng, thời gian gần đúng theo hiệu suất và liệt kê tối thiểu bốn yếu tố có thể làm sai lệch thực tế.

**Kết quả tham khảo:** **19,55 giờ** lý tưởng và **32,58 giờ** nếu chỉ đạt 60% throughput. Cần thêm IOPS, replication lag, nguồn ghi mới và giới hạn dịch vụ.

### Bài E — Diễn tập tình huống không được rollback tùy tiện

Giả sử sau cutover 15 phút, target đã nhận **500 đơn hàng đã xác nhận**, trong khi source không được đồng bộ ngược. Ứng dụng ở target xuất hiện lỗi 5xx tăng mạnh.

1. Vì sao đổi DNS về source ngay có thể làm mất khả năng xem 500 đơn?
2. Cần thu bằng chứng gì trước khi dừng ghi hoặc quyết định roll forward?
3. Có thể dùng reverse sync/replay nào, và điều kiện nào phải được thử trước?
4. Ai có quyền quyết định no-go hoặc phục hồi theo runbook?

**Tiêu chí đạt:** phương án không làm mất/nhân đôi giao dịch đã xác nhận và phân biệt quay lại hạ tầng với quay lại trạng thái dữ liệu.

### Bài F — Báo cáo go/no-go

Lập bảng các điều kiện:

- Target region/SKU/quota.
- Dependency validation và target settings.
- Database consistency và replication lag.
- Identity, DNS, payment allowlist, security.
- Functional, performance, backup restore và cost budget.
- Rollback/roll-forward capability và người duyệt.

Đánh dấu điều kiện nào **chưa có bằng chứng**. Kết luận chỉ được “Go” khi tất cả hard gates đã đạt theo quy trình tổ chức.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Azure Resource Mover có thể thay đổi location của mọi dịch vụ Azure chỉ bằng một nút bấm không?  
**Đáp án:** Không. Phải kiểm tra loại resource, region, dependency và nhiều thành phần có thể cần migration/redeploy riêng.

**Câu 2.** Chuyển resource group có đồng nghĩa chuyển region không?  
**Đáp án:** Không. Đó là thay đổi phạm vi tổ chức/quản lý; cross-region move là bài toán khác.

**Câu 3.** Move collection giúp ích gì?  
**Đáp án:** Quản lý phạm vi các resource đủ điều kiện, dependency và trạng thái thao tác của quá trình move.

**Câu 4.** Dependency validation thành công có bảo đảm API gọi được payment provider không?  
**Đáp án:** Không. Công cụ không tự chứng minh mọi phụ thuộc nghiệp vụ; phải kiểm tra DNS, certificate, outbound IP, network và API.

**Câu 5.** Tại sao không xóa source ngay khi thấy Move completed?  
**Đáp án:** Vì ứng dụng, dữ liệu, backup và integrations vẫn cần nghiệm thu, nguồn có thể còn giá trị rollback và cleanup phải theo retention/owner approval.

**Câu 6.** Database PaaS có bắt buộc đi theo cùng Resource Mover collection với VM không?  
**Đáp án:** Không. Phải chọn phương pháp riêng được dịch vụ/database hỗ trợ và kiểm thử consistency/cutover.

**Câu 7.** Vì sao quota VM đủ vẫn có thể tạo VM đích thất bại?  
**Đáp án:** Quota không bảo đảm SKU/zone/capacity thực tế có sẵn hoặc policy/limit của dịch vụ cho phép.

**Câu 8.** Tại sao nên có overall downtime goal và replication lag threshold riêng?  
**Đáp án:** Downtime là thời gian gián đoạn người dùng; lag phản ánh dữ liệu chưa đồng bộ. Chúng khác nhau nhưng cùng quyết định thời điểm cutover an toàn.

**Câu 9.** Cutback DNS sau khi target nhận ghi có phải rollback an toàn không?  
**Đáp án:** Không, nếu source chưa có dữ liệu mới. Cần reverse data strategy hoặc roll forward có kiểm chứng.

**Câu 10.** Bước Commit có mặc định xóa toàn bộ source và đảm bảo khôi phục mọi giao dịch không?  
**Đáp án:** Không. Phải kiểm tra semantics theo resource/state, còn cleanup và dữ liệu nghiệp vụ là trách nhiệm riêng.

**Câu 11.** 2 TiB qua 250 Mbit/s trong điều kiện lý tưởng cần khoảng bao lâu?  
**Đáp án:** Khoảng 19,55 giờ, chưa tính overhead và dữ liệu thay đổi.

**Câu 12.** Vì sao cần budget dual-run?  
**Đáp án:** Source và target cùng tồn tại có thể phát sinh phí compute, disk, replication, network và logging; cleanup chậm sẽ kéo dài chi phí.

**Câu 13.** Nếu Azure Resource Mover không hỗ trợ một tài nguyên, nên làm gì?  
**Đáp án:** Ghi blocker và đánh giá migration/redeploy/replication riêng của dịch vụ hoặc thay kiến trúc, không cố bỏ qua điều kiện hỗ trợ.

**Câu 14.** VM có health check đạt nhưng backup target chưa được thử restore. Migration đã nghiệm thu chưa?  
**Đáp án:** Chưa, nếu kiểm tra restore là điều kiện bắt buộc của workload; trạng thái hạ tầng và readiness vận hành là hai chuyện khác nhau.

## 25. Checklist production trước khi chuyển region

- [ ] Mục tiêu chuyển region, owner, RTO/RPO, downtime window và SLO được phê duyệt.
- [ ] Đã xác minh loại resource, source/target region và điều kiện hỗ trợ Azure Resource Mover.
- [ ] Inventory gồm VM, disks, NIC, VNet, NSG, route, IP, database, secret, identity, DNS, monitoring và backup.
- [ ] Dependency graph được owner xác nhận, có danh sách item ngoài Resource Mover.
- [ ] Có target architecture, naming, subnet/CIDR, DNS, routing, firewall và private connectivity.
- [ ] Đã kiểm tra quota, SKU, capacity, zone availability, Azure Policy và permission.
- [ ] Dữ liệu, backup/log/key và vùng đích phù hợp data classification/compliance.
- [ ] Database và dữ liệu stateful có cơ chế migration/replication riêng được hỗ trợ.
- [ ] Move collection, dependency validation và target settings được kiểm tra.
- [ ] Các bước Prepare/Initiate move/Commit phù hợp trạng thái từng resource.
- [ ] Có rehearsal, replication lag, single-writer protocol và final sync checkpoint.
- [ ] Runbook bao gồm DNS/gateway/partner allowlist, identity/RBAC, health probes và TLS.
- [ ] Có backup đã thử restore và phương án rollback/roll-forward bảo toàn dữ liệu.
- [ ] Functional, integration, performance, security, business và DR checks đã đạt.
- [ ] Dashboard Azure Monitor/Application Insights và người trực đã sẵn sàng.
- [ ] Có budget dual-run, kiểm soát replication/egress và kế hoạch cleanup.
- [ ] Commit và xóa source chỉ thực hiện khi trạng thái hỗ trợ, nghiệm thu và retention cho phép.
- [ ] Có business sign-off, change ticket, bằng chứng giám sát và báo cáo sau migration.

**Kết luận:** Azure Resource Mover hỗ trợ tổ chức và điều phối việc chuyển **những tài nguyên Azure đủ điều kiện** giữa các region, nhưng không thể thay thế khảo sát phụ thuộc, giải pháp chuyển dữ liệu, cutover traffic hay trách nhiệm bảo vệ giao dịch. Một kế hoạch thành công cần kết hợp **compatibility assessment, target architecture, dependency validation, migration waves, kiểm thử, rollback và cleanup có phê duyệt**. Khi xem Resource Mover là một công cụ trong tổng thể kiến trúc hybrid/migration, đội vận hành có thể chuyển region có kiểm soát mà vẫn bảo vệ tính sẵn sàng, dữ liệu, bảo mật và chi phí của ứng dụng.
