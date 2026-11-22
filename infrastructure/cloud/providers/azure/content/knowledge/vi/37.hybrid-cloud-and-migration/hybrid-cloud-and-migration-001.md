# Khảo sát hệ thống hiện có và chọn chiến lược migration

Di chuyển một hệ thống lên cloud không đơn giản là sao chép máy chủ lên một máy ảo mới. Một ứng dụng có thể phụ thuộc vào Active Directory tại chỗ, database có cấu trúc đặc thù, máy chủ cấp phép phần mềm, tác vụ batch, tệp trên NAS và địa chỉ IP đã được tích hợp vào nhiều hệ thống. Chỉ cần bỏ sót một phụ thuộc, ứng dụng có thể khởi động trên Azure nhưng không hoạt động đúng trong thực tế.

Trong chương **Hybrid cloud và di chuyển lên Azure** của lộ trình **CLOUD_PROVIDERS_AZURE**, chúng ta học cách khảo sát hệ thống hiện hữu (*discovery/assessment*), lượng hóa mức sẵn sàng và lựa chọn chiến lược di chuyển phù hợp từng workload. Chủ đề đặt trong bối cảnh hệ sinh thái Microsoft Azure: từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ, dữ liệu, giám sát, bảo mật, khôi phục sau thảm họa và quản lý chi phí.

Đích đến của bài học không phải “chuyển mọi thứ lên Azure”, mà là **có đủ bằng chứng để quyết định nên chuyển cái gì, chuyển bằng cách nào, theo thứ tự nào, với điều kiện nghiệm thu và phương án quay lui ra sao**.

> **Phạm vi:** Các tên workload, số liệu và cấu hình trong bài đều là ví dụ giả định. Những khả năng, giới hạn hỗ trợ, giá và công cụ Azure có thể thay đổi theo loại nguồn, phiên bản hệ điều hành, database, licensing, region và thời điểm. Khi thực hiện dự án thật, phải xác minh danh sách hỗ trợ và điều khoản áp dụng cho từng workload.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Lập danh mục máy chủ, ứng dụng, cơ sở dữ liệu, kết nối, tài sản dữ liệu, danh tính và phụ thuộc của hệ thống hiện tại.
2. Thu thập baseline về hiệu năng, năng lực, bảo mật, độ tin cậy, chi phí và yêu cầu nghiệp vụ trước khi di chuyển.
3. Dùng Azure Migrate và các phương pháp khảo sát bổ sung đúng phạm vi, không xem kết quả tự động là bằng chứng duy nhất.
4. Phân biệt các lựa chọn **retain, retire, rehost, relocate, replatform, refactor/rearchitect và repurchase**.
5. Chọn đích Azure và chiến lược theo kỹ thuật, rủi ro, chi phí, licensing, ràng buộc dữ liệu và mức thay đổi chấp nhận được.
6. Thiết kế thứ tự các *migration waves* có xét đến graph phụ thuộc và chuẩn bị landing zone.
7. Xây điều kiện kiểm thử, cutover, rollback, thời gian gián đoạn, RTO/RPO và tiêu chí hoàn thành migration.
8. Viết một bản **migration assessment** có thể được kiến trúc sư, chủ ứng dụng, đội bảo mật và vận hành cùng thẩm định.

## 2. Migration là một quyết định về hệ thống, không chỉ về vị trí máy chủ

**Migration** là quá trình đưa ứng dụng, dữ liệu hoặc năng lực hệ thống từ môi trường hiện hữu (on-premises, data center thuê ngoài hoặc một cloud khác) đến môi trường đích, đồng thời bảo đảm các yêu cầu nghiệp vụ cần thiết. **Modernization** là cải tiến cấu trúc, nền tảng hoặc cách phát triển/vận hành; nó có thể diễn ra cùng lúc, trước hoặc sau migration. **Disaster recovery** tập trung khôi phục khi có sự cố và không đồng nghĩa với chuyển nơi vận hành chính.

Ba mục tiêu khác nhau có thể dẫn đến ba quyết định khác nhau:

| Động lực | Câu hỏi thực sự | Hệ quả đến chiến lược |
| --- | --- | --- |
| Hết hạn hợp đồng data center trong 6 tháng | Có thể chuyển dịch vụ ổn định trong hạn không? | Ưu tiên rehost/replatform ít thay đổi, hiện đại hóa sâu ở giai đoạn sau |
| Ứng dụng monolith khó mở rộng, deploy mất nhiều giờ | Cần thay kiến trúc đến mức nào? | Cân nhắc refactor/rearchitect, chia từng khả năng nghiệp vụ |
| Phần mềm kế toán cũ không còn hỗ trợ | Có nên chuyển nguyên phần mềm cũ không? | So sánh repurchase SaaS, thay thế hoặc retire |
| Dữ liệu nhạy cảm bị giới hạn địa điểm xử lý | Dữ liệu nào được phép đưa đi? | Retain/hybrid, mã hóa, kiểm soát region và pháp lý |
| Muốn giảm chi phí vận hành 3 năm | TCO và rủi ro thực tế thay đổi ra sao? | Cần số liệu baseline, pricing, license, vận hành và chi phí di chuyển |

Một dự án có thể có **nhiều chiến lược trong cùng một ứng dụng**: rehost một máy xử lý batch, replatform web frontend, refactor kết nối đến cache, retain một thiết bị công nghiệp tại chỗ và retire dịch vụ báo cáo không còn ai sử dụng.

## 3. Quy trình assessment tổng quát

~~~mermaid
flowchart TD
    A["Xác định mục tiêu và phạm vi"] --> B["Kiểm kê tài sản và owner"]
    B --> C["Khám phá dependency và luồng dữ liệu"]
    C --> D["Baseline: hiệu năng, SLO, RTO/RPO, bảo mật, chi phí"]
    D --> E["Đánh giá compatibility, readiness và rủi ro"]
    E --> F["So sánh chiến lược và Azure target"]
    F --> G["Chọn migration wave, landing zone và thiết kế cutover"]
    G --> H["Pilot và kiểm chứng"]
    H --> I{"Đủ tiêu chí?"}
    I -->|"Không"| E
    I -->|"Có"| J["Phê duyệt kế hoạch migration"]
~~~

Ở từng bước cần lưu **bằng chứng**, không chỉ ý kiến. Một file inventory được lập từ CMDB hai năm trước là điểm bắt đầu, nhưng cần đối chiếu telemetry hiện tại, DNS, lịch tác vụ, kết nối, người sử dụng và dữ liệu thực.

### 3.1. Các vai trò tối thiểu

| Vai trò | Trách nhiệm chính |
| --- | --- |
| **Business owner** | Mục tiêu nghiệp vụ, lịch downtime, chức năng bắt buộc và mức chấp nhận rủi ro |
| **Application owner / developer** | Kiến trúc logic, runtime, thư viện, integrations, quy trình deploy, dữ liệu nghiệp vụ |
| **Infrastructure/Network** | Máy chủ, storage, DNS, IP, firewall, VPN/ExpressRoute, hiệu năng mạng |
| **Database/Data owner** | Database inventory, integrity, schema, backup, replication, cutover |
| **Security/Compliance** | Phân loại dữ liệu, yêu cầu cư trú, danh tính, encryption, audit và quyền |
| **Cloud platform team** | Azure landing zone, subscription, policy, RBAC, capacity/quota, monitoring |
| **Finance/FinOps** | TCO, licensing, cam kết, forecast và ngân sách |
| **Migration lead/SRE** | Wave, runbook, kiểm thử, go/no-go, rollback, hypercare |

Người sở hữu ứng dụng **phải được xác định** trước khi quyết định tắt hệ thống cũ. Nếu không có owner, hãy ghi trạng thái *unowned/pending validation* và điều tra; đừng xem không có owner là bằng chứng tài nguyên có thể xóa.

## 4. Lập danh mục hệ thống hiện hữu

### 4.1. Không chỉ liệt kê VM

Mục tiêu là lập danh sách **workload và mọi thành phần ảnh hưởng đến tính đúng đắn của nó**, gồm:

- Máy chủ vật lý, VM, hypervisor, OS, CPU/RAM, disk, filesystem, middleware và thời hạn support.
- Ứng dụng, phiên bản, framework, runtime, process, container, lịch batch và các công việc thủ công.
- Database engine/version/edition, dung lượng, transaction log, job, replication, linked server, extension và ứng dụng truy cập.
- File share, object storage, snapshot, backup repository, dữ liệu lưu trữ lâu dài và hệ thống tìm kiếm.
- DNS, IP tĩnh, load balancer, firewall, proxy, routing, certificate, LDAP/Kerberos/AD, NTP.
- Công cụ vận hành: CI/CD, scheduler, monitoring, logging, backup/restore, patching, quản lý license.
- Tích hợp với SaaS, đối tác, thiết bị tại nhà máy, hệ thống thanh toán, SMTP, API và endpoint chỉ truy cập qua IP allowlist.
- Quy tắc truy cập dữ liệu, service account, secret, khóa mã hóa, HSM và bên chịu trách nhiệm.
- Ràng buộc bảo mật, pháp lý, quyền sở hữu dữ liệu, lưu giữ, tiêu hủy và audit.

**Đơn vị phân tích quan trọng nhất là workload nghiệp vụ**, không phải tên host. Một ứng dụng có thể dùng nhiều máy và nhiều database; một máy cũng có thể phục vụ nhiều ứng dụng. Vì vậy cần bảng quan hệ nhiều-nhiều.

### 4.2. Mẫu inventory

