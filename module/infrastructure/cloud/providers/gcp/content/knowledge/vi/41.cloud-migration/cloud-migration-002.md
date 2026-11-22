# Migration Center và đánh giá khả năng di chuyển

Di chuyển lên Google Cloud bắt đầu trước khi tạo VM, database hoặc Kubernetes cluster. Tổ chức cần biết **đang sở hữu những tài sản nào, chúng phụ thuộc nhau ra sao, tải thực tế thế nào, ứng dụng nào dễ chuyển, rủi ro ở đâu và chi phí sau di chuyển có hợp lý không**. Nếu bỏ qua bước khảo sát, nhóm có thể chọn sai kích thước Compute Engine, thiếu port kết nối giữa các ứng dụng, quên dịch vụ chạy ngầm hoặc chuyển database trước khi các hệ thống phụ thuộc sẵn sàng.

**Google Cloud Migration Center** hỗ trợ giai đoạn khám phá và đánh giá hạ tầng: thu thập thông tin server, VM, database; tổ chức asset inventory; lập nhóm tài sản; xây dựng các kịch bản đích và tạo báo cáo tổng chi phí sở hữu (Total Cost of Ownership – TCO). Công cụ **Migration Center discovery client** và **mcdc CLI** phục vụ thu thập dữ liệu; một số phương thức còn tạo báo cáo đánh giá offline. Kết quả là dữ liệu đầu vào cho quyết định kiến trúc và kế hoạch migration, chưa phải một lệnh tự động chuyển toàn bộ workload lên GCP.

Bài học hướng dẫn từ khảo sát ban đầu đến lập danh sách ứng dụng theo đợt di chuyển. Ví dụ tập trung vào hệ thống doanh nghiệp đang chạy VM, ứng dụng Java và database ở trung tâm dữ liệu riêng, sau đó cân nhắc Compute Engine, Cloud SQL, Cloud Run và GKE.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích mục đích và giới hạn của Migration Center trong hành trình cloud migration.
- Chọn phương pháp discovery: liên tục, quét một lần, guest discovery hoặc import dữ liệu thủ công.
- Hiểu các loại dữ liệu được thu thập, cách đọc asset inventory và những khoảng trống cần bổ sung.
- Chạy quy trình minh họa với mcdc CLI để khám phá và tạo báo cáo offline.
- Tổ chức asset group, lựa chọn migration preferences và đọc báo cáo TCO.
- Đánh giá readiness theo các trục kỹ thuật, nghiệp vụ, bảo mật, vận hành và chi phí.
- Phân biệt khả năng chuyển VM với khả năng hiện đại hóa ứng dụng Java.
- Xây dựng migration waves có dependency, mục tiêu kiểm chứng và phương án rollback.
- Nhận biết rủi ro về dữ liệu thu thập, quyền truy cập, tính chính xác của ước tính và chi phí thực tế.

## 1. Migration Center nằm ở giai đoạn nào?

Một chương trình cloud migration thường gồm các giai đoạn:

~~~text
Khởi động chương trình
        |
        v
Discovery / Inventory
        |
        v
Assessment / TCO / Readiness
        |
        v
Thiết kế landing zone và target architecture
        |
        v
Lập migration waves và pilot
        |
        v
Migration / Validation / Cutover
        |
        v
Operate / Optimize
~~~

Migration Center hỗ trợ chủ yếu **discovery** và **assessment**. Các bước thực thi migration sử dụng công cụ và quy trình tương ứng, ví dụ Migrate to Virtual Machines cho một số trường hợp chuyển VM, Database Migration Service cho cơ sở dữ liệu được hỗ trợ, hoặc pipeline CI/CD để triển khai lại ứng dụng Java.

### Migration Center cung cấp gì?

| Khả năng | Câu hỏi cần trả lời | Đầu ra |
|---|---|---|
| Discovery | Có những server, VM, database và phần mềm nào? | Danh sách asset và thông số được thu thập |
| Inventory | Có bao nhiêu tài sản, cấu hình và vị trí nào? | Asset inventory, metadata và thống kê |
| Dependency insight | Tài sản nào liên lạc và phụ thuộc lẫn nhau? | Thông tin hỗ trợ lập nhóm và đánh giá |
| Grouping | Những thành phần nào thuộc cùng ứng dụng hoặc phạm vi chuyển đổi? | Nhóm server/database |
| Migration preferences | Nếu chạy ở vùng/loại máy/chiến lược sizing khác nhau thì sao? | Các giả định cho mỗi kịch bản |
| TCO reports | Chi phí hạ tầng mục tiêu có thể là bao nhiêu? | Ước tính và so sánh theo nhóm/tài sản |
| Offline assessment | Workload có phù hợp với một số đích chuyển đổi không? | Fit assessment, findings và blockers theo các quy tắc của công cụ |

Những đầu ra này là một phần của **migration assessment**. Chúng không tự thay thế phỏng vấn application owner, kiểm thử tương thích, phân tích compliance hay quyết định kiến trúc.

### Phân biệt với công cụ migration

| Nhu cầu | Loại công cụ/quy trình |
|---|---|
| Khám phá server và ước tính chi phí | Migration Center |
| Đánh giá offline và phát hiện blockers | mcdc CLI và bộ quy tắc assessment được hỗ trợ |
| Chuyển máy ảo sang GCP | Công cụ migration VM phù hợp nguồn và đích |
| Di chuyển dữ liệu database | Database Migration Service hoặc quy trình database migration |
| Chuyển Java app sang container | Refactor, containerization, CI/CD, Cloud Run/GKE |
| Thiết kế mạng/IAM/tổ chức project | Landing zone, networking, IAM và IaC |
| Đo kết quả sau cutover | Cloud Monitoring, Logging, SLO và kiểm thử ứng dụng |

Một VM được đánh giá có thể chạy trên Compute Engine chưa chứng minh ứng dụng trong VM có thể tách thành microservice hoặc chạy ngay trên Cloud Run.

## 2. Bắt đầu từ câu hỏi nghiệp vụ và phạm vi

Không nên quét toàn bộ hạ tầng trước khi biết dùng kết quả để ra quyết định gì.

Ví dụ mục tiêu của doanh nghiệp:

- Rời trung tâm dữ liệu trước khi hợp đồng thuê hết hạn.
- Giảm chi phí vận hành VM và license.
- Tăng khả năng khôi phục sau thảm họa.
- Hiện đại hóa một số dịch vụ Java/Spring thành container.
- Hợp nhất database và dùng dịch vụ quản lý như Cloud SQL.
- Giảm rủi ro vận hành phần cứng, tăng tự động hóa phát hành.
- Đáp ứng yêu cầu lưu trú dữ liệu, bảo mật và audit.

