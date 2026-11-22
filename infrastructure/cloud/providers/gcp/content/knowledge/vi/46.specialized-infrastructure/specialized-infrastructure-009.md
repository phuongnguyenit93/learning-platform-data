# SAP trên Google Cloud và yêu cầu hạ tầng doanh nghiệp

SAP là nền tảng vận hành các quy trình quan trọng như tài chính, mua hàng, bán hàng, chuỗi cung ứng, sản xuất và báo cáo quản trị. Khi triển khai SAP trên Google Cloud, một VM chạy được Linux hoặc một cơ sở dữ liệu khởi động thành công **chưa đủ** để chứng minh hệ thống đáp ứng yêu cầu doanh nghiệp. Cần kiểm tra chứng nhận của SAP, sizing, lưu trữ, độ sẵn sàng, an toàn dữ liệu, kết nối với hệ thống hiện hữu, giám sát, giấy phép và khả năng phục hồi.

Google Cloud cung cấp hạ tầng Compute Engine, VPC, lưu trữ khối, Cloud Storage, Cloud Load Balancing và các dịch vụ quản lý phục vụ hệ thống SAP. Hệ sinh thái SAP trên Google Cloud còn có công cụ hỗ trợ triển khai, thu thập metrics và đánh giá best practices. Tuy nhiên, **không phải mọi máy ảo, loại đĩa, phiên bản hệ điều hành hoặc kiến trúc đều được SAP chứng nhận**. Lựa chọn thực tế phải đối chiếu danh sách chứng nhận, SAP Notes, tài liệu Google Cloud và hợp đồng hỗ trợ của tổ chức tại thời điểm thiết kế.

Bài học này tập trung vào SAP S/4HANA, SAP HANA, SAP NetWeaver/ABAP và các hệ thống doanh nghiệp liên quan. Người học sẽ biết phân tích workload, thiết kế kiến trúc ba tầng, chọn hạ tầng được hỗ trợ, tổ chức HA/DR, backup, bảo mật, quản lý chi phí và lập kế hoạch chuyển đổi với mức độ kiểm soát tương xứng môi trường production.

## 1. Hiểu các thành phần SAP trong một landscape doanh nghiệp

Một SAP landscape điển hình có nhiều hệ thống và môi trường:

- **Development (DEV):** phát triển ABAP, thay đổi cấu hình và kiểm thử đơn vị.
- **Quality/Testing (QAS):** kiểm thử tích hợp, regression, hiệu năng và transports.
- **Pre-production (PRE-PROD):** kiểm chứng gần giống production khi cần.
- **Production (PRD):** xử lý giao dịch và dữ liệu nghiệp vụ.
- **DR environment:** phục hồi khi hạ tầng hoặc khu vực chính gặp sự cố.

Bên trong một hệ thống SAP, những thành phần thường xuất hiện:

| Thành phần | Vai trò | Lưu ý hạ tầng |
|---|---|---|
| SAP S/4HANA | Bộ ứng dụng ERP trên SAP HANA | Cần kiểm chứng cấu hình 2-tier/3-tier và chứng nhận |
| SAP HANA | Database in-memory, lưu trạng thái bền vững trên storage | Memory, CPU, storage I/O, HA/DR là các điểm then chốt |
| SAP NetWeaver/ABAP Application Server | Xử lý business logic, dialog, background jobs | Có thể triển khai nhiều application servers |
| ASCS/SCS | SAP Central Services, bao gồm enqueue/message services tương ứng | Thành phần quan trọng, thường cần HA |
| ERS | Enqueue Replication Server | Phối hợp với ASCS để bảo vệ enqueue state |
| SAP Web Dispatcher | Điều phối HTTP(S) tới application servers | Có thể cần thiết kế HA/load balancing |
| SAP HANA System Replication | Sao chép HANA tới một hệ thống thứ cấp | Cần lựa chọn chế độ replication và kiểm tra failover |
| SAP Host Agent và Google Cloud's Agent for SAP | Thu thập thông tin host/SAP và phục vụ hỗ trợ, monitoring | Cấu hình theo tài liệu và phiên bản được hỗ trợ |

Các hệ thống SAP BW/4HANA, SAP Business Suite/ECC, SAP Solution Manager hoặc các hệ thống SAP khác có yêu cầu khác nhau. **Không áp dụng một bảng sizing S/4HANA cho mọi SAP product.**

### Tách application tier và database tier

Kiến trúc **2-tier** đặt SAP application và database trên phạm vi tài nguyên gần nhau hoặc cùng host theo mô hình được chứng nhận. Kiến trúc **3-tier** tách application servers khỏi database server, thuận tiện hơn khi mở rộng và tổ chức HA.

Chọn kiến trúc phụ thuộc loại SAP solution, quy mô, yêu cầu hỗ trợ và chứng nhận. Không khẳng định 3-tier luôn tốt hơn nếu workload nhỏ hoặc sản phẩm có deployment guide khác.

## 2. Mô hình trách nhiệm giữa SAP, Google Cloud và doanh nghiệp

Doanh nghiệp vẫn cần vận hành các thành phần nằm trên VM và trong hệ thống SAP.

| Phạm vi | Trách nhiệm chủ yếu |
|---|---|
| Google Cloud infrastructure | Compute Engine, hạ tầng mạng/vùng, storage và dịch vụ Google Cloud theo SLA tương ứng |
| SAP software | Phần mềm, yêu cầu chứng nhận, SAP Notes và hỗ trợ phần mềm theo hợp đồng |
| Hệ điều hành và cluster software | Cấu hình, patch, agent, filesystem và HA cluster theo mô hình trách nhiệm |
| SAP Basis/DBA | SAP instances, HANA, transports, backup, performance tuning |
| Cloud platform/SRE | VPC/IAM, capacity, logging, cloud HA/DR, automation và cost |
| Security/compliance | Quyền, mã hóa, audit, retention, kiểm tra truy cập |
| Chủ nghiệp vụ | SLO, lịch đóng sổ, recovery objectives và chấp thuận downtime |
| Nhà cung cấp dịch vụ quản lý nếu có | Trách nhiệm được ghi rõ trong hợp đồng; không suy từ tên gói dịch vụ |

Với mô hình thương mại như RISE with SAP hoặc dịch vụ quản lý của đối tác, quyền quản trị hạ tầng và trách nhiệm vận hành có thể khác. Phải dùng hợp đồng và RACI chính thức trước khi thiết kế quyền IAM, backup và change workflow.

### Câu hỏi kiến trúc nền tảng

- Đây là migration nguyên trạng, chuyển đổi ECC sang S/4HANA hay triển khai mới?
- Khối lượng SAPS, memory HANA và đỉnh giao dịch lớn đến đâu?
- Môi trường nào cần HA và mức RPO/RTO nào?
- Hệ thống kết nối với nhà máy, ngân hàng, đối tác và on-prem ra sao?
- Có yêu cầu residency hoặc kiểm toán dữ liệu hay không?
- Giấy phép SAP, OS, HANA và các gói hỗ trợ đã phù hợp chưa?

## 3. Chứng nhận SAP là điều kiện tiên quyết