| Trường | Giá trị ví dụ | Lý do cần |
| --- | --- | --- |
| Workload ID | APP-ORD-01 | Khóa nhận diện ổn định |
| Tên nghiệp vụ | Orders Portal | Trao đổi với business owner |
| Owner | Commerce application team | Người duyệt chức năng và cutover |
| Environment | Production | Tách phạm vi production và test |
| Thành phần | web-01, api-01/02, sql-01, file-01 | Xác định migration unit |
| Runtime/OS | .NET 6, Windows Server, SQL Server (ví dụ) | Kiểm tra compatibility và hỗ trợ |
| Trạng thái hỗ trợ | Phải xác minh vòng đời thực tế | Không chuyển EOL sang đích rồi bỏ qua bảo mật |
| CPU/RAM/disk | 8 vCPU, 32 GiB, 1,2 TiB | Sizing ban đầu |
| Data classification | Confidential | Thiết kế private connectivity, quyền, bảo vệ dữ liệu |
| RPO/RTO | 15 phút / 2 giờ | Chọn giải pháp backup, replication, migration |
| Traffic và latency | 120 RPS peak, p95 350 ms | Benchmark và capacity sizing |
| Downtime được phép | 30 phút vào Chủ nhật | Chọn online/offline cutover |
| Dependency | AD, payment gateway, NAS | Quyết định wave và phương án hybrid |
| Tình trạng license | Contract review pending | Kiểm tra BYOL, Software Assurance/Hybrid Benefit nếu đủ điều kiện |
| Đề xuất tạm thời | Replatform API; DB cần assessment | Chưa phải quyết định đã duyệt |

### 4.3. Dữ liệu CSV minh họa

~~~csv
workload_id,component,owner,environment,source_platform,data_class,criticality,status
APP-ORD-01,orders-web,commerce,prod,VMware,internal,high,discovered
APP-ORD-01,orders-api,commerce,prod,VMware,confidential,high,discovered
APP-ORD-01,orders-db,commerce,prod,SQL-Server,confidential,critical,assessment-needed
APP-ORD-01,order-files,commerce,prod,NAS,confidential,high,assessment-needed
APP-REP-02,legacy-reporting,finance,prod,physical-server,internal,low,ownership-review
~~~

CSV trên là **dữ liệu học tập**, không phải output thực của Azure Migrate. Trong dự án thật, tránh lưu password, connection string hoặc dữ liệu cá nhân vào CSV; đặt mã định danh và tham chiếu tới hệ thống bảo mật phù hợp.

### 4.4. Phân biệt độ tin cậy của dữ liệu

| Mức | Nguồn bằng chứng | Hành động |
| --- | --- | --- |
| **Verified** | Telemetry mới, owner xác nhận, cấu hình được kiểm tra | Có thể dùng làm đầu vào assessment |
| **Observed** | Agent/log/flow cho thấy tài nguyên hoặc kết nối tồn tại | Cần owner xác minh ý nghĩa |
| **Declared** | CMDB, tài liệu cũ hoặc phỏng vấn | Kiểm tra chéo với thực tế |
| **Unknown** | Chưa có owner, số liệu hoặc phụ thuộc quan trọng | Gắn blocker; không chốt chiến lược |

Không bỏ qua hệ thống có lưu lượng thấp. Một batch cuối tháng hoặc tác vụ chạy mỗi quý rất dễ vắng mặt trong cửa sổ quan sát một tuần.

## 5. Khám phá dependency và dựng bản đồ luồng dữ liệu

**Dependency mapping** là công việc xác định ứng dụng cần dịch vụ nào để hoạt động, theo giao thức, địa chỉ, chiều truy cập, danh tính và yêu cầu độ trễ. Một graph giúp quyết định thành phần nào phải được chuyển cùng nhau và thành phần nào có thể ở lại tạm thời.

~~~mermaid
flowchart LR
    U["Người dùng nội bộ"] --> DNS["DNS / proxy tại chỗ"]
    DNS --> W["Orders web"]
    W --> API["Orders API"]
    API --> DB["SQL Server"]
    API --> FILE["NAS / file share"]
    API --> PAY["Payment API đối tác"]
    API --> ID["Active Directory / DNS nội bộ"]
    DB --> BACKUP["Backup repository"]
    API -. "Log / metric" .-> MON["Monitoring tại chỗ"]
~~~

Sơ đồ chỉ có ý nghĩa khi từng cạnh được chú thích:

| From → To | Protocol/port | Chiều | Phụ thuộc chức năng | Latency/throughput | Owner | Mức xác nhận |
| --- | --- | --- | --- | --- | --- | --- |
| API → SQL | TCP/1433 (ví dụ) | Outbound từ API | Đọc/ghi giao dịch | p95, IOPS, TPS | DBA | Verified |
| API → NAS | SMB/445 (ví dụ) | Outbound từ API | Đính kèm chứng từ | MB/s, số file | Storage | Observed |
| API → AD | LDAP/Kerberos/DNS theo thực tế | Hai chiều theo dịch vụ | Xác thực tài khoản | Timeout, domain reachability | Identity | Declared |
| API → Payment | HTTPS/443 | Outbound từ API | Tạo thanh toán | Rate limit, retry, idempotency | Integration | Verified |
| SQL → backup | Theo sản phẩm | Outbound từ SQL | Khôi phục sau lỗi | RPO/retention | DBA | Verified |

**Không đoán port theo tên dịch vụ.** Những con số trên chỉ minh họa; hệ thống thật có thể dùng cổng tùy chỉnh, TLS tunnel, proxy hoặc private endpoint.

### 5.1. Phương pháp thu thập dependency

1. **Phỏng vấn owner** để có sơ đồ thiết kế dự kiến.
2. **Network flow logs/firewall/proxy/DNS/host telemetry** để thấy kết nối thực tế trong các khung giờ khác nhau.
3. **Application tracing** hoặc log có correlation ID để thấy lời gọi ở mức nghiệp vụ.
4. **Database/job inventory** để nhận diện scheduled task, linked server, ETL và replication.
5. **Kiểm tra runtime configuration**: connection endpoints, queue names, certificate, service accounts; không sao chép secret ra báo cáo.
6. **Đối chiếu với owner**, vì một kết nối được quan sát không luôn là dependency cần thiết và một dependency hiếm khi dùng có thể không xuất hiện trong dữ liệu.

**Cửa sổ đo phải phủ chu kỳ nghiệp vụ**: giờ cao điểm, cuối tuần, cuối tháng, batch định kỳ, sự kiện bảo trì. Nếu chưa thể đo đủ một chu kỳ, ghi rõ thiếu sót và dùng bài kiểm thử hoặc xác nhận bổ sung.

### 5.2. Tính độ nhạy độ trễ khi chuyển từng phần

Một ứng dụng chuyển lên Azure nhưng SQL ở lại data center có thể tạo nhiều vòng round-trip qua VPN/ExpressRoute. Ví dụ giả định:

- Một API thực hiện **20 truy vấn tuần tự** tới SQL.
- Round-trip latency tăng thêm **12 ms** so với trước.
- Overhead tăng có thể tới khoảng **20 × 12 = 240 ms** cho request, nếu không được che bằng song song hóa hoặc tối ưu giao thức.

Đây là ước lượng khái niệm, không phải dự báo chính xác p95. Cần benchmark theo dependency thật. Nếu giao dịch có nhiều round-trip, việc di chuyển API và database cùng một wave có thể an toàn về latency hơn việc giữ kết nối hybrid kéo dài.

## 6. Thu thập baseline trước khi chuyển

Không có baseline, rất khó kết luận sau migration hệ thống tốt hơn hay tệ hơn. Số liệu ít nhất nên bao gồm **hiệu năng, năng lực, độ tin cậy, trạng thái dữ liệu và chi phí**.

### 6.1. Hiệu năng và capacity

| Nhóm | Chỉ số cần có | Cách dùng |
| --- | --- | --- |
| **Workload traffic** | RPS, transactions/s, sessions, batch jobs/ngày | Dự báo capacity |
| **Latency** | p50, p95, p99 của API và dependency | Đặt SLO sau migration |
| **Errors** | Timeout, 5xx, business errors, retry count | So sánh chất lượng |
| **Compute** | CPU bình quân/peak, RAM working set, GC, threads | Sizing compute |
| **Disk/storage** | Dung lượng, growth, IOPS, throughput, latency | Chọn managed disk/Storage phù hợp |
| **Database** | TPS/QPS, CPU, memory, connections, log growth, query latency | Chọn service/tier và phương pháp migration |
| **Network** | Inbound/outbound bandwidth, connection count, round-trip latency | Chọn hybrid connectivity và egress |
| **Async workload** | Queue depth, oldest-message age, completion rate | Sizing worker và đánh giá backlog |
| **Availability** | SLI/SLO, downtime, sự cố/restore trước đây | So sánh mục tiêu và thiết kế DR |

Thu số liệu cả **mức bình thường và peak**. Việc lấy CPU trung bình 20% từ một thời điểm tĩnh để chọn VM đích có thể gây thiếu capacity khi batch chạy cuối tháng. Cần nhìn mùa vụ, peak ngắn và trạng thái cache.

### 6.2. Chọn tiêu chí đạt sau migration

Ví dụ giả định cho Orders API:

~~~yaml
workload: APP-ORD-01
measurementScope: production-business-transactions
baseline:
  peakRps: 120
  p95LatencyMs: 350
  businessSuccessPercent: 99.95
  databaseSizeTiB: 1.2
  dataGrowthGiBPerMonth: 50
acceptance:
  peakRpsAtLeast: 120
  p95LatencyMsAtMost: 400
  businessSuccessPercentAtLeast: 99.95
  criticalFeaturesPass: true
  maxCutoverDowntimeMinutes: 30
  dataLossToleranceMinutes: 0
~~~

Đây là **mẫu hợp đồng nghiệm thu do bài học định nghĩa**, không phải định dạng cấu hình Azure Migrate. Trong trường hợp ghi nhận dữ liệu có tính pháp lý hoặc thanh toán, yêu cầu “không mất giao dịch đã xác nhận” cần được thiết kế ở mức giao dịch và đối soát; không thể bảo đảm chỉ bằng việc chọn một công cụ sao chép.

### 6.3. RTO, RPO và downtime trong migration

- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ sau gián đoạn nghiêm trọng.
- **RPO (Recovery Point Objective):** giới hạn mất dữ liệu có thể chấp nhận được về thời gian.
- **Migration downtime window:** thời gian gián đoạn được phép trong hoạt động chuyển đích có kế hoạch.
- **Cutover duration:** thời gian thực tế từ khóa thay đổi/cập nhật tuyến đến khi xác nhận hệ thống mới.

**RTO/RPO không bằng downtime window.** Một hệ thống có RTO 2 giờ khi thảm họa xảy ra vẫn có thể chỉ được phép gián đoạn 10 phút trong một buổi migration có kế hoạch. Đặc biệt, backup thành công **không chứng minh** restore đạt RTO/RPO; phải thực hiện thử khôi phục.

## 7. Khảo sát dữ liệu: phần thường quyết định chiến lược

### 7.1. Database inventory

Ngoài engine, phiên bản và dung lượng, phải kiểm tra:

- Schema, stored procedures, triggers, functions, cross-database queries, linked servers.
- Extension/plugin, CLR, full-text search, collation, job scheduler và các tính năng đặc thù engine.
- Số transaction/giây, write latency, log rate, index, partition và thời gian backup/restore.
- Replication/HA, các node phụ, transaction consistency và cửa sổ bảo trì.
- User/login, quyền, service account, key/certificate, cách quản lý secret.
- Dữ liệu lớn dạng BLOB/file, pipeline ETL và hệ thống downstream đọc dữ liệu.
- Cơ chế checksum, số lượng bản ghi, đối soát tổng tiền hoặc invariants nghiệp vụ.

Tính năng database được hỗ trợ ở VM **không đồng nghĩa được hỗ trợ y nguyên** ở Azure SQL Database hoặc Azure SQL Managed Instance. Đánh giá compatibility phải dựa trên các tính năng cụ thể, phiên bản engine và dịch vụ đích.

### 7.2. Data classification và cư trú dữ liệu

Hãy phân loại dữ liệu công khai, nội bộ, bí mật, dữ liệu cá nhân và dữ liệu chịu yêu cầu pháp lý/tuân thủ. Xác định:

1. Dữ liệu nào được phép đưa sang cloud, region nào được dùng và vùng backup/replication có được phép không.
2. Ai được phép đọc/ghi, vai trò quản trị dữ liệu và khóa mã hóa do bên nào quản lý.
3. Thời hạn lưu, xóa, khôi phục và yêu cầu audit.
4. Kết nối đối tác hoặc hệ thống địa phương có được phép truy cập qua Internet không.
5. Những luồng dữ liệu nào phải đi qua private network hoặc cần mã hóa bổ sung.

**Chọn Azure region không tự bảo đảm tuân thủ mọi yêu cầu cư trú dữ liệu.** Phải xem dịch vụ cụ thể, nơi lưu backup/log/metadata, cơ chế replication, chính sách pháp lý và điều khoản của tổ chức.

### 7.3. Thời gian sao chép dữ liệu

Một phép ước lượng sơ bộ:

\[
T_{\text{transfer}} \approx \frac{\text{Dung lượng truyền (bit)}}{\text{Throughput hữu dụng (bit/giây)}}
\]

Ví dụ cần chuyển **4 TiB** qua kết nối có tốc độ danh nghĩa **200 Mbit/s**:

\[
T_{\text{lý tưởng}} \approx
\frac{4\times 1024^4\times 8}{200\times10^6}
\approx 48{,}9\ \text{giờ}
\]

Nếu chỉ đạt **60%** băng thông danh nghĩa vì overhead/cạnh tranh lưu lượng, thời gian ước lượng tăng lên **khoảng 81,5 giờ**. Phép tính chưa tính thay đổi dữ liệu trong lúc copy, checksum, retry, nén, độ trễ công cụ và giới hạn đọc từ nguồn/ghi vào đích.

Với dữ liệu lớn, có thể cân nhắc phương pháp truyền offline hoặc công cụ chuyển dữ liệu phù hợp như dịch vụ của Azure khi đủ điều kiện; phải xác minh khả năng sẵn có hiện tại, mức hỗ trợ, bảo mật và thời gian logistics. Lựa chọn **online replication, staged copy hoặc offline** phải gắn với RPO/downtime thực tế.

## 8. Công cụ Azure hỗ trợ discovery và assessment

### 8.1. Azure Migrate

**Azure Migrate** là nền tảng giúp tập trung khám phá, đánh giá và lập kế hoạch di chuyển những workload được hỗ trợ lên Azure. Trong các kịch bản phù hợp, có thể triển khai appliance/collector hoặc dùng cơ chế discovery tương ứng để lấy thông tin server và đánh giá mức sẵn sàng/sizing. Khả năng assessment/migration thực tế khác nhau theo **VMware, Hyper-V, physical servers, nguồn cloud khác, hệ điều hành, database và phiên bản công cụ**.

Quy trình học thuật:

~~~text
Tạo Azure Migrate project (trong subscription/region phù hợp)
    -> Xác định source environment và phạm vi quyền
    -> Discovery tài sản theo cơ chế hỗ trợ
    -> Để dữ liệu hiệu năng đủ cửa sổ quan sát
    -> Nhóm máy theo workload/dependency
    -> Assessment readiness, sizing, estimated cost
    -> Kiểm tra findings/unsupported dependencies bằng thủ công
    -> Xây migration waves và pilot
~~~

**Kết quả “Azure ready” không có nghĩa ứng dụng đã sẵn sàng nghiệp vụ.** Một máy có thể chạy trên Azure VM nhưng vẫn không truy cập được license server, thiết bị nội bộ hoặc database, hoặc không đáp ứng ràng buộc về dữ liệu. Do đó cần kết hợp máy móc với review kỹ thuật và owner.

### 8.2. Đánh giá database và ứng dụng

Với database, có thể dùng những khả năng đánh giá tương thích và migration của hệ sinh thái Azure phù hợp với engine/đích, ví dụ các luồng dành cho Azure SQL hoặc **Azure Database Migration Service** khi kịch bản được hỗ trợ. Tên công cụ, chế độ online/offline và tính năng có thể thay đổi, nên cần kiểm tra hỗ trợ engine/version, source/target và phương thức replication trước khi ra quyết định.

Với ứng dụng web, đánh giá runtime/OS/framework, authentication, filesystem, session state, native dependency và các tính năng PaaS đích trước khi đề xuất App Service, Container Apps, AKS hoặc Functions.

### 8.3. Azure Arc không đồng nghĩa Azure Migrate

**Azure Arc** giúp quản lý/quản trị một số tài nguyên chạy ngoài Azure bằng các khả năng tích hợp và chính sách được hỗ trợ. Arc có thể hữu ích để duy trì mô hình **hybrid** và quản trị server/Kubernetes ở nơi khác, nhưng **việc onboard một server vào Arc không tự chuyển server đó lên Azure**.

Phân biệt:

| Công cụ/nhóm khả năng | Phù hợp để làm gì? | Không tự làm điều gì? |
| --- | --- | --- |
| **Azure Migrate** | Discovery, assessment, orchestration migration trong phạm vi hỗ trợ | Không đảm bảo mọi app/database tương thích nghiệp vụ |
| **Azure Database Migration tooling** | Di chuyển dữ liệu/database theo source/target hỗ trợ | Không thay thế ứng dụng test, schema/permission review |
| **Azure Arc** | Quản trị môi trường hybrid theo khả năng hỗ trợ | Không tự rehost workload vào Azure |
| **Azure Monitor / Application Insights** | Baseline, dependency tracing và so sánh hậu migration | Không tự quyết định R-strategy |
| **Cost Management / Pricing Calculator** | Ước tính, theo dõi và quản lý chi phí theo điều kiện | Không thay thế TCO và giá hợp đồng |

Trước khi thu thập telemetry, phải xác minh quyền truy cập, nguồn dữ liệu, mạng, chi phí tool và bảo mật của appliance/agent.

## 9. Bảy chiến lược thường gọi là “7 Rs”

Có nhiều cách đặt tên và phân nhóm “R strategies” trong các tài liệu khác nhau. Mô hình dưới đây là một **khung ra quyết định**, không phải danh mục tính năng cố định của Azure.

| Chiến lược | Ý nghĩa | Ví dụ và khi nào cân nhắc | Đánh đổi |
| --- | --- | --- | --- |
| **Retain** | Giữ workload ở môi trường hiện tại trong một giai đoạn | Thiết bị điều khiển tại nhà máy, dữ liệu chưa được phép chuyển | Cần kết nối và quản trị hybrid; còn chi phí/vấn đề tại chỗ |
| **Retire** | Ngừng hệ thống không còn tạo giá trị | Dịch vụ báo cáo không có người dùng sau xác minh | Phải kiểm tra dữ liệu lưu trữ, legal hold và tích hợp còn dùng |
| **Rehost** (*lift and shift*) | Chuyển hệ thống với ít thay đổi ứng dụng | VM từ data center sang Azure VM | Nhanh hơn nhưng giữ kỹ thuật cũ, khó tối ưu PaaS |
| **Relocate** | Di chuyển môi trường/stack có tính liên tục nền tảng theo cách hỗ trợ | Một số kịch bản chuyển workload VMware sang **Azure VMware Solution** | Phụ thuộc stack, licensing, capacity và chi phí dịch vụ |
| **Replatform** (*lift, tinker and shift*) | Điều chỉnh vừa đủ để dùng nền tảng quản lý hơn | Web app sang App Service; database có thể sang managed service tương thích | Cần kiểm thử compatibility, connection và vận hành |
| **Refactor / Rearchitect** | Thay đổi kiến trúc/cấu trúc code để đạt mục tiêu mới | Tách monolith, chuyển state ra ngoài, event-driven | Rủi ro/duration cao, đòi hỏi test và phát triển đáng kể |
| **Repurchase / Replace** | Thay bằng sản phẩm/SaaS khác | Thay hệ thống quản lý công việc cũ bằng SaaS | Migration dữ liệu, quy trình, license, tích hợp và lock-in |