### Các câu hỏi đầu vào

1. Hệ thống nào thuộc phạm vi chuyển đổi?
2. Hạn chót theo hợp đồng, dự án hoặc nghĩa vụ tuân thủ là gì?
3. Mức downtime tối đa chấp nhận được là bao nhiêu?
4. Dữ liệu nào có yêu cầu residency, encryption hoặc kiểm soát truy cập riêng?
5. Application owner và technical owner là ai?
6. Có thể thay đổi kiến trúc hay chỉ được chuyển nguyên trạng?
7. Ngân sách, giới hạn license và năng lực đội ngũ cloud thế nào?
8. Thành công được đo bằng SLO, RTO/RPO, chi phí hay thời gian release?

### Định nghĩa phạm vi

| Thuộc tính | Ví dụ |
|---|---|
| Business unit | Commerce |
| Source environment | VMware vSphere tại datacenter A |
| Số lượng dự kiến | Khoảng 120 VM và 15 database |
| Ứng dụng ưu tiên | Checkout, catalogue, order processing |
| Out of scope | Hệ thống OT và thiết bị mạng chuyên dụng |
| Deadline | Theo kế hoạch dự án đã phê duyệt |
| Target regions | Chọn sau đánh giá latency, compliance và dịch vụ hỗ trợ |
| Người phê duyệt | Application owner, platform, security và tài chính |

Con số chỉ minh họa. Khi khai báo phạm vi, ghi rõ tài sản nào chưa được scan và nguyên nhân, ví dụ do firewall, thiếu credential hoặc hệ điều hành không được công cụ hỗ trợ.

## 3. Discovery và assessment khác nhau thế nào?

**Discovery** thu thập dữ liệu thực tế: tài sản, hệ điều hành, CPU/RAM, disk, network, quá trình đang chạy, cấu hình database và mức sử dụng theo thời gian, tùy phương thức.

**Assessment** dùng dữ liệu đó cùng các giả định để đề xuất đích chuyển đổi, nhận diện rủi ro và so sánh kịch bản. Không có đủ dữ liệu discovery, kết quả assessment phải dùng ước tính mặc định và có độ chắc chắn thấp hơn.

~~~text
Nguồn hạ tầng
  VMware / server vật lý / AWS / Azure / database
             |
             v
      Discovery methods
             |
             v
     Dữ liệu cấu hình + hiệu năng
             |
             v
    Chuẩn hóa inventory + asset groups
             |
             v
Migration preferences + constraints
             |
             v
    Assessment / TCO / Fit / Risks
             |
             v
  Decision register + migration waves
~~~

Một inventory có 150 VM nhưng không có dependency và performance data có thể đủ cho báo cáo sơ bộ; nó chưa đủ để cam kết lịch cutover chi tiết hoặc sizing tối ưu.

## 4. Chọn phương pháp thu thập dữ liệu

Migration Center hỗ trợ nhiều phương pháp để cân bằng tốc độ, chiều sâu và yêu cầu bảo mật.

| Phương pháp | Đặc điểm | Khi nên chọn |
|---|---|---|
| mcdc CLI – one-time discovery | Quét một lần hoặc theo đợt; có thể chạy offline và xuất dữ liệu sau | Pilot, môi trường nhỏ, chưa cho phép agent chạy dài hạn |
| Discovery client – continuous collection | Cài discovery client, thu thập theo lịch và tích lũy dữ liệu theo thời gian | Hệ thống lớn, tải theo chu kỳ, cần mẫu hiệu năng đại diện |
| Guest discovery | Thu thập từ trong OS: process, service, network và một số database | Cần hiểu workload bên trong VM/physical server |
| Inventory discovery | Lấy dữ liệu VM/asset từ hypervisor hoặc cloud API | Muốn lập danh sách nhanh trên nền tảng hỗ trợ |
| IP range scan | Dò dải IP và thu thập theo guest discovery khi có quyền | Thiếu CMDB đầy đủ hoặc chưa rõ máy nào tồn tại |
| Manual import | Upload template hoặc dữ liệu từ nguồn được hỗ trợ như RVTools | Không thể dùng collector hoặc có báo cáo hiện hữu |

### Quét một lần và thu thập liên tục

Quét một lần phù hợp để bắt đầu nhanh, nhưng có thể bỏ lỡ peak traffic, batch cuối tháng hoặc backup window. Thu thập liên tục qua nhiều ngày/tuần giúp phản ánh tải thực tế hơn.

Không có một số ngày khảo sát cố định cho mọi hệ thống. Với ứng dụng có chu kỳ tháng hoặc quý, hãy bổ sung dữ liệu từ monitoring hiện hữu nếu thời gian discovery không bao phủ được đỉnh tải.

### Chọn công cụ theo nguồn

- **VMware vSphere:** mcdc có thể lấy inventory qua vSphere API; guest discovery bổ sung chi tiết hệ điều hành và ứng dụng.
- **Server Linux/Windows:** guest discovery có thể dùng SSH, WMI hoặc script chạy tại máy tùy khả năng kết nối.
- **AWS:** mcdc hỗ trợ một số asset inventory như EC2 và RDS theo phạm vi công cụ.
- **Azure:** một số tính năng inventory discovery còn ở trạng thái Preview; cần kiểm tra hỗ trợ trước khi lên kế hoạch.
- **Database:** có các phương pháp cho Microsoft SQL Server, MySQL và PostgreSQL theo tài liệu.
- **Môi trường hạn chế kết nối:** chạy offline assessment trước hoặc dùng cơ chế xuất dữ liệu có kiểm soát.

Không suy luận mọi loại asset của AWS/Azure hoặc mọi database engine đều được hỗ trợ với cùng độ chi tiết.

## 5. Dữ liệu discovery nào quan trọng?

Nhóm assessment cần đủ thông tin để trả lời ba câu hỏi: **nó là gì, nó chịu tải thế nào và ai phụ thuộc vào nó?**

### Cấu hình cơ bản

| Dữ liệu | Giá trị cho assessment |
|---|---|
| Asset ID/hostname | Nhận diện, loại trùng và đối chiếu CMDB |
| OS và phiên bản | Kiểm tra support/lifecycle và target compatibility |
| CPU architecture/vCPU | Đề xuất machine family và khả năng chuyển đổi |
| RAM | Chọn cấu hình bộ nhớ |
| Disk, filesystem, IOPS | Thiết kế storage và ước tính chi phí |
| IP, network interface, port | Lập kế hoạch VPC, firewall và kết nối |
| Hypervisor/cloud origin | Chọn migration method phù hợp |
| Processes/services | Phát hiện dependency ứng dụng và runtime |
| Database engine/version | Xem khả năng chuyển sang managed database |
| Uptime/maintenance | Xác định cửa sổ di chuyển và rủi ro gián đoạn |

