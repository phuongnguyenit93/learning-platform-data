# Azure Migrate với discovery, assessment và dependency mapping

## 1. Từ danh sách máy chủ đến kế hoạch di chuyển có căn cứ

Một doanh nghiệp muốn chuyển ứng dụng từ trung tâm dữ liệu nội bộ (*on-premises*) lên Microsoft Azure. Nhóm hạ tầng có danh sách 40 máy ảo, biết tổng CPU và RAM, nhưng chưa biết máy nào thực sự đang hoạt động, máy nào chỉ chạy cuối tháng, ứng dụng nào kết nối vào database nào và liệu một VM có thể được thay bằng dịch vụ PaaS hay không. Nếu chuyển từng máy chỉ dựa vào tên hoặc cấu hình đã cấp phát, nhóm có thể bỏ sót một dependency quan trọng, mua Azure VM quá lớn hoặc di chuyển database trước khi ứng dụng sẵn sàng.

**Azure Migrate** cung cấp một điểm tập trung để **khám phá (discovery)**, **đánh giá (assessment)** và tổ chức việc **di chuyển (migration)** các workload được hỗ trợ lên Azure. Trong bài này, chúng ta đi sâu ba hoạt động trước khi cutover:

1. **Discovery:** biết đang có máy chủ/tài nguyên nào, chúng đang chạy ra sao và metadata có đáng tin không.
2. **Assessment:** xác định tính sẵn sàng, lựa chọn đích, kích thước đề xuất, rủi ro và chi phí ước tính theo giả định cụ thể.
3. **Dependency mapping:** xác định quan hệ giao tiếp giữa máy, ứng dụng và hệ thống phụ thuộc để di chuyển theo nhóm hợp lý thay vì từng máy độc lập.

Trong lộ trình học Azure từ subscription, resource group, Microsoft Entra ID, mạng ảo, compute, storage, dữ liệu đến bảo mật và chi phí, Azure Migrate là cầu nối giữa **môi trường hiện hữu** và **kiến trúc đích đã quản trị**. Nó không thay thế Azure landing zone, thiết kế kết nối hybrid hoặc kiểm thử ứng dụng.

### Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt **Azure Migrate project**, *Discovery and assessment*, *Server Migration* và các công cụ đánh giá workload chuyên biệt.
- Lập kế hoạch discovery cho máy ảo VMware, Hyper-V hoặc máy vật lý/nguồn khác thuộc phạm vi hỗ trợ; hiểu vai trò của appliance, credentials và mạng.
- Tạo assessment cho Azure VM, giải thích chế độ **as-on-premises** và **performance-based**, đọc readiness, sizing, confidence và cost estimate.
- Diễn giải bản đồ dependency theo chiều kết nối, IP/port, tiến trình, khoảng quan sát và hạn chế của dữ liệu.
- Gom các máy liên quan thành **application group** và **migration waves**, chọn pilot, xử lý phụ thuộc còn ở on-premises.
- Định nghĩa acceptance criteria để chuyển từ khám phá sang thử nghiệm di chuyển an toàn.

## 2. Các khái niệm và thành phần của Azure Migrate

~~~mermaid
flowchart TD
    S["Nguồn: VMware / Hyper-V / physical / môi trường được hỗ trợ"] --> A["Azure Migrate appliance hoặc cơ chế khám phá tương ứng"]
    A --> P["Azure Migrate project"]
    P --> D["Discovery: inventory, metadata, performance"]
    D --> AS["Assessment: readiness, sizing, chi phí"]
    D --> DEP["Dependency analysis: kết nối, process, IP/port"]
    AS --> PLAN["Application groups + migration waves"]
    DEP --> PLAN
    PLAN --> TEST["Pilot / test migration"]
    TEST --> CUT["Cutover theo runbook"]
    CUT --> VAL["Kiểm chứng và tối ưu trên Azure"]
~~~

| Thành phần | Vai trò | Điều không nên nhầm lẫn |
| --- | --- | --- |
| **Azure Migrate project** | Nơi tập hợp công cụ, inventory, assessment và dữ liệu liên quan tới chương trình migration | Tạo project không đồng nghĩa đã kết nối hay di chuyển máy |
| **Azure Migrate: Discovery and assessment** | Thu thập nguồn máy chủ, đo mức dùng, đánh giá tính sẵn sàng, kích thước và chi phí của đích hỗ trợ | Không tự tạo Azure VM đích |
| **Azure Migrate appliance** | Thành phần được triển khai tại mạng nguồn để khám phá, thu thập và gửi dữ liệu tới project | Không nhất thiết cài agent vào từng VM chỉ để lấy inventory; yêu cầu thay đổi theo nguồn và tính năng |
| **Assessment** | Tập cấu hình và kết quả tính toán theo lựa chọn target và giả định đo | Không phải cam kết SKU sẽ luôn có quota hoặc giá sẽ cố định |
| **Dependency analysis / mapping** | Phân tích các kết nối và tương tác được quan sát giữa hệ thống | Không phải sơ đồ đầy đủ của toàn bộ luồng nghiệp vụ |
| **Server Migration** | Bộ công cụ riêng cho các bước replication, test migration và cutover máy chủ được hỗ trợ | Khác discovery/assessment; không chạy migration chỉ vì xem kết quả assessment |

Tên tính năng, mục trong Azure Portal, nguồn được hỗ trợ, loại assessment và phương thức dependency analysis có thể thay đổi theo phiên bản dịch vụ. Vì vậy, các hướng dẫn dưới đây tập trung vào **nguyên tắc và quy trình ổn định**, đồng thời yêu cầu xác nhận điều kiện hỗ trợ của nguồn thực tế trong giao diện Azure Migrate đang dùng.

### 2.1 Discovery, assessment, mapping trả lời ba câu hỏi khác nhau

| Câu hỏi | Dữ liệu thích hợp |
| --- | --- |
| Có bao nhiêu server, hệ điều hành gì, vCPU/RAM/disk bao nhiêu? | Inventory từ discovery |
| Azure VM nào có thể chứa workload? Chi phí ước tính ra sao? | Assessment với target region, sizing và pricing assumptions |
| Server web có kết nối tới SQL, file share, DNS hoặc SaaS nào? | Dependency mapping cộng với xác nhận từ chủ ứng dụng |
| Có thể chuyển database mà không ảnh hưởng ứng dụng còn lại không? | Dependency map, sơ đồ ứng dụng, kết quả test và kế hoạch cutover |
| Bao giờ có thể tắt máy nguồn? | Runbook và sign-off sau migration, **không** chỉ một kết quả assessment |