SAP công bố những phần cứng, hệ điều hành và phương án triển khai được chứng nhận/hỗ trợ. Trên Google Cloud, chỉ một tập con Compute Engine machine types và các cấu hình storage/OS được hỗ trợ cho từng SAP solution.

Không lựa chọn máy chỉ dựa trên giá/vCPU hoặc memory mà bỏ qua danh sách chứng nhận.

### Ma trận cần kiểm tra

| Hạng mục | Cần đối chiếu |
|---|---|
| SAP product | S/4HANA, BW/4HANA, NetWeaver, HANA hoặc database khác |
| Deployment model | Scale-up, scale-out, 2-tier/3-tier, HA hoặc DR |
| Machine type | Có chứng nhận với workload cụ thể hay không |
| CPU/memory | SAPS, số vCPU, memory và giới hạn cấu hình |
| Operating system | SLES for SAP, RHEL for SAP, Windows nếu solution hỗ trợ |
| Storage type | Loại Persistent Disk/Hyperdisk và layout được chứng nhận |
| Region/zone | Machine type và capacity có sẵn nơi triển khai hay không |
| SAP kernel/HANA revision | Có trong phạm vi hỗ trợ của SAP Notes hay không |
| Network | Băng thông, latency và cách triển khai VIP/HA được hỗ trợ |
| Licensing/support | Quyền sử dụng và đầu mối hỗ trợ tương ứng |

Google Cloud cung cấp trang tập hợp **SAP certifications** và **SAP HANA planning guide**; khi thiết kế phải đối chiếu thêm SAP Certified and Supported SAP HANA Hardware Directory và các SAP Notes có hiệu lực. Không dùng một cấu hình từng được chứng nhận nhiều năm trước mà chưa kiểm tra lại.

### Không suy ra chứng nhận từ họ máy

Một machine family có nhiều biến thể. Một biến thể có nhiều RAM không có nghĩa mọi cấu hình tùy chỉnh của họ đó đều được SAP HANA chứng nhận. Kể cả tùy chọn custom machine type, chỉ những tổ hợp được liệt kê là phù hợp mới được xem xét cho production.

## 4. Sizing: từ yêu cầu nghiệp vụ đến CPU, memory và I/O

Sizing SAP cần kết hợp dữ liệu thực của hệ thống hiện tại với phương pháp sizing được SAP công nhận, ví dụ SAP Quick Sizer hoặc báo cáo sizing phù hợp giải pháp.

### Những đầu vào quan trọng

- Số người dùng đồng thời và kiểu giao dịch.
- Khối lượng dialog steps hoặc business transactions.
- Batch jobs, MRP, kỳ đóng sổ và peak cuối tháng/quý.
- Khối lượng dữ liệu hiện có và tốc độ tăng trưởng.
- HANA memory footprint, column store, row store và working set.
- SAPS của application tier.
- Độ lớn transaction log, backup window và replication.
- Mục tiêu response time, throughput, RTO/RPO.
- Khả năng thay đổi workload sau migration hoặc transformation.

### Memory của HANA

HANA là hệ quản trị dữ liệu in-memory nên memory sizing là yếu tố quan trọng. Không cộng tổng kích thước database trên disk rồi cho rằng đó là RAM tối thiểu chính xác. Cần tính compression, working set, intermediate results, delta merge, headroom và khuyến nghị sizing cho workload cụ thể.

### CPU, SAPS và network

SAPS là đơn vị đo hiệu năng SAP theo benchmark/định nghĩa của SAP; không có quy đổi cố định "một vCPU bằng X SAPS" cho mọi generation CPU và machine type. Cần lấy thông tin từ chứng nhận và sizing tool.

Một HANA host có thể đủ CPU/memory nhưng thiếu băng thông mạng replication hoặc disk log write throughput. Vì vậy sizing phải đồng thời thỏa mãn compute, memory, storage và network.

### Mẫu sizing worksheet

| Workload | Peak metric | Yêu cầu | Kiểm tra |
|---|---|---|---|
| ABAP app | Đồng thời users/dialog steps | SAPS và app-server capacity | Load test giao dịch |
| HANA | Working memory + headroom | Certified host memory | HANA sizing và memory telemetry |
| Data volume | Dung lượng và IOPS | Certified block storage | Latency/read throughput |
| Log volume | Log write rate | Low latency sustained writes | Log backup và benchmark |
| Replication | Change rate | Network bandwidth/latency | HSR lag và failover |
| Backup | Data + log bytes | Backup throughput và bucket | Restore rehearsal |

Không ghi số CPU/memory cứng cho một SAP solution nếu chưa có workload assessment.

## 5. Kiến trúc SAP S/4HANA ba tầng tham chiếu

Một kiến trúc production có thể bố trí SAP application và database trên Compute Engine với phân tách subnet, IAM, HA và backup.

~~~mermaid
flowchart TD
    U[Business users and integration clients] --> W[Private or controlled access]
    W --> D[SAP Web Dispatcher or entry tier]
    D --> A1[ABAP app server zone A]
    D --> A2[ABAP app server zone B]
    A1 --> C[ASCS/ERS HA virtual endpoints]
    A2 --> C
    A1 --> H[HANA primary zone A]
    A2 --> H
    H --> S[HANA secondary zone B]
    H --> B[Backint backup to Cloud Storage]
    S --> B
    M[Cloud Monitoring and Workload Manager] -.-> A1
    M -.-> H
    N[Cloud VPN or Interconnect] --> W
~~~

Sơ đồ rút gọn cho mục tiêu học tập, không phải bản triển khai được chứng nhận. Các VIP, health checks, cluster resource groups, storage mounts và connectivity phải theo deployment guide của Google Cloud cho OS/SAP version đã chọn.

### Ranh giới các tier

- **Presentation/entry:** kết nối SAP GUI, HTTP(S), integrations và Web Dispatcher khi áp dụng.
- **Application:** primary/additional application servers, dialog/background workloads.
- **Central services:** ASCS/SCS, ERS và enqueue state.
- **Database:** SAP HANA, data/log storage, backup và replication.
- **Shared services:** DNS, time, directory/identity, monitoring, automation và secure connectivity.

### Vì sao cần tách?

Application servers có thể mở rộng ngang theo capacity và sự phụ thuộc vào database. Central services và database là stateful nên thiết kế HA khác stateless HTTP services.

## 6. Lựa chọn Compute Engine và capacity reservation

Machine type được chọn phải nằm trong chứng nhận SAP tương ứng; sau đó mới tối ưu region, zone, CPU generation và giá.

Kiểm tra:

1. Instance shape đủ vCPU/memory và được SAP chứng nhận.
2. Machine type sẵn có tại region/zone phù hợp.
3. Dung lượng và quota được phê duyệt.
4. Instance placement cho HA/anti-affinity theo hướng dẫn.
5. Tùy chọn sole-tenant hoặc bare-metal chỉ khi workload, chứng nhận và chính sách yêu cầu.
6. Kế hoạch reservation/capacity nếu hệ thống không được phép thiếu tài nguyên khi failover/rebuild.
7. Khả năng triển khai secondary/DR khi xảy ra sự cố khu vực.