### Hiệu năng theo thời gian

- CPU utilization: trung bình, đỉnh, percentile.
- Memory utilization và memory pressure.
- Disk capacity, disk throughput/IOPS và tốc độ tăng dữ liệu.
- Network throughput, network connections và giao tiếp giữa máy.
- Quy luật traffic theo giờ/ngày/tháng.
- Tình trạng batch job, scheduler, queue và peak load.

Đặc biệt với sizing, không nên chỉ dựa vào vCPU/RAM đã cấp. VM có 16 vCPU nhưng sử dụng 10% CPU phần lớn thời gian có thể được đề xuất máy nhỏ hơn, nhưng cần xem peak, license, tải bất thường và yêu cầu dự phòng trước khi quyết định.

### Ownership và bối cảnh nghiệp vụ

Phần lớn inventory kỹ thuật không tự cho biết:

- Ứng dụng thuộc sản phẩm nào?
- Ai là người phê duyệt downtime?
- Dữ liệu có nhạy cảm hoặc bị ràng buộc theo quy định nào?
- Có tích hợp với hệ thống ngoài phạm vi không?
- License có cho phép chạy trong public cloud không?
- Hệ thống có hoạt động theo tháng/quý hoặc kỳ quyết toán không?

Cần bổ sung các trường này từ CMDB, owner interview và hồ sơ kiến trúc. Đây là công việc phân tích con người, không nên coi là thông tin được Migration Center xác minh tự động.

## 6. Chuẩn bị project và kích hoạt Migration Center

Trước khi upload discovery data, cần có một Google Cloud project dành cho assessment và quyền IAM phù hợp.

Quy trình trên Google Cloud Console:

1. Chọn hoặc tạo project dành cho migration assessment.
2. Mở Migration Center.
3. Nếu được yêu cầu, bật các API cần thiết.
4. Chọn region để lưu và xử lý dữ liệu của Migration Center.
5. Xác nhận migration preferences mặc định hoặc tiếp tục để chỉnh sau.
6. Hoàn thành kích hoạt và phân quyền cho người thực hiện assessment.

**Region của Migration Center được chọn lúc kích hoạt và không thể đổi trực tiếp sau đó.** Kiểm tra residency, governance và giới hạn region trước khi chốt.

### Vai trò và phân quyền

Người thực hiện discovery không nhất thiết phải có quyền quản trị toàn bộ project GCP. Nên tách vai trò:

- Người quản trị Migration Center và API.
- Collector operator có quyền truy cập vào nguồn VMware/OS/database.
- Analyst xem inventory và chạy báo cáo.
- Security reviewer xem metadata thu thập và quyền chia sẻ.
- Finance/architect sử dụng TCO và migration preferences.

Để export dữ liệu mcdc lên Migration Center, tài liệu Google Cloud mô tả role Migration Center Admin và các permission liên quan tới source/report frames. Với từng phương pháp, cần kiểm tra quyền cụ thể. Dùng least privilege và tránh chia sẻ service account key tĩnh nếu có phương án xác thực an toàn hơn.

## 7. Thực hành mcdc CLI: khám phá máy ảo VMware

Ví dụ sau minh họa mcdc trên máy Linux có kết nối tới vCenter và có quyền đọc inventory. Các giá trị VSPHERE_URL, VCENTER_USER và PROJECT_ID là placeholder.

### Bước 1: tải công cụ

Từ tài liệu chính thức của Google Cloud, tải phiên bản mcdc dành cho Linux hoặc Windows. Kiểm tra yêu cầu hệ điều hành, dung lượng lưu trữ, kết nối mạng và checksum nếu nguồn phân phối cung cấp.

Không đưa binary collector hoặc thông tin xác thực vào Git. Dùng máy đánh giá có quyền tối thiểu và kết nối đến hạ tầng nguồn trong phạm vi cho phép.

### Bước 2: quét inventory qua vSphere API

~~~bash
./mcdc discover vsphere \
  --url https://VSPHERE_URL \
  -u VCENTER_USER
~~~

Công cụ sẽ yêu cầu credential tương ứng. Tùy quyền, có thể cần giới hạn path theo datacenter, cluster hoặc folder để không quét tài nguyên ngoài phạm vi.

Ví dụ quét riêng một folder:

~~~bash
./mcdc discover vsphere \
  --url https://VSPHERE_URL \
  -u VCENTER_USER \
  --path DATACENTER/vm/APPLICATION_FOLDER
~~~

Trước khi thực hiện trên production, xác nhận với nhóm hạ tầng về phạm vi API, firewall và thời điểm quét. Nếu cấu hình thống kê của vCenter chưa thu thập đủ số liệu hiệu năng, kết quả sizing có thể phải dùng mặc định.

### Bước 3: guest discovery bổ sung

Inventory ở hypervisor cho biết VM tồn tại, nhưng không nhất thiết cho biết process, database hoặc dependencies trong guest OS. Với Linux host cho phép SSH:

~~~bash
./mcdc discover ssh HOSTNAME_OR_IP
~~~

Với Windows guest, mcdc hỗ trợ phương thức tương ứng qua WMI hoặc script thu thập tại máy; cú pháp và yêu cầu tài khoản tùy phương pháp. Tài liệu cũng mô tả lệnh phát hiện database bằng option chọn engine cho guest discovery.

Guest discovery có thể thu thập process arguments, môi trường chạy và thông tin mạng có tính nhạy cảm. Cần đánh giá nội dung file thu thập, quyền và thời gian lưu trước khi export.

### Bước 4: tạo đánh giá offline

Sau discovery, tạo báo cáo HTML tóm tắt:

~~~bash
./mcdc report --format html --file assessment.html
~~~

mcdc hỗ trợ các định dạng báo cáo offline khác tùy mục đích, gồm HTML, JSON, CSV và XLSX. Báo cáo có thể thể hiện fit assessment cùng findings/blockers cho các migration journeys mà công cụ hỗ trợ.

Phân biệt "đánh giá offline" với "TCO online": báo cáo offline là thông tin phân tích cục bộ theo rules; báo cáo TCO trong Migration Center bổ sung asset groups và migration preferences để so sánh chi phí nhiều kịch bản.

### Bước 5: export lên Migration Center khi được phép

Sau khi kích hoạt project và thiết lập thông tin xác thực, lệnh minh họa:

~~~bash
./mcdc export mc --project PROJECT_ID
~~~

Lệnh này gửi discovery data lên Migration Center. **mcdc không tự upload dữ liệu chỉ vì bạn đã chạy discovery; export là hành động riêng cần được phê duyệt.**

Nếu môi trường không cho phép upload trực tiếp, có thể giữ assessment offline hoặc dùng luồng xuất file rồi upload qua quy trình được phê duyệt.

### Bước 6: kiểm tra sau export

- Số asset trong Migration Center có khớp nguồn được quét?
- Có tài sản trùng, thiếu hoặc khác tên không?
- CPU/RAM/disk của VM có đúng với vCenter không?
- Thông tin hiệu năng có đủ thời gian đại diện không?
- Database nào được nhận diện và engine/version có chính xác không?
- Có nguồn nào không thể discovery do thiếu quyền?
- Có dataset nào cần loại khỏi assessment vì nằm ngoài phạm vi?

Không chuyển thẳng tới thiết kế target nếu inventory chưa được làm sạch.

## 8. Import dữ liệu khi không thể cài discovery client

Một số tổ chức không được phép cho phép công cụ quét hệ thống production hoặc chưa có kết nối tới mọi phân đoạn mạng. Migration Center có các đường nhập thủ công.

| Nguồn | Phương pháp có thể dùng | Giới hạn cần lưu ý |
|---|---|---|
| VM và server | Template/tabular upload | Thiếu hiệu năng thì sizing phải dựa trên giả định |
| VMware | RVTools export và import theo định dạng được hỗ trợ | Có thể thiếu process, service và dependency trong guest |
| SQL Server/MySQL/PostgreSQL | Script khám phá database được hỗ trợ | Quyền và mức chi tiết tùy database engine |
| Hạ tầng nhiều nguồn | Kết hợp kết quả collector và CMDB | Cần đối chiếu ID để loại trùng |

Google Cloud mô tả giới hạn số asset theo project trong tài liệu import/quota. Nên kiểm tra giới hạn hiện hành trước khi chia project assessment; không chia tùy tiện vì có thể làm khó so sánh TCO toàn bộ phạm vi.

### Cảnh báo về chất lượng import

File hợp lệ về schema chưa có nghĩa dữ liệu chính xác. Kiểm tra:

- Mẫu số: số VM power-on và power-off, VM test, template.
- Đơn vị: GB/GiB, MHz/GHz, IOPS và percent.
- Múi giờ và thời gian quan sát.
- Resource ID duy nhất.
- Source và thời điểm xuất báo cáo.
- Giá trị mặc định bị trống hoặc tự động điền sai.
- Trùng lặp giữa inventory discovery và manual import.

Đối với data template, sử dụng định dạng chính thức của Migration Center. Không tự giả định tên cột hoặc thứ tự cột chỉ dựa vào CSV ví dụ trong bài học.

## 9. Xây dựng asset inventory có thể ra quyết định

Sau discovery, bước kế tiếp là làm giàu inventory bằng dữ liệu nghiệp vụ và dependency.

Ví dụ bảng quản trị nội bộ:

| Asset ID | Role | Criticality | Owner | Source | Mục tiêu dự kiến |
|---|---|---|---|---|---|
| vm-web-01 | Java web frontend | High | Commerce | VMware | Compute Engine hoặc Cloud Run sau refactor |
| vm-api-01 | Spring Boot API | Critical | Commerce | VMware | Compute Engine trước, Cloud Run sau |
| vm-db-01 | PostgreSQL | Critical | Data | VMware | Cloud SQL for PostgreSQL nếu tương thích |
| vm-batch-01 | Scheduled jobs | Medium | Operations | VMware | Cloud Run jobs / GKE / VM tùy nhu cầu |
| vm-report-01 | Reporting service | Low | Analytics | VMware | Chuyển sau đợt pilot |

Bảng trên là ví dụ, không phải kết quả Migration Center thực tế.

### Cột nên bổ sung

- Application và business capability.
- Environment: dev/test/staging/prod.
- Compliance classification.
- RTO/RPO và downtime tolerance.
- Peak season và maintenance window.
- OS/runtime/JDK/database versions.
- External connectivity và firewall requirements.
- License owner và hạn bảo trì.
- Migration strategy và migration wave.
- Blocker, decision owner, thời hạn xử lý.
- Confidence level của thông tin thu thập.

Mỗi quyết định nên có nguồn bằng chứng: collector, CMDB, log, tài liệu kiến trúc hoặc xác nhận của owner.

## 10. Asset groups và dependency analysis

Đơn vị di chuyển phù hợp thường là **một application group**, không phải một VM riêng lẻ. Một hệ thống có thể gồm load balancer, web tier, application tier, database, queue, scheduler và các tích hợp với đối tác.

~~~text
Khách hàng
    |
    v
Web / API Gateway
    |
    v
Java Checkout Service
    |
    +----> PostgreSQL
    |
    +----> Inventory Service
    |
    +----> Message Broker
    |
    +----> Payment Provider (external)
~~~

Nếu di chuyển Java Checkout Service nhưng vẫn để database và message broker ở datacenter cũ, latency và chi phí kết nối có thể tăng, đồng thời cutover trở nên khó hơn.

### Khi tạo nhóm tài sản

Migration Center cho phép nhóm assets để tạo báo cáo TCO. Nhóm nên dựa trên một hoặc nhiều ranh giới:

- Business application.
- Độ phụ thuộc mạng và dữ liệu.
- Nhóm sở hữu và lịch bảo trì.
- Mức độ nhạy cảm và compliance.
- Target architecture hoặc project/region.
- Migration wave dự kiến.

Asset group trong báo cáo chi phí không tự chứng minh toàn bộ dependency nghiệp vụ đã được nhận diện. Kết hợp network observation, sơ đồ kiến trúc, firewall logs, application configuration và phỏng vấn owner.

### Dependency matrix

| Nguồn | Đích | Giao thức | Mức độ quan trọng | Gợi ý kế hoạch |
|---|---|---|---|---|
| Checkout API | PostgreSQL | TCP/database | Critical | Di chuyển cùng nhóm hoặc duy trì kết nối ổn định |
| Checkout API | Inventory API | HTTPS | High | Kiểm thử network path và auth |
| Checkout API | Payment Provider | HTTPS external | Critical | Kiểm tra egress IP, TLS và allowlist |
| Batch Worker | Database | TCP/database | Medium | Có thể chuyển sau ứng dụng chính nếu tương thích |
| Reporting | Data export | File/SQL | Low | Phù hợp đợt sau |