**Ví dụ dễ nhầm:** chuyển từ SQL Server on-prem sang **SQL Server chạy trong Azure VM** gần với rehost database; chuyển sang **Azure SQL Managed Instance** hay **Azure SQL Database** thường là replatform nếu tương thích nhưng vẫn phải xem những thay đổi cần làm. Đổi sang mô hình dữ liệu mới hoặc chia kiến trúc giao dịch có thể là refactor. Một migration thực tế thường kết hợp nhiều R.

### 9.1. Câu hỏi sàng lọc theo thứ tự

1. Workload có còn người dùng, nghĩa vụ lưu trữ hoặc business value? Nếu không, xem **retire**.
2. Có ràng buộc không thể chuyển ngay: pháp lý, thiết bị, phụ thuộc hoặc license? Xem **retain** trong kế hoạch hybrid có thời hạn đánh giá lại.
3. Có sản phẩm/SaaS thay thế phù hợp hơn, dữ liệu có thể chuyển và hợp đồng hợp lý? Xem **repurchase**.
4. Cần rời data center nhanh, ứng dụng ổn định và VM đích tương thích? Xem **rehost/relocate**.
5. Có thể giảm vận hành nhờ dịch vụ quản lý mà không thay đổi lớn? Xem **replatform**.
6. Mục tiêu chính là agility, scale, reliability hoặc cấu trúc nghiệp vụ mới mà kiến trúc cũ không đáp ứng? Xem **refactor/rearchitect**.

Không chọn R chỉ theo tên công nghệ. Phải đối chiếu thời gian, dữ liệu, bảo mật, khả năng test, đội ngũ, tiền bạc và tính đúng đắn của từng thao tác.

## 10. Khung đánh giá để chọn chiến lược

### 10.1. Tiêu chí và bằng chứng

| Tiêu chí | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Business value** | Di chuyển có giảm rủi ro/hỗ trợ mục tiêu kinh doanh không? | Deadline, doanh thu, người dùng, yêu cầu hợp đồng |
| **Technical compatibility** | OS/runtime/database/driver có hỗ trợ ở đích không? | Compatibility assessment và PoC |
| **Dependency complexity** | Có bao nhiêu thành phần phải chuyển đồng bộ? | Dependency graph đã xác nhận |
| **Data risk** | Khối lượng, write rate, consistency, residency ra sao? | Data inventory, RPO/RTO, kiểm thử replication |
| **Security/compliance** | Landing zone và quy trình đáp ứng yêu cầu không? | Control mapping, risk approval |
| **Operating model** | Nhóm có vận hành AKS/PaaS hay cần managed service? | Skill matrix, support model |
| **Cost/TCO** | CAPEX/OPEX, license, egress, monitoring, dual run? | Baseline bills, pricing/quotes, assumptions |
| **Timeline/reversibility** | Có kịp deadline và rollback được không? | Plan, cutover rehearsal, risk register |

Một lựa chọn có vẻ tối ưu chi phí nhưng **không đáp ứng cư trú dữ liệu hoặc RTO** phải bị loại trước khi tính điểm. Hãy phân biệt **hard constraints** (bắt buộc) và **trade-offs** (có thể đánh đổi).

### 10.2. Ma trận chọn chiến lược theo thành phần

| Workload / thành phần | Rehost | Replatform | Refactor | Retain/Repurchase | Điều cần chứng minh |
| --- | --- | --- | --- | --- | --- |
| API web stateless, runtime được hỗ trợ | Có thể | Có tiềm năng App Service/Container Apps | Khi cần scale độc lập | Hiếm khi retain vĩnh viễn | Deployment, session, auth, OS dependency |
| Ứng dụng Windows cũ dùng COM/native DLL | Có thể nếu VM hỗ trợ | Có thể không tương thích PaaS | Cần viết lại phần phụ thuộc | Có thể retain tạm | Test binary/driver và license |
| SQL Server với linked server và SQL Agent jobs | VM khả thi | Managed Instance hoặc dịch vụ khác sau đánh giá | Có thể tách tính năng | Retain khi chưa đáp ứng | Compatibility, HA, cutover, logins |
| File share lớn, SMB nhiều thao tác nhỏ | VM/file service tương thích | Azure Files hoặc giải pháp phù hợp | Đổi sang object storage | Retain tạm nếu latency không đạt | ACL, locks, throughput, latency |
| Batch độc lập theo lịch | VM | Managed batch/container/Functions khi phù hợp | Event-driven nếu có ích | Retire nếu không còn dùng | Scheduling, idempotency, deadline |
| Hệ thống công nghiệp có thiết bị cục bộ | VM gần thiết bị | Tùy giao thức/latency | Edge + cloud analytics | Retain/hybrid thường cần xem xét | Offline operation, latency, an toàn |
| CRM mua ngoài | VM nếu được license | PaaS khó nếu là phần mềm đóng | Ít phù hợp khi không có source | Repurchase SaaS | Data export, contract, integrations |

**Đây là ví dụ gợi ý, không phải kết luận cuối cùng.** Dịch vụ đích và phiên bản được hỗ trợ phải được xác minh bằng PoC và tài liệu hiện hành trước khi chốt.

## 11. Xếp ưu tiên workload bằng điểm có giải thích

Để chọn pilot và migration wave, có thể dùng điểm số. Điểm chỉ hỗ trợ quyết định, **không thay thế các điều kiện bắt buộc** và dependency order.

Một mô hình giả định chấm mỗi yếu tố từ 1–5, điểm cao nghĩa là **phù hợp chuyển sớm hơn**:

- **Business opportunity** (30%): lợi ích của việc chuyển sớm; không đồng nghĩa mức độ thiệt hại nếu lỗi.
- **Technical ease** (25%): khả năng chuyển ít thay đổi, dễ test.
- **Dependency readiness** (25%): dependency đã được hiểu và có thể kết nối/di chuyển.
- **Low-risk/reversibility** (20%): mức độ kiểm soát và khả năng rollback tốt.

\[
Score=0{,}30B+0{,}25E+0{,}25D+0{,}20R
\]

| Workload | B | E | D | R | Điểm | Nhận định |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Portal nội bộ không quan trọng | 2 | 5 | 5 | 5 | **4,10** | Pilot phù hợp, ít ảnh hưởng |
| API catalog độc lập | 4 | 4 | 4 | 4 | **4,00** | Wave sớm sau pilot |
| Hệ thống thanh toán cốt lõi | 5 | 2 | 1 | 2 | **2,65** | Quan trọng nhưng khó; cần dependency và rehearsals |

Ví dụ portal: \(0{,}30×2+0{,}25×5+0{,}25×5+0{,}20×5=4{,}10\).

**Điểm cao không có nghĩa được tự động migrate.** Nếu một portal phụ thuộc vào identity service chưa sẵn sàng hoặc sản phẩm có yêu cầu lưu dữ liệu không thể đáp ứng, thứ tự sẽ thay đổi. Các trọng số chỉ là giả định để minh họa phương pháp; doanh nghiệp có thể chọn khác theo rủi ro.

## 12. Ghép workload với năng lực Azure

Sau khi chọn R, mới chọn dịch vụ cụ thể. Một số hướng tham khảo:

| Nhu cầu đã khảo sát | Đích Azure cần đánh giá | Điều kiện cần kiểm chứng |
| --- | --- | --- |
| Rehost Linux/Windows VM | **Azure Virtual Machines**, managed disks, availability design | OS support, image, VM sizing, drivers, license |
| Ứng dụng web/API có runtime được hỗ trợ | **Azure App Service** | Runtime version, filesystem, auth, networking, session state |
| Workload container với nhu cầu orchestration phức tạp | **Azure Kubernetes Service (AKS)** | Skill vận hành, networking, image registry, security, cluster/node cost |
| Container app có mô hình vận hành managed phù hợp | **Azure Container Apps** | Scaling, networking, persistence, integration |
| Hàm/event-driven | **Azure Functions** | Trigger, timeout, plan, concurrency, cold start, state |
| SQL Server cần tương thích cao | **SQL Server on Azure VM**, đánh giá **Azure SQL Managed Instance** | Tính năng engine, SQL Agent, linked server, network và license |
| Cần database PaaS theo khả năng được hỗ trợ | **Azure SQL Database** hoặc dịch vụ dữ liệu tương ứng | Schema, SQL compatibility, HA, DR, performance |
| Dữ liệu object/file | **Azure Blob Storage, Azure Files** | Protocol, ACL, latency, throughput, lifecycle/retention |
| Queue/event | **Azure Service Bus, Event Hubs** theo loại message | Delivery semantics, ordering, retry, throughput |
| Danh tính Azure workloads | **Microsoft Entra ID**, managed identities | Federation, legacy AD/Kerberos needs, authorization |
| Kết nối hybrid | **Site-to-Site VPN, ExpressRoute** theo nhu cầu | Bandwidth, redundancy, route, SLA, security và chi phí |
| Quản trị server hybrid | **Azure Arc** trong phạm vi hỗ trợ | Governance, agent, identity, policy, logs |

Không đưa thành phần đang dùng AD/Kerberos vào Entra ID rồi giả định có thể bỏ domain controller ngay. **Entra ID không phải thay thế trực tiếp cho mọi khả năng của Active Directory Domain Services**. Với ứng dụng legacy, cần phân tích domain join, LDAP, Kerberos, group policy và phương án danh tính phù hợp.

### 12.1. Chọn region và HA/DR

Region phải đáp ứng dữ liệu, độ trễ, availability của từng SKU/dịch vụ, networking, chi phí và sự hiện diện của các dịch vụ phụ thuộc. Cần phân biệt:

- **Availability Zone** nhằm tăng sức chịu lỗi trong region khi dịch vụ/region hỗ trợ.
- **Cross-region replication/DR** nhằm ứng phó sự cố rộng hơn nhưng có chi phí, độ trễ và ràng buộc dữ liệu riêng.
- **Backup/restore** nhằm phục hồi dữ liệu; phải thử khôi phục và xác nhận điểm phục hồi.