### Capacity không đồng nghĩa quota

Có quota đủ lớn không đảm bảo mọi thời điểm đều còn capacity thực tế tại zone. Đối với hệ thống SAP production có yêu cầu phục hồi nghiêm ngặt, cần đánh giá cơ chế đảm bảo/đặt trước capacity và cấu hình DR để giảm nguy cơ thiếu máy khi sự cố.

### Không tự động thay đổi machine type production

Khuyến nghị FinOps rightsizing không tự có giá trị cho SAP HANA. Machine type mới phải được xác nhận hỗ trợ, downtime/HA phải được đánh giá và sizing phải chạy lại. Một VM nhỏ hơn có thể giảm chi phí nhưng phá điều kiện chứng nhận hoặc performance.

## 7. Thiết kế lưu trữ SAP HANA

SAP HANA sử dụng memory để xử lý nhưng vẫn cần lưu dữ liệu và transaction logs một cách bền vững. Các volume có chức năng và đặc điểm I/O khác nhau.

| Mount hoặc vùng dữ liệu | Mục đích | Yêu cầu |
|---|---|---|
| `/hana/data` | Persistence data của HANA | Dung lượng, throughput và latency đạt chuẩn SAP |
| `/hana/log` | Transaction log/persistence | Latency ghi thấp, ổn định, đủ throughput |
| `/hana/shared` | Các thành phần chia sẻ theo kiến trúc HANA | Shared filesystem hoặc cấu hình đúng deployment model |
| `/usr/sap` | SAP software và instance directories | Bảo vệ và quyền OS đúng |
| `/sapmnt` | File dùng chung cho SAP application khi cần | NFS/shared service theo hướng dẫn SAP |
| Backup staging hoặc `/hanabackup` | Backup tạm/đích backup khi dùng | Dung lượng phù hợp và cách dọn an toàn |

Không áp đặt cùng một kích thước hoặc loại đĩa cho data, log và shared. Thiết kế phải theo **certified block storage** và storage performance requirements của SAP solution.

### Persistent Disk, Hyperdisk và NFS

Google Cloud hỗ trợ nhiều loại block storage; những loại/shape được dùng cho SAP HANA phải theo trang certification và guide. Trong kiến trúc HANA scale-out, một số cấu hình yêu cầu NFS cho shared volumes, có thể dùng Filestore nếu đáp ứng tính năng và hiệu năng. Không tự thay block storage data/log bằng NFS tùy tiện.

### RAID và performance

Một số thiết kế kết hợp nhiều volume để đáp ứng yêu cầu throughput/IOPS. Lựa chọn filesystem, RAID, striping và mount options phải theo guide được chứng nhận. Đo storage latency thực, không chỉ nhìn băng thông danh nghĩa.

### Độ bền không đồng nghĩa backup

Zonal disk hoặc replicated storage không thay thế point-in-time recovery. Việc xóa nhầm bảng, corrupted data hoặc thay đổi ứng dụng sai có thể được sao chép sang secondary; vẫn cần backup và diễn tập khôi phục.

## 8. Scale-up và scale-out cho SAP HANA

**Scale-up:** tăng tài nguyên cho một HANA host. Phù hợp khi workload nằm trong giới hạn host được chứng nhận và kiến trúc đơn giản là ưu tiên.

**Scale-out:** phân phối một hệ thống HANA qua nhiều hosts theo kiến trúc được hỗ trợ. Có thể phục vụ workload lớn nhưng yêu cầu nghiêm ngặt hơn về storage, network, host roles và vận hành.

| Khía cạnh | Scale-up | Scale-out |
|---|---|---|
| Số host | Một host cho primary database (chưa tính HA secondary) | Nhiều master/worker/standby roles theo giải pháp |
| Sizing | Chọn máy certified đủ lớn | Sizing tổng thể và phân bố data |
| Network | Quan trọng cho client và replication | Đặc biệt quan trọng giữa HANA hosts |
| Shared filesystem | Theo deployment guide | Thường có yêu cầu shared storage rõ ràng |
| HA/DR | HSR + clustering theo thiết kế | Có host auto-failover và/hoặc replication theo phương án |
| Vận hành | Đơn giản hơn tương đối | Nhiều thành phần và kịch bản sự cố hơn |

Không chọn scale-out chỉ vì cần nhiều máy. Phải xem SAP application, database size, query patterns, hỗ trợ của product và yêu cầu mở rộng chính thức.

## 9. HA cho SAP HANA: System Replication và cluster

High availability (HA) nhằm giảm thời gian gián đoạn do một host hoặc zone gặp sự cố. Trên Google Cloud, một kiến trúc HANA scale-up HA thường gồm hai VM ở các zones thích hợp, SAP HANA System Replication (HSR), Pacemaker/OS HA cluster, health check và cơ chế chuyển VIP.

~~~mermaid
flowchart LR
    A[ABAP application servers] --> V[HANA virtual IP]
    V --> L[Internal passthrough Network Load Balancer]
    L --> P[Primary HANA in zone A]
    L -.-> S[Secondary HANA in zone B]
    P -->|HSR| S
    C[Pacemaker and fencing] --> P
    C --> S
    H[Health checks] --> L
~~~

Google Cloud hướng dẫn sử dụng **internal passthrough Network Load Balancer** làm cơ chế triển khai VIP/failover cho nhiều kiến trúc SAP HA được hỗ trợ. Không dùng floating IP kiểu gratuitous ARP của hệ thống on-prem như thể nó tương thích nguyên trạng với VPC.

### Các thành phần bắt buộc phải hiểu

- **HSR:** sao chép trạng thái database từ primary sang secondary, có chế độ và trade-off độ trễ cụ thể.
- **Pacemaker:** giám sát và phối hợp failover theo cluster resource configuration.
- **Fencing/STONITH:** ngăn hai node cùng nhận primary role trong tình huống split-brain.
- **VIP/Load balancer:** hướng ứng dụng tới database đang giữ primary role.
- **Health checks:** phải đại diện đúng vai trò active/healthy, tránh điều hướng sai.
- **Quorum và failure policies:** quyết định khi nào failover được phép.

### Rủi ro split-brain

Nếu hai HANA systems cùng nghĩ mình là primary và chấp nhận ghi độc lập, dữ liệu có thể không nhất quán. Do đó không tự viết script đổi DNS/VIP đơn giản thay cho cluster design chuẩn.

### Kiểm chứng failover

Trong staging hoặc bài diễn tập production được phê duyệt:

1. Xác nhận replication đang healthy, secondary theo kịp.
2. Ghi baseline request/transaction.
3. Mô phỏng lỗi node theo runbook được chứng nhận.
4. Theo dõi fencing, promotion và VIP routing.
5. Kiểm tra app reconnect, transaction correctness và SLO.
6. Đo RTO và độ trễ/bất kỳ dữ liệu chưa đồng bộ so với RPO.
7. Khôi phục replication topology và xác minh backup.

HA không đồng nghĩa zero downtime, cũng không mặc định RPO bằng không trong mọi chế độ và loại sự cố.

## 10. HA cho SAP NetWeaver: ASCS và ERS