## 3. Tình huống xuyên suốt: ứng dụng Orders ở on-premises

Giả sử một hệ thống đặt hàng có kiến trúc:

| Máy / thành phần | Chức năng | Cấu hình nguồn minh họa | Thông tin cần xác nhận |
| --- | --- | --- | --- |
| `web-01`, `web-02` | Web frontend / reverse proxy | 2 VM, mỗi máy 4 vCPU, 8 GiB RAM | HTTPS, chứng chỉ, session, DNS |
| `api-01`, `api-02` | REST API đặt hàng | 2 VM, mỗi máy 8 vCPU, 16 GiB RAM | TLS, throughput, queue, outbound calls |
| `sql-01` | SQL Server chứa dữ liệu giao dịch | 1 VM, 16 vCPU, 64 GiB RAM | Version/edition, HA, log, I/O, backup, RPO |
| `batch-01` | Job đối soát và xuất báo cáo | 1 VM, 4 vCPU, 8 GiB RAM | Chạy cuối ngày/tháng, file share |
| `files-01` | File share cho báo cáo | 1 máy chủ | SMB/NFS, quyền truy cập, retention |
| `dns-ad-01` | DNS, Active Directory và dịch vụ hạ tầng | 1 hoặc nhiều máy quản trị chung | Domain join, DNS, identity, site-to-site connectivity |
| `payment-partner` | API thanh toán bên ngoài | Không thuộc inventory VM | Egress, firewall allowlist, certificate và thời gian đáp ứng |

Toàn bộ tên và số liệu trong bảng là **dữ liệu giả định để học**, không phải kết quả của một môi trường Azure thực.

~~~mermaid
flowchart LR
    U["Khách hàng"] --> F["Load balancer / DNS nguồn"]
    F --> W["web-01 / web-02"]
    W --> API["api-01 / api-02"]
    API --> DB["sql-01"]
    API --> PAY["Payment API bên ngoài"]
    API --> I["DNS/AD/identity"]
    JOB["batch-01"] --> DB
    JOB --> FILE["files-01"]
~~~

Đây là **sơ đồ giả thuyết** do nhóm ứng dụng cung cấp trước discovery. Mục tiêu của dependency mapping là so sánh những kết nối quan sát được với giả thuyết ấy, phát hiện thêm quan hệ chưa được ghi nhận và quyết định máy nào bắt buộc đi cùng một wave.

## 4. Chuẩn bị scope, quyền và nền tảng Azure

### 4.1 Chốt mục tiêu kinh doanh trước khi thu thập

Hãy xác nhận với các bên liên quan:

- **Trong scope:** máy, ứng dụng, site, VLAN, cluster, database, dữ liệu và các đối tác nào dự kiến chuyển lên Azure?
- **Ngoài scope:** dịch vụ do bên thứ ba quản lý, máy không được phép cài thành phần hỗ trợ, hệ thống OT/legacy nhạy cảm.
- **Mục tiêu:** giảm chi phí trung tâm dữ liệu, tăng resilience, mở rộng, hiện đại hóa hay thoát phần mềm hết hỗ trợ?
- **Giới hạn:** data residency, bảo mật, compliance, hợp đồng license, downtime được phép, RTO/RPO và deadline cutover.
- **Chủ sở hữu:** người duyệt quyền vCenter/Hyper-V, quản trị mạng, ứng dụng, database, bảo mật, tài chính và người điều phối migration.

### 4.2 Chuẩn bị đích Azure

Azure Migrate giúp đánh giá đích, nhưng một migration production còn cần **landing zone**: subscription đúng, management group/policy, resource group, Microsoft Entra ID và RBAC, Azure Virtual Network, subnet, NSG, routing, DNS, private endpoint nếu cần, logging, backup, budget và tagging.

Nếu hệ thống phải giữ kết nối với on-premises trong giai đoạn hybrid, cần thiết kế **site-to-site VPN** hoặc **ExpressRoute** (theo nhu cầu/budget), độ trễ và băng thông, DNS resolution, identity, IP addressing và firewall. Một assessment “Ready” không chứng minh các đường mạng và quyền truy cập này đã hoạt động.

Trước khi tạo project hoặc triển khai appliance, xác định yêu cầu về **vùng lưu metadata**, tính năng hỗ trợ theo region, quota và mô hình quyền của tổ chức. **Region của Azure Migrate project không tự quyết định mọi lựa chọn target region trong assessment**, nhưng phải chọn dựa trên tài liệu hỗ trợ và yêu cầu tuân thủ dữ liệu.

### 4.3 Quyền truy cập và bảo vệ dữ liệu

Áp dụng *least privilege*:

1. Quyền Azure chỉ đủ tạo/quản trị project, đọc assessment và cấu hình thành phần theo vai trò; tách quyền vận hành migration/cutover nếu có thể.
2. Credential nguồn (ví dụ vCenter, Hyper-V hoặc credential guest cần cho software inventory/dependency) chỉ có quyền đúng theo prerequisite, không cấp domain admin chỉ vì tiện lợi.
3. Giữ **project key, credential và cấu hình appliance** trong nơi an toàn; hạn chế ai có thể thấy dữ liệu máy, IP, process và phần mềm đã phát hiện.
4. Kiểm tra outbound connectivity tới các endpoint Azure cần thiết theo cấu hình appliance; không mở inbound rộng hoặc tắt kiểm soát mạng chỉ để “discovery cho nhanh”.
5. Tuân thủ quy định về dữ liệu cá nhân, phân quyền xem báo cáo và retention; dependency map có thể tiết lộ topology và hệ thống bảo mật nhạy cảm.

## 5. Discovery: khám phá máy chủ và thông tin sử dụng

### 5.1 Tạo Azure Migrate project và chọn nguồn

Quy trình tổng quát qua Azure Portal:

1. Đăng nhập đúng tenant và subscription, kiểm tra resource group và khu vực phù hợp.
2. Mở **Azure Migrate**, tạo hoặc chọn **project** theo chương trình (ví dụ `migrate-orders-dc1`), chọn region được hỗ trợ theo yêu cầu lưu trữ dữ liệu.
3. Trong khả năng **Discovery and assessment**, chọn loại nguồn đang dùng: VMware vSphere, Hyper-V, physical hoặc nguồn khác khi dịch vụ hỗ trợ.
4. Xem phương thức discovery tương ứng, requirement của appliance, số lượng server, tài khoản truy cập, cổng mạng và kết nối Azure.
5. Chuẩn bị một appliance phù hợp cho môi trường và **project key/registration** theo luồng hướng dẫn hiển thị; không tự áp dụng appliance image của VMware cho Hyper-V nếu công cụ yêu cầu gói khác.

Điều quan trọng: **create project, register appliance và start discovery không tự di chuyển workload**. Không coi discovery là thay đổi data plane của ứng dụng đích, nhưng appliance vẫn tạo lưu lượng, thu thập metadata và có thể yêu cầu credential/connection tới nguồn.

### 5.2 Vai trò Azure Migrate appliance

Appliance thường được triển khai **gần môi trường nguồn** để có quyền đọc metadata và các metrics cần thiết, sau đó gửi dữ liệu khám phá về Azure Migrate project qua các kết nối được hỗ trợ.

| Nguồn | Cách tiếp cận khái quát | Điểm phải chuẩn bị |
| --- | --- | --- |
| **VMware vSphere** | Appliance liên hệ vCenter để khám phá VM, lấy thông tin cấu hình và hiệu năng; khám phá bên trong guest có thể cần credential riêng | Version/permission của vCenter, kết nối, giới hạn appliance và VMware Tools theo tính năng |
| **Hyper-V** | Appliance hoặc cơ chế khám phá dành cho Hyper-V thu thập inventory/metrics từ host được hỗ trợ | Hyper-V host/cluster, quyền, port và version tương thích |
| **Physical/nguồn khác được hỗ trợ** | Phương thức phát hiện server, dùng quyền/credential và kết nối khác với inventory vCenter | Cơ chế xác thực, OS, firewall, độ đầy đủ của performance data |

**Agentless** trong bối cảnh VMware inventory thường có nghĩa không cần cài agent Azure Migrate lên từng VM để lấy metadata hypervisor. **Không đồng nghĩa** mọi khả năng khám phá ứng dụng, process, database hay dependency đều hoạt động không cần điều kiện trong guest. Một số tính năng hoặc nguồn khác có thể cần agent hoặc credential/extension bổ sung theo hướng dẫn sản phẩm hiện hành.

### 5.3 Các bước thiết lập có thể kiểm tra

1. **Deploy appliance** đúng mẫu/kiểu nguồn, đáp ứng CPU/RAM/disk, hệ điều hành và network theo hướng dẫn của phiên bản hiện tại.
2. **Đăng ký appliance** với project bằng cơ chế và key được cấp; kiểm tra trạng thái kết nối thành công.
3. **Khai báo nguồn**: vCenter/hosts/IP range và credential chỉ đủ quyền theo yêu cầu; kiểm tra không nhập sai site hoặc domain.
4. **Khám phá inventory**: xác minh số VM, tên, UUID/resource key, OS, số vCPU, RAM, disk và network adapters.
5. **Thu thập performance**: để chạy performance-based assessment cần đủ thời gian và metric; kiểm tra trạng thái data collection.
6. **Bật tính năng guest discovery/dependency** nếu được hỗ trợ và có phê duyệt; xác minh software inventory, process và TCP connections có dữ liệu thực.
7. **Theo dõi health appliance**: cảnh báo kết nối, credential hết hạn, server không reachable, metrics thiếu và số đối tượng khám phá thay đổi bất thường.

Đừng chuyển ngay sang assessment khi appliance vừa đăng ký mà chưa đủ lịch sử sử dụng. Một số chỉ số sẽ chỉ có khi đợi đủ chu kỳ thu thập; điều kiện “discovered” và “performance data usable” là **hai trạng thái khác nhau**.

### 5.4 Checklist xác minh discovery

| Kiểm tra | Đạt khi |
| --- | --- |
| Coverage | Số server tìm thấy được so với inventory CMDB/hypervisor; giải thích máy thiếu hoặc phát hiện trùng |
| Identity | Không nhầm hai máy cùng tên ở site khác; xác định key/ID ổn định |
| OS/architecture | OS/version/boot type, vCPU/RAM và cấu hình disk không bị “unknown” vô lý |
| Performance | Có dữ liệu xuyên qua ngày làm việc, batch và peak; biết phần trăm telemetry thiếu |
| Application owner | Mỗi server thuộc ứng dụng, chủ sở hữu và mức độ quan trọng rõ ràng |
| Sensitive scope | Không thu thập/trình bày topology ngoài phạm vi được duyệt |
| Data freshness | Lần cập nhật cuối đủ gần thời điểm ra quyết định |

Ví dụ: CMDB liệt kê 120 VM trong scope, Azure Migrate thấy 116; **coverage = 116/120 × 100% ≈ 96,7%**. Trước khi kết luận đủ dữ liệu, phải tìm 4 VM còn thiếu: máy tắt dài ngày, tài khoản thiếu quyền, VM đặc biệt hoặc inventory chưa cập nhật?

## 6. Assessment: từ inventory tới lựa chọn Azure

### 6.1 Tạo nhóm và assessment

Sau khi đủ discovery, chọn một nhóm server thuộc **một ứng dụng cụ thể**, ví dụ `orders-app`, rồi tạo assessment kiểu Azure VM nếu hướng đi là **rehost**. Một số workload có công cụ assessment chuyên biệt (ví dụ database hoặc web app) theo nguồn/đích được hỗ trợ; đừng dùng kết quả Azure VM assessment để kết luận SQL có thể chuyển thẳng lên Azure SQL Database hay ứng dụng chắc chắn tương thích App Service.

Một assessment cần ghi rõ:

- **Target:** Azure VMs hoặc lựa chọn đích được công cụ hỗ trợ; target region và availability/zone yêu cầu.
- **Sizing criterion:** as-on-premises hoặc performance-based, cùng lịch sử hiệu năng và mức percentile được chọn.
- **Scope:** tập máy nào nằm trong assessment, loại trừ tài nguyên nào và lý do.
- **VM preferences:** series/VM family được phép, OS, storage/disk type, giả định HA, reserved headroom và các đặc tính riêng của workload.
- **Cost assumptions:** vùng đích, currency, license/benefit, pricing option hoặc discount được hỗ trợ trong màn hình assessment.
- **Business constraints:** RTO/RPO, latency, data residency, security, quota, deadline và độ tin cậy của dữ liệu.

**Lưu cấu hình assessment cùng phiên bản** (tên, timestamp, nguồn dữ liệu và giả định); hai assessment trên cùng nhóm server nhưng khác sizing criteria hoặc performance history **không thể so sánh kết quả như cùng một phép tính**.

### 6.2 As-on-premises và performance-based

| Tiêu chí | As-on-premises sizing | Performance-based sizing |
| --- | --- | --- |
| Dữ liệu chính | Năng lực được cấp cho máy nguồn: cores, RAM, disk | Dữ liệu tiêu thụ thực tế trong khoảng thu thập đã chọn |
| Lợi ích | Có thể tạo phương án ban đầu khi còn ít telemetry | Có cơ hội giảm over-provisioned capacity |
| Hạn chế | Giữ nguyên tình trạng cấp phát dư ở on-premises | Có thể đánh giá thấp nếu thiếu peak, batch, guest metric hoặc chưa có đủ lịch sử |
| Khi dùng | Baseline/conservative scenario | Khi dữ liệu đủ tin cậy, có headroom và đã hiểu mùa vụ |

Một vài lựa chọn cấu hình performance-based thường gồm **khoảng lịch sử dữ liệu**, **percentile utilization** và **comfort factor** hoặc hệ số dự phòng, tùy loại assessment. Không coi con số mặc định trong giao diện là chính sách của tổ chức; ví dụ percentile 95 thường bỏ qua 5% mẫu cao nhất, nên không đủ bảo vệ một batch hiếm nhưng tối quan trọng nếu cửa sổ thu thập không có batch ấy.

Ví dụ **minh họa phép suy luận**, không phải công thức nội bộ của Azure Migrate: server nguồn có 8 vCPU, CPU utilization p95 đo được 30%, tương đương nhu cầu CPU xấp xỉ 2,4 vCPU theo cách quy đổi thô. Áp hệ số dự phòng 1,3 cho ra khoảng 3,12 vCPU, gợi ý thử SKU có tối thiểu 4 vCPU. **Kết quả assessment thực** còn phụ thuộc compatibility, disk, RAM, network, SKU, rounding và thuật toán hiện hành; không chọn VM chỉ bằng phép tính này.

### 6.3 Đọc output: readiness, sizing, cost, confidence

| Kết quả | Câu hỏi cần trả lời | Hành động |
| --- | --- | --- |
| **Readiness / suitability** | OS/boot/disk/architecture và tài nguyên có phù hợp đích không? | Kiểm tra lý do *Ready / Ready with conditions / Not ready / Unknown* hoặc trạng thái tương đương theo màn hình |
| **Recommended size** | Loại VM và disk nào được đề xuất theo assessment? | So sánh quota, tính năng, vùng/zone, vCPU/RAM/disk/network limit và growth |
| **Estimated monthly cost** | Chi phí đích ước tính bao nhiêu theo giả định? | Phân biệt compute/storage được tính với mạng, backup, monitoring, data transfer, license và dịch vụ dùng chung |
| **Confidence / data quality** | Kết quả có đủ performance samples? | Bổ sung data collection nếu confidence thấp, máy mới tắt/bật thất thường hoặc telemetry khuyết |
| **Warnings / blockers** | Có OS hết hỗ trợ, disk đặc biệt hoặc cấu hình không tương thích? | Ghi remediation, owner, deadline và phương án thay thế |

**Assessment không phải bằng chứng deployment có thể thành công ngay.** Azure quota, capacity tại thời điểm cấp phát, chính sách doanh nghiệp, quyền, port/firewall, DNS, extension, license và các thay đổi giữa assessment và cutover đều có thể ảnh hưởng kết quả.

### 6.4 Phân tích chi phí đúng cách

Ví dụ **giá học tập hoàn toàn giả định**, không phải bảng giá Azure:

| Nhóm workload | Số máy | Compute + disk ước tính / máy / tháng | Tổng / tháng |
| --- | ---: | ---: | ---: |
| Web | 2 | 140 USD | 280 USD |
| API | 2 | 210 USD | 420 USD |
| SQL VM | 1 | 720 USD | 720 USD |
| Batch | 1 | 170 USD | 170 USD |
| **Tổng máy được đánh giá** | **6** | | **1.590 USD** |

Giả sử thêm **220 USD/tháng** cho VPN/egress, backup, monitoring và dịch vụ dùng chung thuộc phạm vi ước tính, thì tổng ngân sách sơ bộ thành **1.810 USD/tháng**. Con số này vẫn chưa thay thế **Cost Management pricing/calculator**, licensing review hoặc bản dự toán theo tariff thực tế.

Khác biệt giữa **estimated cost** và **actual cost** có thể do workload thay đổi, reservation/savings plans, license, traffic, storage transactions, DR replicas, monitoring ingestion và chi phí vận hành. Bảng ước tính phải ghi ranh giới tính toán.

## 7. Dependency mapping: xác định máy nào thực sự phụ thuộc nhau

Một assessment trả lời “máy nào có thể chuyển tới Azure VM?”. **Dependency mapping** trả lời “nếu chuyển máy này trước, kết nối nào có thể bị đứt?”. Đây là căn cứ để thiết kế migration waves, firewall rules, DNS, chuyển hướng traffic và thứ tự kiểm tra.

### 7.1 Một kết nối được quan sát nói lên điều gì?

Ví dụ quan hệ:

~~~text
Source:      api-01, IP 10.10.20.11
Destination: sql-01, IP 10.10.30.20
Protocol:    TCP
Port:        1433
Observed:    during order-processing test period
Owner:       Orders team
Interpretation: possible SQL Server database connection
~~~

Một bản ghi TCP/IP **không tự chứng minh** đây là SQL transaction quan trọng, và port 1433 có thể được cấu hình khác hoặc dùng bởi ứng dụng khác. Cần ghép **hostname, process, listener/service, connection string, tài liệu ứng dụng và lời xác nhận của owner**.