Đừng chọn region chỉ vì gần người dùng nếu nó không hỗ trợ dịch vụ hoặc ràng buộc dữ liệu của doanh nghiệp.

## 13. Chi phí migration và TCO: so sánh trên cùng phạm vi

Phí Azure hàng tháng **không phải toàn bộ chi phí migration**. Một đánh giá TCO nên bao gồm:

| Nhóm | Nguồn chi phí |
| --- | --- |
| **On-prem hiện tại** | Phần cứng, khấu hao/thuê, điện/làm mát, rack, network, license, backup, DR, nhân sự vận hành |
| **Azure target** | Compute/VM/PaaS, storage, snapshot/backup, database, monitoring, network egress, support, license, reservations/savings plan nếu đủ điều kiện |
| **One-time migration** | Khảo sát, thử nghiệm, chuyển dữ liệu, viết code, đào tạo, cutover rehearsal, thuê chuyên gia |
| **Dual run** | Hai môi trường chạy song song, replication, VPN/ExpressRoute, log và các tài nguyên tạm |
| **Rủi ro/gián đoạn** | Downtime, hiệu năng kém, hỗ trợ ngoài giờ, rollback, rủi ro kinh doanh |
| **Vận hành sau chuyển** | CI/CD, bảo mật, compliance, monitoring, incident response, kỹ năng vận hành |

### 13.1. Ví dụ TCO đơn giản trong 36 tháng

**Số giả định**, để minh họa cách so sánh:

| Khoản | Giữ on-prem 36 tháng | Chuyển sang Azure 36 tháng |
| --- | ---: | ---: |
| Hạ tầng/compute và phần vận hành liên quan | 36.000 USD | 48.600 USD (1.350 USD/tháng × 36) |
| Hosting/điện/mạng tại chỗ | 18.000 USD | Đã tính trong giả định Azure ở hàng trên |
| Vận hành/backup/license khác | 12.000 USD | Đã bao gồm trong 1.350 USD/tháng theo giả định |
| Dự án migration một lần | 0 USD | 12.000 USD |
| Dual run và thử nghiệm | 0 USD | 3.000 USD |
| **Tổng giả định** | **66.000 USD** | **63.600 USD** |

Chênh lệch trong ví dụ là **2.400 USD** trong ba năm (khoảng **3,64%** của 66.000 USD). Mức này có thể bị xóa bỏ hoàn toàn nếu giả định network egress, license, dữ liệu tăng hoặc vận hành thay đổi. Vì vậy **không được kết luận chắc chắn Azure rẻ hơn từ bảng minh họa**.

Khi tính thật, loại bỏ double count, xét chi phí chìm/khấu hao hợp lệ, mức độ tiết kiệm phần cứng sau di chuyển và các chi phí tiếp tục tồn tại. Đơn giá công khai từ Pricing Calculator chưa chắc là giá hợp đồng thực. Cam kết reservations/savings plans hay Azure Hybrid Benefit chỉ nên đưa vào khi đủ điều kiện và mô hình tải phù hợp.

### 13.2. Tính sensitivity

Thay đổi ba biến quan trọng để thấy quyết định có bền vững không:

- Peak compute tăng 30% sau migration.
- Dữ liệu cần truyền qua region khác nhiều hơn 2 lần.
- Dual run kéo dài thêm 2 tháng do cutover thất bại.

Một phương án có TCO thấp ở kịch bản tối ưu nhưng tăng mạnh ở kịch bản xấu có thể rủi ro hơn phương án có dự toán cao hơn nhưng ổn định. Finance và business owner cần biết **biên độ** chứ không chỉ một giá trị tổng.

## 14. Chuẩn bị Azure landing zone trước khi di chuyển

**Landing zone** là nền móng quản trị và vận hành để ứng dụng lên Azure không trở thành những tài nguyên rời rạc thiếu kiểm soát.

### 14.1. Checklist kiến trúc nền

| Lĩnh vực | Việc cần chuẩn bị |
| --- | --- |
| **Subscription/governance** | Ranh giới môi trường, naming, tags, management groups/Policy nếu áp dụng |
| **Identity** | Microsoft Entra ID, nhóm quyền, managed identities, service principals/federation, privileged access |
| **Network** | VNet/subnet, IP planning, route, DNS, firewall, proxy, private endpoints, ingress/egress |
| **Hybrid connectivity** | VPN/ExpressRoute, redundancy, bandwidth, route overlap, DNS resolution hai chiều |
| **Security** | Policy, encryption, Key Vault, logging, segmentation, vulnerability/patch management |
| **Observability** | Azure Monitor, Application Insights, Log Analytics, alert, SLO dashboard |
| **Operations** | Backup/restore, DR test, incident runbook, change management, IaC, CI/CD |
| **Cost** | Budget, tags/cost center, quota, sizing review, region, data transfer, shutdown policy |
| **Resilience** | Zone/region design, service health, capacity khi failover, restore test |

Không yêu cầu mọi pilot phải có toàn bộ mô hình production phức tạp, nhưng **pilot production-bound** vẫn phải có baseline kiểm soát bảo mật, chi phí và dữ liệu. Tách rõ thứ nào là điều kiện tối thiểu, thứ nào được hoàn thiện ở wave sau.

### 14.2. Ví dụ topology hybrid

~~~mermaid
flowchart LR
    subgraph DC["Data center tại chỗ"]
      Legacy["Legacy app + database"]
      AD["AD/DNS"]
    end
    subgraph AZ["Azure landing zone"]
      HUB["Hub VNet / Firewall / DNS"]
      SPOKE["Workload Spoke VNet"]
      APP["App Service/VM/AKS"]
      DATA["Managed database / storage"]
      MON["Monitor + Key Vault"]
      HUB --- SPOKE
      SPOKE --> APP
      APP --> DATA
      APP --> MON
    end
    DC <-->|"VPN hoặc ExpressRoute"| HUB
    APP -. "Identity/dependency tạm thời" .-> AD
    APP -. "Tạm truy cập dữ liệu gốc khi cần" .-> Legacy
~~~

Sơ đồ chỉ minh họa một mô hình hub-spoke; việc dùng private endpoint, DNS forwarder, route hoặc kết nối đi/đến thực tế phụ thuộc thiết kế và dịch vụ. Tránh CIDR overlap giữa on-prem và Azure. Đặc biệt phải kiểm tra **DNS resolution, MTU, outbound path, port allowlist và chiều kết nối**, không chỉ ping thành công.

## 15. Lập migration waves theo dependency

Một *wave* là nhóm workload/thành phần được chuẩn bị, thử nghiệm và cutover trong một khoảng có quản trị. Nên chọn theo **dependency graph** và **business window**, không chia máy theo số lượng đều nhau.

### 15.1. Thứ tự tham khảo

| Wave | Nội dung | Điều kiện vào | Điều kiện thoát |
| --- | --- | --- | --- |
| **0 – Foundation** | Landing zone, identity, network, monitoring, backup, quota | Kiến trúc và bảo mật phê duyệt | Kết nối/test truy cập, policy, alert, backup hoạt động |
| **1 – Pilot** | Portal nội bộ ít quan trọng | Owner, inventory, dependency, rollback sẵn | Chạy ổn định, tài liệu thao tác và số liệu thực |
| **2 – Supporting services** | Các dịch vụ phụ ít phụ thuộc hoặc nền chung | Pilot đạt, dịch vụ dùng chung sẵn | Integration tests, latency, SLO đạt |
| **3 – Business apps** | Catalog/API trung bình | Database/network khả dụng, cutover rehearsal | Chức năng, dữ liệu, hiệu năng, bảo mật được duyệt |
| **4 – Critical flows** | Orders/payment trong phạm vi cho phép | Dependency chain đã giải quyết, DR/rollback tập dượt | Business sign-off, reconciliation, SLO và audit đạt |
| **5 – Optimization/decommission** | Rightsizing, xử lý nợ kỹ thuật, gỡ nguồn cũ | Hết giai đoạn song song, không còn phụ thuộc | Bảo quản/xóa dữ liệu theo chính sách, kết thúc chi phí cũ |

Đây là cấu trúc ví dụ, **không bắt buộc đúng thứ tự với mọi doanh nghiệp**. Nếu một dependency phục vụ các ứng dụng còn ở on-prem, phải duy trì kết nối hybrid trong thời gian chuyển tiếp hoặc điều chỉnh wave để tránh làm gián đoạn ứng dụng cũ.

### 15.2. Không chỉ chuyển web trước database

Nếu API và database trao đổi dữ liệu chặt chẽ, chuyển API trước có thể tăng latency và làm giảm hiệu năng đáng kể. Trong trường hợp đó:

- Chuyển thành phần có dependency thấp trước để luyện quy trình.
- Với hệ thống chặt chẽ, xem một **migration unit** gồm API + DB hoặc dùng replication/connection plan đủ tốt.
- Chia dữ liệu/traffic theo chức năng khi kiến trúc hỗ trợ; không chia theo máy một cách cơ học.
- Xác nhận upstream và downstream không bị quên trong cutover.

**Graph phụ thuộc phải có thứ tự và ownership**, không chỉ là sơ đồ đẹp. Một node thiếu đường kết nối hoặc phụ thuộc ở môi trường khác có thể làm toàn bộ wave thất bại.

## 16. Chọn cách di chuyển dữ liệu: offline, online và staged migration

### 16.1. Ba mô hình thường gặp

| Cách | Cơ chế khái niệm | Phù hợp khi | Rủi ro |
| --- | --- | --- | --- |
| **Offline migration** | Dừng ghi, sao chép dữ liệu, xác minh, chuyển ứng dụng | Downtime đủ dài, dữ liệu có kích thước/tốc độ hợp lý | Gián đoạn lâu nếu copy/restore chậm |
| **Online migration/replication** | Đồng bộ ban đầu, tiếp tục replicate thay đổi, cutover khi lag thấp | Downtime ngắn, công cụ và source/target hỗ trợ | Lag, consistency, cutover và rollback phức tạp |
| **Staged/hybrid migration** | Chuyển từng nhóm dữ liệu/chức năng, duy trì kết nối giữa hai nơi | Ứng dụng có thể tách theo domain hoặc workload | Cross-site latency, giao dịch phân tán, data ownership |