Ở application tier, SAP Central Services quan trọng vì chứa enqueue/message services. Một kiến trúc HA cần ASCS/SCS cùng Enqueue Replication Server (ERS), theo mô hình SAP và OS hỗ trợ.

### Thành phần chính

| Thành phần | Chức năng |
|---|---|
| ASCS | SAP central services cho ABAP stack |
| ERS | Bảo vệ enqueue replication state |
| HA cluster software | Giám sát, khởi động/chuyển vai trò theo rule |
| Virtual endpoints/VIP | Địa chỉ ổn định cho ứng dụng |
| Internal load balancer | Hỗ trợ định tuyến active instance theo health check |
| Shared filesystem | Lưu các thành phần dùng chung theo deployment guide |

Trên Linux, RHEL/SLES với HA cluster stack được chứng nhận là lựa chọn thường gặp; với Windows-based SAP solution được hỗ trợ có thể dùng Windows Server Failover Clustering. Không áp template Linux lên Windows hoặc ngược lại.

### Tránh single point of failure

Có hai application servers nhưng ASCS duy nhất không có HA thì vẫn tồn tại single point of failure. Mặt khác, phân tán ASCS/ERS mà dùng DNS, NFS hoặc identity service không HA cũng chưa giải quyết hết rủi ro.

### Kế hoạch thử nghiệm

- Dừng có kiểm soát host ASCS active.
- Quan sát enqueue behavior và recovery.
- Kiểm tra transaction SAP thực, không chỉ ping VIP.
- Đối chiếu logs cluster, application và OS.
- Kiểm tra failback có cần chạy bằng tay hay theo quy trình được duyệt.

## 11. Thiết kế VPC, subnet và kết nối doanh nghiệp

SAP thường tích hợp với MES, WMS, ERP phụ trợ, Active Directory, hệ thống ngân hàng, đối tác EDI hoặc công cụ báo cáo nằm ngoài Google Cloud.

Các yêu cầu mạng:

- Subnet riêng cho application, database và management khi phù hợp.
- Private IP cho database và dịch vụ nội bộ.
- Kết nối Cloud VPN hoặc Cloud Interconnect theo băng thông/SLA.
- DNS và name resolution nhất quán giữa on-prem và GCP.
- Firewall allowlist theo nguồn, đích, port và traffic direction.
- Giám sát packet loss, jitter, latency và throughput.
- Kết nối Google APIs an toàn bằng Private Google Access hoặc cơ chế được hỗ trợ.
- Quy hoạch CIDR tránh overlap giữa VPC và data center.

~~~mermaid
flowchart TD
    O[On-prem SAP clients and integrations] --> H[Cloud VPN or Cloud Interconnect]
    H --> V[SAP VPC private subnets]
    V --> A[Application tier]
    A --> S[Central services]
    A --> D[HANA database tier]
    V --> M[Monitoring and secure management]
    B[Corporate DNS and identity] --> H
    D --> G[Approved Google APIs for backup and monitoring]
~~~

### Latency tác động trực tiếp đến SAP

Một thao tác SAP có nhiều round-trip giữa application tier và database. Đặt tier ở các khu vực cách xa nhau có thể làm response time tệ dù mỗi VM có CPU mạnh. Khi thiết kế HA cross-zone, cần đánh giá latency và replication network theo khuyến nghị SAP/Google Cloud.

### Khả dụng của đường private connectivity

Một đường VPN đơn lẻ có thể trở thành single point of failure. Cần thiết kế topology dự phòng phù hợp và test failover của DNS, routing và identity, không chỉ kết nối giữa hai VM.

## 12. DNS, NTP, OS và dịch vụ nền

SAP nhạy với hostname, service discovery, timezone và tính nhất quán thời gian.

Checklist:

- Hostnames/FQDN phù hợp SAP system ID (SID) và naming convention.
- DNS forward/reverse resolution đúng giữa application, HANA và ASCS/ERS.
- Đồng bộ thời gian trên OS và cluster bằng phương án được hỗ trợ.
- Kernel/OS packages, filesystem, swap/THP và tuning theo SAP Notes/Google guide.
- SAP-supported OS images và package repositories.
- Host firewall, TLS/certificates và credential management.
- Linux users/groups, ownership và mount options theo SAP requirements.
- System logs, agent services và access audit.

Không chạy một tập lệnh OS tuning tìm thấy trên Internet rồi áp cho mọi HANA revision. HANA, OS, machine generation và memory layout cần được đánh giá cùng nhau.

### Golden images

Có thể dùng image building pipeline để tạo base OS đã harden và kiểm thử. Tuy nhiên, clone một SAP instance có SID, host keys hoặc dữ liệu cố định đòi hỏi quy trình system copy/refresh đúng. Không đơn giản tạo VM image của production rồi dùng làm DEV mà không xử lý identity và dữ liệu nhạy cảm.

## 13. Backup SAP HANA bằng Backint và Cloud Storage

Backup là thành phần độc lập với HA. Trong SAP HANA, các bản sao cần bao gồm dữ liệu, transaction logs và catalog cần thiết để phục hồi theo mục tiêu.

**Google Cloud's Agent for SAP** có khả năng Backint, tích hợp với cơ chế backup/recovery của SAP HANA để đưa backup trực tiếp tới Cloud Storage theo cấu hình được hỗ trợ. Hỗ trợ chi tiết phụ thuộc phiên bản agent và SAP HANA.

### Thiết kế backup

| Thành phần | Nội dung cần quyết định |
|---|---|
| Data backup | Lịch và loại backup phù hợp HANA |
| Log backup | Tần suất và yêu cầu point-in-time recovery |
| Backup catalog | Quản lý trạng thái và metadata backup |
| Cloud Storage bucket | Location, storage class, IAM, retention |
| Encryption | Mã hóa khi truyền và lúc lưu, CMEK nếu yêu cầu |
| Access | Service account quyền tối thiểu, không dùng khóa tĩnh nếu tránh được |
| Retention | Lưu theo chính sách pháp lý/nghiệp vụ |
| Restore drill | Đo RTO, xác minh dữ liệu và catalog |
| HA topology | Tránh hai HANA nodes viết backup nhầm cùng vai trò |

Các backup thuộc application/sap process không tự động chạy chỉ vì bật tính năng Backint. Cần lên lịch backup qua cơ chế SAP phù hợp, kiểm tra logs và alert khi backup fail.

### Quyền và môi trường mạng

Agent cần quyền đọc/ghi object đúng bucket và kết nối tới Cloud Storage APIs. Với Compute Engine, nên sử dụng service account gắn với host hoặc phương án danh tính được hỗ trợ, tránh copy private key vào file cấu hình nếu không bắt buộc.

Nếu VM không có public IP, cấu hình Private Google Access hoặc đường truy cập Google APIs phù hợp. Không mở truy cập Internet rộng chỉ để Backint có thể ghi backup.

### Restore mới là tiêu chí thành công

Backup job báo success không chứng minh có thể restore khi:

- Backup log chain thiếu.
- Catalog không còn.
- CMEK key không truy cập được.
- Restore network không đủ throughput.
- Bucket location bị hạn chế trong sự cố vùng.
- Người phục hồi không có quyền hoặc sai SAP/HANA version.