| Loại thông tin | Cách sử dụng | Bẫy thường gặp |
| --- | --- | --- |
| Source và destination | Xác định máy bắt đầu kết nối và máy được liên hệ | Không suy ra hướng dữ liệu nghiệp vụ chỉ từ hướng TCP |
| IP, port, protocol | Thiết kế NSG, firewall, routing và kiểm thử kết nối | NAT, load balancer, dynamic port hoặc hostname thay đổi |
| Process / application name (nếu có) | Gắn network flow với workload | Không phải mọi nguồn đều có quyền hoặc khả năng đọc process |
| Observation window | Xác định kết nối xuất hiện vào thời gian nào | Không thấy flow ≠ không tồn tại dependency |
| Frequency/volume (nếu có) | Ưu tiên đường kết nối quan trọng | Flow rất hiếm có thể vẫn là bước khóa sổ bắt buộc |
| Owner xác nhận | Phân biệt dependency thật với traffic nền/telemetry | Owner có thể không biết job cũ; phải kiểm tra thêm |

### 7.2 Agentless và agent-based dependency analysis

Với những môi trường **VMware vSphere được hỗ trợ**, Azure Migrate có thể cung cấp **agentless dependency analysis** qua appliance cùng điều kiện discovery bên trong guest, quyền và công cụ của môi trường nguồn tương ứng. Đây là một trong những lợi ích quan trọng khi làm việc với nhiều VM mà không muốn cài thêm agent riêng cho từng máy.

Với các nguồn hoặc tính năng khác, **cơ chế dependency analysis và việc cần agent, extension, credential hay công cụ bổ sung có thể khác**. Không tự lấy một quy trình agent-based cũ rồi áp dụng cho mọi Hyper-V/physical server; cần kiểm tra trạng thái hỗ trợ và prerequisites của bản Azure Migrate đang dùng. Một số luồng phụ thuộc cách thu thập trong guest, bao gồm mức quyền cần cho process/socket information.

Điều cần kiểm tra **trước khi bật**:

1. Nguồn có được hỗ trợ agentless cho dependency mapping hay không?
2. Appliance đã có dữ liệu **guest application/software/process** và kết nối liên quan chưa, hay mới thấy VM metadata?
3. Credential được cấp đúng phạm vi, có yêu cầu VMware Tools/guest support hoặc agent không?
4. Firewall và kết nối cần thiết từ appliance tới nguồn có được phê duyệt không?
5. Trong dữ liệu thu về có máy hoặc subnet nào chưa được quan sát do policy, máy tắt, lỗi đăng nhập hoặc thiếu quyền?

**Không thu thập ngoài phạm vi được cấp phép**. Mapping có thể hiển thị tên host, tiến trình, IP nội bộ và hệ thống bảo mật; bảo vệ quyền xem như thông tin topology nhạy cảm.

### 7.3 Phân tích đủ chu kỳ nghiệp vụ

Trước khi chốt wave, thu thập/đối chiếu tối thiểu những luồng trong:

- Giờ cao điểm và thấp điểm của ứng dụng.
- Batch cuối ngày, cuối tuần, cuối tháng hoặc đóng sổ.
- Backup, antivirus/EDR, monitoring và các dịch vụ quản trị.
- Sự kiện đổi token/chứng chỉ, login, LDAP/Kerberos, DNS.
- Failover/switchover thử nghiệm nếu hạ tầng nguồn có HA và việc thực hiện được phép.
- Luồng outbound đi SaaS, payment gateway, email, API đối tác mà inventory VM **không thể hiện**.

Một dependency chỉ xuất hiện hàng tháng **không thể bị loại** khỏi kế hoạch nếu nhóm chỉ thu thập 7 ngày. Khi thiếu chu kỳ, phải đánh dấu **unknown** hoặc lên lịch đo bổ sung; không biến việc “không quan sát được” thành “không tồn tại”.

## 8. Xây bản đồ ứng dụng từ dependency thực tế

Giả sử kết quả khám phá và đối chiếu owner của Orders cho thấy:

| Source | Destination / loại | Port/protocol ví dụ | Mục đích | Mức quan trọng |
| --- | --- | --- | --- | --- |
| `web-01/02` | `api-01/02` | HTTPS 443 | Gọi API đặt hàng | Critical |
| `api-01/02` | `sql-01` | TCP 1433 | Ghi và đọc đơn | Critical |
| `batch-01` | `sql-01` | TCP 1433 | Đối soát dữ liệu | Critical vào cuối ngày |
| `batch-01` | `files-01` | SMB TCP 445 | Gửi báo cáo | Important |
| Web/API/Batch | DNS/AD | DNS 53, Kerberos 88 (tùy cơ chế) | Phân giải tên, xác thực | Critical |
| API | Payment API bên ngoài | HTTPS 443 | Thanh toán | Critical, ngoài inventory |
| Tất cả máy | Monitoring/backup/management | Theo agent/tool | Giám sát và khôi phục | Operational |

Các cổng là **ví dụ mặc định thông dụng**, không phải cấu hình xác nhận của hệ thống; hãy đối chiếu listener/connection string thật. Active Directory thường liên quan nhiều protocol/port hơn hai cổng minh họa và có thể yêu cầu dynamic RPC, LDAP hoặc cơ chế khác. Không tạo NSG chỉ với danh sách cổng rút gọn này rồi kỳ vọng domain join hoạt động.

~~~mermaid
flowchart TD
    USER["User / DNS"] --> WEB["web-01 / web-02"]
    WEB --> API["api-01 / api-02"]
    API --> SQL["sql-01"]
    API --> PAYMENT["Payment partner / Internet"]
    API --> ID["DNS/AD: on-prem or hybrid"]
    BATCH["batch-01"] --> SQL
    BATCH --> FS["files-01"]
    WEB --> ID
    BATCH --> ID
~~~

### 8.1 Gắn dependency với yêu cầu migration

Ví dụ:

- **Web và API** thường phải có routing, chứng chỉ và network path hoạt động đồng thời. Có thể chuyển web trước nếu kết nối hybrid tới API nguồn ổn định và latency chấp nhận được.
- **API và SQL** là đường đi ghi giao dịch. Di chuyển chúng sang hai phía kết nối WAN khác nhau có thể tăng latency, chi phí và nguy cơ lỗi. Cần kiểm tra performance, firewall, TLS và RTO/RPO trước khi tách wave.
- **Batch và file share** có thể không cần chuyển cùng giờ cao điểm API, nhưng phải xác nhận luồng cuối ngày/đầu tháng và quyền SMB sau thay đổi.
- **Identity/DNS** thường là shared service không thể “chuyển một VM rồi xong”. Phải có thiết kế hybrid name resolution, domain join hoặc phương án identity thích hợp.
- **Payment API** có thể yêu cầu thay đổi allowlist outbound IP, certificate, DNS và endpoint test. Nó không hiện đầy đủ chỉ trong inventory on-prem.

**Dependency map giúp đặt câu hỏi; owner và kiểm thử mới xác nhận câu trả lời.** Một bản đồ tự động nên được xem là tài liệu kỹ thuật có độ tin cậy xác định, không là sự thật tuyệt đối.

### 8.2 Tạo bảng application group

Ví dụ sau là **sổ quyết định của nhóm**, không phải file cấu hình Azure Migrate có thể import trực tiếp:

~~~yaml
# Tài liệu minh họa, KHÔNG PHẢI schema ARM/Azure Migrate.
application: Orders
business_owner: "Orders Product"
technical_owner: "Platform + DB"
environment: production
servers:
  - web-01
  - web-02
  - api-01
  - api-02
  - sql-01
  - batch-01
  - files-01
external_dependencies:
  - "DNS/Active Directory - on-premises shared service"
  - "Payment partner HTTPS endpoint"
critical_paths:
  - "User -> Web -> API -> SQL"
  - "API -> Payment provider"
  - "Batch -> SQL -> File share"
open_questions:
  - "What is the allowed latency between API and SQL?"
  - "How will application identities resolve DNS after cutover?"
  - "Does payment partner require new outbound IP allowlist?"
acceptance:
  - "All critical ports tested in target network"
  - "Business transaction and batch reconciliation pass"
  - "RTO/RPO and rollback plan approved"
~~~

## 9. Chuyển assessment và dependency map thành migration waves

**Migration wave** là một đợt chuyển đổi được lên lịch, có phạm vi, người chịu trách nhiệm, điều kiện đầu vào và kế hoạch khôi phục. Không nên nhóm máy chỉ theo số lượng hoặc kích thước: hãy xem **độ gắn kết nghiệp vụ** và mức độ chia sẻ dữ liệu.

### 9.1 Ví dụ phân nhóm wave

| Wave | Workload | Mục đích | Điểm kiểm soát |
| --- | --- | --- | --- |
| 0 – Foundation | Azure landing zone, VPN/ExpressRoute, DNS, RBAC, monitoring, backup | Có đích và kết nối trước khi chuyển app | Security/network sign-off |
| 1 – Pilot | Một workload stateless ít phụ thuộc hoặc bản sao thử nghiệm | Kiểm tra công cụ, throughput replication, monitoring | Không gây ảnh hưởng production, kết quả đo được |
| 2 – Orders test | Bản sao Web/API/SQL hoặc môi trường thử nghiệm | Test latency, dependency, database restore và workflow | End-to-end tests, cost/size phù hợp |
| 3 – Orders production | Application group Orders theo runbook đã duyệt | Cutover nghiệp vụ thật | Cửa sổ thay đổi, dữ liệu nhất quán, rollback |
| 4 – Cleanup / optimize | Tắt nguồn sau xác nhận, rightsizing, governance | Loại chi phí trùng và vận hành ổn định | Owner xác nhận, retention/backup và decommission |

Nếu API và database không thể chịu latency qua WAN, có thể phải **chuyển trong cùng một change window** hoặc dựng cơ chế đồng bộ/replication để cutover nhất quán. Nếu bắt buộc để SQL tại chỗ, cần bằng chứng hiệu năng và network cho kiến trúc hybrid trước khi phát hành web/API lên Azure.

### 9.2 Đặt tiêu chí GO/NO-GO

Một migration wave chỉ nên bắt đầu khi:

1. Inventory/discovery đã bao phủ tất cả máy trong scope và các dependency quan trọng đã được owner xác nhận.
2. Assessment đang dùng **đúng target region, sizing và pricing assumptions**, đã xử lý máy not-ready/unknown.
3. Azure VNet, NSG/firewall, DNS, identity, IP, route, private connectivity và quota đã kiểm tra.
4. Backup, replication/test migration và kế hoạch dữ liệu phù hợp; đã đo hoặc diễn tập RTO/RPO theo kịch bản.
5. Trước cutover có baseline SLI/latency/throughput, error budget và người trực.
6. Có runbook với mốc **last safe rollback**, nguồn dữ liệu nhất quán và biện pháp tránh ghi vào cả hai phía.
7. Kế hoạch truyền thông, người phê duyệt, cách đo PASS/FAIL và điều kiện hoãn được thống nhất.

Trạng thái *Ready* trong assessment chỉ hỗ trợ **một phần** điều kiện trên, không thay thế sự chuẩn bị production.

## 10. Quy trình thực hành end-to-end, không đụng production

Bài tập thực hành phù hợp nhất là dùng một **lab VMware/Hyper-V hoặc server test** có quyền truy cập hợp lệ. Bạn không cần thực hiện cutover thật để học discovery, assessment và mapping.

### Bước 1: Phạm vi và bảo mật

- Chọn 3–6 VM thử nghiệm, có chủ sở hữu và tài liệu địa chỉ, OS, cấu hình.
- Chọn subscription Azure được phép dùng, project và nơi lưu kết quả theo yêu cầu tuân thủ.
- Đảm bảo quyền truy cập tới nguồn và outbound connection của appliance theo hướng dẫn đúng loại nguồn.
- Có người chịu trách nhiệm việc cấp/thu hồi credential và cleanup sau thử nghiệm.

### Bước 2: Discovery

- Tạo project, chọn nguồn, deploy/register appliance hoặc cơ chế được hỗ trợ.
- Đăng ký nguồn và credential, chạy khám phá; **không cài agent không cần thiết**.
- Đối chiếu inventory phát hiện với danh sách lab: hostname/ID, OS, vCPU, RAM, disks, IP.
- Ghi trường nào thiếu và nguyên nhân; kiểm tra lần cập nhật gần nhất.