**Online không có nghĩa zero downtime**. Vẫn cần một thời điểm chuyển ownership của ghi, kiểm tra dữ liệu và định tuyến client. Khả năng online/offline tùy engine, version và công cụ cụ thể.

### 16.2. Cutover dữ liệu an toàn

Một chuỗi bước khái niệm:

1. Backup và **kiểm thử restore** trước đợt chuyển quan trọng.
2. Đồng bộ bản đầy đủ và phát lại thay đổi (nếu phương pháp hỗ trợ).
3. Giảm DNS TTL trước cutover khi có tác dụng và đủ thời gian cho cache DNS hiện hữu.
4. Đặt hệ thống nguồn vào chế độ **read-only hoặc tạm dừng ghi** theo hợp đồng nghiệp vụ.
5. Chờ replication đạt điều kiện lag/consistency, xác minh checksum/tổng nghiệp vụ.
6. Chuyển ứng dụng và hướng kết nối sang đích; cho phép một **single writer** duy nhất.
7. Chạy smoke test, kiểm tra giao dịch mới và quan sát trong cửa sổ kiểm soát.
8. Chỉ mở ghi đầy đủ khi owner chấp nhận kết quả; tiếp tục hậu kiểm và ghi nhận trạng thái.

**Không duy trì dual-write tùy tiện** giữa hai database độc lập. Nếu cần ghi song song, phải có thiết kế phân xử xung đột, transaction/idempotency, nguồn sự thật và chiến lược hợp nhất được kiểm chứng. Chuyển DNS đơn thuần cũng không bảo đảm mọi client đã đổi ngay: có cache DNS, connection pool, các kết nối dài và IP allowlist.

## 17. Runbook cutover và rollback

Một migration plan chưa đầy đủ nếu chỉ ghi “chạy công cụ và chuyển DNS”. Cần runbook có mốc kiểm tra và người chịu trách nhiệm.

### 17.1. Mẫu cutover runbook

| Giai đoạn | Hành động | Bằng chứng cần xác minh | Người phụ trách |
| --- | --- | --- | --- |
| **T−7 ngày** | Chốt scope, thay đổi cấu hình, xin quyền, kết quả rehearsal | Change ticket, dependency list, backup test | Migration lead |
| **T−1 ngày** | Xác nhận sync/replication, quota, capacity, key/certificate | Lag, health, monitoring, contact list | DBA/Platform |
| **T−30 phút** | Go/no-go, thông báo stakeholders, đóng thay đổi | Phê duyệt, không có sự cố blocker | Business/SRE |
| **T0** | Quiesce writes, chụp điểm khôi phục cần thiết | Không còn giao dịch ghi ngoài kế hoạch | App/DBA |
| **T+** | Final sync và kiểm tra consistency | Row counts, checksum, invariants nghiệp vụ | DBA/Data |
| **T+** | Chuyển traffic, health/smoke tests | Authentication, API, database, logs, payment sandbox | App/Network |
| **T+** | Theo dõi SLO, lỗi, latency, chi phí, security | Dashboard và log kiểm tra | SRE/Owner |
| **Sau ổn định** | Owner sign-off, dừng đường ghi cũ, kế hoạch decommission | Báo cáo nghiệm thu | Business/FinOps |

Các mốc chỉ mang tính minh họa. Thời gian thực phải thiết kế theo **downtime window và tốc độ sync** đo được. Không ra quyết định bằng một checklist được điền cho đủ mà thiếu bằng chứng.

### 17.2. Quy tắc go/no-go

**Go** khi: landing zone an toàn, dependency path hoạt động, backup/restore đã kiểm chứng, replication lag đạt ngưỡng, nguồn lực support có mặt, fallback rõ và rehearsal thành công. **No-go** nếu một điều kiện bắt buộc chưa đạt, ví dụ:

- Không có bản backup đã kiểm thử restore.
- Chưa chứng minh traffic/identity tới hệ thống thanh toán.
- Database schema có chức năng chưa hỗ trợ.
- Đường truyền hoặc quota thiếu so với tải dự kiến.
- Không có phương án bảo đảm không mất giao dịch đã xác nhận.
- Người phê duyệt nghiệp vụ không sẵn sàng.

### 17.3. Rollback khác “trỏ DNS về cũ”

Trước khi nguồn mới nhận ghi, rollback có thể tương đối đơn giản (đưa traffic về nguồn). **Sau khi đích đã nhận dữ liệu mới**, rollback phức tạp hơn: phải trả lời dữ liệu mới chuyển về nguồn cũ bằng cách nào, xử lý giao dịch đang chạy ra sao, và ai xác nhận kết quả.

Ví dụ nếu sau cutover có 1.000 đơn hàng mới ở Azure:

- Chỉ đổi DNS về database cũ sẽ làm các đơn đó **không xuất hiện** ở hệ thống cũ, dù ứng dụng có thể khởi động lại.
- Cần cơ chế reverse replication/đối soát/replay transaction đã thiết kế trước, hoặc chọn **roll forward** sửa lỗi trên đích.
- Nếu không thể rollback dữ liệu an toàn, phải tuyên bố rõ **rollback giới hạn trước thời điểm mở ghi** và có kế hoạch roll forward sau đó.

Điều kiện rollback phải đo được, ví dụ tỷ lệ lỗi vượt ngưỡng trong khoảng đã định hoặc mất một chức năng cốt lõi. Không quyết định rollback chỉ dựa trên cảm giác khi chi phí dữ liệu lớn.

## 18. Bảo mật và compliance trong cả quá trình migration

Di chuyển thường tạo thêm đường truy cập, quyền tạm thời và bản sao dữ liệu, do đó cần bảo vệ từ lúc discovery đến khi xóa hệ thống nguồn.

### 18.1. Những điểm cần kiểm soát

- **Least privilege:** tài khoản discovery/migration chỉ có quyền cần thiết ở source và Azure target, hạn chế role có phạm vi subscription rộng.
- **Identity:** ưu tiên cơ chế danh tính phù hợp như Microsoft Entra ID/managed identities hoặc workload identity federation khi dịch vụ và tool hỗ trợ; tránh lưu secret dài hạn trong script.
- **Secrets/certificates:** lưu và luân chuyển bằng cơ chế quản lý bí mật phù hợp, không commit password vào Git hoặc inventory.
- **Encryption:** mã hóa dữ liệu in transit/at rest theo yêu cầu, kiểm tra ownership và rotation của key.
- **Network security:** giới hạn ingress/egress, private connectivity, NSG/firewall, DNS và monitoring.
- **Data classification:** chỉ chuyển dữ liệu vào các region và dịch vụ đã được phép; không dùng dữ liệu production nhạy cảm trong pilot nếu không có phê duyệt.
- **Audit:** ai chạy migration, thay đổi permission, cutover và rollback lúc nào.
- **Temporary resources:** appliance, agent, staging storage, backup, snapshot, public IP, VPN và credential tạm phải có lịch dọn dẹp.

Không nên **vô hiệu hóa logging, antivirus, database encryption hoặc firewall** chỉ để quá trình copy nhanh hơn nếu chưa có đánh giá, biện pháp bù và chấp thuận bảo mật. Trong một số trường hợp cần cấu hình ngoại lệ tạm thời, phải giới hạn phạm vi/thời gian và có kế hoạch thu hồi.

### 18.2. Di chuyển danh tính

Sơ đồ authentication cũ có thể dựa trên AD DS, LDAP, Kerberos, service account, máy chủ RADIUS hoặc SSO riêng. Phải phân tích:

1. Người dùng và tài khoản dịch vụ nào xác thực với hệ thống nào.
2. Quyền được gán bằng group/role nào, có delegation hoặc trust không.
3. Các ứng dụng có hardcode domain name, SID, LDAP path hoặc service principal name không.
4. Có yêu cầu đồng bộ danh tính hoặc tiếp tục giữ AD tại chỗ trong giai đoạn hybrid không.
5. Có thể chuyển sang Entra/OIDC/SAML hoặc managed identity với mức thay đổi chấp nhận được không.

**Không thay thế IAM bằng việc dùng chung một tài khoản quản trị** cho toàn bộ dịch vụ mới. Migration là cơ hội cải thiện bảo mật, nhưng thay đổi phương thức xác thực lớn cần test đúng luồng nghiệp vụ.

## 19. Kiểm thử migration trước khi production cutover

### 19.1. Những lớp kiểm thử

| Nhóm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Functional** | Luồng nghiệp vụ có đúng không? | Tạo đơn, hoàn trả, xuất báo cáo, tải file |
| **Integration** | Các dependency còn hoạt động? | Payment gateway, AD, SMTP, NAS, batch jobs |
| **Data integrity** | Dữ liệu có đầy đủ và nhất quán? | Row counts, checksums, balances, khóa ngoại |
| **Performance** | Đạt peak RPS, p95/p99, throughput? | Load test cùng mix request với baseline |
| **Security** | Quyền, secret, encryption, audit đúng? | Pentest/risk review theo scope được phép |
| **Resilience/DR** | Mất instance/zone hoặc khôi phục backup thế nào? | Failover/restore rehearsal ở môi trường kiểm soát |
| **Operations** | Có alert, runbook, backup, patch, deploy? | On-call simulation, restore thử, rollback |
| **Financial** | Chi phí có nằm trong forecast? | Cost Analysis, log ingestion, egress/dual-run |

Kết quả **server boot thành công** không đủ nghiệm thu. Một ứng dụng có thể hoạt động trên VM mới nhưng batch cuối tháng không chạy, dữ liệu mới vào sai region, chứng từ không đọc được hoặc thông báo email không gửi ra ngoài.