Định kỳ phục hồi vào môi trường cách ly, so sánh dữ liệu và thời gian thực tế với RTO/RPO.

## 14. Snapshot, disk backup và data consistency

Snapshots của block storage có thể hữu ích trong một số mô hình backup/restore được SAP và Google Cloud hỗ trợ. Tuy nhiên, **snapshot hạ tầng không mặc định là SAP HANA application-consistent backup**.

Để dùng snapshot an toàn cần:

1. Kiểm tra HANA/agent/OS version và quy trình được chứng nhận.
2. Phối hợp database freeze/backup API hoặc workflow tương ứng.
3. Bảo vệ data/log consistency và backup catalog.
4. Lưu snapshot metadata, retention và encryption keys.
5. Thử restore và SAP integrity checks.
6. Xác định khả năng phục hồi tới thời điểm nào.

Không lấy snapshot của một disk bất kỳ rồi gọi đó là phương án DR hoàn chỉnh. Với DB HANA có nhiều volumes, tính nhất quán giữa các volumes phải được thiết kế và kiểm thử.

## 15. Disaster recovery giữa region

HA cùng region thường giảm tác động sự cố host/zone, nhưng không thay thế **cross-region DR**. DR nhằm phục hồi khi có mất mát nghiêm trọng ở một khu vực hoặc khi dữ liệu chính bị tổn hại.

### Mô hình tham khảo

~~~mermaid
flowchart TD
    A[Primary SAP region] --> H[HANA primary and local HA]
    H --> R[Cross-region HANA replication or approved DR mechanism]
    R --> S[DR HANA region B]
    H --> B[Backups with approved location policy]
    B --> S
    C[SAP app servers and ASCS in region A] --> D[Infrastructure templates and recovery procedures]
    D --> E[DR application tier in region B]
    S --> E
    E --> F[Controlled DNS routing and validation]
~~~

### RPO và RTO

- **RPO (Recovery Point Objective):** lượng dữ liệu có thể mất tối đa, tính theo thời gian.
- **RTO (Recovery Time Objective):** thời gian cho phép để khôi phục khả năng phục vụ.

Ví dụ giả định nghiệp vụ yêu cầu RPO 15 phút và RTO 2 giờ. Thiết kế phải chứng minh được các ngưỡng bằng bài diễn tập, không chỉ ghi chúng vào tài liệu.

### Những thứ DR cần

- HANA replication/backup phù hợp cơ chế được chứng nhận.
- Quản lý quyền truy cập và khóa mã hóa tại region DR.
- Capacity/quotas và machine types được hỗ trợ ở nơi phục hồi.
- Application/ASCS/ERS tier ở DR theo kịch bản.
- DNS, routes, load balancing và private connectivity.
- Quy trình mở/cắt integrations để tránh ghi dữ liệu trùng.
- Kế hoạch failback sau khi vùng chính được phục hồi.

**Replication có thể sao chép lỗi logic** như lệnh xóa dữ liệu; backup độc lập và retention vẫn cần thiết.

## 16. Mã hóa và IAM cho hệ thống SAP

Một SAP workload có thể chứa dữ liệu tài chính và cá nhân nhạy cảm. Bảo mật phải trải dài từ Google Cloud resource đến SAP application.

### IAM tối thiểu theo chức năng

| Principal | Quyền điển hình |
|---|---|
| Cloud platform admins | Tạo/sửa network, IAM và hạ tầng trong phạm vi được ủy quyền |
| SAP Basis operators | Vận hành SAP VM, logs và backup qua role cụ thể |
| Backup service identity | Ghi/đọc backup bucket theo quyền cần thiết |
| Monitoring identity | Đọc metrics và ghi telemetry theo chức năng |
| Deployment service account | Triển khai IaC, không dùng cho application runtime |
| Auditor | Đọc bằng chứng audit mà không có quyền thay đổi production |
| Break-glass operators | Quyền khẩn cấp được kiểm soát, ghi log và thu hồi |

Không cấp Owner hoặc Editor project cho mọi SAP administrator chỉ để thuận tiện.

### Bảo mật nhiều tầng

- VPC segmentation và firewall tối thiểu.
- VM không có public IP khi kiến trúc cho phép.
- OS Login/IAP hoặc bastion access theo chính sách.
- SSH key/certificate lifecycle và MFA/SSO phù hợp.
- SAP users/roles/authorizations và SNC/TLS cho giao tiếp tương ứng.
- HANA database users/roles và secrets được quản lý.
- Audit logs của Google Cloud, OS, HANA và SAP.
- Mã hóa lưu trữ, backups và network transit.
- Security Command Center/các công cụ đánh giá tuân thủ nếu phù hợp.

### CMEK và rotation

Nếu tổ chức yêu cầu CMEK, kiểm tra danh sách sản phẩm/tài nguyên hỗ trợ, vị trí key và khả năng truy cập sau phục hồi. Vô hiệu hóa key không đúng cách có thể làm ngừng VM/storage hoặc khiến backup không giải mã được. Quản trị key là một phần của DR.

## 17. Quan sát SAP bằng Agent for SAP và Workload Manager

Compute Engine Monitoring chỉ cho thấy một phần tình trạng VM. Với SAP, cần thêm dữ liệu OS, HANA, ứng dụng và HA cluster.

Google Cloud's Agent for SAP có các tính năng thu thập metrics và hỗ trợ Workload Manager đánh giá một số cấu hình theo best practices. Phạm vi được hỗ trợ phụ thuộc OS/agent version; ví dụ nhiều khả năng Workload Manager evaluation metrics và process monitoring tập trung trên Linux.

### Các lớp quan sát

| Lớp | Tín hiệu |
|---|---|
| Compute Engine | Availability, CPU, network, disk latency và VM events |
| OS | Memory, filesystem, disk queue, time sync, process health |
| SAP Host Agent | Host information phục vụ SAP monitoring/support |
| SAP HANA | Memory utilization, CPU, SQL/service health, log backup, replication lag |
| ASCS/ERS/Pacemaker | Cluster resources, VIP/health, failover events |
| ABAP application | Dialog response, work processes, dumps, background jobs |
| Network | VPN/Interconnect, firewall denies, latency, dropped packets |
| Backup/DR | Backup success, last recovery point, restore timing |
| Cost | Compute/storage/egress, CUD và usage theo SID/environment |

### Workload Manager

Workload Manager có thể đánh giá một số SAP configurations bằng dữ liệu từ agent và các best practices được hỗ trợ. Kết quả là tín hiệu để review, **không tự bảo đảm hệ thống được chứng nhận hoặc đạt SLO**.

### Thiết kế cảnh báo có ý nghĩa

Không chỉ cảnh báo CPU trên 80%. Cần cảnh báo theo hành vi:

- HANA replication mất đồng bộ hoặc secondary không healthy.
- Log backup thất bại liên tiếp.
- Data/log filesystem gần đầy.
- Database connection hoặc SQL latency bất thường.
- SAP application service ngừng phục vụ.
- ASCS/ERS failover bất ngờ.
- Network private connectivity gián đoạn.
- Job nghiệp vụ quan trọng bỏ lỡ lịch.
- RTO/RPO dự kiến không còn đạt.