Giữ lại nguồn và độ tin cậy của từng dependency. Mối kết nối quan sát được không luôn đồng nghĩa với dependency bắt buộc; ngược lại, kết nối chỉ xuất hiện cuối tháng có thể bị bỏ sót.

## 11. Migration preferences và các kịch bản mục tiêu

Sau khi có asset groups, Migration Center cho phép tạo các bộ **migration preferences**. Chúng điều khiển giả định dùng để tạo TCO report, ví dụ region, target product, machine series, sizing và một số yếu tố chi phí.

### Ví dụ các kịch bản

| Kịch bản | Mục tiêu | Giả định |
|---|---|---|
| A – Ưu tiên tương thích | Chuyển VM với thay đổi tối thiểu | Compute Engine, không rightsizing mạnh |
| B – Cân bằng chi phí | Dùng dữ liệu utilization để đề xuất VM nhỏ hơn | Compute Engine, sizing moderate |
| C – Tối ưu chi phí | Giảm cấp phát dư thừa quyết liệt | Compute Engine, sizing aggressive với kiểm tra peak |
| D – VMware continuity | Giữ mô hình VMware cho nhóm phù hợp | Google Cloud VMware Engine |
| E – Database managed | Đánh giá chuyển database được hỗ trợ | Target database managed theo preferences tương ứng |

Không có một kịch bản tốt nhất cho tất cả tài sản. Một ứng dụng critical cần headroom và RTO nghiêm ngặt có thể không phù hợp với aggressive rightsizing.

### Những thông số thường cần xem

- Region triển khai.
- Machine series hoặc nhóm machine type.
- Tenancy preference.
- Sizing strategy: no rightsizing, moderate, aggressive hoặc custom khi hỗ trợ.
- CPU/memory utilization và percentile.
- Storage sizing/multiplier.
- Uptime hoặc giờ sử dụng mỗi tháng.
- Network egress estimate.
- Licensing/OS edition và chi phí liên quan.
- Target product cho server hoặc database được hỗ trợ.

Preferences cho **server** và **database** có phạm vi riêng. Không giả định một cấu hình sizing cho server tự áp dụng cho SQL Server/PostgreSQL/MySQL.

### Vì sao phải tạo nhiều kịch bản?

Ví dụ, cùng một tập 20 VM:

- Kịch bản A giữ gần nguyên vCPU/RAM.
- Kịch bản B dùng số liệu utilization để chọn VM nhỏ hơn.
- Kịch bản C đặt yêu cầu memory headroom lớn hơn vì có batch peak.

So sánh giúp nhìn thấy chênh lệch chi phí dự kiến và trade-off hiệu năng. Đội ngũ kiến trúc cần kiểm chứng máy đề xuất có chịu được peak và yêu cầu license hay không trước khi chốt.

## 12. Đọc báo cáo Total Cost of Ownership (TCO)

Migration Center có thể tạo TCO report cho asset groups dựa trên preferences; ngoài ra có các báo cáo chi tiết pricing và asset inventory.

TCO thường hỗ trợ:

- Tóm tắt các tài sản và mức sử dụng.
- Gợi ý target product hoặc cấu hình tương ứng theo preferences.
- Chi phí hạ tầng ước tính cho nhóm/tài sản.
- So sánh kịch bản target region, sizing và loại sản phẩm.
- Các giả định ảnh hưởng đến ước tính.

### TCO không phải báo giá cố định

Chi phí thực tế còn phụ thuộc:

- Giá tại thời điểm triển khai và region.
- Mức sử dụng thực tế sau cutover.
- Egress, traffic liên vùng và đường truyền tới on-premises.
- Storage, backup, snapshot, logging/monitoring.
- License và cam kết sử dụng.
- Chi phí migration một lần: nhân sự, tooling, test, downtime.
- Chi phí vận hành song song hai môi trường trong quá trình chuyển đổi.
- Chi phí refactor, đào tạo và xử lý nợ kỹ thuật.

Vì vậy, dùng TCO để **so sánh và ra quyết định sơ bộ**, sau đó lập financial model đầy đủ hơn cho business case.

### Cẩn thận với server và database chạy cùng một máy

Tài liệu Google Cloud lưu ý: nếu group chứa cả database deployment và underlying server, báo cáo có thể ước tính server như VM độc lập và database như dịch vụ database riêng. Điều này có thể gây **double counting** khi thực tế dự định chỉ di chuyển database sang Cloud SQL và loại bỏ VM gốc. Nhóm tài chính/kiến trúc phải kiểm tra ranh giới ước tính.

### Kiểm tra chất lượng đầu ra

| Câu hỏi | Vì sao cần hỏi |
|---|---|
| Có đủ performance data không? | Thiếu dữ liệu có thể dẫn tới sizing dựa trên ước tính |
| Có asset bị đếm trùng không? | Làm sai số lượng và chi phí |
| Region có đúng policy không? | Giá và residency khác nhau |
| Disk và IOPS đã được xét chưa? | Dễ bỏ sót hiệu năng lưu trữ |
| Mức egress ước tính có thực tế không? | Chi phí network có thể đáng kể |
| Số giờ chạy/tháng có đúng không? | 24/7 khác workload theo lịch |
| License SQL/Windows/VMware tính thế nào? | Có thể thay đổi đáng kể TCO |
| Quy tắc rightsizing có quá mạnh không? | Rủi ro thiếu capacity |
| Có tính vận hành song song không? | Tránh báo cáo lợi ích quá lạc quan |

## 13. Đánh giá readiness: nhiều hơn khả năng boot VM

**Migration readiness** là mức độ sẵn sàng chuyển đổi trong phạm vi một mục tiêu cụ thể. Nó bao gồm phần cứng/OS, ứng dụng, dữ liệu, network, security, vận hành và nghiệp vụ.

| Trục | Câu hỏi | Bằng chứng cần có |
|---|---|---|
| OS/hardware | OS, CPU architecture và driver có được đích hỗ trợ? | Inventory, compatibility matrix |
| Application | Runtime, thư viện native, service và scheduler có phù hợp? | JDK/app-server versions, dependencies |
| Database | Engine/version, extensions, size, replication và downtime có tương thích? | Database assessment, migration test |
| Network | DNS, routing, firewall, latency, private connectivity và egress? | Dependency map, network design |
| Identity/security | IAM, service account, secrets, certificate, encryption, audit? | Security review và policy |
| Availability | SLO, RTO/RPO, failover và backup có đạt? | Thiết kế DR và diễn tập |
| Operations | Monitoring, logs, runbook, on-call và incident process đã có? | Operational readiness review |
| Business | Owner, maintenance window, downstream approval và cutover deadline? | Sign-off từ stakeholders |
| Cost | Chi phí target và effort có chấp nhận được? | TCO và business case |