### 19.2. Baseline trước và sau

Một bảng nghiệm thu giả định:

| Chỉ số | Trước migration | Mục tiêu sau | Kết quả test (minh họa) | Đánh giá |
| --- | ---: | ---: | ---: | --- |
| Peak throughput | 120 RPS | Ít nhất 120 RPS | 135 RPS | Đạt |
| API p95 | 350 ms | Không quá 400 ms | 370 ms | Đạt |
| Business success | 99,95% | Ít nhất 99,95% | 99,98% | Đạt về chỉ số |
| Restore time | 90 phút | Không quá 120 phút | Chưa diễn tập | **Chưa đạt bằng chứng** |
| Critical batch | 24 job/tháng | 24 job chạy đúng | 22/24 đã test | **Chưa nghiệm thu** |
| Data reconciliation | Không mất giao dịch | Chênh lệch 0 theo quy tắc | 0 sau đối soát | Đạt |

Không tuyên bố **migration completed** chỉ vì ba chỉ số đầu đạt trong khi kiểm thử DR hoặc batch quan trọng còn thiếu. “Chưa có bằng chứng” phải được giữ đúng trạng thái và xử lý.

## 20. Ví dụ tổng hợp: chọn chiến lược cho hệ thống Orders

### 20.1. Hệ thống hiện hữu

Doanh nghiệp có:

- **Orders web:** ứng dụng frontend có thể triển khai lại bằng CI/CD.
- **Orders API:** chạy trên hai VM Windows, phụ thuộc session state cục bộ và file share.
- **SQL Server:** database 1,2 TiB, dùng SQL Agent jobs và một linked server.
- **NAS:** chứa hóa đơn/chứng từ, nhiều thao tác SMB.
- **Active Directory:** cung cấp danh tính cho nhân viên, cũng phục vụ hệ thống cũ khác.
- **Payment provider:** API HTTPS của đối tác có IP allowlist và hỗ trợ idempotency theo hợp đồng.
- **Batch reporting:** chạy cuối tháng, chưa được kiểm thử tải và dependency đầy đủ.

Business owner yêu cầu **downtime planned không quá 30 phút**, không mất giao dịch đã xác nhận, latency p95 không quá 400 ms ở peak 120 RPS và tránh thay đổi kiến trúc thanh toán trong kỳ cao điểm.

### 20.2. Quyết định sơ bộ theo thành phần

| Thành phần | Chiến lược sơ bộ | Azure target cần thử | Lý do và điều kiện |
| --- | --- | --- | --- |
| Orders web | **Replatform** | App Service hoặc container platform phù hợp | Dễ CI/CD, kiểm tra runtime/auth và static assets |
| Orders API | **Replatform theo giai đoạn** | App Service/Container Apps/VM tùy compatibility | Tách session và xử lý file share trước; nếu không đủ thời gian có thể rehost tạm |
| SQL Server | **Rehost trước hoặc replatform sau assessment** | SQL Server on Azure VM; đánh giá Managed Instance/SQL Database | Linked server, jobs, schema/driver cần test; downtime 30 phút đòi hỏi replication |
| NAS file share | **Replatform khi tương thích** | Azure Files hoặc giải pháp phù hợp | Kiểm tra SMB/ACL, lock, latency, throughput |
| AD DS | **Retain/hybrid trong wave đầu** | Kết nối hybrid, đánh giá identity modernization | Hệ thống khác còn phụ thuộc; không thể bỏ ngay |
| Payment integration | **Retain external integration** | HTTPS outbound có kiểm soát | Phê duyệt IP allowlist, retry/idempotency và TLS |
| Batch báo cáo | **Assess, rehost hoặc refactor sau** | VM, service xử lý batch phù hợp | Phải khảo sát lịch và dependency cuối tháng |

**Đây là quyết định có điều kiện**, chưa phải bản thiết kế production. Không kết luận Azure SQL Managed Instance luôn hỗ trợ mọi tính năng SQL Server đang dùng; cần assessment database và PoC.

### 20.3. Vì sao không refactor tất cả ngay?

Phân tách monolith và thay database engine có thể mang lại lợi ích dài hạn, nhưng đồng thời tăng số biến đổi trong một cutover có downtime ngắn. Có thể tách:

1. **Wave 0:** landing zone, hybrid network, danh tính, backup, telemetry.
2. **Wave 1:** pilot dịch vụ báo cáo không critical, xác nhận toolchain và runbook.
3. **Wave 2:** cải thiện session/file dependency, rehearsal API + DB.
4. **Wave 3:** migration Orders theo một nhóm dependency được đánh giá, thực hiện data sync/cutover được đo.
5. **Sau ổn định:** xét tiếp managed database/refactor khi có dữ liệu vận hành thật.

Phương án này chấp nhận một phần nợ kỹ thuật để giảm rủi ro cutover. Nếu hạn chót data center hoặc yêu cầu compliance khác, chiến lược có thể thay đổi.

### 20.4. Các blocker trước khi go-live

- Chưa có bằng chứng linked server/SQL Agent jobs tương thích đích.
- Chưa chứng minh SMB permissions và file lock sau chuyển.
- Payment provider chưa xác nhận endpoint/IP mới.
- Chưa thử nghiệm downtime dưới 30 phút với database 1,2 TiB.
- Chưa có thiết kế xử lý **giao dịch phát sinh sau cutover** khi phải rollback.
- Chưa kiểm tra business batch cuối tháng.
- Chưa đối soát chi phí dual-run và egress từ hệ thống hybrid.

Mỗi blocker cần **owner, deadline, hành động xác minh và quyết định no-go** nếu chưa đạt; không chỉ ghi “rủi ro có thể chấp nhận”.

## 21. Mẫu báo cáo migration assessment

Một bản assessment đủ để review nên có các phần sau:

| Phần | Câu hỏi phải trả lời |
| --- | --- |
| **Executive decision** | Đề xuất chuyển, giữ, thay thế hay ngừng; tại sao? |
| **Business context** | Mục tiêu, deadline, criticality, downtime, stakeholder |
| **Current state** | App inventory, versions, owner, OS, infrastructure, licenses |
| **Dependency graph** | Luồng dữ liệu, auth, network, scheduler, external systems |
| **Baseline** | RPS/p95, CPU/RAM/IOPS, DB growth, backup/restore, cost |
| **Constraints** | Data residency, compliance, unsupported feature, budget |
| **R-strategy comparison** | Lựa chọn, lợi ích, rủi ro, điều kiện loại trừ |
| **Azure target architecture** | Region, landing zone, network, identity, compute, data |
| **Cost/TCO** | On-prem vs Azure, migration/dual-run, kịch bản nhạy cảm |
| **Migration waves** | Nhóm chuyển, dependency order, owner, mốc go/no-go |
| **Data plan** | Online/offline, consistency, CDC/replication, reconciliation |
| **Cutover/rollback** | Runbook, read-only, traffic switch, fallback/roll forward |
| **Acceptance** | Functional, performance, security, DR, operations, cost |
| **Risks/actions** | Risk register, owner, mitigation, deadline, residual risk |

### 21.1. Risk register mẫu

| ID | Rủi ro | Xác suất | Tác động | Biện pháp kiểm chứng/giảm thiểu | Owner |
| --- | --- | --- | --- | --- | --- |
| R-01 | Ứng dụng không truy cập SQL qua hybrid link | Trung bình | Cao | Đo latency, test route/DNS/port, xét chuyển cùng wave | Network/App |
| R-02 | Linked server không tương thích target PaaS | Cao đến khi test | Cao | Assessment tính năng, PoC, phương án SQL VM | DBA |
| R-03 | Replication lag vượt downtime window | Trung bình | Rất cao | Rehearsal với data lớn, thống kê lag, no-go threshold | DBA |
| R-04 | Thiếu quota/IP khi scale | Trung bình | Cao | Capacity và quota check trước wave | Platform |
| R-05 | Chưa đủ bằng chứng backup restore | Trung bình | Rất cao | Restore test, ghi RTO/RPO thực tế | SRE |
| R-06 | Chi phí dual-run kéo dài | Trung bình | Trung bình | Budget, review date, trigger dừng nguồn | FinOps |
| R-07 | Quyền truy cập dữ liệu không tuân thủ | Chưa xác minh | Rất cao | Security approval, data flow mapping và access tests | Security |

Xếp mức rủi ro phải dựa trên bằng chứng và khung đánh giá của tổ chức. “Chưa xác minh” không nên được làm tròn thành “thấp”.

## 22. Thực hành: chọn chiến lược bằng bằng chứng

**Bối cảnh:** Bạn là người lập migration assessment cho một ứng dụng có web, API, SQL Server và file share. Hạ tầng nguồn nằm tại data center; đích dự kiến là Microsoft Azure. Các số liệu dưới đây là giả định và việc thực hành không yêu cầu tạo tài nguyên thực.

### Bài A — Xây inventory

1. Tạo bảng ứng dụng gồm owner, criticality, OS/runtime, database, storage, network, RTO/RPO và lịch batch.
2. Gắn trạng thái **verified/observed/declared/unknown** cho mỗi trường quan trọng.
3. Xác định ít nhất 5 lỗ hổng dữ liệu cần hỏi owner hoặc đo bổ sung.
4. Không ghi secret vào bảng inventory.

**Đầu ra:** bảng kiểm kê đủ để lên kế hoạch khảo sát bổ sung.

### Bài B — Dựng graph phụ thuộc

1. Vẽ luồng từ người dùng qua web/API đến database, file, identity, payment và monitoring.
2. Ghi **protocol, chiều, owner, peak traffic, latency và mức xác nhận** cho từng cạnh.
3. Đánh dấu cạnh sẽ đi qua hybrid VPN/ExpressRoute nếu chỉ một phần được chuyển.
4. Đề xuất thành phần phải cùng wave vì latency hoặc data consistency.