Mỗi alert cần owner, mức độ ưu tiên và runbook.

## 18. Vận hành thay đổi và bảo trì

SAP production thường có lịch vận hành đặc thù như đóng sổ, inventory count hoặc chạy payroll. Maintenance cần phối hợp nhiều bên.

### Các loại thay đổi

- OS security patch.
- SAP kernel/support package update.
- SAP HANA revision upgrade.
- Machine type/disk resize.
- Pacemaker/HA configuration change.
- Network/firewall/VIP change.
- Backup agent và monitoring agent update.
- Transport hoặc application release.

### Change workflow

1. Định nghĩa mục tiêu, tác động và hệ thống liên quan.
2. Xác nhận compatibility/chứng nhận.
3. Tạo rollback plan và backup có thể phục hồi.
4. Thử trên QAS/PRE-PROD.
5. Chạy regression/performance test.
6. Đặt maintenance window tránh kỳ nghiệp vụ nhạy cảm.
7. Triển khai từng lớp theo runbook được duyệt.
8. Kiểm tra health, jobs, integration và dữ liệu.
9. Theo dõi sau change và đóng ticket.

Không tự động cài mọi phiên bản package mới ngay khi có OS update nếu chúng chưa được chứng nhận trong SAP landscape.

## 19. Automation và Infrastructure as Code

Terraform có thể khai báo project, VPC, subnets, firewall, service accounts, Compute Engine instances, disks, load balancers và bucket. Các phần cài SAP/HANA, cluster và DB settings phải theo playbook được hỗ trợ.

Một cấu trúc module tham khảo:

~~~text
sap-platform/
  environments/
    dev/
    qas/
    prod/
  modules/
    network/
    sap-compute/
    sap-storage/
    sap-ha-lb/
    sap-backup/
    observability/
  documentation/
    certified-build-matrix.md
    sizing-worksheet.md
    failover-runbook.md
~~~

Đây là cấu trúc repo minh họa, không phải các file được tạo trong nhiệm vụ này.

### Cấu hình Terraform minh họa

~~~hcl
variable "project_id" { type = string }
variable "zone" { type = string }
variable "certified_machine_type" { type = string }
variable "sap_subnetwork_self_link" { type = string }
variable "sap_service_account_email" { type = string }

resource "google_compute_instance" "sap_app" {
  name         = "sap-app-lab"
  project      = var.project_id
  zone         = var.zone
  machine_type = var.certified_machine_type

  boot_disk {
    initialize_params {
      image = "PROJECT/APPROVED-SAP-OS-IMAGE"
    }
  }

  network_interface {
    subnetwork = var.sap_subnetwork_self_link
  }

  service_account {
    email  = var.sap_service_account_email
    scopes = ["cloud-platform"]
  }

  labels = {
    workload    = "sap"
    environment = "lab"
  }
}
~~~

**Đoạn HCL không đủ để triển khai SAP production.** Giá trị machine type và image là placeholder, cần thay bằng tổ hợp được chứng nhận; phải bổ sung disks, reservations, HA, health checks, OS tuning, IAM, SAP installation và các kiểm soát khác. Không dùng một VM application lab làm mẫu HANA database chỉ bằng cách đổi nhãn.

### Guardrail trong pipeline

- Static checks, security policy và Terraform plan review.
- Kiểm tra machine type/region/OS theo danh sách certified đã được tổ chức cập nhật.
- Phê duyệt độc lập khi có disk destroy, machine replace hoặc downtime.
- State backend bảo vệ quyền và versioning phù hợp.
- Không chứa password, SAP licenses hoặc private keys trong Terraform state nếu tránh được.
- Kiểm thử DR/restore và HA cluster sau thay đổi lớn.

## 20. Chi phí và FinOps cho SAP

SAP enterprise infrastructure thường có memory lớn, storage hiệu năng cao và hệ thống dự phòng nên chi phí đáng kể. Giá VM không phải tổng chi phí sở hữu.

### Các khoản cần tính

| Khoản mục | Yếu tố ảnh hưởng |
|---|---|
| Compute | Certified machine types, CPU, RAM, HA nodes, reservations |
| Storage | Data/log, shared volumes, snapshots, backup buckets |
| Network | Cross-zone, cross-region, Interconnect/VPN và egress |
| Monitoring | Metrics, logs, traces, retention và Workload Manager hỗ trợ |
| Licenses | SAP, HANA, OS và phần mềm cluster theo hợp đồng |
| Support | Google Cloud, SAP và đối tác managed services |
| Operations | SAP Basis, DBA, patch, backup drills và on-call |
| DR | Secondary capacity, replication, backups, network |
| Migration | Tooling, testing, parallel run và cutover |

### Rightsizing không đơn giản

Với SAP HANA, VM được chứng nhận và memory headroom có thể làm chi phí cao nhưng cần thiết. Không giảm size chỉ dựa vào utilization trung bình nếu việc giảm phá chứng nhận hoặc SLO.

### Commitment và reservations

Có thể cân nhắc committed use discounts và capacity reservations khi phù hợp. Nhưng cần đối chiếu loại máy eligible, kỳ sử dụng, khả năng thay đổi cấu hình và kế hoạch migration. Chiết khấu tài chính không đồng nghĩa reservation capacity.

### KPI FinOps

- Chi phí theo SID, environment và business owner.
- Cost per SAP business transaction khi có dữ liệu.
- Tỷ lệ sử dụng memory/CPU trong cửa sổ đại diện.
- Storage growth và backup/restore cost.
- Idle DEV/QAS resources ngoài khung giờ đã phê duyệt.
- Chi phí DR trên mức RTO/RPO mà nghiệp vụ yêu cầu.

Đối với QAS/DEV, việc tắt VM theo lịch có thể tiết kiệm nhưng phải biết SAP/HANA shutdown/startup sequence và ảnh hưởng batch/integration. Không cắt điện VM theo lịch khi đang chạy job quan trọng.

## 21. Lập kế hoạch migration SAP lên Google Cloud

Migration SAP là dự án vừa hạ tầng vừa ứng dụng và dữ liệu, không chỉ di chuyển image VM.

### Giai đoạn assessment

- Inventory các SAP systems, SID, landscape và interfaces.
- Xác định version/supportability và những SAP Notes cần thiết.
- Sizing theo workload và database footprint.
- Map certified Compute Engine/OS/storage.
- Đo network dependency và latency hiện tại.
- Xác định RPO/RTO và downtime window.
- Phân tích giấy phép, bảo mật, compliance và vận hành.
- Chọn migration approach theo SAP guidance.

### Lựa chọn chiến lược

| Chiến lược | Ví dụ | Rủi ro |
|---|---|---|
| Homogeneous system copy | Cùng database/platform theo mô hình được hỗ trợ | Cutover, data consistency |
| HANA system replication | Migration hoặc DR theo HSR có khả năng hỗ trợ | Replication lag, switch-over |
| Backup/restore | Backup nguồn và restore trên GCP | Transfer time, backup integrity |
| Database Migration Option / SAP tools | Chuyển đổi database hoặc upgrade theo quy trình SAP | Compatibility, test effort |
| Rebuild/redeploy | Dựng hạ tầng mới và chuyển cấu hình/dữ liệu | Nhiều tích hợp và phụ thuộc |