### Bước 3: Performance-based assessment

- Thu thập đủ lịch sử bao gồm tải mô phỏng, chọn khoảng dữ liệu và sizing mode.
- Tạo một assessment **as-on-premises** để làm baseline và một assessment **performance-based** cho cùng tập máy.
- So sánh recommended size, disk, readiness và estimated cost; ghi rõ cấu hình khác biệt.
- Đối chiếu nguồn dữ liệu, metric thiếu và mức confidence; không chọn SKU chỉ vì rẻ.

### Bước 4: Dependency mapping

- Bật khả năng phân tích phụ thuộc **được hỗ trợ** cho nguồn lab, theo prerequisites/credential.
- Tạo lưu lượng kiểm thử từ web → API → database, chạy một job theo lịch và gọi một endpoint ngoài.
- Quan sát các kết nối được phát hiện (source, target, port/process nếu có), ghi những luồng không hiển thị.
- Xác minh bằng app config, logs, network traces được cấp phép và phỏng vấn owner.

### Bước 5: Quyết định wave

- Gom các VM cùng critical path, mô tả phần vẫn ở on-premises và đường kết nối hybrid.
- Viết GO/NO-GO, smoke tests, thử nghiệm dữ liệu, RTO/RPO và rollback.
- Báo cáo những rủi ro chưa đóng, không khẳng định hệ thống sẵn sàng chỉ từ dashboard.

**Sản phẩm đầu ra**: danh sách máy đã đối chiếu, hai assessment có ghi giả định, dependency map có mức độ tin cậy, bảng application groups và kế hoạch migration wave. Không phải chỉ một ảnh chụp màn hình “Ready”.

## 11. Troubleshooting discovery, assessment và mapping

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Appliance không register | Sai key/project, outbound network, proxy/TLS, tenant/quyền | Kiểm tra đúng project và connectivity, đồng bộ thời gian, không công khai key |
| Không thấy một số VM | Nguồn cấu hình sai, credential thiếu quyền, VM đã tắt, filter hoặc giới hạn khám phá | Đối chiếu vCenter/host inventory và scope; xem appliance health |
| OS/guest software thiếu | Không có quyền guest, agentless guest discovery chưa bật hoặc source không hỗ trợ | Đối chiếu prerequisites; dùng nguồn bổ sung khi được phép |
| Performance-based assessment confidence thấp | Chưa đủ lịch sử, không có dữ liệu tại peak, sampling gap | Thu thập thêm dữ liệu, kiểm tra chất lượng metric |
| Kết quả VM size quá nhỏ | Chọn percentile thấp, dữ liệu không có batch, thiếu RAM/disk peak | Review sizing settings, comfort factor, workload owners, SLO |
| Azure readiness Not ready/Unknown | OS/boot/disk/architecture không tương thích hoặc metadata thiếu | Xem nguyên nhân và remediation; cân nhắc modernize/alternative target |
| Chi phí assessment khác billing dự kiến | Thiếu dịch vụ dùng chung, license, giá/discount, network, DR, monitoring | Phân tách estimated scope và làm business case bổ sung |
| Dependency map chỉ có vài đường | Thiếu guest telemetry, thời gian quan sát quá ngắn, app chưa tạo traffic | Kéo dài/điều chỉnh thu thập, kích hoạt test được phép |
| Map xuất hiện nhiều kết nối lạ | Monitoring, patching, backup, quản trị, NAT/LB hoặc process khác | Phân loại hệ thống và xác minh port/process/owner |
| Sau migration không kết nối DB | NSG/firewall/route/DNS, TLS, identity, connection string, latency hoặc SQL endpoint | Test connectivity theo luồng source→target, không chỉ ping VM |

### 11.1 Các dấu hiệu dữ liệu chưa đủ để ra quyết định

- Chỉ có danh sách VM, chưa có chủ ứng dụng hoặc critical path.
- Assessment không ghi target region, sizing criteria và chu kỳ dữ liệu.
- Dependency analysis chỉ chạy vài phút dù có batch cuối tháng.
- Không nhìn thấy traffic SaaS, DNS, identity, backup hoặc dịch vụ dùng chung.
- Một số VM chưa được phân loại nhưng vẫn bị đưa vào wave sản xuất.
- Không có baseline latency, error rate, database consistency và phương án khôi phục.

Nếu gặp các dấu hiệu trên, trạng thái chính xác là **cần bổ sung bằng chứng**, không phải “đã hoàn thành assessment”.

## 12. Kiểm soát chi phí, vận hành và an ninh sau migration

Azure Migrate phục vụ chủ yếu cho **quyết định và quá trình di chuyển**; để vận hành lâu dài, cần kế hoạch hậu migration:

- **Cost Management và budgets:** so sánh actual billing với cost estimate, phân bổ tag, kiểm tra quyền mua reservation/savings plan sau khi ổn định workload.
- **Azure Monitor và Application Insights:** theo dõi availability, CPU/memory, disk IO, network, dependency failures, SLI/SLO và cảnh báo.
- **Azure Policy, RBAC, Defender for Cloud:** kiểm soát cấu hình, quyền truy cập và phát hiện rủi ro bảo mật trong môi trường Azure mới.
- **Backup/DR:** xác nhận restore test, retention, RTO/RPO và trách nhiệm dữ liệu sau cutover; bản sao nguồn cũ không thay cho chiến lược backup lâu dài.
- **Rightsizing:** sau vài chu kỳ tải thật, đánh giá lại VM sizing, autoscale và storage. Các giả định từ performance nguồn có thể khác trên Azure.
- **Decommission an toàn:** chỉ tắt/xóa máy nguồn khi chủ hệ thống ký xác nhận, dữ liệu đối soát đủ, yêu cầu lưu trữ và rollback đã rõ.

Một chương trình migration thành công không chỉ là “số VM đã chuyển”; nó phải đáp ứng chức năng, hiệu năng, bảo mật, độ tin cậy và chi phí theo tiêu chí ban đầu.

## 13. Checklist đầu ra cho mỗi ứng dụng