Một kết quả assessment nói VM "Good fit" không có nghĩa các trục trên đều đạt. Fit result dựa trên dữ liệu và rules mà công cụ có.

### Fit assessment offline

mcdc offline assessment có thể phân loại theo các mức như:

- Excellent fit.
- Good fit, có findings cần lưu ý.
- Cần ít công việc trước khi migration.
- Cần công việc mức trung bình.
- Cần công việc lớn.
- No fit.
- Insufficient data.

Các nhãn này thuộc đánh giá offline cho những migration journeys được công cụ hỗ trợ. Cần đọc từng finding/blocker và rule liên quan. Không chuyển kết quả thành một điểm phần trăm rủi ro nếu công cụ không cung cấp thang đó.

### Missing data là một trạng thái có ý nghĩa

Nếu thiếu guest discovery, không nên mặc định workload tương thích. Cần xác định thông tin thiếu và kế hoạch bổ sung:

- Chạy guest scan có quyền phù hợp.
- Hỏi application owner.
- Kiểm tra OS, process, port, runtime và thư viện.
- Thử migration trên bản sao trong pilot.

Đặt confidence level cho mỗi asset và không dùng kết quả thiếu dữ liệu để chốt production cutover.

## 14. Đánh giá riêng ứng dụng Java/Spring trên GCP

Một VM chạy Java có thể chuyển nguyên trạng lên Compute Engine, nhưng để chạy trên Cloud Run/GKE cần đánh giá thêm cách ứng dụng được đóng gói và vận hành.

### Checklist tương thích Java

| Hạng mục | Nội dung đánh giá |
|---|---|
| JDK/runtime | Version, vendor, chính sách LTS, thư viện native |
| Application server | Tomcat, Jetty, WebLogic, JBoss và phụ thuộc cấu hình |
| Configuration | Environment variables, files, secrets và profile |
| Local filesystem | Upload, log, temp file, data bền vững |
| Session state | Session trong memory/local disk hay external store |
| Scheduling | Cron job, batch, background threads |
| Database | Driver JDBC, connection pool, transaction, schema |
| Network | Kết nối private, IP allowlist, DNS, outbound TLS |
| Authentication | Service account, OAuth, mTLS, legacy LDAP |
| Observability | Structured logs, metrics, traces, health checks |
| Startup/shutdown | Cold start, graceful shutdown, signal handling |
| Resilience | Timeout, retry, idempotency, scaling |

### Ví dụ chọn đích

**Compute Engine:** phù hợp khi cần giữ OS, ứng dụng monolith hoặc cấu hình VM gần nguyên trạng. Có thể rút ngắn đường chuyển, nhưng vẫn cần thiết kế backup, network, IAM, patching và autoscaling.

**Cloud Run:** phù hợp với dịch vụ HTTP/container có thể chạy theo model stateless hoặc dùng external state. Cần kiểm tra port, startup, concurrency, local disk tạm và background work.

**GKE:** phù hợp khi cần orchestration, sidecar, các workload có networking/operational requirements phức tạp hoặc đã có đội ngũ Kubernetes. Đổi lại, nhóm cần năng lực quản lý cluster, security và release.

**Cloud SQL:** phù hợp khi engine/version/features được hỗ trợ và có lộ trình chuyển dữ liệu với RTO/RPO đáp ứng. Không mặc định mọi extension hoặc tính năng database đều chuyển trực tiếp.

**Đích được chọn trong TCO** không tự đồng nghĩa với đường migration được công cụ bảo đảm hỗ trợ. Đội kiến trúc phải đánh giá riêng khả năng ứng dụng hoạt động trên đích đó.

## 15. 6R: chiến lược cho từng workload

Khung chiến lược 6R là công cụ thảo luận, không phải phép phân loại duy nhất bắt buộc của Migration Center.

| Chiến lược | Ý nghĩa | Ví dụ |
|---|---|---|
| Rehost | Chuyển phần lớn nguyên trạng | VM Java lên Compute Engine |
| Replatform | Thay đổi nền tảng nhưng ít sửa logic | Database sang Cloud SQL hoặc Java app sang managed runtime phù hợp |
| Refactor / Rearchitect | Thay đổi kiến trúc để tận dụng cloud | Tách monolith, dùng Pub/Sub, Cloud Run/GKE |
| Repurchase | Chuyển sang SaaS | Thay công cụ tự host bằng dịch vụ SaaS |
| Retire | Loại bỏ hệ thống không còn giá trị | VM reporting không còn người dùng |
| Retain | Giữ tạm tại on-premises/nguồn cũ | Ứng dụng có ràng buộc pháp lý hoặc thiết bị chuyên dụng |

Không chọn chiến lược chỉ từ CPU/RAM. Cần kết hợp deadline, technical debt, vòng đời ứng dụng, business criticality và năng lực phát triển.

Ví dụ một legacy Java VM có thể được rehost trước để đáp ứng hạn rời datacenter, sau đó refactor từng dịch vụ sang Cloud Run trong giai đoạn tối ưu. Kế hoạch hai giai đoạn có thể hợp lý hơn làm refactor lớn ngay trước cutover.

## 16. Mô hình ưu tiên: quick win và blockers

Tổ chức cần chọn thứ tự di chuyển dựa trên lợi ích, rủi ro và dependency. Một ma trận định tính có thể hỗ trợ họp đánh giá.

| Tiêu chí | Dễ di chuyển | Khó di chuyển |
|---|---|---|
| Technical compatibility | OS/runtime được hỗ trợ | OS cũ, thư viện native, device riêng |
| Dependency | Ít dependency | Nhiều hệ thống ngoài phạm vi |
| Data | Nhỏ, có replication | Rất lớn, downtime thấp |
| Security/compliance | Quy định rõ, target được chấp thuận | Residency/licensing chưa giải quyết |
| Operations | Có test/monitoring/runbook | Thiếu telemetry và owner |
| Business impact | Có maintenance window | Giao dịch 24/7, SLA nghiêm |
| Team readiness | Có IaC/CI/CD và người phụ trách | Thiếu kỹ năng và quyền truy cập |

Đừng gán điểm định lượng tùy ý rồi gọi đó là kết quả chính thức của Migration Center. Nếu nhóm muốn chấm điểm nội bộ, cần ghi công thức, trọng số, chủ sở hữu và bằng chứng để kết quả có thể review.

### Ưu tiên pilot

Một pilot tốt thường có:

- Giá trị kinh doanh đủ rõ.
- Phạm vi nhỏ và dependency đã được hiểu.
- Có thể kiểm thử, cutover và rollback.
- Ít rủi ro mất dữ liệu hoặc gián đoạn diện rộng.
- Cho phép kiểm chứng landing zone, network, IAM, telemetry và quy trình migration.

Không nhất thiết chọn VM nhỏ nhất nếu nó có nhiều dependency khó hiểu. Chọn workload đại diện nhưng kiểm soát được rủi ro.

## 17. Từ assessment tới migration waves

Migration wave là nhóm workload được di chuyển theo một đợt có dependency, thời gian và tiêu chí hoàn tất rõ ràng.

~~~text
Wave 0: Landing zone + connectivity + pilot
           |
           v
Wave 1: Ứng dụng ít phụ thuộc
           |
           v
Wave 2: Nhóm ứng dụng + database phụ thuộc
           |
           v
Wave 3: Hệ thống giao dịch trọng yếu
           |
           v
Wave 4: Tối ưu / decommission nguồn cũ
~~~

### Mỗi wave cần có gì?

- Danh sách asset và application group.
- Target product/region/project.
- Dependency cần chuyển cùng hoặc duy trì hybrid.
- Migration method và người vận hành.
- Bài test trước cutover.
- RTO/RPO, downtime window và người phê duyệt.
- Data sync/replication và cách bảo đảm consistency.
- Cutover steps: DNS, load balancing, route, secret, config.
- Rollback trigger và thời hạn rollback.
- Acceptance criteria và owner xác nhận.
- Kế hoạch decommission resource cũ sau thời gian quan sát.

Migration Center hỗ trợ inventory, grouping và dữ liệu hoạch định; orchestration và cutover thực tế cần dùng các công cụ và quy trình khác của tổ chức.

## 18. Tình huống thực tế: đánh giá Ứng dụng đặt hàng

Một công ty bán lẻ vận hành hệ thống đặt hàng trên VMware:

- 2 VM chạy Java/Spring Boot API.
- 1 VM chạy PostgreSQL.
- 1 VM xử lý batch và gửi email.
- Một dịch vụ thanh toán bên ngoài qua HTTPS.
- Một hệ thống ERP nội bộ qua VPN.

### Bước 1 – Discovery

Nhóm dùng mcdc kiểm tra inventory, guest discovery trên VM được phê duyệt và thu thập số liệu hiệu năng đủ chu kỳ. Phát hiện PostgreSQL dùng phần mở rộng cần kiểm tra, batch chỉ chạy đêm và API có kết nối cố định tới ERP.

### Bước 2 – Nhóm và làm sạch

Tạo nhóm "Order Management" gồm các VM ứng dụng và database. Bổ sung thông tin nghiệp vụ: SLO, RTO/RPO, giờ batch, owner ERP, quyền truy cập đối tác và yêu cầu dữ liệu.

### Bước 3 – TCO scenarios

- A: API/batch và DB đều giữ trên Compute Engine.
- B: API/batch trên Compute Engine, database chuyển sang Cloud SQL nếu tương thích.
- C: API refactor sang Cloud Run, batch sang Cloud Run jobs, database Cloud SQL.

TCO từ Migration Center chủ yếu phản ánh các nhóm target/chi phí được công cụ hỗ trợ; chi phí refactor, database migration và kết nối hybrid cần tính bổ sung ngoài báo cáo. Không báo cáo ba kịch bản như thể đều được Migration Center tự động mô hình hóa đầy đủ nếu tính năng chưa hỗ trợ.

### Bước 4 – Readiness review

| Thành phần | Phát hiện | Quyết định tạm thời |
|---|---|---|
| Java API | HTTP stateless, nhưng có session trong memory | Externalize session trước khi autoscale |
| PostgreSQL | Extension chưa xác minh trên Cloud SQL | Làm proof-of-concept compatibility |
| Batch | Chạy theo lịch, có file tạm | Đánh giá Cloud Run jobs và storage bền vững |
| ERP VPN | Latency và firewall rule chưa đo | Kiểm thử hybrid connectivity |
| Payment API | IP allowlist cố định | Thiết kế egress/NAT và xin phê duyệt |

### Bước 5 – Pilot

Chọn triển khai API bản sao trên Compute Engine hoặc Cloud Run trong staging, truy cập database thử nghiệm. Đo:

- Request latency.
- Error rate và timeout.
- Network latency qua VPN.
- Khả năng kết nối DB và connection pool.
- Deploy/rollback.
- Logs, metrics, traces và alerts.
- Chi phí thực tế trong giai đoạn thử.

### Bước 6 – Migration wave

Wave 0 xây landing zone và connectivity; Wave 1 thử batch ít quan trọng; Wave 2 chuyển API và database sau khi có kế hoạch đồng bộ dữ liệu; Wave 3 chuyển traffic production theo runbook. Cắt nguồn cũ chỉ sau khi xác nhận dữ liệu nhất quán, business checks đạt và hết thời gian rollback quy định.

## 19. Bảo mật dữ liệu trong quá trình discovery

Discovery thu thập metadata về hệ thống. Nó có thể bao gồm hostname, địa chỉ IP, process, service, network dependency, argument dòng lệnh và các giá trị khác có tính nhạy cảm tùy collector và phương thức.

Cần:

1. Xin phép owner và security team trước khi quét.
2. Giới hạn IP range, account và quyền trên hệ thống nguồn.
3. Đọc tài liệu thu thập dữ liệu của phương pháp được chọn.
4. Lưu dữ liệu khảo sát tại vị trí có IAM phù hợp.
5. Xác nhận quyền export dữ liệu lên Google Cloud trước khi upload.
6. Không đưa credential, private key hoặc dữ liệu khảo sát thô vào Git/ticket/chat.
7. Thiết lập retention và xóa bản xuất không còn cần thiết.
8. Ghi nhận mục đích sử dụng và người nhận báo cáo.
9. Kiểm tra residency region khi kích hoạt Migration Center.
10. Dùng offline assessment nếu yêu cầu bảo mật chưa cho phép upload.

Việc công cụ không chủ đích đọc nội dung ứng dụng hoặc tệp dữ liệu không loại trừ rủi ro từ process arguments, environment hoặc network metadata. Tài liệu Google Cloud mô tả guest discovery có thể thu thập giá trị nhạy cảm trong kết quả tại máy collector; hãy xem file đầu ra như tài sản nhạy cảm.

### IAM và lưu trữ