Không áp một phương pháp cho mọi database/SAP release. Các công cụ SAP như Software Provisioning Manager hoặc SUM/DMO cần được dùng đúng version và scenario.

### Migration waves

1. Sandbox hoặc hệ thống ít quan trọng.
2. DEV/QAS landscape và integrations.
3. PRE-PROD rehearsal với dữ liệu đại diện.
4. Production cutover có phê duyệt.
5. Stabilization, monitoring và hypercare.
6. Decommission hệ thống cũ sau khi kết thúc rollback window.

## 22. Cutover và kiểm chứng nghiệp vụ

Một cutover plan phải có timeline, người chịu trách nhiệm và điều kiện dừng rõ ràng.

### Trước cutover

- Hoàn tất full backup và kiểm tra khả năng restore.
- Xác nhận HANA replication hoặc cơ chế data transfer.
- Kiểm tra firewall, DNS, routes, AD/SSO và integrations.
- Đo backlog của queues và trạng thái batch.
- Khóa hoặc hạn chế thay đổi cấu hình không cần thiết.
- Xác minh GCP quota, region capacity và IAM.
- Thử rollback về hệ thống nguồn nếu được phép.

### Trong cutover

1. Thông báo downtime/business freeze.
2. Dừng hoặc cô lập nguồn ghi theo quy trình.
3. Đồng bộ/restore dữ liệu và kiểm tra consistency.
4. Chuyển SAP application endpoints, DNS hoặc routing.
5. Mở ứng dụng theo thứ tự dependency.
6. Chạy smoke test và key business transactions.
7. Xác minh interfaces, batch jobs, printers và integrations.
8. Chấp thuận đưa users trở lại theo quyết định của business owner.

### Sau cutover

- So sánh tổng chứng từ/record ở các quy trình trọng yếu.
- Kiểm tra hàng đợi, transports, jobs, error logs.
- Theo dõi performance và database growth.
- Xác nhận backup mới chạy và restore path.
- Giữ rollback/forward-fix window theo kế hoạch.
- Không decommission nguồn cũ trước khi business sign-off.

## 23. Kiểm thử hiệu năng và độ tin cậy

Một bài load test SAP phải phản ánh nghiệp vụ thực, không chỉ ping HTTP endpoint của VM.

### Workload cần mô phỏng

- Dialog transactions có số user đồng thời đại diện.
- Background jobs vào giờ cao điểm.
- Mass data load, payroll hoặc closing process nếu trong phạm vi.
- SAP Fiori/UI và backend calls khi có.
- HANA SQL queries với dataset đủ lớn.
- Interactions với bên thứ ba và on-prem integration.
- Backup, delta merge, housekeeping đồng thời với workload.

### Metrics và tiêu chí

| Lớp | Chỉ số |
|---|---|
| SAP business | Thời gian hoàn thành giao dịch, tỷ lệ lỗi, job deadline |
| ABAP/application | Response time, work process availability, queue, dumps |
| HANA | Memory, expensive statements, CPU, log write, replication delay |
| Storage | Latency data/log và throughput |
| Network | RTT, loss, throughput và failover |
| HA | Time to detect, fence, promote và reconnect |
| DR | Actual RPO/RTO và business recovery validation |

Một hệ thống có CPU thấp vẫn có thể chậm vì disk log latency hoặc lock contention. Cần phân tích end-to-end.

### Controlled failure testing

Trong môi trường an toàn:

- Simulate application VM stop để xem load balancing.
- Failover ASCS/ERS theo runbook.
- Kiểm tra HANA HSR switchover.
- Mất một đường VPN/Interconnect.
- Restore database từ backup vào môi trường cách ly.

Mọi thử nghiệm cần rollback/stop condition và owner đồng ý. Không chạy destructive chaos test trong kỳ chốt sổ production.

## 24. Vận hành SAP với SLO và quy trình sự cố

Một hệ thống SAP quan trọng cần chỉ tiêu dễ hiểu với business owner:

- Availability của các giao dịch cốt lõi.
- Response time theo nhóm giao dịch.
- Success rate của background jobs.
- HANA replication health.
- Backup success và khả năng restore.
- Data freshness của các báo cáo tích hợp.
- RTO/RPO được diễn tập.

Ví dụ SLO minh họa:

> Trong giờ nghiệp vụ, tối thiểu 99,9% giao dịch tạo đơn thuộc luồng chuẩn hoàn tất thành công; p95 phản hồi dưới ngưỡng do business phê duyệt; backup logs không vượt quá giới hạn lỗi liên tiếp đã định.

Các con số chỉ là ví dụ, không phải SAP SLA mặc định. SLA của Compute Engine/storage hay network không bằng availability end-to-end của SAP.

### Incident runbook

Một runbook tốt ghi:

1. Cách xác nhận incident và xác định tầng lỗi.
2. Hướng liên hệ SAP Basis, DBA, cloud SRE và network.
3. Cluster/VIP/replication state cần đọc.
4. Những hành động được phép và bị cấm.
5. Quy trình escalation tới SAP, Google Cloud hoặc OS vendor.
6. Điều kiện failover/failback.
7. Bảo toàn logs và audit evidence.
8. Business validation sau phục hồi.

## 25. Tình huống thực hành: thiết kế SAP S/4HANA production

Giả sử doanh nghiệp sản xuất có:

- S/4HANA production phục vụ tài chính, mua hàng và kho.
- Dự báo tăng dữ liệu theo kế hoạch ba năm.
- Kỳ đóng sổ cuối tháng có tải cao.
- ERP kết nối nhà máy qua private network.
- Yêu cầu HA giữa hai zones và DR ở region khác.
- QAS cần đủ giống production để kiểm thử transports.

### Bước 1 — Xác minh đầu vào

Thu SAPS, HANA memory sizing, peak transaction, database growth, data retention, RPO/RTO, integration map và licensing. Xác định các thành phần cần được SAP chứng nhận.

### Bước 2 — Lựa chọn kiến trúc

- Application servers trên Compute Engine certified configuration.
- ASCS/ERS HA theo mô hình OS/SAP được hỗ trợ.
- HANA scale-up primary/secondary với HSR/Pacemaker, nếu sizing phù hợp.
- Shared filesystem và data/log volumes đúng certification.
- Internal passthrough load balancing cho VIP khi guide yêu cầu.
- Kết nối Cloud Interconnect/VPN dự phòng tới nhà máy.

Không quyết định chính xác machine type hoặc disk size khi chưa có kết quả sizing.

### Bước 3 — Thiết kế bảo vệ dữ liệu

- Backint backup data/log/catalog vào bucket có quyền tối thiểu.
- Lịch backup đáp ứng RPO và retention.
- Thử restore vào QAS/restore lab.
- HANA DR path qua replication và/hoặc backup ngoài region theo yêu cầu.
- Kế hoạch giữ khóa mã hóa và DNS khi khu vực chính gặp lỗi.