| Hạng mục | Câu hỏi bắt buộc |
| --- | --- |
| Scope | Mọi server/app/data/source site trong nhóm đã được ghi nhận? |
| Owner | Có người chịu trách nhiệm kỹ thuật và nghiệp vụ ký duyệt? |
| Discovery | Inventory coverage, OS, vCPU/RAM/disk, dữ liệu hiện tại và missing fields? |
| Performance | Đủ peak/batch, metric aggregation, dữ liệu thiếu và confidence? |
| Assessment | Target region, sizing criteria, readiness, SKU/disk, chi phí và giả định đã lưu? |
| Dependencies | Source→target, port/process, external services, identity/DNS/backup đã xác nhận? |
| Application groups | Có máy nào được chia wave sai so với critical path hoặc dữ liệu? |
| Landing zone | Subscription, RBAC, VNet/NSG/DNS, policy, backup, monitoring, cost controls sẵn sàng? |
| Migration plan | Pilot/test migration, replication, cutover, rollback, RTO/RPO và GO/NO-GO? |
| Evidence | Có biên bản owner review, số đo test, warnings và open issues? |
| Post-migration | SLI/latency, bill, data integrity, owner sign-off, decommission có kiểm soát? |

## 14. Bài tập vận dụng và tự kiểm tra

### Bài tập 1: Đánh giá độ bao phủ và độ tin cậy

Một nhóm có **200 VM** trong phạm vi. Azure Migrate phát hiện **190 VM**. Trong số đó, **171 VM** đã có đủ performance history để dùng cho assessment dựa trên hiệu năng. Hỏi:

1. Discovery coverage là bao nhiêu?
2. Performance coverage tính theo toàn bộ scope là bao nhiêu?
3. Nhóm có thể tuyên bố mọi VM production đều đã đủ dữ liệu để sizing chưa?

**Lời giải:**

\[
\mathrm{DiscoveryCoverage}=\frac{190}{200}\times100\%=95\%.
\]

\[
\mathrm{PerformanceCoverage}=\frac{171}{200}\times100\%=85{,}5\%.
\]

Nhóm **chưa thể** khẳng định toàn bộ VM đủ dữ liệu: còn **10 VM chưa được khám phá** và **19 VM đã khám phá nhưng thiếu performance history**. Cần xác định chủ sở hữu, nguyên nhân thiếu, chu kỳ tải và criticality; không lấy trung bình của 171 máy để dự đoán toàn bộ 200 máy một cách máy móc.

### Bài tập 2: Kết hợp assessment với dependency map

Assessment cho `api-01` là *Ready*, giá compute ước tính thấp. Dependency map thấy `api-01` gọi `sql-01` ở on-premises qua kết nối TCP thường xuyên; latency giữa vùng Azure dự định và site hiện tại là **25 ms RTT** (giả định đo trong lab), trong khi một request API thực hiện 10 truy vấn SQL nối tiếp.

**Câu hỏi:** Có nên migrate API trước database chỉ vì assessment Ready? Rủi ro chính?

**Gợi ý đáp án:** Chưa đủ căn cứ. Nếu mười round trip SQL thực sự phải đi tuần tự qua WAN, riêng phần độ trễ mạng bổ sung có thể ở mức **10 × 25 ms = 250 ms** cho một request (ước lượng rất thô, chưa kể pooling, xử lý query, TLS và cách giao tiếp thật). Cần đo end-to-end latency, phân tích calls, kết nối hybrid, database migration/co-location và SLO. Assessment tính phù hợp VM **không chứng minh** latency của kiến trúc ứng dụng đạt yêu cầu.

### Bài tập 3: Lập wave cho Orders

Các máy `web-01`, `web-02`, `api-01`, `api-02`, `sql-01`, `batch-01` và `files-01` có quan hệ như bảng dependency ở phần 8. Hãy:

1. Chỉ ra các đường đi nghiệp vụ quan trọng bắt buộc có network path trong giai đoạn hybrid.
2. Chọn một pilot ít rủi ro hơn việc cắt thẳng production.
3. Viết ba điều kiện GO/NO-GO và một biện pháp rollback cho migration wave chính.

**Gợi ý đáp án:** Nhóm Web/API/SQL cần xử lý như một critical path; payment outbound và DNS/identity cần được kiểm chứng. Pilot nên dùng bản sao thử nghiệm hoặc stateless workload có owner và dữ liệu test. GO đòi hỏi kết nối/VNet/NSG/DNS đã test, replication/backup và dữ liệu nhất quán, cùng smoke/SLI sau test migration đạt. Nếu lỗi, phải có kế hoạch dừng traffic/ghi, phục hồi định tuyến về nguồn và đối soát dữ liệu trước khi nhận lại giao dịch.

### Câu hỏi tự kiểm tra

1. Discovery khác assessment và dependency mapping như thế nào?
2. Vì sao Azure Migrate appliance ở môi trường VMware có thể lấy inventory mà chưa có thông tin process và TCP dependencies?
3. Khi nào nên dùng as-on-premises assessment, khi nào có thể tin performance-based assessment?
4. Vì sao một Azure VM được đánh giá Ready vẫn chưa đủ để tiến hành cutover?
5. Tại sao “không thấy traffic giữa hai VM” không chứng minh chúng độc lập?
6. Những dependency bên ngoài inventory VM nào cần tìm cho ứng dụng dùng DNS/AD, payment API và job cuối tháng?
7. Vì sao estimated compute/storage cost không phải toàn bộ TCO?
8. Khi migration API lên Azure nhưng giữ SQL on-premises, bạn cần kiểm tra gì về network, latency và security?
9. Cần bằng chứng gì trước khi tắt VM nguồn sau cutover?
10. Khi assessment confidence thấp hoặc map thiếu một nhóm server, bạn nên quyết định tiếp tục hay bổ sung dữ liệu?

**Điểm cần nhớ:** Azure Migrate giúp chuyển từ phỏng đoán sang **quyết định dựa trên inventory, hiệu năng và quan hệ phụ thuộc**. Hãy dùng discovery để biết *có gì*, assessment để biết *có thể đi đâu với giả định nào*, và dependency mapping để biết *phải đi cùng ai*. Cuối cùng, cần kiểm chứng landing zone, đường kết nối, dữ liệu và hành trình nghiệp vụ trước khi thực hiện migration wave và cutover.