**Đầu ra:** dependency graph có chú thích và thứ tự wave đề xuất.

### Bài C — Chọn R và target

Xét bốn tình huống:

1. Portal nội bộ ít quan trọng, VM Linux hiện có tương thích.
2. CRM cũ không còn được hỗ trợ, có sản phẩm SaaS được business chấp nhận.
3. SQL Server với stored procedures và linked servers chưa được kiểm thử.
4. Hệ thống điều khiển nhà máy yêu cầu latency cực thấp và hoạt động offline.

Với mỗi tình huống, chọn **tối thiểu hai R có thể cân nhắc**, loại trừ lựa chọn vi phạm hard constraint và xác định kiểm thử cần làm trước khi chốt.

**Đầu ra:** ma trận quyết định có lý do, không chỉ một cột tên dịch vụ Azure.

### Bài D — Tính thời gian truyền và TCO

1. Tính thời gian tối thiểu chuyển 4 TiB trên liên kết danh nghĩa 200 Mbit/s.
2. Tính lại với 60% throughput hữu dụng.
3. So sánh TCO 36 tháng ở phần 13, nêu ít nhất ba giả định có thể đảo ngược kết luận.

**Kết quả tham khảo:** khoảng **48,9 giờ** lý tưởng; khoảng **81,5 giờ** ở 60% throughput; TCO minh họa **66.000 USD so với 63.600 USD**.

### Bài E — Thiết kế cutover/rollback

Chọn mục tiêu **downtime không quá 30 phút**, **không mất giao dịch đã xác nhận**.

1. Viết các bước backup/test restore, initial sync, cuối sync và chế độ dừng ghi.
2. Nêu quy tắc single writer, cách xác nhận dữ liệu và smoke test.
3. Xác định mốc cuối được phép rollback bằng cách đưa traffic về nguồn mà **không cần reverse sync**.
4. Sau khi đích đã nhận giao dịch mới, đề xuất xử lý roll forward hoặc reverse data path có kiểm chứng.
5. Ghi rõ ai đưa ra go/no-go và bằng chứng bắt buộc.

**Đầu ra:** runbook diễn tập cùng bảng acceptance criteria và risk register.

## 23. Những sai lầm thường gặp khi đánh giá migration

| Sai lầm | Tác động | Cách tránh |
| --- | --- | --- |
| Xem VM inventory là toàn bộ ứng dụng | Bỏ sót database, AD, batch, external API | Dựng workload model và graph |
| Chỉ khảo sát 24 giờ | Bỏ qua job cuối tháng và peak | Cửa sổ đủ chu kỳ và owner review |
| Lấy sizing từ CPU trung bình | VM/DB mới thiếu capacity | Dùng peak, percentiles và capacity test |
| Xem công cụ báo ready nghĩa là production ready | Không phát hiện lỗi nghiệp vụ | Compatibility + functional/integration tests |
| Chuyển web trước DB dù quá chatty | p95 tăng vì hybrid latency | Đo round trips, cân nhắc migration unit |
| Chọn PaaS vì rẻ mà không kiểm tra tính năng | SQL feature/runtime không hỗ trợ | PoC và feature matrix |
| Di chuyển hết máy nhưng quên identity/DNS | Login hoặc kết nối thất bại | AD/Entra/DNS architecture + tests |
| Nghĩ online migration = zero downtime | Cutover sai consistency | Quiesce writes, final sync, validation |
| Rollback chỉ là đổi DNS | Mất giao dịch đã ghi ở đích | Thiết kế reverse sync/roll forward trước |
| Chuyển dữ liệu production sang region chưa duyệt | Vi phạm chính sách | Data classification và approval |
| Không tính dual-run/egress | TCO đánh giá thấp | Tính one-time + operating + overlap |
| Mở firewall toàn bộ để chuyển nhanh | Tăng bề mặt tấn công | Least privilege và exception có hạn |
| Decommission ngay sau smoke test | Mất cơ hội phục hồi/không đáp ứng retention | Hypercare, sign-off, archive/deletion policy |
| Sao chép cấu hình cũ lên cloud rồi dừng | Giữ security debt và vận hành tốn kém | Modernization roadmap và post-migration review |

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao chỉ liệt kê VM chưa đủ để quyết định migration?  
**Đáp án:** Vì ứng dụng còn phụ thuộc dữ liệu, identity, network, file, middleware, batch, external integrations và các ràng buộc nghiệp vụ không thể suy ra từ VM list.

**Câu 2.** “Azure ready” trong công cụ assessment có đủ để xác nhận ứng dụng có thể go-live không?  
**Đáp án:** Không. Còn cần test compatibility, luồng nghiệp vụ, data integrity, SLO, bảo mật, network, DR và vận hành.

**Câu 3.** Khi nào nên chọn retain?  
**Đáp án:** Khi có giới hạn pháp lý, thiết bị, network latency hoặc dependency chưa thể chuyển, hoặc quyết định giữ lại được chứng minh có lợi; phải có kế hoạch quản trị hybrid.

**Câu 4.** Rehost khác replatform ở điểm nào?  
**Đáp án:** Rehost chuyển tương đối nguyên hiện trạng lên hạ tầng tương tự; replatform điều chỉnh để sử dụng nền tảng quản lý khác mà không bắt buộc viết lại kiến trúc toàn bộ.

**Câu 5.** Azure Arc có tự chuyển VM tại chỗ thành Azure VM không?  
**Đáp án:** Không. Arc dùng để quản lý/quản trị các tài nguyên ngoài Azure trong phạm vi hỗ trợ, không tự thực hiện migration.

**Câu 6.** Vì sao cần dependency graph trước khi chia migration waves?  
**Đáp án:** Nó cho biết dịch vụ nào phải có sẵn trước, những thành phần cần chuyển cùng lúc và các kết nối hybrid có nguy cơ tăng latency.

**Câu 7.** RTO và downtime window của migration có phải là một giá trị không?  
**Đáp án:** Không. RTO là mục tiêu khôi phục khi sự cố; downtime window là giới hạn gián đoạn kế hoạch trong cutover.

**Câu 8.** 4 TiB dữ liệu trên 200 Mbit/s cần tối thiểu khoảng bao lâu trong điều kiện lý tưởng?  
**Đáp án:** Khoảng 48,9 giờ, chưa tính overhead và dữ liệu thay đổi trong khi copy.

**Câu 9.** Sau cutover, Azure database đã nhận giao dịch mới. Có thể rollback bằng cách đổi DNS về database cũ ngay không?  
**Đáp án:** Không an toàn vì dữ liệu mới có thể không có ở nguồn cũ; cần reverse data plan/đối soát hoặc roll forward.

**Câu 10.** Vì sao chỉ số RPS đạt mục tiêu vẫn chưa chứng minh migration thành công?  
**Đáp án:** Có thể còn batch chưa test, restore không đạt, tính năng lỗi, quyền dữ liệu sai hoặc giao dịch bị mất/nhân đôi.

**Câu 11.** Vì sao mô hình TCO cần tính dual-run?  
**Đáp án:** Trong giai đoạn chuyển tiếp có thể phải trả cho cả nguồn và đích, kết nối, replication và nhân sự vận hành cả hai hệ thống.

**Câu 12.** Nên chọn migration wave chỉ dựa vào điểm ưu tiên cao nhất không?  
**Đáp án:** Không. Hard constraints và thứ tự dependency có thể buộc đổi wave; điểm là công cụ hỗ trợ quyết định chứ không tự động phê duyệt.

## 25. Checklist trước khi phê duyệt migration

- [ ] Đã xác định business objective, owner, downtime window và chỉ số thành công.
- [ ] Inventory có đủ server, app, database, file, identity, network, integration, batch và license.
- [ ] Mọi dữ liệu quan trọng có nguồn và mức độ tin cậy (verified/observed/declared/unknown).
- [ ] Dependency graph đã được owner xác nhận, có protocol, chiều truy cập và latency/throughput.
- [ ] Có baseline hiệu năng, peak capacity, lỗi, backup/restore, SLO, RTO/RPO và chi phí.
- [ ] Đã phân loại dữ liệu, đánh giá cư trú/tuân thủ, mã hóa, secret và audit.
- [ ] Đã kiểm tra compatibility theo target Azure, engine, OS, runtime, feature và licensing.
- [ ] Đã so sánh retain/retire/rehost/relocate/replatform/refactor/repurchase có lý do.
- [ ] Azure landing zone có subscription, policy, RBAC, network, DNS, monitoring, backup, quota và budget phù hợp.
- [ ] Migration waves phản ánh dependency, pilot đã được xác minh.
- [ ] Data migration có cách kiểm tra integrity và quy tắc single writer/cutover.
- [ ] Runbook có người phụ trách, go/no-go, rollback giới hạn và roll-forward plan khi có dữ liệu mới.
- [ ] Có kiểm thử chức năng, integration, performance, security, backup/DR và vận hành.
- [ ] TCO bao gồm phí Azure, license, nhân sự, transfer, dual-run và rủi ro chậm kế hoạch.
- [ ] Có hypercare, acceptance sign-off và điều kiện decommission nguồn cũ.
- [ ] Các blocker chưa giải quyết được báo rõ, không bị tự động coi là đạt.

**Kết luận:** Khảo sát và chọn chiến lược migration là một quá trình ra quyết định có chứng cứ. Một danh mục hạ tầng tốt cần đi kèm dependency graph, baseline, yêu cầu dữ liệu, kiểm tra tương thích, TCO và kịch bản cutover có thể diễn tập. Trên Microsoft Azure, lựa chọn phù hợp có thể là di chuyển, hiện đại hóa, mua sản phẩm mới, giữ hybrid hoặc loại bỏ hệ thống không còn giá trị. Chỉ khi **đúng workload, đúng chiến lược, đúng thứ tự và có tiêu chí nghiệm thu** thì migration mới tạo ra giá trị bền vững thay vì chỉ thay đổi nơi đặt máy chủ.