### Bước 4 — Bảo mật và vận hành

- Tách service accounts triển khai, runtime agent, monitoring và backup.
- Dùng private connectivity, firewall least privilege.
- SAP Basis và cloud SRE có runbook chung.
- Workload Manager/Agent for SAP và Cloud Monitoring giám sát được cấu hình.
- Quy trình patch có QAS test và approval.

### Bước 5 — Test acceptance

| Kiểm tra | Tiêu chí |
|---|---|
| Certification | Máy/OS/storage/SAP version được hỗ trợ |
| Functional | Giao dịch tài chính và mua hàng đúng |
| Performance | Peak cuối tháng đạt mục tiêu đã duyệt |
| HA | Failover HANA và ASCS/ERS đáp ứng SLO |
| Backup | Restore từ Cloud Storage thành công |
| DR | Diễn tập cross-region đáp ứng RPO/RTO |
| Security | IAM, SAP roles, audit và encryption đạt chuẩn |
| Cost | Chi phí và capacity nằm trong forecast |

### Bước 6 — Go-live

Chuẩn bị cutover checklist và rollback decision point, theo dõi stability trong hypercare, so sánh performance với baseline và bàn giao vận hành chính thức. Chỉ đóng dự án khi business owners xác nhận kết quả.

## 26. Những sai lầm thiết kế cần tránh

| Sai lầm | Hậu quả | Giải pháp |
|---|---|---|
| Chọn VM chỉ theo RAM rẻ nhất | Có thể không được SAP chứng nhận | Kiểm tra machine type và SAP Notes |
| Sizing HANA bằng disk capacity | Memory/CPU không đáp ứng thực tế | SAP sizing và telemetry |
| Dùng storage không theo certified layout | Log latency và support risk | Tuân thủ SAP HANA planning guide |
| Coi zonal disk là backup | Mất dữ liệu do xóa nhầm hoặc corruption | HANA Backint và restore drill |
| Có HSR nhưng không có fencing | Split-brain và lỗi dữ liệu | Pacemaker/fencing đúng hướng dẫn |
| VIP dùng gratuitous ARP như on-prem | Failover routing không hoạt động | Cơ chế VIP được Google Cloud hỗ trợ |
| HA nhưng không có DR | Không chịu được sự cố region | Cross-region recovery plan |
| Không giữ capacity cho DR | Không có máy khi cần phục hồi | Capacity planning/reservation |
| Public IP và quyền Owner cho mọi SAP VM | Tăng attack surface | Private network và IAM tối thiểu |
| Chỉ đo CPU của VM | Không thấy lỗi SAP/HANA | Agent, app/DB metrics và SLO |
| Patch tự động không kiểm tra SAP version | Không tương thích/khó support | Certification checks, QAS và change control |
| Dùng snapshot chưa kiểm tra nhất quán HANA | Restore có thể lỗi | HANA-aware backup/recovery workflow |
| Không tính license/support | TCO và quyền hỗ trợ sai | RACI, licensing và hợp đồng |
| Cutover không có business validation | SAP khởi động nhưng nghiệp vụ sai | Functional reconciliation và sign-off |

## 27. Checklist production readiness

### Kiến trúc và chứng nhận

- [ ] SAP solution và landscape DEV/QAS/PRD/DR đã được định nghĩa.
- [ ] Machine type, OS, storage và versions có chứng nhận/hỗ trợ.
- [ ] Sizing SAPS, HANA memory, IOPS, throughput và network đã được xác minh.
- [ ] Region, zones, capacity và quotas đủ cho failure/recovery scenarios.
- [ ] SAP vendor/Google Cloud/đối tác có RACI và support path rõ ràng.

### Network và bảo mật

- [ ] Private connectivity và DNS/time sync đáp ứng yêu cầu.
- [ ] Firewall/service identities được cấp quyền tối thiểu.
- [ ] SAP authorization, HANA roles và admin access được kiểm soát.
- [ ] Logging, audit, backup encryption và CMEK nếu cần có runbook.
- [ ] Không đưa password hoặc keys vào source code/terraform state không cần thiết.

### HA và dữ liệu

- [ ] HANA HSR, cluster, fencing, VIP và health checks đã được thử.
- [ ] ASCS/ERS HA được kiểm chứng theo SAP guide.
- [ ] Data/log mounts đạt yêu cầu và có telemetry.
- [ ] Data/log/catalog backups được lập lịch và kiểm tra lỗi.
- [ ] Restore và DR drill đáp ứng RTO/RPO thực tế.

### Vận hành và chi phí

- [ ] SAP Host Agent/Google Cloud's Agent for SAP được cấu hình theo supported version.
- [ ] Có dashboards SAP/HANA/OS/VM/network và alerts nghiệp vụ.
- [ ] Quy trình incident/patch/change có owner, escalation và rollback.
- [ ] Dev/QAS/PRD được tách theo IAM và dữ liệu.
- [ ] Chi phí compute, storage, licenses, support và DR đã được dự toán.
- [ ] Có hypercare và business sign-off khi go-live.

## 28. Tài liệu chính thức cần đối chiếu

Những tài liệu quan trọng (nội dung và danh sách certification có thể thay đổi):

- [Overview of SAP on Google Cloud](https://docs.cloud.google.com/sap/docs/overview-of-sap-on-google-cloud)
- [SAP certifications for Google Cloud](https://docs.cloud.google.com/sap/docs/sap-certifications)
- [SAP HANA planning guide](https://docs.cloud.google.com/sap/docs/sap-hana-planning-guide)
- [SAP HANA high-availability planning guide](https://docs.cloud.google.com/sap/docs/sap-hana-ha-planning-guide)
- [SAP NetWeaver HA planning guide](https://docs.cloud.google.com/sap/docs/netweaver-ha-planning-guide)
- [Google Cloud's Agent for SAP](https://docs.cloud.google.com/sap/docs/agent-for-sap/latest)
- [Backup and recovery with Backint](https://docs.cloud.google.com/sap/docs/agent-for-sap/latest/backint-backup-recovery)
- [Workload Manager for SAP workloads](https://docs.cloud.google.com/workload-manager/docs/evaluate/set-up-agent-for-sap)

Cần đối chiếu thêm **SAP Notes** và **SAP Certified and Supported SAP HANA Hardware Directory** tương ứng với phiên bản ứng dụng, HANA, OS và phần cứng. Không dùng ví dụ minh họa trong bài thay cho deployment guide được chứng nhận.

**Kết luận:** Thiết kế SAP trên Google Cloud là bài toán phối hợp phần mềm SAP với hạ tầng Compute Engine, storage, VPC, bảo mật và vận hành doanh nghiệp. Một kiến trúc tốt phải bắt đầu từ workload sizing và certification, sau đó bảo vệ dữ liệu bằng HANA-aware backups, tổ chức HA/DR có fencing/failover được kiểm thử, giám sát đến tầng nghiệp vụ và quản lý thay đổi theo quy trình được phê duyệt. Khi mọi lớp được kiểm chứng bằng thử nghiệm thực tế, doanh nghiệp mới có cơ sở vận hành SAP tin cậy và tối ưu chi phí trên Google Cloud.