- Tách service account collector/export với account dùng để chạy ứng dụng production.
- Không cấp project Owner chỉ để thực hiện assessment nếu có quyền hẹp hơn.
- Dùng cơ chế xác thực được tổ chức phê duyệt.
- Theo dõi audit logs cho thay đổi quyền và hoạt động quản trị liên quan.
- Review quyền chia sẻ báo cáo TCO/inventory.
- Nếu sử dụng VPC Service Controls cho dữ liệu assessment, thiết kế perimeter theo khả năng hỗ trợ và kiểm thử đường export.

## 20. Sai lầm thường gặp khi đánh giá migration

| Sai lầm | Hệ quả | Cách tránh |
|---|---|---|
| Quét một lần ngoài giờ cao điểm | Đề xuất sizing quá nhỏ | Thu thập đủ chu kỳ và peak |
| Chỉ dùng dữ liệu hypervisor | Bỏ sót app/database và dependency | Kết hợp guest scan và phỏng vấn owner |
| Coi số VM là số ứng dụng | Lập wave sai và mất dependency | Nhóm theo business application |
| Tin rằng "Good fit" là bảo đảm migration thành công | Bỏ qua network, compliance, data và vận hành | Review blockers và chạy pilot |
| So sánh TCO mà không ghi preferences | Không thể giải thích chênh lệch | Version hóa assumption và scenarios |
| Đếm cả server và DB như hai workload độc lập | Double counting chi phí | Rà soát mô hình target của mỗi nhóm |
| Chuyển DB trước khi xác minh compatibility | Gián đoạn hoặc lỗi dữ liệu | Kiểm thử engine, extension và replication |
| Dùng default utilization khi có peak quan trọng | Thiếu capacity | Bổ sung performance data |
| Bỏ qua downtime/RTO/RPO | Cutover vi phạm nghiệp vụ | Owner xác nhận và diễn tập rollback |
| Upload discovery data chưa được phê duyệt | Rủi ro governance và privacy | Offline trước, duyệt dữ liệu xuất |
| Coi Migration Center là công cụ cutover | Kế hoạch migration thiếu bước thực thi | Phối hợp migration tooling và runbooks |
| Không theo dõi asset ngoài phạm vi | Thiếu hệ thống phụ thuộc | Ghi rõ exclusions và assumptions |

## 21. Checklist đầu ra trước khi chốt kế hoạch di chuyển

### Phạm vi và dữ liệu

- [ ] Đã có business objectives và owner.
- [ ] Đã thống nhất in-scope/out-of-scope.
- [ ] Phương pháp discovery phù hợp với từng nguồn.
- [ ] Đã đo performance đủ đại diện.
- [ ] Inventory được đối chiếu CMDB và source system.
- [ ] Đã gỡ trùng và ghi nhận missing data.
- [ ] Có danh sách dependency quan trọng và hệ thống bên ngoài.

### Assessment và chi phí

- [ ] Asset groups phản ánh ứng dụng, database và dependencies.
- [ ] Migration preferences được version hóa theo kịch bản.
- [ ] TCO được kiểm tra region, sizing, egress, license và uptime.
- [ ] Đã kiểm tra khả năng double counting server/database.
- [ ] Đã bổ sung migration effort, run-in-parallel và chi phí vận hành.
- [ ] Fit assessment được review theo từng finding/blocker.
- [ ] Có readiness matrix với owner và bằng chứng.

### Kế hoạch và vận hành

- [ ] Đích Compute Engine/Cloud SQL/Cloud Run/GKE được xác minh riêng.
- [ ] Các ứng dụng Java được review JDK/runtime, state, filesystem và kết nối.
- [ ] Có landing zone, VPC, IAM, logging và backup phù hợp.
- [ ] Có migration waves theo dependency và business priority.
- [ ] Mỗi wave có test, downtime, cutover, rollback và sign-off.
- [ ] Đã chọn pilot có thể kiểm chứng.
- [ ] Có cơ chế cập nhật inventory/assessment khi nguồn thay đổi.
- [ ] Tài liệu discovery và báo cáo được bảo vệ theo governance.

## Kết luận

Migration Center cung cấp nền tảng dữ liệu cho quyết định di chuyển lên Google Cloud: nhận diện tài sản, thu thập cấu hình/hiệu năng, lập nhóm, so sánh preferences và tính TCO. mcdc CLI giúp khám phá một lần hoặc đánh giá offline; discovery client phù hợp khi cần thu thập dữ liệu theo thời gian. Tuy nhiên, khả năng di chuyển của một workload chỉ được xác nhận khi kết hợp kết quả công cụ với **dependency, tương thích ứng dụng/dữ liệu, bảo mật, vận hành, yêu cầu downtime và pilot thực tế**. Một assessment tốt không chỉ đưa ra chi phí dự kiến mà còn chỉ rõ dữ liệu thiếu, những rủi ro phải xử lý, thứ tự migration waves và cách kiểm chứng thành công.

## Tài liệu tham khảo

- [Google Cloud Migration Center – tổng quan discovery và assessment](https://docs.cloud.google.com/migration-center/docs/discovery-and-assessment-overview)
- [Get started with Migration Center](https://docs.cloud.google.com/migration-center/docs/get-started-with-migration-center)
- [Start an asset discovery](https://docs.cloud.google.com/migration-center/docs/start-asset-discovery)
- [Migration Center discovery client CLI overview](https://docs.cloud.google.com/migration-center/docs/discovery-client-cli-overview)
- [Migration Center discovery client overview](https://docs.cloud.google.com/migration-center/docs/discovery-client-overview)
- [Run an inventory discovery](https://docs.cloud.google.com/migration-center/docs/run-inventory-discovery)
- [Run a guest discovery](https://docs.cloud.google.com/migration-center/docs/run-guest-discovery)
- [Run an IP range scan](https://docs.cloud.google.com/migration-center/docs/run-ip-range-scan)
- [Manual data import overview](https://docs.cloud.google.com/migration-center/docs/manual-import-overview)
- [Generate an offline assessment](https://docs.cloud.google.com/migration-center/docs/run-offline-assessment)
- [Offline assessment rules](https://docs.cloud.google.com/migration-center/docs/assessment-rules)
- [Export data to Migration Center](https://docs.cloud.google.com/migration-center/docs/export-collected-data)
- [Create migration preferences](https://docs.cloud.google.com/migration-center/docs/migration-preferences)
- [Migration preferences for servers](https://docs.cloud.google.com/migration-center/docs/server-preferences)
- [Generate TCO reports](https://docs.cloud.google.com/migration-center/docs/generate-tco-report)
- [Migration Center report types](https://docs.cloud.google.com/migration-center/docs/migration-center-reports)
- [Discovery client data and security](https://docs.cloud.google.com/migration-center/docs/discovery-client-data-and-security)

